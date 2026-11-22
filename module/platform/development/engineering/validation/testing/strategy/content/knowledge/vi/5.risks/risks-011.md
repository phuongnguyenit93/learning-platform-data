# Trình bày phần rủi ro được chấp nhận và người có thẩm quyền quyết định

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Phân biệt rủi ro được chấp nhận, rủi ro đã xử lý, rủi ro còn tồn tại và rủi ro được chuyển giao.
- Đánh giá rủi ro còn lại sau khi áp dụng biện pháp kiểm soát.
- Trình bày rủi ro bằng thông tin rõ ràng về nguyên nhân, khả năng xảy ra, tác động và phạm vi ảnh hưởng.
- Xác định người sở hữu rủi ro, người có thẩm quyền chấp nhận và các bên cần được tham vấn hoặc thông báo.
- Ghi nhận quyết định chấp nhận rủi ro có căn cứ, giới hạn, thời hạn và điều kiện xem xét lại.
- Đưa rủi ro được chấp nhận vào báo cáo kiểm thử và quyết định phát hành một cách minh bạch.

## 1. Vì sao cần trình bày rủi ro được chấp nhận?

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, kiểm thử cung cấp bằng chứng về chất lượng của sản phẩm và những điều kiện chưa được đáp ứng. Tuy nhiên, không phải mọi rủi ro đều có thể loại bỏ hoàn toàn trước khi phát hành. Có thể còn lỗi ít ảnh hưởng, một tình huống hiếm chưa thể kiểm tra, một phụ thuộc chưa có đủ bằng chứng hoặc một biện pháp giảm thiểu cần thêm thời gian để triển khai.

Khi đó, tổ chức phải quyết định có tiếp tục trong khi rủi ro vẫn còn hay không. Quyết định này cần được đưa ra bởi người có thẩm quyền, dựa trên thông tin đủ rõ về hậu quả và các lựa chọn. Nếu nhóm chỉ ghi “đã chấp nhận rủi ro” mà không nêu ai quyết định, chấp nhận điều gì, trong phạm vi nào và đến khi nào, thì không thể xác minh trách nhiệm hoặc biết khi nào cần xem xét lại.

Trình bày rủi ro được chấp nhận giúp:

- Người ra quyết định hiểu phần chất lượng còn chưa được bảo đảm và tác động có thể xảy ra.
- Nhóm phát triển, kiểm thử, vận hành và nghiệp vụ có cùng nhận thức về rủi ro còn lại.
- Tách biệt bằng chứng kiểm thử với quyết định quản trị: một phép kiểm thử Fail không tự biến thành Pass chỉ vì có người chấp nhận rủi ro.
- Xác định rõ người chịu trách nhiệm theo dõi và hành động nếu tình hình thay đổi.
- Hỗ trợ quyết định phát hành, triển khai theo giai đoạn, giới hạn tính năng hoặc trì hoãn phát hành.
- Tạo hồ sơ để kiểm toán, điều tra sự cố và cải thiện cách quản lý rủi ro trong các vòng sau.

Chấp nhận rủi ro là một quyết định có chủ đích về phần rủi ro còn lại. Nó không phải bằng chứng rằng rủi ro đã biến mất hoặc sản phẩm đã đáp ứng yêu cầu.

## 2. Phân biệt các trạng thái xử lý rủi ro

Rủi ro có thể được xử lý theo nhiều cách. Cần dùng thuật ngữ chính xác để tránh hiểu nhầm trạng thái công việc.

- **Tránh rủi ro (avoid)**: thay đổi kế hoạch, phạm vi hoặc thiết kế để loại bỏ hoạt động gây ra rủi ro. Ví dụ: không đưa một tích hợp chưa sẵn sàng vào đợt phát hành.
- **Giảm thiểu rủi ro (mitigate)**: áp dụng biện pháp làm giảm khả năng xảy ra hoặc giảm tác động. Ví dụ: thêm kiểm tra quyền, retry có giới hạn hoặc giám sát giao dịch lỗi.
- **Chuyển giao hoặc chia sẻ rủi ro (transfer/share)**: phân bổ một phần trách nhiệm hoặc hậu quả cho bên khác thông qua hợp đồng, bảo hiểm hoặc thỏa thuận dịch vụ. Việc chuyển giao không có nghĩa là tổ chức không còn trách nhiệm với người dùng hoặc nghĩa vụ pháp lý của mình.
- **Chấp nhận rủi ro (accept)**: quyết định có chủ đích tiếp tục trong khi rủi ro còn lại được hiểu và nằm trong giới hạn mà người có thẩm quyền cho phép.
- **Theo dõi rủi ro (monitor)**: duy trì quan sát các dấu hiệu, ngưỡng hoặc sự kiện có thể khiến đánh giá thay đổi. Theo dõi thường đi cùng một phương án xử lý đã xác định.

Một rủi ro có thể được giảm thiểu rồi vẫn còn phần dư cần chấp nhận. Ví dụ, bổ sung cảnh báo giúp phát hiện giao dịch treo sớm hơn, nhưng không loại bỏ hoàn toàn khả năng nhà cung cấp thanh toán phản hồi chậm. Khi trình bày, cần mô tả rủi ro ban đầu, biện pháp đã thực hiện và phần rủi ro còn lại sau biện pháp.

### Rủi ro còn lại và rủi ro được chấp nhận

**Rủi ro còn lại (residual risk)** là phần rủi ro vẫn tồn tại sau khi đã áp dụng các biện pháp kiểm soát. Rủi ro còn lại có thể được đề xuất chấp nhận, nhưng chỉ được xem là rủi ro đã được chấp nhận khi người có thẩm quyền thực sự ra quyết định.

Ví dụ:

| Trạng thái | Mô tả |
|---|---|
| Rủi ro ban đầu | Webhook thanh toán có thể đến trễ, khiến trạng thái đơn hàng cập nhật chậm. |
| Biện pháp giảm thiểu | Thêm retry, đối soát định kỳ và cảnh báo giao dịch chờ quá thời hạn. |
| Rủi ro còn lại | Một số giao dịch vẫn có thể cần xử lý thủ công khi nhà cung cấp không gửi lại webhook. |
| Đề xuất | Cho phép phát hành với điều kiện có hàng đợi theo dõi, người trực xử lý và thời hạn đối soát. |
| Quyết định | Người có thẩm quyền chấp nhận hoặc từ chối đề xuất, ghi rõ điều kiện và thời hạn. |

Không được suy ra rằng một rủi ro đã được chấp nhận chỉ vì nó xuất hiện trong báo cáo, đã được thảo luận trong cuộc họp hoặc không có ai phản đối.

## 3. Đánh giá mức rủi ro trước khi đề xuất chấp nhận

Muốn trình bày rủi ro có ý nghĩa, nhóm cần mô tả sự kiện có thể xảy ra và hậu quả của nó trong bối cảnh cụ thể.

### 3.1. Viết phát biểu rủi ro rõ ràng

Một phát biểu rủi ro nên thể hiện mối quan hệ giữa nguyên nhân, sự kiện và tác động. Có thể dùng cấu trúc:

> Do **[nguyên nhân hoặc điều kiện]**, có thể xảy ra **[sự kiện không mong muốn]**, dẫn đến **[tác động đối với người dùng, nghiệp vụ hoặc hệ thống]**.

Ví dụ:

> Do môi trường kiểm thử chưa mô phỏng đầy đủ callback thanh toán đến trễ, có thể tồn tại lỗi xử lý trạng thái khi callback đến sau một lần thử lại, dẫn đến đơn hàng hiển thị trạng thái thanh toán không chính xác.

Cách viết này tốt hơn câu “rủi ro thanh toán” vì nó chỉ rõ điều gì có thể xảy ra và vì sao điều đó quan trọng. Phát biểu rủi ro không nên trộn nguyên nhân với giải pháp hoặc kết luận trước khi có bằng chứng.

### 3.2. Xem xét khả năng xảy ra và tác động

Nhóm có thể đánh giá rủi ro bằng các yếu tố như:

- **Khả năng xảy ra**: tần suất đã quan sát, độ phức tạp của tình huống, mức độ phụ thuộc vào bên thứ ba và các điều kiện kích hoạt.
- **Mức độ tác động**: ảnh hưởng đến người dùng, tài chính, dữ liệu, hoạt động, bảo mật, pháp lý, tuân thủ và uy tín.
- **Phạm vi ảnh hưởng**: số người dùng, giao dịch, dịch vụ, khu vực hoặc quy trình có thể bị tác động.
- **Khả năng phát hiện**: tổ chức có thể nhận biết vấn đề sớm đến đâu và bằng chứng nào cho thấy vấn đề đã xảy ra.
- **Khả năng phục hồi**: có thể hoàn tác, khôi phục dữ liệu, xử lý thủ công hoặc chuyển sang phương án dự phòng không?
- **Thời gian phơi nhiễm**: rủi ro sẽ tồn tại trong bao lâu và có thể phát sinh trong giai đoạn nào?

Ma trận khả năng xảy ra và tác động có thể giúp sắp xếp thứ tự ưu tiên:

| Khả năng xảy ra / Tác động | Thấp | Trung bình | Cao |
|---|---|---|---|
| Thấp | Theo dõi theo quy trình thông thường | Cần đánh giá biện pháp giảm thiểu | Cần người có thẩm quyền xem xét kỹ |
| Trung bình | Xem xét biện pháp kiểm soát phù hợp | Ưu tiên xử lý hoặc có kế hoạch giảm thiểu | Thường cần giảm thiểu và phê duyệt rõ ràng |
| Cao | Cần biện pháp giảm thiểu và theo dõi | Cần ưu tiên xử lý | Có thể vượt giới hạn chấp nhận; cần chuyển cấp xem xét hoặc dừng hoạt động liên quan |

Ma trận là công cụ hỗ trợ thảo luận, không phải công thức tự động quyết định. Một rủi ro có hậu quả nghiêm trọng đối với an toàn, quyền riêng tư, bảo mật hoặc nghĩa vụ pháp lý có thể không được chấp nhận dù khả năng xảy ra được đánh giá thấp. Cần áp dụng chính sách, tiêu chuẩn và quy định có liên quan của tổ chức.

### 3.3. Phân biệt rủi ro vốn có và rủi ro còn lại

- **Rủi ro vốn có (inherent risk)** là mức rủi ro trước khi tính đến các biện pháp kiểm soát.
- **Rủi ro còn lại (residual risk)** là mức rủi ro sau khi các biện pháp kiểm soát đã được triển khai và đánh giá.

Không nên giảm điểm rủi ro chỉ vì biện pháp kiểm soát đã được lên kế hoạch. Chỉ ghi nhận mức giảm khi có bằng chứng cho thấy biện pháp đã được triển khai và hoạt động hiệu quả. Ví dụ, việc viết xong tài liệu hướng dẫn đối soát chưa chứng minh đội vận hành có thể phát hiện và xử lý giao dịch treo đúng thời hạn; cần kiểm tra quy trình, quyền, cảnh báo và khả năng thực hiện.

## 4. Xác định ai sở hữu rủi ro và ai có quyền chấp nhận

Người phát hiện rủi ro, người sở hữu rủi ro và người có quyền chấp nhận rủi ro có thể là những người khác nhau. Phải xác định vai trò theo cơ cấu quản trị và phân quyền thực tế của tổ chức.

### 4.1. Các vai trò thường gặp

- **Người phát hiện hoặc báo cáo**: thành viên kiểm thử, phát triển, vận hành, bảo mật, nghiệp vụ hoặc đối tác phát hiện và cung cấp bằng chứng về rủi ro.
- **Người sở hữu rủi ro (risk owner)**: người chịu trách nhiệm theo dõi rủi ro, phối hợp xây dựng phương án xử lý và báo cáo khi mức rủi ro thay đổi.
- **Người thực hiện biện pháp (action owner)**: người hoặc nhóm chịu trách nhiệm hoàn thành công việc giảm thiểu, chẳng hạn sửa lỗi, bổ sung giám sát hoặc xây dựng phương án khôi phục.
- **Người có thẩm quyền chấp nhận (risk acceptance authority)**: người có quyền quyết định tổ chức có tiếp tục trong khi rủi ro còn lại tồn tại hay không, trong phạm vi phân quyền được giao.
- **Bên tham vấn**: chuyên gia hoặc bộ phận cung cấp đánh giá chuyên môn, ví dụ bảo mật, pháp chế, quyền riêng tư, vận hành, kiến trúc hoặc chủ sở hữu nghiệp vụ.
- **Bên cần được thông báo**: nhóm phát hành, hỗ trợ, quản lý sản phẩm, khách hàng hoặc bên liên quan cần biết quyết định và điều kiện đi kèm.

Một người có thể đảm nhiệm nhiều vai trò nếu chính sách cho phép, nhưng trách nhiệm phải rõ. Người sở hữu rủi ro không mặc nhiên có quyền chấp nhận rủi ro. Người viết báo cáo kiểm thử cũng không tự có quyền chấp nhận rủi ro chỉ vì họ phát hiện vấn đề.

### 4.2. Xác định thẩm quyền theo loại và mức rủi ro

Thẩm quyền thường phụ thuộc vào:

- Mức độ nghiêm trọng và phạm vi ảnh hưởng của rủi ro.
- Loại rủi ro: nghiệp vụ, kỹ thuật, vận hành, bảo mật, quyền riêng tư, pháp lý hoặc tuân thủ.
- Mức độ ảnh hưởng đến khách hàng, dữ liệu hoặc cam kết dịch vụ.
- Ngân sách, quyền hạn và trách nhiệm được giao cho từng vai trò.
- Chính sách quản trị rủi ro, quy trình phát hành và quy định bắt buộc của tổ chức.

Ví dụ minh họa về phân cấp quyết định:

| Phạm vi rủi ro | Vai trò có thể được giao xem xét hoặc quyết định | Lưu ý |
|---|---|---|
| Lỗi giao diện ít ảnh hưởng, có cách khắc phục tạm thời | Chủ sở hữu sản phẩm hoặc quản lý phát hành trong giới hạn được ủy quyền | Cần ghi nhận ảnh hưởng và thời hạn sửa. |
| Rủi ro dữ liệu hoặc luồng nghiệp vụ quan trọng | Chủ sở hữu nghiệp vụ phối hợp với người quản lý dịch vụ hoặc cấp quản lý được ủy quyền | Cần xem xét tác động tới khách hàng và hoạt động. |
| Rủi ro bảo mật hoặc quyền riêng tư | Vai trò có thẩm quyền theo chính sách bảo mật, quyền riêng tư và quản trị rủi ro | Không được dùng phê duyệt nghiệp vụ thông thường để bỏ qua yêu cầu bắt buộc. |
| Rủi ro pháp lý hoặc tuân thủ | Vai trò quản trị hoặc pháp chế có thẩm quyền theo quy định áp dụng | Có thể không có lựa chọn chấp nhận nếu quy định cấm. |
| Rủi ro vượt ngưỡng hoặc ảnh hưởng nhiều dịch vụ | Cấp quản lý hoặc hội đồng được tổ chức giao thẩm quyền | Cần hồ sơ và đánh giá liên chức năng. |

Đây chỉ là mô hình tham khảo. Không thể suy ra chức danh cụ thể có quyền phê duyệt trong mọi tổ chức. Nhóm phải tra cứu ma trận phân quyền, chính sách quản trị rủi ro và quy trình phát hành đang có hiệu lực; nếu chưa rõ, cần chuyển cấp quản lý có trách nhiệm xác định thẩm quyền trước khi ghi nhận quyết định.

### 4.3. Tách biệt ý kiến chuyên môn và quyết định chấp nhận

Chuyên gia bảo mật có thể kết luận một lỗ hổng có tác động cao; nhóm vận hành có thể mô tả khả năng giám sát và khôi phục; chủ sở hữu nghiệp vụ có thể đánh giá ảnh hưởng đến khách hàng. Những ý kiến này là đầu vào quan trọng, nhưng quyết định chấp nhận phải do vai trò có thẩm quyền theo chính sách đưa ra.

Nếu một bộ phận chuyên môn xác định rủi ro vi phạm yêu cầu bắt buộc hoặc chính sách không cho phép ngoại lệ, người phê duyệt phát hành không thể tùy ý biến vấn đề đó thành rủi ro được chấp nhận. Trường hợp này cần xử lý theo quy trình ngoại lệ hoặc tuân thủ tương ứng, nếu có.

## 5. Khi nào có thể xem xét chấp nhận rủi ro?

Một đề xuất chấp nhận rủi ro chỉ nên được xem xét khi tổ chức đã hiểu vấn đề và có đủ thông tin để so sánh các lựa chọn.

Các điều kiện cần xem xét gồm:

1. Rủi ro đã được mô tả cụ thể, có nguyên nhân, sự kiện và tác động rõ ràng.
2. Khả năng xảy ra, phạm vi ảnh hưởng và mức độ nghiêm trọng đã được đánh giá dựa trên bằng chứng hiện có.
3. Các biện pháp tránh hoặc giảm thiểu hợp lý đã được xem xét; lý do chưa thực hiện hoặc chưa thể thực hiện được ghi nhận.
4. Rủi ro còn lại nằm trong giới hạn chấp nhận và thẩm quyền được giao.
5. Không vi phạm nghĩa vụ pháp lý, yêu cầu bảo mật, quyền riêng tư, an toàn hoặc chính sách bắt buộc.
6. Có biện pháp giám sát, phương án dự phòng hoặc xử lý sự cố phù hợp với mức rủi ro.
7. Có người sở hữu rủi ro, người thực hiện hành động tiếp theo và thời hạn xem xét lại.
8. Người có thẩm quyền được cung cấp thông tin và đưa ra quyết định rõ ràng.

Chấp nhận có thể phù hợp khi tác động thấp, khả năng xảy ra thấp, chi phí giảm thiểu không tương xứng hoặc có biện pháp phát hiện và khắc phục đủ hiệu quả. Tuy nhiên, lý do “không còn thời gian” hoặc “muốn phát hành đúng lịch” tự nó không chứng minh rủi ro nằm trong giới hạn chấp nhận. Áp lực thời gian cần được trình bày như một yếu tố trong quyết định, cùng với hậu quả và lựa chọn thay thế.

### Những trường hợp cần dừng hoặc chuyển cấp

Nhóm cần chuyển cấp hoặc từ chối đề xuất chấp nhận khi:

- Rủi ro có thể gây hậu quả nghiêm trọng đến con người, dữ liệu nhạy cảm, tài chính hoặc quyền lợi khách hàng.
- Có dấu hiệu vi phạm luật, quy định, hợp đồng hoặc tiêu chuẩn bắt buộc.
- Chưa biết phạm vi ảnh hưởng hoặc không có đủ bằng chứng để ước lượng rủi ro.
- Không có biện pháp phát hiện, ứng phó hoặc khôi phục phù hợp.
- Người đề xuất không xác định được người có thẩm quyền.
- Rủi ro vượt ngưỡng hoặc giới hạn đã được tổ chức phê duyệt.

Trong những trường hợp này, không nên tự ghi nhận trạng thái “accepted”. Cần nêu rõ điểm chưa đáp ứng, bằng chứng còn thiếu và cấp có trách nhiệm xem xét tiếp.

## 6. Cách trình bày một đề xuất chấp nhận rủi ro

Người ra quyết định cần có một bản tóm tắt ngắn, dễ hiểu và có thể truy ngược đến bằng chứng chi tiết. Một hồ sơ đầy đủ thường bao gồm:

| Trường thông tin | Nội dung cần trình bày |
|---|---|
| Mã rủi ro | Định danh duy nhất để liên kết báo cáo, lỗi, quyết định và hành động. |
| Phát biểu rủi ro | Nguyên nhân, sự kiện có thể xảy ra và tác động. |
| Phạm vi | Tính năng, người dùng, dịch vụ, dữ liệu, phiên bản và môi trường bị ảnh hưởng. |
| Bằng chứng | Kết quả kiểm thử, log, metric, sự cố trước đây, phân tích hoặc giới hạn chưa kiểm tra. |
| Mức rủi ro ban đầu | Đánh giá trước biện pháp kiểm soát, cùng phương pháp và giả định đánh giá. |
| Biện pháp đã áp dụng | Kiểm soát nào đã hoàn thành và bằng chứng cho thấy chúng hoạt động. |
| Rủi ro còn lại | Khả năng và tác động còn tồn tại sau biện pháp. |
| Lựa chọn | Chấp nhận, giảm thiểu thêm, tránh, chuyển giao hoặc trì hoãn phát hành. |
| Lý do đề xuất | Vì sao lựa chọn được đề xuất phù hợp với lợi ích, chi phí và giới hạn của tổ chức. |
| Điều kiện chấp nhận | Giới hạn sử dụng, tính năng tắt, người giám sát, quy trình thủ công hoặc biện pháp bổ sung. |
| Người sở hữu | Người chịu trách nhiệm theo dõi rủi ro và cập nhật trạng thái. |
| Người quyết định | Vai trò và danh tính của người có thẩm quyền theo quy trình nội bộ. |
| Thời hạn | Thời điểm hết hiệu lực hoặc ngày phải xem xét lại. |
| Điều kiện kích hoạt xem xét | Chỉ số, sự cố, thay đổi hệ thống hoặc sự kiện khiến quyết định cần được đánh giá lại. |
| Trạng thái quyết định | Đề xuất, đang xem xét, chấp nhận, từ chối, hết hạn hoặc đã đóng. |

### 6.1. Trình bày tác động bằng ngôn ngữ nghiệp vụ

Người ra quyết định có thể không trực tiếp đọc log hoặc mã nguồn. Vì vậy, hãy diễn giải tác động bằng ngôn ngữ gắn với hoạt động thực tế.

Ví dụ:

- Kỹ thuật: “Webhook có thể bị retry sau HTTP 5xx và consumer chưa có deduplication key.”
- Nghiệp vụ: “Trong một số trường hợp nhà cung cấp gửi lại thông báo thanh toán, hệ thống có thể ghi nhận cùng một giao dịch nhiều lần, dẫn đến sai lệch trạng thái đơn hàng hoặc phải đối soát thủ công.”

Giữ lại chi tiết kỹ thuật trong phần bằng chứng, nhưng phần tóm tắt cần giúp người đọc hiểu ai có thể bị ảnh hưởng, điều gì có thể xảy ra và hậu quả là gì.

### 6.2. Nêu rõ lựa chọn thay thế

Không nên chỉ trình bày một phương án “chấp nhận”. Hãy mô tả các lựa chọn thực tế và hệ quả chính:

- Phát hành theo kế hoạch với biện pháp giám sát bổ sung.
- Giới hạn người dùng, khu vực hoặc chức năng để thu hẹp phạm vi phơi nhiễm.
- Tắt tạm tính năng có rủi ro bằng feature flag.
- Trì hoãn phát hành để hoàn thành biện pháp giảm thiểu.
- Triển khai theo giai đoạn với tiêu chí dừng và quay lui rõ ràng.

Người có thẩm quyền cần biết chi phí, thời gian và rủi ro của từng lựa chọn. Nếu có thể giảm đáng kể tác động bằng cách giới hạn phạm vi, lựa chọn đó nên được đánh giá trước khi chấp nhận rủi ro rộng hơn.

## 7. Ghi nhận quyết định và điều kiện chấp nhận

Quyết định chấp nhận cần được lưu bằng văn bản hoặc hệ thống quản lý có thể truy cập theo quyền. Trao đổi miệng hoặc tin nhắn rời rạc không đủ để duy trì lịch sử quyết định nếu không được ghi nhận vào hồ sơ chính thức.

Một quyết định nên ghi rõ:

- **Kết quả**: chấp nhận, từ chối hoặc yêu cầu bổ sung biện pháp.
- **Phạm vi**: đúng phiên bản, môi trường, tính năng, nhóm người dùng hoặc khoảng thời gian được xem xét.
- **Lý do**: căn cứ và đánh giá của người ra quyết định.
- **Điều kiện**: biện pháp bắt buộc trước hoặc sau phát hành.
- **Người chịu trách nhiệm**: risk owner và action owner.
- **Thời hạn hiệu lực**: ngày hết hạn hoặc mốc đánh giá lại.
- **Điều kiện thu hồi**: dấu hiệu hoặc sự kiện khiến quyết định không còn hợp lệ.
- **Dấu vết phê duyệt**: người quyết định, vai trò, thời điểm và liên kết đến bằng chứng.

Chấp nhận rủi ro nên có thời hạn hoặc sự kiện xem xét lại, đặc biệt khi quyết định chỉ nhằm cho phép một đợt phát hành cụ thể. Không nên biến một ngoại lệ tạm thời thành miễn trừ vô thời hạn.

### Theo dõi điều kiện sau khi chấp nhận

Nếu quyết định yêu cầu giám sát tỷ lệ giao dịch lỗi, nhóm vận hành cần biết ngưỡng cảnh báo, người nhận cảnh báo và hành động khi ngưỡng bị vượt. Nếu quyết định yêu cầu xử lý thủ công, cần có người trực, hướng dẫn thao tác và cách xác nhận giao dịch đã được xử lý. Nếu quyết định cho phép phát hành theo giai đoạn, cần có tiêu chí mở rộng hoặc dừng rõ ràng.

Khi một điều kiện không được đáp ứng, rủi ro phải được xem xét lại ngay. Việc người có thẩm quyền từng chấp nhận rủi ro không có nghĩa là tổ chức được tiếp tục bỏ qua các điều kiện đi kèm.

## 8. Ví dụ xuyên suốt: rủi ro callback thanh toán đến trễ

Giả sử kiểm thử phát hiện một số callback thanh toán đến sau thời hạn chờ của ứng dụng. Ứng dụng giữ đơn hàng ở trạng thái chờ và có một tác vụ đối soát chạy định kỳ. Nhóm chưa thể loại bỏ hoàn toàn tình huống này trước ngày phát hành.

### 8.1. Phát biểu và đánh giá rủi ro

> Do nhà cung cấp thanh toán có thể gửi callback muộn hoặc không gửi lại sau lỗi mạng, một số đơn hàng có thể tiếp tục ở trạng thái chờ dù giao dịch đã hoàn tất, dẫn đến người mua không nhận được xác nhận đúng lúc và đội vận hành phải đối soát thủ công.

Nhóm ghi nhận bằng chứng: các lần chạy sandbox có callback chậm, log thời điểm tiếp nhận, trạng thái đơn hàng và kết quả của tác vụ đối soát. Nhóm cũng nêu rõ sandbox chưa chứng minh được tần suất thực tế của vấn đề trong production.

### 8.2. Biện pháp giảm thiểu

- Lưu mã giao dịch nhà cung cấp và mã đơn hàng để đối soát.
- Chạy tác vụ truy vấn trạng thái cho các đơn hàng chờ quá thời hạn.
- Tạo cảnh báo khi số lượng hoặc tuổi của giao dịch chờ vượt ngưỡng.
- Cung cấp quy trình xử lý thủ công có phân quyền và lưu dấu vết.
- Theo dõi tỷ lệ callback đến trễ sau phát hành.

Sau khi kiểm thử các biện pháp, nhóm đánh giá lại rủi ro còn lại. Ví dụ, một số trường hợp hiếm vẫn có thể cần xử lý thủ công khi nhà cung cấp không trả trạng thái cuối cùng.

### 8.3. Đề xuất và quyết định

Đề xuất có thể gồm:

- Phạm vi chấp nhận: chỉ áp dụng cho phiên bản phát hành và hành trình thanh toán đã mô tả.
- Điều kiện: tác vụ đối soát và cảnh báo phải hoạt động trước khi mở tính năng; có người phụ trách xử lý giao dịch chờ.
- Theo dõi: đo số giao dịch chờ, tuổi giao dịch và thời gian từ khi nhà cung cấp hoàn tất đến khi ứng dụng cập nhật trạng thái.
- Ngưỡng xem xét lại: nếu số giao dịch chờ hoặc tuổi giao dịch vượt ngưỡng đã thống nhất, tạm dừng mở rộng phát hành và điều tra.
- Thời hạn: xem xét lại sau giai đoạn phát hành ban đầu hoặc khi có thay đổi hợp đồng nhà cung cấp.

Người sở hữu rủi ro trình bày hồ sơ và bằng chứng. Các bên nghiệp vụ, kỹ thuật, vận hành và chuyên môn liên quan đưa ra ý kiến. Người có thẩm quyền theo ma trận phân quyền quyết định chấp nhận, yêu cầu giảm thiểu thêm hoặc trì hoãn phát hành. Tên chức danh và ngưỡng phê duyệt phải theo quy định thực tế của tổ chức, không suy ra từ ví dụ này.

Nếu đề xuất được chấp nhận, báo cáo kiểm thử vẫn ghi rõ các ca callback trễ chưa đạt hoặc chưa thể xác minh, cùng quyết định và điều kiện được phê duyệt. Trạng thái kiểm thử không thay đổi chỉ vì rủi ro được chấp nhận.

## 9. Liên kết chấp nhận rủi ro với quyết định phát hành

Báo cáo kiểm thử nên có một phần riêng cho rủi ro còn lại và quyết định tương ứng. Phần này giúp người đọc phân biệt:

- Các yêu cầu đã được kiểm tra và đạt.
- Các yêu cầu không đạt hoặc chưa có đủ bằng chứng.
- Các rủi ro còn lại đã được người có thẩm quyền chấp nhận.
- Các rủi ro chưa được chấp nhận hoặc đang chờ quyết định.
- Các điều kiện phải hoàn thành trước hoặc sau phát hành.

Một bảng tóm tắt có thể dùng cấu trúc:

| Mã rủi ro | Rủi ro còn lại | Mức độ | Quyết định | Người có thẩm quyền | Điều kiện và hạn xem xét |
|---|---|---|---|---|---|
| `RISK-014` | Một số callback thanh toán có thể đến trễ | Trung bình (minh họa) | Chấp nhận có điều kiện | Vai trò được ủy quyền theo chính sách | Đối soát hoạt động; theo dõi giao dịch chờ; xem xét lại sau giai đoạn đầu |
| `RISK-018` | Một luồng báo cáo ít dùng chưa có bằng chứng hiệu năng đầy đủ | Thấp (minh họa) | Đang chờ quyết định | Chưa xác định | Cần hoàn thành đo tải hoặc chuyển cấp xác định thẩm quyền |

Trước phát hành, người chịu trách nhiệm cần xác nhận:

1. Mọi rủi ro vượt ngưỡng đã được xử lý hoặc chuyển đến đúng cấp có thẩm quyền.
2. Các quyết định chấp nhận có hồ sơ, phạm vi và điều kiện rõ ràng.
3. Các điều kiện bắt buộc trước phát hành đã được hoàn thành và có bằng chứng.
4. Các rủi ro chưa được quyết định không bị xem là mặc nhiên chấp nhận.
5. Kế hoạch theo dõi, xử lý sự cố và xem xét lại đã có người nhận trách nhiệm.

Việc chấp nhận một rủi ro cụ thể không đồng nghĩa chấp nhận toàn bộ rủi ro của bản phát hành. Mỗi rủi ro cần được đánh giá theo phạm vi và thẩm quyền tương ứng.

## 10. Những sai lầm thường gặp

- **Không xác định người quyết định**: báo cáo ghi “đã được chấp nhận” nhưng không có vai trò hoặc dấu vết phê duyệt. Cần liên kết quyết định với người có thẩm quyền theo chính sách.
- **Nhầm người sở hữu với người phê duyệt**: người theo dõi rủi ro tự ghi nhận chấp nhận dù không có quyền. Cần tách rõ trách nhiệm quản lý và quyền quyết định.
- **Chấp nhận rủi ro mà không nêu tác động**: mô tả chỉ có thuật ngữ kỹ thuật, không nói ảnh hưởng đến ai. Cần diễn giải hậu quả bằng ngôn ngữ nghiệp vụ.
- **Đánh giá rủi ro bằng cảm tính**: chỉ ghi thấp hoặc cao mà không có căn cứ. Cần nêu dữ liệu, giả định, phạm vi và phương pháp đánh giá.
- **Coi kế hoạch giảm thiểu là kiểm soát đã hoàn thành**: điểm rủi ro được giảm dù biện pháp chưa triển khai. Chỉ đánh giá lại sau khi có bằng chứng hoạt động.
- **Chấp nhận vô thời hạn**: ngoại lệ không có ngày xem xét lại và tồn tại qua nhiều phiên bản. Cần giới hạn thời gian hoặc sự kiện hết hiệu lực.
- **Không có điều kiện giám sát**: rủi ro được chấp nhận nhưng không ai theo dõi dấu hiệu xấu đi. Cần xác định chỉ số, ngưỡng, người nhận cảnh báo và hành động.
- **Dùng phê duyệt để bỏ qua yêu cầu bắt buộc**: rủi ro liên quan đến luật, bảo mật hoặc tuân thủ được xem như lỗi sản phẩm thông thường. Cần chuyển đến vai trò chuyên môn và quy trình ngoại lệ phù hợp.
- **Đổi trạng thái kiểm thử sau khi chấp nhận rủi ro**: một ca Fail bị chuyển thành Pass vì có phê duyệt. Cần giữ nguyên kết quả thực thi và ghi riêng quyết định quản trị.
- **Không cập nhật khi điều kiện thay đổi**: phạm vi người dùng, phiên bản hoặc phụ thuộc thay đổi nhưng quyết định cũ vẫn được áp dụng. Cần xem xét lại khi có sự kiện kích hoạt.

## 11. Quy trình trình bày và quyết định rủi ro

Nhóm có thể áp dụng trình tự sau:

1. **Ghi nhận rủi ro**: mô tả nguyên nhân, sự kiện, tác động, phạm vi và bằng chứng.
2. **Đánh giá rủi ro ban đầu**: xem xét khả năng xảy ra, mức độ tác động, phạm vi, khả năng phát hiện và phục hồi.
3. **Xem xét phương án xử lý**: tránh, giảm thiểu, chuyển giao/chia sẻ hoặc chấp nhận; xác định chi phí và giới hạn.
4. **Thực hiện và kiểm chứng kiểm soát**: chỉ tính các biện pháp đã triển khai và có bằng chứng.
5. **Đánh giá rủi ro còn lại**: nêu rõ phần vẫn có thể xảy ra sau kiểm soát.
6. **Xác định thẩm quyền**: tra cứu vai trò được ủy quyền theo loại và mức rủi ro; chuyển cấp nếu vượt quyền.
7. **Trình bày đề xuất**: cung cấp tác động nghiệp vụ, bằng chứng, lựa chọn thay thế, điều kiện và thời hạn.
8. **Ghi nhận quyết định**: lưu người quyết định, vai trò, thời điểm, phạm vi, lý do, điều kiện và trạng thái.
9. **Theo dõi và xem xét lại**: kiểm tra điều kiện chấp nhận, cập nhật khi có thay đổi hoặc sự cố và đóng rủi ro khi không còn tồn tại.

## 12. Tự kiểm tra

Trước khi đưa rủi ro vào báo cáo kiểm thử hoặc đề nghị phát hành, hãy tự hỏi:

- Rủi ro có được mô tả bằng nguyên nhân, sự kiện và tác động cụ thể không?
- Bằng chứng nào hỗ trợ đánh giá khả năng xảy ra và mức độ ảnh hưởng?
- Biện pháp kiểm soát nào đã thực sự triển khai và được kiểm chứng?
- Rủi ro còn lại là gì và nằm trong phạm vi nào?
- Có lựa chọn giảm thiểu, giới hạn phạm vi hoặc trì hoãn nào khác không?
- Ai là người sở hữu rủi ro và ai có thẩm quyền chấp nhận theo chính sách?
- Có yêu cầu bắt buộc nào khiến rủi ro không thể được chấp nhận không?
- Quyết định có ghi rõ lý do, điều kiện, thời hạn và dấu vết phê duyệt không?
- Ai theo dõi rủi ro và điều kiện nào sẽ kích hoạt xem xét lại hoặc dừng phát hành?
- Kết quả kiểm thử có được giữ nguyên, tách biệt với quyết định chấp nhận rủi ro không?

## Kết luận

Rủi ro được chấp nhận là phần rủi ro còn lại mà tổ chức quyết định tiếp tục chịu trong một phạm vi và điều kiện xác định. Để quyết định có trách nhiệm, nhóm phải trình bày rõ nguyên nhân, tác động, bằng chứng, biện pháp đã áp dụng và mức rủi ro còn lại; đồng thời xác định người sở hữu, người có thẩm quyền quyết định, thời hạn và điều kiện xem xét lại. Việc ghi nhận minh bạch giúp quyết định phát hành phản ánh đúng chất lượng đã kiểm chứng và những giới hạn mà tổ chức đã chủ động chấp nhận.
