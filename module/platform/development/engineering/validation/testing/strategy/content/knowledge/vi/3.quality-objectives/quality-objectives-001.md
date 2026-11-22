# Chuyển nhu cầu kinh doanh thành mục tiêu chất lượng có thể kiểm chứng

## 1. Vì sao cần mục tiêu chất lượng?

Nhu cầu kinh doanh thường được diễn đạt bằng kết quả mà tổ chức muốn đạt được: khách hàng hoàn tất giao dịch thuận tiện, nhân viên xử lý hồ sơ nhanh hơn, dữ liệu được bảo vệ, dịch vụ luôn sẵn sàng hoặc chi phí vận hành được kiểm soát. Những phát biểu này định hướng sản phẩm nhưng chưa đủ cụ thể để nhóm phát triển và kiểm thử quyết định hệ thống cần đáp ứng điều gì, kiểm tra bằng cách nào và khi nào có thể chấp nhận phát hành.

**Mục tiêu chất lượng** chuyển kết quả mong muốn thành các điều kiện có thể quan sát và đo lường trong một bối cảnh xác định. Mục tiêu tốt giúp các bên thống nhất mức chất lượng cần đạt, ưu tiên rủi ro, thiết kế hoạt động xác nhận và theo dõi sản phẩm sau khi đưa vào sử dụng.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, mục tiêu chất lượng là cầu nối giữa nhu cầu kinh doanh, yêu cầu sản phẩm, chiến lược kiểm thử và bằng chứng chấp nhận. Chuỗi liên kết cần rõ ràng:

```text
Nhu cầu kinh doanh
       |
       v
Người dùng và hành trình quan trọng
       |
       v
Rủi ro và thuộc tính chất lượng liên quan
       |
       v
Mục tiêu chất lượng có chỉ số, ngưỡng và điều kiện
       |
       v
Phương pháp xác nhận và tiêu chí chấp nhận
       |
       v
Bằng chứng trước phát hành và giám sát sau phát hành
```

Nếu thiếu một mắt xích, nhóm có thể hoàn thành nhiều kiểm thử nhưng vẫn không chứng minh được sản phẩm đáp ứng nhu cầu ban đầu. Ví dụ, kiểm thử chức năng xác nhận nút “Thanh toán” hoạt động không chứng minh quy trình thanh toán đủ nhanh, không thu tiền hai lần khi người dùng thử lại hoặc xử lý đúng khi cổng thanh toán tạm thời mất kết nối.

## 2. Phân biệt nhu cầu, yêu cầu và mục tiêu chất lượng

Các khái niệm liên quan cần được phân biệt để tránh biến mục tiêu kinh doanh thành một chỉ số kỹ thuật thiếu ý nghĩa.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Nhu cầu kinh doanh | Kết quả tổ chức hoặc khách hàng cần đạt | Người mua có thể đặt hàng thuận tiện và tin tưởng giao dịch |
| Kết quả/nghiệp vụ mong đợi | Hành vi hoặc kết quả sản phẩm phải hỗ trợ | Người mua tạo được đơn hàng hợp lệ và nhận xác nhận |
| Yêu cầu chức năng | Hệ thống phải thực hiện hành vi nào | Hệ thống ghi nhận đơn hàng và gửi yêu cầu thanh toán |
| Yêu cầu chất lượng | Mức chất lượng cần có trong một điều kiện sử dụng | Giao dịch phải phản hồi nhanh và không tạo giao dịch trùng |
| Mục tiêu chất lượng | Mức chất lượng được diễn đạt bằng phép đo, ngưỡng, phạm vi và điều kiện | 95% yêu cầu tạo đơn hàng hợp lệ phản hồi trong không quá 2 giây ở tải đã thống nhất |
| Bằng chứng xác nhận | Kết quả chứng minh mục tiêu đã hoặc chưa đạt | Báo cáo kiểm thử tải, kết quả kiểm thử tính lặp an toàn và số liệu giám sát |

Một chỉ số kinh doanh như tỷ lệ chuyển đổi, doanh thu hoặc tỷ lệ giữ chân người dùng có thể phản ánh kết quả cuối cùng, nhưng thường chịu ảnh hưởng của nhiều yếu tố ngoài phần mềm. Nhóm sản phẩm cần tìm ra các điều kiện chất lượng mà hệ thống có thể kiểm soát và có khả năng đóng góp vào kết quả đó.

Ví dụ, tỷ lệ chuyển đổi thấp có thể liên quan đến tốc độ tải trang, lỗi thanh toán, nội dung, giá cả hoặc mức độ phù hợp của sản phẩm. Không nên tự động đặt mục tiêu “tăng chuyển đổi 10%” làm tiêu chí kiểm thử phần mềm. Hãy kiểm tra dữ liệu và hành trình người dùng để xác định những vấn đề chất lượng có thể kiểm chứng, chẳng hạn tỷ lệ lỗi ở bước thanh toán, thời gian phản hồi hoặc khả năng sử dụng trên thiết bị di động.

### 2.1. Mục tiêu chất lượng, KPI, SLI, SLO và SLA

Các thuật ngữ đo lường thường xuất hiện trong cùng cuộc thảo luận nhưng có vai trò khác nhau:

- **KPI (Key Performance Indicator):** chỉ số theo dõi hiệu quả kinh doanh hoặc hoạt động, ví dụ tỷ lệ đơn hàng hoàn tất. KPI có thể chịu tác động từ chất lượng phần mềm nhưng không nhất thiết là chỉ số chất lượng trực tiếp.
- **SLI (Service Level Indicator):** chỉ số đo lường một khía cạnh của dịch vụ, ví dụ tỷ lệ yêu cầu thành công hoặc độ trễ phản hồi.
- **SLO (Service Level Objective):** mục tiêu đặt ra cho một SLI trong một khoảng thời gian và phạm vi xác định, ví dụ tỷ lệ yêu cầu đọc thành công đạt ít nhất 99,9% trong cửa sổ 30 ngày.
- **SLA (Service Level Agreement):** cam kết mức dịch vụ giữa các bên, thường gắn với điều kiện, phạm vi và hệ quả khi không đáp ứng. SLA có thể dựa trên SLO nhưng không đồng nghĩa với mục tiêu kiểm thử nội bộ.

Mục tiêu chất lượng có thể dùng SLI/SLO khi đánh giá dịch vụ vận hành, đồng thời bao gồm các mục tiêu khác như độ chính xác dữ liệu, khả năng sử dụng, bảo mật, tương thích và khả năng phục hồi. Không phải mọi mục tiêu chất lượng đều là cam kết SLA.

## 3. Những thuộc tính chất lượng cần xem xét

Không cần đặt mục tiêu cho mọi thuộc tính trong mọi sản phẩm. Hãy chọn thuộc tính liên quan trực tiếp đến hành trình người dùng, tác động kinh doanh, nghĩa vụ pháp lý và rủi ro của hệ thống.

| Thuộc tính | Câu hỏi cần trả lời | Chỉ số hoặc bằng chứng có thể dùng |
|---|---|---|
| Tính phù hợp chức năng | Hệ thống có cung cấp đúng và đủ kết quả nghiệp vụ không? | Tỷ lệ xử lý đúng, độ chính xác tính toán, kết quả đối chiếu, số lỗi nghiệp vụ |
| Hiệu năng và hiệu quả | Người dùng có nhận được phản hồi trong thời gian chấp nhận được ở tải dự kiến không? | Độ trễ p50/p95/p99, thông lượng, số người dùng đồng thời, mức sử dụng CPU/bộ nhớ |
| Độ tin cậy và sẵn sàng | Dịch vụ có hoạt động ổn định và phục hồi được khi xảy ra lỗi không? | Tỷ lệ yêu cầu thành công, thời gian sẵn sàng, tỷ lệ lỗi, thời gian khôi phục, RTO/RPO |
| Bảo mật và riêng tư | Tài sản và dữ liệu có được bảo vệ theo quyền và chính sách không? | Kết quả kiểm thử phân quyền, phát hiện lỗ hổng, mã hóa, nhật ký kiểm toán, kiểm soát dữ liệu |
| Khả dụng và khả năng tiếp cận | Người dùng mục tiêu có thể hoàn thành tác vụ dễ dàng và tiếp cận được không? | Tỷ lệ hoàn thành tác vụ, thời gian hoàn thành, tỷ lệ lỗi thao tác, kiểm tra bàn phím/trình đọc màn hình |
| Tương thích và liên thông | Hệ thống có hoạt động đúng với thiết bị, trình duyệt, phiên bản và đối tác được hỗ trợ không? | Ma trận môi trường, tỷ lệ tương thích, kết quả kiểm thử hợp đồng và tích hợp |
| Toàn vẹn dữ liệu | Dữ liệu có chính xác, nhất quán, không bị mất hoặc nhân đôi không? | Sai lệch đối soát, số bản ghi lỗi, tính duy nhất, kết quả kiểm thử chuyển đổi và khôi phục |
| Khả năng mở rộng | Hệ thống có đáp ứng khi số người dùng hoặc khối lượng dữ liệu tăng không? | Thông lượng theo mức tải, độ trễ khi tăng tải, tài nguyên trên mỗi giao dịch |
| Khả năng bảo trì và vận hành | Nhóm có thể thay đổi, triển khai, chẩn đoán và khôi phục hệ thống an toàn không? | Thời gian xây dựng/triển khai, tỷ lệ thay đổi gây lỗi, khả năng quan sát, thời gian chẩn đoán |

Một thuộc tính có thể cần nhiều chỉ số. Chẳng hạn, đo hiệu năng chỉ bằng thời gian trung bình có thể che khuất một nhóm nhỏ người dùng phải chờ rất lâu. Khi phân tích độ trễ, các phân vị như p95 hoặc p99 thường cho thấy trải nghiệm ở phần đuôi phân phối rõ hơn. Ngược lại, không nên chọn nhiều chỉ số đến mức nhóm không thể giải thích hoặc hành động dựa trên chúng.

## 4. Cấu trúc của một mục tiêu chất lượng có thể kiểm chứng

Một mục tiêu cần đủ thông tin để hai người độc lập có thể xác định cùng một phép đo và kết luận đạt hay không đạt. Có thể sử dụng cấu trúc sau:

> Trong **[bối cảnh/phạm vi]**, khi **[tác nhân và điều kiện kích hoạt]**, hệ thống phải **[hành vi hoặc kết quả chất lượng quan sát được]**, được đo bằng **[chỉ số và cách tính]**, đạt **[ngưỡng/mục tiêu]** trong **[khoảng thời gian hoặc điều kiện tải]**. Kết quả được xác nhận bằng **[phương pháp và nguồn bằng chứng]**.

Mỗi mục tiêu nên xác định các thành phần sau:

1. **Đối tượng và phạm vi:** dịch vụ, chức năng, nhóm người dùng, loại dữ liệu hoặc môi trường áp dụng.
2. **Điều kiện:** tải, thiết bị, mạng, dữ liệu, phiên bản, thời điểm và trạng thái hệ thống.
3. **Hành vi/kết quả mong đợi:** điều gì phải xảy ra hoặc điều gì không được xảy ra.
4. **Chỉ số:** đại lượng đo, đơn vị, công thức, mẫu số, cách lấy mẫu và các trường hợp loại trừ.
5. **Ngưỡng chấp nhận:** giá trị mục tiêu, giới hạn tối đa/tối thiểu và mức cảnh báo nếu cần.
6. **Cửa sổ đánh giá:** một lần chạy, một phiên, một ngày, 30 ngày hoặc khoảng thời gian phù hợp khác.
7. **Phương pháp xác nhận:** kiểm thử, phân tích, kiểm tra tài liệu, thử nghiệm với người dùng hoặc giám sát vận hành.
8. **Chủ sở hữu:** người chịu trách nhiệm về định nghĩa, dữ liệu và xử lý khi mục tiêu không đạt.

Ví dụ chưa đủ rõ: “Trang thanh toán phải nhanh.”

Ví dụ có thể kiểm chứng hơn: “Ở môi trường kiểm thử gần với cấu hình sản xuất, với 500 phiên người dùng đồng thời và dữ liệu giỏ hàng đại diện, 95% yêu cầu tải bước xác nhận thanh toán phải có thời gian phản hồi phía máy chủ không quá 800 ms trong bài kiểm thử kéo dài 30 phút; báo cáo phải ghi lại độ trễ p50/p95/p99, thông lượng và tỷ lệ lỗi.”

Ngưỡng trong ví dụ chỉ minh họa cách diễn đạt. Nhóm phải xác định con số thực tế từ kỳ vọng người dùng, dữ liệu nền, năng lực hạ tầng, mức rủi ro và chi phí. Không sao chép ngưỡng ví dụ vào sản phẩm khi chưa có căn cứ.

### 4.1. Định nghĩa chỉ số chính xác

Đối với chỉ số dạng tỷ lệ, cần ghi rõ tử số và mẫu số. Ví dụ “tỷ lệ thanh toán thành công” có thể được hiểu theo nhiều cách: số yêu cầu được cổng thanh toán chấp thuận trên tổng yêu cầu gửi đi, số đơn hàng được xác nhận trên tổng đơn hợp lệ, hoặc số phiên người dùng hoàn tất trên tổng phiên bắt đầu thanh toán. Các mẫu số này phản ánh những vấn đề khác nhau.

Một định nghĩa chỉ số nên nêu:

- Sự kiện bắt đầu và kết thúc được tính vào phép đo.
- Đơn vị đo và nguồn dữ liệu.
- Những trường hợp loại trừ có lý do rõ ràng, chẳng hạn giao dịch bị ngân hàng từ chối hợp lệ không được tính là lỗi kỹ thuật của dịch vụ.
- Cách xử lý yêu cầu trùng, retry, timeout, hủy bởi người dùng và dữ liệu thiếu.
- Cửa sổ thời gian, cách tổng hợp và quy tắc xử lý khi không đủ mẫu.

Đối với độ trễ, cần xác định điểm bắt đầu/kết thúc, đo ở phía máy khách hay máy chủ, có tính thời gian mạng hay không và phân vị nào được dùng. Đối với tính sẵn sàng, cần xác định dịch vụ nào được đo, phép kiểm tra nào đại diện cho khả năng sử dụng, cách tính thời gian gián đoạn và lịch bảo trì có được xử lý riêng hay không.

### 4.2. Dùng kịch bản chất lượng để mô tả điều kiện

Khi yêu cầu còn trừu tượng, có thể mô tả một kịch bản chất lượng với sáu thành phần:

| Thành phần | Nội dung cần mô tả |
|---|---|
| Nguồn kích thích | Ai hoặc thành phần nào tạo ra sự kiện? |
| Kích thích | Sự kiện, tải hoặc tình huống nào xảy ra? |
| Môi trường | Hệ thống đang ở điều kiện vận hành nào? |
| Thành phần chịu tác động | Dịch vụ, giao diện, dữ liệu hoặc tài nguyên nào liên quan? |
| Phản hồi mong đợi | Hệ thống cần xử lý hoặc duy trì điều gì? |
| Thước đo phản hồi | Ngưỡng nào cho biết phản hồi đạt yêu cầu? |

Ví dụ: “Khi cổng thanh toán không phản hồi trong lúc người mua xác nhận đơn hàng, dịch vụ đặt hàng phải giữ trạng thái giao dịch có thể truy vấn, không ghi nhận thanh toán thành công khi chưa có xác nhận và cho phép đối soát lại; không tạo khoản thu trùng khi yêu cầu được gửi lại.” Kịch bản này làm rõ tình huống lỗi và hành vi mong đợi. Để thành mục tiêu hoàn chỉnh, cần bổ sung phép đo và tiêu chí cụ thể, ví dụ số trường hợp tạo giao dịch trùng trong tập kiểm thử phải bằng 0 và mọi giao dịch chưa rõ kết quả phải được đưa vào trạng thái có thể đối soát.

## 5. Quy trình chuyển nhu cầu kinh doanh thành mục tiêu chất lượng

### Bước 1: Làm rõ kết quả kinh doanh và người dùng

Hỏi vì sao nhu cầu xuất hiện, ai được hưởng lợi, tác vụ nào cần hoàn thành và hậu quả nếu tác vụ thất bại. Xác định người dùng chính, người vận hành, đối tác tích hợp và các bên có nghĩa vụ pháp lý hoặc kiểm soát. Tránh bắt đầu bằng danh sách công nghệ hay chỉ số có sẵn.

Ví dụ, “giảm thời gian xử lý hồ sơ” cần làm rõ thời gian tính từ lúc nào đến lúc nào, hồ sơ nào thuộc phạm vi, ai xử lý và phần chậm trễ nào do hệ thống gây ra. Nếu phần lớn thời gian phụ thuộc vào bước phê duyệt của con người, tối ưu tốc độ máy chủ có thể không tạo ra kết quả kinh doanh mong muốn.

### Bước 2: Phân rã hành trình và xác định điểm chất lượng quan trọng

Vẽ hoặc mô tả các bước người dùng đi qua để đạt kết quả. Đánh dấu điểm có thể gây thất bại, chờ đợi, nhầm lẫn, mất dữ liệu, lộ thông tin hoặc phát sinh chi phí. Xem xét cả luồng bình thường và tình huống ngoại lệ: tải cao, mạng yếu, yêu cầu lặp, dữ liệu không hợp lệ, dịch vụ phụ thuộc bị lỗi, phiên hết hạn và khôi phục sau gián đoạn.

### Bước 3: Xác định thuộc tính chất lượng và rủi ro

Với mỗi điểm quan trọng, chọn thuộc tính chất lượng liên quan. Đánh giá tác động nếu lỗi xảy ra, khả năng xảy ra, phạm vi ảnh hưởng và khả năng phát hiện trước khi người dùng chịu tác động. Cân nhắc rủi ro về tiền, an toàn, dữ liệu cá nhân, nghĩa vụ pháp lý, uy tín và vận hành.

Không phải mọi rủi ro đều có thể quy về một điểm số. Các yêu cầu bắt buộc về bảo mật, an toàn hoặc tuân thủ cần được giữ thành điều kiện riêng, kể cả khi điểm ưu tiên định lượng của chúng không cao.

### Bước 4: Thu thập dữ liệu nền và xác định điều kiện thực tế

Tìm số liệu hiện tại từ hệ thống đang vận hành, thử nghiệm người dùng, báo cáo sự cố, dữ liệu hỗ trợ, kiểm thử hiệu năng và môi trường triển khai. Xác định tải bình thường, tải đỉnh, tăng trưởng dự kiến, cấu hình thiết bị, chất lượng mạng, vùng địa lý, dữ liệu đại diện và phụ thuộc bên ngoài.

Nếu chưa có dữ liệu nền, ghi rõ giả định và độ không chắc chắn. Có thể cần tạo phép đo ban đầu, chạy thử nghiệm có kiểm soát hoặc thực hiện nghiên cứu người dùng trước khi cam kết một ngưỡng. Không biến một con số ước lượng thành yêu cầu chính thức mà không ghi nguồn và người xác nhận.

### Bước 5: Viết mục tiêu và tiêu chí chấp nhận

Dùng cấu trúc ở mục 4 để diễn đạt từng mục tiêu. Mỗi mục tiêu phải có một ý nghĩa rõ ràng và có thể truy vết đến nhu cầu hoặc rủi ro. Tách các mục tiêu khác bản chất, ví dụ độ trễ và tỷ lệ lỗi, để kết quả của một phép đo không che khuất phép đo còn lại.

Đặt cả giới hạn đạt và điều kiện đo. “99,9% thành công” chưa đầy đủ nếu không nêu thành công của loại yêu cầu nào, đo ở đâu, trong khoảng thời gian nào và có bao nhiêu mẫu. Khi cần, xác định ngưỡng cảnh báo thấp hơn ngưỡng chấp nhận để nhóm có thời gian hành động trước khi vi phạm mục tiêu.

### Bước 6: Chọn cách xác nhận phù hợp

Chọn phương pháp theo bản chất mục tiêu. Kiểm thử tải phù hợp để xác nhận hiệu năng trong điều kiện xác định; kiểm thử bảo mật và rà soát quyền phù hợp với rủi ro truy cập; kiểm thử khả dụng với người dùng đại diện giúp đánh giá khả năng hoàn thành tác vụ; kiểm thử phục hồi giúp xác nhận hành vi khi phụ thuộc bị lỗi. Một số mục tiêu cần kết hợp kiểm thử trước phát hành với giám sát sau phát hành.

### Bước 7: Thống nhất ưu tiên, đánh đổi và trách nhiệm

Trao đổi với người phụ trách sản phẩm, kiến trúc, phát triển, kiểm thử, vận hành, bảo mật và nghiệp vụ. Làm rõ đánh đổi về chi phí, thời gian, trải nghiệm và rủi ro. Ghi lại người phê duyệt ngưỡng, chủ sở hữu chỉ số, nơi lưu bằng chứng và hành động khi mục tiêu không đạt.

### Bước 8: Theo dõi và cập nhật

Sau khi phát hành, so sánh số liệu thực tế với mục tiêu. Xem xét lại khi tải, nhóm người dùng, quy trình nghiệp vụ, kiến trúc, nhà cung cấp, quy định hoặc mức độ rủi ro thay đổi. Mục tiêu cần được cập nhật có kiểm soát, có lý do và lịch sử quyết định để không âm thầm hạ chuẩn chất lượng.

## 6. Ví dụ xuyên suốt: chuyển nhu cầu đặt hàng trực tuyến thành mục tiêu

Giả sử doanh nghiệp muốn người mua hoàn tất đơn hàng thuận tiện và tin tưởng rằng khoản thanh toán được ghi nhận chính xác. Nhóm phân tích hành trình gồm xem giỏ hàng, nhập thông tin, xác nhận đơn, chuyển yêu cầu đến cổng thanh toán và nhận kết quả.

| Nhu cầu/rủi ro | Mục tiêu chất lượng minh họa | Cách xác nhận |
|---|---|---|
| Người mua không phải chờ quá lâu | Với tải đại diện đã thống nhất, p95 thời gian phản hồi của API tạo đơn hợp lệ không vượt quá 800 ms trong bài kiểm thử 30 phút | Kiểm thử tải, phân tích p50/p95/p99, thông lượng và tỷ lệ lỗi |
| Người mua có thể hoàn tất giao dịch | Ít nhất 99,5% yêu cầu tạo đơn hợp lệ được xử lý thành công trong cửa sổ đo đã thống nhất, loại trừ các giao dịch bị từ chối hợp lệ bởi đơn vị phát hành thanh toán | Kiểm thử tích hợp, kiểm thử luồng đầu cuối và giám sát tỷ lệ lỗi theo nguyên nhân |
| Không thu tiền hai lần khi thử lại | Trong các kịch bản gửi lặp cùng khóa idempotency và các tình huống timeout/retry được xác định, không có giao dịch nào tạo khoản thu trùng | Kiểm thử tích hợp với mô phỏng timeout, retry, phản hồi trễ và đối soát trạng thái |
| Người mua có thể sử dụng dịch vụ khi cần | Các hành trình đặt hàng cốt lõi đạt mục tiêu sẵn sàng đã được chủ sản phẩm phê duyệt trong cửa sổ theo dõi, được đo bằng kiểm tra tổng hợp từ các vùng đại diện | Kiểm thử health check, giám sát tổng hợp và rà soát sự cố |
| Thông tin người mua được bảo vệ | Mọi thao tác xem hoặc sửa dữ liệu đơn hàng đều được kiểm tra quyền theo vai trò; không có trường hợp truy cập trái phép trong bộ kiểm thử ma trận quyền đã xác định | Kiểm thử bảo mật, kiểm thử âm tính theo vai trò và rà soát nhật ký truy cập |
| Có thể khôi phục sau sự cố | Dịch vụ đặt hàng phục hồi trong RTO đã thống nhất và dữ liệu giao dịch đáp ứng RPO đã phê duyệt trong diễn tập khôi phục | Diễn tập khôi phục, kiểm thử sao lưu và đối chiếu dữ liệu sau phục hồi |

Các giá trị 800 ms và 99,5% chỉ là số minh họa cho cách viết mục tiêu. Nhóm phải kiểm chứng chúng bằng dữ liệu thực tế, kỳ vọng khách hàng, năng lực hạ tầng và mức chấp nhận rủi ro. “Không có giao dịch trùng” là điều kiện cho tập tình huống và phạm vi kiểm thử được mô tả; để kiểm soát trong thực tế, cần thêm cơ chế idempotency, đối soát và giám sát giao dịch.

Ví dụ trên cũng cho thấy một nhu cầu kinh doanh có thể tạo ra nhiều mục tiêu chất lượng bổ sung cho nhau. Chỉ đo tốc độ hoặc tỷ lệ hoàn tất là chưa đủ nếu hệ thống vẫn có thể ghi nhận sai trạng thái thanh toán hoặc làm lộ dữ liệu.

## 7. Từ mục tiêu đến chiến lược kiểm thử và cổng chất lượng

Sau khi mục tiêu được thống nhất, nhóm cần chỉ rõ bằng chứng nào chứng minh mục tiêu đạt. Có thể lập ma trận truy vết:

| Mục tiêu | Rủi ro cần kiểm soát | Hoạt động xác nhận | Bằng chứng | Điểm quyết định |
|---|---|---|---|---|
| p95 phản hồi dưới ngưỡng ở tải quy định | Người dùng chờ lâu hoặc hệ thống quá tải | Kiểm thử tải và phân tích hồ sơ hiệu năng | Báo cáo tải, biểu đồ phân vị, thông lượng và lỗi | Không phát hành nếu vượt ngưỡng đã phê duyệt hoặc chưa giải thích được điểm nghẽn nghiêm trọng |
| Không phát sinh giao dịch trùng khi retry | Thu tiền sai hoặc đối soát khó khăn | Kiểm thử idempotency, timeout và tích hợp | Kết quả kịch bản, nhật ký giao dịch và đối chiếu dữ liệu | Không chấp nhận lỗi tạo giao dịch trùng trong phạm vi bắt buộc |
| Quyền truy cập đúng theo vai trò | Rò rỉ hoặc sửa dữ liệu trái phép | Kiểm thử phân quyền dương tính và âm tính | Ma trận quyền, kết quả kiểm thử và nhật ký | Không chấp nhận đường truy cập trái phép thuộc phạm vi kiểm soát |
| Khôi phục trong RTO/RPO đã duyệt | Dịch vụ ngừng lâu hoặc mất dữ liệu | Diễn tập phục hồi và kiểm tra sao lưu | Biên bản diễn tập, thời gian phục hồi, kết quả đối soát | Chỉ chấp nhận khi đạt mục tiêu và có người chịu trách nhiệm xác nhận |

Cổng chất lượng nên được xác định theo mức rủi ro. Một số điều kiện là bắt buộc, ví dụ không có lỗi làm sai lệch giao dịch hoặc truy cập trái phép nghiêm trọng trong phạm vi đã xác định. Một số điều kiện có thể được chấp nhận có điều kiện nếu có phương án giảm thiểu, người phê duyệt và thời hạn xử lý. Quyết định ngoại lệ cần ghi lại rủi ro còn lại, tác động đến người dùng và kế hoạch theo dõi.

Không nên dựa vào một tỷ lệ bao phủ mã nguồn chung để kết luận các mục tiêu chất lượng đã đạt. Bao phủ mã nguồn cho biết phần mã được thực thi trong kiểm thử theo một định nghĩa cụ thể; nó không chứng minh kịch bản quan trọng đã được kiểm tra đúng, môi trường đại diện hoặc ngưỡng hiệu năng được đáp ứng.

### 7.1. Chọn phương pháp theo loại mục tiêu

- **Hiệu năng:** kiểm thử tải, tải đỉnh, tải kéo dài, tăng tải và đo trên cấu hình gần sản xuất. Báo cáo cả độ trễ, thông lượng, lỗi và tài nguyên.
- **Độ tin cậy:** kiểm thử lỗi phụ thuộc, timeout, retry, mất kết nối, khởi động lại, chuyển vùng và khôi phục dữ liệu khi phù hợp.
- **Bảo mật:** rà soát thiết kế, phân tích phụ thuộc, kiểm thử xác thực/ủy quyền, kiểm thử xâm nhập theo phạm vi và xác minh xử lý dữ liệu nhạy cảm.
- **Khả dụng:** thử nghiệm với người dùng đại diện, đo tỷ lệ hoàn thành và thời gian tác vụ, kiểm tra khả năng tiếp cận bằng bàn phím và công nghệ hỗ trợ.
- **Tương thích:** kiểm thử trên ma trận thiết bị, trình duyệt, hệ điều hành, phiên bản API và cấu hình được cam kết hỗ trợ.
- **Toàn vẹn dữ liệu:** kiểm thử quy tắc, đối soát, dữ liệu biên, tính lặp, chuyển đổi schema, sao lưu và phục hồi.
- **Khả năng bảo trì/vận hành:** diễn tập triển khai, rollback, quan sát, cảnh báo, chẩn đoán và quy trình xử lý sự cố.

Mục tiêu định lượng thường cần cả kiểm thử có kiểm soát và quan sát sản xuất. Kiểm thử trước phát hành giúp tạo điều kiện lặp lại; số liệu sản xuất xác nhận hành vi trong môi trường và tải thực. Hai nguồn bằng chứng bổ sung cho nhau.

## 8. Ưu tiên mục tiêu và xử lý đánh đổi

Nguồn lực có hạn nên cần ưu tiên mục tiêu dựa trên tác động kinh doanh và rủi ro. Có thể xem xét:

- Mức độ nghiêm trọng nếu mục tiêu không đạt: ảnh hưởng đến người dùng, doanh thu, dữ liệu, an toàn, uy tín và nghĩa vụ pháp lý.
- Khả năng xảy ra: độ phức tạp, lịch sử lỗi, mức biến động, phụ thuộc bên ngoài và điều kiện vận hành.
- Khả năng phát hiện và phục hồi: hệ thống có phát hiện nhanh, giới hạn tác động và khôi phục được không.
- Phạm vi ảnh hưởng: một người dùng, một nhóm, toàn bộ khách hàng hay hệ thống liên kết.
- Chi phí đạt mục tiêu: tác động đến hạ tầng, thời gian phát triển, vận hành và trải nghiệm.

Một ma trận xác suất/tác động có thể giúp sắp xếp thảo luận, nhưng không thay thế phán đoán chuyên môn. Không để một điểm rủi ro tổng hợp làm mất đi yêu cầu bắt buộc về an toàn, bảo mật hoặc tuân thủ.

Các mục tiêu có thể xung đột. Tăng mã hóa và kiểm tra có thể làm tăng độ trễ; tăng thời gian lưu dữ liệu có thể hỗ trợ đối soát nhưng làm tăng nghĩa vụ bảo vệ dữ liệu; triển khai thường xuyên giúp nhận phản hồi nhanh nhưng đòi hỏi kiểm soát phát hành và khôi phục tốt. Khi có xung đột:

1. Nêu rõ mục tiêu nào đang xung đột và nhóm người dùng nào chịu ảnh hưởng.
2. Xác định giới hạn không được vi phạm, như quy định bảo mật hoặc tính đúng đắn giao dịch.
3. Đo tác động của các phương án trong điều kiện đại diện.
4. Thống nhất đánh đổi với đúng người có thẩm quyền và ghi lại lý do.
5. Đặt ngưỡng theo dõi và điều kiện xem xét lại quyết định.

Không nên đặt mục tiêu “tối đa hóa mọi thuộc tính”. Một mục tiêu hữu ích nêu rõ mức chất lượng cần thiết cho hành trình và rủi ro cụ thể, trong giới hạn nguồn lực và nghĩa vụ của sản phẩm.

## 9. Quản lý mục tiêu trong suốt vòng đời sản phẩm

Mục tiêu chất lượng có thể thay đổi khi sản phẩm mở rộng, người dùng thay đổi, kiến trúc được tái cấu trúc hoặc phụ thuộc bên ngoài thay đổi. Cần quản lý mục tiêu như một phần của yêu cầu sản phẩm:

- Gắn mã định danh hoặc liên kết ổn định cho từng mục tiêu để truy vết từ nhu cầu đến kiểm thử và số liệu vận hành.
- Lưu phiên bản, ngày hiệu lực, người đề xuất, người phê duyệt và lý do thay đổi ngưỡng.
- Xác định chủ sở hữu chỉ số, nguồn dữ liệu, dashboard hoặc báo cáo và người xử lý khi vi phạm.
- Rà soát mục tiêu khi có thay đổi đáng kể về tải, nhóm người dùng, quy trình, dữ liệu, kiến trúc hoặc nghĩa vụ pháp lý.
- Loại bỏ hoặc thay thế mục tiêu không còn phù hợp, nhưng lưu lại lịch sử để hiểu các quyết định trước đó.
- Kiểm tra xem phép đo có còn đại diện cho trải nghiệm thực tế và có bị tác động bởi thay đổi cách thu thập dữ liệu hay không.

Khi một mục tiêu liên tục không đạt, cần phân tích nguyên nhân thay vì tự động nới ngưỡng. Có thể nguyên nhân nằm ở kiến trúc, dữ liệu, hạ tầng, thiết kế trải nghiệm, hệ thống bên ngoài hoặc cách định nghĩa phép đo. Chỉ điều chỉnh mục tiêu khi bối cảnh hoặc mức chấp nhận rủi ro thực sự thay đổi và quyết định được phê duyệt.

## 10. Những sai lầm thường gặp

- **Dùng khẩu hiệu thay cho tiêu chí:** “nhanh”, “ổn định”, “an toàn” không cho biết cách đo hoặc ngưỡng chấp nhận.
- **Chọn chỉ số dễ lấy thay vì chỉ số có ý nghĩa:** số lượng kiểm thử hoặc tỷ lệ bao phủ cao không trực tiếp chứng minh người dùng đạt được kết quả mong muốn.
- **Không định nghĩa mẫu số và trường hợp loại trừ:** tỷ lệ thành công có thể bị diễn giải khác nhau giữa nhóm sản phẩm, kiểm thử và vận hành.
- **Đặt ngưỡng không có dữ liệu:** một con số tùy ý có thể quá dễ, không khả thi hoặc không phản ánh trải nghiệm người dùng.
- **Chỉ đo giá trị trung bình:** phân phối có thể có phần đuôi chậm hoặc lỗi tập trung ở một nhóm nhỏ người dùng.
- **Chỉ xác nhận trước phát hành:** môi trường kiểm thử không thể đại diện hoàn toàn cho mọi điều kiện sản xuất; cần giám sát phù hợp.
- **Đặt quá nhiều mục tiêu:** danh sách dài nhưng không có chủ sở hữu hoặc hành động rõ ràng làm giảm khả năng tập trung.
- **Hạ ngưỡng để che giấu vấn đề:** thay đổi mục tiêu không có phân tích và phê duyệt làm mất khả năng so sánh và trách nhiệm giải trình.
- **Không kiểm tra đánh đổi:** tối ưu một chỉ số có thể làm xấu trải nghiệm, bảo mật, chi phí hoặc độ tin cậy ở nơi khác.

## 11. Mẫu ghi nhận mục tiêu chất lượng

Có thể dùng mẫu sau trong tài liệu yêu cầu hoặc hồ sơ xác nhận. Một mục tiêu nên có một bản ghi riêng.

| Trường | Nội dung cần điền |
|---|---|
| ID và tên mục tiêu | Mã định danh và tên ngắn, dễ nhận biết |
| Nhu cầu kinh doanh | Kết quả kinh doanh/người dùng mà mục tiêu hỗ trợ |
| Hành trình và phạm vi | Tác vụ, dịch vụ, nhóm người dùng và thành phần liên quan |
| Rủi ro | Hậu quả nếu mục tiêu không đạt |
| Thuộc tính chất lượng | Hiệu năng, độ tin cậy, bảo mật, khả dụng, dữ liệu hoặc thuộc tính khác |
| Điều kiện đo | Môi trường, tải, thiết bị, dữ liệu, phiên bản và cửa sổ thời gian |
| Chỉ số và công thức | Định nghĩa sự kiện, tử số/mẫu số, đơn vị, phân vị và trường hợp loại trừ |
| Ngưỡng chấp nhận | Giá trị mục tiêu, giới hạn và ngưỡng cảnh báo nếu có |
| Phương pháp xác nhận | Loại kiểm thử, phân tích, thử nghiệm người dùng hoặc giám sát |
| Bằng chứng | Báo cáo, kết quả pipeline, dashboard, biên bản hoặc liên kết hồ sơ |
| Chủ sở hữu/phê duyệt | Người duy trì chỉ số và người chấp nhận ngưỡng |
| Quyết định khi không đạt | Dừng phát hành, giảm phạm vi, giảm thiểu rủi ro, ngoại lệ có thời hạn hoặc kế hoạch sửa |
| Ngày rà soát | Thời điểm và sự kiện cần xem xét lại mục tiêu |

### Checklist rà soát

- [ ] Mục tiêu truy vết được đến một nhu cầu kinh doanh hoặc rủi ro đã xác định.
- [ ] Người dùng, hành trình và phạm vi áp dụng được mô tả rõ.
- [ ] Thuộc tính chất lượng được chọn có lý do.
- [ ] Điều kiện đo phản ánh môi trường và tải đại diện.
- [ ] Chỉ số, công thức, mẫu số, đơn vị và trường hợp loại trừ đã được thống nhất.
- [ ] Ngưỡng có căn cứ từ dữ liệu, kỳ vọng người dùng hoặc nghĩa vụ áp dụng.
- [ ] Có phương pháp xác nhận và bằng chứng cụ thể.
- [ ] Có chủ sở hữu, người phê duyệt và hành động khi mục tiêu không đạt.
- [ ] Các đánh đổi và rủi ro còn lại đã được ghi nhận.
- [ ] Có kế hoạch theo dõi sau phát hành và thời điểm rà soát lại.

## Kết luận

Chuyển nhu cầu kinh doanh thành mục tiêu chất lượng có thể kiểm chứng đòi hỏi hiểu đúng người dùng và hành trình, xác định rủi ro, chọn thuộc tính phù hợp, định nghĩa phép đo và thống nhất ngưỡng trong điều kiện rõ ràng. Mỗi mục tiêu cần liên kết với hoạt động xác nhận, bằng chứng, người chịu trách nhiệm và quyết định khi không đạt. Khi mối liên kết này được duy trì từ lúc hình thành yêu cầu đến vận hành, chiến lược kiểm thử có thể chứng minh chất lượng bằng kết quả cụ thể và hỗ trợ quyết định phát hành dựa trên rủi ro.
