# Đóng gói cache cho container và kiểm soát đường dẫn trong môi trường triển khai

## Mục tiêu bài học

**Ahead-of-Time Cache (AOT cache)** của HotSpot JVM chỉ mang lại lợi ích khi cache được tạo cho đúng ứng dụng, đúng JDK và đúng nền tảng triển khai. Khi đóng gói Java vào Docker hoặc Kubernetes, một file `.aot` được tạo thành công ở máy build vẫn có thể không được sử dụng nếu nó không được đưa vào image cuối, đường dẫn runtime khác với đường dẫn training, classpath bị thay đổi, file không có quyền đọc hoặc volume mount che khuất file đã đóng gói.

Bài **Đóng gói cache cho container và kiểm soát đường dẫn trong môi trường triển khai** thuộc chương **Vận hành AOT** của module **JAVA_VERSION_JAVA25**. Nội dung tập trung vào cách đưa cache vào container image, kiểm soát đường dẫn, quyền file, image layers, volume mounts, Kubernetes và quy trình kiểm tra khi deploy.

Sau bài này, bạn có thể:

1. Giải thích vì sao AOT cache cần gắn với application artifact, JDK release, hệ điều hành và kiến trúc CPU.
2. Tạo cache ngay trong Docker build bằng Spring Boot executable JAR layering.
3. Phân biệt training startup-only với training có workload production-like để tận dụng method profiles của Java 25.
4. Đặt đường dẫn cache rõ ràng, bảo đảm file có trong image cuối và process runtime đọc được.
5. Tránh lỗi do working directory, file permissions, non-root user, read-only root filesystem và volume mount.
6. Triển khai cache theo từng image/version/platform trong Kubernetes, đồng thời kiểm tra cache bằng JVM logging và fail-fast mode.
7. Thiết kế CI/CD để tái tạo cache sau mỗi lần thay đổi JDK, dependency, build hoặc kiến trúc nền tảng.

> **Phiên bản và phạm vi:** các lệnh JVM chính sử dụng Java 25 trở lên. AOT cache được giới thiệu trong JDK 24; Java 25 có one-command workflow và method profiling. Từ JDK 26, JEP 516 mở rộng AOT object caching cho mọi garbage collector, gồm ZGC. Các ví dụ container dùng Linux image và đường dẫn POSIX; nếu build trên Windows bằng Docker Desktop, đường dẫn bên trong container vẫn là đường dẫn Linux.

## 1. AOT cache phải đi cùng artifact triển khai

AOT cache là file dữ liệu do HotSpot tạo ra trong giai đoạn training/assembly. Khi ứng dụng production khởi động, JVM đọc file đó qua tùy chọn `-XX:AOTCache`.

Một cache được tạo thành công chưa đủ để kết luận image production dùng được cache. Cache phụ thuộc vào ba nhóm đầu vào:

- **Ứng dụng:** classpath, JAR hoặc module path, thứ tự JAR và nội dung artifact.
- **JDK:** phiên bản JDK tương thích với cache.
- **Nền tảng:** hệ điều hành và kiến trúc CPU.

Nếu một trong các yếu tố này thay đổi, cần tạo cache mới. Với container, cách an toàn là xem `.aot` như **một phần của cùng release artifact** với JAR/layer ứng dụng và runtime image đã dùng để tạo cache.

~~~mermaid
flowchart LR
    SRC["Source + dependencies"] --> BUILD["Build executable JAR"]
    BUILD --> LAYER["Extract Spring Boot layers"]
    LAYER --> TRAIN["AOT training trên runtime layout"]
    TRAIN --> CACHE["app.aot"]
    CACHE --> IMAGE["Final image<br/>application + app.aot"]
    IMAGE --> POD["Container / Pod"]
    POD --> JVM["JVM đọc cache<br/>-XX:AOTCache"]
~~~

Không nên dùng một file cache chung cho nhiều ứng dụng, nhiều bản release hoặc nhiều kiến trúc CPU. Một volume tên `shared-aot-cache` được nhiều deployment ghi đè có thể khiến Pod mới đọc cache của Pod cũ.

### 1.1. Manifest nhận diện cache

Mỗi image hoặc release nên ghi nhận tối thiểu:

| Trường | Ví dụ |
|---|---|
| Application version | `shop-service:2.4.0` |
| Image digest | Digest của image đã phát hành |
| JDK distribution/build | Nhà cung cấp và build JDK 25 cụ thể |
| OS / architecture | `linux/amd64` |
| Application artifact | Tên và checksum JAR/layers |
| Cache path | `/application/app.aot` |
| Training profile | `aot-training` |
| Training workload | `checkout-smoke-v4` |
| Cache validation | Kết quả chạy `AOTMode=on` |
| Benchmark | Startup p50/p95 và warm-up throughput |

Các trường này là quy ước quản lý artifact của dự án, không phải định dạng manifest bắt buộc của JVM. Mục đích là có thể truy ngược cache được tạo từ JDK, app và workload nào.

## 2. Chọn vị trí lưu cache trong container

Một container có nhiều lớp filesystem và nhiều nguồn mount. Cần xác định chính xác file được tạo ở đâu và JVM sẽ đọc ở đâu.

Ví dụ, Dockerfile đặt:

~~~dockerfile
WORKDIR /application
~~~

Khi training dùng:

~~~bash
java -XX:AOTCacheOutput=app.aot -jar application.jar
~~~

file cache được ghi theo working directory hiện hành, tức `/application/app.aot` trong ví dụ. Khi production chạy:

~~~bash
java -XX:AOTCache=app.aot -jar application.jar
~~~

đường dẫn tương đối cũng phụ thuộc working directory của process tại thời điểm chạy. Nếu ENTRYPOINT, `WORKDIR` hoặc cách gọi Java thay đổi, JVM có thể tìm file ở một thư mục khác.

**Khuyến nghị:** dùng đường dẫn tuyệt đối ở cả training và production:

~~~bash
java -XX:AOTCacheOutput=/application/app.aot -jar application.jar
~~~

~~~bash
java -XX:AOTCache=/application/app.aot -jar application.jar
~~~

Đường dẫn tuyệt đối làm rõ contract giữa Dockerfile, image, Kubernetes manifest và log vận hành. Nếu chọn `/opt/aot/app.aot`, hãy tạo thư mục và bảo đảm file được copy hoặc mount đúng vào đó.

### 2.1. Kiểm tra bốn điều kiện của đường dẫn

| Điều kiện | Câu hỏi | Cách kiểm tra |
|---|---|---|
| File tồn tại | Cache có nằm trong final image không? | `test -r /application/app.aot` |
| Đúng vị trí | JVM option có trỏ tới cùng file training không? | Dùng absolute path trong cả hai lệnh |
| Quyền truy cập | UID/GID runtime có quyền đọc file và traverse thư mục không? | `id`, `ls -l`, kiểm tra mode/owner |
| Không bị che khuất | Volume mount có phủ lên thư mục hoặc file cache không? | Kiểm tra `volumeMounts` và mount path |

Không dùng kết quả kiểm tra trên builder stage để kết luận final image có file. Multi-stage build chỉ chuyển các file được copy hoặc được tạo trong stage cuối vào image cuối cùng.

## 3. Dùng Spring Boot executable JAR layering

Spring Boot hỗ trợ tách executable JAR thành các layer. Cấu trúc này giúp Docker tái sử dụng layer dependency khi chỉ thay đổi code ứng dụng, đồng thời tạo classpath phù hợp hơn cho AOT cache và CDS.

Với Java 25 trở lên, Spring Boot có ví dụ Dockerfile tích hợp AOT cache:

~~~dockerfile
# syntax=docker/dockerfile:1

# Cùng một runtime image được dùng ở cả hai stage.
# Trong CI nên pin JAVA_IMAGE bằng digest đã xác minh.
ARG JAVA_IMAGE=eclipse-temurin:25-jre

FROM \${JAVA_IMAGE} AS builder
WORKDIR /builder

ARG JAR_FILE=target/*.jar
COPY \${JAR_FILE} application.jar

# Tách executable JAR thành các layer.
RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted

FROM \${JAVA_IMAGE} AS runtime
WORKDIR /application

# Copy từng layer vào final image.
COPY --from=builder /builder/extracted/dependencies/ ./
COPY --from=builder /builder/extracted/spring-boot-loader/ ./
COPY --from=builder /builder/extracted/snapshot-dependencies/ ./
COPY --from=builder /builder/extracted/application/ ./

# Training startup-only để tạo cache trong đúng runtime layout.
RUN java -XX:AOTCacheOutput=/application/app.aot \
    -Dspring.context.exit=onRefresh \
    -jar application.jar

# Cache chỉ cần đọc khi production khởi động.
RUN chmod 0444 /application/app.aot

# Dùng UID/GID không phải root theo chính sách image của dự án.
USER 10001:10001

ENTRYPOINT ["java", "-XX:AOTCache=/application/app.aot", "-jar", "application.jar"]
~~~

Đây là mẫu tham khảo cho Linux image. Trong dự án thật:

- Chọn base image Java 25 có HotSpot và AOT cache support.
- Dùng cùng image/JVM build cho stage tạo cache và stage runtime.
- Pin image digest trong pipeline thay vì dựa vào tag mutable.
- Đổi `JAR_FILE` sang `build/libs/*.jar` nếu dùng Gradle.
- Xác minh image base thực sự có `java`, `jarmode=tools` và các thành phần cần thiết.
- Tạo cache sau khi đã copy các layer vào final runtime stage để file `.aot` được giữ trong image cuối.

Spring Boot tài liệu hóa chính mô hình này: extract executable JAR bằng `jarmode=tools`, copy các layer vào runtime image, tạo `app.aot` rồi khởi động với `-XX:AOTCache=app.aot`. Cấu trúc layer được thiết kế để đáp ứng yêu cầu class loading của AOT cache và CDS.

### 3.1. Vì sao training ở runtime stage?

Nếu training trong builder stage nhưng quên copy file `.aot` sang stage cuối, image production sẽ không có cache. Ngay cả khi đã copy, classpath, JAR timestamp, JDK hoặc OS/CPU giữa hai stage cũng có thể không tương thích.

Training ở final runtime layout giúp:

- Cache được tạo với đúng các layer và đường dẫn mà process production sẽ dùng.
- Không phải đoán file cache đã được copy sang stage cuối hay chưa.
- Giảm khả năng sai khác classpath giữa training và production.
- Có thể xác minh file cache trong chính image chuẩn bị phát hành.

Nếu training ở stage riêng để tiết kiệm tài nguyên, cần copy rõ cả cache và bảo đảm mọi điều kiện tương thích giữa hai stage.

### 3.2. Không dựa vào tag image mutable

Ví dụ `eclipse-temurin:25-jre` chỉ minh họa cách chọn image. Trong pipeline production, nên pin cùng một digest cho cả builder và runtime stage:

~~~dockerfile
ARG JAVA_IMAGE=eclipse-temurin:25-jre@sha256:<verified-manifest-digest>

FROM \${JAVA_IMAGE} AS builder
# ...

FROM \${JAVA_IMAGE} AS runtime
# ...
~~~

`<verified-manifest-digest>` là placeholder, phải thay bằng digest lấy từ registry mà dự án tin cậy. Không tự điền một digest đoán trước. Khi base image được cập nhật, cần build lại cache bằng image/JDK mới và chạy lại kiểm chứng.

## 4. Training startup-only và production-like trong container

Trong Dockerfile ví dụ, lệnh:

~~~bash
java -XX:AOTCacheOutput=/application/app.aot \
     -Dspring.context.exit=onRefresh \
     -jar application.jar
~~~

yêu cầu Spring application thoát sau khi `ApplicationContext` refresh. Spring Framework ghi nhận các non-lazy singleton đã được tạo và callback khởi tạo tương ứng đã chạy; lifecycle chưa bắt đầu và `ContextRefreshedEvent` chưa được phát.

Cách này hữu ích khi mục tiêu chính là cache dữ liệu phục vụ startup. Tuy nhiên, Java 25 còn lưu **method profiling information** theo JEP 515. Nếu muốn tận dụng phần này, cần để ứng dụng trải qua một phần workload giống production thay vì chỉ thoát ngay sau context refresh.

### 4.1. Training có workload đại diện

Với service cần method profiles, quy trình nên là:

1. Khởi chạy application trong training mode với `AOTCacheOutput`.
2. Đợi health/readiness theo cách mà workload training yêu cầu.
3. Gửi một bộ request an toàn đại diện cho các luồng nóng.
4. Chờ các thao tác bất đồng bộ hoàn tất hoặc đạt trạng thái xác định.
5. Gọi `jcmd <pid> AOT.end_recording` để kết thúc training và ghi cache.
6. Kết thúc process training và xác minh cache được tạo.

Ví dụ lệnh điều khiển:

~~~bash
jcmd -l
jcmd 12345 AOT.end_recording
~~~

Thay `12345` bằng PID thực tế trong container training. `jcmd` cần có trong image training và người chạy phải có quyền truy cập process tương ứng. Nếu runtime image là JRE tối giản không có công cụ này, có thể dùng một training image JDK có cùng JVM build/version với runtime image hoặc dùng workflow một lệnh có thể tự kết thúc.

**Không đưa secret production vào build stage.** Dùng database/broker thử nghiệm hoặc service stub có dữ liệu an toàn. Training là một lần chạy ứng dụng thật; nó có thể tạo dữ liệu, gửi message hoặc gọi hệ thống ngoài nếu profile không được cô lập.

### 4.2. Chọn cách training theo mục tiêu

| Mục tiêu | Cách thực hiện | Giới hạn |
|---|---|---|
| Cache class/object phục vụ startup | `spring.context.exit=onRefresh` | Không có đủ method profiles từ business workload |
| Cache và method profiles | Production-like training rồi kết thúc recording | Cần workload đại diện và hạ tầng test |
| Server chạy lâu dài | Training job/instance riêng, kết thúc bằng `jcmd` | Phải bảo đảm đúng JDK, classpath và platform |
| CLI hoặc test runner có thời điểm kết thúc rõ | `AOTCacheOutput` rồi để process kết thúc | Workload phải thực sự chạy trước khi thoát |

## 5. Kiểm soát quyền file và người dùng container

Container production nên chạy với UID/GID không phải root nếu ứng dụng cho phép. Khi đó, file cache phải được đọc bởi user runtime và các thư mục cha phải có quyền traverse.

Trong Dockerfile mẫu:

~~~dockerfile
RUN chmod 0444 /application/app.aot
USER 10001:10001
~~~

File mode `0444` cho phép mọi user đọc file nhưng không cho ghi. Có thể dùng quyền hẹp hơn nếu owner/group được cấu hình đúng. Quan trọng là user runtime có:

- Quyền đọc `app.aot`.
- Quyền traverse thư mục `/application`.
- Quyền đọc JAR và các layer ứng dụng.
- Quyền ghi vào các thư mục runtime thực sự cần thiết, ví dụ thư mục tạm hoặc log nếu ứng dụng ghi file.

Kiểm tra trong container:

~~~bash
id
pwd
ls -ld /application
ls -l /application/app.aot
test -r /application/app.aot
~~~

Nếu `test -r` thất bại, kiểm tra owner, group, mode và quyền trên toàn bộ đường dẫn. Chỉ sửa quyền file không đủ nếu thư mục cha không cho phép traverse.

### 5.1. Read-only root filesystem

AOT cache được **đọc** trong production; không cần JVM ghi đè cache khi khởi động. Vì vậy có thể đặt cache trong image và chạy với root filesystem chỉ đọc.

Tuy nhiên, ứng dụng/JVM có thể cần ghi:

- File tạm dưới `/tmp`.
- Log file nếu không ghi ra stdout/stderr.
- Heap dump, crash log hoặc file chẩn đoán khi được cấu hình.
- File upload/cache nghiệp vụ nếu ứng dụng có chức năng đó.

Khi bật read-only root filesystem, cấp riêng writable mount cho các đường dẫn cần thiết. Không biến thư mục chứa application JAR và AOT cache thành volume writable chỉ để giải quyết một nhu cầu ghi file tạm.

### 5.2. Không dùng `AOTCacheOutput` trong production

`-XX:AOTCacheOutput` dùng để tạo cache, không phải tùy chọn khởi chạy thường ngày. Production nên đọc cache:

~~~bash
java -XX:AOTCache=/application/app.aot -jar application.jar
~~~

Nếu production process cố ghi cache vào thư mục chỉ đọc, training có thể thất bại. Tách rõ hai vai trò:

- **Build/training:** có quyền ghi file cache.
- **Production:** chỉ cần quyền đọc file cache tương thích.

## 6. Volume mount có thể che khuất file đã đóng gói

Docker và Kubernetes mount volume lên một đường dẫn trong container. Khi mount lên một thư mục đã có nội dung trong image, nội dung cũ ở vị trí đó có thể bị che khuất trong lúc mount có hiệu lực.

Ví dụ image đã chứa:

~~~text
/application/
  application.jar
  app.aot
  dependencies/
  spring-boot-loader/
~~~

Nếu Kubernetes mount volume vào:

~~~yaml
volumeMounts:
  - name: runtime-data
    mountPath: /application
~~~

thì các file đã đóng gói trong `/application`, gồm `application.jar` và `app.aot`, có thể không còn nhìn thấy trong container đang chạy.

Đây là lỗi thường gặp: Docker image được kiểm tra đúng, nhưng Pod lại báo không tìm thấy cache vì mount đã phủ lên vị trí file.

**Cách tổ chức tốt hơn:**

- Để application và cache bất biến trong image.
- Mount dữ liệu runtime vào thư mục riêng như `/var/lib/shop` hoặc `/tmp`.
- Nếu buộc phải lấy cache từ volume, mount vào thư mục chuyên biệt như `/opt/aot`, không phủ lên application directory.
- Dùng volume read-only cho cache đã được chuẩn bị và xác minh; không chia sẻ một file cache mutable giữa nhiều release.

Ví dụ:

~~~yaml
volumeMounts:
  - name: aot-cache
    mountPath: /opt/aot
    readOnly: true
~~~

Khi đó JVM phải trỏ đúng đường dẫn:

~~~bash
java -XX:AOTCache=/opt/aot/app.aot -jar /application/application.jar
~~~

Cần bảo đảm volume chứa đúng file, đúng JDK/platform/application và quyền đọc hợp lệ. Nếu volume không có file, mount path vẫn có thể tồn tại nhưng cache không được nạp.

## 7. Docker Compose: giữ cache cùng image

Với Docker Compose, cách đơn giản là build image đã chứa cache, sau đó chạy container từ image đó:

~~~yaml
services:
  shop:
    image: example/shop-service:2.4.0
    build:
      context: .
      dockerfile: Dockerfile
    read_only: true
    tmpfs:
      - /tmp
    environment:
      SPRING_PROFILES_ACTIVE: production
    ports:
      - "8080:8080"
~~~

Đây là ví dụ minh họa. Nếu ứng dụng cần thư mục writable khác, khai báo riêng theo đúng nhu cầu. Không mount volume rỗng vào `/application` chỉ để tạo thư mục runtime.

Nếu muốn kiểm tra cache trong Compose, có thể dùng command override tạm thời ở môi trường test:

~~~yaml
services:
  shop-aot-check:
    image: example/shop-service:2.4.0
    entrypoint:
      - java
      - -XX:AOTMode=on
      - -XX:AOTCache=/application/app.aot
      - -Xlog:aot
      - -jar
      - /application/application.jar
~~~

Đảm bảo đường dẫn JAR đúng với layout image thực tế. Service kiểm tra nên chạy trong pipeline/staging, không nhất thiết chạy song song với service production thật.

## 8. Kubernetes: triển khai cache cùng release

Nếu AOT cache đã được đóng gói trong image, Pod chỉ cần đọc file ở đường dẫn cố định. Ví dụ Deployment rút gọn:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shop-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: shop-service
  template:
    metadata:
      labels:
        app: shop-service
    spec:
      containers:
        - name: app
          image: registry.example.com/shop-service:2.4.0
          workingDir: /application
          command: ["java"]
          args:
            - "-XX:AOTCache=/application/app.aot"
            - "-XX:AOTMode=auto"
            - "-jar"
            - "application.jar"
          ports:
            - containerPort: 8080
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            runAsGroup: 10001
            readOnlyRootFilesystem: true
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
~~~

Manifest này giả định image đã có:

- File `/application/app.aot`.
- JAR/layer ứng dụng tại `/application`.
- File và thư mục đọc được bởi UID/GID 10001.
- JVM Java 25 tương thích với cache đã tạo.

Nếu image của dự án có user hoặc layout khác, chỉnh UID/GID và working directory theo image đó. Không copy nguyên manifest vào production mà chưa xác minh các giả định này.

### 8.1. Vì sao dùng `AOTMode=auto` trong production?

`auto` là mode mặc định. Nếu cache không tương thích hoặc không thể đọc, JVM có thể tiếp tục chạy không dùng cache. Điều này giúp ứng dụng giữ khả năng khởi động, nhưng hiệu năng có thể trở lại mức không cache.

Trong CI/staging, nên chạy một lần với:

~~~yaml
args:
  - "-XX:AOTMode=on"
  - "-XX:AOTCache=/application/app.aot"
  - "-Xlog:aot"
  - "-jar"
  - "application.jar"
~~~

`AOTMode=on` là chế độ fail-fast: nếu cache không thể nạp, JVM báo lỗi và thoát. Dùng nó để xác minh image trước khi rollout; chỉ dùng production nếu chính sách vận hành muốn cache mismatch làm Pod không khởi động.

### 8.2. Dùng volume riêng khi cache không nằm trong image

Một số nền tảng phát hành cache như artifact độc lập. Khi đó có thể mount vào thư mục riêng:

~~~yaml
volumeMounts:
  - name: aot-cache
    mountPath: /opt/aot
    readOnly: true
~~~

và chạy:

~~~yaml
args:
  - "-XX:AOTCache=/opt/aot/app.aot"
  - "-jar"
  - "/application/application.jar"
~~~

Volume phải được cung cấp trước khi container khởi động, có file đúng phiên bản và quyền đọc phù hợp. Không dùng ConfigMap cho một file cache nhị phân lớn nếu không phù hợp giới hạn/semantics của nền tảng. Không ghi đè file cache đang được các Pod khác sử dụng.

**Ưu tiên cache nằm trong image** khi có thể, vì image digest gắn code, dependency và cache thành một release bất biến. Volume riêng chỉ nên dùng khi quy trình artifact có kiểm soát version và provenance rõ ràng.

## 9. Multi-architecture và image digest

Một image tag có thể trỏ tới manifest list nhiều kiến trúc, ví dụ `linux/amd64` và `linux/arm64`. Cache phải được tạo cho đúng kiến trúc CPU của runtime image.

Ví dụ:

| Training platform | Runtime platform | Có nên dùng cùng cache? |
|---|---|---|
| `linux/amd64` | `linux/amd64` | Có thể, nếu JDK/app tương thích và các điều kiện khác giống nhau |
| `linux/amd64` | `linux/arm64` | **Không** |
| `linux/arm64` | `linux/arm64` | Có thể, nếu các điều kiện khác giống nhau |
| JDK 25 build A | JDK 25 build B khác JVM distribution/build | Không nên giả định tương thích; tạo lại và kiểm tra |
| JDK 25 | JDK 26 | **Không**; tạo cache mới |

Khi build multi-platform, nên chạy training trên builder native cho từng target architecture. Không giả định JVM training chạy dưới QEMU sẽ tạo ra cache có thể dùng trên target; hãy dùng native build node hoặc pipeline tách theo platform.

Pin base image theo digest và ghi nhận image digest của release. Khi cập nhật JDK security patch, đổi base image hoặc thay architecture, chạy lại training/assembly và validation.

## 10. Giữ classpath và JAR timestamp ổn định

Spring Framework nêu các điều kiện quan trọng để cache được sử dụng:

- Dùng cùng JVM/JDK tương thích giữa training và production.
- Classpath nên là một JAR hoặc danh sách JAR cụ thể; tránh directory và wildcard `*`.
- Giữ nguyên timestamp của các JAR.
- Khi dùng cache, classpath nên giống training và giữ cùng thứ tự; nếu thêm JAR hoặc directory ở cuối, phần bổ sung không có dữ liệu cache tương ứng.

Với Spring Boot executable JAR, **executable JAR unpacking support** được khuyến nghị vì layout tạo ra đáp ứng tốt hơn yêu cầu class loading của AOT cache và CDS.

### 10.1. Vì sao layering hữu ích?

Một executable JAR thường chứa dependency và application code. Nếu copy toàn bộ JAR như một file duy nhất, mỗi lần code thay đổi có thể làm Docker rebuild layer lớn. Spring Boot layering tách:

- `dependencies`
- `spring-boot-loader`
- `snapshot-dependencies`
- `application`

Nhờ vậy, dependency layer ổn định có thể được tái sử dụng khi chỉ application code thay đổi. AOT cache được tạo sau khi các layer đã được copy vào final runtime layout nên phản ánh classpath mà ứng dụng sẽ dùng.

### 10.2. Không tự thay đổi layout sau training

Tránh các thay đổi sau khi cache đã tạo:

- Thêm/xóa JAR trong thư mục dependency.
- Sắp xếp lại classpath.
- Đổi timestamp JAR khi đóng gói lại.
- Chuyển từ `java -jar` sang classpath launcher khác mà không training lại.
- Thêm JVM options có thể làm cache không tương thích.
- Dùng một cache được tạo từ uber JAR cho layout extracted layers khác mà chưa kiểm tra.

Nếu thay đổi layout là cần thiết, hãy coi đó là một lần build mới và tạo lại cache.

## 11. Kiểm tra cache ngay trong container

Trước khi deploy, mở một container từ image đã build và kiểm tra file:

~~~bash
docker run --rm --entrypoint sh example/shop-service:2.4.0 -c \
  "pwd && id && ls -l /application/app.aot && test -r /application/app.aot"
~~~

Nếu base image không có shell hoặc lệnh `ls`, dùng công cụ chẩn đoán phù hợp với image đó hoặc tạo một stage kiểm thử riêng. Không cài thêm shell/tools vào production image chỉ để debug nếu không cần.

### 11.1. Kiểm tra JVM fail-fast

~~~bash
docker run --rm \
  --entrypoint java \
  example/shop-service:2.4.0 \
  -XX:AOTMode=on \
  -XX:AOTCache=/application/app.aot \
  -Xlog:aot \
  -jar /application/application.jar
~~~

Lệnh này xác nhận JVM có thể nạp cache với môi trường và đường dẫn hiện tại. Nếu Spring Boot application cần database/broker, cấu hình môi trường test an toàn hoặc dùng startup check phù hợp.

### 11.2. Kiểm tra class loading

Có thể bật log class loading trong một lần chẩn đoán:

~~~bash
docker run --rm \
  --entrypoint java \
  example/shop-service:2.4.0 \
  -XX:AOTCache=/application/app.aot \
  -Xlog:aot \
  -Xlog:class+load=info:file=/tmp/aot-classload.log \
  -jar /application/application.jar
~~~

Các lớp được nạp từ cache có thể hiện nguồn `shared objects file`. Log file ở `/tmp` yêu cầu thư mục này writable; với read-only root filesystem, mount `/tmp` riêng hoặc chuyển log ra stdout theo cấu hình phù hợp.

Không phải tất cả lớp đều phải đến từ cache. Cần đối chiếu một số lớp ứng dụng/framework dự kiến được training, không kết luận thất bại chỉ vì còn lớp được nạp bình thường.

### 11.3. Phân biệt ba trạng thái

| Trạng thái | Bằng chứng |
|---|---|
| File được đóng gói | `test -r /application/app.aot` thành công |
| JVM chấp nhận cache | Chạy thành công với `-XX:AOTMode=on` và log AOT phù hợp |
| Cache mang lại lợi ích | Benchmark startup/warm-up trên workload đại diện tốt hơn baseline |

File tồn tại không chứng minh cache được JVM sử dụng; JVM nạp cache không chứng minh hiệu năng chắc chắn cải thiện.

## 12. Quy trình CI/CD cho AOT cache

Một pipeline phù hợp có thể tổ chức theo thứ tự:

1. **Build:** biên dịch và đóng gói executable JAR, khóa dependency.
2. **Extract:** dùng `jarmode=tools` để tạo layer layout.
3. **Select runtime:** chọn JDK/JRE image đúng release, OS và CPU architecture.
4. **Training:** chạy workload an toàn, đại diện cho production.
5. **Assembly:** để JVM ghi `.aot` hoặc kết thúc recording theo workflow.
6. **Package:** đặt cache vào final image tại đường dẫn đã định.
7. **Permissions:** xác minh UID/GID runtime đọc được file.
8. **Validation:** chạy image với `AOTMode=on`, `-Xlog:aot`.
9. **Benchmark:** so sánh startup/warm-up với image không cache.
10. **Publish:** gắn app và cache với image digest/release metadata.
11. **Deploy:** rollout image mới theo chiến lược triển khai.
12. **Observe:** kiểm tra log AOT, startup readiness, restart count và latency sau deploy.

### 12.1. Khi nào phải tạo lại cache?

| Thay đổi | Tạo cache mới? | Lý do |
|---|---|---|
| Chỉ đổi environment variable nghiệp vụ không ảnh hưởng classpath | Đánh giá theo workload/config; nên xác minh | Có thể thay đổi đường chạy hoặc thành phần được khởi tạo |
| Thay source code và build JAR mới | **Có** | Application artifact thay đổi |
| Cập nhật dependency | **Có** | Classpath và class content thay đổi |
| Nâng JDK hoặc đổi vendor/build | **Có** | Cache gắn với JDK/JVM |
| Đổi base image OS | **Có** | Nền tảng cache thay đổi |
| Build image amd64 sang arm64 | **Có** | Kiến trúc CPU khác |
| Chỉ đổi port/container label | Thường không cần nếu không ảnh hưởng ứng dụng | Không nhất thiết thay cache input |
| Đổi classpath order hoặc executable layout | **Có** | Điều kiện class loading thay đổi |
| Đổi GC trong cùng JDK 25 | Kiểm tra điều kiện tương thích và loại object cache | Không giả định mọi GC có cùng hỗ trợ |
| Nâng lên JDK 26 | **Có** | JDK release thay đổi; JEP 516 thay đổi object caching |

Nếu không chắc một thay đổi có ảnh hưởng cache hay không, tạo cache mới là cách đơn giản và an toàn hơn so với cố tái sử dụng một file không rõ provenance.

## 13. Xử lý lỗi trong container

| Triệu chứng | Nguyên nhân thường gặp | Hướng điều tra |
|---|---|---|
| JVM báo không tìm thấy cache | Sai đường dẫn, file chưa copy vào final image | Kiểm tra `WORKDIR`, absolute path và final stage |
| Cache có ở builder nhưng không có trong production | Training chạy ở stage không được copy | Tạo cache ở final stage hoặc copy file tường minh |
| `Permission denied` | UID/GID runtime không đọc được file/thư mục | Kiểm tra `USER`, owner, mode và quyền traverse |
| File tồn tại nhưng Pod không thấy | Volume mount che khuất thư mục chứa cache | Kiểm tra `volumeMounts.mountPath` |
| Cache không tương thích trên node ARM | Cache tạo trên amd64 | Tạo cache riêng cho từng architecture |
| Cache mất sau rollout | Cache nằm ở writable layer hoặc thư mục tạm không bền | Đóng gói trong image hoặc artifact versioned |
| Cache cũ sau khi update app | PVC/shared volume chứa file release cũ | Gắn cache với image digest, version path |
| Ứng dụng chạy nhưng không có AOT | `AOTMode=auto` fallback | Kiểm tra `-Xlog:aot`, thử `AOTMode=on` ở staging |
| `AOTMode=on` fail ngay | Cache không tương thích, không accessible hoặc JVM options không phù hợp | Đọc lỗi AOT, tái tạo cache |
| Training container hết RAM | Training/assembly tiêu thụ tài nguyên đỉnh cao | Tăng memory limit hoặc tách giai đoạn |
| Cache startup tốt nhưng warm-up không đổi | Workload training không đại diện | Training thêm luồng production-like |
| Read-only rootfs làm app lỗi | Ứng dụng/JVM cần ghi file tạm/log | Mount writable `/tmp` hoặc thư mục đúng nhu cầu |
| Cache hoạt động ở local nhưng fail trong image | Khác JDK, OS, classpath, timestamp hoặc working directory | So sánh manifest training và runtime |

### 13.1. Cách phân loại nhanh khi Pod không khởi động

1. Kiểm tra exit code và log đầu tiên của JVM.
2. Nếu là `NoSuchFile`/cache missing, kiểm tra đường dẫn và volume mount.
3. Nếu là `Permission denied`, kiểm tra UID/GID và file mode.
4. Nếu là cache mismatch, kiểm tra JDK, OS/CPU, application artifact và JVM options.
5. Chạy lại image trong staging với `-XX:AOTMode=on -Xlog:aot`.
6. Nếu cần giữ availability, chạy production với `auto` và ghi nhận cảnh báo cache không được dùng; sau đó tạo lại image/cache.

Không chỉnh sửa file cache đang chạy hoặc copy đè cache vào volume được nhiều Pod dùng đồng thời.

## 14. Khác biệt Java 25 và JDK 26 trong container

Java 25 hỗ trợ AOT cache và method profiles, nhưng AOT object caching có giới hạn khi dùng ZGC. **JEP 516 trong JDK 26** thay đổi cách lưu/nạp cached objects theo định dạng trung lập với GC, giúp AOT object caching hoạt động với mọi garbage collector, gồm ZGC.

| Nội dung | Java 25 | JDK 26 |
|---|---|---|
| AOT cache | Có | Có |
| One-command creation | Có, JEP 514 | Có |
| Method profiles | Có, JEP 515 | Có |
| AOT object caching với mọi GC | Chưa; ZGC có giới hạn | Có theo JEP 516 |
| Cache tạo từ bản cũ | Không dùng cho JDK 26 | Tạo cache mới bằng JDK 26 |

Khi chuyển image từ Java 25 sang JDK 26:

- Chọn base image JDK/JRE 26 và pin digest mới.
- Build lại executable JAR nếu toolchain/dependency yêu cầu.
- Training và tạo lại cache trên target OS/CPU.
- Chạy kiểm tra fail-fast và benchmark.
- Không giữ file `.aot` của Java 25 chỉ vì đường dẫn và tên file không đổi.

Đừng áp dụng giới hạn GC của Java 25 cho JDK 26, và cũng không giả định cache của JDK 26 có thể dùng ngược với JDK 25.

## 15. Bài thực hành: Docker image có AOT cache

Bạn có Spring Boot service `shop-service`, build ra `target/shop-service.jar`, triển khai trên Linux/amd64 bằng Java 25.

Thực hiện:

1. Viết Dockerfile multi-stage dùng một runtime image Java 25 tương thích cho builder và runtime.
2. Extract executable JAR bằng `java -Djarmode=tools -jar application.jar extract --layers --destination extracted`.
3. Copy bốn layer vào `/application`.
4. Tạo `/application/app.aot` trong final runtime stage bằng `AOTCacheOutput`.
5. Kiểm tra file tồn tại, mode đọc được và parent directory có quyền traverse.
6. Chuyển runtime sang UID/GID không phải root.
7. Khởi động với `-XX:AOTCache=/application/app.aot`.
8. Chạy smoke test với `AOTMode=on` và `-Xlog:aot`.
9. Thêm volume mount vào `/application` để quan sát lỗi che khuất file; sau đó chuyển volume sang `/tmp` và xác nhận ứng dụng đọc cache bình thường.
10. Chạy image trên kiến trúc khác hoặc JDK khác, xác nhận cần tạo cache riêng.
11. Đo startup và warm-up giữa bản có cache và không cache.
12. Ghi lại image digest, JDK, platform, checksum JAR và kết quả validation.

**Sản phẩm nghiệm thu:** Dockerfile, manifest metadata của cache, log xác nhận nạp cache, kết quả kiểm tra file permissions/mount paths, bảng benchmark và checklist tái tạo cache khi release mới.

## 16. Checklist trước khi deploy

- Image training và runtime dùng cùng JVM/JDK build phù hợp.
- OS và CPU architecture của cache khớp với runtime node.
- Executable JAR được extract theo layout ổn định.
- Classpath/JAR list và thứ tự được giữ nguyên.
- JAR timestamps không bị thay đổi sau training.
- Cache được tạo trong final stage hoặc được copy rõ ràng vào final image.
- JVM dùng absolute path trỏ tới file thực tế.
- File và thư mục cha đọc được bởi non-root user.
- Không có volume mount che khuất application/cache directory.
- Read-only root filesystem có writable mounts riêng cho nhu cầu runtime.
- Production dùng `AOTMode=auto` theo chính sách availability.
- CI/staging kiểm tra `AOTMode=on` và `-Xlog:aot`.
- Cache gắn với image digest và application release.
- Mỗi kiến trúc CPU có cache riêng.
- Cache được tạo lại sau khi đổi JDK, application artifact hoặc platform.
- Training không dùng credentials/dữ liệu production không cần thiết.
- Benchmark chứng minh lợi ích trên workload đại diện.

## Tài liệu tham khảo chính thức

- [Spring Boot — Dockerfiles](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html): layering executable JAR và Dockerfile tích hợp AOT cache cho Java 25+.
- [Spring Framework — JVM AOT Cache](https://docs.spring.io/spring-framework/reference/integration/aot-cache.html): classpath, JAR timestamps, training, cache usage và production-like workflow.
- [Oracle Java SE 25 — The java Command, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): tính tương thích theo application/JDK/OS/CPU và các AOT options.
- [Oracle Java SE 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): diagnostic command để kết thúc recording.
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): workflow tạo cache bằng một lệnh.
- [JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): method profiles trong cache Java 25.
- [JEP 516 — Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516): thay đổi trong JDK 26 để hỗ trợ mọi GC.
- [Oracle JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): trạng thái JEP 516 và các thay đổi của JDK 26.
- [Docker — Multi-stage builds](https://docs.docker.com/build/building/multi-stage/): tách builder và runtime stages, chỉ copy artifact cần thiết.
