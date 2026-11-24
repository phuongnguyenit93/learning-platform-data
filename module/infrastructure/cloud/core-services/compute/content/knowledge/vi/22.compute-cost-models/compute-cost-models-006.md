# Lập lịch tắt mở và loại bỏ tài nguyên không còn sử dụng

Tài nguyên compute thường tiếp tục phát sinh chi phí khi không có người dùng hoặc workload đang cần chúng. Một môi trường development có thể chỉ hoạt động trong giờ làm việc; máy chạy kiểm thử có thể chỉ cần tồn tại trong vài giờ; một VM được tạo để điều tra sự cố có thể bị bỏ quên sau khi công việc kết thúc. Nếu không có lịch tắt/mở và quy trình thu hồi, tổ chức sẽ trả tiền cho capacity nhàn rỗi, disk, IP, snapshot, NAT hoặc load balancer không còn mang lại giá trị.

Quản lý chi phí compute cần kết hợp hai hoạt động: **lập lịch vòng đời tài nguyên** để chỉ chạy khi cần và **loại bỏ tài nguyên không còn sử dụng** sau khi xác minh dữ liệu, phụ thuộc và chủ sở hữu. Tắt VM không đồng nghĩa toàn bộ chi phí biến mất; xóa VM cũng không có nghĩa có thể xóa an toàn mọi disk hoặc snapshot liên quan. Bài học này trình bày cách lập lịch, kiểm tra, thu hồi và đo lường tiết kiệm mà vẫn bảo vệ khả năng phục hồi và yêu cầu vận hành.

## 1. Vì sao cần lập lịch và dọn dẹp tài nguyên?

Cloud giúp tạo compute nhanh, nhưng việc cấp phát dễ dàng cũng khiến tài nguyên tồn tại lâu hơn nhu cầu ban đầu. Các tình huống thường gặp:

- VM development hoặc test chạy cả đêm và cuối tuần dù không có ai sử dụng.
- Instance được tạo tạm để benchmark, migration hoặc xử lý incident nhưng không được thu hồi.
- Autoscaling group có minimum capacity cao hơn nhu cầu ngoài giờ.
- Disk, snapshot, image và backup tiếp tục được giữ sau khi workload đã xóa.
- Public IP, load balancer, NAT gateway hoặc địa chỉ tĩnh không còn gắn với dịch vụ.
- Node pool hoặc cluster test vẫn hoạt động sau khi dự án kết thúc.
- Tài nguyên được tạo thủ công ngoài quy trình IaC nên không có owner hoặc ngày hết hạn.

Lập lịch tắt/mở có thể giảm giờ compute tính phí. Dọn dẹp tài nguyên orphan có thể giảm chi phí storage, network và dịch vụ phụ trợ. Hai hoạt động cần phối hợp với lịch làm việc, SLA, backup, patching và quy trình khôi phục.

## 2. Phân loại tài nguyên trước khi tự động hóa

Không nên áp dụng cùng một chính sách cho mọi tài nguyên. Hãy phân loại theo môi trường, mức độ quan trọng, khả năng tái tạo và trạng thái dữ liệu.

| Nhóm | Ví dụ | Chính sách thường cân nhắc |
|---|---|---|
| Development | VM lập trình, database sandbox, môi trường tích hợp | Tắt ngoài giờ; mở lại theo lịch hoặc theo yêu cầu |
| Test/QA | Test runner, staging tạm, môi trường kiểm thử hiệu năng | Lập lịch theo ca kiểm thử; tự thu hồi sau TTL |
| Demo/training | Lab VM, cluster workshop, sandbox học tập | Tắt khi hết buổi; xóa theo ngày hết hạn |
| Production stateless | Web/API worker có thể tái tạo | Autoscaling theo tải; chỉ scale-in theo chính sách |
| Production stateful | Database, file server, node giữ dữ liệu cục bộ | Không tự động tắt nếu chưa có quy trình HA/backup và phê duyệt |
| Batch/ephemeral | Job xử lý dữ liệu, build agent, worker ngắn hạn | Khởi tạo theo sự kiện; tự xóa sau khi hoàn tất |
| Shared platform | NAT, load balancer, registry, logging, cluster control plane | Quản lý theo owner nền tảng và dependency của nhiều workload |

Các câu hỏi cần trả lời cho mỗi tài nguyên:

- Ai sở hữu và ai chịu trách nhiệm chi phí?
- Workload nào phụ thuộc vào nó?
- Có chứa dữ liệu cần giữ hay không?
- Có thể tạo lại từ image/IaC hay không?
- Thời gian cần để khởi động và trở lại phục vụ là bao lâu?
- Có yêu cầu SLA, RTO, RPO hoặc lịch bảo trì không?
- Tài nguyên có bị ràng buộc bởi license, compliance hoặc retention không?

## 3. Tắt, dừng, hibernate và xóa khác nhau thế nào?

Các cloud provider có thể dùng thuật ngữ và hành vi khác nhau. Cần hiểu trạng thái thực tế của từng loại tài nguyên.

| Hành động | Compute capacity | Disk/data | Địa chỉ và dịch vụ phụ trợ | Khả năng phục hồi |
|---|---|---|---|---|
| Stop/deallocate VM | Thường ngừng tính phí compute khi đã dừng đúng trạng thái | Disk thường vẫn tồn tại và tiếp tục tính phí | IP, license, backup hoặc dịch vụ gắn kèm có thể vẫn tính phí | Có thể start lại, nhưng IP hoặc host placement có thể thay đổi tùy nền tảng |
| Hibernate | Compute tạm dừng, trạng thái memory có thể được lưu theo dịch vụ | Disk và vùng lưu trạng thái tiếp tục tồn tại | Có thể có phí lưu trạng thái và disk | Resume nhanh hơn boot đầy đủ trong trường hợp hỗ trợ |
| Scale to zero | Số replica/worker về 0 | Storage dùng chung có thể vẫn tồn tại | Một số endpoint và control plane vẫn tính phí | Khởi tạo lại khi có nhu cầu, có thể có cold start |
| Terminate/delete VM | Compute bị xóa | Disk có thể bị xóa hoặc giữ lại tùy chính sách | IP, NIC, load balancer và snapshot có thể còn | Phải tạo instance mới hoặc restore từ backup/image |
| Delete resource | Tài nguyên được loại bỏ | Dữ liệu có thể mất vĩnh viễn nếu không còn bản sao | Dependency có thể bị ảnh hưởng | Chỉ phục hồi được nếu còn backup hoặc artifact cần thiết |

Không nên dùng từ stop như thể nó luôn có nghĩa là không còn chi phí. Ví dụ, disk persistent, snapshot, reserved capacity, static IP, license hoặc dịch vụ quản lý có thể tiếp tục được tính phí. Kiểm tra trạng thái billing của từng dịch vụ và hóa đơn thực tế.

## 4. Thiết kế lịch tắt/mở theo nhu cầu

Một lịch tốt phản ánh thời điểm workload thực sự cần hoạt động, có buffer cho khởi động và có ngoại lệ rõ ràng.

Ví dụ:

| Môi trường | Giờ hoạt động minh họa | Chính sách |
|---|---|---|
| Developer sandbox | Thứ Hai–Thứ Sáu, 08:00–19:00 | Start trước giờ làm; stop sau giờ kết thúc |
| QA shared | Theo lịch test đã đăng ký | Chạy theo booking; tự stop sau thời gian gia hạn |
| Training lab | Theo buổi học | Start trước buổi; stop khi kết thúc |
| Performance test | Theo cửa sổ benchmark | Chỉ start khi có người phụ trách; giữ log kết quả rồi stop |
| Production API | 24/7 hoặc theo SLO | Không dùng lịch tắt cứng; dùng autoscaling và capacity policy |
| Batch worker | Theo lịch job hoặc queue | Scale theo backlog; scale về 0 khi không có việc nếu hệ thống hỗ trợ |

Lịch trên chỉ là ví dụ. Cần dùng timezone của nhóm vận hành, xử lý ngày nghỉ và daylight saving nếu có. Với workload phục vụ người dùng ở nhiều quốc gia, lịch địa phương của một nhóm không nên vô tình tắt dịch vụ toàn cầu.

### 4.1. Thời gian đệm khi mở máy

Nếu người dùng bắt đầu làm việc lúc 09:00, không nhất thiết start VM đúng 09:00. Cần tính thời gian:

- VM provisioning hoặc deallocation-to-running.
- Boot OS, mount disk và cấu hình network.
- Cloud-init/startup script hoặc extension.
- Khởi động database/cache phụ trợ.
- Kết nối secret manager, service discovery và dependency.
- Health check và readiness.
- Warm-up ứng dụng, JIT và cache.

Hãy đo p50/p95 thời gian startup và thêm buffer phù hợp. Với môi trường cần sẵn sàng đúng giờ, có thể start sớm hơn hoặc dùng warm pool.

### 4.2. Thời gian đệm khi tắt

Không nên stop ngay khi hết giờ nếu còn người dùng, session, job hoặc dữ liệu chưa flush. Có thể:

1. Gửi thông báo sắp tắt.
2. Ngừng nhận workload mới.
3. Drain request và worker.
4. Chờ job kết thúc hoặc checkpoint.
5. Xác minh backup/snapshot nếu chính sách yêu cầu.
6. Stop/deallocate instance.
7. Kiểm tra trạng thái cuối và ghi nhận kết quả.

Nếu có người dùng đang làm việc, cho phép gia hạn có giới hạn và ghi lại owner, lý do, thời gian hết hạn mới.

## 5. Dùng tag để quản lý lịch và quyền thu hồi

Automation cần biết tài nguyên nào được phép tự động stop hoặc delete. Tag giúp mô tả owner, môi trường, lịch và ngày hết hạn.

Một bộ tag tham khảo:

| Tag | Ví dụ | Mục đích |
|---|---|---|
| Environment | dev, test, staging, prod | Phân biệt môi trường |
| Owner | team-platform | Nhóm chịu trách nhiệm |
| CostCenter | CC-204 | Phân bổ chi phí |
| Schedule | office-hours-vn | Ánh xạ tới lịch đã duyệt |
| AutoStop | true | Cho phép automation stop |
| AutoDelete | false | Có cho phép xóa tự động hay không |
| ExpiresAt | 2026-12-01T00:00:00Z | Hạn dùng của tài nguyên tạm |
| DataClass | public, internal, restricted | Hỗ trợ quyết định lưu giữ |
| ManagedBy | terraform, platform-scheduler | Nguồn quản lý vòng đời |

Tag không phải cơ chế bảo mật độc lập. Người có quyền sửa tag có thể cố tình đánh dấu tài nguyên production thành dev hoặc bật AutoDelete. Hãy giới hạn quyền sửa tag, dùng policy kiểm tra và đối chiếu với account/project, resource type cùng inventory.

## 6. Lập lịch stop/start bằng automation

Có thể dùng scheduler, automation service, function hoặc workflow để thực hiện lịch. Kiến trúc chung:

1. Scheduler phát sự kiện theo timezone và lịch đã cấu hình.
2. Automation tìm tài nguyên có tag schedule phù hợp.
3. Policy kiểm tra môi trường, trạng thái, owner và ngoại lệ.
4. Với stop, workload được drain hoặc chạy pre-stop action.
5. Automation gọi API stop/deallocate.
6. Hệ thống kiểm tra trạng thái cuối và ghi log.
7. Khi tới giờ start, automation start tài nguyên.
8. Health check xác nhận dịch vụ sẵn sàng và gửi thông báo nếu lỗi.

~~~mermaid
flowchart TD
    A[Scheduler / lịch đã duyệt] --> B[Automation workflow]
    B --> C[Đọc inventory và tag]
    C --> D{Tài nguyên đủ điều kiện?}
    D -- Không --> E[Bỏ qua và ghi lý do]
    D -- Có --> F[Kiểm tra dependency / ngoại lệ]
    F --> G{Hành động}
    G -- Stop --> H[Drain workload và flush]
    H --> I[Stop / deallocate]
    G -- Start --> J[Start VM / scale workload]
    I --> K[Xác minh trạng thái và ghi audit]
    J --> L[Health check / readiness]
    L --> K
~~~

Automation nên idempotent: chạy lại cùng một lịch không tạo lỗi hoặc hành động nguy hiểm. Ví dụ, nếu VM đã stopped thì stop lần nữa nên được xử lý như trạng thái đã đạt, không phải lỗi cần retry vô hạn.

### 6.1. Tránh phụ thuộc vào một scheduler duy nhất

Scheduler hoặc automation service cũng có thể gặp sự cố. Với workload quan trọng:

- Theo dõi lịch đã chạy và lịch bị bỏ lỡ.
- Ghi lại lần chạy gần nhất và kết quả.
- Có retry hữu hạn với backoff.
- Cảnh báo khi start/stop không đạt trạng thái mong muốn.
- Có runbook thao tác thủ công khi automation lỗi.
- Không để lịch stop chạy nếu policy hoặc dependency check không xác định được trạng thái an toàn.

## 7. Ví dụ công cụ theo nhà cung cấp

Tên dịch vụ và khả năng thay đổi theo thời gian, region và SKU; cần xác minh tài liệu của nền tảng trước khi triển khai.

| Nền tảng | Cơ chế thường dùng | Ứng dụng |
|---|---|---|
| AWS | Amazon EventBridge Scheduler, Systems Manager Automation, Lambda hoặc Instance Scheduler solution | Lập lịch start/stop EC2 theo tag và lịch |
| Azure | Azure Automation, Automation Runbooks, Logic Apps hoặc các giải pháp Start/Stop VM | Lập lịch start/deallocate VM và xử lý theo resource group/tag |
| Google Cloud | Cloud Scheduler kết hợp Cloud Functions/Cloud Run Jobs/Workflows và Compute Engine API | Gọi API start/stop instance theo lịch và label |

Không nên cấp quyền quản trị toàn account cho automation chỉ để stop vài VM. Tạo role riêng giới hạn resource/tag, action start/stop và phạm vi project/subscription/account. Nếu automation cần đọc inventory, chỉ cấp quyền đọc metadata cần thiết.

## 8. Lập lịch theo tag và ngoại lệ

Một lịch có thể áp dụng cho nhiều tài nguyên, nhưng cần cơ chế ngoại lệ.

Ví dụ chính sách:

- Chỉ tài nguyên Environment=dev hoặc test mới được xét.
- AutoStop=true là điều kiện bắt buộc.
- Environment=prod luôn bị loại khỏi lịch stop thông thường.
- Nếu có tag MaintenanceHold=true thì bỏ qua.
- Nếu có ExpiresAt trong quá khứ và AutoDelete=true, đưa vào quy trình thu hồi sau khi kiểm tra.
- Nếu owner không tồn tại hoặc tag thiếu, gửi cảnh báo và yêu cầu xác minh thay vì tự xóa.

Cần quy định thứ tự ưu tiên giữa tag và policy trung tâm. Ví dụ, tag do người dùng tự đặt không được phép vượt qua danh sách cấm stop của production.

### 8.1. Ngoại lệ tạm thời

Một nhóm có thể cần chạy benchmark ngoài giờ. Hãy hỗ trợ ngoại lệ có thời hạn:

- Owner và lý do.
- Tài nguyên được miễn lịch.
- Thời điểm bắt đầu và hết hạn.
- Người phê duyệt nếu môi trường cần kiểm soát.
- Tự động quay lại lịch chuẩn sau khi hết hạn.

Tránh ngoại lệ vô thời hạn. Nếu cần kéo dài, yêu cầu owner gia hạn để inventory luôn phản ánh nhu cầu thực.

## 9. Shutdown an toàn trước khi stop

Stop VM khi ứng dụng đang ghi dữ liệu có thể gây lỗi transaction, mất job hoặc filesystem recovery. Trước khi stop:

- Ngừng nhận request mới bằng readiness hoặc deregistration khỏi load balancer.
- Drain connection và request đang xử lý.
- Ngừng consumer nhận message mới.
- Chờ job hoàn tất hoặc checkpoint/requeue an toàn.
- Commit/rollback transaction theo quy trình database.
- Flush buffer và đóng file/socket.
- Xác minh backup hoặc snapshot theo chính sách.
- Dừng service bằng service manager hoặc cơ chế graceful shutdown.
- Kiểm tra trạng thái instance trước khi automation kết thúc.

Với VM production, lịch stop thường không phù hợp trừ khi dịch vụ được thiết kế để ngừng hoạt động theo giờ và có thông báo, failover, data consistency cùng SLA rõ ràng.

## 10. Start theo đúng thứ tự dependency

Khi mở lại môi trường, không phải lúc nào cũng start tất cả VM cùng lúc. Hãy xác định thứ tự dependency:

1. Network, VPN, private connectivity và DNS.
2. Storage hoặc volume cần thiết.
3. Database, cache hoặc message broker.
4. Identity/secret retrieval và service discovery.
5. Application backend và worker.
6. Load balancer registration và ingress.
7. Smoke test và thông báo sẵn sàng.

Nếu ứng dụng khởi động trước database, startup có thể thất bại hoặc tạo retry storm. Ứng dụng nên có retry có backoff, timeout và readiness phản ánh dependency thiết yếu.

Với hệ thống có nhiều thành phần, dùng workflow có dependency graph thay vì nhiều lịch độc lập dễ chạy sai thứ tự.

## 11. Tắt mở autoscaling group, node pool và cluster

Không nên chỉ dừng từng instance khi chúng được quản lý bởi autoscaling group hoặc cluster scheduler. Control plane có thể tự tạo lại instance hoặc đánh dấu node unhealthy.

Các lưu ý:

- Điều chỉnh desired/min/max capacity theo chính sách đã duyệt.
- Kiểm tra autoscaler, scheduled action và policy khác có thể ghi đè thay đổi.
- Drain node trước khi giảm desired capacity.
- Bảo đảm PodDisruptionBudget và capacity của node còn lại.
- Không giảm node cuối cùng nếu control plane hoặc service thiết yếu phụ thuộc vào nó.
- Khi scale từ 0, xác minh node bootstrap, image pull, secret và network.
- Với cluster managed, hiểu phần control plane hoặc phí quản lý có còn tính khi worker về 0 hay không.

Scale to zero phù hợp với workload chịu cold start và không yêu cầu luôn có replica. Với API cần phản hồi nhanh, có thể giữ một minimum replica hoặc warm capacity.

## 12. Xác định tài nguyên không còn sử dụng

Tài nguyên orphan là tài nguyên không còn được workload đang hoạt động sử dụng nhưng vẫn tồn tại và có thể phát sinh chi phí. Không nên kết luận chỉ dựa trên mức CPU thấp.

Các ví dụ:

- Disk không còn attach vào VM.
- Snapshot hoặc image cũ không còn thuộc quy trình backup/rollback.
- Public IP không còn gắn với endpoint.
- Load balancer không còn backend hoặc DNS record liên quan.
- NAT gateway không có traffic nhưng vẫn được giữ.
- NIC hoặc volume được tạo từ instance đã xóa.
- VM không có owner hoặc không có hoạt động trong thời gian dài.
- Container image/tag cũ không còn được deploy.
- Backup hoặc log archive vượt retention đã định.

Một tài nguyên ít hoạt động vẫn có thể cần thiết cho DR, compliance, warm standby hoặc dự phòng. Cần kiểm tra owner, dependency và mục đích trước khi đưa vào danh sách thu hồi.

## 13. Quy trình phát hiện orphan resource

Một quy trình an toàn gồm:

1. Thu thập inventory từ cloud account/project/subscription.
2. Chuẩn hóa resource ID, type, region, zone, owner và tag.
3. Đối chiếu quan hệ giữa VM, disk, NIC, IP, snapshot, load balancer và network.
4. Kiểm tra metric sử dụng, traffic, attachment và thời điểm hoạt động cuối.
5. So sánh với IaC state, deployment inventory hoặc CMDB nếu được phép.
6. Đánh dấu candidate và lý do vì sao bị nghi là orphan.
7. Thông báo owner và cho thời gian xác nhận.
8. Đặt tài nguyên vào trạng thái quarantine/retention nếu cần.
9. Chỉ xóa khi policy, owner và dependency check đạt.
10. Lưu audit, kết quả và cách khôi phục nếu xóa nhầm.

Không xóa chỉ vì một tài nguyên không có tag. Tài nguyên thiếu metadata nên được gắn nhãn unknown owner và chuyển cho quy trình xử lý, vì có thể là shared platform hoặc tài nguyên do dịch vụ managed tạo.

### 13.1. Dùng nhiều tín hiệu để xác định tài nguyên không dùng

| Tín hiệu | Điều có thể suy ra | Giới hạn |
|---|---|---|
| CPU/network thấp | Ít hoạt động gần đây | Có thể là standby hoặc workload chạy theo lịch |
| Không có attachment | Có thể là disk orphan | Có thể là volume chờ DR hoặc migration |
| Không có backend | Load balancer có thể không còn dùng | Có thể đang chuẩn bị blue/green deployment |
| Không có traffic | Endpoint có thể ít được dùng | Có thể là endpoint dự phòng |
| Không có owner tag | Metadata chưa đầy đủ | Không chứng minh tài nguyên vô chủ |
| Không nằm trong IaC state | Có thể được tạo thủ công hoặc bởi managed service | State có thể không đầy đủ hoặc đã drift |
| ExpiresAt quá hạn | Tài nguyên tạm có thể hết nhu cầu | Cần xác minh owner và dữ liệu trước khi xóa |

Sử dụng kết hợp nhiều tín hiệu và quy trình xác nhận. Không dùng một ngưỡng CPU hoặc một khoảng thời gian không hoạt động làm điều kiện xóa tự động.

## 14. Retention cho disk, snapshot, image và backup

Xóa tài nguyên compute có thể để lại dữ liệu và bản sao. Cần chính sách retention riêng:

- Boot disk và data disk: xác định có xóa khi terminate hay giữ lại.
- Snapshot: giữ số bản gần nhất hoặc theo lịch và yêu cầu khôi phục.
- Machine image: giữ phiên bản đang triển khai, phiên bản rollback và image được phê duyệt.
- Backup: tuân thủ RPO/RTO, retention và yêu cầu pháp lý.
- Log: giữ đủ lâu cho điều tra, audit và chính sách dữ liệu.
- Container image: giữ tag đang deploy và bản phát hành cần rollback.

Trước khi xóa, xác minh backup có thể restore và dữ liệu có tính nhất quán. Một snapshot tồn tại không đồng nghĩa backup đã được kiểm thử. Với database, cần backup theo cơ chế nhất quán của engine và thử restore định kỳ.

## 15. Quy trình thu hồi tài nguyên theo nhiều giai đoạn

Để giảm rủi ro xóa nhầm, dùng quy trình hai hoặc ba giai đoạn.

**Giai đoạn 1 — Discover:** tìm candidate, thu thập metadata, metric, dependency và chi phí ước tính.

**Giai đoạn 2 — Notify/quarantine:** thông báo owner, gắn tag pending-delete, ngừng lịch start nếu phù hợp và chờ thời hạn phản hồi. Với disk hoặc IP, có thể tách khỏi workload chỉ khi đã xác nhận an toàn.

**Giai đoạn 3 — Delete:** kiểm tra lại attachment, snapshot, backup, policy và approval; sau đó xóa bằng automation có audit.

~~~mermaid
flowchart TD
    A[Inventory scan] --> B[Candidate orphan]
    B --> C[Kiểm tra owner và dependency]
    C --> D{Có thể thu hồi?}
    D -- Chưa rõ --> E[Giữ lại / yêu cầu owner xác minh]
    D -- Có --> F[Notify và quarantine]
    F --> G[Hết thời hạn xác nhận]
    G --> H[Recheck attachment, backup, policy]
    H --> I{Đủ điều kiện xóa?}
    I -- Không --> E
    I -- Có --> J[Delete và ghi audit]
    J --> K[Kiểm tra chi phí sau thu hồi]
~~~

Nếu owner xác nhận tài nguyên vẫn cần, cập nhật tag, owner và expiration mới để tránh lặp lại cảnh báo. Nếu không có phản hồi, chỉ xóa theo policy đã công bố và phạm vi tài nguyên được phép.

## 16. Guardrail và quyền automation

Automation có thể gây ảnh hưởng rộng nếu role được cấp quyền quá lớn hoặc selector tag sai. Cần thiết kế guardrail trước khi bật chế độ tự động.

- Tách quyền đọc inventory khỏi quyền stop/delete.
- Tạo role riêng cho lịch stop và quy trình delete.
- Giới hạn action theo resource type và project/account.
- Cấm tự động delete production, database hoặc resource có DataClass restricted nếu chưa có phê duyệt riêng.
- Dùng allowlist các môi trường được phép auto-stop.
- Yêu cầu AutoDelete và ExpiresAt cùng hợp lệ trước khi xóa.
- Bắt buộc owner tag và cost center cho tài nguyên mới.
- Dùng dry-run trước khi bật enforcement.
- Ghi log đầy đủ: selector, resource ID, policy, actor, thời gian và kết quả.
- Có cơ chế pause toàn bộ scheduler khi phát hiện hành động bất thường.
- Dùng rate limit hoặc batch nhỏ để tránh xóa nhầm hàng loạt.

Quyền stop và quyền delete nên tách riêng. Stop thường có thể đảo ngược bằng start; delete có thể mất dữ liệu và cần quy trình chặt chẽ hơn.

## 17. Ví dụ chính sách cho môi trường development

Giả sử nhóm phát triển có nhiều VM sandbox. Quy tắc đề xuất:

- Mọi VM dev phải có Owner, CostCenter và Schedule.
- VM có AutoStop=true sẽ dừng lúc 19:00 theo giờ Việt Nam từ thứ Hai tới thứ Sáu.
- VM được mở lại lúc 08:00 ngày làm việc tiếp theo.
- Ngày nghỉ áp dụng lịch riêng.
- Owner có thể đặt MaintenanceHold=true tối đa 24 giờ với lý do.
- VM tạm phải có ExpiresAt; automation cảnh báo trước khi hết hạn.
- AutoDelete mặc định false. Sau khi owner xác nhận dữ liệu không cần giữ, tài nguyên được đưa vào quarantine trước khi xóa.
- Disk và snapshot được đánh giá riêng theo retention.
- VM không có owner được báo cáo và gắn trạng thái cần xác minh, không tự xóa.

Một lịch minh họa:

| Thời điểm | Hành động | Kiểm tra |
|---|---|---|
| 07:45 ngày làm việc | Start VM | Trạng thái running và network hoạt động |
| 08:00 | Health check | SSH/RDP hoặc agent quản trị sẵn sàng |
| 18:45 | Thông báo sắp stop | Kiểm tra session và job |
| 18:55 | Drain | Không nhận việc mới, job được xử lý |
| 19:00 | Stop/deallocate | Xác minh trạng thái stopped |
| Hàng tuần | Inventory orphan scan | Gửi danh sách candidate cho owner |
| Hàng tháng | Retention review | Kiểm tra disk, snapshot và image cũ |

Thời gian chỉ mang tính minh họa. Nhóm cần điều chỉnh theo timezone, ngày nghỉ, thời gian startup và chính sách làm việc thực tế.

## 18. Đo lường mức tiết kiệm

Không nên chỉ báo cáo số VM đã tắt. Hãy đo chi phí trước và sau, đồng thời kiểm tra ảnh hưởng vận hành.

Các chỉ số hữu ích:

- Compute hours đã loại bỏ.
- Chi phí compute trước/sau theo environment và owner.
- Tỷ lệ tài nguyên được stop đúng lịch.
- Tỷ lệ start thành công đúng giờ.
- Số lần người dùng phải yêu cầu mở lại ngoài lịch.
- Số job bị gián đoạn hoặc thất bại do stop.
- Số orphan candidate được xác nhận và thu hồi.
- Chi phí disk, snapshot, IP, NAT và load balancer đã giảm.
- Tỷ lệ tài nguyên thiếu owner/expiration.
- Số lần automation skip do policy hoặc dependency check.

### 18.1. Công thức ước tính tiết kiệm compute

Nếu một instance có đơn giá compute theo giờ là P và được tắt trong H giờ không cần dùng:

\[
Savings_{compute} \approx P \times H
\]

Với nhiều instance:

\[
Savings_{gross} = \sum_i P_i \times H_i
\]

Tiết kiệm thực tế cần trừ chi phí automation, lưu disk/backup, địa chỉ IP hoặc license còn tính khi stopped, cũng như chi phí khởi động và vận hành bổ sung.

\[
Savings_{net} = Savings_{gross} - C_{remaining} - C_{automation}
\]

Công thức là ước tính. Billing có thể có mức tối thiểu, đơn vị làm tròn, commitment discount hoặc thành phần phí khác. Nên đối chiếu với cost export hoặc invoice.

### 18.2. Ví dụ tính toán

Giả sử một VM development có giá compute minh họa 0,12 USD/giờ. VM chỉ cần hoạt động 10 giờ mỗi ngày trong 5 ngày làm việc. Nếu trước đó VM chạy 24 giờ mỗi ngày, số giờ có thể dừng trong tuần là:

\[
H = (24 - 10) \times 5 = 70\text{ giờ}
\]

Tiết kiệm compute gross mỗi tuần:

\[
0.12 \times 70 = 8.40\text{ USD}
\]

Nếu còn 1,50 USD/tuần chi phí disk và dịch vụ phụ trợ, tiết kiệm net ước tính là 6,90 USD/tuần trước khi tính chi phí automation và các discount liên quan. Giá chỉ là ví dụ, không phải bảng giá cloud thực tế.

## 19. Những lỗi thường gặp

**Tắt mọi VM ngoài giờ mà không phân loại.** Có thể dừng database, worker hoặc dịch vụ dùng chung. Hãy dùng allowlist môi trường và dependency check.

**Cho rằng stop VM là hết chi phí.** Disk, snapshot, IP, license hoặc dịch vụ quản lý có thể tiếp tục tính phí. Đối chiếu từng resource meter.

**Xóa disk ngay sau khi VM bị terminate.** Disk có thể chứa dữ liệu duy nhất. Kiểm tra owner, backup và restore trước khi xóa.

**Dùng tag làm nguồn tin duy nhất.** Tag có thể thiếu hoặc bị sửa. Kết hợp account, resource type, IaC, inventory và dependency.

**Lập lịch start quá sát giờ làm.** VM có thể chưa boot hoặc ứng dụng chưa ready. Đo startup time và thêm buffer.

**Stop khi job đang chạy.** Có thể gây mất message hoặc transaction dở dang. Drain, checkpoint hoặc requeue trước khi dừng.

**Automation retry vô hạn.** Có thể tạo API storm hoặc liên tục tác động trạng thái. Dùng retry hữu hạn, idempotency và cảnh báo.

**Xóa orphan ngay sau một lần scan.** Metric có thể thấp do workload theo mùa hoặc standby. Dùng quarantine và thời hạn xác minh.

**Không theo dõi kết quả.** Lịch có thể chạy nhưng VM start thất bại hoặc bị automation khác bật lại. Ghi audit và giám sát trạng thái thực.

## 20. Checklist triển khai lịch tắt/mở và dọn dẹp

- [ ] Đã phân loại tài nguyên theo môi trường, owner, stateful/stateless và criticality.
- [ ] Đã xác định giờ hoạt động, timezone, ngày nghỉ và ngoại lệ.
- [ ] Đã đo startup time và đặt buffer trước giờ cần sẵn sàng.
- [ ] Có drain, graceful shutdown, checkpoint và xử lý job trước khi stop.
- [ ] Đã xác minh stop/deallocate có ngừng tính compute và những phí nào còn lại.
- [ ] Scheduler chạy idempotent, có retry hữu hạn, audit và cảnh báo.
- [ ] Tag owner, environment, schedule, AutoStop, AutoDelete và ExpiresAt được chuẩn hóa.
- [ ] Production và stateful resource được bảo vệ bằng policy riêng.
- [ ] Autoscaling group/node pool được điều chỉnh qua control plane đúng cách.
- [ ] Inventory scan kiểm tra attachment, dependency, traffic và IaC ownership.
- [ ] Candidate orphan được quarantine và owner có thời gian xác nhận.
- [ ] Backup, snapshot, image và retention được kiểm tra trước khi xóa.
- [ ] Quyền stop và delete được tách riêng, giới hạn theo resource scope.
- [ ] Đã chạy dry-run và kiểm tra selector trước khi bật enforcement.
- [ ] Có quy trình pause/rollback khi automation gây tác động ngoài dự kiến.
- [ ] Đã đo compute hours, chi phí net và ảnh hưởng tới SLO/người dùng.

## 21. Kết luận

Lập lịch tắt/mở giúp giảm giờ compute nhàn rỗi ở môi trường development, test, lab và workload có lịch rõ ràng. Dọn dẹp tài nguyên orphan giảm thêm chi phí disk, snapshot, IP, NAT, load balancer và dịch vụ phụ trợ. Muốn thực hiện an toàn, cần phân loại tài nguyên, gắn owner và expiration, kiểm tra dependency, drain workload trước stop và xác minh dữ liệu trước delete.

Hãy bắt đầu bằng dry-run và lịch cho môi trường ít rủi ro, đo startup/shutdown time, theo dõi kết quả và mở rộng dần. Tách quyền stop khỏi delete, dùng quarantine cho candidate orphan và đối chiếu mức tiết kiệm với billing thực tế. Khi vòng đời tài nguyên có owner, lịch và điều kiện thu hồi rõ ràng, chi phí compute giảm mà khả năng phục hồi và vận hành vẫn được kiểm soát.
