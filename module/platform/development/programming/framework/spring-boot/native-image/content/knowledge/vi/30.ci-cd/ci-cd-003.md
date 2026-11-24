# Thiết kế runner đủ RAM, CPU và dung lượng cho native compilation

## 1. Vì sao native compilation cần runner riêng?

Biên dịch Spring Boot thành GraalVM Native Image là một công việc build nặng. Native Image builder chạy trên một JVM riêng, phân tích reachability của ứng dụng, tạo representation cho các class/method cần thiết, tối ưu mã và gọi native compiler/linker để tạo executable. Quá trình này có thể dùng nhiều RAM, CPU và dung lượng tạm hơn đáng kể so với `mvn test` hoặc `gradle test` thông thường.

Một runner thiếu tài nguyên có thể gặp các biểu hiện khác nhau:

- `OutOfMemoryError: Java heap space` khi heap của Native Image builder đạt giới hạn.
- Tiến trình bị kernel/container OOM-kill dù log không có Java exception.
- Build kéo dài do CPU bị giới hạn hoặc nhiều job cùng tranh tài nguyên.
- Hết dung lượng trong workspace, thư mục tạm, Maven/Gradle cache hoặc Docker layer.
- Build lúc thành công lúc thất bại vì tải song song và mức sử dụng tài nguyên thay đổi.

Thiết kế runner tốt cần nhìn đồng thời **RAM, CPU, disk, giới hạn container và số native build chạy đồng thời**. Không thể chọn runner chỉ dựa trên số core hoặc chỉ dựa trên heap được cấp cho Native Image builder.

Sau bài học, bạn có thể:

- Đọc peak RSS và phân biệt nó với Java heap của builder.
- Chọn RAM theo số đo của ứng dụng, có phần dự phòng cho OS, Maven/Gradle và linker.
- Điều chỉnh `--parallelism`, `-J-Xmx` và số native build chạy đồng thời.
- Tính dung lượng cần cho source, cache, output, temp files và container layers.
- Chọn GitHub-hosted runner hoặc self-hosted runner phù hợp.
- Cấu hình Maven/Gradle, Docker và CI để build ổn định, có thể tái lập.

## 2. Hiểu tài nguyên mà Native Image builder sử dụng

### 2.1. Builder chạy trên JVM, executable được tạo là native

Trong bước build, lệnh `native-image` chạy trên một JVM. JVM này thực hiện phân tích và điều phối quá trình biên dịch. Sau đó GraalVM gọi native toolchain như C compiler và linker để tạo executable cho OS/CPU mục tiêu.

Do đó cần phân biệt hai giai đoạn:

| Giai đoạn | Tài nguyên chính |
|---|---|
| Native Image builder | Java heap, metaspace, thread stacks, dữ liệu phân tích và các cấu trúc native của builder |
| Native compiler/linker | RAM, CPU và file tạm khi biên dịch/link object files |
| Maven/Gradle và các plugin | JVM build tool, daemon, test process, dependency resolution |
| CI host/container | OS, Docker daemon, logging, cache, agent và các tiến trình nền |

`-J-Xmx` chỉ đặt giới hạn heap cho JVM chạy Native Image builder. Nó không giới hạn tổng RSS của builder, native compiler, linker, Maven/Gradle hoặc toàn runner.

### 2.2. Heap không bằng RSS

Ví dụ builder được cấu hình `-J-Xmx8g` không có nghĩa toàn bộ build chỉ dùng tối đa 8 GB RAM. RSS còn bao gồm:

- Heap đã commit của builder.
- Metaspace, code cache, thread stacks và native memory của JVM.
- Native compiler/linker và các tiến trình con.
- Maven/Gradle daemon, test JVM và các tiến trình plugin.
- OS page cache, Docker daemon và dịch vụ của runner.

Vì vậy, khi chọn runner hãy ưu tiên **peak RSS của toàn job** hoặc memory peak của cgroup/container. Dùng heap limit như một nút điều khiển, không dùng nó thay cho số đo tổng bộ nhớ.

### 2.3. Hành vi mặc định theo môi trường CI

Native Image có thể tự xác định lượng bộ nhớ và số thread dựa trên tài nguyên hệ thống. Tài liệu GraalVM hiện hành mô tả chế độ dedicated cho container/CI (thường nhận diện qua biến `CI=true`): builder có thể dùng đến khoảng 85% RAM khả dụng làm giới hạn heap, có giới hạn tối đa theo phiên bản GraalVM. Mức sử dụng thực tế có thể cao hơn heap limit vì các phần native memory và tiến trình con.

Mặc định Native Image sử dụng nhiều processor để rút ngắn thời gian build, nhưng số thread được giới hạn tối đa 32. Có thể giảm số thread bằng `--parallelism` để giảm tải CPU và mức dùng RAM, đổi lại build lâu hơn.

Các mặc định và giới hạn thay đổi theo GraalVM version. Hãy kiểm tra phần Build Resources trong tài liệu đúng version mà runner cài đặt, và đọc phần build output để xem peak RSS thực tế. Tài liệu [Native Image Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/) mô tả cách builder chọn heap và parallelism trong CI.

## 3. Chọn RAM từ số đo, không đoán theo kích thước JAR

### 3.1. Các yếu tố làm peak memory tăng

Peak memory thường tăng khi:

- Application có nhiều class reachable, dependency lớn hoặc nhiều cấu hình framework.
- Reflection, proxy, serialization và resource metadata làm tăng phạm vi phân tích.
- Dùng `-H:Preserve=all`, PGO instrumentation hoặc các tùy chọn yêu cầu lưu thêm thông tin.
- Số thread biên dịch tăng.
- Nhiều native image được build song song trong cùng runner/container.
- Maven/Gradle daemon, test JVM hoặc Docker build chạy cùng thời điểm.

Dung lượng JAR không dự đoán chính xác peak RAM. Hai JAR có kích thước gần nhau có thể có call graph, số class reachable và độ phức tạp phân tích rất khác nhau.

### 3.2. Quy trình đo baseline

1. Chọn một runner sạch, pin GraalVM/JDK, Maven hoặc Gradle và native toolchain.
2. Build đúng profile production, đúng metadata và đúng container target.
3. Ghi peak RSS, heap limit, CPU time, wall-clock time và dung lượng disk cao nhất.
4. Lặp lại build ít nhất vài lần để nhận biết dao động do cache hoặc concurrency.
5. Chạy thêm một lần trong điều kiện CI thực tế, có container/cgroup limit giống pipeline.

Trên Linux có thể dùng `/usr/bin/time -v` để lấy `Maximum resident set size`:

```bash
/usr/bin/time -v ./mvnw -Pnative -DskipTests package
```

Hoặc với Gradle:

```bash
/usr/bin/time -v ./gradlew nativeCompile
```

`time -v` cung cấp số đo RSS cho lệnh được bọc, hữu ích để so sánh cùng một lệnh giữa các lần build. Số này có thể không phản ánh chính xác peak của toàn bộ cây tiến trình chạy đồng thời; dùng `memory.peak` của cgroup hoặc telemetry cấp job để lập kế hoạch RAM runner.

### 3.3. Đo memory peak trong Linux cgroup

Trên Linux dùng cgroup v2, có thể đọc các file sau nếu runner/container cho phép:

```bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.events
```

- `memory.max`: giới hạn cứng của cgroup; giá trị `max` nghĩa là không có hard limit tại cgroup đó.
- `memory.current`: lượng bộ nhớ đang dùng tại thời điểm đọc.
- `memory.peak`: mức sử dụng cao nhất kể từ khi cgroup được tạo.
- `memory.events`: bộ đếm sự kiện như `oom` và `oom_kill`.

Nếu runner dùng cgroup v1 hoặc cấu trúc cgroup lồng nhau, đường dẫn file sẽ khác. Dùng telemetry của nền tảng CI khi không đọc được các file này.

### 3.4. Tính RAM runner có dự phòng

Lấy peak RSS cao nhất từ một build đại diện, sau đó cộng phần dự phòng cho dao động, OS, agent và tiến trình build khác. Một quy tắc khởi đầu có thể là:

\[
RAM_{runner} \ge PeakRSS_{job} + Headroom_{OS,agent,variance}
\]

Với runner chỉ chạy một native build, có thể bắt đầu thử dự phòng 20–30% trên peak RSS đo được; đây là **heuristic lập kế hoạch**, không phải mức tối thiểu do GraalVM quy định. Nếu job chạy Docker-in-Docker, nhiều module hoặc nhiều tiến trình test, phải đo lại toàn bộ workload và tăng phần dự phòng tương ứng.

Không cộng `-Xmx` vào peak RSS lần nữa nếu peak RSS đã đo toàn job; tránh đếm trùng cùng một phần bộ nhớ.

### 3.5. Ví dụ đọc kết quả

Giả sử một native build có số đo:

| Chỉ số | Giá trị minh họa |
|---|---:|
| Native Image builder heap limit | 8 GiB |
| Peak RSS toàn job | 11.5 GiB |
| CPU peak | 4 vCPU gần như liên tục |
| Thời gian build | 18 phút |
| Disk peak trong workspace/temp | 7 GiB |

Không nên chọn runner 8 GiB chỉ vì builder heap là 8 GiB; peak RSS đã vượt mức đó. Nếu cộng dự phòng 25% trên peak RSS, điểm khởi đầu cho RAM runner là khoảng 14.4 GiB, sau đó chọn tier có RAM thực tế cao hơn và kiểm chứng lại.

## 4. Điều tiết CPU và mức song song

### 4.1. CPU ảnh hưởng cả thời gian lẫn RAM

Native Image có thể chạy nhiều phase song song: analysis, compilation, code generation và linking. Tăng số thread thường rút ngắn thời gian nhưng cũng làm tăng số cấu trúc và tác vụ tồn tại đồng thời, từ đó tăng RAM peak.

Không phải cứ runner có nhiều core thì nên dùng toàn bộ. Nếu memory là bottleneck, giảm `--parallelism` có thể giúp build ổn định hơn dù thời gian tăng.

### 4.2. Điều chỉnh `--parallelism`

Ví dụ giới hạn Native Image ở 4 thread:

```bash
native-image --parallelism=4 -jar target/order-service.jar order-service
```

Trong Gradle Native Build Tools:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add('--parallelism=4')
        }
    }
}
```

Trong Maven Native Build Tools:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--parallelism=4</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

Mỗi `buildArg` là một biểu thức option của Native Image, không phải một dòng shell đầy đủ. Giữ các giá trị thuộc cùng một option trong cùng một `buildArg`.

### 4.3. Điều chỉnh heap của Native Image builder

Có thể đặt heap tuyệt đối:

```bash
native-image -J-Xmx8g --parallelism=4 -jar target/order-service.jar order-service
```

Hoặc đặt tỷ lệ trên RAM mà builder nhận diện:

```bash
native-image -J-XX:MaxRAMPercentage=60.0 --parallelism=4 -jar target/order-service.jar order-service
```

Chỉ chọn một chiến lược giới hạn heap phù hợp với runner. Heap quá thấp có thể gây `OutOfMemoryError`; heap quá cao có thể khiến tiến trình native compiler/linker hoặc OS không còn đủ RAM. `-J-Xmx` giới hạn JVM builder, không giới hạn tổng RSS của job.

Với runner 16 GiB, có thể bắt đầu thử `-J-Xmx8g` và `--parallelism=4`, sau đó điều chỉnh theo peak RSS. Đây chỉ là cấu hình thử nghiệm bảo thủ, không phải công thức chung cho mọi ứng dụng.

### 4.4. Tránh nhân đôi concurrency giữa build tool và Native Image

Một job có thể đồng thời chạy:

- Nhiều Maven reactor modules qua `mvn -T`.
- Nhiều Gradle tasks/worker qua `--parallel`.
- Nhiều native image binaries.
- Nhiều CI jobs trên cùng self-hosted runner.
- Native Image builder threads bên trong từng binary.

Nếu mỗi native build dùng 8 thread và runner khởi chạy 3 build đồng thời, tổng tải có thể vượt xa số CPU/RAM có sẵn. Với CI native compilation, nên bắt đầu bằng **một native image build tại một thời điểm trên mỗi runner**; chỉ tăng concurrency khi đã đo được headroom.

Gradle Native Build Tools có giới hạn số native image builds chạy đồng thời. Mặc định giới hạn này dựa trên số CPU cores chia cho 16; có thể điều chỉnh bằng property `org.graalvm.buildtools.max.parallel.builds` trong `gradle.properties` hoặc biến môi trường `GRAALVM_BUILDTOOLS_MAX_PARALLEL_BUILDS`. Giá trị này kiểm soát số image build song song, khác với `--parallelism` kiểm soát thread bên trong một image build.

Ví dụ `gradle.properties`:

```properties
org.graalvm.buildtools.max.parallel.builds=1
```

Với Maven multi-module, tránh bật `-T` cho các module cùng kích hoạt native compilation nếu runner chưa đủ tài nguyên. Có thể để các module compile/test JVM song song, nhưng serialize bước native build trong pipeline.

## 5. Lập kế hoạch dung lượng disk

### 5.1. Những thư mục tiêu thụ disk

Native build có thể tạo nhiều dữ liệu hơn executable cuối cùng:

- Source checkout và generated sources.
- Maven repository `.m2/repository` hoặc Gradle caches.
- GraalVM distribution, native compiler và system packages.
- `target/`, `build/`, AOT generated sources/classes.
- Native Image temporary files, object files và linker outputs.
- Native executable, debug symbols và build reports.
- Docker build context, image layers, intermediate layers và image archive.
- Test reports, logs, tracing metadata và artifacts giữ lại.

Disk peak là tổng các thành phần còn tồn tại đồng thời. Chỉ nhìn kích thước executable cuối cùng sẽ đánh giá thiếu.

### 5.2. Đo disk trước, trong và sau build

Trên Linux:

```bash
df -h
du -sh "$GITHUB_WORKSPACE" 2>/dev/null || true
du -sh "$HOME/.m2/repository" 2>/dev/null || true
du -sh "$HOME/.gradle/caches" 2>/dev/null || true
docker system df 2>/dev/null || true
```

Trước khi chạy native build, ghi lại free space. Sau khi build, kiểm tra lại workspace, thư mục tạm và Docker storage. Với self-hosted runner, cần giám sát disk qua nhiều job vì cache, workspace cũ và image layers có thể tích tụ.

### 5.3. Ước lượng disk cần thiết

Lập kế hoạch theo các phần:

\[
Disk_{required} = Checkout + DependencyCache + BuildTemp + Outputs + ContainerLayers + Headroom
\]

Các số hạng phải được đo trong một pipeline đại diện. Nếu build image container, tính cả image base, layer ứng dụng, layer debug và image archive nếu CI xuất artifact. Giữ khoảng trống để native compiler có thể ghi file tạm trong lúc output cuối chưa được dọn.

### 5.4. Dọn dẹp có chọn lọc

- Dùng runner ephemeral nếu có thể để workspace và container layers được xóa sau job.
- Cache dependency Maven/Gradle và wrapper distributions; đặt cache key theo OS, architecture, JDK/GraalVM và lockfiles.
- Không cache toàn bộ `target/` hoặc `build/` giữa các runner khác OS/architecture/GraalVM version.
- Xóa Docker images/layers cũ trên self-hosted runner theo retention policy.
- Upload executable, test reports và build reports làm artifact trước khi workspace bị dọn.
- Không xóa cache đang được job khác dùng trên runner dùng chung.

### 5.5. Disk và container builds

Nếu CI chạy native build bên trong Docker container, cần tính cả storage của Docker daemon trên host. Xóa file trong container không nhất thiết giải phóng layer của image đã build. Dùng `docker system df` để kiểm tra và cơ chế prune có kiểm soát trên runner chuyên dụng.

## 6. Chọn GitHub-hosted hay self-hosted runner

### 6.1. Runner tiêu chuẩn là baseline, không phải cam kết build thành công

Theo bảng thông số GitHub-hosted runners hiện hành, cấu hình standard phụ thuộc repository visibility. Ví dụ Linux x64 standard runner cho public repository có 4 vCPU, 16 GB RAM và 14 GB SSD; standard runner cho private repository có 2 vCPU, 8 GB RAM và 14 GB SSD. Đây là dung lượng hữu hạn, đặc biệt disk 14 GB có thể chật khi giữ đồng thời dependency cache, build temp và Docker layers.

Thông số runner có thể thay đổi theo loại repository, plan, image và thời điểm. Luôn kiểm tra bảng runner của nhà cung cấp trước khi quyết định.

### 6.2. Ví dụ các tier larger runner

GitHub larger runners hiện có các cấu hình tham khảo:

| vCPU | RAM | SSD | Trường hợp tham khảo |
|---:|---:|---:|---|
| 2 | 8 GB | 75 GB | Build nhỏ, cần nhiều disk hơn runner tiêu chuẩn |
| 4 | 16 GB | 150 GB | Native build vừa, nếu peak RSS đo được phù hợp |
| 8 | 32 GB | 300 GB | Native build nặng hơn hoặc cần giảm thời gian build |
| 16 | 64 GB | 600 GB | Ứng dụng lớn, native tests hoặc pipeline nhiều bước |
| 32 | 128 GB | 1.200 GB | Build rất lớn hoặc workload native song song có kiểm soát |

Đây là ví dụ về các tier của một nhà cung cấp, không phải yêu cầu RAM/CPU của GraalVM. Chọn tier dựa trên peak RSS, CPU time, disk peak và chi phí build thực tế.

### 6.3. Khi nào nên dùng self-hosted runner?

Self-hosted runner hữu ích khi:

- Cần RAM/disk lớn hoặc storage NVMe riêng.
- Cần cache dependency/toolchain lâu dài.
- Cần build native cho nhiều kiến trúc hoặc OS đặc thù.
- Muốn kiểm soát phiên bản compiler/linker và image base.
- Native build quá dài hoặc vượt tài nguyên hosted runner.

Đổi lại, phải vận hành cleanup, cập nhật bảo mật, isolation giữa jobs, theo dõi disk/RAM và bảo đảm job không dùng chung một workspace đang bị thay đổi. Runner có secret production không nên chạy pull request code không tin cậy trên cùng host.

## 7. Container và cgroup limits

### 7.1. Host RAM không phải lúc nào cũng là RAM builder được thấy

Nếu native build chạy trong Docker hoặc Kubernetes pod, builder có thể bị giới hạn bởi cgroup memory. Ví dụ host có 64 GB RAM nhưng container chỉ được cấp 12 GB, Native Image phải hoạt động trong giới hạn container đó.

Docker cho phép đặt hard memory limit và CPU quota. Khi container bị giới hạn, hãy đo trong container/cgroup, không chỉ nhìn `free -h` trên host.

### 7.2. Đừng cấp heap bằng toàn bộ container memory

Ví dụ container có limit 16 GB không nên đặt `-J-Xmx16g` cho builder. Còn phải chừa RAM cho:

- Metaspace, thread stacks và native memory của JVM builder.
- Native compiler/linker.
- Maven/Gradle process và plugin.
- Shell, Docker runtime, logging và agent trong container.

Bắt đầu với heap thấp hơn đáng kể so với container limit, sau đó đọc peak RSS và điều chỉnh. Nếu `memory.events` tăng `oom_kill`, kiểm tra cả tiến trình con và tổng job thay vì chỉ tăng `-Xmx`.

### 7.3. Ví dụ giới hạn Docker

```bash
docker run --rm \
  --memory=16g \
  --cpus=4 \
  -v "$PWD:/workspace" \
  -w /workspace \
  ghcr.io/example/native-build-image:graalvm \
  ./mvnw -Pnative -DskipTests package
```

Ví dụ trên giới hạn container ở 16 GB và 4 CPU. Đây là cấu hình minh họa; heap của Native Image builder và `--parallelism` vẫn cần được cấu hình riêng dựa trên số đo.

## 8. Cấu hình Maven và Gradle cho runner giới hạn tài nguyên

### 8.1. Maven Native Build Tools

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-J-Xmx8g</buildArg>
            <buildArg>--parallelism=4</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

Nếu parent POM đã khai báo `buildArgs`, khi bổ sung ở module con hãy dùng cơ chế merge phù hợp của Maven, ví dụ `combine.children="append"`, để không vô tình xóa các option chung như `--no-fallback`.

### 8.2. Gradle Native Build Tools

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.addAll(
                    '-J-Xmx8g',
                    '--parallelism=4'
            )
        }
    }
}
```

Nếu native tests cũng được build, cấu hình binary `test` riêng hoặc dùng `binaries.all` khi cả hai binary thực sự cần cùng giới hạn. Tránh áp dụng heap/parallelism không phù hợp cho test image nhẹ hơn.

### 8.3. Giới hạn Gradle daemon và số worker

Native Image builder là một JVM riêng với `-J-Xmx`; Gradle daemon có heap riêng được cấu hình bằng `org.gradle.jvmargs`:

```properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
org.gradle.workers.max=2
org.graalvm.buildtools.max.parallel.builds=1
```

Các giá trị trên là ví dụ cho runner nhỏ. Tổng memory vẫn là Gradle daemon + Native Image builder + tiến trình con + OS. Không cộng dồn nhiều build native chỉ vì Gradle có thể chạy nhiều task song song.

### 8.4. Phân biệt các giới hạn

| Cấu hình | Điều khiển |
|---|---|
| `-J-Xmx8g` | Java heap của Native Image builder |
| `-J-XX:MaxRAMPercentage=60.0` | Tỷ lệ heap builder theo RAM mà JVM nhận diện |
| `--parallelism=4` | Số thread tối đa cho một native image build |
| `org.gradle.workers.max=2` | Số Gradle workers có thể hoạt động đồng thời |
| `org.graalvm.buildtools.max.parallel.builds=1` | Số native image builds Gradle plugin chạy đồng thời |
| `--memory=16g` của Docker | Hard memory limit của container |
| `--cpus=4` của Docker | CPU quota của container |

Không nhầm các giới hạn này với nhau. Tăng `-Xmx` không giải quyết CPU throttling; tăng CPU không giải quyết disk full; giảm Gradle workers không tự động giới hạn thread bên trong Native Image nếu chưa cấu hình `--parallelism`.

## 9. Ví dụ pipeline GitHub Actions

Ví dụ dưới đây minh họa một job native build riêng chạy trên self-hosted runner đã gắn label `native-image-large`. Runner cần cài GraalVM, native-image và toolchain C/C++ tương thích trước khi nhận job.

```yaml
name: native-build

on:
  pull_request:
  push:
    branches: [main]

jobs:
  native:
    runs-on: [self-hosted, linux, x64, native-image-large]
    timeout-minutes: 60
    env:
      CI: "true"
    steps:
      - uses: actions/checkout@v4

      - name: Inspect runner resources
        shell: bash
        run: |
          nproc
          free -h
          df -h
          java -version
          native-image --version
          native-image --native-image-info

      - name: Build native executable
        shell: bash
        run: |
          /usr/bin/time -v ./mvnw -Pnative -DskipTests package

      - name: Inspect output and disk
        if: always()
        shell: bash
        run: |
          df -h
          du -sh target 2>/dev/null || true
          find target -maxdepth 2 -type f -printf '%s %p\n' 2>/dev/null | sort -nr | head -30

      - name: Upload native executable
        if: success()
        uses: actions/upload-artifact@v4
        with:
          name: order-service-native
          path: target/order-service
```

Trong production, pin version của các GitHub Actions theo chính sách bảo mật của tổ chức và cài GraalVM/toolchain bằng một bước setup đã được kiểm duyệt hoặc image runner bất biến. Không giả định label `native-image-large` có sẵn; đó là label của self-hosted runner do tổ chức quản lý.

Nếu dùng GitHub-hosted runner, thay `runs-on` bằng label phù hợp với plan/repository. Hãy xem lại bảng thông số runner vì public và private repositories có thể nhận cấu hình CPU/RAM khác nhau dù label tương tự.

## 10. Chọn runner theo workload

Không có một tier duy nhất phù hợp mọi dự án. Bảng sau là hướng khởi đầu để lập benchmark, không phải minimum system requirement:

| Workload | Điểm khởi đầu để thử | Điều cần đo |
|---|---|---|
| Module nhỏ, ít dependency, không build container | Runner 4 vCPU/16 GB hoặc tương đương | Peak RSS, build duration, temp disk |
| Spring Boot service có nhiều starter, AOT và metadata | Runner 8 vCPU/32 GB hoặc tương đương | RSS theo parallelism, compiler/linker time, disk peak |
| Monolith lớn, nhiều integration và native tests | Runner 16 vCPU/64 GB hoặc tương đương | Peak RSS của main/test image, concurrency và container layers |
| Multi-module reactor có nhiều native binaries | Runner 16 vCPU/64 GB trở lên hoặc tách job theo module | Tổng số image build đồng thời, disk cache và memory peak |

Chỉ tăng runner tier khi số đo cho thấy CPU/RAM/disk là bottleneck. Nếu build chậm do tải dependency hoặc Docker image pull, tăng CPU/RAM có thể không giải quyết nguyên nhân.

## 11. Chẩn đoán lỗi tài nguyên

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `OutOfMemoryError: Java heap space` | Heap builder quá thấp hoặc phân tích cần nhiều heap hơn | Kiểm tra `-J-Xmx`, giảm `--parallelism`, hoặc dùng runner RAM lớn hơn |
| Job bị OOM-kill nhưng không có Java stack trace | Tổng RSS vượt cgroup/host limit; native compiler hoặc tiến trình con bị kill | Đọc `memory.events`, `memory.peak`, runner telemetry; giảm concurrency và heap hoặc tăng memory limit |
| Build rất chậm dù CPU nhiều | CPU quota thấp, compiler/linker bị throttle, disk I/O hoặc dependency download | Kiểm tra cgroup CPU throttling, I/O, cache và toolchain |
| RAM peak cao bất thường | Nhiều native builds/Gradle workers chạy cùng lúc | Đặt `org.graalvm.buildtools.max.parallel.builds=1`, giảm workers và `--parallelism` |
| Hết disk giữa native compilation | Temp files, cache, output và Docker layers cùng tồn tại | Đo `df -h`, chuyển sang runner disk lớn, cleanup cache có kiểm soát hoặc giảm artifacts trung gian |
| Build fail ngẫu nhiên trên hosted runner | Tier CPU/RAM khác nhau theo repository visibility hoặc job concurrency | Xác nhận runner thực tế, pin tier lớn hơn hoặc chuyển self-hosted |
| Build trong Docker OOM dù host còn RAM | Container memory limit thấp hơn host RAM | Kiểm tra cgroup bên trong container và điều chỉnh `--memory`/pod limit |
| Tăng `-Xmx` nhưng vẫn OOM-kill | Heap không phải toàn bộ RSS; native memory/linker/OS thiếu headroom | Giảm heap/parallelism hoặc tăng tổng RAM; không chỉ tăng Xmx |
| Cache làm runner nhanh lúc đầu nhưng hết disk về sau | Cache và workspace tích lũy trên self-hosted runner | Dùng ephemeral runner hoặc retention/cleanup policy |
| Build native x64 trên runner ARM64 | Architecture/toolchain không khớp hoặc đang cross-compile ngoài hỗ trợ | Chọn runner cùng OS/architecture target hoặc cấu hình cross compilation theo tài liệu GraalVM |

## 12. Bài thực hành: đo và chọn runner cho order-service

**Bối cảnh:** `order-service` có Spring Web, Data JPA, Actuator, Flyway và PostgreSQL driver. Pipeline cần build native executable, chạy native smoke test và đóng gói OCI image.

### Bước 1 — Tạo baseline

Chạy native build trên runner hiện có. Ghi:

- CPU, RAM, disk và kiến trúc thực tế của runner.
- GraalVM/JDK, Maven/Gradle, C compiler và linker version.
- Peak RSS toàn job, heap builder, CPU utilization và thời gian build.
- Disk free trước build, disk peak và kích thước Docker layers sau build.

### Bước 2 — Thử điều chỉnh song song

Chạy các cấu hình `--parallelism=2`, `4` và `8` (nếu runner có đủ CPU/RAM). Giữ nguyên heap hoặc ghi rõ khi thay đổi. So sánh build duration, peak RSS và CPU throttling.

### Bước 3 — Thử heap limit

Với một parallelism đã chọn, thử `-J-Xmx` hoặc `-J-XX:MaxRAMPercentage`. Không thay nhiều biến cùng lúc; nếu đổi heap và parallelism cùng một lần, khó xác định yếu tố nào làm kết quả khác.

### Bước 4 — Thử giới hạn container

Chạy build trong container với memory/CPU limit gần cấu hình CI. Kiểm tra cgroup peak và OOM events. Xác nhận container có đủ disk cho workspace, temp và Docker output.

### Bước 5 — Chọn runner tier

Chọn tier thấp nhất vẫn đáp ứng:

- Build lặp lại ổn định, không OOM và không disk full.
- Peak RSS còn headroom cho biến động workload.
- CPU/disk không bị throttle đáng kể.
- Build duration đáp ứng thời gian CI mong muốn.
- Toolchain/architecture khớp với image sẽ triển khai.

### Bước 6 — Ghi lại cấu hình

Đưa các giá trị đã đo vào `pom.xml`/`build.gradle`, runner labels, container limits và CI job. Ghi lại GraalVM version cùng số đo để lần nâng cấp tiếp theo có baseline so sánh.

### Phiếu kết quả

| Chỉ số | Baseline | Cấu hình chọn |
|---|---:|---:|
| Runner vCPU | _(ghi)_ | _(ghi)_ |
| Runner RAM | _(ghi)_ | _(ghi)_ |
| Runner disk | _(ghi)_ | _(ghi)_ |
| Container memory limit | _(ghi)_ | _(ghi)_ |
| `-J-Xmx` hoặc MaxRAMPercentage | _(ghi)_ | _(ghi)_ |
| `--parallelism` | _(ghi)_ | _(ghi)_ |
| Native builds đồng thời | _(ghi)_ | _(ghi)_ |
| Peak RSS | _(ghi)_ | _(ghi)_ |
| Peak disk usage | _(ghi)_ | _(ghi)_ |
| Build duration | _(ghi)_ | _(ghi)_ |
| OOM/disk failure | _(ghi)_ | _(ghi)_ |

## 13. Ghi nhớ

Native Image builder chạy trên JVM nhưng tổng tài nguyên build còn bao gồm native compiler/linker, Maven/Gradle, OS và container runtime. Hãy chọn RAM theo peak RSS toàn job, không lấy `-Xmx` làm tổng bộ nhớ. Điều tiết `--parallelism`, Gradle workers và số image builds chạy đồng thời để tránh nhân đôi tải. Tính disk cho cache, temp, AOT output, native artifacts và container layers; theo dõi disk trên cả hosted lẫn self-hosted runners.

Runner phù hợp là runner có thể build lặp lại ổn định, còn headroom cho biến động và có toolchain đúng OS/architecture. Bắt đầu từ số đo baseline, thay đổi từng biến một, rồi chọn tier có chi phí hợp lý. Không có một con số RAM/CPU cố định áp dụng cho mọi Spring Boot Native Image project.

### Tài liệu tham khảo chính thức

- [GraalVM — Native Image Build Output and Build Resources](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/)
- [GraalVM — Native Image Build Configuration](https://www.graalvm.org/reference-manual/native-image/BuildConfiguration/)
- [GraalVM — Native Image Command-line Options](https://www.graalvm.org/latest/reference-manual/native-image/overview/Options/)
- [GraalVM Native Build Tools — Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin)
- [GraalVM Native Build Tools — Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin.html)
- [GitHub Actions — GitHub-hosted Runners Reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [GitHub Actions — Larger Runners Reference](https://docs.github.com/en/actions/reference/runners/larger-runners)
- [Docker — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/)
