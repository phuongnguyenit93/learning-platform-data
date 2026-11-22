# Đơn giản hóa kiến trúc và kiểm soát độ phức tạp phát sinh

## 1. Đơn giản hóa là một nguyên lý thiết kế có thể kiểm chứng

Trong thiết kế ứng dụng trên đám mây, **kiến trúc tốt không phải kiến trúc có nhiều dịch vụ hiện đại nhất**, mà là kiến trúc đáp ứng yêu cầu nghiệp vụ và mục tiêu chất lượng với mức phức tạp mà đội ngũ có thể hiểu, thay đổi, bảo mật và vận hành bền vững.

Một ứng dụng gồm vài thành phần được quản lý tốt có thể đáp ứng yêu cầu mở rộng, hiệu năng và độ tin cậy. Ngược lại, chia ứng dụng nhỏ thành hàng chục microservice, dùng nhiều loại cơ sở dữ liệu và triển khai đa vùng từ ngày đầu có thể tạo ra rủi ro mà doanh nghiệp chưa cần giải quyết.

Tuy nhiên, **đơn giản không đồng nghĩa với sơ sài**. Bỏ qua xác thực, khôi phục dữ liệu, kiểm toán hoặc xử lý giao dịch trùng có thể làm sơ đồ ngắn hơn nhưng khiến hệ thống khó vận hành và sửa chữa hơn. Đơn giản hóa đúng nghĩa là **giảm những thành phần, phụ thuộc và quy trình không tạo đủ giá trị**, đồng thời giữ các cơ chế cần thiết để thỏa yêu cầu.

Đây là nguyên lý xuyên suốt module **CLOUD_ARCHITECTURE**: từ yêu cầu nghiệp vụ, qua lựa chọn mạng, compute, dữ liệu và mô hình triển khai, mỗi thành phần bổ sung phải có lợi ích rõ ràng về **độ tin cậy, bảo mật, khả năng mở rộng, hiệu năng, chi phí hoặc vận hành**. Đánh giá theo tinh thần Well-Architected cần xem xét cả lợi ích và tổng chi phí duy trì.

Sau bài học, bạn có thể:

- Phân biệt độ phức tạp **vốn có** của bài toán với độ phức tạp **phát sinh** do cách triển khai.
- Nhận biết khi nào microservices, hàng đợi, nhiều cơ sở dữ liệu, đa vùng hay đa cloud thực sự cần thiết.
- Đánh giá tổng chi phí quyết định kiến trúc, kể cả chi phí vận hành, bảo mật, dữ liệu và phối hợp con người.
- Thiết kế kiến trúc ban đầu vừa đủ, có ranh giới module rõ ràng và có đường tiến hóa khi yêu cầu thay đổi.
- Theo dõi độ phức tạp và ra quyết định loại bỏ, hợp nhất hoặc thay thế thành phần dư thừa.

## 2. Hai nguồn gốc của độ phức tạp

### 2.1. Độ phức tạp vốn có (*essential complexity*)

Đây là phần khó không thể loại bỏ mà vẫn giữ nguyên yêu cầu nghiệp vụ. Ví dụ, nền tảng đặt chỗ phải bảo đảm hai khách không thể đồng thời xác nhận cùng một chỗ trong cùng khoảng thời gian; hệ thống thanh toán phải xử lý callback đến muộn hoặc bị gửi lặp; hệ thống y tế phải kiểm soát quyền truy cập dữ liệu nhạy cảm. Những yêu cầu này vẫn tồn tại dù ứng dụng chạy trên một máy chủ, container hay serverless.

### 2.2. Độ phức tạp phát sinh (*accidental complexity*)

Đây là phần khó do thiết kế, công nghệ và cách tổ chức tạo ra, chẳng hạn:

- Một luồng đặt chỗ gọi qua sáu dịch vụ đồng bộ dù chỉ có hai nhóm nghiệp vụ liên quan.
- Cùng một trạng thái khách hàng tồn tại trong bốn cơ sở dữ liệu nhưng không có quy tắc đồng bộ rõ ràng.
- Mỗi dịch vụ dùng framework, cách cấu hình và hệ thống theo dõi khác nhau.
- Một tính năng nhỏ yêu cầu sửa ba repository, năm pipeline và nhiều đội cùng phê duyệt.
- Triển khai hai nhà cung cấp cloud dù ứng dụng chưa có ràng buộc pháp lý hoặc kinh doanh cần điều đó.

Không phải mọi độ phức tạp phát sinh đều có thể triệt tiêu; một số là cái giá hợp lý để đáp ứng yêu cầu. Mục tiêu là **giảm phần không có lợi ích đủ lớn so với chi phí**.

| Góc nhìn | Dấu hiệu phức tạp | Câu hỏi chẩn đoán |
| --- | --- | --- |
| **Cấu trúc** | Quá nhiều thành phần, lớp trừu tượng, API và phụ thuộc | Một thay đổi nhỏ phải đi qua bao nhiêu ranh giới? |
| **Dữ liệu** | Nhiều bản sao, sự kiện, quy tắc nhất quán và luồng đối soát | Dữ liệu gốc ở đâu, ai sở hữu và sửa sai thế nào? |
| **Vận hành** | Nhiều pipeline, môi trường, cảnh báo, thủ tục phục hồi | Khi có sự cố, ai có thể chẩn đoán và khôi phục? |
| **Bảo mật** | Nhiều danh tính máy, bí mật, chính sách, điểm truy cập | Thành phần mới tạo thêm quyền và bề mặt tấn công nào? |
| **Tổ chức** | Quá nhiều nhóm và điểm bàn giao, kiến thức phân tán | Ai chịu trách nhiệm đầy đủ cho một hành trình người dùng? |
| **Theo thời gian** | Phiên bản cũ, tương thích ngược, chuyển đổi dữ liệu | Một thay đổi hợp đồng phải hỗ trợ bao nhiêu thế hệ hệ thống? |

**Độ phức tạp không chỉ nằm trên sơ đồ thành phần.** Có kiến trúc ít hộp nhưng mã nguồn phụ thuộc chằng chịt, khó sửa và dễ gây lỗi. Ngược lại, nhiều thành phần vẫn có thể hợp lý khi trách nhiệm rõ ràng, vận hành chuẩn hóa và có yêu cầu thực sự.

## 3. Những nguyên nhân làm kiến trúc phức tạp dần

### 3.1. Thiết kế cho quy mô chưa có bằng chứng

Nhóm chọn sharding, nhiều region, microservices hoặc event streaming vì dự đoán sẽ có “hàng triệu người dùng”, nhưng chưa phân biệt **tổng tài khoản**, **người dùng đồng thời**, **lưu lượng đỉnh**, **dữ liệu cần lưu** và **mức độ quan trọng của từng luồng**. Hãy xác định tải, tăng trưởng, ngưỡng phản hồi và chạy thử tải trước khi thêm cơ chế.

### 3.2. Chia dịch vụ theo lớp kỹ thuật thay vì ranh giới nghiệp vụ

Mô hình “controller service → business service → database service” biến lời gọi hàm thành chuỗi gọi từ xa, phát sinh timeout, retry, xác thực giữa dịch vụ, log phân tán và lỗi mạng. Tách dịch vụ nên dựa trên **năng lực nghiệp vụ độc lập, vòng đời thay đổi, quyền sở hữu dữ liệu, nhu cầu mở rộng riêng hoặc ranh giới tin cậy**, không chỉ vì có nhiều class.

### 3.3. Đưa bất đồng bộ vào mọi nơi

Hàng đợi và sự kiện hữu ích để tách xử lý nền, chịu tải đột biến và giảm phụ thuộc thời gian chạy. Nhưng chúng bổ sung việc giao lại thông điệp, thứ tự xử lý, tiêu thụ trùng, schema evolution, dead-letter queue và nhất quán cuối cùng. Chỉ dùng khi luồng không cần phản hồi ngay, cần hấp thụ burst, cần cách ly lỗi hoặc có lợi ích cụ thể khác. Thao tác yêu cầu xác nhận tức thì và nhất quán chặt có thể phù hợp giao dịch đồng bộ hơn.

### 3.4. Chọn quá nhiều công nghệ

Kết hợp nhiều database, framework, service mesh, bộ giám sát và công cụ CI/CD làm tăng yêu cầu kỹ năng, bản vá, hợp đồng và công sức duy trì. **Đa dạng công nghệ có chi phí cố định** ngay cả khi lưu lượng thấp. Chuẩn hóa một “đường đi thông dụng” (*paved road*) cho ứng dụng, triển khai, giám sát và phân quyền giúp giảm lỗi cấu hình. Ngoại lệ cần có lý do và chủ sở hữu.

### 3.5. Giữ cơ chế cũ sau khi thêm cơ chế mới

Ví dụ, đã chuyển sang định danh tập trung nhưng vẫn giữ hai luồng phân quyền cũ; đã có hàng đợi gửi thông báo nhưng cron job cũ vẫn gửi cùng dữ liệu; đã chuyển nơi lưu trữ nhưng hai nguồn cùng được phép ghi vô thời hạn. Mỗi lần thêm thành phần nên hỏi: **cơ chế nào được thay thế, khi nào xóa, và xác minh việc xóa an toàn ra sao?**

## 4. Nguyên tắc ra quyết định: đơn giản nhất nhưng đáp ứng đủ

Trước khi chọn công nghệ, hãy trả lời lần lượt:

1. **Vấn đề nào cần giải quyết?** Nêu hành vi, lưu lượng, rủi ro hoặc ràng buộc.
2. **Có bằng chứng chưa?** Dựa vào đo đạc, thử tải, sự cố, nghĩa vụ đã xác nhận hay giả định?
3. **Có thể cải tiến phương án hiện tại không?** Ví dụ tối ưu truy vấn, index, cache đúng chỗ, tăng tài nguyên hoặc retry có kiểm soát.
4. **Phương án mới thêm điều gì?** Đếm dịch vụ, dữ liệu, ranh giới mạng, bí mật, pipeline, nhóm sở hữu và cơ chế phục hồi.
5. **Lợi ích có đo được không?** Nêu mức cải thiện mong đợi và cách đánh giá.
6. **Khi nào cần xem lại quyết định?** Xác định tín hiệu tăng trưởng, giới hạn, rủi ro hoặc thay đổi tổ chức.

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ hoặc NFR"] --> B{"Có số liệu và tiêu chí chấp nhận?"}
    B -->|Chưa| C["Đo đường cơ sở, xác minh giả định"]
    C --> B
    B -->|Có| D{"Phương án hiện tại cải tiến nhỏ là đủ?"}
    D -->|Có| E["Tối ưu, thử tải, theo dõi kết quả"]
    D -->|Không| F["So sánh các phương án kiến trúc"]
    F --> G["Đánh giá lợi ích, phức tạp và rủi ro"]
    G --> H["Chọn phương án đủ đáp ứng, ghi ADR"]
    H --> I["Triển khai tăng dần, đo lại"]
    E --> I
    I --> J{"Các chỉ số và giới hạn còn phù hợp?"}
    J -->|Có| K["Tiếp tục duy trì"]
    J -->|Không| A
~~~

Hai nguyên lý hỗ trợ:

- **KISS (*Keep It Simple, Stupid*):** Chọn phương án dễ hiểu và bảo trì khi nó đáp ứng những yêu cầu cần thiết.
- **YAGNI (*You Aren't Gonna Need It*):** Tránh hiện thực hóa cơ chế chỉ phục vụ một tương lai chưa có bằng chứng. YAGNI không phải lý do bỏ qua yêu cầu bắt buộc về an toàn, bảo mật hoặc phục hồi.

Cần phân biệt **đầu tư tạo khả năng thay đổi** với **triển khai toàn bộ khả năng đó**. Tách module rõ ràng giúp về sau tách dịch vụ, nhưng không bắt buộc triển khai các module thành microservices ngay từ đầu.

## 5. So sánh các quyết định kiến trúc phổ biến

| Quyết định | Lựa chọn thường ít phức tạp hơn lúc đầu | Khi nào chấp nhận phức tạp bổ sung? | Chi phí và rủi ro mới |
| --- | --- | --- | --- |
| **Monolith / microservices** | Monolith có module rõ | Có nhu cầu deploy/scale độc lập đo được, miền nghiệp vụ rõ và đội sở hữu phù hợp | API từ xa, giao dịch phân tán, nhiều pipeline, quan sát xuyên dịch vụ |
| **Đồng bộ / bất đồng bộ** | Gọi đồng bộ có timeout cho phản hồi tức thì | Xử lý nền, fan-out, giảm phụ thuộc thời gian chạy, hấp thụ burst | Retry, thông điệp trùng, thứ tự, độ trễ, điều tra lỗi |
| **Một database / nhiều loại** | Một hệ quản trị phù hợp phần lớn dữ liệu | Nhu cầu dữ liệu đặc thù có chứng cứ mà hệ hiện tại không đáp ứng hợp lý | Nhiều hệ thống backup, IAM, migration, giám sát và kỹ năng |
| **Một region / nhiều region** | Một region với nhiều Availability Zone nếu phù hợp | RTO/RPO, địa lý, nghĩa vụ dữ liệu hoặc tác động mất region đòi hỏi | Replication, failover, định tuyến, split-brain, kiểm thử thảm họa |
| **Một cloud / đa cloud** | Một nhà cung cấp, quản trị phụ thuộc ở mức cần thiết | Hợp đồng, quy định, thị trường hoặc rủi ro tập trung đủ để biện minh | IAM, mạng, dữ liệu, nhân sự và vận hành trên nhiều nền tảng |
| **Managed / tự vận hành** | Dịch vụ quản lý khi đáp ứng ràng buộc | Cần tính năng/kiểm soát đặc thù hoặc tổng chi phí đã chứng minh | Quản trị vá lỗi, backup, capacity planning, on-call, giới hạn nhà cung cấp |
| **CI/CD chung / tùy biến riêng** | Một mẫu pipeline và quan sát chung | Có yêu cầu triển khai đặc thù đã xác minh | Phân mảnh quy trình, khó hỗ trợ và kiểm toán |

Đây là **định hướng**, không phải thứ hạng công nghệ bất biến. Monolith kém cấu trúc có thể phức tạp hơn một tập dịch vụ nhỏ quản lý tốt; managed service có thể đắt trên hóa đơn nhưng rẻ hơn về tổng chi phí. So sánh cần gắn với tình huống và năng lực tổ chức.

## 6. Ví dụ xuyên suốt: ứng dụng đặt chỗ trên cloud

Giả sử đội 5 lập trình viên và 1 người phụ trách hạ tầng xây dựng ứng dụng đặt chỗ cho một thị trường ban đầu. Khách tìm chỗ, giữ chỗ, thanh toán qua đối tác và nhận xác nhận; nhân viên hỗ trợ tra cứu giao dịch. Đội phải bảo vệ thông tin cá nhân, chống đặt trùng, phục hồi sau sự cố và kiểm soát chi phí.

**Các số liệu sau chỉ minh họa**, cần thay bằng kết quả đo và yêu cầu được phê duyệt trong dự án thật. Giả sử nhu cầu đỉnh là 200 request/giây cho tra cứu; thao tác cập nhật đặt chỗ có tải thấp hơn; mục tiêu tra cứu tại API là p95 dưới 500 ms ở tải đỉnh. Chưa có bằng chứng cần triển khai độc lập từng miền nghiệp vụ.

### 6.1. Khởi đầu với modular monolith và dịch vụ được quản lý

~~~mermaid
flowchart TB
    U["Khách / Đối tác / Nhân viên hỗ trợ"] --> Edge["DNS / HTTPS / Edge tùy nhu cầu"]
    Edge --> LB["Load balancer hoặc API entrypoint"]
    subgraph Cloud["Cloud region; số vùng sẵn sàng theo SLO"]
        LB --> App["Modular monolith: Tra cứu • Đặt chỗ • Tích hợp thanh toán • Hỗ trợ"]
        App --> DB[("Managed relational database")]
        App --> O[("Object storage nếu cần")]
        App --> Q["Managed queue cho tác vụ nền"]
        Q --> W["Worker gửi thông báo / retry"]
        App -.-> Obs["Logs • Metrics • Traces • Alerts"]
        W -.-> Obs
    end
    App <--> Pay["Cổng thanh toán bên ngoài"]
    W --> Notify["Dịch vụ email / SMS"]
~~~

Phương án có ít **ranh giới triển khai** nhưng vẫn cần:

- Quản lý **xác nhận đặt chỗ** bằng giao dịch và ràng buộc dữ liệu phù hợp, tránh trùng hoặc chồng lấn; định nghĩa chính xác quy tắc theo đơn vị chỗ và khoảng thời gian.
- Tích hợp thanh toán có **khóa idempotency**, xác minh callback, timeout, retry hợp lý và đối soát. Không giả định đối tác chỉ gọi lại một lần, theo đúng thứ tự.
- Gửi email/SMS nền vì không cần hoàn tất cùng giao dịch đặt chỗ. Nếu phát sự kiện sau khi ghi database, phải xét cơ chế chống mất sự kiện, chẳng hạn **transactional outbox** khi mức tin cậy yêu cầu.
- Kiểm soát dữ liệu nhạy cảm bằng phân quyền, mã hóa, quản lý vòng đời và kiểm toán; bí mật được quản lý tập trung.
- Có giám sát, backup, kiểm thử khôi phục, chính sách trực sự cố và SLO được phê duyệt ngay từ đầu.

Sơ đồ không có nghĩa “một instance luôn đủ” hay “một region luôn đủ”. Số bản sao ứng dụng, HA của database và mục tiêu RTO/RPO phải dựa vào mức quan trọng nghiệp vụ. Ở giai đoạn đầu, modular monolith trên nền tảng compute được quản lý có thể đáp ứng mà không cần tự vận hành Kubernetes.

### 6.2. Module nội bộ giữ chi phí thay đổi thấp

~~~text
application/
  booking/             # giữ chỗ, xác nhận, hủy
  inventory/           # nguồn dữ liệu và quy tắc khả dụng
  payment-integration/ # đối tác thanh toán, đối soát
  notification/        # lập yêu cầu và trạng thái gửi
  support/             # chức năng hỗ trợ
  shared-platform/     # logging, config, auth adapter dùng chung
~~~

Nguyên tắc quan trọng hơn tên thư mục: **mỗi module có trách nhiệm nghiệp vụ rõ, API nội bộ xác định và kiểm soát chiều phụ thuộc**. Đừng để phần shared thành nơi mọi module trực tiếp sửa dữ liệu của nhau. Nếu các module chia sẻ một database trong monolith, vẫn cần quy tắc sở hữu bảng và truy cập dữ liệu. Không cần ép tương tác nội bộ qua HTTP chỉ để mô phỏng hệ thống phân tán.

### 6.3. Phương án “mở rộng tốt” nhưng đắt vận hành

Giả sử đội chia ngay thành 12 dịch vụ độc lập, mỗi dịch vụ có database, thêm service mesh, event streaming lớn, triển khai hai cloud và failover giữa hai region. Đội phải quản lý 12 vòng đời phát hành, xác thực giữa dịch vụ, hợp đồng API, nhất quán dữ liệu, chuyển đổi schema, tracing, disaster recovery và đồng bộ mạng.

Với nhu cầu minh họa hiện tại, chưa có bằng chứng lợi ích vượt chi phí. Đội nên thử tải, theo dõi bottleneck và lập kế hoạch tiến hóa dựa vào dữ liệu thật.

### 6.4. Khi nào nên tách dần?

Giả sử chức năng tìm kiếm về sau có tải và chu kỳ phát hành khác hẳn đặt chỗ. Có thể:

1. Xác định thông tin tìm kiếm nào là **bản đọc dẫn xuất**, còn giao dịch đặt chỗ dùng nguồn dữ liệu có thẩm quyền.
2. Chuẩn hóa API/module tra cứu và đo mức phụ thuộc vào phần còn lại.
3. Thử tách tìm kiếm thành dịch vụ trên phạm vi nhỏ, có cơ chế cập nhật bản đọc và giám sát độ trễ dữ liệu.
4. So sánh p95/p99, tỷ lệ lỗi, khả năng phát hành độc lập, chi phí và công sức trực vận hành trước/sau.
5. Chỉ mở rộng cách tách nếu lợi ích đủ lớn; giữ đường quay lại hoặc hợp nhất nếu giả thuyết sai.

**Tín hiệu tách dịch vụ**: một module thường xuyên làm chậm phát hành của module khác; tải/tài nguyên cần mở rộng khác biệt; ranh giới nghiệp vụ và owner ổn định; đội có khả năng giám sát và vận hành dịch vụ độc lập. “Codebase đạt 50.000 dòng” tự nó chưa đủ.

## 7. Ranh giới rõ nhưng tránh trừu tượng hóa quá mức

**Ranh giới tốt** giúp thay đổi nghiệp vụ có phạm vi nhỏ; **ranh giới sai** biến thay đổi nhỏ thành nhiều bước phối hợp. Với từng module hoặc dịch vụ, hãy ghi rõ:

1. **Trách nhiệm:** Sở hữu quy tắc và dữ liệu nào?
2. **Hợp đồng:** Lời gọi, sự kiện, dữ liệu nào được công khai?
3. **Chiều phụ thuộc:** Ai có thể gọi ai, có vòng phụ thuộc không?
4. **Chính sách lỗi:** Timeout, retry, kết quả một phần, idempotency, khôi phục ra sao?
5. **Chủ sở hữu:** Ai phát triển, bảo mật, vận hành và nâng cấp?

Trừu tượng hóa hữu ích khi bao bọc thay đổi có khả năng xảy ra hoặc loại bỏ lặp lại có ý nghĩa. Nó gây hại khi mỗi thao tác đi qua nhiều lớp interface/factory/adapter không tạo giá trị, hoặc khi đội xây dựng “framework nội bộ đa năng” trước nhu cầu. Không có quy tắc “mọi module phải có interface”; giá trị đến từ **giảm phụ thuộc và chi phí thay đổi**.

## 8. Quản lý độ phức tạp dữ liệu và luồng xử lý

Dữ liệu thường là nguyên nhân khiến việc tách hệ thống khó đảo ngược. Mỗi bản sao dữ liệu phải trả lời:

- **Nguồn sự thật:** Bản ghi nào có thẩm quyền cuối cùng?
- **Độ mới:** Chấp nhận dữ liệu chậm tối đa bao lâu cho từng chức năng?
- **Nhất quán:** Thao tác nào cần nhất quán mạnh, thao tác nào có thể nhất quán cuối cùng?
- **Khôi phục:** Nếu đồng bộ lỗi hoặc xử lý lặp, phát hiện và sửa thế nào?
- **Vòng đời:** Dữ liệu được giữ, xóa, lưu trữ và phân quyền thế nào?

Ví dụ trang tra cứu chỗ có thể dùng cache hoặc chỉ mục tìm kiếm được cập nhật trễ trong giới hạn cho phép, **nhưng bước xác nhận phải kiểm tra lại quyền đặt và trạng thái gốc**. Nếu bản đọc báo còn chỗ nhưng dữ liệu có thẩm quyền đã hết, hệ thống phải từ chối hoặc yêu cầu chọn lại.

| Cơ chế | Bài toán giải quyết | Độ phức tạp phải nhận |
| --- | --- | --- |
| Cache | Giảm tải và độ trễ đọc | Invalidation, TTL, dữ liệu cũ, cache stampede |
| Queue | Tách xử lý nền và hấp thụ đột biến | At-least-once delivery, retry, deduplication, DLQ, monitoring |
| Transactional outbox | Giảm rủi ro ghi database xong nhưng không phát được sự kiện | Bảng outbox, worker chuyển phát, xử lý trùng, dọn dữ liệu |
| Read replica | Tăng năng lực đọc và phân tải | Replication lag, định tuyến truy vấn, failover và chi phí |
| Event sourcing | Lưu chuỗi sự kiện làm dữ liệu gốc khi có nhu cầu phù hợp | Projection, replay, schema evolution, truy vấn và vận hành |
| CQRS | Tách mô hình ghi/đọc khi yêu cầu khác biệt rõ | Hai mô hình, đồng bộ dữ liệu, quan sát sự không nhất quán |

Không nên áp dụng toàn bộ các kỹ thuật trên như “bộ tiêu chuẩn”. Mỗi cơ chế chỉ hợp lý khi lợi ích cụ thể có thể mô tả, đo và kiểm soát.

## 9. Đơn giản hóa vận hành, bảo mật và hạ tầng

Sơ đồ ứng dụng đơn giản chưa đủ nếu vận hành và bảo mật đòi hỏi nhiều thao tác thủ công. Kiểm soát độ phức tạp còn là giảm số công việc lặp lại và giảm rủi ro do cấu hình lệch.

### 9.1. Chuẩn hóa quy trình vận hành

- Dùng một quy trình triển khai phổ biến, tự động hóa kiểm thử và cơ chế rollback hoặc roll-forward phù hợp.
- Quản lý tập trung cấu hình và bí mật; hạn chế ngoại lệ giữa các môi trường thiếu lý do.
- Chuẩn hóa logs, metrics, traces, correlation ID, dashboard, cảnh báo hành động được và runbook.
- Dùng *Infrastructure as Code* khi giúp tái lập môi trường, kiểm tra thay đổi và giảm cấu hình thủ công.
- Diễn tập khôi phục, kiểm tra backup và quyền truy cập; giảm bước thủ công khi phục hồi sự cố.

Quy trình lặp lại được giúp giảm phụ thuộc vào “người duy nhất biết cách vận hành”. Tuy vậy, tự động hóa không có kiểm soát cũng có thể làm lỗi lan rộng; cần review, quyền tối thiểu và phương án khắc phục.

### 9.2. Không bỏ kiểm soát an toàn để đơn giản hóa bề ngoài

Xác thực, phân quyền tối thiểu, mã hóa, bảo vệ mạng, quản lý bí mật, backup, lưu vết và kiểm toán có thể là yêu cầu bắt buộc. Đơn giản hóa là **chọn cách cung cấp năng lực bảo vệ hiệu quả hơn**: dùng định danh tập trung thay vì mỗi ứng dụng tự xử lý mật khẩu; dùng secrets manager thay vì phân phối bí mật qua cấu hình không kiểm soát.

Thêm một dịch vụ cũng tăng số danh tính máy, quyền, secret, kết nối mạng và cấu hình kiểm soát. **Bề mặt tấn công** và **chi phí kiểm toán** phải được tính trong quyết định.

### 9.3. Mở rộng và độ tin cậy dựa trên tác động nghiệp vụ

Một hệ thống ít người dùng có thể cần độ sẵn sàng rất cao vì gián đoạn gây thiệt hại lớn; một hệ thống lưu lượng cao lại có thể chấp nhận xử lý theo lô. Không thể suy từ “nhỏ” ra “không cần HA” hoặc từ “lớn” ra “phải multi-region”.

Cần thống nhất **SLO, thời gian phản hồi, RTO, RPO, phân loại tác vụ quan trọng và tác động downtime**, rồi so sánh phương án theo chi phí và khả năng vận hành. Dự phòng nhiều lớp mà không được diễn tập có thể tạo thêm điểm lỗi thay vì tăng độ tin cậy.

## 10. Đo độ phức tạp bằng khả năng thay đổi và vận hành

Không có chỉ số đơn lẻ phản ánh đầy đủ độ phức tạp. Đếm số service, database hoặc dòng code chỉ là dấu hiệu ban đầu. Cần kết hợp dữ liệu thay đổi, sự cố và chi phí thực:

| Khía cạnh | Chỉ số / tín hiệu tham khảo | Cách diễn giải |
| --- | --- | --- |
| Khả năng thay đổi | Lead time từ thay đổi được duyệt đến production; số đội hoặc repository phải phối hợp | Tăng lên dù phạm vi tính năng tương tự có thể báo hiệu phụ thuộc khó kiểm soát |
| Độ ổn định | Tỷ lệ triển khai gây sự cố, thời gian khôi phục sau lỗi | Giúp nhận ra tổn thất do ranh giới hoặc quy trình quá khó vận hành |
| Vận hành | Số cảnh báo không thể hành động, thời gian chẩn đoán, thao tác thủ công | Giảm nhiễu và thao tác thủ công có thể giảm đáng kể tải vận hành |
| Cấu trúc | Số bước đồng bộ trên critical path, số dependency, vòng phụ thuộc giữa module | Hỗ trợ phát hiện coupling và rủi ro lỗi dây chuyền |
| Dữ liệu | Nguồn dữ liệu trùng, lỗi đồng bộ, replication lag, số lần đối soát thất bại | Cho thấy chi phí thực tế của phân tán dữ liệu |
| Kinh tế | Chi phí hạ tầng cộng nhân lực vận hành; chi phí trên giao dịch thành công | Tránh giảm hóa đơn cloud nhưng tăng chi phí con người |
| Tải nhận thức | Thời gian người mới sửa lỗi/triển khai an toàn; tỷ lệ thành phần có owner và runbook | Phản ánh mức độ hệ thống có thể được hiểu và chuyển giao |

Một dashboard minh họa sau đợt hợp nhất pipeline (tất cả số liệu giả định):

| Tín hiệu | Trước cải tiến | Sau cải tiến | Điều cần xác minh |
| --- | --- | --- | --- |
| Số bước triển khai/phê duyệt cho thay đổi nhỏ | 7 | 3 | Đã giảm bàn giao và vẫn giữ kiểm soát bắt buộc? |
| Thời gian khôi phục trung vị ở nhóm sự cố tương đương | 90 phút | 35 phút | Cỡ mẫu có đủ, độ nghiêm trọng các ca có tương tự? |
| Số pipeline phải sửa khi đổi hợp đồng nội bộ | 5 | 1 | Phụ thuộc giữa các nhóm có thực sự giảm? |
| Chi phí vận hành trên một giao dịch thành công | Chưa có đường cơ sở | Đang đo | Chưa thể kết luận hiệu quả kinh tế từ những số trên |

Việc cải thiện một vài chỉ số không chứng minh toàn hệ thống tốt hơn. Phải xem đồng thời SLO, rủi ro bảo mật, tỷ lệ lỗi và tải để tránh tối ưu cục bộ. Ví dụ giảm số lần triển khai có thể làm tỷ lệ thất bại thấp đi nhưng lại khiến phát hành tính năng chậm hơn; cần nhìn vào bối cảnh và xu hướng.

## 11. Thiết lập ngân sách độ phức tạp (*complexity budget*)

Ngân sách độ phức tạp là **quy tắc quản trị nội bộ**, không phải con số chuẩn của ngành. Đội xác định bao nhiêu loại công nghệ, mô hình triển khai và quan hệ phụ thuộc mình đủ năng lực vận hành; ngoại lệ phải có bằng chứng, người sở hữu và điều kiện xem lại.

Một ví dụ chính sách:

- **Mặc định** dùng runtime, database, observability và pipeline đã được đội platform hỗ trợ.
- **Dịch vụ mới** cần miền nghiệp vụ độc lập, lý do triển khai/scale riêng và kế hoạch SLO, bảo mật, dữ liệu, on-call.
- **Hệ thống lưu trữ mới** cần nêu truy vấn hoặc yêu cầu mà hệ hiện tại không đáp ứng hợp lý, kèm backup, migration và quyền truy cập.
- **Đa vùng hoặc đa cloud** cần phân tích tác động rủi ro, tiêu chí failover, diễn tập và chi phí duy trì.
- **Thành phần tạm thời** cần người sở hữu, ngày xem lại và tiêu chí loại bỏ hoặc chuyển thành chính thức.

Có thể dùng thang điểm để hỗ trợ thảo luận nhưng **không biến điểm số thành thuật toán tự động quyết định**:

| Tiêu chí | Cách xem xét | Chiều ưu tiên |
| --- | --- | --- |
| Đáp ứng yêu cầu bắt buộc | Có đáp ứng SLO, bảo mật, dữ liệu, phục hồi và nghĩa vụ áp dụng không? | **Điều kiện loại trừ**: không đạt thì không chọn |
| Chi phí triển khai | Thời gian xây dựng, chuyển đổi, kiểm thử, đào tạo | Thấp hơn khi lợi ích tương đương |
| Chi phí vận hành | On-call, backup, incident, nâng cấp, nhà cung cấp | Thấp hơn khi lợi ích tương đương |
| Tải nhận thức, phụ thuộc | Số thành phần phải hiểu, đổi cùng lúc và cách điều tra lỗi | Thấp hơn khi lợi ích tương đương |
| Khả năng mở rộng tương lai | Chi phí, tốc độ, rủi ro khi tăng tải hoặc thêm miền nghiệp vụ | Đủ cho kịch bản tăng trưởng có bằng chứng |
| Khả năng đảo ngược | Có thể quay lại, di chuyển dữ liệu, hợp nhất hay thay nhà cung cấp? | Dễ đảo ngược hơn khi chưa chắc chắn |

Phải đánh giá **tổng chi phí sở hữu** theo khoảng thời gian hợp lý, ví dụ 12–24 tháng, thay vì chỉ hóa đơn cloud theo tháng. Nếu kết quả còn phụ thuộc giả định lớn, ưu tiên một phép thử kỹ thuật (*spike* hoặc *proof of concept*) để giảm bất định trước khi cam kết.

## 12. ADR và nợ kiến trúc

**Architecture Decision Record (ADR)** là bản ghi ngắn giải thích tại sao một phương án được chọn trong bối cảnh cụ thể. ADR giảm tranh luận lặp lại và giúp người mới hiểu đâu là quyết định tạm thời, đâu là ràng buộc lâu dài.

Ví dụ ADR:

~~~markdown
# ADR-007: Modular monolith cho pha 1

## Bối cảnh
Đội nhỏ, một thị trường; đặt chỗ cần tính nhất quán.
Chưa có bằng chứng cần triển khai độc lập các miền nghiệp vụ.

## Yêu cầu bắt buộc
Không được xác nhận đặt trùng; có kiểm soát truy cập, quan sát,
backup và phục hồi theo các mục tiêu đã phê duyệt.

## Các phương án
1. Modular monolith trên nền tảng compute được quản lý.
2. Microservices theo miền nghiệp vụ.

## Quyết định
Chọn phương án 1, đặt ranh giới module rõ và chuẩn hóa quan sát.

## Đánh đổi
Giảm chi phí mạng/vận hành nhưng chưa scale, deploy độc lập module.

## Điều kiện xem lại
Một module cần scale/triển khai riêng với bằng chứng đo được;
hoặc thời gian phát hành tăng vì phụ thuộc giữa các module.

## Chủ sở hữu và ngày xem lại
Tech Lead; xem lại sau 3 tháng hoặc khi có tín hiệu bất thường.
~~~

Khi phát hiện **nợ kiến trúc**, ghi nó thành hạng mục có tác động cụ thể:

| Nội dung | Ví dụ |
| --- | --- |
| Nợ | Hai quy trình đăng nhập tồn tại cùng lúc |
| Tác động | Tăng nguy cơ cấu hình lệch và khó kiểm toán truy cập |
| Bằng chứng | Sự cố quyền truy cập hoặc thời gian thay đổi quyền kéo dài |
| Giải pháp | Chuyển sang cơ chế định danh chuẩn, kiểm thử phân quyền |
| Chủ sở hữu | Platform và đội ứng dụng liên quan |
| Điều kiện xóa | Không còn caller sử dụng cơ chế cũ; log xác nhận |

Không nhất thiết sửa mọi khoản nợ ngay. Ưu tiên theo tác động nghiệp vụ, tần suất thay đổi, rủi ro sự cố và chi phí tiếp tục giữ lại. Nợ không có owner hoặc điều kiện xóa dễ trở thành kiến trúc tồn tại mãi.

## 13. Quy trình đơn giản hóa có kiểm soát

Để tránh một đợt “đại phẫu” rủi ro cao, hãy thay đổi theo lát cắt nhỏ:

1. **Khoanh vùng:** Chọn luồng có sự cố, thời gian thay đổi hoặc chi phí cao; ghi đường cơ sở.
2. **Lập bản đồ:** Liệt kê request path, dependency, dữ liệu, quyền truy cập, pipeline và owner.
3. **Tìm phần dư:** Công cụ trùng chức năng, lớp trung gian không tạo giá trị, thao tác thủ công, trạng thái nhân bản.
4. **Xác định phần phải giữ:** SLO, dữ liệu, bảo mật, kiểm toán, RTO/RPO, hợp đồng tích hợp và nghĩa vụ áp dụng.
5. **Đề xuất thay đổi nhỏ:** Hợp nhất module, bỏ tầng gọi không cần thiết, chuẩn hóa deployment, giảm số loại database.
6. **Kiểm tra:** Chạy kiểm thử nghiệp vụ, tải, lỗi và bảo mật phù hợp; so sánh thời gian thay đổi, lỗi, chi phí và khả năng vận hành.
7. **Loại bỏ đường cũ:** Xóa cấu hình, secret, quyền, pipeline và thành phần hết dùng sau khi xác minh không còn phụ thuộc; cập nhật runbook và ADR.

**Với dữ liệu**, không xóa hay hợp nhất nguồn lưu trữ khi chưa có kế hoạch migration, đối soát, backup, rollback và xác nhận của người sở hữu. Kiến trúc đơn giản lâu dài phải đi cùng chuyển đổi an toàn.

## 14. Đánh giá theo Well-Architected

Đơn giản hóa cần cân bằng nhiều chiều, không tối ưu riêng số dịch vụ:

| Góc nhìn | Lợi ích đơn giản hóa có thể mang lại | Không được đánh đổi vô thức |
| --- | --- | --- |
| **Operational Excellence / Vận hành** | Ít quy trình tùy biến; runbook và pipeline nhất quán | Quan sát, ứng phó sự cố, cải tiến liên tục |
| **Security / Bảo mật** | Ít bề mặt tấn công, quyền và secret cần quản lý | Quyền tối thiểu, kiểm toán, bảo vệ dữ liệu, mã hóa |
| **Reliability / Độ tin cậy** | Giảm dependency chain và nguồn lỗi phân tán | Backup, khôi phục, chịu lỗi theo mục tiêu |
| **Performance Efficiency / Hiệu quả hiệu năng** | Đường gọi ngắn hơn, ít network hop | Độ trễ, throughput, mở rộng thực tế |
| **Cost Optimization / Tối ưu chi phí** | Ít công cụ trùng lặp, giảm sức vận hành | Dự phòng và chất lượng cần thiết |
| **Sustainability / Bền vững** | Giảm tài nguyên nhàn rỗi và xử lý trùng lặp | Mức phục vụ và hiệu quả đo được |

Các góc nhìn này nhắc đội đánh giá liên tục. “Ít service hơn” không luôn tốt: nếu hợp nhất mọi chức năng khiến một lỗi nhỏ làm sập toàn ứng dụng hoặc không thể phát hành an toàn, chi phí vận hành thực tế có thể tăng. Quyết định phải dựa vào kịch bản lỗi, năng lực phục hồi và đội chịu trách nhiệm.

## 15. Sai lầm thường gặp

| Sai lầm | Vì sao gây vấn đề | Cách khắc phục |
| --- | --- | --- |
| “Dùng microservices từ ngày đầu để sau khỏi sửa” | Trả trước chi phí phân tán khi nhu cầu chưa xác thực | Module hóa nghiệp vụ, đo nhu cầu tách, giữ đường tiến hóa |
| “Đơn giản thì không cần backup/observability” | Giảm số hộp nhưng tăng nguy cơ mất dữ liệu và chậm phát hiện lỗi | Giữ kiểm soát theo mức quan trọng của hệ thống |
| “Bất đồng bộ luôn scale tốt hơn” | Thêm thứ tự, retry, xử lý trùng, nhất quán cuối cùng | Chỉ xử lý nền khi tác vụ và SLO cho phép |
| “Managed service không cần vận hành” | Vẫn phải cấu hình, phân quyền, giám sát, backup và quản lý giới hạn | Phân công trách nhiệm, diễn tập tình huống lỗi |
| “Ít hộp trên sơ đồ nghĩa là đơn giản” | Monolith vẫn có thể phụ thuộc vòng và không có ranh giới | Đo mức khó thay đổi, coupling và trách nhiệm |
| “Đa cloud mặc định tăng độ tin cậy” | Mở thêm đường lỗi, điểm đồng bộ và khác biệt vận hành | Phân tích kịch bản thảm họa, hợp đồng và mục tiêu trước |
| “Giữ cả đường cũ để an toàn” | Hai cơ chế cùng sống gây lỗi lệch và nghĩa vụ duy trì kéo dài | Định nghĩa điều kiện chuyển đổi và xóa đường cũ |
| “Cắt giảm hóa đơn cloud bằng mọi giá” | Có thể tăng downtime, nhân công và rủi ro | Đo tổng chi phí cùng SLO và rủi ro |
| “Quyết định kiến trúc là vĩnh viễn” | Giữ thiết kế không còn hợp bối cảnh | Ghi ADR với trigger xem lại và owner |

## 16. Bài thực hành: chọn kiến trúc tối thiểu có khả năng tiến hóa

Một đội có 6 kỹ sư phát triển nền tảng quản lý đơn hàng. Hệ thống có chức năng tạo đơn, thanh toán qua đối tác, quản lý tồn kho, gửi email và báo cáo. Trong 12 tháng tới, doanh nghiệp kỳ vọng lượng truy cập tăng nhưng chưa có số liệu đường cơ sở. Bộ phận kinh doanh đề xuất “Kubernetes, 15 microservices, 4 database và đa cloud để chắc chắn mở rộng”.

**Yêu cầu thực hành:**

1. Liệt kê ít nhất **5 thông tin còn thiếu** cần xác nhận với nghiệp vụ, vận hành và bảo mật.
2. Vẽ **sơ đồ ngữ cảnh và deployment khái niệm** cho pha 1, nêu trách nhiệm dữ liệu và tích hợp bên ngoài.
3. Đề xuất module để bảo đảm tạo đơn và cập nhật tồn kho đúng; chọn **2 luồng có thể xử lý nền**.
4. So sánh modular monolith và microservices theo **hiệu năng, dữ liệu, vận hành, bảo mật, chi phí và mở rộng**.
5. Viết **một ADR** và xác định **3 tín hiệu đo được** khiến cần xem lại quyết định.
6. Xây dựng kế hoạch đo trước/sau: thời gian thay đổi tính năng, p95 API, tỷ lệ lỗi, chi phí trên đơn thành công và thời gian phục hồi sự cố.

### Gợi ý đánh giá

Phương án đạt yêu cầu khi **không phớt lờ ràng buộc bắt buộc**, giải thích được từng thành phần bằng nhu cầu cụ thể, xác định rõ nguồn dữ liệu gốc, có owner và cách xử lý lỗi, đồng thời có tiêu chí mở rộng/tách thành phần sau khi đo thực tế.

Nếu chưa có yêu cầu triển khai độc lập và các thao tác đơn hàng/tồn kho cần nhất quán, modular monolith với cơ sở dữ liệu quan hệ quản lý có thể là **ứng viên hợp lý**. Email, báo cáo hoặc đồng bộ phân tích có thể là **ứng viên xử lý nền**, với cơ chế xử lý trùng và khôi phục khi lỗi. Đây là điểm xuất phát để xác minh, không phải lựa chọn bắt buộc cho mọi hệ thống.

## 17. Checklist trước khi thêm một thành phần cloud

- [ ] Có **yêu cầu nghiệp vụ/NFR**, chủ sở hữu và bằng chứng cho vấn đề cần giải quyết.
- [ ] Đã cân nhắc cải tiến phương án hiện tại; nếu không áp dụng, có lý do rõ ràng.
- [ ] Có **tiêu chí thành công** và phương pháp đo trước/sau.
- [ ] Đã tính chi phí hạ tầng **và** phát triển, bảo mật, nâng cấp, on-call, backup, khôi phục.
- [ ] Đã mô tả ranh giới dữ liệu, quyền truy cập, hành vi lỗi, timeout/retry, khả năng quan sát.
- [ ] Có đội chịu trách nhiệm triển khai, vận hành, hỗ trợ và quyết định khi sự cố xảy ra.
- [ ] Có ADR ghi phương án, đánh đổi, điều kiện xem lại và đường thoát khỏi lựa chọn.
- [ ] Có kế hoạch xóa thành phần cũ hoặc thí nghiệm khi không còn giá trị.

**Ghi nhớ:** Độ phức tạp là một chi phí kiến trúc tác động đến mọi quyết định về mạng, compute, dữ liệu, triển khai và vận hành. Hãy đầu tư vào **ranh giới nghiệp vụ rõ, quy trình nhất quán, yêu cầu đo được và khả năng thay đổi**. Bắt đầu bằng kiến trúc ít thành phần nhất có thể đáp ứng mọi ràng buộc bắt buộc, rồi bổ sung độ phức tạp khi lợi ích được chứng minh và các đánh đổi được chấp nhận.
