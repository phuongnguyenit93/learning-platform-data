# Vì sao một điểm số không thể mô tả toàn bộ chất lượng?

Một công cụ phân tích thông báo dự án đạt **86/100 điểm chất lượng mã nguồn**. Con số này có thể hữu ích để theo dõi xu hướng, nhưng chưa trả lời được câu hỏi quan trọng hơn: **mã có đủ an toàn, đúng đắn và dễ thay đổi cho mục đích sử dụng hiện tại hay không?** Một ứng dụng có cấu trúc rõ ràng, chạy nhanh và nhiều bài kiểm thử vẫn có thể để lộ dữ liệu vì một lỗi phân quyền.

Trong phần nhập môn của module **CODE_QUALITY_FUNDAMENTALS** (Code Quality Fundamentals), chúng ta sẽ tìm hiểu vì sao chất lượng cần được xem xét qua nhiều khía cạnh, một điểm số tổng hợp đã làm mất những thông tin nào và cách sử dụng số liệu để đưa ra quyết định kỹ thuật.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao chất lượng phần mềm và chất lượng mã nguồn là các khái niệm **đa chiều**, phụ thuộc vào mục đích và bối cảnh.
- Phân biệt **chỉ số đo lường**, **điểm tổng hợp** và **điều kiện bắt buộc** khi đánh giá chất lượng.
- Nhận diện những rủi ro bị che khuất bởi điểm trung bình, tỷ lệ bao phủ kiểm thử hoặc số lượng cảnh báo của công cụ.
- Lập bảng đánh giá ngắn gọn gồm nhiều khía cạnh, bằng chứng và mức độ ưu tiên xử lý.

## 1. Chất lượng không phải một đặc tính duy nhất

Chất lượng mã nguồn liên quan đến việc mã **thực hiện đúng yêu cầu**, **không tạo rủi ro không chấp nhận được** và **có thể được hiểu, kiểm tra, sửa đổi một cách bền vững**. Khi xét một hệ thống đang hoạt động, ta còn cần bằng chứng từ hành vi thực tế như độ trễ, tỷ lệ lỗi và khả năng phục hồi. Không thể quan sát tất cả những điều này chỉ bằng cách đọc mã hoặc chạy một công cụ phân tích tĩnh.

| Khía cạnh | Câu hỏi cần trả lời | Bằng chứng thường dùng |
| --- | --- | --- |
| Tính đúng đắn | Hệ thống có làm đúng yêu cầu, kể cả trường hợp biên? | Kiểm thử theo yêu cầu, kiểm thử tích hợp, đối chiếu kết quả |
| Bảo mật | Người dùng có chỉ truy cập được dữ liệu và thao tác được phép? | Kiểm thử phân quyền, rà soát luồng dữ liệu, phân tích lỗ hổng |
| Độ tin cậy | Hệ thống xử lý lỗi, thử lại và sự cố như thế nào? | Kiểm thử lỗi, kiểm thử phục hồi, tỷ lệ lỗi thực tế |
| Khả năng bảo trì | Người khác có thể hiểu và thay đổi mã với rủi ro hợp lý? | Code review, độ phức tạp, mức độ phụ thuộc, lịch sử thay đổi |
| Khả năng kiểm thử | Có thể kiểm tra hành vi quan trọng một cách ổn định? | Thiết kế kiểm thử, kiểm thử tự động, mức độ cô lập phụ thuộc |
| Hiệu năng | Hệ thống có đáp ứng mục tiêu về thời gian và tài nguyên? | Độ trễ p95, thông lượng, bộ nhớ dưới tải đại diện |

Các khía cạnh này **có liên quan nhưng không thay thế được nhau**. Mã ngắn gọn không tự động bảo mật; nhiều bài kiểm thử không tự động chứng minh đúng yêu cầu; hiệu năng tốt không bù được cho việc tính tiền hai lần.

Giá trị của mỗi khía cạnh còn tùy bối cảnh. Với hệ thống thanh toán, tính đúng đắn và khả năng xử lý giao dịch lặp lại có thể là điều kiện không được vi phạm. Với công cụ nội bộ phục vụ vài người, một số tối ưu hiệu năng có thể ít cấp thiết hơn sự rõ ràng và dễ bảo trì. Vì vậy, muốn đánh giá chất lượng cần biết **hệ thống dùng để làm gì, hậu quả khi lỗi xảy ra là gì và mức độ chấp nhận rủi ro ra sao**.

## 2. Điểm tổng hợp che giấu điều gì?

Giả sử một hệ thống chấm điểm bằng trung bình có trọng số. Ví dụ dưới đây hoàn toàn mang tính minh họa; các mức điểm và trọng số không phải chuẩn chung của ngành.

| Khía cạnh | Trọng số | Điểm thành phần (0–100) | Đóng góp |
| --- | ---: | ---: | ---: |
| Tính đúng đắn | 40% | 95 | 38,0 |
| Bảo mật | 10% | 30 | 3,0 |
| Khả năng bảo trì | 25% | 90 | 22,5 |
| Hiệu năng | 15% | 92 | 13,8 |
| Khả năng kiểm thử | 10% | 90 | 9,0 |
| **Tổng** | **100%** | | **86,3/100** |

Công thức tính:

\[
S = \sum_{i=1}^{n} w_i s_i,\qquad \sum_{i=1}^{n}w_i=1
\]

Trong đó `s_i` là điểm của từng khía cạnh, còn `w_i` là trọng số tương ứng. Kết quả **86,3/100** trông khá tốt, nhưng điểm bảo mật chỉ **30/100**. Nếu tồn tại lỗi cho phép người dùng đọc tài liệu của người khác, đây có thể là lý do phải **dừng phát hành**, bất kể điểm tổng hợp cao bao nhiêu.

Điểm tổng hợp làm mất ít nhất bốn loại thông tin:

1. **Điểm yếu nghiêm trọng:** điểm mạnh ở một mặt có thể bù số học cho điểm yếu ở mặt khác, dù rủi ro thực tế không thể bù như vậy.
2. **Nguồn gốc và độ tin cậy của phép đo:** số liệu có thể đến từ bài kiểm thử thiếu tình huống, dữ liệu tải không đại diện hoặc quy tắc phân tích tĩnh chưa phù hợp.
3. **Mức độ ưu tiên theo bối cảnh:** nếu đổi trọng số thành đúng đắn 30%, bảo mật 30%, bảo trì 20%, hiệu năng 10% và kiểm thử 10%, cùng hệ thống ví dụ chỉ còn **73,7/100**; mã không hề thay đổi.
4. **Xu hướng và phân bố:** hai nhóm cùng đạt 85 điểm có thể khác hẳn nhau: một nhóm ổn định ở mọi khía cạnh, nhóm kia rất tốt ở phần lớn tiêu chí nhưng có một rủi ro đặc biệt nghiêm trọng.

Vì vậy, **điểm số tổng hợp là một bản tóm tắt có mất thông tin**, không phải chứng nhận hệ thống đã đạt chất lượng. Cần luôn nhìn được các điểm thành phần, cách đo, trọng số và vấn đề còn tồn tại.

## 3. Ví dụ Java: mã đơn giản vẫn có thể sai nghiêm trọng

Xét chức năng xem tài liệu. Yêu cầu nghiệp vụ giả định là: *chỉ chủ sở hữu có tài khoản đang hoạt động mới được xem tài liệu*. Đoạn mã dưới đây trông đơn giản và dễ đọc:

```java
boolean canView(User user, Document document) {
    return user != null && user.isActive();
}
```

Hàm có ít nhánh, thực thi nhanh và có thể đạt 100% bao phủ dòng lệnh với các bài kiểm thử cho người dùng đang hoạt động và đã bị vô hiệu hóa. Tuy nhiên, tham số `document` chưa hề được sử dụng. Một người dùng đang hoạt động có thể xem **mọi tài liệu**, kể cả tài liệu không thuộc quyền sở hữu của mình.

Với **quy tắc chỉ chủ sở hữu được xem** trong ví dụ này, một bản sửa có thể là:

```java
boolean canView(User user, Document document) {
    return user != null
        && document != null
        && user.isActive()
        && user.getId() != null
        && user.getId().equals(document.getOwnerId());
}
```

Bộ kiểm thử phải xuất phát từ yêu cầu và rủi ro, chẳng hạn:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Người dùng đang hoạt động xem tài liệu của chính mình | Cho phép |
| Người dùng đang hoạt động xem tài liệu của người khác | Từ chối |
| Chủ sở hữu có tài khoản bị vô hiệu hóa | Từ chối |
| Người dùng hoặc tài liệu là `null` | Từ chối |

Đây là ví dụ tối giản về kiểm tra quyền sở hữu. Một hệ thống thực tế có thể cần chính sách vai trò, chia sẻ tài liệu hoặc phân quyền ở nhiều tầng. Điểm chính là: **độ phức tạp thấp, mã dễ đọc, tốc độ cao và tỷ lệ bao phủ cao vẫn không thay thế được kiểm thử đúng tình huống bảo mật**.

## 4. Vì sao từng chỉ số riêng lẻ cũng có giới hạn?

Chỉ số rất hữu ích khi trả lời **đúng câu hỏi mà nó đo**. Vấn đề xuất hiện khi diễn giải một chỉ số thành tuyên bố về toàn bộ chất lượng.

| Chỉ số | Cho biết điều gì | Không tự chứng minh được điều gì |
| --- | --- | --- |
| Line coverage | Tỷ lệ dòng mã được thực thi khi chạy kiểm thử | Các lời khẳng định trong test đúng và đã xét đủ tình huống nghiệp vụ |
| Số bài kiểm thử thành công | Các kịch bản đã viết đang qua kiểm tra | Các kịch bản còn thiếu cũng đúng |
| Độ phức tạp của hàm | Một dấu hiệu về mức khó hiểu hoặc khó kiểm tra luồng điều khiển | Hàm có làm đúng yêu cầu hay bảo mật hay không |
| Số cảnh báo phân tích tĩnh | Những mẫu rủi ro mà bộ quy tắc phát hiện được | Không còn lỗi khác, hoặc mọi cảnh báo đều nghiêm trọng như nhau |
| Số lỗi được báo cáo | Số vấn đề đã được phát hiện và ghi nhận | Tổng số lỗi thực tế; dự án ít lỗi báo cáo có thể đơn giản là ít được kiểm thử |
| Độ trễ p95 | 95% số lần đo có độ trễ không vượt giá trị đó trong tập dữ liệu đo | Hiệu năng ở mọi loại tải, thiết bị hay thời điểm |

Ví dụ, **90% line coverage** có thể tốt hơn 40% trong cùng điều kiện, nhưng không có nghĩa xác suất hệ thống đúng là 90%. Tương tự, **không phát hiện lỗ hổng** nghĩa là công cụ và quy trình hiện tại chưa tìm thấy lỗ hổng, chứ không chứng minh lỗ hổng không tồn tại.

Một số chỉ số còn có thể xung đột. Tách một hàm lớn thành nhiều hàm nhỏ thường giúp dễ hiểu hơn, nhưng nếu tách quá mức sẽ tạo thêm tầng gián tiếp và gây khó theo dõi. Tối ưu để giảm thời gian đáp ứng có thể khiến logic khó bảo trì hơn. Người đánh giá cần hiểu **đánh đổi** thay vì tối đa hóa mọi con số.

## 5. Cách đánh giá có ích hơn cho quyết định kỹ thuật

Một cách thực tế là dùng **bảng đánh giá đa chiều (scorecard)**, kết hợp điều kiện bắt buộc với những chỉ số có thể cải thiện dần.

**Bước 1 — Xác định mục đích và rủi ro.** Hệ thống phục vụ ai? Điều gì xảy ra nếu sai? Với tài liệu riêng tư, lỗi truy cập trái phép là rủi ro trọng yếu; với xử lý đơn hàng, tính đúng đắn và việc chống xử lý trùng có thể cần ưu tiên.

**Bước 2 — Đặt điều kiện bắt buộc (quality gates).** Một số vấn đề phải được giải quyết trước khi phát hành, không phụ thuộc điểm trung bình. Ví dụ: không còn lỗi phân quyền nghiêm trọng đã xác nhận, các luồng nghiệp vụ trọng yếu vượt qua kiểm thử và yêu cầu hiệu năng đã cam kết được kiểm chứng. Điều kiện phải phù hợp bối cảnh và được thống nhất trước.

**Bước 3 — Thu thập bằng chứng theo từng khía cạnh.** Kết hợp code review, kiểm thử theo yêu cầu, phân tích tĩnh, đánh giá bảo mật và đo lường vận hành khi cần. Ghi rõ môi trường, phạm vi và thời điểm đo để tránh so sánh lệch.

**Bước 4 — Ghi nhận cả điểm mạnh lẫn rủi ro tồn đọng.** Ví dụ bảng dưới đây dùng dữ liệu giả định cho chức năng xem tài liệu:

| Khía cạnh | Bằng chứng | Nhận định / Hành động |
| --- | --- | --- |
| Đúng chức năng | 24/24 bài kiểm thử hiện có vượt qua | Bổ sung kiểm thử truy cập chéo người dùng |
| Bảo mật | Người dùng B xem được tài liệu riêng của A | **Chặn phát hành**, sửa kiểm tra quyền và viết regression test |
| Khả năng bảo trì | Hàm ngắn, dễ đọc; ít nhánh | Đạt ở phạm vi đoạn mã được xem |
| Hiệu năng | p95 = 80 ms tại tải thử 100 request/giây; mục tiêu giả định 200 ms | Đạt trong điều kiện tải đã đo |
| Khả năng kiểm thử | Có test tự động nhưng thiếu tình huống phân quyền | Cập nhật ma trận kiểm thử theo yêu cầu |

**Bước 5 — Ra quyết định và theo dõi xu hướng.** Nếu một điều kiện bắt buộc chưa đạt, ưu tiên khắc phục và xác minh lại. Nếu mọi điều kiện quan trọng đã đạt, điểm thành phần và xu hướng có thể giúp chọn nơi đầu tư cải thiện tiếp theo. Đừng chỉ hỏi “điểm có tăng không?”, mà hãy hỏi “**rủi ro nào đã giảm, có bằng chứng gì và điều gì vẫn chưa được kiểm chứng?**”.

## 6. Khi nào điểm số tổng hợp vẫn hữu ích?

Một điểm số có thể giúp **theo dõi biến động theo thời gian**, **phát hiện khu vực cần xem xét** hoặc **trao đổi nhanh** với người không trực tiếp đọc mã. Để dùng có trách nhiệm:

- Giữ nhất quán quy tắc tính điểm khi so sánh các lần đo; nếu thay đổi trọng số, phải nói rõ.
- Cho phép xem chi tiết điểm thành phần và bằng chứng gốc.
- Không cho phép điểm cao “xóa” một điều kiện bắt buộc đang thất bại.
- Xem điểm là tín hiệu để điều tra, không phải mục tiêu duy nhất. Nếu nhóm chỉ cố nâng điểm, họ có thể tối ưu những gì công cụ đếm được và bỏ qua rủi ro công cụ chưa đo.
- Đánh giá lại chỉ số khi sản phẩm, lượng người dùng hoặc mức độ nhạy cảm của dữ liệu thay đổi.

Ví dụ, tăng coverage từ 70% lên 90% là một tín hiệu đáng xem xét. Nhưng cần kiểm tra những test mới có bảo vệ luồng quan trọng và phát hiện lỗi khi hành vi thay đổi hay chỉ thực thi thêm dòng mã.

## 7. Tự kiểm tra

**Tình huống:** Hai phiên bản của một dịch vụ có kết quả sau:

- **Phiên bản A:** 92/100 điểm tổng hợp, chạy nhanh và ít cảnh báo style; quá trình rà soát phát hiện lỗi cho phép truy cập dữ liệu của người dùng khác.
- **Phiên bản B:** 81/100 điểm tổng hợp, một số hàm cần tái cấu trúc; chưa phát hiện lỗi truy cập trái phép trong bộ kiểm thử và rà soát hiện có.

**Câu hỏi:** Có nên phát hành ngay phiên bản A vì điểm cao hơn B không? Điều gì cần kiểm tra trước khi quyết định?

**Gợi ý trả lời:** Không. Lỗi truy cập trái phép đã xác nhận ở A là rủi ro có thể chặn phát hành. Với B, kết quả “chưa phát hiện” cũng chưa phải bảo đảm tuyệt đối; cần kiểm tra mức độ bao phủ của các tình huống quan trọng, kết quả rà soát bảo mật, tính đúng đắn và các điều kiện phát hành đã thống nhất. Sau khi rủi ro trọng yếu được xử lý, điểm số mới hỗ trợ ưu tiên những cải tiến tiếp theo.

## Ghi nhớ

**Chất lượng là một tập hợp nhiều thuộc tính và bằng chứng, không phải một con số duy nhất.** Điểm tổng hợp làm gọn thông tin để dễ theo dõi, nhưng có thể che khuất vấn đề nghiêm trọng, phụ thuộc vào trọng số và không phản ánh những điều chưa đo. Một đánh giá hữu ích cần nêu rõ **bối cảnh sử dụng, điều kiện bắt buộc, từng khía cạnh chất lượng, bằng chứng và rủi ro còn lại**.
