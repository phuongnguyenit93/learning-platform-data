# Ranh giới với build image, container và native executable

Khi một ứng dụng Spring Boot chạy được bằng `mvn spring-boot:run` hoặc nút Run trong IDE, công việc mới chỉ hoàn tất ở mức **chạy trong môi trường phát triển**. Để chuyển ứng dụng sang máy chủ, pipeline CI/CD hay nền tảng container, chúng ta còn phải quyết định sẽ đóng gói theo hình thức nào, dùng runtime nào và cần đưa những thành phần gì vào môi trường triển khai.

Ba khái niệm rất dễ bị nhầm:

- **Build image:** tạo một *container image*, thường tuân theo định dạng OCI, chứa ứng dụng cùng các thành phần cần thiết để chạy trong container.
- **Container:** một instance đang chạy của container image, có filesystem, network và các giới hạn tài nguyên riêng theo nền tảng container.
- **Native executable:** một chương trình được biên dịch thành mã máy cho hệ điều hành và kiến trúc cụ thể, thường bằng GraalVM Native Image trong hệ sinh thái Spring Boot hiện đại.

Một native executable **có thể nằm bên trong container image**, nhưng không bắt buộc. Ngược lại, một container image **có thể chứa executable JAR chạy trên JVM**, hoàn toàn không dùng Native Image. Vì vậy, “build image” và “build native” là hai quyết định **độc lập tương đối**, không phải hai tên gọi thay thế cho nhau.

Bài học trình bày ranh giới từ source code đến executable JAR, từ JAR đến container image, từ image đến container, và từ bytecode đến native executable. Phần cuối tổng hợp cách lựa chọn theo yêu cầu startup, bộ nhớ, thời gian build, khả năng tương thích và vận hành production.

## 1. Bản đồ tổng quan: từ source tới tiến trình chạy

Một dự án Spring Boot có thể đi theo nhiều con đường:

~~~text
                 Java/Kotlin source + resources
                              |
                              v
                        Compile / test
                              |
                  +-----------+-----------+
                  |                       |
                  v                       v
             JVM artifact           Spring AOT processing
           executable JAR                 |
                  |                       v
                  |                Native Image compile
                  |                       |
         +--------+--------+              v
         |                 |         Native executable
         v                 v              |
    java -jar         Build OCI image     +----------+
         |                 |              |          |
         v                 v              v          v
     JVM process     Container image  Run directly  Package in
                           |             on OS     OCI image
                           v                            |
                       Container                        v
                       running JVM                  Container
                                                   running native
~~~

Nhìn vào sơ đồ, có ít nhất bốn kết quả chạy khác nhau:

| Cách triển khai | Artifact chính | Có JVM runtime khi chạy? | Có container? |
|---|---|---|---|
| Chạy executable JAR trực tiếp | `app.jar` | Có | Không |
| Chạy JAR trong container | OCI image chứa JAR và Java runtime | Có | Có |
| Chạy native executable trực tiếp | Binary native | Không cần JVM runtime đầy đủ | Không |
| Chạy native executable trong container | OCI image chứa native binary và runtime OS phù hợp | Không cần JVM runtime đầy đủ | Có |

Đây là **bốn hình thức thực thi**, không phải bốn framework khác nhau. Business logic có thể dựa trên cùng mã nguồn Spring Boot, nhưng toolchain, startup characteristics và các ràng buộc runtime không hoàn toàn giống nhau.

### Ba câu hỏi cần tách ra

Trước khi chọn công cụ, hãy trả lời:

1. **Đóng gói ứng dụng thành gì?** JAR, WAR, native binary hay một tập artifact trung gian?
2. **Tiến trình chạy bằng runtime nào?** JVM hay executable native đã biên dịch ahead-of-time?
3. **Triển khai và cô lập bằng gì?** Chạy trực tiếp trên host, trong container hay theo một cơ chế khác?

Ví dụ “ứng dụng Spring Boot chạy Docker” chỉ trả lời phần thứ ba. Nó **chưa nói** ứng dụng chạy bằng JVM hay native binary.

## 2. Ranh giới đầu tiên: build project và chạy project

Trong IDE, developer có thể chạy trực tiếp main class:

~~~java
@SpringBootApplication
public class StoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

IDE thường tạo một classpath gồm output classes, resources và dependency JAR, sau đó chạy JVM với main class. Cách đó tiện cho development nhưng không phải hình thức duy nhất để triển khai.

Khi build để phát hành, thông thường cần một artifact có thể được quản lý, lưu trữ và chạy độc lập với source tree. Với Spring Boot, dạng phổ biến nhất là **executable JAR**.

### Build không đồng nghĩa chạy

- **Compile:** chuyển source code thành bytecode/compiled output.
- **Test:** thực thi kiểm thử theo cấu hình build.
- **Package:** gom class, resources và dependency thành artifact.
- **Run:** tạo một process từ artifact đã có.
- **Deploy:** đưa artifact và cấu hình đến môi trường mục tiêu, vận hành lifecycle và giám sát.

Một lệnh `package` thành công không chứng minh ứng dụng có thể kết nối database production, khởi động đúng profile hay đáp ứng health checks. Nó chứng minh một bước của chuỗi phát hành đã hoàn tất.

### Executable JAR không phải native executable

File `.jar` vẫn chứa Java bytecode và metadata. Khi chạy:

~~~bash
java -jar store-service.jar
~~~

hệ điều hành khởi động `java`, JVM nạp class và thực thi ứng dụng.

Ngược lại, một native executable thường được gọi trực tiếp:

~~~bash
./store-service
~~~

Nó là binary dành cho hệ điều hành/kiến trúc tương ứng, không phải file JAR được đổi tên.

## 3. Executable JAR của Spring Boot

Spring Boot hỗ trợ tạo executable JAR có cấu trúc giúp chạy ứng dụng cùng dependencies.

Một sơ đồ điển hình:

~~~text
store-service.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/store/...
│   │   └── application.yml
│   └── lib/
│       ├── spring-boot-...
│       ├── spring-context-...
│       └── ...
└── org/springframework/boot/loader/...
~~~

Cấu trúc chi tiết của launcher có thể khác giữa các thế hệ Spring Boot, nhưng ý tưởng chính là có một launcher hỗ trợ nạp application classes và dependency JARs được đóng gói bên trong artifact.

### Vì sao không chỉ tạo JAR Java thông thường?

Một JAR Java thường không tự mang toàn bộ thư viện mà ứng dụng phụ thuộc. Nếu chỉ đóng gói class của chính mình, khi triển khai bạn có thể phải chuẩn bị một classpath dài gồm nhiều JAR bên ngoài.

Spring Boot executable JAR giúp đơn giản hóa việc chạy:

~~~bash
java -jar store-service.jar
~~~

Điều này đặc biệt hữu ích khi chuyển artifact qua máy khác hoặc đặt JAR vào container.

### Manifest và launcher

Executable JAR thường có manifest chỉ đến launcher phù hợp và thông tin main class ứng dụng. Không nên tự suy đoán rằng `Main-Class` trong JAR luôn là `StoreApplication`; với Boot executable JAR, đó có thể là Boot launcher, còn application main class được chỉ định bằng metadata riêng.

Nếu cần kiểm tra, hãy dùng công cụ xem manifest của artifact thật. Không nên sửa tay manifest sau khi build vì dễ làm sai cơ chế launch hoặc gây khác biệt giữa build và deployment.

## 4. Tạo executable JAR bằng Maven hoặc Gradle

Với Maven và Spring Boot plugin phù hợp, có thể dùng:

~~~bash
mvn clean package
~~~

Spring Boot Maven plugin cung cấp goal `repackage` để biến JAR được build thông thường thành Spring Boot executable JAR. Việc goal này có được gắn vào lifecycle mặc định hay không phụ thuộc cấu hình plugin/parent của dự án.

Ví dụ plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Kết quả thường nằm dưới:

~~~text
target/store-service-0.0.1-SNAPSHOT.jar
~~~

Chạy:

~~~bash
java -jar target/store-service-0.0.1-SNAPSHOT.jar
~~~

Với Gradle có Spring Boot plugin, task phổ biến là:

~~~bash
./gradlew bootJar
~~~

Artifact thường nằm dưới:

~~~text
build/libs/
~~~

Chạy bằng JVM:

~~~bash
java -jar build/libs/store-service-0.0.1-SNAPSHOT.jar
~~~

Tên file chỉ là ví dụ; thực tế phụ thuộc `group`, `version`, archive configuration và cấu hình build.

### Không nhầm plain JAR và Boot executable JAR

Trong một số dự án Gradle/Maven, build có thể tạo:

- JAR thông thường để dùng như thư viện.
- Executable JAR dành cho ứng dụng Spring Boot.

Hai artifact phục vụ mục đích khác nhau. Một plain JAR có thể không chạy được bằng `java -jar` nếu manifest/classpath không phù hợp. Hãy xác định đúng artifact mà pipeline phát hành.

### WAR là một lựa chọn khác

Spring Boot cũng hỗ trợ đóng gói WAR cho những hệ thống cần triển khai vào servlet container bên ngoài, nếu ứng dụng được cấu hình phù hợp. Đây là một lựa chọn đóng gói khác với executable JAR, và **không tự đồng nghĩa** ứng dụng sẽ chạy trong OCI container hay native executable.

Đối với microservice và container deployment thông thường, executable JAR được sử dụng phổ biến vì đơn giản hóa process model. Nhưng hệ thống legacy có yêu cầu WAR vẫn có thể có lý do chính đáng.

## 5. Container image là gì?

Một **container image** là artifact bất biến về mặt nội dung tại một digest nhất định, thường được biểu diễn bằng các **layers** cùng metadata cấu hình process, environment, entrypoint, filesystem và kiến trúc mục tiêu.

Một image có thể chứa:

~~~text
Container image: example/store-service:1.0
├── Base filesystem / OS runtime components
├── Java runtime (nếu chạy JVM)
├── Dependencies hoặc application layers
├── Spring Boot executable JAR
└── Entrypoint / runtime metadata
~~~

Image được **build** trước rồi **run** thành một hoặc nhiều container. Một container là instance đang chạy, có trạng thái runtime, network namespace và tài nguyên do container engine quản lý.

### Image khác container

| Khái niệm | Hình dung | Việc thường làm |
|---|---|---|
| Image | Bản đóng gói và metadata để khởi tạo process | Build, tag, push, scan |
| Container | Một lần chạy cụ thể từ image | Start, stop, inspect, logs |
| Registry | Nơi lưu và phân phối image | Push, pull, kiểm soát quyền |
| Volume | Cơ chế lưu dữ liệu tách khỏi writable container layer | Mount, backup, quản lý dữ liệu |
| Host/container engine | Hạ tầng tạo và quản lý container | CPU, memory, networking, isolation |

Một image có thể được chạy thành nhiều container. Một container bị xóa không đồng nghĩa image bị xóa. Dữ liệu ghi vào writable layer của container cũng không nên được coi là nơi lưu dữ liệu bền vững.

### Container không phải máy ảo đầy đủ

Container thường chia sẻ kernel của host trong những môi trường container Linux, thay vì chạy một kernel riêng như máy ảo truyền thống. Nó cung cấp cơ chế cô lập tiến trình, filesystem, networking và tài nguyên tùy nền tảng.

Vì vậy, container image không phải một lời hứa “chạy được trên mọi hệ điều hành”. Hệ điều hành, kiến trúc CPU, libc và các dependency native vẫn có ảnh hưởng quan trọng.

## 6. OCI image có bắt buộc chứa Spring Boot executable JAR không?

Không. Một OCI image có thể chứa:

- Executable JAR và JRE/JDK phù hợp.
- Native executable cùng một tập thư viện OS cần thiết.
- Một ứng dụng Node.js, Python, Go hoặc ngôn ngữ khác.
- Nhiều file cấu hình, script và runtime components theo thiết kế.

Với Spring Boot, hai mô hình quan trọng nhất:

~~~text
JVM container image:
    Base image + JRE + Spring Boot JAR
                         |
                         v
                 java -jar app.jar

Native container image:
    OS runtime layer + native binary
                         |
                         v
                     ./app
~~~

Tên “image” trong **container image** chỉ đến artifact đóng gói filesystem/layers, trong khi “Native Image” trong **GraalVM Native Image** là công nghệ biên dịch ra mã máy. Hai từ cùng là *image* nhưng nói về **hai tầng hoàn toàn khác nhau**.

## 7. Dùng Dockerfile để đóng gói JAR

Một Dockerfile đơn giản có thể như sau:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app

COPY target/store-service-0.0.1-SNAPSHOT.jar /app/app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ý nghĩa:

1. `FROM` chọn base image có Java runtime.
2. `WORKDIR` tạo/chọn thư mục làm việc.
3. `COPY` đưa JAR đã build vào image.
4. `EXPOSE` ghi nhận cổng mà ứng dụng dự kiến lắng nghe.
5. `ENTRYPOINT` quy định command chính khi container khởi chạy.

Đây là ví dụ cơ bản. Trong production cần xem thêm user không phải root, quyền file, bản cập nhật bảo mật, image digest, memory settings và cách xử lý shutdown.

### Build image và chạy container

Sau khi JAR được build, có thể build image:

~~~bash
docker build -t example/store-service:dev .
~~~

Lệnh trên tạo image cục bộ từ Dockerfile và build context. Nó **chưa khởi động ứng dụng**.

Để chạy:

~~~bash
docker run --rm -p 8080:8080 example/store-service:dev
~~~

Lệnh này tạo và chạy một container từ image.

Truy cập ứng dụng nếu server lắng nghe cổng tương ứng:

~~~text
http://localhost:8080
~~~

Ở đây `-p 8080:8080` ánh xạ cổng host sang cổng container. Chỉ viết `EXPOSE 8080` trong Dockerfile **không tự publish cổng ra host**.

### Vì sao copy đúng artifact quan trọng?

Một Dockerfile dạng:

~~~dockerfile
COPY target/*.jar /app/app.jar
~~~

có thể gặp vấn đề nếu thư mục `target` có nhiều JAR hoặc artifact không đúng. Với dự án thực, nên bảo đảm build tạo đúng output hoặc truyền tên artifact rõ ràng, để CI có thể phát hiện lỗi đóng gói thay vì âm thầm lấy một JAR khác.

### .dockerignore

Build context có thể chứa nhiều file không cần thiết. Ví dụ:

~~~text
.git
.idea
.vscode
node_modules
target/*
!target/store-service-0.0.1-SNAPSHOT.jar
~~~

Đây là ví dụ có chủ đích giữ lại đúng JAR cần đưa vào image. Cú pháp và tính tương tác giữa các quy tắc ignore cần phù hợp với build context của dự án.

Không nên gửi toàn bộ source, credential, file development hoặc cache vào Docker build context nếu chúng không cần thiết. Image nhỏ và build context gọn giúp build ổn định hơn, đồng thời giảm rủi ro lộ thông tin.

## 8. Dockerfile không tự biên dịch Java

Trong ví dụ trên:

~~~dockerfile
COPY target/store-service-0.0.1-SNAPSHOT.jar /app/app.jar
~~~

Dockerfile giả định JAR **đã tồn tại**. Nếu chưa chạy build hoặc file JAR sai version, image build có thể thất bại hoặc đóng gói artifact cũ.

Cần phân biệt hai mô hình:

**Mô hình A — build ngoài Docker:**

~~~text
CI runs Maven/Gradle
         |
         v
     Executable JAR
         |
         v
     docker build
         |
         v
     Container image
~~~

**Mô hình B — multi-stage Docker build:**

~~~text
Docker build stage
         |
         v
Maven/Gradle compiles app
         |
         v
Creates executable JAR
         |
         v
Runtime stage copies artifact
         |
         v
Minimal runtime container image
~~~

Multi-stage build giúp tách build tools khỏi runtime image, nhưng cần quản lý cache, dependency downloads, toolchain versions và reproducibility.

### Ví dụ multi-stage theo ý tưởng

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /workspace
COPY pom.xml .
COPY src ./src

RUN mvn -DskipTests package

FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --from=build /workspace/target/store-service-0.0.1-SNAPSHOT.jar /app/app.jar

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là ví dụ để giải thích **build stage và runtime stage**. Một dự án Maven thật có thể cần parent POM, multi-module dependencies, .mvn, Maven wrapper, settings hoặc repository credentials, nên không nên copy nguyên Dockerfile này mà bỏ qua cấu trúc dự án.

`-DskipTests` chỉ mang ý nghĩa rút ngắn ví dụ build image; pipeline phát hành vẫn cần chạy kiểm thử theo chính sách của dự án ở một stage thích hợp.

## 9. Spring Boot build-image: con đường không cần tự viết Dockerfile

Spring Boot cung cấp goal/task có thể tạo OCI-compatible container image bằng **Cloud Native Buildpacks**.

Với Maven và Spring Boot Maven plugin phù hợp:

~~~bash
mvn spring-boot:build-image
~~~

Với Gradle và Spring Boot plugin phù hợp:

~~~bash
./gradlew bootBuildImage
~~~

Các lệnh này sử dụng buildpacks/builder để biến ứng dụng và metadata thành một container image. Trong cấu hình thông thường, cần có container runtime hoặc endpoint hỗ trợ mà build-image plugin có thể truy cập, cùng khả năng lấy builder/run images và dependencies cần thiết.

### Buildpacks là gì?

Cloud Native Buildpacks mô tả quy trình phát hiện ứng dụng, chọn các thành phần build/runtime, xây dựng layers và tạo OCI image. Thay vì tự chỉ định mọi lệnh trong Dockerfile, buildpack cung cấp một cách đóng gói được chuẩn hóa.

Luồng khái quát:

~~~text
Spring Boot project
       |
       v
Spring Boot build-image task/goal
       |
       v
Builder + buildpacks
       |
       +--> Detect Java application
       +--> Select runtime/components
       +--> Create application layers
       +--> Configure launch process
       |
       v
OCI container image
       |
       v
docker run / container runtime
~~~

Điều này không có nghĩa buildpacks “không dùng container”. Builder có thể sử dụng container runtime trong quá trình build. Nó chỉ có nghĩa developer **không cần tự viết Dockerfile** để có một image chuẩn theo buildpacks.

### Build-image không phải chạy ứng dụng

Lệnh:

~~~bash
mvn spring-boot:build-image
~~~

là bước **build artifact image**, không phải một lời gọi để khởi động server và phục vụ request. Sau khi image được tạo, bạn vẫn cần chạy nó bằng container engine hoặc deploy tới môi trường tương ứng.

### Một số lợi ích của buildpacks

Tùy builder và buildpacks được chọn, giải pháp có thể cung cấp:

- Tách dependency và application layers để tăng hiệu quả cache.
- Chọn Java runtime phù hợp với cấu hình.
- Thiết lập launch process và môi trường runtime.
- Hỗ trợ non-root process và những thực hành bảo mật.
- Metadata phục vụ quản lý image và chuỗi cung ứng phần mềm.
- Cơ chế cập nhật/rebase runtime layers trong những trường hợp tương thích.

Không nên coi mọi khả năng này là tuyệt đối cho mọi builder. Chúng phụ thuộc builder/buildpack/version, registry và chính sách vận hành.

## 10. Buildpacks khác Dockerfile ở đâu?

| Tiêu chí | Buildpacks qua Spring Boot | Dockerfile |
|---|---|---|
| Điểm bắt đầu | Project/artifact + builder/buildpacks | Dockerfile và build context |
| Ai thiết kế bước đóng gói | Buildpacks/builder | Developer/platform team |
| Tùy biến hệ thống | Qua builder, env, bindings, extensions hỗ trợ | Qua Dockerfile stages/instructions |
| Kiểm soát base image | Theo builder/run image | Chủ động chọn `FROM` |
| Caching/layers | Do buildpacks điều phối | Do Dockerfile/build engine điều phối |
| Hợp với | Spring Boot tiêu chuẩn muốn giảm công vận hành Dockerfile | Trường hợp cần kiểm soát đặc biệt |
| Có tự cho native executable? | Không mặc định trong mọi cấu hình | Không; tùy build stage |
| Kết quả | Container image | Container image |

Không nên kết luận buildpacks luôn tốt hơn Dockerfile hoặc ngược lại. Chọn theo yêu cầu nền tảng, mức độ tùy biến, chính sách bảo mật và khả năng vận hành của đội.

### Khi nào nên bắt đầu bằng buildpacks?

Nếu ứng dụng Spring Boot là service tiêu chuẩn, không cần cài những system packages đặc biệt và tổ chức chấp nhận builder được quản lý, buildpacks là điểm bắt đầu hợp lý.

### Khi nào Dockerfile có ích hơn?

Ví dụ:

- Cần thư viện OS đặc biệt không được builder cung cấp.
- Cần quy trình build không tiêu chuẩn.
- Có nhiều artifact/phần mềm khác phải được phối hợp.
- Cần kiểm soát runtime stage, quyền file hoặc image filesystem ở mức chi tiết.
- Nền tảng CI/CD đã chuẩn hóa theo Dockerfile có kiểm soát.

Ngay cả khi dùng Dockerfile, vẫn nên tuân thủ các nguyên tắc về image minimalism, security scanning, reproducible builds và non-root user.

## 11. Layered JAR và image layers

Spring Boot executable JAR có thể mang metadata phục vụ **layering**. Ý tưởng là tách những thành phần thay đổi ở tốc độ khác nhau:

~~~text
Dependencies không thường thay đổi
           |
Spring Boot loader
           |
Snapshot dependencies
           |
Application classes/resources
~~~

Khi build OCI image, những thành phần ổn định có thể nằm ở các layers được cache hiệu quả hơn. Nếu chỉ sửa một Java class, không nhất thiết phải upload/build lại toàn bộ dependency layers.

### Layered JAR không phải bản thân container image

Một JAR được cấu trúc theo layers vẫn là một **JAR**; metadata layer chỉ giúp công cụ đóng gói biết cách chia nội dung khi tạo image.

Ngược lại, một OCI image gồm layers filesystem theo chuẩn container. Hai khái niệm có liên quan nhưng nằm ở hai tầng khác nhau:

~~~text
Spring Boot layered JAR metadata
            |
            v
Image build tool sử dụng thông tin
            |
            v
OCI filesystem layers
~~~

### Có phải layered JAR giúp native image nhanh hơn?

Không theo cùng cơ chế. Native Image compile bytecode và phân tích reachability để tạo binary, không chỉ đặt dependency JAR vào những runtime layers khác nhau.

Cache của container layers có thể vẫn hữu ích cho build pipeline, nhưng **cơ chế tối ưu layered executable JAR không tự chuyển nguyên vẹn thành cơ chế tối ưu native binary**.

### Cẩn thận với hướng dẫn cũ

Cú pháp các công cụ trích xuất layers và jar mode có thể đổi giữa các thế hệ Spring Boot. Với dự án cụ thể, hãy dùng hướng dẫn tương ứng phiên bản đang chạy thay vì áp dụng một câu lệnh jar mode cũ không được hỗ trợ.

## 12. Native executable: một loại artifact khác

Spring Boot có thể hỗ trợ tạo **native executable** thông qua Spring AOT và GraalVM Native Image cùng toolchain phù hợp.

Thay vì:

~~~text
Java bytecode -> JVM load/interpret/JIT at runtime
~~~

mô hình khái quát là:

~~~text
Java bytecode + application metadata
                   |
                   v
            Spring AOT processing
                   |
                   v
        GraalVM Native Image analysis
                   |
                   v
      Machine-code native executable
                   |
                   v
           OS chạy trực tiếp binary
~~~

Native executable là binary được biên dịch cho **hệ điều hành và kiến trúc CPU mục tiêu**. Nó không phải `.jar` đổi phần mở rộng và cũng không phải một OCI image.

### Native Image vẫn liên quan Java

Ứng dụng vẫn được viết bằng Java/Kotlin và dùng Spring framework APIs. Điểm khác là phần lớn công việc phân tích/biên dịch được chuyển sang **build time**, tạo ra executable có thể chạy mà không cần cài một JVM runtime đầy đủ theo cách chạy JAR.

Binary native vẫn có runtime support và có thể cần các thư viện hệ điều hành; “không cần JVM runtime đầy đủ” không có nghĩa “không có bất kỳ runtime component nào”.

### Tại sao native được quan tâm?

Một số trường hợp hưởng lợi:

- Startup nhanh, thích hợp với quy mô instance thay đổi liên tục.
- Chi phí bộ nhớ khi khởi động hoặc ở trạng thái chờ có thể thấp hơn.
- Không phải cài JRE/JDK trong môi trường chạy trực tiếp.
- Giảm một số bước khởi động runtime classloading/JIT.

Đây là **khả năng có thể đạt được**, không phải cam kết mọi workload đều nhanh hơn hoặc tiêu thụ ít bộ nhớ hơn ở mọi tình huống. Cần đo trên ứng dụng thật.

## 13. Spring AOT làm gì trong quá trình native build?

**Ahead-of-Time (AOT) processing** của Spring giúp chuẩn bị một số thông tin mà ứng dụng Spring truyền thống thường khám phá tại runtime.

Trong JVM mode, Spring có nhiều khả năng động:

- Component scanning.
- Reflection để tìm constructor/method/annotation.
- Dynamic proxies.
- Đăng ký bean theo điều kiện.
- Đọc resource từ classpath.
- Serialization/deserialization.
- Cấu hình dựa trên Environment và classpath.

GraalVM Native Image hoạt động theo mô hình phân tích reachability và closed-world ở build time. Không phải mọi code hoặc resource chỉ được gọi bằng reflection/string name ở runtime đều được suy ra tự động.

Spring AOT có thể tạo code và metadata mô tả những thành phần cần thiết cho native runtime, giúp Spring Boot sử dụng những tính năng này trong native executable.

### Hai lớp cần phân biệt

| Thành phần | Công việc |
|---|---|
| Spring AOT | Chuẩn bị bean registration và metadata/hints phù hợp với native build |
| GraalVM Native Image | Phân tích và biên dịch ứng dụng cùng dependencies thành native binary |

Spring AOT **không thay thế** Native Image compiler; Native Image cũng không tự hiểu mọi cơ chế dynamic của Spring nếu không có đủ metadata.

### AOT không phải tối ưu hóa JVM thông thường

Một ứng dụng chạy JVM có thể dùng AOT-generated artifacts trong các ngữ cảnh hỗ trợ, nhưng trọng tâm của native build là cung cấp dữ liệu để tạo executable theo mô hình native. Đừng đồng nhất Spring AOT với JIT compiler của JVM.

## 14. Tạo native executable trực tiếp

Với Spring Boot 3.x và bộ plugin phù hợp, một workflow Maven điển hình có thể có dạng:

~~~bash
mvn -Pnative native:compile
~~~

Lệnh này chỉ hoạt động nếu dự án đã có cấu hình native build thích hợp, chẳng hạn profile/plugin của GraalVM Native Build Tools và Spring Boot AOT integration. Không phải mọi `pom.xml` bất kỳ đều tự có profile `native`.

Với Gradle và Native Build Tools plugin phù hợp:

~~~bash
./gradlew nativeCompile
~~~

Build sử dụng một toolchain có khả năng Native Image cùng các compiler/system dependencies cần thiết.

Sau khi build thành công, artifact có thể nằm ở một output directory như:

~~~text
target/
build/native/nativeCompile/
~~~

Tên đường dẫn và executable cụ thể phụ thuộc plugin, hệ điều hành và cấu hình build.

### Không chạy nativeCompile nếu mục tiêu chỉ là JAR

`nativeCompile` không phải alias của `bootJar`. Nó có thể tiêu tốn đáng kể CPU, bộ nhớ và thời gian build để tạo binary cho một nền tảng cụ thể.

Nếu deployment hiện tại chỉ cần Java 21 và JVM container, một executable JAR là kết quả đầy đủ; native build là lựa chọn tối ưu khác, không phải bước bắt buộc.

### Build cần môi trường phù hợp với nền tảng mục tiêu

Native executable thường liên quan OS, CPU architecture và cách liên kết thư viện native. Một binary build cho Linux x86-64 không thể giả định chạy trực tiếp trên macOS ARM64, và ngược lại.

Cần xác định build host/target platform hoặc cơ chế cross-build được toolchain hỗ trợ. Trong CI, native build thường được chạy trên runner phù hợp với nền tảng deploy.

## 15. Native executable không phải tự động tương thích mọi thư viện

Java trên JVM rất linh hoạt với reflection, classpath scanning, dynamic class loading và runtime code generation. Native Image yêu cầu nhiều thông tin về đường code và metadata được biết tại build time.

Một số trường hợp cần chú ý:

- `Class.forName(...)` với tên class được quyết định động.
- Reflection tìm constructor/method không được framework suy ra.
- Serialization/deserialization của những kiểu được chọn động.
- Resource file chỉ được tra cứu bằng tên tạo lúc chạy.
- JNI hoặc native library với yêu cầu link/load riêng.
- Dynamic proxies từ interface không được mô tả đầy đủ.
- Framework tự tạo bytecode/class runtime.
- ServiceLoader hoặc plugin architecture cần metadata reachability.
- Class initialization có side effect phụ thuộc môi trường build.

Spring Boot và những thư viện được hỗ trợ có thể cung cấp runtime hints, nhưng **không có bảo đảm mọi thư viện Java đều chạy native mà không cần điều chỉnh**.

### Ví dụ reflection động

~~~java
String className = settings.getHandlerClassName();

Class<?> type = Class.forName(className);
Object handler = type.getDeclaredConstructor().newInstance();
~~~

Nếu `className` chỉ xuất hiện trong cấu hình runtime, native compiler có thể không biết trước mọi class cần được giữ và cấp quyền reflective access.

Một hướng xử lý là thay cơ chế lựa chọn class động bằng Spring bean registry rõ ràng, hoặc cung cấp reachability metadata/runtime hints chính xác cho những type cần reflection.

### Resource file trong native image

Ví dụ:

~~~java
InputStream stream =
        getClass().getResourceAsStream("/rules/payment.json");
~~~

Với JVM JAR, resource nằm trên classpath có thể được tìm như mong đợi. Với native binary, resource có thể cần được khai báo để được đưa vào native image.

Không nên kết luận “file nằm trong `src/main/resources` thì native executable chắc chắn chứa nó”. Cần hiểu resource reachability và metadata của build tool.

## 16. Runtime hints: khi phải khai báo khả năng truy cập động

Spring hỗ trợ cơ chế runtime hints cho native/AOT scenarios. Ví dụ về một registrar:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class PartnerRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader
    ) {
        hints.reflection().registerType(
                PartnerPayload.class,
                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );

        hints.resources().registerPattern(
                "partner/templates/*.json"
        );
    }
}
~~~

`PartnerPayload` là class minh họa. `RuntimeHints` mô tả một số nhu cầu reflective invocation và resource access mà native build phải biết.

Một cách đăng ký trong những phiên bản Spring hỗ trợ:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PartnerRuntimeHints.class)
public class PartnerConfiguration {
}
~~~

Cần import `org.springframework.context.annotation.ImportRuntimeHints` cùng các loại liên quan. Đây chỉ là ví dụ cho trường hợp có **nhu cầu runtime dynamic thật**; không phải mọi Spring Boot application đều cần tự viết runtime hints.

### Không đăng ký mọi class một cách mù quáng

Metadata quá rộng có thể tăng kích thước binary, kéo nhiều code không cần thiết vào executable hoặc che đi vấn đề thiết kế. Khi gặp lỗi native, hãy xác định chính xác class/resource nào bị thiếu, cơ chế truy cập nào cần và thư viện đó có hỗ trợ native chính thức hay không.

### Đừng nhầm Spring runtime hints với Dockerfile

Runtime hints tham gia **phân tích và biên dịch native executable**. Dockerfile quyết định **đóng gói và chạy artifact trong container**. Thêm một `COPY` vào Dockerfile không giải quyết một reflection metadata thiếu trong native binary đã build.

## 17. Build image chứa native executable

Có hai bước có thể phối hợp:

~~~text
Build native executable
        |
        v
    app binary
        |
        v
Build OCI image chứa binary
        |
        v
Run container chạy binary
~~~

Một Dockerfile runtime đơn giản minh họa:

~~~dockerfile
FROM debian:bookworm-slim

WORKDIR /app

COPY build/native/nativeCompile/store-service /app/store-service

RUN chmod +x /app/store-service

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["/app/store-service"]
~~~

Ví dụ giả định binary được build cho Linux và tương thích với những system libraries trong base image. Tùy cách link, executable có thể cần glibc, CA certificates, timezone data hoặc native dependencies khác. Nếu base image quá tối giản, binary có thể không chạy dù Dockerfile build thành công.

### Vì sao không copy binary Linux vào image bất kỳ?

Một native binary liên kết động có yêu cầu đối với loader và libraries của hệ điều hành. Một base image dùng libc khác hoặc thiếu thư viện cần thiết có thể gây lỗi runtime.

Khác với JVM JAR vốn được JVM xử lý qua một runtime phù hợp, native binary gắn chặt hơn với nền tảng biên dịch/liên kết. Phải kiểm tra OS/architecture và thư viện runtime của image.

### Image nhỏ không tự chứng minh native nhanh hơn

Image size đo dung lượng các layers được tải/lưu. Startup time đo thời gian process sẵn sàng. RSS memory đo một khía cạnh tiêu thụ bộ nhớ. Throughput và latency đo hành vi dưới tải.

Các chỉ số này liên quan nhưng **không thay thế nhau**. Một image nhỏ vẫn có thể khởi động chậm do chờ database; một native executable nhỏ vẫn có thể có throughput thấp hơn JVM đã warm-up trong một workload nào đó.

## 18. Buildpacks cũng có thể tạo native image

Một số builder/buildpack hỗ trợ chế độ GraalVM Native Image. Spring Boot plugin có thể cấu hình build image để sử dụng chế độ này, tùy phiên bản và builder.

Ví dụ mang tính minh họa với Maven khi dự án đã được chuẩn bị cho native build:

~~~bash
mvn -Pnative spring-boot:build-image
~~~

Trong các hệ thống buildpacks có hỗ trợ Native Image, có thể có environment variable buildpack như:

~~~text
BP_NATIVE_IMAGE=true
~~~

Cách kích hoạt chính xác phụ thuộc builder, buildpack và phiên bản Spring Boot plugin. Không nên cho rằng chỉ đặt biến `BP_NATIVE_IMAGE` trong ứng dụng lúc chạy sẽ tự biến JVM image thành native image.

### Điều gì thực sự diễn ra?

~~~text
Spring Boot project
          |
          v
Boot build-image + native-capable buildpacks
          |
          +--> Spring AOT processing
          +--> GraalVM Native Image compile
          +--> Native binary
          +--> OCI image assembly
          |
          v
OCI image chạy native executable
~~~

Thành phẩm là **container image chứa native executable**. Không nên gọi kết quả đó là “JAR native” hoặc “JVM trong container” nếu thực tế process chạy từ binary.

### Buildpacks native vẫn cần nhiều tài nguyên build

Native Image compilation có thể yêu cầu memory/CPU đáng kể so với đóng gói JAR. Trong CI, cần phân bổ đủ tài nguyên cho builder và giới hạn concurrency nếu nhiều service cùng build.

Việc đưa native build vào container có thể giúp chuẩn hóa toolchain, nhưng không làm chi phí biên dịch biến mất.

## 19. So sánh JVM JAR và native executable

| Khía cạnh | JVM executable JAR | GraalVM native executable |
|---|---|---|
| Định dạng | JAR chứa bytecode/dependencies | Binary mã máy cho target platform |
| Runtime yêu cầu | JVM/JRE phù hợp | Không cần JVM runtime đầy đủ; vẫn cần runtime OS phù hợp |
| Build time | Thường ngắn hơn | Thường dài hơn, cần phân tích và biên dịch native |
| Startup | Có chi phí khởi tạo JVM/framework | Thường có khả năng startup nhanh hơn |
| Bộ nhớ | Có JVM heap, JIT/code cache và runtime overhead | Có thể giảm memory footprint trong một số workload |
| Peak throughput | JVM JIT có thể tối ưu tốt sau warm-up | Phụ thuộc binary, compilation và workload |
| Dynamic reflection/classloading | Linh hoạt hơn | Cần chú ý reachability metadata |
| Portability | JAR có thể chạy ở nhiều OS có JVM phù hợp | Binary gắn với OS/architecture mục tiêu |
| Observability | Nhiều công cụ JVM profiling/JFR/heap dump quen thuộc | Tooling và khả năng quan sát có khác biệt |
| Debugging | Quy trình Java/JVM quen thuộc | Có thêm vấn đề native symbols/toolchain |
| Đóng gói vào OCI image | Có | Có |
| Phù hợp | Dịch vụ tiêu chuẩn, nhiều thư viện dynamic, build nhanh | Cold start/memory-sensitive workloads khi native support đầy đủ |

Không nên biến bảng này thành kết luận “native tốt hơn JVM”. Một service xử lý tải lớn, chạy lâu dài và có thời gian warm-up có thể hưởng lợi mạnh từ JVM JIT. Một function ngắn hạn, scale-to-zero hoặc job có thời gian sống ngắn có thể hưởng lợi từ native startup nhanh.

**Đo trên workload thực tế mới quyết định được.**

## 20. Cùng một mã nguồn có thể có hai chiến lược phát hành

Ví dụ một hệ thống có ba thành phần:

~~~text
checkout-service     -> JVM container
billing-worker       -> JVM container
small-scheduled-job  -> native container
~~~

Không nhất thiết toàn bộ hệ thống phải chuyển sang native cùng lúc.

### Vì sao có thể chọn hỗn hợp?

- Web service xử lý tải liên tục có thể ưu tiên JVM throughput và công cụ debug.
- Scheduled job ngắn có thể ưu tiên thời gian khởi động.
- Service dùng thư viện reflection/plugin phức tạp có thể chưa phù hợp native.
- Một nhóm ứng dụng có thể được quản trị bởi buildpacks, trong khi phần khác cần Dockerfile tùy chỉnh.

Kiến trúc phải giữ API và integration contracts ổn định; runtime packaging không nên rò rỉ vào logic nghiệp vụ nếu không thực sự cần.

### Không thay đổi build mode vô ý giữa môi trường

Nếu test chỉ chạy JVM JAR nhưng production dùng native executable, test có thể bỏ lỡ vấn đề reflection/resource của native. Pipeline cần có ít nhất những kiểm thử phù hợp trên artifact **thực sự được triển khai**.

## 21. Ranh giới cấu hình: không đóng cứng môi trường trong image

Một image tốt thường được thiết kế để dùng lại ở các môi trường với cấu hình khác nhau:

~~~text
Một image theo digest
          |
          +--> dev: DB dev + dev credentials
          |
          +--> staging: DB staging + staging credentials
          |
          +--> prod: DB prod + prod credentials
~~~

Cùng một artifact có thể được chạy với environment variables, mounted configuration hoặc secret management khác nhau. Việc này giúp giảm nguy cơ “mã nguồn đúng nhưng artifact khác” giữa staging và production.

Ví dụ:

~~~bash
docker run --rm \
  -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e SERVER_PORT=8080 \
  example/store-service:1.0
~~~

Ở đây cấu hình được cấp lúc **run container**, không phải nhúng vào container image lúc build.

### spring.profiles.active trong container

Spring Boot đọc profile từ Environment theo precedence:

~~~yaml
spring:
  profiles:
    default: local
~~~

Khi container đặt:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

profile `prod` có thể được chọn mà không sửa image.

Không nên nhúng mật khẩu database, API key hoặc production credential vào `application-prod.yml` được commit trong repository hay vào layer image. Dùng secrets được nền tảng quản lý và giới hạn quyền truy cập.

### Build-time và runtime config khác nhau

| Dữ liệu | Thường cần lúc nào? |
|---|---|
| Java source, dependency versions, compiler flags | Build time |
| Native reflection/resource metadata | Native build time |
| Builder/run image và architecture | Build/image assembly |
| Database URL, credential, active profile | Runtime |
| Port của service, logging level | Runtime |
| Feature flag ảnh hưởng bean registration | Runtime startup |
| Secret dùng khi image build | Chỉ khi thật sự cần, phải dùng cơ chế secret build chuyên dụng |

Không nên đưa runtime secret vào build argument hoặc Dockerfile `ENV` rồi hy vọng layer history không tiết lộ nó.

## 22. Native build làm ranh giới build-time/runtime quan trọng hơn

Trong JVM mode, ứng dụng thường có khả năng khám phá nhiều thứ động tại startup. Với native executable, một số quyết định reachability và class initialization được đưa về build time.

Ví dụ ứng dụng có hai bean:

~~~java
@Configuration
public class PaymentConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "app.payment.mode",
            havingValue = "mock"
    )
    PaymentGateway mockGateway() {
        return new MockPaymentGateway();
    }

    @Bean
    @ConditionalOnProperty(
            name = "app.payment.mode",
            havingValue = "live"
    )
    PaymentGateway liveGateway() {
        return new LivePaymentGateway();
    }
}
~~~

Với native/AOT, cần hiểu rằng **không phải mọi thay đổi runtime property đều có thể làm xuất hiện một loại class hoặc bean chưa được tính tới trong quá trình build**. Spring AOT có cơ chế xử lý condition và reachability theo cách hỗ trợ, nhưng các điều kiện được quyết định tại build time có thể hạn chế những tổ hợp runtime được tạo ra.

Do đó, với một ứng dụng native, hãy kiểm tra các profile/property combinations mà deployment cần hỗ trợ. Không nên giả định cứ đổi environment variable là có thể tải thêm plugin/class hoàn toàn mới vào binary như với JVM classpath.

### Tránh đọc environment production khi build native

Build pipeline phải có thể tái tạo artifact mà không cần nối trực tiếp tới database production hoặc đọc secret runtime. Nếu code trong static initializer hoặc build-time hook cố gọi một dịch vụ bên ngoài, native compile có thể trở nên phụ thuộc vào môi trường không đúng.

Hãy tách rõ logic cần tại build time khỏi side effect chỉ được phép xảy ra khi application process thực sự chạy.

## 23. Container networking: localhost không phải host theo nghĩa thông thường

Một lỗi phổ biến khi chuyển Spring Boot từ IDE sang container là database URL:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/store
~~~

Khi chạy trong container, `localhost` thường chỉ **network namespace của chính container đó**. Nếu database chạy trong container khác, `localhost` không tự trỏ đến database.

Ví dụ với một mạng container có database service tên `postgres`:

~~~properties
spring.datasource.url=jdbc:postgresql://postgres:5432/store
~~~

Cấu hình mạng và tên DNS thực tế phụ thuộc container orchestrator hoặc Docker Compose.

### EXPOSE và -p khác nhau

Dockerfile:

~~~dockerfile
EXPOSE 8080
~~~

chủ yếu là metadata/dấu hiệu về cổng ứng dụng dự kiến dùng.

Lệnh:

~~~bash
docker run -p 8081:8080 example/store-service:dev
~~~

ánh xạ cổng `8081` trên host tới cổng `8080` trong container.

Bên trong ứng dụng:

~~~properties
server.port=8080
~~~

điều khiển cổng Spring Boot web server lắng nghe trong container.

Ba vị trí này là ba cấu hình riêng; nếu không khớp, request có thể không tới được server.

### Bind address

Nếu ứng dụng chỉ bind `127.0.0.1` bên trong container, việc publish port ra host có thể không đạt kết quả mong muốn. Khi muốn phục vụ qua container network, cần kiểm tra server đang lắng nghe địa chỉ phù hợp, ví dụ `0.0.0.0` theo chính sách mạng của nền tảng.

Không nên “sửa” mọi vấn đề mạng bằng cách mở cổng ra public internet; trong production còn cần ingress, network policies, TLS và authentication phù hợp.

## 24. Dữ liệu và filesystem của container

Container có thể có writable layer, nhưng nó không phải nơi lưu dữ liệu nghiệp vụ bền vững lý tưởng.

Ví dụ Spring Boot nhận file upload:

~~~text
/app/uploads/invoice.pdf
~~~

Nếu file được lưu vào writable layer của container rồi container bị thay thế, dữ liệu có thể mất. Với dữ liệu cần giữ, nên dùng:

- Database hoặc object storage phù hợp.
- Volume được quản lý.
- External filesystem có chính sách backup.
- Workflow upload/persistence có retry và kiểm tra integrity.

### Native không giải quyết persistence

Dù process là JVM hay native binary, cả hai đều chịu cùng vấn đề về container writable filesystem. Đổi sang native executable không tự làm dữ liệu trong container bền vững hơn.

### Quyền file và user

Một container chạy bằng non-root user có thể không ghi được vào directory mà image owner là root. Đây là một vấn đề packaging/runtime permission, không phải Spring bean injection hay native compilation.

Nếu cần ghi tạm, hãy cấu hình thư mục và quyền phù hợp hoặc dùng mounted volume. Không chạy root chỉ để bỏ qua lỗi quyền mà chưa đánh giá rủi ro.

## 25. Process lifecycle, PID 1 và graceful shutdown

Trong Dockerfile, **exec-form ENTRYPOINT** là một lựa chọn phù hợp:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Khi process Java là process chính của container, tín hiệu dừng từ container runtime có thể được gửi tới process đó theo cơ chế phù hợp.

Một shell-form như:

~~~dockerfile
ENTRYPOINT java -jar /app/app.jar
~~~

có thể tạo shell làm process chính và làm việc chuyển tiếp signal phức tạp hơn, tùy implementation. Nếu phải dùng entrypoint script, thường nên dùng `exec` khi chuyển sang process ứng dụng:

~~~sh
#!/bin/sh
exec java -jar /app/app.jar
~~~

### Container stop và Spring Boot shutdown

Luồng mong muốn:

~~~text
Orchestrator muốn dừng container
                |
                v
          Gửi tín hiệu dừng
                |
                v
        JVM/native process nhận
                |
                v
        Spring ApplicationContext đóng
                |
                +--> Ngừng nhận việc mới
                +--> Chờ công việc đang chạy
                +--> Đóng connection pools
                +--> Chạy destruction callbacks
                |
                v
         Process kết thúc
~~~

Spring Boot hỗ trợ cấu hình graceful shutdown của web server trong các phiên bản phù hợp. Ví dụ:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Thời gian thực tế còn chịu giới hạn của container orchestrator. Nếu nền tảng chỉ cấp vài giây trước khi kill cưỡng bức, cấu hình chờ dài hơn bên trong Spring không tự bảo đảm các request được hoàn tất.

### Native process cũng cần shutdown đúng

Native executable không tự biến cleanup thành không cần thiết. Nó vẫn có network connections, thread pools, file handles và lifecycle callbacks. Phải kiểm tra graceful shutdown trên **hình thức runtime thực sự sử dụng**.

## 26. Health check và readiness

Một container có trạng thái “running” không bảo đảm ứng dụng sẵn sàng nhận request. Process có thể đang:

- Khởi động Spring ApplicationContext.
- Chạy database migration.
- Chưa kết nối được dependency bắt buộc.
- Tạm thời quá tải hoặc không thể tiếp nhận request mới.

Spring Boot Actuator hỗ trợ health endpoints khi dependency và cấu hình tương ứng được thêm. Ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Endpoint tiêu biểu:

~~~text
/actuator/health
~~~

Trong môi trường orchestrator như Kubernetes, có thể dùng readiness/liveness probes và những endpoint nhóm tương ứng khi được bật/cấu hình phù hợp.

### Liveness khác readiness

| Probe | Câu hỏi | Hậu quả khi không đạt |
|---|---|---|
| Liveness | Process có còn ở trạng thái nên duy trì không? | Nền tảng có thể restart |
| Readiness | Instance hiện có thể nhận lưu lượng không? | Nền tảng có thể tạm ngừng route request |
| Startup probe | Ứng dụng đã hoàn tất giai đoạn startup cho phép kiểm tra khác chưa? | Giảm false failures khi khởi động chậm |

Không nên đặt mọi dependency bên ngoài vào liveness. Nếu database tạm ngừng và mọi instance cùng restart liên tục, sự cố có thể trầm trọng hơn. Thiết kế health check phải gắn với điều mà orchestrator sẽ làm khi probe thất bại.

### JVM và native có startup profile khác nhau

Nếu native process khởi động nhanh hơn, probe delay/threshold có thể thay đổi. Nhưng đừng giảm mọi timeout chỉ dựa trên kết quả một lần start. Startup thực tế còn gồm config loading, DNS, TLS, migration, cache warm-up và kết nối hạ tầng.

## 27. Logging và observability qua ranh giới container

Trong container, cách phổ biến là ghi log ra stdout/stderr để hạ tầng thu thập:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(StoreApplication.class);

log.info("Store service started");
~~~

Có thể xem log development qua:

~~~bash
docker logs <container-name-or-id>
~~~

Trong production, log collector có thể thu thập, gắn metadata và chuyển đến hệ thống quan sát.

### Đừng coi Docker logs là kho lưu trữ vĩnh viễn

Retention và khả năng tìm kiếm phụ thuộc log driver, nền tảng container và collector. Nếu audit bắt buộc, cần cơ chế lưu dữ liệu bền vững, không chỉ một dòng log.

### JVM và native có khác biệt observability

Trên JVM có nhiều công cụ quen thuộc như heap dump, JFR và JVM-specific metrics. Native executable có khả năng quan sát khác nhau; một số API/metric có thể vẫn được hỗ trợ qua Spring/Micrometer, nhưng chi tiết runtime và tooling có thể khác.

Khi chọn native, hãy kiểm tra bộ công cụ giám sát và profiling phù hợp, không chỉ startup time.

## 28. Cấu hình CPU và bộ nhớ trong container

Container có thể giới hạn CPU/memory; nhưng cấu hình JVM và native runtime không giống nhau.

Với JVM image, có thể cần điều chỉnh:

- Heap size hoặc MaxRAMPercentage.
- CPU awareness theo container limits.
- Thread pool và connection pool.
- Metaspace, code cache, native memory.
- Garbage collector settings khi thực sự có nhu cầu.

Ví dụ truyền JVM options:

~~~bash
docker run --rm \
  -e JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65.0" \
  example/store-service:dev
~~~

`JAVA_TOOL_OPTIONS` là một cơ chế JVM đọc tham số khởi động; giá trị ví dụ cần được đánh giá theo heap, non-heap memory và memory limit thật, không phải cấu hình tối ưu chung.

Với native executable, những JVM flags như `-XX:MaxRAMPercentage` không được mặc nhiên áp dụng như khi chạy `java -jar`. Native runtime có các tùy chọn riêng tùy GraalVM Native Image version và kiểu build.

### Không so memory chỉ theo heap

Một JVM có heap 256 MB vẫn còn thread stacks, class metadata, JIT code cache và native allocations. Native process cũng có memory ngoài heap. Khi so sánh, nên đo RSS/working set và memory peak theo cùng workload, cùng giới hạn container.

### Startup nhanh không đồng nghĩa throughput tốt

Một REST service chạy nhiều giờ có thể đạt throughput tốt khi JVM JIT tối ưu những đoạn code nóng. Một native executable có thể thắng ở cold start nhưng không nhất thiết thắng khi tải cao kéo dài. Lựa chọn phải dựa trên SLA thực tế.

## 29. Build-time cache và runtime performance là hai trục khác nhau

Đóng gói artifact nhanh là mục tiêu của pipeline; startup nhanh là mục tiêu runtime. Chúng tác động đến nhau nhưng không đồng nghĩa.

~~~text
Build pipeline
    |
    +--> Compile speed
    +--> Dependency caching
    +--> Docker/buildpack layer cache
    +--> Native compilation cost
    |
    v
Artifact ready
    |
    v
Runtime
    |
    +--> Process startup
    +--> Application readiness
    +--> Memory use
    +--> Throughput
    +--> Latency
~~~

Một native build có thể mất nhiều thời gian hơn để tạo artifact nhưng đổi lại runtime startup nhanh hơn. Nếu tổ chức triển khai rất thường xuyên, chi phí build có thể đáng kể; nếu service scale-to-zero liên tục, startup có thể là ưu tiên lớn.

### Lấy số đo ở đâu?

Nên thu thập:

- Thời gian clean build và incremental build.
- Dung lượng artifact và container image.
- Thời gian từ process start đến readiness.
- Peak RSS và steady-state memory.
- CPU sử dụng khi startup và dưới tải.
- P50/P95/P99 latency, throughput.
- Thời gian shutdown và xử lý request đang chạy.
- Lỗi tương thích, chi phí duy trì runtime hints.

Không nên chọn native chỉ vì một demo “Hello World” có startup đẹp nhưng không đại diện cho ứng dụng thật.

## 30. Reproducibility và supply chain của image

Một image có tag:

~~~text
example/store-service:latest
~~~

không phải định danh bất biến. Tag có thể được cập nhật để trỏ tới nội dung mới.

Một image digest xác định nội dung image cụ thể hơn:

~~~text
example/store-service@sha256:<digest>
~~~

Trong production, dùng digest hoặc quy trình release kiểm soát tag giúp tránh triển khai nhầm artifact.

### Những thực hành hữu ích

- Pin dependency versions qua BOM/lockfile khi phù hợp.
- Quản lý base image version và cập nhật security.
- Tạo image từ pipeline có thể lặp lại.
- Không cài package không cần thiết vào runtime layer.
- Quét lỗ hổng dependency và container image.
- Dùng non-root user nếu khả thi.
- Hạn chế quyền runtime filesystem/network.
- Không lưu secret trong image layers.
- Lưu build metadata/commit SHA để truy vết artifact.
- Ký image hoặc dùng các chính sách artifact attestation nếu tổ chức yêu cầu.
- Theo dõi SBOM và giấy phép dependency phù hợp.

### Native image không miễn nhiễm lỗi bảo mật

Native executable chứa code thư viện tại thời điểm build. Nếu có lỗ hổng trong dependency hoặc runtime component, thường cần **build lại binary** và redeploy. Việc đổi container base image không tự thay nội dung một native binary đã liên kết những thành phần có lỗ hổng.

Tương tự, với JVM image, cập nhật Java runtime/base image là một phần của maintenance nhưng không tự cập nhật thư viện ứng dụng nằm bên trong JAR.

## 31. Multi-platform và architecture

Khi triển khai trên cả x86-64 và ARM64, cần kiểm tra ba thứ:

1. **Container image platform:** OS và CPU architecture của image.
2. **Runtime trong image:** JRE/JDK hoặc native binary tương thích architecture.
3. **External native libraries:** JNI/driver và system libraries phù hợp.

Một Java JAR có thể dùng lại ở nhiều architecture nếu JVM và các dependency native của nó tương thích. Nhưng OCI image chứa JRE x86-64 không tự trở thành ARM64 image chỉ vì file JAR đa nền tảng.

Với native executable, binary phải được biên dịch hoặc xây dựng đúng cho từng target platform, trừ khi toolchain hỗ trợ một hình thức target build cụ thể.

### Multi-arch image

Một registry tag có thể trỏ tới image index/manifest list chứa nhiều architecture variants. Container runtime chọn variant phù hợp với host.

Nhưng tạo multi-arch image thực sự đòi hỏi các artifact tương ứng từng architecture. Đừng chỉ gắn một tag “multiarch” cho binary đơn kiến trúc.

## 32. Native build và class initialization

Một điểm đặc biệt của Native Image là thời điểm **class initialization**. Một số class có thể được khởi tạo lúc build, một số khác lúc runtime theo quy tắc/compiler configuration.

Ví dụ thiết kế không phù hợp:

~~~java
public final class ProductionConfig {

    static final String TOKEN =
            System.getenv("PAYMENT_API_TOKEN");

    private ProductionConfig() {
    }
}
~~~

Nếu class được khởi tạo trong quá trình native build thay vì ở runtime, giá trị environment có thể bị “đóng băng” không đúng hoặc tạo ra vấn đề về secret/configuration. Không nên đặt logic đọc runtime secret, mở socket hay tạo connection trong static initialization mà không hiểu phase của Native Image.

Tốt hơn, đọc cấu hình tại runtime startup qua Spring `Environment`, `@ConfigurationProperties` hoặc một service được tạo đúng vòng đời:

~~~java
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        String apiToken,
        URI endpoint
) {}
~~~

Khi dùng native/AOT, cần đảm bảo property binding type được Spring hỗ trợ và những type động đã có metadata nếu cần. Không dùng native build như lý do để chuyển secret từ runtime về build time.

## 33. Test strategy cho JVM và native

Một chiến lược kiểm thử có thể chia thành các tầng:

| Tầng | Mục tiêu |
|---|---|
| Unit tests | Kiểm tra business logic |
| Spring context tests trên JVM | Kiểm tra DI, configuration, repository, HTTP wiring |
| Container smoke tests | Xác nhận image chạy, port/network/env/health đúng |
| Native smoke tests | Xác nhận binary khởi động và resource/reflection hoạt động |
| Native integration tests | Kiểm tra các use case quan trọng trong native runtime |
| Performance tests | So startup, memory, latency, throughput theo workload thật |

Nếu production dùng native executable nhưng toàn bộ test chỉ chạy trong JVM, một số lỗi chỉ xuất hiện tại native runtime có thể bị bỏ sót.

### Điều cần chú ý ở native smoke test

- Spring context tạo đủ bean cần thiết không?
- JSON serialization/deserialization với DTO thực tế có chạy không?
- Resource trong classpath có được tìm đúng không?
- JPA/ORM/query có hoạt động với metadata cần thiết không?
- Các proxy/transaction/security có hoạt động không?
- Native library và TLS certificate có sẵn không?
- Profile/environment variables ở runtime có hiệu lực đúng không?
- Health probes và graceful shutdown có hoạt động không?

Đây là những loại trường hợp cần được xác minh khi triển khai native, không phải giả định một lần native compile thành công đã chứng minh mọi chức năng.

### Test image đúng cách

Sau khi build một OCI image, hãy chạy **chính image sẽ được deploy** trong môi trường kiểm thử phù hợp. Test một JAR riêng không phát hiện được lỗi sai ENTRYPOINT, thiếu CA certificates, sai user permission hay không publish được port của image.

## 34. Kịch bản thực tế: triển khai Store Service theo JVM image

Giả sử một nhóm phát triển ứng dụng bán hàng với Spring MVC, Spring Data JPA và PostgreSQL. Mục tiêu ban đầu là triển khai nhất quán trên container platform; chưa có yêu cầu cold start đặc biệt.

Luồng nên bắt đầu từ executable JAR:

~~~text
Checkout source
      |
      v
Maven/Gradle build + tests
      |
      v
Spring Boot executable JAR
      |
      v
Dockerfile hoặc Buildpacks
      |
      v
OCI image
      |
      v
Registry
      |
      v
Container orchestrator
      |
      +--> Runtime Environment/Secrets
      +--> Service networking
      +--> Health checks
      +--> CPU/memory limits
      +--> Log collection
      |
      v
Spring Boot process chạy JVM
~~~

Đây là lựa chọn đơn giản, dễ debug và thường có khả năng tương thích tốt với thư viện Java.

### Cấu hình ở runtime

~~~yaml
spring:
  application:
    name: store-service

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Môi trường triển khai có thể cung cấp:

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/store
SPRING_DATASOURCE_USERNAME=store_user
~~~

Mật khẩu nên đến từ secret management phù hợp. Không nhúng nó vào Dockerfile hoặc hard-code trong source.

### Khi nào mới nên thử native?

Khi đã có baseline JVM image và số đo startup/memory, có thể thử native trên cùng use cases. Nếu phần lớn bottleneck nằm ở database migration, network handshake hoặc warm-up một hệ thống bên ngoài, native startup improvement có thể không mang lại lợi ích như kỳ vọng.

## 35. Kịch bản thực tế: scheduled worker muốn giảm cold start

Giả sử một job chạy theo lịch, mỗi lần chỉ xử lý một lượng dữ liệu nhỏ. Thời gian Spring Boot JVM startup chiếm tỷ lệ lớn so với toàn bộ thời gian job.

Một phương án:

~~~text
Source + tests
      |
      v
Spring AOT
      |
      v
GraalVM Native Image build
      |
      v
Native executable
      |
      v
OCI image chứa native binary
      |
      v
Scheduler tạo container
      |
      v
Job chạy và kết thúc
~~~

Ở đây native có thể đáng cân nhắc vì thời gian job ngắn và số lần khởi động nhiều.

Tuy nhiên:

- Build time có thể lâu hơn.
- Nếu job dùng reflection/plugin phức tạp, cần thêm metadata.
- Nếu job chạy trên nhiều architecture, cần multi-platform build.
- Exit code phải được trả đúng cho scheduler.
- Database transactions và idempotency vẫn cần thiết.
- Container startup và cold connection vẫn tồn tại.

Không nên chuyển sang native khi chưa có pipeline kiểm thử binary thật hoặc khi lợi ích đo được không bù chi phí duy trì.

## 36. Ranh giới giữa Spring Boot packaging và deployment platform

Spring Boot giúp:

- Build executable JAR/WAR.
- Tích hợp build image qua buildpacks.
- Chuẩn bị AOT/native build khi có toolchain phù hợp.
- Cung cấp cấu hình runtime, health và lifecycle hooks.
- Chạy web server/worker trong process.

Nhưng Spring Boot **không thay thế**:

- Container registry.
- IAM và secret manager.
- Kubernetes/Docker networking.
- TLS ingress/load balancer.
- Storage/backup.
- CI/CD release policy.
- Autoscaling strategy.
- Image scanning/signing.
- Resource quota và cluster scheduling.

Khi một image chạy thất bại vì registry credentials không hợp lệ, đó chủ yếu là vấn đề deployment/platform. Khi native binary thiếu reflective metadata, đó là vấn đề build/native compatibility. Khi app không tạo được DataSource vì URL sai, đó là vấn đề runtime configuration. Phân biệt đúng ranh giới giúp xử lý sự cố nhanh hơn.

## 37. Lỗi thường gặp và cách định vị

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `java -jar` báo không có main manifest | Dùng plain JAR, không phải Boot executable JAR | Kiểm tra plugin, manifest và artifact |
| Image build báo không thấy JAR | JAR chưa build hoặc `COPY` sai path | Kiểm tra build output và Docker context |
| `docker build` thành công nhưng app không chạy | ENTRYPOINT/runtime config sai | Chạy container, xem logs và exit code |
| App chạy trong container nhưng không gọi được DB ở `localhost` | `localhost` là container hiện tại | Kiểm tra DNS và container network |
| Container chạy nhưng host không truy cập được | Sai port mapping hoặc bind address | Kiểm tra `server.port`, `EXPOSE` và `-p` |
| Buildpacks không tìm thấy Docker endpoint | Container runtime chưa sẵn sàng hoặc endpoint sai | Kiểm tra builder runtime configuration |
| Build-image quá chậm | Cache miss, dependency download, builder hoặc native compilation | Quan sát build stages/cache |
| Image có hai Java runtimes | Dockerfile/base image chứa thành phần dư | Kiểm tra layers và runtime stage |
| Native compile lỗi reflection/resource | Thiếu reachability metadata | Kiểm tra runtime hints và library support |
| Native binary chạy trên máy build nhưng không chạy trên container | OS/libc/library/architecture mismatch | Kiểm tra target platform và linker dependencies |
| Native build đọc nhầm secret của CI | Static init/build-time config không phù hợp | Tách build-time và runtime properties |
| Native app không tìm thấy template/resource | Resource chưa được đưa vào binary | Khai báo resource hints phù hợp |
| Native app chạy nhưng throughput thấp | Workload hoặc optimization khác JVM | Benchmark sau warm-up với số liệu thực |
| Health check fail ngay khi startup | Probe timing/config chưa phù hợp | Phân biệt startup/readiness/liveness |
| Container không dừng graceful | Signal không tới process hoặc timeout quá ngắn | Kiểm tra ENTRYPOINT và orchestration |
| File upload mất khi container bị thay | Ghi vào writable layer không bền vững | Dùng volume/object storage |
| Test JVM pass nhưng native fail | Chưa test native artifact | Thêm smoke/integration tests native |
| Image chứa secret | Copy file config hoặc build args không an toàn | Kiểm tra image layers và secret workflow |

### Cách phân tích theo từng lớp

~~~text
Source/build
      |
      +--> Artifact có đúng không?
      |
Package/image
      |
      +--> Runtime và entrypoint có đúng không?
      |
Container/platform
      |
      +--> Network, filesystem, env và permissions có đúng không?
      |
Spring startup
      |
      +--> Environment, profiles, beans và dependencies có đúng không?
      |
Application behavior
      |
      +--> Nghiệp vụ, database, latency, health có đúng không?
~~~

Không nên sửa Spring configuration khi lỗi thực tế là container không có Java runtime. Ngược lại, không nên thay Docker base image để giải quyết một lỗi BeanCreationException do property sai mà chưa xác định nguyên nhân.

## 38. Chọn phương án nào?

Một cách ra quyết định thực dụng:

| Bối cảnh | Phương án thường đáng bắt đầu |
|---|---|
| Học Spring Boot hoặc xây dựng dự án nhỏ | Executable JAR + `java -jar` |
| Web service chuẩn triển khai trên container platform | JVM OCI image qua buildpacks hoặc Dockerfile |
| Tổ chức muốn ít Dockerfile tùy chỉnh | Spring Boot build-image/Cloud Native Buildpacks |
| Cần điều khiển runtime filesystem và system packages | Dockerfile với multi-stage build |
| Job ngắn, startup và memory cực kỳ quan trọng | Thử native executable, đo lợi ích |
| Ứng dụng dùng nhiều thư viện dynamic chưa hỗ trợ native tốt | JVM runtime thường dễ quản lý hơn |
| Cần process native chạy trực tiếp trên host | Native executable cho target OS/arch |
| Cần native cùng container orchestration | Native executable đóng trong OCI image |
| Đã chuẩn hóa CI trên JVM image và không có bottleneck | Giữ JVM, không tối ưu quá sớm |

### Một decision tree

~~~text
Ứng dụng cần triển khai bằng container?
           |
      +----+----+
      |         |
     Không      Có
      |         |
      v         v
JAR/native    Cần kiểm soát Dockerfile chi tiết?
trên host       |
            +---+---+
            |       |
           Có      Không
            |       |
            v       v
        Dockerfile  Buildpacks
            |       |
            +---+---+
                |
                v
     Cold start/memory có bottleneck thực?
                |
          +-----+-----+
          |           |
         Không        Có
          |           |
          v           v
      JVM image    Thử native build
                      |
                      v
           Compatibility + benchmark
                      |
                      v
          Chọn JVM/native theo số liệu
~~~

Đây là hướng suy nghĩ, không phải quy tắc bắt buộc. Một tổ chức có thể chọn Dockerfile vì compliance dù buildpacks thuận tiện hơn, hoặc chọn native để đáp ứng một ràng buộc sản phẩm cụ thể.

## 39. Một quy trình phát hành có thể dự đoán

Với dự án Spring Boot xây dựng cho production, có thể tổ chức pipeline:

~~~text
Source commit
     |
     v
Static checks + unit tests
     |
     v
Build artifact (JAR hoặc native)
     |
     v
Integration tests
     |
     v
Build OCI image
     |
     v
Image scan / SBOM / metadata
     |
     v
Push registry
     |
     v
Deploy staging bằng image digest
     |
     v
Smoke tests + health + load checks
     |
     v
Promote chính artifact sang production
     |
     v
Observe / rollback if needed
~~~

Nếu native được chọn, thêm native compatibility/smoke tests vào những bước cần thiết. Nếu JVM được chọn, xác nhận Java runtime được cung cấp đúng và cấu hình memory hợp với container.

### “Build once, deploy many” có giới hạn

Cùng một OCI image digest có thể được promote giữa môi trường nếu platform/architecture và runtime configuration phù hợp. Nhưng nếu cần nhiều target architectures hoặc các binary native khác nhau, phải phát hành những variant tương ứng và quản lý manifest/digest phù hợp.

Không nên nói “build một lần chạy mọi nơi” khi artifact đã gắn với OS, CPU hoặc system libraries cụ thể.

## 40. Những hiểu nhầm cần tránh

### “Build image nghĩa là build Native Image”

Sai. Spring Boot `build-image` thông thường tạo **OCI container image**. Nó có thể chứa JAR và Java runtime. GraalVM Native Image là một bước biên dịch riêng cần toolchain và cấu hình phù hợp.

### “Container là một native executable”

Sai. Container là môi trường chạy/instance của image. Container có thể chạy JVM process, native process hoặc những chương trình khác.

### “Native executable không cần Docker”

Đúng theo nghĩa nó có thể chạy trực tiếp trên host tương thích. Nhưng nếu tổ chức dùng Kubernetes hoặc container runtime, vẫn có thể đóng native binary trong OCI image.

### “Có Dockerfile là không cần Java runtime”

Sai nếu image chạy executable JAR. Trong trường hợp đó, image phải có Java runtime phù hợp.

### “Đóng gói JAR là đã deploy”

Sai. JAR là artifact. Còn cần runtime, cấu hình, secrets, networking, storage và process supervision.

### “Chạy native sẽ tự khắc phục vấn đề database”

Sai. Native thay đổi runtime/compilation, không thay đổi quy tắc transaction, consistency, network hoặc credential.

### “Native build lúc nào cũng nhỏ hơn, nhanh hơn”

Không nên giả định. Startup và memory có thể tốt hơn, nhưng build time, binary size và throughput phụ thuộc ứng dụng. Cần đo.

### “Một native binary có thể chạy mọi hệ điều hành”

Sai. Binary có target OS/CPU và những ràng buộc liên kết riêng.

### “Container image có mọi cấu hình production”

Không nên thiết kế như vậy. Secrets và runtime configuration nên được cấp lúc deploy/run, không được đóng cứng vào image.

### “Image chạy thành công là đủ để deploy production”

Chưa đủ. Cần kiểm tra readiness, graceful shutdown, resource limits, security, observability và backup/data lifecycle.

## 41. Checklist trước khi đóng gói Spring Boot

1. **Xác định artifact mục tiêu.** Executable JAR, WAR hoặc native binary?
2. **Xác định runtime.** JVM/JRE hay native process?
3. **Xác định cần container không.** OCI image và container chỉ là một lớp triển khai.
4. **Chọn Dockerfile hoặc buildpacks** dựa trên khả năng tùy biến và chuẩn vận hành.
5. **Kiểm tra artifact trong image** đúng version và đúng startup command.
6. **Kiểm tra OS/CPU architecture** và hệ điều hành target, đặc biệt với native.
7. **Quản lý Java/runtime versions đồng bộ** với build target.
8. **Đặt runtime config và secrets ngoài image** bằng cơ chế phù hợp.
9. **Không phụ thuộc localhost sai** khi kết nối services khác container.
10. **Kiểm tra cổng thực sự được publish** và bind address.
11. **Thiết kế readiness/liveness**, không đồng nhất container running với app ready.
12. **Dùng exec-form entrypoint và kiểm tra signal forwarding**.
13. **Cấu hình graceful shutdown** tương thích timeout của orchestrator.
14. **Không lưu dữ liệu bền vững trong writable layer** của container.
15. **Sử dụng non-root process khi khả thi**, kiểm soát quyền file và network.
16. **Thu thập log, metrics và traces**, tránh secret trong log.
17. **Scan và cập nhật dependency/base image**, lưu build metadata.
18. **Nếu dùng native, kiểm tra reflection/resources/proxies** và native integration tests.
19. **Đo hiệu năng bằng workload thật**, tách build time khỏi runtime performance.
20. **Triển khai artifact có thể truy vết bằng digest/version**, không dựa vào tag mutable ngoài kiểm soát.

## Kết luận

Spring Boot có nhiều khả năng đóng gói và triển khai, nhưng cần phân biệt đúng các tầng: **executable JAR** là artifact Java chạy qua JVM; **OCI container image** là gói gồm filesystem layers và thông tin chạy; **container** là instance được khởi tạo từ image; còn **native executable** là binary được Spring AOT/GraalVM Native Image hỗ trợ biên dịch cho nền tảng cụ thể.

`spring-boot:build-image` và `bootBuildImage` thường hướng tới tạo OCI image bằng buildpacks. Chúng không tự có nghĩa ứng dụng đã được biên dịch native. Dockerfile là cách khác để tạo OCI image. Cả hai cách có thể đóng gói JAR chạy trên JVM hoặc, khi được cấu hình và build thích hợp, một native binary.

Native executable có thể cải thiện startup và memory trong một số bài toán, nhưng đổi lại chi phí build, ràng buộc reachability/metadata và tính phụ thuộc nền tảng. Container giúp chuẩn hóa cách đóng gói và triển khai nhưng không thay thế quản lý cấu hình, dữ liệu, bảo mật hay khả năng quan sát.

Khi quyết định kiến trúc phát hành, hãy tách rõ **build artifact → image assembly → container runtime → Spring application lifecycle**, rồi chọn JVM hay native dựa trên số đo và khả năng tương thích của ứng dụng thực tế. Hiểu ranh giới này giúp thiết kế pipeline rõ ràng, xử lý sự cố đúng lớp và tránh tối ưu sai mục tiêu.
