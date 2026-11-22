# Tính tổng chi phí dựng, lưu, phân phối và sử dụng ảnh

Checkpoint CRaC có thể rút ngắn thời gian khởi động ứng dụng Java bằng cách lưu trạng thái một tiến trình đã được khởi tạo và warm-up, sau đó restore trạng thái đó khi cần tạo instance mới. Nhưng checkpoint không miễn phí. Pipeline phải trả chi phí để chạy môi trường chuẩn bị, warm-up, tạo ảnh, kiểm thử, lưu trữ và phân phối artifact. Mỗi instance còn cần thời gian và tài nguyên để restore, tạo lại connection, listener, client và các dependency phụ thuộc môi trường.

Muốn đánh giá CRaC có hiệu quả về kinh tế hay không, không nên chỉ so sánh thời gian restore với thời gian cold start. Cần tính toàn bộ vòng đời của ảnh: **dựng ảnh, lưu ảnh, phân phối ảnh, sử dụng ảnh và vận hành vòng đời ảnh**. Sau đó phân bổ chi phí theo số release, số instance restore, thời gian retention, vùng triển khai và tần suất scale.

Một checkpoint giúp giảm startup latency nhưng có thể làm tăng chi phí build, storage, network transfer hoặc memory footprint. Với workload ít instance, phần chi phí cố định có thể lớn hơn phần tiết kiệm. Với workload scale-out thường xuyên, cùng một checkpoint có thể được dùng cho nhiều instance và chi phí chuẩn bị được phân bổ trên số lần restore lớn hơn.

## 1. Xác định ranh giới chi phí

Trước khi tính toán, cần xác định đang đo loại artifact nào. Trong quy trình CRaC, có thể có application/container image và checkpoint artifact. Application image chứa JDK, application JAR, native library và filesystem cần thiết; checkpoint chứa trạng thái process tại thời điểm tạo ảnh. Tùy kiến trúc, checkpoint có thể nằm trong container image hoặc được phân phối riêng.

Để so sánh công bằng, hãy tách:

- **Chi phí chung:** build application JAR, tạo application image và pull application image nếu cả cold start lẫn CRaC đều cần.
- **Chi phí tăng thêm do CRaC:** chạy prepare/warm-up, tạo checkpoint, lưu checkpoint, phân phối checkpoint, kiểm tra tương thích, restore và tái tạo resource.
- **Chi phí tiết kiệm nhờ CRaC:** phần CPU/thời gian khởi tạo được giảm, năng lực phục vụ đến sớm hơn, hoặc phần capacity phải dự phòng để đáp ứng startup SLO được giảm.
- **Chi phí vận hành:** quản lý nhiều checkpoint generation, kiểm thử host compatibility, bảo mật artifact, rollback và cold-start fallback.

Không cộng chi phí chung vào một phía của phép so sánh. Nếu cả hai phương án đều phải build và pull application image, hãy loại phần đó khỏi phần chi phí tăng thêm khi tính break-even của checkpoint.

## 2. Năm nhóm chi phí chính

| Nhóm | Nội dung | Đơn vị thường dùng |
|---|---|---|
| Dựng ảnh | Prepare runner, warm-up, CPU/RAM, checkpoint, validation và retry | vCPU-hour, GB-RAM-hour, runner-minute, chi phí dịch vụ test |
| Lưu ảnh | Dung lượng checkpoint, số version, bản sao, backup, retention và request lưu trữ | GB-month, object request, chi phí backup |
| Phân phối ảnh | Download, registry/object-store egress, cross-region transfer, cache miss, giải nén và checksum | GB transfer, network egress, CPU-second, startup delay |
| Sử dụng ảnh | Restore CPU/RAM, tạo lại dependency, health check và memory footprint sau restore | vCPU-second, GB-RAM-hour, giây tới readiness |
| Vận hành ảnh | Pipeline, compatibility test, monitoring, security scan, rollback và fallback | Engineer-hour, CI-minute, chi phí sự cố |

Ngoài năm nhóm trên, có thể có chi phí gián tiếp như thời gian đội nền tảng xử lý checkpoint lỗi, capacity dự phòng trong rollout hoặc ảnh hưởng tới SLO khi artifact không restore được. Ghi nhận các khoản này riêng để mô hình không che khuất nguyên nhân.

## 3. Mô hình tổng chi phí theo release

Với một release (r), có thể mô hình hóa tổng chi phí trong một kỳ đánh giá như sau:

\[
C_{r} = B_{r} + S_{r} + D_{r} + R_{r} + U_{r} + O_{r}
\]

Trong đó:

- (B_r): chi phí dựng và kiểm chứng checkpoint.
- (S_r): chi phí lưu trữ checkpoint trong thời gian retention.
- (D_r): chi phí phân phối checkpoint tới node/instance.
- (R_r): chi phí CPU/RAM và dependency recreation trong lúc restore.
- (U_r): chi phí runtime tăng thêm do trạng thái đã restore, ví dụ memory footprint hoặc GC overhead khác baseline.
- (O_r): chi phí vận hành, bảo mật, kiểm thử tương thích và quản lý release.

Nếu có nhiều release trong kỳ, tổng chi phí là:

\[
C_{CRaC} = \sum_{r=1}^{M} C_r + C_{fallback}
\]

`C_fallback` là chi phí phát sinh khi checkpoint không dùng được và deployment phải cold start, retry hoặc rollback. Có thể bổ sung chi phí incident nếu cần đánh giá TCO đầy đủ.

Đây là mô hình kế toán, không phải công thức cố định của CRaC. Từng tổ chức có thể gộp hoặc tách các khoản theo cách tính cloud bill và cost allocation đang sử dụng. Điều quan trọng là cùng một khoản không bị tính hai lần.

## 4. Tính chi phí dựng ảnh

Chi phí dựng ảnh thường phát sinh một lần cho mỗi checkpoint generation, nhưng có thể lặp lại nhiều lần nếu prepare/checkpoint thất bại hoặc phải tạo lại vì thay đổi JDK, dependency, OS image hay cấu hình warm-up.

Các khoản cần ghi nhận:

- Thời gian chạy prepare container/VM hoặc runner chuyên dụng.
- CPU và RAM trong lúc khởi động ứng dụng.
- Thời gian warm-up và số request/fixture được thực thi.
- Chi phí database, broker, stub service hoặc sandbox được dùng trong warm-up.
- Thời gian tạo checkpoint và tài nguyên native engine.
- Chi phí checksum, đóng gói, upload, scan và restore smoke test.
- Chi phí các attempt thất bại, bao gồm runner-minute và dependency test đã tiêu thụ.

Một công thức đơn giản:

\[
B_r = T_{cpu}P_{cpu} + T_{ram}P_{ram} + C_{warmup} + C_{checkpoint} + C_{verify} + C_{retry}
\]

Trong đó (T_{cpu}) là vCPU-hour, (P_{cpu}) là giá mỗi vCPU-hour; (T_{ram}) là GB-RAM-hour, (P_{ram}) là giá mỗi GB-RAM-hour. Các khoản còn lại là chi phí dịch vụ hoặc pipeline được đo trực tiếp.

### Ví dụ đo chi phí prepare

Giả sử một runner 8 vCPU và 16 GB RAM chạy trong 12 phút để khởi động, warm-up và tạo checkpoint. Thời gian kiểm chứng restore chạy thêm 5 phút trên cùng cấu hình.

| Công đoạn | Thời gian | CPU allocation | RAM allocation |
|---|---:|---:|---:|
| Khởi động và warm-up | 8 phút | 8 vCPU | 16 GB |
| Tạo checkpoint | 4 phút | 8 vCPU | 16 GB |
| Restore smoke test | 5 phút | 8 vCPU | 16 GB |

Tổng CPU allocation là (8 \times 17/60 = 2.27) vCPU-hour; RAM allocation là (16 \times 17/60 = 4.53) GB-RAM-hour. Đây là cách tính theo allocation của runner. Nếu nhà cung cấp tính theo node-minute hoặc VM-hour tối thiểu, hãy dùng đơn giá thực tế thay vì tự quy đổi tuyến tính.

Nếu warm-up gọi database thử nghiệm hoặc sandbox có tính phí, cộng các khoản đó vào (C_{warmup}). Nếu checkpoint phải tạo lại ba lần mới thành công, tính cả ba attempt, không chỉ attempt cuối cùng.

### Tần suất tạo lại ảnh ảnh hưởng lớn tới chi phí

Một checkpoint có thể được dùng cho nhiều instance, nhưng thường phải tạo generation mới khi:

- Application binary hoặc dependency thay đổi.
- JDK, base image, native library hoặc checkpoint engine được cập nhật.
- Cấu hình warm-up thay đổi đáng kể.
- Security patch yêu cầu loại bỏ checkpoint cũ.
- Checkpoint hết hạn theo chính sách vận hành.

Nếu mỗi tháng có nhiều release nhỏ, chi phí build/checkpoint có thể tăng dù số instance restore không đổi. Do đó, cần theo dõi số generation được tạo và số generation thực sự được triển khai.

## 5. Tính chi phí lưu trữ ảnh

Checkpoint thường chứa heap và native state của process, nên kích thước có thể đáng kể. Dung lượng phụ thuộc vào heap đang dùng, object được giữ, cache warm-up, native memory, thread và định dạng image của engine. Không nên lấy `-Xmx` làm kích thước checkpoint dự kiến; hãy đo artifact thực tế.

Chi phí lưu trữ trong một kỳ có thể tính:

\[
S_r = G_r \times P_{GB-month} \times H_r \times K_r + C_{requests} + C_{backup}
\]

Trong đó:

- (G_r): dung lượng checkpoint tính bằng GB.
- (P_{GB-month}): giá lưu một GB trong một tháng.
- (H_r): thời gian lưu quy đổi theo tháng.
- (K_r): số bản sao lưu trữ tương đương, gồm replication hoặc backup nếu có tính phí.
- (C_{requests}): chi phí PUT/GET/LIST hoặc request storage khác.
- (C_{backup}): chi phí snapshot/backup riêng nếu chưa nằm trong (K_r).

Nếu giá storage có nhiều tier, tính từng khoảng retention theo tier tương ứng. Nếu checkpoint nằm trong container registry, xem registry có tính phí theo dung lượng blob, replication, request hoặc data transfer hay không.

### Số version được giữ lại

Giả sử mỗi release tạo checkpoint 6 GB, mỗi tuần phát hành một release và giữ 8 release. Nếu mỗi version được lưu độc lập, dung lượng logical là 48 GB trước khi tính replication/backup. Nếu registry deduplicate được layer hoặc object chunk, dung lượng billable có thể thấp hơn; không giả định deduplication nếu chưa có số liệu billing.

Retention policy ảnh hưởng trực tiếp tới chi phí:

- Giữ nhiều version giúp rollback nhanh nhưng tăng storage.
- Giữ một release đang chạy và một release trước đó có thể đủ cho nhiều hệ thống.
- Môi trường DR hoặc nhiều region có thể cần thêm bản sao.
- Artifact bị revoke vì security patch có thể phải cách ly trong một khoảng thời gian kiểm toán trước khi xóa.

Không xóa checkpoint đang được deployment hoặc rollback plan tham chiếu. Hãy có release catalog ghi rõ version nào active, rollback-eligible, revoked hoặc expired.

## 6. Nén ảnh và trade-off CPU với dung lượng

Nén checkpoint có thể giảm chi phí lưu trữ và truyền tải, nhưng làm tăng CPU và thời gian giải nén. Hiệu quả phụ thuộc dữ liệu trong heap và định dạng image. Heap có nhiều object/string lặp có thể nén tốt; dữ liệu đã nén, encrypted hoặc native memory entropy cao có thể nén ít.

So sánh ít nhất ba đại lượng:

1. Kích thước ảnh chưa nén (G_{raw}).
2. Kích thước sau nén (G_{compressed}).
3. Thời gian và CPU để nén/giải nén trên runner và node restore.

Tỷ lệ nén:

\[
CompressionRatio = \frac{G_{compressed}}{G_{raw}}
\]

Tỷ lệ càng thấp thì artifact càng nhỏ. Nhưng không nên tối ưu tỷ lệ nén riêng lẻ. Nếu giải nén làm tăng time-to-ready hoặc tiêu thụ CPU đáng kể trong lúc scale-out, tổng chi phí có thể cao hơn.

Đo thời gian nén trong pipeline create và giải nén trong deployment. Cũng kiểm tra CPU contention khi nhiều replica đồng thời tải và giải nén checkpoint. Với node có cache cục bộ, có thể giải nén một lần cho nhiều container nếu kiến trúc và quyền truy cập cho phép.

## 7. Tính chi phí phân phối ảnh

Sau khi checkpoint được tạo, artifact cần đến node/host sẽ restore. Chi phí phân phối phụ thuộc:

- Số instance cần tải checkpoint.
- Kích thước artifact sau nén.
- Node có cache artifact hay không.
- Kho lưu trữ và registry nằm cùng region hay khác region.
- Data egress, inter-region transfer hoặc CDN/object-store request.
- Số lần retry do download lỗi.
- CPU và thời gian xác minh checksum/giải nén.
- Mức độ đồng thời khi scale-out.

Một mô hình đơn giản:

\[
D_r = N_r \times G_{transfer} \times P_{GB-transfer} + C_{download-requests} + C_{unpack}
\]

Trong đó (N_r) là số lần tải thực tế, không nhất thiết bằng số container. Nếu mỗi node tải một lần rồi cache dùng chung cho 10 container, số lần tải có thể là số node. Nếu mỗi container tự tải riêng, số lần tải có thể bằng số instance.

### Registry pull không phải lúc nào cũng là một lần cho mỗi pod

Container runtime có thể cache image layer theo digest trên node. Nếu checkpoint nằm trong một layer của image và node đã có layer đó, container mới có thể không phải tải lại toàn bộ bytes. Ngược lại, nếu checkpoint là artifact riêng được init container tải xuống, mỗi pod có thể tạo thêm một lần download.

Hãy lấy số liệu từ registry, object storage và node cache thay vì nhân kích thước checkpoint với số pod một cách máy móc. Cần phân biệt:

- Logical bytes được yêu cầu bởi deployment.
- Bytes thực tế truyền qua mạng.
- Bytes lưu trong registry/cache.
- Bytes giải nén trên local disk.

### Scale-out đồng thời

Nếu 100 replica khởi động cùng lúc và mỗi replica tải checkpoint 4 GB, lượng dữ liệu lý thuyết là 400 GB nếu không có cache chia sẻ. Một burst như vậy có thể tạo áp lực lên registry, object storage, mạng và disk I/O, làm time-to-ready tăng dù từng lần restore riêng lẻ nhanh.

Có thể giảm áp lực bằng:

- Cache checkpoint theo digest ở node hoặc local artifact cache.
- Pre-pull artifact trước khi mở rộng workload.
- Phân phối theo batch thay vì khởi động toàn bộ replica cùng lúc.
- Dùng vùng lưu trữ gần node và tránh cross-region transfer không cần thiết.
- Đo bandwidth và giới hạn concurrency của download/unpack.
- Đặt timeout/retry có jitter để tránh mọi replica tải lại cùng lúc sau một lỗi.

Không dùng một cache key mutable như `latest`. Cache cần gắn với checkpoint digest để không nhầm generation.

## 8. Tính chi phí restore và tạo lại tài nguyên

Restore engine không phải toàn bộ startup. Sau khi process được phục hồi, ứng dụng có thể cần:

- Đọc cấu hình và secret của môi trường hiện tại.
- Tạo lại database pool và kiểm tra connection.
- Tạo HTTP client, broker session, listener và socket.
- Đăng ký instance mới vào service registry.
- Refresh cache hoặc static state đã stale.
- Khởi động scheduler, consumer và telemetry exporter.
- Chạy health check và readiness gate.

Chi phí restore có thể gồm CPU-second, RAM, disk I/O và thời gian sử dụng node trước khi instance nhận traffic. Một mô hình đơn giản:

\[
R_r = N_r \times (C_{restore} + C_{recreate} + C_{health})
\]

Trong đó (C_{restore}) là chi phí CPU/RAM của engine, (C_{recreate}) là chi phí tạo lại dependency, (C_{health}) là chi phí health check và thời gian chờ dependency. Nếu database hoặc service bên ngoài tính phí theo connection/request, cộng phần tương ứng vào (C_{recreate}).

### Thời gian tới readiness

Đo time-to-ready theo các thành phần:

\[
T_{ready} = T_{fetch} + T_{verify} + T_{unpack} + T_{restore} + T_{resources} + T_{health}
\]

Cold start cũng cần được đo theo cùng ranh giới:

\[
T_{cold-ready} = T_{JVM} + T_{framework} + T_{warmup} + T_{resources} + T_{health}
\]

Phần tiết kiệm:

\[
\Delta T = T_{cold-ready} - T_{ready}
\]

Nếu checkpoint lớn, download/unpack lâu hoặc dependency recreation chiếm phần lớn thời gian, (\Delta T) có thể nhỏ hơn dự kiến. Vì vậy, đo p50/p95/p99 của từng giai đoạn trong điều kiện scale thực tế.

## 9. Chi phí runtime sau restore

Một ảnh được warm-up có thể giữ nhiều cache/object trong heap. Điều đó giúp giảm công việc khởi tạo nhưng có thể làm tăng memory footprint so với một process cold start vừa khởi chạy.

Hãy so sánh:

- Heap used và committed ngay sau restore.
- RSS/process memory, native memory và direct buffer.
- GC frequency, pause time và allocation rate trong workload thực.
- Số thread, thread stack và executor queue.
- Cache hit ratio trước và sau khi refresh dependency.
- Số connection thực tế sau khi tạo pool mới.
- CPU spike trong thời gian restore và warm-up sau restore.

Nếu CRaC làm mỗi instance giữ thêm trung bình (\Delta M) GB RAM trong (H) giờ và đơn giá RAM là (P_{ram}), chi phí memory tăng thêm là:

\[
U_{memory} = N \times \Delta M \times H \times P_{ram}
\]

Tương tự, có thể tính phần CPU tăng thêm do GC, refresh cache hoặc reconnect. Không mặc định chi phí runtime bằng 0 chỉ vì checkpoint đã tạo trước đó.

### Warm cache không đồng nghĩa cache hợp lệ

Cache warm-up có thể giảm CPU và database query, nhưng nếu dữ liệu đã cũ hoặc cần invalidate sau restore, ứng dụng phải nạp lại. Khi đó, chi phí refresh cache cần được tính vào (C_{recreate}) và time-to-ready.

Chỉ giữ cache có thể tái sử dụng an toàn, ví dụ metadata bất biến theo version. Cache phụ thuộc tenant, quyền, giá, tồn kho hoặc endpoint runtime cần xác minh trước khi phục vụ.

## 10. Chi phí vận hành và vòng đời ảnh

Chi phí vận hành thường bị bỏ sót khi chỉ đo CPU và storage. Với CRaC, đội ngũ cần quản lý thêm:

- Ma trận tương thích JDK, OS/kernel, CPU architecture, checkpoint engine và container runtime.
- Pipeline tạo checkpoint và restore smoke test.
- Scan image, SBOM, provenance và checksum.
- Theo dõi artifact size, restore success rate và time-to-ready.
- Retention, revoke, delete và rollback.
- Hỗ trợ cold-start fallback khi restore lỗi.
- Xử lý checkpoint cũ sau khi vá JDK hoặc thư viện.
- Điều tra lỗi resource trong callback và lỗi native checkpoint.

Có thể quy đổi thời gian kỹ sư thành chi phí vận hành:

\[
O_r = H_{engineering}P_{hour} + C_{CI} + C_{monitoring} + C_{security}
\]

Trong đó (H_{engineering}) là số giờ vận hành/engineering phân bổ cho release, (P_{hour}) là chi phí mỗi giờ và các thành phần khác là chi phí CI, monitoring và security tooling.

Không nhất thiết phải phân bổ toàn bộ chi phí đội nền tảng vào một release. Có thể phân bổ theo số release, số service hoặc số instance, nhưng cần dùng cùng quy tắc cho cả các phương án để so sánh có ý nghĩa.

## 11. So sánh CRaC với cold start

Cold start cũng có chi phí. Ứng dụng phải khởi tạo JVM, load class, khởi tạo framework, warm-up code path, tạo connection và đạt readiness. Nếu startup chậm, hệ thống có thể phải:

- Giữ capacity dư để chịu tải tăng đột ngột.
- Scale sớm hơn dự báo.
- Chấp nhận request chờ hoặc lỗi trong lúc instance chưa ready.
- Giảm tốc độ rollout vì phải chờ instance khởi động.
- Duy trì nhiều instance warm để tránh cold start.

CRaC có thể giảm một phần chi phí này, nhưng bổ sung chi phí tạo, lưu, phân phối và restore checkpoint. So sánh nên dùng **chi phí tăng thêm** so với baseline cold start.

| Hạng mục | Cold start | CRaC |
|---|---|---|
| Chuẩn bị release | Build application image | Build application image và prepare/warm-up/checkpoint |
| Artifact storage | Application image | Application image và checkpoint nếu lưu riêng/nhúng thêm |
| Distribution | Pull application image | Pull application image và phân phối checkpoint |
| Khởi tạo process | JVM/framework init và warm-up | Restore process image |
| Dependency | Tạo connection/client | Vẫn phải tạo lại hoặc xác minh resource phụ thuộc môi trường |
| Runtime memory | Heap sau startup | Heap snapshot đã warm-up, có thể giữ thêm cache/object |
| Vận hành | Startup probe và scaling | Thêm compatibility, artifact lifecycle, restore test và fallback |

Đừng so sánh chỉ `T_restore` với `T_JVM`. So sánh toàn bộ time-to-ready và chi phí trong cùng một workload, cùng số instance, cùng thời gian quan sát và cùng SLO.

## 12. Tính điểm hòa vốn theo số instance

Giả sử:

- (F): chi phí cố định của một checkpoint generation, gồm build, storage trong kỳ và vận hành.
- (C_{cold}): chi phí khởi tạo tăng thêm trên mỗi instance nếu cold start.
- (C_{crac}): chi phí phân phối, restore và recreate resource trên mỗi instance.
- (N): số instance sử dụng checkpoint trong kỳ.

Chi phí cold start tăng thêm:

\[
C_{cold,total} = N \times C_{cold}
\]

Chi phí CRaC tăng thêm:

\[
C_{crac,total} = F + N \times C_{crac}
\]

Nếu (C_{cold} > C_{crac}), số instance hòa vốn là:

\[
N_{break-even} = \frac{F}{C_{cold} - C_{crac}}
\]

Nếu (C_{cold} \le C_{crac}), CRaC không hòa vốn bằng phần chi phí khởi tạo trực tiếp trong mô hình này. Vẫn có thể có giá trị nhờ giảm latency hoặc đáp ứng SLO, nhưng cần định lượng lợi ích đó riêng.

### Ví dụ số minh họa

Giả sử một checkpoint generation có:

| Khoản cố định | Chi phí quy ước |
|---|---:|
| Prepare, warm-up và checkpoint | 80 |
| Storage và retention trong kỳ | 30 |
| Pipeline, scan và vận hành phân bổ | 20 |
| **Tổng (F)** | **130** |

Giả sử trên mỗi instance:

| Khoản trên mỗi instance | Chi phí quy ước |
|---|---:|
| Cold-start CPU/warm-up | 3.0 |
| Checkpoint download, restore và recreate | 1.5 |
| Tiết kiệm trực tiếp | 1.5 |

Điểm hòa vốn:

\[
N_{break-even} = \frac{130}{3.0 - 1.5} \approx 87
\]

Với 20 instance, cold start có chi phí (20 \times 3 = 60), còn CRaC có chi phí (130 + 20 \times 1.5 = 160). Trong ví dụ này, CRaC tốn thêm 100 đơn vị chi phí.

Với 120 instance, cold start có chi phí (360), còn CRaC có chi phí (130 + 180 = 310). CRaC tiết kiệm 50 đơn vị chi phí.

Các con số chỉ minh họa cách tính, không phải giá cloud hoặc benchmark thực tế. Mô hình giả định chi phí runtime memory và các chi phí chung khác bằng nhau; nếu CRaC làm tăng RAM, GC hoặc fallback, cần cộng các khoản đó vào (F) hoặc (C_{crac}).

## 13. Giá trị của thời gian khởi động nhanh

Không phải lợi ích nào cũng chuyển trực tiếp thành tiền trên hóa đơn. Giảm time-to-ready có thể tạo giá trị qua:

- Đáp ứng SLO scale-out nhanh hơn khi traffic tăng đột ngột.
- Giảm số request phải chờ hoặc bị lỗi trong lúc instance chưa ready.
- Giảm thời gian rollout và thay thế node.
- Giảm số instance warm phải duy trì chỉ để tránh cold start.
- Tăng tốc phục hồi sau node failure hoặc deployment.

Để định lượng, cần dữ liệu workload:

- Tần suất scale event.
- Số instance cần thêm trong mỗi event.
- Số giây giảm được tới readiness.
- Request rate trong khoảng thời gian scale.
- Giá trị của request bị chậm/lỗi hoặc chi phí capacity dư.
- SLO và mức phạt nếu không đạt.

Ví dụ, nếu cần 40 instance mới và CRaC giảm p95 time-to-ready 50 giây, hệ thống có thể có thêm 2.000 instance-second capacity sẵn sàng sớm hơn. Không tự động coi 2.000 instance-second là tiền tiết kiệm; cần xác định lượng request được phục vụ sớm, capacity dự phòng giảm được hoặc penalty tránh được.

Một mô hình lợi ích có thể là:

\[
V_{latency} = V_{requests\ served\ earlier} + V_{capacity\ avoided} + V_{SLO\ risk\ reduced}
\]

Giữ phần giá trị này tách khỏi chi phí hạ tầng trực tiếp. Như vậy, quyết định có thể dựa trên TCO và giá trị kinh doanh mà không đánh đồng hai đại lượng.

## 14. Phân tích độ nhạy

Break-even phụ thuộc vào các giả định. Hãy thay đổi từng biến để xem quyết định có ổn định không:

| Biến | Khi tăng | Ảnh hưởng thường gặp |
|---|---|---|
| Checkpoint size | Storage và transfer tăng | Điểm hòa vốn cần nhiều instance hơn |
| Số instance restore | Chi phí phân phối/restore tăng nhưng fixed cost được phân bổ trên nhiều instance | Có thể làm CRaC kinh tế hơn nếu chi phí mỗi instance thấp hơn cold start |
| Số release mỗi tháng | Build, validation và retention tăng | Tăng chi phí cố định |
| Retention duration | GB-month tăng | Tăng storage cost |
| Cache hit rate | Download bytes giảm | Giảm distribution cost và time-to-ready |
| Compression ratio tốt hơn | Bytes transfer/storage giảm | Có thể tăng CPU và unpack time |
| Dependency recreation time | Restore-to-ready tăng | Giảm lợi ích latency |
| Memory footprint sau restore | RAM-hour tăng | Có thể làm tăng runtime cost |
| Restore failure rate | Retry/fallback tăng | Tăng chi phí và giảm độ tin cậy |

Nên lập ít nhất ba kịch bản:

- **Thấp:** ít instance, ít scale event, checkpoint lớn và retention dài.
- **Cơ sở:** số release/instance theo workload thực tế trung bình.
- **Cao:** scale-out nhiều, cache hit tốt và checkpoint được tái sử dụng trên nhiều instance.

Không dùng riêng kịch bản cao để quyết định triển khai. Nếu CRaC chỉ có lợi khi đạt cache hit gần tuyệt đối hoặc scale liên tục, cần kiểm chứng giả định đó bằng dữ liệu production-like.

## 15. Đo kích thước và chi phí bằng dữ liệu thực tế

Không dự đoán checkpoint size từ heap maximum. Hãy đo trên mỗi release:

```bash
du -sh checkpoint-directory
find checkpoint-directory -type f -printf '%s %p\n'
```

Nếu checkpoint được nén:

```bash
stat -c '%s %n' checkpoint.tar
sha256sum checkpoint.tar
```

Lưu metadata cùng release:

- Raw size và compressed size.
- Số file và số byte thực tế được upload.
- Upload/download duration.
- Cache hit/miss và số node thực tải artifact.
- Unpack và checksum duration.
- Restore duration.
- Dependency recreation và health-check duration.
- Heap/RSS/GC sau restore.

Các command ví dụ trên dùng Linux GNU tools; điều chỉnh theo OS và storage platform. Với object store/registry, dùng số liệu billing và telemetry của chính dịch vụ thay vì chỉ dùng `du` trên workspace local.

## 16. Đo time-to-ready theo từng giai đoạn

Đặt timestamp ở các mốc có thể so sánh:

```text
T0  deployment yêu cầu instance
T1  artifact download bắt đầu
T2  artifact download hoàn tất
T3  checksum/verify và unpack hoàn tất
T4  process restore hoàn tất
T5  database/client/listener được tạo lại
T6  health checks thành công
T7  readiness accepting và instance vào service
```

Từ đó tính:

| Khoảng | Ý nghĩa |
|---|---|
| (T2-T1) | Thời gian download |
| (T3-T2) | Verify và unpack |
| (T4-T3) | Process restore |
| (T5-T4) | Recreate runtime dependencies |
| (T6-T5) | Health check |
| (T7-T0) | Tổng time-to-ready |

Với cold start, đặt các mốc tương đương từ khi scheduler yêu cầu instance tới khi readiness accepting. Đo nhiều lần và dùng p50/p95/p99; một lần restore nhanh không đại diện cho scale burst hoặc node có cache lạnh.

## 17. Thiết kế dashboard chi phí CRaC

Một dashboard hữu ích nên kết nối chi phí artifact với hiệu quả phục vụ:

| Nhóm dashboard | Chỉ số |
|---|---|
| Build | Prepare duration, warm-up duration, checkpoint duration, retry count, runner cost |
| Artifact | Raw/compressed size, GB-month, number of versions, retention, replication |
| Distribution | Download bytes, egress cost, cache hit ratio, download/unpack duration |
| Restore | Restore duration, resource recreation duration, failure rate, time-to-ready |
| Runtime | Heap, RSS, CPU, GC, active connections, cache hit ratio |
| Business/SLO | Scale event, p95 readiness, request delay/error trong lúc scale, capacity dự phòng |
| Lifecycle | Release generation, active/revoked checkpoint count, cold-start fallback count |

Gắn các metric với release ID, application image digest và checkpoint digest trong log/provenance. Tránh đưa digest hoặc UUID có cardinality cao vào mọi metric label; có thể lưu chúng trong log/event metadata và dùng label ổn định hơn cho dashboard tổng hợp.

## 18. Các lỗi tính chi phí thường gặp

### Chỉ tính giá lưu trữ

Storage có thể rẻ nhưng build, transfer, restore, memory và vận hành mới là khoản lớn. Dùng mô hình đủ năm nhóm chi phí.

### Nhân checkpoint size với số pod mà không kiểm tra cache

Registry layer cache hoặc node-local cache có thể giảm số lần tải. Đo bytes thực tế qua mạng và số cache miss.

### Bỏ qua số lần tạo checkpoint thất bại

Một release có thể tốn nhiều runner attempt. Tính cả attempt thất bại và restore smoke test bị retry.

### Chỉ đo restore engine

Ứng dụng vẫn phải tạo connection pool, listener, telemetry exporter và health check. Đo từ lúc deployment yêu cầu instance tới readiness.

### Coi thời gian tiết kiệm là tiền tiết kiệm

Giảm 50 giây startup chỉ có giá trị kinh tế khi giúp phục vụ request sớm hơn, giảm capacity dự phòng hoặc cải thiện SLO. Nêu riêng giá trị latency và chi phí hạ tầng.

### Bỏ qua RAM và GC sau restore

Heap warm-up có thể lớn hơn baseline. Theo dõi RSS, GC và memory-hour thay vì chỉ nhìn CPU startup.

### Không tính retention và security patch

Mỗi generation cũ có thể phải được giữ lại, cách ly hoặc tạo mới sau bản vá. Đưa retention, revoke và rebuild vào mô hình.

### So sánh workload không tương đương

Cold start và CRaC phải chạy cùng JDK/app version, cùng dependency, cùng host class, cùng request mix và cùng readiness definition. Nếu không, kết quả cost/performance không có ý nghĩa.

## 19. Quy trình đánh giá một service trước khi áp dụng CRaC

1. Đo cold-start baseline trên cùng host type: CPU, RAM, startup duration, time-to-ready và first-request latency.
2. Tạo checkpoint thử nghiệm bằng workload warm-up đại diện.
3. Đo raw/compressed checkpoint size và chi phí prepare.
4. Đo storage theo retention và số version dự kiến.
5. Đo distribution trên node có cache lạnh và cache nóng.
6. Đo restore cùng dependency recreation và readiness.
7. Đo heap/RSS/GC và CPU trong workload sau restore.
8. Tính break-even theo số instance, số release và số scale event.
9. Thêm chi phí fallback, security patch và vận hành.
10. Chạy sensitivity analysis với workload thấp/cơ sở/cao.
11. Thử canary và so sánh số liệu thực tế với mô hình.
12. Chỉ mở rộng nếu lợi ích đo được đáp ứng SLO và TCO mục tiêu.

## 20. Checklist tính tổng chi phí

### Dựng ảnh

- [ ] Đã tính runner CPU/RAM và thời gian warm-up.
- [ ] Đã tính checkpoint engine, đóng gói, checksum và restore smoke test.
- [ ] Đã tính các attempt thất bại/retry.
- [ ] Đã tính chi phí dependency/sandbox dùng trong warm-up.

### Lưu ảnh

- [ ] Đã đo raw size và compressed size thực tế.
- [ ] Đã tính số generation, retention và GB-month.
- [ ] Đã tính replication, backup và storage request.
- [ ] Có policy xóa/cách ly checkpoint revoked và expired.

### Phân phối ảnh

- [ ] Đã đo số lần download thực tế và cache hit ratio.
- [ ] Đã tính cross-region egress và registry/object-store request.
- [ ] Đã đo verify, unpack và disk I/O.
- [ ] Đã thử scale-out đồng thời để phát hiện network bottleneck.

### Sử dụng ảnh

- [ ] Đã đo restore CPU/RAM và time-to-ready.
- [ ] Đã tính dependency recreation, connection pool và health check.
- [ ] Đã đo heap/RSS/GC sau restore.
- [ ] Đã tính fallback/retry khi restore thất bại.

### So sánh và quyết định

- [ ] Cold start và CRaC dùng cùng workload và readiness definition.
- [ ] Chi phí chung đã được loại khỏi phần so sánh tăng thêm.
- [ ] Đã tính break-even theo số instance.
- [ ] Giá trị giảm latency/SLO được tách khỏi chi phí hạ tầng trực tiếp.
- [ ] Đã chạy sensitivity analysis và kiểm chứng bằng canary.

## 21. Kết luận

Đánh giá hiệu quả CRaC cần tính toàn bộ chi phí của checkpoint trong vòng đời release: chuẩn bị và warm-up, tạo ảnh, lưu trữ, phân phối, restore, tái tạo dependency, memory/CPU sau restore và vận hành artifact. Kích thước checkpoint và thời gian restore chỉ là hai chỉ số trong một mô hình rộng hơn.

Hãy đo chi phí cố định của mỗi generation, chi phí trên mỗi lần restore và số instance thực sự sử dụng ảnh. Dùng break-even để xác định quy mô mà phần tiết kiệm cold-start bù được chi phí tạo/lưu/phân phối; đồng thời định lượng riêng giá trị time-to-ready và SLO. Chỉ khi so sánh trên cùng workload và có dữ liệu về cache, retention, resource recreation cùng runtime footprint, đội ngũ mới có thể quyết định CRaC đem lại lợi ích kinh tế thực tế cho service đó hay không.
