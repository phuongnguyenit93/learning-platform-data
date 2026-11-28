# Evidence collection: thu thập bằng chứng cho yêu cầu bảo mật

## 1. Bằng chứng giúp trả lời câu hỏi nào?

Trong quản lý rủi ro và tuân thủ, một yêu cầu bảo mật cần đi kèm câu trả lời cho câu hỏi: **Dựa vào đâu để kết luận hệ thống đã đáp ứng yêu cầu, trong phạm vi nào và tại thời điểm nào?**

Evidence collection là quá trình xác định, thu thập và quản lý bằng chứng để hỗ trợ một kết luận có thể kiểm tra lại. Với đặc tả yêu cầu bảo mật, chuỗi liên kết cần được giữ rõ ràng:

**Rủi ro → yêu cầu → biện pháp kiểm soát → cách kiểm chứng → bằng chứng → kết luận và quyết định xử lý.**

Ví dụ, yêu cầu “bảo vệ dữ liệu khách hàng” chưa cho biết phải thu thập gì. Khi yêu cầu được viết thành “API tải bản xuất chỉ cho phép người dùng có quyền phù hợp trong đúng tenant truy cập đối tượng”, nhóm phát triển có thể xác định các tình huống thử, kết quả mong đợi và hồ sơ cần lưu.

Bài học tập trung vào bằng chứng phục vụ yêu cầu bảo mật trong vòng đời phát triển. Thu thập bằng chứng sau sự cố có thể đòi hỏi quy trình điều tra chuyên biệt; một gói bằng chứng kiểm thử thông thường không tự đáp ứng toàn bộ yêu cầu của công việc đó.

Sau bài học, người học có thể:

- Lập kế hoạch bằng chứng từ một yêu cầu đo được và một rủi ro cụ thể.
- Phân biệt tài liệu mô tả, kết quả quan sát và kết luận được hỗ trợ bởi bằng chứng.
- Thiết kế hồ sơ có liên kết đến phiên bản, môi trường, thời gian và người chịu trách nhiệm.
- Bảo vệ dữ liệu trong quá trình thu thập, lưu giữ và cung cấp bằng chứng.
- Xử lý kết quả thiếu, lỗi thời hoặc không đạt mà vẫn giữ được lịch sử quyết định.

## 2. Phân biệt artifact, bằng chứng và kết luận

Một artifact là sản phẩm hoặc dấu vết được tạo ra trong công việc: tài liệu thiết kế, tệp cấu hình, báo cáo kiểm thử, log, bản ghi thay đổi hay phiếu phê duyệt.

Artifact trở thành bằng chứng hữu ích khi nó được gắn với một mệnh đề cần chứng minh và có đủ ngữ cảnh để đánh giá.

| Thành phần | Ví dụ | Giá trị và giới hạn |
| --- | --- | --- |
| Yêu cầu | Chỉ người có quyền `customer.export` mới được tạo bản xuất của tenant mình | Nêu hành vi bắt buộc; chưa chứng minh việc triển khai |
| Artifact thiết kế | Sơ đồ điểm kiểm tra phân quyền | Giải thích cách dự kiến thực hiện; chưa chứng minh hệ thống đang chạy đúng |
| Artifact kiểm thử | Báo cáo thử tải bản xuất của tenant khác | Cho biết một lần chạy thử; cần biết bản build, môi trường, dữ liệu và assertion |
| Bằng chứng có ngữ cảnh | Báo cáo trên gắn với mã yêu cầu, test case, phiên bản và kết quả kiểm tra trạng thái đối tượng | Hỗ trợ đánh giá hành vi trong phạm vi lần chạy đó |
| Kết luận | Build được thử từ chối các trường hợp truy cập chéo tenant đã liệt kê | Chỉ khẳng định phần đã quan sát; chưa bao phủ mọi đường truy cập |
| Quyết định rủi ro | Cho phép phát hành khi các điều kiện nghiệm thu đạt, hoặc chấp nhận một ngoại lệ có thời hạn | Cần người có thẩm quyền; không được suy ra chỉ từ một báo cáo màu xanh |

Một pipeline thành công chỉ chứng minh những công việc mà pipeline đó thực sự chạy và những assertion mà nó thực sự kiểm tra. Nếu pipeline không thử đường tải tệp trực tiếp, kết quả thành công không chứng minh đường tải đó đã được phân quyền đúng.

Tương tự, ảnh chụp màn hình một ô “Enable encryption” hỗ trợ nhận biết cấu hình hiển thị tại thời điểm chụp. Nó chưa đủ để kết luận mọi bản sao dữ liệu, bản sao lưu và đường truyền đều được mã hóa.

## 3. Xuất phát từ yêu cầu và rủi ro

### 3.1. Viết mệnh đề có thể kiểm chứng

Một yêu cầu tốt cho việc thu thập bằng chứng cần làm rõ:

1. **Đối tượng và phạm vi:** API, dữ liệu, môi trường, tenant hoặc vai trò nào.
2. **Điều kiện:** hành động nào, trạng thái phiên nào và giả định nào.
3. **Hành vi bắt buộc:** cho phép, từ chối, ghi nhận, xóa hoặc phục hồi điều gì.
4. **Ngưỡng:** thời gian, dung lượng, tỷ lệ hoặc điều kiện đạt khi có ý nghĩa.
5. **Cách kiểm chứng:** quan sát ở đâu và dùng tiêu chí gì để kết luận.

Ví dụ:

> SEC-EXP-01: Khi một người dùng đã xác thực thuộc tenant B yêu cầu tải bản xuất thuộc tenant A, dịch vụ phải từ chối và không trả nội dung bản xuất, kể cả khi người dùng có quyền xuất dữ liệu trong tenant B.

Mệnh đề này xác định rõ đối tượng, điều kiện và hành vi. Bằng chứng cần bao gồm thông tin về hai tenant, quyền của người dùng, chủ sở hữu bản xuất và các assertion trên phản hồi. Nếu phản hồi trả mã lỗi nhưng vẫn chứa dữ liệu nhạy cảm, kiểm thử phải không đạt.

Nếu tổ chức còn yêu cầu che giấu sự tồn tại của đối tượng, phải đặc tả riêng hành vi phản hồi đó và kiểm chứng nó. Không tự coi một mã HTTP cụ thể là chính sách bắt buộc cho mọi hệ thống.

### 3.2. Xác định bằng chứng đủ cho rủi ro nào

Mức độ đầu tư vào bằng chứng phụ thuộc vào tác động và khả năng xảy ra của rủi ro, phạm vi thay đổi và quyết định cần đưa ra.

- Với chức năng ít nhạy cảm, một báo cáo kiểm thử có truy vết cùng phê duyệt thay đổi có thể đáp ứng nhu cầu nội bộ.
- Với khả năng tải dữ liệu khách hàng hàng loạt, cần xem xét thêm các đường truy cập khác, phân quyền phía máy chủ, cấu hình triển khai và quan sát vận hành phù hợp.
- Với phục hồi dữ liệu quan trọng, trạng thái “backup thành công” cần được bổ sung bằng lần thử khôi phục và kiểm tra dữ liệu sau khôi phục.

Đây là cách chọn mức bảo đảm theo rủi ro. Nó không tạo ra bảo đảm tuyệt đối và không thay thế tiêu chí của bên đánh giá hoặc nghĩa vụ áp dụng cho tổ chức.

### 3.3. Phân biệt thời điểm và khoảng thời gian

Một yêu cầu có thể nói về trạng thái tại một thời điểm hoặc về hoạt động trong một khoảng thời gian:

| Mệnh đề cần chứng minh | Ví dụ bằng chứng phù hợp |
| --- | --- |
| Chính sách đã được thiết kế và phê duyệt | Phiên bản chính sách, người phê duyệt, phạm vi và ngày hiệu lực |
| Build ứng viên đáp ứng các tình huống phân quyền | Kết quả test gắn với build đó và danh sách tình huống đã chạy |
| Cấu hình triển khai đang phù hợp | Snapshot cấu hình hiệu lực, định danh môi trường và thời điểm lấy |
| Hoạt động rà soát quyền được thực hiện trong kỳ | Các bản ghi rà soát theo kỳ, phạm vi tài khoản và cách xử lý phát hiện |
| Quy trình phục hồi đáp ứng ngưỡng đã chọn | Hồ sơ diễn tập, thời điểm đo, trạng thái dữ liệu khôi phục và tiêu chí nghiệm thu |

Một cấu hình đúng vào cuối kỳ không đủ để kết luận nó luôn đúng trong cả kỳ. Khi lấy mẫu, phải ghi tổng thể, cách chọn mẫu, phần không được lấy mẫu và giới hạn của kết luận.

## 4. Lập kế hoạch bằng chứng trước khi triển khai

Kế hoạch bằng chứng nên là một phần của việc hoàn thiện yêu cầu và tiêu chí nghiệm thu. Khi đợi đến sát ngày đánh giá mới thu thập, nhóm thường thiếu dữ liệu gốc, không biết phiên bản nào đã được thử hoặc phải dùng log chứa thông tin nhạy cảm không cần thiết.

Mỗi mục trong kế hoạch nên có các thông tin sau:

| Trường | Câu hỏi cần trả lời |
| --- | --- |
| Evidence ID | Bằng chứng được định danh thế nào để truy vết ổn định? |
| Risk ID và Requirement ID | Bằng chứng phục vụ rủi ro và yêu cầu nào? |
| Mệnh đề kiểm chứng | Chính xác điều gì cần được chứng minh? |
| Nguồn | CI, dịch vụ, kho cấu hình, hệ thống danh tính hay hồ sơ phê duyệt nào? |
| Phương pháp | Kiểm thử, trích xuất cấu hình, quan sát, diễn tập hay rà soát? |
| Phạm vi | Phiên bản, môi trường, tenant, đường truy cập, kỳ báo cáo và mẫu nào? |
| Tiêu chí đạt | Assertion, ngưỡng đo hoặc điều kiện nghiệm thu nào? |
| Người chịu trách nhiệm | Ai thu thập, ai rà soát và ai quyết định khi có khoảng trống? |
| Thời điểm và điều kiện làm mới | Thu khi nào, thay đổi nào khiến bằng chứng phải được lấy lại? |
| Phân loại và quyền truy cập | Hồ sơ có dữ liệu nhạy cảm gì, ai được xem hoặc xuất? |
| Lưu giữ và hủy | Giữ trong bao lâu theo chính sách áp dụng, khi nào được hủy? |
| Giới hạn | Dữ liệu hoặc hành vi nào chưa được quan sát? |

Không có một thời hạn lưu giữ hay chu kỳ làm mới duy nhất đúng cho tất cả hệ thống. Các giá trị này phải được chọn từ nhu cầu kiểm chứng, rủi ro và chính sách hoặc nghĩa vụ đã được xác định cho phạm vi cụ thể.

Cần có điều kiện làm mới theo sự kiện, chẳng hạn:

- Thay đổi cơ chế cấp quyền, middleware xác thực hoặc cách xác định tenant.
- Thay đổi đường tải tệp, cấu hình lưu trữ, chính sách khóa hoặc pipeline triển khai.
- Thay đổi phụ thuộc ảnh hưởng đến biện pháp kiểm soát đang được chứng minh.
- Phát hiện sự cố, lỗi kiểm thử, sai lệch cấu hình hoặc khoảng trống quan sát.

Một báo cáo mới về thời gian vẫn có thể không còn phù hợp nếu nó được tạo trước thay đổi quan trọng.

## 5. Ví dụ xuyên suốt: xuất dữ liệu khách hàng trong hệ thống nhiều tenant

### 5.1. Bối cảnh và mô hình đe dọa

Một dịch vụ cho phép nhân viên được cấp quyền tạo và tải bản xuất dữ liệu khách hàng của doanh nghiệp mình. Mỗi doanh nghiệp là một tenant.

Các tình huống rủi ro được xem xét:

- Người dùng có quyền ở tenant B đoán được mã bản xuất của tenant A.
- Một công việc chạy nền nhận yêu cầu hợp lệ nhưng truy vấn dữ liệu sai tenant.
- Người dùng đã bị thu hồi quyền tiếp tục tải dữ liệu qua liên kết cũ.
- Log vận hành làm lộ token hoặc nội dung khách hàng.
- Nhóm không thể truy lại ai đã tải bản xuất trong phạm vi theo dõi đã đặc tả.

Đường tải có thể đi qua API hoặc cơ chế cấp quyền tải tệp riêng. Kế hoạch bằng chứng phải liệt kê các đường thực tế; chỉ thử một đường rồi kết luận cho tất cả là thiếu cơ sở.

### 5.2. Ma trận truy vết

Các ngưỡng dưới đây là giả định minh họa của hệ thống này, không phải chuẩn bắt buộc chung.

| Rủi ro | Yêu cầu bảo mật | Bằng chứng dự kiến | Tiêu chí kiểm chứng |
| --- | --- | --- | --- |
| Truy cập chéo tenant | SEC-EXP-01: chỉ được tải bản xuất đúng tenant và đúng quyền | Test cho chủ sở hữu hợp lệ, người cùng tenant thiếu quyền và người khác tenant; snapshot cấu hình liên quan | Trường hợp hợp lệ nhận đúng dữ liệu; các trường hợp bị cấm không nhận nội dung |
| Trộn dữ liệu trong công việc nền | SEC-EXP-02: mọi dòng trong bản xuất thuộc tenant của yêu cầu đã được cấp quyền | Test tích hợp với tập dữ liệu tổng hợp có dấu nhận diện theo tenant | Kết quả đúng tập bản ghi mong đợi, không chứa dấu nhận diện của tenant khác |
| Tiếp tục tải sau thu hồi quyền | SEC-EXP-03: mọi đường tải đã liệt kê từ chối yêu cầu mới chậm nhất 60 giây sau khi thao tác thu hồi được hệ thống quyền xác nhận | Kết quả thử từng đường tải với mốc thu hồi, mốc gửi yêu cầu và phản hồi | Sau ngưỡng, yêu cầu mới bị từ chối; phép đo có giới hạn sai số phù hợp |
| Log làm lộ bí mật | SEC-LOG-01: các nguồn log trong phạm vi không ghi access token hoặc nội dung bản xuất | Cấu hình logging, kiểm thử bằng marker tổng hợp và kết quả tìm kiếm trong các nguồn đã liệt kê | Có sự kiện cần thiết; không tìm thấy marker bị cấm trong phạm vi lần thử |
| Thiếu khả năng truy vết | SEC-AUD-01: hành động tạo, tải và từ chối tải có sự kiện với actor, tenant, action, object, outcome và correlation ID | Kịch bản gây sự kiện và bản ghi audit tương ứng | Mọi hành động trong kịch bản có bản ghi phù hợp và liên kết được bằng correlation ID |

Với SEC-EXP-03, cần đặc tả riêng việc xử lý luồng tải đã bắt đầu trước khi thu hồi. Quy tắc trong bảng chỉ nói về yêu cầu tải mới. Không được suy ra rằng hệ thống tự cắt mọi kết nối đang truyền dữ liệu.

Nếu một liên kết tải đã cấp vẫn có hiệu lực lâu hơn 60 giây và cơ chế tải không kiểm tra lại quyền, bằng chứng có thể chỉ ra thiết kế không đáp ứng yêu cầu. Nhóm phải điều chỉnh thiết kế, điều chỉnh yêu cầu qua quy trình phê duyệt hoặc xử lý ngoại lệ; không được làm ngơ đường tải đó.

Với phép đo thời gian, nên ưu tiên đồng hồ đơn điệu trong cùng bộ chạy thử để đo khoảng thời gian. Khi phải ghép mốc từ nhiều hệ thống, cần biết sai lệch đồng hồ và cách tính khoảng sai số. Một kết quả sát ngưỡng nhưng có sai số không được kiểm soát chưa đủ cơ sở để kết luận đạt.

### 5.3. Tiêu chí thử bằng ngôn ngữ hành vi

```gherkin
Feature: Phân quyền tải bản xuất khách hàng

  Scenario: Người có quyền ở tenant khác không được tải bản xuất
    Given bản xuất EXP-A thuộc tenant A
    And người dùng USER-B đã xác thực thuộc tenant B
    And USER-B có quyền customer.export trong tenant B
    When USER-B yêu cầu tải EXP-A
    Then yêu cầu bị từ chối theo hợp đồng API
    And phản hồi không chứa nội dung bản xuất
    And có sự kiện audit từ chối tải liên kết với lần yêu cầu đó

  Scenario: Công việc nền giữ đúng phạm vi tenant
    Given dữ liệu tổng hợp của tenant A và tenant B có marker khác nhau
    And người dùng được phép xuất dữ liệu của tenant A
    When công việc xuất dữ liệu hoàn tất
    Then bản xuất có đúng các bản ghi mong đợi của tenant A
    And bản xuất không chứa marker của tenant B
```

Các kịch bản trên là đặc tả hành vi, chưa phải bằng chứng đã chạy. Khi chuyển thành test thực thi, báo cáo phải lưu kết quả assertion, định danh bộ thử và trạng thái thực tế của lần chạy. Test bị bỏ qua hoặc chưa chạy cần được ghi nhận rõ.

## 6. Quy trình thu thập và đánh giá

### Bước 1: Chốt phạm vi và phiên bản

Xác định mã yêu cầu, bản build hoặc digest artifact, môi trường, cấu hình liên quan, đường truy cập và tập dữ liệu thử. Nếu môi trường thử khác môi trường vận hành, ghi các khác biệt có khả năng ảnh hưởng đến kết luận.

Kiểm thử trong staging cung cấp bằng chứng về staging và artifact được thử. Để sử dụng cho quyết định phát hành, cần xác nhận quan hệ giữa artifact đó với artifact được triển khai và xem xét các cấu hình chỉ tồn tại ở môi trường đích.

### Bước 2: Chuẩn bị cách quan sát

Thiết lập correlation ID, dữ liệu tổng hợp, tài khoản thử và quyền thu thập tối thiểu cần thiết. Xác định trước nguồn log và quyền truy cập, tránh tình huống test đã chạy nhưng log không được giữ hoặc không thể liên kết.

Không bật ghi toàn bộ request, response hoặc token chỉ để có “nhiều bằng chứng”. Cách quan sát phải phù hợp với yêu cầu bảo vệ dữ liệu.

### Bước 3: Thu dữ liệu gốc cùng ngữ cảnh

Thu kết quả kiểm thử, cấu hình hiệu lực và sự kiện liên quan. Lưu cả lần không đạt, lỗi hạ tầng và test bị bỏ qua. Phân biệt lỗi của công cụ thu thập với lỗi của biện pháp kiểm soát.

Thời điểm thu thập và thời điểm sự kiện xảy ra là hai trường khác nhau. Một bản ghi được xuất hôm nay có thể mô tả sự kiện xảy ra trước đó.

### Bước 4: Kiểm tra chất lượng gói thu thập

Trước khi kết luận, kiểm tra:

- Tệp có mở được, đầy đủ và liên kết đúng mã yêu cầu không?
- Báo cáo có đúng phiên bản, môi trường và thời gian đã chốt không?
- Các assertion bắt buộc có thực sự chạy không?
- Có đường truy cập, nguồn log hoặc trường hợp thất bại nào bị bỏ sót không?
- Có dữ liệu nhạy cảm cần xử lý theo chính sách trước khi chia sẻ không?
- Giới hạn và sai số có được ghi lại đủ để người khác đánh giá không?

Đây là bước kiểm tra bằng chứng của quy trình sản phẩm, không phải lý do để sửa một kết quả thất bại thành thành công.

### Bước 5: Rà soát kết quả và lập phát hiện

Người rà soát đối chiếu bằng chứng với tiêu chí đạt. Mức độc lập giữa người thu thập và người rà soát được chọn theo rủi ro và quy trình của tổ chức.

Ví dụ, “không tìm được log tải tệp qua đường trực tiếp” có thể cho thấy thiếu quan sát hoặc thiếu kiểm soát audit. Chưa được kết luận ngay rằng không có lần tải nào xảy ra.

### Bước 6: Ghi kết luận và quyết định

Tách trạng thái kiểm chứng khỏi quyết định rủi ro. Một yêu cầu có thể không đạt nhưng được chấp nhận tạm thời bởi người có thẩm quyền trong một phạm vi và thời hạn cụ thể. Khi đó trạng thái kiểm chứng vẫn là không đạt.

### Bước 7: Theo dõi thay đổi và thu lại khi cần

Liên kết gói bằng chứng với thay đổi làm nó mất hiệu lực. Giữ lịch sử các lần thu để giải thích được điều gì đã thay đổi và tại sao kết luận sau khác kết luận trước.

## 7. Chọn loại bằng chứng theo điều cần chứng minh

Các nguồn bằng chứng bổ sung cho nhau. Không nên dùng một loại hồ sơ để thay thế mọi loại kiểm chứng.

| Nhóm yêu cầu | Bằng chứng thường cần | Giới hạn phải ghi nhận |
| --- | --- | --- |
| Xác thực | Chính sách đã duyệt, cấu hình hiệu lực và test các luồng đăng nhập hoặc khôi phục liên quan | Cấu hình của nhà cung cấp danh tính chưa chứng minh ứng dụng xử lý phiên đúng |
| Phân quyền | Ma trận quyền, test cho phép và từ chối, kiểm tra ranh giới tài nguyên hoặc tenant | Kiểm tra ẩn nút trên giao diện chưa chứng minh API từ chối |
| Bảo vệ dữ liệu | Phân loại dữ liệu, cấu hình mã hóa hoặc vòng đời dữ liệu và kiểm chứng trên đường xử lý thực tế | Mã hóa một kho lưu trữ chưa chứng minh mọi bản sao đều được bảo vệ tương tự |
| Logging và audit | Đặc tả sự kiện, cấu hình thu nhận, sự kiện được tạo bằng kịch bản và truy vấn đối chiếu | Không thấy sự kiện có thể do đường thu nhận lỗi hoặc ngoài phạm vi tìm kiếm |
| Phục hồi | Hồ sơ backup, lần khôi phục, phép đo thời gian và kiểm tra dữ liệu sau khôi phục | Backup thành công chưa chứng minh khôi phục thành công |
| Quy trình quản lý rủi ro | Phát hiện, người phụ trách, quyết định, thời hạn và bằng chứng xử lý | Một phiếu đã đóng chưa chứng minh thay đổi kỹ thuật đã có hiệu lực |

Đối với yêu cầu thời gian phục hồi, bằng chứng cần nêu rõ mốc bắt đầu và kết thúc phép đo, dịch vụ nào đã được kiểm tra và trạng thái dữ liệu được chấp nhận. Khởi động được tiến trình chưa chắc đồng nghĩa người dùng đã thực hiện được chức năng quan trọng.

Đối với yêu cầu tuân thủ, ghi rõ yêu cầu nội bộ đang ánh xạ đến nghĩa vụ hoặc tiêu chí nào đã được tổ chức xác định, phạm vi áp dụng và người xác nhận cách diễn giải. Việc có một bộ log hoặc một báo cáo kiểm thử không tự chứng minh toàn bộ hệ thống tuân thủ mọi nghĩa vụ.

## 8. Chất lượng, nguồn gốc và tính toàn vẹn

### 8.1. Các chiều chất lượng cần xem xét

Một gói bằng chứng hữu ích cần được đánh giá theo nhiều chiều:

- **Liên quan:** trực tiếp hỗ trợ mệnh đề đang kiểm chứng.
- **Đủ phạm vi:** có các đường truy cập, điều kiện lỗi và mẫu cần thiết cho kết luận.
- **Đúng thời điểm:** phù hợp với phiên bản và khoảng thời gian cần đánh giá.
- **Rõ nguồn gốc:** biết nguồn, người hoặc danh tính dịch vụ thu thập, phương pháp và các bước biến đổi.
- **Toàn vẹn:** có cách phát hiện thay đổi sau khi thu và kiểm soát việc sửa hoặc thay thế.
- **Có thể diễn giải:** người rà soát hiểu được kết quả, tiêu chí, đơn vị đo và giới hạn.
- **Có thể tái kiểm chứng:** có đủ thông tin để lặp lại phép thử hoặc đối chiếu kết luận khi được phép.

Có những quan sát vận hành không thể tái tạo đúng từng sự kiện. Khi đó cần giữ định nghĩa truy vấn, nguồn dữ liệu, khoảng thời gian và cách lấy mẫu để người khác có thể kiểm tra cơ sở suy luận.

### 8.2. Hash bảo vệ điều gì?

Mã băm như SHA-256 giúp phát hiện việc nội dung tệp thay đổi so với giá trị đối chiếu đáng tin cậy. Hash không chứng minh dữ liệu trong tệp phản ánh sự thật, không tự chứng minh ai tạo tệp và không chứng minh việc thu thập đã bao phủ đủ phạm vi.

Nếu một người có thể sửa cả tệp và bản kê hash mà không để lại dấu vết, việc lưu hash cạnh tệp không tạo ra bảo đảm mạnh về chống sửa đổi. Tùy rủi ro, cần kết hợp:

- Kho lưu trữ có kiểm soát quyền và lịch sử phiên bản.
- Nhật ký truy cập, ghi và thay thế.
- Bản kê được ký hoặc được hệ thống đáng tin cậy xác nhận.
- Cơ chế giữ bất biến hoặc chính sách lưu giữ phù hợp với nhu cầu.

Chữ ký chỉ hỗ trợ xác minh nguồn ký và tính toàn vẹn khi khóa, danh tính ký và quy trình xác minh được quản lý đúng. Nó không biến một phép thử sai thành một phép thử đúng.

### 8.3. Ghi lại quá trình xử lý bằng chứng

Nếu tệp được xuất, lọc, che dữ liệu hoặc chuyển giao, cần ghi các bước có ảnh hưởng đến khả năng đánh giá:

| Sự kiện | Thông tin nên lưu |
| --- | --- |
| Thu thập | Nguồn, danh tính thu, thời điểm, phương pháp và phạm vi |
| Biến đổi | Công cụ hoặc quy tắc lọc, dữ liệu bị loại, người thực hiện và quan hệ đầu vào/đầu ra |
| Chuyển giao | Bên nhận, thời điểm và cơ sở quyền truy cập |
| Rà soát | Người rà soát, tiêu chí, kết luận và giới hạn |
| Hủy hoặc hết hạn | Lý do, phạm vi và xác nhận theo chính sách |

Mức chi tiết phải tương xứng với rủi ro. Không nên biến mọi test thông thường thành một quy trình điều tra phức tạp; cũng không được giả định hồ sơ thông thường đủ cho tình huống đòi hỏi thủ tục điều tra riêng.

## 9. Đóng gói bằng chứng có thể truy vết

Một gói bằng chứng có thể gồm bản kê, báo cáo thử, cấu hình đã được lọc phù hợp, sự kiện audit và kết luận rà soát.

Cấu trúc dưới đây chỉ là ví dụ tổ chức hồ sơ:

```text
evidence/EV-EXP-2026-0042/
  manifest.yml
  reports/export-authorization.xml
  reports/export-tenant-isolation.json
  observations/audit-events-redacted.json
  configuration/export-policy-sanitized.json
  review/conclusion.md
```

Ví dụ bản kê minh họa:

```yaml
evidenceId: EV-EXP-2026-0042
riskIds:
  - RISK-CROSS-TENANT-EXPORT
requirementIds:
  - SEC-EXP-01
  - SEC-EXP-02
claim: "Phân quyền và cô lập tenant trên các đường xuất/tải đã liệt kê"
buildDigest: "<digest của artifact thực sự được thử>"
configurationVersion: "<phiên bản cấu hình hiệu lực>"
environment: staging
runId: "<định danh lần chạy CI>"
testSuiteVersion: "<commit của bộ kiểm thử>"
collectorIdentity: "<danh tính dịch vụ thu thập>"
collectedAt: "<thời điểm UTC có múi giờ>"
observationWindow:
  start: "<mốc đầu quan sát>"
  end: "<mốc cuối quan sát>"
scope:
  paths:
    - "POST /exports"
    - "GET /exports/{id}/download"
  dataSet: "<phiên bản bộ dữ liệu tổng hợp>"
  cases:
    - "Đúng tenant và có quyền"
    - "Đúng tenant nhưng thiếu quyền"
    - "Khác tenant và có quyền tại tenant khác"
artifacts:
  - path: reports/export-authorization.xml
    sha256: "<SHA-256 của chính tệp được lưu>"
  - path: observations/audit-events-redacted.json
    sha256: "<SHA-256 của bản đã che dữ liệu được lưu>"
transformations:
  - artifact: observations/audit-events-redacted.json
    ruleVersion: "<phiên bản quy tắc che dữ liệu>"
    removedFields:
      - "Định danh trực tiếp không cần thiết cho kết luận"
limitations:
  - "Chưa bao phủ đường cấp quyền tải tệp riêng nếu triển khai bổ sung"
verificationResult: "<PASS, FAIL hoặc INCONCLUSIVE theo quy ước đã chọn>"
reviewer: "<người hoặc vai trò rà soát>"
retentionPolicyId: "<chính sách lưu giữ áp dụng>"
```

Các giá trị trong dấu `<...>` là chỗ điền, không phải dữ liệu bằng chứng thật. Nếu hệ thống thực tế có thêm đường tải tệp riêng, mục giới hạn đó là một khoảng trống cần xử lý trước khi kết luận đã đáp ứng yêu cầu bao phủ mọi đường tải.

Chỉ ghi danh sách đường dẫn tệp là chưa đủ. Các tệp phải tồn tại, mở được, liên kết đúng bản kê và được bảo vệ bằng quyền truy cập phù hợp.

## 10. Bảo vệ dữ liệu trong chính hệ thống bằng chứng

Bằng chứng bảo mật có thể chứa thông tin nhạy cảm: sơ đồ nội bộ, tên tài khoản, định danh khách hàng, chi tiết phân quyền hoặc cấu hình hạ tầng. Kho bằng chứng vì vậy cũng cần yêu cầu bảo mật riêng.

### 10.1. Giảm dữ liệu ngay từ nguồn

Ưu tiên dữ liệu tổng hợp và tài khoản thử. Chỉ thu các trường cần để chứng minh mệnh đề. Ví dụ, để chứng minh một sự kiện audit liên kết được với yêu cầu, correlation ID và một định danh actor phù hợp có thể đủ; không cần đưa nội dung toàn bộ hồ sơ khách hàng vào báo cáo.

Không thu password, access token, refresh token, khóa riêng hoặc bí mật cấu hình để chứng minh chúng “được bảo vệ”. Có thể kiểm chứng cấu hình, cách sử dụng hoặc hành vi thông qua các cơ chế không làm lộ giá trị bí mật.

Nếu phát hiện bí mật đã đi vào gói bằng chứng, xử lý theo quy trình sự cố phù hợp, bao gồm xem xét thu hồi hoặc thay thế bí mật. Che ở bản chia sẻ không xóa được việc bí mật từng bị thu hoặc lộ.

### 10.2. Phân biệt bản gốc và bản đã xử lý

Bản đã che dữ liệu cần giữ thông tin đủ để hiểu kết quả và cần có hash riêng. Không dùng hash của bản gốc làm hash của bản đã che.

Nếu chính sách yêu cầu giữ bản gốc, hạn chế quyền truy cập và liên kết bản gốc với bản chia sẻ. Nếu việc giữ bản gốc không được phép hoặc không cần thiết, không tự tạo thêm bản sao chỉ để “đủ hồ sơ”; thiết kế lại cách thu và ghi rõ giới hạn kiểm chứng.

Phép che dữ liệu không được xóa các chi tiết quyết định kết luận. Ví dụ, nếu thay mọi tenant ID thành cùng một chuỗi, người rà soát không còn đối chiếu được việc truy cập chéo tenant. Có thể dùng ánh xạ nhất quán theo phạm vi được phép, đồng thời bảo vệ bảng ánh xạ nếu có.

### 10.3. Kiểm soát truy cập và vòng đời

Quyền tạo bằng chứng, quyền đọc hồ sơ nhạy cảm, quyền rà soát và quyền chấp nhận rủi ro là các trách nhiệm khác nhau. Với rủi ro cao, xem xét tách các trách nhiệm này theo quy trình áp dụng.

Xác định rõ thời hạn lưu giữ, điều kiện gia hạn, cách xử lý yêu cầu bảo toàn hồ sơ và cách hủy khi được phép. Việc hủy phải bao gồm các bản sao thuộc phạm vi quản lý của tổ chức theo chính sách đã chọn.

## 11. Tích hợp với CI/CD và vận hành

Thu thập tự động giúp giảm thao tác thủ công và duy trì liên kết với thay đổi phần mềm. Một luồng triển khai có thể thực hiện:

1. Đọc danh sách yêu cầu và test case cần áp dụng cho bản phát hành.
2. Chạy kiểm thử trên artifact ứng viên có định danh rõ ràng.
3. Xuất báo cáo cùng bản build, bộ thử, môi trường và kết quả từng assertion.
4. Kiểm tra khả năng thu thập, tính đầy đủ của hồ sơ và dữ liệu bị cấm.
5. Tính hash sau các bước xử lý được phép và lưu gói vào kho có kiểm soát.
6. Đối chiếu tiêu chí phát hành, ghi nhận kết luận và yêu cầu quyết định khi có ngoại lệ.
7. Sau triển khai, thu các quan sát cần thiết về artifact và cấu hình hiệu lực tại môi trường đích.

Cần phân biệt ít nhất ba kết quả:

- **Control test failed:** kiểm thử cho thấy hành vi không đáp ứng yêu cầu.
- **Collection failed:** công cụ không lấy được bằng chứng đủ tin cậy để kết luận.
- **Test skipped:** tình huống cần thử đã không được thực hiện.

Một pipeline có thể dừng phát hành trong cả ba trường hợp tùy chính sách, nhưng nguyên nhân và cách xử lý khác nhau. Khi công cụ thu log lỗi, không được tự coi kiểm soát audit đã đạt hoặc đã thất bại; cần xác định phần nào đã được quan sát.

Không sửa một đường dẫn dạng “latest” rồi dùng nó làm định danh duy nhất cho bằng chứng. Giữ mã lần chạy và phiên bản cố định để một lần chạy mới không làm thay nội dung mà quyết định cũ đã dựa vào.

Quyền của collector cũng cần được giới hạn. Collector nên có khả năng lấy dữ liệu cần thiết mà không được tự sửa biện pháp kiểm soát đang được đánh giá nếu không có lý do và quy trình cho phép.

## 12. Kết luận kiểm chứng và quyết định rủi ro

Một quy ước trạng thái đơn giản có thể gồm:

| Trạng thái kiểm chứng | Ý nghĩa |
| --- | --- |
| PASS | Bằng chứng hỗ trợ việc đáp ứng tiêu chí trong phạm vi đã ghi |
| FAIL | Có kết quả cho thấy ít nhất một tiêu chí bắt buộc không đạt |
| INCONCLUSIVE | Bằng chứng thiếu, không tin cậy hoặc phép đo chưa đủ để kết luận |
| NOT_APPLICABLE | Yêu cầu không áp dụng cho phạm vi này và có cơ sở được phê duyệt |

Đây là quy ước minh họa. Dự án cần định nghĩa rõ trạng thái của mình và cách xử lý từng trạng thái.

Một kết luận hữu ích có thể viết:

> Với build X, cấu hình Y, môi trường staging và bộ dữ liệu tổng hợp Z, các tình huống phân quyền đã liệt kê cho hai API trong bản kê đều đạt. Chưa có bằng chứng cho đường tải tệp riêng, nên chưa thể kết luận yêu cầu bao phủ mọi đường tải đã được đáp ứng.

Kết luận này cho biết phạm vi chắc chắn và phần còn thiếu. Câu “hệ thống an toàn” vượt quá điều mà các tệp trên có thể hỗ trợ.

Nếu phát hiện đường tải cũ không thu hồi quyền trong ngưỡng 60 giây:

- Lưu lần thử không đạt và liên kết đến phát hiện.
- Xác định tác động, phạm vi người dùng hoặc dữ liệu và người phụ trách khắc phục.
- Ghi biện pháp giảm thiểu tạm thời nếu có.
- Nếu có chấp nhận rủi ro, ghi người có thẩm quyền, lý do, phạm vi, thời hạn và điều kiện xem xét lại.
- Sau sửa đổi, thu bằng chứng mới và giữ liên kết với lần không đạt trước.

Một quyết định chấp nhận rủi ro không làm bằng chứng thất bại biến thành PASS. Nó giải thích vì sao tổ chức cho phép một trạng thái chưa đáp ứng yêu cầu tồn tại trong điều kiện đã xác định.

## 13. Những lỗi thường gặp và cách xử lý

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ thu bằng chứng sau khi mọi test đã xanh | Mất lịch sử phát hiện và cách khắc phục | Giữ lần chạy liên quan và phân biệt lần trước/sau thay đổi |
| Chỉ giữ ảnh dashboard | Khó xác định nguồn, phiên bản và phạm vi | Bổ sung dữ liệu xuất có ngữ cảnh, định danh lần chạy và tiêu chí |
| Chỉ thử trường hợp hợp lệ | Không quan sát hành vi khi bị cấm | Thử thiếu quyền, sai tenant, quyền bị thu hồi và đường truy cập khác |
| Dùng báo cáo cũ cho cấu hình mới | Kết luận không còn gắn với hệ thống đang xét | Đánh giá tác động thay đổi và thu lại phần bị ảnh hưởng |
| Đồng nhất không có log với không có hành vi | Có thể bỏ qua lỗi thu nhận hoặc truy vấn | Kiểm tra nguồn, đường thu, khoảng thời gian và sự kiện thử đã biết |
| Thu quá nhiều dữ liệu thật | Tăng rủi ro rò rỉ và chi phí lưu giữ | Giảm dữ liệu, dùng dữ liệu tổng hợp và giới hạn quyền |
| Ghi hash nhưng cho phép sửa cả bản kê | Khả năng chống thay thế yếu | Bảo vệ bản kê và lịch sử bằng cơ chế phù hợp |
| Đóng phát hiện chỉ vì đã có ticket sửa | Chưa có bằng chứng thay đổi đã hiệu lực | Kiểm chứng phiên bản đã triển khai và lưu kết quả mới |
| Một test đạt được diễn giải thành tuân thủ toàn diện | Kết luận vượt phạm vi | Ánh xạ từng yêu cầu, bằng chứng, giới hạn và người xác nhận |

## 14. Checklist khi bàn giao gói bằng chứng

Trước khi dùng bằng chứng để nghiệm thu yêu cầu hoặc đưa ra quyết định rủi ro, kiểm tra:

- [ ] Mỗi bằng chứng liên kết được với yêu cầu, rủi ro và mệnh đề cần kiểm chứng.
- [ ] Tiêu chí đạt đã rõ trước khi diễn giải kết quả.
- [ ] Phiên bản, cấu hình, môi trường, nguồn và thời gian được ghi nhận.
- [ ] Các trường hợp bị cấm và đường truy cập liên quan nằm trong phạm vi hoặc được ghi thành khoảng trống.
- [ ] Test không chạy, lỗi thu thập và kết quả không đạt được phân biệt rõ.
- [ ] Mẫu, sai số, giới hạn quan sát và khác biệt môi trường được công bố.
- [ ] Dữ liệu nhạy cảm được giảm thiểu; bản đã xử lý có nguồn gốc và hash phù hợp.
- [ ] Kho bằng chứng có quyền truy cập, lịch sử và chính sách lưu giữ thích hợp.
- [ ] Người rà soát và người quyết định rủi ro được xác định.
- [ ] Kết luận chỉ bao phủ phần đã được hỗ trợ; ngoại lệ có chủ sở hữu và thời hạn.
- [ ] Có điều kiện thu lại khi yêu cầu, thiết kế, cấu hình hoặc hệ thống thay đổi.
