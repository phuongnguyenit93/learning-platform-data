# Phân bổ mục tiêu giữa đơn vị, tích hợp, hệ thống và chấp nhận

Một chiến lược kiểm thử xác thực cần trả lời hai câu hỏi: sản phẩm phải chứng minh điều gì và ở cấp nào nên thu thập bằng chứng đó. Nếu mọi mục tiêu đều được dồn vào kiểm thử đầu cuối, phản hồi thường chậm, khó xác định nguyên nhân lỗi và tốn kém khi bảo trì. Nếu chỉ dựa vào kiểm thử đơn vị, nhóm có thể có nhiều kiểm thử chạy nhanh nhưng vẫn bỏ sót lỗi giữa các thành phần hoặc hành trình người dùng không hoàn thành.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, phân bổ mục tiêu giữa kiểm thử đơn vị, tích hợp, hệ thống và chấp nhận giúp nhóm chọn đúng đối tượng kiểm thử, phương pháp, môi trường và người chịu trách nhiệm. Mỗi cấp kiểm thử tạo ra một loại bằng chứng khác nhau. Chúng bổ trợ cho nhau để xác nhận từ logic nhỏ nhất đến giá trị mà người dùng và doanh nghiệp mong đợi.

## 1. Hiểu cấp kiểm thử và mục tiêu cần xác thực

### Bốn cấp kiểm thử trả lời bốn nhóm câu hỏi

Cấp kiểm thử mô tả phạm vi hoặc đối tượng đang được kiểm tra. Một cách phân chia phổ biến gồm:

| Cấp kiểm thử | Đối tượng chính | Câu hỏi trọng tâm |
|---|---|---|
| Đơn vị (unit) | Hàm, phương thức, lớp hoặc thành phần nhỏ được cô lập | Logic cục bộ có thực hiện đúng quy tắc đã định không? |
| Tích hợp (integration) | Giao tiếp giữa hai hay nhiều thành phần, dịch vụ hoặc hệ thống | Các thành phần có trao đổi dữ liệu và phối hợp đúng hợp đồng không? |
| Hệ thống (system) | Hệ thống đã tích hợp trong cấu hình đại diện | Sản phẩm có đáp ứng yêu cầu và hành vi đầu cuối trong bối cảnh đã xác định không? |
| Chấp nhận (acceptance) | Sản phẩm hoặc quy trình được đánh giá theo tiêu chí của người nhận kết quả | Giải pháp có đáp ứng nhu cầu, quy tắc nghiệp vụ và điều kiện chấp nhận không? |

Các cấp có thể chồng lấn trong thực tế. Một bài kiểm thử có thể chạy qua nhiều thành phần nhưng vẫn được phân loại là kiểm thử tích hợp nếu mục tiêu chính là xác minh hợp đồng giữa các thành phần đó. Tương tự, một bài kiểm thử qua giao diện có thể là kiểm thử hệ thống hoặc chấp nhận tùy vào tiêu chí và người ra quyết định.

Điều quan trọng là nhóm thống nhất mục tiêu và phạm vi của từng bài kiểm thử. Không nên phân loại chỉ dựa vào công cụ, vị trí chạy hoặc tên thư mục.

### Phân biệt cấp kiểm thử với loại kiểm thử

Cấp kiểm thử và loại kiểm thử là hai chiều khác nhau:

- **Cấp kiểm thử** cho biết kiểm tra đối tượng hoặc phạm vi nào: đơn vị, tích hợp, hệ thống hay chấp nhận.
- **Loại kiểm thử** cho biết đặc tính hoặc rủi ro nào đang được xem xét: chức năng, hiệu năng, bảo mật, khả năng sử dụng, khả năng tiếp cận, độ tin cậy, tương thích hoặc phục hồi.

Ví dụ, kiểm thử hiệu năng có thể được thực hiện ở cấp thành phần để đo thời gian xử lý một thuật toán, ở cấp tích hợp để đo độ trễ qua một dịch vụ phụ thuộc, hoặc ở cấp hệ thống để đo hành trình dưới tải đại diện. Kiểm thử bảo mật cũng có thể xuất hiện ở nhiều cấp.

Vì vậy, không nên hiểu rằng kiểm thử đơn vị chỉ kiểm tra chức năng, còn kiểm thử hệ thống mới kiểm tra hiệu năng hoặc bảo mật. Hãy phân bổ từng mục tiêu theo nơi có thể tạo ra bằng chứng phù hợp nhất.

### Bắt đầu từ mục tiêu, không bắt đầu từ tỷ lệ

Một số nhóm dùng tỷ lệ như 70% đơn vị, 20% tích hợp và 10% đầu cuối làm điểm tham khảo. Tỷ lệ này không phải quy tắc phổ quát. Một hệ thống có nhiều thuật toán nghiệp vụ có thể cần nhiều kiểm thử đơn vị; một sản phẩm dựa trên nhiều dịch vụ bên ngoài có thể cần nhiều kiểm thử hợp đồng và tích hợp hơn.

Trước khi đặt tỷ lệ, hãy xác định:

1. Người dùng và doanh nghiệp cần kết quả gì?
2. Những quy tắc, luồng dữ liệu và phụ thuộc nào có thể làm kết quả sai?
3. Bằng chứng nào có thể thu thập ở cấp thấp hơn với chi phí và độ tin cậy phù hợp?
4. Những rủi ro nào chỉ có thể quan sát trong cấu hình gần thực tế hoặc qua người dùng đại diện?
5. Mỗi cấp cần tạo ra bằng chứng gì để hỗ trợ quyết định?

Tỷ lệ kiểm thử nên là kết quả của phân tích mục tiêu và rủi ro, không phải con số áp đặt trước.

## 2. Phân bổ mục tiêu cho kiểm thử đơn vị

### Xác thực quy tắc cục bộ

Kiểm thử đơn vị phù hợp khi có thể xác minh một quy tắc hoặc hành vi trong phạm vi nhỏ, với đầu vào và đầu ra xác định. Ví dụ:

- Tính giá, thuế, chiết khấu hoặc phí theo quy tắc nghiệp vụ.
- Kiểm tra điều kiện chuyển trạng thái của một đối tượng.
- Xác thực dữ liệu đầu vào và quy tắc chuẩn hóa.
- Áp dụng quyền truy cập theo vai trò trong một hàm chính sách.
- Xử lý ngày giờ, múi giờ, làm tròn và các giá trị biên.
- Xác định cách hệ thống phản ứng với đầu vào thiếu, sai định dạng hoặc ngoài giới hạn.

Một kiểm thử đơn vị tốt có phạm vi nhỏ, kết quả dễ hiểu, chạy nhanh và không phụ thuộc vào mạng, cơ sở dữ liệu hoặc dịch vụ bên ngoài. Khi thất bại, nhóm có thể khoanh vùng nguyên nhân ở logic đang kiểm tra.

### Tập trung vào nhánh logic và trường hợp biên

Đối với mỗi quy tắc quan trọng, hãy xác định:

- Trường hợp bình thường.
- Giá trị biên và giới hạn.
- Đầu vào không hợp lệ hoặc thiếu.
- Trạng thái không mong đợi.
- Nhánh lỗi và ngoại lệ.
- Quy tắc làm tròn, thứ tự ưu tiên hoặc điều kiện xung đột.

Ví dụ, với hàm tính chiết khấu, không chỉ kiểm tra một đơn hàng hợp lệ. Cần kiểm tra giá trị bằng 0, giá trị âm, mức chiết khấu tối đa, mã giảm giá hết hạn, điều kiện không cộng dồn và các quy tắc làm tròn.

Không cần tạo một kiểm thử riêng cho mọi tổ hợp đầu vào. Hãy chọn trường hợp đại diện theo rủi ro, phân vùng tương đương và các giá trị biên có thể làm thay đổi kết quả.

### Khi nào không nên dồn mục tiêu vào kiểm thử đơn vị

Một kiểm thử đơn vị có thể dùng mock để mô phỏng cơ sở dữ liệu hoặc dịch vụ khác. Điều đó hữu ích để xác minh cách logic xử lý phản hồi, nhưng không chứng minh cấu hình thật, schema, quyền truy cập hay hợp đồng giữa các thành phần hoạt động đúng.

Ví dụ, một hàm có thể tạo đúng payload thanh toán theo mock nhưng payload đó vẫn bị dịch vụ thật từ chối vì trường bắt buộc đã đổi tên. Mục tiêu tương thích cần được phân bổ sang kiểm thử hợp đồng hoặc tích hợp.

Kiểm thử đơn vị cũng không chứng minh người dùng hiểu giao diện, có thể hoàn thành hành trình hoặc sản phẩm đáp ứng thời gian phản hồi trong tải thực tế. Những mục tiêu này cần bằng chứng ở cấp khác.

## 3. Phân bổ mục tiêu cho kiểm thử tích hợp

### Xác minh ranh giới và hợp đồng giữa các thành phần

Kiểm thử tích hợp tập trung vào cách các thành phần phối hợp. Đối tượng có thể là hai module trong cùng ứng dụng, ứng dụng với cơ sở dữ liệu, dịch vụ nội bộ với dịch vụ khác, hoặc hệ thống với nhà cung cấp bên ngoài.

Các mục tiêu thường gồm:

- Kiểm tra dữ liệu được chuyển đúng định dạng, kiểu, đơn vị và ngữ nghĩa.
- Xác minh API, schema, giao thức, sự kiện và webhook.
- Kiểm tra xác thực, phân quyền, chứng thư và cấu hình kết nối.
- Xác nhận giao dịch, tính nhất quán và cập nhật trạng thái giữa các thành phần.
- Kiểm tra timeout, retry, idempotency và xử lý lỗi từ phụ thuộc.
- Kiểm tra thứ tự sự kiện, xử lý trùng và khả năng đồng bộ lại.
- Xác minh tương thích giữa các phiên bản dịch vụ.

Cấp tích hợp đặc biệt quan trọng khi hành trình đi qua nhiều nhóm sở hữu hoặc nhà cung cấp. Lỗi ở ranh giới có thể không xuất hiện trong kiểm thử đơn vị của từng phía.

### Chọn cách tích hợp phù hợp

Có nhiều cách tạo bằng chứng tích hợp:

| Cách kiểm thử | Mục tiêu phù hợp | Giới hạn cần lưu ý |
|---|---|---|
| Kiểm thử với mock hoặc stub | Xác minh logic tiêu thụ phản ứng với phản hồi đã định nghĩa | Không chứng minh dịch vụ thật tuân thủ hợp đồng |
| Kiểm thử hợp đồng | Xác minh hai phía thống nhất schema, giao thức và kỳ vọng | Không bao phủ toàn bộ hạ tầng hoặc hành trình |
| Kiểm thử với cơ sở dữ liệu thật trong môi trường kiểm thử | Xác minh truy vấn, transaction, constraint và migration | Có thể chưa đại diện tải hoặc cấu hình production |
| Kiểm thử API giữa các dịch vụ | Xác minh request, response, quyền và trạng thái | Không nhất thiết bao phủ trải nghiệm người dùng |
| Kiểm thử sự kiện hoặc webhook | Xác minh phát, nhận, xác thực, retry và xử lý sự kiện | Cần mô phỏng được sự kiện trùng, đến muộn hoặc sai thứ tự |
| Kiểm thử tích hợp với sandbox | Xác minh tương tác với nhà cung cấp trong điều kiện cho phép | Sandbox có thể khác production về dữ liệu, quota và hành vi |

Không phải lúc nào cũng cần kết nối tất cả dịch vụ thật trong mỗi lần chạy. Hãy chọn cấp tích hợp nhỏ nhất có thể xác minh rủi ro cần quan tâm, sau đó bổ sung một số kịch bản đại diện với cấu hình gần thực tế.

### Kiểm tra lỗi tại ranh giới

Kiểm thử tích hợp nên bao phủ cả thành công và thất bại. Những tình huống thường có giá trị gồm:

- Dịch vụ trả lỗi xác thực hoặc từ chối quyền.
- Phản hồi chậm hơn timeout của phía gọi.
- Kết nối bị ngắt sau khi phía cung cấp đã xử lý yêu cầu.
- Dữ liệu trả về thiếu trường hoặc có phiên bản schema mới.
- Nhà cung cấp giới hạn tần suất hoặc quota.
- Sự kiện được gửi nhiều lần hoặc sai thứ tự.
- Cơ sở dữ liệu từ chối transaction hoặc xảy ra deadlock.
- Dịch vụ phục hồi sau gián đoạn và cần xử lý lại dữ liệu tồn đọng.

Khi kiểm thử thao tác có tác động như thanh toán, tạo đơn hàng hoặc cấp quyền, phải xác minh tính lặp an toàn và trạng thái cuối. Chỉ kiểm tra mã HTTP thành công hoặc phản hồi từ một thành phần là chưa đủ.

## 4. Phân bổ mục tiêu cho kiểm thử hệ thống

### Xác minh sản phẩm như một hệ thống hoàn chỉnh

Kiểm thử hệ thống đánh giá hệ thống đã tích hợp trong một cấu hình được xác định. Mục tiêu là kiểm tra xem các thành phần có cùng tạo ra hành vi đáp ứng yêu cầu hay không.

Các mục tiêu thường gồm:

- Hành trình chức năng quan trọng từ điểm bắt đầu đến kết quả cuối.
- Quy tắc nghiệp vụ xuyên suốt nhiều thành phần.
- Tính nhất quán dữ liệu và trạng thái giữa các bước.
- Phân quyền và kiểm soát truy cập ở các luồng đại diện.
- Hiệu năng, tải, độ ổn định và khả năng phục hồi của hệ thống.
- Khả năng tương thích với trình duyệt, thiết bị, hệ điều hành hoặc cấu hình hỗ trợ.
- Hành vi khi một dịch vụ phụ thuộc chậm, lỗi hoặc không khả dụng.
- Tính đúng đắn của log, metric, cảnh báo và khả năng truy vết.

Hệ thống được kiểm thử cần có phiên bản, cấu hình, dữ liệu và các phụ thuộc được ghi nhận. Nếu môi trường khác production, phải mô tả khác biệt có thể ảnh hưởng đến kết luận.

### Kiểm thử hành trình đầu cuối có chọn lọc

Kiểm thử hệ thống có thể đi qua giao diện, API hoặc kết hợp nhiều điểm vào. Một kịch bản đầu cuối đại diện nên xác minh kết quả có ý nghĩa, ví dụ người dùng đăng ký, xác minh tài khoản, tạo không gian làm việc và hoàn thành công việc đầu tiên.

Không nên chuyển mọi biến thể của từng quy tắc vào kiểm thử đầu cuối. Những trường hợp logic chi tiết thường nên được kiểm tra ở cấp đơn vị hoặc tích hợp. Ở cấp hệ thống, hãy chọn luồng chính, nhánh lỗi quan trọng và các điểm chuyển giao có rủi ro cao.

Kịch bản cần kiểm tra trạng thái sau cùng ở nơi có thẩm quyền. Ví dụ, sau khi người dùng thanh toán, cần xác minh trạng thái thuê bao và giao dịch trong hệ thống nghiệp vụ, không chỉ kiểm tra thông báo trên giao diện.

### Phân bổ mục tiêu phi chức năng

Các đặc tính phi chức năng thường cần kiểm tra ở nhiều cấp:

| Đặc tính | Đơn vị | Tích hợp | Hệ thống |
|---|---|---|---|
| Hiệu năng | Độ phức tạp hoặc thời gian xử lý hàm quan trọng | Độ trễ giữa các dịch vụ, truy vấn và kết nối | Thời gian phản hồi hành trình dưới tải đại diện |
| Bảo mật | Quy tắc xác thực dữ liệu và chính sách cục bộ | Xác thực, phân quyền, truyền dữ liệu và bí mật tại ranh giới | Kiểm soát truy cập xuyên suốt, cấu hình và hành vi hệ thống |
| Độ tin cậy | Xử lý ngoại lệ và trạng thái lỗi trong logic | Retry, timeout, transaction và phục hồi kết nối | Khả năng duy trì dịch vụ, phục hồi và nhất quán toàn hệ thống |
| Tương thích | Xử lý định dạng hoặc kiểu dữ liệu | Tương thích schema và phiên bản API | Trình duyệt, thiết bị, hệ điều hành và cấu hình được hỗ trợ |
| Khả năng tiếp cận | Cấu trúc và thuộc tính của thành phần giao diện | Tương tác giữa các thành phần và điều hướng | Hoàn thành hành trình bằng công nghệ hỗ trợ |
| Khả năng quan sát | Log và metric được phát ra từ logic | Trace qua ranh giới dịch vụ | Phát hiện và chẩn đoán sự cố trên hành trình hoàn chỉnh |

Bảng này gợi ý nơi thu thập bằng chứng, không phải yêu cầu mỗi đặc tính đều phải kiểm tra ở mọi cấp. Chọn phạm vi dựa trên hậu quả và rủi ro cụ thể.

## 5. Phân bổ mục tiêu cho kiểm thử chấp nhận

### Xác nhận sản phẩm đáp ứng tiêu chí của người nhận

Kiểm thử chấp nhận đánh giá sản phẩm hoặc quy trình theo tiêu chí mà người nhận kết quả quan tâm. Người đánh giá có thể là khách hàng, người dùng đại diện, chủ sở hữu nghiệp vụ, vận hành, bộ phận tuân thủ hoặc một cơ quan có thẩm quyền.

Các hình thức phổ biến gồm:

- **Chấp nhận của người dùng (UAT):** người dùng hoặc đại diện nghiệp vụ xác nhận có thể hoàn thành công việc và kết quả đáp ứng nhu cầu.
- **Chấp nhận nghiệp vụ:** xác minh quy tắc, báo cáo, giao dịch và quy trình đáp ứng điều kiện kinh doanh đã thống nhất.
- **Chấp nhận vận hành:** xác minh khả năng triển khai, giám sát, hỗ trợ, sao lưu, phục hồi và xử lý sự cố.
- **Chấp nhận theo hợp đồng:** xác minh tiêu chí nghiệm thu, phạm vi bàn giao và điều kiện đã cam kết.
- **Chấp nhận theo quy định:** xác minh yêu cầu quản lý hoặc tiêu chuẩn chuyên ngành khi sản phẩm thuộc phạm vi áp dụng.

Không phải mọi sản phẩm đều cần tất cả hình thức. Hãy xác định ai là người nhận kết quả, tiêu chí nào có tính ràng buộc và ai có quyền phê duyệt.

### Viết tiêu chí chấp nhận có thể đánh giá

Tiêu chí chấp nhận nên mô tả kết quả quan sát được, điều kiện và phạm vi. Tránh các câu chung như “dễ dùng”, “nhanh” hoặc “an toàn” nếu không có cách đánh giá.

Ví dụ:

- Quản trị viên có thể mời thành viên bằng địa chỉ hợp lệ, xem trạng thái lời mời và gửi lại khi lời mời hết hạn.
- Thành viên chỉ xem được dữ liệu thuộc không gian làm việc mà họ được cấp quyền.
- Sau khi giao dịch được xác nhận thành công, thuê bao được kích hoạt và người dùng nhận thông báo có trạng thái chính xác.
- Nhân viên vận hành có thể phát hiện hàng đợi xử lý bị tồn đọng và thực hiện quy trình khôi phục đã được phê duyệt.

Tiêu chí cần liên kết với yêu cầu, quy tắc nghiệp vụ hoặc thỏa thuận đã được thống nhất. Nếu tiêu chí thay đổi trong quá trình nghiệm thu, cần ghi nhận người phê duyệt và lý do.

### Chấp nhận không thay thế các cấp kiểm thử trước

Kiểm thử chấp nhận thường dùng dữ liệu và hành trình gần với công việc thật, nhưng không phải nơi phù hợp để tìm mọi lỗi logic hoặc mọi biến thể kỹ thuật. Người dùng có thể xác nhận quy trình thanh toán đáp ứng nhu cầu mà không phát hiện được một lỗi race condition hiếm. Một bài nghiệm thu thành công cũng không chứng minh hệ thống chịu được tải đột biến hoặc đã kiểm soát mọi lỗ hổng bảo mật.

Vì vậy, điều kiện chấp nhận nên dựa trên bằng chứng từ các cấp trước và bổ sung xác nhận về giá trị, quy trình hoặc nghĩa vụ của người nhận. Những rủi ro kỹ thuật nghiêm trọng vẫn cần được kiểm chứng bằng phương pháp chuyên môn phù hợp.

## 6. Lập ma trận phân bổ mục tiêu theo cấp

### Nối mục tiêu, rủi ro và cấp kiểm thử

Trước khi viết kịch bản, hãy lập ma trận thể hiện mục tiêu được xác minh ở đâu, bằng phương pháp nào và ai chịu trách nhiệm. Ví dụ:

| Mục tiêu cần xác thực | Rủi ro chính | Cấp chủ đạo | Bằng chứng bổ sung |
|---|---|---|---|
| Công thức tính phí đúng | Tính sai giá hoặc làm tròn sai | Đơn vị | Kiểm tra tích hợp với dữ liệu giá và một hành trình thanh toán |
| Dịch vụ gửi và nhận đúng dữ liệu | Schema hoặc quyền không tương thích | Tích hợp | Kiểm thử hợp đồng và trace |
| Người dùng hoàn thành đăng ký | Một bước trong luồng bị lỗi hoặc trạng thái không nhất quán | Hệ thống | Kiểm thử chấp nhận với người dùng đại diện |
| Quản trị viên phân quyền đúng | Cấp quyền quá rộng hoặc chặn nhầm | Đơn vị và tích hợp | Kiểm thử hệ thống xuyên vai trò; UAT |
| Hệ thống phục hồi sau khi dịch vụ phụ thuộc ngừng | Mất dữ liệu hoặc xử lý lặp | Tích hợp và hệ thống | Kiểm thử phục hồi và xác nhận vận hành |
| Quy trình bàn giao đáp ứng yêu cầu vận hành | Thiếu cảnh báo hoặc thiếu hướng dẫn xử lý | Hệ thống và chấp nhận vận hành | Diễn tập sự cố, rà soát runbook |

Cấp chủ đạo là nơi thu thập bằng chứng chính cho mục tiêu. Các cấp khác có thể bổ sung kiểm tra hoặc bảo vệ hồi quy. Không cần lặp lại cùng một kịch bản ở tất cả cấp nếu không tạo thêm bằng chứng có giá trị.

### Dùng truy vết hai chiều

Mỗi mục tiêu cần truy vết đến:

- Yêu cầu, nhu cầu người dùng hoặc mục tiêu kinh doanh nguồn.
- Rủi ro và hậu quả cần kiểm soát.
- Cấp kiểm thử và phương pháp xác minh.
- Kịch bản, dữ liệu, môi trường và người chịu trách nhiệm.
- Kết quả, bằng chứng và quyết định.

Truy vết ngược cũng quan trọng. Mỗi bài kiểm thử nên giải thích được nó đang hỗ trợ mục tiêu hoặc kiểm soát rủi ro nào. Nếu một bài kiểm thử không có mục tiêu rõ, nhóm cần xem lại liệu nó còn cần thiết hay đang tạo chi phí bảo trì không có giá trị.

### Xác định phạm vi và độ sâu theo rủi ro

Không phải mọi yêu cầu đều cần cùng số lượng bài kiểm thử. Hãy cân nhắc:

1. Mức tác động nếu yêu cầu sai.
2. Khả năng xảy ra và mức độ bất định.
3. Độ phức tạp của logic và số lượng ranh giới tích hợp.
4. Tần suất sử dụng và số người dùng bị ảnh hưởng.
5. Khả năng phát hiện lỗi trước khi người dùng chịu ảnh hưởng.
6. Chi phí sửa lỗi nếu phát hiện muộn.
7. Khả năng phục hồi và phương án thay thế.

Một quy tắc tính phí có hậu quả tài chính lớn có thể cần kiểm thử đơn vị chi tiết, kiểm thử tích hợp dữ liệu giá và kiểm thử hệ thống trên các hành trình đại diện. Một nhãn hiển thị ít quan trọng có thể chỉ cần kiểm tra ở cấp thành phần và một số luồng hồi quy.

## 7. Ví dụ: phân bổ mục tiêu cho hành trình đặt hàng và thanh toán

Giả sử một sản phẩm thương mại cho phép khách hàng chọn sản phẩm, áp dụng mã giảm giá, thanh toán qua nhà cung cấp và theo dõi đơn hàng. Các nhóm liên quan gồm giao diện, đơn hàng, giá, kho, thanh toán và thông báo.

### Phân rã mục tiêu

| Mục tiêu | Quy tắc hoặc rủi ro | Cấp ưu tiên |
|---|---|---|
| Tổng tiền được tính đúng | Thuế, phí, giảm giá và làm tròn có thể sai | Đơn vị |
| Mã giảm giá được xác thực | Điều kiện mã và thời hạn có thể không đồng bộ | Đơn vị và tích hợp |
| Đơn hàng và thanh toán thống nhất | Timeout hoặc webhook trùng có thể tạo trạng thái lệch | Tích hợp |
| Khách hàng đặt hàng thành công | Luồng nhiều dịch vụ có thể bị đứt giữa chừng | Hệ thống |
| Khách hàng hiểu trạng thái đơn hàng | Nội dung và trạng thái có thể gây nhầm lẫn | Hệ thống và chấp nhận |
| Bộ phận vận hành xử lý được giao dịch bất thường | Thiếu cảnh báo hoặc công cụ đối soát | Hệ thống và chấp nhận vận hành |

### Ma trận kịch bản mẫu

| Cấp | Kịch bản | Kết quả cần xác minh |
|---|---|---|
| Đơn vị | Tính tổng tiền với mã giảm giá hợp lệ, hết hạn và không đủ điều kiện | Tổng tiền, thuế và phí đúng theo quy tắc |
| Đơn vị | Tính lại tổng tiền khi số lượng thay đổi | Không dùng giá trị cũ; xử lý đúng giới hạn |
| Tích hợp | Dịch vụ đơn hàng gửi yêu cầu tạo thanh toán | Payload và mã tham chiếu đúng; lỗi được xử lý |
| Tích hợp | Nhà cung cấp gửi webhook thanh toán nhiều lần | Chỉ có một kết quả nghiệp vụ; trạng thái nhất quán |
| Tích hợp | Dịch vụ kho không phản hồi | Đơn hàng có trạng thái chờ hoặc xử lý bù theo quy tắc |
| Hệ thống | Khách hàng đặt hàng từ chọn sản phẩm đến xác nhận | Hành trình hoàn tất; dữ liệu đơn hàng và thanh toán nhất quán |
| Hệ thống | Mạng bị ngắt sau khi thanh toán được xử lý | Không tạo giao dịch trùng; người dùng nhận trạng thái đúng |
| Chấp nhận người dùng | Khách hàng xem lại giỏ, tổng tiền, địa chỉ và xác nhận đơn | Người dùng hiểu thông tin và hoàn thành quy trình |
| Chấp nhận vận hành | Nhân viên xử lý đơn hàng ở trạng thái cần đối soát | Có thể tìm giao dịch, hiểu trạng thái và theo quy trình đã thống nhất |

Ví dụ này cho thấy một mục tiêu kinh doanh có thể cần bằng chứng ở nhiều cấp, nhưng mỗi cấp xác minh một phần khác nhau. Kiểm thử đơn vị chứng minh công thức tính tiền; kiểm thử tích hợp chứng minh dữ liệu và trạng thái giữa dịch vụ; kiểm thử hệ thống chứng minh hành trình; kiểm thử chấp nhận xác nhận quy trình đáp ứng nhu cầu và tiêu chí của người nhận.

## 8. Cân bằng độ bao phủ, tốc độ phản hồi và chi phí bảo trì

### Ưu tiên kiểm thử nhanh và ổn định ở cấp thấp

Kiểm thử đơn vị thường có chi phí chạy thấp và giúp phát hiện lỗi sớm. Kiểm thử tích hợp có thể chậm hơn do cần dịch vụ, dữ liệu và cấu hình. Kiểm thử hệ thống và chấp nhận thường tốn nhiều thời gian thiết lập, dễ bị ảnh hưởng bởi môi trường và dữ liệu.

Một chiến lược thực tế thường đặt nhiều kiểm thử nhỏ, ổn định ở cấp đơn vị; một tập hợp có chọn lọc ở cấp tích hợp; và số lượng có chủ đích ở cấp hệ thống, chấp nhận. Tuy nhiên, không nên đặt tỷ lệ cứng nếu kiến trúc hoặc rủi ro yêu cầu phân bổ khác.

Mục tiêu là phát hiện lỗi ở cấp sớm nhất có thể tạo bằng chứng đáng tin cậy. Khi một lỗi chỉ có thể xuất hiện qua tương tác nhiều dịch vụ, kiểm thử tích hợp là nơi phù hợp. Khi vấn đề liên quan đến hành trình hoặc cấu hình toàn hệ thống, cần kiểm thử ở cấp hệ thống. Khi cần xác nhận giá trị và tiêu chí của người nhận, cần kiểm thử chấp nhận.

### Tránh kiểm thử đầu cuối quá nhiều

Bộ kiểm thử đầu cuối quá lớn có thể tạo ra:

- Thời gian chạy dài và phản hồi chậm.
- Nhiều lỗi không ổn định do môi trường, mạng hoặc dữ liệu.
- Khó xác định thành phần gây lỗi.
- Chi phí bảo trì cao khi giao diện hoặc luồng thay đổi.
- Phụ thuộc vào tài khoản, dịch vụ và dữ liệu dùng chung.

Hãy giữ các kịch bản đầu cuối tập trung vào hành trình cốt lõi, rủi ro cao và điểm tích hợp có hậu quả đáng kể. Chuyển các biến thể logic có thể kiểm tra độc lập xuống cấp đơn vị hoặc tích hợp.

### Tránh bộ kiểm thử đơn vị chỉ kiểm tra chi tiết triển khai

Một bộ kiểm thử đơn vị có thể rất lớn nhưng ít giá trị nếu chỉ xác minh cách viết mã thay vì hành vi mong đợi. Khi cấu trúc nội bộ thay đổi nhưng hành vi không đổi, quá nhiều kiểm thử phụ thuộc chi tiết triển khai có thể thất bại và tạo chi phí bảo trì.

Hãy viết kiểm thử theo hợp đồng hành vi: đầu vào, điều kiện, kết quả và tác dụng phụ cần bảo đảm. Giữ các kiểm thử nhỏ, độc lập và có thông điệp lỗi giúp chẩn đoán.

### Dùng thời gian phản hồi như một tiêu chí phân bổ

Có thể phân chia pipeline theo vòng phản hồi:

| Vòng | Nội dung điển hình | Thời điểm chạy |
|---|---|---|
| Rất nhanh | Kiểm thử đơn vị, kiểm tra tĩnh và một số kiểm thử thành phần | Khi phát triển và trong mỗi thay đổi mã |
| Tích hợp | Hợp đồng, API, cơ sở dữ liệu và các ranh giới quan trọng | Khi tạo hoặc cập nhật nhánh, trước khi hợp nhất |
| Hệ thống | Hành trình trọng yếu, hồi quy đại diện, hiệu năng hoặc phục hồi theo phạm vi | Trước mốc phát hành hoặc theo lịch phù hợp |
| Chấp nhận | UAT, nghiệp vụ, vận hành hoặc nghiệm thu theo hợp đồng | Khi phiên bản đủ ổn định và trước khi phê duyệt |

Đây là ví dụ tổ chức pipeline, không phải lịch bắt buộc. Những kiểm thử bảo mật hoặc kiểm thử rủi ro cao có thể cần chạy ở nhiều thời điểm. Nếu một kiểm thử dài nhưng có khả năng phát hiện lỗi nghiêm trọng trước khi hợp nhất, nhóm cần cân nhắc vị trí chạy dựa trên tác động và chi phí chờ.

## 9. Quản lý dữ liệu, môi trường và trách nhiệm ở từng cấp

### Dữ liệu kiểm thử phải phù hợp với mục tiêu

Mỗi cấp cần dữ liệu có mức phức tạp phù hợp:

- Đơn vị: dữ liệu nhỏ, xác định rõ đầu vào và kết quả, dễ tạo lại.
- Tích hợp: dữ liệu đại diện cho schema, trạng thái, quan hệ và ràng buộc giữa thành phần.
- Hệ thống: dữ liệu mô phỏng hành trình thực tế, gồm các vai trò, trạng thái và nhánh lỗi quan trọng.
- Chấp nhận: dữ liệu đủ gần với công việc của người nhận nhưng được bảo vệ theo chính sách.

Không dùng dữ liệu cá nhân hoặc bí mật thật nếu không có căn cứ và quy trình được phép. Dữ liệu nên có cách khởi tạo, dọn dẹp và làm mới rõ ràng để các lần chạy không ảnh hưởng lẫn nhau.

### Môi trường cần phản ánh điều kiện đang xác thực

Kiểm thử đơn vị thường chạy trong môi trường cô lập. Kiểm thử tích hợp cần các dịch vụ, cơ sở dữ liệu hoặc sandbox thích hợp. Kiểm thử hệ thống cần cấu hình gần với kiến trúc triển khai dự kiến. Kiểm thử chấp nhận cần môi trường và quy trình đủ ổn định để người nhận đánh giá.

Ghi rõ khác biệt giữa môi trường kiểm thử và production: phiên bản dịch vụ, quyền, quota, dữ liệu, cấu hình mạng, feature flag và khả năng giám sát. Một kết quả tốt trong môi trường mô phỏng không tự chứng minh hành vi production.

### Phân công trách nhiệm và quyền quyết định

| Cấp | Người tham gia thường gặp | Trách nhiệm chính |
|---|---|---|
| Đơn vị | Lập trình viên và nhóm phát triển thành phần | Duy trì kiểm thử logic, xử lý lỗi và hồi quy cục bộ |
| Tích hợp | Nhóm tiêu thụ, chủ sở hữu dịch vụ và QA kỹ thuật | Xác minh hợp đồng, dữ liệu, giao tiếp và lỗi tại ranh giới |
| Hệ thống | QA, phát triển, vận hành và chuyên gia miền liên quan | Xác minh hành vi tổng thể, cấu hình và rủi ro đầu cuối |
| Chấp nhận | Người dùng đại diện, chủ sở hữu nghiệp vụ, khách hàng hoặc vận hành | Đánh giá tiêu chí chấp nhận và đưa ra xác nhận thuộc thẩm quyền |

Trách nhiệm có thể khác giữa các tổ chức. Cần xác định ai chuẩn bị dữ liệu, ai quản lý môi trường, ai phân tích lỗi, ai sửa và ai phê duyệt kết quả. Không mặc định rằng bộ phận QA chịu trách nhiệm duy nhất cho mọi cấp kiểm thử.

## 10. Xử lý kết quả và cổng quyết định

### Định nghĩa kết quả đạt trước khi chạy

Mỗi cấp cần tiêu chí đạt phù hợp:

- Đơn vị: quy tắc và nhánh quan trọng được xác minh; không có lỗi chặn chưa xử lý.
- Tích hợp: hợp đồng, dữ liệu, quyền và trạng thái tại ranh giới đáp ứng kỳ vọng; lỗi được xử lý theo quy tắc.
- Hệ thống: hành trình và đặc tính quan trọng đạt tiêu chí trong cấu hình, dữ liệu và tải đã xác định.
- Chấp nhận: người có thẩm quyền xác nhận tiêu chí nghiệp vụ, người dùng, vận hành hoặc hợp đồng.

Tiêu chí có thể bao gồm tỷ lệ hoàn thành, mức lỗi cho phép, ngưỡng thời gian phản hồi, mức bao phủ rủi ro hoặc các điều kiện bắt buộc. Không dùng một ngưỡng chung cho mọi sản phẩm.

### Không đánh đồng kiểm thử xanh với rủi ro bằng không

Một bộ kiểm thử thành công chỉ cho biết các tình huống đã chạy đạt kết quả theo tiêu chí. Nó không chứng minh mọi tình huống đều đúng hoặc mọi rủi ro đã được loại bỏ.

Khi báo cáo, hãy nêu:

- Phạm vi và phiên bản đã kiểm thử.
- Các mục tiêu và rủi ro được bao phủ.
- Môi trường, dữ liệu và phụ thuộc được sử dụng.
- Kết quả, lỗi còn mở và giới hạn kiểm thử.
- Những rủi ro chưa có bằng chứng.
- Quyết định phát hành hoặc chấp nhận và người phê duyệt.

Nếu kiểm thử chấp nhận đạt nhưng kiểm thử tích hợp còn lỗi nghiêm trọng, không nên kết luận sản phẩm đã sẵn sàng chỉ vì người dùng hoàn thành được một kịch bản. Cần áp dụng cổng quyết định theo rủi ro và thẩm quyền.

### Quản lý kiểm thử không ổn định

Kiểm thử thất bại ngẫu nhiên có thể làm nhóm mất niềm tin vào pipeline. Hãy phân loại nguyên nhân: lỗi sản phẩm, lỗi môi trường, dữ liệu dùng chung, phụ thuộc không ổn định hoặc bản thân kiểm thử có điều kiện cạnh tranh.

Có thể tạm cách ly một kiểm thử không ổn định để điều tra, nhưng phải ghi rõ chủ sở hữu, thời hạn và rủi ro bị che khuất. Không nên vô hiệu hóa hàng loạt kiểm thử quan trọng hoặc xem việc chạy lại cho đến khi xanh là bằng chứng đạt.

## 11. Những sai lầm thường gặp

- **Áp đặt tỷ lệ kiểm thử cố định:** phân bổ không phản ánh kiến trúc, mục tiêu và mức rủi ro của sản phẩm.
- **Chỉ kiểm thử ở một cấp:** bỏ sót bằng chứng cần thiết tại ranh giới, hành trình hoặc tiêu chí người nhận.
- **Đưa mọi trường hợp lên đầu cuối:** làm pipeline chậm, khó chẩn đoán và tốn chi phí bảo trì.
- **Dùng mock để kết luận tích hợp thật hoạt động:** mock không chứng minh hợp đồng hoặc cấu hình dịch vụ thật.
- **Nhầm cấp kiểm thử với loại kiểm thử:** khiến các mục tiêu như hiệu năng và bảo mật bị phân bổ thiếu hợp lý.
- **Lặp lại cùng kịch bản ở mọi cấp:** tăng chi phí nhưng không tăng bằng chứng đáng kể.
- **Không xác định tiêu chí chấp nhận:** kết quả nghiệm thu phụ thuộc vào ý kiến chủ quan hoặc thay đổi sau khi kiểm thử.
- **Chỉ kiểm tra giao diện ở cấp chấp nhận:** bỏ qua dữ liệu, trạng thái và quy trình vận hành phía sau.
- **Không gắn bài kiểm thử với mục tiêu hoặc rủi ro:** khó giải thích vì sao cần duy trì bài kiểm thử.
- **Không xác định người chịu trách nhiệm:** lỗi giữa các cấp hoặc nhóm dễ bị bỏ sót.
- **Coi kiểm thử xanh là không còn rủi ro:** bỏ qua giới hạn môi trường, dữ liệu và phạm vi bao phủ.

## 12. Đầu ra cần có trước khi chốt phân bổ kiểm thử

Một kế hoạch phân bổ mục tiêu đủ dùng nên có:

1. **Danh sách mục tiêu xác thực:** nhu cầu người dùng, yêu cầu nghiệp vụ, chất lượng hệ thống và điều kiện chấp nhận.
2. **Danh sách rủi ro:** nguyên nhân, sự kiện, hậu quả, mức ưu tiên và khoảng trống bằng chứng.
3. **Ma trận mục tiêu – cấp kiểm thử:** cấp chủ đạo, cấp bổ trợ và lý do lựa chọn.
4. **Phạm vi từng cấp:** đối tượng, phương pháp, kịch bản, dữ liệu và môi trường.
5. **Trách nhiệm:** người viết, người chạy, người phân tích, người sửa và người phê duyệt.
6. **Tiêu chí đạt:** kết quả cần có, ngưỡng, lỗi chặn và điều kiện chấp nhận.
7. **Kế hoạch thực thi:** vòng phản hồi, pipeline, lịch chạy và xử lý kiểm thử không ổn định.
8. **Bằng chứng và truy vết:** kết quả kiểm thử liên kết với mục tiêu, rủi ro và quyết định.
9. **Rủi ro còn lại:** điều chưa được kiểm chứng, giới hạn môi trường và người chấp nhận.

Trước khi chốt, hãy rà soát:

- Mỗi mục tiêu quan trọng đã có cấp kiểm thử chủ đạo chưa?
- Các quy tắc cục bộ được kiểm tra ở phạm vi nhỏ và dễ chẩn đoán chưa?
- Ranh giới giữa các thành phần có kiểm thử hợp đồng và lỗi phù hợp chưa?
- Hành trình quan trọng có được kiểm tra trong cấu hình đại diện chưa?
- Tiêu chí của người dùng, nghiệp vụ và vận hành có người có thẩm quyền xác nhận chưa?
- Các đặc tính phi chức năng đã được phân bổ theo rủi ro chưa?
- Dữ liệu, môi trường và phụ thuộc có được ghi nhận không?
- Có thể truy vết từ mục tiêu đến kịch bản, kết quả và quyết định không?
- Các giới hạn và rủi ro còn lại có được công khai trước khi phát hành không?

Phân bổ tốt giúp mỗi cấp kiểm thử làm đúng phần việc của nó và tạo bằng chứng phù hợp cho quyết định tiếp theo. Khi sản phẩm thay đổi về kiến trúc, hành trình, người dùng hoặc mức rủi ro, nhóm cần xem lại ma trận phân bổ. Nhờ đó, chiến lược kiểm thử giữ được sự cân bằng giữa độ bao phủ, tốc độ phản hồi, chi phí bảo trì và niềm tin vào kết quả xác thực.

