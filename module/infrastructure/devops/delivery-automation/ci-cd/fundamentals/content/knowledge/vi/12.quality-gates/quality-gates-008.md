# Tránh cho phép bỏ qua lỗi làm pipeline thành công giả

Một pipeline CI/CD màu xanh thường được hiểu là thay đổi đã vượt qua các kiểm tra bắt buộc. Nhưng màu xanh chỉ có ý nghĩa khi mọi lỗi quan trọng đều được truyền đến kết quả cuối cùng. Nếu một lệnh kiểm thử thất bại nhưng script vẫn trả mã thoát thành công, một job bị bỏ qua nhưng cổng chất lượng không nhận ra, hoặc một bước scan được cấu hình cho phép lỗi mà không có ngoại lệ được phê duyệt, pipeline có thể báo thành công dù sản phẩm chưa đạt yêu cầu.

Đó là **thành công giả (false success)**: trạng thái cuối của pipeline không phản ánh đúng kết quả kiểm tra. Để tránh tình trạng này, cần thiết kế đường truyền trạng thái từ lệnh chạy đến job, từ job đến workflow và từ workflow đến chính sách merge hoặc phát hành. Mọi kiểm tra bắt buộc phải có kết quả rõ ràng; việc bỏ qua hoặc cho phép lỗi phải là quyết định có chủ đích, có phạm vi và có dấu vết.

## 1. Hiểu đúng trạng thái của pipeline

Một pipeline có nhiều lớp trạng thái. Lỗi có thể bị che ở bất kỳ lớp nào nếu hệ thống không truyền kết quả đúng cách.

| Lớp | Trạng thái cần quan sát | Ví dụ lỗi bị che |
|---|---|---|
| Process/command | Exit code của lệnh | Test trả mã khác 0 nhưng script chạy tiếp rồi kết thúc bằng 0 |
| Step | Thành công, thất bại, skipped, cancelled | Step được đặt continue-on-error |
| Job | Thành công, thất bại, skipped, cancelled | Job cho phép lỗi hoặc phụ thuộc vào job không chạy |
| Workflow/pipeline | Kết quả tổng hợp | Job quan trọng không nằm trong điều kiện của gate cuối |
| Repository policy | Required checks và quyền merge | Branch protection không yêu cầu đúng check |
| Release policy | Điều kiện promotion và phê duyệt | Deploy chạy dù scan hoặc test chưa có kết quả hợp lệ |

Không nên đồng nhất các trạng thái sau:

- **Success:** tác vụ hoàn thành và đạt điều kiện.
- **Failure:** tác vụ chạy nhưng không đạt điều kiện hoặc gặp lỗi.
- **Skipped:** tác vụ không được thực thi do điều kiện hoặc cấu hình.
- **Cancelled:** tác vụ bị hủy trước khi hoàn tất.
- **Neutral/Warning:** tác vụ đã chạy nhưng kết quả chỉ mang tính thông tin hoặc được chấp nhận theo chính sách.

Một bước skipped không tự động có nghĩa là lỗi. Có thể test frontend được bỏ qua khi chỉ thay đổi tài liệu. Nhưng nếu một kiểm tra bắt buộc bị skipped do điều kiện viết sai, pipeline không được coi đó là đạt. Cần phân biệt bỏ qua hợp lệ theo phạm vi với bỏ qua ngoài dự kiến.

## 2. Nguyên nhân thường tạo ra thành công giả

Những nguyên nhân phổ biến gồm:

1. Script làm mất exit code của lệnh kiểm thử.
2. Dùng continue-on-error, allow_failure hoặc cơ chế tương đương cho kiểm tra bắt buộc.
3. Job quan trọng bị skipped nhưng gate tổng không kiểm tra trạng thái.
4. Lệnh test không tìm thấy test nào nhưng vẫn trả thành công.
5. Bước publish report hoặc scan lỗi nhưng không được coi là điều kiện bắt buộc.
6. Pipeline chỉ kiểm tra một số job, bỏ quên job mới được thêm.
7. Workflow bị lọc theo branch/path khiến required check không được tạo hoặc cập nhật như dự kiến.
8. Branch protection không yêu cầu đúng status check.
9. Ngoại lệ tạm thời được thêm nhưng không có thời hạn hoặc người sở hữu.
10. Deploy được kích hoạt bởi một nhánh workflow khác không phụ thuộc vào kết quả gate.

Điểm chung là hệ thống không xác định đầy đủ điều kiện nào phải đạt trước khi chuyển tiếp. Cách sửa bền vững là lập danh sách kiểm tra bắt buộc, định nghĩa trạng thái được chấp nhận và tổng hợp kết quả tại một cổng cuối có thể kiểm chứng.

## 3. Không làm mất exit code của lệnh

Exit code là tín hiệu cơ bản để shell và CI biết một lệnh có thành công hay không. Theo quy ước phổ biến, mã 0 biểu thị thành công; mã khác 0 biểu thị lỗi hoặc trạng thái đặc biệt do chương trình định nghĩa.

### 3.1. Những cách vô tình che lỗi

Ví dụ sau luôn trả thành công nếu lệnh echo chạy được:

~~~bash
./mvnw --batch-mode verify
echo "Verification finished"
~~~

Trong shell không bật chế độ dừng khi lỗi, lệnh thứ hai có thể trở thành lệnh cuối và trả exit code 0, khiến CI không nhận ra Maven đã thất bại.

Các mẫu nguy hiểm khác:

~~~bash
./mvnw verify || true
~~~

~~~bash
./scripts/run-tests.sh
exit 0
~~~

~~~bash
./mvnw verify | tee test.log
~~~

Trong pipeline shell, lệnh cuối cùng thường quyết định exit code. Với ví dụ dùng tee, kết quả của tee có thể là 0 dù Maven đã thất bại.

### 3.2. Giữ nguyên exit code

Với Bash, có thể bật pipefail để pipeline trả lỗi nếu một lệnh bên trong thất bại:

~~~bash
set -o pipefail
./mvnw --batch-mode verify 2>&1 | tee test.log
~~~

Có thể dùng set -e cho script đơn giản, nhưng cần hiểu các ngoại lệ của shell khi lệnh nằm trong điều kiện, vòng lặp hoặc danh sách &&/||. Với script có xử lý lỗi riêng, hãy lưu và trả lại mã lỗi tường minh:

~~~bash
./mvnw --batch-mode verify
result=$?

if [ "$result" -ne 0 ]; then
  echo "Verification failed with exit code $result"
  exit "$result"
fi
~~~

Khi cần tiếp tục để thu thập bằng chứng, có thể tạm giữ mã lỗi rồi trả lại sau khi upload report:

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

Cách này cho phép thu thập báo cáo sau khi test fail mà vẫn giữ kết quả thất bại của test. Nếu test đạt nhưng bước thu thập report lỗi, job cũng thất bại để nhóm biết bằng chứng bắt buộc chưa được lưu.

Trong PowerShell, cần kiểm tra $LASTEXITCODE sau chương trình native và trả lại mã đó khi cần. Không giả định $? hoặc kết quả của một lệnh PowerShell tiếp theo luôn phản ánh exit code của chương trình trước.

## 4. Phân biệt bước thu thập bằng chứng với bước quyết định chất lượng

Bước upload report thường cần chạy ngay cả khi test thất bại. Điều đó không có nghĩa bước upload được phép biến test fail thành success.

Ví dụ trong GitHub Actions:

~~~yaml
- name: Run tests
  id: tests
  run: ./mvnw --batch-mode verify

- name: Upload test reports
  if: ${{ always() }}
  uses: actions/upload-artifact@v4
  with:
    name: test-reports-${{ github.run_id }}
    path: |
      **/target/surefire-reports/**
      **/target/failsafe-reports/**
    if-no-files-found: warn
~~~

always() giúp bước upload có cơ hội chạy sau khi test thành công hoặc thất bại. Job vẫn giữ trạng thái thất bại nếu bước test bắt buộc đã thất bại. Không đặt continue-on-error: true cho bước test chỉ để pipeline tiếp tục upload report.

Nếu report là đầu ra bắt buộc, cần có kiểm tra riêng để xác nhận file tồn tại và đọc được. if-no-files-found: warn chỉ cảnh báo khi thiếu file; nó không chứng minh rằng test đã chạy đủ. Với kiểm tra bắt buộc, gate phải biết vì sao report không có: test chưa chạy, cấu hình sai, hay suite thực sự không tạo report.

## 5. Dùng continue-on-error và allow_failure có kiểm soát

Các nền tảng CI có cơ chế cho phép một bước hoặc job lỗi mà không làm pipeline thất bại. Chúng hữu ích cho tác vụ mang tính thông tin, kiểm tra thử nghiệm hoặc công việc có ngoại lệ đã được chấp nhận. Nhưng nếu dùng cho quality gate bắt buộc, chúng có thể che lỗi.

Ví dụ GitHub Actions:

~~~yaml
- name: Required unit tests
  run: ./mvnw --batch-mode test
~~~

Không thêm continue-on-error: true vào bước trên nếu unit test là điều kiện bắt buộc.

Với một kiểm tra advisory, có thể cho phép lỗi nhưng phải công khai kết quả:

~~~yaml
- name: Experimental compatibility check
  id: compatibility
  continue-on-error: true
  run: ./scripts/check-next-runtime.sh

- name: Report advisory failure
  if: ${{ steps.compatibility.outcome == 'failure' }}
  run: echo "::warning::Experimental compatibility check did not pass"
~~~

Trong GitHub Actions, trường outcome của step phản ánh kết quả thực thi trước khi áp dụng continue-on-error; trường conclusion phản ánh kết luận sau khi áp dụng chính sách đó. Điều này cho phép hiển thị cảnh báo dù workflow tiếp tục. Hãy giữ advisory check tách khỏi danh sách gate bắt buộc.

GitLab CI có thuộc tính allow_failure; Jenkins có các cơ chế xử lý lỗi stage/build. Tên gọi khác nhau nhưng nguyên tắc giống nhau: chỉ cho phép lỗi khi đã xác định rõ kiểm tra đó không chặn merge hoặc release. Không dùng một cấu hình cho phép lỗi chung cho cả nhóm job có mức độ quan trọng khác nhau.

## 6. Định nghĩa rõ kiểm tra bắt buộc và kiểm tra advisory

Mỗi kiểm tra nên được phân loại trước khi đưa vào pipeline:

| Nhóm | Ví dụ | Khi không đạt |
|---|---|---|
| Required gate | Unit test, integration test bắt buộc, build, secret scan | Chặn merge hoặc promotion |
| Policy gate | Coverage tối thiểu, vulnerability threshold, license policy | Chặn theo ngưỡng đã công bố |
| Advisory check | Kiểm tra runtime thử nghiệm, benchmark tham khảo | Cảnh báo và lưu report |
| Conditional check | Kiểm thử module chỉ khi module đó thay đổi | Chạy theo phạm vi; nếu được yêu cầu thì phải có kết quả |
| Manual approval | Phê duyệt production release | Chờ người có thẩm quyền, không thay thế test |

Một kiểm tra advisory vẫn cần được báo cáo. Nếu chỉ bỏ qua kết quả của nó, nhóm sẽ không biết kiểm tra đã chạy hay chưa và có vấn đề gì.

Danh sách required gate cần được quản lý tập trung hoặc có quy ước rõ. Khi thêm một job mới, reviewer phải xác định job đó là bắt buộc, advisory hay conditional. Không để trạng thái mặc định tự quyết định mức độ quan trọng.

## 7. Xử lý job skipped và điều kiện chạy

Job có thể bị skipped vì nhiều lý do:

- Điều kiện if không thỏa mãn.
- Thay đổi không nằm trong module được kiểm tra.
- Job phụ thuộc vào job trước đó bị thất bại hoặc bị bỏ qua.
- Biến hoặc output điều khiển điều kiện không được tạo.
- Workflow bị lọc theo branch hoặc path.
- Một bước setup không hoàn thành nên các bước sau không chạy.

Với job bắt buộc, skipped phải được xem là chưa đạt trừ khi chính sách quy định rõ trường hợp bỏ qua hợp lệ.

Ví dụ GitHub Actions: nếu job tổng hợp chỉ chạy theo điều kiện mặc định success(), nó có thể bị skipped sau khi một job phụ thuộc thất bại. Khi đó, check tổng hợp không còn cơ hội xác nhận kết quả. Có thể dùng if: always() cho gate cuối để nó kiểm tra trạng thái của các job phụ thuộc.

Cần đặc biệt cẩn thận với paths và paths-ignore ở cấp workflow. Với workflow được cấu hình làm required check, một số trường hợp workflow bị bỏ qua do filter có thể khiến check không được cập nhật như mong đợi và giữ trạng thái pending. Có thể dùng workflow luôn được kích hoạt rồi điều kiện hóa các job bên trong, đồng thời để gate cuối quyết định job nào phải chạy theo phạm vi thay đổi.

Không nên coi mọi trạng thái skipped là success. Cần có bảng chính sách cho từng job và từng loại event.

## 8. Tạo một gate cuối để kiểm tra toàn bộ kết quả

Một workflow nhiều job nên có một job cuối chuyên tổng hợp kết quả. Job này cần phụ thuộc vào tất cả kiểm tra bắt buộc và xác minh trạng thái từng job trước khi trả success.

Ví dụ GitHub Actions:

~~~yaml
name: CI quality gates

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./scripts/lint.sh

  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./mvnw --batch-mode test

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./mvnw --batch-mode verify -Pintegration

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./scripts/security-scan.sh

  quality-gate:
    if: ${{ always() }}
    needs:
      - lint
      - unit-tests
      - integration-tests
      - security-scan
    runs-on: ubuntu-latest
    steps:
      - name: Enforce required results
        env:
          LINT_RESULT: ${{ needs.lint.result }}
          UNIT_RESULT: ${{ needs.unit-tests.result }}
          INTEGRATION_RESULT: ${{ needs.integration-tests.result }}
          SECURITY_RESULT: ${{ needs.security-scan.result }}
        run: |
          failed=0

          for result in "$LINT_RESULT" "$UNIT_RESULT" "$INTEGRATION_RESULT" "$SECURITY_RESULT"; do
            if [ "$result" != "success" ]; then
              echo "Required check did not pass: $result"
              failed=1
            fi
          done

          exit "$failed"
~~~

Trong ví dụ này, quality-gate được yêu cầu chạy sau khi các job liên quan kết thúc, kể cả khi một job thất bại hoặc bị skipped. Nó chỉ trả thành công khi tất cả kết quả bắt buộc là success. Nếu một job bị skipped, cancelled hoặc failure, gate sẽ thất bại.

Khi có job conditional hợp lệ, không nên đơn giản bỏ job đó khỏi danh sách mà không giải thích. Hãy đưa chính sách vào gate: ví dụ chỉ chấp nhận skipped khi event và phạm vi thay đổi chứng minh module không bị ảnh hưởng. Điều kiện chấp nhận phải có thể kiểm tra và được review.

Nếu danh sách job thay đổi, cần cập nhật needs và kiểm tra gate cùng lúc. Một job mới không được tự động coi là đã được kiểm soát chỉ vì workflow vẫn có màu xanh.

## 9. Không để job phụ thuộc làm mất trạng thái lỗi

Job downstream thường chỉ chạy khi các job upstream thành công. Đây là hành vi hữu ích để tiết kiệm tài nguyên, nhưng gate cuối cần quan sát được cả những job đã thất bại hoặc bị bỏ qua.

Ví dụ:

~~~yaml
package:
  needs: [unit-tests, integration-tests]
  runs-on: ubuntu-latest
  steps:
    - run: ./mvnw --batch-mode package
~~~

Nếu test fail, package có thể bị skipped. Điều đó hợp lý vì không nên đóng gói một phiên bản chưa đạt test. Nhưng kết quả tổng phải cho thấy test fail là nguyên nhân chặn pipeline; không được chỉ hiển thị package skipped rồi coi như không có lỗi.

Job tổng hợp dùng always() và needs đầy đủ sẽ giúp phân biệt:

- Job đã chạy và thất bại.
- Job không chạy vì phụ thuộc thất bại.
- Job không chạy do điều kiện hợp lệ.
- Job bị hủy.
- Job chưa có kết quả.

Gate không nên chỉ kiểm tra một job cuối như package hoặc deploy. Nó phải kiểm tra toàn bộ tập điều kiện bắt buộc.

## 10. Kiểm tra trường hợp không có test hoặc report rỗng

Một lệnh test có thể trả thành công dù không tìm thấy test nào, tùy framework và cấu hình. Điều này nguy hiểm khi pipeline cần bảo đảm một suite cụ thể đã chạy.

Các trường hợp cần kiểm soát:

- Test discovery tìm thấy 0 test.
- Module bị bỏ khỏi danh sách test do filter sai.
- Test profile không được kích hoạt.
- Test report rỗng hoặc không hợp lệ.
- Test bị skip toàn bộ do assumption hoặc cấu hình.
- Integration service không khởi động nhưng test suite vẫn không thực thi.
- Coverage report không được tạo nhưng gate vẫn so sánh số liệu cũ.

Cần định nghĩa tối thiểu số test hoặc loại suite phải chạy khi áp dụng. Ví dụ, nếu module có test bắt buộc, report phải thể hiện số test lớn hơn 0. Với Maven Surefire/Failsafe, có thể cấu hình tùy chọn fail khi không tìm thấy test theo phiên bản plugin đang dùng; cần xác minh đúng property của plugin và không áp dụng một cách máy móc cho module hợp lệ không có test.

Không dùng report cũ từ cache hoặc lần chạy trước để thay thế report của commit hiện tại. Report phải gắn với run ID, commit SHA và job hiện tại.

## 11. Kiểm tra chất lượng phải thất bại khi công cụ không thể đưa ra kết luận

Một số bước scan hoặc kiểm tra có thể trả trạng thái thành công vì công cụ không chạy được, cấu hình thiếu hoặc không tìm thấy dữ liệu đầu vào. Cần phân biệt:

- **Pass:** kiểm tra đã chạy và kết quả đạt.
- **Fail:** kiểm tra đã chạy và phát hiện vi phạm.
- **Inconclusive:** không thể đưa ra kết luận do lỗi công cụ, thiếu dữ liệu hoặc cấu hình.
- **Skipped:** không chạy theo chính sách.
- **Approved exception:** có ngoại lệ được chấp thuận với phạm vi cụ thể và thời hạn.

Với gate bắt buộc, inconclusive không được tự động chuyển thành pass. Ví dụ, nếu secret scanner không truy cập được repository hoặc dependency scanner không tải được database lỗ hổng, pipeline phải thể hiện kiểm tra chưa hoàn tất. Nhóm có thể retry theo giới hạn, dùng nguồn dữ liệu dự phòng hoặc chặn promotion cho đến khi có kết quả.

Không nên viết script chỉ kiểm tra xem file report có tồn tại. File có thể rỗng, cũ hoặc không thuộc commit hiện tại. Cần kiểm tra định dạng, thời điểm, run identity và trạng thái kết quả bên trong report.

## 12. Quản lý ngoại lệ mà không mở đường bỏ qua vô thời hạn

Không phải mọi cảnh báo đều có thể sửa ngay. Một số dự án cần chấp nhận rủi ro có giới hạn trong thời gian ngắn. Ngoại lệ phải được quản lý như một quyết định có chủ sở hữu, không phải một dòng cấu hình được thêm rồi quên.

Một ngoại lệ nên có:

| Trường | Nội dung |
|---|---|
| Rule/check | Kiểm tra hoặc quy tắc được miễn |
| Scope | Repository, module, nhánh hoặc phiên bản bị ảnh hưởng |
| Reason | Lý do cần ngoại lệ |
| Owner | Người chịu trách nhiệm xử lý |
| Approver | Người có quyền chấp thuận |
| Created at | Thời điểm bắt đầu |
| Expires at | Thời hạn hết hiệu lực |
| Compensating control | Biện pháp giảm rủi ro tạm thời |
| Tracking issue | Công việc để loại bỏ ngoại lệ |

Khi hết hạn, pipeline phải tự động coi ngoại lệ là không còn hiệu lực và đưa gate trở lại trạng thái bắt buộc. Không dùng một biến như SKIP_SECURITY=true mà không giới hạn ai được đặt, đặt ở đâu và đến khi nào.

Nếu một ngoại lệ chỉ áp dụng cho một module, không nên vô hiệu hóa toàn bộ security scan của repository. Phạm vi miễn trừ phải hẹp nhất có thể và được ghi vào báo cáo.

## 13. Bảo vệ required checks và quy trình merge

Một quality gate chỉ có hiệu lực nếu repository thực sự yêu cầu nó trước khi merge.

Cần kiểm tra:

- Branch protection hoặc ruleset yêu cầu đúng status check.
- Tên check ổn định và không trùng lẫn giữa workflow.
- Required check được tạo trên đúng loại event.
- Không có job bắt buộc nào bị bỏ qua ngoài chính sách.
- Quyền bypass branch protection được giới hạn và có audit.
- Thay đổi workflow, script test và policy cũng được review.
- Pull request không thể tự thay đổi điều kiện để làm check luôn thành công.
- Merge queue hoặc cơ chế merge đặc biệt vẫn chạy các kiểm tra cần thiết.

Nếu required check đổi tên, repository có thể đang yêu cầu check cũ trong khi workflow mới chạy check khác. Khi thay đổi tên job hoặc workflow, cần cập nhật branch protection cùng một thay đổi có kiểm soát.

Không nên dựa vào màu xanh của một job bất kỳ trên giao diện. Hãy xác nhận chính check được branch protection yêu cầu là gate cuối đã kiểm tra đầy đủ các điều kiện.

## 14. Tách gate chất lượng khỏi phê duyệt thủ công

Phê duyệt của con người và kết quả kiểm tra tự động giải quyết hai vấn đề khác nhau.

- Test, build và scan xác minh các điều kiện kỹ thuật.
- Approval xác nhận người có thẩm quyền đồng ý với quyết định phát hành trong phạm vi trách nhiệm của họ.

Một người duyệt production không nên vô tình biến test fail thành pass. Nếu tổ chức cho phép phát hành trong trường hợp có rủi ro đã biết, phải ghi nhận ngoại lệ và người phê duyệt theo chính sách.

Luồng tham khảo:

~~~mermaid
flowchart TD
    A[Source commit] --> B[Lint và test]
    B --> C[Security và policy scan]
    C --> D[Kiểm tra report và metadata]
    D --> E{Tất cả required gates đạt?}
    E -- Không --> F[Chặn merge hoặc promotion]
    E -- Có --> G[Quality gate success]
    G --> H{Có yêu cầu approval?}
    H -- Có --> I[Người có thẩm quyền phê duyệt]
    H -- Không --> J[Promotion]
    I --> J
    J --> K[Deploy và post-deploy verification]
~~~

Gate thành công là điều kiện kỹ thuật để chuyển sang bước phê duyệt hoặc promotion. Approval không nên là cách bỏ qua kết quả kiểm thử bắt buộc.

## 15. Kiểm tra pipeline bằng các tình huống lỗi có chủ đích

Không chỉ kiểm tra đường chạy thành công. Hãy xác minh pipeline phản ứng đúng khi một điều kiện quan trọng thất bại.

| Tình huống thử | Kết quả mong đợi |
|---|---|
| Unit test trả exit code khác 0 | Job test thất bại, gate cuối thất bại |
| Script chạy test qua tee | pipefail giữ được exit code thất bại |
| Một required job bị skipped | Gate cuối thất bại trừ khi có chính sách skip hợp lệ |
| Security scanner không khởi động | Gate thể hiện inconclusive và chặn promotion |
| Không tìm thấy test bắt buộc | Job thất bại hoặc gate phát hiện số test bằng 0 |
| Report upload lỗi | Bằng chứng thiếu được thể hiện; policy quyết định có chặn hay không |
| Advisory check thất bại | Có warning/report, không thay đổi required gate |
| Ngoại lệ đã hết hạn | Gate không còn chấp nhận ngoại lệ |
| Workflow thay đổi tên check | Branch protection vẫn yêu cầu đúng check hiện hành |
| Pipeline bị hủy | Kết quả cancelled không bị coi là success |

Có thể dùng một nhánh thử nghiệm hoặc fixture để cố ý làm một test fail, rồi xác nhận trạng thái cuối cùng. Sau đó khôi phục điều kiện và xác minh đường chạy thành công. Không cần tạo lỗi trên môi trường production để kiểm tra gate.

## 16. Checklist ngăn thành công giả

Trước khi bật pipeline hoặc thay đổi quality gate, hãy kiểm tra:

- [ ] Lệnh test, build và scan trả exit code đúng.
- [ ] Script không dùng || true, exit 0 hoặc cách xử lý làm mất lỗi ngoài chủ đích.
- [ ] Shell pipeline có pipefail khi cần giữ lỗi từ lệnh trước.
- [ ] Required check không dùng continue-on-error hoặc allow_failure.
- [ ] Advisory check được phân loại và hiển thị warning rõ ràng.
- [ ] Bước upload report chạy cả khi test fail nhưng không ghi đè trạng thái test.
- [ ] Job cuối kiểm tra tất cả required jobs và không bỏ qua failure, skipped hoặc cancelled.
- [ ] Job conditional có chính sách chấp nhận skipped rõ ràng.
- [ ] Test suite bắt buộc không được âm thầm chạy 0 test.
- [ ] Report được xác minh thuộc đúng run và commit hiện tại.
- [ ] Scanner hoặc quality tool không chạy được sẽ trả trạng thái inconclusive.
- [ ] Ngoại lệ có owner, approver, scope và thời hạn.
- [ ] Branch protection yêu cầu đúng status check cuối.
- [ ] Quyền bypass và thay đổi workflow được kiểm soát.
- [ ] Có thử nghiệm xác nhận pipeline chuyển đỏ khi từng required gate thất bại.

Một quality gate đáng tin cậy phải bảo toàn kết quả từ lệnh gốc đến quyết định cuối. Khi lỗi không bị nuốt, trạng thái skipped được giải thích, kiểm tra bắt buộc không được cho phép lỗi và gate tổng xác minh đầy đủ các job, màu xanh của pipeline mới thực sự có ý nghĩa.

