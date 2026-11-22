# Theo dõi rủi ro còn lại sau khi thực hiện các hoạt động kiểm chứng

## 1. Vì sao rủi ro vẫn còn sau kiểm chứng?

Hoạt động kiểm chứng như kiểm thử, rà soát thiết kế, phân tích mã nguồn, kiểm tra bảo mật, thử nghiệm với người dùng hoặc diễn tập khôi phục giúp thu thập bằng chứng về chất lượng sản phẩm. Tuy nhiên, kết quả kiểm chứng không thể chứng minh rằng mọi lỗi đều đã được tìm thấy hoặc mọi điều kiện vận hành đều đã được mô phỏng. Rủi ro có thể vẫn tồn tại do phạm vi kiểm thử giới hạn, dữ liệu chưa đại diện, môi trường khác sản xuất, phụ thuộc bên ngoài, thay đổi mới hoặc những tình huống chưa được nhận diện.

**Rủi ro còn lại (residual risk)** là phần rủi ro vẫn tồn tại sau khi đã áp dụng các biện pháp xử lý và kiểm chứng. Theo dõi rủi ro còn lại giúp nhóm hiểu điều gì vẫn có thể xảy ra, hậu quả có thể là gì, tín hiệu nào cho thấy rủi ro đang tăng và ai phải hành động khi điều kiện thay đổi.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, theo dõi rủi ro còn lại nối kết quả kiểm chứng với quyết định phát hành và vận hành. Một báo cáo kiểm thử chỉ nêu số ca đạt/trượt chưa đủ để trả lời liệu sản phẩm có an toàn để phát hành hay không. Cần biết những rủi ro nào đã giảm, rủi ro nào chưa giảm, giới hạn của bằng chứng và rủi ro nào được chấp nhận có điều kiện.

Ví dụ, kiểm thử tải đạt ngưỡng trong môi trường gần sản xuất là bằng chứng tốt cho kịch bản đã chạy. Nó không tự chứng minh hệ thống chịu được lưu lượng tăng gấp nhiều lần, sự cố đồng thời ở nhiều vùng hoặc hành vi bất thường của nhà cung cấp. Những khoảng trống này phải được ghi nhận và theo dõi theo mức tác động.

## 2. Phân biệt rủi ro vốn có, rủi ro còn lại và vấn đề đã xảy ra

Ba khái niệm cần được dùng nhất quán:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Rủi ro vốn có (inherent risk) | Mức rủi ro trước khi xét đến các biện pháp kiểm soát cụ thể | Nếu xử lý retry thanh toán sai, người mua có thể bị thu tiền hai lần |
| Rủi ro còn lại (residual risk) | Mức rủi ro sau khi đã áp dụng kiểm soát và đánh giá bằng chứng | Cơ chế idempotency và đối soát đã được kiểm thử, nhưng vẫn còn khả năng lỗi do phản hồi không nhất quán từ nhà cung cấp |
| Vấn đề/sự cố (issue/incident) | Sự kiện đã xảy ra và cần được xử lý | Đã phát sinh giao dịch thu tiền trùng trong môi trường thật |

Rủi ro thường được diễn đạt dưới dạng nguyên nhân, sự kiện có thể xảy ra và hậu quả: “Do [nguyên nhân], [sự kiện] có thể xảy ra, dẫn đến [hậu quả]”. Cách viết này giúp nhóm xác định biện pháp kiểm soát và chỉ báo phù hợp.

Ví dụ: “Do dữ liệu kiểm thử không bao phủ các bản ghi cũ có định dạng bất thường, quá trình chuyển đổi có thể bỏ sót một số trường, dẫn đến sai lệch hồ sơ khách hàng sau phát hành.”

Khi sự kiện đã xảy ra, cần mở quy trình xử lý lỗi hoặc sự cố, đồng thời cập nhật hồ sơ rủi ro nếu nguyên nhân có thể tiếp tục gây ra các sự kiện khác. Không dùng trạng thái “rủi ro” để thay thế việc quản lý một lỗi đã biết.

### 2.1. Rủi ro còn lại không đồng nghĩa với lỗi chưa sửa

Lỗi đã biết là một nguồn rủi ro, nhưng rủi ro còn lại rộng hơn. Một hệ thống có thể không còn lỗi nghiêm trọng đã biết mà vẫn có rủi ro do:

- Những nhánh xử lý chưa được kiểm thử hoặc chỉ được kiểm tra với ít dữ liệu.
- Khác biệt giữa môi trường kiểm thử và môi trường sản xuất.
- Hệ thống bên ngoài, nhà cung cấp hoặc thiết bị người dùng nằm ngoài quyền kiểm soát.
- Giới hạn của công cụ, dữ liệu quan sát hoặc phương pháp kiểm chứng.
- Thay đổi cấu hình, tải, kiến trúc hoặc yêu cầu sau khi kiểm thử.
- Hành vi mới phát sinh khi nhiều thành phần tương tác đồng thời.

Do đó, danh sách lỗi đã đóng không thể thay thế hồ sơ rủi ro. Ngược lại, một lỗi đã được chấp nhận có điều kiện vẫn phải có liên kết với rủi ro, biện pháp giảm thiểu và thời hạn xử lý.

## 3. Đánh giá rủi ro sau khi kiểm chứng

### 3.1. Xác định rủi ro và phạm vi ảnh hưởng

Mỗi rủi ro nên có một phát biểu cụ thể, chỉ rõ nguyên nhân, sự kiện và hậu quả. Xác định thành phần, luồng nghiệp vụ, nhóm người dùng, loại dữ liệu, phiên bản và môi trường liên quan. Tránh ghi chung chung như “hệ thống có thể không ổn định” hoặc “có rủi ro bảo mật”.

Ví dụ cụ thể hơn: “Khi dịch vụ định danh phản hồi chậm và ứng dụng gửi lại yêu cầu, trạng thái phiên có thể được cập nhật không đồng nhất giữa hai dịch vụ, khiến người dùng phải đăng nhập lại hoặc một thao tác được thực hiện lặp.”

### 3.2. Đánh giá khả năng xảy ra và tác động

Đánh giá rủi ro cần xét ít nhất hai chiều: khả năng sự kiện xảy ra và mức độ hậu quả nếu xảy ra. Có thể bổ sung khả năng phát hiện, khả năng khôi phục, phạm vi ảnh hưởng và mức độ không chắc chắn. Dùng thang đo nhất quán trong tổ chức, chẳng hạn thấp, trung bình, cao và nghiêm trọng.

| Mức | Khả năng xảy ra - ví dụ diễn giải | Tác động - ví dụ diễn giải |
|---|---|---|
| Thấp | Hiếm gặp trong điều kiện đã quan sát; có nhiều lớp kiểm soát đáng tin cậy | Ảnh hưởng nhỏ, cục bộ, dễ khôi phục và không tác động đáng kể đến người dùng |
| Trung bình | Có thể xảy ra khi một số điều kiện nhất định xuất hiện | Làm gián đoạn một phần hành trình, cần can thiệp hoặc khắc phục có kế hoạch |
| Cao | Đã xuất hiện trong kiểm thử/vận hành hoặc điều kiện kích hoạt tương đối phổ biến | Ảnh hưởng đáng kể đến nhiều người dùng, dữ liệu, hoạt động hoặc cam kết dịch vụ |
| Nghiêm trọng | Có điều kiện kích hoạt rõ ràng, kiểm soát yếu hoặc dấu hiệu sự kiện có thể lặp lại | Có thể gây mất dữ liệu, thiệt hại tài chính lớn, vi phạm bảo mật/tuân thủ hoặc gián đoạn diện rộng |

Đây là thang tham khảo. Tổ chức cần định nghĩa ngưỡng và ví dụ theo sản phẩm. Nếu dùng ma trận xác suất/tác động, hãy lưu cả hai mức thành phần và lý do đánh giá. Điểm số tổng hợp không được che khuất hậu quả nghiêm trọng hoặc yêu cầu bắt buộc.

Không nên gán xác suất chính xác khi không có dữ liệu hỗ trợ. Có thể ghi “chưa đủ dữ liệu”, nêu giả định và lên kế hoạch thu thập thêm bằng chứng. Thiếu dữ liệu không đồng nghĩa với xác suất thấp.

### 3.3. Đánh giá lại hiệu quả của biện pháp kiểm soát

Sau khi thực hiện kiểm thử hoặc biện pháp giảm thiểu, cần xác định kiểm soát đã thực sự làm giảm rủi ro đến đâu. Hãy kiểm tra:

- Kiểm soát có được triển khai đúng trên phiên bản và môi trường mục tiêu không?
- Hoạt động kiểm chứng có bao phủ đúng tình huống và điều kiện kích hoạt rủi ro không?
- Kết quả có lặp lại được và có đủ dữ liệu để đưa ra kết luận không?
- Có lỗi, ngoại lệ, kiểm thử bị bỏ qua hoặc kiểm thử không ổn định nào làm giảm độ tin cậy của bằng chứng không?
- Kiểm soát có thể bị vô hiệu hóa bởi cấu hình, quyền truy cập, thay đổi hoặc phụ thuộc bên ngoài không?
- Có tín hiệu vận hành nào cho thấy rủi ro vẫn đang xảy ra hoặc có xu hướng tăng không?

Một kiểm thử đạt chỉ hỗ trợ kết luận trong phạm vi điều kiện đã chạy. Nếu kiểm thử chỉ mô phỏng một nhà cung cấp trong sandbox, không nên kết luận mọi tình huống lỗi của nhà cung cấp thật đã được loại trừ. Ghi rõ giới hạn này trong đánh giá rủi ro còn lại.

### 3.4. Xác định mức rủi ro còn lại

Đánh giá lại khả năng xảy ra và tác động sau khi xét hiệu quả kiểm soát. So sánh với mức chấp nhận rủi ro (risk appetite/tolerance) đã được tổ chức hoặc chủ sở hữu sản phẩm thống nhất. Kết quả cần phân loại rõ:

- **Được kiểm soát trong ngưỡng:** bằng chứng hiện có cho thấy rủi ro còn lại nằm trong mức chấp nhận và có cơ chế theo dõi phù hợp.
- **Chấp nhận có điều kiện:** rủi ro được chấp nhận trong phạm vi, thời hạn và điều kiện cụ thể, kèm kiểm soát bổ sung và người phê duyệt.
- **Cần giảm thiểu thêm:** biện pháp hiện tại chưa đủ; cần kiểm thử bổ sung, thay đổi thiết kế, giới hạn phát hành hoặc tăng kiểm soát.
- **Không chấp nhận:** rủi ro vượt ngưỡng hoặc vi phạm điều kiện bắt buộc; cần dừng phát hành, thu hẹp phạm vi hay chuyển cấp quyết định.

Không tự động hạ mức rủi ro chỉ vì số ca kiểm thử đạt tăng lên. Cần xem xét chất lượng kiểm thử, độ bao phủ theo rủi ro, tính đại diện của dữ liệu và bằng chứng từ môi trường thật.

## 4. Liên kết rủi ro với kiểm soát và bằng chứng

Hồ sơ rủi ro cần truy vết được từ nguyên nhân đến quyết định xử lý. Một chuỗi liên kết hữu ích là:

```text
Nhu cầu / mục tiêu chất lượng
          |
          v
Rủi ro (nguyên nhân -> sự kiện -> hậu quả)
          |
          v
Biện pháp phòng ngừa / phát hiện / khôi phục
          |
          v
Hoạt động kiểm chứng và tiêu chí đạt
          |
          v
Bằng chứng, giới hạn và kết quả
          |
          v
Đánh giá rủi ro còn lại
          |
          v
Chấp nhận / giảm thiểu / giới hạn / dừng phát hành
          |
          v
Chỉ báo, ngưỡng và hành động theo dõi
```

| Thành phần | Câu hỏi cần trả lời | Ví dụ bằng chứng |
|---|---|---|
| Rủi ro | Điều gì có thể xảy ra và hậu quả là gì? | Hồ sơ rủi ro gắn với luồng nghiệp vụ và tài sản liên quan |
| Kiểm soát | Điều gì ngăn ngừa, phát hiện hoặc giảm hậu quả? | Cơ chế idempotency, phân quyền, giới hạn tải, sao lưu |
| Kiểm chứng | Kiểm soát được xác nhận bằng cách nào? | Kiểm thử tích hợp, kiểm thử âm tính, kiểm thử tải, diễn tập phục hồi |
| Kết quả | Điều kiện nào đã đạt hoặc chưa đạt? | Báo cáo chạy, log, dữ liệu đối chiếu, biên bản rà soát |
| Giới hạn | Bằng chứng không bao phủ điều gì? | Môi trường, phiên bản, tải, dữ liệu hoặc nhánh chưa kiểm tra |
| Rủi ro còn lại | Sau kiểm soát, rủi ro ở mức nào và tại sao? | Đánh giá khả năng, tác động, giả định và mức không chắc chắn |
| Theo dõi | Tín hiệu nào cho biết rủi ro thay đổi? | Chỉ báo rủi ro, ngưỡng cảnh báo, người trực và quy trình xử lý |

Nếu một kiểm soát quan trọng chưa được xác nhận, hồ sơ phải thể hiện rõ. Không đánh dấu kiểm soát là hiệu quả chỉ vì tài liệu thiết kế nói rằng nó tồn tại; cần có bằng chứng triển khai và vận hành phù hợp.

## 5. Thiết kế chỉ báo để theo dõi rủi ro còn lại

Rủi ro còn lại cần được theo dõi bằng tín hiệu có thể quan sát, có nguồn dữ liệu và có hành động tương ứng. Có thể kết hợp chỉ báo dẫn dắt (leading indicators), cảnh báo sớm về điều kiện có thể làm rủi ro tăng, với chỉ báo kết quả (lagging indicators), phản ánh sự kiện đã xảy ra.

| Nhóm rủi ro | Chỉ báo có thể theo dõi | Hành động khi tín hiệu xấu đi |
|---|---|---|
| Chất lượng chức năng | Lỗi nghiêm trọng sau phát hành, tỷ lệ giao dịch thất bại, lỗi lặp lại ở luồng trọng yếu | Phân tích nguyên nhân, bổ sung kiểm thử hồi quy, giới hạn hoặc tắt luồng bị ảnh hưởng |
| Hiệu năng và tải | p95/p99 độ trễ, thông lượng, tỷ lệ timeout, mức sử dụng tài nguyên | Điều chỉnh năng lực, giới hạn tải, tối ưu điểm nghẽn và chạy lại kiểm thử đại diện |
| Độ tin cậy | Tỷ lệ lỗi dịch vụ, thời gian gián đoạn, số lần vượt SLO, thời gian khôi phục | Kích hoạt quy trình sự cố, đánh giá error budget, kiểm tra dự phòng và phục hồi |
| Bảo mật và riêng tư | Lỗ hổng mới, cảnh báo truy cập bất thường, lỗi phân quyền, thay đổi phụ thuộc có rủi ro | Đánh giá mức nghiêm trọng, vá lỗi, thu hồi quyền hoặc tạm dừng tính năng liên quan |
| Toàn vẹn dữ liệu | Sai lệch đối soát, bản ghi không hợp lệ, sự kiện trùng, lỗi di trú | Dừng xử lý lô bị ảnh hưởng, đối soát, khôi phục hoặc chạy quy trình sửa dữ liệu có kiểm soát |
| Tích hợp bên ngoài | Tỷ lệ phản hồi lỗi, timeout, độ trễ và thay đổi hợp đồng API | Kích hoạt retry có kiểm soát, hàng đợi dự phòng, quy trình đối soát và trao đổi với nhà cung cấp |
| Khả năng phục hồi | Kết quả sao lưu, thời gian khôi phục thực tế, lỗi diễn tập, độ mới bản sao | Sửa quy trình sao lưu, diễn tập lại và đánh giá khả năng đáp ứng RTO/RPO |
| Độ tin cậy của kiểm thử | Tỷ lệ kiểm thử chập chờn, kiểm thử bị bỏ qua, thời gian phản hồi pipeline | Sửa kiểm thử, khôi phục cổng kiểm tra và đánh giá lại mức tin cậy của bằng chứng |

Chỉ báo cần có định nghĩa cụ thể. Ví dụ, “tỷ lệ giao dịch thất bại” phải phân biệt lỗi kỹ thuật với giao dịch bị từ chối hợp lệ bởi ngân hàng hoặc người dùng chủ động hủy. Nếu định nghĩa thay đổi, phải ghi lại thời điểm và cách điều chỉnh để so sánh xu hướng không bị sai lệch.

### 5.1. Đặt ngưỡng cảnh báo và ngưỡng hành động

Mỗi chỉ báo quan trọng nên có ít nhất:

- **Mức nền:** giá trị hoặc xu hướng thông thường trong điều kiện đã xác định.
- **Ngưỡng cảnh báo:** tín hiệu cho biết rủi ro đang tăng và cần điều tra.
- **Ngưỡng hành động:** điều kiện yêu cầu thực hiện biện pháp cụ thể, như giảm tải, tắt tính năng, dừng phát hành hoặc kích hoạt ứng phó sự cố.
- **Cửa sổ đo:** khoảng thời gian và cách tổng hợp để tránh phản ứng quá mức với một mẫu đơn lẻ hoặc bỏ qua xu hướng kéo dài.
- **Chủ sở hữu và thời gian phản hồi:** người nhận cảnh báo, thời gian đánh giá và kênh xử lý.

Ngưỡng nên dựa trên mục tiêu chất lượng, dữ liệu nền, mức rủi ro và khả năng phản ứng. Ví dụ, một dịch vụ có SLO về tỷ lệ yêu cầu thành công có thể dùng tốc độ tiêu thụ error budget làm tín hiệu cảnh báo. Khi error budget bị tiêu thụ nhanh, nhóm cần giảm tốc độ thay đổi hoặc ưu tiên độ tin cậy theo chính sách vận hành.

Không nên đặt ngưỡng tùy ý hoặc tạo cảnh báo không có người xử lý. Cảnh báo quá nhạy gây mệt mỏi; cảnh báo quá lỏng khiến nhóm phát hiện muộn. Cần rà soát ngưỡng bằng dữ liệu thực tế và sau mỗi sự cố đáng kể.

### 5.2. Theo dõi cả tín hiệu dẫn dắt và tín hiệu kết quả

Chỉ báo dẫn dắt có thể gồm số thay đổi lớn chưa qua kiểm thử ảnh hưởng, số phụ thuộc sắp hết hỗ trợ, tỷ lệ kiểm thử bị bỏ qua, dung lượng tài nguyên còn lại, độ mới bản sao lưu hoặc số ngoại lệ chưa hết hạn. Những tín hiệu này cho phép hành động trước khi sự cố xảy ra.

Chỉ báo kết quả có thể gồm lỗi lọt ra sản xuất, vi phạm SLO, mất dữ liệu, giao dịch sai, sự cố bảo mật hoặc thời gian khôi phục thực tế. Chúng phản ánh rủi ro đã hiện thực hóa và cần được dùng để cập nhật đánh giá, kiểm soát và kế hoạch kiểm thử.

Một chỉ báo đơn lẻ hiếm khi đủ. Ví dụ, số lỗi sản xuất giảm có thể do ít phát hành hơn chứ không nhất thiết do chất lượng tốt lên. Hãy đọc chỉ báo cùng tần suất thay đổi, mức sử dụng, phạm vi kiểm thử và phản hồi người dùng.

## 6. Quản lý hành động xử lý rủi ro

Khi theo dõi cho thấy rủi ro vượt ngưỡng hoặc biện pháp kiểm soát không còn hiệu quả, cần xác định hành động. Các chiến lược xử lý thường gồm:

| Chiến lược | Ý nghĩa | Ví dụ |
|---|---|---|
| Tránh rủi ro | Thay đổi kế hoạch hoặc loại bỏ điều kiện gây rủi ro | Không phát hành tính năng chưa đáp ứng yêu cầu bảo mật bắt buộc |
| Giảm thiểu | Giảm khả năng xảy ra hoặc mức độ hậu quả | Bổ sung kiểm tra quyền, kiểm thử hồi quy, giới hạn tốc độ hoặc đối soát |
| Chuyển giao/chia sẻ | Phân bổ một phần trách nhiệm hoặc tác động qua hợp đồng/bảo hiểm/dịch vụ | Thỏa thuận trách nhiệm và mức dịch vụ với nhà cung cấp; vẫn phải quản lý rủi ro tích hợp còn lại |
| Chấp nhận | Có thẩm quyền quyết định giữ rủi ro trong giới hạn đã thống nhất | Chấp nhận lỗi hiển thị nhỏ trong phạm vi người dùng hạn chế, có thời hạn sửa và theo dõi |

Chuyển giao rủi ro không có nghĩa là loại bỏ trách nhiệm của tổ chức đối với người dùng hoặc dữ liệu. Chấp nhận rủi ro cũng không phải là bỏ qua theo mặc định; cần nêu lý do, phạm vi, người phê duyệt, thời hạn và điều kiện xem xét lại.

Mỗi hành động cần có chủ sở hữu, thời hạn, tiêu chí hoàn tất và bằng chứng xác nhận hiệu quả. Nếu hành động là bổ sung kiểm thử, phải ghi rõ kịch bản, dữ liệu, môi trường, tiêu chí đạt và cách cập nhật đánh giá rủi ro sau khi có kết quả.

### 6.1. Điều kiện kích hoạt xem xét lại

Không chờ đến kỳ rà soát định kỳ nếu có thay đổi đáng kể. Các điều kiện kích hoạt thường gồm:

- Xuất hiện lỗi nghiêm trọng, sự cố, khiếu nại có xu hướng hoặc vi phạm SLO.
- Chỉ báo vượt ngưỡng cảnh báo/hành động hoặc có xu hướng xấu đi liên tục.
- Thay đổi kiến trúc, dữ liệu, cấu hình, quyền truy cập, tải hoặc nhà cung cấp.
- Có lỗ hổng bảo mật mới, yêu cầu pháp lý mới hoặc thay đổi nghĩa vụ hợp đồng.
- Kiểm soát bị tắt, không hoạt động, mất dữ liệu giám sát hoặc kiểm thử quan trọng bị bỏ qua.
- Môi trường sản xuất khác đáng kể so với giả định dùng khi kiểm chứng.
- Rủi ro được chấp nhận có điều kiện sắp hết hạn hoặc không còn đáp ứng điều kiện chấp thuận.

Khi có trigger, chủ sở hữu cần xác định phạm vi ảnh hưởng, cập nhật mức rủi ro, quyết định hành động và thông báo cho người chịu trách nhiệm phát hành/vận hành.

## 7. Vai trò và cơ chế chấp nhận rủi ro

Theo dõi rủi ro cần có trách nhiệm rõ ràng. Vai trò có thể được tổ chức khác nhau, nhưng cần xác định tối thiểu:

| Vai trò | Trách nhiệm chính |
|---|---|
| Chủ sở hữu rủi ro | Duy trì mô tả, đánh giá, chỉ báo, hành động và trạng thái rủi ro |
| Nhóm kiểm thử/xác nhận | Cung cấp bằng chứng, nêu giới hạn kiểm thử, phát hiện rủi ro mới và xác nhận hiệu quả kiểm soát trong phạm vi kiểm thử |
| Chủ sở hữu kỹ thuật/dịch vụ | Triển khai kiểm soát, duy trì khả năng quan sát, xử lý vấn đề và cung cấp dữ liệu vận hành |
| Chủ sở hữu sản phẩm/nghiệp vụ | Đánh giá tác động đến người dùng và mục tiêu kinh doanh, ưu tiên xử lý |
| Bảo mật/dữ liệu/tuân thủ | Tư vấn và quyết định trong phạm vi chuyên môn, xác định yêu cầu bắt buộc và giới hạn không thể miễn trừ |
| Người có thẩm quyền phát hành | Cân nhắc bằng chứng và rủi ro còn lại để quyết định phát hành theo chính sách |

Người thực hiện kiểm thử có trách nhiệm báo cáo trung thực kết quả và giới hạn bằng chứng, nhưng không mặc nhiên có quyền chấp nhận rủi ro kinh doanh hoặc pháp lý. Việc chấp nhận phải do người có thẩm quyền phù hợp với loại rủi ro và chính sách tổ chức thực hiện.

Một quyết định chấp nhận rủi ro cần ghi:

- Rủi ro cụ thể và mức rủi ro còn lại tại thời điểm quyết định.
- Bằng chứng đã xem xét và các giới hạn còn tồn tại.
- Phạm vi sản phẩm, người dùng, môi trường và phiên bản áp dụng.
- Lý do chấp nhận và các biện pháp giảm thiểu đang có.
- Người chấp thuận, ngày quyết định và thời hạn hiệu lực.
- Chỉ báo, ngưỡng, hành động khi vượt ngưỡng và điều kiện thu hồi chấp thuận.

Không dùng một lần phê duyệt vô thời hạn cho rủi ro thay đổi theo tải, phiên bản hoặc môi trường. Rủi ro cần được đánh giá lại khi điều kiện chấp thuận không còn đúng.

## 8. Ví dụ theo dõi rủi ro còn lại

### Ví dụ A: Giao dịch thanh toán có thể bị ghi nhận trùng

**Rủi ro:** khi cổng thanh toán phản hồi chậm, người mua gửi lại yêu cầu và hệ thống có thể tạo hai giao dịch.

**Kiểm soát và bằng chứng:** dịch vụ dùng khóa idempotency, lưu trạng thái giao dịch và chạy đối soát. Kiểm thử tích hợp mô phỏng timeout, phản hồi trễ và retry đã đạt trên các kịch bản được xác định.

**Rủi ro còn lại:** hành vi của nhà cung cấp trong sự cố diện rộng hoặc khi webhook đến sai thứ tự chưa được mô phỏng đầy đủ. Kiểm thử đạt không loại bỏ hoàn toàn rủi ro từ hệ thống bên ngoài.

**Theo dõi:** tỷ lệ giao dịch ở trạng thái chưa rõ, số giao dịch không khớp đối soát, số yêu cầu lặp và cảnh báo webhook lỗi. Khi chỉ báo vượt ngưỡng, tạm giới hạn luồng thanh toán liên quan, chuyển giao dịch sang hàng đợi đối soát và kích hoạt quy trình phối hợp với nhà cung cấp.

### Ví dụ B: Di trú dữ liệu khách hàng

**Rủi ro:** một số bản ghi lịch sử có giá trị rỗng hoặc định dạng cũ có thể bị chuyển đổi sai.

**Kiểm soát và bằng chứng:** kiểm thử chuyển đổi trên tập dữ liệu đại diện, đối chiếu số lượng bản ghi, kiểm tra tổng kiểm và lấy mẫu các trường quan trọng. Kết quả cho thấy các quy tắc đã xác định được đáp ứng.

**Rủi ro còn lại:** dữ liệu hiếm gặp hoặc không có trong tập mẫu vẫn có thể gây lỗi. Tập dữ liệu kiểm thử không bao phủ toàn bộ biến thể lịch sử.

**Theo dõi:** số bản ghi bị từ chối, tỷ lệ trường thiếu, sai lệch đối soát và số lỗi nhập dữ liệu theo lô. Triển khai theo đợt, giữ bản sao lưu, tạm dừng lô khi vượt ngưỡng sai lệch và chỉ tiếp tục sau khi xác định nguyên nhân.

### Ví dụ C: Hiệu năng khi lưu lượng tăng đột biến

**Rủi ro:** dịch vụ có thể tăng độ trễ hoặc từ chối yêu cầu khi lưu lượng vượt mức đã kiểm thử.

**Kiểm soát và bằng chứng:** kiểm thử tải ở mức bình thường và đỉnh dự báo, kiểm tra tự động mở rộng và giới hạn tốc độ. Các ngưỡng trong kịch bản đã chạy đều đạt.

**Rủi ro còn lại:** chưa kiểm thử tải kéo dài vượt dự báo và tình huống nhiều phụ thuộc cùng chậm.

**Theo dõi:** p95/p99, tỷ lệ timeout, hàng đợi, CPU/bộ nhớ và tốc độ tiêu thụ error budget. Khi ngưỡng hành động bị vượt, giảm tải hoặc giới hạn chức năng ít quan trọng, mở rộng năng lực và đánh giá lại trước khi tiếp tục chiến dịch.

### Ví dụ D: Khả năng khôi phục dịch vụ

**Rủi ro:** dịch vụ có thể không khôi phục trong thời gian yêu cầu khi mất một vùng triển khai.

**Kiểm soát và bằng chứng:** sao lưu được xác minh và khôi phục thành công trong môi trường thử nghiệm riêng; thời gian phục hồi của kịch bản đó đáp ứng mục tiêu.

**Rủi ro còn lại:** diễn tập chưa mô phỏng đầy đủ sự cố đồng thời ở vùng dữ liệu và hệ thống định danh.

**Theo dõi:** độ mới bản sao lưu, kết quả kiểm tra tự động, thời gian khôi phục trong diễn tập, lỗi phụ thuộc và tình trạng sao chép dữ liệu. Lập lịch diễn tập đầy đủ và xác định rõ điều kiện phải chuyển cấp nếu bản sao lưu không đạt.

## 9. Mẫu hồ sơ rủi ro còn lại

Mỗi rủi ro nên có một bản ghi ổn định để có thể cập nhật xuyên suốt vòng đời sản phẩm.

| Trường | Nội dung cần ghi |
|---|---|
| ID và tên | Mã định danh duy nhất, tên ngắn mô tả rủi ro |
| Mục tiêu chất lượng liên quan | Nhu cầu, yêu cầu hoặc mục tiêu có thể bị ảnh hưởng |
| Phát biểu rủi ro | Nguyên nhân, sự kiện có thể xảy ra và hậu quả |
| Phạm vi | Thành phần, luồng, người dùng, dữ liệu, phiên bản và môi trường |
| Rủi ro vốn có | Đánh giá khả năng và tác động trước kiểm soát |
| Biện pháp kiểm soát | Phòng ngừa, phát hiện, giảm thiểu và khôi phục |
| Hoạt động kiểm chứng | Kịch bản, dữ liệu, môi trường, phiên bản và tiêu chí đạt |
| Bằng chứng | Kết quả, liên kết báo cáo, thời điểm và người xác nhận |
| Giới hạn bằng chứng | Phần chưa bao phủ, giả định và độ không chắc chắn |
| Rủi ro còn lại | Đánh giá khả năng, tác động và lý do sau kiểm soát |
| Chỉ báo và ngưỡng | Nguồn dữ liệu, mức nền, cảnh báo và ngưỡng hành động |
| Kế hoạch xử lý | Hành động, chủ sở hữu, thời hạn và tiêu chí hoàn tất |
| Chấp thuận | Người có thẩm quyền, lý do, phạm vi và ngày quyết định |
| Điều kiện xem xét lại | Sự kiện kích hoạt, thời điểm rà soát hoặc ngày hết hạn |
| Trạng thái | Mở, đang xử lý, chấp nhận có điều kiện, đã giảm thiểu hoặc đóng |

Ví dụ bản ghi rút gọn:

```yaml
id: RISK-PAY-007
title: "Giao dịch thanh toán có thể chưa rõ trạng thái sau timeout"
statement: "Do phản hồi từ nhà cung cấp có thể đến trễ, trạng thái giao dịch có thể không đồng bộ, dẫn đến đối soát chậm hoặc xử lý lặp."
inherent_risk:
  likelihood: medium
  impact: critical
controls:
  - "Idempotency key cho yêu cầu tạo giao dịch"
  - "Đối soát trạng thái và xử lý webhook lặp"
verification:
  - "Kiểm thử timeout, retry và webhook đến trễ"
  - "Đối chiếu nhật ký giao dịch với kết quả nhà cung cấp"
evidence_limit: "Chưa mô phỏng đầy đủ sự cố diện rộng và webhook sai thứ tự từ nhà cung cấp thật."
residual_risk:
  likelihood: low
  impact: critical
  decision: conditional_acceptance
indicators:
  - "Tỷ lệ giao dịch ở trạng thái chưa rõ"
  - "Số giao dịch không khớp đối soát"
action_threshold: "Vượt ngưỡng vận hành đã được chủ dịch vụ phê duyệt"
owner: "Payment service owner"
review_trigger: "Thay đổi API nhà cung cấp hoặc sự cố thanh toán nghiêm trọng"
```

Ví dụ YAML chỉ minh họa cấu trúc. Mức `likelihood` và `impact`, ngưỡng hành động, chủ sở hữu và quyết định chấp nhận phải được xác định bằng dữ liệu và chính sách thực tế của tổ chức. Không sao chép mức rủi ro ví dụ thành đánh giá chính thức.

## 10. Rà soát định kỳ và báo cáo trạng thái

Rủi ro còn lại cần được xem xét ở các thời điểm có ý nghĩa với vòng đời sản phẩm:

- Trước cổng quyết định phát hành, khi tổng hợp bằng chứng và các ngoại lệ.
- Sau triển khai, khi dữ liệu thực tế bắt đầu cho thấy hành vi của sản phẩm.
- Trong các buổi rà soát chất lượng, độ tin cậy hoặc an toàn định kỳ.
- Sau sự cố, lỗi nghiêm trọng, thay đổi kiến trúc hoặc thay đổi phụ thuộc.
- Trước khi hết hạn một quyết định chấp nhận rủi ro có điều kiện.
- Khi thay đổi nhóm người dùng, quy mô tải, phạm vi dữ liệu hoặc nghĩa vụ pháp lý.

Báo cáo trạng thái nên tập trung vào thay đổi kể từ lần rà soát trước: rủi ro mới, rủi ro tăng/giảm, kiểm soát mất hiệu lực, chỉ báo vượt ngưỡng, hành động quá hạn và quyết định cần cấp có thẩm quyền. Không chỉ báo cáo số lượng rủi ro mở hoặc đóng; một rủi ro nghiêm trọng có thể quan trọng hơn nhiều rủi ro thấp.

Khi đóng rủi ro, cần ghi căn cứ: nguyên nhân đã bị loại bỏ, kiểm soát được xác nhận hiệu quả, phạm vi không còn tồn tại hoặc rủi ro đã được chuyển thành một vấn đề được quản lý theo quy trình khác. Không đóng chỉ vì đã hoàn thành một hoạt động kiểm thử hoặc vì không còn ai nhắc đến rủi ro.

## 11. Những sai lầm thường gặp

- **Cho rằng kiểm thử đạt nghĩa là không còn rủi ro:** mọi hoạt động kiểm chứng đều có giới hạn về phạm vi, dữ liệu và môi trường.
- **Đồng nhất rủi ro còn lại với lỗi chưa sửa:** rủi ro còn bao gồm tình huống chưa xảy ra và khoảng trống bằng chứng.
- **Hạ mức rủi ro mà không có căn cứ:** số ca đạt tăng không tự chứng minh xác suất lỗi đã giảm.
- **Không ghi giới hạn kiểm chứng:** người đọc có thể hiểu nhầm bằng chứng chỉ áp dụng cho một kịch bản là bảo đảm cho mọi điều kiện.
- **Dùng điểm số giả chính xác:** con số không có dữ liệu hỗ trợ tạo cảm giác chắc chắn sai lệch.
- **Theo dõi chỉ báo nhưng không có ngưỡng hoặc người xử lý:** tín hiệu không dẫn đến hành động kịp thời.
- **Chỉ theo dõi chỉ báo kết quả:** nhóm phát hiện vấn đề sau khi hậu quả đã xảy ra mà bỏ qua tín hiệu cảnh báo sớm.
- **Chấp nhận rủi ro vô thời hạn:** điều kiện vận hành và mức phơi nhiễm có thể thay đổi sau quyết định.
- **Không cập nhật sau thay đổi hoặc sự cố:** đánh giá cũ không còn phản ánh sản phẩm hiện tại.
- **Để người kiểm thử tự chấp nhận mọi rủi ro:** quyết định cần đúng thẩm quyền và có trách nhiệm nghiệp vụ/kỹ thuật phù hợp.

## 12. Checklist theo dõi rủi ro còn lại

- [ ] Rủi ro được mô tả bằng nguyên nhân, sự kiện có thể xảy ra và hậu quả.
- [ ] Phạm vi, người dùng, dữ liệu, phiên bản và môi trường bị ảnh hưởng được xác định.
- [ ] Rủi ro vốn có và rủi ro còn lại được phân biệt.
- [ ] Biện pháp kiểm soát đã được triển khai và có bằng chứng về hiệu quả.
- [ ] Kết quả kiểm chứng nêu rõ điều kiện chạy, phạm vi bao phủ và giới hạn.
- [ ] Khả năng xảy ra, tác động và mức độ không chắc chắn được đánh giá có căn cứ.
- [ ] Rủi ro còn lại được so sánh với ngưỡng chấp nhận và yêu cầu bắt buộc.
- [ ] Chỉ báo, nguồn dữ liệu, mức nền, ngưỡng cảnh báo và ngưỡng hành động đã được xác định.
- [ ] Mỗi chỉ báo có chủ sở hữu, thời gian phản hồi và hành động tương ứng.
- [ ] Kế hoạch xử lý có người phụ trách, thời hạn và tiêu chí hoàn tất.
- [ ] Quyết định chấp nhận có đúng thẩm quyền, phạm vi và thời hạn.
- [ ] Có điều kiện kích hoạt rà soát lại sau thay đổi hoặc sự cố.
- [ ] Hồ sơ được cập nhật và liên kết với quyết định phát hành/vận hành.

## Kết luận

Theo dõi rủi ro còn lại sau kiểm chứng đòi hỏi đánh giá cả hiệu quả lẫn giới hạn của các biện pháp đã thực hiện. Nhóm cần liên kết rủi ro với kiểm soát, hoạt động xác nhận, bằng chứng và chỉ báo vận hành; đánh giá lại khả năng xảy ra cùng tác động; xác định ngưỡng và người chịu trách nhiệm; đồng thời ghi rõ quyết định chấp nhận hoặc xử lý thêm. Nhờ đó, kết quả kiểm thử trở thành căn cứ cho quyết định phát hành và quản lý chất lượng liên tục, thay vì một báo cáo đạt/trượt tách rời khỏi rủi ro thực tế.
