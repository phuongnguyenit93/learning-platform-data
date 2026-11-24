# Phân biệt máy general purpose, compute optimized và memory optimized

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa máy ảo general purpose, compute optimized và memory optimized dựa trên tỷ lệ CPU, bộ nhớ và đặc điểm tải.
- Nhận diện loại cấu hình phù hợp với các workload phổ biến như ứng dụng web, xử lý dữ liệu, phân tích trong bộ nhớ và cơ sở dữ liệu.
- Đọc các dấu hiệu nghẽn tài nguyên để tránh chọn máy quá nhỏ, quá lớn hoặc lệch tài nguyên.
- Áp dụng quy trình chọn, kiểm thử và điều chỉnh cấu hình theo hiệu năng và chi phí.

## 1. Vì sao có nhiều nhóm cấu hình máy?

Một máy ảo (virtual machine – VM) thường được mô tả bằng số vCPU, dung lượng RAM, khả năng mạng và đặc tính lưu trữ. Tuy nhiên, hai máy có cùng số vCPU và RAM vẫn có thể khác nhau về thế hệ CPU, băng thông bộ nhớ, giới hạn mạng, khả năng lưu trữ hoặc hiệu năng duy trì khi tải cao. Nhà cung cấp đám mây vì vậy tổ chức các máy thành những nhóm cấu hình (instance family) để tối ưu cho những kiểu công việc khác nhau.

Ba nhóm thường gặp là:

- **General purpose (đa dụng):** cân bằng CPU, RAM và thường cả mạng. Phù hợp khi ứng dụng cần nhiều loại tài nguyên ở mức tương đối đồng đều hoặc chưa có bằng chứng cho thấy một tài nguyên cụ thể là nút thắt.
- **Compute optimized (tối ưu tính toán):** ưu tiên năng lực xử lý trên mỗi đơn vị chi phí, thường có tỷ lệ vCPU/RAM cao hơn nhóm đa dụng. Phù hợp với tác vụ bị giới hạn bởi CPU.
- **Memory optimized (tối ưu bộ nhớ):** cung cấp nhiều RAM so với số vCPU, cùng khả năng phục vụ tập dữ liệu lớn trong bộ nhớ. Phù hợp khi dung lượng bộ nhớ hoặc băng thông truy cập RAM là yếu tố giới hạn.

Không có nhóm nào nhanh nhất cho mọi ứng dụng. Một máy compute optimized có thể hoàn thành phép tính nhanh hơn nhưng vẫn hoạt động kém nếu ứng dụng phải đọc dữ liệu từ đĩa liên tục vì thiếu RAM. Ngược lại, máy memory optimized có nhiều RAM nhưng có thể lãng phí chi phí nếu workload chỉ dùng một phần nhỏ bộ nhớ và chủ yếu chờ CPU.

## 2. Hiểu tỷ lệ CPU và RAM

Khi so sánh cấu hình, hãy xem đồng thời số vCPU và RAM thay vì chỉ nhìn một con số. Một cách mô tả đơn giản là tỷ lệ RAM trên vCPU:

\[
\text{RAM/vCPU} = \frac{\text{Dung lượng RAM (GiB)}}{\text{Số vCPU}}
\]

Ví dụ minh họa:

| Cấu hình | vCPU | RAM | RAM/vCPU | Nhận xét |
|---|---:|---:|---:|---|
| A | 4 | 16 GiB | 4 GiB | Cân bằng, có thể phù hợp workload đa dụng |
| B | 8 | 16 GiB | 2 GiB | Nhiều năng lực CPU tương đối so với RAM |
| C | 4 | 64 GiB | 16 GiB | Nhiều RAM tương đối so với CPU |

Các con số trên chỉ nhằm minh họa cách so sánh. Mỗi nhà cung cấp và từng thế hệ instance có tỷ lệ, giới hạn CPU, RAM, mạng và giá khác nhau. Không nên coi một tỷ lệ cố định là tiêu chuẩn chung cho mọi cloud.

Tỷ lệ RAM/vCPU giúp sàng lọc nhanh, nhưng chưa đủ để quyết định. Bạn cũng cần xem:

- **Hiệu năng CPU:** thế hệ bộ xử lý, xung nhịp duy trì, số lõi vật lý được ánh xạ, tập lệnh và hiệu năng đơn luồng. Một ứng dụng có một luồng xử lý nặng có thể cần CPU đơn nhân mạnh hơn là thật nhiều vCPU.
- **Băng thông bộ nhớ:** workload quét hoặc xử lý tập dữ liệu lớn có thể bị giới hạn bởi tốc độ đưa dữ liệu từ RAM đến CPU, ngay cả khi dung lượng RAM còn dư.
- **Mạng:** hệ thống phân tán, cache từ xa và dịch vụ truyền dữ liệu lớn có thể cần băng thông hoặc số kết nối cao.
- **Lưu trữ:** IOPS, thông lượng và độ trễ của volume có thể ảnh hưởng mạnh đến cơ sở dữ liệu và ứng dụng đọc/ghi nhiều.
- **Tính chất cấp phát CPU:** một số dòng máy dùng cơ chế burst hoặc chia sẻ năng lực CPU. Cần kiểm tra giới hạn duy trì và cơ chế credit nếu tải CPU kéo dài.

## 3. Máy general purpose: cấu hình cân bằng

General purpose hướng đến workload sử dụng CPU và RAM ở mức tương đối cân đối. Đây thường là điểm bắt đầu hợp lý cho dịch vụ mới, môi trường phát triển, ứng dụng web thông thường và các thành phần chưa có số liệu vận hành đủ rõ.

### Đặc điểm

- Cung cấp tỷ lệ CPU/RAM cân bằng cho nhiều loại ứng dụng.
- Dễ dùng làm cấu hình nền để đo đạc trước khi chuyển sang một nhóm chuyên biệt.
- Có nhiều kích thước để tăng hoặc giảm tài nguyên theo nhu cầu.
- Một số nhà cung cấp có biến thể general purpose dạng burstable; biến thể này phù hợp tải có mức sử dụng CPU trung bình thấp và thỉnh thoảng tăng đột biến, nhưng phải hiểu rõ giới hạn credit.

### Workload phù hợp

- Máy chủ web và API có lưu lượng vừa phải.
- Dịch vụ backend, ứng dụng nghiệp vụ và máy chủ ứng dụng.
- Môi trường phát triển, kiểm thử, staging.
- Máy chủ điều phối, dịch vụ nội bộ hoặc ứng dụng có tải CPU và bộ nhớ không quá lệch.
- Cơ sở dữ liệu nhỏ hoặc vừa khi yêu cầu CPU, RAM, I/O đều ở mức vừa phải và được kiểm chứng bằng benchmark.

### Khi nào nên cân nhắc nhóm khác?

Nếu CPU thường xuyên gần bão hòa trong khi RAM còn dư đáng kể, nhóm compute optimized có thể hiệu quả hơn. Nếu working set chiếm gần hết RAM, hệ điều hành phải thu hồi cache liên tục hoặc ứng dụng bị OOM, nhóm memory optimized có thể phù hợp hơn. Hãy xác nhận bằng số liệu trong giờ cao điểm trước khi đổi cấu hình.

## 4. Máy compute optimized: ưu tiên CPU

Compute optimized dành cho workload thực hiện nhiều phép tính và cần nhiều năng lực xử lý hơn so với lượng RAM đi kèm. Nhóm này thường có tỷ lệ vCPU/RAM cao hơn general purpose.

### Đặc điểm

- Tập trung vào thông lượng tính toán hoặc hiệu năng CPU.
- Phù hợp với xử lý song song nếu ứng dụng có thể chia công việc cho nhiều luồng hoặc tiến trình.
- Có thể có lợi cho workload nhạy với hiệu năng đơn luồng; cần kiểm tra benchmark của đúng thế hệ CPU thay vì chỉ so số vCPU.
- Không tự động cải thiện tác vụ bị giới hạn bởi mạng, lưu trữ hoặc khóa đồng bộ trong ứng dụng.

### Workload phù hợp

- Mã hóa, giải mã, nén và giải nén dữ liệu.
- Xử lý ảnh, âm thanh, video bằng CPU.
- Phân tích dữ liệu theo lô, chuyển đổi dữ liệu và ETL có tính toán nặng.
- Mô phỏng khoa học, tính toán số và một số workload kỹ thuật.
- Máy chủ game hoặc dịch vụ có logic tính toán cao, khi profiling cho thấy CPU là nút thắt.
- Máy chủ build, biên dịch mã nguồn và chạy tác vụ CI cần CPU liên tục.

### Dấu hiệu workload bị giới hạn bởi CPU

- CPU utilization duy trì cao trong khoảng thời gian có tải thực tế.
- Hàng đợi chạy (run queue) tăng và tiến trình phải chờ CPU.
- Thời gian xử lý giảm rõ rệt khi tăng năng lực CPU trong một thử nghiệm có kiểm soát.
- RAM vẫn còn dư, không có dấu hiệu swapping hoặc thiếu bộ nhớ.

CPU utilization cao trong thời gian ngắn chưa đủ để kết luận cần compute optimized. Hãy kiểm tra thời gian phản hồi, thông lượng, hàng đợi CPU và mức tải thực tế. Một dịch vụ có thể dùng CPU cao nhưng vẫn đáp ứng SLA; một dịch vụ khác có CPU trung bình thấp nhưng bị nghẽn ở một luồng đơn lẻ.

## 5. Máy memory optimized: ưu tiên RAM

Memory optimized dành cho ứng dụng cần giữ tập dữ liệu lớn trong bộ nhớ hoặc truy cập RAM với cường độ cao. Nhóm này thường cung cấp nhiều RAM trên mỗi vCPU hơn general purpose.

### Đặc điểm

- Có dung lượng RAM lớn để giữ working set, cache hoặc chỉ mục trong bộ nhớ.
- Giúp giảm việc phải đọc dữ liệu từ lưu trữ chậm hơn khi dữ liệu có thể được giữ trong RAM.
- Phù hợp với hệ thống có cấu trúc dữ liệu lớn, nhiều kết nối hoặc nhiều tiến trình đồng thời cần bộ nhớ.
- Cần đánh giá cả băng thông và độ trễ bộ nhớ nếu workload nhạy với truy cập RAM.

### Workload phù hợp

- Cơ sở dữ liệu quan hệ hoặc NoSQL có working set lớn, khi benchmark cho thấy RAM là giới hạn.
- Cơ sở dữ liệu trong bộ nhớ và kho dữ liệu dạng key-value.
- Cache phân tán hoặc cache lớn đặt trên máy chủ.
- Phân tích dữ liệu trong bộ nhớ, truy vấn tương tác trên tập dữ liệu lớn.
- Xử lý dữ liệu dạng đồ thị hoặc ứng dụng giữ nhiều đối tượng trong heap.
- Máy chủ chạy nhiều tiến trình hoặc container có tổng nhu cầu bộ nhớ lớn.

### Dấu hiệu workload bị giới hạn bởi bộ nhớ

- Mức sử dụng RAM thường xuyên cao trong giờ cao điểm và tăng cùng kích thước dữ liệu.
- Hệ điều hành phải swap hoặc reclaim bộ nhớ liên tục; độ trễ tăng khi áp lực bộ nhớ xuất hiện.
- Ứng dụng ghi nhận lỗi cấp phát bộ nhớ, bị OOM killer kết thúc hoặc container chạm memory limit.
- Tăng RAM giúp giảm cache miss ở tầng lưu trữ, giảm swapping hoặc cải thiện thời gian truy vấn trong thử nghiệm.

Không phải mọi mức RAM sử dụng cao đều là vấn đề. Hệ điều hành thường dùng RAM nhàn rỗi làm page cache; vì vậy cần xem available thay vì chỉ nhìn used. Với Java, cần theo dõi heap, non-heap, garbage collection và giới hạn container. Heap lớn hơn không phải lúc nào cũng làm ứng dụng nhanh hơn nếu thời gian GC tăng hoặc cấu trúc dữ liệu không cần thiết chiếm bộ nhớ.

## 6. So sánh ba nhóm cấu hình

| Tiêu chí | General purpose | Compute optimized | Memory optimized |
|---|---|---|---|
| Ưu tiên | Cân bằng CPU và RAM | Năng lực CPU | Dung lượng/băng thông RAM |
| Tỷ lệ RAM/vCPU tương đối | Trung bình, cân bằng | Thấp hơn | Cao hơn |
| Workload điển hình | Web, API, backend, môi trường dev/test | Mã hóa, build, mô phỏng, xử lý dữ liệu nặng CPU | Database/cache lớn, phân tích trong RAM |
| Dấu hiệu nên cân nhắc | Chưa có nút thắt nổi bật; tải khá cân bằng | CPU là nút thắt đã được đo | RAM/working set là nút thắt đã được đo |
| Rủi ro khi chọn sai | Có thể thiếu CPU hoặc RAM khi tải lệch | Trả tiền cho CPU dư nếu ứng dụng chờ I/O hoặc thiếu RAM | Trả tiền cho RAM dư nếu working set nhỏ hoặc CPU mới là nút thắt |

Các tên nhóm có thể khác nhau giữa AWS, Azure, Google Cloud và các nhà cung cấp khác. Ví dụ, một nhà cung cấp có thể dùng ký hiệu M cho nhóm đa dụng, C cho nhóm compute optimized và R hoặc X cho một số nhóm memory optimized. Đây là quy ước minh họa, không phải quy tắc đặt tên bắt buộc. Luôn kiểm tra bảng thông số của đúng vùng, thế hệ và loại instance trước khi triển khai.

## 7. Cách nhận diện tài nguyên đang giới hạn ứng dụng

Để chọn đúng nhóm máy, hãy đo ứng dụng dưới tải gần với thực tế. Một chỉ số đơn lẻ có thể gây hiểu nhầm; nên ghép chỉ số hạ tầng với metric ở tầng ứng dụng.

| Quan sát | Khả năng cần điều tra | Hướng thử nghiệm |
|---|---|---|
| CPU cao kéo dài, run queue tăng, RAM còn dư | Thiếu năng lực CPU | Thử compute optimized hoặc tăng vCPU; kiểm tra song song hóa và hiệu năng đơn luồng |
| RAM available thấp, swap tăng, OOM hoặc latency tăng theo working set | Thiếu bộ nhớ | Thử memory optimized hoặc giảm working set/cache; kiểm tra memory leak và giới hạn container |
| CPU và RAM đều cao | Tổng tải đã vượt cấu hình hoặc ứng dụng giữ nhiều dữ liệu và tính toán cùng lúc | So sánh tăng kích thước máy với mở rộng ngang; profiling cả CPU lẫn bộ nhớ |
| CPU và RAM đều thấp nhưng phản hồi chậm | Có thể nghẽn mạng, lưu trữ, khóa, dependency hoặc giới hạn kết nối | Kiểm tra I/O, network latency, connection pool, lock contention và dịch vụ phụ thuộc |
| CPU tăng vọt rồi bị giới hạn dù trung bình thấp | Có thể dùng máy burstable và cạn CPU credit | Kiểm tra cơ chế credit, giới hạn sustained performance và đặc điểm tải |

Trên Linux, các lệnh sau có thể hỗ trợ kiểm tra ban đầu:

```bash
# Tổng quan CPU, tiến trình và bộ nhớ
top

# Bộ nhớ vật lý và swap; chú ý cột available
free -h

# Run queue, swap và hoạt động hệ thống theo từng giây
vmstat 1

# Thống kê CPU theo tiến trình (nếu sysstat đã được cài)
pidstat 1

# Độ trễ, IOPS và thông lượng thiết bị lưu trữ (nếu sysstat đã được cài)
iostat -xz 1
```

Trong môi trường cloud, hãy kết hợp các lệnh này với dashboard và cảnh báo của nhà cung cấp. Nhiều nền tảng không cung cấp đầy đủ metric bộ nhớ bên trong guest OS nếu chưa cài agent hoặc bật cơ chế thu thập phù hợp. Với container, phải kiểm tra cả mức sử dụng và giới hạn CPU/RAM ở cấp container hoặc pod; số liệu của toàn VM có thể che khuất một container đang chạm giới hạn.

## 8. Quy trình chọn nhóm instance

1. **Mô tả workload.** Xác định ứng dụng làm gì, số người dùng hoặc yêu cầu thông lượng, kích thước dữ liệu, mức đồng thời và thời gian tải cao điểm.
2. **Đặt mục tiêu vận hành.** Ghi rõ SLA/SLO, thời gian phản hồi, thông lượng, độ sẵn sàng và ngân sách. Không chọn cấu hình chỉ dựa trên mức CPU trung bình.
3. **Lấy baseline.** Đo CPU, RAM available, swap, I/O, network, run queue và metric ứng dụng trong điều kiện đại diện, bao gồm cả tải cao điểm.
4. **Xác định nút thắt.** Phân biệt CPU-bound, memory-bound, I/O-bound và network-bound. Dùng profiling hoặc benchmark để xác nhận khi cần.
5. **Chọn nhóm ứng viên.** Dùng general purpose khi tải cân bằng hoặc chưa có bằng chứng; compute optimized khi CPU là giới hạn; memory optimized khi working set hoặc dung lượng RAM là giới hạn.
6. **So sánh kích thước và thế hệ.** Kiểm tra vCPU, RAM, CPU generation, hiệu năng mạng, loại lưu trữ, giới hạn I/O, tính burstable, vùng khả dụng và giá.
7. **Kiểm thử có kiểm soát.** Chạy cùng một bộ tải và dữ liệu trên các cấu hình ứng viên. So sánh p95/p99 latency, throughput, lỗi, CPU, RAM và chi phí trên mỗi đơn vị công việc.
8. **Triển khai và theo dõi.** Bắt đầu với phạm vi nhỏ, đặt cảnh báo cho các ngưỡng có ý nghĩa, rồi điều chỉnh theo xu hướng và thay đổi workload.

Khi workload thay đổi theo giờ hoặc theo mùa, có thể kết hợp chọn đúng instance family với autoscaling. Mở rộng ngang giúp tăng số máy phục vụ đồng thời; tăng kích thước máy (vertical scaling) giúp một tiến trình có thêm CPU hoặc RAM. Cần xem kiến trúc ứng dụng có hỗ trợ chia tải, trạng thái phiên và phân vùng dữ liệu hay không trước khi chọn cách mở rộng.

## 9. Ví dụ thực tế: chọn máy cho ba dịch vụ

Giả sử một hệ thống có ba thành phần với số liệu đo trong giờ cao điểm:

| Thành phần | Số liệu quan sát | Nhận định ban đầu | Nhóm nên thử |
|---|---|---|---|
| API xử lý nghiệp vụ | CPU 35–50%, RAM available còn nhiều, độ trễ ổn định | Tài nguyên tương đối cân bằng | General purpose |
| Dịch vụ chuyển mã video bằng CPU | CPU duy trì 90%, run queue tăng, RAM còn dư | Công việc thiên về tính toán | Compute optimized |
| Cụm cache giữ tập dữ liệu lớn | RAM available thấp, cache eviction và truy cập lưu trữ tăng, CPU trung bình 30% | Working set vượt khả năng bộ nhớ hiện tại | Memory optimized |

Đây là giả định để minh họa cách suy luận. Trước khi chuyển nhóm, đội vận hành cần chạy benchmark trên cấu hình thực tế, kiểm tra giới hạn mạng/lưu trữ và đo chi phí. Nếu API có đợt tăng tải ngắn, autoscaling hoặc instance burstable có thể là ứng viên, nhưng cần xác nhận thời gian burst và khả năng duy trì tải.

## 10. Những nhầm lẫn thường gặp

- **Chỉ nhìn số vCPU.** Số vCPU không thể hiện đầy đủ hiệu năng mỗi lõi, thế hệ CPU, giới hạn duy trì hoặc khả năng song song của ứng dụng.
- **Coi RAM đã dùng là RAM thiếu.** Hệ điều hành tận dụng bộ nhớ trống làm cache. Hãy xem RAM available, swap, áp lực bộ nhớ và hành vi ứng dụng.
- **Cho rằng memory optimized sẽ làm mọi database nhanh hơn.** Database còn phụ thuộc vào thiết kế chỉ mục, truy vấn, độ trễ lưu trữ, IOPS, khóa và mạng.
- **Cho rằng compute optimized phù hợp với mọi tác vụ nặng.** Tác vụ chờ lưu trữ hoặc mạng sẽ không cải thiện nhiều chỉ bằng cách tăng CPU.
- **Bỏ qua giới hạn burst.** Máy burstable có thể chạy nhanh trong thời gian ngắn nhưng không phù hợp với tải CPU cao liên tục nếu credit hoặc giới hạn duy trì không đáp ứng.
- **So sánh giá theo giờ mà quên chi phí trên mỗi tác vụ.** Máy đắt hơn có thể hoàn thành công việc nhanh hơn; cần so sánh tổng chi phí để đạt cùng SLA hoặc cùng khối lượng xử lý.
- **Không đo lại sau khi triển khai.** Workload, kích thước dữ liệu và mô hình truy cập thay đổi theo thời gian, vì vậy quyết định cấu hình cần được xem xét định kỳ.

## 11. Tự kiểm tra

**Tình huống 1:** Một tác vụ nén dữ liệu chạy liên tục, CPU gần 100%, hàng đợi CPU tăng, RAM còn nhiều. Bạn nên thử nhóm nào trước?

**Gợi ý:** Compute optimized là ứng viên đầu tiên vì dữ liệu cho thấy CPU đang là nút thắt. Vẫn cần benchmark để kiểm tra hiệu năng đơn luồng, khả năng song song và giới hạn I/O.

**Tình huống 2:** Một dịch vụ cache có CPU thấp nhưng thường xuyên thiếu RAM, phải loại bỏ dữ liệu khỏi cache và đọc lại từ lưu trữ. Nhóm nào phù hợp hơn?

**Gợi ý:** Memory optimized có thể giúp giữ working set lớn hơn trong RAM. Đồng thời cần xem lại chính sách cache, kích thước dữ liệu và chi phí của cache miss.

**Tình huống 3:** Một ứng dụng nội bộ có CPU và RAM sử dụng ở mức vừa phải, chưa có dấu hiệu nghẽn rõ ràng. Nên bắt đầu từ đâu?

**Gợi ý:** General purpose thường là lựa chọn khởi đầu hợp lý. Thu thập baseline và kiểm thử tải trước khi chuyển sang nhóm chuyên biệt.

## Kết luận

General purpose phù hợp với workload cần sự cân bằng giữa CPU và RAM. Compute optimized phù hợp khi năng lực xử lý CPU là giới hạn chính. Memory optimized phù hợp khi ứng dụng cần giữ working set lớn hoặc đang chịu áp lực bộ nhớ. Hãy dùng metric và benchmark của chính workload để xác nhận lựa chọn, đồng thời kiểm tra mạng, lưu trữ, thế hệ CPU, giới hạn burst và chi phí vận hành trước khi chốt cấu hình.
