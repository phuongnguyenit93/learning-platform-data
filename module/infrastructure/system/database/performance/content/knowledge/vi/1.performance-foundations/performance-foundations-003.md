# Các tài nguyên giới hạn: CPU, bộ nhớ, lưu trữ, mạng và khả năng xử lý đồng thời

Hiệu năng cơ sở dữ liệu phụ thuộc vào cách một tải công việc sử dụng những tài nguyên hữu hạn. Một truy vấn có thể cần CPU để tính toán, bộ nhớ để giữ dữ liệu trung gian, lưu trữ để đọc và ghi trang dữ liệu, mạng để trao đổi kết quả, đồng thời phải chờ các giao dịch khác nhả khóa hoặc nhường quyền truy cập. Khi một tài nguyên trở thành giới hạn, tăng tài nguyên ở nơi khác thường không cải thiện được thời gian phản hồi.

Trong module **DATABASE_PERFORMANCE**, việc tối ưu phải dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Bài học này xây dựng nền tảng để nhận diện giới hạn CPU, bộ nhớ, lưu trữ, mạng và xử lý đồng thời. Những hiểu biết đó giúp ta chọn đúng hướng khi thiết kế chỉ mục, cải thiện SQL, xử lý tranh chấp giao dịch và kiểm chứng kết quả sau điều chỉnh.

Sau bài học, người học có thể:

- Phân biệt độ trễ, thông lượng, mức đồng thời và thời gian chờ.
- Nhận diện dấu hiệu của nút thắt CPU, bộ nhớ, lưu trữ, mạng và khóa giao dịch.
- Chọn số liệu phù hợp để kiểm tra một giả thuyết về hiệu năng.
- Giải thích vì sao tăng số kết nối hoặc tăng tài nguyên không phải lúc nào cũng làm hệ thống nhanh hơn.
- Lập một quy trình đo trước, điều chỉnh có kiểm soát và đo lại sau thay đổi.

## 1. Hiệu năng là bài toán phân bổ tài nguyên

### 1.1. Tải công việc và tài nguyên

Một hệ quản trị cơ sở dữ liệu (DBMS) phục vụ nhiều loại công việc: tìm kiếm một bản ghi, cập nhật số dư, tổng hợp báo cáo, ghi nhật ký, tạo chỉ mục hoặc đồng bộ dữ liệu. Mỗi loại công việc tiêu thụ tài nguyên theo cách khác nhau.

| Tài nguyên | Công việc thường tiêu thụ | Dấu hiệu có thể quan sát |
|---|---|---|
| CPU | Phân tích SQL, lập kế hoạch, nối bảng, sắp xếp, tính biểu thức, mã hóa | CPU bận kéo dài, hàng đợi chạy, truy vấn tốn CPU |
| Bộ nhớ | Bộ đệm trang dữ liệu, cache, sort, hash join, dữ liệu trung gian, phiên kết nối | Thiếu bộ nhớ, phân trang, ghi dữ liệu tạm, cache bị đẩy ra |
| Lưu trữ | Đọc trang dữ liệu, ghi dữ liệu, WAL/redo log, checkpoint, đồng bộ bền vững | Độ trễ I/O cao, hàng đợi thiết bị dài, tiến trình chờ đọc/ghi |
| Mạng | Gửi câu lệnh, trả kết quả, sao chép dữ liệu, giao tiếp giữa ứng dụng và DBMS | RTT cao, băng thông bão hòa, truyền quá nhiều dữ liệu |
| Xử lý đồng thời | Khóa, chốt nội bộ, lịch chạy, quản lý phiên và giao dịch | Chờ khóa, deadlock, hàng đợi kết nối, nhiều phiên tranh chấp |

Các tài nguyên có quan hệ với nhau. Một truy vấn đọc nhiều trang từ đĩa có thể làm tăng I/O, sau đó sử dụng CPU để lọc và sắp xếp dữ liệu. Một truy vấn trả về hàng triệu dòng vừa tiêu thụ tài nguyên máy chủ, vừa chiếm băng thông và thời gian xử lý ở ứng dụng. Một giao dịch giữ khóa lâu có thể khiến nhiều giao dịch khác chờ dù CPU và ổ đĩa vẫn còn dư.

Vì vậy, cần tìm ra đoạn nào của đường đi xử lý đang giới hạn toàn hệ thống thay vì chỉ nhìn một chỉ số riêng lẻ.

### 1.2. Độ trễ, thông lượng và mức đồng thời

Ba khái niệm cần được phân biệt:

- **Độ trễ (latency):** thời gian một yêu cầu cần để hoàn thành. Với cơ sở dữ liệu, có thể đo thời gian thực thi một câu SQL hoặc thời gian toàn bộ yêu cầu ứng dụng chờ kết quả.
- **Thông lượng (throughput):** số yêu cầu hoặc giao dịch hoàn thành trong một đơn vị thời gian, chẳng hạn truy vấn/giây hoặc giao dịch/giây.
- **Mức đồng thời (concurrency):** số công việc đang hoạt động cùng lúc, bao gồm cả công việc đang chạy và công việc đang chờ.

Một hệ thống có thể có thông lượng cao nhưng độ trễ của một số yêu cầu vẫn lớn. Ví dụ, các truy vấn ngắn được xử lý nhanh trong khi một truy vấn báo cáo dài chiếm nhiều tài nguyên. Ngược lại, một truy vấn riêng lẻ có thể chạy nhanh trong thử nghiệm đơn người dùng nhưng chậm đi rõ rệt khi hàng trăm giao dịch cùng truy cập một bản ghi.

Cũng cần phân biệt thời gian phục vụ và thời gian chờ. Thời gian một yêu cầu nằm trong hệ thống có thể gồm:

1. Chờ ứng dụng lấy được kết nối.
2. Chờ DBMS lập lịch hoặc chờ tài nguyên.
3. Chờ khóa hay chốt nội bộ.
4. Thực thi CPU và đọc/ghi dữ liệu.
5. Truyền kết quả qua mạng và xử lý ở phía ứng dụng.

Nếu chỉ đo thời gian chạy SQL ở môi trường thử nghiệm đơn giản, ta có thể bỏ sót thời gian chờ kết nối, chờ khóa hoặc truyền dữ liệu trong môi trường thực tế.

### 1.3. Định luật Little và tác động của hàng đợi

Trong trạng thái ổn định, định luật Little mô tả quan hệ giữa số công việc trung bình trong hệ thống, thông lượng và thời gian trung bình một công việc ở trong hệ thống:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\) là số yêu cầu trung bình đang ở trong hệ thống.
- \(\lambda\) là thông lượng trung bình, tính bằng yêu cầu mỗi giây.
- \(W\) là thời gian trung bình một yêu cầu ở trong hệ thống, tính bằng giây.

Ví dụ, nếu hệ thống hoàn thành trung bình 200 yêu cầu/giây và mỗi yêu cầu mất trung bình 0,1 giây, số yêu cầu trung bình đang ở trong hệ thống là khoảng 20. Nếu thời gian tăng lên 0,5 giây trong khi thông lượng vẫn là 200 yêu cầu/giây, số yêu cầu trung bình sẽ tăng lên khoảng 100.

Công thức này không khẳng định nguyên nhân làm thời gian tăng. Nó cho thấy hàng đợi và thời gian phản hồi có quan hệ trực tiếp: khi công việc vào hệ thống nhanh hơn khả năng hoàn thành, số công việc chờ sẽ tăng.

Khi mức sử dụng một tài nguyên tiến gần giới hạn, thời gian chờ thường tăng nhanh hơn mức tăng tải. Chẳng hạn, một CPU có thể phục vụ tốt ở mức tải vừa phải, nhưng khi liên tục gần bão hòa, các truy vấn phải xếp hàng chờ được lập lịch. Tương tự, thiết bị lưu trữ có thể phản hồi nhanh ở hàng đợi ngắn nhưng tăng độ trễ đáng kể khi có quá nhiều yêu cầu I/O đồng thời.

Không nên dùng một ngưỡng sử dụng cố định để kết luận hệ thống có vấn đề. CPU 85% có thể bình thường đối với một tác vụ xử lý theo lô, trong khi CPU 45% vẫn có thể đi kèm độ trễ cao nếu một lõi bị bão hòa, ứng dụng bị giới hạn CPU hoặc phần lớn thời gian đang chờ khóa.

### 1.4. Nút thắt cổ chai

Nút thắt cổ chai là tài nguyên hoặc cơ chế giới hạn tốc độ hoàn thành của toàn bộ đường xử lý. Tăng năng lực ở thành phần không bị giới hạn thường không giúp tăng thông lượng.

Ví dụ:

- Nếu truy vấn phải chờ đĩa đọc dữ liệu, bổ sung CPU có thể không rút ngắn thời gian chờ đó.
- Nếu nhiều giao dịch cùng chờ một khóa trên một dòng, tăng IOPS không giải quyết được tranh chấp khóa.
- Nếu DBMS trả về quá nhiều dữ liệu qua một kết nối mạng chậm, tăng bộ nhớ máy chủ có thể không cải thiện thời gian người dùng nhận kết quả.
- Nếu ứng dụng mở quá nhiều kết nối, tăng số kết nối thêm có thể làm DBMS tốn bộ nhớ và chi phí lập lịch hơn.

Nút thắt có thể thay đổi sau khi tối ưu. Khi giảm được thời gian đọc đĩa, CPU có thể trở thành giới hạn tiếp theo. Vì thế, cần đo lại toàn bộ đường xử lý sau mỗi thay đổi có ảnh hưởng đáng kể.

## 2. Đo tải trước khi kết luận

### 2.1. Xây dựng đường cơ sở

Trước khi điều chỉnh, hãy ghi nhận trạng thái hiện tại trong một khoảng thời gian đại diện. Một đường cơ sở hữu ích thường có:

- Lưu lượng yêu cầu và số giao dịch hoàn thành mỗi giây.
- Độ trễ p50, p95 và p99 của các thao tác quan trọng.
- Số lỗi, timeout, deadlock và yêu cầu bị từ chối.
- Mức sử dụng CPU, bộ nhớ, lưu trữ và mạng.
- Số kết nối đang hoạt động, số kết nối chờ và số giao dịch đang mở.
- Các loại wait event hoặc thời gian chờ phổ biến.
- Những câu truy vấn tiêu thụ nhiều tổng thời gian hoặc tài nguyên.

Các phân vị độ trễ cho biết trải nghiệm của nhiều nhóm yêu cầu:

- **p50:** một nửa số yêu cầu hoàn thành nhanh hơn hoặc bằng giá trị này.
- **p95:** 95% số yêu cầu hoàn thành nhanh hơn hoặc bằng giá trị này; 5% còn lại chậm hơn.
- **p99:** thể hiện phần đuôi chậm nhất của phân bố và giúp phát hiện những yêu cầu hiếm nhưng gây ảnh hưởng lớn.

Không nên chỉ xem thời gian trung bình. Một số ít truy vấn chậm có thể bị che khuất trong số trung bình nhưng vẫn làm p99 tăng mạnh.

### 2.2. Tải thử nghiệm phải giống tải thật

Một bài kiểm tra chỉ có một kết nối chạy lặp lại một truy vấn không thể đại diện cho mọi hệ thống. Cần xem xét:

- Tỷ lệ đọc và ghi.
- Kích thước dữ liệu và mức độ dữ liệu còn nằm trong cache.
- Phân bố khóa truy cập: đều hay tập trung vào một vài bản ghi nóng.
- Kích thước giao dịch và số câu SQL trong mỗi giao dịch.
- Số kết nối đồng thời và cách ứng dụng tạo tải theo đợt.
- Tỷ lệ truy vấn ngắn, truy vấn dài và tác vụ nền.
- Các thời điểm checkpoint, sao lưu, đồng bộ hoặc chạy báo cáo.

Kiểm tra với dữ liệu quá nhỏ có thể khiến toàn bộ dữ liệu nằm trong bộ nhớ, trong khi môi trường thật thường xuyên phải đọc lưu trữ. Kiểm tra chỉ đọc cũng không phản ánh chi phí WAL, ghi dữ liệu, khóa và checkpoint của tải có nhiều thao tác ghi.

Nên thử tăng tải theo từng mức, giữ tải đủ lâu để quan sát trạng thái ổn định, sau đó thử tải đỉnh hoặc tải kéo dài nếu phù hợp. Ghi rõ cấu hình máy, phiên bản DBMS, kích thước dữ liệu và cách tạo tải để có thể lặp lại phép đo.

### 2.3. Quan sát đồng thời ở nhiều lớp

Không có một bảng điều khiển duy nhất cho biết chính xác nút thắt. Hãy ghép dữ liệu từ:

- **Ứng dụng:** thời gian lấy kết nối, thời gian gọi DBMS, thời gian đọc kết quả, timeout.
- **DBMS:** thống kê câu lệnh, kế hoạch thực thi, wait event, khóa, cache và hoạt động nền.
- **Hệ điều hành hoặc nền tảng:** CPU, RAM, swap, I/O, hàng đợi thiết bị, lưu lượng mạng.
- **Hạ tầng:** giới hạn CPU/RAM của container, thông số ổ đĩa mạng, giới hạn IOPS/băng thông và hiện tượng throttling.

Đồng bộ đồng hồ giữa các lớp nếu có thể. Khi đối chiếu một đợt tăng độ trễ ở ứng dụng với số liệu DBMS, thời điểm không khớp có thể dẫn đến kết luận sai.

## 3. CPU: năng lực tính toán và lập lịch

### 3.1. CPU được dùng vào việc gì?

CPU xử lý nhiều bước trong vòng đời truy vấn:

- Phân tích cú pháp và kiểm tra câu lệnh.
- Lập kế hoạch thực thi và chọn đường truy cập dữ liệu.
- So sánh, lọc và biến đổi giá trị.
- Thực hiện phép nối, sắp xếp, nhóm và tổng hợp.
- Kiểm tra ràng buộc, tính toán biểu thức và thực hiện một phần công việc ghi.
- Mã hóa, nén, giải nén và xử lý giao thức.

Một truy vấn đọc ít dữ liệu vẫn có thể tiêu thụ nhiều CPU nếu phải thực hiện biểu thức phức tạp trên nhiều dòng, nối các tập dữ liệu lớn hoặc sắp xếp một lượng kết quả lớn. Ngược lại, truy vấn đơn giản có thể dùng rất ít CPU nhưng chờ lưu trữ hoặc khóa trong phần lớn thời gian.

### 3.2. Dấu hiệu của nút thắt CPU

Các dấu hiệu nên được xem xét cùng nhau:

- CPU của máy hoặc tiến trình DBMS cao trong thời gian độ trễ tăng.
- Hàng đợi tiến trình chờ CPU hoặc số tiến trình runnable tăng.
- Một số truy vấn có tổng thời gian CPU cao hoặc thực hiện lượng công việc lớn.
- CPU cao nhưng thời gian chờ I/O và khóa không giải thích được độ trễ.
- Một lõi bị sử dụng tối đa trong khi tổng CPU toàn máy chưa cao, có thể do giới hạn song song hoặc một luồng xử lý đơn.

Cần phân biệt CPU bận do DBMS với CPU bận do ứng dụng, tác vụ nền hoặc tiến trình khác trên cùng máy. Trong môi trường container, CPU quota có thể khiến tiến trình bị throttling dù biểu đồ CPU của máy chủ chưa đạt 100%. Trên máy ảo, CPU steal hoặc giới hạn của máy chủ vật lý cũng có thể ảnh hưởng.

### 3.3. Hướng xử lý

Khi có bằng chứng truy vấn bị giới hạn bởi CPU, hãy tìm phần công việc có thể loại bỏ hoặc giảm:

1. Đọc và xử lý ít dòng hơn bằng điều kiện lọc phù hợp.
2. Chọn đúng cột cần dùng thay vì lấy toàn bộ cột.
3. Xem kế hoạch thực thi để phát hiện phép nối, sắp xếp hoặc quét dữ liệu tốn kém.
4. Tránh tính cùng một biểu thức nhiều lần nếu có cách tính một lần và tái sử dụng.
5. Xem xét chỉ mục khi nó giúp giảm đáng kể lượng dữ liệu phải đọc hoặc xử lý; chỉ mục cũng làm tăng chi phí ghi và dung lượng lưu trữ.
6. Dùng xử lý theo lô khi việc gửi nhiều câu lệnh nhỏ tạo chi phí lặp lại lớn, nhưng giữ kích thước lô trong giới hạn bộ nhớ và thời gian khóa hợp lý.
7. Cân nhắc truy vấn song song cho tác vụ phù hợp sau khi đo, vì song song có thể tăng tranh chấp CPU và I/O khi nhiều truy vấn cùng chạy.

Không nên mặc định tăng số lõi hoặc bật mức song song cao nhất. Nếu truy vấn đã chờ I/O hoặc khóa, tăng CPU không giải quyết nguyên nhân. Nếu toàn hệ thống đã bão hòa CPU, tăng song song cho từng truy vấn có thể làm nhiều yêu cầu khác chậm hơn.

## 4. Bộ nhớ: cache, dữ liệu trung gian và áp lực cấp phát

### 4.1. Các vùng sử dụng bộ nhớ

DBMS và hệ điều hành dùng bộ nhớ cho nhiều mục đích:

- **Bộ đệm dữ liệu:** giữ các trang dữ liệu và chỉ mục được truy cập gần đây để giảm số lần đọc từ lưu trữ.
- **Bộ nhớ dùng chung:** chứa cấu trúc nội bộ và vùng dữ liệu mà nhiều tiến trình hoặc luồng có thể truy cập.
- **Bộ nhớ riêng của truy vấn:** phục vụ sort, hash join, hash aggregate và các thao tác trung gian.
- **Bộ nhớ phiên/kết nối:** lưu trạng thái phiên, transaction, cursor, buffer giao thức và dữ liệu liên quan.
- **Bộ nhớ của hệ điều hành:** cache trang tệp, thư viện, tiến trình và các dịch vụ khác.

Tên và cách phân bổ các vùng này khác nhau giữa PostgreSQL, MySQL, SQL Server và các DBMS khác. Khi điều chỉnh cấu hình, phải tra đúng tài liệu cho phiên bản đang vận hành.

### 4.2. Cache giúp giảm I/O như thế nào?

Khi một trang dữ liệu được yêu cầu, DBMS có thể tìm thấy trang trong bộ đệm hoặc phải đọc trang từ lưu trữ. Cache hiệu quả giúp giảm độ trễ đọc và tải I/O. Tuy nhiên, tỷ lệ cache hit cao không tự động chứng minh hệ thống khỏe mạnh:

- Một truy vấn có thể đọc lặp lại một tập dữ liệu nhỏ nên hit rate cao, nhưng vẫn tiêu thụ CPU lớn.
- Một truy vấn báo cáo lần đầu đọc tập dữ liệu lớn nên có nhiều cache miss dù hoạt động bình thường.
- Chỉ số hit có thể không phản ánh đầy đủ lượng dữ liệu đọc, kích thước trang hoặc chi phí truy cập.
- Bộ đệm có thể chứa dữ liệu không còn hữu ích trong khi working set của tải hiện tại liên tục bị đẩy ra.

Cần so sánh hit/miss, lượng dữ liệu đọc thực tế, độ trễ lưu trữ và thời gian truy vấn trong cùng khoảng đo. Hãy xác định working set — tập dữ liệu thường xuyên được tải công việc truy cập — và xem bộ nhớ có đủ giữ phần quan trọng của tập đó hay không.

### 4.3. Dấu hiệu áp lực bộ nhớ

Một số dấu hiệu thường gặp:

- Hệ điều hành bắt đầu dùng swap hoặc có hoạt động phân trang đáng kể.
- Số page fault hoặc lần đọc trang tăng cùng với độ trễ.
- Bộ nhớ cache bị đẩy ra liên tục và dữ liệu phải đọc lại từ lưu trữ.
- Sort hoặc hash operation tràn ra tệp tạm.
- DBMS ghi nhận lỗi cấp phát bộ nhớ hoặc tiến trình bị hệ điều hành kết thúc.
- Bộ nhớ tăng theo số kết nối hoặc theo số truy vấn đồng thời.

Một truy vấn có thể chạy nhanh khi chỉ có một phiên, nhưng khi nhiều truy vấn cùng thực hiện sort hoặc hash join, nhu cầu bộ nhớ cộng dồn có thể vượt quá khả năng máy. Đây là lý do cần đo ở mức tải đồng thời đại diện.

### 4.4. Điều chỉnh bộ nhớ có kiểm soát

Các hướng thường xem xét:

- Giảm lượng dữ liệu trung gian bằng cách lọc sớm và tránh nối những tập dữ liệu không cần thiết.
- Kiểm tra truy vấn có tạo sort/hash lớn hoặc ghi tệp tạm hay không.
- Điều chỉnh cache của DBMS dựa trên dung lượng RAM thực tế, yêu cầu của hệ điều hành và các tiến trình khác.
- Giới hạn số truy vấn nặng chạy đồng thời nếu chúng cạnh tranh cùng một vùng bộ nhớ.
- Quản lý pool kết nối để tránh tạo quá nhiều phiên không cần thiết.
- Xem xét kích thước lô và cấu trúc truy vấn để tránh giữ quá nhiều dữ liệu trong một giao dịch.

Ví dụ, PostgreSQL có tham số **shared_buffers** cho vùng đệm dùng chung và **work_mem** cho một số thao tác sort/hash. **work_mem** có thể được sử dụng nhiều lần trong một truy vấn và bởi nhiều truy vấn đồng thời; nó không phải một khoản ngân sách duy nhất cho toàn máy. Vì thế, tăng giá trị này mà không tính số thao tác và số phiên đồng thời có thể làm tổng nhu cầu RAM vượt giới hạn.

Không nên giải quyết áp lực bộ nhớ bằng cách tắt cơ chế an toàn, vô hiệu hóa kiểm tra hoặc đặt mọi vùng nhớ ở mức tối đa. Trước tiên cần xác định vùng nào tăng, tác nhân nào sử dụng và mức đồng thời nào gây ra đỉnh tiêu thụ.

## 5. Lưu trữ: độ trễ đọc/ghi, IOPS và thông lượng

### 5.1. Ba đặc tính cần phân biệt

Hiệu năng lưu trữ không chỉ là dung lượng ổ đĩa. Ba đặc tính thường cần theo dõi là:

- **Độ trễ I/O:** thời gian hoàn thành một yêu cầu đọc hoặc ghi.
- **IOPS:** số thao tác vào/ra có thể hoàn thành mỗi giây.
- **Thông lượng:** lượng dữ liệu đọc hoặc ghi trong một giây, thường tính bằng MB/s hoặc GB/s.

Một thiết bị có thông lượng tuần tự cao chưa chắc xử lý tốt nhiều yêu cầu đọc ngẫu nhiên nhỏ. Một ổ đĩa có IOPS cao nhưng độ trễ tăng mạnh khi hàng đợi quá dài cũng có thể làm truy vấn chậm.

Kiểu tải rất quan trọng. Quét tuần tự một tệp lớn thường cần thông lượng. Truy cập nhiều trang rời rạc có thể bị giới hạn bởi IOPS và độ trễ từng lần đọc. Ghi giao dịch có thể cần chờ dữ liệu log được xác nhận bền vững.

### 5.2. Những hoạt động lưu trữ của DBMS

Cơ sở dữ liệu thường đọc và ghi nhiều loại dữ liệu:

- Trang dữ liệu và trang chỉ mục.
- Log giao dịch như WAL hoặc redo log.
- Dữ liệu tạm cho sort, hash hoặc thao tác trung gian.
- Tệp phục vụ checkpoint, sao lưu và phục hồi.
- Dữ liệu của hệ thống giám sát hoặc tác vụ nền.

Với hệ thống yêu cầu độ bền, một giao dịch có thể chỉ được xác nhận sau khi log cần thiết đã được ghi bền vững. Điều này giúp bảo vệ dữ liệu khi sự cố xảy ra nhưng cũng khiến độ trễ lưu trữ của đường ghi có ảnh hưởng trực tiếp đến thời gian commit.

Checkpoint và tác vụ nền có thể tạo tải ghi đáng kể. Khi chúng trùng với giờ cao điểm, độ trễ I/O có thể tăng dù lưu lượng ứng dụng không thay đổi.

### 5.3. Dấu hiệu nút thắt lưu trữ

Hãy tìm sự kết hợp của các tín hiệu:

- Độ trễ đọc hoặc ghi tăng đúng thời điểm truy vấn chậm.
- Hàng đợi I/O hoặc độ sâu hàng đợi thiết bị tăng.
- CPU không bận tương ứng, trong khi tiến trình DBMS chờ I/O.
- Số trang phải đọc từ thiết bị tăng hoặc dữ liệu tạm được ghi nhiều.
- Các wait event liên quan đến đọc trang, ghi log hoặc đồng bộ tăng.
- Độ trễ commit tăng dù phần tính toán của câu lệnh không lớn.

Không nên chỉ nhìn mức sử dụng ổ đĩa theo phần trăm. Một thiết bị báo mức bận cao chưa chắc đã bão hòa nếu độ trễ vẫn thấp và hàng đợi được xử lý tốt; ngược lại, một volume có giới hạn IOPS thấp có thể gặp độ trễ cao dù biểu đồ thông lượng chưa đạt mức tối đa.

Trong môi trường cloud, cần kiểm tra giới hạn của volume, IOPS được cấp, thông lượng tối đa, cơ chế burst và giới hạn của máy ảo. Chỉ số ở máy khách có thể khác với chỉ số của thiết bị lưu trữ nền tảng.

### 5.4. Hướng giảm áp lực I/O

- Giảm số trang cần đọc bằng cách cải thiện điều kiện lọc, kế hoạch thực thi và chỉ mục phù hợp.
- Tránh đọc cột hoặc dòng không cần thiết.
- Tận dụng cache khi working set và chính sách truy cập cho phép.
- Giảm ghi dư thừa, cập nhật lặp hoặc ghi cùng dữ liệu nhiều lần.
- Dùng batch hợp lý để giảm chi phí thao tác nhỏ lặp lại, đồng thời tránh tạo giao dịch quá lớn.
- Kiểm tra tác động của chỉ mục: chỉ mục giúp đọc nhanh hơn trong một số trường hợp nhưng làm tăng dung lượng và chi phí cập nhật khi ghi.
- Xem lại lịch chạy checkpoint, sao lưu và tác vụ nền theo khả năng cấu hình của DBMS.
- Nâng cấp hoặc thay đổi lớp lưu trữ khi số liệu chứng minh giới hạn nằm ở năng lực thiết bị.

Không tắt đồng bộ bền vững hoặc cơ chế bảo vệ log chỉ để làm phép đo nhanh hơn trong môi trường thật. Thay đổi như vậy có thể làm mất dữ liệu đã được xác nhận khi xảy ra sự cố.

## 6. Mạng: thời gian truyền và lượng dữ liệu trao đổi

### 6.1. Mạng ảnh hưởng đến truy vấn ra sao?

Ứng dụng và DBMS thường chạy ở hai tiến trình hoặc hai máy khác nhau. Một yêu cầu có thể phải đi qua nhiều lượt trao đổi: mở kết nối, gửi câu lệnh, nhận metadata, lấy từng phần kết quả và gửi lệnh commit. Khi độ trễ mạng giữa hai đầu cao, các lượt trao đổi nhỏ lặp lại có thể cộng dồn thành thời gian đáng kể.

Băng thông cũng quan trọng. Một câu truy vấn trả về hàng trăm nghìn dòng có thể hoàn tất phần thực thi ở máy chủ tương đối nhanh nhưng mất nhiều thời gian để truyền toàn bộ kết quả về ứng dụng. Phía ứng dụng còn phải giải mã, chuyển kiểu và xử lý dữ liệu đó.

Các yếu tố cần xem xét:

- RTT (round-trip time) giữa ứng dụng và DBMS.
- Băng thông khả dụng và mức sử dụng đường truyền.
- Mất gói, retransmission và biến động độ trễ.
- Kích thước dữ liệu gửi/nhận.
- Số lượt trao đổi cần thiết cho một thao tác nghiệp vụ.
- Chi phí TLS, nén, serialization và giải mã.
- Vị trí địa lý hoặc số lớp proxy trung gian.

### 6.2. Dấu hiệu nút thắt mạng

- Thời gian ứng dụng chờ kết quả lớn hơn đáng kể thời gian DBMS thực thi.
- Truy vấn trả về nhiều dữ liệu và thời gian hoàn thành tăng theo kích thước kết quả.
- RTT tăng, mất gói hoặc retransmission xuất hiện cùng thời điểm.
- Băng thông gần giới hạn hoặc có hàng đợi trên đường truyền.
- Ứng dụng gửi nhiều câu lệnh nhỏ liên tiếp dù chúng có thể được gom hợp lý.

Hãy đo riêng thời gian lấy kết nối, gửi câu lệnh, thực thi ở DBMS và đọc hết kết quả. Nếu chỉ dùng một số đo tổng, rất khó phân biệt DBMS chậm với mạng hoặc ứng dụng chậm.

### 6.3. Hướng cải thiện

- Chỉ truy vấn những cột và dòng cần thiết.
- Dùng phân trang hoặc streaming phù hợp khi kết quả lớn.
- Gom các thao tác nhỏ thành batch khi điều đó không làm thay đổi ngữ nghĩa giao dịch.
- Tránh thiết kế ứng dụng tạo quá nhiều lượt gọi DBMS nối tiếp.
- Dùng connection pool có giới hạn hợp lý để giảm chi phí mở kết nối và tránh tạo tải không kiểm soát.
- Đặt ứng dụng và DBMS ở vị trí mạng phù hợp với yêu cầu độ trễ và quy định dữ liệu.
- Chỉ bật nén khi lợi ích giảm lượng truyền lớn hơn chi phí CPU và độ trễ nén/giải nén.

Connection pool giúp tái sử dụng kết nối, nhưng không làm cho mọi truy vấn nhanh hơn. Nếu pool quá lớn, nó có thể đẩy DBMS vào tình trạng quá nhiều phiên đồng thời. Nếu pool quá nhỏ, yêu cầu có thể phải chờ lấy kết nối dù DBMS còn khả năng xử lý. Cần đo thời gian chờ pool và số phiên hoạt động để chọn giới hạn.

## 7. Xử lý đồng thời: khóa, giao dịch và tranh chấp

### 7.1. Nhiều phiên không đồng nghĩa với nhiều công việc hữu ích

DBMS hỗ trợ nhiều phiên cùng truy cập dữ liệu, nhưng các phiên có thể tranh chấp tài nguyên dùng chung. Chúng có thể phải chờ:

- Khóa dòng, khóa bảng hoặc khóa đối tượng khác.
- Chốt nội bộ bảo vệ cấu trúc dữ liệu trong DBMS.
- Kết nối trong pool hoặc lượt chạy của CPU.
- Tài nguyên I/O, bộ nhớ hoặc log.
- Giao dịch khác hoàn thành để bảo đảm tính nhất quán.

Tăng số kết nối có thể làm tăng mức đồng thời, nhưng thông lượng chỉ tăng nếu hệ thống còn tài nguyên và các giao dịch có thể tiến triển độc lập. Khi nhiều giao dịch cùng cập nhật một dòng nóng, số phiên tăng chủ yếu làm hàng đợi khóa dài hơn.

### 7.2. Khóa và deadlock

Khóa giúp bảo vệ tính nhất quán khi nhiều giao dịch đọc hoặc thay đổi cùng dữ liệu. Một giao dịch có thể phải chờ khóa do giao dịch khác đang giữ khóa xung đột.

Ví dụ, hai giao dịch cùng cập nhật số lượng của một sản phẩm:

~~~sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42;

COMMIT;
~~~

Nếu nhiều giao dịch đồng thời cập nhật dòng có product_id bằng 42, chúng có thể phải chờ nhau để lấy khóa trên dòng đó. Tăng CPU hoặc IOPS không loại bỏ được hàng đợi khóa này.

Deadlock xảy ra khi các giao dịch tạo thành vòng chờ. Ví dụ:

1. Giao dịch A giữ khóa dòng X và chờ dòng Y.
2. Giao dịch B giữ khóa dòng Y và chờ dòng X.
3. Không giao dịch nào có thể tiếp tục nếu không có cơ chế phát hiện và phá vòng chờ.

DBMS thường phát hiện deadlock và hủy một giao dịch để giải phóng hệ thống. Ứng dụng cần có chiến lược xử lý lỗi và thử lại có giới hạn. Thử lại vô hạn hoặc đồng loạt ngay lập tức có thể tạo thêm tải và lặp lại tranh chấp.

### 7.3. Giao dịch dài và vùng tranh chấp nóng

Giao dịch càng dài thì càng có thể giữ khóa hoặc trạng thái phiên lâu. Các nguyên nhân thường gặp:

- Gọi dịch vụ bên ngoài trong khi vẫn đang mở transaction.
- Chờ người dùng nhập dữ liệu trước khi commit.
- Xử lý một lô quá lớn trong một transaction.
- Thực hiện truy vấn không cần thiết sau khi đã lấy khóa.
- Không đóng transaction khi xảy ra lỗi ở ứng dụng.

Một vài dòng dữ liệu được truy cập thường xuyên có thể trở thành điểm nóng. Ví dụ, mọi yêu cầu đặt hàng đều cập nhật một dòng tổng tồn kho hoặc một bộ đếm dùng chung. Khi đó, thiết kế thao tác và phạm vi dữ liệu quan trọng hơn việc chỉ tăng phần cứng.

Hướng xử lý có thể gồm:

- Giữ transaction ngắn và chỉ bao gồm các thao tác cần tính nguyên tử.
- Không chờ mạng hoặc người dùng trong lúc giữ khóa.
- Truy cập các đối tượng theo thứ tự nhất quán để giảm nguy cơ deadlock.
- Thiết kế lại điểm ghi nóng nếu nghiệp vụ cho phép, chẳng hạn phân tán bộ đếm hoặc gom cập nhật.
- Chọn mức cô lập phù hợp với yêu cầu nhất quán, sau khi hiểu rõ hành vi đọc/ghi và khả năng phát sinh xung đột.
- Xử lý lỗi deadlock và serialization failure bằng retry có giới hạn, có backoff và bảo đảm thao tác có thể lặp an toàn.

Không hạ mức cô lập chỉ để giảm chờ nếu chưa đánh giá tác động đến tính đúng đắn của nghiệp vụ. Mục tiêu là giảm tranh chấp trong khi vẫn giữ các bảo đảm dữ liệu mà hệ thống yêu cầu.

### 7.4. Số kết nối và giới hạn đồng thời

Mỗi kết nối thường có chi phí bộ nhớ, trạng thái và lập lịch. Số lượng kết nối lớn có thể:

- Làm tăng bộ nhớ nền.
- Tăng chi phí chuyển ngữ cảnh và quản lý phiên.
- Tạo nhiều truy vấn tranh chấp CPU, cache và I/O.
- Làm tăng số transaction đồng thời và khả năng chờ khóa.
- Khiến p95/p99 xấu đi dù thông lượng không tăng.

Hãy xác định mức đồng thời mà DBMS xử lý hiệu quả qua thử nghiệm tải. Connection pool nên có giới hạn dựa trên khả năng DBMS, cấu trúc truy vấn và nhu cầu của các tác vụ nền. Có thể cần hàng đợi ở ứng dụng để điều tiết tải thay vì chuyển mọi yêu cầu đến DBMS cùng lúc.

## 8. Nhận diện nút thắt từ triệu chứng

Một chỉ số riêng lẻ hiếm khi đủ để kết luận. Bảng dưới đây là điểm bắt đầu để hình thành giả thuyết và chọn phép đo tiếp theo.

| Triệu chứng quan sát | Giả thuyết cần kiểm tra | Bằng chứng tiếp theo |
|---|---|---|
| CPU cao kéo dài, truy vấn chậm, I/O wait thấp | Công việc tính toán hoặc xử lý dữ liệu quá lớn | CPU theo tiến trình/lõi, truy vấn tốn CPU, kế hoạch thực thi |
| CPU thấp nhưng truy vấn chậm, độ trễ đọc cao | Chờ lưu trữ | I/O latency, queue depth, số trang đọc, wait event |
| RAM gần đầy, swap hoặc tệp tạm tăng | Áp lực bộ nhớ hoặc quá nhiều thao tác trung gian | RSS, swap, page fault, sort/hash spill, số truy vấn đồng thời |
| DBMS thực thi nhanh nhưng ứng dụng nhận kết quả chậm | Mạng, lượng dữ liệu trả về hoặc xử lý phía ứng dụng | RTT, byte truyền, thời gian đọc hết kết quả, thời gian giải mã |
| Nhiều phiên chờ khóa, deadlock tăng | Tranh chấp giao dịch hoặc điểm nóng | Phiên giữ khóa, câu lệnh liên quan, thời gian transaction |
| Pool hết kết nối nhưng DBMS chưa bão hòa | Pool quá nhỏ, transaction giữ kết nối lâu hoặc rò rỉ kết nối | Pool wait, thời gian mượn/trả kết nối, transaction mở |
| Tăng kết nối nhưng thông lượng không tăng, p99 xấu đi | Quá tải đồng thời hoặc hàng đợi tăng | Throughput theo mức đồng thời, CPU, I/O, lock wait |
| Commit chậm trong khi phần truy vấn ngắn | Chờ ghi log bền vững hoặc lưu trữ | Commit latency, WAL/redo log, fsync và I/O ghi |

### 8.1. Một trình tự chẩn đoán thực tế

Giả sử p95 của một API tăng từ 80 ms lên 450 ms sau khi lưu lượng tăng gấp đôi. Thay vì kết luận ngay rằng máy chủ thiếu CPU, hãy kiểm tra theo trình tự:

1. Xác nhận số yêu cầu, loại truy vấn và kích thước dữ liệu có thay đổi hay không.
2. So sánh thời gian chờ lấy kết nối với thời gian gọi DBMS.
3. Kiểm tra DBMS dành phần lớn thời gian cho CPU, I/O hay chờ khóa.
4. Đối chiếu độ trễ lưu trữ, mức dùng RAM, swap và mạng trong cùng khoảng thời gian.
5. Xác định nhóm truy vấn hoặc giao dịch đóng góp nhiều nhất vào tổng thời gian.
6. Tạo một giả thuyết có thể kiểm chứng, ví dụ: “các truy vấn đọc đang chờ I/O do working set vượt bộ đệm”.
7. Thử một thay đổi có phạm vi hẹp và đo lại dưới tải tương đương.

Nếu CPU chỉ 35%, điều đó không loại trừ nút thắt CPU: một lõi có thể bão hòa hoặc container có thể bị throttling. Nếu I/O wait thấp, điều đó cũng không chứng minh lưu trữ không có vấn đề: cần xem wait event của DBMS, độ trễ thiết bị và cách nền tảng báo cáo số liệu. Hãy dùng nhiều nguồn đo để kiểm tra chéo.

### 8.2. Ví dụ quan sát trên PostgreSQL

Các ví dụ sau dùng PostgreSQL để minh họa cách kết hợp số liệu. Tên view, cột và khả năng quan sát có thể khác theo phiên bản; cần kiểm tra tài liệu đúng phiên bản và quyền truy cập trước khi chạy trên hệ thống thật.

Xem phân bố trạng thái và loại chờ của các phiên đang hoạt động:

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

Tìm các phiên đang chờ khóa:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY xact_start NULLS LAST;
~~~

Nếu extension **pg_stat_statements** đã được cài đặt và bật, có thể tìm các câu lệnh có tổng thời gian thực thi hoặc lượng dữ liệu tạm đáng kể:

~~~sql
SELECT
    calls,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    round(mean_exec_time::numeric, 2) AS mean_exec_ms,
    shared_blks_read,
    temp_blks_written,
    left(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Đọc kế hoạch của một câu truy vấn đại diện:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 50;
~~~

**EXPLAIN ANALYZE** thực sự thực thi câu lệnh. Chỉ chạy trên truy vấn và môi trường phù hợp; với câu lệnh ghi, cần hiểu tác động và cách transaction được quản lý. **BUFFERS** giúp xem hoạt động bộ đệm, nhưng không thay thế số đo ở hệ điều hành hoặc nền tảng lưu trữ.

Ở Linux, các tiện ích như **vmstat**, **iostat** và **sar** có thể bổ sung góc nhìn về bộ nhớ, CPU, thiết bị lưu trữ và mạng. Ví dụ:

~~~bash
vmstat 1
iostat -xz 1
sar -n DEV 1
~~~

Các lệnh này cần được chạy với quyền và công cụ đã được cài đặt phù hợp. Trên Windows hoặc nền tảng cloud, dùng công cụ giám sát tương đương. Điều quan trọng là lấy số liệu cùng khoảng thời gian với truy vấn chậm, không phải tên của một công cụ cụ thể.

## 9. Quy trình kiểm chứng một thay đổi hiệu năng

Một thay đổi chỉ có ý nghĩa khi kết quả được so sánh với đường cơ sở dưới điều kiện tương đương. Quy trình đề xuất:

1. **Nêu triệu chứng:** xác định thao tác nào chậm, phân vị nào tăng, xảy ra từ khi nào và dưới loại tải nào.
2. **Đặt giả thuyết:** chỉ rõ tài nguyên hoặc cơ chế nghi ngờ và số liệu nào sẽ xác nhận hoặc bác bỏ giả thuyết.
3. **Ghi đường cơ sở:** lưu cấu hình, dữ liệu, mức đồng thời, throughput, p50/p95/p99, lỗi và các chỉ số tài nguyên.
4. **Chọn thay đổi nhỏ:** thay một yếu tố có thể cô lập tác động, chẳng hạn điều kiện truy vấn, chỉ mục, kích thước pool hoặc lịch chạy tác vụ nền.
5. **Chạy lại cùng tải:** dùng cùng dữ liệu, phân bố truy cập và mức đồng thời; nếu điều kiện khác, phải ghi rõ.
6. **So sánh nhiều chiều:** thời gian truy vấn, throughput, p95/p99, CPU, RAM, I/O, mạng, khóa và lỗi.
7. **Kiểm tra tác dụng phụ:** một chỉ mục mới có thể làm tăng thời gian ghi; batch lớn có thể giữ khóa lâu; tăng bộ nhớ cho sort có thể làm nhiều phiên cùng lúc thiếu RAM.
8. **Giữ hoặc hoàn tác:** chỉ giữ thay đổi khi lợi ích được xác nhận và các yêu cầu đúng đắn, độ bền, ổn định vẫn được đáp ứng.

Ví dụ bảng ghi kết quả:

| Chỉ số | Trước điều chỉnh | Sau điều chỉnh | Nhận xét |
|---|---:|---:|---|
| Throughput | 180 giao dịch/giây | 225 giao dịch/giây | Tăng khoảng 25% |
| p50 | 42 ms | 35 ms | Cải thiện |
| p95 | 210 ms | 125 ms | Cải thiện rõ |
| p99 | 620 ms | 390 ms | Đuôi độ trễ vẫn cần theo dõi |
| CPU trung bình | 72% | 78% | Tăng do xử lý được nhiều việc hơn |
| I/O read latency | 14 ms | 8 ms | Giảm thời gian chờ đọc |
| Deadlock | 0 | 0 | Không phát sinh trong lần thử |

Các số trong bảng là ví dụ minh họa, không phải ngưỡng chuẩn cho mọi hệ thống. Kết quả tốt cần được đánh giá theo mục tiêu dịch vụ, biến động của tải và khoảng thời gian quan sát. Nếu throughput tăng nhưng p99 vượt mục tiêu hoặc lỗi tăng, thay đổi chưa chắc phù hợp.

### 9.1. Đánh giá năng lực và phần dự phòng

Một hệ thống không nên được vận hành liên tục sát giới hạn nếu tải có thể tăng đột biến hoặc có tác vụ nền. Cần xem xét:

- Tải trung bình, tải đỉnh và tốc độ tăng trưởng.
- Biến động theo giờ, ngày, mùa hoặc chiến dịch.
- Dung lượng còn lại khi chạy sao lưu, checkpoint, báo cáo và bảo trì.
- Năng lực còn lại khi một nút hoặc một vùng dịch vụ gặp sự cố.
- Giới hạn thực tế của CPU, RAM, IOPS, thông lượng và kết nối.
- Thời gian cần để mở rộng tài nguyên hoặc điều tiết tải.

Phần dự phòng cần dựa trên mô hình tải và mục tiêu dịch vụ. Một hệ thống xử lý giao dịch có đỉnh tải bất ngờ cần cách điều tiết và mở rộng khác với hệ thống phân tích chạy theo lịch. Đừng chỉ lấy mức sử dụng trung bình để quyết định năng lực cần thiết.

## 10. Tình huống tổng hợp

Một hệ thống bán hàng có endpoint xác nhận đơn. Khi có chương trình khuyến mãi, số yêu cầu tăng mạnh và p99 tăng từ 300 ms lên hơn 2 giây. Đội vận hành đề xuất tăng CPU và tăng giới hạn kết nối.

Trước khi thay đổi, nhóm kỹ thuật đo được:

- CPU toàn máy dao động quanh 50%, không có dấu hiệu throttling rõ ràng.
- Độ trễ đọc lưu trữ ổn định.
- Số phiên đang chờ khóa tăng nhanh.
- Nhiều transaction cùng cập nhật một dòng tồn kho của sản phẩm bán chạy.
- Một số transaction giữ khóa lâu do ứng dụng thực hiện thêm bước gọi dịch vụ bên ngoài trước khi commit.

Các số liệu này ủng hộ giả thuyết tranh chấp khóa và transaction dài. Tăng CPU hoặc số kết nối không giải quyết được điểm nóng; thậm chí nhiều phiên hơn có thể làm hàng đợi dài hơn.

Nhóm có thể thử theo thứ tự:

1. Chuyển lời gọi dịch vụ bên ngoài ra ngoài khoảng thời gian giữ transaction, sau khi thiết kế lại luồng nghiệp vụ để vẫn bảo đảm tính nhất quán.
2. Rút ngắn transaction và chỉ giữ các câu lệnh cần thiết trong phạm vi nguyên tử.
3. Xem xét cách cập nhật tồn kho để giảm tập trung vào một dòng nóng, nếu mô hình dữ liệu và quy tắc tồn kho cho phép.
4. Bổ sung xử lý retry có giới hạn cho lỗi xung đột hoặc deadlock, kèm backoff và bảo đảm tính lặp an toàn.
5. Chạy lại bài kiểm tra với cùng phân bố sản phẩm nóng, mức đồng thời và thời lượng tải.

Sau thay đổi, nhóm phải kiểm tra cả p99, throughput, số lần chờ khóa, deadlock và tính đúng của tồn kho. Nếu p99 giảm nhưng có thể đặt hàng vượt tồn, đó không phải một tối ưu hợp lệ. Tình huống này cho thấy cần hiểu cơ chế truy cập dữ liệu và giao dịch trước khi quyết định tăng phần cứng.

## 11. Những ngộ nhận thường gặp

**“CPU chưa đạt 100% nên CPU không thể là nút thắt.”**  
Một lõi, một luồng hoặc quota của container có thể đã chạm giới hạn. Cần xem theo lõi, tiến trình, hàng đợi chạy và throttling.

**“Cache hit cao nghĩa là truy vấn nhanh.”**  
Hit rate không cho biết đầy đủ chi phí CPU, lượng dữ liệu xử lý, thời gian khóa hoặc số lần truy cập. Phải xem thêm thời gian, lượng đọc và wait event.

**“Ổ đĩa còn dung lượng nên không thể nghẽn.”**  
Dung lượng và hiệu năng là hai thuộc tính khác nhau. IOPS, thông lượng, độ trễ và hàng đợi mới phản ánh khả năng phục vụ I/O.

**“Càng nhiều kết nối thì throughput càng cao.”**  
Kết nối nhiều làm tăng mức đồng thời và chi phí quản lý. Khi tài nguyên hoặc khóa đã bão hòa, thêm kết nối chỉ tăng hàng đợi.

**“Truy vấn nhanh ở máy phát triển thì sẽ nhanh ở môi trường thật.”**  
Dữ liệu, cache, số phiên, độ trễ mạng, cấu hình lưu trữ và tải nền có thể rất khác nhau.

**“Chỉ cần tối ưu câu SQL là đủ.”**  
Độ trễ người dùng còn có thể đến từ pool kết nối, khóa, lưu trữ, mạng hoặc xử lý phía ứng dụng. Cần đo cả đường đi.

**“Tăng cấu hình bộ nhớ luôn cải thiện hiệu năng.”**  
Bộ nhớ được cấp cho nhiều phiên và nhiều thao tác có thể cộng dồn. Cấp phát quá mức có thể gây swap hoặc OOM, làm hệ thống chậm hơn.

## 12. Kết luận

CPU, bộ nhớ, lưu trữ, mạng và xử lý đồng thời là những phần liên kết trong cùng một đường xử lý cơ sở dữ liệu. Một truy vấn chậm có thể do tính toán, đọc/ghi, truyền dữ liệu hoặc chờ giao dịch khác. Nút thắt thường chỉ rõ khi ta đặt số liệu của ứng dụng, DBMS và hạ tầng cạnh nhau trong cùng khoảng thời gian.

Cách làm có thể lặp lại là đo tải đại diện, ghi đường cơ sở, nêu giả thuyết cụ thể, kiểm tra bằng số liệu, thay đổi có kiểm soát rồi đo lại. Khi đã xác định đúng giới hạn, ta mới chọn được biện pháp phù hợp: cải thiện SQL hoặc chỉ mục, giảm dữ liệu trung gian, điều chỉnh bộ nhớ, giảm I/O, tối ưu luồng mạng, rút ngắn transaction hay điều tiết mức đồng thời.

## Câu hỏi tự kiểm tra

1. Vì sao thông lượng có thể giữ nguyên trong khi p95 và p99 tăng mạnh?
2. Một máy có CPU tổng thể 40% nhưng truy vấn vẫn chậm. Bạn sẽ kiểm tra những dấu hiệu nào trước khi loại trừ CPU?
3. Phân biệt IOPS, thông lượng lưu trữ và độ trễ I/O. Mỗi chỉ số hữu ích trong trường hợp nào?
4. Vì sao tăng work_mem hoặc số kết nối mà không tính mức đồng thời có thể làm thiếu bộ nhớ?
5. Một nhóm truy vấn chờ khóa trong khi CPU và I/O còn thấp. Điều đó gợi ý vấn đề gì?
6. Ứng dụng đo thời gian API là 900 ms nhưng DBMS báo thời gian thực thi truy vấn 100 ms. Những khoảng thời gian nào cần được kiểm tra?
7. Khi kiểm chứng một thay đổi hiệu năng, vì sao cần giữ nguyên dữ liệu, phân bố tải và mức đồng thời?
8. Hãy nêu một ví dụ trong đó chỉ mục giúp giảm thời gian đọc nhưng làm tăng chi phí ghi.

Có thể xem một tối ưu là được xác nhận khi phép đo lặp lại cho thấy mục tiêu độ trễ hoặc thông lượng được cải thiện, tải vẫn ổn định, lỗi không tăng và các bảo đảm về tính đúng đắn, nhất quán, độ bền dữ liệu vẫn được giữ nguyên.

