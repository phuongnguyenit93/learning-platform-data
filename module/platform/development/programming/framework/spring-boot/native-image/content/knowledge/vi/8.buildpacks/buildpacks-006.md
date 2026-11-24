# Truyền cấu hình build mà không nhầm với biến môi trường lúc chạy

Khi đóng gói ứng dụng Spring Boot thành container image bằng **Cloud Native Buildpacks (CNB)**, cùng một tiến trình có thể nhận cấu hình ở hai thời điểm rất khác nhau: lúc build image và lúc container khởi chạy. Nhầm hai thời điểm này dễ dẫn tới các lỗi như đặt nhầm cổng trong build, mong rằng đổi profile runtime sẽ tạo thêm bean đã bị loại ở AOT, hoặc vô tình đóng gói credential vào image.

Buildpacks cung cấp biến môi trường cho buildpack trong giai đoạn tạo image. Với Paketo, nhiều biến cấu hình build có tiền tố **BP_**. Sau khi image đã tạo, runtime platform lại cung cấp biến môi trường cho tiến trình ứng dụng khi chạy. Paketo còn có một số quy ước riêng như **BPL_** cho thành phần runtime do buildpack cung cấp và **BPE_** để ghi biến môi trường khởi chạy vào image thông qua Environment Variables Buildpack.

Bài học này phân biệt các lớp cấu hình đó, minh họa cách truyền qua Gradle, Maven và pack, rồi kiểm tra giá trị mà Spring Boot thực sự nhận được trong native executable.

## 1. Hai thời điểm cấu hình trong vòng đời Buildpacks

Một container image được tạo ra trước khi ứng dụng chạy. Buildpacks nhận source hoặc artifact, phân tích ứng dụng, chọn buildpack phù hợp, thực hiện các bước build và xuất ra OCI image. Khi container bắt đầu, runtime platform khởi chạy process được khai báo trong image và cung cấp environment, arguments, network, volume cùng các tài nguyên khác.

~~~mermaid
flowchart TD
    A["Source / executable JAR"] --> B["Build platform: pack hoặc Spring Boot plugin"]
    B --> C["Builder và Buildpacks"]
    D["BP_* / build tool arguments"] --> C
    C --> E["Detect, Analyze, Restore, Build, Export"]
    E --> F["OCI image"]
    G["docker run / Kubernetes / Compose"] --> H["Runtime environment và arguments"]
    F --> H
    H --> I["Native executable và Spring Boot"]
    I --> J["ApplicationContext và nghiệp vụ"]
~~~

| Câu hỏi | Cấu hình build | Cấu hình runtime |
|---|---|---|
| Khi nào được đọc? | Trong lúc Buildpacks tạo image | Khi container/process khởi chạy |
| Ai thường đọc? | Buildpack, Maven/Gradle được gọi trong build, native-image compiler | Native executable, Spring Boot, thư viện ứng dụng và runtime component |
| Ví dụ | BP_NATIVE_IMAGE=true, BP_NATIVE_IMAGE_BUILD_ARGUMENTS | SERVER_PORT, SPRING_PROFILES_ACTIVE, SPRING_DATASOURCE_URL |
| Công cụ truyền | pack build --env, bootBuildImage.environment, cấu hình buildpack | docker run -e, Docker Compose, Kubernetes env/Secret |
| Có thể thay đổi mà không build lại image? | Thông thường không, vì ảnh hưởng quá trình tạo image | Có, nếu ứng dụng hỗ trợ đọc giá trị đó lúc chạy |

**Quy tắc quan trọng:** biến môi trường được truyền cho build container không tự động trở thành biến môi trường của container chạy ứng dụng. Chỉ những giá trị được buildpack chủ động ghi vào launch environment hoặc metadata của image mới có thể được giữ lại theo cách đó.

## 2. Ba nhóm tiền tố thường gặp trong Paketo

Các tiền tố dưới đây là quy ước của Paketo và những buildpack tương ứng; không phải mọi Buildpack của mọi nhà cung cấp đều hiểu chúng.

| Tiền tố | Giai đoạn | Ý nghĩa |
|---|---|---|
| BP_ | Build time | Cấu hình hành vi buildpack, ví dụ chọn native image hoặc truyền tham số cho compiler |
| BPL_ | Launch time | Cấu hình một số thành phần runtime do buildpack cung cấp, ví dụ thành phần JVM hoặc process hỗ trợ |
| BPE_ | Được khai báo lúc build, tác động khi launch | Yêu cầu Environment Variables Buildpack tạo hoặc chỉnh sửa biến môi trường khởi chạy trong image |

Ví dụ:

- BP_NATIVE_IMAGE=true: yêu cầu buildpack Java Native Image tạo native executable trong lúc build.
- BP_NATIVE_IMAGE_BUILD_ARGUMENTS=-O2: truyền tùy chọn cho lệnh native-image, không phải tham số Spring Boot.
- BPL_*: có thể cấu hình một số tính năng runtime của buildpack. Khi ứng dụng đã là native executable, không nên giả định các cờ dành riêng cho JVM như một số BPL_JVM_* sẽ có tác dụng.
- BPE_DEFAULT_SERVER_PORT=8080: với Paketo Environment Variables Buildpack, tạo giá trị mặc định SERVER_PORT trong launch environment của image. Giá trị này được lưu trong image và có thể bị thay thế khi container khởi chạy tùy quy tắc biến môi trường.

Ngoài các tiền tố, một số công cụ build có biến riêng như GRADLE_OPTS, MAVEN_OPTS, HTTP_PROXY hoặc HTTPS_PROXY. Cần xác định chính xác chương trình nào đọc biến đó và ở giai đoạn nào.

## 3. Cấu hình build native image bằng BP_NATIVE_IMAGE

Đối với Paketo Java Native Image Buildpack, BP_NATIVE_IMAGE là biến bật chế độ tạo native image. Giá trị cần được cung cấp **trong giai đoạn build** và builder phải có bộ buildpack hỗ trợ native image cùng native-image toolkit tương thích.

Với pack CLI:

~~~bash
pack build demo-orders:native \
  --builder paketobuildpacks/builder-jammy-tiny \
  --path . \
  --env BP_NATIVE_IMAGE=true
~~~

Đây là ví dụ minh họa. Builder tag phải tồn tại, hỗ trợ kiến trúc/stack mục tiêu và chứa hoặc có thể phân giải các buildpack cần thiết. Một số môi trường dùng builder khác hoặc pin digest để tái lập build. Không mặc định mọi builder đều hỗ trợ native image chỉ vì nó là builder Java.

Nếu buildpack không nhận diện được ứng dụng hoặc thiếu native-image toolkit, cần kiểm tra log detect/build và danh sách buildpack của builder. Việc đặt BP_NATIVE_IMAGE=true không tự cài đặt mọi thành phần cần thiết cho một builder tùy chỉnh.

## 4. Truyền cấu hình Buildpacks qua Spring Boot Gradle plugin

Spring Boot Gradle plugin cung cấp task bootBuildImage. Thuộc tính environment của task là các biến môi trường được truyền cho **builder trong lúc tạo image**.

Với Groovy DSL trong build.gradle:

~~~groovy
tasks.named("bootBuildImage") {
    imageName = "example/demo-orders:native"
    builder = "paketobuildpacks/builder-jammy-tiny"

    environment = [
        "BP_NATIVE_IMAGE": "true",
        "BP_NATIVE_IMAGE_BUILD_ARGUMENTS": "-O2"
    ]
}
~~~

Với Kotlin DSL trong build.gradle.kts:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName = "example/demo-orders:native"
    builder = "paketobuildpacks/builder-jammy-tiny"

    environment = mapOf(
        "BP_NATIVE_IMAGE" to "true",
        "BP_NATIVE_IMAGE_BUILD_ARGUMENTS" to "-O2"
    )
}
~~~

Sau đó chạy:

~~~bash
./gradlew bootBuildImage
~~~

BP_NATIVE_IMAGE_BUILD_ARGUMENTS ở ví dụ trên được buildpack chuyển cho native-image compiler. Tùy chọn -O2 là ví dụ; các tùy chọn hợp lệ phụ thuộc native-image toolkit và phiên bản. Hãy bắt đầu với cấu hình mặc định, chỉ thêm cờ khi có lý do và đã kiểm thử kết quả.

Trong một số phiên bản Spring Boot Gradle plugin, khi GraalVM Native Image plugin được áp dụng, bootBuildImage có thể tự đặt BP_NATIVE_IMAGE=true và chọn builder mặc định phù hợp. Hành vi mặc định phụ thuộc phiên bản và cấu hình dự án. Khi muốn build có thể đọc và tái lập dễ dàng, hãy kiểm tra log task và cấu hình thực tế thay vì dựa vào giả định.

**Điểm phân biệt:** bootBuildImage.environment không phải System.getenv() của ứng dụng khi container chạy. Đây là environment được gửi tới builder trong giai đoạn build. Muốn ứng dụng nhận SERVER_PORT lúc chạy, hãy cấu hình ở runtime hoặc chủ động dùng cơ chế BPE để tạo giá trị launch mặc định.

## 5. Truyền cấu hình qua Spring Boot Maven plugin

Maven plugin có cấu hình image environment tương tự. Ví dụ trong pom.xml:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <image>
            <name>example/demo-orders:native</name>
            <builder>paketobuildpacks/builder-jammy-tiny</builder>
            <env>
                <BP_NATIVE_IMAGE>true</BP_NATIVE_IMAGE>
                <BP_NATIVE_IMAGE_BUILD_ARGUMENTS>-O2</BP_NATIVE_IMAGE_BUILD_ARGUMENTS>
            </env>
        </image>
    </configuration>
</plugin>
~~~

Chạy:

~~~bash
./mvnw spring-boot:build-image
~~~

Các phần tử trong env được truyền tới builder trong quá trình tạo image. Chúng không phải thuộc tính Spring Boot runtime. Nếu muốn thay đổi cổng web hoặc datasource URL khi container chạy, hãy cấu hình qua Docker/Kubernetes hoặc cơ chế launch environment được hỗ trợ.

Khi dự án cần profile Maven để chuẩn bị artifact hoặc chạy AOT, hãy phân biệt profile Maven của quá trình build với SPRING_PROFILES_ACTIVE của ứng dụng. Profile Maven có thể thay đổi dependency, plugin và nội dung artifact; active profile Spring Boot ở runtime điều khiển cấu hình ứng dụng theo khả năng của image đã tạo.

## 6. Cấu hình trực tiếp bằng pack build

pack là CLI phổ biến để gọi CNB lifecycle. Cờ --env truyền một biến môi trường vào **build container**:

~~~bash
pack build example/demo-orders:native \
  --builder paketobuildpacks/builder-jammy-tiny \
  --path . \
  --env BP_NATIVE_IMAGE=true \
  --env BP_NATIVE_IMAGE_BUILD_ARGUMENTS="-O2"
~~~

Một số biến Paketo hữu ích khác:

| Biến | Mục đích |
|---|---|
| BP_NATIVE_IMAGE | Bật build native image |
| BP_NATIVE_IMAGE_BUILD_ARGUMENTS | Truyền arguments cho native-image |
| BP_NATIVE_IMAGE_BUILD_ARGUMENTS_FILE | Chỉ định file chứa arguments theo định dạng argument file |
| BP_NATIVE_IMAGE_BUILT_ARTIFACT | Chỉ rõ artifact đầu vào khi build từ executable JAR trong tình huống cần chỉ định rõ |
| BP_GRADLE_BUILD_ARGUMENTS | Chỉ định arguments cho lệnh Gradle mà buildpack gọi |
| BP_GRADLE_ADDITIONAL_BUILD_ARGUMENTS | Bổ sung arguments cho lệnh Gradle theo hỗ trợ của buildpack |
| BP_MAVEN_BUILD_ARGUMENTS | Chỉ định arguments cho lệnh Maven mà buildpack gọi |
| BP_LOG_LEVEL | Điều chỉnh mức log buildpack nếu buildpack hỗ trợ, ví dụ DEBUG |

Các biến BP_GRADLE_* và BP_MAVEN_* tác động đến **quá trình build tool bên trong builder**. Ví dụ, BP_GRADLE_BUILD_ARGUMENTS có thể điều khiển task Gradle được gọi; nó không phải tham số --server.port cho ứng dụng sau khi image chạy.

Định dạng và hỗ trợ chính xác phụ thuộc phiên bản Paketo buildpack. Khi cần tùy chỉnh sâu, xem reference của component buildpack mà builder đang dùng.

## 7. Phân biệt arguments của build tool và native-image compiler

Một build native có thể có nhiều lớp lệnh:

~~~text
CNB platform
   |
   +-- Buildpack configuration: BP_*
          |
          +-- Build tool (Maven/Gradle)
          |      BP_GRADLE_BUILD_ARGUMENTS
          |      BP_MAVEN_BUILD_ARGUMENTS
          |
          +-- Native Image compiler
                 BP_NATIVE_IMAGE_BUILD_ARGUMENTS

Container launch
   |
   +-- Application process
          SERVER_PORT
          SPRING_PROFILES_ACTIVE
          --server.port=...
~~~

Ví dụ, ba giá trị sau có ý nghĩa khác nhau:

| Giá trị | Ai nhận | Tác dụng |
|---|---|---|
| BP_GRADLE_BUILD_ARGUMENTS=--no-daemon bootJar | Gradle được gọi trong builder | Điều khiển lệnh build artifact |
| BP_NATIVE_IMAGE_BUILD_ARGUMENTS=-O2 | Native Image compiler | Điều khiển tối ưu hóa khi biên dịch native |
| SERVER_PORT=8085 ở container runtime | Spring Boot trong tiến trình ứng dụng | Chọn cổng server lúc chạy |

Không đặt --server.port=8085 vào BP_NATIVE_IMAGE_BUILD_ARGUMENTS: compiler sẽ hiểu đó là đối số của chính native-image và có thể báo lỗi. Tương tự, không đặt -O2 vào SERVER_PORT hay tham số ứng dụng.

Một cách ghi nhớ: **build tool tạo artifact, native-image compiler tạo executable, runtime config điều khiển ứng dụng đang chạy.**

## 8. Các giá trị nào được lưu vào image?

Không phải mọi biến môi trường của build đều được lưu trong image. Buildpack đọc biến cấu hình ở build time và có thể dùng nó để tạo layer, metadata hoặc launch environment. Việc biến có xuất hiện ở runtime hay không phụ thuộc chức năng của buildpack.

| Nguồn | Mặc định có trong launch environment? | Ghi chú |
|---|---|---|
| BP_NATIVE_IMAGE=true | Không | Chỉ yêu cầu build native image |
| BP_NATIVE_IMAGE_BUILD_ARGUMENTS | Không | Chỉ phục vụ compiler |
| BP_GRADLE_BUILD_ARGUMENTS | Không | Chỉ điều khiển Gradle build |
| SERVER_PORT đặt trong shell chạy pack build | Không tự động | Buildpack không tự chuyển mọi env của build thành runtime env |
| BPE_DEFAULT_SERVER_PORT=8080 | Có, nếu Environment Variables Buildpack được dùng và hỗ trợ | Tạo giá trị mặc định khi launch |
| SERVER_PORT đặt bằng docker run -e | Có trong tiến trình container đó | Chỉ có hiệu lực cho lần chạy container |

Có thể kiểm tra cấu hình image bằng công cụ container và metadata Buildpacks, nhưng không nên giả định docker inspect hiển thị đầy đủ mọi biến động được tính bởi launcher/profile script. Hãy xác minh bằng cách chạy ứng dụng và quan sát cấu hình thực tế.

## 9. Dùng BPE_* để nhúng giá trị mặc định vào launch environment

Paketo Environment Variables Buildpack cho phép thêm hoặc sửa biến môi trường được thiết lập khi image launch. Đây là một **tác vụ ở build time với kết quả dành cho runtime**.

Ví dụ, BPE_DEFAULT_SERVER_PORT yêu cầu đặt mặc định SERVER_PORT nếu lúc launch chưa có giá trị khác:

~~~bash
pack build example/demo-orders:native \
  --builder paketobuildpacks/builder-jammy-tiny \
  --path . \
  --env BP_NATIVE_IMAGE=true \
  --env BPE_DEFAULT_SERVER_PORT=8080
~~~

Ví dụ này chỉ hoạt động khi builder có Paketo Environment Variables Buildpack hoặc buildpack tương đương hỗ trợ các biến BPE. Các hành động thường gặp:

| Biến | Hành động khi launch |
|---|---|
| BPE_SERVER_PORT | Đặt SERVER_PORT theo giá trị đã cấu hình |
| BPE_OVERRIDE_SERVER_PORT | Ghi đè SERVER_PORT |
| BPE_DEFAULT_SERVER_PORT | Chỉ đặt mặc định nếu SERVER_PORT chưa được đặt |
| BPE_APPEND_PATH | Nối thêm vào PATH |
| BPE_PREPEND_PATH | Thêm vào đầu PATH |
| BPE_DELIM_PATH | Chọn delimiter cho thao tác nối/thêm, ví dụ : |

Cần xác minh cú pháp với phiên bản Environment Variables Buildpack của builder. Các biến BPE không phải quy ước chung của mọi CNB builder.

**Không dùng BPE để nhúng mật khẩu, access token, private key hoặc credential.** Giá trị được ghi vào image/layer hoặc metadata liên quan và có thể bị người có quyền đọc image truy cập. Chỉ dùng cho giá trị mặc định không nhạy cảm, ví dụ cổng, chế độ hiển thị hoặc locale.

## 10. Cấu hình runtime đúng cách với Docker

Sau khi image đã được tạo, dùng docker run -e để truyền environment vào container. Đây là thời điểm cấu hình runtime:

~~~bash
docker run --rm \
  --name demo-orders \
  --publish 8085:8085 \
  --env SERVER_PORT=8085 \
  --env SPRING_PROFILES_ACTIVE=staging \
  --env DEMO_MESSAGE="runtime-value" \
  example/demo-orders:native
~~~

Trong ví dụ:

- SERVER_PORT là biến Spring Boot đọc để cấu hình cổng.
- SPRING_PROFILES_ACTIVE chọn profile Spring khi ứng dụng khởi chạy, nếu profile đó có trong cấu hình mà image hỗ trợ.
- DEMO_MESSAGE là biến tùy biến; ứng dụng phải khai báo binding hoặc đọc property tương ứng thì giá trị mới có tác dụng.
- --publish 8085:8085 ánh xạ cổng host tới cổng container; nó không tự đặt server.port.

Đối với native executable, các biến môi trường thông thường vẫn được hệ điều hành cung cấp cho tiến trình. Spring Boot có thể đọc chúng qua Environment, @Value hoặc @ConfigurationProperties, miễn là property và code binding có trong image.

### Runtime arguments

Một số image cho phép truyền thêm command arguments khi khởi chạy. Tuy nhiên, cách Docker nối arguments với ENTRYPOINT và CMD phụ thuộc image configuration. Trước khi thêm --server.port=..., kiểm tra process mặc định của image; nếu command bị thay thế thay vì nối thêm, có thể vô tình bỏ qua launcher hoặc lệnh khởi động đã được Buildpacks tạo.

Với ứng dụng native, không có JVM launcher để nhận các cờ HotSpot như cách chạy java -jar. Hãy dùng application arguments Spring Boot và biến môi trường thông thường, hoặc các tùy chọn native runtime đã được xác nhận cho đúng GraalVM version.

## 11. Dùng Docker Compose cho cấu hình runtime

Có thể quản lý các biến runtime trong file Compose:

~~~yaml
services:
  orders:
    image: example/demo-orders:native
    ports:
      - "8085:8085"
    environment:
      SERVER_PORT: "8085"
      SPRING_PROFILES_ACTIVE: "staging"
      DEMO_MESSAGE: "from-compose"
~~~

Chạy:

~~~bash
docker compose up
~~~

Các giá trị trong environment được cấp cho container lúc khởi chạy. Nếu thay đổi chúng, thông thường không cần build lại image; chỉ cần recreate container với cấu hình mới.

Với credential, dùng Docker secrets hoặc secret manager phù hợp với nền tảng. Không đưa secret vào Dockerfile, build arguments, BP_*, BPE_*, file cấu hình được commit hoặc image layer. Trong môi trường production, Kubernetes Secret, Vault hay dịch vụ quản lý secret của cloud thường phù hợp hơn việc ghi password trực tiếp vào Compose file.

## 12. Profile Spring Boot và cấu trúc đã xử lý bởi AOT

Đổi SPRING_PROFILES_ACTIVE lúc chạy có thể thay đổi các property và cấu hình runtime mà ứng dụng đã đóng gói hỗ trợ. Tuy nhiên, với native image, **không thể giả định profile runtime sẽ tái tạo mọi bean mà Spring AOT không đưa vào image**.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class StorageConfiguration {

    @Bean
    @Profile("local")
    StorageClient localStorageClient() {
        return new LocalStorageClient();
    }

    @Bean
    @Profile("production")
    StorageClient productionStorageClient() {
        return new RemoteStorageClient();
    }
}
~~~

Giả sử quá trình AOT tạo image theo môi trường chỉ nhận diện cấu hình local. Khi container khởi chạy với SPRING_PROFILES_ACTIVE=production, bean productionStorageClient có thể không khả dụng vì lớp/đường tạo bean tương ứng chưa được đưa vào image theo cấu hình AOT đó.

Cần phân biệt:

| Loại cấu hình | Ví dụ | Có thể đổi lúc chạy? |
|---|---|---|
| Giá trị thuộc tính của bean đã có | URL dịch vụ, timeout, cổng | Thường có, nếu ứng dụng đọc từ Spring Environment |
| Profile ảnh hưởng cấu trúc bean tại AOT | @Profile tạo bean khác nhau | Phụ thuộc cấu hình và khả năng hỗ trợ; không mặc định đổi được |
| Native Image build argument | BP_NATIVE_IMAGE_BUILD_ARGUMENTS | Không; muốn đổi cần build lại image |
| Biến launch thông thường | SERVER_PORT, DEMO_MESSAGE | Có, khi container được tạo lại với giá trị mới |

Đối với nhiều tập bean theo môi trường, cần thiết kế cấu hình AOT/build phù hợp và kiểm thử từng image. Không dùng biến môi trường runtime để thay thế một bước build cần thiết.

## 13. Build arguments có thể ảnh hưởng gì đến kết quả native?

BP_NATIVE_IMAGE_BUILD_ARGUMENTS truyền tùy chọn trực tiếp cho native-image compiler. Các tham số như mức tối ưu hóa, báo cáo phân tích hoặc cấu hình heap build có thể làm thay đổi thời gian build, tài nguyên tiêu thụ, kích thước executable hoặc hành vi chẩn đoán.

Ví dụ minh họa:

~~~bash
pack build example/demo-orders:native \
  --builder paketobuildpacks/builder-jammy-tiny \
  --path . \
  --env BP_NATIVE_IMAGE=true \
  --env BP_NATIVE_IMAGE_BUILD_ARGUMENTS="-O2"
~~~

Đây là cờ compiler. Không dùng nó để cấu hình server.port, datasource hay Spring profile. Tương tự, biến BP_NATIVE_IMAGE_BUILD_ARGUMENTS_FILE có thể chỉ tới file argument theo định dạng mà native-image hỗ trợ; file phải hiện diện trong build context ở vị trí buildpack có thể đọc.

Một số tùy chọn compiler có thể không được hỗ trợ ở toolkit hoặc phiên bản hiện tại. Luôn xem log build, phiên bản toolkit trong image/SBOM và tài liệu tương ứng. Khi thêm cờ, ghi lại cấu hình cùng kết quả đo để build có thể tái lập.

## 14. Thay đổi build config có cần build lại image không?

Hãy dùng bảng quyết định sau:

| Thay đổi | Cần build lại image? | Lý do |
|---|---|---|
| Đổi BP_NATIVE_IMAGE_BUILD_ARGUMENTS | Có | Compiler tạo executable khác |
| Đổi builder hoặc run image | Có | Thành phần nền của image thay đổi |
| Đổi BP_GRADLE_BUILD_ARGUMENTS và nội dung artifact | Có | Artifact đầu vào thay đổi |
| Đổi SERVER_PORT qua docker run -e | Không | Giá trị được truyền khi khởi chạy |
| Đổi SPRING_PROFILES_ACTIVE runtime | Không cần build lại về mặt thao tác, nhưng chỉ hoạt động nếu image hỗ trợ cấu trúc profile đó | Giá trị được cung cấp lúc chạy; cấu trúc AOT vẫn có giới hạn |
| Đổi BPE_DEFAULT_SERVER_PORT | Có | Launch environment mặc định được ghi vào image |
| Đổi secret qua nền tảng runtime | Không | Secret được cấp khi container khởi chạy |
| Đổi resource hoặc code ứng dụng | Có | Nội dung image phải được cập nhật |

Quy tắc hữu ích: **nếu thay đổi làm thay đổi executable, dependency, builder layer hoặc launch metadata được nhúng vào image thì phải tạo image mới. Nếu chỉ đổi dữ liệu runtime được container cung cấp thì có thể dùng lại image hiện có.**

## 15. Bảo mật: không đóng gói secret vào image

Một lỗi nghiêm trọng là truyền database password qua biến build rồi vô tình ghi lại nó vào layer, build log, cache hoặc metadata. Image thường được lưu trong registry và có thể được tải bởi nhiều môi trường; credential đã nhúng vào image sẽ khó thu hồi hơn một secret runtime.

Không nên:

~~~bash
# Không làm theo: credential có thể lộ trong shell history/log/layer.
pack build example/demo-orders:native \
  --env BP_DATABASE_PASSWORD=super-secret \
  --env BPE_DEFAULT_SPRING_DATASOURCE_PASSWORD=super-secret
~~~

Nên cung cấp secret tại runtime thông qua cơ chế phù hợp của nền tảng. Ví dụ minh họa với biến môi trường (chỉ để diễn giải luồng, không phải cách quản lý secret tối ưu cho production):

~~~bash
docker run --rm \
  --env SPRING_DATASOURCE_URL \
  --env SPRING_DATASOURCE_USERNAME \
  --env SPRING_DATASOURCE_PASSWORD \
  example/demo-orders:native
~~~

Các giá trị phải được cung cấp bởi môi trường chạy hoặc secret manager. Không ghi password thật trong lệnh, script được commit hoặc tài liệu học tập.

Nếu một build thực sự cần secret để tải dependency riêng, ưu tiên **CNB bindings** hoặc cơ chế secret của CI/build platform mà buildpack hỗ trợ. Binding có thể cung cấp dữ liệu cho build process mà không phải biến nó thành cấu hình mặc định của ứng dụng. Cách khai báo và quyền truy cập binding phụ thuộc platform và buildpack; không giả định mọi builder xử lý cùng loại binding.

## 16. Chẩn đoán khi cấu hình không có tác dụng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Native image không được tạo | BP_NATIVE_IMAGE không được truyền ở build time, builder thiếu buildpack native | Xem log detect/build và builder metadata |
| Buildpack không nhận BP_NATIVE_IMAGE_BUILD_ARGUMENTS | Sai tên biến hoặc biến không đến đúng build environment | Kiểm tra cấu hình bootBuildImage, pack --env và log build |
| Compiler báo lỗi với -O2 hoặc cờ khác | Cờ không hợp lệ với native-image toolkit/version | Kiểm tra native-image version và cú pháp |
| Đổi SERVER_PORT trong terminal trước pack build nhưng container vẫn dùng cổng cũ | Biến chỉ ở build time và không tự được lưu vào image | Đặt SERVER_PORT khi chạy container |
| BP_NATIVE_IMAGE=true đặt bằng docker run -e nhưng không tạo native image | Đã đặt biến ở sai giai đoạn | Truyền BP_NATIVE_IMAGE cho builder khi build lại |
| BPE_DEFAULT_SERVER_PORT không có tác dụng | Builder không có Environment Variables Buildpack hoặc không nhận BPE | Kiểm tra buildpack list và launch environment |
| BPL_* không tác động đến ứng dụng native | Biến chỉ điều khiển thành phần runtime do buildpack cung cấp, có thể là JVM | Xác định ứng dụng là native hay JVM và buildpack nào đọc biến |
| Profile mới làm thiếu bean | Cấu trúc bean đã được xử lý ở AOT theo môi trường khác | Kiểm tra AOT/build profile và tập bean trong image |
| Image chứa credential | Đã nhúng secret qua BPE hoặc build layer/log | Thu hồi/rotate secret, build image sạch và rà soát registry/log/cache |

Khi debug, bật BP_LOG_LEVEL=DEBUG ở build time nếu các buildpack trong builder hỗ trợ. Mức log này giúp quan sát quá trình buildpack, không phải mức log Spring Boot của ứng dụng. Log build cũng có thể chứa đường dẫn, tham số và thông tin môi trường; cần kiểm soát quyền truy cập.

## 17. Thực hành: build một image và đổi cấu hình runtime

Mục tiêu: tạo một native image duy nhất, sau đó thay đổi cổng và profile ở runtime mà không build lại.

### Bước 1 — Chuẩn bị ứng dụng

Ứng dụng Spring Boot có endpoint /runtime-info trả về một property không nhạy cảm:

~~~java
@RestController
class RuntimeInfoController {
    private final Environment environment;

    RuntimeInfoController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/runtime-info")
    Map<String, String> info() {
        return Map.of(
            "message", environment.getProperty("demo.message", "unset"),
            "profile", String.join(",", environment.getActiveProfiles())
        );
    }
}
~~~

Giả sử dự án đã có Spring Web, cấu hình AOT/native tương thích và endpoint được đưa vào executable.

### Bước 2 — Build image

~~~bash
pack build example/runtime-lab:native \
  --builder paketobuildpacks/builder-jammy-tiny \
  --path . \
  --env BP_NATIVE_IMAGE=true
~~~

Hoặc cấu hình bootBuildImage.environment trong Gradle rồi chạy ./gradlew bootBuildImage. Ghi lại builder và phiên bản buildpack đã sử dụng.

### Bước 3 — Chạy cùng image với runtime config thứ nhất

~~~bash
docker run --rm \
  --publish 8081:8081 \
  --env SERVER_PORT=8081 \
  --env SPRING_PROFILES_ACTIVE=staging \
  --env DEMO_MESSAGE=first-run \
  example/runtime-lab:native
~~~

Gọi endpoint:

~~~bash
curl http://localhost:8081/runtime-info
~~~

### Bước 4 — Chạy lại cùng image với giá trị khác

Dừng container trước, rồi chạy:

~~~bash
docker run --rm \
  --publish 8082:8082 \
  --env SERVER_PORT=8082 \
  --env SPRING_PROFILES_ACTIVE=production \
  --env DEMO_MESSAGE=second-run \
  example/runtime-lab:native
~~~

Gọi endpoint trên cổng 8082. Hai lần chạy sử dụng **cùng image** nhưng nhận cấu hình runtime khác nhau. Profile thứ hai chỉ hợp lệ nếu image đã được build với cấu trúc bean và code tương thích.

### Bước 5 — Thử nhầm giai đoạn để nhận biết

Đặt SERVER_PORT=8083 trước lệnh pack build, nhưng không cấu hình BPE hoặc không đưa biến vào launch metadata. Sau khi image được tạo, chạy container mà không truyền SERVER_PORT; không kỳ vọng ứng dụng tự dùng 8083. Sau đó truyền SERVER_PORT=8083 bằng docker run -e và xác nhận kết quả.

### Bảng ghi nhận

| Thử nghiệm | Biến được đặt ở đâu? | Có cần build lại? | Kết quả kỳ vọng |
|---|---|---|---|
| Bật native image | BP_NATIVE_IMAGE trong build | Có | Buildpack tạo executable native |
| Đổi compiler option | BP_NATIVE_IMAGE_BUILD_ARGUMENTS trong build | Có | Compiler chạy với option mới |
| Đổi port | SERVER_PORT khi chạy container | Không | Spring Boot nhận cổng mới |
| Đổi profile | SPRING_PROFILES_ACTIVE khi chạy container | Không về mặt thao tác; phụ thuộc cấu trúc AOT | Profile được kích hoạt nếu image hỗ trợ |
| Đặt mặc định launch | BPE_DEFAULT_SERVER_PORT trong build | Có | Image có default cho launch |
| Đổi secret | Secret runtime/platform | Không | Ứng dụng nhận credential từ môi trường chạy |

## 18. Quy trình kiểm tra trước khi phát hành

Trước khi publish một image native, có thể rà soát theo thứ tự:

1. **Xác nhận builder:** builder hỗ trợ native image, đúng kiến trúc và tương thích run image.
2. **Xác nhận build configuration:** ghi lại BP_NATIVE_IMAGE, native-image arguments, build tool arguments và phiên bản toolkit.
3. **Rà soát thông tin nhạy cảm:** không có password/token trong BP_*, BPE_*, image labels, log hoặc file build.
4. **Kiểm tra launch configuration:** các giá trị mặc định không nhạy cảm được nhúng có chủ đích; giá trị theo môi trường được cấp qua runtime platform.
5. **Kiểm tra cấu trúc AOT:** các bean/profile/conditional cần dùng trong môi trường đích có mặt trong image.
6. **Chạy smoke test:** khởi động image, kiểm tra health endpoint, cổng, profile, datasource và nghiệp vụ quan trọng.
7. **Ghi nhận artifact:** image tag/digest, builder, buildpack versions, commit và cấu hình build để có thể tái lập.

Không dùng tag latest làm bằng chứng duy nhất về phiên bản builder. Với pipeline phát hành, pin builder/run image theo tag cụ thể hoặc digest theo chính sách của tổ chức để giảm thay đổi ngoài dự kiến.

## 19. Nguyên tắc ghi nhớ

- **BP_* cấu hình quá trình tạo image**; BP_NATIVE_IMAGE bật native image và BP_NATIVE_IMAGE_BUILD_ARGUMENTS dành cho compiler.
- **BP_GRADLE_* và BP_MAVEN_* điều khiển build tool** bên trong build container, không cấu hình Spring Boot runtime.
- **Biến runtime** như SERVER_PORT, SPRING_PROFILES_ACTIVE và SPRING_DATASOURCE_URL nên được cấp khi container khởi chạy.
- **BPL_* và BPE_* là quy ước Paketo có mục đích riêng**; kiểm tra buildpack thực tế có hỗ trợ trước khi dùng.
- **BPE có thể ghi giá trị vào image**; chỉ dùng cho cấu hình mặc định không nhạy cảm.
- **Secret nên được cấp qua runtime secret manager hoặc binding phù hợp**, tránh lưu trong layer, image, log và build arguments.
- **Spring AOT quyết định một phần cấu trúc bean từ lúc build**; đổi profile lúc chạy không tự tạo lại bean đã không được đưa vào native image.

### Tài liệu tham khảo

- Paketo — How to Configure Buildpacks: https://paketo.io/docs/howto/configuration/
- Paketo — How to Build Java Apps with Buildpacks: https://paketo.io/docs/howto/java/
- Paketo — Java Native Image Buildpack Reference: https://paketo.io/docs/reference/java-native-image-reference/
- Spring Boot Gradle Plugin Reference: https://docs.spring.io/spring-boot/gradle-plugin/packaging.html#packaging.container-images.buildpacks
- Spring Boot Maven Plugin Reference: https://docs.spring.io/spring-boot/maven-plugin/build-image.html

Tên biến, builder mặc định và cách cấu hình plugin có thể thay đổi theo phiên bản. Khi áp dụng vào dự án, đối chiếu reference của phiên bản Spring Boot, CNB platform và Paketo buildpack thực tế được dùng.
