# Debug mode production

## 1. Vì sao debug ở production là một vấn đề của đặc tả bảo mật?

Trong chương **Configuration security**, chủ đề debug mode production đặt ra câu hỏi: khi hệ thống xử lý dữ liệu thật, những khả năng hỗ trợ phát triển và chẩn đoán nào được phép tồn tại, ai được kích hoạt chúng và bằng chứng nào cho thấy giới hạn đang được thực thi?

Ở môi trường phát triển, một trang lỗi có stack trace, endpoint xem cấu hình hoặc debugger có thể giúp tìm lỗi nhanh. Ở production, các khả năng đó có thể làm lộ token, dữ liệu cá nhân, câu truy vấn, cấu trúc hệ thống hoặc mở một đường thực thi mã. Người vận hành bật debug để giải quyết sự cố cũng có thể vô tình tạo thêm sự cố bảo mật.

Yêu cầu “tắt debug trên production” là điểm bắt đầu, nhưng chưa đủ để phát triển và kiểm thử. Cần xác định debug bao gồm những khả năng nào, nguồn nào được phép điều khiển chúng, hành vi khi cấu hình trái chính sách và cách kiểm chứng trên hệ thống đang chạy.

Trong module đặc tả yêu cầu bảo mật, chuỗi lập luận của bài học là:

**Tình huống đe dọa → khả năng debug gây rủi ro → yêu cầu có phạm vi → thành phần thực thi → tiêu chí kiểm thử → bằng chứng vận hành.**

Sau bài học, người học có thể:

- Phân biệt chế độ phát triển, debugger, log chi tiết và chẩn đoán vận hành.
- Viết bất biến production cho trang lỗi, endpoint, listener và dữ liệu được thu thập.
- Đặc tả nguồn cấu hình, startup, reload và xử lý phát hiện debug đã hoạt động.
- Thiết kế một khả năng chẩn đoán giới hạn theo quyền, phạm vi, dữ liệu và thời gian.
- Liên kết yêu cầu với xác thực, phân quyền, bảo vệ dữ liệu, audit và phục hồi.

Các tên field, mã yêu cầu, thời hạn và dung lượng bên dưới thuộc một hệ thống minh họa. Chúng cần được xác nhận bằng mô hình đe dọa, nhu cầu ứng phó sự cố và kiến trúc thực tế, không phải mức mặc định chung cho mọi sản phẩm.

## 2. Định nghĩa chính xác “debug”

Không nên gộp mọi hoạt động chẩn đoán vào một boolean rồi suy ra rằng cùng một quy tắc áp dụng cho tất cả.

| Khả năng | Mục đích thường gặp | Rủi ro cần đặc tả |
|---|---|---|
| Development mode | Trang lỗi tương tác, tự nạp lại code, công cụ phát triển | Lộ nội bộ, mở tính năng ngoài baseline, làm thay đổi đường xử lý lỗi |
| Remote debugger | Gắn công cụ vào tiến trình, kiểm tra hoặc thay đổi trạng thái | Đọc bộ nhớ, sửa hành vi hoặc thực thi mã trong quyền của ứng dụng |
| Interactive console | Chạy lệnh hoặc biểu thức để kiểm tra hệ thống | Vượt qua kiểm soát nghiệp vụ, truy cập secret hoặc dữ liệu trực tiếp |
| Verbose logging | Ghi thêm chi tiết về hoạt động | Lộ dữ liệu, tăng chi phí, làm đầy kho log hoặc che khuất sự kiện quan trọng |
| Tracing có mục tiêu | Theo dõi một số request hoặc bước xử lý | Thu thập dữ liệu ngoài phạm vi, giữ định danh nhạy cảm trong trace |
| Endpoint chẩn đoán | Xem metric, trạng thái hoặc thông tin cấu hình | Tiết lộ topology, biến môi trường và khả năng quản trị |
| Heap dump hoặc memory dump | Phân tích bộ nhớ, tìm lỗi khó tái hiện | Chứa credential, khóa, phiên và dữ liệu chưa được lọc |
| Artifact hỗ trợ debug | Symbol, source map, metadata bản build | Phân phối thông tin nội bộ ngoài phạm vi được chấp nhận |

### 2.1. Mức log không chứng minh trạng thái an toàn

Một dịch vụ ghi log ở mức `INFO` vẫn có thể mở cổng debugger. Ngược lại, một sự kiện mang nhãn `DEBUG` có cấu trúc, chỉ gồm mã thao tác và thời lượng, chưa chắc tạo cùng rủi ro với việc dump toàn bộ request.

Do đó cần hai lớp yêu cầu:

1. Quy định khả năng nào bị cấm hoặc được phép tồn tại ở production.
2. Quy định dữ liệu nào được phép đi qua từng khả năng được chấp nhận.

Tên mức log không thay thế hợp đồng dữ liệu. Việc tăng mức log cũng không tự cấp quyền ghi token, mật khẩu hay payload nghiệp vụ.

### 2.2. Khả năng quan sát là một nhu cầu vận hành

Tắt công cụ phát triển không có nghĩa xóa mọi bằng chứng cần điều tra. Hệ thống vẫn cần mã lỗi ổn định, correlation ID do hệ thống quản lý, metric, audit và các sự kiện vận hành đã được thiết kế.

Ví dụ, một phản hồi lỗi có thể trả mã `INTERNAL_ERROR` và request ID. Phần vận hành tìm sự kiện nội bộ đã được phân quyền bằng ID đó. Cả phản hồi lẫn log đều không cần mang access token hoặc toàn bộ nội dung tài liệu để tạo khả năng đối chiếu.

Các dữ liệu chẩn đoán có thể liên kết tới người dùng hoặc tenant vẫn cần được phân loại, giới hạn truy cập và có thời hạn lưu phù hợp.

## 3. Xác định phạm vi và mô hình đe dọa

Xét một dịch vụ tài liệu đa tenant, triển khai nhiều instance. Production xử lý tài liệu thật. API người dùng, API quản trị, gateway, worker nền và đường truy cập trực tiếp được hỗ trợ đều thuộc phạm vi cần xem xét.

Những tác nhân liên quan gồm người dùng bên ngoài, người dùng đã đăng nhập nhưng không có quyền vận hành, người vận hành có thể cấu hình nhầm, tài khoản vận hành bị chiếm và pipeline có thể đưa biến hoặc artifact vào runtime.

| Mã rủi ro | Tình huống | Tác động |
|---|---|---|
| R-DBG-01 | Người gọi tạo lỗi và nhận trang lỗi chi tiết | Lộ stack trace, đường dẫn, câu truy vấn hoặc thông tin cấu hình |
| R-DBG-02 | Một debugger hoặc console xuất hiện trong production | Đọc hoặc thay đổi bộ nhớ, thực thi mã theo quyền ứng dụng |
| R-DBG-03 | Log request, header hoặc object chứa dữ liệu thật | Credential và dữ liệu tenant bị sao chép sang kho chẩn đoán |
| R-DBG-04 | Biến môi trường hoặc flag từ xa vượt quyền | Bật lại debug dù file baseline đang đúng |
| R-DBG-05 | Chẩn đoán bật không giới hạn | Thu thập quá phạm vi, kéo dài sau sự cố hoặc làm cạn tài nguyên |
| R-DBG-06 | Một instance không nhận lệnh dừng hoặc restart với cấu hình cũ | Tiếp tục hoạt động ngoài thời hạn được cấp |
| R-DBG-07 | Gói hỗ trợ hoặc artifact bị chia sẻ quá rộng | Lộ dữ liệu và thông tin nội bộ ra khỏi ranh giới được phép |

Mỗi rủi ro cần gắn với đường đi cụ thể. Chẳng hạn, “không thể truy cập debugger từ Internet” chưa trả lời một workload cùng mạng hoặc người có quyền port-forward có thể truy cập nó hay không.

Cũng cần phân biệt thông tin cấu trúc với secret. Source map hoặc symbol có thể giúp phân tích ứng dụng nhưng không tự thay thế quyền truy cập vào máy chủ. Quyết định phân phối các artifact này phụ thuộc mô hình ứng dụng; việc loại bỏ chúng không làm code phía client trở thành nơi lưu secret an toàn.

## 4. Chọn baseline cho production

Trong ví dụ của bài, baseline production có các bất biến sau:

- Development mode, trang lỗi tương tác và interactive console không được kích hoạt.
- Remote debugger không được khởi tạo và không mở listener.
- Phản hồi lỗi bên ngoài không chứa stack trace, đường dẫn nội bộ, giá trị cấu hình hoặc dữ liệu nhạy cảm.
- Log, trace và gói hỗ trợ tuân thủ hợp đồng dữ liệu đã duyệt trước khi ra khỏi thành phần tạo dữ liệu.
- Chẩn đoán mở rộng chỉ sử dụng các khả năng được cho phép riêng, có phạm vi và thời hạn.
- Không có cờ khẩn cấp cho phép bỏ toàn bộ bất biến trên.

Đây là lựa chọn thiết kế của ví dụ. Một hệ thống có nhu cầu gắn debugger vào production phải đặc tả năng lực đó như quyền quản trị rất mạnh, cùng ranh giới tin cậy, cô lập và phương án bảo vệ riêng. Không thể coi việc đổi một boolean là đầy đủ cho quyết định ấy.

### 4.1. Môi trường phải được xác định từ nguồn đáng tin cậy

Nếu ứng dụng chỉ tin `environment=development` trong cùng file cấu hình mà người vận hành có thể sửa, họ có thể vô tình hoặc cố ý làm workload production bỏ qua baseline.

Yêu cầu cần xác định môi trường bằng ngữ cảnh deployment có thẩm quyền, rồi đối chiếu với metadata cấu hình. Nguồn đó có thể là danh tính workload và dữ liệu deployment do nền tảng kiểm soát; lựa chọn cụ thể thuộc kiến trúc.

Những tình huống sau phải có kết quả rõ:

- Không xác định được môi trường đáng tin cậy: không bật khả năng phát triển.
- File tự khai là development nhưng deployment là production: từ chối cấu hình không khớp.
- Một tham số runtime yêu cầu đổi loại môi trường: không được dùng nó để giảm baseline.
- Bản phát hành thiếu thông tin cần kiểm tra: chưa đủ điều kiện đưa workload vào phục vụ production.

### 4.2. Thứ tự ưu tiên không phải quyền ghi đè

Default trong code, file triển khai, biến môi trường, command line, cấu hình từ xa và log management đều có thể ảnh hưởng tới trạng thái cuối cùng.

Cần công bố field nào mỗi nguồn được điều khiển. Trong ví dụ, không nguồn nào được bật development mode hoặc remote debugger trên production; giao diện vận hành chỉ được yêu cầu một phiên chẩn đoán thuộc danh sách cho phép.

Khi một nguồn gửi giá trị bị cấm, hệ thống phải trả kết quả bị từ chối và tạo bằng chứng phù hợp. Không chỉ bỏ qua giá trị rồi báo cập nhật thành công, vì điều đó làm người vận hành hiểu sai trạng thái có hiệu lực.

## 5. Viết yêu cầu bảo mật có thể kiểm chứng

Một yêu cầu nên xác định tối thiểu: phạm vi, điều kiện kích hoạt, hành vi bắt buộc, kết quả khi lỗi, nguồn có thẩm quyền và bằng chứng chấp nhận.

### 5.1. Ví dụ một yêu cầu đầy đủ

**DBG-01 — Cấm development mode trên production**

- **Rủi ro:** R-DBG-01 và R-DBG-04.
- **Phạm vi:** mọi process của dịch vụ tài liệu trong deployment production, gồm API và worker.
- **Điều kiện:** startup, reload hoặc triển khai bản phát hành mới.
- **Yêu cầu:** hệ thống phải kiểm tra trạng thái development mode sau khi hợp nhất mọi nguồn cấu hình được hỗ trợ, dựa trên ngữ cảnh deployment đáng tin cậy.
- **Đầu vào không hợp lệ:** `true`, sai kiểu, field trùng hoặc yêu cầu ghi đè trái thẩm quyền không được tạo một cấu hình có hiệu lực.
- **Khi startup:** không đưa workload vào trạng thái phục vụ nếu candidate vi phạm baseline.
- **Khi reload:** từ chối candidate, giữ snapshot đã được chấp nhận nếu snapshot đó vẫn còn hợp lệ.
- **Bằng chứng:** revision hiệu lực, mã từ chối, nguồn đề nghị đã được lọc và kiểm thử lỗi qua API thực tế.
- **Tiêu chí chấp nhận:** không có đường yêu cầu được hỗ trợ nào nhận trang lỗi phát triển hoặc khởi tạo công cụ phát triển sau một lần cấu hình bị từ chối.

Field bị thiếu có thể nhận default `false`; field rỗng, `null` hoặc chuỗi `"false"` không được tự hiểu là field bị thiếu. Cần định nghĩa kiểu dữ liệu để tránh các cách ép kiểu khác nhau giữa các nguồn.

### 5.2. Bộ yêu cầu cho các khả năng liên quan

| ID | Yêu cầu trong baseline minh họa | Rủi ro và bằng chứng chính |
|---|---|---|
| DBG-02 | Production không khởi tạo remote debugger hoặc interactive console; cơ chế build và deployment phải ngăn các đường khởi tạo đã biết của nền tảng được chọn. | R-DBG-02; kiểm tra artifact, tham số launch, process và kết nối thực tế đến listener |
| DBG-03 | Mọi đường trả lỗi bên ngoài dùng hợp đồng lỗi đã duyệt; không xuất thông tin nội bộ bị cấm. | R-DBG-01; gây lỗi ở gateway, middleware, ứng dụng và đường fallback |
| DBG-04 | Dữ liệu log/trace đi theo danh sách field và quy tắc biến đổi đã duyệt; không ghi credential hoặc payload ngoài hợp đồng. | R-DBG-03; dữ liệu đánh dấu trong header, body, exception và sink cuối |
| DBG-05 | Chỉ chủ thể được cấp quyền riêng mới được yêu cầu chẩn đoán; quyền quản trị nghiệp vụ không tự suy ra quyền này. | R-DBG-04, R-DBG-05; kiểm thử vai trò, tenant, xác thực mạnh theo policy vận hành và audit |
| DBG-06 | Chẩn đoán chỉ áp dụng cho deployment, instance, thành phần và loại sự kiện được cấp; mặc định không hoạt động. | R-DBG-03, R-DBG-05; đối chiếu phạm vi yêu cầu với dữ liệu thực thu |
| DBG-07 | Phiên chẩn đoán có hạn sử dụng, dung lượng và hạn mức sự kiện; không được tự gia hạn hoặc khôi phục hiệu lực bằng restart. | R-DBG-05, R-DBG-06; kiểm thử hết hạn, đạt cận và khởi động lại |
| DBG-08 | Lệnh dừng hoặc thu hồi phải có thời hạn thực thi trên mọi instance; instance mất liên lạc không được hoạt động vô hạn. | R-DBG-06; đo thời điểm chấp nhận lệnh, lần phát sinh cuối và trạng thái từng instance |
| DBG-09 | Đề nghị kích hoạt, gia hạn, dừng, từ chối và thu hồi có audit; kích hoạt cần ghi ý định bền vững trước khi tăng thu thập. | R-DBG-04, R-DBG-05; đối soát revision, phiên và sự kiện sau sự cố |
| DBG-10 | Endpoint chẩn đoán và kho đầu ra chỉ cho các quyền đã xác định; các đường truy cập trực tiếp phải chịu kiểm soát tương ứng. | R-DBG-02, R-DBG-07; kiểm thử xác thực, phân quyền và mọi đường vào được hỗ trợ |
| DBG-11 | Heap dump, memory dump và gói hỗ trợ chưa được lọc không thuộc phiên chẩn đoán thông thường của baseline này. | R-DBG-03, R-DBG-07; kiểm thử không thể yêu cầu loại thu thập ngoài danh sách |
| DBG-12 | Khi phát hiện khả năng debug bị cấm đang hoạt động, hệ thống và vận hành phải cô lập đường đó, thu hồi quyền liên quan và xác minh trạng thái an toàn trước khi phục vụ lại. | R-DBG-02, R-DBG-06; diễn tập phát hiện, cô lập, thay thế workload và kiểm chứng |

Các ID này là mã nội bộ của bài học, không phải tên điều khoản của một tiêu chuẩn. Trong dự án, cần bổ sung chủ sở hữu và liên kết tới quyết định kiến trúc, ca kiểm thử, bản phát hành áp dụng.

## 6. Hợp đồng cấu hình mẫu

Cấu hình sau là schema tự định nghĩa để minh họa yêu cầu. Nó không phải cấu hình có thể copy trực tiếp vào một framework.

```yaml
schemaVersion: 1
revision: "prod-baseline-042"
targetEnvironment: production

development:
  enabled: false
  interactiveErrors: false

runtimeDebug:
  remoteAttachEnabled: false
  interactiveConsoleEnabled: false

errors:
  externalFormat: public-error-v1
  includeStackTrace: false

diagnostics:
  enabledByDefault: false
  allowedCapabilities:
    - component-events
    - duration-metrics
  rawPayloadCaptureAllowed: false
  memoryDumpAllowed: false
  maxSessionSeconds: 900
  maxOutputBytesPerSession: 20971520
  maxEventsPerSecondPerInstance: 100
  revocationDeadlineSeconds: 30

audit:
  durableIntentRequiredForActivation: true
```

Ý nghĩa của hợp đồng:

| Nhóm | Quy tắc khi thiếu hoặc bị ghi đè |
|---|---|
| Metadata schema, revision và môi trường | Bắt buộc có; schema không hỗ trợ hoặc đích không khớp bị từ chối |
| Development và runtime debug | Thiếu nhận `false`; production từ chối mọi yêu cầu bật |
| Hợp đồng lỗi | Dùng `public-error-v1` của phiên bản schema; không cho nguồn runtime bật stack trace bên ngoài |
| Phiên chẩn đoán | Mặc định không có phiên hoạt động; giới hạn của baseline không tự tạo quyền kích hoạt |
| Raw payload và memory dump | Không được bật trong baseline; tên capability ngoài danh sách bị từ chối |
| Các cận tài nguyên và thời gian | Phải là số nguyên dương đúng đơn vị; `0` không mang nghĩa vô hạn |
| Audit | Bắt buộc ghi ý định bền vững trước kích hoạt; không có fallback bỏ audit |

Trong ví dụ, 900 giây là thời gian tối đa cho một phiên; 20.971.520 byte là tổng số byte đầu ra chẩn đoán đã mã hóa UTF-8, tính cả metadata, của toàn phiên trên các instance được chọn. Một bản triển khai phân tán phải có cơ chế thực thi cận tổng, chẳng hạn phân bổ ngân sách con không vượt tổng ngân sách.

Cận 100 sự kiện mỗi giây áp dụng cho từng instance. Hợp đồng cần định nghĩa cửa sổ đo; ở đây dùng giới hạn tốc độ với dung lượng burst tối đa 100 sự kiện. Không tạo hàng đợi chờ không giới hạn để lách cận. Khi hết ngân sách đầu ra, dừng phát sinh sự kiện chẩn đoán tùy chọn của phiên và ghi kết quả tổng hợp đã được lọc.

Các cận này không áp dụng để loại bỏ audit bắt buộc hoặc sự kiện an ninh cần thiết. Hai luồng phải có ngân sách và chính sách khi lỗi rõ ràng, để chẩn đoán không làm mất bằng chứng bảo mật.

Giá trị thời gian, dung lượng và tần suất phải được xác nhận bằng nhu cầu điều tra, chi phí lưu trữ và thử tải. Có cấu hình giới hạn không thay thế bằng chứng giới hạn được thực thi trước khi tài nguyên bị tiêu thụ quá mức.

## 7. Thiết kế chẩn đoán production có kiểm soát

Thay vì bật toàn bộ môi trường phát triển, ví dụ cho phép thu thập thêm các sự kiện của một thành phần trong thời gian ngắn.

### 7.1. Yêu cầu kích hoạt phải mang đủ ngữ cảnh

Một yêu cầu có thể gồm:

```json
{
  "deployment": "documents-prod",
  "instances": ["documents-api-07"],
  "component": "authorization-decision",
  "capability": "component-events",
  "requestedSeconds": 300,
  "reasonRef": "INC-2048"
}
```

Thông tin chủ thể, thời điểm cấp, thời điểm hết hạn và mã phiên phải được lấy hoặc tạo ở phía có thẩm quyền. Client không tự khai chúng để được tin cậy.

Bộ quyết định cần kiểm tra:

- Chủ thể đã xác thực và có quyền chẩn đoán đúng deployment, thành phần, instance.
- Điều kiện xác thực bổ sung cho quyền vận hành nhạy cảm đã được đáp ứng.
- Capability nằm trong danh sách được baseline cho phép.
- Thời lượng và ngân sách không vượt cận.
- Yêu cầu không trỏ sang tenant hoặc workload ngoài phạm vi quyền.
- Có thể ghi ý định audit bền vững và phân phối quyền chẩn đoán một cách xác thực.

Nếu hệ thống yêu cầu phê duyệt độc lập, cần đặc tả vai trò phê duyệt và quan hệ với người yêu cầu. Không mặc định mọi thao tác đều phải qua hai người; quyết định đó xuất phát từ rủi ro và quy trình của hệ thống.

### 7.2. Vòng đời phiên phải có trạng thái rõ

```text
Được yêu cầu
    -> Kiểm tra quyền và phạm vi
    -> Ghi ý định bền vững
    -> Đang hoạt động trong giới hạn
    -> Kết thúc: hết hạn / thu hồi / hết ngân sách / chủ động dừng

Bất kỳ bước kiểm tra nào thất bại
    -> Bị từ chối, không tăng thu thập
```

Một lần gia hạn là một quyết định cấp quyền mới, cần kiểm tra và audit lại. Không tự gia hạn vì sự cố chưa đóng hoặc vì người vận hành vẫn mở giao diện.

Khi kết thúc phiên, dừng tạo dữ liệu chẩn đoán mới. Phần dữ liệu đã được lọc và nằm trong ngân sách có thể tiếp tục chuyển tới kho được phép theo chính sách bàn giao đã xác định; không coi hàng đợi còn dữ liệu là quyền tiếp tục thu thập.

Worker nền, tác vụ bất đồng bộ và process con phải được bao phủ nếu chúng có khả năng tạo dữ liệu của phiên. Chỉ tắt cờ trong một API instance không chứng minh toàn bộ phiên đã dừng.

### 7.3. Thực thi thời hạn khi mất kết nối hoặc restart

Giả sử DBG-08 yêu cầu dừng không muộn hơn 30 giây từ khi dịch vụ điều khiển chấp nhận lệnh thu hồi. Cần ghi rõ mốc bắt đầu, cách đo lần phát sinh cuối và xử lý instance chưa phản hồi.

Instance mất kết nối không thể tự biết ngay một lệnh thu hồi mới. Để giữ cận 30 giây, thiết kế có thể dùng quyền ngắn hạn phải tái xác nhận, kết hợp cơ chế dừng thu thập tại instance hoặc một điểm thực thi độc lập bao phủ mọi đường tạo dữ liệu.

Thời hạn tái xác nhận, sai số thời gian, độ trễ lập lịch và độ trễ chặn phải có tổng cận phù hợp với cam kết. Chỉ đặt chu kỳ polling 30 giây chưa bảo đảm dừng trong 30 giây.

Quyền được lưu cache phải gắn với deployment, instance, capability, phiên và thời điểm hết hạn. Restart không đặt lại đồng hồ của phiên; bản quyền cũ hoặc thông điệp bị phát lại không được khôi phục phiên đã kết thúc.

Nếu chưa có cơ chế bảo đảm cận khi mất liên lạc, yêu cầu thu hồi vẫn là khoảng trống kiến trúc cần giải quyết.

### 7.4. Audit lỗi không được cản trở hành động dừng

Trước kích hoạt, không ghi được ý định bền vững thì không tăng thu thập. Sau kích hoạt, nếu cơ chế bảo đảm quyền hoặc audit bắt buộc mất hiệu lực, phiên phải dừng theo hợp đồng.

Hành động dừng hoặc thu hồi không được bị từ chối chỉ vì kho audit đang lỗi. Hệ thống cần ưu tiên giảm khả năng thu thập, giữ bằng chứng tối thiểu ở nơi bền vững được thiết kế nếu có và đối soát khi khôi phục.

Phải phân biệt “không cấp thêm quyền khi thiếu bằng chứng” với “không cho thu hồi quyền khi thiếu bằng chứng”. Hai hành vi có tác động bảo mật ngược nhau.

## 8. Kiểm soát dữ liệu trước khi ghi hoặc xuất

### 8.1. Thiết kế sự kiện theo danh sách được phép

Với thành phần quyết định quyền, một sự kiện hợp lệ có thể là:

```json
{
  "event": "authorization_decision",
  "requestId": "req-generated-123",
  "policyRevision": "policy-81",
  "decision": "deny",
  "reasonCode": "TENANT_SCOPE_MISMATCH",
  "durationMs": 4
}
```

Không cần ghi access token, cookie, toàn bộ request body hoặc tài liệu để chứng minh quyết định từ chối.

Danh sách field phải đi kèm kiểu dữ liệu, độ dài, miền giá trị và quy tắc xử lý dữ liệu do người gọi kiểm soát. Request ID nhận từ bên ngoài cần được kiểm tra hoặc thay bằng ID nội bộ trước khi dùng để đối chiếu, tránh chèn dữ liệu tùy ý vào log.

Nếu cần định danh tenant hoặc chủ thể, phải xác định mục đích và mức bảo vệ. Hash một định danh không tự loại bỏ khả năng liên kết dữ liệu hoặc mọi nghĩa vụ bảo vệ dữ liệu đó.

### 8.2. Lọc ở đầu nguồn và kiểm tra đường lỗi

Đối tượng request, exception, cấu hình và phản hồi của thư viện đều có thể chứa dữ liệu nhạy cảm. Các đường dễ bị bỏ sót gồm:

- Middleware ghi request khi xảy ra lỗi.
- Bộ xử lý exception xuất thông điệp từ tầng dữ liệu.
- Startup ghi mọi biến môi trường để hỗ trợ chẩn đoán.
- Trace tự gắn header hoặc tham số.
- Fallback logger dùng khi sink chính không hoạt động.
- Bộ tạo gói hỗ trợ gom file log, cấu hình và artifact.

Ưu tiên tạo sự kiện từ các field được cho phép, thay vì serialize object lớn rồi cố xóa một số tên khóa nhạy cảm. Redaction theo tên khóa vẫn có ích nhưng không bảo đảm xử lý giá trị nằm trong chuỗi tự do, giá trị biến đổi hoặc trường lồng nhau.

Dữ liệu cần được kiểm soát trước khi chuyển tới sink, hàng đợi, collector hoặc tệp tạm. Lọc ở giao diện xem log không xóa dữ liệu đã đi vào kho lưu.

### 8.3. Bảo vệ đầu ra và phục hồi sau rò rỉ

Kho chẩn đoán cần có xác thực, phân quyền đọc/xuất, bảo vệ đường truyền, chính sách lưu và xóa. Đường dẫn tải gói hỗ trợ cũng thuộc phạm vi kiểm soát; biết URL không tự tạo quyền truy cập.

Nếu phát hiện secret đã được ghi, chỉ giảm mức log không xử lý phần dữ liệu đã tồn tại. Quy trình cần xác định phạm vi sao chép, giới hạn quyền truy cập, thu hồi hoặc xoay credential bị ảnh hưởng, xử lý dữ liệu theo chính sách và xác minh đường rò đã được đóng.

Không đưa credential thật vào ca kiểm thử để chứng minh redaction. Dùng dữ liệu thử có dấu nhận dạng và môi trường kiểm tra phù hợp.

## 9. Thực thi ở build, deployment và runtime

Một cờ trong file ứng dụng thường không kiểm soát hết khả năng debug của runtime hoặc nền tảng.

| Lớp | Trách nhiệm kiểm soát | Bằng chứng phù hợp |
|---|---|---|
| Build và artifact | Không đóng gói công cụ phát triển bị cấm; quản lý symbol và artifact chẩn đoán theo policy | Danh tính bản build, thành phần đóng gói, kết quả kiểm tra artifact |
| Cấu hình launch | Kiểm tra tham số runtime, agent, biến môi trường và script khởi động thuộc phạm vi hỗ trợ | Cấu hình được chuẩn hóa, nguồn cấp và quyết định chấp nhận |
| Deployment | Đối chiếu môi trường, quyền sửa, port, volume và đường truy cập | Revision deployment, policy áp dụng, đường vào được kiểm kê |
| Ứng dụng | Không tạo trang lỗi phát triển; kiểm soát dữ liệu và phiên chẩn đoán | Kiểm thử API, revision hiệu lực, audit phiên |
| Runtime và mạng | Hạn chế gắn công cụ vào process, truy cập listener và đường quản trị | Quyền runtime, kết nối thử được phép, trạng thái process/listener |
| Vận hành | Phát hiện drift, dừng phiên và cô lập vi phạm | Cảnh báo, thời gian phản ứng, kết quả xác minh sau xử lý |

Danh sách tham số hoặc agent nguy hiểm phụ thuộc runtime được chọn. Khi triển khai thực tế, đội kiến trúc phải xác định chúng theo nền tảng và tài liệu chính thức; bài học không giả định một tên cờ có thể bao phủ mọi runtime.

Không nên coi việc ứng dụng tự báo `debug=false` là bằng chứng duy nhất. Cần kết hợp trạng thái cấu hình có hiệu lực với quan sát khả năng thực tế.

### 9.1. Startup và reload

Khi startup với candidate vi phạm baseline, workload không chuyển sang trạng thái phục vụ. Có thể vẫn cung cấp health tối thiểu theo kiến trúc, nhưng không để health tiết lộ cấu hình hay secret.

Khi reload nhận candidate không hợp lệ, từ chối candidate trước khi thay trạng thái. Giữ cấu hình cũ chỉ khi nó vẫn đáp ứng điều kiện hiệu lực. Không bật tạm debugger rồi mới kiểm tra hoặc ghi audit.

Một cập nhật phiên chẩn đoán phải được áp dụng nhất quán cho phạm vi của nó. Nếu một phần instance không thể thực thi, hệ thống phải báo trạng thái thực tế và xử lý theo hợp đồng, không báo cả nhóm đã kích hoạt hay đã dừng khi chưa có bằng chứng.

### 9.2. Phát hiện debug đã tồn tại

Từ chối candidate mới không đủ khi listener hoặc console đã hoạt động do drift, artifact sai hay đường launch khác.

Khi phát hiện vi phạm, cần có khả năng ngừng listener hoặc cô lập workload khỏi các đường có thể tiếp cận. Chỉ đặt readiness thành không sẵn sàng có thể không chặn kết nối trực tiếp, kết nối đang tồn tại hoặc đường quản trị khác.

Kế hoạch phục hồi cần ghi rõ cách xử lý kết nối hiện có, quyền runtime, workload bị ảnh hưởng và dữ liệu có thể đã lộ. Nếu không thể chứng minh process trở lại trạng thái tin cậy, có thể cần thay thế nó bằng artifact và cấu hình đã được chấp nhận.

Đưa workload trở lại phục vụ chỉ sau khi kiểm tra lại baseline và các đường vào. Một lần restart với cùng tham số sai không phải biện pháp sửa lỗi.

## 10. Kế hoạch kiểm thử gắn với yêu cầu

Không chỉ tìm chuỗi `debug=false` trong repository. Kiểm thử phải bao phủ đầu vào cấu hình, khả năng của process và dữ liệu đi ra.

| Ca | Thiết lập hoặc tác động | Kết quả chấp nhận | Liên kết |
|---|---|---|---|
| T01 | Cài mới thiếu các field debug tùy chọn | Nhận default tắt; không có trang lỗi phát triển, console hoặc debugger | DBG-01, DBG-02 |
| T02 | Bật development mode lần lượt qua file, biến môi trường, command line và nguồn từ xa được hỗ trợ | Mọi candidate trái baseline bị từ chối; startup không phục vụ hoặc reload giữ bản hợp lệ | DBG-01 |
| T03 | Gửi boolean dạng chuỗi, `null`, field sai tên và khóa trùng | Từ chối theo schema; không ép kiểu hoặc bỏ qua âm thầm | DBG-01 |
| T04 | Khai development trong cấu hình của deployment production | Không giảm baseline; ghi nhận lỗi không khớp môi trường | DBG-01 |
| T05 | Cố khởi tạo runtime debugger bằng đường launch thuộc phạm vi nền tảng | Không được đưa workload vi phạm vào phục vụ; không kết nối được vào khả năng bị cấm | DBG-02 |
| T06 | Gây lỗi validation, xác thực, phân quyền, phụ thuộc, proxy và lỗi không dự kiến | Phản hồi theo hợp đồng; không lộ stack, cấu hình, truy vấn hoặc dữ liệu nhạy cảm | DBG-03 |
| T07 | Đặt dấu nhận dạng thử trong token, cookie, body, exception và tham số | Không xuất dấu vào các đầu ra bị cấm, gồm log, trace, tệp tạm và gói hỗ trợ | DBG-04 |
| T08 | Dùng tài khoản nghiệp vụ hoặc người vận hành ngoài phạm vi để yêu cầu chẩn đoán | Bị từ chối; không có phiên hoặc dữ liệu mới ngoài quyền | DBG-05, DBG-06 |
| T09 | Yêu cầu capability không có trong danh sách, thời lượng quá cận hoặc phạm vi khác deployment | Từ chối trước kích hoạt; không mở rộng phạm vi ngầm | DBG-06, DBG-07, DBG-11 |
| T10 | Để phiên hết hạn, hết ngân sách hoặc đạt cận sự kiện | Dừng phần thu thập tùy chọn đúng hợp đồng; không làm mất audit bắt buộc | DBG-07 |
| T11 | Thu hồi khi một instance mất liên lạc, rồi restart nó với dữ liệu cache | Không phát sinh dữ liệu quá thời hạn được cấp; không tái kích hoạt phiên đã hết | DBG-07, DBG-08 |
| T12 | Làm kho audit không ghi được trước kích hoạt, sau đó thử dừng phiên đang chạy | Không tăng thu thập khi thiếu ý định bền vững; vẫn thực hiện hành động dừng | DBG-09 |
| T13 | Thử endpoint và kho đầu ra qua gateway, đường trực tiếp được hỗ trợ và vai trò khác nhau | Mọi đường đều áp dụng xác thực, phân quyền và giới hạn công bố | DBG-10 |
| T14 | Tạo drift làm khả năng bị cấm tồn tại trên một instance | Phát hiện và cô lập theo hợp đồng; xác minh cả kết nối đang tồn tại và đường trực tiếp | DBG-12 |
| T15 | Đề nghị gia hạn hoặc phát lại thông điệp kích hoạt cũ | Gia hạn phải qua kiểm tra mới; thông điệp cũ không phục hồi phiên đã kết thúc | DBG-05, DBG-07, DBG-08 |

T07 cần định nghĩa danh sách đầu ra được kiểm tra và dữ liệu nào được phép xuất. “Không tìm thấy một secret mẫu trong log chính” không chứng minh toàn bộ luồng đã an toàn.

T10 và T11 cần đo ở điểm tạo dữ liệu, phân biệt thời điểm thu thập với thời điểm dữ liệu đã được lọc đến kho. Nếu chỉ dùng thời gian nhận tại collector, dữ liệu trễ có thể làm sai kết luận về việc dừng.

T14 cần có thời hạn phát hiện và cô lập được xác nhận theo rủi ro. Không nên đánh dấu đạt chỉ vì cuối cùng người vận hành tìm thấy vi phạm.

### 10.1. Ví dụ Given–When–Then

```gherkin
Given deployment production có baseline r42 đang hợp lệ
And chỉ component-events được phép cho phiên chẩn đoán thông thường
And người yêu cầu chỉ có quyền chẩn đoán documents-api-07
When người đó yêu cầu memory-dump cho documents-api-08
Then yêu cầu bị từ chối
And không có phiên chẩn đoán mới được kích hoạt
And không có memory dump được tạo
And baseline hiệu lực vẫn là r42
And audit chứa chủ thể, phạm vi đề nghị, kết quả và mã lý do đã được lọc
```

Ca này kiểm tra cả capability lẫn phạm vi quyền. Để biết từng kiểm soát hoạt động độc lập, cần thêm biến thể: capability hợp lệ nhưng sai instance; instance hợp lệ nhưng capability bị cấm; cả hai hợp lệ và các điều kiện còn lại được đáp ứng.

Kiểm tra schema phù hợp với kiểm thử đơn vị. Kiểm tra logger, quyền, audit và reload cần kiểm thử tích hợp. Các cam kết về nhiều instance, listener, mất mạng và khôi phục cần kiểm chứng trên môi trường đại diện cho triển khai.

## 11. Truy vết yêu cầu trong vòng đời phát triển

Một chuỗi truy vết cho rò rỉ qua trang lỗi có thể là:

| Mắt xích | Ví dụ |
|---|---|
| Tài sản và rủi ro | Secret và dữ liệu tenant có thể xuất hiện trong lỗi nội bộ; R-DBG-01 |
| Yêu cầu | DBG-01 cấm development mode; DBG-03 giới hạn phản hồi lỗi |
| Kiến trúc | Bộ xử lý lỗi tại gateway và ứng dụng, hợp đồng public-error-v1 |
| Triển khai | Mapper lỗi dùng mã ổn định; không serialize exception ra bên ngoài |
| Kiểm thử | T02, T04 và T06, gồm đường lỗi fallback |
| Bằng chứng vận hành | Revision baseline, thống kê mã lỗi và sự kiện nội bộ đã được lọc |

Với remote debugger, điểm thực thi còn nằm ở build, launch, runtime và quyền nền tảng. Với dữ liệu log, điểm thực thi nằm tại nơi tạo sự kiện và mọi đường xuất. Một đội không thể tự xác nhận yêu cầu chỉ bằng phần cấu hình mình quản lý.

Khi thay framework, runtime, thư viện logging hoặc nền tảng deployment, cần xác định các khả năng debug mới, các default thay đổi và đường điều khiển mới. Cập nhật yêu cầu và kiểm thử tương ứng trước khi coi baseline cũ còn đầy đủ.

Hồ sơ ngoại lệ, nếu chính sách cho phép, cần có người chịu trách nhiệm rủi ro, phạm vi, lý do, biện pháp bù, thời hạn và cách thu hồi được thực thi. Ngoại lệ không phải một ghi chú cho phép bỏ qua mọi kiểm soát trong ứng dụng.

## 12. Bài tập: sửa yêu cầu “chỉ bật debug khi có sự cố”

Một nhóm mô tả hệ thống như sau:

> Production tắt debug mặc định. Khi có sự cố, admin có thể bật debug, ghi toàn bộ request vào log và tắt lại sau khi xử lý xong.

Đặc tả này còn thiếu định nghĩa admin, khả năng debug, phạm vi dữ liệu, thời hạn, giới hạn tài nguyên, hành vi khi quên tắt và bằng chứng vận hành.

Hãy viết lại thành các yêu cầu độc lập cho:

1. Development mode và remote debugger.
2. Quyền kích hoạt chẩn đoán của người vận hành.
3. Dữ liệu được phép ghi.
4. Phạm vi deployment, instance và thành phần.
5. Thời hạn, ngân sách và cơ chế thu hồi.
6. Audit, mất kết nối, restart và khôi phục.

Một hướng giải quyết là giữ development mode và debugger bị cấm trong baseline; chỉ cho phép sự kiện có cấu trúc của một thành phần; yêu cầu quyền chẩn đoán riêng; áp dụng thời lượng tối đa, ngân sách và quyền ngắn hạn; audit trước khi tăng thu thập; dừng khi hết quyền mà không chờ người vận hành nhớ tắt.

Ví dụ yêu cầu thay thế:

**Khi chủ thể có quyền chẩn đoán đúng deployment yêu cầu thu thập component-events cho một instance production, hệ thống chỉ kích hoạt sau khi xác minh phạm vi, cận tài nguyên và ghi ý định audit bền vững. Phiên không vượt 900 giây, không thu payload thô, không bật console hoặc debugger và phải dừng theo hạn được cấp, kể cả khi mất kết nối hoặc restart.**

Hãy bổ sung ca từ chối cho người có quyền quản trị tài liệu nhưng không có quyền chẩn đoán, ca hết thời hạn và ca kho audit lỗi. Đối với từng ca, nêu revision có hiệu lực, dữ liệu được tạo, hành vi API và bằng chứng sau phục hồi.

Sản phẩm cần đạt là một hợp đồng có thể giao cho phát triển, kiểm thử và vận hành: khả năng nào tồn tại, ai được dùng, dữ liệu nào được phép thu thập, khi nào quyền kết thúc và làm sao chứng minh các giới hạn vẫn đúng khi hệ thống gặp sự cố.
