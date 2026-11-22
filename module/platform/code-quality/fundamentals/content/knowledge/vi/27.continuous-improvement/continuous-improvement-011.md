# Duy trì vòng phản hồi từ mã, kiểm thử, rà soát và vận hành

Một nhóm phát triển có thể hoàn thành nhiều pull request, chạy CI xanh và phát hành đúng lịch nhưng chất lượng phần mềm vẫn không tiến bộ. Lỗi cũ lặp lại ở những khu vực khác, test không bao phủ tình huống production thường gặp, cảnh báo vận hành không quay trở lại backlog, và cùng một nguyên nhân sự cố lại xuất hiện sau vài tháng. Vấn đề không nhất thiết nằm ở việc nhóm thiếu công cụ. Có thể nhóm đang thu thập tín hiệu ở từng giai đoạn nhưng chưa kết nối chúng thành một **vòng phản hồi liên tục**.

Vòng phản hồi giúp nhóm quan sát kết quả của quyết định kỹ thuật, học từ bằng chứng và điều chỉnh cách viết mã, kiểm thử, review, triển khai cũng như vận hành. Mỗi bước cần gửi thông tin hữu ích tới bước tiếp theo: lỗi trong test làm rõ hợp đồng; nhận xét review cải thiện thiết kế; dữ liệu production cho thấy giả định nào chưa đúng; sự cố tạo ra hành động phòng ngừa; kết quả của hành động lại được đo để biết nó có hiệu quả không.

Trong chương **Cải thiện liên tục** của module **CODE_QUALITY_FUNDAMENTALS**, bài học này tập trung vào việc duy trì vòng phản hồi từ **mã nguồn, kiểm thử, rà soát và vận hành**. Mục tiêu là giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi** qua những cải tiến nhỏ, có chủ sở hữu và có bằng chứng.

> Một vòng phản hồi chỉ khép kín khi tín hiệu dẫn tới quyết định, quyết định trở thành hành động, và kết quả của hành động được kiểm tra lại.

## 1. Vòng phản hồi liên tục là gì?

**Vòng phản hồi** (*feedback loop*) là chu trình thu thập thông tin về kết quả của một hoạt động, diễn giải thông tin đó, đưa ra điều chỉnh và quan sát tác động của điều chỉnh. Trong phát triển phần mềm, các vòng có thể diễn ra ở nhiều nhịp:

- **Trong lúc viết mã:** compiler, IDE, formatter và static analysis phản hồi trong vài giây hoặc vài phút.
- **Trong một thay đổi:** unit test, integration test và CI phản hồi trước khi merge.
- **Trong code review:** tác giả và reviewer cùng đánh giá hợp đồng, thiết kế và rủi ro.
- **Sau triển khai:** metrics, logs, traces, alert và phản hồi người dùng cho biết hệ thống hoạt động ra sao.
- **Sau sự cố hoặc theo chu kỳ:** nhóm xem lại nguyên nhân, thay đổi quy trình và đo hiệu quả phòng ngừa.

Các vòng này liên kết với nhau. Ví dụ, một lỗi timeout xuất hiện trong production có thể dẫn tới:

1. Thêm metric phân biệt timeout với lỗi từ chối nghiệp vụ.
2. Bổ sung test cho kết quả chưa xác định sau timeout.
3. Cải thiện code để xử lý idempotency.
4. Thêm nhận xét review yêu cầu mô tả retry contract.
5. Cập nhật cảnh báo và runbook.
6. Theo dõi xem lỗi tương tự có giảm sau phát hành không.

Nếu nhóm chỉ sửa một dòng code để dập lỗi rồi đóng ticket, vòng phản hồi chưa khép kín. Nếu nhóm chỉ tạo một dashboard mới nhưng không ai dùng nó để ra quyết định, tín hiệu cũng chưa tạo ra cải thiện.

### 1.1. Mô hình vòng phản hồi

~~~text
Viết mã và thay đổi thiết kế
          |
          v
Kiểm thử và CI
          |
          v
Rà soát và quyết định
          |
          v
Triển khai
          |
          v
Vận hành và phản hồi người dùng
          |
          v
Phân tích tín hiệu, lỗi và xu hướng
          |
          v
Chọn hành động cải tiến
          |
          +-------> quay lại mã, test, review hoặc vận hành
~~~

Đây là mô hình khái quát. Trong thực tế, các vòng không nhất thiết chạy tuần tự. Developer có thể nhận phản hồi từ production trong lúc một PR khác đang được review; một lỗi ở CI có thể làm nhóm cập nhật hướng dẫn trước khi triển khai.

### 1.2. Phản hồi khác với thu thập số liệu

Một hệ thống có thể có hàng trăm dashboard, hàng nghìn log và nhiều cảnh báo nhưng vẫn không cải thiện. Dữ liệu chỉ trở thành phản hồi hữu ích khi có:

- **Câu hỏi rõ:** nhóm đang muốn hiểu điều gì?
- **Tín hiệu phù hợp:** dữ liệu nào có thể trả lời câu hỏi?
- **Ngữ cảnh:** phiên bản, môi trường, luồng người dùng và thời điểm liên quan.
- **Người nhận:** ai có trách nhiệm xem và quyết định?
- **Hành động:** nếu tín hiệu cho thấy vấn đề, nhóm sẽ làm gì?
- **Xác minh:** làm sao biết hành động đã giảm vấn đề?

Ví dụ, đếm tổng số exception mỗi ngày có thể không hữu ích nếu không phân biệt lỗi đầu vào dự kiến, lỗi phụ thuộc và lỗi lập trình. Một metric tốt hơn có thể phân nhóm theo loại lỗi và endpoint, đồng thời tránh gắn dữ liệu định danh nhạy cảm vào nhãn.

### 1.3. Mục tiêu là học và cải thiện hệ thống

Vòng phản hồi không nhằm tìm người để quy trách nhiệm mỗi khi có lỗi. Nó giúp nhóm phát hiện:

- Giả định nào trong thiết kế không đúng với thực tế?
- Kiểm soát nào chưa phát hiện lỗi đủ sớm?
- Thông tin nào thiếu khiến việc điều tra mất nhiều thời gian?
- Quy trình nào khuyến khích workaround hoặc bỏ qua kiểm tra?
- Thay đổi nào có thể ngăn cùng loại lỗi tái diễn?

Trách nhiệm cá nhân vẫn quan trọng, nhưng một quy trình cải thiện tốt tìm cách làm cho hành vi đúng trở nên dễ thực hiện và lỗi khó lọt qua hơn.

## 2. Thiết kế phản hồi ở nhiều nhịp

Không phải mọi tín hiệu đều cần chờ đến production. Phản hồi càng gần thời điểm tạo ra lỗi thì thường càng dễ xác định nguyên nhân và ít tốn công sửa. Tuy nhiên, phản hồi nhanh không thể thay thế dữ liệu thực tế từ môi trường vận hành.

### 2.1. Vòng nhanh: trong lúc viết mã

Các tín hiệu:

- Compiler và type checker phát hiện lỗi cú pháp hoặc kiểu.
- IDE cảnh báo nullability, API lỗi thời hoặc import không dùng.
- Formatter và linter áp dụng quy ước chung.
- Unit test nhanh kiểm tra quy tắc cục bộ.
- Static analysis tìm một số mẫu lỗi có thể nhận diện.

Vòng nhanh nên có thời gian phản hồi ngắn và kết quả dễ hiểu. Nếu mỗi lần lưu file đều chạy một pipeline dài, developer sẽ ít dùng phản hồi hoặc trì hoãn việc kiểm tra.

### 2.2. Vòng PR: trước khi tích hợp thay đổi

Các tín hiệu:

- CI build và test trên đúng commit.
- Integration/contract tests kiểm tra ranh giới.
- Quality gate áp dụng chính sách bắt buộc.
- Reviewer đánh giá hợp đồng, ngữ nghĩa, thiết kế và rủi ro.
- Tác giả giải thích sai khác và bổ sung bằng chứng.

Vòng PR là nơi kết hợp tự động hóa với phán đoán con người. Gate xanh không thay thế review; review cũng không nên thay thế các kiểm tra lặp lại mà máy thực hiện đáng tin cậy.

### 2.3. Vòng triển khai: khi thay đổi đi vào môi trường thật

Các tín hiệu:

- Tỷ lệ lỗi và độ trễ theo endpoint hoặc luồng nghiệp vụ.
- Số lần retry, timeout và trạng thái chưa xác định.
- Tỷ lệ thành công của thao tác quan trọng.
- Mức sử dụng CPU, memory, connection pool và queue.
- Sai khác dữ liệu hoặc kết quả giữa đường cũ và đường mới.
- Phản hồi hỗ trợ khách hàng và báo cáo sự cố.

Vòng triển khai giúp kiểm tra giả định về dữ liệu, tải, cấu hình và hành vi dependency. Một unit test không thể tái hiện đầy đủ mọi điều kiện production.

### 2.4. Vòng dài: sau sự cố và theo chu kỳ

Các hoạt động:

- Phân tích sự cố và near miss.
- Xem lại các lỗi lặp lại và khoản nợ kỹ thuật.
- Rà soát xu hướng lead time, change failure và thời gian khôi phục.
- Đánh giá tính hữu ích của test, alert và quality gate.
- Cập nhật runbook, hướng dẫn review và tiêu chuẩn hoàn tất.
- Kiểm tra các hành động cải tiến đã tạo kết quả chưa.

Vòng dài thường phát hiện vấn đề hệ thống: một rule gây false positive, một loại test quá chậm, hoặc quy trình triển khai thiếu khả năng dừng rollout.

## 3. Tín hiệu từ mã nguồn: làm cho vấn đề lộ ra sớm

Mã nguồn chứa nhiều dấu hiệu cho biết một thiết kế đang trở nên khó hiểu hoặc dễ lỗi. Những dấu hiệu này không phải lúc nào cũng chứng minh có bug, nhưng có thể chỉ ra nơi cần điều tra.

### 3.1. Quan sát thay đổi và điểm tập trung lỗi

Những câu hỏi hữu ích:

- Một quy tắc nghiệp vụ có bị sao chép ở nhiều lớp không?
- Một module có thường xuyên phải sửa cùng lúc với module khác không?
- Một file lớn có tập trung nhiều thay đổi không liên quan?
- Một số phương thức có thường xuyên được sửa sau sự cố?
- Một nhóm lỗi có lặp lại quanh cùng một kiểu trạng thái hoặc dependency?

Ví dụ, nếu mỗi lần thay chính sách phí đều phải sửa controller, batch và báo cáo, đó là tín hiệu có nhiều nơi sở hữu cùng quy tắc. Nhóm có thể cân nhắc một policy dùng chung, nhưng trước hết phải xác nhận các luồng thực sự có cùng hợp đồng.

### 3.2. Code churn cần được diễn giải theo ngữ cảnh

**Code churn** thường mô tả lượng dòng được thêm, sửa hoặc xóa trong một khoảng thời gian. Vùng churn cao có thể là:

- Module nghiệp vụ thường xuyên thay đổi.
- Điểm tích hợp đang được phát triển.
- Nơi có nhiều bug hoặc yêu cầu chưa ổn định.
- Một vùng mã có thiết kế khó mở rộng.

Nhưng churn cao không tự chứng minh code kém. Một module được đầu tư phát triển tính năng mới cũng có churn cao. Churn thấp cũng không chứng minh an toàn; một module ít thay đổi có thể chứa rủi ro bảo mật hoặc logic hiếm khi chạy.

Hãy kết hợp churn với số lỗi, thời gian review, thời gian sửa, độ phức tạp và tác động người dùng.

### 3.3. Dấu hiệu thiết kế đáng điều tra

| Dấu hiệu | Câu hỏi cần đặt |
| --- | --- |
| Phương thức dài và nhiều nhánh | Có nhiều quy tắc hoặc trách nhiệm bị trộn? |
| Trạng thái mutable dùng chung | Có race, temporal coupling hoặc dữ liệu cũ? |
| Nhiều bản sao logic | Các bản sao có cùng chính sách hay đã phân nhánh nghiệp vụ? |
| Exception bị bắt rộng | Caller có phân biệt được lỗi và phục hồi đúng không? |
| Tham số boolean khó hiểu | Có thể dùng kiểu miền hoặc tên phương thức rõ hơn? |
| Dependency vòng | Trách nhiệm hoặc ranh giới module có đặt sai? |
| Nhiều TODO không có owner | Công việc còn dang dở có được quản lý không? |
| Một lớp bị sửa bởi nhiều nhóm | Ranh giới sở hữu có quá rộng? |

Không nên tự động refactor mọi dấu hiệu. Hãy xem tần suất thay đổi, mức rủi ro và lợi ích có thể kiểm chứng.

### 3.4. Từ tín hiệu mã nguồn thành hành động

Một quan sát hữu ích nên được chuyển thành công việc cụ thể:

~~~text
Quan sát:
  Công thức phí xuất hiện ở controller và batch.

Tác động:
  Một thay đổi chính sách có thể cập nhật thiếu một caller.

Giả thuyết:
  Hai caller phải dùng cùng một policy cho đơn mới.

Xác minh:
  Đối chiếu yêu cầu và chính sách của batch.

Hành động:
  Tách policy thuần, chuyển từng caller và thêm test biên.

Đo lại:
  Không còn công thức trùng trong phạm vi; kết quả caller khớp oracle.
~~~

Nếu chưa xác minh hai caller dùng cùng chính sách, hành động đúng có thể là làm rõ yêu cầu thay vì gom logic.

## 4. Tín hiệu từ kiểm thử và CI

Test không chỉ xác nhận code hiện tại; test còn tạo phản hồi về chất lượng hợp đồng, khả năng tái lập và độ an toàn của thay đổi.

### 4.1. Lỗi test cần được phân loại

Khi CI đỏ, cần phân biệt:

- **Lỗi hành vi:** kết quả không đúng oracle.
- **Lỗi test:** expected hoặc fixture sai.
- **Flaky test:** kết quả phụ thuộc timing, thứ tự hoặc trạng thái dùng chung.
- **Lỗi môi trường:** DB, network, dependency repository hoặc scanner không sẵn sàng.
- **Lỗi cấu hình:** module/source set bị bỏ qua hoặc dùng sai profile.

Không nên retry test liên tục cho tới khi xanh rồi coi vấn đề đã hết. Một test flaky có thể che race condition thật.

### 4.2. Theo dõi thời gian và độ ổn định của test suite

Những tín hiệu đáng theo dõi:

- Thời gian chạy theo từng lớp test.
- Tỷ lệ test flaky và số lần retry.
- Tỷ lệ test thất bại do lỗi môi trường.
- Test bị disable hoặc quarantine.
- Số test không có assertion hữu ích.
- Thời gian từ lúc tạo PR đến khi có kết quả đáng tin cậy.

Nếu test suite chậm dần, nhóm có thể phân tầng test, cô lập fixture, giảm phụ thuộc không cần thiết hoặc chạy song song có kiểm soát. Mục tiêu là giữ phản hồi nhanh mà không bỏ những kiểm tra quan trọng.

### 4.3. Coverage và mutation score là tín hiệu bổ trợ

Coverage giúp xác định code nào chưa được thực thi. Mutation testing có thể thay đổi nhỏ implementation để xem test có phát hiện sai khác không. Cả hai đều có giới hạn:

- Coverage cao không đảm bảo assertion đúng.
- Mutation score phụ thuộc loại mutation và khả năng áp dụng.
- Một test có thể phát hiện mutation nhưng vẫn bỏ sót lỗi nghiệp vụ khác.
- Thay đổi phạm vi scan có thể làm số liệu tăng/giảm mà chất lượng thực không đổi.

Khi số liệu thay đổi, hãy đọc cùng test cases, oracle và diff thay vì chỉ nhìn phần trăm.

### 4.4. Test mới phải bắt nguồn từ điều đã học

Khi một bug được phát hiện, hỏi:

1. Có thể tái hiện bug bằng test tự động ở tầng phù hợp không?
2. Test có thất bại trên code cũ và xanh sau khi sửa không?
3. Test có xác minh hành vi theo yêu cầu, thay vì sao chép lỗi cũ?
4. Có module/caller khác chịu cùng rủi ro không?
5. Có cần contract test, integration test hoặc quality gate để ngăn tái diễn?

Không nhất thiết mọi sự cố đều dẫn tới một unit test. Một vấn đề cấu hình, rollout hoặc concurrency có thể cần kiểm thử ở tầng tích hợp, kiểm soát triển khai hoặc cải thiện quan sát.

## 5. Tín hiệu từ code review

Code review là một vòng phản hồi hai chiều. Reviewer giúp phát hiện vấn đề và truyền đạt kiến thức về hợp đồng, kiến trúc, quy ước; tác giả cung cấp ngữ cảnh, giải thích quyết định và cập nhật thay đổi. Mục tiêu là cải thiện sản phẩm và cách nhóm làm việc.

### 5.1. Nhận xét cần tạo ra hiểu biết có thể dùng lại

Một nhận xét như “đoạn này khó đọc” có thể đúng nhưng chưa đủ hành động. Nhận xét cụ thể hơn:

> Công thức miễn phí vận chuyển đang xuất hiện ở cả controller và batch. Nếu hai luồng dùng cùng chính sách cho đơn mới, hãy đưa quy tắc về một policy có tên rõ và thêm test tại đúng ngưỡng. Trước khi gộp, cần xác nhận batch không áp dụng chính sách lịch sử khác.

Nhận xét này chỉ ra:

- Vị trí và vấn đề quan sát được.
- Tác động có thể xảy ra.
- Điều kiện cần xác minh.
- Hướng cải thiện và bằng chứng cần có.

### 5.2. Phân biệt lỗi cần sửa và gợi ý học hỏi

Không phải mọi nhận xét đều cần chặn merge. Có thể phân biệt:

| Loại phản hồi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Lỗi hợp đồng hoặc an toàn | Thiếu kiểm tra quyền trước khi trả dữ liệu | Sửa hoặc có quyết định rủi ro được phê duyệt trước merge |
| Rủi ro thiết kế đáng kể | Retry có thể thu tiền hai lần | Làm rõ hợp đồng và phương án phục hồi |
| Cải thiện cấu trúc | Tên biến không nêu đơn vị | Sửa trong phạm vi phù hợp hoặc tạo việc riêng |
| Gợi ý phong cách | Một cách viết khác cũng rõ | Trao đổi, không biến sở thích thành blocker |
| Câu hỏi cần ngữ cảnh | Service có được dùng chung giữa request không? | Tác giả giải thích bằng cấu hình/caller |

Nhận xét review nên nói rõ mức độ cần thiết và lý do. Điều đó giúp tác giả ưu tiên và giảm tranh luận về sở thích cá nhân.

### 5.3. Biến nhận xét lặp lại thành cải tiến hệ thống

Nếu reviewer thường xuyên phải nhắc:

- Không truyền trạng thái VIP từ client.
- Kiểm tra đúng ngưỡng.
- Không bắt và bỏ qua InterruptedException.
- Không gọi payment trước validation.
- Không lưu dữ liệu nhạy cảm trong log.

thì có thể cần hơn một lời nhắc trong từng PR. Nhóm có thể:

- Bổ sung ví dụ vào hướng dẫn phát triển.
- Tạo helper hoặc API khó sử dụng sai.
- Thêm test/quality gate phù hợp.
- Cải thiện template PR hoặc checklist.
- Đào tạo ngắn về một chủ đề cụ thể.

Đây là cách chuyển phản hồi cá nhân thành **năng lực chung của nhóm**. Không nên thêm rule tự động nếu công cụ không thể đánh giá đáng tin cậy hoặc rule tạo nhiều false positive.

### 5.4. Theo dõi trải nghiệm review

Các tín hiệu có thể giúp cải thiện quy trình:

- Thời gian chờ review đầu tiên.
- Thời gian từ PR sẵn sàng đến khi được tích hợp.
- Số vòng trao đổi do yêu cầu chưa rõ.
- Tỷ lệ PR quá lớn hoặc khó review.
- Nhận xét lặp lại về cùng một lỗi.
- Tỷ lệ thay đổi phải sửa lại sau review.

Không dùng số bình luận hoặc số PR được approve để xếp hạng cá nhân. Số liệu cần giúp tìm nút thắt trong quy trình, không tạo động cơ viết nhận xét cho đủ số lượng hoặc approve vội.

## 6. Tín hiệu từ vận hành

Vận hành cho biết phần mềm hoạt động ra sao dưới tải, dữ liệu, cấu hình và phụ thuộc thật. Đây là nơi các giả định trong thiết kế và test được kiểm tra bằng hành vi thực tế.

### 6.1. Metrics, logs và traces trả lời các câu hỏi khác nhau

| Loại tín hiệu | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Metrics** | Vấn đề xảy ra thường xuyên đến mức nào? Xu hướng thay đổi ra sao? | Tỷ lệ lỗi tạo đơn theo phút |
| **Logs** | Một sự kiện cụ thể đã xảy ra với ngữ cảnh nào? | Đơn chuyển sang PAYMENT_UNKNOWN |
| **Traces** | Một request đi qua các thành phần nào và tốn thời gian ở đâu? | API → pricing → DB → gateway |
| **Events/audit records** | Ai hoặc thành phần nào đã thực hiện thay đổi trạng thái? | Lệnh hủy đơn được chấp nhận |

Không có loại tín hiệu nào thay thế hoàn toàn loại khác. Metrics phù hợp để phát hiện xu hướng, log giúp điều tra sự kiện, trace giúp nhìn luồng qua nhiều service. Audit record có yêu cầu về tính toàn vẹn và quyền truy cập riêng.

### 6.2. Chọn tín hiệu gắn với hành vi quan trọng

Với một dịch vụ checkout, các chỉ số có thể gồm:

- Tỷ lệ tạo đơn thành công.
- Tỷ lệ request bị từ chối do input không hợp lệ.
- Tỷ lệ timeout của membership/payment dependency.
- Số đơn ở trạng thái chưa xác định quá thời hạn.
- Tỷ lệ retry và số lần retry trung bình.
- Độ trễ theo phân vị p50, p95 và p99.
- Số sai khác khi đối soát tổng tiền.

Metric cần có định nghĩa rõ. Ví dụ, “tỷ lệ thành công” phải nêu mẫu số là request, đơn hay giao dịch thanh toán; request bị từ chối do input hợp lệ có phải tính là lỗi dịch vụ không?

### 6.3. Tránh dữ liệu nhạy cảm và cardinality không kiểm soát

Không nên gắn email, token, số thẻ hoặc order ID duy nhất làm nhãn metric. Điều đó có thể làm lộ dữ liệu và tạo cardinality quá lớn.

Nên ưu tiên nhãn có miền giá trị hữu hạn, ví dụ:

- Endpoint hoặc operation đã chuẩn hóa.
- Loại lỗi theo enum.
- Phiên bản ứng dụng.
- Môi trường triển khai.
- Nhánh xử lý hoặc trạng thái nghiệp vụ có tập giá trị giới hạn.

Log và trace cũng cần lọc hoặc che thông tin nhạy cảm. Dữ liệu quan sát phải được thiết kế cùng yêu cầu bảo mật và quyền truy cập.

### 6.4. Alert cần gắn với hành động

Một alert tốt chỉ ra:

- Tác động tới người dùng hoặc SLO.
- Điều kiện kích hoạt và thời gian duy trì.
- Mức độ khẩn cấp.
- Người/nhóm nhận.
- Runbook hoặc bước điều tra đầu tiên.

Alert cho mỗi exception đơn lẻ có thể gây nhiễu. Một alert dựa trên tỷ lệ lỗi kéo dài hoặc mức tiêu thụ error budget có thể phù hợp hơn, tùy dịch vụ.

Không nên gửi cảnh báo mà không có người chịu trách nhiệm hoặc không có hành động khả thi. Cảnh báo bị bỏ qua lâu ngày làm giảm niềm tin vào toàn bộ hệ thống quan sát.

## 7. Dùng SLI, SLO và error budget để phản hồi theo mức dịch vụ

Để quyết định khi nào cần ưu tiên độ tin cậy, nhóm có thể định nghĩa:

- **SLI (Service Level Indicator):** chỉ số đo một khía cạnh dịch vụ mà người dùng quan tâm.
- **SLO (Service Level Objective):** mục tiêu cho SLI trong một khoảng thời gian.
- **Error budget:** phần lỗi hoặc không đạt mục tiêu mà SLO cho phép trong khoảng thời gian đó.

### 7.1. Ví dụ về SLI và SLO

Giả sử một API tra cứu hóa đơn đặt mục tiêu:

> Trong một cửa sổ 30 ngày, ít nhất 99,9% request hợp lệ hoàn tất thành công trong giới hạn thời gian đã xác định.

Để đo được, nhóm cần định nghĩa:

- Request nào được tính vào mẫu số?
- Request bị từ chối do người dùng không có quyền có được tính là lỗi dịch vụ không?
- Timeout từ dependency được phân loại thế nào?
- “Hoàn tất” có nghĩa là server trả response hay dữ liệu đã được commit?
- Giới hạn thời gian là bao nhiêu và đo ở đâu?

Nếu định nghĩa mơ hồ, SLO có thể xanh dù người dùng vẫn gặp vấn đề.

### 7.2. Error budget tạo phản hồi cho ưu tiên công việc

Khi dịch vụ dùng gần hết error budget, nhóm có thể:

- Tạm giảm tốc độ rollout tính năng rủi ro cao.
- Ưu tiên sửa nguyên nhân gây lỗi lặp.
- Tăng kiểm thử cho dependency hoặc luồng đang không ổn định.
- Cải thiện quan sát và runbook.
- Giảm độ phức tạp vận hành trước khi mở rộng tính năng.

Khi dịch vụ ổn định và còn ngân sách, nhóm có thể tiếp tục đầu tư tính năng trong giới hạn rủi ro được chấp nhận.

Error budget là công cụ hỗ trợ quyết định, không phải giấy phép để gây lỗi tới khi hết ngân sách. Nó cũng không thay thế yêu cầu bảo mật, pháp lý hoặc tính đúng đắn của dữ liệu.

### 7.3. SLO không nên trở thành con số trang trí

Một SLO chỉ hữu ích khi:

- Gắn với hành vi người dùng.
- Có cách đo và nguồn dữ liệu đáng tin.
- Có owner và chu kỳ xem lại.
- Có hành động khi xu hướng xấu.
- Được cân nhắc cùng chi phí vận hành và mục tiêu sản phẩm.

Không nên chọn 99,9% chỉ vì con số đó phổ biến. Mục tiêu phải phản ánh nhu cầu, khả năng kỹ thuật và hậu quả khi không đạt.

## 8. Học từ sự cố và near miss

Sự cố (*incident*) là một tình huống làm suy giảm hoặc gián đoạn dịch vụ, gây tác động tới người dùng hoặc vận hành. **Near miss** là tình huống suýt gây ra hậu quả nhưng được phát hiện hoặc ngăn chặn trước khi tác động lớn xảy ra.

Near miss có giá trị vì nó cho thấy một lớp kiểm soát đã hoạt động, nhưng cũng có thể chỉ ra rủi ro tiềm ẩn. Không nên chỉ học từ những lỗi đã gây thiệt hại.

### 8.1. Phân tích sự cố theo dòng thời gian

Một bản phân tích hữu ích thường ghi:

1. **Tác động:** ai bị ảnh hưởng, chức năng nào, trong bao lâu?
2. **Phát hiện:** tín hiệu nào cho biết có vấn đề, phát hiện mất bao lâu?
3. **Dòng thời gian:** những sự kiện và quyết định quan trọng theo thứ tự.
4. **Nguyên nhân trực tiếp:** điều gì khiến hành vi sai xảy ra?
5. **Điều kiện góp phần:** test, cấu hình, thiết kế, quy trình hoặc quan sát nào chưa đủ?
6. **Khôi phục:** nhóm đã làm gì để giảm tác động?
7. **Hành động tiếp theo:** thay đổi nào sẽ giảm khả năng hoặc tác động tái diễn?

Phân tích nên dựa trên log, metrics, trace, commit và trao đổi có căn cứ. Nếu chưa biết nguyên nhân, ghi rõ điều chưa xác định thay vì tạo một câu chuyện nghe hợp lý.

### 8.2. Phân biệt nguyên nhân trực tiếp và điều kiện hệ thống

Ví dụ:

- **Nguyên nhân trực tiếp:** worker xử lý lại message sau timeout và tạo bản ghi trùng.
- **Điều kiện góp phần:** consumer không có idempotency key.
- **Điều kiện phát hiện:** metric chỉ đếm message thành công, không đo duplicate.
- **Điều kiện quy trình:** review checklist chưa yêu cầu xác định hành vi retry.
- **Điều kiện vận hành:** runbook không có bước đối soát bản ghi trùng.

Nếu chỉ kết luận “developer quên kiểm tra trùng”, nhóm có thể thêm một comment hoặc nhắc nhở nhưng không cải thiện khả năng hệ thống chống lỗi.

### 8.3. Blameless không có nghĩa bỏ trách nhiệm

Phân tích không đổ lỗi (*blameless postmortem*) tập trung vào điều kiện và quyết định trong bối cảnh người thực hiện có lúc đó. Điều này khuyến khích mọi người báo cáo vấn đề sớm, kể cả near miss.

Blameless không có nghĩa:

- Không xác định ai sở hữu hành động khắc phục.
- Không xem xét quyết định kỹ thuật hoặc vi phạm quy trình.
- Không thông báo tác động và trách nhiệm với người dùng.
- Không có tiêu chuẩn về năng lực hoặc hành vi chuyên nghiệp.

Nhóm vẫn cần **owner, deadline, bằng chứng hoàn tất và hậu kiểm**. Khác biệt nằm ở việc dùng phân tích để cải thiện hệ thống thay vì chỉ tìm người để quy lỗi.

### 8.4. Chọn hành động phòng ngừa theo tầng

Một sự cố có thể tạo ra nhiều loại hành động:

| Tầng | Hành động ví dụ |
| --- | --- |
| Code | Thêm idempotency và xử lý trạng thái chưa xác định |
| Test | Test retry cùng key và payload khác |
| Review | Yêu cầu mô tả side effect và retry contract |
| CI/quality gate | Thêm kiểm tra phù hợp nếu có thể tự động hóa đáng tin |
| Deployment | Canary và giới hạn rollout |
| Operations | Alert duplicate, runbook đối soát |
| Learning | Chia sẻ mẫu lỗi và cập nhật hướng dẫn |

Không phải mọi hành động đều cần tạo. Ưu tiên thay đổi có thể giảm rủi ro đáng kể và có cách xác minh.

## 9. Ví dụ Java: đưa tín hiệu vận hành trở lại thiết kế

Giả sử một service tạo đơn gọi membership service để lấy trạng thái VIP, tính ưu đãi rồi lưu báo giá. Production cho thấy số lần timeout membership tăng, nhưng dashboard hiện tại chỉ đếm tổng số request lỗi. Nhóm không phân biệt được timeout với lỗi input hoặc lỗi lưu DB.

### 9.1. Xác định câu hỏi trước khi thêm metric

Nhóm cần trả lời:

- Timeout xảy ra ở bước lấy membership hay ở bước lưu đơn?
- Tỷ lệ timeout tăng theo phiên bản, endpoint hay môi trường?
- Khi membership timeout, service có vô tình mặc định khách là non-VIP không?
- Có đơn nào được tạo với trạng thái VIP không rõ nguồn không?
- Retry có tạo nhiều lần gọi hoặc đơn trùng không?

Từ các câu hỏi này, nhóm có thể xác định những tín hiệu tối thiểu: kết quả membership lookup, loại lỗi, thời gian xử lý, trạng thái cuối của workflow và số lần retry.

### 9.2. Tách trạng thái nghiệp vụ khỏi trạng thái lỗi phụ thuộc

Ví dụ Java:

~~~java
public enum MembershipStatus {
    VIP,
    NON_VIP
}

public interface MembershipClient {
    MembershipStatus lookup(CustomerId customerId);
}

public interface QuoteRepository {
    void save(QuoteSnapshot quote);
}

public interface CheckoutMetrics {
    void membershipLookupSucceeded(String result);
    void membershipLookupFailed(String failureType);
}

public record CustomerId(String value) {}

public record QuoteSnapshot(
        CustomerId customerId,
        long merchandiseSubtotalVnd,
        long discountVnd,
        String policyVersion) {}
~~~

Các interface và record trên là kiểu miền minh họa. **MembershipStatus** chỉ có hai kết quả hợp lệ; lỗi timeout phải được biểu diễn bằng exception hoặc kiểu kết quả lỗi riêng, không được giả làm NON_VIP.

### 9.3. Instrument service mà không làm đổi hợp đồng

~~~java
public final class QuoteApplicationService {
    private final MembershipClient membershipClient;
    private final QuoteRepository quoteRepository;
    private final CheckoutMetrics metrics;

    public QuoteApplicationService(
            MembershipClient membershipClient,
            QuoteRepository quoteRepository,
            CheckoutMetrics metrics) {
        this.membershipClient = membershipClient;
        this.quoteRepository = quoteRepository;
        this.metrics = metrics;
    }

    public QuoteSnapshot createQuote(
            CustomerId customerId,
            long subtotalVnd) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        final MembershipStatus status;
        try {
            status = membershipClient.lookup(customerId);
            metrics.membershipLookupSucceeded(status.name());
        } catch (MembershipTimeoutException timeout) {
            metrics.membershipLookupFailed("timeout");
            throw timeout;
        } catch (MembershipUnavailableException unavailable) {
            metrics.membershipLookupFailed("unavailable");
            throw unavailable;
        }

        boolean vip = status == MembershipStatus.VIP;
        long discountVnd =
                VipDiscountPolicy.discountVnd(subtotalVnd, vip);
        QuoteSnapshot quote = new QuoteSnapshot(
                customerId,
                subtotalVnd,
                discountVnd,
                "vip-discount-v1");
        quoteRepository.save(quote);
        return quote;
    }
}
~~~

**MembershipTimeoutException**, **MembershipUnavailableException** và các dependency là kiểu giả định của ví dụ. Đoạn code minh họa cách ghi nhận loại kết quả mà vẫn giữ nguyên lỗi phụ thuộc. Nó chưa giải quyết transaction, quyền truy cập, idempotency hoặc cách lưu trạng thái workflow đầy đủ.

### 9.4. Thiết kế metric không gắn định danh khách hàng

Một adapter triển khai **CheckoutMetrics** có thể ghi các metric có nhãn hữu hạn:

~~~text
membership_lookup_total{result="vip"}
membership_lookup_total{result="non_vip"}
membership_lookup_failures_total{reason="timeout"}
membership_lookup_failures_total{reason="unavailable"}
membership_lookup_duration_seconds
~~~

Không nên dùng **customerId**, email hoặc order ID làm label. Những giá trị duy nhất làm cardinality tăng mạnh và có thể lộ dữ liệu. Nếu cần điều tra một đơn cụ thể, dùng correlation ID trong log/traces với kiểm soát truy cập và chính sách lưu giữ phù hợp.

### 9.5. Đưa tín hiệu trở lại test và review

Sau khi thấy timeout tăng, nhóm có thể:

1. Bổ sung test để xác nhận membership timeout không bị chuyển thành NON_VIP.
2. Kiểm tra timeout budget và retry policy của client.
3. Review việc lưu quote chỉ diễn ra sau khi có membership result hợp lệ.
4. Thêm metric phân biệt timeout với unavailable.
5. Cập nhật alert khi tỷ lệ timeout vượt ngưỡng vận hành.
6. Đo lại sau phát hành để xác nhận tỷ lệ lỗi và số quote không hợp lệ giảm.

Nếu chỉ thêm metric mà không có test, service vẫn có thể xử lý sai. Nếu chỉ thêm test mà không có metric, nhóm có thể khó phát hiện khi dependency production suy giảm. Vòng phản hồi cần kết hợp cả hai.

## 10. Chuyển bài học thành backlog cải tiến có chủ sở hữu

Sau khi thu thập tín hiệu, nhóm cần chọn việc nào đáng làm, ai chịu trách nhiệm và làm sao biết đã hoàn tất.

### 10.1. Mẫu action item

Một action item hữu ích nên có:

| Thành phần | Câu hỏi |
| --- | --- |
| Vấn đề | Quan sát hoặc sự cố nào dẫn tới hành động? |
| Tác động | Người dùng, vận hành hoặc tốc độ phát triển bị ảnh hưởng ra sao? |
| Giả thuyết | Vì sao hành động này có thể cải thiện tình hình? |
| Thay đổi | Cụ thể sẽ sửa code, test, review, pipeline hay vận hành điều gì? |
| Owner | Ai chịu trách nhiệm đưa việc tới hoàn tất? |
| Thời hạn/ưu tiên | Khi nào cần làm và vì sao? |
| Bằng chứng hoàn tất | Test, metric, tài liệu hoặc hành vi nào chứng minh? |
| Đo lại | Khi nào kiểm tra tác động và theo chỉ số nào? |

Ví dụ:

~~~text
Vấn đề:
  Retry payment sau timeout có thể tạo giao dịch trùng.

Tác động:
  Có nguy cơ khách bị thu tiền hai lần.

Thay đổi:
  Lưu idempotency key theo order và payload hash;
  tra cứu trạng thái khi kết quả gateway chưa rõ.

Owner:
  Nhóm checkout.

Bằng chứng hoàn tất:
  Integration test cho timeout, retry cùng key,
  payload khác và hai request đồng thời.

Đo lại:
  Theo dõi duplicate payment và PAYMENT_UNKNOWN
  trong các lần phát hành tiếp theo.
~~~

### 10.2. Ưu tiên theo rủi ro và khả năng giảm thiểu

Có thể đánh giá các yếu tố:

- Mức độ tác động nếu lỗi tái diễn.
- Khả năng lỗi xuất hiện.
- Số người dùng hoặc luồng bị ảnh hưởng.
- Chi phí hiện tại của workaround.
- Độ chắc chắn rằng hành động sẽ giảm rủi ro.
- Chi phí triển khai và chi phí vận hành giải pháp mới.

Không cần tạo một công thức điểm số giả chính xác. Một cuộc thảo luận có cấu trúc và lý do ghi lại thường hữu ích hơn việc xếp hạng bằng con số không có cơ sở.

### 10.3. Phân biệt hành động phòng ngừa với hành động hoàn tất

Một action item như “thêm test” chưa chắc đủ. Test cần có oracle, chạy ở pipeline phù hợp và phát hiện được sai khác. Một action item như “thêm alert” cần xác định alert được kích hoạt khi nào, ai nhận và runbook hướng dẫn điều gì.

Hãy mô tả **kết quả mong đợi**, không chỉ tên hoạt động:

- Yếu: “Cải thiện logging.”
- Tốt hơn: “Khi payment chuyển sang PAYMENT_UNKNOWN, log có correlation ID, order state và loại timeout, không ghi dữ liệu thanh toán nhạy cảm; runbook chỉ ra cách tra cứu trạng thái.”

### 10.4. Không để backlog cải tiến trở thành kho TODO

Định kỳ:

- Đóng việc đã hoàn tất với bằng chứng.
- Chia việc quá lớn thành lát cắt.
- Hủy việc không còn phù hợp và ghi lý do.
- Nâng ưu tiên khi tín hiệu mới cho thấy rủi ro tăng.
- Gộp các việc trùng lặp có cùng nguyên nhân.
- Xem lại action item quá hạn hoặc không có owner.

Backlog là công cụ ra quyết định. Một danh sách dài không được xem lại chỉ làm tăng chi phí hiểu biết.

## 11. Đo xem vòng phản hồi có cải thiện kết quả không

Không nên đánh giá một chương trình cải thiện chỉ bằng số cuộc họp, số test mới hoặc số cảnh báo được đóng. Cần xem cả **kết quả kỹ thuật, tác động người dùng và khả năng giao hàng**.

### 11.1. Nhóm chỉ số có thể sử dụng

| Nhóm | Ví dụ tín hiệu | Câu hỏi |
| --- | --- | --- |
| Chất lượng thay đổi | Defect sau phát hành, hotfix, rollback | Lỗi có lọt qua các bước trước không? |
| Tốc độ phản hồi | Thời gian CI, thời gian chờ review | Nhóm nhận tín hiệu sớm hay bị chờ lâu? |
| Độ ổn định test | Flaky rate, retry count | Kết quả CI có đáng tin không? |
| Vận hành | Availability, latency, error rate | Người dùng có nhận dịch vụ đúng kỳ vọng? |
| Phục hồi | Time to restore service | Khi có lỗi, nhóm khôi phục nhanh đến đâu? |
| Duy trì mã | Churn kết hợp defect, thời gian sửa | Khu vực nào đang tạo chi phí thay đổi? |
| Học từ sự cố | Action completion và recurrence | Hành động phòng ngừa có hiệu quả không? |

### 11.2. DORA metrics và cách dùng thận trọng

Một số nhóm dùng các chỉ số phân phối phần mềm thường được gọi là DORA metrics, như:

- **Deployment frequency:** tần suất triển khai.
- **Lead time for changes:** thời gian từ khi thay đổi được commit hoặc bắt đầu đến khi chạy trong production, tùy định nghĩa đo.
- **Change failure rate:** tỷ lệ triển khai gây cần remediation như rollback, hotfix hoặc sự cố theo định nghĩa của nhóm.
- **Failed deployment recovery time:** thời gian khôi phục sau triển khai thất bại.

Các chỉ số này giúp thảo luận về năng lực phân phối phần mềm ở cấp hệ thống. Cần dùng định nghĩa nhất quán, phân tích cùng bối cảnh và tránh so sánh nhóm có sản phẩm, quy mô hoặc quy trình rất khác nhau bằng một bảng xếp hạng đơn giản.

Không dùng chúng để đánh giá năng suất cá nhân. Nếu deployment frequency trở thành mục tiêu duy nhất, nhóm có thể chia nhỏ phát hành mà không cải thiện giá trị; nếu lead time là mục tiêu duy nhất, nhóm có thể bỏ qua kiểm tra cần thiết.

### 11.3. Đo cả chỉ số dẫn dắt và chỉ số kết quả

- **Chỉ số dẫn dắt:** thời gian CI, tỷ lệ flaky, số caller còn dùng API cũ, tỷ lệ test có oracle cho nhánh rủi ro.
- **Chỉ số kết quả:** lỗi production, duplicate payment, downtime, thời gian phục hồi, phản hồi người dùng.

Chỉ số dẫn dắt giúp nhóm nhận ra vấn đề trước khi hậu quả xuất hiện. Chỉ số kết quả cho biết cải tiến có tạo tác động thật hay không.

### 11.4. Đọc xu hướng, không kết luận từ một điểm dữ liệu

Trước/sau có thể bị ảnh hưởng bởi:

- Thay đổi lưu lượng hoặc mùa vụ.
- Một đợt phát hành lớn.
- Sự cố từ dependency ngoài.
- Thay đổi cách đếm metric.
- Cấu hình hoặc phạm vi thu thập khác nhau.

Hãy ghi nhận giai đoạn so sánh, mẫu số, phiên bản và các yếu tố gây nhiễu. Nếu dữ liệu chưa đủ, kết luận đúng là **chưa đủ bằng chứng**, không phải tự chọn câu chuyện phù hợp với giả thuyết.

### 11.5. Tránh tối ưu metric gây hại

Ví dụ những hành vi không mong muốn:

- Giảm số bug được ghi nhận bằng cách không tạo ticket.
- Tăng coverage bằng assertion yếu.
- Tăng deployment frequency bằng các lần phát hành không có giá trị.
- Giảm thời gian phục hồi trên báo cáo bằng cách đổi định nghĩa thời điểm bắt đầu.
- Giảm cảnh báo bằng cách tắt rule thay vì sửa vấn đề.

Metric cần được kiểm tra cùng bằng chứng định tính và kết quả người dùng. **Đo lường để học, không để trang trí hoặc trừng phạt.**
## 12. Tạo nhịp cải tiến đều đặn

Vòng phản hồi không tự duy trì nếu nhóm chỉ xem lại khi có sự cố lớn. Cần một nhịp phù hợp để tín hiệu được đọc, hành động được chọn và kết quả được kiểm tra.

### 12.1. Nhịp hằng ngày: phản hồi gần công việc

Trong quá trình phát triển, hãy đọc kết quả build/test trước khi yêu cầu review, xử lý cảnh báo mới có liên quan tới phần thay đổi, ghi nhận lỗi lặp hoặc điểm khó hiểu khi đang sửa mã, chia sẻ sớm khi hợp đồng chưa rõ và kiểm tra alert theo quy trình trực vận hành. Mục tiêu là giải quyết vấn đề khi ngữ cảnh còn mới, không chờ tới buổi họp định kỳ.
### 12.2. Nhịp theo PR hoặc mỗi lần phát hành

Sau một thay đổi đáng kể, nhóm có thể hỏi:

- Hành vi nào được thay đổi và bằng chứng nào xác nhận?
- Có lỗi hoặc cảnh báo mới nào xuất hiện?
- Có adapter, feature flag hoặc workaround cần dọn sau rollout?
- Có điểm nào khiến review mất nhiều vòng?
- Có tín hiệu production cần theo dõi riêng?

Không cần tạo một cuộc họp cho mọi PR nhỏ. Có thể ghi những câu trả lời quan trọng trong PR hoặc release note.

### 12.3. Nhịp hằng tuần hoặc hai tuần

Một buổi xem lại ngắn có thể:

1. Xem xu hướng CI, flaky tests và thời gian review.
2. Xem defect hoặc incident mới và near miss.
3. Kiểm tra action item đang mở.
4. Chọn một hoặc hai cải tiến có tác động rõ.
5. Xác định owner và cách đo lại.

Không nên biến buổi này thành việc đọc toàn bộ dashboard. Hãy bắt đầu bằng một câu hỏi cụ thể hoặc một xu hướng cần giải thích.

### 12.4. Nhịp theo tháng hoặc quý

Ở nhịp dài hơn, có thể xem:

- SLO và error budget.
- Xu hướng lỗi tái diễn.
- Các module có churn và chi phí sửa cao.
- Nợ kỹ thuật đang cản trở roadmap.
- Chất lượng và độ ổn định của pipeline.
- Các ngoại lệ, suppression hoặc bypass đã tồn tại lâu.
- Hiệu quả của hành động sau incident.

Đây là lúc xem liệu các cải tiến cục bộ có tạo ra thay đổi ở cấp hệ thống hay không.

### 12.5. Giữ nhịp nhẹ và gắn với quyết định

Không nên tạo thêm cuộc họp chỉ để “có cải thiện liên tục”. Một nhịp tốt:

- Có dữ liệu hoặc ví dụ cụ thể trước buổi trao đổi.
- Giới hạn số vấn đề cần xử lý.
- Kết thúc bằng quyết định, owner và cách xác minh.
- Có thể thực hiện bất đồng bộ khi phù hợp.
- Được xem lại xem chi phí duy trì có xứng đáng không.

## 13. Những anti-pattern làm vòng phản hồi mất tác dụng

### 13.1. Thu thập metric nhưng không có owner

Dashboard cho thấy tỷ lệ timeout tăng nhưng không có người nhận hoặc quy trình xử lý. Dữ liệu tồn tại nhưng không tạo hành động.

**Cải thiện:** gắn metric với câu hỏi, alert/runbook, owner và lịch xem lại.

### 13.2. Tạo alert cho mọi lỗi

Nếu mỗi exception tạo một cảnh báo, người trực sẽ nhận quá nhiều tín hiệu không cần hành động. Cảnh báo quan trọng dễ bị bỏ qua.

**Cải thiện:** alert theo tác động, xu hướng và ngưỡng có ý nghĩa; phân biệt lỗi dự kiến với lỗi cần can thiệp.

### 13.3. Sửa triệu chứng mà không tìm điều kiện góp phần

Sau một lỗi null, nhóm thêm một null check nhưng không xác định vì sao dữ liệu thiếu hoặc vì sao hợp đồng cho phép trạng thái đó.

**Cải thiện:** xác định nguồn dữ liệu, bất biến và tầng cần bảo vệ; thêm test cho nguyên nhân và đường lỗi phù hợp.

### 13.4. Postmortem tạo ra danh sách hành động không có người sở hữu

Biên bản có nhiều đề xuất nhưng không có owner, hạn hoặc tiêu chí hoàn tất. Vài tuần sau không ai nhớ.

**Cải thiện:** giới hạn số hành động, gắn owner, ưu tiên và bằng chứng hoàn tất; hủy hoặc điều chỉnh việc không còn phù hợp.

### 13.5. Đo cá nhân bằng số liệu nhóm

Dùng số PR, số commit, số bình luận hoặc số bug để xếp hạng developer có thể tạo động cơ tối ưu sai và làm giảm chia sẻ sự cố.

**Cải thiện:** dùng metric để tìm nút thắt ở cấp quy trình và sản phẩm; phản hồi cá nhân dựa trên ngữ cảnh, chất lượng công việc và trao đổi trực tiếp.

### 13.6. Cải thiện quá nhiều thứ cùng lúc

Nếu cùng một thời điểm nhóm đổi test framework, CI, kiến trúc module, cách deploy và metric, rất khó biết thay đổi nào tạo kết quả hoặc gây tác dụng phụ.

**Cải thiện:** chọn một vài giả thuyết, triển khai theo lát cắt và đo lại trước khi mở rộng.

### 13.7. Chỉ học từ lỗi lớn

Near miss, cảnh báo bị bỏ qua và workaround thường xuyên có thể báo trước một sự cố nghiêm trọng.

**Cải thiện:** khuyến khích ghi nhận tình huống suýt xảy ra lỗi và xem lại tín hiệu yếu trước khi có tác động lớn.

### 13.8. Đóng action item khi code đã merge

Một thay đổi đã merge nhưng chưa rollout, chưa có alert hoặc chưa đo được tác động có thể chưa giải quyết vấn đề.

**Cải thiện:** định nghĩa hoàn tất theo kết quả cần đạt; có thể gồm code, test, rollout, quan sát và hậu kiểm.

### 13.9. Để workaround tồn tại vô thời hạn

Feature flag, adapter, retry tạm hoặc suppression được tạo khi sự cố nhưng không có điều kiện loại bỏ.

**Cải thiện:** ghi owner, ngày xem lại, điều kiện dọn và bằng chứng cần có; rà soát chúng theo chu kỳ.
## 14. Tình huống thực hành: lỗi thanh toán sau timeout

Một dịch vụ checkout ghi nhận phản ánh từ khách hàng rằng một số đơn bị trừ tiền nhưng trạng thái vẫn là PENDING. Nhóm điều tra thấy luồng xử lý:

~~~text
Checkout API
    |
    v
Save order as PENDING
    |
    v
Call payment gateway
    |
    +---- Response success ----> Mark order PAID
    |
    +---- Timeout -------------> Return error
~~~

Trong một số lần timeout, gateway đã xử lý thanh toán nhưng phản hồi không tới ứng dụng. Caller retry, và hệ thống có thể gửi lệnh capture lần nữa. Log hiện tại chỉ ghi “payment failed” khi có timeout, không phân biệt kết quả chưa xác định.

### 14.1. Xác định tín hiệu hiện có và khoảng trống

| Nguồn | Đã có | Còn thiếu |
| --- | --- | --- |
| Code | Có catch timeout và trả lỗi | Không có trạng thái PAYMENT_UNKNOWN |
| Test | Test gateway trả success hoặc decline | Chưa test timeout sau khi gateway đã xử lý |
| Review | Review kiểm tra response và exception | Chưa yêu cầu mô tả idempotency/retry |
| Metrics | Đếm payment failure tổng | Không tách timeout, decline và duplicate |
| Logs | Có order ID và thông báo lỗi | Thiếu correlation ID và trạng thái tra cứu |
| Operations | Có quy trình retry request | Chưa có bước đối soát gateway |

### 14.2. Đặt giả thuyết và hành động

Giả thuyết: timeout đang bị hiểu nhầm là thanh toán thất bại chắc chắn, trong khi kết quả thực tế có thể chưa xác định.

Các hành động:

1. Xác nhận hợp đồng gateway về timeout, idempotency key và API tra cứu.
2. Thêm trạng thái PAYMENT_UNKNOWN vào workflow nếu phù hợp.
3. Bảo đảm retry dùng cùng khóa idempotency theo hợp đồng.
4. Thêm integration test cho gateway xử lý thành công nhưng response bị mất.
5. Thêm metrics riêng cho timeout, decline, duplicate và trạng thái unknown.
6. Cập nhật runbook để tra cứu/đối soát trước khi retry thủ công.
7. Bổ sung checklist review cho side effect và retry.

### 14.3. Xác minh sau khi thay đổi

Trước khi phát hành:

- Test cho success, decline, timeout trước xử lý, timeout sau xử lý.
- Test retry cùng key và payload khác.
- Test hai request đồng thời dùng cùng key.
- Test DB lỗi sau khi gateway xác nhận thành công.
- Kiểm tra trạng thái và log không chứa dữ liệu thanh toán nhạy cảm.

Sau khi phát hành:

- Theo dõi số PAYMENT_UNKNOWN và thời gian tồn tại.
- Theo dõi duplicate payment đã xác nhận.
- Đo tỷ lệ timeout theo gateway và phiên bản.
- Kiểm tra số giao dịch cần đối soát thủ công.
- Xem lại sau một khoảng thời gian đủ đại diện.

### 14.4. Khi nào vòng phản hồi được xem là khép kín?

Không phải ngay khi code merge. Vòng phản hồi chỉ có bằng chứng hoàn tất khi:

- Hành vi timeout đã được mô tả và kiểm thử.
- Workflow và idempotency đã được triển khai.
- Metrics/alert giúp phát hiện trạng thái bất thường.
- Runbook cho biết cách tra cứu và phục hồi.
- Dữ liệu sau phát hành cho thấy duplicate giảm hoặc không tái diễn trong phạm vi quan sát.
- Action item còn lại được ghi nhận nếu chưa đủ thời gian hoặc dữ liệu để kết luận.

Nếu không có duplicate trong một ngày với lưu lượng rất thấp, chưa thể khẳng định vấn đề đã biến mất. Hãy nêu rõ thời gian, traffic và giới hạn của bằng chứng.

## 15. Checklist duy trì vòng phản hồi

### 15.1. Từ mã nguồn tới kiểm thử

- [ ] Quy tắc nghiệp vụ có một nguồn sở hữu rõ?
- [ ] Dữ liệu và trạng thái được truyền tường minh?
- [ ] Thay đổi mới có test cho hợp đồng và giá trị biên?
- [ ] Lỗi trước đây có test tái hiện hoặc kiểm soát phòng ngừa phù hợp?
- [ ] Test chạy nhanh, ổn định và có oracle độc lập?

### 15.2. Từ kiểm thử tới review

- [ ] CI chạy trên đúng commit và đúng module?
- [ ] Kết quả FAIL, SKIPPED hoặc flaky được xử lý có lý do?
- [ ] Reviewer hiểu mục tiêu và hành vi trước/sau?
- [ ] Nhận xét review có thể hành động và gắn với rủi ro?
- [ ] Các lỗi lặp lại được chuyển thành hướng dẫn hoặc kiểm soát chung?

### 15.3. Từ review tới vận hành

- [ ] Thay đổi có kế hoạch rollout phù hợp rủi ro?
- [ ] Metrics/logs/traces trả lời được câu hỏi vận hành?
- [ ] Alert có owner và runbook?
- [ ] Có thể dừng rollout và phục hồi khi kết quả xấu?
- [ ] Dữ liệu nhạy cảm được bảo vệ trong telemetry?

### 15.4. Từ vận hành trở lại cải tiến

- [ ] Incident và near miss được ghi nhận?
- [ ] Phân tích xem cả nguyên nhân trực tiếp lẫn điều kiện góp phần?
- [ ] Action item có owner, ưu tiên và tiêu chí hoàn tất?
- [ ] Hành động đã được kiểm tra tác động sau triển khai?
- [ ] Metric được diễn giải cùng ngữ cảnh và không dùng để trừng phạt cá nhân?
- [ ] Workaround, flag và ngoại lệ có điều kiện xem lại/dọn bỏ?
## 16. Những hiểu nhầm thường gặp

**“Cải thiện liên tục là họp retrospective thường xuyên.”** Cuộc họp chỉ là một cách trao đổi. Cải thiện cần tín hiệu, quyết định, hành động và xác minh kết quả.

**“Càng nhiều metric càng tốt.”** Metric không có câu hỏi, owner hoặc hành động chỉ làm tăng nhiễu.

**“CI xanh chứng minh phần mềm đúng.”** CI chỉ xác nhận các kiểm tra đã cấu hình và chạy đều đạt; hợp đồng, ngữ nghĩa và bối cảnh vẫn cần review.

**“Mọi incident đều phải tạo thêm test.”** Một số nguyên nhân cần sửa cấu hình, alert, runbook, quyền truy cập hoặc quy trình triển khai. Chọn biện pháp theo nguyên nhân.

**“Blameless nghĩa là không ai chịu trách nhiệm.”** Nhóm vẫn cần owner và deadline; phân tích tập trung vào điều kiện hệ thống để giảm tái diễn.

**“SLO là lời hứa tuyệt đối.”** SLO là mục tiêu đo trong một cửa sổ và theo định nghĩa cụ thể. Nó hỗ trợ quyết định, không bảo đảm không bao giờ có lỗi.

**“DORA metrics dùng để đánh giá từng developer.”** Các chỉ số phân phối phản ánh năng lực hệ thống và quy trình ở cấp nhóm/tổ chức, không phải thước đo năng suất cá nhân.

**“Đóng ticket là đã giải quyết.”** Cần xem thay đổi đã triển khai chưa, tín hiệu có cải thiện không và rủi ro còn lại là gì.

**“Sự cố đã hết nên không cần xem lại.”** Một khoảng thời gian yên ổn ngắn hoặc lưu lượng thấp chưa đủ chứng minh nguyên nhân đã được loại bỏ.

## 17. Ghi nhớ

- Vòng phản hồi liên tục kết nối **mã nguồn, kiểm thử, review, triển khai và vận hành** thành một chu trình học hỏi có hành động.
- Tín hiệu chỉ hữu ích khi có câu hỏi, ngữ cảnh, người nhận, quyết định và cách xác minh tác động.
- Compiler, test và CI cung cấp phản hồi sớm; code review đánh giá ngữ nghĩa và bối cảnh; metrics, logs, traces và incident cho biết hệ thống hoạt động ngoài thực tế.
- SLI/SLO và error budget giúp liên kết độ tin cậy với ưu tiên công việc, nhưng cần định nghĩa và diễn giải nhất quán.
- Phân tích incident và near miss nên tìm cả nguyên nhân trực tiếp lẫn điều kiện góp phần, đồng thời gắn hành động với owner và bằng chứng hoàn tất.
- Đo lường để học và cải thiện hệ thống, không dùng metric đơn lẻ để xếp hạng hoặc trừng phạt cá nhân.
- Vòng phản hồi khép kín khi **hành động được triển khai, kết quả được quan sát và bài học quay trở lại cách viết mã, kiểm thử, review hoặc vận hành**.

Một nhóm không cần thay đổi mọi thứ sau mỗi lỗi. Nhóm cần biết tín hiệu nào đáng tin, vấn đề nào quan trọng, hành động nào có khả năng giảm rủi ro và bằng chứng nào sẽ cho biết hành động đó có hiệu quả. Khi chu trình này diễn ra đều đặn, chất lượng phần mềm tiến bộ qua từng thay đổi và kinh nghiệm vận hành trở thành kiến thức dùng chung.
