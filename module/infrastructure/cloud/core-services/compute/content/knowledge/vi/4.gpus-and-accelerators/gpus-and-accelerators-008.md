# Lựa chọn máy tăng tốc theo hiệu năng, chi phí và khả năng cấp phát

Trong môi trường điện toán đám mây, GPU và các bộ tăng tốc chuyên dụng có thể rút ngắn đáng kể thời gian huấn luyện mô hình, xử lý dữ liệu song song, dựng hình hoặc phục vụ suy luận. Tuy nhiên, thiết bị có thông số tính toán cao nhất chưa chắc là lựa chọn phù hợp nhất. Một máy tăng tốc chỉ tạo ra giá trị khi nó xử lý được đúng loại công việc, có đủ bộ nhớ, tương thích với phần mềm, đáp ứng thời gian xử lý yêu cầu và có thể được cấp phát ổn định với chi phí chấp nhận được.

Bài học này trình bày cách đánh giá máy tăng tốc dựa trên ba nhóm tiêu chí: hiệu năng thực tế, tổng chi phí và khả năng cấp phát. Các tiêu chí được xem xét cùng CPU, RAM, mạng, lưu trữ và cách triển khai trên đám mây để tránh lựa chọn một GPU mạnh nhưng toàn hệ thống vẫn hoạt động chậm hoặc tốn kém.

Sau bài học, bạn có thể:

- Phân tích đặc điểm tải để xác định loại bộ tăng tốc phù hợp.
- Đọc và so sánh các thông số quan trọng như năng lực tính toán, dung lượng bộ nhớ, băng thông bộ nhớ và kết nối liên thiết bị.
- Ước tính chi phí theo đơn vị công việc hoàn thành thay vì chỉ nhìn giá thuê theo giờ.
- Đánh giá quota, vùng triển khai, nguồn cung và các hình thức cấp phát.
- Thiết kế một phép thử thực tế để chọn cấu hình có hiệu quả tốt nhất.

## 1. Bắt đầu từ đặc điểm của công việc

Trước khi xem tên GPU hoặc bảng giá của nhà cung cấp, hãy mô tả công việc cần chạy. Cùng một bộ tăng tốc có thể rất hiệu quả với một tác vụ nhưng kém phù hợp với tác vụ khác.

### Huấn luyện và suy luận có mục tiêu khác nhau

**Huấn luyện (training)** thường thực hiện nhiều phép tính trên tập dữ liệu lớn, lưu trạng thái trung gian và cập nhật tham số lặp đi lặp lại. Ngoài bộ nhớ chứa trọng số, hệ thống còn cần chỗ cho gradient, trạng thái bộ tối ưu hóa, activation và dữ liệu theo batch. Huấn luyện mô hình lớn có thể cần nhiều GPU và kết nối tốc độ cao giữa chúng.

**Suy luận (inference)** dùng mô hình đã huấn luyện để tạo dự đoán hoặc phản hồi. Khi phục vụ trực tuyến, độ trễ của từng yêu cầu và khả năng xử lý đồng thời thường quan trọng. Với mô hình ngôn ngữ, dung lượng bộ nhớ còn phải tính đến KV cache, độ dài ngữ cảnh và số phiên đang hoạt động. Với suy luận theo lô, thông lượng tổng thể có thể quan trọng hơn độ trễ của một yêu cầu riêng lẻ.

| Đặc điểm tải | Chỉ số cần ưu tiên | Hệ quả khi chọn thiết bị |
|---|---|---|
| Huấn luyện mô hình lớn | Thời gian hoàn thành, bộ nhớ, khả năng mở rộng nhiều GPU | Cần bộ nhớ đủ lớn và kết nối liên GPU tốt |
| Suy luận tương tác | Độ trễ p95/p99, thông lượng khi có tải đồng thời | Cần cân bằng tốc độ, bộ nhớ và khả năng gom batch |
| Suy luận theo lô | Số mẫu hoặc token xử lý mỗi giây, chi phí mỗi đơn vị | Có thể ưu tiên thông lượng và khả năng chạy batch lớn |
| Phân tích khoa học/HPC | Độ chính xác số học, băng thông và kiểu phép toán | Cần kiểm tra hỗ trợ FP64, FP32 hoặc kiểu số chuyên biệt |
| Xử lý video, ảnh, dựng hình | Tốc độ giải mã, mã hóa, xử lý tensor hoặc dựng hình | Cần kiểm tra bộ mã hóa/giải mã và thư viện chuyên dụng |
| Tác vụ nhỏ, ít song song | Thời gian khởi động, chi phí nền và độ phức tạp vận hành | CPU hoặc dịch vụ suy luận được quản lý có thể đã đủ |

Hãy ghi rõ quy mô dữ liệu, kích thước mô hình, batch size, độ dài đầu vào, số yêu cầu đồng thời, thời gian chạy dự kiến và mục tiêu chất lượng dịch vụ (SLO). Những thông tin này tạo thành bộ tiêu chí để lọc cấu hình.

### Chọn đúng loại bộ tăng tốc

- **GPU** có khả năng xử lý song song rộng, hệ sinh thái phần mềm phong phú và phù hợp với nhiều tác vụ AI, đồ họa và tính toán khoa học. Các thế hệ GPU khác nhau có dung lượng bộ nhớ, kiểu số được tăng tốc và kết nối khác nhau.
- **TPU hoặc ASIC chuyên dụng** được thiết kế cho một nhóm phép toán hoặc mô hình công việc cụ thể. Chúng có thể đạt thông lượng và hiệu quả năng lượng tốt, nhưng cần kiểm tra khả năng tương thích của framework, toán tử và quy trình triển khai.
- **FPGA** có thể cấu hình lại phần cứng cho pipeline riêng, hữu ích trong một số tác vụ có yêu cầu độ trễ hoặc mức tiêu thụ năng lượng đặc thù. Đổi lại, quá trình phát triển và tối ưu thường phức tạp hơn.
- **CPU** vẫn phù hợp với tác vụ ít song song, xử lý điều phối, tiền xử lý dữ liệu hoặc mô hình nhỏ. Không nên trả chi phí cho GPU nếu phần lớn thời gian chạy không sử dụng được năng lực song song của nó.

Tên gọi của thiết bị không đủ để kết luận. Hãy kiểm tra kiến trúc, phiên bản phần cứng, bộ nhớ, thư viện được hỗ trợ và cách nhà cung cấp đóng gói thiết bị vào loại máy ảo hoặc dịch vụ cụ thể.

## 2. Đánh giá hiệu năng thực tế

Thông số quảng cáo thường mô tả năng lực tối đa trong điều kiện lý tưởng. Hiệu năng mà ứng dụng nhận được còn phụ thuộc kiểu phép toán, độ chính xác, kích thước batch, dữ liệu đầu vào, phần mềm và khả năng cấp dữ liệu cho bộ tăng tốc.

### Năng lực tính toán và độ chính xác số học

Các bộ tăng tốc có thể hỗ trợ nhiều định dạng số:

| Định dạng | Đặc điểm thường gặp | Trường hợp sử dụng |
|---|---|---|
| FP64 | Độ chính xác kép, chi phí tính toán và bộ nhớ cao hơn | Mô phỏng khoa học hoặc phép tính cần độ chính xác kép |
| FP32 | Độ chính xác đơn, hỗ trợ rộng | Tính toán tổng quát và một số quy trình huấn luyện |
| TF32 | Định dạng tính toán được một số GPU hỗ trợ để tăng tốc phép toán ma trận với độ chính xác tích lũy phù hợp | Huấn luyện deep learning khi framework và phần cứng hỗ trợ |
| BF16/FP16 | Định dạng 16 bit giúp giảm dung lượng và tăng tốc phép toán ma trận | Huấn luyện và suy luận deep learning có kiểm soát độ chính xác |
| FP8 | Định dạng 8 bit được một số phần cứng và phần mềm mới hỗ trợ | Mô hình lớn khi quy trình đã được kiểm chứng về độ chính xác |
| INT8 và các dạng lượng tử hóa thấp hơn | Biểu diễn số nguyên hoặc số bit thấp để giảm bộ nhớ và tăng thông lượng | Suy luận khi chất lượng mô hình sau lượng tử hóa đáp ứng yêu cầu |

Không phải thiết bị nào cũng hỗ trợ mọi định dạng, và tên gọi giống nhau không bảo đảm hiệu năng giống nhau. Khi so sánh, hãy dùng cùng mô hình, cùng kiểu số và cùng thiết lập phần mềm. Đo cả chất lượng đầu ra; tăng tốc bằng định dạng số thấp hơn chỉ có ý nghĩa khi sai số vẫn nằm trong giới hạn chấp nhận được.

### Dung lượng và băng thông bộ nhớ

Hai thông số này thường quyết định liệu mô hình có chạy được và chạy nhanh hay không:

- **Dung lượng bộ nhớ thiết bị** (thường là VRAM trên GPU) giới hạn lượng trọng số, activation, gradient, cache và dữ liệu có thể lưu đồng thời.
- **Băng thông bộ nhớ** cho biết tốc độ truyền dữ liệu giữa bộ nhớ và bộ xử lý. Tác vụ phải đọc/ghi nhiều dữ liệu có thể bị giới hạn bởi băng thông dù năng lực tính toán lý thuyết còn dư.

Khi ước tính bộ nhớ cho mô hình, cần tính ít nhất:

1. Trọng số mô hình. Ví dụ, 7 tỷ tham số ở dạng FP16 cần khoảng 14 GB chỉ cho trọng số (chưa tính phần phụ trợ và khác biệt đơn vị GB/GiB).
2. Activation và gradient trong huấn luyện.
3. Trạng thái của bộ tối ưu hóa, chẳng hạn các biến tích lũy của Adam.
4. KV cache trong suy luận mô hình ngôn ngữ, phụ thuộc độ dài ngữ cảnh, số phiên đồng thời và cấu trúc mô hình.
5. Bộ nhớ dành cho runtime, workspace của thư viện, batch và phần dự phòng để tránh hết bộ nhớ.

Vì vậy, một GPU có 16 GB bộ nhớ có thể không đủ cho mô hình có 14 GB trọng số FP16 khi cần thêm cache và vùng làm việc. Lượng tử hóa có thể giảm bộ nhớ trọng số, nhưng không loại bỏ nhu cầu dành chỗ cho KV cache, batch và runtime. Luôn đo mức sử dụng bộ nhớ với cấu hình thực tế.

### Kết nối giữa các bộ tăng tốc

Với công việc phân tán trên nhiều GPU, thời gian truyền dữ liệu giữa thiết bị có thể trở thành nút thắt. Hãy kiểm tra:

- Kết nối trong máy như PCIe, NVLink hoặc fabric chuyên dụng mà nền tảng cung cấp.
- Topology: các GPU có kết nối trực tiếp hay phải đi qua nhiều tầng chuyển mạch.
- Mạng giữa các máy, chẳng hạn Ethernet tốc độ cao, RoCE hoặc InfiniBand.
- Hỗ trợ RDMA và thư viện truyền thông mà framework sử dụng.

Nếu mô hình dùng tensor parallelism hoặc thường xuyên trao đổi gradient, băng thông và độ trễ liên kết có thể quan trọng ngang với tốc độ tính toán của GPU. Với một tác vụ độc lập trên một GPU, chi phí cho cụm nhiều GPU và mạng tốc độ cao có thể không mang lại lợi ích tương xứng.

### Toàn bộ cấu hình máy đều ảnh hưởng đến kết quả

Máy tăng tốc trên đám mây thường được cấp phát cùng CPU, RAM hệ thống, ổ đĩa và băng thông mạng. CPU yếu hoặc thiếu RAM có thể làm chậm tiền xử lý và nạp dữ liệu; lưu trữ chậm có thể khiến GPU phải chờ; mạng yếu có thể kéo dài thời gian đọc dữ liệu hoặc đồng bộ giữa máy. Vì thế, hãy đánh giá cấu hình máy hoàn chỉnh, không chỉ thông số của GPU.

## 3. Tính chi phí theo công việc hoàn thành

Giá thuê theo giờ dễ so sánh nhưng không phản ánh trực tiếp hiệu quả kinh tế. Thiết bị đắt hơn mỗi giờ vẫn có thể rẻ hơn nếu hoàn thành cùng một khối lượng công việc nhanh hơn đủ nhiều.

Một phép tính cơ bản là:

**Chi phí cho một đơn vị công việc = Giá thuê mỗi giờ / Số đơn vị công việc hoàn thành mỗi giờ**

Ví dụ minh họa với hai cấu hình suy luận có cùng chất lượng đầu ra:

| Cấu hình | Giá giả định | Thông lượng đo được | Chi phí cho 1 triệu token |
|---|---:|---:|---:|
| A | 2 USD/giờ | 1.000 token/giây | Khoảng 0,56 USD |
| B | 3 USD/giờ | 2.000 token/giây | Khoảng 0,42 USD |

Trong ví dụ này, cấu hình B có giá thuê theo giờ cao hơn nhưng tạo ra gấp đôi thông lượng, nên chi phí trên một triệu token thấp hơn. Đây chỉ là số liệu giả định để minh họa cách tính; khi áp dụng cần dùng thông lượng đo được ở tải, batch size và chất lượng dịch vụ thực tế.

Với huấn luyện, đơn vị so sánh có thể là chi phí cho một epoch, một triệu mẫu, một lần chạy thí nghiệm hoặc một mô hình đạt ngưỡng chất lượng đã định. Nếu hai cấu hình hội tụ khác nhau, hãy so sánh chi phí để đạt cùng chất lượng, không chỉ thời gian của một bước huấn luyện.

### Tính tổng chi phí sở hữu

Ngoài tiền thuê bộ tăng tốc, hãy đưa các khoản sau vào phép tính:

- CPU, RAM, ổ đĩa, snapshot và lưu trữ dữ liệu đầu vào/đầu ra.
- Lưu lượng mạng giữa các vùng hoặc giữa nhà cung cấp, phí truyền dữ liệu ra ngoài nếu có.
- Thời gian máy nhàn rỗi trong lúc khởi động, nạp mô hình, chờ dữ liệu hoặc chờ người dùng.
- Chi phí điều phối cụm, dịch vụ quản lý, giấy phép phần mềm và quan sát hệ thống.
- Công sức vận hành, tối ưu và xử lý gián đoạn.

Một GPU mạnh nhưng thường xuyên nhàn rỗi có thể có chi phí thực tế cao. Với tải không đều, khả năng tự động mở rộng và tắt tài nguyên khi không dùng có thể quan trọng hơn việc chọn thiết bị có hiệu năng đỉnh cao nhất.

## 4. Đánh giá khả năng cấp phát

Trong môi trường đám mây, một loại GPU xuất hiện trong danh mục dịch vụ không có nghĩa là luôn có thể tạo máy ngay tại mọi vùng hoặc mọi thời điểm. Khả năng cấp phát cần được kiểm tra sớm, nhất là khi có lịch huấn luyện hoặc thời hạn triển khai.

### Những yếu tố cần kiểm tra

- **Vùng và khu vực khả dụng:** loại máy có thể chỉ được cung cấp ở một số region hoặc zone. Việc chuyển vùng có thể làm thay đổi độ trễ tới dữ liệu, người dùng và các dịch vụ phụ thuộc.
- **Quota và giới hạn tài khoản:** nhà cung cấp có thể giới hạn số GPU, số máy hoặc tổng vCPU được phép sử dụng. Quota có thể cần được yêu cầu tăng trước.
- **Nguồn cung tức thời:** ngay cả khi quota còn, năng lực vật lý tại vùng được chọn có thể tạm thời không đủ.
- **Hình thức cấp phát:** on-demand thường linh hoạt; reserved hoặc capacity reservation giúp giữ năng lực cho nhu cầu dự đoán được; spot/preemptible thường rẻ hơn nhưng có thể bị thu hồi.
- **Thời gian khởi tạo:** tạo máy, tải image, cài driver, tải mô hình và khởi động dịch vụ đều ảnh hưởng thời gian sẵn sàng.
- **Khả năng thay thế:** cần biết có thể chuyển sang thế hệ GPU khác, vùng khác hoặc cấu hình nhỏ hơn mà không phải thay đổi lớn ứng dụng hay không.

Nếu công việc có thể bị gián đoạn, spot/preemptible là một lựa chọn tiết kiệm. Hãy lưu checkpoint định kỳ, thiết kế khả năng khởi động lại và đo chi phí của thời gian bị mất. Với dịch vụ có SLO nghiêm ngặt hoặc phiên huấn luyện dài khó khôi phục, nên ưu tiên nguồn cấp phát ổn định hoặc giữ trước dung lượng cần thiết.

### Tính tương thích phần mềm

Trước khi chọn máy, xác nhận phiên bản driver, runtime tăng tốc, thư viện toán học, framework và container image tương thích với phần cứng. Một cấu hình có sẵn nhưng không hỗ trợ phiên bản thư viện mà ứng dụng cần có thể làm tăng đáng kể thời gian triển khai. Với dịch vụ được quản lý, cần kiểm tra giới hạn phiên bản framework, loại mô hình và các toán tử được hỗ trợ.

## 5. Quy trình chọn cấu hình

Có thể áp dụng quy trình sau cho một dự án mới hoặc khi cần thay đổi loại máy:

1. **Mô tả tải và SLO.** Ghi rõ loại công việc, dữ liệu, mô hình, thông lượng mục tiêu, độ trễ, thời gian hoàn thành và mức gián đoạn có thể chấp nhận.
2. **Lọc theo bộ nhớ và phần mềm.** Loại các cấu hình không đủ bộ nhớ hoặc không hỗ trợ framework, định dạng số và thư viện cần dùng.
3. **Kiểm tra cấp phát.** Xác minh region, quota, nguồn cung, giới hạn số lượng và hình thức thuê phù hợp.
4. **Benchmark trên tải đại diện.** Chạy cùng ứng dụng và dữ liệu trên các cấu hình ứng viên; đo độ trễ, thông lượng, bộ nhớ và mức sử dụng thiết bị.
5. **Tính chi phí theo đơn vị công việc.** Bao gồm tài nguyên phụ trợ và thời gian nhàn rỗi; kiểm tra cả trường hợp tải trung bình và tải đỉnh.
6. **Thử nghiệm khả năng mở rộng và phục hồi.** Kiểm tra khi tăng số yêu cầu, thêm GPU, chuyển vùng hoặc bị thu hồi máy nếu dùng spot.
7. **Chọn phương án và theo dõi.** Triển khai cấu hình đáp ứng SLO với chi phí phù hợp; tiếp tục theo dõi để điều chỉnh khi mô hình hoặc tải thay đổi.

Sơ đồ quyết định rút gọn:

~~~mermaid
flowchart TD
    A["Mô tả workload và SLO"] --> B["Đủ bộ nhớ và tương thích phần mềm?"]
    B -- "Không" --> C["Đổi kiểu số, lượng tử hóa hoặc cấu hình"]
    C --> B
    B -- "Có" --> D["Có quota và nguồn cấp phát?"]
    D -- "Không" --> E["Xin quota, đổi vùng hoặc chọn phương án dự phòng"]
    E --> D
    D -- "Có" --> F["Benchmark trên tải thực tế"]
    F --> G["Đạt SLO và chi phí/đơn vị phù hợp?"]
    G -- "Không" --> H["Điều chỉnh batch, phần mềm hoặc cấu hình"]
    H --> F
    G -- "Có" --> I["Triển khai và theo dõi"]
~~~

### Bảng gợi ý ban đầu

Bảng sau giúp tạo danh sách ứng viên; quyết định cuối cùng vẫn phải dựa trên benchmark và điều kiện cấp phát thực tế.

| Loại công việc | Hướng lựa chọn ban đầu | Cần xác minh |
|---|---|---|
| Suy luận mô hình nhỏ, tải thấp | CPU hoặc GPU dung lượng vừa | Độ trễ, chi phí nền và mức sử dụng thực tế |
| Suy luận mô hình lớn | GPU có đủ bộ nhớ; cân nhắc nhiều GPU nếu mô hình không vừa một thiết bị | Trọng số, KV cache, độ dài ngữ cảnh và số phiên đồng thời |
| Huấn luyện deep learning | GPU hỗ trợ kiểu số phù hợp và có hệ sinh thái framework cần thiết | Bộ nhớ cho trạng thái huấn luyện, thời gian hội tụ và kết nối liên GPU |
| HPC cần độ chính xác kép | GPU hoặc bộ tăng tốc có hiệu năng FP64 phù hợp | Tính đúng đắn số học, thư viện khoa học và hiệu năng FP64 thực |
| Pipeline video hoặc đồ họa | GPU có bộ mã hóa/giải mã hoặc khả năng dựng hình phù hợp | Codec, độ phân giải, số luồng và hỗ trợ phần mềm |
| Tác vụ ổn định, chuyên biệt | Cân nhắc ASIC, TPU hoặc FPGA | Khả năng chuyển đổi mã, giới hạn toán tử và chi phí phát triển |

## 6. Thiết kế benchmark có thể tin cậy

Benchmark chỉ hữu ích khi phản ánh cách ứng dụng sẽ chạy trong thực tế. Một bài thử quá nhỏ, chỉ đo vài giây hoặc dùng batch không giống môi trường sản xuất có thể dẫn đến lựa chọn sai.

Khi so sánh, hãy giữ các điều kiện chính giống nhau:

- Cùng phiên bản mô hình, dữ liệu, mã ứng dụng và thư viện.
- Cùng kiểu số, kích thước batch, độ dài đầu vào/đầu ra và mức đồng thời.
- Cùng giới hạn chất lượng đầu ra và cấu hình CPU, RAM, lưu trữ ở mức có thể so sánh.
- Có bước làm nóng để loại ảnh hưởng của khởi tạo, biên dịch hoặc nạp mô hình.
- Chạy nhiều lần và ghi lại điều kiện thử nghiệm để kết quả có thể lặp lại.

Các chỉ số nên thu thập:

| Chỉ số | Ý nghĩa |
|---|---|
| Throughput | Số mẫu, ảnh, yêu cầu hoặc token xử lý mỗi giây |
| p50, p95, p99 latency | Độ trễ trung vị và các mức đuôi; đặc biệt quan trọng với dịch vụ tương tác |
| Thời gian hoàn thành | Thời gian để kết thúc một epoch, batch dữ liệu hoặc tác vụ |
| GPU utilization | Mức độ bộ tăng tốc thực sự bận xử lý |
| Bộ nhớ đỉnh | Dung lượng bộ nhớ lớn nhất đã dùng và khoảng dự phòng còn lại |
| CPU, RAM, mạng và I/O | Cho biết ứng dụng đang bị nghẽn ở thành phần nào |
| Chi phí trên đơn vị | Chi phí cho một triệu token, một nghìn ảnh hoặc một lần chạy hoàn chỉnh |
| Tỷ lệ lỗi và gián đoạn | Mức ổn định khi tăng tải hoặc khi tài nguyên bị thu hồi |

Nếu GPU utilization thấp trong khi CPU hoặc I/O thường xuyên đạt mức cao, nút thắt có thể nằm ở tiền xử lý, nạp dữ liệu hoặc điều phối. Khi đó, tăng cấp GPU chưa chắc cải thiện hiệu năng. Hãy xử lý nút thắt trước rồi chạy lại benchmark.

## 7. Ví dụ lựa chọn cho dịch vụ suy luận mô hình ngôn ngữ

Giả sử một nhóm cần triển khai mô hình có 7 tỷ tham số để phục vụ yêu cầu hỏi đáp. Nhóm dự kiến dùng trọng số FP16 và muốn hỗ trợ nhiều phiên đồng thời.

**Bước 1: Ước tính bộ nhớ.** Trọng số cần khoảng 14 GB. Dịch vụ còn cần bộ nhớ cho KV cache, runtime, batch và các vùng làm việc khác. Vì vậy, cấu hình 16 GB có nguy cơ quá sát giới hạn; cấu hình có bộ nhớ lớn hơn tạo thêm khoảng trống, nhưng vẫn phải kiểm thử theo độ dài ngữ cảnh và số phiên đồng thời.

**Bước 2: Xác định SLO.** Nhóm ghi rõ thông lượng token mục tiêu, độ trễ p95, số phiên đồng thời và chất lượng đầu ra. Nếu tải thấp, cấu hình nhỏ có thể đáp ứng tốt. Nếu có nhiều yêu cầu đồng thời, thông lượng và dung lượng cache sẽ trở nên quan trọng hơn.

**Bước 3: Kiểm tra nguồn cung.** Nhóm xác minh GPU phù hợp có sẵn trong vùng gần dữ liệu, quota đủ cho số bản sao dự kiến và phiên bản driver tương thích với container của ứng dụng.

**Bước 4: Đo hai cấu hình.** Giả sử cấu hình A có giá 2 USD/giờ và đạt 1.000 token/giây; cấu hình B có giá 3 USD/giờ và đạt 2.000 token/giây trong cùng điều kiện. Chi phí ước tính cho một triệu token lần lượt khoảng 0,56 USD và 0,42 USD. B có thể kinh tế hơn khi tải đủ lớn để sử dụng thông lượng của nó.

**Bước 5: Kiểm tra tải thực tế.** Nhóm tăng dần số phiên đồng thời, theo dõi p95/p99, bộ nhớ và tỷ lệ lỗi. Nếu cấu hình B chỉ có lợi ở tải cao, hệ thống có thể dùng cấu hình nhỏ cho mức tải nền và mở rộng thêm GPU khi nhu cầu tăng. Cách này cần được xác nhận bằng thử nghiệm tự động mở rộng và thời gian khởi động thực tế.

Ví dụ cho thấy quyết định phụ thuộc đồng thời vào bộ nhớ, SLO, thông lượng, giá và khả năng cấp phát. Không thể chọn chỉ dựa trên số tham số mô hình hoặc giá thuê theo giờ.

## 8. Tối ưu sau khi triển khai

Việc chọn thiết bị là điểm bắt đầu. Khi đã có số liệu vận hành, có thể giảm chi phí và cải thiện hiệu năng bằng các biện pháp sau:

- **Dùng mixed precision hoặc lượng tử hóa** khi đã kiểm chứng chất lượng mô hình và độ ổn định số học.
- **Điều chỉnh batch và dynamic batching** để tăng thông lượng mà vẫn giữ độ trễ trong SLO.
- **Dùng caching** cho dữ liệu hoặc kết quả có thể tái sử dụng.
- **Tách tải nền và tải đỉnh:** giữ cấu hình ổn định cho nhu cầu cơ bản, mở rộng khi tải tăng và thu nhỏ khi tải giảm.
- **Dùng spot/preemptible cho công việc có thể khôi phục:** lưu checkpoint và kiểm tra quy trình tiếp tục sau gián đoạn.
- **Đặt tài nguyên gần dữ liệu và người dùng:** giảm thời gian truyền dữ liệu và chi phí mạng.
- **Theo dõi mức sử dụng và chi phí:** phát hiện GPU nhàn rỗi, thiếu bộ nhớ, hàng đợi dài hoặc tình trạng nghẽn CPU/I/O.

Đối với tải không liên tục, khả năng scale-to-zero hoặc tắt máy khi không có việc có thể giảm chi phí đáng kể. Tuy nhiên, cần tính cả thời gian khởi động và nạp mô hình để không làm vi phạm SLO.

## 9. Những sai lầm thường gặp

1. **Chọn theo TFLOPS tối đa:** con số này không phản ánh trực tiếp thông lượng của ứng dụng, nhất là khi khác kiểu số hoặc kích thước batch.
2. **Chỉ tính bộ nhớ cho trọng số:** bỏ qua activation, gradient, optimizer state, KV cache và runtime khiến tác vụ dễ hết bộ nhớ.
3. **So sánh benchmark không cùng điều kiện:** khác batch, độ dài ngữ cảnh, kiểu số hoặc phiên bản thư viện làm kết quả mất ý nghĩa.
4. **Bỏ qua khả năng cấp phát:** quota, vùng triển khai và nguồn cung có thể khiến kế hoạch không thể triển khai đúng hạn.
5. **Bỏ qua chi phí hệ thống phụ trợ:** CPU, RAM, lưu trữ, mạng và thời gian nhàn rỗi có thể chiếm phần đáng kể trong tổng chi phí.
6. **Dùng nhiều GPU khi chưa cần:** giao tiếp và đồng bộ giữa thiết bị có thể làm tăng độ phức tạp và chi phí mà không tăng hiệu năng tương ứng.
7. **Không đo lại sau khi thay đổi tải:** mô hình, dữ liệu và mức đồng thời thay đổi có thể làm lựa chọn ban đầu không còn tối ưu.

## 10. Checklist trước khi chốt máy tăng tốc

- [ ] Đã mô tả workload, kích thước dữ liệu, SLO và mức tải dự kiến.
- [ ] Đã chọn đúng loại bộ tăng tốc cho phép toán và framework.
- [ ] Đã ước tính bộ nhớ cho toàn bộ ứng dụng, bao gồm phần dự phòng.
- [ ] Đã kiểm tra kiểu số, băng thông bộ nhớ và kết nối liên thiết bị nếu cần.
- [ ] Đã xác minh driver, runtime, thư viện và container tương thích.
- [ ] Đã kiểm tra region, quota, nguồn cung và hình thức cấp phát.
- [ ] Đã benchmark trên dữ liệu và mức tải đại diện.
- [ ] Đã so sánh chi phí trên đơn vị công việc và tổng chi phí vận hành.
- [ ] Đã kiểm tra khả năng mở rộng, phục hồi và phương án dự phòng.

## 11. Bài tập vận dụng

Một nhóm đang cân nhắc hai cấu hình GPU cho dịch vụ phân loại ảnh. Cấu hình X có giá 1,20 USD/giờ và xử lý 800 ảnh/giây. Cấu hình Y có giá 1,80 USD/giờ và xử lý 1.500 ảnh/giây. Hai cấu hình đạt cùng chất lượng phân loại trong benchmark.

1. Tính chi phí ước tính để xử lý một triệu ảnh trên mỗi cấu hình.
2. Nếu lưu lượng chỉ chiếm 10% thời gian trong ngày, ngoài chi phí trên mỗi triệu ảnh, nhóm cần đo thêm những yếu tố nào?
3. Nếu cấu hình Y không có sẵn ở vùng đặt dữ liệu, nhóm nên kiểm tra những chi phí và rủi ro nào trước khi chuyển vùng?

Gợi ý: quy đổi thông lượng theo giây thành số ảnh mỗi giờ, sau đó chia giá thuê theo giờ cho số ảnh xử lý trong một giờ. Với câu 2 và 3, hãy xem xét thời gian nhàn rỗi, thời gian khởi động, chi phí mạng, độ trễ và khả năng cấp phát.

## Kết luận

Một lựa chọn máy tăng tốc tốt phải đáp ứng đồng thời yêu cầu tính toán, bộ nhớ, phần mềm, kết nối, chi phí và nguồn cung. Hãy bắt đầu từ workload và SLO, lọc các cấu hình không tương thích, benchmark trên tải thực tế rồi so sánh chi phí cho cùng một đơn vị công việc. Sau khi triển khai, tiếp tục theo dõi mức sử dụng và khả năng cấp phát để điều chỉnh cấu hình theo nhu cầu thực tế.
