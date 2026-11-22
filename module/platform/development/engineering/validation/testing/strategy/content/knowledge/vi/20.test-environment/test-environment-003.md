# Đánh giá mức tương đồng cần thiết với production

## Mục tiêu bài học

Môi trường kiểm thử giúp nhóm thu thập bằng chứng về cách phần mềm hoạt động trước khi đưa thay đổi đến người dùng. Tuy nhiên, kết quả kiểm thử chỉ có ý nghĩa trong phạm vi những điều kiện mà môi trường đó đại diện. Một ứng dụng chạy tốt trên staging vẫn có thể gặp lỗi khi triển khai production nếu hai môi trường khác nhau ở cấu hình, dữ liệu, quyền truy cập, phụ thuộc, mạng, tải hoặc cách vận hành.

Trong chiến lược VALIDATION_TESTING_STRATEGY, mục tiêu không phải lúc nào cũng là sao chép production hoàn toàn. Nhóm cần đánh giá **mức tương đồng nào là cần thiết cho từng mục tiêu kiểm thử và từng loại rủi ro**. Unit test có thể chạy với phụ thuộc giả lập và dữ liệu nhỏ; kiểm thử tích hợp cần các dịch vụ và giao thức đại diện; kiểm thử hiệu năng cần quy mô tải và cấu hình tài nguyên gần với điều kiện dự kiến; diễn tập phục hồi cần kiểm tra các cơ chế backup, restore và chuyển vùng thực tế.

Sau bài học, người học có thể:

- Giải thích vì sao mức tương đồng giữa môi trường kiểm thử và production ảnh hưởng đến độ tin cậy của bằng chứng.
- Phân biệt tương đồng về kiến trúc, cấu hình, dữ liệu, phụ thuộc, mạng, tài nguyên và vận hành.
- Xác định khác biệt giữa môi trường kiểm thử và production có thể làm thay đổi kết quả.
- Chọn mức tương đồng phù hợp theo mục tiêu kiểm thử và rủi ro.
- Thiết kế cách mô phỏng hoặc thay thế phụ thuộc mà vẫn giữ được đặc tính cần xác minh.
- Quản lý dữ liệu đại diện, cấu hình, bí mật và quyền truy cập an toàn.
- Đánh giá sai khác còn lại, ghi nhận giới hạn bằng chứng và quyết định khi nào cần kiểm tra bổ sung.

## 1. Vì sao cần đánh giá mức tương đồng?

Môi trường kiểm thử là tổ hợp của ứng dụng, cấu hình, dữ liệu, dịch vụ phụ thuộc, hạ tầng và quy trình vận hành. Chỉ cần một yếu tố khác production ở đúng ranh giới quan trọng, hành vi có thể thay đổi.

Ví dụ:

- Staging dùng PostgreSQL nhưng production dùng một hệ quản trị cơ sở dữ liệu khác; truy vấn, kiểu dữ liệu hoặc hành vi transaction có thể khác.
- Staging dùng một instance duy nhất, trong khi production có nhiều instance chạy đồng thời; lỗi race condition hoặc cache phân tán chỉ xuất hiện ở production.
- Dữ liệu staging nhỏ và sạch, trong khi production có dữ liệu lớn, lịch sử lâu năm, bản ghi thiếu hoặc phân bố lệch; truy vấn và xử lý biên có thể chậm hoặc sai.
- Dịch vụ thanh toán staging luôn phản hồi nhanh, còn nhà cung cấp production có timeout, giới hạn tần suất và các trạng thái giao dịch không đồng bộ.
- Production bật TLS, xác thực dịch vụ và chính sách mạng chặt chẽ, trong khi staging cho phép truy cập rộng; lỗi chứng chỉ, quyền hoặc kết nối có thể bị bỏ sót.
- Môi trường kiểm thử dùng cấu hình feature flag khác production, làm cho luồng được kiểm tra không phải luồng sẽ phát hành.

Vì vậy, một kết quả “pass trên staging” không tự động chứng minh rằng production sẽ hoạt động giống hệt. Nhóm cần biết kết quả đó dựa trên điều kiện nào, khác biệt nào còn tồn tại và khác biệt nào có khả năng làm mất hiệu lực của bằng chứng.

## 2. Tương đồng không có nghĩa là sao chép toàn bộ production

Môi trường production thường có dữ liệu nhạy cảm, tải lớn, chi phí cao, tích hợp thật và tác động trực tiếp đến người dùng. Sao chép toàn bộ môi trường production cho mọi bài kiểm thử có thể không khả thi, không an toàn và không cần thiết.

Cách tiếp cận phù hợp là **tương đồng theo mục đích**:

- Với kiểm thử logic, cần kiểm soát đầu vào và hành vi phụ thuộc; không cần toàn bộ hạ tầng production.
- Với kiểm thử tích hợp, cần đúng giao thức, phiên bản và đặc tính quan trọng của các thành phần tương tác.
- Với kiểm thử hiệu năng, cần quy mô tài nguyên, dữ liệu, tải và topology đủ đại diện cho câu hỏi đo lường.
- Với kiểm thử bảo mật, cần cấu hình xác thực, phân quyền, mã hóa và ranh giới mạng tương ứng với production.
- Với kiểm thử phục hồi, cần kiểm tra quy trình backup, restore, failover và khả năng khôi phục thực tế.
- Với UAT, cần quy trình, vai trò, dữ liệu và thiết bị phản ánh công việc người dùng.

Mức tương đồng có thể khác nhau giữa các tầng kiểm thử và giữa các thành phần trong cùng một môi trường. Một số phụ thuộc có thể được giả lập để tạo tình huống xác định; những ranh giới có rủi ro cao vẫn cần xác minh với triển khai thật hoặc sandbox có đặc tính phù hợp.

## 3. Những chiều tương đồng cần đánh giá

Không nên chỉ hỏi “staging có giống production không?”. Hãy chia câu hỏi thành các chiều cụ thể để nhận diện sai khác và tác động.

### 3.1. Kiến trúc và topology

Xem xét các thành phần, cách kết nối và số lượng instance:

- Ứng dụng nguyên khối hay nhiều dịch vụ.
- Số instance, vùng triển khai và cách cân bằng tải.
- Cơ sở dữ liệu, cache, message broker và object storage.
- API gateway, ingress, service mesh và reverse proxy.
- Cơ chế discovery, routing và phân vùng.
- Các đường đi đồng bộ và bất đồng bộ.
- Thành phần dùng chung giữa nhiều tenant hoặc dịch vụ.

Nếu production có nhiều instance nhưng staging chỉ có một, kiểm thử có thể bỏ sót lỗi liên quan đến trạng thái trong bộ nhớ, session affinity, khóa phân tán hoặc xử lý đồng thời. Nếu production có nhiều vùng nhưng staging chỉ có một vùng, các vấn đề về độ trễ, chuyển vùng và phụ thuộc liên vùng có thể chưa được đánh giá.

### 3.2. Phiên bản phần mềm và phụ thuộc

Cần kiểm tra phiên bản của:

- Runtime, hệ điều hành và nền tảng container.
- Thư viện, framework và driver.
- Hệ quản trị cơ sở dữ liệu và phiên bản schema.
- Broker, cache, search engine và dịch vụ nền.
- API bên ngoài và phiên bản giao thức.
- Agent giám sát, proxy và thành phần bảo mật.

Một phiên bản mới có thể thay đổi mặc định, cách xử lý lỗi, thuật toán mã hóa, tối ưu truy vấn hoặc khả năng tương thích. Staging nên dùng cùng phiên bản với production khi mục tiêu là xác minh hành vi của phiên bản đó. Nếu không thể, cần ghi nhận sai khác và xác định kiểm thử nào bị ảnh hưởng.

### 3.3. Cấu hình và feature flag

Cấu hình thường làm thay đổi hành vi dù mã nguồn giống nhau:

- URL và endpoint dịch vụ.
- Timeout, retry, connection pool và giới hạn tài nguyên.
- Feature flag, gói dịch vụ và hạn mức.
- Locale, múi giờ, định dạng tiền tệ và ngày giờ.
- Cấu hình cache, session và cookie.
- Chính sách xác thực, quyền và thời hạn token.
- Cấu hình logging, tracing và sampling.
- Biến môi trường và tham số khởi chạy.

Không nên giả định rằng “cùng artifact” đồng nghĩa với “cùng hành vi”. Cần so sánh cấu hình đã triển khai, đồng thời tránh sao chép bí mật production vào môi trường kiểm thử. Những giá trị bí mật nên được quản lý qua cơ chế secrets riêng, còn cấu trúc và chính sách sử dụng cần tương ứng.

### 3.4. Dữ liệu và quy mô dữ liệu

Dữ liệu ảnh hưởng đến cả chức năng và hiệu năng:

- Số lượng bản ghi và kích thước bảng.
- Phân bố giá trị, mức độ lệch và số lượng giá trị duy nhất.
- Quan hệ giữa các thực thể và độ sâu lịch sử.
- Bản ghi thiếu, dữ liệu cũ hoặc trạng thái bất thường.
- Tỷ lệ đọc/ghi và mức độ đồng thời.
- Kích thước tệp, payload và thông điệp.
- Dữ liệu nhiều tenant và phân bố hoạt động giữa tenant.

Một tập dữ liệu nhỏ có thể đủ để kiểm tra quy tắc nghiệp vụ, nhưng không đủ để đánh giá truy vấn, index, phân trang hoặc thời gian xử lý. Dữ liệu kiểm thử cần đại diện cho đặc điểm có ảnh hưởng đến mục tiêu, không nhất thiết phải sao chép từng bản ghi production.

### 3.5. Dịch vụ bên ngoài và tích hợp

Xem xét các hệ thống mà ứng dụng gọi hoặc nhận dữ liệu:

- Cổng thanh toán, gửi email/SMS và nhà cung cấp định danh.
- Dịch vụ thuế, vận chuyển, bản đồ hoặc tìm kiếm.
- API của đối tác và hệ thống kế thừa.
- Hàng đợi, webhook và event stream.
- Dịch vụ cấp chứng thư, quản lý khóa hoặc secrets.

Sandbox có thể phù hợp để xác minh luồng nghiệp vụ, nhưng có thể khác production về độ trễ, giới hạn, dữ liệu, trạng thái lỗi hoặc khả năng đồng bộ. Nếu một rủi ro phụ thuộc vào đặc tính thật của nhà cung cấp, cần có kiểm tra bổ sung được kiểm soát.

### 3.6. Mạng và bảo mật

Các điều kiện mạng và bảo mật có thể khác đáng kể:

- DNS, routing, firewall và network policy.
- TLS, chứng thư, phiên bản giao thức và trust store.
- Xác thực giữa dịch vụ và quản lý danh tính.
- Quyền IAM, service account và quyền truy cập tài nguyên.
- Proxy, NAT, rate limit và giới hạn kết nối.
- Mã hóa dữ liệu khi truyền và khi lưu.
- Phân vùng mạng, tenant isolation và ranh giới tin cậy.

Nếu staging dùng tài khoản quản trị rộng hoặc bỏ qua xác thực giữa dịch vụ, kiểm thử tích hợp có thể pass dù production sẽ từ chối kết nối. Cần giữ nguyên đặc tính bảo mật liên quan đến mục tiêu, dùng danh tính và bí mật riêng cho từng môi trường.

### 3.7. Tài nguyên và tải vận hành

Đánh giá:

- CPU, bộ nhớ, dung lượng đĩa và I/O.
- Giới hạn container và quota.
- Số kết nối đồng thời và kích thước pool.
- Autoscaling, giới hạn scale và thời gian khởi động.
- Tải nền, lịch batch và tác vụ định kỳ.
- Cơ chế throttling, backpressure và queue depth.
- Tải đỉnh, tải trung bình và thời gian duy trì tải.

Một môi trường có tài nguyên dư thừa có thể che giấu lỗi timeout, giới hạn bộ nhớ hoặc hiệu năng suy giảm. Ngược lại, môi trường quá nhỏ có thể tạo ra lỗi không đại diện cho production. Mục tiêu là chọn quy mô đủ để trả lời câu hỏi kiểm thử.

### 3.8. Giám sát và quy trình vận hành

Production thường có hệ thống giám sát, cảnh báo, backup, triển khai và ứng phó sự cố mà staging có thể chưa có. Nếu mục tiêu là xác nhận khả năng vận hành, cần kiểm tra:

- Log, metric, trace và dashboard.
- Cảnh báo và ngưỡng cảnh báo.
- Runbook và hướng dẫn xử lý sự cố.
- Backup, restore và xác minh dữ liệu khôi phục.
- Rollback, roll-forward và feature flag.
- Quyền vận hành, phê duyệt và audit trail.
- Lịch batch, tác vụ nền và quy trình hỗ trợ người dùng.

Kiểm thử chức năng thành công không chứng minh đội vận hành có thể phát hiện và khắc phục sự cố. Mức tương đồng về quy trình cần phù hợp với mục tiêu operational acceptance.

## 4. Chọn mức tương đồng theo mục tiêu kiểm thử

Mỗi loại kiểm thử cần một mức tương đồng khác nhau. Bảng sau đưa ra hướng dẫn ban đầu; dự án cần điều chỉnh theo kiến trúc và rủi ro thực tế.

| Mục tiêu kiểm thử | Mức tương đồng cần ưu tiên | Khác biệt có thể chấp nhận khi được kiểm soát |
|---|---|---|
| Unit test | Hành vi của đối tượng và hợp đồng phụ thuộc cần được xác định. | Dùng stub, mock, fake và dữ liệu nhỏ. |
| Component test | Runtime, cấu hình và ranh giới thành phần liên quan. | Giả lập dịch vụ ngoài không thuộc mục tiêu. |
| API/contract test | Giao thức, schema, xác thực và phiên bản hợp đồng. | Dùng mock provider hoặc sandbox cho một số tương tác. |
| Integration test | Phiên bản và hành vi thực của database, broker hoặc dịch vụ tích hợp quan trọng. | Dùng container hoặc môi trường thử nghiệm thay cho production. |
| System/E2E test | Topology và luồng nghiệp vụ đủ đại diện cho hành trình cần xác minh. | Giới hạn quy mô và dùng dữ liệu tổng hợp. |
| Performance/load test | Tài nguyên, dữ liệu, topology, tải và cấu hình gần với mục tiêu vận hành. | Có thể dùng môi trường riêng được hiệu chỉnh và mô tả sai khác. |
| Security test | Danh tính, quyền, mã hóa, mạng và ranh giới tin cậy tương ứng. | Dùng tài khoản, dữ liệu và bí mật kiểm thử riêng. |
| UAT | Vai trò, quy trình, dữ liệu và thiết bị của người dùng. | Dùng dữ liệu tổng hợp và tích hợp sandbox nếu không làm mất mục tiêu đánh giá. |
| Resilience/DR test | Cơ chế failover, backup, restore và vận hành thực tế. | Có thể diễn tập trên vùng hoặc bản sao được kiểm soát, nhưng phải giữ đặc tính phục hồi cần kiểm tra. |

### 4.1. Unit và component test

Unit test chủ yếu kiểm tra logic trong phạm vi nhỏ. Môi trường cần nhất quán, nhanh và cô lập. Không cần tái tạo topology production nếu câu hỏi chỉ là quy tắc tính toán hoặc xử lý trạng thái.

Component test cần gần hơn với runtime và cấu hình của thành phần. Ví dụ, nếu ứng dụng chạy trên một runtime cụ thể hoặc dùng thư viện native, cần xác minh thành phần trong môi trường tương thích. Tuy nhiên, dịch vụ ngoài không liên quan có thể được thay bằng test double.

### 4.2. Integration và contract test

Với integration test, cần chọn phụ thuộc thật hoặc môi trường tương đương cho các đặc tính đang xác minh. Nếu cần kiểm tra transaction, hãy dùng đúng loại hệ quản trị cơ sở dữ liệu hoặc một phiên bản tương thích đã được chứng minh. Nếu cần kiểm tra serialization và routing, hãy dùng broker hoặc sandbox phù hợp.

Contract test tập trung vào giao tiếp giữa consumer và provider. Nó không đòi hỏi toàn bộ production topology, nhưng cần hợp đồng, phiên bản, provider state và cơ chế xác minh đại diện.

### 4.3. Performance test

Kiểm thử hiệu năng rất nhạy với khác biệt môi trường. Cần xem xét CPU, bộ nhớ, I/O, mạng, số instance, autoscaling, kích thước dữ liệu và các phụ thuộc. Nếu staging có tài nguyên khác production, kết quả không nên được diễn giải như dự báo trực tiếp về production nếu chưa hiệu chỉnh.

Báo cáo cần nêu rõ tải, thời gian warm-up, thời gian duy trì, dữ liệu, topology, giới hạn tài nguyên và sai khác. Khi có thể, dùng môi trường hiệu năng chuyên biệt được xây dựng theo các đặc tính quan trọng của production.

### 4.4. Security và resilience test

Kiểm thử bảo mật cần môi trường có chính sách danh tính, quyền, TLS, network boundary và secrets phù hợp. Dùng cấu hình dễ dãi để tiện kiểm thử có thể bỏ sót lỗi production.

Kiểm thử resilience và disaster recovery cần xác minh những cơ chế thực sự được sử dụng: backup, restore, replication, failover, retry, queue recovery và quy trình vận hành. Một mô phỏng đơn giản có thể kiểm tra logic xử lý lỗi, nhưng không chứng minh quy trình khôi phục production hoạt động.

## 5. Lập bản đồ sai khác giữa môi trường kiểm thử và production

Trước khi quyết định staging đủ đại diện hay chưa, nhóm nên lập danh sách khác biệt có cấu trúc. Không nên chỉ dựa vào cảm giác rằng hai môi trường “gần giống nhau”.

### 5.1. Mẫu so sánh môi trường

| Chiều | Production | Môi trường kiểm thử | Sai khác | Rủi ro đối với kiểm thử |
|---|---|---|---|---|
| Runtime | Phiên bản đang chạy | Phiên bản kiểm thử | Khác/giống | Có thể thay đổi hành vi runtime hoặc thư viện. |
| Database | Engine, phiên bản, topology | Engine, phiên bản, topology | Khác/giống | Có thể ảnh hưởng SQL, transaction và hiệu năng. |
| Số instance | Nhiều instance | Một instance | Khác | Bỏ sót concurrency và cache phân tán. |
| Dữ liệu | Quy mô và phân bố thực | Tập dữ liệu tổng hợp nhỏ | Khác | Không đủ bằng chứng về tải và truy vấn lớn. |
| Xác thực | SSO, MFA, service identity | Tài khoản test đơn giản | Khác | Bỏ sót luồng xác thực và quyền thật. |
| Dịch vụ ngoài | Provider production | Sandbox | Khác | Có thể khác timeout, quota và trạng thái xử lý. |
| Mạng | TLS, firewall, proxy | Mạng nội bộ mở | Khác | Bỏ sót lỗi kết nối và chính sách bảo mật. |
| Giám sát | Dashboard, alert, tracing | Log cơ bản | Khác | Không xác minh được khả năng phát hiện sự cố. |

Đây là mẫu minh họa. Dự án nên ghi giá trị và phiên bản cụ thể, thời điểm đối chiếu, nguồn cấu hình và người xác nhận.

### 5.2. Phân loại sai khác

Có thể chia sai khác thành:

- **Không ảnh hưởng mục tiêu:** ví dụ tên miền nội bộ khác nhưng routing và TLS cần kiểm tra đã được xác minh tương đương.
- **Có ảnh hưởng nhưng được kiểm soát:** ví dụ sandbox thay provider thật, có kiểm thử bổ sung cho các trạng thái mà sandbox không mô phỏng.
- **Chưa rõ ảnh hưởng:** cần thử nghiệm hoặc thu thập thêm bằng chứng.
- **Không chấp nhận được:** sai khác làm mất hiệu lực của kết quả đối với rủi ro trọng yếu.

Không nên mặc định một sai khác nhỏ về cấu hình là vô hại. Cần giải thích nó có thể tác động đến hành vi nào và bằng chứng nào chứng minh rủi ro đã được kiểm soát.

## 6. Đánh giá sai khác theo rủi ro

Không phải mọi chiều đều cần giống production ở mức tối đa. Ưu tiên phụ thuộc vào hậu quả nếu khác biệt làm thay đổi kết quả.

### 6.1. Các câu hỏi đánh giá

Với mỗi sai khác, hãy hỏi:

1. Sai khác có làm thay đổi đường đi xử lý hoặc quyết định nghiệp vụ không?
2. Nó có ảnh hưởng đến bảo mật, quyền riêng tư, tenant isolation hoặc tính toàn vẹn dữ liệu không?
3. Nó có làm thay đổi hiệu năng, concurrency, độ trễ hoặc khả năng phục hồi không?
4. Có lịch sử lỗi hoặc sự cố liên quan không?
5. Rủi ro có thể được kiểm tra bằng cách khác không?
6. Nếu bỏ sót, phạm vi ảnh hưởng và khả năng phát hiện sau phát hành là gì?
7. Có thể giới hạn tác động bằng canary, feature flag, rollback hoặc giám sát không?

### 6.2. Ma trận ưu tiên

| Mức rủi ro | Đặc điểm | Hướng xử lý |
|---|---|---|
| Cao | Sai khác có thể làm mất hiệu lực kiểm thử về bảo mật, dữ liệu, giao dịch, hiệu năng trọng yếu hoặc phục hồi. | Tăng tương đồng ở chiều liên quan hoặc bổ sung kiểm thử trên môi trường đại diện trước phát hành. |
| Trung bình | Có ảnh hưởng đến một số luồng hoặc điều kiện, nhưng có thể kiểm soát bằng kiểm tra bổ sung. | Ghi rõ sai khác, chạy kiểm thử mục tiêu và theo dõi sau triển khai. |
| Thấp | Sai khác không tác động đến mục tiêu hoặc đã có bằng chứng tương đương đáng tin cậy. | Chấp nhận có căn cứ, ghi lại và rà soát khi cấu hình thay đổi. |

Nếu rủi ro cao nhưng không thể tái tạo môi trường production, cần có biện pháp thay thế rõ ràng như kiểm thử contract, thử nghiệm kỹ thuật, kiểm tra cấu hình, diễn tập có kiểm soát hoặc rollout giới hạn. Không nên bỏ qua rủi ro chỉ vì chi phí tạo môi trường quá cao.

## 7. Dữ liệu production-like mà vẫn an toàn

Dữ liệu kiểm thử cần đại diện cho các đặc tính ảnh hưởng đến hành vi. Có thể dùng dữ liệu tổng hợp (synthetic data), dữ liệu đã ẩn danh hoặc dữ liệu mô phỏng theo thống kê.

### 7.1. Đặc tính cần giữ

Tùy mục tiêu, dữ liệu có thể cần đại diện cho:

- Số lượng bản ghi và kích thước bảng.
- Phân bố tenant và mức độ lệch giữa tenant lớn/nhỏ.
- Độ sâu quan hệ và số lượng bản ghi con.
- Tỷ lệ trạng thái bình thường, bị hủy, hết hạn hoặc lỗi.
- Giá trị rỗng, thiếu, trùng và biên.
- Kích thước payload, tệp và thông điệp.
- Lịch sử giao dịch và mức độ thay đổi theo thời gian.
- Các ràng buộc và bất biến nghiệp vụ.

Không cần sao chép nội dung thật nếu mục tiêu chỉ yêu cầu phân bố hoặc cấu trúc. Dữ liệu tổng hợp có thể tái tạo các đặc tính cần thiết mà không đưa thông tin cá nhân vào môi trường kiểm thử.

### 7.2. Bảo vệ dữ liệu nhạy cảm

- Ưu tiên dữ liệu tổng hợp.
- Nếu cần dùng dữ liệu nguồn, áp dụng quy trình ẩn danh hoặc giả danh phù hợp và đánh giá nguy cơ tái nhận diện.
- Không sao chép mật khẩu, token, khóa API, chứng thư riêng hoặc bí mật production.
- Giới hạn quyền truy cập và thời gian lưu dữ liệu.
- Ghi log và lưu artifact theo nguyên tắc tối thiểu.
- Có quy trình xóa dữ liệu và kiểm tra dữ liệu tồn dư.
- Tách biệt dữ liệu giữa các tenant và giữa các lần chạy.

Thay tên hoặc email không đủ để bảo đảm dữ liệu đã ẩn danh nếu các trường khác vẫn có thể liên kết đến một cá nhân. Cần tuân thủ chính sách dữ liệu của tổ chức.

### 7.3. Kiểm tra quy mô và phân bố

Với performance test, số lượng bản ghi đơn thuần chưa đủ. Một triệu bản ghi phân bố đồng đều có thể tạo tải khác một triệu bản ghi tập trung vào một tenant hoặc một khóa nóng. Cần xem xét phân bố, tính locality, quan hệ và mẫu truy cập gần với vận hành.

Nếu dữ liệu production thay đổi theo thời gian, cần ghi nhận thời điểm và cách tạo snapshot tổng hợp để kết quả có thể so sánh giữa các lần chạy.

## 8. Quản lý cấu hình và tránh configuration drift

Configuration drift là tình trạng cấu hình thực tế của các môi trường dần khác nhau so với cấu hình mong muốn hoặc khác nhau ngoài dự kiến. Drift có thể xuất hiện do chỉnh sửa thủ công, biến môi trường thiếu, phiên bản secret không đồng bộ hoặc quy trình triển khai khác nhau.

### 8.1. Các biện pháp kiểm soát

- Quản lý hạ tầng và cấu hình bằng mã (Infrastructure as Code) khi phù hợp.
- Dùng cùng artifact đã được kiểm thử để triển khai qua các môi trường.
- Quản lý phiên bản cấu hình và ghi nhận thay đổi.
- So sánh cấu hình triển khai với cấu hình chuẩn.
- Kiểm tra biến môi trường bắt buộc khi khởi động.
- Tách cấu hình không nhạy cảm khỏi bí mật.
- Quản lý secret riêng cho từng môi trường qua secret manager.
- Hạn chế chỉnh sửa thủ công không được ghi nhận.
- Có quy trình phê duyệt cho khác biệt có chủ đích.

### 8.2. Cùng artifact, cấu hình khác nhau

Một quy trình tốt thường tạo artifact một lần và triển khai artifact đó qua các môi trường. Cấu hình môi trường có thể khác nhau, nhưng cần có hợp đồng cấu hình rõ ràng và được xác minh.

Ví dụ, URL của payment provider có thể trỏ đến sandbox ở staging và endpoint production khi phát hành. Cấu trúc cấu hình, cơ chế xác thực, timeout, xử lý lỗi và schema cần được kiểm tra để bảo đảm khác biệt endpoint không che giấu lỗi tích hợp.

### 8.3. Kiểm tra drift định kỳ

Không chỉ so sánh cấu hình lúc tạo staging. Môi trường có thể thay đổi theo thời gian. Nên kiểm tra định kỳ hoặc trước phát hành:

- Phiên bản runtime và dịch vụ.
- Feature flag và cấu hình quan trọng.
- Quyền IAM và service identity.
- Chính sách mạng và chứng thư.
- Giới hạn tài nguyên và autoscaling.
- Schema database và migration.
- Tình trạng giám sát và cảnh báo.

Khi phát hiện drift, đánh giá xem kết quả kiểm thử trước đó còn hiệu lực không. Nếu thay đổi ảnh hưởng đến chiều đã kiểm tra, cần chạy lại các kiểm tra liên quan.

## 9. Lựa chọn phụ thuộc thật, sandbox hay mô phỏng

Mỗi lựa chọn tạo ra loại bằng chứng khác nhau.

| Lựa chọn | Giá trị | Giới hạn |
|---|---|---|
| Phụ thuộc thật trong môi trường kiểm thử | Kiểm tra giao thức, cấu hình và hành vi triển khai thực. | Có thể tốn tài nguyên, chậm và khó kiểm soát trạng thái. |
| Sandbox của nhà cung cấp | Kiểm tra luồng tích hợp mà không tạo tác động production. | Có thể khác dữ liệu, tải, quota, timeout hoặc hành vi lỗi. |
| Service virtualization/mock server | Tạo phản hồi xác định, bao phủ lỗi và tình huống hiếm. | Chỉ kiểm tra hành vi đã mô phỏng; không chứng minh provider thật tương thích. |
| Stub/fake trong unit test | Cô lập logic và kiểm tra nhánh xử lý nhanh. | Không tạo bằng chứng tích hợp thật. |
| Shadow traffic hoặc so sánh song song | Quan sát xử lý của phiên bản mới với bản sao request/dữ liệu phù hợp. | Cần bảo vệ dữ liệu, tránh tác động phụ và xử lý sai khác cẩn thận. |

### 9.1. Chọn theo câu hỏi cần trả lời

- Nếu cần kiểm tra logic khi provider trả timeout, dùng stub hoặc service virtualization để tạo lỗi xác định.
- Nếu cần kiểm tra request/response theo hợp đồng, dùng contract test.
- Nếu cần kiểm tra giao thức, serialization hoặc cấu hình kết nối, dùng sandbox hoặc phụ thuộc thật.
- Nếu cần đo độ trễ và giới hạn thật, sandbox chỉ có giá trị khi đặc tính đó đủ đại diện; có thể cần thử nghiệm được nhà cung cấp cho phép hoặc đo trong điều kiện production có kiểm soát.
- Nếu cần xác minh tác động end-to-end, kết hợp kiểm thử tích hợp và một số luồng hệ thống đại diện.

Không nên dùng một mock server duy nhất để kết luận mọi khía cạnh tích hợp đều an toàn. Cần nêu rõ phần nào được mô phỏng và phần nào đã được xác minh với phụ thuộc thật.

## 10. Thiết kế môi trường kiểm thử theo tầng

Một hệ thống có thể có nhiều môi trường phục vụ mục tiêu khác nhau. Không cần mỗi môi trường đều có độ tương đồng production như nhau.

### 10.1. Development/local

Môi trường local tối ưu tốc độ và khả năng phản hồi của nhà phát triển:

- Dùng dữ liệu nhỏ, tổng hợp và có thể reset.
- Dùng stub hoặc container cho phụ thuộc cần thiết.
- Cho phép debug và quan sát chi tiết.
- Tập trung unit test và component test.

Local không cần đại diện toàn bộ production, nhưng cần có cách chạy các kiểm tra quan trọng mà không phụ thuộc thao tác thủ công không được ghi nhận.

### 10.2. Integration/test

Môi trường này kiểm tra giao tiếp và phối hợp giữa thành phần:

- Dùng phiên bản database, broker và dịch vụ tương thích.
- Kiểm tra migration, transaction, contract và tích hợp.
- Quản lý dữ liệu và namespace cho nhiều lần chạy.
- Kiểm soát cấu hình và phiên bản phụ thuộc.
- Có thể dùng sandbox cho dịch vụ ngoài.

### 10.3. Staging/pre-production

Staging thường là nơi xác nhận tập hợp thay đổi trước production:

- Dùng artifact và cấu hình có cấu trúc gần production.
- Mô phỏng topology, quyền, tích hợp và luồng triển khai.
- Chạy E2E, smoke test, kiểm tra bảo mật và hiệu năng phù hợp.
- Xác minh backup, rollback hoặc quy trình phát hành khi cần.
- Ghi rõ các khác biệt về dữ liệu, tải, dịch vụ và quyền.

Staging không mặc nhiên đại diện production chỉ vì tên gọi. Mức tương đồng cần được chứng minh bằng so sánh cấu hình và mục tiêu kiểm thử.

### 10.4. Performance, security và resilience environment

Có thể cần môi trường chuyên biệt:

- Performance environment để tạo tải và đo tài nguyên.
- Security environment để kiểm tra chính sách, ranh giới và công cụ chuyên môn.
- Resilience/DR environment để diễn tập lỗi, failover và restore.

Các môi trường này có thể không giống production về mọi mặt, nhưng phải tái tạo chính xác những đặc tính liên quan đến mục tiêu đo hoặc kiểm chứng.

### 10.5. Production verification

Một số xác nhận chỉ có thể thực hiện sau triển khai. Có thể dùng:

- Smoke test với tài khoản và dữ liệu được phê duyệt.
- Health check và synthetic monitoring.
- Canary hoặc progressive rollout.
- Theo dõi metric, log, trace và chỉ số nghiệp vụ.
- Kiểm tra feature flag và khả năng tắt tính năng.
- Đối soát sau migration hoặc xử lý dữ liệu.

Production verification là lớp kiểm soát bổ sung, không thay thế việc kiểm thử trước phát hành. Các kiểm tra phải giới hạn tác động, không tạo giao dịch hoặc thay đổi dữ liệu thật ngoài phạm vi cho phép.

## 11. Đánh giá độ tương đồng cho hiệu năng và khả năng mở rộng

Kết quả performance test chỉ có thể so sánh khi các điều kiện đo được ghi rõ. Một môi trường staging có CPU, bộ nhớ, I/O, mạng hoặc số instance khác production có thể cho kết quả không thể so sánh trực tiếp.

### 11.1. Những yếu tố cần đại diện

- Số instance và cách phân phối request.
- CPU, bộ nhớ, I/O, network bandwidth và giới hạn container.
- Kích thước và phân bố dữ liệu.
- Cache warm/cold và tỷ lệ cache hit.
- Connection pool, thread pool và queue.
- Tải nền, batch job và tác vụ định kỳ.
- Mẫu truy cập, concurrency, think time và burst.
- Autoscaling, quota và thời gian khởi động.

### 11.2. Cách diễn giải kết quả

Báo cáo cần nêu:

- Mục tiêu và loại tải.
- Cấu hình môi trường và sai khác so với production.
- Dữ liệu và cách tạo dữ liệu.
- Thời gian warm-up, thời gian đo và số lần chạy.
- Latency percentiles, throughput, error rate và tài nguyên.
- Giới hạn hoặc điểm nghẽn quan sát được.
- Phạm vi ngoại suy và các giả định.

Không nên lấy kết quả staging nhỏ rồi nhân tuyến tính để dự đoán production nếu chưa xác minh khả năng mở rộng, điểm nghẽn và autoscaling. Khi không thể tạo môi trường tương đương, cần ghi rõ mức tin cậy và bổ sung giám sát hoặc thử nghiệm giới hạn sau triển khai.

## 12. Đánh giá độ tương đồng cho bảo mật và quyền truy cập

Môi trường kiểm thử cần giữ các đặc tính bảo mật có liên quan:

- Cơ chế xác thực và danh tính dịch vụ.
- Vai trò, quyền và phạm vi truy cập.
- Tenant isolation và phân vùng dữ liệu.
- TLS, chứng thư và cấu hình mã hóa.
- Network policy, firewall và service-to-service access.
- Quản lý secret và rotation.
- Audit log và truy vết hành động.
- Cấu hình cookie, session, CORS và header bảo mật khi phù hợp.

Có thể dùng tài khoản và bí mật riêng cho staging, nhưng không nên nới quyền quá mức hoặc bỏ qua các bước bảo mật mà production sẽ áp dụng. Nếu một chính sách chỉ tồn tại ở production, cần có kiểm thử cấu hình hoặc xác minh khác để bảo đảm chính sách đó được áp dụng trước khi phát hành.

Không thực hiện kiểm thử xâm nhập hoặc tải gây ảnh hưởng trên production nếu chưa có phạm vi và phê duyệt rõ ràng. Các kiểm tra chuyên sâu nên chạy trên môi trường được phép và có giới hạn tác động.

## 13. Ví dụ thực tế: đánh giá staging cho nền tảng SaaS nhiều tenant

Một nền tảng SaaS có nhiều tenant, dùng API gateway, dịch vụ ứng dụng, PostgreSQL, Redis và message broker. Production chạy nhiều instance trên hai vùng, có autoscaling, SSO, TLS nội bộ và dữ liệu lớn. Staging chỉ có một instance ứng dụng, dữ liệu tổng hợp nhỏ và dùng sandbox cho email.

Nhóm cần đánh giá các mục tiêu:

| Mục tiêu | Sai khác staging | Đánh giá và hành động |
|---|---|---|
| Logic phân quyền tenant | Dữ liệu tổng hợp có hai tenant. | Có thể kiểm tra quyền và truy cập chéo tenant; bổ sung test cho truy vấn, export và job nền. |
| Transaction database | Cùng engine và phiên bản PostgreSQL. | Có thể kiểm tra transaction và migration; đối chiếu cấu hình connection pool nếu khác. |
| Cache phân tán | Staging chỉ có một instance Redis. | Kiểm tra logic cache cơ bản; cần kiểm tra cấu hình HA/failover riêng nếu đó là rủi ro trọng yếu. |
| Concurrency | Ứng dụng staging chỉ có một instance. | Không đủ bằng chứng cho hành vi nhiều instance; bổ sung môi trường nhiều instance hoặc kiểm thử tích hợp chuyên biệt. |
| SSO và TLS | Staging dùng IdP thử nghiệm và chứng thư riêng. | Kiểm tra luồng giao thức và chính sách tương ứng; xác minh cấu hình production và trust chain trước phát hành. |
| Email | Dùng sandbox không gửi ra ngoài. | Xác minh nội dung, template và trạng thái; không kết luận khả năng gửi thật hoặc deliverability. |
| Hiệu năng | Dữ liệu nhỏ và tài nguyên thấp hơn production. | Không dùng kết quả trực tiếp để dự báo production; tạo performance environment với dữ liệu và tải đại diện. |
| Autoscaling và failover | Staging không có hai vùng. | Cần diễn tập ở môi trường phù hợp hoặc xác minh cấu hình, health check và quy trình DR riêng. |

Kết luận của nhóm không nên chỉ là “staging đạt”. Cần ghi rằng staging cung cấp bằng chứng tốt cho logic tenant, transaction và nội dung email, nhưng chưa đủ bằng chứng cho concurrency nhiều instance, autoscaling, failover và hiệu năng production. Các rủi ro còn lại cần được xử lý bằng kiểm thử chuyên biệt hoặc kiểm soát sau triển khai.

## 14. Theo dõi môi trường và tính nhất quán theo thời gian

Mức tương đồng có thể suy giảm sau khi môi trường được tạo. Một nhóm cập nhật thư viện ở staging nhưng quên production; một thay đổi thủ công điều chỉnh firewall; một feature flag bị bật khác nhau; hoặc một migration chỉ chạy ở một môi trường.

Nên duy trì:

- Danh mục môi trường và mục đích sử dụng.
- Chủ sở hữu và người chịu trách nhiệm.
- Phiên bản artifact, runtime và dịch vụ.
- Cấu hình chuẩn và nguồn quản lý cấu hình.
- Danh sách khác biệt có chủ đích.
- Kết quả so sánh drift.
- Lịch refresh dữ liệu và reset môi trường.
- Trạng thái health và phụ thuộc.
- Bằng chứng kiểm thử gần nhất và giới hạn của bằng chứng.

Trước một đợt phát hành quan trọng, rà soát các khác biệt đã biết và xác định có thay đổi nào khiến kiểm thử trước đó không còn đại diện hay không.

## 15. Quy trình đánh giá mức tương đồng

Có thể áp dụng quy trình sau cho một phiên bản, một luồng nghiệp vụ hoặc một môi trường:

1. **Xác định mục tiêu:** ghi rõ điều cần chứng minh, ví dụ tương thích API, hiệu năng, bảo mật hay khả năng phục hồi.
2. **Xác định rủi ro:** liệt kê hậu quả nếu môi trường kiểm thử khác production ở chiều liên quan.
3. **Lập bản đồ môi trường:** ghi kiến trúc, phiên bản, cấu hình, dữ liệu, phụ thuộc, mạng, tài nguyên và vận hành.
4. **So sánh sai khác:** ghi giá trị production, giá trị kiểm thử và nguồn xác nhận.
5. **Đánh giá tác động:** phân loại sai khác theo mức rủi ro và độ bất định.
6. **Chọn biện pháp:** tăng tương đồng, dùng sandbox, mô phỏng, kiểm thử chuyên biệt hoặc kiểm soát sau triển khai.
7. **Xác định tiêu chí đủ bằng chứng:** nêu điều kiện pass, giới hạn và rủi ro còn lại.
8. **Thực thi và lưu kết quả:** lưu phiên bản, cấu hình, dữ liệu, tải, log và bằng chứng.
9. **Rà soát trước phát hành:** kiểm tra drift và xác nhận sai khác chưa làm mất hiệu lực kết quả.
10. **Cập nhật sau sự cố:** nếu production gặp lỗi không xuất hiện ở staging, xem lại chiều tương đồng và bổ sung kiểm soát phù hợp.

## 16. Những sai lầm thường gặp

- **Coi staging giống production chỉ vì tên môi trường:** không có bằng chứng về cấu hình, topology hoặc phụ thuộc.
- **Sao chép toàn bộ production một cách máy móc:** tăng chi phí và rủi ro dữ liệu mà không làm rõ mục tiêu.
- **Dùng dữ liệu quá nhỏ cho performance test:** không phản ánh quy mô, phân bố hoặc truy vấn thực tế.
- **Dùng mock để kết luận tích hợp thật hoạt động:** bỏ qua giao thức, cấu hình, quota và lỗi của provider.
- **Nới lỏng bảo mật ở staging:** che giấu lỗi quyền, chứng thư và network policy.
- **Bỏ qua khác biệt phiên bản:** test trên runtime hoặc database khác mà không đánh giá ảnh hưởng.
- **Không ghi nhận sai khác có chủ đích:** người đọc kết quả không biết bằng chứng có giới hạn ở đâu.
- **Chỉ kiểm tra lúc tạo môi trường:** bỏ sót configuration drift về sau.
- **Dùng kết quả performance test để ngoại suy thiếu căn cứ:** không tính đến topology, autoscaling và điểm nghẽn.
- **Dùng production làm môi trường thử nghiệm mặc định:** có thể ảnh hưởng người dùng và dữ liệu thật.
- **Không có kiểm tra sau triển khai:** bỏ qua các đặc tính chỉ quan sát được trong vận hành.
- **Đánh dấu đạt dù mục tiêu chưa được kiểm tra:** tạo cảm giác an toàn giả.

## 17. Checklist trước khi chấp nhận mức tương đồng môi trường

- [ ] Mục tiêu và rủi ro của từng hoạt động kiểm thử đã được xác định.
- [ ] Kiến trúc và topology của môi trường đã được so sánh.
- [ ] Runtime, database, broker, cache và phiên bản phụ thuộc đã được đối chiếu.
- [ ] Cấu hình, feature flag, timeout, retry và giới hạn tài nguyên đã được rà soát.
- [ ] Dữ liệu có quy mô, phân bố và quan hệ đại diện cho mục tiêu.
- [ ] Dữ liệu nhạy cảm và bí mật được bảo vệ, không sao chép tùy tiện.
- [ ] Dịch vụ ngoài dùng thật, sandbox hay mô phỏng đã được ghi rõ.
- [ ] Mạng, TLS, danh tính và quyền truy cập có đặc tính phù hợp.
- [ ] Tài nguyên và tải đủ đại diện cho mục tiêu hiệu năng nếu có.
- [ ] Giám sát, cảnh báo, backup, restore và quy trình vận hành được kiểm tra khi cần.
- [ ] Sai khác được ghi nhận, đánh giá rủi ro và có biện pháp bổ sung.
- [ ] Configuration drift được kiểm soát và rà soát trước phát hành.
- [ ] Kết quả có giới hạn và giả định được mô tả rõ.
- [ ] Có kế hoạch production verification hoặc rollout kiểm soát cho rủi ro còn lại.

## Kết luận

Mức tương đồng giữa môi trường kiểm thử và production cần được lựa chọn theo mục tiêu và rủi ro, không phải theo một quy tắc sao chép toàn bộ. Hãy đánh giá riêng kiến trúc, phiên bản, cấu hình, dữ liệu, phụ thuộc, mạng, tài nguyên và vận hành; ghi rõ sai khác và xác định bằng chứng bổ sung cho những chiều chưa đại diện. Unit test có thể cần môi trường cô lập, trong khi kiểm thử tích hợp, hiệu năng, bảo mật và phục hồi cần các đặc tính production-like tương ứng. Một môi trường kiểm thử đáng tin cậy là môi trường có giới hạn được hiểu rõ, khác biệt được kiểm soát và kết quả đủ sức hỗ trợ quyết định phát hành.
