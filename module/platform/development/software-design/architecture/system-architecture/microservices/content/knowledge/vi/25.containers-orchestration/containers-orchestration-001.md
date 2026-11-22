# Đóng gói dịch vụ và quản lý image

Trong kiến trúc microservices, mỗi dịch vụ được xây dựng, kiểm thử và triển khai theo vòng đời riêng. Để cùng một phiên bản có thể chạy ổn định ở máy phát triển, môi trường thử nghiệm và production, nhóm cần một đơn vị phân phối có nội dung xác định. **Container image** là một cách phổ biến để phân phối ứng dụng cùng runtime, thư viện và các tệp cần thiết; container là một phiên bản đang chạy của image đó.

Đóng gói đúng không chỉ là viết `Dockerfile` và chạy `docker build`. Cần kiểm soát nguồn tạo image, cách phân lớp, kích thước, quyền runtime, thông tin cấu hình, phiên bản, registry, kiểm tra bảo mật, tính toàn vẹn, quá trình phát hành và khả năng quay lại bản trước. Một image thiếu kiểm soát có thể chạy tốt trên máy lập trình nhưng thất bại khi chuyển node, không xác định được build nào đang chạy hoặc vô tình chứa secret.

Bài này dùng ví dụ một dịch vụ Java 21/Spring Boot có tên `order-service`. Những đường dẫn, phiên bản và registry trong các lệnh minh họa cần được điều chỉnh theo repository, hạ tầng và chính sách triển khai thực tế.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt **source code**, **build artifact**, **OCI container image**, **container** và **image registry**.
- Thiết kế Dockerfile nhiều giai đoạn để tạo image chỉ gồm phần cần cho runtime.
- Tách phần không nhạy cảm có thể đóng gói khỏi cấu hình môi trường và secret được cấp khi chạy.
- Hiểu tag, digest, image manifest, layer, cache và các yếu tố ảnh hưởng đến khả năng tái lập build.
- Thiết kế quy tắc đặt tên, phát hành, lưu giữ, quét lỗ hổng, ký và quảng bá image giữa các môi trường.
- Chọn cấu hình chạy non-root, hạn chế quyền container, health probe và xử lý signal phù hợp.
- Kiểm thử image trước khi đưa vào Kubernetes và thực hiện rollback theo artifact đã được xác minh.

## 2. Image khác container và JAR như thế nào?

Xét chuỗi chuyển đổi:

~~~text
Source code + build scripts + dependency metadata
                       |
                       v
                Build và test
                       |
                       v
              Spring Boot JAR
                       |
                       v
      Base image + JRE + JAR + metadata
                       |
                       v
              OCI container image
                       |
                       v
               Image registry
                       |
                       v
        Node tải image theo tham chiếu
                       |
                       v
          Container đang chạy trên node
~~~

Các khái niệm cần phân biệt:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Source code | Đầu vào được quản lý bằng version control | Java, `build.gradle`, resource |
| Build artifact | Kết quả biên dịch/đóng gói phần mềm | `order-service.jar` |
| Base image | Nền filesystem và runtime ban đầu | Một image JRE 21 đã được lựa chọn |
| Container image | Tập nội dung và metadata dùng để khởi tạo container | `registry.example.test/apps/order:1.8.2` |
| Image tag | Tên tham chiếu có thể được gán lại | `1.8.2`, `staging` |
| Image digest | Giá trị băm định danh nội dung manifest/index theo OCI | `sha256:...` |
| Registry | Kho phân phối/lưu trữ image | Registry nội bộ hoặc dịch vụ quản lý registry |
| Container | Tiến trình đang chạy cùng giới hạn và filesystem runtime | Pod/container của Order trên một node |

JAR là artifact ứng dụng; nó chưa mô tả đầy đủ môi trường thực thi. Image có thể bổ sung JRE, chứng thư gốc, filesystem và metadata cần thiết để chạy. Ngược lại, image không tự cung cấp mọi thành phần hệ thống như database, DNS, quyền truy cập network, secret hoặc orchestration.

**Không đồng nhất image với một máy ảo.** Container dùng kernel của host, nên cách cô lập tài nguyên, namespace và bảo mật phụ thuộc container runtime cùng hệ điều hành bên dưới.

## 3. Vì sao quản lý image là một phần của kiến trúc microservices?

Giả sử Order Service v1.8.2 được triển khai với 4 replica trên hai node. Nếu mỗi node tự build từ source khác nhau hoặc cùng tag `latest` nhưng trỏ tới nội dung khác nhau, một service có thể chạy nhiều bản không kiểm soát được.

Một quy trình ổn định hướng tới:

1. **Một commit xác định** được kiểm thử và đưa qua pipeline đáng tin cậy.
2. **Một image version xác định** được tạo, kiểm tra và lưu vào registry.
3. Môi trường staging và production chạy **cùng nội dung image** đã được chọn; khác nhau chủ yếu ở cấu hình runtime.
4. Hệ thống ghi nhận **digest đã triển khai** để đối chiếu với release và build.
5. Nếu xảy ra sự cố, có thể xác định và triển khai lại image trước đó, miễn schema dữ liệu và cấu hình vẫn tương thích.

Nguyên tắc này hỗ trợ **independent deployability**: Payment Service có thể phát hành image mới mà Order Service giữ nguyên artifact đang chạy. Việc tất cả service cùng nằm trong một cluster không yêu cầu chúng cùng phiên bản hay phát hành đồng thời.

## 4. Hiểu cấu trúc OCI image

Một image thường được tổ chức theo các lớp nội dung (layers), một cấu hình image (command khởi động, biến môi trường mặc định, user, working directory...) và một manifest tham chiếu tới nội dung liên quan. OCI Image Specification chuẩn hóa định dạng và mô hình phân phối ở mức cần thiết để nhiều công cụ cùng làm việc.

~~~text
OCI image manifest / index
         |
         +-- Image config (entrypoint, env, user, history...)
         |
         +-- Layer A: hệ điều hành hoặc base filesystem
         +-- Layer B: runtime JRE và thư viện hệ thống
         +-- Layer C: dependency của ứng dụng
         +-- Layer D: class/resource của ứng dụng
~~~

Đây là mô hình khái niệm; số lượng layer thực tế phụ thuộc Dockerfile, builder, base image và kỹ thuật đóng gói.

### 4.1. Layer và cache

Dockerfile có nhiều chỉ thị tạo ra những bước trong quá trình build; builder có thể tái sử dụng cache khi đầu vào của bước không thay đổi. Nếu copy toàn bộ source trước khi resolve dependency, thay một file Java nhỏ có thể làm mất cache ở nhiều bước.

Với Java, có thể tối ưu theo cách:

- Copy metadata phụ thuộc và Gradle wrapper trước.
- Tận dụng cache của builder và cache dependency có kiểm soát.
- Copy source vào bước sau, build artifact.
- Tách dependency layer khỏi application class layer nếu kỹ thuật đóng gói và quy trình vận hành hỗ trợ.
- Không lạm dụng cache nếu cần xác thực artifact mới, checksum hoặc dependency đã thay.

**Layer cache không đảm bảo build tái lập hoàn toàn.** Build còn phụ thuộc version dependency, base image, toolchain, timestamp, cấu hình và metadata. Cache giúp giảm thời gian; tính nhất quán cần cơ chế khóa phiên bản và xác minh riêng.

### 4.2. Image nhiều kiến trúc CPU

Một tag có thể tham chiếu tới OCI image index chứa các image dành cho `linux/amd64` và `linux/arm64`. Node chọn manifest phù hợp nền tảng khi pull.

Do đó cần phân biệt digest của **image index** và digest của **manifest thuộc một nền tảng**. Khi pin digest hoặc ký image nhiều kiến trúc, phải hiểu đối tượng được xác minh và môi trường đích hỗ trợ nền tảng nào. Một build chỉ chứa `amd64` có thể không chạy được trên node ARM dù tag đúng.

## 5. Chọn chiến lược build: artifact trước hay build trong Docker?

Hai cách phổ biến:

| Cách | Luồng | Ưu điểm | Điểm cần quản lý |
|---|---|---|---|
| Build JAR bên ngoài | CI chạy Gradle/Maven → tạo JAR → Docker build copy JAR | Tách rõ test/build ứng dụng và image | Phải chứng minh JAR trong image đúng artifact đã kiểm thử |
| Multi-stage Dockerfile | Stage có JDK/build tool → build JAR → stage runtime có JRE | Cùng một mô tả build-to-image; runtime không chứa compiler | Tốc độ/cache, dependency pinning, nguồn build và secret của build stage |

Cả hai cách đều có thể tạo image an toàn. Điều kiện quan trọng là pipeline nhất quán và truy vết được từ commit, build artifact tới digest cuối cùng.

### 5.1. Build stage và runtime stage

Một Dockerfile nhiều giai đoạn giúp image cuối chỉ lấy phần runtime, không mang theo Gradle, compiler, source tree và cache build.

Ví dụ dưới đây giả định **một Spring Boot Gradle project độc lập** có `gradlew`, `gradle/wrapper`, `settings.gradle`, `build.gradle` và `src`. Trong một Gradle multi-project, đường dẫn và task cần được đổi theo module đích.

~~~dockerfile
# syntax=docker/dockerfile:1

FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace

COPY gradlew settings.gradle build.gradle ./
COPY gradle/ ./gradle/
RUN chmod +x ./gradlew

COPY src/ ./src/
RUN ./gradlew --no-daemon test bootJar

# Quy ước cấu hình bootJar.archiveFileName = "app.jar"
# trong Gradle project để tránh chọn nhầm nhiều JAR.
FROM eclipse-temurin:21-jre AS runtime
WORKDIR /app
COPY --from=build /workspace/build/libs/app.jar /app/app.jar

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Với Gradle/Spring Boot, cần đảm bảo task `bootJar` và tên output trùng với phần `COPY --from=build`. Nếu build tạo nhiều JAR, không dùng wildcard mơ hồ ở bước cuối. Khi sử dụng build cache và dependency mirror, vẫn phải xác thực artifact thực tế đã được resolve.

Các điểm cần hiểu:

- Stage `build` có JDK và Gradle wrapper nhưng không được copy toàn bộ vào image cuối.
- Stage `runtime` chỉ có JRE và JAR; bỏ bớt toolchain giảm kích thước và bề mặt tấn công.
- `USER 10001:10001` chạy với UID/GID không phải root theo số. Ứng dụng phải đọc được JAR và tệp runtime; nếu cần ghi, tạo volume/directory có quyền thích hợp.
- `EXPOSE 8080` là metadata về cổng dự kiến, **không tự mở cổng, không tự publish ra host**.
- `ENTRYPOINT` dạng exec truyền signal trực tiếp hơn so với nhiều cách bọc trong shell; khả năng shutdown còn phụ thuộc JVM, ứng dụng và orchestration.

Tag của base image trong ví dụ nhằm minh họa. Với pipeline phát hành nghiêm ngặt, nên kiểm soát digest của base image và có lịch cập nhật chủ động để nhận bản vá bảo mật; không coi tag JRE 21 là nội dung bất biến.

### 5.2. Nếu JAR đã được build và kiểm thử trước

Có thể dùng Dockerfile runtime đơn giản:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/app.jar /app/app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Pipeline cần chắc chắn `build/libs/app.jar` là artifact từ đúng commit, đã qua test và chưa bị sửa sau khi test. Nếu build JAR trên một máy rồi image trên máy khác, cần bàn giao qua artifact store có kiểm chứng thay vì dựa vào file không rõ nguồn gốc.

## 6. Docker build context và .dockerignore

Docker client/builder nhận một **build context**: tập file có thể dùng làm đầu vào cho các bước `COPY` hoặc `ADD`. Nếu context có `.env`, private key, token, log hoặc cả thư mục `.git`, dữ liệu đó có thể bị gửi tới builder và đôi khi bị copy nhầm vào image.

Một `.dockerignore` minh họa:

~~~gitignore
.git
.gradle
build
out
target
.idea
.vscode
*.iml
*.log
.env
.env.*
**/secrets/**
**/*.pem
**/*.key
**/*-credentials.json
~~~

Đây là tập quy tắc tham khảo; dự án có thể cần tệp public key hoặc certificate không nhạy cảm trong build context, nên phải điều chỉnh theo nhu cầu thực tế.

**Không dùng .dockerignore như rào chắn bảo mật duy nhất.** Dữ liệu nhạy cảm nên được giữ ngoài repository/build context từ đầu; kiểm soát secret scanning và quyền truy cập tại nguồn. Với cách build JAR trước rồi copy artifact, cần xác định rõ thư mục `build` có bị loại khỏi context hay không: quy tắc ignore không được vô tình loại chính JAR cần copy.

### 6.1. Không đưa secret vào build args hoặc image layer

Một cách làm nguy hiểm là:

~~~dockerfile
# Không làm theo: chỉ để minh họa anti-pattern.
ARG PAYMENT_API_KEY
ENV PAYMENT_API_KEY=$PAYMENT_API_KEY
~~~

Giá trị có thể lọt vào metadata, layer, log build hoặc hệ thống lưu trữ cache. Không dùng `ARG`/hardcode `ENV` để chuyển mật khẩu, private key hoặc token lâu dài vào image.

Nếu build thật sự cần truy cập repository riêng, dùng secret mount của builder hoặc cơ chế cấp credential ngắn hạn của CI phù hợp với công cụ. Secret phải có phạm vi và thời gian sống giới hạn; không được copy nó vào output layer hoặc log. Đồng thời không dùng token production cho build vốn chỉ cần quyền đọc package.

## 7. Giữ image nhỏ nhưng ưu tiên đúng và bảo mật

Image nhỏ giúp giảm dung lượng truyền và lưu trữ; đôi khi giảm bề mặt tấn công. Tuy nhiên “càng nhỏ càng tốt” không phải mục tiêu duy nhất.

Các cách cải thiện:

1. Dùng multi-stage build để bỏ compiler, cache và source.
2. Chọn runtime base image được duy trì và phù hợp với JVM/JDK.
3. Tránh cài trình biên dịch, package manager, shell và network tool nếu image runtime không cần.
4. Không copy test reports, credentials, node_modules hoặc cấu hình của máy local vào runtime.
5. Có thể dùng lớp ứng dụng theo dependency để tối ưu việc push/pull khi thay code; đo trước khi tối ưu.
6. Xem xét image tối giản hoặc không có shell khi đã có phương pháp debug và quan sát phù hợp.
7. Theo dõi kích thước compressed/uncompressed và startup time thay vì chỉ nhìn số MB trong tên image.

Image distroless/tối giản có thể khó debug tại chỗ do không có shell. Nên dùng log, metric, tracing, ephemeral debug container hoặc cách điều tra phù hợp của nền tảng. Không cần cài sẵn `curl`, `bash` và package manager vào mọi production image chỉ để dùng khi gặp sự cố.

### Layering trong Spring Boot

Spring Boot executable JAR có thể được tổ chức thành các phần dependency và application riêng phục vụ cách build image theo layer, tùy công cụ và phiên bản plugin. Ý tưởng là dependency ít đổi có thể giữ cache khi class ứng dụng đổi. Khi áp dụng, cần đối chiếu tài liệu đúng phiên bản Spring Boot/Gradle đang dùng và xác minh kết quả image cuối khởi động được. Không thêm tối ưu layering nếu nó làm quá trình phát hành khó tái lập hoặc không cải thiện đáng kể.

## 8. Chạy non-root và giảm quyền container

Container không mặc nhiên an toàn chỉ vì chạy trong image riêng. Quá trình chạy cần giới hạn quyền theo nhu cầu.

Các nguyên tắc chính:

- Chạy với UID/GID không phải root nếu ứng dụng không thật sự cần root.
- Không cấp `privileged`, không mount Docker socket hoặc host filesystem trừ khi có lý do được kiểm soát.
- Hạn chế Linux capabilities và cho phép ghi chỉ trên các vùng cần thiết.
- Cân nhắc `readOnlyRootFilesystem` nếu ứng dụng không viết lên filesystem gốc.
- Giới hạn CPU/memory phù hợp, dùng seccomp/AppArmor/SELinux khi nền tảng hỗ trợ.
- Không để secret, private key hoặc credential trong image; cấp qua cơ chế runtime có quyền thích hợp.
- Không để process Java ghi ngẫu nhiên vào thư mục JAR; xác định rõ temp, cache và volume cần ghi.
- Kiểm tra quyền đọc của CA certificates, keystore và cấu hình mount.

Một cấu hình container Kubernetes minh họa:

~~~yaml
containers:
  - name: order-service
    image: registry.example.test/apps/order-service:1.8.2
    securityContext:
      runAsNonRoot: true
      runAsUser: 10001
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop: ["ALL"]
    volumeMounts:
      - name: tmp
        mountPath: /tmp
volumes:
  - name: tmp
    emptyDir: {}
~~~

Đây là **đoạn manifest một phần**, chưa đủ để `kubectl apply` trực tiếp. Nếu ứng dụng, JVM hoặc thư viện cần ghi vào vị trí khác, cấu hình volume và quyền truy cập cho phù hợp. Trong Kubernetes, pod/container security context và chính sách cụm còn có thể áp thêm ràng buộc.

Đừng nhầm `USER 10001` trong image là cơ chế chặn mọi đặc quyền khi run: cấu hình runtime có thể thay đổi user hoặc gắn các quyền khác. Cần kiểm soát cả **image** và **deployment policy**.

## 9. Cấu hình: “build once, configure at runtime”

Một image nên có thể được triển khai sang staging và production mà không sửa code, không build lại chỉ để đổi URL database, số replica hoặc secret.

Phân biệt ba loại:

| Loại dữ liệu | Ví dụ | Đặt ở đâu |
|---|---|---|
| Nội dung thuộc artifact | Class/JAR, static resource, metadata phiên bản | Trong image |
| Cấu hình thay đổi theo môi trường | URL service, timeout, feature flag, log level | ConfigMap, biến môi trường không nhạy cảm hoặc config provider |
| Secret | DB password, API token, private key | Secret manager hoặc cơ chế runtime cấp quyền tương ứng |

Cần tránh nhúng `application-prod.yml` chứa credential production vào image. Một số cấu hình môi trường không nhạy cảm có thể đi kèm image nếu có lý do, nhưng khi phải build lại mỗi lần đổi endpoint thì tính tái sử dụng artifact giữa môi trường bị suy giảm.

Với Spring Boot, cấu hình có thể được bind từ biến môi trường hoặc cấu hình ngoài theo quy tắc của ứng dụng. Khi sử dụng secret mount, kiểm soát quyền file và cách reload/rotation. Không đưa secret vào startup command hoặc log chứa tham số CLI.

### 9.1. Đảm bảo image không cần truy cập nguồn Git khi khởi động

Production container không nên tự tải source code, `git pull` hoặc build lại ứng dụng ở startup. Nếu code mới được tải khi chạy, nội dung thực thi không còn được khóa bởi image digest. Việc tải cấu hình, certificate, credential hoặc data qua cơ chế được quản lý là trường hợp khác; chúng vẫn cần audit và versioning thích hợp.

## 10. Đặt tên image, tag và digest

Một tham chiếu image thông thường:

~~~text
registry.example.test/apps/order-service:1.8.2
└────── registry ─────┘└ repository ┘└ tag ┘
~~~

Tag giúp con người nhận diện release, nhưng về bản chất có thể được gán sang digest mới, trừ khi registry áp chính sách immutable tag. Hai lần pull cùng tag tại hai thời điểm có thể nhận nội dung khác nhau nếu tag bị thay.

Digest giúp tham chiếu nội dung theo băm:

~~~text
registry.example.test/apps/order-service@sha256:<64-hex-digits>
~~~

`<64-hex-digits>` ở đây là placeholder để giải thích cú pháp; khi triển khai cần thay bằng digest thật do registry trả về. Với multi-platform image, cần hiểu digest dùng cho index hay manifest nền tảng cụ thể.

### 10.1. Chiến lược tag thường gặp

| Tag | Vai trò | Rủi ro và khuyến nghị |
|---|---|---|
| `1.8.2` | Phiên bản release theo SemVer hoặc quy ước riêng | Cần policy không ghi đè để dễ truy vết |
| `git-<shortsha>` | Liên kết với source revision | Short SHA không phải bằng chứng toàn bộ artifact; giữ full SHA trong metadata |
| `build-1042` | Mã build CI | Hữu ích khi mỗi build tạo image bất biến |
| `staging` | Alias môi trường | Mutable; không dùng làm bằng chứng duy nhất của artifact đã chạy |
| `production` | Alias tới bản được quảng bá | Có thể đổi; triển khai nên lưu digest chính xác |
| `latest` | Tag mặc định/convenience | Không biểu thị bản được duyệt, mức an toàn hay mới nhất theo thời gian tuyệt đối |

Một release có thể đồng thời mang tag `1.8.2` và `git-abc1234` cùng trỏ một digest. Khi promote qua môi trường, cần ghi lại digest cuối cùng thay vì chỉ nhớ alias.

### 10.2. Vì sao không chỉ dùng latest?

Giả sử ba replica được khởi tạo ở các thời điểm khác nhau. Nếu `latest` bị đổi giữa các lần pull, replica A có thể chạy image cũ còn B/C chạy image mới dù Deployment manifest không đổi. `imagePullPolicy: Always` quyết định khi nào runtime kiểm tra registry; nó **không biến tag mutable thành immutable**.

Để triển khai có thể kiểm toán, chọn image theo digest đã được phê duyệt và lưu metadata liên hệ digest với commit, CI run, scan/signature và release.

## 11. Registry là nơi phân phối artifact đã kiểm soát

Image registry lưu trữ manifest và blob để node có thể pull. Một quy trình tốt bao gồm:

- Repository riêng theo team/application hoặc policy tương ứng.
- Quyền `push` chỉ cho CI hoặc vai trò phát hành; runtime chỉ cần `pull`.
- Không cho developer tùy ý ghi đè release tag production.
- Retention policy để dọn image không còn dùng, nhưng giữ những digest cần rollback hoặc phục vụ điều tra.
- Network/TLS và cơ chế xác thực registry phù hợp.
- Audit ai đã push/delete/promote artifact và vào thời điểm nào.
- Kiểm tra provenance và chính sách admission trước khi chạy image nếu nền tảng hỗ trợ.

### 11.1. Quyền tách biệt

| Principal | Build repository | Production repository | Quyền mong muốn |
|---|---|---|---|
| CI build job | Push image đã build và kiểm thử | Không mặc định push | Quyền ghi tối thiểu, có thời hạn |
| Promotion pipeline | Read image đã duyệt | Ghi/promote bản đã duyệt | Chỉ nhóm artifact đã được xét |
| Kubernetes node/service account | Không cần push | Pull | Read-only |
| Security scanner | Read | Read | Không được sửa image |
| Administrator | Quản lý policy | Quản lý policy | Quyền quản trị có audit |

Không nhúng mật khẩu registry vào Dockerfile, Git repository hoặc image config. CI có thể dùng identity liên kết công việc và token ngắn hạn. Runtime lấy quyền pull qua cơ chế của orchestration/cluster, ví dụ image pull credential được quản lý, nhưng không cấp quyền push cho container chỉ để nó tự tải image.

### 11.2. Phân phối qua nhiều region

Nếu cluster chạy ở nhiều region, có thể mirror hoặc replicate image gần node. Cần xác minh nội dung artifact vẫn đúng digest và chính sách chữ ký/quét bảo mật được giữ nguyên. Đừng coi một tag giống tên là chứng minh hai registry đang có cùng nội dung.

## 12. Promotion image giữa dev, staging và production

Một quy trình mẫu:

~~~text
Commit đã review
      |
      v
CI build + unit/integration tests
      |
      v
OCI image -> ghi digest
      |
      v
Security scan + policy + ký/attestation
      |
      v
Deploy staging bằng digest D
      |
      v
Smoke / integration / load test phù hợp
      |
      v
Approve release
      |
      v
Promote chính digest D sang production
      |
      v
Deploy canary/rolling + quan sát
~~~

Mục tiêu **build once, deploy many** nghĩa là cùng nội dung application image được chọn sau khi test, rồi triển khai ở môi trường tiếp theo. Nếu mỗi môi trường tự build lại source thành image mới, dù cùng commit vẫn có thể khác base image, dependency hoặc metadata.

Promotion có thể thực hiện bằng cách cập nhật tham chiếu manifest trong registry, copy artifact kèm xác minh digest, hoặc dùng công cụ quản lý release. Nếu copy image giữa registry và digest manifest thay đổi do khác cấu trúc/index/metadata, pipeline cần xác minh quan hệ với artifact đã duyệt và chính sách tương đương; đừng ghi “cùng digest” khi thực tế registry trả digest khác mà chưa giải thích.

### Ghi metadata release tối thiểu

Một release record nên có:

~~~yaml
service: order-service
sourceRevision: "<full-git-commit>"
imageRepository: "registry.example.test/apps/order-service"
imageDigest: "sha256:<digest-from-registry>"
buildPipelineRun: "<ci-run-id>"
buildToolchain: "JDK 21 / Gradle (pinned versions)"
scanPolicyResult: "approved"
deploymentEnvironment: "production"
~~~

Giá trị đặt trong dấu `<...>` là chỗ cần điền thật. Tránh ghi secret trong metadata, nhãn image hoặc ticket phát hành.

## 13. Bảo mật chuỗi cung ứng image

Image có thể chứa dependency có lỗ hổng, package thừa hoặc bị thay thế trái phép trên đường phân phối. Quản lý chuỗi cung ứng cần kiểm soát nhiều bước:

1. **Nguồn:** chỉ build từ commit đã xác định, branch/review policy đã được áp dụng.
2. **Toolchain:** kiểm soát JDK, Gradle/Maven, base image và dependency resolution.
3. **Build identity:** CI job có quyền phù hợp, không dùng credential cá nhân dài hạn.
4. **SBOM:** ghi danh sách thành phần phần mềm và version theo khả năng của công cụ.
5. **Vulnerability scanning:** quét OS packages, runtime và application dependencies phù hợp; xác định chính sách xử lý.
6. **Provenance/attestation:** lưu bằng chứng artifact được tạo từ nguồn và quy trình nào.
7. **Signing/verification:** xác minh chữ ký hoặc attestation gắn với digest và danh tính người phát hành.
8. **Admission/deploy:** từ chối image không đáp ứng policy trên môi trường cần bảo vệ.
9. **Runtime:** áp dụng user/quyền tối thiểu, namespace/volume/network policy và logging phù hợp.

### 13.1. Quét lỗ hổng là tín hiệu, không phải sự bảo đảm tuyệt đối

Quét image có thể phát hiện dependency hoặc package nằm trong danh sách lỗ hổng đã biết. Công cụ có thể không nhìn thấy thành phần tải động lúc runtime, lỗ hổng zero-day hoặc logic nghiệp vụ dễ bị khai thác. Kết quả còn chịu ảnh hưởng bởi cơ sở dữ liệu CVE và khả năng nhận diện package.

Nên có chính sách:

- Xếp ưu tiên theo mức nghiêm trọng, khả năng khai thác, đường truy cập và tài sản chịu ảnh hưởng.
- Phân biệt finding có bản vá với finding chưa có bản vá.
- Có thời hạn và owner xử lý hoặc ngoại lệ có kiểm soát.
- Quét lại các image đang chạy sau khi cơ sở dữ liệu lỗ hổng cập nhật.
- Khi base image có bản vá, build lại image ứng dụng từ base đã được duyệt, chạy lại test và phát hành **digest mới**.

Không biến việc sửa lỗ hổng thành thao tác ghi đè tag cũ mà không có release record.

### 13.2. Ký image và policy triển khai

Chữ ký phải liên kết tới digest cụ thể và danh tính phát hành được tin cậy. Khi xác minh, cần kiểm tra signer, đối tượng được ký, chính sách môi trường và tình trạng thu hồi/hiệu lực theo cơ chế đã chọn. Một image “đã ký” bởi nguồn không được tin cậy không tự động đủ điều kiện production.

Có thể gắn attestation cho CI pipeline, test status và provenance. Tuy nhiên không nên coi attestation là cam kết nội dung không có bug: nó chứng minh những thuộc tính của quy trình và artifact trong phạm vi đã định.

## 14. Build reproducibility và truy nguyên từ digest đến source

Một build có thể được lặp lại từ cùng commit, nhưng nếu dependency dùng dynamic version, base image tag thay đổi hoặc build sinh timestamp ngẫu nhiên, output có thể khác.

Để nâng khả năng tái lập:

- Ghim version dependency và toolchain; cân nhắc dependency locking/verification.
- Kiểm soát base image theo digest phù hợp.
- Ghi source revision, build args không nhạy cảm và build system version.
- Cố định nguồn package/registry và kiểm tra checksum/signature.
- Hạn chế tạo artifact phụ thuộc thời điểm build nếu không cần; dùng cơ chế reproducible archives khi có thể.
- Không tải file từ URL không version trong bước Docker build.
- Ghi digest đã push từ registry; đừng suy luận digest chỉ từ tag hoặc tên artifact.
- Không kỳ vọng cùng digest giữa các platform nếu nội dung JRE/native library khác nhau.

**Reproducible build** mạnh hơn “có thể chạy lại pipeline”: hai build từ đầu vào xác định cần cho kết quả tương ứng được kiểm chứng. Để đạt mức bit-for-bit có thể cần kiểm soát metadata, timestamp và thứ tự file trong archive. Nếu chưa đạt, vẫn phải đảm bảo artifact phát hành là bất biến và có provenance rõ.

## 15. Kiểm thử image trước khi triển khai

Bài test ứng dụng chạy bằng `./gradlew test` chưa đủ chứng minh image có entrypoint đúng, file permission hợp lệ, kiến trúc CPU phù hợp hoặc health endpoint hoạt động.

Một pipeline nên có những lớp kiểm tra:

| Lớp kiểm tra | Câu hỏi chính | Ví dụ |
|---|---|---|
| Build test | Source có compile và unit/integration test đạt? | Gradle test |
| Image structure | Image có đúng JAR, user và entrypoint? | Inspect metadata/layer |
| Security scan | Có package/dependency cần khắc phục? | Registry/image scanner |
| Startup smoke | Container có khởi động bằng runtime image thực? | Chạy container thử |
| Readiness | Service thật sự sẵn sàng nhận traffic? | HTTP readiness |
| Config/secrets | Có thể chạy bằng cấu hình được cấp khi runtime? | Mount/config thử |
| Connectivity | Service nói chuyện được với dependency thử nghiệm? | Integration test |
| Resource | Memory/CPU limit có hợp lý? | Load và saturation test |
| Shutdown | Khi nhận SIGTERM, có dừng nhận traffic và thoát an toàn? | Stop container/pod |
| Platform | Image chạy được trên node architecture được hỗ trợ? | amd64/arm64 smoke |

### 15.1. Chạy smoke test local

Nếu image được build bằng Dockerfile của service:

~~~bash
docker build -t order-service:dev .
docker run --rm --name order-local -p 8080:8080 order-service:dev
~~~

Ở terminal khác, với ứng dụng đã cấu hình Spring Boot Actuator readiness:

~~~bash
curl --fail http://localhost:8080/actuator/health/readiness
~~~

Endpoint readiness chỉ tồn tại khi ứng dụng có Actuator và được cấu hình group/probe phù hợp. Nếu không, dùng endpoint kiểm tra do ứng dụng chủ động cung cấp. Đừng biến kiểm tra startup thành một test chỉ thấy port mở: service có thể mở socket nhưng chưa kết nối được các dependency bắt buộc.

### 15.2. Kiểm tra nội dung image

Có thể xem metadata và layer bằng công cụ container phù hợp:

~~~bash
docker image inspect order-service:dev
docker image history order-service:dev
~~~

Kiểm tra runtime user, entrypoint, exposed port, labels và lượng layer. Nếu cần kiểm tra hệ thống file, ưu tiên công cụ inspect/phân tích image có thể làm việc với image tối giản; không mặc định image production có shell.

### 15.3. Không đưa test secrets thật vào smoke

Dùng database, broker và provider giả lập hoặc môi trường sandbox có dữ liệu riêng. Không sử dụng khóa thanh toán production cho bài test local hoặc CI. Đường đi từ CI đến image registry phải có quyền riêng, không nhúng credential vào image để smoke “chạy cho tiện”.

## 16. Triển khai image trên Kubernetes

Deployment chỉ mô tả desired state; controller và kubelet sẽ phối hợp tạo Pod và pull image trên node phù hợp. Một manifest minh họa:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: commerce
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-service
          image: registry.example.test/apps/order-service:1.8.2
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              memory: "768Mi"
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            allowPrivilegeEscalation: false
~~~

Đây là ví dụ kiến trúc, cần bổ sung registry auth, service, cấu hình, security policy và điều chỉnh probe/nguồn lực trước khi dùng thật. Để bảo đảm triển khai đúng artifact đã duyệt, nên sử dụng **image digest** thực tế thay cho tag mutable. Việc tham chiếu tag trong ví dụ giúp dễ đọc cú pháp.

### 16.1. Readiness khác liveness

- **Readiness:** pod có nên nhận request mới không. Khi chưa sẵn sàng, endpoint phải phản ánh đúng khả năng phục vụ.
- **Liveness:** tiến trình có rơi vào trạng thái không thể tự hồi phục, cần được restart không.
- **Startup probe:** hữu ích nếu ứng dụng có pha khởi động dài; cho phép trì hoãn việc đánh giá liveness/readiness theo cách phù hợp.

Một liveness probe gọi đồng loạt tới database có thể gây restart hàng loạt khi database tạm lỗi. Không nên coi mất kết nối dependency trong vài giây là lý do chắc chắn phải restart toàn bộ service. Thiết kế probe dựa trên hành vi ứng dụng và khả năng hồi phục.

### 16.2. Resource requests và limits

`requests` giúp scheduler quyết định nơi đặt pod; `limits` giúp giới hạn tài nguyên theo runtime. JVM cần được cấu hình/đo để hoạt động trong memory limit bao gồm heap, metaspace, stack, native memory và phần phụ trợ. Nếu giới hạn quá chặt, container có thể bị OOMKilled dù heap dump không thể hiện toàn bộ memory đã dùng.

Không sao chép `512Mi` và `768Mi` vào production một cách máy móc. Cần đo startup, steady state, peak, GC và số request đồng thời.

### 16.3. Rolling update không tự bảo đảm rollback nghiệp vụ

RollingUpdate có thể thay pod từng phần, giúp giảm gián đoạn nếu readiness đúng và capacity đủ. Tuy nhiên nếu image mới chạy migration không tương thích hoặc phát event mà consumer cũ không đọc được, hạ image chưa chắc cứu được hệ thống. Phải kiểm tra cả API/message contract và database migration theo hướng expand-contract.

## 17. Đảm bảo image xử lý shutdown đúng

Trong orchestration, khi pod bị thay hoặc scale down, ứng dụng có thể nhận signal kết thúc và có một cửa sổ để dừng.

Hành vi mong muốn:

~~~text
Pod nhận yêu cầu terminate
    |
    v
Endpoint readiness giảm / không nhận request mới
    |
    v
Xử lý nốt request in-flight trong giới hạn
    |
    v
Đóng connection và worker có trật tự
    |
    v
Process thoát trước khi hết grace period
~~~

Trong thực tế thứ tự sự kiện liên quan EndpointSlice, load balancer và hook có thể không đồng thời; không chỉ dựa vào một lệnh “sleep 5 giây” để bảo đảm hết traffic. Cần thử nghiệm đường request thực tế, retry và thời gian drain.

Với Spring Boot, xem xét graceful shutdown và thời hạn shutdown phase cùng cấu hình Kubernetes `terminationGracePeriodSeconds`. Với message consumer, phải dừng nhận message mới, hoàn tất hoặc để redelivery an toàn, sau đó commit/ACK theo hợp đồng.

Cách đóng gói cũng ảnh hưởng: `ENTRYPOINT` dạng exec có thể giúp signal đến đúng JVM. Nếu dùng shell script làm wrapper, phải xử lý `exec` hoặc chuyển signal, tránh để shell giữ PID 1 khiến JVM không nhận SIGTERM như dự kiến.

## 18. Quản lý release, rollout và rollback

Mỗi release nên có bản ghi chính xác:

~~~text
Service: order-service
Version: 1.8.2
Source: commit X
Image: registry.example.test/apps/order-service
Digest: sha256:<được lấy từ registry>
Stage approval: passed
Production deploy: revision Y
Previous digest: sha256:<digest trước>
~~~

**Rollout** có thể là rolling update, canary hoặc blue/green tùy mức độ rủi ro. Với canary, cho một phần traffic đi qua image mới, quan sát error rate, latency, business metric và các dependency quan trọng trước khi mở rộng.

**Rollback** nên đưa hệ thống về một digest đã biết và một cấu hình còn tương thích. Các thành phần cần suy nghĩ ngoài image:

- Migration database đã chạy có còn tương thích với binary cũ?
- Event đã phát từ phiên bản mới có còn được consumer cũ xử lý?
- Secret/config đổi theo release có còn được version cũ chấp nhận?
- External side effect đã xảy ra (thanh toán, email) có cần reconciliation?
- Autoscaling, capacity và resource limits có phù hợp với version cũ?

Không xóa ngay image trước đó nếu nó còn thuộc cửa sổ rollback đã duyệt. Retention chính sách nên cân đối chi phí lưu trữ và yêu cầu phục hồi.

## 19. Những lỗi thường gặp khi đóng gói image

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Dùng tag latest để xác định production release | Không biết chính xác nội dung đang chạy | Pin digest và lưu release record |
| Ghi đè tag/version cũ | Build/rollback mất tính truy vết | Immutable release và registry policy |
| COPY toàn bộ repository vào runtime | Mang source, log, cache hoặc secret thừa | Multi-stage, .dockerignore, kiểm tra filesystem |
| Dùng JDK image làm runtime khi chỉ cần JRE | Image lớn và nhiều tool không cần | Runtime image phù hợp |
| Container chạy root theo mặc định | Tăng tác động khi process bị khai thác | Non-root và security context |
| Ghi secret qua ARG/ENV trong Dockerfile | Lộ qua metadata/cache/log | Secret cấp ở runtime hoặc build secret ngắn hạn |
| Chỉ test JAR mà không chạy image | Bỏ sót entrypoint, permission, OS/runtime mismatch | Startup smoke trên image cuối |
| Readiness phụ thuộc nhầm vào một endpoint không tồn tại | Pod luôn NotReady | Test và cấu hình probe đúng |
| Liveness gọi dependency không ổn định | Restart storm khi dependency lỗi | Phân biệt readiness/liveness |
| Không định nghĩa hành vi SIGTERM | Mất request hoặc xử lý message dang dở | Graceful shutdown test |
| Một image chỉ build amd64 nhưng cluster có arm64 | Pod không khởi động trên node khác kiến trúc | Multi-platform build/test hoặc node scheduling |
| Bỏ qua base image updates | Tồn tại lỗ hổng đã có bản vá | Theo dõi và rebuild chủ động |
| CI dùng token registry admin dài hạn | Tăng hậu quả khi CI bị xâm nhập | Quyền tối thiểu và credential ngắn hạn |
| Bật scan nhưng không có owner xử lý finding | Cảnh báo tích tụ, release policy không rõ | Quy tắc chặn/ngoại lệ và deadline |

## 20. Tình huống thực hành: từ commit đến production

Một nhóm có ba service: Order, Inventory và Payment. Cần phát hành riêng Order 1.8.2 sau khi sửa lỗi timeout.

### Bước 1 — Chốt input

Ghi commit chính xác, Gradle/JDK version và dependency lock. Xác định base image đã được phê duyệt theo digest. Không build từ branch mutable nếu pipeline chưa xác định commit thực tế.

### Bước 2 — Chạy test ứng dụng

Chạy unit/integration test phù hợp, bảo đảm JAR kết quả đến từ cùng source revision. Nếu sử dụng multi-stage Dockerfile, test có thể chạy trong build stage; pipeline vẫn cần lưu kết quả và log kiểm toán.

### Bước 3 — Build image

Dùng Dockerfile nhiều giai đoạn. Đánh tag theo version/revision và push vào registry với credential CI phạm vi nhỏ. Ghi lại digest registry trả về sau push.

### Bước 4 — Kiểm tra bảo mật

Quét dependency, OS packages và image final; sinh SBOM và provenance nếu quy trình yêu cầu. Ký hoặc gắn attestation theo policy; xử lý các finding vượt ngưỡng đã định.

### Bước 5 — Smoke và integration trên image cuối

Chạy image với cấu hình staging và fake dependency. Kiểm tra startup, readiness, quyền non-root, request/response, SIGTERM, resource và việc không chứa secret.

### Bước 6 — Promote

Triển khai staging đúng artifact đã xét. Sau khi đạt tiêu chí, promote cùng artifact đến production bằng digest đã xác minh; không build lại code chỉ vì chuyển môi trường.

### Bước 7 — Canary hoặc rolling update

Cho một tỷ lệ traffic đi qua Order mới trong khi Inventory/Payment giữ version đang chạy. Theo dõi timeout, retry count, error rate và business metrics. Nếu hợp đồng runtime vẫn tương thích, không cần ép hai service còn lại deploy cùng thời điểm.

### Bước 8 — Khôi phục khi cần

Nếu canary lỗi, hạ về digest Order trước đó và kiểm tra DB/event/config có còn tương thích không. Không xóa image lỗi trước khi thu thập metadata cần cho điều tra; điều chỉnh quyền và retention phù hợp.

### Bước 9 — Đóng hồ sơ release

Ghi source revision, digest, version, CI run, kết quả test/scan, phê duyệt và môi trường đã triển khai. Dùng dữ liệu này khi sự cố xuất hiện để biết chính xác artifact nào đang phục vụ request.

## 21. Bài tập thực hành

### Bài A — Viết Dockerfile cho Spring Boot

Một service Java 21 có `bootJar` tên `app.jar`. Hãy viết Dockerfile hai stage, một stage build với JDK/Gradle và một stage runtime chỉ chứa JRE/JAR. Chạy bằng non-root, không copy source vào runtime, và mô tả cách xác nhận image cuối khởi động được.

**Điều cần kiểm chứng:** đúng JAR từ build đã test, user runtime không phải root, process nhận signal, không có secret hay build cache trong image cuối.

### Bài B — Phân biệt tag và digest

Order được deploy với tag `staging`. Nhóm phát hành lại tag này cho image mới nhưng không đổi Deployment manifest. Hãy giải thích vì sao hai node có thể lấy nội dung khác nhau và thiết kế release record/manifest dựa trên digest để loại bỏ tính mơ hồ.

### Bài C — Thiết kế .dockerignore

Repository chứa source, `.git`, `.env`, `build/libs/app.jar`, private key thử nghiệm, log và IDE metadata. Với hai kiểu build “JAR đã build” và “multi-stage build từ source”, hãy thiết kế ignore rules riêng để chỉ gửi những file cần thiết mà vẫn không lộ secret.

### Bài D — Chuyển image qua ba môi trường

Dev, staging và production có URL database khác nhau. Hãy thiết kế quá trình build once/deploy many, phân loại cấu hình và secret, cách chọn digest, cách cấp quyền pull và những bằng chứng cần có trước production approval.

### Bài E — Java container bị OOMKilled

Image chạy được local nhưng bị OOMKilled ở Kubernetes với memory limit nhỏ. Hãy liệt kê phép đo JVM/OS cần xem, phân biệt heap và native memory, và đề xuất quy trình điều chỉnh limits/requests dựa trên tải thực nghiệm.

### Bài F — Registry bị xâm nhập hoặc image bị thay

Một tag release đã được push lại ngoài CI. Hãy mô tả cách phát hiện sự khác biệt digest, kiểm tra chữ ký/provenance, hạn chế quyền push, khóa tag và khôi phục về artifact đã xác minh.

### Bài G — Rollback khi schema đã đổi

Order image 1.9.0 đã chạy migration database rồi cần rollback về 1.8.2. Hãy xác định những điều kiện khiến rollback image không an toàn và đề xuất chiến lược expand-contract để hỗ trợ phiên bản cũ và mới trong cửa sổ triển khai.

## 22. Những điều cần ghi nhớ

- **Image là artifact phân phối; container là tiến trình đang chạy từ image.** Registry là nơi quản lý và cung cấp artifact cho runtime.
- **Build có thể tái lập và kiểm toán** cần source, toolchain, dependency và base image được kiểm soát; chỉ có tag đẹp chưa đủ.
- **Multi-stage build và runtime tối thiểu** giúp tránh đưa compiler, source và cache vào production image.
- **Không chứa secret trong image.** Cấu hình khác nhau theo môi trường được cấp lúc chạy.
- **Tag có thể thay đổi; digest gắn với nội dung.** Production nên ghi nhận digest cụ thể và bằng chứng phê duyệt.
- **Security scanning, SBOM, signing và provenance** là các lớp kiểm soát bổ sung, không thay thế việc giới hạn quyền runtime.
- **Readiness, liveness, startup, resource và graceful shutdown** quyết định image có vận hành tốt trong orchestration hay không.
- **Promotion và rollback** cần theo một artifact đã xác minh, xét cả database, event và cấu hình liên quan.
- **Mỗi service có lịch image release riêng** khi hợp đồng giữa các dịch vụ còn tương thích.

Một quy trình quản lý image tốt biến kết quả build thành một đơn vị triển khai rõ nguồn gốc, được kiểm thử và có thể quay lại bản trước. Khi đó các nhóm microservices có thể phát hành độc lập trong khi vẫn duy trì khả năng quan sát, tính nhất quán và quyền kiểm soát bảo mật của toàn hệ thống.
