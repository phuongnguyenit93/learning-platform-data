# Lặp lại phép đo, quan sát độ biến thiên và nhận diện nhiễu

## 1. Vì sao một lần đo chưa đủ?

Tối ưu hiệu năng cơ sở dữ liệu là quá trình thử một thay đổi, đo kết quả và quyết định có nên giữ thay đổi đó hay không. Một lần chạy benchmark có thể cho thấy truy vấn nhanh hơn, nhưng kết quả ấy chưa đủ để chứng minh thay đổi đã cải thiện hệ thống. Thời gian truy vấn còn chịu ảnh hưởng của cache, tải đồng thời, lịch chạy tác vụ nền, trạng thái lưu trữ, bộ lập lịch hệ điều hành và nhiều yếu tố khác.

Nếu chạy lại cùng một kịch bản nhiều lần, kết quả thường không hoàn toàn giống nhau. Sự chênh lệch giữa các lần đo được gọi là độ biến thiên. Một phần biến thiên là dao động tự nhiên của hệ thống; một phần khác đến từ nhiễu như checkpoint, tác vụ bảo trì, truy vấn khác tranh chấp tài nguyên hoặc sai lệch trong cách thu thập số liệu.

Vì vậy, khi đánh giá một thay đổi về chỉ mục, câu SQL, cấu hình bộ nhớ, connection pool hay giao dịch, cần lặp lại phép đo, ghi nhận độ biến thiên và tìm nguyên nhân của các lần chạy bất thường. Mục tiêu là xác định cải thiện có lặp lại được trong điều kiện tương đương hay chỉ xuất hiện tình cờ ở một lần chạy.

## 2. Phân biệt biến thiên và nhiễu

**Độ biến thiên** mô tả mức độ kết quả thay đổi giữa các lần đo hoặc trong một lần đo. Ví dụ, cùng một truy vấn có thời gian hoàn tất lần lượt là 48 ms, 51 ms, 49 ms và 53 ms. Các giá trị không giống nhau tuyệt đối, nhưng dao động quanh một mức tương đối ổn định.

**Nhiễu đo lường** là tác động ngoài điều cần khảo sát làm kết quả bị lệch hoặc dao động. Nhiễu có thể ngẫu nhiên, chẳng hạn một tiến trình khác bất chợt dùng CPU, hoặc có tính hệ thống, chẳng hạn mọi lần chạy phiên bản mới đều được thực hiện sau khi cache đã nóng trong khi phiên bản cũ luôn chạy với cache lạnh.

Hai khái niệm này liên quan nhưng không đồng nghĩa. Độ biến thiên là điều quan sát được trong dữ liệu; nhiễu là một nhóm nguyên nhân có thể tạo ra hoặc làm tăng biến thiên. Không phải mọi dao động đều là lỗi của công cụ đo, và một phép đo ổn định vẫn có thể sai lệch nếu tồn tại thiên lệch có hệ thống.

Trong đo hiệu năng cơ sở dữ liệu, nên phân biệt ít nhất ba tình huống:

- **Dao động tự nhiên:** tải nền và lịch thực thi thay đổi nhẹ dù môi trường được kiểm soát tương đối tốt.
- **Nhiễu có thể nhận diện:** một lần chạy trùng với checkpoint, backup, autovacuum, tác vụ ETL, truy vấn nặng khác hoặc sự kiện I/O bất thường.
- **Thiên lệch trong thiết kế phép thử:** thứ tự chạy, trạng thái cache, dữ liệu, kế hoạch thực thi hoặc mức đồng thời khác nhau giữa hai phương án.

Lặp lại phép đo giúp ước lượng mức biến thiên, nhưng không tự loại bỏ thiên lệch. Nếu tất cả lần chạy đều được thiết kế sai theo cùng một cách, số lần lặp nhiều hơn chỉ làm kết quả sai có vẻ chắc chắn hơn.

## 3. Những nguồn gây biến thiên trong hệ thống cơ sở dữ liệu

Trước khi chạy thử, hãy liệt kê các yếu tố có thể làm thay đổi kết quả. Việc này giúp chọn dữ liệu cần ghi nhận và giải thích được những lần chạy bất thường.

| Nhóm yếu tố | Ví dụ | Tác động có thể quan sát |
|---|---|---|
| Tải công việc | Số người dùng, tỷ lệ đọc/ghi, kích thước batch, phân bố khóa truy cập | Thông lượng và độ trễ thay đổi theo mức đồng thời hoặc mức tranh chấp |
| Cache và bộ nhớ | Buffer pool, page cache của hệ điều hành, plan cache, dữ liệu vừa được đọc | Lần chạy sau có thể ít đọc đĩa hơn hoặc tái sử dụng kế hoạch đã biên dịch |
| Trạng thái dữ liệu | Kích thước bảng, độ phân mảnh, thống kê, dữ liệu nóng/lạnh | Kế hoạch thực thi, số trang phải đọc và lượng công việc thay đổi |
| Tác vụ nền của cơ sở dữ liệu | Checkpoint, vacuum, phân tích thống kê, backup, replication, ghi log | CPU, I/O, khóa hoặc độ trễ ghi tăng trong một số khoảng thời gian |
| Tranh chấp đồng thời | Giao dịch khác, khóa hàng/bảng, latch, connection pool | Thời gian chờ tăng dù bản thân câu SQL không đổi |
| Hạ tầng | CPU bị chia sẻ, giới hạn IOPS, hàng đợi lưu trữ, mạng, máy ảo dùng chung | Thời gian thực thi dao động giữa các lần chạy |
| Công cụ đo | Đồng hồ không phù hợp, lấy mẫu thưa, ghi log đồng bộ, bộ sinh tải quá tải | Số liệu thiếu, sai độ phân giải hoặc chính công cụ tạo thêm tải |

Ví dụ, một truy vấn đọc nhiều trang có thể nhanh hơn rõ rệt ở lần chạy thứ hai vì dữ liệu đã nằm trong buffer pool. Đây là hiệu ứng cache, không nhất thiết là cải thiện do thay đổi SQL. Nếu muốn đánh giá trạng thái cache nóng, hãy làm nóng cache theo quy trình giống nhau cho cả hai phương án. Nếu muốn đánh giá lần truy cập lạnh, cần có quy trình tạo trạng thái lạnh có thể lặp lại và ghi rõ giới hạn của môi trường thử nghiệm.

Tương tự, nếu một phương án được đo khi máy chủ nhàn rỗi còn phương án kia được đo trong lúc backup, so sánh đó không cô lập được tác động của thay đổi. Hãy ghi nhận tác vụ nền và trạng thái máy chủ trong từng lần chạy.

## 4. Thiết kế phép đo có thể lặp lại

Một phép thử tốt bắt đầu bằng việc định nghĩa rõ câu hỏi. Chẳng hạn: “Chỉ mục mới có giảm thời gian truy vấn tìm đơn hàng theo khách hàng ở tải đọc hỗn hợp hay không?” Câu hỏi cụ thể giúp xác định kịch bản, chỉ số và điều kiện cần giữ ổn định.

### 4.1. Cố định kịch bản và dữ liệu

Trước mỗi lần chạy, ghi lại:

- Phiên bản ứng dụng, cơ sở dữ liệu, driver và cấu hình liên quan.
- Schema, chỉ mục, thống kê, kích thước dữ liệu và cách sinh dữ liệu thử.
- Tập câu lệnh, tham số, tỷ lệ đọc/ghi, kích thước batch và phân bố truy cập.
- Số client, số kết nối, mức đồng thời và thời gian chạy.
- Điều kiện cache, trạng thái warm-up, chế độ transaction và mức cô lập.
- Máy chủ, CPU, bộ nhớ, loại lưu trữ, giới hạn I/O và tải nền có liên quan.

Giữ nguyên các yếu tố này giữa các phương án, trừ yếu tố đang được thử nghiệm. Nếu thay đổi đồng thời câu SQL, chỉ mục và cấu hình pool, kết quả có thể tốt hơn nhưng ta không biết yếu tố nào tạo ra khác biệt.

### 4.2. Tách warm-up và giai đoạn đo

Lần chạy đầu có thể bao gồm thời gian khởi tạo kết nối, nạp lớp hoặc driver, biên dịch kế hoạch, nạp trang dữ liệu và làm nóng cache. Nếu mục tiêu là đo hiệu năng ổn định, hãy chạy warm-up trước, sau đó chỉ ghi nhận cửa sổ đo đã định nghĩa. Không cộng thời gian warm-up vào kết quả của một phương án nhưng loại bỏ ở phương án còn lại.

Nếu mục tiêu là đánh giá cold start hoặc truy cập dữ liệu lạnh, hãy đo riêng tình huống đó. Không dùng kết quả cache nóng để đại diện cho cache lạnh hoặc ngược lại. Trong một số môi trường, không thể xóa sạch mọi lớp cache; khi ấy phải mô tả trạng thái thực tế và giới hạn của phép thử.

### 4.3. Lặp lại và thay đổi thứ tự chạy

Chạy nhiều lần độc lập với cùng kịch bản. Không có một con số lần lặp phù hợp cho mọi phép thử. Có thể bắt đầu bằng một đợt chạy thăm dò để ước lượng độ biến thiên, sau đó quyết định số lần lặp dựa trên độ ổn định cần đạt, chi phí chạy và mức cải thiện muốn phát hiện. Nếu kết quả còn dao động mạnh, cần thêm lần chạy hoặc kiểm soát nguồn biến thiên trước khi kết luận.

Khi so sánh phương án A và B, không nên luôn chạy toàn bộ A trước rồi mới chạy toàn bộ B. Máy chủ có thể nóng lên, cache thay đổi hoặc tải nền tăng dần theo thời gian. Hãy cân nhắc ghép cặp và đổi thứ tự, ví dụ A-B, B-A, A-B, B-A. Cách này giúp mỗi phương án được đo trong các khoảng thời gian gần nhau và giảm ảnh hưởng của xu hướng môi trường.

Nếu có thể, dùng cùng một tập dữ liệu và cùng seed sinh dữ liệu. Với các phép thử có trạng thái thay đổi dữ liệu, hãy khôi phục snapshot hoặc tạo lại trạng thái đầu vào tương đương trước mỗi lần chạy. Nếu không thể khôi phục, phải ghi rõ trạng thái dữ liệu đã thay đổi và cân nhắc thiết kế thử nghiệm khác.

### 4.4. Chọn cửa sổ đo và tải ổn định

Không nên lấy vài giây đầu khi hệ thống còn khởi động làm đại diện cho toàn bộ tải ổn định. Xác định trước thời gian warm-up, thời gian đo và điều kiện dừng. Với tải kéo dài, chia kết quả thành các khoảng thời gian để phát hiện drift, checkpoint hoặc hàng đợi tăng dần.

Đồng thời theo dõi tốc độ yêu cầu đến và tốc độ hoàn tất. Nếu bộ sinh tải không phát đủ yêu cầu vì chính nó đã quá tải, thông lượng đo được không còn đại diện cho năng lực của cơ sở dữ liệu. Nếu hàng đợi tăng liên tục, hệ thống có thể chưa ở trạng thái ổn định; không nên diễn giải một cửa sổ ngắn như kết quả bền vững.

## 5. Thu thập số liệu ở cấp lần chạy và cấp yêu cầu

Mỗi lần chạy nên có một mã định danh để liên kết cấu hình, log, số liệu và sự kiện xảy ra. Tối thiểu cần ghi:

| Nhóm số liệu | Chỉ số nên theo dõi |
|---|---|
| Kết quả công việc | Số yêu cầu hoàn tất, thông lượng, số lỗi, timeout và retry |
| Độ trễ | Trung bình, trung vị, p95, p99 và phân bố thời gian phản hồi |
| Đồng thời và hàng đợi | Số truy vấn đang chạy, số giao dịch đang mở, thời gian chờ pool và độ dài hàng đợi |
| Tài nguyên | CPU, bộ nhớ, đọc/ghi I/O, IOPS, throughput lưu trữ, độ trễ thiết bị và mạng |
| Cơ sở dữ liệu | Kế hoạch thực thi, số lần đọc trang, cache hit, wait events, khóa và thời gian ghi log |
| Điều kiện thử | Mã lần chạy, thời điểm, cấu hình, trạng thái cache, warm-up, tải nền và ghi chú sự kiện |

Giữ lại dữ liệu thô theo từng lần chạy. Báo cáo chỉ có một con số tổng hợp sẽ che khuất các đợt chậm hoặc những lần chạy không bình thường. Khi có thể, lưu cả chuỗi thời gian theo khoảng ngắn để đối chiếu thời điểm độ trễ tăng với CPU, I/O, khóa, checkpoint hoặc hoạt động của bộ sinh tải.

Không nhầm số lượng mẫu yêu cầu với số lần chạy độc lập. Một lần benchmark có thể chứa hàng trăm nghìn yêu cầu, nhưng các yêu cầu trong cùng cửa sổ thường chịu chung trạng thái cache, tải nền và hàng đợi; chúng không nhất thiết là hàng trăm nghìn quan sát độc lập. Khi so sánh hai phương án, cần xem xét độ biến thiên giữa các lần chạy độc lập, đồng thời dùng phân bố cấp yêu cầu để hiểu độ trễ bên trong từng lần chạy.

## 6. Đo và diễn giải độ biến thiên

Không có một thống kê duy nhất phù hợp cho mọi phân bố. Hãy chọn cách tóm tắt theo hình dạng dữ liệu và câu hỏi đang trả lời.

### 6.1. Trung bình, trung vị và độ lệch chuẩn

- **Trung bình** hữu ích khi muốn biết thời gian hoặc thông lượng trung bình trên toàn bộ công việc. Giá trị này nhạy với các lần chạy cực đoan.
- **Trung vị (median)** là giá trị ở giữa sau khi sắp xếp. Nó ít bị kéo lệch bởi một vài lần chạy rất chậm.
- **Độ lệch chuẩn (standard deviation)** mô tả mức phân tán quanh trung bình. Độ lệch chuẩn lớn cho thấy kết quả biến thiên mạnh hơn, nhưng cần đọc cùng đơn vị và quy mô trung bình.
- **Khoảng tứ phân vị (IQR)** là chênh lệch giữa phân vị 75 và phân vị 25, giúp mô tả độ rộng của nửa giữa phân bố.

Hệ số biến thiên (coefficient of variation, CV) biểu diễn độ lệch chuẩn tương đối so với trung bình:

\[
CV = \frac{s}{\bar{x}} \times 100\%
\]

Trong đó \(s\) là độ lệch chuẩn mẫu và \(\bar{x}\) là trung bình mẫu. CV thuận tiện khi so sánh độ phân tán tương đối giữa các chỉ số có mức trung bình khác nhau, nhưng không nên dùng máy móc khi trung bình gần 0 hoặc dữ liệu có phân bố đặc biệt.

### 6.2. Ví dụ so sánh hai phương án

Giả sử đo thời gian phản hồi trung bình của cùng một truy vấn trong năm lần chạy độc lập. Các lần chạy dùng cùng dữ liệu, tải và quy trình warm-up:

| Lần chạy | Phương án A (ms) | Phương án B (ms) |
|---:|---:|---:|
| 1 | 100 | 92 |
| 2 | 102 | 94 |
| 3 | 98 | 91 |
| 4 | 101 | 93 |
| 5 | 99 | 90 |
| **Trung bình** | **100** | **92** |
| **Trung vị** | **100** | **92** |

Trong ví dụ này, phương án B có thời gian trung bình thấp hơn 8 ms, tương đương giảm 8% so với A. Các lần chạy cũng khá gần nhau. Đây là dấu hiệu tích cực, nhưng năm lần chạy chỉ là ví dụ minh họa; để kết luận trong một dự án thực tế, cần xem mức biến thiên quan sát được, độ chính xác mong muốn và tính đại diện của tải thử.

Giả sử một lần chạy của A đột ngột tăng lên 150 ms do checkpoint. Không nên âm thầm xóa giá trị này để làm kết quả đẹp hơn. Hãy giữ lại dữ liệu, kiểm tra log và chuỗi thời gian, ghi nhận sự kiện, rồi quyết định theo quy tắc loại trừ đã xác định trước. Nếu checkpoint là một phần của vận hành bình thường, tác động của nó có thể là điều cần đánh giá chứ không phải dữ liệu vô ích.

### 6.3. Phân vị và đuôi độ trễ

Trung bình có thể che khuất một nhóm yêu cầu rất chậm. p95 là mức thời gian mà khoảng 95% quan sát không vượt quá; p99 mô tả đuôi chậm hơn nữa. Khi hệ thống phục vụ người dùng, cần theo dõi p95/p99 song song với trung bình để biết thay đổi có cải thiện trải nghiệm của đa số và nhóm yêu cầu chậm hay không.

Hãy tính phân vị trên cùng loại yêu cầu, cùng cửa sổ và cùng cách lấy mẫu. Nếu mỗi lần chạy có tải hoặc số lượng yêu cầu khác nhau đáng kể, việc gộp tất cả mẫu thô có thể khiến lần chạy có nhiều yêu cầu chi phối kết quả. Nên báo cáo phân vị theo từng lần chạy, sau đó so sánh các lần chạy tương ứng hoặc nêu rõ cách tổng hợp.

### 6.4. Độ bất định và mức cải thiện có ý nghĩa

Một khác biệt nhỏ hơn mức dao động giữa các lần chạy có thể chưa đủ bằng chứng để khẳng định thay đổi tạo ra cải thiện. Có thể dùng khoảng tin cậy cho trung bình hoặc trung vị, bootstrap cho thống kê phù hợp, hay phân tích chênh lệch theo cặp A/B. Phương pháp cần phù hợp với phân bố và thiết kế thử nghiệm.

Khi ghép cặp, tính chênh lệch giữa A và B trong từng cặp gần nhau về thời gian, sau đó xem phân bố của các chênh lệch. Cách này thường giúp giảm ảnh hưởng của biến động môi trường chung. Nếu số liệu có tự tương quan theo thời gian, không nên giả định từng yêu cầu liên tiếp là mẫu độc lập để tạo khoảng tin cậy quá hẹp.

Hãy phân biệt **ý nghĩa thống kê** và **ý nghĩa vận hành**. Một thay đổi rất nhỏ có thể đo được khi số mẫu lớn nhưng không đủ quan trọng để bù chi phí tạo và duy trì chỉ mục. Ngược lại, giảm p99 hoặc giảm timeout có thể có giá trị lớn dù trung bình chỉ thay đổi ít. Đặt trước ngưỡng cải thiện có ý nghĩa đối với hệ thống và xem xét cả độ bất định trước khi quyết định.

## 7. Nhận diện và xử lý các lần chạy nhiễu

Khi một lần chạy lệch rõ rệt, hãy điều tra trước khi loại bỏ. Có thể dùng quy trình:

1. Đối chiếu mã lần chạy, thời điểm bắt đầu/kết thúc và cấu hình thực tế với kế hoạch thử.
2. Xem chuỗi thời gian để xác định độ trễ tăng trong toàn bộ lần chạy hay chỉ ở một khoảng ngắn.
3. Đối chiếu CPU, bộ nhớ, I/O, mạng, hàng đợi, khóa và wait events tại đúng thời điểm.
4. Kiểm tra log tác vụ nền như checkpoint, backup, vacuum, cập nhật thống kê, replication hoặc batch job.
5. Kiểm tra bộ sinh tải và công cụ giám sát có bị quá tải, mất mẫu hoặc tạo thêm I/O hay không.
6. Ghi nguyên nhân đã xác nhận, mức độ tin cậy và quy tắc xử lý; nếu không tìm được nguyên nhân, giữ lần chạy trong tập dữ liệu và báo cáo ảnh hưởng của nó.

Không nên loại mọi giá trị lớn hơn một ngưỡng tùy ý chỉ vì chúng làm kết quả xấu đi. Quy tắc loại trừ phải được xác định trước, có lý do kỹ thuật và áp dụng nhất quán cho cả hai phương án. Nếu một sự kiện vận hành thường xuyên xảy ra trong môi trường thật, cần đo tác động của sự kiện đó trong một kịch bản riêng hoặc trong bài thử đại diện.

Một lỗi khác là chỉ nhìn số trung bình toàn lần chạy. Ví dụ, truy vấn có thể nhanh trong phần lớn thời gian nhưng chậm đột biến mỗi khi checkpoint diễn ra. Biểu đồ theo thời gian và log sự kiện sẽ giúp phát hiện mẫu hình này; trung bình đơn lẻ có thể che mất vấn đề.

## 8. Quy trình thực hành khi đánh giá một thay đổi

Có thể dùng quy trình sau để đánh giá một chỉ mục mới, một cách viết lại SQL hoặc điều chỉnh cấu hình:

1. **Đặt giả thuyết.** Nêu thay đổi dự kiến tác động đến phần nào, chẳng hạn giảm số trang đọc hoặc giảm thời gian chờ khóa.
2. **Chọn chỉ số chính và chỉ số bảo vệ.** Ví dụ, thời gian truy vấn và thông lượng là chỉ số chính; p99, lỗi, CPU, I/O và thời gian ghi là chỉ số bảo vệ.
3. **Chuẩn hóa môi trường.** Cố định dữ liệu, kịch bản, cấu hình và điều kiện cache; ghi lại các khác biệt không thể kiểm soát.
4. **Chạy thử thăm dò.** Xác nhận bộ sinh tải hoạt động đúng, hệ thống vào trạng thái ổn định và số liệu được thu thập đầy đủ.
5. **Lặp lại có ghép cặp hoặc đổi thứ tự.** Thực hiện đủ số lần để đánh giá độ biến thiên và tránh thiên lệch do luôn chạy một phương án trước.
6. **Giữ dữ liệu thô và đánh dấu sự kiện.** Gắn mã cho từng lần chạy, lưu log, kế hoạch thực thi và số liệu tài nguyên.
7. **Phân tích phân bố và độ bất định.** So sánh trung bình, trung vị, độ phân tán, p95/p99 và chênh lệch theo cặp; điều tra các lần chạy bất thường.
8. **Đánh giá tác động tổng thể.** Kiểm tra lợi ích có lặp lại, có đạt ngưỡng vận hành và có gây suy giảm ở chỉ số khác hay không.
9. **Lặp lại trong điều kiện đại diện.** Xác nhận kết quả với tải hỗn hợp, giờ cao điểm hoặc trạng thái cache phù hợp trước khi áp dụng rộng.

Ví dụ, thêm chỉ mục có thể làm truy vấn SELECT nhanh hơn nhưng khiến INSERT/UPDATE chậm hơn và tăng dung lượng lưu trữ. Vì vậy, benchmark cần chứa cả truy vấn đọc và ghi đại diện. Nếu chỉ đo một câu SELECT riêng lẻ, ta có thể kết luận tốt về câu truy vấn nhưng chưa đánh giá được tác động của chỉ mục lên toàn hệ thống.

Một báo cáo kết quả nên ghi cả kết luận và giới hạn: số lần chạy, cách ghép cặp, trạng thái cache, mức tải, thống kê được dùng, sự kiện nhiễu đã xác nhận, các lần chạy bị loại theo quy tắc nào và những điều kiện chưa được kiểm thử. Người khác cần có đủ thông tin để tái lập phép đo.

## 9. Những sai lầm thường gặp

- **Chỉ chạy một lần:** kết quả có thể trùng với một trạng thái cache hoặc tải nền đặc biệt. Hãy lặp lại và xem độ phân tán.
- **Chạy A rồi mới chạy B trong thời gian dài:** xu hướng tải, nhiệt độ, cache hoặc tác vụ nền có thể tạo thiên lệch thứ tự. Hãy đổi thứ tự hoặc ghép cặp.
- **Bỏ warm-up ở một phương án:** hai phương án không được đo trong cùng điều kiện. Xác định trước mục tiêu cache nóng hay lạnh và áp dụng nhất quán.
- **Xóa outlier không có quy tắc:** việc này có thể loại bỏ chính sự cố người dùng gặp. Giữ dữ liệu gốc và điều tra sự kiện trước khi quyết định.
- **Coi hàng triệu request là hàng triệu lần chạy độc lập:** các request trong cùng một lần chạy thường chia sẻ trạng thái và chịu tự tương quan. Phân tích cả mức biến thiên giữa các lần chạy.
- **Chỉ báo cáo trung bình:** đuôi độ trễ và các lần chạy bất thường có thể bị che khuất. Bổ sung median, p95/p99 và độ phân tán.
- **Chỉ nhìn thời gian truy vấn:** thay đổi có thể tăng CPU, I/O, thời gian ghi hoặc tranh chấp ở tải hỗn hợp. Theo dõi chỉ số bảo vệ.
- **Thay nhiều yếu tố cùng lúc:** không thể quy kết nguyên nhân cho một thay đổi cụ thể. Tách biến hoặc thiết kế thử nghiệm phù hợp.
- **Nhầm ổn định với chính xác:** kết quả lặp lại rất sát nhau vẫn có thể bị thiên lệch do cấu hình hoặc cách đo sai.
- **Dùng số lần lặp tùy tiện:** quá ít lần có thể bỏ sót biến thiên; quá nhiều lần trong cùng điều kiện sai không sửa được thiên lệch. Chọn số lần dựa trên độ biến thiên và mức cải thiện cần phát hiện.

## 10. Bài tập tự kiểm tra

**Bài 1.** Một truy vấn được đo năm lần với kết quả 40 ms, 42 ms, 41 ms, 39 ms và 68 ms. Bạn sẽ báo cáo chỉ số nào và cần kiểm tra điều gì trước khi kết luận?

*Gợi ý:* Có thể báo cáo trung bình, trung vị và độ phân tán; kiểm tra log và chuỗi thời gian của lần chạy 68 ms để tìm checkpoint, tải nền, cache miss, khóa hoặc sự cố của bộ sinh tải. Không tự ý xóa giá trị đó.

**Bài 2.** Nhóm phát triển luôn chạy phiên bản cũ trước, sau đó mới chạy phiên bản mới. Vì sao thiết kế này có thể tạo thiên lệch và nên thay đổi thế nào?

*Gợi ý:* Trạng thái máy chủ có thể thay đổi theo thời gian. Ghép cặp các lần chạy gần nhau và đổi thứ tự A-B/B-A giúp giảm ảnh hưởng của xu hướng môi trường.

**Bài 3.** Một thay đổi làm thời gian trung bình giảm 3%, nhưng p99 tăng 25% và số timeout tăng. Có nên xem đây là cải thiện hiệu năng không?

*Gợi ý:* Chưa thể kết luận là cải thiện tổng thể. Cần xem mục tiêu vận hành, phân bố độ trễ, timeout, tải hỗn hợp và nguyên nhân đuôi chậm. Trung bình tốt hơn không bù được suy giảm nghiêm trọng ở nhóm yêu cầu chậm nếu chúng ảnh hưởng người dùng.

## 11. Ghi nhớ khi đo hiệu năng

Phép đo đáng tin cậy cần có kịch bản rõ ràng, điều kiện tương đương, nhiều lần chạy và dữ liệu đủ để giải thích biến thiên. Hãy tách warm-up khỏi cửa sổ đo, ghi nhận trạng thái cache và tải nền, đổi thứ tự khi so sánh các phương án, đồng thời giữ lại dữ liệu thô của từng lần chạy.

Khi phân tích, dùng trung bình cùng trung vị và độ phân tán; theo dõi p95/p99 để hiểu đuôi độ trễ; xem xét độ bất định và tác động vận hành trước khi chấp nhận thay đổi. Một kết quả chỉ đáng tin khi có thể lặp lại trong điều kiện đại diện và không đánh đổi một chỉ số quan trọng khác mà ta chưa đo.

Trong tối ưu hiệu năng cơ sở dữ liệu, đo đạc là nền tảng để quyết định về chỉ mục, SQL, giao dịch, bộ nhớ và I/O. Lặp lại phép đo và nhận diện nhiễu giúp phân biệt tác động thật của điều chỉnh với dao động của môi trường, từ đó đưa ra quyết định có căn cứ và có thể kiểm chứng.
