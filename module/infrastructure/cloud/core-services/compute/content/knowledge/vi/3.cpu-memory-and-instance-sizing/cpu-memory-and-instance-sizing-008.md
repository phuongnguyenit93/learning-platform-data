# Ước lượng cấu hình từ lưu lượng, thời gian xử lý và lượng dữ liệu

Khi chọn cấu hình máy chủ đám mây, số lượng người dùng đăng ký hoặc tổng số request trong một ngày chưa đủ để quyết định cần bao nhiêu vCPU và RAM. Một hệ thống nhận 100 request mỗi giây nhưng mỗi request chỉ dùng CPU trong vài mili giây có nhu cầu rất khác hệ thống xử lý ảnh hoặc mã hóa dữ liệu trong hàng trăm mili giây. Tương tự, hai ứng dụng có cùng lưu lượng có thể cần dung lượng lưu trữ khác nhau nhiều lần nếu kích thước dữ liệu và thời gian lưu giữ khác nhau.

Ta có thể ước lượng cấu hình ban đầu bằng cách kết hợp ba nhóm số liệu:

- **Lưu lượng:** số request đến trong một giây, mức tăng đột biến và tỷ lệ đọc/ghi.
- **Thời gian xử lý:** thời gian CPU thực sự tiêu thụ cho mỗi request, thời gian phản hồi và số request đang được xử lý đồng thời.
- **Lượng dữ liệu:** kích thước dữ liệu đi qua hệ thống, dữ liệu được ghi mỗi ngày và thời gian cần lưu giữ.

Các phép tính dưới đây giúp hình thành cấu hình khởi điểm. Kết quả cần được kiểm chứng bằng tải thử trên đúng ứng dụng, loại máy và cấu hình mạng dự kiến.

## 1. Thu thập số liệu của tải công việc

Trước khi tính tài nguyên, hãy mô tả tải công việc bằng các số liệu có đơn vị rõ ràng. Nên lấy số liệu từ log, hệ thống giám sát hoặc một bài kiểm thử có dữ liệu gần với môi trường thật.

| Số liệu | Ký hiệu hoặc cách đo | Dùng để ước lượng |
|---|---|---|
| Lưu lượng trung bình | Request/giây (RPS) trung bình trong khoảng đo | Nhu cầu vận hành thông thường |
| Lưu lượng đỉnh | RPS cao nhất hoặc đỉnh kéo dài trong một khoảng xác định | Năng lực cần có khi tải tăng |
| Hệ số đỉnh | RPS đỉnh chia cho RPS trung bình | Mức chênh lệch giữa tải đỉnh và tải thường |
| CPU cho mỗi request | Giây CPU/request, lấy từ profiling hoặc tải thử | Số vCPU cần thiết |
| Thời gian phản hồi | Thời gian trung bình, p95 và p99 | Độ trễ người dùng và mức đồng thời |
| Bộ nhớ nền | RAM của tiến trình khi tải thấp | Phần RAM cố định của ứng dụng |
| Bộ nhớ tăng thêm | RAM tăng theo request đang xử lý, cache hoặc phiên | Tổng RAM cần thiết |
| Kích thước dữ liệu | Byte/request hoặc byte/bản ghi | Băng thông và dung lượng lưu trữ |
| Tỷ lệ ghi và thời gian lưu | Bản ghi/giây, số ngày giữ dữ liệu | Dung lượng dữ liệu tích lũy |

Không nên chỉ dùng giá trị trung bình. Một hệ thống có lưu lượng trung bình thấp nhưng thường xuyên tăng gấp nhiều lần trong vài phút vẫn cần phương án đáp ứng các đợt tăng đó. Hãy ghi nhận cả tải theo giờ, ngày trong tuần, mùa cao điểm, các đợt chạy batch và chiến dịch kinh doanh.

Phân biệt **thời gian CPU** với **thời gian phản hồi**. Thời gian CPU là tổng thời gian các lõi xử lý thực thi công việc của request. Thời gian phản hồi còn bao gồm chờ mạng, cơ sở dữ liệu, khóa, hàng đợi và các dịch vụ phụ thuộc. Dùng thời gian phản hồi thay cho thời gian CPU trong công thức tính vCPU thường làm kết quả sai lệch, đặc biệt với ứng dụng I/O-bound.

## 2. Ước lượng số vCPU từ RPS và thời gian CPU

Một lõi CPU cung cấp xấp xỉ một giây năng lực xử lý trong mỗi giây. Nếu mỗi request tiêu thụ `C` giây CPU và hệ thống nhận `R` request mỗi giây, nhu cầu CPU trung bình là:

\[
\text{CPU cores cần dùng} = R \times C
\]

Máy chủ không nên chạy liên tục ở mức sử dụng CPU 100%. Cần dành khoảng trống cho dao động tải, tác vụ nền, garbage collection, tiến trình hệ điều hành và những thời điểm xử lý chậm hơn dự kiến. Nếu chọn mức sử dụng CPU mục tiêu là `U`, số vCPU cần cấp phát được ước lượng bằng:

\[
\text{vCPU cần cấp phát} = \frac{R_{peak} \times C}{U}
\]

Trong đó:

- `R_peak` là lưu lượng đỉnh cần phục vụ, tính bằng request/giây.
- `C` là thời gian CPU cho một request, tính bằng giây CPU/request.
- `U` là tỷ lệ sử dụng CPU mục tiêu, viết dưới dạng số thập phân. Ví dụ 65% tương ứng `0,65`.

**Ví dụ:** một API nhận trung bình 120 request/giây và có giờ cao điểm gấp đôi, tức 240 request/giây. Profiling cho thấy mỗi request tiêu thụ trung bình 25 ms CPU, tương đương 0,025 giây CPU. Với mục tiêu sử dụng CPU 65%:

\[
\frac{240 \times 0,025}{0,65} \approx 9,23\text{ vCPU}
\]

Ta có thể bắt đầu thử nghiệm với cấu hình khoảng 10 vCPU cho năng lực xử lý toàn tải đỉnh. Nếu triển khai hai replica và chia tải đều, mỗi replica cần khoảng 5 vCPU trong điều kiện cả hai đều hoạt động. Nếu yêu cầu hệ thống vẫn xử lý đủ tải đỉnh khi một replica gặp sự cố, mỗi replica còn lại phải có khả năng nhận toàn bộ 240 request/giây; khi đó cần tính khoảng 10 vCPU cho từng replica hoặc thiết kế cơ chế tự mở rộng đủ nhanh để đáp ứng yêu cầu khôi phục.

Mức sử dụng CPU mục tiêu 60–70% thường là điểm khởi đầu hợp lý cho dịch vụ có tải biến động, nhưng không phải quy tắc cố định. Một tác vụ batch có thể chấp nhận mức sử dụng cao hơn nếu không có yêu cầu độ trễ tương tác. Dịch vụ thời gian thực có thể cần nhiều khoảng trống hơn. Hãy kiểm tra CPU throttling, thời gian chờ CPU và độ trễ p95/p99 trong tải thử.

Nếu request có nhiều loại xử lý khác nhau, hãy tính theo từng nhóm thay vì dùng một giá trị trung bình chung. Ví dụ, request đọc cache, request truy vấn phức tạp và request tạo báo cáo có chi phí CPU rất khác nhau. Có thể tính tổng nhu cầu bằng cách cộng `R_i × C_i` của từng nhóm request.

## 3. Ước lượng mức đồng thời và RAM

Lưu lượng đến và thời gian phản hồi quyết định số request có mặt đồng thời trong hệ thống. Định luật Little cho quan hệ:

\[
L = \lambda \times W
\]

Trong đó `L` là số request trung bình đang ở trong hệ thống, `λ` là tốc độ request đến (request/giây), và `W` là thời gian trung bình một request ở trong hệ thống (giây). Ví dụ, nếu một replica nhận 120 request/giây và thời gian phản hồi trung bình là 180 ms, số request đồng thời trung bình xấp xỉ:

\[
120 \times 0,18 = 21,6\text{ request}
\]

Đây là số trung bình. Khi hệ thống có hàng đợi hoặc tải tăng đột ngột, số request đồng thời có thể cao hơn. Dùng số liệu ở tải đỉnh và kiểm tra thêm p95/p99 để đánh giá các thời điểm bất thường.

RAM cần thiết thường gồm nhiều phần:

\[
\begin{aligned}
\text{RAM cơ sở} ={}& \text{RAM tiến trình nền} \\
&+ \text{RAM cache và buffer} \\
&+ (\text{request đồng thời} \times \text{RAM tăng thêm/request}) \\
&+ \text{RAM sidecar và thành phần phụ trợ}
\end{aligned}
\]

Sau khi tính phần đang sử dụng, cộng thêm khoảng dự phòng cho biến động tải, garbage collection, bộ đệm và tăng trưởng. Phần RAM tăng thêm trên mỗi request phải được đo hoặc suy ra từ tải thử; không phải toàn bộ heap của ứng dụng đều được nhân với số request đồng thời.

**Tiếp tục ví dụ:** giả sử mỗi replica xử lý 120 request/giây, có 21,6 request đồng thời trung bình. Ứng dụng dùng 1,8 GB RAM nền, cache và buffer chiếm 1 GB, các thành phần phụ trợ chiếm 0,7 GB, và mỗi request đang hoạt động làm tăng khoảng 3 MB RAM. Khi đó:

\[
1,8 + 1,0 + 0,7 + (21,6 \times 0,003) \approx 3,565\text{ GB}
\]

Với 30% dự phòng, nhu cầu vào khoảng 4,63 GB. Có thể chọn mức RAM gần nhất lớn hơn, chẳng hạn 6 GB hoặc cấu hình tiêu chuẩn 8 GB tùy dòng máy của nhà cung cấp. Khi kiểm tra tình huống một replica phải nhận toàn bộ tải đỉnh, tính lại số request đồng thời và RAM theo 240 request/giây.

Với ứng dụng Java, cần phân biệt heap với RAM của toàn bộ tiến trình. Native memory, metaspace, thread stack, direct buffer, agent giám sát và bộ nhớ của hệ điều hành cũng tiêu thụ RAM. Không đặt giới hạn heap bằng toàn bộ RAM máy. Hãy theo dõi cả heap sau garbage collection, RSS, bộ nhớ native và dấu hiệu swap hoặc OOM.

## 4. Ước lượng băng thông mạng

Lưu lượng request và kích thước dữ liệu trao đổi quyết định băng thông cần thiết. Nếu tổng kích thước request và response trung bình là `B` byte, băng thông dữ liệu xấp xỉ:

\[
\text{Throughput (byte/s)} = R \times B
\]

Đổi sang bit/giây bằng cách nhân với 8. Cần tính riêng chiều vào và chiều ra nếu kích thước request và response chênh lệch đáng kể. Với hệ thống truyền file, stream hoặc trả về payload lớn, băng thông có thể trở thành giới hạn trước CPU.

Ví dụ, mỗi request trao đổi tổng cộng 24 KB dữ liệu và lưu lượng trung bình là 120 request/giây:

\[
120 \times 24\text{ KB} = 2,88\text{ MB/s} \approx 23\text{ Mbit/s}
\]

Ở mức đỉnh gấp đôi, nhu cầu dữ liệu vào/ra tổng hợp khoảng 46 Mbit/s. Khi chọn cấu hình mạng, cần cộng phần overhead của TCP/TLS, giao thức ứng dụng, retry, đồng bộ dữ liệu và lưu lượng quản trị. Đồng thời kiểm tra giới hạn băng thông của loại instance, giới hạn theo kích thước máy, số kết nối và giới hạn của load balancer hoặc dịch vụ mạng đi kèm.

Đừng quên lưu lượng giữa các thành phần. Một request có thể đi qua load balancer, ứng dụng, cache, cơ sở dữ liệu và dịch vụ lưu trữ. Nếu các thành phần ở nhiều vùng sẵn sàng hoặc vùng địa lý khác nhau, lưu lượng liên vùng còn ảnh hưởng đến độ trễ và chi phí truyền dữ liệu.

## 5. Ước lượng dung lượng lưu trữ từ lượng dữ liệu

Để ước lượng dung lượng, hãy bắt đầu từ **tốc độ ghi dữ liệu**, không phải tổng RPS nếu nhiều request chỉ đọc. Với `W` bản ghi được ghi mỗi giây, kích thước trung bình `S` byte/bản ghi và thời gian lưu `D` ngày:

\[
\text{Dung lượng thô} = W \times S \times 86.400 \times D
\]

Sau đó điều chỉnh theo các yếu tố thực tế:

- **Chỉ mục và metadata:** cơ sở dữ liệu thường cần thêm dung lượng cho index, journal, metadata và cấu trúc lưu trữ.
- **Nén:** dữ liệu nén được có thể giảm dung lượng, nhưng tỷ lệ nén phải đo trên dữ liệu thật.
- **Bản sao:** tính số bản sao nếu kiến trúc yêu cầu tự quản lý replication. Với dịch vụ lưu trữ do nhà cung cấp quản lý, cần đọc cách tính dung lượng và độ bền để tránh nhân bản sao hai lần.
- **Backup và snapshot:** xác định chính sách lưu bản đầy đủ, bản tăng dần và thời gian giữ bản sao lưu.
- **Dung lượng trống:** để lại không gian cho compaction, tăng trưởng, thao tác bảo trì và khôi phục.

**Ví dụ:** giả sử hệ thống có trung bình 120 request/giây và mỗi request ghi một bản ghi 8 KB. Đây là giả định tải ghi; nếu chỉ một phần request tạo dữ liệu, phải thay 120 bằng số bản ghi ghi thực tế mỗi giây.

\[
120 \times 8\text{ KB} \times 86.400 \approx 82,9\text{ GB/ngày}
\]

Với thời gian lưu 30 ngày, dữ liệu thô vào khoảng 2,49 TB. Nếu đo được tỷ lệ sau nén là 50%, cần khoảng 1,245 TB. Nếu kiến trúc tự quản lý ba bản sao, dung lượng tăng lên khoảng 3,735 TB. Cộng 20% khoảng trống vận hành thì cần xấp xỉ 4,48 TB. Con số này chưa bao gồm backup độc lập nếu chính sách backup yêu cầu thêm dung lượng.

Phân biệt dung lượng lưu trữ với tốc độ đọc/ghi. Một ổ đĩa có đủ TB nhưng không đạt IOPS hoặc throughput yêu cầu vẫn có thể làm ứng dụng chậm. Với cơ sở dữ liệu, hãy kiểm tra kích thước block, tỷ lệ đọc/ghi, độ sâu hàng đợi, độ trễ đọc/ghi và tốc độ tăng dữ liệu. Với object storage, quan tâm thêm số lượng object, kích thước object, tần suất truy cập và lớp lưu trữ.

## 6. Tổng hợp thành cấu hình máy

Sau khi có ước lượng CPU, RAM, mạng và lưu trữ, chọn dòng máy phù hợp với đặc tính tải:

| Đặc tính tải | Hướng chọn cấu hình |
|---|---|
| Tính toán nhiều, ít dữ liệu trong bộ nhớ | Dòng tối ưu CPU, có hiệu năng mỗi vCPU phù hợp |
| Nhiều cache, dữ liệu nóng hoặc nhiều request đồng thời | Dòng tối ưu bộ nhớ, RAM đủ lớn và băng thông bộ nhớ phù hợp |
| Truyền dữ liệu lớn hoặc nhiều kết nối | Dòng có năng lực mạng cao, kiểm tra giới hạn băng thông và kết nối |
| Truy vấn lưu trữ nhiều, cần IOPS ổn định | Chọn loại volume/đĩa theo IOPS, throughput và độ trễ; cân nhắc máy có hỗ trợ lưu trữ phù hợp |
| Tải biến động mạnh | Cân nhắc autoscaling, hàng đợi và khả năng khởi tạo replica đủ nhanh |

Không nên chỉ so sánh số vCPU giữa các dòng máy. Hiệu năng mỗi vCPU còn phụ thuộc thế hệ CPU, kiến trúc, xung nhịp, mức chia sẻ tài nguyên và giới hạn duy trì hiệu năng. Máy burstable có thể phù hợp với tải thấp, ngắt quãng; tải CPU cao liên tục có thể làm cạn credit và giảm hiệu năng. Hãy so sánh bằng bài tải thử đại diện.

Với triển khai nhiều replica, tính năng lực cho từng replica và kiểm tra cả hai trạng thái: vận hành bình thường và khi một replica hoặc một vùng sẵn sàng bị mất. Nếu dùng autoscaling, xác định thời gian khởi động, thời gian tải dữ liệu/cache và tốc độ tăng replica. Autoscaling không thể bù tức thời cho một đợt tăng tải nhanh hơn thời gian khởi tạo máy.

## 7. Ví dụ tổng hợp

Một dịch vụ API có các giả định ban đầu sau:

| Tham số | Giá trị giả định |
|---|---:|
| RPS trung bình toàn dịch vụ | 120 request/giây |
| Hệ số đỉnh | 2 lần |
| RPS đỉnh toàn dịch vụ | 240 request/giây |
| CPU cho mỗi request | 25 ms |
| Thời gian phản hồi trung bình | 180 ms |
| RAM nền + cache + thành phần phụ trợ | 3,5 GB/replica |
| RAM tăng thêm khi xử lý một request | 3 MB |
| Dữ liệu trao đổi trung bình | 24 KB/request |
| Tốc độ ghi dữ liệu | 1 bản ghi 8 KB/request |
| Thời gian lưu dữ liệu | 30 ngày |

Với hai replica chia tải đều, mỗi replica nhận khoảng 120 request/giây ở thời điểm đỉnh. Mỗi replica cần khoảng 4,62 vCPU theo mục tiêu CPU 65%, nên có thể bắt đầu thử nghiệm ở mức 5 vCPU. Số request đồng thời trung bình mỗi replica khoảng 22; RAM ước lượng gồm 3,5 GB cố định và khoảng 66 MB cho request đang hoạt động. Sau khi cộng 30% dự phòng, nhu cầu khoảng 4,63 GB, nên chọn mức RAM tiêu chuẩn 6–8 GB.

Nếu yêu cầu một replica vẫn chịu được toàn bộ tải đỉnh khi replica còn lại hỏng, tính riêng trường hợp 240 request/giây cho một máy: khoảng 9,23 vCPU trước khi làm tròn và khoảng 43 request đồng thời trung bình. Khi đó có thể thử cấu hình khoảng 10 vCPU và 8 GB RAM cho mỗi replica. Đây là cấu hình dự phòng theo giả định đã nêu; chi phí và khả năng đáp ứng cần được xác nhận bằng kiểm thử lỗi thực tế.

Ở mức 120 request/giây trung bình, dữ liệu trao đổi tổng hợp khoảng 23 Mbit/s; mức đỉnh xấp xỉ 46 Mbit/s trước overhead. Tốc độ ghi giả định tạo khoảng 82,9 GB dữ liệu thô mỗi ngày, tương đương 2,49 TB trong 30 ngày trước khi tính nén, bản sao, index và backup. Các con số này giúp xác định giới hạn cần kiểm tra khi chọn network interface và storage.

Các kết quả trên không phải cấu hình áp dụng cho mọi API. Nếu request có tỷ lệ đọc/ghi khác, truy vấn cơ sở dữ liệu nặng, payload biến động hoặc cache hit ratio thấp, phải cập nhật các giả định rồi tính lại.

## 8. Kiểm chứng bằng tải thử và giám sát

Ước lượng chỉ là điểm bắt đầu. Trước khi chốt cấu hình, hãy chạy tải thử trên loại instance, hệ điều hành, runtime, storage và mạng dự kiến triển khai. Bài thử nên có tải trung bình, tải đỉnh, burst ngắn và giai đoạn duy trì tải đủ lâu để phát hiện vấn đề về bộ nhớ hoặc credit CPU.

Theo dõi tối thiểu các chỉ số sau:

- **CPU:** mức sử dụng theo từng instance, CPU throttling, thời gian chờ CPU và thời gian xử lý mỗi request.
- **RAM:** RSS, heap, native memory, garbage collection, swap và sự kiện OOM.
- **Độ trễ:** thời gian phản hồi p50, p95, p99; thời gian chờ trong hàng đợi và lỗi timeout.
- **Mạng:** throughput vào/ra, số kết nối, retransmission, packet drop và giới hạn băng thông.
- **Lưu trữ:** dung lượng đã dùng, tốc độ tăng, IOPS, throughput và độ trễ đọc/ghi.
- **Ứng dụng:** RPS thành công, tỷ lệ lỗi, cache hit ratio, số request đồng thời và độ sâu hàng đợi.

Nếu CPU thấp nhưng độ trễ cao, hãy kiểm tra thời gian chờ cơ sở dữ liệu, mạng, khóa hoặc hàng đợi trước khi tăng vCPU. Nếu RAM tăng dần trong bài soak test, kiểm tra rò rỉ bộ nhớ và cache không có giới hạn. Nếu storage còn nhiều dung lượng nhưng truy vấn chậm, kiểm tra IOPS và độ trễ. Khi mở rộng ngang, xác nhận load balancer phân phối tải đều và các thành phần dùng chung như database không trở thành nút thắt cổ chai.

Sau khi triển khai, so sánh số liệu thực tế với giả định ban đầu và cập nhật lại mô hình định kỳ. Lưu lượng, kích thước dữ liệu, phiên bản ứng dụng và hành vi người dùng đều có thể thay đổi; cấu hình máy cần được điều chỉnh theo bằng chứng đo được để giữ độ sẵn sàng và chi phí trong giới hạn mong muốn.
