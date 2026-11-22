# Thể hiện phân bổ cấp độ, loại kiểm thử và kỹ thuật chính

Một tài liệu chiến lược kiểm thử cần cho người đọc thấy sản phẩm sẽ được xác thực ở đâu, bằng loại kiểm thử nào và dùng kỹ thuật gì để tạo bằng chứng. Nếu tài liệu chỉ liệt kê tên test hoặc ghi “có unit, integration và E2E”, nhóm chưa biết hành vi nào được kiểm tra ở từng cấp, rủi ro nào còn thiếu bằng chứng, hay vì sao một kiểm tra được đặt ở pipeline này thay vì pipeline khác. Ngược lại, nếu chỉ đặt tỷ lệ phần trăm cho từng cấp mà không liên kết với kiến trúc và rủi ro, nhóm có thể đạt chỉ tiêu số lượng nhưng vẫn bỏ sót những hành trình quan trọng.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, thể hiện phân bổ cấp độ, loại kiểm thử và kỹ thuật chính là cách mô tả có cấu trúc mối quan hệ giữa yêu cầu, rủi ro, ranh giới hệ thống, cấp kiểm thử, loại kiểm thử và kỹ thuật kiểm tra. Tài liệu phải giúp nhóm quyết định phần nào được kiểm tra sớm và gần thành phần, phần nào cần kiểm tra qua tích hợp hoặc toàn hệ thống, kỹ thuật nào tạo bằng chứng phù hợp, và khi nào cần mở rộng phạm vi. Phân bổ là quyết định dựa trên rủi ro và chi phí, không phải một tỷ lệ cố định áp dụng cho mọi sản phẩm.

## 1. Mục đích của bản phân bổ trong tài liệu chiến lược

### Trả lời ba câu hỏi cốt lõi

Một bản phân bổ tốt phải trả lời:

1. **Cấp độ nào?** Kiểm tra logic trong một đơn vị, một component, hợp đồng giữa hai thành phần, tích hợp nhiều dịch vụ, toàn hệ thống hay mức chấp nhận nghiệp vụ?
2. **Loại kiểm thử nào?** Kiểm tra chức năng, hồi quy, bảo mật, hiệu năng, độ tin cậy, khả năng tương thích, khả năng sử dụng hoặc một thuộc tính chất lượng khác?
3. **Kỹ thuật nào?** Dùng phân vùng tương đương, giá trị biên, bảng quyết định, chuyển trạng thái, kiểm tra hợp đồng, kiểm thử dựa trên thuộc tính, fault injection, exploratory testing hay kỹ thuật khác?

Ba chiều này có liên quan nhưng không đồng nhất. Cấp độ mô tả phạm vi và ranh giới được kiểm tra; loại kiểm thử mô tả mục tiêu hoặc thuộc tính cần xác minh; kỹ thuật mô tả cách thiết kế và thực hiện kiểm tra.

Ví dụ, kiểm thử bảo mật có thể được thực hiện ở cấp unit để xác minh hàm kiểm tra quyền, ở cấp API để kiểm tra xác thực và phân quyền, hoặc ở cấp hệ thống để kiểm tra luồng truy cập xuyên dịch vụ. Không nên gắn một loại kiểm thử với duy nhất một cấp.

### Thể hiện lựa chọn và lý do

Tài liệu không chỉ ghi một ma trận có dấu kiểm. Với mỗi vùng rủi ro quan trọng, cần giải thích:

- Hành vi hoặc thuộc tính cần xác minh.
- Lý do chọn cấp kiểm thử.
- Loại kiểm thử cần thực hiện.
- Kỹ thuật tạo dữ liệu và oracle.
- Môi trường và phụ thuộc cần thiết.
- Bằng chứng cần thu thập.
- Điều kiện mở rộng sang cấp sâu hơn.
- Owner và tần suất chạy.

Một quyết định “không kiểm tra ở E2E” cũng nên có lý do nếu người đọc có thể hiểu nhầm đó là khoảng trống. Ví dụ, quy tắc tính thuế được kiểm tra đầy đủ bằng unit và component test, còn E2E chỉ xác nhận tổng tiền được hiển thị và truyền đúng qua hành trình thanh toán.

### Hỗ trợ nhiều đối tượng sử dụng tài liệu

Bản phân bổ thường được dùng bởi:

- Kiến trúc sư và kỹ sư để hiểu ranh giới xác thực.
- QA/test engineer để thiết kế suite và kỹ thuật.
- Nhóm phát triển để biết kiểm tra nào cần nằm gần code.
- Nhóm CI/CD để cấu hình stage, gate và lịch chạy.
- Product owner để hiểu rủi ro nào được bảo vệ.
- Vận hành/SRE để biết kiểm tra nào cần môi trường hoặc quan sát production.

Vì vậy, tài liệu cần có phần tổng quan dễ đọc và các bảng chi tiết có thể truy vết đến test case, pipeline hoặc artifact thực tế.

## 2. Phân biệt cấp độ, loại kiểm thử và kỹ thuật

### Cấp độ kiểm thử

Cấp độ (test level) xác định đối tượng và ranh giới của kiểm tra. Một mô hình thường dùng gồm:

| Cấp độ | Đối tượng chính | Câu hỏi điển hình |
|---|---|---|
| Unit | Hàm, lớp hoặc đơn vị logic nhỏ | Quy tắc có đúng với đầu vào và trạng thái đã cho không? |
| Component | Một component hoặc dịch vụ trong phạm vi cô lập | Component xử lý dữ liệu, trạng thái và phụ thuộc của nó đúng không? |
| Contract/API | Hợp đồng giữa provider và consumer | Schema, mã lỗi, semantics và tương thích có được giữ không? |
| Integration | Tương tác giữa nhiều thành phần hoặc hạ tầng | Database, queue, API và worker phối hợp đúng không? |
| System | Hệ thống đã tích hợp như một tổng thể | Các luồng xuyên thành phần đáp ứng yêu cầu hệ thống không? |
| End-to-end | Hành trình nghiệp vụ từ điểm vào đến kết quả | Người dùng có thể hoàn thành mục tiêu trong điều kiện thực tế không? |
| Acceptance | Tiêu chí chấp nhận và mục tiêu nghiệp vụ | Sản phẩm có phù hợp nhu cầu và điều kiện chấp nhận không? |

Tên cấp độ có thể khác giữa tổ chức. Một số nhóm gộp system và E2E; một số nhóm coi contract test là loại kiểm tra ở ranh giới thay vì một cấp riêng. Tài liệu cần định nghĩa cách dùng thuật ngữ để các nhóm không hiểu khác nhau.

### Loại kiểm thử

Loại kiểm thử (test type) xác định mục tiêu hoặc thuộc tính được đánh giá. Có thể phân nhóm:

- **Functional:** hành vi, quy tắc nghiệp vụ, đầu vào/đầu ra và luồng xử lý.
- **Regression:** bảo đảm thay đổi không làm hỏng hành vi đã hoạt động.
- **Smoke/sanity:** xác nhận nhanh các chức năng và phụ thuộc thiết yếu.
- **Security:** xác thực, phân quyền, bảo vệ dữ liệu, lỗ hổng và cấu hình.
- **Performance:** latency, throughput, capacity và resource utilization.
- **Reliability/resilience:** timeout, retry, failover, phục hồi và xử lý lỗi.
- **Compatibility:** trình duyệt, thiết bị, runtime, phiên bản API và dữ liệu cũ.
- **Usability/accessibility:** khả năng hoàn thành tác vụ và khả năng tiếp cận.
- **Data quality/integrity:** tính đúng, nhất quán, đầy đủ và bảo toàn dữ liệu.
- **Installation/upgrade:** cài đặt, cấu hình, nâng cấp và migration.
- **Exploratory:** khám phá hành vi, rủi ro và tình huống chưa được mô hình hóa.

Một test có thể mang nhiều nhãn. Ví dụ, E2E tạo đơn hàng là functional regression; nếu kiểm tra thêm quyền tenant và dữ liệu thì có thể mang nhãn security hoặc data integrity cho các assertion tương ứng.

### Kỹ thuật kiểm thử

Kỹ thuật (test technique) mô tả cách chọn điều kiện, dữ liệu và bước kiểm tra. Một số kỹ thuật phổ biến:

| Kỹ thuật | Phù hợp khi | Ví dụ |
|---|---|---|
| Phân vùng tương đương | Đầu vào có các nhóm được xử lý tương tự | Mã giảm giá hợp lệ, hết hạn, không tồn tại |
| Phân tích giá trị biên | Lỗi dễ xuất hiện ở giới hạn | Số lượng tối thiểu, tối đa và ngoài giới hạn |
| Bảng quyết định | Kết quả phụ thuộc nhiều điều kiện kết hợp | Vai trò, trạng thái đơn và phương thức thanh toán |
| Chuyển trạng thái | Hành vi phụ thuộc trạng thái và thứ tự sự kiện | Đơn hàng từ PENDING sang PAID hoặc CANCELLED |
| Use-case/scenario | Cần xác minh một mục tiêu người dùng | Tạo, thanh toán và hủy đơn |
| Pairwise/combinatorial | Nhiều tham số kết hợp gây bùng nổ số trường hợp | Trình duyệt, vai trò, vùng và phương thức thanh toán |
| Error guessing | Có hiểu biết về lỗi thường gặp | Gửi request lặp, payload thiếu trường |
| Property-based | Có thuộc tính tổng quát cần đúng với nhiều đầu vào | Tổng phân bổ không vượt số lượng ban đầu |
| Fuzz testing | Cần kiểm tra đầu vào bất thường hoặc không tin cậy | Parser nhận dữ liệu ngẫu nhiên có giới hạn |
| Mutation testing | Muốn đánh giá khả năng phát hiện lỗi của test | Đổi toán tử hoặc điều kiện và kiểm tra test có fail |
| Fault injection | Cần xác minh hành vi khi phụ thuộc lỗi | Làm queue chậm hoặc API trả lỗi có kiểm soát |
| Exploratory testing | Cần khám phá rủi ro ngoài kịch bản định sẵn | Thử luồng sử dụng khác thường và ghi nhận quan sát |

Không cần liệt kê tất cả kỹ thuật trong mọi module. Chọn kỹ thuật dựa trên cấu trúc rủi ro và khả năng tạo oracle đáng tin cậy.

## 3. Nguyên tắc phân bổ

### Đặt kiểm tra ở cấp sớm nhất có thể tạo bằng chứng đáng tin

Quy tắc nghiệp vụ thuần thường nên được kiểm tra gần logic bằng unit hoặc component test vì chạy nhanh, dễ cô lập và dễ xác định nguyên nhân. Hành vi phụ thuộc giao tiếp, transaction, serialization hoặc broker cần test ở ranh giới tích hợp. Hành trình người dùng và cấu hình thực tế cần một số E2E đại diện.

“Cấp sớm nhất” không có nghĩa là mọi thứ phải bị mock. Nếu rủi ro nằm ở cách hai dịch vụ thực sự giao tiếp, mock một phía không tạo đủ bằng chứng. Hãy đặt test ở ranh giới nơi hành vi cần xác minh thực sự xảy ra.

### Phân bổ theo rủi ro, không theo số lượng test

Cân nhắc:

- Mức nghiêm trọng nếu hành vi sai.
- Khả năng xảy ra và tần suất sử dụng.
- Số người dùng, tenant hoặc dịch vụ bị ảnh hưởng.
- Khả năng phát hiện lỗi ở production.
- Chi phí sửa muộn và phục hồi.
- Độ phức tạp của logic và tích hợp.
- Lịch sử defect và thay đổi gần đây.
- Nghĩa vụ bảo mật, dữ liệu hoặc tuân thủ.

Một luồng thanh toán có thể cần nhiều lớp kiểm tra hơn một trang nội dung tĩnh. Một thư viện phân quyền dùng chung có thể cần unit, contract, integration và security regression vì phạm vi ảnh hưởng rộng.

### Dùng nhiều lớp bằng chứng bổ trợ

Không một cấp nào thay thế toàn bộ cấp khác:

- Unit test xác minh quy tắc và nhánh logic.
- Component test xác minh cách một thành phần phối hợp với phụ thuộc được kiểm soát.
- Contract test xác minh giao tiếp và tương thích.
- Integration test xác minh tương tác với hạ tầng hoặc dịch vụ thật trong phạm vi.
- E2E xác minh hành trình đại diện.
- Acceptance test xác nhận tiêu chí nghiệp vụ.
- Monitoring/synthetic check cung cấp tín hiệu sau triển khai.

Tài liệu cần tránh lặp cùng một assertion ở nhiều cấp mà không có giá trị bổ sung. Tuy nhiên, một số invariant quan trọng có thể được kiểm tra ở nhiều lớp để bảo vệ trước lỗi ở các ranh giới khác nhau.

### Cân bằng tốc độ, độ tin cậy và chi phí

Phân bổ phải xét:

- Thời gian phản hồi mong muốn của pull request.
- Chi phí runner và môi trường.
- Mức độ flaky và khả năng chạy song song.
- Thời gian chuẩn bị và dọn dữ liệu.
- Độ khó chẩn đoán.
- Phạm vi rủi ro được bao phủ.

Không giảm E2E chỉ vì chúng chậm nếu chúng bảo vệ hành trình có rủi ro cao. Có thể giảm số E2E trùng lặp, tối ưu dữ liệu, chạy theo shard hoặc đưa kiểm tra chi tiết xuống cấp phù hợp hơn, đồng thời giữ một số hành trình đại diện.

## 4. Thiết kế phân bổ theo cấp độ

### Unit test

Nên ưu tiên unit test cho:

- Quy tắc nghiệp vụ thuần.
- Tính toán, chuẩn hóa và validation.
- Quyết định theo bảng điều kiện.
- Chuyển trạng thái nội bộ.
- Xử lý lỗi và nhánh biên.
- Hàm biến đổi dữ liệu có invariant rõ.

Kỹ thuật thường dùng: phân vùng tương đương, giá trị biên, bảng quyết định, state-based test, property-based test và mutation testing.

Unit test không nên phụ thuộc network, clock thật hoặc dữ liệu dùng chung nếu có thể đưa các phụ thuộc qua abstraction. Test phải kiểm tra hành vi có ý nghĩa, không khóa chặt vào chi tiết triển khai không ổn định.

### Component test

Component test kiểm tra một thành phần trong ranh giới xác định, có thể dùng database hoặc adapter thật nhưng thay thế một số phụ thuộc ngoài phạm vi.

Dùng khi cần xác minh:

- Mapping và validation dữ liệu.
- Transaction và repository behavior.
- Xử lý message trong một worker.
- Cấu hình và dependency injection.
- Hành vi khi một adapter trả lỗi.
- Tính nhất quán của component.

Kỹ thuật gồm fixture theo trạng thái, contract nội bộ, kiểm tra invariant, fault simulation và kiểm tra vòng đời tài nguyên.

### Contract/API test

Contract test phù hợp khi nhiều provider và consumer cần phối hợp độc lập. Nó xác minh:

- Schema request/response hoặc event.
- Trường bắt buộc và tùy chọn.
- Mã lỗi và semantics.
- Quy tắc versioning.
- Tương thích ngược.
- Idempotency, pagination hoặc ordering nếu hợp đồng quy định.

Nên kiểm tra cả provider và consumer theo cách tổ chức áp dụng. Contract test không chứng minh toàn bộ nghiệp vụ hoặc độ sẵn sàng của mọi dịch vụ.

### Integration test

Integration test cần xác minh tương tác thật ở những ranh giới quan trọng:

- Ứng dụng với database.
- Producer với broker và consumer.
- API với dịch vụ bên ngoài sandbox.
- Transaction, outbox và retry.
- Cache invalidation và read model.
- Authentication giữa các dịch vụ.

Kỹ thuật thường dùng: dữ liệu có quan hệ, kiểm tra trạng thái trước/sau, fault injection có kiểm soát, đối soát event và xác minh eventual consistency.

### System, E2E và acceptance

Dùng system/E2E cho một tập hành trình đại diện có giá trị cao:

- Đăng nhập và phân quyền.
- Tạo, cập nhật và hoàn tất giao dịch.
- Luồng lỗi hoặc phục hồi quan trọng.
- Tương tác xuyên nhiều dịch vụ.
- Tương thích cấu hình triển khai thực tế.

Acceptance test gắn với tiêu chí chấp nhận của người dùng hoặc nghiệp vụ. Có thể dùng ví dụ cụ thể, BDD hoặc kịch bản người dùng. Không biến toàn bộ chi tiết logic thành E2E vì chi phí và độ không ổn định sẽ tăng.

## 5. Thiết kế phân bổ theo loại kiểm thử

### Functional và regression

Functional test cần được phân bổ xuyên nhiều cấp. Unit kiểm tra quy tắc; integration kiểm tra tương tác; E2E xác minh hành trình. Regression là mục đích chạy lại bằng chứng sau thay đổi, có thể bao gồm tất cả các cấp trên.

Tài liệu nên chỉ ra:

- Bộ test nhanh chạy cho mỗi thay đổi.
- Bộ test theo tác động.
- Hành trình cốt lõi chạy trước release.
- Full regression theo lịch hoặc theo rủi ro.
- Quy tắc mở rộng khi phân tích tác động không đáng tin.

Không đồng nhất regression với E2E. Unit và contract test cũng là thành phần quan trọng của hồi quy.

### Security

Phân bổ kiểm thử bảo mật theo ranh giới và loại rủi ro:

- Unit: kiểm tra policy, validation và quy tắc phân quyền.
- Component/API: xác minh authentication, authorization và input handling.
- Integration: kiểm tra quyền xuyên dịch vụ, secret và trust boundary.
- System: kiểm tra luồng dữ liệu, session, tenant isolation và cấu hình.
- Dynamic/security assessment: kiểm tra ứng dụng đang chạy theo phạm vi được phép.
- Review tĩnh: phân tích mã, dependency, secret và cấu hình.

Kỹ thuật có thể gồm negative testing, role/permission matrix, fuzzing, threat-based scenario và kiểm tra dữ liệu nhạy cảm. Phạm vi và môi trường cần được phê duyệt phù hợp.

### Performance và scalability

Không dồn toàn bộ kiểm thử hiệu năng vào E2E. Phân bổ:

- Unit/component: đo thuật toán hoặc xử lý dữ liệu cục bộ khi có ý nghĩa.
- Integration: đo query, serialization, broker và giao tiếp dịch vụ.
- System/load: đo throughput, latency và saturation của hệ thống.
- Stress/soak: kiểm tra giới hạn, suy giảm và ổn định theo thời gian.
- Capacity: kiểm tra khả năng tăng tải và tài nguyên.

Kỹ thuật gồm load profile, workload model, percentile analysis, baseline comparison và bottleneck analysis. Tài liệu cần ghi dataset, cấu hình môi trường, thời lượng warm-up và tiêu chí dừng.

### Reliability, resilience và recovery

Phân bổ kiểm tra cho các chế độ lỗi:

- Unit/component: timeout, retry, backoff và state transition.
- Integration: mất kết nối, message trùng, queue chậm hoặc dependency unavailable.
- System: failover, restart, recovery và degraded mode.
- Operational exercise: runbook, alert, backup restore và disaster recovery.

Kỹ thuật gồm fault injection, chaos experiment trong phạm vi kiểm soát, kiểm tra idempotency và kiểm tra phục hồi từ checkpoint. Cần có điều kiện an toàn, giới hạn blast radius và tiêu chí khôi phục.

### Compatibility, accessibility và usability

Các loại này có thể nằm ở nhiều cấp:

- Unit/component: format, keyboard behavior và logic responsive.
- System/UI: browser, device, viewport, locale và timezone.
- Acceptance/usability: hoàn thành tác vụ, hiểu thông báo và xử lý lỗi.
- Accessibility: keyboard navigation, semantic structure, contrast và screen reader behavior.

Dùng pairwise để giảm số tổ hợp nền tảng khi phù hợp, nhưng giữ các tổ hợp bắt buộc theo mức sử dụng và rủi ro.

## 6. Chọn kỹ thuật theo đặc tính yêu cầu

### Yêu cầu dựa trên đầu vào và quy tắc

Nếu yêu cầu có miền đầu vào rõ, dùng phân vùng tương đương và giá trị biên. Nếu kết quả phụ thuộc nhiều điều kiện, dùng bảng quyết định. Nếu hành vi phụ thuộc trạng thái và thứ tự, dùng state transition.

Ví dụ, quy tắc cấp quyền tải báo cáo có thể phụ thuộc vai trò, trạng thái tài khoản, tenant và loại dữ liệu. Bảng quyết định giúp liệt kê tổ hợp hợp lệ và bị từ chối.

### Yêu cầu có nhiều tham số kết hợp

Khi có nhiều tham số như trình duyệt, vai trò, ngôn ngữ, vùng và phương thức thanh toán, kiểm tra toàn bộ tích Descartes có thể quá tốn kém. Có thể dùng pairwise hoặc combinatorial testing để chọn tập hợp đại diện.

Tuy nhiên, pairwise chỉ bảo đảm mức kết hợp đã chọn. Nếu rủi ro xuất phát từ tương tác ba hoặc nhiều yếu tố, cần thêm trường hợp targeted theo phân tích rủi ro.

### Yêu cầu có invariant hoặc thuộc tính tổng quát

Property-based testing phù hợp khi có thuộc tính đúng cho nhiều đầu vào. Ví dụ:

- Tổng số lượng sau phân bổ không vượt số lượng ban đầu.
- Chuẩn hóa cùng một giá trị nhiều lần cho cùng kết quả.
- Mã hóa rồi giải mã khôi phục dữ liệu hợp lệ.
- Một thao tác idempotent không tạo thêm tác dụng phụ khi lặp.

Ghi seed và dữ liệu gây lỗi để có thể tái hiện. Khi tìm được counterexample, chuyển nó thành test hồi quy ổn định nếu phù hợp.

### Yêu cầu về xử lý lỗi và phục hồi

Fault injection phù hợp khi cần chứng minh hệ thống xử lý được tình huống lỗi. Chọn điểm tiêm lỗi theo dependency graph và rủi ro: timeout API, message delay, consumer restart, database connection loss hoặc lỗi nhà cung cấp sandbox.

Phải xác định trước trạng thái mong đợi, điều kiện dừng và cách khôi phục môi trường. Không thực hiện fault injection trên môi trường người dùng thật nếu chưa có phạm vi và phê duyệt phù hợp.

### Kỹ thuật khám phá

Exploratory testing có giá trị khi yêu cầu còn mơ hồ, luồng phức tạp hoặc có nhiều hành vi phát sinh. Ghi charter, mục tiêu, phạm vi, dữ liệu, quan sát và vấn đề phát hiện. Kết quả khám phá nên được phân loại thành defect, câu hỏi yêu cầu, rủi ro hoặc test tự động có thể bổ sung.

## 7. Liên kết yêu cầu, rủi ro, cấp độ, loại và kỹ thuật

### Dùng ma trận truy vết

Một ma trận phân bổ có thể dùng các cột:

| Trường | Ý nghĩa |
|---|---|
| Requirement/behavior | Hành vi hoặc thuộc tính cần xác minh |
| Risk ID | Rủi ro được kiểm soát |
| Component/boundary | Thành phần hoặc ranh giới liên quan |
| Test level | Cấp độ thực hiện |
| Test type | Loại kiểm thử |
| Technique | Kỹ thuật chính |
| Data/environment | Dữ liệu và môi trường |
| Oracle/evidence | Cách xác định pass/fail và bằng chứng |
| Pipeline stage | Khi nào chạy |
| Owner | Người hoặc nhóm chịu trách nhiệm |
| Status/gap | Trạng thái và khoảng trống còn lại |

Ma trận có thể liên kết đến test case, test suite hoặc pipeline thay vì sao chép chi tiết từng bước vào tài liệu chiến lược.

### Ví dụ ma trận cho luồng thanh toán

| Hành vi/rủi ro | Cấp độ | Loại | Kỹ thuật chính | Bằng chứng |
|---|---|---|---|---|
| Tính tổng, thuế và giảm giá sai | Unit/component | Functional/regression | Bảng quyết định, giá trị biên, property-based | Expected/actual và test report |
| API nhận sai trường tiền tệ | Contract/API | Contract/compatibility | Schema validation, negative cases | Contract verification |
| Callback trùng tạo giao dịch lặp | Integration | Reliability/data integrity | Idempotency scenario, message replay | Transaction và event IDs |
| Thanh toán không cập nhật trạng thái đơn | System/E2E | Functional/reliability | State transition, end-to-end scenario | Order/payment state và trace |
| Người dùng tenant khác xem giao dịch | API/system | Security | Role/tenant matrix, negative testing | Access decision và audit evidence |
| Hệ thống chậm khi tải tăng | System/load | Performance | Load profile, percentile analysis | Latency, throughput, resource metrics |

Ma trận này chỉ là ví dụ. Cần điều chỉnh theo kiến trúc, nhà cung cấp thanh toán, ranh giới dữ liệu và yêu cầu thực tế.

### Ghi nhận khoảng trống và quyết định chấp nhận rủi ro

Nếu một rủi ro chưa có test phù hợp, ghi:

- Lý do chưa có bằng chứng.
- Mức độ rủi ro còn lại.
- Biện pháp kiểm soát thay thế.
- Người chấp nhận rủi ro.
- Thời hạn hoặc điều kiện xem xét lại.
- Kế hoạch bổ sung test.

Không để ô trống trong ma trận bị hiểu nhầm là không có rủi ro. Phân biệt “không áp dụng”, “chưa triển khai”, “được kiểm tra ở nơi khác” và “đã chấp nhận rủi ro”.

## 8. Thể hiện tỷ trọng và phân bổ theo cấp độ

### Không áp dụng tỷ lệ phần trăm cứng cho mọi sản phẩm

Các mô hình như test pyramid hoặc test trophy là định hướng về cấu trúc và chi phí, không phải quota bắt buộc. Một sản phẩm có nhiều logic thuần có thể có tỷ trọng unit test cao. Một nền tảng tích hợp nhiều dịch vụ có thể cần nhiều contract và integration test. Một sản phẩm phần cứng hoặc giao diện có thể cần tỷ trọng system/acceptance cao hơn.

Nếu dùng tỷ lệ, phải ghi rõ mẫu số. Có thể đo theo:

- Số test case.
- Thời gian chạy.
- Chi phí compute.
- Công sức bảo trì.
- Số yêu cầu/rủi ro được bao phủ.
- Số lần chạy ở từng stage.

Tỷ lệ theo số test không tương đương tỷ lệ theo thời gian hoặc mức bảo vệ.

### Dùng mô hình phân bổ như điểm khởi đầu

Ví dụ định hướng:

- Unit/component: nhiều kiểm tra nhỏ, chạy nhanh, tập trung logic và trạng thái.
- Contract/integration: kiểm tra ranh giới và tương tác quan trọng.
- System/E2E: số lượng có chọn lọc, đại diện cho hành trình và cấu hình thực tế.
- Acceptance/exploratory: tập trung vào tiêu chí nghiệp vụ và vùng chưa mô hình hóa.
- Non-functional: phân bổ theo rủi ro, tải, dữ liệu và yêu cầu vận hành.

Đây là mô tả định tính. Nếu nhóm đặt mục tiêu phần trăm, hãy dùng dữ liệu lịch sử làm baseline và đánh giá tác động trước khi thay đổi.

### Đo sự cân bằng bằng nhiều chỉ số

Không chỉ hỏi “có bao nhiêu unit test?”. Hãy xem:

- Rủi ro quan trọng có test ở ranh giới phù hợp không?
- Tỷ lệ lỗi được phát hiện ở từng cấp.
- Thời gian phản hồi và chi phí của từng lớp.
- Tỷ lệ flaky và retry theo cấp.
- Mức trùng lặp assertion.
- Khả năng chẩn đoán khi fail.
- Phạm vi test bị skip hoặc cách ly.
- Tỷ lệ test được liên kết với yêu cầu/rủi ro.

Một suite có tỷ trọng unit cao nhưng thiếu integration test cho message hoặc transaction vẫn có thể có khoảng trống nghiêm trọng.

## 9. Gắn phân bổ với pipeline và nhịp phát hành

### Phân bổ theo vòng phản hồi

Một cấu hình điển hình:

| Thời điểm | Phạm vi thường chạy | Mục tiêu |
|---|---|---|
| Local/pre-commit | Unit, lint, static checks và test component nhanh | Phản hồi tức thì |
| Pull request | Unit/component, contract và test theo tác động | Chặn lỗi sớm trước review/merge |
| Sau tích hợp | Integration và E2E trọng yếu | Xác minh các ranh giới kết hợp |
| Nightly/scheduled | Regression rộng, compatibility và một số non-functional | Phát hiện tác động ngoài dự kiến |
| Pre-release | Full regression theo rủi ro, acceptance, security và performance cần thiết | Bằng chứng phát hành |
| Post-deploy | Smoke, synthetic và monitoring | Xác minh hành vi trong môi trường triển khai |

Không phải test nào cũng phải chạy ở mọi stage. Tài liệu cần quy định điều kiện chọn, điều kiện bỏ qua hợp lệ và fallback khi phân tích tác động không đáng tin.

### Xác định gate và điều kiện mở rộng

Với mỗi stage, ghi:

- Test bắt buộc.
- Tiêu chí pass/fail.
- Mức độ nghiêm trọng chặn pipeline.
- Quy tắc xử lý flaky.
- Điều kiện mở rộng test theo thay đổi.
- Hành vi khi môi trường hoặc phân tích tác động lỗi.
- Người có quyền chấp nhận ngoại lệ.

Không để công cụ chọn test tự động bỏ qua một kiểm tra bảo mật hoặc dữ liệu bắt buộc mà không có chính sách fallback.

### Kết nối test với artifact và quyết định release

Báo cáo cần cho biết:

- Test nào đã chạy và ở cấp nào.
- Loại và kỹ thuật đã dùng.
- Phiên bản, dữ liệu và môi trường.
- Test nào bị skip, blocked hoặc cách ly.
- Rủi ro nào chưa có bằng chứng.
- Gate nào đạt hoặc chưa đạt.
- Ngoại lệ nào được chấp nhận và bởi ai.

Nhờ đó, người ra quyết định có thể hiểu mức bảo vệ thực tế thay vì chỉ nhìn trạng thái xanh/đỏ của pipeline.

## 10. Ví dụ: phân bổ kiểm thử cho hệ thống thương mại điện tử

Giả sử hệ thống gồm catalog, cart, order, payment, inventory và notification. Các rủi ro chính là tính sai giá, tồn kho âm, thanh toán trùng, rò rỉ dữ liệu giữa tenant và thông báo gửi sai người nhận.

### Phân bổ theo hành vi

| Hành vi/rủi ro | Cấp ưu tiên | Loại kiểm thử | Kỹ thuật |
|---|---|---|---|
| Tính giá, thuế và mã giảm giá | Unit/component | Functional/regression | Decision table, boundary, property-based |
| Tồn kho không âm khi nhiều đơn đồng thời | Component/integration | Concurrency/data integrity | Invariant, concurrent scenario |
| API order và payment tương thích | Contract/API | Contract/compatibility | Schema và consumer contract |
| Callback thanh toán bị lặp | Integration | Reliability/regression | Idempotency và message replay |
| Hành trình đặt và hủy đơn | System/E2E | Functional/acceptance | Use-case và state transition |
| Tenant không truy cập dữ liệu của tenant khác | API/system | Security | Role/tenant matrix, negative tests |
| Email chỉ gửi đúng một lần cho người nhận | Integration/E2E | Functional/reliability | Event assertion và side-effect verification |
| Hệ thống chịu tải giờ cao điểm | System | Performance | Load, stress và percentile analysis |

### Phân bổ theo thời điểm

- Pull request: unit/component cho giá và tồn kho, contract cho order/payment, static security checks.
- Sau tích hợp: database/queue integration, idempotency và notification contract.
- Nightly: E2E hành trình đặt/hủy đơn, concurrency và regression rộng.
- Trước release: security assessment, performance theo profile đại diện, migration và acceptance.
- Sau deploy: smoke và synthetic checks cho đăng nhập, xem catalog và tạo đơn thử nghiệm được kiểm soát.

### Bảo đảm ma trận phản ánh kiến trúc

Nếu payment provider được thay thế, contract và integration test cần cập nhật. Nếu chỉ thay giao diện hiển thị tổng tiền, không nhất thiết chạy lại mọi kiểm tra concurrency ở mức sâu, nhưng vẫn cần xác minh tổng tiền và dữ liệu truyền qua hành trình. Phân bổ phải thay đổi theo ranh giới và rủi ro thực tế.

## 11. Quản trị và duy trì tài liệu phân bổ

### Xác định owner cho từng phần

Có thể phân công:

- Owner module chịu trách nhiệm rủi ro và hành vi nghiệp vụ.
- QA/test architect duy trì mô hình cấp độ và kỹ thuật.
- Nhóm phát triển duy trì unit/component và contract test.
- Nhóm platform duy trì pipeline, runner và test environment.
- Security/SRE phụ trách các loại kiểm tra chuyên môn.
- Product owner xác nhận tiêu chí chấp nhận và mức rủi ro.

Một ma trận không có owner sẽ nhanh chóng lỗi thời khi kiến trúc hoặc test suite thay đổi.

### Cập nhật khi có thay đổi

Rà soát bản phân bổ khi:

- Thêm hoặc bỏ module, service hoặc API.
- Thay đổi schema, event hoặc dependency.
- Thêm hành trình hoặc quy tắc nghiệp vụ.
- Có defect nghiêm trọng hoặc incident.
- Tỷ lệ flaky, thời gian chạy hoặc chi phí thay đổi đáng kể.
- Thay đổi nền tảng, trình duyệt hoặc môi trường.
- Một test bị cách ly hoặc loại bỏ.
- Thay đổi gate hoặc quy trình phát hành.

Không cần sửa toàn bộ tài liệu cho mọi commit. Cần có trigger và quy trình cập nhật theo tác động.

### Quản lý phiên bản và quyết định

Tài liệu nên ghi:

- Phiên bản và ngày cập nhật.
- Phạm vi sản phẩm.
- Người sở hữu và người phê duyệt.
- Thay đổi chính so với phiên bản trước.
- Quyết định phân bổ và lý do.
- Rủi ro hoặc ngoại lệ đang mở.
- Liên kết đến test catalog, pipeline và traceability.

Lưu lịch sử quyết định để nhóm hiểu vì sao một lớp test được thêm, chuyển hoặc loại bỏ.

## 12. Đo lường hiệu quả phân bổ

### Chỉ số về phạm vi và rủi ro

Theo dõi:

- Tỷ lệ yêu cầu/rủi ro quan trọng có test liên kết.
- Rủi ro chưa có bằng chứng hoặc chỉ có kiểm soát bù.
- Lỗi phát hiện ở từng cấp.
- Lỗi lọt qua các cấp đến staging hoặc production.
- Tỷ lệ test có owner và cập nhật gần đây.
- Số test bị skip, blocked hoặc cách ly.

Không diễn giải coverage theo dòng code như bằng chứng đầy đủ về coverage nghiệp vụ. Dùng traceability và risk coverage bổ sung.

### Chỉ số về tốc độ và độ ổn định

Theo dõi:

- Thời gian phản hồi theo stage.
- Thời gian chạy p50/p95 của từng cấp.
- Tỷ lệ pass lần đầu.
- Tỷ lệ flaky và retry.
- Thời gian điều tra lỗi.
- Chi phí runner và môi trường.
- Tỷ lệ test chạy song song an toàn.

Một lớp test quá chậm hoặc flaky có thể làm nhóm bỏ qua nó, vì vậy độ tin cậy là một phần của chất lượng phân bổ.

### Rà soát khoảng trống và trùng lặp

Định kỳ tìm:

- Rủi ro quan trọng chỉ được kiểm tra ở một E2E mong manh.
- Nhiều test lặp assertion nhưng không thêm bằng chứng.
- Ranh giới API hoặc event chưa có contract.
- Logic phức tạp chưa có test ở cấp gần.
- Hành trình quan trọng không có E2E hoặc acceptance evidence.
- Loại kiểm thử phi chức năng chưa được phân bổ.
- Test cũ không còn liên kết với yêu cầu hiện tại.

Điều chỉnh cấp và kỹ thuật để tăng giá trị bằng chứng, không chỉ tăng số test.

## 13. Những sai lầm thường gặp

- **Đồng nhất cấp độ với loại kiểm thử:** cho rằng security hoặc regression chỉ thuộc một cấp.
- **Dùng tỷ lệ phần trăm cứng:** chạy theo quota mà không dựa trên rủi ro.
- **Chỉ ghi tên suite:** không thể hiện hành vi, kỹ thuật và oracle.
- **Đẩy mọi kiểm tra lên E2E:** làm suite chậm, flaky và khó chẩn đoán.
- **Chỉ có unit test:** bỏ sót contract, transaction và tích hợp thật.
- **Mock toàn bộ phụ thuộc:** không tạo bằng chứng cho ranh giới quan trọng.
- **Lặp cùng assertion ở nhiều cấp:** tăng chi phí mà không tăng khả năng phát hiện.
- **Không kiểm tra loại phi chức năng:** bỏ qua security, performance, resilience hoặc compatibility.
- **Chỉ đo số lượng test:** không biết rủi ro nào được bảo vệ.
- **Không ghi lý do phân bổ:** khó thay đổi khi kiến trúc hoặc rủi ro đổi.
- **Không có fallback cho TIA hoặc metadata thiếu:** có thể bỏ sót test bắt buộc.
- **Không quản lý test bị cách ly:** vùng rủi ro mất bảo vệ kéo dài.
- **Không cập nhật sau incident:** lặp lại khoảng trống đã gây lỗi.
- **Không chỉ định owner:** ma trận nhanh chóng lỗi thời.

## 14. Đầu ra cần có trước khi chốt bản phân bổ kiểm thử

Một bản phân bổ đủ dùng nên có:

1. **Từ điển thuật ngữ:** định nghĩa cấp độ, loại và kỹ thuật theo cách dùng của tổ chức.
2. **Danh mục yêu cầu và rủi ro:** hành vi, thuộc tính và mức độ ảnh hưởng.
3. **Bản đồ kiến trúc:** module, service, API, event, dữ liệu và ranh giới.
4. **Ma trận phân bổ:** yêu cầu/rủi ro × cấp độ × loại × kỹ thuật.
5. **Lý do lựa chọn:** vì sao kiểm tra ở cấp đó và vì sao không cần lặp ở cấp khác.
6. **Kỹ thuật và oracle:** cách tạo dữ liệu, điều kiện và tiêu chí pass/fail.
7. **Môi trường và phụ thuộc:** nơi chạy, sandbox, dữ liệu và quyền.
8. **Kế hoạch pipeline:** stage, tần suất, gate và điều kiện mở rộng.
9. **Bằng chứng:** report, trace, artifact và liên kết test.
10. **Khoảng trống và ngoại lệ:** rủi ro chưa được kiểm tra, kiểm soát bù và người chấp nhận.
11. **Owner và quản trị:** trách nhiệm cập nhật, review và phê duyệt.
12. **Chỉ số đánh giá:** risk coverage, lỗi lọt, thời gian, flaky và chi phí.

Trước khi chốt, hãy rà soát:

- Cấp độ, loại và kỹ thuật có được phân biệt rõ không?
- Mỗi rủi ro quan trọng có ít nhất một cách tạo bằng chứng phù hợp không?
- Test có được đặt gần ranh giới tạo ra hành vi cần xác minh không?
- Các tích hợp quan trọng có contract hoặc integration evidence không?
- Hành trình nghiệp vụ cốt lõi có system/E2E hoặc acceptance evidence không?
- Security, performance, reliability, compatibility và data integrity đã được xem xét chưa?
- Kỹ thuật được chọn có phù hợp miền đầu vào, trạng thái và tổ hợp điều kiện không?
- Ma trận có oracle, dữ liệu, môi trường, stage và owner không?
- Tỷ trọng có dựa trên rủi ro và dữ liệu thực tế thay vì quota tùy ý không?
- Khoảng trống và ngoại lệ có owner, thời hạn và quyết định rủi ro không?
- Pipeline có gate và fallback khi phân tích tác động thiếu tin cậy không?
- Tài liệu có lịch cập nhật khi kiến trúc, lỗi và chi phí thay đổi không?

Thể hiện phân bổ cấp độ, loại kiểm thử và kỹ thuật chính giúp chiến lược kiểm thử chuyển từ danh sách hoạt động thành mô hình bằng chứng có thể thực thi và quản trị. Khi từng rủi ro được liên kết với cấp phù hợp, loại kiểm thử, kỹ thuật, oracle và thời điểm chạy, nhóm có thể phát hiện lỗi sớm, giảm kiểm tra trùng lặp và giải thích rõ phần rủi ro còn lại. Hãy xem bản phân bổ là tài liệu sống, được cập nhật theo kiến trúc, lịch sử lỗi, năng lực pipeline và yêu cầu sản phẩm.

