# Build bị dừng do thiếu RAM, timeout hoặc giới hạn tài nguyên runner

## Mục tiêu bài học

Native Image build là một tác vụ nặng. Quá trình này chạy Native Image builder, thực hiện reachability analysis, tối ưu và biên dịch machine code, sau đó tạo executable. Với Spring Boot, build còn có bước Spring AOT để sinh mã và metadata trước khi native compilation bắt đầu.

Khi build dừng giữa chừng, thông báo “failed” hoặc log cuối cùng chưa đủ để xác định nguyên nhân. Có thể builder JVM hết heap, container bị kernel OOM kill, CI job hết thời gian, CPU bị throttling, ổ đĩa đầy hoặc runner bị giới hạn tài nguyên. Mỗi trường hợp cần bằng chứng khác nhau và cách xử lý khác nhau.

Sau bài học, bạn có thể:

- Phân biệt Java heap OOM của Native Image builder với container/host OOM kill.
- Đọc build log để xác định phase cuối cùng và thời điểm build dừng.
- Kiểm tra CPU quota, memory/cgroup, disk, inode và temporary directory.
- Điều chỉnh builder heap và mức song song có kiểm soát.
- Xử lý CI timeout, Docker resource limit và Kubernetes runner/job limit.
- Thiết kế quy trình retry, thu thập log và theo dõi build để tránh lặp lại lỗi.

## 1. Hiểu đúng tiến trình Native Image build

### 1.1. Builder JVM khác native executable được tạo ra

Khi chạy `native-image`, toolchain khởi chạy Native Image builder dựa trên Java. Builder JVM phân tích ứng dụng, tạo image heap và biên dịch các method reachable. Kết quả cuối cùng là native executable chạy độc lập với JVM.

Vì vậy, trong giai đoạn build có hai loại tài nguyên cần phân biệt:

- **Tài nguyên của builder:** Java heap của tiến trình build, native memory của builder, compiler threads, temporary files và các tiến trình compiler/linker.
- **Tài nguyên của ứng dụng native:** managed heap/runtime memory, thread stack, native allocations, shared libraries và dữ liệu ứng dụng khi executable chạy.

Một ứng dụng native có RSS nhỏ khi runtime không có nghĩa quá trình biên dịch nó cũng cần ít RAM. Builder có thể cần nhiều memory hơn đáng kể so với executable sau khi build xong.

### 1.2. Các bước có thể xuất hiện trong build log

Tên phase và cách hiển thị phụ thuộc GraalVM version, nhưng log thường thể hiện các công việc:

1. Khởi tạo builder và các feature.
2. Phân tích reachability, type, field, method và object graph.
3. Xử lý class initialization và metadata.
4. Tối ưu/inlining method.
5. Biên dịch method thành machine code.
6. Bố trí code và tạo image.
7. Link và ghi executable cùng các artifact bổ sung.

Nếu build dừng ở Analysis, cần xem graph và memory của builder. Nếu dừng ở Compiling Methods, cần xem số method, CPU, compiler threads và thời gian. Nếu dừng ở Creating Image hoặc linker, kiểm tra memory, disk, temporary directory và toolchain native.

### 1.3. Một lần build có nhiều lớp giới hạn

| Lớp | Giới hạn có thể áp dụng |
|---|---|
| Native Image builder JVM | `-J-Xmx`, JVM options và số compiler threads |
| Docker/container | CPU quota, memory limit, PID limit, ephemeral storage |
| Kubernetes | requests/limits, node allocatable, ephemeral storage, pod eviction |
| CI runner | RAM/CPU thực tế, thời gian job, disk quota, concurrency |
| Host/VM | Host OOM, swap policy, filesystem, inode và contention |

Build chỉ thành công khi tất cả các lớp đều đủ tài nguyên trong toàn bộ thời gian chạy.

## 2. Phân loại lỗi trước khi thay đổi cấu hình

### 2.1. Dấu hiệu thường gặp

| Dấu hiệu | Nguyên nhân có thể | Bằng chứng cần tìm |
|---|---|---|
| `OutOfMemoryError: Java heap space` | Heap của builder JVM không đủ | Builder JVM log, heap dump nếu có, cấu hình `-J-Xmx` |
| Container exit code 137 hoặc `OOMKilled` | Kernel kill do vượt memory limit hoặc SIGKILL từ bên ngoài | Container state, cgroup memory events, host/kernel log |
| CI job bị cancel sau một khoảng thời gian cố định | Job timeout hoặc workflow timeout | CI job summary, timeout configuration, timestamp |
| Build chậm dần, CPU thấp hoặc throttling cao | CPU quota thấp, host contention hoặc build chờ I/O | CPU usage, throttled periods, process state, disk metrics |
| `No space left on device` | Hết dung lượng hoặc inode | `df -h`, `df -i`, temp/workspace size |
| Build dừng khi tạo image/link | Temporary storage, linker hoặc native toolchain | Log cuối, disk space, linker output và exit code |
| Process biến mất không có stack trace | Runner/host kill, timeout hoặc OOM kill | CI event, container status, kernel event |

Không kết luận OOM chỉ từ exit code 137. Mã này thường tương ứng SIGKILL, có thể do OOM nhưng cũng có thể do timeout controller hoặc thao tác kill bên ngoài.

### 2.2. Thu thập bằng chứng trước khi retry

Trước khi chạy lại, lưu:

- Toàn bộ stdout/stderr của native build và Spring AOT.
- Exit code của lệnh build và container/job.
- Timestamp bắt đầu, phase cuối cùng và thời điểm dừng.
- GraalVM/JDK version, OS, architecture và build arguments.
- CPU, memory limit/request và số CPU khả dụng.
- Disk usage, inode và temporary directory.
- CI job summary hoặc Kubernetes termination reason.

Retry ngay mà không lưu thông tin có thể làm mất bằng chứng về OOM event, timeout hoặc trạng thái runner.

### 2.3. Xác định build process còn chạy hay đã bị kill

Trong Linux runner, có thể quan sát:

```bash
ps -eo pid,ppid,stat,%cpu,%mem,rss,etime,args \
  | grep -E 'native-image|Native Image|java'
```

Nếu process vẫn tồn tại, xem CPU, RSS, elapsed time và trạng thái process. Nếu process đã biến mất, đối chiếu exit code và sự kiện của container/runner. Không chỉ dựa vào việc log không có dòng mới để kết luận process bị treo.

## 3. Chẩn đoán builder JVM hết heap

### 3.1. Nhận diện Java heap OOM

Thông báo như:

```text
java.lang.OutOfMemoryError: Java heap space
java.lang.OutOfMemoryError: GC overhead limit exceeded
```

cho thấy builder JVM không có đủ Java heap hoặc dành quá nhiều thời gian thu gom rác. Đây là lỗi khác với kernel OOM kill toàn bộ container.

Nếu có `Java heap space`, builder JVM thường có thể ghi stack trace và dừng với lỗi rõ ràng. Tuy nhiên, nếu container bị kernel kill trước khi JVM ghi log, bạn có thể không thấy `OutOfMemoryError`.

### 3.2. Tăng heap cho builder bằng `-J-Xmx`

`-J-` chuyển JVM option tới Java process chạy Native Image builder. Ví dụ:

```bash
native-image \
  -J-Xmx6g \
  -jar target/payment-service.jar
```

`-J-Xmx6g` đặt maximum Java heap của builder JVM khoảng 6 GiB. Nó không đặt heap cap cho native executable được tạo ra.

Chọn giá trị dựa trên memory khả dụng của runner. Nếu container có memory limit 8 GiB, đặt builder heap 8 GiB sẽ không để lại đủ headroom cho:

- Metaspace, code cache và thread stack của builder JVM.
- Native allocations của Graal compiler.
- C compiler/linker và subprocess.
- File cache, memory mapping và hệ điều hành.

Hãy bắt đầu với heap vừa đủ, đo peak container memory và tăng từng bước. Không đặt heap vượt giới hạn cgroup.

### 3.3. Phân biệt `-J-Xmx` với `-Xmx`

| Tùy chọn | Áp dụng cho |
|---|---|
| `-J-Xmx6g` | JVM chạy Native Image builder |
| `-Xmx` khi chạy `java -jar app.jar` | JVM chạy ứng dụng thông thường |
| Native Image runtime heap options | Managed heap của native executable, theo hỗ trợ của GraalVM version |

Đặt `-Xmx` đơn lẻ vào native-image command không phải cách thay thế cho `-J-Xmx`. Kiểm tra `native-image --help` và tài liệu đúng version để xác nhận option được hỗ trợ.

### 3.4. Thu thập heap dump khi cần

Khi builder JVM có thể ghi dump trước khi hết heap, có thể thêm JVM option:

```bash
native-image \
  -J-Xmx6g \
  -J-XX:+HeapDumpOnOutOfMemoryError \
  -J-XX:HeapDumpPath=build/diagnostics \
  -jar target/payment-service.jar
```

Heap dump có thể lớn và chứa dữ liệu từ build process. Bảo đảm thư mục có đủ dung lượng, giới hạn quyền truy cập và không upload dump vào artifact công khai. Không phải mọi trường hợp OOM đều tạo được dump; kernel SIGKILL có thể xảy ra trước.

## 4. Khi container hoặc runner bị OOM kill

### 4.1. Kiểm tra memory limit thực tế

Trên Linux, kiểm tra:

```bash
free -h
cat /proc/meminfo
```

Trong cgroup v2, các file thường dùng gồm:

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
```

`memory.current` cho biết mức memory hiện tại; `memory.max` là giới hạn (hoặc `max` nếu không có giới hạn cứng); `memory.events` ghi nhận các sự kiện như `oom` và `oom_kill`.

Đường dẫn và tên file khác nhau trên cgroup v1 hoặc khi process nằm trong cgroup con. Hãy đọc `/proc/self/cgroup` và mount information để xác định đúng cgroup của builder.

### 4.2. Đối chiếu container memory với builder heap

Ví dụ:

| Số liệu | Giá trị minh họa |
|---|---:|
| Container memory limit | 8 GiB |
| Builder JVM max heap | 6 GiB |
| Metaspace, thread stack, code cache | 700 MiB |
| Compiler/linker/native memory và overhead | 1.5 GiB |

Tổng có thể vượt 8 GiB dù Java heap chưa chạm `-Xmx`. Đây là lý do phải đo cgroup memory/peak thay vì chỉ theo dõi Java heap.

Các con số trên chỉ minh họa cách cộng ngân sách; thành phần và mức sử dụng thực tế thay đổi theo ứng dụng, toolchain và runner.

### 4.3. Xác định OOM từ Kubernetes

Kiểm tra pod và container state:

```bash
kubectl describe pod <pod-name>
kubectl get pod <pod-name> -o wide
kubectl get events --sort-by=.lastTimestamp
```

Tìm:

- `Reason: OOMKilled`.
- Exit code 137.
- Container restart count.
- Node memory pressure và eviction events.
- Job/pod resource limits.

Nếu pod bị `OOMKilled`, tăng builder heap không phải giải pháp đầu tiên. Cần tăng memory limit/runner capacity hoặc giảm peak memory của build.

### 4.4. Xác định host OOM

Nếu build chạy trực tiếp trên VM/runner, kiểm tra kernel log nếu quyền cho phép:

```bash
dmesg -T | grep -i -E 'out of memory|killed process'
```

Trên hệ thống dùng systemd, có thể xem kernel journal hoặc system journal theo quyền của runner. Nếu host OOM killer chọn builder JVM hoặc linker process, log CI có thể chỉ ghi process exit bất thường.

## 5. CPU quota và mức song song của compiler

### 5.1. Build bị chậm vì CPU throttling

Native compilation có thể sử dụng nhiều core. Nếu runner chỉ cấp một phần CPU, build có thể kéo dài đáng kể dù không thiếu memory.

Kiểm tra:

- CPU quota/cpuset của container.
- CPU usage và throttled periods.
- Số compiler threads.
- CPU contention từ các job khác.
- Thời gian của từng build phase.

Đừng tăng timeout ngay nếu build đang bị throttling liên tục. Trước tiên xác định runner có đủ CPU hoặc có thể giảm mức song song hay không.

### 5.2. Giảm parallelism để giảm peak memory

Một số GraalVM version cung cấp tùy chọn `--parallelism` để giới hạn số thao tác song song trong quá trình build. Ví dụ nếu phiên bản hiện tại hỗ trợ:

```bash
native-image \
  --parallelism=4 \
  -J-Xmx6g \
  -jar target/payment-service.jar
```

Giảm parallelism có thể giảm số tác vụ compiler/analysis chạy đồng thời và hạ peak resource usage, nhưng thường kéo dài thời gian build. Tên option và phạm vi tác động phụ thuộc GraalVM version; xác nhận bằng `native-image --help` trước khi dùng.

Không chọn số thread chỉ dựa trên số core vật lý. Runner có CPU quota, memory limit và mức contention riêng. Benchmark các mức song song khác nhau trong cùng giới hạn tài nguyên.

### 5.3. Phân biệt CPU-bound và memory-bound

| Dấu hiệu | Khả năng | Thử nghiệm xác nhận |
|---|---|---|
| CPU cao, memory còn headroom, compile phase dài | CPU-bound | Tăng CPU quota hoặc dùng runner mạnh hơn |
| RSS gần limit, GC nhiều, OOM | Memory-bound | Tăng memory/headroom hoặc giảm parallelism |
| CPU thấp, RSS thấp, elapsed time cao | I/O wait hoặc process đang chờ | Kiểm tra disk, temp directory, linker và process state |
| CPU throttled cao | CPU quota-bound | Tăng quota trong một lần đo có kiểm soát |

## 6. Chẩn đoán CI timeout

### 6.1. Phân biệt timeout của job và timeout của lệnh

CI có thể kết thúc build vì:

- Workflow/job có giới hạn thời gian tổng.
- Step hoặc command wrapper có timeout riêng.
- Runner bị thu hồi hoặc mất kết nối.
- Người dùng hoặc automation cancel job.

Nếu log kết thúc ở một timestamp cố định, kiểm tra timeout cấu hình trước khi điều chỉnh GraalVM memory.

### 6.2. So sánh thời gian build với timeout

Lưu thời gian cho các bước:

- Resolve dependency.
- Compile và package JVM artifact.
- Spring AOT processing.
- Native Image analysis.
- Native compilation.
- Linking và packaging container.

Nếu chỉ native compilation chiếm phần lớn thời gian, đặt timeout cho job dựa trên phân bố thời gian thực tế và mức dao động của runner. Nếu dependency resolution hoặc image pull chiếm nhiều thời gian, tăng timeout native build không giải quyết đúng nút thắt.

### 6.3. Tăng timeout có căn cứ

Trước khi tăng timeout:

1. Xác nhận build còn tiến triển qua log/CPU/memory.
2. Xác định phase đang chạy và thời gian phase đó.
3. Loại trừ OOM, disk full và CPU throttling.
4. So sánh với thời gian build thành công trên runner tương đương.
5. Đặt timeout có headroom hợp lý và alert nếu vượt baseline.

Timeout dài hơn chỉ cho phép công việc tiếp tục lâu hơn; nó không tự làm build nhanh hơn.

### 6.4. Tránh retry vô hạn

Retry có thể hữu ích với runner bị gián đoạn tạm thời, nhưng không khắc phục một cấu hình thiếu RAM hoặc một dependency graph quá lớn. Giới hạn số lần retry, lưu log mỗi lần và phân biệt lỗi transient với lỗi deterministic.

Nếu cùng source/toolchain luôn dừng ở cùng phase và cùng memory usage, hãy điều tra build input/resource thay vì lặp lại job không giới hạn.

## 7. Kiểm tra disk, inode và temporary directory

### 7.1. Native build dùng temporary storage

Native Image builder và compiler/linker có thể tạo nhiều file trung gian. Workspace và temp directory cần đủ dung lượng cho:

- Extracted dependencies và build artifacts.
- Generated Spring AOT sources/classes.
- Native Image intermediate files.
- Object files, linker outputs và debug information.
- Heap dump hoặc log chẩn đoán nếu được bật.

`No space left on device` có thể xuất hiện khi filesystem hết dung lượng hoặc hết inode. Hai trường hợp cần kiểm tra riêng.

### 7.2. Kiểm tra dung lượng và inode

```bash
df -h
df -i
du -sh "$PWD" "${TMPDIR:-/tmp}"
```

Kiểm tra filesystem của workspace và temp directory thực tế. Trong container, temp có thể nằm trên ephemeral storage hoặc filesystem có quota riêng.

Không xóa file trung gian khi builder vẫn đang chạy. Sau khi job kết thúc, chỉ dọn các thư mục build tạm thuộc đúng job/workspace.

### 7.3. Chọn temporary directory có đủ chỗ

Nếu `/tmp` nhỏ hoặc nằm trên filesystem có quota thấp, có thể đặt `TMPDIR` tới mount phù hợp trước khi chạy build:

```bash
mkdir -p "$PWD/build/native-tmp"
export TMPDIR="$PWD/build/native-tmp"
native-image -J-Xmx6g -jar target/payment-service.jar
```

Đảm bảo thư mục tồn tại, có quyền ghi và nằm trên volume có đủ dung lượng. Dùng cùng loại storage khi benchmark build time; filesystem chậm có thể làm linking/temporary file operations kéo dài.

## 8. Cấu hình build qua Maven, Gradle và buildpacks

### 8.1. Gradle Native Build Tools

Ví dụ cấu hình build arguments:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add("-J-Xmx6g")
            buildArgs.add("--parallelism=4")
        }
    }
}
```

Kiểm tra phiên bản Gradle plugin và GraalVM có hỗ trợ các arguments này. Đặt giá trị theo memory/CPU thực tế của runner. Không tăng heap lên sát memory limit chỉ vì build chạy trong container.

### 8.2. Maven Native Build Tools

Ví dụ:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-J-Xmx6g</buildArg>
            <buildArg>--parallelism=4</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

Đây là cấu hình minh họa cho `native-maven-plugin`. Nếu dự án dùng Spring Boot Maven plugin hoặc một execution/profile riêng, truyền build arguments vào đúng execution thực hiện Native Image compilation.

### 8.3. Build bằng Cloud Native Buildpacks

Khi dùng `spring-boot:build-image` hoặc `bootBuildImage`, Native Image có thể chạy bên trong builder container do buildpack điều khiển. Khi đó cần kiểm tra:

- Resource limit của builder container.
- Memory/CPU mà Docker daemon hoặc CI runner cấp cho builder.
- Environment variables và build arguments mà buildpack nhận.
- Timeout của step tạo image và timeout của CI job.
- Disk/ephemeral storage của Docker daemon.

Đừng giả định `-J-Xmx` đặt trong cấu hình native plugin sẽ tự động áp dụng cho buildpack. Cách truyền arguments và cấp tài nguyên phụ thuộc builder/buildpack version; xác nhận bằng log buildpack và tài liệu đúng phiên bản.

### 8.4. Ghi lại cấu hình thực sự được sử dụng

Lưu các giá trị:

- GraalVM/JDK version.
- Native Build Tools plugin version.
- Builder image và buildpack version nếu có.
- Native Image arguments cuối cùng.
- CPU/memory/disk limits của runner và builder container.
- CI timeout và concurrency.

Không chỉ lưu file cấu hình trong repository; log cần cho biết profile/task nào đã chạy và arguments nào thực sự được truyền.

## 9. Thu thập log và số liệu để tìm phase gây nghẽn

### 9.1. Giữ build output đầy đủ

Trong CI, lưu stdout/stderr đầy đủ và timestamp. Không chỉ lưu vài dòng cuối vì lỗi có thể xuất hiện trước khi runner bị kill.

Có thể xuất machine-readable build output nếu GraalVM version hỗ trợ:

```bash
native-image \
  -H:BuildOutputJSONFile=build/native/native-build-output.json \
  -J-Xmx6g \
  -jar target/payment-service.jar
```

JSON có thể hỗ trợ theo dõi thời gian, resource usage và số liệu analysis tùy schema version. Xác nhận file thực sự được tạo sau build và lưu schema/toolchain version cùng nó.

### 9.2. Dùng Build Report khi toolchain hỗ trợ

Nếu GraalVM distribution hỗ trợ HTML Build Report, có thể thêm `--emit build-report` để phân tích Code Area, Image Heap, Resources và SBOM.

Build Report giúp tìm thành phần làm image lớn hoặc graph reachable rộng. Nó không thay thế số liệu CPU/memory của runner và không giải thích trực tiếp CI timeout. Nếu report không được tạo, kiểm tra edition/version và dùng build output có sẵn.

### 9.3. Theo dõi theo từng phase

Tạo bảng cho mỗi build:

| Phase | Duration | CPU | Peak memory | Ghi chú |
|---|---:|---:|---:|---|
| Spring AOT | ... | ... | ... | Generated sources |
| Analysis | ... | ... | ... | Reachability graph |
| Compilation | ... | ... | ... | Compiler threads |
| Image creation/linking | ... | ... | ... | Disk/temp/linker |
| Packaging | ... | ... | ... | Container/image layer |

Điền số liệu thực tế từ log và monitoring. Không suy ra duration của phase nếu toolchain không cung cấp mốc đo.

## 10. Quy trình khắc phục theo từng triệu chứng

### 10.1. Builder JVM báo Java heap OOM

1. Lưu stack trace và heap dump nếu tạo được.
2. Kiểm tra `-J-Xmx` hiện tại.
3. Đo container/host memory và xác nhận còn headroom.
4. Tăng builder heap từng bước, không vượt cgroup limit.
5. Nếu peak memory vẫn cao, giảm parallelism nếu version hỗ trợ.
6. Kiểm tra dependency/reachability và class initialization.
7. Build lại và so sánh peak RSS, thời gian và phase.

### 10.2. Container bị OOMKilled

1. Xác nhận `OOMKilled` và cgroup `oom_kill` event.
2. Kiểm tra memory limit và peak container memory.
3. So sánh builder heap với phần memory ngoài heap.
4. Tăng memory của runner/builder nếu capacity cho phép.
5. Giảm parallelism hoặc chia tải CI để giảm contention.
6. Không chỉ tăng `-J-Xmx`, vì heap lớn hơn có thể làm tổng memory vượt limit sớm hơn.

### 10.3. CI job timeout nhưng process không OOM

1. Xác nhận job timeout/cancel reason.
2. Xem phase cuối và tiến độ log.
3. Kiểm tra CPU throttling, disk I/O và runner contention.
4. Dùng runner phù hợp hoặc giảm concurrency của các job song song.
5. Tối ưu dependency/metadata nếu phase analysis tăng.
6. Điều chỉnh timeout theo thời gian build đo được và headroom.

### 10.4. Build chậm khi CPU thấp

1. Kiểm tra quota và throttled periods.
2. Xác định builder có đang chờ I/O hoặc memory không.
3. Thử runner có CPU quota cao hơn.
4. So sánh thời gian với cùng memory và parallelism.
5. Chỉ tăng parallelism khi CPU và memory còn đủ.

### 10.5. Disk full hoặc lỗi linker

1. Lưu log linker và exit code.
2. Kiểm tra `df -h`, `df -i`, workspace và temp mount.
3. Xác định output/intermediate nào đang chiếm dung lượng.
4. Cấp ephemeral storage hoặc volume phù hợp.
5. Đặt temp directory có đủ chỗ.
6. Dọn workspace sau khi job kết thúc và giữ artifacts cần chẩn đoán.

## 11. Thiết kế CI runner ổn định

### 11.1. Tránh quá nhiều native build đồng thời

Native compilation có thể tiêu thụ nhiều CPU và RAM. Nếu một runner chạy nhiều native builds cùng lúc, mỗi build có thể chậm hơn và tổng memory có thể vượt giới hạn.

Đặt concurrency phù hợp với tổng RAM/CPU của runner. Có thể dùng queue riêng cho native builds, runner lớn hơn hoặc giới hạn số job native chạy đồng thời.

### 11.2. Tách dependency cache khỏi build workspace

Cache Maven/Gradle giúp giảm thời gian tải dependency, nhưng không làm giảm trực tiếp memory cần cho reachability analysis hoặc compilation. Đảm bảo cache không chiếm hết disk của workspace/temp.

Không chia sẻ cùng thư mục output/intermediate giữa hai native builds đồng thời nếu plugin/task không hỗ trợ. Mỗi job cần workspace riêng.

### 11.3. Giữ artifacts chẩn đoán có kiểm soát

Có thể lưu:

- Native build log.
- JSON build output.
- HTML Build Report nếu có.
- GraalVM/plugin/builder versions.
- Exit code và CI metadata.
- Heap dump chỉ khi cần điều tra, với quyền truy cập hạn chế.

Đặt retention phù hợp vì heap dump, debug files và report có thể lớn hoặc chứa thông tin nhạy cảm.

## 12. Ví dụ checklist trước khi retry

| Câu hỏi | Kết quả cần ghi |
|---|---|
| Build dừng ở phase nào? | Tên phase và timestamp |
| Có `OutOfMemoryError` không? | Có/không, stack trace |
| Container có `OOMKilled` không? | State, exit reason, cgroup events |
| Builder heap hiện tại? | `-J-Xmx` |
| Container memory limit? | Giới hạn và peak usage |
| CPU quota/throttling? | CPU limit, throttled periods |
| Disk/inode còn đủ? | `df -h`, `df -i` |
| Temp directory ở đâu? | Đường dẫn, filesystem và dung lượng |
| CI job bị timeout/cancel? | Job timeout, timestamp và reason |
| Có nhiều native builds đồng thời? | Runner concurrency |
| GraalVM và plugin version? | Version đầy đủ |
| Build arguments thực tế? | Log/config sau khi resolve profile |

### Câu hỏi tự kiểm tra

1. Vì sao memory của native executable khi runtime không dự đoán được memory cần cho builder JVM?
2. `-J-Xmx` khác `-Xmx` như thế nào?
3. Vì sao container có thể bị OOM kill dù builder JVM chưa đạt maximum heap?
4. Exit code 137 có đủ để kết luận OOM không?
5. Khi nào giảm `--parallelism` có thể giúp build ổn định hơn?
6. Vì sao tăng CI timeout không giải quyết được CPU throttling hoặc disk full?
7. Buildpacks và Native Build Tools có cùng cách nhận build arguments không?
8. Vì sao cần lưu build log, cgroup events và CI termination reason trước khi retry?

**Ghi nhớ:** xác định đúng lớp giới hạn trước khi thay đổi cấu hình. `-J-Xmx` điều chỉnh heap của builder JVM; container memory phải bao gồm cả native memory, thread stack và compiler/linker; parallelism ảnh hưởng trade-off giữa thời gian và peak resource; timeout chỉ kiểm soát thời lượng job. Thu thập log, exit reason, cgroup, CPU, disk và phase timing trước khi retry để chọn biện pháp phù hợp.
