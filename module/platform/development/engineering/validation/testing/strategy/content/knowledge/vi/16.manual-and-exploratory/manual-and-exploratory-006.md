# Lựa chọn cặp phối hợp giữa phát triển, kiểm thử và nghiệp vụ

Trong module **VALIDATION_TESTING_STRATEGY**, kiểm thử thủ công và kiểm thử khám phá hiệu quả hơn khi người hiểu cách xây dựng sản phẩm, người chuyên trách chất lượng và người hiểu nghiệp vụ cùng chia sẻ góc nhìn. Một người có thể nhận ra vấn đề về logic hoặc kỹ thuật; người khác có thể phát hiện kỳ vọng người dùng chưa rõ; người thứ ba có thể hiểu điều kiện vận hành hoặc quy tắc nghiệp vụ mà hai người còn lại chưa biết.

**Phối hợp theo cặp (pair collaboration)** là cách hai vai trò cùng làm việc trên một mục tiêu kiểm thử hoặc một vấn đề cần làm rõ. Các cặp có thể gồm phát triển–kiểm thử, kiểm thử–nghiệp vụ hoặc phát triển–nghiệp vụ. Khi câu hỏi cần nhiều góc nhìn cùng lúc, nhóm có thể dùng phiên phối hợp ba bên, thường được gọi là Three Amigos. Việc lựa chọn cặp phụ thuộc vào mục tiêu, loại bất định, rủi ro và quyết định cần đưa ra.

Không phải lúc nào cũng cần mời tất cả mọi người vào một phiên. Chọn đúng người giúp cuộc trao đổi tập trung, tạo bằng chứng nhanh và tránh để một vai trò phải tự suy diễn thay vai trò khác. Bài học này hướng dẫn cách lựa chọn cặp phối hợp, phân công vai trò, tổ chức phiên làm việc và chuyển kết quả thành hành động kiểm thử có thể truy vết.

## 1. Mục tiêu của phối hợp theo cặp

### 1.1. Vì sao cần phối hợp?

Một yêu cầu phần mềm thường chứa ba lớp hiểu biết:

- **Nghiệp vụ:** vấn đề nào cần giải quyết, quy tắc nào áp dụng và kết quả nào có giá trị với người dùng hoặc tổ chức.
- **Phát triển:** giải pháp được xây dựng ra sao, các thành phần tương tác thế nào và giới hạn kỹ thuật nằm ở đâu.
- **Kiểm thử:** điều gì có thể sai, cần quan sát bằng chứng nào và làm sao xác nhận hành vi trong nhiều điều kiện.

Nếu chỉ một vai trò phân tích, có thể xuất hiện khoảng trống. Chuyên gia nghiệp vụ có thể mô tả mục tiêu nhưng chưa nêu hết tình huống kỹ thuật. Developer có thể triển khai đúng mô tả nhưng mô tả chưa phản ánh đủ ngoại lệ thực tế. Tester có thể thiết kế nhiều trường hợp nhưng chưa biết quy tắc nào là bắt buộc và quy tắc nào chỉ là giả định.

Phối hợp giúp các góc nhìn bổ sung cho nhau ngay khi vấn đề được phát hiện, trước khi hiểu nhầm trở thành mã, dữ liệu hoặc tiêu chí kiểm thử.

### 1.2. Kết quả mong đợi

Một phiên phối hợp tốt nên tạo ra một hoặc nhiều kết quả cụ thể:

- Thống nhất cách hiểu về mục tiêu và quy tắc nghiệp vụ.
- Làm rõ điều kiện trước, hành động, kết quả và ngoại lệ.
- Xác định giả định, câu hỏi còn mở và người có thẩm quyền trả lời.
- Tìm rủi ro hoặc đường lỗi mà một vai trò có thể bỏ sót.
- Chọn dữ liệu, môi trường và bằng chứng phù hợp.
- Thiết kế hoặc thực hiện một số kiểm thử mục tiêu.
- Xác định lỗi cần sửa, quyết định cần phê duyệt hoặc bước tiếp theo.

Không nên tổ chức phiên chỉ để “cùng xem qua” mà không xác định câu hỏi cần trả lời. Nếu mục tiêu là làm rõ quy tắc, kết quả cần là quyết định hoặc câu hỏi được giao người xử lý. Nếu mục tiêu là kiểm thử khám phá, kết quả cần gồm quan sát, bằng chứng, rủi ro và vấn đề được phát hiện.

### 1.3. Phối hợp theo cặp không thay thế trách nhiệm chuyên môn

Hai người cùng làm việc không có nghĩa mọi quyết định đều được quyết định bằng biểu quyết. Mỗi vai trò vẫn giữ trách nhiệm phù hợp:

- Người có thẩm quyền nghiệp vụ xác nhận quy tắc, ưu tiên và kết quả mong muốn.
- Developer giải thích thiết kế, hành vi kỹ thuật và phương án triển khai.
- Tester đánh giá khả năng kiểm thử, thiết kế thăm dò, rủi ro và chất lượng bằng chứng.

Nếu không có người có thẩm quyền trong phiên, nhóm có thể ghi nhận cách hiểu tạm thời nhưng không nên biến nó thành quy tắc chính thức.

## 2. Các kiểu cặp và khi nào nên chọn

### 2.1. Cặp phát triển–kiểm thử

Cặp Developer–Tester phù hợp khi cần hiểu hành vi kỹ thuật, tìm lỗi trong một thay đổi hoặc kiểm tra tương tác giữa các thành phần.

Nên chọn cặp này khi:

- Một lỗi khó tái hiện hoặc cần hiểu đường đi dữ liệu.
- Thay đổi có nhiều nhánh xử lý, trạng thái hoặc xử lý bất đồng bộ.
- Cần kiểm tra nhanh một bản dựng hoặc nguyên mẫu.
- Tester cần hiểu giới hạn kỹ thuật để thiết kế thăm dò có trọng tâm.
- Developer cần phản hồi về khả năng quan sát, xử lý lỗi và khả năng kiểm thử.
- Một lỗi được sửa và cần cùng xác nhận điều kiện tái hiện cùng hành vi sau sửa.

Ví dụ: Tester nhận thấy yêu cầu tạo đơn có thể bị gửi lặp sau timeout. Developer giải thích cơ chế idempotency và trạng thái xử lý; Tester đề xuất gửi lại cùng mã yêu cầu, gửi đồng thời và kiểm tra số giao dịch cuối cùng. Cặp có thể cùng chạy thử, xem log và xác định bằng chứng cần có.

### 2.2. Cặp kiểm thử–nghiệp vụ

Cặp Tester–Business phù hợp khi cần chuyển kỳ vọng nghiệp vụ thành hành vi có thể quan sát hoặc làm rõ các trường hợp ngoại lệ.

Nên chọn cặp này khi:

- Yêu cầu có từ ngữ mơ hồ như “hợp lệ”, “đúng hạn”, “đủ điều kiện”.
- Có nhiều chính sách hoặc vai trò khác nhau.
- Cần xác nhận kết quả trong trường hợp biên hoặc ngoại lệ.
- Có sự khác biệt giữa quy trình trên tài liệu và cách nhân viên thực tế xử lý.
- Cần ưu tiên hành trình theo tác động đến khách hàng hoặc hoạt động.
- Cần xác nhận lỗi nào là lỗi nghiệp vụ và lỗi nào là hành vi được phép.

Ví dụ: Tester và chuyên gia nghiệp vụ cùng xem quy trình hủy lịch. Họ dùng các ví dụ trước 24 giờ, đúng 24 giờ, dưới 24 giờ, lịch đã bắt đầu và lịch do nhân viên đặt để xác định điều kiện hủy, hoàn phí và giải phóng chỗ. Tester chuyển kết quả thành tiêu chí và kịch bản.

### 2.3. Cặp phát triển–nghiệp vụ

Cặp Developer–Business phù hợp khi cần làm rõ tính khả thi, cách triển khai hoặc tác động của một quy tắc đến quy trình và dữ liệu.

Nên chọn cặp này khi:

- Một quy tắc nghiệp vụ khó triển khai hoặc có nhiều cách hiểu kỹ thuật.
- Cần đánh giá tác động của thay đổi lên dữ liệu cũ.
- Có giới hạn từ hệ thống tích hợp hoặc nền tảng.
- Cần xác định hành vi khi dịch vụ ngoài chậm hoặc không sẵn sàng.
- Cần thống nhất cách biểu diễn trạng thái hoặc sự kiện.
- Một quyết định thiết kế có thể làm thay đổi trải nghiệm hoặc chính sách.

Ví dụ: Chuyên gia nghiệp vụ yêu cầu hoàn tiền một phần. Developer cùng người nghiệp vụ làm rõ cách tính số tiền đủ điều kiện, trường hợp có nhiều lần hoàn và cách xử lý khi nhà cung cấp thanh toán phản hồi không rõ. Tester có thể tham gia sau đó để biến quy tắc thành kiểm thử.

### 2.4. Phiên phối hợp ba bên (Three Amigos)

Three Amigos là phiên làm việc có đại diện phát triển, kiểm thử và nghiệp vụ cùng xem xét một yêu cầu hoặc câu chuyện người dùng. Mỗi vai trò đưa ra góc nhìn riêng để phát hiện khác biệt trước khi triển khai hoặc chấp nhận.

Nên chọn phiên ba bên khi:

- Thay đổi có rủi ro nghiệp vụ hoặc kỹ thuật cao.
- Quy tắc, kiến trúc và cách xác minh phụ thuộc lẫn nhau.
- Các vai trò đang có cách hiểu khác nhau.
- Một quyết định ảnh hưởng nhiều nhóm hoặc nhiều hệ thống.
- Cần thống nhất tiêu chí chấp nhận trước khi phát triển.
- Cần đưa ra quyết định có tác động đến phát hành.

Không cần tổ chức phiên ba bên cho mọi thay đổi nhỏ. Một cặp có thể giải quyết câu hỏi chuyên biệt rồi ghi lại kết quả. Nếu phát hiện quyết định cần góc nhìn còn thiếu, hãy mời thêm vai trò phù hợp.

### 2.5. Bảng lựa chọn nhanh

| Mục tiêu hoặc vấn đề | Cặp phù hợp để bắt đầu | Khi cần mở rộng |
|---|---|---|
| Làm rõ quy tắc nghiệp vụ và ngoại lệ | Tester–Business | Thêm Developer nếu quy tắc ảnh hưởng giải pháp hoặc dữ liệu |
| Tái hiện lỗi kỹ thuật | Developer–Tester | Thêm Business nếu cần đánh giá hậu quả hoặc quy tắc |
| Xác nhận tính khả thi của yêu cầu | Developer–Business | Thêm Tester để xác định cách chứng minh |
| Thiết kế kiểm thử cho thay đổi rủi ro cao | Three Amigos | Mời chuyên gia bảo mật, dữ liệu hoặc vận hành nếu cần |
| Khám phá hành vi không rõ | Developer–Tester hoặc Tester–Business | Mở rộng khi phát hiện giả định nghiệp vụ hoặc kiến trúc |
| Xác nhận tiêu chí chấp nhận | Tester–Business | Thêm Developer nếu có giới hạn triển khai |
| Đánh giá tác động của thay đổi dữ liệu | Developer–Business | Thêm Tester để lập kiểm tra hồi quy và đối soát |

Bảng là hướng dẫn khởi đầu. Chọn người theo năng lực và quyền quyết định thực tế, không chỉ theo chức danh.

## 3. Chọn cặp dựa trên mục tiêu, bất định và rủi ro

### 3.1. Xác định câu hỏi cần trả lời trước

Trước khi mời người tham gia, hãy viết một câu hỏi cụ thể:

- “Điều kiện nào cho phép khách hủy đơn?”
- “Sau timeout, làm sao biết giao dịch đã được xử lý?”
- “Kết quả nào chứng minh tồn kho không bị trừ hai lần?”
- “Thay đổi trạng thái này ảnh hưởng những báo cáo nào?”
- “Người dùng chỉ dùng bàn phím có thể hoàn tất biểu mẫu không?”

Câu hỏi cho biết loại kiến thức cần có và giúp chọn cặp phù hợp. Nếu câu hỏi chứa cả chính sách và chi tiết kỹ thuật, có thể cần phiên ba bên hoặc hai phiên nối tiếp.

### 3.2. Phân loại điểm chưa chắc chắn

| Loại bất định | Ví dụ | Vai trò cần có |
|---|---|---|
| Nghiệp vụ | Không rõ chính sách hoàn phí | Người hiểu và có quyền xác nhận nghiệp vụ cùng Tester |
| Kỹ thuật | Không rõ timeout có thể xảy ra sau khi server đã xử lý | Developer cùng Tester |
| Tương tác giữa hai bên | Không rõ provider và consumer thống nhất trạng thái nào | Developer, Tester và chủ sở hữu nghiệp vụ hoặc tích hợp |
| Trải nghiệm người dùng | Không rõ thông báo lỗi có giúp người dùng khắc phục không | Tester cùng đại diện người dùng hoặc nghiệp vụ |
| Vận hành | Không rõ ai xử lý giao dịch ở trạng thái chưa xác định | Business, Developer và đại diện vận hành |
| Bảo mật hoặc tuân thủ | Không rõ dữ liệu nào được phép đưa vào log | Chuyên gia phụ trách cùng Developer và Tester |

Nếu câu hỏi liên quan đến quyết định pháp lý, bảo mật hoặc chính sách tổ chức, cần có người chịu trách nhiệm chuyên môn. Không nên yêu cầu cặp thông thường tự suy luận thay họ.

### 3.3. Ưu tiên theo rủi ro

Chọn phối hợp sớm khi:

- Hậu quả nếu sai có thể nghiêm trọng.
- Quy tắc có nhiều ngoại lệ hoặc cách hiểu khác nhau.
- Thay đổi ảnh hưởng dữ liệu, tiền, quyền truy cập hoặc hành trình cốt lõi.
- Có nhiều hệ thống hoặc nhóm cùng chịu trách nhiệm.
- Lỗi khó phát hiện hoặc khó phục hồi.
- Thời gian sửa muộn sẽ tốn kém.

Một lỗi hiển thị nhỏ có thể được xử lý qua cặp Tester–Developer. Một thay đổi ảnh hưởng cách thu tiền, hoàn tiền và đối soát nên được làm rõ với nghiệp vụ trước khi triển khai; phiên ba bên thường giúp các bên thống nhất tiêu chí và bằng chứng.

### 3.4. Chọn người có hiểu biết và quyền quyết định phù hợp

Không phải người mang chức danh “Business” nào cũng có quyền xác nhận chính sách. Không phải Developer nào cũng hiểu hệ thống tích hợp liên quan. Hãy chọn người:

- Có kinh nghiệm trực tiếp với quy trình hoặc thành phần.
- Có thể giải thích nguồn thông tin và giới hạn hiểu biết.
- Có quyền quyết định hoặc biết ai có quyền quyết định.
- Có thể tham gia vào hành động tiếp theo.
- Sẵn sàng xem xét bằng chứng và cập nhật cách hiểu.

Nếu người phù hợp không thể tham gia, ghi rõ ai cần xác nhận sau và điều gì chưa được phép kết luận.

## 4. Chuẩn bị phiên phối hợp

### 4.1. Xác định mục tiêu và phạm vi

Một lời mời tốt nên nêu:

- Chủ đề hoặc thay đổi cần xem xét.
- Câu hỏi hoặc quyết định cần giải quyết.
- Phạm vi: yêu cầu, hành trình, lỗi hoặc phiên bản nào.
- Kết quả mong đợi của phiên.
- Vai trò cần tham gia.
- Thời lượng dự kiến.
- Tài liệu, dữ liệu hoặc môi trường cần chuẩn bị.

Ví dụ: “Cùng xác minh quy tắc gửi lại yêu cầu thanh toán sau timeout. Mục tiêu là thống nhất hành vi idempotency, trạng thái khi kết quả chưa rõ và các bằng chứng cần kiểm tra. Chuẩn bị hợp đồng API, một mã giao dịch thử và log của môi trường integration.”

### 4.2. Chuẩn bị tài liệu và bằng chứng

Tùy mục tiêu, chuẩn bị:

- Yêu cầu và tiêu chí chấp nhận hiện tại.
- Ví dụ nghiệp vụ hoặc dữ liệu đã ẩn danh.
- Sơ đồ luồng và các thành phần liên quan.
- Mô tả lỗi, bước tái hiện và log.
- Phiên bản ứng dụng và môi trường.
- Bộ dữ liệu hoặc tài khoản thử nghiệm được cấp.
- Công cụ quan sát như log, trace, API client hoặc trình duyệt.
- Danh sách giả định và câu hỏi còn mở.

Không cần chuẩn bị mọi tài liệu có thể có. Chỉ đưa những thông tin hỗ trợ câu hỏi của phiên. Nếu thiếu một nguồn xác nhận quan trọng, ghi rõ giới hạn ngay từ đầu.

### 4.3. Phân vai trong phiên

Có thể dùng các vai trò sau:

- **Driver:** điều khiển công cụ, chạy thao tác hoặc ghi lại nội dung.
- **Navigator:** quan sát, đặt câu hỏi, đề xuất trường hợp và theo dõi mục tiêu.
- **Business voice:** giải thích quy tắc, tác nhân và hậu quả nghiệp vụ.
- **Facilitator:** giữ cuộc trao đổi đúng mục tiêu, bảo đảm các câu hỏi được ghi nhận.

Trong cặp hai người, một người có thể vừa điều khiển vừa ghi chép; nên luân phiên để cả hai đều tham gia suy nghĩ. Trong phiên ba bên, người điều phối có thể luân phiên hoặc do một người đảm nhiệm riêng. Không nên để một người thao tác liên tục còn người khác chỉ quan sát thụ động.

### 4.4. Thống nhất cách ghi nhận

Trước khi bắt đầu, xác định nơi ghi:

- Quy tắc đã thống nhất.
- Ví dụ và kết quả mong đợi.
- Giả định và câu hỏi còn mở.
- Lỗi hoặc rủi ro phát hiện.
- Bằng chứng và đường dẫn tham chiếu.
- Người phụ trách và thời hạn hành động.

Ghi nhận cần ngắn gọn nhưng đủ để người không tham dự hiểu kết quả và tiếp tục công việc.

## 5. Cách làm việc trong phiên phối hợp

### 5.1. Mở đầu bằng mục tiêu và hiểu biết hiện tại

Bắt đầu bằng cách nêu mục tiêu nghiệp vụ, thay đổi hoặc lỗi cần xem xét. Mỗi người chia sẻ điều mình biết và điều chưa chắc chắn. Không nên bắt đầu bằng việc tranh luận về giải pháp hoặc thao tác công cụ khi chưa thống nhất câu hỏi.

Có thể hỏi:

- Điều gì đang được yêu cầu hoặc quan sát?
- Người dùng muốn đạt kết quả gì?
- Điều gì đã được xác nhận?
- Điều gì đang là giả định?
- Quyết định nào cần được đưa ra trong phiên?

### 5.2. Khám phá ví dụ từ nhiều góc nhìn

Chọn một tình huống cụ thể rồi lần lượt xem:

- Business: tình huống có thực tế không, quy tắc nào áp dụng, hậu quả nếu sai là gì?
- Developer: hệ thống xử lý qua những thành phần nào, dữ liệu và trạng thái thay đổi ở đâu?
- Tester: điều kiện nào có thể làm hành vi sai, có thể quan sát bằng chứng nào, cần kiểm tra nhánh nào?

Ví dụ với yêu cầu hoàn tiền:

- Business nêu chính sách hoàn toàn phần và một phần.
- Developer giải thích cách lưu giao dịch gốc, giao dịch hoàn và trạng thái xử lý.
- Tester hỏi về hai yêu cầu hoàn đồng thời, timeout, retry và tổng tiền hoàn tối đa.

Từ đó, nhóm xác định quy tắc, kịch bản và điểm cần xác nhận thêm.

### 5.3. Dùng kỹ thuật đặt câu hỏi

Các câu hỏi hữu ích:

- “Điều gì xảy ra nếu…?”
- “Có trường hợp nào không áp dụng quy tắc này không?”
- “Làm sao biết thao tác đã hoàn tất?”
- “Nếu phản hồi không đến thì trạng thái nào được xem là đúng?”
- “Nguồn dữ liệu nào có thẩm quyền?”
- “Ai có quyền thực hiện hành động này?”
- “Điều gì không được phép thay đổi khi thao tác thất bại?”
- “Bằng chứng nào sẽ thuyết phục người khác rằng kết quả đúng?”

Câu hỏi nên trung lập và hướng đến hiểu biết. Tránh hỏi theo cách dẫn dắt để người khác xác nhận một giả định đã có sẵn.

### 5.4. Thử nghiệm và quan sát khi phù hợp

Nếu mục tiêu là khám phá hành vi, cặp có thể thực hiện một thử nghiệm có kiểm soát:

1. Xác định câu hỏi và giả thuyết.
2. Chuẩn bị dữ liệu và môi trường.
3. Ghi trạng thái ban đầu.
4. Thực hiện một hành động hoặc biến thể.
5. Quan sát phản hồi và tác dụng phụ.
6. Lưu bằng chứng.
7. So sánh với quy tắc hoặc kỳ vọng.
8. Ghi kết luận và câu hỏi tiếp theo.

Chỉ thay đổi một yếu tố chính mỗi lần khi cần tìm nguyên nhân. Với thử nghiệm có thể tạo giao dịch, gửi thông báo hoặc thay đổi dữ liệu, hãy sử dụng môi trường và tài khoản được phép.

### 5.5. Chốt lại trước khi kết thúc

Cuối phiên, đọc lại:

- Điều đã thống nhất.
- Điều chưa thống nhất hoặc chưa đủ bằng chứng.
- Lỗi và rủi ro được phát hiện.
- Hành động tiếp theo, người phụ trách và thời hạn.
- Kiểm thử cần bổ sung hoặc chạy lại.
- Quyết định nào cần người có thẩm quyền phê duyệt.

Không kết thúc bằng câu “đã trao đổi xong” nếu chưa biết ai làm gì tiếp theo.

## 6. Ví dụ: chọn cặp cho một yêu cầu giảm giá

Giả sử sản phẩm bổ sung mã giảm giá theo nhóm khách hàng. Mã có thể bị giới hạn theo thời gian, số lần sử dụng và giá trị đơn.

### 6.1. Khi cần cặp Tester–Business

Câu hỏi ban đầu: “Khách thuộc nhóm nào được áp dụng mã?”

Tester và chuyên gia nghiệp vụ làm rõ:

- Nhóm khách hàng được xác định tại thời điểm nào?
- Khách thay đổi nhóm sau khi thêm mã vào giỏ thì giá được tính lại không?
- Mã áp dụng đồng thời với khuyến mãi khác không?
- Mã hết hạn trong lúc khách đang thanh toán thì xử lý ra sao?
- Có giới hạn theo khách hàng, đơn hàng hay toàn chiến dịch?

Kết quả là các quy tắc được xác nhận và ví dụ đối chiếu để viết tiêu chí chấp nhận.

### 6.2. Khi cần cặp Developer–Tester

Sau khi quy tắc rõ, Developer và Tester xem cách tính giá được gọi ở giỏ hàng, đơn hàng và thanh toán. Họ cùng kiểm tra:

- Cùng mã được gửi hai lần có giảm trùng không?
- Hai request áp dụng mã đồng thời có vượt giới hạn sử dụng không?
- Tổng tiền trong request thanh toán có khớp với đơn không?
- Khi dịch vụ khuyến mãi timeout, đơn có giữ trạng thái nhất quán không?

Cặp có thể tạo dữ liệu thử, chạy API và kiểm tra bản ghi để tìm vấn đề kỹ thuật.

### 6.3. Khi cần Three Amigos

Nếu thay đổi liên quan đến giá, tồn kho, thanh toán và báo cáo, một phiên ba bên giúp thống nhất toàn bộ kết quả:

- Business xác nhận quy tắc và hậu quả tài chính.
- Developer giải thích nguồn dữ liệu, cách tính và luồng tích hợp.
- Tester đề xuất trường hợp, rủi ro và bằng chứng.

Kết quả có thể là một ma trận điều kiện, tiêu chí chấp nhận, danh sách kiểm thử và các câu hỏi cần chủ sở hữu tài chính xác nhận.

## 7. Phối hợp trong kiểm thử khám phá

### 7.1. Khi nào nên pair exploratory testing?

Kiểm thử khám phá theo cặp hữu ích khi:

- Hành vi sản phẩm chưa được mô tả đầy đủ.
- Lỗi khó tái hiện hoặc chỉ xuất hiện trong một chuỗi thao tác.
- Cần khám phá nhanh một tính năng mới.
- Có nhiều cách hiểu về kết quả mong đợi.
- Cần quan sát đồng thời hành vi và log kỹ thuật.
- Một người cần học cách sử dụng hệ thống hoặc hiểu miền nghiệp vụ.

Một người điều khiển thao tác, người còn lại quan sát và đặt câu hỏi. Sau một khoảng thời gian, hai người đổi vai để tránh thiên kiến và giúp cả hai hiểu toàn bộ hành trình.

### 7.2. Dùng charter để giữ trọng tâm

Charter là mục tiêu khám phá ngắn gọn, có thể gồm:

- **Mục tiêu:** điều cần tìm hiểu.
- **Phạm vi:** tính năng, hành trình hoặc thành phần.
- **Rủi ro:** điều gì có thể sai.
- **Dữ liệu:** điều kiện cần chuẩn bị.
- **Giới hạn:** môi trường và thao tác được phép.
- **Thời lượng:** khoảng thời gian khám phá.
- **Kết quả mong đợi:** ghi nhận, bằng chứng và câu hỏi.

Ví dụ charter:

> Khám phá cách giỏ hàng áp dụng và giữ mã giảm giá khi khách thay đổi số lượng, đăng nhập hoặc thanh toán chậm. Tập trung vào tổng tiền, số lần sử dụng mã và trạng thái đơn. Dùng tài khoản thử nghiệm, không tạo giao dịch thật. Ghi lại các trường hợp tổng tiền thay đổi bất thường và mã tương quan.

### 7.3. Ghi lại session notes

Trong phiên, ghi theo cấu trúc:

| Thời điểm | Hành động / dữ liệu | Quan sát | Giả thuyết hoặc câu hỏi |
|---|---|---|---|
| 10:02 | Thêm mã giảm giá vào giỏ | Tổng tiền giảm đúng | Cần xác nhận thời hạn mã |
| 10:05 | Tăng số lượng sản phẩm | Tổng tiền tính lại nhưng mã vẫn hiển thị | Giới hạn giảm theo đơn hay theo sản phẩm? |
| 10:08 | Gửi thanh toán rồi mô phỏng timeout | Giao diện vẫn ở trạng thái chờ | Cần truy vấn trạng thái trước retry |
| 10:12 | Tải lại giỏ hàng | Mã giảm giá không còn | Có thể trạng thái chưa được lưu bền vững |

Ghi quan sát tách biệt với giả thuyết. “Mã biến mất sau tải lại” là quan sát; “backend không lưu mã” là giả thuyết cần xác minh.

### 7.4. Kết thúc phiên khám phá

Phân loại kết quả:

- Lỗi đã tái hiện và có bằng chứng.
- Hành vi bất ngờ cần làm rõ với nghiệp vụ.
- Rủi ro chưa thể kiểm tra trong môi trường hiện tại.
- Giả thuyết đã được xác nhận hoặc bác bỏ.
- Kiểm thử hồi quy cần bổ sung.
- Câu hỏi cần chuyển cho chủ sở hữu.

Không nên chuyển mọi quan sát thành defect ngay. Có thể đó là hành vi được thiết kế, giới hạn môi trường hoặc yêu cầu chưa rõ. Cần phân loại trước khi mở lỗi.

## 8. Phối hợp từ refinement đến xác nhận sau sửa

Cặp phối hợp có thể được sử dụng ở nhiều thời điểm trong vòng đời phát triển.

### 8.1. Trước khi phát triển

Tester–Business hoặc Three Amigos cùng làm rõ:

- Mục tiêu và tác nhân.
- Quy tắc và ví dụ.
- Tiêu chí chấp nhận.
- Nhánh lỗi và ngoại lệ.
- Rủi ro và bằng chứng cần có.

Kết quả giúp giảm thay đổi do hiểu nhầm khi đã triển khai.

### 8.2. Trong khi phát triển

Developer–Tester có thể cùng:

- Rà soát thay đổi và các đường xử lý.
- Thiết kế dữ liệu kiểm thử.
- Kiểm tra khả năng quan sát.
- Chạy thử trên môi trường phát triển.
- Phát hiện lỗi sớm và điều chỉnh cách kiểm thử.

Business có thể tham gia khi một câu hỏi về quy tắc hoặc ưu tiên xuất hiện.

### 8.3. Khi phát hiện lỗi

Developer–Tester cùng tái hiện và xác định nguyên nhân. Business tham gia nếu cần xác nhận tác động hoặc kết quả đúng. Ghi lại:

- Điều kiện tái hiện.
- Hành vi thực tế và mong đợi.
- Phạm vi ảnh hưởng.
- Nguyên nhân đã biết hoặc giả thuyết.
- Kiểm thử xác nhận sau sửa.
- Hành vi hồi quy cần kiểm tra.

### 8.4. Trước khi chấp nhận hoặc phát hành

Three Amigos hoặc nhóm phù hợp xem xét:

- Các tiêu chí quan trọng đã có bằng chứng chưa?
- Lỗi còn mở ảnh hưởng đến người dùng hoặc nghiệp vụ thế nào?
- Có rủi ro nào chưa được kiểm tra?
- Có giới hạn môi trường hoặc phụ thuộc mô phỏng không?
- Ai có quyền chấp nhận rủi ro còn lại?
- Điều kiện nào cần theo dõi sau phát hành?

Phối hợp không thay thế quyết định phát hành của người có thẩm quyền. Nó cung cấp thông tin và bằng chứng để quyết định đó có căn cứ.

## 9. Kỹ năng và nguyên tắc làm việc hiệu quả

### 9.1. Lắng nghe và làm rõ trước khi kết luận

Mỗi vai trò có vốn từ và cách nhìn khác nhau. Hãy yêu cầu ví dụ cụ thể khi một thuật ngữ có thể mang nhiều nghĩa. Tóm tắt lại điều vừa nghe để xác nhận cách hiểu.

### 9.2. Tập trung vào vấn đề, không đổ lỗi

Khi phát hiện lỗi, tập trung vào điều kiện, dữ liệu, thiết kế và bằng chứng. Tránh gắn lỗi với năng lực hoặc cá nhân. Mục tiêu là hiểu hệ thống và cải thiện cách làm việc.

### 9.3. Luân phiên điều khiển và quan sát

Trong pair testing, người điều khiển không nên chiếm toàn bộ phiên. Người quan sát cần chủ động đề xuất biến thể, hỏi về trạng thái và ghi nhận bằng chứng. Luân phiên giúp phát hiện điểm mù và chia sẻ hiểu biết.

### 9.4. Tôn trọng thẩm quyền và giới hạn kiến thức

Developer không tự quyết định chính sách nghiệp vụ; Tester không tự suy diễn tiêu chí chấp nhận; Business không giả định giới hạn kỹ thuật nếu chưa được xác minh. Khi thiếu chuyên gia, ghi nhận câu hỏi và chuyển đúng người.

### 9.5. Giữ phiên làm việc ngắn và có mục tiêu

Chia vấn đề lớn thành các câu hỏi nhỏ. Một phiên có thể tập trung vào quy tắc, phiên khác vào kiểm thử kỹ thuật. Kết thúc mỗi phiên bằng kết quả và hành động cụ thể.

### 9.6. Ghi bằng chứng đủ để người khác tiếp tục

Ghi phiên bản, môi trường, dữ liệu, bước thực hiện, quan sát và mã tham chiếu. Không phụ thuộc vào trí nhớ của người tham gia. Bằng chứng cần đủ rõ để người không dự phiên có thể hiểu và tiếp tục xử lý.

## 10. Làm việc từ xa và phối hợp không đồng bộ

### 10.1. Phiên trực tiếp hoặc từ xa

Pair collaboration có thể thực hiện trực tiếp hoặc qua công cụ chia sẻ màn hình, trình duyệt, terminal, bảng trắng và tài liệu chung. Với phiên từ xa:

- Xác nhận mọi người có quyền truy cập môi trường và dữ liệu cần thiết.
- Thống nhất ai điều khiển chuột, bàn phím hoặc terminal.
- Dùng con trỏ, ghi chú hoặc mã tham chiếu để chỉ rõ vùng đang thảo luận.
- Ghi lại kết quả ở một nơi chung.
- Tránh chia sẻ secret hoặc dữ liệu nhạy cảm trên màn hình.
- Dành thời gian để người tham gia quan sát và đặt câu hỏi.

### 10.2. Khi không thể cùng tham gia

Có thể phối hợp không đồng bộ bằng:

- Gửi câu hỏi cụ thể kèm ví dụ và bằng chứng.
- Ghi nhận cách hiểu tạm thời và đánh dấu cần xác nhận.
- Đính kèm bước tái hiện và môi trường.
- Đề nghị người có thẩm quyền trả lời một câu hỏi rõ.
- Tổng hợp quyết định và yêu cầu xác nhận lại.

Không nên dùng một bình luận ngắn như “nhờ xem giúp” khi người nhận cần hiểu bối cảnh và quyết định. Cung cấp đủ thông tin để họ có thể phản hồi mà không phải tái dựng toàn bộ vấn đề.

### 10.3. Lưu quyết định và tránh mất ngữ cảnh

Mỗi kết luận quan trọng nên có:

- Người tham gia và vai trò.
- Ngày, phiên bản và phạm vi.
- Câu hỏi cần giải quyết.
- Kết luận và căn cứ.
- Giả định hoặc giới hạn.
- Người phê duyệt nếu cần.
- Hành động tiếp theo và thời hạn.

Khi yêu cầu hoặc chính sách thay đổi, xem lại quyết định cũ để tránh áp dụng kết luận không còn phù hợp.

## 11. Những sai lầm thường gặp

1. **Chọn cặp theo chức danh thay vì câu hỏi:** mời người không có kiến thức hoặc quyền quyết định phù hợp.
2. **Mời quá nhiều người cho vấn đề nhỏ:** cuộc trao đổi mất trọng tâm và khó chốt hành động.
3. **Chỉ có Developer và Tester trong câu hỏi nghiệp vụ:** hai người tự suy diễn chính sách mà không có xác nhận.
4. **Chỉ có Business và Tester khi cần hiểu kỹ thuật:** kết luận kiểm thử không tính đến giới hạn hoặc phụ thuộc hệ thống.
5. **Để một người thao tác toàn bộ:** người còn lại không chủ động quan sát và đặt câu hỏi.
6. **Không xác định mục tiêu phiên:** cuộc trao đổi lan sang nhiều vấn đề mà không có kết quả rõ.
7. **Biến giả định thành quyết định:** không ghi người có thẩm quyền xác nhận.
8. **Tranh luận theo ý kiến:** không dùng ví dụ, dữ liệu hoặc bằng chứng để giải quyết khác biệt.
9. **Không ghi lại hành động tiếp theo:** câu hỏi chưa giải quyết bị bỏ quên.
10. **Coi mọi quan sát là lỗi:** không phân biệt defect, hành vi mong đợi, giới hạn môi trường và yêu cầu chưa rõ.
11. **Không luân phiên vai trò:** mất góc nhìn hoặc tạo phụ thuộc vào một người.
12. **Không đánh giá lại cặp khi phạm vi đổi:** vấn đề đã chuyển sang nghiệp vụ, bảo mật hoặc kiến trúc nhưng vẫn chỉ có hai vai trò ban đầu.

## 12. Checklist lựa chọn và tổ chức cặp phối hợp

- [ ] Đã xác định câu hỏi hoặc mục tiêu cụ thể của phiên.
- [ ] Đã phân loại điểm chưa chắc chắn là nghiệp vụ, kỹ thuật, trải nghiệm hay vận hành.
- [ ] Đã chọn cặp có kiến thức và quyền quyết định phù hợp.
- [ ] Đã mời thêm vai trò thứ ba hoặc chuyên gia khi câu hỏi vượt phạm vi cặp.
- [ ] Đã xác định phạm vi, phiên bản, môi trường và thời lượng.
- [ ] Đã chuẩn bị yêu cầu, ví dụ, dữ liệu và bằng chứng cần thiết.
- [ ] Đã thống nhất người điều khiển, người quan sát và cách ghi nhận.
- [ ] Phiên làm việc tập trung vào ví dụ và câu hỏi có thể kiểm chứng.
- [ ] Quan sát được tách biệt với giả thuyết và kết luận.
- [ ] Quy tắc nghiệp vụ được người có thẩm quyền xác nhận.
- [ ] Lỗi và rủi ro có bằng chứng, phạm vi và mức ưu tiên.
- [ ] Câu hỏi còn mở có người phụ trách và thời hạn.
- [ ] Kết quả được liên kết với tiêu chí chấp nhận và kiểm thử liên quan.
- [ ] Có hành động tiếp theo rõ ràng sau phiên.

Lựa chọn đúng cặp phối hợp giúp đưa kiến thức nghiệp vụ, hiểu biết kỹ thuật và tư duy kiểm thử vào cùng một cuộc trao đổi có mục tiêu. Khi mỗi vai trò đóng góp đúng thế mạnh, nhóm có thể làm rõ quy tắc sớm hơn, khám phá rủi ro có trọng tâm và tạo ra bằng chứng đủ tin cậy để hỗ trợ quyết định chấp nhận sản phẩm.
