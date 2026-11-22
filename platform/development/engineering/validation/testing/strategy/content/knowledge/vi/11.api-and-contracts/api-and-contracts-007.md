# Xác định bằng chứng còn cần từ tích hợp thật hoặc luồng đầu cuối

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), unit test và contract test có thể cung cấp bằng chứng nhanh về logic cục bộ và thỏa thuận giao tiếp. Tuy nhiên, chúng không luôn chứng minh rằng các thành phần thực sự hoạt động cùng nhau trong môi trường triển khai. Khi một thay đổi đi qua nhiều dịch vụ, cơ sở dữ liệu, hàng đợi, cấu hình hoặc giao diện người dùng, nhóm cần xác định phần bằng chứng còn thiếu và quyết định có cần kiểm thử tích hợp thật hay kiểm thử đầu cuối (end-to-end – E2E) hay không.

Mục tiêu không phải là chạy E2E cho mọi tình huống. Nhóm cần chỉ ra câu hỏi nào chưa được trả lời bởi bằng chứng hiện có, rủi ro nào có thể xảy ra tại ranh giới thực tế và tầng kiểm thử nào có thể cung cấp bằng chứng đáng tin cậy nhất. Bài học này hướng dẫn cách nhận diện khoảng trống bằng chứng, đánh giá giới hạn của kiểm thử mô phỏng, chọn kiểm thử tích hợp hoặc E2E theo rủi ro và ghi nhận cơ sở cho quyết định.

## 1. Hiểu bằng chứng mà mỗi tầng kiểm thử cung cấp

Một kết quả kiểm thử chỉ hỗ trợ kết luận trong phạm vi điều kiện và môi trường đã được kiểm tra. Khi xem xét một luồng nghiệp vụ, cần biết mỗi tầng đã chứng minh điều gì và phần nào vẫn là giả định.

### 1.1. Unit test chứng minh logic cục bộ

Unit test thường xác minh một hàm, lớp hoặc đơn vị logic với các phụ thuộc được kiểm soát. Nó phù hợp để kiểm tra:

- Quy tắc nghiệp vụ, phép tính và chuyển trạng thái.
- Giá trị biên, dữ liệu không hợp lệ và trường hợp lỗi.
- Nhánh điều kiện, xử lý ngoại lệ và kết quả trả về.
- Quy tắc xác thực và phân quyền được thực hiện trong đơn vị đó.

Nếu unit test của CheckoutService dùng mock cho PaymentGateway, test có thể chứng minh dịch vụ tạo yêu cầu thanh toán với tham số đúng. Nó không chứng minh rằng API của nhà cung cấp thật chấp nhận yêu cầu, chứng thư và cấu hình mạng đúng, hoặc callback thực tế được xử lý thành công.

### 1.2. Contract test chứng minh hai phía tuân thủ thỏa thuận

Contract test kiểm tra producer và consumer tuân thủ schema hoặc giao diện đã thống nhất. Nó có thể xác minh:

- Tên trường, kiểu dữ liệu và trường bắt buộc.
- Cấu trúc request, response hoặc thông điệp.
- Mã phản hồi và cách biểu diễn lỗi.
- Các thay đổi tương thích hoặc không tương thích của hợp đồng.

Contract test hữu ích để phát hiện sai lệch giao diện trước khi triển khai chung. Tuy nhiên, hợp đồng hợp lệ không chứng minh dịch vụ thật đang chạy, cấu hình định tuyến đúng, quyền truy cập hợp lệ hoặc toàn bộ chuỗi xử lý hoàn tất.

### 1.3. Integration test chứng minh các thành phần phối hợp tại ranh giới

Integration test xác minh hai hay nhiều thành phần thực sự trao đổi dữ liệu hoặc phối hợp qua một ranh giới. Tùy mục tiêu, nó có thể dùng cơ sở dữ liệu, message broker, service nội bộ hoặc adapter thật trong môi trường thử nghiệm.

Ví dụ, integration test có thể chứng minh:

- Repository ghi và đọc dữ liệu qua cơ sở dữ liệu thật.
- Producer phát thông điệp có thể được broker nhận.
- Consumer xử lý thông điệp và cập nhật trạng thái.
- API gateway chuyển request đến đúng service.
- Transaction rollback khi một bước ghi dữ liệu thất bại.

Một integration test thường tập trung vào một hoặc một số ranh giới cụ thể, vì vậy dễ chẩn đoán hơn một luồng E2E lớn.

### 1.4. End-to-end test chứng minh hành trình xuyên suốt

E2E test kiểm tra một luồng từ điểm bắt đầu đến kết quả mà người dùng hoặc hệ thống bên ngoài có thể quan sát. Nó có thể đi qua giao diện, API, nhiều dịch vụ, cơ sở dữ liệu và các tích hợp.

Ví dụ, một E2E test thanh toán có thể xác minh người dùng tạo đơn, thanh toán qua sandbox, nhận kết quả và nhìn thấy trạng thái đơn được cập nhật. Test này giúp phát hiện lỗi do phối hợp nhiều thành phần, cấu hình hoặc ánh xạ dữ liệu mà unit test riêng lẻ không thể phát hiện.

E2E test không tự động chứng minh mọi nhánh nghiệp vụ hoặc mọi trường hợp lỗi. Một luồng thành công duy nhất không đủ bao phủ callback trùng, timeout, quyền sai hoặc dữ liệu biên.

### 1.5. So sánh phạm vi bằng chứng

| Tầng | Bằng chứng chính | Điều chưa được chứng minh tự động |
|---|---|---|
| Unit test | Logic và trạng thái của đơn vị nhỏ. | Giao tiếp với phụ thuộc thật, cấu hình triển khai và hành vi xuyên hệ thống. |
| Contract test | Hai phía tuân thủ schema hoặc giao diện. | Dịch vụ thật sẵn sàng, mạng và cấu hình hoạt động, luồng hoàn tất. |
| Integration test | Các thành phần phối hợp qua ranh giới cụ thể. | Toàn bộ hành trình người dùng hoặc mọi tích hợp trong hệ thống. |
| End-to-end test | Một hành trình xuyên suốt trong môi trường xác định. | Mọi tổ hợp dữ liệu, tải, trạng thái và lỗi có thể xảy ra. |

Các tầng bổ sung bằng chứng cho nhau. Nhóm cần liên kết kết quả với mục tiêu và rủi ro cụ thể, thay vì coi số lượng tầng đã chạy là thước đo đầy đủ.

## 2. Nhận diện khoảng trống bằng chứng

Trước khi quyết định thêm integration test hoặc E2E test, hãy lập danh sách các kết luận mà nhóm cần đưa ra và bằng chứng hiện có cho từng kết luận.

### 2.1. Bắt đầu từ luồng nghiệp vụ và ranh giới

Phân rã luồng thành các bước và xác định thành phần tham gia. Với mỗi bước, ghi:

- Đầu vào và đầu ra.
- Thành phần gửi và nhận dữ liệu.
- Nơi dữ liệu được lưu hoặc thay đổi.
- Cấu hình, quyền và phụ thuộc bên ngoài.
- Hành vi cần xảy ra khi thành công và khi lỗi.

Ví dụ luồng đặt hàng có thể gồm giao diện web, order API, cơ sở dữ liệu, payment service, nhà cung cấp thanh toán, callback handler và message broker. Một unit test của order API không chứng minh toàn bộ chuỗi đó phối hợp đúng.

### 2.2. Hỏi bằng chứng hiện tại đang dựa trên giả định nào

Với từng kết luận, hãy hỏi:

1. Phụ thuộc nào đang được mock, stub hoặc fake?
2. Dữ liệu có đi qua giao thức và schema thật không?
3. Có sử dụng cấu hình và quyền tương đương môi trường mục tiêu không?
4. Có kiểm tra việc lưu, đọc lại và tính nhất quán dữ liệu không?
5. Có thành phần bất đồng bộ, retry hoặc callback chưa được thực thi thật không?
6. Có kiểm tra kết quả từ góc nhìn người dùng hoặc consumer cuối không?
7. Nếu một dịch vụ thật ngừng hoạt động hoặc phản hồi chậm, hành vi có được xác minh không?

Câu trả lời giúp nhận diện khoảng trống. Ví dụ, test đang dùng mock cho repository nên chưa có bằng chứng về SQL, transaction và mapping. Khi đó, integration test với cơ sở dữ liệu thử nghiệm có thể phù hợp hơn một E2E test toàn hệ thống.

### 2.3. Phân loại khoảng trống

| Loại khoảng trống | Ví dụ | Bằng chứng có thể cần |
|---|---|---|
| Giao tiếp | Producer gửi sai header hoặc consumer không giải mã được payload. | Contract test và integration test với broker hoặc service thật. |
| Persistence | Dữ liệu trong bộ nhớ đúng nhưng migration hoặc transaction thực tế lỗi. | Integration test với cơ sở dữ liệu tương thích. |
| Cấu hình | URL, credential, timeout hoặc feature flag khác môi trường mục tiêu. | Integration test triển khai với cấu hình đại diện; smoke test sau deploy. |
| Bất đồng bộ | Callback trễ, sự kiện trùng hoặc xử lý sai thứ tự. | Integration test với broker/callback thực và kịch bản retry có kiểm soát. |
| Phân quyền xuyên hệ thống | Gateway xác thực nhưng service downstream kiểm tra sai quyền. | Integration test qua ranh giới xác thực; E2E đại diện theo vai trò. |
| Hành trình người dùng | API thành công nhưng giao diện không hiển thị kết quả đúng. | E2E test từ giao diện đến trạng thái cuối. |
| Vận hành | Health check, routing hoặc khả năng khôi phục không đúng sau triển khai. | Kiểm tra trên môi trường triển khai, smoke test và kiểm thử phục hồi phù hợp. |

Không phải mọi khoảng trống đều cần E2E. Hãy chọn tầng gần nhất có thể chứng minh rủi ro đang xét.

## 3. Khi nào cần tích hợp thật?

Tích hợp thật có nghĩa là kiểm tra với thành phần thực hoặc một triển khai tương thích đủ đại diện cho ranh giới đang đánh giá. Điều này không nhất thiết yêu cầu dùng production. Có thể dùng container, sandbox, môi trường staging hoặc dịch vụ thử nghiệm được quản lý.

### 3.1. Cần integration test khi phụ thuộc thật có thể thay đổi kết quả

Cân nhắc integration test khi:

- Câu lệnh SQL, transaction, index hoặc constraint có ảnh hưởng đến hành vi.
- Serialization, protocol hoặc mapping dữ liệu có nguy cơ sai.
- Cấu hình kết nối, quyền truy cập hoặc routing có thể làm giao tiếp thất bại.
- Message broker, queue hoặc consumer có cơ chế retry và xử lý trùng.
- Nhiều service phối hợp qua API hoặc sự kiện.
- Một test double không mô phỏng được đặc tính quan trọng của phụ thuộc.

Ví dụ, mock repository có thể xác nhận phương thức save được gọi, nhưng không chứng minh dữ liệu được ghi vào đúng bảng hoặc transaction rollback khi lỗi. Integration test với cơ sở dữ liệu thử nghiệm cung cấp bằng chứng trực tiếp hơn cho rủi ro này.

### 3.2. Chọn phụ thuộc thật có mục tiêu

Không cần khởi chạy toàn bộ hệ thống nếu chỉ một ranh giới đang có rủi ro. Hãy xác định thành phần tối thiểu cần thật:

- Cơ sở dữ liệu thật cho kiểm tra persistence.
- Broker thật hoặc môi trường broker tương thích cho luồng message.
- Service nội bộ thật cho xác minh giao tiếp và xác thực.
- Nhà cung cấp sandbox cho kiểm tra hợp đồng và callback.
- Adapter hoặc filesystem thật cho kiểm tra thao tác tài nguyên.

Những phụ thuộc không liên quan vẫn có thể được thay thế bằng test double. Cách này giữ phạm vi kiểm tra đủ gần thực tế nhưng giảm độ phức tạp và thời gian chạy.

### 3.3. Xác định mức độ đại diện của môi trường

Integration test chỉ có giá trị trong điều kiện đã thiết lập. Ghi rõ:

- Phiên bản dịch vụ, database, broker và runtime.
- Cấu hình kết nối, timeout, retry và quyền.
- Schema hoặc artifact đang được kiểm tra.
- Dữ liệu ban đầu và cách dọn dữ liệu sau test.
- Những phần được mô phỏng hoặc thay thế.
- Khác biệt quan trọng so với môi trường production.

Nếu staging dùng phiên bản database hoặc cấu hình khác production, kết quả cần được diễn giải trong phạm vi đó. Với rủi ro có ảnh hưởng lớn, cần bổ sung kiểm tra trên môi trường gần production hoặc kiểm tra sau triển khai.

### 3.4. Kiểm tra cả thành công và lỗi tại ranh giới

Một tích hợp hoạt động trong trường hợp thành công vẫn có thể thất bại khi timeout, mất kết nối hoặc nhận dữ liệu sai. Hãy chọn các kịch bản lỗi theo rủi ro:

- Phụ thuộc không phản hồi hoặc phản hồi chậm.
- Phản hồi lỗi 4xx hoặc 5xx.
- Payload thiếu trường hoặc sai định dạng.
- Kết nối bị ngắt giữa giao dịch.
- Thông điệp được gửi lặp hoặc đến sai thứ tự.
- Quyền truy cập hết hạn hoặc không hợp lệ.
- Retry tạo tác dụng phụ trùng lặp.

Không cần kiểm tra mọi mã lỗi ở mọi tầng. Ưu tiên các tình huống có hậu quả lớn hoặc từng gây sự cố.

## 4. Khi nào cần end-to-end test?

E2E test phù hợp khi nhóm cần bằng chứng về một hành trình hoàn chỉnh, nhất là khi nhiều ranh giới cùng góp phần tạo ra kết quả mà người dùng quan sát.

### 4.1. Khi lỗi có thể xuất hiện từ sự phối hợp nhiều thành phần

Cân nhắc E2E test khi:

- Một luồng quan trọng đi qua nhiều dịch vụ hoặc giao diện.
- Ánh xạ dữ liệu giữa các thành phần có thể sai.
- Cấu hình, xác thực hoặc feature flag ảnh hưởng hành vi toàn luồng.
- Kết quả cuối phụ thuộc vào nhiều bước đồng bộ và bất đồng bộ.
- Một lỗi ở giao diện, API hoặc service downstream có thể làm hỏng hành trình người dùng.
- Cần xác nhận sản phẩm triển khai thực sự có thể thực hiện một tác vụ quan trọng.

Ví dụ, unit test xác minh logic tạo đơn, integration test xác minh lưu đơn và phát sự kiện, nhưng chỉ E2E test mới chứng minh người dùng có thể hoàn tất hành trình từ giao diện đến màn hình xác nhận với các thành phần được kết nối.

### 4.2. Chọn ít luồng nhưng có giá trị cao

E2E test thường chậm và nhạy với môi trường. Hãy chọn một số hành trình đại diện dựa trên:

- Tần suất sử dụng và tầm quan trọng với người dùng.
- Hậu quả nếu hành trình thất bại.
- Số lượng ranh giới và phụ thuộc tham gia.
- Lịch sử lỗi lọt qua các tầng thấp hơn.
- Khả năng tái lập và quan sát kết quả.
- Mức độ cần thiết cho quyết định phát hành.

Ví dụ, một hệ thống thương mại điện tử có thể chọn đăng nhập, tìm sản phẩm, đặt hàng và thanh toán làm luồng E2E chính. Các biến thể giá trị biên của thuế hoặc giảm giá nên được kiểm tra sâu hơn ở unit test, thay vì tạo hàng trăm E2E test tương tự.

### 4.3. Xác định điểm bắt đầu và kết thúc rõ ràng

Một E2E test cần nêu:

- Ai hoặc thành phần nào khởi tạo luồng.
- Điều kiện và dữ liệu ban đầu.
- Các hệ thống được đi qua.
- Kết quả quan sát được ở cuối.
- Thời gian chờ tối đa và cách xử lý bước bất đồng bộ.
- Cách dọn dữ liệu và khôi phục trạng thái sau test.

Ví dụ: người dùng có quyền mua đăng nhập bằng tài khoản thử nghiệm, tạo đơn từ sản phẩm còn hàng, thanh toán trên sandbox và nhìn thấy đơn ở trạng thái PAID trong trang lịch sử đơn hàng. Kết quả cuối cần được xác nhận bằng giao diện hoặc API công khai phù hợp, không dựa vào truy cập trực tiếp cấu trúc nội bộ nếu đó không phải mục tiêu.

### 4.4. Không dùng E2E để thay thế mọi kiểm thử khác

Một E2E test thành công chỉ xác minh một kịch bản cụ thể. Nó thường không hiệu quả để kiểm tra hàng trăm giá trị biên, mọi quyền hoặc tất cả mã lỗi. Khi E2E thất bại, nguyên nhân cũng có thể nằm ở nhiều thành phần nên việc chẩn đoán khó hơn.

Hãy dùng unit test cho logic chi tiết, integration test cho ranh giới và E2E cho hành trình có rủi ro cao. Cấu trúc này giúp nhóm có bằng chứng ở nhiều mức mà không phụ thuộc vào một bộ E2E quá lớn.

## 5. Quy trình quyết định bằng chứng bổ sung

Có thể dùng quy trình sau khi review kế hoạch kiểm thử hoặc chuẩn bị phát hành.

### Bước 1: Liệt kê kết luận cần đưa ra

Viết các kết luận dưới dạng hành vi có thể xác minh, ví dụ:

- Đơn hàng được lưu đúng và chỉ tạo một lần.
- Payment service gửi yêu cầu với đúng số tiền.
- Nhà cung cấp trả callback được xác minh và xử lý.
- Trạng thái đơn hàng được cập nhật sau thanh toán.
- Người dùng nhìn thấy trạng thái cuối chính xác.

### Bước 2: Gắn bằng chứng hiện có với từng kết luận

Liên kết mục tiêu với unit test, contract test, integration test, E2E test, review hoặc quan sát vận hành hiện có. Ghi rõ test dùng phụ thuộc thật hay test double.

### Bước 3: Tìm giả định chưa được kiểm chứng

Đánh dấu những kết luận đang dựa trên giả định như:

- Mock được cho là tương đương với nhà cung cấp thật.
- Schema được cho là giống giữa staging và production.
- Callback được giả định luôn đến một lần và đúng thứ tự.
- Feature flag được giả định đã bật đúng nhóm.
- Dữ liệu thử nghiệm được giả định đại diện cho dữ liệu thực.

### Bước 4: Đánh giá hậu quả và khả năng xảy ra

Ưu tiên khoảng trống liên quan đến tiền, dữ liệu, bảo mật, quyền truy cập, giao dịch hoặc hành trình cốt lõi. Xem xét lịch sử lỗi và mức độ khó phát hiện sau triển khai.

### Bước 5: Chọn tầng bổ sung tối thiểu đủ chứng minh

- Nếu khoảng trống nằm ở logic, bổ sung unit test.
- Nếu nằm ở giao tiếp, schema hoặc persistence, bổ sung contract hoặc integration test phù hợp.
- Nếu nằm ở phối hợp nhiều dịch vụ hoặc trải nghiệm người dùng, bổ sung E2E test đại diện.
- Nếu chỉ xuất hiện trong môi trường triển khai, bổ sung smoke test hoặc kiểm tra trên môi trường gần production.
- Nếu liên quan đến tải hoặc phục hồi, thiết kế kiểm thử phi chức năng chuyên biệt.

### Bước 6: Xác định điều kiện môi trường và dữ liệu

Ghi phiên bản phụ thuộc, cấu hình, dữ liệu, tài khoản, quyền và cách tái lập. Nếu không thể dùng tích hợp thật, hãy ghi rõ phần mô phỏng và giới hạn của bằng chứng.

### Bước 7: Ghi quyết định và rủi ro còn lại

Nêu rõ kiểm thử nào được thêm, mục tiêu nào được bao phủ, ai chịu trách nhiệm, khi nào chạy và phần nào vẫn chưa được xác minh. Nếu chấp nhận khoảng trống, quyết định cần đúng thẩm quyền và có điều kiện xem xét lại.

## 6. Ví dụ: bằng chứng cho luồng thanh toán

Giả sử hệ thống có checkout API, cơ sở dữ liệu đơn hàng, payment service, nhà cung cấp thanh toán và callback handler. Bộ kiểm thử hiện tại có unit test cho tính tiền, contract test cho request thanh toán và một số integration test dùng mock.

Nhóm có thể rà soát như sau:

| Kết luận cần chứng minh | Bằng chứng hiện có | Khoảng trống | Bằng chứng bổ sung |
|---|---|---|---|
| Tổng tiền được tính đúng | Unit test với giá trị biên. | Không có khoảng trống đáng kể ở logic tính toán. | Duy trì unit test; không cần lặp toàn bộ ở E2E. |
| Request thanh toán có schema đúng | Contract test. | Chưa chứng minh cấu hình và credential cho sandbox hoạt động. | Integration test gọi sandbox với tài khoản thử nghiệm. |
| Đơn hàng và giao dịch được lưu nhất quán | Unit test dùng repository mock. | Chưa kiểm tra transaction, constraint và mapping thật. | Integration test với database tương thích. |
| Callback được xác minh và xử lý | Unit test cho logic chữ ký và trạng thái. | Chưa kiểm tra endpoint, routing và payload qua HTTP thực. | Integration test gửi callback đến handler đang chạy. |
| Callback trùng không tạo giao dịch lặp | Unit test cho idempotency. | Chưa xác minh tính duy nhất và trạng thái trong kho dữ liệu. | Integration test gửi callback lặp và đọc lại dữ liệu. |
| Người dùng hoàn tất thanh toán | Chưa có. | Chưa có bằng chứng xuyên suốt từ giao diện đến kết quả cuối. | Một E2E test trên staging hoặc môi trường tương đương. |
| Hành vi khi nhà cung cấp timeout | Stub mô phỏng timeout. | Chưa xác minh timeout, retry và cấu hình thực tế. | Integration test có kiểm soát hoặc môi trường sandbox hỗ trợ lỗi; kiểm tra phục hồi theo rủi ro. |

Từ ma trận này, nhóm không cần chạy lại toàn bộ biến thể tính tiền ở E2E. Phần còn thiếu chủ yếu nằm ở database, callback thật, cấu hình sandbox và hành trình người dùng.

Một kế hoạch kiểm thử có thể gồm:

1. Giữ unit test cho quy tắc tính tiền, xác thực và idempotency.
2. Chạy integration test với database thật để xác minh transaction và dữ liệu.
3. Chạy integration test với sandbox để xác minh request, callback và xử lý lỗi.
4. Chạy một E2E test thanh toán thành công từ giao diện đến trạng thái đơn.
5. Chạy thêm một E2E hoặc integration scenario cho lỗi có hậu quả cao, chẳng hạn thanh toán thất bại hoặc callback đến trễ.
6. Ghi rõ những điều sandbox không thể mô phỏng và theo dõi rủi ro còn lại khi triển khai.

## 7. Đánh giá chất lượng bằng chứng tích hợp và E2E

Một test được chạy thành công chưa chắc cung cấp bằng chứng mạnh. Cần đánh giá chất lượng của điều kiện kiểm thử và cách quan sát kết quả.

### 7.1. Môi trường có đại diện không?

Kiểm tra phiên bản dịch vụ, schema, cấu hình, mạng, quyền, dữ liệu và cách triển khai. Ghi khác biệt có thể ảnh hưởng kết quả. Môi trường thử nghiệm không cần giống production ở mọi chi tiết, nhưng phải tương thích với rủi ro đang kiểm tra.

### 7.2. Test có quan sát đúng kết quả không?

Một E2E test chỉ kiểm tra trang web hiển thị thông báo “thành công” có thể bỏ sót việc dữ liệu chưa được lưu. Với luồng quan trọng, nên xác nhận kết quả ở một ranh giới có ý nghĩa, chẳng hạn trạng thái đơn qua API công khai hoặc một xác nhận nghiệp vụ độc lập.

Tránh phụ thuộc vào database nội bộ trong E2E nếu mục tiêu là hành vi người dùng và việc truy cập đó làm test gắn chặt với triển khai. Có thể dùng integration test riêng để xác minh persistence.

### 7.3. Test có ổn định và tái lập được không?

Dữ liệu dùng chung, thời gian chờ cố định, thứ tự chạy và phụ thuộc không ổn định có thể tạo flaky test. Hãy dùng dữ liệu riêng cho mỗi lần chạy, đồng bộ theo điều kiện trạng thái thay vì sleep tùy ý, dọn dẹp sau test và ghi log đủ để điều tra.

### 7.4. Test có tạo ra tín hiệu chẩn đoán hữu ích không?

Khi thất bại, cần biết thành phần, request hoặc bước nào gây lỗi. Có thể lưu trace ID, log đã lọc thông tin nhạy cảm, response code và dấu mốc thời gian. Không đưa credential, token hoặc dữ liệu cá nhân vào log kiểm thử.

### 7.5. Kết quả có gắn với đúng phiên bản không?

Ghi commit, build, image digest, phiên bản dịch vụ và cấu hình quan trọng. Nếu artifact hoặc cấu hình thay đổi sau khi kiểm thử, hãy đánh giá lại bằng chứng nào cần chạy lại.

## 8. Quản lý giới hạn khi không thể tích hợp thật

Đôi khi nhóm không thể gọi dịch vụ production hoặc sandbox không sẵn sàng. Khi đó, có thể dùng test double hoặc mô phỏng có kiểm soát, nhưng cần ghi rõ giới hạn.

Một báo cáo tốt nên phân biệt:

- Đã xác minh bằng phụ thuộc thật.
- Đã xác minh bằng sandbox hoặc môi trường tương thích.
- Đã xác minh bằng mock, stub hoặc fake.
- Chưa xác minh do thiếu môi trường, quyền hoặc dữ liệu.

Nếu phải dùng mô phỏng, hãy xác nhận rằng nó phản ánh các đặc tính cần thiết như schema, lỗi, độ trễ hoặc retry. Không nên suy rộng kết quả mock thành bằng chứng rằng nhà cung cấp thật hoạt động đúng.

Với khoảng trống quan trọng, cần xác định phương án tiếp theo: chờ môi trường, dùng kiểm thử thay thế có giới hạn, thực hiện kiểm tra sau triển khai có kiểm soát hoặc xin quyết định chấp nhận rủi ro. Quyết định phải ghi người phụ trách, thời hạn và điều kiện kích hoạt.

## 9. Mẫu ghi nhận khoảng trống bằng chứng

Có thể dùng mẫu sau để review một luồng hoặc một bản phát hành:

~~~text
Tên luồng / tính năng:
Phiên bản / artifact:
Mục tiêu và rủi ro cần xác minh:

Các thành phần và ranh giới:
- Producer / caller:
- Consumer / callee:
- Database / broker / provider:
- Cấu hình và quyền liên quan:

Bằng chứng hiện có:
- Unit test:
- Contract test:
- Integration test:
- End-to-end test:
- Kiểm tra vận hành:

Giả định hoặc phần đang mô phỏng:
Khoảng trống bằng chứng:
Hậu quả nếu khoảng trống không được kiểm tra:

Bằng chứng bổ sung được chọn:
- Tầng kiểm thử:
- Phụ thuộc thật hoặc môi trường:
- Dữ liệu và cấu hình:
- Kết quả mong đợi:

Người phụ trách:
Thời hạn:
Rủi ro còn lại:
Quyết định / người chấp nhận (nếu có):
~~~

## 10. Những sai lầm thường gặp

- **Cho rằng contract test đã chứng minh tích hợp thật:** contract test xác minh thỏa thuận, không chứng minh cấu hình, mạng và dịch vụ đang hoạt động.
- **Cho rằng mock thành công nghĩa là nhà cung cấp thật thành công:** mock chỉ cung cấp phản hồi được lập trình trước.
- **Dùng E2E cho mọi trường hợp:** làm pipeline chậm, khó chẩn đoán và tăng flaky test.
- **Chỉ kiểm tra luồng thành công:** bỏ sót timeout, retry, callback trùng và phục hồi.
- **Không kiểm tra persistence thật:** kết quả trong bộ nhớ không chứng minh transaction và dữ liệu được lưu đúng.
- **Dùng môi trường không đại diện mà không ghi giới hạn:** người đọc có thể suy rộng kết luận vượt quá bằng chứng.
- **Không gắn kết quả với phiên bản:** khó biết artifact đang triển khai có đúng artifact đã kiểm tra hay không.
- **Thêm test nhưng không xác định khoảng trống:** tăng chi phí mà không làm rõ rủi ro được giảm.
- **Không quản lý phần chưa xác minh:** khoảng trống có thể bị quên khi chuyển sang quyết định phát hành.

## 11. Danh sách rà soát trước khi kết luận đủ bằng chứng

- [ ] Các kết luận cần chứng minh được mô tả thành hành vi cụ thể.
- [ ] Mỗi kết luận được liên kết với test và tầng kiểm thử hiện có.
- [ ] Các phụ thuộc đang được mock hoặc mô phỏng được nhận diện.
- [ ] Khoảng trống về giao tiếp, persistence, cấu hình, bất đồng bộ và hành trình người dùng đã được xem xét.
- [ ] Integration test được chọn cho ranh giới cần xác minh với phụ thuộc thật.
- [ ] E2E test được giới hạn ở hành trình quan trọng và có điểm bắt đầu/kết thúc rõ ràng.
- [ ] Trường hợp lỗi có hậu quả lớn được cân nhắc cùng với luồng thành công.
- [ ] Môi trường, phiên bản, dữ liệu và cấu hình có thể tái lập được ghi rõ.
- [ ] Kết quả có thể quan sát, chẩn đoán và liên kết với artifact.
- [ ] Giới hạn của sandbox, mock hoặc môi trường được nêu rõ.
- [ ] Khoảng trống còn lại có người phụ trách, thời hạn và quyết định phù hợp.

## Kết luận

Để xác định có cần tích hợp thật hoặc kiểm thử đầu cuối, nhóm cần bắt đầu từ kết luận cần chứng minh và bằng chứng đang có. Unit test xác minh logic; contract test xác minh thỏa thuận; integration test xác minh các ranh giới thực; E2E test xác minh hành trình quan trọng xuyên suốt. Bổ sung kiểm thử ở nơi còn khoảng trống có ý nghĩa, ghi rõ giới hạn môi trường và liên kết kết quả với đúng phiên bản giúp nhóm có cơ sở đáng tin cậy cho quyết định phát hành mà không tạo thêm các kiểm tra trùng lặp.
