# Chọn tổ hợp cấu hình theo rủi ro và tương tác cần kiểm chứng

## Mục tiêu bài học

Một sản phẩm có thể chạy trên nhiều hệ điều hành, trình duyệt, thiết bị, vai trò người dùng, ngôn ngữ, vùng dữ liệu, phương thức xác thực và cấu hình tính năng. Mỗi chiều cấu hình có thể có nhiều giá trị. Nếu kiểm thử mọi tổ hợp, số trường hợp tăng rất nhanh và thường vượt quá thời gian, môi trường và nhân lực sẵn có. Nếu chỉ chọn một vài tổ hợp thuận tiện, nhóm có thể bỏ sót lỗi chỉ xuất hiện khi các yếu tố tương tác với nhau.

Trong chiến lược VALIDATION_TESTING_STRATEGY, thiết kế bao phủ cần chọn tổ hợp cấu hình dựa trên rủi ro và tương tác cần kiểm chứng. Nhóm phải xác định những yếu tố nào có ảnh hưởng đến hành vi, tổ hợp nào hợp lệ, cặp hoặc nhóm yếu tố nào có thể gây lỗi, và những điều kiện nào có hậu quả đủ lớn để cần kiểm tra chuyên sâu. Các kỹ thuật như phân vùng tương đương, kiểm thử giá trị biên, pairwise và t-wise giúp giảm số trường hợp mà vẫn giữ được mức bao phủ có chủ đích.

Sau bài học, người học có thể:

- Xác định các chiều cấu hình và giá trị có ý nghĩa đối với sản phẩm.
- Giải thích vì sao kiểm thử toàn bộ tổ hợp thường không khả thi.
- Phân biệt kiểm thử một yếu tố, pairwise, t-wise và kiểm thử toàn bộ tổ hợp.
- Chọn tổ hợp theo rủi ro, tương tác, điều kiện biên và lịch sử lỗi.
- Áp dụng ràng buộc để loại tổ hợp không hợp lệ.
- Xây dựng bộ kiểm thử có thể truy vết, tái lập và cập nhật khi cấu hình thay đổi.
- Đánh giá giới hạn của pairwise và bổ sung kiểm thử chuyên sâu khi cần.

## 1. Vì sao cần thiết kế tổ hợp cấu hình?

Lỗi cấu hình thường không xuất hiện khi từng yếu tố được kiểm tra riêng lẻ. Một ứng dụng có thể hoạt động trên Chrome và Firefox, đồng thời hỗ trợ tiếng Việt và tiếng Anh, nhưng vẫn lỗi khi Firefox dùng tiếng Việt và người dùng có vai trò quản trị. Một API có thể hoạt động với từng phương thức xác thực, nhưng lỗi khi token hết hạn cùng lúc hệ thống bật một feature flag mới.

Các chiều cấu hình thường gặp:

- **Nền tảng:** hệ điều hành, phiên bản hệ điều hành, kiến trúc CPU, trình duyệt và phiên bản trình duyệt.
- **Thiết bị:** máy tính, điện thoại, máy tính bảng, kích thước màn hình, bộ nhớ và khả năng phần cứng.
- **Vai trò và quyền:** khách, nhân viên, quản lý, quản trị viên, quyền đọc/ghi hoặc quyền theo phạm vi dữ liệu.
- **Ngôn ngữ và vùng:** locale, múi giờ, tiền tệ, định dạng ngày giờ, quy tắc số và vùng pháp lý.
- **Xác thực và bảo mật:** mật khẩu, MFA, SSO, token, thời hạn phiên, chính sách cookie và quyền truy cập.
- **Dữ liệu và trạng thái:** dữ liệu rỗng, dữ liệu lớn, bản ghi cũ, trạng thái giao dịch, dữ liệu biên và dữ liệu không hợp lệ.
- **Cấu hình sản phẩm:** feature flag, gói dịch vụ, hạn mức, chế độ tương thích và cấu hình tenant.
- **Điều kiện vận hành:** mạng nhanh/chậm, mất kết nối, tải đồng thời, vùng triển khai và dịch vụ phụ thuộc.

Một lỗi có thể do một chiều riêng lẻ, nhưng nhiều lỗi khác xuất hiện do tương tác giữa hai hoặc nhiều chiều. Thiết kế tổ hợp giúp nhóm kiểm tra các tương tác có khả năng làm thay đổi hành vi thay vì chỉ kiểm tra danh sách giá trị một cách rời rạc.

## 2. Bùng nổ số lượng tổ hợp

Giả sử ứng dụng hỗ trợ:

- 3 hệ điều hành.
- 4 trình duyệt hoặc loại client.
- 3 vai trò.
- 2 ngôn ngữ.
- 2 phương thức xác thực.
- 3 trạng thái mạng.

Nếu mọi chiều đều độc lập và mọi giá trị đều có thể kết hợp, số tổ hợp là:

\[
3 \times 4 \times 3 \times 2 \times 2 \times 3 = 432
\]

Chỉ sáu chiều đã tạo ra 432 tổ hợp. Nếu mỗi tổ hợp cần nhiều kịch bản nghiệp vụ, thời gian kiểm thử còn tăng thêm. Trong thực tế, nhiều chiều có thể có hàng chục giá trị, hoặc tổ hợp còn phải chạy trên nhiều phiên bản dữ liệu và nhiều luồng nghiệp vụ.

Kiểm thử toàn bộ tổ hợp (exhaustive testing) có thể phù hợp khi số giá trị rất nhỏ hoặc hậu quả yêu cầu bằng chứng đầy đủ cho một phạm vi hẹp. Với hệ thống lớn, nhóm thường cần chiến lược giảm tổ hợp có căn cứ.

Cần phân biệt hai vấn đề:

1. **Bao phủ giá trị:** mỗi giá trị của từng chiều có được kiểm tra ít nhất một lần không?
2. **Bao phủ tương tác:** các cặp hoặc nhóm giá trị có khả năng ảnh hưởng lẫn nhau có được kiểm tra không?

Một bộ test có thể bao phủ tất cả giá trị riêng lẻ nhưng vẫn bỏ sót tương tác. Ví dụ, Chrome và Firefox đều được kiểm tra, tiếng Việt và tiếng Anh đều được kiểm tra, nhưng không có trường hợp Firefox kết hợp tiếng Việt.

## 3. Xác định chiều cấu hình và giá trị cần kiểm tra

Không nên đưa mọi thuộc tính có thể cấu hình vào ma trận ngay lập tức. Trước tiên, xác định yếu tố nào có khả năng làm thay đổi hành vi hoặc rủi ro của sản phẩm.

### 3.1. Lập danh sách chiều cấu hình

Với mỗi chiều, ghi lại tên, các giá trị, nguồn thông tin và phạm vi áp dụng.

| Chiều | Ví dụ giá trị | Vì sao có thể quan trọng |
|---|---|---|
| Trình duyệt | Chrome, Firefox, Safari, Edge | Khác biệt engine, cookie, font, API và cách hiển thị. |
| Hệ điều hành | Windows, macOS, Android, iOS | Khác biệt quyền, bàn phím, hệ thống tệp và khả năng thiết bị. |
| Vai trò | Khách, nhân viên, quản lý, quản trị viên | Quyền và dữ liệu được phép truy cập khác nhau. |
| Locale | vi-VN, en-US, ja-JP | Định dạng ngày, số, tiền tệ và độ dài văn bản khác nhau. |
| Phương thức xác thực | Mật khẩu, SSO, MFA | Khác biệt luồng đăng nhập, phiên và xử lý lỗi. |
| Trạng thái dữ liệu | Rỗng, bình thường, lớn, biên | Có thể kích hoạt nhánh xử lý hoặc giới hạn khác nhau. |
| Feature flag | Bật, tắt | Có thể thay đổi luồng, dữ liệu và khả năng tương thích. |
| Mạng | Ổn định, độ trễ cao, gián đoạn | Ảnh hưởng timeout, retry, đồng bộ và trải nghiệm. |

### 3.2. Chọn giá trị đại diện

Với chiều có nhiều giá trị, có thể nhóm thành các phân vùng tương đương nếu các giá trị trong nhóm được kỳ vọng có hành vi tương tự. Ví dụ, các phiên bản trình duyệt cùng engine và còn được hỗ trợ có thể được đại diện bằng một số phiên bản theo chính sách hỗ trợ. Tuy nhiên, phiên bản mới nhất và phiên bản cũ nhất còn được hỗ trợ thường cần được xem xét riêng.

Không nên gộp các giá trị chỉ vì chúng có tên gần nhau. Cần dựa trên hành vi, nền tảng, lịch sử lỗi và cam kết hỗ trợ. Các giá trị có khác biệt về quyền, bảo mật, locale hoặc giới hạn thường không nên bị gộp nếu khác biệt đó có thể ảnh hưởng kết quả.

### 3.3. Xác định miền giá trị và điều kiện biên

Mỗi chiều có thể cần giá trị đại diện và giá trị biên. Ví dụ:

- Dung lượng tải lên: 0 byte, dưới giới hạn, đúng giới hạn, vượt giới hạn.
- Số lượng bản ghi: 0, 1, số lượng thông thường, gần giới hạn, vượt giới hạn.
- Phiên đăng nhập: mới tạo, gần hết hạn, hết hạn, bị thu hồi.
- Kích thước màn hình: nhỏ nhất hỗ trợ, phổ biến, lớn nhất hỗ trợ.
- Phiên bản API: hiện tại, phiên bản trước còn được hỗ trợ và phiên bản sắp ngừng hỗ trợ.

Thiết kế tổ hợp không thay thế kiểm thử giá trị biên. Một ma trận pairwise có thể kết hợp các giá trị đại diện nhưng vẫn cần thêm trường hợp biên cho những chiều có ngưỡng nghiệp vụ hoặc kỹ thuật quan trọng.

## 4. Chọn mức bao phủ tương tác

### 4.1. Kiểm thử một yếu tố (single-factor)

Mỗi lần kiểm thử thay đổi một yếu tố trong khi các yếu tố còn lại giữ cố định. Cách này giúp phát hiện lỗi liên quan đến từng giá trị riêng lẻ và dễ xác định nguyên nhân.

Ví dụ, giữ trình duyệt Chrome, vai trò nhân viên, locale vi-VN và kiểm tra lần lượt các phương thức xác thực. Sau đó, có thể giữ các chiều khác cố định và đổi trình duyệt.

Ưu điểm là đơn giản và dễ chẩn đoán. Hạn chế là bỏ sót lỗi chỉ xuất hiện khi nhiều yếu tố kết hợp. Vì vậy, single-factor thường là nền tảng ban đầu, không phải chiến lược bao phủ tương tác đầy đủ.

### 4.2. Pairwise testing (bao phủ từng cặp)

Pairwise testing chọn các tổ hợp sao cho mọi cặp giá trị giữa hai chiều đều xuất hiện ít nhất một lần trong bộ kiểm thử. Ví dụ, nếu có chiều trình duyệt, vai trò và ngôn ngữ, bộ kiểm thử pairwise cần bao phủ mọi cặp:

- Trình duyệt × vai trò.
- Trình duyệt × ngôn ngữ.
- Vai trò × ngôn ngữ.

Giả định thực hành thường dùng là nhiều lỗi tương tác xuất hiện do một hoặc hai yếu tố kết hợp. Pairwise có thể giảm đáng kể số test so với exhaustive testing, nhưng không đảm bảo phát hiện lỗi cần ba hoặc nhiều yếu tố đồng thời.

Ví dụ với ba chiều nhị phân:

| Trường hợp | Trình duyệt | Vai trò | Ngôn ngữ |
|---|---|---|---|
| T1 | Chrome | Quản trị | vi-VN |
| T2 | Chrome | Nhân viên | en-US |
| T3 | Firefox | Quản trị | en-US |
| T4 | Firefox | Nhân viên | vi-VN |

Bốn trường hợp này bao phủ đủ bốn cặp giá trị của từng cặp chiều. Tuy nhiên, nếu có lỗi chỉ xảy ra khi Firefox + Quản trị + vi-VN + MFA, bộ pairwise trên chưa thể phát hiện vì nó không bao phủ tương tác bốn chiều đó.

### 4.3. T-wise testing

T-wise testing tổng quát hóa pairwise. Với mức t, bộ kiểm thử được thiết kế để mọi tổ hợp giá trị của mọi nhóm t chiều đều xuất hiện ít nhất một lần, trong phạm vi các ràng buộc hợp lệ.

- **2-wise:** bao phủ từng cặp.
- **3-wise:** bao phủ mọi tổ hợp của ba chiều.
- **4-wise:** bao phủ mọi tổ hợp của bốn chiều.

Mức t càng cao, số test thường càng tăng. Chọn t dựa trên độ phức tạp, lịch sử lỗi, hậu quả và tương tác đã biết. Không nên tăng t cho toàn bộ hệ thống nếu chỉ một số vùng có rủi ro tương tác cao.

### 4.4. Kiểm thử toàn bộ tổ hợp có chọn lọc

Với một vùng nhỏ nhưng có hậu quả nghiêm trọng, nhóm có thể kiểm thử toàn bộ các tổ hợp hợp lệ. Ví dụ, một ma trận quyền truy cập gồm ba vai trò và hai loại tài nguyên có thể đủ nhỏ để kiểm tra đầy đủ. Cách này phù hợp khi phạm vi giới hạn và việc bỏ sót tổ hợp không thể chấp nhận.

Có thể dùng exhaustive testing cho một nhóm chiều trọng yếu, đồng thời dùng pairwise hoặc t-wise cho phần còn lại.

## 5. Chọn tổ hợp theo rủi ro

Không phải mọi cặp hay mọi giá trị có tầm quan trọng như nhau. Một tổ hợp có thể cần ưu tiên cao nếu nó liên quan đến:

- Luồng nghiệp vụ cốt lõi như thanh toán, đăng nhập, phê duyệt hoặc ghi nhận giao dịch.
- Quyền truy cập, dữ liệu nhạy cảm, tenant isolation hoặc ranh giới bảo mật.
- Thiết bị, trình duyệt hoặc phiên bản được sử dụng phổ biến.
- Giá trị biên hoặc trạng thái lỗi có hậu quả lớn.
- Thay đổi mới, thành phần vừa tái cấu trúc hoặc phụ thuộc vừa nâng cấp.
- Lịch sử lỗi từng xuất hiện với tổ hợp tương tự.
- Tổ hợp có độ bất định cao hoặc khó phát hiện khi vận hành.

### 5.1. Đánh giá rủi ro cho tổ hợp

Có thể đánh giá từng tổ hợp hoặc nhóm tương tác theo các yếu tố:

| Yếu tố | Câu hỏi |
|---|---|
| Tác động | Nếu tổ hợp này lỗi, hậu quả đối với người dùng, dữ liệu hoặc nghiệp vụ là gì? |
| Khả năng xảy ra | Các giá trị này có tạo điều kiện dễ phát sinh lỗi không? |
| Mức phơi nhiễm | Có bao nhiêu người dùng, giao dịch hoặc môi trường sử dụng tổ hợp này? |
| Độ bất định | Thành phần hoặc tương tác đã được kiểm chứng trước đây chưa? |
| Khả năng phát hiện | Có thể phát hiện lỗi trước phát hành hay chỉ khi người dùng gặp? |
| Khả năng phục hồi | Có thể tắt tính năng, rollback hoặc khôi phục dữ liệu nhanh không? |

Nhóm có thể dùng thang định tính thấp/trung bình/cao hoặc quy đổi thành điểm để sắp xếp. Điểm số chỉ là công cụ hỗ trợ; cần ghi rõ giả định và không tạo độ chính xác giả tạo khi dữ liệu còn thiếu.

### 5.2. Tăng mức bao phủ ở vùng rủi ro cao

Một chiến lược thực tế có thể kết hợp:

- Pairwise cho các chiều cấu hình phổ biến.
- 3-wise cho nhóm tương tác có lịch sử lỗi hoặc độ phức tạp cao.
- Exhaustive testing cho ma trận nhỏ nhưng trọng yếu.
- Kiểm thử giá trị biên cho giới hạn và ngưỡng.
- Kiểm thử chuyên biệt cho bảo mật, hiệu năng, tương thích và phục hồi.
- Kiểm thử khám phá để tìm tương tác chưa được mô hình hóa.

Không nên coi một ma trận pairwise đạt là bằng chứng rằng mọi rủi ro đã được kiểm soát.

## 6. Xử lý ràng buộc và tổ hợp không hợp lệ

Trong thực tế, không phải mọi giá trị đều có thể kết hợp. Ví dụ:

- Một phương thức xác thực chỉ hỗ trợ trên trình duyệt hoặc nền tảng nhất định.
- Một tính năng chỉ có trong gói dịch vụ cao cấp.
- Một vai trò không được phép truy cập loại dữ liệu nhất định.
- Một phiên bản ứng dụng không hỗ trợ phiên bản API mới.
- Một chế độ thiết bị không có trên hệ điều hành cụ thể.

Những điều kiện này gọi là ràng buộc (constraints). Khi tạo tổ hợp, cần loại bỏ các trường hợp không hợp lệ theo quy tắc sản phẩm. Tuy nhiên, không được loại bỏ một tổ hợp chỉ vì nó khó kiểm thử hoặc ít phổ biến nếu đó là trạng thái hợp lệ mà người dùng có thể gặp.

### 6.1. Phân biệt không hợp lệ và không được hỗ trợ

- **Tổ hợp không hợp lệ:** sản phẩm không cho phép theo quy tắc nghiệp vụ hoặc kỹ thuật. Cần kiểm tra hệ thống từ chối hoặc xử lý đúng.
- **Tổ hợp không được hỗ trợ:** nằm ngoài cam kết hỗ trợ. Cần xác định sản phẩm phải từ chối rõ ràng, hiển thị thông báo hay có hành vi dự phòng.
- **Tổ hợp hợp lệ nhưng hiếm:** có thể ít được dùng nhưng vẫn cần xem xét theo rủi ro.
- **Tổ hợp chưa rõ:** cần làm rõ yêu cầu hoặc chính sách trước khi quyết định loại khỏi bộ kiểm thử.

Ví dụ, nếu MFA không hỗ trợ trên một thiết bị cũ, cần kiểm tra người dùng nhận được hướng dẫn phù hợp và không bị rơi vào trạng thái không thể đăng nhập. Không nên đơn giản xóa tổ hợp đó khỏi ma trận mà không xác minh hành vi từ chối.

### 6.2. Ghi ràng buộc một cách tường minh

Có thể mô tả ràng buộc bằng ngôn ngữ dễ hiểu:

~~~text
- Nếu platform = iOS, browser phải thuộc nhóm trình duyệt được hỗ trợ trên iOS.
- Nếu plan = Basic, advancedExport phải = false.
- Nếu role = Guest, accessLevel không được là Admin.
- Nếu authMethod = SSO, tenant phải có cấu hình identity provider.
~~~

Ràng buộc nên có nguồn căn cứ như yêu cầu, chính sách sản phẩm hoặc giới hạn kỹ thuật. Khi quy tắc thay đổi, ma trận tổ hợp cần được tạo lại hoặc rà soát.

## 7. Kết hợp pairwise với phân vùng tương đương và giá trị biên

Pairwise giải quyết tương tác giữa các chiều, còn phân vùng tương đương và giá trị biên giải quyết cách chọn giá trị trong từng chiều. Chúng bổ sung cho nhau.

Ví dụ với trường số lượng sản phẩm:

- Phân vùng hợp lệ: từ 1 đến 100.
- Phân vùng không hợp lệ: nhỏ hơn 1 và lớn hơn 100.
- Giá trị biên: 0, 1, 2, 99, 100, 101.

Nếu chỉ đưa một giá trị đại diện là 10 vào ma trận pairwise, các lỗi ở giới hạn 1 hoặc 100 có thể bị bỏ sót. Nhóm nên xác định bộ giá trị biên riêng rồi chọn cách kết hợp với các chiều quan trọng.

Một cách làm hiệu quả:

1. Xác định các phân vùng tương đương cho từng chiều.
2. Chọn giá trị đại diện trong mỗi phân vùng.
3. Bổ sung giá trị biên và trạng thái đặc biệt.
4. Xác định ràng buộc giữa các chiều.
5. Tạo bộ pairwise hoặc t-wise trên các giá trị đại diện hợp lệ.
6. Thêm các trường hợp biên hoặc tổ hợp rủi ro cao chưa được bao phủ.
7. Kiểm tra lại rằng mọi yêu cầu trọng yếu đều có bằng chứng.

## 8. Quy trình thiết kế bộ tổ hợp cấu hình

### Bước 1: Xác định mục tiêu và phạm vi

Mô tả chức năng, luồng nghiệp vụ hoặc rủi ro cần kiểm tra. Xác định phiên bản sản phẩm, môi trường và nhóm người dùng liên quan.

### Bước 2: Liệt kê chiều cấu hình

Ghi lại các yếu tố có thể ảnh hưởng đến hành vi: nền tảng, trình duyệt, vai trò, locale, xác thực, dữ liệu, feature flag và điều kiện vận hành.

### Bước 3: Chọn giá trị đại diện và biên

Dùng phân vùng tương đương để giảm số giá trị, nhưng giữ các phiên bản, trạng thái và ngưỡng có ý nghĩa. Xem xét giá trị phổ biến, hiếm nhưng quan trọng và các giá trị có lịch sử lỗi.

### Bước 4: Xác định ràng buộc

Loại tổ hợp không hợp lệ theo quy tắc đã được xác nhận. Ghi rõ tổ hợp không được hỗ trợ và hành vi từ chối cần kiểm tra.

### Bước 5: Đánh giá tương tác và rủi ro

Xác định những chiều có khả năng tương tác. Chọn mức 2-wise, 3-wise hoặc mức cao hơn cho vùng cần thiết. Đánh dấu các tổ hợp có hậu quả nghiêm trọng để kiểm tra riêng.

### Bước 6: Tạo và rà soát bộ tổ hợp

Dùng công cụ tạo covering array hoặc lập ma trận có kiểm soát. Kiểm tra mọi giá trị và cặp cần bao phủ, ràng buộc, dữ liệu và tính khả thi của môi trường.

### Bước 7: Gắn tổ hợp với kịch bản kiểm thử

Mỗi tổ hợp cần gắn với mục tiêu kiểm tra cụ thể. Không phải mọi tổ hợp đều cần chạy toàn bộ luồng E2E; có thể dùng unit, API, integration hoặc kiểm tra giao diện tùy rủi ro.

### Bước 8: Thực thi và lưu bằng chứng

Lưu cấu hình, phiên bản, dữ liệu, môi trường, kết quả và lỗi. Bảo đảm có thể tái lập tổ hợp khi test thất bại.

### Bước 9: Cập nhật khi sản phẩm thay đổi

Khi thêm trình duyệt, vai trò, phương thức xác thực hoặc feature flag, rà soát lại ma trận và các ràng buộc. Không tiếp tục dùng bộ tổ hợp cũ nếu nó không còn đại diện cho cấu hình được hỗ trợ.

## 9. Ví dụ thực tế: ứng dụng quản lý đơn hàng

Một ứng dụng quản lý đơn hàng được sử dụng trên trình duyệt máy tính và thiết bị di động. Nhóm cần kiểm tra màn hình chi tiết đơn hàng với các chiều:

- Platform: Desktop, Mobile.
- Browser: Chrome, Firefox, Safari.
- Role: Staff, Manager.
- Locale: vi-VN, en-US.
- Auth: Password, SSO.

Nếu tạo mọi tổ hợp, có 2 × 3 × 2 × 2 × 2 = 48 trường hợp trước khi tính đến dữ liệu và trạng thái mạng. Nhóm xác định ràng buộc: Safari chỉ được hỗ trợ trên các nền tảng phù hợp; SSO chỉ bật cho tenant có cấu hình identity provider.

Nhóm chọn cách tiếp cận:

1. Kiểm tra mọi role với các hành động nhạy cảm như xem, sửa và hoàn tiền ở API/service test.
2. Dùng pairwise cho các chiều platform, browser, locale và auth trong phạm vi tổ hợp hợp lệ.
3. Bổ sung 3-wise cho các tương tác có rủi ro cao như browser × locale × auth nếu lịch sử lỗi cho thấy vấn đề về cookie, redirect hoặc định dạng.
4. Kiểm tra giá trị biên với đơn hàng có tổng tiền bằng 0, rất lớn hoặc có nhiều loại tiền tệ nếu sản phẩm hỗ trợ.
5. Giữ một số E2E đại diện cho nhân viên và quản lý để xác minh hành trình thực tế.
6. Chạy kiểm tra bảo mật chuyên biệt cho quyền hoàn tiền và tenant isolation.

Nhóm không cần chạy mọi trường hợp E2E trên tất cả 48 tổ hợp. Mỗi loại kiểm tra được đặt ở tầng phù hợp với rủi ro. Nếu lỗi xuất hiện trên Safari với SSO và locale vi-VN, nhóm lưu lại tổ hợp chính xác để tái hiện, sau đó xem xét tăng mức bao phủ cho các tương tác liên quan.

## 10. Dùng covering array và công cụ tạo tổ hợp

Với nhiều chiều và ràng buộc phức tạp, nhóm có thể dùng công cụ sinh tổ hợp theo pairwise hoặc t-wise. Kết quả thường được gọi là covering array: một tập test được thiết kế để bao phủ mọi nhóm giá trị có kích thước t trong các tổ hợp hợp lệ.

Công cụ giúp giảm lỗi khi lập ma trận thủ công, nhưng không tự biết rủi ro nghiệp vụ. Người thiết kế vẫn phải:

- Chọn chiều và giá trị đúng.
- Xác định ràng buộc hợp lệ.
- Chọn mức t phù hợp.
- Bổ sung trường hợp biên và tổ hợp rủi ro cao.
- Kiểm tra kết quả sinh ra có thể chạy trong môi trường thật.
- Đảm bảo mỗi tổ hợp có dữ liệu và kịch bản cần thiết.

Không nên chọn công cụ chỉ vì nó tạo ra ít test nhất. Mục tiêu là bộ kiểm thử nhỏ nhất có thể đáp ứng mức bằng chứng cần thiết, không phải tối thiểu số lượng bằng mọi giá.

## 11. Tái lập và quản lý kết quả kiểm thử

Một test thất bại chỉ hữu ích khi nhóm có thể tái hiện và xác định điều kiện xảy ra. Với kiểm thử cấu hình, cần lưu:

- Mã test hoặc tên kịch bản.
- Các chiều và giá trị cấu hình.
- Phiên bản ứng dụng, build và commit.
- Hệ điều hành, trình duyệt, thiết bị và phiên bản.
- Feature flag, vai trò, locale và phương thức xác thực.
- Dữ liệu đầu vào và trạng thái ban đầu.
- Môi trường, cấu hình mạng và phụ thuộc liên quan.
- Kết quả mong đợi, kết quả thực tế, log và bằng chứng.
- Mức rủi ro và lý do chọn tổ hợp.

Tránh lưu token, mật khẩu hoặc dữ liệu cá nhân trong log và báo cáo. Có thể lưu mã tham chiếu hoặc dữ liệu đã ẩn danh để tái lập trong môi trường kiểm thử an toàn.

Khi một tổ hợp không còn được hỗ trợ, cần cập nhật ma trận và ghi nhận quyết định. Không nên âm thầm bỏ một cấu hình khỏi bộ kiểm thử vì nó thường xuyên thất bại; cần xác định lỗi sản phẩm, môi trường hay chính sách hỗ trợ.

## 12. Đo lường chất lượng bao phủ

Một số chỉ số hữu ích:

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Giá trị được bao phủ | Tỷ lệ giá trị của từng chiều đã được kiểm tra. | Phát hiện giá trị cấu hình chưa có bằng chứng. |
| Bao phủ cặp hoặc t-wise | Tỷ lệ cặp/nhóm giá trị hợp lệ đã xuất hiện trong bộ test. | Đánh giá mức bao phủ tương tác theo thiết kế. |
| Bao phủ rủi ro | Tỷ lệ rủi ro quan trọng có tổ hợp và kịch bản kiểm tra. | Bảo đảm bộ test phản ánh hậu quả và lịch sử lỗi. |
| Tỷ lệ lỗi theo tổ hợp | Lỗi phát hiện theo nền tảng, vai trò, locale hoặc nhóm tương tác. | Nhận diện cấu hình có vấn đề lặp lại. |
| Thời gian chạy | Chi phí thực thi bộ tổ hợp. | Cân bằng độ sâu và phản hồi pipeline. |
| Khả năng tái lập | Tỷ lệ lỗi có thể tái hiện từ thông tin cấu hình đã lưu. | Đánh giá chất lượng dữ liệu và môi trường kiểm thử. |

Không nên chỉ báo cáo “đã chạy 100 test”. Cần cho biết 100 test đó bao phủ chiều nào, cặp nào, rủi ro nào và các tổ hợp nào chưa được kiểm tra. Bao phủ pairwise 100% không đồng nghĩa với bao phủ mọi lỗi có thể xảy ra.

## 13. Những sai lầm thường gặp

- **Chỉ kiểm tra từng giá trị riêng lẻ:** bỏ sót lỗi do tương tác giữa các chiều.
- **Dùng pairwise như bảo đảm tuyệt đối:** lỗi ba chiều hoặc nhiều chiều vẫn có thể bị bỏ qua.
- **Chọn tổ hợp ngẫu nhiên không có căn cứ:** khó chứng minh rủi ro quan trọng đã được bao phủ.
- **Gộp giá trị khác biệt về hành vi:** có thể che khuất lỗi phiên bản, quyền hoặc locale.
- **Loại tổ hợp khó chạy mà không xác nhận:** có thể bỏ qua một cấu hình hợp lệ mà người dùng vẫn sử dụng.
- **Bỏ qua giá trị biên:** ma trận tương tác không tự động bao phủ các ngưỡng dữ liệu.
- **Tạo ma trận nhưng không gắn kịch bản:** biết cấu hình nào được chạy nhưng không biết điều gì đã được xác minh.
- **Chạy mọi tổ hợp bằng E2E:** làm bộ kiểm thử chậm, tốn tài nguyên và khó bảo trì.
- **Không lưu cấu hình chính xác:** lỗi không thể tái hiện khi phiên bản trình duyệt hoặc feature flag đã thay đổi.
- **Không cập nhật ma trận khi sản phẩm thay đổi:** bộ kiểm thử dần mất tính đại diện.
- **Chỉ tối ưu số lượng test:** giảm test nhưng bỏ rơi tương tác rủi ro cao không phải là cải thiện.

## 14. Checklist trước khi chốt bộ tổ hợp

- [ ] Mục tiêu kiểm thử và rủi ro cần xác minh đã được xác định.
- [ ] Các chiều cấu hình có ảnh hưởng đến hành vi đã được liệt kê.
- [ ] Giá trị đại diện, phân vùng tương đương và giá trị biên đã được chọn.
- [ ] Các ràng buộc hợp lệ và không được hỗ trợ đã được ghi rõ.
- [ ] Mức bao phủ single-factor, pairwise hoặc t-wise phù hợp với rủi ro.
- [ ] Các tương tác ba chiều hoặc nhiều chiều có rủi ro cao được kiểm tra riêng.
- [ ] Tổ hợp không hợp lệ có hành vi từ chối hoặc thông báo được xác minh khi cần.
- [ ] Mỗi tổ hợp được gắn với kịch bản và tầng kiểm thử phù hợp.
- [ ] Môi trường, dữ liệu và cấu hình có thể tái lập.
- [ ] Kết quả được lưu cùng phiên bản, cấu hình và bằng chứng.
- [ ] Có kế hoạch cập nhật ma trận khi cấu hình sản phẩm thay đổi.
- [ ] Báo cáo nêu rõ phần đã bao phủ và phần còn rủi ro.

## Kết luận

Thiết kế tổ hợp cấu hình cần bắt đầu từ các chiều có thể làm thay đổi hành vi, ràng buộc hợp lệ và rủi ro của tương tác. Kiểm thử từng yếu tố giúp xác minh giá trị riêng; pairwise và t-wise giúp mở rộng bao phủ tương tác với chi phí thấp hơn exhaustive testing; các tổ hợp nhỏ nhưng trọng yếu có thể được kiểm tra đầy đủ. Không có kỹ thuật giảm tổ hợp nào thay thế đánh giá rủi ro, giá trị biên và bằng chứng chuyên biệt. Bộ kiểm thử tốt cần có lý do lựa chọn rõ ràng, gắn từng tổ hợp với mục tiêu, có thể tái lập và được cập nhật cùng sản phẩm.
