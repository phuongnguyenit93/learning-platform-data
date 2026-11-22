# Tiến trình build chạy ở đâu và sử dụng môi trường nào

Khi chạy một lệnh Gradle, máy tính phải khởi động một hoặc nhiều tiến trình để đọc cấu hình build, phân giải dependency và thực thi các task. Những tiến trình này sử dụng một môi trường cụ thể: hệ điều hành, JVM, JDK, thư mục làm việc, biến môi trường, quyền truy cập file, mạng và tài nguyên phần cứng.

Môi trường build có thể là máy của lập trình viên, máy chủ CI, máy ảo hoặc container. Điều quan trọng là xác định **tiến trình Gradle thực sự chạy ở đâu**, **JVM nào chạy Gradle**, **JDK nào được dùng để biên dịch/chạy test**, và **các task có tạo tiến trình riêng hay không**. Những câu hỏi này giúp giải thích vì sao một build chạy được trên máy này nhưng thất bại trên máy khác.

## 1. Build không chạy bên trong ứng dụng Java

Build là hoạt động phát triển phần mềm diễn ra trước khi ứng dụng được chạy hoặc triển khai. Khi gõ:

~~~shell
./gradlew clean build
~~~

hoặc trên Windows:

~~~powershell
.\gradlew.bat clean build
~~~

lệnh này khởi chạy Gradle từ môi trường của máy đang thực hiện lệnh. Gradle đọc build script, tạo task graph, rồi thực hiện những công việc như biên dịch mã nguồn, chạy test và đóng gói artifact.

Ứng dụng Java được tạo ra là một sản phẩm của quá trình đó. Sau khi build xong, ứng dụng có thể được chạy trong một JVM khác, trên một máy khác hoặc trong một container khác.

Có thể phân biệt hai giai đoạn:

| Giai đoạn | Mục đích | Tiến trình điển hình |
|---|---|---|
| Build time | Biên dịch, kiểm thử, đóng gói, tạo tài liệu hoặc sinh mã | Gradle daemon, compiler process, test worker, tiến trình công cụ ngoài |
| Runtime | Chạy ứng dụng đã được đóng gói | JVM chạy ứng dụng, application server hoặc container runtime |

Ví dụ, Gradle có thể chạy trên máy phát triển để tạo `app.jar`. Sau đó `app.jar` được đưa lên máy chủ Linux và chạy bằng một JVM trên máy chủ. Hai môi trường này không cần giống nhau hoàn toàn. Chúng cần tương thích với yêu cầu của artifact và cách ứng dụng được triển khai.

Vì vậy, khi thấy lỗi build, cần điều tra môi trường chạy Gradle và các tiến trình con của nó trước. Không nên mặc định rằng lỗi đến từ JVM đang chạy ứng dụng ở môi trường production.

## 2. Những tiến trình tham gia khi chạy Gradle

Một lệnh Gradle thường đi qua một chuỗi tiến trình. Sơ đồ khái quát:

~~~text
Terminal / IDE / CI job
        |
        v
Gradle Wrapper script
        |
        v
Gradle client process
        |
        v
Gradle daemon (JVM chạy build)
        |
        +-------------------------+
        |                         |
        v                         v
Task chạy trong daemon      Tiến trình riêng
                            - test worker JVM
                            - JavaExec JVM
                            - worker process
                            - lệnh hệ điều hành
        |                         |
        +------------+------------+
                     |
                     v
             Build outputs
          class / report / JAR / ZIP
~~~

Không phải mọi build đều tạo ra đầy đủ mọi loại tiến trình trong sơ đồ. Cấu hình task và plugin quyết định tiến trình nào thực sự cần thiết.

### Gradle Wrapper và client process

**Gradle Wrapper** là bộ script đi kèm repository, thường gồm `gradlew`, `gradlew.bat` và cấu hình trong `gradle/wrapper/`. Wrapper giúp dự án chọn một phiên bản Gradle cụ thể mà người dùng không cần tự cài phiên bản đó trên toàn máy.

Khi chạy Wrapper:

1. Script xác định Java executable có thể dùng để khởi động Gradle.
2. Nếu Gradle distribution được yêu cầu chưa có trong Gradle User Home, Wrapper tải distribution từ URL được cấu hình.
3. Wrapper khởi chạy Gradle client và chuyển các tham số dòng lệnh cho Gradle.
4. Gradle kết nối đến daemon phù hợp hoặc khởi động daemon mới để thực hiện build.

Wrapper không phải là một máy chủ build độc lập. Nó là điểm khởi đầu giúp chọn và khởi chạy đúng Gradle distribution.

### Gradle daemon

**Gradle daemon** là một tiến trình JVM chạy nền để thực hiện các build. Daemon có thể được tái sử dụng cho những lần chạy tiếp theo nếu phiên bản Gradle, JVM và các điều kiện tương thích phù hợp.

Daemon giúp giảm thời gian khởi động vì Gradle không phải tạo lại toàn bộ JVM và nạp lại mọi thành phần từ đầu cho mỗi lệnh. Nó cũng có thể giữ một số dữ liệu trong bộ nhớ giữa các lần build.

Một số điểm cần nhớ:

- Daemon thường chạy dưới tài khoản người dùng đã khởi chạy build.
- Daemon chạy trên máy hoặc môi trường nơi Wrapper/Gradle được khởi chạy.
- Daemon sử dụng một JVM riêng cho Gradle build.
- Một daemon không nhất thiết được dùng chung cho mọi phiên bản Gradle hoặc mọi cấu hình JVM.
- Daemon có thể dừng khi không còn được sử dụng trong thời gian cấu hình cho phép, hoặc được dừng chủ động.

Lệnh kiểm tra các daemon của phiên bản Gradle hiện tại:

~~~shell
./gradlew --status
~~~

Dừng các daemon thuộc phiên bản Gradle hiện tại:

~~~shell
./gradlew --stop
~~~

Trên Windows, thay `./gradlew` bằng `gradlew.bat` hoặc `.\gradlew.bat` tùy shell.

### `--no-daemon` có nghĩa gì?

Tùy chọn `--no-daemon` yêu cầu Gradle không tái sử dụng daemon nền theo cách thông thường. Tuy nhiên, khi build cần một bộ JVM argument khác với tiến trình client, Gradle vẫn có thể khởi chạy một **single-use daemon** để thực hiện build rồi kết thúc tiến trình đó sau khi hoàn tất.

Do đó, không nên hiểu `--no-daemon` là cam kết rằng toàn bộ task sẽ chạy ngay trong tiến trình terminal ban đầu. Mục đích chính của tùy chọn là tránh tái sử dụng daemon nền giữa các lần gọi.

Trong CI, có thể lựa chọn daemon hoặc `--no-daemon` tùy chính sách và cách runner được quản lý. Nếu runner tồn tại lâu và chạy nhiều build tương thích, daemon có thể giúp tiết kiệm thời gian. Nếu mỗi job chạy trong một môi trường dùng một lần, lợi ích tái sử dụng daemon có thể nhỏ hơn.

## 3. Phân biệt JVM chạy Gradle và JDK dùng cho project

Đây là một trong những điểm quan trọng nhất của môi trường build.

Gradle cần một JVM để chạy chính nó. Trong khi đó, project Java có thể yêu cầu một JDK khác để biên dịch mã nguồn hoặc chạy test. Hai vai trò này có thể sử dụng cùng một JDK, nhưng không bắt buộc phải giống nhau.

| Thành phần | Dùng để làm gì? | Được chọn bởi |
|---|---|---|
| JVM chạy Gradle | Chạy Gradle client/daemon, build logic và phần lớn task action | Java dùng để khởi chạy Gradle, cấu hình JVM của Gradle |
| Java toolchain | Cung cấp JDK/compiler phù hợp để biên dịch, chạy test hoặc chạy công cụ Java | Khai báo toolchain trong build script và các toolchain đã cài/có thể tải |
| JVM chạy test | Chạy các test trong tiến trình test worker | Cấu hình test task và toolchain |
| JVM chạy ứng dụng | Chạy artifact sau khi build | Môi trường triển khai và lệnh khởi động ứng dụng |

Ví dụ, một dự án có thể chạy Gradle bằng JDK 21 nhưng dùng Java toolchain 17 để biên dịch và chạy test. Artifact được tạo ra khi đó cần tuân theo mức tương thích Java mà project đã cấu hình. Máy production có thể dùng một JVM tương thích với bytecode và thư viện của artifact.

### Java dùng để khởi chạy Gradle

Gradle cần một JVM đáp ứng yêu cầu của phiên bản Gradle đang sử dụng. Java được chọn để khởi chạy Wrapper thường được xác định từ môi trường của tiến trình gọi, chẳng hạn `JAVA_HOME` hoặc `PATH`; cấu hình JVM của Gradle cũng có thể chỉ định JVM cho build daemon.

Một số nguồn cấu hình thường gặp:

- `JAVA_HOME`: thường trỏ đến thư mục cài đặt JDK mà shell hoặc công cụ khởi chạy Java sử dụng.
- `PATH`: giúp hệ điều hành tìm lệnh `java` nếu không dùng đường dẫn tuyệt đối.
- `org.gradle.java.home`: có thể được cấu hình trong `gradle.properties` để chọn Java home cho Gradle build process.
- `org.gradle.jvmargs`: cấu hình JVM argument cho Gradle daemon, chẳng hạn heap size hoặc encoding.

Ví dụ một phần của `gradle.properties`:

~~~properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
~~~

Thiết lập này điều chỉnh JVM argument của Gradle daemon. Nó không tự động đặt Java toolchain cho mọi task biên dịch trong project.

### Java toolchain

**Java toolchain** cho phép project khai báo phiên bản Java cần dùng cho các công việc Java mà không buộc JVM chạy Gradle phải có cùng phiên bản đó.

Ví dụ với Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Cấu hình này yêu cầu Gradle chọn toolchain Java 17 phù hợp cho các task tích hợp với Java toolchain. Gradle tìm các JDK phù hợp đã có trên máy; nếu project cấu hình thêm toolchain resolver thì Gradle có thể tải toolchain theo cơ chế đó. Nếu không tìm được toolchain phù hợp và không có cơ chế tải, task cần toolchain sẽ không thể chạy.

Toolchain có thể được dùng cho:

- Biên dịch Java bằng compiler của JDK được chọn.
- Chạy test trong JVM có phiên bản phù hợp.
- Chạy Java application hoặc công cụ Java thông qua task được tích hợp với toolchain.

Cấu hình toolchain không có nghĩa là thay đổi JVM đang chạy Gradle daemon. Nếu Gradle daemon không tương thích với phiên bản Java cần thiết để chạy chính Gradle, việc khai báo toolchain không sửa được vấn đề đó.

### Source compatibility, target compatibility và toolchain

Ba khái niệm này liên quan nhưng không giống nhau:

- **Toolchain** chọn JDK/công cụ Java dùng cho task.
- **Source compatibility** quy định mức cú pháp/ngôn ngữ Java mà compiler chấp nhận.
- **Target compatibility** quy định mức bytecode đích mà compiler tạo ra trong những trường hợp tương ứng.

Với compiler Java hiện đại, có thể dùng tùy chọn `--release` để kiểm soát đồng thời mức ngôn ngữ, bytecode và API Java chuẩn được phép sử dụng. Cần cấu hình phù hợp với phiên bản Gradle và plugin của project.

Một toolchain mới hơn không tự động có nghĩa artifact sẽ yêu cầu đúng phiên bản JDK mới đó khi chạy. Điều này phụ thuộc vào mức bytecode, API và thư viện mà project thực sự sử dụng.

## 4. Task có thể chạy trong tiến trình nào?

Gradle daemon là môi trường thực thi chính cho phần lớn hoạt động cấu hình và điều phối build. Tuy nhiên, một số task có thể tạo tiến trình riêng hoặc dùng cơ chế cô lập để thực hiện công việc.

| Loại công việc | Môi trường thường gặp | Ví dụ |
|---|---|---|
| Build logic và task action thông thường | JVM của Gradle daemon | Cấu hình task, xử lý dữ liệu nhỏ |
| Java compilation | Compiler thuộc Java toolchain; mặc định thường được tích hợp với tiến trình build, tùy cấu hình fork | `compileJava` |
| Kiểm thử | JVM test worker riêng | `test` |
| Chạy ứng dụng Java | JVM riêng | `JavaExec`, task `run` |
| Worker API | Có thể dùng cùng tiến trình, classloader cô lập hoặc process riêng tùy chế độ | Tác vụ xử lý song song |
| Lệnh hệ điều hành | Tiến trình hệ điều hành con | `Exec`, gọi shell script hoặc công cụ ngoài |

### Test worker

Task `Test` của Gradle chạy test trong một hoặc nhiều JVM test worker riêng. Điều này giúp cô lập test khỏi JVM của Gradle daemon và cho phép cấu hình số tiến trình test song song.

Ví dụ:

~~~groovy
tasks.test {
    maxParallelForks = 2
}
~~~

Cấu hình trên cho phép tối đa hai test process chạy song song cho task tương ứng, tùy số worker và tài nguyên Gradle có thể cấp. Đây là số tiến trình test, không phải số Gradle daemon.

Vì test chạy trong JVM riêng, lỗi chỉ xuất hiện khi chạy test có thể liên quan đến JVM của test worker, system property, environment variable hoặc classpath của test. Không phải mọi vấn đề test đều là lỗi JVM chạy Gradle.

### JavaExec và tiến trình hệ điều hành

Task `JavaExec` chạy một lớp Java main trong một JVM riêng. Ví dụ:

~~~groovy
tasks.register('runSample', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.SampleApplication'
}
~~~

Khi task này chạy, Gradle điều phối việc khởi động một Java process với classpath và tham số đã cấu hình. JVM của ứng dụng mẫu là tiến trình con, tách biệt với Gradle daemon.

Task `Exec` có thể khởi chạy một chương trình bất kỳ của hệ điều hành, chẳng hạn script, compiler native hoặc công cụ đóng gói. Khả năng chạy thành công phụ thuộc vào executable có sẵn, quyền truy cập, biến môi trường và quy tắc của hệ điều hành.

### Worker API

Gradle Worker API cho phép plugin thực hiện công việc theo các chế độ cô lập khác nhau:

- **No isolation**: công việc chạy trong môi trường JVM hiện tại của Gradle.
- **Classloader isolation**: công việc được cô lập bằng classloader riêng.
- **Process isolation**: công việc chạy trong worker process riêng.

Mức cô lập ảnh hưởng đến classpath, bộ nhớ, vòng đời tiến trình và cách chia sẻ trạng thái. Không nên giả định rằng mọi worker đều là một JVM mới; phải xem isolation mode mà plugin sử dụng.

## 5. Môi trường build gồm những gì?

Môi trường build không chỉ là phiên bản Java. Nó là tập hợp các điều kiện mà Gradle và các task nhìn thấy trong lúc thực thi.

### Hệ điều hành và kiến trúc máy

Gradle chạy trong hệ điều hành nơi tiến trình được khởi chạy: Windows, Linux hoặc macOS. Các task cũng chịu ảnh hưởng từ kiến trúc CPU, filesystem và các công cụ có sẵn.

Một số khác biệt thường gây lỗi:

- Đường dẫn Windows thường dùng dấu `\`, trong khi Linux/macOS thường dùng dấu `/`.
- Hệ thống file có thể phân biệt chữ hoa/chữ thường khác nhau. Một tên file chỉ khác chữ hoa/chữ thường có thể hoạt động trên máy này nhưng xung đột trên máy khác.
- Quyền thực thi script và quyền đọc/ghi file khác nhau giữa các hệ điều hành.
- Script shell như `.sh` không tự chạy được bằng PowerShell nếu không có môi trường tương thích.
- Native library hoặc executable được build cho một hệ điều hành/kiến trúc có thể không chạy ở môi trường khác.
- Locale, timezone, charset và line ending có thể làm thay đổi output của một số task.

Để build ổn định, nên dùng API và task của Gradle thay vì phụ thuộc không cần thiết vào một lệnh riêng chỉ có trên một hệ điều hành. Nếu phải gọi công cụ ngoài, cần xác định rõ công cụ đó được cài ở đâu và phiên bản nào.

### Thư mục làm việc và filesystem

Build sử dụng một số vùng lưu trữ có vai trò khác nhau:

| Vị trí | Vai trò |
|---|---|
| Thư mục project | Chứa source code, build script và tài nguyên do dự án quản lý |
| `build/` | Chứa output sinh ra trong project, thường gồm class, report và archive |
| Project `.gradle/` | Chứa dữ liệu Gradle gắn với project, chẳng hạn trạng thái và cache nội bộ |
| Gradle User Home | Chứa Gradle distribution, dependency cache, daemon data, log, init script và cấu hình người dùng |

Gradle User Home mặc định thường là thư mục `.gradle` trong home directory của người dùng. Có thể đổi vị trí bằng biến môi trường `GRADLE_USER_HOME`.

Trên Windows, home directory thường nằm dưới thư mục profile của người dùng; trên Linux/macOS thường là thư mục home. Không nên nhầm Gradle User Home với thư mục `build/` của project:

- Xóa `build/` thường xóa output của project.
- Xóa cache trong Gradle User Home có thể khiến Gradle phải tải lại distribution hoặc dependency.
- Thay đổi Project `.gradle/` có thể làm mất trạng thái/cache gắn với project và khiến một số bước phải tính lại.

Đường dẫn tương đối trong build script thường được diễn giải theo project hoặc theo đối tượng file mà task sử dụng. Nếu task phụ thuộc vào current working directory của shell, hãy xác định rõ thư mục chạy lệnh. Có thể chọn project directory rõ ràng bằng tùy chọn `-p`/`--project-dir`.

### Biến môi trường và Gradle properties

Biến môi trường được tiến trình khởi chạy cung cấp cho Gradle và các tiến trình con theo quy tắc của hệ điều hành. Build script có thể đọc biến môi trường để lấy cấu hình như endpoint, chế độ chạy hoặc thông tin xác thực.

Các biến thường gặp:

| Biến | Vai trò thường gặp |
|---|---|
| `JAVA_HOME` | Chỉ định Java installation cho công cụ khởi chạy Java |
| `PATH` | Danh sách thư mục để hệ điều hành tìm executable |
| `GRADLE_USER_HOME` | Chọn Gradle User Home |
| `CI` | Một số CI provider đặt biến này để nhận diện môi trường CI |
| `ORG_GRADLE_PROJECT_name` | Cách truyền project property tên `name` qua environment variable |

Gradle còn có các cách truyền cấu hình riêng:

- `-Pname=value` truyền project property.
- `-Dname=value` truyền system property cho JVM/Gradle theo quy tắc tương ứng.
- `gradle.properties` lưu cấu hình Gradle hoặc project properties.
- `ORG_GRADLE_PROJECT_name=value` có thể được dùng để cung cấp project property qua môi trường.

Ví dụ:

~~~shell
./gradlew -PdeploymentEnv=staging build
~~~

Build script có thể đọc project property `deploymentEnv` để chọn cấu hình phù hợp. Với thông tin nhạy cảm, nên dùng secret store của CI hoặc cơ chế quản lý credential phù hợp, tránh ghi mật khẩu/token vào source code hoặc log.

Cần phân biệt **environment variable**, **system property** và **project property**. Chúng có nguồn cung cấp và phạm vi khác nhau; tên giống nhau không làm chúng trở thành cùng một loại dữ liệu.

### Mạng và dependency repository

Khi build cần một dependency chưa có trong cache, Gradle phải truy cập repository để lấy metadata và artifact. Do đó môi trường build có thể cần:

- Kết nối mạng đến Maven repository hoặc plugin repository.
- Proxy phù hợp nếu mạng nội bộ yêu cầu proxy.
- Credential hợp lệ cho repository riêng.
- Chứng chỉ TLS và cấu hình trust phù hợp.
- Quyền truy cập các dịch vụ mà task tùy chỉnh gọi đến.

Chế độ offline:

~~~shell
./gradlew --offline build
~~~

yêu cầu Gradle chỉ dùng dependency đã có trong cache. Nếu một dependency hoặc metadata cần thiết chưa được cache, build có thể thất bại. Offline mode không tải dependency mới và cũng không đảm bảo mọi task tùy chỉnh đều chạy được, vì task có thể cần truy cập mạng riêng.

## 6. Build chạy trên máy lập trình viên, IDE, CI hay container?

Cùng một repository có thể được build ở nhiều môi trường. Cách Gradle thực thi vẫn dựa trên process và JVM, nhưng máy chủ sở hữu các process và filesystem sẽ khác nhau.

### Máy lập trình viên

Khi chạy Wrapper từ terminal, build thường diễn ra trên máy cá nhân:

~~~text
Laptop
  ├── Terminal
  ├── JDK
  ├── Gradle Wrapper
  ├── Gradle daemon
  ├── Project files
  └── build/
~~~

Build sử dụng tài nguyên, quyền truy cập file, biến môi trường, cấu hình proxy và dependency cache của người dùng đó. Vì mỗi lập trình viên có thể cài JDK, IDE, shell và công cụ khác nhau, build chạy được trên một máy chưa chắc chạy được trên máy khác.

Dùng Gradle Wrapper, Java toolchain và cấu hình dependency rõ ràng giúp giảm khác biệt giữa các máy.

### IDE

IntelliJ IDEA, Eclipse hoặc VS Code có thể gọi Gradle để đồng bộ project, chạy task hoặc kiểm thử. Khi dùng Gradle Wrapper, IDE có thể sử dụng Wrapper distribution của repository.

Ví dụ:

~~~text
IDE
  |
  +--> Gradle Wrapper
          |
          +--> Gradle daemon
                  |
                  +--> compile/test/package
~~~

IDE là nơi người dùng khởi tạo thao tác; nó không nhất thiết là tiến trình thực hiện toàn bộ build. Gradle daemon vẫn có thể là tiến trình JVM riêng. IDE cũng có thể dùng một JDK riêng để chạy chính IDE; JDK đó không tự động đồng nghĩa với JDK của Gradle daemon hoặc Java toolchain.

Khi IDE báo lỗi khác terminal, hãy kiểm tra IDE đang chọn Gradle distribution nào, Gradle JVM nào, project JDK nào và có đang dùng Wrapper hay bản Gradle cài toàn máy hay không.

### CI runner

Trong CI, build chạy trên máy hoặc môi trường runner do nền tảng CI cung cấp. Ví dụ tổng quát:

~~~text
Git push / Pull request
        |
        v
CI workflow
        |
        v
Runner được cấp phát
        |
        +--> Checkout source
        +--> Chọn JDK
        +--> Chạy Gradle Wrapper
        +--> Test và package
        +--> Lưu artifact / report
~~~

Runner có thể là máy ảo dùng một lần, container hoặc máy tự quản lý (self-hosted runner). Khi job kết thúc, môi trường dùng một lần có thể bị hủy. Khi đó daemon, file tạm và cache cục bộ cũng không còn, trừ khi pipeline chủ động lưu hoặc khôi phục chúng.

Một CI pipeline thường cần xác định rõ:

1. Phiên bản JDK dùng để chạy Gradle.
2. Phiên bản Gradle thông qua Wrapper.
3. Toolchain cần cho compile/test.
4. Dependency repository và credential.
5. Biến môi trường, system property và project property.
6. Số worker, heap và giới hạn CPU/RAM của runner.
7. Những output nào cần lưu thành artifact hoặc báo cáo.

Self-hosted runner có thể giữ lại cache và công cụ giữa các job, nhưng cũng có nguy cơ tích lũy trạng thái cũ hoặc cấu hình khác nhau giữa các lần chạy. Runner dùng một lần sạch hơn nhưng thường cần chiến lược cache để giảm thời gian tải dependency.

### Container

Nếu lệnh Gradle được chạy bên trong container, các tiến trình Gradle và tiến trình con chạy trong môi trường container đó. Container cung cấp filesystem, process namespace, biến môi trường, user và giới hạn tài nguyên theo cấu hình container.

~~~text
Máy host
  |
  +--> Container runtime
          |
          +--> Container
                  ├── JDK
                  ├── Gradle Wrapper
                  ├── Gradle daemon
                  ├── Source mount / checkout
                  └── build/
~~~

Trong mô hình này, build không tự động sử dụng JDK đã cài trên host. Nó dùng JDK nhìn thấy bên trong container. Nếu source được mount từ host, output có thể xuất hiện trên filesystem host thông qua mount; nếu không, output có thể chỉ nằm trong filesystem container cho đến khi được copy ra hoặc đóng gói.

Container giúp chuẩn hóa một phần môi trường như OS image, JDK và công cụ. Tuy nhiên, container vẫn cần được cấu hình rõ ràng: image tag hoặc digest, user, mount, network, proxy, credential và giới hạn tài nguyên. Dùng tag thay đổi theo thời gian có thể khiến cùng một pipeline nhận image khác ở những lần chạy khác nhau.

## 7. Remote cache không đồng nghĩa với remote build execution

Một build có thể tương tác với dịch vụ từ xa mà task vẫn chạy trên máy hiện tại. Cần phân biệt:

- **Dependency repository** cung cấp dependency và plugin.
- **Remote build cache** lưu hoặc cung cấp output task đã được cache.
- **Remote build execution** chuyển việc thực thi task sang một môi trường máy khác thông qua hạ tầng hỗ trợ phù hợp.

Ví dụ, khi task có thể lấy output hợp lệ từ remote build cache, Gradle tải output đó về thay vì thực hiện lại action trên máy hiện tại. Điều này không có nghĩa task vừa được chạy trên máy chủ cache.

Gradle hỗ trợ cơ chế build cache; hệ thống remote execution/distributed execution có thể cần nền tảng hoặc plugin bổ sung. Không nên mặc định rằng chỉ cần cấu hình một remote cache là toàn bộ build sẽ chạy trên server.

Sự phân biệt này hữu ích khi điều tra hiệu năng:

- Build nhanh vì dependency đã có cache: giảm thời gian tải dependency.
- Task hiện `FROM-CACHE`: output được lấy từ build cache.
- Task chạy trong worker process: vẫn có thể là process trên cùng máy.
- Task được remote execution: cần có hạ tầng thực sự điều phối việc thực thi ở máy khác.

## 8. Tài nguyên và giới hạn của môi trường

Build tiêu thụ CPU, RAM, dung lượng đĩa, file descriptor/handle và kết nối mạng. Khi build chạy trong container hoặc CI runner, các tài nguyên này có thể bị giới hạn bởi nền tảng.

Một số cấu hình thường liên quan:

| Cấu hình | Tác động |
|---|---|
| `org.gradle.jvmargs` | Bộ nhớ và JVM argument của Gradle daemon |
| `org.gradle.workers.max` | Giới hạn số worker lease Gradle sử dụng đồng thời |
| `org.gradle.parallel` | Cho phép Gradle thực hiện một số công việc/project song song khi đủ điều kiện |
| `maxParallelForks` | Số test process tối đa của một Test task |
| Container CPU/memory limits | Giới hạn tài nguyên mà tiến trình trong container có thể dùng |

Tăng số worker không phải lúc nào cũng làm build nhanh hơn. Nếu runner thiếu RAM, nhiều compiler/test process có thể tranh chấp bộ nhớ và khiến build chậm hoặc bị hệ điều hành/container dừng. Nếu disk chậm hoặc thiếu dung lượng, các task tạo nhiều output cũng có thể thất bại.

Khi gặp lỗi như `OutOfMemoryError`, process bị kill, timeout hoặc không thể tạo file, hãy đối chiếu giới hạn thực tế của môi trường với heap, số worker và số test process đang chạy. Không nên chỉ tăng `-Xmx` mà không kiểm tra tổng RAM mà tất cả process đang dùng.

## 9. Vì sao build chạy được trên máy này nhưng thất bại trên máy khác?

Một build phụ thuộc vào nhiều điều kiện ngoài source code. Các nguyên nhân thường gặp gồm:

| Khác biệt | Biểu hiện có thể gặp | Hướng kiểm tra |
|---|---|---|
| Gradle version | Plugin hoặc DSL không tương thích | Kiểm tra Wrapper và `./gradlew --version` |
| JVM chạy Gradle | Gradle không khởi động hoặc lỗi tương thích JVM | Kiểm tra `JAVA_HOME`, `org.gradle.java.home`, JVM daemon |
| Java toolchain | Không tìm thấy compiler/JDK yêu cầu | Kiểm tra toolchain được khai báo và các JDK cài đặt |
| Hệ điều hành | Script, path hoặc native executable không chạy | Kiểm tra lệnh, quyền file và đường dẫn |
| Environment variable | Build chọn sai endpoint hoặc thiếu cấu hình | Kiểm tra biến môi trường trong đúng terminal/runner |
| Credential/proxy | Không tải được plugin hoặc dependency riêng | Kiểm tra secret, proxy, TLS và repository |
| Cache | Máy này có dependency/output cũ, máy kia chưa có | Thử build sạch hoặc offline/online có kiểm soát |
| RAM/CPU/disk | Build timeout, bị kill hoặc thiếu bộ nhớ | Kiểm tra giới hạn runner/container và số worker |
| Locale/timezone/charset | Test hoặc output khác nhau | Chuẩn hóa encoding, locale và timezone nếu task phụ thuộc chúng |

Một build đáng tin cậy cần giảm phụ thuộc vào trạng thái ngầm của máy. Các biện pháp hữu ích gồm:

- Commit Gradle Wrapper và dùng Wrapper trong local/CI.
- Khai báo Java toolchain cho các công việc cần JDK cụ thể.
- Quản lý dependency version rõ ràng; cân nhắc dependency locking và dependency verification.
- Khai báo repository rõ ràng, không dựa vào dependency chỉ có trong máy cá nhân.
- Truyền cấu hình môi trường qua cơ chế có kiểm soát; không lưu secret trong source code.
- Chuẩn hóa OS image/container khi cần môi trường hệ điều hành cố định.
- Không dựa vào file tạm hoặc output chưa được khai báo của một lần build trước.
- Lưu report và artifact của CI để có thể kiểm tra kết quả sau khi runner kết thúc.

## 10. Cách xác định build đang dùng môi trường nào

Khi điều tra một build, nên xác định lần lượt phiên bản Gradle, JVM chạy Gradle, toolchain, daemon và môi trường của task bị lỗi.

### Kiểm tra Gradle và JVM

~~~shell
./gradlew --version
~~~

Lệnh này hiển thị phiên bản Gradle, JVM mà Gradle sử dụng và thông tin hệ điều hành. Đây là bước đầu tiên để biết build đang chạy bằng Gradle/JVM nào.

Kiểm tra Java mà shell tìm thấy:

Trên macOS/Linux:

~~~shell
echo "$JAVA_HOME"
which java
java -version
~~~

Trên PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command java
java -version
~~~

Kết quả `java -version` cho biết Java được tìm thấy qua shell hiện tại. Nếu Gradle có `org.gradle.java.home` hoặc IDE chọn Gradle JVM riêng, JVM thực tế chạy build có thể khác; hãy đối chiếu với `./gradlew --version`.

### Kiểm tra daemon

~~~shell
./gradlew --status
~~~

Lệnh này hiển thị trạng thái các daemon thuộc phiên bản Gradle hiện tại. Nếu vừa đổi JDK hoặc cấu hình JVM và nghi ngờ daemon cũ còn được tái sử dụng, có thể dừng daemon rồi chạy lại:

~~~shell
./gradlew --stop
./gradlew --version
~~~

### Kiểm tra Java toolchain

Với project đã áp dụng Java plugin, có thể xem các toolchain Gradle phát hiện:

~~~shell
./gradlew -q javaToolchains
~~~

Lệnh này giúp xác định JDK nào có sẵn để Gradle lựa chọn. Nếu task compile/test vẫn chọn không đúng toolchain mong muốn, chạy task liên quan với log thông tin:

~~~shell
./gradlew :app:compileJava --info
~~~

Thay `:app` bằng project path thực tế. Log `--info` thường cung cấp thêm thông tin về lựa chọn toolchain và quá trình thực thi. Tránh chia sẻ log có chứa URL nội bộ, username hoặc thông tin nhạy cảm.

### Kiểm tra task và môi trường thực thi

~~~shell
./gradlew :app:test --info
~~~

Có thể dùng log để xem task nào chạy, task nào được lấy từ cache hoặc bỏ qua, và một số thông tin về tiến trình. Nếu lỗi chỉ xảy ra ở test, cần kiểm tra cấu hình Test task, toolchain, JVM argument, system property, environment variable và test worker.

`--debug` tạo log chi tiết hơn, nhưng log debug có thể chứa dữ liệu nhạy cảm do plugin hoặc build script ghi ra. Chỉ sử dụng khi thật sự cần và phải kiểm tra log trước khi chia sẻ.

### Kiểm tra dependency và chế độ offline

Nếu lỗi xảy ra khi tải plugin hoặc thư viện, hãy kiểm tra repository, mạng, proxy và credential. Có thể thử:

~~~shell
./gradlew --offline build
~~~

Nếu offline build thành công, các dependency cần thiết đã có trong cache cho lần chạy đó; kết quả này không chứng minh repository hoặc kết nối mạng hiện tại hoạt động. Nếu offline build thất bại do thiếu dependency, hãy kiểm tra khả năng truy cập repository ở chế độ online.

## 11. Một ví dụ đối chiếu local và CI

Giả sử cùng một commit được build ở laptop và CI:

| Thành phần | Laptop | CI runner |
|---|---|---|
| Source code | Working tree local | Checkout commit |
| Gradle | Wrapper của repository | Wrapper của repository |
| JVM chạy Gradle | JDK đã chọn trên laptop | JDK được workflow cài/chọn |
| Java toolchain | JDK được Gradle phát hiện hoặc tải | JDK được runner cài hoặc toolchain resolver cung cấp |
| Gradle User Home | Cache của người dùng | Cache riêng của runner hoặc cache được khôi phục |
| Credential | Credential local | CI secrets/service account |
| Filesystem | Ổ đĩa local | Filesystem của runner/container |
| Output | Project `build/` | Project `build/`, sau đó upload artifact nếu cần |

Nếu laptop build thành công nhưng CI thất bại, hãy so sánh các cột theo thứ tự: commit/source, Wrapper, JVM, toolchain, repository/credential, OS và tài nguyên. Cách đối chiếu này thu hẹp phạm vi nguyên nhân nhanh hơn việc thay đổi ngẫu nhiên nhiều cấu hình.

Nếu cần tái hiện CI ở local, có thể dùng cùng JDK, cùng Wrapper và cùng container image với pipeline. Tuy vậy, cần nhớ rằng credential, network policy, CPU/RAM và filesystem vẫn có thể khác.

## 12. Những nhầm lẫn thường gặp

| Dễ nhầm | Cách hiểu đúng |
|---|---|
| Gradle chạy trong JVM của ứng dụng | Gradle chạy trong JVM của build process; ứng dụng được tạo ra có thể chạy trong JVM khác |
| JDK của IDE luôn là JDK của Gradle | IDE có thể có JDK riêng, còn Gradle JVM được chọn theo cấu hình Gradle/Wrapper |
| Java toolchain đổi JVM chạy Gradle | Toolchain chọn JDK cho các task được tích hợp; JVM chạy Gradle vẫn là cấu hình riêng |
| `--no-daemon` luôn chạy build trong terminal process | Gradle có thể dùng single-use daemon để đáp ứng JVM argument |
| Mọi task chạy trong Gradle daemon | Test, JavaExec, Exec và worker process có thể chạy trong tiến trình riêng |
| Container dùng JDK của host | Tiến trình trong container nhìn thấy JDK trong container, trừ khi được cung cấp qua mount/cấu hình |
| Remote build cache nghĩa là build chạy trên server | Cache có thể chỉ cung cấp output; task có thể không được thực thi lại |
| Local build thành công chứng minh CI sẽ thành công | CI có OS, JDK, credential, filesystem, mạng và tài nguyên riêng |
| Xóa `build/` là xóa toàn bộ Gradle cache | `build/`, project `.gradle/` và Gradle User Home là các vùng khác nhau |

Khi một task thất bại, hãy xác định process thực thi task đó trước. Sau đó xác định JVM/JDK mà process sử dụng, hệ điều hành và filesystem mà nó nhìn thấy, các biến môi trường cùng credential được cung cấp, rồi mới xem xét cấu hình task hoặc source code. Cách lần theo môi trường thực thi này giúp tìm ra nguyên nhân cụ thể và làm cho build nhất quán hơn giữa máy lập trình viên, IDE, CI và container.
