# CPU, RAM, I/O và giới hạn tài nguyên của máy build

Hiệu năng build Java phụ thuộc vào nhiều yếu tố của máy thực thi. CPU xử lý biên dịch, phân tích mã và chạy test; RAM giữ dữ liệu, heap của JVM, class metadata và các tiến trình build; I/O đọc mã nguồn, dependency, ghi class file, báo cáo và cache. Mạng cũng ảnh hưởng khi build phải tải dependency hoặc truy cập remote build cache.

Một máy có nhiều lõi CPU chưa chắc build nhanh nếu thiếu RAM, ổ đĩa chậm hoặc nhiều tiến trình tranh chấp tài nguyên. Ngược lại, tăng heap hoặc tăng số worker không phải lúc nào cũng cải thiện tốc độ. Khi số worker quá cao, các tiến trình có thể tranh CPU, RAM và I/O, khiến thời gian hoàn thành tăng lên hoặc build thất bại do hết bộ nhớ.

Để tối ưu máy build, cần xác định nút thắt trước, sau đó điều chỉnh mức song song, bộ nhớ, cache, ổ đĩa và giới hạn CI theo số liệu thực tế. Bài học này tập trung vào CPU, RAM, I/O và cách các giới hạn tài nguyên tác động tới Maven, Gradle và quy trình build Java.

## 1. Ba nhóm tài nguyên chính

Một build thường sử dụng đồng thời nhiều tài nguyên:

| Tài nguyên | Công việc tiêu biểu | Dấu hiệu thiếu hoặc quá tải |
| --- | --- | --- |
| CPU | Biên dịch Java, phân tích mã, nén JAR, chạy test, xử lý annotation processor | CPU sử dụng cao kéo dài, worker phải chờ, thời gian CPU lớn |
| RAM | Heap JVM, class metadata, compiler, test JVM, Gradle/Maven daemon, tiến trình fork | GC thường xuyên, heap gần đầy, swap/pagefile, OOM hoặc tiến trình bị hệ điều hành kết thúc |
| Disk I/O | Đọc source/dependency, ghi class file, archive, báo cáo, cache và file tạm | Disk active time cao, độ trễ đọc/ghi lớn, queue dài, build chậm dù CPU còn rảnh |
| Network I/O | Tải dependency, truy cập repository, remote build cache | Thời gian chờ tải cao, request retry, độ trễ hoặc băng thông mạng thấp |

Ba nhóm CPU, RAM và disk I/O thường được nhắc cùng nhau vì chúng ảnh hưởng trực tiếp tới khả năng xử lý trên máy. Network I/O cũng là yếu tố quan trọng, đặc biệt với build sạch hoặc pipeline không có cache cục bộ.

Các tài nguyên có quan hệ với nhau. Ví dụ, tăng số worker có thể làm CPU bận hơn nhưng đồng thời tăng số JVM và lượng RAM cần thiết. Nếu RAM không đủ, hệ điều hành phải swap hoặc kết thúc tiến trình; khi đó build có thể chậm hơn dù CPU có nhiều lõi.

## 2. CPU: số lõi, mức song song và tranh chấp

CPU thực hiện phần tính toán của build. Những công việc thường tiêu thụ CPU gồm:

- Biên dịch source Java thành bytecode.
- Chạy annotation processor hoặc compiler plugin.
- Phân tích mã tĩnh, kiểm tra chất lượng và tạo báo cáo.
- Chạy unit test hoặc integration test.
- Nén, ký và đóng gói artifact.
- Chạy các tác vụ sinh mã hoặc công cụ ngoài.

### Số lõi không phải là số worker tối ưu

Một CPU có nhiều lõi có thể xử lý nhiều công việc đồng thời. Tuy nhiên, mỗi worker/task có thể cần RAM và I/O riêng. Nếu máy có 8 lõi logic, không có nghĩa đặt 32 worker sẽ nhanh hơn 8 worker.

Mức song song phù hợp phụ thuộc vào:

- Số lõi vật lý và logic.
- CPU quota mà container hoặc CI runner được cấp.
- Mức sử dụng CPU của từng task.
- Bộ nhớ tiêu thụ trên mỗi worker hoặc test JVM.
- Mức đọc/ghi của các task.
- Các tiến trình khác đang chạy trên máy.

Một task biên dịch có thể sử dụng nhiều CPU trong một khoảng thời gian; một task khác có thể chủ yếu chờ disk hoặc network. Tăng worker chỉ có lợi nếu còn tài nguyên để chạy thêm công việc và dependency graph có đủ task độc lập.

### CPU quota trong container và CI

Máy ảo hoặc container có thể nhìn thấy nhiều CPU logic nhưng chỉ được cấp một phần CPU quota. Ví dụ, host có 32 lõi nhưng container chỉ được giới hạn tương đương 4 CPU. Nếu công cụ build tự nhận diện số CPU không đúng với quota, nó có thể tạo quá nhiều worker.

Hãy kiểm tra giới hạn thực tế của runner/container, không chỉ xem cấu hình máy host. Trên Linux có thể xem thông tin CPU và cgroup; trong CI, thông số runner thường được công bố trong cấu hình job hoặc tài liệu nền tảng.

### CPU utilization cao chưa chắc là vấn đề

CPU sử dụng gần 100% trong lúc biên dịch có thể là dấu hiệu tốt: máy đang tận dụng CPU. Chỉ số này đáng lo khi đi cùng thời gian build dài bất thường, nhiệt độ cao, giảm xung, hàng đợi công việc lớn hoặc tác vụ quan trọng bị tranh chấp.

Ngược lại, CPU thấp trong khi build vẫn chậm có thể cho thấy task đang chờ I/O, mạng, lock, tiến trình con hoặc một tác vụ tuần tự chưa thể chạy song song.

## 3. Điều chỉnh mức song song trong Gradle

Gradle có thể thực hiện các task độc lập song song khi build được cấu hình phù hợp. Có hai khái niệm cần phân biệt:

- **Song song giữa các project:** cho phép các project độc lập trong multi-project build được thực thi đồng thời.
- **Worker/task parallelism:** giới hạn số worker mà Gradle có thể sử dụng cho các công việc.

### Bật parallel project execution

Có thể bật bằng command line:

    ./gradlew build --parallel

Hoặc trong gradle.properties:

    org.gradle.parallel=true

Tùy chọn này hữu ích trong multi-project build khi các project có thể được xử lý độc lập. Gradle vẫn phải tuân thủ quan hệ phụ thuộc; những task có dependency chưa hoàn tất không thể chạy trước.

Không phải mọi build đều tăng tốc khi bật parallel. Nếu project có nhiều phụ thuộc chéo, task không độc lập hoặc máy đã bão hòa CPU/RAM, lợi ích có thể nhỏ hoặc âm.

### Giới hạn số worker

Có thể đặt giới hạn worker:

    ./gradlew build --max-workers=4

Hoặc trong gradle.properties:

    org.gradle.workers.max=4

Giới hạn này điều khiển số worker Gradle dùng để thực thi công việc song song. Nó không có nghĩa mọi task luôn có một process riêng, và cũng không thay thế việc giới hạn heap của từng JVM hoặc process fork.

Hãy bắt đầu bằng giá trị gần với CPU quota thực tế, sau đó đo thời gian và RAM. Với task nặng bộ nhớ, số worker tối ưu có thể thấp hơn số lõi CPU.

### Worker API và process riêng

Plugin có thể dùng Gradle Worker API để chạy công việc trong process hiện tại, classloader riêng hoặc process worker riêng. Mỗi lựa chọn có chi phí CPU, RAM và khởi tạo khác nhau. Một plugin tạo nhiều process con có thể làm tổng mức tiêu thụ tài nguyên vượt xa số worker nhìn thấy ở một cấu hình đơn giản.

Khi điều tra số tiến trình Java tăng cao, hãy xem cả Gradle daemon, compiler daemon nếu có, test worker và process do plugin tạo ra.

## 4. Điều chỉnh mức song song trong Maven

Maven hỗ trợ parallel build ở cấp reactor bằng tùy chọn -T:

    mvn -T 1C clean verify

Trong đó 1C biểu thị mức song song theo số lõi mà Maven nhận diện. Có thể chỉ định số thread cụ thể:

    mvn -T 4 clean verify

Parallel reactor hữu ích khi các module độc lập hoặc có quan hệ phụ thuộc được mô tả chính xác. Maven vẫn tuân thủ thứ tự reactor dependency. Một số plugin hoặc goal có thể không an toàn khi chạy song song; cần kiểm tra tài liệu plugin và kết quả build trước khi bật rộng rãi.

### Song song trong Surefire

Maven Surefire có cơ chế fork JVM và chạy test song song. Ví dụ:

    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
        <configuration>
            <forkCount>2</forkCount>
            <reuseForks>true</reuseForks>
        </configuration>
    </plugin>

forkCount điều khiển số fork JVM cho test theo cấu hình plugin. Có thể dùng biểu thức theo CPU như 1C ở các phiên bản Surefire hỗ trợ.

Nếu vừa chạy reactor với -T vừa tăng forkCount, tổng số JVM test có thể tăng đáng kể. Ví dụ 4 module chạy song song và mỗi module có 2 test fork có thể tạo nhiều tiến trình test cùng lúc. Cần tính tổng tài nguyên, không chỉ nhìn một thông số riêng lẻ.

## 5. RAM: heap, metaspace và tiến trình build

Build Java thường chạy trong một hoặc nhiều JVM. RAM được dùng cho:

- Heap của Gradle daemon hoặc Maven process.
- Metaspace chứa metadata của class.
- Code cache của JIT.
- Thread stack.
- Bộ nhớ native của compiler, ZIP, TLS và thư viện native.
- Heap của test JVM hoặc process fork.
- Bộ nhớ của các tiến trình ngoài như Node, Docker hoặc công cụ phân tích.

Vì vậy, tổng RAM cần thiết lớn hơn giá trị heap được cấu hình. Nếu mỗi JVM được cấp heap 2 GB và có 5 JVM cùng chạy, chỉ riêng heap tối đa đã có thể lên tới 10 GB, chưa tính metaspace, native memory và hệ điều hành.

### Heap không phải tổng bộ nhớ của process

Tùy chọn -Xmx giới hạn heap tối đa của JVM:

    -Xmx2g

Nó không giới hạn toàn bộ resident memory của process ở 2 GB. Process còn dùng metaspace, stack, code cache và native memory. Đặt -Xmx quá cao trên máy ít RAM có thể khiến nhiều JVM cạnh tranh và hệ điều hành bắt đầu swap hoặc kết thúc process.

### Dấu hiệu thiếu RAM

Các triệu chứng phổ biến:

- JVM báo java.lang.OutOfMemoryError: Java heap space.
- JVM báo Metaspace nếu vùng class metadata không đủ.
- Build process bị hệ điều hành hoặc container OOM killer kết thúc.
- Máy dùng swap/pagefile liên tục và phản hồi chậm.
- GC hoạt động thường xuyên, thời gian pause tăng.
- Test fork thất bại ngẫu nhiên khi nhiều module chạy đồng thời.

Không phải mọi OutOfMemoryError đều được giải quyết bằng cách tăng -Xmx. Cần xác định loại lỗi, process nào hết bộ nhớ và liệu có memory leak hoặc số worker quá cao hay không.

## 6. Cấu hình bộ nhớ cho Gradle daemon

Gradle daemon là JVM chạy Gradle build và có thể được tái sử dụng giữa các lần chạy. Có thể cấu hình JVM arguments trong gradle.properties:

    org.gradle.jvmargs=-Xmx3g -XX:MaxMetaspaceSize=1g -Dfile.encoding=UTF-8

Ví dụ trên đặt heap tối đa 3 GB và giới hạn metaspace 1 GB. Đây chỉ là giá trị minh họa; cần điều chỉnh theo RAM được cấp, số worker và loại build.

Không nên tăng heap vô hạn. Hãy theo dõi GC, mức sử dụng bộ nhớ và thời gian build. Nếu daemon dùng heap thấp nhưng các test JVM hoặc compiler process mới là nơi hết bộ nhớ, thay đổi org.gradle.jvmargs có thể không giải quyết đúng vấn đề.

Có thể dừng daemon khi cần giải phóng process hoặc chẩn đoán trạng thái:

    ./gradlew --stop

Lệnh này dừng các Gradle daemon liên quan tới Gradle user home hiện tại. Lần build sau có thể khởi động daemon mới.

## 7. Bộ nhớ cho test JVM và worker process

Test có thể chạy trong JVM riêng. Nếu test suite dùng nhiều dữ liệu, mock lớn, framework nặng hoặc khởi tạo application context, test JVM có thể cần heap riêng.

Gradle:

    tasks.withType(Test).configureEach {
        maxHeapSize = "1g"
    }

Thiết lập này áp dụng giới hạn heap cho test process do task quản lý. Nếu chạy nhiều test worker song song, tổng bộ nhớ có thể gần bằng số worker nhân với mức heap tối đa, cộng overhead.

Maven Surefire:

    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
        <configuration>
            <argLine>-Xms256m -Xmx1g</argLine>
            <forkCount>1</forkCount>
            <reuseForks>true</reuseForks>
        </configuration>
    </plugin>

argLine truyền JVM arguments cho forked test process. Cấu hình này không nhất thiết thay đổi heap của Maven process chính.

Nếu test chạy song song, hãy cân đối forkCount, số module song song và heap của từng test JVM. Tăng forkCount trong khi RAM đã đầy thường làm build kém ổn định hơn.

## 8. Ước lượng ngân sách RAM

Một cách lập kế hoạch đơn giản là ước lượng tổng bộ nhớ đỉnh:

    Tổng RAM cần
      ≈ Gradle/Maven process
      + số worker × RAM trung bình mỗi worker
      + test JVM/process con
      + hệ điều hành và dịch vụ nền
      + phần dự phòng

Ví dụ máy CI có 16 GB RAM. Nếu hệ điều hành và agent cần khoảng 3 GB, còn khoảng 13 GB cho build. Nếu Gradle daemon dùng tối đa 3 GB, ba test JVM mỗi process có thể dùng 2 GB và các process khác cần thêm 1 GB, tổng đã gần 10 GB trước phần native overhead. Chạy thêm nhiều worker có thể đẩy máy tới giới hạn.

Không nên dùng công thức này như một phép đo chính xác. Heap tối đa không đồng nghĩa với heap thực tế luôn được sử dụng, còn native memory thay đổi theo tải. Hãy dùng số liệu đỉnh từ CI hoặc hệ điều hành để hiệu chỉnh.

## 9. Disk I/O: đọc source và ghi đầu ra

Build thường thực hiện nhiều thao tác file:

- Quét source tree và tài nguyên.
- Đọc JAR, POM và metadata dependency.
- Ghi class file và generated source.
- Tạo JAR/WAR và các archive tạm.
- Ghi test report, log và kết quả phân tích.
- Đọc/ghi local build cache và Gradle/Maven cache.

Ổ SSD thường có độ trễ thấp và xử lý nhiều thao tác ngẫu nhiên tốt hơn HDD. Tuy nhiên, tốc độ thực tế còn phụ thuộc loại SSD, dung lượng trống, filesystem, controller, mã hóa, antivirus và tải I/O đồng thời.

### Dấu hiệu disk là nút thắt

- CPU không bận nhưng build vẫn chậm.
- Disk active time hoặc queue length cao.
- Nhiều task cùng đọc/ghi thư mục build và cache.
- Build chậm rõ rệt khi chạy trên HDD hoặc volume mạng.
- Thời gian giải nén dependency hoặc tạo archive chiếm tỷ lệ lớn.

Nếu disk là nút thắt, tăng worker có thể làm tình hình tệ hơn vì nhiều task tranh cùng một thiết bị.

### Dung lượng trống cũng quan trọng

Build cần chỗ cho:

- Source và checkout.
- Local dependency cache.
- Gradle user home và Maven local repository.
- Thư mục build của các module.
- File tạm, báo cáo và artifact.
- Docker layer hoặc image nếu pipeline sử dụng container.

Khi dung lượng gần đầy, thao tác ghi có thể thất bại hoặc hiệu năng giảm. CI runner dùng chung cần dọn workspace và cache theo chính sách phù hợp, nhưng không nên xóa dữ liệu cần thiết giữa các job đang chạy.

## 10. File system, antivirus và workspace

Hiệu năng file phụ thuộc filesystem và cách workspace được đặt.

Một số yếu tố cần xem:

- Workspace trên ổ cục bộ hay network share.
- Filesystem có hỗ trợ thao tác metadata nhanh không.
- Antivirus hoặc endpoint security có quét mọi file .class, JAR và file tạm không.
- File watcher hoặc indexing service có hoạt động quá mức không.
- Cache và workspace có nằm trên volume được mã hóa hoặc đồng bộ cloud không.

Trên Windows, antivirus có thể quét các file mới tạo trong build directory hoặc cache. Không nên tự ý tắt bảo vệ của tổ chức; hãy phối hợp với quản trị viên để đánh giá chính sách exclusion an toàn cho thư mục build/cache nếu số liệu cho thấy đây là nút thắt.

Tránh đặt thư mục build tạm trên ổ mạng có độ trễ cao nếu build tạo hàng nghìn file nhỏ. Với CI, dùng workspace cục bộ và cache có chủ đích thường dễ dự đoán hơn.

## 11. Network I/O và repository

Build sạch thường cần tải:

- Plugin và dependency.
- POM, Gradle Module Metadata và repository metadata.
- Sources hoặc Javadoc nếu được yêu cầu.
- Toolchain hoặc distribution của Gradle/Maven Wrapper.
- Artifact từ remote build cache.

Nếu mạng chậm, DNS lỗi, TLS handshake lâu hoặc repository manager quá tải, build có thể chờ lâu dù CPU và RAM còn dư.

### Local dependency cache

Gradle lưu dependency cache trong Gradle User Home; Maven mặc định dùng local repository dưới ~/.m2/repository. Khi dependency đã có sẵn và còn hợp lệ, công cụ có thể tránh tải lại nội dung.

Cache giúp giảm tải mạng nhưng không nên được coi là nguồn bảo đảm tính tái lập. Version động, SNAPSHOT hoặc changing module vẫn có thể cần kiểm tra metadata theo chính sách cập nhật.

### Repository manager nội bộ

Tổ chức có thể dùng repository manager làm proxy/cache cho Maven Central và các nguồn công khai. Cấu hình này giúp giảm request ra Internet, quản lý quyền truy cập và kiểm soát nguồn dependency.

Nếu nhiều runner đồng thời tải cùng một dependency, proxy cache có thể giảm tải mạng. Tuy nhiên, repository manager cần đủ CPU, RAM, disk và băng thông để không trở thành nút thắt chung.

### Remote Build Cache

Remote Build Cache có thể giảm lượng công việc tính toán nhưng cũng tạo thêm network I/O. Nếu task output lớn hoặc mạng chậm, tải cache có thể mất nhiều thời gian hơn chạy lại task tại chỗ.

Hãy so sánh thời gian cache lookup/download với thời gian thực thi task. Một cache hit không tự động đồng nghĩa với thời gian ngắn hơn trong mọi trường hợp.

## 12. Tác động kết hợp giữa CPU, RAM và I/O

Các tài nguyên không hoạt động độc lập.

Ví dụ tăng số worker:

    Số worker tăng
        |
        +--> Nhiều task chạy đồng thời
        |       |
        |       +--> CPU sử dụng tăng
        |       +--> RAM cho process/thread tăng
        |       +--> Disk I/O tăng
        |
        +--> Có thể giảm thời gian chờ nếu còn tài nguyên
                |
                +--> Nếu quá tải: GC/swap/I/O queue tăng
                         |
                         +--> Tổng thời gian build tăng

Một build có thể chuyển từ CPU-bound sang memory-bound khi tăng song song. Ví dụ, 4 worker có thể chạy tốt trên máy 8 GB RAM, nhưng 12 worker tạo nhiều test JVM và khiến máy swap. Kết quả là CPU không còn được tận dụng hiệu quả vì process liên tục chờ bộ nhớ và I/O.

Do đó, tối ưu song song phải xét đồng thời số lõi, RAM, disk và network.

## 13. Xác định nút thắt bằng số liệu

Không nên thay đổi nhiều thông số cùng lúc rồi kết luận nguyên nhân từ một lần build. Hãy đo một baseline, thay đổi một yếu tố, sau đó đo lại trong điều kiện tương đương.

### Ghi thời gian build

Với Gradle:

    ./gradlew clean build --profile

Tùy phiên bản Gradle, task profile tạo báo cáo thời gian cấu hình và thực thi task trong thư mục báo cáo của build. Build Scan cũng có thể cung cấp thông tin chi tiết nếu tổ chức bật plugin và dịch vụ tương ứng.

Với Maven, có thể bật log thời gian hoặc dùng plugin/CI timing phù hợp. Log debug:

    mvn -X clean verify

cung cấp nhiều thông tin nhưng không phải lúc nào cũng là cách tốt nhất để đo hiệu năng vì log quá chi tiết có thể làm thay đổi tải và kích thước output.

### Theo dõi CPU và RAM trên Windows

PowerShell có thể liệt kê tiến trình Java:

    Get-Process java,javaw -ErrorAction SilentlyContinue |
      Select-Object Id,CPU,WorkingSet64,PrivateMemorySize64

WorkingSet64 biểu thị lượng RAM hiện đang nằm trong working set của process; PrivateMemorySize64 biểu thị bộ nhớ riêng của process. Các số liệu này không tương đương heap JVM.

Có thể mở Task Manager hoặc Resource Monitor để xem:

- CPU theo process.
- Memory/commit.
- Disk active time, response time và queue.
- Network throughput.

### Theo dõi trên Linux

Các lệnh thường dùng:

    top
    htop
    free -h
    vmstat 1
    iostat -xz 1
    df -h

Chúng giúp xem CPU, RAM, swap, hoạt động block device, độ trễ I/O và dung lượng đĩa. Tùy hệ thống, iostat có thể cần gói sysstat.

### Theo dõi JVM

Nếu có JDK phù hợp, có thể dùng:

    jcmd <pid> GC.heap_info
    jcmd <pid> VM.flags
    jstat -gc <pid> 1000

Các lệnh này giúp quan sát heap, JVM flags và hoạt động GC của process Java. Hãy xác định đúng PID của Gradle daemon, Maven process hoặc test worker; các process có thể có cấu hình khác nhau.

## 14. Phân biệt CPU-bound, memory-bound và I/O-bound

### CPU-bound

Dấu hiệu:

- CPU bận liên tục.
- RAM và disk còn đủ.
- Tăng worker trong giới hạn hợp lý có thể giảm thời gian.
- Các task compiler hoặc phân tích mã chiếm phần lớn thời gian.

Hướng xử lý:

- Dùng mức song song phù hợp với CPU quota.
- Tận dụng task graph độc lập.
- Bật incremental compilation và cache khi phù hợp.
- Giảm công việc phân tích hoặc sinh mã không cần thiết.
- Tránh chạy nhiều tiến trình nền nặng cùng lúc.

### Memory-bound

Dấu hiệu:

- Heap gần giới hạn hoặc GC thường xuyên.
- Có swap/pagefile hoặc container OOM.
- Build ổn định khi chạy ít worker nhưng lỗi khi chạy song song.
- Test fork thất bại khi số process tăng.

Hướng xử lý:

- Giảm max-workers, Maven -T hoặc test forkCount.
- Điều chỉnh heap cho đúng process bị thiếu bộ nhớ.
- Tăng RAM runner nếu có thể.
- Kiểm tra memory leak và dữ liệu test quá lớn.
- Tránh cấp heap tối đa quá cao cho mọi JVM.

### I/O-bound

Dấu hiệu:

- CPU thấp hoặc không được sử dụng hết.
- Disk queue/latency cao hoặc network chậm.
- Tải dependency, giải nén hoặc ghi nhiều file chiếm thời gian.
- Tăng worker làm disk contention nặng hơn.

Hướng xử lý:

- Dùng SSD cục bộ và workspace phù hợp.
- Tận dụng dependency cache và repository proxy.
- Đặt remote cache gần runner và đo lợi ích thực tế.
- Giảm thao tác file lặp lại hoặc tạo nhiều file tạm.
- Kiểm tra antivirus, network share và dung lượng trống.

Một build có thể đồng thời chịu nhiều nút thắt. Hãy xác định phần chiếm thời gian lớn nhất trước khi tối ưu.

## 15. Tối ưu CI runner và container

CI thường chạy nhiều job trên máy ảo hoặc container có giới hạn tài nguyên. Một job build có thể bị giới hạn:

- CPU quota hoặc số vCPU.
- RAM tối đa.
- Disk quota và tốc độ volume.
- Network throughput.
- Số process hoặc thread.
- Thời gian chạy tối đa của job.

### Tránh cấu hình dựa trên host thay vì quota

Nếu container chỉ được cấp 4 CPU và 8 GB RAM, không nên cấu hình build như thể nó có 32 CPU và 64 GB RAM. Kiểm tra công cụ có nhận diện đúng giới hạn container hay không. Khi cần, đặt rõ max-workers và JVM heap theo giới hạn job.

### Không cộng dồn quá nhiều lớp song song

Một pipeline có thể đồng thời:

- Chạy nhiều module/project song song.
- Chạy test fork song song.
- Chạy nhiều test thread trong mỗi fork.
- Chạy nhiều job CI trên cùng host.

Mỗi lớp song song đều có chi phí. Hãy tính tổng số process và thread có thể hoạt động cùng lúc. Với runner nhỏ, mức song song vừa phải thường ổn định hơn.

### Tách job theo đặc tính tài nguyên

Có thể tách:

- Job compile/static analysis có xu hướng CPU-bound.
- Job integration test có thể cần RAM và dịch vụ ngoài.
- Job package/signing có thể cần I/O hoặc CPU.
- Job tải dependency/cache có thể bị giới hạn mạng.

Việc tách job chỉ hữu ích nếu chi phí checkout, khởi động và truyền artifact không lớn hơn lợi ích. Hãy đo tổng thời gian pipeline thay vì chỉ thời gian của từng job.

## 16. Tác động của Gradle daemon và Maven process

### Gradle daemon

Gradle daemon là process JVM chạy lâu dài để tái sử dụng trạng thái và tránh chi phí khởi động JVM ở các lần build. Nó có thể giữ heap, class metadata và một số dữ liệu trong bộ nhớ giữa các lần chạy.

Daemon giúp build lặp lại nhanh hơn, nhưng trên runner có RAM rất hạn chế, nhiều daemon hoặc nhiều job cùng chạy có thể làm tăng áp lực bộ nhớ. Có thể kiểm tra process Java và dừng daemon khi cần:

    ./gradlew --stop

Không nên tắt daemon mặc định chỉ vì thấy có process Java đang chạy. Hãy cân nhắc workload, số job và chi phí khởi động lại.

### Maven process

Maven thường chạy trong một JVM cho mỗi invocation, trừ khi có cơ chế wrapper hoặc daemon riêng của hệ sinh thái được sử dụng. Test plugin có thể fork thêm JVM. Maven JVM và test JVM có heap riêng, nên phải kiểm soát cả hai.

Maven JVM options có thể được cung cấp qua MAVEN_OPTS hoặc cấu hình phù hợp trong môi trường. Ví dụ:

    MAVEN_OPTS="-Xmx2g -XX:MaxMetaspaceSize=768m"

Trên Windows PowerShell, có thể đặt biến môi trường cho phiên terminal:

    $env:MAVEN_OPTS = "-Xmx2g -XX:MaxMetaspaceSize=768m"

Giá trị này chỉ là ví dụ; chọn theo RAM và số process thực tế.

## 17. Đo trước và sau khi thay đổi cấu hình

Một quy trình tối ưu thực tế:

1. Ghi nhận cấu hình runner: CPU quota, RAM, loại disk và giới hạn container.
2. Chạy build baseline trong điều kiện ổn định.
3. Ghi thời gian tổng, thời gian task, CPU peak, RAM peak, disk/network và số process.
4. Xác định nút thắt chính.
5. Thay đổi một thông số, ví dụ max-workers hoặc heap.
6. Chạy lại cùng commit và cùng cache condition.
7. So sánh cả thời gian lẫn độ ổn định.
8. Lặp lại với một vài giá trị hợp lý và ghi lại cấu hình tốt nhất.

Không nên so sánh build sạch với build cache nóng mà không ghi rõ. Một lần build có thể nhanh hơn vì dependency cache, Configuration Cache hoặc Build Cache được tái sử dụng, chứ không phải vì CPU/RAM được tối ưu.

Nên phân biệt:

- Build sạch, cache lạnh.
- Build tăng dần, cache nóng.
- Build với remote cache.
- Build sau khi thay đổi một tệp source.
- Build test hoặc integration test riêng.

## 18. Ví dụ điều chỉnh Gradle cho runner giới hạn tài nguyên

Giả sử CI runner có 4 CPU và 8 GB RAM. Một cấu hình khởi đầu thận trọng có thể là:

    # gradle.properties
    org.gradle.workers.max=3
    org.gradle.parallel=true
    org.gradle.jvmargs=-Xmx2g -XX:MaxMetaspaceSize=768m -Dfile.encoding=UTF-8
    org.gradle.caching=true

Nếu build tương thích, có thể bật thêm:

    org.gradle.configuration-cache=true

Đối với test task:

    tasks.withType(Test).configureEach {
        maxHeapSize = "1g"
        maxParallelForks = 1
    }

Đây chỉ là cấu hình ban đầu để đo, không phải công thức tối ưu cho mọi runner. Nếu task nặng RAM, giảm workers hoặc fork. Nếu CPU còn dư và RAM ổn định, có thể thử tăng workers. Nếu build bị I/O-bound, tăng song song thường không giải quyết gốc rễ.

## 19. Ví dụ điều chỉnh Maven cho runner giới hạn tài nguyên

Với runner có khoảng 4 CPU, có thể bắt đầu bằng:

    mvn -T 2 clean verify

Sau đó theo dõi CPU và RAM trước khi thử:

    mvn -T 1C clean verify

Đối với Surefire:

    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
        <configuration>
            <forkCount>1</forkCount>
            <reuseForks>true</reuseForks>
            <argLine>-Xmx1g</argLine>
        </configuration>
    </plugin>

Nếu nhiều module chạy song song, forkCount của mỗi module có thể nhân tổng số test JVM. Hãy bắt đầu với số fork thấp và chỉ tăng khi RAM còn dư và test suite thật sự có thể chạy độc lập.

## 20. Dung lượng, cache và dọn dẹp

Cache dependency và build output có thể chiếm dung lượng lớn. Việc xóa cache liên tục làm tăng network I/O và thời gian tải lại dependency. Ngược lại, để cache phát triển không giới hạn có thể làm đầy disk.

Một chính sách hợp lý cần:

- Giữ cache cần thiết để build lặp lại nhanh.
- Dùng cache cleanup hoặc retention policy phù hợp.
- Theo dõi dung lượng workspace và Gradle/Maven user home.
- Xóa output của job đã kết thúc theo chính sách CI.
- Không xóa cache đang được job khác sử dụng.
- Dùng remote cache khi có lợi ích và hạ tầng đáng tin cậy.

Lệnh Gradle clean thường xóa build output của project, không xóa toàn bộ Gradle dependency cache hoặc remote Build Cache. Maven clean xóa thư mục target của project, không xóa toàn bộ ~/.m2/repository.

## 21. Những sai lầm thường gặp

### Đặt worker bằng số lõi CPU mà không đo RAM

Task và test JVM có thể tiêu thụ nhiều RAM. Số worker bằng số lõi không đảm bảo máy đủ bộ nhớ.

### Tăng heap để chữa mọi lỗi build

Lỗi có thể đến từ metaspace, native memory, container limit, memory leak hoặc quá nhiều process. Tăng -Xmx có thể làm tình hình tệ hơn.

### Bật parallel ở mọi nơi

Một số task không độc lập hoặc plugin không an toàn khi chạy song song. Tăng concurrency có thể gây race condition, xung đột file hoặc lỗi không ổn định.

### Nhầm CPU thấp với CPU yếu

CPU thấp có thể do build đang chờ disk, mạng, lock hoặc dependency chưa sẵn sàng. Cần đo thời gian chờ và I/O.

### Bỏ qua dung lượng disk

Build có thể thất bại khi workspace, cache hoặc thư mục tạm hết dung lượng. Kiểm tra free space cùng với RAM/CPU.

### So sánh hai build trong điều kiện khác nhau

Build cache nóng, dependency cache, daemon và Configuration Cache có thể làm thay đổi thời gian. Phải ghi rõ điều kiện đo.

## 22. Checklist đánh giá máy build

| Hạng mục | Cần xác nhận |
| --- | --- |
| CPU | Số lõi, CPU quota, mức sử dụng và hiện tượng throttling |
| RAM | RAM được cấp, heap từng JVM, metaspace, native memory, swap và OOM |
| Worker | Gradle max-workers, parallel project execution, Maven -T |
| Test process | Gradle maxParallelForks, Surefire forkCount và heap test JVM |
| Disk | SSD/HDD, latency, queue, dung lượng trống và filesystem |
| Network | Độ trễ repository, băng thông, proxy và remote cache |
| Cache | Dependency cache, up-to-date, Build Cache, Configuration Cache |
| CI/container | CPU/RAM/disk quota, process limit và số job đồng thời |
| Đo lường | Baseline, peak resource usage, thời gian task và điều kiện cache |

## 23. Nguyên tắc tối ưu

- Đo trước khi thay đổi cấu hình.
- Điều chỉnh song song theo CPU quota và RAM, không chỉ theo số lõi.
- Giới hạn worker và test fork để tránh tạo quá nhiều JVM.
- Cấp heap cho đúng process đang thiếu bộ nhớ.
- Theo dõi metaspace, native memory và swap, không chỉ heap.
- Dùng SSD cục bộ cho workspace/cache nếu có thể.
- Kiểm tra network và repository manager khi build chờ tải dependency.
- Duy trì cache theo chính sách, tránh xóa cache không cần thiết.
- Tách job theo đặc tính tài nguyên khi tổng pipeline có lợi.
- So sánh build trong điều kiện giống nhau và kiểm tra độ ổn định qua nhiều lần chạy.

Máy build hoạt động tốt khi CPU, RAM, disk và network được cân bằng với đặc điểm của task. Tăng concurrency chỉ có lợi khi tài nguyên còn dư; tăng heap chỉ có ích khi đúng JVM đang thiếu heap; cache chỉ giúp khi kết quả có thể tái sử dụng và chi phí truy cập cache thấp hơn công việc phải làm lại. Đo đúng nút thắt rồi điều chỉnh từng yếu tố sẽ tạo ra build nhanh và ổn định hơn.
