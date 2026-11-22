# Nguồn lực: Sử dụng ước lượng ba điểm khi cần thể hiện độ bất định

## 1. Vì sao một con số duy nhất thường không đủ?

Khi lập kế hoạch kiểm thử, nhóm cần ước lượng công sức, thời gian, nhân lực và tài nguyên hỗ trợ. Một con số duy nhất như “5 ngày” có thể tạo cảm giác chắc chắn hơn mức hiểu biết thực tế. Công việc có thể kéo dài hơn do dữ liệu khó chuẩn bị, môi trường chưa ổn định, defect phát sinh hoặc chuyên gia cần thiết chưa sẵn sàng.

**Ước lượng ba điểm (three-point estimation)** biểu diễn một công việc bằng ba khả năng:

- **Lạc quan (Optimistic — O):** thời lượng hoặc công sức nếu các điều kiện thuận lợi và ít trở ngại.
- **Khả dĩ nhất (Most likely — M):** kết quả có khả năng xảy ra nhất trong điều kiện đã nêu.
- **Bi quan (Pessimistic — P):** thời lượng hoặc công sức nếu các trở ngại hợp lý xuất hiện, nhưng vẫn trong phạm vi giả định.

Ba điểm không phải ba cam kết khác nhau. Chúng mô tả khoảng bất định để nhóm hiểu điều gì có thể thay đổi và lập kế hoạch với nhận thức thực tế hơn.

Trong **VALIDATION_TESTING_STRATEGY**, ước lượng ba điểm hữu ích khi lập kế hoạch cho hoạt động kiểm thử có độ biến động đáng kể, chẳng hạn thiết kế test cho yêu cầu mới, chuẩn bị dữ liệu phức tạp, tích hợp môi trường, phân tích defect, kiểm thử hiệu năng hoặc phối hợp với nhà cung cấp. Nó cũng giúp dự báo nhu cầu nhân lực, thiết bị, môi trường và thời gian dự phòng.

## 2. Ba điểm O, M và P

### 2.1. Điểm lạc quan — O

O là kịch bản thuận lợi nhưng vẫn khả thi, dựa trên điều kiện cụ thể:

- Yêu cầu và acceptance criteria đã rõ.
- Dữ liệu có sẵn hoặc dễ tạo.
- Môi trường hoạt động ổn định.
- Người có kỹ năng phù hợp sẵn sàng.
- Không phát hiện vấn đề lớn cần điều tra.

Không dùng O như mục tiêu bắt buộc hoặc “thời gian tối thiểu tuyệt đối” nếu không có căn cứ. Nó mô tả một trường hợp tốt có thể xảy ra khi các giả định thuận lợi giữ đúng.

### 2.2. Điểm khả dĩ nhất — M

M là kết quả được xem là có khả năng xảy ra nhất khi xét điều kiện thông thường:

- Có một số câu hỏi cần làm rõ.
- Một phần dữ liệu hoặc môi trường cần chuẩn bị.
- Có thể phát sinh lỗi nhỏ và phải điều tra.
- Công việc diễn ra theo cách nhóm thường gặp.

M không nhất thiết bằng trung bình của O và P. Nếu phần lớn lần thực hiện trước đây tập trung quanh một giá trị, M có thể nằm gần một đầu của khoảng ước lượng.

### 2.3. Điểm bi quan — P

P là kịch bản bất lợi có cơ sở, ví dụ:

- Một phụ thuộc chưa ổn định.
- Dữ liệu phải tạo lại hoặc làm sạch.
- Có nhiều vòng sửa test hoặc làm rõ yêu cầu.
- Một defect cần phối hợp nhiều nhóm.
- Thiết bị, license hoặc môi trường bị giới hạn.

P không nên là một con số tùy tiện để “cộng thật nhiều buffer”. Hãy nêu các sự kiện có thể khiến công việc đi tới P. Nếu có một rủi ro hiếm nhưng tác động rất lớn nằm ngoài P, cần ghi riêng và đánh giá như một rủi ro hoặc kịch bản bổ sung.

### 2.4. Giữ cùng đơn vị và cùng phạm vi

O, M và P phải đo cùng một đại lượng và cùng phạm vi:

- Cùng là giờ công, ngày công hoặc ngày lịch.
- Cùng bao gồm hoặc loại trừ thời gian review, chờ môi trường và sửa lỗi.
- Cùng giả định về nhân lực, kỹ năng và công cụ.
- Cùng phạm vi đầu ra và tiêu chí hoàn tất.

Không so sánh O là ngày công của một kỹ sư với P là ngày lịch của cả nhóm. Nếu cần ước lượng cả effort lẫn elapsed time, lập hai bộ ước lượng riêng và ghi rõ các phụ thuộc.

## 3. Công thức ước lượng ba điểm

Có nhiều cách chuyển ba điểm thành một giá trị kỳ vọng. Hai cách thường gặp là PERT có trọng số và trung bình tam giác.

### 3.1. PERT có trọng số

PERT (Program Evaluation and Review Technique) đặt trọng số lớn hơn cho M:

\[
E = \frac{O + 4M + P}{6}
\]

Trong đó:

- \(E\) là giá trị kỳ vọng dùng để lập kế hoạch.
- \(O\) là ước lượng lạc quan.
- \(M\) là ước lượng khả dĩ nhất.
- \(P\) là ước lượng bi quan.

Độ lệch chuẩn xấp xỉ thường dùng:

\[
\sigma = \frac{P-O}{6}
\]

Phương sai xấp xỉ:

\[
\sigma^2 = \left(\frac{P-O}{6}\right)^2
\]

PERT phù hợp khi muốn nhấn mạnh kịch bản khả dĩ nhất và có một phân phối ước lượng lệch quanh M. Công thức độ lệch chuẩn là xấp xỉ dựa trên mô hình PERT; không nên diễn giải nó như một khoảng tin cậy chính xác nếu chưa kiểm chứng giả định phân phối.

### 3.2. Trung bình tam giác

Phương pháp tam giác coi ba điểm là ba tham số của phân phối tam giác:

\[
E_{\text{triangular}} = \frac{O+M+P}{3}
\]

Phương pháp này đơn giản và cho trọng số bằng nhau đối với ba điểm. Nó có thể phù hợp khi nhóm chỉ cần một giá trị kỳ vọng đơn giản và không muốn dùng trọng số PERT.

### 3.3. Chọn phương pháp và giữ nhất quán

| Phương pháp | Công thức kỳ vọng | Đặc điểm |
| --- | --- | --- |
| PERT | \((O+4M+P)/6\) | Nhấn mạnh giá trị khả dĩ nhất |
| Tam giác | \((O+M+P)/3\) | Đơn giản, trọng số ba điểm bằng nhau |

Không chọn công thức sau khi nhìn kết quả chỉ để có con số thuận lợi. Nhóm nên thống nhất phương pháp theo loại công việc, cách dữ liệu lịch sử được hiệu chỉnh và mục đích ra quyết định. Nếu so sánh nhiều dự án hoặc nhiều lần ước lượng, hãy dùng cùng một phương pháp hoặc ghi rõ sự khác biệt.

## 4. Ví dụ tính toán cho một hoạt động kiểm thử

Giả sử nhóm cần thiết kế và chạy một đợt regression test cho dịch vụ đặt lịch. Các giá trị được ước lượng bằng ngày công (person-days):

| Công việc | O | M | P |
| --- | ---: | ---: | ---: |
| Thiết kế test và review yêu cầu | 2 | 3 | 6 |
| Chuẩn bị môi trường và dữ liệu | 1 | 2 | 5 |
| Thực thi test và thu thập bằng chứng | 3 | 5 | 9 |
| Phân tích defect và xác nhận lại | 1 | 2 | 6 |

Áp dụng PERT cho từng công việc:

| Công việc | Phép tính | E (ngày công) |
| --- | --- | ---: |
| Thiết kế test | \((2+4×3+6)/6\) | 3,33 |
| Môi trường và dữ liệu | \((1+4×2+5)/6\) | 2,33 |
| Thực thi test | \((3+4×5+9)/6\) | 5,33 |
| Phân tích và xác nhận | \((1+4×2+6)/6\) | 2,50 |
| **Tổng kỳ vọng** | **Tổng các E** | **13,50** |

Nhóm có thể dùng khoảng tổng đơn giản từ 7 ngày công ở kịch bản lạc quan đến 26 ngày công ở kịch bản bi quan để nhìn thấy biên của các ước lượng công việc. Tổng kỳ vọng PERT là 13,5 ngày công.

Con số 13,5 không có nghĩa công việc chắc chắn hoàn tất sau 13,5 ngày lịch. Đây là tổng effort kỳ vọng. Thời gian lịch còn phụ thuộc số người, kỹ năng, khả năng làm song song, lịch nghỉ, thời gian chờ môi trường và các phụ thuộc.

## 5. Phân biệt công sức, thời lượng và năng lực nguồn lực

Ba đại lượng này liên quan nhưng không thể thay thế cho nhau.

### 5.1. Công sức (effort)

Effort là lượng lao động cần để hoàn thành công việc, thường đo bằng giờ công hoặc ngày công. Ví dụ, thiết kế test cần 3 ngày công của kỹ sư kiểm thử.

### 5.2. Thời lượng (duration)

Duration là thời gian lịch từ lúc bắt đầu đến khi hoàn tất. Một công việc 6 ngày công có thể kéo dài 3 ngày nếu có hai người làm song song và công việc có thể chia tách; cũng có thể kéo dài hơn 6 ngày lịch nếu người thực hiện chỉ dành một phần thời gian hoặc phải chờ phụ thuộc.

### 5.3. Năng lực (capacity)

Capacity là thời gian hoặc khối lượng công việc mà nguồn lực có thể cung cấp trong một khoảng thời gian:

- Một kỹ sư toàn thời gian có lịch làm việc 5 ngày/tuần có capacity danh nghĩa 5 ngày công/tuần.
- Nếu chỉ dành 60% thời gian cho dự án, capacity kế hoạch là khoảng 3 ngày công/tuần trước khi trừ họp, nghỉ và công việc hỗ trợ khác.
- Một môi trường staging chỉ có thể được đặt trước 20 giờ/tuần là một giới hạn capacity khác với effort của kỹ sư.

Khi lập kế hoạch, phải chuyển effort thành duration dựa trên capacity thực tế và trình tự phụ thuộc. Không chia effort cho số người một cách máy móc nếu công việc cần chuyên môn riêng hoặc không thể thực hiện song song.

### 5.4. Lập kế hoạch theo vai trò và kỹ năng

Không phải mọi ngày công đều hoán đổi được. Ví dụ:

- Kỹ sư automation xây dựng framework và script.
- Chuyên gia domain xác nhận oracle và quy tắc nghiệp vụ.
- Kỹ sư performance thiết kế workload và phân tích bottleneck.
- Kỹ sư môi trường cấp phát cluster, network và credential.
- Người kiểm thử bảo mật xác nhận quyền và cấu hình.

Ước lượng theo vai trò khi kỹ năng là ràng buộc. Nếu P tăng vì chuyên gia chỉ có thể tham gia một vài khung giờ, ghi đây là phụ thuộc capacity thay vì cộng chung vào effort kỹ thuật.

## 6. Dùng ước lượng ba điểm để lập kế hoạch nguồn lực

### 6.1. Xác định nguồn lực cần thiết

Ngoài nhân lực, hoạt động kiểm thử có thể cần:

- Môi trường test, staging hoặc performance riêng.
- Thiết bị di động, trình duyệt và license.
- CI runner, máy ảo, container hoặc cluster.
- Database, message broker và service sandbox.
- Dataset, tài khoản, secret và công cụ quản lý dữ liệu.
- Công cụ quan sát, lưu trace, video và artifact.
- Hỗ trợ từ nhóm sản phẩm, vận hành, bảo mật hoặc nhà cung cấp.

Với mỗi nguồn lực, cần ước lượng đại lượng phù hợp. Ví dụ:

| Nguồn lực | Đại lượng có thể ước lượng | Yếu tố bất định |
| --- | --- | --- |
| Nhân lực kiểm thử | Ngày công theo vai trò | Phạm vi test, độ rõ yêu cầu, số defect |
| Môi trường staging | Giờ/ngày sử dụng | Thời gian cấp phát, xung đột lịch, readiness |
| Thiết bị | Số thiết bị hoặc ngày thiết bị | Ma trận hỗ trợ, thiết bị sẵn có |
| CI runner | Giờ runner hoặc số job đồng thời | Thời lượng suite, retry, tải nền |
| Dataset | Giờ chuẩn bị và dung lượng | Chất lượng nguồn, quan hệ dữ liệu, cleanup |
| Sandbox provider | Số lượt gọi hoặc cửa sổ sử dụng | Quota, lịch bảo trì, rate limit |

### 6.2. Tách effort thực hiện khỏi thời gian chờ

Một nhóm có thể cần 2 ngày công để cấu hình môi trường, nhưng phải chờ 4 ngày lịch để nhà cung cấp cấp quyền. Nếu gộp hai đại lượng thành “6 ngày công”, kế hoạch nhân lực sẽ sai.

Hãy ghi riêng:

- Effort để thực hiện công việc.
- Lead time hoặc thời gian chờ phụ thuộc.
- Thời gian chiếm dụng tài nguyên.
- Ngày bắt đầu sớm nhất và mốc sẵn sàng cần có.

Ước lượng ba điểm có thể áp dụng cho từng đại lượng, nhưng phải ghi đúng tên và đơn vị.

### 6.3. Kiểm tra giới hạn tài nguyên

Sau khi có kỳ vọng và khoảng ước lượng, kiểm tra:

- Có đủ người với đúng kỹ năng trong cửa sổ cần thiết không?
- Môi trường có đủ capacity cho test song song không?
- License hoặc thiết bị có bị dùng chung không?
- Sandbox có đủ quota không?
- Có thể chia test theo nhóm hoặc theo thời gian không?
- Nếu kịch bản P xảy ra, tài nguyên bổ sung nào cần được kích hoạt?

Không chỉ kiểm tra tổng số người. Một dự án có thể đủ tổng ngày công nhưng vẫn trễ nếu tất cả công việc cần cùng một chuyên gia hoặc cùng một môi trường.

## 7. Quy trình thực hiện ước lượng ba điểm

### 7.1. Bước 1 — Chia nhỏ công việc

Phân rã phạm vi thành các work package đủ rõ để người ước lượng hiểu đầu vào, đầu ra và điều kiện hoàn tất. Ví dụ:

- Phân tích yêu cầu và rủi ro.
- Thiết kế test case.
- Chuẩn bị dữ liệu.
- Cấp phát và xác minh môi trường.
- Viết automation.
- Thực thi test.
- Phân tích và phân loại defect.
- Retest và regression.
- Báo cáo bằng chứng.

Không ước lượng một mục quá lớn như “test toàn bộ sản phẩm” nếu các phần có mức bất định khác nhau. Chia nhỏ giúp xác định nguyên nhân của khoảng chênh lệch O–P.

### 7.2. Bước 2 — Xác định giả định và loại trừ

Với mỗi work package, ghi:

- Đầu vào đã sẵn sàng hay chưa.
- Mức độ ổn định của yêu cầu.
- Số lượng luồng, dữ liệu hoặc nền tảng.
- Người và kỹ năng cần thiết.
- Phụ thuộc bên ngoài.
- Công việc nào được tính trong estimate.
- Công việc nào nằm ngoài phạm vi.

Nếu giả định thay đổi, ước lượng cần được xem xét lại. Ví dụ, estimate chuẩn bị dữ liệu giả định schema đã ổn định; khi schema đổi nhiều lần, O/M/P ban đầu không còn phù hợp.

### 7.3. Bước 3 — Thu thập cơ sở ước lượng

Ưu tiên dùng:

- Dữ liệu actual từ công việc tương tự.
- Kết quả các lần chạy test trước.
- Kích thước và độ phức tạp của phạm vi.
- Số lượng nền tảng, vai trò và biến thể dữ liệu.
- Kinh nghiệm của người trực tiếp thực hiện.
- Các defect và trở ngại đã xảy ra trong quá khứ.

Nếu chưa có dữ liệu lịch sử, hãy ghi rõ estimate dựa trên chuyên gia và mức tin cậy còn hạn chế. Có thể thực hiện một discovery spike nhỏ để giảm bất định trước khi lập kế hoạch chi tiết.

### 7.4. Bước 4 — Ước lượng độc lập

Khi có nhiều người tham gia, có thể yêu cầu họ ước lượng độc lập trước khi thảo luận. Cách này giảm ảnh hưởng của người nói đầu tiên hoặc áp lực đồng thuận.

Sau đó:

1. So sánh O, M và P của từng người.
2. Tìm hiểu lý do khác biệt.
3. Kiểm tra giả định, phạm vi và dữ liệu lịch sử.
4. Thống nhất một bộ ba điểm có căn cứ.
5. Ghi lại các bất đồng hoặc rủi ro chưa giải quyết.

Không lấy trung bình cơ học của các con số nếu người ước lượng đang giả định phạm vi khác nhau.

### 7.5. Bước 5 — Tính kỳ vọng và độ phân tán

Chọn PERT hoặc tam giác theo quy ước đã thống nhất. Nếu dùng PERT, tính E và độ lệch chuẩn xấp xỉ cho từng work package. Giữ cả ba điểm trong hồ sơ; không chỉ lưu giá trị kỳ vọng.

### 7.6. Bước 6 — Tổng hợp và kiểm tra phụ thuộc

Với các công việc có thể xem là độc lập, tổng kỳ vọng bằng tổng kỳ vọng từng công việc. Nếu dùng PERT và giả định độc lập, có thể cộng phương sai để ước lượng phương sai tổng:

\[
E_{\text{total}} = \sum_i E_i
\]

\[
\sigma^2_{\text{total}} = \sum_i \sigma_i^2
\quad \text{(khi các công việc độc lập)}
\]

Nếu các công việc cùng chịu một yếu tố như môi trường chưa ổn định hoặc yêu cầu thay đổi, bất định có tương quan. Khi đó, phương sai tổng có thêm các thành phần hiệp phương sai:

\[
\operatorname{Var}(T)=\sum_i \operatorname{Var}(T_i)
+2\sum_{i<j}\operatorname{Cov}(T_i,T_j)
\]

Không nên giả định độc lập khi nhiều hạng mục phụ thuộc cùng một dịch vụ, chuyên gia hoặc quyết định.

### 7.7. Bước 7 — Chuyển thành kế hoạch nguồn lực

Ánh xạ effort và duration sang:

- Người/nhóm theo vai trò.
- Thời điểm cần từng kỹ năng.
- Cửa sổ sử dụng môi trường và thiết bị.
- Capacity của CI, sandbox và license.
- Mốc chuẩn bị, thực thi, retest và báo cáo.
- Phương án khi kịch bản bi quan xảy ra.

Kế hoạch cần thể hiện các ràng buộc và đường găng. Không cộng tất cả ngày công rồi xem đó là ngày hoàn thành.

### 7.8. Bước 8 — Rà soát và cập nhật

Khi có actual hoặc thông tin mới:

- So sánh actual với O/M/P và E.
- Ghi lý do chênh lệch.
- Cập nhật giả định hoặc estimate phần việc còn lại.
- Điều chỉnh capacity và mốc nguồn lực.
- Lưu phiên bản estimate để thấy chất lượng dự báo theo thời gian.

Không viết lại ước lượng ban đầu để làm cho dự báo trông chính xác. Giữ baseline và ghi forecast mới riêng.

## 8. Đọc và quản lý độ bất định

### 8.1. Khoảng O–P cho biết điều gì?

Độ rộng \(P-O\) cho thấy khoảng bất định được nhóm mô tả. Khoảng càng rộng thường cho thấy:

- Phạm vi hoặc yêu cầu chưa rõ.
- Thiếu dữ liệu lịch sử.
- Phụ thuộc bên ngoài chưa chắc chắn.
- Công việc có nhiều nhánh hoặc điều kiện.
- Khả năng phát sinh defect hoặc vòng lặp sửa đổi cao.

Khoảng hẹp không tự động đồng nghĩa estimate chính xác. Nếu nhóm thiếu thông tin và đặt O, M, P quá gần nhau, độ bất định có thể đang bị đánh giá thấp.

### 8.2. Độ lệch chuẩn không tự động là khoảng tin cậy

Với PERT, \(\sigma=(P-O)/6\) là độ lệch chuẩn xấp xỉ theo mô hình. Không nên tự động nói “E ± 1σ là 68% chắc chắn” hoặc “P là P90” nếu chưa xác định và kiểm chứng phân phối, cách lấy mẫu cùng các giả định.

Nếu quyết định cần một mức xác suất cụ thể như P80 hoặc P90, cần có mô hình phân phối phù hợp, dữ liệu lịch sử hoặc mô phỏng Monte Carlo đã được hiệu chỉnh. Ba điểm đơn lẻ không đủ để bảo đảm một xác suất chính xác.

### 8.3. Khi nào dùng mô phỏng Monte Carlo?

Monte Carlo có thể hữu ích khi:

- Nhiều work package có khoảng ước lượng khác nhau.
- Các công việc có phụ thuộc hoặc có thể chạy song song.
- Nhóm cần xác suất đạt một mốc ngày hoặc giới hạn ngân sách.
- Có thể mô hình hóa phân phối và tương quan hợp lý.

Mỗi lần mô phỏng lấy một giá trị từ phân phối của từng công việc, tính lịch hoặc tổng effort theo phụ thuộc, rồi lặp nhiều lần. Kết quả là phân phối của tổng, có thể đọc các percentile như P50, P80 hoặc P90.

Mô phỏng không làm dữ liệu đầu vào trở nên đúng. Nếu O/M/P thiếu căn cứ hoặc mô hình tương quan sai, kết quả Monte Carlo chỉ tạo ra vẻ chính xác giả tạo.

### 8.4. Phân biệt bất định có thể ước lượng và rủi ro chưa mô hình hóa

Three-point estimate mô tả các kịch bản đã nghĩ tới. Nó không bao phủ mọi sự kiện bất ngờ. Ví dụ, nhà cung cấp ngừng dịch vụ dài ngày hoặc thay đổi pháp lý có thể vượt khỏi P đã đặt.

Với rủi ro tác động lớn:

- Ghi riêng rủi ro và điều kiện kích hoạt.
- Ước lượng xác suất/tác động nếu có cơ sở.
- Xác định biện pháp giảm thiểu hoặc phương án thay thế.
- Không giấu rủi ro hiếm trong một P quá lớn nhưng không giải thích.

## 9. Dùng kết quả để lập dự phòng và quyết định

### 9.1. Không cộng buffer tùy tiện

Buffer nên dựa trên nguồn bất định và mức rủi ro:

- Dự phòng cho vòng sửa lỗi dựa trên dữ liệu lịch sử.
- Dự phòng thời gian chờ cho nhà cung cấp dựa trên lead time.
- Dự phòng capacity môi trường cho giờ cao điểm hoặc chạy lại.
- Dự phòng chuyên gia cho các mốc review bắt buộc.

Nếu đã đưa một rủi ro vào P, không cộng thêm toàn bộ tác động đó lần nữa vào buffer mà không giải thích. Tránh double-counting.

### 9.2. Chọn mức kế hoạch theo hậu quả của việc trễ

Giá trị kỳ vọng phù hợp cho dự báo trung tâm, nhưng một mốc cam kết có thể cần mức bảo thủ hơn tùy hậu quả:

- Mốc nội bộ có thể dùng E để theo dõi forecast.
- Mốc phụ thuộc nhiều nhóm có thể cần một percentile đã được hiệu chỉnh.
- Mốc phát hành bắt buộc có thể cần phương án dự phòng và điều kiện go/no-go.

Không gọi một con số là “cam kết 90%” nếu chưa có mô hình và dữ liệu hỗ trợ.

### 9.3. Ưu tiên giảm bất định trước khi tăng nguồn lực

Nếu P rất lớn vì yêu cầu chưa rõ, tăng thêm người có thể không rút ngắn thời gian. Có thể hiệu quả hơn khi:

- Làm rõ acceptance criteria.
- Thử nghiệm kỹ thuật ngắn.
- Xác minh sandbox hoặc quyền truy cập sớm.
- Tạo dataset mẫu.
- Kiểm tra tương thích công cụ.
- Chia work package lớn thành phần nhỏ hơn.

Sau hoạt động giảm bất định, cập nhật O/M/P cho phần còn lại.

## 10. Ví dụ tổng hợp: lập kế hoạch regression campaign

Giả sử nhóm có một kỹ sư kiểm thử được phân bổ 75% thời gian trong bốn tuần làm việc. Capacity danh nghĩa là:

\[
5 \text{ ngày/tuần} \times 4 \text{ tuần} \times 0{,}75
= 15 \text{ ngày công}
\]

Ước lượng PERT của chiến dịch là 13,5 ngày công. So sánh sơ bộ cho thấy capacity danh nghĩa đủ cho effort kỳ vọng, nhưng chưa thể kết luận lịch chắc chắn đáp ứng vì:

- Kỹ sư có thể cần họp, hỗ trợ production hoặc nghỉ.
- Công việc có thể chờ môi trường hoặc chuyên gia domain.
- Một số nhiệm vụ có thể không làm song song.
- Kịch bản bi quan lên tới 26 ngày công theo tổng P của các hạng mục.

Nhóm nên:

1. Xác nhận 15 ngày công là capacity thực sau khi trừ các nghĩa vụ khác.
2. Đặt lịch môi trường và review chuyên gia trước khi bắt đầu.
3. Ưu tiên test có rủi ro cao để có tín hiệu sớm.
4. Theo dõi actual theo từng work package.
5. Chuẩn bị phương án giảm phạm vi hoặc bổ sung capacity nếu các yếu tố kích hoạt kịch bản P xuất hiện.

Ví dụ này cho thấy ước lượng ba điểm không chỉ tạo một con số; nó giúp nhóm thấy khoảng cách giữa effort dự kiến, capacity và rủi ro lịch.

## 11. Mẫu ghi nhận ước lượng ba điểm

~~~text
Work package:
Đầu ra / điều kiện hoàn tất:
Phạm vi bao gồm:
Phạm vi loại trừ:

Đại lượng ước lượng: effort / duration / resource usage
Đơn vị:
O — Lạc quan:
M — Khả dĩ nhất:
P — Bi quan:
Phương pháp: PERT / Triangular
Giá trị kỳ vọng:
Độ lệch chuẩn/phương sai (nếu dùng):

Giả định:
Yếu tố làm tăng P:
Phụ thuộc và tương quan:
Nguồn dữ liệu lịch sử:
Người ước lượng / người rà soát:
Ngày ước lượng / phiên bản:

Vai trò và capacity cần:
Môi trường / thiết bị / license:
Lead time bên ngoài:
Điều kiện kích hoạt phương án dự phòng:
Actual sau khi hoàn tất:
Lý do chênh lệch và bài học:
~~~

## 12. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng O làm cam kết | Kế hoạch thiếu thực tế | Dùng O như kịch bản thuận lợi, trình bày cả khoảng |
| Đặt P tùy ý rất lớn | Estimate mất ý nghĩa | Gắn P với trở ngại có cơ sở và phạm vi |
| Ba điểm dùng đơn vị khác nhau | Kết quả tính toán vô nghĩa | Chuẩn hóa đại lượng và đơn vị |
| Nhầm effort với duration | Lịch và nhân lực sai | Ước lượng riêng effort, lead time và capacity |
| Cộng ngày công rồi chia số người | Bỏ qua kỹ năng và phụ thuộc | Lập lịch theo vai trò, capacity và đường găng |
| Chỉ lưu giá trị E | Mất thông tin bất định | Giữ O, M, P, giả định và phương pháp |
| Coi PERT là xác suất chính xác | Tạo độ tin cậy giả | Nêu rõ giả định; hiệu chỉnh bằng actual |
| Giả định mọi công việc độc lập | Đánh giá thấp rủi ro chung | Ghi tương quan và mô hình hóa dependency |
| Cộng buffer trùng với rủi ro đã tính | Dự phòng bị tính hai lần | Theo dõi rủi ro và buffer riêng, ghi cách tính |
| Không cập nhật khi phạm vi đổi | Forecast lỗi thời | Phiên bản hóa estimate và cập nhật phần còn lại |

## 13. Checklist sử dụng ước lượng ba điểm

- [ ] Công việc đã được chia thành work package có đầu ra rõ.
- [ ] O, M và P dùng cùng đại lượng, đơn vị và phạm vi.
- [ ] Mỗi điểm có giả định và cơ sở thực tế.
- [ ] P phản ánh trở ngại hợp lý, không phải buffer tùy tiện.
- [ ] Phương pháp PERT hoặc tam giác được chọn nhất quán.
- [ ] Giá trị kỳ vọng không bị diễn giải thành cam kết chắc chắn.
- [ ] Effort, duration, lead time và capacity được phân biệt.
- [ ] Nhu cầu nhân lực được phân theo vai trò và kỹ năng.
- [ ] Môi trường, thiết bị, license, runner và sandbox được xem xét.
- [ ] Phụ thuộc và tương quan giữa công việc được ghi nhận.
- [ ] Rủi ro ngoài khoảng O–P được quản lý riêng.
- [ ] Buffer không tính trùng tác động đã nằm trong P.
- [ ] Actual được so sánh với estimate để cải thiện hiệu chỉnh.
- [ ] Thay đổi phạm vi hoặc giả định kích hoạt cập nhật estimate.

Ước lượng ba điểm giúp nhóm biểu diễn sự không chắc chắn một cách minh bạch thay vì che nó sau một con số duy nhất. Khi O, M và P có cơ sở, đơn vị nhất quán và được chuyển thành kế hoạch theo capacity cùng phụ thuộc thực tế, nhóm có thể dự báo nguồn lực tốt hơn, chuẩn bị phương án cho kịch bản bất lợi và học từ chênh lệch giữa dự báo với kết quả thực tế.
