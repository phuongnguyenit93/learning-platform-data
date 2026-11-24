# Triển khai, cập nhật và rollback workload từ xa

Trong mô hình compute lai và điện toán biên, workload có thể chạy ở cloud, trung tâm dữ liệu tại chỗ, nhà máy, cửa hàng hoặc thiết bị đặt gần nguồn dữ liệu. Người vận hành cần triển khai và cập nhật phần mềm trên nhiều môi trường từ một hệ thống quản lý tập trung, dù các node ở xa có thể dùng phần cứng khác nhau, kết nối mạng không ổn định hoặc chỉ cho phép truy cập trong một khoảng thời gian nhất định.

**Triển khai từ xa** là quá trình đưa một phiên bản workload và cấu hình tới nhóm máy đích, xác nhận máy đã nhận và chạy đúng phiên bản. **Cập nhật từ xa** thay phiên bản đang hoạt động theo một kế hoạch kiểm soát rủi ro. **Rollback** đưa workload hoặc cấu hình về phiên bản đã biết là hoạt động tốt khi bản phát hành mới gây lỗi.

Một quy trình tốt cần quản lý được danh tính thiết bị, phiên bản artifact, cấu hình, tiến trình rollout, trạng thái sức khỏe và khả năng khôi phục. Đối với edge, phải tính đến trường hợp thiết bị mất kết nối giữa lúc tải và lúc kích hoạt bản cập nhật.

## 1. Kiến trúc triển khai workload từ xa

Một hệ thống triển khai từ xa thường có bốn thành phần:

- **Control plane:** nơi người vận hành định nghĩa bản phát hành, nhóm thiết bị, chính sách triển khai, lịch cập nhật và tiêu chí thành công.
- **Artifact registry:** kho lưu image container, package, binary, cấu hình mẫu hoặc firmware đã được kiểm tra.
- **Device/edge agent:** thành phần chạy tại site hoặc node, xác thực với control plane, nhận lệnh, tải artifact, kiểm tra và điều phối workload cục bộ.
- **Workload runtime:** container runtime, Kubernetes distribution, process supervisor hoặc nền tảng IoT edge thực thi workload.

~~~mermaid
flowchart TD
    A["CI/CD build và kiểm thử"] --> B["Artifact registry<br/>image/package đã ký"]
    B --> C["Control plane<br/>release và rollout policy"]
    D["Fleet inventory<br/>nhóm thiết bị, phiên bản, health"] --> C
    C --> E["Device / edge agent"]
    E --> F["Xác minh chữ ký và cấu hình"]
    F --> G["Runtime tại edge"]
    G --> H["Workload mới"]
    H --> I["Health check và telemetry"]
    I --> C
    C --> J["Tiếp tục, tạm dừng hoặc rollback"]
~~~

Control plane thường không cần mở cổng quản trị trực tiếp vào mọi thiết bị. Một mô hình phổ biến là edge agent chủ động tạo kết nối outbound có xác thực tới dịch vụ quản lý, nhận desired state và gửi reported state. Cách này phù hợp với site nằm sau NAT hoặc firewall nghiêm ngặt. Nếu dùng mô hình push, cần thiết kế kênh quản trị, xác thực và giới hạn truy cập chặt chẽ.

### 1.1. Desired state và reported state

Control plane mô tả **desired state**: phiên bản workload, cấu hình, số replica hoặc trạng thái mong muốn. Edge agent báo cáo **reported state**: phiên bản đang chạy, trạng thái tải artifact, kết quả health check và lỗi gần nhất.

Hai trạng thái có thể lệch nhau khi thiết bị offline, tải file thất bại hoặc runtime không thể kích hoạt bản mới. Hệ thống quản lý cần thể hiện rõ sự khác biệt này thay vì đánh dấu triển khai thành công ngay khi gửi lệnh.

Ví dụ:

| Desired state | Reported state | Diễn giải |
|---|---|---|
| v2.4.1 | v2.4.1 healthy | Thiết bị đã đạt phiên bản mong muốn |
| v2.4.1 | v2.3.8 offline | Thiết bị chưa nhận được bản cập nhật |
| v2.4.1 | v2.4.1 unhealthy | Đã kích hoạt nhưng workload không khỏe |
| v2.4.1 | v2.3.8 update_failed | Tải hoặc xác minh artifact thất bại |
| v2.4.1 | v2.3.8 rollback_complete | Bản mới lỗi và thiết bị đã quay lại bản cũ |

## 2. Chuẩn bị workload cho triển khai từ xa

Workload cần được đóng gói và định danh để có thể triển khai lặp lại trên nhiều node.

### 2.1. Đóng gói và định danh phiên bản

Với container, build image trong pipeline và gắn tag phiên bản dễ đọc. Khi triển khai, nên tham chiếu image bằng digest bất biến, ví dụ:

registry.example.com/edge/temperature-processor@sha256:...

Digest xác định chính xác nội dung image. Tag như latest có thể trỏ tới nội dung khác sau này, làm cho hai thiết bị nhận cùng cấu hình nhưng chạy mã khác nhau.

Với binary hoặc package, lưu checksum và metadata build. Với firmware, cần lưu model phần cứng, phiên bản bootloader, yêu cầu nguồn điện và quy trình cập nhật riêng. Không nên coi việc cập nhật ứng dụng container và cập nhật firmware là cùng một thao tác.

### 2.2. Artifact và metadata phát hành

Mỗi release nên có metadata tối thiểu:

- Tên workload và phiên bản.
- Artifact URI và digest/checksum.
- Kiến trúc CPU và loại runtime tương thích.
- Phiên bản cấu hình hoặc schema.
- Chữ ký số và danh tính đơn vị phát hành.
- Điều kiện tài nguyên tối thiểu.
- Phiên bản tối thiểu của edge agent hoặc runtime nếu có.
- Chính sách health check, timeout và rollback.
- Ghi chú thay đổi và liên kết tới build/commit.

Artifact nên được ký trong pipeline và xác minh chữ ký trên thiết bị trước khi cài đặt. Checksum phát hiện lỗi truyền tải; chữ ký số còn giúp xác minh artifact đến từ nguồn phát hành đáng tin cậy.

### 2.3. Cấu hình tách khỏi image

Cấu hình theo site hoặc thiết bị nên được quản lý riêng với image. Một workload có thể dùng cùng image ở nhiều nhà máy nhưng mỗi site kết nối tới broker, endpoint hoặc vùng dữ liệu khác nhau.

Cấu hình cần có version và schema. Secret như chứng thư, token hoặc mật khẩu phải được cấp qua secret manager hoặc danh tính workload, không nhúng vào image hay manifest công khai. Khi rollback, phải biết cấu hình nào tương thích với phiên bản workload cũ.

## 3. Phân nhóm thiết bị và chính sách rollout

Không nên phát hành đồng thời cho toàn bộ fleet nếu workload có ảnh hưởng tới vận hành vật lý hoặc nghiệp vụ. Chia thiết bị thành nhóm giúp phát hiện lỗi sớm và giới hạn phạm vi tác động.

Một số cách phân nhóm:

- **Theo môi trường:** lab, staging, pilot và production.
- **Theo site:** nhà máy, kho, cửa hàng hoặc vùng địa lý.
- **Theo phần cứng:** model CPU, kiến trúc, dung lượng RAM, GPU hoặc phiên bản gateway.
- **Theo mức độ quan trọng:** thiết bị thử nghiệm, thiết bị dự phòng và thiết bị vận hành trọng yếu.
- **Theo điều kiện mạng:** luôn kết nối, kết nối theo lịch hoặc thường xuyên offline.

Có thể triển khai theo các vòng:

1. **Lab:** kiểm tra chức năng và tương thích trên thiết bị đại diện.
2. **Canary:** cập nhật một số ít thiết bị production có thể quan sát tốt.
3. **Pilot:** mở rộng tới một site hoặc nhóm người dùng nhỏ.
4. **Progressive rollout:** tăng dần tỷ lệ thiết bị sau mỗi lần đánh giá.
5. **Fleet-wide:** phát hành cho phần còn lại khi các ngưỡng chất lượng đạt yêu cầu.

~~~mermaid
flowchart LR
    A["Lab<br/>2 thiết bị"] --> B["Canary<br/>5 thiết bị"]
    B --> C["Pilot<br/>1 site"]
    C --> D["Rollout<br/>10% fleet"]
    D --> E["Rollout<br/>50% fleet"]
    E --> F["Toàn bộ fleet"]
    B -. "lỗi vượt ngưỡng" .-> G["Pause / rollback"]
    C -. "lỗi vượt ngưỡng" .-> G
    D -. "lỗi vượt ngưỡng" .-> G
    E -. "lỗi vượt ngưỡng" .-> G
~~~

Tỷ lệ và kích thước nhóm phải phù hợp với mức độ rủi ro, khả năng quan sát và năng lực hỗ trợ. Với hệ thống điều khiển công nghiệp, có thể cần cập nhật từng thiết bị dự phòng trước, sau đó mới cập nhật thiết bị đang đảm nhiệm chức năng chính.

### 3.1. Điều kiện bắt đầu và dừng rollout

Trước khi bắt đầu một đợt rollout, xác nhận:

- Thiết bị đang online hoặc có lịch kết nối đủ để tải artifact.
- Đủ dung lượng lưu trữ cho artifact mới và bản cũ dùng rollback.
- Nguồn điện ổn định và thiết bị không ở chế độ vận hành bị cấm cập nhật.
- Runtime và phần cứng tương thích.
- Có backup hoặc checkpoint cho dữ liệu cần bảo vệ.
- Có cửa sổ bảo trì và người chịu trách nhiệm khi cập nhật hệ thống quan trọng.

Đặt ngưỡng dừng rõ ràng, ví dụ tỷ lệ health check thất bại, số thiết bị không báo cáo, lỗi khởi động, latency tăng hoặc lỗi nghiệp vụ. Khi vượt ngưỡng, control plane tạm dừng phân phối bản mới để tránh mở rộng sự cố.

## 4. Quy trình cập nhật workload từ xa

Một quy trình cập nhật có kiểm soát thường gồm các bước:

1. **Lập kế hoạch:** xác định release, nhóm thiết bị, cửa sổ cập nhật và ngưỡng thành công.
2. **Kiểm tra tương thích:** so sánh kiến trúc, runtime, tài nguyên, phiên bản agent và schema cấu hình.
3. **Tải artifact:** edge agent tải artifact từ registry hoặc cache gần site.
4. **Xác minh:** kiểm tra chữ ký, digest, nguồn phát hành và metadata.
5. **Chuẩn bị:** lưu cấu hình cần thiết, kiểm tra dung lượng và giữ lại phiên bản đang hoạt động.
6. **Kích hoạt:** tạo container/process mới hoặc chuyển workload sang bản mới theo chiến lược đã chọn.
7. **Health check:** kiểm tra tiến trình, readiness, kết nối dependency và metric nghiệp vụ.
8. **Báo cáo:** gửi phiên bản thực tế, trạng thái và lỗi về control plane.
9. **Quyết định:** tiếp tục rollout, tạm dừng, retry hoặc rollback.

Thiết bị có thể mất mạng giữa các bước. Agent cần lưu tiến trình cập nhật bền vững cục bộ để sau khi kết nối trở lại có thể tiếp tục hoặc hủy an toàn. Lệnh rollout nên có release ID và idempotency key để việc nhận lại cùng một lệnh không tạo ra nhiều lần cài đặt ngoài ý muốn.

### 4.1. Cập nhật rolling

Rolling update thay thế workload theo từng nhóm nhỏ. Nếu một node có nhiều replica, hệ thống có thể tạo replica mới, kiểm tra readiness rồi mới dừng replica cũ.

Ưu điểm là giảm gián đoạn và không cần nhân đôi toàn bộ fleet. Đánh đổi là trong giai đoạn chuyển tiếp, hai phiên bản có thể cùng tồn tại. API, message format và schema dữ liệu phải tương thích trong thời gian này.

Với edge gateway chỉ có một instance, rolling có thể cần một tiến trình phụ hoặc một runtime slot để khởi chạy bản mới trong khi bản cũ vẫn sẵn sàng. Nếu tài nguyên không đủ để chạy song song, cần lịch downtime rõ ràng và phương án phục hồi.

### 4.2. Blue-green hoặc A/B

Blue-green duy trì hai môi trường: bản đang phục vụ (blue) và bản mới (green). Sau khi green vượt qua kiểm tra, bộ định tuyến hoặc supervisor chuyển traffic sang green. Nếu có lỗi, chuyển lại blue.

Cách này giúp rollback nhanh nhưng cần đủ tài nguyên để lưu và chạy hai phiên bản. Trên thiết bị edge nhỏ, có thể không đủ RAM hoặc dung lượng để giữ cả hai image đã giải nén. Cần tính trước storage, CPU và thời gian khởi động.

### 4.3. Cập nhật theo lịch và theo điều kiện

Một số thiết bị chỉ có thể cập nhật ngoài giờ sản xuất hoặc khi máy móc đang ở trạng thái an toàn. Control plane có thể phát hành desired state trước, còn agent chỉ thực thi khi điều kiện tại chỗ thỏa mãn.

Ví dụ, gateway trong kho chỉ cập nhật lúc ít hoạt động, còn thiết bị giám sát lạnh có thể cập nhật ngay nếu bản mới không làm gián đoạn cảm biến. Điều kiện an toàn cần được xác minh tại thiết bị vì control plane có thể nhận trạng thái trễ.

## 5. Quản lý mạng chập chờn và thiết bị offline

Edge node có thể mất kết nối trong thời gian dài. Không nên yêu cầu mọi bước cập nhật phụ thuộc vào kết nối liên tục với cloud.

Các biện pháp phù hợp:

- Agent chủ động kết nối outbound, xác thực thiết bị bằng chứng thư hoặc identity riêng.
- Dùng retry với exponential backoff và jitter để tránh hàng nghìn thiết bị cùng kết nối lại một lúc.
- Lưu release ID, trạng thái tải và checksum đã xác minh để tiếp tục tải khi phù hợp.
- Dùng cache artifact tại site hoặc regional registry để giảm băng thông WAN.
- Tải theo block có checksum hoặc cơ chế resume nếu giao thức hỗ trợ.
- Chỉ kích hoạt khi artifact hoàn chỉnh và đã xác minh chữ ký.
- Lưu reported state cục bộ khi offline rồi đồng bộ lại khi kết nối trở lại.
- Có chính sách hết hạn cho lệnh cập nhật để thiết bị không thực thi một lệnh quá cũ sau nhiều ngày offline.

Cần phân biệt retry tải artifact với retry khởi chạy workload. Tải lỗi có thể thử lại mà chưa ảnh hưởng ứng dụng đang chạy. Kích hoạt bản mới lỗi cần quay về phiên bản cũ và ghi nhận trạng thái rollback.

## 6. Rollback workload và cấu hình

Rollback là quy trình có chủ đích để đưa hệ thống về trạng thái đã biết là hoạt động tốt. Nó cần có từ lúc thiết kế release, không nên chỉ là thao tác đổi tag image.

Một kế hoạch rollback cần xác định:

- Phiên bản workload trước đó và artifact digest tương ứng.
- Cấu hình đã chạy cùng phiên bản đó.
- Cách chuyển traffic hoặc khởi chạy lại phiên bản cũ.
- Dữ liệu nào được tạo hoặc thay đổi bởi bản mới.
- Thời gian tối đa để rollback và tiêu chí xác nhận thành công.
- Cách xử lý nếu thiết bị offline hoặc bản cũ không còn tương thích.

### 6.1. Điều kiện kích hoạt rollback

Rollback có thể được kích hoạt khi:

- Workload mới không khởi động hoặc crash liên tục.
- Health check thất bại quá ngưỡng.
- Error rate hoặc latency vượt giới hạn.
- Không thể kết nối tới dependency quan trọng.
- Output sai schema hoặc vi phạm kiểm tra nghiệp vụ.
- Tỷ lệ thiết bị cập nhật thành công thấp hơn mục tiêu.
- Thiết bị mất khả năng điều khiển hoặc quan sát cần thiết.

Với thiết bị liên quan đến an toàn vật lý, cần có trạng thái fail-safe tại chỗ. Rollback phần mềm không thể thay thế interlock hoặc cơ chế bảo vệ độc lập của thiết bị.

### 6.2. Các bước rollback

1. Dừng rollout và ngăn thiết bị mới nhận release lỗi.
2. Xác định nhóm thiết bị bị ảnh hưởng và phiên bản thực tế.
3. Chọn artifact đã biết tốt bằng digest hoặc version cố định.
4. Khôi phục cấu hình tương thích với bản cũ.
5. Khởi chạy bản cũ hoặc chuyển traffic về môi trường cũ.
6. Kiểm tra health, kết nối và kết quả nghiệp vụ.
7. Báo cáo trạng thái rollback về control plane.
8. Giữ log và metadata của release lỗi để điều tra.

Nếu bản mới đã thay đổi dữ liệu, cần có phương án riêng. Rollback binary không tự hoàn tác database migration hoặc dữ liệu đã ghi. Cần ưu tiên migration tương thích ngược, version hóa record, backup hoặc thao tác bù trừ.

## 7. Tương thích dữ liệu và schema khi rollback

Một lỗi thường gặp là workload mới ghi dữ liệu theo schema mà phiên bản cũ không đọc được. Khi rollback, tiến trình cũ khởi động thành công nhưng không thể xử lý dữ liệu mới.

Có thể giảm rủi ro bằng mô hình **expand-contract**:

1. Mở rộng schema theo cách phiên bản cũ vẫn đọc được.
2. Triển khai workload mới có thể đọc/ghi schema cũ và mới.
3. Chuyển đổi dữ liệu theo từng bước, có kiểm tra.
4. Chỉ bỏ trường hoặc cấu trúc cũ khi không còn workload nào cần nó và thời hạn rollback đã hết.

Với edge offline, cần đặc biệt cẩn thận vì thiết bị có thể ở phiên bản cũ trong thời gian dài. API và schema trung tâm nên duy trì tương thích trong khoảng thời gian đã định hoặc có giao thức version negotiation.

Nếu không thể duy trì tương thích, cần quy định phiên bản tối thiểu được hỗ trợ, lịch hết hạn rollback và quy trình nâng cấp bắt buộc trước khi thiết bị được phép gửi dữ liệu mới.

## 8. Ví dụ thực tế: cập nhật bộ xử lý dữ liệu tại nhiều cửa hàng

Một doanh nghiệp có 120 cửa hàng. Mỗi cửa hàng có một edge gateway chạy container inventory-sync, thu thập dữ liệu bán hàng và đồng bộ với cloud khi mạng khả dụng.

Phiên bản hiện tại là 2.3.8; bản mới 2.4.1 sửa lỗi đồng bộ và bổ sung trường metadata. Quy trình triển khai có thể như sau:

### 8.1. Chuẩn bị release

Pipeline build image inventory-sync, chạy unit/integration test, quét lỗ hổng, tạo SBOM và ký artifact. Release metadata chứa digest, kiến trúc CPU, phiên bản cấu hình và health check.

Bản phát hành được thử trên thiết bị lab và một cửa hàng nội bộ. Nhóm xác nhận gateway có đủ dung lượng lưu image cũ và mới, đồng thời kiểm tra bản mới đọc được dữ liệu do phiên bản cũ tạo ra.

### 8.2. Rollout theo nhóm

- Nhóm canary gồm 2 cửa hàng.
- Nếu cả hai báo healthy và đồng bộ dữ liệu thành công trong cửa sổ quan sát, mở rộng lên 10 cửa hàng.
- Tiếp theo triển khai 25% fleet, rồi 50%, sau đó toàn bộ.
- Thiết bị offline được giữ ở trạng thái pending và cập nhật khi kết nối trở lại trong cửa sổ cho phép.

Control plane theo dõi tỷ lệ thiết bị healthy, số lần retry, thời gian cập nhật, lỗi đồng bộ và độ trễ dữ liệu. Nếu canary có lỗi vượt ngưỡng, dừng rollout.

### 8.3. Rollback

Nếu phiên bản 2.4.1 làm tăng lỗi đồng bộ, control plane gửi release rollback tới nhóm đã cập nhật. Agent xác minh artifact 2.3.8, khôi phục cấu hình tương thích và khởi chạy lại container cũ. Dữ liệu bán hàng đã lưu cục bộ được giữ nguyên; agent tiếp tục đồng bộ sau khi phiên bản cũ healthy.

Không xóa image cũ hoặc dữ liệu pending cho đến khi rollback được xác nhận và nhóm vận hành đã kiểm tra số lượng bản ghi chưa đồng bộ.

Ví dụ này cho thấy rollout phải quan sát cả sức khỏe tiến trình và kết quả nghiệp vụ. Container ở trạng thái Running không chứng minh dữ liệu đã đồng bộ đúng.

## 9. Ví dụ manifest release mang tính khái niệm

Manifest dưới đây minh họa thông tin một release. Cấu trúc thực tế phụ thuộc nền tảng quản lý fleet và edge runtime:

~~~yaml
release:
  id: inventory-sync-2.4.1
  workload: inventory-sync
  artifact:
    image: registry.example.com/edge/inventory-sync@sha256:IMAGE_DIGEST
    signatureRef: release-signature
  target:
    labels:
      environment: production
      hardware: edge-gateway-v2
  rollout:
    strategy: progressive
    batches:
      - percent: 2
        observeMinutes: 30
      - percent: 10
        observeMinutes: 60
      - percent: 25
        observeMinutes: 60
      - percent: 100
    maxFailurePercent: 2
  health:
    readiness: /health/ready
    maxStartupSeconds: 90
  rollback:
    artifactRef: inventory-sync-2.3.8
    onReadinessFailure: true
    preserveLocalQueue: true
~~~

Đây là ví dụ mô hình hóa, không phải schema chuẩn của Kubernetes, AWS IoT Greengrass hay Azure IoT Edge. Trước khi áp dụng, ánh xạ các trường sang deployment service cụ thể và xác minh cách nền tảng xử lý tỷ lệ rollout, offline target, timeout và rollback.

## 10. Bảo mật kênh triển khai từ xa

Kênh triển khai có quyền thay đổi phần mềm chạy trên thiết bị, do đó phải được bảo vệ như một mặt phẳng quản trị có đặc quyền cao.

- Mỗi thiết bị có danh tính riêng, chứng thư hoặc cơ chế workload identity; tránh dùng chung một khóa cho toàn fleet.
- Xác thực hai chiều khi agent kết nối control plane nếu nền tảng hỗ trợ.
- Ký artifact và xác minh chữ ký trước khi cài đặt.
- Giới hạn quyền phát hành theo vai trò; tách quyền build, approve và deploy.
- Ghi audit trail cho người phê duyệt, release ID, nhóm đích và thời điểm.
- Mã hóa dữ liệu truyền tải và bảo vệ secret trong kho chuyên dụng.
- Chống replay bằng release ID, nonce, timestamp hoặc version monotonic phù hợp.
- Hạn chế lệnh từ xa; agent chỉ thực hiện loại thao tác đã được cho phép.
- Cập nhật và bảo vệ chính edge agent vì agent có quyền triển khai workload.
- Thu hồi chứng thư thiết bị bị mất, bị thay thế hoặc không còn thuộc fleet.

Chữ ký artifact chứng minh nguồn gốc và tính toàn vẹn của gói, nhưng không chứng minh phần mềm an toàn hoặc không có lỗi. Pipeline vẫn cần kiểm thử, quét lỗ hổng và quy trình phê duyệt phù hợp.

## 11. Quan sát rollout và xác minh kết quả

Một đợt triển khai cần có trạng thái theo từng thiết bị, theo từng release và theo toàn fleet. Các chỉ số nên bao gồm:

| Chỉ số | Mục đích |
|---|---|
| Target reachability | Biết thiết bị online, offline hoặc chưa nhận lệnh |
| Download success / duration | Phát hiện lỗi registry, mạng hoặc thiếu băng thông |
| Signature verification | Xác nhận artifact hợp lệ trước khi kích hoạt |
| Activation success | Biết workload mới đã được khởi chạy |
| Readiness / health | Xác nhận workload có thể phục vụ |
| Version convergence | Tỷ lệ thiết bị đang chạy đúng desired version |
| Rollback count | Phát hiện release có vấn đề |
| Business metric | Kiểm tra dữ liệu hoặc nghiệp vụ thực sự hoạt động |
| Disk / memory / CPU | Phát hiện tài nguyên không đủ sau cập nhật |

Log cần có device ID, site ID, release ID, workload version, bước cập nhật và mã lỗi. Tránh ghi credential hoặc dữ liệu nghiệp vụ nhạy cảm.

### 11.1. Tiêu chí hoàn tất rollout

Không nên kết luận rollout hoàn tất chỉ dựa vào số lệnh đã gửi. Cần xác nhận:

- Thiết bị mục tiêu đã nhận release hoặc được ghi nhận offline theo chính sách.
- Artifact được xác minh chữ ký và digest.
- Workload chạy đúng version và cấu hình.
- Health/readiness đạt yêu cầu trong thời gian quan sát.
- Metric nghiệp vụ không vượt ngưỡng lỗi.
- Thiết bị đã báo cáo trạng thái về control plane.
- Những thiết bị thất bại có lý do, người xử lý và kế hoạch retry/rollback.

Có thể đặt ngưỡng hoàn tất theo nhóm, ví dụ 98% thiết bị online đã healthy và phần còn lại được phân loại rõ ràng. Thiết bị offline không nên bị tính là thành công chỉ vì không báo lỗi.

## 12. Xử lý sự cố triển khai

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Thiết bị không nhận release | Offline, DNS/firewall, chứng thư hết hạn | Kiểm tra heartbeat, thời gian hệ thống, outbound endpoint và identity |
| Tải artifact thất bại | Mạng chập chờn, hết dung lượng, quyền registry | Kiểm tra retry, cache, quota disk và quyền tải |
| Chữ ký không hợp lệ | Artifact bị thay đổi hoặc trust root sai | Dừng kích hoạt, xác minh nguồn phát hành và trust chain |
| Container không khởi động | Image sai kiến trúc, thiếu dependency hoặc config | Đọc runtime log, kiểm tra manifest và tương thích phần cứng |
| Health check thất bại | Dependency chưa sẵn sàng, lỗi ứng dụng | Dừng rollout, xem log và cân nhắc rollback |
| Rollback không thành công | Bản cũ không còn artifact, schema không tương thích, disk đầy | Giữ trạng thái an toàn, khôi phục artifact/config và xử lý dữ liệu theo runbook |
| Thiết bị cập nhật lặp | Lệnh không idempotent hoặc desired state không hội tụ | Kiểm tra release ID, reported state và logic agent |

Khi xử lý thiết bị mất kết nối, không nên liên tục gửi lệnh mới với release ID khác nhau. Trước hết cần biết agent đã thực hiện tới bước nào; khi thiết bị online trở lại, nó có thể đang chạy bản mới, bản cũ hoặc ở trạng thái cần phục hồi.

## 13. Checklist triển khai, cập nhật và rollback

- [ ] Workload có artifact/version bất biến, digest hoặc checksum và chữ ký số.
- [ ] Runtime, kiến trúc phần cứng, tài nguyên và dependency tương thích với nhóm thiết bị.
- [ ] Cấu hình có version riêng, secret được cấp an toàn và có thể khôi phục.
- [ ] Fleet được phân nhóm theo site, phần cứng, mức độ quan trọng và điều kiện mạng.
- [ ] Có lab, canary, pilot và rollout tăng dần với ngưỡng dừng rõ ràng.
- [ ] Agent xác thực thiết bị, nhận lệnh an toàn và lưu tiến trình khi offline.
- [ ] Artifact chỉ được kích hoạt sau khi tải đầy đủ và xác minh chữ ký.
- [ ] Có đủ dung lượng để giữ bản đang chạy và bản dự phòng cần cho rollback.
- [ ] Health check bao gồm cả sức khỏe tiến trình và kiểm tra nghiệp vụ.
- [ ] Lệnh triển khai có release ID và có thể retry mà không tạo tác dụng lặp.
- [ ] Schema và dữ liệu tương thích với phiên bản cũ trong cửa sổ rollback.
- [ ] Có tiêu chí kích hoạt rollback, quy trình khôi phục và người chịu trách nhiệm.
- [ ] Control plane hiển thị desired/reported version và phân loại thiết bị offline.
- [ ] Sau rollout hoặc rollback, xác minh version, health, dữ liệu và metric toàn fleet.

Triển khai từ xa hiệu quả khi control plane quản lý được desired state, agent thực thi an toàn tại site và mỗi release có thể truy vết bằng phiên bản bất biến. Rollout theo nhóm, kiểm tra sức khỏe, xử lý offline và chuẩn bị tương thích dữ liệu giúp giảm phạm vi ảnh hưởng khi cập nhật. Rollback chỉ được coi là thành công sau khi workload cũ chạy ổn định và dữ liệu nghiệp vụ đã được xác minh.
