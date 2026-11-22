# Error budgets và quyết định tốc độ phát hành

Một dịch vụ cần đủ tin cậy để người dùng hoàn thành công việc, nhưng việc theo đuổi độ sẵn sàng tuyệt đối thường làm chi phí và tốc độ phát triển tăng cao. Site Reliability Engineering (SRE) giải quyết sự cân bằng này bằng cách đặt mục tiêu độ tin cậy có thể đo lường, sau đó dùng error budget để quyết định mức độ rủi ro mà nhóm có thể chấp nhận khi phát hành thay đổi.

Error budget là phần lỗi được phép xảy ra trong một cửa sổ đo SLO. Khi ngân sách còn nhiều, nhóm có thể tiếp tục phát hành với tốc độ bình thường và thử nghiệm cải tiến. Khi ngân sách tiêu thụ nhanh hoặc đã cạn, nhóm cần giảm rủi ro phát hành và ưu tiên khôi phục độ tin cậy. Cách làm này biến SLO thành cơ chế ra quyết định vận hành, thay vì chỉ là một con số trên dashboard.

## 1. SLI, SLO và SLA liên hệ với nhau thế nào?

Trước khi tính error budget, cần thống nhất ba khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| SLI (Service Level Indicator) | Chỉ số đo trải nghiệm hoặc kết quả mà người dùng nhận được | Tỷ lệ yêu cầu thành công, tỷ lệ yêu cầu hoàn thành trong 300 ms |
| SLO (Service Level Objective) | Mục tiêu cần đạt cho một SLI trong một cửa sổ thời gian | 99,9% yêu cầu hợp lệ thành công trong 30 ngày |
| SLA (Service Level Agreement) | Cam kết dịch vụ với khách hàng, thường kèm điều khoản hoặc biện pháp khắc phục khi không đạt | Cam kết khả dụng trong hợp đồng với điều kiện và ngoại lệ cụ thể |

SLI phải phản ánh điều người dùng thực sự quan tâm. Ví dụ, một API có thể trả HTTP 200 nhưng dữ liệu sai hoặc quá chậm; chỉ đo tỷ lệ HTTP 200 có thể đánh giá quá lạc quan. Với API giao dịch, nhóm có thể đo tỷ lệ yêu cầu trả kết quả đúng và trong giới hạn latency đã chọn. Với pipeline dữ liệu, SLI có thể là tỷ lệ dữ liệu đến đúng hạn hoặc độ trễ từ lúc phát sinh đến lúc có thể truy vấn.

SLO là mục tiêu vận hành nội bộ của nhóm sở hữu dịch vụ. SLA có thể dựa trên SLO nhưng không nhất thiết giống hệt, vì SLA còn có phạm vi, ngoại lệ, cách đo và nghĩa vụ hợp đồng. Không nên dùng error budget nội bộ như thể đó là điều khoản SLA nếu chưa có quy định tương ứng.

Một dịch vụ thường có nhiều SLI/SLO: availability, latency, freshness hoặc correctness. Mỗi SLO cần định nghĩa rõ sự kiện đủ điều kiện, sự kiện tốt, cửa sổ đo và nguồn dữ liệu. Nếu chỉ có một SLO tổng hợp, nhóm có thể bỏ sót một dạng suy giảm mà người dùng vẫn cảm nhận rõ.

## 2. Error budget là gì?

Error budget là phần còn lại giữa mức hoàn hảo 100% và mục tiêu SLO. Với SLO dạng tỷ lệ sự kiện tốt:

\[
\text{Error budget ratio} = 1 - \text{SLO target}
\]

Nếu mục tiêu là 99,9% yêu cầu thành công, tỷ lệ yêu cầu lỗi được phép là 0,1%. Trong cửa sổ đo, số lượng sự kiện lỗi tối đa được phép phụ thuộc vào tổng số sự kiện đủ điều kiện.

Với SLO dựa trên thời gian:

\[
\text{Time budget} = \text{Window duration} \times (1-\text{SLO})
\]

Ví dụ, một dịch vụ đặt SLO availability 99,9% trong 30 ngày:

- Cửa sổ 30 ngày có 43.200 phút.
- Error budget ratio là 0,1%.
- Ngân sách gián đoạn tương đương 43,2 phút trong cửa sổ đó.

Với SLO dựa trên yêu cầu, giả sử API nhận 1.000.000 yêu cầu hợp lệ trong cửa sổ và mục tiêu thành công là 99,9%. Ngân sách là 1.000 yêu cầu lỗi. Nếu có 250 yêu cầu lỗi, nhóm đã tiêu thụ 25% ngân sách; nếu có 1.500 yêu cầu lỗi, ngân sách đã vượt 150%.

Hai cách đo này có ý nghĩa khác nhau. SLO thời gian phù hợp khi dịch vụ được xem là sẵn sàng hoặc không sẵn sàng theo từng khoảng thời gian. SLO theo yêu cầu phù hợp với API có lưu lượng thay đổi và cho phép đo chính xác tỷ lệ yêu cầu tốt. Với dịch vụ có nhiều vùng hoặc nhiều endpoint, hãy chọn cách đo phản ánh đúng tác động đến người dùng.

## 3. Chọn cửa sổ đo và định nghĩa sự kiện lỗi

Error budget luôn gắn với cửa sổ đo của SLO. Cửa sổ có thể là lịch cố định, chẳng hạn mỗi tháng, hoặc cửa sổ trượt, chẳng hạn 30 ngày gần nhất. Cửa sổ trượt cập nhật liên tục theo dữ liệu mới; lỗi cũ dần rời khỏi cửa sổ khi thời gian trôi qua. Cửa sổ lịch cố định có mốc bắt đầu và kết thúc rõ ràng, nhưng việc ngân sách được làm mới vào đầu kỳ có thể tạo động lực phát hành quá nhiều ngay sau thời điểm reset.

Với dịch vụ liên tục phục vụ người dùng, cửa sổ trượt 28 hoặc 30 ngày thường giúp nhóm quan sát mức độ tin cậy gần đây một cách liên tục. Dù chọn cách nào, cần công bố rõ ngày bắt đầu, thời lượng, múi giờ và cách xử lý dữ liệu đến trễ để mọi nhóm tính cùng một kết quả.

Định nghĩa lỗi phải nhất quán. Với SLO availability cho API, nhóm cần xác định:

- Yêu cầu nào được tính vào mẫu số, ví dụ yêu cầu hợp lệ đến endpoint phục vụ khách hàng.
- Kết quả nào được xem là tốt, ví dụ phản hồi thành công và hoàn thành trong giới hạn latency.
- Kết quả nào được xem là lỗi, ví dụ lỗi phía máy chủ, timeout hoặc phản hồi sai định dạng.
- Những yêu cầu nào được loại trừ, nếu có, và vì sao việc loại trừ phản ánh đúng trải nghiệm người dùng.

Không nên loại bỏ lỗi do dependency hoặc hạ tầng chỉ vì nhóm sở hữu dịch vụ không trực tiếp gây ra. Người dùng vẫn chịu ảnh hưởng khi dependency gặp sự cố. Chỉ loại trừ các sự kiện có lý do rõ ràng, được ghi trong định nghĩa SLI và áp dụng nhất quán; tránh thay đổi quy tắc sau một sự cố để làm đẹp kết quả.

## 4. Theo dõi mức tiêu thụ và burn rate

Tỷ lệ ngân sách đã dùng cho biết mức độ lỗi tích lũy. Burn rate cho biết tốc độ tiêu thụ ngân sách so với tốc độ có thể tiêu thụ đều trong toàn bộ cửa sổ SLO.

\[
\text{Burn rate} =
\frac{\text{Observed error ratio}}{\text{Allowed error ratio}}
\]

Với SLO 99,9%, tỷ lệ lỗi cho phép là 0,1%. Nếu trong một khoảng quan sát, 0,5% yêu cầu bị lỗi, burn rate là 5 lần. Nếu tốc độ này kéo dài, dịch vụ sẽ tiêu thụ ngân sách nhanh gấp năm lần tốc độ cho phép.

Có thể ước lượng tỷ lệ ngân sách đã tiêu thụ bằng:

\[
\text{Budget consumed} \approx
\text{Burn rate} \times
\frac{\text{Elapsed time}}{\text{SLO window}}
\]

Ví dụ, cửa sổ SLO là 30 ngày và dịch vụ duy trì burn rate 10 lần trong 24 giờ. Dịch vụ đã dùng xấp xỉ một phần ba error budget của cửa sổ. Đây là tín hiệu cần điều tra sớm, ngay cả khi dashboard availability tổng thể vẫn trông khá cao.

Burn rate hữu ích hơn một ngưỡng lỗi tuyệt đối khi lưu lượng thay đổi. Một tỷ lệ lỗi nhỏ trong dịch vụ có ngân sách rất chặt có thể tiêu thụ ngân sách nhanh; một đợt lỗi lớn nhưng rất ngắn cũng có thể cần cảnh báo ngay. Hãy theo dõi cả tỷ lệ ngân sách còn lại, burn rate và số lượng yêu cầu để hiểu mức ảnh hưởng thực tế.

## 5. Cảnh báo burn rate với nhiều cửa sổ thời gian

Một cảnh báo chỉ dùng cửa sổ dài có thể phản ứng chậm trước sự cố đang diễn ra. Cảnh báo chỉ dùng cửa sổ ngắn lại dễ bị kích hoạt bởi một đợt nhiễu rất ngắn. SRE thường kết hợp cửa sổ dài và ngắn: cửa sổ dài xác nhận mức tiêu thụ đáng kể, cửa sổ ngắn xác nhận vấn đề vẫn đang xảy ra.

Ví dụ tham khảo cho SLO 30 ngày:

| Mức độ | Burn rate minh họa | Cửa sổ dài / ngắn | Ý nghĩa |
| --- | ---: | --- | --- |
| Nghiêm trọng | 14,4x | 1 giờ / 5 phút | Có thể tiêu thụ khoảng 2% ngân sách chỉ trong 1 giờ |
| Cao | 6x | 6 giờ / 30 phút | Có thể tiêu thụ khoảng 5% ngân sách trong 6 giờ |
| Trung bình | 1x | 3 ngày / 6 giờ | Ngân sách đang bị tiêu thụ nhanh tương đương tốc độ cho phép |

Các ngưỡng này là điểm khởi đầu phổ biến, không phải cấu hình bắt buộc cho mọi dịch vụ. Nhóm cần điều chỉnh theo độ nhạy của người dùng, lưu lượng, độ trễ phát hiện, khả năng trực on-call và thời gian cần để khôi phục. Mỗi cảnh báo phải gắn với hành động rõ ràng; tránh gửi cảnh báo mà không có người chịu trách nhiệm xử lý.

Trong Google Cloud, Cloud Monitoring hỗ trợ theo dõi dịch vụ và SLO thông qua Service Monitoring. Nhóm có thể xác định SLI, tạo SLO, xem error budget và thiết lập cảnh báo dựa trên burn rate. Dashboard nên hiển thị mục tiêu SLO, ngân sách còn lại, tốc độ tiêu thụ, số yêu cầu tốt/xấu và các phiên bản đang triển khai. Cloud Logging và trace có thể hỗ trợ tìm nguyên nhân sau khi cảnh báo được kích hoạt.

## 6. Dùng error budget để quyết định tốc độ phát hành

Error budget tạo ra một chính sách phát hành có thể giải thích được. Khi ngân sách còn khỏe, nhóm có dư địa để triển khai tính năng và thay đổi. Khi ngân sách suy giảm, nhóm giảm tốc độ hoặc thu hẹp phạm vi phát hành để dành năng lực cho độ tin cậy.

Một chính sách tham khảo:

| Trạng thái ngân sách | Chính sách phát hành | Hành động vận hành |
| --- | --- | --- |
| Còn nhiều, burn rate ổn định | Phát hành theo nhịp bình thường | Duy trì kiểm thử tự động, canary và theo dõi sau phát hành |
| Đang tiêu thụ nhanh | Giảm kích thước đợt phát hành và thận trọng với thay đổi rủi ro cao | Điều tra nguyên nhân, tăng thời gian quan sát, chuẩn bị rollback |
| Còn rất ít, gần cạn | Tạm dừng mở rộng rollout của tính năng có rủi ro cao | Ưu tiên sửa lỗi, giảm tải, cải thiện capacity và loại bỏ nguyên nhân gây lỗi |
| Đã cạn hoặc SLO liên tục không đạt | Dừng phát hành tính năng thông thường theo chính sách đã thống nhất | Tập trung khôi phục SLO, rà soát sự cố và chỉ phát hành thay đổi phục hồi đã được đánh giá |

Tổ chức cần định nghĩa ngưỡng cụ thể, ví dụ cảnh báo khi ngân sách còn dưới 25% hoặc khi burn rate vượt một mức trong khoảng thời gian xác định. Con số 25% chỉ là ví dụ để xây dựng chính sách; mỗi dịch vụ phải chọn ngưỡng phù hợp với cửa sổ SLO và thời gian cần để khắc phục.

Khi ngân sách đã cạn, không có nghĩa mọi thay đổi đều bị cấm. Bản vá bảo mật khẩn cấp, biện pháp ngăn mất dữ liệu hoặc thay đổi cần thiết để khôi phục dịch vụ có thể giảm rủi ro tổng thể. Các ngoại lệ nên có người phê duyệt, đánh giá tác động, kế hoạch rollback và ghi nhận lý do. Chính sách cần phân biệt phát hành tính năng làm tăng rủi ro với thay đổi nhằm giảm rủi ro.

Ngược lại, khi ngân sách còn nhiều, nhóm vẫn phải tuân thủ kiểm thử và kiểm soát phát hành. Error budget không phải giấy phép triển khai tùy ý; nó là giới hạn rủi ro được chấp nhận ở cấp dịch vụ.

## 7. Kết hợp error budget với canary và rollback

SLO cho biết độ tin cậy của dịch vụ trong cửa sổ đo; canary giúp phát hiện sớm tác động của một phiên bản mới trước khi mở rộng đến toàn bộ người dùng. Khi triển khai, nhóm nên so sánh SLI của nhóm canary với baseline hoặc phiên bản ổn định, đồng thời quan sát SLO toàn dịch vụ.

Một luồng phát hành có thể gồm:

1. Kiểm tra ngân sách còn lại và burn rate trước khi bắt đầu.
2. Chạy kiểm thử tự động và triển khai phiên bản mới cho một tỷ lệ nhỏ lưu lượng.
3. Theo dõi tỷ lệ lỗi, latency, saturation và các SLI liên quan trong khoảng quan sát đủ dài.
4. Nếu canary làm burn rate tăng hoặc vượt ngưỡng lỗi đã định, dừng rollout và rollback.
5. Chỉ mở rộng tỷ lệ lưu lượng khi các chỉ số ổn định và không có dấu hiệu suy giảm trải nghiệm.
6. Sau phát hành, tiếp tục theo dõi để phát hiện lỗi xuất hiện muộn hoặc chỉ xảy ra dưới tải thực tế.

Cloud Deploy có thể hỗ trợ pipeline triển khai theo từng target và chiến lược canary cho các nền tảng được hỗ trợ. Cloud Monitoring cung cấp SLI, dashboard và alert để đánh giá tác động. Nhóm có thể tích hợp bước xác minh hoặc điều kiện phát hành vào pipeline, nhưng cần bảo đảm tín hiệu dùng làm gate phản ánh đúng SLO và không chỉ dựa vào một phép kiểm tra tổng quát.

Không nên dùng riêng SLO toàn dịch vụ để quyết định rollback một revision nếu lưu lượng canary quá nhỏ hoặc bị trộn với lỗi từ các phiên bản khác. Khi có thể, hãy gắn nhãn revision, target hoặc phiên bản vào metric và log để phân biệt tác động của thay đổi mới. Đồng thời, tránh rollback tự động khi nguyên nhân là sự cố dependency bên ngoài mà rollback không thể khắc phục; cần kết hợp quy tắc tự động với đánh giá của người trực.

~~~mermaid
flowchart TD
  A["Kiểm tra SLO và error budget"] --> B{"Ngân sách còn khỏe?"}
  B -->|Có| C["Kiểm thử và triển khai canary"]
  B -->|Không| D["Giảm tốc độ, điều tra và ưu tiên độ tin cậy"]
  C --> E{"SLI và burn rate ổn định?"}
  E -->|Có| F["Mở rộng rollout từng bước"]
  E -->|Không| G["Dừng rollout và rollback"]
  F --> H["Theo dõi SLO sau phát hành"]
  G --> D
  D --> I["Khắc phục và đánh giá lại ngân sách"]
  I --> A
~~~

## 8. Ví dụ tính ngân sách và quyết định phát hành cho API

Một API đơn hàng chạy trên Cloud Run có SLO availability 99,9% theo yêu cầu trong cửa sổ trượt 30 ngày. SLI tính các yêu cầu hợp lệ đến endpoint tạo đơn; yêu cầu được xem là tốt khi hoàn tất thành công trong giới hạn latency đã định.

Trong cửa sổ hiện tại:

- Có 2.000.000 yêu cầu đủ điều kiện.
- Ngân sách lỗi cho phép là 0,1% × 2.000.000 = 2.000 yêu cầu.
- Hệ thống đã ghi nhận 1.200 yêu cầu lỗi.
- Tỷ lệ ngân sách đã dùng là 1.200 / 2.000 = 60%.
- Ngân sách còn lại là 800 yêu cầu lỗi, tương đương 40%.

Nhóm chuẩn bị phát hành một thay đổi lớn trong luồng thanh toán. Dù ngân sách còn dương, nhóm nhận thấy burn rate đang tăng do một dependency chậm. Chính sách phù hợp là trì hoãn mở rộng rollout, điều tra dependency và chỉ tiếp tục khi SLI ổn định. Nếu thay đổi mới là bản vá xử lý chính dependency đang gây lỗi, nhóm có thể triển khai canary nhỏ với giám sát chặt và kế hoạch rollback rõ ràng.

Nếu ngân sách đã vượt 100%, nhóm tạm dừng phát hành tính năng thông thường, tập trung giảm lỗi và khôi phục SLO. Sau khi nguyên nhân được xử lý, nhóm xem xét lại dữ liệu trong cửa sổ đo. Với cửa sổ trượt, ngân sách có thể phục hồi khi các sự kiện lỗi cũ rời khỏi cửa sổ; không nên giả định rằng việc sang tháng mới sẽ xóa tác động của sự cố nếu SLO dùng cửa sổ trượt.

Ví dụ này cho thấy quyết định phát hành không phụ thuộc riêng vào tỷ lệ ngân sách còn lại. Nhóm cần xét cả xu hướng burn rate, nguyên nhân lỗi, mức độ ảnh hưởng, rủi ro của thay đổi và khả năng rollback.

## 9. Quản trị chính sách error budget giữa các nhóm

Error budget chỉ có tác dụng khi nhóm phát triển, vận hành, bảo mật và chủ sở hữu sản phẩm cùng chấp nhận cách đo và cách ra quyết định. Trước khi áp dụng, tổ chức cần thống nhất:

- Ai sở hữu SLI và SLO, ai phê duyệt thay đổi mục tiêu.
- Dữ liệu nào được dùng để tính SLI và ai chịu trách nhiệm chất lượng dữ liệu.
- Cửa sổ đo, cách xử lý sự kiện loại trừ và cách xử lý dữ liệu đến trễ.
- Ngưỡng cảnh báo, người nhận cảnh báo và thời gian phản hồi.
- Ngưỡng ngân sách làm chậm hoặc tạm dừng phát hành.
- Quy trình ngoại lệ cho bản vá bảo mật, khôi phục dịch vụ hoặc ngăn mất dữ liệu.
- Cách ghi nhận sự cố, hành động khắc phục và quyết định tiếp tục phát hành.

Không nên đặt SLO quá cao chỉ để tạo cảm giác an toàn. SLO 100% làm error budget bằng 0, khiến mọi lỗi đều vượt mục tiêu và loại bỏ công cụ cân bằng rủi ro. Mục tiêu cần dựa trên trải nghiệm người dùng, yêu cầu sản phẩm, khả năng kỹ thuật và chi phí để đạt được mức độ tin cậy đó.

Khi một dịch vụ phụ thuộc vào nhiều dịch vụ khác, nhóm cần xác định SLO ở ranh giới mà người dùng cảm nhận. Không nên nhân hoặc cộng cơ học các SLO thành phần nếu không xét cách request đi qua các dependency, mức độ dự phòng và tương quan lỗi. Error budget của từng dịch vụ thành phần vẫn hữu ích cho đội sở hữu, còn SLO hành trình người dùng cho biết trải nghiệm tổng thể.

## 10. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chọn SLI chỉ dựa trên metric dễ thu thập | Dashboard đẹp nhưng không phản ánh trải nghiệm người dùng | Chọn sự kiện tốt/xấu theo hành trình và kỳ vọng của người dùng |
| Không định nghĩa rõ mẫu số và ngoại lệ | Các nhóm tính SLO khác nhau hoặc loại lỗi tùy tiện | Công bố định nghĩa SLI và quản lý thay đổi có phê duyệt |
| Chỉ xem availability trung bình | Bỏ lỡ lỗi tập trung vào một endpoint, vùng hoặc nhóm người dùng | Theo dõi SLI theo phân đoạn quan trọng và SLO hành trình |
| Dùng một cửa sổ cảnh báo duy nhất | Cảnh báo chậm hoặc quá nhạy với nhiễu | Kết hợp cửa sổ dài và ngắn, hiệu chỉnh theo mức độ nghiêm trọng |
| Dừng mọi phát hành khi ngân sách cạn | Ngăn cả bản vá giảm rủi ro hoặc khôi phục dịch vụ | Có quy trình ngoại lệ với phê duyệt và rollback |
| Tiếp tục phát hành dù burn rate tăng mạnh | Thay đổi mới có thể làm sự cố nghiêm trọng hơn | Giảm rollout, điều tra và ưu tiên khắc phục độ tin cậy |
| Làm mới ngân sách theo tháng dù đang dùng cửa sổ trượt | Đánh giá sai ngân sách thực tế | Tính đúng theo cửa sổ SLO đã công bố |

## 11. Checklist áp dụng cho một dịch vụ Google Cloud

Trước khi dùng error budget làm điều kiện phát hành, hãy xác nhận:

- SLI phản ánh trải nghiệm quan trọng của người dùng và có nguồn dữ liệu tin cậy.
- SLO có mục tiêu, cửa sổ đo, mẫu số, sự kiện lỗi và ngoại lệ được tài liệu hóa.
- Error budget được tính tự động và có dashboard thể hiện ngân sách đã dùng, còn lại và burn rate.
- Cảnh báo burn rate dùng nhiều cửa sổ thời gian và có người chịu trách nhiệm xử lý.
- Cloud Monitoring Service Monitoring hoặc hệ thống tương đương cung cấp SLO và cảnh báo có thể hành động.
- Pipeline Cloud Build hoặc Cloud Deploy có thể triển khai từng bước, quan sát canary và dừng hoặc rollback khi tín hiệu vượt ngưỡng.
- Chính sách phát hành quy định rõ khi nào phát hành bình thường, giảm tốc độ, tạm dừng và áp dụng ngoại lệ.
- Nhóm có lịch rà soát SLO, error budget, sự cố và hiệu quả của chính sách phát hành.

Error budget giúp nhóm phát hành nhanh khi độ tin cậy đang được kiểm soát và chuyển ưu tiên sang ổn định hệ thống khi rủi ro tăng. Khi SLI phản ánh đúng trải nghiệm, SLO có cửa sổ đo rõ ràng và chính sách phát hành được các nhóm thống nhất, tốc độ phát hành trở thành quyết định dựa trên dữ liệu thay vì tranh luận cảm tính giữa phát triển và vận hành.
