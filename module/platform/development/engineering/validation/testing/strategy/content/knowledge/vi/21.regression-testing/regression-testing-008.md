# Loại bỏ ca trùng mục tiêu hoặc không còn tương ứng với sản phẩm

## Mục tiêu bài học

Bộ kiểm thử hồi quy bảo vệ những hành vi quan trọng của sản phẩm sau mỗi thay đổi. Theo thời gian, sản phẩm, yêu cầu và kiến trúc thay đổi; các ca kiểm thử mới được bổ sung; một số ca cũ được sao chép để xử lý lỗi; và nhiều kịch bản có thể dần kiểm tra cùng một mục tiêu. Nếu không rà soát, bộ hồi quy sẽ chứa các ca trùng lặp, lỗi thời hoặc không còn tạo ra bằng chứng hữu ích. Chúng làm tăng thời gian chạy, chi phí bảo trì và độ nhiễu khi điều tra lỗi.

Trong chiến lược VALIDATION_TESTING_STRATEGY, loại bỏ một ca kiểm thử là quyết định về phạm vi bảo vệ chất lượng. Không nên xóa chỉ vì test dài, chạy chậm hoặc thường xuyên thất bại. Trước tiên cần hiểu mục tiêu, rủi ro và bằng chứng mà test đang cung cấp; xác nhận sản phẩm hoặc yêu cầu đã thay đổi; kiểm tra các ca khác có thực sự thay thế được mục tiêu đó; rồi mới retire test có kiểm soát.

Sau bài học, người học có thể:

- Phân biệt ca kiểm thử trùng mục tiêu, chồng lấn một phần và ca kiểm thử bổ trợ.
- Nhận diện test không còn tương ứng với chức năng, yêu cầu, giao diện hoặc kiến trúc hiện tại.
- Đánh giá giá trị và rủi ro của việc giữ, sửa, hợp nhất, thay thế hoặc loại bỏ test.
- Dùng mục tiêu kiểm thử, yêu cầu, rủi ro và bằng chứng để xác định mức bao phủ còn lại.
- Loại bỏ test mà không tạo khoảng trống bảo vệ hồi quy.
- Quản lý phụ thuộc, dữ liệu, fixture, pipeline và tài liệu liên quan khi retire test.
- Theo dõi hiệu quả sau khi tinh gọn bộ hồi quy.

## 1. Vì sao cần rà soát và loại bỏ ca kiểm thử?

Một bộ hồi quy có thể lớn dần qua nhiều năm. Mỗi lỗi được phát hiện có thể dẫn đến một test mới; mỗi tính năng có thể có nhiều kịch bản; nhiều nhóm có thể viết test cho cùng một hành vi ở các tầng khác nhau. Trong khi đó, chức năng cũ bị thay thế, quy tắc nghiệp vụ thay đổi và kiến trúc được tái cấu trúc.

Nếu giữ tất cả test vô thời hạn, nhóm có thể gặp:

- Nhiều test kiểm tra cùng một mục tiêu nhưng không tăng bằng chứng.
- Test xác minh hành vi cũ đã bị sản phẩm thay thế hoặc loại bỏ.
- Test tham chiếu endpoint, màn hình, trạng thái hoặc cấu hình không còn tồn tại.
- Bộ hồi quy chạy lâu hơn, làm chậm phản hồi cho nhà phát triển.
- Nhiều test thất bại cùng một nguyên nhân, khiến việc điều tra bị phân tán.
- Fixture, dữ liệu và môi trường cũ tiếp tục phải duy trì.
- Người đọc không biết test nào là nguồn bảo vệ chính cho một yêu cầu.
- Test lỗi thời buộc nhóm sửa theo sản phẩm mới dù mục tiêu kiểm thử không còn hợp lệ.

Tinh gọn bộ hồi quy giúp tập trung vào những kiểm tra còn giá trị. Tuy nhiên, giảm số lượng test tự nó không phải mục tiêu chất lượng. Một bộ test nhỏ hơn nhưng bỏ sót quyền truy cập, giao dịch hoặc dữ liệu quan trọng là một bước lùi.

## 2. Phân biệt các trường hợp cần xử lý

Không phải mọi test có vẻ giống nhau đều là trùng lặp. Cần phân loại đúng trước khi quyết định.

| Trường hợp | Đặc điểm | Hướng xử lý thường phù hợp |
|---|---|---|
| Trùng mục tiêu hoàn toàn | Hai hoặc nhiều test bảo vệ cùng một hành vi, cùng điều kiện quan trọng và cùng mức bằng chứng. | Giữ test tốt hơn hoặc hợp nhất, sau khi xác minh phạm vi tương đương. |
| Chồng lấn một phần | Các test có một số bước hoặc assertion giống nhau nhưng mỗi test còn bảo vệ một điều kiện riêng. | Tách mục tiêu, loại phần lặp hoặc giữ các biến thể có giá trị. |
| Test không còn tương ứng với sản phẩm | Chức năng, endpoint, trạng thái hoặc quy tắc đã bị loại bỏ hay thay đổi. | Cập nhật, thay thế hoặc retire theo yêu cầu hiện tại. |
| Test dựa trên yêu cầu đã thay đổi | Kết quả mong đợi trong test không còn đúng với chính sách hoặc đặc tả mới. | Xác nhận yêu cầu mới rồi sửa hoặc loại test cũ. |
| Test không còn tạo bằng chứng | Test luôn pass nhưng không kiểm tra được hành vi cần bảo vệ, hoặc assertion không thể phát hiện sai lệch. | Thiết kế lại hoặc loại bỏ sau khi xác nhận có bằng chứng khác. |
| Test tạm thời không ổn định | Test có giá trị nhưng đang flaky do môi trường, đồng bộ hoặc dữ liệu. | Sửa nguyên nhân hoặc cách ly có thời hạn; không coi flaky là lý do tự động xóa. |
| Test bổ trợ ở tầng khác | Nhiều test cùng tên mục tiêu nhưng kiểm tra các ranh giới khác nhau, ví dụ unit, contract và E2E. | Giữ nếu mỗi tầng cung cấp bằng chứng riêng có ý nghĩa. |

### 2.1. Trùng mục tiêu không đồng nghĩa trùng nội dung

Hai test có thể dùng tên khác nhau, dữ liệu khác nhau hoặc được viết ở hai lớp khác nhau nhưng vẫn bảo vệ cùng một hành vi. Ngược lại, hai test có cùng các bước thao tác có thể xác minh những rủi ro khác nhau.

Ví dụ, hai test cùng gọi một endpoint lấy đơn hàng có thể kiểm tra:

- Người dùng được phép xem đơn hàng của tenant mình.
- Người dùng không được xem đơn hàng thuộc tenant khác.

Các request trông giống nhau, nhưng mục tiêu và kết quả mong đợi khác nhau. Không nên xóa một test chỉ vì chúng dùng cùng endpoint.

### 2.2. Chồng lấn không nhất thiết là dư thừa

Một unit test xác minh quy tắc tính phí, một integration test xác minh transaction lưu phí và một E2E xác minh người dùng hoàn tất thanh toán có thể cùng liên quan đến “thanh toán thành công”. Tuy nhiên, mỗi test bảo vệ một ranh giới và loại lỗi khác nhau.

Chỉ coi là trùng khi mục tiêu, điều kiện, kết quả cần xác minh và giá trị bằng chứng thực sự tương đương. Tên test hoặc số dòng code không đủ để kết luận.

## 3. Xác định mục tiêu và giá trị của từng ca kiểm thử

Trước khi xem xét xóa một test, cần biết vì sao nó tồn tại. Một test tốt nên liên kết được với một hoặc nhiều mục tiêu:

- Yêu cầu chức năng hoặc tiêu chí chấp nhận.
- Quy tắc nghiệp vụ hoặc bất biến dữ liệu.
- Rủi ro sản phẩm hoặc kiểm soát bảo mật.
- Lỗi đã từng xảy ra và cần ngăn tái diễn.
- Hợp đồng giữa các thành phần.
- Luồng người dùng quan trọng.
- Yêu cầu phi chức năng như hiệu năng, khả năng phục hồi hoặc tương thích.

Nếu test không có liên kết rõ, hãy xem lịch sử thay đổi, commit, pull request, báo cáo lỗi và người sở hữu để tìm nguồn gốc. Không nên giả định test vô dụng chỉ vì tài liệu thiếu.

### 3.1. Hồ sơ mục tiêu kiểm thử

Có thể mô tả mỗi test bằng các thuộc tính:

| Thuộc tính | Câu hỏi |
|---|---|
| Mục tiêu | Test muốn chứng minh điều gì? |
| Phạm vi | Thành phần, API, vai trò hoặc luồng nào được kiểm tra? |
| Điều kiện | Dữ liệu, trạng thái và cấu hình nào cần có? |
| Kết quả mong đợi | Assertion nào thể hiện hành vi đúng? |
| Rủi ro | Lỗi nào sẽ bị bỏ sót nếu không có test? |
| Tầng kiểm thử | Unit, component, API, contract, integration hay E2E? |
| Bằng chứng | Test có thể phát hiện loại sai lệch nào? |
| Chủ sở hữu | Nhóm nào hiểu và duy trì mục tiêu đó? |

Một test có thể bảo vệ nhiều yêu cầu; một yêu cầu quan trọng có thể cần nhiều test ở các tầng khác nhau. Mục tiêu là làm rõ mối liên hệ để tránh xóa nhầm.

### 3.2. Đánh giá sức mạnh phát hiện

Test có thể vẫn chạy pass nhưng không còn phát hiện được lỗi mà nó được tạo ra để ngăn. Ví dụ:

- Assertion chỉ kiểm tra mã HTTP thành công, không kiểm tra nội dung response.
- Test dùng mock trả sẵn dữ liệu nên không phát hiện truy vấn database sai.
- Test xác minh một nút tồn tại nhưng không kiểm tra hành động của nút.
- Test chỉ kiểm tra số lượng bản ghi lớn hơn 0, dù yêu cầu là đúng một bản ghi.
- Test bị vô hiệu hóa assertion hoặc bỏ qua điều kiện lỗi.

Trong trường hợp này, vấn đề có thể là test yếu hoặc lỗi thời, không nhất thiết là trùng lặp. Cần thiết kế lại hoặc thay thế bằng kiểm tra có sức mạnh phát hiện phù hợp.

## 4. Nhận diện ca kiểm thử trùng mục tiêu

Việc tìm trùng lặp có thể bắt đầu từ nhiều tín hiệu. Không tín hiệu đơn lẻ nào đủ để quyết định xóa.

### 4.1. Dấu hiệu trong mã và kết quả chạy

- Tên test khác nhau nhưng assertion và dữ liệu đầu vào gần như giống nhau.
- Nhiều test chạy cùng endpoint với cùng trạng thái và cùng kỳ vọng.
- Nhiều test được sao chép sau các lỗi tương tự mà không có điều kiện phân biệt.
- Một test suite lặp lại các bước setup và assertion của suite khác.
- Hai test luôn thất bại cùng lúc với cùng một nguyên nhân.
- Thay đổi một hành vi khiến nhiều test cùng phải sửa dù mục tiêu được cho là khác nhau.
- Một test mới được thêm để xác minh một hành vi đã được bảo vệ đầy đủ.

### 4.2. So sánh theo mục tiêu, không chỉ theo dòng lệnh

Khi so sánh hai test, hãy kiểm tra:

1. Chúng có bảo vệ cùng yêu cầu hoặc bất biến không?
2. Chúng dùng cùng điều kiện đầu vào và trạng thái quan trọng không?
3. Chúng xác minh cùng kết quả và cùng tác động phụ không?
4. Chúng chạy ở cùng ranh giới hay cung cấp bằng chứng khác nhau?
5. Một test có bao phủ trường hợp biên mà test kia bỏ qua không?
6. Một test có đại diện cho nền tảng, vai trò hoặc cấu hình riêng không?
7. Nếu xóa một test, có loại lỗi nào sẽ không còn được phát hiện?

Có thể lập bảng so sánh để ghi rõ phần giống và khác:

| Tiêu chí | Test A | Test B | Đánh giá |
|---|---|---|---|
| Mục tiêu | Kiểm tra trạng thái đơn hàng sau thanh toán | Kiểm tra trạng thái đơn hàng sau thanh toán | Giống |
| Dữ liệu | Giao dịch thành công | Giao dịch thành công | Giống |
| Assertion | Trạng thái PAID | Trạng thái PAID | Giống |
| Tầng | API integration | API integration | Giống |
| Điều kiện biên | Không có | Không có | Không tạo khác biệt |
| Bằng chứng bổ sung | Không | Không | Có thể trùng hoàn toàn |

Nếu Test B kiểm tra thêm việc phát event hoặc rollback khi thất bại, nó không còn tương đương hoàn toàn với Test A.

### 4.3. Dùng coverage map

Coverage map liên kết yêu cầu hoặc rủi ro với các test đang bảo vệ. Ví dụ:

| Yêu cầu/rủi ro | Unit | API/Integration | E2E | Ghi chú |
|---|---|---|---|---|
| Tính tổng tiền chính xác | Test tính toán | Test lưu và truy vấn | Luồng thanh toán đại diện | Các tầng có mục tiêu khác nhau. |
| Ngăn truy cập chéo tenant | Test policy | Test truy vấn và API | Kiểm tra hành trình đại diện | Không xóa test ở tầng API chỉ vì có E2E. |
| Trạng thái thanh toán không bị trùng | Test idempotency logic | Test transaction/concurrency | Test hành trình gửi lại | Giữ kiểm tra ở ranh giới bảo vệ bất biến. |
| Màn hình cũ đã bị loại bỏ | — | — | Test giao diện cũ | Có thể retire nếu không còn đường sử dụng được hỗ trợ. |

Coverage map giúp nhìn ra vùng không có test, vùng có nhiều test cùng mục tiêu và vùng có các tầng bổ trợ nhau.

## 5. Nhận diện test không còn tương ứng với sản phẩm

Một test có thể trở nên lỗi thời khi sản phẩm thay đổi. Các thay đổi phổ biến gồm:

- Chức năng hoặc màn hình bị loại bỏ.
- API được thay thế hoặc phiên bản cũ ngừng hỗ trợ.
- Quy trình nghiệp vụ thay đổi.
- Trạng thái hoặc quy tắc dữ liệu được cập nhật.
- Vai trò và quyền được thiết kế lại.
- Feature flag cũ không còn tồn tại.
- Kiến trúc thay đổi, một dịch vụ được hợp nhất hoặc tách ra.
- Hệ thống không còn hỗ trợ trình duyệt, thiết bị hoặc nền tảng cũ.
- Một luồng được thay bằng sản phẩm hoặc dịch vụ khác.

### 5.1. Phân biệt sản phẩm đã đổi với test chưa được cập nhật

Test thất bại sau một thay đổi có thể là:

- Lỗi sản phẩm mới.
- Yêu cầu mới chưa được triển khai.
- Test cần cập nhật vì hành vi hợp lệ đã thay đổi.
- Fixture hoặc môi trường không còn phù hợp.
- Một phụ thuộc đã đổi phiên bản hoặc hợp đồng.

Không nên xóa test chỉ để làm pipeline xanh. Trước tiên cần xác định thay đổi sản phẩm đã được phê duyệt và test đang kiểm tra một hành vi không còn được hỗ trợ hay chưa.

### 5.2. Kiểm tra nguồn xác nhận

Có thể dùng các bằng chứng sau trong phạm vi công việc của nhóm:

- Yêu cầu hoặc tiêu chí chấp nhận hiện hành.
- Quyết định sản phẩm đã được phê duyệt.
- Tài liệu API hoặc hợp đồng phiên bản hiện tại.
- Danh sách chức năng được hỗ trợ.
- Kế hoạch ngừng hỗ trợ hoặc migration.
- Pull request thay đổi chức năng.
- Người sở hữu nghiệp vụ hoặc thành phần xác nhận.

Lịch sử code cho biết test được tạo khi nào và vì sao, nhưng không tự chứng minh sản phẩm đã ngừng hỗ trợ một hành vi. Cần có căn cứ hiện tại để xác định test đã lỗi thời.

## 6. Phân biệt xóa, sửa, hợp nhất, thay thế và cách ly

Không phải mọi test dư thừa hoặc lỗi thời đều cần xóa ngay. Có nhiều lựa chọn với tác động khác nhau.

| Hành động | Khi phù hợp | Điều cần bảo đảm |
|---|---|---|
| Giữ nguyên | Test còn mục tiêu riêng và tạo bằng chứng cần thiết. | Có chủ sở hữu và lý do duy trì. |
| Sửa (update) | Mục tiêu vẫn hợp lệ nhưng dữ liệu, giao diện hoặc điều kiện đã đổi. | Assertion vẫn phản ánh yêu cầu hiện tại. |
| Hợp nhất (merge) | Nhiều test cùng mục tiêu, có thể gom thành một test rõ ràng với các trường hợp cần thiết. | Không mất điều kiện, assertion hoặc bằng chứng riêng. |
| Thay thế (replace) | Test cũ không còn phù hợp về tầng hoặc cách thực hiện, nhưng rủi ro vẫn còn. | Test mới chứng minh được mục tiêu trước khi retire test cũ. |
| Xóa/retire | Mục tiêu không còn tồn tại hoặc đã được bảo vệ tương đương bởi test khác. | Có căn cứ, đánh giá khoảng trống và lưu lịch sử cần thiết. |
| Cách ly tạm thời | Test có giá trị nhưng đang gây nhiễu do flaky hoặc môi trường. | Có thời hạn, chủ sở hữu và biện pháp kiểm soát thay thế. |

### 6.1. Khi nào nên hợp nhất?

Hợp nhất phù hợp khi các test cùng bảo vệ một hành vi và sự khác nhau chỉ nằm ở setup hoặc dữ liệu không tạo ra mục tiêu riêng. Ví dụ, hai test riêng lẻ kiểm tra cùng một quy tắc từ chối đơn hàng với hai giá trị đầu vào tương đương có thể được tổ chức lại thành một parameterized test.

Tuy nhiên, không nên gộp quá nhiều mục tiêu vào một test lớn. Nếu một test parameterized chứa hàng chục trường hợp khác nhau, báo cáo thất bại có thể khó đọc; cần đặt tên tham số và phân nhóm theo quy tắc.

### 6.2. Khi nào nên thay thế?

Nếu một E2E cũ đang kiểm tra logic phân quyền qua giao diện nhưng thời gian chạy lớn và khó chẩn đoán, nhóm có thể bổ sung API/integration test kiểm tra ma trận quyền và giữ một E2E đại diện cho hành trình người dùng. Chỉ retire E2E cũ sau khi xác nhận test mới cùng các kiểm tra còn lại bảo vệ đầy đủ mục tiêu cần thiết.

### 6.3. Khi nào nên cách ly thay vì xóa?

Một test không ổn định do race condition hoặc môi trường có thể vẫn bảo vệ một rủi ro quan trọng. Cần điều tra và sửa nguyên nhân. Nếu phải cách ly tạm thời để pipeline tiếp tục hoạt động, ghi lý do, người phụ trách, thời hạn và biện pháp kiểm soát thay thế. Không dùng trạng thái quarantine như cách loại bỏ âm thầm một cảnh báo khó xử lý.

## 7. Đánh giá khoảng trống bao phủ trước khi retire

Trước khi xóa hoặc hợp nhất, cần trả lời: nếu test này biến mất, nhóm còn bằng chứng nào cho mục tiêu và rủi ro của nó?

### 7.1. So sánh mục tiêu và assertion

Liệt kê từng assertion và điều kiện quan trọng mà test hiện tại xác minh. Kiểm tra xem test còn lại có xác minh đúng những điều đó không. Không chỉ so sánh tên hoặc số lượng test.

Ví dụ, một test cũ xác minh:

- Người dùng tenant A không đọc được hồ sơ tenant B.
- API không trả nội dung dữ liệu nhạy cảm.
- Không có event hoặc audit record thành công được phát sinh.
- Kết quả được ghi nhận là truy cập bị từ chối.

Nếu test thay thế chỉ kiểm tra HTTP 403, nó chưa chắc bảo vệ các tác động còn lại.

### 7.2. Đánh giá ranh giới và tầng kiểm thử

Hai test cùng yêu cầu có thể cung cấp bằng chứng khác nhau:

- Unit test kiểm tra quy tắc logic nhanh và cô lập.
- API test kiểm tra request, response và middleware.
- Integration test kiểm tra database, transaction hoặc broker.
- Contract test kiểm tra kỳ vọng giữa consumer và provider.
- E2E test kiểm tra hành trình xuyên hệ thống.

Một test ở tầng thấp hơn có thể thay thế một phần bằng chứng của test ở tầng cao hơn, nhưng không tự động thay thế toàn bộ hành vi xuyên hệ thống. Ngược lại, một E2E có thể đi qua luồng thành công nhưng không bao phủ tất cả trường hợp biên mà unit test đang kiểm tra.

### 7.3. Kiểm tra rủi ro còn lại

Xem xét:

- Hậu quả nếu hành vi sai tái diễn.
- Khả năng xảy ra và tần suất sử dụng.
- Phạm vi người dùng, tenant hoặc dữ liệu bị ảnh hưởng.
- Khả năng phát hiện lỗi ở môi trường cao hơn.
- Khả năng rollback hoặc phục hồi.
- Bằng chứng thay thế và mức độ tin cậy của nó.

Nếu mục tiêu liên quan đến bảo mật, thanh toán, dữ liệu hoặc tuân thủ, cần có xác nhận của người sở hữu rủi ro trước khi loại bỏ kiểm tra cuối cùng bảo vệ hành vi đó.

## 8. Quy trình retire ca kiểm thử có kiểm soát

Một quy trình có thể áp dụng:

1. **Đề xuất:** xác định test nghi trùng hoặc lỗi thời và lý do xem xét.
2. **Tìm nguồn gốc:** liên kết test với yêu cầu, lỗi, thay đổi sản phẩm và người sở hữu.
3. **Mô tả mục tiêu:** ghi hành vi, điều kiện, assertion và rủi ro được bảo vệ.
4. **So sánh:** tìm các test khác có thể trùng hoặc thay thế; lập bảng phần giống và khác.
5. **Xác minh sản phẩm hiện tại:** kiểm tra chức năng, hợp đồng hoặc yêu cầu có còn được hỗ trợ không.
6. **Đánh giá khoảng trống:** xác định bằng chứng nào sẽ mất đi và rủi ro còn lại.
7. **Chọn hành động:** giữ, sửa, hợp nhất, thay thế, retire hoặc cách ly có thời hạn.
8. **Thực hiện thay đổi:** cập nhật test, fixture, dữ liệu, pipeline và tham chiếu liên quan.
9. **Chạy xác minh:** chạy các test còn lại, kiểm tra phạm vi liên quan và xác nhận không mất mục tiêu.
10. **Review và ghi nhận:** lưu lý do, người phê duyệt, bằng chứng và thời điểm retire.
11. **Theo dõi sau thay đổi:** quan sát lỗi lọt qua, thời gian chạy và chất lượng tín hiệu.

### 8.1. Mẫu hồ sơ retire

~~~text
Test ID / đường dẫn:
Mục tiêu kiểm thử:
Yêu cầu hoặc rủi ro liên quan:
Lý do đề xuất retire:
Bằng chứng sản phẩm đã thay đổi (nếu lỗi thời):
Test trùng hoặc test thay thế:
Assertion/điều kiện được giữ lại:
Khoảng trống bao phủ sau khi retire:
Rủi ro còn lại:
Hành động: giữ / sửa / hợp nhất / thay thế / retire / cách ly
Người review và phê duyệt:
Kết quả kiểm tra sau thay đổi:
Thời điểm và phiên bản:
~~~

Với test có mức rủi ro cao, nên có review của người sở hữu nghiệp vụ hoặc kỹ thuật liên quan. Không nên để tác giả test tự quyết định xóa kiểm tra quan trọng mà không có người review độc lập.

## 9. Ví dụ 1: Hợp nhất hai ca kiểm thử thanh toán trùng mục tiêu

Một hệ thống có hai test API:

- Test A: thanh toán đơn hàng bằng thẻ hợp lệ, xác minh trạng thái đơn hàng là PAID.
- Test B: thanh toán đơn hàng bằng một bộ dữ liệu thẻ hợp lệ khác, cũng xác minh trạng thái PAID.

Điều tra cho thấy hai test dùng cùng luồng, cùng trạng thái ban đầu và không kiểm tra đặc tính riêng của từng loại thẻ. Cả hai không xác minh event, ledger hoặc lỗi thanh toán.

Nhóm có thể:

1. Xác nhận mục tiêu là chuyển trạng thái đơn hàng sau thanh toán thành công.
2. Kiểm tra các loại thẻ có thực sự đại diện cho các nhánh nghiệp vụ khác nhau không.
3. Nếu không, hợp nhất thành một test rõ ràng hoặc parameterized test với dữ liệu đại diện.
4. Bổ sung kiểm tra riêng cho các loại thanh toán chỉ khi chúng có hợp đồng hoặc rủi ro khác nhau.
5. Giữ các test về từ chối, timeout, retry và idempotency vì chúng bảo vệ mục tiêu khác.
6. Xác minh báo cáo test vẫn hiển thị trường hợp cụ thể nếu một tham số thất bại.

Kết quả là giảm lặp setup và thời gian chạy mà không làm mất các nhánh nghiệp vụ cần thiết.

## 10. Ví dụ 2: Retire test của chức năng đã ngừng hỗ trợ

Một sản phẩm từng hỗ trợ xuất báo cáo theo định dạng cũ. Sau một quyết định sản phẩm, định dạng cũ bị loại bỏ và mọi người dùng được chuyển sang định dạng mới. Bộ E2E vẫn có test kiểm tra nút xuất cũ, file cũ và màn hình cấu hình cũ.

Không nên chỉ xóa test vì nó đang thất bại. Nhóm cần:

- Xác nhận quyết định ngừng hỗ trợ và phiên bản áp dụng.
- Kiểm tra không còn tenant hoặc người dùng được hỗ trợ phụ thuộc định dạng cũ.
- Xác định dữ liệu cũ có cần đọc hoặc chuyển đổi hay không.
- Kiểm tra luồng xuất mới và khả năng tương thích dữ liệu lịch sử.
- Xác định các test migration hoặc backward compatibility vẫn cần giữ.
- Xóa test giao diện cũ và fixture chỉ phục vụ chức năng đã retire.
- Cập nhật tài liệu và pipeline nếu còn tham chiếu đến kịch bản cũ.

Nếu hệ thống vẫn phải đọc dữ liệu định dạng cũ, test đọc hoặc migration có thể còn giá trị dù giao diện xuất cũ đã bị loại bỏ. Chỉ retire những kiểm tra thực sự không còn mục tiêu.

## 11. Quản lý phụ thuộc khi loại bỏ test

Một ca kiểm thử có thể dùng chung fixture, dữ liệu, helper, mock server, test account hoặc pipeline job với nhiều test khác. Xóa test không đồng nghĩa có thể xóa ngay mọi thành phần mà nó sử dụng.

Trước khi xóa helper hoặc dữ liệu:

- Tìm các test khác còn tham chiếu.
- Kiểm tra fixture có tạo dữ liệu cho nhiều mục tiêu không.
- Xác định job CI, tag, suite hoặc lịch chạy còn sử dụng test.
- Kiểm tra tài liệu, dashboard và báo cáo có liên kết đến test ID.
- Đánh giá snapshot, baseline hoặc file dữ liệu có thể còn cần.
- Xóa dữ liệu chỉ khi không còn consumer và có thể dọn an toàn.

Nên thực hiện thay đổi nhỏ, dễ review và có thể truy vết. Nếu xóa test và helper trong cùng một thay đổi, cần xác minh toàn bộ test còn lại vẫn biên dịch và chạy đúng.

### 11.1. Không xóa bằng chứng lịch sử quan trọng

Test có thể được retire khỏi pipeline nhưng lịch sử về lỗi, quyết định và kết quả cũ vẫn có giá trị. Giữ liên kết trong hệ thống quản lý lỗi hoặc pull request, ghi lý do retire và phiên bản áp dụng. Không cần giữ một test lỗi thời chạy mãi chỉ để lưu lịch sử.

## 12. Tích hợp rà soát trùng lặp vào vòng đời bộ hồi quy

Rà soát không nên chỉ diễn ra khi pipeline quá chậm. Có thể thực hiện theo chu kỳ hoặc khi có sự kiện thay đổi.

### 12.1. Thời điểm nên rà soát

- Sau một đợt tái cấu trúc hoặc thay đổi kiến trúc lớn.
- Khi loại bỏ hoặc thay thế một tính năng.
- Khi API hoặc hợp đồng thay đổi phiên bản.
- Khi bộ test tăng nhanh hoặc thời gian chạy vượt ngưỡng.
- Khi nhiều test thất bại cùng nguyên nhân.
- Khi một test không còn được chạy trong pipeline hoặc không có người sở hữu.
- Trước khi chuyển sang nhịp phát hành mới.
- Trong hoạt động bảo trì định kỳ của bộ kiểm thử.

### 12.2. Trách nhiệm

- **Nhóm phát triển:** giải thích hành vi và thay đổi mã.
- **Nhóm kiểm thử:** xác định mục tiêu, coverage và bằng chứng.
- **Chủ sở hữu nghiệp vụ/sản phẩm:** xác nhận quy tắc và chức năng còn được hỗ trợ.
- **Chủ sở hữu nền tảng/pipeline:** đánh giá tác động lên lịch chạy, fixture và môi trường.
- **Người review:** kiểm tra quyết định retire có tạo khoảng trống rủi ro không.

Với nhóm nhỏ, một người có thể đảm nhiệm nhiều vai trò, nhưng quyết định cần được ghi nhận đủ để người khác hiểu.

## 13. Đo lường hiệu quả sau khi tinh gọn

Đánh giá kết quả không chỉ bằng số test đã xóa. Cần xem bộ hồi quy có nhanh hơn mà vẫn giữ khả năng phát hiện lỗi hay không.

| Chỉ số | Điều cần quan sát | Cách diễn giải |
|---|---|---|
| Thời gian chạy suite | Thời gian trước và sau khi hợp nhất/retire. | Giảm thời gian là hữu ích nếu mức bảo vệ vẫn được giữ. |
| Tỷ lệ test trùng mục tiêu | Số nhóm test có mục tiêu tương đương. | Cho biết mức lặp và cơ hội hợp nhất. |
| Tỷ lệ test lỗi thời | Test tham chiếu chức năng hoặc hợp đồng không còn được hỗ trợ. | Cho biết mức lệch giữa suite và sản phẩm. |
| Flaky rate | Tỷ lệ test thất bại không ổn định. | Giúp phân biệt vấn đề ổn định với vấn đề trùng lặp. |
| Lỗi lọt qua | Lỗi thuộc mục tiêu đã retire xuất hiện sau thay đổi. | Tín hiệu cần xem lại quyết định hoặc bằng chứng thay thế. |
| Thời gian chẩn đoán | Thời gian xác định nguyên nhân khi test thất bại. | Suite rõ mục tiêu thường giúp giảm nhiễu điều tra. |
| Chi phí bảo trì | Thời gian cập nhật test, fixture và môi trường. | Đánh giá lợi ích dài hạn của việc tinh gọn. |
| Bao phủ rủi ro | Rủi ro quan trọng còn có kiểm tra tương ứng. | Bảo đảm tinh gọn không làm mất kiểm soát. |

Không nên dùng số lượng test giảm làm chỉ tiêu duy nhất. Một test có thể mất nhiều thời gian nhưng là kiểm tra duy nhất cho một rủi ro nghiêm trọng. Một test chạy rất nhanh vẫn có thể dư thừa nếu không cung cấp thêm bằng chứng.

## 14. Những sai lầm thường gặp

- **Xóa test chỉ vì tên giống nhau:** có thể bỏ mất điều kiện hoặc mục tiêu khác biệt.
- **Coi các tầng kiểm thử là thay thế hoàn toàn cho nhau:** bỏ sót bằng chứng ở ranh giới tích hợp hoặc hành trình người dùng.
- **Xóa test đang thất bại để làm pipeline xanh:** che giấu lỗi sản phẩm hoặc vấn đề môi trường.
- **Xóa test không có tài liệu mà không điều tra:** có thể bỏ mất kiểm tra được tạo sau một sự cố nghiêm trọng.
- **Coi chức năng bị ẩn là chức năng đã bị loại bỏ:** feature flag có thể còn được bật cho một số tenant hoặc nhóm người dùng.
- **Hợp nhất quá nhiều trường hợp vào một test lớn:** làm khó chẩn đoán và tăng phụ thuộc dữ liệu.
- **Xóa helper dùng chung:** gây lỗi cho các test khác không được rà soát.
- **Không cập nhật coverage map và truy vết:** người bảo trì sau này không hiểu vì sao test bị loại bỏ.
- **Không review rủi ro:** bỏ kiểm tra bảo mật, giao dịch hoặc dữ liệu mà không có người chịu trách nhiệm.
- **Không theo dõi sau retire:** không phát hiện sớm lỗi lọt qua do mất bằng chứng.

## 15. Checklist trước khi retire một ca kiểm thử

- [ ] Đã xác định mục tiêu và rủi ro mà test đang bảo vệ.
- [ ] Đã tìm yêu cầu, lỗi, quyết định sản phẩm và lịch sử liên quan.
- [ ] Đã phân biệt trùng hoàn toàn với chồng lấn một phần.
- [ ] Đã xác minh chức năng hoặc hành vi có thực sự không còn được hỗ trợ.
- [ ] Đã so sánh điều kiện, dữ liệu, assertion và tầng kiểm thử.
- [ ] Đã kiểm tra test thay thế có bảo vệ cùng mục tiêu và ranh giới cần thiết.
- [ ] Đã đánh giá khoảng trống bao phủ và rủi ro còn lại.
- [ ] Đã xem xét các trường hợp biên, vai trò, nền tảng và tenant liên quan.
- [ ] Đã xác định phụ thuộc dùng chung trước khi xóa helper hoặc fixture.
- [ ] Đã chọn rõ hành động giữ, sửa, hợp nhất, thay thế, retire hoặc cách ly.
- [ ] Đã có review và phê duyệt phù hợp với mức rủi ro.
- [ ] Đã chạy bộ kiểm thử còn lại và kiểm tra pipeline.
- [ ] Đã cập nhật liên kết, tài liệu và coverage map.
- [ ] Đã lưu lý do, phiên bản và bằng chứng của quyết định.
- [ ] Có kế hoạch theo dõi lỗi lọt qua và giá trị sau khi tinh gọn.

## Kết luận

Loại bỏ ca kiểm thử trùng mục tiêu hoặc không còn tương ứng với sản phẩm là hoạt động quản lý chất lượng của bộ hồi quy. Hãy đánh giá mục tiêu, điều kiện, assertion, rủi ro và loại bằng chứng mà mỗi test tạo ra; xác nhận sản phẩm hoặc yêu cầu đã thay đổi; rồi chọn giữ, sửa, hợp nhất, thay thế hay retire. Trước khi xóa, phải chứng minh rằng các rủi ro quan trọng vẫn được bảo vệ và các phụ thuộc dùng chung không bị ảnh hưởng. Bộ hồi quy tốt không phải bộ có nhiều test nhất hoặc ít test nhất, mà là bộ kiểm tra có mục tiêu rõ, không lặp vô ích, còn phù hợp với sản phẩm và tạo bằng chứng đáng tin cậy.
