# Cách tiếp cận: Phối hợp kiểm thử tĩnh, kiểm thử động và phản hồi từ vận hành

## 1. Vì sao cần phối hợp ba nguồn bằng chứng?

Một sản phẩm có thể vượt qua kiểm tra mã nguồn nhưng vẫn hoạt động sai khi chạy. Một bộ kiểm thử động có thể đạt nhưng chưa bao phủ được điều kiện hiếm hoặc môi trường thực tế. Một hệ thống đang vận hành ổn định trong vài ngày cũng chưa chứng minh rằng mọi yêu cầu và rủi ro quan trọng đã được xác nhận. Mỗi cách tiếp cận nhìn thấy một phần khác nhau của chất lượng sản phẩm.

Trong **VALIDATION_TESTING_STRATEGY**, kiểm thử tĩnh, kiểm thử động và phản hồi từ vận hành cần được tổ chức thành một vòng học liên tục:

- **Kiểm thử tĩnh (static testing):** phân tích yêu cầu, thiết kế, mã nguồn và cấu hình mà không cần thực thi chương trình để phát hiện mâu thuẫn, sai lệch, mẫu lỗi và rủi ro sớm.
- **Kiểm thử động (dynamic testing):** thực thi phần mềm với dữ liệu và điều kiện xác định, quan sát hành vi thực tế rồi so sánh với tiêu chí mong đợi.
- **Phản hồi từ vận hành (operational feedback):** sử dụng tín hiệu từ môi trường chạy thật hoặc môi trường gần production để hiểu cách sản phẩm hoạt động dưới điều kiện sử dụng, tải, phụ thuộc và hành vi người dùng thực tế.

Ba nguồn bằng chứng bổ trợ cho nhau. Phân tích tĩnh giúp ngăn lỗi trước khi chạy; kiểm thử động chứng minh hành vi trong những điều kiện được chọn; dữ liệu vận hành cho biết các giả định kiểm thử có phản ánh thực tế hay không. Kết quả từ mỗi nguồn cần quay lại cập nhật yêu cầu, mô hình rủi ro, thiết kế, bộ kiểm thử và tiêu chí phát hành.

Mục tiêu không phải chạy thật nhiều công cụ. Mục tiêu là chọn đúng phương pháp cho từng loại rủi ro, biết mỗi phương pháp chứng minh được điều gì và kết nối kết quả thành bằng chứng có thể truy vết.

## 2. Hiểu đúng ba cách tiếp cận

### 2.1. Kiểm thử tĩnh

Kiểm thử tĩnh xem xét sản phẩm hoặc tài liệu mà không thực thi luồng chương trình cần kiểm tra. Nó có thể được thực hiện thủ công hoặc tự động.

Các hoạt động thường gặp:

- Rà soát yêu cầu, user story và tiêu chí chấp nhận để tìm chỗ mơ hồ, mâu thuẫn hoặc thiếu trường hợp lỗi.
- Rà soát kiến trúc và thiết kế để phát hiện điểm phụ thuộc quá chặt, ranh giới tin cậy không rõ, đường đi dữ liệu nhạy cảm hoặc thiếu cơ chế phục hồi.
- Peer review mã nguồn để kiểm tra logic, khả năng đọc hiểu, xử lý lỗi, điều kiện biên và quy ước của nhóm.
- Static code analysis để tìm lỗi tiềm ẩn, cấu trúc khó bảo trì, API nguy hiểm hoặc vi phạm quy tắc lập trình.
- Phân tích bảo mật tĩnh (SAST), phân tích thành phần phụ thuộc (SCA), kiểm tra secret và cấu hình hạ tầng dưới dạng mã.
- Kiểm tra schema, hợp đồng API, cấu hình triển khai, migration và tài liệu kỹ thuật.

Kiểm thử tĩnh đặc biệt hữu ích khi lỗi có thể được phát hiện trực tiếp trong tài liệu hoặc mã nguồn, trước khi cần môi trường thực thi. Tuy nhiên, một cảnh báo tĩnh không tự động chứng minh rằng lỗi có thể xảy ra trong mọi đường chạy. Nhóm cần xem xét ngữ cảnh, mức độ ảnh hưởng, khả năng khai thác và bằng chứng bổ sung.

### 2.2. Kiểm thử động

Kiểm thử động thực thi phần mềm hoặc một phần của hệ thống trong điều kiện được kiểm soát. Người kiểm thử cung cấp đầu vào, thiết lập trạng thái ban đầu, thực hiện hành động và quan sát kết quả.

Các cấp độ và kỹ thuật thường gặp:

- **Unit/component testing:** xác nhận hàm, lớp, module hoặc dịch vụ nhỏ với dữ liệu và phụ thuộc được kiểm soát.
- **Integration testing:** xác nhận tương tác giữa các thành phần, chẳng hạn service với database, API với message broker hoặc consumer với provider.
- **Contract testing:** xác nhận provider và consumer tuân thủ cùng một hợp đồng dữ liệu và hành vi.
- **System/end-to-end testing:** xác nhận hành trình nghiệp vụ qua ranh giới của hệ thống.
- **Acceptance testing:** đánh giá sản phẩm có đáp ứng mục tiêu và tiêu chí chấp nhận của người dùng hoặc nghiệp vụ hay không.
- **Non-functional testing:** đo hiệu năng, độ tin cậy, khả năng phục hồi, khả năng truy cập, tương thích và bảo mật trong điều kiện phù hợp.
- **Exploratory testing:** người kiểm thử chủ động khảo sát hành vi, thử giả thuyết và tìm tình huống chưa được mô tả trong kịch bản.

Kiểm thử động cung cấp bằng chứng trực tiếp về hành vi trong lần chạy và môi trường cụ thể. Kết quả chỉ có giá trị trong giới hạn của dữ liệu, cấu hình, phiên bản, tải và các phụ thuộc đã sử dụng.

### 2.3. Phản hồi từ vận hành

Phản hồi vận hành là dữ liệu thu được khi sản phẩm được triển khai và sử dụng. Nguồn có thể bao gồm:

- Logs có cấu trúc, metrics và distributed traces.
- Tỷ lệ lỗi, độ trễ, thông lượng, mức sử dụng tài nguyên và trạng thái phụ thuộc.
- Cảnh báo, sự cố, thời gian phục hồi và kết quả điều tra nguyên nhân gốc.
- Phản hồi từ người dùng, bộ phận hỗ trợ, nhóm vận hành và chủ sản phẩm.
- Tỷ lệ hoàn tất hành trình, tỷ lệ hủy, giao dịch thất bại và các chỉ số nghiệp vụ phù hợp.
- Kết quả triển khai canary, progressive delivery hoặc thử nghiệm có kiểm soát.

Nguồn vận hành giúp nhận ra điều kiện thực tế mà môi trường kiểm thử có thể chưa mô phỏng đầy đủ: dữ liệu có phân bố khác dự kiến, tải tăng theo thời điểm, nhà cung cấp chậm, thiết bị người dùng đa dạng hoặc các sự kiện hiếm xuất hiện theo chuỗi.

Phản hồi vận hành không thay thế kiểm thử trước phát hành. Một cảnh báo không phải lúc nào cũng xác định được nguyên nhân; việc không có cảnh báo cũng không chứng minh hệ thống không có lỗi. Cần kết hợp telemetry với tiêu chí nghiệp vụ, kiểm tra và quy trình điều tra.

## 3. Ba cách tiếp cận phát hiện những loại vấn đề khác nhau

| Khía cạnh | Kiểm thử tĩnh | Kiểm thử động | Phản hồi vận hành |
| --- | --- | --- | --- |
| Đối tượng quan sát | Yêu cầu, thiết kế, mã nguồn, cấu hình, dependency | Chương trình đang thực thi trong môi trường kiểm thử | Sản phẩm đang chạy trong môi trường sử dụng |
| Thời điểm phát hiện | Thường sớm, trước hoặc trong khi phát triển | Trong quá trình xây dựng và xác nhận bản dựng | Sau triển khai hoặc trong các đợt chạy production-like |
| Ví dụ phát hiện | Nhánh xử lý thiếu, secret bị commit, schema không tương thích | Tính sai giá, API trả sai trạng thái, timeout không được xử lý | Độ trễ tăng, lỗi provider theo giờ cao điểm, người dùng bỏ dở hành trình |
| Bằng chứng | Review comment, báo cáo analyzer, kết quả scan | Test result, log, trace, dữ liệu đầu ra | Dashboard, alert, incident, phản hồi người dùng, chỉ số nghiệp vụ |
| Giới hạn | Có thể có cảnh báo giả và không thấy mọi hành vi runtime | Chỉ bao phủ điều kiện, dữ liệu và môi trường đã chạy | Phản ánh những gì đã xảy ra và quan sát được; có thể đến sau khi người dùng chịu ảnh hưởng |
| Cách phản hồi | Sửa yêu cầu, thiết kế, mã nguồn hoặc cấu hình | Sửa lỗi, bổ sung test, cập nhật oracle và phạm vi | Tạo regression test, điều chỉnh thiết kế, ngưỡng cảnh báo và vận hành |

Không nên dùng một nguồn để thay thế hoàn toàn nguồn khác. Ví dụ, SAST có thể phát hiện một đường nối chuỗi truy vấn nguy hiểm, nhưng kiểm thử động mới xác nhận được cách ứng dụng xử lý một payload cụ thể. Ngược lại, một bộ kiểm thử API có thể pass với bộ dữ liệu hiện tại nhưng review thiết kế phát hiện thiếu giới hạn truy cập ở một nhánh chưa được chạy.

## 4. Tổ chức vòng đời kiểm thử kết hợp

Một luồng phối hợp có thể bắt đầu từ yêu cầu và tiếp tục đến sau phát hành:

~~~mermaid
flowchart TD
    REQ["Yêu cầu và tiêu chí chấp nhận"] --> SR["Rà soát yêu cầu, rủi ro và thiết kế"]
    SR --> CODE["Phát triển và peer review"]
    CODE --> STATIC["Static analysis, SAST, SCA, kiểm tra cấu hình"]
    STATIC --> G1{"Kết quả tĩnh đạt<br/>ngưỡng đã định?"}
    G1 -->|"Chưa"| FIX1["Sửa tài liệu, thiết kế hoặc mã nguồn"]
    FIX1 --> SR
    G1 -->|"Đạt"| BUILD["Tạo artifact và triển khai môi trường kiểm thử"]
    BUILD --> DYNAMIC["Unit, contract, integration,<br/>system và acceptance test"]
    DYNAMIC --> G2{"Bằng chứng động<br/>đủ và đạt?"}
    G2 -->|"Chưa"| FIX2["Phân tích lỗi và sửa sản phẩm / test"]
    FIX2 --> CODE
    G2 -->|"Đạt"| RELEASE["Quyết định và triển khai có kiểm soát"]
    RELEASE --> OPS["Quan sát vận hành và phản hồi người dùng"]
    OPS --> SIGNAL["Phân tích telemetry, cảnh báo<br/>và sự cố"]
    SIGNAL --> LEARN["Cập nhật rủi ro, yêu cầu,<br/>thiết kế và regression test"]
    LEARN --> SR
~~~

### 4.1. Trước khi viết mã: dùng kiểm thử tĩnh để làm rõ điều cần xác nhận

Ở giai đoạn yêu cầu và thiết kế, nhóm có thể phát hiện sớm:

1. Tiêu chí chấp nhận không thể đo hoặc không xác định kết quả khi xảy ra lỗi.
2. Trạng thái nghiệp vụ thiếu hoặc chuyển trạng thái không hợp lệ.
3. Hợp đồng API/event thiếu trường, kiểu dữ liệu hoặc quy tắc tương thích.
4. Ranh giới bảo mật, quyền truy cập hoặc trách nhiệm dữ liệu chưa rõ.
5. Rủi ro hiệu năng, khả năng phục hồi hoặc phụ thuộc chưa có phương án xử lý.

Kết quả rà soát cần chuyển thành hành động cụ thể: câu hỏi cần làm rõ, thay đổi thiết kế, tiêu chí chấp nhận mới hoặc rủi ro cần kiểm thử động. Đừng để nhận xét review chỉ tồn tại trong một cuộc họp mà không có dấu vết giải quyết.

### 4.2. Trong khi phát triển: kiểm tra tĩnh liên tục

Có thể tích hợp các kiểm tra tự động vào pull request hoặc pipeline:

- Formatter và linter để phát hiện vấn đề định dạng và quy ước.
- Compiler hoặc type checker để tìm lỗi kiểu và tham chiếu.
- Static analyzer để tìm lỗi tiềm ẩn và mẫu code nguy hiểm.
- SAST và secret scanning để phát hiện vấn đề bảo mật trong mã nguồn.
- SCA để kiểm tra thư viện phụ thuộc, giấy phép và lỗ hổng đã biết.
- Kiểm tra schema, migration và cấu hình triển khai.

Nên chia kiểm tra theo thời gian phản hồi. Kiểm tra nhanh có thể chạy trên mỗi thay đổi; phân tích sâu hoặc scan toàn diện có thể chạy theo lịch hay trước các mốc phát hành. Nếu pipeline báo lỗi, kết quả cần chỉ rõ rule, vị trí, mức nghiêm trọng và cách xử lý.

Không nên tự động chặn mọi cảnh báo. Nhóm cần phân loại true positive, false positive, mức độ khai thác và ngoại lệ được phê duyệt. Ngoại lệ phải có lý do, người chịu trách nhiệm, phạm vi ảnh hưởng và thời hạn xem xét lại.

### 4.3. Trước phát hành: dùng kiểm thử động để xác nhận hành vi

Kiểm thử động cần chạy trên artifact xác định và môi trường có cấu hình được ghi nhận. Thứ tự thường đi từ nhanh đến rộng:

1. Unit và component test xác nhận quy tắc cốt lõi.
2. Contract test xác nhận giao diện giữa các thành phần.
3. Integration test xác nhận dữ liệu và trạng thái qua các ranh giới.
4. System và end-to-end test xác nhận hành trình nghiệp vụ quan trọng.
5. Kiểm thử phi chức năng xác nhận hiệu năng, bảo mật và phục hồi theo rủi ro.
6. Acceptance hoặc exploratory testing xác nhận các tình huống sử dụng có ý nghĩa với người dùng.

Không phải mọi thay đổi đều cần chạy toàn bộ bộ kiểm thử dài nhất. Phạm vi có thể dựa trên phân tích tác động, nhưng cần có kiểm tra nền tảng và không được bỏ qua luồng trọng yếu bị ảnh hưởng.

### 4.4. Sau phát hành: dùng phản hồi vận hành để kiểm tra giả định

Sau triển khai, nhóm theo dõi các chỉ số kỹ thuật và nghiệp vụ đã xác định trước. Cần so sánh với baseline, ngưỡng cảnh báo và hành vi dự kiến. Khi phát hiện sai lệch:

- Xác định phiên bản, thời điểm, nhóm người dùng và hành trình bị ảnh hưởng.
- Dùng correlation ID và trace để lần theo giao dịch qua các dịch vụ.
- Đối chiếu log và trạng thái nghiệp vụ với kết quả kiểm thử tiền phát hành.
- Phân biệt lỗi sản phẩm, lỗi cấu hình, lỗi phụ thuộc và thay đổi hành vi sử dụng.
- Ghi nhận nguyên nhân gốc, mức ảnh hưởng và biện pháp khắc phục.
- Bổ sung kiểm thử tái hiện và điều chỉnh kiểm soát tĩnh, động hoặc vận hành.

Nếu cần rollback, disable feature flag hoặc giảm lưu lượng, quyết định phải theo quy trình vận hành đã thống nhất. Sau khi xử lý, tiếp tục quan sát để xác nhận chỉ số đã trở về vùng chấp nhận.

## 5. Kết nối kết quả giữa ba nguồn

Vòng phản hồi chỉ hiệu quả khi kết quả của một phương pháp làm thay đổi hoạt động của các phương pháp còn lại.

| Phát hiện ban đầu | Phản hồi trong kiểm thử tĩnh | Phản hồi trong kiểm thử động | Phản hồi trong vận hành |
| --- | --- | --- | --- |
| Review phát hiện trạng thái đơn hàng chưa đầy đủ | Cập nhật state model và quy tắc chuyển trạng thái | Thêm test chuyển trạng thái hợp lệ, không hợp lệ và phục hồi | Theo dõi đơn ở trạng thái treo và cảnh báo theo thời hạn |
| SAST phát hiện xử lý đầu vào nguy hiểm | Sửa code, thêm rule hoặc guideline phù hợp | Thêm kiểm thử payload hợp lệ/không hợp lệ và kiểm tra bảo mật | Theo dõi lỗi bất thường, request bị từ chối và dấu hiệu khai thác |
| Integration test phát hiện callback lặp | Rà soát thiết kế idempotency và hợp đồng event | Thêm regression test gửi trùng, gửi trễ và retry | Theo dõi số callback lặp, giao dịch trùng và kết quả đối soát |
| Production ghi nhận độ trễ tăng | Rà soát truy vấn, cấu hình và thiết kế phụ thuộc | Thêm kiểm thử tải, soak test hoặc kiểm tra truy vấn | Đặt ngưỡng latency, saturation, alert và theo dõi xu hướng |
| Người dùng báo không hoàn tất được luồng | Rà soát tiêu chí chấp nhận và thiết kế trải nghiệm | Tạo exploratory test và kịch bản tái hiện theo thiết bị/dữ liệu | Phân tích funnel, lỗi client và phản hồi hỗ trợ |

### 5.1. Tạo liên kết truy vết

Mỗi phát hiện quan trọng nên được liên kết với:

- Yêu cầu hoặc hành trình nghiệp vụ liên quan.
- Mã rủi ro và thành phần/ranh giới bị ảnh hưởng.
- Phiên bản mã nguồn, artifact và cấu hình.
- Kết quả static analysis hoặc review có liên quan.
- Kịch bản kiểm thử động xác nhận hoặc tái hiện.
- Bằng chứng vận hành, incident hoặc phản hồi người dùng.
- Quyết định khắc phục, người chịu trách nhiệm và trạng thái hoàn tất.

Liên kết này cho phép nhóm trả lời câu hỏi: lỗi đã được phát hiện ở đâu, vì sao kiểm soát trước đó bỏ sót, biện pháp nào ngăn lỗi quay lại và có cần điều chỉnh quality gate hay không.

### 5.2. Chuyển sự cố thành regression test

Không phải sự cố nào cũng chuyển trực tiếp thành một bài kiểm thử tự động. Trước tiên, cần xác định chế độ lỗi và điều kiện kích hoạt. Sau đó chọn lớp kiểm thử phù hợp:

- Nếu nguyên nhân là quy tắc tính toán, bổ sung unit test hoặc property-based test.
- Nếu nguyên nhân là hợp đồng, bổ sung contract test.
- Nếu nguyên nhân là tương tác dịch vụ, bổ sung integration test.
- Nếu nguyên nhân chỉ xuất hiện trong luồng nhiều bước, bổ sung system hoặc end-to-end test có mục tiêu.
- Nếu nguyên nhân là tải, thời gian hoặc tài nguyên, bổ sung kiểm thử hiệu năng hay phục hồi.
- Nếu lỗi phụ thuộc điều kiện môi trường, bổ sung kiểm tra cấu hình, deployment hoặc runbook.

Mỗi regression test cần có oracle đủ nhạy để thất bại khi lỗi cũ quay lại. Nếu chỉ tái hiện hành động mà không kiểm tra kết quả cuối, bài test có thể pass dù lỗi vẫn tồn tại.

## 6. Thiết kế phản hồi vận hành có thể hành động

### 6.1. Chọn tín hiệu gắn với mục tiêu sản phẩm

Không nên thu thập mọi metric có thể có rồi chờ sự cố xảy ra. Hãy bắt đầu từ hành trình và rủi ro quan trọng, sau đó chọn tín hiệu phản ánh sức khỏe của hành vi đó.

| Mục tiêu hoặc rủi ro | Tín hiệu kỹ thuật | Tín hiệu nghiệp vụ |
| --- | --- | --- |
| Người dùng đăng nhập được | Tỷ lệ lỗi xác thực, độ trễ identity provider | Tỷ lệ đăng nhập thành công |
| Tạo đơn chính xác | Lỗi API, lỗi database, retry và transaction failure | Tỷ lệ tạo đơn thành công, số đơn ở trạng thái bất thường |
| Thanh toán không bị ghi nhận trùng | Callback error, consumer lag, số lần retry | Số giao dịch trùng, chênh lệch đối soát |
| Thông báo được gửi | Queue depth, delivery error, provider latency | Tỷ lệ thông báo gửi thành công theo thời hạn |
| Hành trình nhanh và ổn định | p50/p95/p99 latency, error rate, saturation | Tỷ lệ hoàn tất hành trình và tỷ lệ bỏ dở |

Chỉ số cần có định nghĩa, nguồn dữ liệu, cửa sổ thời gian, phân nhóm và người chịu trách nhiệm. Một ngưỡng cảnh báo không có hành động tiếp theo chỉ tạo thêm nhiễu.

### 6.2. Quan sát xuyên suốt một giao dịch

Trong hệ thống phân tán, một hành động người dùng có thể tạo ra nhiều request, event và tác vụ nền. Correlation ID hoặc trace ID giúp nối các phần này để nhóm hiểu giao dịch đi qua đâu và bị chậm hoặc thất bại ở bước nào.

Ví dụ với một đơn hàng:

~~~mermaid
sequenceDiagram
    autonumber
    participant USER as Người dùng
    participant OPS as Nhóm vận hành
    participant API as Order API
    participant PAY as Payment Adapter
    participant EXT as Payment Provider
    participant Q as Event Queue
    participant W as Worker
    participant OBS as Monitoring

    USER->>API: Tạo đơn (correlation ID)
    API->>PAY: Yêu cầu thanh toán
    PAY->>EXT: Payment request
    EXT-->>PAY: Accepted / Pending
    PAY-->>API: Trạng thái theo hợp đồng
    API->>Q: Phát OrderPaymentUpdated
    Q->>W: Giao event
    W->>API: Cập nhật trạng thái đơn
    API->>OBS: Log, metric, trace
    PAY->>OBS: Kết quả gọi provider
    W->>OBS: Kết quả xử lý event
    OBS-->>OPS: Dashboard / alert
~~~

Trong thực tế, không phải mọi thành phần đều gửi telemetry đến cùng một hệ thống. Cần bảo đảm metadata đủ để nối các dấu vết mà không làm lộ dữ liệu nhạy cảm. Log nên ghi mã tham chiếu thay vì toàn bộ token, thông tin thanh toán hoặc dữ liệu cá nhân.

### 6.3. Canary và triển khai có kiểm soát

Với thay đổi có rủi ro cao, nhóm có thể triển khai theo tỷ lệ nhỏ hoặc bật tính năng cho một nhóm người dùng được kiểm soát. Canary giúp so sánh chỉ số của phiên bản mới với baseline hoặc nhóm đối chứng.

Trước khi triển khai, xác định:

- Chỉ số nào được dùng để đánh giá thành công và thất bại.
- Ngưỡng nào kích hoạt dừng rollout hoặc rollback.
- Thời gian quan sát đủ để bao phủ chu kỳ nghiệp vụ liên quan.
- Cách xử lý khi dữ liệu ít, kết quả nhiễu hoặc có sự kiện bên ngoài.
- Người có quyền quyết định tiếp tục, tạm dừng hoặc khôi phục phiên bản.

Canary là một kiểm soát bổ sung sau khi đã có bằng chứng tiền phát hành. Nó không phù hợp để thử nghiệm tùy tiện trên luồng nhạy cảm hoặc dữ liệu có thể gây thiệt hại không thể đảo ngược.

## 7. Quality gate và quyết định phát hành

Quality gate kết hợp bằng chứng từ nhiều nguồn theo mức rủi ro. Một gate có thể xem xét:

| Nguồn | Ví dụ điều kiện |
| --- | --- |
| Kiểm thử tĩnh | Không còn cảnh báo nghiêm trọng chưa được xử lý; ngoại lệ có phê duyệt và thời hạn |
| Kiểm thử động | Các kịch bản trọng yếu đạt; contract và integration test liên quan đã chạy; lỗi nghiêm trọng được xử lý |
| Phi chức năng | Ngưỡng hiệu năng, bảo mật hoặc phục hồi quan trọng được đáp ứng |
| Môi trường và artifact | Đúng artifact, cấu hình và dữ liệu đã xác nhận; triển khai có thể truy vết |
| Vận hành | Dashboard, alert, runbook và người trực đã sẵn sàng; rollback hoặc biện pháp giảm thiểu khả thi |
| Rủi ro còn lại | Được ghi nhận, có chủ sở hữu và được người có thẩm quyền chấp nhận |

Không nên gộp tất cả thành một tỷ lệ pass duy nhất. Một lỗi nghiêm trọng ở luồng thanh toán hoặc quyền truy cập có thể cần chặn phát hành dù các kiểm tra khác đều đạt. Ngược lại, một cảnh báo tĩnh đã được xác nhận là false positive có thể được xử lý bằng ngoại lệ có kiểm soát thay vì làm mất tín hiệu của pipeline.

Quyết định phát hành cần dựa trên phiên bản cụ thể và bằng chứng gắn với phiên bản đó. Nếu mã nguồn, cấu hình hoặc dependency thay đổi sau khi kiểm thử, cần đánh giá lại phần bằng chứng bị ảnh hưởng.

## 8. Phân vai và nhịp phối hợp

| Vai trò | Trách nhiệm chính trong cách tiếp cận kết hợp |
| --- | --- |
| Chủ sản phẩm / nghiệp vụ | Xác định mục tiêu, tiêu chí chấp nhận và mức tác động của sai lệch |
| Kiến trúc sư | Rà soát ranh giới, phụ thuộc, luồng dữ liệu và rủi ro thiết kế |
| Nhà phát triển | Peer review, xử lý cảnh báo tĩnh, viết test thành phần và khắc phục lỗi |
| QA / kỹ sư kiểm thử | Thiết kế oracle, kiểm thử động, phân tích kết quả và truy vết rủi ro |
| DevSecOps / bảo mật | Thiết lập kiểm tra bảo mật, phân loại phát hiện và tư vấn kiểm soát |
| SRE / vận hành | Thiết kế telemetry, alert, runbook, điều tra sự cố và phản hồi production |
| Người quyết định phát hành | Xem xét bằng chứng, ngoại lệ và rủi ro còn lại trước khi cho phép phát hành |

Nhịp phối hợp có thể gồm rà soát yêu cầu khi bắt đầu tính năng, kiểm tra tự động mỗi pull request, kiểm thử động theo pipeline, rà soát rủi ro trước release và xem lại tín hiệu vận hành sau triển khai. Sự cố nghiêm trọng cần kích hoạt vòng phản hồi ngay, không phải chờ đến cuộc họp định kỳ.

## 9. Đo lường chất lượng của cách tiếp cận kết hợp

Nên đo hiệu quả của hệ thống kiểm soát, không chỉ đếm số lần chạy:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Thời điểm phát hiện lỗi | Lỗi được tìm thấy ở yêu cầu, review, pipeline, môi trường kiểm thử hay production |
| Tỷ lệ lỗi lọt | Số lỗi được phát hiện sau phát hành so với tổng lỗi được ghi nhận trong phạm vi xác định |
| Tỷ lệ cảnh báo tĩnh có giá trị | Mức độ cảnh báo dẫn đến hành động sửa hoặc kiểm soát thực tế |
| Độ bao phủ rủi ro trọng yếu | Tỷ lệ rủi ro ưu tiên cao có oracle và bằng chứng kiểm thử phù hợp |
| Độ ổn định của kiểm thử | Tỷ lệ kết quả flaky và số lần chạy lại cần thiết |
| Thời gian phát hiện và khôi phục | Thời gian từ khi sai lệch bắt đầu đến khi phát hiện và phục hồi |
| Thời gian đóng vòng phản hồi | Thời gian từ phát hiện đến khi có biện pháp ngăn tái diễn được xác nhận |

Các chỉ số phải có phạm vi đo và định nghĩa thống nhất. Tỷ lệ lỗi lọt có thể tăng khi nhóm cải thiện khả năng phát hiện hoặc thay đổi cách phân loại lỗi; cần đọc cùng số lượng thay đổi, mức độ sử dụng và độ bao phủ kiểm thử. Không dùng chỉ số để khuyến khích che giấu cảnh báo hoặc giảm số lỗi được ghi nhận.

## 10. Ví dụ hoàn chỉnh: một lỗi được phát hiện và ngăn tái diễn

Giả sử người dùng báo rằng một số đơn hàng đã thanh toán nhưng giao diện vẫn hiển thị “đang chờ”. Nhóm điều tra thấy callback từ cổng thanh toán đến đúng, nhưng worker xử lý event đôi lúc bị trễ.

**Bước 1 – Phản hồi vận hành:** dashboard cho thấy consumer lag tăng cùng thời điểm; trace liên kết giao dịch cho thấy API nhận callback nhưng event chưa được xử lý trong thời hạn kỳ vọng. Nhóm xác định phạm vi người dùng và đơn hàng bị ảnh hưởng.

**Bước 2 – Phân tích nguyên nhân:** log và dữ liệu trạng thái cho thấy worker có thể xử lý lại event sau timeout. Thiết kế hiện tại chưa bảo đảm chuyển trạng thái idempotent trong một nhánh retry.

**Bước 3 – Kiểm thử tĩnh:** review state transition và transaction boundary; analyzer hoặc review phát hiện nhánh xử lý cập nhật trạng thái mà không kiểm tra phiên bản/trạng thái hiện tại. Nhóm sửa logic và bổ sung quy tắc review cho xử lý event lặp.

**Bước 4 – Kiểm thử động:** thêm integration test gửi cùng event nhiều lần, gửi event trễ và làm worker gián đoạn giữa chừng. Xác nhận đơn chỉ chuyển trạng thái hợp lệ một lần, dữ liệu giao dịch không bị nhân đôi và retry có thể hoàn tất.

**Bước 5 – Phát hành có kiểm soát:** chạy bộ kiểm thử hồi quy trên artifact mới, triển khai canary và theo dõi consumer lag, tỷ lệ đơn treo, tỷ lệ xử lý event lỗi và đối soát giao dịch.

**Bước 6 – Đóng vòng:** sau thời gian quan sát đã định nghĩa, nhóm xác nhận chỉ số trở về vùng chấp nhận, cập nhật risk register, lưu incident review và liên kết regression test với lỗi đã xảy ra.

Ví dụ này cho thấy phản hồi vận hành tạo ra tình huống kiểm thử mới; kiểm thử tĩnh giúp sửa nguyên nhân trong thiết kế và mã; kiểm thử động xác nhận lỗi không còn tái hiện trong các điều kiện đã mô hình hóa. Sau phát hành, telemetry tiếp tục kiểm tra giả định và cung cấp tín hiệu nếu vấn đề quay lại.

## 11. Checklist phối hợp kiểm thử tĩnh, động và vận hành

- [ ] Yêu cầu và tiêu chí chấp nhận có thể kiểm tra, bao gồm cả trạng thái lỗi quan trọng.
- [ ] Rủi ro được liên kết với thành phần, hành trình và chủ sở hữu.
- [ ] Rà soát yêu cầu, thiết kế và mã nguồn được thực hiện ở thời điểm phù hợp.
- [ ] Static analysis, SAST, SCA và kiểm tra cấu hình có ngưỡng cùng quy trình xử lý ngoại lệ.
- [ ] Kết quả tĩnh quan trọng được chuyển thành thay đổi hoặc kịch bản xác nhận.
- [ ] Bộ kiểm thử động bao phủ các tầng cần thiết theo rủi ro và có oracle rõ ràng.
- [ ] Artifact, môi trường, dữ liệu và cấu hình của lần chạy được ghi nhận.
- [ ] Telemetry phản ánh cả sức khỏe kỹ thuật và kết quả nghiệp vụ quan trọng.
- [ ] Có correlation ID hoặc cơ chế tương đương để lần theo giao dịch xuyên dịch vụ.
- [ ] Alert có ngưỡng, người nhận và hành động xử lý cụ thể.
- [ ] Sự cố và phản hồi người dùng được phân tích để cập nhật rủi ro và regression test.
- [ ] Quality gate xem xét bằng chứng tĩnh, động, vận hành và rủi ro còn lại.
- [ ] Ngoại lệ có người phê duyệt, lý do và thời hạn xem xét lại.
- [ ] Có cơ chế đánh giá lại khi mã nguồn, cấu hình, dependency hoặc hành vi sử dụng thay đổi.

Khi ba nguồn bằng chứng được liên kết qua cùng yêu cầu, rủi ro và phiên bản sản phẩm, nhóm có thể phát hiện vấn đề sớm hơn, xác nhận hành vi trong điều kiện cụ thể và học từ cách sản phẩm thực sự vận hành. Đây là nền tảng để chiến lược validation testing luôn thích ứng với thay đổi mà vẫn giữ được tính truy vết và trách nhiệm trong quyết định chất lượng.
