# Filesystem tạm thời và lưu trữ bền vững cho container

Container thường được tạo, dừng, thay thế và di chuyển trong suốt vòng đời của một ứng dụng. Vì vậy, dữ liệu ghi bên trong container không mặc nhiên tồn tại lâu dài. Một file được tạo trong filesystem của container có thể biến mất khi container bị xóa hoặc được thay bằng container mới, dù ứng dụng vẫn giữ nguyên tên và image.

Thiết kế storage cho container cần phân biệt dữ liệu tạm thời với dữ liệu phải tồn tại qua vòng đời workload. Cache, file trung gian và scratch data có thể đặt ở vùng lưu trữ tạm; database, file người dùng, checkpoint và dữ liệu nghiệp vụ cần được lưu ở volume hoặc dịch vụ lưu trữ có durability phù hợp.

Bài học thuộc module **CLOUD_CORE_SERVICES_COMPUTE**, chương **Nền tảng container**. Nội dung trình bày writable layer, filesystem tạm thời, tmpfs, bind mount, Docker volume, Kubernetes emptyDir, PersistentVolume/PersistentVolumeClaim, CSI, hiệu năng, bảo mật, backup và cách chọn storage theo vòng đời dữ liệu.

## 1. Vì sao filesystem của container cần được thiết kế riêng?

Container được thiết kế để có thể thay thế. Một deployment có thể tạo Pod mới khi node lỗi, cập nhật image hoặc scale số replica. Nếu dữ liệu quan trọng chỉ nằm trong filesystem riêng của container, việc thay thế container có thể làm mất dữ liệu.

Các tình huống phổ biến:

- Container restart sau khi process chính thoát hoặc bị lỗi.
- Pod bị xóa và được tạo lại trên node khác.
- Deployment rolling update thay Pod cũ bằng Pod mới.
- Node bị drain, bảo trì hoặc mất kết nối.
- Autoscaler scale-in node chứa Pod.
- Container image được cập nhật và tạo ra instance mới.

Không phải mọi thao tác đều làm mất dữ liệu ngay lập tức. Container restart bên trong cùng Pod có thể vẫn nhìn thấy một số volume của Pod; writable layer thuộc container cũ thường không được giữ khi container được tạo lại. Pod mới có thể được schedule trên node khác nên không thể dựa vào local filesystem của node cũ.

### 1.1. Phân loại dữ liệu trước khi chọn storage

| Loại dữ liệu | Ví dụ | Yêu cầu thường gặp |
|---|---|---|
| Runtime scratch | File tạm khi xử lý request | Có thể xóa sau khi xử lý |
| Cache | Cache ứng dụng, nội dung tải về có thể tái tạo | Có thể mất và tạo lại |
| Log | Log ứng dụng hoặc audit | Cần chuyển ra hệ thống log bền vững |
| Session | Trạng thái đăng nhập hoặc giỏ hàng | Nên dùng token hoặc store dùng chung |
| User upload | Ảnh, tài liệu người dùng | Cần durability, backup và quyền truy cập |
| Database | Bảng, transaction, index | Cần consistency, backup, restore và HA |
| Checkpoint | Tiến độ batch hoặc model training | Cần lưu bền vững để resume |
| Artifact | File build, package hoặc kết quả xử lý | Cần retention và versioning |

Hãy hỏi ba câu trước khi chọn nơi lưu:

1. Dữ liệu có thể tái tạo từ nguồn khác không?
2. Dữ liệu phải tồn tại qua container restart, Pod replacement hay cả node/zone failure?
3. Mức mất dữ liệu và thời gian phục hồi tối đa có thể chấp nhận là bao nhiêu?

## 2. Các lớp filesystem của container

Container image thường được xây từ nhiều filesystem layer bất biến. Khi container chạy, runtime tạo một writable layer ở phía trên các layer của image. Cơ chế cụ thể phụ thuộc container runtime và storage driver; trên Linux, OverlayFS là một cách triển khai phổ biến.

~~~mermaid
flowchart TB
    W["Container writable layer"] --> I["Image layer 3"]
    I --> J["Image layer 2"]
    J --> K["Image layer 1"]
    K --> B["Base image"]
    W --> V["Mounted volume / bind mount"]
    W --> T["Temporary filesystem / tmpfs"]
~~~

Các image layer được chia sẻ và thường chỉ đọc. Writable layer ghi những thay đổi của container, chẳng hạn file mới, file bị sửa hoặc xóa. Khi container bị xóa, writable layer của nó thường bị loại bỏ. Image layer vẫn còn trong local image cache cho tới khi được dọn dẹp.

### 2.1. Copy-on-write

Khi ứng dụng đọc file từ image layer, runtime có thể đọc trực tiếp từ layer chỉ đọc. Khi ứng dụng sửa file đó, cơ chế copy-on-write có thể sao chép file lên writable layer rồi áp dụng thay đổi tại đó.

Điều này giúp nhiều container dùng chung image layer mà không sửa image gốc. Tuy nhiên:

- Ghi nhiều dữ liệu vào writable layer có thể làm tăng dung lượng và I/O.
- Sửa file lớn có thể tạo chi phí copy-up.
- Dữ liệu trong writable layer gắn với vòng đời container.
- Không nên dùng writable layer làm nơi lưu database hoặc file nghiệp vụ lâu dài.

### 2.2. File trong image và file runtime

File được đóng gói trong image phù hợp với mã nguồn, thư viện, binary và cấu hình mặc định bất biến. Dữ liệu được tạo lúc chạy nên nằm ở volume hoặc storage phù hợp.

Không ghi file runtime vào thư mục chứa mã nguồn nếu thư mục đó được mount từ image và không có volume riêng. Việc này có thể:

- Không ghi được nếu filesystem được mount read-only.
- Tạo dữ liệu chỉ tồn tại trong writable layer.
- Bị che khuất khi mount volume lên cùng đường dẫn.
- Làm image khó tái sử dụng và khó kiểm soát trạng thái.

## 3. Phân biệt các kiểu lưu trữ

| Kiểu lưu trữ | Vòng đời điển hình | Dùng cho |
|---|---|---|
| Writable layer | Theo container | Thay đổi runtime không cần giữ |
| tmpfs / memory-backed volume | Theo container hoặc Pod tùy runtime | Scratch nhạy tốc độ, dữ liệu tạm |
| Docker named volume | Độc lập với container; tồn tại tới khi bị xóa | Database hoặc file local cần giữ trên host |
| Bind mount | Theo đường dẫn trên host | Phát triển, cấu hình hoặc tích hợp dữ liệu host |
| Kubernetes emptyDir | Theo vòng đời Pod | Scratch dùng chung giữa container trong Pod |
| Kubernetes ephemeral volume | Theo Pod hoặc cơ chế volume tương ứng | Storage tạm do CSI cấp |
| PersistentVolume | Theo chính sách vòng đời PV/storage | Dữ liệu cần tồn tại qua Pod |
| Object storage | Theo bucket/object retention | File, artifact, backup và dữ liệu phi cấu trúc |

Tên gọi “persistent” cần được hiểu theo phạm vi cụ thể. Docker volume có thể sống lâu hơn container nhưng vẫn phụ thuộc host; Kubernetes PV có thể độc lập với Pod nhưng có thể nằm trong một AZ hoặc bị xóa theo reclaim policy. Hãy xác định rõ failure domain mà dữ liệu cần sống sót.

## 4. Writable layer: lưu tạm theo vòng đời container

Writable layer phù hợp với file tạm chỉ cần trong thời gian container tồn tại. Ví dụ:

- File PID hoặc socket runtime.
- Cache nhỏ có thể tái tạo.
- File trung gian trong một request ngắn.
- Dữ liệu tạm của process không cần chia sẻ với container khác.

Không nên lưu:

- Database production.
- File upload duy nhất của người dùng.
- Log duy nhất cần audit.
- Checkpoint duy nhất của job dài.
- Secret hoặc key cần giữ lâu dài.

### 4.1. Điều gì xảy ra khi container restart?

Phải phân biệt restart process với tạo container mới:

- Nếu process bên trong cùng container restart, writable layer vẫn thuộc container đó và thường còn nguyên.
- Nếu runtime xóa container cũ và tạo container mới từ image, writable layer cũ không tự chuyển sang container mới.
- Nếu Pod được thay thế, container mới không dùng writable layer của Pod cũ.

Chính sách restart của Docker hoặc Kubernetes không biến writable layer thành storage bền vững. Hãy kiểm tra chính xác thao tác đang diễn ra: restart process, restart container, recreate container hay replace Pod.

## 5. tmpfs và lưu trữ trong bộ nhớ

tmpfs là filesystem lưu nội dung trong bộ nhớ, có thể dùng RAM và swap tùy cấu hình hệ điều hành. Nó phù hợp với dữ liệu tạm cần truy cập nhanh hoặc dữ liệu không muốn ghi xuống disk.

Ví dụ:

- File tạm chứa dữ liệu trung gian.
- Cache có thể tạo lại.
- File nhạy cảm cần tránh ghi vào disk thông thường.
- Socket hoặc scratch data của ứng dụng.

tmpfs không phải storage bền vững. Nội dung thường mất khi mount bị tháo, container/Pod kết thúc hoặc máy khởi động lại.

### 5.1. Giới hạn bộ nhớ

tmpfs sử dụng memory của host hoặc phạm vi cgroup. Nếu không đặt giới hạn, dữ liệu tạm có thể cạnh tranh RAM với ứng dụng. Trong container, cần xem memory limit và cấu hình tmpfs tương ứng.

Với Kubernetes, memory-backed emptyDir có thể tính vào memory usage của Pod. Nếu dữ liệu tạm tăng quá mức, container có thể bị OOMKilled hoặc Pod bị ảnh hưởng bởi memory pressure.

### 5.2. Docker tmpfs

~~~bash
docker run --rm \
  --mount type=tmpfs,destination=/run/cache,tmpfs-size=64m \
  my-worker:1.0
~~~

Ví dụ mount tmpfs tối đa 64 MiB tại /run/cache. Cú pháp và tùy chọn chi tiết phụ thuộc phiên bản Docker và nền tảng host. Không ghi dữ liệu cần khôi phục vào đường dẫn này.

## 6. Docker volume

Docker volume được Docker quản lý và có vòng đời độc lập với container sử dụng nó. Volume thường được lưu dưới vùng dữ liệu của Docker trên host hoặc do volume plugin quản lý.

Tạo và sử dụng named volume:

~~~bash
# Tạo volume
docker volume create app-data

# Chạy container và mount volume
docker run -d \
  --name app \
  --mount source=app-data,target=/var/lib/app \
  my-app:1.0

# Kiểm tra volume
docker volume inspect app-data

# Xóa container nhưng giữ volume
docker rm -f app
~~~

Sau khi container bị xóa, named volume vẫn tồn tại cho tới khi bị xóa bằng lệnh hoặc chính sách quản lý volume. Đây là lý do volume phù hợp hơn writable layer khi cần giữ dữ liệu qua container replacement trên cùng host.

### 6.1. Named volume và anonymous volume

- **Named volume:** có tên do người dùng đặt, dễ tham chiếu lại trong cấu hình và vận hành.
- **Anonymous volume:** được tạo tự động với định danh riêng khi container yêu cầu volume mà không đặt tên.

Anonymous volume có thể trở thành volume mồ côi nếu container bị xóa mà volume không được dọn dẹp. Cần có quy trình inventory và cleanup rõ ràng.

### 6.2. Xóa volume

Lệnh xóa container không nhất thiết xóa volume. Ngược lại, lệnh xóa volume sẽ loại bỏ dữ liệu trong volume đó. Một số lệnh như docker rm -v hoặc docker compose down -v có thể xóa volume được gắn trong phạm vi lệnh.

Trước khi xóa volume:

- Xác định container/service nào đang dùng volume.
- Xác minh backup và khả năng restore.
- Kiểm tra tên volume và project/stack liên quan.
- Không dùng prune hàng loạt trên host production nếu chưa đánh giá tác động.

### 6.3. Docker Compose

~~~yaml
services:
  database:
    image: postgres:16
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    volumes:
      - database-data:/var/lib/postgresql/data
    secrets:
      - db_password

volumes:
  database-data:

secrets:
  db_password:
    file: ./secrets/db_password.txt
~~~

Ví dụ minh họa named volume cho thư mục dữ liệu database và secret file cho mật khẩu. Trong production, cần quản lý secret bằng cơ chế phù hợp với môi trường, không lưu mật khẩu trong source control. Docker volume trên một host không tự cung cấp replication đa host hoặc backup.

## 7. Bind mount

Bind mount gắn một đường dẫn cụ thể trên host vào container. Nó hữu ích trong phát triển phần mềm, mount file cấu hình hoặc tích hợp với thư mục do một agent trên host quản lý.

~~~bash
docker run --rm \
  --mount type=bind,source=/srv/app/config,target=/etc/app,readonly \
  my-app:1.0
~~~

Ví dụ mount thư mục cấu hình từ host vào /etc/app ở chế độ read-only.

### 7.1. Ưu điểm và rủi ro

Ưu điểm:

- Dễ chia sẻ file giữa host và container.
- Có thể chỉnh file trên host mà không rebuild image.
- Dễ tích hợp với công cụ phát triển và debug.

Rủi ro:

- Container phụ thuộc cấu trúc filesystem của host.
- Quyền UID/GID và permission có thể không khớp.
- Container có thể sửa file host nếu mount read-write.
- Đường dẫn host không tồn tại hoặc khác nhau giữa các node.
- Di chuyển container sang host khác không tự mang dữ liệu theo.

### 7.2. Khi nào dùng bind mount?

Dùng bind mount khi cần truy cập có chủ đích vào một đường dẫn host. Với dữ liệu nghiệp vụ cần quản lý vòng đời độc lập, hãy cân nhắc volume hoặc dịch vụ storage được quản lý.

Không mount toàn bộ thư mục root của host vào container. Chỉ cấp đường dẫn nhỏ nhất cần thiết, ưu tiên read-only và kiểm soát quyền truy cập.

## 8. Docker volume, bind mount và tmpfs: chọn loại nào?

| Tiêu chí | Named volume | Bind mount | tmpfs |
|---|---|---|---|
| Vị trí quản lý | Docker/volume driver | Đường dẫn host | Memory filesystem |
| Dễ di chuyển container trên cùng host | Có thể gắn lại | Cần đường dẫn host tương ứng | Không giữ dữ liệu sau vòng đời |
| Chia sẻ với host | Có thể truy cập qua cơ chế quản lý, nhưng không nên sửa tùy tiện | Trực tiếp | Không như file disk thông thường |
| Dữ liệu sau khi container bị xóa | Thường còn nếu volume không bị xóa | Còn trên host | Mất khi mount/lifecycle kết thúc |
| Phù hợp | Dữ liệu ứng dụng cần giữ trên host | Config, source code, host integration | Scratch/cache nhạy tốc độ |
| Phạm vi HA | Không tự có HA đa host | Phụ thuộc host | Không bền vững |

Đối với database production, named volume chỉ giải quyết việc dữ liệu tồn tại qua container replacement trên cùng host. Nó không tự giải quyết host failure, disk failure, replication, backup hay failover.

## 9. Kubernetes volume và vòng đời Pod

Kubernetes cung cấp volume để chia sẻ dữ liệu giữa container trong cùng Pod hoặc gắn storage có vòng đời độc lập với Pod.

### 9.1. emptyDir

emptyDir được tạo khi Pod được gán vào node và tồn tại trong suốt vòng đời Pod. Nhiều container trong cùng Pod có thể mount cùng emptyDir để chia sẻ file.

Khi một container trong Pod restart, emptyDir vẫn tồn tại. Khi Pod bị xóa khỏi node, dữ liệu emptyDir bị xóa.

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: scratch-worker
spec:
  containers:
    - name: producer
      image: busybox:1.36
      command: ["sh", "-c", "echo ready > /scratch/state.txt; sleep 3600"]
      volumeMounts:
        - name: scratch
          mountPath: /scratch
    - name: consumer
      image: busybox:1.36
      command: ["sh", "-c", "sleep 5; cat /scratch/state.txt; sleep 3600"]
      volumeMounts:
        - name: scratch
          mountPath: /scratch
  volumes:
    - name: scratch
      emptyDir: {}
~~~

Ví dụ cho thấy hai container trong cùng Pod chia sẻ thư mục scratch. Không dùng emptyDir làm nơi lưu dữ liệu phải sống sót qua Pod replacement.

### 9.2. emptyDir trên memory

~~~yaml
volumes:
  - name: memory-scratch
    emptyDir:
      medium: Memory
      sizeLimit: 128Mi
~~~

Khi dùng medium Memory, Kubernetes mount tmpfs cho emptyDir. Nội dung sử dụng memory và có thể làm tăng memory pressure. sizeLimit giới hạn dung lượng volume theo cấu hình; vẫn cần tính tới memory limit và tổng memory usage của Pod.

### 9.3. ephemeral-storage

Kubernetes có tài nguyên local ephemeral storage. Request và limit của ephemeral-storage có thể áp dụng cho writable layer của container, log container và một số emptyDir dùng disk.

Ví dụ:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
    ephemeral-storage: "1Gi"
  limits:
    cpu: "1"
    memory: "1Gi"
    ephemeral-storage: "2Gi"
~~~

Request giúp scheduler tính toán tài nguyên local storage được yêu cầu; limit cho phép kubelet theo dõi mức sử dụng và có thể evict Pod khi vượt ngưỡng hoặc node thiếu dung lượng theo chính sách. Chi tiết accounting phụ thuộc filesystem layout và cấu hình node.

Không nhầm ephemeral-storage với PVC. Đây là tài nguyên lưu trữ tạm trên node, không phải ổ đĩa bền vững có thể gắn lại ở node khác.

## 10. PersistentVolume và PersistentVolumeClaim

PersistentVolume (PV) là tài nguyên storage trong cluster, đại diện cho một volume có vòng đời độc lập với Pod. PersistentVolumeClaim (PVC) là yêu cầu storage của workload. Kubernetes ghép PVC với PV phù hợp dựa trên dung lượng, access mode, StorageClass và các điều kiện khác.

Luồng cơ bản:

1. Người vận hành hoặc StorageClass cung cấp PV.
2. Workload tạo PVC yêu cầu dung lượng và chế độ truy cập.
3. Kubernetes bind PVC với PV phù hợp hoặc provision volume động.
4. Pod mount PVC vào container.
5. Pod có thể bị thay thế; PVC vẫn tồn tại theo chính sách.
6. Volume được detach/attach theo khả năng storage backend và topology.

~~~mermaid
flowchart TD
    A["Application Pod"] --> B["PersistentVolumeClaim"]
    B --> C["PersistentVolume"]
    C --> D["CSI Driver"]
    D --> E["Cloud Block / File Storage"]
    F["StorageClass"] --> D
    G["Snapshot / Backup"] --> E
~~~

PVC tách yêu cầu storage khỏi chi tiết triển khai của backend. Ứng dụng có thể yêu cầu dung lượng và access mode mà không cần biết chính xác tên thiết bị block ở cloud provider.

### 10.1. Ví dụ PVC và Pod

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 20Gi
  storageClassName: fast-block
---
apiVersion: v1
kind: Pod
metadata:
  name: app
spec:
  containers:
    - name: app
      image: my-app:1.0
      volumeMounts:
        - name: data
          mountPath: /var/lib/app
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: app-data
~~~

Ví dụ yêu cầu 20 GiB qua StorageClass tên fast-block. StorageClass này phải tồn tại và được cấu hình với CSI driver phù hợp trong cluster. ReadWriteOnce không có nghĩa chỉ một Pod được mount trong mọi tình huống; semantics của access mode cần hiểu theo node và driver.

### 10.2. Dynamic provisioning

Với dynamic provisioning, PVC có thể khiến CSI provision volume mới theo StorageClass. Nhóm vận hành không cần tạo từng PV thủ công.

StorageClass có thể quy định:

- CSI provisioner.
- Loại disk hoặc performance tier.
- Topology/zone.
- Filesystem hoặc volume parameters.
- Reclaim policy.
- Binding mode.
- Expansion policy nếu backend hỗ trợ.

Hãy kiểm tra StorageClass trước khi tạo PVC production. Một storage class có tên “fast” không tự chứng minh latency, IOPS hay durability; cần xem thông số thực tế của backend.

### 10.3. Access modes

Các access mode thường gặp:

- **ReadWriteOnce (RWO):** volume có thể được mount read-write bởi một node tại một thời điểm theo semantics của Kubernetes/driver; nhiều Pod trên cùng node có thể cùng sử dụng.
- **ReadOnlyMany (ROX):** volume có thể được mount read-only bởi nhiều node nếu backend hỗ trợ.
- **ReadWriteMany (RWX):** volume có thể được mount read-write bởi nhiều node nếu backend hỗ trợ.
- **ReadWriteOncePod (RWOP):** giới hạn mount read-write cho một Pod trong phạm vi được hỗ trợ.

Access mode là điều kiện mount/claim, không thay thế permission của filesystem hoặc cơ chế khóa ở tầng ứng dụng. RWX không bảo đảm ứng dụng có thể ghi đồng thời an toàn; ứng dụng vẫn cần file locking, transaction hoặc giao thức đồng bộ phù hợp.

## 11. StorageClass, CSI và topology

Container Storage Interface (CSI) là giao diện chuẩn để Kubernetes giao tiếp với storage provider. CSI driver có thể provision, attach, mount, resize, snapshot hoặc thực hiện các thao tác khác tùy khả năng được triển khai.

### 11.1. StorageClass

StorageClass mô tả một loại storage có thể cấp phát động. Ví dụ, một cluster có thể có:

- Class cho block storage hiệu năng cao.
- Class cho block storage tiết kiệm chi phí.
- Class cho shared file storage hỗ trợ RWX.
- Class cho local ephemeral storage hoặc loại volume đặc thù.

Không nên chọn StorageClass chỉ theo tên. Hãy xem provisioner, parameters, binding mode, reclaim policy, topology và khả năng backup/snapshot.

### 11.2. Volume topology

Một số block volume chỉ có thể attach vào instance trong cùng AZ nơi volume được tạo. Nếu Pod chuyển sang node ở AZ khác, scheduler cần biết topology để đặt Pod ở nơi có thể attach volume.

volumeBindingMode: WaitForFirstConsumer có thể trì hoãn việc bind/provision volume cho tới khi scheduler biết Pod sẽ chạy ở đâu. Điều này giúp lựa chọn topology phù hợp hơn trong nhiều kiến trúc block storage.

~~~yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-block
provisioner: csi.example.com
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
reclaimPolicy: Retain
parameters:
  tier: performance
~~~

Đây là ví dụ cấu trúc; csi.example.com và tier là giá trị minh họa, phải thay bằng provisioner và parameter thực tế của driver. Không áp dụng trực tiếp YAML này vào cluster nếu chưa có CSI driver tương ứng.

### 11.3. Reclaim policy

Reclaim policy quyết định hành vi PV khi PVC bị xóa:

- **Retain:** giữ PV và dữ liệu để quản trị viên xử lý thủ công hoặc tái sử dụng theo quy trình.
- **Delete:** yêu cầu backend xóa volume khi claim/PV được giải phóng theo semantics của provisioner.

Chính sách thực tế còn phụ thuộc CSI driver và dịch vụ storage. Với dữ liệu quan trọng, cần hiểu chính xác điều gì bị xóa khi PVC bị xóa và có backup trước thao tác hay không.

## 12. StatefulSet và volume claim template

StatefulSet phù hợp với workload cần danh tính ổn định và storage riêng cho từng replica, ví dụ database hoặc broker cluster.

volumeClaimTemplates tạo PVC riêng cho mỗi Pod. Pod có thể được tạo lại với cùng danh tính và gắn lại claim tương ứng, tùy khả năng của storage và topology.

~~~yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: ledger
spec:
  serviceName: ledger
  replicas: 3
  selector:
    matchLabels:
      app: ledger
  template:
    metadata:
      labels:
        app: ledger
    spec:
      containers:
        - name: database
          image: example/ledger-db:2.0
          volumeMounts:
            - name: data
              mountPath: /var/lib/ledger
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: fast-block
        resources:
          requests:
            storage: 50Gi
~~~

Mỗi replica nhận claim riêng. StatefulSet không tự replicate database data hoặc bảo đảm quorum; database engine hoặc operator phải quản lý replication, leader election và consistency.

### 12.1. Xóa StatefulSet và PVC

PVC do volumeClaimTemplates tạo ra thường có lifecycle riêng và không mặc nhiên bị xóa chỉ vì Pod restart. Hành vi retention khi xóa hoặc scale StatefulSet phụ thuộc cấu hình retention policy của StatefulSet và phiên bản Kubernetes.

Trước khi scale-in hoặc xóa StatefulSet, hãy kiểm tra:

- PVC nào còn tồn tại.
- PV đang bind với PVC nào.
- Reclaim policy là Retain hay Delete.
- Có snapshot/backup mới và đã kiểm thử restore chưa.
- Có cần giữ dữ liệu để tái tạo cluster không.

## 13. Object storage hay block/file storage?

Không phải mọi dữ liệu container đều cần mount filesystem. Chọn loại storage theo cách ứng dụng truy cập:

| Loại | Cách truy cập | Phù hợp |
|---|---|---|
| Block storage | Thiết bị block được filesystem/database sử dụng | Database, filesystem cần IOPS và latency ổn định |
| File storage | Giao thức file như NFS hoặc SMB | File chia sẻ giữa nhiều node/Pod, home directory |
| Object storage | API object, bucket/key | Upload, artifact, backup, media và dữ liệu phi cấu trúc |
| Local ephemeral disk | Disk cục bộ của node/instance | Scratch, cache có thể tạo lại, dữ liệu tạm hiệu năng cao |
| Memory storage | RAM/tmpfs | Temporary data nhỏ, cần tốc độ cao |

### 13.1. Block storage

Block volume thường được gắn vào một VM/node rồi format filesystem hoặc dùng trực tiếp bởi ứng dụng hỗ trợ block device. Cần xem IOPS, throughput, latency, queue depth, burst balance và giới hạn theo kích thước volume/instance.

Block volume không nhất thiết có thể attach read-write đồng thời vào nhiều node. Một số dịch vụ hỗ trợ multi-attach nhưng có yêu cầu và giới hạn riêng; filesystem hoặc database phải hỗ trợ đồng thời an toàn.

### 13.2. File storage

File storage hỗ trợ nhiều node truy cập cùng namespace. Nó hữu ích khi ứng dụng cần chia sẻ file qua nhiều Pod. Cần kiểm tra:

- NFS/SMB version và mount option.
- Throughput và IOPS theo workload.
- File locking và consistency semantics.
- Permission, UID/GID, ACL và root squash.
- Network path và mount target theo AZ.
- Behavior khi network storage bị gián đoạn.

### 13.3. Object storage

Object storage truy cập qua API, không phải filesystem POSIX đầy đủ. Nó phù hợp với file upload, media, backup và artifact. Ứng dụng cần dùng SDK/API, quản lý multipart upload, retry, checksum, versioning và lifecycle policy.

Không nên mount object storage như filesystem rồi mặc định mọi thao tác rename, lock hoặc atomic write sẽ có semantics giống local disk. Hãy thiết kế theo object API của dịch vụ.

## 14. Durability, availability và backup

Durability mô tả khả năng dữ liệu không bị mất theo thời gian; availability mô tả khả năng truy cập dữ liệu khi cần. Một storage có durability cao vẫn có thể tạm thời không truy cập được; một volume có thể mount được nhưng dữ liệu vẫn có nguy cơ bị xóa nhầm.

Để bảo vệ dữ liệu:

- Chọn replication và failure domain phù hợp.
- Bật backup hoặc snapshot theo RPO.
- Dùng retention và versioning khi cần.
- Bảo vệ backup khỏi quyền xóa ngoài ý muốn.
- Kiểm thử restore định kỳ.
- Theo dõi lỗi ghi, checksum và replication lag.
- Tách backup khỏi lifecycle của workload chính.

### 14.1. Snapshot không thay thế backup hoàn chỉnh

Snapshot có thể tạo điểm phục hồi của volume, nhưng cần kiểm tra tính nhất quán ứng dụng. Với database, snapshot crash-consistent có thể cần recovery log; application-consistent snapshot cần phối hợp flush hoặc quiesce.

Nếu nhiều volume cùng tạo nên một ứng dụng, snapshot từng volume ở thời điểm khác nhau có thể tạo trạng thái không đồng bộ. Hãy dùng quy trình snapshot group hoặc backup-native của database khi cần nhất quán xuyên volume.

### 14.2. Backup và replication giải quyết vấn đề khác nhau

Replication hỗ trợ tiếp tục hoạt động khi một bản sao hoặc node lỗi. Backup hỗ trợ phục hồi khi dữ liệu bị xóa nhầm, mã độc hoặc lỗi logic được replicate sang các bản sao.

Không coi replica là backup. Cần retention, bản sao độc lập và quyền truy cập tách biệt.

## 15. Hiệu năng storage cho container

Storage có thể trở thành bottleneck dù CPU và memory còn dư. Hãy đo theo workload:

- Read/write IOPS.
- Throughput (MiB/s hoặc GiB/s).
- Average và tail latency.
- Queue depth.
- fsync/flush latency.
- Cache hit/miss.
- File count và metadata operation.
- Network throughput tới file/object storage.

### 15.1. IOPS và throughput

IOPS đo số thao tác I/O mỗi giây; throughput đo lượng dữ liệu truyền mỗi giây. Workload đọc nhiều block nhỏ có thể bị giới hạn IOPS; xử lý file lớn có thể bị giới hạn throughput.

Không chỉ nhìn thông số tối đa của volume. Hiệu năng thực tế còn phụ thuộc instance/network limit, filesystem, queue depth, block size và mức tải đồng thời.

### 15.2. Latency

Database thường nhạy với tail latency. Một vài lần ghi chậm có thể làm transaction, connection pool và request queue kéo dài. Hãy xem p95/p99 storage latency cùng application latency.

### 15.3. Local SSD và ephemeral disk

Local NVMe hoặc instance store có thể cung cấp hiệu năng cao nhưng dữ liệu thường gắn với vòng đời instance hoặc phần cứng. Dùng cho cache, scratch, shuffle hoặc dữ liệu có thể tái tạo; không dùng làm bản sao duy nhất của dữ liệu quan trọng.

Nếu cần giữ dữ liệu, hãy replicate hoặc checkpoint ra storage bền vững trước khi instance bị dừng.

## 16. Dung lượng, quota và eviction

Filesystem tạm có giới hạn. Nếu writable layer, log hoặc emptyDir sử dụng quá nhiều dung lượng, node có thể hết disk và ảnh hưởng nhiều workload.

Trên Kubernetes, kubelet có thể theo dõi local ephemeral storage và evict Pod khi node gặp disk pressure hoặc Pod vượt giới hạn theo chính sách. Một container ghi log không giới hạn có thể làm node hết dung lượng dù ứng dụng nghiệp vụ không ghi nhiều file.

Biện pháp:

- Đặt request/limit cho ephemeral-storage phù hợp.
- Cấu hình log rotation và log shipping.
- Đặt sizeLimit cho emptyDir khi phù hợp.
- Theo dõi node filesystem và inode.
- Dọn file tạm sau khi job hoàn tất.
- Không lưu cache không giới hạn trên local disk.
- Có cảnh báo trước khi node đạt ngưỡng disk pressure.

### 16.1. Disk space và inode

Filesystem có thể hết inode dù còn nhiều byte trống nếu ứng dụng tạo hàng triệu file nhỏ. Theo dõi cả dung lượng và inode:

~~~bash
df -h
df -i
du -sh /var/lib/app/*
~~~

Các lệnh trên là ví dụ trên Linux; cần điều chỉnh đường dẫn và quyền truy cập theo image/container. Khi kiểm tra container, hãy xác định filesystem đó là writable layer, volume hay filesystem của node.

## 17. Bảo mật filesystem và volume

Storage mount mở rộng quyền truy cập của container tới dữ liệu bên ngoài. Cần cấp quyền tối thiểu:

- Dùng user không phải root khi có thể.
- Đặt ownership và permission rõ ràng.
- Mount volume read-only nếu ứng dụng chỉ cần đọc.
- Tránh mount đường dẫn nhạy cảm của host.
- Không lưu secret trong image hoặc writable layer.
- Mã hóa dữ liệu at rest và in transit theo yêu cầu.
- Quản lý key và quyền KMS/secret service.
- Tách volume giữa tenant hoặc workload có ranh giới bảo mật khác nhau.
- Audit thao tác đọc, ghi, snapshot và xóa dữ liệu quan trọng.

### 17.1. UID/GID và permission

Container có thể chạy với UID/GID khác host. Volume mount thành công nhưng ứng dụng không ghi được nếu ownership không phù hợp.

Trong Kubernetes, securityContext.fsGroup có thể giúp thiết lập quyền nhóm trên một số volume và CSI driver hỗ trợ. Cơ chế áp dụng và hiệu năng thay đổi theo loại volume; không nên giả định nó luôn sửa permission đệ quy trên mọi backend.

### 17.2. Read-only root filesystem

Đặt root filesystem read-only giúp giảm khả năng sửa file hệ thống khi container bị xâm nhập. Ứng dụng vẫn có thể cần vùng ghi riêng như /tmp, /var/cache hoặc thư mục runtime.

~~~yaml
securityContext:
  runAsNonRoot: true
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
~~~

Khi bật readOnlyRootFilesystem, hãy mount writable volume riêng cho các đường dẫn cần ghi. Nếu không, ứng dụng có thể lỗi khi khởi động hoặc khi tạo file tạm.

### 17.3. Secret và dữ liệu nhạy cảm

Không đóng gói secret vào image hoặc ghi secret lâu dài trong volume dùng chung. Dùng secret manager hoặc Kubernetes Secret được bảo vệ bằng encryption at rest, RBAC và chính sách rotation phù hợp.

Nếu secret được mount thành file, cần kiểm soát permission, thời điểm refresh và behavior của ứng dụng khi nội dung thay đổi.

## 18. Logging trong container

Container thường ghi log ra stdout/stderr để runtime thu thập. Đây là cách phù hợp với nền tảng orchestration vì log có thể được agent chuyển tới hệ thống tập trung.

Tránh ghi log duy nhất vào file trong writable layer. Khi container bị thay thế, file có thể biến mất. Nếu ứng dụng bắt buộc ghi file:

- Mount một volume phù hợp.
- Cấu hình log rotation.
- Có agent hoặc sidecar chuyển log ra hệ thống tập trung.
- Giới hạn dung lượng và retention.
- Theo dõi khi collector hoặc network bị lỗi.

Không dùng một file log duy nhất làm cơ chế audit bền vững nếu yêu cầu nghiệp vụ cần chống sửa/xóa hoặc lưu giữ dài hạn.

## 19. Di chuyển và nâng cấp workload có dữ liệu

Rolling update thay container image nhưng volume có thể được giữ lại nếu cấu hình mount không đổi. Tuy nhiên, dữ liệu trên volume vẫn có thể không tương thích với phiên bản ứng dụng mới.

Trước khi nâng cấp:

1. Xác định schema hoặc format dữ liệu có thay đổi không.
2. Tạo backup/snapshot theo quy trình ứng dụng.
3. Kiểm thử migration trên bản sao dữ liệu.
4. Xác nhận phiên bản cũ có thể đọc dữ liệu sau migration hay không.
5. Lập kế hoạch rollback.
6. Thực hiện migration theo thứ tự và theo dõi lỗi.

Với database, migration schema có thể không đảo ngược. Hãy dùng chiến lược expand-and-contract khi cần hỗ trợ phiên bản ứng dụng cũ và mới chạy song song.

### 19.1. Di chuyển Pod sang node khác

Nếu PVC dùng block volume có topology theo AZ, Pod mới có thể phải chạy ở node cùng AZ để attach volume. Nếu AZ đó mất, volume có thể không truy cập được dù Pod controller tạo Pod mới.

Khả năng phục hồi cần storage replication hoặc database replica ở AZ khác. Việc chỉ reschedule Pod không tự di chuyển block data.

### 19.2. Di chuyển giữa môi trường

Bind mount phụ thuộc đường dẫn host; local Docker volume phụ thuộc host; PV phụ thuộc CSI backend và topology. Khi chuyển cluster hoặc cloud provider, cần kế hoạch export/import, snapshot restore, replication hoặc data migration.

Không thể giả định một volume driver hoặc filesystem mount option có semantics giống nhau giữa mọi nền tảng.

## 20. Ví dụ chọn storage theo workload

| Workload | Dữ liệu | Lựa chọn phù hợp | Lưu ý |
|---|---|---|---|
| Web API stateless | Session, cache, upload | Session store dùng chung; cache có thể tái tạo; object storage cho upload | Không giữ session/file duy nhất trong writable layer |
| Batch worker | Input/output tạm, checkpoint | emptyDir hoặc local scratch cho trung gian; object/block storage cho checkpoint | Job cần resume sau interruption |
| PostgreSQL | Data directory, WAL | Persistent block volume hoặc managed database storage | Backup, replication, fsync và failover |
| Media processing | File tạm, kết quả | Local NVMe scratch và object storage cho kết quả | Upload output bền vững trước khi xóa scratch |
| Shared content service | File dùng chung | Managed file storage hỗ trợ nhiều node | Kiểm tra locking và throughput |
| CI runner | Source checkout, cache, artifact | emptyDir/local scratch cho workspace; artifact store cho kết quả | Cache có thể xóa, artifact cần retention |

## 21. Ví dụ thực tế: database container và file upload

Một ứng dụng thương mại điện tử chạy API trên Kubernetes. Ban đầu nhóm phát triển lưu ảnh upload và file database trong thư mục bên trong container. Khi rolling update, Pod mới được tạo và các file cũ biến mất.

Thiết kế lại:

1. API stateless chạy nhiều replica qua nhiều node.
2. File upload được ghi vào object storage bằng API; database chỉ lưu object key và metadata.
3. Database chạy dưới dạng dịch vụ managed hoặc StatefulSet có PVC, backup và replication phù hợp.
4. Cache và file tạm dùng emptyDir với giới hạn dung lượng.
5. Log ghi stdout/stderr và được chuyển tới hệ thống log tập trung.
6. PVC có StorageClass, topology và reclaim policy được xác định.
7. Backup được kiểm thử restore, tách khỏi lifecycle của Pod.

Sau đó, khi API Pod bị thay thế, file upload vẫn còn trong object storage và database data vẫn gắn với storage bền vững. Khi một node bị mất, Kubernetes có thể tạo Pod mới; database/storage cần cơ chế riêng để xử lý topology và failover.

## 22. Những sai lầm thường gặp

- **Lưu dữ liệu quan trọng trong writable layer:** container replacement có thể làm mất dữ liệu.
- **Nhầm container restart với container recreate:** hai thao tác có lifecycle filesystem khác nhau.
- **Dùng emptyDir cho dữ liệu phải tồn tại qua Pod replacement:** emptyDir bị xóa khi Pod kết thúc.
- **Coi Docker volume là storage đa host:** volume local vẫn phụ thuộc host hoặc driver.
- **Dùng bind mount read-write quá rộng:** container có thể sửa dữ liệu host ngoài phạm vi cần thiết.
- **Dùng tmpfs không giới hạn:** có thể gây memory pressure hoặc OOM.
- **Cho rằng PVC luôn có thể attach ở mọi AZ:** block volume có thể bị ràng buộc topology.
- **Coi StatefulSet tự replicate dữ liệu:** StatefulSet cấp danh tính và claim, database phải xử lý replication.
- **Không xem reclaim policy:** xóa PVC có thể kéo theo xóa volume backend.
- **Nhầm access mode với permission:** RWO/RWX không thay thế UID/GID, ACL hoặc file locking.
- **Chỉ theo dõi dung lượng, bỏ qua inode:** filesystem vẫn có thể hết khả năng tạo file.
- **Không kiểm thử restore:** snapshot tồn tại nhưng có thể không phục hồi được ứng dụng.
- **Ghi log duy nhất trong container:** log có thể mất khi container bị thay thế.
- **Không kiểm tra schema khi deploy:** ứng dụng mới có thể làm dữ liệu không tương thích với bản cũ.

## 23. Checklist thiết kế storage cho container

Trước khi triển khai, hãy xác nhận:

- [ ] Đã phân loại dữ liệu thành scratch, cache, log, session, upload, database và checkpoint.
- [ ] Dữ liệu quan trọng không nằm duy nhất trong writable layer.
- [ ] Vòng đời của container, Pod, node và volume đã được phân biệt.
- [ ] tmpfs/emptyDir có giới hạn memory hoặc disk phù hợp.
- [ ] Docker volume hoặc bind mount có owner và cleanup policy rõ ràng.
- [ ] PVC có dung lượng, access mode và StorageClass phù hợp.
- [ ] CSI driver và volume topology được xác minh.
- [ ] Reclaim policy không xóa dữ liệu ngoài dự kiến.
- [ ] StatefulSet có chiến lược replication/consistency riêng.
- [ ] Backup, snapshot và restore đã được thử nghiệm.
- [ ] Có metric cho IOPS, throughput, latency, capacity và inode.
- [ ] Permission, UID/GID, read-only mount và encryption được cấu hình.
- [ ] Log và secret không phụ thuộc writable layer.
- [ ] Quy trình upgrade/migration có backup và rollback.

## 24. Quy trình vận hành và bảo trì

1. **Inventory:** lập danh sách volume, PVC, PV, StorageClass và owner.
2. **Phân loại:** xác định dữ liệu nào có thể tái tạo và dữ liệu nào phải giữ.
3. **Capacity planning:** dự báo dung lượng, IOPS, throughput, inode và growth.
4. **Lifecycle policy:** quy định retention, snapshot, reclaim và cleanup.
5. **Security review:** kiểm tra quyền, encryption, secret và mount scope.
6. **Observability:** theo dõi latency, lỗi mount, attach/detach, disk pressure và backup.
7. **Recovery test:** restore dữ liệu và khởi chạy ứng dụng từ bản phục hồi.
8. **Change management:** kiểm thử schema, migration và compatibility trước deploy.
9. **Retirement:** xác nhận owner và backup trước khi xóa PVC, PV hoặc volume.

## 25. Ghi nhớ

Filesystem trong container có nhiều lớp với vòng đời khác nhau. Writable layer và tmpfs phù hợp với dữ liệu tạm; Docker volume, bind mount và Kubernetes PV/PVC cung cấp các cách lưu dữ liệu ngoài container nhưng có phạm vi durability và phụ thuộc hạ tầng khác nhau. emptyDir sống cùng Pod, còn PVC có thể sống lâu hơn Pod theo reclaim policy và storage backend.

Hãy chọn storage theo vòng đời dữ liệu, failure domain, access pattern, hiệu năng và yêu cầu bảo mật. Dữ liệu quan trọng cần backup, restore test và replication phù hợp; local disk hoặc volume trên một host không tự tạo HA đa node. Theo dõi cả dung lượng, inode, IOPS, throughput và latency. Thiết kế rõ ownership, topology, permission và chính sách xóa để container có thể được thay thế mà không làm mất dữ liệu nghiệp vụ.
