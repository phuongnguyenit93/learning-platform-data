# Ghi lại lý do lựa chọn và điều kiện cần xem xét lại

## 1. Vì sao cần ghi lại lý do lựa chọn cách tiếp cận?

Chiến lược kiểm thử có thể sử dụng nhiều cách tiếp cận: kiểm thử dựa trên rủi ro, kiểm thử theo yêu cầu, kiểm thử khám phá, tự động hóa ở các tầng khác nhau, xác nhận sớm trong quá trình phát triển, kiểm thử độc lập trước phát hành hoặc giám sát sau triển khai. Không có một cách tiếp cận duy nhất phù hợp với mọi sản phẩm, nhóm phát triển và mức rủi ro.

Một quyết định có thể hợp lý trong bối cảnh hiện tại nhưng trở nên không phù hợp khi kiến trúc, yêu cầu, tải, nhóm người dùng hoặc năng lực vận hành thay đổi. Nếu chỉ lưu kết luận như “dùng kiểm thử tự động” hoặc “ưu tiên kiểm thử dựa trên rủi ro”, người thực hiện sau này sẽ không biết quyết định đó nhằm giải quyết vấn đề nào, dựa trên giả định gì và điều kiện nào khiến cần xem xét lại.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, cần ghi lại cả lựa chọn lẫn lý do, bằng chứng và giới hạn của lựa chọn đó. Hồ sơ quyết định giúp:

- Giải thích vì sao cách tiếp cận hiện tại phù hợp với mục tiêu chất lượng và rủi ro.
- Làm rõ các phương án đã cân nhắc và đánh đổi được chấp nhận.
- Giữ tính nhất quán giữa các nhóm, phiên bản và giai đoạn vòng đời.
- Tránh lặp lại thảo luận hoặc đưa ra quyết định trái ngược mà không hiểu bối cảnh trước đó.
- Xác định tín hiệu và sự kiện buộc nhóm đánh giá lại cách tiếp cận.
- Hỗ trợ kiểm toán, bàn giao, lập kế hoạch nguồn lực và cải tiến liên tục.

Ghi lại lý do không nhằm tạo thêm thủ tục cho mọi lựa chọn nhỏ. Hãy tập trung vào các quyết định ảnh hưởng đáng kể đến phạm vi, độ sâu, thứ tự, mức tự động hóa, môi trường, dữ liệu, nguồn lực hoặc tiêu chí chấp nhận của hoạt động kiểm thử.

## 2. Phân biệt quyết định, lý do và bằng chứng

Một hồ sơ tốt cần phân biệt rõ ba phần:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Quyết định | Nhóm sẽ thực hiện điều gì? | Ưu tiên kiểm thử hợp đồng API và tích hợp cho các dịch vụ thanh toán |
| Lý do | Vì sao lựa chọn này phù hợp với bối cảnh? | Nhiều nhóm phát triển dịch vụ độc lập; thay đổi giao diện có thể gây lỗi dây chuyền và ảnh hưởng giao dịch |
| Bằng chứng | Dữ liệu nào hỗ trợ nhận định? | Sơ đồ phụ thuộc, lịch sử lỗi tích hợp, tần suất thay đổi API và kết quả kiểm thử trước đây |

Không nên dùng một câu như “đây là thông lệ tốt” làm lý do duy nhất. Thông lệ hoặc kinh nghiệm có thể cung cấp định hướng, nhưng cần giải thích cách chúng liên quan đến sản phẩm cụ thể.

Ví dụ, quyết định “không tự động hóa toàn bộ kiểm thử giao diện đầu cuối” có thể dựa trên các bằng chứng: giao diện đang thay đổi thường xuyên, nhiều ca kiểm thử bị chập chờn do phụ thuộc môi trường, thời gian chạy dài và phần lớn quy tắc nghiệp vụ đã được kiểm tra ổn định ở tầng API. Lựa chọn này có thể ưu tiên kiểm thử đơn vị, thành phần, API và một tập nhỏ hành trình đầu cuối quan trọng. Hồ sơ cũng cần ghi rõ rủi ro còn lại và điều kiện khiến nhóm mở rộng tự động hóa giao diện.

## 3. Những yếu tố cần cân nhắc trước khi chọn cách tiếp cận

Quyết định kiểm thử nên bắt đầu từ mục tiêu chất lượng và rủi ro, sau đó xét đến điều kiện thực hiện. Các yếu tố dưới đây giúp tránh chọn phương pháp chỉ vì nhóm quen dùng hoặc công cụ đang có sẵn.

| Yếu tố | Câu hỏi cần xem xét | Ảnh hưởng đến lựa chọn |
|---|---|---|
| Mục tiêu kinh doanh và người dùng | Hành trình nào quan trọng? Hậu quả nếu thất bại là gì? | Xác định mức ưu tiên và độ sâu kiểm thử cho luồng quan trọng |
| Rủi ro sản phẩm | Lỗi có thể gây mất dữ liệu, thiệt hại tài chính, gián đoạn hoặc vi phạm nghĩa vụ không? | Chọn kiểm thử phòng ngừa, phát hiện và phục hồi tương ứng; xác định điều kiện bắt buộc |
| Vòng đời sản phẩm | Sản phẩm đang khám phá, ra mắt, tăng trưởng, duy trì hay kết thúc? | Điều chỉnh tỷ trọng kiểm thử khám phá, hồi quy, tương thích và vận hành |
| Mức độ trưởng thành | Yêu cầu, kiến trúc, quy trình phát hành và giám sát ổn định đến đâu? | Quyết định mức tự động hóa, chuẩn hóa và khả năng dựa vào pipeline |
| Tốc độ và phạm vi thay đổi | Thay đổi thường xuyên và ảnh hưởng bao nhiêu thành phần? | Điều chỉnh kiểm thử theo ảnh hưởng, kiểm thử hợp đồng và tần suất chạy |
| Kiến trúc và phụ thuộc | Hệ thống phân tán, tích hợp ngoài hoặc có trạng thái phức tạp không? | Xác định ranh giới kiểm thử, mô phỏng phụ thuộc và kiểm thử đầu cuối cần thiết |
| Dữ liệu và môi trường | Có dữ liệu đại diện, môi trường gần sản xuất và quyền truy cập phù hợp không? | Giới hạn hoặc bổ sung cách kiểm thử khi điều kiện chưa đáp ứng |
| Năng lực nhóm | Nhóm có kỹ năng, thời gian và người chịu trách nhiệm duy trì không? | Chọn phương pháp có thể thực hiện và duy trì đáng tin cậy |
| Công cụ và hạ tầng | Công cụ có hỗ trợ loại kiểm thử, tích hợp pipeline và thu thập bằng chứng không? | Đánh giá chi phí, độ tin cậy và khả năng mở rộng |
| Ràng buộc bên ngoài | Có yêu cầu pháp lý, hợp đồng, tiêu chuẩn hoặc kiểm toán không? | Bổ sung bằng chứng, phê duyệt và kiểm tra bắt buộc |

Các yếu tố này có thể mâu thuẫn. Ví dụ, rủi ro cao yêu cầu kiểm thử sâu, trong khi môi trường dữ liệu thật không thể được dùng vì lý do riêng tư. Nhóm cần tìm cách tạo dữ liệu tổng hợp phù hợp, che dữ liệu hoặc dùng môi trường được kiểm soát; đồng thời ghi rõ giới hạn bằng chứng nếu chưa thể mô phỏng đầy đủ.

### 3.1. Phân biệt điều kiện bắt buộc và tiêu chí ưu tiên

Trước khi so sánh phương án, hãy tách:

- **Điều kiện bắt buộc:** phải đáp ứng, ví dụ yêu cầu tuân thủ, bảo vệ dữ liệu, kiểm tra quyền truy cập hoặc mức chất lượng tối thiểu đã cam kết.
- **Tiêu chí ưu tiên:** giúp lựa chọn giữa các phương án có thể chấp nhận, ví dụ thời gian phản hồi, chi phí vận hành, khả năng tái sử dụng, mức độ bao phủ và độ dễ bảo trì.

Một phương án có chi phí thấp hoặc triển khai nhanh vẫn không phù hợp nếu vi phạm điều kiện bắt buộc. Có thể dùng bảng so sánh hoặc ma trận trọng số để thảo luận tiêu chí ưu tiên, nhưng không dùng điểm tổng để bù trừ cho yêu cầu bắt buộc chưa đạt.

## 4. Cách lựa chọn và ghi nhận quyết định

### Bước 1: Nêu vấn đề cần quyết định

Viết ngắn gọn vấn đề mà nhóm phải giải quyết. Nêu phạm vi ảnh hưởng: sản phẩm, dịch vụ, hành trình, phiên bản, giai đoạn phát triển hoặc đợt phát hành. Câu hỏi cần đủ cụ thể để người đọc hiểu tại sao cần đưa ra quyết định.

Ví dụ: “Cần xác định cách xác nhận thay đổi API giữa ba dịch vụ thanh toán được triển khai độc lập, nhằm giảm lỗi không tương thích trước khi triển khai từng dịch vụ.”

### Bước 2: Xác định mục tiêu và ràng buộc

Liên kết vấn đề với mục tiêu chất lượng, rủi ro và tiêu chí chấp nhận. Ghi các ràng buộc về thời gian, ngân sách, dữ liệu, môi trường, công cụ, năng lực nhóm, bảo mật và hợp đồng. Phân biệt điều đã được xác nhận với giả định chưa có bằng chứng.

### Bước 3: Thu thập bằng chứng và giả định

Xem xét dữ liệu kiểm thử, lỗi sản xuất, thay đổi yêu cầu, kiến trúc, thời gian pipeline, mức độ ổn định của môi trường, phản hồi người dùng và kết quả các đợt trước. Nếu chưa có dữ liệu, ghi rõ giả định và mức độ không chắc chắn; có thể thực hiện thử nghiệm nhỏ để so sánh phương án trước khi quyết định lâu dài.

### Bước 4: Liệt kê các phương án thực tế

Nêu các lựa chọn có thể thực hiện, kể cả phương án giữ nguyên cách làm hiện tại hoặc không triển khai thay đổi. Không cần liệt kê phương án không khả thi chỉ để làm hồ sơ dài hơn. Với mỗi phương án, mô tả phạm vi, điều kiện cần, lợi ích, hạn chế và chi phí duy trì.

### Bước 5: So sánh và giải thích đánh đổi

Đối chiếu phương án theo điều kiện bắt buộc và tiêu chí ưu tiên. Nêu phương án nào đáp ứng tốt mục tiêu, phương án nào có rủi ro hoặc chi phí không phù hợp và vì sao. Nếu có đánh đổi, nói rõ nhóm đang chấp nhận điều gì và biện pháp kiểm soát rủi ro tương ứng.

### Bước 6: Ghi quyết định và phạm vi áp dụng

Nêu lựa chọn đã thống nhất, ngày quyết định, người tham gia và người phê duyệt. Xác định phạm vi, phiên bản, nhóm hoặc điều kiện áp dụng. Ghi rõ điều gì nằm ngoài quyết định để tránh mở rộng kết luận quá mức.

### Bước 7: Xác định cách đánh giá hiệu quả

Chọn chỉ số hoặc bằng chứng cho biết lựa chọn có đạt mục tiêu không. Ví dụ: tỷ lệ lỗi giao diện được phát hiện trước triển khai, thời gian phản hồi của pipeline, tỷ lệ kiểm thử chập chờn, số lỗi lọt ra sản xuất hoặc chi phí duy trì. Ghi mức nền, mục tiêu, cửa sổ đo và chủ sở hữu.

### Bước 8: Đặt điều kiện và thời điểm xem xét lại

Xác định sự kiện hoặc ngưỡng khiến quyết định cần được đánh giá lại. Có thể gồm thay đổi kiến trúc, tăng tải, thay đổi nhóm người dùng, vi phạm SLO, lỗi nghiêm trọng, thay đổi pháp lý, công cụ hết hỗ trợ hoặc chi phí duy trì vượt ngưỡng. Ghi người chịu trách nhiệm theo dõi và thời điểm rà soát định kỳ nếu cần.

## 5. Cấu trúc một bản ghi quyết định

Một bản ghi quyết định cách tiếp cận kiểm thử (test approach decision record) có thể ngắn hoặc dài tùy mức ảnh hưởng. Cấu trúc sau phù hợp cho quyết định quan trọng:

| Trường | Nội dung cần ghi |
|---|---|
| ID và tiêu đề | Mã duy nhất và tên quyết định dễ tìm |
| Trạng thái | Đề xuất, đã chấp thuận, bị thay thế hoặc bị từ chối |
| Ngày và phiên bản | Ngày quyết định, phiên bản sản phẩm hoặc đợt áp dụng |
| Người tham gia/phê duyệt | Vai trò đưa ra ý kiến và người có thẩm quyền quyết định |
| Bối cảnh/vấn đề | Tình huống, nhu cầu và lý do cần quyết định |
| Mục tiêu chất lượng/rủi ro | Mục tiêu được hỗ trợ và rủi ro cần kiểm soát |
| Ràng buộc và giả định | Điều kiện bắt buộc, giới hạn và giả định chưa được xác nhận |
| Phương án đã cân nhắc | Các lựa chọn thực tế cùng lợi ích, hạn chế và chi phí |
| Quyết định | Cách tiếp cận được chọn và phạm vi áp dụng |
| Lý do lựa chọn | Bằng chứng và tiêu chí giải thích vì sao phương án phù hợp |
| Đánh đổi/rủi ro còn lại | Điều nhóm chấp nhận, phần chưa được bao phủ và biện pháp kiểm soát |
| Kế hoạch thực hiện | Công việc, chủ sở hữu, nguồn lực và mốc thời gian |
| Cách đo hiệu quả | Chỉ số, mức nền, mục tiêu và nguồn bằng chứng |
| Điều kiện xem xét lại | Trigger, ngưỡng, thời điểm và người chịu trách nhiệm |
| Liên kết | Yêu cầu, hồ sơ rủi ro, báo cáo kiểm thử, kiến trúc hoặc quyết định liên quan |

Không cần sao chép toàn bộ tài liệu khác vào bản ghi. Dùng liên kết ổn định đến yêu cầu, hồ sơ rủi ro, kết quả kiểm thử hoặc tài liệu kiến trúc để giữ thông tin nhất quán. Nếu tài liệu liên kết thay đổi, cần ghi lại phiên bản hoặc thời điểm của bằng chứng đã dùng khi quyết định.

### 5.1. Ví dụ bản ghi ngắn

```yaml
id: TAD-API-003
title: "Dùng kiểm thử hợp đồng cho giao diện giữa các dịch vụ thanh toán"
status: accepted
scope: "API giữa order-service, payment-service và notification-service"
context: "Các dịch vụ được phát hành độc lập; lỗi thay đổi schema từng gây lỗi tích hợp."
quality_goals:
  - "Phát hiện thay đổi không tương thích trước triển khai"
  - "Giữ thời gian phản hồi pipeline trong giới hạn nhóm thống nhất"
options_considered:
  - "Chỉ kiểm thử đầu cuối sau khi triển khai tích hợp"
  - "Kiểm thử hợp đồng trong pipeline của bên cung cấp và bên tiêu thụ"
  - "Kết hợp kiểm thử hợp đồng với một tập kiểm thử đầu cuối trọng yếu"
decision: "Kết hợp kiểm thử hợp đồng tự động và kiểm thử đầu cuối có chọn lọc"
rationale: "Phát hiện sai lệch giao diện sớm; giảm phụ thuộc vào môi trường tích hợp chung."
tradeoffs:
  - "Cần quản lý phiên bản hợp đồng và duy trì dữ liệu kiểm thử"
  - "Không thay thế hoàn toàn kiểm thử luồng nghiệp vụ xuyên dịch vụ"
success_measures:
  - "Tỷ lệ thay đổi không tương thích được phát hiện trước triển khai"
  - "Tỷ lệ lỗi tích hợp lọt ra môi trường thật"
revisit_when:
  - "Bổ sung dịch vụ hoặc thay đổi mô hình giao tiếp"
  - "Tỷ lệ lỗi lọt qua tăng trong hai chu kỳ rà soát liên tiếp"
owner: "Engineering and test leads"
review_date: "2027-03-31"
```

Đây là ví dụ minh họa cấu trúc, không phải cấu hình mặc định. Các ngưỡng và mốc thời gian thực tế phải được thống nhất theo nhịp phát hành và dữ liệu của sản phẩm.

## 6. Ghi lại các phương án đã cân nhắc

Việc ghi phương án bị từ chối có giá trị khi nó giải thích một đánh đổi quan trọng hoặc ngăn nhóm lặp lại thử nghiệm không phù hợp. Không cần ghi mọi ý tưởng thoáng qua. Tập trung vào các phương án khả thi đã được đánh giá.

| Cách ghi chưa đủ | Cách ghi hữu ích hơn |
|---|---|
| “Không chọn kiểm thử thủ công vì tốn thời gian.” | “Kiểm thử thủ công toàn bộ hồi quy không đáp ứng nhịp phát hành hàng tuần; nhóm giữ kiểm thử khám phá cho thay đổi mới và tự động hóa các luồng ổn định, có rủi ro cao.” |
| “Không dùng kiểm thử giao diện vì flaky.” | “Bộ kiểm thử giao diện hiện có tỷ lệ chập chờn cao do phụ thuộc dữ liệu và môi trường; nhóm ưu tiên xác nhận quy tắc ở API, sửa các điểm không ổn định và giữ một tập nhỏ luồng giao diện trọng yếu.” |
| “Không kiểm thử tải vì chưa cần.” | “Tính năng chưa mở cho người dùng và chưa tạo tải đáng kể; trước khi mở rộng, nhóm sẽ kiểm thử tải ở ngưỡng dự báo và đặt điều kiện giới hạn lưu lượng trong giai đoạn thử nghiệm.” |
| “Dùng công cụ X vì tốt hơn.” | “Công cụ X hỗ trợ tích hợp pipeline hiện tại, lưu được bằng chứng và đáp ứng kỹ năng nhóm; phương án Y cần hạ tầng riêng và tăng chi phí vận hành. Nhóm sẽ đánh giá lại khi số dịch vụ tăng.” |

Khi từ chối một phương án, nên ghi lý do gắn với tiêu chí đã thống nhất, không dùng nhận xét cảm tính về công cụ hoặc cá nhân. Nếu phương án có thể phù hợp trong tương lai, hãy ghi điều kiện khiến nhóm xem xét lại.

## 7. Điều kiện cần xem xét lại cách tiếp cận

Một quyết định cần có trigger rõ ràng. Trigger có thể là thay đổi trong bối cảnh, kết quả đo không đạt, sự kiện rủi ro hoặc giới hạn của phương pháp hiện tại.

| Nhóm trigger | Ví dụ sự kiện hoặc tín hiệu | Hướng xem xét lại |
|---|---|---|
| Thay đổi sản phẩm/nghiệp vụ | Thêm hành trình quan trọng, đổi quy tắc tính toán, mở nhóm người dùng mới | Đánh giá lại mục tiêu chất lượng, phạm vi và độ sâu kiểm thử |
| Thay đổi kiến trúc | Tách dịch vụ, chuyển cơ sở dữ liệu, đổi giao thức, bổ sung nhà cung cấp | Rà soát ranh giới kiểm thử, hợp đồng, tích hợp và phục hồi |
| Tăng tải hoặc quy mô | Người dùng, giao dịch, dữ liệu hoặc khu vực triển khai tăng đáng kể | Bổ sung kiểm thử tải, khả năng mở rộng và giám sát |
| Thay đổi rủi ro | Lỗi nghiêm trọng, sự cố bảo mật, lỗi dữ liệu hoặc vi phạm SLO | Đánh giá lại kiểm soát, kiểm thử âm tính, hồi quy và điều kiện phát hành |
| Hiệu quả kiểm thử giảm | Lỗi lọt ra tăng, kiểm thử chập chờn, pipeline chậm hoặc bỏ qua cổng kiểm tra | Sửa tín hiệu kiểm thử, điều chỉnh tầng kiểm thử và đầu tư hạ tầng |
| Thay đổi môi trường | Chuyển cloud, thay hệ điều hành, trình duyệt, thiết bị hoặc cấu hình | Cập nhật ma trận tương thích và môi trường đại diện |
| Thay đổi công cụ/phụ thuộc | Công cụ hết hỗ trợ, giấy phép thay đổi, thư viện có lỗ hổng | Đánh giá công cụ thay thế, phạm vi tái xác nhận và kế hoạch chuyển đổi |
| Thay đổi tổ chức | Nhóm sở hữu dịch vụ thay đổi, năng lực hoặc trách nhiệm vận hành thay đổi | Xác định lại trách nhiệm, kỹ năng, quy trình và khả năng duy trì |
| Thay đổi nghĩa vụ | Quy định, hợp đồng, chính sách bảo mật hoặc yêu cầu kiểm toán mới | Bổ sung kiểm soát và bằng chứng bắt buộc |
| Đến kỳ rà soát | Đến mốc xem xét đã ghi trong quyết định | Xác nhận các giả định còn đúng và chỉ số vẫn phản ánh mục tiêu |

Không phải mọi thay đổi đều bắt buộc thay cách tiếp cận. Trigger yêu cầu nhóm đánh giá lại, sau đó ghi kết luận “giữ nguyên”, “điều chỉnh”, “thử nghiệm phương án khác” hoặc “thay thế quyết định”. Nếu giữ nguyên, ghi bằng chứng cho thấy lựa chọn vẫn phù hợp.

### 7.1. Đặt trigger đo được

Trigger càng cụ thể càng dễ hành động. Thay vì ghi “xem xét khi hiệu năng xấu”, có thể ghi “xem xét khi p95 vượt mục tiêu trong ba cửa sổ đo liên tiếp hoặc khi error budget bị tiêu thụ nhanh hơn ngưỡng vận hành”. Thay vì “xem xét khi hệ thống thay đổi lớn”, có thể ghi “xem xét khi một dịch vụ mới tham gia luồng thanh toán hoặc schema dùng chung có thay đổi phá vỡ tương thích”.

Không nên đặt ngưỡng thiếu dữ liệu hoặc quá nhạy khiến nhóm phải đánh giá lại liên tục. Có thể bắt đầu bằng ngưỡng tạm thời, ghi rõ giả định, thu thập dữ liệu rồi hiệu chỉnh theo quy trình quản lý quyết định.

## 8. Theo dõi hiệu quả của quyết định

Sau khi áp dụng, cần kiểm tra lựa chọn có tạo ra kết quả dự kiến không. Chỉ số nên phản ánh mục tiêu của quyết định, không chỉ phản ánh số lượng hoạt động đã thực hiện.

| Mục tiêu của cách tiếp cận | Chỉ số/bằng chứng có thể dùng | Cách diễn giải |
|---|---|---|
| Phát hiện lỗi sớm | Tỷ lệ lỗi được tìm thấy trước khi triển khai, giai đoạn phát hiện lỗi | Đọc cùng mức độ nghiêm trọng và tổng số thay đổi; phát hiện nhiều lỗi nhỏ không nhất thiết tốt hơn |
| Tăng độ tin cậy phát hành | Tỷ lệ thay đổi gây lỗi, lỗi lọt ra, thời gian khôi phục | Xem xét xu hướng cùng quy mô và tần suất phát hành |
| Rút ngắn phản hồi | Thời gian pipeline, thời gian từ thay đổi đến kết quả kiểm thử | Đánh giá cả độ ổn định và chất lượng tín hiệu, tránh tối ưu tốc độ bằng cách bỏ kiểm tra cần thiết |
| Tăng độ bao phủ rủi ro | Tỷ lệ rủi ro cao có kiểm thử và bằng chứng cập nhật | Xác định các rủi ro chưa được xác nhận, không chỉ đếm số ca kiểm thử |
| Giảm chi phí duy trì | Thời gian bảo trì bộ kiểm thử, tỷ lệ chập chờn, công sức xử lý lỗi môi trường | Đọc cùng giá trị lỗi được phát hiện và mức độ tin cậy của bộ kiểm thử |
| Cải thiện trải nghiệm người dùng | Tỷ lệ hoàn thành hành trình, lỗi người dùng gặp, phản hồi hỗ trợ | Kết hợp dữ liệu định lượng với quan sát và phản hồi trực tiếp |

Định nghĩa chỉ số, nguồn dữ liệu, cửa sổ đo và mức nền trước khi triển khai nếu có thể. Nếu không có mức nền, ghi rõ thời điểm bắt đầu đo và tránh tuyên bố cải thiện chỉ từ một kết quả đơn lẻ.

### 8.1. Đánh giá sau áp dụng

Sau một hoặc vài chu kỳ phù hợp, tổ chức một buổi xem xét ngắn:

1. Mục tiêu ban đầu có còn đúng không?
2. Kết quả đo có đạt kỳ vọng không?
3. Có rủi ro mới hoặc rủi ro cũ tăng lên không?
4. Chi phí và công sức duy trì có đúng với dự tính không?
5. Giả định nào đã được xác nhận hoặc bị bác bỏ?
6. Cần giữ, điều chỉnh hay thay thế quyết định?

Ghi lại kết quả và liên kết với quyết định ban đầu. Nếu quyết định mới thay thế quyết định cũ, giữ lịch sử để người đọc biết lựa chọn trước đó đã được áp dụng trong khoảng thời gian nào và vì sao thay đổi.

## 9. Quản lý vòng đời của bản ghi quyết định

Hồ sơ quyết định cần dễ tìm, có phiên bản và phản ánh đúng trạng thái. Một quy trình đơn giản có thể gồm:

- **Đề xuất:** vấn đề và các phương án đang được đánh giá; chưa được xem là quyết định có hiệu lực.
- **Đã chấp thuận:** lựa chọn, phạm vi, người phê duyệt và điều kiện xem xét lại đã rõ.
- **Đang rà soát:** trigger đã xuất hiện hoặc đến kỳ đánh giá; nhóm đang kiểm tra mức phù hợp.
- **Được điều chỉnh:** lựa chọn hoặc điều kiện áp dụng đã thay đổi; ghi lại lý do và ngày hiệu lực.
- **Bị thay thế:** có quyết định mới thay thế; liên kết đến bản ghi mới và giữ lịch sử.
- **Bị từ chối/đóng:** phương án không được áp dụng hoặc vấn đề quyết định không còn tồn tại; ghi lý do đóng.

Nên lưu bản ghi gần với tài liệu chiến lược kiểm thử, kiến trúc hoặc hệ thống quản lý quyết định của tổ chức. Dùng mã định danh ổn định và liên kết hai chiều với mục tiêu chất lượng, hồ sơ rủi ro, kế hoạch kiểm thử, kết quả xác nhận và quyết định phát hành.

Khi thay đổi quyết định, không sửa mất lý do lịch sử. Hãy ghi ngày thay đổi, bằng chứng mới, tác động của thay đổi và quyết định thay thế. Điều này giúp phân biệt thay đổi có chủ đích với sự thay đổi không được kiểm soát trong cách làm.

## 10. Ví dụ thực tế

### Ví dụ A: Chọn kiểm thử hợp đồng cho kiến trúc dịch vụ

Một nền tảng có nhiều dịch vụ do các nhóm khác nhau phát triển và triển khai độc lập. Lịch sử cho thấy thay đổi schema ở một dịch vụ có thể làm hỏng dịch vụ tiêu thụ. Nhóm cân nhắc chỉ kiểm thử đầu cuối trong môi trường tích hợp, kiểm thử hợp đồng độc lập hoặc kết hợp cả hai. Nhóm chọn kiểm thử hợp đồng trong pipeline của bên cung cấp và bên tiêu thụ, đồng thời duy trì một số hành trình đầu cuối quan trọng.

Lý do là kiểm thử hợp đồng phản hồi sớm về sai lệch giao diện và giảm phụ thuộc vào môi trường tích hợp chung. Đánh đổi là phải quản lý phiên bản hợp đồng và xử lý các trường hợp tương thích ngược. Nhóm theo dõi lỗi tích hợp lọt ra, tỷ lệ hợp đồng không tương thích bị phát hiện trước triển khai và thời gian pipeline. Cần xem xét lại khi kiến trúc chuyển sang giao tiếp bất đồng bộ, có dịch vụ mới hoặc số lỗi lọt ra tăng.

### Ví dụ B: Chọn kiểm thử khám phá cho tính năng mới

Nhóm đang phát triển một tính năng có quy tắc nghiệp vụ chưa ổn định và người dùng chưa có thói quen sử dụng rõ ràng. Việc viết nhiều kiểm thử giao diện tự động ngay từ đầu có nguy cơ tạo chi phí sửa đổi lớn khi luồng thay đổi. Nhóm chọn kiểm thử khám phá có hướng dẫn, phiên thử nghiệm với người dùng đại diện và ghi nhận lỗi theo rủi ro; các quy tắc đã ổn định được tự động hóa ở tầng phù hợp.

Lựa chọn này dựa trên mức độ chưa chắc chắn của yêu cầu và nhu cầu học nhanh từ phản hồi. Rủi ro còn lại là một số hành vi có thể không được lặp lại nếu không ghi lại phiên kiểm thử. Nhóm cần lưu charter, dữ liệu, phát hiện và quyết định sản phẩm. Khi quy tắc và luồng người dùng ổn định, nhóm xem xét chuyển các kịch bản quan trọng thành kiểm thử hồi quy tự động.

### Ví dụ C: Chọn kiểm thử hiệu năng theo hành trình quan trọng

Một hệ thống có nhiều API nhưng chỉ một số hành trình ảnh hưởng trực tiếp đến doanh thu và trải nghiệm. Nhóm cân nhắc chạy tải đồng đều trên tất cả API hoặc mô phỏng tải theo hành trình người dùng thực tế. Nhóm chọn mô hình tải theo hành trình, bổ sung kiểm tra riêng cho API có rủi ro tài nguyên cao.

Lý do là mô hình này phản ánh phân bố sử dụng và điểm nghẽn mà người dùng thực sự gặp. Đánh đổi là cần dữ liệu hành vi đủ tin cậy và phải cập nhật mô hình khi cơ cấu người dùng thay đổi. Nhóm theo dõi độ trễ phân vị, thông lượng, lỗi và tài nguyên theo từng hành trình. Cần xem xét lại khi có kênh người dùng mới, chiến dịch lớn hoặc tỷ trọng giao dịch thay đổi đáng kể.

### Ví dụ D: Chọn triển khai theo từng đợt cho thay đổi rủi ro cao

Một thay đổi ảnh hưởng đến quy tắc tính phí và có thể tác động đến nhiều khách hàng. Nhóm chọn triển khai theo từng đợt với giới hạn nhóm người dùng, giám sát đối soát và khả năng tắt thay đổi. Quyết định này dựa trên tác động tài chính và khả năng quan sát sau triển khai.

Đánh đổi là quá trình phát hành và xác nhận kéo dài hơn, đồng thời phải duy trì khả năng tương thích giữa các phiên bản trong giai đoạn chuyển tiếp. Nhóm theo dõi sai lệch tính phí, lỗi giao dịch và phản hồi hỗ trợ. Cần xem xét lại khi không thể cô lập nhóm người dùng, dữ liệu giám sát không đáng tin hoặc cơ chế tắt thay đổi không còn hiệu lực.

## 11. Những sai lầm thường gặp

- **Chỉ ghi kết luận mà không ghi lý do:** người đọc không thể biết lựa chọn dựa trên mục tiêu hoặc bằng chứng nào.
- **Ghi lý do chung chung:** “theo best practice” hoặc “nhóm đã thống nhất” không giải thích mối liên hệ với bối cảnh.
- **Không lưu phương án thay thế:** nhóm sau không biết các lựa chọn khác đã được cân nhắc và vì sao bị loại.
- **Không nêu đánh đổi:** quyết định có thể bị hiểu nhầm là bao phủ đầy đủ mọi rủi ro.
- **Biến giả định thành sự thật:** thiếu dữ liệu nhưng ghi nhận như kết luận chắc chắn làm sai lệch quyết định sau này.
- **Không định nghĩa phạm vi áp dụng:** lựa chọn cho một dịch vụ bị áp dụng nhầm cho toàn bộ sản phẩm.
- **Không có trigger xem xét lại:** quyết định cũ tiếp tục tồn tại dù kiến trúc, tải hoặc rủi ro đã thay đổi.
- **Đặt trigger mơ hồ:** các cụm từ như “khi cần” không cho biết ai đánh giá và điều kiện nào kích hoạt.
- **Chỉ đo hoạt động, không đo kết quả:** số lượng ca kiểm thử tăng không chứng minh rủi ro đã giảm.
- **Sửa mất lịch sử quyết định:** không thể giải thích vì sao cách tiếp cận thay đổi theo thời gian.
- **Ghi mọi lựa chọn nhỏ thành hồ sơ dài:** làm tăng gánh nặng quản lý và khiến quyết định quan trọng khó được tìm thấy.

## 12. Checklist rà soát bản ghi quyết định

- [ ] Vấn đề và phạm vi cần quyết định được mô tả rõ.
- [ ] Mục tiêu chất lượng, rủi ro và ràng buộc liên quan được liên kết.
- [ ] Bằng chứng, giả định và phần chưa chắc chắn được phân biệt.
- [ ] Các phương án thực tế đã được cân nhắc.
- [ ] Lý do lựa chọn gắn với tiêu chí và bối cảnh cụ thể.
- [ ] Đánh đổi, giới hạn và rủi ro còn lại được ghi nhận.
- [ ] Phạm vi áp dụng, phiên bản, người tham gia và người phê duyệt được xác định.
- [ ] Có chỉ số hoặc bằng chứng để đánh giá hiệu quả sau áp dụng.
- [ ] Trigger xem xét lại có thể nhận biết và có người chịu trách nhiệm.
- [ ] Có ngày hoặc chu kỳ rà soát phù hợp.
- [ ] Quyết định thay thế vẫn giữ liên kết đến lịch sử và bằng chứng cũ.

## Kết luận

Ghi lại lý do lựa chọn và điều kiện cần xem xét lại giúp cách tiếp cận kiểm thử trở thành một quyết định có căn cứ và có thể điều chỉnh. Hồ sơ cần thể hiện bối cảnh, mục tiêu, ràng buộc, phương án đã cân nhắc, lựa chọn, bằng chứng, đánh đổi, phạm vi áp dụng và người phê duyệt. Các chỉ số cùng trigger cụ thể cho biết khi nào quyết định cần được đánh giá lại. Khi duy trì lịch sử và cập nhật theo thay đổi thực tế, nhóm giữ được tính nhất quán mà vẫn thích ứng với rủi ro và nhu cầu mới của sản phẩm.
