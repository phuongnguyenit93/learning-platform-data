# Xác định vấn đề chất lượng đang gây chi phí thực tế

Trong chương **Cải thiện liên tục** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tập trung vào bước đầu tiên của mọi hoạt động cải tiến: xác định vấn đề chất lượng nào đang làm nhóm, sản phẩm hoặc người dùng phải trả một khoản chi phí có thể quan sát được.

Một code smell, một cảnh báo static analysis hay một chỉ số đang tăng có thể là tín hiệu đáng điều tra. Nhưng bản thân tín hiệu chưa chứng minh rằng nó đang gây tổn thất. Một phương thức dài có thể ổn định và hiếm khi thay đổi; một test chập chờn có thể làm cả nhóm mất thời gian mỗi tuần; một quy tắc nghiệp vụ bị sao chép có thể khiến mỗi lần thay đổi phải sửa nhiều nơi và đã từng tạo ra hành vi không nhất quán.

Mục tiêu của **CODE_QUALITY_FUNDAMENTALS** là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Để cải thiện các thuộc tính đó, nhóm cần nối một vấn đề kỹ thuật với công việc thực tế: thay đổi nào bị chậm, lỗi nào đến được người dùng, hoạt động vận hành nào phải lặp lại, hoặc rủi ro nào đang tăng vì một cơ chế cụ thể.

> **Bắt đầu từ một tình huống có thể kiểm chứng: ai đang gặp trở ngại, trong công việc nào, chi phí hoặc rủi ro phát sinh ra sao, và bằng chứng nào cho thấy vấn đề đáng được ưu tiên?**

Bài học này hướng dẫn cách nhận diện tín hiệu, phân biệt triệu chứng với nguyên nhân, thu thập bằng chứng, ước lượng chi phí có giới hạn, lập đường cơ sở, ưu tiên vấn đề và chuyển kết quả điều tra thành một thử nghiệm cải tiến có thể đánh giá.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt vấn đề chất lượng đã được quan sát với nhận xét cảm tính, mùi mã hoặc giải pháp được đề xuất sẵn.
2. Nhận diện các loại chi phí phát sinh từ chất lượng mã: làm lại, chờ đợi, lỗi lọt ra ngoài, vận hành, tìm hiểu và rủi ro.
3. Viết mô tả vấn đề gắn với tình huống thay đổi, sự cố hoặc công việc lặp lại.
4. Thu thập bằng chứng từ pull request, CI, test, issue, incident, telemetry và phản hồi người dùng.
5. Đo tần suất, thời gian, phạm vi và mức độ ảnh hưởng bằng đơn vị rõ ràng.
6. Phân biệt chi phí đã xảy ra với tổn thất kỳ vọng hoặc rủi ro chưa hiện thực hóa.
7. Tìm nguyên nhân có thể kiểm chứng thay vì dừng ở triệu chứng hoặc đổ lỗi cho cá nhân.
8. Ưu tiên vấn đề theo tác động, tần suất, độ chắc chắn, chi phí xử lý và khả năng giảm rủi ro.
9. Đề xuất một thay đổi nhỏ có giả thuyết, tiêu chí thành công và điều kiện dừng rõ ràng.
10. Đánh giá cải tiến bằng dữ liệu trước–sau mà không tuyên bố quan hệ nhân quả vượt quá bằng chứng.

## 2. Vấn đề chất lượng là gì?

Một vấn đề chất lượng tồn tại khi **hành vi, cấu trúc hoặc quy trình hiện tại gây trở ngại hoặc rủi ro đáng kể so với điều sản phẩm và nhóm cần đạt được**.

Vấn đề có thể biểu hiện ở nhiều nơi:

- Mã khó hiểu khiến người mới không tìm được nơi sở hữu một quy tắc.
- Test không ổn định khiến thay đổi phải chạy lại nhiều lần.
- Thiếu kiểm thử tích hợp khiến lỗi schema chỉ xuất hiện sau khi triển khai.
- Logic nghiệp vụ bị nhân bản khiến các luồng trả kết quả khác nhau.
- Cấu hình và quy trình deploy phụ thuộc vào trí nhớ của một người.
- Một truy vấn tạo tải lớn và làm tăng độ trễ trong kịch bản người dùng quan trọng.

Một vấn đề chất lượng không nhất thiết đã gây incident. Một cơ chế có thể tạo ra rủi ro nghiêm trọng và có thể chứng minh bằng lập luận kỹ thuật trước khi hậu quả xảy ra. Tuy nhiên, cần ghi rõ đó là **rủi ro có căn cứ**, không mô tả nó như một thiệt hại đã xảy ra.

### 2.1. Phân biệt tín hiệu, vấn đề, nguyên nhân và giải pháp

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Tín hiệu** | Ta nhìn thấy điều gì? | CI có nhiều lần chạy lại; một class có complexity cao. |
| **Vấn đề** | Công việc hoặc người dùng bị ảnh hưởng thế nào? | PR phải chờ kết quả đáng tin; thay đổi chính sách thường bỏ sót một luồng. |
| **Nguyên nhân giả thuyết** | Cơ chế nào có thể tạo ra ảnh hưởng? | Test chia sẻ trạng thái; quy tắc được sao chép ở nhiều module. |
| **Giải pháp giả thuyết** | Thay đổi nào có thể giảm nguyên nhân? | Cô lập fixture; tập trung quy tắc vào một nơi có trách nhiệm. |
| **Kết quả cần xác minh** | Bằng chứng nào sẽ khác sau cải tiến? | Số lần rerun giảm; thay đổi chính sách không còn phải sửa nhiều bản sao. |

Nếu bắt đầu bằng câu “chúng ta cần viết lại service”, nhóm đã chọn giải pháp trước khi xác định vấn đề. Có thể việc viết lại giúp ích, nhưng cũng có thể một test không ổn định hoặc một ranh giới dữ liệu chưa rõ mới là nguyên nhân thật.

### 2.2. Không phải mọi điều chưa hoàn hảo đều là vấn đề ưu tiên

Một đoạn mã có thể chưa dùng cấu trúc tối ưu nhất nhưng vẫn dễ hiểu, ổn định và ít thay đổi. Một cảnh báo có thể đúng về mặt hình thức nhưng không liên quan đến rủi ro của sản phẩm.

Hãy hỏi:

- Có ai đang phải làm thêm việc vì điều này không?
- Hành vi nào bị chậm, sai hoặc khó xác minh?
- Tình huống có lặp lại không?
- Phạm vi ảnh hưởng và hậu quả là gì?
- Có bằng chứng cho thấy cải thiện sẽ giúp công việc tốt hơn không?

Nếu chưa có tác động quan sát được, vẫn có thể ghi nhận một giả thuyết để theo dõi. Nhưng không nên tự gán mức ưu tiên cao chỉ vì một metric hoặc công cụ báo đỏ.

## 3. Những loại chi phí chất lượng thường gặp

Chi phí chất lượng không chỉ là tiền sửa bug. Nó bao gồm thời gian làm lại, thời gian chờ, gián đoạn vận hành và rủi ro mà sản phẩm phải gánh.

### 3.1. Chi phí làm lại (*rework*)

Phát sinh khi một công việc phải sửa hoặc thực hiện lại do lỗi, thiếu thông tin hoặc thay đổi bị bỏ sót.

Ví dụ:

- PR phải sửa nhiều vòng vì yêu cầu và hợp đồng chưa rõ.
- Một chính sách bị cập nhật ở hai module nhưng bỏ quên module thứ ba.
- Test không kiểm tra giá trị biên nên lỗi quay lại và phải làm hotfix.
- Dữ liệu phải sửa thủ công sau một migration chưa được kiểm tra đầy đủ.

Có thể ghi số lần sửa bổ sung, thời gian xử lý và nguyên nhân. Không nên gộp toàn bộ thời gian PR thành “chi phí do chất lượng” nếu trong đó còn có thời gian chờ phê duyệt hoặc thay đổi yêu cầu.

### 3.2. Chi phí chờ đợi và gián đoạn luồng công việc

Phát sinh khi người phát triển hoặc nhóm phải chờ:

- Pipeline CI chạy lâu hoặc runner đang bận.
- Review bị chặn vì không có người hiểu module.
- Môi trường tích hợp không sẵn sàng.
- Một quyết định kiến trúc chưa có người chịu trách nhiệm.
- Phụ thuộc bên ngoài chưa xác nhận hợp đồng.

Thời gian chờ làm kéo dài thời gian hoàn thành và có thể gây chuyển ngữ cảnh. Tuy nhiên, **thời gian PR mở không đồng nghĩa với số giờ lao động bị mất**. Cần tách thời gian lịch thực, thời gian chờ và thời gian con người thực sự phải xử lý.

### 3.3. Chi phí lỗi lọt ra ngoài (*escaped defects*)

Lỗi không được phát hiện trước khi phát hành có thể tạo:

- Hỗ trợ khách hàng và điều tra.
- Hotfix, rollback hoặc khôi phục dữ liệu.
- Giao dịch sai, mất dữ liệu hoặc gián đoạn dịch vụ.
- Bồi hoàn, phạt hoặc ảnh hưởng cam kết dịch vụ.
- Mất niềm tin của người dùng.

Với sự cố nghiêm trọng, một lần xảy ra có thể đủ để ưu tiên xử lý. Không nên chỉ nhìn tần suất mà bỏ qua mức tác động.

### 3.4. Chi phí vận hành và bảo trì

Ví dụ:

- On-call phải kiểm tra thủ công nhiều bước cho một alert.
- Job định kỳ cần người khởi động lại thường xuyên.
- Một service khó deploy vì cấu hình không nhất quán.
- Truy vấn dư thừa làm tăng tải database.
- Không có runbook khiến thời gian khôi phục kéo dài.

Những chi phí này có thể lặp lại ngay cả khi code không thay đổi.

### 3.5. Chi phí hiểu và truyền đạt tri thức

Khi trách nhiệm, hợp đồng hoặc quyết định không rõ, nhóm có thể phải:

- Hỏi lại người viết cũ.
- Đọc nhiều file để tìm một quy tắc.
- Dựng môi trường khó tái tạo.
- Review nhiều vòng để xác minh giả định.
- Bàn giao lâu vì chỉ một người hiểu quy trình.

Không phải mọi câu hỏi đều là lãng phí; trao đổi là một phần của cộng tác. Vấn đề xuất hiện khi cùng một thông tin phải được khám phá lặp lại hoặc một người trở thành điểm nghẽn cho công việc quan trọng.

### 3.6. Rủi ro chưa hiện thực hóa

Một thiết kế có thể tạo nguy cơ mất dữ liệu, lộ thông tin hoặc không thể rollback dù chưa có incident. Có thể ghi nhận rủi ro nếu cơ chế và điều kiện xảy ra rõ ràng.

Phải phân biệt:

- **Chi phí đã xảy ra:** có sự kiện và bằng chứng.
- **Chi phí có khả năng lặp lại:** đã quan sát một cơ chế hoặc nhiều lần tương tự.
- **Rủi ro dự kiến:** hậu quả có thể xảy ra theo một kịch bản có căn cứ.
- **Giả thuyết chưa xác minh:** cần thêm dữ liệu trước khi đánh giá.

## 4. Tìm tín hiệu từ công việc hằng ngày

Những vấn đề chất lượng thường để lại dấu vết trong quy trình phát triển và vận hành.

| Nguồn | Tín hiệu có thể quan sát | Câu hỏi cần đặt |
| --- | --- | --- |
| Pull request | Nhiều vòng sửa cùng một lỗi; nhiều file phải đồng bộ. | Điều gì làm thay đổi khó review hoặc dễ bỏ sót? |
| CI/CD | Pipeline lâu, rerun, job lỗi môi trường. | Check nào tạo giá trị và check nào gây nhiễu? |
| Test | Flaky test, test bị quarantine, assertion thiếu rõ ràng. | Nguyên nhân nằm ở code, dữ liệu hay môi trường? |
| Incident | Hotfix lặp lại, thời gian điều tra dài. | Cơ chế nào góp phần tạo hoặc kéo dài sự cố? |
| Telemetry | Độ trễ, lỗi, retry hoặc tài nguyên tăng. | Kịch bản nào bị ảnh hưởng và từ phiên bản nào? |
| Hỗ trợ người dùng | Cùng câu hỏi hoặc lỗi được báo nhiều lần. | Hợp đồng hoặc trải nghiệm nào đang gây nhầm lẫn? |
| Onboarding | Người mới không chạy được test hoặc không biết nơi sửa. | Tri thức nào khó tìm hoặc thiếu xác minh? |
| Bảo mật | Cảnh báo mới, quyền quá rộng, secret bị xử lý sai. | Ranh giới tin cậy nào cần kiểm tra? |
| Vận hành | Thao tác thủ công lặp lại, rollback khó. | Có bước nào dễ tự động hóa hoặc cần làm rõ? |

### 4.1. Dùng nguồn dữ liệu phù hợp với vấn đề

Nếu vấn đề là CI chậm, xem thời gian queue, setup và execution của từng job. Nếu vấn đề là lỗi phân quyền, xem test theo role, log truy cập và phạm vi dữ liệu. Nếu vấn đề là khó thay đổi, xem lịch sử PR, số nơi phải sửa cùng một quy tắc và những lần bỏ sót.

Đừng dùng một metric chung để giải thích mọi vấn đề. **Bằng chứng phải khớp với cơ chế đang điều tra.**

### 4.2. Lắng nghe người thực hiện công việc

Người phát triển, reviewer, QA, support và on-call có thể nhìn thấy các phần khác nhau của cùng một vấn đề.

Hãy hỏi theo tình huống:

- “Lần gần nhất điều này làm bạn phải làm lại là khi nào?”
- “Bạn đã phải tìm thông tin ở đâu?”
- “Bước nào khiến bạn chờ lâu nhất?”
- “Điều gì đã giúp bạn xác định nguyên nhân?”
- “Nếu thay đổi này xảy ra lần nữa, bạn dự đoán cần làm gì?”

Câu hỏi cụ thể thường cho dữ liệu hữu ích hơn câu “bạn thấy code có tốt không?”.

## 5. Mô tả vấn đề bằng một tình huống có thể kiểm chứng

Một bản ghi vấn đề nên giúp người chưa tham gia sự việc hiểu điều gì xảy ra và vì sao đáng xử lý.

Có thể dùng cấu trúc:

> **Khi** [điều kiện hoặc công việc], **nhóm/người dùng phải** [hành động hoặc gặp trở ngại] **vì** [cơ chế đang được quan sát]. Điều đó dẫn đến [tác động đã xảy ra hoặc rủi ro có căn cứ], được hỗ trợ bởi [nguồn bằng chứng]. Chúng ta chưa biết [điều còn chưa xác minh].

Ví dụ yếu:

> “CI quá chậm, cần tối ưu pipeline.”

Ví dụ có thể hành động:

> “Khi gửi PR Java, nhóm phải chờ bộ integration test khởi tạo database và chạy tuần tự trước khi nhận kết quả unit test. Trong 30 ngày gần nhất, thời gian từ lúc job bắt đầu đến kết quả đầu tiên có trung vị 18 phút. Tám PR phải chạy lại do một nhóm test không ổn định. Cần phân tích thời gian từng job và xác minh nguyên nhân test chập chờn trước khi thay đổi thứ tự pipeline.”

Ví dụ thứ hai có phạm vi, thời gian, sự kiện và câu hỏi tiếp theo. Số liệu ở đây là **tình huống minh họa**, không phải số đo của repository hiện tại.

### 5.1. Ghi riêng điều đã biết và điều suy đoán

| Điều đã quan sát | Giả thuyết cần kiểm tra |
| --- | --- |
| Test PaymentRepositoryIT thất bại không ổn định ở CI. | Test có thể chia sẻ database hoặc port. |
| Mỗi lần thêm hạng khách hàng đều sửa ba module. | Ba module có thể đang sở hữu cùng một chính sách. |
| p95 tăng sau một phiên bản deploy. | Truy vấn mới có thể gây N+1. |
| Người mới cần hỏi owner để biết cách rollback. | Runbook có thể thiếu hoặc lỗi thời. |

Giả thuyết là điểm bắt đầu điều tra, không phải kết luận cuối cùng.

## 6. Thu thập bằng chứng có chất lượng

Một vấn đề đáng ưu tiên cần bằng chứng đủ để xác nhận mức ảnh hưởng. Không phải mọi trường hợp cần dashboard hoặc thống kê lớn; một test tái hiện ổn định hay một incident có dữ liệu đầy đủ có thể đủ để bắt đầu.

### 6.1. Các trường nên ghi

- **Thời gian:** khoảng ngày hoặc phiên bản có liên quan.
- **Phạm vi:** module, endpoint, nhóm người dùng hoặc môi trường.
- **Tần suất:** số lần xảy ra trên một khoảng thời gian hoặc số lần thử.
- **Mẫu số:** tổng số PR, request, deploy hoặc giao dịch tương ứng.
- **Tác động:** thời gian làm lại, độ trễ, lỗi, dữ liệu hoặc gián đoạn.
- **Nguồn:** link issue, test, trace, report, PR hoặc incident.
- **Mức tin cậy:** đã xác nhận, có bằng chứng một phần hay mới là giả thuyết.
- **Giới hạn:** dữ liệu thiếu, môi trường khác biệt hoặc yếu tố gây nhiễu.

### 6.2. Bảo vệ dữ liệu và quyền riêng tư

Khi thu thập log hoặc ví dụ production:

- Loại bỏ token, mật khẩu, private key và credential.
- Không đưa dữ liệu cá nhân hoặc payload khách hàng thật vào issue nếu không cần thiết.
- Dùng ID giả lập hoặc dữ liệu đã ẩn danh.
- Chỉ liên kết tới nguồn mà người nhận có quyền truy cập.
- Không mở rộng quyền chỉ để thuận tiện điều tra.

Bằng chứng cần đủ để kiểm chứng, nhưng không cần sao chép dữ liệu nhạy cảm ra khỏi hệ thống có kiểm soát.

### 6.3. Một nguồn dữ liệu chưa chắc đã đủ

Một dashboard có thể cho thấy latency tăng, nhưng không chứng minh nguyên nhân là code. Một PR có nhiều vòng review có thể do yêu cầu thay đổi, không phải thiết kế khó hiểu. Kết hợp nhiều nguồn giúp kiểm tra giả thuyết:

- Metric cho biết hiện tượng.
- Trace hoặc log giúp xác định đường đi.
- PR/commit cho biết thay đổi liên quan.
- Test tái hiện điều kiện cụ thể.
- Phỏng vấn người thực hiện giúp hiểu công việc thực tế.

## 7. Đo chi phí bằng đơn vị rõ ràng

Không cần biến mọi vấn đề thành tiền ngay. Có thể bắt đầu bằng đơn vị dễ xác minh:

- Số lần rerun mỗi tháng.
- Số giờ điều tra incident.
- Số phút từ commit đến kết quả CI đầu tiên.
- Số PR phải sửa bổ sung.
- Số nơi phải cập nhật cùng một quy tắc.
- Số lần thao tác vận hành thủ công.
- Tỷ lệ request lỗi trên tổng request.
- Thời gian khôi phục dịch vụ.

### 7.1. Tính công sức làm lại

Một ước lượng đơn giản:

\[
\text{Effort}_{rework} =
\sum_{i=1}^{n} \text{thời gian xử lý bổ sung của sự kiện } i
\]

Ví dụ, nếu có 6 lần phải sửa bổ sung và mỗi lần ghi nhận 20 phút làm việc thực tế, tổng công sức làm lại là 120 phút. Không cộng toàn bộ thời gian PR mở nếu người phát triển không làm việc trong khoảng chờ đó.

### 7.2. Đo chi phí CI

Có thể tách:

\[
\text{Runner time} =
\text{thời gian chạy ban đầu}
+
\text{thời gian chạy lại}
\]

Đây là chi phí tài nguyên CI, không đồng nghĩa với giờ lao động của developer. Nếu muốn tính công sức con người, cần đo riêng thời gian điều tra, khởi động lại, đọc log hoặc xử lý kết quả.

### 7.3. Ước lượng rủi ro kỳ vọng

Trong trường hợp có dữ liệu xác suất và tác động đủ tin cậy, có thể tham khảo:

\[
\text{Expected loss} =
P(\text{sự kiện}) \times \text{Impact}(\text{sự kiện})
\]

Ví dụ này chỉ có ý nghĩa khi xác suất và tác động được ước lượng có căn cứ, trong cùng bối cảnh. Một sự cố hiếm nhưng có tác động rất lớn vẫn cần đánh giá riêng; không nên dùng một xác suất thiếu cơ sở để hạ ưu tiên.

**Không cộng trực tiếp phút chờ, số lỗi và mức nghiêm trọng** thành một tổng điểm nếu chưa có quy đổi và lý do rõ. Giữ các đơn vị riêng thường trung thực hơn một con số tổng hợp giả chính xác.

## 8. Tránh đếm trùng và phóng đại chi phí

Một incident có thể tạo nhiều dấu vết: ticket support, thời gian on-call, hotfix, rollback và PR sửa lỗi. Nếu cộng toàn bộ mà không xác định phần nào là cùng một công việc, nhóm có thể đếm trùng.

Ví dụ:

- 90 phút điều tra incident.
- 30 phút viết hotfix.
- 20 phút xác minh sau deploy.
- Ticket support ghi nhận cùng 90 phút điều tra.

Nếu ticket support chỉ là bản ghi của 90 phút điều tra, không được cộng thêm lần nữa. Hãy xác định **hoạt động riêng biệt** trước khi tính tổng.

Cũng cần tránh gán toàn bộ sự cố cho một thay đổi khi có nhiều yếu tố, nhân thời gian chờ với tất cả thành viên dù họ không cùng bị chặn, dùng chi phí dự kiến như chi phí đã phát sinh, so sánh hai giai đoạn có số PR hoặc lưu lượng rất khác nhau mà không chuẩn hóa, hoặc dùng một incident hiếm để khẳng định tần suất dài hạn.

Khi chưa đủ dữ liệu, hãy báo khoảng ước lượng và giả định thay vì tạo ra độ chính xác giả.

## 9. Lập đường cơ sở trước khi cải tiến

*Baseline* là dữ liệu mô tả tình trạng trước khi thay đổi. Nếu không có baseline, nhóm khó biết vấn đề đã giảm hay chỉ thay đổi cách đo.

### 9.1. Chọn khoảng thời gian phù hợp

Khoảng đo cần đủ dài để phản ánh công việc bình thường. Với pipeline có nhiều PR mỗi ngày, vài tuần có thể cung cấp tín hiệu ban đầu. Với incident hiếm hoặc migration ít xảy ra, cần xem lịch sử dài hơn hoặc dùng diễn tập và phân tích rủi ro.

Không có một khoảng thời gian đúng cho mọi vấn đề. Ghi rõ ngày bắt đầu, ngày kết thúc, số lượng mẫu và những yếu tố bất thường.

### 9.2. Dùng cả trung vị và phân vị cao

Thời gian trung bình có thể bị một số lần chạy rất lâu kéo lệch. Có thể xem:

- Median (p50): trải nghiệm ở giữa.
- p90 hoặc p95: các trường hợp chậm hơn thường lệ.
- Min/max: phạm vi quan sát, dùng cẩn thận.
- Tỷ lệ thất bại hoặc rerun: số sự kiện trên mẫu số.

Ví dụ, p50 CI là 12 phút nhưng p90 là 38 phút có thể cho thấy một nhóm job hoặc môi trường gây chậm ở một số PR.

### 9.3. So sánh các nhóm tương đồng

So sánh pipeline trước và sau cải tiến cần xem cùng loại runner/cấu hình tài nguyên, số test và phạm vi test, PR có kích thước hoặc loại thay đổi tương đương, lưu lượng request, và các đợt release hay sự cố hạ tầng có thể làm dữ liệu lệch.

Nếu thay đổi cách đo, cần ghi rõ. Không nên tuyên bố cải thiện chỉ vì mẫu số đã thay đổi.

## 10. Tìm nguyên nhân thay vì dừng ở triệu chứng

Một vấn đề có thể có nhiều nguyên nhân góp phần. Phương pháp điều tra cần giúp nhóm kiểm tra giả thuyết, không biến thành trò tìm người chịu lỗi.

### 10.1. Hỏi “vì sao” theo chuỗi có thể kiểm chứng

Ví dụ:

1. Vì sao PR phải chạy lại integration test?
2. Vì test thất bại ngẫu nhiên.
3. Vì nhiều test dùng chung một database schema và dữ liệu.
4. Vì mỗi test không tạo namespace hoặc dữ liệu riêng.
5. Vì test suite được thiết kế trước khi chạy song song và chưa được cập nhật.

Mỗi câu trả lời cần có bằng chứng. Nếu câu thứ ba chưa được xác minh, hãy xem log, test setup hoặc thử chạy cô lập.

### 10.2. Phân biệt nguyên nhân gần và nguyên nhân hệ thống

- **Nguyên nhân gần:** một test đọc dữ liệu do test khác tạo.
- **Nguyên nhân hệ thống:** test suite không có quy tắc cô lập dữ liệu khi chạy song song.
- **Điều kiện góp phần:** runner tăng số worker khiến lỗi dễ xuất hiện hơn.
- **Tác động:** rerun, chờ kết quả và giảm niềm tin vào CI.

Sửa dữ liệu của một test có thể khôi phục nhanh, nhưng nếu toàn bộ suite vẫn chia sẻ trạng thái, lỗi có thể quay lại ở test khác.

### 10.3. Không dùng “5 Whys” như công thức bắt buộc

Có vấn đề cần hai hoặc nhiều nhánh nguyên nhân. Có vấn đề không thể trả lời đủ năm lần. Mục đích là tìm cơ chế có thể tác động, không phải đạt đúng số câu hỏi.

Có thể dùng sơ đồ nhân quả, phân tích luồng dữ liệu, review kiến trúc, trace hoặc thử nghiệm có kiểm soát. Hãy chọn phương pháp giúp kiểm chứng giả thuyết.

## 11. Ưu tiên vấn đề theo tác động và khả năng xử lý

Backlog có thể chứa hàng chục vấn đề. Không thể xử lý tất cả cùng lúc. Một cách đánh giá hữu ích xem xét:

| Yếu tố | Câu hỏi |
| --- | --- |
| **Tác động** | Nếu vấn đề xảy ra, người dùng, dữ liệu hoặc nhóm chịu ảnh hưởng thế nào? |
| **Tần suất** | Vấn đề xuất hiện bao nhiêu lần trong một khoảng thời gian? |
| **Phạm vi** | Bao nhiêu service, người dùng hoặc nhóm công việc liên quan? |
| **Độ chắc chắn** | Bằng chứng đã xác nhận nguyên nhân hay mới là giả thuyết? |
| **Chi phí xử lý** | Cần bao nhiêu công sức, thay đổi và phối hợp? |
| **Rủi ro khi sửa** | Cải tiến có thể làm thay đổi hành vi hoặc gây gián đoạn gì? |
| **Khả năng đảo ngược** | Có thể thử nhỏ, bật/tắt hoặc rollback không? |
| **Thời điểm** | Có thay đổi hoặc release sắp tới tạo cơ hội xử lý không? |

### 11.1. Không ưu tiên chỉ theo tần suất

Một lỗi phân quyền có thể chưa xuất hiện thường xuyên nhưng tác động rất lớn. Một warning format có thể xuất hiện hàng nghìn lần nhưng không tạo chi phí đáng kể.

### 11.2. Không ưu tiên chỉ theo mức dễ sửa

Một việc dễ làm không tự động đáng ưu tiên hơn một rủi ro dữ liệu nghiêm trọng. Ngược lại, một vấn đề lớn nhưng chưa hiểu nguyên nhân có thể cần một nhiệm vụ điều tra nhỏ trước khi cam kết refactor dài.

### 11.3. Chia quyết định thành ba nhóm

- **Xử lý ngay:** rủi ro nghiêm trọng hoặc lỗi đang ảnh hưởng người dùng.
- **Điều tra tiếp:** tác động có thể lớn nhưng bằng chứng/nguyên nhân chưa đủ.
- **Theo dõi hoặc chấp nhận có điều kiện:** tác động thấp, ít lặp lại hoặc chi phí sửa cao hơn lợi ích hiện tại; cần trigger xem lại nếu bối cảnh thay đổi.

Việc hoãn một vấn đề cũng là quyết định. Ghi rõ lý do, người chịu trách nhiệm và điều kiện xem lại.

## 12. So sánh lợi ích và chi phí của một cải tiến

Một cải tiến có thể giảm chi phí lặp lại nhưng tạo chi phí mới. Ví dụ, tập trung logic vào một service có thể giảm bản sao nhưng tăng phụ thuộc runtime và yêu cầu vận hành.

Hãy xem chi phí triển khai và review, rủi ro thay đổi hành vi, chi phí migration hoặc tương thích, chi phí vận hành thành phần mới, lợi ích lặp lại dự kiến, và khả năng quay lại nếu giả thuyết sai.

Một ước lượng đơn giản có thể là:

\[
\text{Net benefit over period} =
\text{observed cost avoided}
-
\text{implementation and operating cost}
\]

Chỉ dùng phép so sánh này khi các thành phần có thể quy đổi về cùng đơn vị và khoảng thời gian. Nếu không, trình bày các yếu tố riêng và giải thích đánh đổi.

**Không cần chứng minh mọi cải tiến sẽ hoàn vốn trong một con số chính xác.** Với rủi ro bảo mật, an toàn dữ liệu hoặc tuân thủ, nghĩa vụ giảm rủi ro có thể quan trọng hơn tiết kiệm thời gian trực tiếp.

## 13. Đề xuất một giả thuyết cải tiến có thể kiểm tra

Một giả thuyết tốt liên kết nguyên nhân với thay đổi và kết quả dự kiến:

> “Nếu [thay đổi cụ thể] xử lý [cơ chế đã xác minh], thì [chỉ số hoặc hành vi] sẽ cải thiện trong [phạm vi/thời gian], trong khi [điều kiện an toàn] vẫn được giữ.”

Ví dụ:

> “Nếu các integration test tạo database/schema riêng thay vì dùng chung dữ liệu mutable, tỷ lệ test phải rerun do xung đột dữ liệu sẽ giảm trong tháng tiếp theo, trong khi toàn bộ integration test bắt buộc vẫn chạy trước merge và không tăng lỗi lọt ra môi trường sau.”

Giả thuyết phải nêu được can thiệp cụ thể, nguyên nhân mà can thiệp nhắm tới, chỉ số hoặc hành vi cần thay đổi, khoảng thời gian hoặc số mẫu đánh giá, guardrail để tránh đánh đổi chất lượng, và cách quay lại nếu kết quả xấu.

## 14. Chọn thay đổi nhỏ và giảm rủi ro thử nghiệm

Không nhất thiết phải viết lại toàn bộ pipeline hoặc kiến trúc để kiểm tra một giả thuyết.

Có thể sửa một nhóm test đang chia sẻ fixture, thêm một contract test cho endpoint có lỗi, tập trung một quy tắc bị sao chép trong phạm vi nhỏ, tự động hóa một thao tác runbook lặp lại, bổ sung metric để xác định nguyên nhân trước khi tối ưu, hoặc thử feature flag/canary cho thay đổi có thể bật tắt.

### 14.1. Phạm vi thử nghiệm

Một thử nghiệm nên giới hạn:

- Module hoặc nhóm test cụ thể.
- Số lượng người dùng/traffic nếu có rollout.
- Thời gian theo dõi.
- Điều kiện thành công.
- Điều kiện dừng hoặc rollback.
- Người chịu trách nhiệm quan sát.

Nếu thử nghiệm không thể đảo ngược, cần kiểm tra backup, migration và phương án phục hồi trước khi bắt đầu.

## 15. Vòng cải tiến liên tục: quan sát, thử, đo và học

Một vòng lặp đơn giản có thể biểu diễn như sau:

~~~text
Quan sát công việc và dữ liệu
          |
          v
Mô tả vấn đề có bằng chứng
          |
          v
Xác định nguyên nhân cần kiểm tra
          |
          v
Ưu tiên và chọn can thiệp nhỏ
          |
          v
Thực hiện trong phạm vi kiểm soát
          |
          v
Đo kết quả và guardrail
          |
          v
Giữ lại / điều chỉnh / hoàn tác
          |
          v
Cập nhật tri thức và tiếp tục quan sát
~~~

Đây là cách vận dụng tư duy PDCA:

- **Plan:** xác định vấn đề, baseline, giả thuyết và tiêu chí.
- **Do:** thử thay đổi trong phạm vi phù hợp.
- **Check:** so sánh dữ liệu và kiểm tra guardrail.
- **Act:** chuẩn hóa thay đổi, điều chỉnh hoặc hoàn tác.

Cải tiến liên tục không có nghĩa lúc nào cũng phải thay code. Đôi khi kết quả tốt nhất là bổ sung metric, làm rõ ownership, cập nhật runbook hoặc quyết định không đầu tư vào một vấn đề có tác động thấp.

## 16. Ví dụ thực hành: CI Java chậm và test phải chạy lại

Giả sử nhóm phát triển một ứng dụng Java và ghi nhận PR thường phải chờ lâu để biết có thể merge hay không.

**Các số liệu dưới đây là giả định phục vụ bài học**, không phải dữ liệu đo từ repository thật.

### 16.1. Tình huống và baseline

Trong 30 ngày, nhóm quan sát:

| Chỉ số | Giá trị minh họa |
| --- | ---: |
| Số PR hoàn tất trong kỳ | 40 |
| Thời gian CI ban đầu trung vị | 18 phút |
| Số PR có ít nhất một lần rerun do test chập chờn | 8 |
| Thời gian một lần rerun trung bình | 18 phút |
| Thời gian điều tra trung bình cho mỗi lần flaky failure | 6 phút |
| Số integration test bắt buộc | Toàn bộ suite |

Từ dữ liệu giả định:

- CI chạy ban đầu: 40 × 18 = 720 phút runner, tương đương 12 giờ runner.
- Rerun: 8 × 18 = 144 phút runner, tương đương 2,4 giờ runner.
- Điều tra thủ công: 8 × 6 = 48 phút công sức con người, nếu mỗi sự kiện thực sự cần đủ 6 phút.

Ba con số này đo **ba loại chi phí khác nhau**. 14,4 giờ runner không phải 14,4 giờ lao động. 48 phút điều tra cũng chưa tính mọi tác động của chuyển ngữ cảnh hoặc chờ review.

### 16.2. Điều cần xác minh

Nhóm chưa nên kết luận “integration test chạy tuần tự là nguyên nhân duy nhất”. Cần phân tích:

- Thời gian queue, setup và execution của từng job.
- Test nào thất bại khi chạy lại mà không đổi code.
- Có test chia sẻ database, port, file hoặc dữ liệu mutable không?
- Unit test có đang chờ môi trường tích hợp dù không cần không?
- Các job độc lập có thể chạy song song an toàn không?
- Test nào thật sự bắt buộc trước merge?

### 16.3. Giả thuyết cải tiến

> “Nếu tách compile, lint và unit test nhanh thành đường phản hồi đầu tiên, đồng thời cô lập dữ liệu cho các integration test đang chập chờn, người viết sẽ nhận tín hiệu ban đầu sớm hơn và nhóm sẽ giảm số lần rerun do xung đột test. Toàn bộ integration test bắt buộc vẫn phải hoàn tất trước merge.”

Can thiệp dự kiến:

1. Đưa compile, format check và unit test nhanh lên đầu pipeline.
2. Chạy static analysis song song nếu không phụ thuộc artifact chưa có.
3. Sửa fixture/database isolation cho test đã xác minh có xung đột.
4. Giữ integration suite đầy đủ như gate bắt buộc trước merge.
5. Ghi nhận thời gian từng giai đoạn và lý do rerun.
6. Không quarantine hàng loạt test chỉ để làm pipeline xanh.

### 16.4. Tiêu chí đánh giá trước khi thử

Có thể đặt tiêu chí giả định:

| Nhóm | Tiêu chí |
| --- | --- |
| Feedback | Thời gian tới kết quả đầu tiên có trung vị không quá 5 phút trên loại PR tương đương. |
| Độ ổn định | Không còn rerun do nhóm nguyên nhân fixture đã xử lý trong mẫu đánh giá. |
| Bằng chứng | Toàn bộ integration test bắt buộc vẫn hoàn tất trước merge. |
| An toàn | Không tăng lỗi lọt qua liên quan tới các luồng được kiểm tra. |
| Chi phí | Runner time và công sức điều tra được đo riêng. |

Đây là **mục tiêu thử nghiệm**, không phải kết quả đã đạt. Nhóm cần xác định cỡ mẫu đủ, theo dõi ít nhất một chu kỳ công việc đại diện và điều chỉnh nếu điều kiện môi trường thay đổi.

### 16.5. Đánh giá sau thử nghiệm

Giả sử kết quả cho thấy thời gian feedback đầu tiên giảm, nhưng tổng thời gian tới khi tất cả gate hoàn tất không đổi. Điều đó vẫn có thể có giá trị vì người phát triển nhận lỗi compile/unit sớm hơn. Tuy nhiên, không nên tuyên bố toàn bộ thời gian PR đã giảm nếu thời gian merge không thay đổi.

Nếu rerun vẫn cao, cần tiếp tục điều tra test flaky. Nếu test bắt đầu chạy song song làm tăng xung đột database, phải cô lập môi trường hoặc điều chỉnh mức song song. **Một thử nghiệm có kết quả không như mong đợi vẫn cung cấp tri thức nếu giả thuyết và dữ liệu được ghi rõ.**

## 17. Ví dụ khác: quy tắc nghiệp vụ bị sao chép

Giả sử một chính sách phí vận chuyển được triển khai riêng trong checkout, báo giá và import đơn hàng.

Một lần thay đổi ngưỡng miễn phí chỉ cập nhật checkout. Báo giá vẫn dùng ngưỡng cũ, khiến cùng một đơn có hai mức phí hiển thị.

### 17.1. Mô tả vấn đề

> “Trong lần thay đổi ngưỡng miễn phí vận chuyển, nhóm cập nhật checkout nhưng bỏ sót báo giá. Hai luồng trả kết quả khác nhau cho cùng hạng khách hàng và tổng tiền. PR liên quan cho thấy quy tắc được định nghĩa ở ba nơi; cần xác nhận các luồng này có cùng hợp đồng trước khi tập trung chính sách.”

### 17.2. Bằng chứng cần thu thập

- Test hoặc dữ liệu tái hiện cùng đầu vào qua hai luồng.
- PR đã thay đổi một bản sao và bỏ sót bản còn lại.
- Hợp đồng nghiệp vụ xác nhận các luồng phải thống nhất.
- Lịch sử thay đổi cho biết tình trạng nhân bản lặp lại hay chỉ một lần.
- Ước lượng phạm vi sửa và rủi ro khi thay đổi.

### 17.3. Không nhảy ngay đến giải pháp tổng quát

Nếu ba luồng có cùng chính sách, một thành phần dùng chung có thể giảm nguy cơ lệch. Nhưng nếu import cần lưu giá trị gốc để audit còn checkout tính theo chính sách hiện tại, cần tách trách nhiệm trước khi gộp.

Chi phí thực tế ở đây là **sai lệch hành vi và công sức sửa bổ sung đã quan sát**. Việc tập trung quy tắc là một giả thuyết cải tiến cần được xác minh bằng test và một thay đổi tiếp theo.

## 18. Chọn metric phù hợp và tránh chạy theo chỉ số

Một chỉ số hữu ích phải gắn với câu hỏi cần trả lời.

| Mục tiêu | Metric có thể dùng | Điều cần tránh |
| --- | --- | --- |
| Giảm thời gian CI | p50/p90 feedback, runner time, queue time. | Chỉ đo thời gian execution. |
| Giảm làm lại | Số PR sửa bổ sung theo nguyên nhân, thời gian rework. | Đếm mọi commit bổ sung như lỗi chất lượng. |
| Giảm lỗi production | Tỷ lệ lỗi theo request hoặc giao dịch, incident theo mức ảnh hưởng. | Chỉ đếm số ticket không có mẫu số. |
| Tăng khả năng thay đổi | Số nơi phải sửa cùng quy tắc, change lead time theo loại việc. | Dùng số file làm thước đo duy nhất. |
| Cải thiện test | Flake rate, rerun rate, lỗi được test phát hiện. | Tăng coverage bằng assertion không có ý nghĩa. |
| Cải thiện vận hành | Thời gian khôi phục, số thao tác thủ công, alert actionable. | Giảm số alert bằng cách tắt cảnh báo quan trọng. |
| Giảm phụ thuộc cá nhân | Số người thực hiện được nhiệm vụ trọng yếu, kết quả diễn tập. | Đếm tên owner trong file mà không kiểm tra năng lực. |

### 18.1. Dùng mẫu số và phân đoạn

Ví dụ “có 8 PR phải rerun” cần đặt cạnh tổng số PR. Nếu tháng sau có 80 PR và 10 rerun, số tuyệt đối tăng nhưng tỷ lệ có thể giảm.

Tương tự, latency cần phân đoạn theo endpoint, kích thước payload hoặc loại người dùng nếu các nhóm có đặc điểm khác nhau. Một số trung bình toàn hệ thống có thể che khuất nhóm chịu ảnh hưởng nghiêm trọng.

### 18.2. Không biến metric thành mục tiêu gây hành vi sai

Nếu nhóm chỉ bị đánh giá theo số PR đóng, họ có thể chia PR quá nhỏ hoặc bỏ qua test. Nếu chỉ theo coverage, họ có thể thêm assertion yếu. Nếu chỉ theo thời gian pipeline, họ có thể bỏ các gate quan trọng.

Metric nên là **tín hiệu hỗ trợ học hỏi**, đi cùng tiêu chí chất lượng và đánh giá định tính.

## 19. Cộng tác khi xác định vấn đề chất lượng

Một vấn đề chất lượng thường đi qua nhiều vai trò:

- Developer hiểu cấu trúc và lịch sử thay đổi.
- QA hiểu cách tái hiện và phạm vi hành vi.
- Product/Business xác nhận quy tắc mong đợi và mức ảnh hưởng.
- SRE/Operations hiểu độ ổn định và chi phí vận hành.
- Security đánh giá ranh giới tin cậy và mức rủi ro.
- Support cung cấp tình huống người dùng gặp phải.

Không nhất thiết mọi vai trò tham gia mọi vấn đề. Hãy mời đúng người để xác nhận phần hợp đồng hoặc dữ liệu mà nhóm kỹ thuật chưa thể tự quyết định.

### 19.1. Tập trung vào hệ thống, không quy lỗi cho cá nhân

Thay vì “developer A làm sai”, hãy mô tả quy tắc nằm ở đâu, review hoặc test nào không phát hiện, yêu cầu có rõ không, quy trình có tạo điều kiện bỏ sót không, và người thực hiện có đủ thông tin cùng quyền cần thiết không.

Cách tiếp cận này không xóa trách nhiệm cá nhân. Nó giúp nhóm tìm điều kiện hệ thống có thể cải thiện để lỗi ít lặp lại hơn.

### 19.2. Chia sẻ bằng chứng và mức chắc chắn

Khi đưa vấn đề vào backlog, hãy nói rõ điều gì đã được xác nhận, điều gì mới là giả thuyết, ai có thể xác minh tiếp và khi nào cần quyết định. Tránh biến một biểu đồ hoặc nhận xét trong review thành kết luận mà chưa kiểm tra.

## 20. Mẫu ghi nhận vấn đề chất lượng

Có thể dùng mẫu ngắn sau trong issue hoặc buổi cải tiến:

~~~markdown
# [Quality problem] <Mô tả tác động>

## Tình huống
Khi <công việc / điều kiện>, <người dùng hoặc nhóm> phải <trở ngại>.

## Hành vi hoặc hiện trạng
- Kết quả thực tế:
- Kết quả mong đợi:
- Phạm vi / phiên bản / môi trường:

## Chi phí hoặc rủi ro
- Đã xảy ra:
- Tần suất và khoảng thời gian:
- Đơn vị đo:
- Rủi ro dự kiến (nếu có):

## Bằng chứng
- PR / commit / test:
- Incident / issue:
- Metric / trace / dashboard:
- Phản hồi người thực hiện:

## Nguyên nhân
- Điều đã xác minh:
- Giả thuyết:
- Điều chưa biết:

## Ưu tiên
- Tác động:
- Phạm vi:
- Độ chắc chắn:
- Chi phí và rủi ro khi sửa:

## Hướng thử nghiệm
- Thay đổi nhỏ:
- Chỉ số / hành vi cần cải thiện:
- Guardrail:
- Thời gian / mẫu đánh giá:
- Điều kiện dừng hoặc rollback:

## Ownership
- Người/nhóm xác minh:
- Người/nhóm thực hiện:
- Ngày xem lại:
~~~

### 20.1. Ví dụ điền ngắn

| Trường | Nội dung minh họa |
| --- | --- |
| Tình huống | PR Java chờ lâu trước khi nhận kết quả kiểm tra đầu tiên. |
| Hiện trạng | CI chạy unit và integration theo thứ tự. |
| Chi phí | p50 18 phút trong mẫu 30 ngày giả định. |
| Bằng chứng | CI job timing và 8 PR rerun trong cùng kỳ giả định. |
| Nguyên nhân đã xác minh | Chưa đủ; cần phân tích test và job dependency. |
| Giả thuyết | Có thể đưa fast checks lên trước và cô lập fixture flaky. |
| Guardrail | Integration test bắt buộc vẫn chạy trước merge. |
| Đánh giá | So sánh p50/p90, rerun rate và lỗi lọt qua. |

Đây là ví dụ cách điền, không phải kết quả đo của dự án thực.

## 21. Những lỗi thường gặp khi xác định vấn đề

### 21.1. Đưa giải pháp vào tên vấn đề

“Cần chuyển sang microservices” là giải pháp đề xuất, chưa phải mô tả vấn đề. Hãy ghi công việc đang bị cản trở và cơ chế gây ra nó trước.

### 21.2. Dùng metric không có bối cảnh

“Pipeline mất 20 phút” cần biết đo từ đâu đến đâu, p50 hay p90, có queue time không và loại PR nào.

### 21.3. Đếm thời gian chờ như giờ lao động

Thời gian lịch có thể kéo dài nhưng không phải toàn bộ là công sức con người. Tách queue, execution, active diagnosis và rework.

### 21.4. Coi tương quan là nguyên nhân

Latency tăng sau deploy không tự chứng minh commit đó là nguyên nhân. So sánh trace, cấu hình, tải và các thay đổi đồng thời.

### 21.5. Chỉ nhìn lỗi đã xảy ra

Một rủi ro bảo mật hoặc mất dữ liệu có thể cần xử lý trước incident. Ghi kịch bản, điều kiện và mức chắc chắn riêng.

### 21.6. Ưu tiên theo độ dễ nhìn thấy

Một cảnh báo đỏ dễ thấy có thể ít ảnh hưởng hơn một lỗi khó tái hiện nhưng tác động tới dữ liệu quan trọng. Cần cân nhắc hậu quả và phạm vi.

### 21.7. Đo quá nhiều thứ rồi không ra quyết định

Một dashboard có hàng trăm metric không tự tạo cải tiến. Chọn một câu hỏi chính, vài chỉ số liên quan và một người chịu trách nhiệm hành động.

### 21.8. Không xem lại giả thuyết

Nếu dữ liệu mới bác bỏ nguyên nhân ban đầu, hãy cập nhật hoặc đóng vấn đề. Không giữ một issue sai chỉ vì đã dành thời gian điều tra.

## 22. Bài tập tự đánh giá

### Tình huống A: class có complexity cao

Một class có cognitive complexity cao nhưng không thay đổi trong sáu tháng, không có lỗi và có test tốt.

**Câu hỏi:** đã đủ bằng chứng để ưu tiên refactor chưa?

**Gợi ý:** chưa. Complexity là tín hiệu. Cần tìm tình huống thay đổi thực tế, khó khăn review, thời gian tìm hiểu hoặc rủi ro cụ thể. Có thể ghi nhận để theo dõi thay vì tạo việc khẩn cấp.

### Tình huống B: pipeline chậm

CI mất 25 phút nhưng 18 phút là thời gian chờ runner. Thời gian test thực tế chỉ 7 phút.

**Câu hỏi:** tối ưu test có xử lý đúng vấn đề không?

**Gợi ý:** chưa chắc. Cần xem năng lực runner, queue, lịch sử tải và phân bổ job. Thay đổi test có thể không cải thiện phần lớn thời gian phản hồi.

### Tình huống C: bug xuất hiện một lần

Một khách hàng báo phí sai nhưng nhóm chưa tái hiện được. Có một thay đổi policy gần đây và nhiều yếu tố cấu hình khác nhau.

**Câu hỏi:** có thể ghi nguyên nhân là commit mới không?

**Gợi ý:** chưa. Ghi sự kiện, dữ liệu đã ẩn danh, phiên bản và giả thuyết; kiểm tra cấu hình, đường dữ liệu và test. Tách sự cố đã xác nhận khỏi nguyên nhân chưa chứng minh.

### Tình huống D: nhiều lần bỏ sót cùng quy tắc

Ba PR liên tiếp phải sửa bổ sung vì chỉ cập nhật một trong hai nơi chứa chính sách.

**Câu hỏi:** nên thu thập dữ liệu gì và giả thuyết nào đáng kiểm tra?

**Gợi ý:** link PR, số bản sao quy tắc, số lần sửa bổ sung, thời gian thực tế và hợp đồng giữa hai nơi. Giả thuyết có thể là cùng một quyết định đang bị nhân bản; xác nhận trước khi tập trung logic.

### Tình huống E: rủi ro chưa có incident

Một service singleton giữ dữ liệu request trong field mutable. Chưa có báo cáo lộ dữ liệu nhưng nhiều request có thể chạy đồng thời.

**Câu hỏi:** có thể coi đây là vấn đề chất lượng không?

**Gợi ý:** có thể ghi nhận rủi ro nếu xác định được cơ chế và điều kiện đồng thời. Không mô tả như một vụ rò rỉ đã xảy ra. Đánh giá phạm vi và ưu tiên theo rủi ro dữ liệu.

### Tình huống F: chỉ số cải thiện sau thay đổi

Sau khi pipeline được chia tầng, p50 kết quả đầu tiên giảm từ 18 xuống 5 phút, nhưng số integration test giảm một nửa.

**Câu hỏi:** có thể kết luận cải tiến thành công không?

**Gợi ý:** chưa. Cần xem các test bị bỏ có được chuyển sang gate khác không, bằng chứng trước merge có còn đủ, và lỗi lọt qua có thay đổi không. Tốc độ tăng không bù cho việc mất kiểm tra bắt buộc.

## 23. Checklist xác định vấn đề chất lượng đang gây chi phí thực tế

- [ ] Vấn đề được mô tả bằng một tình huống công việc hoặc hành vi cụ thể.
- [ ] Đã phân biệt tín hiệu, vấn đề, nguyên nhân giả thuyết và giải pháp.
- [ ] Có người dùng, nhóm hoặc quy trình chịu ảnh hưởng được xác định.
- [ ] Hành vi mong đợi có nguồn từ hợp đồng hoặc yêu cầu đáng tin.
- [ ] Đã ghi thời gian, phạm vi, tần suất và mẫu số phù hợp.
- [ ] Đơn vị đo rõ: phút chờ, giờ làm lại, runner time, tỷ lệ lỗi hoặc tác động khác.
- [ ] Chi phí đã xảy ra được tách khỏi rủi ro dự kiến.
- [ ] Không đếm trùng incident, support, hotfix và thời gian điều tra.
- [ ] Dữ liệu nhạy cảm đã được loại bỏ hoặc bảo vệ đúng quyền.
- [ ] Baseline có khoảng thời gian, cỡ mẫu và giới hạn rõ.
- [ ] Metric được phân đoạn phù hợp, không chỉ dùng một số trung bình.
- [ ] Nguyên nhân được kiểm chứng thay vì suy từ tương quan.
- [ ] Ưu tiên xem cả tác động, tần suất, phạm vi, độ chắc chắn và chi phí sửa.
- [ ] Giải pháp đề xuất có giả thuyết và chỉ số đánh giá.
- [ ] Có guardrail để không giảm chất lượng khác nhằm làm đẹp metric.
- [ ] Thử nghiệm có phạm vi, người chịu trách nhiệm và điều kiện dừng.
- [ ] Kết quả được so sánh với baseline tương đồng.
- [ ] Kết luận chỉ khẳng định điều mà bằng chứng hỗ trợ.
- [ ] Issue được cập nhật hoặc đóng khi giả thuyết bị bác bỏ.
- [ ] Tri thức thu được được chia sẻ trong nguồn phù hợp của dự án.

## 24. Kết luận

**Xác định vấn đề chất lượng đang gây chi phí thực tế** là bước giúp nhóm chọn đúng điều cần cải thiện. Một metric, warning hoặc nhận xét code review có thể chỉ ra nơi nên quan sát; quyết định ưu tiên cần dựa trên tình huống, tác động, tần suất, phạm vi và bằng chứng.

Hãy phân biệt **chi phí đã xảy ra** với **rủi ro dự kiến**, tách thời gian chờ khỏi công sức lao động, tránh đếm trùng và không coi tương quan là nguyên nhân. Khi đã hiểu cơ chế, nhóm có thể chọn một thay đổi nhỏ, đặt tiêu chí thành công cùng guardrail, rồi đo lại trước khi mở rộng.

Trong **CODE_QUALITY_FUNDAMENTALS**, cải thiện liên tục có ý nghĩa khi giúp mã nguồn **đáng tin cậy hơn, dễ hiểu hơn và dễ thay đổi hơn** qua những thay đổi có căn cứ. Thay vì bắt đầu bằng “nên refactor phần nào?”, hãy bắt đầu bằng **“vấn đề nào đang khiến chúng ta hoặc người dùng phải trả chi phí, và bằng chứng nào chứng minh điều đó?”**

