# Trình bày độ bất định, khoảng trống và giới hạn suy luận

## Mục tiêu bài học

Số liệu kiểm thử thường được dùng để đánh giá chất lượng, so sánh bản build, quyết định phát hành và xác định nơi cần đầu tư cải thiện. Tuy nhiên, một con số không tự giải thích dữ liệu được thu thập như thế nào, phần nào chưa được kiểm tra hoặc mức độ chắc chắn của kết luận. Báo cáo ghi “tỷ lệ pass 99%” có thể tạo cảm giác an toàn, nhưng ý nghĩa sẽ rất khác nếu chỉ có mười test, nhiều test bị bỏ qua, kết quả phụ thuộc môi trường hoặc phần rủi ro quan trọng chưa được đo.

Trong VALIDATION_TESTING_STRATEGY, trình bày kết quả đo lường cần làm rõ **độ bất định, khoảng trống và giới hạn suy luận**. Độ bất định cho biết kết quả có thể dao động hoặc sai lệch đến mức nào. Khoảng trống cho biết phần đối tượng, hành vi, dữ liệu hoặc điều kiện chưa được quan sát. Giới hạn suy luận xác định điều gì có thể và không thể kết luận từ bằng chứng hiện có. Ba nội dung này giúp người đọc hiểu đúng mức độ tin cậy và đưa ra quyết định tương xứng với rủi ro.

Sau bài học, người học có thể:

- Phân biệt số đo, ước lượng, suy luận và quyết định.
- Nhận diện sai số ngẫu nhiên, sai lệch hệ thống, sai số lấy mẫu và giới hạn công cụ.
- Trình bày biến thiên, cỡ mẫu, khoảng tin cậy và các giả định của phép đo.
- Xác định khoảng trống về coverage, dữ liệu, môi trường, nền tảng và nhóm người dùng.
- Phân biệt dữ liệu bằng không, dữ liệu thiếu, chưa đo và không áp dụng.
- Tránh suy luận quá mức từ tỷ lệ, xu hướng, tương quan hoặc một lần chạy.
- Ghi rõ giới hạn của việc so sánh và ngoại suy kết quả sang production.
- Viết báo cáo đo lường cân bằng giữa kết quả, độ tin cậy, phần chưa biết và hành động tiếp theo.

## 1. Vì sao phải trình bày điều chưa chắc chắn?

Đo lường là cơ sở để ra quyết định, nhưng phép đo luôn có điều kiện và giới hạn. Một bộ kiểm thử đạt không có nghĩa mọi hành vi đều đúng; một lần chạy hiệu năng tốt không chứng minh hệ thống sẽ đáp ứng tải trong mọi thời điểm; không phát hiện defect trong một mẫu kiểm tra không chứng minh không có lỗi.

Nếu chỉ trình bày kết quả thuận lợi, người đọc có thể hiểu phạm vi bảo vệ rộng hơn thực tế. Ví dụ:

- Tỷ lệ pass 100% nhưng 20% test bị skip.
- Không có defect nghiêm trọng trong một đợt test ngắn, nhưng chức năng thanh toán chưa được kiểm tra với giao dịch đồng thời.
- P95 latency giảm 15%, nhưng bản build mới chạy trên runner có CPU nhanh hơn và cache đã warm.
- Không ghi nhận lỗi bảo mật trong phạm vi scan tự động, nhưng chưa có kiểm tra phân quyền thủ công hoặc threat-based testing.
- Tỷ lệ lỗi giảm sau khi triển khai, nhưng lưu lượng và cơ cấu người dùng cũng thay đổi.

Một báo cáo có trách nhiệm phải cho biết dữ liệu hỗ trợ kết luận nào, kết luận nào chỉ là giả thuyết và phần nào chưa được kiểm tra. Nêu giới hạn không làm giảm giá trị của kết quả; nó giúp tránh quyết định dựa trên sự chắc chắn giả tạo.

## 2. Phân biệt số đo, ước lượng, suy luận và quyết định

Các tầng này có liên hệ nhưng không đồng nghĩa:

| Tầng | Ý nghĩa | Ví dụ |
|---|---|---|
| Số đo (measurement) | Giá trị được ghi nhận theo một quy tắc và công cụ cụ thể. | 1.240 request được gửi trong một lần chạy. |
| Thống kê mô tả | Tóm tắt dữ liệu đã quan sát. | P95 latency của lần chạy là 420 ms. |
| Ước lượng (estimate) | Giá trị dùng để đại diện cho một tổng thể hoặc quá trình rộng hơn. | Ước lượng tỷ lệ lỗi request trong điều kiện tải đã chọn. |
| Suy luận (inference) | Kết luận về tổng thể, nguyên nhân hoặc hành vi chưa quan sát trực tiếp. | Bản build có thể có tỷ lệ lỗi thấp hơn trong điều kiện tương tự. |
| Quyết định (decision) | Hành động được chọn dựa trên bằng chứng, rủi ro và ngưỡng chấp nhận. | Cho phép rollout có kiểm soát với giám sát bổ sung. |

Số đo có thể chính xác về mặt ghi nhận nhưng không đại diện cho mục tiêu cần suy luận. Ví dụ, công cụ ghi đúng 1.240 request nhưng workload không đại diện cho hành vi người dùng thực tế. Tính chính xác của công cụ không bảo đảm tính phù hợp của kết luận.

### 2.1. Mô tả điều đã quan sát trước khi suy luận

Nên trình bày theo thứ tự:

1. Điều kiện và phạm vi thu thập.
2. Dữ liệu thực tế đã ghi nhận.
3. Cách tóm tắt hoặc phân tích.
4. Kết luận được dữ liệu hỗ trợ.
5. Giả định và giới hạn.
6. Quyết định hoặc bước xác minh tiếp theo.

Ví dụ:

- Quan sát: Trong ba lần chạy với 500 người dùng ảo, P95 latency lần lượt là 410, 438 và 421 ms.
- Mô tả: Các giá trị nằm trong khoảng 410–438 ms; trung vị giữa ba lần chạy là 421 ms.
- Kết luận giới hạn: Kết quả trong cấu hình và workload đã thử nằm dưới ngưỡng 500 ms.
- Giới hạn: Chưa thử tải đột biến, nhiều vùng triển khai hoặc dữ liệu production-scale.
- Hành động: Bổ sung một lần chạy tải đỉnh và kiểm tra cấu hình autoscaling trước khi kết luận về năng lực production.

Không nên viết “hệ thống luôn phản hồi dưới 500 ms” từ một số lần chạy có điều kiện.

## 3. Các nguồn độ bất định trong đo lường kiểm thử

Độ bất định có thể đến từ quá trình lấy mẫu, bản thân hệ thống, công cụ, môi trường và cách định nghĩa chỉ số. Cần nhận diện nguồn nào có khả năng ảnh hưởng đến kết luận.

### 3.1. Biến thiên ngẫu nhiên

Biến thiên ngẫu nhiên là dao động tự nhiên giữa các lần quan sát dù điều kiện được giữ tương đối giống nhau. Ví dụ:

- Thời gian phản hồi thay đổi theo lịch lập lịch CPU.
- Request gặp độ trễ mạng khác nhau.
- Tác vụ nền được xử lý với thời điểm khác nhau.
- Test có tính ngẫu nhiên tạo ra dữ liệu khác nhau.
- Tải đồng thời thay đổi nhẹ giữa các lần chạy.

Cách xử lý thường gồm chạy lặp lại, mô tả phân bố thay vì chỉ báo một giá trị và kiểm soát điều kiện có thể kiểm soát. Không nên loại bỏ các kết quả bất lợi chỉ vì chúng làm số trung bình xấu đi.

### 3.2. Sai lệch hệ thống

Sai lệch hệ thống làm các phép đo lệch theo một hướng hoặc một cách có cấu trúc. Ví dụ:

- Đồng hồ máy chạy sai hoặc khác múi giờ.
- Công cụ đo bỏ sót request thất bại.
- Dữ liệu test chỉ chứa trường hợp dễ xử lý.
- Một endpoint được đo qua cache warm trong khi production thường cold.
- Bộ đếm chỉ ghi nhận test thành công mà bỏ qua test timeout.
- Cấu hình runner luôn nhanh hơn môi trường mục tiêu.

Chạy lặp nhiều lần không tự loại bỏ sai lệch hệ thống. Cần kiểm tra công cụ, định nghĩa chỉ số, thiết kế lấy mẫu và điều kiện thực thi.

### 3.3. Sai số lấy mẫu

Khi chỉ quan sát một phần tổng thể, mẫu có thể không đại diện. Ví dụ, kiểm thử trên một số tenant lớn không cho biết hành vi của tenant nhỏ; kiểm tra một nhóm trình duyệt không phản ánh mọi thiết bị được hỗ trợ.

Cần nêu:

- Tổng thể muốn đại diện là gì.
- Cách chọn mẫu.
- Số lượng mẫu và đơn vị quan sát.
- Nhóm nào được bao gồm hoặc loại trừ.
- Mẫu có thể bị lệch ở điểm nào.

Một mẫu lớn vẫn có thể sai lệch nếu cách chọn không phù hợp. Tăng số lượng quan sát không tự sửa được selection bias.

### 3.4. Sai số công cụ và định nghĩa

Công cụ có thể có độ phân giải, sai số, sampling hoặc giới hạn thu thập. Chỉ số cũng có thể được định nghĩa khác nhau giữa các hệ thống.

Ví dụ, một dashboard tính tỷ lệ pass trên số test đã chạy; dashboard khác tính trên tổng số test gồm cả skipped. Hai tỷ lệ không thể so sánh trực tiếp nếu mẫu số khác nhau.

Nên ghi phiên bản công cụ, cấu hình, đơn vị, cách làm tròn, bộ lọc và quy tắc tính toán. Với metric được lấy từ nhiều nguồn, cần xác định nguồn chuẩn và cách xử lý dữ liệu trùng hoặc thiếu.

### 3.5. Bất định do mô hình và giả định

Một số kết quả dựa trên mô hình hoặc giả định, chẳng hạn dự báo throughput khi tăng số instance, mô hình hóa tải hoặc ước lượng tỷ lệ defect lọt qua.

Giả định có thể không đúng khi:

- Hệ thống thay đổi chế độ hoạt động ở tải cao.
- Điểm nghẽn chuyển từ CPU sang database hoặc network.
- Request không độc lập.
- Dữ liệu có phân bố lệch.
- Hành vi người dùng thay đổi theo thời gian.
- Autoscaling có độ trễ hoặc giới hạn.

Cần ghi mô hình, giả định và phạm vi mà mô hình đã được kiểm chứng. Không trình bày dự báo như số đo thực tế.

### 3.6. Bất định do môi trường và vận hành

Một phép đo có thể bị ảnh hưởng bởi:

- Phiên bản runtime, database, broker hoặc thư viện.
- Tài nguyên runner và cấu hình container.
- Cache, dữ liệu nền và tác vụ định kỳ.
- Mạng, DNS, TLS và phụ thuộc bên ngoài.
- Feature flag, tenant plan và quyền truy cập.
- Trạng thái hệ thống trước khi chạy.
- Thời điểm trong ngày hoặc tải của hệ thống dùng chung.

Khi điều kiện không ổn định, báo cáo cần phân biệt thay đổi do sản phẩm với thay đổi do môi trường. Nếu không thể cô lập nguyên nhân, kết luận phải giữ ở mức mô tả tương quan.

## 4. Thiết kế phép đo trước khi thu thập

Độ tin cậy của báo cáo bắt đầu từ thiết kế phép đo. Nếu câu hỏi, đơn vị và mẫu số không rõ, phân tích sau đó khó sửa được.

### 4.1. Xác định câu hỏi đo lường

Câu hỏi nên cụ thể, có thể kiểm chứng và gắn với quyết định. Ví dụ:

- P95 latency của API tìm kiếm có dưới 500 ms ở mức 300 request/giây không?
- Tỷ lệ test hồi quy không ổn định thay đổi thế nào sau khi sửa fixture?
- Bao nhiêu yêu cầu rủi ro cao có ít nhất một test xác minh?
- Tỷ lệ giao dịch bị lỗi trong một workload nhất định có vượt ngưỡng không?

Tránh câu hỏi mơ hồ như “hệ thống có tốt không?” hoặc “chất lượng đã tăng chưa?” nếu chưa định nghĩa chất lượng và cách đo.

### 4.2. Định nghĩa đơn vị quan sát và mẫu số

Mọi tỷ lệ cần có tử số và mẫu số rõ ràng. Ví dụ:

- Pass rate = số test đạt / số test có kết quả hợp lệ.
- Flaky rate = số test được xác nhận không ổn định / số test được quan sát trong kỳ.
- Defect density = số defect theo một đơn vị kích thước hoặc phạm vi đã định nghĩa.
- Requirement coverage = số yêu cầu được kiểm tra theo tiêu chí / tổng số yêu cầu thuộc phạm vi.

Cần nêu cách xử lý skipped, blocked, inconclusive, rerun và test bị hủy. Không nên thay đổi mẫu số giữa các kỳ mà không công bố.

### 4.3. Xác định tổng thể và phạm vi

Ghi rõ:

- Sản phẩm, service hoặc component nào.
- Phiên bản hoặc khoảng thời gian nào.
- Loại người dùng, tenant hoặc dữ liệu nào.
- Nền tảng, trình duyệt và thiết bị nào.
- Môi trường và topology nào.
- Test suite hoặc nhóm rủi ro nào.
- Điều kiện loại trừ và lý do.

Phạm vi đo càng rõ, người đọc càng dễ xác định kết luận có áp dụng cho quyết định của họ hay không.

### 4.4. Xác định ngưỡng và quy tắc trước khi xem kết quả

Nếu có thể, xác định ngưỡng pass/fail, mức cảnh báo và phương pháp phân tích trước khi thu thập. Điều này giảm nguy cơ chọn ngưỡng sau khi nhìn thấy dữ liệu để làm kết quả có vẻ thuận lợi.

Ngưỡng cần có nguồn gốc từ yêu cầu, SLA/SLO, risk appetite hoặc quyết định được phê duyệt. Nếu ngưỡng thay đổi, ghi lại thời điểm và lý do để không so sánh sai các kỳ.

## 5. Trình bày biến thiên và phân bố, không chỉ một con số

Một giá trị trung bình có thể che giấu những trường hợp rất chậm hoặc lỗi tập trung ở một nhóm nhỏ. Cần chọn thống kê phù hợp với phân bố và câu hỏi.

### 5.1. Mean, median và percentile

- **Mean (trung bình):** tổng giá trị chia cho số quan sát; nhạy với giá trị cực đoan.
- **Median (trung vị):** giá trị giữa khi sắp xếp; ít bị ảnh hưởng bởi một số ngoại lệ lớn.
- **Percentile:** ngưỡng mà một tỷ lệ phần trăm quan sát nằm ở hoặc dưới giá trị đó. P95 là giá trị mà khoảng 95% quan sát không vượt quá trong mẫu đã đo.

Với latency, thường nên trình bày median, P90/P95/P99 cùng số lượng request và error rate. P99 có thể dao động mạnh nếu mẫu nhỏ; cần nêu số quan sát và không diễn giải quá chắc chắn.

### 5.2. Range và độ phân tán

Có thể trình bày:

- Min/max.
- Khoảng tứ phân vị (IQR).
- Độ lệch chuẩn khi phù hợp.
- Biểu đồ histogram hoặc box plot.
- Kết quả theo từng lần chạy.

Không nên chỉ báo min vì nó thường phản ánh trường hợp thuận lợi. Max cũng cần ngữ cảnh vì có thể là một ngoại lệ đơn lẻ hoặc dấu hiệu của tail latency.

### 5.3. So sánh các lần chạy

Ví dụ, một bài performance test có ba lần chạy:

| Lần chạy | P95 latency | Error rate |
|---|---:|---:|
| 1 | 410 ms | 0,20% |
| 2 | 438 ms | 0,25% |
| 3 | 421 ms | 0,22% |

Có thể nói P95 quan sát được nằm trong khoảng 410–438 ms và error rate nằm trong khoảng 0,20–0,25% ở ba lần chạy. Chưa đủ cơ sở để khẳng định hệ thống luôn đạt các giá trị này trong mọi điều kiện. Cần xem thêm workload, số request, trạng thái cache và sự ổn định môi trường.

### 5.4. Không trộn các nhóm khác nhau

Nếu latency khác nhau đáng kể theo endpoint, tenant, vùng hoặc loại request, hãy báo cáo riêng khi các nhóm có ý nghĩa. Trung bình gộp có thể che giấu một nhóm bị suy giảm nghiêm trọng.

Tuy nhiên, không chia nhóm tùy tiện sau khi thấy kết quả xấu. Nêu tiêu chí phân nhóm và lý do; nếu phân tích là khám phá sau quan sát, ghi rõ đây là phát hiện cần xác minh.

## 6. Cỡ mẫu và khoảng tin cậy

Khi muốn suy luận từ mẫu sang tổng thể, cần xem xét số lượng quan sát và cách lấy mẫu. Một tỷ lệ từ 10 lần chạy có độ bất định lớn hơn tỷ lệ từ hàng nghìn quan sát độc lập, nhưng số lượng lớn không bảo đảm mẫu đại diện.

### 6.1. Tỷ lệ và sai số chuẩn

Với một tỷ lệ mẫu p được tính từ n quan sát nhị phân, sai số chuẩn xấp xỉ trong điều kiện lấy mẫu độc lập là:

\[
SE(\hat p) \approx \sqrt{\frac{\hat p(1-\hat p)}{n}}
\]

Trong đó p-hat là tỷ lệ quan sát. Công thức này là xấp xỉ và có thể không phù hợp khi mẫu nhỏ, tỷ lệ gần 0 hoặc 1, hoặc các quan sát phụ thuộc nhau.

Với tỷ lệ nhỏ hoặc mẫu nhỏ, nên dùng phương pháp khoảng tin cậy phù hợp như Wilson hoặc exact binomial thay vì dựa máy móc vào xấp xỉ chuẩn.

### 6.2. Khoảng tin cậy là gì?

Khoảng tin cậy mô tả độ bất định của một ước lượng theo phương pháp và giả định thống kê đã chọn. Ví dụ, khoảng tin cậy 95% trong cách diễn giải tần suất có nghĩa là nếu lặp lại quy trình lấy mẫu và tính khoảng rất nhiều lần trong cùng điều kiện, khoảng được tạo ra sẽ bao phủ tham số thật khoảng 95% số lần.

Không nên diễn giải một khoảng tin cậy 95% là “có 95% xác suất tham số thật nằm trong khoảng này” theo cách hiểu cổ điển sau khi đã tính khoảng. Cách diễn giải phụ thuộc trường phái thống kê và mô hình được dùng.

### 6.3. Ví dụ về tỷ lệ lỗi

Giả sử 2.000 request trong một bài kiểm thử có 10 request lỗi. Tỷ lệ lỗi quan sát là 0,5%. Báo cáo nên nêu:

- Số request: 2.000.
- Số request lỗi: 10.
- Tỷ lệ lỗi quan sát: 0,5%.
- Cách chọn workload và thời gian chạy.
- Khoảng tin cậy nếu mục tiêu là ước lượng tỷ lệ trong điều kiện tương tự.
- Các giới hạn như request không độc lập, phân bố endpoint hoặc môi trường dùng chung.

Không nên kết luận tỷ lệ lỗi production là 0,5% chỉ từ bài test này nếu workload và điều kiện không đại diện.

### 6.4. Khi không quan sát thấy lỗi

Không có lỗi trong mẫu không đồng nghĩa rủi ro bằng 0. Với n phép thử Bernoulli độc lập và không quan sát thấy sự cố, quy tắc gần đúng “3/n” thường được dùng làm giới hạn trên khoảng 95% cho xác suất sự cố trong điều kiện giả định phù hợp. Ví dụ, không thấy lỗi trong 1.000 lần thử không chứng minh xác suất lỗi bằng 0; giới hạn trên xấp xỉ theo quy tắc này là 0,3%.

Quy tắc này không áp dụng máy móc cho request phụ thuộc nhau, dữ liệu không đại diện, test không độc lập hoặc các tình huống có nhiều chế độ hoạt động. Hãy ghi giả định và dùng phương pháp phù hợp với thiết kế thử nghiệm.

### 6.5. Cỡ mẫu không thay thế thiết kế tốt

Tăng n giúp giảm một số dạng bất định lấy mẫu, nhưng không sửa được:

- Mẫu chỉ gồm người dùng hoặc dữ liệu dễ kiểm tra.
- Công cụ đo sai hoặc bỏ sót kết quả.
- Điều kiện môi trường không đại diện.
- Các lần chạy phụ thuộc nhau.
- Chỉ số không đo đúng khái niệm cần đánh giá.

Một mẫu nhỏ nhưng được chọn có chủ đích có thể hữu ích cho kiểm tra khám phá; một mẫu lớn nhưng sai lệch có thể dẫn đến kết luận sai.

## 7. Trình bày khoảng trống về coverage

Coverage thường được diễn giải như một tỷ lệ, nhưng mẫu số và ý nghĩa cần được làm rõ. Có nhiều loại coverage khác nhau:

- Requirement coverage.
- Risk coverage.
- Code coverage.
- Test execution coverage.
- API/contract coverage.
- Platform/browser coverage.
- Tenant, role và permission coverage.
- Data state và boundary coverage.
- Performance workload coverage.

Không nên dùng một chỉ số coverage để đại diện cho tất cả.

### 7.1. Phân biệt được kiểm tra với được bao phủ

Một yêu cầu được liên kết với test không có nghĩa test đã chạy hoặc test có khả năng phát hiện lỗi. Cần phân biệt:

1. Có test được thiết kế.
2. Test đã được thực thi.
3. Test có kết quả hợp lệ.
4. Assertion thực sự kiểm tra hành vi.
5. Bằng chứng cho thấy rủi ro được kiểm soát ở mức cần thiết.

Một dashboard chỉ đếm liên kết requirement-test có thể báo 100% coverage dù nhiều test bị skip hoặc chỉ kiểm tra trạng thái rất sơ sài.

### 7.2. Ghi khoảng trống cụ thể

Ví dụ báo cáo coverage nên nêu:

- Đã kiểm tra: API đọc đơn hàng trong hai tenant, với vai trò Admin và Viewer.
- Chưa kiểm tra: tenant có dữ liệu lớn, người dùng tham gia nhiều tenant, export bất đồng bộ.
- Không áp dụng: luồng offline vì sản phẩm không hỗ trợ chế độ này.
- Bị chặn: kiểm tra SSO trên môi trường staging do identity provider thử nghiệm chưa sẵn sàng.

Cách trình bày này hữu ích hơn một con số tổng hợp 85% mà không giải thích 15% còn lại.

### 7.3. Phân loại khoảng trống

| Trạng thái | Ý nghĩa | Cách báo cáo |
|---|---|---|
| Tested and passed | Đã kiểm tra và đạt. | Ghi test, build, môi trường và kết quả. |
| Tested and failed | Đã kiểm tra nhưng không đạt. | Liên kết defect và bằng chứng. |
| Not tested | Chưa thực hiện. | Nêu lý do, rủi ro và kế hoạch. |
| Blocked | Không thể thực hiện do phụ thuộc hoặc môi trường. | Ghi blocker, owner và điều kiện tiếp tục. |
| Skipped | Bị bỏ qua theo cấu hình hoặc quyết định. | Nêu lý do, người phê duyệt và ảnh hưởng coverage. |
| Inconclusive | Đã chạy nhưng kết quả không đủ để kết luận. | Giải thích vấn đề và cách thu thập lại. |
| Not applicable | Không thuộc phạm vi hoặc không áp dụng theo thiết kế. | Nêu căn cứ loại trừ. |

Không gộp Not tested, Blocked và Not applicable thành một trạng thái “N/A”. Chúng mang ý nghĩa và mức rủi ro khác nhau.

## 8. Khoảng trống dữ liệu và thiên lệch

Dữ liệu không đầy đủ có thể khiến báo cáo sai lệch. Trước khi phân tích, cần hiểu dữ liệu nào bị thiếu và vì sao.

### 8.1. Phân biệt các trạng thái dữ liệu

- **Zero:** giá trị đo thực sự bằng 0.
- **Missing:** không có dữ liệu được ghi nhận.
- **Not measured:** chỉ số chưa được thu thập.
- **Not applicable:** khái niệm không áp dụng cho đối tượng.
- **Filtered out:** dữ liệu bị loại theo tiêu chí phân tích.
- **Unknown:** trạng thái chưa xác định.

Ví dụ, error rate bằng 0 khác với error rate không có dữ liệu vì agent telemetry bị mất. Thay missing bằng 0 có thể làm hệ thống trông tốt hơn thực tế.

### 8.2. Các dạng thiên lệch thường gặp

**Selection bias:** chỉ chọn các trường hợp dễ hoặc thuận lợi, khiến mẫu không đại diện.

**Survivorship bias:** chỉ phân tích những test hoặc request còn lại sau khi các trường hợp thất bại bị loại khỏi tập dữ liệu.

**Measurement bias:** công cụ hoặc quy trình đo làm kết quả lệch có hệ thống.

**Reporting bias:** chỉ báo cáo chỉ số thuận lợi hoặc chỉ chọn khoảng thời gian đẹp.

**Confirmation bias:** tập trung vào bằng chứng ủng hộ giả thuyết ban đầu và bỏ qua kết quả trái chiều.

**Missing data bias:** dữ liệu thiếu có liên quan đến kết quả, chẳng hạn request chậm thường timeout trước khi telemetry được ghi.

### 8.3. Kiểm tra dữ liệu thiếu

Nên báo cáo:

- Tỷ lệ bản ghi thiếu theo từng trường.
- Nhóm hoặc thời điểm bị thiếu.
- Nguyên nhân đã biết và chưa biết.
- Cách xử lý trong phân tích.
- Kết luận có thể thay đổi thế nào nếu dữ liệu thiếu khác với giả định.

Không nên xóa các bản ghi bất lợi chỉ vì chúng không đầy đủ. Nếu loại dữ liệu, cần nêu tiêu chí và số lượng bị loại.

## 9. Giới hạn khi so sánh giữa các build hoặc giai đoạn

So sánh trước/sau có thể hữu ích, nhưng chỉ đáng tin khi điều kiện đủ tương đồng hoặc sai khác đã được phân tích.

### 9.1. Các yếu tố gây nhiễu

- Khác runner hoặc tài nguyên.
- Khác dữ liệu và phân bố request.
- Khác số lượng test hoặc phiên bản test suite.
- Khác cấu hình cache, timeout hoặc retry.
- Khác môi trường, vùng và số instance.
- Khác feature flag hoặc tenant plan.
- Khác thời điểm và tải nền.
- Khác công cụ đo hoặc cách tính metric.

Nếu P95 latency giảm từ 500 ms xuống 430 ms nhưng build mới chạy trên phần cứng nhanh hơn, chưa thể kết luận thay đổi mã làm hệ thống nhanh hơn.

### 9.2. Chuẩn hóa điều kiện so sánh

Khi có thể:

- Dùng cùng workload và dữ liệu.
- Dùng cùng loại runner và giới hạn tài nguyên.
- Cố định cấu hình và phiên bản phụ thuộc.
- Thực hiện warm-up theo quy trình giống nhau.
- Chạy lặp lại đủ để quan sát biến thiên.
- Ghi lại thay đổi không thể giữ cố định.
- So sánh cùng percentile, cùng đơn vị và cùng mẫu số.

Nếu không thể chuẩn hóa, cần báo cáo sai khác và tránh diễn giải chênh lệch như tác động nhân quả của bản build.

### 9.3. So sánh thay đổi tỷ lệ

Khi báo cáo tỷ lệ, nêu cả số lượng tuyệt đối. Ví dụ, tỷ lệ lỗi giảm từ 2% xuống 1% nghe như giảm một nửa, nhưng cần biết mẫu số là 100 request hay 1 triệu request. Đồng thời, thay đổi cơ cấu request có thể làm tỷ lệ tổng hợp thay đổi dù từng nhóm không cải thiện.

Có thể trình bày theo nhóm endpoint, tenant hoặc loại giao dịch để phát hiện thay đổi thành phần. Nếu cơ cấu nhóm khác nhau giữa hai kỳ, cần cân nhắc chuẩn hóa hoặc so sánh riêng từng nhóm.

## 10. Giới hạn suy luận nhân quả

Tương quan không chứng minh quan hệ nhân quả. Nếu hai chỉ số thay đổi cùng lúc, không thể kết luận một thay đổi gây ra thay đổi kia nếu chưa loại trừ các yếu tố khác.

Ví dụ, sau khi thêm test tự động, số defect được phát hiện tăng. Điều này có thể do:

- Test mới phát hiện được lỗi trước đây bị bỏ sót.
- Sản phẩm có nhiều thay đổi hơn.
- Nhóm tăng hoạt động exploratory testing.
- Quy trình báo cáo lỗi được cải thiện.
- Một module có rủi ro cao được đưa vào phạm vi.

Không nên kết luận chất lượng sản phẩm giảm chỉ từ số defect tăng. Cần phân tích phạm vi kiểm tra, số lượng thay đổi, mức độ sử dụng và cách phát hiện.

### 10.1. Bằng chứng mạnh hơn cho quan hệ nhân quả

Để đánh giá tác động của một thay đổi, có thể:

- Xác định giả thuyết trước.
- Dùng nhóm đối chứng hoặc baseline phù hợp khi khả thi.
- Giữ điều kiện khác tương đương.
- Thay đổi một yếu tố có chủ đích.
- Đo trước và sau theo cùng định nghĩa.
- Lặp lại hoặc xác minh trên nhiều giai đoạn.
- Phân tích yếu tố gây nhiễu.
- Kiểm tra cơ chế giải thích kết quả.

Trong hệ thống phần mềm, thử nghiệm A/B, canary hoặc rollout theo nhóm có thể cung cấp bằng chứng tốt hơn so sánh đơn giản trước/sau, nhưng vẫn cần kiểm soát cách phân nhóm và các yếu tố khác.

### 10.2. Ngôn ngữ kết luận phù hợp

| Mức bằng chứng | Cách diễn đạt phù hợp |
|---|---|
| Mô tả trực tiếp | “Trong lần chạy này, P95 là 430 ms.” |
| Quan sát xu hướng | “P95 giảm trong ba lần chạy gần nhất.” |
| Liên hệ có điều kiện | “Mức giảm xuất hiện sau khi thay đổi cache trong cùng cấu hình đo.” |
| Bằng chứng nhân quả hạn chế | “Kết quả phù hợp với giả thuyết cache góp phần giảm latency; cần xác minh thêm trên tải đa vùng.” |
| Bằng chứng thực nghiệm mạnh hơn | “Trong thử nghiệm có đối chứng với workload và tài nguyên tương đương, thay đổi cache làm giảm P95 trong phạm vi đo.” |

Tránh các từ như “chắc chắn”, “luôn luôn”, “đã loại bỏ hoàn toàn” nếu dữ liệu không hỗ trợ phạm vi đó.

## 11. Giới hạn ngoại suy kết quả sang production

Môi trường kiểm thử không phải lúc nào cũng đại diện production. Một kết quả có thể đúng trong staging nhưng không áp dụng trực tiếp cho tải, dữ liệu, quyền hoặc topology production.

Trước khi ngoại suy, cần xem xét:

- Kiến trúc và số instance.
- Phiên bản runtime, database và phụ thuộc.
- Kích thước, phân bố và chất lượng dữ liệu.
- Mẫu tải và concurrency.
- Mạng, vùng và độ trễ.
- Cache, autoscaling và giới hạn tài nguyên.
- Feature flag và cấu hình.
- Hành vi dịch vụ bên ngoài.
- Cách telemetry thu thập và sampling.

### 11.1. Nêu rõ phạm vi áp dụng

Ví dụ:

“Bài kiểm thử xác nhận API đáp ứng ngưỡng P95 500 ms với workload 300 request/giây trên staging, hai instance ứng dụng và dữ liệu tổng hợp 2 triệu bản ghi. Kết quả chưa chứng minh khả năng đáp ứng ở tải đột biến 1.000 request/giây, khi failover giữa vùng hoặc với phân bố tenant production.”

Cách viết này cho biết điều đã được chứng minh và phần chưa được chứng minh.

### 11.2. Kết hợp bằng chứng trước và sau triển khai

Khi rủi ro còn lại chỉ có thể quan sát trong production, có thể dùng:

- Smoke test giới hạn và an toàn.
- Synthetic monitoring.
- Canary hoặc progressive rollout.
- Theo dõi error rate, latency và metric nghiệp vụ.
- So sánh nhóm canary với baseline phù hợp.
- Feature flag và khả năng rollback.
- Đối soát dữ liệu sau migration.

Đây là kiểm soát bổ sung, không biến kết quả staging thành bằng chứng đầy đủ cho production. Cần có ngưỡng dừng và owner xử lý nếu chỉ số vượt giới hạn.

## 12. Trình bày độ bất định cho các chỉ số kiểm thử phổ biến

Mỗi metric có nguồn bất định và giới hạn riêng. Không nên dùng cùng một cách diễn giải cho mọi loại số liệu.

### 12.1. Pass rate

Pass rate phụ thuộc vào mẫu số, trạng thái skipped, blocked, retry và cách xử lý flaky test.

Cần nêu:

- Số test đạt, thất bại, skipped, blocked và inconclusive.
- Tổng số test được thiết kế và số thực sự chạy.
- Kết quả lần đầu và kết quả sau retry.
- Phạm vi suite, build và môi trường.
- Test nào không chạy và lý do.

Pass rate 100% trên 80 test đã chạy không có nghĩa toàn bộ 100 test trong suite đã đạt nếu 20 test còn lại bị bỏ qua.

### 12.2. Flaky rate

Flaky rate cần định nghĩa đơn vị: số test không ổn định, số lần chạy thất bại bất thường hay số test có ít nhất một lần retry pass. Các định nghĩa khác nhau cho kết quả khác nhau.

Nên lưu chuỗi kết quả theo test và theo thời gian, số lần chạy, số lần retry và điều kiện môi trường. Một test chỉ chạy một lần không đủ dữ liệu để đánh giá độ ổn định.

### 12.3. Defect detection và defect escape

Số defect được phát hiện phụ thuộc vào phạm vi, thời gian kiểm thử, chất lượng test, mức độ sử dụng và quy trình báo cáo. Số defect lọt qua production cũng phụ thuộc cách phân loại và khả năng phát hiện sau phát hành.

Khi so sánh, nêu:

- Định nghĩa defect và severity.
- Khoảng thời gian quan sát.
- Mẫu số như release, change, user hoặc transaction nếu phù hợp.
- Cách gán defect cho phiên bản.
- Độ trễ từ phát sinh đến phát hiện.
- Các lỗi chưa được phân loại hoặc còn tranh luận.

Không nên so sánh số defect tuyệt đối giữa hai nhóm có quy mô, phạm vi và cách ghi nhận khác nhau mà không chuẩn hóa.

### 12.4. Coverage

Coverage cần gắn với loại coverage và phạm vi. Code coverage cao không chứng minh mọi yêu cầu hoặc rủi ro đã được kiểm tra. Requirement coverage cao không chứng minh assertion đủ mạnh. Nêu rõ coverage đo gì và phần nào bị loại trừ.

### 12.5. Thời gian thực thi

Execution time có thể biến thiên theo runner, tải nền, cache và concurrency. Nên báo median hoặc percentile qua nhiều lần chạy, cùng điều kiện và số mẫu. Nếu chỉ có một lần chạy, ghi là thời gian quan sát của lần đó.

### 12.6. Hiệu năng

Latency, throughput và error rate cần được đọc cùng nhau. Tăng throughput bằng cách chấp nhận error rate cao hơn không phải cải thiện toàn diện. Báo workload, số request, warm-up, thời gian duy trì, tài nguyên và các percentile. Ghi rõ phần tải chưa được thử.

## 13. Trình bày bất định và khoảng trống trên dashboard

Dashboard cần hỗ trợ người đọc hiểu nhanh trạng thái mà không che giấu giới hạn.

### 13.1. Hiển thị mẫu số và trạng thái

Thay vì chỉ hiển thị “Pass rate 98%”, có thể trình bày:

- 980/1.000 test có kết quả hợp lệ đạt.
- 10 test thất bại.
- 6 test skipped.
- 4 test blocked.
- 12 test có lịch sử flaky trong 30 ngày.
- 3 nhóm rủi ro cao chưa có kiểm tra tự động.

Các con số trên chỉ là ví dụ. Cần xác định cách tính để các nhóm không cộng trùng trạng thái.

### 13.2. Hiển thị thời gian và phiên bản

Mỗi widget hoặc bảng cần cho biết:

- Khoảng thời gian.
- Build/release.
- Environment.
- Thời điểm cập nhật dữ liệu.
- Bộ lọc đang áp dụng.
- Nguồn dữ liệu và phiên bản metric nếu có.

Một con số không có timestamp có thể bị hiểu nhầm là trạng thái hiện tại dù dữ liệu đã cũ.

### 13.3. Hiển thị mức độ tin cậy và phần chưa đo

Có thể dùng nhãn:

- Đã xác minh.
- Ước lượng.
- Chưa đủ mẫu.
- Dữ liệu thiếu.
- Bị chặn.
- Chưa kiểm tra.
- Không áp dụng.

Không nên dùng màu xanh cho mọi trường hợp chưa có lỗi. “Chưa kiểm tra” không phải “đạt”; “không có dữ liệu” không phải “không có vấn đề”.

## 14. Cách viết báo cáo đo lường cân bằng

Một báo cáo tốt nên giúp người đọc đưa ra quyết định, không chỉ liệt kê số liệu.

### 14.1. Cấu trúc báo cáo gợi ý

1. **Câu hỏi và quyết định cần hỗ trợ:** tại sao đo và ai sẽ dùng kết quả?
2. **Phạm vi:** sản phẩm, build, môi trường, thời gian, nhóm dữ liệu và test.
3. **Phương pháp:** công cụ, cách lấy mẫu, định nghĩa metric và điều kiện chạy.
4. **Kết quả:** số liệu, phân bố, mẫu số và xu hướng.
5. **Độ bất định:** biến thiên, khoảng tin cậy, sai số và giả định.
6. **Khoảng trống:** nội dung chưa đo, bị chặn, bị bỏ qua hoặc không đại diện.
7. **Giới hạn suy luận:** kết luận nào chưa thể rút ra.
8. **Rủi ro còn lại:** hậu quả và mức độ chấp nhận.
9. **Hành động tiếp theo:** kiểm tra bổ sung, owner và thời hạn.

### 14.2. Ví dụ cách viết chưa tốt và cách viết tốt hơn

**Chưa tốt:**

“Hiệu năng đã cải thiện 20%. Hệ thống sẵn sàng production.”

Câu này không nêu chỉ số, điều kiện, số lần chạy, phạm vi hay giới hạn.

**Tốt hơn:**

“Trong bốn lần chạy staging với cùng workload 250 request/giây và cùng loại runner, P95 latency giảm từ trung vị 500 ms xuống 400 ms sau thay đổi. Error rate không tăng trong các lần chạy đã quan sát. Kết quả hỗ trợ nhận định thay đổi cải thiện latency trong cấu hình này. Chưa thử tải đột biến, failover hoặc topology production; cần hoàn tất các kiểm tra đó và theo dõi canary trước khi kết luận về khả năng đáp ứng production.”

### 14.3. Tách kết quả khỏi khuyến nghị

Kết quả mô tả bằng chứng. Khuyến nghị kết hợp bằng chứng với mức rủi ro và ngưỡng chấp nhận. Có thể hai người đồng ý về số liệu nhưng khác nhau về mức rủi ro có thể chấp nhận.

Báo cáo nên ghi:

- Dữ liệu cho thấy điều gì.
- Giới hạn dữ liệu.
- Rủi ro còn lại.
- Người có thẩm quyền quyết định.
- Điều kiện để thay đổi quyết định.

## 15. Ví dụ tổng hợp: báo cáo kết quả hồi quy trước release

Một release candidate chạy 1.200 test hồi quy. Báo cáo thô ghi 1.176 pass, 8 fail, 10 skipped và 6 blocked.

### 15.1. Mô tả đúng mẫu số

Nếu tính trên 1.190 test có kết quả pass hoặc fail, pass rate là 1.176/1.190, khoảng 98,82%. Nếu tính trên toàn bộ 1.200 test được lên kế hoạch, tỷ lệ pass là 98%. Hai cách tính trả lời hai câu hỏi khác nhau.

Báo cáo nên giữ cả trạng thái và mẫu số thay vì chỉ chọn tỷ lệ thuận lợi. Sáu test blocked và mười test skipped vẫn là khoảng trống cần được đánh giá.

### 15.2. Phân tích theo rủi ro

Giả sử trong tám test fail:

- Ba test liên quan đến hiển thị ít quan trọng.
- Hai test liên quan đến quyền truy cập tenant.
- Một test liên quan đến migration dữ liệu.
- Hai test flaky chưa xác định nguyên nhân.

Không thể kết luận release sẵn sàng chỉ dựa trên tỷ lệ pass 98,82%. Hai lỗi tenant access và một lỗi migration có thể có tác động cao dù số lượng nhỏ. Cần đánh giá severity, requirement và risk tương ứng.

### 15.3. Nêu phần chưa được kiểm tra

Mười test skipped thuộc một trình duyệt ít phổ biến; sáu test blocked do sandbox của đối tác không sẵn sàng. Báo cáo cần nêu trình duyệt nào bị ảnh hưởng, nhóm người dùng có sử dụng hay không, tích hợp nào chưa được xác minh và biện pháp thay thế nào có sẵn.

### 15.4. Kết luận có điều kiện

Một kết luận cân bằng có thể là:

“Release candidate đạt 1.176/1.190 test có kết quả hợp lệ. Tám test thất bại đang được phân loại; trong đó có các kiểm tra về tenant isolation và migration cần được xử lý trước khi quyết định phát hành. Mười test bị skipped và sáu test blocked tạo ra khoảng trống về compatibility và tích hợp đối tác. Tỷ lệ pass không đủ để kết luận release sẵn sàng. Cần xác minh các lỗi rủi ro cao, đánh giá biện pháp thay thế cho các test chưa chạy và để release owner quyết định dựa trên risk acceptance.”

## 16. Những sai lầm thường gặp

- **Chỉ báo số trung bình:** che giấu tail latency và nhóm có kết quả xấu.
- **Không ghi mẫu số:** tỷ lệ không thể diễn giải hoặc so sánh.
- **Coi không có lỗi là rủi ro bằng 0:** bỏ qua giới hạn mẫu và coverage.
- **Đồng nhất missing với zero:** làm kết quả trông tốt hơn thực tế.
- **Tăng cỡ mẫu nhưng giữ cách chọn sai:** thiên lệch vẫn tồn tại.
- **Dùng khoảng tin cậy như bảo đảm:** bỏ qua giả định và cách lấy mẫu.
- **Suy luận nhân quả từ trước/sau:** không kiểm soát yếu tố gây nhiễu.
- **Ngoại suy staging sang production:** bỏ qua khác biệt topology, tải và dữ liệu.
- **Gộp các nhóm khác nhau:** che giấu vấn đề ở tenant, endpoint hoặc nền tảng cụ thể.
- **Chỉ hiển thị pass/fail:** bỏ qua blocked, skipped và inconclusive.
- **Thay ngưỡng sau khi xem dữ liệu:** làm kết quả khó khách quan.
- **Chỉ báo kết quả thuận lợi:** khiến người quyết định không thấy khoảng trống.
- **Dùng ngôn ngữ chắc chắn quá mức:** làm kết luận vượt xa bằng chứng.
- **Không ghi giả định và giới hạn:** người đọc áp dụng kết quả ngoài phạm vi.

## 17. Checklist trình bày độ bất định, khoảng trống và giới hạn

- [ ] Câu hỏi đo lường và quyết định cần hỗ trợ được nêu rõ.
- [ ] Đơn vị quan sát, tổng thể và mẫu số được định nghĩa.
- [ ] Phạm vi sản phẩm, build, môi trường và thời gian được ghi.
- [ ] Phương pháp lấy mẫu và điều kiện thu thập được mô tả.
- [ ] Nguồn sai số ngẫu nhiên, sai lệch hệ thống và sai số công cụ được xem xét.
- [ ] Số lượng quan sát và số lần chạy được trình bày.
- [ ] Thống kê phù hợp với phân bố và câu hỏi.
- [ ] Khoảng tin cậy hoặc mức bất định được dùng khi phù hợp và có giả định rõ.
- [ ] Dữ liệu zero, missing, not measured và not applicable được phân biệt.
- [ ] Test skipped, blocked, failed và inconclusive được hiển thị riêng.
- [ ] Coverage gap được mô tả theo yêu cầu, rủi ro, nền tảng và điều kiện.
- [ ] Sai khác giữa các build hoặc môi trường được phân tích.
- [ ] Không suy luận nhân quả khi chỉ có tương quan hoặc so sánh trước/sau.
- [ ] Giới hạn ngoại suy sang production được nêu.
- [ ] Evidence và nguồn dữ liệu có thể truy xuất.
- [ ] Kết luận không vượt quá bằng chứng.
- [ ] Rủi ro còn lại, owner và hành động tiếp theo được ghi.
- [ ] Dashboard hiển thị timestamp, build, environment và bộ lọc.
- [ ] Ngưỡng và quy tắc tính metric có nguồn gốc rõ ràng.

## Kết luận

Trình bày độ bất định, khoảng trống và giới hạn suy luận là phần thiết yếu của đo lường kiểm thử. Hãy nêu rõ điều kiện, mẫu số, cỡ mẫu, biến thiên, sai số và nguồn dữ liệu; phân biệt phần đã kiểm tra với phần bị bỏ qua, bị chặn hoặc chưa đo; đồng thời giới hạn kết luận theo phạm vi bằng chứng. Khoảng tin cậy và thống kê mô tả chỉ có ý nghĩa khi giả định phù hợp. So sánh build, suy luận nhân quả và ngoại suy sang production cần kiểm soát yếu tố gây nhiễu. Một báo cáo tốt không chỉ cho biết con số là bao nhiêu, mà còn giúp người đọc hiểu con số đó chứng minh được điều gì, chưa chứng minh được điều gì và cần làm gì tiếp theo.
