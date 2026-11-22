# Đánh giá kỹ năng nhóm, công cụ hiện có và nợ kiểm thử

Một chiến lược kiểm thử chỉ khả thi khi phù hợp với năng lực thực tế của nhóm, hệ thống công cụ đang vận hành và những khoản nợ kiểm thử đã tích lũy. Vì vậy, trước khi đặt mục tiêu tự động hóa, chọn thêm nền tảng hoặc yêu cầu tăng phạm vi kiểm thử, nhóm cần đánh giá ba yếu tố này một cách có hệ thống.

Đánh giá không nhằm xếp hạng cá nhân hay tìm người chịu trách nhiệm cho những thiếu sót trong quá khứ. Mục tiêu là hiểu nhóm hiện có thể làm tốt điều gì, đang bị giới hạn ở đâu, rủi ro nào chưa được kiểm soát và cần đầu tư vào đâu để cải thiện chất lượng với nguồn lực phù hợp.

Ba yếu tố có quan hệ chặt chẽ:

- **Kỹ năng nhóm** quyết định nhóm có thể thiết kế, xây dựng, thực thi và phân tích kiểm thử đến mức nào.
- **Công cụ hiện có** quyết định nhóm có phương tiện phù hợp để thực hiện công việc, nhận phản hồi và lưu giữ bằng chứng hay không.
- **Nợ kiểm thử** phản ánh những thiếu sót hoặc lựa chọn trì hoãn trước đây khiến việc kiểm chứng hiện tại tốn thời gian, kém tin cậy hoặc bỏ sót rủi ro.

Một công cụ tốt không tự tạo ra năng lực nếu nhóm chưa biết sử dụng và duy trì nó. Một nhóm có kỹ năng tốt cũng khó làm việc hiệu quả nếu môi trường thiếu ổn định hoặc bộ kiểm thử không đáng tin cậy. Khi đánh giá cả ba yếu tố, chiến lược kiểm thử có thể dựa trên thực trạng thay vì giả định.

## 1. Xác định mục đích và phạm vi đánh giá

Trước khi thu thập thông tin, hãy xác định những quyết định mà kết quả đánh giá cần hỗ trợ. Ví dụ:

- Nhóm có đủ năng lực kiểm thử các luồng nghiệp vụ và rủi ro quan trọng của sản phẩm không?
- Những kỹ năng nào đang tập trung ở một vài thành viên, tạo ra điểm phụ thuộc?
- Công cụ nào đang hỗ trợ tốt, công cụ nào ít được dùng hoặc gây trở ngại?
- Những khoản nợ kiểm thử nào làm chậm phản hồi, giảm độ tin cậy hoặc khiến lỗi lọt ra môi trường thực tế?
- Cần đào tạo, cải tiến quy trình, đầu tư công cụ hay thay đổi thiết kế hệ thống?
- Có thể cải thiện điều gì trong một chu kỳ ngắn và điều gì cần kế hoạch dài hạn?

Phạm vi đánh giá nên phù hợp với sản phẩm và nhóm chịu trách nhiệm. Với một nhóm nhỏ, có thể đánh giá toàn bộ năng lực và công cụ của nhóm. Với tổ chức lớn, nên phân chia theo sản phẩm, nhóm dịch vụ hoặc luồng nghiệp vụ để kết quả không quá chung chung.

Cần xác định rõ đối tượng và thời điểm đánh giá. Ví dụ, đánh giá năng lực của nhóm đang sở hữu một dịch vụ trong quý hiện tại khác với đánh giá năng lực kiểm thử của toàn bộ bộ phận. Không nên suy rộng kết luận từ một nhóm sang những nhóm chưa được khảo sát.

## 2. Đánh giá kỹ năng kiểm thử của nhóm

Kỹ năng kiểm thử không chỉ thuộc về người mang vai trò kiểm thử chuyên trách. Nhà phát triển cần biết kiểm tra mã và hành vi của thành phần mình xây dựng; người phụ trách kiểm thử cần phân tích rủi ro và thiết kế cách kiểm chứng; chủ sản phẩm cần làm rõ quy tắc nghiệp vụ và tiêu chí chấp nhận; nhóm vận hành cần hiểu cách quan sát và xác minh hệ thống sau triển khai.

Do đó, nên đánh giá năng lực chung của cả nhóm và chiều sâu chuyên môn cần thiết cho từng vai trò.

### Những nhóm năng lực cần xem xét

| Nhóm năng lực | Biểu hiện có thể quan sát |
|---|---|
| Hiểu sản phẩm và nghiệp vụ | Giải thích được hành trình người dùng, quy tắc nghiệp vụ, dữ liệu quan trọng và hậu quả của lỗi |
| Phân tích rủi ro | Nhận diện được điểm dễ lỗi, ước lượng tác động và ưu tiên kiểm thử theo rủi ro |
| Thiết kế kiểm thử | Chọn được tình huống bình thường, âm tính, giá trị biên, chuyển trạng thái và dữ liệu đại diện |
| Kiểm thử ở các cấp độ | Biết khi nào kiểm thử đơn vị, thành phần, hợp đồng, tích hợp, hệ thống hoặc chấp nhận là phù hợp |
| Tự động hóa và lập trình | Viết kiểm thử dễ đọc, có cấu trúc, có thể bảo trì và tích hợp vào quy trình phát triển |
| API, dữ liệu và tích hợp | Kiểm tra được giao tiếp giữa dịch vụ, tính nhất quán dữ liệu, xử lý lỗi và các phụ thuộc bên ngoài |
| Kiểm thử phi chức năng | Hiểu cách kiểm tra hiệu năng, bảo mật, độ tin cậy, khả năng phục hồi và khả năng tiếp cận khi cần |
| Phân tích lỗi | Tái hiện vấn đề, thu thập bằng chứng, khoanh vùng nguyên nhân và phân biệt lỗi sản phẩm với lỗi môi trường |
| CI/CD và vận hành | Hiểu luồng xây dựng, triển khai, cổng kiểm tra, log, metric, trace và kiểm tra sau triển khai |
| Cộng tác và truyền đạt | Viết báo cáo rõ ràng, thảo luận rủi ro, phản hồi sớm và phối hợp xử lý vấn đề |

Không phải nhóm nào cũng cần chuyên gia sâu ở mọi lĩnh vực. Một sản phẩm có yêu cầu bảo mật cao có thể cần chuyên môn bảo mật riêng; một hệ thống xử lý lượng giao dịch lớn có thể cần kỹ năng kiểm thử hiệu năng và dữ liệu. Hãy chọn những năng lực gắn với rủi ro thực tế của sản phẩm.

### Dùng ma trận kỹ năng để thấy năng lực của cả nhóm

Ma trận kỹ năng giúp thể hiện mức độ thành thạo và mức độ phân bố kiến thức. Có thể dùng thang bốn mức đơn giản:

| Mức | Mô tả |
|---|---|
| 1 – Nhận biết | Hiểu khái niệm, nhận ra khi nào cần kỹ năng và có thể làm theo hướng dẫn |
| 2 – Thực hiện có hỗ trợ | Hoàn thành nhiệm vụ quen thuộc với tài liệu, ví dụ hoặc sự hỗ trợ của thành viên khác |
| 3 – Làm việc độc lập | Tự lựa chọn cách tiếp cận, thực hiện nhiệm vụ và giải thích được quyết định |
| 4 – Hướng dẫn và cải tiến | Giải quyết tình huống phức tạp, hướng dẫn người khác và cải thiện cách làm của nhóm |

Mức đánh giá cần gắn với hành vi cụ thể. Chẳng hạn, ở kỹ năng thiết kế kiểm thử, mức 2 có thể là tạo được trường hợp kiểm thử theo yêu cầu và ví dụ có sẵn; mức 3 là tự phân tích quy tắc, xác định giá trị biên và giải thích phạm vi; mức 4 là hướng dẫn nhóm cải thiện chiến lược kiểm thử dựa trên rủi ro.

Ma trận minh họa:

| Năng lực | Thành viên A | Thành viên B | Thành viên C | Nhu cầu của nhóm |
|---|---:|---:|---:|---|
| Phân tích rủi ro | 3 | 2 | 2 | 3 |
| Kiểm thử đơn vị | 4 | 3 | 2 | 3 |
| Kiểm thử API và tích hợp | 2 | 3 | 1 | 3 |
| Kiểm thử hiệu năng | 1 | 2 | 1 | 2 |
| Phân tích log và điều tra lỗi | 3 | 2 | 2 | 3 |

Các mức trong bảng chỉ là ví dụ. Nhóm có thể thêm tên thành viên hoặc dùng vai trò thay cho tên nếu muốn tập trung vào năng lực tập thể. Cột “Nhu cầu của nhóm” biểu thị mức cần thiết dựa trên rủi ro và mục tiêu sản phẩm, không phải tiêu chuẩn chung cho mọi nhóm.

Khi đọc ma trận, hãy xem cả độ sâu và độ phủ. Nếu chỉ một người đạt mức 4 ở một kỹ năng quan trọng, nhóm có thể có chuyên môn tốt nhưng vẫn phụ thuộc vào một cá nhân. Nếu nhiều người đạt mức 2 nhưng không ai có thể hướng dẫn hoặc xử lý tình huống khó, nhóm có thể thiếu chiều sâu. Nếu kỹ năng có mức cao nhưng không liên quan đến rủi ro hiện tại, việc đầu tư thêm có thể chưa phải ưu tiên.

### Thu thập bằng chứng thay vì chỉ hỏi tự đánh giá

Tự đánh giá giúp thành viên chia sẻ cảm nhận và nhu cầu học tập, nhưng không đủ để kết luận về năng lực. Nên kết hợp nhiều nguồn:

- Xem xét các trường hợp kiểm thử, mã tự động hóa, báo cáo lỗi và tài liệu do nhóm tạo ra.
- Quan sát cách nhóm phân tích một thay đổi hoặc một sự cố thực tế.
- Thực hiện buổi trao đổi kỹ thuật, bài tập tình huống hoặc phiên kiểm thử cùng nhau.
- Xem xét chất lượng phản hồi khi kiểm thử thất bại: nhóm có tái hiện được lỗi và tìm ra nguyên nhân không?
- Trao đổi trong buổi hồi cứu về kỹ năng còn thiếu, điểm phụ thuộc và nhu cầu hỗ trợ.
- Đối chiếu với kết quả sản phẩm như lỗi lọt ra thực tế, thời gian phát hiện và khả năng phục hồi.

Ví dụ, để đánh giá kỹ năng kiểm thử API, có thể đưa ra một API tạo đơn hàng và yêu cầu nhóm xác định tình huống cần kiểm tra. Một câu trả lời tốt cần xem xét dữ liệu hợp lệ và không hợp lệ, xác thực và phân quyền, giá trị biên, yêu cầu gửi lặp, lỗi phụ thuộc và tính nhất quán của trạng thái sau khi xử lý. Qua cách lập luận và bằng chứng thực hiện, người đánh giá hiểu được khả năng áp dụng kỹ năng thực tế.

Nên ghi nhận cả điểm mạnh và điều kiện giúp thành viên làm tốt. Một người chưa từng thực hiện kiểm thử hiệu năng vì nhóm không có môi trường phù hợp không nhất thiết thiếu khả năng học kỹ năng đó. Phân biệt thiếu kiến thức, thiếu cơ hội thực hành và thiếu công cụ sẽ giúp chọn biện pháp cải thiện đúng nguyên nhân.

## 3. Đánh giá công cụ kiểm thử hiện có

Danh sách công cụ đã cài đặt không phản ánh đầy đủ năng lực của hệ thống kiểm thử. Cần hiểu công cụ được sử dụng như thế nào, có tích hợp vào quy trình không, kết quả có đáng tin cậy không và ai chịu trách nhiệm duy trì.

### Kiểm kê theo mục đích sử dụng

Có thể chia công cụ thành các nhóm sau:

| Nhóm công cụ | Mục đích |
|---|---|
| Quản lý yêu cầu và kiểm thử | Liên kết yêu cầu, rủi ro, trường hợp kiểm thử, lần chạy và lỗi |
| Kiểm thử đơn vị và thành phần | Kiểm tra logic và hành vi của các phần nhỏ trong hệ thống |
| Kiểm thử API và hợp đồng | Xác minh giao tiếp, cấu trúc thông điệp và thỏa thuận giữa các dịch vụ |
| Kiểm thử giao diện và đầu cuối | Kiểm tra hành trình người dùng qua giao diện hoặc toàn hệ thống |
| Kiểm thử hiệu năng | Đo thời gian phản hồi, thông lượng, mức sử dụng tài nguyên và khả năng chịu tải |
| Kiểm thử bảo mật | Phát hiện điểm yếu trong mã, cấu hình, phụ thuộc và hành vi ứng dụng |
| Kiểm thử khả năng tiếp cận | Đánh giá khả năng sử dụng với các nhu cầu và công nghệ hỗ trợ khác nhau |
| Quản lý dữ liệu kiểm thử | Tạo, làm sạch, ẩn danh, đặt lại và quản lý dữ liệu kiểm thử |
| Môi trường và giả lập phụ thuộc | Tạo môi trường có thể tái lập, giả lập dịch vụ và kiểm soát cấu hình |
| CI/CD và báo cáo | Tự động chạy kiểm thử, lưu kết quả, thông báo lỗi và kiểm soát điều kiện hợp nhất hoặc phát hành |
| Quan sát hệ thống | Thu thập log, metric, trace và cảnh báo để điều tra, xác minh sau triển khai |

Không cần có một sản phẩm riêng cho mỗi nhóm. Một nền tảng có thể đáp ứng nhiều nhu cầu, hoặc nhóm có thể dùng công cụ sẵn có trong ngôn ngữ, framework và hệ thống CI/CD.

### Lập hồ sơ cho từng công cụ

Với mỗi công cụ, hãy ghi nhận những thông tin giúp đánh giá giá trị thực tế:

- Tên và mục đích sử dụng.
- Nhóm hoặc người sở hữu, người có thể hỗ trợ khi gặp vấn đề.
- Nhóm nào đang sử dụng và tần suất sử dụng.
- Những bước trong quy trình phát triển mà công cụ tham gia.
- Loại kiểm thử hoặc rủi ro mà công cụ hỗ trợ.
- Khả năng tích hợp với mã nguồn, CI/CD, quản lý lỗi và báo cáo.
- Độ ổn định, thời gian chạy, chất lượng kết quả và mức độ dễ sử dụng.
- Chi phí giấy phép, hạ tầng, vận hành và bảo trì.
- Yêu cầu về bảo mật, quyền truy cập, dữ liệu và tuân thủ.
- Giới hạn đã biết, phụ thuộc kỹ thuật và kế hoạch hỗ trợ.

Ví dụ:

| Công cụ | Cách dùng hiện tại | Giá trị | Vấn đề cần kiểm tra |
|---|---|---|---|
| Framework kiểm thử đơn vị | Chạy trong quá trình phát triển và CI | Phản hồi nhanh về logic | Có kiểm tra đúng hành vi hay chỉ tăng số lượng test? |
| Công cụ kiểm thử API | Dùng cho một số luồng tích hợp | Kiểm tra hợp đồng và phản hồi dịch vụ | Có thể chạy tự động và quản lý dữ liệu ổn định không? |
| Công cụ kiểm thử giao diện | Chạy trước phát hành | Xác nhận hành trình người dùng | Thời gian chạy và tỷ lệ thất bại giả có cao không? |
| Nền tảng CI/CD | Xây dựng và chạy bộ kiểm thử | Chuẩn hóa quy trình và lưu bằng chứng | Hàng đợi, cấu hình hoặc bước kiểm thử nào đang làm chậm phản hồi? |
| Nền tảng quan sát | Thu thập log và metric sau triển khai | Hỗ trợ phát hiện và điều tra sự cố | Nhóm có biết truy vấn và liên kết dữ liệu để tìm nguyên nhân không? |

Bảng này cũng chỉ là ví dụ. Công cụ cần được đánh giá trong bối cảnh cách nhóm sử dụng, không dựa trên danh tiếng hoặc số lượng tính năng của nhà cung cấp.

### Đánh giá mức độ phù hợp và mức độ khai thác

Một công cụ có thể phù hợp về kỹ thuật nhưng không phù hợp với cách làm việc của nhóm. Hãy xem xét:

1. Công cụ có giải quyết vấn đề cụ thể đã được xác định không?
2. Nhóm có đủ kỹ năng để sử dụng, sửa lỗi và duy trì nó không?
3. Công cụ có tích hợp với quy trình hiện tại và tạo được phản hồi đúng thời điểm không?
4. Kết quả có đáng tin cậy, dễ hiểu và có thể truy vết không?
5. Chi phí sở hữu trong dài hạn có hợp lý không?
6. Công cụ có đáp ứng yêu cầu bảo mật, quyền riêng tư và quản lý dữ liệu không?
7. Có sự trùng lặp chức năng hoặc phụ thuộc vào một cá nhân hay nhà cung cấp không?

Cần phân biệt ba tình huống. Thứ nhất, công cụ hiện có phù hợp và được khai thác tốt; khi đó nên duy trì và cải tiến cách dùng. Thứ hai, công cụ phù hợp nhưng nhóm chưa khai thác hết; khi đó đào tạo, chuẩn hóa và tích hợp có thể đem lại giá trị lớn hơn việc mua công cụ mới. Thứ ba, công cụ không phù hợp với nhu cầu hoặc gây chi phí vận hành cao; khi đó cần cân nhắc thay thế hoặc đơn giản hóa.

Đừng chọn công cụ chỉ vì nó phổ biến hoặc có nhiều tính năng. Quyết định nên xuất phát từ rủi ro cần kiểm soát, quy trình cần hỗ trợ và chi phí duy trì trong suốt vòng đời.

## 4. Nhận diện và phân loại nợ kiểm thử

Nợ kiểm thử là những thiếu sót, thỏa hiệp hoặc phần việc kiểm chứng bị trì hoãn khiến nhóm phải trả thêm chi phí trong tương lai hoặc chấp nhận rủi ro chất lượng cao hơn. Nợ có thể phát sinh có chủ ý để đáp ứng thời hạn, hoặc tích lũy dần do thiếu thời gian, thiếu kỹ năng, công cụ không phù hợp hay thay đổi kiến trúc.

Nợ kiểm thử có thể tồn tại ngay cả khi sản phẩm đang hoạt động tốt. Ví dụ, một luồng quan trọng chưa có kiểm thử tự động có thể chưa gây sự cố, nhưng mỗi lần thay đổi nhóm phải kiểm tra thủ công và có nguy cơ bỏ sót hồi quy. Một bộ kiểm thử đầu cuối không ổn định có thể khiến nhóm bỏ qua cảnh báo, làm giảm giá trị của cả quy trình CI.

### Các dạng nợ kiểm thử thường gặp

| Loại nợ | Ví dụ | Hệ quả |
|---|---|---|
| Nợ về phạm vi và thiết kế kiểm thử | Thiếu tình huống biên, âm tính hoặc kiểm tra quy tắc quan trọng | Lỗi có thể không được phát hiện trước phát hành |
| Nợ tự động hóa | Luồng quan trọng chỉ được kiểm tra thủ công hoặc có kiểm thử tự động còn thiếu | Phản hồi chậm và dễ bỏ sót hồi quy |
| Nợ chất lượng kiểm thử | Assertion yếu, kiểm thử không xác định hoặc dữ liệu dùng chung | Kiểm thử có thể đạt dù hành vi sai hoặc thất bại không ổn định |
| Nợ bảo trì | Kiểm thử trùng lặp, mã khó đọc, fixture phức tạp hoặc kiểm thử lỗi thời | Thay đổi nhỏ cũng tốn nhiều công sức |
| Nợ môi trường và dữ liệu | Môi trường lệch cấu hình, dữ liệu khó tái tạo hoặc không thể đặt lại | Lỗi khó tái hiện và kết quả giữa các lần chạy không nhất quán |
| Nợ quy trình và pipeline | Bộ kiểm thử chạy quá lâu, báo cáo thiếu thông tin hoặc bước quan trọng bị bỏ qua | Nhóm nhận phản hồi muộn hoặc mất niềm tin vào CI |
| Nợ về khả năng kiểm thử của hệ thống | Thành phần phụ thuộc chặt, thiếu điểm quan sát hoặc không thể giả lập phụ thuộc | Kiểm thử tích hợp khó cô lập và khó điều tra |
| Nợ về quyền sở hữu và tri thức | Không rõ ai duy trì bộ kiểm thử, thiếu hướng dẫn và phụ thuộc vào một người | Công việc bị đình trệ khi người phụ trách vắng mặt |

### Phân biệt nợ kiểm thử với lỗi sản phẩm

Lỗi sản phẩm là hành vi sai so với yêu cầu hoặc kỳ vọng đã thống nhất. Nợ kiểm thử là điểm yếu trong cách nhóm kiểm chứng sản phẩm. Hai vấn đề có thể liên quan nhưng không đồng nhất.

Ví dụ, chức năng tính phí áp dụng sai mức thuế là lỗi sản phẩm. Việc không có kiểm thử cho các mức thuế ở ranh giới là nợ kiểm thử. Khi lỗi tính thuế xảy ra, nợ kiểm thử có thể là nguyên nhân khiến lỗi không được phát hiện sớm.

Một kiểm thử thất bại không tự động là nợ kiểm thử. Nó có thể phát hiện một lỗi sản phẩm thật. Ngược lại, kiểm thử luôn đạt cũng không chứng minh chất lượng tốt nếu kiểm thử không xác minh đúng hành vi hoặc không bao phủ rủi ro quan trọng.

### Nhận diện nợ từ tín hiệu thực tế

Có thể tìm nợ kiểm thử bằng cách xem xét:

- Lỗi nghiêm trọng lọt ra môi trường thực tế và tình huống lẽ ra có thể phát hiện trước đó.
- Những luồng quan trọng vẫn phụ thuộc vào kiểm tra thủ công lặp lại.
- Kiểm thử thường xuyên thất bại không ổn định hoặc bị tắt để pipeline tiếp tục chạy.
- Thời gian chạy kiểm thử tăng lên khiến nhóm phải trì hoãn hoặc bỏ qua phản hồi.
- Nhiều lỗi chỉ được phát hiện ở giai đoạn muộn vì thiếu kiểm thử thành phần hoặc hợp đồng.
- Môi trường và dữ liệu khó đặt lại, khiến việc tái hiện lỗi mất nhiều thời gian.
- Kiểm thử bị trùng lặp, không còn phù hợp với hành vi hiện tại hoặc không có người sở hữu.
- Nhóm không thể giải thích rõ kiểm thử nào đang bảo vệ rủi ro nào.
- Khi thay đổi một thành phần, nhóm không biết những thành phần hoặc hành trình nào có thể bị ảnh hưởng.

Một buổi hồi cứu sau sự cố là nguồn thông tin hữu ích. Hãy hỏi kiểm thử nào đã chạy, bằng chứng nào có sẵn, vì sao cảnh báo không được nhận diện và điều gì sẽ giúp phát hiện vấn đề sớm hơn. Câu trả lời nên dẫn đến cải tiến có thể thực hiện, thay vì chỉ thêm một trường hợp kiểm thử mà không hiểu nguyên nhân.

## 5. Ghi nhận và ưu tiên nợ kiểm thử

Không phải mọi khoản nợ đều cần xử lý ngay. Nhóm cần một danh sách có thể truy vết và cách ưu tiên dựa trên rủi ro, chi phí và ảnh hưởng đến công việc.

### Nội dung của một bản ghi nợ

Mỗi khoản nợ nên có:

- Mô tả cụ thể và bằng chứng quan sát được.
- Thành phần, luồng nghiệp vụ hoặc bộ kiểm thử bị ảnh hưởng.
- Rủi ro chất lượng và hậu quả nếu tiếp tục trì hoãn.
- Tần suất khoản nợ gây cản trở hoặc chi phí phát sinh.
- Nguyên nhân đã biết hoặc giả thuyết cần xác minh.
- Người hoặc nhóm sở hữu việc xử lý.
- Hướng giải quyết và phạm vi công việc ước tính.
- Mức ưu tiên, thời điểm xem xét lại và trạng thái.

Ví dụ về sổ theo dõi:

| Khoản nợ | Tác động | Mức ưu tiên minh họa | Hướng xử lý |
|---|---|---|---|
| Luồng hoàn tiền chưa có kiểm thử hồi quy | Có thể hoàn tiền sai hoặc không hoàn tiền sau thay đổi | Cao | Bổ sung kiểm thử quy tắc, tích hợp và tình huống lỗi |
| Bộ kiểm thử giao diện thường xuyên thất bại ngẫu nhiên | Nhóm mất niềm tin vào kết quả CI | Cao | Phân tích nguyên nhân, cô lập dữ liệu và sửa đồng bộ |
| Dữ liệu kiểm thử được tạo thủ công | Chuẩn bị môi trường lâu và khó tái tạo lỗi | Trung bình | Tạo fixture hoặc cơ chế khởi tạo dữ liệu có thể lặp lại |
| Một số kiểm thử cũ trùng lặp | Tăng thời gian chạy và bảo trì | Thấp đến trung bình | Xác định giá trị từng kiểm thử rồi hợp nhất hoặc loại bỏ có kiểm soát |

Mức ưu tiên trong ví dụ cần được xác nhận theo bối cảnh thực tế. Không nên gán mức cao chỉ vì một khoản nợ dễ nhìn thấy hoặc được nhiều người nhắc đến.

### Ưu tiên theo rủi ro và chi phí trì hoãn

Khi đánh giá một khoản nợ, hãy cân nhắc:

- **Mức độ ảnh hưởng:** nếu không xử lý, người dùng, dữ liệu, bảo mật, doanh thu hoặc vận hành có thể chịu tác động gì?
- **Khả năng xảy ra:** tình huống liên quan thường xuất hiện đến mức nào, thay đổi có thường xuyên không?
- **Mức độ phơi nhiễm:** có bao nhiêu luồng, nhóm hoặc bản phát hành bị ảnh hưởng?
- **Khả năng phát hiện:** nếu lỗi xảy ra, nhóm có nhận biết nhanh và xác định được nguyên nhân không?
- **Chi phí tích lũy:** mỗi lần phát triển hoặc phát hành phải trả thêm bao nhiêu thời gian, công sức và độ trễ?
- **Chi phí xử lý:** cần thay đổi mã, dữ liệu, môi trường, kỹ năng hoặc quy trình đến mức nào?

Có thể dùng thang định tính như cao, trung bình và thấp để bắt đầu. Nếu dùng điểm số, cần thống nhất ý nghĩa của từng mức và xem điểm số như công cụ hỗ trợ thảo luận. Một công thức không thể thay thế việc hiểu hậu quả thực tế.

Nợ có thể được xem xét qua hai phần: chi phí xử lý hiện tại và chi phí phát sinh mỗi lần tiếp tục trì hoãn. Một kiểm thử thủ công mất vài phút và chỉ chạy hiếm khi có thể chưa cần tự động hóa ngay. Một kiểm thử thủ công kéo dài hàng giờ, chạy mỗi lần phát hành và liên quan đến giao dịch quan trọng có thể tạo chi phí tích lũy lớn.

Cũng cần cân nhắc rủi ro khi sửa nợ. Xóa một bộ kiểm thử trùng lặp có thể giảm thời gian chạy, nhưng nếu chưa xác minh những hành vi mà nó bảo vệ thì có thể tạo ra khoảng trống mới. Mọi thay đổi với bộ kiểm thử quan trọng cần có bằng chứng rằng phạm vi bảo vệ vẫn được duy trì.

## 6. Kết hợp ba kết quả để xác định hành động

Đánh giá kỹ năng, công cụ và nợ kiểm thử cần được đọc cùng nhau. Một thiếu sót có thể có nhiều nguyên nhân và mỗi nguyên nhân cần cách xử lý khác nhau.

| Quan sát | Nguyên nhân có thể | Hướng cải thiện |
|---|---|---|
| Nhóm ít kiểm thử hợp đồng dù dịch vụ phụ thuộc nhiều vào nhau | Thiếu kỹ năng, chưa rõ quyền sở hữu hoặc chưa có công cụ phù hợp | Hướng dẫn thiết kế hợp đồng, chọn công cụ phù hợp và đưa kiểm thử vào CI |
| Có công cụ kiểm thử hiệu năng nhưng hầu như không sử dụng | Thiếu kỹ năng, môi trường tải không sẵn sàng hoặc chưa có mục tiêu đo | Đào tạo thực hành, chuẩn bị môi trường và xác định ngưỡng hiệu năng |
| Bộ kiểm thử đầu cuối chậm và không ổn định | Dữ liệu dùng chung, phụ thuộc môi trường hoặc kiểm thử quá nhiều trách nhiệm | Phân tích độ ổn định, cô lập dữ liệu và chuyển kiểm tra phù hợp xuống cấp độ thấp hơn |
| Chỉ một thành viên hiểu cách xử lý lỗi pipeline | Tri thức tập trung và thiếu tài liệu hoặc chia sẻ | Pairing, luân phiên trách nhiệm và ghi lại quy trình xử lý |
| Lỗi dữ liệu thường chỉ được phát hiện sau triển khai | Thiếu tình huống kiểm thử, dữ liệu đại diện hoặc quan sát hệ thống | Bổ sung kiểm thử toàn vẹn dữ liệu, dữ liệu thử nghiệm và kiểm tra sau triển khai |

Ví dụ, nếu nhóm chưa tự động hóa kiểm thử API, đừng vội kết luận cần mua nền tảng mới. Hãy xác minh nhóm có hiểu cách thiết kế kiểm thử API không, framework hiện tại có hỗ trợ không, dữ liệu và môi trường có thể tái tạo không, và quy trình CI có thể chạy bộ kiểm thử đó không. Kết quả sẽ cho biết cần đào tạo, chuẩn hóa dữ liệu, tích hợp công cụ hay đầu tư giải pháp mới.

## 7. Xây dựng kế hoạch cải thiện có thể thực hiện

Sau khi đánh giá, nhóm cần chuyển phát hiện thành hành động có người sở hữu và kết quả mong đợi. Một kế hoạch tốt không cố xử lý mọi khoảng trống cùng lúc. Nó ưu tiên những thay đổi giảm rủi ro lớn hoặc loại bỏ trở ngại đang làm chậm công việc.

### Chia hành động theo thời hạn và tác động

**Trong ngắn hạn**, ưu tiên những việc có thể giảm rủi ro hoặc khôi phục độ tin cậy nhanh:

- Sửa hoặc cách ly kiểm thử không ổn định sau khi đã xác định nguyên nhân.
- Bổ sung kiểm thử cho một quy tắc nghiệp vụ có tác động cao đang bị bỏ trống.
- Làm rõ người sở hữu các bộ kiểm thử và công cụ quan trọng.
- Chuẩn hóa cách tái tạo dữ liệu và báo cáo lỗi.
- Loại bỏ bước thủ công lặp lại có thể tự động hóa đơn giản.

**Trong trung hạn**, xây dựng năng lực và cải thiện quy trình:

- Tổ chức thực hành theo cặp về thiết kế kiểm thử, API, dữ liệu hoặc tự động hóa.
- Chuẩn hóa cấu trúc và quy ước của bộ kiểm thử.
- Tích hợp các kiểm tra có giá trị vào CI/CD.
- Cải thiện môi trường, dữ liệu và khả năng giả lập phụ thuộc.
- Tạo tài liệu vận hành, hướng dẫn điều tra lỗi và chia sẻ tri thức.

**Trong dài hạn**, xử lý những vấn đề có ảnh hưởng cấu trúc:

- Cải thiện kiến trúc để các thành phần dễ kiểm thử và cô lập hơn.
- Xây dựng năng lực chuyên sâu cho rủi ro đặc thù như hiệu năng hoặc bảo mật.
- Đơn giản hóa hệ sinh thái công cụ và giảm phụ thuộc không cần thiết.
- Tái thiết kế pipeline hoặc chiến lược môi trường nếu cấu trúc hiện tại không còn đáp ứng.
- Đưa việc đánh giá nợ kiểm thử vào chu kỳ lập kế hoạch và hồi cứu định kỳ.

### Gắn hành động với kết quả đo được

Mỗi hành động nên nêu rõ vấn đề cần giải quyết, người chịu trách nhiệm, kết quả mong đợi và cách xác minh. Ví dụ:

| Hành động | Kết quả mong đợi | Cách xác minh |
|---|---|---|
| Bổ sung kiểm thử tự động cho quy tắc hoàn tiền | Phát hiện hồi quy trước khi phát hành | Các tình huống thành công, thất bại và biên được chạy trong CI |
| Chia sẻ kỹ năng điều tra lỗi pipeline | Có nhiều thành viên xử lý được sự cố thường gặp | Thành viên khác tự điều tra một lần chạy thất bại và giải thích nguyên nhân |
| Cải thiện dữ liệu kiểm thử | Có thể tạo lại cùng một tình huống | Dữ liệu được khởi tạo và đặt lại nhất quán qua nhiều lần chạy |
| Rà soát công cụ kiểm thử giao diện | Giảm thời gian và thất bại giả | So sánh thời gian chạy và độ ổn định trước, sau cải tiến |

Đào tạo chỉ hiệu quả khi có cơ hội áp dụng. Sau buổi học, hãy giao một nhiệm vụ thực tế, tổ chức phiên làm việc cùng người có kinh nghiệm và xem lại kết quả. Tương tự, mua công cụ chỉ là đầu vào; cần đo xem công cụ có cải thiện tốc độ phản hồi, độ tin cậy hoặc khả năng phát hiện lỗi không.

### Dành thời gian xử lý nợ kiểm thử

Nếu mọi chu kỳ phát triển đều chỉ ưu tiên tính năng mới, nợ kiểm thử sẽ tiếp tục tăng. Nhóm nên dành một phần năng lực có kế hoạch cho việc sửa bộ kiểm thử, cải thiện dữ liệu, môi trường và công cụ. Tỷ lệ thời gian cụ thể phụ thuộc vào mức nợ, nhịp độ phát hành và rủi ro của sản phẩm.

Có thể xử lý nợ cùng lúc với thay đổi liên quan. Khi sửa một thành phần, hãy bổ sung hoặc cập nhật kiểm thử cho hành vi bị ảnh hưởng. Cách này giúp kiểm thử phát triển cùng sản phẩm và giảm việc tạo thêm nợ mới.

## 8. Theo dõi hiệu quả sau cải thiện

Đánh giá chỉ có giá trị khi nhóm quay lại xem hành động đã tạo ra thay đổi gì. Nên chọn một số chỉ số liên quan trực tiếp đến vấn đề đã xác định.

| Chỉ số | Điều cần hiểu |
|---|---|
| Thời gian phản hồi kiểm thử | Nhóm phải chờ bao lâu từ khi tạo thay đổi đến khi có bằng chứng |
| Tỷ lệ kiểm thử không ổn định | Mức độ tin cậy của kết quả và lượng công sức điều tra thất bại giả |
| Lỗi lọt ra sau phát hành | Những rủi ro nào chưa được kiểm soát trước khi người dùng gặp phải |
| Thời gian tái hiện và khoanh vùng lỗi | Khả năng sử dụng dữ liệu, log và công cụ để điều tra |
| Mức bao phủ rủi ro quan trọng | Những luồng hoặc hậu quả có ảnh hưởng lớn đã có bằng chứng kiểm thử đến đâu |
| Mức phân bố kỹ năng | Nhóm có thể tự thực hiện và hỗ trợ lẫn nhau ở các năng lực quan trọng không |
| Chi phí duy trì công cụ | Thời gian, hạ tầng và công sức cần để công cụ hoạt động ổn định |

Không nên dùng số lượng công cụ, số người được đào tạo hoặc phần trăm độ bao phủ mã làm thước đo duy nhất. Một buổi đào tạo hoàn thành chưa chứng minh kỹ năng đã được áp dụng; nhiều công cụ chưa chắc giải quyết được vấn đề; độ bao phủ cao chưa chắc kiểm tra đúng rủi ro.

Hãy đọc chỉ số cùng phản hồi của nhóm, sự cố thực tế và xu hướng qua nhiều chu kỳ. Nếu thời gian chạy giảm nhưng lỗi nghiêm trọng tăng, cần xem xét liệu nhóm đã loại bỏ nhầm kiểm thử có giá trị hay không. Nếu ma trận kỹ năng tăng nhưng mọi công việc phức tạp vẫn phải chờ một chuyên gia, cần đánh giá lại khả năng áp dụng độc lập và chia sẻ tri thức.

## 9. Những sai lầm thường gặp khi đánh giá

- **Đánh giá con người thay vì năng lực cần cho công việc:** dùng thâm niên hoặc chức danh để suy ra kỹ năng có thể dẫn đến kết luận sai.
- **Chỉ dựa vào tự đánh giá:** cảm nhận cá nhân hữu ích nhưng cần được đối chiếu với công việc và bằng chứng thực tế.
- **Biến ma trận kỹ năng thành bảng xếp hạng:** điều này làm giảm sự cởi mở và không giúp nhóm xác định cách hỗ trợ.
- **Đồng nhất số lượng công cụ với mức trưởng thành:** nhiều công cụ có thể tạo thêm chi phí, trùng lặp và gánh nặng bảo trì.
- **Mua công cụ trước khi hiểu vấn đề:** giải pháp mới không tự khắc phục thiếu kỹ năng, dữ liệu hoặc quy trình.
- **Chỉ ghi nhận nợ mà không có người sở hữu:** danh sách nợ dài nhưng không có kế hoạch sẽ nhanh chóng mất giá trị.
- **Cố xóa mọi khoản nợ:** một số khoản nợ có chi phí xử lý cao và rủi ro thấp; cần quản lý và xem xét lại thay vì xử lý máy móc.
- **Đặt mục tiêu không có thời gian thực hiện:** nếu kế hoạch không được đưa vào năng lực của nhóm, cải tiến sẽ luôn bị trì hoãn.
- **Không đánh giá lại:** công nghệ, kiến trúc, thành viên và rủi ro thay đổi; kết quả cũ có thể không còn phản ánh hiện trạng.

Để đánh giá có ích, hãy tạo môi trường trao đổi an toàn, tập trung vào bằng chứng, nguyên nhân và điều kiện làm việc. Kết quả cần giúp nhóm quyết định nên học gì, cải thiện gì và giảm rủi ro nào trước.

## 10. Mẫu tổng hợp kết quả đánh giá

Có thể dùng cấu trúc sau để ghi lại kết quả cho một nhóm hoặc một sản phẩm:

| Hạng mục | Nội dung cần ghi |
|---|---|
| Phạm vi | Sản phẩm, nhóm, thành phần và thời điểm đánh giá |
| Mục tiêu | Những quyết định mà đánh giá cần hỗ trợ |
| Kỹ năng hiện có | Năng lực mạnh, năng lực còn thiếu và mức độ phân bố trong nhóm |
| Công cụ hiện có | Công cụ đang dùng, chủ sở hữu, mức độ phù hợp và vấn đề vận hành |
| Nợ kiểm thử | Mô tả, bằng chứng, tác động, chi phí trì hoãn và người phụ trách |
| Rủi ro ưu tiên | Những khoảng trống có ảnh hưởng lớn nhất đến chất lượng |
| Hành động | Việc cần làm, người sở hữu, thời hạn và kết quả mong đợi |
| Cách xác minh | Chỉ số, bằng chứng và thời điểm đánh giá lại |

Sau khi tổng hợp, hãy trao đổi kết quả với những người trực tiếp thực hiện công việc để xác minh rằng nhận định phản ánh đúng thực tế. Nếu có bất đồng, ghi nhận bằng chứng còn thiếu và thống nhất cách kiểm tra thêm.

## Kết luận

Đánh giá kỹ năng nhóm, công cụ hiện có và nợ kiểm thử giúp chiến lược kiểm thử phản ánh đúng khả năng và giới hạn của tổ chức. Ma trận kỹ năng cho thấy nhóm có thể thực hiện và hỗ trợ lẫn nhau đến đâu; kiểm kê công cụ cho biết phương tiện hiện tại có phù hợp và đáng tin cậy không; sổ theo dõi nợ kiểm thử làm rõ những khoảng trống đang tạo rủi ro hoặc chi phí tích lũy.

Khi kết hợp ba góc nhìn này, nhóm có thể lựa chọn đúng biện pháp: phát triển kỹ năng, cải thiện cách sử dụng công cụ, đầu tư giải pháp mới hoặc xử lý nợ kiểm thử theo mức độ ưu tiên. Việc đánh giá nên được lặp lại khi sản phẩm, kiến trúc, đội ngũ hoặc rủi ro thay đổi, để chiến lược luôn gắn với thực tế và hỗ trợ quyết định cải tiến có cơ sở.
