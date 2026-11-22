# Volume bền vững, quyền thư mục và vòng đời container khi triển khai PostgreSQL

Đóng gói PostgreSQL trong container giúp chuẩn hóa môi trường chạy, nhưng container không phải nơi lưu trữ dữ liệu lâu dài. Container có thể bị xóa và tạo lại khi deploy, reschedule, nâng image hoặc khôi phục sau sự cố. Nếu database chỉ ghi vào writable layer của container, dữ liệu có thể biến mất cùng container.

Để triển khai an toàn, cần tách vòng đời của PostgreSQL server khỏi vòng đời container. Data directory, WAL, tablespaces và những file cần thiết để phục hồi phải nằm trên storage có vòng đời được quản lý rõ ràng. Container mới phải có thể gắn lại đúng volume, chạy bằng user có UID/GID và quyền phù hợp, đọc được cấu hình, khởi động database hiện có và tiếp tục phục vụ workload.

Bài học này giải thích cách chọn persistent volume, bind mount và PVC; cách bố trí `PGDATA`, WAL và tablespaces; cách xử lý ownership, mode bits, SELinux và Kubernetes security context; cách vận hành stop/restart/recreate, backup/restore, failover và nâng cấp PostgreSQL trong container. Các ví dụ dùng Docker/Compose và Kubernetes, nhưng nguyên tắc áp dụng cho các container runtimes và orchestration platforms khác.

Bài học thuộc chương **Triển khai** của module *Database Engine Relational PostgreSQL*.

> **Nguyên tắc:** Container có thể thay thế; database cluster phải có storage và recovery plan riêng. Không để một thao tác xóa/recreate container vô tình xóa data volume, và không gắn cùng một PostgreSQL data directory cho nhiều server đang chạy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt container writable layer, bind mount, named volume và Kubernetes PersistentVolume.
2. Chọn loại storage phù hợp cho PostgreSQL data directory.
3. Bố trí `PGDATA`, `pg_wal`, tablespaces, configuration và backup locations.
4. Hiểu mount semantics và cách mount che nội dung có sẵn trong image.
5. Cấu hình UID/GID, ownership, directory modes và file permissions.
6. Xử lý rootless containers, user namespace mapping và Kubernetes security context.
7. Nhận diện vấn đề SELinux labels và filesystem permissions.
8. Đánh giá filesystem, block storage, latency, IOPS và durability.
9. Quản lý PVC, StorageClass, StatefulSet và volume retention.
10. Hiểu container stop signal, graceful shutdown, restart và crash recovery.
11. Thiết kế readiness, liveness và startup probes phù hợp với PostgreSQL.
12. Thực hiện backup/restore và snapshot với consistency phù hợp.
13. Bảo đảm WAL, archive và tablespaces được lưu bền vững.
14. Triển khai rolling update và major-version upgrade an toàn.
15. Tránh mount data directory đồng thời cho nhiều PostgreSQL instances.
16. Theo dõi dung lượng, I/O, permissions và volume health.
17. Xây dựng runbooks cho permission errors, missing volume và failed startup.
18. Lập checklist vận hành và recovery cho PostgreSQL containers.

## 2. Container filesystem và persistent storage

Container có một filesystem view được tạo từ image layers và writable layer của container. Khi container bị xóa, writable layer thường bị xóa theo. Storage được mount từ bên ngoài có vòng đời độc lập với container.

### 2.1. Writable layer không phải database storage

Nếu PostgreSQL ghi vào đường dẫn không có volume mount, dữ liệu nằm trong writable layer. Khi container được recreate từ image mới, container cũ và layer của nó có thể bị loại bỏ. Image mới không chứa các transaction đã commit trong container cũ.

Không dùng writable layer làm nơi lưu `PGDATA` cho database cần tồn tại qua deploy/restart.

### 2.2. Persistent volume tách data khỏi container

Persistent volume cho phép:
- Xóa và tạo lại container mà giữ database files.
- Nâng image trong khi giữ storage.
- Gắn volume vào node/container mới theo quy trình platform.
- Tách quyền quản lý data lifecycle khỏi image lifecycle.
- Thực hiện backup/snapshot theo storage platform.

Volume bền vững không tự động là backup. Nếu volume bị xóa, corruption hoặc dữ liệu bị xóa nhầm, bản sao độc lập vẫn cần thiết.

### 2.3. Các loại mount phổ biến

| Loại | Vị trí quản lý | Đặc điểm | Trường hợp phù hợp |
|---|---|---|---|
| Container writable layer | Runtime | Đi theo container | Cache/tạm thời, không dùng cho PGDATA |
| Named volume | Docker/Podman | Runtime quản lý vòng đời | Database đơn host hoặc môi trường Compose |
| Bind mount | Host path | Gắn thư mục/file cụ thể từ host | Tích hợp storage/backup/config do host quản lý |
| tmpfs | Memory của host | Mất khi container dừng/recreate | Temporary data không cần bền vững |
| Kubernetes PVC | Kubernetes/storage provider | Yêu cầu storage có lifecycle riêng | Stateful workloads |
| Cloud block disk | Cloud provider | Block device attach vào node | Database cần persistent block storage |
| Network filesystem | NAS/storage service | Chia sẻ qua network | Chỉ dùng khi PostgreSQL/provider hỗ trợ semantics và hiệu năng cần thiết |

### 2.4. Named volume và bind mount khác nhau

Named volume do container runtime quản lý, giúp Compose hoặc runtime tham chiếu bằng tên ổn định. Bind mount tham chiếu một path cụ thể trên host, nên quyền, SELinux label, backup và path provisioning do host/platform quản lý nhiều hơn.

### 2.5. Mount có thể che nội dung trong image

Khi mount một bind mount lên một thư mục không rỗng trong image, nội dung gốc tại mountpoint bị che khuất trong container. Named volumes có thể có behavior khởi tạo/copy dữ liệu khác tùy runtime và options. Không dựa vào nội dung sẵn có trong image để lưu database; hãy kiểm tra mountpoint và volume thực tế.

### 2.6. tmpfs không phải persistent storage

tmpfs phù hợp cho dữ liệu tạm thời có chủ đích. Không mount `PGDATA`, `pg_wal` hoặc tablespace duy trì lâu dài vào tmpfs. Mất RAM hoặc container lifecycle có thể làm mất dữ liệu chưa được lưu vào storage bền vững.

## 3. Chọn persistent storage cho PostgreSQL

PostgreSQL thực hiện nhiều thao tác đọc/ghi đồng bộ, đặc biệt liên quan WAL và commit. Storage phải đáp ứng durability và latency, không chỉ có dung lượng đủ lớn.

### 3.1. Block storage thường là lựa chọn phổ biến

Cloud block volumes và local block devices thường phù hợp với database vì PostgreSQL làm việc với filesystem trên block device và cần semantics về flush/sync. Cần chọn loại volume có IOPS, throughput và latency đáp ứng workload.

### 3.2. Đánh giá filesystem

Kiểm tra:
- Filesystem được OS và storage provider hỗ trợ.
- POSIX semantics.
- `fsync`/flush behavior.
- File locking và shared memory requirements.
- Crash consistency.
- Mount options.
- Filesystem expansion.
- Quota và capacity reporting.

PostgreSQL dựa vào filesystem và OS để bảo đảm durability. Một filesystem/network storage có behavior không phù hợp với locking hoặc flush semantics có thể gây lỗi nghiêm trọng. Chỉ dùng loại storage được PostgreSQL/platform vendor hỗ trợ và đã kiểm thử trong môi trường mục tiêu.

### 3.3. Network filesystem

Không mặc định rằng NFS/SMB hoặc bất kỳ shared filesystem nào đều phù hợp. Xác nhận support matrix, locking semantics, cache coherency, flush behavior và failure modes. Nếu provider khuyến nghị block volume hoặc có giới hạn cụ thể, tuân theo hướng dẫn đó.

### 3.4. Local ephemeral disk

Local NVMe có thể rất nhanh nhưng có thể mất khi instance/node bị thay thế. Chỉ dùng khi kiến trúc có replication, backup và recovery strategy rõ ràng, và hiểu chính xác data-loss exposure. Không gọi local ephemeral disk là persistent chỉ vì path vẫn tồn tại sau container restart trên cùng host.

### 3.5. Latency quan trọng cùng IOPS và throughput

WAL flush và synchronous commit nhạy với latency. Một volume có throughput lớn nhưng latency cao có thể làm transaction commit chậm. Benchmark với `fsync`/durability configuration gần production.

### 3.6. Capacity và headroom

Ước lượng:
- Data files.
- Indexes.
- WAL growth.
- Temporary files.
- Sort/hash spill.
- Backup staging nếu nằm cùng volume.
- Tablespaces.
- Bloat và maintenance headroom.
- Growth theo thời gian.

Không cấp volume vừa khít với dung lượng hiện tại. Dự phòng tăng trưởng và các đợt index build/restore.

## 4. Xác định data directory và PGDATA

`PGDATA` là biến môi trường thường được image PostgreSQL dùng để chỉ đường dẫn data directory. Nó phải trỏ tới directory chứa cluster đã được `initdb` khởi tạo hoặc directory mà entrypoint sẽ khởi tạo lần đầu.

### 4.1. Tách PGDATA khỏi image

Một ví dụ Docker Compose đơn giản:

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped
    stop_grace_period: 1m

volumes:
  pgdata:
```

Đây là cấu hình minh họa. Kiểm tra tài liệu của image tag thực tế vì entrypoint, default `PGDATA`, secret support và directory layout có thể thay đổi giữa image variants/major versions.

### 4.2. Mount root và PGDATA subdirectory

Trong ví dụ trên, volume được mount tại `/var/lib/postgresql/data`, còn cluster ở thư mục con `/var/lib/postgresql/data/pgdata`. Cách bố trí này có thể giúp entrypoint xử lý mount root và data subdirectory riêng, nhưng phải khớp với image.

Một số image sử dụng layout khác theo major version hoặc biến môi trường. Không copy đường dẫn từ một ví dụ cũ mà chưa kiểm tra image.

### 4.3. Xác nhận cluster directory

Trong container, có thể kiểm tra:

```bash
printf 'PGDATA=%s\n' "$PGDATA"
ls -ld "$PGDATA"
ls -l "$PGDATA/PG_VERSION"
```

`PG_VERSION` là file metadata của cluster. Đọc nội dung file để xác định major version của data directory; không suy ra version chỉ từ image tag.

### 4.4. Một volume cho một cluster data directory

Một PostgreSQL cluster chỉ có một primary writer tại một thời điểm theo kiến trúc thông thường. Không mount cùng `PGDATA` read-write vào hai PostgreSQL servers đang chạy. Filesystem locks không biến một data directory thành multi-writer database.

### 4.5. Mỗi replica có data directory riêng

Với physical streaming replication, primary và mỗi standby có data directory riêng. WAL/replication truyền changes giữa các nodes; không chia sẻ cùng một `PGDATA` để thay thế replication.

## 5. Mount semantics trong Docker và Compose

Docker volume là đối tượng riêng của runtime. Container chỉ nhìn thấy volume tại mount destination.

### 5.1. Khai báo named volume

```yaml
services:
  db:
    image: postgres:17
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

Compose tạo hoặc sử dụng named volume theo project/name resolution. Tên thực tế có thể được prefix bởi project name trừ khi cấu hình external/name cụ thể.

### 5.2. Bind mount

```yaml
services:
  db:
    image: postgres:17
    volumes:
      - type: bind
        source: ./postgres-data
        target: /var/lib/postgresql/data
```

Host directory phải tồn tại hoặc được tạo theo semantics của Compose/runtime. Kiểm tra owner, permissions và SELinux label trên host trước khi start.

### 5.3. Read-only mount

Read-only mount phù hợp cho config/certificate mà server chỉ cần đọc. Không mount `PGDATA` read-only nếu PostgreSQL cần ghi WAL, status files, relation files và control files.

### 5.4. Không mount nhầm một file vào directory

Nếu mount destination và source type không khớp, entrypoint có thể không tìm thấy file hoặc server không thể khởi động. Kiểm tra file-vs-directory và path spelling, nhất là trên Windows/WSL.

### 5.5. Container recreate và volume retention

`docker compose down` thường giữ named volumes; `docker compose down -v` yêu cầu xóa volumes được quản lý trong project (ngoại trừ external volumes theo behavior của Compose). `docker volume prune` có thể xóa volumes không còn được runtime xem là đang dùng.

Trước lệnh xóa, xác nhận volume name, mount source, backup và mục tiêu. Không dùng `-v` hoặc prune như thao tác cleanup mặc định cho production.

### 5.6. External volumes

Có thể khai báo volume do platform quản lý bên ngoài Compose. Khi đó Compose không tạo lifecycle mới theo project. Ghi lại người sở hữu volume và quy trình attach/restore.

### 5.7. Kiểm tra mount thực tế

Dùng runtime inspect để xác nhận source, destination, read/write mode và volume identity. Không chỉ dựa vào YAML vì interpolation, project name hoặc override files có thể làm cấu hình cuối khác dự kiến.

## 6. Quyền thư mục: PostgreSQL cần đúng owner

PostgreSQL chạy dưới một OS user riêng, thường là user `postgres` trong image. Data directory phải thuộc user chạy server và có permission phù hợp.

### 6.1. Ownership

Trên Linux, kiểm tra:

```bash
id postgres
stat -c '%u:%g %a %n' "$PGDATA"
namei -l "$PGDATA"
```

`id` cho biết UID/GID trong container. `stat` kiểm tra owner/mode; `namei -l` giúp xem permissions của từng path component nếu công cụ có sẵn.

### 6.2. Directory permissions

`initdb` mặc định tạo data directory với quyền riêng tư trên Unix; thông thường mode `0700`. Option `--allow-group-access` cho phép group access với mode rộng hơn (thường `0750`). PostgreSQL kiểm tra permissions của data directory khi khởi động.

Không chmod toàn bộ data directory thành `0777` để khắc phục lỗi. Cách đó mở dữ liệu database cho users/processes không cần thiết và có thể khiến PostgreSQL từ chối start.

### 6.3. Parent directory traversal

Các thư mục cha cần execute/search permission để user `postgres` đi tới `PGDATA`. Parent directory không nhất thiết phải writable bởi user PostgreSQL nếu mount/layout không yêu cầu tạo thư mục con ở đó.

Ví dụ một path có `PGDATA=/srv/postgres/data` cần quyền traverse trên `/srv` và `/srv/postgres`, ngoài quyền trên `/srv/postgres/data`.

### 6.4. File permissions

WAL, relation files, control files và configuration có yêu cầu truy cập tương ứng. Không chạy `chmod -R` tùy tiện khi server đang hoạt động. Nếu ownership/modes sai, dừng server theo quy trình, xác định nguyên nhân và sửa đúng phạm vi.

### 6.5. Initdb và directory không rỗng

`initdb` khởi tạo một cluster mới trong directory trống phù hợp. Nếu mount một volume đã chứa data, entrypoint phải nhận diện cluster hiện hữu và không chạy initdb lại. Nếu directory có file lạ nhưng không phải cluster hợp lệ, startup có thể fail.

Không xóa nội dung volume để “thử lại” trước khi xác nhận đó không phải database cần giữ.

## 7. UID/GID mapping và rootless containers

Tên user trong image không bảo đảm UID/GID giống user trên host.

### 7.1. Bind mount dùng ownership của host

Ví dụ host directory thuộc UID 1001 nhưng process PostgreSQL trong container chạy UID 999. Từ bên trong container, server có thể không ghi được directory dù cả hai nơi đều hiển thị tên user quen thuộc.

Tên user là mapping từ UID/GID; kernel permission check dựa trên numeric IDs.

### 7.2. Xác nhận UID/GID của image cụ thể

Kiểm tra:

```bash
docker run --rm --entrypoint sh postgres:17 -c 'id postgres'
```

Image tag ở ví dụ chỉ minh họa. Pin đúng tag/digest production và kiểm tra lại sau khi đổi image.

### 7.3. Chuẩn bị bind mount

Host admin có thể tạo directory và gán owner/group theo UID/GID mà container cần. Ví dụ Linux:

```bash
sudo install -d -o 999 -g 999 -m 0700 /srv/postgres/data
```

UID/GID `999` chỉ là ví dụ, không phải giá trị cố định cho mọi image. Lấy giá trị thật từ image và security policy.

### 7.4. Rootless Docker/Podman

Rootless runtime dùng user namespace mapping. UID trong container có thể map sang subordinate UID trên host. Chown từ host bằng UID nhìn thấy trong container có thể không đúng. Kiểm tra uidmap, subuid/subgid hoặc runtime inspect theo platform.

### 7.5. User namespace remapping

Docker userns-remap có thể thay đổi owner IDs được nhìn thấy trên host. Cần hiểu mapping trước khi tạo/chown bind mount. Không sửa owner theo phỏng đoán vì có thể làm container khác mất quyền truy cập.

### 7.6. Không chạy PostgreSQL bằng root để né permissions

PostgreSQL server không được chạy với superuser OS root. Dùng user không privileged, đúng UID/GID, ownership và mount policy. Nếu entrypoint khởi động dưới root để chuẩn bị thư mục rồi hạ quyền, đó là behavior của entrypoint cụ thể; không thay bằng lệnh chạy server trực tiếp dưới root.

## 8. Kubernetes security context và PVC permissions

Trong Kubernetes, pod có thể chạy với `runAsUser`, `runAsGroup`, `fsGroup` và các controls khác.

Ví dụ minh họa:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: postgres
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 999
    runAsGroup: 999
    fsGroup: 999
    fsGroupChangePolicy: OnRootMismatch
  containers:
    - name: postgres
      image: postgres:17
      env:
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
      volumeMounts:
        - name: pgdata
          mountPath: /var/lib/postgresql/data
  volumes:
    - name: pgdata
      persistentVolumeClaim:
        claimName: postgres-data
```

Đây là skeleton để giải thích security context, không phải manifest production hoàn chỉnh. UID, mount path, image, probes, resources, secrets và StorageClass cần khớp platform.

### 8.1. runAsUser và runAsGroup

`runAsUser` và `runAsGroup` xác định numeric identity của process trong container. Chọn UID/GID được image hỗ trợ và thống nhất với ownership của mounted storage.

### 8.2. fsGroup

`fsGroup` có thể khiến volume được gắn với supplementary group của pod hoặc thay đổi ownership/mode tùy volume driver và Kubernetes implementation. Không phải CSI driver nào cũng hỗ trợ cùng cách.

`fsGroup` không tự động bảo đảm data directory thỏa kiểm tra permission của PostgreSQL. Kiểm tra `stat`, effective groups và mode bits từ bên trong pod.

### 8.3. fsGroupChangePolicy

Trên các Kubernetes versions hỗ trợ, `fsGroupChangePolicy: OnRootMismatch` có thể tránh thay đổi ownership đệ quy mỗi lần mount khi root directory đã khớp. Với volume lớn, recursive ownership change có thể làm pod startup kéo dài đáng kể. Xác nhận CSI driver có xử lý ownership hay không.

### 8.4. Init container để chuẩn bị ownership

Một số deployment dùng init container có quyền phù hợp để chuẩn bị thư mục. Cách này cần review:
- Có được phép chạy root không?
- Có chown toàn volume mỗi lần start không?
- Volume có hàng triệu files không?
- Security policy/Pod Security Admission có cho phép không?
- UID/GID có khớp container chính không?

Không cấp quyền root rộng chỉ để né việc thiết kế ownership đúng.

### 8.5. readOnlyRootFilesystem

Có thể bật read-only root filesystem cho container và mount các writable paths cần thiết bằng volume riêng. PostgreSQL vẫn cần writable `PGDATA`, socket/temp paths và các directories do image/runtime yêu cầu. Test startup, logs và recovery khi bật policy này.

### 8.6. Capabilities và privilege

Chạy non-root và loại bỏ capabilities không cần thiết theo image/platform guidance. Không dùng privileged pod hoặc hostPath rộng nếu không có yêu cầu rõ và approval.

## 9. SELinux, AppArmor và filesystem labels

Trên hệ thống bật SELinux, Unix mode bits đúng vẫn chưa đủ. Security label có thể ngăn container truy cập bind mount.

### 9.1. SELinux labels

Docker/Podman có thể hỗ trợ relabel bind mounts bằng options như `:Z` (label riêng cho container) hoặc `:z` (label chia sẻ giữa containers), tùy runtime. Ví dụ:

```bash
docker run -v /srv/postgres/data:/var/lib/postgresql/data:Z ...
```

Không áp dụng label option một cách máy móc cho storage đang được nhiều services dùng. Relabel có thể thay đổi label trên host path và ảnh hưởng process khác.

### 9.2. Diagnose SELinux

Kiểm tra audit logs/AVC denials, file labels và container process context. Đừng tắt SELinux toàn host để khắc phục một mount lỗi.

### 9.3. AppArmor và seccomp

AppArmor/seccomp có thể hạn chế filesystem syscalls hoặc process actions. Dùng profile tương thích và kiểm tra audit/logs nếu server bị deny. Tránh `unconfined` như giải pháp mặc định.

### 9.4. Kubernetes SELinux options

Kubernetes có thể gán SELinux context cho container/volume theo policy và CSI driver. Kiểm tra node OS, runtime, admission policy và volume plugin. Cấu hình trên một node không bảo đảm labels giống nhau trên mọi node.

## 10. Tách data, WAL, tablespaces và cấu hình

Một PostgreSQL cluster có nhiều loại file với mục đích và lifecycle khác nhau.

### 10.1. PGDATA

`PGDATA` chứa control files, catalogs, relation files, subdirectories và mặc định cả `pg_wal` trừ khi WAL được đặt riêng bằng cơ chế được hỗ trợ.

### 10.2. WAL

WAL là thành phần cần thiết cho crash recovery và durability. Nếu `pg_wal` nằm trên mount riêng hoặc symlink, volume đó phải được quản lý bền vững cùng data directory. Mất WAL có thể làm cluster không thể recover.

Không đặt WAL trên tmpfs hoặc container writable layer trong một hệ thống cần durability.

### 10.3. Tablespaces

Tablespaces có thể đặt relation files ở locations ngoài `PGDATA`. Các locations này phải được mount/persist trên mọi host cần sử dụng chúng. Logical/physical backup và restore cần xử lý tablespaces theo đúng phương thức.

### 10.4. Archive destination

`archive_command` hoặc archive library có thể ghi WAL ra object storage, filesystem hoặc dịch vụ ngoài. Archive location cần credentials, network policy, retention và monitoring riêng.

### 10.5. Configuration

Có thể mount configuration read-only hoặc quản lý qua ConfigMap/secret/config management. Đảm bảo config không bị mất khi recreate container và có version/audit. Tránh mount cả một thư mục config làm che các file mặc định mà image cần.

### 10.6. Secrets và certificates

Mount password/certificate từ secret manager hoặc Kubernetes Secret theo policy. Hạn chế quyền đọc và không bake secrets vào image layer. Kiểm tra file mode, rotation và certificate reload/restart requirement.

## 11. Dung lượng và I/O của volume

PostgreSQL có thể tăng dung lượng nhanh hơn dự kiến do WAL, index builds, temp files, bloat và long-running transactions.

### 11.1. Theo dõi dung lượng filesystem

Trong container hoặc node, kiểm tra total/used/available bytes, inodes nếu filesystem có giới hạn, per-directory growth, WAL directory size, temporary files, tablespace paths và volume quota.

### 11.2. Volume gần đầy là incident

Disk full có thể khiến writes, WAL creation, checkpoints hoặc maintenance fail. Thiết lập alerts trước khi hết dung lượng và xác định hành động: mở rộng volume, dọn dữ liệu được phép, kiểm tra replication slots/archives hoặc xử lý runaway temp files.

Không xóa file trong `PGDATA` hoặc `pg_wal` bằng shell để lấy dung lượng. Dùng PostgreSQL-supported procedures để xử lý WAL, logs và database objects.

### 11.3. PVC expansion

Một số StorageClasses/CSI drivers hỗ trợ mở rộng volume. Việc tăng PVC capacity có thể cần:
- StorageClass cho phép expansion.
- PVC spec update.
- CSI volume expansion.
- Filesystem resize.
- Pod remount/restart tùy driver.

Xác nhận capacity thực tế trong pod sau khi expand. Không giả định sửa `resources.requests.storage` lập tức làm filesystem tăng dung lượng.

### 11.4. IOPS và throughput

Đặt limits/provisioned performance theo workload. Theo dõi latency của volume, queue depth và throttling. Một volume shared với backup/logging workload có thể gây contention.

### 11.5. WAL và data volume riêng

Tách WAL sang volume riêng có thể hữu ích trong một số thiết kế, nhưng tạo thêm failure domain và consistency requirements. Nếu tách:
- Cả hai volume đều phải persistent.
- Mount paths phải có trên mọi replacement node.
- Backup/snapshot phải capture trạng thái nhất quán của cả hai.
- Capacity và IOPS được sizing riêng.
- Restore procedure phải khôi phục cả hai đúng vị trí.

Không tách WAL chỉ vì thấy cấu hình trong một bài hướng dẫn mà chưa benchmark.

## 12. Stateful workloads trong Kubernetes

PostgreSQL là stateful workload. Kubernetes cung cấp StatefulSet, PVC và storage orchestration để quản lý identity/storage.

### 12.1. StatefulSet

StatefulSet cung cấp stable pod identity và có thể tạo PVC riêng từ `volumeClaimTemplates`. Đây là pattern phổ biến cho một PostgreSQL instance trên mỗi pod, kết hợp operator hoặc replication manager khi cần HA.

### 12.2. PVC template

Ví dụ rút gọn:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:17
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 100Gi
```

Skeleton này minh họa stable PVC association. Production cần StorageClass, security context, resources, probes, secrets, config, service, backup và HA design.

### 12.3. ReadWriteOnce không phải database lock

`ReadWriteOnce` mô tả access mode ở mức volume attachment/node theo storage implementation; nó không phải cơ chế PostgreSQL multi-writer lock. Một số CSI drivers hỗ trợ nhiều pods trên cùng node mount volume theo cách riêng. Không dựa vào access mode để cho phép hai PostgreSQL servers dùng chung `PGDATA`.

### 12.4. ReadWriteOncePod

Nếu CSI/platform hỗ trợ, `ReadWriteOncePod` có thể giới hạn volume được mount bởi một pod tại một thời điểm. Đây là lớp bảo vệ bổ sung; vẫn cần kiến trúc đảm bảo một writer và quy trình fencing/HA.

### 12.5. PVC lifecycle

PVC thường tồn tại độc lập với Pod. Xóa Pod không nhất thiết xóa PVC. Xóa StatefulSet cũng có retention behavior phụ thuộc policy/version. Xác định rõ khi scale down hoặc delete StatefulSet thì PVC giữ lại hay xóa.

### 12.6. PV reclaim policy

`Retain` giữ underlying storage sau khi PVC/PV được giải phóng, giúp quản trị viên xử lý dữ liệu có kiểm soát. `Delete` có thể yêu cầu storage provider xóa volume khi claim được giải phóng. Kiểm tra StorageClass/PV policy trước khi xóa claim.

### 12.7. Không dùng replicas: 2 với cùng một PGDATA

Hai PostgreSQL containers không trở thành HA chỉ bằng cách chạy hai replicas cùng mount. HA cần mỗi instance có storage riêng, replication/fencing, leader election và failover policy. Một shared volume với hai postmasters có thể làm hỏng cluster.

## 13. Docker Compose và volume lifecycle

Compose phù hợp cho development, test và một số deployment đơn host. Production HA cần đánh giá thêm host failure, storage failure và failover.

### 13.1. Khai báo volume ổn định

```yaml
services:
  db:
    image: postgres:17
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  postgres_data:
    name: production-postgres-data
```

Đặt tên rõ giúp nhận diện volume. Pin image version/digest theo release process; không dùng floating tag không kiểm soát cho database production.

### 13.2. docker compose up và recreate

Khi container được recreate, Compose gắn lại named volume theo project/config. Kiểm tra volume name không đổi do project name hoặc directory thay đổi.

### 13.3. down, down -v và prune

- `docker compose down` thường xóa containers/networks nhưng giữ named volumes.
- `docker compose down -v` yêu cầu xóa volumes của project theo semantics Compose.
- `docker volume prune` có thể xóa volumes không còn được dùng.

Trước khi chạy, inspect volume và xác nhận backup/retention. Các lệnh cleanup có thể gây mất dữ liệu không phục hồi nếu volume không có backup.

### 13.4. Compose project name

Volume mặc định có thể được prefix bởi project name. Khi đổi folder/project name, có thể tạo volume mới rỗng thay vì gắn volume cũ. Dùng `name`/`external` khi cần identity ổn định và ghi lại quy trình migration.

### 13.5. Không coi restart policy là HA

`restart: unless-stopped` chỉ điều khiển restart container theo runtime policy. Nó không cung cấp replication, backup, fencing, multi-node failover hoặc bảo đảm data volume còn truy cập được sau host loss.

## 14. Vòng đời container và PostgreSQL shutdown

Container có lifecycle riêng: create, start, stop, restart, kill, remove. PostgreSQL có lifecycle riêng: startup, recovery, accepting connections, shutdown và crash recovery.

### 14.1. Graceful shutdown

Khi dừng container, runtime gửi signal tới process theo cấu hình image/runtime, rồi có thể gửi kill signal sau timeout. PostgreSQL có các shutdown modes khác nhau:
- Smart: chờ clients disconnect.
- Fast: ngắt clients và rollback active transactions.
- Immediate: dừng ngay, lần start tiếp theo phải crash recovery.

Trong container environment, kiểm tra signal được truyền tới PostgreSQL process và timeout đủ dài cho shutdown policy đã chọn.

### 14.2. Termination grace period

Đặt stop timeout/termination grace period đủ cho PostgreSQL dừng dưới workload bình thường. Nếu timeout quá ngắn, runtime có thể kill process trước khi shutdown hoàn tất. Khi đó PostgreSQL thường cần crash recovery ở lần start tiếp theo, làm tăng downtime và cần kiểm tra logs.

### 14.3. PID 1 và signal forwarding

Entrypoint shell cần `exec` hoặc cơ chế init/signal forwarding phù hợp để signal đến server process. Tránh chạy shell wrapper không forward signals.

### 14.4. Restart không đồng nghĩa restore

Restart container với cùng volume thường chỉ start lại cluster và thực hiện recovery nếu cần. Nó không phục hồi data đã bị xóa, volume corruption hoặc một major-version incompatibility.

### 14.5. Stop trước khi detach/di chuyển volume

Không detach block volume hoặc di chuyển data directory khi postmaster còn chạy. Dừng server theo quy trình, xác nhận shutdown hoàn tất rồi mới detach/snapshot/copy theo hướng dẫn storage platform.

### 14.6. Crash recovery

Sau process/host crash, PostgreSQL dùng WAL để phục hồi cluster. Đảm bảo `PGDATA` và WAL storage cùng tồn tại và storage đã thực hiện flush đúng semantics. Kiểm tra startup logs và recovery completion trước khi mở traffic.

## 15. Startup, readiness và liveness probes

Orchestrator cần biết container đã start, PostgreSQL có nhận connections và ứng dụng có thể sử dụng đúng role/endpoint hay chưa.

### 15.1. Startup probe

Startup probe cho phép database có thời gian khởi động/recovery lâu mà không bị liveness probe restart liên tục. Đặt budget dựa trên thời gian recovery có thể xảy ra.

### 15.2. Readiness probe

Readiness quyết định pod có nhận traffic hay không. `pg_isready` kiểm tra trạng thái kết nối PostgreSQL, nhưng không tự xác nhận:
- Node là primary hay standby.
- Database ứng dụng đã tồn tại.
- Role ứng dụng có quyền.
- Schema migration đã hoàn tất.
- Remote dependencies khỏe.

Nếu ứng dụng cần writable primary, readiness check phải phản ánh role/condition đó theo HA design.

### 15.3. Liveness probe

Liveness xác định process có cần restart hay không. Không dùng một query nặng hoặc dependency bên ngoài làm liveness nếu lỗi tạm thời sẽ tạo restart loop.

### 15.4. Probe timing

Cấu hình initial delay/period/timeout/failure threshold dựa trên startup/recovery measurements. Nếu probe timeout quá thấp trong load spike, orchestrator có thể restart database đang phục vụ traffic.

### 15.5. Kubernetes probe example

```yaml
startupProbe:
  exec:
    command:
      - sh
      - -c
      - pg_isready -h 127.0.0.1 -p 5432
  periodSeconds: 5
  failureThreshold: 60

readinessProbe:
  exec:
    command:
      - sh
      - -c
      - pg_isready -h 127.0.0.1 -p 5432
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3

livenessProbe:
  exec:
    command:
      - sh
      - -c
      - pg_isready -h 127.0.0.1 -p 5432
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 6
```

Đây là ví dụ khởi đầu, không phải probe policy cho mọi deployment. Với HA, readiness cần xác định primary/standby role và app-specific conditions. Cấu hình startup probe để tránh liveness can thiệp trước khi recovery có cơ hội hoàn tất.

## 16. Storage consistency và durability

PostgreSQL durability dựa vào WAL, fsync/flush, filesystem và storage hardware/platform.

### 16.1. Không tắt fsync để tăng tốc production

`fsync=off` có thể làm mất hoặc hỏng dữ liệu sau OS/power crash. Chỉ dùng trong môi trường disposable/test khi hiểu rõ rủi ro; không dùng như tối ưu mặc định.

### 16.2. Storage cache và flush guarantees

Kiểm tra provider có bảo đảm write ordering/flush semantics không. Một storage layer xác nhận write trước khi dữ liệu thực sự bền vững có thể phá durability assumptions.

### 16.3. Synchronous commit

`synchronous_commit` ảnh hưởng thời điểm commit được xác nhận so với WAL flush/replication mode. Không thay đổi chỉ để che storage latency; xác định durability contract và test failover/data-loss window.

### 16.4. Clock và host events

Container không có storage riêng biệt khỏi host kernel/device. Node reboot, disk detach, host replacement và storage failover đều thuộc recovery model. Ghi lại event behavior của provider.

### 16.5. Không copy live PGDATA bằng file copy thông thường

Copy thư mục database khi PostgreSQL đang chạy mà không dùng backup method được hỗ trợ có thể tạo inconsistent copy. Dùng `pg_basebackup`, backup mode/API được hỗ trợ hoặc snapshot workflow có consistency và WAL recovery phù hợp.

## 17. Backup, snapshot và restore của volume

Persistent volume bảo vệ dữ liệu khỏi container deletion nhưng không thay backup độc lập.

### 17.1. Logical backup

`pg_dump`/`pg_dumpall` tạo logical backups phù hợp cho database/object-level recovery và migration. Backup files phải được lưu ngoài volume database và có retention/restore tests.

### 17.2. Physical backup

Dùng `pg_basebackup` hoặc backup tooling hỗ trợ PostgreSQL physical backup và WAL archiving. Đảm bảo tool version và procedure tương thích với server.

### 17.3. Volume snapshot

Snapshot storage có thể hữu ích, nhưng cần biết:
- Snapshot có crash-consistent hay application-consistent?
- Một hay nhiều volumes được snapshot atomically?
- Có capture WAL và tablespaces không?
- Có cần checkpoint/quiesce/backup mode?
- Snapshot có thể attach vào host khác không?
- Snapshot retention và encryption thế nào?

Một snapshot nhất quán của block volume có thể phục hồi như sau crash nếu PostgreSQL và storage guarantees phù hợp; snapshot của nhiều volumes ở các thời điểm khác nhau có thể không nhất quán.

### 17.4. WAL archive và PITR

Để point-in-time recovery, cần base backup và chuỗi WAL liên tục tới target time. Archive phải ở storage độc lập, có monitoring cho failed archive, retention và restore test.

### 17.5. Restore drill

Định kỳ restore vào volume/cluster mới:
1. Tạo target volume.
2. Cài PostgreSQL và extension packages đúng versions.
3. Khôi phục base backup hoặc logical dump.
4. Cấu hình tablespaces/WAL paths.
5. Replay WAL nếu PITR.
6. Kiểm tra recovery complete.
7. Chạy database/application validation.
8. Đo thời gian phục hồi và cập nhật RTO/RPO.

### 17.6. Backup không cùng volume

Nếu backup file được ghi vào cùng volume với PGDATA, volume loss có thể xóa cả database và backup. Dùng independent storage, account/region hoặc backup service phù hợp với threat model.

## 18. Tablespaces và nhiều volumes

Tablespace cho phép relation files nằm ngoài data directory.

### 18.1. Mount path ổn định

Nếu tablespace path là `/pg_tblspc` symlink tới mount khác, target path phải có mặt với đúng ownership trước khi server start. Mọi node có thể promote hoặc restore phải có cấu trúc phù hợp.

### 18.2. Backup coverage

Physical backup/restore cần bao gồm tablespace contents theo quy trình. Logical dump có thể tái tạo objects vào tablespace được chỉ định nhưng không bảo toàn mọi physical layout.

### 18.3. Snapshot consistency

Nếu data, WAL và tablespaces ở nhiều volumes, dùng snapshot group/consistency group nếu provider hỗ trợ hoặc dùng backup method được hỗ trợ. Snapshot từng volume không đồng bộ có thể tạo state không thể replay an toàn.

### 18.4. Disk failure domain

Tách volumes có thể tăng hiệu năng hoặc quản lý capacity nhưng cũng tạo thêm failure domains. Đánh giá volume loss, attach failure và recovery cho từng path.

## 19. Major-version upgrade trong container

Đổi image tag không phải là major-version upgrade database.

### 19.1. Data directory format

PostgreSQL major versions có thể thay đổi internal data format. Không khởi động binary major mới trực tiếp trên data directory của major cũ trừ khi đang dùng một quy trình upgrade được hỗ trợ.

### 19.2. Các phương thức migration

Tùy môi trường, có thể dùng:
- `pg_upgrade`.
- Logical dump/restore.
- Logical replication/cutover.
- Managed provider upgrade workflow.

Chọn method dựa trên extension compatibility, downtime, data size và recovery plan.

### 19.3. Không gắn volume production vào container thử nghiệm

Tạo snapshot/clone hoặc restore sang volume riêng cho rehearsal. Không để hai containers có thể cùng ghi data directory production.

### 19.4. Pin image version

Dùng exact major/minor tag hoặc immutable digest theo release policy. Floating `latest` có thể làm deploy vô tình thay major version hoặc OS base.

### 19.5. Extension binaries

Cài native extension binaries phù hợp với target PostgreSQL major trên target image/hosts. Data/catalog migration và `ALTER EXTENSION UPDATE` là các bước cần kiểm tra riêng theo hướng dẫn extension.

### 19.6. Rollback major upgrade

Không thể rollback bằng cách thay image về major cũ rồi gắn target data directory. Giữ source cluster/backup riêng và thiết kế cutover/reconciliation trước khi target nhận writes.

## 20. Rolling updates và HA

PostgreSQL không phải stateless web service. Rolling update phải theo database topology.

### 20.1. Primary và standbys

Mỗi node có volume riêng. Trước khi failover/promote, xác nhận node có đúng image, configuration, extension packages, certificates và data state.

### 20.2. Fencing

HA manager phải bảo đảm node cũ không tiếp tục ghi sau khi node mới được promote. Storage attachment policy một mình không thay thế fencing/leader election.

### 20.3. Node rescheduling

Khi pod được schedule sang node khác, CSI driver phải attach volume, mount đúng filesystem và khôi phục ownership/labels. Đo attach/mount/startup/recovery duration.

### 20.4. PodDisruptionBudget

PDB có thể hạn chế voluntary disruptions nhưng không bảo vệ khỏi mọi node/storage failure. Cấu hình theo số replicas/HA policy và hiểu interaction với node drain.

### 20.5. StatefulSet rollout

StatefulSet update strategy có thể thay pod tuần tự, nhưng không tự biết PostgreSQL replication safety hoặc promotion order. Dùng operator/HA controller được thiết kế cho PostgreSQL khi cần managed failover.

### 20.6. Replication readiness

Trước khi update/failover, kiểm tra replay lag, replication state, timeline và slots. Một standby chưa catch up có thể làm mất transactions đã commit trên primary khi promote.

## 21. Kubernetes storage lifecycle

### 21.1. StorageClass

StorageClass xác định provisioner và parameters như disk type, performance tier, encryption hoặc topology. Pin/record StorageClass và hiểu behavior khi volume được provision ở zone cụ thể.

### 21.2. VolumeBindingMode

`WaitForFirstConsumer` có thể trì hoãn provision/binding tới khi scheduler biết pod topology. Điều này hữu ích cho zonal volumes nhưng có thể ảnh hưởng scheduling.

### 21.3. Topology và zone

Persistent block volume có thể chỉ attach trong một zone. Pod reschedule sang zone khác có thể không mount được. Thiết kế HA/DR cần xử lý zone failure, cross-zone replication và restore.

### 21.4. PVC deletion protection

Xác định StatefulSet PVC retention policy, PV reclaim policy và provider snapshot/backup. Không giả định xóa StatefulSet sẽ luôn giữ hoặc luôn xóa claims.

### 21.5. Restore sang PVC mới

Khi phục hồi, thường tạo PVC mới từ snapshot/backup và triển khai pod với claim đó. Kiểm tra identity/path/ownership trước khi server start.

## 22. Security và data-at-rest

Volume chứa database files, WAL, temp data và có thể chứa dữ liệu nhạy cảm.

Kiểm tra:
- Encryption at rest của cloud volume.
- Encryption key ownership/rotation.
- Filesystem permissions.
- Host access.
- Snapshot access policy.
- Backup encryption.
- Secret mounts.
- Audit log.
- Data deletion/retention policy.

### 22.1. Encryption at rest

Ưu tiên encryption do storage provider/host platform hỗ trợ theo policy. Kiểm tra key permissions và khả năng restore khi key rotation hoặc key revocation.

### 22.2. Container access

Chỉ container PostgreSQL và các maintenance/backup processes được quyền cần thiết vào PGDATA. Tránh mount data volume vào nhiều application containers.

### 22.3. Snapshot permissions

Snapshot có thể chứa toàn bộ database, bao gồm deleted-but-not-yet-reclaimed data và WAL. Giới hạn ai có thể copy, share, export hoặc restore snapshot.

### 22.4. Temporary files

Sort/hash spills có thể chứa dữ liệu nhạy cảm. Chọn temp storage, permissions và retention theo policy. Nếu temp path nằm trên ephemeral disk, chấp nhận rõ việc mất temp files khi container dừng.

## 23. Monitoring cho volume và container lifecycle

Theo dõi database và storage cùng lúc.

### 23.1. Storage metrics

- Volume capacity/available bytes.
- IOPS/throughput.
- Read/write latency.
- Queue depth/throttling.
- Filesystem errors.
- Attach/mount failures.
- PVC pending/binding state.
- Volume expansion status.

### 23.2. PostgreSQL metrics

- WAL generation and archive status.
- Checkpoint activity.
- Replication lag.
- Long-running transactions.
- Temporary file usage.
- Database size/index growth.
- Autovacuum progress.
- Startup/recovery duration.
- Connection saturation.

### 23.3. Container metrics

- Restart count.
- OOM kills.
- Exit codes.
- Termination reason.
- Startup/readiness duration.
- Node evictions.
- Probe failures.
- CPU/memory throttling.

### 23.4. Alerting

Alert trước khi volume đầy hoặc replica lag vượt budget. Cảnh báo restart loop, mount failure, permission denied, archive backlog và repeated recovery. Alert phải có runbook tương ứng.

### 23.5. Correlate events

Khi PostgreSQL chậm, đối chiếu query latency với volume latency, node pressure, CPU throttling và WAL/checkpoint metrics. Không quy mọi latency spike cho SQL planner.

## 24. Ví dụ Docker Compose có data volume và config riêng

Ví dụ sau minh họa volume data và mount config read-only:

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./postgresql.conf:/etc/postgresql/postgresql.conf:ro
    command:
      - postgres
      - -c
      - config_file=/etc/postgresql/postgresql.conf
    secrets:
      - db_password
    restart: unless-stopped
    stop_grace_period: 1m

volumes:
  pgdata:

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

Đây là ví dụ minh họa; cách hỗ trợ `POSTGRES_PASSWORD_FILE`, secret mounts, config path và entrypoint phụ thuộc image/runtime. Bảo đảm file config có quyền đọc phù hợp và không ghi đè các defaults quan trọng ngoài ý muốn. File secret không được commit vào source control.

## 25. Ví dụ Kubernetes PVC và Pod security

Một PVC tối giản:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
  storageClassName: fast-block
```

Tên `fast-block` là ví dụ, phải thay bằng StorageClass thực tế.

Một Pod tham chiếu claim:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: postgres
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 999
    runAsGroup: 999
    fsGroup: 999
    fsGroupChangePolicy: OnRootMismatch
  containers:
    - name: postgres
      image: postgres:17
      env:
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
      volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
      resources:
        requests:
          cpu: "1"
          memory: 2Gi
        limits:
          memory: 4Gi
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: postgres-data
```

Ví dụ chưa bao gồm Service, Secrets, probes, config, backup, HA và resource sizing. Với production, cân nhắc PostgreSQL operator hoặc platform-specific controller thay vì tự viết toàn bộ lifecycle management.

## 26. Runbook: PostgreSQL báo permission denied

Khi server không thể đọc/ghi data directory:

1. Kiểm tra logs để xác định path và operation bị deny.
2. Xác nhận container đang mount đúng volume.
3. Kiểm tra UID/GID thực tế của process PostgreSQL.
4. Kiểm tra owner/mode của PGDATA và parent directories.
5. Kiểm tra rootless/user namespace mapping.
6. Kiểm tra SELinux/AppArmor denials.
7. Kiểm tra filesystem mount read-only hoặc volume attach mode.
8. Dừng server nếu cần thay ownership/mode.
9. Sửa đúng path/UID/GID theo image và policy.
10. Start staging hoặc instance đã được phê duyệt và xác nhận recovery.

Không chạy `chmod -R 777`, không chạy server dưới root và không xóa data directory để khắc phục lỗi permissions.

## 27. Runbook: container start với volume rỗng

Nếu container mới khởi tạo database rỗng thay vì thấy cluster cũ:

1. Dừng application traffic tới container mới.
2. Xác nhận container đang mount volume nào.
3. Inspect volume name/ID và host path.
4. Kiểm tra Compose project name hoặc PVC claim binding.
5. Kiểm tra `PGDATA` có thay đổi so với image trước không.
6. Kiểm tra mount destination có bị đổi không.
7. Tìm volume cũ theo inventory/backup; không prune/delete.
8. Reattach đúng volume sau khi xác nhận ownership.
9. Kiểm tra `PG_VERSION` và cluster identity.
10. Chỉ mở traffic sau khi xác nhận đúng cluster và recovery state.

Đừng initdb thêm vào volume production chỉ vì entrypoint không tìm thấy cluster mong đợi.

## 28. Runbook: volume không attach hoặc pod Pending

1. Kiểm tra PVC/PV state và events.
2. Kiểm tra StorageClass/provisioner.
3. Kiểm tra zone/topology constraints.
4. Kiểm tra volume có đang attach vào node khác không.
5. Kiểm tra provider API/quota/permission.
6. Kiểm tra access mode và CSI driver support.
7. Không force detach khi PostgreSQL có thể còn ghi.
8. Dùng HA/fencing runbook để xác nhận node cũ đã dừng.
9. Attach volume theo quy trình provider.
10. Xác nhận filesystem và PostgreSQL recovery trước khi nhận traffic.

## 29. Runbook: container bị kill hoặc restart loop

1. Xem exit code, termination reason, OOMKilled và probe events.
2. Kiểm tra startup logs và PostgreSQL crash recovery.
3. Xác nhận termination grace period có đủ không.
4. Kiểm tra volume mount/permissions sau restart.
5. Kiểm tra memory limit và OOM pressure.
6. Kiểm tra startup/liveness probes có quá aggressive không.
7. Xác định extension/preload/library có làm startup fail không.
8. Không xóa `postmaster.pid` khi chưa xác nhận không còn postmaster sử dụng data directory.
9. Đợi recovery hoàn tất và chạy validation.
10. Điều chỉnh resource/probe/shutdown policy sau khi xác định nguyên nhân.

## 30. Runbook: volume gần đầy

1. Xác định filesystem/volume và path đang tăng.
2. Phân biệt database files, WAL, archive, temp files và logs.
3. Kiểm tra replication slots và archive backlog.
4. Kiểm tra long-running transactions/autovacuum.
5. Mở rộng volume nếu platform hỗ trợ và đã được phê duyệt.
6. Xử lý logs/backup/temp files theo retention policy.
7. Không xóa WAL files thủ công.
8. Theo dõi filesystem capacity và recovery.
9. Xác nhận archive/replication hoạt động trở lại.
10. Điều chỉnh capacity alerts và growth forecast.

## 31. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả |
|---|---|
| Lưu PGDATA trong writable layer | Mất database khi container bị xóa |
| Mount nhầm volume mới rỗng | Container tạo cluster mới, ứng dụng nhìn thấy database rỗng |
| Đổi PGDATA path | Entry point không tìm thấy cluster cũ |
| UID/GID không khớp | Permission denied hoặc initdb/startup fail |
| chmod 777 | Mở rộng quyền truy cập và có thể vi phạm kiểm tra permissions |
| Chạy PostgreSQL bằng root | Vi phạm security model của PostgreSQL |
| fsGroup không được kiểm chứng | Volume vẫn không writable hoặc startup rất chậm |
| Thiếu SELinux label | Permission denied dù mode bits đúng |
| WAL nằm trên ephemeral storage | Không thể crash recovery sau container/host loss |
| Xóa PVC/volume khi cleanup | Mất database |
| Hai postmasters dùng chung PGDATA | Corruption hoặc concurrent access không an toàn |
| Chỉ có snapshot cùng volume | Không có backup độc lập khi volume loss |
| Đổi image major trực tiếp | Binary không tương thích data directory |
| Stop timeout quá ngắn | Process bị kill và cần crash recovery |
| Probe quá aggressive | Restart loop trong startup/recovery |
| Không test attach ở node khác | Failover/reschedule không thể mount storage |

## 32. Checklist trước khi triển khai

- [ ] Chọn storage type được PostgreSQL/platform hỗ trợ.
- [ ] Đánh giá latency, IOPS, throughput và durability.
- [ ] Tách PGDATA khỏi container writable layer.
- [ ] Pin image tag/digest và xác nhận default PGDATA.
- [ ] Xác nhận volume name/claim identity ổn định.
- [ ] Kiểm tra mount source/destination và read/write mode.
- [ ] Xác nhận UID/GID của image.
- [ ] Xác nhận ownership/mode của PGDATA và parent paths.
- [ ] Kiểm tra rootless/user namespace mapping.
- [ ] Kiểm tra SELinux/AppArmor.
- [ ] Xác nhận WAL và tablespaces persistent.
- [ ] Xác định backup/archive locations độc lập.
- [ ] Kiểm tra secret/config mounts.
- [ ] Xác định stop timeout và startup/recovery budget.
- [ ] Thiết kế probes theo primary/standby role.
- [ ] Xác định PVC/PV retention và reclaim policy.
- [ ] Xác nhận mỗi PostgreSQL instance có storage riêng.
- [ ] Rehearse restart, recreate, reschedule và restore.

## 33. Checklist vận hành

- [ ] Container restart giữ đúng volume và cluster identity.
- [ ] Image update không thay đổi data directory path ngoài dự kiến.
- [ ] Graceful shutdown hoàn tất trong termination budget.
- [ ] Startup probe không restart cluster đang recovery.
- [ ] Readiness chỉ mở traffic khi role/DB state phù hợp.
- [ ] Disk capacity và I/O latency có alerts.
- [ ] WAL/archive/replication lag được theo dõi.
- [ ] PVC attach/mount events được giám sát.
- [ ] Permission/SELinux errors có runbook.
- [ ] Snapshot/backup có retention và restore drill.
- [ ] Failover node có extension packages/config phù hợp.
- [ ] PVC deletion/prune commands có approval/process.
- [ ] Major upgrade rehearsal dùng clone/volume riêng.
- [ ] Không có nhiều postmasters cùng sử dụng PGDATA.

## 34. Tài liệu chính thức tham khảo

- [PostgreSQL — File System Level Backup](https://www.postgresql.org/docs/current/backup-file.html): backup bằng filesystem và yêu cầu consistency.
- [PostgreSQL — Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backup, WAL archive và PITR.
- [PostgreSQL — pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): physical base backup.
- [PostgreSQL — initdb](https://www.postgresql.org/docs/current/app-initdb.html): khởi tạo cluster và data directory permissions.
- [PostgreSQL — Server Shutdown](https://www.postgresql.org/docs/current/server-shutdown.html): shutdown modes.
- [PostgreSQL — WAL Reliability](https://www.postgresql.org/docs/current/wal-reliability.html): durability và storage assumptions.
- [Docker — Volumes](https://docs.docker.com/engine/storage/volumes/): named volumes và lifecycle.
- [Docker — Bind Mounts](https://docs.docker.com/engine/storage/bind-mounts/): host paths và mount behavior.
- [Docker Compose — Volumes](https://docs.docker.com/reference/compose-file/volumes/): volume configuration.
- [Kubernetes — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/): PV, PVC, StorageClass và reclaim policy.
- [Kubernetes — StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/): stable identity và storage claims.
- [Kubernetes — Security Context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/): runAsUser, fsGroup và security settings.
- [Kubernetes — Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): startup, readiness và liveness probes.

Đường dẫn /current/ của PostgreSQL và tài liệu Docker/Kubernetes có thể thay đổi theo phiên bản. Khi triển khai, kiểm tra manual tương ứng với PostgreSQL major, image digest, container runtime, Kubernetes version và CSI driver thực tế.

## 35. Tổng kết

PostgreSQL trong container chỉ bền vững khi database files được đặt trên storage có lifecycle độc lập, quyền truy cập phù hợp và recovery procedure đã được thử nghiệm. Container có thể được recreate, nhưng volume, WAL, tablespaces, backups và identity của cluster phải được quản lý nhất quán.

1. **Storage:** dùng persistent volume phù hợp, đo latency/IOPS/throughput và không lưu PGDATA trên writable layer hoặc tmpfs.
2. **Paths:** cố định PGDATA, mount destination, WAL và tablespaces; kiểm tra volume identity trước khi start.
3. **Permissions:** chạy PostgreSQL bằng non-root user, xác nhận UID/GID, ownership, mode bits và SELinux labels.
4. **Lifecycle:** truyền shutdown signals đúng, dành đủ termination time, cấu hình probes theo startup/recovery và không dùng restart policy thay HA.
5. **Recovery:** backup độc lập, archive WAL, snapshot nhất quán và restore drill trên volume mới.
6. **Kubernetes/Compose:** quản lý PVC/named volume retention, storage topology và deletion policy có chủ đích.
7. **Upgrade:** không đổi major image rồi gắn trực tiếp data directory cũ; dùng quy trình migration PostgreSQL được hỗ trợ.

Một triển khai đáng tin cậy phải vượt qua thử nghiệm recreate container, restart node, attach volume ở node phù hợp, restore từ backup và phục hồi sau crash mà vẫn giữ đúng cluster, dữ liệu và quyền truy cập.
