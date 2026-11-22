# Secret, persistent volume và quan sát Container Apps

Một API chạy trên **Azure Container Apps** cần mật khẩu kết nối cơ sở dữ liệu, phải ghi tệp báo cáo để những replica khác cùng đọc, đồng thời đội vận hành cần tìm nguyên nhân khi một revision liên tục khởi động lại. Ba nhu cầu này thuộc ba lớp khác nhau: **secret** bảo vệ thông tin nhạy cảm, **persistent volume** duy trì dữ liệu ngoài vòng đời container, còn **observability** giúp nhìn thấy trạng thái, nhật ký và hiệu năng của ứng dụng đang chạy.

Nếu chỉ đóng gói toàn bộ cấu hình trong container image, ghi tệp vào filesystem cục bộ rồi xem vài dòng log trên màn hình, hệ thống có thể hoạt động ở máy phát triển nhưng gặp vấn đề khi scale-out, cập nhật revision hoặc khởi động lại replica. Bài học này hướng dẫn tổ chức ba lớp trên một cách thực tế, có khả năng phục hồi và kiểm toán.

Nội dung thuộc chương **Container Registry và Container Apps** của module `CLOUD_PROVIDERS_AZURE`. Module khám phá hệ sinh thái Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, tính toán, lưu trữ và dữ liệu; đồng thời hướng dẫn triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng. Ở đây, trọng tâm là **Azure Container Apps**, không phải Kubernetes cluster do người học trực tiếp quản trị.

> Các ví dụ minh họa sử dụng Container Apps chạy trong một managed environment, volume dựa trên Azure Files và secret tham chiếu Azure Key Vault. Tên lệnh, giới hạn mount, cơ chế xác thực và tính năng log có thể khác theo phiên bản Azure CLI, loại môi trường và khả năng dịch vụ. Khi triển khai thật, đối chiếu cấu hình được hỗ trợ trong subscription/region đang sử dụng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Container Apps environment**, **container app**, **revision**, **replica** và **container**.
2. Giải thích khác biệt giữa **secret**, environment variable thường và cấu hình nằm trong image.
3. Quản lý secret cấp ứng dụng, sử dụng `secretRef` và tích hợp **Azure Key Vault** bằng managed identity khi được hỗ trợ.
4. Lập quy trình xoay vòng secret, khởi động lại hoặc triển khai revision để cập nhật giá trị một cách an toàn.
5. Phân biệt **filesystem ghi được của container**, **EmptyDir** và **Azure Files persistent volume**.
6. Cấu hình volume ở cấp environment và mount volume vào container của một revision.
7. Nhận diện rủi ro ghi đồng thời, khóa tệp, dữ liệu tạm, backup và network khi dùng Azure Files.
8. Xem **console logs**, **system logs**, Azure Monitor metrics và distributed traces.
9. Viết truy vấn Log Analytics, tạo cảnh báo và liên hệ log với revision, replica, request ID.
10. Chẩn đoán các lỗi secret không đọc được, mount thất bại, replica restart, scale-to-zero hoặc ứng dụng không có log.
11. Thiết kế giải pháp cân bằng tính bảo mật, độ bền dữ liệu, hiệu năng và chi phí.

## 2. Hiểu đúng đơn vị vận hành trong Container Apps

Azure Container Apps là nền tảng chạy container theo mô hình managed, có các khả năng như **HTTP/TCP ingress theo cấu hình hỗ trợ**, revisions, scaling và tích hợp logging/monitoring.

| Đối tượng | Vai trò | Ảnh hưởng khi thay đổi |
|---|---|---|
| **Container Apps environment** | Ranh giới dùng chung cho một nhóm Container Apps: hạ tầng mạng, cấu hình logs, và các cấu hình môi trường như storage mount. | Thay đổi có thể ảnh hưởng nhiều ứng dụng dùng chung environment. |
| **Container app** | Tài nguyên logic chứa cấu hình ứng dụng, ingress, secret cấp app và các revision. | Có thể có nhiều revision theo revision mode. |
| **Revision** | Bản bất biến về template triển khai như image, container env, volumes, scale rules theo khả năng cấu hình. | Thay đổi template thường tạo revision mới; một số cấu hình cấp app không làm vậy. |
| **Replica** | Một instance chạy của revision, gồm một hoặc nhiều container/sidecar theo template. | Có thể được tạo, thu hồi hoặc khởi động lại khi scale/rollout. |
| **Container** | Tiến trình, image, env vars và các volume mounts được khai báo. | Filesystem nội bộ không nên được xem là lưu trữ bền vững. |
| **Container Apps Job** | Cơ chế chạy workload theo lần thực thi, lịch hoặc event. | Không đồng nhất hoàn toàn với revision/ingress và vòng đời của app phục vụ lâu dài. |

### Mô hình hai revision và nhiều replica

```text
Container Apps environment: cae-orders-prod
│
├── Storage mapping: reports-storage --> Azure Files share
├── Logging destination: Log Analytics / nơi được hỗ trợ
│
└── Container App: orders-api
    ├── App-level secret: db-password
    ├── App-level ingress: HTTPS endpoint
    │
    ├── Revision: orders-api--r1
    │   ├── Replica A --> container orders-api
    │   └── Replica B --> container orders-api
    │
    └── Revision: orders-api--r2
        ├── Replica C --> container orders-api
        └── Replica D --> container orders-api
```

Chế độ **single revision** và **multiple revisions** có hành vi triển khai/traffic khác nhau. Với multiple revisions, có thể chia traffic giữa các revision theo cấu hình. **Một secret của container app không phải secret riêng biệt của mỗi replica**, trong khi các biến môi trường được khai báo trong revision template quyết định cách mỗi container tham chiếu secret đó.

## 3. Ba lớp dữ liệu phải được thiết kế riêng

| Dữ liệu | Ví dụ | Nơi đặt hợp lý | Không nên làm |
|---|---|---|---|
| **Secret** | API token, mật khẩu DB, connection string nhạy cảm. | App-level secret hoặc tham chiếu Key Vault qua managed identity. | Ghi trực tiếp vào Dockerfile, Git, log hoặc image. |
| **Cấu hình không nhạy cảm** | `LOG_LEVEL=info`, tên queue, feature flag không nhạy cảm. | Environment variables hoặc hệ thống cấu hình theo chính sách. | Dùng secret chỉ vì biến nào cũng phải “bí mật”. |
| **Trạng thái bền vững** | File báo cáo, tài liệu người dùng, dữ liệu dùng chung. | Azure Files, Blob Storage, database hoặc dịch vụ lưu trữ chuyên dụng. | Chỉ ghi vào writable layer của container. |
| **Dữ liệu tạm** | Cache có thể dựng lại, file trung gian ngắn hạn. | EmptyDir hoặc scratch phù hợp. | Đặt trên persistent share nếu không cần. |
| **Logs/metrics/traces** | Exception, request ID, latency, lỗi scale. | stdout/stderr, Azure Monitor, Log Analytics và backend tracing. | Chỉ ghi vào một tệp local dễ mất. |

Một Container App được thiết kế tốt thường **stateless ở lớp phục vụ HTTP**: container có thể bị thay thế bất kỳ lúc nào, còn dữ liệu quan trọng phải nằm ngoài vòng đời replica.

## 4. Secret trong Azure Container Apps là gì?

**Secret** là một mục cấu hình chứa giá trị cần bảo vệ, được quản lý ở **cấp container app**. Ứng dụng không phải ghi giá trị đó vào image; container có thể tham chiếu secret qua biến môi trường hoặc các cơ chế được nền tảng hỗ trợ.

Ví dụ ứng dụng cần:

- `DB_PASSWORD` để kết nối cơ sở dữ liệu.
- `PAYMENT_API_TOKEN` để gọi dịch vụ thanh toán.
- Một credential cho scale rule hoặc tích hợp cụ thể được hỗ trợ.

Trong Container Apps, tên secret có thể là `db-password`; container dùng **`secretRef: db-password`** để đưa giá trị vào biến `DB_PASSWORD`. Hai tên thuộc hai cấp cấu hình khác nhau.

### Phân biệt cấu hình thông thường và secret

```text
App-level secrets
  db-password  ──────────────┐
                             │ tham chiếu qua secretRef
Revision template            ▼
  Container: orders-api
    env:
      LOG_LEVEL   = info                 (giá trị thường)
      DB_PASSWORD = secretref:db-password (giá trị nhạy cảm)
```

**Không nên đặt mật khẩu trực tiếp vào `env.value`** dù container vẫn đọc được. Giá trị có thể bị lộ trong template, CLI output, IaC state hoặc hệ thống kiểm toán không được thiết kế để chứa secrets. Thay vào đó, khai báo secret riêng rồi tham chiếu bằng tên.

### Một secret không tự tạo quyền truy cập

Ví dụ một container có secret chứa token hợp lệ nhưng **network firewall** chặn đường đến database, ứng dụng vẫn không kết nối được. Ngược lại, mở mạng tới database không thay thế được credential hợp lệ. Phải kiểm tra đồng thời **secret, identity, networking và quyền của hệ thống đích**.

## 5. Secret cấp ứng dụng và ranh giới revision

Đây là một trong những khác biệt quan trọng nhất khi vận hành Container Apps:

- **Secret nằm ở cấu hình cấp container app**, không được đóng băng như một phần của template bất biến của mỗi revision theo cùng cách image/env template được phiên bản hóa.
- **Environment variable tham chiếu secret** nằm trong template container của revision.
- Thêm, sửa hoặc xóa app-level secret **không nhất thiết tạo revision mới**.
- Một tiến trình container nhận environment variable khi khởi động **không nên được giả định sẽ tự thay đổi giá trị trong bộ nhớ ngay khi secret được xoay vòng**.
- Sau khi cập nhật secret, cần kiểm tra cơ chế refresh của nguồn secret và nền tảng. Với secret cập nhật cấp app, thường phải **restart revision** hoặc **deploy revision mới** theo quy trình được hỗ trợ để container dùng giá trị mới; tham chiếu Key Vault có hành vi làm mới riêng.

### Ví dụ vòng đời

```text
09:00  Secret db-password = version A
       Revision r1 bắt đầu chạy, đọc DB_PASSWORD=A

10:00  Nhóm bảo mật đổi credential sang version B
       App secret hoặc Key Vault reference được cập nhật

10:01  Không được giả định tiến trình r1 đã nhận B
       → Xác minh cơ chế refresh/restart theo loại secret

10:05  Rollout/restart an toàn, theo dõi replica mới
       → Kiểm tra kết nối DB thành công với B

10:15  Thu hồi A sau khi xác minh không còn phụ thuộc
```

**Chú ý với Key Vault reference:** khi tham chiếu phiên bản không cố định, nền tảng có thể cập nhật tham chiếu và khởi động lại các revision đang dùng secret theo hành vi được tài liệu hỗ trợ. Không thay quy trình kiểm thử bằng giả định “mọi secret cần restart tay” hoặc “mọi secret tự động cập nhật tức thì”. Hãy đo thời gian phát hiện giá trị mới và xác minh revision/replica thật sự sử dụng credential mới.

## 6. Dùng Azure Key Vault và managed identity

Với môi trường Production, cách quản lý secret tập trung thường là để **giá trị thật ở Azure Key Vault** và để Container Apps **tham chiếu** secret bằng managed identity.

### Các thành phần

1. **Key Vault:** chứa secret, phiên bản, chính sách rotation và audit.
2. **Managed identity:** danh tính Azure của container app, có thể là system-assigned hoặc user-assigned theo tính năng hỗ trợ.
3. **Azure RBAC/Key Vault access policy:** cho phép identity thực hiện **Get secret** cần thiết, không cấp toàn bộ quyền quản trị vault.
4. **Network access:** nếu vault bị giới hạn mạng, Container Apps environment phải có đường truy cập phù hợp.
5. **Container Apps secret reference:** trỏ đến secret trong Key Vault, dùng identity tương ứng.
6. **Revision template:** tham chiếu tên app-level secret bằng `secretRef`.

### Trình tự cấu hình đề xuất

1. Tạo hoặc chọn Key Vault trong tenant/subscription được phê duyệt.
2. Tạo một secret thử, ví dụ `orders-db-password`; không dùng mật khẩu Production trong bài học.
3. Bật managed identity trên Container App.
4. Cấp role đọc secret thích hợp (ví dụ **Key Vault Secrets User** trong mô hình Azure RBAC phù hợp) ở scope hẹp nhất cần thiết.
5. Xác minh network/DNS cho phép ứng dụng và dịch vụ nền tảng truy cập vault theo cơ chế hỗ trợ.
6. Tạo app-level secret tham chiếu đến URL của Key Vault secret bằng identity đó.
7. Tham chiếu app secret trong revision template.
8. Kiểm thử kết nối tới hệ thống đích; không in giá trị secret để “xác minh”.
9. Thiết lập monitoring khi Key Vault access bị từ chối hoặc secret hết hiệu lực.

**Managed identity thay thế nhu cầu lưu client secret dành cho việc xác thực tới Key Vault.** Điều đó không có nghĩa mọi dịch vụ đích đều tự hỗ trợ đăng nhập managed identity. Nếu database hỗ trợ Microsoft Entra authentication, nên cân nhắc bỏ hẳn mật khẩu ứng dụng khi phù hợp.

## 7. Mẫu YAML: app secret, Key Vault và secretRef

Đoạn dưới đây minh họa **các trường cấu hình liên quan**, không phải manifest đầy đủ có thể áp dụng nguyên trạng. Tên image, URL vault và identity chỉ là placeholder; app phải được cấu hình identity và quyền trước đó.

```yaml
configuration:
  secrets:
    - name: db-password
      keyVaultUrl: https://kv-orders.example.vault.azure.net/secrets/db-password
      identity: system

template:
  containers:
    - name: orders-api
      image: example.azurecr.io/orders-api:1.0.0
      env:
        - name: LOG_LEVEL
          value: info
        - name: DB_PASSWORD
          secretRef: db-password
```

**Đọc cấu hình theo hai tầng:**

- `configuration.secrets`: khai báo secret cấp app (tham chiếu Key Vault).
- `template.containers[].env[].secretRef`: biến môi trường của container nhận giá trị từ secret.

URL trong ví dụ chỉ minh họa cấu trúc. Trong thực tế dùng URL thật có dạng `https://<vault-name>.vault.azure.net/secrets/<secret-name>`; tên vault phải hợp lệ và đã tồn tại. Nếu dùng user-assigned identity, trường identity cần chỉ đúng resource ID/danh tính theo schema đang được hỗ trợ, không giữ mặc định `system`.

### Không đặt secret trong code hoặc trong terminal history

Ví dụ không nên làm:

```bash
# KHÔNG làm: mật khẩu xuất hiện trực tiếp trong lịch sử lệnh.
az containerapp update --name orders-api \
  --resource-group rg-apps \
  --set-env-vars "DB_PASSWORD=MyProductionPassword"
```

Đây là **ví dụ phản diện**, không phải lệnh cần thực thi. Tránh sử dụng những lệnh chứa giá trị bí mật trong đối số. Dùng Key Vault references, managed identity và workflow triển khai bảo vệ dữ liệu nhạy cảm.

### Các giới hạn khi sửa secret

- Thay secret có thể ảnh hưởng **nhiều revision** dùng chung tham chiếu.
- Xóa secret vẫn còn được revision/scale rule sử dụng có thể gây lỗi khởi động hoặc lỗi xác thực.
- Một token có thời hạn có thể hết hạn trong khi replica vẫn chạy; ứng dụng cần retry, refresh/redeploy theo thiết kế.
- Secret ở environment variable có thể bị chính ứng dụng tiết lộ qua crash report, debug endpoint hoặc log nếu lập trình sai.
- Quyền xem metadata app và quyền truy cập giá trị secret phải được kiểm soát khác nhau; không cấp quyền đọc giá trị chỉ để kiểm tra tên secret.

## 8. Quy trình rotation và thu hồi secret an toàn

Một **rotation** tốt có kiểm thử và kế hoạch rollback. Giả sử cần thay mật khẩu của user database do ứng dụng dùng:

1. **Lập phạm vi:** những container apps, revisions, jobs hoặc kết nối nào sử dụng credential cũ?
2. **Chuẩn bị credential mới:** nếu hệ thống đích cho phép, tạo credential mới song song để tránh cắt kết nối đang chạy.
3. **Cập nhật Key Vault:** tạo phiên bản mới hoặc secret mới theo mô hình đã thiết kế.
4. **Xác minh quyền và khả năng truy cập:** managed identity có quyền Get; cấu hình DNS/network không chặn.
5. **Triển khai an toàn:** theo cơ chế secret được hỗ trợ, restart revision hoặc tạo revision mới; có thể dùng phân chia traffic để giảm rủi ro trong multiple revisions mode.
6. **Kiểm tra:** đọc metrics kết nối DB, log lỗi, health probe và tỷ lệ HTTP 5xx của các replica mới.
7. **Thu hồi credential cũ:** chỉ sau khi chắc chắn mọi consumer đã chuyển đổi.
8. **Ghi bằng chứng:** thời gian, người phê duyệt, đối tượng ảnh hưởng, bản secret và kết quả.
9. **Rollback:** nếu phát hiện lỗi, có phương án khôi phục kết nối mà không ghi lại secret vào chat/ticket.

**Không đặt log thông báo** kiểu `"DB_PASSWORD is " + password`. Khi kiểm thử chỉ ghi “secret loaded” hoặc trạng thái kiểm tra kết nối, không log giá trị, prefix, suffix hoặc token.

## 9. Vì sao container filesystem không phải persistent storage?

Mỗi replica có vòng đời riêng. Container Apps có thể tạo hoặc thu hồi replica khi autoscale, update revision, host maintenance, retry hay failure.

Hãy giả sử ứng dụng ghi `/app/uploads/customer.pdf` vào writable layer của container:

```text
Replica A:
  /app/uploads/customer.pdf  ← có dữ liệu

Replica B:
  /app/uploads/              ← không có file của A

Replica A bị thay thế:
  dữ liệu chỉ nằm trên writable layer có thể mất
```

Điều đó gây hai lỗi phổ biến:

- Người dùng upload qua replica A, lần tải lại đi vào replica B và nhận 404 vì file không tồn tại ở B.
- Sau khi rollout image hoặc scale-to-zero rồi scale lại, file ở writable layer cũ không còn.

Quy tắc: **container image + local writable filesystem không phải nơi lưu bản duy nhất của dữ liệu quan trọng**. Chọn storage độc lập với vòng đời replica, hoặc thiết kế app stateless với Blob Storage/database.

## 10. So sánh EmptyDir, Azure Files và các hướng lưu dữ liệu khác

| Cơ chế | Vòng đời/khả năng chia sẻ | Dùng cho | Không nên dùng cho |
|---|---|---|---|
| **Container writable layer** | Gắn với instance container; không có cam kết bền vững khi bị thay thế. | Tệp tạm nhỏ, cache có thể tái tạo. | File người dùng, checkpoint duy nhất. |
| **EmptyDir volume** | Dữ liệu tạm thuộc vòng đời **replica** và có thể được các container trong replica chia sẻ theo mount. | Scratch, file trao đổi giữa sidecars trong một replica. | Dữ liệu cần tồn tại sau khi replica mất hoặc dùng chung giữa replicas. |
| **Azure Files volume** | File share tồn tại ngoài replica, có thể được mount bởi các replicas theo cấu hình hỗ trợ. | File cần chia sẻ, xuất báo cáo, một số ứng dụng cần filesystem. | Giả định thay thế database transaction hoặc filesystem hiệu năng cao ở mọi workload. |
| **Azure Blob Storage** | Object storage bền vững, truy cập qua SDK/API; không tự là filesystem POSIX thông thường. | Uploads, artifacts, media, logs/exports, tệp lớn. | App bắt buộc thao tác POSIX atomic lock theo cách Blob API không cung cấp. |
| **Database/managed state store** | Trạng thái được quản lý theo mô hình DB. | Session, đơn hàng, transactional state. | Tệp lớn đơn giản nếu object storage phù hợp hơn. |

**EmptyDir không có nghĩa “đĩa được cấp cố định mãi mãi”.** Khi replica bị thu hồi, dữ liệu tạm không phải recovery point. Với multi-replica workloads, mỗi replica có không gian EmptyDir riêng, không dùng chung cho toàn ứng dụng.

### Quy tắc chọn

- **Tệp người dùng tải lên:** ưu tiên Blob Storage nếu ứng dụng hỗ trợ object API.
- **Thư mục cần mount và chia sẻ:** Azure Files khi thỏa yêu cầu giao thức/performance.
- **Cache/temporary processing:** EmptyDir khi mất có thể tính toán lại.
- **Session và transactional state:** Redis/database theo yêu cầu consistency và SLA.
- **Cấu hình nhạy cảm:** secret/Key Vault, không đặt trong file chung chỉ để tránh dùng secretRef.

## 11. Mô hình Azure Files persistent volume trong Container Apps

Với Azure Files mount, cần phân biệt **hai đối tượng cấu hình**:

1. **Environment-level storage:** Container Apps environment được cấu hình thông tin kết nối tới một Azure Files share, thường bằng tên logical storage mapping. Tại lớp này, môi trường cần phương thức xác thực share được tính năng hỗ trợ.
2. **App revision volume:** revision template khai báo volume dùng tên storage mapping đó, sau đó **volumeMounts** đưa volume vào đường dẫn trong container.

```text
Azure Storage account: stordersfiles
    |
    +-- File share: reports
             |
             | SMB / network + credentials theo cấu hình hỗ trợ
             v
Container Apps environment: cae-orders-prod
    |
    +-- environment storage mapping: reports-storage
             |
             v
Container App: orders-api
    |
    +-- Revision template
          |
          +-- volume name: reports-volume
          |     storageType: AzureFile
          |     storageName: reports-storage
          |
          +-- container volumeMount:
                /mnt/reports
```

**Volume này không phải Kubernetes PersistentVolumeClaim (PVC) do bạn tạo thủ công**. Container Apps có cơ chế khai báo managed storage mounts riêng; đừng sao chép máy móc manifest `PersistentVolume`/`PersistentVolumeClaim` của AKS vào app YAML mà mong chúng được hiểu giống nhau.

### Điều kiện phải kiểm tra

- Storage account và file share đã tồn tại.
- Loại giao thức Azure Files và cơ chế mount được Container Apps environment hỗ trợ (ví dụ SMB trong kịch bản phổ biến).
- Đường kết nối mạng từ environment tới Storage, bao gồm firewall, DNS và private endpoint nếu dùng private access.
- Credential/cách xác thực của environment storage mapping hợp lệ và được bảo vệ.
- Tên storage mapping khớp với `storageName` trong app volume.
- Quyền truy cập read-only/read-write, cấu hình OS user, file permissions và đường dẫn mount.
- Quota, IOPS, throughput, latency và số kết nối của Azure Files phù hợp tải ứng dụng.

Một app container nhận secret từ Key Vault **không đồng nghĩa** Azure Files mount tự dùng chính managed identity đó. Cơ chế xác thực environment storage có cấu hình riêng; tránh suy diễn quyền Identity → Key Vault cũng cấp quyền Azure Files SMB mount.

## 12. YAML mẫu: Azure Files volume và volumeMounts

Đây là **đoạn trích cấu hình**, giả sử environment đã có storage mapping `reports-storage` trỏ tới một file share và ứng dụng có image phù hợp.

```yaml
template:
  containers:
    - name: orders-api
      image: example.azurecr.io/orders-api:1.0.0
      env:
        - name: REPORT_DIRECTORY
          value: /mnt/reports
      volumeMounts:
        - volumeName: reports-volume
          mountPath: /mnt/reports

  volumes:
    - name: reports-volume
      storageType: AzureFile
      storageName: reports-storage
```

Đọc đường liên kết:

- `template.volumes[].name` là tên volume **trong revision**.
- `storageType: AzureFile` chỉ ra loại mount.
- `storageName: reports-storage` tham chiếu storage mapping **ở environment**.
- `volumeMounts[].volumeName` liên kết container với volume.
- `mountPath` là đường dẫn ứng dụng sẽ đọc/ghi.

**Lỗi rất phổ biến:** environment có tên storage `reports-storage` nhưng revision dùng `storageName: report-storage` (thiếu chữ `s`). Kết quả mount có thể thất bại dù storage account/file share vẫn hoạt động.

### Mẫu EmptyDir cho scratch

```yaml
template:
  containers:
    - name: processor
      image: example.azurecr.io/processor:1.0.0
      volumeMounts:
        - volumeName: scratch
          mountPath: /tmp/work

  volumes:
    - name: scratch
      storageType: EmptyDir
```

Nếu dùng chung EmptyDir với sidecar trong **cùng replica**, thêm volumeMount thích hợp cho sidecar; **không** kỳ vọng sidecar ở replica khác đọc được file đó.

### Không nhầm đường dẫn volume với dữ liệu cũ trong image

Mount một volume vào đường dẫn đã có file trong image có thể **che nội dung bên dưới** đường dẫn mount trong runtime. Vì vậy chọn `/mnt/reports` thay vì đặt volume lên thư mục chứa binary/cấu hình quan trọng của ứng dụng. Với rolling update, hai revisions có thể đồng thời mount chung share; ứng dụng phải an toàn khi đọc/ghi song song.

## 13. Persistent không đồng nghĩa dữ liệu luôn nhất quán và an toàn

Một file share bền vững có thể tồn tại sau khi container bị thay thế, nhưng cần hiểu:

### Nhiều replicas ghi cùng một file

Giả sử replica A và B đồng thời ghi `/mnt/reports/status.json`. Kết quả có thể là:

- Ghi đè lẫn nhau.
- Đọc thấy file chưa hoàn chỉnh.
- Tranh chấp file lock hoặc lỗi truy cập tùy ứng dụng/giao thức.
- Một replica cache thông tin cũ trong khi replica khác đã ghi.

Azure Files cung cấp semantics giao thức hỗ trợ, nhưng **không tự chuyển một ứng dụng không xử lý concurrency thành hệ thống giao dịch an toàn**.

Những cách phòng tránh:

- Dùng tên file duy nhất theo job/request ID.
- Ghi ra file tạm, flush/validate rồi đổi tên theo cơ chế filesystem hỗ trợ.
- Dùng hàng đợi/worker phân chia quyền ghi hoặc distributed lock phù hợp.
- Đặt dữ liệu transactional vào database thay vì file share.
- Kiểm thử ứng dụng với **ít nhất hai replica** và rolling revision deployment.

### Persistent volume không phải backup

Nếu người dùng xóa nhầm file trên Azure Files, các replicas nhìn thấy dữ liệu đã xóa theo hành vi share. Persistent volume chỉ nói dữ liệu **không gắn với vòng đời replica**; nó không tạo lịch sử phiên bản hay bảo vệ khỏi ransomware.

Cần đánh giá:

- Azure Files snapshots/backup và soft delete cho share khi được hỗ trợ.
- Retention, RPO/RTO, recovery target và khả năng khôi phục file.
- Redundancy LRS/ZRS/GRS/GZRS theo loại account/region.
- Quyền xóa file/share, access key rotation, logging.
- Sự cố mất storage account, network hoặc region.

## 14. Network, identity và hiệu năng của Azure Files mount

Một mount có thể thất bại mặc dù tài khoản Storage tồn tại và key còn đúng. Phải kiểm tra **đường mạng từ Container Apps environment đến Azure Files**.

### Mạng

- Với storage account có firewall, xác định traffic từ environment có được phép không.
- Nếu dùng private endpoint, cần private DNS resolution đúng cho endpoint Azure Files và route tới private IP.
- Kiểm tra những cổng/giao thức mà Azure Files yêu cầu (ví dụ SMB trên TCP 445 trong kịch bản SMB).
- Không nhầm ingress HTTPS của Container App với outbound network từ replica đến Azure Files.
- Nếu egress qua firewall/UDR, kiểm tra luồng Storage không bị chặn nhầm.

### Credential

- Environment storage mapping thường có cấu hình riêng cho thông tin xác thực share theo cơ chế hỗ trợ, chẳng hạn storage account key trong những kịch bản Azure Files mount.
- Không in account key trong ticket, Terraform plan công khai, file YAML chia sẻ hoặc command history.
- Khi xoay vòng key, cập nhật mapping/credential theo thứ tự đã được kiểm tra để tránh mất mount.
- Kiểm tra các cách auth khác theo khả năng hỗ trợ thực tế; **không giả định managed identity dùng cho app secret cũng tự cấp quyền mount**.

### Hiệu năng

- Một file share có giới hạn dung lượng, IOPS và throughput theo loại/tier đã chọn.
- Tăng số replica có thể làm tăng số thao tác đọc/ghi cùng share, biến storage thành nút thắt.
- Nhiều file rất nhỏ có thể tạo nhiều metadata operations.
- Mạng private/region và kích thước file ảnh hưởng latency.
- Theo dõi Azure Files metrics và ứng dụng, không chỉ CPU của container.

Nếu workload chỉ xuất vài file báo cáo theo giờ, Azure Files có thể phù hợp. Nếu ứng dụng phục vụ hàng triệu ảnh hoặc uploads qua Internet, Blob Storage/ứng dụng thiết kế dùng object API thường là lựa chọn vận hành tốt hơn.

## 15. Quan sát Container Apps gồm ba trụ cột

**Observability** trả lời ba câu hỏi khác nhau:

- **Logs:** điều gì đã xảy ra, lỗi nào xuất hiện ở thời điểm nào?
- **Metrics:** hệ thống có dấu hiệu bất thường về số replica, request rate, CPU, memory, latency hay errors không?
- **Traces:** một request đi qua những dịch vụ nào, thành phần nào làm chậm hoặc thất bại?

| Trụ cột | Ví dụ | Công cụ/nguồn dữ liệu |
|---|---|---|
| Logs | Exception, startup log, probe failure, scale event. | Console logs, system logs, Log Analytics và logging destination được cấu hình. |
| Metrics | Replica count, CPU/memory utilization, requests, errors, latency. | Azure Monitor metrics, dashboards và alert rules. |
| Traces | Request HTTP → API → database → queue worker. | Application Insights/OpenTelemetry hoặc tích hợp tracing được cấu hình. |

**Không mặc định chỉ cần bật Container Apps là có đầy đủ distributed tracing**. Trace end-to-end thường cần instrumentation, exporter/agent và backend lưu trữ phù hợp. Có log và metric không tự tạo span cho mọi request.

## 16. Console logs và system logs: đọc đúng nguồn

Azure Container Apps phân biệt hai nhóm quan trọng:

### Console logs

Đây là output của ứng dụng/container trên **stdout** và **stderr**, ví dụ:

```text
2026-11-20T08:00:00Z level=info service=orders-api revision=r12
  event=startup completed

2026-11-20T08:02:14Z level=error service=orders-api revision=r12
  event=storage_write_failed request_id=demo-4 reason=timeout
```

Nếu ứng dụng chỉ ghi log vào `/app/logs/service.log` trong filesystem container mà không có cơ chế ship logs, output đó **không tự xuất hiện** trong console logs. Với Container Apps, nên ghi log ứng dụng ra stdout/stderr theo định dạng có cấu trúc.

### System logs

Đây là sự kiện do **nền tảng Container Apps** phát ra, có thể giúp điều tra:

- Revision được tạo hoặc kích hoạt.
- Replica/Container bắt đầu hoặc thất bại.
- Image pull, cấu hình/container startup lỗi.
- Health probe thất bại.
- Scale operations, sự cố liên quan môi trường.
- Volume mount hoặc cấu hình runtime lỗi khi nền tảng có ghi nhận.

**System logs không thay thế console logs.** Nếu app crash do exception trước khi khởi tạo server, console log cho stack trace còn system log có thể giúp biết replica restart và lỗi probe.

### Thêm context vào mỗi log

Một sự kiện nên có các trường phù hợp:

- `timestamp` (UTC).
- `service` và `revision`.
- `replica` hoặc instance identifier khi có.
- `request_id` / `trace_id`.
- `severity`, `event`, `duration_ms`.
- Loại lỗi, dependency, mã HTTP.
- `job_id` cho background processing.

**Không log:** password, access token, Storage account key, full connection string, thông tin thẻ thanh toán hoặc dữ liệu cá nhân không cần thiết.

## 17. Quan sát revisions, replicas và scaling

Container Apps có thể scale dựa trên HTTP concurrency, CPU/memory hoặc những event sources được hỗ trợ qua KEDA. Khi workload tăng, nhiều replica được tạo; khi hết tải, replica có thể giảm về số tối thiểu đã cấu hình, kể cả **scale-to-zero** nếu app/scale rule hỗ trợ.

### Điều cần kiểm tra

| Tín hiệu | Câu hỏi |
|---|---|
| **Active revisions** | Revision nào đang nhận traffic? Có revision cũ còn hoạt động không? |
| **Replica count** | App có đủ replica khi tải tăng? Có scale quá chậm không? |
| **Min/max replicas** | Ngưỡng scale có phù hợp tính chất traffic và ngân sách? |
| **CPU/memory usage** | Có throttling, OOM hoặc request limit không? |
| **Request rate/error rate** | Lỗi tăng sau rollout hay khi scale-out? |
| **Latency p95/p99** | Một nhóm request có chậm dù average vẫn ổn? |
| **Scale triggers** | Rule hoặc secret dùng để xác thực nguồn event còn hợp lệ? |
| **Restart/termination** | Replica restart do crash, health probe, thay revision hay scale action? |

Một app ở `minReplicas: 0` có thể **không có replica chạy** khi chưa có traffic/event. Việc không thấy console log mới trong thời gian rảnh không chứng minh logging đã hỏng. Nhưng nếu ứng dụng cần xử lý tác vụ liên tục, phải bảo đảm loại trigger và min replica phù hợp.

### Revision rollout và quan sát

Giả sử r12 mới được đưa vào hoạt động:

1. Xem số replica Ready/Healthy của r12.
2. Kiểm tra console logs r12 cho startup, secret và volume mount errors.
3. So sánh HTTP 5xx/p95 latency giữa r11 và r12.
4. Nếu multiple revisions mode, điều chỉnh traffic theo chiến lược rollout được hỗ trợ.
5. Nếu r12 lỗi, quay lại r11 theo quy trình; **lưu ý rollback revision không tự hoàn tác dữ liệu ghi trên Azure Files hoặc trong database**.

## 18. Dùng Azure Portal để xem logs và metrics

Một quy trình vận hành cơ bản:

1. Mở [Azure Portal](https://portal.azure.com/) và chọn đúng subscription.
2. Mở **Container Apps**, chọn ứng dụng cần kiểm tra.
3. Xem **Revisions and replicas** để xác nhận revision, trạng thái và số replica.
4. Vào **Log stream** hoặc **Logs** theo giao diện hiện tại; chọn đúng container và loại log.
5. So sánh console log với system log tại **cùng thời điểm UTC**.
6. Mở **Metrics** để xem requests, CPU, memory, replicas và những metrics đang được hỗ trợ.
7. Nếu environment gửi logs tới Log Analytics, mở workspace và truy vấn theo app/revision/time.
8. Kiểm tra **Alerts** để xác định sự kiện nào đã kích hoạt cảnh báo.
9. Nếu ứng dụng có tracing, mở Application Insights/trace backend để kiểm tra request bị ảnh hưởng.

**Một trang Log stream hiển thị được log không có nghĩa retention dài hạn đã được cấu hình.** Phải kiểm tra logging destination, workspace, thời gian giữ dữ liệu, sampling và giới hạn ingestion.

## 19. Đọc tình trạng bằng Azure CLI

Các lệnh bên dưới **chỉ đọc metadata hoặc log**, không yêu cầu giá trị secret và không thay đổi app. Thay placeholder tương ứng. Nếu CLI báo thiếu lệnh, kiểm tra phiên bản/extension **containerapp** bằng hướng dẫn CLI trong môi trường được phép.

### Xác minh context

```bash
az account show \
  --query "{Name:name,Subscription:id,Tenant:tenantId}" \
  --output table
```

### Xem app và revision

```bash
az containerapp show \
  --name "<APP_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --query "{name:name,revisionMode:properties.configuration.activeRevisionsMode,minReplicas:properties.template.scale.minReplicas,maxReplicas:properties.template.scale.maxReplicas}" \
  --output json

az containerapp revision list \
  --name "<APP_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --output table
```

### Liệt kê tên secrets, không xuất giá trị

```bash
az containerapp secret list \
  --name "<APP_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --query "[].name" \
  --output tsv
```

Mục tiêu là xem **tên secret đã được cấu hình**. Tránh dùng tùy chọn hiện giá trị, ghi toàn bộ cấu hình nhạy cảm vào file log hoặc gửi kết quả CLI chứa secret cho người không được cấp quyền.

### Liệt kê storage mappings của environment

```bash
az containerapp env storage list \
  --name "<ENVIRONMENT_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --output table
```

Tên storage mapping ở environment phải tương ứng với `storageName` trong template revision. Lệnh đọc listing không chứng minh file share đã mount thành công tại replica; cần kiểm tra system logs/đường dẫn mount.

### Xem console logs và system logs

```bash
az containerapp logs show \
  --name "<APP_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --type console \
  --tail 50

az containerapp logs show \
  --name "<APP_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --type system \
  --tail 50
```

Có thể cần chọn thêm revision, replica hoặc container trong ứng dụng có nhiều thành phần. Kiểm tra `az containerapp logs show --help` để biết các tùy chọn của phiên bản CLI. Với incident, ghi lại thời gian UTC và nguồn log để không trộn log từ revision trước với revision đang chạy.

## 20. Truy vấn Log Analytics bằng KQL

Khi Container Apps environment gửi logs tới **Log Analytics**, bạn có thể tìm sự kiện theo app và thời gian. Tên bảng và schema có thể khác theo cách kết nối logging và các phiên bản dịch vụ; trong nhiều workspace có các bảng như `ContainerAppConsoleLogs_CL` và `ContainerAppSystemLogs_CL`.

### Tìm log lỗi ứng dụng

```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(2h)
| where ContainerAppName_s == "orders-api"
| where Log_s has_any ("error", "exception", "failed")
| project TimeGenerated, ContainerAppName_s, RevisionName_s,
          ContainerName_s, Log_s
| order by TimeGenerated desc
```

### Tìm lỗi nền tảng

```kusto
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(2h)
| where ContainerAppName_s == "orders-api"
| project TimeGenerated, RevisionName_s, Log_s
| order by TimeGenerated desc
```

Đây là **ví dụ truy vấn theo schema tham khảo**. Nếu workspace dùng tên bảng `ContainerAppConsoleLogs` hoặc tên cột khác, hãy mở **Tables/Schema** trong Log Analytics, xác minh dữ liệu thực tế rồi điều chỉnh truy vấn. Không kết luận “không có lỗi” chỉ vì copy truy vấn ở một schema khác và trả về rỗng.

### Kết hợp log với metrics và trace

Giả sử dashboard báo HTTP 5xx tăng lúc 08:15:

1. Chọn khung thời gian 08:10–08:20 UTC.
2. Tìm lỗi console logs của revision đang nhận traffic.
3. Xem system logs có sự kiện crash, probe fail, volume mount hoặc scale không.
4. Nếu có trace ID trong log, mở trace backend để biết dependency nào timeout.
5. Đối chiếu metric Azure Files/Storage, Key Vault hoặc database nếu lỗi liên quan các dịch vụ này.

Một chuỗi log có chữ `timeout` chưa đủ để kết luận timeout nằm ở database; phải đối chiếu request ID, thời gian và dependency.

## 21. Distributed tracing và correlation ID

Khi request đi qua nhiều services, riêng log của `orders-api` có thể không đủ tìm nguyên nhân:

```text
Client
  |
  v
API Gateway / Ingress
  |
  v
orders-api  --HTTP--> payment-api
  |
  +--SQL--> database
  |
  +--Queue--> order-worker
```

Với OpenTelemetry hoặc cơ chế instrumentation tương đương, mỗi request có thể được gắn **trace ID** và các **spans** biểu diễn thời gian gọi từng thành phần.

Ví dụ:

```text
trace_id = 71f3... (minh họa, không phải token)
  orders-api POST /orders          580 ms
    ├── database INSERT             35 ms
    ├── payment-api POST /charge   490 ms
    └── queue publish               12 ms
```

Kết quả giúp nhận thấy payment-api là phần chiếm phần lớn thời gian, thay vì suy đoán ingress bị chậm.

### Điều kiện để tracing có giá trị

- Ứng dụng được instrument bằng SDK/agent hoặc integration phù hợp.
- Trace context được truyền qua HTTP/gRPC/queue theo chuẩn khi hỗ trợ.
- Cấu hình exporter tới Application Insights hoặc hệ thống tracing được phê duyệt.
- Sampling/retention đủ để bắt được yêu cầu lỗi.
- Log dùng trace ID để liên kết với span.
- Không đưa secrets/PII nhạy cảm vào span attributes.

**Dapr có thể hỗ trợ các khả năng observability trong những ứng dụng dùng Dapr**, nhưng bật Dapr không có nghĩa mọi code ứng dụng đều tự tạo đầy đủ traces của database và custom methods. Kiểm tra cụ thể instrumentation và pipeline xuất telemetry.

## 22. Thiết kế alert theo tác động, không chỉ theo tài nguyên

Một dashboard đẹp không thay được cảnh báo có người chịu trách nhiệm.

| Điều kiện cảnh báo | Mục tiêu | Cách phản ứng |
|---|---|---|
| HTTP 5xx rate tăng liên tục | Khách hàng gặp lỗi. | Kiểm tra revision rollout, logs, dependencies. |
| Replica restart/crash bất thường | Ứng dụng không ổn định. | Phân loại OOM, secret, probe, image, mount. |
| p95 latency vượt ngưỡng | Dịch vụ chậm. | So traces, CPU/memory, downstream latency. |
| Số replicas ở mức max kéo dài | Có thể thiếu capacity hoặc scale config chưa hợp lý. | Kiểm tra throughput, rule, quota và giới hạn dịch vụ. |
| Console log liên tục có lỗi auth | Secret/identity hoặc downstream permission thay đổi. | Kiểm tra Key Vault/DB/Storage role, rotation timeline. |
| Azure Files write errors tăng | Persistent storage không đáp ứng. | Kiểm tra mount, network, quota, IOPS, locks. |
| Không có log mới khi app lẽ ra đang hoạt động | Pipeline logging hoặc ứng dụng có vấn đề. | Xác minh requests, revision state và log destination. |
| Chi phí logs/storage tăng bất thường | Dư thừa telemetry hoặc thay đổi workload. | Điều chỉnh sampling, retention, logging level và budget. |

### Tránh alert noise

- Dùng ngưỡng theo **tỷ lệ** và thời gian quan sát, không chỉ số lỗi tuyệt đối.
- Phân biệt ứng dụng không có traffic vì **scale-to-zero hợp lệ** và ứng dụng không nhận traffic do outage.
- Có dashboard theo **revision** để phát hiện phiên bản triển khai mới gây lỗi.
- Định nghĩa owner, severity, escalation và runbook cho mỗi alert.
- Kiểm thử bằng sự kiện giả lập trong lab trước khi phụ thuộc vào alert cho Production.

## 23. Quy trình triển khai qua Azure Portal

### Giai đoạn A: Chuẩn bị

1. Chọn subscription, resource group và region phù hợp.
2. Có Container Apps environment và app với image được quản lý trong Azure Container Registry hoặc registry tương thích.
3. Chuẩn bị managed identity cho app, Key Vault secret và quyền đọc secret nếu dùng tích hợp.
4. Tạo Azure Storage account/file share nếu ứng dụng thật sự cần filesystem bền vững.
5. Lập bảng nguồn dữ liệu: biến thường, secret, file share, Blob Storage và logs.
6. Chọn yêu cầu network, DNS, retention, backup, metric và ngân sách.

### Giai đoạn B: Cấu hình secret

1. Mở **Container Apps → ứng dụng → Secrets** trong Portal.
2. Thêm app-level secret có giá trị được quản lý an toàn hoặc Key Vault reference được hỗ trợ.
3. Nếu dùng Key Vault, chọn managed identity, URI secret và kiểm tra quyền.
4. Mở cấu hình container của revision, thêm environment variable **tham chiếu secret**.
5. Triển khai revision theo quy trình, kiểm tra health và log xác thực.
6. Ghi cơ chế rotation và cách refresh secret cho các revision hiện có.

### Giai đoạn C: Cấu hình persistent volume

1. Tạo Azure Files share trong storage account, xác nhận giao thức và khả năng kết nối.
2. Tại **Container Apps environment**, khai báo **environment storage** trỏ tới share theo phương thức hỗ trợ.
3. Tại cấu hình Container App, tạo volume loại Azure Files và tham chiếu tên storage mapping.
4. Mount volume vào đường dẫn riêng của container, ví dụ `/mnt/reports`.
5. Triển khai revision mới và kiểm tra system logs khi mount.
6. Thử ghi/đọc một file **lab** và đọc lại từ replica khác/revision khác nếu mô hình ứng dụng yêu cầu.
7. Kiểm tra backup, quyền ghi đồng thời và xử lý khi storage không khả dụng.

### Giai đoạn D: Bật quan sát

1. Xác định destination của application/system logs tại environment.
2. Cấu hình Log Analytics workspace hoặc logging destination phù hợp.
3. Ứng dụng ghi stdout/stderr có cấu trúc; bổ sung request ID và trace ID.
4. Mở Azure Monitor metrics cho app, thiết lập dashboard theo revision.
5. Tích hợp tracing nếu workflow có nhiều services.
6. Đặt alerts cho lỗi 5xx, restart, latency, auth, mount và quota.
7. Chạy một incident drill trong lab để xác minh có thể tra ngược nguồn lỗi.

## 24. Chẩn đoán lỗi secret, Key Vault và revision

| Triệu chứng | Khả năng nguyên nhân | Bước khoanh vùng |
|---|---|---|
| Container không có biến `DB_PASSWORD` | Thiếu `secretRef` trong env template hoặc sai tên secret. | Xem cấu hình revision và app-level secret names. |
| Secret tồn tại nhưng không đọc được | Identity thiếu quyền hoặc Key Vault không cho phép truy cập. | Kiểm tra identity, role, vault firewall/DNS và log Key Vault. |
| App vẫn dùng credential cũ sau rotation | Revision chưa được làm mới hoặc tham chiếu Key Vault chưa cập nhật theo cơ chế hỗ trợ. | Xem version reference, revision restart/rollout, thời điểm refresh. |
| Replica khởi động thất bại sau xóa secret | Secret vẫn được env/scale rule tham chiếu. | Kiểm tra dependency và phục hồi secret có kiểm soát. |
| Secret đúng nhưng DB báo unauthorized | User/password đích không phù hợp hoặc DB quyền bị thu hồi. | Kiểm tra database auth, account lock và network; không in credential. |
| Một revision chạy, revision khác lỗi | Template/secretRef/runtime/identity khác nhau, hoặc refresh chưa đồng nhất. | So cấu hình và logs theo revision. |
| App bị rò rỉ secret trong logs | Code ghi env/config hoặc exception chứa credential. | Ngăn lộ, rotate secret, điều tra truy cập logs và sửa logging. |

### Runbook khi secret rotation làm ứng dụng lỗi

1. Xác định app, revision, thời điểm đổi Key Vault secret và tình trạng HTTP 5xx.
2. Kiểm tra Key Vault secret version/expiry/permissions và managed identity.
3. Xác nhận container env đang tham chiếu đúng tên app-level secret.
4. Kiểm tra network tới Key Vault và dịch vụ downstream.
5. Nếu cần, restart revision hoặc rollout mới theo cách được hỗ trợ, quan sát readiness.
6. Kiểm tra logs **không chứa secret values**, chỉ trạng thái kết nối.
7. Khôi phục dịch vụ bằng credential phiên bản trước **chỉ nếu còn hợp lệ và được phê duyệt**, không đưa giá trị vào log.
8. Ghi nguyên nhân, những revision bị ảnh hưởng và thay đổi quy trình rotation.

## 25. Chẩn đoán lỗi persistent volume

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Replica không start sau khi thêm volume | `storageName` sai, mapping thiếu, cấu hình volume không hợp lệ. | Đọc revision YAML và environment storage, xem system logs. |
| Mount thất bại | Share/account không tồn tại, credential sai, network/SMB bị chặn. | Xác minh Azure Files, key, firewall, DNS/route và port. |
| App báo `Permission denied` khi ghi | File permissions, access mode read-only, UID/GID hoặc application path. | Kiểm tra mode, ownership và thư mục đích trong container. |
| Ghi được nhưng replica khác không thấy ngay | Ứng dụng ghi local path thay vì mount, cache hoặc concurrency. | Kiểm tra đường mount, flush/locking và replication semantics. |
| File biến mất sau scale/revision | Chỉ ghi writable layer/EmptyDir, không ghi lên persistent share. | Kiểm tra storageType và mountPath thực tế. |
| Share ngày càng chậm khi scale-out | IOPS/throughput quota, lock contention, nhiều file nhỏ. | Đo Azure Files metrics và tối ưu workload/tier. |
| Storage outage khiến app 5xx | App phụ thuộc cứng vào share và không có fallback. | Thiết kế retry/backoff, queue, cache và circuit breaker phù hợp. |
| Rollback revision nhưng file vẫn ở bản mới | Persistent storage nằm ngoài revision. | Khôi phục từ backup/version phù hợp, không coi rollback app là rollback data. |

### Kiểm tra đường dẫn từ container

Khi app/replica đã chạy và quản trị viên được phép sử dụng console/exec, có thể kiểm tra **chỉ đọc**:

```bash
pwd
ls -ld /mnt/reports
df -h /mnt/reports
```

Không ghi file thử vào thư mục Production nhạy cảm để kiểm tra mount. Nếu cần test write, dùng share/thư mục lab có quyền được phê duyệt, tạo tên file duy nhất và dọn theo quy trình.

## 26. Chẩn đoán khi không có logs hoặc metrics

### Trường hợp 1: Không có console logs

Kiểm tra theo thứ tự:

1. App có active revision và replica thực sự đang chạy không?
2. Có traffic/event làm app hoạt động hay app scale về zero hợp lệ?
3. Code có ghi ra stdout/stderr hay chỉ ghi vào file local?
4. Đã chọn đúng container/revision/replica và khung thời gian UTC chưa?
5. Environment đã cấu hình logging destination chưa?
6. Workspace có đúng subscription, quyền và ingestion/retention không?
7. Truy vấn KQL có đúng tên bảng/schema không?

### Trường hợp 2: Có console logs nhưng thiếu system logs

Kiểm tra loại log, tình trạng triển khai gần đây, logging destination và quyền truy vấn. Không có system events trong một khoảng thời gian yên ổn **không tự chứng minh lỗi**.

### Trường hợp 3: Metrics tốt nhưng người dùng báo chậm

- Average latency có thể che p95/p99 latency.
- CPU thấp không chứng minh database/Storage không bị nghẽn.
- Một số metrics phụ thuộc vào nguồn dữ liệu/agent hoặc khả năng tính năng.
- Traces có thể cho biết yêu cầu chậm ở downstream nào.
- Đôi khi request bị chặn trước khi vào app, khiến metrics của ứng dụng không phản ánh đầy đủ sự cố ingress.

### Trường hợp 4: Replica restart nhiều lần

- Kiểm tra exit code, lỗi OOM, readiness/liveness probes.
- Xem app console logs ngay trước restart.
- Xem system logs cho image pull, revision activation, mount và scaling.
- Đối chiếu các thay đổi gần nhất: image, secret, volume, env var và resource limits.
- Không tăng memory limit mù quáng khi root cause là vòng lặp exception do credential sai.

## 27. Cân bằng chi phí, bảo mật và độ tin cậy

Các hạng mục có thể phát sinh chi phí:

| Nhóm | Chi phí/giới hạn cần dự toán |
|---|---|
| **Container Apps compute** | CPU, memory, số replica, thời gian active, mô hình tính phí của environment. |
| **Azure Files** | Dung lượng, tier, giao dịch đọc/ghi, hiệu năng và redundancy. |
| **Key Vault** | Các operation, key/secret management, network và logging theo dịch vụ. |
| **Azure Monitor/Log Analytics** | Log ingestion, retention, alerts, query và export. |
| **Application Insights/tracing** | Lượng telemetry, sampling, storage/retention và chi phí liên quan. |
| **Networking** | Private endpoints, VNet egress, NAT/firewall và dữ liệu truyền khi áp dụng. |
| **Backup/DR** | Snapshots, retention, vault hoặc giải pháp bảo vệ dữ liệu độc lập. |

### Lựa chọn có cơ sở

- Không xây Azure Files share chỉ để lưu **temporary cache** có thể mất sau khi replica kết thúc.
- Không giữ **debug log** chứa payload dài trong thời gian vô hạn.
- Không giảm log retention đến mức không còn đủ dữ liệu điều tra sự cố thường được phát hiện sau nhiều ngày.
- Không scale replicas quá cao khi tất cả đều tranh chấp một file share nhỏ.
- Không dùng app-level secret chứa storage account key cho mọi ứng dụng nếu có thể dùng identity-based APIs hoặc phân chia quyền hẹp hơn.
- Không coi việc sử dụng managed identity là lý do bỏ qua bảo vệ endpoint quản trị, logs và network.

### Mẫu ngân sách theo workload

Giả sử service xuất báo cáo một lần/giờ:

1. Đo thời gian xử lý, CPU/RAM cần thiết và số request đồng thời.
2. Ước lượng dung lượng file sau 30/90/365 ngày.
3. Đo số lần đọc/ghi và latency của Azure Files nếu chọn mount.
4. Tính thời gian active của replicas và chi phí logs theo mức verbosity.
5. Thử giữ `minReplicas=0` khi workload và loại trigger cho phép; kiểm tra cold start và deadline.
6. So sánh Blob object storage khi app không cần thao tác filesystem.

Mức giá cụ thể phụ thuộc region, SKU, lượng dữ liệu và phiên bản mô hình tính phí; sử dụng Azure Pricing Calculator và số liệu thực đo, không dựa vào con số giả định của bài học.

## 28. Bài thực hành: API có secret, share dùng chung và logging

**Bối cảnh:** Nhóm triển khai `orders-api` trên Container Apps. Ứng dụng gọi cơ sở dữ liệu bằng secret, xuất file CSV vào Azure Files để hai replicas cùng đọc và cần dashboard để điều tra lỗi.

Bảng yêu cầu:

| Thành phần | Giá trị minh họa |
|---|---|
| Container Apps environment | `cae-orders-lab` |
| Container app | `orders-api` |
| Image | `example.azurecr.io/orders-api:1.0.0` |
| App-level secret | `db-password` |
| Key Vault secret | `orders-db-password` |
| Container env | `DB_PASSWORD` → `secretRef: db-password` |
| Azure Files share | `reports` |
| Environment storage mapping | `reports-storage` |
| Revision volume | `reports-volume` |
| Mount path | `/mnt/reports` |
| Số replicas khi kiểm thử | 2 |
| Logging | Console/system logs vào Log Analytics theo cấu hình |
| Theo dõi | HTTP 5xx, p95 latency, replicas, mount errors |

### Nhiệm vụ

1. Vẽ ranh giới **environment/app/revision/replica**, đặt secret và volume đúng cấp.
2. Mô tả các bước cấp quyền managed identity để Container App đọc Key Vault secret.
3. Viết đoạn YAML app secretRef và volumeMounts theo schema được hỗ trợ.
4. Nêu khác biệt giữa `DB_PASSWORD` và `reports-storage`: chúng có cùng cơ chế xác thực không?
5. Chạy hoặc mô tả kiểm tra **liệt kê tên secret** mà không in value.
6. Mô tả cách xác minh file trong `/mnt/reports` vẫn tồn tại sau khi một replica bị thay thế.
7. Kiểm thử hai replicas ghi các file riêng, tránh ghi đồng thời cùng tên.
8. Tạo một log JSON gồm timestamp, revision, replica, request ID, event, duration và error code; không có secret.
9. Viết truy vấn Log Analytics tìm lỗi ở revision mới sau deployment.
10. Tạo hai cảnh báo: một cho HTTP 5xx tăng, một cho volume write errors.
11. Lập runbook khi credential DB được đổi nhưng một replica vẫn dùng credential cũ.
12. Nêu phương án khôi phục khi ai đó xóa file báo cáo và đánh giá backup/retention.

### Lời giải tham khảo

**Secret:** Key Vault chứa giá trị thật. Managed identity của app có quyền đọc secret. Cấu hình app-level secret tham chiếu Key Vault; revision template tạo env var `DB_PASSWORD` từ `db-password`. Khi rotation, kiểm tra cơ chế refresh/restart và theo dõi lỗi kết nối.

**Volume:** Azure Files share được khai báo ở cấp environment dưới tên `reports-storage`. Revision template gán volume `reports-volume` với `storageType: AzureFile` và mount vào `/mnt/reports`. Thông tin xác thực Azure Files mapping **không phải mặc nhiên** là `DB_PASSWORD` hoặc quyền Key Vault của app.

**Dữ liệu:** hai replicas ghi file `report-<job-id>.csv` với tên riêng; kiểm tra file từ replica khác hoặc sau rollout. Nếu xóa nhầm, dùng cơ chế snapshots/backup của Azure Files phù hợp; không trông chờ rollback revision.

**Quan sát:** ứng dụng ghi JSON trên stdout, platform có system logs và app/environment cung cấp metrics. Chọn khung thời gian triển khai và revision, so sánh logs với p95 latency và tỷ lệ 5xx; instrument tracing nếu cần phân tích gọi DB/queue nhiều bước.

**Nghiệm thu:** không secret nào xuất hiện trong logs/IaC output, có thể đọc/ghi share đúng quyền, dữ liệu tồn tại qua thay replica, alerts phát hiện được sự cố lab và có runbook restore.

## 29. Tự kiểm tra kiến thức

**Câu 1.** Trong Container Apps, `secretRef` dùng để làm gì?

A. Tạo Azure Files share.  
B. Tham chiếu một app-level secret để container sử dụng mà không ghi giá trị vào env template.  
C. Tạo revision mới mỗi lần đọc secret.

**Đáp án: B.** Secret được khai báo ở cấp app; template tham chiếu qua tên.

**Câu 2.** Chỉ thêm một secret mới có chắc tự tạo Container Apps revision mới không?

**Đáp án:** Không. Secret là cấu hình cấp app; template của revision là lớp cấu hình khác. Khi đổi secret, cần kiểm tra cơ chế refresh/restart để app dùng giá trị mới.

**Câu 3.** Managed identity của app có quyền đọc Key Vault secret có tự bảo đảm Azure Files volume mount hoạt động không?

**Đáp án:** Không. Azure Files environment storage mapping có điều kiện xác thực, kết nối mạng và quyền riêng.

**Câu 4.** Vì sao ghi file vào `/app/uploads` của container có thể làm mất dữ liệu sau rollout?

**Đáp án:** Writable layer thuộc vòng đời container/replica; instance mới không mặc nhiên mang file của instance cũ.

**Câu 5.** EmptyDir có được chia sẻ giữa mọi replica của cùng Container App không?

**Đáp án:** Không. EmptyDir là dữ liệu tạm thuộc replica; nhiều container bên trong replica có thể chia sẻ qua mount, nhưng replicas khác không dùng cùng EmptyDir.

**Câu 6.** Muốn container mount Azure Files, cần khai báo storage mapping ở đâu?

**Đáp án:** Ở **Container Apps environment**, sau đó revision template tham chiếu bằng `storageName` và container mount qua `volumeMounts`.

**Câu 7.** Khi hai replicas cùng mount Azure Files, có thể mặc định cả hai ghi cùng một file JSON mà không cần cơ chế đồng bộ không?

**Đáp án:** Không. Ứng dụng cần xử lý concurrency, file locks hoặc dùng thiết kế file theo job ID/database để tránh xung đột.

**Câu 8.** Persistent volume có phải là một bản backup tự động cho dữ liệu không?

**Đáp án:** Không. Nó tách vòng đời file khỏi replica; phải thiết kế snapshots/backup và quyền xóa phù hợp.

**Câu 9.** Console logs khác system logs thế nào?

**Đáp án:** Console logs chủ yếu từ stdout/stderr của container; system logs chủ yếu phản ánh sự kiện nền tảng Container Apps như revision, probe, startup hoặc scaling.

**Câu 10.** App scale về zero và không có log mới, có chắc logging bị lỗi không?

**Đáp án:** Không. Nếu không có replica chạy hoặc event/traffic, có thể không sinh console logs mới.

**Câu 11.** Có log và metric sẵn thì mọi HTTP request có distributed trace tự động không?

**Đáp án:** Không. Thường cần instrumentation và exporter/tracing backend phù hợp.

**Câu 12.** Vì sao KQL ví dụ truy vấn bảng `ContainerAppConsoleLogs_CL` có thể không chạy trong một workspace khác?

**Đáp án:** Tên bảng/cột và kiểu dữ liệu có thể khác theo logging destination/schema. Cần kiểm tra bảng thực có trong workspace.

**Câu 13.** Một revision cũ hoạt động, revision mới lỗi ngay khi startup. Nên kiểm tra các thay đổi nào?

**Đáp án:** Image, env `secretRef`, quyền/Key Vault reference, volume mapping, mountPath, resource limits, probes và system/console logs theo revision.

**Câu 14.** Rollback revision có tự động hoàn tác file đã ghi vào Azure Files không?

**Đáp án:** Không. Persistent share nằm ngoài revision; cần phương án backup/restore dữ liệu độc lập.

**Câu 15.** Khi muốn giảm chi phí log, có nên tắt toàn bộ error logs không?

**Đáp án:** Không. Nên giảm debug verbosity, lọc dữ liệu không cần thiết, quản lý sampling/retention nhưng vẫn giữ đủ dữ liệu để chẩn đoán sự cố.

**Câu 16.** Cách xác minh secret rotation an toàn là gì?

**Đáp án:** Kiểm tra managed identity/quyền/network, cập nhật tham chiếu theo cơ chế được hỗ trợ, restart/rollout khi cần, quan sát health/5xx và chỉ thu hồi credential cũ sau khi mọi consumer đã chuyển đổi.

**Tóm lại:** Azure Container Apps quản lý tốt workloads co giãn khi **secret được tách khỏi image, dữ liệu bền vững được tách khỏi replica và telemetry được tách khỏi filesystem cục bộ**. Hãy thiết kế đúng cấp **app → revision → replica**, chọn Key Vault/managed identity, Azure Files/Blob Storage và Azure Monitor/Log Analytics theo nhu cầu. Một ứng dụng vận hành tốt phải chứng minh được rằng đổi secret không làm gián đoạn vô cớ, scale/rollout không làm mất dữ liệu, và khi phát sinh sự cố có đủ log, metric, trace để tìm nguyên nhân và phục hồi.
