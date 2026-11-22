# Tích hợp hoạt động kiểm thử vào định nghĩa hoàn thành

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), kiểm thử cần được tích hợp vào cách nhóm xác định một công việc đã hoàn thành. Nếu nhóm chỉ kiểm thử sau khi phát triển xong hoặc coi việc viết mã là dấu mốc kết thúc, lỗi có thể được phát hiện muộn, chi phí sửa tăng và quyết định phát hành thiếu bằng chứng.

**Định nghĩa hoàn thành (Definition of Done – DoD)** là thỏa thuận chung về những điều kiện chất lượng mà một hạng mục công việc phải đáp ứng trước khi được xem là hoàn tất. Khi hoạt động kiểm thử được đưa vào DoD, nhóm thống nhất từ đầu loại bằng chứng cần có, mức kiểm tra phù hợp với rủi ro, cách xử lý lỗi và trách nhiệm của từng vai trò. Nhờ đó, chất lượng trở thành một phần của quy trình phát triển hằng ngày.

Bài học này trình bày cách xây dựng DoD có thể kiểm chứng, tích hợp kiểm thử theo từng giai đoạn, quản lý ngoại lệ và duy trì thỏa thuận khi sản phẩm thay đổi.

## 1. Hiểu đúng về Definition of Done

### 1.1. DoD là tiêu chuẩn chung để xác nhận hoàn tất

DoD mô tả trạng thái tối thiểu mà một hạng mục phải đạt để nhóm có thể gọi là hoàn thành. Đây là thỏa thuận áp dụng nhất quán cho các hạng mục thuộc phạm vi đã thống nhất, dù từng hạng mục có thể cần thêm tiêu chí riêng.

Ví dụ, một DoD có thể yêu cầu:

- Thay đổi đáp ứng tiêu chí chấp nhận đã thống nhất.
- Code review hoàn tất và các góp ý bắt buộc đã được xử lý.
- Kiểm thử phù hợp với rủi ro đã chạy và có kết quả được ghi nhận.
- Không còn lỗi nghiêm trọng chưa có quyết định xử lý.
- Tài liệu, cấu hình và thông tin vận hành liên quan đã được cập nhật.
- Thay đổi có thể tích hợp vào nhánh hoặc bản build mục tiêu mà không làm hỏng các kiểm tra bắt buộc.

Một điều kiện trong DoD cần đủ rõ để hai thành viên độc lập có thể đánh giá cùng một kết quả. Câu “đã kiểm thử đầy đủ” không cho biết cần chạy loại kiểm thử nào, với dữ liệu nào hoặc thế nào là đạt. Câu “unit test cho quy tắc mới và các trường hợp biên đã chạy thành công; integration test cho thay đổi schema đã chạy trên cơ sở dữ liệu thử nghiệm” có thể kiểm chứng tốt hơn.

### 1.2. Phân biệt DoD với tiêu chí chấp nhận và Definition of Ready

Các khái niệm này hỗ trợ nhau nhưng có mục đích khác nhau:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Definition of Ready (DoR) | Hạng mục đã đủ rõ để bắt đầu chưa? | Yêu cầu có mục tiêu, tiêu chí chấp nhận, dữ liệu và phụ thuộc đã xác định. |
| Tiêu chí chấp nhận (Acceptance Criteria) | Hành vi cụ thể nào phải đúng để hạng mục đáp ứng nhu cầu? | Khi mã giảm giá hết hạn, hệ thống từ chối và hiển thị thông báo phù hợp. |
| Definition of Done (DoD) | Hạng mục cần đáp ứng những tiêu chuẩn chung nào trước khi được xem là hoàn tất? | Kiểm thử liên quan đã đạt, review hoàn tất, tài liệu được cập nhật và không còn lỗi nghiêm trọng chưa xử lý. |

DoR tập trung vào điều kiện bắt đầu; tiêu chí chấp nhận mô tả kết quả riêng của hạng mục; DoD xác định tiêu chuẩn chất lượng chung khi kết thúc. Không nên dùng DoD để thay thế các tiêu chí nghiệp vụ cụ thể.

### 1.3. DoD áp dụng ở cấp độ nào?

Tùy cách tổ chức, DoD có thể được áp dụng ở nhiều cấp:

- **Hạng mục hoặc user story:** xác nhận một thay đổi nhỏ đã đáp ứng tiêu chuẩn chung.
- **Increment hoặc tính năng:** xác nhận nhiều hạng mục phối hợp thành một phần sản phẩm có thể sử dụng.
- **Bản phát hành:** xác nhận các yêu cầu phát hành, kiểm thử hồi quy, vận hành, bảo mật và rủi ro còn lại đã được xem xét.

Các cấp này có thể có tiêu chuẩn bổ sung. Ví dụ, một story có thể hoàn tất unit test và integration test, trong khi bản phát hành còn cần kiểm thử tải, kiểm tra bảo mật, kế hoạch rollback và phê duyệt rủi ro. Hoàn thành một story không tự động có nghĩa là toàn bộ sản phẩm đã sẵn sàng phát hành.

## 2. Vì sao cần đưa kiểm thử vào DoD?

Nếu kiểm thử chỉ diễn ra ở cuối dự án, nhóm dễ tích lũy nhiều thay đổi chưa được xác minh. Khi lỗi xuất hiện, việc tìm nguyên nhân trở nên khó khăn vì nhiều thành phần đã thay đổi cùng lúc.

Tích hợp kiểm thử vào DoD mang lại các lợi ích sau:

- **Phát hiện lỗi sớm:** người viết mã kiểm tra hành vi trong lúc thay đổi còn nhỏ và dễ hiểu.
- **Giảm chi phí sửa lỗi:** lỗi được xử lý gần thời điểm tạo ra, trước khi lan sang các thành phần khác.
- **Tạo bằng chứng nhất quán:** mọi hạng mục đều có tiêu chuẩn tối thiểu về kết quả kiểm thử và review.
- **Làm rõ trách nhiệm:** phát triển, kiểm thử, vận hành và sản phẩm cùng hiểu phần việc cần hoàn tất.
- **Giảm công việc dồn cuối kỳ:** kiểm thử và cập nhật tài liệu diễn ra liên tục thay vì trở thành một đợt riêng sau khi phát triển.
- **Hỗ trợ quyết định phát hành:** nhóm biết rõ điều gì đã được xác minh và khoảng trống nào vẫn còn.

DoD cũng giúp tránh cách hiểu khác nhau về từ “xong”. Một người có thể coi mã đã merge là hoàn tất; người khác chỉ coi hạng mục hoàn tất khi có kiểm thử, review và tài liệu. Thỏa thuận chung loại bỏ phần lớn sự mơ hồ đó.

## 3. Nguyên tắc xây dựng DoD có thể kiểm chứng

### 3.1. Mô tả điều kiện bằng kết quả quan sát được

Mỗi mục cần có cách xác nhận cụ thể. Ưu tiên câu mô tả kết quả hoặc bằng chứng, chẳng hạn:

| Diễn đạt mơ hồ | Diễn đạt có thể kiểm chứng |
|---|---|
| Đã test. | Các unit test cho logic thay đổi và trường hợp biên đã chạy; kết quả CI được liên kết với pull request. |
| Chất lượng tốt. | Code review hoàn tất; không còn góp ý bắt buộc chưa xử lý; quy tắc lint và phân tích tĩnh bắt buộc đạt. |
| Không có bug. | Không còn lỗi mức nghiêm trọng đã biết trong phạm vi; lỗi còn lại có mức độ, người phụ trách và quyết định xử lý. |
| Tài liệu đầy đủ. | Hướng dẫn sử dụng, API hoặc vận hành bị ảnh hưởng đã được cập nhật và review. |
| Sẵn sàng triển khai. | Artifact đã được xác định phiên bản, cấu hình triển khai đã kiểm tra và có phương án rollback phù hợp. |

Không nên viết DoD thành danh sách khẩu hiệu. Nếu không biết bằng chứng nào chứng minh một điều kiện đã đạt, điều kiện đó cần được viết lại.

### 3.2. Chọn mức kiểm thử theo rủi ro

Không phải mọi thay đổi đều cần cùng một bộ kiểm thử. DoD nên xác định tiêu chuẩn nền áp dụng cho mọi hạng mục và yêu cầu bổ sung theo loại thay đổi hoặc mức rủi ro.

Ví dụ:

- Thay đổi thuật toán thuần cần unit test cho quy tắc và giá trị biên.
- Thay đổi truy vấn hoặc migration cần integration test với cơ sở dữ liệu.
- Thay đổi API cần kiểm tra hợp đồng, xác thực, phân quyền và tương thích.
- Thay đổi giao diện cần kiểm tra hành vi người dùng và nền tảng được hỗ trợ.
- Thay đổi ảnh hưởng hiệu năng hoặc bảo mật cần kiểm thử chuyên biệt trước mốc phát hành phù hợp.

Cách tiếp cận theo rủi ro giữ DoD đủ thực tế. Một hạng mục tài liệu nhỏ không cần chạy kiểm thử tải, nhưng một thay đổi ở luồng thanh toán không thể chỉ dựa vào unit test.

### 3.3. Xác định rõ điều kiện đạt và cách xử lý thất bại

DoD nên quy định kết quả nào được coi là đạt, điều gì xảy ra khi kiểm thử thất bại và ai có quyền quyết định ngoại lệ.

Ví dụ, điều kiện có thể yêu cầu:

- Tất cả kiểm tra bắt buộc liên quan đến thay đổi đều đạt.
- Kiểm tra thất bại được phân loại là lỗi sản phẩm, lỗi test hoặc lỗi môi trường.
- Lỗi nghiêm trọng chặn hoàn tất cho đến khi sửa hoặc có quyết định chính thức theo quy trình.
- Ca kiểm thử bị bỏ qua hoặc tạm vô hiệu hóa phải có lý do, người phụ trách và thời hạn xem xét.
- Không được đổi trạng thái pipeline bằng cách bỏ qua kiểm tra bắt buộc mà không ghi nhận.

Nếu một ca flaky, nhóm cần điều tra và ghi trạng thái rõ ràng. Một lần chạy lại thành công không tự động chứng minh lần thất bại trước là vô nghĩa.

### 3.4. Giữ DoD ngắn gọn, ổn định và đủ bao quát

DoD là thỏa thuận làm việc chung nên cần dễ hiểu và có thể áp dụng thường xuyên. Không nên đưa mọi chi tiết kiểm thử của từng tính năng vào danh sách chung. Những yêu cầu đặc thù nên nằm trong tiêu chí chấp nhận, kế hoạch kiểm thử hoặc checklist theo loại thay đổi.

DoD cũng không nên quá dài đến mức nhóm chỉ đánh dấu cho xong. Mỗi điều kiện cần có lý do chất lượng rõ ràng và người có thể xác nhận.

## 4. Tích hợp kiểm thử vào từng giai đoạn phát triển

Kiểm thử hiệu quả khi được thực hiện xuyên suốt vòng đời thay đổi. Có thể tổ chức theo các giai đoạn sau.

### 4.1. Trước khi phát triển: làm rõ yêu cầu và khả năng kiểm thử

Trong refinement hoặc lập kế hoạch, nhóm cần:

- Làm rõ mục tiêu, người dùng và tiêu chí chấp nhận.
- Xác định trường hợp thành công, lỗi, giá trị biên và trạng thái chuyển tiếp.
- Nhận diện rủi ro về dữ liệu, tích hợp, bảo mật và hiệu năng.
- Xác định phụ thuộc, môi trường và dữ liệu cần chuẩn bị.
- Thống nhất loại kiểm thử và bằng chứng cần có để hoàn tất.

Ví dụ, story “người dùng đổi mật khẩu” cần làm rõ quy tắc mật khẩu, xác minh danh tính, vô hiệu hóa phiên cũ, giới hạn thử sai, thông báo và hành vi khi dịch vụ email không sẵn sàng. Nếu những điểm này chưa rõ, tiêu chí chấp nhận và kế hoạch kiểm thử sẽ thiếu cơ sở.

### 4.2. Trong khi phát triển: kiểm tra cùng với mã thay đổi

Người phát triển nên thực hiện kiểm tra gần với nơi tạo ra hành vi:

- Viết hoặc cập nhật unit test cùng lúc với logic mới.
- Kiểm tra component khi thay đổi một thành phần có phụ thuộc được kiểm soát.
- Cập nhật contract test khi thay đổi giao diện hoặc schema.
- Chạy kiểm tra định dạng, lint, phân tích tĩnh và các quy tắc bảo mật tự động.
- Tạo dữ liệu kiểm thử và kiểm tra migration khi thay đổi cấu trúc dữ liệu.

Khi kiểm thử được viết cùng mã, người phát triển có thể sửa nhanh và hiểu rõ lý do của assertion. Nhóm không phải chờ đến cuối sprint mới phát hiện rằng hành vi mới chưa có cách xác minh.

### 4.3. Khi review và tích hợp: xác nhận thay đổi trong bối cảnh chung

Pull request hoặc merge request nên có các bằng chứng phù hợp:

- Mục tiêu và phạm vi thay đổi rõ ràng.
- Kết quả kiểm thử tự động liên quan.
- Review mã và xử lý góp ý.
- Kiểm tra tương thích API, schema và phụ thuộc khi cần.
- Đánh giá ảnh hưởng đến dữ liệu, cấu hình, bảo mật và vận hành.
- Hướng dẫn kiểm thử thủ công hoặc bằng chứng bổ sung nếu cần.

Pipeline CI có thể tự động chạy unit test, lint, phân tích tĩnh, contract test và một số integration test. Các kiểm tra chậm hơn có thể chạy theo lịch, trên môi trường chuyên dụng hoặc trước mốc phát hành. Điều quan trọng là các điều kiện chặn merge phải được xác định rõ và không bị bỏ qua tùy tiện.

### 4.4. Trước khi phát hành: xác minh sản phẩm tích hợp

Khi nhiều thay đổi đã tích hợp, nhóm cần xác nhận các rủi ro ở cấp hệ thống:

- Kiểm thử hồi quy cho luồng quan trọng.
- Kiểm thử end-to-end cho hành trình người dùng đại diện.
- Kiểm thử hiệu năng, tải, bảo mật hoặc khả năng phục hồi theo yêu cầu.
- Kiểm tra cấu hình, feature flag, migration và artifact thực tế.
- Xác nhận giám sát, cảnh báo, backup và phương án rollback.
- Đánh giá lỗi còn mở và rủi ro còn lại.

Các hoạt động này có thể thuộc DoD cấp release thay vì DoD của từng story. Nhóm cần nói rõ cấp nào chịu trách nhiệm để không có khoảng trống giữa “story đã xong” và “release đã sẵn sàng”.

### 4.5. Sau triển khai: xác nhận và học từ vận hành

Với thay đổi có rủi ro cao, DoD cấp release có thể yêu cầu xác minh sau triển khai:

- Health check và smoke test trên môi trường mục tiêu.
- Theo dõi log, metrics, trace và cảnh báo.
- Kiểm tra tỷ lệ lỗi, độ trễ và các chỉ số nghiệp vụ quan trọng.
- Xác nhận feature flag và phân phối lưu lượng đúng.
- Có người trực theo dõi và điều kiện rollback rõ ràng.

Kết quả production cung cấp bằng chứng bổ sung về môi trường thật. Nếu phát hiện lỗi, nhóm cần đưa bài học vào kiểm thử hồi quy và xem xét cập nhật DoD nếu đó là khoảng trống có tính hệ thống.

## 5. Xây dựng checklist DoD có phần kiểm thử

Một checklist mẫu cho hạng mục phát triển có thể gồm các nhóm điều kiện sau. Đây là điểm khởi đầu; mỗi nhóm nên điều chỉnh theo kiến trúc và rủi ro sản phẩm.

### 5.1. Yêu cầu và hành vi

- [ ] Hạng mục đáp ứng các tiêu chí chấp nhận đã thống nhất.
- [ ] Trường hợp thành công, lỗi và giá trị biên quan trọng đã được xem xét.
- [ ] Hành vi không mong muốn và quy tắc phân quyền được xác định khi liên quan.
- [ ] Không còn điểm mơ hồ có ảnh hưởng đến kết quả cần xác minh.

### 5.2. Mã nguồn và review

- [ ] Mã thay đổi đã được review theo quy trình của nhóm.
- [ ] Các góp ý bắt buộc đã được xử lý hoặc có quyết định rõ ràng.
- [ ] Quy tắc lint, format và phân tích tĩnh bắt buộc đã đạt.
- [ ] Không đưa bí mật, dữ liệu nhạy cảm hoặc cấu hình môi trường vào mã nguồn.

### 5.3. Kiểm thử và bằng chứng

- [ ] Unit test phù hợp với logic mới hoặc logic bị thay đổi đã chạy.
- [ ] Kiểm thử component, integration hoặc contract đã được chọn theo ranh giới bị ảnh hưởng.
- [ ] Kiểm thử hồi quy phù hợp với rủi ro đã chạy.
- [ ] Kiểm thử thủ công hoặc exploratory test đã được ghi nhận nếu cần.
- [ ] Kết quả đạt, thất bại, bỏ qua và flaky được phân biệt.
- [ ] Các lỗi còn mở có mức độ, người phụ trách và quyết định xử lý.
- [ ] Bằng chứng kiểm thử được liên kết với hạng mục hoặc pull request.

### 5.4. Dữ liệu, cấu hình và tài liệu

- [ ] Migration và khả năng tương thích dữ liệu đã được kiểm tra khi có thay đổi.
- [ ] Cấu hình, feature flag và biến môi trường liên quan đã được xác minh.
- [ ] API, tài liệu người dùng hoặc hướng dẫn vận hành bị ảnh hưởng đã được cập nhật.
- [ ] Dữ liệu kiểm thử không chứa thông tin nhạy cảm không cần thiết.

### 5.5. Sẵn sàng tích hợp và phát hành

- [ ] Thay đổi tích hợp được vào nhánh hoặc artifact mục tiêu theo quy trình.
- [ ] Các kiểm tra CI bắt buộc đã đạt.
- [ ] Rủi ro còn lại và phần chưa được xác minh đã được ghi nhận.
- [ ] Điều kiện triển khai, giám sát và rollback được cập nhật khi cần.

Không phải mọi hạng mục đều cần tất cả các mục trên. DoD chung nên ghi rõ các điều kiện bắt buộc và cách kích hoạt các yêu cầu bổ sung theo loại thay đổi.

## 6. Ví dụ DoD theo loại hạng mục

Một DoD chung cần đủ ổn định, nhưng nhóm có thể bổ sung checklist theo loại công việc. Ví dụ dưới đây minh họa cách áp dụng.

| Loại hạng mục | Bằng chứng kiểm thử cần thiết | Điều kiện hoàn tất bổ sung |
|---|---|---|
| Thay đổi logic tính toán | Unit test cho quy tắc, giá trị biên và trường hợp lỗi. | Kết quả tính toán được đối chiếu với ví dụ nghiệp vụ; không có assertion quan trọng bị bỏ qua. |
| Thay đổi API | Contract test và integration test cho request/response, mã lỗi và xác thực. | Tài liệu API và khả năng tương thích consumer được xem xét. |
| Thay đổi schema hoặc migration | Integration test với dữ liệu đại diện, kiểm tra nâng cấp và rollback nếu hỗ trợ. | Có kế hoạch triển khai migration và xử lý lỗi dữ liệu. |
| Thay đổi giao diện | Kiểm tra hành vi chính, trạng thái lỗi và nền tảng hỗ trợ. | Accessibility và responsive được kiểm tra theo tiêu chuẩn sản phẩm. |
| Thay đổi bảo mật | Kiểm thử quyền, xác thực, dữ liệu nhạy cảm và phân tích bảo mật phù hợp. | Lỗi bảo mật nghiêm trọng được xử lý hoặc có quyết định theo quy trình quản trị. |
| Thay đổi hiệu năng | Benchmark hoặc load test với tải, dữ liệu và ngưỡng đã thống nhất. | Kết quả đo, giới hạn môi trường và xu hướng được lưu lại. |
| Thay đổi cấu hình triển khai | Kiểm tra cấu hình, health check, khởi động và khả năng rollback. | Artifact và cấu hình đã được định danh đúng phiên bản. |

### 6.1. Ví dụ cụ thể: story thay đổi quy tắc giảm giá

Giả sử nhóm bổ sung quy tắc không cho phép áp dụng mã giảm giá đã hết hạn. Tiêu chí chấp nhận có thể gồm:

1. Mã còn hạn được áp dụng nếu đáp ứng điều kiện.
2. Mã hết hạn bị từ chối.
3. Thời điểm hết hạn được tính theo múi giờ đã quy định.
4. Hệ thống hiển thị thông báo phù hợp và không thay đổi tổng tiền sai.

DoD áp dụng cho story này có thể yêu cầu:

- Unit test cho thời điểm trước, đúng tại và sau thời điểm hết hạn.
- Integration test xác minh API trả kết quả nghiệp vụ phù hợp.
- Một kiểm thử giao diện đại diện xác nhận thông báo hiển thị đúng.
- Code review hoàn tất và CI đạt.
- Không còn lỗi nghiêm trọng liên quan đến tính toán hoặc thời gian.
- Tài liệu quy tắc giảm giá được cập nhật nếu hành vi đã thay đổi.

Bộ kiểm thử chi tiết về múi giờ và giá trị biên nằm ở unit test. Integration test xác minh ranh giới API; kiểm thử giao diện xác minh cách người dùng nhận kết quả. Các tầng có mục tiêu riêng nên không phải lặp lại toàn bộ cùng một bộ dữ liệu.

## 7. Vai trò và trách nhiệm trong việc thực hiện DoD

DoD là thỏa thuận của nhóm, không phải nhiệm vụ riêng của QA. Mỗi vai trò đóng góp bằng chứng trong phần việc mình kiểm soát.

| Vai trò | Trách nhiệm liên quan đến DoD |
|---|---|
| Product owner / người đại diện sản phẩm | Làm rõ nhu cầu, tiêu chí chấp nhận và mức độ quan trọng của hành vi. |
| Developer | Thiết kế thay đổi có thể kiểm tra, viết test phù hợp, xử lý lỗi và cập nhật tài liệu kỹ thuật. |
| QA / test engineer | Hỗ trợ phân tích rủi ro, thiết kế kiểm thử, đánh giá bằng chứng và chỉ ra khoảng trống. |
| Tech lead | Định hướng tiêu chuẩn kỹ thuật, review thiết kế và giải quyết vấn đề ảnh hưởng nhiều thành phần. |
| DevOps / SRE | Hỗ trợ CI, môi trường, cấu hình, quan sát hệ thống và khả năng triển khai/rollback. |
| Cả nhóm | Thống nhất DoD, tuân thủ, xem xét ngoại lệ và cải tiến dựa trên dữ liệu. |

QA có thể tư vấn và xác nhận chất lượng bằng chứng, nhưng không nên trở thành người duy nhất chịu trách nhiệm “làm cho story đạt DoD”. Người phát triển cần sở hữu kiểm thử cho thay đổi của mình; cả nhóm cùng chịu trách nhiệm về tiêu chuẩn hoàn tất.

## 8. Quản lý ngoại lệ và lỗi chưa xử lý

Trong thực tế, có thể xuất hiện một ca kiểm thử không chạy được do môi trường, một tích hợp chưa sẵn sàng hoặc một lỗi chưa thể sửa ngay. Nhóm cần quy trình minh bạch để xử lý mà không làm mất ý nghĩa của DoD.

### 8.1. Phân loại nguyên nhân

Khi một điều kiện chưa đạt, hãy xác định đó là:

- Lỗi sản phẩm.
- Lỗi hoặc dữ liệu sai trong bộ kiểm thử.
- Môi trường hoặc dịch vụ phụ thuộc không sẵn sàng.
- Kiểm thử chưa thực hiện do thiếu thời gian hoặc quyền truy cập.
- Điều kiện không áp dụng với loại thay đổi hiện tại.

Mỗi loại cần cách xử lý khác nhau. Ví dụ, lỗi môi trường có thể cần mở issue vận hành và chạy lại kiểm thử; lỗi sản phẩm cần sửa hoặc đánh giá rủi ro; một kiểm tra không áp dụng cần có lý do được thống nhất.

### 8.2. Không coi bỏ qua là đạt

Nếu một kiểm tra bắt buộc không chạy, trạng thái phải thể hiện rõ là bị bỏ qua hoặc chưa xác minh. Không đánh dấu đạt chỉ vì pipeline không báo lỗi.

Một ngoại lệ nên ghi:

- Điều kiện DoD chưa đạt và lý do.
- Phạm vi, phiên bản và rủi ro bị ảnh hưởng.
- Người đề xuất và người có thẩm quyền phê duyệt.
- Biện pháp giảm thiểu hoặc kiểm tra thay thế.
- Người phụ trách và thời hạn hoàn tất.
- Điều kiện xem xét lại hoặc thu hồi ngoại lệ.

### 8.3. Phân biệt ngoại lệ với thay đổi DoD

Ngoại lệ là quyết định tạm thời cho một trường hợp cụ thể. Thay đổi DoD là điều chỉnh thỏa thuận chung và cần được cả nhóm xem xét. Không nên tạo ngoại lệ lặp đi lặp lại cho cùng một vấn đề; nếu tiêu chuẩn không còn phù hợp hoặc quy trình có lỗ hổng, hãy cải tiến DoD chính thức.

### 8.4. Quy định quyền chấp nhận rủi ro

Người có quyền chấp nhận rủi ro phụ thuộc vào chính sách và mức ảnh hưởng. Một developer không nên tự bỏ qua kiểm tra bảo mật bắt buộc chỉ để merge nhanh. QA cũng không nên tự chấp nhận rủi ro nghiệp vụ vượt thẩm quyền.

Với rủi ro nghiêm trọng, cần chuyển đến người hoặc nhóm có thẩm quyền, ghi lại cơ sở quyết định và bảo đảm các bên liên quan hiểu phần chưa được xác minh.

## 9. Tự động hóa DoD trong quy trình CI/CD

Những điều kiện có thể kiểm tra bằng máy nên được tự động hóa để tạo kết quả nhất quán và giảm thao tác thủ công.

Ví dụ, pipeline có thể chạy:

- Format, lint và static analysis.
- Unit test và component test.
- Contract test và integration test phù hợp.
- Kiểm tra dependency, secret và lỗ hổng bảo mật.
- Build artifact và xác nhận metadata phiên bản.
- Smoke test hoặc end-to-end test cho các luồng quan trọng.

Kết quả pipeline nên được lưu và liên kết với commit, pull request hoặc artifact tương ứng. Nếu artifact thay đổi sau khi kiểm thử, nhóm cần xác định bằng chứng nào phải chạy lại.

### 9.1. Phân biệt kiểm tra chặn và kiểm tra cung cấp thông tin

Không phải mọi kiểm tra đều cần chặn merge. Có thể phân loại:

- **Gate bắt buộc:** thất bại thì không được hoàn tất bước tích hợp hoặc phát hành, trừ khi có ngoại lệ đúng thẩm quyền.
- **Kiểm tra cảnh báo:** kết quả cung cấp thông tin để nhóm đánh giá, nhưng không tự động chặn.
- **Kiểm tra theo lịch hoặc theo mốc:** chạy trên môi trường chuyên dụng, trước release hoặc sau triển khai.

Việc phân loại phải dựa trên rủi ro và khả năng tin cậy của kiểm tra. Một gate flaky cần được xử lý để khôi phục độ tin cậy; không nên giữ một gate liên tục bị bỏ qua.

### 9.2. Tránh tự động hóa hình thức

Pipeline xanh không chứng minh mọi mục tiêu chất lượng đều đạt. Nhóm cần xem xét test có kiểm tra đúng hành vi hay chỉ chạy qua mã; test có assertion có ý nghĩa hay chỉ xác nhận phản hồi tồn tại; và môi trường có đại diện cho điều kiện sử dụng hay không.

Các kiểm tra thủ công, exploratory test, đánh giá trải nghiệm, quyết định chấp nhận rủi ro và review nghiệp vụ vẫn có thể cần thiết. Hãy ghi nhận bằng chứng của chúng trong cùng luồng công việc.

## 10. Theo dõi hiệu quả của DoD

Sau khi áp dụng DoD, nhóm cần đánh giá xem tiêu chuẩn có giúp tăng chất lượng và giảm công việc dồn cuối kỳ hay không.

Các tín hiệu có thể theo dõi:

- Tỷ lệ hạng mục hoàn tất có đủ bằng chứng kiểm thử.
- Số lỗi được phát hiện trước và sau khi tích hợp.
- Số lỗi production liên quan đến khoảng trống trong DoD.
- Thời gian từ khi bắt đầu đến khi hạng mục đạt DoD.
- Tỷ lệ kiểm thử flaky hoặc gate bị bỏ qua.
- Số ngoại lệ đang mở và thời gian tồn tại của chúng.
- Tỷ lệ công việc phải mở lại do thiếu kiểm thử hoặc tài liệu.
- Thời gian pipeline và mức độ ổn định của môi trường.

Không nên dùng các chỉ số này để thúc đẩy nhóm chạy theo số lượng test hoặc hoàn tất checklist một cách máy móc. Mục đích là tìm điểm nghẽn và khoảng trống. Ví dụ, nếu nhiều story phải mở lại do thiếu kiểm thử tích hợp, nhóm có thể bổ sung hướng dẫn và môi trường tích hợp vào quy trình phát triển.

## 11. Duy trì và cải tiến DoD

DoD cần được xem xét khi kiến trúc, mức rủi ro, công cụ hoặc yêu cầu sản phẩm thay đổi. Nhóm có thể rà soát trong retrospective, sau sự cố hoặc trước một giai đoạn phát hành lớn.

Khi đề xuất thay đổi, hãy:

1. Nêu vấn đề hoặc khoảng trống đã quan sát.
2. Đưa ra bằng chứng như lỗi lọt qua, ngoại lệ lặp lại hoặc thời gian chờ.
3. Xác định điều kiện mới và cách kiểm chứng.
4. Đánh giá chi phí thực hiện và tác động đến tốc độ phát triển.
5. Thống nhất người chịu trách nhiệm và thời điểm áp dụng.
6. Cập nhật tài liệu nhóm, pipeline và hướng dẫn liên quan.
7. Theo dõi kết quả sau khi thay đổi.

Không nên thêm điều kiện vào DoD chỉ vì một lỗi đơn lẻ nếu điều kiện đó không giảm rủi ro có ý nghĩa. Ngược lại, một lỗi nghiêm trọng cho thấy khoảng trống lặp lại có thể là lý do cần bổ sung gate hoặc kiểm thử bắt buộc.

## 12. Mẫu Definition of Done có tích hợp kiểm thử

Mẫu sau có thể được điều chỉnh theo dự án. Nhóm nên thống nhất mục nào áp dụng chung, mục nào chỉ kích hoạt khi loại thay đổi hoặc mức rủi ro yêu cầu.

~~~text
DEFINITION OF DONE - HẠNG MỤC

Yêu cầu và hành vi
- Tiêu chí chấp nhận đã được đáp ứng.
- Trường hợp lỗi và giá trị biên quan trọng đã được xem xét.

Mã nguồn và review
- Code review hoàn tất.
- Các kiểm tra format, lint và phân tích tĩnh bắt buộc đạt.

Kiểm thử
- Unit test phù hợp với thay đổi đã chạy.
- Integration / contract / component test đã chạy khi ranh giới bị ảnh hưởng.
- Kiểm thử hồi quy theo rủi ro đã hoàn tất.
- Kiểm thử thủ công hoặc exploratory test có ghi nhận khi cần.
- Kết quả thất bại, bỏ qua và flaky được phân loại rõ.
- Bằng chứng được liên kết với hạng mục hoặc pull request.

Dữ liệu, cấu hình và tài liệu
- Migration và dữ liệu được kiểm tra khi có thay đổi.
- Cấu hình và feature flag liên quan đã được xác minh.
- Tài liệu bị ảnh hưởng đã được cập nhật.

Lỗi và rủi ro
- Không còn lỗi nghiêm trọng chưa có quyết định xử lý.
- Ngoại lệ có người phê duyệt, phạm vi và thời hạn.
- Rủi ro còn lại được ghi nhận và chuyển đúng người phụ trách.

Tích hợp / phát hành
- CI bắt buộc đạt.
- Artifact hoặc phiên bản mục tiêu được định danh.
- Điều kiện triển khai, giám sát và rollback được cập nhật khi cần.
~~~

Có thể dùng checklist ngắn hơn cho story và checklist mở rộng cho release. Điều quan trọng là người thực hiện biết rõ bằng chứng nào cần tạo và người review có thể xác nhận điều kiện hoàn tất.

## 13. Danh sách rà soát trước khi áp dụng DoD

- [ ] DoD được cả nhóm thống nhất và áp dụng nhất quán.
- [ ] DoD được phân biệt với tiêu chí chấp nhận và Definition of Ready.
- [ ] Mỗi điều kiện có kết quả quan sát được hoặc bằng chứng xác nhận.
- [ ] Kiểm thử được chọn theo thay đổi và rủi ro.
- [ ] Trách nhiệm kiểm thử được chia sẻ giữa phát triển, QA và các vai trò liên quan.
- [ ] Kiểm tra tự động được tích hợp vào CI/CD với gate rõ ràng.
- [ ] Kiểm tra thủ công và exploratory test có cách ghi nhận.
- [ ] Lỗi, kiểm tra bỏ qua và flaky được phân loại minh bạch.
- [ ] Ngoại lệ có người phê duyệt, lý do, thời hạn và rủi ro còn lại.
- [ ] DoD cấp story được phân biệt với điều kiện hoàn tất cấp release.
- [ ] Có cách đo hiệu quả và lịch xem xét cải tiến DoD.

## Kết luận

Tích hợp kiểm thử vào Definition of Done giúp nhóm xác định rõ bằng chứng chất lượng cần có trước khi coi một hạng mục là hoàn tất. DoD hiệu quả mô tả điều kiện có thể kiểm chứng, chọn mức kiểm thử theo rủi ro, phân công trách nhiệm, quy định cách xử lý thất bại và ngoại lệ, đồng thời liên kết kết quả với CI/CD và quyết định phát hành. Khi cả nhóm cùng sở hữu thỏa thuận này và cải tiến dựa trên bằng chứng, kiểm thử trở thành hoạt động liên tục trong phát triển thay vì công việc dồn lại ở cuối vòng đời.
