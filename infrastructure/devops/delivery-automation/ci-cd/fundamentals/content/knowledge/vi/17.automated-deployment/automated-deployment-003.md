# Thiết kế script có kiểm tra lỗi và trạng thái hoàn tất rõ ràng

Script triển khai tự động là một phần của hệ thống phát hành. Nó có thể tải artifact, xác minh checksum, chuẩn bị môi trường, cập nhật workload, chờ ứng dụng sẵn sàng, chạy smoke test và ghi nhận kết quả. Một script chỉ chạy lần lượt các lệnh rồi kết thúc với exit code 0 chưa chắc đã triển khai thành công: lệnh có thể chỉ gửi yêu cầu bất đồng bộ, ứng dụng có thể chưa sẵn sàng, hoặc bước xác minh sau triển khai có thể chưa chạy.

Một script đáng tin cậy phải trả lời được ba câu hỏi: **đã thực hiện đến bước nào, lỗi xảy ra ở đâu và trạng thái cuối cùng của lần triển khai là gì**. Nó cần kiểm tra đầu vào, kiểm tra mã thoát của lệnh, giới hạn thời gian, xử lý retry có điều kiện, dọn dẹp tài nguyên, xác minh trạng thái thực tế và chỉ báo thành công khi mọi điều kiện bắt buộc đã đạt.

Bài học này trình bày cách thiết kế script có kiểm soát lỗi và trạng thái hoàn tất rõ ràng trong bối cảnh CI/CD. Ví dụ sử dụng Bash để minh họa, nhưng các nguyên tắc tương tự áp dụng cho PowerShell, Python, Node.js hoặc công cụ triển khai chuyên dụng.

## 1. Định nghĩa thành công của một lần triển khai

Trước khi viết script, cần xác định thế nào là hoàn tất. Một lệnh như deployctl apply trả về thành công có thể chỉ có nghĩa yêu cầu đã được chấp nhận. Nó không nhất thiết chứng minh workload mới đã khởi động, vượt qua readiness check hoặc phục vụ traffic bình thường.

Một lần triển khai thường có các bước:

1. Xác thực tham số, quyền và môi trường đích.
2. Kiểm tra điều kiện trước triển khai (preflight).
3. Lấy artifact đúng phiên bản.
4. Xác minh digest, chữ ký hoặc metadata theo chính sách.
5. Ghi nhận phiên bản đang chạy để hỗ trợ rollback.
6. Thực hiện thay đổi triển khai.
7. Chờ hệ thống đạt trạng thái sẵn sàng.
8. Chạy smoke test hoặc kiểm tra chấp nhận sau triển khai.
9. Ghi nhận release mới là phiên bản hiện hành.
10. Lưu kết quả, log và metadata của lần chạy.

Chỉ khi các bước bắt buộc hoàn tất, script mới được ghi nhận trạng thái **SUCCEEDED**. Nếu lệnh triển khai đã trả về 0 nhưng readiness check thất bại, lần triển khai vẫn chưa thành công.

~~~mermaid
flowchart TD
    A["Nhận yêu cầu triển khai"] --> B["Validate input và quyền"]
    B --> C["Preflight: môi trường, khóa, quota"]
    C --> D["Tải và xác minh artifact"]
    D --> E["Ghi nhận phiên bản hiện tại"]
    E --> F["Apply deployment"]
    F --> G["Chờ readiness trong timeout"]
    G --> H{"Ứng dụng sẵn sàng?"}
    H -- "Không" --> I["Xử lý lỗi / rollback nếu an toàn"]
    H -- "Có" --> J["Smoke test và xác minh phiên bản"]
    J --> K{"Các kiểm tra đạt?"}
    K -- "Không" --> I
    K -- "Có" --> L["Ghi nhận release thành công"]
    L --> M["Lưu trạng thái SUCCEEDED"]
~~~

Định nghĩa thành công cần gắn với yêu cầu của hệ thống. Một dịch vụ web có thể cần readiness, smoke test HTTP và xác minh artifact digest. Một job xử lý dữ liệu có thể cần xác minh số lượng bản ghi hoặc checkpoint. Không nên dùng một điều kiện chung cho mọi loại workload.

## 2. Thiết kế trạng thái triển khai rõ ràng

Script nên quản lý trạng thái như một quy trình có các bước xác định. Điều này giúp log, dashboard và hệ thống điều phối hiểu được lần chạy đang ở đâu.

| Trạng thái | Ý nghĩa | Điều kiện chuyển tiếp |
|---|---|---|
| **PENDING** | Đã nhận yêu cầu nhưng chưa bắt đầu | Được runner tiếp nhận |
| **RUNNING** | Đang thực hiện các bước triển khai | Tiếp tục, thất bại hoặc bị hủy |
| **VALIDATING** | Đang kiểm tra đầu vào và điều kiện môi trường | Preflight đạt hoặc thất bại |
| **DEPLOYING** | Đã bắt đầu thay đổi workload | Apply hoàn tất hoặc thất bại |
| **VERIFYING** | Đang chờ readiness và chạy smoke test | Xác minh đạt hoặc thất bại |
| **SUCCEEDED** | Tất cả điều kiện bắt buộc đã đạt | Trạng thái cuối |
| **FAILED** | Lần chạy thất bại, chưa xác nhận rollback thành công | Trạng thái cuối hoặc chờ xử lý |
| **ROLLED_BACK** | Đã khôi phục phiên bản trước và xác minh rollback | Trạng thái cuối |
| **ROLLBACK_FAILED** | Thao tác rollback không hoàn tất hoặc chưa xác minh được | Cần can thiệp |
| **CANCELLED** | Lần chạy bị hủy theo chính sách | Trạng thái cuối hoặc chờ xác minh |

Không phải dự án nào cũng cần mọi trạng thái. Điều quan trọng là trạng thái có ý nghĩa nhất quán và không bị ghi thành công quá sớm.

### 2.1. Phân biệt exit code với deployment status

Exit code là kết quả của tiến trình script. Deployment status mô tả kết quả nghiệp vụ của lần triển khai.

Ví dụ:

- Exit code 0 và status **SUCCEEDED**: triển khai, readiness và smoke test đều đạt.
- Exit code khác 0 và status **FAILED**: có bước bắt buộc thất bại.
- Exit code khác 0 và status **ROLLED_BACK**: triển khai candidate thất bại nhưng phiên bản trước đã được khôi phục và xác minh.
- Exit code khác 0 và status **ROLLBACK_FAILED**: cả triển khai lẫn khôi phục đều gặp vấn đề.

Một lần chạy có thể trả exit code khác 0 nhưng trạng thái môi trường cuối cùng vẫn ổn định vì rollback thành công. Cần giữ cả hai thông tin để pipeline biết thao tác ban đầu thất bại và môi trường đã được phục hồi.

### 2.2. Chỉ ghi trạng thái cuối sau khi xác minh

Không ghi **SUCCEEDED** ngay sau lệnh apply. Hãy chờ readiness, chạy smoke test và xác minh release ID hoặc digest đang chạy. Nếu pipeline triển khai bất đồng bộ, cần poll trạng thái từ nền tảng cho đến khi đạt trạng thái cuối hoặc hết timeout.

Trạng thái **RUNNING** cũng không nên tồn tại mãi nếu runner bị mất kết nối. Hệ thống điều phối cần timeout ở cấp job và cơ chế đối soát trạng thái thực tế của môi trường.

## 3. Kiểm tra đầu vào và điều kiện trước triển khai

Kiểm tra đầu vào càng sớm càng giảm khả năng script thực hiện một thay đổi sai môi trường hoặc sai artifact.

Những tham số thường cần xác thực:

- Môi trường đích, ví dụ **staging** hoặc **production**.
- Release ID hoặc version.
- Artifact URI và digest mong đợi.
- Namespace, cluster, region hoặc application name.
- Tham chiếu cấu hình và secret cần thiết.
- Timeout và giới hạn retry.
- Quyền của danh tính thực thi.
- Trạng thái phê duyệt nếu môi trường yêu cầu.

Nên kiểm tra giá trị bắt buộc, kiểu dữ liệu, định dạng và danh sách cho phép. Ví dụ, môi trường đích nên khớp allowlist. Không ghép chuỗi từ input chưa tin cậy vào lệnh shell, không dùng **eval** và luôn quote biến khi truyền thành đối số.

### 3.1. Preflight trước khi thay đổi môi trường

Preflight là nhóm kiểm tra trước khi script bắt đầu tác động đến hệ thống:

- Runner đã xác thực đúng tài khoản hoặc workload identity.
- Người gọi được phép triển khai đến môi trường đích.
- Cluster, namespace hoặc API đích đang sẵn sàng.
- Artifact tồn tại và có thể đọc.
- Digest hoặc chữ ký hợp lệ.
- Quota và tài nguyên đủ cho rollout.
- Không có một lần triển khai xung đột đang giữ khóa.
- Cấu hình môi trường hợp lệ và tương thích với artifact.
- Có phiên bản hiện tại hoặc kế hoạch xử lý khi không thể rollback.

Preflight không bảo đảm mọi thao tác sau đó chắc chắn thành công, nhưng giúp phát hiện sớm điều kiện sai trước khi thay đổi trạng thái.

### 3.2. Tách kiểm tra chỉ đọc khỏi thao tác thay đổi

Nên tổ chức script theo hai nhóm:

- **Read-only checks:** đọc trạng thái, kiểm tra quyền, xác minh artifact, kiểm tra cấu hình và quota.
- **Mutating operations:** cập nhật deployment, thay đổi traffic, sửa cấu hình hoặc ghi nhận release mới.

Nhóm chỉ đọc có thể chạy trước và thường dễ retry hơn. Nhóm thay đổi cần có khóa, idempotency và kế hoạch xử lý lỗi rõ ràng.

## 4. Kiểm tra lỗi và mã thoát của lệnh

Mỗi lệnh bên ngoài có thể thất bại vì nhiều lý do: sai tham số, thiếu quyền, lỗi mạng, timeout, dịch vụ không sẵn sàng hoặc lỗi từ chính ứng dụng. Script cần kiểm tra kết quả của các lệnh quan trọng và giữ lại mã thoát để chẩn đoán.

### 4.1. Exit code trong shell

Theo quy ước Unix phổ biến:

- **0:** lệnh hoàn tất thành công.
- **Khác 0:** có lỗi hoặc kết quả đặc biệt cần được diễn giải theo công cụ.

Mã thoát cụ thể phụ thuộc chương trình. Không nên giả định mọi mã khác 0 đều cùng một loại lỗi. Cần đọc tài liệu của CLI đang dùng và ánh xạ các mã quan trọng sang trạng thái của pipeline.

Ví dụ:

~~~bash
if deployctl preflight --environment "$TARGET_ENV"; then
  printf '%s\n' "Preflight passed"
else
  rc=$?
  printf 'Preflight failed, exit=%s\n' "$rc" >&2
  exit "$rc"
fi
~~~

Cấu trúc **if command; then ... else rc=$?; ... fi** giữ được mã thoát thực tế của lệnh. Tránh mẫu **if ! command; then rc=$?**, vì khi đi vào nhánh then, **$?** là mã của phép phủ định và thường bằng 0, không còn là mã lỗi ban đầu.

### 4.2. Strict mode trong Bash

Một script Bash thường bắt đầu bằng:

~~~bash
set -Eeuo pipefail
IFS=$'\n\t'
~~~

Ý nghĩa:

- **-e:** yêu cầu shell dừng khi một lệnh thất bại trong các ngữ cảnh mà quy tắc errexit áp dụng.
- **-E:** cho phép trap ERR được kế thừa vào function và một số ngữ cảnh con.
- **-u:** báo lỗi khi tham chiếu biến chưa được đặt.
- **pipefail:** pipeline trả mã lỗi của lệnh thất bại thay vì chỉ lấy mã của lệnh cuối.

Strict mode hữu ích nhưng không thay thế kiểm tra lỗi tường minh. Hành vi của **set -e** có ngoại lệ trong **if**, **while**, **&&**, **||**, pipeline và một số ngữ cảnh function/subshell. Vì vậy, lệnh quan trọng như deploy, rollback, xác minh digest và health check nên được kiểm tra bằng **if/else** hoặc wrapper có xử lý mã thoát.

### 4.3. Tránh nuốt lỗi

Các mẫu như **command || true**, **2>/dev/null** hoặc bỏ qua output có thể che giấu lỗi. Chỉ dùng khi lỗi đã được xác định là không ảnh hưởng đến mục tiêu và lý do được ghi lại.

Ví dụ, xóa thư mục tạm có thể là best-effort nhưng lỗi xác minh artifact thì không. Một script không nên biến mọi lỗi thành cảnh báo chỉ để pipeline luôn xanh.

### 4.4. Kiểm tra cả pipeline và command substitution

Với **pipefail**, lệnh như **download | sha256sum** có thể trả lỗi nếu một thành phần trong pipeline thất bại. Nếu không bật **pipefail**, shell có thể chỉ báo trạng thái của lệnh cuối và che mất lỗi tải dữ liệu.

Command substitution như **VERSION=$(deployctl current-version)** cũng cần được kiểm tra. Nếu lệnh con thất bại, script không nên tiếp tục với chuỗi rỗng hoặc giá trị mặc định không an toàn.

## 5. Hàm dùng chung để chạy lệnh có kiểm soát

Một wrapper giúp log thống nhất và giữ mã thoát:

~~~bash
run_checked() {
  local description="$1"
  shift

  log INFO "START: $description"

  if "$@"; then
    log INFO "PASS: $description"
    return 0
  else
    local rc=$?
    log ERROR "FAIL: $description (exit=$rc)"
    return "$rc"
  fi
}
~~~

Cách gọi:

~~~bash
if run_checked "verify artifact" artifactctl verify \
  --uri "$ARTIFACT_URI" \
  --sha256 "$EXPECTED_SHA256"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Artifact verification failed"
fi
~~~

Hàm nhận command và đối số dưới dạng các phần tử riêng. Cách này tránh ghép chuỗi lệnh rồi dùng **eval**, giảm nguy cơ command injection và lỗi quote. Không nên nhận một chuỗi lệnh tùy ý từ pull request rồi thực thi trên runner có quyền triển khai.

Một wrapper tốt nên ghi tên bước, thời điểm, kết quả và mã thoát. Không ghi secret, token hoặc toàn bộ connection string vào log.

## 6. Timeout và retry có giới hạn

Một lệnh triển khai có thể chờ mãi nếu dịch vụ phụ thuộc không phản hồi. Mọi bước có khả năng chờ cần timeout phù hợp:

- Timeout kết nối đến API.
- Timeout tải artifact.
- Timeout chờ rollout.
- Timeout readiness check.
- Timeout smoke test.
- Timeout toàn bộ job triển khai.

Timeout ở client không nhất thiết dừng thao tác ở server. Ví dụ, script hết thời gian chờ trong khi hệ thống điều phối vẫn đang rollout. Khi timeout, cần truy vấn trạng thái thực tế trước khi gửi lệnh mới hoặc rollback.

### 6.1. Retry chỉ với lỗi tạm thời

Retry phù hợp với lỗi có khả năng tự hết như network reset, rate limit hoặc một số lỗi dịch vụ tạm thời. Không nên retry lỗi validation, thiếu quyền, artifact sai digest hoặc cấu hình không hợp lệ.

Một chính sách retry nên xác định:

- Những mã lỗi hoặc loại lỗi nào được retry.
- Số lần thử tối đa.
- Khoảng chờ giữa các lần thử.
- Exponential backoff và jitter để tránh nhiều job retry cùng lúc.
- Timeout tổng.
- Điều kiện dừng ngay khi lỗi không thể khắc phục bằng retry.

Không retry vô hạn. Retry quá nhiều có thể làm tăng tải, che giấu sự cố và khiến thời gian phản hồi khó dự đoán.

### 6.2. Retry thao tác thay đổi cần idempotency

Lặp lại lệnh đọc trạng thái thường an toàn hơn lặp lại lệnh tạo tài nguyên hoặc triển khai. Nếu một yêu cầu đã đến server nhưng response bị mất, client có thể không biết thao tác đã được áp dụng hay chưa.

Với thao tác thay đổi, hãy dùng idempotency key hoặc release ID ổn định nếu API hỗ trợ. Trước khi retry, truy vấn trạng thái hiện tại để xác định yêu cầu trước đã hoàn tất hay chưa.

## 7. Idempotency và điều phối triển khai đồng thời

Một script idempotent có thể chạy lại với cùng đầu vào mà không tạo ra trạng thái sai hoặc tài nguyên trùng lặp. Đây là đặc tính quan trọng khi runner bị gián đoạn, pipeline retry hoặc người vận hành chạy lại thủ công.

Các nguyên tắc:

- Xác định tài nguyên theo tên hoặc release ID ổn định.
- Kiểm tra trạng thái hiện tại trước khi tạo hoặc cập nhật.
- Dùng API khai báo trạng thái mong muốn khi có thể.
- Tránh thao tác cộng dồn không có khóa, ví dụ tạo bản ghi release mới mỗi lần chạy.
- Gắn idempotency key cho yêu cầu thay đổi.
- Ghi nhận kết quả để lần chạy sau có thể tiếp tục hoặc xác minh.

Hai pipeline có thể cùng triển khai một dịch vụ. Nếu không có concurrency control, lần chạy cũ có thể hoàn tất sau và ghi đè phiên bản mới. Cần khóa theo ứng dụng/môi trường hoặc dùng cơ chế tuần tự hóa của nền tảng.

Ví dụ khóa ở mức hệ điều hành:

~~~bash
exec 9>"/var/lock/orders-production-deploy.lock"
if ! flock -n 9; then
  printf '%s\n' "Another deployment is running" >&2
  exit 75
fi
~~~

Ví dụ này chỉ phù hợp khi các job dùng chung filesystem/host hỗ trợ **flock**. Với runner phân tán, cần concurrency group, distributed lock hoặc cơ chế khóa của hệ thống triển khai. Khóa phải có thời hạn hoặc cơ chế thu hồi để tránh deadlock khi runner bị mất.

## 8. Dọn dẹp và xử lý tín hiệu

Script có thể tạo workspace tạm, tải artifact, sinh file metadata hoặc khởi chạy process phụ. Những tài nguyên này cần được dọn dẹp khi thành công, thất bại hoặc bị hủy.

Trong Bash, **trap** cho phép thực hiện cleanup khi shell thoát hoặc nhận tín hiệu:

~~~bash
WORK_DIR="$(mktemp -d)"

cleanup() {
  local rc=$?
  if [[ -n "${WORK_DIR:-}" && -d "$WORK_DIR" ]]; then
    if ! rm -rf -- "$WORK_DIR"; then
      printf '%s\n' "WARNING: cleanup failed" >&2
    fi
  fi
}

trap cleanup EXIT
~~~

Cleanup nên:

- Xóa file tạm và workspace do job tạo.
- Thu hồi hoặc hủy credential tạm nếu có thể.
- Dừng process phụ và container tạm.
- Giải phóng lock.
- Giữ lại log và báo cáo cần thiết.
- Không xóa artifact hoặc bằng chứng cần điều tra.

Cleanup không nên che giấu lỗi chính. Nếu deployment thất bại, cleanup vẫn phải chạy nhưng exit code ban đầu cần được giữ lại. Với runner ephemeral, hủy toàn bộ môi trường sau job có thể là cách đáng tin cậy hơn việc cố dọn từng tài nguyên.

### 8.1. Xử lý SIGTERM và hủy job

Nền tảng CI có thể gửi SIGTERM khi timeout hoặc người dùng hủy pipeline. Script nên xử lý tín hiệu một cách có kiểm soát: ngừng bắt đầu thao tác mới, ghi nhận trạng thái **CANCELLED** hoặc **INTERRUPTED**, dừng tiến trình con và kiểm tra trạng thái deployment đang diễn ra.

Không nên tự động rollback trong mọi trường hợp bị hủy. Nếu thao tác thay đổi đã được áp dụng một phần, cần truy vấn trạng thái môi trường và tuân theo chính sách khôi phục. Rollback cũng là một thao tác thay đổi cần được xác minh.

## 9. Readiness, health check và smoke test

Sau khi lệnh deploy hoàn tất, script cần xác minh ứng dụng thực sự sẵn sàng.

| Kiểm tra | Câu hỏi | Thời điểm |
|---|---|---|
| Process/container state | Process hoặc container đã chạy chưa? | Ngay sau apply |
| Readiness check | Ứng dụng đã sẵn sàng nhận traffic chưa? | Trong rollout |
| Liveness check | Process có còn sống và không bị treo không? | Sau khi chạy |
| Health endpoint | Các thành phần cần thiết có hoạt động không? | Sau readiness |
| Smoke test | Luồng nghiệp vụ tối thiểu có hoạt động không? | Sau triển khai |
| Version/digest check | Phiên bản đang chạy có đúng artifact được phát hành không? | Trước khi đánh dấu thành công |

Readiness và liveness có mục tiêu khác nhau. Một process còn sống chưa chắc đã sẵn sàng phục vụ request. Một readiness endpoint chỉ trả 200 cũng chưa đủ nếu nó không kiểm tra dependency quan trọng hoặc trả kết quả giả.

Smoke test nên ngắn, ổn định và kiểm tra đường đi quan trọng nhất: endpoint cơ bản, xác thực, kết nối dịch vụ cần thiết hoặc một thao tác nghiệp vụ an toàn. Không dùng smoke test có tác dụng phụ như tạo giao dịch thật trong production nếu chưa có cơ chế dữ liệu test riêng.

### 9.1. Polling với timeout và khoảng nghỉ

Thay vì sleep cố định rồi giả định ứng dụng đã sẵn sàng, hãy poll trạng thái:

1. Gọi readiness endpoint hoặc API rollout.
2. Nếu đạt, tiếp tục.
3. Nếu trạng thái đang tiến triển, chờ một khoảng ngắn rồi kiểm tra lại.
4. Nếu gặp lỗi tạm thời, áp dụng retry có giới hạn.
5. Nếu hết deadline hoặc có trạng thái lỗi cuối, đánh dấu thất bại và thực hiện chính sách xử lý.

Poll cần có timeout tổng và log số lần thử hoặc thời gian đã chờ. Tránh polling quá dày gây tải lên hệ thống đang gặp sự cố.

## 10. Rollback và trạng thái sau lỗi

Rollback là một phần của thiết kế triển khai, nhưng không phải lúc nào cũng an toàn hoặc có thể tự động.

Trước khi thay đổi, script nên ghi nhận phiên bản hiện tại, artifact digest, cấu hình liên quan và thông tin cần để khôi phục. Nếu candidate thất bại sau khi đã thay đổi môi trường, có thể rollback khi:

- Phiên bản trước còn tồn tại và xác minh được.
- Cấu hình và schema tương thích.
- Thao tác có thể đảo ngược.
- Chính sách môi trường cho phép tự động rollback.
- Có thể xác minh phiên bản trước hoạt động trở lại.

Không nên rollback mù quáng sau một migration dữ liệu không tương thích hoặc thao tác irreversible. Trong trường hợp đó, có thể cần dừng rollout, giữ trạng thái hiện tại và yêu cầu quyết định của người vận hành hoặc thực hiện forward fix.

### 10.1. Phân biệt các kết quả cuối

| Kết quả | Ý nghĩa | Hành động tiếp theo |
|---|---|---|
| **SUCCEEDED** | Candidate đã triển khai và xác minh đạt | Hoàn tất release record |
| **FAILED** | Có bước thất bại, chưa khôi phục được trạng thái trước | Điều tra và quyết định xử lý |
| **ROLLED_BACK** | Candidate lỗi nhưng phiên bản trước đã được xác minh | Ghi nhận incident và nguyên nhân |
| **ROLLBACK_FAILED** | Không khôi phục được hoặc chưa xác minh được | Cảnh báo khẩn cấp, can thiệp vận hành |
| **CANCELLED** | Lần chạy bị hủy | Đối soát trạng thái thực tế trước lần chạy tiếp theo |

Rollback thành công không biến lần triển khai candidate thành thành công. Nó chỉ cho biết môi trường đã được khôi phục về trạng thái trước theo tiêu chí đã xác minh.

## 11. Log, báo cáo và trạng thái máy đọc được

Log cần giúp người vận hành biết bước nào bắt đầu, kết thúc và thất bại. Mỗi dòng nên có timestamp, level, release ID, môi trường và tên bước. Tránh ghi secret hoặc dữ liệu nhạy cảm.

Ví dụ:

~~~text
2026-11-18T09:00:00Z level=INFO release=rel-2026-11-18-01 env=staging step=preflight status=STARTED
2026-11-18T09:00:03Z level=INFO release=rel-2026-11-18-01 env=staging step=artifact-verify status=PASSED
2026-11-18T09:00:10Z level=INFO release=rel-2026-11-18-01 env=staging step=deploy status=STARTED
2026-11-18T09:01:12Z level=INFO release=rel-2026-11-18-01 env=staging step=readiness status=PASSED
2026-11-18T09:01:20Z level=INFO release=rel-2026-11-18-01 env=staging result=SUCCEEDED
~~~

Ngoài log, nên tạo một kết quả máy đọc được để pipeline hoặc hệ thống quan sát sử dụng. Ví dụ JSON:

~~~json
{
  "release_id": "rel-2026-11-18-01",
  "environment": "staging",
  "status": "SUCCEEDED",
  "exit_code": 0,
  "artifact_digest": "sha256:...",
  "previous_release": "rel-2026-11-17-03",
  "started_at": "2026-11-18T09:00:00Z",
  "completed_at": "2026-11-18T09:01:20Z",
  "checks": {
    "artifact_verified": true,
    "readiness": true,
    "smoke_test": true,
    "running_version_verified": true
  }
}
~~~

Kết quả này cần được ghi nguyên tử: ghi ra file tạm rồi đổi tên trong cùng filesystem để người đọc không thấy nội dung dở dang. Với dữ liệu JSON, dùng thư viện hoặc công cụ như jq để escape giá trị đúng cách thay vì tự nối chuỗi. Lưu kết quả cùng pipeline run ID, commit SHA và artifact digest.

## 12. Ví dụ script Bash có kiểm tra lỗi và trạng thái hoàn tất

Ví dụ dưới đây dùng các CLI giả định **artifactctl**, **deployctl** và **smoke-test** để minh họa cấu trúc. Đây không phải script có thể chạy trực tiếp nếu chưa thay các công cụ và chính sách theo nền tảng của dự án.

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

: "${TARGET_ENV:?TARGET_ENV is required}"
: "${RELEASE_ID:?RELEASE_ID is required}"
: "${ARTIFACT_URI:?ARTIFACT_URI is required}"
: "${EXPECTED_SHA256:?EXPECTED_SHA256 is required}"
: "${RESULT_FILE:?RESULT_FILE is required}"
: "${ROLLBACK_ALLOWED:?ROLLBACK_ALLOWED must come from trusted release policy}"

case "$TARGET_ENV" in
  staging|production) ;;
  *)
    printf 'Unsupported environment: %s\n' "$TARGET_ENV" >&2
    exit 2
    ;;
esac

case "$ROLLBACK_ALLOWED" in
  true|false) ;;
  *)
    printf '%s\n' "ROLLBACK_ALLOWED must be true or false" >&2
    exit 2
    ;;
esac

RESULT_DIR="$(dirname -- "$RESULT_FILE")"
mkdir -p -- "$RESULT_DIR"
WORK_DIR="$(mktemp -d)"
RESULT_STATUS="RUNNING"
DEPLOYMENT_STARTED="false"
PREVIOUS_RELEASE=""

log() {
  local level="$1"
  shift
  printf '%s level=%s %s\n' "$(date -u +%FT%TZ)" "$level" "$*" >&2
}

write_result() {
  local status="$1"
  local exit_code="$2"
  local result_tmp="${RESULT_FILE}.tmp.$$"

  jq -n \
    --arg status "$status" \
    --arg release "$RELEASE_ID" \
    --arg environment "$TARGET_ENV" \
    --arg digest "$EXPECTED_SHA256" \
    --argjson exit_code "$exit_code" \
    '{
      status: $status,
      release_id: $release,
      environment: $environment,
      artifact_digest: $digest,
      exit_code: $exit_code
    }' > "$result_tmp"

  mv -f -- "$result_tmp" "$RESULT_FILE"
}

cleanup() {
  if [[ -n "${WORK_DIR:-}" && -d "$WORK_DIR" ]]; then
    if ! rm -rf -- "$WORK_DIR"; then
      log WARN "Temporary workspace cleanup failed"
    fi
  fi
}

on_error() {
  local rc=$?
  local line="${BASH_LINENO[0]:-unknown}"
  log ERROR "Unhandled command failure exit=$rc line=$line"

  if [[ "$RESULT_STATUS" == "RUNNING" ]]; then
    RESULT_STATUS="FAILED"
    if ! write_result "$RESULT_STATUS" "$rc"; then
      log ERROR "Could not persist failure result"
    fi
  fi

  exit "$rc"
}

on_signal() {
  local signal="$1"
  local rc=130
  if [[ "$signal" == "SIGTERM" ]]; then
    rc=143
  fi

  log WARN "Received $signal; checking remote deployment state"
  if [[ "$DEPLOYMENT_STARTED" == "true" ]]; then
    if deployctl status --environment "$TARGET_ENV" --release "$RELEASE_ID"; then
      :
    else
      log WARN "Could not query remote deployment state"
    fi
  fi

  RESULT_STATUS="CANCELLED"
  if ! write_result "$RESULT_STATUS" "$rc"; then
    log ERROR "Could not persist cancellation result"
  fi
  exit "$rc"
}

run_checked() {
  local description="$1"
  shift

  log INFO "START: $description"

  if "$@"; then
    log INFO "PASS: $description"
    return 0
  else
    local rc=$?
    log ERROR "FAIL: $description exit=$rc"
    return "$rc"
  fi
}

fail_deployment() {
  local rc="$1"
  shift
  log ERROR "$*"

  local final_status="FAILED"

  if [[ "$DEPLOYMENT_STARTED" == "true" &&
        "$ROLLBACK_ALLOWED" == "true" &&
        -n "$PREVIOUS_RELEASE" ]]; then
    if run_checked "rollback previous release" \
      deployctl rollback \
        --environment "$TARGET_ENV" \
        --release "$PREVIOUS_RELEASE" \
        --idempotency-key "${RELEASE_ID}-rollback"; then
      if run_checked "verify previous release" \
        deployctl verify-current \
          --environment "$TARGET_ENV" \
          --release "$PREVIOUS_RELEASE"; then
        final_status="ROLLED_BACK"
      else
        final_status="ROLLBACK_FAILED"
      fi
    else
      final_status="ROLLBACK_FAILED"
    fi
  fi

  RESULT_STATUS="$final_status"
  if ! write_result "$RESULT_STATUS" "$rc"; then
    log ERROR "Could not persist final deployment result"
  fi

  exit "$rc"
}

trap cleanup EXIT
trap on_error ERR
trap 'on_signal SIGINT' INT
trap 'on_signal SIGTERM' TERM

log INFO "Deployment started release=$RELEASE_ID env=$TARGET_ENV"

if ! command -v jq >/dev/null 2>&1; then
  log ERROR "jq is required to write the result file"
  exit 2
fi

if PREVIOUS_RELEASE="$(deployctl current-release --environment "$TARGET_ENV")"; then
  log INFO "Previous release captured"
else
  rc=$?
  fail_deployment "$rc" "Cannot read current release"
fi

if run_checked "verify artifact" \
  artifactctl verify \
    --uri "$ARTIFACT_URI" \
    --sha256 "$EXPECTED_SHA256"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Artifact verification failed"
fi

if run_checked "preflight target" \
  deployctl preflight --environment "$TARGET_ENV"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Deployment preflight failed"
fi

# ROLLBACK_ALLOWED was injected by trusted release policy and validated above.

# Mark the change as started before invoking apply because the remote
# operation may partially succeed even when the client receives an error.
DEPLOYMENT_STARTED="true"

if run_checked "apply release" \
  deployctl apply \
    --environment "$TARGET_ENV" \
    --release "$RELEASE_ID" \
    --artifact "$ARTIFACT_URI" \
    --idempotency-key "$RELEASE_ID"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Apply operation failed"
fi

if run_checked "wait for readiness" \
  deployctl wait-ready \
    --environment "$TARGET_ENV" \
    --release "$RELEASE_ID" \
    --timeout 180s; then
  :
else
  rc=$?
  fail_deployment "$rc" "Readiness check failed"
fi

if run_checked "smoke tests" \
  smoke-test --environment "$TARGET_ENV" --release "$RELEASE_ID"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Smoke tests failed"
fi

if run_checked "verify running release" \
  deployctl verify-current \
    --environment "$TARGET_ENV" \
    --release "$RELEASE_ID" \
    --artifact-digest "$EXPECTED_SHA256"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Running release verification failed"
fi

if run_checked "record current release" \
  deployctl mark-current \
    --environment "$TARGET_ENV" \
    --release "$RELEASE_ID"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Could not record current release"
fi

RESULT_STATUS="SUCCEEDED"
if write_result "$RESULT_STATUS" 0; then
  log INFO "Deployment completed release=$RELEASE_ID env=$TARGET_ENV status=$RESULT_STATUS"
else
  log ERROR "Deployment succeeded but result persistence failed"
  exit 70
fi
~~~

### 12.1. Những điểm cần điều chỉnh trước khi dùng thật

Ví dụ trên thể hiện cách tổ chức và xử lý luồng điều khiển. Khi chuyển thành script thực tế, cần:

- Thay CLI giả định bằng công cụ triển khai của nền tảng.
- Xác định **ROLLBACK_ALLOWED** từ policy đáng tin cậy và kiểm tra tính tương thích của rollback.
- Tạo thư mục cha của **RESULT_FILE** trước khi ghi.
- Cấp quyền ghi result file đúng phạm vi và bảo vệ nội dung.
- Cấu hình timeout cho từng CLI, không chỉ timeout tổng của pipeline.
- Kiểm tra trạng thái remote sau timeout vì thao tác có thể vẫn tiếp tục ở server.
- Bổ sung metadata commit SHA, pipeline run ID, thời điểm và config revision.
- Xác định cách xử lý khi không có phiên bản trước hoặc khi migration không thể đảo ngược.
- Kiểm thử các nhánh lỗi trong môi trường an toàn trước khi cho phép triển khai production.

**trap ERR** trong ví dụ là lớp ghi nhận lỗi không được xử lý. Nó không thay thế các nhánh **if/else** tường minh ở những thao tác quan trọng. Những lệnh được gọi trong điều kiện hoặc danh sách **&&/||** có quy tắc xử lý lỗi riêng của Bash, nên không thể dựa hoàn toàn vào **set -e** hoặc trap để quyết định trạng thái nghiệp vụ.

## 13. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra exit code của lệnh deploy | Lệnh được chấp nhận nhưng ứng dụng chưa sẵn sàng | Chờ rollout, readiness và smoke test |
| Không xác thực input | Triển khai nhầm môi trường hoặc artifact | Kiểm tra required field, allowlist và digest |
| Dùng **set -e** như cơ chế xử lý lỗi duy nhất | Bỏ sót lỗi trong điều kiện hoặc pipeline | Kiểm tra tường minh các lệnh quan trọng |
| Dùng **! command** rồi đọc **$?** để lấy lỗi | Nhận mã 0 của phép phủ định | Dùng **if command; then ... else rc=$?** |
| Retry vô hạn | Tăng tải và kéo dài sự cố | Giới hạn số lần, backoff và timeout |
| Retry thao tác không idempotent | Tạo tài nguyên hoặc release trùng | Idempotency key và đối soát trạng thái |
| Không khóa triển khai | Hai pipeline ghi đè phiên bản của nhau | Concurrency group hoặc distributed lock |
| Không dọn dẹp tài nguyên | Rò rỉ workspace, process và credential | Trap cleanup hoặc ephemeral runner |
| Đánh dấu thành công ngay sau apply | Báo xanh dù ứng dụng lỗi | Chỉ ghi **SUCCEEDED** sau xác minh |
| Rollback không kiểm tra | Có thể làm trạng thái tệ hơn | Xác minh điều kiện và trạng thái sau rollback |
| Ghi log toàn bộ environment | Lộ secret và token | Log theo allowlist, redact dữ liệu nhạy cảm |
| Không lưu trạng thái máy đọc được | Khó tích hợp dashboard và điều tra | Result JSON gắn release, commit và digest |

## 14. Tình huống mẫu: triển khai thất bại ở bước readiness

Giả sử pipeline triển khai một phiên bản API mới lên staging. Lệnh apply trả về 0 vì nền tảng đã nhận yêu cầu, nhưng một pod mới không thể kết nối database.

1. Script ghi trạng thái **DEPLOYING** và lưu release hiện tại trước khi thay đổi.
2. Lệnh apply hoàn tất, script chuyển sang **VERIFYING**.
3. Readiness check được poll trong thời hạn đã cấu hình.
4. Một số lần kiểm tra đầu trả về chưa sẵn sàng; script tiếp tục chờ trong giới hạn, không đánh dấu thành công.
5. Hết timeout, script ghi nhận lỗi readiness và thu thập thông tin cần thiết.
6. Chính sách cho phép rollback, phiên bản trước còn tồn tại và tương thích. Script gửi rollback với idempotency key riêng.
7. Script chờ phiên bản trước sẵn sàng và xác minh release ID cũ đang chạy.
8. Nếu xác minh đạt, trạng thái cuối là **ROLLED_BACK**, exit code của lần triển khai vẫn khác 0 để pipeline báo lần phát hành candidate thất bại.
9. Nếu rollback không đạt, trạng thái là **ROLLBACK_FAILED**, tạo cảnh báo cần người vận hành xử lý.
10. Log và result record lưu candidate release, phiên bản trước, artifact digest, bước lỗi và kết quả rollback.

Tình huống này cho thấy trạng thái cuối cần mô tả đúng điều đã xảy ra. Một lần chạy không nên báo **SUCCEEDED** chỉ vì API triển khai chấp nhận yêu cầu; đồng thời hệ thống cũng cần phân biệt thất bại đã phục hồi với thất bại chưa phục hồi.

## 15. Lộ trình thực hành

Có thể thực hành trên môi trường staging hoặc ứng dụng mẫu theo các bước:

1. **Định nghĩa trạng thái:** thống nhất các trạng thái cuối như **SUCCEEDED**, **FAILED**, **ROLLED_BACK** và **ROLLBACK_FAILED**.
2. **Xác thực input:** yêu cầu environment, release ID, artifact URI và digest; từ chối giá trị ngoài allowlist.
3. **Thêm preflight:** kiểm tra quyền, kết nối, artifact, quota và phiên bản hiện tại.
4. **Kiểm tra exit code:** tạo một lệnh test thất bại có chủ đích và xác nhận script giữ đúng mã thoát.
5. **Thêm timeout:** mô phỏng dịch vụ không phản hồi và xác nhận job dừng trong thời hạn.
6. **Thêm retry có giới hạn:** mô phỏng lỗi mạng tạm thời và lỗi permission để xác nhận chỉ lỗi phù hợp được retry.
7. **Kiểm tra idempotency:** chạy lại cùng release ID và xác nhận không tạo release hoặc tài nguyên trùng.
8. **Kiểm soát concurrency:** khởi chạy hai yêu cầu đồng thời và xác nhận chỉ một lần triển khai được phép thay đổi môi trường.
9. **Xác minh sau deploy:** làm readiness hoặc smoke test thất bại trong staging, kiểm tra trạng thái được ghi đúng.
10. **Diễn tập rollback:** xác nhận phiên bản trước được khôi phục và trạng thái **ROLLED_BACK** chỉ được ghi sau khi verify.
11. **Kiểm tra cleanup:** hủy job giữa chừng và xác nhận workspace, process, lock và credential tạm được xử lý.
12. **Kiểm tra báo cáo:** xác nhận result JSON chứa release ID, environment, digest, trạng thái, exit code và thời điểm.

### Tiêu chí hoàn thành

Người học có thể xem bài thực hành hoàn thành khi chứng minh được:

- Định nghĩa được điều kiện thành công thực tế của một lần triển khai.
- Phân biệt được exit code với deployment status.
- Kiểm tra được input, quyền và preflight trước khi thay đổi môi trường.
- Xử lý lỗi tường minh và giữ đúng mã thoát.
- Hiểu giới hạn của **set -e**, **pipefail** và **trap ERR**.
- Thiết lập timeout và retry có giới hạn theo loại lỗi.
- Thiết kế thao tác idempotent và chống triển khai đồng thời.
- Dọn dẹp tài nguyên khi thành công, thất bại hoặc bị hủy.
- Xác minh readiness, smoke test và phiên bản artifact đang chạy.
- Chỉ ghi **SUCCEEDED** sau khi mọi gate bắt buộc đạt.
- Phân biệt **FAILED**, **ROLLED_BACK** và **ROLLBACK_FAILED**.
- Lưu được log và result record có thể truy vết.

## Kết luận

Script triển khai đáng tin cậy cần điều khiển được toàn bộ vòng đời của một lần thay đổi: xác thực đầu vào, kiểm tra điều kiện, thực thi có kiểm soát, xác minh kết quả và ghi trạng thái cuối. Exit code là tín hiệu của tiến trình; deployment status phải phản ánh trạng thái thực tế của môi trường sau readiness, smoke test và rollback nếu có.

Khi kết hợp xử lý lỗi tường minh, timeout, retry có giới hạn, idempotency, concurrency control, cleanup và result record, script trở thành một thành phần có thể vận hành và điều tra được. Điều này giúp pipeline phân biệt rõ một lần phát hành đã hoàn tất, một lần thất bại đã được khôi phục và một sự cố vẫn cần can thiệp.

