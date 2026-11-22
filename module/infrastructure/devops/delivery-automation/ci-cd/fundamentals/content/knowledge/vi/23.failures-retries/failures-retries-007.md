# Dọn tài nguyên bằng cơ chế luôn được thực hiện khi kết thúc

Một pipeline CI/CD thường tạo ra nhiều tài nguyên tạm để build và kiểm thử: container, network, volume, database/schema, namespace Kubernetes, máy ảo, bucket, test account, process nền, port-forward hoặc lock. Nếu job thất bại giữa chừng và bỏ qua bước dọn dẹp, những tài nguyên này có thể tiếp tục tồn tại, tiêu tốn chi phí, giữ dữ liệu thử nghiệm hoặc ảnh hưởng lần chạy tiếp theo.

Vì vậy, cleanup cần được thiết kế như một phần của vòng đời công việc, không phải một lệnh tùy chọn ở cuối script. Cần có cơ chế finalizer được thực hiện khi luồng chính kết thúc dù thành công, thất bại hay bị hủy; tài nguyên phải có định danh và chủ sở hữu rõ ràng; thao tác xóa cần an toàn khi chạy lặp; và hệ thống phải có cách thu hồi tài nguyên mồ côi nếu runner bị mất hoặc bị kết thúc cưỡng bức.

Bài này tập trung vào việc dọn tài nguyên trong CI/CD. Các ví dụ bao gồm cleanup trong một process, finalizer ở cấp pipeline, bảo toàn exit code, xử lý lỗi cleanup, giới hạn của cơ chế luôn chạy và bộ dọn tài nguyên theo thời hạn (janitor).

## 1. Vì sao cleanup phải chạy ở mọi kết quả?

Một script thường được viết theo luồng tuần tự: tạo môi trường, chạy test, xóa môi trường. Cách này chỉ dọn được tài nguyên nếu mọi lệnh trước đó kết thúc theo đường đi dự kiến.

Ví dụ, nếu test trả mã lỗi và shell dừng do chế độ fail-fast, lệnh xóa cuối script có thể không chạy. Nếu người vận hành bấm Cancel, runner bị timeout hoặc một bước deploy thất bại, phần cleanup thông thường cũng có thể bị bỏ qua.

Tài nguyên bị bỏ lại có thể gây ra:

- Chi phí cloud hoặc container tiếp tục tăng.
- Namespace, database hoặc volume chiếm quota.
- Cổng mạng hoặc process nền gây xung đột với lần chạy sau.
- Dữ liệu test còn tồn tại và làm sai kết quả của test tiếp theo.
- Lock không được giải phóng khiến pipeline khác phải chờ.
- Credential tạm vẫn còn hiệu lực.
- Tài nguyên chứa dữ liệu nhạy cảm không được xóa đúng hạn.
- Runner hoặc môi trường dùng chung dần mất ổn định.

Cleanup đáng tin cậy giúp mỗi lần chạy có ranh giới tài nguyên riêng. Khi công việc kết thúc, những tài nguyên do nó tạo ra được giải phóng và trạng thái của lần chạy được ghi lại.

## 2. Finalizer là gì?

Finalizer là đoạn xử lý được đăng ký để chạy khi một phạm vi thực thi kết thúc, bất kể kết quả chính là thành công hay thất bại. Tùy công nghệ, cơ chế này có tên khác nhau:

- Shell có EXIT trap.
- Java hoặc C# có finally và cơ chế đóng tài nguyên.
- GitHub Actions có step condition dùng always().
- Jenkins Declarative Pipeline có post với always.
- GitLab CI có after_script.
- Azure Pipelines có condition always().

Các cơ chế này có phạm vi khác nhau. EXIT trap chỉ bảo vệ một shell process. finally bảo vệ một phạm vi chương trình. CI finalizer bảo vệ các bước trong job hoặc pipeline theo ngữ nghĩa của nền tảng.

Không nên giả định một finalizer có thể chạy trong mọi tình huống. Runner bị mất, máy chủ bị tắt, process nhận SIGKILL hoặc nền tảng dừng job ngay lập tức có thể khiến cleanup không được thực thi. Vì vậy, finalizer cần đi cùng nhãn sở hữu tài nguyên, TTL và một bộ dọn tài nguyên mồ côi độc lập.

## 3. Xác định tài nguyên thuộc quyền sở hữu của lần chạy

Trước khi tạo tài nguyên, pipeline cần xác định cách nhận diện tài nguyên đó và cách liên kết nó với một run cụ thể.

Một tài nguyên tạm nên có:

- Tên hoặc ID duy nhất.
- Run ID hoặc pipeline ID.
- Repository/project và service sở hữu.
- Job hoặc stage tạo tài nguyên.
- Thời điểm tạo.
- Thời điểm hết hạn (TTL).
- Loại tài nguyên.
- Môi trường hoặc namespace.
- Nhãn cho biết đây là tài nguyên tạm của CI.
- Chính sách cleanup hoặc owner chịu trách nhiệm.

Ví dụ nhãn logic:

```text
owner=ci
service=orders-api
run-id=1842
job=integration-test
created-at=2026-11-18T08:00:00Z
expires-at=2026-11-18T10:00:00Z
```

Tên và nhãn cần tuân theo quy tắc của hệ thống đích. Không dùng tên chung như test-db hoặc temp-namespace nếu nhiều pipeline có thể tạo cùng lúc.

Run ID giúp xác định tài nguyên nào thuộc lần chạy nào. TTL giúp hệ thống khác dọn tài nguyên nếu finalizer không bao giờ chạy.

## 4. Lập danh sách tài nguyên cần dọn

Không chỉ container hoặc database mới cần cleanup. Hãy liệt kê mọi thứ được tạo hoặc giữ trạng thái trong suốt job.

| Nhóm | Ví dụ | Hành động cleanup |
|---|---|---|
| Process | Server test, worker, tunnel, port-forward | Dừng process và xác minh đã thoát |
| Container | Container, network, volume | Stop rồi remove đúng tài nguyên của run |
| Kubernetes | Namespace, Job, Pod, temporary Secret | Xóa theo owner label và chờ có giới hạn |
| Database | Database, schema, test rows, temporary role | Drop hoặc xóa dữ liệu trong phạm vi sở hữu |
| Cloud | VM, disk, IP, load balancer, bucket | Xóa resource ID cụ thể |
| Lock | Deployment lock, migration lock, lease | Release hoặc để lease hết hạn theo thiết kế |
| Credential | Token, certificate, temporary account | Revoke hoặc chờ hết hạn ngắn |
| File | Thư mục tạm, socket, report tạm | Xóa file thuộc workspace/run |
| Network | Proxy, tunnel, firewall rule tạm | Đóng kết nối và gỡ rule được tạo |
| Test data | Tenant, user, order, fixture | Xóa theo namespace hoặc run ID |

Danh sách này nên được ghi trong thiết kế job. Nếu một bước tạo tài nguyên nhưng không có owner, ID hoặc phương án xóa, tài nguyên đó có nguy cơ trở thành orphan.

## 5. Đăng ký cleanup ngay khi bắt đầu

Cleanup handler nên được đăng ký trước khi bắt đầu tạo tài nguyên. Nếu chỉ đăng ký sau khi tạo xong, một lỗi giữa lúc tạo và lúc đăng ký có thể để lại tài nguyên không được quản lý.

Trình tự an toàn:

1. Khởi tạo biến lưu ID tài nguyên.
2. Đăng ký finalizer.
3. Tạo tài nguyên với owner label và TTL.
4. Lưu ID ngay khi API trả về.
5. Chạy công việc chính.
6. Finalizer đọc ID đã lưu và thực hiện cleanup.
7. Ghi kết quả cleanup.

Khi tài nguyên được tạo bằng nhiều API call, hãy lưu từng ID sau mỗi lần tạo thành công. Nếu tạo database thành công nhưng tạo network thất bại, finalizer vẫn cần biết database nào phải xóa.

Nếu thao tác tạo tài nguyên có thể hoàn tất ở phía server sau khi client timeout, cần tìm tài nguyên theo run ID hoặc idempotency key. Không giả định timeout có nghĩa là tài nguyên chưa được tạo.

## 6. Cleanup phải idempotent

Một cleanup operation là idempotent khi có thể chạy nhiều lần mà trạng thái cuối vẫn giống như chạy một lần. Đây là yêu cầu quan trọng vì finalizer có thể được retry, người vận hành có thể chạy lại hoặc janitor có thể dọn cùng tài nguyên sau đó.

Ví dụ:

- Xóa resource đã không tồn tại được xem là thành công.
- Gỡ network rule đã bị gỡ không tạo lỗi nghiêm trọng.
- Release lock chỉ giải phóng lock thuộc đúng owner.
- Xóa namespace không ảnh hưởng namespace của run khác.
- Revoke credential đã hết hạn hoặc đã bị revoke được xử lý an toàn.

Với API trả HTTP 404 khi resource không tồn tại, cleanup có thể coi đó là trạng thái đã đạt. Các lỗi 401/403 thường là lỗi quyền và cần báo rõ; không nên retry vô hạn. Lỗi 429, timeout hoặc 5xx có thể retry có giới hạn nếu thao tác xóa an toàn.

Idempotency không có nghĩa là bỏ qua mọi lỗi. Nếu API trả 500 hoặc quyền bị từ chối, tài nguyên có thể vẫn tồn tại. Cần phân biệt "đã không còn" với "không thể xác minh".

## 7. Chỉ xóa tài nguyên thuộc lần chạy hiện tại

Cleanup có thể nguy hiểm hơn bước tạo nếu dùng selector quá rộng. Một lệnh xóa mọi namespace có tiền tố test- có thể xóa nhầm tài nguyên của pipeline khác hoặc môi trường chia sẻ.

Nguyên tắc:

- Xóa theo resource ID đã lưu hoặc owner label chính xác.
- Kiểm tra owner/run ID trước khi xóa.
- Giới hạn quyền cleanup vào project, namespace hoặc resource group được phép.
- Không xóa resource dùng chung chỉ vì nó có tên giống tài nguyên tạm.
- Không dùng wildcard không có allowlist.
- Ghi lại ID và lý do trước khi xóa.
- Nếu không xác định chắc quyền sở hữu, dừng và báo lỗi thay vì đoán.

Tên resource có thể bị tái sử dụng. Một resource ID bất biến hoặc UID từ API đáng tin cậy an toàn hơn chỉ dựa vào tên hiển thị.

## 8. Ví dụ Bash với EXIT trap

Trong một Bash script, trap EXIT có thể gọi cleanup khi shell thoát bình thường, kể cả khi một lệnh làm shell thoát do fail-fast.

Ví dụ:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

RESOURCE_ID=""

cleanup() {
  local main_status=$?
  local cleanup_status=0

  trap - EXIT

  if [[ -n "$RESOURCE_ID" ]]; then
    ./scripts/delete-env.sh "$RESOURCE_ID" || cleanup_status=$?
  fi

  if (( main_status != 0 )); then
    if (( cleanup_status != 0 )); then
      printf 'Cleanup failed with status %s\n' "$cleanup_status" >&2
    fi
    exit "$main_status"
  fi

  exit "$cleanup_status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

RESOURCE_ID="$(./scripts/create-env.sh --owner "$CI_RUN_ID")"
test -n "$RESOURCE_ID"

./scripts/run-integration-tests.sh
```

Cách hoạt động:

- Handler EXIT được đăng ký trước khi tạo môi trường.
- Khi shell thoát, cleanup đọc exit status ban đầu.
- Nếu đã có RESOURCE_ID, script gọi lệnh xóa.
- trap - EXIT ngăn handler tự gọi lại khi hàm kết thúc bằng exit.
- Nếu công việc chính thất bại, script giữ nguyên mã lỗi chính.
- Nếu công việc chính thành công nhưng cleanup thất bại, script trả mã lỗi cleanup.
- INT và TERM được chuyển thành exit code; sau đó EXIT handler thực hiện cleanup.

Đây là mẫu cần điều chỉnh theo API tạo/xóa thực tế. Lệnh create nên gắn owner và TTL ngay từ đầu. Nếu resource được tạo nhưng process bị dừng trước khi ID được ghi ra stdout, finalizer không thể biết ID; janitor cần tìm theo owner/run ID để thu hồi.

## 9. Giữ nguyên lỗi chính khi cleanup cũng thất bại

Có hai lỗi có thể xảy ra trong cùng một lần chạy:

1. Công việc chính thất bại, ví dụ integration test trả mã 1.
2. Cleanup cũng thất bại, ví dụ API xóa database timeout.

Nếu cleanup thay thế exit code ban đầu, người vận hành có thể chỉ thấy lỗi xóa database mà bỏ qua nguyên nhân test thất bại. Ngược lại, nếu cleanup thất bại sau một công việc thành công mà không được ghi nhận, tài nguyên có thể bị bỏ lại trong khi pipeline báo xanh.

Nên định nghĩa chính sách rõ:

| Kết quả công việc chính | Kết quả cleanup | Trạng thái cuối |
|---|---|---|
| Thành công | Thành công | Thành công |
| Thất bại | Thành công | Giữ lỗi chính |
| Thất bại | Thất bại | Giữ lỗi chính và ghi cleanup failure riêng |
| Thành công | Thất bại | Thất bại hoặc cảnh báo theo mức độ rủi ro |
| Bị hủy | Thành công | Giữ trạng thái cancelled |
| Bị hủy | Thất bại | Giữ trạng thái cancelled và ghi tài nguyên có thể còn sót |

Với tài nguyên có chi phí hoặc rủi ro bảo mật cao, cleanup thất bại sau một công việc thành công nên làm job thất bại hoặc chuyển sang trạng thái cần xử lý. Với file tạm trong workspace đã bị xóa cùng runner, có thể chọn mức cảnh báo thấp hơn.

Không gộp cleanup status vào cùng một thông báo không cấu trúc. Hãy ghi primary result và cleanup result thành hai trường riêng.

## 10. Dùng try/finally trong ứng dụng hoặc công cụ viết bằng Java

Khi chương trình test tự tạo tài nguyên, có thể biểu diễn tài nguyên đó bằng AutoCloseable và dùng try-with-resources. Java sẽ gọi close khi rời khỏi phạm vi, kể cả khi thân khối ném exception.

Ví dụ:

```java
try (TemporaryEnvironment environment =
         provisioner.create("integration-test")) {
    testClient.runAgainst(environment.endpoint());
}
```

TemporaryEnvironment nên triển khai AutoCloseable và close phải an toàn khi gọi nhiều lần. Nếu thân khối và close cùng ném exception, try-with-resources giữ exception chính và gắn exception từ close dưới dạng suppressed exception. Nhờ đó, lỗi test không bị che mất khi cleanup cũng lỗi.

Nếu tài nguyên gồm nhiều đối tượng phụ thuộc nhau, đóng theo thứ tự ngược với thứ tự tạo. Ví dụ dừng worker trước, đóng connection pool sau, rồi mới xóa database hoặc network mà chúng đang sử dụng.

## 11. Dùng try/finally trong PowerShell

PowerShell hỗ trợ try/finally. Khối finally được thực hiện khi điều khiển rời khỏi try/catch theo các đường thực thi thông thường.

Ví dụ:

```powershell
$resourceId = $null

try {
    $resourceId = ./scripts/create-env.ps1 -Owner $env:CI_RUN_ID
    ./scripts/run-tests.ps1 -ResourceId $resourceId
}
finally {
    if ($resourceId) {
        ./scripts/delete-env.ps1 -ResourceId $resourceId
    }
}
```

Trong script thực tế, cần dùng ErrorActionPreference phù hợp và kiểm tra exit code của native executable. Nếu cleanup có thể ném exception, hãy ghi riêng lỗi cleanup và bảo toàn exception ban đầu. Không dùng finally để bỏ qua lỗi bằng cách nuốt mọi exception.

Giống shell trap, finally không chạy nếu process hoặc máy bị kết thúc cưỡng bức trước khi runtime có thể thực thi nó.

## 12. Finalizer ở cấp GitHub Actions

Mỗi step của GitHub Actions chạy trong process riêng. EXIT trap trong một step không bảo vệ các step tiếp theo và cũng không thay thế finalizer ở cấp job.

Có thể dùng step có điều kiện always() để chạy cleanup sau khi step trước thành công, thất bại hoặc job bị hủy theo khả năng nền tảng.

Ví dụ:

```yaml
jobs:
  integration:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - name: Create temporary environment
        id: environment
        shell: bash
        run: |
          resource_id="$(./scripts/create-env.sh --owner "$GITHUB_RUN_ID")"
          test -n "$resource_id"
          printf 'resource_id=%s\n' "$resource_id" >> "$GITHUB_OUTPUT"

      - name: Run integration tests
        run: ./scripts/run-integration-tests.sh

      - name: Always clean up
        if: ${{ always() }}
        timeout-minutes: 5
        env:
          RESOURCE_ID: ${{ steps.environment.outputs.resource_id }}
        run: |
          if [[ -n "$RESOURCE_ID" ]]; then
            ./scripts/delete-env.sh "$RESOURCE_ID"
          fi
```

always() là expression của GitHub Actions và được thay vào ví dụ ở vị trí điều kiện. Output của step tạo môi trường được lưu trong GITHUB_OUTPUT rồi tham chiếu ở step cleanup. Không dựa vào biến shell được export trong step trước vì mỗi step có process riêng.

Cần đặt timeout cho cleanup để job không chờ vô hạn. Nếu create step bị dừng sau khi resource đã được tạo nhưng trước khi output được ghi, step cleanup có thể không có ID. Owner label và TTL vẫn cần thiết để janitor tìm tài nguyên đó.

## 13. Jenkins Declarative Pipeline với post always

Jenkins Declarative Pipeline có khối post để chạy hành động sau các stage. Điều kiện always phù hợp cho cleanup cần thực hiện bất kể kết quả pipeline.

Ví dụ:

```groovy
pipeline {
    agent any

    stages {
        stage('Provision') {
            steps {
                script {
                    env.RESOURCE_ID = sh(
                        script: './scripts/create-env.sh --owner "$BUILD_TAG"',
                        returnStdout: true
                    ).trim()
                }
            }
        }

        stage('Test') {
            steps {
                sh './scripts/run-integration-tests.sh'
            }
        }
    }

    post {
        always {
            script {
                if (env.RESOURCE_ID?.trim()) {
                    withEnv(["RESOURCE_ID=${env.RESOURCE_ID}"]) {
                        sh './scripts/delete-env.sh "$RESOURCE_ID"'
                    }
                }
            }
        }
    }
}
```

Trong ví dụ, placeholder được thay bằng tham chiếu tới env.RESOURCE_ID của Jenkins. Nên dùng withEnv hoặc cơ chế truyền biến an toàn thay vì ghép ID vào chuỗi shell có thể bị diễn giải như mã. Resource ID nên được kiểm tra định dạng trước khi dùng.

post always chạy sau các stage theo ngữ nghĩa Jenkins, nhưng không thể bảo đảm cleanup khi agent hoặc controller mất khả năng thực thi. Có thể đặt timeout cho cleanup và vẫn dùng TTL/janitor làm lớp bảo vệ.

## 14. GitLab CI với after_script

GitLab CI cung cấp after_script để chạy lệnh sau script chính. Một điểm quan trọng là after_script chạy trong shell context riêng; biến shell được export trong script không tự động tồn tại trong after_script.

Có thể lưu resource ID vào file tạm có định dạng đơn giản rồi đọc lại trong after_script:

```yaml
integration:
  script:
    - RESOURCE_ID="$(./scripts/create-env.sh --owner "$CI_PIPELINE_ID")"
    - printf 'RESOURCE_ID=%s\n' "$RESOURCE_ID" > resource.env
    - ./scripts/run-integration-tests.sh

  after_script:
    - |
      if [ -f resource.env ]; then
        . ./resource.env
        if [ -n "$RESOURCE_ID" ]; then
          ./scripts/delete-env.sh "$RESOURCE_ID"
        fi
      fi

  artifacts:
    when: always
    paths:
      - resource.env
```

File resource.env chỉ nên chứa identifier đã được kiểm tra, không chứa token hoặc secret. Không source một file có thể bị người dùng không tin cậy chỉnh sửa. Nếu file đến từ artifact hoặc workspace có thể bị thay đổi, xác minh owner và định dạng ID trước khi dùng.

after_script có vòng đời và timeout riêng theo cấu hình GitLab Runner. Lỗi trong after_script không nhất thiết thay đổi exit status của script chính; nếu cleanup là điều kiện bắt buộc để job được coi là thành công, hãy thiết kế thêm bước kiểm tra trạng thái cleanup hoặc cơ chế thực thi phù hợp với phiên bản GitLab đang dùng. Cần kiểm tra tài liệu nền tảng và runner cụ thể về hành vi khi job bị cancel hoặc timeout.

## 15. Azure Pipelines với condition always()

Azure Pipelines cho phép đặt condition cho step. always() giúp step được đánh giá để chạy ngay cả khi các bước trước thất bại hoặc job bị hủy, theo giới hạn timeout và trạng thái agent.

Ví dụ:

```yaml
steps:
  - bash: |
      resource_id="$(./scripts/create-env.sh --owner "$BUILD_BUILDID")"
      echo "##vso[task.setvariable variable=resourceId]$resource_id"
    displayName: Create temporary environment

  - bash: ./scripts/run-integration-tests.sh
    displayName: Run integration tests

  - bash: |
      if [ -n "$RESOURCE_ID" ]; then
        ./scripts/delete-env.sh "$RESOURCE_ID"
      fi
    displayName: Always clean up
    condition: always()
    timeoutInMinutes: 5
    env:
      RESOURCE_ID: $(resourceId)
```

Biến task được chia sẻ qua cơ chế variable của Azure Pipelines, không phải do shell trước export. Nếu cần truyền output giữa job hoặc stage, dùng output variable và dependency mapping đúng phạm vi.

always() không thể chạy khi agent đã mất hoặc job bị kết thúc cứng. Đặt timeout và giữ TTL cho resource để xử lý trường hợp này.

## 16. So sánh các cơ chế finalizer

| Cơ chế | Phạm vi | Lưu ý |
|---|---|---|
| Bash EXIT trap | Một shell process | Không bắt được SIGKILL hoặc runner mất |
| Java try-with-resources | Một phạm vi tài nguyên trong JVM | Đóng tài nguyên theo thứ tự ngược; có suppressed exception |
| PowerShell finally | Một khối try/catch/finally | Không chạy nếu process bị kết thúc cưỡng bức |
| GitHub Actions always() | Step/job theo workflow condition | Cần truyền resource ID giữa steps; đặt timeout |
| Jenkins post always | Pipeline post section | Phụ thuộc agent/controller còn khả năng chạy |
| GitLab after_script | Phần hậu xử lý của job | Shell context riêng; timeout và exit-status semantics cần lưu ý |
| Azure Pipelines always() | Step/job condition | Vẫn phụ thuộc agent và giới hạn cancellation/timeout |

Không có một cơ chế nào tự bảo đảm cleanup trong mọi sự cố. Lựa chọn phù hợp phụ thuộc nơi tài nguyên được tạo và vòng đời của tài nguyên.

Nếu tài nguyên nằm trong một process, dùng finally hoặc EXIT trap. Nếu tài nguyên sống qua nhiều CI step, dùng finalizer cấp job. Nếu tài nguyên có thể sống lâu hơn runner, phải có TTL và janitor độc lập.

## 17. Dọn theo thứ tự phụ thuộc

Cleanup cần tôn trọng quan hệ phụ thuộc giữa các tài nguyên. Ví dụ, không xóa network trước khi container đang sử dụng nó được dừng.

Một thứ tự thường gặp:

1. Ngừng nhận công việc mới hoặc dừng traffic tới môi trường tạm.
2. Dừng test client, worker và process nền.
3. Thu thập log, report và evidence cần giữ.
4. Đóng connection, tunnel và port-forward.
5. Giải phóng lock hoặc lease.
6. Xóa dữ liệu test và credential tạm.
7. Xóa workload/container.
8. Xóa database, volume, network hoặc namespace.
9. Xác minh tài nguyên đã được giải phóng.
10. Ghi cleanup result và resource còn sót nếu có.

Thứ tự thực tế phụ thuộc hệ thống. Nếu cần log từ container để điều tra, phải thu thập trước khi xóa container. Nếu cleanup database cần một process migration đang chạy, dừng process đó trước.

Không xóa evidence hoặc artifact phát hành chỉ vì chúng được tạo trong cùng run. Chỉ dọn tài nguyên tạm thuộc ownership của job; report cần lưu theo retention policy riêng.

## 18. Dùng TTL để chống orphan resource

TTL (time to live) là thời hạn tối đa mà tài nguyên được phép tồn tại nếu không được gia hạn hoặc xóa sớm. Mỗi tài nguyên tạm nên có expiry time được ghi ở nơi hệ thống quản lý có thể truy vấn.

Ví dụ:

- Namespace CI có label run ID và annotation expires-at.
- Cloud resource có tag owner, run ID và TTL.
- Database/schema tạm có metadata ghi thời điểm hết hạn.
- Object storage prefix của test run có lifecycle rule.
- Credential tạm có expiry ngắn ngay khi cấp.

TTL cần phù hợp với thời gian job dự kiến cộng thêm khoảng dự phòng. Nếu TTL quá ngắn, janitor có thể xóa tài nguyên khi test vẫn chạy. Nếu TTL quá dài, orphan tồn tại và tiêu tốn tài nguyên.

Nếu job kéo dài, có thể gia hạn TTL bằng heartbeat hoặc lease. Việc gia hạn phải xác thực owner và giới hạn mức tối đa; không cho một job tùy ý giữ resource vô thời hạn.

## 19. Janitor độc lập để thu hồi tài nguyên mồ côi

Janitor là tiến trình hoặc scheduled job định kỳ tìm tài nguyên CI đã hết hạn rồi thu hồi chúng. Nó là lớp bảo vệ khi finalizer không chạy.

Một janitor an toàn nên:

- Chỉ tìm tài nguyên có nhãn CI được quản lý.
- Kiểm tra expires-at đã qua.
- Xác minh owner/run ID và loại tài nguyên.
- Bỏ qua tài nguyên có lease còn hiệu lực.
- Có chế độ dry-run hoặc báo cáo trước khi bật xóa tự động.
- Giới hạn số lượng xóa mỗi vòng.
- Ghi audit cho từng resource.
- Retry lỗi tạm thời có giới hạn.
- Cảnh báo khi không thể xóa hoặc resource không có metadata cần thiết.

Không xóa tài nguyên chỉ dựa trên việc job ID không còn tồn tại trong CI. Có thể job đang bị tạm dừng hoặc API trạng thái CI đang lỗi. TTL và lease cung cấp tín hiệu rõ hơn; với tài nguyên quan trọng, nên có grace period và kiểm tra lần cuối trước khi xóa.

Janitor nên dùng identity riêng chỉ có quyền xóa tài nguyên được gắn nhãn CI trong phạm vi cho phép. Không dùng quyền quản trị toàn cloud account nếu chỉ cần dọn một resource group hoặc namespace.

## 20. Xử lý trường hợp tạo tài nguyên thành công nhưng mất ID

Một tình huống khó là API đã tạo resource nhưng client timeout trước khi nhận response. Pipeline không có ID để đưa cho finalizer.

Có thể giảm rủi ro bằng cách:

- Gửi idempotency key dựa trên run ID khi API hỗ trợ.
- Gắn owner/run ID vào request tạo resource.
- Dùng tên duy nhất có thể tái tạo từ run ID.
- Sau timeout, truy vấn theo owner label trước khi thử tạo lại.
- Lưu ID ngay sau khi nhận response.
- Dùng janitor tìm tài nguyên quá hạn theo owner và TTL.

Không retry lệnh create một cách mù quáng nếu lần đầu có thể đã thành công. Retry tạo thêm VM, database hoặc namespace thứ hai có thể làm tăng chi phí và gây xung đột. Hãy kiểm tra resource theo idempotency key hoặc owner label trước.

## 21. Retry cleanup có giới hạn

Cleanup cũng có thể gặp lỗi tạm thời: API rate limit, network timeout, control plane bận hoặc tài nguyên đang được giải phóng bất đồng bộ.

Có thể dùng retry với backoff và jitter:

```text
attempt 1: wait 1 second
attempt 2: wait 2 seconds plus jitter
attempt 3: wait 4 seconds plus jitter
attempt 4: wait 8 seconds plus jitter
stop after the configured deadline
```

Các giá trị chỉ minh họa. Tổng thời gian retry phải nằm trong cleanup timeout. Không sleep lâu đến mức finalizer bị CI kill trước khi hoàn tất.

Phân loại lỗi:

| Lỗi | Xử lý |
|---|---|
| Resource đã không tồn tại | Coi là đã cleanup |
| Timeout hoặc lỗi mạng tạm thời | Retry có giới hạn |
| HTTP 429 hoặc 5xx | Backoff, tôn trọng retry hint nếu có |
| 401/403 | Dừng và báo lỗi quyền |
| Resource đang Terminating | Chờ có giới hạn rồi kiểm tra lại |
| Owner không khớp | Không xóa; báo mismatch |
| Resource ID không hợp lệ | Dừng, không đoán tên để xóa |
| Dependency vẫn đang dùng resource | Dừng consumer trước rồi thử lại |

Không retry vô hạn và không biến mọi lỗi thành success. Khi hết deadline, ghi rõ resource nào còn tồn tại để janitor hoặc người vận hành xử lý.

## 22. Cleanup khi job bị cancel hoặc timeout

Cancel có nhiều mức độ:

- Người dùng yêu cầu hủy và runner có thời gian xử lý tín hiệu.
- Job timeout và nền tảng bắt đầu kết thúc process.
- Agent mất kết nối nhưng tài nguyên bên ngoài vẫn chạy.
- Runner bị terminate cưỡng bức hoặc máy chủ bị tắt.
- Process nhận SIGKILL hoặc bị hệ điều hành dừng đột ngột.

Finalizer có cơ hội chạy trong một số trường hợp cancel mềm, nhưng không thể bảo đảm trong trường hợp runner hoặc process không còn hoạt động.

Nên thiết kế nhiều lớp:

1. EXIT trap hoặc finally cho process.
2. Finalizer cấp job cho CI workflow.
3. TTL trên tài nguyên.
4. Janitor độc lập.
5. Audit/cảnh báo khi cleanup không hoàn tất.

Đặt timeout riêng cho finalizer. Nếu job chính có timeout 30 phút, cleanup cần một khoảng thời gian hữu hạn bổ sung theo cấu hình nền tảng. Không giả định finalizer được cấp thời gian vô hạn sau khi cancel.

## 23. Cleanup credential, lock và process nền

Một số tài nguyên không phải cloud resource nhưng vẫn cần dọn.

**Credential:** revoke token hoặc certificate nếu có thể; nếu token ngắn hạn thì xác minh expiry và không ghi nó vào file lâu dài.

**Lock:** giải phóng lock chỉ khi owner token hoặc run ID khớp. Với distributed lock, dùng lease có expiry để process chết không giữ lock vô hạn.

**Process nền:** lưu PID hoặc process group ID, dừng đúng process thuộc run và chờ process thoát. Không dùng kill theo tên process chung vì có thể dừng service của job khác.

**Port-forward/tunnel:** giữ PID hoặc handle, đóng tunnel trước khi xóa network.

**Temporary files:** chỉ xóa thư mục được tạo trong workspace/run; không xóa đường dẫn được cấu hình từ input không tin cậy nếu chưa chuẩn hóa và xác minh.

Với process chạy trong container hoặc runner riêng, nên quản lý theo process group hoặc supervisor thay vì chỉ giữ PID của process cha. Child process có thể tiếp tục chạy sau khi parent thoát nếu không được quản lý đúng.

## 24. Lưu evidence của cleanup

Cleanup nên tạo một record riêng để biết tài nguyên nào đã được thu hồi và tài nguyên nào còn tồn tại.

Một record có thể gồm:

- Run ID, job ID và owner.
- Resource type và resource ID.
- Created-at và cleanup-started-at.
- Cleanup attempt count.
- Finalizer source: trap, finally, CI post step hoặc janitor.
- Kết quả: deleted, already-absent, failed, skipped hoặc orphaned.
- Error code và thông báo đã được làm sạch.
- Thời điểm hoàn tất.
- Người hoặc workload thực hiện.

Không ghi secret, connection string hoặc token vào cleanup report. Nếu cleanup thất bại, report nên chỉ rõ bước tiếp theo hoặc janitor sẽ thử lại lúc nào.

Evidence cũng giúp đo tỷ lệ tài nguyên mồ côi, thời gian dọn và lỗi permission. Nếu nhiều lần chạy để lại cùng một loại resource, có thể cần sửa cách tạo, gắn owner hoặc quyền cleanup.

## 25. Kiểm thử đường cleanup

Cleanup là một nhánh quan trọng và cần được kiểm tra chủ động. Chỉ test trường hợp pipeline thành công không chứng minh finalizer hoạt động khi thất bại.

Các tình huống nên thử:

- Công việc chính thành công.
- Unit/integration test thất bại.
- Provisioning thất bại giữa chừng.
- Cleanup được gọi hai lần.
- Resource đã bị xóa trước khi finalizer chạy.
- API delete timeout hoặc trả rate limit.
- Credential cleanup thiếu quyền.
- Job bị cancel trong lúc test.
- Runner bị kill để xác nhận janitor thu hồi orphan.
- Hai run chạy song song với resource riêng.
- Resource có cùng tên thân thiện nhưng khác owner.
- Cleanup timeout trong khi resource đang Terminating.

Kiểm tra rằng lỗi chính vẫn được giữ, cleanup failure được ghi riêng và không có resource của run khác bị xóa. Có thể dùng một resource test có TTL ngắn để diễn tập janitor.

Không cần cố tình kill production runner để kiểm thử. Dùng môi trường thử nghiệm và tài nguyên có thể tái tạo.

## 26. Các anti-pattern thường gặp

| Cách làm chưa tốt | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ đặt lệnh delete cuối script | Bị bỏ qua khi lệnh trước thất bại | Đăng ký trap/finally/finalizer ngay từ đầu |
| Cho rằng always() bảo đảm tuyệt đối | Runner mất vẫn để lại resource | Kết hợp TTL và janitor |
| Cleanup theo tên chung hoặc wildcard | Có thể xóa nhầm tài nguyên khác | Dùng resource ID và owner label chính xác |
| Cleanup không idempotent | Retry tạo lỗi hoặc tác dụng phụ | Xem resource đã vắng mặt là trạng thái đạt |
| Cleanup ghi đè exit code chính | Che mất nguyên nhân lỗi ban đầu | Lưu primary và cleanup status riêng |
| Bỏ qua cleanup failure sau job xanh | Resource rò rỉ nhưng pipeline báo xanh | Chính sách fail/warn theo mức độ rủi ro |
| Export biến ở step trước rồi dùng ở step sau | Biến không tồn tại trong process mới | Dùng output/variable/file theo cơ chế CI |
| GitLab after_script dựa vào biến shell của script | Không có resource ID trong shell mới | Lưu ID vào file an toàn hoặc metadata |
| Retry delete vô hạn | Job treo hoặc vượt timeout | Backoff có giới hạn và deadline |
| Xóa tài nguyên trước khi thu thập report | Mất log và evidence điều tra | Thu thập dữ liệu cần giữ trước cleanup |
| Không gắn TTL | Orphan có thể tồn tại vô thời hạn | Tag expiry và chạy janitor |
| Janitor dùng quyền admin rộng | Một lỗi selector có thể gây xóa diện rộng | Identity riêng và scope tối thiểu |
| Không kiểm tra owner trước khi xóa | Có thể thu hồi tài nguyên của run khác | Xác minh run ID/lease/owner |

## 27. Lộ trình đưa cleanup vào pipeline

Có thể chuẩn hóa theo các bước:

1. **Kiểm kê tài nguyên:** liệt kê process, container, database, namespace, cloud resource, credential, lock và file tạm.
2. **Định nghĩa owner:** mỗi resource có run ID, job ID, loại resource và TTL.
3. **Đăng ký finalizer sớm:** trap, finally hoặc CI post step được thiết lập trước khi provision.
4. **Lưu resource ID:** ghi ngay sau khi tạo và truyền qua output hoặc file phù hợp với nền tảng.
5. **Viết cleanup idempotent:** xóa đúng owner, xử lý already-absent và retry có giới hạn.
6. **Bảo toàn lỗi chính:** tách primary status với cleanup status.
7. **Đặt timeout:** giới hạn thời gian cleanup và chờ xóa bất đồng bộ.
8. **Tạo janitor:** tìm resource hết TTL, kiểm tra owner rồi thu hồi.
9. **Ghi evidence:** lưu resource, attempt, kết quả và lỗi.
10. **Diễn tập failure path:** test fail, cancel, timeout, runner loss và delete API lỗi.
11. **Theo dõi orphan:** cảnh báo khi resource vượt TTL hoặc cleanup failure tăng.

Bắt đầu với một job integration test tạo namespace hoặc database tạm. Khi cơ chế hoạt động ổn định, áp dụng cùng quy ước owner/TTL/finalizer cho các loại tài nguyên khác.

## 28. Đo hiệu quả cleanup

Các chỉ số hữu ích:

- Tỷ lệ run hoàn tất cleanup thành công.
- Số resource còn tồn tại sau TTL.
- Thời gian từ job kết thúc đến khi resource bị xóa.
- Số lần finalizer thất bại và nhóm lỗi.
- Số resource được janitor thu hồi.
- Chi phí phát sinh từ orphan resource.
- Tỷ lệ cleanup retry thành công.
- Số lần cleanup nhầm hoặc owner mismatch.
- Số job bị fail chỉ vì cleanup.
- Tỷ lệ run có resource ID và owner label đầy đủ.

Không chỉ tối ưu tỷ lệ cleanup success bằng cách bỏ qua lỗi xóa. Hãy đo cả resource tồn tại thực tế và khả năng thu hồi sau khi finalizer không chạy.

## 29. Checklist trước khi dùng tài nguyên tạm trong CI

- [ ] Tài nguyên có ID hoặc tên duy nhất theo run.
- [ ] Owner label và TTL được gắn ngay khi tạo.
- [ ] Finalizer được đăng ký trước khi provision.
- [ ] Resource ID được lưu ngay sau khi tạo.
- [ ] Cleanup chỉ xóa tài nguyên đúng owner.
- [ ] Cleanup có thể chạy lặp an toàn.
- [ ] Resource đã vắng mặt được xử lý như trạng thái đạt.
- [ ] Lỗi cleanup được ghi riêng với lỗi công việc chính.
- [ ] Chính sách xác định cleanup failure làm fail hay warn.
- [ ] Timeout và retry deadline được giới hạn.
- [ ] Tài nguyên phụ thuộc được dọn theo đúng thứ tự.
- [ ] Report/log cần giữ được thu thập trước khi xóa.
- [ ] CI finalizer phù hợp với nền tảng và phạm vi job.
- [ ] Biến hoặc resource ID được truyền qua cơ chế đúng của CI.
- [ ] Có TTL và janitor cho trường hợp runner mất.
- [ ] Janitor kiểm tra owner, lease và expiry trước khi xóa.
- [ ] Cleanup identity có quyền tối thiểu.
- [ ] Có test cho failure, cancellation, retry và orphan recovery.
- [ ] Cleanup evidence không chứa secret hoặc dữ liệu nhạy cảm.

## Kết luận

Dọn tài nguyên đáng tin cậy cần nhiều lớp bảo vệ. Trap, finally và finalizer của CI xử lý các đường kết thúc thông thường; cleanup idempotent và việc lưu resource ID giúp thao tác xóa có thể chạy lại; TTL và janitor thu hồi tài nguyên khi runner hoặc process không còn cơ hội thực hiện cleanup.

Hãy đăng ký finalizer trước khi tạo tài nguyên, gắn owner/run ID và TTL ngay từ đầu, chỉ xóa đúng tài nguyên thuộc run, giới hạn retry và bảo toàn exit code của công việc chính. Ghi lại cleanup result và diễn tập cả đường thất bại, cancel, timeout lẫn runner loss. Nhờ vậy, pipeline vừa giữ được nguyên nhân lỗi để điều tra vừa hạn chế tài nguyên mồ côi và chi phí phát sinh.

