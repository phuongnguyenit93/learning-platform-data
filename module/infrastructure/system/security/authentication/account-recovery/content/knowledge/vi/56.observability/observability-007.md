# Observability data privacy — Quyền riêng tư của dữ liệu quan sát trong khôi phục tài khoản

## 1. Vì sao telemetry của khôi phục tài khoản đặc biệt nhạy cảm?

**Observability data privacy** là việc giới hạn dữ liệu được thu thập, truyền, sử dụng, chia sẻ và lưu giữ trong hệ thống quan sát sao cho phục vụ đúng mục đích vận hành, đồng thời giảm khả năng tiết lộ bí mật hoặc suy ra thông tin riêng tư của người dùng.

Trong khôi phục tài khoản, dữ liệu đi qua nhiều bước nhạy cảm: nhập định danh, kiểm tra token dùng một lần, xác minh danh tính, xem xét rủi ro, thay MFA, đăng ký passkey mới và kiểm soát session. Một cấu hình tự ghi HTTP body hoặc URL đầy đủ có thể đưa chính bằng chứng khôi phục vào hệ thống logs hay traces.

Khi đó, người chỉ cần xem lỗi vận hành có thể vô tình nhận được khả năng tiếp tục một giao dịch khôi phục hoặc thấy hồ sơ xác minh mà họ không có nhiệm vụ xử lý.

Quyền riêng tư không chỉ là che mật khẩu:

| Nhóm dữ liệu | Ví dụ trong luồng khôi phục | Nguy cơ khi đưa vào telemetry |
| --- | --- | --- |
| Bí mật có thể cấp quyền | Recovery token, OTP, cookie, mã dự phòng | Có thể hỗ trợ chiếm quyền hoặc vượt một bước xác minh |
| Dữ liệu định danh | Email, số điện thoại, giấy tờ | Tiết lộ hoặc liên kết danh tính |
| Bằng chứng xác minh | Ảnh, hồ sơ, nội dung trả lời | Tạo thêm bản sao dữ liệu rất nhạy cảm |
| Metadata hành vi | Thời điểm yêu cầu, thiết bị, vị trí mạng | Suy ra hoạt động hoặc mối liên hệ |
| Dữ liệu quyết định | Lý do nội bộ, điểm rủi ro, nhánh xem xét | Tiết lộ trạng thái tài khoản hoặc cơ chế bảo vệ |
| Dữ liệu liên kết | Request ID, trace ID, account reference | Nối các tập dữ liệu vốn được tách biệt |

Một định danh ngẫu nhiên không phải mật khẩu nhưng vẫn có thể là dữ liệu liên kết cần được bảo vệ. Một metric tổng hợp cũng có thể tiết lộ hoạt động nếu được lọc tới một nhóm rất ít người.

## 2. Thu thập theo mục đích, không theo khả năng của công cụ

Câu hỏi đầu tiên nên là: cần dữ liệu nào để giải thích một vấn đề cụ thể?

Ví dụ, để biết dịch vụ kiểm tra challenge đang bị timeout, có thể chỉ cần operation, nhóm kết quả, thời gian xử lý và phiên bản triển khai. Không cần biết OTP người dùng đã nhập hoặc email đầy đủ của họ.

[OpenTelemetry — Handling sensitive data](https://opentelemetry.io/docs/security/handling-sensitive-data/) nhấn mạnh giảm dữ liệu tại nguồn và trách nhiệm hiểu dữ liệu do instrumentation phát ra. Công cụ không tự biết mọi thông tin nhạy cảm trong ngữ cảnh riêng của ứng dụng.

Một hợp đồng thu thập nên xác định:

- Mục đích vận hành hoặc điều tra.
- Tín hiệu nào nhận trường dữ liệu: metric, log, span hay audit.
- Dữ liệu đến từ nguồn nào và mức tin cậy ra sao.
- Ai được xem, xuất hoặc liên kết dữ liệu.
- Thời hạn và nơi lưu.
- Cách xử lý khi trường mới hoặc định dạng chưa được phép xuất hiện.

Không dùng “có thể hữu ích sau này” làm lý do serialize nguyên request. Một trường giúp điều tra gian lận không mặc nhiên phải có trong mọi trace hoặc dashboard của đội vận hành.

Cũng cần phân biệt telemetry và kho bằng chứng. Hồ sơ xác minh có thể phải được xử lý trong một hệ thống chuyên biệt có quyền truy cập riêng; việc đó không tạo lý do sao chép hồ sơ sang logs.

## 3. Lập bản đồ đường đi và những bản sao dễ bị quên

Dữ liệu có thể rò trước khi tới collector mà nhóm vận hành thường xem là nơi xử lý riêng tư.

Một request có thể đi qua:

1. Trình duyệt, ứng dụng di động hoặc SDK phía client.
2. CDN, reverse proxy, gateway và access log.
3. Framework HTTP, middleware và agent tự động instrument.
4. Recovery Service cùng các worker.
5. Buffer, spool trên đĩa, broker và hàng đợi lỗi.
6. Collector, exporter và backend observability.
7. Dashboard, cảnh báo, báo cáo, file export và bản sao lưu.

Chỉ che một trường trên giao diện dashboard không xóa trường đó khỏi raw storage, chỉ mục, cache hoặc thông điệp cảnh báo đã gửi.

Những vị trí đặc biệt cần được xem xét trong thiết kế:

- URL có token trong query string hoặc đoạn đường dẫn.
- Exception message có đầu vào gốc.
- Span event được agent tạo khi bắt lỗi.
- HTTP client log ghi nguyên header hoặc response của nhà cung cấp.
- SQL statement có literal hoặc tham số nhạy cảm.
- Payload nguyên gốc trong dead-letter queue.
- Collector debug log in lại dữ liệu bị từ chối.
- Heap dump, crash report hoặc bản ghi hỗ trợ chứa bộ nhớ tiến trình.

Một lớp redaction ở cuối pipeline không bảo vệ được bản sao đã được phát tới một exporter khác từ trước.

## 4. Phân loại dữ liệu và chọn cách xử lý

Có thể dùng bảng chính sách minh họa sau để bắt đầu:

| Dữ liệu | Hướng xử lý mặc định trong telemetry thông thường |
| --- | --- |
| Mật khẩu, OTP, recovery token, mã dự phòng | Không thu thập |
| Authorization header, cookie, khóa riêng, secret của MFA | Không thu thập |
| Giấy tờ, ảnh xác minh, câu trả lời chứng minh danh tính | Không đưa vào telemetry; giữ ở kho chuyên biệt nếu có mục đích hợp lệ |
| Email và số điện thoại | Tránh thu; chỉ dùng biểu diễn tối thiểu khi có nhu cầu đã xác định |
| IP và dữ liệu thiết bị | Chỉ thu ở phạm vi có mục đích, độ chi tiết và thời hạn rõ |
| Nội dung lỗi tự do | Chuyển thành mã lỗi hoặc nhóm lỗi được kiểm soát |
| Route, operation, outcome hữu hạn, thời gian xử lý | Có thể phù hợp nếu đã kiểm tra nội dung và phạm vi truy cập |
| Tham chiếu giao dịch nội bộ | Chỉ ở tín hiệu cần liên kết, với quyền và thời hạn phù hợp |

[OWASP Logging Cheat Sheet — Data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude) đề cập việc loại trừ hoặc xử lý đặc biệt các bí mật, token, dữ liệu session và thông tin cá nhân. Trong luồng khôi phục, mặc định không thu bí mật thường giảm rủi ro tốt hơn việc thu rồi cố che.

Không đưa token vào log dưới dạng hash để “vẫn tìm được khi cần” mà không có mục đích và đánh giá riêng. Với OTP hoặc mã ít khả năng, hash có thể bị đối chiếu bằng cách thử toàn bộ không gian giá trị. Với token có entropy cao, bản hash vẫn là một trường liên kết bổ sung; nếu không cần thì không thu.

Một địa chỉ email đã che một phần vẫn có thể nhận dạng trong một tổ chức nhỏ. Bỏ octet cuối của IP hoặc chỉ giữ email domain cũng không tự tạo ra dữ liệu ẩn danh trong mọi bối cảnh.

## 5. Hợp đồng cho từng tín hiệu quan sát

### 5.1. Metrics: chỉ giữ chiều tổng hợp cần thiết

Labels nên là tập giá trị hữu hạn như operation, nhóm outcome hoặc channel. Không dùng account ID, email, request ID, token, trace ID hay URL đầy đủ làm label.

Hash account ID không làm giảm cardinality. Nó vẫn tạo một series hoặc nhóm series cho từng giá trị và cho phép theo dõi cùng một đối tượng.

Ví dụ:

~~~text
Phù hợp với một metric tổng hợp:
  operation = challenge_verify
  result = timeout
  channel = email

Không phù hợp làm label:
  email = địa chỉ người dùng
  request_id = định danh riêng của mỗi request
  token_hash = giá trị riêng của mỗi token
~~~

Không cần thu một label chỉ vì framework có thể tự thêm. Cấu hình chuyển baggage thành metric attributes cũng phải chịu cùng hợp đồng nhãn.

### 5.2. Logs: sự kiện có cấu trúc thay cho dữ liệu đầu vào

Một log có thể mô tả sự kiện bằng mã ổn định, nhóm lỗi và tham chiếu hỗ trợ nội bộ cần thiết. Không nối nguyên HTTP body hoặc exception message vào message.

Nội dung có cấu trúc vẫn cần được kiểm tra. Một JSON field tên metadata không cho phép chứa mọi thứ.

### 5.3. Traces: đo luồng xử lý mà không sao chép bằng chứng

Span name nên mô tả thao tác hoặc route mẫu, chẳng hạn verify recovery challenge. Không đặt email hoặc token vào tên span.

Attributes và span events cần có allowlist riêng. Việc không lưu request body ở application log chưa đủ nếu agent vẫn đưa body hoặc thông điệp lỗi chứa dữ liệu đó vào span.

Trace được lấy mẫu vẫn là dữ liệu đã được thu thập. Sampling giảm số lượng, không biến thông tin bí mật thành an toàn.

### 5.4. Audit: giữ ngữ nghĩa và quyền riêng biệt

Audit có thể cần actor và đối tượng để giải thích một thay đổi nhạy cảm. Điều đó không có nghĩa các định danh ấy phải được sao chép sang metrics và traces.

Nếu một lớp telemetry loại bỏ trường không được phép, cần tránh làm mất âm thầm sự kiện audit bắt buộc. Hợp đồng audit phải được thiết kế tối thiểu và đúng ngay tại nguồn; không đẩy một payload tùy ý qua bộ lọc rồi hy vọng phần còn lại đủ giá trị chứng cứ.

## 6. Allowlist và sự kiện đã được làm sạch tại nguồn

Cách tiếp cận dễ kiểm soát là xây một object dành riêng cho telemetry từ các trường được phép, thay vì sao chép object nghiệp vụ rồi xóa vài field đã biết.

Mã giả:

~~~text
safeEvent = {
  eventName: RECOVERY_CHALLENGE_EVALUATED,
  operation: mapAllowedOperation(operation),
  outcome: mapAllowedOutcome(decision),
  reasonGroup: mapAllowedReason(reason),
  durationMs: measuredDuration,
  deployment: trustedDeploymentMetadata
}

emitStructuredTelemetry(safeEvent)
~~~

Các hàm ánh xạ chỉ trả về giá trị trong danh mục đã định nghĩa. Giá trị lạ được biểu diễn bằng một nhóm an toàn hoặc bị từ chối theo hợp đồng, không rơi về nguyên chuỗi client đã gửi.

Ví dụ một sự kiện vận hành sau xử lý:

~~~json
{
  "eventName": "RECOVERY_CHALLENGE_EVALUATED",
  "operation": "challenge_verify",
  "outcome": "DENIED",
  "reasonGroup": "PROOF_NOT_ACCEPTED",
  "durationMs": 38,
  "deployment": "recovery-release-17"
}
~~~

Sự kiện này không tự nói ai là người yêu cầu hoặc token nào đã bị thử. Nếu điều tra cần liên kết tới giao dịch, có thể có một trường tham chiếu nội bộ được kiểm soát riêng, không dùng chung trên mọi tín hiệu.

Allowlist cần áp dụng cho cả cấu trúc lồng nhau và giới hạn độ dài. Nếu cho phép một message tự do dài không giới hạn, phần lớn lợi ích của allowlist có thể bị mất.

Regex dò email hoặc token là một lớp hỗ trợ, không phải ranh giới duy nhất. Nó có thể bỏ sót dữ liệu được mã hóa, chia nhỏ hoặc có định dạng mới, và có thể che nhầm dữ liệu không nhạy cảm.

## 7. Liên kết dữ liệu mà không dùng bí mật làm khóa

Điều tra thường cần nối một lỗi ở API với một job chuyển phát hoặc một sự kiện nghiệp vụ. Không dùng recovery token, cookie hoặc OTP làm correlation ID.

Có thể tạo tham chiếu opaque dành cho quan sát, với những đặc điểm:

- Không cấp quyền thực hiện tác vụ.
- Không được suy ra từ bí mật của người dùng.
- Chỉ có phạm vi liên kết cần thiết.
- Có vòng đời và quyền truy cập rõ.
- Không được dùng làm căn cứ xác thực actor hoặc tenant.

Nếu cần ánh xạ tham chiếu đó tới account hoặc request, bảng ánh xạ cần được kiểm soát riêng. Có tham chiếu trong log không đồng nghĩa mọi người đọc log được quyền mở hồ sơ tài khoản.

Tham chiếu được server tạo vẫn có thể là dữ liệu giả danh, vì người có quyền đối chiếu có thể nhận dạng chủ thể. Không gọi nó là ẩn danh chỉ vì nhìn không giống email.

Với một số nhu cầu đối soát, HMAC theo mục đích và phạm vi có thể hạn chế việc đoán trực tiếp so với hash thuần của dữ liệu dễ đoán. Nhưng nó vẫn tạo khả năng liên kết trong phạm vi dùng cùng khóa, phụ thuộc vào bảo vệ khóa và không tự chứng minh danh tính. Không dùng một khóa và cùng một giá trị giả danh cho mọi mục đích nếu không cần liên kết xuyên hệ thống.

Khi đổi khóa hoặc phạm vi liên kết, cần tính đến dữ liệu cũ và yêu cầu điều tra. Không lưu thêm dữ liệu gốc ở nơi khác chỉ để việc xoay khóa thuận tiện hơn.

Nếu cung cấp một mã hỗ trợ cho người dùng tại endpoint công khai, mã đó không được tự mở quyền xem trace nội bộ hay tiết lộ tài khoản có tồn tại. Quyền truy vấn luôn phải kiểm tra độc lập.

## 8. Tự động instrumentation và baggage cần ranh giới rõ

Agent tự động có thể tạo telemetry trước khi code nghiệp vụ gọi hàm log an toàn. Vì vậy cần hiểu các cấu hình thu URL, header, tham số, body và exception ở những lớp đang dùng.

Đối với endpoint có token trong URL, một lựa chọn là chỉ ghi route mẫu và các thuộc tính an toàn. Xóa riêng query string chưa đủ nếu token nằm trong path. Ngược lại, route mẫu không giúp được nếu message lỗi vẫn chứa URL đầy đủ.

Không cho phép một tùy chọn debug bật thu nguyên body của endpoint xác minh chỉ để điều tra nhanh. Có thể tăng độ chi tiết bằng mã giai đoạn, nhóm lỗi, thời gian xử lý và dấu hiệu nội bộ đã được định nghĩa.

Baggage là ngữ cảnh có thể lan qua các dịch vụ. [OpenTelemetry — Baggage security considerations](https://opentelemetry.io/docs/concepts/signals/baggage/#baggage-security-considerations) lưu ý rằng baggage nhạy cảm có thể được truyền tới bên nhận ngoài dự kiến và không có sẵn bảo đảm rằng các giá trị là do hệ thống tin cậy tạo.

Vì vậy:

- Không đặt token, OTP, email hoặc hồ sơ xác minh vào baggage.
- Không coi actor, account hoặc tenant trong baggage nhận từ client là bằng chứng quyền.
- Chỉ truyền các trường được cho phép qua ranh giới dịch vụ.
- Kiểm soát propagation khi gọi nhà cung cấp bên ngoài.
- Không tự chuyển toàn bộ baggage thành attributes của mọi span hoặc metric.

Trace context cũng không phải cơ chế xác thực. Kết nối hai span theo trace ID không cho phép bỏ kiểm tra quyền ở dịch vụ phía sau.

Cần áp dụng chính sách cho request đi ra và callback đi vào, không chỉ request từ trình duyệt vào Recovery Service.

## 9. Pipeline xử lý riêng tư theo nhiều lớp

Một kiến trúc minh họa:

~~~mermaid
flowchart LR
    A[Sự kiện nghiệp vụ] --> B[Tạo telemetry tối thiểu tại nguồn]
    B --> C[SDK và instrumentation được cấu hình]
    C --> D[Collector với hợp đồng thuộc tính]
    D --> E[Backend theo phạm vi dữ liệu]
    E --> F[Dashboard và truy vấn có kiểm soát quyền]
    E --> G[Export theo mục đích đã xác định]
    H[Kho hồ sơ xác minh riêng] -. Tham chiếu có kiểm soát .-> A
~~~

Mỗi lớp có vai trò khác nhau:

1. **Tại nguồn:** không đưa bí mật vào object telemetry.
2. **Instrumentation:** tắt những cơ chế tự thu vượt nhu cầu.
3. **Collector:** áp dụng giới hạn và chính sách bổ sung trước khi chuyển tiếp.
4. **Backend:** kiểm soát truy cập, lưu giữ, index và xuất dữ liệu.
5. **Đầu ra:** giảm thông tin trong dashboard, cảnh báo và file chia sẻ.

Bộ lọc collector không nên có một nhánh exporter khác gửi raw payload trước khi làm sạch. Queue và buffer ở trước bộ lọc cũng phải được tính là nơi có thể giữ dữ liệu nhạy cảm nếu dữ liệu đã đi tới đó.

Khi bộ xử lý không hiểu một field mới, không tự cho field đó đi qua chỉ để “không mất thông tin”. Có thể loại thuộc tính không bắt buộc hoặc đưa vào quy trình xử lý có giới hạn theo hợp đồng. Không ghi nguyên payload bị từ chối vào error log của chính collector.

Với sự kiện audit bắt buộc, cần cơ chế riêng để phát hiện hợp đồng không hợp lệ và xử lý việc lưu bền vững. Không áp dụng một quyết định drop telemetry chung rồi tuyên bố mọi audit vẫn đầy đủ.

Mã hóa khi truyền và khi lưu giảm một số nguy cơ truy cập trái phép, nhưng người có quyền đọc backend vẫn có thể thấy nội dung. Mã hóa không thay thế được việc giảm dữ liệu và giới hạn quyền.

## 10. Quyền truy cập phải theo nhiệm vụ và phạm vi

Không phải ai cần xem độ trễ đều cần xem định danh của người khôi phục.

Có thể tách các lớp truy cập:

| Nhóm công việc | Dữ liệu thường cần |
| --- | --- |
| Vận hành độ tin cậy | Metrics tổng hợp, nhóm lỗi, trạng thái phụ thuộc |
| Phân tích lỗi ứng dụng | Trace đã giảm dữ liệu và log kỹ thuật phù hợp |
| Hỗ trợ một giao dịch | Thông tin liên quan đến case được giao và quyền tương ứng |
| Điều tra bảo mật | Audit, dữ liệu liên kết và tín hiệu có thẩm quyền |
| Quản trị lưu trữ | Quyền quản lý hạ tầng không mặc nhiên là nhu cầu đọc mọi hồ sơ |

Đây là cách phân chia minh họa. Quyền thực tế cần kiểm tra theo tài khoản, tenant và nhiệm vụ, không chỉ theo tên vai trò chung.

Ở hệ thống nhiều tenant, không chỉ thêm bộ lọc tenant trên dashboard. Backend query, API, đường export và các định danh dùng để mở chi tiết phải duy trì cùng ranh giới. Bộ lọc do người dùng tự sửa không phải cơ chế cách ly.

Các hành động nhạy cảm như mở dữ liệu định danh, xuất lượng lớn hoặc thay đổi chính sách thu thập cần có dấu vết phù hợp. Luồng ghi nhận việc truy cập telemetry cũng phải tránh tự gọi đệ quy vô hạn và không sao chép lại nội dung đang được bảo vệ.

Một URL dashboard hoặc trace được chia sẻ không nên trở thành bearer capability vô thời hạn. Người mở vẫn cần quyền phù hợp; bản cache, ảnh chụp và export cũng có thể là bản sao dữ liệu cần quản lý.

Không mặc định chuyển log đầy đủ vào ticket, email cảnh báo hoặc công cụ chat. Mỗi đích là một phạm vi người đọc và lưu giữ khác.

## 11. Thời hạn lưu giữ và xóa phải bao phủ các bản sao

Mỗi loại dữ liệu nên có thời hạn dựa trên mục đích:

- Metrics tổng hợp có thể có vòng đời khác trace chi tiết.
- Log kỹ thuật có thể khác audit của tác vụ nhạy cảm.
- Bảng ánh xạ tham chiếu tới tài khoản có thể cần thời hạn riêng.
- Dữ liệu debug tạm thời không nên được lưu như dữ liệu vận hành mặc định.

Không cần một con số chung cho tất cả hệ thống. Điều quan trọng là xác định được lý do giữ và cơ chế thực thi cho từng nhóm.

Khi dữ liệu được giảm độ phân giải, không mặc định rằng phần còn lại đã ẩn danh. Một chuỗi tổng hợp với nhãn rất cụ thể vẫn có thể liên kết đến người dùng hoặc sự kiện nhạy cảm.

Vòng đời cần tính tới:

- Raw storage và bản sao dự phòng.
- Chỉ mục tìm kiếm, materialized view và cache.
- Hàng đợi, spool và vùng tạm của exporter.
- File export, báo cáo và dữ liệu được chuyển cho nhà cung cấp.
- Bảng ánh xạ định danh và bản sao dùng để đối soát.

Nếu có yêu cầu loại bỏ dữ liệu theo chính sách, cần xác định dữ liệu nào còn khả năng liên kết và ở đâu. Không chỉ xóa một document trong index rồi coi mọi bản sao đã biến mất.

Đối với backup chưa thể sửa từng bản ghi ngay, quy trình phục hồi cần có cách tránh đưa dữ liệu đã bị loại khỏi hệ thống trở lại trạng thái phục vụ. Khả năng thực hiện và thời điểm cần được mô tả đúng, không báo xóa hoàn tất chỉ dựa trên một thao tác.

Việc xóa bảng ánh xạ có thể giảm khả năng đối chiếu, nhưng không bảo đảm các bản sao khác hoặc thông tin ngoài hệ thống không còn nhận dạng được chủ thể.

## 12. Sampling và debug không thay cho chính sách riêng tư

Một trace chứa token vẫn là sự cố dù chỉ một phần nhỏ request được lấy mẫu. Tương tự, chỉ cho phép ghi body khi có lỗi có thể làm dữ liệu nhạy cảm tập trung đúng vào những tình huống bất thường.

Debug tạm thời nên có phạm vi và giới hạn rõ:

- Tăng độ chi tiết của mã giai đoạn và nhóm lỗi đã làm sạch.
- Chỉ áp dụng cho thành phần hoặc loại lỗi cần điều tra.
- Có thời điểm tự kết thúc.
- Có giới hạn dung lượng và người được đọc.
- Ghi nhận thay đổi cấu hình.
- Không bật thu bí mật đã bị cấm ở chế độ thường.

Không dùng email, token hoặc toàn bộ request làm cách chọn đối tượng debug công khai. Nếu cần điều tra một case cụ thể, cơ chế chọn và liên kết phải qua kênh có kiểm tra quyền.

Dữ liệu mô phỏng dùng cho môi trường thử nghiệm cũng cần được nhận biết. Không lấy dữ liệu thật của người dùng làm mẫu log rồi đưa vào tài liệu, dashboard demo hoặc bộ dữ liệu hỗ trợ.

Một hệ thống có thể theo dõi số lần thuộc tính bị loại hoặc payload không đáp ứng hợp đồng bằng mã lý do hữu hạn. Metric giám sát chính sách không được chứa chính giá trị nhạy cảm bị loại.

## 13. Xử lý khi phát hiện telemetry đã chứa bí mật

Giả sử sau khi thay agent, trace tự động ghi URL của một endpoint chứa recovery token. Collector hiện tại đã che query string, nhưng proxy access log và một exporter phụ đã nhận dữ liệu gốc.

Cần phân biệt các công việc:

1. Dừng nguồn thu không phù hợp và chặn đường xuất tiếp theo theo phạm vi cần thiết.
2. Xác định những bản sao, người có quyền đọc và khoảng thời gian bị ảnh hưởng.
3. Đánh giá token hoặc bằng chứng nào có thể còn hiệu lực.
4. Áp dụng xử lý vô hiệu hóa hoặc phát hành lại theo policy của loại bằng chứng bị lộ.
5. Loại bỏ hoặc hạn chế dữ liệu đã thu theo quy trình của từng nơi lưu.
6. Giữ dấu vết tối thiểu về sự cố và việc xử lý, không sao chép nguyên bí mật sang hồ sơ sự cố.
7. Xác định giới hạn của việc đã xử lý: bản sao ngoài phạm vi kiểm soát không tự biến mất.

Không chỉ thêm regex rồi kết luận dữ liệu cũ đã an toàn. Cũng không tự thu hồi mọi session của mọi tài khoản nếu chưa đánh giá loại dữ liệu và phạm vi tác động.

Nếu phải xoay khóa hoặc vô hiệu hóa một nhóm token, đó là quyết định bảo mật có phạm vi riêng. Một giá trị bị lộ trong telemetry có thể là bí mật cấp quyền, định danh hoặc chỉ là nhãn vận hành; cách xử lý phải tương ứng với ý nghĩa thật.

## 14. Tình huống vận dụng

Một người dùng mất thiết bị MFA và yêu cầu lấy lại quyền truy cập. Luồng gồm kiểm tra bằng chứng, xem xét rủi ro, đăng ký yếu tố mới và xử lý session.

Một thiết kế quan sát phù hợp có thể giữ:

- Counter theo operation và nhóm outcome để thấy lỗi hoặc từ chối tăng.
- Histogram theo thao tác để nhận diện phần xử lý chậm.
- Trace của các lời gọi cần thiết với route mẫu và thuộc tính được phép.
- Log kỹ thuật chứa mã lỗi đã ánh xạ, không chứa bằng chứng.
- Audit có actor, đối tượng và sự kiện thay đổi theo hợp đồng riêng.
- Hồ sơ xác minh trong kho chuyên biệt, được truy cập qua quyền của case.

Khi lỗi xảy ra ở bước xác minh:

1. Dashboard cho thấy timeout của một phụ thuộc tăng.
2. Trace hỗ trợ xác định lời gọi bị chậm mà không chứa OTP hoặc tài liệu người dùng.
3. Nhân viên có nhiệm vụ điều tra được phép nối tham chiếu nội bộ tới case phù hợp.
4. Nhà cung cấp chuyển phát không nhận baggage chứa email hoặc trạng thái khôi phục.
5. Một file export phục vụ điều tra chỉ có dữ liệu cần thiết, người đọc và thời hạn được xác định.
6. Dữ liệu debug kết thúc theo cấu hình thay vì tiếp tục tích lũy sau khi sự cố đã được xử lý.

Ở từng điểm thu thập và chuyển tiếp, cần biết **dữ liệu nào đang đi qua, mục đích nào cho phép giữ nó, ai được liên kết hoặc đọc nó, và khi nào nó hết vòng đời**. Những ranh giới đó giúp hệ thống quan sát hỗ trợ khôi phục tài khoản mà không trở thành kho bí mật hoặc đường tiếp cận hồ sơ ngoài ý muốn.
