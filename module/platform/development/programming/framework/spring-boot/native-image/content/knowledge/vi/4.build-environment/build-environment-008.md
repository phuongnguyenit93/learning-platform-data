# Dung lượng đĩa, RAM và CPU cho quá trình biên dịch native

Biên dịch ứng dụng Spring Boot thành **GraalVM Native Image** là công việc tiêu tốn tài nguyên đáng kể ở *thời điểm build*. So với việc tạo một file JAR chạy trên JVM, Native Image phải phân tích đường gọi và các kiểu có khả năng được sử dụng (*reachability analysis*), xử lý metadata cho reflection/resource, tối ưu mã, biên dịch ra mã máy và liên kết executable. **Spring AOT** giúp làm rõ cấu trúc ứng dụng Spring trước khi GraalVM phân tích, nhưng không loại bỏ chi phí của các công đoạn đó.

Vì vậy, một dịch vụ Spring Boot có thể chạy ổn với vài trăm MB RAM sau khi khởi động nhưng **cần nhiều GB RAM và nhiều phút xử lý CPU để build bản native**. Bài học này hướng dẫn ước lượng tài nguyên đĩa, RAM, CPU, quan sát điểm nghẽn và cấu hình build Maven/Gradle hoặc container sao cho có thể tái lập kết quả.

## 1. Phân biệt tài nguyên lúc build và lúc chạy

| Khía cạnh | Build native | Chạy native executable |
|---|---|---|
| Mục tiêu | Phân tích toàn bộ chương trình có thể truy cập và tạo executable | Khởi động và phục vụ nghiệp vụ |
| CPU | Dùng để phân tích, tối ưu và sinh mã máy; có thể dùng nhiều lõi | Phụ thuộc request, tác vụ nền và tải thực tế |
| RAM | Cần bộ nhớ cho trình build, cấu trúc phân tích và các công cụ phụ trợ | Chủ yếu cho heap/runtime của ứng dụng và thư viện |
| Đĩa | Cần dependency cache, mã AOT, file trung gian, executable, container layers nếu có | Cần executable, dữ liệu ứng dụng, log và storage của workload |
| Chỉ số theo dõi | Thời gian build, peak RAM/RSS, CPU, đĩa trống, tỷ lệ build thành công | Thời gian khởi động, RSS, throughput, latency và độ ổn định |

**Không lấy mức RAM khi chạy native để suy ra RAM phải cấp cho native compiler.** Hai pha thực hiện hai công việc khác nhau. Ngược lại, yêu cầu RAM lớn ở CI/CD không chứng minh ứng dụng native sẽ dùng nhiều RAM hơn JVM khi vận hành.

Góc nhìn tổng quát:

~~~mermaid
flowchart TD
    A["Source Spring Boot và dependencies"] --> B["Spring AOT sinh mã và metadata"]
    B --> C["GraalVM Native Image: reachability và tối ưu"]
    C --> D["Sinh mã máy và liên kết executable"]
    D --> E["Native executable"]
    F["CPU, RAM, dung lượng đĩa build host"] --> B
    F --> C
    F --> D
    E --> G["Chạy với tài nguyên runtime riêng"]
~~~

Trong thực tế, các công đoạn có thể xen kẽ hoặc được triển khai khác nhau giữa các phiên bản công cụ; sơ đồ chỉ giúp hình dung nguồn tiêu thụ tài nguyên.

## 2. Vì sao native compilation tốn tài nguyên?

Một build native phải xử lý nhiều thông tin trước khi executable có thể chạy:

1. **Spring AOT** phân tích bean, auto-configuration và những thành phần hỗ trợ AOT; tạo Java source và metadata.
2. **Phân tích reachability** xác định các phương thức, kiểu, trường dữ liệu và đường đi cần được đưa vào image.
3. **Phân tích và tối ưu mã** trên những phần reachable, có thể bao gồm các pha tối ưu liên thủ tục và tối ưu ở mức thấp.
4. **Sinh mã máy** cho kiến trúc và hệ điều hành đích.
5. **Liên kết** với thành phần native runtime và những thư viện liên quan để sinh executable.
6. **Đóng gói container** nếu pipeline còn tạo image với Buildpacks hoặc Docker.

Mỗi bước có một kiểu áp lực khác nhau. Reachability và tối ưu có thể làm tăng nhu cầu RAM; sinh mã có thể làm nhiều lõi CPU bận liên tục; liên kết và ghi output tạo thêm nhu cầu đĩa. Nếu build trong container, các giới hạn cgroup/Docker và bộ nhớ được cấp cho VM hoặc WSL cũng ảnh hưởng kết quả.

Độ phức tạp không tỷ lệ trực tiếp với số dòng code ứng dụng. Một module nhỏ nhưng kéo theo nhiều thư viện, cơ chế reflection hay bộ xử lý annotation có thể có thời gian và footprint build lớn hơn dự kiến.

## 3. Ước lượng cấu hình máy ban đầu

Không có một mức RAM, CPU hay dung lượng đĩa trống **bảo đảm phù hợp cho mọi ứng dụng**. Giá trị thay đổi theo phiên bản JDK/GraalVM, Spring Boot, dependency, metadata, chế độ tối ưu, hệ điều hành và cách build container. Bảng sau chỉ là **mốc khởi đầu thực hành**, không phải yêu cầu tối thiểu chính thức hoặc cam kết rằng mọi dự án đều build thành công.

| Quy mô tham khảo | CPU logic dành cho build | RAM khả dụng cho môi trường build | Dung lượng đĩa trống nên dự phòng |
|---|---:|---:|---:|
| Demo API hoặc dịch vụ nhỏ, ít dependency | 4 lõi | 8–16 GB | 15–25 GB |
| Dịch vụ Spring Boot mức vừa, nhiều starter thông dụng | 8 lõi | 16–32 GB | 25–50 GB |
| Ứng dụng lớn, đồ thị dependency rộng hoặc nhiều build song song | 12–16 lõi trở lên | 32–64 GB trở lên | 50 GB trở lên, tùy cache và container layers |

Các con số là **năng lực môi trường để bắt đầu thử nghiệm**. Một dự án đơn giản có thể build được trên cấu hình thấp hơn; một dự án phức tạp có thể cần nhiều hơn đáng kể. Cần xác nhận bằng **đỉnh sử dụng tài nguyên thực tế (peak)** và chừa dư địa cho lần build sau khi dependency thay đổi.

Nếu chỉ có máy 8 GB RAM, hãy thử dịch vụ mẫu nhỏ, tránh chạy nhiều ứng dụng nặng đồng thời và xem xét build trên CI runner/host có nhiều RAM hơn cho dự án thực. Nếu máy có 16 GB nhưng đang chạy IDE, trình duyệt, Docker Desktop và database, **RAM khả dụng cho native build sẽ nhỏ hơn 16 GB**.

### Cách chọn cấu hình theo công việc

- **Học tập và build thử:** ưu tiên môi trường có đủ RAM để hoàn thành build; tăng CPU giúp giảm thời gian khi không nghẽn RAM hoặc I/O.
- **CI/CD ổn định:** đo peak của một lần build đầy đủ, thêm biên an toàn và quản lý số job được chạy đồng thời.
- **Monorepo hoặc nhiều service:** tính tài nguyên theo **số build chạy đồng thời**, không chỉ theo một service.
- **Build container:** kiểm tra hạn mức của Docker/WSL/VM, dung lượng storage của Docker và cấu hình runner ngoài số liệu của máy host.

## 4. RAM: thường là giới hạn đầu tiên cần kiểm soát

Trong một build Maven/Gradle và Native Image, RAM có thể được sử dụng bởi nhiều tiến trình hoặc thành phần:

- JVM chạy Maven hoặc Gradle và Gradle daemon nếu có.
- JVM/tiến trình do Native Image dùng để phân tích và biên dịch.
- Bộ nhớ native ngoài Java heap: thread stacks, cấu trúc compiler, thư viện và bộ nhớ ánh xạ file.
- Linker cùng các tiến trình công cụ hệ thống.
- Hệ điều hành, IDE, Docker daemon/VM và các dịch vụ khác.

**Java heap của trình build không phải toàn bộ RAM mà build sử dụng.** Đặt giới hạn heap bằng `-J-Xmx` chỉ giới hạn một phần bộ nhớ của tiến trình Native Image; tổng RSS và tổng tài nguyên của pipeline còn có thể cao hơn.

### Ví dụ ngân sách RAM

Giả sử máy build có 16 GB RAM và bạn dự định cấp tối đa 8 GB heap cho Native Image:

~~~text
RAM máy build                 : 16 GB
Heap tối đa Native Image       :  8 GB  (ví dụ)
Phần còn lại                   :  8 GB
Dùng cho                      : OS, non-heap/native memory,
                                Maven/Gradle, linker, Docker/WSL,
                                daemon, các tiến trình khác
~~~

Đây là **một ví dụ phân bổ**, không phải công thức đảm bảo. Nếu Native Image cần heap lớn hơn, giới hạn `-J-Xmx8g` có thể gây lỗi `java.lang.OutOfMemoryError`. Nếu máy hoặc container không còn RAM cho overhead ngoài heap, tiến trình có thể bị hệ điều hành kết thúc dù chưa chạm mức heap đó.

Đừng đặt heap bằng đúng toàn bộ RAM vật lý. Với container, phải tính theo giới hạn bộ nhớ thực sự được cấp cho container/VM và các tiến trình chạy bên trong.

### Phân biệt hai nhóm lỗi thiếu bộ nhớ

| Dấu hiệu | Cách hiểu ban đầu | Việc cần làm |
|---|---|---|
| `java.lang.OutOfMemoryError: Java heap space` | Heap JVM của trình build bị thiếu hoặc cấu trúc phân tích quá lớn | Kiểm tra giá trị heap đang áp dụng, cân nhắc tăng `-J-Xmx` khi còn RAM vật lý |
| Build bị `Killed`, kết thúc mã 137 trên Linux/container, hoặc log báo `OOMKilled` | Có thể bị OS/cgroup kết thúc vì tổng memory vượt hạn mức | Kiểm tra cgroup/Docker/runner, giảm concurrency hoặc tăng RAM giới hạn |
| Máy bắt đầu swap mạnh, build rất chậm | Bộ nhớ vật lý bị áp lực dù tiến trình chưa chết | Giảm tiến trình chạy đồng thời, giới hạn concurrency, tăng RAM |
| Gradle daemon biến mất | Có thể do áp lực RAM hoặc lỗi riêng của daemon | Xem daemon log và system log; không mặc định lỗi nằm ở Native Image |

Mã thoát 137 thường cho thấy tiến trình nhận SIGKILL, nhưng **không đủ một mình để kết luận OOM**; cần đối chiếu kernel log hoặc trạng thái container.

## 5. CPU: số lõi, mức song song và hiệu quả thực tế

Native compilation có những pha sử dụng nhiều CPU và có thể khai thác nhiều lõi. Vì vậy, nâng số lõi từ 2 lên 4 hoặc 8 thường giúp rút ngắn build nếu còn đủ RAM và I/O. Tuy nhiên, **tăng lõi không luôn giảm thời gian theo tỷ lệ tuyến tính**.

Các nguyên nhân gồm:

- Một số pha không song song hóa hoàn toàn.
- Thêm worker có thể làm tăng áp lực RAM, garbage collection hoặc I/O.
- Máy ảo và CI runner có thể có quota CPU hoặc bị chia sẻ tài nguyên với job khác.
- Linker và các pha xử lý nối tiếp có thể trở thành giới hạn sau khi phần compiler đã được tăng tốc.

Ví dụ, nếu 8 lõi rút ngắn một build nhưng làm peak RAM vượt hạn mức runner, cấu hình 4 lõi ổn định có thể hiệu quả hơn cho CI. Hãy đánh giá **thời gian build thành công**, thay vì chỉ nhìn CPU luôn ở 100%.

### Tài nguyên song song ở ba cấp

1. **Song song bên trong Native Image:** số thread mà công cụ build sử dụng.
2. **Song song của build tool:** Maven/Gradle có thể chạy task/module hoặc worker khác cùng lúc.
3. **Song song của CI:** nhiều job native build dùng chung runner hoặc host.

Tổng áp lực CPU/RAM là kết quả của cả ba cấp. Một runner 8 vCPU chạy **hai job native song song** không tương đương với mỗi job được độc quyền 8 vCPU.

## 6. Dung lượng đĩa: không chỉ là kích thước executable

Dung lượng thực sự cần trong lúc build có thể lớn hơn rất nhiều so với file native cuối cùng. Cần tính cả đầu vào, cache và dữ liệu tạm:

| Nơi lưu | Những gì thường chiếm đĩa |
|---|---|
| Source workspace | Source code, resource, generated source của Spring AOT |
| `~/.m2/repository` | Dependency và plugin tải về của Maven |
| `~/.gradle/caches` | Dependency, Gradle distribution và các cache build |
| `target/` hoặc `build/` | Classes, mã AOT, object và output trung gian, test artifacts, executable |
| Thư mục tạm của OS/build | File trung gian, log, object/linker output tùy công cụ |
| Docker/Buildpacks storage | Builder image, run image, layers, cache buildpacks, image cuối cùng |

Không nên ước lượng “native executable chỉ 80 MB nên cần 80 MB đĩa”. Ngay một build trả về file vài chục MB cũng có thể dùng nhiều GB vì compiler intermediates và caches. Khi build với Buildpacks, Docker còn cần chỗ cho image/layer và cache được giữ lại giữa các lần build.

### Đĩa trống ở đâu mới quan trọng?

Trên máy có nhiều ổ hoặc nhiều volume, hãy phân biệt:

- **Workspace volume:** nơi chứa dự án, `target/` và `build/`.
- **Cache volume:** nơi Maven/Gradle lưu dependency và các cache.
- **Temporary volume:** nơi hệ điều hành hoặc linker ghi file tạm.
- **Docker data volume:** nơi Docker daemon lưu layers và images; có thể nằm trong VM/WSL chứ không nằm ở cùng phân vùng với mã nguồn.

Một ổ còn trống nhiều không giúp ích nếu phân vùng chứa Docker data hoặc thư mục tạm đã đầy. Thông báo `No space left on device` cần được đối chiếu đúng volume đang dùng.

## 7. Kiểm tra tài nguyên trước khi build

Nên xác nhận **máy build thật sự nhìn thấy bao nhiêu CPU, RAM và đĩa**, nhất là khi làm việc với Docker Desktop, WSL hoặc CI container. Số liệu hiển thị trên host có thể khác hạn mức container.

### Trên Linux

~~~bash
# Số CPU logic hệ thống cung cấp
nproc

# RAM/swap nhìn thấy trong môi trường hiện tại
free -h

# Dung lượng và phần trăm dùng của phân vùng
df -h

# Quan sát tiến trình và áp lực CPU/RAM khi build
top
~~~

Nếu chạy trong container, các lệnh trên có thể phản ánh thông tin host hoặc khác hạn mức cgroup tùy môi trường. Hãy xem thêm cấu hình memory/CPU của container hoặc runner.

### Trên Windows PowerShell

~~~powershell
# RAM vật lý tổng và RAM hiện có (đơn vị GB)
$os = Get-CimInstance Win32_OperatingSystem
[pscustomobject]@{
    TotalRAM_GB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
    FreeRAM_GB  = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
}

# Số lõi logic của các bộ xử lý trên máy
(Get-CimInstance Win32_Processor |
    Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum

# Dung lượng còn trống của các ổ đĩa
Get-PSDrive -PSProvider FileSystem |
    Select-Object Name,
        @{Name='FreeGB'; Expression={[math]::Round($_.Free / 1GB, 1)}},
        @{Name='UsedGB'; Expression={[math]::Round($_.Used / 1GB, 1)}}
~~~

Thông tin này phản ánh máy Windows; khi build bên trong WSL2 hoặc Docker Desktop, phải kiểm tra hạn mức và dung lượng đĩa của môi trường đó nữa.

### Với Docker

~~~bash
docker info
docker system df
~~~

`docker info` giúp kiểm tra môi trường và tài nguyên daemon báo cáo; `docker system df` cho biết lượng storage do Docker objects đang dùng. Khi đang chạy build container, có thể quan sát container bằng `docker stats` nếu container tương ứng xuất hiện và vẫn đang hoạt động.

**Không dùng lệnh xóa toàn bộ Docker cache/layers một cách tự động** chỉ vì thiếu đĩa; cần xác định đúng dữ liệu có thể dọn và tác động với những dự án khác cùng host.

## 8. Chạy native build và lưu số liệu để so sánh

Với dự án Spring Boot đã cấu hình GraalVM và plugin tương ứng, các lệnh phổ biến:

~~~bash
# Maven: thường cần native profile đã được cấu hình
./mvnw -Pnative native:compile

# Gradle: cần GraalVM Native Build Tools plugin
./gradlew nativeCompile
~~~

Trên Windows dùng wrapper tương ứng `mvnw.cmd` và `gradlew.bat`. Đường dẫn output và cách cấu hình native profile/task có thể phụ thuộc dự án.

### Đo thời gian trên Linux

~~~bash
# Đo elapsed time và peak RSS nếu máy có GNU time
/usr/bin/time -v ./mvnw -Pnative native:compile
~~~

GNU `time -v` thường cung cấp các trường như `Elapsed (wall clock) time`, `Maximum resident set size` và tỷ lệ CPU. Nếu build dùng nhiều tiến trình, chỉ số được báo cần được hiểu theo cách `time` tổng hợp tiến trình con; nó **không nhất thiết là đỉnh RAM toàn bộ host**. Có thể kết hợp công cụ giám sát host hoặc cgroup để đo đầy đủ hơn.

### Đo thời gian trên PowerShell

~~~powershell
Measure-Command { .\mvnw.cmd -Pnative native:compile }
~~~

`Measure-Command` cho thời gian thực thi nhưng không tự báo đỉnh RAM/CPU. Hãy quan sát Task Manager, Resource Monitor hoặc công cụ giám sát hệ thống tương ứng trong lúc lệnh chạy.

### Ghi nhật ký tài nguyên tối thiểu

Mỗi lần đo nên lưu:

| Trường | Ví dụ minh họa |
|---|---|
| Artifact | `payment-api`, commit và cấu hình build cố định |
| Toolchain | Spring Boot version, JDK/GraalVM version, Maven/Gradle version |
| Host/runner | 8 vCPU, 16 GB RAM, Linux x86-64 |
| Kiểu build | Local nativeCompile hoặc Buildpacks container |
| Cache | Clean/cold hay warm cache |
| Thời gian | Wall-clock elapsed time |
| Bộ nhớ | Peak RSS của tiến trình hoặc peak memory của job/cgroup |
| Đĩa | Dung lượng trống trước/sau và đỉnh nếu đo được |
| Kết quả | Success/failure, giai đoạn lỗi và log liên quan |

Các giá trị trong bảng là ví dụ cách ghi, **không phải số đo thực nghiệm**. Phân biệt rõ *cold build* (chưa có cache liên quan) và *warm build* (đã có dependency/layer cache), vì hai lần build có thể khác nhiều về thời gian và I/O.

## 9. Điều chỉnh RAM và mức song song

Nếu đã có dữ liệu đo và xác định Native Image thiếu heap, có thể truyền tùy chọn cho trình native-image. Ví dụ, thiết lập heap tối đa 8 GB và giới hạn số luồng biên dịch ở 4; **chỉ áp dụng nếu phiên bản Native Image đang dùng hỗ trợ những tùy chọn này**:

~~~text
-J-Xmx8g
--parallelism=4
~~~

`-J-Xmx8g` đặt giới hạn heap cho JVM chạy công cụ Native Image. Nó **không đảm bảo tổng RAM tiêu thụ là 8 GB** và không làm ứng dụng native sau khi build chạy với heap 8 GB.

`--parallelism=4` nhằm giới hạn số luồng Native Image sử dụng trong những phiên bản hỗ trợ. Kiểm tra `native-image --help` hoặc tài liệu đúng phiên bản công cụ để xác nhận cú pháp; một số bản dùng cơ chế cấu hình khác.

### Ví dụ cấu hình trong Gradle (Groovy DSL)

Khi đã dùng GraalVM Native Build Tools plugin, có thể thêm vào `build.gradle`:

~~~groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add('-J-Xmx8g')
            buildArgs.add('--parallelism=4')
        }
    }
}
~~~

### Ví dụ cấu hình trong Maven

Khi dự án đã kích hoạt `org.graalvm.buildtools:native-maven-plugin`, phần cấu hình plugin có thể chứa:

~~~xml
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
~~~

Mẫu trên minh họa riêng phần build arguments; dự án vẫn cần cấu hình plugin, dependency và toolchain phù hợp. Đừng sao chép giá trị 8 GB/4 luồng như một mặc định chung. Nếu build thường bị OOM, trước hết kiểm tra RAM thực có sẵn, giới hạn container và số build đồng thời; đặt heap lớn hơn trong máy thiếu RAM có thể làm tình hình tệ hơn.

## 10. Khi build bằng Buildpacks hoặc Docker

Spring Boot hỗ trợ tạo container image; trong một số cấu hình, Spring Boot Maven/Gradle plugin dùng Cloud Native Buildpacks và builder hỗ trợ native image. Cách build này thường **tiêu thụ thêm đĩa và có thể thêm áp lực RAM** do builder image, layers, cache và container build.

~~~bash
# Ví dụ Maven với native profile và plugin đã cấu hình
./mvnw -Pnative spring-boot:build-image

# Ví dụ Gradle với cấu hình native image/buildpacks tương ứng
./gradlew bootBuildImage
~~~

Lệnh Gradle `bootBuildImage` không tự bảo đảm chọn native executable chỉ vì GraalVM Native Build Tools đã được cài. Cần cấu hình đúng loại build image/native environment theo phiên bản Spring Boot và builder đang sử dụng.

Kiểm tra bốn yếu tố:

1. **Docker daemon có hoạt động và đủ dung lượng lưu image/layer không?**
2. **Container build được cấp đủ RAM và CPU không?** Trên Docker Desktop, giới hạn của VM/WSL có thể thấp hơn tổng RAM host.
3. **Builder có phù hợp với hệ điều hành/kiến trúc đích không?** Native executable gắn với platform.
4. **Có đủ đĩa cho cả builder cache và image đầu ra không?** Nếu CI dùng runner ngắn hạn, dữ liệu phải được tải lại, làm thay đổi thời gian và dung lượng sử dụng.

**Tránh so sánh trực tiếp thời gian `nativeCompile` local với `build-image` trong container** rồi quy kết mọi chênh lệch cho native compiler. Hai pipeline có chi phí tải dependencies, layers và đóng gói khác nhau.

## 11. Phân tích điểm nghẽn bằng dấu hiệu quan sát được

| Hiện tượng | Khả năng cần điều tra | Hướng xử lý |
|---|---|---|
| Build chết với `Java heap space` | Heap build thiếu so với phân tích thực tế | Xem memory log và heap setting; tăng khi có headroom |
| Build bị kill đột ngột trong Docker/CI | Giới hạn cgroup/runner hoặc memory pressure | Kiểm tra OOM event, giảm job đồng thời, tăng memory limit |
| CPU luôn cao nhưng build vẫn tiến triển | Compiler đang dùng CPU; chưa chắc là lỗi | Đo elapsed time và peak RAM trước khi thay cấu hình |
| CPU thấp, ổ đĩa hoạt động mạnh, nhiều swap | Nghẽn RAM hoặc I/O | Tăng RAM, giảm swap pressure hoặc chuyển workspace/cache sang đĩa nhanh hơn |
| Build dừng với `No space left on device` | Workspace, temp, Docker data hoặc cache volume đầy | Xác định đúng filesystem và dữ liệu có thể dọn |
| Build trên CI chậm hơn local | CPU quota thấp, storage chậm, cold cache, network | So sánh cấu hình runner/cache và chia thời gian theo giai đoạn |
| Sau khi thêm thư viện, peak RAM tăng mạnh | Đồ thị reachable/metadata/đường biên dịch thay đổi | Kiểm tra dependency mới, khả năng đăng ký reflection quá rộng và log build |
| Nhiều build chạy song song đều chậm hoặc thất bại | Tranh chấp CPU/RAM/đĩa | Giảm mức song song giữa các job hoặc tăng runner capacity |

Tránh kết luận chỉ từ một dấu hiệu. Ví dụ, build chậm có thể do tải dependency qua mạng hoặc thiếu toolchain, không liên quan CPU. Một báo lỗi liên kết native cũng có thể do thiếu thư viện hệ thống chứ không phải hết RAM hay đĩa.

## 12. Lập kế hoạch dung lượng cho CI/CD

Giả sử một service có một build native chạy độc lập với peak memory quan sát được là 14 GB trên runner 8 vCPU và hoàn tất ổn định. Đừng mặc định runner 16 GB có thể chạy **hai build cùng lúc**: hai job có thể tạo tổng nhu cầu bộ nhớ vượt xa 16 GB, chưa tính OS và build tool.

Cách lập kế hoạch hợp lý:

1. **Đo một build đơn lẻ** trên đúng toolchain và runner dự kiến.
2. **Xác định peak memory thực**, đĩa cần lúc build và thời gian hoàn tất (gồm cả cold/warm cache).
3. **Chừa khoảng dự phòng** cho OS, linker, dependency tăng dần và sự biến thiên của runner.
4. **Tính concurrency:** số job chạy đồng thời phải phù hợp ngân sách RAM, CPU và đĩa tổng.
5. **Xác nhận bằng vài lần build ổn định** trên commit và điều kiện tương đương trước khi áp dụng làm cấu hình CI chuẩn.

Với runner có RAM thấp, đôi khi chạy tuần tự hai service nhanh hơn tổng thể so với cho cả hai chạy cùng lúc rồi bị swap hoặc OOM. Với runner có dư CPU và RAM, song song hóa lại có thể giảm thời gian chờ của pipeline.

### Ví dụ giả định để tính ngân sách

Giả sử đo được mỗi job native sử dụng peak **12 GB memory ở cấp job** và khoảng **20 GB dung lượng workspace/cache tăng thêm**. Nếu runner có 32 GB RAM và 80 GB đĩa còn trống, trước khi chạy hai job đồng thời phải tính thêm tài nguyên OS, các tiến trình nền, chênh lệch peak và Docker storage. Không thể chỉ lấy `32 / 12 = 2` rồi kết luận chắc chắn chạy được hai job.

Các con số 12 GB và 20 GB ở đây là **giả định minh họa**, không phải chuẩn tiêu thụ của Spring Boot/GraalVM.

## 13. Những cách giảm áp lực tài nguyên

Nếu yêu cầu tài nguyên vượt quá máy hiện có, có thể điều chỉnh theo thứ tự sau:

**Giảm phần việc không cần thiết của pipeline.** Không bắt mọi nhánh commit đều chạy full native build nếu nhu cầu kiểm thử cho phép một số bước dùng JVM/AOT trước; bố trí native build ở giai đoạn cần xác nhận tương thích và phát hành.

**Quản lý dependency và metadata.** Loại bỏ thư viện thực sự không dùng, tránh mở rộng reflection/resource hints quá rộng và kiểm tra cơ chế đăng ký class động. Điều này có thể giúp GraalVM phân tích ít mã hơn, nhưng tác động cần được đo; không phải mọi dependency lớn đều tăng kích thước image hay peak RAM như nhau.

**Dùng cache phù hợp.** Maven/Gradle dependency caches và Docker/Buildpacks cache có thể giảm thời gian tải/tạo một số đầu vào. Cache cũng chiếm dung lượng; cần thiết kế chính sách lưu giữ và đo cả trường hợp cold cache.

**Đặt concurrency hợp lý.** Nếu bottleneck là RAM, giảm số job hoặc mức song song thường hiệu quả hơn việc cố tăng heap. Nếu bottleneck thực sự là CPU và còn RAM, runner có nhiều lõi có thể giúp giảm thời gian build.

**Dùng runner phù hợp.** Tách native build khỏi máy laptop vốn phải chạy IDE, browser và database; CI runner riêng giúp kết quả ổn định và dễ theo dõi hơn.

**Không đánh đổi tùy tiện chất lượng bản phát hành.** Một số tùy chọn tối ưu có thể thay đổi thời gian build và đặc tính runtime của image. Nếu dùng chế độ build nhanh để lặp phát triển, cần kiểm thử và đo lại trên đúng cấu hình build phát hành.

## 14. Thực hành: đo và tối ưu cùng một dự án

Mục tiêu là xác định cấu hình build phù hợp **bằng đo đạc**, không đoán từ dung lượng file JAR hoặc image cuối.

**Chuẩn bị.** Chọn một ứng dụng Spring Boot có một endpoint đơn giản, đã cấu hình AOT/GraalVM Native Build Tools. Ghi lại hệ điều hành, JDK/GraalVM, phiên bản plugin, số vCPU, RAM, dung lượng trống và kiểu build local/container.

**Lần 1 — baseline.** Build native với cấu hình mặc định. Đo thời gian thực tế, peak memory, CPU và tình trạng disk. Đảm bảo executable chạy được và endpoint trả kết quả đúng.

**Lần 2 — thay mức song song.** Giữ nguyên source, toolchain và cache policy; điều chỉnh số luồng Native Image (nếu phiên bản hỗ trợ). Ghi lại thời gian và peak RAM. Nếu số lõi giảm khiến RAM thấp hơn nhưng build chậm hơn, đây là một trade-off bình thường.

**Lần 3 — thay giới hạn heap khi có lý do.** Chỉ thay `-J-Xmx` nếu log hoặc số liệu chứng minh heap là điểm nghẽn và host còn headroom. So sánh build success, thời gian GC nếu có dữ liệu và peak memory.

**Lần 4 — mô phỏng CI.** Chạy trong container/runner với quota giống môi trường triển khai, kiểm tra lại đĩa Docker/cache và concurrency. Không dùng kết quả local để mặc nhiên bảo đảm CI thành công.

Ghi kết quả vào mẫu:

| Lần đo | CPU được cấp | RAM/quota | Giới hạn heap | Song song native | Thời gian | Peak memory | Kết quả |
|---|---|---|---|---|---|---|---|
| Baseline | Điền số liệu | Điền số liệu | Mặc định | Mặc định | … | … | … |
| Điều chỉnh luồng | Giữ nguyên | Giữ nguyên | Mặc định | Giá trị thử nghiệm | … | … | … |
| Điều chỉnh heap | Giữ nguyên | Giữ nguyên | Giá trị thử nghiệm | Giữ nguyên | … | … | … |
| Runner/CI | Theo runner | Theo runner | Theo cấu hình | Theo cấu hình | … | … | … |

Một thử nghiệm có ý nghĩa khi thay **một nhóm yếu tố tại một thời điểm**, dùng cùng commit và ghi rõ tác động của cache. Đo đạc runtime (startup, RSS sau khi chạy, throughput) là bước riêng và không được thay thế bằng số liệu build.

## 15. Tổng kết

Để biên dịch Spring Boot thành GraalVM Native Image, cần chuẩn bị **CPU cho phân tích và tối ưu**, **RAM cho compiler cùng các tiến trình phụ trợ**, và **đĩa cho dependency cache, mã AOT, file trung gian và container layers**. Các nguồn lực này thay đổi theo dự án và môi trường build; nên dùng bảng cấu hình tham khảo để bắt đầu, sau đó chốt cấu hình dựa trên peak memory, thời gian build và kết quả chạy thực tế.

Ba nguyên tắc quan trọng nhất là: **đo tài nguyên của chính pipeline**, **dành headroom cho toàn bộ môi trường chứ không chỉ heap Native Image**, và **kiểm soát số build đồng thời**. Khi đó nhóm có thể chọn máy phát triển, CI runner hoặc builder container phù hợp và đánh giá lợi ích startup/bộ nhớ của bản native mà không bị các lỗi tài nguyên trong lúc build làm sai lệch thí nghiệm.
