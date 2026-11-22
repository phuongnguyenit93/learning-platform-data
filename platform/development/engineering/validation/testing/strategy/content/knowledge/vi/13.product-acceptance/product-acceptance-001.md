# Xác định người đại diện nhu cầu sử dụng và quyền chấp nhận

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, quyết định chấp nhận sản phẩm cần dựa trên hai điều kiện khác nhau: nhóm đã hiểu đúng nhu cầu của những người sẽ sử dụng hoặc chịu ảnh hưởng bởi sản phẩm, và người có thẩm quyền đã xem xét bằng chứng để quyết định sản phẩm có thể được chấp nhận hay không. Vì vậy, cần xác định rõ **ai đại diện cho nhu cầu sử dụng** và **ai có quyền chấp nhận** trước khi tổ chức kiểm thử chấp nhận.

Hai vai trò này có thể do cùng một người đảm nhiệm trong một dự án nhỏ, nhưng thường thuộc về những người khác nhau. Người trực tiếp sử dụng sản phẩm có thể hiểu rõ công việc hằng ngày nhưng không có quyền ký nghiệm thu hợp đồng. Người đại diện khách hàng có thể được ủy quyền chấp nhận nhưng không trực tiếp thực hiện mọi tác vụ. Nếu nhóm nhầm lẫn hai vai trò, sản phẩm có thể được chấp nhận dù nhu cầu của một nhóm người dùng quan trọng chưa được kiểm tra, hoặc kết quả kiểm thử bị tranh cãi vì người ký không có thẩm quyền.

## 1. Phân biệt người đại diện nhu cầu và người có quyền chấp nhận

### Người đại diện nhu cầu sử dụng

Người đại diện nhu cầu sử dụng (user representative) là người cung cấp góc nhìn có cơ sở về công việc, mục tiêu, khó khăn, điều kiện và kỳ vọng của một hoặc nhiều nhóm người dùng. Họ giúp nhóm phát triển hiểu sản phẩm cần hỗ trợ điều gì trong thực tế.

Người đại diện có thể là:

- Người dùng trực tiếp có kinh nghiệm thực hiện công việc.
- Chuyên gia nghiệp vụ hoặc nhân viên chủ chốt hiểu quy trình và các trường hợp ngoại lệ.
- Đại diện của một nhóm người dùng, chi nhánh, khu vực hoặc vai trò cụ thể.
- Product owner hoặc business analyst có trách nhiệm tổng hợp và làm rõ nhu cầu.
- Đại diện hỗ trợ khách hàng, vận hành hoặc đối tác, khi họ hiểu rõ tác động của sản phẩm đến công việc liên quan.

Người đại diện không nhất thiết là người quản lý cao nhất. Một quản lý có thể hiểu mục tiêu và chính sách, nhưng nhân viên trực tiếp thực hiện tác vụ mới biết những bước khó, cách xử lý ngoại lệ và giới hạn của môi trường làm việc. Với sản phẩm phục vụ nhiều nhóm, thường cần nhiều đại diện thay vì một người duy nhất.

### Người có quyền chấp nhận

Người có quyền chấp nhận (acceptance authority) là cá nhân hoặc vai trò được giao quyền đưa ra quyết định chính thức rằng sản phẩm, phiên bản hoặc phạm vi bàn giao đáp ứng điều kiện chấp nhận đã thống nhất.

Tùy bối cảnh, người này có thể là:

- Đại diện khách hàng được ghi rõ trong hợp đồng hoặc thỏa thuận nghiệm thu.
- Product owner chịu trách nhiệm về kết quả sản phẩm và được tổ chức ủy quyền.
- Chủ sở hữu nghiệp vụ hoặc người bảo trợ có quyền phê duyệt kết quả.
- Hội đồng hoặc nhóm phê duyệt nếu quyết định cần nhiều chức năng cùng tham gia.

Quyền chấp nhận phải được xác định bằng quy định, hợp đồng, cơ chế ủy quyền hoặc quyết định quản trị phù hợp. Không nên suy ra quyền này chỉ từ chức danh, mức độ tham gia cuộc họp hoặc việc một người đã gửi phản hồi.

### Hai vai trò có thể giao nhau nhưng không đồng nhất

| Khía cạnh | Đại diện nhu cầu sử dụng | Người có quyền chấp nhận |
|---|---|---|
| Trách nhiệm chính | Giúp xác định và xác nhận nhu cầu, công việc, bối cảnh và kỳ vọng | Ra quyết định chấp nhận dựa trên tiêu chí và bằng chứng |
| Góc nhìn | Công việc thực tế và trải nghiệm của nhóm người dùng được đại diện | Mục tiêu sản phẩm, cam kết, phạm vi và mức rủi ro được phép chấp nhận |
| Hoạt động điển hình | Phỏng vấn, review quy trình, thử nghiệm prototype, thực hiện tác vụ, phản hồi UAT | Xem xét kết quả, xác nhận điều kiện nghiệm thu, chấp nhận hoặc từ chối, ghi nhận ngoại lệ |
| Bằng chứng đóng góp | Kịch bản sử dụng, quan sát, phản hồi, vấn đề và tiêu chí nghiệp vụ | Biên bản quyết định, xác nhận tiêu chí, phê duyệt hoặc lý do từ chối |
| Giới hạn | Có thể không có quyền ký nghiệm thu hoặc chấp nhận rủi ro | Có thể không trực tiếp hiểu mọi chi tiết công việc của từng nhóm người dùng |

Người dùng đại diện có thể đề xuất sản phẩm chưa phù hợp; người có quyền chấp nhận phải xem xét phản hồi đó cùng các tiêu chí đã thống nhất. Ngược lại, việc người có thẩm quyền ký chấp nhận không tự chứng minh rằng mọi nhóm người dùng đều có trải nghiệm tốt. Cần có bằng chứng đại diện đủ tin cậy để hỗ trợ quyết định.

## 2. Vì sao phải xác định đúng người tham gia?

Chọn sai người tham gia có thể khiến nhóm thu thập thông tin không đại diện, bỏ sót nhu cầu hoặc ra quyết định vượt quá thẩm quyền.

Những rủi ro thường gặp gồm:

- Chỉ hỏi quản lý hoặc người bảo trợ, nên bỏ qua khó khăn của người trực tiếp thao tác.
- Chỉ mời người dùng thường xuyên, nên không thấy vấn đề của người dùng ít kinh nghiệm hoặc chỉ sử dụng trong tình huống đặc biệt.
- Chỉ mời một bộ phận, trong khi sản phẩm ảnh hưởng đến nhiều vai trò hoặc đơn vị.
- Dùng một người đại diện cho tất cả nhóm mà không xác minh họ có hiểu công việc của từng nhóm hay không.
- Để người thực hiện test tự tuyên bố chấp nhận thay cho khách hàng hoặc chủ sở hữu nghiệp vụ.
- Có nhiều người đưa ra ý kiến nhưng không ai được giao quyền quyết định cuối cùng.
- Người có quyền chấp nhận không được cung cấp tiêu chí, bằng chứng, giới hạn kiểm thử hoặc rủi ro còn tồn dư.

Xác định đúng người giúp nhóm phân biệt phản hồi cá nhân với nhu cầu chung, nhận diện xung đột giữa các nhóm, làm rõ tiêu chí trước khi test và tránh tranh chấp vào thời điểm bàn giao.

## 3. Xác định các nhóm người dùng và bên liên quan

Trước khi chọn đại diện, hãy lập bản đồ những người sử dụng, nhận kết quả hoặc chịu ảnh hưởng từ sản phẩm. Không chỉ xem ai đăng nhập vào ứng dụng; một quy trình có thể ảnh hưởng đến người phê duyệt, người nhận thông báo, nhân viên hỗ trợ, bộ phận vận hành, khách hàng cuối và đối tác.

### Phân nhóm theo công việc và bối cảnh

Có thể phân nhóm theo:

- **Vai trò:** người tạo, người xem, người phê duyệt, người quản trị, người hỗ trợ hoặc người vận hành.
- **Tác vụ:** công việc chính, công việc phụ, xử lý ngoại lệ và tác vụ có hậu quả cao.
- **Tần suất:** sử dụng hằng ngày, thỉnh thoảng, theo mùa vụ hoặc chỉ khi có sự cố.
- **Kinh nghiệm:** người mới, người thành thạo, chuyên gia nghiệp vụ và người cần hỗ trợ.
- **Môi trường:** văn phòng, hiện trường, thiết bị di động, mạng yếu, nhiều ca làm hoặc nhiều múi giờ.
- **Đặc điểm tiếp cận:** thiết bị hỗ trợ, khả năng tiếp cận, ngôn ngữ và điều kiện thao tác khác nhau.
- **Mức ảnh hưởng:** người trực tiếp dùng, người nhận kết quả, người quản lý rủi ro và người chịu trách nhiệm khi quy trình thất bại.

Các nhóm này không nhất thiết tạo thành những phân khúc loại trừ lẫn nhau. Một người có thể đảm nhiệm nhiều vai trò; một vai trò có thể có nhiều kiểu người dùng. Mục tiêu là nhận diện sự khác biệt có thể làm thay đổi yêu cầu hoặc kết quả chấp nhận.

### Xác định ai cần được đại diện

Với mỗi nhóm, ghi rõ công việc, nhu cầu, quyết định họ đưa ra, vấn đề nếu sản phẩm không hoạt động và bằng chứng cần thu thập. Ưu tiên nhóm có tác vụ trọng yếu, tần suất cao, rủi ro lớn hoặc điều kiện sử dụng khác biệt.

| Nhóm liên quan | Điều cần hiểu hoặc xác nhận | Đại diện phù hợp có thể là |
|---|---|---|
| Người dùng trực tiếp | Có hoàn thành tác vụ chính và ngoại lệ được không? | Người thực hiện công việc hằng ngày, có mức kinh nghiệm đa dạng |
| Chủ sở hữu nghiệp vụ | Quy trình và kết quả có đáp ứng mục tiêu nghiệp vụ không? | Chủ quy trình hoặc chuyên gia nghiệp vụ được giao trách nhiệm |
| Khách hàng hoặc đơn vị đặt hàng | Phạm vi bàn giao có đáp ứng cam kết không? | Đại diện khách hàng được chỉ định |
| Vận hành và hỗ trợ | Sản phẩm có thể vận hành, giám sát và hỗ trợ không? | Đại diện vận hành, help desk hoặc quản trị hệ thống |
| Bảo mật và tuân thủ | Các điều kiện kiểm soát bắt buộc có được đáp ứng không? | Người phụ trách bảo mật, quyền riêng tư hoặc tuân thủ |
| Người dùng có nhu cầu tiếp cận khác nhau | Luồng thao tác có sử dụng được trong điều kiện của họ không? | Người dùng thực tế hoặc chuyên gia có kinh nghiệm tiếp cận |
| Đối tác tích hợp | Trao đổi dữ liệu và quy trình phối hợp có hoạt động đúng không? | Đầu mối kỹ thuật hoặc nghiệp vụ của đối tác |

Không phải dự án nào cũng cần tất cả nhóm. Chọn nhóm theo phạm vi, tác động và nghĩa vụ của sản phẩm; nếu một nhóm bị loại khỏi hoạt động xác nhận, ghi rõ lý do và rủi ro liên quan.

## 4. Tiêu chí chọn người đại diện nhu cầu sử dụng

Một người có chức danh phù hợp chưa chắc là đại diện tốt. Cần đánh giá khả năng họ phản ánh chính xác công việc và sự đa dạng trong nhóm mà họ đại diện.

### Hiểu công việc thực tế

Người đại diện nên trực tiếp thực hiện công việc hoặc có bằng chứng đáng tin cậy về quy trình. Họ cần hiểu các bước chính, ngoại lệ, điểm nghẽn, công cụ liên quan và hậu quả khi xảy ra sai sót. Nếu họ chỉ biết quy trình trên tài liệu, hãy bổ sung quan sát người dùng thực tế.

### Đại diện đúng phạm vi

Xác định người đó đại diện cho vai trò, địa điểm, nhóm khách hàng hay loại tác vụ nào. Tránh tuyên bố một người đại diện cho “tất cả người dùng” khi họ chỉ có kinh nghiệm trong một môi trường hoặc một phân khúc.

### Có khả năng cung cấp phản hồi cụ thể

Đại diện tốt có thể mô tả tình huống, dữ liệu, điều kiện và kết quả mong muốn; phân biệt điều bắt buộc với điều ưu tiên; đưa ra ví dụ thực tế và giải thích vì sao một vấn đề ảnh hưởng đến công việc. Phản hồi như “giao diện không tốt” cần được làm rõ bằng tác vụ, bước gây khó và hệ quả quan sát được.

### Có đủ thời gian và quyền tham gia

Người đại diện cần được bố trí thời gian cho phỏng vấn, review, thử nghiệm và phản hồi. Quản lý của họ nên biết và hỗ trợ việc tham gia. Nếu họ không thể tham gia ở các mốc quan trọng, cần có người thay thế và quy trình chuyển giao thông tin.

### Hạn chế thiên lệch

Không chỉ chọn những người luôn đồng ý với nhóm phát triển hoặc có quan hệ gần với người ra quyết định. Nên có góc nhìn khác nhau, kể cả phản hồi trái chiều. Với nhóm đông hoặc phân tán, kết hợp nhiều người đại diện và dữ liệu quan sát để tránh phụ thuộc vào ý kiến của một cá nhân.

## 5. Chọn đại diện theo mức độ rủi ro và tính đa dạng

Không phải lúc nào cũng có thể mời toàn bộ người dùng tham gia. Mẫu tham gia cần phản ánh các tình huống có khả năng làm thay đổi thiết kế hoặc quyết định chấp nhận.

Hãy ưu tiên:

- Người thực hiện tác vụ có hậu quả cao nếu sai.
- Người dùng có tần suất và khối lượng công việc lớn.
- Người dùng mới hoặc ít kinh nghiệm nếu sản phẩm phải dễ tiếp cận với nhóm này.
- Nhóm làm việc ở môi trường khác biệt như hiện trường, thiết bị cũ hoặc mạng không ổn định.
- Người dùng có nhu cầu tiếp cận hoặc phương thức thao tác khác nhau.
- Nhóm ít được đại diện nhưng chịu ảnh hưởng đáng kể từ sản phẩm.
- Người xử lý ngoại lệ, khiếu nại, hoàn tiền hoặc tình huống khôi phục.

Ví dụ, ứng dụng quản lý kho được dùng bởi nhân viên nhập hàng, nhân viên kiểm kê, quản lý kho và bộ phận kế toán. Chỉ mời quản lý kho sẽ không đủ để xác nhận thao tác quét mã, nhập số lượng, xử lý hàng thiếu hoặc làm việc khi mất mạng. Cần chọn người đại diện theo các tác vụ và điều kiện này.

### Kiểm tra tính đại diện

Trước khi bắt đầu, hãy đối chiếu danh sách người tham gia với bản đồ nhóm người dùng:

- Nhóm nào có người tham gia và nhóm nào chưa có?
- Người tham gia có thực sự thực hiện tác vụ trong phạm vi không?
- Có đủ tình huống bình thường và ngoại lệ không?
- Có khác biệt đáng kể về kinh nghiệm, thiết bị, địa điểm hoặc khả năng tiếp cận không?
- Nhóm nào bị bỏ sót có thể làm thay đổi quyết định chấp nhận?

Không có một cỡ mẫu cố định phù hợp cho mọi hoạt động. Phỏng vấn khám phá, kiểm thử khả năng sử dụng định tính, khảo sát định lượng và nghiệm thu theo hợp đồng có mục tiêu khác nhau. Cần chọn số người và cách lấy mẫu theo câu hỏi, độ đa dạng, mức rủi ro và độ tin cậy cần có; không nên tuyên bố kết quả đại diện thống kê nếu phương pháp lấy mẫu không hỗ trợ kết luận đó.

## 6. Xác định người có quyền chấp nhận

Người có quyền chấp nhận phải được xác định trước khi thực hiện kiểm thử chấp nhận, tốt nhất từ giai đoạn làm rõ yêu cầu và thỏa thuận phạm vi. Việc này giúp nhóm biết ai duyệt tiêu chí, ai xem xét bằng chứng và ai ra quyết định cuối cùng.

### Căn cứ xác định thẩm quyền

Quyền chấp nhận có thể được xác định từ:

- Hợp đồng, statement of work hoặc thỏa thuận nghiệm thu.
- Quy chế quản trị sản phẩm hoặc quy trình phê duyệt nội bộ.
- Quyết định ủy quyền bằng văn bản.
- Vai trò chủ sở hữu sản phẩm hoặc chủ sở hữu nghiệp vụ được tổ chức công nhận.
- Quy định về an toàn, bảo mật, tuân thủ hoặc vận hành yêu cầu một vai trò chuyên trách phê duyệt.

Nếu có nhiều cấp phê duyệt, cần xác định phạm vi quyết định của từng cấp. Ví dụ, chủ sở hữu nghiệp vụ xác nhận quy trình, đại diện khách hàng chấp nhận bàn giao theo hợp đồng, còn người phụ trách vận hành xác nhận điều kiện đưa dịch vụ vào vận hành. Một vai trò không tự động thay thế quyền của vai trò khác.

### Quy định rõ phạm vi quyền

Với người có quyền chấp nhận, cần làm rõ:

- Họ được quyền chấp nhận sản phẩm, tính năng, phiên bản hay một phần phạm vi nào?
- Họ có quyền chấp nhận có điều kiện hay chấp nhận ngoại lệ không?
- Những tiêu chí nào là bắt buộc và không thể miễn trừ?
- Khi có rủi ro còn lại, ai có quyền chấp thuận và theo quy trình nào?
- Nếu người được ủy quyền vắng mặt, ai là người thay thế?
- Quyết định được ghi nhận ở đâu và có cần chữ ký hoặc phê duyệt điện tử không?

Không nên để nhóm dự án tự quyết định rằng một người có thẩm quyền chỉ vì người đó tham gia cuộc họp nghiệm thu. Nếu chưa rõ quyền, phải làm rõ với chủ thể sở hữu hợp đồng hoặc quy trình quản trị trước khi dựa vào chữ ký đó.

## 7. Phân biệt người tham gia kiểm thử, người đề xuất và người quyết định

Một quy trình chấp nhận thường có nhiều vai trò. Tách vai trò giúp tránh xung đột và đảm bảo người quyết định nhận được thông tin phù hợp.

| Vai trò | Trách nhiệm thường gặp | Có quyền chấp nhận không? |
|---|---|---|
| Người dùng đại diện | Thực hiện tác vụ, mô tả nhu cầu, phản hồi về mức phù hợp | Không mặc định; chỉ khi được ủy quyền rõ |
| Tester/QA | Thiết kế và thực hiện kiểm thử, báo cáo bằng chứng và giới hạn | Không mặc định; thường tư vấn về chất lượng kiểm thử |
| Business analyst | Làm rõ yêu cầu, quy tắc và truy vết tiêu chí | Theo quyền được giao; không mặc định |
| Product owner/chủ sở hữu nghiệp vụ | Ưu tiên nhu cầu, xác nhận giá trị và tiêu chí sản phẩm | Có thể có, nếu được tổ chức ủy quyền |
| Đại diện khách hàng | Xác nhận phạm vi bàn giao và nghĩa vụ với khách hàng | Có thể có, theo hợp đồng hoặc ủy quyền |
| Vận hành | Xem xét khả năng triển khai, giám sát, hỗ trợ và khôi phục | Có thể có quyền duyệt điều kiện vận hành hoặc quyền chặn theo chính sách |
| Bảo mật/tuân thủ | Xem xét kiểm soát và nghĩa vụ chuyên môn | Có thể có quyền phê duyệt hoặc quyền phủ quyết trong phạm vi được quy định |
| Quản lý dự án/release manager | Điều phối lịch, rủi ro, nguồn lực và quyết định phát hành | Không mặc định có quyền chấp nhận nghiệp vụ |

Tester có trách nhiệm trình bày kết quả trung thực, bao gồm test chưa chạy, lỗi còn mở, điều kiện môi trường và giới hạn bằng chứng. Tester không nên thay người dùng quyết định rằng sản phẩm đáp ứng nhu cầu, cũng không nên tự nhận quyền chấp nhận rủi ro nếu chưa được giao.

## 8. Thiết lập ma trận trách nhiệm và quyền quyết định

Ma trận trách nhiệm giúp mọi người biết ai thực hiện, ai chịu trách nhiệm cuối cùng, ai cần được tham vấn và ai cần được thông báo. Có thể dùng RACI hoặc bảng phân quyền tương đương.

Ví dụ minh họa:

| Hoạt động | Người dùng đại diện | QA/Test Lead | Product Owner | Đại diện khách hàng có thẩm quyền | Vận hành/Bảo mật |
|---|---|---|---|---|---|
| Xác định nhóm người dùng và tác vụ | C | R | A | C | C |
| Làm rõ tiêu chí chấp nhận nghiệp vụ | C | C | A/R | C | C |
| Thiết kế và thực hiện test | C | A/R | C | I | C |
| Xác nhận trải nghiệm và tác vụ | R | C | A | C | I |
| Tổng hợp bằng chứng và rủi ro | C | R | A | I | C |
| Quyết định chấp nhận bàn giao | C | C | C | A/R | C hoặc A theo phạm vi |
| Xác nhận điều kiện vận hành/bảo mật | I | C | C | I | A/R trong phạm vi chuyên môn |

Ký hiệu: **R** (Responsible) là người thực hiện; **A** (Accountable) là người chịu trách nhiệm cuối cùng hoặc có quyền quyết định; **C** (Consulted) là người được tham vấn; **I** (Informed) là người được thông báo. Bảng chỉ là ví dụ. Mỗi hoạt động nên có một đầu mối A rõ ràng; quyền phê duyệt thực tế phải tuân theo hợp đồng và quy chế của tổ chức.

Nếu một hội đồng có quyền chấp nhận tập thể, cần quy định thành phần, điều kiện đủ số người, cách biểu quyết, xử lý bất đồng và người ghi biên bản. Không nên ghi nhiều người cùng là A mà không giải thích cơ chế quyết định.

## 9. Kết nối đại diện người dùng với tiêu chí chấp nhận

Đại diện nhu cầu cần tham gia từ lúc hình thành yêu cầu, không chỉ xuất hiện vào buổi UAT cuối cùng. Họ giúp chuyển công việc thực tế thành kịch bản, dữ liệu và kết quả có thể quan sát.

Một tiêu chí chấp nhận tốt nên mô tả:

- Vai trò người dùng và mục tiêu tác vụ.
- Điều kiện trước khi bắt đầu.
- Dữ liệu và bối cảnh sử dụng.
- Hành động hoặc luồng cần thực hiện.
- Kết quả mong đợi và các ngoại lệ.
- Điều kiện chất lượng liên quan như thời gian, khả năng tiếp cận, độ chính xác hoặc thông báo lỗi.
- Bằng chứng và cách xác định đạt/không đạt.

Ví dụ, yêu cầu “nhân viên kho có thể xác nhận phiếu nhập” còn quá chung. Có thể làm rõ thành:

> Khi nhân viên có quyền của kho A mở phiếu nhập đã được phân công, họ có thể kiểm tra mã hàng, số lượng và đơn vị rồi xác nhận phiếu. Hệ thống hiển thị kết quả rõ ràng, ghi nhận người xác nhận và chỉ cập nhật tồn kho một lần. Nhân viên thuộc kho B hoặc người không có quyền xác nhận không thể thực hiện thao tác này.

Đại diện nhân viên kho cần xác nhận kịch bản phản ánh đúng công việc; chủ sở hữu nghiệp vụ làm rõ quy tắc; QA thiết kế kiểm tra; người có thẩm quyền chấp nhận xác nhận tiêu chí và bằng chứng nào là đủ cho quyết định.

### Phân biệt phản hồi, yêu cầu thay đổi và tiêu chí đạt

Không phải mọi đề xuất của người dùng đều tự động trở thành yêu cầu bắt buộc. Nhóm cần ghi nhận nguồn phản hồi, lý do, mức ảnh hưởng và người quyết định ưu tiên. Nếu phản hồi làm thay đổi phạm vi hoặc tiêu chí chấp nhận, cần cập nhật tài liệu và đánh giá tác động trước khi kết luận test.

Tương tự, một tiêu chí được người dùng đồng ý không đồng nghĩa sản phẩm đã đạt. Cần thực hiện kịch bản, lưu kết quả và đối chiếu với tiêu chí. Ý kiến của đại diện cung cấp bối cảnh; bằng chứng kiểm thử xác nhận hành vi; người có thẩm quyền đưa ra quyết định theo quy trình.

## 10. Tổ chức kiểm thử chấp nhận và ra quyết định

Một quy trình chấp nhận rõ ràng có thể gồm các bước sau:

### Bước 1: Xác nhận người tham gia và quyền hạn

Lập danh sách nhóm người dùng, đại diện, người thay thế, người thực hiện kiểm thử, người xem xét và người có quyền chấp nhận. Ghi rõ phạm vi đại diện và nguồn ủy quyền.

### Bước 2: Thống nhất phạm vi và tiêu chí

Xác định tính năng, quy trình, phiên bản, môi trường, dữ liệu, điều kiện trước, tiêu chí bắt buộc, tiêu chí mong muốn và các trường hợp ngoài phạm vi. Làm rõ điều kiện nào không thể miễn trừ.

### Bước 3: Chuẩn bị kịch bản và môi trường

Đảm bảo kịch bản phản ánh tác vụ thực tế, tài khoản đúng vai trò, dữ liệu an toàn, thiết bị và môi trường phù hợp. Hướng dẫn người tham gia cách báo lỗi và ghi nhận quan sát mà không hướng dẫn họ theo một kết quả mong muốn.

### Bước 4: Thực hiện và ghi nhận bằng chứng

Người dùng đại diện thực hiện tác vụ hoặc đánh giá prototype/sản phẩm. QA ghi nhận kết quả, bước thất bại, lỗi, dữ liệu, thời gian, môi trường và phản hồi. Phân biệt lỗi có thể tái hiện với ý kiến hoặc đề xuất cần phân tích thêm.

### Bước 5: Đánh giá tiêu chí và rủi ro

Đối chiếu từng tiêu chí với bằng chứng. Xem xét lỗi còn mở, mức độ ảnh hưởng, giới hạn kiểm thử, yêu cầu chưa được kiểm tra và rủi ro tồn dư. Nếu có khác biệt giữa các nhóm người dùng, không gộp thành một kết luận chung mà không giải thích.

### Bước 6: Trình quyết định cho đúng người

Chuẩn bị báo cáo tóm tắt gồm phạm vi, kết quả, tiêu chí đạt/chưa đạt, lỗi còn mở, ngoại lệ, giới hạn và khuyến nghị. Người có quyền chấp nhận xem xét và ghi quyết định: chấp nhận, từ chối, hoặc chấp nhận có điều kiện nếu quy trình cho phép.

### Bước 7: Theo dõi điều kiện và hành động sau quyết định

Nếu chấp nhận có điều kiện, ghi rõ điều kiện, người chịu trách nhiệm, thời hạn, cách xác minh và hậu quả nếu không hoàn thành. Nếu từ chối, ghi lý do, yêu cầu khắc phục và tiêu chí cần kiểm tra lại. Quyết định phải được lưu ở nơi có thể truy vết.

## 11. Chấp nhận có điều kiện và xử lý bất đồng

Một số tổ chức cho phép chấp nhận có điều kiện khi còn vấn đề không chặn việc sử dụng hoặc có biện pháp giảm thiểu. Hình thức này chỉ hợp lệ khi quy trình, hợp đồng và thẩm quyền cho phép.

Một quyết định chấp nhận có điều kiện cần ghi:

- Tiêu chí hoặc vấn đề chưa đạt.
- Tác động và rủi ro còn lại.
- Lý do vẫn tiếp tục chấp nhận trong phạm vi xác định.
- Biện pháp giảm thiểu hoặc giới hạn sử dụng.
- Người có thẩm quyền chấp nhận rủi ro.
- Người chịu trách nhiệm khắc phục và thời hạn.
- Điều kiện kích hoạt đánh giá lại, dừng sử dụng hoặc rollback.

Không được dùng chấp nhận có điều kiện để bỏ qua yêu cầu pháp lý, an toàn, bảo mật hoặc tiêu chí không thể miễn trừ. Nếu có tranh luận về rủi ro, chuyển đến cấp có thẩm quyền theo quy trình; tester hoặc đại diện người dùng không tự quyết định ngoại lệ.

### Khi các nhóm người dùng có nhu cầu xung đột

Ví dụ, nhân viên kho muốn ít bước thao tác hơn, trong khi bộ phận kiểm soát cần xác nhận kép cho giao dịch giá trị cao. Đây không chỉ là tranh luận về giao diện; nó liên quan đến năng suất và kiểm soát rủi ro. Nhóm cần:

1. Ghi rõ nhu cầu và hậu quả của từng phía.
2. Xác định nghĩa vụ hoặc kiểm soát bắt buộc.
3. Dùng prototype hoặc thử nghiệm để so sánh các phương án.
4. Đánh giá rủi ro, chi phí và tác động đến các nhóm.
5. Trình người có quyền quyết định để chọn phương án và ghi lý do.

Không nên chọn ý kiến của người có chức vụ cao hơn mà bỏ qua bằng chứng sử dụng. Cũng không nên để một nhóm người dùng tự miễn trừ kiểm soát bắt buộc chỉ vì thao tác thuận tiện hơn.

## 12. Ví dụ xuyên suốt: chấp nhận ứng dụng quản lý kho

Giả sử tổ chức triển khai ứng dụng quản lý nhập, xuất và kiểm kê cho nhiều kho. Người dùng gồm nhân viên kho, trưởng ca, kế toán kho và bộ phận vận hành. Đợt bàn giao cần xác nhận quy trình nhập hàng, quyền xác nhận và khả năng làm việc khi mạng gián đoạn.

### Chọn đại diện nhu cầu

- Mời nhân viên nhập hàng có kinh nghiệm và nhân viên mới để thực hiện quét mã, nhập số lượng và xử lý hàng thiếu.
- Mời trưởng ca xác nhận luồng phê duyệt và xử lý sai lệch.
- Mời kế toán kho kiểm tra báo cáo và đối soát.
- Mời vận hành đánh giá cảnh báo, đồng bộ dữ liệu và khả năng hỗ trợ khi mất kết nối.
- Nếu ứng dụng dùng trên thiết bị cầm tay hoặc trong môi trường mạng yếu, chọn người làm việc trong điều kiện đó để thử nghiệm.

Mỗi đại diện được ghi rõ phạm vi: ví dụ nhân viên nhập hàng đại diện cho tác vụ nhận hàng tại kho có thiết bị quét mã; họ không mặc nhiên đại diện cho quy trình kế toán hoặc tất cả địa điểm.

### Xác định người có quyền chấp nhận

Giả sử hợp đồng quy định đại diện khách hàng được chỉ định ký nghiệm thu. Product owner chịu trách nhiệm xác nhận giá trị và phạm vi sản phẩm; trưởng vận hành xác nhận điều kiện hỗ trợ; bộ phận bảo mật xác nhận các kiểm soát thuộc phạm vi chuyên môn. Người ký nghiệm thu cuối cùng là đại diện khách hàng theo ủy quyền trong hợp đồng, sau khi nhận các xác nhận bắt buộc.

### Tiêu chí và bằng chứng

| Tiêu chí | Người cung cấp góc nhìn | Bằng chứng | Người xem xét/quyết định |
|---|---|---|---|
| Nhân viên nhập hàng hoàn thành quy trình nhập đúng | Nhân viên kho đại diện | Quan sát tác vụ, kết quả phiếu và dữ liệu tồn kho | Chủ sở hữu nghiệp vụ/Product owner |
| Chỉ người có quyền mới xác nhận phiếu | Trưởng ca và chuyên gia phân quyền | Test vai trò hợp lệ/không hợp lệ, log và trạng thái dữ liệu | Chủ sở hữu nghiệp vụ và bảo mật theo phạm vi |
| Số lượng và đơn vị được ghi nhận chính xác | Nhân viên kho, kế toán kho | Kịch bản dữ liệu biên và đối soát | Chủ sở hữu nghiệp vụ |
| Hệ thống xử lý được mất kết nối theo quy tắc | Nhân viên hiện trường, vận hành | Thử nghiệm mất mạng, đồng bộ lại và kiểm tra trùng | Vận hành và Product owner |
| Phạm vi bàn giao đáp ứng hợp đồng | Đại diện khách hàng | Báo cáo test, lỗi còn mở và ma trận tiêu chí | Đại diện khách hàng có quyền ký nghiệm thu |

### Ra quyết định

Giả sử các luồng nhập hàng và phân quyền đạt, nhưng kiểm tra đồng bộ khi mất mạng chỉ hoàn thành trên một loại thiết bị. Báo cáo phải nêu rõ phạm vi thiết bị đã kiểm tra và phần chưa có bằng chứng. Người có quyền chấp nhận xem xét rủi ro, điều kiện triển khai và cam kết hỗ trợ trước khi quyết định. Nếu chấp nhận có điều kiện được phép, cần ghi giới hạn thiết bị, biện pháp giảm thiểu, thời hạn bổ sung kiểm tra và người chịu trách nhiệm. Nếu đây là tiêu chí bắt buộc trong hợp đồng, không thể tự bỏ qua bằng một ghi chú chung.

## 13. Bằng chứng và hồ sơ quyết định chấp nhận

Hồ sơ cần đủ để một người không tham gia trực tiếp vẫn hiểu ai đã xác nhận điều gì và quyết định dựa trên cơ sở nào.

Một bộ hồ sơ có thể gồm:

- Danh sách nhóm người dùng, người đại diện và phạm vi đại diện.
- Vai trò, nguồn ủy quyền và người có quyền chấp nhận.
- Phiên bản sản phẩm, phạm vi bàn giao và môi trường kiểm thử.
- Tiêu chí chấp nhận đã thống nhất và lịch sử thay đổi.
- Kịch bản, dữ liệu, kết quả, lỗi và phản hồi của người tham gia.
- Báo cáo kiểm thử, giới hạn bằng chứng và rủi ro tồn dư.
- Biên bản quyết định: chấp nhận, từ chối hoặc chấp nhận có điều kiện.
- Ngoại lệ, người phê duyệt, hành động, thời hạn và bằng chứng hoàn tất.

Phản hồi người dùng có thể chứa thông tin cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm. Chỉ lưu thông tin cần thiết, kiểm soát quyền truy cập, che dữ liệu nhận diện khi phù hợp và tuân thủ chính sách lưu giữ. Khi trích dẫn ý kiến, cần có ngữ cảnh đủ để không làm sai ý người tham gia.

## 14. Những sai lầm thường gặp

**Chọn quản lý làm đại diện duy nhất.** Quản lý có thể hiểu mục tiêu nhưng không biết mọi khó khăn thao tác. Hãy bổ sung người trực tiếp thực hiện công việc và các nhóm có điều kiện sử dụng khác nhau.

**Coi một người dùng tích cực là đại diện cho tất cả.** Mức kinh nghiệm, thiết bị, tần suất và bối cảnh khác nhau có thể tạo nhu cầu khác nhau. Ghi rõ phạm vi đại diện và chọn thêm người khi cần.

**Chỉ mời người dùng vào cuối dự án.** Khi đó, phát hiện nhu cầu sai có thể gây thay đổi lớn. Hãy tham gia người đại diện từ lúc làm rõ yêu cầu, review prototype và định nghĩa tiêu chí.

**Để người tham gia UAT tự động trở thành người ký nghiệm thu.** Người thực hiện test cung cấp bằng chứng và phản hồi; quyền ký phải đến từ hợp đồng hoặc ủy quyền rõ ràng.

**Không xác định người quyết định cuối cùng.** Nhiều ý kiến được thu thập nhưng không có cơ chế giải quyết bất đồng sẽ khiến quyết định bị trì hoãn hoặc tranh cãi. Chỉ định người có quyền và quy trình thay thế từ sớm.

**Coi chữ ký là bằng chứng duy nhất về chất lượng.** Chữ ký ghi nhận quyết định, không thay thế kết quả test, phản hồi người dùng, tiêu chí và rủi ro. Người ký cần được cung cấp hồ sơ đầy đủ.

**Không phân biệt ý kiến, yêu cầu và tiêu chí đạt.** Ý kiến cần được phân tích; yêu cầu cần được ưu tiên và phê duyệt; tiêu chí đạt cần có kết quả kiểm chứng. Trộn lẫn chúng làm thay đổi phạm vi không kiểm soát.

**Chấp nhận ngoại lệ không đúng thẩm quyền.** Người không được giao quyền có thể đồng ý về mặt sử dụng nhưng không thể miễn trừ nghĩa vụ hợp đồng hoặc kiểm soát bắt buộc. Phải chuyển đến người có quyền theo quy trình.

**Không lưu phạm vi đại diện và rủi ro nhóm bị bỏ sót.** Báo cáo “người dùng đã xác nhận” quá chung chung. Cần nêu nhóm nào tham gia, nhóm nào chưa, tác vụ nào được thử và giới hạn kết luận.

## 15. Checklist xác định đại diện và quyền chấp nhận

Khi bắt đầu:

- [ ] Đã lập bản đồ nhóm người dùng và bên liên quan chịu ảnh hưởng.
- [ ] Đã xác định tác vụ, bối cảnh, tần suất và rủi ro của từng nhóm.
- [ ] Mỗi đại diện có phạm vi đại diện rõ và có hiểu biết thực tế phù hợp.
- [ ] Các nhóm ít được đại diện hoặc có điều kiện sử dụng khác biệt đã được xem xét.
- [ ] Có người thay thế hoặc cách tiếp tục khi đại diện không thể tham gia.

Trước kiểm thử chấp nhận:

- [ ] Người có quyền chấp nhận được xác định bằng hợp đồng, quy chế hoặc ủy quyền.
- [ ] Phạm vi quyền, tiêu chí bắt buộc và quyền chấp nhận ngoại lệ đã rõ.
- [ ] Vai trò người dùng, QA, Product owner, khách hàng, vận hành và chuyên gia kiểm soát được phân định.
- [ ] Tiêu chí chấp nhận gắn với tác vụ, điều kiện, kết quả và bằng chứng.
- [ ] Người quyết định đã thống nhất cách xử lý lỗi, bất đồng và chấp nhận có điều kiện.

Khi kết thúc:

- [ ] Kết quả và phản hồi được lưu cùng nhóm người tham gia và bối cảnh thử nghiệm.
- [ ] Phạm vi đã được xác nhận và các nhóm chưa được đại diện được nêu rõ.
- [ ] Lỗi, tiêu chí chưa đạt, giới hạn và rủi ro tồn dư được báo cáo.
- [ ] Quyết định được ghi bởi đúng người có thẩm quyền và có thể truy vết.
- [ ] Điều kiện, ngoại lệ, người phụ trách và thời hạn được theo dõi đến khi hoàn tất.

## 16. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Nhân viên kho trực tiếp thử ứng dụng và xác nhận thao tác nhập hàng phù hợp. Họ là người đại diện nhu cầu sử dụng cho tác vụ đó. Nếu hợp đồng quy định giám đốc vận hành của khách hàng ký nghiệm thu, nhân viên kho không tự động có quyền ký thay.

**Tình huống 2:** Product owner được giao quyền chấp nhận tính năng, nhưng chưa có người dùng đại diện thử luồng thực tế. Quyền quyết định đã rõ, nhưng bằng chứng về tính phù hợp với công việc còn thiếu. Cần bổ sung người dùng đại diện hoặc bằng chứng sử dụng phù hợp trước khi kết luận.

**Tình huống 3:** Một đại diện khách hàng ký nghiệm thu dù còn lỗi bảo mật thuộc tiêu chí bắt buộc không thể miễn trừ. Chữ ký đó không tự làm cho vi phạm trở nên chấp nhận được. Cần xử lý theo quy trình bảo mật và thẩm quyền được quy định.

**Tình huống 4:** Người dùng tại văn phòng xác nhận ứng dụng dễ dùng, nhưng nhân viên hiện trường dùng thiết bị cũ và mạng yếu không thể hoàn tất tác vụ. Kết quả từ nhóm văn phòng không đại diện cho bối cảnh hiện trường. Cần bổ sung nhóm người dùng và điều kiện thử nghiệm còn thiếu, sau đó đánh giá tác động.

**Tình huống 5:** Có ba nhóm đưa ra ưu tiên khác nhau và không thống nhất về một quy tắc. Nhóm cần ghi nhận tác động từng phía, xác định nghĩa vụ bắt buộc, thử nghiệm phương án nếu có thể và chuyển quyết định đến người có quyền. Không nên lấy ý kiến đa số hoặc chức danh cao nhất làm căn cứ duy nhất.

Khi chuẩn bị chấp nhận sản phẩm, hãy tự hỏi: **ai thực sự hiểu công việc và đại diện cho nhóm người dùng nào, ai được ủy quyền quyết định, và người đó sẽ dựa vào bằng chứng nào?** Nếu ba câu hỏi này chưa có câu trả lời rõ ràng, quy trình chấp nhận vẫn còn khoảng trống về đại diện hoặc thẩm quyền.

## Kết luận

Người đại diện nhu cầu sử dụng giúp nhóm hiểu công việc và đánh giá sản phẩm trong bối cảnh thực tế; người có quyền chấp nhận đưa ra quyết định chính thức dựa trên tiêu chí, bằng chứng và phạm vi thẩm quyền. Hai vai trò có thể giao nhau nhưng cần được xác định riêng, cùng với nhóm người dùng được đại diện, người tham gia kiểm thử, người xem xét và người quyết định. Khi quyền hạn, tiêu chí, bằng chứng và cách xử lý ngoại lệ được thống nhất từ sớm, quyết định chấp nhận trở nên minh bạch, có thể truy vết và phản ánh tốt hơn nhu cầu thực tế.
