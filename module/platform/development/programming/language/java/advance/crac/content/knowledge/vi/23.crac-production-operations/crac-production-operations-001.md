# Thiết kế pipeline dựng ứng dụng, làm nóng, tạo ảnh và kiểm chứng

Một pipeline CRaC production cần làm nhiều hơn việc khởi động JVM rồi gọi lệnh checkpoint. Nó phải tạo ra một ứng dụng có thể tái lập, chạy warm-up an toàn, đưa tài nguyên về trạng thái phù hợp, tạo ảnh checkpoint hoàn chỉnh, kiểm tra ảnh trong môi trường tương thích và chỉ publish artifact khi các bước xác minh đạt yêu cầu.

Pipeline nên xem checkpoint image là artifact triển khai bất biến gắn với một build, JDK/CRaC runtime, cấu hình nền tảng và môi trường tạo ảnh cụ thể. Nếu build thay đổi, runtime thay đổi hoặc dependency không còn tương thích, ảnh cũ có thể không dùng được dù file vẫn tồn tại và checksum vẫn đúng.

Luồng tổng quát:

```text
Source + dependencies
        |
        v
Build application artifact
        |
        v
Create pinned runtime/container image
        |
        v
Start application in checkpoint environment
        |
        v
Warm up classes, JIT, caches and safe resources
        |
        v
Verify warm-up and application readiness
        |
        v
Quiesce and prepare CRaC resources
        |
        v
Create checkpoint image
        |
        v
Package + manifest + checksum/signature
        |
        v
Restore in a clean compatible test environment
        |
        v
Smoke tests + readiness + performance checks
        |
        v
Publish immutable artifact and promote
```

Điểm quan trọng là tách **build thành công**, **warm-up thành công**, **checkpoint thành công**, **restore thành công** và **ứng dụng sẵn sàng phục vụ** thành các trạng thái độc lập. Không được coi một bước là bằng chứng tự động cho bước tiếp theo.

## 1. Mục tiêu và ranh giới pipeline

Pipeline cần trả lời được bốn câu hỏi:

1. **Đang tạo ảnh từ build nào?** Phải truy vết được source commit, application artifact, dependency, JDK/CRaC runtime và cấu hình.
2. **Warm-up đã thực sự hoàn tất chưa?** Phải có tiêu chí đo được, không chỉ chờ một khoảng thời gian cố định.
3. **Ảnh checkpoint có thể restore không?** Cần restore thử trên môi trường tương thích và kiểm tra callback/resource.
4. **Ứng dụng sau restore có hoạt động đúng không?** Cần health check và smoke test nghiệp vụ, không chỉ kiểm tra process còn sống.

Pipeline thường có hai loại artifact:

| Artifact | Nội dung | Mục đích |
| --- | --- | --- |
| Application/runtime artifact | JAR, dependency, container image hoặc filesystem nền | Cung cấp đúng code và runtime để tạo/restore checkpoint. |
| CRaC checkpoint artifact | Trạng thái process được checkpoint | Khởi động nhanh từ trạng thái đã warm-up. |

Hai artifact phải được liên kết bằng manifest. Không publish checkpoint độc lập với runtime image mà nó phụ thuộc. Một deployment cần biết chính xác image/container digest, checkpoint id và compatibility profile tương ứng.

## 2. Chọn kiến trúc pipeline: build một lần, checkpoint trong môi trường chuẩn

Một mô hình dễ kiểm soát là:

- Build JAR/container image từ source commit xác định.
- Dùng runtime image đã pin phiên bản JDK/CRaC và native dependency.
- Khởi chạy ứng dụng trong môi trường chuyên dùng để warm-up và checkpoint.
- Lưu checkpoint vào staging riêng.
- Restore thử bằng đúng runtime image và cấu hình tương thích.
- Chỉ sau khi restore test thành công mới publish checkpoint cùng metadata.

Không nên build lại source hoặc tải dependency phiên bản mới trong bước warm-up. Nếu code hoặc dependency thay đổi giữa lúc build và lúc tạo checkpoint, artifact không còn tái lập được.

Có thể tạo checkpoint trong CI runner, trong một job Kubernetes chuyên biệt hoặc trong một môi trường build service riêng. Lựa chọn phụ thuộc khả năng hỗ trợ CRaC/CRIU của kernel, container runtime, privilege, cgroup, filesystem và CPU. Một runner thông thường không nhất thiết có đủ capability để checkpoint/restore container.

Nếu CI không hỗ trợ CRaC, tách pipeline thành hai giai đoạn: CI build và publish runtime image; một checkpoint builder có môi trường tương thích lấy image bất biến đó, warm-up, tạo ảnh và gửi kết quả trở lại artifact registry. Cả hai giai đoạn phải dùng cùng build id và manifest.

## 3. Pin phiên bản để ảnh có thể tái lập

Checkpoint phụ thuộc nhiều yếu tố hơn JAR. Manifest nên ghi nhận tối thiểu:

- Git commit và application build version.
- JAR checksum hoặc container image digest.
- JDK vendor, version, build và CRaC implementation.
- CRaC API/library version và JVM flags quan trọng.
- CRIU version/capabilities nếu nền tảng sử dụng CRIU.
- OS distribution, kernel version và CPU architecture/feature baseline.
- Container runtime, Kubernetes version và security configuration nếu áp dụng.
- Native library, agent, JNI/JNA dependency và driver quan trọng.
- Mount layout, filesystem type, UID/GID mapping và cgroup configuration cần thiết.
- Warm-up profile, dataset version và checkpoint configuration.

Không chỉ pin dependency trong Maven/Gradle. Cần pin cả base image bằng digest, package hệ điều hành và runtime JDK. Nếu dùng tag động như `latest`, hai lần chạy pipeline có thể tạo ảnh từ runtime khác nhau dù source commit không đổi.

Ví dụ cấu hình image nên dùng digest cụ thể:

```dockerfile
FROM registry.example.com/java-crac-runtime@sha256:<immutable-digest>

WORKDIR /opt/myapp
COPY build/libs/myapp.jar /opt/myapp/myapp.jar

ENTRYPOINT ["java", "-XX:CRaCCheckpointTo=/var/lib/myapp/checkpoint", "-jar", "/opt/myapp/myapp.jar"]
```

Digest trong ví dụ là placeholder. JVM flags và đường dẫn checkpoint phải theo JDK/runtime đang sử dụng. Không đưa secret vào Dockerfile, image layer hoặc command line; cấp secret tại runtime theo cơ chế bảo mật của môi trường.

## 4. Tách build, warm-up và checkpoint thành các job có trạng thái

Pipeline nên biểu diễn rõ trạng thái để có thể retry một bước mà không vô tình dùng lại dữ liệu dở dang.

| Job | Đầu vào | Đầu ra | Điều kiện thành công |
| --- | --- | --- | --- |
| Build | Source commit, lockfile, build config | JAR và runtime image | Build/test thành công; digest và checksum được ghi nhận. |
| Provision | Runtime image và checkpoint profile | Environment sẵn sàng | Kernel/runtime/capability/mount phù hợp. |
| Start | Runtime image, cấu hình không chứa secret cố định | Process đang chạy | Startup health đạt. |
| Warm-up | Process và warm-up workload | JVM/cache ở trạng thái mục tiêu | Warm-up criteria và workload assertions đạt. |
| Prepare | Process đã warm-up | Resource quiesced | Worker/transaction/resource được chuẩn bị trong deadline. |
| Checkpoint | Process đã prepare | Checkpoint directory | Runtime xác nhận checkpoint hoàn tất. |
| Package | Checkpoint directory | Archive, manifest, checksum | File/metadata được bảo toàn và checksum đúng. |
| Restore validation | Runtime image + checkpoint | Test result | Restore callback, readiness và smoke tests đạt. |
| Publish | Artifact đã xác minh | Immutable checkpoint artifact | Artifact registry ghi nhận published state. |
| Promote | Artifact đã publish | Deployment reference | Canary/rollout policy chấp nhận. |

Mỗi job nên có attempt id riêng, log có cấu trúc và output rõ ràng. Không dùng một thư mục checkpoint cố định cho nhiều job chạy song song.

## 5. Chuẩn bị môi trường warm-up

Warm-up cần chạy trong môi trường có cấu hình gần với môi trường restore production, nhưng không nên dùng dữ liệu hoặc quyền production không cần thiết.

Các yếu tố cần khớp hoặc được khai báo:

- JDK/CRaC runtime và JVM options.
- CPU architecture và feature baseline.
- Container user, UID/GID, capabilities và cgroup limits.
- Mount path, filesystem, working directory và file permission.
- Environment profile, feature flags và cấu hình ứng dụng.
- Phiên bản schema/database client và API contract.
- DNS/service discovery/network policy ở mức tương thích.
- Secret provider identity và cách cấp credential sau restore.

Không cần dùng cùng một database production để warm-up. Có thể dùng database staging hoặc fixture data đại diện. Nếu cần warm-up kết nối tới dependency thật, dùng tài khoản giới hạn quyền và dữ liệu test được kiểm soát.

Mục tiêu là tạo ra trạng thái JVM có ích khi restore, đồng thời giữ được khả năng làm mới tài nguyên bên ngoài đã thay đổi. Đừng warm-up bằng cách nhét một lượng lớn dữ liệu nhạy cảm vào cache chỉ để làm cho checkpoint có vẻ “ấm”.

## 6. Thiết kế warm-up workload có đại diện

Warm-up nên mô phỏng các đường code quan trọng của ứng dụng:

- Load class và khởi tạo framework/DI container.
- Khởi tạo serializer, mapper, validator và template.
- Chạy một tập request đại diện cho API quan trọng.
- Thực thi các đường code thường xuyên để JVM có cơ hội JIT compile.
- Nạp cache tham chiếu có thể giữ an toàn qua checkpoint nếu freshness policy cho phép.
- Chuẩn bị metadata và lookup không chứa dữ liệu production.
- Khởi tạo các cấu trúc dữ liệu dùng chung.

Không nhất thiết phải chạy mọi API. Chọn workload theo traffic profile và business criticality. Một warm-up profile có thể khai báo danh sách route, loại request, số lần lặp, dữ liệu fixture, concurrency và tiêu chí latency.

Ví dụ profile dạng YAML:

```yaml
warmup:
  profile: standard-api-v3
  timeout: 5m
  concurrency: 4
  scenarios:
    - name: health-read
      method: GET
      path: /internal/catalog/sample
      iterations: 20
      expectedStatus: 200
    - name: search-validation
      method: POST
      path: /internal/search
      fixture: search-small.json
      iterations: 30
      expectedStatus: 200
    - name: pricing-calculation
      method: POST
      path: /internal/pricing/preview
      fixture: pricing-fixture.json
      iterations: 20
      expectedStatus: 200
```

Đây là schema minh họa của pipeline, không phải định dạng được Spring Boot hoặc CRaC tự hiểu. Warm-up runner của dự án cần parse profile, giới hạn payload và kiểm tra response.

## 7. Tránh side effect khi warm-up

Warm-up không được vô tình tạo giao dịch thật. Một request có thể gửi email, trừ tiền, publish message, cập nhật dữ liệu, tăng counter hoặc tạo job nền.

Các cách kiểm soát:

- Dùng fixture data và tenant test.
- Dùng endpoint preview/dry-run nếu ứng dụng hỗ trợ.
- Tắt outbound notification hoặc trỏ tới sink giả lập.
- Dùng database/schema riêng cho warm-up.
- Dùng broker/topic riêng hoặc consumer không thực hiện nghiệp vụ thật.
- Tắt scheduler tạo công việc production trong warm-up profile.
- Gắn idempotency key test và cleanup dữ liệu sau warm-up.
- Không dùng credential có quyền ghi production nếu chỉ cần warm-up class/JIT.

Không chỉ dựa vào environment variable `WARMUP=true` nếu code nghiệp vụ không thực sự tôn trọng nó. Hãy kiểm thử rằng các side effect bị chặn ở tầng phù hợp.

Nếu warm-up cần tạo cache, xác định dữ liệu nào được phép giữ lại sau checkpoint. Cache có chứa quyền, credential, thông tin người dùng hoặc dữ liệu thay đổi nhanh nên được invalidate/refresh theo policy trong `afterRestore`.

## 8. Đo warm-up thay vì chỉ sleep

Một pipeline không nên chờ `sleep 60` rồi giả định JVM đã warm-up. Thời gian JIT compile phụ thuộc CPU, workload, compiler và trạng thái ứng dụng. Warm-up cần có điều kiện kết thúc rõ ràng.

Có thể dùng các tiêu chí:

- Startup readiness đạt.
- Tất cả scenario warm-up hoàn tất với status mong đợi.
- Số lần thực thi tối thiểu đạt.
- Latency p95/p99 ổn định qua các cửa sổ đo liên tiếp.
- Error rate bằng 0 hoặc nằm trong ngưỡng được định nghĩa.
- CPU/JIT activity giảm về mức ổn định theo profile nếu có telemetry phù hợp.
- Cache hit ratio hoặc số entry mục tiêu đạt ngưỡng nếu cache được warm-up.
- Không còn warm-up request hoặc background task chưa hoàn tất.

Ví dụ tiêu chí:

| Metric | Điều kiện minh họa |
| --- | --- |
| Scenario completion | 100% scenario bắt buộc thành công. |
| Error rate | 0 lỗi trong các request warm-up bắt buộc. |
| p95 latency | Dưới ngưỡng được cấu hình trong 3 cửa sổ liên tiếp. |
| Warm-up duration | Không vượt quá pipeline timeout. |
| Background work | Không còn task warm-up đang ghi dữ liệu. |
| Readiness | `ACCEPTING_TRAFFIC` trước khi bắt đầu prepare checkpoint. |

Các ngưỡng phải lấy từ baseline của ứng dụng và runner. Không dùng một giá trị latency chung cho mọi service.

## 9. JIT warm-up và tính ổn định của workload

JVM có thể biên dịch code theo mức độ nóng của method và profile runtime. Warm-up quá ngắn có thể không làm nóng các đường code quan trọng; warm-up không đại diện có thể tối ưu nhầm những đường code ít được dùng.

Nên:

- Chạy các route/operation quan trọng với input có hình dạng đại diện.
- Dùng concurrency gần với mô hình production nhưng giới hạn để không gây quá tải.
- Đo nhiều cửa sổ để nhận biết latency đã ổn định.
- Ghi lại warm-up profile version để so sánh giữa build.
- Tránh warm-up bằng dữ liệu ngẫu nhiên hoàn toàn nếu làm thay đổi code path không giống production.
- Tránh chỉ gọi health endpoint; health check thường không chạy qua business logic quan trọng.

JIT compilation không có một cờ hoặc metric duy nhất chứng minh toàn bộ ứng dụng đã tối ưu. Mục tiêu thực tế là giảm chi phí khởi động và ổn định các đường code quan trọng, sau đó đo hiệu năng sau restore bằng workload độc lập.

## 10. Resource CRaC cần được chuẩn bị trước khi tạo ảnh

Warm-up có thể mở connection, khởi động worker, tạo scheduler hoặc nạp cache. Trước checkpoint, các tài nguyên không thể giữ nguyên qua restore cần được đóng hoặc chuyển về trạng thái an toàn.

Một `Resource` có thể điều phối:

- Dừng nhận request/message mới.
- Drain request, transaction và worker đang chạy.
- Dừng scheduler để không phát sinh công việc mới.
- Flush dữ liệu bền vững theo chính sách.
- Đóng socket, connection pool hoặc client không thể tiếp tục.
- Giữ lại cấu hình logic và factory cần thiết để tạo lại resource.

Sau restore, callback `afterRestore` có thể:

- Refresh DNS, secret, credential và endpoint.
- Tạo connection pool/client mới.
- Khởi động lại scheduler/consumer theo thứ tự.
- Revalidate cache/version và trạng thái dependency.
- Chỉ mở readiness sau khi resource bắt buộc hoạt động.

Không coi warm-up thành công là lý do để giữ mọi socket hoặc credential trong ảnh. Một warm-up có thể làm nóng class/JIT và cache an toàn, trong khi network connection được đóng trước checkpoint và tạo mới sau restore.

## 11. Ví dụ Resource chuẩn bị và phục hồi tài nguyên

Ví dụ sau minh họa cách tách warm-up khỏi resource lifecycle. Các interface là abstraction của ứng dụng:

```java
import org.crac.Context;
import org.crac.Resource;

public final class ApplicationCracResource implements Resource {
    private final WorkCoordinator work;
    private final DependencyFactory dependencies;
    private final ReadinessGate readiness;

    public ApplicationCracResource(
            WorkCoordinator work,
            DependencyFactory dependencies,
            ReadinessGate readiness) {
        this.work = work;
        this.dependencies = dependencies;
        this.readiness = readiness;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        readiness.refuseTraffic();
        work.stopAcceptingNewWork();
        work.drainWithTimeout();
        dependencies.closeCheckpointSensitiveResources();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        dependencies.refreshConfigurationAndReconnect();
        dependencies.validateRequiredServices();
        work.resume();
        readiness.acceptTraffic();
    }
}
```

`drainWithTimeout()` và `refreshConfigurationAndReconnect()` phải có deadline hữu hạn. Trong triển khai thật, cần rollback nếu `beforeCheckpoint` thất bại hoặc checkpoint bị abort; không dùng `afterRestore` làm callback rollback. `acceptTraffic()` chỉ chạy sau khi toàn bộ dependency bắt buộc đã sẵn sàng.

Nếu Spring Boot version đã cung cấp CRaC integration cho lifecycle component, không đăng ký thêm coordinator làm cùng một việc. Kiểm tra ownership của từng Resource để tránh đóng hoặc start cùng một pool hai lần.

## 12. Trigger checkpoint từ pipeline

Sau khi warm-up và các precondition đạt, pipeline yêu cầu JVM tạo checkpoint. Cách trigger phụ thuộc JDK/CRaC distribution và runtime. Một số môi trường hỗ trợ diagnostic command qua `jcmd`, ví dụ:

```bash
jcmd <pid> JDK.checkpoint
```

Hãy xác nhận command có trong runtime bằng `jcmd <pid> help` hoặc tài liệu của JDK đang dùng. Tên command, quyền thực thi, process namespace và semantics khi checkpoint hoàn tất có thể phụ thuộc distribution/version.

Ứng dụng cũng có thể gọi CRaC API trong code theo thư viện/runtime tương ứng, ví dụ `org.crac.Core.checkpointRestore()`. API và exception type cần đối chiếu với dependency CRaC thực tế. Không gọi checkpoint từ request path production tùy tiện; nên dùng một control path riêng có authentication, authorization và trạng thái pipeline.

Pipeline cần chờ kết quả theo semantics runtime:

- Ghi lại thời điểm gửi yêu cầu checkpoint.
- Chờ lệnh/operation kết thúc hoặc nhận trạng thái checkpoint thành công.
- Kiểm tra log JVM/CRIU và output directory.
- Xác nhận không còn writer đang ghi checkpoint.
- Phân biệt exit code của command với trạng thái thành công của ảnh.
- Nếu timeout, không lập tức copy thư mục hoặc xóa ảnh; trước tiên xác định runtime/process còn hoạt động hay không.

Một số API có thể tạm dừng luồng gọi cho tới khi process được restore; một số cách điều khiển ngoài process có thể báo kết quả theo cách khác. Pipeline phải theo tài liệu runtime cụ thể, không giả định mọi lệnh checkpoint đều có cùng exit behavior.

## 13. Tạo checkpoint trong thư mục staging riêng

Mỗi pipeline run cần một checkpoint path riêng:

```text
/var/lib/myapp/crac/
├── staging/
│   └── build-<build-id>/
│       └── attempt-<attempt-id>/
└── published/
    └── build-<build-id>/
```

Không tái sử dụng một thư mục có thể còn file từ attempt trước. Trước khi tạo ảnh, xác nhận dung lượng filesystem và quyền user chạy JVM. Đường dẫn phải tồn tại hoặc được tạo theo yêu cầu của runtime, có owner/permission đúng và nằm trên filesystem được hỗ trợ.

Nếu checkpoint thất bại, đánh dấu attempt là `FAILED` hoặc `INCOMPLETE`; không dùng thư mục đó làm input cho restore validation. Giữ log theo retention để điều tra rồi cleanup sau khi chắc chắn không còn process ghi.

## 14. Kiểm tra checkpoint đã hoàn tất

Không dùng một điều kiện duy nhất như “directory exists” hoặc “có file image” để xác định thành công. Pipeline nên kết hợp:

- Kết quả operation theo API/command của runtime.
- Exit status và log JVM/CRIU.
- Trạng thái process theo semantics của checkpoint mode.
- Cấu trúc output và metadata mà runtime mong đợi.
- Dung lượng/file count hợp lý so với baseline, chỉ dùng làm kiểm tra bất thường.
- Không còn tiến trình ghi vào checkpoint directory.

Nếu runtime hỗ trợ status/metadata command chính thức, dùng command đó thay cho suy đoán từ tên file. Không chỉnh sửa hoặc xóa file nội bộ của checkpoint để làm cho pipeline “pass”.

## 15. Đóng gói và tạo manifest

Sau khi xác nhận checkpoint hoàn tất, pipeline có thể archive thư mục theo cách bảo toàn file metadata cần thiết. Nếu restore yêu cầu directory tree gốc, giải nén phải giữ đúng relative path và không tạo thêm cấp thư mục.

Manifest nên liên kết:

| Nhóm | Trường |
| --- | --- |
| Identity | Artifact id, build id, checkpoint attempt id, createdAt UTC. |
| Source | Git commit, JAR checksum, container image digest. |
| Runtime | JDK vendor/build, CRaC version, JVM flags, CRIU version. |
| Platform | OS, kernel, CPU architecture/features, container runtime. |
| Warm-up | Profile id/version, scenario count, duration, result summary. |
| Checkpoint | Callback results, checkpoint command/API, result status. |
| Package | Archive format, compression, size, SHA-256, signature. |
| Validation | Restore test environment, restore duration, readiness result, smoke test version. |
| Promotion | Registry location, artifact state and deployment reference. |

Không đưa secret, access token, password, private key hoặc dữ liệu người dùng vào manifest. Nếu warm-up dùng dataset fixture, chỉ lưu version/hash và tên fixture đã được phép công bố.

Tính checksum sau khi archive hoàn tất:

```bash
sha256sum checkpoint.tar > checkpoint.tar.sha256
sha256sum --check checkpoint.tar.sha256
```

Checksum giúp phát hiện thay đổi/hỏng file trong quá trình lưu trữ và truyền tải. Nó không chứng minh ảnh tương thích hoặc restore thành công.

## 16. Restore validation trong môi trường sạch

Một ảnh chỉ nên được publish sau khi đã restore thử trong môi trường tương thích. Test này nên dùng một sandbox sạch, không chia sẻ state với builder và không có process khác chiếm namespace/tài nguyên cần thiết.

Các điều kiện cần khớp:

- Cùng runtime image digest hoặc compatibility profile đã được chứng minh.
- JDK/CRaC/CRIU, kernel và CPU baseline phù hợp.
- Cấu hình container, user, mount, cgroup và namespace cần thiết.
- Dependency test endpoints và secret provider test identity.
- Checkpoint path được giải nén đầy đủ và có permission đúng.

Không restore vào môi trường production đang phục vụ traffic chỉ để kiểm chứng artifact. Dùng một instance test tách biệt và dependency staging hoặc test doubles.

## 17. Smoke test sau restore

Sau restore, pipeline phải xác nhận cả process và ứng dụng:

1. Process restore thành công, JVM tiếp tục chạy.
2. `afterRestore` callbacks hoàn tất; không có Resource bắt buộc bị lỗi.
3. DNS/secret/config được refresh nếu có thể thay đổi.
4. Connection pool/client được tạo lại và health check thành công.
5. Message consumer/scheduler khởi động đúng thứ tự nếu chúng thuộc phạm vi warm-up.
6. Readiness chuyển sang chấp nhận traffic sau khi dependency bắt buộc hoạt động.
7. API smoke test trả kết quả mong đợi.
8. Nghiệp vụ đọc/ghi thử không tạo side effect ngoài dự kiến.
9. Error rate và latency nằm trong ngưỡng.
10. Không có log chứa secret hoặc lỗi callback bị bỏ qua.

Không coi process `RUNNING` là đủ. Có thể dùng readiness endpoint, health indicator theo dependency và một tập request đại diện. Liveness nên kiểm tra process có khả năng tiếp tục hoạt động; không nên làm liveness phụ thuộc trực tiếp vào mọi dependency bên ngoài vì có thể tạo restart storm khi một service tạm thời outage.

## 18. Kiểm tra hiệu năng sau restore

Mục tiêu của CRaC thường là giảm thời gian khởi động và cải thiện thời gian tới readiness. Cần đo cùng một workload trước và sau khi áp dụng checkpoint.

Các mốc nên đo:

- Process launch/restore start.
- Thời điểm `afterRestore` bắt đầu và kết thúc.
- Thời gian reconnect từng dependency.
- Thời điểm readiness đạt.
- Thời gian tới request đầu tiên thành công.
- Latency p50/p95/p99 của smoke workload.
- CPU và memory sau restore.
- Số lần retry hoặc lỗi trong cửa sổ đầu tiên.

So sánh với baseline cold start bằng cùng runtime image, resource limit, dependency và workload. Nếu checkpoint làm giảm JVM startup nhưng `afterRestore` mất nhiều thời gian reconnect, RTO thực tế có thể không cải thiện như kỳ vọng.

Không đặt ngưỡng performance chỉ dựa trên một lần chạy. Dùng nhiều lần đo, cùng điều kiện và percentile phù hợp. Ghi nhận warm-up profile và runner hardware để giải thích biến động.

## 19. Canary và promotion artifact

Sau khi restore validation đạt, publish checkpoint thành artifact bất biến. Không ghi đè artifact cũ hoặc thay nội dung dưới cùng artifact id.

Quy trình promotion có thể là:

1. Publish checkpoint và runtime image digest vào registry.
2. Gắn trạng thái `VALIDATED` sau restore smoke test.
3. Deploy một canary instance dùng đúng artifact id.
4. Kiểm tra readiness, error rate, latency và dependency behavior.
5. Tăng dần tỷ lệ traffic nếu canary đạt.
6. Nếu lỗi, rollback deployment pointer về artifact/runtime pair đã biết tốt.
7. Giữ artifact trước đó trong rollback window.

Không promote chỉ vì checksum đúng hoặc restore process thành công. Cần xác nhận ứng dụng sau restore thực sự phục vụ request.

## 20. Rollback và checkpoint cũ

Checkpoint cũ có thể không tương thích với database schema, secret version, DNS hoặc service API hiện tại. Vì vậy, rollback không đơn giản là trỏ về checkpoint cũ.

Trước khi cho phép rollback, xác nhận:

- Application build còn tương thích schema database.
- Secret provider có thể cấp credential hiện hành.
- Endpoint/service API vẫn hỗ trợ phiên bản cũ.
- Cache/lease/token trong ảnh sẽ được invalidate hoặc refresh.
- Runtime/kernel/CPU compatibility vẫn đáp ứng.
- Message consumer offset và event schema không làm xử lý lại dữ liệu sai.

Một rollback có thể dùng runtime image cũ nhưng tạo checkpoint mới từ build đó trong môi trường hiện hành. Với hệ thống có schema migration, dùng expand-and-contract để duy trì tương thích trong rollback window.

## 21. Bảo mật trong pipeline

Checkpoint có thể chứa secret và dữ liệu người dùng trong heap. Warm-up cũng có thể nạp payload và cache vào memory. Do đó pipeline phải bảo vệ cả môi trường builder lẫn artifact:

- Dùng secret manager hoặc workload identity; không hardcode secret trong pipeline YAML, Dockerfile hoặc command line.
- Dùng credential test có quyền tối thiểu.
- Không warm-up bằng dữ liệu production nếu không có cơ chế bảo vệ được phê duyệt.
- Không in environment hoặc system properties toàn bộ vào log.
- Mã hóa checkpoint khi lưu và khi truyền.
- Giới hạn quyền đọc, copy, restore và delete.
- Ghi audit cho artifact access.
- Giữ retention phù hợp; xóa staging và artifact cũ theo reference/lease.
- Không đưa checkpoint/heap dump vào ticket hoặc chat thông thường.
- Ký manifest nếu cần xác thực nguồn phát hành.

Không giả định đóng pool hoặc xóa một biến secret trước checkpoint sẽ loại bỏ mọi bản sao khỏi heap. Thiết kế nên hạn chế secret được nạp vào process builder và dùng cơ chế refresh credential sau restore.

## 22. Ví dụ pipeline dạng YAML minh họa

Đoạn dưới đây mô tả cấu trúc pipeline trung lập, không phải cú pháp copy trực tiếp cho GitHub Actions, GitLab CI hay Jenkins. Từng bước cần được chuyển thành job/task theo CI engine thực tế:

```yaml
pipeline:
  build:
    steps:
      - checkout_source
      - resolve_locked_dependencies
      - run_unit_tests
      - build_application
      - build_runtime_image
      - record_build_manifest

  checkpoint:
    needs: build
    environment: crac_compatible_builder
    steps:
      - verify_runtime_and_kernel
      - create_unique_attempt_directory
      - start_application
      - wait_for_startup_readiness
      - run_warmup_profile
      - verify_warmup_criteria
      - request_checkpoint
      - verify_checkpoint_completion
      - package_checkpoint
      - generate_checksum_and_manifest
      - upload_to_staging

  validate:
    needs: checkpoint
    environment: compatible_restore_sandbox
    steps:
      - download_immutable_candidate
      - verify_checksum_and_manifest
      - verify_compatibility
      - extract_checkpoint
      - restore_application
      - wait_for_after_restore_and_readiness
      - run_smoke_tests
      - measure_restore_to_ready
      - publish_validation_result

  publish:
    needs: validate
    when: validation_success
    steps:
      - publish_immutable_artifact
      - update_deployment_reference
      - retain_previous_release
```

Pipeline engine cần thực hiện dependency ordering, retry policy và cleanup rõ ràng. Nếu job checkpoint bị retry, phải tạo attempt id mới hoặc có cơ chế xác nhận attempt trước đã kết thúc và thư mục staging không còn được sử dụng.

## 23. Ví dụ shell orchestration ở mức khái niệm

Một script orchestration có thể kiểm tra từng bước và dừng ngay khi điều kiện không đạt. Ví dụ sau chỉ minh họa thứ tự, cần thay command và health endpoint theo runtime/ứng dụng thật:

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_PID="${APP_PID:?APP_PID must be set}"
CHECKPOINT_DIR="${CHECKPOINT_DIR:?CHECKPOINT_DIR must be set}"
WARMUP_URL="${WARMUP_URL:?WARMUP_URL must be set}"

curl --fail --silent "$WARMUP_URL/actuator/health/readiness"

# Warm-up runner executes the versioned profile and exits non-zero on failure.
./bin/run-warmup --profile standard-api-v3 --timeout 5m

# Confirm the warm-up runner has no outstanding work before checkpoint.
./bin/verify-warmup-state

# Runtime-specific command; confirm support on the selected CRaC JDK.
jcmd "$APP_PID" JDK.checkpoint

# The orchestrator must wait for the runtime's documented completion signal
# before packaging CHECKPOINT_DIR.
./bin/verify-checkpoint-complete "$CHECKPOINT_DIR"

tar --xattrs --acls --numeric-owner -cpf checkpoint.tar \
    -C "$(dirname "$CHECKPOINT_DIR")" "$(basename "$CHECKPOINT_DIR")"

sha256sum checkpoint.tar > checkpoint.tar.sha256
```

Đoạn script không phải implementation hoàn chỉnh cho mọi CRaC JDK. Đặc biệt, `JDK.checkpoint` và cách xác định checkpoint completion phải được xác nhận theo distribution/version; `verify-checkpoint-complete` là script riêng của pipeline. Không chạy `tar` cho tới khi runtime xác nhận checkpoint đã hoàn tất và không còn writer. Trong môi trường có thể bị shell interruption, cần quản lý trạng thái process và cleanup riêng thay vì giả định `set -e` giải quyết toàn bộ failure mode.

## 24. Quản lý trạng thái và retry của pipeline

Các job checkpoint thường tốn thời gian và tài nguyên. Retry thiếu kiểm soát có thể tạo nhiều ảnh, ghi đè artifact hoặc để lại thư mục dở dang.

Nên dùng state machine:

```text
BUILDING
   |
   v
BUILT
   |
   v
WARMING
   |
   v
WARMED
   |
   v
PREPARING
   |
   v
CHECKPOINTING
   |
   v
CHECKPOINTED
   |
   v
PACKAGED
   |
   v
RESTORE_VALIDATING
   |
   +---- failure ----> REJECTED
   |
   v
VALIDATED
   |
   v
PUBLISHED
   |
   v
PROMOTED
```

Mỗi transition cần ghi timestamp, attempt id và kết quả. Không chuyển sang `CHECKPOINTED` chỉ vì lệnh trigger đã được gửi; phải có bằng chứng runtime hoàn tất. Không chuyển sang `VALIDATED` nếu chỉ checksum đúng mà chưa restore thử.

Retry phù hợp cho lỗi hạ tầng tạm thời như runner unavailable hoặc storage upload timeout. Nếu warm-up scenario thất bại do application bug, không nên retry vô hạn. Nếu checkpoint operation không rõ trạng thái, trước khi retry cần xác định process/runtime và staging directory của attempt trước.

## 25. Observability của pipeline

Pipeline nên xuất metric và log có cấu trúc cho từng giai đoạn:

- Build duration, test result, image digest và JAR checksum.
- Provision duration, kernel/runtime compatibility result.
- Startup duration và readiness transition.
- Warm-up profile id, scenario count, request count, error rate và latency percentile.
- Callback duration theo Resource và số worker/transaction còn lại.
- Checkpoint duration, result code, image size và disk usage.
- Package/compression duration, upload throughput và checksum result.
- Restore duration, `afterRestore` duration và dependency reconnect time.
- Restore-to-ready duration, smoke test result, error rate và latency.
- Artifact state, retention deadline và deployment reference.

Gắn mọi log với build id, checkpoint attempt id và artifact id. Không dùng secret, request payload hoặc user id làm metric label. Nếu một bước thất bại, log error class/code và component cụ thể để dễ tìm nguyên nhân.

## 26. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| Warm-up job pass nhưng hiệu năng sau restore không cải thiện | Workload không đại diện hoặc chỉ gọi health endpoint | Xây dựng profile từ đường code quan trọng và đo latency sau restore. |
| Checkpoint image không tương thích host đích | JDK/kernel/CPU/CRIU/runtime khác | Pin compatibility profile và restore test trước publish. |
| Ảnh thiếu file hoặc hỏng | Pipeline copy khi checkpoint còn ghi | Chờ completion signal và xác nhận không còn writer. |
| Ứng dụng restore nhưng readiness không đạt | Dependency chưa sẵn sàng, secret cũ hoặc pool/socket stale | Refresh/reconnect trong `afterRestore`, readiness gate và retry deadline. |
| Warm-up tạo dữ liệu thật | Workload gọi API có side effect | Dùng fixture, dry-run, test tenant và sink riêng. |
| Build giống nhau nhưng checkpoint khác | Runtime/base image/dependency không được pin hoặc warm-up không deterministic | Ghi digest, pin toolchain và version warm-up profile. |
| Pipeline retry tạo nhiều artifact rác | Attempt id/path dùng chung hoặc state không rõ | Mỗi attempt dùng thư mục riêng và state machine. |
| Restore test pass nhưng deployment production lỗi | Môi trường validation khác CPU/kernel/mount/secret/network | Dùng compatibility profile sát production và kiểm tra drift. |
| Readiness mở quá sớm | Pipeline chỉ chờ process sống hoặc callback trả về | Chờ dependency health và smoke test trước khi accept traffic. |
| Rollback checkpoint cũ thất bại | Schema, credential hoặc API đã thay đổi | Kiểm tra compatibility và duy trì rollback window có kiểm soát. |

## 27. Checklist thiết kế pipeline

- [ ] Build từ source commit xác định và dependency lockfile.
- [ ] Pin JDK/CRaC, CRIU, base image digest, native dependency và platform profile.
- [ ] Gắn application artifact và checkpoint image bằng manifest.
- [ ] Dùng môi trường checkpoint tương thích với restore target.
- [ ] Dùng warm-up profile có version và workload đại diện.
- [ ] Warm-up không tạo side effect production hoặc nạp dữ liệu nhạy cảm không cần thiết.
- [ ] Có tiêu chí warm-up đo được, không chỉ sleep cố định.
- [ ] Kiểm tra startup readiness trước warm-up và warm-up completion trước prepare.
- [ ] Dừng nhận việc, drain worker/transaction và chuẩn bị Resource trong deadline.
- [ ] Chỉ trigger checkpoint sau khi precondition đạt.
- [ ] Chờ runtime xác nhận checkpoint hoàn tất trước khi copy/nén.
- [ ] Mỗi attempt dùng staging directory riêng.
- [ ] Tạo archive, checksum, manifest và signature nếu cần.
- [ ] Restore thử trong sandbox sạch, tương thích.
- [ ] Kiểm tra `afterRestore`, dependency, readiness và smoke workload.
- [ ] Đo restore-to-ready và performance sau restore.
- [ ] Publish artifact bất biến chỉ sau khi validation đạt.
- [ ] Có canary, rollback và retention policy.
- [ ] Bảo vệ checkpoint vì memory có thể chứa secret và dữ liệu người dùng.
- [ ] Có state machine, retry policy, cleanup và observability cho từng job.

## 28. Kết luận

Pipeline CRaC đáng tin cậy cần liên kết chặt chẽ build, runtime, warm-up, resource preparation, checkpoint, packaging, restore validation và promotion. Build phải tái lập; môi trường warm-up phải tương thích và dùng workload an toàn; checkpoint chỉ được tạo sau khi ứng dụng đạt tiêu chí warm-up và resource đã sẵn sàng; ảnh chỉ được publish sau khi checksum, compatibility và restore smoke test đạt.

Hãy quản lý mỗi attempt bằng định danh riêng, lưu manifest đầy đủ, đo thời gian từ restore tới readiness và triển khai artifact theo canary/rollback. CRaC có thể giảm thời gian khởi động, nhưng lợi ích chỉ đáng tin khi pipeline chứng minh được ảnh có thể restore trong môi trường mục tiêu và ứng dụng sau restore thực sự phục vụ đúng nghiệp vụ.
