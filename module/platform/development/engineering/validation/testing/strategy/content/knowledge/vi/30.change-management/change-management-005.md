# Ưu tiên cải tiến theo tác động và công sức thực hiện

Nhóm phát triển và kiểm thử thường có nhiều cơ hội cải tiến hơn thời gian và nguồn lực có thể dành ra. Có thể cần giảm thời gian chạy pipeline, xử lý test flaky, cải thiện dữ liệu kiểm thử, bổ sung kiểm thử hợp đồng, tăng khả năng quan sát, rút ngắn thời gian triage lỗi hoặc chuẩn hóa quy trình bàn giao. Nếu chọn công việc theo cảm giác, theo người đề xuất lớn tiếng nhất hoặc theo việc dễ làm nhất, nhóm có thể dành nhiều công sức cho cải tiến ít giá trị trong khi những điểm nghẽn quan trọng vẫn tồn tại.

Ưu tiên cải tiến theo tác động và công sức thực hiện là cách so sánh các cơ hội dựa trên giá trị dự kiến, mức giảm rủi ro, phạm vi được hưởng lợi, độ tin cậy của giả định và nguồn lực cần thiết. Mục tiêu là chọn đúng việc nên làm trước, hiểu lý do, xác định điều kiện thành công và cân bằng giữa cải tiến nhanh với đầu tư dài hạn.

Tác động và công sức là hai chiều hữu ích, nhưng không phải toàn bộ quyết định. Một cải tiến có tác động lớn nhưng phụ thuộc vào nền tảng khác có thể chưa sẵn sàng. Một việc nhỏ có thể mở khóa nhiều công việc tiếp theo. Một hạng mục ít tác động trực tiếp nhưng giảm rủi ro bảo mật hoặc giúp khôi phục dịch vụ có thể cần ưu tiên cao. Vì vậy, nhóm cần kết hợp dữ liệu thực tế, đánh giá rủi ro, độ tin cậy, phụ thuộc và năng lực thực hiện.

Bài học này trình bày cách hình thành danh sách cải tiến, ước lượng tác động và công sức, sử dụng ma trận hoặc mô hình điểm, chọn danh mục công việc cân bằng, theo dõi kết quả và điều chỉnh ưu tiên khi có bằng chứng mới.

## 1. Vì sao cần ưu tiên cải tiến có hệ thống?

Cải tiến thường cạnh tranh trực tiếp với phát triển tính năng, sửa lỗi, hỗ trợ vận hành và công việc bắt buộc. Nếu không có cách ưu tiên, nhóm dễ gặp các tình huống:

- Chọn cải tiến dễ thấy nhưng không giải quyết nguyên nhân chính.
- Liên tục tối ưu một bộ test vốn không phải điểm nghẽn.
- Trì hoãn xử lý flaky test khiến nhóm mất niềm tin vào pipeline.
- Đầu tư tự động hóa cho kịch bản ít chạy trong khi luồng quan trọng chưa được bảo vệ.
- Thực hiện nhiều thay đổi cùng lúc nên không biết thay đổi nào tạo ra kết quả.
- Để nợ kỹ thuật và nợ kiểm thử tăng mà không có chủ sở hữu.
- Không dành thời gian cho bảo trì, dữ liệu, môi trường và khả năng quan sát.
- Đánh giá thành công bằng số lượng task hoàn thành thay vì tác động thực tế.

Một quy trình ưu tiên giúp nhóm tập trung vào cải tiến có giá trị cao hơn trong giới hạn nguồn lực. Nó cũng tạo căn cứ để giải thích vì sao một việc được làm trước, một việc được hoãn và một việc cần thêm dữ liệu.

### Kết quả mong đợi

Một quyết định ưu tiên tốt cần làm rõ:

- Vấn đề hoặc cơ hội đang được giải quyết.
- Ai hoặc luồng công việc nào được hưởng lợi.
- Tác động dự kiến và cách đo.
- Công sức, chi phí và thời gian cần thiết.
- Rủi ro nếu không thực hiện.
- Mức độ tin cậy của ước lượng.
- Phụ thuộc và điều kiện sẵn sàng.
- Người sở hữu, thời hạn và tiêu chí hoàn tất.

Ưu tiên không phải cam kết bất biến. Khi dữ liệu, rủi ro, năng lực hoặc mục tiêu thay đổi, thứ tự cần được xem xét lại.

## 2. Xác định đúng cơ hội cải tiến

Trước khi chấm điểm, cần mô tả cơ hội cải tiến dưới dạng vấn đề hoặc kết quả cần đạt. Một đề xuất như “mua công cụ kiểm thử mới” chưa cho biết vấn đề nào cần giải quyết. Một đề xuất tốt hơn có thể là “giảm thời gian chuẩn bị môi trường tích hợp từ 45 phút xuống dưới 10 phút để nhóm có thể chạy kiểm thử hồi quy thường xuyên hơn”.

### Nguồn phát hiện cơ hội

Cơ hội cải tiến có thể đến từ:

- Số liệu pipeline: thời gian chạy, tỷ lệ thất bại, thời gian chờ và số lần rerun.
- Chất lượng kiểm thử: flaky test, test bị bỏ qua, lỗi lọt và độ bao phủ rủi ro.
- Hoạt động triage: thời gian phát hiện, phân loại, tái hiện và sửa lỗi.
- Sự cố production: nguyên nhân lặp lại, thiếu log, thiếu cảnh báo hoặc khó phục hồi.
- Phản hồi từ developer, QA, nghiệp vụ và vận hành.
- Nút thắt quy trình: chờ môi trường, dữ liệu, review hoặc phê duyệt.
- Chi phí vận hành: runner, license, môi trường và công sức bảo trì.
- Thay đổi sản phẩm: kiến trúc mới, tăng tải, thêm tích hợp hoặc yêu cầu tuân thủ.
- Retrospective và review sau phát hành.
- Kết quả thử nghiệm hoặc đánh giá công cụ.

### Phân biệt triệu chứng và vấn đề gốc

Ví dụ, pipeline mất 40 phút có thể do:

- Nhiều test E2E chạy tuần tự.
- Runner thiếu CPU hoặc bộ nhớ.
- Test khởi tạo dữ liệu quá chậm.
- Một nhóm test flaky thường xuyên phải chạy lại.
- Mỗi test tạo môi trường riêng dù có thể tái sử dụng an toàn.
- Pipeline chờ dịch vụ bên ngoài.

Đề xuất “tăng số runner” có thể giảm thời gian chờ nhưng không xử lý test chậm hoặc dữ liệu kém hiệu quả. Trước khi ưu tiên giải pháp, cần hiểu nguyên nhân và xác định chỉ số đang bị ảnh hưởng.

### Viết đề xuất theo cấu trúc vấn đề – tác động – kết quả

Một đề xuất ngắn nên có:

1. **Vấn đề:** điều gì đang gây khó khăn hoặc rủi ro?
2. **Bằng chứng:** số liệu, ví dụ hoặc phản hồi nào hỗ trợ nhận định?
3. **Đối tượng ảnh hưởng:** nhóm, người dùng hoặc luồng nào?
4. **Kết quả mong muốn:** điều gì sẽ tốt hơn sau cải tiến?
5. **Cách đo:** chỉ số nào xác nhận kết quả?
6. **Giải pháp dự kiến:** hướng xử lý ban đầu, có thể thay đổi sau điều tra.

Không nên gắn giải pháp quá sớm khi chưa hiểu vấn đề. Có thể đưa nhiều phương án khác nhau vào đánh giá.

## 3. Xác định tác động cần đo

Tác động là lợi ích hoặc mức giảm rủi ro dự kiến nếu cải tiến thành công. Tác động không chỉ là tiết kiệm thời gian. Với chiến lược kiểm thử, nó có thể liên quan đến chất lượng bằng chứng, khả năng phát hiện lỗi, độ tin cậy, tốc độ phản hồi và chi phí vận hành.

### Tác động đến tốc độ và luồng công việc

- Giảm thời gian chạy pipeline.
- Giảm thời gian chờ môi trường hoặc dữ liệu.
- Rút ngắn thời gian triage và tái hiện lỗi.
- Tăng số vòng phản hồi trong ngày.
- Giảm thời gian chuẩn bị bản phát hành.
- Giảm công việc thủ công lặp lại.

Cần phân biệt thời gian chạy với thời gian chờ. Một pipeline chạy 20 phút nhưng chờ 40 phút để có runner vẫn tạo tổng thời gian phản hồi dài.

### Tác động đến chất lượng và rủi ro

- Tăng khả năng phát hiện lỗi quan trọng trước phát hành.
- Giảm lỗi lọt vào production.
- Tăng độ tin cậy của kết quả kiểm thử.
- Giảm flaky test và false alarm.
- Tăng khả năng kiểm tra dữ liệu, bảo mật hoặc tính nhất quán.
- Giảm nguy cơ thao tác sai trong migration hoặc triển khai.
- Cải thiện khả năng truy vết và giải thích quyết định.

Không nên dùng tỷ lệ pass làm đại diện duy nhất cho chất lượng. Một cải tiến làm giảm test thất bại bằng cách bỏ qua test có thể làm pipeline xanh hơn nhưng giảm khả năng phát hiện lỗi.

### Tác động đến con người và phối hợp

- Giảm gián đoạn và context switching.
- Giảm phụ thuộc vào một chuyên gia.
- Giúp thành viên mới tiếp nhận công việc nhanh hơn.
- Làm rõ quyền sở hữu và quyết định.
- Giảm xung đột do thông tin thiếu hoặc không nhất quán.
- Tăng khả năng phối hợp giữa phát triển, kiểm thử, nghiệp vụ và vận hành.

### Tác động đến chi phí

- Giảm giờ công bảo trì hoặc xử lý thủ công.
- Giảm chi phí hạ tầng, runner và license.
- Tránh chi phí sự cố, khôi phục hoặc bồi hoàn.
- Giảm chi phí duy trì công cụ hoặc tích hợp trùng lặp.
- Giảm chi phí cơ hội do chậm phát hành.

### Tác động chiến lược và khả năng mở khóa

Một cải tiến có thể không tạo lợi ích lớn ngay lập tức nhưng mở đường cho nhiều việc khác. Ví dụ, chuẩn hóa dữ liệu kiểm thử có thể giúp tự động hóa nhiều luồng, tạo môi trường tạm thời và kiểm tra migration đáng tin cậy hơn.

Cần ghi nhận giá trị mở khóa này, nhưng không nên phóng đại lợi ích tương lai chưa có kế hoạch cụ thể.

## 4. Đánh giá tác động theo nhiều chiều

Có thể dùng các chiều sau để tránh chỉ nhìn một chỉ số:

| Chiều tác động | Câu hỏi đánh giá | Ví dụ bằng chứng |
|---|---|---|
| Người dùng/nghiệp vụ | Có giảm lỗi hoặc gián đoạn ở luồng quan trọng không? | Sự cố, ticket hỗ trợ, giao dịch lỗi |
| Chất lượng | Có tăng khả năng phát hiện lỗi hoặc giảm false positive không? | Lỗi lọt, test flaky, kết quả hồi quy |
| Tốc độ | Có rút ngắn thời gian phản hồi hoặc chờ không? | Lead time, pipeline duration |
| Độ tin cậy | Có giảm gián đoạn hoặc cải thiện phục hồi không? | Tỷ lệ thành công, MTTR |
| Năng suất nhóm | Có giảm thao tác thủ công hoặc phụ thuộc cá nhân không? | Giờ công, thời gian triage |
| Chi phí | Có giảm chi phí hạ tầng hoặc vận hành không? | Chi phí runner, license, giờ công |
| Tuân thủ/chứng minh | Có cải thiện truy vết và độ tin cậy hồ sơ không? | Hồ sơ thiếu, thời gian audit |
| Khả năng mở rộng | Có hỗ trợ kiến trúc, tải hoặc nhóm mới không? | Nút thắt, giới hạn năng lực |

Không phải mọi cải tiến cần tác động trên tất cả chiều. Chọn những chiều liên quan và ghi rõ chiều nào không áp dụng.

### Tác động trực tiếp và gián tiếp

Tác động trực tiếp có thể đo ngay, ví dụ pipeline giảm 15 phút. Tác động gián tiếp cần thận trọng hơn, ví dụ giảm mệt mỏi do chờ đợi có thể cải thiện trải nghiệm nhóm nhưng khó quy đổi thành con số chính xác.

Có thể ghi nhận lợi ích định tính nếu chưa có dữ liệu, nhưng cần nói rõ đó là giả định và xác định cách kiểm tra sau triển khai.

## 5. Ước lượng công sức thực hiện

Công sức là tổng nguồn lực cần để đưa cải tiến đến trạng thái có thể sử dụng và duy trì. Không nên chỉ ước lượng thời gian viết mã hoặc cấu hình công cụ.

Các thành phần cần tính:

- Điều tra và xác nhận nguyên nhân.
- Thiết kế giải pháp.
- Thay đổi mã, test, dữ liệu hoặc hạ tầng.
- Tích hợp với hệ thống hiện có.
- Review và phê duyệt.
- Kiểm thử, thử nghiệm và xác minh.
- Di chuyển hoặc chuyển đổi người dùng.
- Tài liệu và đào tạo.
- Triển khai và theo dõi.
- Bảo trì sau khi đưa vào sử dụng.

### Công sức khác với thời gian lịch

Một cải tiến cần 5 ngày công của hai người có thể kéo dài ba tuần nếu phụ thuộc vào phê duyệt, môi trường hoặc nhóm khác. Cần ước lượng riêng:

- **Effort:** tổng công sức của các vai trò.
- **Elapsed time:** thời gian lịch từ bắt đầu đến hoàn tất.
- **Waiting time:** thời gian chờ phụ thuộc hoặc quyết định.
- **Ongoing cost:** công sức duy trì sau khi triển khai.

### Đưa chi phí duy trì vào ước lượng

Một framework mới có thể triển khai nhanh nhưng tạo thêm chi phí nâng cấp, license, plugin, bảo mật và hỗ trợ. Một script đơn giản có thể rẻ lúc đầu nhưng khó mở rộng và thiếu người sở hữu.

Ước lượng nên tính cả chi phí vòng đời phù hợp với phạm vi quyết định.

### Dùng dải ước lượng khi chưa chắc chắn

Thay vì ghi “3 ngày” khi chưa điều tra, có thể ước lượng “2–5 ngày công, chưa gồm thời gian chờ nhóm nền tảng”. Dải ước lượng phản ánh mức bất định và giúp người quyết định hiểu rủi ro kế hoạch.

## 6. Chấm điểm tác động và công sức

Để so sánh nhiều đề xuất, nhóm có thể dùng thang điểm định tính. Một ví dụ đơn giản:

### Thang tác động

| Điểm | Mức | Mô tả |
|---:|---|---|
| 1 | Rất thấp | Lợi ích giới hạn, ít người hoặc ít công việc được hưởng lợi |
| 2 | Thấp | Cải thiện nhỏ ở một khu vực |
| 3 | Trung bình | Cải thiện rõ cho một luồng hoặc nhóm |
| 4 | Cao | Ảnh hưởng nhiều luồng, nhóm hoặc giảm rủi ro đáng kể |
| 5 | Rất cao | Bảo vệ luồng cốt lõi, giảm rủi ro nghiêm trọng hoặc mở khóa năng lực chiến lược |

### Thang công sức

| Điểm | Mức | Mô tả |
|---:|---|---|
| 1 | Rất thấp | Có thể hoàn tất trong vài giờ hoặc thay đổi rất nhỏ |
| 2 | Thấp | Khoảng một đến hai ngày công, ít phụ thuộc |
| 3 | Trung bình | Vài ngày đến khoảng một tuần công |
| 4 | Cao | Nhiều tuần công hoặc cần phối hợp nhiều vai trò |
| 5 | Rất cao | Dự án nhiều giai đoạn, phụ thuộc lớn hoặc chi phí duy trì đáng kể |

Đây là thang minh họa. Nhóm nên định nghĩa dải thời gian phù hợp với quy mô và cách ước lượng của mình.

### Ma trận tác động – công sức

| Tác động / Công sức | Thấp | Trung bình | Cao |
|---|---|---|---|
| Cao | Ưu tiên sớm | Lập kế hoạch gần | Chia giai đoạn, xác minh lợi ích |
| Trung bình | Chọn khi có năng lực | So sánh với việc khác | Chỉ làm khi có lý do chiến lược |
| Thấp | Quick win nếu gần như không có chi phí | Đưa backlog thấp | Hoãn hoặc loại bỏ |

Ma trận giúp định hướng thảo luận:

- **Tác động cao, công sức thấp:** thường là ứng viên ưu tiên sớm.
- **Tác động cao, công sức cao:** cần chia nhỏ, thử nghiệm hoặc đưa vào lộ trình.
- **Tác động thấp, công sức thấp:** có thể làm khi đang có khoảng trống, nhưng tránh để chúng chiếm hết thời gian.
- **Tác động thấp, công sức cao:** thường nên hoãn hoặc loại bỏ trừ khi có yêu cầu bắt buộc.

Không nên coi ma trận là thuật toán tự động. Một cải tiến giảm rủi ro nghiêm trọng có thể cần thực hiện dù công sức cao và lợi ích khó đo trực tiếp.

## 7. Dùng tỷ lệ tác động trên công sức một cách thận trọng

Một cách so sánh nhanh là chia điểm tác động cho điểm công sức:

\[
\text{Tỷ lệ ưu tiên sơ bộ} = \frac{\text{Điểm tác động}}{\text{Điểm công sức}}
\]

Ví dụ:

| Cải tiến | Tác động | Công sức | Tỷ lệ |
|---|---:|---:|---:|
| Sửa nhóm test flaky chính | 5 | 2 | 2,5 |
| Tự động tạo dữ liệu test | 4 | 3 | 1,33 |
| Thay toàn bộ framework E2E | 4 | 5 | 0,8 |
| Chuẩn hóa báo cáo test | 2 | 1 | 2,0 |

Tỷ lệ cao giúp phát hiện ứng viên có tác động tương đối lớn so với công sức. Tuy nhiên, nó có một số giới hạn:

- Điểm là thang thứ bậc, không phải đơn vị đo chính xác.
- Tỷ lệ có thể làm một việc nhỏ nhưng ít quan trọng đứng quá cao.
- Không thể hiện rủi ro bắt buộc hoặc phụ thuộc.
- Không phản ánh độ tin cậy của ước lượng.
- Không tính đầy đủ giá trị mở khóa và chi phí duy trì.

Dùng tỷ lệ như tín hiệu để thảo luận, không dùng như thứ tự tuyệt đối.

## 8. Bổ sung độ tin cậy và mức bất định

Một ước lượng tác động cao nhưng chỉ dựa trên phỏng đoán cần được xử lý khác với lợi ích đã được đo nhiều lần. Vì vậy, nên ghi mức độ tin cậy.

Có thể dùng ba mức:

- **Cao:** có số liệu nền, nguyên nhân đã được xác nhận hoặc kết quả thử nghiệm.
- **Trung bình:** có ví dụ và bằng chứng một phần, nhưng phạm vi hoặc hiệu quả còn bất định.
- **Thấp:** chủ yếu là giả định, chưa kiểm tra nguyên nhân hoặc chưa rõ người hưởng lợi.

### Điều chỉnh cách xử lý theo độ tin cậy

- Tác động cao, công sức thấp, tin cậy cao: có thể đưa vào kế hoạch gần.
- Tác động cao nhưng tin cậy thấp: thực hiện spike hoặc thử nghiệm nhỏ trước.
- Công sức cao và bất định cao: chia giai đoạn, giới hạn phạm vi hoặc xác minh phụ thuộc.
- Tác động thấp và tin cậy thấp: thường chưa cần đầu tư thêm thời gian phân tích.

### Spike là một hạng mục có đầu ra

Spike không phải thời gian nghiên cứu không giới hạn. Cần xác định câu hỏi cần trả lời, thời gian tối đa, cách thử và kết quả cần bàn giao. Ví dụ: “Trong hai ngày, đo khả năng giảm thời gian pipeline bằng cách chạy song song một nhóm test đại diện; đầu ra là số liệu trước/sau và ước lượng triển khai toàn bộ.”

## 9. Tính đến rủi ro nếu không cải tiến

Một số cải tiến không tạo lợi ích dễ nhìn thấy nhưng giảm nguy cơ sự cố. Nếu chỉ chấm điểm theo năng suất hoặc thời gian tiết kiệm, nhóm có thể liên tục hoãn công việc bảo mật, phục hồi và độ tin cậy.

Đánh giá rủi ro nếu không thực hiện:

- Hậu quả có thể xảy ra.
- Khả năng hoặc tần suất.
- Phạm vi người dùng, dữ liệu và dịch vụ.
- Khả năng phát hiện trước khi hậu quả lan rộng.
- Khả năng phục hồi.
- Nghĩa vụ pháp lý, hợp đồng hoặc chính sách.
- Thời gian còn lại trước khi rủi ro tăng.

### Ví dụ các cải tiến giảm rủi ro

- Bổ sung kiểm thử phân quyền cho API nhạy cảm.
- Tạo kiểm thử migration và đối soát dữ liệu.
- Thiết lập backup restore drill.
- Bổ sung cảnh báo cho lỗi webhook hoặc backlog.
- Loại bỏ secret khỏi log.
- Tăng khả năng rollback của thay đổi schema.
- Kiểm thử concurrency cho giao dịch quan trọng.

Nếu rủi ro vượt ngưỡng chấp nhận hoặc có yêu cầu bắt buộc, công việc có thể trở thành điều kiện phải làm. Khi đó, ma trận tác động/công sức vẫn giúp lập kế hoạch thực hiện, nhưng không được dùng để loại bỏ nghĩa vụ.

## 10. Xem xét phụ thuộc và khả năng sẵn sàng

Một cải tiến có thể có giá trị cao nhưng chưa thể thực hiện vì thiếu nền tảng, quyền, dữ liệu hoặc quyết định từ nhóm khác.

Cần xác định:

- Phụ thuộc kỹ thuật.
- Nhóm cần hỗ trợ.
- Quyền và môi trường.
- Thay đổi kiến trúc hoặc hợp đồng liên quan.
- Lịch phát hành và thời điểm phù hợp.
- Rủi ro xung đột với công việc đang chạy.
- Điều kiện để bắt đầu.
- Phương án nếu phụ thuộc chậm.

### Phân biệt giá trị và mức sẵn sàng

Một hạng mục chưa sẵn sàng không đồng nghĩa nó ít quan trọng. Có thể giữ mức ưu tiên cao nhưng ghi trạng thái “blocked” và xử lý phụ thuộc. Ngược lại, một hạng mục sẵn sàng ngay không tự động trở thành ưu tiên cao nhất.

### Ưu tiên công việc mở khóa

Một cải tiến nền tảng có thể làm giảm công sức của nhiều cải tiến sau. Ví dụ, chuẩn hóa môi trường tạm thời có thể mở khóa kiểm thử tích hợp song song, kiểm thử migration và kiểm tra nhánh lỗi. Giá trị mở khóa nên được mô tả bằng các hạng mục cụ thể sẽ được hỗ trợ.

## 11. Chia nhỏ cải tiến lớn để tạo giá trị sớm

Cải tiến lớn thường có rủi ro ước lượng cao và thời gian phản hồi dài. Chia nhỏ giúp kiểm tra giả định, thu được giá trị sớm và có thể dừng nếu kết quả không như mong đợi.

Ví dụ, thay toàn bộ framework E2E có thể chia thành:

1. Đo thời gian và độ ổn định hiện tại.
2. Chọn một luồng đại diện để thử framework mới.
3. So sánh khả năng bảo trì, tốc độ và độ tin cậy.
4. Xác định chiến lược chạy song song hoặc chuyển đổi.
5. Chuyển một nhóm test có giá trị cao.
6. Theo dõi kết quả và chi phí duy trì.
7. Quyết định mở rộng hoặc dừng.

### Định nghĩa lát cắt có thể kiểm chứng

Mỗi lát cắt nên có:

- Phạm vi rõ.
- Người dùng hoặc nhóm hưởng lợi.
- Kết quả đo được.
- Phụ thuộc cần thiết.
- Điều kiện dừng.
- Cách hoàn nguyên nếu thử nghiệm thất bại.

Không nên chia nhỏ theo số task kỹ thuật mà không tạo được kết quả có thể đánh giá.

## 12. Các mô hình ưu tiên có thể sử dụng

Ma trận tác động/công sức phù hợp với thảo luận nhanh. Khi danh sách lớn hoặc nhiều bên liên quan, có thể dùng mô hình có cấu trúc hơn.

### RICE

RICE thường gồm:

- **Reach:** số người hoặc đối tượng được ảnh hưởng trong một khoảng thời gian.
- **Impact:** mức tác động đến mỗi đối tượng.
- **Confidence:** độ tin cậy của ước lượng.
- **Effort:** công sức thực hiện.

Một công thức thường dùng:

\[
\text{RICE} = \frac{\text{Reach} \times \text{Impact} \times \text{Confidence}}{\text{Effort}}
\]

Phù hợp khi có thể ước lượng phạm vi hưởng lợi và cần so sánh nhiều sáng kiến. Hạn chế là các giá trị có thể khó đo và không phản ánh đầy đủ nghĩa vụ bắt buộc hoặc rủi ro hiếm nhưng nghiêm trọng.

### WSJF

Weighted Shortest Job First so sánh chi phí trì hoãn với kích thước công việc. Có thể dùng các thành phần:

- Giá trị người dùng hoặc nghiệp vụ.
- Mức giảm rủi ro hoặc tạo cơ hội.
- Tính cấp bách theo thời gian.
- Kích thước công việc.

Công thức khái quát:

\[
\text{WSJF} = \frac{\text{Cost of Delay}}{\text{Job Size}}
\]

Phù hợp khi cần xem xét công việc nào mất giá trị nhiều nhất nếu bị trì hoãn. Cần thống nhất cách chấm điểm và tránh tạo độ chính xác giả.

### MoSCoW

Phân loại thành:

- Must have: bắt buộc.
- Should have: rất quan trọng nhưng có thể có phương án thay thế.
- Could have: có giá trị nhưng không thiết yếu.
- Won't have this time: không thực hiện trong chu kỳ này.

MoSCoW hữu ích để thống nhất phạm vi, nhưng không tự xếp thứ tự giữa các mục trong cùng nhóm. Cần bổ sung tác động, công sức và phụ thuộc.

### Cost of Delay

Đánh giá tổn thất hoặc giá trị bị mất khi trì hoãn. Ví dụ, cải tiến giảm rủi ro bảo mật có thể cần làm trước khi mở rộng người dùng; tối ưu pipeline có thể tiết kiệm thời gian mỗi ngày; tài liệu phục hồi có thể rất quan trọng trước mùa cao điểm.

Không nhất thiết phải quy mọi tác động thành tiền. Có thể dùng mức định tính và ghi rõ cơ sở.

### Chọn mô hình theo mục đích

| Tình huống | Mô hình phù hợp |
|---|---|
| Nhóm nhỏ, ít hạng mục | Ma trận tác động/công sức |
| Nhiều đề xuất cần so sánh | RICE hoặc thang điểm có trọng số |
| Công việc có giá trị giảm dần theo thời gian | Cost of Delay hoặc WSJF |
| Chốt phạm vi một chu kỳ | MoSCoW kết hợp đánh giá tác động |
| Có nghĩa vụ hoặc rủi ro bắt buộc | Cổng bắt buộc trước khi xếp hạng các việc tùy chọn |

Không cần dùng nhiều mô hình cùng lúc. Chọn một cách đủ minh bạch để ra quyết định và giữ nhất quán trong một chu kỳ.

## 13. Thiết kế thang điểm có trọng số

Khi nhiều yếu tố cần được cân nhắc, nhóm có thể tạo điểm tổng hợp. Ví dụ:

\[
\text{Điểm giá trị} =
0.30I + 0.25R + 0.20T + 0.15U + 0.10E
\]

Trong đó:

- \(I\): tác động đến người dùng hoặc nghiệp vụ.
- \(R\): mức giảm rủi ro.
- \(T\): cải thiện tốc độ hoặc năng suất.
- \(U\): giá trị mở khóa hoặc khả năng mở rộng.
- \(E\): mức cấp thiết theo thời gian.

Các trọng số chỉ là ví dụ. Nhóm cần thống nhất theo mục tiêu; nếu rủi ro bảo mật là trọng tâm, trọng số giảm rủi ro có thể cao hơn.

Công sức có thể chấm riêng theo thang 1–5 hoặc ước lượng ngày công. Không nên trừ công sức khỏi điểm giá trị theo cách tùy tiện; hãy dùng tỷ lệ hoặc ma trận đã thống nhất.

### Ví dụ tính điểm

Giả sử một cải tiến được chấm:

- Tác động \(I=4\)
- Giảm rủi ro \(R=5\)
- Tốc độ \(T=3\)
- Mở khóa \(U=4\)
- Cấp thiết \(E=3\)

Điểm giá trị:

\[
0.30(4)+0.25(5)+0.20(3)+0.15(4)+0.10(3)=3.95
\]

Nếu công sức là 2 trên thang 1–5, đây có thể là ứng viên ưu tiên cao. Tuy nhiên, vẫn cần xem độ tin cậy, phụ thuộc và điều kiện bắt buộc.

### Tránh độ chính xác giả

Một điểm 3,95 không có nghĩa giá trị chính xác hơn điểm 3,8. Mô hình giúp cấu trúc cuộc thảo luận, không biến đánh giá chủ quan thành sự thật khoa học. Nên ghi lý do và khoảng bất định thay vì chỉ lưu tổng điểm.

## 14. Cân bằng quick wins và cải tiến nền tảng

Quick win là việc có thể tạo giá trị trong thời gian ngắn với công sức thấp. Cải tiến nền tảng có thể mất nhiều thời gian nhưng giảm chi phí hoặc rủi ro trong dài hạn.

Nếu chỉ làm quick win, nhóm có thể liên tục sửa triệu chứng và không xử lý nợ kỹ thuật. Nếu chỉ đầu tư nền tảng, nhóm có thể mất nhiều chu kỳ mà chưa tạo giá trị quan sát được.

Một danh mục cân bằng có thể gồm:

- Cải tiến nhanh giúp giảm điểm đau hiện tại.
- Cải tiến giảm rủi ro cho luồng quan trọng.
- Đầu tư nền tảng giúp mở khóa năng lực.
- Bảo trì và loại bỏ nợ kỹ thuật.
- Thử nghiệm nhỏ để kiểm chứng giả định.
- Công việc bắt buộc về bảo mật, tuân thủ hoặc vận hành.

Tỷ lệ phân bổ không nên cố định cho mọi nhóm. Có thể thay đổi theo giai đoạn sản phẩm, sự cố, thời hạn phát hành và năng lực hiện tại.

### Dành năng lực cho bảo trì

Nếu toàn bộ thời gian được dùng cho tính năng mới, nợ kiểm thử và hạ tầng sẽ tích lũy. Nhóm nên dành một phần năng lực có kế hoạch cho bảo trì, nhưng cần đo hiệu quả và điều chỉnh theo nhu cầu thực tế.

## 15. Ví dụ ưu tiên cải tiến trong nhóm kiểm thử

Giả sử nhóm có các đề xuất sau:

| Đề xuất | Tác động | Công sức | Tin cậy | Nhận định |
|---|---:|---:|---|---|
| Sửa 20 test flaky gây rerun thường xuyên | Cao | Thấp | Cao | Ưu tiên sớm |
| Tạo công cụ seed dữ liệu dùng chung | Cao | Trung bình | Trung bình | Làm spike rồi chia giai đoạn |
| Thay framework E2E toàn bộ | Trung bình/Cao | Rất cao | Thấp | Thử nghiệm trên một luồng trước |
| Bổ sung dashboard lỗi theo dịch vụ | Trung bình/Cao | Thấp | Cao | Có thể làm sớm nếu metric sẵn có |
| Viết lại toàn bộ tài liệu cũ | Thấp/Trung bình | Cao | Thấp | Chọn tài liệu quan trọng và cập nhật theo thay đổi |
| Thêm kiểm thử phân quyền cho API nhạy cảm | Rất cao | Trung bình | Cao | Ưu tiên theo rủi ro |

Nhóm không nên chọn chỉ theo tỷ lệ tác động/công sức. Kiểm thử phân quyền có thể là điều kiện cần vì rủi ro; sửa flaky test có thể giải phóng thời gian ngay; dashboard hỗ trợ điều tra; công cụ seed có thể mở khóa nhiều kiểm thử; thay framework cần thêm bằng chứng trước khi đầu tư lớn.

### Chuyển danh sách thành kế hoạch

Một kế hoạch khả thi có thể:

1. Sửa nhóm flaky test có tác động lớn.
2. Bổ sung kiểm thử phân quyền theo phạm vi rủi ro.
3. Làm spike công cụ seed dữ liệu.
4. Tạo dashboard từ metric hiện có.
5. Thử framework mới trên một luồng có giá trị.
6. Chỉ mở rộng khi kết quả thử nghiệm chứng minh lợi ích.

Thứ tự có thể thay đổi nếu có sự cố hoặc thời hạn mới. Điều quan trọng là lý do thay đổi được ghi lại.

## 16. Đánh giá cải tiến theo tác động đến toàn bộ vòng đời kiểm thử

Một cải tiến có thể tạo lợi ích ở một giai đoạn nhưng tăng chi phí ở giai đoạn khác.

Ví dụ, tự động hóa thêm nhiều E2E có thể tăng khả năng kiểm tra hành trình, nhưng cũng làm pipeline chậm, flaky và tốn bảo trì nếu chọn sai tầng.

Cần xem toàn bộ vòng đời:

- Phân tích yêu cầu.
- Chuẩn bị dữ liệu và môi trường.
- Thiết kế kiểm thử.
- Thực thi và phản hồi.
- Triage và điều tra.
- Sửa lỗi và hồi quy.
- Phát hành và giám sát.
- Bảo trì tài sản kiểm thử.

### Đánh giá chi phí dịch chuyển

Hãy hỏi:

- Công việc có giảm ở bước này nhưng tăng ở bước khác không?
- Có tạo thêm phụ thuộc vào một công cụ hoặc chuyên gia không?
- Có làm tăng thời gian bảo trì không?
- Có tạo false positive hoặc giảm khả năng quan sát không?
- Có ảnh hưởng tốc độ developer feedback không?
- Có làm quy trình khó hiểu hơn với người mới không?

Một cải tiến chỉ có giá trị nếu tổng thể tốt hơn trong bối cảnh mục tiêu, không chỉ làm đẹp một chỉ số cục bộ.

## 17. Chọn phạm vi thử nghiệm trước khi đầu tư lớn

Khi tác động hoặc công sức chưa chắc chắn, nên thực hiện thử nghiệm có giới hạn.

### Xác định giả thuyết

Ví dụ: “Chạy song song nhóm API test sẽ giảm thời gian pipeline ít nhất 30% mà không tăng flaky rate hoặc tải database vượt ngưỡng.”

### Chọn phạm vi đại diện

Chọn một nhóm test đủ đại diện cho dữ liệu, phụ thuộc và mức tải, nhưng đủ nhỏ để hoàn nguyên dễ dàng.

### Xác định tiêu chí thành công và dừng

Ví dụ:

- Thời gian chạy giảm tối thiểu 25%.
- Tỷ lệ thất bại không tăng đáng kể.
- Không tạo tranh chấp dữ liệu.
- Chi phí runner không vượt ngân sách.
- Kết quả có thể tái hiện qua nhiều lần chạy.

### Ghi nhận kết quả

Lưu dữ liệu trước/sau, phiên bản, cấu hình, số lần chạy, giới hạn và khuyến nghị. Nếu thử nghiệm không đạt, ghi rõ giả thuyết nào bị bác bỏ và bài học thu được.

Không nên kéo dài thử nghiệm vô hạn chỉ vì đã đầu tư công sức. Cần có thời hạn và quyết định tiếp tục, điều chỉnh hoặc dừng.

## 18. Xem xét phụ thuộc và trình tự thực hiện

Một số cải tiến phải thực hiện theo thứ tự. Ví dụ, muốn chạy E2E song song có thể cần cô lập dữ liệu trước. Muốn đo hiệu năng cần môi trường và dữ liệu đại diện. Muốn tự động hóa kiểm thử hợp đồng cần thống nhất schema.

Có thể biểu diễn phụ thuộc:

**Chuẩn hóa dữ liệu → Cô lập test state → Chạy song song → Đo hiệu năng pipeline**

### Phân biệt hạng mục tiên quyết và hạng mục độc lập

- **Tiên quyết:** phải hoàn thành trước khi hạng mục khác bắt đầu.
- **Độc lập:** có thể thực hiện song song.
- **Có thể thay thế:** có phương án khác nếu phụ thuộc chưa sẵn sàng.
- **Mở khóa:** giúp nhiều hạng mục sau khả thi hơn.

Không nên xếp hạng từng task riêng lẻ mà bỏ qua chuỗi phụ thuộc. Một hạng mục có điểm tác động thấp nhưng là điều kiện tiên quyết có thể cần thực hiện trước.

### Quản lý giới hạn công việc đang làm

Nếu nhóm bắt đầu quá nhiều cải tiến cùng lúc, công việc bị phân mảnh và kéo dài. Nên giới hạn WIP, hoàn tất hạng mục đang làm trước khi mở thêm việc, trừ khi có lý do khẩn cấp.

## 19. Phân bổ nguồn lực và năng lực thực hiện

Ưu tiên cao không có nghĩa có thể bắt đầu ngay. Cần xem nhóm có người, thời gian, quyền và kỹ năng phù hợp hay không.

Các yếu tố:

- Số người có thể thực hiện.
- Kỹ năng chuyên môn cần thiết.
- Công việc tính năng và hỗ trợ đã cam kết.
- Lịch phát hành và thời gian đóng băng.
- Thời gian chờ nhóm khác.
- Năng lực môi trường và hạ tầng.
- Ngân sách công cụ hoặc dịch vụ.
- Chi phí bảo trì sau cải tiến.

### Không dùng 100% năng lực danh nghĩa

Thời gian của nhóm còn bị chia cho hỗ trợ, review, sự cố, họp, học tập và công việc không dự đoán được. Kế hoạch nên dùng năng lực thực tế đã quan sát trong các chu kỳ trước, có dự phòng phù hợp.

### Gắn người sở hữu và người dự phòng

Cải tiến quan trọng cần người sở hữu và người có thể tiếp nhận. Nếu chỉ một chuyên gia có thể triển khai hoặc duy trì, cải tiến có thể tạo ra điểm phụ thuộc mới.

## 20. Theo dõi tiến độ và kết quả sau cải tiến

Hoàn thành task không đồng nghĩa đạt tác động mong đợi. Cần đo trước và sau, đồng thời theo dõi xem lợi ích có duy trì hay không.

### Xác định đường cơ sở

Trước khi thay đổi, ghi:

- Chỉ số hiện tại.
- Khoảng thời gian đo.
- Số mẫu hoặc số lần chạy.
- Phạm vi và điều kiện.
- Nguồn dữ liệu.
- Yếu tố có thể làm kết quả sai lệch.

Ví dụ, thời gian pipeline trung bình có thể bị ảnh hưởng bởi cache, tải runner hoặc số test thay đổi. Cần so sánh các lần chạy tương đương hoặc phân tích theo nhóm.

### Chọn chỉ số kết quả

| Mục tiêu cải tiến | Chỉ số kết quả |
|---|---|
| Giảm flaky test | Tỷ lệ rerun do flaky, số test bị quarantine, tỷ lệ thất bại không ổn định |
| Tăng tốc pipeline | Thời gian end-to-end, thời gian chờ runner, chi phí mỗi lần chạy |
| Cải thiện dữ liệu | Thời gian chuẩn bị, tỷ lệ lỗi fixture, khả năng tái tạo |
| Tăng khả năng phát hiện | Lỗi phát hiện trước phát hành, lỗi lọt, độ bao phủ rủi ro |
| Cải thiện triage | Thời gian từ lỗi đến phân loại và xác định nguyên nhân |
| Tăng khả năng phục hồi | Thời gian khôi phục, tỷ lệ diễn tập đạt, số bước thủ công |
| Cải thiện tài liệu | Thời gian tìm thông tin, số câu hỏi lặp, tỷ lệ tài liệu quan trọng còn đúng |

### Kiểm tra tác động phụ

Một cải tiến có thể đạt mục tiêu chính nhưng gây vấn đề khác. Ví dụ, tăng song song làm pipeline nhanh hơn nhưng khiến database quá tải. Cần theo dõi các chỉ số bảo vệ (guardrail) để phát hiện trade-off.

### Quyết định sau đo lường

- Giữ và mở rộng nếu lợi ích được xác nhận.
- Điều chỉnh nếu kết quả một phần hoặc có tác động phụ.
- Hoàn nguyên nếu rủi ro vượt lợi ích.
- Dừng nếu giả thuyết bị bác bỏ.
- Cập nhật ước lượng và ưu tiên của các hạng mục liên quan.

## 21. Quản lý danh mục cải tiến

Danh sách cải tiến nên được quản lý như một backlog có mục tiêu và chủ sở hữu, không phải một danh sách ý tưởng không giới hạn.

Mỗi mục nên có:

- ID và tiêu đề.
- Vấn đề và bằng chứng.
- Kết quả mong muốn.
- Nhóm hoặc người hưởng lợi.
- Tác động theo các chiều liên quan.
- Công sức và chi phí duy trì.
- Độ tin cậy.
- Rủi ro nếu trì hoãn.
- Phụ thuộc và trạng thái sẵn sàng.
- Chủ sở hữu và người hỗ trợ.
- Chỉ số thành công.
- Trạng thái và ngày xem xét.

### Các trạng thái tham khảo

- Ý tưởng mới.
- Cần thêm dữ liệu.
- Đã đánh giá.
- Đã ưu tiên.
- Sẵn sàng thực hiện.
- Đang thực hiện.
- Chờ phụ thuộc.
- Đang đo kết quả.
- Đã hoàn tất.
- Đã hoãn.
- Đã loại bỏ.

Mục “đã hoãn” nên có lý do và điều kiện xem xét lại. Mục “đã loại bỏ” nên ghi lý do để nhóm không lặp lại cùng đề xuất mà không có thông tin mới.

### Rà soát backlog định kỳ

Trong mỗi chu kỳ hoặc buổi review, nhóm cần:

- Bổ sung đề xuất mới từ số liệu và sự cố.
- Xác nhận vấn đề còn tồn tại.
- Cập nhật tác động và công sức.
- Kiểm tra phụ thuộc.
- Xem kết quả cải tiến đã triển khai.
- Loại bỏ hoặc gộp mục trùng.
- Chọn số lượng việc phù hợp năng lực.

## 22. Phối hợp khi nhiều nhóm cùng đề xuất cải tiến

Các nhóm có thể có mục tiêu khác nhau. QA muốn giảm flaky test; developer muốn tăng tốc build; vận hành muốn cải thiện observability; nghiệp vụ muốn tăng kiểm tra luồng thanh toán.

Cần đánh giá trên mục tiêu chung và tác động toàn hệ thống.

### Cách xử lý

1. Chuẩn hóa đề xuất theo cùng cấu trúc.
2. Xác định nhóm hưởng lợi và nhóm chịu chi phí.
3. Làm rõ tác động chéo.
4. Xác định ai có quyền quyết định khi nguồn lực xung đột.
5. Chọn một danh mục ưu tiên chung hoặc ghi rõ danh mục theo nhóm.
6. Giao chủ sở hữu và cơ chế phối hợp.
7. Theo dõi lợi ích ở cấp liên nhóm.

### Tránh tối ưu cục bộ

Ví dụ, một nhóm có thể giảm thời gian test bằng cách chuyển nhiều kiểm thử sang môi trường dùng chung, nhưng làm môi trường quá tải cho các nhóm khác. Cần đánh giá tác động tổng thể, không chỉ số liệu của nhóm đề xuất.

## 23. Những sai lầm thường gặp

- **Chọn việc dễ làm nhất:** tạo nhiều quick win nhưng bỏ qua rủi ro lớn.
- **Chỉ nhìn tác động trực tiếp:** bỏ sót giá trị giảm rủi ro và mở khóa.
- **Ước lượng công sức quá thấp:** quên điều tra, review, triển khai, tài liệu và bảo trì.
- **Không tính thời gian chờ:** kế hoạch trông ngắn nhưng bị phụ thuộc kéo dài.
- **Chấm điểm quá chính xác:** biến giả định thành con số có vẻ khách quan.
- **Không ghi độ tin cậy:** hạng mục dựa trên phỏng đoán được xếp ngang bằng bằng chứng thực tế.
- **Bỏ qua công việc bắt buộc:** dùng điểm thấp để trì hoãn bảo mật hoặc tuân thủ.
- **Không chia nhỏ cải tiến lớn:** chờ quá lâu mới biết giả thuyết sai.
- **Mở quá nhiều việc cùng lúc:** tăng WIP và thời gian hoàn tất.
- **Không đo trước và sau:** không biết cải tiến có tạo giá trị không.
- **Đo chỉ số sai:** pipeline nhanh hơn nhưng độ tin cậy giảm.
- **Không có người sở hữu:** cải tiến hoàn thành nhưng không được duy trì.
- **Không xem lại ưu tiên:** backlog không phản ánh rủi ro và mục tiêu hiện tại.
- **Tối ưu cục bộ:** một nhóm tốt lên nhưng toàn hệ thống kém đi.

## 24. Mẫu đề xuất cải tiến

~~~text
ID:
TÊN CẢI TIẾN:
NGƯỜI ĐỀ XUẤT:
NHÓM / SẢN PHẨM:

VẤN ĐỀ:
BẰNG CHỨNG:
ĐỐI TƯỢNG ẢNH HƯỞNG:
KẾT QUẢ MONG MUỐN:

TÁC ĐỘNG:
- Người dùng / nghiệp vụ:
- Chất lượng / rủi ro:
- Tốc độ / năng suất:
- Chi phí:
- Khả năng mở khóa:

CÁCH ĐO:
ĐƯỜNG CƠ SỞ:
MỤC TIÊU SAU CẢI TIẾN:

CÔNG SỨC:
- Điều tra:
- Thiết kế:
- Thực hiện:
- Kiểm thử / review:
- Triển khai:
- Tài liệu / đào tạo:
- Bảo trì:

ĐỘ TIN CẬY:
RỦI RO NẾU TRÌ HOÃN:
PHỤ THUỘC:
ĐIỀU KIỆN SẴN SÀNG:
CHỦ SỞ HỮU:
NGƯỜI DỰ PHÒNG:
~~~

## 25. Mẫu bảng ưu tiên tác động và công sức

~~~text
ID | TÊN | TÁC ĐỘNG | CÔNG SỨC | TIN CẬY | RỦI RO TRÌ HOÃN
   | PHỤ THUỘC | CHỦ SỞ HỮU | QUYẾT ĐỊNH | LÝ DO

CÁCH CHẤM TÁC ĐỘNG:
1 =
2 =
3 =
4 =
5 =

CÁCH CHẤM CÔNG SỨC:
1 =
2 =
3 =
4 =
5 =

HẠNG MỤC BẮT BUỘC:
HẠNG MỤC ƯU TIÊN CAO:
HẠNG MỤC CẦN SPIKE:
HẠNG MỤC CHỜ PHỤ THUỘC:
HẠNG MỤC HOÃN / LOẠI BỎ:
NGÀY RÀ SOÁT TIẾP THEO:
~~~

## 26. Mẫu kế hoạch thử nghiệm cải tiến

~~~text
TÊN THỬ NGHIỆM:
VẤN ĐỀ CẦN GIẢI QUYẾT:
GIẢ THUYẾT:
PHẠM VI THỬ:
NGƯỜI HƯỞNG LỢI:

ĐƯỜNG CƠ SỞ:
- Chỉ số:
- Khoảng thời gian:
- Nguồn dữ liệu:
- Điều kiện đo:

KẾT QUẢ MỤC TIÊU:
CHỈ SỐ BẢO VỆ:
PHỤ THUỘC:
NGƯỜI SỞ HỮU:
THỜI HẠN:

CÁCH THỰC HIỆN:
ĐIỀU KIỆN DỪNG:
CÁCH HOÀN NGUYÊN:
KẾT QUẢ THỰC TẾ:
TÁC ĐỘNG PHỤ:
KẾT LUẬN:
- Mở rộng
- Điều chỉnh
- Hoàn nguyên
- Dừng

BƯỚC TIẾP THEO:
~~~

## 27. Mẫu rà soát danh mục cải tiến theo chu kỳ

~~~text
CHU KỲ:
MỤC TIÊU SẢN PHẨM:
NĂNG LỰC NHÓM:

1. KẾT QUẢ CẢI TIẾN ĐÃ THỰC HIỆN
- Hạng mục:
- Đường cơ sở:
- Kết quả:
- Tác động phụ:
- Quyết định:

2. RỦI RO / ĐIỂM NGHẼN MỚI
- Vấn đề:
- Bằng chứng:
- Tác động:
- Chủ sở hữu:

3. DANH MỤC ƯU TIÊN TIẾP THEO
- Hạng mục:
- Tác động:
- Công sức:
- Độ tin cậy:
- Phụ thuộc:
- Lý do ưu tiên:

4. NĂNG LỰC VÀ NGUỒN LỰC
- Người thực hiện:
- Kỹ năng cần:
- Năng lực dành cho cải tiến:
- Hỗ trợ cần thiết:

5. QUYẾT ĐỊNH
- Bắt đầu:
- Tiếp tục:
- Chờ:
- Hoãn:
- Loại bỏ:

NGƯỜI QUYẾT ĐỊNH:
NGÀY REVIEW TIẾP THEO:
~~~

## Kết luận

Ưu tiên cải tiến theo tác động và công sức giúp nhóm tập trung nguồn lực vào những thay đổi tạo giá trị lớn nhất trong bối cảnh hiện tại. Để quyết định đáng tin cậy, cần mô tả đúng vấn đề, dùng bằng chứng để ước lượng tác động, tính đủ công sức vòng đời, ghi nhận độ bất định, xem xét rủi ro nếu trì hoãn và phụ thuộc liên nhóm.

Ma trận tác động/công sức, RICE, WSJF hoặc thang điểm có trọng số có thể hỗ trợ so sánh, nhưng không thay thế phán đoán và quyền quyết định. Nhóm cần bảo vệ công việc bắt buộc, cân bằng quick win với đầu tư nền tảng, chia nhỏ hạng mục lớn và đo kết quả trước/sau. Khi danh mục được rà soát định kỳ, có người sở hữu và điều chỉnh theo bằng chứng mới, hoạt động cải tiến trở thành một phần liên tục của chiến lược kiểm thử thay vì một danh sách ý tưởng không được thực hiện.
