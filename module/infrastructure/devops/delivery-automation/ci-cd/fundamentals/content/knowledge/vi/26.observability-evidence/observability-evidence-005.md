# Giới hạn dữ liệu nhạy cảm trong báo cáo và nhật ký

CI/CD tạo ra nhiều bằng chứng trong suốt vòng đời phần mềm: log build, test report, security scan, deployment event, trace, metric, crash dump và artifact chẩn đoán. Những dữ liệu này giúp giải thích vì sao một thay đổi được chấp nhận, vì sao pipeline thất bại hoặc phiên bản nào đang chạy. Nhưng chúng cũng có thể chứa password, token, private key, dữ liệu cá nhân, thông tin thanh toán, header xác thực, câu lệnh SQL và nội dung request của người dùng.

Báo cáo và nhật ký cần đủ chi tiết để điều tra, đồng thời phải giới hạn dữ liệu nhạy cảm ngay từ lúc thu thập. Cách tiếp cận an toàn là **chỉ ghi những trường cần thiết, biến đổi hoặc loại bỏ dữ liệu nhạy cảm trước khi phát tán, giới hạn người được xem và thời gian lưu**. Redaction ở bước hiển thị chỉ là lớp bổ sung; nếu secret đã đi vào log thô, artifact hoặc trace ở nơi khác, nguy cơ vẫn còn.

## 1. Vì sao log và report có thể trở thành nơi rò rỉ dữ liệu?

Một pipeline có thể xử lý secret và dữ liệu nhạy cảm ở nhiều bước:

- Checkout repository có file cấu hình hoặc test fixture chứa thông tin thật.
- Build đọc credential để tải dependency hoặc ký artifact.
- Test sử dụng token, connection string, dữ liệu khách hàng hoặc response từ hệ thống tích hợp.
- Scanner in nội dung file, URL hoặc đoạn mã có secret.
- Deploy script truyền credential đến cloud, cluster hoặc registry.
- Ứng dụng ghi request, response, exception hoặc SQL parameter vào log.
- Crash dump và heap dump có thể giữ dữ liệu từng tồn tại trong bộ nhớ.
- Test report có thể lưu tên, email, địa chỉ, payload hoặc stack trace.
- Artifact và cache có thể đóng gói file cấu hình, thư mục home hoặc credential tạm.

Một giá trị nhạy cảm không cần được ghi trực tiếp mới gây rò rỉ. Ví dụ, URL kết nối có dạng username:password@host; header Authorization được ghi trong debug log; exception chứa toàn bộ query string; hoặc report lưu nguyên request body. Một file đã được che trong giao diện CI vẫn có thể tồn tại trong artifact tải xuống hoặc log archive.

Vì vậy, cần xem log, report, trace, metric label và artifact chẩn đoán là các kênh dữ liệu cần kiểm soát. Chúng không tự động an toàn chỉ vì được tạo bởi hệ thống nội bộ.

## 2. Phân loại dữ liệu trước khi ghi

Trước khi thiết kế logging policy, hãy phân loại trường dữ liệu theo mức độ nhạy cảm và mục đích sử dụng.

| Nhóm | Ví dụ | Cách xử lý |
|---|---|---|
| Công khai | Commit SHA, tên job, phiên bản ứng dụng đã công bố | Có thể ghi theo nhu cầu truy vết |
| Nội bộ | Tên service, cluster alias, tên package nội bộ | Chỉ chia sẻ trong phạm vi được phép |
| Nhạy cảm | Email, user ID, IP, tenant ID, mã đơn hàng | Giảm thiểu, giả danh hóa hoặc giới hạn truy cập |
| Bí mật xác thực | Password, API token, cookie, private key | Không ghi giá trị; loại bỏ hoặc che trước khi log |
| Dữ liệu cá nhân/nhạy cảm cao | Hồ sơ cá nhân, thông tin thanh toán, dữ liệu định danh | Tránh thu thập trong telemetry; chỉ xử lý trong hệ thống được phê duyệt |
| Dữ liệu vận hành có thể nhạy cảm | SQL, request body, hostname nội bộ, topology | Chỉ ghi phần cần thiết và kiểm soát quyền truy cập |

Tên gọi hoặc mã định danh không phải lúc nào cũng vô hại. Một user ID có thể liên kết trở lại một cá nhân khi kết hợp với hệ thống khác. IP, tenant ID hoặc order ID có thể tiết lộ hoạt động của một người hoặc tổ chức. Cần đánh giá cả khả năng liên kết dữ liệu, không chỉ nhìn riêng từng trường.

Phân loại phải được áp dụng cho cả log thành công và log lỗi. Exception, debug output và test report thường chứa nhiều chi tiết hơn log thông thường nên cần chính sách tương ứng.

## 3. Nguyên tắc tối thiểu hóa dữ liệu

Data minimization nghĩa là chỉ thu thập dữ liệu cần để vận hành, bảo mật hoặc điều tra một mục tiêu cụ thể.

Trước khi thêm một trường vào log, hãy hỏi:

- Trường này giúp trả lời câu hỏi vận hành nào?
- Có thể dùng trạng thái, mã lỗi hoặc thống kê thay cho giá trị gốc không?
- Có thể dùng correlation ID thay cho user/request payload không?
- Ai cần xem trường này?
- Trường có thể bị kết hợp với dữ liệu khác để nhận diện cá nhân không?
- Cần giữ trong bao lâu?
- Nếu trường bị lộ, tác động là gì?

Ví dụ, để điều tra lỗi đăng nhập, thường cần thời điểm, kết quả, mã lỗi, client type và correlation ID. Không cần ghi password, cookie hoặc toàn bộ request body.

Thay vì ghi:

~~~json
{
  "event": "login_failed",
  "email": "customer@example.com",
  "password": "P@ssw0rd",
  "authorization": "Bearer eyJhbGciOi...",
  "requestBody": {
    "email": "customer@example.com",
    "password": "P@ssw0rd"
  }
}
~~~

Hãy ghi sự kiện tối thiểu:

~~~json
{
  "event": "login_failed",
  "reason_code": "INVALID_CREDENTIALS",
  "subject_ref": "usr_7f21a9",
  "correlation_id": "req_01J9K...",
  "client_type": "web"
}
~~~

Giá trị subject_ref trong ví dụ là định danh giả danh hóa. Hệ thống vẫn cần bảo vệ mapping giữa định danh này và tài khoản thật. Không đưa dữ liệu gốc vào một trường khác trong cùng log.

## 4. Không ghi secret vào log

Các loại dữ liệu sau cần được xem là secret hoặc credential:

- Password và database connection string có password.
- Access token, refresh token, API key và webhook secret.
- Authorization header, cookie và session ID.
- Private key, signing key, certificate material.
- Cloud access key, temporary credential và OIDC token.
- Registry credential và deploy token.
- Secret trong query parameter hoặc URL.
- Nội dung file cấu hình có giá trị bí mật.

Không dùng log để xác minh secret đã được cấp đúng. Thay vào đó, log trạng thái như “credential retrieved”, “authentication succeeded” hoặc mã lỗi đã được chuẩn hóa. Nếu cần xác định secret version, ghi secret resource/version identifier đã được phê duyệt, không ghi giá trị.

Không đưa secret vào:

- Console output hoặc debug print.
- Shell command line và process arguments.
- Exception message.
- Test assertion message.
- JUnit XML, HTML report hoặc coverage metadata.
- Artifact, cache và build scan.
- Trace attribute, span event hoặc baggage.
- URL, query string hoặc tên file.
- Screenshot/video của terminal hoặc giao diện quản trị.

Nếu secret đã xuất hiện trong log, cần coi credential đó có nguy cơ bị lộ: thu hồi hoặc xoay vòng theo quy trình, xác định phạm vi bản sao và xử lý log/artifact theo chính sách sự cố. Chỉ xóa dòng log khỏi giao diện không làm credential cũ an toàn trở lại.

## 5. Thiết kế logging theo allowlist

Một cách an toàn là định nghĩa schema log với danh sách trường được phép. Ứng dụng chỉ ghi các trường đã được duyệt, thay vì ghi toàn bộ object hoặc serialize nguyên request.

Ví dụ schema sự kiện:

~~~json
{
  "timestamp": "2026-11-18T10:20:30Z",
  "level": "ERROR",
  "service": "payments-api",
  "environment": "production",
  "event": "payment_authorization_failed",
  "error_code": "PROVIDER_TIMEOUT",
  "correlation_id": "req_01J9K...",
  "duration_ms": 1200
}
~~~

Một schema có allowlist giúp review rõ ràng trường nào được ghi và loại dữ liệu nào bị cấm. Với log có cấu trúc, tránh đặt toàn bộ object request vào một field dạng JSON string vì pipeline redaction khó kiểm soát các trường lồng nhau và biến thể tên field.

Nên chuẩn hóa tên trường nhạy cảm cần chặn, ví dụ:

- password, passwd, secret, token, api_key.
- authorization, proxy_authorization, cookie, set_cookie.
- private_key, client_secret, access_token, refresh_token.
- card_number, cvv, security_code.
- email, phone, address hoặc các trường cá nhân theo phân loại dữ liệu của tổ chức.

Danh sách này không thể bao phủ mọi tên trường. Allowlist theo schema vẫn đáng tin cậy hơn việc chỉ tìm một số từ khóa cấm.

## 6. Ghi log an toàn trong ứng dụng Java

Trong Java, không nên log nguyên request, entity hoặc object chứa thông tin xác thực. Hãy tạo log event riêng với các trường đã chọn.

Ví dụ với SLF4J:

~~~java
log.warn(
    "Payment authorization failed: service={}, errorCode={}, correlationId={}, durationMs={}",
    "payments-api",
    errorCode,
    correlationId,
    durationMs
);
~~~

Nếu dùng structured logging, tạo object log đã được kiểm soát:

~~~java
Map<String, Object> event = Map.of(
    "event", "payment_authorization_failed",
    "service", "payments-api",
    "error_code", errorCode,
    "correlation_id", correlationId,
    "duration_ms", durationMs
);

logger.atWarn().addKeyValue("event", event).log("Payment authorization failed");
~~~

Cú pháp structured logging phụ thuộc backend và phiên bản thư viện. Điều quan trọng là object event chỉ chứa trường được duyệt, không serialize toàn bộ request hoặc domain entity.

Cần đặc biệt chú ý exception. Stack trace có thể hữu ích nhưng exception message đôi khi chứa JDBC URL, SQL parameter, HTTP URL hoặc response body. Có thể ghi loại exception, mã lỗi và correlation ID; chỉ gửi stack trace đầy đủ vào kho chẩn đoán có quyền truy cập chặt khi thật sự cần. Không nối secret vào exception message.

## 7. Redaction và masking ở nhiều lớp

Redaction là loại bỏ hoặc thay thế dữ liệu nhạy cảm trước khi ghi hoặc trước khi chia sẻ. Có thể triển khai ở nhiều lớp:

1. **Application layer:** không tạo log có trường nhạy cảm ngay từ đầu.
2. **Logging library/appender:** filter hoặc rewrite event trước khi ghi.
3. **Agent/collector:** loại bỏ hoặc thay thế thuộc tính trước khi gửi đi.
4. **Backend ingestion:** áp dụng policy khi nhận dữ liệu.
5. **Report/export layer:** tạo bản chia sẻ đã redacted.
6. **Access layer:** giới hạn người có thể xem dữ liệu thô còn cần giữ.

Ưu tiên xử lý ở nguồn. Nếu ứng dụng ghi secret vào file log local rồi collector mới che, secret vẫn có thể tồn tại trên disk, backup hoặc file được upload trước khi collector xử lý.

Masking như thay một phần email hoặc token bằng dấu sao có thể hữu ích cho hỗ trợ vận hành, nhưng không nên giữ nhiều ký tự hơn mức cần thiết. Với credential, cách an toàn nhất là không ghi bất kỳ phần giá trị nào.

Ví dụ:

~~~text
Authorization: Bearer [REDACTED]
email: u***@example.com
payment_card: [REMOVED]
password: [REMOVED]
~~~

Không sử dụng masking một cách tùy tiện cho mọi trường. Một số giá trị có thể được giả danh hóa bằng HMAC để liên kết sự kiện trong phạm vi kiểm soát, trong khi secret xác thực phải bị loại bỏ hoàn toàn.

## 8. Cẩn trọng với regex redaction

Regex có thể phát hiện một số mẫu như email, token hoặc header, nhưng không thể bảo đảm tìm được mọi dạng dữ liệu nhạy cảm.

Các vấn đề thường gặp:

- Token có định dạng mới không khớp regex.
- Secret bị encode, chia nhỏ hoặc escape.
- JSON có tên trường viết khác nhau.
- Giá trị nằm trong exception hoặc nested object.
- Regex che nhầm dữ liệu hợp lệ, làm mất khả năng điều tra.
- Pattern phức tạp gây tốn CPU hoặc ReDoS nếu xử lý input không tin cậy.

Nếu dùng regex, hãy coi đó là lớp phòng vệ bổ sung. Cần có test với dữ liệu thật đã được giả lập, các biến thể encoding và trường hợp false positive. Không dựa vào một regex duy nhất để chứng minh log không còn secret.

Một cách tốt hơn là kết hợp schema allowlist, field-level policy và redaction filter cho các nguồn dữ liệu khó kiểm soát. Mọi trường mới cần được review trước khi phát hành.

## 9. Bảo vệ trace, span, baggage và metric label

Observability không chỉ có log. Distributed tracing và metrics cũng có thể chứa dữ liệu nhạy cảm.

Với trace:

- Không ghi raw HTTP header, cookie hoặc Authorization.
- Không thêm request/response body vào span mặc định.
- Không đưa email, phone, token hoặc nội dung giao dịch vào span attribute.
- Không dùng URL có query string chứa dữ liệu cá nhân.
- Kiểm soát baggage vì nó có thể được truyền qua nhiều service.
- Giữ trace ID và span ID để nối sự kiện mà không cần payload gốc.

Với metrics:

- Không dùng email, user ID, order ID hoặc token làm label.
- Tránh label có cardinality cao như request path chứa ID động.
- Dùng route template, error class hoặc nhóm trạng thái.
- Không đưa dữ liệu cá nhân vào metric exemplar hoặc annotation.

Ví dụ label không an toàn:

~~~text
http_requests_total{user_email="customer@example.com",order_id="ORD-938271"}
~~~

Ví dụ phù hợp hơn:

~~~text
http_requests_total{route="/payments/{id}",status_class="5xx",region="ap-southeast-1"}
~~~

Metric label có thể được sao chép vào dashboard, alert, time-series storage và hệ thống export. Một trường nhỏ nhưng cardinality cao cũng có thể làm tăng chi phí và giảm hiệu năng backend.

## 10. Kiểm soát dữ liệu ở OpenTelemetry Collector

OpenTelemetry Collector có thể xử lý log, trace và metric trước khi gửi đến backend. Processor cho phép lọc, xóa hoặc biến đổi thuộc tính theo policy. Cấu hình cụ thể phụ thuộc phiên bản Collector và các component được đóng gói.

Ví dụ cấu hình minh họa loại bỏ một số thuộc tính nhạy cảm khỏi span:

~~~yaml
processors:
  attributes/sanitize:
    actions:
      - key: http.request.header.authorization
        action: delete
      - key: http.request.header.cookie
        action: delete
      - key: user.email
        action: delete
      - key: db.statement
        action: delete

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [attributes/sanitize, batch]
      exporters: [otlp]
~~~

Cấu hình chỉ là ví dụ cho tên thuộc tính cụ thể. Semantic convention có thể thay đổi theo instrumentation và phiên bản; cần kiểm tra đúng key thực tế. Processor phải được đặt trong pipeline áp dụng cho mọi đường xuất dữ liệu cần bảo vệ. Nếu có exporter khác gửi trực tiếp, dữ liệu có thể bỏ qua processor này.

Không xem collector là lớp duy nhất bảo vệ dữ liệu. Ứng dụng cần tránh tạo thuộc tính nhạy cảm ngay từ đầu, còn backend cần có access control và retention phù hợp.

## 11. Giới hạn dữ liệu trong CI log và test report

CI report thường được chia sẻ rộng hơn production log vì developer có thể tải xuống trực tiếp từ pull request hoặc build run. Cần xác định loại dữ liệu được phép đi vào report.

Các nguồn cần rà soát:

- JUnit XML và test failure message.
- Surefire/Failsafe report.
- HTML report, coverage report và screenshot.
- Build scan hoặc dependency report.
- Static analysis và secret scan output.
- Docker build output.
- Environment dump và debug trace.
- Artifact được upload sau khi job thất bại.

Không ghi dữ liệu khách hàng thật vào test fixture nếu không cần. Ưu tiên synthetic data hoặc dữ liệu đã được tạo giả lập. Nếu test phải truy cập môi trường dùng chung, hãy dùng tài khoản và dữ liệu thử nghiệm riêng.

Ví dụ GitHub Actions upload report:

~~~yaml
- name: Run tests
  run: ./mvnw --batch-mode verify

- name: Sanitize test reports
  if: ${{ always() }}
  run: ./scripts/redact-test-reports.sh target/surefire-reports

- name: Upload sanitized reports
  if: ${{ always() }}
  uses: actions/upload-artifact@v4
  with:
    name: sanitized-test-reports
    path: target/surefire-reports/
    if-no-files-found: warn
    retention-days: 7
~~~

Script redaction phải xử lý đúng định dạng XML và chỉ upload bản đã được kiểm tra. Không dùng thay thế chuỗi đơn giản có thể làm hỏng XML hoặc bỏ sót dữ liệu lồng nhau. Với report có nguy cơ cao, có thể chỉ upload summary đã lọc thay vì toàn bộ raw output.

Không upload cả thư mục workspace hoặc home directory chỉ để tiện debug. Chọn đường dẫn cụ thể và kiểm tra nội dung trước khi lưu artifact.

## 12. GitHub Actions masking không phải biện pháp duy nhất

GitHub Actions hỗ trợ lưu secret trong cấu hình bảo mật và che một số giá trị khỏi log. Có thể đăng ký giá trị động bằng lệnh add-mask trước khi lệnh có khả năng in giá trị đó chạy.

Ví dụ:

~~~yaml
- name: Use deployment credential
  env:
    DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}
  shell: bash
  run: |
    set +x
    ./scripts/deploy.sh
~~~

Không cần echo token ra output để kiểm tra nó tồn tại. Có thể kiểm tra biến đã được cấp bằng trạng thái boolean hoặc kiểm tra lệnh xác thực trả kết quả thành công.

Nếu cần mask giá trị động:

~~~bash
echo "::add-mask::$VALUE"
~~~

Lệnh này chỉ giúp che giá trị đã đăng ký trong log của nền tảng. Nó không bảo vệ giá trị trong artifact, process arguments, file tạm, trace hoặc hệ thống log bên ngoài. Giá trị đã được encode, biến đổi hoặc chia nhỏ có thể không được nhận diện. Đăng ký mask sau khi secret đã xuất hiện trong log là quá muộn.

Không bật shell tracing khi xử lý secret. Không truyền credential qua URL hoặc tham số dòng lệnh nếu có cách truyền qua environment hoặc file tạm có quyền hạn chế. Hãy kiểm soát mọi step có thể nhận environment chứa secret.

## 13. Bảo vệ artifact và file chẩn đoán

Artifact CI có thể chứa nhiều dữ liệu hơn tên file gợi ý. Một gói build hoặc report có thể vô tình mang theo:

- File .env hoặc application-local.yml.
- Credential cache trong thư mục home.
- Private key hoặc certificate.
- Database dump.
- Test fixture chứa dữ liệu thật.
- Browser storage hoặc cookie.
- Crash dump, heap dump và thread dump.
- File cấu hình đã được render với secret.

Trước khi upload, hãy dùng allowlist đường dẫn và loại bỏ file không cần thiết. Không dùng pattern quá rộng như upload toàn bộ repository hoặc workspace.

Một bước kiểm tra có thể:

- Liệt kê chính xác file sẽ upload.
- Quét secret trên tập file đó.
- Kiểm tra tên và kích thước bất thường.
- Kiểm tra file cấu hình và dump.
- Đảm bảo report đã qua redaction.
- Gắn retention và quyền truy cập phù hợp.

Artifact có thể được tải xuống bởi người có quyền đọc workflow run. Cần xem quyền truy cập artifact tương đương quyền truy cập dữ liệu bên trong, không chỉ quyền xem trạng thái pipeline.

## 14. Giả danh hóa và hash định danh

Đôi khi nhóm cần liên kết nhiều sự kiện của cùng một user hoặc tenant mà không ghi định danh thật. Có thể dùng pseudonymization, ví dụ HMAC với khóa bí mật riêng của hệ thống log.

~~~text
subject_ref = HMAC-SHA256(logging_key, internal_subject_id)
~~~

Cách này cho phép tạo một định danh ổn định trong phạm vi khóa, hỗ trợ correlation mà không đưa ID gốc vào log. Tuy nhiên:

- HMAC không làm dữ liệu trở thành vô danh tuyệt đối.
- Ai có khóa và dữ liệu nguồn vẫn có thể tạo lại mapping.
- Nếu dùng khóa chung ở nhiều hệ thống, khả năng liên kết dữ liệu tăng.
- Khóa HMAC phải được bảo vệ và xoay vòng theo chính sách.
- Không dùng hash thường cho email hoặc số điện thoại có không gian giá trị nhỏ; kẻ khác có thể dò từ điển.

Nếu chỉ cần phân nhóm, có thể dùng bucket hoặc cohort thay cho định danh từng cá nhân. Nếu cần liên kết trong thời gian ngắn, có thể dùng pseudonym có thời hạn hoặc khóa theo môi trường.

## 15. Phân quyền xem log, report và telemetry

Redaction không loại bỏ nhu cầu kiểm soát truy cập. Một số dữ liệu vận hành vẫn nhạy cảm dù đã loại bỏ secret.

Nên áp dụng:

- Role-based access control theo nhóm và môi trường.
- Tách quyền xem log production khỏi quyền xem CI report thông thường.
- Hạn chế quyền export và download.
- Audit thao tác tìm kiếm, truy cập và tải dữ liệu nhạy cảm.
- Cấp quyền tạm thời khi cần điều tra.
- Break-glass access có lý do, thời hạn và audit.
- Tách dữ liệu raw restricted khỏi dữ liệu đã redacted dùng cho nhóm rộng hơn.

Không nên cho mọi developer quyền truy cập mọi log production chỉ vì họ cần debug. Có thể cung cấp dashboard đã tổng hợp, correlation ID và quy trình yêu cầu truy cập dữ liệu chi tiết khi cần.

Quyền đọc artifact CI cũng cần được xem xét. Một report được tạo trong pull request có thể chứa dữ liệu nhạy cảm do test thất bại. Không nên giả định mọi contributor hoặc fork đều có quyền xem mọi artifact.

## 16. Retention, xóa và vị trí lưu trữ

Dữ liệu không nên được giữ vô thời hạn chỉ vì storage rẻ. Retention cần phù hợp với mục đích, nghĩa vụ pháp lý và khả năng điều tra.

Cần định nghĩa riêng cho từng loại:

| Dữ liệu | Retention cần xem xét |
|---|---|
| Debug log ngắn hạn | Đủ để điều tra lỗi gần thời điểm phát sinh |
| Audit/security event | Theo chính sách kiểm toán và bảo mật |
| CI test report | Theo thời gian review và sửa lỗi |
| Build artifact | Theo vòng đời release và nhu cầu rollback |
| Trace chi tiết | Có thể ngắn hơn metric tổng hợp do dung lượng và dữ liệu nhạy cảm |
| Crash/heap dump | Rất hạn chế, quyền truy cập chặt và xóa theo thời hạn |
| Raw request sample | Chỉ khi có mục đích rõ và được phép |

Xóa khỏi dashboard không có nghĩa dữ liệu đã bị xóa khỏi backend, archive, backup hoặc bản export. Chính sách cần mô tả thời gian xóa ở từng lớp và cách xử lý bản sao.

Nếu dữ liệu được lưu ở nhiều khu vực hoặc nhà cung cấp, cần xác định vị trí lưu, quyền truy cập xuyên biên giới và yêu cầu của tổ chức. Không tự ý chuyển log có dữ liệu cá nhân sang dịch vụ ngoài phạm vi được phê duyệt.

## 17. Phát hiện và ứng phó khi dữ liệu nhạy cảm bị ghi nhầm

Cần có quy trình khi secret hoặc dữ liệu nhạy cảm xuất hiện trong log/report:

1. Xác định loại dữ liệu, thời gian, pipeline run và nơi lưu.
2. Giới hạn quyền truy cập hoặc gỡ artifact khỏi phạm vi chia sẻ theo quy trình.
3. Nếu là credential, thu hồi hoặc xoay vòng ngay theo mức độ rủi ro.
4. Tìm các bản sao trong log backend, artifact, cache, export và backup.
5. Xác định ai đã truy cập hoặc tải dữ liệu nếu audit có sẵn.
6. Xóa hoặc hạn chế bản sao theo chính sách lưu trữ và ứng phó sự cố.
7. Sửa nguồn log hoặc report gây rò rỉ.
8. Thêm test để ngăn lỗi lặp lại.
9. Ghi nhận incident và bằng chứng xử lý.

Không sửa log gốc theo cách làm mất dấu vết điều tra nếu chính sách yêu cầu bảo toàn bằng chứng. Có thể hạn chế truy cập bản gốc và tạo bản redacted phục vụ người dùng rộng hơn. Với credential đã lộ, xóa bản ghi không thay thế việc thu hồi credential.

## 18. Kiểm thử policy chống rò rỉ

Logging policy cần được kiểm thử giống code. Có thể tạo dữ liệu canary giả lập để xác minh secret không xuất hiện trong log hoặc report.

Ví dụ test:

~~~java
@Test
void doesNotLogAuthorizationToken() {
    String fakeToken = "test-token-never-use-in-production";

    String output = captureLogs(() -> {
        paymentClient.callWithAuthorization(fakeToken);
    });

    assertThat(output).doesNotContain(fakeToken);
}
~~~

Test này chỉ là minh họa. Nếu thiết kế tốt, ứng dụng không nên đưa token vào log ngay từ đầu; không cần yêu cầu mọi log phải chứa literal [REDACTED]. Điều quan trọng là secret không xuất hiện ở bất kỳ sink nào được kiểm tra.

Có thể kiểm thử thêm:

- Password trong exception message.
- Cookie và Authorization header.
- URL có query parameter nhạy cảm.
- Request body và SQL bind parameter.
- Nested JSON/XML field.
- Stack trace và test assertion.
- OpenTelemetry span attribute và baggage.
- JUnit XML, HTML report và artifact ZIP.
- Giá trị đã encode hoặc biến đổi phổ biến.
- Quyền tải artifact từ workflow khác.

Secret scanner giúp phát hiện một số mẫu, nhưng không thay thế schema review và kiểm thử đầu ra. Dữ liệu test nên dùng token giả có mẫu dễ nhận diện, không dùng credential thật làm canary.

## 19. Thiết kế luồng bằng chứng an toàn cho CI/CD

Một luồng có thể tổ chức như sau:

~~~mermaid
flowchart TD
    A[Ứng dụng và pipeline tạo sự kiện] --> B[Schema allowlist tại nguồn]
    B --> C[Redaction và data minimization]
    C --> D[Collector validation]
    D --> E[Log/trace/metric backend]
    E --> F[Access control và audit]
    F --> G[Dashboard hoặc report đã lọc]
    E --> H[Retention và deletion policy]
    C --> I[Secret/data leak scanning]
    I --> J{Có dữ liệu bị cấm?}
    J -- Có --> K[Chặn export và xử lý incident]
    J -- Không --> D
~~~

Các điểm kiểm soát:

- Ứng dụng chỉ tạo trường đã được duyệt.
- Collector loại bỏ thuộc tính nhạy cảm còn sót.
- Scanner kiểm tra report/artifact trước khi chia sẻ.
- Backend giới hạn quyền và ghi audit.
- Dashboard hiển thị dữ liệu đã tổng hợp hoặc redacted.
- Retention policy xử lý log, artifact và bản sao.
- Khi phát hiện rò rỉ, quy trình incident có thể thu hồi credential và hạn chế truy cập.

Nếu dữ liệu đã bị ghi vào raw log trước khi collector lọc, cần kiểm soát cả vị trí lưu raw log. Đừng chỉ cấu hình dashboard để ẩn trường nhạy cảm trong khi dữ liệu vẫn truy cập được qua API hoặc export.

## 20. Checklist giới hạn dữ liệu nhạy cảm trong báo cáo và nhật ký

Trước khi đưa pipeline hoặc dịch vụ vào vận hành, hãy kiểm tra:

- [ ] Đã phân loại dữ liệu công khai, nội bộ, nhạy cảm và bí mật xác thực.
- [ ] Log schema dùng allowlist và có owner review.
- [ ] Không ghi password, token, cookie, private key hoặc Authorization header.
- [ ] Không ghi toàn bộ request/response body theo mặc định.
- [ ] Exception và stack trace được kiểm tra nguy cơ chứa dữ liệu nhạy cảm.
- [ ] Log ứng dụng Java chỉ ghi trường đã chọn, không serialize object tùy ý.
- [ ] Redaction được thực hiện ở nguồn và có lớp lọc bổ sung.
- [ ] Regex không phải biện pháp duy nhất để phát hiện dữ liệu nhạy cảm.
- [ ] Trace, span, baggage và metric label không chứa dữ liệu cá nhân không cần thiết.
- [ ] Test report và artifact được sanitize trước khi upload.
- [ ] CI chỉ upload file theo allowlist, không upload toàn bộ workspace.
- [ ] Secret masking không bị xem là thay thế cho việc ngăn secret đi vào log.
- [ ] Pseudonymization dùng HMAC/khóa phù hợp khi cần liên kết sự kiện.
- [ ] Quyền đọc, export và download được giới hạn và audit.
- [ ] Retention và deletion áp dụng cho backend, archive, artifact và backup.
- [ ] Có quy trình xử lý khi secret hoặc dữ liệu nhạy cảm bị lộ.
- [ ] Có test canary để kiểm tra log, trace và report không chứa secret.

Bằng chứng CI/CD cần giúp nhóm hiểu điều gì đã xảy ra mà không thu thập nhiều dữ liệu hơn mức cần thiết. Khi schema log được kiểm soát, secret bị loại khỏi nguồn, trace và report được lọc, còn quyền truy cập và retention được giới hạn, nhóm vẫn có thể truy vết release bằng commit, artifact digest, run ID và correlation ID mà không phải phát tán credential hoặc dữ liệu người dùng.

