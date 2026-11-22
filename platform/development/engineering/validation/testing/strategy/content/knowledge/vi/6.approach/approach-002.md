# Kiểm thử dựa trên yêu cầu và tiêu chí chấp nhận

Trong module `VALIDATION_TESTING_STRATEGY`, kiểm thử dựa trên yêu cầu và tiêu chí chấp nhận là cách xây dựng hoạt động kiểm thử từ điều sản phẩm cần đáp ứng. Thay vì chọn trường hợp kiểm thử theo thói quen hoặc chỉ dựa vào cấu trúc mã nguồn, nhóm bắt đầu từ nhu cầu, quy tắc và kết quả được mong đợi, sau đó chuyển chúng thành điều kiện, dữ liệu, thao tác và bằng chứng có thể xác minh.

**Kiểm thử dựa trên yêu cầu (requirements-based testing)** xác nhận các yêu cầu đã được triển khai đúng và đầy đủ. **Kiểm thử dựa trên tiêu chí chấp nhận (acceptance-criteria-based testing)** tập trung vào những điều kiện cụ thể phải thỏa mãn để một yêu cầu, tính năng hoặc câu chuyện người dùng được chấp nhận. Hai cách tiếp cận bổ trợ cho nhau: yêu cầu xác định phạm vi và ý định; tiêu chí chấp nhận làm rõ thế nào là kết quả đạt được trong các tình huống cụ thể.

Một chiến lược tốt cần bảo đảm mỗi yêu cầu quan trọng có thể truy vết đến kiểm thử và bằng chứng; mỗi tiêu chí chấp nhận được diễn giải nhất quán; các trường hợp thành công, từ chối, biên và ngoại lệ được xem xét theo rủi ro. Bài học này trình bày cách đọc và làm rõ yêu cầu, chuyển yêu cầu thành điều kiện kiểm thử, xây dựng tiêu chí chấp nhận có thể xác minh, tổ chức truy vết và xử lý thay đổi.

## 1. Hiểu yêu cầu và tiêu chí chấp nhận

### 1.1. Yêu cầu là gì?

Yêu cầu (requirement) mô tả một nhu cầu, khả năng, quy tắc hoặc thuộc tính mà sản phẩm hay hệ thống cần đáp ứng. Yêu cầu có thể đến từ người dùng, chủ sở hữu sản phẩm, quy trình kinh doanh, hợp đồng, quy định, kiến trúc hoặc các hệ thống tích hợp.

Một yêu cầu có thể mô tả:

- **Chức năng:** hệ thống cần thực hiện hành động hoặc cung cấp khả năng nào.
- **Quy tắc nghiệp vụ:** điều kiện nào quyết định kết quả, quyền hạn hoặc trạng thái.
- **Dữ liệu:** dữ liệu nào cần được thu thập, xử lý, lưu trữ hoặc trao đổi.
- **Giao diện và tích hợp:** cách người dùng hoặc hệ thống khác tương tác.
- **Thuộc tính chất lượng:** mức hiệu năng, bảo mật, độ tin cậy, khả năng sử dụng, tương thích hoặc khả năng phục hồi cần đạt.
- **Ràng buộc:** điều kiện kỹ thuật, vận hành, pháp lý hoặc chính sách mà giải pháp phải tuân theo.

Yêu cầu có thể được ghi dưới dạng tài liệu đặc tả, câu chuyện người dùng (user story), trường hợp sử dụng, quy tắc nghiệp vụ, hợp đồng API, tiêu chuẩn chất lượng hoặc tiêu chí trong hợp đồng. Dù ở định dạng nào, yêu cầu cần có ý nghĩa rõ ràng với người triển khai và người xác nhận.

### 1.2. Tiêu chí chấp nhận là gì?

Tiêu chí chấp nhận (acceptance criteria) là tập hợp điều kiện có thể quan sát hoặc xác minh, dùng để quyết định một yêu cầu hoặc phần việc đã đáp ứng kỳ vọng hay chưa. Tiêu chí giúp nhóm thống nhất kết quả cần đạt và cung cấp căn cứ để kiểm thử.

Ví dụ, yêu cầu “người dùng có thể đặt lại mật khẩu” chưa đủ chi tiết để xác nhận. Các tiêu chí chấp nhận có thể nêu:

- Người dùng đã đăng ký có thể yêu cầu liên kết đặt lại mật khẩu.
- Liên kết có thời hạn sử dụng được xác định.
- Liên kết hết hạn hoặc đã sử dụng không thể đặt lại mật khẩu lần nữa.
- Mật khẩu mới phải đáp ứng chính sách hiện hành.
- Sau khi đặt lại thành công, người dùng có thể đăng nhập bằng mật khẩu mới.
- Hệ thống không tiết lộ liệu một địa chỉ email có tồn tại hay không qua thông báo công khai, nếu chính sách bảo mật yêu cầu.

Tiêu chí chấp nhận thường cụ thể hơn mô tả yêu cầu, nhưng không nhất thiết thay thế toàn bộ đặc tả. Một tính năng lớn có thể có nhiều yêu cầu, mỗi yêu cầu có một nhóm tiêu chí. Một tiêu chí cũng có thể cần nhiều trường hợp kiểm thử để bao phủ các nhánh và dữ liệu khác nhau.

### 1.3. Phân biệt yêu cầu, tiêu chí chấp nhận và trường hợp kiểm thử

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Yêu cầu | Sản phẩm cần đáp ứng nhu cầu hoặc quy tắc nào? | Người dùng có thể đặt lại mật khẩu |
| Tiêu chí chấp nhận | Điều kiện nào phải đúng để yêu cầu được chấp nhận? | Liên kết hết hạn không thể sử dụng |
| Trường hợp kiểm thử | Cần thiết lập gì, thực hiện gì và quan sát gì để xác minh tiêu chí? | Tạo liên kết, chờ quá thời hạn, mở liên kết và xác nhận hệ thống từ chối |
| Bằng chứng | Dựa vào dữ liệu hoặc quan sát nào để kết luận? | Phản hồi từ hệ thống, trạng thái token, log kiểm toán phù hợp và thông báo trên giao diện |

Không nên xem một câu mô tả yêu cầu là trường hợp kiểm thử hoàn chỉnh. Trường hợp kiểm thử cần có điều kiện ban đầu, hành động, dữ liệu và kết quả mong đợi. Tương tự, một tiêu chí như “hệ thống phải nhanh” chưa thể kiểm thử cho đến khi có ngưỡng, điều kiện đo và cách đánh giá.

### 1.4. Yêu cầu chức năng và phi chức năng

Yêu cầu chức năng mô tả hệ thống làm gì. Yêu cầu phi chức năng mô tả hệ thống cần vận hành tốt đến mức nào hoặc phải tuân theo thuộc tính chất lượng nào.

| Loại | Ví dụ yêu cầu | Hướng kiểm thử |
|---|---|---|
| Chức năng | Người dùng có thể tìm đơn hàng theo mã đơn | Tìm với mã hợp lệ, không tồn tại, sai định dạng và dữ liệu biên |
| Quy tắc nghiệp vụ | Chỉ chủ đơn hoặc vai trò được cấp quyền mới xem được chi tiết | Kiểm tra quyền đúng, sai và truy cập trực tiếp qua API |
| Hiệu năng | 95% yêu cầu tìm kiếm hoàn tất trong ngưỡng thời gian đã thỏa thuận ở tải xác định | Đo phân vị thời gian phản hồi trong điều kiện tải được mô tả |
| Bảo mật | Dữ liệu nhạy cảm chỉ được truy cập bởi vai trò phù hợp | Kiểm tra xác thực, phân quyền và khả năng truy cập trái phép |
| Độ tin cậy | Giao dịch được xử lý nhất quán khi một dịch vụ phụ thuộc tạm thời không sẵn sàng | Mô phỏng lỗi, thử lại và xác minh trạng thái sau phục hồi |
| Tương thích | Chức năng hoạt động trên các trình duyệt hoặc thiết bị được hỗ trợ | Chạy bộ kiểm thử trên ma trận nền tảng đã thống nhất |

Yêu cầu phi chức năng cũng cần tiêu chí chấp nhận đo được. Chẳng hạn, “hệ thống chịu tải tốt” cần được làm rõ bằng tải đồng thời, thời gian chạy, phân vị phản hồi, tỷ lệ lỗi và điều kiện môi trường. Nếu không có các thông tin đó, kết quả đo khó dùng để đưa ra quyết định.

## 2. Đọc và đánh giá chất lượng yêu cầu trước khi kiểm thử

Kiểm thử hiệu quả bắt đầu từ yêu cầu đủ rõ. Yêu cầu mơ hồ hoặc mâu thuẫn khiến người viết kiểm thử phải tự suy diễn, dẫn đến kết quả mong đợi không thống nhất.

### 2.1. Đặc điểm của yêu cầu có thể kiểm thử

Một yêu cầu tốt thường có các đặc điểm:

- **Rõ ràng:** chỉ có một cách hiểu hợp lý trong bối cảnh đã nêu.
- **Đầy đủ:** nêu đủ điều kiện, quy tắc và ngoại lệ quan trọng.
- **Nhất quán:** không mâu thuẫn với yêu cầu hoặc chính sách khác.
- **Có thể xác minh:** có thể thu thập bằng chứng để kết luận đạt hoặc không đạt.
- **Có thể truy vết:** có mã hoặc tham chiếu giúp liên kết với nguồn và kiểm thử.
- **Có phạm vi:** chỉ rõ đối tượng, vai trò, điều kiện và ranh giới áp dụng.
- **Khả thi:** có thể thực hiện trong giới hạn kỹ thuật, dữ liệu, nguồn lực và quy định.
- **Có ưu tiên:** mức quan trọng hoặc thứ tự xử lý được hiểu rõ.

Không phải mọi yêu cầu đều cần cùng mức chi tiết. Tuy nhiên, những yêu cầu có rủi ro cao hoặc ảnh hưởng đến nhiều hệ thống cần được làm rõ trước khi thiết kế kiểm thử.

### 2.2. Nhận diện từ ngữ mơ hồ

Các từ như “nhanh”, “dễ dùng”, “hợp lý”, “an toàn”, “thường xuyên”, “đầy đủ” hoặc “tối ưu” thường chưa đủ để tạo kết quả mong đợi cụ thể.

Ví dụ:

| Câu yêu cầu chưa rõ | Câu hỏi cần làm rõ |
|---|---|
| Trang phải tải nhanh | Đo thời gian nào, ở phân vị nào, với dữ liệu và tải ra sao? |
| Người dùng chỉ được xem dữ liệu phù hợp | Vai trò nào được xem đối tượng nào? Có ngoại lệ hoặc quyền quản trị không? |
| Hệ thống phải xử lý giao dịch an toàn | Cần bảo đảm tính toàn vẹn, chống trùng, mã hóa hay khả năng phục hồi nào? |
| Tìm kiếm phải trả kết quả chính xác | Quy tắc xếp hạng, điều kiện lọc và mức độ khớp được định nghĩa ra sao? |
| Thông báo được gửi kịp thời | Trong bao lâu, qua kênh nào và xử lý thế nào khi nhà cung cấp không sẵn sàng? |

Hãy chuyển từ ngữ định tính thành điều kiện quan sát được, ngưỡng đo hoặc quy tắc đã được người có thẩm quyền xác nhận. Không tự đặt ngưỡng chỉ để có thể viết kiểm thử.

### 2.3. Kiểm tra tính đầy đủ và nhất quán

Với mỗi yêu cầu, xem xét các câu hỏi:

- Ai là người dùng hoặc hệ thống khởi tạo?
- Điều kiện trước khi thực hiện là gì?
- Đầu vào nào hợp lệ và đầu vào nào bị từ chối?
- Kết quả thành công được biểu diễn ở đâu?
- Có trạng thái trung gian hay chuyển trạng thái nào?
- Nếu thất bại, hệ thống phải phản hồi và phục hồi thế nào?
- Quy tắc về quyền hạn, dữ liệu và bảo mật là gì?
- Có giới hạn về thời gian, khối lượng hoặc tần suất không?
- Yêu cầu có xung đột với quy tắc hiện có hay yêu cầu khác không?

Ví dụ, một yêu cầu “hủy đơn hàng” cần làm rõ đơn được hủy ở trạng thái nào, có cần hoàn tiền không, tồn kho được giải phóng khi nào, thông báo nào được gửi và nhân viên có quyền hủy thay khách hay không. Nếu chỉ kiểm tra nút Hủy xuất hiện và trạng thái đổi thành “Đã hủy”, nhóm có thể bỏ sót các tác động nghiệp vụ phía sau.

### 2.4. Xử lý yêu cầu thiếu hoặc mâu thuẫn

Khi phát hiện điểm chưa rõ:

1. Ghi lại nguyên văn yêu cầu và vị trí nguồn.
2. Mô tả cách hiểu hiện tại và vì sao có nhiều cách diễn giải.
3. Đưa ra câu hỏi cụ thể kèm ví dụ tình huống.
4. Xác định người có thẩm quyền trả lời, chẳng hạn Product Owner, chuyên gia nghiệp vụ, chủ sở hữu dữ liệu hoặc kiến trúc sư.
5. Ghi lại quyết định, thời điểm, phạm vi và các yêu cầu bị ảnh hưởng.
6. Cập nhật tiêu chí chấp nhận và trường hợp kiểm thử liên quan.

Nếu chưa có câu trả lời, đánh dấu giả định hoặc câu hỏi còn mở. Với yêu cầu quan trọng, không nên tự tạo kết quả mong đợi từ phỏng đoán. Nhóm có thể tiếp tục chuẩn bị những phần độc lập, nhưng cần nêu rõ điểm nào đang chặn việc kết luận.

## 3. Chuyển yêu cầu thành điều kiện kiểm thử

Sau khi hiểu yêu cầu, người kiểm thử phân rã nó thành các quy tắc và điều kiện có thể kiểm tra. Mục tiêu là bao phủ những cách hệ thống có thể nhận đầu vào, xử lý và tạo ra kết quả.

### 3.1. Phân rã yêu cầu thành quy tắc

Một yêu cầu lớn thường chứa nhiều quy tắc nhỏ. Ví dụ, “người dùng có thể tạo lịch hẹn” có thể bao gồm:

- Người dùng đã đăng nhập và có quyền tạo lịch.
- Thời điểm đặt phải nằm trong khoảng cho phép.
- Khung giờ phải còn chỗ.
- Không được đặt trùng với lịch đã xác nhận của cùng người dùng nếu chính sách cấm.
- Hệ thống phải lưu múi giờ hoặc quy tắc thời gian thống nhất.
- Người dùng nhận được xác nhận sau khi đặt thành công.
- Khi hai người cùng đặt chỗ cuối cùng, chỉ số lượng hợp lệ được xác nhận.

Mỗi quy tắc cần được liên kết với yêu cầu gốc. Nếu một quy tắc không có nguồn xác nhận, hãy ghi rõ là giả định cần làm rõ.

### 3.2. Xác định điều kiện trước, hành động và kết quả

Một trường hợp kiểm thử có thể được mô tả theo cấu trúc:

- **Tiền điều kiện (precondition):** trạng thái hệ thống, dữ liệu và quyền trước khi thực hiện.
- **Dữ liệu đầu vào:** giá trị được cung cấp hoặc sự kiện được tạo.
- **Hành động:** thao tác của người dùng hoặc hệ thống.
- **Kết quả mong đợi (expected result):** trạng thái, phản hồi và tác dụng phụ cần quan sát.
- **Bằng chứng:** nguồn dùng để xác minh kết quả.

Ví dụ:

| Thành phần | Nội dung |
|---|---|
| Tiền điều kiện | Người dùng đã đăng nhập; khung giờ còn một chỗ |
| Dữ liệu | Ngày và khung giờ hợp lệ |
| Hành động | Người dùng xác nhận đặt lịch |
| Kết quả mong đợi | Một lịch được tạo; số chỗ còn lại giảm đúng một; người dùng nhận xác nhận |
| Bằng chứng | Bản ghi lịch, số chỗ còn lại và thông báo xác nhận |

Cấu trúc này giúp trường hợp kiểm thử có thể lặp lại và giúp người khác hiểu vì sao một kết quả được xem là đạt.

### 3.3. Chọn kỹ thuật thiết kế kiểm thử phù hợp

Một số kỹ thuật thường hữu ích khi chuyển yêu cầu thành trường hợp kiểm thử:

**Phân vùng tương đương (equivalence partitioning):** chia dữ liệu thành các nhóm được kỳ vọng xử lý giống nhau, rồi chọn đại diện cho từng nhóm. Với tuổi được phép đăng ký từ 18 đến 65, có thể xét nhóm dưới 18, từ 18 đến 65 và trên 65. Cần kiểm tra đại diện trong từng nhóm và bổ sung trường hợp biên.

**Phân tích giá trị biên (boundary value analysis):** tập trung vào các giá trị tại hoặc gần ranh giới, nơi lỗi thường xuất hiện. Với giới hạn 18 đến 65, cần xem xét 17, 18, 19, 64, 65 và 66 tùy quy tắc bao gồm hai đầu mút.

**Bảng quyết định (decision table):** dùng khi kết quả phụ thuộc vào nhiều điều kiện kết hợp. Ví dụ, áp dụng ưu đãi có thể phụ thuộc vào nhóm khách hàng, trạng thái mã, giá trị đơn và thời hạn. Bảng giúp phát hiện tổ hợp điều kiện bị bỏ sót.

**Chuyển trạng thái (state transition):** dùng khi hành vi phụ thuộc trạng thái hiện tại và sự kiện. Ví dụ, đơn hàng chỉ được hủy trong một số trạng thái; cần kiểm tra cả chuyển đổi hợp lệ và chuyển đổi bị cấm.

**Use case hoặc luồng người dùng:** dùng khi cần xác nhận hành trình đầu cuối gồm nhiều tác nhân và bước tương tác.

**Kiểm thử dựa trên rủi ro:** ưu tiên các quy tắc có hậu quả lớn, khả năng xảy ra cao hoặc khó phát hiện.

Các kỹ thuật có thể kết hợp. Không cần áp dụng mọi kỹ thuật cho mọi yêu cầu; chọn kỹ thuật giúp bao phủ quy tắc và rủi ro với chi phí phù hợp.

### 3.4. Bao phủ các nhóm tình huống

Với mỗi yêu cầu, xem xét:

- Luồng thành công với dữ liệu hợp lệ.
- Dữ liệu không hợp lệ, thiếu hoặc sai định dạng.
- Giá trị biên và giới hạn.
- Điều kiện không thỏa mãn hoặc quyền không đủ.
- Trạng thái trước và sau thao tác.
- Xử lý lỗi, timeout và thử lại.
- Yêu cầu lặp hoặc thao tác đồng thời.
- Tác động đến dữ liệu và hệ thống liên quan.
- Các thuộc tính phi chức năng được yêu cầu.

Không nên tạo số lượng trường hợp lớn chỉ để tăng con số bao phủ. Hãy bảo đảm mỗi trường hợp có mục đích rõ ràng và chứng minh được một hoặc nhiều điều kiện quan trọng.

## 4. Viết tiêu chí chấp nhận có thể xác minh

Tiêu chí chấp nhận tốt mô tả hành vi hoặc kết quả mà các bên có thể thống nhất. Nó phải đủ cụ thể để người phát triển hiểu điều cần làm và người kiểm thử biết cần quan sát điều gì.

### 4.1. Mẫu Given–When–Then

Một cách viết phổ biến là Given–When–Then:

- **Given (Cho trước):** bối cảnh hoặc tiền điều kiện.
- **When (Khi):** hành động hoặc sự kiện xảy ra.
- **Then (Thì):** kết quả mong đợi có thể quan sát.

Ví dụ:

```gherkin
Feature: Đặt lịch hẹn

  Scenario: Đặt lịch khi khung giờ còn chỗ
    Given người dùng đã đăng nhập
      And khung giờ còn ít nhất một chỗ
    When người dùng xác nhận đặt lịch
    Then hệ thống tạo một lịch hẹn cho người dùng
      And số chỗ còn lại giảm đúng một
      And người dùng nhận được xác nhận đặt lịch
```

Cách viết này giúp tách bối cảnh, hành động và kết quả. Tuy nhiên, không nên biến mọi chi tiết giao diện hoặc thao tác kỹ thuật thành tiêu chí chấp nhận nếu chúng không liên quan đến kết quả cần xác nhận. Tiêu chí nên tập trung vào hành vi có ý nghĩa với người dùng và nghiệp vụ.

### 4.2. Tiêu chí phải có thể quan sát

“Xử lý chính xác” không cho biết cần kiểm tra dữ liệu hay trạng thái nào. Có thể diễn đạt thành:

- Tổng tiền được tính bằng giá từng mặt hàng nhân số lượng, cộng thuế và phí theo quy tắc đã thống nhất.
- Không tạo quá một giao dịch thu tiền cho cùng một yêu cầu nghiệp vụ.
- Khi yêu cầu bị từ chối, dữ liệu đơn hàng không chuyển sang trạng thái đã xác nhận.
- Người dùng không có quyền nhận phản hồi từ chối và không đọc được dữ liệu nhạy cảm.

Kết quả có thể quan sát ở giao diện, API, cơ sở dữ liệu, log, sự kiện hoặc hệ thống bên ngoài. Chọn nguồn dữ liệu có thẩm quyền cho từng kết quả. Một thông báo hiển thị thành công không nhất thiết chứng minh dữ liệu đã được lưu hoặc giao dịch đã được đối soát.

### 4.3. Tránh tiêu chí quá chi tiết hoặc quá chung chung

Tiêu chí quá chung khiến cách hiểu khác nhau. Tiêu chí quá chi tiết có thể khóa chặt thiết kế nội bộ và khiến kiểm thử dễ gãy khi giao diện thay đổi dù hành vi nghiệp vụ vẫn đúng.

Ví dụ:

- Quá chung: “Người dùng tìm được đơn hàng.”
- Tập trung vào hành vi: “Người dùng có quyền có thể tìm đơn theo mã đơn hợp lệ và xem các trường thông tin được phép.”
- Quá gắn với triển khai: “Nhấn nút màu xanh ở tọa độ bên phải, hệ thống gọi hàm X rồi cập nhật phần tử DOM Y.”

Tiêu chí nên mô tả điều người dùng hoặc hệ thống cần nhận được, cùng điều kiện nghiệp vụ cần thỏa mãn. Chi tiết triển khai thuộc thiết kế hoặc bước kiểm thử phù hợp, trừ khi nó là một yêu cầu giao diện cụ thể.

### 4.4. Tiêu chí cho trường hợp âm và ngoại lệ

Tiêu chí chấp nhận không chỉ mô tả thành công. Cần nêu hệ thống phải xử lý thế nào khi điều kiện không đạt.

Ví dụ với đặt lịch:

| Tình huống | Tiêu chí chấp nhận |
|---|---|
| Khung giờ đã hết chỗ | Không tạo lịch; người dùng nhận thông báo phù hợp và có thể chọn khung giờ khác |
| Người dùng chưa đăng nhập | Yêu cầu xác thực trước khi tạo lịch |
| Người dùng không có quyền đặt cho đối tượng được chọn | Từ chối thao tác và không thay đổi dữ liệu |
| Hai người cùng đặt chỗ cuối cùng | Chỉ một yêu cầu được xác nhận; số chỗ không âm |
| Dịch vụ lưu lịch tạm thời không sẵn sàng | Không thông báo đặt thành công khi chưa có xác nhận lưu; trạng thái có thể được đối soát theo thiết kế |

Các tiêu chí này làm rõ hành vi an toàn khi lỗi xảy ra và giúp tránh trạng thái nửa hoàn tất.

### 4.5. Tiêu chí phi chức năng

Tiêu chí phi chức năng cần điều kiện đo rõ ràng. Ví dụ:

- Trong điều kiện tải đã mô tả, 95% yêu cầu tìm kiếm hoàn tất trong thời gian không vượt ngưỡng đã thống nhất.
- Người dùng không có quyền không thể đọc dữ liệu của người khác qua giao diện hoặc API.
- Sau khi một nút dịch vụ phụ thuộc bị lỗi, hệ thống phục hồi theo thời hạn và quy tắc đã xác định.
- Giao diện hỗ trợ các trình duyệt và kích thước màn hình trong danh sách được phê duyệt.

Khi viết tiêu chí đo lường, cần xác định môi trường, dữ liệu, số lượng mẫu, thời gian đo, ngưỡng đạt và công cụ hoặc nguồn bằng chứng. Nếu thiếu điều kiện đo, hai lần kiểm thử có thể cho kết quả không thể so sánh.

## 5. Xây dựng ma trận truy vết yêu cầu và kiểm thử

Truy vết (traceability) cho biết mỗi yêu cầu được kiểm tra ở đâu và bằng chứng nào chứng minh kết quả. Ma trận truy vết giúp phát hiện yêu cầu chưa có kiểm thử, kiểm thử không có căn cứ hoặc thay đổi chưa được đánh giá đầy đủ.

### 5.1. Liên kết yêu cầu, tiêu chí và trường hợp kiểm thử

Một chuỗi truy vết đơn giản:

```
Nguồn yêu cầu
    -> Yêu cầu (REQ)
        -> Tiêu chí chấp nhận (AC)
            -> Trường hợp kiểm thử (TC)
                -> Kết quả chạy và bằng chứng
```

Ví dụ:

| Requirement ID | Acceptance Criteria ID | Test Case ID | Mục tiêu kiểm tra |
|---|---|---|---|
| REQ-BOOK-01 | AC-01 | TC-001 | Đặt lịch thành công khi còn chỗ |
| REQ-BOOK-01 | AC-02 | TC-002 | Từ chối khi khung giờ đã hết chỗ |
| REQ-BOOK-01 | AC-03 | TC-003 | Chỉ một yêu cầu được xác nhận khi đặt đồng thời |
| REQ-BOOK-02 | AC-04 | TC-004 | Người không có quyền không thể xem lịch riêng tư |

Một yêu cầu có thể liên kết đến nhiều tiêu chí; một tiêu chí có thể cần nhiều trường hợp kiểm thử. Một trường hợp cũng có thể bao phủ nhiều tiêu chí nếu mục tiêu và kết quả đều được ghi rõ.

### 5.2. Truy vết hai chiều

- **Từ yêu cầu đến kiểm thử:** giúp phát hiện yêu cầu chưa có trường hợp kiểm thử hoặc chưa có bằng chứng.
- **Từ kiểm thử về yêu cầu:** giúp xác định trường hợp kiểm thử nào không còn căn cứ, đã lỗi thời hoặc đang kiểm tra ngoài phạm vi dự kiến.

Truy vết hai chiều đặc biệt hữu ích khi yêu cầu thay đổi. Nhóm có thể tìm các kiểm thử liên quan, đánh giá ảnh hưởng và cập nhật kế hoạch.

### 5.3. Mẫu ma trận truy vết

| Trường | Ý nghĩa |
|---|---|
| Requirement ID | Mã yêu cầu duy nhất |
| Nguồn yêu cầu | Tài liệu, câu chuyện người dùng, hợp đồng hoặc quyết định |
| Mô tả yêu cầu | Nội dung ngắn gọn, có phạm vi |
| Acceptance Criteria ID | Mã tiêu chí chấp nhận |
| Test Case ID | Mã trường hợp kiểm thử |
| Mức ưu tiên | Mức quan trọng theo nghiệp vụ và rủi ro |
| Loại kiểm thử | Chức năng, tích hợp, hồi quy, hiệu năng, bảo mật... |
| Trạng thái | Chưa thiết kế, sẵn sàng, đã chạy, đạt, không đạt, bị chặn |
| Bằng chứng | Báo cáo, log, dữ liệu hoặc tham chiếu kết quả |
| Phiên bản | Phiên bản yêu cầu hoặc sản phẩm được xác nhận |

Mã định danh cần ổn định và không tái sử dụng cho một yêu cầu khác. Khi nội dung thay đổi đáng kể, ghi lại phiên bản hoặc lịch sử để biết kết quả kiểm thử đang áp dụng cho nội dung nào.

### 5.4. Đo độ bao phủ yêu cầu

Có thể dùng các chỉ số đơn giản:

[
\text{Requirement Coverage} =
\frac{\text{Số yêu cầu có kiểm thử phù hợp}}
{\text{Tổng số yêu cầu trong phạm vi}} \times 100\%
]

[
\text{Acceptance Criteria Coverage} =
\frac{\text{Số tiêu chí có ít nhất một kiểm thử}}
{\text{Tổng số tiêu chí trong phạm vi}} \times 100\%
]

Các tỷ lệ này chỉ cho biết mức liên kết, không chứng minh kiểm thử có chất lượng hoặc đủ sâu. Một tiêu chí có thể có liên kết đến một trường hợp nhưng trường hợp đó không kiểm tra đủ nhánh quan trọng. Vì vậy, cần kết hợp rà soát nội dung, rủi ro và bằng chứng thực tế.

## 6. Tổ chức thực hiện kiểm thử dựa trên yêu cầu

### 6.1. Trước khi thực thi

Người kiểm thử nên:

1. Xác định phiên bản và nguồn yêu cầu đang có hiệu lực.
2. Đọc yêu cầu, tiêu chí chấp nhận và các quy tắc liên quan.
3. Làm rõ các từ ngữ mơ hồ, mâu thuẫn và thông tin còn thiếu.
4. Xác định phạm vi, ưu tiên và rủi ro.
5. Thiết kế trường hợp kiểm thử, dữ liệu và kết quả mong đợi.
6. Kiểm tra điều kiện môi trường, quyền truy cập và dữ liệu.
7. Rà soát truy vết để bảo đảm yêu cầu quan trọng có kiểm thử.

### 6.2. Trong khi thực thi

Với mỗi trường hợp:

- Xác nhận tiền điều kiện và phiên bản đang kiểm thử.
- Ghi lại dữ liệu, thao tác và cấu hình liên quan.
- Quan sát kết quả thực tế tại nguồn phù hợp.
- So sánh với tiêu chí và kết quả mong đợi đã thống nhất.
- Lưu bằng chứng đủ để tái hiện và đánh giá.
- Ghi rõ sai lệch, điều kiện xảy ra và mức độ ảnh hưởng.

Một trường hợp chỉ được đánh dấu đạt khi bằng chứng cho thấy kết quả đáp ứng tiêu chí trong phạm vi đã nêu. Nếu môi trường không sẵn sàng, dữ liệu thiếu hoặc dịch vụ phụ thuộc lỗi, hãy ghi trạng thái bị chặn hoặc không thể kết luận thay vì xem như đạt.

### 6.3. Khi phát hiện lỗi

Báo cáo lỗi cần liên kết với yêu cầu và tiêu chí liên quan. Nội dung nên có:

- Mã lỗi và mức độ ưu tiên.
- Requirement ID và Acceptance Criteria ID.
- Phiên bản, môi trường và dữ liệu.
- Các bước tái hiện.
- Kết quả mong đợi và kết quả thực tế.
- Bằng chứng như ảnh chụp, log, phản hồi API hoặc bản ghi.
- Tác động nghiệp vụ và phạm vi có thể bị ảnh hưởng.

Liên kết này giúp nhóm hiểu lỗi vi phạm điều gì, có cần điều chỉnh yêu cầu hay không và cần chạy lại những kiểm thử nào sau khi sửa.

### 6.4. Kết thúc và báo cáo

Báo cáo nên thể hiện:

- Tổng số yêu cầu và tiêu chí trong phạm vi.
- Số lượng đã có kiểm thử và đã thực thi.
- Kết quả đạt, không đạt, bị chặn hoặc chưa chạy.
- Các yêu cầu có rủi ro cao chưa được xác nhận.
- Lỗi còn mở và ảnh hưởng nghiệp vụ.
- Phạm vi đã kiểm thử, phạm vi loại trừ và lý do.
- Rủi ro còn lại cùng người có thẩm quyền chấp nhận.

Không nên chỉ báo cáo một tỷ lệ đạt chung. Một yêu cầu quan trọng chưa kiểm thử có thể có ý nghĩa lớn hơn nhiều trường hợp ít rủi ro đã đạt.

## 7. Quản lý thay đổi yêu cầu và tiêu chí chấp nhận

Yêu cầu có thể thay đổi khi người dùng phản hồi, quy định cập nhật hoặc nhóm phát hiện thông tin mới. Mỗi thay đổi cần được đánh giá để tránh kiểm thử theo phiên bản yêu cầu cũ.

### 7.1. Phân tích ảnh hưởng của thay đổi

Khi yêu cầu hoặc tiêu chí thay đổi:

1. Ghi nhận nội dung và lý do thay đổi.
2. Xác định yêu cầu, tiêu chí và quy tắc liên quan.
3. Tìm các trường hợp kiểm thử đang truy vết đến nội dung cũ.
4. Đánh giá ảnh hưởng đến dữ liệu, tích hợp, quy trình và hồi quy.
5. Cập nhật kết quả mong đợi, dữ liệu và môi trường nếu cần.
6. Xác nhận lại với người có thẩm quyền.
7. Ghi phiên bản và thời điểm áp dụng.

Không sửa tiêu chí một cách âm thầm sau khi kiểm thử thất bại. Nếu kỳ vọng thay đổi, cần ghi nhận đó là thay đổi yêu cầu hoặc quyết định nghiệp vụ, sau đó đánh giá lại kết quả đã có.

### 7.2. Tránh kiểm thử theo tài liệu lỗi thời

Mỗi lần chạy cần biết đang dùng phiên bản yêu cầu nào. Nếu yêu cầu được sửa trong lúc kiểm thử, cần xác định trường hợp nào phải thiết kế lại hoặc chạy lại. Kết quả trước đó có thể vẫn có giá trị với phiên bản cũ nhưng không chứng minh phiên bản mới đáp ứng yêu cầu.

### 7.3. Quản lý tiêu chí chấp nhận bị bỏ sót

Nếu một tiêu chí được bổ sung sau khi tính năng đã phát triển:

- Xác định tiêu chí mới có làm thay đổi hành vi hiện tại không.
- Đánh giá dữ liệu và thiết kế có đáp ứng được không.
- Bổ sung kiểm thử và cập nhật ma trận truy vết.
- Xác định có cần hồi quy các luồng liên quan không.
- Ghi rõ quyết định về phạm vi và mốc hoàn thành.

## 8. Vai trò và phối hợp giữa các bên

Kiểm thử dựa trên yêu cầu cần sự phối hợp. Người kiểm thử có thể phát hiện điểm mơ hồ nhưng không nên tự quyết định quy tắc nghiệp vụ thay cho người có thẩm quyền.

| Vai trò | Trách nhiệm thường gặp |
|---|---|
| Product Owner / chủ sở hữu sản phẩm | Làm rõ nhu cầu, ưu tiên và chấp nhận kết quả theo mục tiêu sản phẩm |
| Chuyên gia nghiệp vụ | Giải thích quy trình, quy tắc và ngoại lệ |
| Business Analyst | Phân tích, ghi nhận, làm rõ và quản lý yêu cầu |
| Developer | Phân tích khả thi, triển khai và giải thích hành vi kỹ thuật |
| Tester / QA | Đánh giá khả năng kiểm thử, thiết kế trường hợp, thực thi và cung cấp bằng chứng |
| Kiến trúc sư / chủ sở hữu tích hợp | Làm rõ phụ thuộc, hợp đồng và tác động hệ thống |
| Vận hành / bảo mật / tuân thủ | Xác nhận yêu cầu về môi trường, vận hành, bảo mật và nghĩa vụ áp dụng |

Một buổi rà soát yêu cầu có thể diễn ra trước khi phát triển. Người kiểm thử đưa ra tình huống âm, dữ liệu biên, câu hỏi về bằng chứng và rủi ro. Nhóm thống nhất cách hiểu và cập nhật tiêu chí trước khi chi phí sửa đổi tăng lên.

## 9. Ví dụ tổng hợp: yêu cầu đặt lại mật khẩu

Giả sử yêu cầu là: “Người dùng có thể đặt lại mật khẩu khi quên mật khẩu.”

### 9.1. Phân rã yêu cầu

Các quy tắc cần làm rõ:

- Người dùng khởi tạo yêu cầu bằng thông tin định danh nào?
- Hệ thống gửi liên kết hoặc mã xác minh qua kênh nào?
- Liên kết hoặc mã có thời hạn bao lâu?
- Một liên kết có thể sử dụng bao nhiêu lần?
- Mật khẩu mới phải đáp ứng chính sách nào?
- Các phiên đăng nhập cũ được xử lý ra sao?
- Hệ thống phản hồi thế nào nếu email không tồn tại?
- Có giới hạn số lần yêu cầu để giảm lạm dụng không?

### 9.2. Viết tiêu chí chấp nhận

| ID | Tiêu chí |
|---|---|
| AC-01 | Người dùng có thể yêu cầu đặt lại mật khẩu từ luồng quên mật khẩu |
| AC-02 | Hệ thống gửi thông tin đặt lại qua kênh đã đăng ký khi yêu cầu hợp lệ |
| AC-03 | Liên kết hoặc mã hết hạn không thể được sử dụng |
| AC-04 | Liên kết hoặc mã đã dùng không thể sử dụng lần thứ hai |
| AC-05 | Mật khẩu mới phải đáp ứng chính sách đã công bố |
| AC-06 | Sau khi đặt lại thành công, người dùng đăng nhập được bằng mật khẩu mới |
| AC-07 | Hành vi với phiên đăng nhập cũ tuân theo chính sách bảo mật |
| AC-08 | Phản hồi công khai không tiết lộ thông tin tài khoản nếu chính sách yêu cầu tránh dò tìm tài khoản |

### 9.3. Chuyển thành trường hợp kiểm thử

| Test Case | Tiền điều kiện và hành động | Kết quả mong đợi |
|---|---|---|
| TC-01 | Người dùng hợp lệ yêu cầu đặt lại | Yêu cầu được tiếp nhận và thông tin đặt lại được gửi |
| TC-02 | Mở liên kết còn hạn và đặt mật khẩu hợp lệ | Mật khẩu được cập nhật; đăng nhập bằng mật khẩu mới thành công |
| TC-03 | Mở liên kết đã hết hạn | Hệ thống từ chối và yêu cầu tạo liên kết mới |
| TC-04 | Dùng lại liên kết đã sử dụng | Hệ thống từ chối; mật khẩu không bị thay đổi lần nữa |
| TC-05 | Nhập mật khẩu không đáp ứng chính sách | Không cập nhật mật khẩu; hiển thị hướng dẫn phù hợp |
| TC-06 | Gửi yêu cầu với địa chỉ không tồn tại | Phản hồi công khai tuân theo chính sách và không làm lộ trạng thái tài khoản |
| TC-07 | Gửi yêu cầu liên tục vượt giới hạn | Hệ thống áp dụng cơ chế giới hạn đã thống nhất |
| TC-08 | Đặt lại mật khẩu khi có phiên đăng nhập cũ | Các phiên cũ được xử lý theo chính sách bảo mật |

Một số kết quả trong ví dụ cần được Product Owner hoặc chủ sở hữu bảo mật xác nhận trước khi dùng làm tiêu chí chính thức. Ví dụ này cho thấy cách biến yêu cầu ngắn thành các quy tắc, tiêu chí và kiểm thử có thể truy vết.

## 10. Những sai lầm thường gặp

1. **Viết kiểm thử từ mô tả quá chung:** tạo kết quả mong đợi dựa trên cách hiểu cá nhân thay vì làm rõ yêu cầu.
2. **Chỉ kiểm tra luồng thành công:** bỏ qua điều kiện từ chối, dữ liệu biên, quyền hạn và phục hồi.
3. **Nhầm tiêu chí chấp nhận với bước thao tác:** mô tả cách nhấn nút nhưng không nêu kết quả nghiệp vụ cần đạt.
4. **Không xác định nguồn dữ liệu chuẩn:** dựa vào một thông báo giao diện dù trạng thái hoặc dữ liệu ở hệ thống khác chưa đúng.
5. **Thiếu truy vết:** không biết yêu cầu nào chưa được kiểm tra hoặc trường hợp nào không còn căn cứ.
6. **Dùng tỷ lệ bao phủ như bằng chứng chất lượng:** tỷ lệ liên kết cao nhưng trường hợp kiểm thử có thể không đủ sâu hoặc không có bằng chứng.
7. **Tự đặt ngưỡng:** chuyển từ “nhanh” thành một con số mà chưa được người có thẩm quyền thống nhất.
8. **Không quản lý phiên bản yêu cầu:** chạy kiểm thử theo tài liệu cũ và báo cáo kết quả cho phiên bản mới.
9. **Sửa tiêu chí sau khi thất bại mà không ghi nhận:** làm mất dấu vết giữa yêu cầu ban đầu và quyết định mới.
10. **Không gắn lỗi với yêu cầu:** khiến việc đánh giá tác động và kiểm thử lại trở nên khó khăn.

## 11. Checklist trước khi xác nhận yêu cầu và tiêu chí chấp nhận

- [ ] Đã xác định nguồn, phiên bản và người chịu trách nhiệm của yêu cầu.
- [ ] Yêu cầu có phạm vi, đối tượng và mục tiêu rõ ràng.
- [ ] Các từ ngữ mơ hồ, mâu thuẫn và thông tin còn thiếu đã được làm rõ hoặc ghi nhận.
- [ ] Đã phân rã yêu cầu thành quy tắc và điều kiện có thể kiểm tra.
- [ ] Tiêu chí chấp nhận mô tả kết quả quan sát được, có cả nhánh âm và ngoại lệ cần thiết.
- [ ] Yêu cầu phi chức năng có ngưỡng, điều kiện đo và nguồn bằng chứng.
- [ ] Đã chọn kỹ thuật thiết kế kiểm thử phù hợp với quy tắc và dữ liệu.
- [ ] Mỗi yêu cầu và tiêu chí quan trọng có liên kết đến trường hợp kiểm thử.
- [ ] Trường hợp kiểm thử có tiền điều kiện, dữ liệu, hành động và kết quả mong đợi.
- [ ] Đã xác định nguồn dữ liệu chuẩn và bằng chứng để kết luận.
- [ ] Đã có quy trình cập nhật yêu cầu và đánh giá ảnh hưởng khi thay đổi.
- [ ] Báo cáo thể hiện rõ kết quả, phạm vi chưa kiểm thử và rủi ro còn lại.

Kiểm thử dựa trên yêu cầu giúp xác nhận sản phẩm đáp ứng điều đã được thống nhất; kiểm thử dựa trên tiêu chí chấp nhận biến kỳ vọng thành điều kiện có thể quan sát và đánh giá. Khi yêu cầu rõ ràng, tiêu chí có thể xác minh và truy vết được duy trì, nhóm có căn cứ để thiết kế kiểm thử, báo cáo kết quả và đưa ra quyết định về chất lượng sản phẩm.
