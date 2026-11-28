# Xác định mục tiêu latency, throughput và sử dụng tài nguyên

Trong Java 27, tối ưu hiệu năng không bắt đầu bằng việc thêm thread, đổi garbage collector hay thay một cấu trúc dữ liệu. Trước hết cần trả lời: **hệ thống phải phục vụ khối lượng công việc nào, nhanh đến mức nào, với độ tin cậy và chi phí tài nguyên ra sao?**

Ba nhóm mục tiêu cốt lõi là:

- **Latency (độ trễ):** thời gian từ một điểm bắt đầu được định nghĩa rõ tới khi một thao tác hoàn tất, thường tính bằng mili giây.
- **Throughput (thông lượng):** số lượng công việc hoàn tất trong một đơn vị thời gian, ví dụ request/giây, giao dịch/giây hoặc MB/giây.
- **Resource utilization (mức sử dụng tài nguyên):** mức tiêu thụ CPU, heap, native memory, I/O, kết nối, thread, hàng đợi và những tài nguyên hữu hạn khác.

Một ứng dụng có throughput cao nhưng **p99 latency** rất xấu vẫn có thể đem lại trải nghiệm không chấp nhận được. Ngược lại, một ứng dụng nhanh khi chỉ có một người dùng có thể suy giảm mạnh khi hàng đợi đầy và CPU hoặc database bị bão hòa.

Bài học thuộc chương **Chẩn đoán và hiệu năng** của học phần **Java 27 và các kiến thức liên quan**. Nội dung tập trung vào cách **định nghĩa mục tiêu có thể đo lường**, lựa chọn chỉ số, dựng kịch bản kiểm thử, thu thập dữ liệu bằng công cụ hiện hành của JDK và diễn giải kết quả mà không đánh đồng tương quan với nguyên nhân.

## 1. Từ yêu cầu nghiệp vụ tới mục tiêu kỹ thuật

Phát biểu mơ hồ:

> “API phải chạy nhanh và không dùng quá nhiều RAM.”

Không thể dùng phát biểu này để kết luận một bản phát hành đã đạt hay chưa. Một yêu cầu kiểm chứng được cần nêu ít nhất:

1. **Phạm vi:** endpoint, loại tác vụ, thành phần hoặc toàn dịch vụ.
2. **Workload:** số request đến, tỷ lệ từng loại request, kích thước dữ liệu, số người dùng.
3. **Chỉ số:** latency, throughput, error rate và tài nguyên.
4. **Ngưỡng:** ví dụ p95 dưới 200 ms.
5. **Khoảng thời gian:** ví dụ cửa sổ 10 phút hoặc toàn bộ bài load test 30 phút.
6. **Điều kiện đo:** số instance, CPU/RAM được cấp, phiên bản JVM, trạng thái cache và hệ thống phụ thuộc.
7. **Quy tắc chấp nhận:** mọi điều kiện nào phải đồng thời đúng.

Ví dụ mục tiêu *minh họa*, không phải chuẩn phổ quát:

| Thành phần | Mục tiêu minh họa | Điều kiện |
|---|---|---|
| API tra cứu sản phẩm | p95 ≤ 150 ms; p99 ≤ 400 ms | 300 request/giây, payload và dữ liệu theo kịch bản |
| API tạo đơn hàng | p99 ≤ 700 ms | 50 request/giây, database thật của môi trường kiểm thử |
| Thành công | ≥ 99,9% request hợp lệ | Không loại trừ lỗi server một cách tùy tiện |
| CPU | CPU process còn headroom, không bão hòa kéo dài | Instance và giới hạn CPU được nêu rõ |
| Heap/GC | Không tăng bộ nhớ giữ lại không giới hạn; GC pause đáp ứng ngân sách latency | Trong thời gian chạy ổn định và sau các chu kỳ tải |
| Hàng đợi | Không tăng vô hạn; có giới hạn và chính sách từ chối | Khi tải vượt năng lực xử lý |

**Các con số trên chỉ là ví dụ để học cách đặt mục tiêu.** Ngưỡng phù hợp phải xuất phát từ nhu cầu người dùng, kiến trúc, chi phí và dữ liệu vận hành thực tế.

## 2. Phân biệt SLI, SLO và SLA

Ba thuật ngữ thường xuất hiện trong quản lý độ tin cậy và hiệu năng.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **SLI — Service Level Indicator** | Chỉ số quan sát được | Tỷ lệ request có latency không quá 200 ms |
| **SLO — Service Level Objective** | Mục tiêu đặt trên một hoặc nhiều SLI | Ít nhất 99% request hợp lệ hoàn tất trong 200 ms |
| **SLA — Service Level Agreement** | Thỏa thuận cam kết với bên sử dụng, có thể kèm hệ quả hợp đồng | Điều khoản dịch vụ và cách tính vi phạm |

SLO không nhất thiết là SLA. Một nhóm có thể đặt **SLO nội bộ nghiêm ngặt hơn** để có khoảng dự phòng trước khi vi phạm cam kết bên ngoài.

### SLI phải xác định chính xác mẫu số

Nếu chọn SLI về latency:

\[
SLI_{latency} = \frac{\text{số request hợp lệ có latency }\le T}{\text{tổng số request hợp lệ trong phạm vi đo}}
\]

Cần nói rõ “request hợp lệ” là gì. Ví dụ có tính request lỗi 5xx không? Tính những request bị timeout ở gateway không? Có bao gồm request bị rate limit không?

Không được loại toàn bộ request chậm hoặc lỗi khỏi mẫu số chỉ để tỷ lệ đẹp hơn. Nếu một request hết timeout và không có latency hoàn tất phía ứng dụng, hệ thống vẫn cần ghi nhận nó theo hợp đồng SLI từ điểm quan sát thích hợp.

### Error budget

Với SLO thành công **99,9%**, phần ngân sách lỗi là **0,1%**:

\[
Error\ budget = 1 - 0.999 = 0.001
\]

Nếu có 1.000.000 request đủ điều kiện trong kỳ, ngân sách tương đương **1.000 request không đạt** tiêu chí thành công. Đây là ví dụ số học, không có nghĩa 1.000 lỗi luôn chấp nhận được về mặt nghiệp vụ.

SLO latency và SLO availability có thể tạo **những ngân sách riêng**. Một request thành công nhưng cực chậm có thể không đạt SLO latency, dù không tính là lỗi ứng dụng.

## 3. Xác định ranh giới đo latency

Latency là **khoảng thời gian giữa hai sự kiện**. Nếu không định nghĩa hai điểm đó, cùng một endpoint có thể được báo cáo bằng nhiều số liệu không so sánh được.

Ví dụ:

~~~text
Client gửi request
       |
       v
Load balancer nhận
       |
       v
Hàng đợi tại gateway
       |
       v
Server Java nhận
       |
       v
Chờ executor / connection
       |
       v
Đọc cache / truy vấn database
       |
       v
Tạo response
       |
       v
Client nhận đủ response
~~~

Các loại latency:

- **Client-observed latency:** từ lúc client bắt đầu gửi đến khi nhận kết quả theo giao thức đo.
- **Gateway latency:** thời gian request nằm trong phạm vi gateway.
- **Application latency:** thời gian ứng dụng Java xử lý request từ ranh giới đã instrument.
- **Dependency latency:** thời gian chờ database, HTTP downstream hoặc một tài nguyên khác.
- **Queue wait time:** thời gian chờ trước khi bắt đầu công việc.
- **Service time:** thời gian thực sự xử lý khi tác vụ được nhận.

**Một số đo latency chỉ có ý nghĩa khi gắn với điểm bắt đầu, điểm kết thúc và phạm vi tính toán.**

Nếu người dùng quan tâm “nhấn nút đến lúc nhìn thấy kết quả”, chỉ đo một method Java nhanh 2 ms không đủ để kết luận trải nghiệm đáp ứng mục tiêu 200 ms.

## 4. Mean, median và percentile latency

Các cách tóm tắt latency không mang cùng thông tin.

- **Mean (trung bình cộng):** tổng thời gian của các quan sát chia cho số quan sát.
- **Median (p50):** khoảng 50% quan sát có latency không lớn hơn mức này theo cách định nghĩa quantile.
- **p90:** khoảng 90% quan sát nằm ở hoặc dưới ngưỡng percentile.
- **p95:** mô tả phần đuôi của 5% request chậm nhất.
- **p99:** mô tả phần đuôi của 1% request chậm nhất.
- **p99.9:** tập trung vào những quan sát rất hiếm; đòi hỏi số lượng mẫu đáng kể.

Ví dụ có 1.000 request, một phương pháp tính percentile có thể cho:

| Chỉ số | Giá trị minh họa |
|---|---:|
| p50 | 35 ms |
| p90 | 80 ms |
| p95 | 120 ms |
| p99 | 480 ms |
| max | 2.400 ms |

Nếu chỉ nhìn p50 = 35 ms, có thể bỏ qua một nhóm request có độ trễ rất lớn. Người dùng gặp nhóm p99 vẫn bị ảnh hưởng dù “trung bình khá nhanh”.

### Vì sao trung bình có thể đánh lừa?

Giả sử 99 request mất 10 ms và 1 request mất 2.000 ms:

\[
Mean = \frac{99\times10 + 2000}{100} = 29.9\text{ ms}
\]

Mean chỉ gần 30 ms, nhưng người dùng gặp request chậm nhất phải chờ **2 giây**. Vì vậy, khi đánh giá dịch vụ tương tác, hãy đo thêm percentile phù hợp thay vì chỉ báo cáo mean.

**Percentile không phải giá trị bảo đảm tuyệt đối cho mọi request.** Mục tiêu p99 ≤ 400 ms vẫn cho phép một phần nhỏ request chậm hơn ngưỡng, tùy định nghĩa SLO và cửa sổ đo.

## 5. Hiểu đúng p99 và số lượng mẫu

Trong một tập 10.000 request, p99 nằm gần ranh giới giữa nhóm 99% nhanh hơn và nhóm 1% chậm nhất. Tuy nhiên, các công cụ đo có thể dùng những phương pháp tính quantile khác nhau, bao gồm nearest-rank, nội suy hoặc histogram.

Ví dụ nearest-rank với danh sách đã sắp xếp tăng dần:

\[
rank(p) = \lceil p \times N \rceil
\]

Với p = 0,99 và N = 100, rank = 99 (đếm từ 1). Giá trị ở vị trí 99 là p99 theo định nghĩa này.

### Không kết luận từ p99 của một tập quá nhỏ

Nếu chỉ có vài chục quan sát, “p99” gần như phản ánh một trong những giá trị lớn nhất và có độ bất định thống kê cao. Khi số lượng mẫu ít, nên hiển thị **N**, số lỗi, max và thời gian thu thập cùng percentile.

Với khối lượng thấp, có thể lựa chọn cửa sổ dài hơn, chỉ số phù hợp hơn hoặc diễn giải độ bất định. Không được biến một con số p99 thiếu mẫu thành bằng chứng hệ thống đã đạt một SLO nghiêm ngặt.

### Không lấy trung bình các percentile

Nếu instance A có p99 = 100 ms, instance B có p99 = 900 ms, **(100 + 900)/2 = 500 ms không phải p99 của toàn hệ thống**.

Vì sao?

- Hai instance có thể xử lý số lượng request khác nhau.
- Phân bố latency có hình dạng khác nhau.
- Percentile không tuyến tính như tổng số request.

Để tính p99 toàn cụm, phải tổng hợp các quan sát hoặc dữ liệu histogram/bucket có cách gộp phù hợp. Không lấy trung bình p99 từ các instance hoặc các phút rồi tuyên bố đó là percentile toàn bộ.

## 6. Tail latency và đường găng của request

**Tail latency** đề cập đến phần đuôi của phân bố thời gian phản hồi, thường được theo dõi qua p95, p99 hoặc p99.9.

Các nguyên nhân thường gặp:

- Hàng đợi tăng khi tải cao.
- Garbage collection pause hoặc allocation churn.
- Tranh chấp khóa và scheduler delay.
- Truy vấn database đột biến.
- Lỗi cache miss khiến phải gọi tầng chậm.
- Network retransmission hoặc timeout ở dịch vụ phụ thuộc.
- Một số payload lớn hơn trung bình.
- Retry khiến request trải qua nhiều lần gọi.

### Tác vụ fan-out

Nếu một request đồng thời gọi nhiều dịch vụ và đợi tất cả hoàn tất, latency của request thường chịu ảnh hưởng bởi **nhánh chậm nhất**, không phải trung bình của các nhánh.

~~~text
Request tổng
    |
    +---- Service A: 20 ms ---+
    |                        |
    +---- Service B: 45 ms ---+--> Tổng hợp sau khi cả ba hoàn tất
    |                        |
    +---- Service C: 400 ms --+
~~~

Một đường găng như vậy có thể làm tail latency xấu ngay cả khi đa số dependency nhanh. Cần theo dõi cả **end-to-end latency** và latency từng dependency, đồng thời có chính sách timeout/fallback phù hợp yêu cầu nghiệp vụ.

Không tối ưu hóa một method chiếm 1 ms nếu đường găng thường nằm ở lời gọi database chậm 300 ms.

## 7. Phân biệt queue wait, service time và end-to-end

Thời gian tổng của một tác vụ thường gồm nhiều thành phần:

\[
W_{total} \approx W_{queue} + W_{service} + W_{transport}
\]

Trong đó cách tách phụ thuộc hệ thống; có những thành phần có thể chồng lấn thời gian nên không phải mọi phép cộng đều đúng tuyệt đối.

Ví dụ:

~~~text
Arrival: 00 ms
         |
         | Queue wait 180 ms
         v
Start: 180 ms
         |
         | Work time 20 ms
         v
Done: 200 ms
~~~

Nếu chỉ đo từ lúc worker bắt đầu xử lý, bạn báo cáo 20 ms, nhưng tác vụ đã mất **200 ms từ khi vào hàng đợi**.

Do đó, khi đặt SLO latency, thường cần giữ ít nhất hai số:

1. **End-to-end** từ ranh giới người dùng/caller quan tâm.
2. **Service time** hoặc các phân đoạn để điều tra nguyên nhân.

Đo các mốc thời gian ở cùng hệ đồng hồ phù hợp. Trong cùng tiến trình JVM, dùng **System.nanoTime()** để đo khoảng thời gian; không dùng **System.currentTimeMillis()** cho phép tính độ dài ngắn khi đồng hồ hệ thống có thể được hiệu chỉnh.

## 8. Throughput: đo tốc độ hoàn tất, không chỉ tốc độ nhận

Throughput thường tính:

\[
Throughput = \frac{\text{số công việc hoàn tất}}{\text{thời gian đã trôi qua}}
\]

Với API, đơn vị có thể là:

- **Requests per second (RPS)**: số request/giây.
- **Transactions per second (TPS)**: số giao dịch theo định nghĩa nghiệp vụ/giây.
- **Messages per second**: số message được xử lý/giây.
- **MiB/s**: số byte dữ liệu hoàn tất xử lý hoặc truyền trong một giây.

Không được so sánh RPS với TPS nếu một transaction bao gồm nhiều request.

### Arrival rate khác completion rate

Giả sử:

~~~text
Tải đầu vào:           500 requests/s
Ứng dụng hoàn tất:     350 requests/s
Phần chênh lệch:       150 requests/s
~~~

Nếu không từ chối hay kiểm soát tải, backlog có thể tăng. **Số request được gửi vào hệ thống không phải throughput đã xử lý thành công.**

Nên đo ba luồng số liệu riêng:

| Chỉ số | Câu hỏi trả lời |
|---|---|
| **Offered/arrival rate** | Bao nhiêu request đến mỗi giây? |
| **Admitted rate** | Bao nhiêu request được hệ thống chấp nhận? |
| **Completed/success rate** | Bao nhiêu request hoàn tất, và bao nhiêu thành công? |

Một load generator có thể gửi 1.000 RPS, nhưng nếu server chỉ hoàn tất 400 RPS còn phần lớn lỗi hoặc timeout, không thể báo throughput thành công là 1.000 RPS.

## 9. Latency và throughput không tăng/giảm tuyến tính

Ở mức tải thấp, ứng dụng có thể phản hồi nhanh và dùng ít CPU. Khi tăng tải, throughput thường tăng đến một ngưỡng. Gần giới hạn tài nguyên, queue wait và tail latency có thể tăng mạnh, trong khi throughput cải thiện rất ít hoặc giảm.

~~~text
Latency
   ^
   |                      /
   |                    /
   |                 __/
   |______________--/
   +----------------------------> Offered load
                   vùng gần bão hòa

Throughput
   ^
   |             __________
   |          __/
   |       __/
   |______/
   +----------------------------> Offered load
~~~

Đây là **hình minh họa xu hướng**, không phải đường cong định lượng được bảo đảm cho mọi hệ thống.

Mục tiêu hiệu năng thường nên chọn một **điểm vận hành có headroom**, không phải điểm throughput tối đa ngay trước khi ứng dụng suy sụp.

Ví dụ yêu cầu:

- Tại tải 300 RPS, p99 ≤ 400 ms và success ≥ 99,9%.
- CPU/connection pool còn dự phòng để xử lý đợt tăng tải ngắn.
- Tải vượt ngưỡng được điều tiết hoặc từ chối rõ ràng, không làm hàng đợi kéo dài vô hạn.

## 10. Little's Law: liên hệ concurrency, throughput và latency

Trong hệ thống tương đối ổn định, **Little's Law** cho biết:

\[
L = \lambda \times W
\]

Trong đó:

- **L**: số công việc trung bình đang ở trong hệ thống (*in flight*).
- **λ**: tốc độ hoàn tất/đến trung bình trong trạng thái ổn định, đơn vị công việc/giây.
- **W**: thời gian trung bình mỗi công việc ở trong hệ thống, đơn vị giây.

Ví dụ:

\[
\lambda = 400\ \text{request/s},\quad
W = 0.25\ \text{s}
\]

Khi đó:

\[
L = 400 \times 0.25 = 100
\]

Có khoảng **100 request đang ở trong hệ thống trung bình** ở điều kiện ổn định, theo cùng ranh giới đo.

### Không nhầm số công việc in-flight với số CPU core

Một request chờ mạng vẫn có thể được tính là in-flight dù không chiếm một CPU core để chạy liên tục. Virtual thread cũng không làm công thức trở thành “mỗi request cần một core”.

### Điều kiện áp dụng

Little's Law dùng trên **trung bình và ranh giới đo nhất quán**, khi hệ thống đủ ổn định trong khoảng quan sát. Nếu queue đang tăng vô hạn, arrival rate và completion rate khác nhau, dùng một vài số đo tức thời để suy “capacity” có thể rất sai.

Công thức giúp **kiểm tra tính hợp lý của số liệu**, không tự chứng minh ứng dụng có thể đáp ứng mọi mức concurrency đó.

## 11. Concurrency, parallelism và giới hạn tài nguyên

Hai thuật ngữ không đồng nghĩa:

- **Concurrency:** nhiều công việc đang diễn ra hoặc chờ hoàn thành trong cùng giai đoạn.
- **Parallelism:** nhiều công việc thực sự được CPU hoặc tài nguyên thực hiện đồng thời.

Một ứng dụng Java có thể xử lý 1.000 request đồng thời nhưng chỉ có 8 CPU core; nhiều request chờ database hoặc network.

Các giới hạn đáng chú ý:

- Số CPU core và quota CPU trong container.
- Số connection tới database hoặc hệ thống ngoài.
- Giới hạn request song song của dependency.
- Số file descriptor/socket.
- Dung lượng queue, bộ nhớ giữ task và cache.
- Disk IOPS, throughput thiết bị lưu trữ.
- Bandwidth mạng và giới hạn dịch vụ bên ngoài.

### Virtual thread không xóa các nút thắt cổ chai

Virtual thread là tính năng Java hiện hành giúp biểu diễn nhiều tác vụ chờ theo mô hình thread thuận tiện hơn. Nhưng tăng số virtual thread **không tự tăng CPU, database connection hoặc năng lực downstream**.

Ví dụ nếu connection pool chỉ cho phép 20 truy vấn đang dùng kết nối, tạo thêm 5.000 virtual thread có thể làm tăng số request chờ pool. Cần đo **pool wait time**, queue depth và latency trước khi kết luận “thiếu thread”.

## 12. Đo CPU utilization cho đúng

CPU utilization trả lời phần năng lực CPU được dùng trong một khoảng thời gian. Tuy nhiên, phần trăm CPU chỉ có nghĩa khi biết **mẫu số**:

- Theo một core hay toàn máy?
- Theo container quota hay host?
- Theo process JVM hay toàn bộ hệ thống?
- Theo khoảng thời gian 1 giây, 30 giây hay 5 phút?

Một process dùng 200% CPU theo công cụ tính 100% cho mỗi core có thể đang tiêu thụ tương đương hai core, không nhất thiết là lỗi. Trong môi trường container, CPU quota có thể thấp hơn số core mà host công bố.

### Các tín hiệu liên quan

| Tín hiệu | Có thể gợi ý |
|---|---|
| CPU process cao kéo dài | Tải CPU-bound, vòng lặp bận hoặc nhiều GC/công việc nền |
| CPU thấp nhưng latency cao | Chờ khóa, database, I/O, queue hoặc dependency |
| CPU throttling cao trong container | Bị giới hạn quota CPU |
| CPU tăng đồng thời allocation tăng | Có thể nhiều việc cấp phát/GC, cần đối chiếu JFR |
| CPU cao nhưng throughput không tăng | Có thể gần bão hòa, contention hoặc công việc lặp |

**CPU 100% không tự chứng minh có lỗi**, và CPU 30% không tự chứng minh hệ thống còn 70% capacity. Có thể một dependency đơn lẻ đã bão hòa trong khi CPU ứng dụng vẫn rảnh.

Mục tiêu CPU nên là **guardrail** được diễn giải cùng throughput, latency, error và headroom, thay vì dùng một ngưỡng cố định cho mọi loại hệ thống.

## 13. Heap utilization, allocation rate và GC

Đối với JVM, **heap used** chỉ là một phần của câu chuyện bộ nhớ.

Những đại lượng khác nhau:

- **Heap used:** bộ nhớ heap hiện đang được sử dụng theo số đo tương ứng.
- **Heap committed:** bộ nhớ heap JVM đã dành/commit.
- **Heap max:** giới hạn tối đa của heap theo cấu hình/môi trường.
- **Allocation rate:** lượng bộ nhớ đối tượng được cấp phát trong một đơn vị thời gian.
- **Live set:** dữ liệu vẫn còn sống sau quá trình thu gom thích hợp.
- **GC pause duration:** thời gian các phần công việc ứng dụng bị tạm dừng bởi các pha GC tương ứng.
- **GC CPU/work:** tài nguyên CPU dành cho GC; không chỉ có pause time.

Ví dụ một ứng dụng có heap 4 GiB:

~~~text
Heap max:          4.0 GiB
Heap committed:    3.0 GiB
Heap used hiện tại: 2.2 GiB
~~~

Không được kết luận chương trình **chiếm đúng 2.2 GiB RAM của hệ điều hành**. Process còn có native memory, metaspace, code cache, thread stacks, direct buffers và các cấu trúc JVM khác.

### Allocation rate cao không đồng nghĩa memory leak

Một dịch vụ xử lý nhiều request có thể cấp phát nhiều object ngắn hạn. Chúng được GC thu hồi bình thường. Trong khi đó, một memory leak có thể làm **live set hoặc lượng bộ nhớ giữ lại** tăng dần dù tải đã ổn định.

Khi điều tra:

1. So sánh cùng mức workload.
2. Quan sát bộ nhớ qua nhiều chu kỳ GC.
3. Theo dõi allocation rate và object allocation profile.
4. Kiểm tra queue/cache có tăng không kiểm soát không.
5. Đối chiếu thời điểm spike latency với GC pause và CPU.

Không tối ưu heap bằng cách chỉ nhìn một ảnh chụp số **used** duy nhất.

## 14. GC pause và ngân sách latency

GC có thể góp phần vào tail latency, nhưng **không phải mọi request chậm đều do GC**.

Giả sử mục tiêu p99 end-to-end = 200 ms. Nếu một số request đã mất 170 ms cho queue và database, chỉ còn ít khoảng dự phòng cho xử lý ở JVM, serialization, transport và các sự kiện như GC pause.

Có thể lập một **latency budget** minh họa:

| Thành phần | Mức dự kiến |
|---|---:|
| Gateway/transport | 15 ms |
| Queue wait | 20 ms |
| Application logic | 35 ms |
| Database | 80 ms |
| Serialization/response | 15 ms |
| Dự phòng biến động | 35 ms |
| **Tổng** | **200 ms** |

Bảng chỉ là mô hình lập kế hoạch, không phải chứng minh các thành phần có thể cộng đơn giản trong mọi trường hợp fan-out song song. Phân bố tổng và percentile của từng thành phần không có phép cộng tuyến tính đơn giản.

**Không cộng p99 của từng dependency để suy p99 end-to-end**, và cũng không lấy p99 end-to-end trừ p99 database để suy chính xác “p99 phần còn lại”. Muốn hiểu đường găng, cần timeline/trace và phân tích phân bố thực tế.

### Chọn collector dựa trên đo đạc

Java hiện đại có các GC lựa chọn theo nhu cầu throughput, latency và footprint. Không nên đổi GC dựa vào một lời khuyên chung mà chưa biết workload, heap, CPU quota và mục tiêu. Sử dụng dữ liệu JFR/GC log và phép thử có điều kiện giống nhau để đánh giá.

## 15. Native memory, RSS và giới hạn container

Java process có thể sử dụng bộ nhớ bên ngoài heap cho:

- Direct buffers và các vùng native/off-heap.
- Thread stacks.
- Metaspace và các cấu trúc runtime.
- JIT code cache.
- Thư viện native và bộ nhớ mà thư viện cấp phát.
- Những thành phần nội bộ khác của JVM.

**RSS (resident set size)** phản ánh một khái niệm bộ nhớ vật lý của process theo hệ điều hành; nó không đồng nghĩa với **heap used** và cũng không phải phép cộng đơn giản tất cả những trường JVM công bố.

Ví dụ giả định:

~~~text
Heap used:       1.5 GiB
Heap committed:  2.0 GiB
Direct buffers:  0.3 GiB
Các vùng khác:   biến thiên
Process RSS:     có thể lớn hơn heap used đáng kể
~~~

Một service có thể bị giới hạn bộ nhớ container dù heap chưa chạm **-Xmx**, vì phần non-heap/native cũng tiêu thụ tài nguyên.

### Những mục tiêu tài nguyên cần nêu rõ

- Giới hạn heap (nếu có) và hành vi live set.
- RSS hoặc container working set dưới budget phù hợp.
- Allocation rate hợp lý và không gây GC overhead ngoài mục tiêu.
- Số connection, thread, file descriptor không tăng vô hạn.
- Queue depth và cache có giới hạn hoặc chính sách loại bỏ.

**Không đặt Xmx bằng toàn bộ memory limit của container** rồi bỏ qua native memory và overhead JVM.

## 16. I/O, database pool và contention

Khi latency tăng nhưng CPU không bão hòa, hãy xem **waiting** và **contention**.

Một số điểm chờ:

~~~text
HTTP request
    |
    +--> Chờ hàng đợi executor
    |
    +--> Chờ lấy DB connection
    |
    +--> Chờ database query
    |
    +--> Chờ synchronized lock
    |
    +--> Chờ network call
    |
    +--> Trả response
~~~

Các số liệu hữu ích:

| Vùng | Chỉ số |
|---|---|
| Database pool | Active/idle connections, pending borrowers, wait time |
| HTTP client | Connection acquisition, DNS/connect/TLS/read durations |
| Worker queue | Queue length, enqueue/dequeue rate, wait time, rejection |
| Locking | Contention duration, blocked thread, lock owner |
| Storage | Read/write latency, throughput, IOPS, queue depth |
| Network | Request latency, retries, timeout, error, bytes |
| Downstream API | p95/p99, availability, rate limiting |

Một phép tăng thread chỉ có ích nếu loại concurrency đang thiếu đúng là nút thắt. Nếu nguyên nhân là connection pool nhỏ hoặc database đã hết capacity, tăng thread thường tạo thêm công việc chờ.

## 17. Error rate gắn với mục tiêu hiệu năng

Một hệ thống trả lỗi ngay có thể có latency thấp và throughput hoàn tất cao, nhưng **không đạt mục tiêu dịch vụ**.

Ví dụ:

~~~text
10.000 requests được gửi
9.000 responses là lỗi 503 trong 2 ms
1.000 requests thành công trong 100 ms
~~~

Nếu chỉ tính latency response của tất cả request, số liệu có thể “đẹp” do lỗi trả rất nhanh.

Nên phân tách:

- **Total completed request rate**.
- **Successful request rate**.
- **Error rate theo loại** (4xx, 5xx, timeout, rejection hoặc lỗi nghiệp vụ).
- **Latency của request đạt tiêu chí** và latency end-to-end của toàn bộ request theo định nghĩa SLI.
- **Số request đang chờ** hoặc bị abandon.

Mục tiêu throughput **phải có điều kiện về chất lượng**, chẳng hạn “ít nhất 300 request thành công/giây với p99 ≤ 400 ms và error rate ≤ 0,1%”, thay vì chỉ “trả 300 response/giây”.

Cách phân loại lỗi cần hợp đồng rõ: một lỗi 4xx do người dùng gửi đầu vào không hợp lệ có thể không phản ánh lỗi availability của server, nhưng vẫn cần ghi nhận trong hoạt động và bảo mật.

## 18. Timeout, retry và hiệu ứng khuếch đại tải

Giả sử một yêu cầu cần một lần gọi downstream. Khi downstream chậm, client retry tự động tới ba lần. Với cùng tốc độ request đầu vào, số lần gọi thực tế tới downstream có thể tăng lên đáng kể.

~~~text
Request từ caller
      |
      +-- Attempt 1: timeout
      |
      +-- Attempt 2: timeout
      |
      +-- Attempt 3: success / failure
~~~

Nếu nhiều client cùng retry ngay lập tức, tải có thể tăng trong thời điểm downstream đang yếu, làm tail latency xấu thêm.

Khi đặt SLO và thiết kế thí nghiệm hiệu năng:

1. Ghi rõ retry được bật hay tắt.
2. Đếm **attempt rate** riêng với **logical request rate**.
3. Theo dõi tỷ lệ retry, timeout và bị từ chối.
4. Có deadline tổng, backoff/jitter và giới hạn số attempt.
5. Với thao tác có side effect, yêu cầu cơ chế idempotency phù hợp.
6. Không coi latency của attempt cuối là latency end-to-end của toàn yêu cầu.

**Timeout ở tầng CompletableFuture không tự dừng tác vụ nền**; nếu request đã timeout nhưng tác vụ vẫn giữ connection hoặc CPU, tải thực tế có thể cao hơn số request thành công quan sát được.

## 19. Đặt SLO theo từng loại workload

Không nên trộn các nhóm request có chi phí rất khác nhau rồi dùng một percentile chung để kết luận mọi endpoint đều đạt.

Ví dụ một dịch vụ có:

- **GET /products/{id}**: tra cứu ngắn, tần suất cao.
- **POST /orders**: ghi dữ liệu và xác thực nhiều bước.
- **POST /reports**: tạo báo cáo lớn.

Nếu 95% lưu lượng là tra cứu rất nhanh, p95 toàn dịch vụ có thể che giấu việc **POST /orders** luôn chậm.

Mục tiêu nên được chia theo:

- Endpoint hoặc **request class**.
- Đồng bộ hoặc bất đồng bộ; tác vụ nền có thời gian hoàn thành riêng.
- Payload size hoặc khối lượng dữ liệu.
- Region, tenant hoặc nhóm khách hàng cần quan sát.
- Cache hit/miss.
- Loại kết quả (thành công, timeout, lỗi).
- Môi trường và số instance.

Không cần tạo vô số metric nhãn duy nhất: số lượng label có tính cardinality cao có thể gây tốn RAM và lưu trữ của hệ thống observability. Chọn nhãn có giới hạn, có ý nghĩa.

## 20. Thiết kế mục tiêu chấp nhận theo ma trận tải

Một mức tải trung bình không đủ kiểm tra hành vi khi tăng tải. Có thể thiết kế **load envelope**:

| Kịch bản minh họa | Offered load | Thời gian | Mục tiêu |
|---|---:|---:|---|
| Nhàn rỗi | 5 RPS | 5 phút | Kiểm tra nền và độ ổn định |
| Bình thường | 150 RPS | 15 phút | Đạt latency và success SLO |
| Cao điểm | 300 RPS | 20 phút | Đạt SLO, CPU/heap/queue trong budget |
| Burst ngắn | 600 RPS | 30 giây | Hạn chế quá tải, không sụp đổ; phục hồi nhanh |
| Soak | 200 RPS | 2 giờ | Không tăng tài nguyên không giới hạn |
| Overload | Tăng từng bậc sau ngưỡng | Có kiểm soát | Từ chối/điều tiết rõ ràng, không queue vô hạn |

Những giá trị trên chỉ minh họa cách lập ma trận. Nếu ứng dụng cần xử lý một batch 10 GiB vào ban đêm, chỉ số phù hợp có thể là **MiB/s, thời gian toàn batch và peak memory**, không phải RPS.

### Định nghĩa điều kiện môi trường

Một báo cáo tải nên đính kèm:

- Phiên bản Java/JDK, GC, tùy chọn JVM có ảnh hưởng.
- CPU quota, RAM limit và số instance.
- Kích thước dữ liệu, số record, cache warm/cold.
- Loại database và mức tải của các dependency.
- Cấu hình pool, connection và queue.
- Trạng thái retry, timeout, rate limit và circuit breaker.
- Vị trí load generator và độ trễ mạng.
- Cách tính success, latency và khoảng thời gian đo.

Thiếu bối cảnh, phép so sánh giữa hai lần chạy có thể dẫn tới kết luận sai.

## 21. Đo thời lượng bằng System.nanoTime()

Trong cùng JVM, **System.nanoTime()** là API chuẩn để đo **khoảng thời gian trôi qua**, không phải để tạo timestamp lịch.

~~~java
long start = System.nanoTime();

try {
    performOperation();
} finally {
    long elapsedNanos = System.nanoTime() - start;
    double elapsedMillis = elapsedNanos / 1_000_000.0;

    recordLatency(elapsedMillis);
}
~~~

Đoạn trên giả định các method **performOperation()** và **recordLatency(...)** đã được định nghĩa. Ghi trong **finally** giúp quan sát cả thao tác thành công và thao tác ném ngoại lệ, nhưng vẫn cần ghi thêm trạng thái success/error.

### Không dùng System.currentTimeMillis() để benchmark ngắn

**System.currentTimeMillis()** là thời gian lịch có thể chịu điều chỉnh đồng hồ, nên không phù hợp bằng nanoTime để đo một đoạn ngắn.

**System.nanoTime()** chỉ hữu ích khi lấy **hiệu hai lần đo cùng nguồn**, không thể đổi thẳng thành ngày giờ hoặc so sánh như một timestamp độc lập.

### Tránh phép đo làm thay đổi workload

Nếu ghi log cho mỗi request ngay trong đường xử lý nóng, overhead logging có thể lớn hơn phần code cần đo. Với ứng dụng chạy tải cao, nên dùng metric histogram/aggregation phù hợp và tránh giữ tất cả raw event trong bộ nhớ vô hạn.

Không xem một lần gọi method 100 ns như benchmark chắc chắn: JIT, dead-code elimination, warm-up và độ phân giải đo ảnh hưởng lớn đến microbenchmark. Khi benchmark đoạn code nhỏ, cân nhắc **JMH** ở phần sau.

## 22. Ví dụ Java độc lập: đếm RPS, error rate và percentile

Ví dụ sau minh họa cách lấy chỉ số từ **cùng một cửa sổ đo**. Nó chỉ dùng Java SE và có thể biên dịch bằng JDK hiện đại. Chương trình dùng công việc mô phỏng để kết quả không phụ thuộc database hoặc mạng.

Lưu thành **PerformanceTargetsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public final class PerformanceTargetsDemo {
    private PerformanceTargetsDemo() {}

    private static final class Window {
        private final List<Long> durationsNanos = new ArrayList<>();
        private int errors;

        void record(long durationNanos, boolean success) {
            durationsNanos.add(durationNanos);

            if (!success) {
                errors++;
            }
        }

        int completed() {
            return durationsNanos.size();
        }

        int errors() {
            return errors;
        }

        double errorPercent() {
            if (completed() == 0) {
                return Double.NaN;
            }

            return 100.0 * errors / completed();
        }

        double percentileMillis(double p) {
            if (durationsNanos.isEmpty()) {
                return Double.NaN;
            }

            if (!(p > 0.0 && p <= 1.0)) {
                throw new IllegalArgumentException(
                        "Percentile must be in (0, 1]");
            }

            List<Long> sorted = new ArrayList<>(durationsNanos);
            Collections.sort(sorted);

            int rank = (int) Math.ceil(p * sorted.size());
            long nanos = sorted.get(rank - 1);

            return nanos / 1_000_000.0;
        }
    }

    private static void simulatedRequest(int requestId)
            throws InterruptedException {

        // Chỉ mô phỏng thời gian xử lý, không phải benchmark thực.
        Thread.sleep(2 + (requestId % 5));

        if (requestId % 25 == 0) {
            throw new IllegalStateException("simulated failure");
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        // Warm-up minh họa, không tính vào cửa sổ đo.
        for (int i = 1; i <= 10; i++) {
            simulatedRequest(i);
        }

        Window window = new Window();
        long windowStart = System.nanoTime();

        for (int id = 1; id <= 100; id++) {
            long start = System.nanoTime();
            boolean success = true;

            try {
                simulatedRequest(id);
            } catch (IllegalStateException exception) {
                success = false;
            } finally {
                window.record(System.nanoTime() - start, success);
            }
        }

        long elapsedNanos = System.nanoTime() - windowStart;
        double seconds = elapsedNanos / 1_000_000_000.0;

        double completedRps = window.completed() / seconds;
        double successfulRps =
                (window.completed() - window.errors()) / seconds;

        System.out.printf(
                Locale.ROOT,
                "completed=%d, errors=%d, errorRate=%.2f%%%n",
                window.completed(),
                window.errors(),
                window.errorPercent()
        );

        System.out.printf(
                Locale.ROOT,
                "completedRps=%.1f, successfulRps=%.1f%n",
                completedRps,
                successfulRps
        );

        System.out.printf(
                Locale.ROOT,
                "p50=%.2f ms, p95=%.2f ms, p99=%.2f ms%n",
                window.percentileMillis(0.50),
                window.percentileMillis(0.95),
                window.percentileMillis(0.99)
        );
    }
}
~~~

Biên dịch và chạy:

~~~text
javac PerformanceTargetsDemo.java
java PerformanceTargetsDemo
~~~

Những kết quả cố định theo logic chương trình:

~~~text
completed=100, errors=4, errorRate=4.00%
~~~

**RPS và percentile không có giá trị cố định**, vì phụ thuộc việc thực thi, độ chính xác của sleep, scheduling và tải của máy. Đừng sao chép một số p99 giả định rồi tuyên bố đó là benchmark của JDK 27.

### Điều gì đang được đo?

1. **System.nanoTime()** ghi thời gian bắt đầu và kết thúc cho từng thao tác.
2. **finally** ghi latency ngay cả khi simulatedRequest ném lỗi.
3. **completed()** đếm tất cả lời gọi hoàn tất trong cửa sổ, không chỉ lời gọi thành công.
4. **errors()** đếm đúng bốn request có ID chia hết cho 25.
5. **completedRps** dùng thời gian thực đã trôi qua của cả vòng đo.
6. **successfulRps** loại request lỗi ra khỏi tử số.
7. **percentileMillis()** sắp xếp sample và lấy nearest-rank theo một cách định nghĩa rõ.
8. Warm-up ở ví dụ không bảo đảm JVM đã đạt trạng thái tối ưu; nó chỉ minh họa việc tách giai đoạn đo.

### Giới hạn của ví dụ

- Chỉ một thread, không đo concurrency hoặc queue wait.
- Dữ liệu latency nhỏ và nhân tạo; không đại diện request HTTP thực.
- Giữ toàn bộ sample trong List, không thích hợp cho metric production không giới hạn.
- Không đo CPU, GC, bộ nhớ hay tài nguyên bên ngoài.
- Không mô phỏng open-loop arrival rate hoặc overload.
- Không chứng minh một SLO production đạt yêu cầu.

Đây là **ví dụ về định nghĩa và tính metric**, không phải framework load test.

## 23. Histogram, bucket và rolling window

Một ứng dụng production không thể lưu mọi latency mãi mãi trong một List rồi sort toàn bộ. Công cụ observability thường dùng:

- **Counter:** số request, lỗi, retry, timeout.
- **Gauge:** queue depth, active connections, heap used ở thời điểm lấy mẫu.
- **Histogram:** phân bố latency hoặc kích thước payload theo các bucket.
- **Timer:** đo thời lượng một operation, thường kết hợp count và histogram.
- **Tracing:** đường đi của một request qua các dịch vụ, phù hợp điều tra request chậm cụ thể.

### Ví dụ histogram bucket

~~~text
latency <=  50 ms : 850 requests
latency <= 100 ms : 940 requests
latency <= 200 ms : 980 requests
latency <= 500 ms : 997 requests
latency >  500 ms :   3 requests
Tổng                1000 requests
~~~

Các số trong bảng là một ví dụ về **phân bố số lượng request theo khoảng**, không phải histogram cumulative chuẩn của một sản phẩm monitoring cụ thể. Khi triển khai Prometheus-style cumulative histogram, mỗi bucket chứa số lượng **≤ ngưỡng**, nên phải dùng cách diễn giải tương ứng.

### Cửa sổ thời gian

Số liệu có thể được xem theo:

- 1 phút để phát hiện biến động nhanh.
- 5–15 phút để giảm độ nhiễu ở lượng request trung bình.
- 1 giờ hoặc một kỳ SLO dài để đánh giá xu hướng.
- Khoảng so sánh trước/sau triển khai.

Khi đặt SLO, xác định rõ **window**. Đừng so p99 của 1 phút tải cực thấp với p99 của 30 phút tải cao như hai phép đo tương đương.

### Đừng gộp percentile sai

Hãy tổng hợp **bucket/count/sum hoặc raw samples theo hợp đồng công cụ**, rồi tính quantile, thay vì trung bình p95/p99 từ từng instance. Với histogram bucket, percentile thường là ước lượng phụ thuộc độ rộng bucket.

## 24. JDK Flight Recorder (JFR): quan sát nguyên nhân

**Java Flight Recorder (JFR)** là khả năng ghi sự kiện chẩn đoán tích hợp trong JDK hiện đại. Nó giúp quan sát các hoạt động có thể liên quan đến hiệu năng, chẳng hạn:

- CPU execution samples.
- Garbage collection và pause events.
- Object allocation events.
- Thread scheduling, blocking và lock contention trong phạm vi các event được bật.
- Một số sự kiện I/O và JVM khác tùy phiên bản/cấu hình.
- Sự kiện tùy chỉnh của ứng dụng nếu bạn chủ động instrument bằng API **jdk.jfr**.

JFR **không tự biết “API checkout có p99 latency bao nhiêu”** nếu ứng dụng không có cách gắn request và đo duration tương ứng. Metric cấp endpoint vẫn cần được instrument theo ranh giới phù hợp.

### Bật JFR từ khi khởi động

Một ví dụ dòng lệnh:

~~~text
java -XX:StartFlightRecording=filename=app.jfr,duration=60s,settings=profile -jar app.jar
~~~

Lệnh này tạo một recording trong khoảng đã chỉ định, với cấu hình sự kiện phù hợp profile. Cần thay **app.jar** bằng artifact của ứng dụng thật; đường dẫn recording phải có quyền ghi và dung lượng đĩa đủ.

### Bật JFR cho JVM đang chạy

~~~text
jcmd -l
jcmd <PID> JFR.start name=perf settings=profile duration=60s filename=perf.jfr
~~~

Thay **<PID>** bằng process ID thực tế. Việc attach/chạy diagnostic command phụ thuộc quyền, runtime và cấu hình JVM.

Các event và cấu hình JFR có overhead. Overhead thường đủ phù hợp cho nhiều tình huống chẩn đoán, nhưng **không bằng 0**; hãy cân nhắc profile trong môi trường sản xuất theo chính sách vận hành.

### Java Mission Control

**Java Mission Control (JMC)** là công cụ thường dùng để phân tích bản ghi JFR, quan sát allocation, thread, GC và các vấn đề hiệu năng. Đây là công cụ riêng trong hệ sinh thái Java, không nên mặc định mọi bản JDK đều đóng gói cùng giao diện JMC.

Sử dụng JFR/JMC để **tìm giả thuyết nguyên nhân**, rồi đối chiếu chúng với latency và throughput thực tế của ứng dụng.

## 25. jcmd, JMX và thống kê JVM

Bên cạnh JFR, JDK có **jcmd** để truy vấn một số thông tin chẩn đoán từ tiến trình JVM.

Ví dụ:

~~~text
jcmd -l
jcmd <PID> GC.heap_info
jcmd <PID> Thread.print
jcmd <PID> JFR.check
~~~

Ý nghĩa:

- **GC.heap_info:** thông tin heap theo GC/runtime tương ứng.
- **Thread.print:** thông tin thread phục vụ điều tra các trạng thái chờ, lock và deadlock phù hợp.
- **JFR.check:** kiểm tra trạng thái các JFR recording đang hoạt động.

Tùy phiên bản, quyền truy cập và cấu hình, một số lệnh có thể không sẵn hoặc cần tham số khác. Không tự động thu thập thread dump/JFR hàng loạt trên môi trường nhạy cảm nếu chưa xem xét overhead và dữ liệu có thể chứa thông tin vận hành.

### Native Memory Tracking (NMT)

Nếu cần điều tra bộ nhớ native mà JVM quản lý, có thể bật **Native Memory Tracking** khi khởi động bằng tùy chọn thích hợp, ví dụ:

~~~text
-XX:NativeMemoryTracking=summary
~~~

Sau đó một số thông tin có thể xem bằng:

~~~text
jcmd <PID> VM.native_memory summary
~~~

**NMT cần được bật phù hợp từ thời điểm khởi động và có overhead**, đồng thời không theo dõi đầy đủ mọi cấp phát do mã native bên thứ ba thực hiện. Nó không thay thế metric RSS/container và kiểm tra memory leak ở thư viện ngoài.

### MXBeans

Java cung cấp các MXBean qua **java.lang.management** để đọc một số số liệu runtime bằng code.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

MemoryUsage heap =
        ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();

double usedMiB = heap.getUsed() / 1_048_576.0;

System.out.printf("heapUsedMiB=%.1f%n", usedMiB);
~~~

**MemoryUsage.getUsed()** trả heap used tại lần đọc, không phải toàn bộ RSS hay memory limit của container. Khi xuất metric định kỳ, kết hợp bộ đo từ runtime với metric của hệ điều hành/container và hệ thống phụ thuộc.

## 26. Phân tích dấu hiệu: CPU, GC, lock hay dependency?

Một số kiểu quan sát có thể giúp tạo **giả thuyết**, nhưng không đủ để kết luận chắc chắn:

| Quan sát | Giả thuyết ban đầu | Cần đo tiếp |
|---|---|---|
| CPU tăng, throughput tăng | Hệ thống đang khai thác CPU | p95/p99 và headroom ở tải cao |
| CPU cao, throughput phẳng | CPU-bound hoặc contention | JFR CPU samples, lock profile, GC |
| CPU thấp, p99 cao | I/O/queue/lock chờ | Pool wait, thread states, dependency p99 |
| Heap used tăng liên tục | Cache/backlog hoặc live-set tăng | Heap sau GC, allocation profile, queue/cache sizes |
| GC pause spike trùng request chậm | GC có thể góp phần vào tail | Timeline JFR/trace cùng mốc |
| Error rate tăng khi tăng RPS | Quá tải hoặc giới hạn downstream | Rejections, timeouts, pool, network |
| p50 ổn, p99 xấu dần | Tail amplification/queue/hotspot | Per-endpoint latency, queue time, downstream traces |
| RPS của client cao, successful RPS thấp | Nhiều request lỗi, timeout hoặc bị từ chối | Completion/error classification |
| RSS tăng nhưng heap ổn | Native/off-heap hoặc môi trường | NMT, direct buffer, thread stacks, OS metrics |

**Tương quan không tự chứng minh quan hệ nhân quả.** Ví dụ GC pause và p99 cùng tăng có thể đều bị ảnh hưởng bởi một đợt tải lớn. Chạy thử nghiệm có kiểm soát hoặc phân tích timeline là bước tiếp theo cần thiết.

## 27. Thiết kế bài load test tái lập được

Một bài thử tốt không chỉ tạo nhiều request; nó tái hiện điều kiện người dùng gặp.

### Giai đoạn chuẩn bị

1. Xác định SLO và ngưỡng tài nguyên cần kiểm chứng.
2. Chọn dữ liệu thử có kích thước, phân bố và mức cache hit/miss hợp lý.
3. Thiết lập đúng số instance, CPU/RAM quota và cấu hình dependency.
4. Xác nhận load generator không trở thành nút thắt.
5. Xác định retry, timeout và cơ chế kiểm soát tải.
6. Chuẩn bị metric latency, success, errors, throughput, CPU, GC, memory, queue.
7. Xác định cách khôi phục trạng thái sau thử nghiệm nếu có thao tác ghi.

### Giai đoạn chạy

~~~text
Warm-up ----> Steady state ----> Peak/burst ----> Recovery
   |                |                |             |
   v                v                v             v
JIT/cache        Đo SLO       Đo overload      Đo thời gian
ổn định          bình thường    và backpressure  phục hồi
~~~

- **Warm-up:** tạo đủ hoạt động để JIT compilation, cache và connection pool đạt trạng thái phù hợp.
- **Steady state:** lấy số liệu ổn định dưới mức tải mục tiêu.
- **Peak/burst:** tăng tải có kiểm soát, quan sát vùng bão hòa và chính sách từ chối.
- **Recovery:** giảm tải, quan sát queue, latency và memory có trở lại mức bình thường không.
- **Soak:** chạy lâu hơn để phát hiện tích lũy tài nguyên và các vấn đề chỉ xuất hiện theo thời gian.

Không dùng riêng kết quả của giai đoạn warm-up để phán đoán throughput ổn định.

### Lặp lại và đối chiếu

Mỗi lần chạy cần lưu cấu hình, ngày giờ, commit/build, JDK, mức tải, dataset và các thay đổi môi trường. Khi so sánh hai phương án, giữ biến số không liên quan càng giống nhau càng tốt, lặp lại đủ lần và xem độ biến động.

Một cải thiện 1–2% trong thử nghiệm có noise 10% chưa đủ bằng chứng để kết luận tối ưu hiệu quả.

## 28. Open-loop, closed-loop và coordinated omission

Có hai cách phổ biến để mô hình hóa tải:

- **Closed-loop:** mỗi client/worker gửi request tiếp theo sau khi request trước hoàn tất.
- **Open-loop:** request được lên lịch đến theo tốc độ đầu vào mục tiêu, độc lập tương đối với thời điểm kết thúc request trước.

Closed-loop có thể hữu ích cho một số mô hình người dùng, nhưng khi server chậm đi, tốc độ gửi của client cũng giảm theo. Điều đó có thể làm phép đo **che bớt khoảng thời gian bị chậm hoặc số request đáng lẽ đến**, nếu workload thật có arrival rate độc lập.

### Coordinated omission

Một load generator gửi request kế tiếp **sau khi** request trước hoàn tất có thể bỏ qua những thời điểm mà một client độc lập khác đáng lẽ đã gửi request trong lúc server đang treo/chậm. Kết quả latency có thể bị báo cáo lạc quan.

Khái niệm này thường được gọi là **coordinated omission**. Để phòng tránh:

1. Chọn mô hình tải phản ánh workload thực.
2. Với arrival rate độc lập, cần công cụ lên lịch request theo nhịp đã đặt.
3. Xác định rõ timestamp bắt đầu từ **lúc request dự kiến đến**, **thực sự gửi**, hay **được server nhận**.
4. Đếm request bị bỏ lỡ, bị từ chối hoặc không phát được do load generator quá tải.
5. Không loại thời gian queue khỏi latency end-to-end nếu queue thuộc hành trình request cần đo.

Không phải mọi bài thử đều phải open-loop, nhưng báo cáo cần mô tả mô hình tạo tải và giới hạn của phép đo.

## 29. Microbenchmark với JMH và kiểm thử end-to-end

**JMH (Java Microbenchmark Harness)** là công cụ benchmark trong hệ sinh thái OpenJDK, thường được dùng để đo các thao tác Java nhỏ trong điều kiện có cơ chế warm-up, fork và phương pháp đo phù hợp.

JMH **không phải API tự động có sẵn trong mọi ứng dụng Java SE**. Khi dùng, cần tích hợp dependency/plugin của JMH vào quy trình benchmark và chạy với cấu hình phù hợp.

### Khi nào dùng JMH?

Ví dụ các câu hỏi phù hợp:

- Một phương thức parse dữ liệu nhanh hơn phương thức khác bao nhiêu ở cùng đầu vào?
- Cấu trúc Map nào có chi phí truy cập phù hợp trong một tình huống cụ thể?
- Một cách cấp phát hoặc chuyển đổi dữ liệu ảnh hưởng allocation như thế nào?

Câu hỏi không được trả lời chỉ bằng JMH:

- API checkout có đáp ứng p99 400 ms dưới 500 RPS không?
- Có bị nghẽn database pool khi 200 user đồng thời không?
- Phục hồi sau khi downstream timeout mất bao lâu?

Những câu hỏi đó cần **load test hoặc integration test với hệ thống đầy đủ**.

### Tránh benchmark thủ công một vòng lặp nhỏ

~~~java
// Không nên xem đây là benchmark đáng tin cậy:
long start = System.nanoTime();

for (int i = 0; i < 1_000; i++) {
    calculateSomething();
}

System.out.println(System.nanoTime() - start);
~~~

JIT có thể tối ưu hóa hoặc loại bỏ công việc, hiệu ứng warm-up và môi trường nền có thể chi phối số đo. Nếu thật sự cần microbenchmark, dùng phương pháp thí nghiệm chuyên dụng như JMH và bảo đảm kết quả tính toán không bị tối ưu bỏ ngoài ý muốn.

## 30. Mục tiêu hiệu năng và chi phí vận hành

Tăng throughput bằng cách dùng gấp đôi CPU, gấp ba heap hoặc số instance lớn hơn có thể là quyết định hợp lý, nhưng cần ghi rõ đánh đổi.

Một số thước đo:

- **Requests thành công/giây/instance** tại SLO đã đặt.
- **CPU-seconds/request** cho workload tương đương.
- **Byte allocation/request**.
- **Chi phí hạ tầng trên một triệu request thành công**.
- **Số instance tối thiểu** cần cho peak traffic và headroom.
- **Thời gian recovery** sau một đợt overload hoặc dependency degradation.

Không tối ưu chi phí bằng cách xóa bỏ mọi headroom. Khi traffic tăng bất thường hoặc một instance bị mất, hệ thống vẫn cần khoảng dự phòng để duy trì SLO hoặc từ chối tải có kiểm soát.

### Capacity planning

Có thể ước tính sơ bộ:

\[
Instances_{theoretical} \approx
\frac{\text{target successful RPS}}{\text{measured sustainable RPS per instance}}
\]

Đây **không phải công thức triển khai đủ dùng ngay**: cần tính replication, biến động traffic, vùng lỗi, mất instance, độ trễ mạng, database/shared services và dự phòng. Sustainable RPS phải được đo **trong khi latency/error/resource đạt mục tiêu**, không phải throughput tối đa một lần chạy ngắn.

## 31. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Đặt mục tiêu “nhanh hơn” nhưng không có đơn vị/ngưỡng | Không thể xác minh | Viết SLI/SLO đo được |
| Chỉ báo cáo latency trung bình | Che tail latency | Theo dõi p50, p95, p99 và N |
| Lấy trung bình p99 của nhiều instance | Sai về thống kê | Gộp histogram/raw samples phù hợp |
| Không phân loại endpoint/payload | Dịch vụ nhanh che endpoint chậm | Phân nhóm workload có ý nghĩa |
| Chỉ đo service time, bỏ qua queue | Người dùng vẫn thấy chậm | Đo end-to-end và queue wait |
| Chỉ đo request đã thành công | Bỏ sót timeout/error | Ghi đủ completion và quy tắc SLI |
| Gọi offered RPS là successful throughput | Đánh giá năng lực sai | Tách offered, admitted, completed, successful |
| Thấy CPU thấp thì tăng thread | Nút thắt có thể ở dependency | Đo pool/queue/lock/I/O |
| Thấy heap used cao thì kết luận leak | Nhầm heap usage với live set | Quan sát sau GC và theo thời gian |
| Coi heap used là RSS | Bỏ qua native memory | Theo dõi process/container memory |
| Dùng sleep để “đo sau khi mọi task xong” | Không bảo đảm hoàn tất | Dùng Future/join và đồng bộ phù hợp |
| Đo JIT chưa warm-up rồi so sánh | Bị ảnh hưởng khởi động | Tách warm-up và steady state |
| Load generator bão hòa | Không biết server thực sự đáp ứng gì | Đo trạng thái load generator |
| Dùng closed-loop rồi không chú ý coordinated omission | Có thể báo latency quá đẹp | Xác định arrival model và timestamp |
| Dùng JMH để kết luận p99 của hệ thống | Sai phạm vi thí nghiệm | Load test end-to-end |
| Tối ưu theo một benchmark mà bỏ error rate | Nhanh vì trả lỗi | SLO phải kết hợp chất lượng |
| Tăng tải không giới hạn rồi queue phình to | Latency và memory suy sụp | Backpressure, capacity, rejection |
| Bật nhiều retry khi tải cao | Khuếch đại quá tải | Deadline, backoff, giới hạn attempt |
| Đổi GC/flag JVM không có baseline | Khó biết hiệu quả hay nguyên nhân | Thử nghiệm có kiểm soát và so sánh |
| Chỉ nhìn một snapshot của JVM | Không thấy xu hướng hoặc spike | Time series, JFR và nhiều cửa sổ đo |

## 32. Checklist trước khi kết luận đã đạt mục tiêu

- Đã định nghĩa **người dùng hoặc caller** quan tâm thao tác nào chưa?
- Mỗi SLI có **ranh giới đo, đơn vị, mẫu số và cửa sổ thời gian** rõ chưa?
- Latency có phân biệt **end-to-end, queue wait, service time và dependency latency** không?
- Có theo dõi percentile phù hợp cùng **số lượng mẫu** và error rate không?
- Có tránh trung bình percentile của nhiều node hoặc nhiều cửa sổ không?
- Throughput có tách **offered, admitted, completed và successful** không?
- Mục tiêu latency/throughput có gắn với **mức tải, payload, số instance và cấu hình** không?
- Có đo CPU **theo process/container/quota** phù hợp không?
- Có đo heap used/committed/max, allocation, GC pause và live set khi cần không?
- Có theo dõi RSS/native memory, direct buffers, thread và các tài nguyên ngoài heap không?
- Khi CPU thấp nhưng latency cao, đã kiểm tra lock, queue, database pool, network chưa?
- Có xử lý sự khác biệt giữa **concurrency và parallelism** không?
- Có đo khả năng phục hồi và hành vi khi overload, timeout và retry không?
- Có biết bài test là **open-loop hay closed-loop**, và rủi ro coordinated omission không?
- Load generator có đủ năng lực phát request theo tốc độ yêu cầu không?
- Đã tách **warm-up, steady state, peak, soak và recovery** chưa?
- Có dùng JFR/jcmd/metrics/tracing đúng mục tiêu điều tra không?
- Có tránh xem p99 của một microbenchmark thành SLO end-to-end không?
- Có kiểm thử lặp lại, lưu đầy đủ cấu hình và nhận diện noise không?
- Có kết luận dựa trên **nhiều chỉ số và cùng điều kiện tải**, thay vì chỉ một biểu đồ đẹp không?

## Kết luận

Đặt mục tiêu hiệu năng cho Java 27 cần kết hợp **latency, throughput, error rate và mức sử dụng tài nguyên** trong cùng một ngữ cảnh workload. **p95/p99** giúp nhận diện request chậm, **successful throughput** cho thấy năng lực phục vụ có chất lượng, còn **CPU, heap, GC, native memory, queue và dependency metrics** cho biết hệ thống có đang tiến gần giới hạn hay không.

Một mục tiêu tốt có thể kiểm chứng: **tác vụ nào, ở mức tải nào, trong khoảng thời gian nào, với ngưỡng percentile, error và resource nào**. Đo đúng ranh giới, không cộng hoặc trung bình percentile sai, tách offered load khỏi completed throughput và luôn dành headroom cho tải biến động.

Với **System.nanoTime()**, **JFR**, **jcmd**, **MXBeans**, công cụ load test phù hợp và quy trình thí nghiệm tái lập, nhóm phát triển có thể chuyển từ cảm giác “chương trình nhanh” sang quyết định kỹ thuật dựa trên bằng chứng. Tối ưu hiệu năng chỉ có ý nghĩa khi cải thiện được **mục tiêu nghiệp vụ đã định nghĩa** mà không làm suy giảm độ tin cậy hoặc gây chi phí tài nguyên không kiểm soát.
