# Instance family, machine type và cấu hình máy tùy chỉnh

Khi triển khai máy ảo trên đám mây, lựa chọn “một máy có bao nhiêu CPU và RAM” mới chỉ là bước đầu. Mỗi nhà cung cấp đóng gói CPU, bộ nhớ, mạng, khả năng lưu trữ cục bộ và bộ tăng tốc thành các nhóm phần cứng khác nhau. Chọn đúng nhóm máy và kích thước giúp ứng dụng đạt độ trễ, thông lượng và độ sẵn sàng mong muốn mà không trả tiền cho tài nguyên không sử dụng.

Bài học này phân biệt **instance family**, **machine type** và **cấu hình máy tùy chỉnh**, sau đó trình bày cách chọn cấu hình theo đặc điểm tải, kiểm chứng bằng thử nghiệm và điều chỉnh trong vận hành. Các khái niệm áp dụng cho máy ảo ở nhiều nền tảng đám mây; tên gọi và danh mục cụ thể có thể khác nhau giữa các nhà cung cấp.

## 1. Ba khái niệm cần phân biệt

### Instance family: nhóm máy theo đặc tính phần cứng

Instance family là nhóm cấu hình được thiết kế để phục vụ một kiểu tải nhất định. Các máy trong cùng family thường có định hướng tương tự về tỷ lệ CPU/bộ nhớ, thế hệ bộ xử lý, băng thông mạng hoặc thiết bị lưu trữ.

Ví dụ về các nhóm phổ biến:

- General purpose: cân bằng CPU và RAM cho ứng dụng web, dịch vụ API, máy chủ ứng dụng và cơ sở dữ liệu nhỏ.
- Compute optimized: ưu tiên năng lực xử lý CPU cho xử lý dữ liệu, mã hóa, mô phỏng, tác vụ tính toán và dịch vụ có nhiều phép tính.
- Memory optimized: cung cấp nhiều RAM so với số vCPU cho cache, cơ sở dữ liệu trong bộ nhớ, phân tích dữ liệu và ứng dụng giữ working set lớn.
- Storage optimized: tập trung vào IOPS, thông lượng hoặc dung lượng lưu trữ cục bộ, phù hợp với cơ sở dữ liệu và hệ thống xử lý dữ liệu cần truy cập đĩa nhanh.
- Accelerated computing: bổ sung GPU hoặc bộ tăng tốc chuyên dụng cho đồ họa, huấn luyện và suy luận AI, xử lý song song hoặc tính toán khoa học.
- Burstable: có mức CPU cơ sở và khả năng tăng tốc trong khoảng thời gian nhất định, phù hợp với tải trung bình thấp nhưng thỉnh thoảng tăng đột biến.
- Network optimized: ưu tiên băng thông, số gói tin mỗi giây hoặc độ trễ mạng cho hệ thống phân tán, HPC và dịch vụ truyền dữ liệu lớn.

Các nhãn trên mô tả định hướng, không phải một chuẩn thống nhất. Một family có thể đồng thời có mạng nhanh hoặc ổ đĩa cục bộ; cần đọc thông số của đúng dòng máy và thế hệ cụ thể.

### Machine type hoặc instance size: một cấu hình cụ thể

Machine type là lựa chọn cụ thể bên trong một family hoặc danh mục máy. Nó xác định tập tài nguyên và giới hạn mà máy ảo được cấp, thường gồm:

- Số vCPU và kiến trúc CPU.
- Dung lượng RAM.
- Băng thông mạng tối đa hoặc mức hiệu năng mạng theo kích thước máy.
- Khả năng gắn ổ đĩa, số lượng ổ đĩa, IOPS và thông lượng được hỗ trợ.
- Dung lượng và đặc tính của ổ đĩa cục bộ nếu có.
- Khả năng sử dụng GPU hoặc thiết bị tăng tốc.
- Một số giới hạn theo nền tảng, vùng triển khai hoặc thế hệ phần cứng.

Tên gọi thay đổi theo nhà cung cấp: AWS thường dùng thuật ngữ *instance type*, Azure dùng *VM size*, còn Google Cloud dùng *machine type*. Không nên so sánh hai tên SKU chỉ dựa vào số vCPU; cần so cả CPU platform, RAM, mạng, lưu trữ và giới hạn đi kèm.

### Cấu hình máy tùy chỉnh: tự chọn tỷ lệ tài nguyên trong giới hạn hỗ trợ

Một số nền tảng cho phép chọn số vCPU và dung lượng RAM thay vì chỉ dùng các kích thước dựng sẵn. Ví dụ, một dịch vụ có thể cần 4 vCPU và 24 GiB RAM. Nếu các kích thước có sẵn chỉ gồm 4 vCPU/16 GiB và 8 vCPU/32 GiB, cấu hình tùy chỉnh có thể tránh cấp thừa CPU hoặc thiếu RAM, nếu family và vùng triển khai hỗ trợ tổ hợp đó.

Cấu hình tùy chỉnh vẫn bị giới hạn bởi nền tảng. Nhà cung cấp có thể quy định:

- Những family hoặc thế hệ máy nào hỗ trợ tùy chỉnh.
- Khoảng số vCPU và dung lượng RAM tối thiểu/tối đa.
- Tỷ lệ RAM trên mỗi vCPU hoặc bước tăng RAM hợp lệ.
- Kiến trúc CPU, thiết bị mạng và thiết bị lưu trữ đi kèm.
- Khu vực, vùng sẵn sàng, hệ điều hành hoặc loại giấy phép được hỗ trợ.

Vì vậy, “tùy chỉnh” không có nghĩa là tự do chọn mọi thông số phần cứng. Đây là cách chọn một tổ hợp được nền tảng cho phép.

| Khái niệm | Câu hỏi mà nó trả lời | Ví dụ minh họa |
|---|---|---|
| Instance family | Máy được tối ưu cho kiểu tải nào? | General purpose, compute optimized, memory optimized |
| Machine type / size | Máy cụ thể có bao nhiêu tài nguyên và giới hạn gì? | Một SKU có 4 vCPU, 16 GiB RAM |
| Custom machine configuration | Có thể chọn tỷ lệ CPU/RAM phù hợp hơn không? | 4 vCPU, 24 GiB RAM nếu nền tảng hỗ trợ |

## 2. Chọn family theo đặc điểm tải

Bắt đầu bằng cách xác định tài nguyên nào đang giới hạn ứng dụng. Một ứng dụng có thể cần nhiều CPU nhưng ít RAM; ứng dụng khác có thể ít tính toán nhưng phải giữ hàng chục gigabyte dữ liệu trong bộ nhớ. Cùng một số vCPU không có nghĩa là hai máy có hiệu năng tương đương.

| Family | Đặc điểm thường gặp | Tải phù hợp | Điểm cần kiểm tra |
|---|---|---|---|
| General purpose | CPU và RAM cân bằng | Web/API, máy chủ ứng dụng, môi trường phát triển, cơ sở dữ liệu vừa và nhỏ | Tỷ lệ CPU/RAM, hiệu năng mạng ở kích thước đã chọn |
| Compute optimized | Nhiều năng lực CPU trên mỗi GiB RAM | Xử lý dữ liệu, mã hóa, xử lý ảnh/video, mô phỏng | Thế hệ CPU, hiệu năng đơn luồng/đa luồng, giới hạn CPU |
| Memory optimized | RAM lớn so với số vCPU | Cache, cơ sở dữ liệu trong RAM, phân tích dữ liệu, JVM heap lớn | RAM khả dụng thực tế, băng thông bộ nhớ, giới hạn kết nối mạng |
| Storage optimized | Lưu trữ cục bộ hoặc thông lượng/IOPS cao | Cơ sở dữ liệu, kho dữ liệu tạm, xử lý log và dữ liệu lớn | Loại ổ đĩa, độ bền dữ liệu, IOPS, throughput và độ trễ |
| Accelerated | GPU hoặc bộ tăng tốc | AI/ML, đồ họa, tính toán song song | Loại GPU, VRAM, driver, framework, khả năng chia sẻ GPU và chi phí |
| Burstable | Có mức CPU cơ sở và cơ chế tích lũy/tín dụng CPU | Dịch vụ nhỏ, môi trường thử nghiệm, tải thấp và không liên tục | Mức CPU cơ sở, cơ chế credit, hành vi khi dùng CPU kéo dài |
| Network optimized | Băng thông hoặc khả năng xử lý gói tin cao | Hệ thống phân tán, HPC, dịch vụ truyền dữ liệu | Băng thông hai chiều, PPS, độ trễ, giới hạn theo kích thước |

### Ví dụ theo loại ứng dụng

**Dịch vụ API xử lý yêu cầu thông thường.** Nếu ứng dụng dùng CPU và RAM ở mức tương đối cân bằng, family general purpose là điểm bắt đầu hợp lý. Khi profiling cho thấy CPU thường xuyên là nút thắt trong khi RAM còn dư, hãy thử compute optimized. Nếu heap, cache hoặc working set tăng cao và gây áp lực bộ nhớ, hãy xem xét memory optimized.

**Cơ sở dữ liệu trong bộ nhớ.** Dung lượng RAM và băng thông bộ nhớ có thể quan trọng hơn việc tăng số vCPU. Cần tính cả bộ nhớ cho hệ điều hành, cache, kết nối, tiến trình nền và khoảng dự phòng. Không lấy toàn bộ RAM danh nghĩa làm dung lượng dữ liệu ứng dụng có thể sử dụng.

**Tác vụ xử lý tệp lớn.** Nếu thời gian chủ yếu nằm ở đọc/ghi dữ liệu, tăng vCPU có thể không cải thiện đáng kể. Hãy đo độ trễ và thông lượng lưu trữ, đồng thời kiểm tra mạng nếu dữ liệu nằm trên ổ đĩa mạng hoặc dịch vụ lưu trữ bên ngoài.

**Tác vụ AI.** Chỉ chọn máy có GPU sau khi xác nhận framework và mô hình thực sự dùng được GPU. Kiểm tra VRAM, khả năng tương thích driver, băng thông truyền dữ liệu và thời gian GPU chờ CPU. Một GPU mạnh nhưng thường xuyên chờ dữ liệu có thể không mang lại hiệu quả tương xứng.

## 3. Đọc thông số máy trước khi chọn kích thước

### vCPU không luôn đồng nghĩa với một lõi CPU vật lý

vCPU là đơn vị tài nguyên CPU mà nền tảng cung cấp cho máy ảo. Tùy kiến trúc và cách nhà cung cấp triển khai, một vCPU có thể tương ứng với một luồng phần cứng hoặc một phần năng lực xử lý được lập lịch. Vì vậy, không thể suy ra hiệu năng chỉ từ phép so sánh số vCPU giữa hai family hoặc hai nhà cung cấp.

Khi tải nhạy với CPU, hãy kiểm tra thêm:

- Thế hệ và dòng CPU, xung nhịp và đặc tính tăng tốc.
- Hiệu năng đơn luồng nếu ứng dụng có đoạn xử lý tuần tự.
- Hiệu năng đa luồng nếu tác vụ có thể chạy song song.
- Kiến trúc x86-64 hay Arm và khả năng tương thích của image, thư viện, binary.
- Hiện tượng throttling, thời gian chờ CPU và CPU steal nếu hệ điều hành cung cấp chỉ số này.

Ứng dụng có thể chạy tốt trên ít vCPU thế hệ mới hơn hoặc cần nhiều vCPU hơn khi dùng CPU có đặc tính khác. Benchmark trên đúng loại tải là cách kiểm chứng đáng tin cậy hơn.

### RAM: tính theo working set và mức tăng trưởng

RAM cần đáp ứng working set ở giờ cao điểm, không chỉ mức trung bình. Working set là phần dữ liệu và tiến trình cần nằm trong bộ nhớ để ứng dụng hoạt động ổn định. Khi thiếu RAM, hệ điều hành có thể phải reclaim cache, swap hoặc kết thúc tiến trình do OOM. Những hành vi này thường làm độ trễ tăng mạnh hoặc khiến dịch vụ gián đoạn.

Khi ước lượng RAM, hãy tính:

1. Bộ nhớ của hệ điều hành và agent giám sát/bảo mật.
2. Heap hoặc bộ nhớ của runtime.
3. Cache, buffer và dữ liệu nóng.
4. Bộ nhớ cho các kết nối và yêu cầu đồng thời.
5. Tải nền, tác vụ batch và mức tăng trưởng dự kiến.
6. Khoảng dự phòng để xử lý đỉnh tải và quá trình khởi động lại.

Không áp dụng một tỷ lệ dự phòng cố định cho mọi hệ thống. Dịch vụ có bộ nhớ ổn định, có thể giới hạn cache sẽ khác với JVM, cơ sở dữ liệu hoặc ứng dụng xử lý dữ liệu có working set biến động.

### Mạng: băng thông, PPS và giới hạn theo kích thước máy

Thông số mạng có thể được công bố dưới dạng mức tối đa, mức cơ sở, hoặc hiệu năng thay đổi theo kích thước và điều kiện tải. Cần kiểm tra:

- Băng thông vào và ra, cũng như cách tính tổng băng thông.
- Số gói tin mỗi giây (PPS) và khả năng xử lý nhiều kết nối nhỏ.
- Độ trễ, jitter và tỷ lệ retransmission.
- Giới hạn của card mạng ảo, chế độ tăng tốc mạng và số hàng đợi.
- Lưu lượng liên vùng, liên vùng sẵn sàng hoặc ra Internet có thể phát sinh chi phí riêng.

Nếu ứng dụng có nhiều kết nối nhỏ, PPS và độ trễ có thể quan trọng hơn băng thông tối đa. Nếu truyền tệp lớn, throughput và giới hạn đường truyền thường quan trọng hơn.

### Lưu trữ: phân biệt ổ cục bộ và ổ đĩa bền vững

Một số máy có ổ đĩa SSD/NVMe cục bộ với độ trễ thấp và throughput cao. Tuy nhiên, ổ cục bộ có thể là bộ nhớ tạm gắn với vòng đời máy; dữ liệu có thể mất khi máy bị dừng, thay thế hoặc chuyển sang host khác tùy nền tảng.

Ổ đĩa mạng hoặc dịch vụ block storage thường có đặc tính bền vững và khả năng tách khỏi vòng đời máy, nhưng hiệu năng phụ thuộc loại volume, cấu hình IOPS/throughput, hàng đợi và mạng. Cần phân biệt rõ:

- Dung lượng lưu trữ.
- IOPS (số thao tác vào/ra mỗi giây).
- Throughput (lượng dữ liệu đọc/ghi mỗi giây).
- Độ trễ và độ ổn định của độ trễ.
- Giới hạn tổng hợp giữa máy ảo, volume và đường truyền.

Không đặt dữ liệu duy nhất của hệ thống lên ổ tạm nếu chưa có cơ chế sao chép hoặc khôi phục phù hợp.

### GPU và bộ tăng tốc

Khi workload cần GPU, hãy chọn theo loại phép tính và yêu cầu bộ nhớ thiết bị. Số lượng GPU không đủ để mô tả năng lực: hai GPU có thể khác kiến trúc, VRAM, băng thông bộ nhớ và khả năng hỗ trợ phần mềm.

Kiểm tra tính tương thích giữa GPU, driver, runtime, framework và image triển khai. Đo tỷ lệ sử dụng GPU, bộ nhớ GPU và thời gian chờ dữ liệu. Với tác vụ suy luận, cần đo thông lượng và độ trễ theo kích thước batch và số yêu cầu đồng thời.

## 4. Khi nào nên dùng cấu hình máy tùy chỉnh?

Cấu hình tùy chỉnh hữu ích khi tải có tỷ lệ CPU/RAM đặc thù hoặc khi các kích thước dựng sẵn tạo ra lãng phí rõ rệt.

Giả sử một dịch vụ sau khi đo tải cao điểm cần khoảng 2,8 vCPU và working set RAM 17 GiB. Đội vận hành muốn giữ dự phòng cho tăng trưởng ngắn hạn. Hai lựa chọn dựng sẵn có thể là:

- 4 vCPU, 16 GiB RAM: CPU có thể đủ nhưng RAM quá sát mức working set, dễ phát sinh áp lực bộ nhớ.
- 8 vCPU, 32 GiB RAM: có nhiều RAM nhưng cấp thêm CPU mà ứng dụng chưa chắc sử dụng.

Nếu nền tảng hỗ trợ, cấu hình 4 vCPU và 24 GiB RAM có thể phù hợp hơn. Đây chỉ là cấu hình ứng viên: phải kiểm tra giới hạn family, hiệu năng CPU, mạng, chi phí và kết quả benchmark trước khi đưa vào môi trường thật.

Nên cân nhắc custom configuration khi:

- Ứng dụng cần nhiều RAM nhưng không tận dụng thêm CPU.
- Tải cần CPU tương đối lớn nhưng working set nhỏ.
- Kích thước tùy chỉnh giúp giảm lãng phí mà vẫn đáp ứng SLO.
- Có dữ liệu đo đủ tốt để xác định nhu cầu CPU/RAM.
- Family và vùng triển khai hỗ trợ tổ hợp mong muốn.

Không nên tùy chỉnh chỉ vì muốn có một con số “vừa đẹp”. Nếu nhu cầu thay đổi mạnh theo thời gian, autoscaling hoặc thay đổi số lượng máy có thể hiệu quả hơn việc tạo một máy đơn lẻ rất lớn.

Trước khi chốt, xác minh giới hạn số vCPU, tỷ lệ RAM hợp lệ, vùng sẵn sàng, quota, giấy phép hệ điều hành/phần mềm, khả năng đặt trước dung lượng và tính tương thích với các tính năng như live migration hoặc resize. Giá của cấu hình tùy chỉnh cũng có thể được tính theo quy tắc riêng; cần đối chiếu báo giá thực tế.

## 5. Quy trình chọn family và machine type

### Bước 1: mô tả workload bằng số liệu

Thu thập số liệu ở tải bình thường và giờ cao điểm. Ghi nhận thông lượng yêu cầu, số kết nối đồng thời, độ trễ p50/p95/p99, CPU, RAM, I/O và mạng. Tách tải nền khỏi các đợt batch hoặc tác vụ định kỳ.

Nếu chưa có môi trường thật, tạo tải thử đại diện cho dữ liệu và hành vi người dùng dự kiến. Một bài thử chỉ chạy vài yêu cầu đơn giản thường không phản ánh được tải thực tế.

### Bước 2: xác định ràng buộc và SLO

Làm rõ mục tiêu về độ trễ, thông lượng, tỷ lệ lỗi và thời gian khôi phục. Xác định kiến trúc CPU, hệ điều hành, yêu cầu GPU, vị trí dữ liệu, vùng triển khai và yêu cầu bảo mật. Các ràng buộc này có thể loại bỏ một số family ngay từ đầu.

### Bước 3: chọn family trước, kích thước sau

Chọn family dựa trên tài nguyên đang giới hạn workload. Sau đó chọn một hoặc vài machine type có đủ CPU, RAM, mạng và lưu trữ. Đừng tăng đồng thời mọi tài nguyên nếu chưa biết nút thắt nằm ở đâu.

### Bước 4: benchmark trên cấu hình ứng viên

Chạy cùng một bộ kiểm thử trên các cấu hình. Giữ ổn định phiên bản ứng dụng, dữ liệu, số lượng client và điều kiện mạng. So sánh:

- Thông lượng đạt được tại cùng mức lỗi.
- Độ trễ p95/p99 ở giờ cao điểm.
- CPU và RAM sử dụng, bao gồm thời điểm đỉnh.
- IOPS, throughput và độ trễ lưu trữ.
- Băng thông, PPS, retransmission và packet drop.
- Chi phí trên mỗi đơn vị công việc hoàn thành.

Một cấu hình chỉ được xem là phù hợp khi đáp ứng SLO trong điều kiện tải đại diện và có khoảng dự phòng cần thiết.

### Bước 5: kiểm tra khả năng triển khai và tính sẵn sàng

Xác minh machine type có sẵn ở vùng mong muốn, còn quota và dung lượng cung cấp hay không. Nếu hệ thống yêu cầu độ sẵn sàng cao, triển khai nhiều máy ở các vùng sẵn sàng độc lập, dùng health check và cơ chế thay thế máy lỗi. Kiểm tra autoscaling có thể tạo thêm đúng loại máy khi tải tăng.

Một cấu hình tốt trên giấy vẫn có thể không triển khai được nếu nhà cung cấp hết dung lượng tại vùng đã chọn hoặc quota chưa được cấp.

### Bước 6: tính tổng chi phí

So sánh chi phí theo cùng một khối lượng công việc, không chỉ giá mỗi giờ của một máy. Tổng chi phí có thể bao gồm:

- Thời gian chạy máy và mô hình thanh toán theo nhu cầu, cam kết hoặc spot/preemptible.
- Ổ đĩa, snapshot, IOPS và throughput bổ sung.
- Lưu lượng mạng liên vùng hoặc ra Internet.
- GPU, giấy phép hệ điều hành và phần mềm thương mại.
- Dung lượng dự phòng để bảo đảm sẵn sàng.
- Chi phí vận hành do phải quản lý nhiều máy hoặc xử lý sự cố.

Một máy lớn hơn có thể rẻ hơn trên mỗi đơn vị công việc nếu hoàn thành tác vụ nhanh hơn và cho phép giảm số máy. Ngược lại, máy quá lớn có thể lãng phí khi phần lớn thời gian ở trạng thái nhàn rỗi. Hãy đo chi phí trên mỗi request, mỗi bản ghi, mỗi tác vụ hoặc mỗi giờ xử lý hữu ích.

### Bước 7: theo dõi và điều chỉnh

Sau khi triển khai, theo dõi cùng nhóm chỉ số đã dùng khi benchmark. Khi tải tăng, xác định nên scale up (đổi sang máy lớn hơn), scale out (thêm máy) hay tối ưu ứng dụng. Đặt ngưỡng cảnh báo dựa trên SLO và đặc điểm workload, không dựa duy nhất vào CPU utilization.

Sơ đồ lựa chọn có thể tóm tắt như sau:

~~~mermaid
flowchart TD
    A["Đo workload và SLO"] --> B["Xác định nút thắt: CPU, RAM, mạng, I/O, GPU"]
    B --> C["Chọn instance family phù hợp"]
    C --> D["Chọn machine type hoặc custom configuration"]
    D --> E["Benchmark dưới tải đại diện"]
    E --> F{"Đạt SLO và chi phí mục tiêu?"}
    F -- "Chưa" --> G["Điều chỉnh family, kích thước hoặc ứng dụng"]
    G --> E
    F -- "Đạt" --> H["Kiểm tra quota, vùng và khả năng dự phòng"]
    H --> I["Triển khai, giám sát và rightsize định kỳ"]
~~~

## 6. Ví dụ: chọn máy cho một dịch vụ API

Một nhóm vận hành dịch vụ API có các số liệu sau trong giờ cao điểm:

- CPU sử dụng khoảng 2,8 vCPU ở thời điểm tải lớn.
- Working set RAM khoảng 17 GiB.
- Lưu lượng mạng ở mức vừa phải, không có yêu cầu GPU.
- Dữ liệu chính nằm trên dịch vụ lưu trữ bền vững bên ngoài máy.
- Dịch vụ cần giữ độ trễ p95 trong SLO khi tải tăng.

Nhóm bắt đầu với family general purpose vì tải chưa cho thấy yêu cầu đặc biệt về CPU, bộ nhớ, mạng hoặc GPU. Họ so sánh các kích thước 4 vCPU/16 GiB và 8 vCPU/32 GiB, đồng thời kiểm tra cấu hình tùy chỉnh 4 vCPU/24 GiB nếu nền tảng cho phép.

Kích thước 4 vCPU/16 GiB có nguy cơ thiếu khoảng dự phòng RAM. Kích thước 8 vCPU/32 GiB có thể đáp ứng nhưng cần kiểm chứng liệu CPU bổ sung có tạo ra cải thiện đủ lớn để bù chi phí. Cấu hình 4 vCPU/24 GiB là ứng viên cân bằng hơn về mặt dung lượng, nhưng chỉ được chọn sau khi benchmark xác nhận độ trễ, throughput, mạng và chi phí.

Nhóm tiếp tục chạy thử ở mức tải cao hơn dự kiến, kiểm tra hành vi khi một máy bị thay thế và xác minh autoscaling có thể thêm máy trong vùng triển khai. Nếu CPU trở thành nút thắt khi tăng số yêu cầu đồng thời, nhóm thử family compute optimized. Nếu RAM tăng nhanh do cache hoặc working set, nhóm xem xét memory optimized hoặc điều chỉnh chính sách cache trước khi tăng kích thước máy.

Ví dụ này cho thấy lựa chọn machine type là một giả thuyết kỹ thuật cần được kiểm chứng. Số liệu đo quyết định cấu hình cuối cùng.

## 7. Liên hệ với container và serverless

Với container, instance family và machine type thường được chọn cho các node của cluster. Sau đó scheduler phân bổ container lên node dựa trên CPU request, memory request, limit và tài nguyên còn trống. Chọn node quá nhỏ có thể gây thiếu chỗ lập lịch hoặc memory pressure; chọn node quá lớn có thể làm giảm hiệu quả sử dụng. Cần đánh giá đồng thời kích thước node, mật độ pod, mức overcommit và khả năng scale node pool.

Với serverless, người dùng thường không chọn trực tiếp instance family hay machine type. Nền tảng quản lý phần cứng bên dưới; người dùng cấu hình các tham số như memory, CPU nếu được hỗ trợ, thời gian chạy, concurrency và giới hạn scale. Dù không chọn SKU máy, nguyên tắc đo workload, xác định SLO và tối ưu chi phí trên mỗi đơn vị công việc vẫn áp dụng.

Khi chuyển một dịch vụ từ VM sang container hoặc serverless, không nên sao chép nguyên xi cấu hình CPU/RAM của máy cũ. Hãy đo lại mức sử dụng thực tế và hiểu cách nền tảng mới cấp phát tài nguyên.

## 8. Theo dõi hiệu năng sau triển khai

Bảng dưới đây liên kết triệu chứng với nhóm thông số cần kiểm tra. Một chỉ số đơn lẻ hiếm khi đủ để kết luận phải đổi family.

| Triệu chứng | Chỉ số cần xem | Hướng điều tra |
|---|---|---|
| Độ trễ tăng khi nhiều request chạy đồng thời | CPU utilization, run queue, CPU throttling, p95/p99 | Xác định thiếu CPU, đoạn xử lý tuần tự hoặc giới hạn concurrency |
| Tiến trình bị OOM hoặc restart | RSS, working set, page fault, swap, OOM event | Kiểm tra heap, cache, leak và dung lượng RAM |
| Đọc/ghi chậm | IOPS, throughput, latency, queue depth | Phân biệt giới hạn volume, máy ảo và đường truyền |
| Truyền dữ liệu chậm | Throughput, PPS, retransmission, packet drop | Kiểm tra giới hạn mạng, kích thước gói và vị trí dữ liệu |
| GPU sử dụng thấp | GPU utilization, VRAM, thời gian chờ CPU/I/O | Kiểm tra pipeline dữ liệu, batch size, driver và khả năng tận dụng GPU |
| Chi phí cao nhưng máy thường nhàn rỗi | Mức sử dụng theo thời gian, request/tác vụ hoàn thành, chi phí theo đơn vị công việc | Right-size, autoscaling hoặc cân nhắc mô hình thanh toán khác |

Trên Linux, một số lệnh có thể hỗ trợ kiểm tra nhanh trong máy ảo:

~~~sh
lscpu
free -h
vmstat 1
iostat -xz 1
ip -s link
~~~

**iostat** thường được cung cấp bởi gói sysstat; chỉ số và công cụ có thể khác theo bản phân phối. Kết quả trong máy khách cũng cần được đối chiếu với metric do nền tảng đám mây cung cấp, vì máy ảo không phải lúc nào cũng nhìn thấy toàn bộ giới hạn ở lớp hạ tầng.

Nên theo dõi xu hướng theo giờ, ngày và chu kỳ nghiệp vụ. Một máy có CPU thấp trong phần lớn thời gian vẫn có thể cần dự phòng nếu có đỉnh tải ngắn nhưng quan trọng. Ngược lại, nếu CPU, RAM và I/O đều thấp trong thời gian dài, hãy đánh giá giảm kích thước hoặc scale theo tải.

## 9. Các lỗi lựa chọn thường gặp

1. **Chọn máy chỉ theo số vCPU.** Hai máy có cùng vCPU có thể khác CPU platform, RAM, mạng và hiệu năng lưu trữ.
2. **Coi vCPU là lõi vật lý.** Cách ánh xạ vCPU phụ thuộc nền tảng và kiến trúc; cần benchmark ứng dụng thật.
3. **Dùng burstable cho tải CPU cao liên tục.** Khi vượt mức cơ sở hoặc cạn credit, hiệu năng có thể giảm theo chính sách của nhà cung cấp.
4. **Bỏ qua RAM ở giờ cao điểm.** RAM trung bình thấp không bảo đảm máy đủ bộ nhớ khi có batch, cache tăng hoặc nhiều kết nối đồng thời.
5. **Chỉ nhìn băng thông mạng tối đa.** PPS, độ trễ, packet drop và giới hạn theo kích thước máy có thể mới là nút thắt.
6. **Nhầm ổ cục bộ với lưu trữ bền vững.** Cần hiểu rõ dữ liệu có tồn tại sau khi máy dừng hoặc bị thay thế hay không.
7. **Chọn GPU trước khi kiểm tra phần mềm.** Driver hoặc framework không tương thích có thể khiến GPU không được sử dụng.
8. **Cấp máy quá lớn để dự phòng mọi tình huống.** Dự phòng nên dựa trên số liệu và chiến lược scale, vì tài nguyên nhàn rỗi vẫn phát sinh chi phí.
9. **Bỏ qua quota và dung lượng vùng.** SKU có thể không khả dụng ở vùng cần triển khai hoặc chưa được cấp đủ quota.
10. **Không đo lại sau khi thay đổi ứng dụng.** Một bản phát hành mới, thay đổi dữ liệu hoặc tăng concurrency có thể làm profile tài nguyên thay đổi đáng kể.

## 10. Checklist trước khi chốt cấu hình

- [ ] Đã đo CPU, RAM, mạng và I/O ở tải đại diện, bao gồm giờ cao điểm.
- [ ] Đã xác định tài nguyên đang giới hạn SLO.
- [ ] Đã chọn family theo đặc tính workload.
- [ ] Đã kiểm tra vCPU, kiến trúc CPU, thế hệ phần cứng và khả năng tương thích.
- [ ] Đã tính RAM cho ứng dụng, hệ điều hành, cache và khoảng dự phòng.
- [ ] Đã xác minh băng thông, PPS, IOPS, throughput và độ trễ cần thiết.
- [ ] Đã xác định ổ đĩa cục bộ có phải dữ liệu tạm hay không.
- [ ] Đã kiểm tra GPU/driver/framework nếu workload cần bộ tăng tốc.
- [ ] Đã xác nhận SKU hoặc cấu hình tùy chỉnh có sẵn ở vùng triển khai và đủ quota.
- [ ] Đã benchmark và so sánh chi phí trên mỗi đơn vị công việc.
- [ ] Đã có kế hoạch autoscaling, thay thế máy lỗi, giám sát và rightsize.

## Kết luận

Instance family giúp chọn đúng định hướng phần cứng; machine type xác định cấu hình tài nguyên cụ thể; custom machine configuration điều chỉnh tỷ lệ CPU/RAM trong giới hạn nền tảng. Quy trình đáng tin cậy là đo workload, xác định SLO, chọn family, thử một số kích thước, xác minh khả năng triển khai và theo dõi sau khi phát hành. Khi lựa chọn dựa trên số liệu CPU, bộ nhớ, mạng, lưu trữ và chi phí thực tế, hệ thống có cơ hội đạt hiệu năng ổn định với mức đầu tư phù hợp.
