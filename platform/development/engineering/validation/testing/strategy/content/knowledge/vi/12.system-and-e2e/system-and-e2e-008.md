# Giới hạn số ca theo giá trị phát hiện lỗi và khả năng duy trì

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích vì sao số lượng system test và end-to-end test cần được kiểm soát theo giá trị mà chúng mang lại.
- Phân biệt số lượng test, độ bao phủ yêu cầu, độ bao phủ rủi ro và khả năng phát hiện lỗi.
- Đánh giá một ca kiểm thử theo mức độ quan trọng của hành trình, loại lỗi có thể phát hiện và bằng chứng bổ sung.
- Lựa chọn kịch bản đại diện bằng phân vùng tương đương, giá trị biên, chuyển trạng thái, tổ hợp và phân tích rủi ro.
- Nhận diện test trùng lặp, ít giá trị, không ổn định hoặc có chi phí bảo trì quá cao.
- Tối ưu danh mục system và E2E mà vẫn bảo vệ các hành trình, quy tắc và rủi ro quan trọng.
- Theo dõi sức khỏe bộ kiểm thử và đưa ra quyết định thêm, sửa, hợp nhất hoặc loại bỏ test có căn cứ.

## 1. Vì sao cần giới hạn số ca system và E2E?

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, kiểm thử hệ thống (system testing) và kiểm thử đầu-cuối (end-to-end testing, E2E) giúp xác minh hành vi của nhiều thành phần khi phối hợp trong một luồng gần với cách hệ thống được sử dụng. Chúng có thể phát hiện lỗi tích hợp, cấu hình, dữ liệu, giao tiếp và quy trình mà kiểm thử ở cấp thấp không thể nhìn thấy.

Tuy nhiên, một ca E2E thường cần nhiều thành phần, môi trường, dữ liệu và dịch vụ phụ thuộc. Nó có thể chậm, khó chẩn đoán, dễ bị ảnh hưởng bởi trạng thái dùng chung và tốn công bảo trì khi giao diện hoặc kiến trúc thay đổi. Nếu mọi tổ hợp đầu vào và mọi biến thể nhỏ đều được triển khai thành một ca E2E riêng, bộ kiểm thử sẽ phình to nhanh chóng. Thời gian pipeline tăng, kết quả không ổn định nhiều hơn và nhóm khó xác định những ca nào thực sự bảo vệ rủi ro quan trọng.

Giới hạn số ca không có nghĩa là giảm chất lượng hoặc bỏ qua trường hợp nguy hiểm. Đó là việc chọn những ca mang lại bằng chứng có giá trị cao, đồng thời kiểm tra các chi tiết có thể được xác minh ổn định và rẻ hơn ở cấp unit, component, contract hoặc integration.

Một danh mục tốt cần trả lời:

- Ca này bảo vệ hành trình, yêu cầu hoặc rủi ro nào?
- Nó có thể phát hiện loại lỗi nào mà các ca hiện tại chưa phát hiện?
- Vì sao cần kiểm tra ở cấp system hoặc E2E?
- Dữ liệu, trạng thái và môi trường nào cần thiết?
- Chi phí chạy và bảo trì có tương xứng với giá trị phát hiện không?
- Nếu bỏ hoặc gộp ca này, bằng chứng quan trọng nào sẽ mất đi?

Không có một con số tối đa phù hợp cho mọi hệ thống. Quy mô danh mục cần dựa trên kiến trúc, mức rủi ro, độ phức tạp của hành trình, tần suất thay đổi và năng lực duy trì.

## 2. Phân biệt số lượng test và độ bao phủ

Số lượng ca kiểm thử chỉ cho biết danh mục có bao nhiêu trường hợp. Nó không cho biết các trường hợp đó kiểm tra được bao nhiêu yêu cầu, rủi ro, đường đi hoặc loại lỗi.

Ví dụ, một bộ có 200 ca E2E có thể dành 150 ca cho cùng một luồng đăng nhập với các biến thể dữ liệu nhỏ, trong khi không có ca nào kiểm tra hủy đơn, hoàn tiền hoặc quyền truy cập giữa các tổ chức. Một bộ có ít ca hơn nhưng mỗi ca bảo vệ một hành trình quan trọng và kiểm tra được trạng thái cuối có thể mang lại độ bao phủ rủi ro tốt hơn.

Phân biệt các khái niệm:

- **Số lượng test**: tổng số test case hoặc test scenario trong danh mục.
- **Độ bao phủ yêu cầu**: các yêu cầu hoặc tiêu chí chấp nhận có ít nhất một phép kiểm chứng phù hợp.
- **Độ bao phủ rủi ro**: các rủi ro quan trọng có kịch bản kiểm thử và bằng chứng tương ứng.
- **Độ bao phủ hành trình**: các luồng nghiệp vụ chính, ngoại lệ và trạng thái quan trọng được kiểm tra.
- **Khả năng phát hiện lỗi**: khả năng một ca phát hiện được loại lỗi mà nó được thiết kế để tìm.
- **Độ tin cậy của test**: mức độ kết quả có thể lặp lại và phản ánh đúng trạng thái hệ thống.

Không nên dùng số lượng ca Pass hoặc phần trăm test đã chạy làm đại diện duy nhất cho chất lượng. Một test có thể Pass liên tục nhưng không còn kiểm tra rủi ro có ý nghĩa, hoặc assertion của nó quá yếu để phát hiện lỗi.

## 3. Đánh giá giá trị của một ca kiểm thử

Giá trị của một ca kiểm thử nằm ở bằng chứng mà nó bổ sung. Trước khi thêm một ca E2E mới, hãy đánh giá theo các khía cạnh sau.

### 3.1. Mức độ quan trọng của hành trình

Hành trình được sử dụng thường xuyên, tạo doanh thu, thay đổi dữ liệu quan trọng hoặc ảnh hưởng đến quyền truy cập thường cần được bảo vệ ở cấp hệ thống. Ví dụ: đăng nhập, đặt hàng, thanh toán, hoàn tiền, cấp quyền, xuất dữ liệu hoặc khôi phục tài khoản.

Một hành trình ít được sử dụng vẫn có thể có rủi ro cao nếu sai sót gây hậu quả nghiêm trọng, chẳng hạn thao tác xóa dữ liệu hoặc thay đổi quyền quản trị. Tần suất sử dụng chỉ là một yếu tố; tác động khi lỗi xảy ra cũng phải được xem xét.

### 3.2. Khả năng phát hiện một loại lỗi khác biệt

Một ca có giá trị cao khi nó có thể phát hiện lỗi chưa được kiểm tra ở nơi khác. Ví dụ:

- Kiểm tra đơn hàng được tạo đúng một lần khi client gửi yêu cầu lặp.
- Kiểm tra trạng thái thanh toán được phản ánh đúng sau callback bất đồng bộ.
- Kiểm tra người dùng tổ chức A không thể truy cập dữ liệu tổ chức B.
- Kiểm tra trạng thái đơn hàng và tồn kho nhất quán sau khi một dịch vụ phụ thuộc lỗi.

Nếu một ca chỉ lặp lại cùng đường đi, cùng dữ liệu và cùng assertion với một ca đã có, giá trị bổ sung có thể rất thấp.

### 3.3. Khả năng phát hiện lỗi ở cấp thấp hơn

Không phải mọi quy tắc đều cần kiểm tra bằng E2E. Nếu lỗi tính thuế có thể được phát hiện đầy đủ bằng unit test với nhiều trường hợp biên, không cần tạo hàng chục hành trình E2E chỉ để thay đổi một con số đầu vào. E2E nên tập trung xác minh rằng các thành phần phối hợp đúng và kết quả nghiệp vụ được thể hiện đúng qua toàn bộ hành trình.

Tuy vậy, một số lỗi chỉ xuất hiện khi tích hợp: cấu hình sai, mapping dữ liệu, quyền ở gateway, transaction, callback, định tuyến hoặc phiên bản dịch vụ không tương thích. Các rủi ro đó cần được kiểm tra tại ranh giới phù hợp.

### 3.4. Chi phí và độ tin cậy

Đánh giá cả thời gian thực thi, setup, cleanup, dữ liệu, môi trường, phụ thuộc, công sửa khi giao diện thay đổi và tần suất flaky. Một ca có thể bảo vệ rủi ro quan trọng nhưng cần được thiết kế lại nếu chi phí quá cao hoặc kết quả không đáng tin.

### 3.5. Bằng chứng và khả năng chẩn đoán

Một ca có giá trị khi thất bại cho biết điều gì đã sai và giúp truy nguyên đến thành phần hoặc trạng thái liên quan. Assertion chung như “trang đã tải” có thể quá yếu. Nên xác minh kết quả nghiệp vụ, trạng thái dữ liệu hoặc phản hồi cụ thể, đồng thời lưu log, trace và mã giao dịch cần thiết.

## 4. Ưu tiên theo rủi ro và giá trị phát hiện

Danh mục system và E2E nên bắt đầu từ rủi ro, không phải từ mong muốn có thật nhiều ca. Một cách đánh giá đơn giản là xem xét khả năng xảy ra, tác động, phạm vi ảnh hưởng và khả năng phát hiện vấn đề sau khi triển khai.

### 4.1. Xây dựng phát biểu rủi ro

Có thể dùng cấu trúc:

> Do **[nguyên nhân]**, có thể xảy ra **[sự kiện lỗi]**, dẫn đến **[tác động nghiệp vụ hoặc người dùng]**.

Ví dụ:

> Do callback thanh toán có thể đến lặp sau khi mạng gián đoạn, hệ thống có thể ghi nhận cùng một giao dịch nhiều lần, dẫn đến sai trạng thái đơn hàng và cần đối soát thủ công.

Từ phát biểu này, nhóm có thể thiết kế một ca E2E gửi callback lặp và xác minh chỉ có một giao dịch hợp lệ được ghi nhận. Một số chi tiết về xử lý khóa idempotency có thể được kiểm tra thêm ở unit hoặc integration test.

### 4.2. Đánh giá rủi ro

Nhóm có thể xem xét:

- Khả năng xảy ra dựa trên lịch sử lỗi, độ phức tạp và số lượng phụ thuộc.
- Mức độ tác động đến tiền, dữ liệu, quyền, an toàn, hoạt động hoặc uy tín.
- Số người dùng, giao dịch, tenant hoặc dịch vụ có thể bị ảnh hưởng.
- Khả năng phát hiện và khắc phục trước khi người dùng chịu hậu quả.
- Mức độ khó kiểm tra bằng phương pháp khác.

Ma trận khả năng xảy ra và tác động có thể dùng để sắp xếp ưu tiên, nhưng không thay thế đánh giá chuyên môn. Rủi ro bảo mật, quyền riêng tư hoặc tuân thủ có thể cần kiểm tra bắt buộc dù khả năng xảy ra được đánh giá thấp.

### 4.3. Xem xét giá trị biên và phần đóng góp mới

Khi hai ca có cùng mức rủi ro, hãy ưu tiên ca có thể phát hiện lỗi mới, bao phủ một trạng thái chưa được kiểm tra hoặc xác minh một ranh giới quan trọng. Không nên thêm ca chỉ vì nó làm tăng số lượng hoặc phần trăm coverage.

Một bảng ưu tiên tham khảo:

| Tiêu chí | Câu hỏi |
|---|---|
| Tác động | Nếu lỗi xảy ra, hậu quả đối với người dùng hoặc nghiệp vụ nghiêm trọng đến đâu? |
| Khả năng xảy ra | Có lịch sử lỗi, thay đổi gần đây hoặc độ phức tạp làm tăng khả năng lỗi không? |
| Khoảng trống hiện tại | Danh mục đã có ca nào kiểm tra cùng rủi ro chưa? |
| Khả năng phát hiện | Ca mới có thể tìm ra lỗi khác biệt hoặc xác minh trạng thái chưa được kiểm tra không? |
| Mức đại diện | Dữ liệu và hành trình có phản ánh cách sử dụng thực tế không? |
| Chi phí | Thời gian chạy, setup và bảo trì là bao nhiêu? |
| Độ ổn định | Ca có thể chạy lặp lại với kết quả đáng tin không? |

Có thể chấm điểm để hỗ trợ thảo luận, nhưng không nên xem tổng điểm là quyết định tự động. Một rủi ro nghiêm trọng không được bỏ qua chỉ vì chi phí kiểm thử cao; khi cần, hãy tìm cách kiểm tra ở cấp khác hoặc chia nhỏ bằng chứng.

## 5. Dùng kỹ thuật thiết kế test để giảm số tổ hợp

Một hành trình có thể có nhiều vai trò, dữ liệu, trạng thái, trình duyệt, thiết bị và kết quả phụ thuộc. Nếu kiểm tra mọi tổ hợp bằng E2E, số lượng ca có thể tăng theo cấp số nhân. Các kỹ thuật thiết kế test giúp chọn trường hợp đại diện.

### 5.1. Phân vùng tương đương

Chia dữ liệu đầu vào thành các nhóm được kỳ vọng xử lý giống nhau. Chọn một hoặc một vài giá trị đại diện cho mỗi nhóm thay vì kiểm tra mọi giá trị.

Ví dụ, trường số lượng sản phẩm cho phép từ 1 đến 20:

- Hợp lệ: 1 đến 20.
- Không hợp lệ thấp: nhỏ hơn 1.
- Không hợp lệ cao: lớn hơn 20.
- Không hợp lệ về kiểu: chữ hoặc giá trị không phải số.

Unit test có thể kiểm tra nhiều giá trị biên và kiểu dữ liệu. E2E chỉ cần một số trường hợp đại diện để xác minh validation, thông báo và trạng thái giỏ hàng được tích hợp đúng.

### 5.2. Phân tích giá trị biên

Lỗi thường xuất hiện tại điểm chuyển giữa các phân vùng. Với giới hạn 1 đến 20, các giá trị 0, 1, 20 và 21 thường có giá trị kiểm tra cao. Chọn các biên quan trọng ở cấp phù hợp; không cần tạo toàn bộ biến thể ở E2E nếu logic giới hạn đã được kiểm tra kỹ ở cấp thấp.

### 5.3. Kiểm thử chuyển trạng thái

Với hành trình có nhiều trạng thái, hãy xác định trạng thái hợp lệ và chuyển tiếp được phép. Ví dụ đơn hàng có thể đi qua `DRAFT`, `PENDING_PAYMENT`, `PAID`, `SHIPPED`, `DELIVERED` hoặc `CANCELLED`.

Không nhất thiết phải tạo một E2E cho mọi đường đi. Hãy chọn:

- Một luồng chính đại diện.
- Các chuyển tiếp có rủi ro cao như thanh toán thành công, hủy trước giao hàng và hoàn tiền.
- Một số chuyển tiếp không hợp lệ cần bị từ chối.
- Trường hợp lỗi giữa chừng và phục hồi nếu có tác động lớn.

Các quy tắc chuyển trạng thái có thể được kiểm tra rộng ở unit/component; E2E xác nhận các luồng quan trọng xuyên suốt.

### 5.4. Pairwise và kiểm thử tổ hợp

Khi nhiều yếu tố có thể kết hợp, kiểm thử pairwise chọn tập trường hợp sao cho mọi cặp giá trị của các yếu tố được xuất hiện ít nhất một lần. Cách này giảm đáng kể số tổ hợp so với kiểm tra toàn bộ, nhưng không bảo đảm phát hiện lỗi chỉ xảy ra khi ba hoặc nhiều yếu tố kết hợp.

Ví dụ các yếu tố có thể gồm vai trò người dùng, phương thức thanh toán, loại thiết bị và trạng thái mạng. Pairwise có thể phù hợp cho một tập kiểm thử tương thích; các tổ hợp có rủi ro đặc biệt vẫn cần được bổ sung dựa trên nghiệp vụ và lịch sử lỗi.

### 5.5. Kiểm thử dựa trên kịch bản và lỗi đã biết

Chọn kịch bản dựa trên cách người dùng thực hiện công việc, sự cố từng xảy ra và các điểm dễ sai trong kiến trúc. Lỗi production trước đây nên được phân tích để xác định test hồi quy có giá trị. Không phải lỗi nào cũng cần E2E; nếu nguyên nhân là một hàm tính toán, unit regression test có thể phù hợp hơn.

## 6. Chọn phạm vi system và E2E phù hợp

System test đánh giá hệ thống tích hợp theo yêu cầu. E2E test thường đi qua nhiều thành phần từ điểm khởi đầu đến kết quả cuối. Ranh giới giữa hai loại có thể khác nhau theo tổ chức, vì vậy cần định nghĩa trong dự án.

### 6.1. Ưu tiên hành trình cốt lõi

Một bộ E2E nhỏ nên bảo vệ các hành trình mang ý nghĩa lớn đối với người dùng hoặc hoạt động, chẳng hạn:

- Người dùng đăng nhập và được cấp đúng quyền.
- Người mua tạo đơn và nhận mã đơn hàng.
- Thanh toán thành công và trạng thái đơn hàng được cập nhật.
- Người dùng có quyền xem hoặc xuất đúng dữ liệu thuộc phạm vi của mình.
- Người vận hành xử lý một tình huống lỗi quan trọng hoặc khôi phục dịch vụ.

Hãy ưu tiên kết quả cuối và các bất biến nghiệp vụ. Một test đăng nhập không nên chỉ xác minh URL đổi; nó cần xác minh danh tính và quyền phù hợp. Một test đặt hàng không nên chỉ xác minh nút bấm hoạt động; nó cần xác minh đơn hàng được tạo đúng và trạng thái liên quan nhất quán.

### 6.2. Giữ các chi tiết ở cấp thấp hơn

Những biến thể logic có thể kiểm tra ổn định ở unit hoặc component nên được đặt ở đó. Ví dụ: tất cả tổ hợp quy tắc giảm giá, thuế và làm tròn có thể được kiểm tra ở cấp thấp; E2E chỉ cần một số tình huống đại diện để xác nhận giá trị được truyền và hiển thị đúng qua hành trình.

Contract và integration test nên bảo vệ giao diện giữa các dịch vụ, schema, transaction và xử lý thông điệp. E2E được giữ cho những luồng mà việc phối hợp nhiều thành phần là chính điều cần chứng minh.

### 6.3. Không bỏ qua ngoại lệ quan trọng

Giảm số ca không có nghĩa chỉ giữ happy path. Các trường hợp từ chối quyền, dữ liệu không hợp lệ, gửi lặp, timeout, callback trễ hoặc hủy giao dịch có thể có tác động cao. Hãy giữ chúng nếu chúng đại diện cho một rủi ro khác biệt và cần kiểm tra ở cấp hệ thống.

### 6.4. Giới hạn các biến thể giao diện

Không cần chạy mọi hành trình E2E trên mọi trình duyệt, thiết bị và kích thước màn hình. Hãy chọn ma trận đại diện dựa trên dữ liệu người dùng, mức độ phổ biến và khác biệt nền tảng. Các thành phần giao diện có thể được kiểm tra rộng hơn ở component/UI test; E2E tập trung vào một số môi trường có giá trị cao.

## 7. Nhận diện trùng lặp và giá trị biên thấp

Trùng lặp không chỉ là hai test có cùng tên hoặc cùng bước. Hai test có thể khác dữ liệu nhưng vẫn kiểm tra cùng một hành vi, cùng một đường đi và cùng một loại lỗi. Ngược lại, hai test có vẻ giống nhau vẫn có thể cần thiết nếu chúng kiểm tra các ranh giới hoặc vai trò khác nhau.

### 7.1. Dấu hiệu test có giá trị bổ sung thấp

- Cùng hành trình, cùng điều kiện và cùng assertion với một test khác.
- Chỉ thay đổi một giá trị dữ liệu nhưng logic đã được bao phủ ở unit test.
- Không liên kết được với yêu cầu, rủi ro hoặc lỗi lịch sử cụ thể.
- Assertion chỉ kiểm tra giao diện tải xong, không xác minh kết quả nghiệp vụ.
- Test thường xuyên bị bỏ qua hoặc không còn chạy trong pipeline.
- Test thất bại do môi trường nhưng không cung cấp thông tin chẩn đoán hữu ích.

### 7.2. Dùng ma trận so sánh

Khi rà soát hai ca, có thể so sánh:

| Khía cạnh | Test A | Test B | Câu hỏi quyết định |
|---|---|---|---|
| Yêu cầu/rủi ro | Mã yêu cầu hoặc rủi ro | Mã yêu cầu hoặc rủi ro | Có bảo vệ cùng một điều không? |
| Hành trình | Các bước và trạng thái | Các bước và trạng thái | Có đường đi khác biệt không? |
| Dữ liệu | Phân vùng và giá trị | Phân vùng và giá trị | Khác biệt có thể làm lộ lỗi mới không? |
| Ranh giới | Thành phần được đi qua | Thành phần được đi qua | Có kiểm tra tích hợp khác nhau không? |
| Assertion | Kết quả được xác minh | Kết quả được xác minh | Có bằng chứng bổ sung không? |
| Chi phí | Thời gian và bảo trì | Thời gian và bảo trì | Giá trị tăng thêm có tương xứng không? |

Nếu hai test gần như giống nhau, có thể hợp nhất thành một test tham số hóa hoặc giữ một test đại diện. Tuy nhiên, chỉ hợp nhất khi vẫn giữ được khả năng chẩn đoán, mức độ rõ ràng và tính độc lập.

### 7.3. Phân biệt hợp nhất với xóa bỏ

Hợp nhất là đưa nhiều trường hợp tương tự vào một cấu trúc chung nhưng vẫn chạy các biến thể cần thiết. Xóa bỏ là loại một trường hợp khỏi danh mục. Trước khi xóa, cần xác định bằng chứng nào sẽ mất, liệu trường hợp đó có bảo vệ rủi ro duy nhất hay không và có phép kiểm thử khác thay thế được không.

## 8. Khả năng duy trì của bộ system và E2E

Một test có giá trị phát hiện cao nhưng liên tục hỏng do dữ liệu hoặc selector không ổn định sẽ làm giảm độ tin cậy của pipeline. Khả năng duy trì cần được xem xét ngay khi thiết kế, không chỉ sau khi suite trở nên quá lớn.

### 8.1. Tính ổn định

Test nên cho kết quả nhất quán trong cùng điều kiện. Tránh phụ thuộc vào sleep cố định, thời gian thực không kiểm soát, thứ tự chạy, dữ liệu dùng chung hoặc dịch vụ bên ngoài không ổn định. Với luồng bất đồng bộ, hãy chờ điều kiện quan sát được với timeout hợp lý.

Không nên dùng retry tự động để biến test flaky thành Pass mà không lưu lần thất bại đầu. Cần theo dõi tỷ lệ flaky và xử lý nguyên nhân.

### 8.2. Dữ liệu kiểm thử

Test cần tạo dữ liệu riêng hoặc sử dụng fixture có phiên bản, có thể tái tạo và dọn dẹp an toàn. Tránh phụ thuộc vào dữ liệu production hoặc một tài khoản dùng chung có thể bị test khác thay đổi.

Với dữ liệu nhạy cảm, dùng dữ liệu giả hoặc đã được xử lý phù hợp. Không đưa token, thông tin cá nhân hoặc bí mật vào log và báo cáo.

### 8.3. Selector và giao diện

Đối với UI E2E, ưu tiên selector ổn định gắn với vai trò, nhãn hoặc thuộc tính kiểm thử được thiết kế có chủ đích. Tránh selector phụ thuộc quá sâu vào cấu trúc DOM hoặc vị trí hiển thị dễ thay đổi. Test nên thao tác theo ý nghĩa người dùng và xác minh trạng thái cuối, không phụ thuộc chi tiết trình bày không liên quan.

### 8.4. Setup, teardown và môi trường

Thiết lập môi trường cần được quản lý và có thể tái hiện. Cleanup chỉ nên xóa tài nguyên do test sở hữu. Nếu một test cần nhiều bước thủ công, dữ liệu đặc biệt hoặc phụ thuộc vào môi trường dùng chung, chi phí duy trì sẽ tăng và khả năng chạy độc lập giảm.

### 8.5. Khả năng chẩn đoán

Khi thất bại, test nên cung cấp đủ ngữ cảnh: bước hiện tại, dữ liệu định danh, mã giao dịch, phiên bản ứng dụng, log, trace và trạng thái cuối. Một test chỉ báo “expected true but was false” trong một hành trình dài thường tốn nhiều thời gian điều tra.

### 8.6. Quyền sở hữu

Mỗi nhóm test cần có người hoặc nhóm chịu trách nhiệm cập nhật khi hành trình, API hoặc kiến trúc thay đổi. Test không có chủ sở hữu dễ bị bỏ quên, trở nên lỗi thời hoặc bị tắt mà không đánh giá tác động.

## 9. Đánh giá chi phí vòng đời của một ca

Chi phí của một ca không chỉ là thời gian chạy. Cần xem xét toàn bộ vòng đời:

- Công thiết kế và tạo dữ liệu.
- Công chuẩn bị môi trường, tài khoản và phụ thuộc.
- Thời gian thực thi và tài nguyên CI.
- Công điều tra false failure hoặc flaky.
- Công cập nhật khi giao diện, schema hoặc kiến trúc thay đổi.
- Công duy trì fixture, selector, mock và dữ liệu chuẩn.
- Công lưu trữ và đọc hiểu bằng chứng.

Một ca chậm nhưng bảo vệ rủi ro rất cao có thể vẫn đáng duy trì. Một ca nhanh nhưng không có assertion có ý nghĩa có thể không đáng giữ. Quyết định cần dựa trên giá trị phát hiện, tính duy nhất của bằng chứng và chi phí tổng thể.

Có thể dùng khái niệm **giá trị biên (marginal value)**: phần bằng chứng hoặc khả năng phát hiện lỗi mà một ca bổ sung mang lại so với danh mục hiện tại. Nếu giá trị biên gần bằng không và không có yêu cầu bắt buộc, nên xem xét hợp nhất hoặc chuyển kiểm tra xuống cấp phù hợp hơn.

## 10. Quy trình chọn, rà soát và tối ưu danh mục

Một quy trình thực tế có thể gồm:

1. **Lập danh sách hành trình và rủi ro**: xác định các hành trình quan trọng, yêu cầu, trạng thái và lỗi có hậu quả đáng kể.
2. **Xác định loại bằng chứng cần có**: quyết định điều gì cần được chứng minh ở cấp system hoặc E2E và điều gì có thể kiểm tra ở cấp thấp hơn.
3. **Tạo kịch bản đại diện**: dùng phân vùng tương đương, giá trị biên, chuyển trạng thái, pairwise và lịch sử lỗi để chọn ca.
4. **Đánh giá giá trị bổ sung**: so sánh với các ca hiện tại về yêu cầu, rủi ro, hành trình, ranh giới và assertion.
5. **Ước lượng chi phí vòng đời**: đo thời gian, setup, dữ liệu, độ ổn định và công bảo trì.
6. **Ưu tiên theo rủi ro**: giữ các ca bảo vệ hành trình hoặc hậu quả nghiêm trọng; sắp xếp các ca còn lại theo giá trị phát hiện.
7. **Tổ chức thực thi**: đặt ca vào pipeline hoặc lịch chạy phù hợp với chi phí và nhu cầu phản hồi.
8. **Theo dõi sức khỏe**: đo thời gian, flaky rate, tỷ lệ lỗi phát hiện, chi phí điều tra và mức độ cập nhật.
9. **Rà soát định kỳ**: hợp nhất, sửa, bổ sung hoặc loại bỏ ca sau khi đánh giá tác động đến độ bao phủ.

## 11. Ví dụ xuyên suốt: chọn bộ E2E cho hành trình đặt hàng

Giả sử một cửa hàng trực tuyến có hành trình từ chọn sản phẩm, thêm vào giỏ, đặt hàng, thanh toán đến nhận xác nhận. Nếu tạo một E2E cho mọi tổ hợp sản phẩm, số lượng, mã giảm giá, phương thức thanh toán, thiết bị và trạng thái mạng, số ca sẽ tăng rất nhanh.

### 11.1. Xác định rủi ro chính

- Đơn hàng có thể chứa sai sản phẩm hoặc số lượng.
- Tổng tiền có thể sai khi áp dụng khuyến mại.
- Gửi lặp có thể tạo đơn hàng hoặc giao dịch trùng.
- Callback thanh toán đến trễ hoặc lặp có thể làm sai trạng thái.
- Người dùng có thể truy cập dữ liệu đơn hàng không thuộc quyền của mình.
- Hành trình có thể không hoàn tất khi dịch vụ phụ thuộc tạm thời không sẵn sàng.

### 11.2. Phân bổ kiểm thử theo cấp

| Rủi ro | Cấp kiểm thử chính | E2E cần giữ |
|---|---|---|
| Công thức giá, thuế và giảm giá | Unit / component | Một ca đại diện xác minh tổng tiền hiển thị và lưu đúng trong đơn hàng. |
| Tạo đơn từ giỏ hàng | Component / integration | Một luồng đặt hàng thành công xuyên hệ thống. |
| Gửi yêu cầu lặp | Unit / integration | Một ca E2E gửi lại thao tác xác nhận và xác minh chỉ có một đơn. |
| Callback thanh toán trễ hoặc lặp | Component / integration / contract | Một ca đại diện xác minh trạng thái cuối không bị ghi nhận sai. |
| Truy cập đơn hàng trái quyền | Integration / security | Một ca kiểm tra người dùng khác không thể xem đơn hàng ngoài phạm vi. |
| Phụ thuộc thanh toán ngừng hoạt động | Integration / resilience | Một ca E2E hoặc system test xác minh hành vi từ chối/chờ phù hợp khi rủi ro cao. |

### 11.3. Bộ E2E đại diện

Một danh mục ban đầu có thể giữ các ca sau:

1. Đặt hàng và thanh toán thành công với giỏ hàng hợp lệ.
2. Gửi lặp yêu cầu xác nhận và chỉ ghi nhận một đơn hàng.
3. Thanh toán bị từ chối và đơn hàng không chuyển sang trạng thái đã thanh toán.
4. Callback thanh toán đến lặp hoặc đến trễ nhưng trạng thái cuối vẫn nhất quán.
5. Người dùng không có quyền bị từ chối khi truy cập đơn hàng của người khác.
6. Phụ thuộc thanh toán không sẵn sàng và hệ thống hiển thị trạng thái chờ hoặc lỗi theo quy tắc đã thống nhất.

Danh sách này là ví dụ, không phải số lượng chuẩn. Nếu một rủi ro đã được kiểm chứng đầy đủ ở cấp integration và E2E không tạo thêm bằng chứng, có thể không cần giữ ca E2E tương ứng. Ngược lại, nếu có lỗi production hoặc yêu cầu quan trọng chưa được bảo vệ, cần bổ sung ca phù hợp.

### 11.4. Rà soát giá trị và chi phí

Giả sử nhóm có 12 ca E2E gần giống nhau cho các mã giảm giá khác nhau. Logic áp dụng mã giảm giá đã có unit test cho các phân vùng và giá trị biên. Nếu các ca E2E chỉ thay mã nhưng cùng đi qua một hành trình và cùng xác minh kết quả, có thể giữ một hoặc hai ca đại diện để xác nhận tích hợp, còn các biến thể logic ở unit/component test.

Trước khi hợp nhất, cần kiểm tra mã giảm giá có loại đặc biệt nào làm thay đổi quy trình thanh toán hoặc trạng thái đơn hàng không. Nếu có, trường hợp đó có thể đại diện cho một rủi ro khác biệt và cần giữ riêng.

## 12. Chỉ số đánh giá sức khỏe danh mục system và E2E

Không có một chỉ số duy nhất phản ánh chất lượng bộ kiểm thử. Nên kết hợp các chỉ số sau:

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Thời gian suite | Thời gian chạy tổng và phân vị | Phát hiện xu hướng tăng và nhóm gây chậm. |
| Flaky rate | Tỷ lệ test có kết quả không ổn định | Xác định test hoặc môi trường cần sửa. |
| Tỷ lệ phát hiện lỗi có giá trị | Số lỗi thực tế được phát hiện, phân loại theo mức độ và loại test | Đánh giá danh mục có tìm ra lỗi quan trọng hay không. |
| Tỷ lệ lỗi lọt | Lỗi được phát hiện sau phát hành mà có thể được kiểm tra trước đó | Tìm khoảng trống trong hành trình hoặc ranh giới. |
| Chi phí bảo trì | Thời gian sửa test, fixture, selector và môi trường | Nhận diện test quá nhạy với thay đổi. |
| Độ bao phủ rủi ro | Rủi ro trọng yếu có kịch bản và bằng chứng phù hợp | Bảo đảm danh mục tập trung vào điều quan trọng. |
| Tỷ lệ test không còn liên kết | Test không truy vết được đến yêu cầu, rủi ro hoặc mục đích hiện tại | Rà soát test lỗi thời hoặc không cần thiết. |
| Thời gian chẩn đoán | Thời gian từ khi test Fail đến khi xác định nguyên nhân | Cải thiện log, trace và assertion. |

Không nên thưởng cho nhóm chỉ dựa trên số lượng test hoặc số lỗi được tìm thấy. Các chỉ số cần được đọc cùng bối cảnh: thay đổi kiến trúc, lượng mã mới, mức độ phức tạp và chất lượng môi trường.

## 13. Khi nào nên thêm, hợp nhất, sửa hoặc loại bỏ test?

### Thêm test khi:

- Có yêu cầu hoặc rủi ro quan trọng chưa được bảo vệ.
- Một lỗi production hoặc lỗi nghiêm trọng cho thấy khoảng trống cụ thể.
- Một ranh giới kiến trúc mới được tạo ra hoặc thay đổi.
- Test hiện tại không xác minh được trạng thái cuối hoặc assertion chưa đủ mạnh.
- Có tổ hợp hoặc trạng thái đặc biệt mà kỹ thuật chọn mẫu hiện tại chưa bao phủ.

### Hợp nhất test khi:

- Nhiều ca kiểm tra cùng hành trình và cùng loại lỗi.
- Các biến thể có thể được biểu diễn bằng tham số mà vẫn giữ rõ ngữ cảnh và kết quả.
- Một ca có thể bao phủ các điều kiện tương đương mà không làm khó chẩn đoán.

### Sửa test khi:

- Test flaky do sleep, dữ liệu dùng chung, selector hoặc phụ thuộc thứ tự.
- Assertion yếu hoặc chỉ kiểm tra dấu hiệu bề mặt.
- Setup, teardown hoặc dữ liệu không thể tái tạo.
- Hành vi sản phẩm đã thay đổi nhưng test chưa được cập nhật theo yêu cầu đã xác nhận.

### Loại bỏ test khi:

- Không còn yêu cầu, rủi ro hoặc hành vi nào mà test bảo vệ.
- Bằng chứng của test đã được thay thế bởi phép kiểm thử khác ổn định hơn và ở cấp phù hợp.
- Test trùng lặp và không bổ sung độ bao phủ hoặc khả năng chẩn đoán.
- Test dựa trên hành vi đã bị loại bỏ hoặc môi trường không còn được hỗ trợ.

Trước khi xóa, hãy truy vết đến yêu cầu và rủi ro để bảo đảm không loại bỏ bằng chứng duy nhất. Việc giảm số lượng phải có ghi nhận lý do và đánh giá tác động.

## 14. Những sai lầm thường gặp

- **Đặt chỉ tiêu số lượng E2E**: nhóm tạo thêm ca để đạt số mục tiêu nhưng không tăng khả năng phát hiện lỗi. Hãy ưu tiên rủi ro và bằng chứng bổ sung.
- **Chỉ giữ happy path**: bộ test ngắn nhưng bỏ qua lỗi thanh toán, quyền, gửi lặp hoặc phục hồi. Hãy giữ các ngoại lệ có tác động cao.
- **Đưa mọi biến thể lên E2E**: logic được kiểm tra lặp lại ở cấp đắt đỏ. Hãy chuyển các phân vùng và giá trị biên phù hợp xuống cấp thấp.
- **Xóa test vì chậm mà không phân tích**: có thể loại bỏ ca bảo vệ rủi ro nghiêm trọng. Hãy đo chi phí và xem xét tối ưu trước.
- **Giữ test vì đã đầu tư nhiều công**: chi phí đã bỏ ra không phải lý do để duy trì một ca không còn giá trị. Hãy đánh giá lợi ích hiện tại và chi phí tương lai.
- **Assertion quá yếu**: test Pass dù trạng thái nghiệp vụ sai. Hãy xác minh dữ liệu, quyền và kết quả cuối phù hợp.
- **Không kiểm soát dữ liệu và môi trường**: test thất bại ngẫu nhiên hoặc phụ thuộc thứ tự. Hãy cô lập dữ liệu và chuẩn hóa điều kiện chạy.
- **Không truy vết test đến rủi ro**: danh mục tăng nhưng không ai biết test bảo vệ điều gì. Hãy ghi mã yêu cầu, hành trình hoặc rủi ro liên quan.
- **Dùng retry che lỗi không ổn định**: kết quả cuối Pass làm mất dấu lần thất bại đầu. Hãy ghi nhận retry và xử lý nguyên nhân.
- **Không rà soát sau thay đổi kiến trúc**: test cũ có thể không còn đại diện cho luồng mới. Hãy cập nhật danh mục khi ranh giới hoặc phụ thuộc thay đổi.

## 15. Quy trình quản lý danh mục system và E2E

Nhóm có thể áp dụng trình tự sau:

1. **Xác định hành trình và rủi ro**: lập danh sách hành trình cốt lõi, yêu cầu quan trọng, trạng thái và lỗi có tác động lớn.
2. **Phân loại bằng chứng theo cấp**: xác định phần nào cần system/E2E và phần nào phù hợp hơn với unit, component, contract hoặc integration.
3. **Thiết kế tập đại diện**: dùng phân vùng tương đương, giá trị biên, chuyển trạng thái, pairwise và lịch sử lỗi.
4. **Đánh giá giá trị biên**: so sánh từng ca mới với danh mục hiện tại để xác định loại lỗi hoặc ranh giới bổ sung.
5. **Ước lượng chi phí vòng đời**: tính thời gian chạy, setup, dữ liệu, độ ổn định, chẩn đoán và bảo trì.
6. **Ưu tiên và phê duyệt danh mục**: giữ ca bảo vệ rủi ro quan trọng; ghi rõ lý do cho các ca có chi phí cao.
7. **Tổ chức thực thi và quan sát**: đặt ca vào pipeline phù hợp, lưu kết quả, log, trace và mã giao dịch.
8. **Rà soát định kỳ**: theo dõi flaky rate, thời gian suite, lỗi lọt và test không còn liên kết.
9. **Điều chỉnh có truy vết**: thêm, sửa, hợp nhất hoặc loại bỏ test và cập nhật ma trận độ bao phủ.

## 16. Tự kiểm tra

Trước khi chốt hoặc thay đổi danh mục system và E2E, hãy tự hỏi:

- Mỗi ca có liên kết đến hành trình, yêu cầu hoặc rủi ro cụ thể không?
- Ca có thể phát hiện loại lỗi nào mà các ca khác chưa kiểm tra?
- Vì sao cần kiểm tra ở cấp system hoặc E2E?
- Các biến thể logic có thể được kiểm tra ở cấp thấp hơn không?
- Những trường hợp lỗi, trạng thái và quyền có tác động cao đã được giữ lại chưa?
- Có ca trùng lặp hoặc có giá trị biên thấp không?
- Test có dữ liệu riêng, assertion đủ mạnh và kết quả ổn định không?
- Thời gian chạy và công bảo trì có tương xứng với giá trị phát hiện không?
- Có thể chẩn đoán nhanh khi test thất bại không?
- Việc thêm, hợp nhất hoặc xóa ca có làm mất bằng chứng duy nhất cho một rủi ro không?

## Kết luận

Số lượng system và E2E test cần phản ánh giá trị phát hiện lỗi, mức độ quan trọng của hành trình và khả năng duy trì lâu dài. Một danh mục hiệu quả bảo vệ các rủi ro và trạng thái quan trọng bằng những ca có assertion rõ, dữ liệu kiểm soát được và bằng chứng có thể truy nguyên. Các biến thể logic nên được kiểm tra ở cấp phù hợp; system và E2E tập trung xác minh sự phối hợp và kết quả xuyên suốt. Khi đánh giá giá trị biên, chi phí vòng đời và sức khỏe bộ kiểm thử định kỳ, nhóm có thể giữ danh mục đủ mạnh mà vẫn ổn định và dễ duy trì.
