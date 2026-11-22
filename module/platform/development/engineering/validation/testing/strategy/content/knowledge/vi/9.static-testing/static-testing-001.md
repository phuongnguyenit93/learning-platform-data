# Lựa chọn sản phẩm công việc cần rà soát trước khi thực thi

Kiểm thử tĩnh giúp phát hiện điểm không rõ ràng, mâu thuẫn, thiếu sót và lỗi tiềm ẩn trong sản phẩm công việc trước khi phần mềm được thực thi. Sản phẩm công việc có thể là yêu cầu, câu chuyện người dùng, tiêu chí chấp nhận, thiết kế, mô hình dữ liệu, hợp đồng API, mã nguồn, kịch bản kiểm thử, dữ liệu kiểm thử hoặc cấu hình triển khai. Rà soát đúng tài liệu vào đúng thời điểm có thể ngăn lỗi lan sang các giai đoạn sau, giảm chi phí sửa chữa và tạo cơ sở đáng tin cậy cho kiểm thử động.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, nhóm cần lựa chọn sản phẩm công việc dựa trên mục tiêu xác thực, rủi ro, mức độ thay đổi và khả năng phát hiện lỗi. Không phải mọi tài liệu đều cần cùng hình thức hoặc mức độ rà soát. Một quyết định tốt giải thích được sản phẩm nào cần rà soát, vì sao, ai tham gia, kiểm tra điều gì và bằng chứng nào cho thấy vấn đề đã được xử lý.

## 1. Hiểu sản phẩm công việc và kiểm thử tĩnh

### Sản phẩm công việc là gì?

Sản phẩm công việc (work product) là bất kỳ đầu ra nào được tạo ra trong quá trình xác định, thiết kế, xây dựng, kiểm thử, triển khai hoặc vận hành sản phẩm. Nó có thể là tài liệu, mô hình, mã, cấu hình, dữ liệu hoặc kết quả phân tích.

Một số nhóm sản phẩm công việc thường gặp:

| Giai đoạn | Sản phẩm công việc | Ví dụ |
|---|---|---|
| Khám phá và yêu cầu | Mục tiêu, yêu cầu, user story, tiêu chí chấp nhận | Quy tắc nghiệp vụ, luồng người dùng, điều kiện hoàn thành |
| Phân tích và thiết kế | Kiến trúc, sơ đồ luồng, thiết kế giao diện, mô hình dữ liệu | Sequence diagram, ERD, prototype, phân quyền |
| Tích hợp | Đặc tả API, schema, hợp đồng sự kiện, cấu hình kết nối | OpenAPI, JSON schema, webhook contract |
| Phát triển | Mã nguồn, migration, script, cấu hình | Pull request, truy vấn SQL, feature flag |
| Kiểm thử | Chiến lược, kế hoạch, test case, checklist, dữ liệu | Test charter, test oracle, test data set |
| Phát hành và vận hành | Runbook, hướng dẫn triển khai, cảnh báo, tài liệu hỗ trợ | Kế hoạch rollback, dashboard, hướng dẫn xử lý sự cố |

Một sản phẩm công việc có thể được dùng bởi nhiều nhóm. Ví dụ, tiêu chí chấp nhận vừa định hướng phát triển vừa là cơ sở để thiết kế kiểm thử và nghiệm thu. Vì vậy, lỗi trong một tài liệu nền tảng có thể lan đến nhiều đầu ra khác.

### Kiểm thử tĩnh là gì?

Kiểm thử tĩnh đánh giá sản phẩm công việc mà không cần thực thi phần mềm đang được kiểm tra. Hoạt động này có thể bao gồm:

- Rà soát thủ công tài liệu, mô hình, mã nguồn hoặc cấu hình.
- Walkthrough để tác giả trình bày nội dung và người tham gia cùng phân tích.
- Technical review hoặc inspection theo quy trình có cấu trúc.
- Phân tích tĩnh mã nguồn bằng công cụ để phát hiện mẫu lỗi, vấn đề chất lượng hoặc rủi ro bảo mật.
- Kiểm tra định dạng, schema, quy tắc và tính nhất quán tự động.

Kiểm thử tĩnh có thể bắt đầu từ yêu cầu và tiếp tục trong suốt vòng đời phát triển. Nó giúp phát hiện lỗi trước khi tạo bản chạy, dữ liệu thực hoặc môi trường tích hợp.

### Phân biệt kiểm thử tĩnh và kiểm thử động

| Khía cạnh | Kiểm thử tĩnh | Kiểm thử động |
|---|---|---|
| Đối tượng | Sản phẩm công việc và cấu trúc của nó | Phần mềm đang thực thi |
| Cách thực hiện | Đọc, phân tích, kiểm tra quy tắc hoặc dùng công cụ phân tích | Chạy phần mềm với đầu vào và quan sát kết quả |
| Thời điểm | Có thể thực hiện ngay khi sản phẩm công việc được tạo | Khi có thành phần có thể chạy trong môi trường phù hợp |
| Ví dụ | Rà soát yêu cầu, code review, phân tích tĩnh | Unit test, API test, system test, UAT |
| Loại vấn đề thường phát hiện | Mơ hồ, thiếu yêu cầu, mâu thuẫn, sai cấu trúc, code smell, luồng dữ liệu nguy hiểm | Hành vi sai khi chạy, lỗi tích hợp, hiệu năng, lỗi phụ thuộc môi trường |
| Giới hạn | Không chứng minh hành vi thực tế của hệ thống | Có thể không bao phủ mọi đường đi hoặc mọi trạng thái |

Hai cách tiếp cận bổ trợ cho nhau. Một yêu cầu rõ ràng vẫn có thể được triển khai sai; mã nguồn không có cảnh báo phân tích tĩnh vẫn có thể hoạt động sai trong môi trường thực tế. Rà soát tĩnh không thay thế kiểm thử động, và kiểm thử động cũng không thể bù hoàn toàn cho yêu cầu thiếu hoặc mơ hồ.

## 2. Vì sao phải lựa chọn sản phẩm công việc để rà soát

### Tối ưu thời điểm phát hiện lỗi

Chi phí sửa lỗi thường tăng khi lỗi đã lan sang nhiều sản phẩm công việc hoặc được phát hiện sau khi triển khai. Ví dụ, nếu quy tắc tính phí sai ngay trong yêu cầu, nhóm có thể sửa tiêu chí và thiết kế trước khi viết mã. Nếu chỉ phát hiện sau khi đã xây dựng, tích hợp, tạo dữ liệu và kiểm thử, phạm vi sửa chữa có thể lớn hơn.

Rà soát sớm giúp:

- Làm rõ mục tiêu và tiêu chí trước khi triển khai.
- Phát hiện mâu thuẫn giữa yêu cầu, thiết kế và hợp đồng.
- Giảm việc viết lại mã hoặc kịch bản do hiểu sai.
- Phát hiện sớm rủi ro bảo mật, quyền riêng tư và vận hành.
- Tạo cơ sở truy vết từ nhu cầu đến kiểm thử và nghiệm thu.

### Tập trung vào nơi có nguy cơ và tác động lớn

Nguồn lực rà soát có giới hạn. Nếu mọi tài liệu đều được rà soát cùng độ sâu, nhóm có thể tốn thời gian vào đầu ra ít quan trọng trong khi sản phẩm có rủi ro cao chưa được xem xét.

Các yếu tố làm tăng nhu cầu rà soát gồm:

- Sai sót có thể gây hậu quả nghiêm trọng cho người dùng hoặc doanh nghiệp.
- Sản phẩm công việc là đầu vào cho nhiều nhóm hoặc nhiều giai đoạn.
- Nội dung phức tạp, mới, khó hiểu hoặc có nhiều giả định.
- Có thay đổi lớn về yêu cầu, kiến trúc, dữ liệu hoặc phụ thuộc.
- Đầu ra liên quan đến tiền, quyền truy cập, dữ liệu nhạy cảm, an toàn hoặc nghĩa vụ.
- Lỗi khó phát hiện bằng kiểm thử động hoặc khó khôi phục sau khi phát hành.

### Rà soát theo mục tiêu xác thực

Không phải sản phẩm công việc nào cũng cần được rà soát để tìm cùng một loại vấn đề. Ví dụ:

- Rà soát yêu cầu nhằm phát hiện mơ hồ, thiếu điều kiện, mâu thuẫn và tiêu chí không đo được.
- Rà soát thiết kế nhằm phát hiện thiếu luồng, điểm lỗi, ranh giới trách nhiệm và vấn đề kiến trúc.
- Rà soát hợp đồng API nhằm phát hiện sai schema, ngữ nghĩa dữ liệu và quy tắc lỗi.
- Rà soát mã nguồn nhằm phát hiện lỗi logic dễ thấy, độ phức tạp, vấn đề bảo mật và vi phạm quy ước.
- Rà soát test case nhằm phát hiện thiếu tình huống, oracle không rõ và dữ liệu không phù hợp.
- Rà soát runbook nhằm phát hiện bước vận hành thiếu, điều kiện rollback mơ hồ và thiếu đầu mối hỗ trợ.

Mục tiêu rà soát phải gắn với sản phẩm công việc và rủi ro cụ thể, thay vì chỉ yêu cầu người tham gia “đọc qua xem có vấn đề không”.

## 3. Xác định tiêu chí lựa chọn

### Đánh giá mức độ quan trọng đối với sản phẩm

Trước tiên, xác định sản phẩm công việc có ảnh hưởng thế nào đến mục tiêu và hành trình:

- Có mô tả hoặc quyết định một hành trình cốt lõi không?
- Có định nghĩa quy tắc nghiệp vụ, dữ liệu hoặc quyền quan trọng không?
- Có ảnh hưởng đến nhiều thành phần hoặc nhóm sở hữu không?
- Có được dùng làm cơ sở cho phát triển, kiểm thử, nghiệm thu hoặc vận hành không?
- Nếu sai, phạm vi ảnh hưởng sẽ là một thành phần hay toàn bộ sản phẩm?

Sản phẩm công việc nền tảng thường đáng được ưu tiên vì sai sót của nó có thể lan truyền. Ví dụ, mô hình quyền truy cập sai có thể ảnh hưởng đến API, giao diện, dữ liệu và test case.

### Đánh giá khả năng và mức độ hậu quả của lỗi

Dùng cách đánh giá rủi ro đã thống nhất trong nhóm. Hãy xem xét:

- Khả năng sản phẩm công việc chứa lỗi hoặc thiếu sót.
- Mức tác động nếu lỗi không được phát hiện.
- Khả năng phát hiện lỗi bằng phương pháp khác.
- Mức độ khó khôi phục hoặc sửa sau khi sử dụng.
- Mức độ không chắc chắn của bằng chứng hiện có.

Không cần chấm điểm phức tạp cho mọi sản phẩm. Với các đầu ra nhỏ, checklist đơn giản có thể đủ. Với yêu cầu hoặc thiết kế có ảnh hưởng đến dữ liệu nhạy cảm, thanh toán hay quyền truy cập, cần đánh giá sâu hơn và có chuyên gia phù hợp.

### Đánh giá độ phức tạp và tính mới

Sản phẩm công việc cần rà soát kỹ hơn khi có một hoặc nhiều đặc điểm:

- Công nghệ, kiến trúc hoặc mô hình nghiệp vụ mới.
- Nhiều trạng thái, điều kiện và nhánh ngoại lệ.
- Nhiều nhóm cùng sở hữu hoặc phụ thuộc vào dịch vụ bên ngoài.
- Quy tắc dữ liệu hoặc quyền phức tạp.
- Tài liệu được tạo từ giả định chưa được xác minh.
- Người thực hiện thiếu kinh nghiệm với miền nghiệp vụ hoặc công nghệ.

Tính mới không tự động đồng nghĩa với rủi ro cao, nhưng làm giảm mức tin cậy của kinh nghiệm và dữ liệu lịch sử. Nhóm nên xem xét thêm bằng chứng và mời người có chuyên môn phù hợp.

### Đánh giá mức độ thay đổi

Một sản phẩm đã được rà soát trước đó vẫn có thể cần rà soát lại khi thay đổi đáng kể. Các dấu hiệu gồm:

- Thay đổi yêu cầu hoặc tiêu chí chấp nhận.
- Thay đổi cấu trúc dữ liệu, API hoặc schema sự kiện.
- Thay đổi thuật toán, quyền hoặc luồng nghiệp vụ.
- Thay đổi nhà cung cấp, phiên bản hoặc cấu hình tích hợp.
- Sửa lỗi nghiêm trọng hoặc tái cấu trúc khu vực nhạy cảm.
- Thay đổi ảnh hưởng đến tài liệu, hướng dẫn hoặc quy trình vận hành.

Phạm vi rà soát lại nên dựa trên phần thay đổi và các sản phẩm phụ thuộc. Không nhất thiết lặp lại toàn bộ review nếu thay đổi nhỏ, nhưng phải kiểm tra tác động lan truyền và các liên kết liên quan.

### Xem xét khả năng phát hiện bằng công cụ hoặc phương pháp khác

Một số lỗi dễ phát hiện tự động, chẳng hạn định dạng sai, schema không hợp lệ, vi phạm quy tắc lint hoặc tham chiếu bị thiếu. Một số vấn đề cần con người đánh giá, như yêu cầu có phù hợp nhu cầu, thông điệp có gây hiểu nhầm hay thiết kế có đáp ứng bối cảnh sử dụng.

Lựa chọn sản phẩm và phương pháp rà soát cần xem xét:

- Công cụ có thể kiểm tra chính xác điều gì?
- Công cụ có thể tạo cảnh báo sai hoặc bỏ sót loại lỗi nào?
- Cần chuyên gia nào để diễn giải kết quả?
- Có cần review thủ công bổ sung không?
- Có thể dùng cùng một bằng chứng cho nhiều mục tiêu mà không làm giảm độ tin cậy không?

Không nên xem việc công cụ chạy thành công là bằng chứng rằng toàn bộ sản phẩm công việc đã đúng.

## 4. Các sản phẩm công việc thường nên được rà soát

### Yêu cầu, user story và tiêu chí chấp nhận

Đây là đầu vào quan trọng vì nó định hướng thiết kế, phát triển và kiểm thử. Nên rà soát khi yêu cầu mới được tạo, thay đổi đáng kể hoặc dùng làm cơ sở cho một hành trình quan trọng.

Các điểm cần xem xét:

- Mục tiêu và đối tượng người dùng có rõ không?
- Phạm vi và điều kiện ngoài phạm vi có được nêu không?
- Thuật ngữ có nhất quán và không gây nhiều cách hiểu không?
- Quy tắc nghiệp vụ, điều kiện trước và trạng thái sau có đầy đủ không?
- Trường hợp lỗi, ngoại lệ và quyền truy cập có được mô tả không?
- Tiêu chí chấp nhận có quan sát và kiểm chứng được không?
- Có mâu thuẫn với yêu cầu, chính sách hoặc luồng khác không?

Ví dụ, yêu cầu “hệ thống gửi thông báo nhanh chóng” chưa thể kiểm thử nếu không định nghĩa loại thông báo, thời điểm bắt đầu tính, ngưỡng thời gian, điều kiện lỗi và cách xử lý khi nhà cung cấp không sẵn sàng.

### Kiến trúc, thiết kế và mô hình dữ liệu

Rà soát các đầu ra này trước khi xây dựng giúp phát hiện quyết định có thể tạo ảnh hưởng rộng:

- Thành phần và trách nhiệm có được phân chia rõ không?
- Luồng dữ liệu và luồng điều khiển có đầy đủ không?
- Ranh giới tin cậy, xác thực và phân quyền có được thể hiện không?
- Có điểm lỗi đơn, phụ thuộc vòng hoặc đường đi không thể phục hồi không?
- Mô hình dữ liệu có khóa, ràng buộc, tính duy nhất và quy tắc vòng đời phù hợp không?
- Thiết kế có đáp ứng tải, khả năng mở rộng, quan sát và phục hồi cần thiết không?
- Có tương thích với các hệ thống và phiên bản đang được hỗ trợ không?

Với sơ đồ, cần kiểm tra cả tính chính xác và mức độ dễ hiểu. Một sơ đồ đẹp nhưng thiếu luồng lỗi hoặc ranh giới sở hữu vẫn không đủ làm căn cứ thiết kế kiểm thử.

### Đặc tả API, schema và hợp đồng tích hợp

Các sản phẩm này cần được rà soát trước khi nhóm tiêu thụ và cung cấp triển khai độc lập. Kiểm tra:

- Endpoint, phương thức, kiểu dữ liệu và trường bắt buộc.
- Ngữ nghĩa của trường, đơn vị, múi giờ và giá trị mặc định.
- Mã lỗi, điều kiện retry, timeout và giới hạn sử dụng.
- Xác thực, phân quyền, phạm vi dữ liệu và cơ chế bảo vệ bí mật.
- Idempotency, thứ tự sự kiện, webhook và xử lý trùng.
- Quy tắc phiên bản, tương thích ngược và thông báo thay đổi.
- Ví dụ request/response có nhất quán với schema không?

Một hợp đồng thiếu quy tắc timeout hoặc trạng thái bất đồng bộ có thể khiến hai nhóm triển khai đúng theo cách hiểu riêng nhưng không tương thích khi tích hợp.

### Mã nguồn, migration và cấu hình

Rà soát mã nguồn trước khi hợp nhất hoặc phát hành có thể phát hiện lỗi logic, độ phức tạp, vấn đề bảo mật và rủi ro bảo trì. Các mục tiêu thường gồm:

- Logic có đúng với yêu cầu và tiêu chí chấp nhận không?
- Có xử lý đầu vào không tin cậy và dữ liệu biên không?
- Quyền truy cập có được kiểm tra tại ranh giới phù hợp không?
- Có nguy cơ lộ bí mật, dữ liệu cá nhân hoặc thông tin nhạy cảm trong log không?
- Có xử lý lỗi, timeout, transaction và tài nguyên đúng cách không?
- Migration có bảo toàn dữ liệu và có kế hoạch khôi phục phù hợp không?
- Cấu hình có giá trị mặc định an toàn và không chứa bí mật không?
- Mã có dễ hiểu, dễ kiểm thử và tuân thủ quy ước của dự án không?

Công cụ phân tích tĩnh, secret scanning, dependency scanning và lint có thể bổ sung cho review của con người. Kết quả công cụ cần được phân loại, xử lý false positive và liên kết với chính sách chất lượng.

### Kế hoạch, kịch bản và dữ liệu kiểm thử

Rà soát test plan và test case trước khi thực thi giúp tránh chạy một bộ kiểm thử thiếu mục tiêu hoặc không có oracle rõ ràng.

Kiểm tra:

- Mục tiêu kiểm thử có liên kết với yêu cầu và rủi ro không?
- Phạm vi, giả định, môi trường và phụ thuộc có rõ không?
- Điều kiện trước, bước thực hiện và kết quả mong đợi có đủ cụ thể không?
- Có tình huống bình thường, biên, lỗi và phục hồi phù hợp không?
- Dữ liệu có đại diện và có thể tạo lại không?
- Có tránh dùng dữ liệu nhạy cảm trái phép không?
- Kết quả có thể quan sát, ghi nhận và truy vết không?
- Tiêu chí dừng, đạt, thất bại và báo lỗi có thống nhất không?

Một test case ghi “kiểm tra đăng nhập thành công” nhưng không nêu tài khoản, trạng thái, bước thực hiện hoặc điều kiện thành công sẽ khó thực thi nhất quán.

### Tài liệu phát hành, vận hành và hỗ trợ

Rà soát các sản phẩm công việc vận hành trước khi bàn giao hoặc phát hành:

- Hướng dẫn triển khai có đúng thứ tự và điều kiện không?
- Cấu hình, secret và quyền được quản lý theo cách an toàn không?
- Có quy trình rollback, backup và restore phù hợp không?
- Dashboard và cảnh báo có chỉ ra tín hiệu cần hành động không?
- Runbook có bước chẩn đoán, người liên hệ và điều kiện leo thang không?
- Tài liệu hỗ trợ có mô tả trạng thái và cách khắc phục đúng không?
- Có xác định cách xử lý dữ liệu tồn đọng, giao dịch không rõ kết quả hoặc sự cố phụ thuộc không?

Nếu sản phẩm có hành trình trọng yếu, thiếu runbook hoặc hướng dẫn phục hồi có thể biến một lỗi kỹ thuật có thể kiểm soát thành sự cố kéo dài.

## 5. Ưu tiên sản phẩm công việc bằng ma trận lựa chọn

### Dùng tiêu chí thống nhất

Nhóm có thể chấm mức ưu tiên rà soát theo một số tiêu chí. Ví dụ thang 1–5:

| Tiêu chí | Câu hỏi định hướng |
|---|---|
| Tác động nếu sai | Lỗi trong sản phẩm này có thể gây hậu quả gì? |
| Khả năng có lỗi | Nội dung có phức tạp, mới, mơ hồ hoặc từng có lỗi tương tự không? |
| Mức độ thay đổi | Sản phẩm vừa thay đổi nhiều hoặc có phụ thuộc bị thay đổi không? |
| Mức lan truyền | Bao nhiêu thành phần, nhóm hoặc tài liệu khác dựa vào nó? |
| Khó phát hiện muộn | Nếu không rà soát bây giờ, lỗi có khó phát hiện hoặc khó sửa sau này không? |

Có thể dùng tổng điểm hoặc ma trận để sắp xếp danh sách, nhưng cần định nghĩa mức điểm và ngưỡng. Không nên nhân hoặc cộng các thang thứ bậc rồi xem kết quả như xác suất chính xác. Điểm số chỉ hỗ trợ thảo luận và ra quyết định.

### Ví dụ ma trận ưu tiên

| Sản phẩm công việc | Tác động nếu sai | Độ phức tạp/thay đổi | Mức lan truyền | Quyết định rà soát |
|---|---|---|---|---|
| Quy tắc tính phí và thuế | Cao | Trung bình | Cao | Rà soát nghiệp vụ và kỹ thuật trước triển khai |
| Mô hình quyền truy cập | Rất cao | Cao | Cao | Rà soát chuyên sâu với chủ sở hữu bảo mật |
| Hợp đồng webhook thanh toán | Rất cao | Cao | Cao | Review liên nhóm và kiểm tra schema tự động |
| Nội dung trợ giúp cho chức năng phụ | Thấp | Thấp | Thấp | Rà soát thông thường hoặc lấy mẫu |
| Test case cho hành trình đăng ký | Cao | Trung bình | Trung bình | Rà soát trước khi thực thi và xác nhận oracle |
| Runbook phục hồi dịch vụ | Cao | Cao | Trung bình | Review vận hành và diễn tập khi phù hợp |

Các mức trong bảng là ví dụ minh họa. Nhóm cần điều chỉnh theo sản phẩm, người dùng, nghĩa vụ và lịch sử lỗi thực tế. Một đầu ra có tác động rất cao vẫn có thể cần review bắt buộc dù các tiêu chí khác thấp.

### Chọn phạm vi rà soát khi sản phẩm lớn

Với sản phẩm công việc lớn, có thể chia theo phần, lấy mẫu hoặc tập trung vào các khu vực rủi ro cao. Việc lấy mẫu cần có cơ sở:

- Chọn phần có logic phức tạp hoặc thay đổi lớn.
- Chọn luồng xử lý dữ liệu nhạy cảm hoặc quyền quan trọng.
- Chọn các điểm tích hợp và chuyển giao giữa nhóm.
- Chọn các phần có lịch sử lỗi hoặc khó kiểm thử động.
- Bao gồm các trường hợp đại diện và một số nhánh ngoại lệ.

Lấy mẫu không phù hợp khi chính sách hoặc hậu quả yêu cầu kiểm tra toàn bộ, chẳng hạn một số kiểm soát bảo mật, quy tắc tài chính hoặc điều kiện nghiệm thu bắt buộc. Nếu chỉ rà soát một phần, phải ghi rõ phần đã xem và giới hạn của kết luận.

## 6. Chọn hình thức rà soát phù hợp với sản phẩm

### Rà soát không chính thức

Rà soát không chính thức phù hợp với đầu ra nhỏ, thay đổi ít rủi ro hoặc giai đoạn khám phá. Tác giả có thể nhờ đồng nghiệp đọc và phản hồi trực tiếp. Hình thức này nhanh, dễ tổ chức nhưng thường ít bằng chứng và ít kiểm soát hơn.

Cần ít nhất làm rõ mục tiêu đọc, người phản hồi và cách ghi nhận vấn đề quan trọng. Không nên dùng một cuộc trao đổi ngẫu nhiên làm bằng chứng duy nhất cho sản phẩm có hậu quả cao.

### Walkthrough

Trong walkthrough, tác giả dẫn người tham gia đi qua sản phẩm công việc, giải thích bối cảnh, quyết định và cách sử dụng. Hình thức này hữu ích khi nội dung mới, phức tạp hoặc cần thu thập nhiều góc nhìn.

Ví dụ, kiến trúc sư trình bày sơ đồ tích hợp để nhóm phát triển, QA và vận hành lần theo luồng dữ liệu, tìm điểm thiếu và thống nhất các tình huống lỗi. Người tham gia có thể đặt câu hỏi, nêu tình huống và ghi nhận vấn đề ngay trong buổi làm việc.

### Technical review

Technical review tập trung đánh giá tính phù hợp kỹ thuật, tính đúng đắn, khả năng bảo trì, tuân thủ tiêu chuẩn hoặc mức đáp ứng yêu cầu. Người rà soát cần có chuyên môn liên quan và hiểu tiêu chí đánh giá.

Ví dụ, nhóm bảo mật rà soát mô hình phân quyền; nhóm nền tảng rà soát hợp đồng API; nhóm dữ liệu rà soát migration và tính nhất quán.

### Inspection hoặc review có cấu trúc

Inspection thường có quy trình chặt chẽ hơn: xác định mục tiêu, vai trò, chuẩn bị độc lập, ghi nhận lỗi, phân loại, sửa chữa và xác minh lại. Hình thức này phù hợp với sản phẩm công việc quan trọng, phức tạp hoặc có yêu cầu tuân thủ.

Không phải mọi sản phẩm đều cần inspection chính thức. Hãy chọn mức nghiêm ngặt tương ứng với hậu quả nếu lỗi không được phát hiện và yêu cầu bằng chứng của tổ chức.

### Phân tích tĩnh tự động

Công cụ tự động có thể kiểm tra mã nguồn, cấu hình, schema, tài liệu hoặc phụ thuộc theo quy tắc định sẵn. Ví dụ:

- Linter và formatter để kiểm tra quy ước và cấu trúc mã.
- Static application security testing (SAST) để tìm mẫu mã có nguy cơ bảo mật.
- Secret scanning để phát hiện thông tin xác thực có thể bị đưa vào repository.
- Dependency scanning để tìm thư viện có lỗ hổng đã biết hoặc giấy phép cần xem xét.
- Type checker và compiler analysis để phát hiện sai kiểu hoặc tham chiếu không hợp lệ.
- Schema validator để kiểm tra dữ liệu và hợp đồng.
- Link checker hoặc tài liệu validator để phát hiện liên kết hỏng và cấu trúc không hợp lệ.

Công cụ chỉ kiểm tra được quy tắc và phạm vi mà nó hiểu. Nhóm cần quản lý cấu hình, phiên bản, mức nghiêm trọng, false positive và trường hợp ngoại lệ. Kết quả tự động không thay thế đánh giá ngữ nghĩa hoặc nhu cầu người dùng.

## 7. Xác định thời điểm và điều kiện rà soát

### Rà soát tại điểm sản phẩm công việc đủ trưởng thành

Rà soát quá sớm có thể không có đủ nội dung để đánh giá; quá muộn khiến lỗi đã lan sang các đầu ra khác. Hãy chọn thời điểm phù hợp với loại sản phẩm:

| Sản phẩm công việc | Thời điểm gợi ý | Điều kiện sẵn sàng |
|---|---|---|
| Yêu cầu và tiêu chí chấp nhận | Trước khi thiết kế hoặc phát triển dựa vào yêu cầu | Có mục tiêu, phạm vi và người dùng liên quan |
| Kiến trúc và thiết kế | Trước khi xây dựng thành phần phụ thuộc vào quyết định đó | Có luồng chính, ranh giới và giả định |
| Hợp đồng API/schema | Trước khi các bên triển khai độc lập | Có phiên bản, trường dữ liệu và quy tắc lỗi |
| Mã nguồn | Trước khi hợp nhất hoặc phát hành | Thay đổi đủ hoàn chỉnh, có mô tả và kiểm thử liên quan |
| Test plan/test case | Trước khi thực thi chiến dịch kiểm thử | Có mục tiêu, môi trường, dữ liệu và oracle |
| Runbook và tài liệu triển khai | Trước khi bàn giao hoặc triển khai | Có bước thực hiện, điều kiện và đầu mối hỗ trợ |

Một số sản phẩm cần nhiều vòng review. Ví dụ, kiến trúc có thể được review ở mức khái niệm trước, sau đó review chi tiết khi hợp đồng và thiết kế đã rõ hơn.

### Xác định điều kiện đầu vào và đầu ra

Trước khi bắt đầu, hãy thống nhất:

- Phiên bản sản phẩm công việc và phạm vi cần rà soát.
- Mục tiêu, tiêu chí hoặc checklist dùng để đánh giá.
- Người tham gia và vai trò của họ.
- Thời gian chuẩn bị và cách ghi nhận nhận xét.
- Các tài liệu tham chiếu có thẩm quyền.
- Cách phân loại vấn đề và người quyết định khi có bất đồng.

Sau review, cần có kết quả rõ ràng: vấn đề đã ghi nhận, mức độ, người xử lý, thời hạn, quyết định chấp nhận hoặc yêu cầu review lại. Với sản phẩm quan trọng, nên có dấu vết xác nhận phiên bản đã rà soát.

### Rà soát lại khi có thay đổi

Khi sản phẩm công việc thay đổi sau review, hãy đánh giá tác động của thay đổi đến kết luận trước đó. Một sửa đổi nhỏ về câu chữ có thể không cần review lại toàn bộ; một thay đổi schema, quyền hoặc quy tắc tính phí có thể yêu cầu review chuyên sâu và kiểm thử bổ sung.

Ghi rõ phiên bản, phần thay đổi, người phê duyệt và sản phẩm phụ thuộc cần xem lại. Tránh tiếp tục dùng kết quả review cũ như bằng chứng cho một phiên bản khác mà không đánh giá tác động.

## 8. Tổ chức review có hiệu quả

### Chọn người tham gia theo góc nhìn cần thiết

Người rà soát nên được chọn theo kiến thức và mục tiêu, không chỉ theo chức danh. Có thể cần:

- Người hiểu yêu cầu và mục tiêu kinh doanh.
- Chuyên gia nghiệp vụ để xác minh quy tắc và ngoại lệ.
- Kiến trúc sư hoặc lập trình viên để đánh giá thiết kế và mã.
- QA để đánh giá khả năng kiểm chứng, oracle và độ bao phủ.
- Chuyên gia bảo mật, quyền riêng tư hoặc tuân thủ khi có dữ liệu và nghĩa vụ liên quan.
- Vận hành và hỗ trợ để đánh giá khả năng triển khai, giám sát và phục hồi.
- Người dùng đại diện để đánh giá ngôn ngữ, hành trình và mức phù hợp với công việc.

Một người có thể đảm nhiệm nhiều góc nhìn, nhưng không nên giả định một cá nhân có thể đánh giá chuyên sâu mọi lĩnh vực.

### Chuẩn bị độc lập trước buổi review

Người tham gia cần có đủ thời gian đọc sản phẩm và tài liệu tham chiếu. Tác giả nên gửi phiên bản cụ thể, mục tiêu và câu hỏi cần tập trung. Review hiệu quả thường tránh để mọi người lần đầu đọc tài liệu ngay trong cuộc họp.

Với review có cấu trúc, người tham gia có thể ghi nhận vấn đề độc lập trước, sau đó cùng phân loại và thảo luận. Cách này giảm nguy cơ một ý kiến ban đầu ảnh hưởng quá mạnh đến những người còn lại.

### Ghi nhận vấn đề có thể hành động

Một phát hiện nên mô tả:

- Vị trí hoặc phần liên quan.
- Vấn đề quan sát được.
- Vì sao đây là vấn đề hoặc tiêu chí bị vi phạm.
- Hậu quả hoặc rủi ro có thể phát sinh.
- Đề xuất hoặc câu hỏi cần làm rõ.
- Mức độ ưu tiên và người xử lý.

Ví dụ: “Ở mục 4.2, tiêu chí chỉ nói ‘thông báo được gửi nhanh’ nhưng không nêu ngưỡng thời gian hoặc điểm bắt đầu tính. QA không thể xác định pass/fail; cần chủ sở hữu nghiệp vụ định nghĩa ngưỡng và hành vi khi nhà cung cấp chậm.”

Phân biệt lỗi với câu hỏi, đề xuất cải tiến và sở thích cá nhân. Không phải mọi góp ý đều là lỗi cần sửa. Hãy dùng tiêu chí đã thống nhất để quyết định.

### Theo dõi sửa chữa và đóng vấn đề

Sau review, tác giả hoặc người được giao cần xử lý từng phát hiện. Người rà soát hoặc người có thẩm quyền xác minh các vấn đề quan trọng đã được giải quyết. Nếu không sửa, phải ghi lý do và người chấp nhận rủi ro.

Một mục không nên được đánh dấu đóng chỉ vì đã có phản hồi. Cần xác minh nội dung mới đáp ứng tiêu chí, hoặc có quyết định chấp nhận ngoại lệ được ghi nhận.

## 9. Ví dụ: lựa chọn sản phẩm công việc cho hành trình đăng ký SaaS

Giả sử một sản phẩm SaaS cho phép quản trị viên tạo không gian làm việc, mời thành viên, phân quyền và bắt đầu công việc. Hành trình phụ thuộc vào dịch vụ định danh, email và nền tảng phân quyền nội bộ.

### Xác định các sản phẩm công việc cần rà soát

| Sản phẩm công việc | Rủi ro nếu sai | Hình thức rà soát | Thời điểm |
|---|---|---|---|
| User story và tiêu chí chấp nhận | Người dùng không biết trạng thái lời mời hoặc điều kiện hoàn tất | Walkthrough với nghiệp vụ và QA | Trước thiết kế |
| Mô hình quyền | Thành viên xem hoặc sửa dữ liệu ngoài phạm vi | Technical review với chuyên gia bảo mật | Trước triển khai |
| Hợp đồng API mời thành viên | Hai dịch vụ hiểu khác nhau về trạng thái và lỗi | Review liên nhóm và schema validation | Trước tích hợp |
| Mã xử lý lời mời | Gửi trùng, bỏ sót hoặc cấp quyền sai | Code review, SAST và unit test | Trước hợp nhất |
| Test case hành trình | Thiếu trường hợp hết hạn, gửi lại hoặc không đủ quyền | Review với QA và chủ sở hữu nghiệp vụ | Trước thực thi |
| Runbook hỗ trợ | Không xác định được lời mời bị kẹt hoặc xử lý lại an toàn | Review vận hành và walkthrough | Trước phát hành |

### Ví dụ phát hiện từ review

Giả sử tiêu chí chấp nhận chỉ nói “quản trị viên có thể mời thành viên”. Khi review, nhóm nhận ra chưa có quy định về:

- Địa chỉ email đã tồn tại trong hệ thống.
- Lời mời hết hạn và gửi lại.
- Người nhận đã là thành viên.
- Quản trị viên không có quyền mời.
- Email gửi thành công nhưng webhook cập nhật trạng thái bị chậm.

Nhóm làm rõ các trạng thái và kết quả mong đợi trước khi triển khai. Từ đó, API contract có thể định nghĩa trạng thái lời mời; test case có thể bao phủ các nhánh; runbook có thể hướng dẫn xử lý lời mời bị kẹt.

Ví dụ này cho thấy một review yêu cầu có thể ngăn thiếu sót lan sang thiết kế, mã, kiểm thử và vận hành. Rà soát sản phẩm công việc đầu vào tạo ra hiệu quả lớn khi được thực hiện trước khi nhiều nhóm dựa vào nó.

## 10. Đo lường hiệu quả rà soát

### Chọn chỉ số phản ánh kết quả

Có thể theo dõi:

- Số lượng và mức độ nghiêm trọng của vấn đề được phát hiện theo loại sản phẩm.
- Tỷ lệ vấn đề được phát hiện trước khi thực thi hoặc trước phát hành.
- Số lỗi được tìm thấy ở giai đoạn sau nhưng có thể phát hiện trong review sớm hơn.
- Thời gian từ khi phát hiện đến khi xử lý và xác minh.
- Tỷ lệ vấn đề tái diễn trong cùng loại sản phẩm công việc.
- Tỷ lệ cảnh báo tự động được xác nhận là vấn đề thật.
- Chi phí và thời gian review so với giá trị lỗi được ngăn chặn.

Không nên tối ưu chỉ số số lượng lỗi tìm thấy. Một review có ít phát hiện không nhất thiết kém hiệu quả; sản phẩm có thể đã được chuẩn bị tốt. Ngược lại, số lỗi cao có thể phản ánh review sâu hoặc quy trình tạo sản phẩm đang có vấn đề.

### Đánh giá cả hiệu quả và chi phí

Review quá nông có thể bỏ sót vấn đề; review quá nặng có thể tạo nút thắt. Hãy xem xét:

- Sản phẩm có được review đúng thời điểm không?
- Người tham gia có đúng chuyên môn không?
- Phát hiện có hữu ích và có thể hành động không?
- Vấn đề có được xử lý trước khi gây ảnh hưởng không?
- Có trùng lặp giữa review thủ công và công cụ tự động không?
- Có thể cải thiện checklist hoặc hướng dẫn để giảm lỗi lặp lại không?

Dữ liệu nên được phân tích theo loại sản phẩm, mức rủi ro và giai đoạn. Không dùng một chỉ số duy nhất để đánh giá năng suất cá nhân hoặc gây áp lực phải tạo ra nhiều phát hiện.

## 11. Những sai lầm thường gặp

- **Rà soát tất cả sản phẩm như nhau:** không phản ánh mức rủi ro, độ phức tạp và hậu quả.
- **Chỉ review mã nguồn:** bỏ qua yêu cầu, thiết kế, hợp đồng, test case và tài liệu vận hành.
- **Review quá muộn:** lỗi đã lan sang nhiều đầu ra và tốn kém để sửa.
- **Không xác định mục tiêu review:** người tham gia đọc nhưng không biết cần tìm loại vấn đề nào.
- **Chọn người tham gia không phù hợp:** thiếu góc nhìn nghiệp vụ, bảo mật, QA hoặc vận hành.
- **Chỉ dựa vào công cụ:** công cụ không hiểu đầy đủ ngữ nghĩa và bối cảnh người dùng.
- **Nhầm góp ý với lỗi:** review biến thành tranh luận sở thích và mất trọng tâm.
- **Không theo dõi phát hiện:** vấn đề được ghi nhận nhưng không có người xử lý hoặc xác minh.
- **Không review lại sau thay đổi lớn:** kết luận cũ không còn đúng với phiên bản hiện tại.
- **Dùng số lượng lỗi làm thước đo duy nhất:** có thể khuyến khích phát hiện nhỏ hoặc tạo báo cáo sai lệch.

## 12. Đầu ra cần có trước khi đưa sản phẩm công việc vào thực thi

Một kế hoạch lựa chọn và rà soát đủ dùng nên có:

1. **Danh mục sản phẩm công việc:** loại, phiên bản, tác giả, người sử dụng và giai đoạn.
2. **Mục tiêu rà soát:** loại vấn đề cần phát hiện và tiêu chí đánh giá.
3. **Đánh giá ưu tiên:** tác động, khả năng có lỗi, mức thay đổi, độ lan truyền và khả năng phát hiện muộn.
4. **Quyết định phạm vi:** sản phẩm được chọn, phần được lấy mẫu và lý do.
5. **Hình thức rà soát:** không chính thức, walkthrough, technical review, inspection hoặc phân tích tự động.
6. **Người tham gia:** chuyên môn, vai trò và trách nhiệm.
7. **Thời điểm và điều kiện:** phiên bản, tài liệu tham chiếu, thời gian chuẩn bị và điều kiện đầu vào.
8. **Kết quả review:** phát hiện, mức độ, người xử lý, thời hạn và trạng thái xác minh.
9. **Ngoại lệ và rủi ro còn lại:** phần chưa rà soát, lý do, người chấp nhận và hành động theo dõi.

Trước khi đưa sản phẩm công việc sang bước tiếp theo, hãy rà soát:

- Sản phẩm có ảnh hưởng đến mục tiêu hoặc hành trình quan trọng không?
- Hậu quả nếu sai đã được đánh giá chưa?
- Mức mới, phức tạp và thay đổi có được xem xét không?
- Có chọn đúng phương pháp và người rà soát không?
- Tiêu chí và tài liệu tham chiếu có rõ không?
- Các phát hiện quan trọng đã được xử lý hoặc chấp nhận đúng thẩm quyền chưa?
- Phiên bản sau review có được xác định và lưu dấu không?
- Các giới hạn của review có được ghi nhận để kiểm thử động tiếp tục xác minh không?

Lựa chọn đúng sản phẩm công việc giúp kiểm thử tĩnh phát hiện lỗi ở thời điểm có thể xử lý với chi phí thấp và ngăn lỗi lan sang các giai đoạn sau. Danh mục và mức độ rà soát cần được cập nhật khi mục tiêu, rủi ro, kiến trúc hoặc cách làm việc thay đổi. Nhờ đó, hoạt động review tạo ra bằng chứng có thể sử dụng trong chiến lược xác thực và hỗ trợ quyết định chuyển sang phát triển, thực thi kiểm thử hoặc phát hành.

