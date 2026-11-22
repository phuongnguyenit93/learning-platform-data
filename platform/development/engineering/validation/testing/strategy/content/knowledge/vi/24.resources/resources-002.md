# Ước lượng theo kinh nghiệm, công việc tương tự và tham vấn nhóm

Ước lượng nguồn lực kiểm thử là quá trình dự đoán công sức, thời gian, kỹ năng và điều kiện cần để hoàn thành một phạm vi công việc với mức chất lượng đã thống nhất. Ước lượng giúp nhóm lập kế hoạch, cân đối năng lực, xác định phụ thuộc và trao đổi kỳ vọng với các bên liên quan. Nó không phải lời hứa chắc chắn về ngày hoàn thành, bởi kết quả còn phụ thuộc độ rõ của yêu cầu, mức phức tạp, môi trường, dữ liệu, sự cố và những điều chưa biết.

Khi chưa có đủ dữ liệu để tính toán chi tiết, nhóm có thể kết hợp ba nguồn tri thức: kinh nghiệm từ công việc đã thực hiện, dữ liệu của những công việc tương tự và tham vấn những người sẽ trực tiếp tham gia. Mỗi nguồn có điểm mạnh và giới hạn. Kinh nghiệm giúp nhận diện phần việc thường bị bỏ sót; công việc tương tự cung cấp mốc so sánh thực tế; tham vấn nhóm giúp kiểm tra giả định và phát hiện khác biệt về hiểu biết. Kết hợp có phương pháp sẽ tạo ra ước lượng đáng tin hơn một con số do một người tự đưa ra.

## 1. Xác định đúng đối tượng cần ước lượng

Trước khi hỏi “mất bao lâu?”, cần xác định chính xác điều gì sẽ được thực hiện. Một kế hoạch kiểm thử có thể bao gồm nhiều loại công việc:

- Làm rõ yêu cầu, tiêu chí chấp nhận và rủi ro.
- Thiết kế chiến lược, test case, charter và dữ liệu kiểm thử.
- Chuẩn bị môi trường, tài khoản, công cụ và quyền truy cập.
- Viết hoặc cập nhật kiểm thử tự động.
- Thực hiện kiểm thử thủ công, thăm dò và kiểm tra chuyên sâu.
- Phân tích kết quả, tái hiện lỗi và thu thập bằng chứng.
- Báo cáo, triage và phối hợp xử lý phát hiện.
- Chạy lại sau sửa lỗi và kiểm tra hồi quy.
- Hoàn thiện tài liệu, bàn giao và hỗ trợ phát hành.

Nếu chỉ ước lượng thời gian chạy test mà bỏ qua chuẩn bị dữ liệu, điều tra lỗi và kiểm tra lại, kế hoạch sẽ thiếu công sức thực tế. Ngược lại, nếu cộng toàn bộ thời gian chờ vào công sức thực hiện mà không phân biệt, nhóm có thể đánh giá sai nhu cầu nhân lực.

Cần thống nhất đơn vị ước lượng. **Effort** thường được biểu diễn bằng giờ hoặc ngày công của người thực hiện; **duration** là khoảng thời gian lịch từ bắt đầu đến hoàn thành; **capacity** là năng lực thực tế có thể dành cho công việc trong một giai đoạn. Một hoạt động cần 4 ngày công có thể kéo dài 8 ngày lịch nếu người thực hiện chỉ dành một nửa thời gian hoặc phải chờ môi trường.

## 2. Phân rã công việc trước khi ước lượng

Ước lượng một hạng mục lớn bằng trực giác thường bỏ sót công việc và làm tăng sai số. Hãy phân rã phạm vi thành các phần có đầu ra và điều kiện hoàn thành rõ ràng.

Ví dụ, thay vì ước lượng chung “kiểm thử chức năng thanh toán”, có thể tách thành:

| Công việc | Đầu ra |
|---|---|
| Làm rõ luồng và rủi ro thanh toán | Danh sách quy tắc, luồng chính và ngoại lệ |
| Chuẩn bị dữ liệu và sandbox | Tài khoản, giao dịch thử và trạng thái ban đầu |
| Thiết kế test | Test case cho thành công, từ chối, timeout và callback lặp |
| Kiểm thử API và contract | Kết quả xác minh request/response và hợp đồng |
| Kiểm thử tích hợp | Bằng chứng tương tác giữa đơn hàng và nhà cung cấp |
| Kiểm thử hồi quy tự động | Bộ test được cập nhật và chạy trên CI |
| Điều tra và kiểm tra lại | Lỗi được tái hiện, xác minh sửa lỗi và báo cáo |
| Tổng hợp nghiệm thu | Trạng thái tiêu chí và rủi ro còn lại |

Mức phân rã nên đủ nhỏ để người có chuyên môn hiểu cách thực hiện và ước lượng. Không cần chia mọi công việc thành từng thao tác vài phút. Một hạng mục quá nhỏ làm tăng chi phí quản lý; một hạng mục quá lớn che giấu phụ thuộc và độ bất định.

Với mỗi phần việc, ghi rõ phạm vi bao gồm, phần loại trừ, đầu vào, đầu ra, người phụ trách và điều kiện hoàn tất. Nếu còn phần chưa rõ, ghi thành giả định hoặc việc cần làm rõ thay vì âm thầm cộng một khoảng thời gian không giải thích được.

## 3. Dùng kinh nghiệm một cách có căn cứ

Kinh nghiệm cá nhân là nguồn thông tin hữu ích khi người ước lượng từng thực hiện loại công việc tương tự. Người có kinh nghiệm có thể nhận ra các bước thường bị bỏ quên như cấu hình môi trường, chờ quyền truy cập, xử lý dữ liệu sai, điều tra flaky test hoặc phối hợp với nhóm phụ thuộc.

Tuy nhiên, kinh nghiệm dễ bị ảnh hưởng bởi trí nhớ chọn lọc. Một lần hoàn thành rất nhanh hoặc một sự cố bất thường có thể khiến người ước lượng đánh giá quá thấp hoặc quá cao công việc tiếp theo. Để dùng kinh nghiệm tốt hơn:

- Nhắc lại một số lần thực hiện gần nhất, không chỉ lần thành công nổi bật.
- Tách thời gian thực hiện thực tế khỏi thời gian chờ.
- Ghi nhận phần việc phát sinh và nguyên nhân.
- So sánh điều kiện cũ với phạm vi mới.
- Xem xét kỹ năng của người sẽ thực hiện và mức độ quen thuộc với hệ thống.
- Nêu rõ yếu tố nào trong ước lượng dựa trên kinh nghiệm cá nhân.

Ví dụ, một kỹ sư từng viết test API cho dịch vụ đơn giản có thể ước lượng nhanh phần kiểm tra endpoint. Nhưng nếu công việc mới có xác thực nhiều vai trò, dữ liệu đa tenant, callback bất đồng bộ và sandbox không ổn định, kinh nghiệm cũ chỉ hỗ trợ một phần. Cần bổ sung người hiểu nghiệp vụ, bảo mật và tích hợp để kiểm tra giả định.

Kinh nghiệm không nên trở thành lý do để bác bỏ ý kiến của thành viên ít thâm niên. Người mới có thể nhận ra yêu cầu chưa rõ hoặc cách làm phức tạp mà người quen hệ thống đã mặc định là bình thường.

## 4. Tìm công việc tương tự làm mốc tham chiếu

Ước lượng tương tự (analogous estimation) sử dụng dữ liệu từ công việc đã hoàn thành để dự đoán công việc mới. Cách này đặc biệt hữu ích ở giai đoạn đầu, khi chưa thể phân rã đầy đủ hoặc chưa biết chính xác mọi điều kiện.

Một công việc tham chiếu tốt có:

- Mục tiêu và loại kiểm thử gần giống.
- Mức độ phức tạp tương đương.
- Số lượng luồng, API, vai trò hoặc cấu hình gần nhau.
- Mức ổn định của yêu cầu và kiến trúc tương tự.
- Điều kiện môi trường, dữ liệu và phụ thuộc có thể so sánh.
- Thành phần nhóm và năng lực thực hiện tương đương.
- Dữ liệu thực tế về effort, duration và phần việc phát sinh.

Không nên chọn công việc tương tự chỉ vì tên hoặc số lượng test giống nhau. Hai tính năng đều có 20 test case nhưng một tính năng có dữ liệu độc lập, còn tính năng kia cần nhiều vai trò, giao dịch bất đồng bộ và đối soát; công sức có thể khác đáng kể.

Khi dùng mốc tham chiếu, hãy ghi:

1. Công việc lịch sử nào được chọn.
2. Những điểm giống nhau.
3. Những khác biệt có ảnh hưởng.
4. Điều chỉnh tăng hoặc giảm và lý do.
5. Mức tin cậy của phép so sánh.

Ví dụ, một đợt kiểm thử API trước đây cần 5 ngày công cho 12 endpoint với một vai trò và dữ liệu ổn định. Công việc mới có 10 endpoint nhưng thêm ba vai trò, callback và dữ liệu đa tenant. Không nên giảm ước lượng theo tỷ lệ số endpoint; cần điều chỉnh theo độ phức tạp về quyền, tích hợp và chuẩn bị dữ liệu.

## 5. Điều chỉnh công việc tương tự theo độ phức tạp

Có thể dùng bảng yếu tố điều chỉnh để tránh so sánh máy móc.

| Yếu tố | Làm tăng công sức khi | Làm giảm công sức khi |
|---|---|---|
| Yêu cầu | Nhiều điểm chưa rõ hoặc thay đổi thường xuyên | Tiêu chí đã được xác nhận và ổn định |
| Kiến trúc | Nhiều dịch vụ, phụ thuộc hoặc luồng bất đồng bộ | Ranh giới đơn giản, giao diện ổn định |
| Dữ liệu | Cần tạo dữ liệu lớn, nhạy cảm hoặc nhiều quan hệ | Có fixture đáng tin và công cụ tạo dữ liệu |
| Môi trường | Cần cấp phát, phê duyệt hoặc cấu hình chuyên biệt | Môi trường sẵn sàng và có thể tạo lại |
| Bảo mật | Nhiều vai trò, tenant, tài sản nhạy cảm hoặc kiểm tra chuyên sâu | Phạm vi rủi ro thấp và có kiểm soát sẵn |
| Tự động hóa | Framework mới, test khó ổn định hoặc cần tích hợp CI | Có thư viện, pattern và pipeline dùng lại |
| Năng lực nhóm | Thiếu kỹ năng hoặc cần học công nghệ mới | Nhóm đã quen hệ thống và công cụ |
| Phụ thuộc ngoài | Sandbox, nhà cung cấp hoặc nhóm khác khó phối hợp | Có stub, contract và lịch phối hợp rõ |
| Phạm vi hồi quy | Nhiều consumer hoặc luồng bị ảnh hưởng | Tác động cục bộ và đồ thị phụ thuộc rõ |

Không cần chuyển mọi yếu tố thành hệ số số học. Có thể ghi điều chỉnh định tính như “cao hơn công việc tham chiếu vì cần xác minh phân quyền đa tenant” và nêu phần effort bổ sung dự kiến. Nếu dùng hệ số, cần hiệu chỉnh bằng dữ liệu lịch sử để tránh tạo cảm giác chính xác giả tạo.

## 6. Tham vấn nhóm để kiểm tra giả định

Tham vấn nhóm (team consultation) giúp tập hợp hiểu biết từ những người nhìn công việc ở các góc độ khác nhau. Một người có thể hiểu logic nghiệp vụ, người khác biết hạ tầng, người khác nắm quy trình phát hành hoặc lịch sử lỗi.

Nên mời những vai trò thực sự liên quan:

- QA hoặc test lead hiểu phạm vi và phương pháp kiểm thử.
- Developer hiểu cấu trúc mã, thay đổi và phụ thuộc.
- Product owner hoặc chuyên gia nghiệp vụ xác nhận quy tắc và ưu tiên.
- DevOps, platform hoặc SRE hiểu môi trường và triển khai.
- Security specialist đánh giá rủi ro và kiểm tra bảo mật.
- DBA hoặc data engineer hỗ trợ dữ liệu và migration.
- Người phụ trách tích hợp hoặc nhà cung cấp khi có phụ thuộc ngoài.

Tham vấn không có nghĩa mọi người đều phải tham gia mọi buổi ước lượng. Chọn người theo câu hỏi cần trả lời để tránh cuộc họp quá đông và mất thời gian. Nếu thiếu một chuyên môn quan trọng, ghi rõ phần ước lượng còn bất định và cách bổ sung ý kiến sau đó.

## 7. Tổ chức buổi ước lượng có cấu trúc

Một buổi ước lượng hiệu quả cần chuẩn bị trước để thời gian trao đổi tập trung vào giả định và khác biệt.

### Trước buổi trao đổi

- Gửi mục tiêu, phạm vi và tài liệu liên quan.
- Chia công việc thành các hạng mục có đầu ra.
- Cung cấp dữ liệu công việc tương tự nếu có.
- Nêu các ràng buộc về thời gian, môi trường và kỹ năng.
- Đánh dấu câu hỏi chưa được giải đáp.

### Trong buổi trao đổi

1. Xác nhận mọi người hiểu cùng một phạm vi.
2. Làm rõ điều kiện hoàn thành và phần loại trừ.
3. Xem xét từng hạng mục và phụ thuộc.
4. Ước lượng độc lập trước khi thảo luận nếu có nguy cơ bị ảnh hưởng bởi ý kiến đầu tiên.
5. Yêu cầu người đưa ra giá trị cao hoặc thấp giải thích giả định.
6. Ghi nhận phần việc chưa rõ và rủi ro.
7. Thống nhất khoảng ước lượng hoặc cách xử lý bất đồng.

### Sau buổi trao đổi

- Ghi kết quả, giả định, người tham gia và ngày ước lượng.
- Giao người xác minh các câu hỏi còn mở.
- Cập nhật khi phạm vi hoặc điều kiện thay đổi.
- Giữ lịch sử ước lượng ban đầu để so sánh và học hỏi.

Buổi ước lượng không nên biến thành cuộc tranh luận nhằm tìm một con số khiến tất cả hài lòng. Mục tiêu là làm rõ cơ sở và mức không chắc chắn để nhóm có thể lập kế hoạch có trách nhiệm.

## 8. Dùng ước lượng độc lập và kỹ thuật Planning Poker

Khi một người nói con số đầu tiên, những người khác có thể vô thức điều chỉnh theo. Ước lượng độc lập giúp bộc lộ sự khác nhau trong cách hiểu.

Planning Poker là một kỹ thuật tham vấn thường dùng trong nhóm Agile:

1. Người điều phối trình bày hạng mục và tiêu chí hoàn thành.
2. Các thành viên đặt câu hỏi để làm rõ.
3. Mỗi người chọn giá trị ước lượng độc lập, thường dùng dãy số tăng dần như Fibonacci hoặc thang điểm của nhóm.
4. Mọi người công bố lựa chọn cùng lúc.
5. Người chọn mức thấp nhất và cao nhất giải thích giả định.
6. Nhóm thảo luận khác biệt, làm rõ phạm vi và ước lượng lại nếu cần.
7. Ghi kết quả cùng các rủi ro hoặc giả định còn mở.

Planning Poker không tự tạo ra độ chính xác. Điểm tương đối không phải ngày công và không nên chuyển trực tiếp thành cam kết lịch nếu nhóm chưa có dữ liệu hiệu chỉnh. Kỹ thuật này hữu ích để phát hiện khác biệt trong hiểu biết, đặc biệt khi công việc có nhiều phụ thuộc hoặc cách tiếp cận khác nhau.

Nếu hạng mục quá lớn hoặc chưa đủ thông tin, hãy tách nhỏ hoặc thực hiện một hoạt động khám phá ngắn thay vì ép nhóm chọn một con số.

## 9. Dùng ước lượng ba điểm để thể hiện bất định

Một con số đơn lẻ thường che giấu mức không chắc chắn. Ước lượng ba điểm ghi nhận ba tình huống:

- **Optimistic (O):** công việc diễn ra thuận lợi trong các điều kiện hợp lý.
- **Most likely (M):** kịch bản có khả năng xảy ra nhất.
- **Pessimistic (P):** công việc gặp các khó khăn có cơ sở, nhưng chưa phải tình huống thảm họa.

Có thể dùng công thức PERT để tính giá trị kỳ vọng:

\[
E = \frac{O + 4M + P}{6}
\]

Ví dụ, nhóm ước lượng một hạng mục kiểm thử là O = 2 ngày công, M = 4 ngày công, P = 8 ngày công:

\[
E = \frac{2 + 4(4) + 8}{6} = 4{,}33 \text{ ngày công}
\]

Giá trị này là một ước lượng có trọng số, không phải lời hứa rằng công việc chắc chắn hoàn thành trong 4,33 ngày. Khoảng từ 2 đến 8 ngày vẫn thể hiện bất định đáng kể. Nếu P lớn vì phụ thuộc chưa được xác nhận, cần tìm cách giảm bất định thay vì chỉ cộng thêm một hệ số.

Ba điểm cần dựa trên giả định và dữ liệu. Không nên chọn O quá lạc quan hoặc P như một thảm họa không liên quan. Ghi rõ sự kiện nào khiến kịch bản xấu có thể xảy ra.

## 10. Phân biệt effort, duration và capacity khi lập kế hoạch

Ước lượng công sức không trực tiếp quyết định ngày hoàn thành. Hãy chuyển effort thành lịch dựa trên năng lực có thể dành cho công việc và các phụ thuộc.

Ví dụ:

- Tổng effort ước lượng: 12 ngày công.
- Hai người có thể tham gia, mỗi người dành trung bình 50% thời gian.
- Capacity lý thuyết mỗi ngày: 1 ngày công.
- Duration lý thuyết tối thiểu: khoảng 12 ngày làm việc, chưa tính phụ thuộc và chờ đợi.

Không phải lúc nào tăng số người cũng giảm duration theo tỷ lệ. Một số công việc có thứ tự bắt buộc; người mới cần thời gian làm quen; nhiều người cùng sửa một tài nguyên có thể tạo xung đột. Hãy xem xét:

- Người có kỹ năng cần thiết có thực sự sẵn sàng không?
- Có thể chia công việc độc lập không?
- Các hạng mục có phụ thuộc tuần tự không?
- Môi trường hoặc thiết bị có giới hạn số người dùng đồng thời không?
- Có thời gian review, bàn giao và phối hợp không?
- Người tham gia còn nhiệm vụ vận hành hoặc hỗ trợ khác không?

Capacity nên dựa trên thời gian làm việc thực tế sau khi trừ nghỉ phép, họp, hỗ trợ và công việc thường xuyên. Không lập kế hoạch với giả định mọi người dành 100% thời gian cho một dự án nếu điều đó không đúng.

## 11. Đưa phụ thuộc và thời gian chờ vào ước lượng

Một số công việc kiểm thử không thể bắt đầu ngay khi người thực hiện sẵn sàng. Chúng phụ thuộc vào:

- Yêu cầu hoặc thiết kế được phê duyệt.
- Build hoặc API từ nhóm phát triển.
- Môi trường, tài khoản và quyền truy cập.
- Dataset hoặc bản sao dữ liệu.
- Sandbox và lịch của nhà cung cấp.
- Thiết bị, giấy phép hoặc chuyên gia dùng chung.
- Kết quả sửa lỗi và bản dựng mới.
- Quyết định về phạm vi hoặc ngoại lệ.

Cần phân biệt **effort xử lý phụ thuộc** với **thời gian chờ phụ thuộc**. Ví dụ, chuẩn bị tài khoản có thể cần 2 giờ công nhưng quy trình phê duyệt kéo dài 3 ngày lịch. Nếu chỉ ghi 2 giờ, lịch sẽ không phản ánh thời điểm có thể bắt đầu kiểm thử.

Với phụ thuộc có độ bất định cao, ghi người sở hữu, ngày cần, trạng thái và phương án thay thế. Nếu một sandbox chưa sẵn sàng, có thể dùng fake để kiểm tra logic trước, nhưng phải giữ lại bước xác minh với sandbox thật nếu đó là mục tiêu bắt buộc.

## 12. Tính đến công việc phát sinh, điều tra và kiểm tra lại

Kiểm thử không chỉ là chạy test lần đầu. Khi phát hiện lỗi, nhóm cần tái hiện, thu thập bằng chứng, phân tích, phối hợp sửa và xác minh lại.

Ước lượng nên xét:

- Số vòng kiểm thử dự kiến.
- Khả năng xuất hiện lỗi và thời gian triage.
- Mức phức tạp khi tái hiện.
- Thời gian chờ bản dựng sửa lỗi.
- Phạm vi hồi quy sau khi sửa.
- Khả năng phát sinh lỗi liên quan.
- Thời gian cập nhật test, dữ liệu và tài liệu.
- Nhu cầu kiểm tra lại trên nhiều môi trường hoặc cấu hình.

Không nên cộng một tỷ lệ dự phòng tùy tiện cho mọi dự án. Hãy xem lịch sử các công việc tương tự để hiểu phần effort phát sinh thường đến từ đâu. Nếu chưa có dữ liệu, ghi rõ giả định và xem xét một khoảng dự phòng phù hợp với mức bất định.

Cũng cần tránh tính trùng. Nếu ước lượng một hạng mục đã bao gồm một vòng sửa và retest, không cộng lại cùng phần việc trong mục tổng hợp khác.

## 13. Quản lý bất định, giả định và khoảng dự phòng

Bất định là phần chưa thể xác định chính xác tại thời điểm ước lượng. Một số nguồn phổ biến:

- Yêu cầu chưa được xác nhận.
- Thiết kế hoặc API đang thay đổi.
- Công nghệ hoặc công cụ mới.
- Dữ liệu và môi trường chưa sẵn sàng.
- Phụ thuộc bên ngoài khó dự đoán.
- Chưa rõ phạm vi hồi quy.
- Thiếu dữ liệu lịch sử hoặc chuyên gia.

Hãy ghi mỗi bất định cùng ảnh hưởng và cách giảm:

| Bất định | Ảnh hưởng có thể có | Hành động giảm bất định |
|---|---|---|
| Chưa rõ quy tắc hoàn tiền | Test case và dữ liệu có thể phải thiết kế lại | Workshop với chủ sở hữu nghiệp vụ |
| Sandbox nhà cung cấp chưa ổn định | Tăng thời gian chờ và điều tra | Xác nhận lịch, quota và chuẩn bị fake |
| Chưa biết phạm vi consumer API | Có thể thiếu contract test | Lập danh sách consumer và rà soát phụ thuộc |
| Nhóm chưa quen framework | Tăng thời gian thiết lập và sửa test | Spike ngắn, ghép cặp hoặc đào tạo |
| Dataset lớn chưa sẵn sàng | Không thể đánh giá hiệu năng đại diện | Chuẩn bị dữ liệu tổng hợp hoặc bản sao phù hợp |

Dự phòng nên gắn với rủi ro cụ thể, không phải phần thời gian “để cho chắc” không có căn cứ. Với rủi ro có thể loại bỏ bằng một hoạt động khám phá ngắn, hãy thực hiện hoạt động đó trước khi chốt kế hoạch. Với bất định không thể loại bỏ, dùng khoảng ước lượng và theo dõi khi có thông tin mới.

## 14. Ghi lại ước lượng, mức tin cậy và cơ sở

Một ước lượng có thể sử dụng được cần giải thích cách hình thành. Hồ sơ có thể gồm:

| Trường | Nội dung |
|---|---|
| Hạng mục | Công việc cần ước lượng và đầu ra |
| Phạm vi | Bao gồm, loại trừ và tiêu chí hoàn thành |
| Effort | Khoảng công sức hoặc giá trị ước lượng |
| Duration | Khoảng thời gian lịch dự kiến |
| Capacity | Người và tỷ lệ thời gian có thể tham gia |
| Cơ sở tham chiếu | Công việc tương tự, dữ liệu lịch sử hoặc chuyên gia |
| Giả định | Điều kiện cần đúng để ước lượng có hiệu lực |
| Phụ thuộc | Môi trường, nhóm, dữ liệu, quyền và nhà cung cấp |
| Rủi ro | Sự kiện có thể làm tăng effort hoặc duration |
| Mức tin cậy | Cao, trung bình hoặc thấp cùng lý do |
| Chủ sở hữu | Người cập nhật và theo dõi |
| Ngày rà soát | Thời điểm xem lại khi có thông tin mới |

Mức tin cậy không nên là nhãn cảm tính. Ví dụ, “trung bình” có thể có nghĩa phạm vi đã rõ và có công việc tham chiếu, nhưng môi trường tích hợp chưa được xác nhận. Ghi lý do giúp người đọc hiểu cần làm gì để tăng độ tin cậy.

## 15. Theo dõi sai lệch giữa ước lượng và thực tế

Sau khi hoàn thành, so sánh effort và duration thực tế với ước lượng ban đầu. Mục tiêu là học cách ước lượng tốt hơn, không phải đánh giá cá nhân dựa trên việc có hoàn thành đúng con số hay không.

Hãy phân tích:

- Phần nào hoàn thành nhanh hoặc chậm hơn dự kiến?
- Công việc nào bị bỏ sót?
- Giả định nào đúng hoặc sai?
- Phụ thuộc nào gây chờ đợi?
- Có thay đổi phạm vi không?
- Có lỗi môi trường, dữ liệu hoặc công cụ không?
- Kỹ năng và số người tham gia có khác kế hoạch không?
- Phần effort phát sinh có lặp lại ở các dự án khác không?

Phân biệt sai lệch do ước lượng với sai lệch do thay đổi phạm vi. Nếu yêu cầu tăng thêm sau khi bắt đầu, cần ghi thay đổi và ước lượng lại phần bổ sung thay vì coi toàn bộ sai lệch là lỗi dự báo ban đầu.

Dùng dữ liệu tổng hợp qua nhiều công việc để hiệu chỉnh cách ước lượng. Không nên lấy một trường hợp bất thường làm hệ số chung. Có thể phân nhóm theo loại kiểm thử, công nghệ, mức độ phức tạp và kinh nghiệm nhóm để so sánh công bằng hơn.

## 16. Ví dụ: ước lượng kiểm thử một tính năng hoàn tiền

Một nhóm cần kiểm thử tính năng hoàn tiền cho đơn hàng. Phạm vi gồm API, phân quyền, tích hợp nhà cung cấp thanh toán, xử lý callback và cập nhật trạng thái đơn hàng.

Nhóm phân rã công việc và dùng một tính năng thanh toán trước đó làm mốc tham chiếu:

| Hạng mục | Cơ sở ước lượng | Effort dự kiến |
|---|---|---:|
| Làm rõ quy tắc và tiêu chí | Tham vấn product và nghiệp vụ | 1–2 ngày công |
| Thiết kế test và rủi ro | Kinh nghiệm kiểm thử giao dịch | 1–2 ngày công |
| Chuẩn bị dữ liệu, vai trò và sandbox | Công việc tích hợp tương tự | 1–3 ngày công |
| API, contract và phân quyền | Số endpoint, vai trò và ma trận quyền | 2–3 ngày công |
| Callback, retry và idempotency | Độ phức tạp bất đồng bộ | 2–4 ngày công |
| Hồi quy và tự động hóa | Mức dùng lại framework hiện tại | 2–4 ngày công |
| Triage, retest và báo cáo | Lịch sử lỗi của luồng thanh toán | 2–4 ngày công |

Các khoảng trên chỉ minh họa cách phân tích, không phải chuẩn định mức áp dụng cho mọi dự án. Nhóm cần thay bằng dữ liệu và năng lực thực tế.

Trong buổi tham vấn, developer lưu ý callback có thể đến trước khi hệ thống cập nhật trạng thái đơn hàng; DBA xác nhận cần thêm dữ liệu đối soát; QA phát hiện sandbox không hỗ trợ một số mã lỗi; product xác nhận chính sách hoàn một phần. Những thông tin này làm thay đổi phạm vi so với tính năng tham chiếu.

Nhóm ghi nhận các giả định: sandbox được cấp trong tuần đầu, API contract được chốt trước khi viết test và môi trường có thể tạo giao dịch giả lập. Nếu các giả định không đạt, effort và duration cần được xem xét lại. Nhóm cũng tách effort thực hiện khỏi thời gian chờ phê duyệt sandbox.

Sau khi hoàn thành, nhóm so sánh số ngày công thực tế, thời gian chờ và số vòng retest với ước lượng. Nếu phần lớn phát sinh do sandbox, lần sau cần đưa thời gian phụ thuộc nhà cung cấp vào lịch sớm hơn; nếu do thiếu quy tắc hoàn một phần, cần cải thiện refinement trước khi bắt đầu kiểm thử.

## 17. Quy trình ước lượng kết hợp ba nguồn tri thức

Có thể áp dụng quy trình sau:

1. **Làm rõ phạm vi:** xác định đầu ra, điều kiện hoàn thành và phần loại trừ.
2. **Phân rã công việc:** chia thành hạng mục đủ nhỏ để ước lượng.
3. **Thu thập kinh nghiệm:** hỏi người đã thực hiện công việc tương tự và xem lại các lần gần nhất.
4. **Chọn mốc tham chiếu:** tìm công việc lịch sử có phạm vi và điều kiện gần nhất.
5. **Điều chỉnh khác biệt:** xem xét độ phức tạp, dữ liệu, môi trường, kỹ năng và phụ thuộc.
6. **Tham vấn nhóm:** ước lượng độc lập, giải thích chênh lệch và thống nhất giả định.
7. **Thể hiện bất định:** dùng khoảng hoặc ba điểm khi cần, ghi rủi ro và mức tin cậy.
8. **Chuyển sang kế hoạch:** phân biệt effort, duration và capacity; lập lịch theo phụ thuộc.
9. **Theo dõi và cập nhật:** điều chỉnh khi phạm vi hoặc giả định thay đổi.
10. **Học từ thực tế:** so sánh với kết quả, tìm sai lệch có tính hệ thống và cải thiện dữ liệu tham chiếu.

~~~mermaid
flowchart TD
    A["Yêu cầu và phạm vi kiểm thử"] --> B["Phân rã thành công việc"]
    B --> C["Thu thập kinh nghiệm và dữ liệu lịch sử"]
    C --> D["Chọn công việc tương tự"]
    D --> E["Điều chỉnh theo khác biệt và phụ thuộc"]
    E --> F["Tham vấn, ước lượng độc lập trong nhóm"]
    F --> G["Thống nhất khoảng, giả định và mức tin cậy"]
    G --> H["Lập kế hoạch theo effort, duration và capacity"]
    H --> I["Thực hiện và ghi nhận thực tế"]
    I --> J["So sánh, rút kinh nghiệm và cập nhật dữ liệu"]
    J --> C
~~~

## 18. Checklist ước lượng nguồn lực

Trước khi chốt kế hoạch, hãy kiểm tra:

- Phạm vi, đầu ra và tiêu chí hoàn thành đã rõ chưa?
- Công việc đã được phân rã đủ để nhận diện phần việc bị bỏ sót chưa?
- Ước lượng có tính thiết kế, dữ liệu, môi trường, thực thi, triage, retest và báo cáo không?
- Có dữ liệu thực tế từ công việc tương tự không?
- Những khác biệt về độ phức tạp và phụ thuộc đã được điều chỉnh chưa?
- Người có chuyên môn liên quan đã tham vấn chưa?
- Các thành viên có cơ hội ước lượng độc lập và giải thích chênh lệch không?
- Effort, duration và capacity đã được phân biệt chưa?
- Thời gian chờ môi trường, quyền và nhóm phụ thuộc đã được thể hiện chưa?
- Giả định, rủi ro và mức tin cậy có được ghi lại không?
- Khoảng dự phòng có gắn với rủi ro cụ thể và tránh tính trùng không?
- Có điều kiện làm phát sinh việc ước lượng lại không?
- Thực tế sau hoàn thành có được ghi nhận để hiệu chỉnh lần sau không?

Ước lượng theo kinh nghiệm, công việc tương tự và tham vấn nhóm giúp biến dự đoán thành một quá trình có thể giải thích và cải thiện. Kinh nghiệm chỉ ra những phần việc thường bị bỏ sót; dữ liệu tương tự cung cấp mốc thực tế; tham vấn giúp kiểm tra giả định và phát hiện khác biệt trong cách hiểu. Khi nhóm ghi rõ phạm vi, phụ thuộc, mức bất định và so sánh với kết quả thực tế, ước lượng trở thành công cụ lập kế hoạch và học hỏi thay vì một con số cam kết thiếu cơ sở.

