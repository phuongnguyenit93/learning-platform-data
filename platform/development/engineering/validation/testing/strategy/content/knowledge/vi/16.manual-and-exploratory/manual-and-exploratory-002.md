# Lập mục tiêu và phạm vi phiên kiểm thử khám phá

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, kiểm thử khám phá (exploratory testing) giúp nhóm tìm hiểu sản phẩm, thiết kế thử nghiệm và thực hiện kiểm tra đồng thời dựa trên những gì vừa quan sát được. Hoạt động này đặc biệt hữu ích khi yêu cầu chưa bao quát mọi tình huống, sản phẩm có nhiều trạng thái, hành vi phụ thuộc vào dữ liệu hoặc nhóm cần tìm những vấn đề khó dự đoán bằng kịch bản viết sẵn.

Một phiên khám phá có hiệu quả cần có **mục tiêu rõ ràng và phạm vi đủ cụ thể**. Nếu chỉ mở ứng dụng rồi thao tác tùy ý, nhóm có thể bỏ sót rủi ro quan trọng, lặp lại việc đã làm hoặc không giải thích được kết quả. Nếu kịch bản quy định sẵn từng bước và kết quả đến mức người kiểm thử chỉ làm theo, hoạt động lại mất đi khả năng học hỏi và điều chỉnh của kiểm thử khám phá. Cần xác định hướng tìm hiểu, ranh giới, thời lượng và bằng chứng cần ghi nhận, đồng thời để người kiểm thử tự lựa chọn đường đi dựa trên quan sát.

## 1. Phiên kiểm thử khám phá là gì?

Kiểm thử khám phá là cách tiếp cận trong đó người kiểm thử liên tục kết hợp ba hoạt động:

- **Học hỏi:** tìm hiểu sản phẩm, quy tắc, trạng thái, dữ liệu và bối cảnh sử dụng.
- **Thiết kế thử nghiệm:** hình thành câu hỏi, giả thuyết, dữ liệu và bước tiếp theo dựa trên hiểu biết hiện tại.
- **Thực thi và quan sát:** tương tác với sản phẩm, so sánh kết quả, ghi nhận bất thường rồi điều chỉnh hướng khám phá.

Ba hoạt động diễn ra đan xen. Ví dụ, khi kiểm tra giỏ hàng, người kiểm thử nhận thấy số lượng sản phẩm thay đổi sau khi áp dụng mã giảm giá. Quan sát này gợi ra câu hỏi mới: mã giảm giá được tính lại thế nào khi số lượng giảm xuống dưới ngưỡng? Người kiểm thử có thể thay đổi dữ liệu, thử lại, kiểm tra trạng thái đơn và ghi nhận kết quả ngay trong phiên.

Kiểm thử khám phá không có nghĩa là làm việc không có kế hoạch. Nhóm vẫn cần xác định mục tiêu, rủi ro, điều kiện và thời lượng. Điểm khác biệt là các trường hợp kiểm tra cụ thể được phát triển linh hoạt trong quá trình khám phá, thay vì toàn bộ đường đi đã được định trước.

## 2. Vì sao cần xác định mục tiêu và phạm vi?

Một phiên kiểm thử thường bị giới hạn bởi thời gian, môi trường và người thực hiện. Mục tiêu và phạm vi giúp nhóm dùng thời gian có chủ đích, tạo ra bằng chứng có thể chia sẻ và biết phần nào chưa được kiểm tra.

Mục tiêu rõ giúp trả lời:

- Vấn đề, rủi ro hoặc giả định nào cần tìm hiểu?
- Sau phiên này, nhóm cần biết thêm điều gì hoặc có thể đưa ra quyết định nào?
- Những hành vi hay tình huống nào có khả năng bộc lộ lỗi quan trọng?
- Bằng chứng nào cần ghi lại để người khác hiểu và tái hiện phát hiện?

Phạm vi rõ giúp xác định:

- Thành phần, chức năng, luồng nghiệp vụ hoặc thuộc tính chất lượng được khám phá.
- Vai trò người dùng, trạng thái, dữ liệu, thiết bị và môi trường liên quan.
- Điều kiện bắt đầu, điều kiện dừng và thời lượng dự kiến.
- Phần nào được loại trừ và lý do loại trừ.
- Những phụ thuộc hoặc giới hạn có thể ảnh hưởng đến kết luận.

Không có mục tiêu cụ thể, phiên kiểm thử dễ biến thành thao tác ngẫu nhiên. Không có phạm vi, người kiểm thử có thể đi quá xa khỏi vấn đề đang cần đánh giá hoặc dành hết thời gian cho một nhánh ít rủi ro.

## 3. Session charter — bản định hướng phiên khám phá

Nhóm có thể dùng một *session charter* (bản định hướng phiên) để thống nhất mục tiêu và ranh giới trước khi bắt đầu. Charter không phải danh sách bước bắt buộc phải làm theo. Nó mô tả nhiệm vụ khám phá, câu hỏi cần tìm hiểu và giới hạn để người kiểm thử tự thiết kế các thử nghiệm phù hợp.

Một charter thường gồm:

1. **Tên phiên:** ngắn gọn, nhận diện được khu vực hoặc rủi ro.
2. **Nhiệm vụ (mission):** điều cần khám phá, diễn đạt bằng động từ và mục đích.
3. **Mục tiêu học hỏi:** câu hỏi hoặc giả thuyết cần được làm rõ.
4. **Phạm vi trong:** chức năng, luồng, vai trò, trạng thái hoặc thuộc tính được tập trung.
5. **Phạm vi ngoài:** phần không kiểm tra trong phiên và lý do.
6. **Rủi ro ưu tiên:** hậu quả hoặc tình huống có giá trị phát hiện cao.
7. **Điều kiện và dữ liệu:** build, môi trường, tài khoản, dữ liệu đầu vào, thiết bị và phụ thuộc.
8. **Thời lượng:** timebox và mốc dừng hoặc debrief.
9. **Bằng chứng:** thông tin cần ghi nhận, ảnh chụp, log, ID giao dịch hoặc bước tái hiện.
10. **Tiêu chí kết thúc:** điều kiện hoàn thành, chuyển hướng hoặc dừng sớm.

Không nhất thiết charter phải dài. Với một phiên ngắn, vài dòng có thể đủ nếu nêu được nhiệm vụ, phạm vi, điều kiện và thời lượng. Với khu vực rủi ro cao, cần mô tả rõ hơn các trạng thái, vai trò, dữ liệu và giới hạn an toàn.

## 4. Viết mục tiêu khám phá cụ thể

Mục tiêu nên tập trung vào điều cần học hoặc rủi ro cần kiểm tra, thay vì chỉ ghi tên chức năng.

Ví dụ mục tiêu còn mơ hồ:

- Test giỏ hàng.
- Kiểm tra thanh toán.
- Khám phá màn hình quản trị.
- Tìm lỗi ở API đơn hàng.

Các mục tiêu này chưa nói rõ cần quan sát điều gì hoặc khi nào phiên được xem là hữu ích.

Ví dụ mục tiêu rõ hơn:

- Khám phá cách giỏ hàng tính lại tổng tiền khi người dùng thay đổi số lượng, áp dụng hoặc gỡ mã giảm giá và thay đổi địa chỉ giao hàng.
- Tìm các trạng thái không nhất quán khi thanh toán timeout, người dùng tải lại trang hoặc cổng thanh toán gửi kết quả chậm.
- Đánh giá liệu nhân viên kho có thể xác nhận phiếu đúng quyền và không làm tăng tồn kho hai lần khi gửi lại thao tác.
- Tìm hiểu cách API đơn hàng phản ứng với dữ liệu thiếu, giá trị biên và yêu cầu lặp trong điều kiện xác thực hợp lệ.

### Công thức hỗ trợ viết mục tiêu

Có thể dùng cấu trúc:

> Khám phá [khu vực/hành vi] trong điều kiện [bối cảnh/đầu vào] để tìm hiểu [câu hỏi/rủi ro/kết quả cần quan sát].

Ví dụ:

> Khám phá luồng đặt lại mật khẩu trên thiết bị di động với tài khoản có nhiều trạng thái để tìm hiểu cách hệ thống xử lý liên kết hết hạn, yêu cầu lặp và thông báo lỗi.

Mục tiêu không cần dự đoán trước mọi lỗi. Nó cần đủ rõ để hướng sự chú ý, nhưng vẫn để người kiểm thử theo đuổi những phát hiện mới có liên quan.

### Phân biệt mục tiêu, giả thuyết và kết quả mong đợi

- **Mục tiêu** nói điều phiên cần khám phá, ví dụ đánh giá xử lý retry của thao tác thanh toán.
- **Giả thuyết** là dự đoán có thể kiểm tra, ví dụ gửi lại cùng yêu cầu sau timeout sẽ không tạo thêm giao dịch.
- **Kết quả mong đợi** là hành vi được xác định từ yêu cầu, hợp đồng hoặc quy tắc nghiệp vụ.
- **Quan sát thực tế** là điều hệ thống thực sự thể hiện trong phiên.

Không nên biến giả thuyết của người kiểm thử thành yêu cầu chính thức nếu chưa được xác nhận. Khi đặc tả không rõ, ghi lại câu hỏi và trao đổi với chủ sở hữu nghiệp vụ thay vì tự suy diễn kết quả đúng.

## 5. Xác định phạm vi trong và ngoài

Phạm vi cần đủ hẹp để có thể khám phá sâu trong timebox, nhưng đủ rộng để theo đuổi các nhánh liên quan khi phát hiện mới xuất hiện.

### Phạm vi trong

Nêu rõ các phần cần tập trung:

- Chức năng hoặc thành phần cụ thể.
- Các luồng chính và trạng thái quan trọng.
- Vai trò, quyền và loại người dùng.
- Dữ liệu bình thường, biên, bất thường hoặc lịch sử.
- Tích hợp và phụ thuộc có liên quan.
- Thuộc tính chất lượng cần quan sát, chẳng hạn tính đúng đắn, khả năng sử dụng, bảo mật hoặc độ tin cậy.

### Phạm vi ngoài

Ghi rõ phần không thuộc phiên, ví dụ:

- Kiểm thử tải lớn vì phiên này tập trung vào quy tắc nghiệp vụ.
- Kiểm thử bảo mật chuyên sâu vì cần một phiên riêng và môi trường được phê duyệt.
- Các trình duyệt ngoài danh sách hỗ trợ.
- Luồng hoàn tiền vì không nằm trong thay đổi đang được đánh giá.
- Dữ liệu production thật vì không phù hợp với điều kiện an toàn của phiên.

Phạm vi ngoài không có nghĩa khu vực đó không cần kiểm thử. Nó chỉ xác định phần chưa được khám phá trong phiên hiện tại. Nếu rủi ro của phần ngoài vẫn đáng kể, cần ghi nhận để lập phiên hoặc hoạt động khác.

### Xác định ranh giới có thể mở rộng

Trong quá trình khám phá, một phát hiện có thể dẫn sang khu vực khác. Ví dụ, lỗi tổng tiền trong giỏ hàng có thể liên quan đến dịch vụ tính giá hoặc mã giảm giá. Người kiểm thử nên theo đuổi nhánh mới khi nó giúp làm rõ mục tiêu hoặc phát hiện rủi ro quan trọng, đồng thời ghi nhận lý do thay đổi phạm vi.

Nếu nhánh mới cần nhiều thời gian hoặc phụ thuộc khác, hãy ghi thành câu hỏi tiếp nối cho phiên sau thay vì để phiên hiện tại mất kiểm soát. Có thể dùng nguyên tắc: tiếp tục khi phát hiện liên quan trực tiếp và có giá trị cao; tách phiên khi mục tiêu, môi trường hoặc kỹ năng cần thiết đã khác đáng kể.

## 6. Chọn phạm vi theo rủi ro

Không nên phân bổ thời gian khám phá đồng đều cho mọi màn hình hoặc chức năng. Hãy ưu tiên khu vực có khả năng phát sinh lỗi và hậu quả lớn.

Các tín hiệu rủi ro có thể gồm:

- Chức năng mới, vừa thay đổi hoặc có nhiều lỗi lịch sử.
- Logic có nhiều điều kiện, trạng thái và tổ hợp dữ liệu.
- Tích hợp với dịch vụ bên ngoài hoặc phụ thuộc mạng.
- Xử lý tiền, quyền, dữ liệu cá nhân hoặc dữ liệu không thể khôi phục.
- Quy trình có nhiều bước và có thể bị gián đoạn giữa chừng.
- Hành vi phụ thuộc vào thời gian, múi giờ, đồng thời hoặc sự kiện bất đồng bộ.
- Yêu cầu chưa rõ, thiếu tiêu chí hoặc có nhiều cách diễn giải.

Có thể xếp hạng rủi ro theo mức tác động và khả năng xảy ra, sau đó chọn nhiệm vụ khám phá. Điểm số chỉ hỗ trợ ưu tiên; các yêu cầu an toàn, bảo mật và tuân thủ bắt buộc vẫn cần được xử lý theo chính sách riêng.

### Ví dụ ma trận ưu tiên

| Khu vực | Rủi ro chính | Ưu tiên phiên khám phá | Hướng tìm hiểu |
|---|---|---|---|
| Thanh toán | Ghi nhận trùng hoặc sai trạng thái | Rất cao | Timeout, retry, tải lại trang, webhook trễ/lặp |
| Quyền quản trị | Truy cập hoặc thay đổi dữ liệu trái phép | Rất cao | Vai trò khác nhau, URL trực tiếp, phiên hết hạn |
| Giỏ hàng | Tính tổng tiền sai ở điều kiện biên | Cao | Số lượng, giảm giá, phí giao hàng, làm tròn |
| Tìm kiếm | Kết quả khó hiểu hoặc không đầy đủ | Trung bình | Từ khóa, ký tự đặc biệt, bộ lọc, dữ liệu rỗng |
| Nội dung trợ giúp | Lỗi hiển thị ít ảnh hưởng | Thấp | Điều hướng, liên kết và nội dung đại diện |

Ưu tiên trong bảng chỉ là ví dụ. Cần điều chỉnh theo phạm vi thay đổi, lịch sử lỗi, dữ liệu và mức độ ảnh hưởng của sản phẩm cụ thể.

## 7. Thiết lập điều kiện trước phiên

Một phiên khám phá khó tạo kết quả đáng tin cậy nếu build, môi trường hoặc dữ liệu không rõ ràng.

### Build và môi trường

Ghi nhận phiên bản ứng dụng, commit hoặc build identifier, môi trường, cấu hình, trình duyệt/thiết bị và các feature flag liên quan. Nếu môi trường không ổn định hoặc khác đáng kể so với môi trường mục tiêu, cần ghi rõ giới hạn.

### Tài khoản và vai trò

Chuẩn bị tài khoản có quyền phù hợp với mục tiêu. Nếu kiểm tra phân quyền, cần có các vai trò đối chiếu như người được phép, người không được phép và người có quyền hạn khác. Tránh dùng tài khoản cá nhân hoặc tài khoản production không được phê duyệt.

### Dữ liệu kiểm thử

Chuẩn bị dữ liệu đại diện và các trường hợp biên cần thiết. Ghi cách tạo, trạng thái ban đầu và cách dọn dẹp. Với dữ liệu nhạy cảm, dùng dữ liệu tổng hợp hoặc đã được xử lý theo chính sách. Tránh thay đổi dữ liệu dùng chung của người khác trong phiên.

### Công cụ và quan sát

Chuẩn bị công cụ ghi chú, chụp ảnh, xem log, kiểm tra request/response hoặc theo dõi trạng thái khi được phép. Đảm bảo người kiểm thử biết cách lấy mã giao dịch, timestamp và thông tin cần thiết để tái hiện lỗi.

### Điều kiện an toàn

Không thực hiện thao tác có thể gây thanh toán thật, gửi thông báo thật, xóa dữ liệu hoặc làm gián đoạn dịch vụ ngoài phạm vi được phép. Nếu cần thử tình huống rủi ro, sử dụng sandbox, dữ liệu thử hoặc quy trình đã được phê duyệt. Dừng khi phát hiện tác động ngoài dự kiến.

## 8. Timebox và cấu trúc phiên

Timebox là khoảng thời gian được dành cho một phiên. Thời lượng phụ thuộc độ phức tạp, mục tiêu và mức độ chuẩn bị. Một phiên ngắn có thể kéo dài 30–45 phút; phiên chuyên sâu có thể dài hơn nếu nhiệm vụ cần nhiều trạng thái hoặc phụ thuộc. Không có một thời lượng bắt buộc cho mọi dự án.

Một cấu trúc tham khảo cho phiên 60 phút:

| Khoảng thời gian | Hoạt động |
|---|---|
| 0–5 phút | Xác nhận charter, build, môi trường, dữ liệu và giới hạn |
| 5–10 phút | Khám phá ban đầu, xác nhận luồng và các trạng thái có sẵn |
| 10–45 phút | Thiết kế và thực hiện thử nghiệm, theo đuổi nhánh có giá trị |
| 45–55 phút | Tái hiện phát hiện, thu thập log/ảnh và kiểm tra tác động |
| 55–60 phút | Tóm tắt kết quả, câu hỏi còn mở và phiên tiếp theo |

Đây chỉ là gợi ý. Nếu phát hiện lỗi nghiêm trọng, có thể dừng khám phá để xác minh và báo cáo. Nếu môi trường gặp sự cố, thời gian xử lý môi trường không nên bị nhầm là thời gian khám phá sản phẩm.

### Điều kiện kết thúc phiên

Phiên có thể kết thúc khi:

- Timebox đã hết và kết quả đã được tóm tắt.
- Mục tiêu đã được khám phá đủ để trả lời câu hỏi chính.
- Phát hiện quan trọng cần chuyển sang quy trình xác minh hoặc điều tra riêng.
- Môi trường hoặc phụ thuộc không còn cho phép kiểm tra đáng tin cậy.
- Có rủi ro an toàn hoặc tác động ngoài dự kiến cần dừng ngay.
- Cần kỹ năng, quyền hoặc người tham gia khác để tiếp tục.

Kết thúc phiên không có nghĩa toàn bộ chức năng đã được kiểm thử. Báo cáo cần nêu phần đã khám phá, phần chưa khám phá và lý do dừng.

## 9. Chọn kỹ thuật và heuristic cho phiên khám phá

Charter đặt hướng đi; heuristic giúp người kiểm thử tạo ra ý tưởng thử nghiệm. Heuristic là gợi ý tìm hiểu, không phải quy tắc chứng minh sản phẩm đúng.

### Phân vùng tương đương và giá trị biên

Chọn dữ liệu đại diện cho các nhóm hành vi khác nhau, sau đó thử giá trị ở biên. Ví dụ, với số lượng sản phẩm, thử giá trị nhỏ nhất, bằng không, số âm, giá trị lớn, số thập phân nếu không hợp lệ và giới hạn tối đa.

### Thay đổi trạng thái và thứ tự thao tác

Thử các chuỗi hành động khác nhau: tạo rồi hủy, lưu rồi sửa, tải lại giữa chừng, quay lại bước trước, mở nhiều tab hoặc gửi yêu cầu đồng thời. Mục tiêu là tìm trạng thái không nhất quán hoặc chuyển trạng thái không hợp lệ.

### Dữ liệu bất thường và lỗi phụ thuộc

Thử dữ liệu thiếu, ký tự đặc biệt, dữ liệu dài, định dạng sai, thời gian khác múi giờ, mạng chập chờn, timeout hoặc phản hồi không theo dự kiến. Chỉ thực hiện mô phỏng lỗi trong môi trường được phép.

### Heuristic CRUD và quyền

Với đối tượng dữ liệu, khám phá các thao tác tạo, đọc, cập nhật và xóa theo từng vai trò. Kiểm tra cả đường giao diện và API khi phạm vi cho phép, đặc biệt các thao tác trực tiếp hoặc thay đổi định danh.

### Khám phá theo trải nghiệm người dùng

Quan sát liệu người dùng có hiểu nhãn, trạng thái, thông báo và bước tiếp theo hay không. Ghi nhận nơi họ do dự, thao tác sai, quay lại hoặc cần trợ giúp. Không hướng dẫn quá nhiều vì điều đó có thể che giấu vấn đề về khả năng sử dụng.

### Khám phá dựa trên lỗi lịch sử

Xem xét các lỗi trước đây, thay đổi gần đây và thành phần có nhiều phụ thuộc. Thử các tình huống từng gây lỗi và biến thể gần đó. Lỗi cũ có thể chỉ ra một nhóm rủi ro rộng hơn, nhưng cần tránh lặp lại máy móc mà không có câu hỏi mới.

## 10. Ghi nhận hoạt động và kết quả trong phiên

Ghi chú cần đủ để người khác hiểu mục tiêu, đường đi, điều kiện và phát hiện mà không biến phiên thành việc ghi chép từng thao tác không cần thiết.

Thông tin hữu ích gồm:

- Mã phiên, người thực hiện, thời điểm và thời lượng.
- Charter, build, môi trường, thiết bị và tài khoản/role đã dùng.
- Khu vực, dữ liệu và trạng thái được khám phá.
- Ý tưởng thử nghiệm hoặc heuristic đã sử dụng.
- Quan sát đáng chú ý, kết quả khác kỳ vọng và câu hỏi mới.
- Lỗi nghi ngờ, mức độ tác động, bước tái hiện và bằng chứng.
- Giới hạn, phụ thuộc hoặc điều kiện khiến kết quả chưa chắc chắn.
- Phần chưa kiểm tra và đề xuất phiên tiếp theo.

### Phân biệt phát hiện lỗi với câu hỏi chưa được giải đáp

Không phải mọi điều bất thường đều là lỗi. Có thể phân loại:

- **Defect candidate:** hành vi có bằng chứng khác yêu cầu, hợp đồng hoặc kết quả mong đợi đã được xác nhận.
- **Question:** chưa rõ hành vi đúng là gì hoặc yêu cầu còn mơ hồ.
- **Observation:** điều đáng chú ý nhưng chưa chứng minh là lỗi, ví dụ thao tác khó hiểu hoặc phản hồi chậm hơn cảm nhận.
- **Risk:** tình huống có thể gây hậu quả nhưng chưa tái hiện được.
- **Follow-up:** cần thêm quyền, dữ liệu, môi trường hoặc chuyên gia để kiểm tra tiếp.

Phân loại trung thực giúp tránh tạo lỗi sai và cũng tránh bỏ qua vấn đề chỉ vì chưa có đặc tả đầy đủ.

### Ghi lại để có thể tái hiện

Với một phát hiện, lưu tối thiểu:

1. Build và môi trường.
2. Trạng thái ban đầu và dữ liệu liên quan.
3. Các bước quan trọng để tái hiện.
4. Kết quả thực tế và kết quả mong đợi hoặc câu hỏi còn mở.
5. Tần suất tái hiện và điều kiện ảnh hưởng.
6. Ảnh, video, request/response, log hoặc ID giao dịch khi phù hợp.
7. Tác động đối với người dùng hoặc nghiệp vụ.

Không đưa mật khẩu, token, dữ liệu cá nhân hoặc bí mật vào báo cáo. Dùng dữ liệu đã che hoặc mã tham chiếu an toàn theo quy định.

## 11. Debrief — tổng kết sau phiên

Debrief là cuộc trao đổi ngắn sau phiên giữa người kiểm thử và những người liên quan. Mục tiêu là chia sẻ điều đã học, xem lại phát hiện và quyết định bước tiếp theo.

Một buổi debrief có thể trả lời:

- Mục tiêu của phiên đã được khám phá đến đâu?
- Những hành vi hoặc trạng thái nào đã được kiểm tra?
- Có lỗi, câu hỏi, quan sát hoặc rủi ro nào đáng chú ý?
- Phát hiện nào cần xác minh, báo lỗi hoặc chuyển cấp?
- Có phần nào chưa kiểm tra do thời gian, môi trường hoặc dữ liệu?
- Cần phiên tiếp theo, test hồi quy, làm rõ yêu cầu hay thay đổi thiết kế nào?

Không nên chỉ báo số lượng lỗi. Một phiên không phát hiện defect vẫn có thể có giá trị nếu làm rõ được hành vi, giảm bất định hoặc xác nhận một giả định quan trọng. Ngược lại, phát hiện nhiều lỗi nhỏ không nhất thiết có giá trị hơn một phát hiện rủi ro nghiêm trọng.

### Kết quả phiên và mức độ bao phủ

Có thể dùng các trạng thái tóm tắt:

- Hoàn thành mục tiêu trong phạm vi và thời lượng đã định.
- Hoàn thành một phần, còn câu hỏi hoặc nhánh rủi ro chưa được khám phá.
- Bị chặn do môi trường, quyền, dữ liệu hoặc phụ thuộc.
- Dừng sớm do phát hiện nghiêm trọng hoặc rủi ro an toàn.

Ghi rõ kết quả này không phải tỷ lệ bao phủ toàn bộ chức năng. Nó mô tả phạm vi thực tế của một phiên khám phá cụ thể.

## 12. Ví dụ xuyên suốt: khám phá luồng thanh toán

Giả sử nhóm vừa thay đổi quy trình thanh toán của cửa hàng trực tuyến. Rủi ro là người mua có thể gửi lại yêu cầu sau timeout, không biết giao dịch đã thành công hay chưa hoặc bị tạo đơn trùng.

### Charter minh họa

| Trường | Nội dung |
|---|---|
| Tên phiên | Khám phá trạng thái thanh toán khi gián đoạn |
| Mission | Khám phá cách checkout phản ứng khi phản hồi thanh toán chậm, mất kết nối hoặc được gửi lại |
| Mục tiêu học hỏi | Xác định trạng thái đơn và giao dịch có nhất quán không; người mua có hiểu bước tiếp theo không |
| Phạm vi trong | Tạo yêu cầu thanh toán, timeout, tải lại trang, retry, webhook đến trễ/lặp và hiển thị trạng thái |
| Phạm vi ngoài | Kiểm thử tải lớn, đánh giá bảo mật chuyên sâu và các phương thức thanh toán chưa thay đổi |
| Rủi ro ưu tiên | Ghi nhận tiền hoặc tạo đơn trùng; đơn ở trạng thái không rõ; thông báo gây hiểu nhầm |
| Điều kiện | Staging, sandbox thanh toán, tài khoản thử nghiệm, dữ liệu đơn có thể dọn dẹp |
| Timebox | 60 phút, gồm 10 phút tổng kết |
| Bằng chứng | Order ID, payment reference, timestamp, log/trace, ảnh trạng thái và bước tái hiện |
| Điều kiện dừng | Phát sinh giao dịch thật, dữ liệu dùng chung bị ảnh hưởng hoặc sandbox không còn đáng tin cậy |

### Hướng khám phá có thể phát triển trong phiên

1. Tạo đơn và bắt đầu thanh toán, quan sát trạng thái trước và sau khi gửi yêu cầu.
2. Mô phỏng phản hồi chậm, kiểm tra nội dung thông báo và hành động người mua có thể thực hiện.
3. Tải lại trang hoặc mở lại đơn trong tab khác, xem trạng thái có nhất quán không.
4. Gửi lại yêu cầu trong điều kiện được phép, xác minh có tạo giao dịch hoặc đơn trùng không.
5. Cho webhook đến trễ hoặc lặp trong sandbox, kiểm tra trạng thái cuối và thông báo.
6. Nếu phát hiện trạng thái không nhất quán, theo dõi mã giao dịch và trace để xác định bước cần kiểm tra sâu hơn.

Các bước trên là gợi ý, không phải trình tự bắt buộc. Nếu ở bước đầu người kiểm thử phát hiện đơn được đánh dấu đã thanh toán dù sandbox trả thất bại, họ có thể tập trung khám phá trạng thái và luồng cập nhật trước khi đi tiếp các nhánh khác.

### Debrief minh họa

Giả sử phiên phát hiện trang checkout hiển thị “thử lại” sau timeout nhưng yêu cầu trước đó có thể đã được xử lý. Người mua có thể gửi lại và tạo một yêu cầu thanh toán thứ hai. Nhóm cần xác minh liệu đây là lỗi giao dịch, thiếu idempotency hay thông báo chưa rõ. Báo cáo ghi lại hai payment reference, cùng order ID, timestamp và trace. Hành động tiếp theo có thể là test tích hợp gửi lặp, làm rõ quy tắc trạng thái và bổ sung kiểm tra hồi quy.

## 13. Mẫu session charter có thể tái sử dụng

Có thể sao chép mẫu sau cho từng phiên:

```text
SESSION ID:
TÊN PHIÊN:
NGƯỜI THỰC HIỆN:
THỜI ĐIỂM / TIMEBOX:

MISSION:
MỤC TIÊU HỌC HỎI / CÂU HỎI:
RỦI RO ƯU TIÊN:

PHẠM VI TRONG:
-

PHẠM VI NGOÀI:
-

BUILD / MÔI TRƯỜNG / THIẾT BỊ:
TÀI KHOẢN / VAI TRÒ:
DỮ LIỆU / TRẠNG THÁI BAN ĐẦU:
PHỤ THUỘC / CÔNG CỤ:

BẰNG CHỨNG CẦN GHI:
ĐIỀU KIỆN DỪNG:

KẾT QUẢ:
PHÁT HIỆN / CÂU HỎI / RỦI RO:
PHẦN CHƯA KHÁM PHÁ:
HÀNH ĐỘNG TIẾP THEO / NGƯỜI PHỤ TRÁCH:
```

Mẫu có thể rút gọn hoặc mở rộng theo rủi ro. Không cần điền mọi trường nếu không liên quan, nhưng build, môi trường, nhiệm vụ, phạm vi và kết quả cần đủ rõ để hiểu giá trị của phiên.

## 14. Những sai lầm thường gặp

**Chỉ ghi tên chức năng làm mục tiêu.** “Test đăng nhập” không chỉ ra điều cần học. Hãy nêu hành vi, rủi ro hoặc câu hỏi, chẳng hạn xử lý tài khoản bị khóa, liên kết hết hạn và phiên đăng nhập đồng thời.

**Phạm vi quá rộng.** Một phiên cố khám phá toàn bộ ứng dụng thường chỉ chạm qua nhiều màn hình mà không đi sâu. Chia thành các nhiệm vụ nhỏ theo rủi ro và luồng nghiệp vụ.

**Phạm vi quá cứng.** Nếu charter yêu cầu chính xác từng bước, người kiểm thử có thể bỏ qua phát hiện mới. Hãy mô tả mission và ranh giới, để đường đi được điều chỉnh theo quan sát.

**Không ghi phần ngoài phạm vi.** Người đọc có thể hiểu nhầm khu vực chưa kiểm tra đã được bao phủ. Nêu rõ phần loại trừ và tạo follow-up nếu rủi ro còn đáng kể.

**Không chuẩn bị môi trường và dữ liệu.** Thời gian phiên bị tiêu tốn cho việc tìm tài khoản, sửa dữ liệu hoặc chờ hệ thống. Chuẩn bị trước và ghi lại điều kiện để kết quả có thể tái lập.

**Không dùng timebox.** Một nhánh có thể chiếm toàn bộ thời gian. Dùng mốc xem xét để quyết định tiếp tục, ghi follow-up hoặc chuyển sang rủi ro khác.

**Ghi chú quá ít hoặc quá nhiều.** Ghi quá ít khiến không tái hiện được; ghi từng thao tác không có ý nghĩa làm giảm thời gian khám phá. Ghi mục tiêu, dữ liệu, trạng thái, quan sát, phát hiện và bằng chứng quan trọng.

**Coi mọi điều bất thường là defect.** Yêu cầu có thể chưa rõ hoặc hành vi có thể được thiết kế có chủ đích. Phân loại câu hỏi, quan sát và lỗi nghi ngờ; xác nhận oracle trước khi kết luận.

**Kết thúc mà không debrief.** Phát hiện và kiến thức có thể không được chuyển cho nhóm. Dành thời gian tổng kết, gắn người phụ trách và xác định phiên tiếp theo.

**Báo cáo không phát hiện lỗi như bằng chứng đầy đủ.** Một phiên không tìm thấy lỗi chỉ phản ánh phạm vi, dữ liệu, thời lượng và kỹ thuật đã dùng. Nêu rõ giới hạn và mức độ bất định.

## 15. Checklist lập và thực hiện phiên khám phá

Trước phiên:

- [ ] Mission nêu rõ khu vực, hành vi và câu hỏi cần khám phá.
- [ ] Mục tiêu gắn với rủi ro hoặc điều cần học, không chỉ là tên chức năng.
- [ ] Phạm vi trong và ngoài được xác định.
- [ ] Build, môi trường, thiết bị, tài khoản và dữ liệu đã sẵn sàng.
- [ ] Timebox, điều kiện dừng và bằng chứng cần lưu đã rõ.
- [ ] Các giới hạn an toàn và quyền thực hiện đã được xác nhận.

Trong phiên:

- [ ] Người kiểm thử vừa học, vừa thiết kế và thực hiện thử nghiệm dựa trên quan sát.
- [ ] Các nhánh mới được theo đuổi khi liên quan và có giá trị; nhánh ngoài mục tiêu được ghi follow-up.
- [ ] Dữ liệu, trạng thái, build và môi trường được ghi nhận khi cần.
- [ ] Phát hiện được phân biệt với câu hỏi hoặc quan sát chưa xác minh.
- [ ] Bằng chứng đủ để tái hiện và đánh giá tác động.
- [ ] Phiên dừng khi hết timebox, môi trường không đáng tin cậy hoặc có rủi ro ngoài dự kiến.

Sau phiên:

- [ ] Kết quả được debrief và so sánh với mission.
- [ ] Phần đã khám phá, chưa khám phá và giới hạn được báo cáo.
- [ ] Phát hiện quan trọng được xác minh hoặc chuyển đúng quy trình.
- [ ] Câu hỏi mở có người phụ trách và hành động tiếp theo.
- [ ] Charter hoặc heuristic được cập nhật nếu có hiểu biết mới hữu ích.

## 16. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Charter chỉ ghi “kiểm tra trang đăng nhập trong 60 phút”. Mục tiêu còn mơ hồ. Có thể viết lại thành “khám phá cách đăng nhập xử lý tài khoản bị khóa, mật khẩu hết hạn và nhiều phiên đồng thời để tìm trạng thái không nhất quán hoặc thông báo gây hiểu nhầm”.

**Tình huống 2:** Trong khi khám phá giỏ hàng, người kiểm thử phát hiện lỗi tính thuế và muốn chuyển sang kiểm thử tải toàn bộ hệ thống. Đây có thể là mục tiêu khác. Nên ghi phát hiện, xác định liệu nó liên quan trực tiếp đến rủi ro hiện tại hay không, rồi tạo phiên riêng nếu cần môi trường và kỹ thuật khác.

**Tình huống 3:** Phiên không phát hiện defect nhưng làm rõ rằng yêu cầu chưa xác định cách xử lý mã giảm giá khi đơn bị hủy. Kết quả vẫn có giá trị: một câu hỏi quan trọng đã được nhận diện và cần chuyển đến chủ sở hữu nghiệp vụ để làm rõ.

**Tình huống 4:** Người kiểm thử không thể tiếp tục vì môi trường staging mất kết nối với sandbox. Phiên nên được ghi nhận là bị chặn hoặc hoàn thành một phần, kèm điều kiện, thời gian mất và phần chưa kiểm tra. Không nên báo cáo toàn bộ mission đã đạt.

**Tình huống 5:** Một thao tác có thể gửi thông báo thật cho khách hàng. Nếu charter không cho phép tác động đó, người kiểm thử phải dùng dữ liệu hoặc dịch vụ mô phỏng, hoặc dừng nhánh đó và xin điều kiện thử nghiệm phù hợp.

Khi chuẩn bị phiên khám phá, hãy tự hỏi: **cần học điều gì, rủi ro nào đáng ưu tiên, ranh giới nào được phép khám phá và bằng chứng nào giúp người khác hiểu kết quả?** Một charter tốt trả lời được các câu hỏi này mà vẫn để người kiểm thử linh hoạt theo đuổi những phát hiện có giá trị.

## Kết luận

Mục tiêu và phạm vi là nền tảng để phiên kiểm thử khám phá có định hướng và tạo ra bằng chứng hữu ích. Session charter nên nêu mission, câu hỏi cần học, rủi ro, phạm vi trong/ngoài, điều kiện, timebox, bằng chứng và điều kiện dừng. Trong phiên, người kiểm thử liên tục học hỏi, thiết kế và thực hiện thử nghiệm dựa trên quan sát; sau phiên, debrief chuyển phát hiện và câu hỏi mở thành hành động tiếp theo. Cách tổ chức này giữ được tính linh hoạt của kiểm thử khám phá đồng thời giúp nhóm kiểm soát phạm vi và giải thích rõ điều đã, chưa được kiểm tra.
