# Phân công người rà soát và mức độc lập cần thiết

Kiểm thử tĩnh (static testing) đánh giá tài liệu, yêu cầu, thiết kế, mã nguồn, ca kiểm thử hoặc các sản phẩm công việc khác mà không cần thực thi phần mềm. Một phần quan trọng để hoạt động rà soát có hiệu quả là chọn đúng người tham gia và xác định mức độ độc lập phù hợp. Người rà soát cần đủ kiến thức để nhận ra vấn đề, có góc nhìn phù hợp với mục tiêu rà soát và có đủ khoảng cách với công việc được tạo ra để nhận xét khách quan.

**Phân công người rà soát** trả lời câu hỏi ai sẽ kiểm tra nội dung nào, với trách nhiệm gì. **Mức độc lập** mô tả người rà soát tách biệt với tác giả hoặc nhóm tạo sản phẩm công việc đến đâu. Hai yếu tố có quan hệ với nhau nhưng không đồng nhất: một chuyên gia ở nhóm khác có thể rất độc lập nhưng thiếu kiến thức miền nghiệp vụ; một đồng nghiệp cùng nhóm có thể hiểu sâu thiết kế nhưng dễ chia sẻ các giả định chưa được kiểm chứng.

Mục tiêu không phải lúc nào cũng chọn người độc lập nhất. Nhóm cần cân bằng chuyên môn, góc nhìn mới, mức rủi ro, thời gian, chi phí và yêu cầu tuân thủ. Với nội dung có ảnh hưởng lớn như phân quyền, xử lý thanh toán hoặc yêu cầu an toàn, mức độc lập cao hơn thường đem lại giá trị. Với bản nháp nội bộ hoặc thay đổi nhỏ, rà soát đồng cấp có thể đủ.

## 1. Vì sao cần phân công người rà soát có chủ đích?

Chất lượng rà soát phụ thuộc nhiều vào người tham gia. Một người có thể đọc rất kỹ nhưng không phát hiện lỗi nếu họ không hiểu quy tắc nghiệp vụ. Một chuyên gia kỹ thuật có thể nhận ra vấn đề kiến trúc nhưng bỏ qua yêu cầu pháp lý hoặc trải nghiệm của người dùng. Một nhóm có nhiều người cùng nền tảng và cùng giả định có thể bỏ sót cùng một loại sai lệch.

Phân công có chủ đích giúp:

- **Bao phủ đúng chuyên môn:** Có người hiểu nghiệp vụ, kỹ thuật, bảo mật, khả năng truy cập hoặc vận hành tùy nội dung cần rà soát.
- **Giảm điểm mù:** Bổ sung góc nhìn từ người không trực tiếp tạo ra tài liệu hoặc thiết kế.
- **Làm rõ trách nhiệm:** Biết ai chuẩn bị, ai rà soát, ai ghi nhận phát hiện, ai sửa và ai xác nhận hoàn tất.
- **Sử dụng thời gian hợp lý:** Phân bổ người có chuyên môn khan hiếm vào phần có rủi ro cao thay vì mời họ đọc toàn bộ tài liệu không cần thiết.
- **Tạo bằng chứng đáng tin cậy:** Ghi nhận được phạm vi, người tham gia, phát hiện, quyết định và trạng thái xử lý.
- **Đáp ứng yêu cầu độc lập:** Tách người tạo và người phê duyệt khi quy trình, hợp đồng hoặc quy định yêu cầu.

Ví dụ, khi rà soát yêu cầu thanh toán, người hiểu nghiệp vụ cần kiểm tra quy tắc tính tiền và hoàn tiền; lập trình viên hoặc kiến trúc sư cần xem xét tính nhất quán và khả năng triển khai; chuyên gia bảo mật cần đánh giá xác thực, phân quyền và dữ liệu nhạy cảm. Một người có thể có nhiều năng lực, nhưng nhóm cần xác nhận rằng các khía cạnh quan trọng đều có người chịu trách nhiệm xem xét.

## 2. Các vai trò thường có trong một cuộc rà soát

Tên vai trò và cách phân chia có thể khác nhau giữa các phương pháp rà soát. Một cuộc rà soát không chính thức có thể chỉ có tác giả và một đồng nghiệp; một cuộc kiểm tra có quy trình chặt chẽ có thể cần người điều phối, người ghi nhận và nhiều chuyên gia.

| Vai trò | Trách nhiệm chính | Lưu ý |
|---|---|---|
| Tác giả (author) | Tạo sản phẩm công việc, cung cấp bối cảnh, trả lời câu hỏi và xử lý phát hiện | Không nên tự quyết định bỏ qua mọi phát hiện liên quan đến nội dung mình tạo nếu cần phê duyệt độc lập |
| Người rà soát (reviewer) | Kiểm tra nội dung theo mục tiêu và phạm vi, xác định sai lệch, rủi ro hoặc điểm chưa rõ | Cần có chuyên môn phù hợp và chuẩn bị trước |
| Người điều phối/người dẫn dắt (moderator/facilitator) | Lập kế hoạch, hướng dẫn quy trình, giữ cuộc họp đúng mục tiêu và xử lý bất đồng | Nên giữ trung lập, đặc biệt khi nội dung có tranh luận hoặc rủi ro cao |
| Người ghi nhận (recorder/scribe) | Ghi phát hiện, câu hỏi, quyết định, người phụ trách và thời hạn | Có thể là người điều phối trong nhóm nhỏ nếu vẫn ghi chép đầy đủ |
| Người quản lý hoặc chủ sở hữu quy trình | Cung cấp thời gian, nhân lực, điều kiện rà soát và xử lý các vấn đề về nguồn lực | Không nhất thiết tham gia đánh giá chi tiết nội dung |
| Chuyên gia chuyên môn (subject matter expert) | Đánh giá khía cạnh nghiệp vụ hoặc kỹ thuật chuyên sâu | Có thể tham gia với tư cách reviewer hoặc tư vấn cho reviewer |

Không phải cuộc rà soát nào cũng cần đủ tất cả vai trò. Điều quan trọng là các trách nhiệm thiết yếu được thực hiện và mọi người biết phạm vi quyền hạn của mình. Người ghi nhận không tự quyết định thay chủ sở hữu yêu cầu; người điều phối không thay reviewer kết luận về chuyên môn; tác giả chịu trách nhiệm xử lý nội dung sau rà soát.

## 3. Hiểu mức độ độc lập

Mức độc lập có thể xem như một phổ, từ người tạo nội dung tự kiểm tra đến người đánh giá bên ngoài tổ chức. Khoảng cách với tác giả càng lớn có thể làm giảm ảnh hưởng của các giả định chung, nhưng cũng có thể làm tăng thời gian tìm hiểu bối cảnh và chi phí phối hợp.

### 3.1. Tự rà soát bởi tác giả

Tác giả đọc lại công việc của mình trước khi chia sẻ hoặc chuyển sang bước tiếp theo. Đây là bước hữu ích để phát hiện lỗi trình bày, thiếu nội dung, sai cú pháp, liên kết hỏng hoặc lỗi đơn giản.

Ưu điểm là nhanh, tác giả hiểu rõ ý định và có thể sửa ngay. Hạn chế là tác giả dễ đọc theo điều mình nghĩ đã viết, bỏ qua giả định sai hoặc không nhận ra vấn đề do chính cách tiếp cận của mình tạo ra. Tự rà soát nên là bước chuẩn bị, không thay thế một cuộc rà soát độc lập khi rủi ro hoặc quy trình yêu cầu.

### 3.2. Rà soát đồng cấp trong cùng nhóm

Một đồng nghiệp có chuyên môn tương tự hoặc làm việc gần với tác giả kiểm tra nội dung. Họ thường hiểu kiến trúc, quy ước, công cụ và bối cảnh nhóm, nên có thể phản hồi nhanh và cụ thể.

Mức độc lập cao hơn tự rà soát nhưng vẫn có thể tồn tại điểm mù chung do cùng chia sẻ kiến thức, áp lực tiến độ hoặc quyết định thiết kế trước đó. Nên luân phiên reviewer và tránh để cùng một người luôn kiểm tra cùng một loại nội dung.

### 3.3. Rà soát liên nhóm hoặc bởi chuyên gia độc lập

Người rà soát thuộc nhóm khác hoặc không tham gia trực tiếp vào việc tạo sản phẩm công việc. Họ có thể mang đến cách nhìn mới, kinh nghiệm từ hệ thống khác hoặc hiểu biết chuyên sâu về bảo mật, dữ liệu, hiệu năng, vận hành và nghiệp vụ.

Mức độc lập thường cao hơn, nhưng reviewer cần được cung cấp bối cảnh, thuật ngữ, mục tiêu và tiêu chí đánh giá. Nếu thiếu thông tin, họ có thể đưa ra nhận xét không phù hợp với giới hạn hoặc quyết định đã thống nhất của dự án.

### 3.4. Đánh giá độc lập bên ngoài nhóm hoặc tổ chức

Một bên đánh giá độc lập, kiểm toán viên, chuyên gia bên ngoài hoặc tổ chức đánh giá có thể được mời khi cần bằng chứng khách quan cao, chuyên môn đặc biệt hoặc đáp ứng yêu cầu hợp đồng, pháp lý và tuân thủ.

Hình thức này thường tốn thời gian và chi phí hơn, cần chuẩn bị hồ sơ và phạm vi rõ ràng. Người đánh giá bên ngoài cũng cần hiểu bối cảnh và tiêu chí áp dụng; tính độc lập về tổ chức không tự động bảo đảm mọi kết luận đều chính xác.

Có thể tóm tắt phổ độc lập như sau:

| Mức | Người rà soát | Giá trị thường có | Giới hạn cần quản lý |
|---|---|---|---|
| 1 | Chính tác giả | Nhanh, hiểu ý định và sửa ngay | Dễ bỏ qua giả định hoặc lỗi do chính mình tạo ra |
| 2 | Đồng nghiệp cùng nhóm | Hiểu bối cảnh và quy ước nội bộ | Có thể chia sẻ điểm mù và áp lực chung |
| 3 | Người từ nhóm khác/chuyên gia độc lập | Góc nhìn mới và chuyên môn bổ sung | Cần thời gian tiếp nhận bối cảnh, điều phối lịch |
| 4 | Bên đánh giá độc lập bên ngoài | Khoảng cách tổ chức lớn, phù hợp yêu cầu đánh giá đặc biệt | Chi phí, thời gian và yêu cầu hồ sơ cao hơn |

Đây là cách mô tả thực hành, không phải thang xếp hạng chất lượng tuyệt đối. Mức phù hợp phụ thuộc mục tiêu, nội dung và rủi ro của cuộc rà soát.

## 4. Độc lập có nhiều chiều

Không nên xem độc lập là một nhãn đơn giản “có” hoặc “không”. Có thể đánh giá ít nhất các chiều sau:

- **Độc lập với tác giả:** Reviewer có trực tiếp viết hoặc quyết định nội dung đang được rà soát không?
- **Độc lập về tổ chức:** Reviewer có thuộc cùng nhóm, cùng tuyến quản lý hoặc cùng đơn vị chịu trách nhiệm về kết quả không?
- **Độc lập về chuyên môn và tư duy:** Reviewer có thể chất vấn các giả định, cách tiếp cận và quyết định kỹ thuật mà không bị ràng buộc bởi việc bảo vệ lựa chọn trước đó không?
- **Độc lập trong phê duyệt:** Người đưa ra quyết định chấp nhận có tách biệt với người thực hiện và người sửa nội dung không, khi quy trình yêu cầu?
- **Độc lập về lợi ích:** Có xung đột lợi ích, mục tiêu cá nhân hoặc áp lực nào có thể ảnh hưởng đến nhận xét không?

Ví dụ, một chuyên gia bảo mật ở nhóm khác có thể độc lập về tổ chức và không phải tác giả, nhưng vẫn chịu áp lực tiến độ từ cùng một chương trình phát hành. Một kiểm toán viên bên ngoài có thể độc lập về tổ chức nhưng không có đủ hiểu biết về kiến trúc nội bộ để đánh giá chi tiết một quyết định kỹ thuật. Vì vậy, cần mô tả loại độc lập cần có thay vì chỉ ghi “reviewer độc lập”.

## 5. Chọn mức độc lập dựa trên mục tiêu và rủi ro

Mức độc lập nên tương xứng với hậu quả nếu sai và quyết định mà kết quả rà soát hỗ trợ. Hãy xem xét các yếu tố:

1. **Mức độ ảnh hưởng:** Sai sót có thể gây mất dữ liệu, thiệt hại tài chính, gián đoạn dịch vụ, ảnh hưởng an toàn hoặc vi phạm tuân thủ đến mức nào?
2. **Độ phức tạp và mới lạ:** Nội dung có kiến trúc mới, thuật toán khó, tích hợp nhiều hệ thống hoặc yêu cầu chưa ổn định không?
3. **Khả năng phát hiện sau này:** Nếu bỏ sót, lỗi có dễ phát hiện ở giai đoạn tiếp theo hay chỉ xuất hiện trong môi trường sử dụng?
4. **Mức độ bất định:** Có nhiều giả định, thiếu dữ liệu hoặc bất đồng về cách hiểu yêu cầu không?
5. **Yêu cầu bắt buộc:** Hợp đồng, chính sách nội bộ, tiêu chuẩn hoặc quy định có yêu cầu người đánh giá hay người phê duyệt độc lập không?
6. **Khả năng bố trí:** Có reviewer phù hợp, thời gian chuẩn bị và nguồn lực cần thiết không?

Ma trận gợi ý:

| Bối cảnh rà soát | Mức độc lập thường phù hợp | Ví dụ |
|---|---|---|
| Bản nháp nội bộ, thay đổi nhỏ, hậu quả thấp | Tác giả tự kiểm tra kết hợp đồng nghiệp cùng nhóm | Sửa lỗi chính tả hoặc cập nhật hướng dẫn nội bộ |
| Yêu cầu hoặc thiết kế có ảnh hưởng đến nhiều thành phần | Đồng cấp và ít nhất một reviewer liên nhóm hoặc chuyên gia liên quan | Thay đổi mô hình đơn hàng được nhiều dịch vụ sử dụng |
| Logic thanh toán, phân quyền hoặc xử lý dữ liệu nhạy cảm | Reviewer chuyên môn độc lập với tác giả; cân nhắc thêm người phê duyệt tách biệt | Thay đổi quy tắc hoàn tiền hoặc quyền xem dữ liệu khách hàng |
| Nội dung thuộc phạm vi kiểm toán, hợp đồng hoặc quy định đặc thù | Mức độc lập theo yêu cầu chính thức, có thể gồm đánh giá bên ngoài | Hồ sơ kiểm soát cần được bên có thẩm quyền xác nhận |

Ma trận chỉ là điểm khởi đầu. Nhóm phải xác định tiêu chí cụ thể và kiểm tra yêu cầu bắt buộc của tổ chức. Một rủi ro nghiêm trọng không thể được hạ mức độc lập chỉ vì lịch đang gấp; nếu không bố trí được reviewer cần thiết, phải ghi nhận giới hạn và chuyển quyết định cho người có thẩm quyền.

## 6. Chọn reviewer theo năng lực và góc nhìn

Reviewer cần có kiến thức phù hợp với mục tiêu rà soát. Có thể dùng ma trận năng lực để xác định ai cần tham gia:

| Khía cạnh cần rà soát | Năng lực phù hợp | Câu hỏi tiêu biểu |
|---|---|---|
| Nghiệp vụ | Hiểu quy trình và quy tắc sản phẩm | Luồng có phản ánh đúng chính sách và trường hợp ngoại lệ không? |
| Kiến trúc và thiết kế | Hiểu thành phần, ranh giới và phụ thuộc | Thiết kế có nhất quán, mở rộng và tích hợp được không? |
| Mã nguồn và tiêu chuẩn kỹ thuật | Thành thạo ngôn ngữ, framework và quy ước | Có lỗi logic, xử lý ngoại lệ hoặc vấn đề bảo trì nào không? |
| Bảo mật và quyền riêng tư | Hiểu mối đe dọa, kiểm soát truy cập và xử lý dữ liệu | Có đường truy cập trái phép hoặc dữ liệu nhạy cảm bị lộ không? |
| Kiểm thử và chất lượng | Hiểu kỹ thuật kiểm thử, tiêu chí và rủi ro | Yêu cầu có thể kiểm chứng và có đủ điều kiện chấp nhận không? |
| Vận hành và độ tin cậy | Hiểu triển khai, giám sát, sao lưu và phục hồi | Có thể triển khai, quan sát và phục hồi khi có sự cố không? |
| Khả năng sử dụng và truy cập | Hiểu người dùng, thiết kế tương tác và tiêu chuẩn tiếp cận | Người dùng mục tiêu có thể hiểu và hoàn thành tác vụ không? |

Không cần mời mọi chuyên gia vào mọi cuộc rà soát. Hãy chọn người theo câu hỏi cần trả lời. Với tài liệu yêu cầu thanh toán, có thể cần chủ sản phẩm, chuyên gia thanh toán, QA và bảo mật; với thay đổi cấu trúc dữ liệu, có thể cần kiến trúc sư, lập trình viên phụ trách dữ liệu và vận hành.

Ngoài chuyên môn, cần xem xét khả năng phản biện, sự cẩn thận, kỹ năng diễn đạt và thời gian sẵn sàng. Reviewer giỏi không chỉ tìm lỗi mà còn giải thích rõ vị trí, tác động và lý do phát hiện quan trọng. Họ cần tôn trọng tác giả và tập trung vào sản phẩm công việc, tránh biến rà soát thành đánh giá cá nhân.

## 7. Phân công và chuẩn bị cuộc rà soát

Trước khi gửi lời mời, người điều phối hoặc chủ sở hữu rà soát cần xác định:

- Mục tiêu: tìm lỗi, xác nhận tuân thủ, đánh giá tính khả thi hay đạt quyết định phê duyệt?
- Đối tượng: tài liệu hoặc phần nội dung nào thuộc phạm vi?
- Tiêu chí: quy tắc, checklist, tiêu chuẩn hoặc yêu cầu nào sẽ được dùng?
- Thành phần: ai là tác giả, reviewer, người điều phối, người ghi nhận và người phê duyệt?
- Mức độc lập: cần tách khỏi tác giả ở chiều nào và vì sao?
- Khối lượng: số trang, số dòng mã, số yêu cầu hoặc phạm vi thay đổi cần xem xét?
- Thời gian: hạn chuẩn bị, thời lượng họp và thời hạn xử lý phát hiện?
- Bằng chứng: phát hiện và quyết định sẽ được lưu ở đâu, ai có quyền truy cập?

Chỉ định rõ phần nội dung cho từng reviewer. Ví dụ, chuyên gia bảo mật xem xét luồng xác thực và phân quyền; QA xem xét tính kiểm chứng và các trường hợp ngoại lệ; chủ sản phẩm xác nhận quy tắc nghiệp vụ. Phân công theo chủ đề giúp tránh mọi người cùng đọc một phần trong khi phần quan trọng khác không ai phụ trách.

Reviewer nên nhận tài liệu đủ sớm, cùng với mục tiêu, phạm vi, phiên bản, tiêu chí và hướng dẫn ghi nhận phát hiện. Tài liệu cần ở trạng thái phù hợp để rà soát; nếu thay đổi lớn trong lúc review, người điều phối cần xác định có phải cập nhật phiên bản và bắt đầu lại một phần hoạt động hay không.

## 8. Trách nhiệm trong các giai đoạn rà soát

Một quy trình phổ biến gồm lập kế hoạch, chuẩn bị cá nhân, trao đổi hoặc họp, sửa đổi và theo dõi. Mức nghiêm ngặt tùy loại review.

| Giai đoạn | Tác giả | Reviewer | Điều phối/ghi nhận |
|---|---|---|---|
| Lập kế hoạch | Cung cấp bối cảnh và phiên bản cần xem | Xác nhận năng lực, thời gian và xung đột lợi ích | Chốt mục tiêu, phạm vi, người tham gia và lịch |
| Chuẩn bị | Làm rõ thuật ngữ và tài liệu tham chiếu | Đọc trước, dùng checklist và ghi nhận điểm nghi vấn | Cung cấp tài liệu, hướng dẫn và tiêu chí |
| Rà soát | Giải thích ý định khi được hỏi | Đưa ra nhận xét dựa trên bằng chứng | Giữ trao đổi đúng mục tiêu và ghi nhận phát hiện |
| Sửa đổi | Phân loại và xử lý phát hiện được chấp nhận | Làm rõ nhận xét hoặc kiểm tra lại khi được giao | Theo dõi người phụ trách và thời hạn |
| Kết thúc | Cập nhật trạng thái nội dung | Xác nhận phần cần kiểm tra lại đã được giải quyết nếu được yêu cầu | Kiểm tra tiêu chí kết thúc và lưu kết quả |

Reviewer nên phân biệt phát hiện bắt buộc sửa, câu hỏi cần làm rõ, đề xuất cải tiến và ý kiến mang tính sở thích. Người điều phối giúp nhóm tránh tranh luận về phong cách khi mục tiêu là tìm sai lệch có ảnh hưởng đến chất lượng. Nếu không thống nhất, ghi lại quan điểm, căn cứ và người có quyền quyết định.

Tác giả chịu trách nhiệm sửa sản phẩm công việc và phản hồi cách xử lý. Reviewer có thể xác nhận việc sửa có giải quyết phát hiện hay không, nhưng không tự ý thay đổi nội dung gốc nếu không được giao vai trò đó. Người phê duyệt quyết định chấp nhận hoặc từ chối theo thẩm quyền và tiêu chí đã xác định.

## 9. Khác biệt về phân công giữa các hình thức review

Các hình thức rà soát có mục tiêu và mức chính thức khác nhau, vì vậy thành phần tham gia cũng khác.

| Hình thức | Cách tổ chức | Thành phần thường gặp |
|---|---|---|
| Rà soát không chính thức (informal review) | Trao đổi nhanh, có thể qua pull request hoặc nhận xét trực tiếp | Tác giả và một hoặc vài đồng nghiệp |
| Walkthrough | Tác giả dẫn người tham gia đi qua nội dung hoặc luồng thiết kế để nhận phản hồi | Tác giả trình bày, reviewer đặt câu hỏi, người ghi nhận nếu cần |
| Rà soát kỹ thuật (technical review) | Đánh giá tính đúng đắn, khả thi và phù hợp kỹ thuật theo tiêu chí | Chuyên gia kỹ thuật, người hiểu nghiệp vụ, người điều phối |
| Inspection | Quy trình có cấu trúc, chuẩn bị cá nhân, ghi nhận và theo dõi phát hiện chặt chẽ | Tác giả, moderator, reviewer, recorder và các vai trò khác theo quy trình |

Tên gọi và vai trò cụ thể có thể thay đổi theo tổ chức hoặc tiêu chuẩn áp dụng. Không nên gọi một cuộc họp đọc tài liệu đơn giản là inspection nếu không thực hiện các bước và trách nhiệm tương ứng. Hãy chọn mức chính thức dựa trên mục tiêu, rủi ro và yêu cầu lưu hồ sơ.

## 10. Quản lý xung đột lợi ích và tính khách quan

Một reviewer có thể bị ảnh hưởng bởi lợi ích hoặc áp lực mà họ khó nhận ra. Ví dụ, người trực tiếp đề xuất một thiết kế có thể ngại chỉ ra giả định sai; người chịu KPI về tiến độ có thể muốn bỏ qua phát hiện làm chậm phát hành; một nhà cung cấp có thể đánh giá sản phẩm do chính họ cung cấp.

Để giảm ảnh hưởng:

- Chỉ định reviewer không phải tác giả hoặc người phê duyệt trước đó khi mức độc lập yêu cầu.
- Luân phiên người rà soát để tránh phụ thuộc lâu dài vào một góc nhìn.
- Cho reviewer thời gian đọc độc lập trước cuộc họp, tránh để ý kiến đầu tiên chi phối mọi người.
- Yêu cầu nêu căn cứ, tiêu chí hoặc bằng chứng cho phát hiện quan trọng.
- Ghi nhận xung đột lợi ích và cách xử lý, chẳng hạn bổ sung reviewer hoặc tách quyền phê duyệt.
- Tạo môi trường trao đổi tôn trọng, tập trung vào nội dung và cho phép nêu ý kiến khác biệt.

Khách quan không có nghĩa là mọi reviewer phải đồng ý. Bất đồng có thể cho thấy yêu cầu chưa rõ hoặc tiêu chí chưa đầy đủ. Nhóm nên ghi lại điểm chưa thống nhất và chuyển cho người có thẩm quyền giải quyết, thay vì xóa bỏ nhận xét chỉ vì không đạt đồng thuận.

## 11. Ví dụ: rà soát thay đổi trong luồng thanh toán

Giả sử nhóm chuẩn bị thay đổi quy tắc hoàn tiền và trạng thái đơn hàng. Một lỗi có thể khiến khách hàng được hoàn tiền hai lần hoặc đơn hàng chuyển sang trạng thái sai. Nhóm xác định mục tiêu rà soát là kiểm tra tính nhất quán của quy tắc nghiệp vụ, thiết kế trạng thái, quyền thực hiện hoàn tiền và khả năng kiểm chứng.

Phân công có thể như sau:

| Người tham gia | Góc nhìn được giao | Lý do |
|---|---|---|
| Tác giả là lập trình viên phụ trách thanh toán | Giải thích thay đổi, phụ thuộc và giả định thiết kế | Nắm chi tiết triển khai và cung cấp bối cảnh |
| Chủ sản phẩm/chuyên gia nghiệp vụ | Kiểm tra chính sách hoàn tiền, trường hợp một phần và ngoại lệ | Xác nhận quy tắc đúng nhu cầu và chính sách |
| QA độc lập với tác giả | Kiểm tra trạng thái, trường hợp biên và khả năng viết ca kiểm thử | Tìm khoảng trống trong yêu cầu và bằng chứng |
| Chuyên gia bảo mật | Kiểm tra quyền, xác thực và dấu vết thao tác nhạy cảm | Đánh giá rủi ro truy cập và lạm dụng |
| Kiến trúc sư hoặc kỹ sư tích hợp | Kiểm tra đồng bộ với cổng thanh toán, kho dữ liệu và dịch vụ đơn hàng | Đánh giá tác động xuyên hệ thống |
| Người điều phối | Giữ phạm vi, ghi nhận phát hiện và theo dõi xử lý | Bảo đảm quy trình và trách nhiệm rõ ràng |

Trong trường hợp này, rà soát đồng cấp đơn thuần có thể chưa đủ vì rủi ro tài chính và phân quyền đáng kể. Reviewer QA và bảo mật nên độc lập với tác giả; nếu chính sách tổ chức yêu cầu, người phê duyệt phát hành hoặc kiểm soát rủi ro cũng cần tách biệt. Chuyên gia nghiệp vụ có thể thuộc cùng nhóm sản phẩm nhưng vẫn cung cấp góc nhìn cần thiết về quy tắc.

Kết quả review cần ghi nhận các trường hợp như hoàn tiền toàn phần, hoàn tiền một phần, yêu cầu lặp, giao dịch đang xử lý, giao dịch bị từ chối, quyền của nhân viên và việc đối soát. Mỗi phát hiện có người xử lý, thời hạn và trạng thái. Nếu còn bất đồng về cách xử lý giao dịch đến muộn, cần đưa ra quyết định nghiệp vụ hoặc kỹ thuật có thẩm quyền trước khi kết luận rà soát hoàn tất.

## 12. Đánh giá chất lượng hoạt động rà soát

Số lượng người tham gia hoặc số nhận xét không tự chứng minh một cuộc rà soát có chất lượng. Hãy đánh giá liệu đúng chuyên môn đã tham gia, mục tiêu có được đáp ứng và phát hiện có được xử lý hay không.

Một số chỉ báo có thể theo dõi:

- Tỷ lệ sản phẩm công việc rủi ro cao được rà soát bởi người có năng lực phù hợp.
- Tỷ lệ yêu cầu hoặc phần nội dung quan trọng có reviewer được phân công rõ.
- Số phát hiện theo loại và mức độ ảnh hưởng.
- Tỷ lệ phát hiện được xử lý đúng hạn hoặc có quyết định chấp nhận rõ ràng.
- Số lỗi quan trọng được phát hiện ở giai đoạn sau dù có review trước đó.
- Thời gian chuẩn bị, thời gian rà soát và thời gian xử lý phát hiện.
- Tỷ lệ cuộc rà soát phải làm lại do sai phiên bản, thiếu bối cảnh hoặc thiếu reviewer cần thiết.

Các chỉ báo cần được xem cùng bối cảnh. Số lỗi phát hiện cao có thể phản ánh reviewer hiệu quả hoặc chất lượng đầu vào còn thấp. Số lỗi phát hiện thấp có thể do sản phẩm tốt hoặc cuộc rà soát quá hời hợt. Không nên đặt mục tiêu số lượng nhận xét khiến reviewer tạo ra góp ý không cần thiết.

Sau một số cuộc rà soát, nhóm có thể xem xét lỗi lọt qua, phản hồi của tác giả và reviewer, độ phù hợp của checklist và thời gian thực tế. Dùng kết quả để điều chỉnh cách phân công, bổ sung năng lực còn thiếu hoặc tăng mức độc lập ở khu vực rủi ro cao.

## 13. Những sai lầm thường gặp

- **Chỉ mời người có chức danh cao:** Chức danh không bảo đảm người đó hiểu nội dung hoặc có thời gian chuẩn bị.
- **Chỉ mời người cùng nhóm:** Có thể thiếu góc nhìn mới hoặc bỏ qua giả định chung.
- **Chọn người độc lập nhưng thiếu chuyên môn:** Khoảng cách tổ chức không thay thế hiểu biết nghiệp vụ và kỹ thuật.
- **Mời quá nhiều người:** Tăng chi phí phối hợp, làm trách nhiệm mờ và có thể kéo dài quyết định.
- **Không chỉ định phạm vi:** Reviewer cùng đọc một phần, trong khi các phần quan trọng không được ai xem xét.
- **Không làm rõ quyền quyết định:** Nhận xét, đề xuất và quyết định phê duyệt bị trộn lẫn.
- **Để tác giả tự đóng mọi phát hiện:** Các vấn đề có tác động lớn có thể bị bỏ qua nếu không có xác nhận phù hợp.
- **Nhầm độc lập với đối đầu:** Reviewer cần phản biện nội dung trên cơ sở bằng chứng, không tìm lỗi để quy trách nhiệm cá nhân.
- **Không ghi nhận xung đột lợi ích:** Áp lực tiến độ hoặc lợi ích liên quan có thể làm giảm tính khách quan.
- **Không theo dõi sau cuộc họp:** Phát hiện được nêu ra nhưng không có người xử lý, thời hạn hoặc xác nhận hoàn tất.

## 14. Checklist phân công reviewer

Trước khi bắt đầu rà soát, người điều phối có thể dùng checklist sau:

- [ ] Mục tiêu, phạm vi và tiêu chí rà soát đã rõ.
- [ ] Phiên bản tài liệu hoặc sản phẩm công việc đã được xác định.
- [ ] Các khía cạnh nghiệp vụ, kỹ thuật và chất lượng quan trọng đã có người phụ trách.
- [ ] Reviewer có đủ kiến thức và thời gian chuẩn bị.
- [ ] Mức độc lập phù hợp với rủi ro và yêu cầu bắt buộc.
- [ ] Xung đột lợi ích hoặc quan hệ với tác giả đã được xem xét.
- [ ] Vai trò điều phối, ghi nhận, sửa đổi và phê duyệt đã rõ.
- [ ] Cách ghi phát hiện, người phụ trách và thời hạn xử lý đã thống nhất.
- [ ] Có tiêu chí kết thúc và cách xử lý các điểm chưa thống nhất.

Phân công reviewer tốt giúp kiểm thử tĩnh tạo ra phản hồi đúng chuyên môn và đủ khách quan cho quyết định chất lượng. Khi nhóm xác định rõ mục tiêu, chọn người có năng lực phù hợp, đặt mức độc lập theo rủi ro và theo dõi phát hiện đến khi có kết quả, hoạt động rà soát trở thành một phần có thể quản lý và truy vết của chiến lược kiểm thử.
