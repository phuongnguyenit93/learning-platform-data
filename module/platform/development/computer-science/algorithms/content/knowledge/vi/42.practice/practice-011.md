# Đánh giá lời giải ngẫu nhiên hoặc gần đúng bằng tiêu chí phù hợp

Một thuật toán có thể chạy nhanh và thường tìm được lời giải tốt nhưng vẫn chưa đủ cơ sở để kết luận nó đáng tin cậy. Với **thuật toán ngẫu nhiên (randomized algorithm)** hoặc **thuật toán xấp xỉ (approximation algorithm)**, chất lượng kết quả có thể thay đổi theo random seed, dữ liệu đầu vào, ngân sách thời gian và cách thuật toán được chạy.

Muốn đánh giá đúng, cần xác định trước **thuật toán đang cam kết điều gì**, rồi chọn thước đo tương ứng. Có bài cần đo xác suất trả lời chính xác; có bài cần đo tỷ lệ đạt một ngưỡng chất lượng; có bài luôn đúng nhưng thời gian chạy biến động; cũng có bài luôn trả một phương án khả thi nhưng chất lượng khác nhau giữa các lần chạy.

Bài thuộc nhóm **Thực hành tổng hợp**, tập trung vào cách thiết kế một thí nghiệm có thể lặp lại, sử dụng oracle khi biết đáp án tối ưu, so sánh chất lượng và độ bất định thống kê, xử lý trường hợp chưa biết optimum, và tránh những kết luận sai khi chỉ nhìn một lần chạy.

Ví dụ xuyên suốt là **Max-Cut**: chia đỉnh của đồ thị thành hai phía sao cho số cạnh nối hai phía lớn nhất. Ta cài một thuật toán greedy có thứ tự duyệt ngẫu nhiên, tính optimum chính xác trên đồ thị nhỏ, chạy 500 seed, rồi báo cáo **tỷ lệ đạt ngưỡng, khoảng tin cậy, chất lượng trung bình, trung vị và kết quả tệ nhất**. Chương trình Java 17+ ở cuối bài in kết quả mẫu có thể tái lập.

## 1. Trước tiên phải xác định đang đánh giá điều gì

Có ít nhất bốn câu hỏi riêng:

1. **Tính hợp lệ:** kết quả có thỏa mọi ràng buộc của bài toán không?
2. **Tính đúng đắn:** nếu bài yêu cầu đáp án chính xác, thuật toán có trả đúng đáp án không?
3. **Chất lượng:** nếu cho phép xấp xỉ, lời giải tốt đến mức nào so với optimum hoặc một chuẩn tham chiếu?
4. **Tài nguyên:** cần bao nhiêu thời gian, bộ nhớ, số lần thử hoặc năng lượng để đạt chất lượng đó?

Không nên gộp bốn câu hỏi thành một con số duy nhất.

Ví dụ, một thuật toán trả lời đúng 99% lần nhưng 1% lần còn lại vi phạm ràng buộc nghiêm trọng có thể không phù hợp với hệ thống thanh toán. Một heuristic luôn trả phương án hợp lệ nhưng đôi khi kém hơn baseline 30% lại cần đánh giá bằng **chất lượng mục tiêu**, không phải chỉ tỷ lệ chạy thành công.

### Bảng chọn tiêu chí

| Loại cam kết | Chỉ số chính | Chỉ số bổ sung |
| --- | --- | --- |
| Trả lời chính xác với xác suất cao | Success probability | Confidence interval, số lỗi |
| Luôn đúng, runtime ngẫu nhiên | Runtime distribution | Median, p95, timeout rate |
| Phương án xấp xỉ | Approximation ratio/gap | Feasibility, mean, median, quantiles |
| Heuristic không có guarantee | Quality distribution | Worst observed, baseline, robustness |
| Có nhiều ràng buộc | Feasibility rate | Mức độ vi phạm từng ràng buộc |
| Thuật toán anytime | Quality theo thời gian | Best-so-far curve, time-to-target |

## 2. Phân biệt randomized, Monte Carlo, Las Vegas và approximation

Các thuật ngữ này liên quan nhưng không đồng nghĩa.

**Randomized algorithm** sử dụng ngẫu nhiên trong quá trình chạy. Randomness có thể ảnh hưởng kết quả, runtime hoặc cả hai.

**Monte Carlo algorithm** có thời gian chạy được giới hạn theo thiết kế nhưng có thể trả lời sai với xác suất nhỏ. Cần đo **xác suất trả lời đúng** hoặc xác suất đạt tiêu chí đã cam kết.

**Las Vegas algorithm** luôn trả kết quả đúng theo hợp đồng, nhưng thời gian chạy là biến ngẫu nhiên. Cần đo phân phối runtime, số bước và xác suất vượt deadline.

**Approximation algorithm** được phép trả lời không tối ưu, nhưng có mục tiêu và thường có guarantee về khoảng cách tới optimum. Cần đo **chất lượng lời giải** và kiểm tra guarantee.

**Randomized heuristic** có thể tạo các lời giải hợp lệ với chất lượng thay đổi. Nó không tự động có guarantee xấp xỉ chỉ vì sử dụng random seed.

Một thuật toán có thể vừa randomized vừa approximate. Ví dụ, một thuật toán tìm đường có thể luôn trả một đường hợp lệ nhưng độ dài đường thay đổi giữa các seed.

### Không đánh đồng “thành công” với “tối ưu”

Nếu thuật toán trả một đường đi hợp lệ dài 120 trong khi đường tối ưu dài 100, nó đã **thành công về tính khả thi** nhưng chưa **đạt tối ưu**. Nếu ngưỡng cho phép là không quá 1.25 lần optimum, nó vẫn đạt tiêu chí xấp xỉ vì 120≤125.

Phải ghi rõ success được định nghĩa bằng điều kiện nào.

## 3. Xác định objective và chiều tối ưu

Trước khi chọn metric, hãy viết rõ objective.

**Bài maximize:** giá trị càng lớn càng tốt, ví dụ số cạnh được cắt trong Max-Cut, lợi nhuận hoặc số việc hoàn thành.

**Bài minimize:** giá trị càng nhỏ càng tốt, ví dụ chi phí, thời gian hoặc độ dài đường đi.

**Bài feasibility:** chỉ cần tồn tại phương án thỏa các ràng buộc; objective có thể không quan trọng.

**Bài đa mục tiêu:** nhiều tiêu chí có thể xung đột, chẳng hạn thời gian, chi phí và mức sử dụng bộ nhớ.

Không nên đổi chiều objective tùy tiện khi tổng hợp kết quả. Một giá trị 0.95 có thể là tốt trong quality ratio, nhưng có thể là tệ trong error rate.

### Ghi nhận cả objective và constraint

Với mỗi lần chạy, lưu ít nhất:

- Input instance hoặc ID của instance.
- Random seed và cấu hình.
- Kết quả objective.
- Trạng thái feasible/infeasible.
- Các ràng buộc bị vi phạm và độ lớn vi phạm.
- Runtime và tài nguyên quan trọng.
- Phiên bản thuật toán và môi trường chạy.

Nếu kết quả không feasible, không nên tính approximation ratio như thể nó là một lời giải hợp lệ. Hãy báo riêng tỷ lệ feasible và cách xử lý vi phạm theo hợp đồng.

## 4. Approximation ratio cho bài maximize

Giả sử:

- **OPT** là giá trị tối ưu.
- **ALG** là giá trị của lời giải thuật toán trả về.
- Bài toán maximize có giá trị không âm và ALG là feasible.

Khi đó:

**quality = ALG / OPT**.

Thông thường:

**0≤quality≤1**.

Ví dụ:

~~~text
OPT = 100
ALG = 90
quality = 90/100 = 0.90
~~~

Lời giải đạt 90% optimum.

Một thuật toán có **approximation factor α≥1** cho bài maximize nếu:

**ALG ≥ OPT/α**.

Ví dụ α=2 nghĩa là lời giải được bảo đảm ít nhất một nửa optimum.

### Đừng nhầm ratio với phần trăm thiếu hụt

Với quality=0.90:

- Quality đạt được: 90%.
- Relative shortfall so với OPT: 10%.

Hai số có liên hệ nhưng tên gọi khác nhau. Báo cáo nên ghi đúng nhãn.

## 5. Approximation ratio cho bài minimize

Với bài minimize, ALG thường không nhỏ hơn OPT. Để chuẩn hóa quality về khoảng (0,1], dùng:

**quality = OPT / ALG**,

giả sử ALG>0 và feasible.

Ví dụ:

~~~text
OPT = 100
ALG = 125
quality = 100/125 = 0.80
~~~

Lời giải có chi phí cao hơn optimum 25%, tương ứng quality ratio 0.80.

Một thuật toán có factor α cho bài minimize nếu:

**ALG ≤ α·OPT**.

Với α=1.25, lời giải không đắt hơn 1.25 lần optimum.

### Khi objective bằng 0 hoặc âm

Ratio có thể không xác định hoặc gây hiểu lầm nếu OPT=0, ALG=0 hoặc objective có thể âm.

Trong trường hợp đó, hãy dùng:

- Additive gap.
- Relative error theo một scale được định nghĩa hợp lệ.
- Một metric theo domain, chẳng hạn số vi phạm, thời gian hoặc chi phí tuyệt đối.

Không cộng một hằng số tùy ý chỉ để làm mẫu số dương nếu phép biến đổi đó thay đổi ý nghĩa so sánh.

## 6. Additive error và multiplicative error

Không phải bài nào cũng phù hợp với ratio.

**Maximize, additive gap:**

**gap = OPT−ALG**.

**Minimize, additive gap:**

**gap = ALG−OPT**.

Gap càng nhỏ càng tốt, và bằng 0 khi tối ưu.

**Relative error** thường chia additive gap cho một scale dương có ý nghĩa, thường là |OPT| khi OPT khác 0 và cách chuẩn hóa đó hợp lý.

### Khi nào dùng loại nào?

- Objective có thang đo ổn định và OPT xa 0: ratio thường dễ diễn giải.
- Objective gần 0 hoặc có thể âm: additive gap có thể rõ hơn.
- Hệ thống có ngưỡng nghiệp vụ cố định: báo cả việc đạt ngưỡng hay không.
- Nhiều đại lượng khác đơn vị: chuẩn hóa theo từng đại lượng trước khi tổng hợp, và giải thích cách chuẩn hóa.

Không nên lấy trung bình thời gian (ms), chi phí (USD) và chất lượng (ratio) trực tiếp thành một số không có định nghĩa.

## 7. Feasibility là cổng đầu tiên

Một lời giải xấp xỉ vẫn phải đáp ứng các ràng buộc được yêu cầu.

Ví dụ trong bài phân lịch:

- Một công việc không được gán cho hai máy cùng lúc.
- Máy không xử lý hai công việc chồng thời gian nếu mô hình cấm.
- Tổng tải không vượt capacity.
- Mọi công việc bắt buộc đều phải được xử lý.

Một kết quả có objective rất tốt nhưng vi phạm ràng buộc cứng **không phải lời giải feasible**.

### Báo cáo feasibility riêng

Nếu chạy N lần và có V lần trả phương án hợp lệ:

**feasibility rate = V/N**.

Sau đó mới đánh giá objective/quality trên tập kết quả feasible, đồng thời báo rõ số lần bị loại. Nếu hệ thống thực tế dùng fallback khi heuristic thất bại, hãy đo cả **toàn bộ policy gồm fallback**, không chỉ heuristic đứng riêng.

### Ràng buộc mềm và phạt

Nếu một ràng buộc là soft constraint, có thể dùng penalty trong objective nhưng phải nêu:

- Mức penalty.
- Vì sao mức đó phản ánh chi phí thật.
- Có trade-off nào giữa objective và violation.
- Kết quả gốc trước penalty.

Không tùy tiện cộng penalty rất lớn để làm cho một phương án trông “tệ” hơn mà không có căn cứ.

## 8. Oracle và ground truth: biết OPT bằng cách nào?

Muốn tính ratio chính xác, cần biết **OPT**. Có nhiều cách:

**Exact oracle:** giải chính xác bằng brute force, dynamic programming, integer programming hoặc một solver tin cậy trên instance nhỏ.

**Best-known solution:** dùng nghiệm tốt nhất đã biết, nhưng phải gọi đúng là best-known chứ không tuyên bố optimum nếu chưa chứng minh.

**Lower/upper bound:** dùng cận toán học để đưa ra bảo đảm một phía.

**Baseline:** dùng thuật toán khác để so sánh tương đối. Baseline không thay thế ground truth.

### Cỡ instance phù hợp

Exact oracle có thể quá chậm cho instance lớn. Một quy trình hợp lý:

1. Sinh các instance nhỏ đủ đa dạng.
2. Tính OPT chính xác.
3. Kiểm tra ratio và tính feasible của heuristic trên tập nhỏ.
4. Với instance lớn, dùng best-known hoặc bounds, đồng thời ghi rõ mức độ chắc chắn.

Không ngoại suy rằng kết quả trên n=10 tự động đúng với n=10⁶.

## 9. Khi chưa biết OPT: sử dụng bound đúng chiều

Đây là điểm dễ đánh giá sai.

### Bài maximize

Ta biết ALG≤OPT. Nếu có **upper bound UB≥OPT**, thì:

**ALG/UB ≤ ALG/OPT**.

Do đó ALG/UB là **cận dưới hợp lệ** cho quality ratio thật. Nếu UB chưa chặt, cận này có thể bảo thủ.

### Bài minimize

Ta biết OPT≤ALG. Nếu có **lower bound LB≤OPT**, thì:

**LB/ALG ≤ OPT/ALG**.

Do đó LB/ALG là cận dưới hợp lệ cho quality ratio thật.

### Ví dụ

Maximize:

~~~text
ALG = 80
OPT chưa biết
UB = 100

ALG/UB = 0.80
~~~

Có thể kết luận quality thật **ít nhất 0.80**, không thể kết luận đúng bằng 0.80.

Minimize:

~~~text
ALG = 125
OPT chưa biết
LB = 100

LB/ALG = 0.80
~~~

Quality thật **ít nhất 0.80**.

### Hướng bound rất quan trọng

- Maximize cần UB để chứng nhận cận dưới của ALG/OPT.
- Minimize cần LB để chứng nhận cận dưới của OPT/ALG.

Dùng ngược chiều có thể tạo ra một “quality score” lạc quan không được bảo đảm.

## 10. Randomness tạo ra một phân phối kết quả

Với cùng một input, thuật toán randomized có thể trả những kết quả khác nhau do:

- Random order.
- Random initialization.
- Random sampling.
- Tie-breaking.
- Random restart.
- Randomized data structure.
- Ngân sách thử nghiệm hoặc stopping rule.

Vì vậy, **một lần chạy không mô tả đầy đủ thuật toán**.

Một thí nghiệm thường cố định input và chạy nhiều seed:

~~~text
instance I
seed 1 -> quality q1
seed 2 -> quality q2
...
seed N -> quality qN
~~~

Ta thu được một mẫu từ phân phối kết quả theo randomness của thuật toán trên instance I.

### Hai nguồn biến động khác nhau

**Biến động theo seed:** cùng một instance nhưng kết quả khác nhau.

**Biến động theo instance:** bài dễ và bài khó có thể tạo kết quả khác nhau dù dùng cùng thuật toán.

Muốn đánh giá chất lượng trên một lớp input, phải lấy mẫu **nhiều instance**, không chỉ chạy nhiều seed trên một instance.

## 11. Chọn thống kê mô tả phù hợp

Với các quality ratios q₁,...,qₙ, nên cân nhắc:

**Mean:** trung bình, phản ánh chất lượng kỳ vọng nhưng nhạy với outlier.

**Median:** trung vị, mô tả lần chạy điển hình và ít nhạy với outlier.

**Minimum/maximum observed:** trường hợp tốt/tệ nhất trong mẫu; không phải worst-case guarantee.

**Quantiles:** p10, p25, p75, p90 giúp nhìn phân phối.

**Standard deviation:** mức phân tán quanh mean.

**Success rate:** tỷ lệ đạt một ngưỡng định nghĩa trước.

**Runtime p50/p95:** thời gian điển hình và đuôi phân phối.

### Vì sao không chỉ báo best run?

Nếu chạy 1000 seed rồi chỉ báo kết quả tốt nhất, người đọc không biết:

- Một lần chạy thông thường có tốt không?
- Cần bao nhiêu thời gian để đạt best?
- Kết quả best có lặp lại được không?
- Production có thật sự được phép chạy 1000 restart không?

Nếu production thực hiện đúng 1000 restart và chọn tốt nhất, hãy đánh giá **policy 1000 restart** như một đơn vị thí nghiệm, với đúng budget đó.

## 12. Định nghĩa success threshold trước khi chạy

Một thí nghiệm có thể định nghĩa:

**success = quality ≥ 0.90**.

Nếu có N lần chạy, S lần thành công:

**p̂ = S/N**.

Ví dụ:

~~~text
N = 500
S = 362
p̂ = 362/500 = 0.724
~~~

Tức 72.4% lần chạy đạt ít nhất 90% optimum.

Ngưỡng phải được xác định theo yêu cầu trước khi xem kết quả. Nếu thử nhiều ngưỡng rồi chỉ báo ngưỡng làm thuật toán trông tốt, báo cáo sẽ bị thiên lệch.

### Ngưỡng có ý nghĩa thực tế

- SLA: hoàn tất trong 2 giây.
- Tối ưu: quality≥0.95.
- Tìm kiếm: trả nghiệm đúng trong 99.9% lượt.
- Phân lịch: không có vi phạm cứng và chi phí không quá 1.1× baseline.

Một ngưỡng 0.90 không mặc nhiên tốt hoặc xấu; ý nghĩa phụ thuộc bài toán.

## 13. Khoảng tin cậy cho xác suất thành công

Tỷ lệ S/N chỉ là **ước lượng điểm**. Khi N hữu hạn, tỷ lệ thật còn bất định.

Với các lần chạy Bernoulli và giả thiết độc lập cùng xác suất thành công p, có thể dùng **Wilson score interval** thay vì khoảng Wald đơn giản.

Đặt:

- p̂=S/N.
- z là quantile chuẩn, khoảng 1.96 cho mức 95%.
- N là số lần chạy.

Mẫu số:

**den = 1 + z²/N**.

Tâm:

**center = (p̂ + z²/(2N))/den**.

Nửa độ rộng:

**half = z·sqrt(p̂(1−p̂)/N + z²/(4N²))/den**.

Khoảng:

**[center−half, center+half]**.

Wilson hoạt động tốt hơn Wald khi tỷ lệ gần 0 hoặc 1 và khi số lần chạy không lớn.

### Cách diễn giải

Khoảng tin cậy 95% là thuộc tính của **phương pháp tạo khoảng qua nhiều thí nghiệm lặp**, theo giả thiết thống kê đã chọn. Không nên diễn giải thành “xác suất p nằm trong chính khoảng đã tính là 95%” theo nghĩa xác suất hậu nghiệm.

### Giới hạn giả thiết

Wilson không sửa được thiết kế lấy mẫu sai. Nếu các lần chạy phụ thuộc mạnh, seed bị tái sử dụng có chủ đích hoặc instance được chọn thiên lệch, khoảng tin cậy có thể gây hiểu nhầm.

## 14. Khoảng tin cậy cho chất lượng trung bình

Với qᵢ là quality ratio trong [0,1], tính:

**mean = Σqᵢ/N**.

Độ lệch chuẩn mẫu:

**s = sqrt(Σ(qᵢ−mean)²/(N−1))**.

Sai số chuẩn:

**SE = s/sqrt(N)**.

Một khoảng tin cậy gần đúng 95% khi mẫu đủ lớn:

**mean ± 1.96·SE**.

Với mẫu nhỏ và giả thiết phù hợp, dùng Student t critical value thay 1.96. Nếu phân phối lệch mạnh hoặc có cấu trúc nhiều tầng, có thể dùng bootstrap theo đơn vị lấy mẫu phù hợp.

### Mean không phải median

Nếu 95% kết quả rất tốt nhưng 5% kết quả cực tệ, mean có thể giảm mạnh. Ngược lại, median có thể che mất một tail failure quan trọng. Vì vậy hãy báo cả phân vị và tỷ lệ lỗi khi tail risk có ý nghĩa.

## 15. Ước lượng số lần chạy cần thiết

Với biến ngẫu nhiên độc lập X nằm trong [0,1], bất đẳng thức **Hoeffding** cho:

**Pr(|mean−E[X]|≥ε) ≤ 2·exp(−2Nε²)**.

Muốn sai số tối đa ε với xác suất sai không quá δ, có thể chọn:

**N ≥ ln(2/δ)/(2ε²)**.

Ví dụ:

- ε=0.05.
- δ=0.05.
- ln(2/0.05)=ln(40).

Suy ra:

**N ≥ ln(40)/(2×0.05²) ≈ 737.78**,

nên cần ít nhất **738 lần chạy** theo bound bảo thủ này.

### Không dùng công thức một cách máy móc

- Bound giả định các mẫu độc lập.
- X phải bị chặn trong [0,1].
- Đây là bảo đảm sai số cho mean, không phải cho median hay p95.
- N tăng khi muốn ε nhỏ hơn hoặc confidence cao hơn.
- Nếu lấy nhiều instance và nhiều seed, phải xác định đơn vị lấy mẫu và nguồn biến động cần ước lượng.

Wilson interval thường phù hợp hơn cho xác suất Bernoulli; Hoeffding là bound tổng quát cho biến bị chặn.

## 16. Đánh giá trên một instance và trên cả tập instance

Một thuật toán có thể hoạt động xuất sắc trên một đồ thị nhưng kém trên đồ thị thưa, đồ thị có cộng đồng hoặc dữ liệu mất cân bằng.

Một benchmark tốt nên chia input thành các nhóm có ý nghĩa:

- Kích thước nhỏ, vừa, lớn.
- Mật độ thưa và dày.
- Cấu trúc ngẫu nhiên và cấu trúc có quy luật.
- Trường hợp biên, duplicates, outliers.
- Instance thật và instance tổng hợp.
- Dữ liệu dễ, trung bình và khó theo một tiêu chí định nghĩa trước.

### Hai cấp độ báo cáo

**Per-instance:** mean/median quality, success rate, runtime và variability qua seeds.

**Across-instances:** phân phối kết quả giữa các instance; có thể báo median của per-instance means, worst group hoặc macro-average.

Không để một instance có hàng triệu lần chạy lấn át 100 instance chỉ được chạy một lần nếu mục tiêu là mỗi instance có trọng số ngang nhau.

### Tách tập tuning và test

Nếu đã dùng benchmark để chọn tham số, nó trở thành dữ liệu tuning. Nên có tập held-out để đánh giá cuối, giống nguyên tắc train/validation/test trong machine learning.

## 17. So sánh hai thuật toán công bằng

Khi so A và B:

1. Dùng cùng tập instance.
2. Dùng ngân sách thời gian hoặc số lần đánh giá objective tương đương.
3. Cố định điều kiện phần cứng, runtime, compiler/JDK và tải hệ thống.
4. Ghi lại seed và cấu hình.
5. Đo cùng loại metric.
6. Báo cả chất lượng lẫn runtime.

### Thiết kế paired comparison

Trên mỗi instance i, tính:

**dᵢ = quality(A,i)−quality(B,i)**.

Nếu có thể ghép seed tương ứng một cách hợp lý, dùng cùng seed hoặc cùng nguồn randomness để giảm nhiễu so sánh. Với các thuật toán tiêu thụ random numbers khác nhau, cùng seed không bảo đảm hai đường chạy tương ứng hoàn toàn; cần ghi rõ cách ghép.

Báo mean/median của dᵢ và khoảng tin cậy của chênh lệch.

### Kiểm định thống kê

- Paired t-test có thể phù hợp với các hiệu số gần chuẩn và giả thiết cần thiết.
- Wilcoxon signed-rank hoặc permutation test có thể phù hợp hơn trong một số phân phối khác.
- Với nhiều thuật toán/metric, phải lưu ý multiple comparisons.
- Báo **effect size và confidence interval**, không chỉ p-value.

Một chênh lệch rất nhỏ có thể có p-value thấp khi N cực lớn nhưng không tạo giá trị thực tế.

## 18. Baseline và ablation

Một thuật toán mới nên được so với baseline có ý nghĩa:

- Random solution đơn giản.
- Greedy deterministic.
- Heuristic phổ biến.
- Best-known solver hoặc exact solver trên instance nhỏ.
- Phiên bản trước khi thêm thành phần mới.

**Ablation** tắt từng thành phần để xác định thành phần nào thực sự đóng góp. Ví dụ, so randomized greedy với phiên bản giữ thứ tự đỉnh cố định để biết random ordering cải thiện chất lượng đến đâu.

### Không so với baseline yếu tùy tiện

Nếu baseline không được tuning hoặc có budget thấp hơn, kết quả “vượt baseline” không có nhiều ý nghĩa. Hãy dùng baseline mạnh hợp lý và cùng ngân sách.

## 19. Best-of-k restart là một thuật toán khác về mặt đánh giá

Giả sử mỗi run tạo quality q và ta chạy k lần rồi lấy lời giải tốt nhất.

**Qₖ=max(q₁,...,qₖ)** cho bài maximize quality.

Khi k tăng, best-of-k thường không giảm, nhưng thời gian và tài nguyên cũng tăng.

Cần phân biệt:

- Chất lượng trung bình của **một run**.
- Chất lượng tốt nhất trong **k runs**.
- Thời gian để thực hiện k runs.
- Xác suất đạt threshold trong k runs.

Nếu xác suất một run độc lập đạt threshold là p, xác suất ít nhất một trong k runs đạt là:

**1−(1−p)ᵏ**.

Công thức này cần giả thiết các run độc lập cùng xác suất p. Nếu seed hoặc trạng thái chia sẻ làm chúng phụ thuộc, công thức có thể không đúng.

### So sánh đúng budget

Nếu A được 100 restarts còn B chỉ có 1, không thể kết luận A có thuật toán tốt hơn mà không tính chi phí. Hãy so cả hai dưới cùng deadline hoặc cùng số lần objective evaluation.

## 20. Ví dụ xuyên suốt: Max-Cut

Cho đồ thị vô hướng G=(V,E). Mỗi đỉnh được đặt vào một trong hai phía S và V\\S.

Một cạnh (u,v) được tính vào cut nếu hai đầu ở hai phía khác nhau.

Mục tiêu:

**Maximize cut(S)= số cạnh có hai đầu thuộc hai phía khác nhau.**

Với một đồ thị nhỏ, có thể duyệt tất cả cách chia để tìm **OPT**. Nếu có n đỉnh, có 2ⁿ cách gán phía; vì đảo hai phía không thay đổi cut, ta có thể cố định đỉnh 0 ở phía false và chỉ duyệt:

**2⁽ⁿ⁻¹⁾** cách.

Ví dụ trong chương trình:

- 10 đỉnh.
- 22 cạnh.
- Chỉ cần duyệt 2⁹=512 cách phân hoạch.
- Exact optimum được tính là **16**.

Đây là ground truth của instance mẫu, không phải một khẳng định về mọi đồ thị 10 đỉnh.

## 21. Randomized greedy Max-Cut

Thuật toán:

1. Tạo một thứ tự ngẫu nhiên của các đỉnh.
2. Duyệt từng đỉnh theo thứ tự ấy.
3. Với đỉnh đang xét, đếm số cạnh nối tới các đỉnh đã gán phía false và số cạnh nối tới các đỉnh đã gán phía true.
4. Chọn phía làm nhiều cạnh nối tới các đỉnh trước đó bị cắt hơn.
5. Nếu hai lựa chọn bằng nhau, tung đồng xu ngẫu nhiên.
6. Sau khi gán hết đỉnh, tính cut.

Randomness nằm ở **thứ tự duyệt** và **tie-breaking**. Cùng một đồ thị có thể cho các cut khác nhau.

### Một chi tiết cần hiểu đúng

Khi gán đỉnh v, thuật toán chỉ xét các cạnh từ v đến những đỉnh đã được gán. Các cạnh nối tới đỉnh chưa gán sẽ được xét sau, khi đầu còn lại được xử lý.

Mỗi cạnh được quyết định đúng một lần: tại thời điểm đỉnh thứ hai trong cạnh được gán phía.

## 22. Guarantee 1/2 của greedy và vai trò của randomness

Gọi A là số cạnh từ đỉnh hiện tại tới các đỉnh đã gán phía false, B là số cạnh tới các đỉnh đã gán phía true.

- Nếu đặt v ở phía true, ta cắt A cạnh.
- Nếu đặt v ở phía false, ta cắt B cạnh.

Greedy chọn phía có số cạnh bị cắt lớn hơn, nên số cạnh mới được cắt **ít nhất max(A,B)≥(A+B)/2**.

Mỗi cạnh của đồ thị được tính đúng một lần khi đầu thứ hai của nó được gán. Cộng qua tất cả đỉnh:

**cut do greedy tạo ra ≥ |E|/2**.

Vì cut tối ưu không thể lớn hơn |E|:

**ALG/OPT ≥ 1/2**.

Đây là guarantee của thuật toán cụ thể, không phụ thuộc thứ tự ngẫu nhiên. Randomness có thể cải thiện kết quả thực tế nhưng không cần thiết cho bảo đảm 1/2.

### Guarantee không đồng nghĩa với kết quả quan sát

Một lần chạy đạt 15/16≈0.938 không chứng minh thuật toán luôn đạt 0.938. Bảo đảm lý thuyết ở đây là **ít nhất 0.5** cho mọi đồ thị đầu vào hợp lệ; số 0.938 là một kết quả trung bình thực nghiệm trên một đồ thị cụ thể.

## 23. Exact oracle và đánh giá một lần chạy

Để đánh giá thuật toán trên đồ thị mẫu:

**Bước 1:** tính OPT bằng exact enumeration.

**Bước 2:** chạy randomized greedy với seed xác định.

**Bước 3:** tính ALG bằng cách đếm cạnh qua hai phía.

**Bước 4:** kiểm tra cut hợp lệ và tính quality=ALG/OPT.

**Bước 5:** lặp qua nhiều seed.

Vì mỗi lời giải Max-Cut là một phân hoạch hai phía, mọi assignment đều feasible trong mô hình không có constraint bổ sung. Nếu bài thực tế có giới hạn kích thước hai phía, chi phí vertex hoặc ràng buộc khác, phải kiểm tra riêng; không được áp dụng metric của Max-Cut thuần túy.

### Exact oracle có thể chỉ dùng cho input nhỏ

Độ phức tạp exact enumeration là **O(2⁽ⁿ⁻¹⁾·m)** với m=|E|. Đây chỉ là oracle kiểm thử cho đồ thị nhỏ; không phải thuật toán dùng production cho đồ thị lớn.

## 24. Báo cáo 500 lần chạy trên đồ thị mẫu

Chương trình sử dụng:

- 10 đỉnh, 22 cạnh.
- OPT=16.
- 500 seed liên tiếp bắt đầu từ 20261110.
- Success threshold: quality≥0.90.
- Một randomized greedy run cho mỗi seed.

Kết quả mẫu:

| Metric | Kết quả |
| --- | ---: |
| Mean cut | 15.050 |
| Mean quality ratio | 0.941 |
| Median quality ratio | 0.938 |
| Successes ≥0.90 | 362/500 = 0.724 |
| 95% Wilson CI cho success rate | [0.683, 0.761] |
| 95% CI gần đúng cho mean quality | [0.936, 0.946] |
| Best cut quan sát | 16 |
| Worst cut quan sát | 12 |
| Mỗi run đạt cut≥ceil(22/2) | Có |

### Diễn giải

Trên **instance này**, chất lượng trung bình khoảng 94.1% optimum. Có 72.4% số lần chạy đạt ngưỡng 90%; Wilson interval mô tả độ bất định của tỷ lệ thành công theo các seed đã lấy mẫu.

Tất cả 500 lần chạy đều đạt ít nhất 11 cạnh cắt, phù hợp guarantee 1/2. Lần tệ nhất quan sát được là 12; điều này **không chứng minh worst case toàn cục là 12**.

Khoảng tin cậy của mean là xấp xỉ theo normal approximation. Nếu phân phối hoặc thiết kế thí nghiệm khác, nên chọn phương pháp CI phù hợp hơn.

## 25. Java 17+ độc lập: đo chất lượng randomized Max-Cut

Chương trình gồm:

- **buildAdjacency:** dựng danh sách kề và validate đồ thị.
- **randomizedGreedyCut:** tạo phân hoạch theo thứ tự đỉnh ngẫu nhiên.
- **cutValue:** tính số cạnh bị cắt.
- **exactMaxCut:** oracle vét cạn cho n≤25.
- **wilsonInterval:** khoảng tin cậy 95% cho success rate.
- **main:** chạy 500 seed, thống kê chất lượng và in kết quả.

Các cạnh là vô hướng, không có self-loop. Nếu danh sách cạnh chứa nhiều bản ghi cùng cặp đỉnh, mỗi bản ghi được tính như một cạnh song song; instance mẫu không có cạnh trùng.

**Tên tệp: RandomizedApproximationEvaluationDemo.java**

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.Random;

public class RandomizedApproximationEvaluationDemo {

    static int[][] buildAdjacency(int n, int[][] edges) {
        if (n < 1) {
            throw new IllegalArgumentException(
                    "The graph must have at least one vertex");
        }

        Objects.requireNonNull(edges, "edges");
        int[] degree = new int[n];

        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException(
                        "Each edge must contain two endpoints");
            }

            int u = edge[0];
            int v = edge[1];

            if (u < 0 || u >= n || v < 0 || v >= n) {
                throw new IllegalArgumentException(
                        "Edge endpoint is outside the graph");
            }

            if (u == v) {
                throw new IllegalArgumentException(
                        "Self-loops are not supported");
            }

            degree[u]++;
            degree[v]++;
        }

        int[][] adjacency = new int[n][];
        for (int v = 0; v < n; v++) {
            adjacency[v] = new int[degree[v]];
        }

        int[] next = new int[n];

        for (int[] edge : edges) {
            int u = edge[0];
            int v = edge[1];

            adjacency[u][next[u]++] = v;
            adjacency[v][next[v]++] = u;
        }

        return adjacency;
    }

    static long cutValue(int[][] edges, boolean[] side) {
        Objects.requireNonNull(edges, "edges");
        Objects.requireNonNull(side, "side");

        long cut = 0L;

        for (int[] edge : edges) {
            if (side[edge[0]] != side[edge[1]]) {
                cut++;
            }
        }

        return cut;
    }

    // Randomized order and random tie-breaking.
    static boolean[] randomizedGreedyCut(
            int[][] adjacency, Random random) {
        Objects.requireNonNull(adjacency, "adjacency");
        Objects.requireNonNull(random, "random");

        int n = adjacency.length;
        int[] order = new int[n];

        for (int i = 0; i < n; i++) {
            order[i] = i;
        }

        // Fisher-Yates shuffle.
        for (int i = n - 1; i > 0; i--) {
            int j = random.nextInt(i + 1);
            int temp = order[i];
            order[i] = order[j];
            order[j] = temp;
        }

        boolean[] side = new boolean[n];
        boolean[] assigned = new boolean[n];

        for (int vertex : order) {
            int toFalse = 0;
            int toTrue = 0;

            for (int neighbor : adjacency[vertex]) {
                if (!assigned[neighbor]) {
                    continue;
                }

                if (side[neighbor]) {
                    toTrue++;
                } else {
                    toFalse++;
                }
            }

            // Putting this vertex on true cuts edges to
            // previously assigned false vertices.
            // Putting it on false cuts edges to true vertices.
            if (toFalse > toTrue) {
                side[vertex] = true;
            } else if (toTrue > toFalse) {
                side[vertex] = false;
            } else {
                side[vertex] = random.nextBoolean();
            }

            assigned[vertex] = true;
        }

        return side;
    }

    // Exact oracle for small graphs only.
    // Complementing every side leaves the cut unchanged,
    // so vertex 0 can be fixed to false.
    static long exactMaxCut(int n, int[][] edges) {
        if (n < 1 || n > 25) {
            throw new IllegalArgumentException(
                    "Exact enumeration supports 1 <= n <= 25");
        }

        boolean[] side = new boolean[n];
        long best = 0L;
        long limit = 1L << (n - 1);

        for (long mask = 0L; mask < limit; mask++) {
            side[0] = false;

            for (int vertex = 1; vertex < n; vertex++) {
                side[vertex] =
                        (mask & (1L << (vertex - 1))) != 0L;
            }

            best = Math.max(best, cutValue(edges, side));
        }

        return best;
    }

    // Returns [lower, upper] Wilson score interval.
    static double[] wilsonInterval(
            int successes, int trials) {
        if (trials <= 0 || successes < 0
                || successes > trials) {
            throw new IllegalArgumentException(
                    "Invalid binomial sample");
        }

        double z = 1.96;
        double p = (double) successes / trials;
        double z2 = z * z;
        double denominator = 1.0 + z2 / trials;

        double center =
                (p + z2 / (2.0 * trials)) / denominator;

        double half =
                z * Math.sqrt(
                        p * (1.0 - p) / trials
                        + z2 / (4.0 * trials * trials))
                / denominator;

        return new double[] {
                center - half,
                center + half
        };
    }

    public static void main(String[] args) {
        int n = 10;

        int[][] edges = {
                {0,1}, {0,2}, {0,3},
                {1,2}, {1,4}, {1,5},
                {2,3}, {2,5}, {2,6},
                {3,6}, {3,7},
                {4,5}, {4,8},
                {5,6}, {5,8}, {5,9},
                {6,7}, {6,9},
                {7,9}, {8,9},
                {4,7}, {1,9}
        };

        int[][] adjacency = buildAdjacency(n, edges);
        long optimum = exactMaxCut(n, edges);

        if (optimum <= 0L) {
            throw new IllegalArgumentException(
                    "Quality ratio requires a positive optimum");
        }

        int trials = 500;
        double threshold = 0.90;

        long totalCut = 0L;
        long bestCut = Long.MIN_VALUE;
        long worstCut = Long.MAX_VALUE;
        int successes = 0;
        boolean guaranteeHolds = true;

        double meanQuality = 0.0;
        double m2 = 0.0;
        double[] qualities = new double[trials];

        for (int trial = 0; trial < trials; trial++) {
            long seed = 20261110L + trial;
            Random random = new Random(seed);

            boolean[] side =
                    randomizedGreedyCut(adjacency, random);

            long value = cutValue(edges, side);
            double quality = value / (double) optimum;

            qualities[trial] = quality;
            totalCut += value;
            bestCut = Math.max(bestCut, value);
            worstCut = Math.min(worstCut, value);

            if (quality >= threshold) {
                successes++;
            }

            // This greedy construction guarantees cut >= |E|/2.
            if (2L * value < edges.length) {
                guaranteeHolds = false;
            }

            // Welford's online mean and sum of squares.
            double delta = quality - meanQuality;
            meanQuality += delta / (trial + 1);
            double deltaAfter = quality - meanQuality;
            m2 += delta * deltaAfter;
        }

        Arrays.sort(qualities);

        double medianQuality =
                (qualities[trials / 2 - 1]
                + qualities[trials / 2]) / 2.0;

        double successRate =
                (double) successes / trials;

        double[] wilson =
                wilsonInterval(successes, trials);

        double sampleVariance = m2 / (trials - 1);
        double standardError =
                Math.sqrt(sampleVariance / trials);

        // Large-sample normal approximation.
        double meanMargin = 1.96 * standardError;

        System.out.println("Vertices: " + n);
        System.out.println("Edges: " + edges.length);
        System.out.println("Exact optimum: " + optimum);
        System.out.println("Randomized trials: " + trials);

        System.out.printf(
                Locale.ROOT, "Mean cut: %.3f%n",
                (double) totalCut / trials);

        System.out.printf(
                Locale.ROOT, "Mean quality ratio: %.3f%n",
                meanQuality);

        System.out.printf(
                Locale.ROOT, "Median quality ratio: %.3f%n",
                medianQuality);

        System.out.printf(
                Locale.ROOT,
                "Success threshold (>=0.900): %d/%d = %.3f%n",
                successes, trials, successRate);

        System.out.printf(
                Locale.ROOT, "95%% Wilson CI: [%.3f, %.3f]%n",
                wilson[0], wilson[1]);

        System.out.printf(
                Locale.ROOT,
                "95%% mean CI (normal approx): [%.3f, %.3f]%n",
                meanQuality - meanMargin,
                meanQuality + meanMargin);

        System.out.println(
                "Best/worst cut: " + bestCut + " / " + worstCut);

        System.out.println(
                "Guarantee every run >= ceil(m/2): "
                + guaranteeHolds);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 RandomizedApproximationEvaluationDemo.java
java RandomizedApproximationEvaluationDemo
~~~

**Đầu ra mẫu:**

~~~text
Vertices: 10
Edges: 22
Exact optimum: 16
Randomized trials: 500
Mean cut: 15.050
Mean quality ratio: 0.941
Median quality ratio: 0.938
Success threshold (>=0.900): 362/500 = 0.724
95% Wilson CI: [0.683, 0.761]
95% mean CI (normal approx): [0.936, 0.946]
Best/worst cut: 16 / 12
Guarantee every run >= ceil(m/2): true
~~~

### Những gì chương trình chứng minh được

- Exact oracle xác định optimum=16 cho đồ thị mẫu.
- Mỗi lần chạy dùng một seed riêng và có thể tái lập.
- Mọi cut được tạo đều là một phân hoạch hợp lệ.
- Greedy đạt ít nhất một nửa số cạnh trên mọi đồ thị hợp lệ.
- Thống kê mô tả và confidence interval được tính từ 500 lần chạy.
- Chương trình không chọn best run làm đại diện cho một lần chạy thông thường.

**Giới hạn:** exact oracle chỉ dùng cho đồ thị nhỏ; ví dụ thống kê chỉ đại diện cho đồ thị đã chọn và cơ chế random seed của chương trình. Mã được trình bày như một chương trình Java 17+ độc lập; cần biên dịch trong môi trường JDK để xác nhận runtime thực tế.

## 26. Đọc kết quả mà không kết luận quá mức

Mean quality 0.941 có nghĩa là **trung bình trên 500 lần chạy của instance này**, ratio đạt khoảng 94.1%.

Median 0.938 có nghĩa ít nhất một nửa mẫu có quality không thấp hơn khoảng 0.938 và ít nhất một nửa không cao hơn mức này (tùy quy ước median khi số mẫu chẵn).

Success rate 0.724 là tỷ lệ lần chạy đạt threshold 0.90. Wilson CI [0.683,0.761] phản ánh bất định lấy mẫu cho xác suất success dưới mô hình Bernoulli.

Khoảng mean [0.936,0.946] dùng normal approximation trên mẫu 500 run. Nó không phải bảo đảm rằng mọi input mới có mean trong khoảng ấy.

### Ba phát biểu khác nhau

- **Guarantee:** thuật toán luôn cắt ít nhất một nửa số cạnh.
- **Observation:** trong 500 run, lần tệ nhất đạt 12/16=0.75.
- **Estimate:** mean quality trên instance này khoảng 0.941.

Không được thay phát biểu thứ nhất bằng thứ hai hoặc thứ ba.

## 27. Runtime, memory và chất lượng theo thời gian

Một heuristic tốt hơn có thể tốn thời gian hơn. Vì vậy cần báo:

- Runtime median và p95.
- Memory peak.
- Số lần đánh giá objective.
- Số restarts.
- Chất lượng sau các mốc thời gian.
- Time-to-target: thời gian cần để đạt quality threshold.

### Benchmark Java

Khi đo runtime Java:

1. Tách thời gian compile/JVM startup khỏi thời gian thuật toán nếu mục tiêu là runtime steady-state.
2. Chạy warm-up để JVM JIT có cơ hội tối ưu.
3. Dùng **System.nanoTime()** cho khoảng thời gian.
4. Không trộn thời gian in log/I/O vào thuật toán nếu không phải chi phí production.
5. Lặp nhiều lần và báo median, p95 cùng môi trường chạy.
6. Giữ cùng giới hạn heap, CPU và tải hệ thống khi so sánh.

Một microbenchmark nghiêm túc có thể dùng JMH; đừng suy luận từ một lần gọi System.currentTimeMillis.

### Anytime algorithm

Nếu thuật toán có thể cải thiện lời giải theo thời gian, hãy vẽ:

**best quality so far vs elapsed time**.

Một thuật toán có thể chậm lúc đầu nhưng đạt chất lượng cao sau 10 giây; thuật toán khác đạt chất lượng tốt trong 100 ms. Deadline của ứng dụng quyết định lựa chọn.

## 28. Những lỗi đánh giá thường gặp

1. **Chỉ chạy một seed:** không đo được variability.
2. **Chỉ báo best run:** che giấu chất lượng điển hình và chi phí restart.
3. **Dùng success không định nghĩa:** người đọc không biết điều kiện đạt là gì.
4. **Gọi best-known là OPT:** khẳng định quá mức nếu chưa có chứng minh.
5. **Dùng ratio sai chiều:** maximize và minimize có công thức khác nhau.
6. **Dùng ratio khi OPT=0:** mẫu số không xác định.
7. **Đánh giá objective nhưng bỏ feasibility:** lời giải vi phạm constraint vẫn được tính điểm.
8. **Chỉ báo mean:** outlier và tail failure bị che.
9. **Chỉ báo median:** tail failure nghiêm trọng có thể biến mất.
10. **Bỏ confidence interval:** tỷ lệ thành công được trình bày như số chắc chắn.
11. **Dùng Wald interval cho p gần 0 hoặc 1 mà không cân nhắc:** khoảng có thể kém.
12. **Chọn sample size tùy ý:** không xét precision mong muốn.
13. **Xem 500 seed trên một instance là 500 instance độc lập:** nhầm hai nguồn biến động.
14. **Tuning trên test set:** làm kết quả đánh giá lạc quan.
15. **So sánh ngân sách không bằng nhau:** thuật toán có nhiều restart hơn được lợi.
16. **So A/B trên các tập input khác nhau:** khác biệt có thể do dữ liệu.
17. **Chỉ báo p-value:** thiếu effect size và ý nghĩa thực tế.
18. **Thử nhiều metric rồi chỉ chọn metric đẹp:** multiple comparisons và selective reporting.
19. **Không lưu seed:** khó tái lập lỗi hoặc kết quả.
20. **Dùng cùng seed nhưng không mô tả cách ghép:** tưởng paired experiment trong khi randomness không tương ứng.
21. **Không giữ phiên bản code/config:** kết quả không thể truy nguyên.
22. **Đo thời gian gồm cả console output:** benchmark sai mục tiêu.
23. **Bỏ qua JVM warm-up:** kết quả Java không ổn định.
24. **Dùng một lần chạy runtime:** không thấy p95 và tail latency.
25. **Gộp nhiều instance thành một mean không trọng số:** có thể làm lệch ý nghĩa.
26. **Để instance lớn lấn át tất cả instance nhỏ:** trọng số không đúng mục tiêu.
27. **Dùng bound sai chiều:** quality lower bound bị báo quá lạc quan.
28. **Coi empirical worst là theoretical worst-case:** mẫu hữu hạn không chứng minh điều đó.
29. **Dùng guarantee kỳ vọng như guarantee từng run:** hai loại xác suất khác nhau.
30. **Nhầm E[ALG]/OPT với E[OPT/ALG] ở bài minimize:** phép lấy kỳ vọng không tuyến tính qua phép chia.
31. **Không tách failure do timeout khỏi failure do chất lượng:** hai vấn đề khác nhau.
32. **Không tính fallback trong policy production:** kết quả đánh giá không giống hệ thống thật.
33. **Tự đặt penalty không có căn cứ:** objective thay đổi.
34. **Xóa input duplicates trước khi đo:** có thể đổi bài toán.
35. **Chỉ thử dữ liệu ngẫu nhiên:** bỏ qua worst-case cấu trúc.
36. **Không thử dữ liệu lệch phân phối:** đánh giá không phản ánh production.
37. **Coi confidence interval là guarantee deterministic:** sai bản chất thống kê.
38. **Dùng nhiều seed liên tiếp rồi giả định độc lập tuyệt đối:** cần xem PRNG và thiết kế lấy mẫu.
39. **Bỏ qua phiên bản PRNG/JDK:** tái lập có thể khác nếu thay đổi thuật toán sinh số.
40. **Không công bố số lần chạy và tiêu chí dừng:** không thể hiểu budget thực tế.

## 29. Bài tập tự luyện có đáp án

**Câu 1.** Thuật toán luôn đúng nhưng runtime thay đổi theo seed thuộc kiểu nào?  
**Đáp án:** Mô hình Las Vegas là ví dụ điển hình.

**Câu 2.** Thuật toán chạy trong giới hạn thời gian cố định nhưng có xác suất trả lời sai là gì?  
**Đáp án:** Monte Carlo.

**Câu 3.** Bài maximize có OPT=100, ALG=90, quality ratio?  
**Đáp án:** 0.90.

**Câu 4.** Bài minimize có OPT=100, ALG=125, quality ratio?  
**Đáp án:** 0.80.

**Câu 5.** Approximation factor α=2 cho bài maximize cam kết gì?  
**Đáp án:** ALG≥OPT/2.

**Câu 6.** Approximation factor α=1.5 cho bài minimize cam kết gì?  
**Đáp án:** ALG≤1.5×OPT.

**Câu 7.** Một lời giải objective tốt nhưng vi phạm hard constraint có phải feasible không?  
**Đáp án:** Không.

**Câu 8.** 362 lần thành công trong 500 run cho p̂ bao nhiêu?  
**Đáp án:** 0.724.

**Câu 9.** Wilson interval dùng để ước lượng điều gì?  
**Đáp án:** Khoảng tin cậy cho xác suất thành công của các thử nghiệm Bernoulli.

**Câu 10.** Vì sao không chỉ dùng mean?  
**Đáp án:** Mean có thể che outlier và tail failures; cần thêm median/quantiles.

**Câu 11.** Với quality trong [0,1], Hoeffding cần bao nhiêu mẫu cho ε=0.05, δ=0.05 theo bound cơ bản?  
**Đáp án:** Ít nhất 738.

**Câu 12.** 500 seed trên một đồ thị đo biến động nào?  
**Đáp án:** Chủ yếu đo biến động do randomness trên instance đó.

**Câu 13.** Muốn đánh giá tổng quát trên input population cần gì thêm?  
**Đáp án:** Nhiều instance được lấy mẫu phù hợp.

**Câu 14.** Khi chưa biết OPT của bài maximize, bound nào giúp chứng nhận quality lower bound?  
**Đáp án:** Upper bound UB≥OPT, dùng ALG/UB.

**Câu 15.** Khi chưa biết OPT của bài minimize, bound nào giúp chứng nhận quality lower bound?  
**Đáp án:** Lower bound LB≤OPT, dùng LB/ALG.

**Câu 16.** Vì sao cần ghép A và B trên cùng instance?  
**Đáp án:** Giảm nhiễu do độ khó khác nhau giữa input.

**Câu 17.** Có thể chỉ so best-of-100 của A với một run của B không?  
**Đáp án:** Không công bằng nếu budget khác; phải so cùng policy/budget.

**Câu 18.** Trong Max-Cut, một cạnh được tính vào cut khi nào?  
**Đáp án:** Hai đầu cạnh thuộc hai phía khác nhau.

**Câu 19.** Exact Max-Cut với 10 đỉnh cần duyệt bao nhiêu partition nếu cố định đỉnh 0?  
**Đáp án:** 2⁹=512.

**Câu 20.** Greedy Max-Cut trong ví dụ bảo đảm tối thiểu bao nhiêu cạnh?  
**Đáp án:** Ít nhất |E|/2, làm tròn lên vì cut là số nguyên.

**Câu 21.** OPT=16, ALG=12, quality?  
**Đáp án:** 0.75.

**Câu 22.** 72.4% success trên một instance có chứng minh 72.4% trên mọi graph không?  
**Đáp án:** Không.

**Câu 23.** Một confidence interval 95% có phải guarantee cho từng input mới không?  
**Đáp án:** Không.

**Câu 24.** Vì sao dùng System.nanoTime() thay currentTimeMillis() khi benchmark khoảng thời gian?  
**Đáp án:** nanoTime được thiết kế để đo elapsed time đơn điệu.

**Câu 25.** Nếu quality threshold được chọn sau khi xem 100 ngưỡng khác nhau, rủi ro là gì?  
**Đáp án:** Selective reporting/multiple comparisons.

**Câu 26.** Nếu một policy chạy 10 restarts và chọn best, đơn vị đánh giá nên là gì?  
**Đáp án:** Toàn bộ policy 10 restarts với ngân sách thời gian tương ứng.

## 30. Checklist thiết kế một báo cáo đánh giá

1. Đã nêu rõ bài toán maximize/minimize/feasibility chưa?
2. Đã định nghĩa objective và đơn vị chưa?
3. Đã xác định hard constraints và soft constraints chưa?
4. Đã tách tính feasible khỏi chất lượng chưa?
5. Đã xác định thuật toán Monte Carlo, Las Vegas hay heuristic approximate chưa?
6. Đã ghi rõ guarantee lý thuyết hay chỉ là quan sát thực nghiệm chưa?
7. Đã xác định OPT bằng exact oracle hay chỉ best-known/bounds chưa?
8. Nếu dùng bound, đã dùng đúng chiều cho maximize/minimize chưa?
9. Ratio có hợp lệ khi OPT bằng 0 hoặc âm không?
10. Đã định nghĩa success threshold trước thí nghiệm chưa?
11. Đã chạy nhiều seed trên cùng instance chưa?
12. Đã lấy mẫu nhiều instance nếu cần tổng quát hóa chưa?
13. Đã lưu seed, input ID, config, code version và runtime environment chưa?
14. Đã báo mean, median và quantiles phù hợp chưa?
15. Đã báo feasibility rate và success rate chưa?
16. Đã tính confidence interval phù hợp chưa?
17. Sample size có đáp ứng precision mong muốn không?
18. Đã tách biến động do seed với biến động do instance chưa?
19. Đã dùng baseline đủ mạnh và budget công bằng chưa?
20. Đã cân nhắc paired comparison, effect size và multiple comparisons chưa?
21. Đã đo runtime median/p95 và memory chưa?
22. Đã tách compile, warm-up, I/O và thời gian thuật toán chưa?
23. Nếu dùng restart, đã tính toàn bộ budget của restart policy chưa?
24. Đã kiểm tra worst-case cấu trúc và input lệch phân phối chưa?
25. Đã kiểm tra kết quả bằng exact/brute oracle trên instance nhỏ chưa?
26. Đã tránh coi best observed là worst-case guarantee chưa?
27. Đã phân biệt expected guarantee với per-run guarantee chưa?
28. Đã ghi giới hạn và giả thiết của thống kê chưa?
29. Người khác có thể tái lập thí nghiệm từ báo cáo không?
30. Kết luận có đúng phạm vi dữ liệu đã đo không?

**Kết luận:** đánh giá một lời giải ngẫu nhiên hoặc gần đúng cần kết hợp **tính khả thi, quality ratio hoặc additive gap, phân phối kết quả, xác suất đạt ngưỡng, độ bất định thống kê và chi phí tài nguyên**. Exact oracle rất hữu ích trên input nhỏ; với input lớn, cần bound và best-known được gắn nhãn chính xác. Nhiều seed cho biết độ biến động do randomness, còn nhiều instance mới cho biết khả năng tổng quát hóa. Một báo cáo tốt luôn phân biệt rõ **bảo đảm lý thuyết, kết quả quan sát và ước lượng thống kê**, nhờ đó người đọc hiểu thuật toán tốt đến đâu và trong điều kiện nào.
