# Chọn chính sách tạo lại ảnh theo thay đổi và tuổi của ảnh

Checkpoint image của CRaC (Coordinated Restore at Checkpoint) là snapshot trạng thái của một tiến trình Java tại thời điểm tạo ảnh. Nó có thể lưu application code đã được nạp, heap đã warm-up, trạng thái thread, native memory và các cấu trúc runtime mà checkpoint engine hỗ trợ. Khi ứng dụng được restore, tiến trình tiếp tục từ trạng thái đó và chạy các callback phục hồi tài nguyên.

Vì checkpoint image mang theo trạng thái của một lần chạy cụ thể, đội vận hành cần quyết định khi nào có thể tiếp tục sử dụng image hiện có, khi nào chỉ cần làm mới trạng thái bên ngoài và khi nào phải tạo image mới. Một image có thể vẫn restore được về mặt kỹ thuật nhưng đã cũ so với application release, JDK, thư viện native, cấu hình, schema database hoặc chính sách bảo mật hiện tại.

Chính sách tạo lại ảnh cần trả lời hai câu hỏi riêng:

- **Image còn tương thích để restore không?** Điều này phụ thuộc vào code, JDK/CRaC build, checkpoint engine, kernel, CPU, container runtime và các điều kiện nền tảng.
- **Trạng thái trong image còn phù hợp để phục vụ không?** Điều này phụ thuộc vào cache, cấu hình, credential, session, lease, dữ liệu và trạng thái của dịch vụ bên ngoài.

Tuổi ảnh là một tín hiệu vận hành quan trọng, nhưng không phải bằng chứng duy nhất về tính tương thích. Một image mới tạo hôm qua vẫn có thể không phù hợp nếu JDK hoặc secret đã bị thu hồi. Một image cũ hơn có thể vẫn restore được trên đúng profile nhưng cần làm mới cache hoặc credential trước khi nhận traffic.

Bài này trình bày cách phân loại thay đổi, đặt ngưỡng tuổi ảnh, xác định trigger tạo lại, quản lý phiên bản và rollback, rồi đưa chính sách đó vào CI/CD để không sử dụng image đã lỗi thời hoặc ngoài phạm vi hỗ trợ.

## 1. Tạo lại ảnh là quyết định theo nhiều tín hiệu

Không nên tạo lại checkpoint chỉ dựa vào một mốc thời gian hoặc chỉ dựa vào việc có một deployment mới. Hãy kết hợp các tín hiệu:

- Thay đổi application code hoặc dependency.
- Thay đổi JDK, CRaC runtime hoặc checkpoint engine.
- Thay đổi kernel, CPU architecture/features hoặc container runtime.
- Thay đổi native library, JVM flags hoặc filesystem layout.
- Thay đổi cấu hình và dữ liệu bên ngoài.
- Thay đổi secret, certificate, token hoặc identity policy.
- Tuổi ảnh và thời gian ảnh đã được giữ.
- Lỗi restore, lỗi callback hoặc suy giảm hiệu năng.
- Yêu cầu rollback và thời gian hỗ trợ của release.

Có ba hành động cơ bản:

1. **Reuse:** tiếp tục sử dụng image hiện tại khi compatibility và freshness policy vẫn đạt.
2. **Reconcile:** giữ image nhưng làm mới trạng thái động sau restore, ví dụ lấy secret mới, reconnect database, tải config mới hoặc rebuild cache.
3. **Rebuild:** khởi động ứng dụng từ đúng artifact/runtime hiện tại, warm-up lại và tạo checkpoint image mới.

Đôi khi cần **retire** image: ngừng cho phép restore, thu hồi quyền truy cập và xóa artifact theo retention policy. Rebuild không tự động thay thế bước retire nếu image cũ đã chứa credential hoặc dữ liệu không còn được phép sử dụng.

## 2. Phân biệt tương thích với độ mới của trạng thái

Hai khái niệm này phải được quản lý riêng.

### 2.1 Compatibility

Compatibility trả lời câu hỏi runtime có thể khôi phục tiến trình từ image hay không. Những yếu tố quan trọng gồm:

- JDK vendor, version và exact build.
- CRaC API/runtime build.
- Checkpoint engine và version.
- OS/kernel và các yêu cầu hệ thống.
- CPU architecture và features.
- Native libraries và ABI.
- Container image digest, runtime, namespace và mount.
- JVM flags và runtime configuration.

Nếu một thay đổi nằm ngoài phạm vi được vendor hỗ trợ, không dùng image cũ chỉ vì image vẫn còn trên storage. Cần tạo image mới trên target profile được hỗ trợ hoặc chuyển sang fresh JVM startup.

### 2.2 Freshness

Freshness trả lời câu hỏi trạng thái được lưu trong image còn đủ mới để ứng dụng tiếp tục hoạt động đúng hay không.

Ví dụ:

- Feature flag trong heap đã bị tắt ở configuration service.
- Access token đã hết hạn.
- Secret đã được rotate.
- Session đã bị revoke.
- Cache dữ liệu tham chiếu đã cũ.
- Lease đã được cấp cho instance khác.
- Message broker đã thay đổi partition assignment.
- Database schema đã được nâng cấp.

Những thay đổi này không phải lúc nào cũng yêu cầu tạo checkpoint mới. Thông thường, ứng dụng cần reconnect và reconcile sau restore. Nhưng nếu image chứa state không thể refresh an toàn, hoặc code trong image không tương thích với state mới, image cần bị loại bỏ và tạo lại.

### 2.3 Bảng phân biệt

| Tình huống | Compatibility | Freshness | Hành động thường phù hợp |
|---|---|---|---|
| Chỉ có thêm dữ liệu trong database, schema tương thích | Có thể vẫn đạt | Cache có thể cũ | Reconcile hoặc rebuild cache |
| Access token hết hạn | Process có thể restore | Credential không còn hợp lệ | Lấy token mới sau restore |
| Feature flag đổi | Process có thể restore | Config snapshot cũ | Tải revision mới và validate |
| JAR/application code thay đổi | Image chứa code cũ | Image không đại diện release mới | Rebuild checkpoint |
| JDK/engine thay đổi ngoài compatibility policy | Không được đảm bảo | Có thể không liên quan | Rebuild và test trên runtime mới |
| Kernel/CPU node pool thay đổi | Cần xác minh source-target | Có thể không đổi | Chạy compatibility test; rebuild nếu policy yêu cầu |
| Certificate bị thu hồi | Process có thể restore | Trust/identity state không hợp lệ | Revoke image nếu chứa key cũ; lấy certificate mới |
| Image vượt max age | Chưa chắc mất compatibility | Rủi ro stale state tăng | Reconcile hoặc rebuild theo age policy |
| Checkpoint bị hỏng | Không đạt | Không liên quan | Retire artifact và tạo lại |

Không dùng một status chung như “image cũ” để xử lý tất cả các trường hợp. Ghi rõ image bị chặn vì compatibility, freshness, security, integrity hay policy tuổi ảnh.

## 3. Phân loại thay đổi và hành động tạo lại

Trước khi đặt automation, hãy xây một bảng phân loại thay đổi. Bảng này là policy của hệ thống và cần được đối chiếu với ma trận hỗ trợ của JDK vendor và checkpoint engine.

| Thay đổi | Hành động mặc định | Lý do |
|---|---|---|
| Source code hoặc JAR thay đổi | Rebuild | Image chứa code đã nạp của release cũ |
| Java dependency thay đổi | Rebuild | Class và object graph có thể thuộc dependency cũ |
| JDK vendor/build thay đổi | Rebuild và kiểm thử | Runtime implementation có thể khác |
| CRaC runtime/API thay đổi | Rebuild và kiểm thử | Callback và checkpoint format có thể khác |
| Checkpoint engine thay đổi | Rebuild và kiểm thử | Process image phụ thuộc engine |
| Native library/JNI thay đổi | Rebuild và kiểm thử | Native code, ABI và memory state có thể khác |
| JVM flags ảnh hưởng runtime | Rebuild | Image được tạo với cấu hình runtime khác |
| Container base image thay đổi | Đánh giá; thường rebuild | Userland, JDK hoặc native libraries có thể đổi |
| Kernel patch trong phạm vi hỗ trợ | Kiểm thử target | Có thể chỉ cần xác minh restore trên target mới |
| CPU node pool đổi | Kiểm thử target | Feature baseline hoặc architecture có thể khác |
| Config revision đổi | Reconcile | Tải và validate config hiện tại sau restore |
| Secret/certificate rotate | Reconcile hoặc retire | Lấy credential mới; image chứa secret bị thu hồi phải được retire |
| Database schema đổi | Kiểm tra compatibility | Code trong image phải tương thích schema mới |
| Cache TTL hết hạn | Invalidate/rebuild cache | Cache không còn đủ mới |
| Image vượt max age | Reconcile hoặc rebuild | Giới hạn stale state và rủi ro vận hành |
| Artifact checksum sai | Retire | Không thể tin cậy tính toàn vẹn |

### 3.1 Thay đổi code luôn tạo ra một application generation mới

Checkpoint image không phải một container có thể thay JAR bên dưới rồi tiếp tục sử dụng heap cũ. Heap có thể giữ class, object, singleton, framework context và dữ liệu được tạo bởi binary trước đó.

Khi application JAR hoặc dependency thay đổi, cách an toàn thông thường là:

1. Build JAR mới.
2. Build/pin container image mới nếu runtime hoặc filesystem thay đổi.
3. Khởi động JVM mới.
4. Warm-up ứng dụng mới.
5. Tạo checkpoint mới.
6. Kiểm thử restore trước khi publish.

Không ghép JAR mới vào container filesystem rồi cố restore checkpoint được tạo từ JAR cũ. Process image có thể vẫn chứa class và object của code cũ.

### 3.2 Thay đổi host không phải lúc nào cũng yêu cầu build lại ngay

Một kernel patch hoặc thay đổi node pool có thể nằm trong phạm vi tương thích của vendor. Trong trường hợp đó, có thể giữ checkpoint artifact và chạy restore test trên target mới.

Nhưng chỉ được reuse sau khi policy xác nhận source-target pair nằm trong phạm vi hỗ trợ và test cần thiết đã đạt. Không suy luận rằng cùng Linux hoặc cùng amd64 có nghĩa là tương thích.

### 3.3 Thay đổi bên ngoài thường cần reconcile

Configuration service, secret manager, database và broker có vòng đời riêng. Chúng tiếp tục thay đổi trong khi image được lưu. Sau restore, hãy lấy trạng thái hiện tại từ nguồn có thẩm quyền.

Không tạo checkpoint mới mỗi khi một feature flag đổi nếu image có thể tải config mới an toàn. Ngược lại, nếu code trong image không hiểu schema config mới, phải chặn image cũ và build release tương thích.

## 4. Xây dựng fingerprint cho checkpoint

Mỗi checkpoint cần một manifest ghi lại những yếu tố tạo nên image. Fingerprint giúp pipeline so sánh môi trường tạo ảnh với môi trường dự định restore.

Một manifest có thể chứa:

~~~yaml
checkpoint:
  id: orders-2.8.1-amd64-001
  createdAt: "2026-11-13T07:00:00Z"
  artifactDigest: sha256:example-checkpoint-digest

application:
  name: orders-service
  version: 2.8.1
  sourceCommit: abcdef123
  jarDigest: sha256:example-jar-digest

runtime:
  jdkVendor: example-vendor
  jdkVersion: 21.x
  jdkBuild: example-crac-build
  cracRuntime: example-crac-version
  engine: example-engine
  engineVersion: example-engine-version
  jvmFlagsProfile: production-default

platform:
  os: linux
  architecture: amd64
  kernelProfile: kernel-profile-a
  containerDigest: sha256:example-container-digest
  containerRuntime: example-runtime

compatibility:
  sourceProfile: linux-amd64-jdkA-engineE1
  allowedTargets:
    - prod-amd64-poolA
    - prod-amd64-poolB

freshness:
  configRevisionAtCreate: cfg-1842
  schemaCompatibility:
    minimum: 42
    maximum: 44
  maxAgeHours: 168
~~~

Đây là schema minh họa do pipeline định nghĩa, không phải định dạng bắt buộc của CRaC. Không đưa password, token, private key hoặc secret value vào manifest. Chỉ lưu version ID, digest hoặc reference không nhạy cảm.

### 4.1 So sánh fingerprint có policy

Không nhất thiết mọi trường phải giống tuyệt đối. Hãy chia thành:

- **Must match:** phải trùng chính xác, ví dụ application build, JDK build hoặc engine nếu vendor yêu cầu.
- **Allowed range:** được khác trong phạm vi vendor hỗ trợ, ví dụ một số kernel patch level.
- **Must retest:** thay đổi cần chạy restore test trước khi tiếp tục dùng image.
- **Runtime refresh:** trạng thái được lấy lại sau restore, ví dụ secret, config và service endpoint.
- **Informational:** trường chỉ phục vụ truy vết và không quyết định compatibility.

Không chỉ so sánh một hash tổng rồi báo mismatch. Khi fingerprint khác, pipeline cần nêu trường nào thay đổi và policy áp dụng cho trường đó.

### 4.2 Gắn image với release và target profile

Checkpoint ID cần bất biến và liên kết với:

- Application release.
- JAR digest.
- Container image digest.
- JDK/CRaC build.
- Engine version.
- Source environment profile.
- Target profiles đã kiểm chứng.
- Checkpoint timestamp và checksum.

Không dùng tên tag mutable như latest làm định danh duy nhất. Tag có thể trỏ tới artifact khác sau lần build tiếp theo.

## 5. Đặt chính sách tuổi tối đa cho image

Image age là thời gian từ lúc checkpoint được tạo đến thời điểm được chọn để restore. Có thể tính:

~~~text
imageAge = currentTime - checkpoint.createdAt
~~~

Tuổi ảnh giúp giới hạn khoảng thời gian mà snapshot có thể chứa trạng thái cũ. Tuy nhiên, không có một con số TTL đúng cho mọi ứng dụng. Một image có thể cũ nhưng vẫn tương thích; một image vừa tạo cũng có thể chứa credential đã bị revoke ngay sau đó.

### 5.1 Phân biệt soft age và hard max age

Có thể định nghĩa hai ngưỡng:

- **Soft age:** khi vượt ngưỡng, pipeline lên lịch tạo image mới hoặc tăng mức kiểm tra freshness. Image hiện tại vẫn có thể được dùng nếu reconcile và compatibility đạt.
- **Hard max age:** khi vượt ngưỡng, policy không cho phép restore image đó. Phải tạo image mới hoặc chuyển sang fresh startup.

Ví dụ minh họa:

| Tuổi ảnh | Chính sách |
|---|---|
| 0–24 giờ | Reuse nếu fingerprint và external state hợp lệ |
| 24–72 giờ | Reuse sau freshness validation; lên lịch rebuild |
| 72–168 giờ | Chỉ reuse nếu có exception/policy và đầy đủ reconciliation |
| Trên 168 giờ | Hard expire; tạo lại hoặc fresh startup |

Các khoảng trên chỉ là ví dụ để thiết kế policy. Hãy chọn ngưỡng dựa trên tần suất release, mức độ thay đổi dependency, khả năng refresh state, mục tiêu startup và rủi ro bảo mật.

### 5.2 Chọn TTL theo loại ứng dụng

TTL nên phản ánh mức độ thay đổi và rủi ro:

| Workload | Yếu tố quyết định TTL |
|---|---|
| Stateless API | Tần suất release, runtime patch và cache freshness |
| Service giữ cache lớn | Cache invalidation, data revision và thời gian rebuild |
| Consumer xử lý event | Cursor, partition assignment và replay policy |
| Service giữ credential | Token TTL, secret rotation và identity refresh |
| Batch worker | Workflow deadline và khả năng resume từ durable state |
| Service có native resource | Runtime/engine compatibility và resource lifecycle |
| Workload regulated | Security policy, audit và retention requirement |

Không đặt TTL ngắn chỉ để tạo nhiều image hơn. Nếu phần tốn thời gian là warm-up, hãy đo chi phí rebuild và lợi ích reuse. Ngược lại, không kéo dài TTL chỉ để tiết kiệm CI nếu trạng thái trong image có rủi ro stale hoặc credential.

### 5.3 Tuổi ảnh không thay thế expiry của dữ liệu bên trong

Một image 10 phút tuổi có thể chứa token TTL 5 phút đã hết hạn. Một image 5 ngày tuổi có thể không chứa token và chỉ cần tải config mới.

Vì vậy, cần kiểm tra từng loại thời hạn:

- Token exp và refresh token validity.
- Session idle/absolute timeout.
- Certificate validity/revocation.
- Lease TTL và fencing token.
- Cache TTL và source revision.
- Request/workflow deadline.
- Database schema compatibility.
- Image hard max age.

Không dùng image TTL để thay thế việc kiểm tra credential và state của từng dependency.

## 6. Chọn trigger tạo lại ảnh

Có thể phân loại trigger thành bắt buộc, theo lịch, theo tuổi, theo sự kiện và theo vận hành.

### 6.1 Trigger bắt buộc theo release

Tạo checkpoint mới khi application release hoặc thành phần runtime tạo image thay đổi:

- JAR hoặc source build.
- Dependency graph.
- JDK/CRaC build.
- Checkpoint engine.
- Native library.
- JVM flags ảnh hưởng runtime.
- Container base image hoặc filesystem cần thiết.
- Warm-up procedure hoặc object initialization thay đổi.

Đây là trigger có mức ưu tiên cao vì image cũ chứa code/runtime generation trước đó.

### 6.2 Trigger theo platform change

Khi node pool thay kernel, CPU, container runtime hoặc security profile:

1. Thu thập fingerprint target mới.
2. So sánh với target profile đã kiểm chứng.
3. Nếu thay đổi được vendor hỗ trợ và policy cho phép, chạy restore test.
4. Nếu test đạt, tiếp tục dùng image trong phạm vi đã xác minh.
5. Nếu không hỗ trợ hoặc test thất bại, tạo image mới trên profile phù hợp hoặc dùng fresh startup.

Không nhất thiết tạo lại image chỉ vì host metadata thay đổi. Điều cần thiết là xác minh source-target compatibility. Một số thay đổi chỉ ảnh hưởng target, không ảnh hưởng nội dung image.

### 6.3 Trigger theo freshness event

Các sự kiện như secret rotation, certificate renewal, feature flag update hoặc schema migration thường kích hoạt reconcile. Chỉ tạo lại image nếu:

- Image chứa credential đã bị thu hồi và không thể đảm bảo loại bỏ.
- Code trong image không tương thích trạng thái mới.
- Cache hoặc object graph không thể rebuild sau restore.
- Policy yêu cầu image phải được tạo từ config revision hiện tại.
- External state không thể được reconcile an toàn.

Nếu image có callback refresh đúng cách, không cần rebuild chỉ vì một secret version thay đổi.

### 6.4 Trigger theo tuổi

Scheduler hoặc release pipeline kiểm tra createdAt. Khi image vượt soft age, tạo image mới trong background. Khi vượt hard max age, chặn restore.

Tạo trước image mới giúp tránh đến lúc scale-out mới phát hiện image cũ đã hết hạn. Cần có đủ thời gian để warm-up, checkpoint, restore test và publish trước khi image hiện tại tới hard max age.

### 6.5 Trigger theo lỗi hoặc hiệu năng

Có thể tạo image mới sau khi phát hiện:

- Restore failure lặp lại.
- afterRestore callback thất bại do trạng thái image không còn phù hợp.
- First-request latency hoặc time-to-ready vượt ngưỡng.
- Cache warm-up state không còn hiệu quả.
- Native resource leak hoặc memory usage bất thường.
- Image artifact integrity không đạt.

Không dùng rebuild để che lỗi code hoặc lỗi dependency. Ghi nguyên nhân trước, xác định liệu image cũ là nguyên nhân hay chỉ là nơi biểu hiện lỗi.

## 7. Ma trận quyết định reuse, reconcile hay rebuild

Một decision table giúp pipeline và người vận hành đưa ra hành động nhất quán.

| Điều kiện | Reuse | Reconcile | Rebuild |
|---|---:|---:|---:|
| Application/JAR digest trùng release yêu cầu | Có thể | Có thể | Không cần nếu các điều kiện khác đạt |
| Application/JAR digest khác | Không | Không | Có |
| JDK/engine nằm ngoài compatibility policy | Không | Không đủ | Có |
| Target profile chưa được kiểm chứng | Chưa | Không đủ | Rebuild/test trên target phù hợp hoặc fresh startup |
| Config revision đổi nhưng schema tương thích | Có thể | Có | Chỉ khi policy pin revision |
| Secret rotate và runtime identity có thể lấy lại | Có thể | Có | Không bắt buộc |
| Credential bị revoke nhưng còn trong image | Không cho phép dùng image theo policy bảo mật | Có thể không đủ | Retire image và tạo lại an toàn |
| Cache hết TTL nhưng rebuild được sau restore | Có thể | Có | Không bắt buộc |
| Cache không thể refresh và cần đúng dữ liệu mới | Không | Không đủ | Có |
| Image vượt soft age | Có điều kiện | Có | Lên lịch |
| Image vượt hard max age | Không | Không đủ | Có hoặc fresh startup |
| Checksum không hợp lệ | Không | Không | Retire |
| Database schema không tương thích code trong image | Không | Không đủ | Rebuild application release tương thích |
| Restore test target pass, application checks pass | Có | Theo policy | Không bắt buộc |

Từ “có thể” nghĩa là còn phải đạt các điều kiện còn lại như integrity, compatibility, freshness và security. Không coi một dòng đơn lẻ là quyết định cuối cùng.

### 7.1 Quy tắc ưu tiên

Khi nhiều trigger cùng xuất hiện, áp dụng thứ tự:

1. **Security/integrity block:** image có secret bị thu hồi, artifact không toàn vẹn hoặc bị cấm sử dụng thì retire ngay.
2. **Compatibility block:** code/runtime/target không tương thích thì không restore.
3. **Hard age expiry:** image quá tuổi tối đa thì không restore.
4. **Freshness reconciliation:** làm mới trạng thái động và xác minh dependency.
5. **Performance policy:** nếu image không đạt mục tiêu vận hành, tạo image mới hoặc điều chỉnh warm-up.
6. **Reuse:** chỉ khi mọi điều kiện bắt buộc đều đạt.

Không cho phép một kết quả “restore process thành công” ghi đè một security block hoặc hard age expiry.

## 8. Quy trình tạo image mới mà không làm gián đoạn deployment

Tạo lại image không nhất thiết phải dừng service đang phục vụ. Có thể xây dựng image mới song song và chỉ chuyển deployment sau khi restore test đạt.

~~~mermaid
flowchart TD
    A["Current checkpoint is serving"] --> B["Change or age trigger"]
    B --> C["Build new JAR/container if needed"]
    C --> D["Start isolated checkpoint builder"]
    D --> E["Warm up with approved dependencies"]
    E --> F["Create new checkpoint"]
    F --> G["Restore test on required targets"]
    G --> H{"All required checks pass?"}
    H -->|No| I["Keep current image if still valid<br/>or use fresh startup"]
    H -->|Yes| J["Publish immutable new image"]
    J --> K["Canary restore"]
    K --> L["Promote new image"]
    L --> M["Retire old image after rollback window"]
~~~

### 8.1 Build song song

Trong lúc image mới được tạo:

- Instance hiện tại tiếp tục phục vụ nếu còn hợp lệ.
- CI hoặc checkpoint builder dùng environment riêng.
- Dữ liệu warm-up được kiểm soát.
- Credential có scope và TTL phù hợp.
- Checkpoint artifact mới được tạo với ID mới.
- Restore test chạy trên target profiles bắt buộc.

Không ghi đè checkpoint artifact đang được sử dụng. Tạo version mới và publish bất biến.

### 8.2 Canary restore

Sau khi test CI đạt, có thể restore một số instance canary từ image mới. Theo dõi:

- Restore success rate.
- Callback duration.
- External reconciliation.
- Time-to-ready.
- First-request latency.
- Error rate và resource usage.

Nếu canary không đạt, dừng promotion. Image cũ chỉ được giữ làm fallback nếu vẫn đạt compatibility, security và age policy.

### 8.3 Promote và retire

Khi canary đạt, chuyển traffic hoặc rollout sang image mới. Giữ image cũ trong rollback window đã định nghĩa. Khi hết window:

- Đánh dấu image cũ RETIRED.
- Chặn restore mới.
- Thu hồi quyền đọc nếu cần.
- Xóa artifact theo retention policy.
- Kiểm tra backup/replica và registry cache theo quy trình.

## 9. Quản lý rollback khi image mới có vấn đề

Rollback checkpoint không giống rollback JAR đơn thuần. Image cũ có thể chứa code, config snapshot, token hoặc schema assumption cũ.

Trước khi giữ một image cho rollback, cần xác minh:

- Image còn trong compatibility window.
- JDK/engine/target profile vẫn được hỗ trợ.
- Schema database hiện tại vẫn tương thích với code cũ.
- External API và config mới không phá vỡ code cũ.
- Credential được lấy mới sau restore.
- Image chưa bị retire hoặc security-revoked.
- Image chưa vượt hard max age.

### 9.1 Expand/contract giúp giữ rollback window

Nếu schema database được thay đổi theo expand/contract, code cũ và mới có thể cùng hoạt động trong một khoảng thời gian. Điều này cho phép rollback application release mà không cần rollback database ngay lập tức.

Tuy nhiên, sau bước contract xóa cột hoặc thay đổi semantics, image cũ có thể không còn tương thích. Khi đó, phải retire checkpoint cũ trước hoặc đồng thời với contract migration.

### 9.2 Không rollback về image đã bị thu hồi vì lý do bảo mật

Nếu image cũ bị retire do chứa credential bị compromise, không khôi phục nó chỉ vì image mới có lỗi. Dùng fresh startup từ artifact an toàn hoặc tạo checkpoint mới. Security revocation có mức ưu tiên cao hơn rollback convenience.

### 9.3 Giới hạn thời gian rollback

Rollback window cần ngắn hơn hoặc bằng khoảng thời gian mà:

- Schema còn tương thích.
- Runtime profile còn được hỗ trợ.
- Credential có thể được cấp lại.
- Image chưa hết hard max age.
- Release còn được phép vận hành.

Lưu ngày hết hạn rollback trong manifest hoặc deployment metadata để pipeline không chọn image cũ vô thời hạn.

## 10. Phân biệt rebuild image với refresh external state

Một lỗi vận hành thường gặp là tạo lại checkpoint mỗi khi có thay đổi bên ngoài, dù ứng dụng có thể refresh sau restore. Điều đó làm tăng chi phí build và tạo thêm artifact mà không cải thiện compatibility.

### 10.1 Những gì thường refresh được

Sau restore, ứng dụng thường có thể:

- Lấy secret version hiện tại.
- Refresh access token.
- Reconnect database và kiểm tra schema.
- Resolve service discovery/DNS.
- Tải feature flags và config revision mới.
- Rebuild cache.
- Rejoin message consumer group.
- Reacquire lease và fencing token.
- Revalidate session hoặc identity.

Các thao tác này nên được đặt trong Resource callback hoặc lifecycle stage phù hợp. Readiness chỉ bật sau khi dependency bắt buộc được xác minh.

### 10.2 Những gì thường cần image mới

- Application code đã thay đổi.
- Class hoặc dependency trong heap không còn tương ứng release.
- JDK/engine build thay đổi ngoài phạm vi compatibility.
- Native library hoặc ABI thay đổi.
- JVM flags làm thay đổi runtime assumptions.
- Image được tạo từ environment sai hoặc chứa trạng thái không thể loại bỏ an toàn.
- Checkpoint artifact hỏng hoặc checksum sai.
- Policy yêu cầu image được tạo sau một security patch cụ thể.

### 10.3 Khi không thể xác minh external state

Nếu secret manager hoặc config service không sẵn sàng, đừng tự coi snapshot trong heap là hiện hành.

Có thể giữ instance ở RECONCILING và retry có giới hạn. Nếu policy cho phép degraded mode, chỉ bật những chức năng không phụ thuộc state chưa xác minh. Nếu dependency bảo mật hoặc dữ liệu bắt buộc không thể kiểm tra, giữ readiness false.

## 11. Chính sách theo môi trường

Không nhất thiết staging và production dùng cùng một TTL hoặc cùng checkpoint artifact.

| Environment | Mục tiêu | Chính sách gợi ý |
|---|---|---|
| Local development | Thử callback và học API | Image tạm, TTL ngắn, dữ liệu giả |
| CI | Kiểm tra regression | Tạo theo commit hoặc build, xóa sau retention ngắn |
| Staging | Kiểm tra gần production | Tạo theo release candidate, test target profiles và external reconciliation |
| Production | Scale/rollout nhanh | Tạo theo release/runtime profile, hard max age, canary và rollback window |
| Disaster recovery | Khả năng phục hồi vùng khác | Image riêng hoặc target pair đã được kiểm chứng, kiểm tra định kỳ |
| Long-running batch | Resume workflow | Ưu tiên durable state và deadline; checkpoint age theo workflow semantics |

Production checkpoint thường nên được tạo từ một release candidate đã qua test, với cấu hình không chứa credential dài hạn. Sau restore, lấy runtime identity và secret theo môi trường đích.

Không promote nguyên trạng checkpoint staging sang production nếu heap chứa endpoint, tenant, identity hoặc cache riêng của staging. Nếu thiết kế cho phép cùng image chạy nhiều environment, phải có bước reconcile và kiểm thử rõ ràng.

## 12. Ví dụ policy dạng YAML

Một policy có thể mô tả trigger, tuổi ảnh và hành động:

~~~yaml
checkpointPolicyVersion: 1

image:
  maxAge:
    softHours: 72
    hardHours: 168
  immutable: true

rebuildOn:
  applicationDigestChange: true
  dependencyDigestChange: true
  jdkBuildChange: true
  cracRuntimeChange: true
  checkpointEngineChange: true
  nativeLibraryChange: true
  jvmRuntimeProfileChange: true
  containerDigestChange: true

retestOn:
  kernelProfileChange: true
  cpuFeatureProfileChange: true
  containerRuntimeChange: true
  targetNodePoolChange: true

reconcileAfterRestore:
  configuration: true
  secrets: true
  certificates: true
  databaseConnections: true
  schemaCompatibility: true
  serviceDiscovery: true
  cacheRevision: true
  messageAssignments: true
  leases: true

security:
  rejectRevokedArtifact: true
  requireArtifactChecksum: true
  requireApprovedProvenance: true
  requireRuntimeIdentityAfterRestore: true

release:
  requiredTargetProfiles:
    - production-amd64-a
    - production-amd64-b
  requireRestoreTest: true
  requireApplicationReadiness: true
  canaryBeforePromotion: true
  rollbackWindowHours: 48
~~~

Đây là cấu trúc minh họa do hệ thống deployment định nghĩa, không phải file cấu hình chuẩn của CRaC. Các giá trị giờ và profile phải được thay bằng policy thực tế.

### 12.1 Validate policy trước khi dùng

Pipeline nên kiểm tra:

- softHours nhỏ hơn hardHours.
- Mọi required target profile đều tồn tại.
- Mỗi trigger có hành động tương ứng.
- Image ID và digest là bất biến.
- Không có secret trong manifest.
- Rollback window không vượt image hard max age.
- Image bị revoked không thể được chọn dù còn trong storage.
- External reconciliation được bật cho dependency bắt buộc.

Nếu policy thiếu hoặc không hợp lệ, fail closed cho checkpoint deployment và dùng fresh startup theo fallback policy nếu được phép.

## 13. Ví dụ logic chọn image

Có thể triển khai một decision service đơn giản dựa trên metadata và policy. Ví dụ dưới đây minh họa thứ tự quyết định, không phải implementation đầy đủ của một engine.

~~~java
import java.time.Duration;
import java.time.Instant;

enum ImageAction {
    REUSE,
    RECONCILE,
    REBUILD,
    RETIRE
}

record ImageMetadata(
        String applicationDigest,
        String runtimeFingerprint,
        Instant createdAt,
        String artifactDigest,
        boolean revoked) {
}

record TargetState(
        String applicationDigest,
        String runtimeFingerprint,
        Instant now,
        Duration hardMaxAge,
        boolean targetVerified,
        boolean externalStateCanBeReconciled) {
}

final class CheckpointPolicy {

    ImageAction decide(
            ImageMetadata image,
            TargetState target) {

        if (image.revoked()) {
            return ImageAction.RETIRE;
        }

        if (image.artifactDigest() == null
                || image.artifactDigest().isBlank()) {
            return ImageAction.RETIRE;
        }

        if (!image.applicationDigest()
                .equals(target.applicationDigest())) {
            return ImageAction.REBUILD;
        }

        if (!target.targetVerified()) {
            return ImageAction.REBUILD;
        }

        Duration age = Duration.between(
                image.createdAt(),
                target.now());

        if (age.isNegative() || age.compareTo(
                target.hardMaxAge()) > 0) {
            return ImageAction.REBUILD;
        }

        if (!image.runtimeFingerprint()
                .equals(target.runtimeFingerprint())) {
            return ImageAction.REBUILD;
        }

        if (target.externalStateCanBeReconciled()) {
            return ImageAction.RECONCILE;
        }

        return ImageAction.REUSE;
    }
}
~~~

Ví dụ này dùng fingerprint equality như một policy nghiêm ngặt. Hệ thống thực tế thường cần compatibility evaluator có thể xử lý allowed ranges, vendor support và retest evidence. Cũng cần xác minh checksum thật, image status, target profile và các dependency bắt buộc trước khi quyết định.

Không nên coi RECONCILE là trạng thái cuối cùng cho phép nhận traffic. Đó là hành động cần thực hiện. Chỉ sau khi reconciliation thành công, readiness mới được bật.

## 14. Đưa age policy vào scheduler và CI/CD

Một image sắp hết hạn không nên chỉ được phát hiện khi instance mới cần scale. Hãy theo dõi tuổi ảnh định kỳ và tạo trước image thay thế.

### 14.1 Scheduled refresh

Một job định kỳ có thể:

1. Liệt kê checkpoint đang active.
2. Đọc createdAt và hard max age.
3. So sánh application/runtime fingerprint với release hiện tại.
4. Kiểm tra target profiles còn được hỗ trợ.
5. Tạo image mới khi image hiện tại tới soft age.
6. Chạy restore matrix.
7. Publish image mới nếu đạt.
8. Đánh dấu image cũ retiring theo rollback window.

Scheduler nên có lock hoặc idempotency key để không tạo nhiều image giống nhau khi nhiều pipeline cùng chạy.

### 14.2 Event-driven rebuild

Có thể kích hoạt rebuild khi:

- Application release được publish.
- JDK/engine base image được cập nhật.
- Native dependency được nâng cấp.
- Security patch yêu cầu tạo lại runtime image.
- Checkpoint artifact bị thu hồi.
- Restore test phát hiện incompatibility.
- Target node pool mới được thêm vào.

Không kích hoạt rebuild cho mọi config event nếu config có thể được refresh sau restore. Hãy dùng event classification để chọn đúng hành động.

### 14.3 CI release gate

Trước khi publish checkpoint mới, pipeline cần:

- Xác minh JAR/container digest.
- Thu thập source fingerprint.
- Tạo checkpoint từ runtime được pin.
- Kiểm tra artifact checksum.
- Restore trên target profiles bắt buộc.
- Chạy callback và application smoke tests.
- Kiểm tra time-to-ready và performance threshold.
- Ghi manifest và evidence.
- Chỉ publish khi required pairs đạt.

Image mới không được xem là thay thế image cũ cho tới khi tất cả bước bắt buộc hoàn tất.

## 15. Quan sát tuổi ảnh và vòng đời image

Cần có metric và log để đội vận hành biết image nào đang được dùng và vì sao image mới được tạo.

Metric hữu ích:

- Tuổi của checkpoint đang active.
- Thời gian còn lại tới soft age và hard max age.
- Số image theo trạng thái ACTIVE, CANDIDATE, RETIRED, REVOKED.
- Số lần restore theo checkpoint ID.
- Restore success/failure rate.
- Reconciliation success/failure rate.
- Time-to-ready.
- Số lần rebuild theo từng trigger.
- Tỷ lệ image bị loại vì compatibility.
- Số image vượt hard age.
- Storage usage và số artifact hết hạn chưa xóa.

Log sự kiện nên ghi:

~~~json
{
  "event": "checkpoint_rebuild_decision",
  "currentCheckpointId": "orders-2.8.1-amd64-001",
  "action": "REBUILD",
  "reason": "SOFT_AGE_EXCEEDED",
  "ageHours": 74,
  "softAgeHours": 72,
  "targetProfile": "production-amd64-a"
}
~~~

Ví dụ này không chứa secret. Có thể thêm release ID, fingerprint delta và pipeline run ID để truy vết.

### 15.1 Đo time-to-ready thay vì chỉ restore duration

Một image có thể restore nhanh nhưng mất nhiều thời gian tải secret, reconnect database hoặc rebuild cache.

Đo các mốc:

~~~text
T0: restore command started
T1: process restored
T2: afterRestore callbacks completed
T3: external state reconciled
T4: readiness true
~~~

- Restore duration = T1 - T0.
- Callback duration = T2 - T1.
- Reconciliation duration = T3 - T2.
- Time-to-ready = T4 - T0.

Nếu rebuild image mới làm giảm warm-up nhưng không cải thiện time-to-ready, cần xem lại dependency recovery thay vì chỉ tăng tần suất checkpoint.

## 16. Quản lý retention và trạng thái image

Mỗi checkpoint nên có lifecycle state rõ ràng:

| State | Ý nghĩa | Có được restore? |
|---|---|---|
| CANDIDATE | Vừa tạo, đang kiểm thử | Không |
| ACTIVE | Được phê duyệt cho target profiles | Có, nếu còn hạn |
| DEPRECATED | Có image mới thay thế, đang trong rollback window | Chỉ theo rollback policy |
| RETIRED | Đã hết thời gian sử dụng | Không |
| REVOKED | Bị thu hồi vì security/integrity/policy | Không |
| EXPIRED | Vượt hard max age | Không |

Chuyển state cần được ghi nhận và audit. Không để một image DEPRECATED được chọn mặc định cho scale-out chỉ vì nó vẫn có trong registry.

### 16.1 Retention không chỉ là xóa file

Khi retire image, kiểm tra:

- Artifact store chính.
- Registry hoặc object storage replica.
- CI artifacts.
- Cache trên node.
- Backup.
- Bản copy được tải về local workspace.
- Manifest và deployment reference.

Nếu image bị revoke do credential compromise, cần xử lý cả credential và mọi bản sao theo incident policy. Xóa file không thu hồi credential đã lộ.

### 16.2 Giữ đủ image để rollback, nhưng không giữ vô hạn

Retention nên cân bằng:

- Rollback window.
- Image hard max age.
- Database schema compatibility.
- Runtime support window.
- Security retention.
- Storage cost.
- Thời gian cần điều tra incident.

Một image cũ không còn tương thích không có giá trị rollback chỉ vì nó vẫn được lưu. Hãy tự động đánh dấu RETIRED khi điều kiện rollback không còn đạt.

## 17. Kiểm thử chính sách tạo lại ảnh

Policy cần được kiểm thử như code. Có thể tạo test cho decision table mà không cần khởi chạy JVM hoặc checkpoint engine thật.

Các trường hợp cần có:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Cùng application/runtime fingerprint, image còn hạn | REUSE hoặc RECONCILE |
| Application digest thay đổi | REBUILD |
| JDK/engine thay đổi ngoài policy | REBUILD |
| Target profile chưa verified | Chặn reuse, yêu cầu test/rebuild |
| Soft age vượt ngưỡng | Lên lịch rebuild |
| Hard age vượt ngưỡng | Không restore |
| Secret rotate nhưng lấy lại được sau restore | RECONCILE |
| Credential bị revoke và image bị cấm | RETIRE |
| Checksum không hợp lệ | RETIRE |
| Cache stale nhưng rebuild được | RECONCILE |
| Schema không tương thích code | REBUILD application release hoặc chặn |
| Image cũ còn trong rollback window và vẫn tương thích | Cho phép rollback theo policy |
| Image cũ bị security-revoked | Không cho rollback |

Ngoài unit test cho policy, cần integration test xác nhận:

- Image mới được tạo khi trigger đúng.
- Không tạo image trùng khi nhiều scheduler chạy.
- Artifact cũ không bị ghi đè.
- Restore job chọn đúng image ID.
- Image hết hạn hoặc revoked bị từ chối.
- Reconciliation lỗi giữ readiness false.
- Rollback chỉ chọn image còn hợp lệ.
- Retention job không xóa image đang active hoặc còn trong rollback window.

## 18. Những sai lầm thường gặp

### Tạo lại image theo lịch nhưng không xét thay đổi

Một cron job mỗi ngày không phát hiện được một secret bị revoke ngay sau khi image được tạo. Cần event-driven revocation và runtime validation.

### Dùng tuổi ảnh làm bằng chứng tương thích

Image mới vẫn có thể không tương thích với target kernel hoặc CPU. Compatibility cần fingerprint và test.

### Rebuild mỗi khi config thay đổi

Config động thường có thể refresh sau restore. Rebuild liên tục làm tăng chi phí và không giải quyết được state ownership.

### Giữ image cũ làm rollback vô thời hạn

Schema, runtime và security policy có thể khiến image cũ không còn dùng được. Rollback window cần giới hạn và được kiểm tra.

### Ghi đè checkpoint artifact đang active

Điều này làm mất khả năng truy vết và có thể khiến instance mới nhận bytes khác với image đã được test. Dùng immutable checkpoint ID.

### Chỉ kiểm tra process restore

Process sống không đồng nghĩa application ready. Kiểm tra callback, external reconciliation và functional path.

### Cho phép restore image bị revoked

Một image có thể còn checksum đúng nhưng credential bên trong đã bị thu hồi. Security status phải được kiểm tra riêng.

### Rebuild để che lỗi application

Nếu callback hoặc dependency liên tục lỗi, tạo image mới có thể chỉ che triệu chứng. Thu thập nguyên nhân và phân loại lỗi trước khi quyết định rebuild.

### Không tính thời gian kiểm thử vào age policy

Image candidate có thể mất nhiều giờ để chạy restore matrix. Khi publish, tuổi ảnh đã khác thời điểm tạo. Dùng createdAt thực tế và kiểm tra lại hard age trước khi deploy.

## 19. Quy trình vận hành đề xuất

Một quy trình thực tế để chọn reuse, reconcile hoặc rebuild có thể gồm:

**Bước 1 — Đọc manifest.** Lấy checkpoint ID, createdAt, application digest, JDK/engine, container digest và source profile.

**Bước 2 — Kiểm tra integrity và security state.** Xác minh checksum, provenance, trạng thái REVOKED và quyền truy cập artifact.

**Bước 3 — So sánh application/runtime fingerprint.** Nếu code, dependency, JDK hoặc engine thay đổi ngoài policy, yêu cầu rebuild.

**Bước 4 — Xác minh target profile.** Đối chiếu kernel, CPU, container runtime và target profile với ma trận đã kiểm chứng.

**Bước 5 — Tính image age.** Áp dụng soft age và hard max age. Không restore image vượt hard limit.

**Bước 6 — Phân loại external changes.** Xác định config, secret, schema, cache, session, lease và broker state có thể reconcile hay buộc retire/rebuild.

**Bước 7 — Chọn hành động.** Reuse, reconcile, rebuild hoặc retire theo thứ tự ưu tiên security, compatibility, hard age và freshness.

**Bước 8 — Tạo image candidate khi cần.** Build từ JAR/container/runtime đã pin, warm-up bằng dữ liệu phù hợp và tạo artifact ID mới.

**Bước 9 — Kiểm thử restore.** Chạy source-target matrix, callback, external reconciliation, functional smoke và performance checks.

**Bước 10 — Promote có kiểm soát.** Publish immutable artifact, canary restore và chuyển sang ACTIVE sau khi đạt.

**Bước 11 — Giữ rollback window.** Chỉ giữ image cũ nếu còn tương thích, chưa revoked và chưa hard-expired.

**Bước 12 — Retire và dọn dẹp.** Chặn restore mới, thu hồi quyền và xóa artifact theo retention policy.

## 20. Tiêu chí hoàn tất một lần tạo lại ảnh

Một image mới chỉ nên được xem là ACTIVE khi:

- Được tạo từ đúng application release và runtime profile.
- Manifest ghi đầy đủ JAR/container digest, JDK/engine và source profile.
- Checkpoint artifact có checksum hợp lệ.
- Target profiles bắt buộc nằm trong phạm vi hỗ trợ.
- Restore test thực tế đạt.
- Resource callback hoàn tất.
- External state được reconcile.
- Functional smoke test đạt.
- Time-to-ready và resource usage nằm trong ngưỡng.
- Security scan, provenance và access policy đạt.
- Rollback/retention metadata được thiết lập.

Một image vừa tạo nhưng chưa qua restore test vẫn là CANDIDATE. Không để scheduler hoặc deployment tự chọn nó chỉ vì createdAt mới hơn.

## Tài liệu tham khảo

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): mô hình checkpoint/restore và trạng thái tiến trình.
- [CRaC — Running an Application With CRaC](https://docs.azul.com/crac/usage/running-crac): chuẩn bị runtime và chạy ứng dụng CRaC.
- [CRaC — CRaC Engines](https://docs.azul.com/crac/usage/crac-engines): engine và phạm vi tương thích theo bản dựng.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): quản lý Resource callback trước checkpoint và sau restore.
- [CRaC — Debugging](https://crac.org/reference/debugging/): điều tra lỗi checkpoint/restore.
- [OCI Image Format Specification](https://github.com/opencontainers/image-spec): digest và metadata bất biến của container image.
- [Kubernetes — Container Images](https://kubernetes.io/docs/concepts/containers/images/): quản lý image, tag và digest trong deployment.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): vòng đời secret, rotation và thu hồi.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): validator và conditional request khi quản lý revision.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ token và refresh token.

