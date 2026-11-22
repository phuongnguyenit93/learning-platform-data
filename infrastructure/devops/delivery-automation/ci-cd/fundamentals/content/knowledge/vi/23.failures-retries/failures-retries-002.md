# Dừng sớm khi lỗi đã đủ để loại bỏ một thay đổi

Một pipeline CI/CD có thể chạy nhiều phút hoặc nhiều giờ, nhưng không phải lỗi nào cũng cần chờ đến cuối mới kết luận. Nếu mã nguồn không biên dịch được, dependency không thể giải quyết, migration không hợp lệ hoặc một kiểm tra bắt buộc đã thất bại rõ ràng, các bước phụ thuộc phía sau thường không còn giá trị. Tiếp tục chạy chúng chỉ tiêu tốn runner, kéo dài thời gian phản hồi và làm người phát triển phải chờ lâu hơn để biết thay đổi cần sửa.

**Fail fast** là nguyên tắc dừng sớm khi đã có bằng chứng đủ mạnh rằng thay đổi không thể vượt qua điều kiện bắt buộc. Pipeline nên ưu tiên các kiểm tra nhanh và có tính quyết định, ngừng những công việc phụ thuộc vào kết quả đã thất bại, đồng thời giữ lại log và báo cáo cần thiết để điều tra. Dừng sớm phải giữ nguyên trạng thái lỗi; không được biến lỗi thành thành công hoặc bỏ qua kiểm tra bắt buộc.

## 1. Fail fast giải quyết vấn đề gì?

Một pipeline thông thường gồm nhiều bước: kiểm tra cấu hình, cài dependency, lint, compile, unit test, integration test, security scan, đóng gói và publish artifact. Nếu compile thất bại nhưng pipeline vẫn chạy integration test, publish hoặc deploy, nhiều bước sau có thể thất bại dây chuyền vì cùng một nguyên nhân.

Fail fast giúp:

- Rút ngắn thời gian từ lúc commit đến khi nhận phản hồi có thể hành động.
- Giảm phút runner và tài nguyên dùng cho công việc đã mất điều kiện tiếp tục.
- Tránh tạo log lỗi thứ cấp che khuất nguyên nhân đầu tiên.
- Ngăn publish hoặc deploy một thay đổi đã không vượt qua gate bắt buộc.
- Giải phóng hàng đợi để các thay đổi khác được kiểm tra sớm hơn.

Ví dụ, một lỗi cú pháp trong module chính khiến build thất bại. Việc tiếp tục chạy browser test, đóng gói image và deploy staging không giúp tìm thêm nguyên nhân có ích. Pipeline nên dừng các bước phụ thuộc, lưu compiler log và thông báo lỗi đầu tiên.

Tuy nhiên, không phải mọi lỗi đều có nghĩa toàn bộ pipeline nên dừng ngay. Nếu lint, unit test và dependency scan là các kiểm tra độc lập, nhóm có thể muốn chạy đủ để người phát triển nhận được nhiều phản hồi trong một lần. Fail fast cần được áp dụng theo quan hệ phụ thuộc và giá trị chẩn đoán của từng bước.

## 2. Phân biệt fail fast, fail pipeline và fail job

Ba khái niệm có liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Fail fast | Dừng công việc không còn cần thiết ngay khi có lỗi quyết định | Compile fail nên không chạy integration test |
| Fail job | Job kết thúc với trạng thái thất bại | Unit test có assertion không đạt |
| Fail pipeline | Kết quả tổng thể không đạt điều kiện | Một required job thất bại hoặc bị hủy ngoài chính sách |

Một job có thể thất bại trong khi các job độc lập vẫn tiếp tục chạy để thu thập kết quả. Một pipeline có thể vẫn thất bại dù một số job khác thành công. Ngược lại, một job bị hủy hoặc skipped không được tự động xem là pass.

Cần phân biệt thêm:

- **Failure:** một lệnh hoặc kiểm tra đã chạy và không đạt.
- **Cancelled:** công việc bị hủy bởi người dùng, timeout, workflow mới hoặc fail-fast.
- **Skipped:** công việc không được chạy do điều kiện hoặc phụ thuộc.
- **Success:** công việc đã chạy và đạt điều kiện được định nghĩa.

Fail fast thường tạo ra một số trạng thái cancelled hoặc skipped ở các bước không còn cần thiết. Gate cuối cần biết job nào thất bại đầu tiên, job nào bị hủy do phụ thuộc và job nào được bỏ qua hợp lệ.

## 3. Sắp xếp pipeline theo chi phí và quan hệ phụ thuộc

Một cách áp dụng fail fast là đưa các kiểm tra nhanh, ít tốn tài nguyên và có khả năng loại bỏ thay đổi lên trước.

Thứ tự tham khảo:

1. Kiểm tra định dạng file, cấu hình và cú pháp pipeline.
2. Kiểm tra dependency manifest, lockfile và điều kiện bảo mật cơ bản.
3. Lint, format và static validation.
4. Compile hoặc build bước đầu.
5. Unit test.
6. Kiểm tra module hoặc ma trận runtime cần thiết.
7. Integration test và contract test.
8. End-to-end, performance hoặc test cần môi trường riêng.
9. Đóng gói, ký, publish artifact và triển khai.

Thứ tự này không phải quy tắc cứng. Nếu một static analysis nhanh có thể chạy song song với compile mà không gây tranh chấp tài nguyên, có thể chạy song song. Nếu một kiểm tra cần artifact đã build, nó phải phụ thuộc vào build thành công.

Có thể biểu diễn đồ thị phụ thuộc:

~~~mermaid
flowchart TD
    A[Checkout và validate input] --> B[Lint và static checks]
    A --> C[Resolve dependencies]
    B --> D[Compile/build]
    C --> D
    D --> E[Unit tests]
    E --> F[Integration tests]
    F --> G[E2E và release checks]
    G --> H[Publish artifact]
    H --> I[Deploy]
~~~

Nếu B hoặc C thất bại, D và các bước phụ thuộc không cần chạy. Nếu một kiểm tra độc lập khác vẫn có giá trị chẩn đoán, nó có thể tiếp tục theo policy.

Đừng chỉ sắp xếp theo thời gian chạy ngắn nhất. Một kiểm tra nhanh nhưng thường xuyên báo lỗi nhiễu có thể làm pipeline dừng không cần thiết. Ưu tiên kiểm tra nhanh, ổn định, có độ tin cậy cao và có thể loại bỏ sớm một thay đổi.

## 4. Xác định lỗi nào đủ điều kiện dừng sớm

Không phải tất cả warning hoặc lỗi tạm thời đều có cùng mức độ. Trước khi bật fail fast, hãy phân loại kết quả.

| Nhóm lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Deterministic code failure | Compile error, syntax error, assertion fail | Dừng bước phụ thuộc |
| Required policy violation | Secret scan phát hiện credential, license policy bị vi phạm | Chặn pipeline theo policy |
| Invalid input | Manifest sai schema, thiếu tham số bắt buộc | Dừng trước khi cấp tài nguyên |
| Dependency/environment transient | Registry timeout, runner mất kết nối tạm thời | Retry có giới hạn trước khi kết luận |
| Advisory warning | Benchmark tham khảo vượt nhẹ ngưỡng không chặn | Ghi warning và tiếp tục |
| Insufficient evidence | Report không có, telemetry chưa sẵn sàng | Chờ, retry hoặc đánh dấu chưa xác minh |
| Independent failure | Lint fail nhưng security scan vẫn có giá trị | Có thể tiếp tục kiểm tra độc lập |

Một lỗi deterministic thường không được giải quyết bằng retry. Chạy lại compile với cùng source và cùng compiler hiếm khi sửa được lỗi cú pháp. Ngược lại, timeout khi tải dependency có thể là lỗi tạm thời; nên retry theo chính sách trước khi dừng cả pipeline.

Điều kiện dừng phải được định nghĩa trước. Không để một script tùy ý quyết định bỏ qua lỗi vì muốn pipeline xanh.

## 5. Dừng các bước phụ thuộc, giữ các bước độc lập có giá trị

Đồ thị pipeline cho biết bước nào cần kết quả từ bước nào. Khi một node thất bại, các node phụ thuộc trực tiếp hoặc gián tiếp không thể tiếp tục một cách có ý nghĩa.

Ví dụ:

- Compile thất bại: không chạy unit test cần bytecode mới.
- Artifact không được tạo: không chạy image scan hoặc deploy trên artifact đó.
- Migration validation thất bại: không chạy test ứng dụng dựa trên schema mới.
- Secret scan phát hiện credential thật: không publish artifact chứa dữ liệu rò rỉ.
- Lint thất bại: có thể vẫn chạy security scan độc lập nếu mục tiêu là cung cấp thêm phản hồi.

Điều này khác với việc dừng toàn bộ workflow ngay khi có bất kỳ job nào fail. Nếu một job độc lập có thể phát hiện lỗi quan trọng khác với chi phí hợp lý, tiếp tục nó có thể hữu ích.

Một cách thiết kế là chia pipeline thành các nhóm:

- **Prerequisite gates:** điều kiện nền tảng; thất bại thì dừng các bước phụ thuộc.
- **Independent diagnostics:** kiểm tra độc lập có thể chạy song song và báo kết quả riêng.
- **Release gates:** điều kiện bắt buộc trước publish hoặc deploy.
- **Evidence collection:** thu thập report/log sau khi kiểm tra kết thúc, kể cả khi thất bại.

## 6. Ví dụ GitHub Actions: dừng ma trận khi một cấu hình thất bại

GitHub Actions hỗ trợ `strategy.fail-fast` cho matrix job. Giá trị mặc định là `true`. Khi một job trong ma trận thất bại, các job đang chạy hoặc đang chờ trong cùng ma trận có thể bị hủy.

Ví dụ:

~~~yaml
name: Runtime compatibility

on:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: true
      matrix:
        java: ['17', '21']
        os: [ubuntu-latest, windows-latest]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}

      - name: Run tests on Unix
        if: runner.os != 'Windows'
        run: ./mvnw --batch-mode verify

      - name: Run tests on Windows
        if: runner.os == 'Windows'
        run: .\mvnw.cmd --batch-mode verify
~~~

Nếu một tổ hợp OS/JDK thất bại, những tổ hợp còn lại trong cùng ma trận có thể bị hủy. Điều này tiết kiệm tài nguyên khi lỗi đã đủ để loại bỏ thay đổi.

Tuy nhiên, ma trận có thể bị hủy trước khi cho biết lỗi có chỉ xảy ra trên một hệ điều hành hay runtime cụ thể hay không. Với lỗi tương thích đa nền tảng, thông tin đó đôi khi rất quan trọng. Khi cần kết quả đầy đủ, đặt `fail-fast: false` để mọi tổ hợp tiếp tục và thu thập report.

Không nhầm `strategy.fail-fast` với việc bỏ qua lỗi. Job thất bại đầu tiên vẫn phải làm ma trận và pipeline thể hiện đúng trạng thái không đạt.

## 7. Khi nào nên tắt fail-fast cho ma trận?

Có những tình huống cần chạy đủ ma trận dù một tổ hợp đã thất bại:

- Xác định chính xác runtime hoặc OS nào bị lỗi.
- Kiểm tra mức độ ảnh hưởng trên nhiều kiến trúc.
- Thu thập kết quả cho một đợt nâng cấp JDK hoặc dependency lớn.
- Chạy nightly regression để có báo cáo đầy đủ.
- Thu thập bằng chứng cho một sự cố đã biết.
- Đánh giá một thay đổi có thể có hành vi khác nhau theo nền tảng.

Ví dụ:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    java: ['17', '21']
    os: [ubuntu-latest, windows-latest]
~~~

Trong chế độ này, pipeline có thể tốn thêm tài nguyên nhưng cung cấp bức tranh đầy đủ hơn. Các job vẫn phải trả trạng thái thật; `fail-fast: false` không biến failure thành success.

Có thể dùng chính sách khác nhau theo loại workflow: pull request thông thường ưu tiên phản hồi nhanh; nightly hoặc release qualification ưu tiên kết quả ma trận đầy đủ. Hãy ghi rõ lý do để người vận hành hiểu vì sao hai workflow có hành vi khác nhau.

## 8. Thu thập report trước khi job kết thúc

Dừng sớm không có nghĩa bỏ mất bằng chứng. Một test job thất bại vẫn nên upload JUnit XML, log và các tệp chẩn đoán trước khi runner kết thúc.

Ví dụ:

~~~yaml
- name: Run tests
  run: ./mvnw --batch-mode verify

- name: Upload test reports
  if: ${{ always() }}
  uses: actions/upload-artifact@v4
  with:
    name: test-reports-${{ github.run_id }}-${{ github.run_attempt }}
    path: |
      **/target/surefire-reports/**
      **/target/failsafe-reports/**
    if-no-files-found: warn
    retention-days: 14
~~~

Bước upload dùng `always()` để có cơ hội chạy sau khi test fail. Job vẫn thất bại nếu test bắt buộc thất bại. Không đặt `continue-on-error: true` lên test chỉ để upload report.

Với job bị hủy ngay bởi fail-fast, các bước cleanup hoặc upload có thể không chạy tùy thời điểm và cách nền tảng hủy job. Vì vậy:

- Lưu log quan trọng liên tục khi có thể.
- Đặt bước thu thập ngay sau nhóm lệnh tạo bằng chứng.
- Không phụ thuộc duy nhất vào một bước cuối dài.
- Dùng log store ngoài runner cho hệ thống cần bằng chứng bền vững.
- Phân biệt report thiếu do test chưa chạy với report mất do job bị hủy.

## 9. Fail fast trong shell script

Shell script có thể tiếp tục sau một lệnh thất bại nếu không được viết rõ. Một mẫu Bash thường dùng:

~~~bash
set -euo pipefail

./scripts/validate-inputs.sh
./mvnw --batch-mode -DskipTests package
./mvnw --batch-mode test
~~~

- `-e` yêu cầu shell thoát khi một số lệnh thất bại, nhưng có ngoại lệ trong điều kiện và cấu trúc điều khiển.
- `-u` làm lỗi khi tham chiếu biến chưa được đặt.
- `pipefail` giữ lỗi từ các lệnh bên trong pipeline shell.

Không nên xem `set -e` là cơ chế xử lý lỗi hoàn chỉnh. Nếu cần thu thập report hoặc chạy cleanup sau khi một lệnh fail, hãy lưu exit code và trả lại kết quả cuối đúng cách:

~~~bash
set +e
./mvnw --batch-mode verify
test_status=$?
./scripts/collect-test-reports.sh
report_status=$?
set -e

if [ "$test_status" -ne 0 ]; then
  exit "$test_status"
fi

exit "$report_status"
~~~

Nếu bước thu thập report cũng là điều kiện bắt buộc, cần lưu và đánh giá cả hai exit code. Không để lệnh cleanup thành công ghi đè lỗi test ban đầu.

Với PowerShell, cần kiểm tra `$LASTEXITCODE` sau chương trình native và chủ động thoát với mã phù hợp. Không giả định một lệnh PowerShell tiếp theo sẽ giữ nguyên exit code của tiến trình trước.

## 10. Fail fast trong build tool và test runner

Các build tool có tùy chọn điều khiển cách xử lý khi một module hoặc task thất bại.

Với Maven reactor:

- `-ff` / `--fail-fast`: dừng reactor khi gặp lỗi đầu tiên.
- `-fae` / `--fail-at-end`: tiếp tục các module độc lập có thể chạy, rồi báo thất bại ở cuối.
- `-fn` / `--fail-never`: không làm build thất bại vì lỗi reactor; cần tránh dùng cho gate bắt buộc.

Với Gradle, hành vi mặc định dừng việc lập lịch các task phụ thuộc khi có lỗi; tùy chọn `--continue` cho phép tiếp tục những task không phụ thuộc vào task đã thất bại để thu thập thêm kết quả.

Chọn chế độ theo mục tiêu:

| Mục tiêu | Chiến lược phù hợp |
|---|---|
| Pull request cần phản hồi nhanh | Dừng sớm ở prerequisite hoặc module phụ thuộc |
| Monorepo có module độc lập | Tiếp tục module độc lập để có nhiều kết quả |
| Nightly regression | Thu thập đầy đủ kết quả và báo cáo |
| Release gate | Không bỏ qua bất kỳ lỗi bắt buộc nào |
| Điều tra lỗi môi trường | Có thể chạy lại có kiểm soát và giữ report từng lần |

Cần đọc tài liệu đúng phiên bản build tool và test runner. Một tùy chọn có thể thay đổi hành vi của cả reactor hoặc task graph; không áp dụng chỉ vì tên gọi có vẻ phù hợp.

## 11. Dừng sớm nhưng không bỏ qua kiểm tra bắt buộc

Fail fast quyết định thời điểm dừng công việc không còn ý nghĩa; nó không thay đổi danh sách điều kiện phải đạt.

Ví dụ, nếu lint fail, integration test phụ thuộc build có thể bị bỏ qua. Nhưng nếu security scan độc lập vẫn được thiết kế là required check, nhóm cần quyết định có tiếp tục scan để cung cấp phản hồi hay dừng toàn bộ theo policy. Dù chọn cách nào, kết quả cuối vẫn phải phản ánh lint fail.

Một số nguyên tắc:

- Không dùng `|| true`, `exit 0` hoặc `continue-on-error` để che lỗi bắt buộc.
- Job bị cancelled do fail-fast không được coi là pass.
- Job skipped do dependency failure phải được giải thích trong summary.
- Required gate cần kiểm tra đúng tập kết quả.
- Nếu công cụ không thể đưa ra kết luận, trạng thái là inconclusive hoặc failed theo policy.
- Chỉ publish/deploy khi mọi prerequisite bắt buộc đã đạt.

Một pipeline xanh phải có nghĩa mọi điều kiện bắt buộc đã được xác minh. Dừng sớm chỉ loại bỏ các bước không còn cần chạy; nó không hạ thấp tiêu chuẩn chất lượng.

## 12. Cân bằng fail fast với việc thu thập đủ chẩn đoán

Nếu dừng quá sớm ở lỗi đầu tiên, người phát triển có thể phải sửa từng lỗi theo nhiều vòng commit. Nếu chạy tất cả dù compile đã fail, thời gian và log có thể tăng mà không cung cấp thông tin hữu ích.

Cách cân bằng:

- Dừng các bước cần output không tồn tại hoặc không hợp lệ.
- Cho phép kiểm tra độc lập tiếp tục nếu có giá trị chẩn đoán.
- Dùng report có cấu trúc để hiển thị nhiều lỗi trong một lần chạy.
- Giới hạn thời gian và tài nguyên cho diagnostic job.
- Đưa log, test report và metadata vào artifact.
- Tách workflow PR nhanh khỏi nightly đầy đủ nếu mục tiêu khác nhau.

Ví dụ, một monorepo có 20 module độc lập. Nếu module A compile fail, không cần chạy integration test của A, nhưng module B đến T vẫn có thể chạy lint hoặc unit test. Dừng toàn bộ repository sẽ làm mất phản hồi của những nhóm không liên quan; tiếp tục mọi bước của module A lại lãng phí tài nguyên.

Fail fast nên áp dụng trên từng nhánh phụ thuộc, không nhất thiết là một công tắc toàn cục cho mọi job.

## 13. Retry không phải cách thay thế fail fast

Retry phù hợp với lỗi tạm thời có khả năng tự hồi phục, không phải lỗi logic xác định.

| Loại lỗi | Có nên retry? | Lý do |
|---|---|---|
| Compile error | Không | Cùng source sẽ tạo cùng lỗi |
| Assertion fail | Thường không | Cần sửa code hoặc test |
| Schema validation fail | Không | Input vẫn không hợp lệ |
| Registry timeout | Có giới hạn | Có thể là sự cố mạng tạm thời |
| HTTP 429/503 từ dependency | Có kiểm soát | Cần backoff và tôn trọng Retry-After |
| Runner mất kết nối | Có thể retry job | Cần xác minh job có tác dụng phụ hay không |
| Test flaky | Chỉ theo policy | Phải giữ kết quả lần đầu và đánh dấu flaky |
| Deploy timeout | Không retry mù | Có thể thao tác đã hoàn tất một phần |

Một retry policy nên có số lần tối đa, exponential backoff, jitter, timeout và điều kiện dừng. Không retry một thao tác không idempotent nếu chưa có idempotency key hoặc cơ chế kiểm tra trạng thái.

Không được retry vô hạn để biến một lỗi deterministic thành một pipeline xanh ngẫu nhiên. Nếu lần đầu fail và lần sau pass, cần giữ lại cả hai kết quả để điều tra flaky behavior.

## 14. Hủy workflow cũ khi có commit mới

Trong CI cho pull request, một commit mới có thể làm kết quả của workflow trước trở nên lỗi thời. Hủy workflow cũ giúp runner tập trung vào phiên bản source mới nhất.

Ví dụ GitHub Actions:

~~~yaml
concurrency:
  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
~~~

Cấu hình này gom các lần chạy cùng workflow và cùng pull request/ref vào một nhóm concurrency; khi có lần chạy mới, lần cũ có thể bị hủy.

Cần giới hạn phạm vi cẩn thận:

- Phù hợp với kiểm tra CI có thể chạy lại trên commit mới.
- Không áp dụng máy móc cho release workflow hoặc deploy đang thay đổi production.
- Không hủy một migration hoặc thao tác dữ liệu giữa chừng nếu chưa có cơ chế an toàn.
- Bảo đảm trạng thái cancelled không được hiểu là pass.
- Giữ lại bằng chứng cần thiết trước khi workflow bị thay thế.

Cancel stale run và fail-fast matrix là hai cơ chế khác nhau. Một cơ chế hủy lần chạy cũ vì có phiên bản mới; cơ chế kia dừng các job trong cùng ma trận khi một tổ hợp thất bại.

## 15. Quản lý timeout và tránh job treo

Fail fast cũng liên quan đến timeout. Một job không trả kết quả có thể giữ runner và làm pipeline chờ vô hạn nếu không có giới hạn.

Nên đặt timeout theo từng loại công việc:

- Lint và static check: ngắn.
- Compile/build: theo quy mô module và cache.
- Unit test: theo baseline thời gian của suite.
- Integration/E2E: dài hơn do cần service phụ trợ.
- Performance test: có thời lượng và tải được định nghĩa.
- Deploy: có timeout riêng cho rollout và health verification.

Timeout cần đủ rộng để không tạo false failure do runner chậm bất thường, nhưng đủ ngắn để giải phóng tài nguyên khi job bị treo. Khi timeout xảy ra, lưu log và trạng thái service nếu có thể.

Không dùng timeout như retry. Một job timeout có thể đã thực hiện một phần tác dụng phụ; trước khi chạy lại cần xác minh trạng thái hiện tại.

## 16. Quan sát và đo hiệu quả fail fast

Fail fast chỉ có ích nếu giảm thời gian phản hồi mà không làm mất quá nhiều thông tin cần thiết.

Nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Time to first failure | Thời gian từ khi bắt đầu đến lỗi quyết định đầu tiên |
| Time to feedback | Thời gian người phát triển nhận được kết quả |
| Wasted runner minutes | Thời gian runner dùng cho bước bị hủy hoặc không còn giá trị |
| Cancelled job count | Số job bị hủy do fail-fast hoặc commit mới |
| Diagnostic completeness | Tỷ lệ lỗi có report/log đủ để điều tra |
| Retry rate | Tỷ lệ job hoặc test cần retry |
| Flaky test rate | Tỷ lệ test không ổn định |
| False cancellation | Số trường hợp hủy làm mất kết quả cần thiết |
| Pipeline duration | Thời gian tổng thể theo loại workflow |

Nếu cancelled job tăng mạnh nhưng time to feedback không giảm, có thể fail-fast được bật ở sai cấp hoặc thường xuyên hủy các job độc lập có giá trị. Nếu diagnostic completeness giảm, cần cải thiện cách lưu log và report trước khi dừng job.

So sánh theo loại workflow và kích thước thay đổi. Không nên tối ưu một con số trung bình duy nhất nếu nightly, pull request và release pipeline có mục tiêu khác nhau.

## 17. Ví dụ thiết kế CI nhanh cho pull request và đầy đủ cho nightly

Pull request thường ưu tiên phản hồi nhanh. Nightly có thể ưu tiên độ bao phủ và báo cáo đầy đủ.

| Workflow | Mục tiêu | Cách dừng |
|---|---|---|
| Pull request | Phản hồi sớm cho thay đổi | Fail fast ở build và matrix khi phù hợp |
| Main branch | Xác minh thay đổi đã merge | Chạy required gates; giữ diagnostics |
| Nightly | Tìm regression đa môi trường | Có thể tắt matrix fail-fast để thu đủ kết quả |
| Release qualification | Chứng minh artifact đủ điều kiện phát hành | Không bỏ qua required checks |
| Incident reproduction | Thu thập bằng chứng | Chạy phạm vi kiểm tra được kiểm soát, giữ mọi attempt |

Không nên dùng kết quả nightly để thay thế required check của commit hiện tại nếu artifact, source hoặc môi trường khác nhau. Mỗi kết quả cần gắn với commit và run identity cụ thể.

## 18. Checklist áp dụng fail fast

Trước khi bật hoặc thay đổi fail-fast policy, hãy kiểm tra:

- [ ] Đã xác định prerequisite và quan hệ phụ thuộc giữa các job.
- [ ] Kiểm tra nhanh, ổn định và có tính quyết định được ưu tiên.
- [ ] Lỗi deterministic không bị retry vô ích.
- [ ] Bước phụ thuộc vào output thất bại được dừng.
- [ ] Kiểm tra độc lập có giá trị chẩn đoán được cân nhắc tiếp tục.
- [ ] Matrix fail-fast được chọn theo mục tiêu phản hồi nhanh hay cần kết quả đầy đủ.
- [ ] Job cancelled/skipped không bị coi là success.
- [ ] Report và log được thu thập khi test fail.
- [ ] Script giữ nguyên exit code và không che lỗi.
- [ ] Required gates vẫn được kiểm tra trước publish/deploy.
- [ ] Retry có giới hạn, backoff và điều kiện idempotency.
- [ ] Workflow cũ chỉ bị hủy khi thao tác có thể hủy an toàn.
- [ ] Timeout phù hợp từng loại job.
- [ ] Có metric để đánh giá time to feedback và diagnostic completeness.
- [ ] Pull request, nightly và release có policy phù hợp với mục tiêu riêng.

Fail fast hiệu quả khi pipeline biết chính xác lỗi nào đã đủ để loại bỏ thay đổi, bước nào phụ thuộc vào kết quả đó và bằng chứng nào vẫn cần giữ lại. Dừng đúng phần công việc không còn giá trị giúp phản hồi nhanh hơn, tiết kiệm runner và vẫn bảo đảm mọi required gate phản ánh trung thực kết quả của thay đổi.

