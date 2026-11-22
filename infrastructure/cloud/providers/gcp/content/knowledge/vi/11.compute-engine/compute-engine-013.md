# Suspend, resume, stop và xóa VM an toàn trên Compute Engine

> **Chương:** Compute Engine  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Một máy ảo Compute Engine chạy ứng dụng Java có thể cần tạm nghỉ ngoài giờ, dừng để bảo trì, tiếp tục sau vài ngày hoặc được loại bỏ khi đã chuyển workload sang Cloud Run hay GKE. Bốn thao tác **suspend, resume, stop và delete** trông giống những nút quản lý đơn giản, nhưng hậu quả rất khác nhau với **RAM, disk, Local SSD, IP, trạng thái hệ điều hành, SLA, khả năng khôi phục và chi phí**.

Điều quan trọng không phải là biết chạy một lệnh, mà là chọn **hành động đúng với dữ liệu và mục tiêu nghiệp vụ**, dự đoán những tài nguyên được giữ hoặc bị giải phóng, rồi kiểm tra kết quả. Bài học này hướng dẫn cách thiết kế runbook an toàn trước khi tác động lên VM thật.

## Mục tiêu học tập

Sau bài, người học có thể:

1. Phân biệt **RUNNING, SUSPENDING, SUSPENDED, STOPPING, TERMINATED** và thao tác start/resume/delete.
2. Giải thích chính xác phần nào của VM được giữ khi **suspend** so với **stop**, và điều gì có nguy cơ mất khi **delete**.
3. Hiểu các giới hạn suspend như **60 ngày**, loại VM không hỗ trợ, tài nguyên vùng và xử lý Local SSD.
4. Kiểm kê boot disk, data disk, autoDelete, snapshot, backup, external IP, service account, network và các phụ thuộc trước thay đổi.
5. Thực hành các lệnh **gcloud** chỉ đọc và các mẫu lệnh có kiểm soát để suspend/resume/stop/start/delete.
6. Thiết kế quy trình **graceful shutdown, backup, kiểm thử phục hồi, phê duyệt và xác minh sau thao tác**.
7. Phân tích ảnh hưởng lên **Managed Instance Group (MIG)**, GKE nodes, Cloud Load Balancing, IAM, Cloud Monitoring và hóa đơn.

## 1. Hiểu vòng đời của Compute Engine VM

Máy ảo là một tài nguyên Compute Engine gắn với **project và zone**, có machine type, boot disk, các disk bổ sung, giao diện mạng, service account, metadata và những thuộc tính khác. VM thường trải qua các trạng thái như:

| Trạng thái | Ý nghĩa thực tế |
|---|---|
| **PROVISIONING** | Compute Engine đang chuẩn bị tài nguyên |
| **STAGING** | Đang chuẩn bị để khởi chạy VM |
| **RUNNING** | VM đang chạy, có thể phục vụ workload nếu OS/ứng dụng sẵn sàng |
| **SUSPENDING** | Đang lưu trạng thái RAM, thiết bị và ứng dụng để suspend |
| **SUSPENDED** | Đã tạm ngưng, trạng thái RAM được lưu, không tiếp tục xử lý request |
| **STOPPING** | Đang dừng hoặc shutdown |
| **TERMINATED** | VM đã dừng, vẫn còn tài nguyên VM để có thể start lại nếu được hỗ trợ |
| **REPAIRING** | Nền tảng đang xử lý một tác vụ sửa chữa; thao tác lifecycle có thể bị giới hạn |

**TERMINATED** là trạng thái VM **đã stop**, không đồng nghĩa tài nguyên đã được **delete**. Khi delete hoàn tất, VM không còn tồn tại để describe/start theo tên đó.

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING: Create
    PROVISIONING --> STAGING
    STAGING --> RUNNING
    RUNNING --> SUSPENDING: Suspend
    SUSPENDING --> SUSPENDED
    SUSPENDED --> PROVISIONING: Resume
    RUNNING --> STOPPING: Stop
    STOPPING --> TERMINATED
    TERMINATED --> PROVISIONING: Start
    SUSPENDED --> TERMINATED: Sau tối đa 60 ngày
    RUNNING --> [*]: Delete
    SUSPENDED --> [*]: Delete
    TERMINATED --> [*]: Delete
~~~

Sơ đồ lược giản các trạng thái chính; quá trình start/resume còn có thể đi qua STAGING và các trạng thái chuyển tiếp. Tình trạng **RUNNING** không tự chứng minh ứng dụng đã sẵn sàng: một JVM có thể vẫn đang khởi động, chờ database hoặc bị health check đánh dấu unhealthy.

### 1.1. Các thao tác không đồng nghĩa với nhau

- **Suspend:** giữ RAM và trạng thái thiết bị/ứng dụng bằng cách lưu vào persistent storage, rồi giải phóng tài nguyên compute.
- **Resume:** đưa VM **SUSPENDED** trở lại trạng thái chạy, khôi phục RAM từ dữ liệu đã lưu khi còn hợp lệ và có tài nguyên vùng.
- **Stop:** shutdown VM, **không bảo toàn trạng thái RAM** để tiếp tục từ vị trí cũ; cấu hình VM và các persistent disks vẫn có thể được giữ.
- **Start:** khởi động VM ở trạng thái **TERMINATED**, thực hiện boot OS/ứng dụng lại.
- **Delete:** xóa tài nguyên VM; các disk và tài nguyên phụ thuộc có được giữ hay không phụ thuộc cấu hình và tham số xóa.
- **Reset:** giống nhấn nút reset cứng, không phải stop có bảo toàn dữ liệu chưa ghi; có rủi ro mất dữ liệu đang ở bộ nhớ.
- **Reboot từ guest OS:** khởi động lại bên trong hệ điều hành; không được coi như thao tác suspend của Compute Engine.

Để **suspend**, không dùng lệnh **systemctl suspend** trong guest OS rồi mong Compute Engine quản lý trạng thái đó. Dùng API, console hoặc **gcloud compute instances suspend** theo cơ chế nền tảng hỗ trợ.

## 2. Chọn Suspend, Stop hay Delete?

| Nhu cầu | Hành động phù hợp | Vì sao |
|---|---|---|
| Tạm nghỉ desktop/dev VM qua đêm, muốn giữ phiên ứng dụng/RAM | **Suspend**, nếu VM đủ điều kiện | Có thể tiếp tục công việc gần trạng thái trước |
| Tắt VM test ngoài giờ, có thể boot lại bình thường | **Stop** | Không cần tốn chỗ lưu trạng thái RAM |
| Thay machine type hoặc bảo trì cần shutdown | **Stop → update → Start**, nếu loại VM cho phép | Một số thay đổi cần VM dừng |
| VM ngừng sử dụng nhưng muốn giữ dữ liệu và cấu hình phục vụ kiểm tra | **Stop** trước khi cân nhắc delete | Cho phép đánh giá phụ thuộc và hồi phục |
| Không còn nhu cầu VM nhưng phải lưu dữ liệu | **Backup/snapshot + Delete VM với disk retention được chọn** | Xóa compute nhưng không xóa nhầm dữ liệu |
| Hết vòng đời, dữ liệu đã được xử lý theo chính sách lưu giữ | **Delete** sau phê duyệt | Loại bỏ VM và tài nguyên liên quan có kiểm soát |
| JVM bị treo, cần cứu dịch vụ | **Đánh giá ứng dụng → graceful restart/stop → reset chỉ khi cần** | Reset không phải phương án an toàn đầu tiên |
| Workload chạy trong Managed Instance Group | **Thao tác qua MIG/desired state** | MIG có thể tạo lại VM bị xóa hoặc thay đổi |
| GKE node trong node pool | **Quản lý qua GKE**, không tùy tiện stop/delete VM node | Hệ thống Kubernetes/GKE có controller riêng |

**Không có thao tác nào tối ưu cho mọi tiêu chí.** Suspend có thể giữ phiên ứng dụng nhưng không bảo đảm không mất kết nối mạng, không bảo đảm resume được ngay hoặc ứng dụng không cần reconnect đến database. Stop tiết kiệm trạng thái compute mà không cần lưu RAM, nhưng ứng dụng phải boot lại. Delete chỉ an toàn khi đã hiểu chính sách disk và phụ thuộc.

## 3. Dữ liệu nào được giữ, dữ liệu nào có thể mất?

### 3.1. RAM, device state và application state

Khi suspend được hỗ trợ, Compute Engine lưu **guest OS memory, device state và application state** vào persistent storage để sử dụng khi resume. Đây là điểm khác biệt chính với stop.

Sau **stop/start**, chương trình sẽ boot lại. Session trong bộ nhớ JVM, cache chỉ ở RAM, queue tạm trong process và transaction chưa được ghi bền vững có thể không còn. Vì vậy ứng dụng Java cần có shutdown hook, cơ chế xử lý lại job an toàn, connection retry và lưu state cần thiết xuống kho bền vững.

Sau **suspend/resume**, RAM có thể khôi phục, nhưng **external connections, DNS cache, token hết hạn, session TLS hoặc connection pool cũ** vẫn có thể không hợp lệ. Không giả định resume là tiếp tục mọi hoạt động mạng mà không cần tái kết nối.

### 3.2. Boot disk và data disks

Boot disk thường là Persistent Disk hoặc Hyperdisk được Compute Engine hỗ trợ theo machine family; có thể có các persistent data disks. Khi **stop hoặc suspend**, các disk bền vững gắn với VM thường vẫn tồn tại và tiếp tục phát sinh phí lưu trữ.

Khi **delete**, mỗi disk có thuộc tính **autoDelete** hoặc tùy chọn keep/delete tại thời điểm xóa. Mặc định thường gặp là **boot disk có autoDelete=true**, nghĩa là disk có thể bị xóa cùng VM. Data disk phải được **kiểm tra riêng từng cái**, không suy từ boot disk hoặc từ tên “data”.

| Loại lưu trữ | Suspend | Stop | Delete VM |
|---|---|---|---|
| **Persistent boot disk** | Thường giữ | Thường giữ | Có thể **bị xóa** theo autoDelete/tùy chọn delete |
| **Persistent data disk** | Thường giữ | Thường giữ | Phụ thuộc autoDelete/tùy chọn keep/delete |
| **RAM/thiết bị/ứng dụng** | Được lưu cho resume khi hỗ trợ | Không được bảo toàn | Không còn |
| **Local SSD** | Mặc định dữ liệu bị bỏ; có tùy chọn preserve giới hạn/pre-GA | Mặc định dữ liệu bị bỏ; có tùy chọn preserve giới hạn/pre-GA | Không giữ độc lập khi xóa VM |
| **Snapshot/backup đã tạo riêng** | Không bị thay bởi thao tác suspend | Không bị thay bởi thao tác stop | Có thể tồn tại độc lập theo chính sách retention |

**Snapshot không đồng nhất với backup hoàn chỉnh:** snapshot một disk không tự bảo đảm các transaction qua nhiều disk/database ở trạng thái nhất quán nếu không có quiesce, freeze hoặc cơ chế backup application-consistent. Với database production, nên dùng backup gốc của database/dịch vụ và diễn tập phục hồi.

### 3.3. Local SSD là tình huống có rủi ro cao

**Local SSD** có hiệu năng cao nhưng dữ liệu gắn với vòng đời host/VM và **không phải persistent disk**. Theo tài liệu hiện hành:

- **Stop hoặc suspend mặc định sẽ bỏ dữ liệu Local SSD**, và khi VM chạy lại Local SSD có thể trống.
- Có **tùy chọn lưu dữ liệu Local SSD khi stop/suspend** ở một số tình huống, nhưng là tính năng **Preview/pre-GA**, chịu giới hạn về loại ổ, số ổ và phương thức thao tác.
- Không được dựa vào khả năng preserve mặc định của Google Cloud console; một số cách bảo toàn chỉ thực hiện bằng gcloud/API với cờ cụ thể.
- **Titanium SSD** và các cấu hình không được hỗ trợ có ràng buộc riêng; phải đọc tài liệu của machine family.
- Nếu dữ liệu Local SSD là quan trọng, **di chuyển/sao lưu sang persistent storage trước** khi thực hiện stop, suspend hoặc delete.

Không để dữ liệu ứng dụng không thể tái tạo chỉ nằm trên Local SSD rồi dựa vào một cờ Preview làm phương án recovery duy nhất.

### 3.4. IP, network và service account

Với stop/suspend, VM có thể giữ cấu hình network interface, MAC, internal IP và các **static external IP** đã gắn theo điều kiện hỗ trợ; **ephemeral external IP có thể bị giải phóng**.

Hệ quả thực tế:

- Sau resume/start, public endpoint có thể đổi nếu trước đó dùng ephemeral external IP.
- Nếu ứng dụng phụ thuộc IP cố định, cân nhắc reserved static IP hoặc load balancer/DNS có cơ chế thay đổi an toàn.
- Dù một địa chỉ static IP được giữ, nó có thể **tiếp tục bị tính phí**.
- Dùng labels, network tags và service account đúng phạm vi; quyền truy cập sau khi VM chạy lại vẫn chịu IAM/firewall hiện tại.
- Nếu VM đang là backend của load balancer, backend có thể bị đánh dấu unhealthy khi VM không RUNNING.

### 3.5. Tóm tắt khả năng giữ lại

| Đặc điểm | Suspend/Resume | Stop/Start | Delete |
|---|---|---|---|
| VM resource/name/config | Giữ | Giữ | Xóa |
| RAM/application state | Giữ có điều kiện và thời hạn | Không giữ | Mất |
| Persistent disks | Thường giữ và tính phí | Thường giữ và tính phí | Cần quyết định keep/delete |
| Local SSD contents | Mặc định không giữ; Preview có điều kiện | Mặc định không giữ; Preview có điều kiện | Không giữ |
| Ephemeral external IP | Có thể giải phóng | Có thể giải phóng | Giải phóng theo cấu hình |
| Static external IP | Có thể tiếp tục gắn/tính phí | Có thể tiếp tục gắn/tính phí | Kiểm tra xem đã được giải phóng/chuyển dùng |
| VM vCPU/memory running charges | Dừng sau khi suspend hoàn tất | Dừng sau khi stop hoàn tất | Dừng sau khi delete |
| Storage cho trạng thái RAM | Có thể phát sinh | Không cần loại dữ liệu suspend này | Không còn nếu state đã mất |
| Khởi động lại workload | Phải kiểm tra ứng dụng sau resume | Boot OS và ứng dụng từ đầu | Tạo VM mới/restore nếu cần |
| Có thể quay lại? | Resume trong cửa sổ hợp lệ | Start khi còn resource/config | Không có nút undo VM delete; cần phương án rebuild/restore |

## 4. Suspend có giới hạn và không phải một bản backup

### 4.1. Quy tắc tối đa 60 ngày

Một VM có thể ở trạng thái **SUSPENDED tối đa 60 ngày**. Sau đó Compute Engine chuyển VM sang **TERMINATED**; **trạng thái RAM, thiết bị và ứng dụng đã lưu sẽ không còn để resume**. Dữ liệu trên persistent disks vẫn chịu cơ chế của disk, nhưng bạn phải **start** và boot ứng dụng như sau stop.

Vì vậy:

- Suspend không phù hợp để “lưu một desktop đang mở trong sáu tháng”.
- Nếu cần giữ phiên ứng dụng dài hạn, thiết kế lưu state vào cơ sở dữ liệu/kho bền vững hoặc snapshot phù hợp.
- Cần một lịch theo dõi những VM sắp chạm ngưỡng; không để chuyển trạng thái ngoài dự kiến rồi kỳ vọng RAM còn nguyên.

### 4.2. Các VM không hỗ trợ hoặc có điều kiện riêng

Tùy phiên bản dịch vụ và machine/OS, suspend có thể bị từ chối. Theo tài liệu Google Cloud, các trường hợp đáng chú ý gồm:

- **Bare metal instances**.
- **Confidential VMs**.
- VM có **GPU hoặc TPU**.
- VM có **hơn 208 GB RAM**.
- VM có disk sử dụng **CSEK** ở cơ chế không được hỗ trợ.
- Guest OS không hỗ trợ suspend, hoặc một số OS cần cấu hình thêm; ví dụ Windows và những phiên bản Debian cũ được tài liệu nêu.
- Thiếu **Persistent Disk Standard quota** để lưu RAM/state, dù VM đang dùng loại disk khác.
- VM không ở trạng thái **RUNNING** khi yêu cầu suspend.

Một số Spot/preemptible VMs có thể suspend, nhưng vẫn chịu nguy cơ preemption trong quá trình chuyển trạng thái. Không dùng suspend để coi một Spot VM được bảo đảm duy trì.

### 4.3. Resume phụ thuộc tài nguyên zone

Khi suspend, compute capacity được trả về pool tài nguyên của zone. Resume cần zone có **đủ capacity**, hoặc reservation phù hợp. Nếu thiếu capacity, thao tác resume có thể **thất bại và VM vẫn SUSPENDED**. Đây không nhất thiết là mất dữ liệu; cần xử lý availability/quota/capacity rồi thử lại theo hướng dẫn, không xóa VM để “sửa”.

### 4.4. Suspend không giống hibernate OS tự phát

Compute Engine quản lý việc lưu RAM và device state. Một số hành vi ngủ/hibernate phát sinh **bên trong guest OS** không được xem là thao tác suspend của hạ tầng Compute Engine. Chỉ dùng Console, gcloud hoặc REST API phù hợp.

## 5. Chi phí: Stop/Suspend giảm compute, không xóa hóa đơn

Một nhận định sai rất phổ biến là **“tắt VM thì không còn tốn tiền”**. Với VM stopped/suspended, các khoản dùng CPU/RAM khi chạy có thể dừng tính phí sau chuyển trạng thái, nhưng **persistent storage, static IP và tài nguyên liên quan** vẫn có thể tính phí.

| Khoản chi phí | RUNNING | SUSPENDED | TERMINATED (stopped) | Sau DELETE |
|---|---|---|---|---|
| vCPU/guest RAM khi chạy | Có theo machine/pricing | Không tính phần running compute | Không tính phần running compute | Không còn phí compute VM |
| Persistent disks/Hyperdisk | Có | Tiếp tục | Tiếp tục | Tiếp tục nếu giữ disk |
| Dung lượng lưu state RAM/device | Không phải snapshot suspend | Có theo mức lưu trữ áp dụng | Không cần giữ trạng thái suspend | Không giữ |
| Static external IPv4 hoặc IP có phí | Tùy loại/mức dùng | Có thể tiếp tục | Có thể tiếp tục | Có thể tiếp tục nếu còn reserved |
| Local SSD data preservation | Theo cấu hình | Có thể có phí lưu nếu bật Preview | Có thể có phí lưu nếu bật Preview | Không giữ theo VM |
| Snapshot/backup | Theo dung lượng | Tiếp tục | Tiếp tục | Tiếp tục nếu vẫn giữ |
| Reservation/commitment | Theo hợp đồng/cấu hình | Không tự hủy | Không tự hủy | Không tự hủy chỉ vì xóa VM |
| Sole-tenant node hoặc nguồn lực dùng chung | Có thể tính riêng | Có thể vẫn phát sinh | Có thể vẫn phát sinh | Có thể vẫn phát sinh |

**Ước tính minh họa** (không phải giá niêm yết): VM dev chi phí compute giả định 20 đơn vị/ngày, disks 3 đơn vị/ngày, static IP và services khác 1 đơn vị/ngày. Nếu stop 10 ngày, khoản compute 200 đơn vị có thể không phát sinh, nhưng disk/IP vẫn tạo khoảng 40 đơn vị trong giả định đó. Với suspend, còn cân nhắc lưu RAM. Hóa đơn thật còn phụ thuộc vùng, loại máy, CUD, phí IPv4, OS license, storage, cam kết, reservations và Billing account.

### 5.1. Vì sao không thể cộng “VM đã xóa = tiết kiệm toàn bộ tiền”?

Xóa VM không tự xóa:

- Disk đã chọn **keep**.
- Snapshot/backup độc lập.
- Reserved external IP chưa giải phóng.
- Reservation chưa chỉnh.
- Cam kết **Committed Use Discount** vẫn còn hiệu lực.
- Sole-tenant nodes hoặc tài nguyên chia sẻ khác.
- Cloud Logging lưu dữ liệu hay tài nguyên ứng dụng ngoài VM.

Muốn đo hiệu quả, cần **Cloud Billing Reports theo Service/SKU và project**, đối chiếu **Cost table** kỳ hóa đơn khi cần. Dữ liệu billing có độ trễ nên không nên kết luận về tiết kiệm sau vài phút.

## 6. Preflight: điều tra VM trước khi nhấn nút

Một thao tác stop/suspend/delete chỉ được coi là an toàn khi có bằng chứng đủ để trả lời:

1. **Đúng VM?** Project ID, zone, tên VM và resource ID có khớp ticket không?
2. **Ai sở hữu?** Labels/team/application, môi trường dev/staging/production, người phê duyệt?
3. **Workload nào chạy?** Process Java, database, batch job, queue consumer, cron, traffic thực tế?
4. **Có phụ thuộc?** Load balancer backend, Managed Instance Group, DNS, private IP, Cloud SQL, GKE, Cloud Run connector, firewall hoặc hybrid VPN?
5. **Disk nào sẽ bị ảnh hưởng?** Boot/data disk names, autoDelete, disk type, Local SSD, encryption key?
6. **Có cần backup?** Snapshot và ứng dụng/database backup, yêu cầu retention, kiểm thử restore?
7. **Có thể quay lại?** Kịch bản start/resume, tái tạo VM từ IaC, restore disk, rollback DNS/traffic?
8. **Ai có quyền?** IAM roles/permission tối thiểu, quyền thao tác với khóa CMEK/CSEK nếu dùng?
9. **Thời gian dừng?** Maintenance window, SLO/SLA, người nhận cảnh báo và kế hoạch truyền thông?
10. **Kết quả kỳ vọng?** Trạng thái API, health check, dữ liệu và chi phí sau thao tác được xác minh thế nào?

~~~mermaid
flowchart TD
    Q["Yêu cầu giảm chi phí/ngừng VM"] --> ID["Xác minh project/zone/owner/workload"]
    ID --> DEP["Kiểm tra traffic, MIG/GKE, network và disks"]
    DEP --> DATA{"Cần giữ RAM?"}
    DATA -- "Có" --> SUS{"Suspend được hỗ trợ, trong 60 ngày?"}
    SUS -- "Có" --> S["Suspend có giám sát"]
    SUS -- "Không" --> SAVE["Lưu state/backup rồi chọn stop"]
    DATA -- "Không" --> KEEP{"Cần giữ VM?"}
    KEEP -- "Có" --> STOP["Stop có giám sát"]
    KEEP -- "Không" --> RET["Retention, backup, autoDelete, approvals"]
    RET --> DEL["Delete có kiểm soát"]
    SAVE --> STOP
    S --> VER["Verify status + app + billing"]
    STOP --> VER
    DEL --> VER
~~~

Không có quy tắc “VM tên chứa test thì có thể xóa”. Tên có thể cũ, labels sai hoặc instance đang phục vụ một tác vụ quan trọng. Trong production, phải xác nhận **dependency và dữ liệu** bằng nhiều nguồn, không chỉ dựa vào tên.

## 7. Thực hành 1 — Kiểm kê bằng gcloud (chỉ đọc)

Các lệnh trong phần này **không thay đổi hạ tầng**. Cần đăng nhập gcloud, có quyền xem Compute Engine và biết đúng project/zone. Đặc biệt không dùng VM của một nhóm khác chỉ vì có quyền project rộng.

### 7.1. Xác minh danh tính, project và VM

~~~bash
# Chỉ đọc: danh tính gcloud và project đang cấu hình.
gcloud auth list
gcloud config list project

# THAY BẰNG project/zone và tên máy thật được phép xem.
PROJECT_ID="my-training-project"
ZONE="asia-southeast1-a"
VM="java-dev-vm"

# Liệt kê VM và trạng thái trong project, không thay đổi gì.
gcloud compute instances list \
  --project="$PROJECT_ID" \
  --format="table(name,zone,status,machineType)"

# Xem đúng một VM.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --format="yaml(name,id,status,zone,machineType,labels,deletionProtection)"
~~~

**Lưu ý:** trường **status=TERMINATED** thường nghĩa là VM đã dừng. Không có VM trong list có thể là đã bị delete, sai project, sai quyền hoặc bộ lọc, cần đối chiếu thêm. Resource **id** giúp phân biệt một VM cũ bị xóa với VM mới tạo có cùng tên.

### 7.2. Kiểm kê disk và autoDelete

~~~bash
# Đọc attachment ở VM: nguồn disk, boot/data, autoDelete.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(disks)"

# Thông tin ổ đĩa bền vững trong zone của lab.
gcloud compute disks list \
  --project="$PROJECT_ID" \
  --filter="zone:$ZONE" \
  --format="table(name,zone,type,sizeGb,status,users)"

# Đọc chi tiết một disk có trong kết quả, nếu được cấp quyền.
gcloud compute disks describe "DISK_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,type,sizeGb,users,labels)"
~~~

Từ **VM disks attachment**, lập bảng:

| Trường | Điều cần ghi |
|---|---|
| Device/source | Tên resource disk và vùng/zone |
| **boot** | Boot disk hay data disk |
| **autoDelete** | Có tự xóa khi delete VM không |
| Disk type/size | Persistent Disk, Hyperdisk hoặc loại tương ứng |
| Encryption | Google-managed key, CMEK, CSEK hoặc cơ chế khác |
| Dữ liệu nghiệp vụ | DB, file upload, artifact, cache hay dữ liệu có thể tái tạo |
| Backup | Snapshot/backup nào, thời điểm và khả năng restore |

Nếu VM có Local SSD, cần đặc biệt kiểm tra loại disk và đường dẫn dữ liệu trong guest OS. Một bảng disk chỉ cho biết metadata của block device, không tự nói ứng dụng đã flush mọi dữ liệu lên disk.

### 7.3. Kiểm tra network, IP, service account và deletion protection

~~~bash
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(networkInterfaces,serviceAccounts,tags,metadata,deletionProtection,scheduling)"

# Kiểm tra có snapshot hiện có theo project, chỉ đọc.
gcloud compute snapshots list \
  --project="$PROJECT_ID" \
  --format="table(name,creationTimestamp,status,sourceDisk)"
~~~

Không in credential, token, khóa mã hóa hoặc secret ra log. **Metadata** có thể chứa thông tin cấu hình nhạy cảm; chỉ chia sẻ phần phù hợp khi lưu bằng chứng. Với CMEK/CSEK, cần xác minh khả năng truy cập khóa để start hoặc khôi phục disk.

### 7.4. Kiểm tra workload trước khi dừng

Ngoài metadata VM, người vận hành phải xem:

- **Cloud Monitoring**: CPU, network, disk I/O, request count, traffic, lỗi.
- **Load balancer**: instance có nằm trong backend pool và đang nhận traffic không?
- **Managed Instance Group**: VM có được controller tự quản lý không?
- **Cloud Logging/Audit Logs**: lỗi gần đây, thao tác lifecycle và thay đổi cấu hình.
- **IaC/CI/CD**: VM có trong Terraform state, startup script hoặc một lộ trình deploy không?
- **Ứng dụng**: JVM có đang nhận request, chạy scheduled jobs, consumer hoặc ghi dữ liệu không?

Đừng nhầm CPU thấp với “không còn sử dụng”: một VM có thể chờ event, giữ kết nối tới message queue, làm standby hoặc chạy batch theo lịch.

## 8. Thực hành 2 — Suspend và resume có kiểm soát

**Tình huống:** máy phát triển Java dùng ban ngày, cần giữ JVM/debugging session để hôm sau làm tiếp. Chỉ dùng suspend nếu VM hỗ trợ, không nằm trong workload không được phép gián đoạn và kế hoạch resume nằm trong cửa sổ 60 ngày.

### 8.1. Preflight dành riêng cho suspend

Trước thao tác:

1. VM đang **RUNNING**; snapshot/backup dữ liệu quan trọng đã có.
2. Guest OS/machine type đủ điều kiện, không thuộc nhóm VM loại trừ như GPU/TPU, Confidential VM, bare metal hoặc RAM vượt giới hạn.
3. Không phụ thuộc dữ liệu Local SSD chưa sao lưu; nếu có Local SSD, hiểu rõ chính sách discard/preserve.
4. Có quota disk standard để lưu RAM/state.
5. Ứng dụng chấp nhận bị gián đoạn kết nối; connection pools có reconnect sau resume.
6. Vùng có khả năng cấp lại tài nguyên khi resume; có kế hoạch nếu hết capacity.
7. Đã ghi thời điểm suspend, người phụ trách và deadline dưới 60 ngày.

### 8.2. Lệnh suspend

~~~bash
# THAY ĐỔI TRẠNG THÁI THẬT.
# Chỉ chạy sau khi người phụ trách cho phép và VM đủ điều kiện.
gcloud compute instances suspend "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"

# CHỈ ĐỌC — xác minh sau thao tác.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="value(status)"
~~~

Đợi trạng thái **SUSPENDED**; không kết luận chỉ từ thông báo CLI yêu cầu đã được nhận. Với VM có RAM lớn, thao tác có thể cần thời gian để lưu bộ nhớ. Không reset hoặc delete máy trong khi chờ chỉ vì lệnh chưa kết thúc nhanh.

Nếu VM có Local SSD, phải **chỉ rõ chính sách discard hay preserve**, theo khả năng của loại VM/phiên bản SDK. Ví dụ yêu cầu loại bỏ Local SSD data:

~~~bash
# CHỈ MINH HỌA CHO VM CÓ LOCAL SSD.
# TÁC ĐỘNG: toàn bộ dữ liệu Local SSD có thể bị mất.
gcloud compute instances suspend "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --discard-local-ssd=true
~~~

Không chạy ví dụ này nếu Local SSD còn dữ liệu quan trọng. Tùy chọn bảo toàn Local SSD bằng **--discard-local-ssd=false** trong gcloud beta là **Preview** và không áp dụng cho mọi cấu hình. Nếu chưa nắm điều kiện và cơ chế phục hồi, nên sao lưu data sang Persistent Disk/Cloud Storage và dùng phương án được hỗ trợ ổn định.

### 8.3. Lệnh resume

~~~bash
# THAY ĐỔI TRẠNG THÁI THẬT.
gcloud compute instances resume "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"

# CHỈ ĐỌC — kiểm tra VM RUNNING.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,status,networkInterfaces)"
~~~

Resume chỉ dùng cho **SUSPENDED**. Nếu VM đã tự chuyển sang **TERMINATED** sau giới hạn 60 ngày, phải dùng **start** thay vì resume, và **RAM state không còn**.

### 8.4. Kiểm thử sau resume

- VM trở lại **RUNNING**, ứng dụng Java trả health check mong đợi.
- Kiểm tra JVM process, thread pools và scheduler.
- Reconnect DB, Pub/Sub, Redis/Memorystore, Cloud SQL, Secret Manager theo cơ chế thư viện.
- Thay mới access tokens/ID tokens đã hết hạn, thiết lập lại TLS sessions khi cần.
- Kiểm tra ephemeral external IP, DNS cache, load balancer membership.
- Quan sát latency, error rate và network traffic ít nhất qua giai đoạn ổn định.
- Nếu không đủ capacity trong zone, xử lý tình huống theo runbook; không vội delete VM.

**Khôi phục RAM không thay cho tính bền vững nghiệp vụ.** Một request đang xử lý khi suspend có thể timeout ở phía client, dẫn tới retry sau resume. Service nên có cơ chế idempotency cho các thao tác thanh toán hoặc ghi dữ liệu.

## 9. Thực hành 3 — Stop và start an toàn

Stop phù hợp khi muốn **giữ VM và persistent disks**, không cần RAM state. Ví dụ VM phục vụ batch chỉ hoạt động vào giờ làm việc, hoặc VM cần tắt để đổi machine type.

### 9.1. Graceful shutdown là trách nhiệm của ứng dụng và hạ tầng

Trước stop:

- Ngừng nhận traffic mới: loại backend khỏi routing hoặc đưa ứng dụng vào chế độ draining theo thiết kế.
- Hoàn thành/ghi checkpoint các batch jobs có thể kéo dài.
- Dừng consumer nhận việc mới, xác nhận in-flight messages được ack hoặc có thể retry.
- Flush write buffers và commit transaction cần thiết; tránh để dữ liệu chỉ còn trong RAM.
- Tùy workload, dùng **shutdown script** có thời hạn thích hợp để thông báo hoặc dọn resource.
- Kiểm tra policy graceful shutdown của loại VM; nếu bị timeout, hệ thống có thể dừng cưỡng bức.

Trong Java có thể dùng **shutdown hook** để đóng connection pool và graceful stop, nhưng hook không bảo đảm chạy đủ trong mọi trường hợp (mất điện/host failure/kill -9). Thiết kế dữ liệu phải chịu được gián đoạn bất ngờ.

### 9.2. Lệnh stop

~~~bash
# THAY ĐỔI THẬT — yêu cầu stop theo trình tự chuẩn.
gcloud compute instances stop "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"

# CHỈ ĐỌC — trạng thái dự kiến sau khi dừng.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="value(status)"
~~~

Trạng thái mong đợi khi hoàn tất là **TERMINATED**. Đừng dùng **--no-graceful-shutdown** làm mặc định: tùy chọn này bỏ qua hoặc kết thúc quá trình shutdown có trật tự, có thể gây mất dữ liệu chưa ghi. Chỉ sử dụng khi đã được phê duyệt và hiểu tình trạng ứng dụng.

Nếu VM có Local SSD:

~~~bash
# THAY ĐỔI — TÁC ĐỘNG: discard dữ liệu Local SSD khi dừng.
gcloud compute instances stop "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --discard-local-ssd=true
~~~

Theo tài liệu, khi có Local SSD bạn phải chỉ rõ có discard hay không. Bảo toàn Local SSD khi stop bằng tùy chọn false có thể chỉ có dưới **gcloud beta** ở giai đoạn Preview; không dùng như một backup.

### 9.3. Lệnh start

~~~bash
# THAY ĐỔI THẬT — boot OS và ứng dụng từ đầu.
gcloud compute instances start "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"

# CHỈ ĐỌC — xem trạng thái, IP và attached disks.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(status,networkInterfaces,disks)"
~~~

Start từ **TERMINATED**; không dùng để khôi phục RAM của trạng thái SUSPENDED. Với disk dùng key theo cơ chế đặc biệt, có thể cần quyền và tham số cung cấp khóa trước khi start.

### 9.4. Kiểm thử sau start

| Thành phần | Kiểm tra |
|---|---|
| VM | RUNNING, đúng machine type/zone/labels |
| Disk | Đúng boot/data disks, mount point, filesystem, data integrity |
| Network | VPC, subnet, IP, DNS, firewall, route, VPN/Interconnect |
| Ứng dụng | JVM/service started, health/readiness, logs không có fatal error |
| Database | Kết nối thành công, migration/transaction không lỗi |
| Queue/batch | Retry/idempotency đúng, không nhân đôi công việc |
| IAM và secret | Runtime service account có quyền tối thiểu, token refresh bình thường |
| Monitoring | Traffic, CPU, error rate, alert và SLO phục hồi |

Nếu start thất bại do **quota/capacity/availability**, chưa đủ cơ sở để xóa disk hoặc khôi phục vào một vùng khác mà không có thiết kế di chuyển phù hợp.

## 10. Delete VM an toàn: thứ tự quan trọng hơn lệnh

**Delete là thao tác rủi ro cao** vì tài nguyên VM sẽ không còn và boot/data disks có thể bị xóa theo cấu hình. Không xem nó như “stop tiết kiệm hơn” nếu chưa có quyết định dữ liệu, dependency và backup.

### 10.1. Runbook trước delete

1. **Xác nhận đúng đích:** project ID, zone, VM name, resource ID và environment.
2. **Owner phê duyệt:** người phụ trách dữ liệu, vận hành, bảo mật khi cần.
3. **Ngừng traffic:** loại endpoint khỏi load balancer/DNS hoặc thay route theo trình tự có kế hoạch.
4. **Đánh giá phụ thuộc:** scheduler, queue, IAM, service accounts, Cloud SQL, storage, VPC firewall, monitoring, backups.
5. **Kiểm kê disks:** từng boot/data disk, autoDelete, local SSD, snapshot/backup; xác định disk nào **giữ**, disk nào **xóa**.
6. **Backup và restore test:** ưu tiên application-consistent backup; xác nhận snapshot/backup thành công và kiểm thử khả năng phục hồi.
7. **Retention:** đối chiếu yêu cầu lưu trữ dữ liệu, retention lock/hold và quy trình xóa dữ liệu nhạy cảm.
8. **Định danh và IP:** xác định static external IP, reserved address, DNS name, URL, certificate và references cần thay.
9. **IAM và IaC:** cập nhật cấu hình nguồn để controller/pipeline không tạo lại VM; ghi lại người thay đổi và ticket.
10. **Chạy có kiểm soát:** không dùng lệnh hàng loạt/--quiet khi chưa có guard; chờ API xác nhận xóa.
11. **Xác minh:** VM biến mất, disks/IP/snapshots còn hoặc mất đúng kế hoạch, monitor/billing được điều chỉnh.

### 10.2. Deletion protection

Compute Engine có thuộc tính **deletionProtection** giúp ngăn delete VM do nhầm thao tác. Có thể bật khi tạo VM hoặc qua update có quyền phù hợp. Tuy nhiên:

- Deletion protection **không ngăn stop, reset hoặc suspend**.
- **Không hỗ trợ deletion protection trên VM thuộc Managed Instance Group**.
- Nó không phải lớp bảo vệ dữ liệu tuyệt đối trước việc xóa project hoặc một số tác động đặc biệt.
- Người có quyền điều chỉnh deletionProtection có thể tắt nó, vì vậy vẫn cần IAM tối thiểu, approval và audit logs.

~~~bash
# CHỈ ĐỌC — kiểm tra deletion protection trước khi xóa.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,id,status,deletionProtection,disks)"
~~~

Nếu đang **true**, không được tự động tắt để làm cho lệnh delete chạy được. Phải xác định đây có phải guardrail được thiết lập có chủ đích và cần phê duyệt riêng hay không.

### 10.3. AutoDelete của boot/data disks

Một VM có thể có các disk sau:

| Disk | Vai trò | autoDelete đang quan sát | Quyết định khi delete |
|---|---|---:|---|
| boot-java-dev | Hệ điều hành | true | Có thể xóa nếu image/IaC và dữ liệu cần thiết đã có |
| user-workspace | Source/data của lập trình viên | false | Giữ và xác minh backup |
| scratch-cache | Cache tái tạo được | true | Có thể xóa sau xác nhận |
| Local SSD | Scratch/temp | Không như persistent disk | Mất theo vòng đời VM; phải copy dữ liệu cần giữ |

**autoDelete được kiểm tra trên disk attachment của instance.** Nếu không kiểm tra, xóa VM có thể làm mất boot disk chứa cấu hình chưa được backup hoặc data disk được ai đó đặt autoDelete=true.

### 10.4. Lệnh delete với quyết định giữ disk rõ ràng

Đối với VM dev đã được phép loại bỏ nhưng phải **giữ tất cả persistent disks** để review sau, có thể dùng:

~~~bash
# TÁC ĐỘNG NGHIÊM TRỌNG: DELETE VM.
# Chỉ chạy sau khi checklist/approval/backup đã PASS.
# --keep-disks=all giữ attached persistent boot và data disks;
# không giữ RAM hoặc Local SSD.
gcloud compute instances delete "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --keep-disks=all
~~~

Lệnh có bước xác nhận mặc định; **không thêm --quiet** vào bản hướng dẫn để tránh bỏ qua một guard đơn giản. Cờ **--keep-disks** có thể chọn **all**, **boot** hoặc **data** theo nhu cầu. Nếu muốn xóa cả disk, cần quyết định riêng và kiểm tra autoDelete/disk deletion policy; không tự suy từ việc delete VM.

**Giữ disk không bảo đảm dữ liệu đã có backup ở nơi khác.** Disk còn có thể bị mất do xóa nhầm độc lập, chính sách khác hoặc sự cố; cần snapshot/backup riêng và xác nhận khôi phục được.

### 10.5. Hậu kiểm khi delete

~~~bash
# CHỈ ĐỌC — VM phải không còn xuất hiện trong danh sách.
gcloud compute instances list \
  --project="$PROJECT_ID" \
  --filter="name=$VM"

# CHỈ ĐỌC — kiểm tra disk còn tồn tại đúng kế hoạch.
gcloud compute disks list \
  --project="$PROJECT_ID" \
  --format="table(name,zone,status,users)"

# CHỈ ĐỌC — kiểm tra địa chỉ reserved nếu có.
gcloud compute addresses list \
  --project="$PROJECT_ID"

# CHỈ ĐỌC — kiểm tra snapshots được giữ.
gcloud compute snapshots list \
  --project="$PROJECT_ID"
~~~

Nếu VM không thấy ở lệnh list, xác minh API operation hoàn tất, đúng project/zone và không có Managed Instance Group/pipeline tạo lại. Với disk giữ lại, phải ghi rõ **owner, retention deadline, nơi backup và chi phí tiếp tục**.

## 11. Backup, snapshot và khả năng phục hồi thực tế

### 11.1. Snapshot có tác dụng gì?

Snapshot tạo một bản sao dữ liệu disk theo tính năng Persistent Disk/Hyperdisk hỗ trợ, hữu ích khi cần:

- Bảo toàn dữ liệu trước bảo trì hay delete.
- Tạo disk mới từ bản snapshot để kiểm thử.
- Hỗ trợ khôi phục sau khi VM bị xóa nếu còn cấu hình/IaC cần thiết.

Snapshot không tự lưu mọi cấu hình mạng, role IAM, service account permissions, startup scripts ngoài disk hoặc cấu trúc phụ thuộc ứng dụng. Với nhiều disk và database, cần thiết kế **application-consistent backup**; snapshot đơn độc có thể chỉ crash-consistent theo điều kiện thao tác.

### 11.2. Ví dụ snapshot boot disk hoặc data disk

~~~bash
# THAY ĐỔI — tạo snapshot tính phí lưu trữ.
# Chỉ sau khi xác minh đúng disk, quyền và chính sách backup.
DISK_NAME="user-workspace"
SNAPSHOT_NAME="workspace-before-decommission-20261119"

gcloud compute disks snapshot "$DISK_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --snapshot-names="$SNAPSHOT_NAME"

# CHỈ ĐỌC — xác minh snapshot hoàn tất.
gcloud compute snapshots describe "$SNAPSHOT_NAME" \
  --project="$PROJECT_ID" \
  --format="yaml(name,status,sourceDisk,creationTimestamp)"
~~~

Đối với snapshot VM đang chạy, nên phối hợp cơ chế quiesce/flush và chính sách của ứng dụng. Nếu workload cần RPO/RTO nghiêm ngặt, dùng backup được thiết kế cho DB hoặc hệ thống lưu trữ thay vì xem snapshot tiện dụng là bản sao đầy đủ.

### 11.3. Restore test là bằng chứng quan trọng

Quy trình kiểm chứng phục hồi:

1. Chọn snapshot/backup đã hoàn tất và còn trong thời hạn.
2. Tạo **disk thử nghiệm** từ snapshot trong vùng/zone phù hợp.
3. Attach vào **VM phục hồi cô lập** theo quyền được cấp hoặc tạo VM mới từ disk boot nếu được hỗ trợ.
4. Kiểm tra filesystem, checksum/data sample, ứng dụng Java hoặc database ở chế độ an toàn.
5. Đối chiếu thời gian phục hồi với **RTO**, dữ liệu mới nhất với **RPO**.
6. Không để VM restore dùng nhầm production endpoint, publish trùng thông điệp hoặc ghi đè database thật.
7. Lưu kết quả và dọn tài nguyên phục hồi thử nghiệm có kiểm soát.

**Backup chưa được thử khôi phục chưa phải bằng chứng chắc chắn của khả năng hồi phục.** Khi có nguy cơ xóa nhầm data disk, restoration test là phần có giá trị hơn một thông báo “snapshot created”.

## 12. VM thuộc MIG, GKE hoặc các mô hình đặc biệt

Không phải VM nào có tên trong **Compute Engine → VM instances** cũng nên quản trị độc lập. Trước thao tác lifecycle phải xác định **ai là controller/nguồn chuẩn** của VM.

### 12.1. Managed Instance Group (MIG)

**Managed Instance Group** quản lý tập VM theo instance template, desired size, autoscaling, autohealing và rolling updates. Nếu một VM thuộc MIG bị xóa hoặc dừng ngoài quy trình, **MIG có thể tái tạo hoặc đưa trạng thái nhóm về mục tiêu**, khiến thao tác “giảm chi phí” không có tác dụng hoặc gây gián đoạn.

Các tình huống:

- Muốn giảm số VM xử lý: xem **autoscaler/min-size/target-size** và thay qua MIG.
- Muốn bảo trì/rolling update: dùng cơ chế MIG update/repair phù hợp.
- Muốn tạo **stopped/suspended pool**: dùng tính năng standby pools theo loại MIG và cấu hình được hỗ trợ, không chỉ stop một VM ngẫu nhiên.
- Trong **regional MIG**, có các điều kiện hạn chế về target distribution shape và redistribution khi stop/suspend một instance cụ thể.
- Với stateful MIG, kiểm tra **preserved state** của disk/IP; không mặc định có thể giữ data như standalone VM.

**Deletion protection không được áp dụng cho VM là thành viên MIG** theo tài liệu Compute Engine. Guardrail phải nằm ở IAM, pipeline, cấu hình MIG và quy trình phê duyệt.

### 12.2. GKE node không phải máy chủ do ứng dụng tự quản

GKE node thực chất chạy trên Compute Engine, nhưng do **GKE node pool/autoscaler/upgrade controller** quản lý. Nếu người vận hành stop hoặc delete một node trực tiếp:

- Pod có thể mất nơi chạy và được scheduler chuyển đi, tùy cluster và khả năng còn capacity.
- Các PodDisruptionBudget, drain và thời gian chờ của workload cần được xem xét.
- Controller có thể sửa chữa/tạo node thay thế.
- Các dữ liệu không bền vững trên node có thể mất.
- SLO ứng dụng có thể giảm dù ý định chỉ là tiết kiệm phí Compute Engine.

Muốn thay đổi năng lực GKE, dùng thao tác **GKE node pool, autoscaling và maintenance** phù hợp. Không dùng gcloud compute instances delete cho node đang thuộc cluster chỉ vì tên nó xuất hiện trong danh sách VM.

### 12.3. Spot, preemptible, GPU, TPU, Confidential và sole-tenant

| Loại VM | Điều cần kiểm tra trước lifecycle |
|---|---|
| **Spot/preemptible** | Có thể bị preempt; chính sách restart/preemption và dữ liệu tạm phải phù hợp |
| **GPU/TPU** | Suspend có thể không được hỗ trợ; stop/start cần xem capacity và quota |
| **Confidential VM** | Suspend không được hỗ trợ theo tài liệu hiện hành |
| **Bare metal** | Suspend không được hỗ trợ |
| **VM nhiều RAM** | Trên 208 GB RAM không hỗ trợ suspend theo tài liệu được kiểm tra |
| **Sole-tenant VM** | Dừng/xóa VM chưa chắc dừng phí sole-tenant node |
| **Reservation-bound/committed workload** | Stop/delete một VM không tự hủy reservation hoặc commitment |
| **VM gắn Local SSD** | Dữ liệu mặc định bị bỏ khi stop/suspend; tính năng giữ dữ liệu có giới hạn |
| **VM có khóa mã hóa riêng** | Start/restore có thể đòi hỏi key còn hoạt động và quyền sử dụng key |

Một số giới hạn/khả năng đang ở Preview có thể thay đổi theo phiên bản. Với loại máy đặc biệt, cần tra tài liệu chính thức và chạy một bài kiểm thử trên VM không chứa dữ liệu quan trọng trước khi đưa vào runbook production.

## 13. IAM, audit, automation và chính sách vòng đời

### 13.1. Quyền thao tác tối thiểu

Các quyền tiêu biểu của Compute Engine:

| Thao tác | IAM permission thường liên quan |
|---|---|
| Xem VM | **compute.instances.get**, **compute.instances.list** |
| Suspend | **compute.instances.suspend** |
| Resume | **compute.instances.resume** |
| Stop | **compute.instances.stop** |
| Start | **compute.instances.start** |
| Delete | **compute.instances.delete** |
| Thay deletion protection | **compute.instances.update** hoặc quyền phù hợp theo API |
| Tạo/đọc snapshot | **compute.disks.createSnapshot**, quyền snapshot tương ứng |
| Thao tác disk độc lập | Quyền trên disks, snapshots, vùng và các tài nguyên phụ thuộc |

Một vai trò như **roles/compute.instanceAdmin.v1** có thể bao gồm nhiều quyền quản trị VM, nhưng có phạm vi rộng; nên cân nhắc custom roles, phạm vi project/VM và điều kiện theo chính sách tổ chức. Người thực hiện backup/restore còn cần quyền trên snapshot/storage/keys. Không cấp **Owner** cho pipeline chỉ để thao tác suspend.

### 13.2. Audit log và danh tính người thực hiện

Với những thao tác stop, suspend, resume, delete hoặc thay deletion protection, giữ bằng chứng:

- **Ai** yêu cầu hành động: user/service account.
- **Khi nào**: timestamp UTC, project, zone và instance ID.
- **Lý do**: ticket, change request, môi trường, owner.
- **Kết quả**: operation ID, status, lỗi nếu có, timestamp chuyển trạng thái.
- **Dữ liệu**: quyết định keep/delete disk, snapshot IDs, retention và restore test.
- **Sức khỏe**: health checks, monitoring, cost review sau thao tác.

**Cloud Audit Logs** là nguồn quan trọng để tìm các API actions; nếu cần tìm ai đã đổi deployment/instance template, hãy đối chiếu với PR/IaC history. Hạn chế ghi dữ liệu nhạy cảm vào log và không lưu credentials.

### 13.3. Tự động hóa tiết kiệm chi phí phải có guardrails

Có thể dùng Cloud Scheduler kết hợp Cloud Run/Workflows hoặc công cụ IaC để **tự động stop/start VM dev ngoài giờ**. Nhưng quy tắc an toàn cần ít nhất:

1. Phạm vi cố định: **allowlist project và zone**, không quét toàn organization rồi xử lý mặc định.
2. Dựa vào nhãn có kiểm soát như **lifecycle=schedulable**, **environment=development**, **owner=...**.
3. Có **dry run/report** trước khi thực thi, hiển thị đúng VM ID và thao tác dự kiến.
4. Không stop VM trong MIG/GKE hoặc production, trừ khi đã có thiết kế tương ứng.
5. Kiểm tra workload an toàn để dừng, backup và Local SSD.
6. Có cơ chế **opt-out/exception**, manual override và thời hạn ngoại lệ.
7. Service account thực thi có IAM tối thiểu.
8. Có alert khi stop/start thất bại và có người phụ trách.
9. Lưu audit trail, đối chiếu billing theo tháng.
10. Không tạo automation tự động **delete** chỉ vì VM có nhãn expires_on đã qua ngày mà chưa kiểm tra dữ liệu và phụ thuộc.

Ví dụ truy vấn chỉ đọc dùng để lập danh sách cần review:

~~~bash
# CHỈ ĐỌC — lọc tên VM ứng viên. Cần xác minh output và nhãn cụ thể.
gcloud compute instances list \
  --project="$PROJECT_ID" \
  --filter="labels.environment=development" \
  --format="table(name,zone,status,labels)"
~~~

Không thực hiện stop/delete đồng loạt trên kết quả lọc như một one-liner. Nhãn có thể sai hoặc bị bỏ sót; cần owner review theo runbook.

### 13.4. Mẫu bảng quyết định trước thay đổi

| Trường | Giá trị cần có |
|---|---|
| Change/ticket ID | … |
| Project/zone/instance name/id | … |
| Application/environment/owner | … |
| Hành động | Suspend / Resume / Stop / Start / Delete |
| Lý do | Chi phí / bảo trì / ngừng dịch vụ |
| Traffic đã được xử lý? | Drain / disabled backend / schedule |
| RAM state có cần giữ? | Có/không, trong bao lâu |
| Local SSD có dữ liệu? | Có/không và cách xử lý |
| Boot/data disks và autoDelete | Bảng từng disk |
| Snapshot/backup IDs | Danh sách và kết quả kiểm thử restore |
| Static/ephemeral IP | Có phụ thuộc DNS/client không |
| MIG/GKE/Spot/reservation/commitment | Kết quả kiểm tra |
| Approval/rollback owner | … |
| Dự kiến trạng thái sau thao tác | … |
| Hậu kiểm và billing review | … |

Dấu “…” trong mẫu là trường phải được điền bằng dữ liệu thật; đây không phải bằng chứng đã hoàn thành công việc.

## 14. Chẩn đoán lỗi suspend, resume, stop, start và delete

### 14.1. Sơ đồ tìm nguyên nhân

~~~mermaid
flowchart TD
    A["Lifecycle command thất bại"] --> B{"Đúng project/zone/VM state?"}
    B -- "Không" --> ID["Kiểm tra identity, resource ID và status"]
    B -- "Có" --> C{"Đủ IAM/API/quota?"}
    C -- "Không" --> IAM["Kiểm tra permissions, quota, API enablement"]
    C -- "Có" --> D{"Suspend/stop có hạn chế VM type/disk?"}
    D -- "Có" --> LIMIT["Local SSD, GPU, RAM, Confidential, OS, quotas"]
    D -- "Không" --> E{"Resume/start thiếu zone capacity/key?"}
    E -- "Có" --> CAP["Capacity, reservations, encryption key"]
    E -- "Không" --> F{"Delete blocked hoặc resource do controller quản lý?"}
    F -- "Có" --> PROTECT["Deletion protection, MIG/GKE, dependency"]
    F -- "Không" --> LOG["Audit logs, API error, operation status"]
~~~

### 14.2. Các triệu chứng thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Suspend báo unsupported | VM không RUNNING, OS/machine không hỗ trợ, GPU/Confidential | Kiểm tra status/loại máy/OS theo tài liệu |
| Suspend thất bại do quota disk | Thiếu Persistent Disk Standard quota để lưu RAM | Xem quota vùng, xử lý theo quy trình |
| Suspend mất lâu | RAM/device state lớn hoặc có yêu cầu lưu Local SSD | Theo dõi operation, không reset vội |
| SUSPENDED sau 60 ngày chuyển TERMINATED | Hết cửa sổ suspend | Dùng start và boot app lại; RAM state đã mất |
| Resume không có capacity | Zone không đủ tài nguyên và không có reservation phù hợp | Chờ/đánh giá capacity; không xóa VM để sửa |
| VM chạy lại nhưng Java app lỗi | Pool kết nối/token/DNS cache hoặc checkpoint không còn hợp lệ | Kiểm tra logs, reconnect, readiness và secrets |
| Stop bị lỗi với Local SSD | Chưa khai báo discard/preserve theo yêu cầu | Xác minh dữ liệu, chọn cờ và tính năng được hỗ trợ |
| Start thành công nhưng IP public đổi | Trước đó là ephemeral IP | Cập nhật DNS hoặc dùng static IP/load balancer phù hợp |
| Start lỗi do encryption key | Key bị thu hồi hoặc thiếu quyền | Xem CMEK/CSEK và quyền sử dụng khóa |
| Delete bị từ chối | Deletion protection, IAM thiếu hoặc VM thuộc nhóm quản lý | Xem guardrails, MIG/GKE, policy; xin phê duyệt |
| VM vừa delete đã xuất hiện lại | MIG/automation tái tạo theo desired state | Sửa configuration/controller thay vì xóa từng VM |
| Disk biến mất sau delete | autoDelete=true hoặc lựa chọn xóa disk | Khôi phục từ backup/snapshot nếu có; kiểm tra quy trình |
| Hóa đơn vẫn tăng dù đã stop/delete | Disk, IP, snapshot, reservation, CUD, sole-tenant hoặc phí dịch vụ khác | Phân tích Billing theo project/service/SKU |
| VM đã RUNNING nhưng ứng dụng chưa phục vụ | Boot script, service fail, IAM, firewall hoặc DB timeout | Kiểm tra health/readiness, logs và monitoring |

### 14.3. Phân biệt lỗi hệ thống và lỗi ứng dụng

- **VM status=RUNNING** nhưng HTTP 503: có thể JVM chưa sẵn sàng hoặc backend fail health check.
- **VM status=SUSPENDED** nhưng lệnh curl timeout: đó là hành vi dự kiến khi máy không chạy, không phải lỗi firewall.
- **VM status=TERMINATED** sau stop: không dùng resume; dùng start.
- **Lỗi 403 từ Google APIs** sau start/resume: kiểm tra IAM/service account/token, không phải cứ cấp external IP là giải quyết.
- **Disk usage tăng sau stop**: persistent storage vẫn tính phí; cần quyết định retention, không xóa dữ liệu chỉ vì thấy charge.

Với các lỗi không rõ nguyên nhân, ghi **đúng operation ID và thông báo lỗi** rồi xem Cloud Logging/Audit Logs/Compute Engine operation, thay vì chạy lặp cùng một lệnh nguy hiểm.

## 15. Case study — Từ Java VM sang Cloud Run, cần xóa máy cũ

**Bối cảnh giả định:** nhóm payments có một VM **checkout-legacy** tại project **commerce-prod** chạy ứng dụng Java xử lý đơn hàng. Ứng dụng mới đã được triển khai lên Cloud Run, nhưng VM cũ vẫn tồn tại. Một data disk giữ file đối soát, boot disk chứa cấu hình cũ, còn địa chỉ IP của VM đã được tham chiếu trong một job nội bộ.

### 15.1. Nếu xóa VM ngay thì chuyện gì có thể xảy ra?

- Boot disk có autoDelete=true bị xóa, mất cấu hình chưa được sao lưu.
- Data disk nếu autoDelete=true cũng có thể bị xóa.
- Job nội bộ vẫn gọi IP cũ nên lỗi hoặc đi nhầm endpoint sau khi IP ephemeral được tái cấp.
- Một task xử lý cuối ngày vẫn chạy trên VM, gây mất công việc đang thực hiện.
- Monitoring hoặc alert cũ gửi cảnh báo ảo; IAM/service account cũ vẫn có quyền.
- Sau khi xóa VM, phí disk giữ lại, snapshot hoặc reserved IP vẫn tồn tại.

### 15.2. Phương án an toàn

1. **Inventory:** xác định VM resource ID, owner, labels, zone, disks, deletionProtection, network và service account.
2. **Traffic check:** đối chiếu request logs/load balancer/backend metrics và chứng minh Cloud Run đã nhận toàn bộ lưu lượng.
3. **Scheduler/queue check:** chuyển tác vụ batch và consumer sang hệ thống mới; xác nhận không còn event cần xử lý.
4. **Data retention:** backup file đối soát, tạo snapshot data disk và thử restore trong môi trường cách ly.
5. **IAM/network review:** xác định secret, service account, firewall và DNS không còn dùng; thu hồi dần theo kế hoạch, không xóa dữ liệu dùng chung.
6. **Stop có thời hạn quan sát:** dừng VM trong maintenance window, kiểm tra không có dependency nào thất bại.
7. **Đo và xác nhận:** quan sát SLO ứng dụng mới và các sự kiện lỗi trong một khoảng phù hợp.
8. **Delete có keep disk:** nếu owner đã phê duyệt, xóa VM nhưng giữ disk trong thời gian kiểm chứng được quy định; điều chỉnh IaC.
9. **Hậu kiểm:** VM không còn, data disk/snapshot được giữ đúng, job không lỗi, IP/DNS sạch và phí còn lại được giải thích.
10. **Kết thúc retention:** chỉ sau khi hết thời hạn giữ và có phê duyệt phù hợp mới cân nhắc xóa disk/snapshot.

### 15.3. Vì sao không chọn suspend?

VM cần ngừng **dài hạn**; không cần giữ JVM RAM. Suspend chỉ giữ trạng thái trong tối đa 60 ngày, có thêm chi phí lưu state và không giải quyết dependency chưa được chuyển. **Stop trước, delete sau khi quan sát** là phù hợp hơn trong tình huống này.

Nếu đây là VM dev cá nhân dùng một ngày rồi tiếp tục debug, suspend có thể hợp lý. **Lựa chọn lifecycle phải dựa trên mục tiêu thực tế**, không chỉ là nút nào có thể giảm chi phí.

## 16. Bài tập thực hành và câu hỏi tự kiểm tra

### 16.1. Bài tập A — Chọn hành động

Với mỗi tình huống, chọn **Suspend, Stop, Start, Resume hoặc Delete**, rồi giải thích yêu cầu kiểm tra dữ liệu:

| Tình huống | Quyết định gợi ý |
|---|---|
| VM dev Java đang mở phiên IDE/JVM, nghỉ qua đêm, hỗ trợ suspend | **Suspend**, rồi **Resume** |
| VM batch chạy hằng tuần, không cần giữ RAM state | **Stop**, rồi **Start** khi cần |
| VM đã SUSPENDED 10 ngày, cần làm việc lại | **Resume**, kiểm tra app connections |
| VM bị SUSPENDED 61 ngày và tự chuyển TERMINATED | **Start**, không còn RAM state để resume |
| VM production ngừng phục vụ, chưa xác minh backup/data disk | **Không Delete ngay**; inventory và backup, có thể Stop có kiểm soát |
| VM đã được thay thế, mọi dữ liệu/owner/retention đã phê duyệt | **Delete** có lựa chọn disk rõ ràng |
| VM thuộc MIG cần giảm số bản sao | Thay **desired state/autoscaler/MIG**, không thao tác tùy tiện từng VM |

### 16.2. Bài tập B — Đọc disk attachment

Giả sử một VM có các disk:

~~~yaml
# Dữ liệu mô phỏng, không phải response API đầy đủ.
disks:
  - boot: true
    source: boot-disk
    autoDelete: true
  - boot: false
    source: orders-data
    autoDelete: false
  - boot: false
    source: scratch-backup
    autoDelete: true
~~~

**Câu hỏi:**

1. Nếu xóa VM mà không thay lựa chọn disk, những disk nào có nguy cơ bị xóa?
2. Lệnh có **--keep-disks=all** thay đổi kết quả gì?
3. orders-data giữ lại có còn phát sinh phí không?
4. Nếu scratch-backup thực sự chứa dữ liệu quan trọng thì nên làm gì trước delete?
5. Chỉ nhìn autoDelete có chứng minh backup đã thành công không?

**Đáp án định hướng:** (1) boot-disk và scratch-backup; (2) giữ attached persistent disks khi xóa VM; (3) có, tùy loại/dung lượng disk; (4) xác minh dữ liệu, snapshot/backup và restore test; (5) không.

### 16.3. Bài tập C — Điều tra suspend thất bại

Một VM có **GPU, 256 GB RAM, Local SSD**. Lập trình viên dùng:

~~~bash
gcloud compute instances suspend training-gpu-vm \
  --project=training-project \
  --zone=asia-southeast1-a
~~~

Lệnh bị từ chối. Hãy liệt kê ít nhất **ba nguyên nhân độc lập** và chọn phương án quản lý vòng đời thay thế.

**Định hướng:** GPU và hơn 208 GB RAM là các giới hạn suspend; Local SSD có điều kiện xử lý dữ liệu. Nếu cần giảm chi phí, cần backup/persist dữ liệu quan trọng và cân nhắc **stop** theo khả năng VM, kiểm tra GPU/Local SSD, capacity khi start lại và SLA ứng dụng.

### 16.4. Bài tập D — Kiểm chứng chi phí

Một VM đã stop cuối tháng, nhưng Billing Reports tiếp tục có khoản phí mỗi ngày. Hãy phân tích các khoản có thể vẫn phát sinh: persistent boot/data disks, snapshots, static external IP, reservation, CUD, sole-tenant resource, logs/monitoring. So sánh **Service/SKU** để xác minh, không kết luận VM chưa stop chỉ từ một dòng tổng.

### 16.5. Mẫu biên bản thao tác lifecycle

~~~text
REQUEST_ID:
UTC_TIMESTAMP:
PROJECT_ID:
ZONE:
VM_NAME:
VM_RESOURCE_ID:
APPLICATION:
ENVIRONMENT:
OWNER:
CURRENT_STATUS:
REQUESTED_ACTION:
REASON:
APPROVER:
MIG_OR_GKE_CONTROLLER:
DISKS_AND_AUTODELETE:
LOCAL_SSD_POLICY:
BACKUP_AND_RESTORE_RESULT:
IP_AND_DNS_DEPENDENCIES:
TRAFFIC_DRAIN_RESULT:
COMMAND_OR_OPERATION_ID:
FINAL_VM_STATUS:
POST_ACTION_HEALTH_CHECK:
BILLING_REVIEW_DATE:
ROLLBACK_OR_RECOVERY_PLAN:
OPEN_ISSUES:
~~~

Dữ liệu trong biên bản phải phản ánh **đã quan sát thực tế**, không điền “PASS” khi chỉ dự đoán kết quả.

## 17. Những sai lầm cần tránh và tài liệu tham khảo

### 17.1. Ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “TERMINATED nghĩa là VM đã bị xóa.” | TERMINATED thường là VM đã stop và có thể start lại. |
| “Suspend và stop giống nhau.” | Suspend giữ RAM có thời hạn; stop không bảo toàn RAM để resume. |
| “Suspend có thể giữ state vô thời hạn.” | Giới hạn tối đa **60 ngày**. |
| “VM nào cũng suspend được.” | Có giới hạn OS, GPU/TPU, Confidential, RAM, disk/key và quota. |
| “Resume chắc chắn thành công ngay.” | Còn phụ thuộc capacity zone và điều kiện tài nguyên. |
| “Stopped VM không còn phí gì.” | Disk, IP, backups, reservation, commitments… vẫn có thể có phí. |
| “Local SSD luôn giữ dữ liệu khi stop.” | Mặc định có thể mất; preserve là khả năng giới hạn/Preview. |
| “Delete VM thì mọi disk cũng mất.” | Phụ thuộc autoDelete và lựa chọn keep/delete. |
| “Delete VM không động tới dữ liệu.” | Boot/data disk có thể bị xóa; cần kiểm tra từng attachment. |
| “Deletion protection ngăn mọi loại gián đoạn.” | Không chặn stop, suspend hoặc reset; không thay thế IAM và backup. |
| “Snapshot là backup nhất quán cho toàn bộ database.” | Cần application-consistent backup và restore test. |
| “Delete node GKE/MIG là giảm chi phí bền vững.” | Controller có thể tái tạo; phải thay desired state. |
| “RUNNING là ứng dụng đã healthy.” | Phải kiểm tra readiness/health, DB, traffic và logs. |
| “VM không có CPU nghĩa là có thể xóa.” | Có thể là standby hoặc workload chạy theo lịch. |
| “Stop VM là hủy CUD/reservation.” | Cam kết và reservations được quản lý riêng. |

### 17.2. Tài liệu Google Cloud chính thức

- [Compute Engine instance lifecycle](https://docs.cloud.google.com/compute/docs/instances/instance-lifecycle)
- [Suspend, stop, or reset Compute Engine instances](https://docs.cloud.google.com/compute/docs/instances/suspend-stop-reset-instances-overview)
- [Suspend or resume a Compute Engine instance](https://docs.cloud.google.com/compute/docs/instances/suspend-resume-instance)
- [Stop or restart a Compute Engine instance](https://docs.cloud.google.com/compute/docs/instances/stop-start-instance)
- [Delete a Compute Engine instance](https://docs.cloud.google.com/compute/docs/instances/deleting-instance)
- [Prevent accidental VM deletion](https://docs.cloud.google.com/compute/docs/instances/preventing-accidental-vm-deletion)
- [View disk details and autoDelete](https://docs.cloud.google.com/compute/docs/disks/view-disk-details)
- [Local SSD disks and data preservation](https://docs.cloud.google.com/compute/docs/disks/local-ssd)
- [Troubleshoot suspend and resume](https://docs.cloud.google.com/compute/docs/troubleshooting/troubleshooting-suspend-resume)
- [Stopped and suspended VMs in a MIG](https://docs.cloud.google.com/compute/docs/instance-groups/suspended-and-stopped-vms-in-mig)
- [Compute Engine pricing](https://cloud.google.com/compute/all-pricing)

Các giới hạn sản phẩm, giai đoạn Preview, cờ gcloud, giá và khả năng của từng machine family có thể thay đổi. Với môi trường thật, kiểm tra tài liệu của **đúng loại VM và phiên bản SDK** trước khi triển khai.

---

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** quản lý vòng đời Compute Engine không tách rời **project/IAM, VPC, persistent storage, snapshot/backup, service account, Cloud Monitoring, Cloud Billing và CI/CD/IaC**. Khi workload chuyển sang GKE, Cloud Run hoặc database được quản lý, cần đánh giá phụ thuộc và cơ chế điều phối trước khi ngừng VM cũ. Một thao tác chỉ thực sự an toàn khi **đúng tài nguyên, đúng quyết định dữ liệu, có quyền/phê duyệt, có phương án phục hồi và kết quả được xác minh**.



