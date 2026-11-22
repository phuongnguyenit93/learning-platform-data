# Lưu báo cáo đủ để xác định lỗi mà không chỉ nhìn trạng thái đỏ

Một pipeline hiển thị màu đỏ chỉ cho biết một bước không hoàn tất theo điều kiện đã đặt. Nó chưa trả lời được câu hỏi quan trọng hơn: **điều gì đã thất bại, xảy ra ở đâu, với đầu vào nào, do lỗi sản phẩm hay do môi trường, và cần bằng chứng gì để tái hiện?**

Nếu CI chỉ lưu trạng thái pass/fail rồi xóa log khi job kết thúc, người phát triển phải chạy lại pipeline hoặc đoán nguyên nhân. Điều đó làm chậm việc sửa lỗi và có thể khiến lỗi thoáng qua biến mất trước khi được điều tra. Một chiến lược kiểm thử tốt cần coi báo cáo, log và metadata là đầu ra chính thức của mỗi lần chạy. Những đầu ra này phải đủ chi tiết để xác định lỗi, liên kết với commit và môi trường, đồng thời được thu thập ngay cả khi test thất bại.

## 1. Trạng thái kiểm thử và bằng chứng chẩn đoán

Trạng thái là kết luận tổng hợp của một job hoặc pipeline. Bằng chứng chẩn đoán là dữ liệu giải thích vì sao có kết luận đó.

| Thông tin | Trả lời câu hỏi nào? | Ví dụ |
|---|---|---|
| Pipeline status | Lần chạy có đạt điều kiện không? | success, failure, cancelled |
| Test summary | Có bao nhiêu test được chạy và kết quả ra sao? | 240 passed, 2 failed, 3 skipped |
| Test report | Test case cụ thể nào lỗi? | tên suite, tên test, assertion, stack trace |
| Build log | Lệnh nào và giai đoạn nào thất bại? | Maven test, compiler, dependency resolution |
| Environment metadata | Lỗi xuất hiện trong môi trường nào? | JDK 21, Linux x64, profile integration |
| Runtime evidence | Hệ thống phụ trợ hoạt động ra sao? | service log, database log, container status |
| Trace hoặc correlation ID | Request lỗi đi qua thành phần nào? | trace ID, request ID |
| Source/artifact identity | Lỗi gắn với phiên bản mã và sản phẩm nào? | commit SHA, pipeline run ID, artifact digest |

Một báo cáo tốt cần trả lời được ít nhất năm câu hỏi:

1. **Điều gì thất bại?** Tên test, bước chạy, assertion hoặc thao tác cụ thể.
2. **Thất bại ở đâu và khi nào?** Suite, job, môi trường, thời điểm và thời lượng.
3. **Đầu vào nào được dùng?** Commit, cấu hình, dependency, dữ liệu test và artifact.
4. **Có thể tái hiện không?** Lệnh chạy, seed ngẫu nhiên, phiên bản dịch vụ và điều kiện môi trường.
5. **Bằng chứng nằm ở đâu?** Báo cáo máy đọc, log, trace, screenshot hoặc artifact liên quan.

Không nên buộc người điều tra suy ra tất cả thông tin từ một log dài. Hãy tạo một bản tóm tắt dễ đọc, kèm báo cáo có cấu trúc và liên kết đến bằng chứng chi tiết.

## 2. Thiết kế hợp đồng đầu ra cho mỗi giai đoạn kiểm thử

Mỗi job kiểm thử nên công bố đầu vào, kết quả và bằng chứng theo một hợp đồng thống nhất.

| Thành phần | Nội dung cần lưu |
|---|---|
| Identity | Repository, commit SHA, pipeline run ID, job ID, attempt |
| Test scope | Suite, module, loại test, profile hoặc tag được chọn |
| Environment | OS, architecture, runtime, toolchain, container image |
| Dependencies | Lockfile hash, dependency version, service image version |
| Execution | Lệnh chạy, thời điểm bắt đầu/kết thúc, thời lượng, timeout |
| Result | Tổng test, pass, fail, error, skipped, aborted |
| Failure detail | Test case, expected/actual, exception, stack trace |
| Supporting evidence | Log, dump, trace, screenshot, service status |
| Classification | Product defect, test defect, infrastructure, configuration hoặc flaky |
| Retention | Nơi lưu, quyền truy cập và thời hạn lưu |

Không phải mọi job đều tạo ra cùng loại báo cáo. Unit test thường cần JUnit XML hoặc định dạng tương đương; browser test có thể cần screenshot và video; integration test có thể cần log database hoặc message broker. Tuy vậy, các job nên dùng chung cách đặt tên, metadata và nơi lưu để người điều tra không phải học một quy trình mới cho từng module.

Ví dụ một cây thư mục bằng chứng:

~~~text
test-diagnostics/
├── summary/
│   ├── test-summary.md
│   └── run-metadata.json
├── reports/
│   ├── surefire/
│   ├── failsafe/
│   └── coverage/
├── logs/
│   ├── application.log
│   └── test-runner.log
└── attachments/
    ├── screenshots/
    └── thread-dumps/
~~~

Đây là cấu trúc tham khảo. Không cần tạo file rỗng cho loại bằng chứng không áp dụng. Điều quan trọng là báo cáo phải chỉ ra dữ liệu nào được tạo, dữ liệu nào không có và lý do không có.

## 3. Dùng định dạng báo cáo máy có thể đọc

Log văn bản hữu ích cho con người nhưng khó tổng hợp chính xác qua nhiều job. Báo cáo có cấu trúc cho phép CI hiển thị test case lỗi, đếm kết quả, so sánh lịch sử và tạo cảnh báo.

Các định dạng thường gặp:

| Định dạng | Công dụng | Ví dụ hệ sinh thái |
|---|---|---|
| JUnit XML | Kết quả test suite và test case | JUnit, TestNG, Maven Surefire/Failsafe, nhiều framework khác |
| TRX | Kết quả test của hệ sinh thái Microsoft | dotnet test, Visual Studio Test |
| JSON report | Kết quả có cấu trúc và metadata mở rộng | Playwright, custom test runner |
| HTML report | Báo cáo tương tác cho người điều tra | Allure, Playwright HTML |
| LCOV/Cobertura/Jacoco XML | Dữ liệu coverage | Java, JavaScript và các công cụ coverage |
| SARIF | Kết quả phân tích tĩnh hoặc bảo mật | Code scanning, static analysis |

Ví dụ JUnit XML tối giản:

~~~xml
<testsuite name="OrderServiceTest"
           tests="3"
           failures="1"
           errors="0"
           skipped="1"
           time="2.41">
  <testcase name="createsOrder" classname="OrderServiceTest" time="0.82"/>
  <testcase name="rejectsInvalidAddress" classname="OrderServiceTest" time="0.21">
    <failure message="expected 400 but was 500">
      AssertionError: expected status 400, actual 500
      at OrderServiceTest.rejectsInvalidAddress(OrderServiceTest.java:84)
    </failure>
  </testcase>
  <testcase name="handlesUnavailablePayment" classname="OrderServiceTest" time="0">
    <skipped message="requires payment sandbox"/>
  </testcase>
</testsuite>
~~~

Từ báo cáo này, hệ thống có thể xác định suite có ba test, một test thất bại, một test bị bỏ qua và lỗi cụ thể nằm ở assertion nào. Một dòng trạng thái đỏ không thể cung cấp mức chi tiết đó.

Cần phân biệt `failures` và `errors` theo quy ước của framework. Failure thường là assertion không đạt; error thường là exception hoặc lỗi thực thi ngoài assertion. Cách phân loại chính xác phụ thuộc công cụ tạo báo cáo, vì vậy hãy giữ nguyên report gốc và tránh tự suy diễn từ chuỗi log.

## 4. Ghi lại ngữ cảnh để tái hiện lỗi

Một test case lỗi có thể phụ thuộc vào phiên bản runtime, hệ điều hành, cấu hình, dữ liệu hoặc dịch vụ bên ngoài. Chỉ lưu tên test là chưa đủ.

Các metadata nên gắn với mỗi lần chạy:

- Repository và commit SHA chính xác.
- Nhánh, tag hoặc pull request; loại event kích hoạt.
- Pipeline run ID, job ID và attempt number.
- Phiên bản workflow hoặc pipeline definition nếu khác commit mã nguồn.
- Runner image, OS, architecture và phiên bản runtime.
- Phiên bản compiler, package manager và công cụ test.
- Dependency lockfile hash hoặc dependency graph snapshot khi phù hợp.
- Profile, feature flag và biến cấu hình không nhạy cảm.
- Phiên bản image của database, broker và service phụ trợ.
- Test suite, test filter và lệnh chạy.
- Test data fixture hoặc random seed nếu test có tính ngẫu nhiên.
- Thời điểm, timezone, thời lượng, timeout và số lần retry.
- Artifact digest nếu test chạy trên một sản phẩm đã đóng gói.

Ví dụ metadata JSON:

~~~json
{
  "repository": "example/order-service",
  "commit": "a1b2c3d4",
  "pipelineRunId": "8421",
  "job": "integration-test",
  "attempt": 1,
  "runner": {
    "os": "linux",
    "architecture": "x64",
    "image": "ubuntu-24.04"
  },
  "runtime": {
    "java": "21",
    "maven": "3.9"
  },
  "test": {
    "suite": "integration",
    "profile": "ci",
    "seed": 91827
  },
  "services": {
    "postgres": "16",
    "redis": "7"
  }
}
~~~

Đây là ví dụ minh họa. Giá trị cần lấy từ môi trường thực tế của job. Không ghi token, password, connection string có credential hoặc toàn bộ environment variables vào metadata. Nếu cấu hình có chứa bí mật, chỉ ghi tên cấu hình hoặc phiên bản tham chiếu.

Với test ngẫu nhiên, seed giúp chạy lại cùng chuỗi dữ liệu. Với test phụ thuộc thời gian, hãy ghi timestamp và timezone. Với test phân tán, cần thêm trace ID hoặc correlation ID để nối log từ nhiều dịch vụ.

## 5. Thu thập báo cáo ngay cả khi test thất bại

Một lỗi phổ biến là chỉ upload report sau khi test thành công. Khi test fail, job dừng sớm và bằng chứng quan trọng bị bỏ lại trong runner đã bị hủy.

Cần thiết kế bước thu thập báo cáo chạy theo điều kiện phù hợp với nền tảng. Trong GitHub Actions, `if: always()` có thể dùng để upload báo cáo sau khi các bước trước thành công, thất bại hoặc bị bỏ qua, miễn là job còn thực thi được bước đó.

Ví dụ cho dự án Java Maven:

~~~yaml
name: Java test diagnostics

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 25

    steps:
      - uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Run verification
        run: ./mvnw --batch-mode verify

      - name: Upload test diagnostics
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: test-diagnostics-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            **/target/surefire-reports/**
            **/target/failsafe-reports/**
            **/target/site/jacoco/**
            logs/test/**
          if-no-files-found: warn
          retention-days: 14
~~~

Maven Surefire thường ghi báo cáo unit test trong `target/surefire-reports`; Maven Failsafe thường ghi báo cáo integration test trong `target/failsafe-reports`. Đường dẫn thực tế có thể thay đổi theo module hoặc cấu hình plugin. Nếu một job thất bại trước khi test chạy, không có report là tình huống có thể xảy ra; `if-no-files-found: warn` giúp phân biệt thiếu file với lỗi upload.

Bước upload nên nằm sau các bước tạo bằng chứng và có điều kiện chạy khi thất bại. Nếu runner bị mất đột ngột, bị hủy cưỡng bức hoặc nền tảng gặp sự cố, bước này vẫn có thể không chạy. Với hệ thống quan trọng, cân nhắc đẩy log liên tục đến log store hoặc observability platform để giảm phụ thuộc vào bước cuối job.

Không nên dùng điều kiện `success()` cho bước upload chẩn đoán nếu mục tiêu là giữ bằng chứng khi test fail. Cũng không dùng `always()` một cách thiếu chọn lọc cho tác vụ có quyền cao hoặc có tác dụng phụ; chỉ áp dụng cho việc thu thập và lưu bằng chứng cần thiết.

## 6. Kết hợp summary, report và log

Mỗi loại bằng chứng phục vụ một mục đích khác nhau:

- **Summary:** giúp người đọc hiểu nhanh số lượng test, test lỗi và liên kết đến báo cáo.
- **Structured report:** cho biết chính xác test case, trạng thái, assertion và stack trace.
- **Execution log:** thể hiện thứ tự sự kiện, lệnh đã chạy, thời điểm và thông tin runtime.
- **Service log:** giải thích hành vi của database, broker, API hoặc container phụ trợ.
- **Trace và correlation ID:** nối một request qua nhiều dịch vụ.
- **Attachment:** screenshot, video, heap dump hoặc thread dump khi loại test cần.

Một summary nên đặt thông tin quan trọng lên đầu:

~~~text
Test result: FAILED
Commit: a1b2c3d4
Run: 8421 / attempt 1
Suite: integration
Duration: 06m 18s

Tests: 240
Passed: 237
Failed: 2
Errors: 0
Skipped: 1

Failed cases:
- OrderServiceTest.rejectsInvalidAddress
  Expected HTTP 400, actual HTTP 500
- PaymentFlowTest.retriesAfterGatewayTimeout
  Timed out waiting for payment status

Evidence:
- JUnit XML: test-diagnostics/reports/failsafe/
- Application log: test-diagnostics/logs/application.log
- Run metadata: test-diagnostics/summary/run-metadata.json
~~~

Summary không thay thế báo cáo gốc. Nó là điểm bắt đầu để người điều tra biết nên mở file nào trước. Nên giữ summary ngắn, không chép toàn bộ stack trace vào phần hiển thị của pull request.

## 7. Thu thập log đủ ngữ cảnh mà không tạo nhiễu

Log quá ít không giải thích được lỗi; log quá nhiều làm người điều tra khó tìm tín hiệu và tăng chi phí lưu trữ.

Một log hữu ích thường có:

- Timestamp nhất quán, tốt nhất theo UTC hoặc có timezone rõ ràng.
- Mức độ log như DEBUG, INFO, WARN, ERROR.
- Tên service, module, test suite và test case.
- Run ID, job ID, attempt và correlation ID.
- Thông điệp mô tả sự kiện hoặc lỗi.
- Exception type và stack trace khi có lỗi.
- Thời lượng của thao tác quan trọng.
- Trạng thái dependency hoặc service phụ trợ tại thời điểm lỗi.

Ví dụ log có cấu trúc:

~~~json
{
  "timestamp": "2026-11-18T08:30:12.420Z",
  "level": "ERROR",
  "service": "order-service",
  "test": "PaymentFlowTest.retriesAfterGatewayTimeout",
  "runId": "8421",
  "correlationId": "req-7f31",
  "event": "payment_status_timeout",
  "elapsedMs": 15000,
  "dependency": "payment-sandbox"
}
~~~

Không nên log chỉ một thông điệp như `test failed`. Cũng không nên bật DEBUG cho toàn bộ hệ thống trong mọi pipeline nếu log rất lớn. Có thể dùng mức INFO mặc định và bật DEBUG có giới hạn cho module hoặc test cần điều tra.

Khi một request đi qua nhiều service, correlation ID giúp tìm tất cả log liên quan. Với hệ thống hỗ trợ distributed tracing, lưu trace ID và liên kết đến trace tương ứng. Không tự tạo correlation ID mới ở mỗi service nếu cần nối cùng một luồng request.

## 8. Chụp bằng chứng phù hợp với từng loại test

Không phải mọi loại test đều cần cùng một bộ bằng chứng.

| Loại test | Bằng chứng nên lưu |
|---|---|
| Unit test | JUnit XML, stack trace, test output |
| Integration test | JUnit XML, application log, service/container log, trạng thái dependency |
| API test | Request/response đã loại bỏ dữ liệu nhạy cảm, status code, latency, correlation ID |
| Browser E2E | Screenshot khi lỗi, video hoặc trace, console log, network failure |
| Performance test | Kết quả throughput, latency percentile, error rate, load profile |
| Contract test | Báo cáo contract mismatch, schema/version, provider/consumer |
| Smoke test sau deploy | Deployment revision, endpoint, response, health check và thời điểm xác minh |
| Static analysis | SARIF hoặc report tương ứng, rule ID, file và dòng mã |

Đối với browser test, screenshot nên được chụp khi test fail và gắn với tên test, thời điểm cùng run ID. Video hoặc trace có thể giúp tìm race condition nhưng chiếm nhiều dung lượng; chỉ bật cho suite cần thiết hoặc khi retry thất bại.

Đối với performance test, không chỉ lưu một kết luận pass/fail. Cần lưu cấu hình tải, số virtual users, thời lượng warm-up, thời gian đo, dữ liệu đầu vào, latency p50/p95/p99, throughput và tỷ lệ lỗi. Nếu không có cấu hình tải, hai báo cáo hiệu năng có thể không so sánh được.

Đối với smoke test sau deploy, ghi deployment revision và artifact digest để biết chính xác phiên bản nào được kiểm tra. Một kết quả health check không có liên kết đến revision sẽ khó dùng khi điều tra phát hành.

## 9. Phân loại lỗi để chọn hướng xử lý

Không phải mọi test fail đều là lỗi của ứng dụng. Một chiến lược báo cáo nên phân biệt nguyên nhân dựa trên bằng chứng.

| Nhóm lỗi | Dấu hiệu thường gặp | Hướng điều tra |
|---|---|---|
| Product defect | Assertion phản ánh hành vi sai, tái hiện ổn định | Kiểm tra mã, yêu cầu và thay đổi gần nhất |
| Test defect | Test setup sai, assertion lỗi, fixture không hợp lệ | Kiểm tra test code, dữ liệu và giả định |
| Environment/configuration | Thiếu biến, sai profile, sai quyền hoặc endpoint | So sánh cấu hình và metadata môi trường |
| Infrastructure | Runner mất kết nối, service unavailable, disk đầy | Kiểm tra runner, mạng và dịch vụ phụ thuộc |
| Timeout/resource | OOM, CPU throttling, pool cạn, deadline hết | Kiểm tra ngân sách tài nguyên và concurrency |
| Flaky test | Cùng commit và điều kiện nhưng kết quả không ổn định | Lưu attempt, seed, thời gian và trace |
| Dependency failure | Registry lỗi, package bị thu hồi hoặc không resolve được | Kiểm tra dependency graph, repository và cache |

Không tự động gán mọi lỗi timeout thành lỗi hạ tầng. Một endpoint chậm có thể là regression của ứng dụng. Cần xem thời điểm, trace, log service và lịch sử để xác định nguyên nhân.

Nếu chưa đủ bằng chứng, ghi nhận là chưa phân loại hoặc cần điều tra. Một nhãn nguyên nhân sai có thể khiến nhóm bỏ qua lỗi sản phẩm hoặc mất thời gian xử lý nhầm thành phần.

## 10. Xử lý flaky test và lưu lịch sử các lần thử

Flaky test là test có thể pass hoặc fail trong các lần chạy khác nhau dù mã nguồn và điều kiện đầu vào tưởng như không đổi. Nguyên nhân có thể đến từ race condition, phụ thuộc thời gian, test dùng chung dữ liệu, thứ tự chạy, network hoặc tài nguyên không ổn định.

Khi có retry, cần lưu kết quả từng attempt:

| Attempt | Kết quả | Thời gian | Seed/Context | Ghi chú |
|---|---|---:|---|---|
| 1 | Failed | 4m 12s | seed 91827 | Timeout chờ event |
| 2 | Passed | 3m 58s | seed 91827 | Retry thành công |

Không nên chỉ ghi trạng thái cuối cùng là passed. Nếu attempt đầu fail nhưng retry pass, cần thể hiện rõ test đã không ổn định. Retry có thể giúp giảm gián đoạn tạm thời, nhưng không chứng minh test đáng tin cậy.

Một chính sách phù hợp có thể:

- Giới hạn số lần retry.
- Giữ report và log của mọi attempt.
- Đánh dấu test flaky khi có mẫu hình lặp lại.
- Theo dõi tỷ lệ flaky theo test, module và thời gian.
- Tạo công việc sửa test thay vì bỏ qua vô thời hạn.
- Không để retry che khuất lỗi nghiêm trọng hoặc làm thay đổi dữ liệu production.

Nếu dùng quarantine cho test flaky, cần có người sở hữu, lý do, thời hạn xem xét và phạm vi ảnh hưởng. Test bị quarantine không nên biến mất khỏi báo cáo tổng hợp.

## 11. Coverage và chất lượng cần đi cùng ngữ cảnh

Coverage giúp hiểu mã nào đã được thực thi trong một lần kiểm thử, nhưng một con số phần trăm không giải thích test có kiểm tra đúng hành vi hay không.

Báo cáo coverage nên ghi:

- Công cụ và phiên bản tạo report.
- Commit SHA và test suite đã chạy.
- Line coverage, branch coverage hoặc metric mà dự án sử dụng.
- Module/package được đo.
- File hoặc vùng mã thay đổi chưa được bao phủ nếu có.
- Ngưỡng policy và kết quả so sánh.

Ví dụ, coverage giảm từ 82% xuống 78% có thể do thêm mã mới chưa có test, nhưng cũng có thể do thay đổi phạm vi đo hoặc bỏ qua một suite. Cần xem report theo module và diff thay đổi để hiểu ý nghĩa.

Báo cáo static analysis hoặc security scan cũng cần giữ rule ID, severity, file, dòng mã, công cụ và phiên bản rule set. Chỉ lưu số lượng issue hoặc trạng thái đỏ không đủ để người phát triển tìm vị trí cần sửa.

## 12. Bảo vệ dữ liệu trong báo cáo và artifact

Báo cáo kiểm thử có thể chứa dữ liệu nhạy cảm: access token, password, connection string, dữ liệu người dùng, email, request body hoặc thông tin nội bộ. Thu thập nhiều bằng chứng hơn không đồng nghĩa với việc lưu tất cả dữ liệu thô.

Các nguyên tắc cần áp dụng:

1. **Redact trước khi lưu:** loại bỏ token, password, cookie, authorization header và dữ liệu nhạy cảm khỏi log hoặc request/response.
2. **Không dump toàn bộ environment:** chỉ ghi các biến không nhạy cảm cần cho chẩn đoán.
3. **Dùng dữ liệu giả lập:** ưu tiên fixture và dữ liệu test tổng hợp thay cho dữ liệu production.
4. **Giới hạn quyền đọc:** artifact chứa log hoặc screenshot chỉ cho nhóm có nhu cầu.
5. **Đặt retention:** lưu đủ thời gian điều tra và kiểm toán, sau đó xóa theo chính sách.
6. **Kiểm soát chia sẻ:** không đính kèm log nội bộ hoặc dữ liệu khách hàng vào pull request công khai.
7. **Kiểm tra artifact trước upload:** không đưa file cấu hình hoặc credential vào thư mục report.

Nếu phát hiện secret trong log, cần xử lý như một sự cố lộ bí mật: thu hồi hoặc xoay vòng credential, giới hạn quyền truy cập artifact và xóa bản sao theo quy trình. Chỉ xóa dòng log khỏi giao diện không đảm bảo mọi bản lưu đã biến mất.

## 13. Retention và khả năng truy xuất bằng chứng

Báo cáo cần tồn tại đủ lâu để điều tra nhưng không nên giữ vô thời hạn nếu không có lý do. Chính sách retention có thể phân biệt theo loại pipeline:

| Loại lần chạy | Chính sách lưu tham khảo |
|---|---|
| Pull request thông thường | Thời hạn ngắn, đủ cho review và sửa lỗi |
| Build nhánh chính | Lưu lâu hơn để so sánh regression |
| Release candidate | Giữ report cùng artifact và approval |
| Production release | Theo yêu cầu kiểm toán và chính sách tổ chức |
| Security incident | Giữ theo quy trình điều tra sự cố |
| Performance baseline | Giữ dữ liệu lịch sử để so sánh xu hướng |

Thời hạn cụ thể phụ thuộc dung lượng, quy định và yêu cầu vận hành. Nên đặt tên artifact có thể truy ra run ID và attempt, ví dụ `test-diagnostics-8421-1`. Metadata bên trong vẫn cần chứa commit SHA và job ID để không phụ thuộc vào tên file.

Cần kiểm tra rằng artifact upload thành công và có thể tải xuống. Một bước upload có trạng thái xanh nhưng không chứa report cần thiết vẫn chưa đáp ứng mục tiêu. Nên ghi số file hoặc danh sách report đã thu thập, đồng thời cảnh báo khi một loại report bắt buộc bị thiếu.

## 14. Quy trình điều tra từ một pipeline đỏ

Khi pipeline fail, có thể dùng trình tự sau để giảm thời gian tìm nguyên nhân:

1. **Đọc summary:** xác định job, suite và test case lỗi đầu tiên; xem số test pass/fail/skip.
2. **Kiểm tra identity:** xác nhận commit SHA, run ID, attempt và artifact digest.
3. **Mở report có cấu trúc:** xem assertion, exception, stack trace và test duration.
4. **Đọc log quanh thời điểm lỗi:** đối chiếu test log với application và service log.
5. **Kiểm tra môi trường:** so sánh runtime, dependency, profile, service image và tài nguyên với lần chạy thành công gần nhất.
6. **Xác định nhóm nguyên nhân:** product, test, environment, infrastructure, resource, dependency hoặc flaky.
7. **Tái hiện có kiểm soát:** dùng đúng commit, test filter, seed và cấu hình có thể tái tạo.
8. **Ghi nhận kết luận:** liên kết issue hoặc pull request sửa lỗi với run và report gốc.

Không nên chỉ rerun toàn bộ pipeline nhiều lần mà không lưu kết quả từng lần. Việc đó có thể làm mất dấu hiệu lỗi ban đầu, nhất là lỗi race condition hoặc lỗi phụ thuộc tải.

## 15. Ví dụ: cấu trúc báo cáo cho một lần kiểm thử

Một lần chạy integration test của dịch vụ đặt hàng có thể tạo ra:

~~~text
run-8421/
├── summary/
│   ├── test-summary.md
│   └── run-metadata.json
├── reports/
│   ├── surefire/
│   │   └── TEST-OrderServiceTest.xml
│   └── failsafe/
│       └── TEST-PaymentFlowTest.xml
├── logs/
│   ├── test-runner.log
│   ├── order-service.log
│   └── postgres.log
└── traces/
    └── req-7f31.json
~~~

Giả sử `PaymentFlowTest.retriesAfterGatewayTimeout` thất bại. Summary chỉ ra test case và thời lượng. Failsafe XML ghi exception cùng stack trace. Test runner log cho biết test đã chờ 15 giây. Application log có correlation ID `req-7f31`; trace cho thấy request bị chậm ở payment sandbox. Metadata cho biết test chạy trên commit nào, JDK nào, service image nào và seed nào.

Từ các bằng chứng đó, nhóm có thể xác định bước chậm nằm ở dịch vụ phụ thuộc hay ở logic retry của ứng dụng. Nếu chỉ có trạng thái đỏ, nhóm sẽ phải chạy lại test và đoán thời điểm lỗi.

## 16. Checklist thiết kế báo cáo kiểm thử

Trước khi đưa chiến lược báo cáo vào pipeline, hãy kiểm tra:

- [ ] Mỗi job kiểm thử tạo summary dễ đọc và report có cấu trúc.
- [ ] Báo cáo thể hiện tổng test, pass, fail, error, skipped và duration.
- [ ] Test case lỗi có tên, assertion hoặc exception và stack trace.
- [ ] Có commit SHA, run ID, job ID và attempt number.
- [ ] Có OS, architecture, runtime, toolchain và cấu hình test cần thiết.
- [ ] Dependency và phiên bản dịch vụ phụ trợ có thể xác định.
- [ ] Test ngẫu nhiên lưu seed; test phân tán lưu correlation/trace ID khi cần.
- [ ] Report và log được upload ngay cả khi test thất bại.
- [ ] Thiếu report bắt buộc được cảnh báo rõ ràng.
- [ ] Retry giữ lại bằng chứng của mọi attempt và không che flaky test.
- [ ] Screenshot, trace, dump hoặc service log được thu thập theo loại test.
- [ ] Secret và dữ liệu nhạy cảm được redact trước khi lưu.
- [ ] Artifact có quyền truy cập và retention phù hợp.
- [ ] Có thể tải lại report và lần từ report về đúng commit, job và artifact.
- [ ] Quy trình điều tra có bước phân loại nguyên nhân và ghi nhận kết luận.

Một pipeline kiểm thử trưởng thành phải giải thích được lý do của trạng thái cuối cùng bằng bằng chứng có thể kiểm tra. Khi summary, report, log và metadata được lưu cùng định danh commit và lần chạy, nhóm có thể tìm đúng test lỗi, tái hiện điều kiện, phân biệt lỗi sản phẩm với lỗi môi trường và xử lý regression nhanh hơn.

