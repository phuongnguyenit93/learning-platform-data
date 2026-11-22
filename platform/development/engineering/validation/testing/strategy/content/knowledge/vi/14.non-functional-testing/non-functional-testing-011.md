# Xác định ngưỡng và điều kiện đo riêng cho từng thuộc tính chất lượng

Một mục tiêu phi chức năng chỉ có thể được đánh giá nhất quán khi nhóm biết cần đo điều gì, đo trong điều kiện nào và ngưỡng nào thể hiện kết quả chấp nhận được. Cùng một hệ thống có thể phản hồi nhanh trong môi trường thử nghiệm nhỏ nhưng chậm khi tải cao; có thể hoạt động liên tục trong một bài kiểm thử ngắn nhưng vẫn gặp lỗi sau nhiều giờ; hoặc có thể vượt qua công cụ quét bảo mật nhưng còn điểm yếu trong logic phân quyền.

Vì vậy, không nên dùng một ngưỡng chung cho mọi thuộc tính chất lượng. Hiệu năng, độ tin cậy, bảo mật, khả năng sử dụng, khả năng tương thích và khả năng phục hồi có bản chất khác nhau. Mỗi thuộc tính cần chỉ số, phương pháp đo, điều kiện thử và tiêu chí đánh giá riêng. Các ngưỡng phải xuất phát từ nhu cầu người dùng, rủi ro, cam kết dịch vụ, đường cơ sở và khả năng vận hành.

## 1. Từ thuộc tính chất lượng đến phép đo

Thuộc tính chất lượng mô tả một khía cạnh của sản phẩm mà người dùng hoặc tổ chức quan tâm. Một thuộc tính như “hiệu năng” vẫn còn quá rộng để kiểm thử. Cần chuyển nó thành một tình huống chất lượng có thể quan sát.

Một tình huống chất lượng thường nêu:

- **Nguồn kích hoạt:** người dùng, hệ thống khác, tác vụ nền hoặc một sự kiện lỗi.
- **Kích thích hoặc hành động:** thao tác hay điều kiện gây ra hành vi cần đánh giá.
- **Môi trường:** tải, nền tảng, cấu hình, dữ liệu và trạng thái hệ thống.
- **Thành phần liên quan:** API, giao diện, dịch vụ, cơ sở dữ liệu hoặc quy trình.
- **Phản hồi mong đợi:** hành vi hoặc kết quả cần đạt.
- **Chỉ số và ngưỡng:** cách đo phản hồi và mức nào được xem là đạt.

Ví dụ, thay vì ghi “trang tìm kiếm phải nhanh”, có thể mô tả: “Khi có 300 phiên người dùng đồng thời gửi truy vấn tìm kiếm với bộ dữ liệu đại diện trên cấu hình production tương đương, ít nhất 95% yêu cầu hoàn tất trong 700 ms, tỷ lệ lỗi không vượt quá 0,5% trong bài đo kéo dài 20 phút sau giai đoạn làm nóng.”

Phát biểu này giúp nhóm xác định tải, dữ liệu, môi trường, điểm đo, phân vị, tỷ lệ lỗi và thời lượng. Các giá trị 300 phiên, 700 ms và 0,5% chỉ là ví dụ; dự án thực tế phải xác lập chúng từ yêu cầu và dữ liệu.

## 2. Phân biệt chỉ số, ngưỡng, điều kiện đo và tiêu chí đạt

Các thành phần sau cần được định nghĩa riêng để tránh hiểu khác nhau giữa người thiết kế, người chạy kiểm thử và người đọc báo cáo.

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Thuộc tính chất lượng | Khía cạnh cần đánh giá | Hiệu năng, bảo mật, độ tin cậy, khả năng sử dụng |
| Chỉ số (metric) | Đại lượng được quan sát hoặc tính toán | p95 thời gian phản hồi, tỷ lệ lỗi, tỷ lệ hoàn thành tác vụ |
| Định nghĩa chỉ số | Công thức, đơn vị, mẫu số và quy tắc thu thập | Số yêu cầu lỗi chia cho tổng yêu cầu hợp lệ trong cửa sổ đo |
| Điều kiện đo | Bối cảnh tạo ra dữ liệu | 300 phiên đồng thời, 20 phút, dữ liệu 1 triệu bản ghi |
| Đường cơ sở (baseline) | Kết quả hiện tại hoặc mốc tham chiếu | p95 hiện tại là 1,1 giây trong cùng bài đo |
| Ngưỡng (threshold) | Giới hạn hoặc mức mục tiêu dùng để đánh giá | p95 không vượt 700 ms |
| Tiêu chí đạt | Quy tắc kết luận dựa trên chỉ số và điều kiện | p95 đạt ngưỡng, tỷ lệ lỗi không quá 0,5%, không có lỗi dữ liệu |

Chỉ số không tự nói lên chất lượng. Ví dụ, “thời gian phản hồi 500 ms” thiếu thông tin về điểm bắt đầu và kết thúc, loại yêu cầu, tải, phân vị và môi trường. Tương tự, “tỷ lệ sẵn sàng 99,9%” chưa rõ khoảng thời gian, cách xác định dịch vụ sẵn sàng và cách tính thời gian bảo trì.

Ngưỡng cũng không phải lúc nào chỉ là một con số. Có thể là giới hạn trên, giới hạn dưới, khoảng giá trị, điều kiện kết hợp, số lần vi phạm cho phép hoặc quy tắc đánh giá định tính có tiêu chí rõ.

## 3. Quy trình xác định ngưỡng và điều kiện đo

Có thể dùng quy trình sau cho từng thuộc tính chất lượng:

1. **Xác định nhu cầu và rủi ro:** người dùng cần điều gì, hậu quả nào xảy ra nếu thuộc tính không đạt và luồng nào quan trọng nhất?
2. **Chọn tình huống đại diện:** mô tả tác nhân, hành động, môi trường, thành phần và phản hồi cần quan sát.
3. **Chọn chỉ số có ý nghĩa:** ưu tiên đại lượng phản ánh trực tiếp trải nghiệm hoặc rủi ro. Không chọn chỉ số chỉ vì công cụ dễ thu thập.
4. **Định nghĩa cách đo:** thống nhất điểm đo, đơn vị, công thức, mẫu số, nguồn dữ liệu, cách xử lý ngoại lệ và cửa sổ thời gian.
5. **Thu thập đường cơ sở:** đo hệ thống hiện tại trong điều kiện đã mô tả. Nếu chưa có dữ liệu, thực hiện giai đoạn khảo sát và ghi rõ độ bất định.
6. **Đặt ngưỡng:** kết hợp nhu cầu, cam kết, dữ liệu thực tế, khả năng kỹ thuật và mức rủi ro chấp nhận được.
7. **Xác định cách xác minh:** chọn loại kiểm thử, môi trường, dữ liệu, công cụ, số lần chạy và tiêu chí kết luận.
8. **Theo dõi và hiệu chỉnh:** xem xét xu hướng, thay đổi tải hoặc kiến trúc, và cập nhật ngưỡng theo quy trình có kiểm soát.

Ngưỡng nên được thống nhất trước khi chạy bài kiểm thử dùng để ra quyết định. Nếu nhóm thay đổi ngưỡng sau khi thấy kết quả, cần ghi lý do, bằng chứng và người phê duyệt để tránh điều chỉnh chỉ nhằm làm cho kết quả trông như đạt.

## 4. Xác định ngưỡng cho hiệu năng

Hiệu năng thường được đánh giá qua thời gian phản hồi, thông lượng và mức sử dụng tài nguyên. Mỗi chỉ số trả lời một câu hỏi khác nhau.

### Thời gian phản hồi và phân vị

Thời gian phản hồi là khoảng thời gian từ một mốc bắt đầu đến khi nhận được kết quả đã định nghĩa. Với API, nhóm có thể đo từ lúc client gửi yêu cầu đến khi nhận đủ phản hồi. Với giao diện, có thể đo thời gian hiển thị nội dung có ý nghĩa hoặc hoàn tất một tác vụ.

Không nên chỉ nhìn vào giá trị trung bình. Một số yêu cầu rất chậm có thể bị che khuất bởi nhiều yêu cầu nhanh. Phân vị giúp hiểu phần đuôi của phân bố:

- **p50:** một nửa số quan sát có thời gian không vượt quá giá trị này; thường gần với trải nghiệm điển hình.
- **p90 hoặc p95:** cho biết nhóm yêu cầu chậm hơn so với phần lớn quan sát.
- **p99:** giúp quan sát phần đuôi rất chậm, nhưng cần đủ mẫu để ước lượng có ý nghĩa.

Ví dụ, p95 = 700 ms nghĩa là khoảng 95% quan sát trong mẫu có thời gian phản hồi không vượt quá 700 ms. Nó không có nghĩa mọi yêu cầu đều hoàn tất trong 700 ms.

### Thông lượng và tỷ lệ lỗi

Thông lượng có thể được biểu diễn bằng số yêu cầu mỗi giây, giao dịch mỗi phút hoặc tác vụ hoàn tất trong một khoảng thời gian. Cần đo ở mức tải đã xác định và kiểm tra rằng kết quả trả về vẫn đúng.

Tỷ lệ lỗi cần định nghĩa rõ mẫu số. Có thể tính:

`Tỷ lệ lỗi = số yêu cầu lỗi / tổng số yêu cầu hợp lệ × 100%`

Nhóm cần thống nhất mã trạng thái hoặc kết quả nào được tính là lỗi, có tính timeout từ client hay không, và cách xử lý yêu cầu bị hủy. Nếu chỉ báo cáo thông lượng mà bỏ qua lỗi, hệ thống có thể trông như xử lý được nhiều yêu cầu trong khi thực tế từ chối hoặc làm hỏng một phần lớn giao dịch.

### Tài nguyên và điều kiện tải

Các chỉ số tài nguyên gồm CPU, bộ nhớ, I/O đĩa, mạng, số kết nối, độ sâu hàng đợi và dung lượng cache. Chúng giúp giải thích điểm nghẽn và xác định hệ thống còn dư địa hay không.

Điều kiện đo hiệu năng nên ghi rõ:

- Số người dùng hoặc phiên đồng thời và mô hình hành vi.
- Tốc độ gửi yêu cầu, phân bố loại yêu cầu và thời gian giữ tải.
- Kích thước, phân bố và độ mới của dữ liệu.
- Cấu hình máy, container, autoscaling, database và cache.
- Trạng thái cache, giai đoạn làm nóng và các tác vụ nền đang chạy.
- Số lần chạy, thời gian đo và cách tổng hợp kết quả.

### Các kiểu bài đo và ngưỡng tương ứng

| Kiểu kiểm thử | Câu hỏi | Điều kiện cần kiểm soát |
| --- | --- | --- |
| Load testing | Hệ thống hoạt động thế nào ở tải dự kiến? | Mô hình tải đại diện, thời lượng ổn định, dữ liệu và cấu hình mục tiêu |
| Stress testing | Giới hạn hoặc điểm suy giảm nằm ở đâu? | Tăng tải có kiểm soát, tiêu chí dừng và quan sát phục hồi |
| Spike testing | Hệ thống phản ứng ra sao khi tải tăng đột ngột? | Mức tăng, tốc độ tăng/giảm và thời gian giữa các đợt |
| Soak testing | Có suy giảm sau thời gian dài không? | Tải duy trì, thời lượng đủ dài, theo dõi rò rỉ và cạn tài nguyên |
| Benchmark | Thay đổi thành phần có cải thiện hiệu năng không? | Đầu vào, phần cứng, phiên bản, warm-up và cách lặp giống nhau |

Ngưỡng hiệu năng cần gắn với mục tiêu người dùng và tải dự kiến. Một API quản trị ít sử dụng có thể có ngưỡng khác API tìm kiếm hoặc thanh toán. Không nên áp một giới hạn độ trễ giống nhau cho mọi endpoint.

## 5. Xác định ngưỡng cho độ tin cậy và tính sẵn sàng

Độ tin cậy đánh giá khả năng thực hiện chức năng đúng và duy trì hoặc phục hồi dịch vụ trong điều kiện xác định. Các chỉ số có thể gồm tỷ lệ yêu cầu thành công, tỷ lệ lỗi, số sự cố, thời gian gián đoạn, thời gian phục hồi và mức mất dữ liệu.

### Tỷ lệ sẵn sàng

Một cách tính phổ biến:

`Tỷ lệ sẵn sàng = thời gian dịch vụ sẵn sàng / thời gian dịch vụ cam kết × 100%`

Nhóm phải định nghĩa “sẵn sàng” theo trải nghiệm hoặc giao dịch quan trọng. Một máy chủ trả lời health check nhưng không xử lý được thanh toán có thể không được xem là sẵn sàng đối với dịch vụ thanh toán.

Khoảng thời gian cam kết cần rõ: theo tháng, quý hay cửa sổ trượt. Cần nêu cách xử lý bảo trì theo kế hoạch, sự cố do phụ thuộc và khoảng thời gian gián đoạn ngắn. Cách tính phải nhất quán với cam kết dịch vụ.

### SLI và SLO

**SLI (Service Level Indicator)** là chỉ số đo mức dịch vụ thực tế, ví dụ tỷ lệ yêu cầu thành công hoặc tỷ lệ yêu cầu có độ trễ dưới ngưỡng. **SLO (Service Level Objective)** là mục tiêu đặt cho SLI trong một cửa sổ thời gian.

Ví dụ: SLI là tỷ lệ yêu cầu tra cứu đơn hàng thành công; SLO là ít nhất 99,9% yêu cầu hợp lệ thành công trong cửa sổ 30 ngày. SLO phải nêu rõ tập yêu cầu được tính, loại trừ nào được phép và nguồn dữ liệu đo.

### Error budget

Error budget là phần lỗi hoặc gián đoạn có thể xảy ra trong phạm vi SLO mà không làm mục tiêu bị vi phạm. Nếu SLO sẵn sàng là 99,9% trong một cửa sổ thời gian, phần còn lại là ngân sách lỗi theo định nghĩa của cửa sổ đó. Nhóm có thể dùng xu hướng tiêu thụ error budget để điều chỉnh ưu tiên độ ổn định so với tốc độ phát hành.

Error budget là công cụ quản lý, không phải mục tiêu để cố tình sử dụng hết. Cần xác định cách đo, cửa sổ, loại sự cố và chính sách hành động khi ngân sách lỗi bị tiêu thụ nhanh.

### Điều kiện đo độ tin cậy

Cần xác định:

- Tập giao dịch hoặc yêu cầu được tính là quan trọng.
- Cách phân loại thành công, lỗi nghiệp vụ, lỗi hạ tầng và lỗi phía client.
- Cửa sổ thời gian, vùng triển khai và nhóm người dùng.
- Cách phát hiện sự cố và thời điểm bắt đầu/kết thúc gián đoạn.
- Cách tính ảnh hưởng của phụ thuộc bên ngoài.
- Số lần lặp, thời gian quan sát và trạng thái dữ liệu ban đầu.

Không nên chỉ dùng số lần máy chủ khởi động lại hoặc tỷ lệ health check để kết luận độ tin cậy. Cần xem xét hành vi nghiệp vụ và tính toàn vẹn dữ liệu.

## 6. Xác định ngưỡng cho khả năng phục hồi

Khả năng phục hồi (recoverability) mô tả khả năng khôi phục dữ liệu, chức năng hoặc dịch vụ sau lỗi. Các mục tiêu thường gặp:

- **RTO (Recovery Time Objective):** khoảng thời gian tối đa mục tiêu để khôi phục dịch vụ sau sự cố.
- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa theo thời gian mà tổ chức có thể chấp nhận.
- **Thời gian khôi phục thực tế:** thời gian đo được trong diễn tập hoặc kiểm thử.
- **Mức toàn vẹn dữ liệu sau phục hồi:** dữ liệu có đầy đủ, nhất quán và có thể đối soát không.

Ví dụ, hệ thống đơn hàng có RTO mục tiêu 60 phút và RPO mục tiêu 5 phút. Trong bài diễn tập, nhóm mô phỏng mất vùng dữ liệu, khôi phục từ backup và log giao dịch, sau đó đo thời gian dịch vụ có thể xử lý giao dịch hợp lệ và kiểm tra phần dữ liệu bị mất hoặc cần đối soát.

Điều kiện đo cần ghi rõ loại sự cố, phạm vi ảnh hưởng, trạng thái backup, kích thước dữ liệu, hạ tầng phục hồi, mức tải sau khôi phục và cách xác minh tính toàn vẹn. Một lần restore thành công với dữ liệu nhỏ không chứng minh RTO/RPO đạt trong tình huống production lớn.

Tiêu chí đạt nên kết hợp thời gian và tính đúng đắn. Dịch vụ khởi động lại nhanh nhưng mất giao dịch đã xác nhận vẫn có thể không đạt mục tiêu phục hồi.

## 7. Xác định ngưỡng cho bảo mật

Bảo mật không thể được biểu diễn bằng một chỉ số duy nhất. Cần đánh giá theo tài sản, mối đe dọa, ranh giới tin cậy và yêu cầu bảo vệ.

Các bằng chứng có thể gồm:

- Số phát hiện theo mức độ nghiêm trọng và khả năng khai thác.
- Tỷ lệ lỗ hổng đã được xử lý trong thời hạn quy định.
- Kết quả kiểm tra xác thực, phân quyền và kiểm soát truy cập.
- Khả năng bảo vệ dữ liệu khi truyền và khi lưu.
- Kết quả kiểm thử API, kiểm thử xâm nhập và rà soát cấu hình.
- Khả năng phát hiện, cảnh báo và phản ứng với hành vi bất thường.

### Đặt ngưỡng dựa trên rủi ro

Ví dụ về tiêu chí có thể dùng:

- Không còn phát hiện mức nghiêm trọng hoặc cao chưa được xử lý trong phạm vi phát hành, theo phương pháp phân loại đã thống nhất.
- Mọi endpoint xử lý dữ liệu nhạy cảm đều có kiểm thử quyền truy cập cho vai trò được phép và không được phép.
- Bí mật không xuất hiện trong mã nguồn, log hoặc artifact phát hành theo các nguồn quét và kiểm tra đã xác định.
- Các phát hiện được chấp nhận ngoại lệ có chủ sở hữu, biện pháp giảm thiểu, thời hạn và phê duyệt đúng thẩm quyền.

Đây là ví dụ về chính sách đo, không phải ngưỡng phổ quát. Mức nghiêm trọng cần xét khả năng khai thác, mức phơi lộ, giá trị tài sản, tác động và biện pháp kiểm soát. Số lượng phát hiện bằng không trong một lần quét không chứng minh hệ thống không có lỗ hổng.

### Điều kiện đo bảo mật

Phải xác định phạm vi tài sản, phiên bản, cấu hình, vai trò, loại kiểm thử, công cụ và quy tắc phân loại. Báo cáo cần nêu endpoint hoặc thành phần chưa được kiểm tra, xác thực có dùng tài khoản thử hay không, các khu vực bị loại trừ và cách xác minh phát hiện.

Không nên so sánh số lượng cảnh báo từ hai công cụ khác nhau nếu cách phát hiện và phân loại không tương đương. Một thay đổi công cụ có thể làm số phát hiện tăng hoặc giảm mà mức bảo mật thực tế không thay đổi tương ứng.

## 8. Xác định ngưỡng cho khả năng sử dụng và khả năng tiếp cận

Khả năng sử dụng (usability) tập trung vào việc người dùng có thể hoàn thành tác vụ hiệu quả, dễ hiểu và ít nhầm lẫn. Chỉ số có thể gồm:

- Tỷ lệ hoàn thành tác vụ theo tiêu chí.
- Thời gian hoàn thành tác vụ.
- Số lỗi hoặc bước sai trong quá trình thực hiện.
- Số lần cần trợ giúp hoặc phải thử lại.
- Mức độ hài lòng hoặc mức dễ dàng được người tham gia tự đánh giá.

Ví dụ, với tác vụ “tìm và tải hóa đơn”, nhóm có thể đặt mục tiêu ít nhất 90% người tham gia thuộc nhóm người dùng mục tiêu hoàn thành mà không cần trợ giúp trong vòng 2 phút. Điều kiện đo phải ghi rõ hồ sơ người tham gia, thiết bị, tác vụ, hướng dẫn, cỡ mẫu và cách xử lý trường hợp bị gián đoạn.

Không nên chỉ dựa vào điểm hài lòng trung bình. Người tham gia có thể đánh giá giao diện tích cực nhưng vẫn không hoàn thành được tác vụ quan trọng. Cần kết hợp chỉ số hành vi và phản hồi định tính.

Khả năng tiếp cận (accessibility) cần được đánh giá bằng tiêu chí phù hợp với chuẩn hoặc yêu cầu được chọn. Ví dụ, nhóm có thể kiểm tra điều hướng bàn phím, thứ tự focus, nhãn cho trình đọc màn hình, tương phản và cấu trúc nội dung. Cần ghi phiên bản chuẩn, cấp độ mục tiêu, công cụ tự động, bước kiểm tra thủ công và các ngoại lệ.

Điểm số từ công cụ tự động không bao phủ mọi vấn đề tiếp cận. Một bài kiểm tra đạt chỉ cung cấp bằng chứng cho tiêu chí và trang đã kiểm tra trong điều kiện cụ thể.

## 9. Xác định ngưỡng cho khả năng tương thích và khả năng cài đặt

Khả năng tương thích cần được đánh giá trên tập nền tảng thực sự được hỗ trợ. Có thể bao gồm trình duyệt, hệ điều hành, thiết bị, phiên bản runtime, cơ sở dữ liệu hoặc giao thức.

Điều kiện đo cần xác định:

- Danh sách nền tảng và phiên bản thuộc phạm vi hỗ trợ.
- Cấu hình thiết bị, độ phân giải, ngôn ngữ, múi giờ và quyền.
- Luồng chức năng quan trọng cần chạy trên mỗi tổ hợp.
- Các tổ hợp được chọn theo mức sử dụng và rủi ro.
- Cách ghi nhận sai khác và mức độ ảnh hưởng.

Không phải lúc nào cũng cần kiểm tra mọi tổ hợp thiết bị và trình duyệt. Có thể dùng ma trận tương thích, chọn tổ hợp đại diện theo mức sử dụng và rủi ro, đồng thời xác định rõ tổ hợp nào chưa có bằng chứng.

Khả năng cài đặt và triển khai có thể đo qua tỷ lệ triển khai thành công, thời gian cài đặt, khả năng nâng cấp, rollback và tính nhất quán cấu hình. Cần kiểm thử cả cài mới và nâng cấp từ phiên bản được hỗ trợ, trên môi trường có cấu hình tương đương.

Ví dụ, tiêu chí có thể là “tỷ lệ triển khai thành công đạt ít nhất 99% trên 100 lần triển khai thử với cấu hình chuẩn; rollback hoàn tất trong tối đa 10 phút và không làm mất dữ liệu đã xác nhận”. Phạm vi, cách tạo lần triển khai và tiêu chí xác nhận thành công phải được định nghĩa rõ.

## 10. Xác định ngưỡng cho khả năng bảo trì

Khả năng bảo trì (maintainability) là mức độ dễ hiểu, phân tích, sửa đổi và kiểm thử của hệ thống. Đây là thuộc tính khó gói vào một con số duy nhất.

Các chỉ số hỗ trợ có thể gồm:

- Thời gian trung vị để xử lý một loại thay đổi hoặc sửa lỗi đã định nghĩa.
- Tỷ lệ thay đổi gây lỗi hồi quy trong phạm vi theo dõi.
- Độ phức tạp hoặc mức phụ thuộc của các thành phần quan trọng.
- Tỷ lệ mã có kiểm thử tự động phù hợp với rủi ro.
- Thời gian pipeline phản hồi khi thay đổi.
- Số cảnh báo phân tích tĩnh hoặc nợ kỹ thuật theo quy tắc đã thống nhất.

Những chỉ số này cần được diễn giải cẩn thận. Độ phức tạp thấp không tự động chứng minh mã dễ bảo trì; độ bao phủ cao không đảm bảo kiểm thử có chất lượng; số lỗi hồi quy còn phụ thuộc cách phát hiện và phạm vi sử dụng.

Điều kiện đo nên xác định nhóm thành phần, loại thay đổi, giai đoạn theo dõi, nguồn dữ liệu và các yếu tố gây nhiễu. Có thể dùng một số nhiệm vụ bảo trì mẫu hoặc đánh giá review để bổ sung góc nhìn định tính.

## 11. Kết hợp nhiều chỉ số mà không tối ưu sai mục tiêu

Một thuộc tính chất lượng thường cần nhiều chỉ số bổ trợ. Ví dụ, tối ưu thời gian phản hồi mà không theo dõi tỷ lệ lỗi có thể khiến hệ thống trả lời nhanh bằng cách từ chối yêu cầu. Tăng tỷ lệ sẵn sàng mà không kiểm tra tính toàn vẹn dữ liệu có thể tạo ra hệ thống luôn hoạt động nhưng trả về trạng thái sai.

Có thể thiết kế bộ chỉ số theo ba nhóm:

- **Chỉ số kết quả:** phản ánh trải nghiệm hoặc mục tiêu chính, ví dụ p95, tỷ lệ hoàn thành tác vụ, tỷ lệ yêu cầu thành công.
- **Chỉ số bảo vệ:** phát hiện tác dụng phụ, ví dụ tỷ lệ lỗi, giao dịch sai, sự kiện trùng hoặc mức tiêu thụ tài nguyên.
- **Chỉ số chẩn đoán:** giúp giải thích nguyên nhân, ví dụ CPU, độ sâu queue, số lần retry, lỗi database hoặc độ trễ phụ thuộc.

Ví dụ cho API thanh toán:

| Nhóm | Chỉ số | Vai trò |
| --- | --- | --- |
| Kết quả | p95 thời gian phản hồi, tỷ lệ thanh toán hoàn tất | Đánh giá tốc độ và kết quả nghiệp vụ |
| Bảo vệ | Tỷ lệ giao dịch trùng, tỷ lệ timeout, tỷ lệ lỗi | Phát hiện tác dụng phụ và rủi ro giao dịch |
| Chẩn đoán | Thời gian phản hồi của gateway, số lần retry, độ sâu queue, CPU | Xác định nguồn gây chậm hoặc lỗi |

Không nên gộp mọi chỉ số thành một điểm chất lượng duy nhất nếu điều đó che khuất một rủi ro nghiêm trọng. Một chỉ số bảo vệ có thể là điều kiện bắt buộc dù chỉ số kết quả đạt mục tiêu.

## 12. Thiết kế điều kiện đo có thể lặp lại

Điều kiện đo ảnh hưởng trực tiếp đến kết quả. Để so sánh giữa các phiên bản, nhóm cần kiểm soát các yếu tố quan trọng.

### Môi trường và cấu hình

Ghi lại phiên bản ứng dụng, cấu hình runtime, tài nguyên, hạ tầng, mạng, database, broker, cache và các phụ thuộc. Nếu môi trường khác production, mô tả khác biệt và đánh giá ảnh hưởng đến kết luận.

### Dữ liệu

Chọn dữ liệu có kích thước, phân bố và đặc điểm gần với sử dụng dự kiến. Dữ liệu quá nhỏ có thể làm truy vấn nhanh bất thường; dữ liệu sạch hoàn toàn có thể bỏ qua các trường hợp null, trùng hoặc không hợp lệ. Không sử dụng dữ liệu cá nhân thật nếu không có cơ sở và biện pháp bảo vệ phù hợp.

### Làm nóng và trạng thái ban đầu

Với một số bài đo hiệu năng, cần giai đoạn warm-up để runtime, JIT, cache và connection pool đạt trạng thái ổn định. Với bài kiểm thử phục hồi, cần xác định trạng thái backup và dữ liệu trước khi mô phỏng sự cố. Với kiểm thử bảo mật, cần ghi vai trò và quyền của tài khoản.

### Số lần chạy và biến động

Một lần đo có thể bị ảnh hưởng bởi nhiễu. Với bài benchmark hoặc hiệu năng, nên chạy lặp trong điều kiện tương đương, báo cáo phân bố và xem xét độ biến động. Không nên loại bỏ lần chạy xấu nếu không có lý do kỹ thuật được ghi lại.

### Cửa sổ thời gian

Chỉ số theo thời gian cần có cửa sổ rõ ràng: vài phút, một giờ, một ngày hay 30 ngày. Cửa sổ quá ngắn có thể bỏ sót giờ cao điểm hoặc sự cố hiếm; cửa sổ quá dài có thể che giấu một giai đoạn suy giảm.

## 13. Ví dụ tổng hợp: đặt ngưỡng cho một dịch vụ đặt hàng

Giả sử nhóm chuẩn bị phát hành một dịch vụ đặt hàng cho cửa hàng trực tuyến. Các ngưỡng sau chỉ minh họa cách lập đặc tả, không phải giá trị mặc định cho mọi hệ thống.

| Thuộc tính | Chỉ số | Điều kiện đo | Ngưỡng minh họa |
| --- | --- | --- | --- |
| Hiệu năng | p95 thời gian phản hồi API tạo đơn | 300 phiên đồng thời, dữ liệu đại diện, 20 phút sau warm-up | Không vượt 700 ms |
| Hiệu năng | Tỷ lệ lỗi yêu cầu | Cùng bài tải và tập yêu cầu hợp lệ | Không vượt 0,5% |
| Độ tin cậy | Tỷ lệ yêu cầu nghiệp vụ thành công | Cửa sổ 30 ngày, chỉ tính giao dịch hợp lệ trong phạm vi dịch vụ | Ít nhất 99,9% |
| Bảo mật | Phát hiện nghiêm trọng/cao chưa xử lý | Quét và rà soát trên build phát hành, phạm vi API và thành phần đã liệt kê | Không có phát hiện nghiêm trọng/cao chưa xử lý nếu chính sách yêu cầu |
| Khả năng phục hồi | RTO và RPO | Diễn tập mất vùng dịch vụ với bộ dữ liệu gần quy mô mục tiêu | RTO không quá 60 phút; RPO không quá 5 phút |
| Khả năng sử dụng | Tỷ lệ hoàn thành tác vụ tạo đơn | Người tham gia thuộc nhóm mục tiêu, cùng kịch bản và thiết bị xác định | Ít nhất 90% hoàn thành không cần trợ giúp |
| Tương thích | Tỷ lệ kịch bản quan trọng đạt trên nền tảng hỗ trợ | Ma trận trình duyệt/thiết bị được chọn theo mức sử dụng | 100% kịch bản quan trọng trên tổ hợp bắt buộc |

Để dùng bảng này trong dự án thật, nhóm cần xác minh từng ngưỡng với dữ liệu đường cơ sở, cam kết dịch vụ và hậu quả nếu không đạt. Ví dụ, 99,9% có thể quá thấp hoặc quá cao tùy giá trị nghiệp vụ và khả năng vận hành; 700 ms có thể không phù hợp với endpoint khác.

### Cách đưa ra kết luận

Giả sử bài kiểm thử cho kết quả:

- p95 = 650 ms, đạt ngưỡng 700 ms.
- Tỷ lệ lỗi = 0,8%, vượt ngưỡng 0,5%.
- Tỷ lệ yêu cầu thành công trong cửa sổ đo = 99,2%.

Không thể kết luận hiệu năng đạt chỉ vì p95 đạt. Bộ tiêu chí yêu cầu đồng thời đáp ứng ngưỡng thời gian và tỷ lệ lỗi; kết quả hiện tại chưa đạt. Nhóm cần phân tích loại lỗi, tải và điểm nghẽn, sửa vấn đề rồi chạy lại trong điều kiện tương đương.

Nếu một chỉ số không thể đo do môi trường bị chặn, cần ghi là chưa có bằng chứng. Không được coi thiếu dữ liệu là đạt ngưỡng.

## 14. Ngưỡng cảnh báo, ngưỡng hành động và tiêu chí phát hành

Trong vận hành, có thể phân biệt ba mức:

- **Ngưỡng mục tiêu:** mức chất lượng mong muốn trong điều kiện bình thường.
- **Ngưỡng cảnh báo:** mức cho thấy xu hướng xấu hoặc cần điều tra trước khi ảnh hưởng vượt giới hạn.
- **Ngưỡng hành động:** mức buộc thực hiện biện pháp, ví dụ giới hạn tải, tắt tính năng, rollback hoặc kích hoạt ứng phó.

Ví dụ, SLO p95 dưới 700 ms có thể đi cùng cảnh báo khi p95 vượt 650 ms trong 5 phút và hành động khi p95 vượt 700 ms liên tục 10 phút hoặc tỷ lệ lỗi vượt ngưỡng. Các con số phải được chọn theo khả năng quan sát và mức chịu đựng của dịch vụ.

Ngưỡng cảnh báo nên tránh quá nhạy gây nhiều cảnh báo giả hoặc quá lỏng khiến nhóm phát hiện muộn. Cần kiểm tra cảnh báo bằng tình huống mô phỏng và xác định người nhận, thời gian phản hồi, runbook và điều kiện đóng cảnh báo.

Tiêu chí phát hành có thể yêu cầu nhiều điều kiện cùng đạt. Một số ngưỡng là bắt buộc; một số có thể được chấp nhận có điều kiện nếu rủi ro được đánh giá và người có thẩm quyền phê duyệt. Không được tự ý biến ngưỡng bắt buộc theo chính sách hoặc hợp đồng thành điều kiện tùy chọn.

## 15. Xử lý kết quả gần ngưỡng hoặc biến động

Kết quả gần ngưỡng không nên được diễn giải chỉ theo một lần chạy. Cần xem:

- Mức độ biến động giữa các lần đo.
- Số lượng mẫu và độ đại diện của dữ liệu.
- Có thay đổi cấu hình, tải hoặc phiên bản giữa các lần chạy không.
- Các chỉ số bảo vệ có dấu hiệu xấu đi không.
- Kết quả có ổn định qua các cửa sổ thời gian không.
- Có sự kiện ngoại lệ được xác minh như hạ tầng dùng chung bị quá tải không.

Không nên tự động làm tròn kết quả để biến thất bại thành đạt. Nếu ngưỡng là 700 ms và phép đo cho p95 = 704 ms, kết quả đã vượt ngưỡng theo định nghĩa hiện tại. Nhóm có thể điều tra độ không chắc chắn và chạy lại nếu điều kiện đo không hợp lệ, nhưng phải ghi lý do và giữ kết quả gốc.

Với chỉ số định tính, nên dùng rubric hoặc tiêu chí quan sát được. Ví dụ, đánh giá khả năng sử dụng cần nêu thế nào là hoàn thành tác vụ, lỗi nghiêm trọng là gì và người quan sát ghi nhận ra sao. Hai người đánh giá nên có hướng dẫn chung để giảm khác biệt chủ quan.

## 16. Cập nhật ngưỡng khi bối cảnh thay đổi

Ngưỡng không nên thay đổi tùy tiện, nhưng cũng không phải bất biến. Cần xem xét lại khi:

- Số lượng người dùng, lưu lượng hoặc quy mô dữ liệu thay đổi đáng kể.
- Kiến trúc, nền tảng, nhà cung cấp hoặc cấu hình triển khai thay đổi.
- Nhu cầu người dùng hoặc mức độ quan trọng của luồng nghiệp vụ thay đổi.
- Có dữ liệu production mới cho thấy giả định ban đầu không còn phù hợp.
- Cam kết dịch vụ, hợp đồng hoặc yêu cầu pháp lý thay đổi.
- Một thuộc tính trở thành rủi ro trọng yếu sau sự cố hoặc thay đổi mối đe dọa.

Khi cập nhật, ghi lại giá trị cũ, giá trị mới, lý do, dữ liệu hỗ trợ, người phê duyệt và thời điểm áp dụng. Nếu thay đổi điều kiện đo, cần cân nhắc đo lại đường cơ sở để so sánh công bằng.

Ví dụ, tăng gấp đôi tải dự kiến có thể đòi hỏi mô hình tải mới và ngưỡng hiệu năng được xem xét. Không nên chỉ nới ngưỡng p95 để phù hợp kết quả mới mà không phân tích tác động đến người dùng và năng lực hạ tầng.

## 17. Báo cáo kết quả đo

Một báo cáo có thể được người khác diễn giải cần có:

1. Thuộc tính chất lượng và tình huống được đánh giá.
2. Chỉ số, công thức, đơn vị, ngưỡng và tiêu chí đạt.
3. Phiên bản sản phẩm, cấu hình, môi trường và dữ liệu.
4. Mô hình tải hoặc hồ sơ người tham gia khi phù hợp.
5. Thời gian đo, giai đoạn warm-up, cửa sổ và số lần chạy.
6. Kết quả tổng hợp và phân bố, không chỉ một con số đại diện.
7. Các sai lệch, ngoại lệ, cảnh báo và giới hạn của phép đo.
8. Kết luận đạt, không đạt hoặc chưa đủ bằng chứng.
9. Rủi ro còn lại và hành động tiếp theo.

Ví dụ báo cáo hiệu năng:

> Build `release-4.2.1` được đo trên môi trường staging với 300 phiên đồng thời, dữ liệu 1 triệu đơn hàng và thời gian đo 20 phút sau warm-up 5 phút. p95 của API tìm kiếm là 680 ms, đạt ngưỡng 700 ms; tỷ lệ lỗi là 0,7%, vượt ngưỡng 0,5%. CPU trung bình 72%, độ sâu queue tăng trong 3 phút cuối. Kết luận: chưa đạt tiêu chí hiệu năng kết hợp; cần điều tra lỗi timeout và chạy lại sau khi xử lý.

Báo cáo này nêu cả chỉ số đạt và không đạt, cùng điều kiện đo. Người đọc có thể hiểu vì sao kết luận tổng thể là chưa đạt.

## 18. Những lỗi thường gặp khi đặt ngưỡng

- **Ngưỡng không gắn với nhu cầu người dùng:** chọn một con số theo thói quen mà không có lý do.
- **Chỉ dùng trung bình:** che khuất phần đuôi chậm hoặc nhóm người dùng gặp lỗi.
- **Không định nghĩa mẫu số:** tỷ lệ giữa các nhóm hoặc thời kỳ không thể so sánh.
- **Điều kiện đo không đại diện:** dữ liệu nhỏ, cấu hình yếu hoặc tải không đúng với mục tiêu.
- **Không đo lặp:** kết luận từ một lần chạy bị ảnh hưởng bởi nhiễu.
- **Chỉ đo một chỉ số:** tối ưu tốc độ nhưng bỏ qua lỗi, tính toàn vẹn hoặc tài nguyên.
- **Dùng ngưỡng bảo mật tuyệt đối mà không xác định phạm vi:** số phát hiện bằng không bị hiểu nhầm là không có lỗ hổng.
- **Đánh giá độ tin cậy bằng health check đơn giản:** dịch vụ còn phản hồi nhưng nghiệp vụ có thể không hoạt động.
- **Đánh giá phục hồi chỉ bằng thời gian khởi động:** bỏ qua mất dữ liệu và trạng thái không nhất quán.
- **Thay đổi ngưỡng sau khi thấy kết quả mà không ghi lý do:** làm giảm tính minh bạch và khả năng so sánh.
- **Không ghi trạng thái chưa đo:** thiếu dữ liệu bị hiểu nhầm thành đạt.

## 19. Checklist xác định ngưỡng và điều kiện đo

- [ ] Thuộc tính chất lượng gắn với nhu cầu hoặc rủi ro cụ thể.
- [ ] Tình huống đo nêu nguồn kích hoạt, hành động, môi trường, thành phần và phản hồi.
- [ ] Chỉ số có định nghĩa, đơn vị, công thức, mẫu số và nguồn dữ liệu.
- [ ] Ngưỡng có căn cứ từ yêu cầu, đường cơ sở, cam kết hoặc phân tích rủi ro.
- [ ] Điều kiện đo ghi rõ phiên bản, cấu hình, dữ liệu, tải và thời gian.
- [ ] Có quy tắc warm-up, số lần chạy và xử lý biến động khi cần.
- [ ] Chỉ số kết quả đi kèm chỉ số bảo vệ và chỉ số chẩn đoán phù hợp.
- [ ] Tiêu chí đạt, không đạt và chưa đủ bằng chứng được xác định trước.
- [ ] Ngưỡng cảnh báo và hành động có người nhận, runbook và điều kiện phản ứng.
- [ ] Có quy trình xem xét lại khi nhu cầu hoặc môi trường thay đổi.
- [ ] Báo cáo giữ lại kết quả gốc, ngoại lệ, giới hạn và rủi ro còn lại.

## 20. Những điểm cần ghi nhớ

- Mỗi thuộc tính chất lượng cần chỉ số, ngưỡng và điều kiện đo phù hợp với bản chất của nó.
- Một chỉ số chỉ có ý nghĩa khi có định nghĩa, đơn vị, mẫu số, nguồn dữ liệu và cửa sổ đo.
- Ngưỡng cần xuất phát từ nhu cầu người dùng, rủi ro, cam kết và đường cơ sở; không chọn tùy tiện.
- Hiệu năng cần xem thời gian phản hồi theo phân vị, thông lượng, tỷ lệ lỗi và tài nguyên trong mô hình tải rõ ràng.
- Độ tin cậy cần định nghĩa giao dịch thành công, cửa sổ đo, SLI/SLO và cách tính thời gian gián đoạn.
- Khả năng phục hồi cần đo cả RTO, RPO và tính toàn vẹn dữ liệu sau khôi phục.
- Bảo mật cần nhiều loại bằng chứng theo phạm vi và mối đe dọa; không có một chỉ số nào chứng minh an toàn tuyệt đối.
- Khả năng sử dụng, tiếp cận, tương thích và bảo trì cần điều kiện thử hoặc tiêu chí quan sát riêng.
- Kết quả gần ngưỡng cần được xem cùng biến động và chất lượng dữ liệu; không làm tròn hoặc thay đổi ngưỡng để che thất bại.
- Khi điều kiện hoặc nhu cầu thay đổi, cập nhật ngưỡng minh bạch và đo lại đường cơ sở khi cần.

## Câu hỏi tự kiểm tra

1. Phân biệt chỉ số, định nghĩa chỉ số, điều kiện đo, đường cơ sở, ngưỡng và tiêu chí đạt bằng một ví dụ.
2. Vì sao p95 thường cung cấp thông tin khác với thời gian phản hồi trung bình? Khi nào cần xem p99?
3. Hãy mô tả điều kiện đo đủ rõ để một nhóm khác có thể lặp lại bài kiểm thử tải.
4. Một dịch vụ có tỷ lệ sẵn sàng cao nhưng giao dịch vẫn sai trạng thái. Điều này cho thấy giới hạn gì của chỉ số sẵn sàng?
5. Phân biệt RTO và RPO. Một bài kiểm thử phục hồi cần xác minh những gì ngoài thời gian khởi động lại?
6. Vì sao kết quả quét bảo mật không có phát hiện nghiêm trọng không chứng minh hệ thống không có lỗ hổng?
7. Hãy chọn một tác vụ người dùng và đề xuất chỉ số, ngưỡng, cỡ mẫu và điều kiện đo khả năng sử dụng.
8. Nếu p95 đạt ngưỡng nhưng tỷ lệ lỗi vượt giới hạn, kết luận tổng thể nên là gì và cần điều tra những dữ liệu nào?
9. Khi lưu lượng dự kiến tăng gấp đôi, nhóm nên xem xét lại những ngưỡng và điều kiện đo nào?
10. Hãy lập một bảng ngưỡng cho ít nhất ba thuộc tính chất lượng của sản phẩm bạn biết, nêu căn cứ và giới hạn của từng phép đo.
