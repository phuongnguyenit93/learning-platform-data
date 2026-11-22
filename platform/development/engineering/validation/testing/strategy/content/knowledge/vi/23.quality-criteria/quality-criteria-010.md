# Rà soát tiêu chí khi mục tiêu hoặc điều kiện sản phẩm thay đổi

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích vì sao tiêu chí chất lượng cần được rà soát khi mục tiêu, người dùng, môi trường hoặc điều kiện vận hành của sản phẩm thay đổi.
- Phân biệt mục tiêu chất lượng, yêu cầu chất lượng, tiêu chí chấp nhận, SLI, SLO, ngưỡng cảnh báo và điều kiện phát hành.
- Nhận diện các tín hiệu kích hoạt việc rà soát tiêu chí, bao gồm thay đổi nghiệp vụ, kiến trúc, dữ liệu, tải, dependency, bảo mật và quy định.
- Đánh giá ảnh hưởng của thay đổi đến các thuộc tính chất lượng và các bên liên quan.
- Viết lại tiêu chí theo cách đo được, có ngữ cảnh, nguồn đo, cửa sổ đánh giá và điều kiện đạt/không đạt rõ ràng.
- Xử lý xung đột giữa các mục tiêu chất lượng và lựa chọn đánh đổi có căn cứ.
- Cập nhật phạm vi kiểm thử, dữ liệu, môi trường, giám sát và cổng chất lượng tương ứng với tiêu chí mới.
- Quản lý phiên bản, phê duyệt, ngoại lệ và truy vết để bảo đảm tiêu chí luôn phù hợp với sản phẩm.

## 1. Vì sao phải rà soát tiêu chí chất lượng?

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, tiêu chí chất lượng xác định mức độ mà sản phẩm phải đáp ứng các kỳ vọng về chức năng và thuộc tính vận hành. Chúng cung cấp căn cứ để thiết kế kiểm thử, đánh giá kết quả, quyết định phát hành và theo dõi chất lượng sau triển khai.

Tiêu chí từng phù hợp ở một giai đoạn có thể không còn phù hợp khi sản phẩm thay đổi. Một ứng dụng ban đầu chỉ phục vụ một nhóm nội bộ có thể mở rộng cho hàng nghìn khách hàng; một API vốn chỉ được gọi trong mạng nội bộ có thể trở thành giao diện đối tác; một quy trình thanh toán đơn giản có thể bổ sung nhiều phương thức, nhiều loại tiền tệ và xử lý bất đồng bộ. Khi mục tiêu hoặc điều kiện thay đổi, ngưỡng chất lượng cũ có thể quá lỏng, quá chặt hoặc đo sai điều người dùng thực sự quan tâm.

Nếu không rà soát, nhóm có thể tiếp tục kiểm thử theo những giả định đã lỗi thời. Pipeline vẫn xanh nhưng không bảo vệ rủi ro mới; SLO không phản ánh trải nghiệm hiện tại; dữ liệu test không đại diện cho quy mô mới; hoặc tiêu chí bảo mật không bao phủ luồng truy cập mới. Ngược lại, nếu thay đổi tiêu chí tùy tiện sau khi kết quả không đạt, tổ chức có thể làm mất tính khách quan và hạ thấp chất lượng mà không có quyết định minh bạch.

Rà soát tiêu chí là hoạt động có chủ đích nhằm xác nhận tiêu chí hiện tại còn phù hợp hay cần sửa đổi, bổ sung, loại bỏ hoặc phân tầng theo bối cảnh. Hoạt động này không nhất thiết diễn ra theo lịch cố định בלבד; nó cần được kích hoạt khi xuất hiện thay đổi có khả năng làm thay đổi kỳ vọng hoặc rủi ro chất lượng.

Rà soát đúng lúc giúp:

- Bảo đảm kiểm thử đo đúng điều người dùng và nghiệp vụ cần.
- Phát hiện yêu cầu chất lượng mới trước khi triển khai thay đổi.
- Tránh giữ lại ngưỡng đã lỗi thời hoặc không còn khả thi.
- Làm rõ đánh đổi giữa tốc độ, độ tin cậy, bảo mật, chi phí và khả năng mở rộng.
- Cập nhật test, dữ liệu, môi trường, monitoring và điều kiện phát hành đồng bộ.
- Ghi nhận ai phê duyệt thay đổi và rủi ro nào được chấp nhận.

## 2. Phân biệt các loại tiêu chí và mục tiêu chất lượng

Trước khi rà soát, cần hiểu chính xác đối tượng đang được điều chỉnh. Các thuật ngữ có thể được tổ chức sử dụng khác nhau, vì vậy nhóm nên thống nhất định nghĩa trong dự án.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Mục tiêu chất lượng | Kết quả rộng mà sản phẩm cần đạt | Người dùng có thể hoàn tất thanh toán đáng tin cậy trong giờ cao điểm. |
| Yêu cầu chất lượng | Mô tả thuộc tính hoặc điều kiện sản phẩm cần đáp ứng | Hệ thống phải duy trì tính sẵn sàng và bảo vệ giao dịch khỏi ghi nhận trùng. |
| Tiêu chí chấp nhận | Điều kiện cụ thể để chấp nhận một chức năng hoặc thay đổi | Khi callback thanh toán được gửi lặp, chỉ một giao dịch được ghi nhận thành công. |
| SLI (Service Level Indicator) | Chỉ số đo lường một khía cạnh của dịch vụ | Tỷ lệ request hợp lệ hoàn tất trong thời gian quy định. |
| SLO (Service Level Objective) | Mục tiêu định lượng cho một SLI trong cửa sổ xác định | 99,9% request thuộc phạm vi đo hoàn tất trong 500 ms trong cửa sổ 30 ngày. |
| SLA (Service Level Agreement) | Cam kết dịch vụ có tính thỏa thuận với bên sử dụng | Mức dịch vụ và cách xử lý khi không đáp ứng theo hợp đồng. |
| Ngưỡng cảnh báo | Mức kích hoạt điều tra hoặc hành động vận hành | Tỷ lệ lỗi vượt 1% trong 10 phút. |
| Cổng chất lượng/phát hành | Điều kiện phải đáp ứng trước khi chuyển giai đoạn | Không còn lỗi bảo mật nghiêm trọng chưa được xử lý hoặc chấp nhận theo quy trình. |

Không nên dùng các khái niệm này thay thế lẫn nhau. SLI là cách đo, SLO là mục tiêu cho chỉ số, còn SLA là cam kết với bên liên quan theo thỏa thuận. Một tiêu chí chấp nhận cho tính năng có thể được kiểm tra bằng test case; một SLO vận hành cần được đo liên tục bằng telemetry phù hợp.

### 2.1. Tiêu chí cần có ngữ cảnh

Một con số không có phạm vi và điều kiện đo thường không đủ để làm tiêu chí. Ví dụ “thời gian phản hồi dưới 500 ms” cần làm rõ:

- Endpoint hoặc hành trình nào được đo?
- Đo từ phía client, gateway hay service?
- Dùng p50, p95 hay p99?
- Tải, kích thước dữ liệu và cấu hình môi trường ra sao?
- Cửa sổ đo kéo dài bao lâu?
- Request lỗi hoặc timeout được tính như thế nào?
- Có loại trừ warm-up, health check hoặc traffic nội bộ không?

Nếu thiếu ngữ cảnh, hai nhóm có thể báo cáo cùng một con số nhưng đang đo hai hiện tượng khác nhau.

## 3. Những thay đổi kích hoạt việc rà soát

Rà soát tiêu chí nên được kích hoạt bởi các thay đổi có khả năng ảnh hưởng đến kỳ vọng chất lượng hoặc cách đo. Không phải mọi thay đổi nhỏ đều cần xem lại toàn bộ tiêu chí; cần xác định phạm vi tương ứng.

### 3.1. Thay đổi mục tiêu và chiến lược sản phẩm

- Sản phẩm chuyển từ thử nghiệm sang vận hành chính thức.
- Mở rộng từ người dùng nội bộ sang khách hàng bên ngoài.
- Thay đổi phân khúc, thị trường hoặc mô hình doanh thu.
- Bổ sung hành trình nghiệp vụ cốt lõi hoặc kênh sử dụng mới.
- Thay đổi cam kết trải nghiệm hoặc mức dịch vụ với khách hàng.
- Tăng mức độ quan trọng của hệ thống đối với hoạt động tổ chức.

Ví dụ, một công cụ báo cáo nội bộ trước đây chấp nhận hoàn tất trong vài phút có thể cần phản hồi gần thời gian thực khi được đưa vào màn hình điều hành trực tiếp.

### 3.2. Thay đổi người dùng và cách sử dụng

- Số lượng người dùng hoặc số tenant tăng đáng kể.
- Thêm nhóm người dùng có kỹ năng, thiết bị hoặc nhu cầu truy cập khác.
- Tỷ lệ hành trình đọc/ghi thay đổi.
- Tăng giao dịch theo mùa vụ hoặc chiến dịch.
- Người dùng bắt đầu sử dụng tính năng theo cách chưa được dự đoán.
- Yêu cầu về ngôn ngữ, khả năng truy cập hoặc trải nghiệm đa thiết bị thay đổi.

### 3.3. Thay đổi kiến trúc và công nghệ

- Tách hoặc hợp nhất service, chuyển sang kiến trúc phân tán.
- Thay database, cache, queue, runtime hoặc nền tảng triển khai.
- Chuyển từ xử lý đồng bộ sang bất đồng bộ.
- Bổ sung multi-region, autoscaling hoặc disaster recovery.
- Thay đổi giao thức, API, event schema hoặc ranh giới trust.
- Nâng cấp dependency có thay đổi hành vi, hiệu năng hoặc bảo mật.

### 3.4. Thay đổi dữ liệu

- Tăng kích thước, tốc độ tăng hoặc mức độ đa dạng dữ liệu.
- Thêm trường, trạng thái, quan hệ hoặc kiểu dữ liệu mới.
- Thay đổi chính sách lưu trữ, xóa, ẩn danh hoặc đồng bộ.
- Dữ liệu có phân bố hoặc mức độ thiếu khác trước.
- Thêm dữ liệu nhạy cảm hoặc yêu cầu kiểm soát truy cập mới.

### 3.5. Thay đổi rủi ro và bối cảnh bên ngoài

- Xuất hiện lỗ hổng, sự cố hoặc kiểu tấn công mới.
- Quy định, tiêu chuẩn, hợp đồng hoặc yêu cầu kiểm toán thay đổi.
- Nhà cung cấp thay đổi SLA, API, quota hoặc khu vực triển khai.
- Hệ thống được dùng trong quy trình quan trọng hơn.
- Hậu quả của mất dữ liệu, gián đoạn hoặc sai giao dịch tăng lên.

### 3.6. Tín hiệu từ vận hành và kiểm thử

- SLO thường xuyên không đạt hoặc có xu hướng suy giảm.
- Nhiều lỗi lọt qua kiểm thử dù các cổng hiện tại đều Pass.
- Test flaky hoặc không còn đại diện cho môi trường thực tế.
- Alert tạo quá nhiều cảnh báo giả hoặc không phát hiện sự cố quan trọng.
- Chi phí vận hành hoặc tài nguyên vượt ngân sách.
- Người dùng phản ánh chất lượng không phù hợp dù metric kỹ thuật vẫn đạt.

## 4. Xác định điều gì đã thay đổi trong bối cảnh sản phẩm

Trước khi sửa tiêu chí, hãy mô tả bối cảnh cũ và mới. Nếu chỉ thấy một chỉ số thay đổi mà không hiểu nguyên nhân, nhóm có thể điều chỉnh sai mục tiêu.

### 4.1. Lập bản tóm tắt bối cảnh

Ghi nhận:

- Mục tiêu sản phẩm trước và sau thay đổi.
- Nhóm người dùng, tenant, thị trường và hành trình liên quan.
- Quy mô, tần suất và kiểu workload.
- Kiến trúc, dependency và môi trường triển khai.
- Dữ liệu, trạng thái và quy trình nghiệp vụ.
- Rủi ro, quy định và cam kết dịch vụ.
- Những giả định cũ không còn đúng.

### 4.2. Phân biệt tín hiệu với nguyên nhân

Ví dụ, p95 tăng từ 400 ms lên 900 ms có thể do lượng người dùng tăng, truy vấn mới, cache miss, database thay đổi, dependency chậm hoặc máy phát tải bị giới hạn. Không nên lập tức nới SLO lên 1 giây. Trước tiên cần xác định thay đổi nào gây ra hiện tượng và liệu mục tiêu người dùng có thực sự thay đổi hay không.

### 4.3. Xác định phạm vi ảnh hưởng

Liệt kê các thuộc tính chất lượng, hành trình, thành phần, nhóm người dùng và môi trường có thể bị tác động. Có thể dùng dependency map, phân tích dữ liệu, lịch sử sự cố, trace, test coverage và trao đổi với owner để tìm vùng ảnh hưởng.

Không nên rà soát một tiêu chí tách rời các tiêu chí liên quan. Ví dụ, tăng thời gian timeout có thể cải thiện tỷ lệ request hoàn tất nhưng làm tăng thời gian chờ, số request đồng thời và mức sử dụng connection.

## 5. Rà soát theo các thuộc tính chất lượng

Khi mục tiêu hoặc điều kiện thay đổi, cần xem thuộc tính nào bị ảnh hưởng. Có thể dùng mô hình chất lượng sản phẩm của tổ chức hoặc các nhóm thuộc tính phổ biến làm khung tham chiếu.

### 5.1. Tính phù hợp chức năng

Rà soát:

- Yêu cầu hoặc quy tắc nghiệp vụ mới.
- Kết quả mong đợi và điều kiện chấp nhận.
- Trường hợp ngoại lệ, trạng thái và quyền.
- Tính chính xác, đầy đủ và nhất quán của kết quả.
- Hành vi tương thích với quy trình hiện tại.

Ví dụ, bổ sung phương thức thanh toán trả sau làm xuất hiện trạng thái và điều kiện chấp nhận mới. Tiêu chí cần phân biệt “đã gửi yêu cầu”, “được chấp thuận”, “đã capture” và “đã đối soát”.

### 5.2. Hiệu năng và hiệu quả tài nguyên

Rà soát:

- Mục tiêu latency theo hành trình và phân vị.
- Throughput thành công và concurrency.
- Kích thước dữ liệu, tốc độ tăng và workload.
- CPU, memory, storage, network và giới hạn dependency.
- Thời gian xử lý tác vụ nền và backlog.
- Ngân sách tài nguyên và chi phí trên mỗi giao dịch.

Mục tiêu hiệu năng phải phản ánh tải dự kiến mới. Nếu lượng giao dịch tăng gấp nhiều lần, một SLO được thiết kế cho tải thấp có thể không còn phù hợp. Tuy nhiên, không nên nới ngưỡng trước khi xem xét tối ưu kiến trúc hoặc mở rộng tài nguyên.

### 5.3. Độ tin cậy và khả năng phục hồi

Rà soát:

- Tính sẵn sàng và thời gian gián đoạn cho phép.
- Tỷ lệ lỗi và thời gian phát hiện.
- RTO (Recovery Time Objective) và RPO (Recovery Point Objective) nếu áp dụng.
- Khả năng chịu lỗi dependency, retry, failover và degradation.
- Khả năng phục hồi sau deploy, restart hoặc mất vùng.
- Tính nhất quán và idempotency trong xử lý giao dịch.

Khi sản phẩm chuyển sang phục vụ quy trình liên tục, tiêu chí phục hồi và khả năng chịu lỗi có thể quan trọng hơn trước. Cần bổ sung kiểm thử fault injection, backup/restore hoặc disaster recovery nếu thuộc phạm vi.

### 5.4. Bảo mật và quyền riêng tư

Rà soát:

- Xác thực, phân quyền và phân tách tenant.
- Quản lý secret, token, key và chứng thư.
- Mã hóa dữ liệu khi truyền và lưu.
- Audit trail và khả năng truy nguyên thao tác nhạy cảm.
- Xử lý dữ liệu cá nhân, thời hạn lưu và quyền xóa.
- Threat model, bề mặt tấn công và dependency mới.
- Yêu cầu kiểm thử bảo mật và xử lý lỗ hổng.

Khi mở API cho đối tác hoặc khách hàng bên ngoài, ranh giới trust thay đổi. Các tiêu chí trước đây chỉ dựa trên mạng nội bộ có thể không còn đủ.

### 5.5. Tương thích và khả năng tương tác

Rà soát:

- Phiên bản API và schema.
- Tương thích ngược của consumer cũ.
- Trình duyệt, hệ điều hành, thiết bị và runtime hỗ trợ.
- Giao thức, encoding, timezone, locale và tiền tệ.
- Tương tác với dịch vụ bên thứ ba và giới hạn của họ.
- Hành vi khi nhiều phiên bản ứng dụng chạy song song trong rollout.

### 5.6. Khả năng sử dụng và khả năng truy cập

Rà soát:

- Thời gian hoàn thành tác vụ theo góc nhìn người dùng.
- Tỷ lệ hoàn thành và tỷ lệ bỏ dở hành trình.
- Tính rõ ràng của thông báo, lỗi và hướng dẫn.
- Hỗ trợ bàn phím, trình đọc màn hình, tương phản và cấu trúc nội dung.
- Hành vi trên thiết bị, kích thước màn hình và ngôn ngữ mới.
- Các bước thao tác hoặc yêu cầu nhận thức mới.

Metric backend tốt không tự chứng minh trải nghiệm tốt. Khi nhóm người dùng hoặc cách sử dụng thay đổi, cần có đánh giá người dùng, usability test hoặc accessibility test phù hợp.

### 5.7. Khả năng bảo trì, thay đổi và triển khai

Rà soát:

- Mức độ dễ thay đổi và kiểm tra các thành phần.
- Khả năng quan sát và chẩn đoán lỗi.
- Thời gian build, test và triển khai.
- Khả năng rollback, migration và tương thích phiên bản.
- Chất lượng tài liệu, ownership và cấu hình.
- Mức độ tự động hóa và độ tin cậy của pipeline.

Khi kiến trúc được tách thành nhiều service, tiêu chí về khả năng chẩn đoán, contract test và thời gian khôi phục có thể cần cập nhật.

## 6. Đánh giá ảnh hưởng và mức độ ưu tiên

Không phải mọi tiêu chí đều cần thay đổi khi sản phẩm thay đổi. Cần xác định mức độ liên quan và ưu tiên các tiêu chí có nguy cơ trở nên sai lệch.

### 6.1. Ma trận thay đổi – thuộc tính – tiêu chí

| Thay đổi | Thuộc tính có thể ảnh hưởng | Tiêu chí cần xem xét |
|---|---|---|
| Mở rộng số người dùng | Hiệu năng, khả năng mở rộng, độ tin cậy | Latency, throughput, concurrency, error rate, capacity. |
| Mở API ra bên ngoài | Bảo mật, tương thích, khả năng tương tác | AuthN/AuthZ, rate limit, schema compatibility, audit. |
| Thêm xử lý bất đồng bộ | Độ tin cậy, tính đúng đắn, quan sát | Queue lag, retry, idempotency, thời gian hoàn tất, trace. |
| Chuyển database | Hiệu năng, toàn vẹn dữ liệu, khả năng phục hồi | Query latency, migration accuracy, backup/restore, consistency. |
| Thêm nhóm người dùng mới | Khả năng sử dụng, truy cập, tương thích | Accessibility, locale, quyền, tỷ lệ hoàn thành hành trình. |
| Thay nhà cung cấp | Tương thích, độ tin cậy, bảo mật | Contract, timeout, quota, failover, data handling. |
| Thay quy định dữ liệu | Quyền riêng tư, bảo mật, audit | Consent, retention, deletion, access logging. |
| Mở rộng đa vùng | Độ tin cậy, hiệu năng, nhất quán | Failover, replication lag, RTO/RPO, latency theo vùng. |

### 6.2. Chấm mức độ ảnh hưởng

Có thể đánh giá theo các chiều:

- Mức độ thay đổi so với giả định cũ.
- Số thuộc tính chất lượng bị tác động.
- Mức độ quan trọng của hành trình và nhóm người dùng.
- Khả năng xảy ra lỗi và mức hậu quả.
- Khả năng đo lường hiện tại có đủ tin cậy không.
- Mức độ khó đảo ngược hoặc khôi phục.
- Nghĩa vụ hợp đồng hoặc quy định có liên quan.

Không nên chỉ cộng điểm rồi quyết định tự động. Một yêu cầu pháp lý hoặc bảo mật bắt buộc có thể cần ưu tiên dù xác suất sự cố thấp. Rủi ro nghiêm trọng cần người có thẩm quyền xem xét.

### 6.3. Xác định phần giữ nguyên

Rà soát cần xác định cả tiêu chí nào vẫn phù hợp. Không thay đổi một tiêu chí chỉ vì sản phẩm có thay đổi ở nơi khác. Ghi rõ “giữ nguyên” cùng lý do giúp tránh việc rà soát trở thành hoạt động thay ngưỡng không có căn cứ.

## 7. Viết lại tiêu chí sao cho đo được

Tiêu chí mới cần rõ ràng, kiểm chứng được và gắn với điều kiện sản phẩm mới. Một tiêu chí tốt tránh các từ mơ hồ như “nhanh”, “ổn định”, “dễ dùng” hoặc “an toàn” nếu không có định nghĩa vận hành.

### 7.1. Các thành phần của tiêu chí

Một tiêu chí định lượng hoặc định tính có thể gồm:

1. **Đối tượng**: chức năng, hành trình, service, nhóm người dùng hoặc dữ liệu.
2. **Thuộc tính**: latency, availability, correctness, access control, usability hoặc recovery.
3. **Chỉ số hoặc phép đánh giá**: SLI, test case, checklist, audit hoặc đánh giá người dùng.
4. **Ngưỡng/kết quả mong đợi**: giới hạn, tỷ lệ, trạng thái hoặc điều kiện đạt.
5. **Điều kiện vận hành**: tải, môi trường, cấu hình, dữ liệu, phiên bản và dependency.
6. **Cửa sổ thời gian**: thời điểm đo, thời lượng và tần suất.
7. **Nguồn dữ liệu**: telemetry, test report, log, trace hoặc khảo sát.
8. **Trách nhiệm**: owner, người phê duyệt và cách xử lý khi không đạt.

### 7.2. Mẫu câu cho tiêu chí

> Trong điều kiện **[môi trường và tải]**, đối với **[hành trình hoặc thành phần]**, hệ thống phải đạt **[chỉ số/ngưỡng]** trong **[cửa sổ đo]**, được xác minh bằng **[nguồn đo/test]**; nếu không đạt, **[hành động hoặc quyết định]**.

Ví dụ:

> Trong giờ cao điểm giả lập với 300 giao dịch đặt hàng mỗi phút trên cấu hình staging tương đương production, 95% yêu cầu xác nhận đơn hàng phải hoàn tất trong 2 giây, tỷ lệ lỗi kỹ thuật không vượt ngưỡng đã phê duyệt và mỗi yêu cầu idempotency chỉ tạo tối đa một đơn hàng. Kết quả được đo từ gateway và đối chiếu với dữ liệu đơn hàng cuối cùng.

Các con số trong ví dụ chỉ minh họa cách diễn đạt. Ngưỡng chính thức phải được thống nhất dựa trên mục tiêu sản phẩm, dữ liệu vận hành và năng lực hệ thống.

### 7.3. Phân biệt mục tiêu, ngưỡng cảnh báo và ngưỡng dừng

Một tiêu chí vận hành có thể có nhiều mức:

- **Mục tiêu**: mức cần đạt trong điều kiện bình thường.
- **Cảnh báo**: mức cho biết xu hướng cần điều tra hoặc hành động.
- **Ngưỡng dừng/an toàn**: mức cần dừng kiểm thử hoặc chuyển sang quy trình ứng phó để tránh tác động nghiêm trọng.
- **Điều kiện phát hành**: điều kiện được dùng để quyết định có chuyển giai đoạn hay không.

Không nên dùng một ngưỡng duy nhất cho mọi mục đích. Ví dụ, ngưỡng cảnh báo có thể nhạy hơn điều kiện chặn phát hành; ngưỡng dừng stress test cần ưu tiên an toàn môi trường.

### 7.4. Định nghĩa mẫu số và phạm vi đo

Với tỷ lệ, cần xác định tử số và mẫu số. Ví dụ “99,9% request thành công” cần làm rõ request nào được tính, cách xử lý client cancel, retry, health check và request nội bộ. Với tỷ lệ hoàn thành hành trình, mẫu số có thể là số phiên bắt đầu hoặc số người dùng đủ điều kiện; hai cách tính cho kết quả khác nhau.

Với thời gian, cần xác định điểm bắt đầu, điểm kết thúc và phân vị. Với tính sẵn sàng, cần xác định cách tính thời gian lỗi và các khoảng bảo trì được loại trừ theo thỏa thuận.

## 8. Xử lý xung đột giữa các mục tiêu chất lượng

Các thuộc tính chất lượng có thể xung đột. Tối ưu một tiêu chí có thể làm tiêu chí khác xấu đi.

Ví dụ:

- Tăng retry giúp tăng cơ hội hoàn tất nhưng có thể tăng tải và tạo giao dịch trùng.
- Tăng thời gian cache cải thiện latency nhưng có thể làm dữ liệu cũ hơn.
- Tăng mã hóa hoặc kiểm tra bảo mật có thể tăng chi phí CPU và latency.
- Tăng mức ghi log giúp điều tra nhưng có thể tăng storage, chi phí và nguy cơ lộ dữ liệu.
- Tăng mức sẵn sàng bằng nhiều bản sao có thể làm phức tạp tính nhất quán dữ liệu.
- Giảm thời gian timeout có thể giải phóng tài nguyên nhanh nhưng tăng tỷ lệ lỗi với dependency chậm.

### 8.1. Ghi nhận đánh đổi

Với mỗi xung đột, hãy ghi:

- Mục tiêu nào được ưu tiên và vì sao.
- Tiêu chí nào có thể bị ảnh hưởng.
- Mức suy giảm tối đa có thể chấp nhận.
- Biện pháp giảm thiểu hoặc giới hạn phạm vi.
- Cách đo và người chịu trách nhiệm theo dõi.
- Điều kiện cần xem xét lại quyết định.

### 8.2. Không hy sinh yêu cầu bắt buộc

Một số yêu cầu về bảo mật, quyền riêng tư, an toàn hoặc quy định không thể tự ý đánh đổi để đạt hiệu năng hoặc giảm chi phí. Nếu có xung đột, cần theo quy trình đánh giá và phê duyệt của tổ chức, đồng thời xác định giải pháp kiến trúc hoặc vận hành phù hợp.

### 8.3. Sử dụng ngân sách lỗi khi phù hợp

Trong vận hành dịch vụ, error budget có thể giúp cân bằng tốc độ thay đổi và độ tin cậy. Nó được suy ra từ SLO và lượng không đạt được cho phép trong cửa sổ đo. Khi ngân sách lỗi bị tiêu thụ nhanh, nhóm có thể giảm tốc độ phát hành hoặc ưu tiên cải thiện độ tin cậy. Cần dùng định nghĩa và chính sách của tổ chức; không áp dụng khái niệm này máy móc cho mọi thuộc tính chất lượng hoặc mọi loại sản phẩm.

## 9. Chuyển tiêu chí mới thành kế hoạch kiểm thử

Tiêu chí chỉ có giá trị khi được chuyển thành bằng chứng kiểm chứng được. Khi tiêu chí thay đổi, cần rà soát lại loại test, dữ liệu, môi trường, công cụ và thời điểm chạy.

### 9.1. Cập nhật ma trận tiêu chí – test

Với mỗi tiêu chí:

- Xác định test case, suite hoặc phép đánh giá liên quan.
- Chọn cấp kiểm thử phù hợp: unit, component, contract, integration, system, E2E hoặc non-functional.
- Xác định dữ liệu, trạng thái và dependency cần chuẩn bị.
- Chọn môi trường và cấu hình đại diện.
- Định nghĩa assertion, metric hoặc bằng chứng.
- Xác định tần suất chạy và trigger.
- Chỉ rõ owner và cách xử lý khi không đạt.

### 9.2. Bổ sung test khi tiêu chí mới xuất hiện

Ví dụ, khi sản phẩm hỗ trợ nhiều tenant, tiêu chí phân quyền cần kiểm tra cách ly dữ liệu giữa tenant. Bộ test trước đây chỉ có một tenant không còn đủ. Cần tạo dữ liệu ở ít nhất hai tenant, kiểm tra truy cập đúng quyền và thử truy cập chéo bị từ chối.

### 9.3. Sửa test khi cách đo thay đổi

Nếu SLO chuyển từ đo trung bình sang p95, báo cáo và cổng CI cần dùng đúng phân vị. Nếu điểm đo chuyển từ service nội bộ sang client, cần tính thêm network, gateway và xử lý phía client. Không nên so sánh trực tiếp số liệu cũ và mới nếu phương pháp đo khác nhau mà không ghi rõ.

### 9.4. Loại bỏ test hoặc tiêu chí lỗi thời

Khi một hành vi bị loại bỏ hoặc một tiêu chí không còn ý nghĩa, hãy truy vết các test, dashboard, alert và tài liệu đang sử dụng nó. Xóa tiêu chí mà không cập nhật các công cụ phụ thuộc có thể tạo cổng chất lượng sai hoặc báo cáo không nhất quán.

## 10. Cập nhật dữ liệu, môi trường và giám sát

Thay đổi tiêu chí thường kéo theo thay đổi ngoài mã test.

### 10.1. Dữ liệu kiểm thử

Rà soát:

- Quy mô và phân bố dữ liệu mới.
- Nhóm người dùng, trạng thái và trường hợp biên.
- Quan hệ và bất biến giữa các bản ghi.
- Dữ liệu lịch sử hoặc dữ liệu cần giữ để kiểm tra migration.
- Dữ liệu tổng hợp/ẩn danh và giới hạn quyền sử dụng.

### 10.2. Môi trường

Rà soát:

- Cấu hình và năng lực có đại diện cho mục tiêu mới không?
- Số instance, quota, database, cache và network có phù hợp không?
- Dependency và sandbox có cùng phiên bản hoặc hành vi cần kiểm tra không?
- Có thể mô phỏng tải, lỗi, vùng và trạng thái mới không?
- Có cần môi trường riêng cho stress, security hoặc recovery test không?

### 10.3. Monitoring và alert

Rà soát:

- Metric có đo đúng SLI mới không?
- Có đủ phân đoạn theo tenant, vùng, endpoint hoặc loại giao dịch không?
- Alert có ngưỡng và cửa sổ phù hợp không?
- Log và trace có đủ ngữ cảnh mà không lộ dữ liệu nhạy cảm không?
- Có dashboard để so sánh với baseline và mục tiêu mới không?
- Có runbook và owner cho alert quan trọng không?

### 10.4. Cổng CI/CD và phát hành

Nếu tiêu chí mới là điều kiện phát hành, cần cập nhật quality gate và kiểm tra cách xử lý kết quả thiếu, flaky, blocked hoặc inconclusive. Không nên chặn phát hành dựa trên một metric chưa được xác thực hoặc một test không ổn định mà không có quy trình xử lý.

## 11. Quản lý phiên bản và phê duyệt tiêu chí

Tiêu chí chất lượng là một phần của yêu cầu sản phẩm và cơ chế quản trị. Thay đổi cần có lịch sử để biết vì sao ngưỡng được điều chỉnh và kết quả trước/sau có thể so sánh đến đâu.

### 11.1. Version hóa tiêu chí

Mỗi thay đổi quan trọng nên ghi:

- Mã hoặc phiên bản tiêu chí.
- Nội dung trước và sau.
- Lý do và tín hiệu kích hoạt.
- Phạm vi sản phẩm, môi trường và người dùng áp dụng.
- Ngày hiệu lực và giai đoạn chuyển tiếp.
- Test, metric, dashboard và tài liệu bị ảnh hưởng.
- Người đề xuất, người review và người phê duyệt.

### 11.2. Phân công trách nhiệm

Tùy tổ chức, các vai trò có thể gồm:

- Product owner xác nhận mục tiêu và trải nghiệm mong đợi.
- Kiến trúc sư hoặc technical owner đánh giá khả năng kỹ thuật và đánh đổi.
- QA/test lead xác định phương pháp và bằng chứng kiểm thử.
- SRE/operations xác định SLI, SLO, monitoring và khả năng phục hồi.
- Security/privacy owner đánh giá kiểm soát và nghĩa vụ dữ liệu.
- Compliance/legal hoặc người có thẩm quyền xem xét yêu cầu chuyên ngành.

Một người có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ, nhưng trách nhiệm phê duyệt và chấp nhận rủi ro cần rõ ràng.

### 11.3. Quản lý ngoại lệ

Nếu chưa thể đáp ứng tiêu chí mới, cần ghi:

- Tiêu chí nào chưa đạt và bằng chứng hiện có.
- Nguyên nhân và mức độ ảnh hưởng.
- Biện pháp giảm thiểu tạm thời.
- Rủi ro còn lại và phạm vi người dùng bị tác động.
- Người có thẩm quyền chấp nhận.
- Thời hạn, điều kiện hết hiệu lực và kế hoạch khắc phục.

Ngoại lệ không nên trở thành trạng thái vĩnh viễn không được xem xét. Cần có ngày hết hạn hoặc trigger rà soát lại.

### 11.4. Giữ khả năng so sánh lịch sử

Khi đổi cách đo hoặc ngưỡng, cần ghi rõ thời điểm chuyển đổi. Nếu có thể, chạy song song cách đo cũ và mới trong một khoảng thời gian để hiểu khác biệt. Không nối hai chuỗi số liệu thành một xu hướng liên tục nếu định nghĩa SLI đã thay đổi đáng kể.

## 12. Ví dụ xuyên suốt: sản phẩm mở rộng từ nội bộ sang nhiều khách hàng

Giả sử một hệ thống quản lý đơn hàng ban đầu phục vụ 50 nhân viên nội bộ. Sản phẩm được mở rộng thành SaaS cho nhiều khách hàng, mỗi khách hàng có tenant riêng, số giao dịch cao hơn và API cho đối tác.

### 12.1. Tiêu chí cũ

- Chỉ kiểm tra một tenant.
- Độ trễ trung bình API dưới 1 giây trong môi trường test nhỏ.
- Nhân viên đăng nhập qua mạng nội bộ.
- Database backup theo lịch nhưng chưa có bài kiểm tra restore định kỳ.
- Một số thao tác quản trị được thực hiện bằng tài khoản chung.

Những tiêu chí này có thể phù hợp cho công cụ nội bộ, nhưng không đủ cho SaaS nhiều khách hàng.

### 12.2. Thay đổi bối cảnh

- Thêm tenant và người dùng bên ngoài.
- Tăng số request và số lượng dữ liệu.
- API được mở cho đối tác.
- Yêu cầu cách ly dữ liệu và audit chặt hơn.
- Hệ thống cần vận hành liên tục và có cam kết dịch vụ.
- Nhiều phiên bản client có thể tồn tại đồng thời.

### 12.3. Tiêu chí cần rà soát

| Thuộc tính | Tiêu chí cũ | Hướng cập nhật |
|---|---|---|
| Hiệu năng | Trung bình dưới 1 giây trên tải nhỏ | Xác định SLI theo endpoint/hành trình, p95/p99 và workload nhiều tenant. |
| Công suất | Không có mục tiêu rõ | Định nghĩa throughput thành công, concurrency và capacity theo giờ cao điểm. |
| Bảo mật | Đăng nhập mạng nội bộ | Kiểm tra xác thực, phân quyền, cách ly tenant, token và API đối tác. |
| Tương thích | Một client nội bộ | Hỗ trợ phiên bản API/client theo chính sách và kiểm tra tương thích ngược. |
| Độ tin cậy | Backup theo lịch | Xác định RTO/RPO, kiểm thử restore và failover theo mức dịch vụ. |
| Quan sát | Log ứng dụng cơ bản | Bổ sung correlation ID, metric theo tenant/endpoint, trace và audit. |
| Khả năng sử dụng | Nhân viên được đào tạo | Đánh giá onboarding, thông báo lỗi, accessibility và hành trình khách hàng. |

### 12.4. Chuyển thành kế hoạch kiểm thử

- Kiểm thử phân quyền với nhiều tenant, bao gồm truy cập chéo bị từ chối.
- Contract test cho API đối tác và client cũ.
- Load/capacity test với phân bố tenant và workload đại diện.
- Test migration, dữ liệu lớn và đối soát.
- Test backup/restore và failover theo mục tiêu phục hồi.
- Security test cho API public, token và audit.
- Usability/accessibility test với nhóm người dùng mục tiêu.
- Kiểm tra dashboard, alert và runbook trước khi phát hành.

### 12.5. Quản lý chuyển tiếp

Nhóm không cần thay tất cả tiêu chí trong một ngày. Có thể xác định các giai đoạn: trước khi mở beta, trước khi mở rộng khách hàng và trước khi ký cam kết dịch vụ. Mỗi giai đoạn có tiêu chí bắt buộc, ngoại lệ được phê duyệt và rủi ro còn lại. Sau khi traffic thực tế tăng, nhóm cần so sánh giả định workload với telemetry và cập nhật tiêu chí nếu cần.

## 13. Ví dụ khác: thay đổi điều kiện vận hành của một API

Giả sử API tra cứu trước đây chỉ được gọi nội bộ vài lần mỗi giây. Nay đối tác bên ngoài gọi API với lưu lượng biến động và có thể gửi request sai hoặc lặp.

Rà soát cần xem:

- **Hiệu năng**: thêm mục tiêu p95/p99 theo endpoint, throughput và rate limit.
- **Bảo mật**: xác thực client, scope, quota, chống lạm dụng và audit.
- **Tương thích**: versioning, schema, error code và chính sách deprecation.
- **Độ tin cậy**: timeout, circuit breaker, retry và hành vi khi dependency lỗi.
- **Quan sát**: metric theo client, correlation ID và khả năng phân biệt lỗi đối tác với lỗi dịch vụ.
- **Dữ liệu**: kiểm tra input validation, kích thước payload và thông tin nhạy cảm.
- **Vận hành**: runbook, alert, quota và cơ chế khóa client khi có sự cố.

Một tiêu chí như “API trả lời dưới 500 ms” chưa đủ. Cần nêu điều kiện tải, loại request, tỷ lệ lỗi, giới hạn client và hành vi khi vượt quota.

## 14. Những sai lầm thường gặp

- **Giữ tiêu chí cũ vì đã quen**: bối cảnh mới làm ngưỡng không còn phù hợp. Hãy rà soát theo các tín hiệu thay đổi.
- **Nới ngưỡng chỉ để đạt Pass**: làm giảm tính khách quan. Hãy phân tích nguyên nhân và phê duyệt thay đổi trước khi đánh giá lại.
- **Chỉ sửa một con số**: bỏ qua phạm vi, cửa sổ đo và mẫu số. Hãy định nghĩa đầy đủ cách đo.
- **Chỉ tập trung vào hiệu năng**: bỏ sót bảo mật, độ tin cậy, usability và khả năng phục hồi. Hãy rà soát nhiều thuộc tính liên quan.
- **Đặt tiêu chí không khả thi**: ngưỡng không dựa trên nhu cầu hoặc năng lực. Hãy dùng dữ liệu, thử nghiệm và đánh đổi được ghi nhận.
- **Không cập nhật test và monitoring**: tiêu chí mới không có bằng chứng. Hãy cập nhật test, metric, dashboard và alert đồng bộ.
- **Trộn số liệu cũ và mới**: phương pháp đo thay đổi khiến xu hướng không còn so sánh trực tiếp. Hãy version hóa SLI và thời điểm chuyển đổi.
- **Không phân biệt SLI, SLO và SLA**: dẫn đến hiểu sai cam kết và cách đo. Hãy thống nhất thuật ngữ.
- **Bỏ qua nhóm người dùng hiếm hoặc mới**: tiêu chí chỉ phản ánh người dùng phổ biến. Hãy xác định quần thể và hành trình mục tiêu.
- **Không có owner**: tiêu chí lỗi thời hoặc ngoại lệ kéo dài. Hãy giao trách nhiệm và thời hạn rà soát.
- **Không công khai rủi ro còn lại**: quyết định phát hành thiếu bối cảnh. Hãy ghi phần chưa đạt và người chấp nhận.
- **Rà soát quá rộng với mọi thay đổi nhỏ**: tạo chi phí không cần thiết. Hãy xác định phạm vi theo blast radius và rủi ro.

## 15. Hồ sơ rà soát tiêu chí chất lượng

Mỗi lần rà soát đáng kể nên để lại hồ sơ có thể truy vết.

| Trường | Nội dung cần ghi |
|---|---|
| Review ID | Mã ticket, change request hoặc phiên bản rà soát. |
| Trigger | Sự kiện hoặc thay đổi kích hoạt rà soát. |
| Bối cảnh cũ/mới | Mục tiêu, người dùng, workload, kiến trúc và điều kiện vận hành. |
| Tiêu chí bị ảnh hưởng | Mã và nội dung tiêu chí hiện tại. |
| Quyết định | Giữ nguyên, sửa, bổ sung, thay thế hoặc loại bỏ. |
| Tiêu chí mới | Phạm vi, chỉ số, ngưỡng, cửa sổ đo và nguồn bằng chứng. |
| Đánh đổi | Thuộc tính được ưu tiên và ảnh hưởng chấp nhận. |
| Test/monitoring bị ảnh hưởng | Test case, suite, SLI, dashboard, alert và quality gate. |
| Rủi ro còn lại | Phần chưa đạt, chưa đo hoặc chưa thể xác minh. |
| Phê duyệt | Người đề xuất, reviewer, owner và người chấp nhận rủi ro. |
| Hiệu lực | Ngày áp dụng, giai đoạn chuyển tiếp và ngày rà soát lại. |

Hồ sơ có thể ngắn với thay đổi nhỏ. Với thay đổi mục tiêu sản phẩm, bảo mật, dữ liệu hoặc cam kết dịch vụ, cần có đủ thông tin để người review hiểu lý do và tác động.

## 16. Quy trình rà soát tiêu chí khi điều kiện thay đổi

Nhóm có thể áp dụng trình tự sau:

1. **Nhận diện trigger**: ghi nhận thay đổi mục tiêu, người dùng, workload, kiến trúc, dữ liệu, dependency, rủi ro hoặc quy định.
2. **Mô tả bối cảnh mới**: so sánh giả định cũ và điều kiện hiện tại; xác định tín hiệu và nguyên nhân.
3. **Lập vùng ảnh hưởng**: xác định hành trình, thành phần, nhóm người dùng và thuộc tính chất lượng liên quan.
4. **Rà soát tiêu chí hiện tại**: đánh giá tiêu chí còn phù hợp, quá lỏng, quá chặt, không đo được hay thiếu phạm vi.
5. **Đánh giá đánh đổi và ưu tiên**: xem tác động, khả năng, nghĩa vụ bắt buộc và rủi ro còn lại.
6. **Viết tiêu chí cập nhật**: xác định đối tượng, chỉ số, ngưỡng, điều kiện, cửa sổ đo và nguồn bằng chứng.
7. **Cập nhật kế hoạch kiểm thử**: bổ sung hoặc sửa test, dữ liệu, môi trường, công cụ và tần suất chạy.
8. **Cập nhật monitoring và cổng chất lượng**: điều chỉnh SLI, SLO, alert, dashboard và điều kiện phát hành.
9. **Review và phê duyệt**: lấy ý kiến owner liên quan, ghi quyết định và quản lý ngoại lệ.
10. **Theo dõi sau thay đổi**: so sánh kết quả thực tế, kiểm tra giả định và đặt thời điểm rà soát tiếp theo.

## 17. Tự kiểm tra

Trước khi chốt một bộ tiêu chí đã được rà soát, hãy tự hỏi:

- Có trigger cụ thể cho lần rà soát này không?
- Mục tiêu sản phẩm, nhóm người dùng và điều kiện vận hành mới đã được mô tả chưa?
- Các giả định cũ nào không còn đúng?
- Những thuộc tính chất lượng nào bị ảnh hưởng trực tiếp hoặc gián tiếp?
- Tiêu chí hiện tại còn đo đúng điều người dùng và nghiệp vụ cần không?
- Chỉ số, mẫu số, ngưỡng, cửa sổ đo và nguồn bằng chứng đã rõ chưa?
- Các xung đột và đánh đổi đã được ghi nhận, phê duyệt đúng thẩm quyền chưa?
- Test, dữ liệu, môi trường, monitoring và quality gate đã được cập nhật đồng bộ chưa?
- Số liệu cũ và mới có thể so sánh không, hay cần đánh dấu phiên bản đo?
- Ngoại lệ có owner, thời hạn và kế hoạch khắc phục không?
- Rủi ro chưa được kiểm chứng có được công khai trước quyết định phát hành không?

## Kết luận

Tiêu chí chất lượng cần phản ánh mục tiêu và điều kiện thực tế của sản phẩm. Khi người dùng, workload, kiến trúc, dữ liệu, dependency, rủi ro hoặc nghĩa vụ bên ngoài thay đổi, nhóm cần xem lại các giả định và xác định thuộc tính chất lượng nào bị ảnh hưởng. Tiêu chí cập nhật phải có phạm vi, chỉ số, ngưỡng, điều kiện đo và nguồn bằng chứng rõ ràng; đồng thời cần xử lý đánh đổi, cập nhật test và monitoring, version hóa và phê duyệt minh bạch. Rà soát có truy vết giúp kiểm thử tiếp tục bảo vệ đúng điều quan trọng và giữ cho quyết định chất lượng phù hợp với bối cảnh mới.
