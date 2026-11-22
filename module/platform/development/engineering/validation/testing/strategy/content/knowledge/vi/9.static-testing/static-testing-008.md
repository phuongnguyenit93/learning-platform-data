# Kiểm thử tĩnh: Đánh giá giới hạn của phân tích tĩnh so với kiểm chứng khi chạy

## 1. Vì sao cần hiểu giới hạn của phân tích tĩnh?

Phân tích tĩnh (static analysis) giúp tìm vấn đề trong mã nguồn, bytecode, cấu hình hoặc mô hình dữ liệu mà không cần thực thi luồng chương trình đang được kiểm tra. Nó có thể phát hiện sớm lỗi kiểu, đường dữ liệu nguy hiểm, nhánh xử lý đáng ngờ, dependency có lỗ hổng đã biết và nhiều vi phạm quy tắc kỹ thuật. Tuy nhiên, một báo cáo phân tích tĩnh không tự động chứng minh phần mềm sẽ hoạt động đúng trong môi trường thực tế.

Một chương trình có thể không có cảnh báo từ static analyzer nhưng vẫn thất bại khi chạy vì dữ liệu thật, cấu hình, quyền, tải, thời điểm, trạng thái bên ngoài hoặc cách nhiều thành phần phối hợp. Ngược lại, một công cụ có thể cảnh báo một đường mã nguy hiểm dù điều kiện kích hoạt không thể xảy ra trong sản phẩm. Muốn đưa ra quyết định chất lượng đáng tin cậy, nhóm cần hiểu cả năng lực lẫn giới hạn của từng loại bằng chứng.

Trong **VALIDATION_TESTING_STRATEGY**, nội dung này giúp nhóm:

- Đánh giá static analysis chứng minh được điều gì và không chứng minh được điều gì.
- Phân biệt cảnh báo có thể khai thác với cảnh báo giả hoặc không liên quan đến ngữ cảnh.
- Nhận diện các lỗi chỉ xuất hiện khi chương trình thực thi với dữ liệu, trạng thái và môi trường cụ thể.
- Chọn kiểm thử động, kiểm chứng khi chạy hoặc giám sát runtime để xử lý khoảng trống phù hợp.
- Kết hợp kết quả tĩnh và động vào ma trận truy vết, mô hình rủi ro và quality gate.

Nguyên tắc quan trọng là mỗi phương pháp chỉ cung cấp bằng chứng trong phạm vi mô hình và điều kiện mà nó quan sát được. Kết luận chất lượng cần phản ánh giới hạn đó.

## 2. Phân biệt phân tích tĩnh, kiểm thử động và kiểm chứng khi chạy

Các thuật ngữ này có liên quan nhưng không hoàn toàn đồng nghĩa.

### 2.1. Phân tích tĩnh (static analysis)

Phân tích tĩnh kiểm tra một biểu diễn của chương trình mà không chạy chương trình theo kịch bản sử dụng. Đầu vào có thể là mã nguồn, bytecode, binary, dependency graph, schema hoặc cấu hình.

Các kỹ thuật thường gặp:

- Phân tích cú pháp và cấu trúc chương trình (AST).
- Phân tích kiểu dữ liệu, luồng điều khiển và luồng dữ liệu.
- Phân tích taint để theo dõi dữ liệu không tin cậy đi đến điểm nhạy cảm.
- Phân tích dependency và phiên bản thư viện.
- Kiểm tra quy tắc bảo mật, coding standard và cấu hình.
- Symbolic execution hoặc model checking trong phạm vi mô hình và tài nguyên cho phép.

Static analysis có thể phát hiện vấn đề mà không cần tạo dữ liệu chạy hoặc dựng toàn bộ hệ thống. Độ tin cậy của kết quả phụ thuộc vào loại phân tích, giả định, mức bao phủ, mô hình môi trường và cách công cụ diễn giải chương trình.

### 2.2. Kiểm thử động (dynamic testing)

Kiểm thử động thực thi chương trình với đầu vào, trạng thái ban đầu và môi trường xác định. Người kiểm thử quan sát kết quả rồi so sánh với test oracle.

Ví dụ:

- Gửi payload vào API để xác nhận validation và xử lý lỗi.
- Chạy nhiều yêu cầu đồng thời để kiểm tra tranh chấp dữ liệu.
- Thực hiện giao dịch qua các dịch vụ để xác nhận trạng thái cuối.
- Tiêm lỗi mạng hoặc dừng một worker để kiểm tra retry và phục hồi.
- Đo độ trễ và thông lượng dưới mô hình tải đã định nghĩa.

Kiểm thử động chứng minh hành vi đã quan sát trong những lần chạy cụ thể. Nó không chứng minh mọi đầu vào, trạng thái hoặc lịch thực thi đều đúng.

### 2.3. Kiểm chứng khi chạy (runtime verification)

Kiểm chứng khi chạy là việc quan sát một lần thực thi hoặc một luồng sự kiện runtime rồi đối chiếu với các thuộc tính đã định nghĩa. Bộ giám sát (monitor) có thể kiểm tra bất biến, thứ tự sự kiện, giới hạn thời gian, quy tắc chuyển trạng thái hoặc điều kiện an toàn.

Runtime verification có thể được dùng trong môi trường kiểm thử, staging hoặc production. Ví dụ, monitor theo dõi mọi giao dịch và cảnh báo nếu cùng một mã thanh toán tạo ra hai lần ghi nhận, hoặc nếu một đơn hàng ở trạng thái chờ quá thời hạn đã quy định.

Kiểm thử động và runtime verification có phần giao nhau nhưng mục tiêu có thể khác nhau: kiểm thử động thường chủ động tạo đầu vào và điều kiện để xác nhận kịch bản; runtime verification có thể theo dõi các sự kiện phát sinh tự nhiên trong một phiên chạy hoặc luồng hoạt động dài hạn.

### 2.4. Bảng so sánh

| Khía cạnh | Phân tích tĩnh | Kiểm thử động | Kiểm chứng khi chạy |
| --- | --- | --- | --- |
| Đối tượng | Mã, binary, cấu hình, dependency hoặc mô hình | Chương trình đang chạy với đầu vào được chọn | Sự kiện, trạng thái và trace của một lần chạy |
| Cần thực thi chương trình | Không | Có | Có |
| Điều kiện được quan sát | Đường mã và mô hình mà công cụ phân tích được | Các kịch bản và môi trường đã chạy | Các sự kiện và khoảng thời gian monitor quan sát được |
| Phát hiện phù hợp | Lỗi kiểu, mẫu code nguy hiểm, luồng dữ liệu đáng ngờ, dependency lỗi thời | Sai lệch đầu ra, lỗi tích hợp, lỗi dữ liệu, hành vi theo điều kiện cụ thể | Vi phạm bất biến, thứ tự sự kiện, giới hạn thời gian hoặc trạng thái trong phiên chạy |
| Giới hạn chính | Mô hình xấp xỉ, giả định và cảnh báo không đúng ngữ cảnh | Không thể chạy hết mọi tổ hợp đầu vào và trạng thái | Chỉ thấy sự kiện được thu thập; monitor có thể thiếu dữ liệu hoặc bỏ lỡ đường chạy |
| Bằng chứng | Vị trí mã, rule, dataflow path, báo cáo scan | Test result, request/response, log, trace, trạng thái cuối | Event trace, monitor result, violation record, metric |

Không nên coi ba phương pháp là các cấp độ thay thế nhau. Chúng quan sát những khía cạnh khác nhau của cùng một rủi ro.

## 3. Giới hạn của phân tích tĩnh

### 3.1. Phân tích dựa trên mô hình và giả định

Static analyzer không quan sát trực tiếp mọi điều kiện runtime. Công cụ xây dựng một mô hình của chương trình từ mã nguồn hoặc binary, sau đó áp dụng các quy tắc và phép phân tích. Mô hình có thể bỏ qua hoặc đơn giản hóa một số yếu tố:

- Giá trị cấu hình chỉ có khi triển khai.
- Dữ liệu được tải từ database hoặc hệ thống bên ngoài.
- Hành vi thư viện, framework hoặc native code mà analyzer không có mô hình đầy đủ.
- Reflection, dynamic dispatch, plugin hoặc mã được nạp lúc chạy.
- Hành vi của container, operating system, network và cloud service.
- Trạng thái do người dùng, thời gian hoặc sự kiện bên ngoài quyết định.

Nếu giả định của công cụ không khớp môi trường thật, kết quả có thể thiếu cảnh báo hoặc tạo cảnh báo không liên quan. Vì vậy, cần xem tài liệu rule, loại phân tích và phạm vi hỗ trợ của công cụ trước khi diễn giải báo cáo.

### 3.2. Không chứng minh được mọi hành vi thực tế chỉ từ một lần phân tích thông thường

Một static analyzer tổng quát thường phải cân bằng giữa tốc độ, khả năng mở rộng và độ chính xác. Nó có thể đánh giá một đường đi là có khả năng xảy ra dù điều kiện thực tế không thể đồng thời đúng; hoặc bỏ qua đường đi mà công cụ không mô hình hóa được.

Một số phương pháp hình thức có thể chứng minh thuộc tính trong mô hình và giả định được xác định rõ. Tuy nhiên, kết luận đó vẫn phụ thuộc vào tính đầy đủ của mô hình, đặc tả, môi trường và các thành phần nằm ngoài phạm vi chứng minh. Không nên đánh đồng một báo cáo lint hoặc SAST với một chứng minh hình thức toàn diện.

### 3.3. Bùng nổ số đường đi và trạng thái

Khi số nhánh điều kiện, vòng lặp, lời gọi hàm và trạng thái tăng, số đường đi có thể tăng rất nhanh. Một chương trình nhỏ cũng có thể có số tổ hợp lớn nếu phụ thuộc nhiều cờ cấu hình hoặc dữ liệu đầu vào.

Các công cụ thường giới hạn độ sâu, thời gian, số trạng thái hoặc dùng heuristic để hoàn tất phân tích. Khi đó:

- Một số đường đi không được khám phá.
- Một số vòng lặp chỉ được xấp xỉ.
- Tương tác giữa nhiều thread hoặc process có thể không được mô hình hóa đầy đủ.
- Báo cáo có thể ghi nhận phân tích chưa hoàn tất hoặc bỏ qua một số module.

Nhóm cần kiểm tra trạng thái hoàn tất và phạm vi scan. Một báo cáo không có finding chưa chắc là báo cáo đã phân tích hết phần mã quan trọng.

### 3.4. Khó mô hình hóa dữ liệu và cấu hình runtime

Một số lỗi chỉ xuất hiện với dữ liệu thật hoặc cấu hình triển khai cụ thể. Ví dụ:

- Giá trị null hoặc dữ liệu lịch sử không đúng giả định của schema.
- Feature flag bật ở production nhưng tắt trong cấu hình scan.
- Quyền của service account khác với quyền trong môi trường phát triển.
- Giá trị bí mật hoặc endpoint được inject khi triển khai.
- Thứ tự dữ liệu, collation, timezone hoặc locale làm thay đổi kết quả.

Static analysis có thể phát hiện một số rủi ro trong cách đọc cấu hình hoặc sử dụng API, nhưng không tự chứng minh cấu hình cuối cùng và dữ liệu thực tế tạo ra hành vi mong muốn.

### 3.5. Khó kết luận về hiệu năng và tính thời gian thực

Phân tích tĩnh có thể tìm thuật toán có độ phức tạp cao, truy vấn có dấu hiệu tốn kém hoặc thao tác đồng bộ đáng ngờ. Tuy nhiên, nó thường không đủ để kết luận thời gian phản hồi, thông lượng hoặc mức sử dụng tài nguyên trong môi trường thật.

Hiệu năng phụ thuộc vào kích thước dữ liệu, cache, phần cứng, tải đồng thời, network, scheduler, database plan và hành vi của phụ thuộc. Những yếu tố này cần được đo khi chạy bằng workload đại diện.

### 3.6. Không tự chứng minh được khả năng khai thác và tác động nghiệp vụ

Một đường dữ liệu có vẻ nguy hiểm trong mã chưa chắc có thể bị khai thác trong mọi ngữ cảnh. Ngược lại, một vấn đề bảo mật có thể phát sinh từ cấu hình, quyền hoặc tương tác nhiều dịch vụ mà scan mã nguồn không nhìn thấy.

Static analyzer có thể chỉ ra vị trí cần điều tra, nhưng nhóm thường cần xác nhận thêm:

- Dữ liệu không tin cậy có thực sự đến được điểm nhạy cảm không?
- Có lớp validation, encoding hoặc authorization nào bảo vệ đường đi đó không?
- Tài khoản và quyền runtime có cho phép thao tác hay không?
- Kết quả có thể quan sát được hoặc gây tác động đến dữ liệu không?
- Vấn đề có thể tái hiện trong môi trường được kiểm soát không?

Không chạy payload nguy hiểm trên hệ thống production chỉ để xác nhận một cảnh báo. Hãy dùng môi trường kiểm thử được phép, dữ liệu tổng hợp và phạm vi thử nghiệm đã xác định.

## 4. False positive và false negative

### 4.1. False positive

False positive là cảnh báo chỉ ra một vấn đề nhưng khi xem xét ngữ cảnh, đường lỗi không thể xảy ra hoặc không vi phạm thuộc tính được bảo vệ.

Ví dụ: analyzer cảnh báo dữ liệu có thể null trước khi gọi một hàm. Tuy nhiên, hợp đồng của hàm khởi tạo và kiểm tra trước đó bảo đảm giá trị không null trong mọi đường gọi thuộc phạm vi. Cảnh báo cần được đánh giá bằng bằng chứng, không nên bỏ qua chỉ vì nhóm nghĩ rằng nó không xảy ra.

Quy trình xử lý nên gồm:

1. Xác định rule, vị trí và đường dữ liệu mà công cụ báo cáo.
2. Kiểm tra điều kiện kích hoạt và các lớp bảo vệ.
3. Xác nhận bằng test, hợp đồng hoặc phân tích bổ sung khi cần.
4. Ghi lý do phân loại và người quyết định.
5. Tạo suppression có phạm vi hẹp, liên kết với finding và thời hạn xem xét nếu công cụ hỗ trợ.

Không nên tắt cả rule hoặc bỏ qua toàn bộ finding chỉ để làm pipeline xanh.

### 4.2. False negative

False negative xảy ra khi có lỗi nhưng công cụ không báo cáo. Nguyên nhân có thể gồm:

- Rule không bao phủ loại lỗi đó.
- Mã hoặc framework nằm ngoài phạm vi phân tích.
- Dependency hoặc cấu hình runtime không được scan.
- Đường dữ liệu đi qua reflection, plugin, native code hoặc dịch vụ bên ngoài.
- Phân tích bị giới hạn tài nguyên hoặc không hoàn tất.
- Lỗi phụ thuộc dữ liệu, thời điểm, tải hoặc trạng thái không thể suy ra từ mô hình tĩnh.

Không thể kết luận rằng hệ thống an toàn chỉ vì static analyzer không phát hiện finding. Cần kết hợp rà soát, kiểm thử động, kiểm chứng khi chạy và các kiểm soát khác theo rủi ro.

### 4.3. Không dùng tỷ lệ cảnh báo làm thước đo duy nhất

Một công cụ có nhiều cảnh báo không nhất thiết phát hiện tốt hơn. Một công cụ ít cảnh báo cũng không nhất thiết chính xác hơn. Nên theo dõi:

- Tỷ lệ finding được xác nhận là vấn đề thực.
- Mức độ nghiêm trọng và khả năng khai thác của finding.
- Số module và loại tài sản đã được scan.
- Tỷ lệ phân tích hoàn tất và phần bị bỏ qua.
- Thời gian xử lý finding.
- Lỗi lọt ra sau phát hành mà công cụ có thể đã phát hiện nếu cấu hình hoặc rule phù hợp.

Các chỉ số này cần được đọc cùng phạm vi scan, thay đổi code và mô hình rủi ro của sản phẩm.

## 5. Những lỗi thường cần kiểm chứng khi chạy

Một số loại vấn đề phụ thuộc trực tiếp vào trạng thái, dữ liệu hoặc tương tác runtime. Bảng dưới đây gợi ý cách bổ sung bằng chứng.

| Loại vấn đề | Vì sao phân tích tĩnh có thể chưa đủ | Kiểm chứng khi chạy phù hợp |
| --- | --- | --- |
| Dữ liệu thực tế và quy tắc nghiệp vụ | Giá trị và trạng thái database không có đầy đủ trong mô hình scan | Chạy với dữ liệu đại diện, kiểm tra kết quả và bất biến nghiệp vụ |
| Phân quyền | Quyền cuối cùng phụ thuộc token, role, policy và cấu hình runtime | Kiểm thử âm tính với nhiều danh tính và vai trò trên API/UI |
| Race condition | Lịch thực thi thread/process và tranh chấp tài nguyên khó dự đoán đầy đủ | Kiểm thử đồng thời, stress test và kiểm tra trạng thái cuối |
| Timeout và retry | Thời gian mạng, trạng thái provider và retry thực tế thay đổi | Fault injection, mô phỏng độ trễ và kiểm tra idempotency |
| Tương tác hệ thống ngoài | Hành vi provider, callback và giới hạn quota nằm ngoài mã nguồn | Contract test, sandbox test và kiểm thử tích hợp có kiểm soát |
| Hiệu năng | Tải, phần cứng, cache và database plan ảnh hưởng kết quả | Load, stress, soak test và đo latency/throughput |
| Phục hồi sau lỗi | Trạng thái hệ thống sau khi process hoặc dependency dừng không thể suy ra chỉ từ code | Chaos/fault test có kiểm soát, restart và xác nhận dữ liệu sau phục hồi |
| Tương thích môi trường | OS, browser, thiết bị, locale và cấu hình có thể khác nhau | Chạy trên ma trận môi trường đại diện |
| Trạng thái bất đồng bộ | Sự kiện có thể trễ, lặp, mất hoặc sai thứ tự | Kiểm thử event, consumer, retry, dead-letter và trạng thái cuối |

Kiểm chứng khi chạy cần có oracle rõ ràng. Chỉ quan sát rằng chương trình không crash hoặc API trả HTTP 200 thường không đủ để xác nhận nghiệp vụ.

## 6. Ví dụ: phân tích tĩnh và kiểm chứng lỗi phân quyền

Giả sử API trả thông tin lịch hẹn theo appointmentId. Static analyzer có thể phát hiện endpoint đọc dữ liệu và một số đường đi thiếu kiểm tra authorization rõ ràng. Tuy nhiên, để đánh giá đúng mức độ rủi ro, nhóm cần xem xét middleware, policy, token, cấu hình và cách endpoint được gọi.

Một quy trình xác nhận trong môi trường kiểm thử có thể gồm:

1. **Phân tích tĩnh:** xác định điểm vào API, vị trí truy cập dữ liệu và các lớp authorization được gọi hoặc có thể bị bỏ qua.
2. **Rà soát hợp đồng:** làm rõ người dùng được phép xem lịch của chính mình, lịch được chia sẻ hoặc lịch thuộc tổ chức theo quy tắc nào.
3. **Chuẩn bị dữ liệu:** tạo hai tài khoản kiểm thử và hai lịch hẹn thuộc quyền sở hữu khác nhau.
4. **Kiểm thử động:** tài khoản A truy cập lịch của A và lịch của B; lặp lại với vai trò quản trị hoặc vai trò được chia sẻ nếu nghiệp vụ có hỗ trợ.
5. **Kiểm chứng khi chạy:** kiểm tra phản hồi, trạng thái truy cập và log audit để xác nhận request bị từ chối không làm lộ nội dung lịch.
6. **Đối chiếu:** nếu test phát hiện truy cập trái phép, liên kết kết quả với finding tĩnh, sửa lỗi và thêm regression test.

Ví dụ tiêu chí:

~~~gherkin
Feature: Quyền xem lịch hẹn

  Scenario: Người dùng không có quyền xem lịch của người khác
    Given tài khoản A và tài khoản B sở hữu hai lịch hẹn khác nhau
      And tài khoản A đã đăng nhập
    When tài khoản A yêu cầu xem lịch thuộc tài khoản B
    Then hệ thống từ chối theo hợp đồng truy cập
      And không trả về nội dung hoặc dữ liệu nhạy cảm của lịch B
      And sự kiện truy cập bị từ chối có thể được kiểm tra trong audit log
~~~

Static analysis giúp chỉ ra nơi cần xem xét; kiểm thử động xác nhận một ma trận quyền cụ thể; audit log cung cấp bằng chứng về hành vi quan sát được. Kết luận chỉ áp dụng cho vai trò, cấu hình, endpoint và dữ liệu đã kiểm tra. Các vai trò hoặc đường truy cập khác cần được đưa vào phạm vi theo rủi ro.

## 7. Ví dụ: race condition và xử lý callback thanh toán

Một analyzer có thể phát hiện nhiều nơi cùng ghi vào trạng thái giao dịch hoặc cảnh báo thao tác cập nhật không có khóa rõ ràng. Nhưng việc hai callback thực sự đến gần nhau, transaction được commit theo thứ tự nào và dữ liệu cuối ra sao phụ thuộc vào runtime.

Kịch bản kiểm chứng:

1. Tạo một giao dịch ở trạng thái chờ.
2. Chuẩn bị hai callback hợp lệ cùng mã giao dịch.
3. Gửi hai callback gần như đồng thời trong môi trường kiểm thử.
4. Lặp lại với callback đến trễ sau một lần retry.
5. Xác nhận chỉ có một tác dụng phụ nghiệp vụ, trạng thái cuối hợp lệ và dữ liệu đối soát không bị nhân đôi.
6. Thu thập trace, log, mã giao dịch và kết quả kiểm tra dữ liệu.

Có thể biểu diễn thuộc tính cần bảo toàn:

\[
\text{Số lần ghi nhận thanh toán cho một mã giao dịch} \leq 1
\]

Đây là bất biến nghiệp vụ cần được xác nhận bằng trạng thái cuối và bằng chứng phù hợp. Một bài test chỉ kiểm tra response của từng callback có thể bỏ sót việc hai callback đều trả thành công nhưng cùng tạo tác dụng phụ.

## 8. Thiết kế chiến lược kết hợp static analysis và runtime verification

### 8.1. Bắt đầu từ rủi ro và thuộc tính cần bảo vệ

Không chọn công cụ trước rồi tìm vấn đề để scan. Hãy bắt đầu từ rủi ro:

- Dữ liệu nào cần được bảo vệ?
- Bất biến nghiệp vụ nào không được vi phạm?
- Những quyền hoặc trạng thái nào cần được kiểm soát?
- Lỗi có thể xuất hiện do dữ liệu, tải, thời gian, cấu hình hay tương tác nào?
- Có thể quan sát thuộc tính đó ở đâu?

Từ đó chọn phương pháp có khả năng tạo bằng chứng phù hợp. Ví dụ, kiểm tra secret nên dùng secret scanning; sai lệch schema có thể cần static schema validation và contract test; giao dịch lặp cần phân tích code cùng kiểm thử idempotency khi chạy.

### 8.2. Ma trận chọn phương pháp

| Rủi ro hoặc thuộc tính | Phân tích tĩnh | Kiểm thử động | Runtime verification / giám sát |
| --- | --- | --- | --- |
| Null dereference hoặc lỗi kiểu | Type analysis, nullability rule | Test dữ liệu null và biên | Theo dõi exception trong môi trường chạy |
| Injection | Taint analysis, SAST | Payload kiểm thử an toàn trên môi trường được phép | Theo dõi request bất thường và lỗi bảo mật |
| Quyền truy cập | Review policy và đường gọi authorization | Kiểm thử theo vai trò và chủ sở hữu dữ liệu | Audit event, cảnh báo truy cập bất thường |
| Giao dịch lặp | Review transaction/idempotency logic | Gửi request hoặc callback lặp, kiểm tra trạng thái cuối | Monitor số giao dịch trùng và đối soát |
| Hiệu năng | Phân tích độ phức tạp, truy vấn đáng ngờ | Load/stress/soak test | Theo dõi latency, throughput và saturation |
| Phục hồi | Review retry, timeout và state transition | Fault injection, restart, network failure | Theo dõi thời gian phục hồi và lỗi kéo dài |
| Dependency có lỗ hổng | SCA và kiểm tra phiên bản | Kiểm thử tích hợp hoặc xác minh bản vá trong môi trường phù hợp | Theo dõi inventory, cảnh báo lỗ hổng mới và phiên bản triển khai |

Không phải mọi hàng đều cần đủ ba cột. Hãy chọn cách tiếp cận theo loại lỗi, mức rủi ro, khả năng quan sát và chi phí kiểm chứng.

### 8.3. Đặt static analysis vào pipeline

Một pipeline tham khảo:

~~~mermaid
flowchart TD
    SRC["Commit / pull request"] --> PRE["Format, lint, type check"]
    PRE --> SA["Static analysis, SAST, SCA, secret scan"]
    SA --> REVIEW["Review finding và ngoại lệ"]
    REVIEW --> BUILD["Build artifact"]
    BUILD --> TEST["Unit và component test"]
    TEST --> INT["Contract và integration test"]
    INT --> SYS["System, security và performance test theo rủi ro"]
    SYS --> GATE{"Quality gate đạt?"}
    GATE -->|"Không"| FIX["Sửa lỗi hoặc bổ sung bằng chứng"]
    FIX --> SRC
    GATE -->|"Có"| DEPLOY["Triển khai có kiểm soát"]
    DEPLOY --> MON["Runtime monitor và telemetry"]
    MON --> FEEDBACK["Sự cố, cảnh báo và phản hồi"]
    FEEDBACK --> SRC
~~~

Pipeline cần công bố trạng thái phân tích, thời điểm scan, commit, phiên bản rule và phạm vi tài sản. Nếu một phần không được phân tích, báo cáo phải nêu rõ để người đọc không nhầm “không có finding” với “đã kiểm tra toàn bộ”.

### 8.4. Thiết kế runtime monitor

Một monitor hữu ích cần:

- Thuộc tính cần kiểm tra được định nghĩa rõ, ví dụ trạng thái đơn hàng không thể chuyển từ đã hủy sang đã thanh toán.
- Sự kiện đầu vào có schema và định danh giao dịch.
- Thứ tự hoặc cửa sổ thời gian cần quan sát được quy định.
- Hành động khi vi phạm được xác định: log, alert, chặn thao tác hoặc tạo incident.
- Cơ chế xử lý dữ liệu thiếu, trễ, trùng và sai thứ tự.
- Giới hạn tác động và chi phí của việc thu thập telemetry.

Monitor chỉ có thể xác nhận những gì nó quan sát được. Nếu event bị mất trước khi tới monitor, kết quả “không thấy vi phạm” không chứng minh bất biến luôn được bảo toàn. Cần đánh giá độ đầy đủ của nguồn sự kiện và cơ chế đối soát.

## 9. Đánh giá chất lượng và giới hạn của bằng chứng

### 9.1. Đọc báo cáo static analysis đúng cách

Khi nhận báo cáo, hãy kiểm tra:

1. Commit hoặc artifact nào đã được phân tích?
2. Những thư mục, ngôn ngữ, module và dependency nào nằm trong phạm vi?
3. Công cụ và rule set phiên bản nào được sử dụng?
4. Scan có hoàn tất hay bị giới hạn thời gian/tài nguyên?
5. Có file, generated code, binary hoặc module nào bị bỏ qua?
6. Finding có severity, confidence và đường dữ liệu cụ thể không?
7. Ngoại lệ cũ còn hiệu lực và có đúng phạm vi không?

Một báo cáo cần có metadata đủ để tái lập. Nếu thay đổi code sau scan, cần xác định phần nào phải phân tích lại.

### 9.2. Đánh giá kiểm thử động và runtime verification

Với kiểm thử động, cần ghi:

- Phiên bản phần mềm, môi trường, cấu hình và dữ liệu.
- Kịch bản, điều kiện trước/sau và test oracle.
- Phạm vi đầu vào, tải, vai trò và phụ thuộc đã sử dụng.
- Kết quả, log, trace và lý do thất bại.
- Những đường đi hoặc điều kiện chưa được kiểm tra.

Với runtime verification, bổ sung:

- Nguồn sự kiện và mức độ đầy đủ của dữ liệu.
- Cách xử lý event trễ, mất hoặc trùng.
- Phiên bản monitor và thuộc tính được kiểm tra.
- Cửa sổ quan sát và điều kiện cảnh báo.
- Tác động hiệu năng và cách xử lý khi monitor không sẵn sàng.

### 9.3. Không suy rộng quá mức

Các kết luận sau là quá mức nếu không có bằng chứng tương ứng:

- “Không có cảnh báo SAST nên ứng dụng an toàn.”
- “Tất cả test đã pass nên không còn lỗi.”
- “Không có alert nên hệ thống không vi phạm bất biến.”
- “Đã scan repository nên mọi dependency và cấu hình triển khai đều được kiểm tra.”

Thay vào đó, báo cáo nên nêu rõ: phương pháp nào đã dùng, phạm vi nào đã kiểm tra, điều kiện nào đã quan sát, finding nào được xử lý và khoảng trống nào còn lại.

## 10. Các quyết định thực tế khi nguồn lực có hạn

Không cần chạy mọi công cụ trên mọi thay đổi với cùng độ sâu. Có thể phân tầng theo rủi ro:

- **Mỗi pull request:** formatter, lint, type check, static analysis nhanh, secret scan và kiểm thử thành phần liên quan.
- **Theo nhánh tích hợp hoặc lịch:** SAST/SCA sâu hơn, contract test, integration test và kiểm tra cấu hình toàn diện.
- **Trước phát hành:** kiểm thử hệ thống, bảo mật, hiệu năng, phục hồi và xác nhận các finding nghiêm trọng.
- **Sau triển khai:** runtime monitor, telemetry, canary và đối soát các thuộc tính nghiệp vụ quan trọng.

Việc phân tầng phải dựa trên thời gian phản hồi và mức độ rủi ro. Không trì hoãn một kiểm tra bắt buộc hoặc rủi ro nghiêm trọng chỉ để pipeline nhanh hơn.

Khi một finding bị hoãn hoặc miễn trừ, cần ghi:

- Lý do và bằng chứng hỗ trợ quyết định.
- Phạm vi code, dịch vụ hoặc môi trường chịu ảnh hưởng.
- Tác động nếu đánh giá sai.
- Biện pháp giảm thiểu tạm thời.
- Người phê duyệt và thời hạn xem xét lại.

## 11. Checklist đánh giá giới hạn và chọn kiểm chứng khi chạy

- [ ] Đã xác định static analyzer kiểm tra loại tài sản và ngôn ngữ nào.
- [ ] Đã kiểm tra scan có hoàn tất và phạm vi nào bị bỏ qua.
- [ ] Đã hiểu giả định và giới hạn của rule hoặc mô hình phân tích.
- [ ] Finding được phân loại theo bằng chứng, không chỉ dựa vào severity.
- [ ] Có quy trình xử lý false positive và theo dõi false negative qua sự cố thực tế.
- [ ] Các rủi ro phụ thuộc dữ liệu, cấu hình, quyền, thời gian và concurrency có kiểm chứng runtime phù hợp.
- [ ] Test oracle xác định kết quả đúng ở mức nghiệp vụ và kỹ thuật.
- [ ] Môi trường, dữ liệu và dependency của lần chạy được ghi nhận.
- [ ] Runtime monitor có thuộc tính, nguồn sự kiện, cửa sổ quan sát và hành động rõ ràng.
- [ ] Đã đánh giá khả năng mất, trễ hoặc trùng sự kiện quan sát.
- [ ] Kết quả tĩnh và động được liên kết với cùng yêu cầu, rủi ro và phiên bản.
- [ ] Báo cáo nêu rõ giới hạn bằng chứng và rủi ro còn lại.
- [ ] Ngoại lệ có chủ sở hữu, biện pháp giảm thiểu và thời hạn xem xét.

Phân tích tĩnh giúp phát hiện sớm nhiều vấn đề trong mã và mô hình chương trình; kiểm chứng khi chạy cho biết hành vi thực tế dưới các điều kiện đã quan sát. Khi hiểu đúng giới hạn của từng nguồn và chọn cách kết hợp theo rủi ro, nhóm có thể đưa ra kết luận chính xác hơn, giảm lỗi lọt và giải thích rõ mức độ tin cậy của quyết định phát hành.
