# Khởi động thông thường dự phòng khi restore không đáp ứng điều kiện

CRaC (Coordinated Restore at Checkpoint) giúp một ứng dụng Java tiếp tục từ trạng thái đã được chuẩn bị trước, nhờ đó giảm thời gian khởi động. Tuy nhiên, checkpoint chỉ có thể được restore khi runtime, checkpoint image và môi trường đích đáp ứng các điều kiện tương thích. Artifact có thể thiếu hoặc hỏng, JDK có thể khác build, kernel hay kiến trúc có thể không phù hợp, tài nguyên container có thể không đủ, hoặc một dependency cần thiết có thể không phục hồi được.

Một dịch vụ vận hành tốt cần có đường khởi động dự phòng bằng JVM thông thường. Khi restore không thể thực hiện an toàn, hệ thống bỏ qua checkpoint và khởi chạy ứng dụng từ đầu với cùng cấu hình triển khai, sau đó chờ readiness như một lần startup mới. Cơ chế dự phòng phải được đặt ở launcher, supervisor hoặc orchestrator có thể quan sát kết quả restore. Nếu lỗi xảy ra trước khi application code tiếp tục chạy, chính process đang restore thường không có cơ hội tự quyết định chạy lại main().

Điều quan trọng là phân biệt lỗi restore với lỗi của dịch vụ bên ngoài. Cold start có thể khắc phục checkpoint không tương thích hoặc trạng thái connection cũ, nhưng không sửa được database đang down, credential sai hay cấu hình ứng dụng lỗi. Bài học này trình bày cách thiết kế fallback, phân loại lỗi, kiểm tra trước restore, giới hạn retry, bảo đảm chỉ một instance nhận traffic và đo lường hiệu quả của đường khởi động dự phòng.

## 1. Vì sao cần cold-start fallback?

Một checkpoint được tạo ở một thời điểm và môi trường cụ thể. Khi restore, runtime phải khôi phục process state và các resource được hỗ trợ. Điều kiện có thể thay đổi giữa hai thời điểm:

- Checkpoint directory bị xóa, upload thiếu file hoặc artifact bị corruption.
- Manifest không khớp với JDK vendor, version, build hoặc application build.
- CPU architecture, OS, kernel, CRIU hoặc container runtime không tương thích.
- Cgroup memory/PIDs limit của container đích thấp hơn nhu cầu thực tế.
- File descriptor, socket, mount hoặc network resource không thể khôi phục.
- Credential, token, DNS, endpoint hoặc secret đã thay đổi.
- Callback afterRestore() không thể kết nối lại dependency.
- Checkpoint được tạo từ cấu hình hoặc schema cũ không còn được chấp nhận.

Nếu hệ thống chỉ có đường restore, một lỗi trong các trường hợp này có thể khiến instance không khởi động được. Cold-start fallback cung cấp đường đi thứ hai: tạo JVM mới, nạp cấu hình hiện tại, khởi tạo Spring/application context và tạo lại resource theo lifecycle thông thường.

~~~text
                 Start instance
                       |
                       v
              Checkpoint available?
                 /           \
               No             Yes
               |               |
               v               v
         Start fresh       Verify artifact
              JVM           and target
               |               |
               |          Eligible?
               |           /      \
               |          No       Yes
               |          |         |
               |          |         v
               |          |    Attempt restore
               |          |         |
               |          |    Restore succeeds?
               |          |      /       \
               |          |     Yes       No
               |          |      |         |
               |          +------+---------+
               |                 |
               +-----------------+
                       |
                       v
                Start normally
                       |
                       v
               Dependency checks
                       |
                       v
                  Readiness
                       |
                       v
                 Receive traffic
~~~

Sơ đồ mô tả quyết định ở cấp supervisor. Cách gọi restore thực tế phụ thuộc JDK distribution và nền tảng. Không phải mọi CRaC runtime đều có cùng CLI, exit code hoặc cách bàn giao process.

## 2. Hai loại fallback cần phân biệt

Có hai nhóm lỗi khác nhau và chúng cần được xử lý ở hai tầng.

**Restore không thể bắt đầu hoặc thất bại trước khi ứng dụng tiếp tục chạy.** Ví dụ, runtime không đọc được checkpoint, artifact không tương thích, CRIU từ chối restore hoặc kernel không hỗ trợ một resource. Lúc này application main() của process được restore chưa chạy tiếp. Fallback phải do launcher, supervisor hoặc orchestrator bên ngoài thực hiện.

**Process đã được restore nhưng ứng dụng không đạt trạng thái sẵn sàng.** Ví dụ, callback afterRestore() thất bại khi reconnect database, credential provider không lấy được token hoặc web server không thể bind endpoint. Lúc này process có thể đã tồn tại nhưng không thể phục vụ. Ứng dụng nên thử phục hồi resource theo chính sách có giới hạn; nếu trạng thái không thể khắc phục, process phải thoát hoặc được supervisor dừng trước khi supervisor khởi chạy JVM mới.

Không nên để một process đã restore nhưng đang lỗi tiếp tục chạy song song với JVM cold-start mới. Nếu cả hai cùng đăng ký consumer, chạy scheduler hoặc xử lý job, hệ thống có thể tạo side effect trùng lặp.

## 3. Vì sao process đang restore không phải lúc nào cũng tự fallback được?

Restore thường là thao tác ở cấp runtime và hệ điều hành. Runtime phải nạp trạng thái process trước khi luồng Java tiếp tục tại vị trí đã checkpoint. Nếu bước nạp trạng thái thất bại, application code không được tiếp tục thực thi để bắt exception rồi gọi main() lần nữa.

Do đó, kiến trúc nên có một thành phần nằm ngoài process được restore:

- Container entrypoint hoặc wrapper script.
- Process supervisor.
- Orchestrator controller hoặc init system.
- Deployment platform có cơ chế thử restore rồi chuyển sang command startup thông thường.

Thành phần này có thể kiểm tra artifact, gọi restore operation và nhận biết liệu process đã được khởi chạy thành công hay chưa. Khi restore không tạo được một process có thể quản lý, supervisor chọn cold start.

Một số runtime tích hợp restore vào command khởi chạy JVM hoặc cung cấp API/launcher riêng. Khi đó, cần dùng đúng cơ chế mà vendor hỗ trợ để phân biệt restore failure với application exit. Không giả định rằng mọi lỗi đều được biểu diễn bằng một exception Java hoặc một exit code giống nhau.

## 4. Vị trí của fallback trong kiến trúc triển khai

Một mô hình phổ biến là đặt logic chọn startup mode trong entrypoint của container hoặc supervisor:

~~~text
Container / VM supervisor
        |
        +---- Checkpoint metadata and integrity
        |
        +---- Check target compatibility
        |
        +---- Attempt CRaC restore
        |          |
        |          +---- Success -> monitor restored application
        |
        +---- Restore unavailable/failed
                   |
                   v
             Start fresh JVM
                   |
                   v
             Monitor readiness
~~~

Supervisor cần giữ quyền kiểm soát lifecycle của ứng dụng. Nó phải biết process nào đang chạy, process nào đã thoát, process nào đạt readiness và khi nào có thể chuyển startup mode.

Nếu restore command daemonize process hoặc trả về trước khi application sẵn sàng, wrapper cần theo dõi PID/process group hoặc dùng protocol readiness do runtime cung cấp. Không được coi việc command trả exit code 0 là bằng chứng ứng dụng đã sẵn sàng phục vụ.

## 5. Điều kiện để chọn restore hay cold start

Không nên thử restore một cách mù quáng với mọi artifact có mặt trên disk. Trước khi gọi runtime, supervisor có thể kiểm tra các metadata không tốn kém:

- Artifact có tồn tại và có đủ các file bắt buộc không?
- Manifest có hợp lệ và đã được xác thực không?
- Artifact có đúng application, build và environment không?
- JDK vendor/version/build có thuộc compatibility policy không?
- OS, architecture, kernel và checkpoint engine có tương thích không?
- Cgroup CPU, memory và PIDs có đạt mức tối thiểu đã kiểm chứng không?
- Checkpoint có quá cũ hoặc đã bị thu hồi không?
- Encryption key và identity restore có sẵn không?
- Artifact generation có được phép restore không?

Preflight chỉ giúp loại bỏ các trường hợp chắc chắn không đủ điều kiện. Nó không thể chứng minh restore sẽ thành công vì một số lỗi chỉ xuất hiện khi runtime thực sự nạp process state hoặc khi callback phục hồi resource chạy.

Kết quả preflight nên có lý do rõ ràng, ví dụ ARTIFACT_MISSING, SIGNATURE_INVALID, RUNTIME_MISMATCH, RESOURCE_PROFILE_UNSUPPORTED hoặc CHECKPOINT_EXPIRED. Không chỉ ghi một boolean eligible.

## 6. Kiểm tra tương thích runtime và ứng dụng

Checkpoint thường gắn với runtime và môi trường đã tạo ra nó. Một manifest nội bộ có thể lưu:

| Trường | Mục đích |
|---|---|
| artifactId | Định danh duy nhất của checkpoint |
| applicationBuild | Phiên bản ứng dụng |
| jdkVendor | Nhà cung cấp JDK |
| jdkVersion/build | Phiên bản và build cụ thể |
| cracRuntime | Bản CRaC runtime/engine |
| os/architecture | Hệ điều hành và kiến trúc |
| kernel/runtime profile | Điều kiện nền tảng được hỗ trợ |
| resourceProfile | CPU, memory, PIDs và các giới hạn liên quan |
| createdAt | Thời điểm tạo |
| generation | Chống dùng lại artifact cũ nếu policy yêu cầu |
| integrity/signature | Xác thực nguồn gốc và nội dung |

Manifest này là metadata do pipeline triển khai định nghĩa, không phải schema CRaC chuẩn. Cần xác thực manifest trước khi tin các trường của nó. Nếu compatibility check thất bại, chuyển sang cold start và ghi lý do cụ thể.

Không nên so sánh chỉ chuỗi Java major version. Hai bản JDK cùng Java 21 có thể khác vendor, patch, build hoặc CRaC implementation. Dùng compatibility matrix do tổ chức kiểm chứng hoặc tài liệu chính thức của vendor.

## 7. Kiểm tra resource profile trước restore

Checkpoint có thể chứa heap, native memory, thread và các quyết định runtime đã hình thành trong môi trường nguồn. Restore vào container có giới hạn nhỏ hơn có thể gây OOM hoặc không tạo thêm được thread.

Trước khi restore, nên đối chiếu:

- CPU quota và cpuset.
- JVM availableProcessors được dùng lúc tạo checkpoint.
- Memory limit và headroom dự kiến.
- Heap maximum và mức sử dụng tại checkpoint.
- Direct memory, metaspace, code cache và thread stack.
- PIDs limit.
- Disk space cho restore staging.
- Network access và file system mount cần thiết.

Một profile đích không phù hợp nên được đánh dấu là không đủ điều kiện restore. Cold start có thể chọn heap sizing và concurrency theo giới hạn mới, nếu JVM được khởi động với flags phù hợp. Tuy nhiên, cold start cũng không thể chạy ổn định nếu container thực sự thiếu tài nguyên cho workload.

Không nên hạ memory limit một cách tùy tiện rồi kỳ vọng fallback luôn cứu được instance. Đường cold start cần được benchmark trong cùng resource limit.

## 8. Kiểm tra artifact trước khi gọi restore

Preflight nên xác minh artifact đã được publish hoàn chỉnh:

1. Checkpoint operation đã báo hoàn tất.
2. Danh sách file bắt buộc đầy đủ.
3. Kích thước file không bằng 0 ngoài trường hợp được định nghĩa.
4. Manifest khớp với file list và artifact ID.
5. Checksum, MAC hoặc chữ ký hợp lệ.
6. Artifact không bị đánh dấu incomplete, revoked hoặc expired.
7. Storage object version đúng với manifest.
8. Quyền đọc và giải mã có sẵn cho workload restore.

Nếu artifact được mã hóa, xác minh metadata và quyền KMS trước khi giải mã. Không đưa một artifact có signature sai hoặc AEAD authentication failure vào runtime. Hãy đánh dấu artifact bị lỗi hoặc quarantine theo policy để không liên tục thử lại cùng một image hỏng.

Preflight không thay thế kiểm tra của CRaC runtime. Một artifact vượt qua checksum vẫn có thể không tương thích với kernel hoặc chứa trạng thái resource không thể khôi phục.

## 9. Phân loại lỗi để quyết định fallback

Không phải mọi lỗi đều nên kích hoạt cold start ngay lập tức. Phân loại giúp tránh retry vô ích và tránh che giấu lỗi cấu hình.

| Nhóm lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Artifact không tồn tại | File bị xóa, chưa publish | Cold start |
| Artifact hỏng/không xác thực | Thiếu file, checksum/tag/signature sai | Quarantine artifact, cold start |
| Runtime không tương thích | JDK build, architecture hoặc engine khác | Cold start; cập nhật compatibility metadata |
| Resource không đủ | Memory/PIDs không đạt profile | Cold start nếu profile hỗ trợ; nếu không thì fail rõ ràng |
| Restore engine lỗi | CRIU/kernel/resource restore failure | Ghi chẩn đoán, cold start nếu lỗi không phải transient |
| Dependency tạm thời lỗi | KMS, metadata, database hoặc DNS timeout | Retry có giới hạn hoặc chờ dependency; không mặc định cold start |
| Ứng dụng lỗi cấu hình | Property sai, schema không tương thích | Fail fast; cold start có thể lỗi tương tự |
| Callback afterRestore lỗi | Reconnect client thất bại | Thử recovery có giới hạn; sau đó dừng process và fallback |
| Readiness timeout | Dependency hoặc worker chưa sẵn sàng | Chẩn đoán nguyên nhân; dừng process trước khi chuyển mode |

Ví dụ, artifact bị thiếu là điều kiện rõ ràng để bỏ qua restore. Ngược lại, KMS timeout trong vài giây có thể là lỗi tạm thời; một lần cold start ngay lập tức có thể vẫn cần KMS hoặc secret manager và thất bại giống hệt. Dùng retry/backoff có giới hạn cho dependency tạm thời.

## 10. Chính sách retry trước khi cold start

Retry restore có thể hữu ích khi lỗi do storage/network tạm thời, nhưng retry một artifact không tương thích thường chỉ lặp lại cùng lỗi.

Một chính sách hợp lý phân biệt:

- **Không retry:** Signature sai, artifact thiếu file, JDK/architecture không tương thích, checkpoint bị thu hồi.
- **Retry ngắn có giới hạn:** Storage timeout, lỗi tải artifact tạm thời, KMS throttling hoặc lỗi transient đã được xác định.
- **Không chuyển cold start ngay:** Dependency thiết yếu đang unavailable nếu cold start cũng phụ thuộc cùng dependency.
- **Cold start sau restore failure:** Runtime không thể restore artifact và ứng dụng có thể khởi động sạch.
- **Fail deployment:** Cả restore lẫn cold start đều không đạt điều kiện tối thiểu hoặc cấu hình không hợp lệ.

Dùng exponential backoff có jitter cho lỗi transient. Đặt tổng thời gian retry tối đa để instance không chờ vô hạn. Ghi số lần thử và nguyên nhân từng lần.

Không retry vô hạn trong cùng container. Điều đó có thể giữ tài nguyên, làm chậm rollout và khiến orchestrator liên tục restart pod.

## 11. Cold start phải dùng cùng cấu hình ứng dụng hiện tại

Khi chuyển sang khởi động thông thường, dùng application artifact và configuration được phát hành cho deployment hiện tại. Không lấy cấu hình cũ từ checkpoint metadata làm nguồn sự thật cho các giá trị cần thay đổi.

Cold-start path cần:

- Chạy đúng JDK runtime được hỗ trợ.
- Dùng cùng application build đã được deploy.
- Nạp environment variables, ConfigMap/secret hoặc config service hiện hành.
- Tạo instance identity mới.
- Resolve credential mới.
- Tạo connection pool và client mới.
- Khởi tạo Spring ApplicationContext từ đầu.
- Chạy migration hoặc startup task theo quy tắc idempotent.
- Warm-up nếu cần.
- Đạt readiness trước khi nhận traffic.

Đừng để cold-start fallback vô tình chạy một file JAR khác, profile khác hoặc Java flags khác với deployment dự kiến. Nếu cold start là đường vận hành chính thức, nó phải được kiểm thử như một startup mode độc lập.

## 12. Không dùng lại trạng thái nghiệp vụ cũ một cách mù quáng

Checkpoint có thể chứa trạng thái trong heap tại thời điểm tạo ảnh. Nếu restore không thành công và ứng dụng cold start, heap state đó sẽ không tồn tại. Những dữ liệu cần tiếp tục công việc phải được lưu ở hệ thống bền vững.

Thiết kế nghiệp vụ nên bảo đảm:

- Progress quan trọng được commit vào database hoặc durable store.
- Job có thể resume từ checkpoint nghiệp vụ hoặc cursor đã lưu.
- Side effect có idempotency key hoặc operation ID.
- Message consumer commit offset theo đúng semantics.
- Scheduler và leader election acquire lease mới.
- Không dựa vào một biến static hoặc object trong heap làm nguồn duy nhất của tiến độ.
- Startup task có thể chạy lại an toàn hoặc có cơ chế xác định đã hoàn thành.

Nếu restore thất bại, cold start có thể chạy lại startup hook. Các hook tạo tài khoản, gửi email, tạo schema hoặc phát message cần có tính idempotent hoặc transaction rõ ràng.

## 13. Xử lý lỗi afterRestore và readiness

Có thể runtime restore thành công nhưng một resource không thể phục hồi. Ví dụ, connection pool không reconnect được, token hết hạn, DNS thay đổi hoặc file mount không tồn tại.

Một số ứng dụng có thể phục hồi tại chỗ bằng cách tạo lại client hoặc kết nối. Nếu resource không thể phục hồi sau số lần thử cho phép, hãy:

1. Giữ instance ở trạng thái not ready.
2. Ngừng nhận request và job mới.
3. Ghi lại resource ID và lỗi gốc.
4. Thử recovery theo timeout/backoff có giới hạn.
5. Nếu không thể phục hồi, kết thúc process với exit code hoặc trạng thái lỗi mà supervisor nhận biết.
6. Supervisor dừng process đã restore hoàn toàn.
7. Supervisor mới khởi chạy JVM cold-start.
8. Cold-start path tạo lại resource từ cấu hình hiện tại và kiểm tra readiness.

Không để một callback nuốt exception rồi báo restore thành công nếu dependency thiết yếu chưa hoạt động. Cũng không nên mở traffic chỉ vì HTTP port đã bind; readiness cần xác minh những dependency mà request thực tế cần dùng.

## 14. Ngăn hai process cùng chạy trong fallback

Một rủi ro lớn là supervisor khởi chạy cold JVM trong khi process restore cũ vẫn còn sống. Cả hai có thể:

- Cùng consume một message group hoặc partition.
- Cùng chạy scheduled job.
- Cùng giữ lease hoặc cố lấy distributed lock.
- Cùng nhận traffic qua cùng endpoint.
- Cùng thực hiện migration hoặc startup task.
- Ghi đè dữ liệu hoặc tạo side effect trùng.

Trước khi cold start sau lỗi post-restore, cần bảo đảm process cũ đã kết thúc hoặc bị dừng và không còn nhận traffic. Orchestrator cần quản lý process identity và readiness. Với workload có quyền sở hữu độc quyền, dùng lease và fencing token để ngăn stale process tiếp tục side effect.

Không dựa chỉ vào PID file cũ vì PID có thể được tái sử dụng. Supervisor cần theo dõi process handle, process group, container lifecycle hoặc một cơ chế quản lý đáng tin cậy của nền tảng.

## 15. Ví dụ supervisor pseudocode

Lệnh restore cụ thể khác nhau theo JDK vendor và nền tảng, vì vậy ví dụ dưới đây mô tả hợp đồng của một wrapper do đội triển khai cung cấp. Hàm restore-wrapper phải trả kết quả rõ ràng: restore không thể khởi chạy, hoặc supervisor đã tiếp quản và đang theo dõi process được restore.

~~~bash
#!/usr/bin/env bash
set -u

APP_JAR="/app/app.jar"
CHECKPOINT_DIR="/checkpoint/current"

log() {
  printf '%s %s\n' "$(date -Iseconds)" "$*"
}

if [ -d "$CHECKPOINT_DIR" ] && /app/bin/verify-checkpoint "$CHECKPOINT_DIR"; then
  log "Checkpoint passed preflight; attempting restore"

  /app/bin/restore-wrapper "$CHECKPOINT_DIR"
  restore_rc=$?

  if [ "$restore_rc" -eq 0 ]; then
    log "Restore supervisor completed normally"
    exit 0
  fi

  log "Restore failed with code $restore_rc; selecting cold start"
else
  log "No usable checkpoint; selecting cold start"
fi

exec java \
  -XX:MaxRAMPercentage=60 \
  -jar "$APP_JAR"
~~~

Đây là skeleton minh họa, không phải script dùng trực tiếp cho mọi CRaC distribution. Cần định nghĩa chính xác exit contract của restore-wrapper. Nếu restore command thành công rồi detach process, wrapper phải tiếp tục giám sát process đó và không được khởi chạy JVM thứ hai. Nếu process được restore nhưng sau đó readiness thất bại, supervisor phải dừng process cũ trước khi đi vào cold-start path.

Trong môi trường container, entrypoint shell có thể dùng exec để thay shell bằng JVM cold-start. Khi cần quản lý cả restore process lẫn cold process, có thể cần một supervisor chuyên biệt hoặc cơ chế process management của orchestrator thay vì script đơn giản.

## 16. Ví dụ Java cho quyết định preflight

Ứng dụng có thể định nghĩa một kết quả preflight có lý do rõ ràng. Phần này chạy trước khi gọi runtime restore, trong một launcher hoặc control component có thể thực thi trước process restore.

~~~java
public record RestoreEligibility(
        boolean eligible,
        String reason) {
}

public interface CheckpointInspector {
    RestoreEligibility inspect(
            String checkpointPath,
            RuntimeProfile target);
}

public record RuntimeProfile(
        String jdkVendor,
        String jdkBuild,
        String os,
        String architecture,
        long memoryLimitBytes,
        int cpuCapacity) {
}
~~~

Một triển khai inspector có thể đọc manifest đã xác thực và so sánh với RuntimeProfile hiện tại. Không nên tự viết một phép so sánh chuỗi version đơn giản rồi coi đó là bảo đảm tương thích. Compatibility policy cần được xây dựng từ tài liệu runtime và các cấu hình đã được kiểm chứng.

Ví dụ logic quyết định:

~~~java
RestoreEligibility eligibility =
        inspector.inspect(checkpointPath, currentProfile);

if (!eligibility.eligible()) {
    logger.warn("Skipping CRaC restore: {}", eligibility.reason());
    return StartupMode.COLD;
}

return StartupMode.RESTORE;
~~~

Đây là logic lựa chọn mode ở tầng launcher. Nó không thể thay thế việc runtime xác nhận restore thực tế.

## 17. Giữ cold-start path đơn giản và độc lập

Cold start cần được duy trì ngay cả khi phần lớn instance production dùng checkpoint. Không nên chỉ kiểm thử restore rồi bỏ quên startup thông thường.

Một cold-start path tốt nên:

- Dùng entrypoint chính thức của ứng dụng.
- Có thể chạy trong cùng container image mà không cần checkpoint directory.
- Không yêu cầu artifact restore để khởi động.
- Tạo lại mọi client/socket/pool từ cấu hình hiện tại.
- Làm mới credential và identity.
- Khởi động scheduler/consumer theo readiness gate.
- Không chạy lại side effect không idempotent.
- Có timeout và health/readiness probe rõ ràng.
- Có thể được kích hoạt bằng một startup mode hoặc deployment flag.

Không nên để cold start phụ thuộc vào một biến môi trường chỉ được tạo ra bởi checkpoint pipeline. Các cấu hình cần thiết để ứng dụng khởi động từ đầu phải được đóng gói hoặc cấp bởi môi trường triển khai.

## 18. Cold start không phải lúc nào cũng là phương án đúng

Fallback có giới hạn. Có những lỗi mà cold start không thể giải quyết:

- Database hoặc message broker đang down.
- KMS/secret manager không truy cập được và ứng dụng cần nó để khởi động.
- Image ứng dụng sai hoặc thiếu dependency.
- Cấu hình production không hợp lệ.
- Container memory limit quá thấp cho cả cold start.
- JDK runtime không thể chạy ứng dụng.
- Schema database không tương thích.
- Network policy chặn mọi đường đến dependency.

Trong những trường hợp này, cold start có thể thất bại theo cùng cách. Hệ thống nên báo lỗi rõ ràng và để orchestrator retry theo chính sách hoặc dừng rollout. Đừng dùng fallback như cách che giấu lỗi hạ tầng hoặc lỗi cấu hình.

Có thể phân biệt ba kết quả cuối:

- RESTORE_READY: restore thành công và instance sẵn sàng.
- COLD_START_READY: restore không được dùng; startup thông thường thành công.
- STARTUP_FAILED: cả hai đường đều không đạt điều kiện phục vụ.

Metric và log cần giữ được startup mode cuối cùng để vận hành biết instance đang chạy theo đường nào.

## 19. Timeout và ngân sách startup

Đặt timeout riêng cho từng phase:

- Artifact discovery/preflight.
- Download và integrity verification.
- Restore engine.
- afterRestore resource recovery.
- Cold JVM startup.
- Application warm-up.
- Readiness.
- Tổng startup deadline.

Cold start thường chậm hơn restore. Nếu startup probe hoặc orchestrator timeout được đặt theo giả định mọi instance đều restore nhanh, fallback có thể bị kill trước khi ứng dụng khởi động xong.

Ví dụ ngân sách khái niệm:

| Phase | Timeout cần cân nhắc |
|---|---|
| Preflight | Đủ ngắn để loại artifact lỗi nhanh |
| Artifact download/decrypt | Theo kích thước image và network |
| Restore attempt | Theo baseline restore p95 và giới hạn an toàn |
| Cold start | Theo startup p95 trong resource profile đích |
| Dependency readiness | Theo timeout thực tế của service ngoài |
| Total startup | Bao trùm các phase và retry có giới hạn |

Không đặt một con số chung cho mọi ứng dụng. Dùng benchmark cold-start và restore-to-ready để cấu hình startup probe, liveness và orchestrator deadline. Readiness failure không nhất thiết phải restart process ngay; liveness failure mới thường dẫn đến restart theo policy.

## 20. Cập nhật checkpoint sau cold start

Nếu một checkpoint bị lỗi hoặc không còn tương thích, không nên tiếp tục dùng nó cho mọi lần khởi động. Có thể đánh dấu artifact là stale/quarantined và lên kế hoạch tạo checkpoint mới từ một instance đã khởi động sạch.

Một luồng có thể là:

1. Restore thất bại và artifact được đánh dấu không sử dụng.
2. Cold start thành công.
3. Ứng dụng đạt readiness và warm-up.
4. Pipeline tạo checkpoint mới theo cùng compatibility profile.
5. Artifact mới được verify, publish và gắn generation mới.
6. Artifact cũ được giữ hoặc xóa theo retention policy.

Không tạo checkpoint mới ngay trong lúc cold-start fallback còn đang xử lý request hoặc dependency chưa ổn định. Hãy tuân thủ quy trình quiesce và kiểm tra tài nguyên như các lần checkpoint bình thường.

Nếu artifact cũ chỉ lỗi do một sự cố storage tạm thời, không nhất thiết phải xóa ngay. Quarantine và lưu nguyên nhân giúp điều tra. Chỉ xóa theo retention và policy được phê duyệt.

## 21. Triển khai trên Kubernetes hoặc orchestrator

Với Kubernetes, một container có thể chạy entrypoint wrapper để chọn restore hoặc cold start. Orchestrator vẫn quản lý restart, readiness, liveness và rollout. Cần cấu hình probe đủ thời gian cho cả hai mode.

Một số nguyên tắc:

- Readiness probe chỉ thành công khi ứng dụng thật sự phục vụ được.
- Startup probe cho phép cold start lâu hơn liveness interval thông thường.
- Liveness không nên fail chỉ vì một dependency bên ngoài tạm thời lỗi nếu process vẫn có thể phục hồi.
- Pod không ready không nhận traffic từ Service theo cơ chế readiness chuẩn.
- Rolling update cần đủ surge capacity để cold-start fallback không làm cạn capacity.
- Checkpoint volume và quyền truy cập phải sẵn sàng trước khi entrypoint thử restore.
- Log cần phân biệt restore attempt và cold-start attempt.

Nếu dùng init container để download hoặc verify artifact, nhớ rằng init container chỉ hoàn thành preflight; nó không thể thay thế runtime restore operation nếu restore cần khôi phục process state. Cách phối hợp phải phù hợp với CRaC runtime và container lifecycle.

## 22. Bảo mật và tính toàn vẹn trong fallback

Fallback không được làm yếu kiểm tra bảo mật của restore. Nếu signature sai hoặc encryption authentication thất bại, không giải mã/restore artifact chỉ để thử thêm lần nữa.

Một số yêu cầu:

- Xác thực artifact trước khi đưa cho runtime.
- Chỉ workload identity được phép mới đọc/decrypt checkpoint.
- Không log token, key hoặc signed URL.
- Quarantine artifact lỗi để tránh vòng lặp.
- Không tự động tải artifact từ nguồn không tin cậy khi restore thất bại.
- Dùng cùng chính sách secret và identity cho cold-start path.
- Ghi audit event về quyết định bỏ qua checkpoint và lý do.
- Bảo vệ checkpoint metadata và log vì chúng có thể tiết lộ cấu hình.

Cold start cần lấy credential mới từ identity provider, không lấy token đã lưu trong checkpoint manifest. Artifact metadata có thể dùng để kiểm tra compatibility, nhưng không phải nguồn sự thật cho secret hiện tại.

## 23. Quan sát fallback trong production

Nên có metric riêng cho từng startup mode và từng nguyên nhân:

| Metric | Ý nghĩa |
|---|---|
| startup_mode_total | Số lần restore hoặc cold start được chọn |
| restore_attempt_total | Tổng lần thử restore |
| restore_success_total | Restore thành công |
| restore_failure_total{reason} | Lỗi restore theo nhóm |
| restore_preflight_rejected_total{reason} | Artifact bị từ chối trước khi gọi runtime |
| cold_start_fallback_total{reason} | Số lần chuyển sang cold start |
| cold_start_duration | Thời gian JVM mới đến readiness |
| restore_to_ready_duration | Thời gian restore đến readiness |
| fallback_success_total | Cold start sau fallback thành công |
| startup_failure_total | Cả hai đường không đạt readiness |
| checkpoint_artifact_age | Tuổi artifact tại thời điểm restore |

Log mỗi lần startup nên có:

- Startup attempt ID.
- Instance/pod ID.
- Application build và JDK build.
- Checkpoint artifact ID/generation.
- Startup mode được chọn.
- Preflight result và reason.
- Restore exit/error classification.
- Cold-start reason nếu có fallback.
- Thời gian từng phase.
- Readiness result và dependency failures.

Không gắn nhãn mọi restore failure thành một lỗi chung. Phân loại rõ giúp biết nên sửa checkpoint pipeline, runtime compatibility, resource profile hay dependency.

## 24. Kiểm thử fallback có chủ đích

Fallback chỉ đáng tin khi được kiểm thử, không chỉ tồn tại trong code.

Các kịch bản cần có:

1. Không có checkpoint artifact: ứng dụng cold start thành công.
2. Artifact thiếu một file bắt buộc: preflight từ chối và cold start.
3. Manifest sai chữ ký hoặc checksum: artifact bị quarantine, cold start.
4. JDK build không khớp compatibility policy: bỏ qua restore.
5. Architecture hoặc runtime profile không được hỗ trợ: cold start hoặc fail theo policy.
6. Memory/PIDs limit thấp hơn ngưỡng: preflight từ chối hoặc runtime restore thất bại có kiểm soát.
7. Restore command trả lỗi trước khi process được khởi chạy: supervisor cold start.
8. Restore process chạy nhưng afterRestore thất bại: process không ready, được dừng rồi cold start nếu lỗi có thể khắc phục bằng khởi tạo mới.
9. Dependency bên ngoài down: xác nhận cold start không tạo vòng lặp retry vô hạn.
10. Cold start cũng thất bại: orchestrator nhận trạng thái lỗi rõ ràng.
11. Supervisor restart giữa lúc quyết định startup: không tạo hai process.
12. Artifact cũ được đưa lại: rollback policy xử lý đúng.
13. Nhiều replica cùng fallback: không tạo duplicate job hoặc consumer ownership.
14. Sau cold start, checkpoint mới được tạo và restore thử thành công.

Dùng artifact test và dữ liệu giả lập. Không cố tình phá checkpoint production hoặc làm gián đoạn dịch vụ thật để kiểm tra fallback.

## 25. Ví dụ ma trận quyết định

Một ma trận đơn giản giúp chuẩn hóa hành vi:

| Tình huống | Restore | Cold start | Kết quả mong đợi |
|---|---|---|---|
| Không có artifact | Bỏ qua | Có | Startup bình thường |
| Artifact không hợp lệ | Không thử | Có | Ghi reason, quarantine |
| Runtime mismatch | Không thử | Có nếu runtime cold-start hợp lệ | Startup mới |
| Storage timeout tạm thời | Retry giới hạn | Sau retry nếu policy cho phép | Không retry vô hạn |
| Restore engine lỗi không retryable | Thất bại | Có | Supervisor chuyển mode |
| afterRestore dependency lỗi tạm thời | Đã restore | Retry recovery/readiness giới hạn | Chưa mở traffic |
| afterRestore không thể phục hồi | Process không ready | Sau khi dừng process | Không chạy hai instance |
| Database down | Không giải quyết bằng restore | Có thể cũng không ready | Báo dependency failure |
| Cold start lỗi cấu hình | Không | Thất bại | Fail fast, không lặp vô hạn |

Ma trận cần được điều chỉnh theo semantics của runtime và loại workload. Với một số lỗi, policy an toàn nhất là fail deployment thay vì cold start.

## 26. Những lỗi thiết kế thường gặp

**Đặt fallback trong main() và kỳ vọng bắt mọi restore failure.** Runtime có thể thất bại trước khi Java code tiếp tục. Dùng launcher hoặc supervisor bên ngoài.

**Chạy cold JVM ngay sau khi restore command trả về.** Process restore có thể đã được khởi chạy hoặc detach. Xác định rõ exit contract và theo dõi process.

**Không dừng process đã restore nhưng chưa ready.** Cold JVM thứ hai có thể chạy song song và tạo side effect trùng. Dừng process cũ trước khi chuyển mode.

**Retry vô hạn cùng một checkpoint hỏng.** Lỗi không tự biến mất. Phân loại artifact corruption và quarantine.

**Cold start khi database hoặc KMS đang down.** Startup mới vẫn phụ thuộc các dịch vụ đó. Retry có giới hạn và báo dependency failure.

**Dùng checkpoint metadata làm cấu hình production hiện tại.** Endpoint, credential và identity có thể cũ. Cold start phải nạp config từ deployment hiện tại.

**Không kiểm tra signature hoặc integrity trước restore.** Artifact bị sửa có thể được đưa vào runtime. Xác minh trước khi restore.

**Đánh dấu ready ngay khi process tồn tại.** Dependency hoặc worker có thể chưa phục hồi. Readiness phải phản ánh khả năng phục vụ.

**Để startup hook tạo side effect không idempotent.** Cold start có thể chạy lại hook sau một restore failure. Dùng operation ID, transaction hoặc idempotency.

**Không đo fallback rate.** Hệ thống có thể âm thầm cold start gần như mọi lần. Theo dõi restore success và fallback reason.

**Chỉ kiểm thử đường restore.** Khi checkpoint hỏng, ứng dụng không có đường phục hồi đã xác nhận. Test cold start độc lập và test chuyển mode.

## 27. Checklist vận hành fallback

- [ ] Có launcher/supervisor bên ngoài process restore không?
- [ ] Đã định nghĩa rõ restore command, exit contract và process ownership chưa?
- [ ] Preflight xác minh artifact completeness, integrity và compatibility chưa?
- [ ] JDK vendor/build, OS, architecture, kernel và CRaC engine có được đối chiếu không?
- [ ] CPU, memory, PIDs và storage profile có đạt mức đã kiểm chứng không?
- [ ] Lỗi được phân loại thành permanent, transient, dependency hoặc application failure chưa?
- [ ] Retry có giới hạn thời gian, số lần và backoff/jitter chưa?
- [ ] Artifact lỗi có được quarantine để tránh thử lại vô hạn không?
- [ ] Cold-start path dùng đúng JDK, application build và configuration hiện tại không?
- [ ] Credential, identity, DNS và client có được tạo/làm mới theo môi trường hiện tại không?
- [ ] Startup hook và job có idempotent hoặc có durable progress không?
- [ ] Process restore lỗi có được dừng trước khi cold JVM chạy không?
- [ ] Readiness chỉ thành công khi dependency và worker thiết yếu sẵn sàng không?
- [ ] Startup probe/deadline có đủ thời gian cho cold start không?
- [ ] Metric/log có ghi startup mode và fallback reason không?
- [ ] Đã thử artifact missing/corrupt, runtime mismatch, afterRestore failure và cold-start failure chưa?
- [ ] Đã kiểm tra nhiều replica fallback không tạo duplicate side effect chưa?
- [ ] Có kế hoạch tạo checkpoint mới sau cold start thành công không?

## Kết luận

Khởi động thông thường là đường dự phòng cần thiết khi checkpoint không thể restore trong môi trường đích. Restore có thể thất bại trước khi application code tiếp tục, vì vậy quyết định fallback phải được thực hiện ở launcher, supervisor hoặc orchestrator. Nếu process đã restore nhưng callback hoặc readiness thất bại, phải phục hồi có giới hạn hoặc dừng process đó trước khi khởi chạy JVM mới.

Thiết kế đáng tin cậy cần preflight artifact và compatibility, phân loại lỗi, giới hạn retry, giữ cold-start path độc lập, nạp cấu hình và identity hiện tại, đồng thời ngăn hai process cùng chạy. Cold start không chữa được dependency outage hay cấu hình ứng dụng sai; các trường hợp đó cần được báo rõ và xử lý theo policy. Khi đo riêng restore success, fallback rate, cold-start duration và readiness, đội vận hành có thể biết checkpoint đang mang lại lợi ích thực tế hay hệ thống thường xuyên phải quay về startup thông thường.
