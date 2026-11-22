# Bối cảnh sản phẩm: Phân tích kiến trúc, luồng dữ liệu và các điểm tích hợp

## 1. Vì sao cần hiểu bối cảnh sản phẩm trước khi xây dựng chiến lược kiểm thử?

Chiến lược kiểm thử xác nhận (validation testing strategy) chỉ có giá trị khi nó phản ánh cách sản phẩm thực sự được sử dụng, cách các thành phần phối hợp và những rủi ro có thể làm sai lệch kết quả. Một danh sách ca kiểm thử có thể bao phủ nhiều chức năng nhưng vẫn bỏ sót lỗi nghiêm trọng nếu người thiết kế không hiểu dữ liệu đi qua những dịch vụ nào, trạng thái được lưu ở đâu, hệ thống bên ngoài tham gia tại thời điểm nào và kết quả nào được xem là bằng chứng đáng tin cậy.

Phân tích bối cảnh sản phẩm giúp trả lời bốn câu hỏi:

- **Sản phẩm phải đáp ứng điều gì?** Mục tiêu của người dùng, quy tắc nghiệp vụ, yêu cầu chức năng và các thuộc tính chất lượng cần được xác nhận.
- **Điều gì tạo ra hành vi đó?** Các giao diện, dịch vụ, kho dữ liệu, hàng đợi và hệ thống phụ thuộc cấu thành đường đi của một nghiệp vụ.
- **Dữ liệu và trạng thái thay đổi ra sao?** Đầu vào được kiểm tra, biến đổi, lưu trữ, truyền đi và đối soát như thế nào.
- **Có thể quan sát và chứng minh điều gì?** Mỗi kết quả kiểm thử cần gắn với yêu cầu, dữ liệu đầu vào, phiên bản phần mềm, môi trường chạy và bằng chứng thu thập được.

Trong bài này, **VALIDATION_TESTING_STRATEGY** được xem là năng lực xác định, tổ chức và đánh giá các hoạt động kiểm thử nhằm chứng minh sản phẩm phù hợp với mục đích sử dụng. Mô hình kiến trúc dưới đây là **mô hình tham chiếu** để phân tích và thiết kế chiến lược; nó không khẳng định một hệ thống triển khai cụ thể có sẵn các dịch vụ hay công cụ mang tên như trong sơ đồ. Khi áp dụng, cần ánh xạ từng khối sang thành phần, hợp đồng và quy trình thực tế của sản phẩm.

## 2. Phạm vi xác nhận và các bên liên quan

Xác nhận sản phẩm không chỉ là kiểm tra từng hàm hoặc từng màn hình. Nó xem xét một luồng sử dụng hoàn chỉnh trong bối cảnh người dùng, dữ liệu, quy tắc nghiệp vụ và các hệ thống phụ thuộc. Hoạt động này có thể bao gồm kiểm thử chức năng, tích hợp, hệ thống, chấp nhận và các thuộc tính phi chức năng như hiệu năng, độ tin cậy, khả năng truy cập, bảo mật hoặc khả năng phục hồi.

Nên phân biệt hai câu hỏi có liên quan:

- **Verification – sản phẩm có được xây dựng đúng theo đặc tả không?** Ví dụ: API trả về đúng mã trạng thái và cấu trúc dữ liệu đã cam kết.
- **Validation – sản phẩm có giải quyết đúng nhu cầu và tình huống sử dụng không?** Ví dụ: người mua có thể hoàn tất đơn hàng một cách dễ hiểu, an toàn và nhất quán trong điều kiện thanh toán thành công hoặc thất bại.

Hai hoạt động bổ trợ cho nhau. Một kiểm thử xác nhận tốt thường dựa trên các kiểm tra verification ở những ranh giới kỹ thuật, sau đó đánh giá kết quả nghiệp vụ đầu cuối.

| Bên liên quan | Điều họ cần xác nhận | Đầu vào hoặc bằng chứng hữu ích |
| --- | --- | --- |
| Chủ sản phẩm và chuyên gia nghiệp vụ | Luồng sử dụng có đáp ứng mục tiêu, chính sách và tiêu chí chấp nhận | User story, quy tắc nghiệp vụ, ví dụ dữ liệu hợp lệ và không hợp lệ |
| Kiến trúc sư và nhóm phát triển | Thành phần phối hợp đúng, hợp đồng ổn định và lỗi được xử lý đúng | Sơ đồ thành phần, API/event contract, log và trace |
| QA và kỹ sư kiểm thử | Kịch bản có thể tái hiện, có oracle rõ ràng và bao phủ rủi ro | Ma trận truy vết, bộ dữ liệu, ca kiểm thử, kết quả chạy |
| Vận hành và phát hành | Bản dựng có đủ điều kiện triển khai và có thể quan sát sau phát hành | Báo cáo pipeline, cảnh báo, chỉ số độ tin cậy, tiêu chí release gate |
| Người dùng hoặc đại diện người dùng | Sản phẩm dễ dùng và xử lý đúng tình huống thực tế | Kịch bản chấp nhận, phản hồi sử dụng, tiêu chí trải nghiệm |

Để tránh kiểm thử theo suy đoán, mỗi yêu cầu quan trọng cần có người chịu trách nhiệm giải thích, tiêu chí chấp nhận có thể quan sát và nguồn dữ liệu xác định kết quả mong đợi.

## 3. Kiến trúc tham chiếu cho hoạt động validation testing

Có thể phân tích hệ thống thành ba miền: **nguồn yêu cầu và thiết kế kiểm thử**, **môi trường thực thi sản phẩm**, và **bằng chứng cùng quyết định chất lượng**. Các miền kết nối với nhau qua những hợp đồng có thể kiểm tra.

~~~mermaid
flowchart LR
    R["Yêu cầu, mục tiêu người dùng<br/>Quy tắc nghiệp vụ"] --> D["Phân tích rủi ro<br/>Kịch bản và tiêu chí chấp nhận"]
    D --> T["Danh mục kiểm thử<br/>Liên kết truy vết"]
    T --> O["Điều phối kiểm thử<br/>Pipeline / Test runner"]
    O --> E["Chuẩn bị môi trường<br/>Cấu hình và dữ liệu"]
    E --> S["Sản phẩm được kiểm thử<br/>UI, API, dịch vụ, dữ liệu"]
    S <--> X["Hệ thống phụ thuộc<br/>API ngoài, event, sandbox"]
    O --> A["Bộ kết nối và bộ kiểm tra<br/>UI, API, contract, database"]
    A <--> S
    S --> V["Log, metric, trace và trạng thái"]
    O --> V
    V --> Q["Thu thập bằng chứng<br/>Phân tích và báo cáo"]
    Q --> G{"Đạt tiêu chí<br/>chất lượng?"}
    G -->|Đạt| P["Quyết định phát hành"]
    G -->|Không đạt| F["Tạo lỗi / phản hồi yêu cầu"]
    F --> D
~~~

### 3.1. Nguồn yêu cầu và thiết kế kiểm thử

Miền này chuyển mục tiêu sản phẩm thành các điều kiện có thể xác nhận:

1. Thu thập yêu cầu, hành trình người dùng, quy tắc nghiệp vụ, tiêu chí chấp nhận, ràng buộc pháp lý và yêu cầu phi chức năng.
2. Phân tích tác động nếu hành vi sai: ảnh hưởng đến người dùng, dữ liệu, doanh thu, an toàn, bảo mật hoặc khả năng vận hành.
3. Xác định kịch bản đại diện, trường hợp biên, trạng thái lỗi và điều kiện phục hồi.
4. Xác định **test oracle** – căn cứ để kết luận kết quả đúng hay sai. Oracle có thể là giá trị mong đợi, bất biến dữ liệu, hợp đồng API, trạng thái nghiệp vụ, sự kiện được phát ra hoặc giới hạn hiệu năng.
5. Liên kết yêu cầu với kịch bản, dữ liệu, bước thực thi và bằng chứng.

Yêu cầu mơ hồ cần được làm rõ trước khi biến thành một kết quả pass/fail. Chẳng hạn, câu “hệ thống phản hồi nhanh” chưa đủ để tạo kiểm thử hiệu năng; cần xác định loại tải, phân vị thời gian phản hồi, thời gian đo và điều kiện môi trường.

### 3.2. Điều phối và thực thi

Bộ điều phối nhận phiên bản mã, bộ kiểm thử, cấu hình môi trường và điều kiện chạy. Nó có thể được kích hoạt khi có pull request, sau khi triển khai lên môi trường kiểm thử, theo lịch hoặc theo yêu cầu của nhóm QA.

Bộ điều phối chịu trách nhiệm chọn tập kiểm thử phù hợp, cấp phát môi trường, chuẩn bị dữ liệu, khởi chạy runner, thu thập trạng thái và áp dụng quality gate. Runner thực hiện các bước qua adapter phù hợp: giao diện người dùng, API, hợp đồng dịch vụ, thông điệp hoặc truy vấn kiểm tra dữ liệu được cho phép.

Việc điều phối nên tách khỏi logic kiểm thử. Khi thay công cụ CI hoặc runner, kịch bản và tiêu chí nghiệp vụ không nên phải viết lại toàn bộ. Ngược lại, adapter cần phản ánh đúng hợp đồng kỹ thuật để tránh tạo ra một lớp trừu tượng che khuất lỗi thật.

### 3.3. Sản phẩm được kiểm thử và hệ thống phụ thuộc

Đối tượng kiểm thử (system under test – SUT) có thể gồm giao diện, API gateway, các dịch vụ nghiệp vụ, cơ sở dữ liệu, bộ xử lý nền và các thành phần triển khai. Ranh giới SUT phải được ghi rõ cho từng loại kiểm thử.

Một bài kiểm thử đơn vị có thể cô lập một thành phần. Kiểm thử tích hợp xác nhận tương tác giữa một số thành phần. Kiểm thử hệ thống hoặc đầu cuối đánh giá luồng nghiệp vụ qua nhiều ranh giới. Không nên dùng một bài kiểm thử đầu cuối duy nhất để thay thế mọi kiểm tra ở tầng thấp hơn, vì khi lỗi xảy ra sẽ khó xác định nguyên nhân và thời gian phản hồi thường chậm.

Hệ thống phụ thuộc có thể là dịch vụ thanh toán, định danh, gửi thông báo, đối tác dữ liệu hoặc nền tảng đám mây. Tùy mục tiêu, kiểm thử có thể dùng mô phỏng, stub, sandbox của nhà cung cấp hoặc kết nối thật. Lựa chọn này phải được ghi nhận vì mỗi cách có giới hạn bằng chứng khác nhau.

### 3.4. Bằng chứng, phân tích và quyết định

Kết quả “pass” chỉ có ý nghĩa khi biết kiểm thử nào đã chạy, trên bản dựng nào, với dữ liệu và cấu hình nào, dựa trên tiêu chí nào. Vì vậy, miền bằng chứng cần lưu tối thiểu:

- Mã yêu cầu và phiên bản tiêu chí chấp nhận.
- Mã commit, build hoặc artifact đã triển khai.
- Môi trường, cấu hình đã được làm sạch thông tin bí mật và phiên bản dữ liệu kiểm thử.
- Tên kịch bản, kết quả, thời điểm chạy và thời lượng.
- Log, trace, ảnh chụp hoặc phản hồi API cần thiết để giải thích kết quả.
- Mã lỗi hoặc liên kết tới vấn đề được tạo khi kiểm thử thất bại.

Quality gate nên được xác định trước khi chạy. Gate có thể yêu cầu tất cả kịch bản trọng yếu đạt, không còn lỗi nghiêm trọng chưa xử lý, ngưỡng hiệu năng được đáp ứng và bằng chứng cần thiết đã được thu thập. Một tỷ lệ pass cao không đủ để cho phép phát hành nếu một luồng quan trọng chưa được kiểm tra.

## 4. Luồng dữ liệu từ yêu cầu đến quyết định phát hành

Luồng dữ liệu là cách thông tin và trạng thái đi qua các thành phần. Phân tích luồng giúp tìm ra nơi dữ liệu bị biến đổi, nơi phát sinh bất đồng bộ, điểm có thể mất thông tin và vị trí đặt assertion phù hợp.

~~~mermaid
sequenceDiagram
    autonumber
    participant PO as Nguồn yêu cầu
    participant QA as Thiết kế kiểm thử
    participant CI as CI/CD và điều phối
    participant ENV as Môi trường kiểm thử
    participant SUT as Sản phẩm
    participant EXT as Hệ thống phụ thuộc
    participant OBS as Quan sát và báo cáo

    PO->>QA: Yêu cầu, quy tắc, tiêu chí chấp nhận
    QA->>QA: Phân tích rủi ro, tạo kịch bản và oracle
    QA->>CI: Bộ kiểm thử và liên kết truy vết
    CI->>ENV: Cấp môi trường, cấu hình và dữ liệu
    CI->>SUT: Triển khai bản dựng cần xác nhận
    CI->>SUT: Gửi yêu cầu kiểm thử
    SUT->>EXT: Gọi API hoặc phát sự kiện
    EXT-->>SUT: Phản hồi hoặc sự kiện kết quả
    SUT-->>CI: Kết quả quan sát được
    CI->>OBS: Trạng thái chạy và metadata bản dựng
    SUT->>OBS: Log, metric, trace
    OBS-->>QA: Bằng chứng và báo cáo
    QA->>PO: Kết quả, rủi ro còn lại và phản hồi
~~~

Một luồng chuẩn thường có các bước sau:

1. **Tiếp nhận thay đổi:** yêu cầu hoặc tiêu chí chấp nhận được cập nhật và gắn mã định danh, phiên bản.
2. **Phân tích tác động:** xác định chức năng, dịch vụ, dữ liệu và tích hợp bị ảnh hưởng; ưu tiên theo mức độ rủi ro.
3. **Thiết kế kiểm thử:** tạo kịch bản, dữ liệu, điều kiện trước/sau và oracle; liên kết chúng với yêu cầu.
4. **Tạo môi trường có thể tái lập:** triển khai đúng artifact, áp dụng cấu hình, chuẩn bị dữ liệu sạch và xác nhận các phụ thuộc sẵn sàng.
5. **Thực thi:** chạy kiểm thử theo tầng và thu thập trạng thái ở cả đường đi thành công lẫn đường đi lỗi.
6. **Đối chiếu:** so sánh kết quả thực tế với oracle; với luồng bất đồng bộ, chờ theo điều kiện và thời hạn xác định thay vì dựa vào khoảng ngủ cố định.
7. **Phân tích:** phân loại lỗi sản phẩm, lỗi môi trường, lỗi dữ liệu, lỗi kiểm thử hoặc kết quả không ổn định; giữ lại bằng chứng đủ để tái hiện.
8. **Ra quyết định và phản hồi:** áp dụng gate, ghi nhận rủi ro còn lại, tạo lỗi hoặc cập nhật yêu cầu và kịch bản liên quan.

### 4.1. Theo dõi dữ liệu và trạng thái qua các ranh giới

Với mỗi luồng quan trọng, hãy lập bảng theo dõi:

| Điểm trong luồng | Câu hỏi cần trả lời | Cách xác nhận gợi ý |
| --- | --- | --- |
| Đầu vào | Ai gửi dữ liệu? Trường nào bắt buộc? Có kiểm tra quyền và định dạng không? | Kiểm tra schema, validation rule, quyền truy cập và trường hợp dữ liệu sai |
| Biến đổi | Dịch vụ có áp dụng đúng quy tắc và chuẩn hóa dữ liệu không? | Assertion trên đầu ra, bảng quyết định và các trường hợp biên |
| Lưu trữ | Trạng thái nào được ghi? Có bảo đảm tính nhất quán và ràng buộc không? | Kiểm tra bất biến, khóa ngoại, giao dịch và trạng thái sau lỗi |
| Truyền nhận | API hoặc event có tuân thủ hợp đồng? Có retry, timeout hoặc trùng lặp không? | Contract test, kiểm thử timeout, retry, idempotency và schema version |
| Phản hồi | Người dùng và hệ thống gọi có nhận kết quả đúng không? | Kiểm tra mã phản hồi, nội dung, trạng thái cuối và thông báo |
| Quan sát | Có thể lần theo một giao dịch qua nhiều dịch vụ không? | Correlation ID, trace, log có cấu trúc và metric phù hợp |

Không phải mọi kiểm thử đều cần đọc trực tiếp cơ sở dữ liệu. Chỉ sử dụng kiểm tra ở tầng lưu trữ khi đó là bằng chứng phù hợp và được phép; ưu tiên xác nhận qua giao diện hoặc hợp đồng công khai nếu mục tiêu là hành vi mà người dùng hoặc bên gọi dịch vụ nhìn thấy.

## 5. Các điểm tích hợp cần đưa vào chiến lược

Mỗi điểm tích hợp là một ranh giới nơi dữ liệu, quyền hạn, giao thức hoặc giả định có thể khác nhau. Với từng điểm, cần ghi rõ chủ sở hữu, hợp đồng, cách cấu hình, cách mô phỏng, điều kiện lỗi và bằng chứng quan sát.

| Điểm tích hợp | Dữ liệu đi qua | Nội dung cần xác nhận | Rủi ro thường gặp |
| --- | --- | --- | --- |
| Quản lý mã nguồn và yêu cầu | Commit, pull request, user story, acceptance criteria | Bản dựng liên kết đúng thay đổi và yêu cầu; thay đổi có kích hoạt đúng tập kiểm thử | Thiếu liên kết truy vết, chạy nhầm phiên bản, bỏ sót kiểm thử bị ảnh hưởng |
| CI/CD và hệ thống triển khai | Artifact, biến cấu hình, trạng thái triển khai | Pipeline dùng đúng artifact; triển khai và rollback có thể quan sát | Artifact không đồng nhất, cấu hình lệch giữa môi trường, pipeline báo thành công quá sớm |
| Quản lý kiểm thử | Kịch bản, phiên bản, kết quả, người sở hữu | Kết quả có thể truy về yêu cầu và phiên bản bộ kiểm thử | Trùng lặp kịch bản, trạng thái cũ, không rõ phạm vi đã chạy |
| Giao diện và API | Request, response, session, token | Schema, mã lỗi, quyền, phân trang, giới hạn và tương thích ngược | Sai định dạng, lỗi xác thực, thay đổi hợp đồng không được phát hiện |
| Hàng đợi và event bus | Event, key, metadata, thứ tự và thời điểm | Schema event, khả năng xử lý lặp, retry, dead-letter và tính cuối cùng | Mất hoặc trùng sự kiện, sai thứ tự, consumer xử lý chậm |
| Cơ sở dữ liệu và kho dữ liệu | Bản ghi, giao dịch, bản sao, dữ liệu tổng hợp | Ràng buộc, tính nhất quán, migration và quyền truy cập | Dữ liệu cũ, ghi một phần, migration không tương thích |
| Dịch vụ bên thứ ba | Yêu cầu, phản hồi, callback, trạng thái sandbox | Hợp đồng, timeout, giới hạn tốc độ, xác thực và hành vi khi nhà cung cấp lỗi | Sandbox khác production, giới hạn quota, phản hồi không ổn định |
| Quan sát và cảnh báo | Log, metric, trace, correlation ID | Có thể liên kết một kết quả kiểm thử với hoạt động của các dịch vụ | Thiếu trace, log không đủ ngữ cảnh, lộ dữ liệu nhạy cảm |
| Bí mật và cấu hình | Secret, endpoint, feature flag, biến môi trường | Quyền tối thiểu, phân tách môi trường và xoay vòng cấu hình | Dùng nhầm secret, cấu hình sai, bí mật xuất hiện trong log |

### 5.1. Kiểm tra hợp đồng tại ranh giới

Hợp đồng tích hợp mô tả những điều hai thành phần cùng cam kết: cấu trúc dữ liệu, kiểu dữ liệu, trường bắt buộc, ý nghĩa trường, mã lỗi, quy tắc xác thực, thời hạn phản hồi và hành vi khi có lỗi. Kiểm thử hợp đồng giúp phát hiện thay đổi phá vỡ tương thích trước khi phải chạy toàn bộ hành trình đầu cuối.

Với API đồng bộ, hãy xác nhận cả phản hồi thành công và các lỗi như dữ liệu không hợp lệ, chưa xác thực, không đủ quyền, tài nguyên không tồn tại, xung đột và giới hạn tốc độ. Với event bất đồng bộ, cần xác nhận schema, versioning, khả năng xử lý lặp, retry, dead-letter và cách consumer xử lý sự kiện đến trễ.

### 5.2. Tích hợp thật, sandbox và mô phỏng

Không có một cách kết nối phù hợp cho mọi mục tiêu:

- **Mô phỏng hoặc stub** phù hợp để kiểm soát tình huống hiếm, lỗi mạng, timeout và phản hồi có tính quyết định. Nó không chứng minh nhà cung cấp thật đang hoạt động đúng.
- **Sandbox của nhà cung cấp** kiểm tra được nhiều quy tắc tích hợp thực tế hơn, nhưng có thể khác production về dữ liệu, giới hạn, độ ổn định hoặc tính năng.
- **Kết nối thật trong môi trường được kiểm soát** cung cấp bằng chứng gần thực tế nhất, nhưng cần giới hạn phạm vi, tài khoản, dữ liệu và tác động bên ngoài.

Chiến lược tốt thường kết hợp các cách trên theo mức rủi ro. Mỗi kết quả phải ghi rõ loại phụ thuộc đã dùng để người đọc hiểu giới hạn của bằng chứng.

## 6. Ví dụ minh họa: xác nhận luồng đặt hàng

Giả sử một sản phẩm thương mại điện tử có luồng đặt hàng gồm giao diện mua hàng, dịch vụ đơn hàng, dịch vụ tồn kho, cổng thanh toán và dịch vụ thông báo. Đây là ví dụ minh họa cho cách áp dụng mô hình, không phải mô tả một hệ thống cụ thể.

Yêu cầu nghiệp vụ: khi thanh toán được chấp nhận, đơn hàng chuyển sang trạng thái đã xác nhận và tồn kho được giữ hoặc trừ theo quy tắc; khi thanh toán bị từ chối, người mua nhận được thông báo phù hợp và đơn hàng không được ghi nhận là đã thanh toán.

Một bộ xác nhận có thể bao gồm:

| Tình huống | Hành động | Kết quả cần xác nhận |
| --- | --- | --- |
| Thanh toán thành công | Tạo đơn và gửi yêu cầu thanh toán hợp lệ | Đơn hàng có trạng thái phù hợp; giao dịch thanh toán được liên kết; tồn kho được cập nhật đúng; thông báo được phát theo quy tắc |
| Thanh toán bị từ chối | Cổng thanh toán trả về trạng thái từ chối | Đơn không ở trạng thái đã thanh toán; tồn kho được giải phóng nếu đã giữ trước đó; người mua thấy hướng xử lý phù hợp |
| Phản hồi thanh toán bị timeout | Dịch vụ thanh toán không phản hồi trong thời hạn | Hệ thống không tự suy diễn timeout là thất bại cuối cùng; trạng thái có thể đối soát và không tạo giao dịch trùng |
| Callback gửi lặp | Nhà cung cấp gửi lại cùng một thông báo | Xử lý idempotent; trạng thái và số tiền không bị cập nhật hai lần |
| Sự kiện thông báo đến trễ | Event được xử lý sau khi đơn đã chuyển trạng thái | Người dùng không nhận thông báo mâu thuẫn; thứ tự nghiệp vụ vẫn nhất quán |

Ở tầng API, kiểm tra schema và mã phản hồi. Ở tầng tích hợp, xác nhận hợp đồng giữa dịch vụ đơn hàng, tồn kho và thanh toán. Ở tầng hệ thống, đi qua hành trình người mua và kiểm tra trạng thái cuối cùng. Với xử lý bất đồng bộ, dùng correlation ID để nối request, callback, event và log; đợi đến khi điều kiện trạng thái đạt hoặc hết thời hạn kiểm thử đã định nghĩa.

Ví dụ này cho thấy một assertion ở giao diện là chưa đủ. Người dùng có thể nhìn thấy thông báo “Đặt hàng thành công” trong khi dữ liệu đơn hàng chưa được ghi hoặc event thanh toán chưa được xử lý. Chiến lược cần chọn bằng chứng ở nhiều ranh giới để xác nhận cả trải nghiệm lẫn tính nhất quán nghiệp vụ.

## 7. Các quyết định thiết kế ảnh hưởng đến độ tin cậy của kiểm thử

### 7.1. Chọn mức kiểm thử theo rủi ro

Đặt kiểm thử nhanh, ổn định ở tầng thấp để xác nhận quy tắc và biến đổi dữ liệu thường xuyên. Dùng kiểm thử tích hợp cho hợp đồng và tương tác có rủi ro. Giữ các kịch bản đầu cuối cho hành trình có giá trị nghiệp vụ cao. Cách phân bổ này giúp phát hiện lỗi gần nơi phát sinh và giữ thời gian phản hồi phù hợp.

### 7.2. Dữ liệu kiểm thử phải an toàn và tái lập

Mỗi kịch bản nên xác định dữ liệu đầu vào, trạng thái ban đầu và cách dọn dẹp. Ưu tiên dữ liệu tổng hợp hoặc đã được khử định danh; không đưa thông tin cá nhân hay bí mật production vào log và báo cáo. Nếu nhiều bài kiểm thử chạy song song, cần cách ly dữ liệu theo lần chạy hoặc theo định danh duy nhất để tránh tranh chấp.

### 7.3. Xử lý bất đồng bộ theo điều kiện

Với queue, event và tác vụ nền, thời điểm phản hồi không cố định. Kiểm thử nên chờ một điều kiện quan sát được, có timeout rõ ràng và báo cáo trạng thái cuối. Một khoảng ngủ cố định có thể làm kiểm thử chậm khi hệ thống nhanh và chập chờn khi hệ thống chậm.

### 7.4. Kiểm soát tính không ổn định

Kịch bản phụ thuộc vào thời gian, dữ liệu dùng chung, dịch vụ bên ngoài hoặc thứ tự chạy thường dễ flaky. Khi phát hiện, cần lưu bằng chứng và tìm nguyên nhân gốc như race condition, môi trường không sạch, đồng hồ lệch, retry không xác định hoặc oracle thiếu chính xác. Không nên tự động chạy lại đến khi pass mà không ghi nhận lần thất bại đầu tiên, vì cách đó che khuất tín hiệu chất lượng.

### 7.5. Xác định quality gate theo tác động

Gate cần phản ánh rủi ro phát hành. Ví dụ, lỗi làm sai số tiền, lộ dữ liệu, mất đơn hoặc phá vỡ luồng đăng nhập có thể chặn phát hành ngay cả khi phần lớn kiểm thử khác đạt. Với rủi ro thấp hơn, nhóm có thể chấp nhận phát hành có điều kiện nếu đã ghi rõ tác động, biện pháp giảm thiểu, người chịu trách nhiệm và thời hạn xử lý.

## 8. Đo lường hiệu quả của chiến lược

Không nên đánh giá chiến lược chỉ bằng số lượng ca kiểm thử hoặc tỷ lệ pass. Một bộ kiểm thử lớn có thể lặp lại cùng một đường đi và bỏ trống các rủi ro quan trọng. Nên kết hợp các chỉ số sau:

| Chỉ số | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| Độ bao phủ truy vết yêu cầu | Tỷ lệ yêu cầu quan trọng có kịch bản và bằng chứng tương ứng | Cho biết phần nào chưa có cách xác nhận |
| Bao phủ luồng nghiệp vụ trọng yếu | Mức độ các hành trình và trạng thái quan trọng đã được kiểm tra | Tập trung vào rủi ro người dùng và nghiệp vụ |
| Tỷ lệ lỗi lọt ra sau phát hành | Lỗi được phát hiện sau khi người dùng hoặc vận hành chịu ảnh hưởng | Gợi ý khoảng trống trong mô hình rủi ro hoặc oracle |
| Tỷ lệ kiểm thử flaky | Tỷ lệ kết quả thay đổi khi chạy lại cùng điều kiện | Phản ánh độ tin cậy của tín hiệu kiểm thử |
| Thời gian phản hồi | Thời gian từ thay đổi đến khi có kết quả đủ tin cậy | Ảnh hưởng đến tốc độ phát triển và sửa lỗi |
| Thời gian phân loại lỗi | Thời gian từ khi kiểm thử thất bại đến khi xác định được nguyên nhân | Cho biết chất lượng bằng chứng và khả năng quan sát |
| Tỷ lệ lỗi tái diễn | Lỗi tương tự xuất hiện lại sau khi đã xử lý | Gợi ý thiếu kiểm thử hồi quy hoặc xử lý nguyên nhân gốc |

Các chỉ số cần được đọc cùng ngữ cảnh. Ví dụ, tỷ lệ pass tăng có thể do nhóm đã loại bỏ những kịch bản khó hoặc giảm phạm vi kiểm thử. Hãy theo dõi thay đổi về phạm vi và rủi ro cùng lúc để tránh diễn giải sai.

## 9. Checklist phân tích kiến trúc và tích hợp

Trước khi chốt chiến lược validation testing, hãy xác nhận:

- [ ] Mục tiêu người dùng, quy tắc nghiệp vụ và tiêu chí chấp nhận đã rõ ràng, có thể quan sát.
- [ ] Các thành phần thuộc SUT và các hệ thống phụ thuộc đã được nhận diện.
- [ ] Luồng dữ liệu chính, trạng thái, điểm biến đổi và điểm lưu trữ đã được mô tả.
- [ ] Các giao diện API, event, database và callback có hợp đồng cùng chủ sở hữu.
- [ ] Kịch bản bao gồm đường thành công, lỗi, biên, timeout, retry và xử lý trùng khi phù hợp.
- [ ] Test oracle xác định rõ kết quả mong đợi ở từng ranh giới.
- [ ] Môi trường, cấu hình và dữ liệu có thể tái lập, cách ly và dọn dẹp.
- [ ] Cách dùng mock, stub, sandbox hoặc tích hợp thật được ghi rõ cùng giới hạn bằng chứng.
- [ ] Log, metric, trace và correlation ID đủ để lần theo một giao dịch.
- [ ] Mỗi kết quả gắn với yêu cầu, phiên bản phần mềm, môi trường và artifact.
- [ ] Quality gate có ngưỡng, chủ sở hữu và cách xử lý ngoại lệ rõ ràng.
- [ ] Báo cáo phản ánh cả độ bao phủ, rủi ro còn lại và độ tin cậy của bộ kiểm thử.

Khi các câu trả lời trên đã rõ, nhóm có thể chọn tầng kiểm thử, công cụ và mức tự động hóa dựa trên rủi ro thực tế. Kiến trúc, luồng dữ liệu và điểm tích hợp khi đó trở thành nền tảng để xây dựng một chiến lược xác nhận có thể giải thích, tái lập và hỗ trợ quyết định phát hành.
