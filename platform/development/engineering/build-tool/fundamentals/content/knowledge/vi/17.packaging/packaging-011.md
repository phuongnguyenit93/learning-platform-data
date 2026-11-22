# Phân biệt đóng gói Java, tạo container image và triển khai

Đưa một ứng dụng Java từ máy phát triển đến môi trường chạy gồm nhiều bước. Trước tiên, mã nguồn được biên dịch và đóng gói thành artifact như JAR hoặc WAR. Sau đó, artifact có thể được đặt cùng runtime, thư viện và cấu hình cần thiết để tạo container image. Cuối cùng, image được chạy trong một môi trường cụ thể với cấu hình, mạng, tài nguyên, dữ liệu và chính sách vận hành phù hợp.

Ba công việc này có liên quan nhưng không thay thế cho nhau:

- **Đóng gói Java (packaging):** tạo artifact từ mã nguồn và tài nguyên, ví dụ JAR hoặc WAR.
- **Tạo container image:** tạo một image có thể chạy, gồm filesystem, runtime và ứng dụng, thường được mô tả bằng Dockerfile hoặc buildpack.
- **Triển khai (deployment):** đưa một phiên bản image/artifact vào môi trường đích, cấu hình cách chạy và quản lý vòng đời của ứng dụng.

```text
Mã nguồn + dependency + cấu hình build
                 |
                 v
          Build / Packaging
                 |
                 v
          JAR hoặc WAR
                 |
                 v
       Container image build
       (runtime + app + metadata)
                 |
                 v
          Image registry
                 |
                 v
        Deployment vào môi trường
                 |
                 v
       Container chạy và được vận hành
```

Ví dụ, `my-app-1.0.0.jar` là artifact Java. Một container image có thể chứa JAR đó cùng Java Runtime và lệnh khởi chạy. Khi triển khai, nền tảng chạy container tạo instance từ image, truyền biến môi trường, cấp tài nguyên, thiết lập mạng và theo dõi tình trạng ứng dụng.

Hiểu ranh giới giữa các bước giúp bạn biết nên xử lý lỗi ở đâu: lỗi biên dịch thuộc build, lỗi thiếu runtime dependency có thể thuộc packaging/image, còn lỗi kết nối database hoặc thiếu secret thường thuộc cấu hình triển khai và môi trường chạy.

## 1. Đóng gói Java tạo ra sản phẩm gì?

Đóng gói là bước biến output đã biên dịch và tài nguyên thành một artifact có định dạng phù hợp để sử dụng ở bước tiếp theo. Build tool như Gradle hoặc Maven điều phối biên dịch, xử lý tài nguyên, kiểm thử và tạo archive.

Các định dạng phổ biến:

| Artifact | Nội dung và mục đích thường gặp |
|---|---|
| JAR | Java classes, resources và metadata. Có thể là thư viện hoặc ứng dụng. |
| Thin JAR | JAR ứng dụng/thư viện không nhúng toàn bộ dependency bên ngoài; dependency được cung cấp riêng. |
| Fat/Uber JAR | Archive chứa ứng dụng và các dependency được gom hoặc được loader đặc biệt nạp. |
| Executable JAR | JAR có cơ chế khởi chạy, chẳng hạn manifest `Main-Class` hoặc loader do framework cung cấp. |
| WAR | Gói ứng dụng web theo quy ước Servlet, thường triển khai lên servlet container hoặc application server tương thích. |
| EAR | Gói ứng dụng enterprise Java theo mô hình máy chủ ứng dụng hỗ trợ EAR. |

Không phải mọi JAR đều chạy được bằng `java -jar`. Một JAR thư viện có thể chỉ chứa các lớp để ứng dụng khác sử dụng và không có `Main-Class`. Tương tự, WAR thường được triển khai vào web/application server chứ không được chạy như một ứng dụng JAR thông thường.

### Thin JAR và dependency

Một Thin JAR thường chỉ chứa lớp và tài nguyên của module. Dependency bên ngoài nằm trong repository hoặc thư mục riêng. Khi chạy ứng dụng, JVM phải tìm được JAR ứng dụng cùng toàn bộ thư viện runtime qua classpath, manifest hoặc script khởi chạy.

Ví dụ phân phối:

```text
my-app/
├── bin/
│   └── my-app
└── lib/
    ├── my-app-1.0.0.jar
    ├── http-client.jar
    └── json-core.jar
```

Thin JAR giúp giữ các thư viện riêng biệt, dễ nhìn thấy dependency và phù hợp với mô hình repository. Tuy nhiên, người phát hành phải bảo đảm thư mục `lib/` đầy đủ và classpath được thiết lập chính xác.

### Fat/Uber JAR

Fat JAR gom lớp của ứng dụng và dependency vào một archive hoặc dùng một layout cùng loader đặc biệt để nạp các JAR lồng bên trong. Cách này thuận tiện khi cần một artifact ứng dụng dễ phân phối.

Việc gom dependency có thể cần xử lý tài nguyên trùng, `META-INF/services`, chữ ký JAR, license và metadata của thư viện. Không nên tự giải nén tất cả JAR rồi ghi đè file trùng một cách tùy tiện.

### JAR và WAR

JAR phù hợp cho thư viện Java, ứng dụng chạy độc lập hoặc executable JAR của framework. WAR đóng gói web application theo cấu trúc được servlet container hiểu. Với WAR truyền thống, runtime server cung cấp servlet API và các dịch vụ mà ứng dụng cần; không nên đưa nhầm API do container cung cấp vào gói như một thư viện thông thường.

Việc chọn JAR hay WAR phụ thuộc cách ứng dụng được khởi chạy và môi trường đích. Đó là quyết định ở lớp packaging, trước khi chọn cách triển khai vật lý hoặc container.

## 2. Tạo artifact bằng Gradle và Maven

### Gradle

Với Java plugin, task `jar` tạo JAR từ output của source set `main`:

```shell
./gradlew clean test jar
```

Trên Windows:

```powershell
.\gradlew.bat clean test jar
```

JAR thường được tạo trong `build/libs/`. Tên file phụ thuộc tên project, version và cấu hình archive.

Nếu dự án dùng Application plugin, có thể khai báo lớp chính và tạo distribution chứa JAR, runtime dependency cùng script:

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'com.example.app.Main'
}
```

Các task `installDist`, `distZip` hoặc `distTar` tạo cấu trúc phân phối có thư mục `bin/` và `lib/`. Đây là gói ứng dụng Java có thể chạy; nó chưa phải container image.

Nếu dự án dùng plugin framework, chẳng hạn plugin tạo executable JAR, task đóng gói có thể khác `jar`. Hãy xem task và output thực tế của project thay vì giả định mọi dự án đều tạo cùng một loại archive.

### Maven

Maven dùng lifecycle để chạy các bước cần thiết. Với dự án đóng gói JAR:

```shell
mvn clean verify
```

Giai đoạn `package` tạo JAR; `verify` tiếp tục các bước xác minh được cấu hình trong lifecycle. Artifact thường nằm trong `target/`.

Trong `pom.xml`, loại artifact được xác định bởi `packaging`, ví dụ:

```xml
<packaging>jar</packaging>
```

hoặc:

```xml
<packaging>war</packaging>
```

Maven plugin tương ứng tạo archive theo packaging và cấu hình của project. Nếu dùng Spring Boot Maven Plugin, một task/goal riêng có thể tạo executable JAR khác với JAR thông thường.

### Kiểm tra artifact trước khi chuyển bước

Trước khi tạo image, hãy xác nhận:

- Build hoàn tất và các kiểm thử bắt buộc đã chạy.
- Artifact có đúng tên, version và định dạng mong muốn.
- Entry point đúng nếu artifact cần chạy độc lập.
- Dependency runtime được nhúng hoặc được cung cấp theo đúng mô hình.
- Tài nguyên cần thiết có mặt trong JAR/WAR hoặc được đưa vào distribution.
- Có thể truy vết artifact về commit, version và cấu hình build.

Có thể dùng `jar tf` để liệt kê nội dung JAR và kiểm tra `META-INF/MANIFEST.MF`. Với artifact WAR, có thể kiểm tra các thư mục `WEB-INF/classes`, `WEB-INF/lib` và metadata liên quan.

## 3. Container là gì?

Container là một tiến trình ứng dụng chạy trong môi trường được cô lập ở mức hệ điều hành, với filesystem, process namespace, network namespace và giới hạn tài nguyên do nền tảng container quản lý. Container dùng kernel của host, vì vậy nó không phải một máy ảo đầy đủ chứa kernel riêng.

Các khái niệm cần phân biệt:

- **Image:** mẫu bất biến theo nội dung, chứa filesystem và metadata để tạo container.
- **Container:** một instance đang chạy hoặc đã được tạo từ image.
- **Registry:** nơi lưu và phân phối image theo tên/tag/digest.
- **Runtime:** thành phần trên host hoặc node chịu trách nhiệm tạo và quản lý container, thường thông qua container engine/runtime.
- **Orchestrator:** hệ thống điều phối nhiều container, ví dụ Kubernetes, quản lý replica, scheduling, health và cập nhật.

Một image Java thường chứa:

1. Base filesystem và thư viện hệ thống cần thiết.
2. Java Runtime hoặc JDK nếu ứng dụng cần công cụ phát triển ở runtime.
3. JAR/WAR hoặc các file ứng dụng.
4. Entry point hoặc command để khởi chạy.
5. Metadata như working directory, user mặc định, port được mô tả và biến môi trường mặc định.

Image không tự chứa mọi thứ mà ứng dụng cần trong mọi môi trường. Database, message broker, secret, persistent data, DNS và các dịch vụ bên ngoài thường được cung cấp lúc triển khai.

## 4. Container image khác JAR ở điểm nào?

JAR là artifact Java. Container image là đơn vị đóng gói ở cấp hệ điều hành/runtime để có thể tạo container. Image có thể chứa một JAR, nhiều JAR, script, runtime và các file hệ thống.

| Tiêu chí | JAR/WAR | Container image |
|---|---|---|
| Phạm vi | Mã Java và tài nguyên ứng dụng | Filesystem, runtime, ứng dụng và metadata chạy |
| Runtime | JVM phải có sẵn ở môi trường chạy | Có thể mang theo Java Runtime trong image |
| Dependency hệ thống | Thường do môi trường cung cấp | Có thể cài/copy vào image khi build |
| Cấu hình theo môi trường | Có thể truyền khi chạy ứng dụng | Thường được inject qua environment, mount hoặc secret khi chạy container |
| Đơn vị triển khai | Artifact Java | Image được registry phân phối |
| Khả năng chạy | Cần JVM và classpath phù hợp | Cần container runtime/orchestrator tương thích |
| Tính bất biến | Artifact release nên bất biến | Image nên được nhận diện bằng digest và phát hành bất biến |

Một container image không thay thế JAR trong vòng đời phát triển. Artifact Java vẫn có thể được kiểm thử, lưu trong artifact repository, dùng làm đầu vào tạo image và phân phối theo các cách khác nhau.

## 5. Dockerfile: mô tả cách tạo image

Dockerfile là tập chỉ thị mô tả các lớp và metadata của image. Một ví dụ đơn giản dùng JAR đã được build sẵn:

```dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app

COPY build/libs/my-app-1.0.0.jar /app/app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Ý nghĩa:

- `FROM` chọn base image có Java Runtime 21.
- `WORKDIR` đặt thư mục làm việc mặc định trong image.
- `COPY` đưa artifact đã build vào image.
- `EXPOSE` mô tả cổng mà ứng dụng dự kiến lắng nghe; chỉ thị này không tự publish cổng ra host.
- `ENTRYPOINT` khai báo tiến trình chính của container bằng dạng exec, giúp JVM nhận tín hiệu hệ điều hành trực tiếp hơn so với shell wrapper không cần thiết.

Tạo image từ thư mục có Dockerfile:

```shell
docker build -t example/my-app:1.0.0 .
```

Chạy container và ánh xạ cổng:

```shell
docker run --rm -p 8080:8080 example/my-app:1.0.0
```

`-p 8080:8080` ánh xạ cổng 8080 trên host đến cổng 8080 trong container. Ứng dụng phải thực sự lắng nghe trên interface phù hợp bên trong container, thường là `0.0.0.0`, thì kết nối từ ngoài container mới đến được.

Lệnh `docker build` tạo image. Lệnh `docker run` tạo và khởi chạy container từ image. Hai thao tác này tương ứng với hai giai đoạn khác nhau.

## 6. Build artifact trước hay build image trực tiếp?

Có hai mô hình phổ biến:

### Mô hình A: build artifact trước, sau đó tạo image

```text
Source code
    |
    v
Gradle/Maven build
    |
    v
JAR/WAR artifact
    |
    v
docker build
    |
    v
Container image
```

Ưu điểm:

- Artifact Java có thể được kiểm thử và lưu riêng trước khi đóng image.
- Cùng một artifact có thể được dùng cho nhiều loại môi trường triển khai.
- Tách trách nhiệm giữa build Java và đóng gói container.
- Dễ truy vết artifact và image nếu lưu checksum/metadata.

Mô hình này thường phù hợp với pipeline CI/CD đã có artifact repository.

### Mô hình B: multi-stage build

Dockerfile có thể thực hiện cả build Java lẫn tạo runtime image. Stage đầu dùng JDK và build tool; stage sau chỉ chứa runtime và artifact.

Ví dụ với Gradle Wrapper:

```dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace

COPY gradlew .
COPY gradle ./gradle
COPY settings.gradle build.gradle ./
COPY src ./src

RUN chmod +x gradlew && ./gradlew --no-daemon clean test jar

FROM eclipse-temurin:21-jre
WORKDIR /app

COPY --from=build /workspace/build/libs/my-app-1.0.0.jar /app/app.jar

USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Ví dụ giả định tên artifact cố định là `my-app-1.0.0.jar`, dự án không cần file build bổ sung và task `jar` tạo JAR có thể chạy bằng `java -jar`. Nếu dự án dùng executable task khác, có dependency runtime ngoài hoặc cần file cấu hình bổ sung, hãy điều chỉnh stage build và nội dung copy.

Stage `build` chứa JDK và các công cụ cần để biên dịch. Stage cuối chỉ nhận JAR từ stage trước và sử dụng JRE/runtime image. Vì Docker chỉ đưa filesystem của stage cuối vào image cuối, compiler và cache build không cần nằm trong runtime image.

### Lợi ích của multi-stage build

- Giảm kích thước và số công cụ có trong runtime image.
- Tránh đưa source code, build cache và JDK không cần thiết vào production image.
- Giữ một Dockerfile mô tả được cả quy trình build và runtime.
- Có thể dùng stage riêng để kiểm thử, tạo artifact hoặc tạo image cuối.

Multi-stage build không tự bảo đảm build có thể tái lập. Vẫn cần khóa version base image, Gradle/Maven, plugin, dependency và kiểm soát nguồn đầu vào.

## 7. Chọn base image Java

Base image cung cấp hệ điều hành tối thiểu và Java runtime cần thiết. Khi chọn image, hãy cân nhắc:

- **Phiên bản Java:** phải tương thích với bytecode và API mà ứng dụng sử dụng.
- **JDK hay JRE:** runtime image thường chỉ cần JRE; ứng dụng có thể cần JDK nếu dùng công cụ như `jcmd`, compiler runtime hoặc native tooling.
- **Kích thước:** image nhỏ giảm thời gian tải và dung lượng lưu trữ.
- **Hệ điều hành và libc:** một số thư viện native cần môi trường tương thích.
- **Cập nhật bảo mật:** base image cần được cập nhật và quét lỗ hổng.
- **Kiến trúc CPU:** image phải hỗ trợ `amd64`, `arm64` hoặc kiến trúc node triển khai.
- **Nguồn cung cấp:** ưu tiên image chính thức hoặc nguồn được tổ chức phê duyệt.

Không nên chọn image chỉ vì nó nhỏ nhất. Image quá tối giản có thể thiếu CA certificates, timezone data, font, shell hoặc thư viện native mà ứng dụng cần. Hãy kiểm tra ứng dụng trên chính image mục tiêu.

### Java version phải nhất quán

Giả sử ứng dụng được biên dịch bằng JDK 21 nhưng runtime image chỉ có Java 17. Nếu artifact dùng bytecode hoặc API chỉ có trong Java 21, ứng dụng có thể lỗi khi khởi chạy. Cần chọn runtime tương thích hoặc cấu hình compiler/toolchain để tạo bytecode mục tiêu phù hợp.

### JDK trong build stage, JRE trong runtime stage

Một mẫu phổ biến:

```dockerfile
FROM eclipse-temurin:21-jdk AS build
# Biên dịch và đóng gói ứng dụng

FROM eclipse-temurin:21-jre
# Chỉ chạy artifact
```

Đây là cách tách công cụ build khỏi môi trường chạy. Với ứng dụng native hoặc yêu cầu đặc biệt, lựa chọn runtime có thể khác.

## 8. Cấu hình ứng dụng khi tạo image và khi triển khai

Một nguyên tắc quan trọng là không đóng cứng cấu hình riêng của từng môi trường vào artifact hoặc image dùng chung. Image nên chứa chương trình và mặc định an toàn; cấu hình thay đổi giữa development, staging và production nên được truyền vào lúc chạy.

Ví dụ cấu hình theo môi trường:

| Cấu hình | Development | Production |
|---|---|---|
| Database host | localhost hoặc service dev | DNS/service endpoint production |
| Log level | DEBUG | INFO/WARN theo chính sách |
| Số kết nối pool | Nhỏ | Theo tải và giới hạn DB |
| Secret | Secret local/dev | Secret manager hoặc nền tảng triển khai |
| External API endpoint | Sandbox | Production endpoint |

### Biến môi trường

Ứng dụng Java có thể đọc cấu hình từ environment variables:

```java
String portValue = System.getenv().getOrDefault("APP_PORT", "8080");
int port = Integer.parseInt(portValue);
```

Trong Docker:

```shell
docker run --rm \
  -e APP_PORT=8080 \
  -p 8080:8080 \
  example/my-app:1.0.0
```

Biến môi trường phù hợp cho cấu hình không nhạy cảm hoặc tham chiếu đến secret. Không nên ghi mật khẩu thật vào Dockerfile bằng `ENV`, vì giá trị có thể xuất hiện trong metadata hoặc các lớp image.

### Secret và dữ liệu nhạy cảm

Secret như database password, API token, private key và credential không nên được copy vào image hoặc commit vào repository. Hãy dùng cơ chế secret của nền tảng chạy, secret manager hoặc file mount được cấp quyền phù hợp.

Ví dụ, container có thể đọc secret từ file được mount ở runtime. Cách mount cụ thể phụ thuộc Docker Compose, Kubernetes hoặc nền tảng triển khai. Cần hạn chế quyền đọc, kiểm soát vòng đời và không in secret vào log.

### Dữ liệu cần lưu lâu dài

Filesystem bên trong container có thể bị thay thế khi container được tạo lại. Dữ liệu cần giữ như database files, upload hoặc state nên nằm trong database, object storage hoặc persistent volume phù hợp. Không coi writable layer của container là nơi lưu dữ liệu lâu dài.

## 9. Tạo image có tính bảo mật và dễ vận hành

Container image là một phần của chuỗi cung ứng phần mềm. Một số thực hành quan trọng:

- Dùng base image được duy trì và cập nhật định kỳ.
- Ưu tiên image runtime nhỏ nhưng vẫn có đủ chứng chỉ, timezone và thư viện cần thiết.
- Chạy ứng dụng bằng user không có quyền root khi có thể.
- Không đưa compiler, package manager, source code hoặc credential không cần thiết vào runtime image.
- Giới hạn những file được copy bằng `.dockerignore`.
- Không dùng tag `latest` làm định danh duy nhất cho production release.
- Quét image và dependency, lưu kết quả kiểm tra theo build.
- Gắn metadata như version, commit SHA và build timestamp khi phù hợp.
- Tạo image từ artifact đã được xác định, kiểm thử và truy vết.
- Dùng image digest khi cần bảo đảm chính xác nội dung được triển khai.

### `.dockerignore`

File `.dockerignore` loại các file không cần gửi vào build context. Ví dụ:

```text
.git
.gradle
build
target
.idea
*.iml
*.log
.env
```

Danh sách cần phù hợp với Dockerfile. Nếu Dockerfile cần copy JAR đã build ở `build/libs/`, không được ignore toàn bộ `build/` trong mô hình build artifact trước. Ngược lại, nếu Dockerfile multi-stage tự build từ source, có thể loại build output cũ khỏi context để tránh gửi dữ liệu không cần thiết.

`.dockerignore` không thay thế `.gitignore`; hai file phục vụ hai phạm vi khác nhau. `.gitignore` kiểm soát file Git theo dõi, còn `.dockerignore` kiểm soát file được gửi vào Docker build context.

### Chạy bằng user không phải root

Ví dụ trong Dockerfile:

```dockerfile
RUN useradd --system --uid 10001 appuser
USER 10001
```

Lệnh tạo user phụ thuộc base image; image dựa trên Alpine có thể dùng công cụ khác. Trước khi chuyển sang user không root, hãy bảo đảm thư mục ứng dụng, log hoặc thư mục tạm mà ứng dụng cần có quyền truy cập phù hợp.

### Tín hiệu dừng và tiến trình chính

Nên dùng exec form cho `ENTRYPOINT`:

```dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Dạng này giúp JVM trở thành tiến trình chính của container và nhận tín hiệu dừng. Khi ứng dụng nhận tín hiệu `SIGTERM`, nó nên dừng nhận request mới, hoàn tất công việc đang xử lý trong thời gian cho phép và đóng tài nguyên.

Nếu chạy qua shell script, script nên dùng `exec` để chuyển sang JVM hoặc chủ động chuyển tiếp tín hiệu. Một container có PID 1 không xử lý tín hiệu đúng có thể bị dừng đột ngột khi nền tảng triển khai thay thế instance.

## 10. Build image, gắn tag và lưu vào registry

Sau khi có Dockerfile và artifact, tạo image:

```shell
docker build -t registry.example.com/team/my-app:1.0.0 .
```

Tag thường gồm registry, namespace/repository và nhãn version. Ví dụ:

```text
registry.example.com/team/my-app:1.0.0
```

Tag giúp con người nhận diện phiên bản. Tuy nhiên, tag có thể được di chuyển sang image khác nếu registry cho phép ghi đè. Digest là định danh theo nội dung image và phù hợp khi cần pin chính xác image được triển khai.

Đăng nhập registry bằng cơ chế xác thực được tổ chức phê duyệt, sau đó push:

```shell
docker push registry.example.com/team/my-app:1.0.0
```

Trong CI, credentials nên được cấp qua secret của pipeline hoặc identity ngắn hạn. Không đưa token vào command line được lưu trong log hoặc vào Dockerfile.

### Tag release và tag commit

Một pipeline có thể gắn nhiều tag cho cùng image:

```text
my-app:1.0.0
my-app:git-a1b2c3d
```

Tag version phục vụ người dùng và vận hành. Tag commit giúp truy ngược image về source. Nếu dùng tag như `latest`, hãy coi nó là nhãn tiện dụng có thể thay đổi, không phải bằng chứng rằng image đang chạy chính xác là bản release mong muốn.

### Image digest

Sau khi push, registry cung cấp digest dạng:

```text
registry.example.com/team/my-app@sha256:<digest>
```

Triển khai bằng digest giúp xác định chính xác nội dung image. Pipeline có thể lưu tag để đọc thuận tiện và digest để triển khai, kiểm toán hoặc rollback.

## 11. Triển khai là gì?

Triển khai là quá trình đưa artifact hoặc image vào môi trường đích và làm cho ứng dụng sẵn sàng phục vụ công việc. Nó bao gồm nhiều quyết định ngoài việc tạo image:

- Chạy image nào và version/digest nào.
- Chạy bao nhiêu instance/replica.
- Cấp CPU, memory và giới hạn tài nguyên.
- Truyền cấu hình, secret và profile môi trường.
- Cấu hình cổng, service discovery, DNS và ingress/load balancer.
- Kết nối database, queue, cache và dịch vụ bên ngoài.
- Kiểm tra health/readiness và xử lý restart.
- Cập nhật phiên bản, theo dõi tiến trình và rollback khi cần.

Một image có thể được triển khai ở nhiều môi trường khác nhau bằng cách thay cấu hình runtime. Ví dụ cùng image `my-app@sha256:...` có thể chạy ở staging và production với database endpoint, secret, resource limit và số replica khác nhau.

### Các môi trường thường gặp

| Môi trường | Mục đích |
|---|---|
| Local development | Chạy ứng dụng trên máy lập trình viên để phát triển và debug. |
| Test/CI | Kiểm thử tự động, kiểm tra image và tích hợp. |
| Staging | Môi trường gần production để xác nhận trước khi phát hành. |
| Production | Phục vụ người dùng hoặc workload thực tế. |

Không nên tạo image khác nhau chỉ vì mỗi môi trường có database URL khác nhau. Hãy giữ image giống nhau và truyền cấu hình riêng khi triển khai, trừ khi có khác biệt kỹ thuật thực sự cần một artifact/image khác.

## 12. Chạy container đơn lẻ và triển khai nhiều instance

Để thử image trên máy local:

```shell
docker run --rm \
  --name my-app \
  -p 8080:8080 \
  -e APP_ENV=local \
  registry.example.com/team/my-app:1.0.0
```

Lệnh này tạo một container có tên `my-app`, ánh xạ cổng và truyền biến môi trường. Đây là cách kiểm tra cơ bản nhưng không cung cấp đầy đủ khả năng điều phối cho ứng dụng production nhiều instance.

Khi ứng dụng cần database hoặc nhiều dịch vụ đi kèm, Docker Compose có thể mô tả một nhóm container cho môi trường local/test. Ví dụ:

```yaml
services:
  app:
    image: example/my-app:1.0.0
    ports:
      - "8080:8080"
    environment:
      APP_ENV: local
      DB_HOST: db
    depends_on:
      - db

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app
      POSTGRES_PASSWORD: local-only-password
```

Đây là ví dụ dành cho môi trường local. Không dùng mật khẩu mẫu hoặc cấu hình này làm secret production. `depends_on` chủ yếu điều phối thứ tự khởi tạo container theo cấu hình Compose; nó không tự bảo đảm database đã sẵn sàng nhận kết nối nếu không có health check và điều kiện phù hợp.

Với production, hệ thống điều phối như Kubernetes hoặc nền tảng container managed có thể quản lý replica, scheduling, service discovery, rolling update, health check và restart policy.

## 13. Deployment trên Kubernetes ở mức khái niệm

Trong Kubernetes, một Deployment mô tả trạng thái mong muốn của nhóm Pod chạy image. Controller cố gắng duy trì số replica và cập nhật Pod theo chiến lược được cấu hình.

Một manifest minh họa:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
        - name: app
          image: registry.example.com/team/my-app:1.0.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: APP_ENV
              value: production
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
```

Trong ví dụ:

- `replicas: 2` yêu cầu duy trì hai Pod.
- `image` xác định container image sẽ chạy.
- `containerPort` mô tả cổng container dự kiến lắng nghe; nó không tự tạo Service hoặc mở cổng Internet.
- `env` truyền cấu hình runtime.
- `resources` khai báo CPU/memory requests và limits.

Để truy cập ứng dụng từ Pod khác hoặc bên ngoài cluster, thường cần Service và có thể cần Ingress/Gateway hoặc load balancer. Việc mở cổng và định tuyến là một phần của cấu hình triển khai.

### Health check: liveness và readiness

Kubernetes có các loại probe với mục đích khác nhau:

- **Liveness probe:** kiểm tra container có còn hoạt động theo tiêu chí của ứng dụng không. Nếu thất bại liên tục theo cấu hình, kubelet có thể restart container.
- **Readiness probe:** kiểm tra ứng dụng có sẵn sàng nhận traffic không. Nếu chưa sẵn sàng, Pod bị loại khỏi endpoint phục vụ của Service trong thời gian đó.
- **Startup probe:** dành cho ứng dụng khởi động lâu, giúp trì hoãn việc đánh giá liveness/readiness cho đến khi startup hoàn tất.

Ví dụ nếu ứng dụng có endpoint health:

```yaml
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8080
            initialDelaySeconds: 15
            periodSeconds: 20
```

Đường dẫn chỉ là ví dụ; ứng dụng phải thực sự cung cấp endpoint phù hợp. Không nên dùng readiness và liveness cùng một kiểm tra phụ thuộc database theo cách khiến sự cố database làm tất cả instance bị restart liên tục. Liveness nên trả lời tiến trình có còn sống và có thể tự phục hồi hay không; readiness trả lời instance có nên nhận traffic lúc này hay không.

### Secret và ConfigMap

Kubernetes có ConfigMap cho cấu hình không nhạy cảm và Secret cho dữ liệu nhạy cảm. Cần cấu hình RBAC, encryption at rest và quy trình quản lý secret phù hợp; không coi một object Secret mặc định là đã được bảo vệ đầy đủ chỉ vì dữ liệu được encode.

## 14. Rolling update, rollback và phát hành

Khi phát hành phiên bản mới, hệ thống triển khai cần thay thế instance cũ theo cách giảm gián đoạn. Một số chiến lược phổ biến:

- **Rolling update:** thay instance theo từng đợt, giữ một phần instance cũ phục vụ trong lúc cập nhật.
- **Blue/green:** duy trì hai môi trường, chuyển traffic từ môi trường cũ sang môi trường mới khi xác nhận sẵn sàng.
- **Canary:** đưa phiên bản mới đến một phần nhỏ traffic hoặc người dùng, theo dõi chỉ số trước khi mở rộng.

Lựa chọn phụ thuộc kiến trúc, nền tảng, khả năng tương thích database và mức độ rủi ro chấp nhận được.

### Rollback không chỉ là quay lại image cũ

Nếu ứng dụng mới thay đổi schema database, message format hoặc dữ liệu lưu trữ, quay lại image cũ có thể không đủ. Cần thiết kế migration theo hướng tương thích trong khoảng thời gian chuyển đổi, có kế hoạch backup và rollback dữ liệu nếu cần.

Một bản phát hành an toàn nên lưu:

- Image digest đã triển khai.
- Source commit và artifact version.
- Cấu hình triển khai tương ứng.
- Migration database đã chạy.
- Kết quả kiểm thử và phê duyệt.
- Chỉ số/log trong và sau rollout.

Khi có sự cố, nhóm cần biết chính xác image nào đang chạy và cách quay về phiên bản đã biết là tốt.

## 15. Pipeline CI/CD từ mã nguồn đến production

Một pipeline thường chia thành các giai đoạn rõ ràng:

```text
Commit / Pull Request
        |
        v
Compile + Unit Test + Quality checks
        |
        v
Package JAR/WAR
        |
        v
Publish artifact / lưu checksum
        |
        v
Build container image
        |
        v
Scan image + dependency + provenance
        |
        v
Push image vào registry
        |
        v
Deploy staging
        |
        v
Smoke / Integration / Acceptance tests
        |
        v
Approval hoặc policy gate
        |
        v
Deploy production
        |
        v
Monitor + rollback khi cần
```

Không phải dự án nào cũng cần mọi bước trong cùng một pipeline. Tuy nhiên, nên phân biệt rõ build, đóng gói, tạo image và triển khai để biết lỗi hoặc phê duyệt xảy ra ở giai đoạn nào.

### Artifact và image cần truy vết được

Một image nên liên hệ được với:

- Artifact Java đã đóng gói.
- Version của ứng dụng.
- Commit source.
- Version JDK/build tool/plugin.
- Dependency graph hoặc lock state.
- Base image và digest của base image.
- Kết quả test và security scan.

Khi cùng một image được đưa qua staging rồi production, bạn có thể giảm nguy cơ hai môi trường chạy hai bản build khác nhau. Thay đổi cấu hình môi trường được truyền ở thời điểm triển khai, còn image đã được xác định bằng digest.

### Không build lại tùy tiện cho từng môi trường

Nếu pipeline build lại source riêng cho staging và production, hai image có thể khác nhau do dependency động, base image thay đổi, timestamp hoặc cấu hình build. Mô hình đáng tin cậy thường tạo một image đã được kiểm tra, sau đó promote chính image đó qua các môi trường bằng cùng digest và cấu hình khác nhau.

## 16. Phân biệt lỗi ở packaging, image build và deployment

Khi ứng dụng không chạy, xác định giai đoạn lỗi giúp tránh sửa sai lớp.

| Biểu hiện | Giai đoạn nên điều tra | Ví dụ nguyên nhân |
|---|---|---|
| `javac` không biên dịch được | Build/packaging | Lỗi source, dependency compile, JDK không phù hợp. |
| Không tạo được JAR/WAR | Packaging | Task/goal sai, cấu hình archive hoặc plugin lỗi. |
| JAR chạy local nhưng container báo thiếu class | Image/runtime packaging | Thiếu runtime dependency hoặc sai classpath. |
| Container thoát ngay sau khi start | Image entrypoint/runtime | Sai `Main-Class`, command, Java version hoặc cấu hình bắt buộc. |
| Container chạy nhưng không truy cập được | Deployment/network | Port mapping, Service, ingress, bind address hoặc firewall. |
| Ứng dụng không kết nối được database | Deployment/configuration | DNS, credential, network policy, TLS hoặc database chưa sẵn sàng. |
| Pod bị restart liên tục | Runtime/health/resource | Crash, OOM, liveness probe quá gắt hoặc startup quá lâu. |
| Chạy được staging nhưng lỗi production | Environment/configuration | Secret, endpoint, quyền, resource limit hoặc dữ liệu khác nhau. |
| Rollback image nhưng lỗi vẫn còn | Data/protocol compatibility | Schema hoặc message đã thay đổi theo hướng không tương thích. |

### Các lệnh điều tra cơ bản

Xem image local:

```shell
docker images
```

Xem container:

```shell
docker ps -a
```

Xem log:

```shell
docker logs my-app
```

Xem cấu hình và trạng thái container:

```shell
docker inspect my-app
```

Với Kubernetes, các lệnh thường dùng:

```shell
kubectl get pods
kubectl describe pod <pod-name>
kubectl logs <pod-name>
kubectl get deployment my-app
kubectl rollout status deployment/my-app
```

Log cho biết ứng dụng in ra gì; `describe` và event giúp tìm lỗi scheduling, image pull, probe hoặc resource. Hãy kiểm tra đúng namespace và container nếu Pod có nhiều container.

## 17. Quản lý tài nguyên và hành vi JVM trong container

Container có thể được giới hạn CPU và memory. JVM cần nhận biết giới hạn đó để chọn heap và số luồng phù hợp. Các JDK hiện đại có hỗ trợ nhận biết container ở nhiều môi trường, nhưng cần kiểm tra phiên bản JDK và cờ JVM được dùng.

### Memory limit không phải heap limit

Nếu container có memory limit 512 MiB, không nên đặt `-Xmx512m` rồi kỳ vọng mọi thứ luôn an toàn. JVM còn cần native memory, metaspace, thread stack, code cache, direct buffer và các vùng khác. Heap cần thấp hơn giới hạn tổng để còn chỗ cho các thành phần này và phần đệm vận hành.

Có thể cấu hình heap bằng `-Xmx` hoặc tỷ lệ memory phù hợp, nhưng giá trị phải dựa trên đo đạc và tải thực tế. Hãy theo dõi RSS/container memory, GC, heap usage và OOM events.

### CPU limit và thread pool

CPU quota có thể ảnh hưởng số processor mà JVM nhìn thấy và cách framework tạo thread pool. Nếu ứng dụng tạo quá nhiều thread hoặc dùng pool theo số CPU host thay vì quota container, hiệu năng có thể kém hoặc context switching tăng. Kiểm tra CPU limit, JDK version và cấu hình executor/pool của ứng dụng.

### Shutdown grace period

Nền tảng thường gửi `SIGTERM` trước, chờ một khoảng thời gian rồi mới kill cưỡng bức nếu container chưa dừng. Ứng dụng cần có shutdown hook hoặc lifecycle handler để đóng server, flush log và hoàn tất công việc đang xử lý. Grace period phải đủ dài nhưng cũng cần có giới hạn để rollout không bị treo.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Tạo JAR là đã tạo container image | JAR là artifact Java; image còn chứa runtime/filesystem và metadata. |
| `EXPOSE 8080` tự mở cổng ra host | Đây là metadata mô tả cổng; cần publish/map port hoặc Service/Ingress. |
| Container là máy ảo có kernel riêng | Container chia sẻ kernel host và cô lập tiến trình/tài nguyên ở mức hệ điều hành. |
| Image và container là một | Image là mẫu; container là instance được tạo từ image. |
| Image chứa luôn database và dữ liệu ứng dụng | Database thường là dịch vụ riêng; dữ liệu lâu dài cần storage phù hợp. |
| Có `Main-Class` là JAR chắc chắn chạy được | Còn cần runtime dependency, Java version và cấu hình phù hợp. |
| Dockerfile chỉ cần copy JAR là đủ cho mọi ứng dụng | Cần đúng runtime, dependency, command, user, port và tài nguyên bổ sung. |
| Biến môi trường là nơi an toàn để lưu mọi secret | Environment có thể bị lộ qua process metadata/log; dùng secret mechanism phù hợp. |
| Tag image là bất biến | Tag có thể bị di chuyển; digest xác định nội dung image. |
| Triển khai chỉ là chạy `docker run` | Production còn cần cấu hình, mạng, health, replica, tài nguyên, rollout và monitoring. |
| Rollback image luôn khôi phục được hệ thống | Thay đổi database hoặc dữ liệu có thể không tương thích với image cũ. |
| Staging và production phải build hai image riêng | Thường nên promote cùng image đã kiểm tra và truyền cấu hình riêng theo môi trường. |

## 19. Quy trình thực hành từ Java đến container

Với một ứng dụng Java nhỏ, có thể thực hành theo thứ tự:

1. Tạo ứng dụng có lớp chính và một endpoint hoặc chức năng có thể quan sát.
2. Dùng Gradle hoặc Maven biên dịch, chạy test và tạo JAR/WAR.
3. Kiểm tra artifact, manifest, version và dependency runtime.
4. Viết Dockerfile sử dụng base image Java phù hợp.
5. Tạo `.dockerignore` dựa trên cách Dockerfile nhận artifact hoặc source.
6. Build image với tag có version.
7. Chạy container local, ánh xạ cổng và truyền cấu hình qua environment.
8. Xem log và kiểm tra container có thực sự phục vụ request không.
9. Thử chạy bằng user không phải root và giới hạn resource phù hợp.
10. Push image lên registry thử nghiệm, lưu tag và digest.
11. Triển khai vào staging với cấu hình riêng, secret và health check.
12. Chạy smoke/integration test, theo dõi log và metrics.
13. Thử rollout một phiên bản mới và xác định cách rollback về digest trước đó.

Trong môi trường thật, cần thêm quy trình phê duyệt, security scan, quản lý secret, backup dữ liệu và quan sát hệ thống theo chính sách của tổ chức.

## 20. Bài tập tình huống

**Tình huống 1: JAR chạy trên máy lập trình viên nhưng container báo thiếu class.**

Hãy kiểm tra JAR có phải Thin JAR không, dependency nào nằm trong `runtimeClasspath`, Dockerfile có copy thư mục `lib/` không và `ENTRYPOINT` có thiết lập classpath đúng không.

**Tình huống 2: Image build thành công nhưng container thoát ngay.**

Hãy đọc `docker logs`, kiểm tra command/entrypoint, Java version, manifest, biến môi trường bắt buộc và exit code. Image build thành công chỉ chứng minh image đã được tạo, không chứng minh ứng dụng khởi động thành công.

**Tình huống 3: Container chạy nhưng người dùng không truy cập được.**

Kiểm tra ứng dụng có bind `0.0.0.0` không, cổng bên trong container, `-p` hoặc Kubernetes Service, ingress/load balancer và firewall/network policy.

**Tình huống 4: Pod liên tục restart sau khi thêm liveness probe.**

Kiểm tra endpoint probe, startup time, timeout, failure threshold và log. Một probe quá gắt có thể restart ứng dụng trong lúc nó vẫn đang khởi động hoặc tạm thời quá tải.

**Tình huống 5: Rollback image nhưng ứng dụng vẫn lỗi khi truy cập database.**

Kiểm tra migration schema, dữ liệu đã được thay đổi, compatibility của query và version ứng dụng cũ với schema hiện tại. Rollback cần tính đến trạng thái dữ liệu, không chỉ image.

Sau khi hoàn thành bài thực hành, bạn cần phân biệt được artifact Java, container image và deployment; biết mỗi bước nhận đầu vào gì và tạo ra kết quả gì; giải thích được runtime, configuration và secret được cung cấp ở đâu; và có thể truy nguyên lỗi theo đúng giai đoạn. Đây là nền tảng để đóng gói và triển khai ứng dụng Java nhất quán từ máy phát triển đến môi trường vận hành.
