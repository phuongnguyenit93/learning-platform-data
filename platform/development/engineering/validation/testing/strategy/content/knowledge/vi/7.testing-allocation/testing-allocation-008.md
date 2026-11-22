# Giảm kiểm tra trùng mục tiêu giữa nhiều tầng

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), phân bổ kiểm thử là quyết định xem mỗi mục tiêu xác minh nên được kiểm tra ở tầng nào và bằng loại bằng chứng nào. Một mục tiêu có thể xuất hiện trong unit test, component test, integration test và end-to-end test. Việc lặp lại đôi khi cần thiết để kiểm tra các ranh giới khác nhau, nhưng nếu nhiều tầng chỉ xác nhận cùng một quy tắc theo cùng một cách thì bộ kiểm thử sẽ tốn thời gian, khó bảo trì và làm chậm phản hồi mà không tăng tương ứng mức độ tin cậy.

Giảm kiểm tra trùng mục tiêu không có nghĩa là giảm tùy tiện số lượng kiểm thử. Mục tiêu là giao cho mỗi tầng một vai trò rõ ràng: tầng phù hợp nhất xác minh quy tắc chi tiết; các tầng cao hơn xác minh cách các thành phần phối hợp và những luồng quan trọng có hoạt động trong môi trường gần thực tế hay không. Nhờ vậy, nhóm vẫn giữ được bằng chứng cần thiết nhưng giảm các lần xác nhận giống nhau.

## 1. Hiểu thế nào là kiểm tra trùng mục tiêu?

Một mục tiêu kiểm thử là hành vi, quy tắc hoặc thuộc tính mà nhóm muốn xác minh. Ví dụ: “mã giảm giá hết hạn không được áp dụng vào tổng tiền đơn hàng” là một mục tiêu cụ thể.

Kiểm tra trùng mục tiêu xảy ra khi nhiều ca kiểm thử ở các tầng khác nhau cùng xác nhận một kết luận giống nhau, với dữ liệu và điều kiện tương đương, trong khi tầng bổ sung không kiểm tra thêm ranh giới hoặc rủi ro có ý nghĩa.

Ví dụ, cả unit test của hàm tính giảm giá, integration test của API tạo đơn và end-to-end test trên giao diện đều chỉ kiểm tra rằng mã giảm giá hết hạn bị từ chối. Nếu integration test và end-to-end test không xác minh thêm việc dữ liệu được lưu đúng, phản hồi API được ánh xạ đúng hoặc giao diện hiển thị lỗi phù hợp, chúng có thể chỉ lặp lại quy tắc đã được unit test kiểm tra trực tiếp.

Ngược lại, các ca kiểm thử có cùng một mục tiêu nghiệp vụ nhưng kiểm tra những ranh giới khác nhau có thể bổ sung bằng chứng cho nhau. Unit test có thể xác minh quy tắc tính tiền; integration test xác minh giao dịch và lưu trạng thái; end-to-end test xác minh người dùng nhìn thấy tổng tiền chính xác sau khi hoàn tất quy trình. Chúng không phải bản sao nếu mỗi ca có một câu hỏi riêng.

### 1.1. Phân biệt lặp lại có ích và lặp lại không cần thiết

| Loại kiểm tra | Đặc điểm | Cách xử lý |
|---|---|---|
| Trùng hoàn toàn | Cùng quy tắc, cùng điều kiện, cùng kết luận; tầng cao hơn không thêm bằng chứng về ranh giới. | Chọn một tầng phù hợp làm nơi xác minh chính; xem xét bỏ hoặc thu hẹp bản lặp. |
| Trùng một phần | Có cùng một số assertion nhưng mỗi tầng còn xác minh hành vi riêng. | Giữ phần kiểm tra ranh giới có giá trị; loại assertion lặp nếu không cần thiết. |
| Bổ sung theo tầng | Cùng luồng nghiệp vụ nhưng mỗi tầng xác minh một khía cạnh khác nhau. | Giữ các ca vì chúng cung cấp bằng chứng khác nhau. |
| Kiểm tra hồi quy có chủ đích | Một quy tắc quan trọng được xác minh ở nhiều ranh giới để giảm nguy cơ lỗi tích hợp hoặc cấu hình. | Giữ có chọn lọc, ghi rõ rủi ro mà mỗi tầng bổ sung đang bao phủ. |

Không nên quyết định chỉ dựa vào tên test hoặc câu mô tả. Hai ca có tên khác nhau vẫn có thể kiểm tra cùng một assertion; hai ca có tên gần giống nhau lại có thể kiểm tra các ranh giới hoàn toàn khác nhau. Cần đọc điều kiện, dữ liệu, kết quả mong đợi và các tương tác mà ca kiểm thử thực sự bao phủ.

### 1.2. Vì sao kiểm tra trùng mục tiêu gây tốn kém?

Kiểm tra lặp không cần thiết có thể gây ra một số hệ quả:

- **Phản hồi chậm:** end-to-end test thường khởi tạo nhiều dịch vụ, dữ liệu và giao diện nên có thể mất nhiều thời gian hơn unit test.
- **Bảo trì tăng:** một thay đổi nghiệp vụ buộc nhóm cập nhật nhiều ca giống nhau ở nhiều tầng.
- **Lỗi khó định vị:** cùng một quy tắc thất bại ở nhiều tầng có thể tạo nhiều lỗi báo cáo cho một nguyên nhân.
- **Flaky test tăng:** ca kiểm thử ở tầng cao chịu ảnh hưởng của mạng, thời gian, dữ liệu dùng chung và trạng thái môi trường.
- **Tín hiệu bị nhiễu:** số lượng ca lớn có thể tạo cảm giác bao phủ rộng dù nhiều ca chỉ xác nhận một hành vi.
- **Chi phí CI tăng:** pipeline sử dụng thêm tài nguyên và kéo dài thời gian chờ của nhóm phát triển.

Một bộ kiểm thử nhỏ hơn không mặc nhiên tốt hơn. Nếu bỏ nhầm kiểm tra ở tầng tích hợp, nhóm có thể mất khả năng phát hiện lỗi giao tiếp hoặc cấu hình. Vì vậy, mỗi lần loại bỏ hoặc thay đổi một ca cần dựa trên mục tiêu và bằng chứng mà ca đó cung cấp.

## 2. Vai trò riêng của từng tầng kiểm thử

Để phân bổ mục tiêu, nhóm cần thống nhất câu hỏi mà mỗi tầng trả lời. Tên tầng có thể khác nhau giữa các dự án, nhưng nguyên tắc là chọn nơi có thể kiểm tra hành vi với chi phí và độ phức tạp phù hợp.

| Tầng | Câu hỏi chính | Mục tiêu phù hợp |
|---|---|---|
| Unit test | Quy tắc hoặc đơn vị logic có xử lý đúng đầu vào và trạng thái không? | Phép tính, điều kiện, chuyển trạng thái, kiểm tra giá trị biên và xử lý lỗi cục bộ. |
| Component test | Một thành phần có hoạt động đúng với các phụ thuộc được kiểm soát không? | Logic nội bộ của service, adapter, repository hoặc component với test double. |
| Integration test | Các thành phần hoặc hệ thống có trao đổi và phối hợp đúng không? | Truy vấn cơ sở dữ liệu, giao dịch, serialization, message broker, cấu hình và giao tiếp thực tế giữa các thành phần. |
| Contract test | Hai phía của một giao tiếp có tuân thủ thỏa thuận không? | Schema, trường bắt buộc, kiểu dữ liệu, mã phản hồi, định dạng sự kiện và tương thích hợp đồng. |
| End-to-end test | Một luồng quan trọng của người dùng có hoạt động xuyên suốt trong môi trường gần thực tế không? | Đăng nhập, đặt hàng, thanh toán, kích hoạt tài khoản và các hành trình có rủi ro cao. |
| Kiểm thử phi chức năng | Hệ thống có đáp ứng thuộc tính chất lượng trong điều kiện đã định không? | Hiệu năng, tải, bảo mật, khả năng truy cập, phục hồi và độ tin cậy. |

### 2.1. Ưu tiên kiểm tra quy tắc ở tầng gần quy tắc nhất

Quy tắc thuần logic thường dễ kiểm tra ở unit test. Tầng này chạy nhanh, ít phụ thuộc môi trường và giúp chỉ ra nguyên nhân lỗi cụ thể.

Ví dụ, cách tính thuế theo vùng có thể được kiểm tra với các giá trị biên trong unit test. Không cần chạy toàn bộ trình duyệt và nhiều dịch vụ cho từng giá trị đầu vào nếu mục tiêu chỉ là xác minh công thức.

### 2.2. Dùng tầng tích hợp để xác minh ranh giới

Unit test có thể xác minh một hàm tạo ra kết quả đúng nhưng không chứng minh dữ liệu được ghi đúng vào cơ sở dữ liệu hoặc thông điệp được gửi đúng schema. Integration test cần tập trung vào các tương tác đó.

Ví dụ, khi lưu đơn hàng, integration test có thể xác minh transaction, khóa ngoại, rollback và trạng thái được đọc lại. Nó không cần lặp lại toàn bộ tổ hợp giá trị biên của công thức tính tiền nếu các trường hợp đó đã được kiểm tra ở unit test.

### 2.3. Giữ end-to-end cho hành trình có giá trị cao

End-to-end test nên tập trung vào một số hành trình quan trọng mà lỗi ở giao diện, cấu hình, xác thực hoặc kết nối giữa các dịch vụ có thể gây hậu quả lớn.

Một ca end-to-end có thể xác minh người dùng đăng nhập, tạo đơn, thanh toán trên sandbox và nhìn thấy trạng thái đơn chính xác. Ca này không cần lặp lại hàng chục biến thể giá trị biên của hàm tính thuế; nó nên dùng một kịch bản đại diện để xác minh luồng xuyên suốt.

### 2.4. Chọn contract test khi ranh giới giao tiếp là trọng tâm

Nếu mục tiêu là bảo đảm producer và consumer hiểu cùng một schema, contract test có thể cung cấp phản hồi nhanh hơn và rõ hơn so với việc chạy toàn bộ luồng đầu cuối.

Ví dụ, contract test xác minh payment service phát sự kiện với các trường bắt buộc và order service có thể tiêu thụ định dạng đó. End-to-end test vẫn có thể giữ một ca đại diện để xác nhận sự kiện thực sự dẫn đến trạng thái đơn hàng mà người dùng nhìn thấy.

## 3. Quy tắc phân bổ mục tiêu giữa các tầng

Nhóm có thể dùng các nguyên tắc sau để quyết định nơi đặt kiểm tra chính và khi nào cần xác minh bổ sung.

### 3.1. Mỗi mục tiêu cần có một nơi xác minh chính

Với mỗi quy tắc hoặc assertion, hãy chỉ định tầng chịu trách nhiệm xác minh chi tiết nhất. Tầng đó là nơi chứa phần lớn biến thể dữ liệu, giá trị biên và trường hợp lỗi liên quan.

Ví dụ:

- Quy tắc làm tròn tiền: unit test của module tính tiền.
- Quy tắc phân quyền theo chủ sở hữu đơn hàng: unit test cho policy và integration test ở ranh giới API.
- Cấu trúc thông điệp thanh toán: contract test.
- Transaction ghi đơn và payment: integration test với cơ sở dữ liệu.
- Người dùng hoàn thành thanh toán và thấy trạng thái xác nhận: một end-to-end test đại diện.

Một nơi xác minh chính giúp tránh phải sửa nhiều bộ test khi quy tắc thay đổi. Tuy nhiên, điều này không cấm các tầng khác kiểm tra tác động của quy tắc tại ranh giới của chúng.

### 3.2. Chỉ lặp lại assertion khi có lý do về ranh giới hoặc rủi ro

Trước khi giữ cùng một assertion ở nhiều tầng, hãy trả lời:

1. Tầng bổ sung có kiểm tra một tương tác hoặc ranh giới khác không?
2. Nếu bỏ assertion này, có rủi ro thực tế nào không còn được phát hiện?
3. Tầng hiện tại có thể phát hiện lỗi mà tầng thấp hơn không thể phát hiện không?
4. Chi phí chạy và bảo trì có tương xứng với giá trị bằng chứng không?

Nếu không có câu trả lời cụ thể, nhiều khả năng assertion đang bị lặp mà không tạo thêm giá trị.

### 3.3. Tách mục tiêu nghiệp vụ khỏi chi tiết triển khai

Một ca kiểm thử tốt mô tả hành vi cần xác minh thay vì phụ thuộc quá sâu vào cấu trúc nội bộ. Khi một quy tắc được kiểm tra ở unit test và end-to-end test, hãy phân biệt:

- Unit test xác minh thuật toán hoặc quy tắc nội bộ.
- End-to-end test xác minh hệ thống thực thi quy tắc đó đúng qua luồng người dùng và các ranh giới liên quan.

Không cần sao chép cùng bộ dữ liệu chi tiết sang mọi tầng. Hãy dùng dữ liệu đại diện ở tầng cao và dành bộ dữ liệu phong phú cho tầng phù hợp nhất.

### 3.4. Ưu tiên phát hiện lỗi sớm, nhưng không bỏ qua lỗi tích hợp

Nếu một lỗi có thể được phát hiện nhanh bằng unit test, hãy đặt kiểm tra chi tiết ở đó. Nhưng lỗi do serialization, cấu hình, transaction, quyền ở gateway hoặc sự khác biệt giữa dịch vụ thường cần kiểm tra ở tầng tích hợp.

Không nên đẩy mọi kiểm thử xuống unit test chỉ vì nó nhanh. Mục tiêu là chọn tầng có khả năng xác minh đáng tin cậy nhất với chi phí hợp lý.

### 3.5. Giữ kiểm tra nhiều tầng cho rủi ro có hậu quả lớn

Một số mục tiêu cần bằng chứng ở nhiều ranh giới, ví dụ quyền truy cập, tính toàn vẹn dữ liệu, thanh toán hoặc xử lý giao dịch. Khi giữ kiểm tra nhiều tầng, cần ghi rõ mỗi ca bổ sung xác minh điều gì.

Ví dụ, quyền truy cập đơn hàng có thể được kiểm tra trong unit test của policy, integration test của API gateway và một end-to-end test đại diện. Ba ca này có thể cần thiết vì chúng xác minh logic policy, thực thi ở ranh giới HTTP và hành vi thực tế của người dùng.

## 4. Quy trình phát hiện và xử lý kiểm tra trùng mục tiêu

Có thể thực hiện theo các bước sau khi tạo bộ kiểm thử mới hoặc rà soát bộ kiểm thử hiện tại.

### Bước 1: Lập danh sách mục tiêu cần xác minh

Tách yêu cầu thành các hành vi hoặc thuộc tính nhỏ, có thể quan sát. Tránh dùng tên tính năng quá rộng như “thanh toán hoạt động đúng”.

Ví dụ với thanh toán:

- Tổng tiền được tính chính xác.
- Mã giảm giá hết hạn bị từ chối.
- Người dùng không thể thanh toán đơn của người khác.
- Callback trùng không tạo giao dịch lặp.
- Trạng thái đơn được cập nhật sau khi thanh toán thành công.
- Người dùng nhìn thấy kết quả thanh toán cuối cùng.

### Bước 2: Gắn từng mục tiêu với các ca kiểm thử hiện có

Ghi ID hoặc tên ca, tầng kiểm thử, điều kiện, dữ liệu, assertion và phụ thuộc. Một ca có thể kiểm tra nhiều mục tiêu; một mục tiêu cũng có thể xuất hiện ở nhiều ca.

### Bước 3: So sánh giá trị bằng chứng

Không chỉ so sánh tên hoặc kết quả đạt/thất bại. Hãy xác định mỗi ca có kiểm tra thêm điều gì: logic, giao tiếp, lưu trữ, cấu hình, phân quyền hay hiển thị.

### Bước 4: Chọn nơi xác minh chính

Chọn tầng có thể kiểm tra mục tiêu trực tiếp, ổn định, nhanh và dễ chẩn đoán. Chuyển các biến thể chi tiết đến tầng này.

### Bước 5: Giữ các kiểm tra bổ sung có lý do

Với tầng cao hơn, giữ lại các assertion liên quan đến ranh giới, tích hợp hoặc hành trình người dùng. Thu hẹp các ca chỉ lặp quy tắc đã được xác minh ở tầng thấp hơn.

### Bước 6: Đánh giá rủi ro trước khi loại bỏ

Xem xét lịch sử lỗi, độ quan trọng của luồng, khả năng phát hiện lỗi ở tầng khác và mức độ đại diện của môi trường. Nếu chưa đủ bằng chứng, hãy giữ ca cho đến khi có kiểm tra thay thế đáng tin cậy.

### Bước 7: Cập nhật tài liệu và theo dõi kết quả

Ghi lại nơi xác minh chính, lý do giữ hoặc bỏ assertion lặp, ca thay thế và kết quả sau thay đổi. Theo dõi thời gian pipeline, độ ổn định và loại lỗi phát hiện được để xác nhận quyết định có hiệu quả.

## 5. Ví dụ: phân bổ kiểm thử cho luồng đặt hàng và thanh toán

Giả sử hệ thống có các thành phần tính giá, API đơn hàng, cơ sở dữ liệu, dịch vụ thanh toán và giao diện web. Ban đầu, nhiều tầng đều kiểm tra cùng các trường hợp mã giảm giá, thuế và tổng tiền. Bộ kiểm thử chạy lâu, nhưng phần lớn thời gian được dùng để xác nhận lại quy tắc tính toán.

Có thể phân bổ lại như sau:

| Mục tiêu | Tầng xác minh chính | Kiểm tra bổ sung ở tầng khác |
|---|---|---|
| Tính thuế, giảm giá và làm tròn | Unit test của PriceCalculator | Một ca end-to-end đại diện xác nhận tổng tiền hiển thị đúng. |
| Từ chối mã giảm giá hết hạn | Unit test của discount policy | Integration test xác minh API trả lỗi nghiệp vụ đúng; không lặp toàn bộ bộ dữ liệu giá trị biên. |
| Chặn người dùng truy cập đơn hàng của người khác | Unit test của authorization policy | Integration test xác minh HTTP 403; end-to-end test có thể giữ một ca đại diện cho hành vi người dùng. |
| Lưu đơn hàng và payment nhất quán | Integration test với cơ sở dữ liệu | End-to-end test xác minh trạng thái cuối cùng qua luồng thanh toán. |
| Định dạng callback từ nhà cung cấp | Contract test | Integration test xác minh handler xử lý thông điệp; end-to-end test dùng một callback đại diện. |
| Callback lặp không tạo giao dịch lặp | Unit test cho idempotency logic và integration test cho trạng thái lưu trữ | End-to-end chỉ cần một kịch bản retry đại diện nếu đây là rủi ro trọng yếu. |
| Người dùng hoàn tất thanh toán và thấy xác nhận | End-to-end test | Không cần lặp toàn bộ quy tắc tính tiền đã được kiểm tra chi tiết ở unit test. |

Sau khi phân bổ, nhóm có thể giữ:

- Nhiều unit test nhanh cho công thức tính giá và các giá trị biên.
- Một số integration test tập trung vào transaction, quyền truy cập, callback và trạng thái dữ liệu.
- Contract test cho giao tiếp với nhà cung cấp.
- Một số ít end-to-end test bao phủ hành trình quan trọng từ giao diện đến kết quả cuối.

Cách phân bổ này giảm các assertion lặp trong end-to-end test nhưng vẫn giữ bằng chứng về giao tiếp và hành vi người dùng. Nếu một lỗi thực tế từng xuất hiện do cấu hình hoặc mapping ở tầng API, hãy giữ kiểm tra ở đúng ranh giới đó thay vì cho rằng unit test đã đủ.

## 6. Ma trận phân bổ mục tiêu

Ma trận giúp nhìn thấy mục tiêu nào đang được xác minh ở đâu và phát hiện các vùng bị lặp hoặc chưa có bằng chứng.

| Mục tiêu | Unit | Component | Integration | Contract | End-to-end |
|---|---|---|---|---|---|
| Quy tắc tính giá | Chính | Có thể có | Chỉ kiểm tra mapping cần thiết | — | Một ca đại diện |
| Giá trị biên của mã giảm giá | Chính | — | Không lặp toàn bộ | — | — |
| Schema API | — | — | Có thể kiểm tra mapping | Chính | Một luồng smoke nếu cần |
| Transaction và persistence | — | Có thể có | Chính | — | Một ca xác nhận trạng thái cuối |
| Phân quyền ở policy | Chính | Có thể có | Kiểm tra thực thi tại API | — | Luồng người dùng đại diện |
| Giao tiếp producer/consumer | — | — | Kiểm tra tích hợp thực tế | Chính cho hợp đồng | Một luồng xuyên suốt |
| Hành trình thanh toán của người dùng | — | — | Kiểm tra các ranh giới quan trọng | Hợp đồng liên quan | Chính |

Ký hiệu “Chính” thể hiện nơi xác minh chi tiết; “Có thể có” hoặc “Một ca đại diện” chỉ nên dùng khi có giá trị bổ sung. Dấu gạch ngang nghĩa là thường không cần kiểm tra mục tiêu đó ở tầng này, nhưng có thể có ngoại lệ dựa trên rủi ro.

Ma trận không phải quy tắc cứng. Ví dụ, một ứng dụng desktop có thể cần kiểm tra giao diện và tương tác thiết bị ở mức component; một hệ thống phân tán có thể cần nhiều contract test hơn. Hãy điều chỉnh theo kiến trúc và rủi ro thực tế.

## 7. Cách quyết định giữ, thu hẹp hoặc loại bỏ một ca kiểm thử

Trước khi thay đổi bộ kiểm thử, đánh giá từng ca theo giá trị bằng chứng.

| Quyết định | Khi phù hợp | Việc cần làm |
|---|---|---|
| Giữ nguyên | Ca xác minh một ranh giới quan trọng hoặc là bằng chứng duy nhất cho rủi ro cụ thể. | Ghi rõ mục tiêu và lý do cần duy trì. |
| Thu hẹp | Ca có một số assertion hữu ích nhưng cũng lặp lại quy tắc đã được kiểm tra ở tầng khác. | Giữ assertion về ranh giới; chuyển biến thể chi tiết về tầng chính. |
| Chuyển tầng | Ca đang kiểm tra logic thuần ở tầng cao, gây chậm và khó chẩn đoán. | Tạo kiểm tra tương đương ở tầng phù hợp, xác nhận độ bao phủ rồi mới loại phần cũ. |
| Gộp | Nhiều ca cùng xác minh một mục tiêu trong điều kiện tương đương và có thể hợp nhất mà vẫn dễ chẩn đoán. | Gộp có chọn lọc; tránh tạo một ca lớn chứa quá nhiều mục tiêu không liên quan. |
| Loại bỏ | Ca không còn liên quan, không có giá trị bằng chứng riêng hoặc đã được thay thế bằng kiểm tra đáng tin cậy. | Ghi lý do và bảo đảm không để lại khoảng trống rủi ro. |

Không xóa ca chỉ vì nó chậm hoặc trùng tên. Trước hết, xác định chính xác assertion nào lặp và phần nào đang cung cấp bằng chứng duy nhất. Nếu một ca end-to-end mất nhiều phút nhưng là ca duy nhất phát hiện sai cấu hình routing, cần giữ nó hoặc thay bằng một kiểm tra khác có thể xác minh cùng ranh giới.

## 8. Đo hiệu quả sau khi giảm trùng lặp

Sau khi điều chỉnh, nhóm nên theo dõi cả chi phí lẫn chất lượng bằng chứng. Không nên chỉ nhìn số lượng test giảm.

Các chỉ số hữu ích:

- **Thời gian phản hồi pipeline:** thời gian từ khi thay đổi mã đến khi có kết quả kiểm thử.
- **Thời gian chạy theo tầng:** unit, integration, contract và end-to-end để tìm tầng gây chậm.
- **Tỷ lệ flaky:** số lần chạy không ổn định trên tổng số lần chạy của các ca.
- **Khả năng định vị lỗi:** mức độ nhanh chóng xác định tầng hoặc thành phần gây lỗi.
- **Lỗi lọt qua tầng thấp hơn:** lỗi chỉ được phát hiện ở tầng tích hợp hoặc production, dùng để đánh giá liệu phân bổ hiện tại có bỏ sót ranh giới quan trọng không.
- **Chi phí bảo trì:** số ca phải sửa khi một quy tắc hoặc giao diện thay đổi.
- **Mức bao phủ mục tiêu:** tỷ lệ mục tiêu quan trọng có ít nhất một ca xác minh phù hợp và có chủ sở hữu.

Không nên tối ưu một chỉ số riêng lẻ. Ví dụ, giảm mạnh thời gian pipeline nhưng đồng thời tăng lỗi tích hợp lọt qua có thể cho thấy nhóm đã loại bỏ kiểm tra cần thiết. Ngược lại, giữ quá nhiều end-to-end test chỉ để tăng số ca đạt không đồng nghĩa với bằng chứng tốt hơn.

## 9. Duy trì phân bổ khi yêu cầu và kiến trúc thay đổi

Phân bổ kiểm thử cần được xem xét lại khi:

- Quy tắc nghiệp vụ hoặc tiêu chí chấp nhận thay đổi.
- Một service được tách, gộp hoặc chuyển sang giao tiếp bất đồng bộ.
- Schema, API hoặc hợp đồng thông điệp thay đổi.
- Feature flag hoặc cấu hình tạo thêm nhánh hành vi.
- Một lỗi production cho thấy tầng hiện tại không phát hiện được vấn đề.
- Một ca kiểm thử trở nên flaky hoặc chi phí bảo trì tăng đáng kể.

Khi có thay đổi, hãy cập nhật ma trận mục tiêu, kiểm tra xem tầng xác minh chính còn phù hợp không và xác định các kiểm tra bổ sung cần thiết. Một lỗi lọt qua có thể là bằng chứng rằng mục tiêu cần được kiểm tra ở ranh giới khác; không nhất thiết phải nhân bản toàn bộ ca kiểm thử ở mọi tầng.

Nên lưu liên kết giữa yêu cầu, mục tiêu, ca kiểm thử và lỗi. Điều đó giúp nhóm hiểu vì sao một ca tồn tại và tránh loại bỏ nó trong lần tối ưu sau.

## 10. Những sai lầm thường gặp

- **Đồng nhất cùng nghiệp vụ với cùng mục tiêu kiểm thử:** một luồng nghiệp vụ có thể chứa nhiều ranh giới và thuộc tính khác nhau. Hãy mô tả assertion cụ thể.
- **Chỉ dựa vào tên test để phát hiện trùng lặp:** cần so sánh dữ liệu, điều kiện, kết quả mong đợi và tương tác thực tế.
- **Đẩy mọi kiểm tra xuống unit test:** unit test không chứng minh tích hợp, cấu hình, giao dịch hoặc hành vi người dùng.
- **Giữ mọi assertion ở end-to-end:** điều này làm bộ test chậm và dễ lỗi mà không nhất thiết tăng bằng chứng.
- **Xóa ca trước khi có kiểm tra thay thế:** có thể tạo khoảng trống ở ranh giới quan trọng.
- **Gộp quá nhiều mục tiêu vào một ca:** khi thất bại sẽ khó biết hành vi nào sai và khó bảo trì.
- **Không ghi lý do giữ kiểm tra nhiều tầng:** nhóm sau này có thể xóa nhầm ca cần thiết.
- **Chỉ đo thời gian chạy:** cần theo dõi cả lỗi lọt qua, độ ổn định và khả năng định vị nguyên nhân.

## 11. Danh sách rà soát trước khi chốt phân bổ

- [ ] Mỗi mục tiêu kiểm thử được mô tả thành hành vi hoặc assertion cụ thể.
- [ ] Mỗi mục tiêu quan trọng có tầng xác minh chính.
- [ ] Các ca ở tầng cao tập trung vào ranh giới và luồng có giá trị.
- [ ] Assertion lặp được nhận diện bằng điều kiện và kết quả thực tế, không chỉ tên test.
- [ ] Kiểm tra nhiều tầng có lý do gắn với rủi ro hoặc ranh giới riêng.
- [ ] Ca bị thu hẹp, chuyển tầng hoặc loại bỏ có bằng chứng thay thế phù hợp.
- [ ] Không bỏ sót tích hợp, cấu hình, persistence hoặc hành vi người dùng.
- [ ] Ma trận mục tiêu và ca kiểm thử được cập nhật.
- [ ] Thời gian pipeline, flaky test, lỗi lọt qua và chi phí bảo trì được theo dõi.
- [ ] Phân bổ được xem xét lại khi yêu cầu, kiến trúc hoặc lịch sử lỗi thay đổi.

## Kết luận

Giảm kiểm tra trùng mục tiêu là việc phân công rõ nơi xác minh chính và giữ lại những kiểm tra bổ sung có giá trị ở các ranh giới khác nhau. Unit test nên xác minh chi tiết quy tắc cục bộ; integration và contract test tập trung vào giao tiếp, dữ liệu và phối hợp; end-to-end test xác minh một số hành trình quan trọng của người dùng. Khi mỗi ca có mục tiêu rõ, có lý do tồn tại và được liên kết với rủi ro, bộ kiểm thử có thể phản hồi nhanh hơn mà vẫn duy trì bằng chứng cần thiết cho quyết định phát hành.
