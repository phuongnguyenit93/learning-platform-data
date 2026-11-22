# Lập phương án dự phòng khi môi trường hoặc dịch vụ bên ngoài không sẵn sàng

Môi trường kiểm thử và dịch vụ bên ngoài có thể ngừng hoạt động đúng lúc nhóm cần xác minh một thay đổi. Cơ sở dữ liệu thử nghiệm bị lỗi, môi trường staging không thể truy cập, nhà cung cấp thanh toán bảo trì, sandbox hết hạn thông tin xác thực hoặc một dịch vụ dùng chung quá tải đều có thể làm gián đoạn kiểm thử.

Nếu không có phương án dự phòng, nhóm thường phải chờ mà không biết khi nào có thể tiếp tục, hoặc tự ý bỏ qua kiểm thử để giữ tiến độ. Cả hai cách đều tạo rủi ro: thời gian phát triển bị lãng phí, bằng chứng bị thiếu và người ra quyết định có thể hiểu nhầm rằng hệ thống đã được xác minh đầy đủ.

Lập phương án dự phòng giúp nhóm tiếp tục những hoạt động có thể thực hiện an toàn, xác định rõ phần kiểm thử nào phải chờ phụ thuộc thật, và khôi phục đầy đủ bằng chứng khi môi trường hoặc dịch vụ hoạt động trở lại. Phương án cần quy định điều kiện kích hoạt, lựa chọn thay thế, giới hạn của từng lựa chọn, người chịu trách nhiệm, cách ghi nhận kết quả và quy trình chạy bù.

Mục tiêu là duy trì tiến độ mà vẫn bảo toàn ý nghĩa của kiểm thử. Một mock có thể giúp kiểm tra logic xử lý phản hồi, nhưng không chứng minh nhà cung cấp thật đang hoạt động. Một môi trường dự phòng có thể cho phép chạy kiểm thử, nhưng chỉ tạo ra bằng chứng tương đương khi cấu hình, dữ liệu và phiên bản đáp ứng đúng điều kiện cần thiết.

## 1. Phân biệt sự cố môi trường và sự cố dịch vụ bên ngoài

Môi trường kiểm thử là tập hợp hạ tầng, cấu hình, dữ liệu và dịch vụ cần thiết để thực hiện kiểm thử. Nó có thể gồm ứng dụng, cơ sở dữ liệu, hàng đợi, mạng, DNS, chứng thư, tài khoản, runner CI, công cụ quan sát và các dịch vụ hỗ trợ.

Dịch vụ bên ngoài là phụ thuộc nằm ngoài quyền kiểm soát trực tiếp của nhóm sản phẩm hoặc tổ chức. Ví dụ gồm cổng thanh toán, nhà cung cấp danh tính, dịch vụ email, nền tảng vận chuyển, API dữ liệu, dịch vụ định vị hoặc sandbox do đối tác quản lý.

Hai loại vấn đề có thể xuất hiện đồng thời. Chẳng hạn staging vẫn chạy nhưng không thể gọi sandbox thanh toán; hoặc sandbox vẫn sẵn sàng nhưng DNS trong môi trường kiểm thử không phân giải được địa chỉ của nhà cung cấp.

### Các dạng không sẵn sàng thường gặp

| Loại sự cố | Ví dụ | Ảnh hưởng đến kiểm thử |
|---|---|---|
| Môi trường ứng dụng | Staging không khởi động, bản dựng lỗi | Không thể thực hiện hành trình trên ứng dụng |
| Cơ sở dữ liệu | Database thử nghiệm mất kết nối hoặc schema sai phiên bản | Không thể đọc, ghi hoặc xác minh dữ liệu |
| Hạ tầng dùng chung | Runner CI, broker, DNS hoặc mạng gặp sự cố | Nhiều bộ kiểm thử bị chặn cùng lúc |
| Cấu hình và quyền | Secret hết hạn, chứng thư sai, tài khoản bị khóa | Kết nối hoặc xác thực thất bại |
| Dịch vụ bên ngoài | Sandbox thanh toán hoặc API đối tác ngừng hoạt động | Không thể xác minh tương tác thật |
| Dữ liệu kiểm thử | Fixture bị hỏng, snapshot không tương thích | Kịch bản không có trạng thái đầu vào hợp lệ |
| Giới hạn tài nguyên | Hết quota, giới hạn tốc độ hoặc quá tải | Test timeout hoặc kết quả không ổn định |
| Thay đổi phiên bản | API hoặc schema của phụ thuộc thay đổi | Hợp đồng và dữ liệu không còn tương thích |

Cần phân biệt một phụ thuộc thật sự không sẵn sàng với lỗi do sản phẩm hoặc mã kiểm thử. Ví dụ, API trả 401 có thể do secret hết hạn, nhưng cũng có thể do ứng dụng gửi token sai. Không nên kích hoạt phương án dự phòng trước khi có bằng chứng đủ để phân loại nguyên nhân.

## 2. Mục tiêu và nguyên tắc của phương án dự phòng

Một phương án tốt cần cân bằng bốn mục tiêu:

1. **An toàn:** không gây tác động ngoài ý muốn lên dữ liệu, tài khoản hoặc hệ thống thật.
2. **Liên tục:** cho phép tiếp tục những kiểm thử không phụ thuộc vào thành phần đang lỗi.
3. **Trung thực về bằng chứng:** ghi rõ điều gì đã được kiểm tra bằng phụ thuộc thay thế và điều gì vẫn chưa được xác minh.
4. **Khả năng phục hồi:** có cách quay lại môi trường chuẩn, chạy bù và khép lại khoảng trống kiểm thử.

Các nguyên tắc nên áp dụng:

- Chuẩn bị phương án trước khi xảy ra sự cố, đặc biệt với phụ thuộc quan trọng.
- Chọn phương án dự phòng theo loại rủi ro và mục tiêu kiểm thử.
- Không coi kết quả dùng mock hoặc stub là bằng chứng tương đương với phụ thuộc thật nếu chưa chứng minh được điều đó.
- Không biến trạng thái bị chặn thành đạt chỉ để pipeline xanh.
- Không dùng dữ liệu sản xuất hoặc thông tin xác thực thật làm giải pháp tạm thời thiếu kiểm soát.
- Ghi nhận người quyết định, thời điểm kích hoạt và thời điểm kết thúc phương án.
- Chạy lại các kiểm thử cần phụ thuộc thật khi dịch vụ khôi phục.
- Đánh giá sau sự cố để cải thiện độ sẵn sàng và giảm thời gian gián đoạn.

Phương án dự phòng không phải cách loại bỏ mọi phụ thuộc. Nó là cách quản lý có chủ đích những gì nhóm có thể tiếp tục và những gì phải chờ.

## 3. Lập danh mục phụ thuộc và đánh giá mức độ quan trọng

Không thể lập kế hoạch cho một phụ thuộc mà nhóm chưa nhận diện. Hãy lập danh mục các thành phần cần thiết cho từng tầng kiểm thử và hành trình quan trọng.

Thông tin nên ghi:

- Tên thành phần hoặc dịch vụ.
- Nhóm sở hữu và đầu mối hỗ trợ.
- Mục đích sử dụng trong kiểm thử.
- Môi trường và endpoint liên quan.
- Mức độ quan trọng đối với từng luồng.
- Cách phát hiện tình trạng không sẵn sàng.
- Phương án thay thế có thể dùng.
- Giới hạn bằng chứng của phương án thay thế.
- Thời gian khôi phục dự kiến hoặc cam kết dịch vụ nếu có.
- Quy trình xác nhận hoạt động trở lại.

### Phân loại mức độ quan trọng

Có thể dùng ba mức:

| Mức | Ý nghĩa | Cách chuẩn bị |
|---|---|---|
| Quan trọng đối với phát hành | Không thể đưa ra quyết định an toàn nếu thiếu bằng chứng | Có phương án dự phòng được kiểm chứng và quy tắc chặn phát hành |
| Quan trọng đối với tiến độ | Có thể tiếp tục một phần công việc khi phụ thuộc lỗi | Chuẩn bị mock, môi trường thay thế hoặc cách chạy cục bộ |
| Hỗ trợ | Có thể trì hoãn hoặc thay thế bằng quy trình thủ công trong thời gian ngắn | Ghi đầu mối và hướng dẫn khôi phục |

Mức quan trọng cần gắn với mục tiêu kiểm thử. Một dịch vụ email có thể chỉ là phụ thuộc hỗ trợ trong kiểm thử tính toán đơn hàng, nhưng lại là thành phần quan trọng khi kiểm tra quy trình gửi thông báo bắt buộc.

### Bản đồ phụ thuộc theo luồng

Ví dụ, hành trình thanh toán có thể phụ thuộc vào ứng dụng web, API đơn hàng, cơ sở dữ liệu, dịch vụ tồn kho, cổng thanh toán sandbox, webhook hoặc message broker và dịch vụ thông báo.

Nếu sandbox thanh toán ngừng hoạt động, nhóm vẫn có thể kiểm tra tạo đơn, xác thực đầu vào và một phần xử lý trạng thái bằng stub. Tuy nhiên, việc xác minh hợp đồng và hành vi thực tế với nhà cung cấp phải được đánh dấu còn thiếu.

## 4. Chọn loại phương án dự phòng phù hợp

Không có một giải pháp thay thế dùng được cho mọi sự cố. Cần chọn dựa trên câu hỏi kiểm thử.

### Môi trường dự phòng

Dùng một môi trường thứ hai đã được chuẩn bị với phiên bản, cấu hình và dữ liệu phù hợp. Cách này hữu ích khi môi trường chính bị lỗi hạ tầng hoặc cần được bảo trì.

Trước khi chuyển sang, cần xác minh môi trường dự phòng không bị trôi schema, thiếu secret hoặc dùng dữ liệu khác biệt làm thay đổi kết quả.

### Môi trường cục bộ hoặc tạm thời

Dùng container, compose stack hoặc môi trường tạm thời để chạy ứng dụng cùng các phụ thuộc có thể khởi tạo. Cách này giảm phụ thuộc vào môi trường dùng chung và phù hợp với kiểm thử đơn vị, thành phần hoặc một số kiểm thử tích hợp.

Cần xác nhận các khác biệt về cấu hình, mạng, tài nguyên và phiên bản so với môi trường mục tiêu.

### Mock, stub và fake

Dùng để mô phỏng một phụ thuộc khi mục tiêu là kiểm tra cách thành phần của mình xử lý phản hồi đã biết.

- Stub trả về phản hồi định trước.
- Mock ghi nhận hoặc xác minh tương tác.
- Fake cung cấp triển khai đơn giản có hành vi gần với hợp đồng cần thiết.

Chúng phù hợp để tiếp tục kiểm thử logic và các nhánh lỗi, nhưng không xác minh dịch vụ thật đang hoạt động.

### Service virtualization

Mô phỏng dịch vụ với các kịch bản có thể cấu hình, gồm phản hồi thành công, lỗi, độ trễ, timeout, giới hạn tốc độ và thông điệp bất thường. Cách này phù hợp khi phụ thuộc có nhiều hành vi khó tái tạo hoặc sandbox không ổn định.

Các mô hình mô phỏng cần được quản lý phiên bản và so sánh định kỳ với hợp đồng hiện tại.

### Sandbox hoặc nhà cung cấp thay thế

Nếu có sandbox thứ hai hoặc nhà cung cấp tương đương đã được phê duyệt, có thể chuyển sang khi hợp đồng và cấu hình tương thích. Không nên tự ý đổi nhà cung cấp hoặc endpoint trong kiểm thử vì hành vi, dữ liệu và giới hạn có thể khác.

### Kiểm thử độc lập không cần phụ thuộc

Tách những kiểm thử không cần dịch vụ đang lỗi để tiếp tục chạy. Ví dụ, có thể chạy kiểm thử đơn vị, kiểm tra tĩnh, kiểm thử giao diện với dữ liệu giả hoặc kiểm thử hợp đồng bằng schema đã lưu.

Đây thường là lựa chọn ít rủi ro nhất khi chưa rõ thời gian khôi phục.

## 5. Ma trận lựa chọn phương án theo mục tiêu kiểm thử

Phương án dự phòng chỉ có ý nghĩa khi phù hợp với loại bằng chứng cần thu thập.

| Mục tiêu | Phương án có thể dùng | Bằng chứng còn thiếu |
|---|---|---|
| Kiểm tra logic xử lý phản hồi thành công | Stub hoặc fake | Hành vi của dịch vụ thật |
| Kiểm tra timeout và retry | Service virtualization hoặc fault injection | Đặc tính thực tế của nhà cung cấp |
| Kiểm tra schema và cấu trúc thông điệp | Contract test với schema có phiên bản | Khả năng sẵn sàng và cấu hình endpoint thật |
| Kiểm tra ghi dữ liệu | Database tạm thời tương thích | Khác biệt hạ tầng của môi trường mục tiêu |
| Kiểm tra hành trình xuyên dịch vụ | Môi trường dự phòng đầy đủ hoặc service virtualization | Những phụ thuộc bị mô phỏng |
| Kiểm tra tích hợp nhà cung cấp | Sandbox dự phòng đã được xác nhận | Khác biệt giữa sandbox và production |
| Kiểm tra giao diện | Môi trường cục bộ với backend giả | Tích hợp thật và dữ liệu thật |
| Kiểm tra sau triển khai | Chờ môi trường mục tiêu phục hồi hoặc dùng môi trường staging tương đương | Bằng chứng trên môi trường thực tế |

Trước khi chọn, hãy trả lời:

1. Câu hỏi kiểm thử cụ thể là gì?
2. Phần nào của hệ thống cần được thực thi thật?
3. Phụ thuộc nào có thể thay thế mà không làm thay đổi ý nghĩa kiểm thử?
4. Những assertion nào vẫn có giá trị?
5. Kết quả cần được gắn nhãn ra sao?
6. Kiểm thử nào phải chạy lại khi phụ thuộc phục hồi?

Nếu không thể trả lời rõ, hãy chạy các kiểm thử độc lập và đánh dấu phần phụ thuộc là bị chặn.

## 6. Phân biệt mô phỏng phụ thuộc với kiểm tra cơ chế dự phòng của sản phẩm

Có hai mục tiêu thường bị nhầm lẫn.

**Phương án dự phòng của hoạt động kiểm thử** giúp nhóm tiếp tục kiểm tra khi môi trường hoặc dịch vụ thật không sẵn sàng. Ví dụ, dùng stub để kiểm tra cách dịch vụ đơn hàng xử lý phản hồi từ chối của cổng thanh toán.

**Cơ chế dự phòng của chính sản phẩm** là hành vi mà hệ thống cần thực hiện khi phụ thuộc thật gặp sự cố. Ví dụ, sản phẩm chuyển giao dịch sang trạng thái chờ đối soát, hiển thị thông báo phù hợp hoặc dùng nhà cung cấp dự phòng.

Dùng stub để tiếp tục kiểm thử không tự động chứng minh cơ chế dự phòng của sản phẩm hoạt động đúng. Muốn xác minh cơ chế đó, cần tạo điều kiện lỗi có kiểm soát trong môi trường phù hợp và kiểm tra hành vi thực tế của ứng dụng.

Ví dụ, nếu sản phẩm có circuit breaker, kiểm thử cần xác minh ngưỡng lỗi làm circuit mở, request tiếp theo được xử lý như thế nào, thời gian chờ trước khi thử lại, cách circuit chuyển sang trạng thái half-open, điều kiện đóng lại sau khi phụ thuộc phục hồi và log, metric, cảnh báo tương ứng.

Một mock có thể giúp kiểm tra logic này ở cấp độ thành phần. Kiểm thử tích hợp hoặc kiểm thử hỗn loạn có kiểm soát cần xác minh hành vi với kết nối và phụ thuộc thật trong phạm vi an toàn.

## 7. Xác định điều kiện kích hoạt phương án dự phòng

Không nên chuyển phương án chỉ vì một request thất bại. Lỗi đơn lẻ có thể do dữ liệu, mã kiểm thử hoặc cấu hình. Cần có tiêu chí phát hiện và ngưỡng rõ.

Các tín hiệu có thể gồm:

- Health check thất bại liên tục trong khoảng thời gian quy định.
- Không thể thiết lập kết nối đến endpoint.
- Tỷ lệ timeout hoặc lỗi vượt ngưỡng.
- Runner hoặc môi trường không thể khởi tạo.
- Database không đáp ứng truy vấn kiểm tra cơ bản.
- Sandbox trả thông báo bảo trì hoặc quota bị khóa.
- Chứng thư, token hoặc secret hết hạn.
- Đội sở hữu phụ thuộc xác nhận sự cố.
- Thời gian chờ vượt quá ngưỡng được thống nhất cho pipeline.

### Phân biệt lỗi tạm thời và sự cố kéo dài

Có thể định nghĩa ba trạng thái vận hành:

| Trạng thái | Điều kiện tham khảo | Hành động |
|---|---|---|
| Bình thường | Health check và giao dịch kiểm tra đạt | Dùng môi trường chuẩn |
| Suy giảm | Lỗi rải rác, độ trễ cao hoặc một phần chức năng không sẵn sàng | Thử lại có giới hạn, giảm tải và thông báo |
| Không sẵn sàng | Nhiều lần kiểm tra liên tiếp thất bại hoặc có xác nhận sự cố | Kích hoạt phương án dự phòng đã phê duyệt |

Ngưỡng cần dựa trên đặc tính phụ thuộc. Một API có thể chấp nhận vài giây độ trễ; một database dùng cho kiểm thử đồng thời có thể cần tiêu chí sẵn sàng nghiêm ngặt hơn.

### Tránh retry không giới hạn

Retry có thể giúp vượt qua lỗi mạng ngắn, nhưng retry quá nhiều làm kéo dài pipeline và tạo tải thêm cho dịch vụ đang gặp sự cố. Cần có timeout, số lần thử tối đa và backoff phù hợp. Nếu vẫn thất bại, chuyển sang trạng thái blocked hoặc kích hoạt phương án theo quy tắc.

## 8. Chuẩn bị môi trường dự phòng trước khi cần dùng

Môi trường dự phòng chỉ hữu ích khi được kiểm tra định kỳ. Một môi trường tồn tại trên tài liệu nhưng không thể khởi động, thiếu dữ liệu hoặc dùng phiên bản cũ không phải là phương án đáng tin cậy.

Checklist chuẩn bị:

- Có chủ sở hữu và đầu mối vận hành.
- Có hướng dẫn kích hoạt và điều kiện sử dụng.
- Có phiên bản ứng dụng và schema được xác định.
- Có cách nạp dữ liệu kiểm thử an toàn.
- Có secret, chứng thư và quyền truy cập được quản lý.
- Có giới hạn tài nguyên và số lượng test được phép chạy.
- Có cơ chế cleanup và reset.
- Có log, metric và cách điều tra.
- Có tiêu chí xác nhận môi trường đủ tương đương.
- Có lịch kiểm tra định kỳ và ghi nhận kết quả.

### Kiểm tra khả năng chuyển đổi định kỳ

Có thể tổ chức diễn tập ngắn để xác nhận môi trường dự phòng khởi động được, ứng dụng kết nối được với các phụ thuộc cần thiết, schema và dữ liệu đúng phiên bản, bộ kiểm thử mẫu chạy đạt, quy trình chuyển về môi trường chuẩn hoạt động và dữ liệu cùng tài nguyên được cleanup an toàn.

Diễn tập giúp phát hiện sớm cấu hình lỗi thời và tránh việc lần đầu sử dụng dự phòng lại chính là lúc phát hành đang bị chặn.

## 9. Thiết kế phương án cho môi trường dùng chung

Môi trường dùng chung thường bị ảnh hưởng bởi nhiều nhóm, lịch triển khai và dữ liệu tích lũy. Khi xảy ra sự cố, cần tránh để các nhóm tự sửa chồng chéo.

### Xác định trạng thái môi trường

Môi trường có thể được theo dõi theo các trạng thái: sẵn sàng, đang triển khai, đang bảo trì, suy giảm, không sẵn sàng, đang khôi phục và chờ xác minh sau khôi phục.

Trạng thái cần được thông báo ở nơi nhóm có thể xem trước khi bắt đầu pipeline hoặc phiên kiểm thử.

### Cách xử lý khi môi trường bị lỗi

1. Xác nhận lỗi bằng health check và một phép kiểm tra độc lập.
2. Ghi nhận thời điểm, phạm vi ảnh hưởng và nhóm đang sử dụng.
3. Dừng những test có thể gây thêm dữ liệu sai hoặc làm tăng tải.
4. Chuyển các test độc lập sang môi trường cục bộ hoặc runner riêng nếu phù hợp.
5. Bảo toàn log, trạng thái và dữ liệu cần điều tra.
6. Giao nhóm sở hữu môi trường khôi phục.
7. Kiểm tra schema, dữ liệu và cấu hình sau khi khôi phục.
8. Chạy smoke test trước khi mở lại cho các nhóm.
9. Thông báo trạng thái và cho phép tiếp tục theo thứ tự ưu tiên.

Không nên reset toàn bộ môi trường khi chưa xác định tác động đến các nhóm khác hoặc chưa lưu bằng chứng cần thiết.

### Dữ liệu dùng chung và snapshot

Nếu cần khôi phục nhanh, snapshot có thể giúp tái tạo trạng thái. Tuy nhiên, cần ghi phiên bản schema, thời điểm tạo, nguồn dữ liệu và các migration đã áp dụng. Snapshot cũ có thể không tương thích với ứng dụng mới.

Khi reset dữ liệu, cần xác định ai được phép thực hiện, phạm vi xóa và cách phục hồi. Không nên dùng dữ liệu sản xuất chưa được bảo vệ làm snapshot kiểm thử.

## 10. Phương án khi dịch vụ bên ngoài không sẵn sàng

Dịch vụ bên ngoài có thể có lịch bảo trì, quota, giới hạn tốc độ, sandbox không ổn định hoặc thay đổi hợp đồng. Nhóm cần có phương án riêng cho từng phụ thuộc quan trọng.

### Cổng thanh toán

Có thể dùng stub hoặc service virtualization để kiểm tra thanh toán thành công, từ chối giao dịch, timeout trước và sau khi nhà cung cấp xử lý, webhook lặp hoặc đến trễ, giới hạn tốc độ, lỗi xác thực và trạng thái giao dịch không chắc chắn.

Khi sandbox phục hồi, cần chạy lại kiểm thử hợp đồng và tích hợp thật để xác minh endpoint, xác thực, payload, webhook và đối soát.

### Dịch vụ email hoặc SMS

Có thể dùng bộ thu nhận thư thử nghiệm hoặc stub để kiểm tra nội dung, người nhận và điều kiện gửi. Cần kiểm tra riêng việc tích hợp với nhà cung cấp thật, giới hạn gửi, trạng thái giao nhận và xử lý lỗi.

Không nên gửi thông báo thử nghiệm đến người dùng thật khi đang dùng phương án tạm thời.

### Nhà cung cấp danh tính

Có thể dùng identity provider giả lập để kiểm tra logic xử lý token hợp lệ, hết hạn hoặc thiếu quyền. Tuy nhiên, việc xác minh cấu hình issuer, chữ ký, key rotation, metadata và luồng đăng nhập thật vẫn cần phụ thuộc thật hoặc môi trường tương đương đã được xác nhận.

### API dữ liệu hoặc vận chuyển

Có thể dùng fixture phản hồi đã được kiểm soát để kiểm tra mapping và quy tắc nghiệp vụ. Cần ghi phiên bản payload và nguồn dữ liệu. Khi dịch vụ phục hồi, kiểm tra lại schema, mã lỗi, giới hạn tốc độ và hành vi thực tế.

## 11. Quản lý mock, stub và dữ liệu phản hồi dự phòng

Mô phỏng chỉ hữu ích nếu phản ánh hợp đồng mà ứng dụng cần xử lý. Một stub tự tạo theo giả định cũ có thể khiến kiểm thử đạt dù tích hợp thật đã thay đổi.

Nên quản lý:

- Phiên bản schema hoặc hợp đồng mà mô phỏng đại diện.
- Nguồn của ví dụ request và response.
- Các tình huống thành công và lỗi.
- Thời gian phản hồi và hành vi timeout.
- Giá trị biên và dữ liệu bất thường.
- Ngày kiểm tra tương thích gần nhất.
- Người sở hữu mô hình mô phỏng.

### Không chỉ mô phỏng đường đi thành công

Một bộ mô phỏng hữu ích cần hỗ trợ phản hồi hợp lệ, phản hồi thiếu trường hoặc sai định dạng, mã lỗi nghiệp vụ, lỗi xác thực hoặc phân quyền, timeout và kết nối bị ngắt, phản hồi chậm, thông điệp lặp hoặc sai thứ tự, giới hạn tốc độ và kết quả không chắc chắn sau khi request đã được xử lý.

### Kiểm tra độ lệch giữa mô phỏng và dịch vụ thật

Khi phụ thuộc phục hồi, chạy contract test hoặc một nhóm kiểm thử so sánh để phát hiện mô phỏng đã lỗi thời. Nếu schema thay đổi, cập nhật mô hình và xác định test nào cần chạy lại.

Không nên dùng response ghi lại từ một lần chạy cũ mà không kiểm tra dữ liệu nhạy cảm, phiên bản hợp đồng và thời điểm. Dữ liệu ghi lại cần được làm sạch, có nguồn gốc và không chứa token hoặc thông tin nhận diện người thật.

## 12. Phân loại kết quả khi phương án dự phòng được kích hoạt

Kết quả kiểm thử cần phản ánh đúng điều đã xảy ra. Một test dùng mock và đạt không có cùng ý nghĩa với test chạy qua phụ thuộc thật và đạt.

Có thể dùng các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| Passed | Test đã chạy với điều kiện dự kiến và tất cả assertion đạt |
| Failed | Test đã chạy và có assertion không đạt |
| Blocked | Không thể chạy hoặc hoàn tất do môi trường/phụ thuộc không sẵn sàng |
| Skipped | Được chủ động bỏ qua theo quy tắc đã ghi |
| Passed with substitute | Đạt khi dùng mock, stub, fake hoặc môi trường thay thế |
| Inconclusive | Có chạy nhưng bằng chứng không đủ để kết luận |
| Not run | Chưa thực hiện trong lần đánh giá |

Nếu công cụ chỉ hỗ trợ Passed/Failed/Skipped, hãy ghi rõ loại phụ thuộc và phương án đã dùng trong metadata hoặc báo cáo. Không gộp Passed with substitute vào Passed mà không giữ thông tin.

### Không biến Blocked thành Passed

Nếu test không chạy do sandbox ngừng hoạt động, kết quả là blocked. Nếu một test khác dùng stub để kiểm tra logic xử lý, test đó có thể đạt trong phạm vi mô phỏng. Hai kết quả cần được báo cáo riêng.

### Phân biệt Skipped và Blocked

- **Skipped:** nhóm quyết định bỏ qua theo điều kiện đã định, ví dụ test chỉ chạy theo lịch hoặc trên nền tảng không thuộc phạm vi.
- **Blocked:** test lẽ ra cần chạy nhưng không thể thực hiện do điều kiện phụ thuộc hoặc môi trường.
- **Passed with substitute:** có thực thi bằng phương án thay thế, nhưng bằng chứng bị giới hạn.

Sự phân biệt này giúp người ra quyết định thấy phần kiểm thử nào còn thiếu.

## 13. Xác định điều kiện chặn pipeline và phát hành

Không phải mọi sự cố phụ thuộc đều phải dừng toàn bộ pipeline. Cần phân loại test theo mức độ quan trọng và xác định cách xử lý trước khi xảy ra sự cố.

### Nhóm kiểm thử có thể tiếp tục

Ví dụ: kiểm thử đơn vị không cần môi trường ngoài; kiểm tra tĩnh và phân tích mã; kiểm thử thành phần dùng fake đã được xác minh; contract test dùng schema đã quản lý; kiểm thử giao diện với backend giả khi mục tiêu chỉ là hành vi giao diện.

### Nhóm kiểm thử cần chờ phụ thuộc thật

Ví dụ: xác minh tích hợp với nhà cung cấp thanh toán; kiểm tra callback hoặc webhook thực tế; kiểm tra cấu hình xác thực với identity provider; kiểm thử hiệu năng trên hạ tầng mục tiêu; kiểm tra migration trên phiên bản cơ sở dữ liệu mục tiêu; smoke test sau triển khai trên môi trường đích.

### Quy tắc quyết định

| Tình huống | Hành động pipeline | Điều kiện phát hành |
|---|---|---|
| Test độc lập đạt | Tiếp tục | Chỉ hỗ trợ các rủi ro mà test đó bao phủ |
| Test dùng substitute đạt | Tiếp tục với nhãn riêng | Không thay thế bằng chứng tích hợp thật nếu rủi ro yêu cầu |
| Test quan trọng bị blocked | Đánh dấu blocked và thông báo | Không tự động coi là đạt; cần chạy bù hoặc quyết định rủi ro có thẩm quyền |
| Môi trường không ổn định | Dừng nhóm test bị ảnh hưởng hoặc chuyển môi trường đã xác minh | Đánh giá ảnh hưởng đến độ tin cậy bằng chứng |
| Lỗi sản phẩm được xác nhận | Fail và tạo issue | Xử lý theo tiêu chí phát hành |
| Chỉ một phụ thuộc hỗ trợ bị lỗi | Tiếp tục các nhóm độc lập | Ghi rõ phần chức năng chưa được xác minh |

Một kiểm thử quan trọng bị blocked có thể làm quyết định phát hành phải chờ. Nếu tổ chức chấp nhận ngoại lệ, cần có người có thẩm quyền, lý do, rủi ro, biện pháp giảm thiểu và thời điểm xem xét lại. Nhóm kiểm thử không nên tự chuyển trạng thái blocked thành đạt.

## 14. Thiết kế pipeline để cô lập phụ thuộc

Pipeline nên chia test thành các nhóm có phụ thuộc khác nhau. Nhờ đó, sự cố của một dịch vụ không nhất thiết làm mất toàn bộ kết quả.

Một cấu trúc tham khảo:

- **Nhóm nhanh:** kiểm tra tĩnh, đơn vị và thành phần.
- **Nhóm hợp đồng:** kiểm tra schema và tương thích producer-consumer.
- **Nhóm tích hợp mô phỏng:** dùng service virtualization cho các tình huống lỗi.
- **Nhóm tích hợp thật:** cần môi trường hoặc sandbox.
- **Nhóm E2E:** cần các thành phần phối hợp trong môi trường tương đương.
- **Nhóm sau triển khai:** chạy trên môi trường mục tiêu khi đủ điều kiện.

### Cổng kiểm tra sẵn sàng

Trước khi chạy nhóm phụ thuộc môi trường, pipeline có thể kiểm tra endpoint có truy cập được không, phiên bản dịch vụ có đúng không, database có truy vấn được không, schema revision có phù hợp không, tài khoản và quyền có hợp lệ không, dữ liệu cần thiết có sẵn không và phụ thuộc có vượt giới hạn tốc độ hoặc quota không.

Nếu cổng kiểm tra thất bại, pipeline cần dừng nhóm phụ thuộc đó với lý do rõ ràng, đồng thời tiếp tục nhóm độc lập nếu chính sách cho phép.

### Không dùng health check duy nhất làm bằng chứng đầy đủ

Một endpoint health trả 200 chỉ cho biết một mức sẵn sàng nhất định. Nó không chứng minh rằng giao dịch nghiệp vụ, quyền, dữ liệu hoặc tích hợp đều hoạt động. Có thể cần một smoke test nhỏ, chỉ đọc hoặc giao dịch thử an toàn, để xác minh điều kiện cần cho nhóm kiểm thử.

### Tách retry và rerun

Retry là thử lại trong cùng một lần thực thi theo chính sách đã định. Rerun là chạy lại một nhóm hoặc pipeline sau khi điều kiện đã thay đổi. Cần lưu lịch sử để không che giấu lần thất bại ban đầu.

## 15. Bảo vệ dữ liệu và thông tin xác thực khi chuyển phương án

Sự cố thường tạo áp lực tìm cách nhanh nhất để tiếp tục. Tuy nhiên, chuyển sang môi trường hoặc dịch vụ thay thế không được làm giảm kiểm soát dữ liệu và quyền truy cập.

Cần bảo đảm:

- Không dùng tài khoản hoặc secret sản xuất tùy tiện trong môi trường kiểm thử.
- Không sao chép dữ liệu cá nhân thật vào môi trường dự phòng nếu chưa được phép và bảo vệ.
- Dùng dữ liệu tổng hợp hoặc đã ẩn danh phù hợp.
- Secret của môi trường dự phòng được quản lý riêng và có thời hạn.
- Quyền truy cập theo nguyên tắc tối thiểu.
- Log và artifact không chứa token, mật khẩu hoặc dữ liệu nhạy cảm.
- Snapshot có kiểm soát truy cập và thời hạn lưu.
- Dữ liệu thử nghiệm được cleanup sau khi kết thúc.

Nếu phương án yêu cầu thay endpoint, cần xác minh chứng thư, hostname, quyền và danh tính dịch vụ. Không nên tắt kiểm tra TLS hoặc bỏ xác thực chỉ để kết nối được.

## 16. Quy trình kích hoạt và điều phối sự cố

Một quy trình ngắn, rõ vai trò giúp nhóm tránh quyết định tùy tiện trong lúc bị áp lực thời gian.

### Bước 1: Phát hiện và xác nhận

Thu thập lỗi kết nối, health check, log và thời điểm bắt đầu. Thử xác minh bằng một phép kiểm tra độc lập, tránh kết luận dựa trên một test đơn lẻ.

### Bước 2: Xác định phạm vi ảnh hưởng

Liệt kê môi trường, dịch vụ, nhóm test, nhóm phát triển và mốc phát hành bị ảnh hưởng. Xác định có thể tiếp tục các kiểm thử độc lập hay không.

### Bước 3: Thông báo và chỉ định đầu mối

Thông báo tình trạng, người điều phối, nhóm chịu trách nhiệm khôi phục và thời điểm cập nhật tiếp theo. Không cần đợi biết nguyên nhân cuối cùng mới thông báo rằng kiểm thử đang bị ảnh hưởng.

### Bước 4: Chọn phương án

Dựa vào mục tiêu kiểm thử, chọn môi trường dự phòng, local stack, stub, service virtualization hoặc hoãn test. Ghi rõ phần bằng chứng còn thiếu.

### Bước 5: Kích hoạt và xác minh phương án

Kiểm tra phiên bản, schema, dữ liệu, cấu hình, quyền và smoke test trước khi chạy. Gắn nhãn kết quả để phân biệt với lần chạy chuẩn.

### Bước 6: Theo dõi và đánh giá lại

Theo dõi thời gian gián đoạn, lỗi mới, giới hạn của phương án và tiến độ khôi phục. Nếu phương án không còn đáng tin cậy, dừng và chuyển sang cách khác.

### Bước 7: Khôi phục môi trường chuẩn

Khi phụ thuộc trở lại, xác minh health check, phiên bản, schema, dữ liệu và cấu hình. Chạy smoke test trước khi mở lại nhóm kiểm thử đầy đủ.

### Bước 8: Chạy bù và đóng sự cố

Chạy các test đã blocked hoặc chỉ có bằng chứng mô phỏng, cập nhật báo cáo, xử lý chênh lệch và ghi nhận bài học.

## 17. Quy định vai trò và quyền quyết định

Một phương án cần chỉ định ai có quyền kích hoạt, ai hỗ trợ và ai quyết định về rủi ro phát hành.

| Vai trò | Trách nhiệm |
|---|---|
| Điều phối kiểm thử | Đánh giá nhóm test bị ảnh hưởng, chọn phương án trong phạm vi đã phê duyệt và theo dõi bằng chứng |
| Chủ sở hữu môi trường | Xác nhận sự cố, khôi phục môi trường, kiểm tra phiên bản và dữ liệu |
| Chủ sở hữu dịch vụ ngoài | Liên hệ nhà cung cấp, theo dõi trạng thái và xác nhận dịch vụ phục hồi |
| Nhóm phát triển | Xác định lỗi sản phẩm hay lỗi phụ thuộc, điều chỉnh test hoặc ứng dụng khi cần |
| Nhóm nền tảng | Hỗ trợ mạng, runner, secret, container và hạ tầng |
| Chủ sản phẩm hoặc người phê duyệt | Quyết định chấp nhận rủi ro khi bằng chứng quan trọng còn thiếu |
| Người sở hữu test | Cập nhật nhãn, cấu hình, fixture, kiểm thử và kế hoạch chạy bù |

Có thể dùng RACI nếu nhiều nhóm cùng tham gia. Với mỗi quyết định có ảnh hưởng đến phát hành, cần xác định người chịu trách nhiệm cuối cùng. Điều phối viên kiểm thử có thể báo cáo khoảng trống và đề xuất, nhưng quyết định chấp nhận rủi ro nghiệp vụ cần thuộc đúng thẩm quyền.

## 18. Phục hồi và chạy bù sau khi dịch vụ trở lại

Một lỗi môi trường không kết thúc khi health check chuyển xanh. Nhóm cần khép lại khoảng trống bằng chứng.

### Xác minh môi trường phục hồi

- Xác nhận endpoint và dịch vụ đã sẵn sàng.
- Kiểm tra phiên bản ứng dụng và schema.
- Kiểm tra dữ liệu, fixture và trạng thái ban đầu.
- Xác minh secret, chứng thư và quyền.
- Chạy smoke test đại diện.
- Xác nhận không còn dữ liệu dở dang từ lần chạy bị gián đoạn.
- Thông báo thời điểm môi trường sẵn sàng cho nhóm.

### Lập danh sách kiểm thử cần chạy bù

Danh sách nên gồm test bị blocked và chưa chạy; test chạy bằng mock hoặc stub nhưng cần xác minh thật; test thất bại do môi trường và cần chạy lại; test có dữ liệu bị ảnh hưởng khi sự cố xảy ra; và kiểm thử hồi quy liên quan đến phần vừa được khôi phục.

Không cần chạy lại toàn bộ bộ kiểm thử nếu có thể xác định chính xác phạm vi bị ảnh hưởng. Tuy nhiên, nếu không thể chứng minh nhóm test nào không bị tác động, cần mở rộng phạm vi chạy lại.

### Giữ lại lịch sử

Không xóa kết quả blocked hoặc thất bại ban đầu. Báo cáo cần cho thấy lần chạy nào bị ảnh hưởng, phương án tạm thời nào đã dùng và kết quả chạy bù sau đó. Điều này giúp người đánh giá hiểu đầy đủ tiến trình và tránh tạo cảm giác rằng kiểm thử luôn đạt ngay từ đầu.

## 19. Ví dụ: sandbox thanh toán không sẵn sàng

Giả sử nhóm đang kiểm thử thay đổi luồng thanh toán. Sandbox của nhà cung cấp trả lỗi 503 và không có thời gian phục hồi chắc chắn.

### Phần có thể tiếp tục

Nhóm có thể chạy kiểm thử đơn vị cho tính toán số tiền và chuyển trạng thái; dùng stub để kiểm tra phản hồi thành công, từ chối và timeout; dùng service virtualization để mô phỏng webhook lặp hoặc đến trễ; chạy contract test với schema đã được quản lý; kiểm tra giao diện với backend giả; và kiểm tra xử lý idempotency trong thành phần của mình.

Các kết quả này được ghi là đạt trong phạm vi mô phỏng hoặc hợp đồng.

### Phần phải chờ

Nhóm vẫn cần sandbox thật để xác minh endpoint và thông tin xác thực hiện tại, payload thực tế và mã phản hồi, chữ ký webhook, thứ tự và hành vi giao nhận của nhà cung cấp, giới hạn tốc độ và quy tắc retry thực tế, cũng như đối soát giao dịch với nhà cung cấp.

### Cách đóng khoảng trống

Khi sandbox hoạt động lại, nhóm chạy smoke test an toàn, xác minh hợp đồng, thực hiện một giao dịch thử theo quy trình được phê duyệt, kiểm tra webhook và đối soát. Sau đó cập nhật báo cáo, liên kết kết quả với phiên bản ứng dụng và xác nhận các test bị blocked đã có bằng chứng.

Nếu các kiểm thử tích hợp thật là điều kiện phát hành, nhóm không được dùng kết quả stub để thay thế. Người có thẩm quyền phải quyết định chờ, giảm phạm vi phát hành hoặc chấp nhận rủi ro theo quy trình.

## 20. Ví dụ: môi trường staging và cơ sở dữ liệu dùng chung bị lỗi

Giả sử staging không truy cập được do database bị quá tải. Nhiều nhóm đang chạy kiểm thử E2E và một số nhóm đã tạo dữ liệu dở dang.

Một phương án phù hợp:

1. Điều phối viên thông báo staging đang suy giảm và tạm dừng nhóm E2E ghi dữ liệu.
2. Chủ sở hữu môi trường kiểm tra database, tải, kết nối và migration gần nhất.
3. Các nhóm tiếp tục test đơn vị, kiểm tra tĩnh và test thành phần cục bộ.
4. Nhóm cần xác minh tích hợp có thể dùng database tạm thời với schema tương thích, nếu mục tiêu cho phép.
5. Bảo toàn log và định danh các phiên chạy bị gián đoạn.
6. Sau khi database phục hồi, kiểm tra migration, dữ liệu và trạng thái các giao dịch dở dang.
7. Chạy smoke test và xác nhận staging sẵn sàng.
8. Chạy bù các luồng E2E quan trọng và cập nhật kết quả.

Không nên tự ý khởi động lại database hoặc reset dữ liệu khi chưa phối hợp với chủ sở hữu môi trường. Thao tác đó có thể làm mất bằng chứng hoặc ảnh hưởng các nhóm khác.

## 21. Theo dõi hiệu quả của phương án dự phòng

Các chỉ số giúp nhóm biết phương án có thực sự giảm gián đoạn và bảo toàn chất lượng hay không.

Có thể theo dõi:

- Số lần môi trường hoặc dịch vụ không sẵn sàng.
- Thời gian từ phát hiện đến khi kích hoạt phương án.
- Thời gian khôi phục môi trường chuẩn.
- Tỷ lệ test có thể tiếp tục bằng phương án thay thế.
- Số test bị blocked và thời gian tồn đọng.
- Số test dùng substitute cần chạy bù.
- Tỷ lệ chạy bù hoàn tất trong thời hạn.
- Số lần phương án dự phòng thất bại hoặc không dùng được.
- Số lỗi phát hiện do môi trường dự phòng lệch phiên bản hoặc dữ liệu.
- Thời gian công sức bị mất vì chờ, cấu hình lại hoặc khôi phục.

Không nên tối ưu chỉ số tỷ lệ test tiếp tục chạy bằng cách dùng mock cho mọi thứ. Một phương án tốt giảm thời gian chờ nhưng vẫn giữ rõ phần bằng chứng chưa có.

### Rà soát sau sự cố

Sau mỗi sự cố đáng kể, hãy xem nguyên nhân gốc là gì, tín hiệu phát hiện có đủ sớm không, phương án đã kích hoạt có phù hợp không, có test nào bị đánh dấu sai trạng thái không, có dữ liệu hoặc bằng chứng bị mất không, chạy bù có hoàn tất không, có cần cải thiện môi trường, hợp đồng hoặc service virtualization không, và ai sở hữu hành động phòng ngừa cùng thời hạn.

Tập trung vào cải thiện hệ thống và quy trình, không quy trách nhiệm cá nhân cho người phải xử lý tình huống bất ngờ.

## 22. Mẫu danh mục phụ thuộc và phương án dự phòng

~~~text
TÊN PHỤ THUỘC:
LOẠI:
NHÓM SỞ HỮU:
ĐẦU MỐI:
MỤC ĐÍCH TRONG KIỂM THỬ:
LUỒNG / BỘ TEST BỊ ẢNH HƯỞNG:

MỨC ĐỘ QUAN TRỌNG:
TÍN HIỆU KHÔNG SẴN SÀNG:
NGƯỠNG KÍCH HOẠT:
TIMEOUT / RETRY:

PHƯƠNG ÁN DỰ PHÒNG:
- Môi trường thay thế:
- Local / container:
- Mock / stub / fake:
- Service virtualization:
- Kiểm thử độc lập có thể tiếp tục:

GIỚI HẠN BẰNG CHỨNG:
TEST PHẢI CHỜ:
TEST CÓ THỂ TIẾP TỤC:
ĐIỀU KIỆN CHẶN PHÁT HÀNH:

CÁCH XÁC MINH PHƯƠNG ÁN:
CÁCH KHÔI PHỤC:
TEST CẦN CHẠY BÙ:
NGƯỜI PHÊ DUYỆT NGOẠI LỆ:
NGÀY DIỄN TẬP GẦN NHẤT:
NGÀY RÀ SOÁT TIẾP THEO:
~~~

## 23. Mẫu runbook kích hoạt và khôi phục

~~~text
SỰ CỐ:
THỜI ĐIỂM PHÁT HIỆN:
MÔI TRƯỜNG / DỊCH VỤ:
NGƯỜI ĐIỀU PHỐI:
NHÓM KHÔI PHỤC:

1. XÁC NHẬN
- Health check:
- Log / lỗi:
- Phạm vi ảnh hưởng:
- Nguyên nhân đã biết:

2. QUYẾT ĐỊNH
- Trạng thái: Suy giảm / Không sẵn sàng
- Phương án được chọn:
- Lý do:
- Người phê duyệt:
- Thời điểm kích hoạt:

3. KIỂM THỬ
- Nhóm test tiếp tục:
- Nhóm test bị blocked:
- Nhóm test dùng substitute:
- Giới hạn bằng chứng:
- Nhãn kết quả:

4. KHÔI PHỤC
- Điều kiện môi trường hoạt động:
- Phiên bản / schema / dữ liệu:
- Smoke test:
- Người xác nhận:
- Thời điểm mở lại:

5. CHẠY BÙ
- Test cần chạy:
- Thứ tự ưu tiên:
- Kết quả:
- Khoảng trống còn lại:

6. ĐÓNG SỰ CỐ
- Nguyên nhân:
- Tác động:
- Bài học:
- Hành động phòng ngừa:
- Người sở hữu:
- Thời hạn:
~~~

## 24. Những sai lầm thường gặp

- **Không lập phương án trước:** khi sự cố xảy ra, nhóm mới bắt đầu tìm endpoint, tài khoản và người hỗ trợ.
- **Dùng mock để thay thế mọi kiểm thử:** pipeline có thể xanh nhưng tích hợp thật chưa được xác minh.
- **Đánh dấu test bị chặn là đạt:** làm sai lệch bằng chứng và quyết định phát hành.
- **Chuyển môi trường mà không kiểm tra phiên bản:** schema, cấu hình hoặc dữ liệu khác biệt làm kết quả không đáng tin cậy.
- **Retry vô hạn:** kéo dài pipeline và tạo tải thêm cho dịch vụ đang lỗi.
- **Dùng endpoint thay thế không được phê duyệt:** có thể gây rủi ro dữ liệu, bảo mật hoặc sai hợp đồng.
- **Tắt kiểm tra xác thực hoặc TLS:** che giấu lỗi cấu hình và làm mất điều kiện kiểm chứng.
- **Không ghi nhận test dùng substitute:** người đọc không biết giới hạn bằng chứng.
- **Không chạy bù:** khoảng trống kiểm thử tồn tại đến lúc phát hành.
- **Reset môi trường thiếu phối hợp:** làm mất dữ liệu và ảnh hưởng nhóm khác.
- **Không diễn tập môi trường dự phòng:** chỉ phát hiện phương án không hoạt động khi đang cần.
- **Không có người quyết định ngoại lệ:** nhóm kiểm thử phải tự gánh quyết định rủi ro ngoài thẩm quyền.

## Kết luận

Phương án dự phòng cho môi trường và dịch vụ bên ngoài cần xác định phụ thuộc quan trọng, tín hiệu kích hoạt, lựa chọn thay thế, giới hạn bằng chứng, người chịu trách nhiệm và quy trình khôi phục. Nhóm có thể tiếp tục các kiểm thử độc lập hoặc dùng mock, stub, fake và service virtualization cho mục tiêu phù hợp, nhưng phải giữ riêng kết quả mô phỏng với bằng chứng từ phụ thuộc thật.

Khi môi trường chuẩn phục hồi, cần xác minh phiên bản, schema, dữ liệu và cấu hình, chạy smoke test rồi chạy bù các kiểm thử bị blocked hoặc chỉ được thực hiện bằng phương án thay thế. Một kế hoạch được diễn tập và có người sở hữu rõ ràng giúp nhóm giảm thời gian gián đoạn mà vẫn đưa ra quyết định chất lượng dựa trên bằng chứng trung thực.
