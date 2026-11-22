# Hủy công việc lỗi thời khi chưa gây tác động cần giữ

Trong CI/CD, một commit mới có thể xuất hiện khi pipeline của commit trước vẫn đang chạy. Một pull request được cập nhật nhiều lần có thể tạo ra nhiều lượt kiểm thử; một nhánh bị đóng có thể để lại job đang chờ; một release candidate mới có thể khiến công việc chuẩn bị cũ không còn giá trị. Nếu cứ để mọi job chạy đến hết, hệ thống lãng phí runner, kéo dài hàng đợi và có thể tạo ra kết quả cũ gây nhầm lẫn.

Hủy công việc lỗi thời (cancel stale work) là việc dừng những job hoặc pipeline không còn đại diện cho trạng thái mong muốn mới nhất. Tuy nhiên, không phải công việc nào cũng có thể bị hủy tùy ý. Một job đang chạy unit test thường có thể dừng ngay; một job đã publish package, chạy database migration hoặc thay đổi production có thể đã tạo tác động cần giữ và phải được xử lý theo quy trình riêng.

Nguyên tắc cốt lõi là **hủy sớm công việc còn an toàn để hủy, đồng thời bảo vệ các hành động có side effect bằng điểm kiểm tra, tính idempotent, khóa và cơ chế chống job cũ tiếp tục ghi dữ liệu**.

## 1. Nhận diện công việc lỗi thời

Một job hoặc pipeline trở nên lỗi thời khi đầu vào hoặc mục tiêu mà nó đại diện đã bị thay thế, thu hồi hoặc không còn được phép thực hiện.

Các tình huống thường gặp:

- Pull request nhận commit mới trong khi test của commit cũ vẫn chạy.
- Người dùng push nhiều commit liên tiếp; các pipeline trung gian không còn cần thiết.
- Nhánh hoặc pull request bị đóng, xóa hoặc chuyển sang trạng thái không cần kiểm tra nữa.
- Một pipeline được chạy lại (rerun) và lượt chạy mới thay thế kết quả của lượt cũ.
- Release candidate mới được tạo trước khi job publish candidate cũ bắt đầu.
- Một job phụ thuộc vào kết quả upstream đã bị hủy hoặc thất bại.
- Người vận hành yêu cầu dừng rollout hoặc thu hồi một release request.
- Lịch chạy định kỳ tạo ra các lần thực thi chồng lấn, trong đó chỉ lần mới nhất còn hữu ích.

Không phải mọi job cũ đều lỗi thời. Ví dụ, một pipeline đang tạo báo cáo audit cho release đã phát hành vẫn có thể cần hoàn tất dù một release mới hơn đã xuất hiện. Cần xác định giá trị của công việc theo mục tiêu, loại trigger và trạng thái side effect, không chỉ dựa vào thời điểm bắt đầu.

### Freshness và identity của một lần chạy

Để nhận diện đúng công việc cũ, cần gắn job với định danh đầu vào rõ ràng:

- Repository, branch hoặc pull request ID.
- Commit SHA hoặc immutable revision.
- Pipeline/run ID và attempt number.
- Release ID hoặc artifact digest.
- Environment và deployment target nếu job có thể thay đổi runtime.
- Generation/version của yêu cầu nếu hệ thống điều phối có khái niệm phiên bản mới nhất.

Không dùng tên branch hoặc tag mutable làm bằng chứng duy nhất cho nội dung đang chạy. Cùng một branch có thể trỏ tới commit khác sau mỗi lần push; tag cũng có thể bị di chuyển nếu repository không bảo vệ tag. Job cần ghi nhận commit SHA đã checkout và kiểm tra lại freshness trước khi thực hiện hành động có side effect.

## 2. Phân biệt cancel, fail, skip, timeout và rollback

Các trạng thái này mang ý nghĩa vận hành khác nhau:

| Trạng thái/hành động | Ý nghĩa | Ví dụ |
|---|---|---|
| Cancel | Chủ động yêu cầu dừng một job/pipeline đang chờ hoặc đang chạy | Hủy test của commit cũ khi PR đã có commit mới |
| Fail | Job kết thúc do lỗi thực thi hoặc điều kiện không đạt | Unit test thất bại hoặc build command trả exit code khác 0 |
| Skip | Job không được chạy vì điều kiện hoặc dependency không thỏa | Job deploy staging bị bỏ qua khi nhánh không phải `main` |
| Timeout | Hệ thống dừng job do vượt giới hạn thời gian | Integration test không hoàn tất trong 20 phút |
| Rollback | Thực hiện hành động bù để đưa hệ thống về trạng thái trước đó hoặc trạng thái ổn định | Deploy lại image digest cũ sau khi release mới gây lỗi |
| Compensation | Thực hiện thao tác nghiệp vụ đối ứng để xử lý side effect đã xảy ra | Hủy reservation hoặc hoàn giao dịch theo quy trình nghiệp vụ |

Cancel không tự động hoàn tác những gì job đã làm. Nếu job đã gửi email, tạo cloud resource, publish package hoặc cập nhật database, việc dừng process chỉ ngăn các bước tiếp theo; tác động đã hoàn thành có thể vẫn tồn tại. Muốn phục hồi cần rollback hoặc compensation có chủ đích.

Tương tự, job bị cancel không nhất thiết là lỗi sản phẩm. Báo cáo pipeline cần phân biệt `cancelled` với `failed`, nếu không tỷ lệ lỗi sẽ bị tính sai và người phát triển khó hiểu vì sao công việc dừng.

## 3. Phân loại công việc theo mức độ an toàn khi hủy

Trước khi bật tự động hủy, hãy xác định job có thể dừng ở đâu và những tác động nào đã xảy ra.

| Loại công việc | Khả năng hủy | Cách xử lý gợi ý |
|---|---|---|
| Lint, unit test, static analysis | Thường an toàn | Hủy ngay khi đầu vào bị thay thế; lưu trạng thái cancelled |
| Build artifact trong workspace tạm | Thường an toàn nếu output chưa được publish | Dừng process, xóa workspace tạm và artifact chưa phát hành |
| Integration test với tài nguyên ephemeral | An toàn nếu có cleanup | Dừng test, hủy container/database tạm và thu hồi dữ liệu test |
| Benchmark/performance test | Có thể hủy nhưng cần dừng load generator và cleanup | Dừng phát tải, chờ worker kết thúc, ghi nhận dữ liệu chưa đầy đủ |
| Publish package/image | Cần kiểm soát | Kiểm tra upload đã hoàn tất chưa; dùng version/digest bất biến và xử lý trạng thái dở dang |
| Ký artifact hoặc phát hành release | Cần kiểm soát | Bảo vệ signing operation, xác minh trạng thái và tránh tạo release một phần |
| Database migration | Rủi ro cao | Chỉ hủy tại checkpoint an toàn; thiết kế migration có thể tiếp tục hoặc có compensation |
| Deploy/rollout production | Rủi ro cao | Không dùng latest-wins tùy tiện; cần pause/abort policy và xác minh trạng thái runtime |
| Gửi thông báo hoặc thao tác bên ngoài | Side effect có thể không thu hồi được | Dùng idempotency key, outbox hoặc compensation phù hợp |

Một job được đánh dấu `interruptible` chỉ cho hệ thống điều phối biết nó có thể bị dừng; điều đó không chứng minh script bên trong đã xử lý cleanup hoặc rollback đúng. Người thiết kế pipeline phải xác định ranh giới an toàn ở cấp thao tác.

## 4. Chọn chính sách hủy theo mục tiêu công việc

Có ba chính sách thường dùng:

### Latest wins — chỉ giữ công việc mới nhất

Phù hợp với công việc kiểm tra trạng thái hiện tại, chẳng hạn lint/test của pull request. Khi commit mới xuất hiện, pipeline cũ bị hủy để runner tập trung vào revision mới nhất.

Không phù hợp với mọi công việc phát hành. Nếu một pipeline đang deploy production, commit mới xuất hiện không có nghĩa deployment hiện tại nên bị giết ngay. Việc hủy giữa chừng có thể để lại rollout một phần hoặc làm trạng thái runtime không rõ ràng.

### Queue/serialize — chạy lần lượt

Phù hợp với migration, deployment hoặc thao tác trên một tài nguyên dùng chung. Các lần chạy được xếp hàng hoặc chỉ một lần chạy được phép vào critical section tại một thời điểm.

Queue không tự giải quyết freshness. Khi một job tới lượt, nó vẫn phải kiểm tra yêu cầu còn hợp lệ hay đã bị release mới thay thế. Nếu đã lỗi thời trước khi bắt đầu side effect, job nên kết thúc mà không thực hiện hành động.

### Deduplicate — gộp công việc trùng

Phù hợp với tác vụ có cùng input và cùng kết quả mong muốn, ví dụ tạo report hoặc tính checksum cho cùng artifact digest. Hệ thống có thể dùng idempotency key hoặc cache kết quả để tránh thực hiện trùng.

Deduplication cần khóa theo nội dung đầu vào và phạm vi tài nguyên. Hai job có cùng tên nhưng khác commit hoặc khác environment không nên bị gộp nhầm.

| Mục tiêu | Chính sách thường phù hợp | Ví dụ |
|---|---|---|
| Phản hồi nhanh cho PR | Latest wins | Chỉ giữ test của commit mới nhất |
| Deploy một environment | Serialize/queue và kiểm tra freshness | Một deployment production tại một thời điểm |
| Tạo report cho artifact | Deduplicate theo digest | Một SBOM cho cùng image digest |
| Migration database | Serialize + lock + checkpoint | Không chạy hai migration đồng thời |
| Nightly batch | Queue hoặc bỏ lần cũ theo policy | Không chạy chồng hai lần đồng bộ cùng dataset |

## 5. Xác định điểm kiểm tra freshness trước side effect

Hủy job đang chạy là thao tác bất đồng bộ. Có thể có khoảng thời gian từ lúc hệ thống gửi tín hiệu cancel tới lúc process thực sự dừng. Job cũ vẫn có thể chạy thêm một vài lệnh hoặc tiếp tục gọi API nếu không kiểm tra trạng thái.

Vì vậy, các job có side effect cần tự xác minh rằng chúng vẫn được phép thực hiện trước mỗi ranh giới quan trọng.

Ví dụ các điểm kiểm tra:

1. Trước khi tải hoặc sử dụng credential đặc quyền.
2. Trước khi publish package hoặc tạo release tag.
3. Trước khi bắt đầu migration hoặc ghi dữ liệu dùng chung.
4. Trước khi chuyển traffic hoặc cập nhật workload production.
5. Trước khi gửi thông báo bên ngoài hoặc kích hoạt workflow downstream.

### Dùng generation hoặc revision token

Một hệ thống điều phối có thể cấp một generation tăng dần cho mỗi yêu cầu. Job chỉ được ghi nếu generation của nó vẫn là generation hiện hành.

Ví dụ logic giả mã:

```text
request = get_current_release_request(service)
my_generation = request.generation

run_tests_and_prepare_candidate()

if get_current_generation(service) != my_generation:
    cancel_without_side_effect()
    return

publish_candidate()

if get_current_generation(service) != my_generation:
    stop_before_deploy()
    record_published_but_superseded()
    return

deploy_approved_digest()
```

Kiểm tra freshness cần diễn ra gần thời điểm side effect. Nếu kiểm tra xong rồi chờ lâu mới ghi, một yêu cầu mới có thể xuất hiện trong khoảng giữa (time-of-check to time-of-use race). Với hệ thống phân tán, cần kết hợp generation token với lock hoặc fencing token để ngăn job cũ tiếp tục ghi sau khi mất quyền.

### Fencing token

Fencing token là số phiên bản tăng đơn điệu do hệ thống cấp khi một worker nhận quyền thực hiện critical section. Tài nguyên đích lưu token lớn nhất đã chấp nhận và từ chối thao tác có token thấp hơn.

Ví dụ:

- Worker A nhận token 41 nhưng bị treo.
- Lease của A hết hạn; worker B nhận token 42 và thực hiện cập nhật.
- Worker A tỉnh lại và gửi lệnh cũ với token 41.
- Tài nguyên từ chối token 41 vì đã chấp nhận token 42.

Fencing bảo vệ tài nguyên trước worker cũ còn chạy sau khi lease hết hạn. Một distributed lock đơn thuần không luôn bảo đảm điều này nếu client cũ vẫn có thể gửi request sau khi mất lease.

## 6. Hủy job có cleanup và graceful shutdown

Khi nhận tín hiệu cancel, job nên dừng nhận công việc mới, kết thúc hoặc hủy các tiến trình con, thu hồi tài nguyên tạm và ghi lại trạng thái. Thứ tự cleanup phụ thuộc loại job.

Một quy trình graceful cancellation thường gồm:

1. Nhận tín hiệu dừng từ CI runner hoặc orchestrator.
2. Đánh dấu job không nhận thêm request/task mới.
3. Dừng phát tải, consumer hoặc worker con.
4. Chờ các thao tác đang ở critical section hoàn tất nếu có thể.
5. Xóa workspace/container/database tạm hoặc giải phóng tài nguyên được tạo cho job.
6. Thu hồi credential tạm và xóa file nhạy cảm theo chính sách.
7. Ghi trạng thái cancelled, reason, checkpoint và side effect đã hoàn thành.
8. Thoát trong grace period; nếu không, runner có thể buộc kết thúc process.

Không phải cleanup nào cũng nên chạy khi cancel. Ví dụ, xóa artifact đã publish hoặc xóa database production không phải cleanup an toàn. Cleanup phải giới hạn vào tài nguyên tạm mà job sở hữu và có thể xác định chắc chắn.

### Ví dụ shell xử lý tín hiệu dừng

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

WORK_DIR="${RUNNER_TEMP:-/tmp}/build-${CI_JOB_ID:-local}"
mkdir -p "$WORK_DIR"

cleanup() {
  local exit_code=$?
  trap - EXIT
  ./ci/stop-test-workers.sh || true
  rm -rf -- "$WORK_DIR"
  exit "$exit_code"
}

trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

./ci/run-isolated-tests.sh --work-dir "$WORK_DIR"
```

Ví dụ minh họa cleanup cho workspace và worker thử nghiệm. Trong hệ thống thật, cần bảo đảm `stop-test-workers.sh` có thể nhận diện đúng process group/container do job tạo ra và không đụng tới tài nguyên dùng chung. Runner có thể gửi SIGTERM rồi SIGKILL sau grace period; shell, process con và executor không phải lúc nào cũng xử lý tín hiệu giống nhau. Cần kiểm tra hành vi hủy trên executor đang dùng.

## 7. Idempotency và xử lý side effect dở dang

Một job có thể bị hủy sau khi server đã nhận request nhưng trước khi client nhận phản hồi. Khi retry, job không biết thao tác trước đã thành công hay chưa. Nếu thực hiện lại mà không có kiểm soát, hệ thống có thể tạo duplicate.

Các mẫu thiết kế hữu ích:

- **Idempotency key:** gắn khóa duy nhất với một yêu cầu nghiệp vụ; server trả lại kết quả cũ khi nhận cùng khóa thay vì thực hiện lần hai.
- **Transactional write:** cập nhật dữ liệu và trạng thái công việc trong cùng transaction khi có thể.
- **Outbox pattern:** ghi sự kiện cần gửi vào outbox trong transaction, worker gửi sau và đánh dấu đã xử lý.
- **Checkpoint:** lưu tiến độ để job mới có thể tiếp tục từ bước an toàn.
- **Compensation:** thực hiện thao tác đối ứng khi side effect đã xảy ra và không thể rollback trực tiếp.
- **Reconciliation:** đọc trạng thái thật từ hệ thống đích trước khi quyết định retry hoặc tiếp tục.

Ví dụ publish image: nếu upload hoàn tất nhưng job bị hủy trước khi ghi report, job mới nên tra registry theo digest và xác minh nội dung đã tồn tại trước khi upload lại. Không tạo version khác hoặc ghi đè tag chỉ vì lần chạy trước bị đánh dấu cancelled.

Ví dụ gửi email: nếu provider đã nhận yêu cầu nhưng pipeline mất kết nối trước khi nhận response, hủy job không thu hồi email. Cần idempotency key hoặc outbox để tránh gửi trùng.

## 8. Khóa và điều phối tài nguyên dùng chung

Khi nhiều job có thể thay đổi cùng một target, cần cơ chế serialize hoặc lock. Ví dụ hai pipeline cùng deploy service `orders` vào production hoặc hai migration cùng cập nhật schema database.

Một lock an toàn cần:

- Scope rõ ràng: lock theo service, environment, database hoặc resource cụ thể.
- Owner identity: biết job/run nào đang giữ lock.
- Lease/TTL: lock không tồn tại vĩnh viễn nếu worker chết.
- Renewal: worker đang hoạt động có thể gia hạn lease theo policy.
- Fencing token: ngăn worker cũ ghi sau khi lease hết hạn và lock được cấp cho worker khác.
- Release có kiểm tra owner: job không được giải phóng lock của job khác.
- Timeout/wait policy: quy định job chờ bao lâu và xử lý ra sao khi không lấy được lock.

Không nên dùng một lock toàn cục cho mọi pipeline nếu chỉ một số tài nguyên cần tuần tự hóa; điều đó làm giảm concurrency không cần thiết. Ngược lại, lock quá hẹp có thể để hai job cùng thay đổi một tài nguyên chung.

### Concurrency group trong GitHub Actions

Với kiểm tra pull request, có thể hủy run cũ khi run mới cho cùng PR xuất hiện:

```yaml
name: Pull request checks

on:
  pull_request:

concurrency:
  group: pr-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./ci/verify.sh
```

Ở đây, nhóm concurrency gắn với PR number để các lần chạy của cùng một PR thay thế nhau. Cần dùng policy khác cho release/deployment. GitHub Actions concurrency group giới hạn số run cùng group đang chạy/chờ; run chờ có thể bị thay thế khi có run mới và thứ tự không phải hàng đợi FIFO. Vì vậy, đây không phải cơ chế bảo đảm mọi release đều được thực hiện theo thứ tự.

Với production deployment, thường không nên bật `cancel-in-progress: true` một cách máy móc:

```yaml
name: Production deployment

on:
  workflow_dispatch:

concurrency:
  group: deploy-production-orders
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - run: ./ci/check-release-is-current.sh
      - run: ./ci/deploy-approved-digest.sh
      - run: ./ci/verify-deployment.sh
```

Group trên giúp tránh nhiều workflow cùng nhóm chạy đồng thời, nhưng không tự tạo FIFO queue cho mọi release. Job vẫn cần kiểm tra release còn hiệu lực và dùng approval/artifact digest đã xác định. Nếu phải bảo đảm mọi release được xử lý tuần tự, cần cơ chế queue có semantics phù hợp.

### Auto-cancel redundant pipeline trong GitLab CI

GitLab hỗ trợ đánh dấu job có thể bị hủy và cấu hình auto-cancel khi có commit mới. Ví dụ minh họa:

```yaml
workflow:
  auto_cancel:
    on_new_commit: interruptible

unit_tests:
  stage: test
  interruptible: true
  script:
    - ./gradlew test --no-daemon

build_candidate:
  stage: build
  interruptible: true
  script:
    - ./gradlew assemble --no-daemon

deploy_production:
  stage: deploy
  interruptible: false
  script:
    - ./ci/deploy-approved-digest.sh
```

`interruptible: true` phù hợp với job có thể dừng an toàn như test và build tạm. Job deploy được đánh dấu `false` để auto-cancel redundant pipeline không tùy tiện ngắt nó khi đã bắt đầu. Hành vi chi tiết phụ thuộc phiên bản GitLab và cấu hình `workflow:auto_cancel`; hãy kiểm tra tài liệu phiên bản đang chạy. Việc đánh dấu `false` không thay thế quy trình pause/abort deployment có chủ đích.

## 9. Không hủy nhầm công việc đã tạo tác động cần giữ

Một số bước có thể vượt qua ranh giới không thể hủy an toàn. Hãy xác định điểm commit (commit point) của từng hành động.

| Hành động | Ranh giới cần chú ý | Cách xử lý khi có yêu cầu cancel mới |
|---|---|---|
| Build trong workspace | Trước khi upload/publish artifact | Hủy process và dọn output tạm |
| Publish package | Khi registry đã nhận manifest/layer hoặc version | Kiểm tra trạng thái theo digest; hoàn tất metadata hoặc đánh dấu candidate superseded |
| Tạo release/tag | Khi tag hoặc release đã được công bố | Không xóa tùy tiện; dùng deprecate/yank theo policy và ghi audit |
| Database migration | Khi transaction/DDL đã commit hoặc dữ liệu đã biến đổi | Hoàn tất bước an toàn, dừng ở checkpoint hoặc chạy compensation/roll-forward |
| Deploy rollout | Khi một phần replica đã nhận phiên bản mới | Pause rollout và đánh giá trạng thái; không giết process mà bỏ mặc trạng thái runtime |
| Gửi event/payment | Khi hệ thống đích đã chấp nhận yêu cầu | Dùng idempotency/reconciliation/compensation |
| Backup/restore | Khi snapshot hoặc restore operation đang chạy | Dùng API điều khiển có trạng thái; không xóa file đang được hệ thống sử dụng |

Một job cũ đã publish artifact có thể không còn được deploy, nhưng artifact vẫn có thể cần giữ để audit hoặc điều tra. “Superseded” không có nghĩa “xóa ngay”. Cần tách trạng thái release khỏi retention của bằng chứng.

## 10. Hủy công việc phụ thuộc trong pipeline DAG

Pipeline thường là đồ thị phụ thuộc (DAG). Khi một job upstream bị hủy, các job downstream cần được xử lý theo dependency và điều kiện chạy.

- Job downstream cần kết quả upstream để chạy thì nên bị skip/cancel khi dependency không còn hợp lệ.
- Job cleanup hoặc thu thập diagnostics có thể vẫn cần chạy khi upstream fail/cancel.
- Job publish/deploy không được chạy chỉ vì một điều kiện `always` nếu gate bắt buộc chưa đạt.
- Job tổng hợp report có thể cần chạy với trạng thái cancelled để lưu nguyên nhân và artifact diagnostics.

Ví dụ GitHub Actions:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./ci/test.sh

  publish:
    needs: test
    if: needs.test.result == 'success'
    runs-on: ubuntu-latest
    steps:
      - run: ./ci/publish.sh

  collect-diagnostics:
    needs: test
    if: always()
    runs-on: ubuntu-latest
    steps:
      - run: ./ci/collect-diagnostics.sh
```

`publish` chỉ chạy khi test thành công. `collect-diagnostics` có thể chạy để thu thập thông tin sau trạng thái kết thúc, nhưng script phải xử lý trường hợp workspace hoặc artifact không tồn tại. `always()` không nên dùng cho deploy hoặc publish nếu nó có thể bỏ qua gate bắt buộc.

## 11. Hủy theo sự kiện và hủy theo trạng thái mong muốn

Có hai cách xác định job cũ:

- **Event-based:** khi nhận sự kiện mới, gửi cancel cho các run cũ trong cùng nhóm. Cách này đơn giản và phù hợp với PR checks.
- **State-based:** trước khi thực hiện side effect, job hỏi nguồn sự thật hiện tại xem yêu cầu của nó còn là yêu cầu được chấp nhận không. Cách này cần thiết khi sự kiện có thể đến trễ, bị gửi lặp hoặc chạy không theo thứ tự.

Ví dụ, webhook commit B có thể tới trước webhook commit A dù A được tạo trước. Nếu hệ thống chỉ dựa vào thứ tự nhận sự kiện, job A có thể bị coi là mới nhất nhầm. State-based freshness dùng commit/generation hiện hành để xác định chính xác.

Đối với deployment, nguồn sự thật có thể là release record đã được phê duyệt, desired state trong GitOps repository hoặc một deployment controller. Job cần so sánh với nguồn đó ngay trước khi thay đổi target.

## 12. Theo dõi cancellation và lý do dừng

Cancellation cần có metadata để phân biệt hủy chủ động, timeout, runner mất kết nối và lỗi thực thi.

Nên ghi:

- Job/run ID, attempt và commit SHA.
- Nhóm concurrency hoặc resource lock liên quan.
- Lý do cancel: superseded, PR closed, manual stop, timeout, dependency cancelled hoặc policy.
- Ai/điều kiện nào yêu cầu cancel.
- Thời điểm gửi signal, thời điểm process dừng và cleanup hoàn tất.
- Side effect đã hoàn thành hoặc trạng thái cần reconciliation.
- Artifact tạm được giữ/xóa và tài nguyên được cleanup.
- Job mới thay thế nếu có, cùng revision/generation của nó.

Các chỉ số hữu ích:

- Số job stale được hủy và thời gian runner được giải phóng.
- Tỷ lệ cancellation trước/sau khi bắt đầu side effect.
- Thời gian từ yêu cầu cancel tới khi process dừng.
- Số cleanup thất bại hoặc tài nguyên tạm bị rò rỉ.
- Số duplicate side effect do retry/cancel race.
- Số deployment bị pause/abort và thời gian đưa target về trạng thái ổn định.

Nếu tỷ lệ cancellation quá cao, có thể pipeline đang bị trigger dư thừa, người dùng push nhiều commit nhỏ hoặc concurrency group được định nghĩa quá rộng. Cần phân tích nguyên nhân thay vì chỉ tăng runner capacity.

## 13. Kiểm thử chính sách hủy

Không nên chỉ kiểm tra YAML có `cancel-in-progress: true`. Cần thử các race condition và trạng thái thực tế.

Các tình huống nên kiểm tra:

1. Push commit mới khi unit test cũ đang chạy: job cũ dừng và job mới chạy đúng SHA.
2. Push commit mới khi build đang tạo file tạm: process dừng, workspace được dọn và không publish artifact dở dang.
3. Cancel đến ngay sau khi publish hoàn tất: registry vẫn có artifact đúng digest và release record phản ánh trạng thái thực tế.
4. Hai job deploy cùng service: chỉ một job được vào critical section; job còn lại chờ hoặc bị đánh dấu superseded theo policy.
5. Worker mất lease nhưng vẫn tiếp tục chạy: fencing token khiến ghi cũ bị từ chối.
6. Cancel trong lúc migration: hệ thống dừng ở checkpoint an toàn hoặc tiếp tục/compensate theo thiết kế.
7. Runner bị mất kết nối: controller reconcile trạng thái và không giả định job đã cleanup.
8. Pull request bị đóng: job kiểm thử bị dừng, nhưng job thu thập audit/diagnostics cần thiết vẫn lưu kết quả.
9. Job mới bị hủy sau khi đã thay thế job cũ: policy xác định có khởi chạy lại hay không, tránh để không còn job hợp lệ.
10. Cancel lặp hoặc webhook gửi trùng: hệ thống xử lý idempotent và không tạo side effect trùng.

## 14. Anti-pattern thường gặp

- **Bật cancel-in-progress cho mọi workflow:** có thể ngắt deployment, migration hoặc publish giữa chừng.
- **Coi cancel là rollback:** process dừng nhưng side effect đã xảy ra vẫn còn.
- **Chỉ kiểm tra freshness lúc job bắt đầu:** job có thể lỗi thời trước khi ghi dữ liệu hoặc deploy.
- **Dùng tên branch thay commit SHA:** job cũ có thể checkout hoặc publish nội dung không xác định.
- **Dựa vào lock không có fencing:** worker cũ có thể tiếp tục ghi sau khi lease hết hạn.
- **Cleanup xóa mọi output:** có thể xóa artifact đã phát hành hoặc bằng chứng cần lưu.
- **Không dừng process con:** shell đã thoát nhưng test server hoặc load generator vẫn chạy.
- **Đánh dấu mọi job interruptible:** hệ thống điều phối có thể hủy một bước không an toàn.
- **Dùng `always()` cho side effect downstream:** job publish/deploy có thể chạy sau khi gate bị hủy hoặc thất bại.
- **Coi concurrency group là FIFO queue:** run chờ có thể bị thay thế; thứ tự không được bảo đảm.
- **Không reconcile trạng thái sau timeout/cancel:** hệ thống không biết request đã được đích chấp nhận hay chưa.
- **Không ghi cancellation reason:** khó phân biệt pipeline lỗi với công việc được thay thế hợp lệ.

## 15. Checklist thiết kế hủy công việc lỗi thời

Trước khi bật auto-cancel, hãy kiểm tra:

1. Job đại diện cho trạng thái nào và khi nào nó trở nên lỗi thời?
2. Định danh freshness có dùng commit SHA, run ID, attempt và target rõ ràng không?
3. Job có thể hủy an toàn ở giai đoạn nào? Điểm commit/side effect nằm ở đâu?
4. Chính sách là latest-wins, queue/serialize hay deduplicate? Vì sao?
5. Job có kiểm tra freshness lại ngay trước side effect không?
6. Các thao tác có side effect có idempotency key, checkpoint hoặc compensation không?
7. Tài nguyên dùng chung có lock, lease và fencing phù hợp không?
8. Runner có dừng process con và cleanup tài nguyên tạm trong grace period không?
9. Artifact đã publish và audit evidence có được giữ đúng retention không?
10. Job downstream có điều kiện rõ để skip/cancel; diagnostics có được thu thập khi cần không?
11. Deployment/migration có quy trình pause/abort riêng thay vì bị hủy tùy tiện không?
12. Cancellation reason, actor, thời gian và side effect có được ghi lại không?
13. Có kiểm thử race giữa cancel, retry, webhook trễ và worker mất lease không?
14. Có đo thời gian giải phóng runner, cleanup failure và duplicate side effect không?

Hủy công việc lỗi thời giúp CI/CD phản hồi nhanh và tiết kiệm tài nguyên, nhưng chỉ an toàn khi hiểu rõ trạng thái của job và tác động nó đã tạo. Hãy dùng latest-wins cho công việc kiểm tra có thể bỏ, queue/lock cho tài nguyên dùng chung, và freshness/idempotency/fencing cho hành động có side effect. Khi job cũ bị dừng đúng thời điểm, pipeline mới có thể tiến lên mà không để lại trạng thái nửa chừng hoặc ghi đè kết quả mới bằng một công việc đã lỗi thời.
