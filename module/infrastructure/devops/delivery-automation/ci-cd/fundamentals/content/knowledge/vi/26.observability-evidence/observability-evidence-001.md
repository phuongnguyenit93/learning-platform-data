# Đọc nhật ký theo từng bước và giữ thông báo lỗi có ý nghĩa

Khi một pipeline CI/CD thất bại, câu hỏi đầu tiên thường là: bước nào lỗi, lỗi xảy ra ở đâu, nguyên nhân có thể là gì và cần làm gì tiếp theo? Nếu log chỉ chứa một dòng “Command failed” hoặc hàng nghìn dòng output không có ngữ cảnh, người xử lý phải tự ghép thông tin từ nhiều nơi. Việc điều tra kéo dài, retry có thể che giấu lỗi gốc và những lần phát hành sau khó tái hiện sự cố.

Log tốt giúp tái dựng tiến trình của một lần chạy theo từng run, job và step. Mỗi thông báo cần có thời điểm, ngữ cảnh, mức độ, mã lỗi ổn định và thông tin đủ để hành động. Khi lỗi xuất hiện, log nên giải thích điều gì đã thất bại, thành phần nào bị ảnh hưởng, có thể retry hay không và nơi tìm bằng chứng chi tiết. Log cũng phải được thiết kế để không làm lộ secret, token, dữ liệu cá nhân hoặc thông tin hạ tầng nhạy cảm.

Trong module CI/CD, log là một phần của observability và release evidence. Nó hỗ trợ xác định nguyên nhân của build/test/deploy, theo dõi retry, đối chiếu trạng thái pipeline và lưu dấu vết phục vụ audit. Log cần được thiết kế cùng pipeline, thay vì chỉ bật console output rồi hy vọng thông tin cần thiết sẽ xuất hiện.

## 1. Log giải quyết vấn đề gì trong CI/CD?

Một pipeline có nhiều tầng thực thi. Một run có thể chứa các job build, test, scan, publish, deploy và post-deploy verification; mỗi job lại gồm nhiều step. Khi lỗi xảy ra, chỉ biết run thất bại là chưa đủ.

Log theo từng bước giúp trả lời:

- Run nào, commit nào và artifact nào đang được xử lý?
- Job và step nào bắt đầu, kết thúc hoặc thất bại?
- Lệnh hoặc hoạt động nào được thực hiện?
- Step chạy trong môi trường, runner hoặc dependency nào?
- Thời gian thực thi và thời điểm phát hiện lỗi là bao lâu?
- Exit code, error code hoặc exception nào được trả về?
- Đây là lỗi tạm thời, lỗi cấu hình, lỗi kiểm thử hay lỗi không xác định?
- Attempt hiện tại là lần thử thứ mấy và các lần trước kết thúc ra sao?
- Bước tiếp theo nên retry, sửa cấu hình, chuyển owner hay dừng phát hành?

Log cũng giúp phân biệt lỗi của ứng dụng với lỗi của hạ tầng. Ví dụ, integration test có thể thất bại vì assertion sai, database không sẵn sàng, DNS lỗi hoặc runner hết disk. Nếu chỉ ghi “integration tests failed”, người nhận không biết nên bắt đầu từ đâu.

## 2. Phân biệt log, metric, trace và artifact

Các loại bằng chứng observability bổ sung cho nhau:

| Loại dữ liệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Log | Điều gì đã xảy ra tại một thời điểm? | Step tải dependency nhận HTTP 503 |
| Metric | Hiện tượng xảy ra thường xuyên hoặc ở mức nào? | Tỷ lệ job timeout, queue wait, build duration |
| Trace | Một request hoặc hoạt động đi qua những thành phần nào? | Deploy request đi từ pipeline đến controller và cluster |
| Artifact/evidence | Đầu ra hoặc bằng chứng chi tiết nào được lưu? | Test report, SBOM, scan report, deployment manifest |
| Event/state history | Trạng thái đã chuyển đổi theo trình tự nào? | Run chuyển từ QUEUED sang RUNNING rồi FAILED |

Log không thay thế metric. Một dòng lỗi cho biết một lần timeout; metric cho biết timeout đang tăng trên nhiều run. Log không thay thế trace khi cần theo dõi một request qua nhiều service. Log cũng không nên là nơi duy nhất lưu test report hoặc file dump lớn; hãy lưu artifact riêng và ghi liên kết cùng digest/ID vào log.

Trong CI/CD, nên liên kết các loại dữ liệu bằng run ID, job ID, step ID, attempt ID, commit SHA, artifact digest và trace/correlation ID. Nhờ vậy, người xử lý có thể đi từ dashboard đến log, từ log đến report và từ report đến đúng artifact đã được kiểm tra.

## 3. Cấu trúc vòng đời run, job và step

Một cách tổ chức log dễ đọc là chia thành các ranh giới rõ:

~~~text
Pipeline run
  ├── Job: build
  │     ├── Step: checkout-source
  │     ├── Step: resolve-dependencies
  │     └── Step: compile-and-package
  ├── Job: test
  │     ├── Step: start-test-services
  │     ├── Step: unit-tests
  │     └── Step: integration-tests
  ├── Job: security
  │     ├── Step: dependency-scan
  │     └── Step: image-scan
  └── Job: deploy
        ├── Step: verify-artifact
        ├── Step: apply-release
        └── Step: post-deploy-check
~~~

Mỗi cấp cần có sự kiện bắt đầu và kết thúc. Nếu một step thất bại, log phải cho biết job và run cha của nó. Nếu một job bị skip do dependency thất bại, ghi rõ lý do skip để tránh hiểu nhầm rằng job đã chạy và pass.

Nên dùng tên step ổn định qua các lần chạy. Tên hiển thị có thể thân thiện, nhưng ID máy đọc nên không đổi tùy ý vì dashboard, alert và truy vấn log có thể dựa vào ID đó.

## 4. Những trường ngữ cảnh nên có trong log

Log có cấu trúc giúp truy vấn và nhóm sự kiện chính xác hơn. Một bản ghi CI/CD thường cần một số trường sau:

| Trường | Mục đích |
|---|---|
| timestamp | Thời điểm sự kiện, ưu tiên UTC và định dạng chuẩn |
| level | Mức độ như INFO, WARN hoặc ERROR |
| event | Tên sự kiện ổn định, ví dụ step_started |
| message | Mô tả ngắn, dễ đọc |
| run_id | Định danh pipeline run |
| attempt | Lần chạy hoặc retry hiện tại |
| job_id | Định danh job |
| step_id | Định danh step |
| repository | Repository nguồn |
| commit_sha | Revision đã checkout/build |
| artifact_digest | Định danh nội dung artifact nếu đã có |
| environment | Môi trường đích hoặc môi trường test |
| runner_id | Runner thực thi, nếu cần cho điều tra |
| duration_ms | Thời lượng step hoặc operation |
| error_code | Mã lỗi ổn định khi có lỗi |
| correlation_id/trace_id | Nối log với hệ thống hoặc request khác |

Không phải dòng log nào cũng cần lặp lại toàn bộ metadata. Có thể đặt context chung ở đầu run/job và bổ sung các trường thay đổi theo step. Tuy nhiên, log cần giữ đủ khóa để khi tách riêng một đoạn hoặc truy vấn theo error code, người đọc vẫn xác định được nguồn.

Trường dữ liệu phải có schema nhất quán. Không dùng lúc thì runId, lúc pipeline, lúc execution nếu tất cả đều mang cùng ý nghĩa. Thay đổi schema log cần có version hoặc kế hoạch tương thích cho parser/dashboard.

## 5. Structured logging và log dạng văn bản

Structured logging ghi mỗi sự kiện dưới dạng bản ghi có trường rõ ràng, thường là JSON. Log dạng văn bản tự do vẫn hữu ích cho output của compiler, test runner hoặc công cụ bên ngoài, nhưng khó truy vấn nếu thiếu metadata.

Ví dụ một bản ghi JSON:

~~~json
{
  "timestamp": "2026-11-18T08:30:12.418Z",
  "level": "ERROR",
  "event": "step_failed",
  "message": "Integration test did not complete",
  "run_id": "build-1842",
  "attempt": 2,
  "job_id": "integration-tests",
  "step_id": "run-contract-suite",
  "commit_sha": "9f4c...e81a",
  "environment": "ci-test",
  "duration_ms": 120034,
  "error_code": "TEST_TIMEOUT",
  "retryable": false
}
~~~

Ví dụ đã rút gọn; giá trị commit và ID là placeholder. JSON giúp hệ thống lọc theo event, level, job hoặc error code mà không cần phân tích câu văn. Message vẫn cần dễ đọc để người vận hành hiểu nhanh.

Không nên biến mọi output thành JSON bằng cách nối chuỗi thủ công nếu message có dấu ngoặc kép, newline hoặc ký tự đặc biệt. Dùng JSON encoder của ngôn ngữ hoặc công cụ như jq để escape đúng. Nếu một công cụ chỉ xuất plain text, có thể giữ nguyên output trong step log và phát thêm sự kiện có cấu trúc ở ranh giới bắt đầu/kết thúc.

## 6. Ghi log ở ranh giới bắt đầu và kết thúc step

Một step nên phát ra ít nhất các sự kiện:

- step_started: step bắt đầu, kèm ID và context.
- step_progress: checkpoint hoặc tiến độ khi step dài.
- step_succeeded: step hoàn tất thành công, kèm duration.
- step_failed: step thất bại, kèm error code, exit code và retryability.
- step_skipped: step không chạy, kèm điều kiện hoặc dependency khiến nó bị skip.
- step_cancelled: step bị hủy, kèm actor hoặc nguyên nhân nếu biết.

Ví dụ trình tự:

~~~text
08:30:00Z INFO  step_started   job=build step=compile
08:30:01Z INFO  compile_progress source_files=412
08:30:18Z INFO  step_succeeded job=build step=compile duration_ms=17420
08:30:18Z INFO  step_started   job=build step=package
08:30:22Z ERROR step_failed    job=build step=package error_code=PACKAGE_OUTPUT_MISSING
~~~

Không cần ghi log cho mọi vòng lặp hoặc từng file nếu khối lượng quá lớn. Hãy chọn checkpoint có ích: bắt đầu, kết thúc, số lượng đã xử lý, mốc phần trăm hoặc thay đổi trạng thái. Với job dài, progress marker giúp phân biệt hoạt động chậm với job bị treo.

Nếu step bị kill đột ngột, sự kiện kết thúc có thể không được ghi. Dashboard nên nhận diện trường hợp thiếu terminal event bằng heartbeat, timeout và trạng thái runner, thay vì suy đoán rằng step đã thành công.

## 7. Log level và cách dùng nhất quán

Log level giúp người đọc lọc mức độ quan trọng:

| Level | Khi dùng | Ví dụ |
|---|---|---|
| TRACE | Chi tiết rất sâu để debug ngắn hạn | Quyết định nội bộ của parser |
| DEBUG | Thông tin phục vụ điều tra | Dependency cache hit/miss |
| INFO | Sự kiện bình thường có ý nghĩa | Build bắt đầu, artifact được publish |
| WARN | Bất thường nhưng vẫn tiếp tục được | Dùng fallback mirror sau timeout |
| ERROR | Một operation hoặc step thất bại | Test assertion fail, deploy gate denied |
| FATAL/CRITICAL | Thành phần không thể tiếp tục an toàn | Runner agent mất state không thể phục hồi |

Không dùng ERROR cho mọi thông báo để làm nổi bật log. Nếu một test case thất bại nhưng job tổng hợp vẫn chạy cleanup, test event là ERROR; cleanup thành công là INFO. Nếu một dependency timeout nhưng retry thành công, lần đầu có thể là WARN tùy policy, còn operation cuối cùng cần ghi kết quả thành công sau retry.

Log level không thay thế outcome. Một dòng WARN không đồng nghĩa pipeline pass; một dòng ERROR không nhất thiết có nghĩa toàn bộ run đã kết thúc. Dashboard cần tổng hợp theo state và policy của job.

## 8. Viết thông báo lỗi có ý nghĩa

Một thông báo lỗi tốt cần giúp người đọc trả lời nhanh:

1. Điều gì thất bại?
2. Xảy ra ở run/job/step hoặc thành phần nào?
3. Bằng chứng hoặc nguyên nhân đã biết là gì?
4. Tác động đến pipeline/release ra sao?
5. Có thể retry không, và theo điều kiện nào?
6. Người xử lý nên làm gì tiếp theo?

Thông báo yếu:

~~~text
ERROR: Something went wrong.
~~~

Thông báo hữu ích hơn:

~~~text
ERROR [TEST_TIMEOUT]: Contract test suite exceeded 120 seconds.
Job: integration-tests
Step: run-contract-suite
Attempt: 2 of 2
Impact: staging deployment is blocked.
Retryable: no automatic retry; inspect the slow test and dependency health.
Evidence: test-report artifact contract-tests-1842.
~~~

Ví dụ trên là mẫu nội dung. Khi nguyên nhân chưa xác định, hãy nói rõ “chưa xác định” và đưa ra bằng chứng đã biết. Không viết “database down” nếu log chỉ chứng minh một kết nối bị timeout; nguyên nhân có thể là network, pool exhaustion, DNS hoặc database quá tải.

## 9. Error code ổn định và error taxonomy

Error code là định danh máy đọc cho một loại lỗi. Message có thể được cải thiện theo thời gian hoặc dịch sang ngôn ngữ khác, còn code nên ổn định để alert, dashboard và runbook dựa vào.

Một taxonomy có thể chia theo nhóm:

| Prefix/category | Ví dụ code | Ý nghĩa |
|---|---|---|
| SOURCE | SOURCE_CHECKOUT_FAILED | Không lấy được source revision |
| BUILD | COMPILATION_FAILED | Compiler kết thúc với lỗi |
| TEST | TEST_ASSERTION_FAILED | Assertion không đạt |
| TEST | TEST_TIMEOUT | Test vượt thời gian cho phép |
| RUNNER | RUNNER_HEARTBEAT_LOST | Mất heartbeat từ runner |
| DEPENDENCY | REGISTRY_RATE_LIMITED | Registry giới hạn request |
| ARTIFACT | ARTIFACT_DIGEST_MISMATCH | Nội dung không khớp digest kỳ vọng |
| POLICY | DEPLOYMENT_POLICY_DENIED | Policy không cho phép bước tiếp theo |
| ENVIRONMENT | TEST_DATABASE_NOT_READY | Database test chưa sẵn sàng |
| DEPLOY | ROLLOUT_HEALTH_CHECK_FAILED | Health gate không đạt |

Đây là ví dụ taxonomy, không phải danh mục bắt buộc. Code nên đủ cụ thể để hỗ trợ routing nhưng không quá chi tiết đến mức mỗi message có một code riêng. Không nhúng giá trị động như run ID hoặc tên branch vào error code; đặt chúng trong field context.

Khi đổi code, cần duy trì mapping hoặc alias trong thời gian tương thích nếu hệ thống alert/runbook còn tham chiếu code cũ.

## 10. Phân biệt nguyên nhân, triệu chứng và hành động

Một log cần tách ba lớp thông tin:

- **Symptom:** điều quan sát được, ví dụ HTTP request timeout sau 10 giây.
- **Cause:** nguyên nhân đã được xác minh hoặc giả thuyết, ví dụ connection pool hết slot.
- **Action:** việc nên làm, ví dụ kiểm tra pool saturation và dependency latency.

Nếu cause chưa được xác minh, ghi nhận là suspected cause hoặc hypothesis. Không trình bày giả thuyết như sự thật.

Ví dụ:

~~~text
Symptom: package download returned HTTP 503.
Known context: registry endpoint was registry.internal.example.
Cause: not confirmed; upstream availability is under investigation.
Action: wait for Retry-After or check registry status before retrying.
Retryable: yes, within the configured retry budget.
~~~

Thông báo lỗi không nên chứa kết luận vượt quá bằng chứng. Điều này đặc biệt quan trọng khi pipeline tự động phân loại lỗi và gán owner; phân loại sai có thể chuyển ticket đến nhóm không liên quan.

## 11. Exit code, exception và command context

Khi một command thất bại, log nên ghi exit code hoặc exception type cùng step đã chạy. Exit code 1 thường chỉ báo lỗi chung của chương trình; không tự suy ra nguyên nhân cụ thể nếu tool không cung cấp thêm thông tin.

Ví dụ:

~~~text
Step: run-unit-tests
Command: ./gradlew test
Exit code: 1
Result: test task failed
Report: build/reports/tests/test/index.html
Next action: inspect failed test cases in the report
~~~

Không nhất thiết ghi nguyên command line nếu arguments có thể chứa password, token, signed URL hoặc dữ liệu nhạy cảm. Có thể ghi tên executable, task, sanitized arguments và phiên bản tool. Không dump toàn bộ environment variables để tìm nguyên nhân; cách đó thường làm lộ credential.

Với exception, ghi loại lỗi, message đã được redact, stack trace khi cần và correlation ID. Tránh log cùng một exception ở mọi tầng khiến một lỗi tạo hàng chục bản sao. Nên chọn một tầng chịu trách nhiệm log chi tiết; các tầng khác bổ sung context hoặc propagate error.

## 12. Giữ stdout và stderr có ý nghĩa

Nhiều công cụ CI thu thập stdout và stderr thành một luồng console. Một số hệ thống giữ riêng hai stream. Cần hiểu cách nền tảng hiển thị và lưu chúng để không mất thông tin.

- stdout thường chứa kết quả bình thường, progress và summary.
- stderr thường chứa warning, error hoặc diagnostic của công cụ, nhưng không phải công cụ nào cũng tuân thủ quy ước này.
- Exit code mới là tín hiệu chính của command success/failure; không chỉ dựa vào việc có text trên stderr.
- Khi redirect hoặc pipe output, cần bảo đảm exit code của command gốc được giữ lại.
- Output nhiều dòng cần có ranh giới step hoặc prefix để xác định nguồn.

Ví dụ với Bash:

~~~bash
set -Eeuo pipefail

./gradlew test 2>&1 | tee test-output.log
~~~

Với Bash, pipefail giúp pipeline command trả lỗi nếu một command trong pipe thất bại thay vì chỉ lấy exit code của tee. Tuy nhiên, cần kiểm tra shell thực tế của runner; cú pháp và semantics có thể khác giữa Bash, PowerShell và cmd.exe.

Không dùng grep tìm từ “ERROR” làm tiêu chí duy nhất để kết luận job thất bại. Một tool có thể in warning/error text nhưng exit code 0, hoặc thất bại mà không có từ khóa đó. Hãy kết hợp exit code, machine-readable report và log context.

## 13. Ví dụ wrapper ghi log theo step bằng Bash

Một wrapper nhỏ có thể ghi sự kiện bắt đầu/kết thúc và exit code mà không in toàn bộ command arguments:

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail

RUN_ID="$CI_RUN_ID"
JOB_ID="unit-tests"
STEP_ID="gradle-test"

log_event() {
  local level="$1"
  local event="$2"
  local message="$3"
  local exit_code="$4"

  jq -cn \
    --arg timestamp "$(date -u +%FT%TZ)" \
    --arg level "$level" \
    --arg event "$event" \
    --arg message "$message" \
    --arg run_id "$RUN_ID" \
    --arg job_id "$JOB_ID" \
    --arg step_id "$STEP_ID" \
    --arg exit_code "$exit_code" \
    '{
      timestamp: $timestamp,
      level: $level,
      event: $event,
      message: $message,
      run_id: $run_id,
      job_id: $job_id,
      step_id: $step_id,
      exit_code: (if $exit_code == "" then null else ($exit_code | tonumber) end)
    }'
}

log_event "INFO" "step_started" "Gradle test task started" ""

if ./gradlew test; then
  log_event "INFO" "step_succeeded" "Gradle test task passed" ""
else
  rc=$?
  log_event "ERROR" "step_failed" "Gradle test task failed" "$rc" >&2
  exit "$rc"
fi
~~~

Ví dụ cần Bash, jq và biến CI_RUN_ID được cung cấp bởi runner. Nếu biến context không tồn tại, script nên kiểm tra và báo lỗi cấu hình rõ ràng. Không đưa secret vào message hoặc command arguments. Trong triển khai thực tế, có thể bổ sung attempt, commit SHA, duration và report reference.

## 14. Ghi log lỗi mà không làm mất exit code

Một lỗi thường gặp là wrapper bắt lỗi nhưng sau đó trả exit code 0, khiến pipeline báo thành công. Ví dụ nguy hiểm:

~~~bash
./gradlew test || echo "Tests failed"
~~~

Trong shell, phần echo thành công có thể làm command list trả mã 0 nếu script không chủ động trả lại mã lỗi. Kết quả là thông báo lỗi xuất hiện nhưng gate CI vẫn xanh.

Cách rõ ràng hơn:

~~~bash
if ./gradlew test; then
  echo "INFO: tests passed"
else
  rc=$?
  echo "ERROR: tests failed with exit code $rc" >&2
  exit "$rc"
fi
~~~

Không dùng **|| true** cho test/build/deploy gate bắt buộc chỉ để pipeline tiếp tục. Nếu cần thu thập report hoặc cleanup sau lỗi, hãy dùng cơ chế **always()**/finally của CI platform hoặc shell trap có chủ đích, rồi giữ outcome thất bại ban đầu.

## 15. Ghi log cho retry và backoff

Khi một step được retry, mỗi attempt cần có log riêng và liên kết về cùng operation. Tối thiểu cần ghi:

- attempt hiện tại và số attempt tối đa.
- error code và loại lỗi.
- retry decision: allowed, denied hoặc exhausted.
- delay/backoff và Retry-After nếu có.
- thời điểm bắt đầu retry.
- kết quả từng attempt và kết quả cuối.
- idempotency key hoặc operation ID khi phù hợp, không ghi secret.

Ví dụ:

~~~text
WARN retry_scheduled operation=download-dependency attempt=1 max_attempts=3
     error_code=REGISTRY_RATE_LIMITED delay_ms=2000
INFO retry_started operation=download-dependency attempt=2
INFO retry_succeeded operation=download-dependency attempt=2 duration_ms=840
~~~

Không chỉ ghi “retrying”. Người điều tra cần biết vì sao retry được phép và lần thử nào đã thành công. Nếu lỗi là compile error hoặc policy denied, retry thường không có ích; log nên nói rõ retry bị từ chối vì lỗi không thuộc nhóm transient.

Khi hết retry budget, ghi một sự kiện cuối như **retry_exhausted** và giữ error code gốc. Đừng thay nguyên nhân bằng một thông báo chung “max retries exceeded” mà không liên kết lỗi đầu tiên.

## 16. Log cho timeout và cancellation

Timeout cần ghi rõ timeout ở tầng nào:

- Connect timeout.
- Read/response timeout.
- Command/step timeout.
- Job timeout.
- Pipeline deadline.
- External operation deadline.

Thông báo “operation timed out” chưa đủ nếu không biết deadline và thời gian đã chờ. Nên ghi timeout_ms, elapsed_ms, dependency/request ID và operation state cuối cùng có thể xác minh.

Cancellation cần ghi actor hoặc policy đã yêu cầu hủy, thời điểm gửi yêu cầu và kết quả xác nhận. Hủy pipeline không đảm bảo process bên ngoài đã dừng. Nếu runner mất kết nối khi deploy, trạng thái có thể là unknown; log cần chỉ rõ chưa xác minh side effect và không khuyến nghị retry mù.

## 17. Correlation ID và trace context

Một pipeline có thể gọi nhiều hệ thống: Git provider, artifact registry, scanner, cloud API, deployment controller và notification service. Để nối log giữa chúng, cần correlation ID hoặc trace ID được truyền qua các request.

Các định danh nên được phân biệt:

- run_id: một lần chạy pipeline.
- attempt_id: một lần thực thi hoặc retry cụ thể.
- job_id/step_id: thành phần trong pipeline.
- operation_id: một thao tác logic như publish artifact hoặc deploy release.
- correlation_id: nối các hoạt động có liên quan qua nhiều hệ thống.
- trace_id/span_id: theo dõi một distributed trace theo chuẩn tracing.

Không dùng một ID thay thế tất cả nếu phạm vi và vòng đời khác nhau. Một run có thể có nhiều attempt; một operation có thể được gọi lại từ nhiều job; một trace có thể kết thúc trước khi toàn bộ release hoàn tất.

Nếu nhận correlation ID từ nguồn ngoài, cần kiểm tra độ dài/định dạng và tránh cho phép người dùng chèn ký tự điều khiển vào log. Với hệ thống dùng W3C Trace Context, truyền traceparent/tracestate theo chuẩn và không ghi giá trị nhạy cảm vào baggage.

## 18. Timestamp và duration

Timestamp nên dùng UTC, có timezone và định dạng nhất quán, ví dụ RFC 3339/ISO 8601. Điều này giúp so sánh log giữa runner, registry và cloud service ở các múi giờ khác nhau.

Duration nên được đo bằng monotonic clock trong cùng process nếu cần tính chính xác thời gian chạy. Đồng hồ hệ thống có thể được điều chỉnh bởi NTP hoặc thay đổi thời gian; không nên lấy hiệu hai wall-clock timestamp làm nguồn duy nhất cho duration ngắn.

Một bản ghi step có thể chứa:

- started_at và finished_at.
- duration_ms.
- runner timezone hoặc clock metadata nếu cần điều tra.
- event timestamp từ nguồn phát và ingest timestamp từ log platform nếu có.

Phân biệt event time với ingest time giúp phát hiện log đến trễ hoặc đồng hồ runner lệch. Không sắp xếp các sự kiện chỉ dựa trên thứ tự chúng xuất hiện trong giao diện nếu nhiều runner ghi đồng thời.

## 19. Giữ thông báo lỗi an toàn: redaction và data minimization

Log thường chứa dữ liệu đi qua command, environment và request. Trước khi ghi hoặc gửi log ra hệ thống tập trung, cần loại bỏ:

- Access token, API key, password và private key.
- Authorization header, cookie và session token.
- Signed URL hoặc query parameter chứa credential.
- Secret environment variables và nội dung secret manager.
- Dữ liệu cá nhân hoặc payload khách hàng không cần cho điều tra.
- Private endpoint hoặc thông tin nội bộ vượt phạm vi người xem log.

Không dump toàn bộ environment, request body hoặc file cấu hình khi debug. Không bật shell tracing (**set -x**) trong step có secret nếu chưa có cơ chế redaction đáng tin. Masking theo chuỗi có thể thất bại nếu secret bị encode, chia nhỏ, biến đổi hoặc xuất hiện trong URL/header khác.

Tốt nhất là không đưa secret vào command line hoặc log ngay từ đầu. Lấy secret qua cơ chế quản lý phù hợp, truyền qua file/descriptor hoặc environment được kiểm soát, giới hạn scope và thời gian sống. Redaction là lớp bảo vệ bổ sung, không phải lý do để ghi dữ liệu nhạy cảm.

## 20. Log injection và dữ liệu không tin cậy

Tên branch, commit message, test output, tên file và response từ dependency có thể do người dùng hoặc hệ thống ngoài kiểm soát. Nếu nối trực tiếp vào log text, dữ liệu có thể chứa newline, ký tự điều khiển hoặc chuỗi giống lệnh annotation của CI platform.

Rủi ro gồm:

- Giả mạo một dòng log ERROR hoặc SUCCESS.
- Tạo annotation/link ngoài ý muốn.
- Làm hỏng JSON hoặc log parser.
- Chèn nội dung nhạy cảm vào dashboard/notification.
- Làm người vận hành hiểu sai actor hoặc kết quả.

Hãy dùng structured logger/JSON encoder, giới hạn độ dài field và escape ký tự điều khiển. Khi dùng annotation command riêng của CI platform, phải encode đúng các ký tự đặc biệt theo tài liệu nền tảng. Không đưa giá trị không tin cậy vào cú pháp điều khiển mà không sanitize.

## 21. Không ghi log quá nhiều

Log quá ít khiến điều tra thiếu dữ liệu; log quá nhiều làm tăng chi phí, che lấp tín hiệu và có thể làm lộ thông tin. Cần chọn mức chi tiết theo loại step và rủi ro.

Nên ghi:

- Ranh giới bắt đầu/kết thúc và kết quả của step.
- Phiên bản tool, môi trường và dependency quan trọng.
- Số lượng hoặc summary có ý nghĩa.
- Error code, exit code và report reference.
- Retry decision và attempt history.
- Các thay đổi state hoặc quyết định release.

Tránh:

- In từng vòng lặp hoặc từng file khi không có giá trị điều tra.
- Dump toàn bộ environment hoặc config.
- In nguyên request/response chứa dữ liệu khách hàng.
- Lặp lại cùng một stack trace ở nhiều tầng.
- Ghi thông tin nhạy cảm chỉ để tiện debug.

Với output lớn như compiler log, test report hoặc scanner report, giữ file dưới dạng artifact có retention phù hợp. Console log chỉ cần summary, vị trí lưu và ID/digest để truy xuất.

## 22. Step group, annotation và summary

Log pipeline cần dễ quét. Có thể nhóm output theo job/step, đánh dấu warning/error và tạo summary ở cuối run.

Một summary tốt nên có:

- Tổng số job/step pass, fail, skipped.
- Step thất bại đầu tiên và các lỗi tiếp theo.
- Error code và thông báo ngắn.
- Attempt/retry count.
- Link đến report/artifact.
- Bước bị chặn hoặc môi trường chưa được deploy.
- Next action hoặc owner nếu được xác định bởi hệ thống.

Không chỉ đưa “Pipeline failed” ở cuối. Summary nên giúp người xem định vị nhanh step lỗi mà không cần đọc toàn bộ log từ đầu. Tuy nhiên, summary không thay thế log gốc; phải có liên kết đến chi tiết.

Khi dùng màu hoặc annotation, vẫn phải có text rõ ràng để hỗ trợ terminal không màu, screen reader và hệ thống lưu trữ. Không dùng màu đỏ/xanh là tín hiệu duy nhất.

## 23. Ví dụ workflow giữ log theo từng step

Ví dụ GitHub Actions dưới đây minh họa việc đặt tên step, giữ test report và tạo summary khi thất bại:

~~~yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        id: checkout
        uses: actions/checkout@v4

      - name: Record build context
        id: context
        run: |
          echo "run_id=$GITHUB_RUN_ID"
          echo "attempt=$GITHUB_RUN_ATTEMPT"
          echo "commit_sha=$(git rev-parse HEAD)"

      - name: Run unit tests
        id: unit-tests
        run: ./gradlew test

      - name: Upload test report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: unit-test-report
          path: build/reports/tests/test/
          if-no-files-found: warn

      - name: Write failure summary
        if: failure()
        run: |
          {
            echo "## Unit test job failed"
            echo ""
            echo "- Run: $GITHUB_RUN_ID"
            echo "- Attempt: $GITHUB_RUN_ATTEMPT"
            echo "- Commit: $(git rev-parse HEAD)"
            echo "- Report: unit-test-report artifact"
          } >> "$GITHUB_STEP_SUMMARY"
~~~

Ví dụ minh họa, cần pin action theo commit SHA nếu policy của repository yêu cầu. Không ghi secret vào step output hoặc summary. Step context chỉ ghi metadata không nhạy cảm; test report được lưu riêng và có quyền truy cập theo artifact policy.

Điều kiện **always()** giúp upload report sau khi test thất bại, còn **failure()** tạo summary khi job có lỗi. Với pipeline phức tạp, cần chú ý semantics của job dependency, cancellation và timeout; một step cleanup/upload vẫn có thể bị hủy nếu toàn bộ workflow bị cancel hoặc runner mất kết nối.

## 24. Phân tích log theo thứ tự điều tra

Khi một job thất bại, nên đọc log theo thứ tự:

1. Xác định run ID, attempt, commit SHA và environment.
2. Tìm summary để xác định job/step thất bại.
3. Mở log của step lỗi và xác định error code/exit code.
4. Đọc các sự kiện ngay trước lỗi để tìm context.
5. Kiểm tra dependency hoặc step upstream có liên quan.
6. Đối chiếu test report, scanner report hoặc artifact evidence.
7. Kiểm tra retry history và xem lỗi có lặp lại cùng một dạng không.
8. Xác định lỗi có transient, deterministic, policy-related hay unknown.
9. Chọn next action và owner dựa trên bằng chứng.
10. Ghi kết quả điều tra và liên kết đến runbook/ticket nếu cần.

Đọc từ dòng lỗi cuối cùng trở ngược đôi khi hữu ích, nhưng không nên dừng ở dòng cuối. Nguyên nhân thường xuất hiện trước đó: một dependency không sẵn sàng, một warning bị bỏ qua hoặc một cấu hình được resolve sai.

## 25. Ví dụ: lỗi dependency download

Log không đủ ngữ cảnh:

~~~text
Download failed.
~~~

Log có ích hơn:

~~~text
timestamp=2026-11-18T08:32:10Z
level=WARN
event=dependency_download_retryable
run_id=build-1842
job_id=build
step_id=resolve-dependencies
dependency=org.example:library:2.4.1
http_status=503
attempt=1
max_attempts=3
retry_after_ms=2000
error_code=REGISTRY_UNAVAILABLE
~~~

Nếu attempt tiếp theo thành công, ghi sự kiện retry thành công và kết quả cuối. Nếu hết retry budget, ghi **retry_exhausted**, giữ nguyên dependency coordinates và registry host đã được phép hiển thị. Không ghi credential hoặc full URL có token.

Với lỗi 404 do version không tồn tại, retry thường không giải quyết được. Error classification nên chỉ ra đây có thể là lỗi dependency declaration hoặc repository configuration, thay vì tiếp tục retry theo cùng một policy.

## 26. Ví dụ: test thất bại do assertion

Thông báo tốt nên chỉ ra test nào, kỳ vọng gì và thực tế là gì, đồng thời liên kết report:

~~~text
ERROR [TEST_ASSERTION_FAILED]
Test: OrderPricingTest.appliesDiscountForEligibleCustomer
Expected: total = 90000 VND
Actual: total = 100000 VND
Job: unit-tests
Step: gradle-test
Attempt: 1
Retryable: no automatic retry; deterministic assertion failure
Evidence: unit-test-report artifact
~~~

Trong hệ thống thực tế, chỉ ghi giá trị nghiệp vụ nếu chúng không chứa dữ liệu cá nhân hoặc thông tin nhạy cảm. Nếu test fixture có customer data thật, thay bằng synthetic identifier hoặc redacted value.

Không tự động retry một assertion deterministic nhiều lần chỉ để chờ test pass. Nếu test flaky, hãy ghi riêng trạng thái flaky, số lần tái hiện và môi trường; không biến lần retry thành bằng chứng rằng code đã ổn định.

## 27. Log cho deploy và post-deploy verification

Deploy log cần liên kết artifact đã được xác minh với môi trường đích:

- service và release ID.
- artifact URI và digest.
- environment, region/cluster/namespace.
- deployment controller request ID.
- rollout strategy và step/cohort hiện tại.
- expected replica/instance count.
- health gate và kết quả từng probe.
- expected digest và actual runtime digest.
- thời điểm bắt đầu/kết thúc, duration và actor.

Nếu deploy API timeout, ghi rõ request ID và trạng thái chưa xác minh. Không ghi “deploy failed” nếu chưa biết controller có thực hiện side effect hay không. Khi runtime digest khác digest dự kiến, ghi error code như **RUNTIME_ARTIFACT_MISMATCH** và chặn bước promotion tiếp theo.

Post-deploy log nên ghi riêng smoke test, readiness, error rate/latency gate và kết quả xác minh runtime. Deploy command exit code 0 không thay thế xác minh sau triển khai.

## 28. Retention, truy cập và integrity của log

Log có thể chứa thông tin nội bộ và là bằng chứng điều tra. Chính sách log cần xác định:

- Thời gian lưu theo loại log: console, audit, debug và security event.
- Quyền xem theo repository, service, environment và incident role.
- Mã hóa khi truyền và khi lưu.
- Cách redact hoặc xóa dữ liệu nhạy cảm theo yêu cầu.
- Giới hạn dung lượng, chunking và xử lý log bị truncate.
- Cách lưu trữ lâu dài cho release evidence cần giữ qua rollback/audit window.
- Audit việc truy cập hoặc export log nhạy cảm khi cần.

Không giữ debug log vô thời hạn chỉ vì storage rẻ. Ngược lại, không xóa release evidence trước khi hết thời gian cần cho điều tra, rollback hoặc compliance. Retention nên dựa trên mục đích và mức độ nhạy cảm.

Với bằng chứng quan trọng, có thể lưu digest của report/log bundle trong release record để phát hiện file bị thay đổi. Digest giúp xác định nội dung; quyền truy cập và nguồn phát hành vẫn cần được kiểm soát riêng.

## 29. Xử lý log bị thiếu, trễ hoặc truncate

Log có thể không đầy đủ vì runner mất kết nối, agent bị kill, output vượt giới hạn nền tảng hoặc upload artifact thất bại. Cần ghi rõ trạng thái thu thập:

- **complete:** log được thu thập đầy đủ theo giới hạn đã định.
- **partial:** có một phần log nhưng thiếu đoạn hoặc terminal event.
- **truncated:** log vượt giới hạn và bị cắt.
- **unavailable:** không truy xuất được log.
- **delayed:** log đến muộn so với event time.

Không diễn giải “không thấy lỗi trong log” thành “không có lỗi” nếu log bị partial hoặc truncated. Dashboard nên cảnh báo rõ chất lượng evidence.

Với output lớn, chia chunk có sequence number, step ID và timestamp. Nếu upload report thất bại, ghi error riêng và giữ đường dẫn local nếu runner còn sống. Nếu runner đã mất, state cần phản ánh rằng evidence chưa đầy đủ.

## 30. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ ghi “Step failed” | Không biết lỗi ở đâu hoặc làm gì tiếp | Thêm step ID, error code, exit code và next action |
| Chỉ dựa vào console text | Khó truy vấn và nhóm lỗi | Structured event cho ranh giới và kết quả |
| Dùng ERROR cho mọi dòng | Alert nhiễu, khó tìm lỗi thật | Quy ước log level |
| Ghi toàn bộ environment | Có thể lộ token/password | Allowlist field cần thiết |
| Bật shell tracing với secret | Secret xuất hiện trong log | Tránh trace hoặc dùng cơ chế bảo vệ đã kiểm chứng |
| Bắt lỗi rồi trả exit code 0 | Pipeline xanh giả | Propagate exit code và giữ failure outcome |
| Retry nhưng không ghi attempt | Không biết lỗi ban đầu và lần nào thành công | Log attempt, delay, reason và kết quả |
| Ghi giả thuyết như nguyên nhân chắc chắn | Điều tra sai hướng | Phân biệt symptom, known cause và hypothesis |
| In toàn bộ report vào console | Log lớn, khó đọc và tốn chi phí | Lưu artifact, ghi summary và link |
| Không có correlation ID | Khó nối log giữa các hệ thống | Truyền run/operation/trace context |
| Dùng timestamp không timezone | Khó đối chiếu nhiều runner | UTC và định dạng chuẩn |
| Ghi dữ liệu không tin cậy trực tiếp | Log injection hoặc hỏng parser | Structured encoder và sanitize |
| Không ghi rõ log partial/truncated | Người đọc tin evidence chưa đầy đủ | Gắn collection status |
| Dùng grep “ERROR” làm gate | False positive/negative | Dựa vào exit code và report có cấu trúc |

## 31. Checklist thiết kế log cho pipeline

Trước khi đưa pipeline vào sử dụng, hãy kiểm tra:

- [ ] Run, job và step có ID ổn định và tên dễ hiểu.
- [ ] Có event bắt đầu/kết thúc và trạng thái skipped/cancelled khi cần.
- [ ] Log có timestamp UTC và duration.
- [ ] Có run ID, attempt, job ID, step ID và commit SHA.
- [ ] Artifact digest và environment được ghi ở các bước publish/deploy.
- [ ] Log có level, event name và schema nhất quán.
- [ ] Error code ổn định, không chứa giá trị động.
- [ ] Thông báo phân biệt symptom, cause đã xác minh và next action.
- [ ] Exit code/exception được giữ nguyên và propagate đúng.
- [ ] Retry log có attempt, max attempts, delay, reason và final outcome.
- [ ] Timeout/cancellation ghi rõ tầng và trạng thái side effect.
- [ ] Correlation/trace ID nối được các hệ thống liên quan.
- [ ] Secret, token, cookie và dữ liệu cá nhân được loại khỏi log.
- [ ] Input không tin cậy được escape trước khi ghi hoặc tạo annotation.
- [ ] Output lớn được lưu thành artifact có link và retention phù hợp.
- [ ] Summary giúp định vị step lỗi và evidence chi tiết.
- [ ] Log partial/truncated/unavailable được đánh dấu rõ.
- [ ] Quyền truy cập, encryption và retention được cấu hình.
- [ ] Có kiểm tra thử khi runner mất kết nối hoặc log upload thất bại.

## 32. Kết luận

Đọc nhật ký theo từng bước giúp nhóm xác định chính xác nơi pipeline bắt đầu, tiến triển, thất bại hoặc bị gián đoạn. Log có cấu trúc, ID ổn định, timestamp UTC, error code và correlation context giúp nối một lỗi với run, job, commit, artifact và môi trường liên quan. Thông báo lỗi có ý nghĩa phải mô tả điều đã biết, tác động, khả năng retry và hành động tiếp theo mà không khẳng định nguyên nhân chưa được xác minh.

Thiết kế log cần giữ exit code, ghi attempt và retry decision, phân biệt timeout với cancellation, bảo vệ secret và đánh dấu evidence bị thiếu hoặc truncate. Khi log được liên kết với metric, trace, test report và deployment record, pipeline trở nên dễ điều tra hơn và quyết định phát hành có thể dựa trên bằng chứng rõ ràng.
