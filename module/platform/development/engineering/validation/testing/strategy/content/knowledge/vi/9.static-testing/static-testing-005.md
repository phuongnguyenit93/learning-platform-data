# Xác định mức bắt buộc và cách xử lý cảnh báo

Kiểm thử tĩnh giúp phát hiện vấn đề trong mã nguồn, cấu hình, phụ thuộc và tài liệu thiết kế mà không cần thực thi toàn bộ ứng dụng. Các hoạt động như rà soát mã, phân tích tĩnh, kiểm tra kiểu dữ liệu, quét bảo mật, kiểm tra bí mật và xác minh cấu hình hạ tầng có thể tìm ra lỗi sớm trong quy trình phát triển.

Tuy nhiên, nếu mọi phát hiện đều bị xem là nghiêm trọng và chặn mọi thay đổi, quy trình sẽ chậm, tạo nhiều cảnh báo không có giá trị và khiến nhóm tìm cách bỏ qua công cụ. Ngược lại, nếu tất cả kết quả chỉ được ghi nhận để tham khảo, các lỗi có ảnh hưởng lớn có thể đi qua mà không được xử lý.

Vì vậy, chiến lược kiểm thử cần xác định rõ mức nào là bắt buộc, phát hiện nào làm quy trình thất bại, cảnh báo nào cần được xử lý theo thời hạn và trường hợp nào có thể được miễn trừ. Quyết định cần dựa trên rủi ro của sản phẩm, độ tin cậy của công cụ, mức độ nghiêm trọng, khả năng khai thác và chi phí sửa lỗi.

Một chính sách tốt giúp nhóm hiểu cùng một cách về kết quả kiểm thử tĩnh: điều kiện nào phải đạt trước khi hợp nhất mã, điều gì cần xử lý trước phát hành, ai có quyền chấp nhận ngoại lệ và bằng chứng nào phải được lưu lại.

## 1. Kiểm thử tĩnh và cảnh báo là gì?

Kiểm thử tĩnh là hoạt động đánh giá sản phẩm hoặc các tạo tác phát triển mà không thực thi phần mềm theo cách sử dụng thông thường. Hoạt động có thể được thực hiện thủ công hoặc bằng công cụ.

Các hình thức phổ biến gồm:

- **Rà soát yêu cầu và thiết kế:** tìm mâu thuẫn, thiếu điều kiện, quy tắc chưa rõ hoặc rủi ro kiến trúc trước khi triển khai.
- **Rà soát mã nguồn:** kiểm tra tính đúng đắn, khả năng đọc, thiết kế, xử lý lỗi và các vấn đề tiềm ẩn.
- **Phân tích tĩnh mã nguồn:** phân tích cấu trúc và luồng dữ liệu để phát hiện lỗi lập trình, mẫu mã nguy hiểm hoặc vi phạm quy tắc.
- **Kiểm tra kiểu và biên dịch:** phát hiện kiểu dữ liệu không tương thích, tham chiếu sai hoặc lỗi cấu trúc trước khi chạy.
- **Lint và kiểm tra quy ước:** phát hiện mẫu mã không nhất quán, cấu trúc đáng ngờ hoặc vi phạm quy ước đã thống nhất.
- **Quét bảo mật mã nguồn:** tìm điểm yếu như dữ liệu đầu vào không được kiểm soát, cấu hình không an toàn hoặc bí mật được ghi trực tiếp trong mã.
- **Quét thành phần phụ thuộc:** phát hiện thư viện có lỗ hổng đã biết hoặc giấy phép cần xem xét.
- **Kiểm tra cấu hình và hạ tầng dưới dạng mã:** tìm quyền quá rộng, cấu hình mạng không an toàn hoặc tài nguyên được khai báo sai.

Công cụ thường tạo ra một hoặc nhiều phát hiện. Tùy sản phẩm, phát hiện có thể được gọi là issue, finding, violation hoặc warning. Trong bài này, “cảnh báo” là cách gọi chung cho kết quả cần được xem xét; một số cảnh báo có thể là lỗi thật, một số là rủi ro tiềm ẩn và một số có thể không áp dụng trong ngữ cảnh cụ thể.

### Phân biệt cảnh báo, lỗi và vi phạm chính sách

- **Cảnh báo** là tín hiệu từ công cụ hoặc người rà soát cho biết có điều cần chú ý.
- **Lỗi thực tế** là hành vi hoặc trạng thái sai đã được xác minh.
- **Vi phạm chính sách** là trường hợp không đáp ứng một quy tắc chất lượng hoặc bảo mật đã được tổ chức quy định.
- **Phát hiện giả** là cảnh báo không phản ánh vấn đề trong ngữ cảnh đang xét.
- **Rủi ro được chấp nhận** là vấn đề có thật hoặc chưa thể loại trừ nhưng được người có thẩm quyền chấp nhận trong phạm vi và thời hạn xác định.

Không nên tự động coi mọi cảnh báo là lỗi thực tế. Cũng không nên xem cảnh báo chưa tái hiện được là vô hại. Cần phân loại và xác minh trước khi quyết định chặn, sửa, theo dõi hoặc miễn trừ.

## 2. Xác định mức kiểm thử tĩnh bắt buộc

Mức bắt buộc là tập hợp các kiểm tra và ngưỡng mà một thay đổi phải đáp ứng trước khi được hợp nhất hoặc phát hành. Mức này cần đủ rõ để có thể tự động hóa, áp dụng nhất quán và giải thích được khi có ngoại lệ.

Không có một mức duy nhất phù hợp với mọi hệ thống. Một thư viện dùng nội bộ, một dịch vụ xử lý thanh toán và một hệ thống lưu dữ liệu nhạy cảm có thể cần chính sách khác nhau. Tuy vậy, tổ chức nên có một nền tảng tối thiểu chung để tránh mỗi nhóm tự chọn mức chất lượng tùy ý.

### Bắt đầu từ rủi ro và hậu quả

Khi xác định mức bắt buộc, hãy xem xét:

- Loại dữ liệu được xử lý: dữ liệu công khai, dữ liệu nội bộ, dữ liệu cá nhân hay dữ liệu nhạy cảm.
- Tác động nếu có lỗi: gián đoạn dịch vụ, mất dữ liệu, thiệt hại tài chính, lộ thông tin hoặc vi phạm nghĩa vụ.
- Mức độ phơi nhiễm: thành phần có được truy cập từ Internet, được nhiều hệ thống dùng chung hay chỉ chạy trong phạm vi hẹp.
- Vai trò của thành phần: thư viện dùng chung, dịch vụ xác thực, thanh toán, lưu trữ hay chức năng phụ trợ.
- Khả năng phát hiện và phục hồi: lỗi có thể được nhận biết nhanh, quay lui hoặc sửa dữ liệu an toàn không.
- Yêu cầu hợp đồng, pháp lý, bảo mật và tiêu chuẩn nội bộ.
- Mức độ trưởng thành của công cụ và khả năng xử lý kết quả của nhóm.

Một thành phần có quyền truy cập dữ liệu nhạy cảm cần kiểm tra bảo mật nghiêm ngặt hơn một trang nội dung tĩnh. Một thư viện dùng chung có thể cần quy tắc tương thích và kiểm tra phụ thuộc chặt hơn vì một lỗi có thể lan đến nhiều dịch vụ.

### Thiết lập một nền tảng tối thiểu chung

Nền tảng tối thiểu nên bao gồm những kiểm tra có chi phí thấp, phản hồi nhanh và có giá trị ổn định cho phần lớn thay đổi. Ví dụ:

- Mã phải biên dịch hoặc vượt qua kiểm tra cú pháp phù hợp.
- Kiểm tra kiểu và các quy tắc lint cốt lõi phải đạt.
- Không đưa bí mật như mật khẩu, khóa riêng hoặc token vào kho mã.
- Không thêm phụ thuộc có lỗ hổng nghiêm trọng đã xác minh mà chưa có quyết định xử lý.
- Các kiểm tra bắt buộc của kho mã và quy trình CI phải hoàn tất.
- Thay đổi phải được rà soát theo quy tắc bảo vệ nhánh hoặc quy trình tương đương.

Nền tảng này nên được áp dụng tự động cho mọi thay đổi liên quan. Nếu có ngoại lệ, ngoại lệ phải được ghi nhận theo quy trình thay vì bỏ qua kiểm tra âm thầm.

### Bổ sung yêu cầu theo mức rủi ro

Có thể chia thành ba mức tham khảo:

| Mức | Đặc điểm hệ thống hoặc thành phần | Kiểm tra bổ sung gợi ý |
|---|---|---|
| Cơ bản | Chức năng ít nhạy cảm, phạm vi ảnh hưởng nhỏ, dễ quay lui | Lint cốt lõi, kiểu dữ liệu, rà soát mã, kiểm tra bí mật và phụ thuộc |
| Tăng cường | Có dữ liệu quan trọng, tích hợp nhiều dịch vụ hoặc ảnh hưởng đáng kể đến người dùng | Phân tích tĩnh sâu hơn, kiểm tra cấu hình, quét bảo mật và rà soát phụ thuộc có chọn lọc |
| Nghiêm ngặt | Xử lý dữ liệu nhạy cảm, xác thực, phân quyền, thanh toán hoặc chức năng có hậu quả nghiêm trọng | Quy tắc bảo mật bắt buộc, rà soát chuyên môn, kiểm tra hạ tầng và phụ thuộc chặt, quản lý ngoại lệ có phê duyệt |

Tên mức và danh sách kiểm tra cần được điều chỉnh theo tổ chức. Không nên áp dụng mức nghiêm ngặt chỉ vì một thành phần được gắn nhãn quan trọng; cần xác định cụ thể rủi ro nào khiến kiểm tra bổ sung trở nên cần thiết.

### Định nghĩa rõ điểm chặn

Một kiểm tra bắt buộc cần trả lời:

- Kiểm tra chạy ở bước nào: máy phát triển, pull request, tích hợp liên tục hay trước phát hành?
- Điều kiện đạt và không đạt là gì?
- Phát hiện nào làm thất bại pipeline?
- Ai nhận thông báo và chịu trách nhiệm sửa?
- Có cho phép miễn trừ không, ai phê duyệt và thời hạn bao lâu?
- Nếu công cụ không khả dụng, quy trình thay thế là gì?

Nếu chỉ ghi “phải chạy phân tích tĩnh”, chính sách vẫn còn mơ hồ. Cần nêu quy tắc nào là chặn, ngưỡng nào được phép và cách xử lý khi kết quả không thể phân loại tự động.

## 3. Phân loại mức độ nghiêm trọng của phát hiện

Mức độ nghiêm trọng mô tả hậu quả tiềm tàng nếu vấn đề là thật và xảy ra. Mức này cần được định nghĩa nhất quán để các nhóm không tùy tiện diễn giải cùng một loại phát hiện.

Có thể dùng thang bốn mức:

| Mức | Ý nghĩa | Ví dụ |
|---|---|---|
| Nghiêm trọng (Critical) | Có thể gây xâm phạm bảo mật lớn, mất dữ liệu nghiêm trọng hoặc làm hệ thống cốt lõi không thể hoạt động | Bí mật quản trị bị lộ; lỗ hổng cho phép thực thi mã từ xa trong dịch vụ phơi nhiễm |
| Cao (High) | Có thể gây ảnh hưởng lớn đến dữ liệu, quyền truy cập, giao dịch hoặc tính sẵn sàng | Bỏ qua kiểm tra quyền ở API nhạy cảm; lỗ hổng nghiêm trọng trong thành phần đang sử dụng |
| Trung bình (Medium) | Có thể tạo lỗi hoặc rủi ro đáng kể trong điều kiện nhất định, nhưng phạm vi hoặc khả năng khai thác hạn chế hơn | Xử lý đầu vào chưa chặt ở một luồng ít phơi nhiễm; cấu hình có thể làm lộ thông tin hạn chế |
| Thấp (Low) | Tác động nhỏ, khó khai thác hoặc chủ yếu ảnh hưởng khả năng bảo trì | Mẫu mã khó đọc, cảnh báo kiểu không ảnh hưởng đường chạy quan trọng |

Tên mức có thể khác nhau giữa công cụ. Tổ chức cần ánh xạ các mức từ nhiều nguồn về một cách phân loại thống nhất.

### Không đồng nhất mức nghiêm trọng với mức ưu tiên

Mức nghiêm trọng nói về hậu quả nếu vấn đề xảy ra. Mức ưu tiên nói về thứ tự cần xử lý trong bối cảnh hiện tại. Một phát hiện nghiêm trọng ở mã không được triển khai hoặc không thể tiếp cận có thể cần xác minh ngữ cảnh trước khi quyết định. Một phát hiện trung bình trong thành phần được truy cập rộng và đang thay đổi thường xuyên có thể cần xử lý sớm.

Khi ưu tiên, hãy kết hợp:

- Mức nghiêm trọng.
- Khả năng khai thác hoặc xảy ra.
- Mức độ phơi nhiễm của thành phần.
- Khả năng phát hiện và giảm thiểu.
- Tính sẵn có của bản vá hoặc biện pháp thay thế.
- Mức độ ảnh hưởng của thay đổi nếu sửa ngay.

Không nên tự hạ mức nghiêm trọng chỉ vì việc sửa lỗi khó hoặc tốn thời gian. Nếu chưa thể sửa, hãy ghi nhận rủi ro và xin quyết định ngoại lệ phù hợp.

## 4. Đánh giá độ tin cậy và mức chắc chắn của cảnh báo

Hai cảnh báo cùng mức nghiêm trọng không nhất thiết có cùng độ tin cậy. Một cảnh báo có thể chỉ ra luồng dữ liệu nguy hiểm có thể đi đến điểm sử dụng nhạy cảm; cảnh báo khác có thể được tạo từ một mẫu mã tổng quát mà công cụ chưa hiểu đầy đủ ngữ cảnh.

Cần xem xét:

- Công cụ có hỗ trợ chính xác ngôn ngữ, framework và phiên bản đang dùng không?
- Quy tắc có được kích hoạt trong đúng ngữ cảnh hay chỉ dựa trên mẫu mã?
- Đường dữ liệu hoặc điều kiện gây vấn đề có thể thực sự xảy ra không?
- Phụ thuộc có được sử dụng trong sản phẩm hoặc chỉ tồn tại trong công cụ phát triển?
- Phiên bản bị ảnh hưởng có nằm trong phạm vi triển khai không?
- Công cụ có bằng chứng như vị trí nguồn, đường đi dữ liệu hoặc phiên bản thư viện không?
- Cảnh báo đã được xác minh trước đây hay thường xuyên tạo kết quả giả?

Có thể ghi thêm mức chắc chắn:

| Mức chắc chắn | Diễn giải | Cách xử lý gợi ý |
|---|---|---|
| Cao | Có đường đi hoặc bằng chứng cụ thể hỗ trợ phát hiện | Xác minh nhanh và áp dụng chính sách theo mức nghiêm trọng |
| Trung bình | Có dấu hiệu hợp lý nhưng cần kiểm tra ngữ cảnh | Phân tích bổ sung, kiểm tra cấu hình hoặc tái hiện phù hợp |
| Thấp | Phát hiện dựa trên mẫu tổng quát hoặc thiếu thông tin | Triage để xác định có áp dụng; không tự động bỏ qua nếu hậu quả tiềm tàng cao |

Độ chắc chắn thấp không có nghĩa là rủi ro thấp. Nếu phát hiện có thể gây hậu quả nghiêm trọng, cần xác minh với mức ưu tiên phù hợp thay vì loại bỏ chỉ vì công cụ chưa đủ bằng chứng.

## 5. Quy định cảnh báo nào làm chặn quy trình

Không phải mọi cảnh báo đều nên chặn pipeline. Chính sách cần phân biệt phát hiện vi phạm ngưỡng bắt buộc với khuyến nghị cải thiện.

Một mô hình tham khảo:

| Loại phát hiện | Xử lý mặc định trong pull request | Theo dõi tiếp |
|---|---|---|
| Lỗi biên dịch, kiểu hoặc cú pháp bắt buộc | Chặn | Sửa trước khi hợp nhất |
| Bí mật thật được xác minh trong mã | Chặn và xử lý bí mật | Thu hồi hoặc xoay vòng bí mật, kiểm tra lịch sử |
| Lỗ hổng nghiêm trọng có khả năng áp dụng | Chặn hoặc yêu cầu phê duyệt khẩn cấp theo chính sách | Cập nhật, loại bỏ hoặc giảm thiểu rủi ro |
| Lỗ hổng cao | Chặn theo ngưỡng đã thống nhất hoặc đặt hạn xử lý rất ngắn | Theo dõi đến khi đóng |
| Cảnh báo trung bình | Thường không chặn mọi thay đổi; tạo công việc có chủ sở hữu | Xử lý theo thời hạn và mức phơi nhiễm |
| Cảnh báo thấp về khả năng bảo trì | Không chặn trừ khi vi phạm quy tắc cụ thể | Đưa vào backlog hoặc xử lý khi sửa khu vực liên quan |
| Cảnh báo chưa rõ hoặc có khả năng là giả | Chuyển triage | Xác minh và ghi quyết định |

Bảng này là ví dụ. Chính sách thực tế cần căn cứ vào rủi ro, yêu cầu tuân thủ và độ tin cậy của công cụ. Một cảnh báo trung bình có thể trở thành điều kiện chặn nếu nó vi phạm quy tắc bắt buộc của một thành phần nhạy cảm. Một cảnh báo cao có thể cần quy trình khẩn cấp riêng nếu hệ thống đang bị khai thác.

### Tránh đặt ngưỡng chỉ dựa trên số lượng

Quy tắc “không được có quá mười cảnh báo” không thể hiện rõ rủi ro. Một cảnh báo nghiêm trọng không thể được bù trừ bởi hàng trăm cảnh báo thấp. Ngược lại, hàng trăm cảnh báo cũ có thể khiến nhóm không nhìn thấy phát hiện mới.

Nên dùng điều kiện theo mức và ngữ cảnh, ví dụ:

- Không có phát hiện Critical mới chưa được xử lý hoặc chấp nhận hợp lệ.
- Không có phát hiện High mới trong phạm vi triển khai mà chưa có quyết định.
- Các kiểm tra bắt buộc phải chạy thành công.
- Phát hiện Medium có người sở hữu và thời hạn xử lý.
- Phát hiện Low được ghi nhận hoặc xử lý cùng thay đổi liên quan.

## 6. Xử lý cảnh báo theo một quy trình thống nhất

Một quy trình xử lý cảnh báo nên đưa kết quả từ lúc công cụ phát hiện đến khi được đóng, miễn trừ hoặc chấp nhận rủi ro.

### Bước 1: Tiếp nhận và chuẩn hóa

Thu thập mã phát hiện, công cụ, quy tắc, vị trí, phiên bản, mức nghiêm trọng, mức chắc chắn và bằng chứng. Nếu nhiều công cụ báo cùng một vấn đề, liên kết chúng để tránh tạo nhiều công việc trùng lặp.

### Bước 2: Loại bỏ trùng lặp và xác định phạm vi

Xác định phát hiện đã tồn tại hay mới xuất hiện, ảnh hưởng đến nhánh nào, môi trường nào và phiên bản nào. Kiểm tra xem mã hoặc phụ thuộc có thực sự được triển khai và sử dụng hay không.

### Bước 3: Triage và xác minh

Người có chuyên môn xem xét liệu cảnh báo có áp dụng, đường đi có thể xảy ra và hậu quả là gì. Kết quả triage có thể là:

- Vấn đề thật, cần sửa.
- Vấn đề thật nhưng có biện pháp giảm thiểu tạm thời.
- Cảnh báo không áp dụng trong ngữ cảnh này.
- Phát hiện giả do giới hạn của công cụ.
- Chưa đủ bằng chứng, cần điều tra thêm.

Không nên đánh dấu false positive chỉ vì chưa tái hiện được lỗi. Cần nêu lý do kỹ thuật và bằng chứng hỗ trợ.

### Bước 4: Chọn hành động

Tùy kết quả, nhóm có thể:

- Sửa mã hoặc cấu hình.
- Nâng cấp, thay thế hoặc loại bỏ phụ thuộc.
- Thu hồi và xoay vòng bí mật đã lộ.
- Thêm kiểm tra hoặc ràng buộc để ngăn điều kiện nguy hiểm.
- Bổ sung kiểm thử động hoặc kiểm thử tích hợp để xác minh hành vi.
- Chấp nhận rủi ro trong thời hạn có kiểm soát.
- Đánh dấu phát hiện không áp dụng với lý do có thể kiểm tra lại.

### Bước 5: Xác minh và đóng

Sau khi sửa, chạy lại công cụ hoặc kiểm tra phù hợp để xác nhận phát hiện đã được xử lý. Với vấn đề bảo mật, cần kiểm tra cả khả năng khai thác và biện pháp giảm thiểu. Với thay đổi mã, cần bảo đảm sửa lỗi không tạo hồi quy.

Chỉ đóng phát hiện khi có bằng chứng. Nếu vấn đề được chấp nhận hoặc miễn trừ, trạng thái phải thể hiện rõ đây là quyết định quản lý rủi ro, không phải lỗi đã được sửa.

## 7. Phân biệt false positive, not applicable và accepted risk

Ba trạng thái này thường bị dùng lẫn lộn nhưng có ý nghĩa khác nhau.

- **False positive (phát hiện giả):** công cụ báo có vấn đề nhưng sau khi kiểm tra, điều kiện mà quy tắc mô tả không tồn tại trong mã hoặc ngữ cảnh thực tế. Ví dụ, công cụ nhận diện một chuỗi giống khóa bí mật nhưng đó là giá trị giả được tài liệu hóa.
- **Not applicable (không áp dụng):** quy tắc có thể đúng trong trường hợp tổng quát nhưng không liên quan đến thành phần hoặc cấu hình cụ thể. Ví dụ, một thư viện được đánh dấu có lỗ hổng ở chức năng mà sản phẩm không sử dụng; tuy vậy cần xem xét khả năng gọi gián tiếp và điều kiện khai thác trước khi kết luận.
- **Accepted risk (rủi ro được chấp nhận):** vấn đề là thật hoặc chưa thể loại trừ, nhưng người có thẩm quyền quyết định tạm thời không xử lý vì lý do được ghi nhận. Ví dụ, bản vá có nguy cơ làm hỏng tương thích và cần thời gian chuẩn bị triển khai.

Không được dùng false positive để né việc sửa một vấn đề khó. Không được dùng not applicable nếu chưa xác minh cấu hình và đường sử dụng. Không được dùng accepted risk như trạng thái vô thời hạn.

### Thông tin cần có khi loại trừ cảnh báo

Một quyết định loại trừ nên ghi:

- Mã phát hiện và quy tắc liên quan.
- Phạm vi loại trừ: dòng mã, tệp, thành phần, phiên bản hoặc môi trường.
- Lý do kỹ thuật cụ thể.
- Bằng chứng hỗ trợ.
- Người xem xét và thời điểm.
- Ngày hết hạn hoặc điều kiện xem xét lại.
- Liên kết đến công việc hoặc quyết định liên quan nếu có.

Phạm vi loại trừ phải hẹp nhất có thể. Nếu một dòng mã không áp dụng, không nên tắt toàn bộ quy tắc cho cả kho mã. Nếu cảnh báo phụ thuộc vào một cấu hình, cần giới hạn ngoại lệ ở cấu hình đó.

## 8. Quản lý baseline và cảnh báo tồn đọng

Ở hệ thống lâu năm, lần đầu bật phân tích tĩnh có thể tạo ra rất nhiều cảnh báo cũ. Nếu chặn toàn bộ ngay lập tức, nhóm có thể không thể hợp nhất thay đổi và mất động lực cải thiện.

Baseline là tập hợp các phát hiện đã tồn tại tại một thời điểm được xác định. Baseline giúp phân biệt phát hiện cũ với phát hiện mới để nhóm cải thiện dần mà không bỏ qua rủi ro mới.

Một cách triển khai:

1. Chạy công cụ trên nhánh chuẩn và lưu danh sách phát hiện hiện có.
2. Phân loại những phát hiện nghiêm trọng, đặc biệt là bảo mật và bí mật.
3. Đặt điều kiện không cho phát sinh thêm phát hiện vượt ngưỡng.
4. Tạo backlog cho cảnh báo cũ, gắn người sở hữu và thời hạn theo rủi ro.
5. Xử lý cảnh báo cũ khi sửa khu vực liên quan hoặc theo kế hoạch riêng.
6. Cập nhật baseline khi có thay đổi chính sách hoặc phiên bản công cụ, kèm lý do.
7. Định kỳ rà soát để tránh biến baseline thành nơi lưu trữ cảnh báo vô thời hạn.

Baseline không phải giấy phép bỏ qua vấn đề cũ. Những phát hiện nghiêm trọng, bí mật đã lộ hoặc rủi ro có thể bị khai thác cần được xử lý theo quy trình khẩn cấp dù chúng xuất hiện trước khi thiết lập baseline.

### Ngăn cảnh báo mới bị che khuất

Nên hiển thị riêng phát hiện mới, phát hiện đã tồn tại và phát hiện đã được miễn trừ. Pull request cần tập trung vào thay đổi mới, nhưng người chịu trách nhiệm bảo mật vẫn cần nhìn thấy toàn bộ rủi ro đang tồn tại.

Nếu công cụ thay đổi phiên bản hoặc bộ quy tắc, số lượng cảnh báo có thể tăng hoặc giảm mà không phải do mã nguồn thay đổi. Cần ghi nhận phiên bản công cụ, cấu hình và thời điểm cập nhật để so sánh có ý nghĩa.

## 9. Đặt kiểm thử tĩnh vào các giai đoạn của quy trình phát triển

Không phải kiểm tra nào cũng cần chạy ở mọi thời điểm. Việc phân tầng thực thi giúp phản hồi nhanh cho nhà phát triển và vẫn có kiểm tra sâu trước phát hành.

| Thời điểm | Kiểm tra phù hợp | Mục tiêu |
|---|---|---|
| Khi phát triển cục bộ | Lint nhanh, kiểu dữ liệu, định dạng, kiểm tra bí mật cục bộ | Phản hồi ngay khi viết mã |
| Khi tạo pull request | Kiểm tra bắt buộc, phân tích tĩnh, quét bảo mật và phụ thuộc theo chính sách | Ngăn vấn đề mới đi vào nhánh chính |
| Sau khi hợp nhất hoặc theo lịch | Phân tích sâu, quét toàn bộ kho mã, kiểm tra cấu hình và báo cáo xu hướng | Phát hiện vấn đề rộng hoặc phát hiện mới từ bộ quy tắc |
| Trước phát hành | Kiểm tra phụ thuộc và cấu hình triển khai, rà soát ngoại lệ còn hiệu lực | Xác nhận điều kiện phát hành |
| Sau triển khai | Kiểm tra vận hành, đối chiếu cấu hình và theo dõi cảnh báo liên quan | Xác minh môi trường thực tế và phát hiện sai lệch |

### Phản hồi nhanh trong pull request

Các kiểm tra ở pull request nên đủ nhanh để không làm gián đoạn vòng phản hồi. Chỉ những quy tắc có giá trị chặn rõ ràng mới nên trở thành cổng bắt buộc. Phát hiện cần hiển thị vị trí, lý do, mức độ và hướng xử lý.

### Kiểm tra sâu theo lịch hoặc trước phát hành

Một số phân tích tốn thời gian hoặc cần quyền truy cập rộng có thể chạy theo lịch hoặc trong pipeline phát hành. Kết quả vẫn phải có chủ sở hữu và thời hạn xử lý. Chạy kiểm tra mà không ai xem kết quả không tạo ra kiểm soát thực chất.

### Xử lý khi công cụ không khả dụng

Chính sách cần nêu cách xử lý khi dịch vụ phân tích tĩnh ngừng hoạt động, hết license hoặc không thể tải dữ liệu quy tắc. Với kiểm tra bảo mật nghiêm trọng, có thể cần dừng hợp nhất cho đến khi có kết quả hoặc quy trình kiểm tra thay thế được phê duyệt. Với kiểm tra chất lượng ít rủi ro, có thể cho phép tiếp tục có điều kiện và chạy bù sau đó.

Không nên để trạng thái “không chạy được” bị hiểu nhầm thành “đã đạt”. Pipeline cần phân biệt rõ passed, failed, skipped và unavailable.

## 10. Thiết kế chính sách cảnh báo có thể vận hành

Một chính sách tốt cần đủ cụ thể để công cụ và con người áp dụng nhất quán.

### Nội dung chính sách

Tối thiểu nên quy định:

- Các loại kiểm tra bắt buộc theo sản phẩm hoặc mức rủi ro.
- Phiên bản công cụ và bộ quy tắc được sử dụng.
- Ngưỡng nghiêm trọng và điều kiện chặn.
- Cách đánh giá độ chắc chắn và khả năng áp dụng.
- Thời hạn xử lý theo mức ưu tiên.
- Người hoặc nhóm chịu trách nhiệm triage và sửa lỗi.
- Cách ghi nhận false positive, not applicable và accepted risk.
- Quy trình phê duyệt, thời hạn và phạm vi miễn trừ.
- Cách quản lý baseline và phát hiện cũ.
- Cách xử lý khi công cụ lỗi hoặc kết quả không đầy đủ.
- Nơi lưu bằng chứng và cách báo cáo.

### Ví dụ về thời hạn xử lý

| Mức ưu tiên | Hành động gợi ý | Thời hạn tham khảo |
|---|---|---|
| Khẩn cấp | Cô lập, thu hồi bí mật hoặc triển khai biện pháp giảm thiểu ngay | Ngay khi xác minh |
| Cao | Sửa trước phát hành hoặc xin quyết định ngoại lệ có thời hạn ngắn | Trong chu kỳ hiện tại |
| Trung bình | Giao người sở hữu, lập kế hoạch và theo dõi | Theo kế hoạch đã thống nhất |
| Thấp | Xử lý khi sửa khu vực liên quan hoặc trong đợt bảo trì | Theo backlog |

Thời hạn thực tế cần được điều chỉnh theo mức độ phơi nhiễm, khả năng khai thác, yêu cầu tuân thủ và năng lực phản ứng. Không nên coi thời hạn tham khảo là tiêu chuẩn phổ quát.

## 11. Quy trình miễn trừ có kiểm soát

Có những trường hợp không thể sửa ngay mà không gây rủi ro lớn hơn, chẳng hạn bản vá chưa tương thích hoặc thay đổi ảnh hưởng đến hệ thống đang vận hành. Khi đó, cần cơ chế miễn trừ rõ ràng.

Một yêu cầu miễn trừ nên nêu:

1. Phát hiện và phạm vi bị ảnh hưởng.
2. Lý do chưa thể sửa ngay.
3. Hậu quả nếu vấn đề xảy ra.
4. Biện pháp giảm thiểu tạm thời.
5. Người chịu trách nhiệm theo dõi.
6. Người có thẩm quyền chấp nhận.
7. Thời hạn hết hiệu lực hoặc điều kiện bắt buộc xem xét lại.
8. Kế hoạch xử lý lâu dài.

Ví dụ, một phụ thuộc có lỗ hổng mức cao chưa có bản vá tương thích. Nhóm có thể hạn chế chức năng liên quan, chặn đường truy cập từ bên ngoài, tăng giám sát và đặt lịch nâng cấp. Quyết định này phải có thời hạn, người phê duyệt và điều kiện chấm dứt ngoại lệ.

Miễn trừ không nên áp dụng cho bí mật đã bị lộ mà chưa được thu hồi hoặc cho rủi ro đang bị khai thác nếu không có biện pháp phản ứng phù hợp. Những trường hợp đó cần xử lý sự cố và giảm thiểu khẩn cấp theo chính sách bảo mật.

## 12. Ví dụ: thiết lập mức bắt buộc cho một dịch vụ thanh toán

Giả sử một dịch vụ thanh toán xử lý thông tin giao dịch, giao tiếp với nhà cung cấp bên ngoài và cập nhật trạng thái đơn hàng. Nhóm muốn thiết lập quy tắc kiểm thử tĩnh cho mọi pull request.

Có thể xây dựng chính sách minh họa như sau:

| Nhóm kiểm tra | Mức bắt buộc | Cách xử lý phát hiện |
|---|---|---|
| Biên dịch, kiểu và lint cốt lõi | Bắt buộc trên mọi thay đổi | Chặn nếu không đạt |
| Bí mật và khóa truy cập | Bắt buộc trên mọi thay đổi | Chặn phát hiện bí mật thật; thu hồi nếu đã lộ |
| Phân tích bảo mật mã nguồn | Bắt buộc, áp dụng quy tắc phù hợp với dịch vụ | Chặn phát hiện nghiêm trọng đã xác minh; phát hiện cao theo ngưỡng chính sách |
| Thành phần phụ thuộc | Bắt buộc khi thêm hoặc nâng cấp phụ thuộc và kiểm tra lại trước phát hành | Xác minh khả năng áp dụng, nâng cấp hoặc miễn trừ có thời hạn |
| Cấu hình hạ tầng | Bắt buộc với thay đổi hạ tầng liên quan | Chặn quyền quá rộng hoặc cấu hình vi phạm chính sách |
| Rà soát mã | Bắt buộc trước khi hợp nhất | Người rà soát xác nhận logic, xử lý lỗi và tác động dữ liệu |
| Cảnh báo bảo trì mức thấp | Theo dõi, không tự động chặn mọi thay đổi | Giao backlog và xử lý theo kế hoạch |

Một cảnh báo về bí mật cần được xác minh nhanh. Nếu đó là khóa thật, việc xóa khỏi dòng mã hiện tại chưa đủ vì khóa có thể còn trong lịch sử hoặc đã được sử dụng. Nhóm cần thu hồi hoặc xoay vòng khóa và kiểm tra nơi có thể đã bị truy cập.

Một cảnh báo về phụ thuộc cần được kiểm tra phiên bản, cấu hình triển khai và việc có sử dụng chức năng dễ bị ảnh hưởng hay không. Nếu chưa có bản vá tương thích, nhóm cần ghi nhận rủi ro, biện pháp giảm thiểu và thời hạn xem xét.

Ví dụ này cho thấy mức bắt buộc không chỉ là danh sách công cụ. Nó còn bao gồm ngưỡng, người xử lý, quyết định phát hành và cách quản lý rủi ro còn lại.

## 13. Theo dõi chất lượng của chính quy trình cảnh báo

Chính sách cảnh báo cũng cần được đánh giá. Một quy trình quá nghiêm có thể tạo nhiều cảnh báo giả và làm chậm phát triển; một quy trình quá lỏng có thể để vấn đề nghiêm trọng đi qua.

Một số chỉ số có thể theo dõi:

- Số phát hiện mới theo mức nghiêm trọng và loại quy tắc.
- Tỷ lệ phát hiện được xác minh là vấn đề thật.
- Tỷ lệ false positive và not applicable theo công cụ hoặc quy tắc.
- Thời gian từ khi phát hiện đến khi triage và đóng.
- Số ngoại lệ đang hiệu lực và số ngoại lệ quá hạn.
- Số phát hiện cũ chưa có chủ sở hữu.
- Tỷ lệ pipeline thất bại do lỗi công cụ hoặc cấu hình.
- Số vấn đề tĩnh dẫn đến lỗi hoặc sự cố sau phát hành.
- Thời gian phản hồi của các kiểm tra bắt buộc.

Không nên tối ưu một chỉ số đơn lẻ. Giảm số cảnh báo có thể chỉ vì nhóm tắt quy tắc; giảm thời gian triage có thể do đánh dấu false positive quá nhanh; tăng số lỗi tìm được có thể phản ánh công cụ tốt hơn. Cần đọc chỉ số cùng chất lượng xác minh và kết quả thực tế.

Định kỳ xem lại các quy tắc tạo nhiều cảnh báo không có giá trị, cập nhật phiên bản công cụ, điều chỉnh ngưỡng và đào tạo nhóm cách xử lý. Mọi thay đổi chính sách chặn cần được truyền đạt rõ và có thời điểm áp dụng.

## 14. Những sai lầm thường gặp

- **Chặn mọi cảnh báo:** tạo nhiễu, kéo dài thời gian phản hồi và làm nhóm mất niềm tin vào công cụ.
- **Không chặn bất kỳ cảnh báo nào:** phát hiện nghiêm trọng có thể bị bỏ qua hoặc không có người theo dõi.
- **Dùng mức nghiêm trọng của công cụ mà không xem ngữ cảnh:** có thể đánh giá sai khả năng áp dụng hoặc hậu quả thực tế.
- **Đánh đồng false positive với accepted risk:** một phát hiện giả và một rủi ro có thật cần cách quản lý khác nhau.
- **Tắt quy tắc trên toàn kho mã để xử lý một cảnh báo:** làm giảm khả năng phát hiện ở các khu vực khác.
- **Miễn trừ không có thời hạn:** ngoại lệ có thể trở thành trạng thái vĩnh viễn.
- **Chỉ xử lý cảnh báo mới:** nợ cũ nghiêm trọng có thể tiếp tục gây rủi ro.
- **Đánh dấu kiểm tra đạt khi công cụ không chạy:** làm sai lệch bằng chứng chất lượng.
- **Không xác minh sau khi sửa:** phát hiện có thể vẫn tồn tại hoặc lỗi mới có thể xuất hiện.
- **Đo thành công bằng số cảnh báo giảm:** số lượng thấp không chứng minh rủi ro đã được kiểm soát.

## 15. Mẫu quyết định cho một cảnh báo

Có thể dùng mẫu sau để thống nhất cách triage và xử lý:

~~~text
MÃ PHÁT HIỆN:
CÔNG CỤ / QUY TẮC:
VỊ TRÍ / PHIÊN BẢN:
MÔ TẢ:

MỨC NGHIÊM TRỌNG:
ĐỘ CHẮC CHẮN:
KHẢ NĂNG ÁP DỤNG:
HẬU QUẢ TIỀM TÀNG:

KẾT QUẢ TRIAGE:
- Vấn đề thật
- False positive
- Not applicable
- Chưa đủ bằng chứng
- Accepted risk

BẰNG CHỨNG VÀ LÝ DO:

HÀNH ĐỘNG:
- Sửa mã hoặc cấu hình
- Nâng cấp hoặc loại bỏ phụ thuộc
- Bổ sung biện pháp giảm thiểu
- Điều tra thêm
- Miễn trừ có thời hạn

CHỦ SỞ HỮU:
NGƯỜI PHÊ DUYỆT (NẾU CẦN):
THỜI HẠN:
NGÀY XEM XÉT LẠI:

KẾT QUẢ XÁC MINH SAU XỬ LÝ:
LIÊN KẾT BẰNG CHỨNG:
TRẠNG THÁI CUỐI:
~~~

Mẫu này giúp giữ lại lý do ra quyết định. Người xem xét sau này có thể hiểu vì sao một cảnh báo bị chặn, được sửa, được loại trừ hoặc được chấp nhận trong một khoảng thời gian.

## Kết luận

Xác định mức kiểm thử tĩnh bắt buộc là quyết định về rủi ro, ngưỡng chất lượng và trách nhiệm. Nền tảng chung giúp mọi thay đổi vượt qua các kiểm tra tối thiểu; yêu cầu bổ sung được áp dụng theo mức nhạy cảm và hậu quả của thành phần. Cảnh báo cần được đánh giá theo mức nghiêm trọng, độ chắc chắn và khả năng áp dụng trước khi quyết định chặn, sửa, theo dõi hoặc miễn trừ.

Khi chính sách quy định rõ điều kiện chặn, quy trình triage, người sở hữu, thời hạn và bằng chứng đóng cảnh báo, kiểm thử tĩnh có thể cung cấp phản hồi sớm mà không làm quy trình phát triển mất kiểm soát. Chính sách cũng cần được xem xét định kỳ để giữ cân bằng giữa an toàn, chất lượng và tốc độ phát triển.
