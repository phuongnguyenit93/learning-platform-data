# Quyền người dùng, filesystem chỉ đọc và thư mục cần ghi

Chạy ứng dụng Java với filesystem chỉ đọc và user không phải root là một cách giảm quyền của container. Cấu hình này cũng làm lộ rõ những nơi ứng dụng và CRaC cần ghi dữ liệu. JVM có thể cần thư mục tạm để giải nén native library hoặc tạo file tạm; framework có thể ghi cache; ứng dụng có thể tạo file, log hoặc PID; còn checkpoint engine cần một nơi lưu checkpoint image và metadata theo cách triển khai.

Với CRaC trong container, cần thiết kế quyền truy cập theo từng loại tài nguyên. Root filesystem có thể chỉ đọc trong khi các volume được mount riêng vẫn ghi được. User chạy JVM phải có quyền đọc ứng dụng, ghi đúng các thư mục runtime cần thiết và truy cập các tài nguyên checkpoint mà nền tảng cho phép. Khi restore, danh tính UID/GID, mount và quyền truy cập phải tương thích với trạng thái đã checkpoint.

Không cần chạy toàn bộ container bằng root chỉ vì checkpoint cần quyền đặc biệt. Trước hết hãy tách quyền của ứng dụng khỏi quyền của checkpoint/restore runtime; quyền bổ sung nào cần thiết phụ thuộc kernel, CRIU, container runtime và chính sách Kubernetes của cluster.

## 1. Vì sao quyền filesystem quan trọng với CRaC?

Checkpoint lưu trạng thái tiến trình đang chạy. Quá trình tạo và restore checkpoint còn liên quan tới file descriptor, file đang mở, socket, thư mục làm việc, mount namespace và những đường dẫn mà tiến trình sử dụng. Một ứng dụng chạy bình thường trong container có root filesystem ghi được có thể thất bại khi bật `readOnlyRootFilesystem` nếu một thư viện cố ghi vào `/tmp`, thư mục hiện hành hoặc home directory.

Các vấn đề thường gặp:

- JVM hoặc thư viện cần tạo file tạm trong `/tmp`.
- Native library được giải nén vào `java.io.tmpdir` khi nạp.
- Framework ghi cache, PID file, lock file hoặc file upload vào thư mục cài đặt.
- Log appender ghi vào một file nằm dưới root filesystem.
- Ứng dụng ghi dữ liệu trạng thái vào thư mục không có volume.
- Checkpoint engine không thể tạo checkpoint image vì thư mục đích không tồn tại hoặc user không có quyền ghi.
- Restore thất bại vì checkpoint image không đọc được, mount path thay đổi hoặc UID/GID không còn quyền truy cập.

Vì vậy, cần xác định rõ ba nhóm đường dẫn:

1. **Đường dẫn chỉ cần đọc:** JAR, classpath, cấu hình bất biến, thư viện và file ứng dụng.
2. **Đường dẫn ứng dụng cần ghi:** temp, cache, dữ liệu runtime, log file hoặc file trạng thái nếu ứng dụng thực sự cần.
3. **Đường dẫn checkpoint:** nơi checkpoint engine hoặc công cụ điều phối ghi và đọc checkpoint image, metadata và file phụ trợ.

Đường dẫn checkpoint có thể được quản lý bên ngoài container hoặc được mount vào container, tùy cách tích hợp CRaC/CRIU. Không giả định rằng mọi triển khai đều yêu cầu ứng dụng Java tự ghi checkpoint image vào một thư mục cố định.

## 2. Chạy JVM bằng user không phải root

Trong container, user mặc định có thể là root nếu image không chỉ định `USER`. Chạy ứng dụng với UID/GID riêng giúp giới hạn tác động khi ứng dụng bị khai thác hoặc ghi nhầm file.

Ví dụ, image có thể dùng UID `10001` và GID `10001` cho tiến trình Java. Các con số này là ví dụ; cần chọn ID phù hợp với chính sách user/group của hệ thống.

```dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /opt/app

# Ứng dụng và thư mục bất biến thuộc sở hữu của user runtime.
COPY --chown=10001:10001 app.jar /opt/app/app.jar

# Chỉ tạo các thư mục runtime mà ứng dụng thực sự cần ghi.
RUN mkdir -p /var/lib/myapp /var/cache/myapp /var/log/myapp /tmp \
    && chown -R 10001:10001 /var/lib/myapp /var/cache/myapp /var/log/myapp \
    && chmod 0750 /var/lib/myapp /var/cache/myapp /var/log/myapp \
    && chmod 1777 /tmp

ENV JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=/tmp"

USER 10001:10001

ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
```

Trong ví dụ này:

- JAR nằm dưới `/opt/app` và chỉ cần đọc khi chạy.
- User runtime có quyền ghi vào các thư mục dữ liệu đã được tạo sẵn.
- `/tmp` có sticky bit (`1777`) để nhiều user có thể tạo file tạm mà không tùy tiện xóa file của nhau.
- JVM dùng `/tmp` làm thư mục tạm.

Nếu triển khai với `readOnlyRootFilesystem`, những thư mục ghi được trong image vẫn trở thành chỉ đọc khi container chạy với root filesystem read-only. Khi đó cần mount volume ghi được vào đúng các đường dẫn ứng dụng cần sử dụng.

### 2.1. UID và GID phải được giữ nhất quán

Quyền trên Linux dựa trên UID, GID, supplementary groups, mode bits và ACL. Tên user trong `/etc/passwd` chỉ là cách ánh xạ dễ đọc; kernel kiểm tra ID số của tiến trình.

Khi tạo checkpoint và restore, cần duy trì danh tính phù hợp:

- Dùng cùng UID/GID cho tiến trình Java ở các lần chạy cần dùng chung checkpoint.
- Bảo đảm UID/GID có quyền đọc checkpoint image và ghi các thư mục runtime.
- Nếu volume được tạo từ trước, kiểm tra ownership thực tế trên volume, không chỉ nhìn `runAsUser` trong YAML.
- Với rootless container hoặc user namespace, phân biệt UID trong container với UID được ánh xạ trên host.
- Không giả định tên user giống nhau nghĩa là UID/GID giống nhau.

Một checkpoint được tạo khi tiến trình chạy dưới UID này không tự động cấp quyền cho một tiến trình restore chạy dưới UID khác. Ngoài file permissions, checkpoint engine còn có thể áp dụng ràng buộc về credential, capability và namespace của tiến trình. Hãy dùng cùng security identity theo yêu cầu của runtime và kiểm thử trên cluster mục tiêu.

### 2.2. Quyền thư mục và umask

Mode bits thường gặp:

| Mode | Ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| `0700` | Chỉ owner đọc, ghi, truy cập thư mục. | Thư mục checkpoint hoặc dữ liệu nhạy cảm của một user. |
| `0750` | Owner toàn quyền; group đọc/truy cập; others không có quyền. | Thư mục dữ liệu runtime cần chia sẻ trong một group. |
| `0770` | Owner và group đọc/ghi/truy cập. | Volume dùng chung giữa các process cùng group. |
| `1777` | Mọi user có thể tạo file; sticky bit hạn chế xóa file của người khác. | `/tmp` dùng chung. |

Với thư mục, quyền execute (`x`) có nghĩa được phép traverse/search qua thư mục. Một user có quyền đọc file nhưng không có quyền execute trên thư mục cha vẫn có thể không truy cập được file đó.

`umask` quyết định những permission bits bị loại bỏ khi tạo file/thư mục mới. Ví dụ `umask 027` thường tạo file mới tối đa với mode `0640` và thư mục mới tối đa `0750`, tùy mode mà chương trình yêu cầu. Nếu cần thiết lập umask, có thể dùng entrypoint script:

```sh
#!/bin/sh
set -eu
umask 027
exec java -Djava.io.tmpdir=/tmp -jar /opt/app/app.jar
```

Không dựa vào umask để sửa quyền của file đã tồn tại. Hãy kiểm tra ownership và mode của volume sau khi mount.

## 3. Bật `readOnlyRootFilesystem` trong Kubernetes

Kubernetes cho phép đặt `readOnlyRootFilesystem: true` trong container `securityContext`. Thiết lập này làm root filesystem của container chỉ đọc. Những volume được mount riêng vẫn có thể ghi nếu mount không đặt `readOnly: true` và loại volume hỗ trợ ghi.

Ví dụ Pod với JVM chạy non-root, root filesystem chỉ đọc và các volume ghi riêng:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-crac-app
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 20001
    fsGroupChangePolicy: OnRootMismatch
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: example/java-crac-app:1.0
      env:
        - name: JAVA_TOOL_OPTIONS
          value: "-Djava.io.tmpdir=/tmp"
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
      volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: app-state
          mountPath: /var/lib/myapp
        - name: app-cache
          mountPath: /var/cache/myapp
        - name: checkpoint-store
          mountPath: /var/lib/crac
  volumes:
    - name: tmp
      emptyDir: {}
    - name: app-state
      persistentVolumeClaim:
        claimName: java-app-state
    - name: app-cache
      emptyDir: {}
    - name: checkpoint-store
      persistentVolumeClaim:
        claimName: java-crac-checkpoints
```

Đây là skeleton minh họa cho quyền và mount. Nó chưa phải manifest CRaC hoàn chỉnh: checkpoint/restore còn cần cấu hình của JDK, CRIU, container runtime, kernel và cluster. Ví dụ cũng không cấp capability cho CRIU; các quyền cần thiết phụ thuộc cách nền tảng thực hiện checkpoint.

### 3.1. `runAsUser`, `runAsGroup` và `fsGroup`

| Trường | Vai trò |
|---|---|
| `runAsUser` | UID của tiến trình trong container. |
| `runAsGroup` | GID chính của tiến trình. |
| `fsGroup` | Group bổ sung được dùng cho quyền truy cập volume trong các trường hợp Kubernetes/volume driver hỗ trợ quản lý ownership. |
| `supplementalGroups` | Các group bổ sung khác mà tiến trình tham gia. |
| `runAsNonRoot` | Yêu cầu Kubernetes xác nhận container không chạy với UID 0. |
| `fsGroupChangePolicy` | Điều khiển khi Kubernetes thay đổi ownership/permission của volume, nếu volume type hỗ trợ. |

`fsGroup` không phải phép sửa quyền tổng quát cho mọi filesystem. Cách áp dụng phụ thuộc volume type và CSI driver; một số CSI driver tự xử lý group ownership hoặc dùng cơ chế mount group. `hostPath`, NFS với `root_squash` và một số storage backend có thể cần chuẩn bị quyền ở phía node/storage. Hãy xác nhận UID/GID và mode thực tế bằng một Pod kiểm tra chạy cùng security context.

### 3.2. Mount volume vẫn có thể ghi khi root filesystem chỉ đọc

`readOnlyRootFilesystem: true` áp dụng cho root filesystem của container. Một volume mount ghi được tại `/tmp` hoặc `/var/lib/myapp` vẫn có thể ghi nếu:

- Volume hỗ trợ thao tác ghi.
- `volumeMounts` không đặt `readOnly: true`.
- UID/GID của tiến trình có quyền theo mode/ACL.
- SELinux, AppArmor, seccomp và chính sách node không chặn thao tác.

Ngược lại, mount một volume với `readOnly: true` sẽ làm đường dẫn đó chỉ đọc dù user có quyền ghi trên filesystem gốc của volume.

## 4. Xác định thư mục nào cần ghi

Không nên mount toàn bộ root filesystem thành writable chỉ vì chưa biết ứng dụng ghi ở đâu. Hãy kiểm kê các đường dẫn runtime thực tế và chỉ mount các thư mục cần thiết.

| Đường dẫn thường gặp | Mục đích | Cách cấu hình gợi ý |
|---|---|---|
| `/tmp` | File tạm, native library extraction, thư viện tạo temporary file. | Mount `emptyDir`; đặt `-Djava.io.tmpdir=/tmp`. |
| `/var/tmp` | Temporary file cần tồn tại lâu hơn `/tmp` theo convention của một số ứng dụng. | Chỉ mount nếu ứng dụng hoặc thư viện thực sự dùng. |
| `/var/lib/myapp` | Dữ liệu runtime cần giữ qua lần restart. | PVC hoặc volume có persistence phù hợp. |
| `/var/cache/myapp` | Cache có thể tái tạo. | `emptyDir` nếu mất cache không ảnh hưởng tính đúng đắn; PVC nếu có lý do rõ ràng. |
| `/var/log/myapp` | Log file nếu không ghi stdout/stderr. | Volume log riêng; thường ưu tiên log ra stdout/stderr. |
| `/run` hoặc `/var/run` | PID file, socket nội bộ, runtime state. | `emptyDir` hoặc memory-backed volume nếu phù hợp. |
| `/var/lib/crac` | Checkpoint image/metadata nếu công cụ triển khai yêu cầu path trong container. | Volume ghi được với quyền hạn chế và storage phù hợp. |
| `$HOME` | Cache/config của một số thư viện và công cụ. | Đặt `HOME` tới thư mục có chủ đích hoặc mount riêng nếu cần ghi. |

Danh sách trên là điểm bắt đầu. Một ứng dụng có thể không cần tất cả thư mục này. Hãy dùng log lỗi, cấu hình thư viện, system call tracing trong môi trường thử nghiệm hoặc kiểm tra filesystem để xác định nơi ghi thật.

### 4.1. Cấu hình thư mục tạm cho JVM

JVM dùng system property `java.io.tmpdir` để xác định thư mục tạm mặc định cho một số API Java và thư viện. Có thể cấu hình ngay khi khởi chạy:

```bash
java -Djava.io.tmpdir=/tmp -jar application.jar
```

Một số thư viện native hoặc chương trình con có thể đọc biến môi trường `TMPDIR`, `TMP` hoặc `TEMP` thay vì `java.io.tmpdir`. Nếu cần, cấu hình chúng nhất quán:

```yaml
env:
  - name: TMPDIR
    value: /tmp
  - name: JAVA_TOOL_OPTIONS
    value: "-Djava.io.tmpdir=/tmp"
```

Hãy kiểm tra ứng dụng có tạo file tạm trong home hoặc working directory hay không. Chỉ đổi `java.io.tmpdir` không tự chuyển mọi thư viện sang `/tmp`.

### 4.2. Log nên đi đâu?

Trong Kubernetes, cách đơn giản thường là ghi log ra stdout/stderr để container runtime và hệ thống logging thu thập. Nếu dùng file appender, hãy mount thư mục log riêng và cấp quyền ghi cho UID/GID của ứng dụng.

Không nên ghi log vào `/opt/app`, `/` hoặc thư mục chứa JAR khi root filesystem chỉ đọc. Nếu log file cần tồn tại qua Pod recreation, dùng storage bền vững hoặc log shipping phù hợp; `emptyDir` không phải nơi lưu log lâu dài.

### 4.3. Home directory và cache của thư viện

Một số thư viện mặc định ghi vào `$HOME/.cache`, `$HOME/.config` hoặc thư mục user. Khi chạy non-root, home có thể là `/` hoặc một đường dẫn không tồn tại nếu image không cấu hình rõ.

Hãy xác định `HOME` của user runtime và đặt thư mục phù hợp. Ví dụ:

```yaml
env:
  - name: HOME
    value: /var/lib/myapp/home
  - name: XDG_CACHE_HOME
    value: /var/cache/myapp
```

Nếu thư viện cần ghi vào hai đường dẫn trên, mount volume và tạo thư mục với ownership/mode tương ứng. Không đặt `HOME=/root` cho một process non-root với hy vọng nó có thể truy cập thư mục đó.

## 5. Thư mục lưu checkpoint và vòng đời của volume

Checkpoint image có thể chứa trạng thái bộ nhớ của tiến trình, bao gồm dữ liệu nhạy cảm trong heap. Thư mục lưu checkpoint vì vậy vừa cần đủ dung lượng, vừa cần quyền truy cập chặt chẽ và vòng đời storage phù hợp.

### 5.1. Chọn loại volume theo mục tiêu restore

| Loại lưu trữ | Vòng đời thường gặp | Khi phù hợp |
|---|---|---|
| `emptyDir` | Tồn tại trong vòng đời Pod; mất khi Pod bị xóa. | Checkpoint và restore trong cùng Pod hoặc bài thử ngắn nếu runtime hỗ trợ. |
| PVC | Tồn tại độc lập với Pod theo reclaim policy và storage backend. | Cần giữ checkpoint qua việc tạo Pod mới hoặc điều phối restore sang Pod khác tương thích. |
| `hostPath` | Gắn với filesystem của node cụ thể. | Chỉ khi nền tảng quản lý node affinity, ownership và bảo mật rõ ràng. |
| Storage ngoài/container runtime | Do CRIU, runtime hoặc control plane quản lý. | Khi cơ chế checkpoint của nền tảng yêu cầu artifact ở ngoài container filesystem. |

`emptyDir` thường tồn tại khi container trong cùng Pod restart, nhưng bị xóa khi Pod bị xóa khỏi node. Do đó, không nên đặt checkpoint cần dùng cho một Pod mới vào `emptyDir` rồi kỳ vọng dữ liệu vẫn còn sau khi Pod bị thay thế.

PVC cũng không tự động bảo đảm có thể restore trên node khác. Cần xem access mode, topology, mount options, filesystem semantics và cách checkpoint engine sử dụng artifact. Nếu storage là node-local, Pod restore có thể cần được schedule đúng node.

### 5.2. Quyền của checkpoint directory

Nếu công cụ triển khai yêu cầu checkpoint directory bên trong container, hãy:

- Tạo directory trước khi ứng dụng chạy hoặc dùng volume mount tại đường dẫn đó.
- Cấp quyền ghi cho user/group mà checkpoint process thực sự sử dụng.
- Hạn chế quyền đọc vì image có thể chứa dữ liệu nhạy cảm.
- Đảm bảo đủ dung lượng và inode cho checkpoint image cùng file phụ trợ.
- Giữ mount path và cấu trúc directory tương thích giữa lúc tạo checkpoint và restore.
- Không để tiến trình khác ghi đè hoặc xóa file trong khi restore đang sử dụng.

Ví dụ permission chặt cho thư mục do một user sở hữu có thể là `0700`. Nếu công cụ checkpoint và restore chạy dưới group riêng, dùng group access phù hợp như `0750` hoặc `0770` theo đúng yêu cầu của nền tảng. Không mở `0777` để xử lý nhanh lỗi permission.

### 5.3. Checkpoint image là dữ liệu nhạy cảm

Heap có thể chứa password, token, session, dữ liệu cá nhân, nội dung request hoặc key material. Vì vậy, checkpoint directory cần được bảo vệ tương tự một artifact chứa dữ liệu runtime nhạy cảm:

- Chỉ cấp quyền cho service account và operator có trách nhiệm.
- Dùng encryption at rest nếu storage/platform yêu cầu.
- Không publish checkpoint image lên registry hoặc object store công khai.
- Xác định thời hạn giữ và quy trình xóa image cũ.
- Không ghi đường dẫn có chứa secret hoặc nội dung nhạy cảm vào log.
- Theo dõi quyền truy cập và thao tác copy/download checkpoint.

## 6. Quyền filesystem của CRIU và checkpoint runtime

Trong nhiều triển khai Linux, CRIU tham gia checkpoint/restore tiến trình. CRIU cần tương tác với kernel và các tài nguyên của tiến trình, nên có thể yêu cầu capability hoặc quyền đặc biệt tùy kernel, cấu hình và loại resource cần checkpoint.

Đây là điểm cần tách bạch:

- **Ứng dụng Java:** cần quyền tối thiểu để đọc JAR/config, ghi temp/cache/state và truy cập các dependency.
- **Checkpoint/restore tool:** có thể cần quyền bổ sung để dump/restore process, memory mapping, namespace, file descriptor và các resource khác.
- **Container runtime hoặc orchestrator:** có thể thực hiện một phần thao tác checkpoint bên ngoài container và quản lý artifact riêng.

Không nên mặc định rằng chỉ cần chạy Java bằng root là mọi checkpoint sẽ thành công. Ngược lại, `readOnlyRootFilesystem` và `drop: [ALL]` cũng không bảo đảm CRIU có đủ quyền. Yêu cầu cụ thể phụ thuộc CRIU version, Linux kernel, container runtime, seccomp profile, LSM và cách Kubernetes tích hợp chức năng checkpoint.

### 6.1. Capability và quyền đặc biệt

Một số môi trường có thể yêu cầu capability như `CAP_CHECKPOINT_RESTORE`, `CAP_SYS_ADMIN` hoặc quyền khác tùy thao tác và phiên bản kernel/CRIU. Không có một danh sách tối thiểu duy nhất đúng cho mọi triển khai.

Quy trình phù hợp:

1. Xác định checkpoint/restore được thực hiện bởi CRIU trong container, runtime bên ngoài hay node agent.
2. Đọc yêu cầu của đúng phiên bản CRIU, kernel và container runtime.
3. Cấp đúng capability cho đúng thành phần chịu trách nhiệm, theo chính sách cluster.
4. Giữ ứng dụng chạy non-root nếu không cần quyền nâng cao.
5. Kiểm thử cả checkpoint lẫn restore dưới cùng security context dự kiến.

Không thêm `privileged: true` hoặc `CAP_SYS_ADMIN` một cách mặc định chỉ để vượt qua lỗi. Nếu cluster không cho phép capability cần thiết, cần dùng cơ chế checkpoint được nền tảng hỗ trợ hoặc thay đổi chính sách qua người quản trị cluster.

### 6.2. Seccomp, AppArmor và SELinux

Quyền Unix truyền thống không phải yếu tố duy nhất. Một thao tác có thể bị chặn bởi:

- **seccomp:** lọc system call mà tiến trình được phép gọi.
- **AppArmor:** giới hạn file path, capability và hành vi tiến trình theo profile.
- **SELinux:** kiểm soát truy cập dựa trên label của process và file.
- **Mount options:** ví dụ `ro`, `noexec`, `nodev`, `nosuid` có thể ảnh hưởng tới cách thư viện sử dụng file hoặc executable mapping.

Nếu checkpoint hoặc restore báo permission denied, hãy xác định syscall/path bị chặn và chính sách nào từ chối. Đừng giải quyết bằng cách tắt toàn bộ bảo vệ bảo mật nếu chưa biết yêu cầu thực tế. Với SELinux, volume cần label phù hợp; với AppArmor/seccomp, profile phải cho phép các thao tác mà runtime cần.

## 7. Kubernetes volume permissions trong thực tế

Khi mount PVC hoặc `emptyDir`, file có thể thuộc owner/group khác với UID/GID của JVM. Pod `securityContext` có thể khai báo `fsGroup`, nhưng kết quả phụ thuộc volume plugin/CSI driver.

### 7.1. Kiểm tra quyền từ bên trong Pod

Một Pod debug dùng cùng `runAsUser`, `runAsGroup`, `fsGroup` và mount có thể kiểm tra:

```sh
id
umask
pwd
printf 'probe\n' > /tmp/write-test
printf 'probe\n' > /var/lib/myapp/write-test
printf 'probe\n' > /var/lib/crac/write-test
ls -ld /tmp /var/lib/myapp /var/lib/crac
ls -ln /var/lib/myapp /var/lib/crac
```

Các lệnh ghi chỉ là phép thử trong môi trường debug. Không chạy chúng trên thư mục checkpoint đang được runtime sử dụng. Hãy dùng file probe riêng và xóa sau khi kiểm tra.

`id` cho biết UID/GID và supplementary groups của process. `ls -ln` hiển thị ID số, hữu ích khi image và storage không có cùng `/etc/passwd` mapping.

### 7.2. Khi `fsGroup` không giải quyết được permission

Các nguyên nhân có thể gồm:

- Volume type không hỗ trợ Kubernetes đổi ownership.
- CSI driver tự quản lý mount group.
- NFS export dùng `root_squash` hoặc mapping user khác.
- `hostPath` được tạo với owner/mode không phù hợp trên node.
- ACL hoặc SELinux label từ storage chặn truy cập.
- File đã tồn tại có mode chỉ owner cũ được ghi.

Khi đó, cần phối hợp với người quản trị storage/cluster để đặt owner/group/mode hoặc cấu hình CSI phù hợp. Không giả định một init container chạy root có thể sửa mọi loại volume; nó cũng chịu security policy của cluster và có thể không được phép.

### 7.3. `fsGroupChangePolicy`

`fsGroupChangePolicy: OnRootMismatch` có thể giảm thời gian khởi động khi volume có nhiều file bằng cách tránh thay đổi ownership đệ quy nếu root directory đã có group/mode phù hợp. Trường này chỉ ảnh hưởng những volume mà Kubernetes thực hiện quản lý ownership; nếu CSI driver đảm nhiệm mount group, hành vi có thể khác.

Với checkpoint volume lớn, việc đổi ownership đệ quy có thể tốn thời gian và tạo tải I/O. Tốt hơn là chuẩn bị quyền đúng ngay khi provision volume hoặc dùng cơ chế storage phù hợp.

## 8. Giữ đường dẫn và mount nhất quán giữa checkpoint và restore

Checkpoint có thể giữ file descriptor và tham chiếu tới file hoặc mount. Nếu môi trường restore thay đổi mount namespace, đường dẫn hoặc filesystem backing, một số tài nguyên có thể không được khôi phục như mong đợi.

Hãy kiểm tra:

- Cùng đường dẫn mount cho thư mục cần thiết ở lần tạo checkpoint và lần restore.
- Cùng quyền đọc/ghi và ownership phù hợp.
- File cần tồn tại vẫn có mặt trên volume tương ứng.
- Filesystem hỗ trợ semantics mà ứng dụng hoặc checkpoint engine cần.
- Socket/file descriptor được xử lý theo Resource callback nếu peer hoặc file có thể thay đổi.
- Checkpoint image nằm ở storage còn tồn tại trong suốt quy trình restore.

Không nên coi việc mount một PVC cùng tên là đủ. PVC có thể được bind sang filesystem hoặc node khác, có mount option khác, hoặc có dữ liệu được provision với owner khác. Cần xác minh storage thực tế trước khi restore.

## 9. Ví dụ tách writable paths trong một Pod

Manifest sau minh họa cách tách các thư mục runtime. Trong ví dụ, ứng dụng ghi log ra stdout/stderr nên không cần volume log riêng. Checkpoint PVC chỉ là ví dụ nếu runtime yêu cầu một thư mục checkpoint bên trong container; hãy thay bằng cơ chế storage thực tế của nền tảng.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: crac-java
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 20001
    fsGroupChangePolicy: OnRootMismatch
  containers:
    - name: java
      image: example/java-crac-app:1.0
      env:
        - name: HOME
          value: /var/lib/myapp/home
        - name: TMPDIR
          value: /tmp
        - name: JAVA_TOOL_OPTIONS
          value: "-Djava.io.tmpdir=/tmp"
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: app-state
          mountPath: /var/lib/myapp
        - name: cache
          mountPath: /var/cache/myapp
        - name: checkpoints
          mountPath: /var/lib/crac
  volumes:
    - name: tmp
      emptyDir:
        sizeLimit: 256Mi
    - name: app-state
      persistentVolumeClaim:
        claimName: myapp-state
    - name: cache
      emptyDir:
        sizeLimit: 512Mi
    - name: checkpoints
      persistentVolumeClaim:
        claimName: myapp-checkpoints
```

Các điểm cần điều chỉnh trước khi dùng:

- `runAsUser`, `runAsGroup` và `fsGroup` phải khớp với owner/group mà storage cho phép.
- PVC cần được provision với access mode, topology và filesystem phù hợp với cách restore.
- `emptyDir.sizeLimit` là giới hạn ví dụ; cần dựa trên nhu cầu thật và quota ephemeral storage của Pod.
- `readOnlyRootFilesystem` chỉ phù hợp sau khi mọi đường dẫn ghi đã được xác định và mount.
- `drop: ["ALL"]` là baseline hạn chế quyền cho ứng dụng; nếu checkpoint runtime cần capability, cấp ở đúng thành phần theo thiết kế nền tảng thay vì bật privileged cho toàn container.
- `HOME` cần có thư mục tồn tại và ghi được trên volume `/var/lib/myapp`.

## 10. Checklist xử lý lỗi permission

Khi ứng dụng hoặc checkpoint engine báo `Permission denied`, hãy điều tra theo thứ tự:

1. Xác định chính xác process nào bị lỗi: JVM, CRIU, container runtime hay node agent.
2. Ghi lại syscall hoặc đường dẫn bị từ chối từ log phù hợp.
3. Kiểm tra UID/GID và supplementary groups của process thực tế.
4. Kiểm tra owner, mode và ACL của file cùng tất cả thư mục cha.
5. Xác nhận volume mount có phải read-only không.
6. Kiểm tra SELinux/AppArmor/seccomp và mount options.
7. Xác nhận capability cần thiết thuộc về ứng dụng hay checkpoint runtime.
8. Kiểm tra volume có tồn tại, writable và được mount tại cùng path ở restore hay không.
9. Kiểm tra quota, dung lượng và inode.
10. Thử bằng một Pod tối giản có cùng security context để khoanh vùng storage permission.

Không nên xử lý mọi lỗi bằng cách chạy container dưới root hoặc đặt `chmod -R 777`. Những cách này có thể che giấu nguyên nhân và mở rộng quyền ghi ngoài phạm vi cần thiết.

## 11. Những hiểu lầm thường gặp

**`readOnlyRootFilesystem: true` làm mọi volume chỉ đọc.** Không đúng. Volume mount riêng vẫn có thể ghi nếu không mount read-only và permission cho phép.

**Chỉ cần mount `/tmp` là ứng dụng CRaC hoạt động.** `/tmp` giải quyết một nhóm temporary files; ứng dụng còn có thể cần home, cache, state, log hoặc checkpoint storage.

**`fsGroup` luôn sửa được quyền PVC.** Không đúng. Hành vi phụ thuộc volume type, CSI driver, storage backend và chính sách node.

**Chạy Java bằng root sẽ giải quyết mọi lỗi CRaC.** Root không bảo đảm kernel, CRIU, seccomp, mount hoặc runtime tương thích; đồng thời làm tăng quyền của ứng dụng.

**Checkpoint directory có thể đặt trong `emptyDir` cho mọi trường hợp.** `emptyDir` mất khi Pod bị xóa. Nếu restore diễn ra trong Pod mới, cần storage tồn tại đủ lâu hoặc cơ chế artifact riêng của nền tảng.

**UID giống nhau là đủ để restore.** Còn phải kiểm tra GID, supplementary groups, capability, namespace, ACL, SELinux label và quyền của checkpoint engine.

**Checkpoint image chỉ chứa dữ liệu kỹ thuật, không nhạy cảm.** Heap có thể chứa token, session, dữ liệu cá nhân và key material. Cần bảo vệ image như dữ liệu nhạy cảm.

## 12. Checklist trước khi triển khai

- [ ] Chọn UID/GID non-root ổn định cho JVM.
- [ ] Bảo đảm JAR, classpath và cấu hình chỉ cần đọc khi chạy.
- [ ] Liệt kê mọi đường dẫn ứng dụng cần ghi.
- [ ] Đặt `java.io.tmpdir` và `TMPDIR` tới thư mục tạm ghi được.
- [ ] Chuyển log sang stdout/stderr hoặc mount log directory riêng.
- [ ] Đặt `HOME` và cache path rõ ràng nếu thư viện cần ghi.
- [ ] Bật `readOnlyRootFilesystem` sau khi các writable path đã được mount.
- [ ] Kiểm tra UID/GID, `fsGroup`, ACL và owner trên volume thực tế.
- [ ] Xác định checkpoint directory do ứng dụng, CRIU, runtime hay orchestrator quản lý.
- [ ] Dùng storage có vòng đời phù hợp với nơi và thời điểm restore.
- [ ] Bảo vệ checkpoint image bằng quyền hạn chế và chính sách lưu trữ.
- [ ] Xác định capability, seccomp, AppArmor và SELinux yêu cầu cho checkpoint runtime.
- [ ] Giữ security identity và mount layout tương thích giữa checkpoint và restore.
- [ ] Kiểm thử ghi file, tạo temp, checkpoint và restore bằng đúng security context dự kiến.
- [ ] Không cấp `privileged: true` hoặc quyền root rộng hơn yêu cầu đã xác minh.

## 13. Thuật ngữ cần nhớ

- **Non-root container:** container chạy tiến trình với UID khác 0.
- **`runAsUser` / `runAsGroup`:** UID và GID chính của tiến trình trong Pod.
- **`fsGroup`:** group bổ sung được Kubernetes dùng để hỗ trợ quyền truy cập volume khi volume driver hỗ trợ.
- **`readOnlyRootFilesystem`:** cấu hình làm root filesystem của container chỉ đọc.
- **Writable mount:** volume mount cho phép tiến trình ghi dữ liệu tại một đường dẫn cụ thể.
- **`emptyDir`:** volume tạm có vòng đời gắn với Pod.
- **PVC:** PersistentVolumeClaim yêu cầu storage có vòng đời độc lập với container/Pod theo cấu hình backend.
- **UID mapping:** ánh xạ user ID giữa namespace/container và host.
- **umask:** mặt nạ quyền bị loại bỏ khi tạo file hoặc thư mục mới.
- **Capability:** quyền Linux cấp hạt mịn cho một số thao tác đặc quyền.
- **seccomp:** cơ chế lọc system call.
- **SELinux/AppArmor:** cơ chế kiểm soát truy cập bổ sung cho process và filesystem.
- **Checkpoint image:** dữ liệu lưu trạng thái tiến trình để phục vụ restore.

Triển khai CRaC trong container an toàn cần kết hợp user không phải root, root filesystem chỉ đọc và các writable mount có mục đích. Hãy xác định riêng thư mục temp, cache, state, log và checkpoint; cấp UID/GID cùng group permission đúng cho từng volume; giữ storage và mount path tồn tại qua quy trình restore. Quyền đặc biệt mà CRIU hoặc container runtime cần phải được xác định theo môi trường cụ thể và cấp cho đúng thành phần, trong khi ứng dụng Java tiếp tục chạy với quyền tối thiểu.

## Tài liệu tham khảo

- [Kubernetes — Configure a Security Context for a Pod or Container](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/): `runAsUser`, `runAsGroup`, `fsGroup`, `fsGroupChangePolicy`, capabilities và `readOnlyRootFilesystem`.
- [Kubernetes — Volumes](https://kubernetes.io/docs/concepts/storage/volumes/): vòng đời và hành vi của `emptyDir`, volume mount và các loại storage.
- [Kubernetes — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/): PV/PVC, access modes và vòng đời storage.
- [CRIU — Documentation](https://criu.org/): yêu cầu checkpoint/restore tiến trình Linux và các tài nguyên hệ điều hành.
- [CRaC — About CRaC](https://crac.org/about/about-crac/): mô hình checkpoint/restore và yêu cầu phối hợp giữa ứng dụng với môi trường.
