# Kết hợp kiến thức người dùng, rủi ro và kinh nghiệm lỗi

Kiểm thử thủ công và kiểm thử khám phá có giá trị đặc biệt khi nhóm cần hiểu cách sản phẩm được sử dụng trong thực tế, nhận diện những tình huống chưa được mô tả đầy đủ và tìm ra lỗi khó dự đoán trước. Để hoạt động này có trọng tâm, người kiểm thử cần kết hợp ba nguồn hiểu biết: **kiến thức về người dùng và công việc của họ**, **nhận định về rủi ro sản phẩm**, và **kinh nghiệm từ các lỗi đã từng xảy ra**.

Mỗi nguồn trả lời một câu hỏi khác nhau. Kiến thức người dùng cho biết điều gì quan trọng trong bối cảnh sử dụng; phân tích rủi ro cho biết thất bại nào có thể gây hậu quả lớn; lịch sử lỗi cho biết những cách sản phẩm từng thất bại và điều kiện dễ kích hoạt chúng. Khi kết hợp, nhóm có thể chọn hành trình cần khám phá, đặt giả thuyết kiểm thử và điều chỉnh hướng kiểm tra dựa trên bằng chứng quan sát được.

## 1. Ba nguồn hiểu biết bổ sung cho nhau

### Kiến thức về người dùng và công việc thực tế

Kiến thức người dùng mô tả ai sử dụng sản phẩm, họ muốn hoàn thành công việc gì, trong hoàn cảnh nào và điều gì khiến họ thành công hoặc thất bại. Nguồn này có thể đến từ:

- Phỏng vấn, quan sát người dùng và thử nghiệm khả năng sử dụng.
- Nhân viên hỗ trợ, vận hành, bán hàng hoặc chuyên gia nghiệp vụ thường xuyên tiếp xúc với người dùng.
- Phản hồi, khiếu nại, yêu cầu hỗ trợ, đánh giá và báo cáo lỗi từ người dùng.
- Dữ liệu sử dụng như tỷ lệ bỏ dở, bước thường bị lặp, thời gian hoàn thành tác vụ hoặc luồng ít được sử dụng.
- Bối cảnh thực tế: thiết bị, trình duyệt, kết nối mạng, ngôn ngữ, múi giờ, khả năng tiếp cận và quy trình làm việc.

Những thông tin này giúp người kiểm thử hiểu khoảng cách giữa quy trình được mô tả trong tài liệu và cách người dùng thực sự làm việc. Người dùng có thể nhập dữ liệu theo cách không được dự đoán, quay lại bước trước, chuyển thiết bị giữa chừng hoặc dùng một tính năng theo cách khác với ý định ban đầu của nhóm thiết kế.

Ví dụ, tài liệu nói người dùng đặt lịch bằng cách chọn ngày rồi chọn giờ. Quan sát nhân viên lễ tân có thể cho thấy họ thường mở nhiều hồ sơ cùng lúc, giữ chỗ trong khi gọi điện xác nhận và quay lại màn hình sau vài phút. Những hành vi này tạo ra điều kiện kiểm thử về trạng thái cũ, thời gian hết hạn và xung đột đặt lịch.

### Hiểu biết về rủi ro sản phẩm

Rủi ro sản phẩm là khả năng một vấn đề trong sản phẩm gây hậu quả không mong muốn. Khi chọn kiểm thử, cần xem xét ít nhất:

- **Khả năng xảy ra:** điều kiện gây lỗi có phổ biến hoặc dễ xuất hiện không?
- **Mức độ tác động:** người dùng, dữ liệu, tiền, hoạt động hoặc uy tín bị ảnh hưởng đến đâu?
- **Phạm vi phơi lộ:** bao nhiêu người dùng, giao dịch hoặc thành phần có thể bị ảnh hưởng?
- **Khả năng phát hiện và khôi phục:** vấn đề có dễ nhận ra, cô lập và sửa chữa không?
- **Mức độ bất định:** nhóm còn thiếu thông tin nào về hành vi hoặc điều kiện sử dụng?

Không cần biến mọi nhận định thành điểm số chính xác. Có thể dùng mức thấp, trung bình, cao hoặc ma trận đã thống nhất. Điều quan trọng là giải thích lý do ưu tiên và nhận diện các hậu quả nghiêm trọng dù xác suất xảy ra thấp.

Kiến thức người dùng làm rõ tác động trong bối cảnh thật. Ví dụ, một lỗi đặt nhầm lịch có thể gây bất tiện nhỏ với cuộc hẹn nội bộ nhưng gây hậu quả lớn nếu đó là lịch khám hoặc lịch dịch vụ khan hiếm. Cùng một lỗi kỹ thuật có thể có mức rủi ro khác nhau tùy mục đích sử dụng.

### Kinh nghiệm từ lỗi đã xảy ra

Lịch sử lỗi cho biết sản phẩm, nhóm phát triển hoặc hệ thống tương tự từng thất bại như thế nào. Nguồn này có thể gồm:

- Báo cáo lỗi đã sửa và lỗi lọt tới production.
- Sự cố vận hành, postmortem và near miss (tình huống suýt gây sự cố).
- Lỗi hồi quy sau thay đổi mã, cấu hình, dữ liệu hoặc phụ thuộc.
- Những khu vực có nhiều thay đổi, độ phức tạp cao hoặc nhiều người cùng chỉnh sửa.
- Các mẫu nguyên nhân như xử lý null, làm tròn, múi giờ, đồng thời, retry, cache cũ, phân quyền hoặc dữ liệu không nhất quán.
- Kết quả kiểm thử khám phá trước đây và các giả thuyết từng dẫn tới phát hiện.

Không nên chỉ ghi nhớ tên lỗi hoặc vị trí mã. Cần hiểu điều kiện kích hoạt, nguyên nhân gốc, tác động, cách phát hiện và biện pháp đã sửa. Một lỗi đã đóng vẫn có thể gợi ý các trường hợp tương tự ở thành phần khác.

Ví dụ, nếu một phiên bản trước từng đặt trùng lịch do hai yêu cầu đồng thời cùng kiểm tra một khung giờ còn trống, người kiểm thử nên xem xét các luồng giữ chỗ, xác nhận, hủy và thử lại ở các màn hình hoặc dịch vụ có cùng quy tắc.

## 2. Vì sao cần kết hợp cả ba nguồn?

Mỗi nguồn riêng lẻ đều có điểm mù:

| Chỉ dựa vào | Có thể bỏ sót | Cách nguồn khác bổ sung |
| --- | --- | --- |
| Kiến thức người dùng | Hành vi ít gặp nhưng có hậu quả nghiêm trọng; lỗi kỹ thuật chưa từng được người dùng báo cáo | Phân tích rủi ro xác định hậu quả; lịch sử lỗi gợi ý điều kiện kỹ thuật dễ thất bại |
| Danh sách rủi ro | Bối cảnh sử dụng, cách làm việc thực tế và những khó khăn người dùng chưa diễn đạt thành yêu cầu | Quan sát người dùng cho thấy tác vụ, cách dùng thay thế và tác động thực tế |
| Lịch sử lỗi | Vấn đề mới do thay đổi sản phẩm hoặc hành vi mới của người dùng; lỗi cũ có thể không còn liên quan | Người dùng và rủi ro giúp xác định mức độ quan trọng; thay đổi hiện tại giúp cập nhật giả thuyết |

Kết hợp ba nguồn giúp tránh hai thái cực: kiểm thử chỉ lặp lại những gì đã biết, hoặc khám phá ngẫu nhiên mà không có mục tiêu. Người kiểm thử bắt đầu từ thông tin hiện có, sau đó vẫn quan sát và điều chỉnh khi phát hiện điều bất ngờ.

## 3. Thu thập và đánh giá chất lượng thông tin

Trước khi dùng một thông tin để ưu tiên kiểm thử, cần hiểu nó đến từ đâu và đáng tin cậy đến mức nào.

### Phân biệt quan sát, lời kể và giả định

- **Quan sát trực tiếp:** người kiểm thử nhìn thấy hành vi hoặc đo được kết quả trong một tình huống cụ thể.
- **Lời kể hoặc phản hồi:** người dùng hay nhân viên mô tả điều đã xảy ra; thông tin hữu ích nhưng có thể thiếu bước, thời điểm hoặc điều kiện.
- **Dữ liệu tổng hợp:** số liệu cho thấy xu hướng, nhưng có thể không giải thích nguyên nhân hoặc nhóm bị ảnh hưởng.
- **Giả định:** điều nhóm tin là đúng nhưng chưa có bằng chứng đủ mạnh.

Hãy ghi rõ loại thông tin thay vì trình bày giả định như sự thật. Ví dụ, “người dùng thường nhấn nút hai lần” là một giả thuyết nếu chưa quan sát hoặc có dữ liệu hỗ trợ. Có thể kiểm tra giả thuyết bằng quan sát, log sự kiện hoặc thử nghiệm với người dùng.

### Kiểm tra tính liên quan và độ mới

Một báo cáo lỗi từ ba năm trước có thể không còn liên quan nếu thành phần đã được thay thế. Ngược lại, một sự cố cũ vẫn quan trọng nếu cùng quy tắc nghiệp vụ hoặc cùng loại phụ thuộc còn tồn tại.

Khi xem xét thông tin, hỏi:

- Thông tin thuộc phiên bản, cấu hình và phạm vi nào?
- Hành vi hoặc nhóm người dùng có còn tương tự hiện tại không?
- Có bằng chứng xác nhận nguyên nhân hay chỉ có triệu chứng?
- Số lượng quan sát có đủ để nhận diện xu hướng không?
- Có sự kiện mới nào làm thay đổi mức rủi ro không?

### Tránh để một phản hồi đơn lẻ chi phối toàn bộ kế hoạch

Một khiếu nại có thể phản ánh vấn đề nghiêm trọng nhưng cũng có thể là trường hợp cá biệt. Một lỗi xuất hiện nhiều lần có thể do cùng một nguyên nhân, không nhất thiết là nhiều rủi ro độc lập. Nên đối chiếu phản hồi với log, dữ liệu sử dụng, kiểm thử tái hiện, phỏng vấn hoặc thông tin từ nhóm nghiệp vụ.

Không được xem số lượng khiếu nại thấp là bằng chứng chắc chắn rằng người dùng không gặp vấn đề. Một số người dùng không báo lỗi, bỏ dở tác vụ hoặc tự tìm cách khắc phục. Quan sát hành vi và dữ liệu sử dụng giúp phát hiện những vấn đề không được báo cáo trực tiếp.

## 4. Biến thông tin thành giả thuyết kiểm thử

Thông tin chỉ trở nên hữu ích khi được chuyển thành câu hỏi có thể kiểm tra. Có thể dùng cấu trúc:

> Khi **[người dùng hoặc tác nhân]** thực hiện **[hành động]** trong **[điều kiện]**, hệ thống cần **[kết quả mong đợi]**. Nếu không, **[tác động hoặc rủi ro]** có thể xảy ra. Cần thu thập **[bằng chứng quan sát]** để xác minh.

Ví dụ:

> Khi nhân viên lễ tân mở cùng một khung giờ trên hai màn hình và xác nhận gần như đồng thời, hệ thống cần chỉ cho phép một lịch được đặt thành công. Nếu cả hai yêu cầu cùng thành công, hai khách hàng có thể được xếp vào một khung giờ. Cần kiểm tra trạng thái lịch, phản hồi API và dữ liệu lưu cuối cùng.

Một giả thuyết tốt có thể bị bác bỏ bằng quan sát. Tránh câu quá rộng như “kiểm tra xem lịch có hoạt động tốt không” vì không cho biết điều kiện, kết quả và bằng chứng cần thu.

## 5. Kết hợp thông tin theo hành trình người dùng

Hành trình người dùng giúp gắn các tín hiệu từ nhiều nguồn vào một quy trình cụ thể. Với mỗi bước, hãy ghi:

- Mục tiêu của người dùng.
- Hành động và dữ liệu họ cung cấp.
- Điều kiện môi trường và các phụ thuộc.
- Trạng thái hệ thống trước và sau hành động.
- Khó khăn hoặc cách làm thay thế đã quan sát.
- Rủi ro nếu bước đó thất bại.
- Lỗi cũ hoặc mẫu lỗi tương tự.
- Bằng chứng cần thu thập trong phiên kiểm thử.

Ví dụ với quy trình đặt lịch:

| Bước trong hành trình | Kiến thức người dùng | Rủi ro | Kinh nghiệm lỗi cần xem xét |
| --- | --- | --- | --- |
| Tìm khung giờ | Nhân viên thường lọc theo cơ sở, chuyên môn và ngày; người dùng có thể đổi bộ lọc liên tục | Hiển thị khung giờ đã hết hoặc sai cơ sở | Cache kết quả cũ, múi giờ và bộ lọc không được làm mới |
| Giữ khung giờ | Nhân viên cần thời gian gọi xác nhận trước khi hoàn tất | Hai người cùng giữ một khung giờ hoặc giữ chỗ không hết hạn | Race condition, lock hết hạn sai, tác vụ dọn dẹp chậm |
| Xác nhận lịch | Người dùng có thể quay lại trang hoặc gửi lại sau khi mạng chậm | Tạo lịch trùng khi retry | Idempotency thiếu hoặc trạng thái cập nhật không nguyên tử |
| Hủy hoặc đổi lịch | Người dùng có thể đổi lịch nhiều lần do thay đổi kế hoạch | Lịch cũ vẫn giữ chỗ hoặc thông báo sai | Sự kiện đến muộn, cập nhật một phần và lỗi đồng bộ |
| Nhận thông báo | Người dùng cần biết lịch đã được xác nhận hay mới chỉ được yêu cầu | Thông báo gửi sai trạng thái hoặc nhiều lần | Consumer xử lý trùng, retry và dữ liệu template cũ |

Bảng này giúp chọn các bước cần khám phá sâu. Một bước có nhiều khó khăn người dùng, hậu quả lớn và lịch sử lỗi lặp lại thường cần ưu tiên cao.

## 6. Ưu tiên kiểm thử khi có nhiều tín hiệu

Khi nguồn lực hạn chế, nhóm cần giải thích vì sao một khu vực được kiểm tra trước. Có thể dùng ma trận định tính với các yếu tố:

1. **Tác động tới người dùng hoặc nghiệp vụ:** lỗi ảnh hưởng tới tác vụ quan trọng, tiền, dữ liệu, quyền hoặc nghĩa vụ nào?
2. **Mức phơi lộ:** có bao nhiêu người dùng hoặc giao dịch có thể gặp điều kiện này?
3. **Khả năng xảy ra:** điều kiện kích hoạt có phổ biến, dễ tái hiện hoặc xuất hiện trong dữ liệu vận hành không?
4. **Lịch sử lỗi:** khu vực đã từng có lỗi nghiêm trọng, lỗi lặp lại hoặc lỗi lọt production chưa?
5. **Khó phát hiện và khôi phục:** người dùng có nhận biết được vấn đề không; nhóm có thể sửa hoặc đối soát nhanh không?
6. **Mức độ thay đổi:** thành phần vừa được sửa lớn, thay phụ thuộc, thay schema hoặc tái cấu trúc không?

Có thể phân loại ưu tiên:

| Mức ưu tiên | Dấu hiệu thường gặp | Cách phân bổ |
| --- | --- | --- |
| Cao | Hậu quả lớn, nhiều người bị ảnh hưởng, có lỗi lặp lại hoặc thay đổi lớn tại luồng trọng yếu | Khám phá sớm, nhiều góc nhìn, kiểm tra cả nhánh lỗi và trạng thái dữ liệu |
| Trung bình | Tác động vừa phải, điều kiện xảy ra tương đối rõ, có thể phát hiện hoặc khôi phục | Chọn phiên kiểm thử có mục tiêu và dữ liệu đại diện |
| Thấp | Tác động nhỏ, ít phơi lộ, có phương án xử lý dễ dàng và ít thay đổi | Kiểm tra theo checklist hoặc trong thời gian còn lại; ghi rõ phần chưa kiểm tra |

Đây là cách hỗ trợ sắp xếp công việc, không phải công thức thay thế đánh giá chuyên môn. Một lỗi hiếm nhưng có thể gây mất dữ liệu hoặc vi phạm quyền riêng tư vẫn có thể được ưu tiên cao. Không nên cộng điểm máy móc nếu một yếu tố nghiêm trọng bị che khuất bởi các yếu tố khác.

### Ma trận tín hiệu kết hợp

Có thể tạo bảng ngắn để quyết định phiên khám phá:

| Khu vực | Tín hiệu người dùng | Rủi ro chính | Lịch sử lỗi | Quyết định kiểm thử |
| --- | --- | --- | --- | --- |
| Xác nhận đặt lịch | Người dùng thường gửi lại khi mạng chậm | Đặt trùng một khung giờ | Từng có race condition khi hai yêu cầu đến đồng thời | Ưu tiên cao: kiểm thử đồng thời, retry và trạng thái cuối |
| Tìm kiếm lịch | Người dùng thay đổi bộ lọc nhiều lần | Hiển thị kết quả cũ | Từng có lỗi cache không làm mới | Ưu tiên trung bình: thay đổi nhanh bộ lọc, quay lại và làm mới trang |
| Màu sắc biểu tượng | Một số phản hồi cho rằng khó phân biệt | Một nhóm người dùng có thể khó nhận biết trạng thái | Chưa có lỗi chức năng liên quan | Kiểm thử khả năng tiếp cận với màu, nhãn và trình đọc màn hình |

## 7. Dùng kinh nghiệm lỗi để mở rộng khám phá

Không nên chỉ chạy lại đúng bước đã từng làm lỗi. Hãy phân tích nguyên nhân và tìm các điều kiện tương tự ở những luồng khác.

### Từ triệu chứng đến điều kiện kích hoạt

Một báo cáo “đặt lịch bị trùng” mới chỉ mô tả triệu chứng. Phân tích sâu hơn có thể cho thấy:

- Hai yêu cầu đến gần như đồng thời.
- Cả hai đều đọc trạng thái khung giờ là còn trống.
- Không có ràng buộc duy nhất hoặc cơ chế khóa phù hợp ở nơi lưu dữ liệu.
- Hai yêu cầu cùng ghi thành công.

Từ nguyên nhân này, có thể khám phá thêm:

- Hai trình duyệt hoặc hai tài khoản cùng đặt một khung giờ.
- Một yêu cầu được gửi lại sau timeout.
- Consumer nhận sự kiện xác nhận hai lần.
- Tác vụ hết hạn giữ chỗ chạy đồng thời với thao tác xác nhận.
- Hệ thống xử lý hai cơ sở dữ liệu hoặc replica có độ trễ đồng bộ.

Đây là cách dùng kinh nghiệm lỗi để mở rộng không gian kiểm thử. Các trường hợp mới cần dựa trên cơ chế gây lỗi, không chỉ dựa trên việc thay đổi ngẫu nhiên dữ liệu.

### Xem xét mẫu lỗi theo loại

| Mẫu lỗi từng gặp | Điều kiện nên khám phá | Câu hỏi cần trả lời |
| --- | --- | --- |
| Race condition | Yêu cầu đồng thời, thao tác gần nhau về thời gian, nhiều phiên người dùng | Có trạng thái hoặc tác động nào được áp dụng hai lần không? |
| Sai múi giờ/ngày giờ | Gần nửa đêm, đổi múi giờ, giờ mùa hè nếu có, lịch qua ngày | Ngày và giờ được lưu, hiển thị và so sánh theo quy tắc nào? |
| Làm tròn hoặc sai số tiền | Giá trị biên, nhiều loại tiền, thuế, chiết khấu kết hợp | Tổng tiền và số tiền hiển thị có nhất quán không? |
| Cache cũ | Thay đổi dữ liệu rồi đọc lại, nhiều người dùng, nhiều phiên bản | Người dùng có nhìn thấy trạng thái cũ sau khi dữ liệu đã đổi không? |
| Retry tạo tác động lặp | Timeout, gửi lại, mất acknowledgement, consumer khởi động lại | Cùng một hành động có được áp dụng đúng số lần không? |
| Phân quyền thiếu | Đổi vai trò, truy cập trực tiếp URL/API, dùng tài nguyên của người khác | Quyền được kiểm tra ở mọi ranh giới hay chỉ ở giao diện? |
| Xử lý null hoặc dữ liệu không đầy đủ | Trường vắng mặt, null, rỗng, dữ liệu cũ và dữ liệu nhập tay | Hệ thống có phản hồi rõ ràng và giữ bất biến không? |
| Sai thứ tự sự kiện | Sự kiện đến muộn, trùng hoặc đảo thứ tự | Trạng thái cuối có hợp lệ và có thể đối soát không? |

### Kiểm tra vùng thay đổi

Thay đổi mã nguồn, cấu hình, thư viện hoặc schema là một tín hiệu quan trọng. Kết hợp lịch sử lỗi với bản đồ thay đổi để xác định:

- Thành phần nào vừa được sửa hoặc tái cấu trúc?
- Thành phần nào phụ thuộc vào giao diện đã thay đổi?
- Lỗi cũ nào từng xuất hiện trong cùng khu vực?
- Quy tắc nào được dùng ở nhiều luồng nhưng chỉ được kiểm thử tại một nơi?
- Có đường dữ liệu hoặc vai trò người dùng mới không?

Người kiểm thử không cần biết mọi chi tiết mã nguồn để làm điều này. Trao đổi với lập trình viên, xem mô tả thay đổi và đọc báo cáo lỗi có thể giúp nhận diện các vùng cần khám phá.

## 8. Thiết kế phiên kiểm thử khám phá có mục tiêu

Một phiên kiểm thử khám phá (exploratory testing session) nên có nhiệm vụ rõ nhưng đủ linh hoạt để người kiểm thử học hỏi và thay đổi hướng đi.

### Viết charter

Charter là mô tả ngắn về mục tiêu khám phá. Một charter tốt nêu:

- **Sứ mệnh:** điều cần tìm hiểu hoặc rủi ro cần kiểm tra.
- **Phạm vi:** tính năng, hành trình, vai trò, nền tảng hoặc dịch vụ liên quan.
- **Góc nhìn người dùng:** ai thực hiện, mục tiêu và bối cảnh của họ.
- **Giả thuyết/rủi ro:** điều gì có thể sai và hậu quả.
- **Gợi ý khám phá:** dữ liệu, trạng thái hoặc điều kiện đáng thử.
- **Bằng chứng:** kết quả, trạng thái, log, ảnh hoặc trace cần ghi.

Ví dụ charter:

> Khám phá việc giữ và xác nhận lịch từ góc nhìn nhân viên lễ tân đang xử lý nhiều cuộc gọi. Tập trung vào hai phiên làm việc cùng chọn một khung giờ, mạng chậm, giữ chỗ hết hạn và thao tác gửi lại. Tìm dấu hiệu đặt trùng, giữ chỗ không giải phóng hoặc trạng thái hiển thị không đúng. Ghi lại mã lịch, thời điểm, trạng thái API và dữ liệu cuối.

Charter xác định hướng đi nhưng không phải danh sách bước cố định. Nếu quan sát được một hành vi bất ngờ, người kiểm thử có thể điều chỉnh dữ liệu hoặc luồng để tìm hiểu nguyên nhân, miễn là vẫn ghi lại mối liên hệ với mục tiêu.

### Chuẩn bị phiên

Trước khi bắt đầu, xác định:

- Build, môi trường và cấu hình cần dùng.
- Vai trò và tài khoản thử nghiệm phù hợp.
- Dữ liệu ban đầu, cách tạo và dọn dẹp.
- Thiết bị, trình duyệt, mạng hoặc công cụ quan sát.
- Thời lượng phiên và người tham gia nếu kiểm thử theo cặp.
- Cách ghi nhận lỗi và liên kết với rủi ro hoặc lịch sử lỗi.

Không dùng dữ liệu cá nhân thật hoặc thực hiện hành động có tác động thật nếu chưa có cơ sở và kiểm soát phù hợp. Với thanh toán, gửi thông báo hoặc đặt dịch vụ thật, hãy dùng sandbox, dữ liệu thử hoặc môi trường đã được cho phép.

### Thực hiện và điều chỉnh

Trong phiên, người kiểm thử:

1. Bắt đầu với charter và dữ liệu đã chuẩn bị.
2. Quan sát phản hồi của hệ thống và cách người dùng có thể hiểu phản hồi đó.
3. Thử thay đổi điều kiện có liên quan đến giả thuyết, chẳng hạn tốc độ mạng, vai trò, thứ tự thao tác hoặc dữ liệu biên.
4. Khi phát hiện dấu hiệu bất thường, lặp lại với điều kiện kiểm soát để xác định có thể tái hiện không.
5. Theo dõi tác động đến dữ liệu, trạng thái và các thành phần liên quan.
6. Ghi nhận điều đã thử, điều đã học và câu hỏi còn mở.

Khám phá không đồng nghĩa với thao tác ngẫu nhiên. Mỗi bước nên có lý do: kiểm tra một rủi ro, xác minh một giả thuyết hoặc tìm hiểu hành vi chưa rõ.

## 9. Ghi chép để biến kinh nghiệm thành bằng chứng

Kiểm thử thủ công và khám phá có thể tạo ra nhiều phát hiện có giá trị nhưng khó tái hiện nếu ghi chép không đầy đủ.

Một ghi chép phiên nên bao gồm:

- Charter và thời lượng thực tế.
- Build, môi trường, cấu hình, vai trò và dữ liệu.
- Các hành động chính và điều kiện đã thay đổi.
- Kết quả mong đợi và kết quả quan sát.
- Lỗi, hành vi bất ngờ, bằng chứng và mức độ tái hiện.
- Rủi ro hoặc lịch sử lỗi có liên quan.
- Những khu vực đã khám phá, chưa khám phá và câu hỏi tiếp theo.

Một báo cáo lỗi nên nêu bước tái hiện tối thiểu, dữ liệu, kết quả mong đợi, kết quả thực tế, tần suất, tác động và bằng chứng. Nếu lỗi chỉ xuất hiện khi hai thao tác diễn ra đồng thời, cần ghi cách tạo đồng thời hoặc dấu thời gian để người khác có thể thử lại.

### Mẫu ghi chép phiên

```text
SESSION: EXP-BOOKING-04
MISSION: Tìm lỗi đặt trùng khi giữ và xác nhận lịch
BUILD / ENVIRONMENT: build-218 / test environment
USER CONTEXT: Nhân viên lễ tân, hai phiên làm việc
RISK: Hai khách hàng có thể được xác nhận cùng một khung giờ
HISTORY: Từng có race condition trong bước kiểm tra lịch trống
ACTIONS:
  - Mở cùng khung giờ trên hai phiên
  - Gửi xác nhận gần như đồng thời
  - Lặp lại với một yêu cầu bị timeout
OBSERVATION:
  - Hai phản hồi trả về thành công
  - Hai mã lịch khác nhau cùng tham chiếu một khung giờ
EVIDENCE: request IDs, timestamps, booking IDs, database state
RESULT: Defect candidate; reproducibility 3/5 runs
FOLLOW-UP: Kiểm tra ràng buộc duy nhất và tính nguyên tử của thao tác giữ lịch
```

Mẫu này là ví dụ về cấu trúc. Các giá trị thực tế phải lấy từ phiên kiểm thử. Không ghi token, mật khẩu hoặc dữ liệu nhạy cảm vào ghi chép.

## 10. Từ phát hiện đến học hỏi và cải thiện

Mỗi phiên khám phá nên tạo ra một vòng phản hồi. Sau khi phát hiện lỗi hoặc xác minh một giả thuyết, nhóm cần cập nhật hiểu biết để lần kiểm thử sau tập trung hơn.

### Phân tích nguyên nhân và phạm vi liên quan

Khi lỗi được xác nhận, hãy tìm hiểu:

- Điều kiện trực tiếp kích hoạt lỗi.
- Nguyên nhân trong yêu cầu, thiết kế, mã, dữ liệu, cấu hình hoặc vận hành.
- Vì sao kiểm thử trước đó không phát hiện.
- Thành phần hoặc luồng khác có cùng cơ chế không.
- Biện pháp sửa có thể tạo tác động phụ nào.

Từ phân tích này, bổ sung trường hợp hồi quy ở nơi phù hợp, cập nhật checklist hoặc charter, và liên kết với rủi ro. Nếu nguyên nhân là một mẫu lỗi có thể tái diễn, hãy tìm các điểm sử dụng cùng quy tắc hoặc thư viện.

### Ghi nhận near miss và điểm yếu quy trình

Không chỉ lỗi đã gây thiệt hại mới có giá trị. Một tình huống gần gây ra lỗi, được phát hiện nhờ kiểm soát hoặc do người dùng báo trước, có thể chỉ ra điểm yếu trong thiết kế hoặc quy trình.

Ví dụ, hệ thống đã từ chối một lần đặt trùng nhờ ràng buộc database, nhưng giao diện vẫn hiển thị thông báo thành công trong vài giây. Dữ liệu cuối không sai, nhưng người dùng có thể hiểu nhầm và thực hiện thao tác khác. Đây là tín hiệu để khám phá cả tính nhất quán của thông báo và khả năng xử lý xung đột.

### Cập nhật tri thức dùng chung

Những bài học có thể được đưa vào:

- Bộ kiểm thử hồi quy tự động khi hành vi ổn định và có thể kiểm tra lặp lại.
- Checklist kiểm thử thủ công cho các tình huống cần quan sát.
- Charter khám phá cho rủi ro còn chưa hiểu rõ.
- Danh mục mẫu lỗi và điều kiện kích hoạt.
- Tài liệu rủi ro, tiêu chí chấp nhận và hướng dẫn vận hành.

Không phải mọi bước khám phá đều cần tự động hóa. Một số đánh giá về khả năng sử dụng, sự dễ hiểu hoặc hành vi mới cần con người quan sát. Hãy tự động hóa những kiểm tra có kết quả rõ, lặp lại thường xuyên và có chi phí bảo trì hợp lý; giữ lại khám phá thủ công cho những câu hỏi cần phán đoán và học hỏi.

## 11. Ví dụ tổng hợp: kiểm thử khám phá quy trình đặt lịch

Giả sử một nền tảng cho phép khách hàng đặt lịch dịch vụ. Nhân viên hỗ trợ phản ánh rằng đôi khi khách hàng thấy lịch đã được xác nhận nhưng nhân viên không tìm thấy lịch trong danh sách. Dữ liệu sử dụng cho thấy một số người dùng gửi yêu cầu lại khi màn hình chờ lâu. Lịch sử lỗi có một sự cố đặt trùng do hai yêu cầu đồng thời.

### Tổng hợp ba nguồn

| Nguồn | Thông tin | Câu hỏi hoặc rủi ro được hình thành |
| --- | --- | --- |
| Người dùng | Người dùng gửi lại khi không thấy phản hồi; nhân viên mở nhiều phiên để xử lý cuộc gọi | Phản hồi chậm có khiến tạo lịch nhiều lần hoặc hiển thị trạng thái sai không? |
| Rủi ro | Một khung giờ chỉ được xác nhận cho một khách hàng; đặt trùng ảnh hưởng trực tiếp đến dịch vụ | Hai yêu cầu đồng thời có thể cùng được xác nhận không? |
| Kinh nghiệm lỗi | Từng có race condition ở bước đọc lịch trống rồi ghi lịch | Có thể tái hiện lỗi khi hai yêu cầu kiểm tra và xác nhận gần như cùng lúc không? |

### Charter khám phá

> Khám phá hành trình đặt lịch khi phản hồi chậm hoặc có nhiều phiên làm việc. Thử gửi lại yêu cầu, xác nhận đồng thời, làm mới trang và hủy lịch gần thời điểm hết hạn giữ chỗ. Ưu tiên phát hiện lịch trùng, trạng thái giao diện khác dữ liệu lưu, hoặc thông báo xác nhận trước khi giao dịch hoàn tất. Ghi mã yêu cầu, mã lịch, dấu thời gian, trạng thái API và dữ liệu cuối.

### Các trường hợp nên thử

1. Hai người dùng chọn cùng một khung giờ và xác nhận gần như đồng thời.
2. Người dùng gửi lại cùng yêu cầu sau khi client timeout nhưng server đã tạo lịch.
3. Một người hủy lịch trong khi người khác đang xác nhận khung giờ đó.
4. Giữ chỗ hết hạn đúng lúc tác vụ nền đang giải phóng lịch.
5. Người dùng mở hai tab, một tab xác nhận và tab kia vẫn hiển thị trạng thái cũ.
6. Thông báo xác nhận đến muộn sau khi lịch đã bị hủy hoặc thay đổi.

### Đánh giá phát hiện

Nếu hai yêu cầu cùng nhận phản hồi thành công nhưng dữ liệu chỉ có một lịch, cần kiểm tra xem phản hồi nào sai và người dùng nhận thông báo gì. Nếu dữ liệu có hai lịch cùng khung giờ, đây là lỗi ảnh hưởng trực tiếp đến tính toàn vẹn nghiệp vụ. Nếu dữ liệu đúng nhưng giao diện hiển thị sai, cần đánh giá tác động tới quyết định của người dùng và khả năng họ thực hiện thao tác lặp.

Nhóm nên tái hiện với cùng dữ liệu và điều kiện, liên kết log/trace, phân tích nguyên nhân, cập nhật rủi ro và bổ sung kiểm thử hồi quy cho cơ chế chống trùng. Sau đó, mở rộng khám phá sang luồng đổi lịch, hủy lịch và các dịch vụ khác dùng chung cơ chế giữ chỗ.

## 12. Phối hợp giữa người kiểm thử, người dùng và nhóm phát triển

Kết hợp ba nguồn hiểu biết cần sự trao đổi giữa nhiều vai trò:

- **Người dùng hoặc đại diện nghiệp vụ:** giải thích mục tiêu, bối cảnh, cách làm việc, tác động và trường hợp ngoại lệ.
- **Nhân viên hỗ trợ và vận hành:** cung cấp phản hồi, sự cố, dấu hiệu khó phát hiện và quy trình xử lý thực tế.
- **Người kiểm thử:** kết nối thông tin với rủi ro, thiết kế charter, thực hiện khám phá và lưu bằng chứng.
- **Lập trình viên:** giải thích thay đổi, ranh giới thành phần, nguyên nhân lỗi và cách tạo điều kiện tái hiện.
- **Chủ sản phẩm hoặc người quản lý rủi ro:** giúp xếp ưu tiên và quyết định mức rủi ro cần xử lý.

Trong một buổi khám phá theo cặp, một người có thể thao tác còn người kia quan sát, ghi chép và đặt câu hỏi. Vai trò có thể đổi trong phiên. Người quan sát nên ghi lại cả hành vi hệ thống và cách người dùng diễn giải phản hồi, vì một giao diện kỹ thuật đúng vẫn có thể khiến người dùng đưa ra quyết định sai.

Không nên yêu cầu người dùng cung cấp dữ liệu nhạy cảm để tái hiện lỗi nếu có thể dùng dữ liệu giả lập. Khi phỏng vấn hoặc quan sát, chỉ thu thập thông tin cần thiết và tuân theo quy trình bảo vệ dữ liệu của tổ chức.

## 13. Tránh thiên kiến khi kết hợp thông tin

Người kiểm thử có thể bị ảnh hưởng bởi những gì đã biết. Một lỗi từng gây sự cố lớn dễ khiến nhóm chỉ tìm lỗi cùng loại; một yêu cầu từ người dùng có ảnh hưởng có thể được ưu tiên quá mức; một khu vực chưa từng có lỗi có thể bị xem là an toàn.

Các cách giảm thiên kiến:

- **Tách bằng chứng và giả định:** ghi nhãn rõ thông tin đã quan sát, lời kể và điều chưa xác minh.
- **Tìm bằng chứng trái chiều:** nếu giả thuyết là hệ thống đặt trùng, cũng kiểm tra các cơ chế ngăn trùng đang hoạt động trong điều kiện khác.
- **Xem xét nhóm ít được đại diện:** người dùng thiết bị cũ, kết nối yếu, dùng bàn phím hoặc có nhu cầu tiếp cận khác.
- **Cập nhật lịch sử lỗi:** phân biệt lỗi còn liên quan với lỗi đã được loại bỏ bởi thay đổi kiến trúc.
- **Không chỉ kiểm tra vùng có lỗi cũ:** dành một phần thời gian khám phá hành vi mới, thay đổi lớn và đường đi ít được sử dụng.
- **Dùng nhiều nguồn:** đối chiếu phản hồi, dữ liệu vận hành, kết quả kiểm thử và phân tích nguyên nhân.
- **Ghi giới hạn mẫu:** một vài người dùng hoặc một vài phiên kiểm thử không đại diện cho mọi nhóm và điều kiện.

Kiểm thử khám phá cần linh hoạt nhưng kết luận phải dựa trên bằng chứng. Nếu chưa đủ thông tin, ghi rõ điều chưa biết và đề xuất cách kiểm tra tiếp.

## 14. Đánh giá hiệu quả của hoạt động khám phá

Không nên chỉ đo hiệu quả bằng số lỗi tìm được hoặc số trường hợp đã chạy. Các chỉ số hỗ trợ có thể gồm:

- Tỷ lệ rủi ro ưu tiên cao đã có hoạt động kiểm tra và bằng chứng.
- Số lỗi nghiêm trọng được phát hiện trước phát hành so với sau phát hành.
- Tỷ lệ lỗi tái diễn do cùng nguyên nhân sau khi đã có biện pháp sửa.
- Thời gian từ khi phát hiện tín hiệu đến khi tái hiện và xác định phạm vi.
- Tỷ lệ hành động sau phiên khám phá được hoàn tất và xác minh.
- Mức độ bao phủ các nhóm người dùng, nền tảng và điều kiện quan trọng.
- Chất lượng ghi chép: người khác có thể tái hiện hoặc tiếp tục khám phá không?

Các chỉ số này cần được đọc theo xu hướng và bối cảnh. Số lỗi phát hiện tăng có thể phản ánh kiểm thử tốt hơn hoặc sản phẩm kém ổn định hơn. Số lỗi production giảm có thể do sản phẩm tốt hơn, nhưng cũng có thể do ít người sử dụng hoặc ít báo cáo hơn.

## 15. Checklist kết hợp ba nguồn hiểu biết

- [ ] Hành trình và mục tiêu người dùng đã được mô tả bằng ví dụ hoặc quan sát thực tế.
- [ ] Phản hồi, dữ liệu sử dụng và lời kể được phân biệt với giả định.
- [ ] Rủi ro được đánh giá theo khả năng xảy ra, tác động, phạm vi và khả năng phát hiện/khôi phục.
- [ ] Lịch sử lỗi được xem xét theo nguyên nhân, điều kiện kích hoạt và phạm vi liên quan.
- [ ] Các thay đổi mới và vùng chưa có lịch sử lỗi cũng được xem xét.
- [ ] Thông tin từ ba nguồn đã được chuyển thành giả thuyết có thể kiểm tra.
- [ ] Charter nêu rõ sứ mệnh, phạm vi, bối cảnh người dùng, rủi ro và bằng chứng.
- [ ] Phiên kiểm thử có dữ liệu, môi trường và cách quan sát phù hợp.
- [ ] Phát hiện được ghi với điều kiện tái hiện, tác động và bằng chứng.
- [ ] Bài học được đưa vào kiểm thử hồi quy, checklist, charter hoặc hồ sơ rủi ro phù hợp.
- [ ] Giới hạn, giả định và câu hỏi chưa được giải quyết được ghi rõ.

## 16. Những điểm cần ghi nhớ

- Kiến thức người dùng cho biết điều gì quan trọng trong công việc thực tế và bối cảnh sử dụng.
- Phân tích rủi ro giúp ưu tiên tình huống theo khả năng xảy ra, tác động, phạm vi và mức độ bất định.
- Lịch sử lỗi cho biết mẫu nguyên nhân, điều kiện kích hoạt và khu vực có thể tái diễn vấn đề.
- Kết hợp ba nguồn giúp chọn hành trình và giả thuyết khám phá có trọng tâm.
- Phân biệt quan sát, lời kể, dữ liệu tổng hợp và giả định; kiểm tra tính liên quan và độ mới của thông tin.
- Dùng charter để định hướng phiên khám phá nhưng vẫn điều chỉnh theo điều quan sát được.
- Ghi chép đủ điều kiện, dữ liệu, trạng thái và bằng chứng để người khác có thể tái hiện.
- Chuyển bài học thành kiểm thử hồi quy, checklist, charter và cập nhật rủi ro khi phù hợp.
- Tránh thiên kiến bằng cách tìm bằng chứng trái chiều, xem xét nhóm người dùng đa dạng và ghi rõ giới hạn.

## Câu hỏi tự kiểm tra

1. Ba nguồn kiến thức người dùng, rủi ro và kinh nghiệm lỗi trả lời những câu hỏi khác nhau nào?
2. Vì sao một phản hồi đơn lẻ của người dùng cần được đối chiếu với dữ liệu hoặc quan sát khác?
3. Hãy chuyển một khiếu nại hoặc quan sát người dùng thành giả thuyết kiểm thử có điều kiện, kết quả và bằng chứng.
4. Một lỗi từng xảy ra do retry tạo tác động lặp. Bạn sẽ mở rộng khám phá sang những luồng hoặc điều kiện nào?
5. Hãy lập bảng kết hợp ba nguồn thông tin cho một hành trình sản phẩm bạn biết và giải thích thứ tự ưu tiên.
6. Một khu vực chưa từng có lỗi có nên được xem là ít rủi ro không? Cần thêm thông tin gì?
7. Hãy viết một charter khám phá nêu sứ mệnh, phạm vi, bối cảnh người dùng, rủi ro và bằng chứng cần ghi.
8. Sau khi phát hiện lỗi trong phiên khám phá, nhóm nên làm gì để bài học được dùng lại trong các lần kiểm thử sau?
