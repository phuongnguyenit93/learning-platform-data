# Lộ trình xây dựng chiến lược từ bối cảnh đến quyết định phát hành

Một chiến lược kiểm thử tốt giúp nhóm trả lời được năm câu hỏi: sản phẩm cần đạt chất lượng nào, điều gì có thể làm chất lượng đó thất bại, cần kiểm tra những phần nào, bằng cách nào và dựa trên bằng chứng nào để quyết định phát hành. Chiến lược nối mục tiêu kinh doanh với hoạt động kiểm thử và quyết định kỹ thuật. Nó định hướng cách kiểm thử trong suốt vòng đời sản phẩm, thay vì chỉ liệt kê các trường hợp kiểm thử cho một đợt bàn giao.

Chiến lược không phải tài liệu cố định. Khi phạm vi sản phẩm, kiến trúc, mức độ rủi ro hoặc dữ liệu vận hành thay đổi, nhóm cần xem lại các giả định và điều chỉnh cách kiểm thử tương ứng.

## 1. Hiểu bối cảnh trước khi chọn cách kiểm thử

Điểm bắt đầu là hiểu sản phẩm được xây dựng cho ai và thành công có nghĩa là gì. Nếu chưa hiểu bối cảnh, nhóm dễ chọn những bài kiểm thử thuận tiện để thực hiện nhưng bỏ sót những lỗi gây ảnh hưởng lớn đến người dùng hoặc hoạt động kinh doanh.

Hãy thu thập thông tin từ các nguồn phù hợp:

- **Mục tiêu và quy trình nghiệp vụ:** sản phẩm giải quyết vấn đề gì, luồng nào tạo ra giá trị chính, kết quả nào được xem là thành công.
- **Người dùng và môi trường sử dụng:** nhóm người dùng, thiết bị, trình duyệt, mạng, ngôn ngữ, khả năng tiếp cận và các tình huống sử dụng thực tế.
- **Phạm vi thay đổi:** tính năng mới, phần được sửa, phần dùng chung có thể bị ảnh hưởng và các hệ thống phụ thuộc.
- **Kiến trúc và dữ liệu:** ranh giới dịch vụ, API, cơ sở dữ liệu, hàng đợi, bên thứ ba, cơ chế xác thực và luồng dữ liệu quan trọng.
- **Ràng buộc:** thời hạn, ngân sách, năng lực nhóm, môi trường kiểm thử, quy định bảo mật hoặc lưu trữ dữ liệu.
- **Lịch sử chất lượng:** lỗi đã xảy ra, sự cố production, khu vực thường xuyên phát sinh lỗi và những bài học từ lần phát hành trước.

Các câu hỏi sau giúp kiểm tra xem nhóm đã hiểu đủ bối cảnh chưa:

1. Người dùng sẽ gặp hậu quả gì nếu luồng chính bị lỗi?
2. Dữ liệu hoặc giao dịch nào không được phép mất, sai lệch hay xử lý lặp?
3. Hệ thống nào nằm ngoài quyền kiểm soát của nhóm nhưng có thể làm tính năng thất bại?
4. Có yêu cầu pháp lý, bảo mật, hiệu năng hoặc khả năng tiếp cận nào phải đáp ứng?
5. Điều gì đã thay đổi kể từ lần phát hành gần nhất?

Ghi rõ nguồn thông tin và giả định chưa được xác minh. Một giả định quan trọng chưa có bằng chứng cần trở thành rủi ro hoặc việc cần làm, thay vì được xem như sự thật.

## 2. Chuyển bối cảnh thành mục tiêu chất lượng

Mục tiêu chất lượng mô tả kết quả mà người dùng và hệ thống cần đạt. Chúng phải đủ cụ thể để nhóm có thể thiết kế phép kiểm tra và đánh giá kết quả.

Tùy sản phẩm, mục tiêu có thể bao gồm:

| Khía cạnh chất lượng | Câu hỏi cần trả lời | Ví dụ về bằng chứng |
|---|---|---|
| Tính đúng đắn chức năng | Hệ thống có thực hiện đúng quy tắc nghiệp vụ không? | Kết quả của các luồng chính, quy tắc tính toán và trường hợp biên |
| Tính toàn vẹn dữ liệu | Dữ liệu có được lưu và cập nhật chính xác không? | Đối chiếu dữ liệu trước và sau giao dịch, kiểm tra ràng buộc |
| Độ tin cậy | Hệ thống có xử lý lỗi và phục hồi đúng cách không? | Kiểm thử timeout, retry, mất kết nối và phục hồi |
| Hiệu năng và khả năng mở rộng | Hệ thống có đáp ứng tải dự kiến không? | Độ trễ, thông lượng và mức sử dụng tài nguyên dưới tải |
| Bảo mật và quyền riêng tư | Người dùng có chỉ truy cập được dữ liệu được phép không? | Kiểm tra phân quyền, xác thực, rò rỉ dữ liệu và xử lý bí mật |
| Khả năng sử dụng và tiếp cận | Người dùng mục tiêu có thể hoàn thành công việc không? | Đánh giá luồng thao tác, bàn phím, trình đọc màn hình |
| Tương thích | Sản phẩm có hoạt động trên môi trường được hỗ trợ không? | Kết quả trên các trình duyệt, thiết bị và phiên bản được hỗ trợ |

Một mục tiêu có thể kiểm chứng thường có bốn phần: đối tượng hoặc luồng được xét, điều kiện đo, ngưỡng chấp nhận và cách thu thập bằng chứng. Chẳng hạn, thay vì ghi “trang thanh toán phải nhanh”, hãy xác định luồng thanh toán, loại tải, môi trường đo, chỉ số độ trễ và ngưỡng đã được chủ sở hữu sản phẩm thống nhất.

Không cần áp dụng mọi thuộc tính chất lượng cho mọi sản phẩm. Hãy chọn những thuộc tính gắn với bối cảnh, sau đó xếp thứ tự ưu tiên theo tác động đối với người dùng, nghiệp vụ và vận hành.

## 3. Đánh giá rủi ro để xác định thứ tự ưu tiên

Rủi ro chất lượng là khả năng một vấn đề trong sản phẩm gây ra hậu quả không mong muốn. Chiến lược kiểm thử dựa trên rủi ro tập trung nỗ lực vào nơi thất bại có khả năng xảy ra hoặc gây thiệt hại lớn nhất.

Có thể bắt đầu bằng cách chấm từng rủi ro theo hai chiều:

- **Khả năng xảy ra:** mức độ dễ phát sinh lỗi, xét đến độ phức tạp, tần suất thay đổi, lịch sử lỗi và số lượng phụ thuộc.
- **Mức độ ảnh hưởng:** hậu quả đối với người dùng, dữ liệu, doanh thu, an toàn, tuân thủ và khả năng vận hành.

Điểm ưu tiên có thể được ước lượng bằng khả năng xảy ra nhân với mức độ ảnh hưởng. Đây là công cụ hỗ trợ thảo luận, không phải phép đo chính xác. Với rủi ro nghiêm trọng như lộ dữ liệu hoặc xử lý sai giao dịch tài chính, nhóm nên đặt mức ưu tiên cao ngay cả khi xác suất xảy ra thấp.

Ví dụ về danh mục rủi ro:

| Rủi ro | Khả năng xảy ra | Mức độ ảnh hưởng | Hướng kiểm thử |
|---|---|---|---|
| Một giao dịch bị ghi nhận hai lần khi người dùng gửi lại yêu cầu | Trung bình | Rất cao | Kiểm thử idempotency, retry, timeout và đối chiếu dữ liệu |
| Người dùng xem được dữ liệu của tài khoản khác | Thấp đến trung bình | Rất cao | Kiểm thử phân quyền ở API và giao diện, thử truy cập chéo tài khoản |
| Tồn kho không được cập nhật đồng nhất giữa các dịch vụ | Trung bình | Cao | Kiểm thử tích hợp, xử lý đồng thời và phục hồi thông điệp |
| Bố cục không phù hợp trên một kích thước màn hình ít phổ biến | Trung bình | Trung bình | Kiểm thử giao diện trên các nhóm thiết bị đại diện |

Mỗi rủi ro nên có mô tả, nguyên nhân hoặc điều kiện kích hoạt, hậu quả, mức ưu tiên, cách phát hiện, biện pháp giảm thiểu và người chịu trách nhiệm theo dõi. Danh mục này cần được cập nhật khi có thay đổi kiến trúc, yêu cầu hoặc dữ liệu lỗi mới.

## 4. Xác định phạm vi và giới hạn kiểm thử

Sau khi hiểu mục tiêu và rủi ro, hãy xác định rõ phạm vi. Phạm vi tốt giúp nhóm phân bổ thời gian hợp lý và giúp người ra quyết định hiểu phần nào đã được kiểm tra.

Phân chia phạm vi thành ba nhóm:

- **Trong phạm vi:** chức năng, dịch vụ, luồng dữ liệu, môi trường và thuộc tính chất lượng sẽ được kiểm thử.
- **Ngoài phạm vi:** nội dung không được kiểm thử trong đợt này, kèm lý do và tác động của việc loại trừ.
- **Phụ thuộc hoặc chưa chắc chắn:** dịch vụ bên thứ ba, dữ liệu, môi trường hoặc quyết định đang chờ xác nhận.

Không nên ghi “không kiểm thử” mà không giải thích hệ quả. Ví dụ, nếu không thể kiểm thử trực tiếp một nhà cung cấp thanh toán trong môi trường thử nghiệm, nhóm có thể kiểm thử hợp đồng API bằng dữ liệu mô phỏng và ghi rõ phần hành vi của nhà cung cấp vẫn cần được xác nhận bằng bằng chứng khác.

Phạm vi cũng cần phản ánh tác động lan truyền. Một thay đổi nhỏ ở thư viện xác thực dùng chung có thể ảnh hưởng nhiều luồng hơn một tính năng giao diện lớn nhưng độc lập.

## 5. Chọn các lớp kiểm thử và kỹ thuật phù hợp

Không có một lớp kiểm thử đơn lẻ nào chứng minh được toàn bộ chất lượng. Hãy phối hợp nhiều lớp sao cho lỗi được phát hiện sớm, phản hồi đủ nhanh và các rủi ro quan trọng được kiểm tra trong điều kiện gần thực tế.

| Lớp hoặc hoạt động | Mục tiêu chính | Khi nào hữu ích |
|---|---|---|
| Rà soát tĩnh | Phát hiện vấn đề trong yêu cầu, thiết kế, mã nguồn và cấu hình trước khi chạy hệ thống | Khi làm rõ yêu cầu, rà soát thay đổi hoặc kiểm tra bảo mật |
| Kiểm thử đơn vị | Xác minh logic nhỏ trong phạm vi hẹp | Với quy tắc nghiệp vụ, phép tính và nhánh điều kiện |
| Kiểm thử thành phần | Kiểm tra một thành phần cùng các phụ thuộc được kiểm soát | Khi cần xác minh hành vi của module hoặc dịch vụ riêng |
| Kiểm thử tích hợp | Xác minh các thành phần trao đổi dữ liệu và phối hợp đúng | Với API, cơ sở dữ liệu, hàng đợi và hệ thống phụ thuộc |
| Kiểm thử hợp đồng | Xác minh các bên tuân thủ giao diện và cấu trúc trao đổi đã thống nhất | Khi nhiều nhóm phát triển dịch vụ độc lập |
| Kiểm thử đầu cuối | Kiểm tra một hành trình thực tế qua nhiều thành phần | Với các luồng người dùng hoặc nghiệp vụ quan trọng |
| Kiểm thử chấp nhận | Xác nhận sản phẩm đáp ứng nhu cầu và tiêu chí nghiệp vụ | Trước khi bàn giao hoặc phát hành |
| Kiểm thử phi chức năng | Đánh giá hiệu năng, bảo mật, độ tin cậy, khả năng tiếp cận và các thuộc tính khác | Khi các thuộc tính đó tạo thành rủi ro đáng kể |

Các lớp kiểm thử nên bổ sung cho nhau. Kiểm thử đơn vị thường nhanh và dễ khoanh vùng lỗi; kiểm thử tích hợp phát hiện vấn đề ở ranh giới; kiểm thử đầu cuối xác minh hành trình thực tế nhưng thường chậm và nhạy cảm với thay đổi môi trường. Vì vậy, hãy đặt phần lớn kiểm tra logic ổn định ở lớp phù hợp, đồng thời giữ đủ kiểm thử tích hợp và đầu cuối cho các rủi ro xuyên suốt.

Chọn kỹ thuật thiết kế kiểm thử theo đặc điểm của quy tắc:

- **Phân vùng tương đương:** chia đầu vào thành các nhóm được xử lý tương tự, sau đó chọn đại diện từ mỗi nhóm.
- **Phân tích giá trị biên:** tập trung vào giới hạn tối thiểu, tối đa và giá trị ngay sát giới hạn.
- **Bảng quyết định:** kiểm tra tổ hợp điều kiện và kết quả, hữu ích với quy tắc nghiệp vụ có nhiều nhánh.
- **Chuyển trạng thái:** xác minh trạng thái hợp lệ, chuyển đổi được phép và chuyển đổi phải bị từ chối.
- **Kiểm thử tổ hợp:** dùng kỹ thuật như pairwise khi nhiều tham số tạo ra số tổ hợp lớn.
- **Kiểm thử thăm dò:** người kiểm thử chủ động tìm hiểu hệ thống, đặt giả thuyết và điều chỉnh phép thử theo kết quả quan sát.
- **Kiểm thử dựa trên thuộc tính:** xác minh một quy luật tổng quát trên nhiều dữ liệu được sinh tự động, khi bài toán phù hợp.

Ví dụ, với chức năng đặt hàng, bảng quyết định có thể kết hợp trạng thái tồn kho, trạng thái thanh toán và quyền mua để xác định đơn hàng có được tạo hay không. Kiểm thử chuyển trạng thái có thể xác minh một đơn hàng đã hủy không được chuyển ngược sang trạng thái đang giao.

## 6. Chuẩn bị môi trường và dữ liệu kiểm thử

Kết quả kiểm thử chỉ đáng tin khi môi trường và dữ liệu đủ phù hợp với mục tiêu kiểm tra.

Môi trường cần có cấu hình, phiên bản dịch vụ, quyền truy cập và các phụ thuộc được kiểm soát. Hãy ghi nhận những khác biệt so với production vì chúng có thể làm thay đổi hành vi, chẳng hạn như cấu hình cache, giới hạn tài nguyên hoặc cách xử lý callback từ bên ngoài.

Dữ liệu kiểm thử nên:

- Đại diện cho dữ liệu hợp lệ, dữ liệu biên, dữ liệu không hợp lệ và tình huống hiếm nhưng có hậu quả lớn.
- Có thể tạo lại hoặc khôi phục để các lần chạy có kết quả so sánh được.
- Được cô lập giữa các lần chạy để tránh phụ thuộc vào thứ tự thực thi.
- Không chứa dữ liệu cá nhân hoặc bí mật thật nếu không có cơ chế bảo vệ và quyền sử dụng phù hợp.
- Bao gồm dữ liệu lớn, dữ liệu thiếu, dữ liệu trùng và dữ liệu không nhất quán khi các trường hợp đó liên quan đến rủi ro.

Với phụ thuộc bên ngoài, cân nhắc dùng sandbox, stub, mock hoặc service virtualization. Cách mô phỏng phải phản ánh đúng hợp đồng và các tình huống lỗi quan trọng. Mô phỏng không thể thay thế hoàn toàn việc xác minh với hệ thống thật; chiến lược cần ghi rõ giới hạn đó và xác định nơi thu thập bằng chứng bổ sung.

## 7. Xây dựng cách tự động hóa và phản hồi

Tự động hóa có giá trị khi giúp nhóm nhận phản hồi nhanh, lặp lại được và đủ tin cậy. Không phải phép kiểm thử nào cũng nên tự động hóa. Hãy ưu tiên những kiểm tra có tần suất chạy cao, kết quả xác định được, rủi ro đáng kể và chi phí bảo trì hợp lý.

Một luồng phản hồi thường gồm:

1. Kiểm tra định dạng, phân tích tĩnh và rà soát cấu hình.
2. Chạy kiểm thử đơn vị và kiểm thử thành phần.
3. Chạy kiểm thử hợp đồng và tích hợp.
4. Chạy nhóm kiểm thử đầu cuối trọng yếu.
5. Chạy các kiểm tra phi chức năng theo lịch, theo thay đổi hoặc trước mốc phát hành phù hợp.
6. Lưu kết quả, log, báo cáo và thông tin phiên bản để có thể truy vết.

Mỗi kiểm tra tự động cần có người hoặc nhóm chịu trách nhiệm khi thất bại. Kiểm thử không ổn định (flaky test) làm giảm niềm tin vào pipeline: hãy theo dõi tỷ lệ không ổn định, điều tra nguyên nhân và sửa hoặc cách ly có thời hạn kèm người phụ trách. Không nên bỏ qua lỗi chỉ vì một bài kiểm thử từng thất bại ngẫu nhiên.

Với kiểm thử thủ công, hãy ghi lại mục tiêu khám phá, phạm vi, dữ liệu sử dụng, môi trường, phát hiện và phần chưa thể xác minh. Kết quả thủ công cũng cần tạo ra bằng chứng có thể xem xét lại.

## 8. Thiết lập điều kiện bắt đầu, kết thúc và tiêu chí phát hành

Điều kiện bắt đầu (entry criteria) xác định khi nào một hoạt động kiểm thử đã sẵn sàng. Ví dụ: yêu cầu đủ rõ, bản dựng có thể triển khai, môi trường hoạt động, dữ liệu đã chuẩn bị và các phụ thuộc thiết yếu sẵn sàng.

Điều kiện kết thúc (exit criteria) xác định khi nào có đủ bằng chứng để kết thúc một giai đoạn kiểm thử. Ví dụ:

- Các luồng nghiệp vụ quan trọng đã được kiểm tra theo phạm vi thống nhất.
- Những kiểm tra bắt buộc đã chạy trên đúng phiên bản ứng viên phát hành.
- Không còn lỗi nghiêm trọng chưa có phương án xử lý được phê duyệt.
- Các ngưỡng chất lượng đã thống nhất được đáp ứng hoặc có sai lệch được ghi nhận.
- Rủi ro còn lại, phần chưa kiểm thử và giới hạn môi trường đã được công khai.
- Bằng chứng kiểm thử có thể truy vết đến bản dựng và cấu hình tương ứng.

Exit criteria và quyết định phát hành có liên quan nhưng không đồng nhất. Nhóm kiểm thử cung cấp bằng chứng và đánh giá rủi ro; người có thẩm quyền phát hành cân nhắc thêm mức độ chấp nhận rủi ro, nhu cầu kinh doanh, kế hoạch triển khai và khả năng phục hồi.

Có thể chuẩn hóa quyết định thành ba hướng:

| Quyết định | Điều kiện thường gặp | Hành động |
|---|---|---|
| Phát hành | Các tiêu chí bắt buộc đạt, rủi ro còn lại nằm trong mức chấp nhận | Tiến hành theo kế hoạch phát hành |
| Phát hành có điều kiện | Còn sai lệch đã được đánh giá, có biện pháp giảm thiểu, người chịu trách nhiệm và thời hạn xử lý | Ghi nhận chấp thuận rủi ro, giới hạn phạm vi hoặc triển khai theo từng giai đoạn |
| Chưa phát hành | Có lỗi hoặc thiếu bằng chứng khiến rủi ro vượt mức chấp nhận | Hoãn phát hành, xử lý vấn đề và kiểm thử lại |

Mọi ngoại lệ phải nêu rõ rủi ro, tác động, lý do chấp nhận, biện pháp giám sát, người phê duyệt và thời điểm xem xét lại. Không nên dùng một tỷ lệ kiểm thử thành công tổng thể để che khuất một lỗi nghiêm trọng ở luồng trọng yếu.

## 9. Thu thập bằng chứng và chọn chỉ số có ý nghĩa

Bằng chứng kiểm thử giúp người khác hiểu nhóm đã kiểm tra điều gì, trong điều kiện nào và kết quả có ý nghĩa ra sao. Một báo cáo hữu ích thường gắn với phiên bản ứng viên phát hành, môi trường, dữ liệu, thời điểm chạy, kết quả, lỗi đã biết và các giới hạn.

Có thể theo dõi các nhóm chỉ số sau:

- **Mức độ bao phủ rủi ro:** những rủi ro ưu tiên cao nào đã có phép kiểm tra và bằng chứng.
- **Tình trạng lỗi:** số lượng lỗi theo mức độ nghiêm trọng, thời gian xử lý và lỗi tái xuất hiện.
- **Chất lượng sau phát hành:** lỗi lọt ra production, sự cố theo phiên bản và thời gian phát hiện.
- **Hiệu quả phản hồi:** thời gian pipeline, thời gian nhận biết lỗi và thời gian khôi phục.
- **Độ tin cậy của kiểm thử:** tỷ lệ bài kiểm thử không ổn định, thời gian bảo trì và số lần chạy lại.

Mỗi chỉ số cần có định nghĩa, nguồn dữ liệu, chu kỳ xem xét và người chịu trách nhiệm. Chỉ số chỉ hữu ích khi dẫn đến hành động. Ví dụ, tỷ lệ pass cao nhưng chưa kiểm tra rủi ro lộ dữ liệu không phải bằng chứng đủ để phát hành. Tương tự, số lượng test case lớn không tự chứng minh rằng các luồng quan trọng đã được bao phủ.

Nên kết hợp chỉ số định lượng với đánh giá định tính về các giả định, vùng chưa kiểm thử và mức độ tin cậy của bằng chứng.

## 10. Chuẩn bị phát hành và học từ vận hành

Kiểm thử trước phát hành giảm rủi ro nhưng không thể chứng minh rằng mọi tình huống production đều đã được mô phỏng. Chiến lược cần nối hoạt động kiểm thử với giám sát và phản hồi sau triển khai.

Trước khi phát hành, xác định:

- Chỉ số và log cần theo dõi cho các luồng quan trọng.
- Ngưỡng cảnh báo và người nhận cảnh báo.
- Cách triển khai từng phần, canary hoặc dùng feature flag nếu phù hợp.
- Điều kiện dừng triển khai, rollback hoặc tắt tính năng.
- Quy trình xác minh nhanh sau triển khai.
- Người chịu trách nhiệm điều phối khi có sự cố.

Sau phát hành, so sánh hành vi thực tế với mục tiêu chất lượng. Phân tích lỗi lọt, sự cố, phản hồi người dùng và các cảnh báo để cập nhật danh mục rủi ro. Khi một lỗi xuất hiện, hãy xem xét bổ sung kiểm thử ở lớp có thể phát hiện lỗi sớm nhất mà vẫn tái hiện được nguyên nhân; đồng thời kiểm tra xem tiêu chí phát hành hoặc khả năng quan sát có cần điều chỉnh không.

## 11. Ví dụ: xây dựng chiến lược cho luồng thanh toán

Giả sử một sản phẩm thương mại điện tử bổ sung luồng thanh toán mới. Mục tiêu là người dùng có thể thanh toán đơn hàng, nhận kết quả rõ ràng và không bị tính tiền hai lần khi mạng chập chờn.

Từ bối cảnh đó, nhóm có thể xây dựng chuỗi quyết định như sau:

| Bối cảnh hoặc rủi ro | Mục tiêu chất lượng | Cách kiểm thử và bằng chứng |
|---|---|---|
| Người dùng gửi lại yêu cầu khi không nhận được phản hồi | Một đơn hàng không tạo ra nhiều giao dịch thu tiền | Kiểm thử timeout, retry và idempotency; đối chiếu mã giao dịch và dữ liệu đơn hàng |
| Nhà cung cấp thanh toán phản hồi chậm hoặc không sẵn sàng | Hệ thống thể hiện trạng thái nhất quán và có thể phục hồi | Kiểm thử lỗi mạng, callback đến trễ, callback lặp và cơ chế đối soát |
| Người dùng thay đổi giỏ hàng trong lúc thanh toán | Số tiền được thu khớp với đơn hàng được xác nhận | Kiểm thử đồng thời, giá thay đổi và dữ liệu giỏ hàng cũ |
| API thanh toán bị gọi từ tài khoản không có quyền | Chỉ chủ thể hợp lệ mới có thể thực hiện giao dịch | Kiểm thử xác thực, phân quyền và truy cập chéo tài khoản |
| Lượng truy cập tăng vào giờ cao điểm | Luồng thanh toán đáp ứng ngưỡng hiệu năng đã thống nhất | Kiểm thử tải với kịch bản gần thực tế; lưu độ trễ, thông lượng và lỗi |

Từ bảng này, nhóm chọn các lớp kiểm thử: kiểm thử đơn vị cho quy tắc tính tiền, kiểm thử thành phần cho trạng thái đơn hàng, kiểm thử hợp đồng với nhà cung cấp thanh toán, kiểm thử tích hợp cho callback và lưu trữ, kiểm thử đầu cuối cho hành trình mua hàng. Kiểm thử bảo mật và tải được thực hiện theo mức rủi ro và tiêu chí đã thống nhất.

Trước khi phát hành, nhóm kiểm tra rằng các giao dịch thử nghiệm không tạo khoản thu trùng, trạng thái đơn hàng và giao dịch khớp nhau, lỗi nhà cung cấp được xử lý theo thiết kế, các kiểm tra phân quyền đạt và ngưỡng hiệu năng được đáp ứng. Nếu còn một vấn đề chưa thể kiểm chứng, vấn đề đó phải được ghi thành rủi ro với biện pháp giảm thiểu và người có thẩm quyền quyết định có chấp nhận hay không.

Ví dụ này cho thấy chiến lược bắt đầu từ hậu quả có thể xảy ra với người dùng, rồi mới lựa chọn lớp kiểm thử và bằng chứng. Danh sách test case là kết quả của quá trình đó, không phải điểm xuất phát duy nhất.

## 12. Duy trì chiến lược như một quyết định có thể xem lại

Một tài liệu chiến lược đủ dùng nên giúp người khác hiểu và thực hiện được các quyết định của nhóm. Có thể tổ chức tài liệu theo cấu trúc sau:

1. **Bối cảnh:** mục tiêu sản phẩm, người dùng, kiến trúc, thay đổi và ràng buộc.
2. **Mục tiêu chất lượng:** thuộc tính cần bảo đảm, ngưỡng và cách đo.
3. **Danh mục rủi ro:** tác động, khả năng xảy ra, ưu tiên và chủ sở hữu.
4. **Phạm vi:** phần được kiểm thử, phần loại trừ và các phụ thuộc.
5. **Cách tiếp cận:** lớp kiểm thử, kỹ thuật, mức tự động hóa và hoạt động thủ công.
6. **Môi trường và dữ liệu:** cấu hình, nguồn dữ liệu, cách cô lập và giới hạn mô phỏng.
7. **Điều kiện kiểm thử:** entry criteria, exit criteria và tiêu chí phát hành.
8. **Bằng chứng và báo cáo:** chỉ số, nơi lưu kết quả và khả năng truy vết.
9. **Vận hành sau phát hành:** giám sát, rollout, rollback và vòng phản hồi.
10. **Giả định và quyết định còn mở:** nội dung cần xác minh, người phụ trách và thời hạn xem xét.

Sơ đồ dưới đây thể hiện mạch xây dựng chiến lược và vòng phản hồi sau phát hành:

~~~mermaid
flowchart TD
    A["Bối cảnh sản phẩm và thay đổi"] --> B["Mục tiêu chất lượng"]
    B --> C["Đánh giá và xếp hạng rủi ro"]
    C --> D["Xác định phạm vi và phụ thuộc"]
    D --> E["Chọn lớp, kỹ thuật và môi trường kiểm thử"]
    E --> F["Thực thi và thu thập bằng chứng"]
    F --> G["Đánh giá tiêu chí kết thúc"]
    G --> H{"Đủ điều kiện phát hành?"}
    H -->|Có| I["Phê duyệt và triển khai"]
    H -->|Chưa| J["Giảm thiểu rủi ro, sửa lỗi, kiểm thử lại"]
    J --> F
    I --> K["Giám sát và thu thập phản hồi"]
    K --> L["Cập nhật mục tiêu và danh mục rủi ro"]
    L --> A
~~~

Hãy xem lại chiến lược khi có thay đổi đáng kể về yêu cầu, kiến trúc, phụ thuộc, dữ liệu, mức tải, sự cố hoặc mức độ chấp nhận rủi ro. Mỗi lần cập nhật nên nêu điều gì đã thay đổi, quyết định nào bị ảnh hưởng và bằng chứng nào hỗ trợ quyết định mới.

Một chiến lược kiểm thử có giá trị khi nó giúp nhóm tập trung vào rủi ro quan trọng, tạo ra bằng chứng đáng tin và đưa ra quyết định phát hành minh bạch. Chất lượng của chiến lược được thể hiện qua khả năng giải thích vì sao nhóm kiểm thử những gì đã chọn, điều gì vẫn chưa chắc chắn và ai chịu trách nhiệm với rủi ro còn lại.

