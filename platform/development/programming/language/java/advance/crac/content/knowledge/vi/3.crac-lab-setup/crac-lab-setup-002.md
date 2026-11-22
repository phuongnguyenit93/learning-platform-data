# Chọn và cố định phiên bản JDK, thư viện org.crac và hệ điều hành

Để thực hành CRaC ổn định, cần chọn một bộ môi trường gồm JDK có hỗ trợ checkpoint/restore, Java API `org.crac`, hệ điều hành và các thành phần hệ thống tương thích. Chỉ ghi “Java 21” hoặc “Linux” là chưa đủ để tái tạo môi trường: hai bản JDK cùng major version có thể khác nhau về hỗ trợ CRaC, còn hai máy Linux có thể khác kernel, kiến trúc CPU, CRIU và cấu hình container.

Mục tiêu của việc cố định phiên bản là để mọi lần build, tạo checkpoint image và restore đều dùng một bộ thành phần đã được kiểm chứng. Khi cần nâng cấp, ta thay đổi có chủ đích, kiểm tra lại toàn bộ quy trình rồi mới công bố bộ phiên bản mới.

## 1. Một bộ môi trường CRaC gồm những gì?

Khi lựa chọn môi trường, hãy xem xét đồng thời các thành phần sau:

| Thành phần | Cần xác định | Vì sao cần cố định |
|---|---|---|
| JDK | Nhà cung cấp, dòng JDK, phiên bản đầy đủ, bản build và kiến trúc | Không phải mọi bản JDK đều có triển khai CRaC; các bản build có thể khác về cách hỗ trợ checkpoint/restore |
| CRaC Java API | Tọa độ Maven `org.crac:crac` và phiên bản nếu dự án cần dependency này | Mã nguồn cần API tương thích với JDK và các thư viện tích hợp CRaC |
| Hệ điều hành | Bản phân phối Linux, phiên bản, kiến trúc và thư viện hệ thống | Checkpoint/restore phụ thuộc vào khả năng của kernel và môi trường tiến trình |
| CRIU | Phiên bản công cụ và cách cài đặt | Trên các triển khai Linux sử dụng CRIU, công cụ này tham gia lưu và khôi phục trạng thái tiến trình |
| Container/runtime | Base image, runtime container, cấu hình namespace, cgroup, quyền và mount | Container image không tự mang theo kernel của host hoặc mọi quyền cần cho checkpoint/restore |
| Công cụ build | Gradle Wrapper, cấu hình toolchain và dependency lock | Giúp quá trình biên dịch và phân giải dependency có thể tái lập |

Các thành phần trên tạo thành một **bộ phiên bản đã kiểm chứng**. Không nên chọn JDK, thư viện và hệ điều hành riêng rẽ theo tiêu chí “mới nhất”, sau đó giả định chúng tương thích với nhau.

## 2. Chọn JDK có hỗ trợ CRaC

### 2.1. Bắt đầu từ khả năng CRaC của bản phân phối

CRaC cần sự hỗ trợ từ JVM và nền tảng checkpoint/restore. Cài một JDK Java thông thường rồi thêm dependency `org.crac` vào Gradle không tự biến JVM đó thành CRaC-enabled JDK.

Khi chọn nhà cung cấp JDK, hãy kiểm tra tài liệu chính thức của đúng nhà cung cấp và đúng dòng phiên bản. Xác nhận các điểm sau:

- Nhà cung cấp có bản JDK tích hợp hoặc hỗ trợ CRaC cho major version mà dự án cần hay không.
- Bản build đó hỗ trợ hệ điều hành và kiến trúc CPU dự kiến triển khai hay không.
- Cách bật checkpoint, cách tạo image và cách restore được tài liệu hóa như thế nào.
- Bản JDK có yêu cầu CRIU, kernel, quyền hoặc cấu hình hệ thống cụ thể nào.
- Nhà cung cấp có lịch cập nhật bảo mật, chính sách hỗ trợ và điều khoản sử dụng phù hợp hay không.
- Phiên bản đó có tương thích với framework, agent, JNI và các thư viện native của ứng dụng hay không.

Có thể chọn JDK 21 làm major version cho một dự án đang dùng Java 21, nhưng phải chọn **bản phân phối JDK 21 có CRaC thực sự**. Không suy ra khả năng CRaC chỉ từ số phiên bản Java hoặc từ việc một bản JDK có thể chạy ứng dụng Java bình thường.

### 2.2. Ghi nhận phiên bản đầy đủ

Một số thông tin khác nhau thường bị gộp thành cụm “Java 21”:

- **Major version:** ví dụ 21, thể hiện dòng ngôn ngữ và nền tảng Java.
- **Patch/update version:** ví dụ `21.0.x`, thể hiện bản cập nhật trong dòng JDK.
- **Vendor build:** nhà cung cấp, số build và các bản vá riêng của nhà cung cấp.
- **CRaC capability:** khả năng checkpoint/restore cụ thể của bản build đó.

Hai JDK cùng Java 21 nhưng khác nhà cung cấp hoặc khác bản build không mặc nhiên tạo và restore được cùng một checkpoint image. Đối với image dùng trong triển khai, nên cố định nhà cung cấp, phiên bản đầy đủ và build đã được thử nghiệm. Khi cần thận trọng, hãy tạo và restore image bằng cùng một bản JDK chính xác.

Có thể xem thông tin JDK đang chạy bằng:

```bash
java -version
java -XshowSettings:properties -version
```

Lệnh thứ hai hiển thị thêm các thuộc tính như `java.vendor`, `java.version`, `java.runtime.version`, `java.home` và `os.arch`. Hãy lưu kết quả vào log build hoặc hồ sơ môi trường để biết chính xác JDK nào đã tạo image.

### 2.3. Dùng toolchain cho biên dịch, cố định runtime cho checkpoint

Gradle Java Toolchains giúp chọn JDK theo major version và nhà cung cấp. Ví dụ:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Đoạn cấu hình trên yêu cầu Java 21 cho tác vụ sử dụng toolchain. Nó chưa khóa đầy đủ patch version, số build hoặc khả năng CRaC. Gradle có thể tìm một JDK phù hợp đã cài trên máy hoặc tải toolchain theo cấu hình; vì vậy, không nên xem riêng cấu hình major version là bằng chứng runtime đã được cố định.

Hãy tách hai yêu cầu:

1. **JDK biên dịch:** toolchain cần đúng major version và vendor theo quy ước của dự án.
2. **JDK tạo image và restore:** phải là bản CRaC-enabled JDK đã được chốt chính xác, thường được cung cấp qua một container image có tag phiên bản đầy đủ và digest bất biến, hoặc qua bộ cài JDK được quản lý có checksum.

Nếu dùng toolchain, hãy cấu hình vendor khi dự án đã chọn nhà cung cấp. Sau đó, CI vẫn cần xác minh phiên bản runtime thực tế bằng `java -version` và các thuộc tính hệ thống. Toolchain không thay thế bước xác minh bản build CRaC.

## 3. Chọn và cố định thư viện `org.crac`

### 3.1. Phân biệt Java API với khả năng checkpoint của JVM

Package `org.crac` cung cấp các kiểu Java mà ứng dụng sử dụng để đăng ký resource và xử lý vòng đời, chẳng hạn `Resource`, `Context` và `Core`. Dependency Maven thường được khai báo với tọa độ:

```text
org.crac:crac
```

Dependency này cung cấp API cho mã Java theo cách đóng gói của thư viện. Nó không thay thế một JDK có khả năng CRaC, không cung cấp khả năng checkpoint của kernel và không cài đặt CRIU. Một ứng dụng biên dịch được với `org.crac` vẫn có thể không checkpoint hoặc restore được nếu runtime không hỗ trợ CRaC.

Một số bản phân phối JDK hoặc framework có cách cung cấp/tích hợp API riêng. Vì vậy, trước khi thêm dependency, hãy đọc hướng dẫn của JDK và framework đã chọn. Mục tiêu là có một nguồn API nhất quán, tránh đóng gói các lớp trùng hoặc không tương thích với runtime.

### 3.2. Khóa phiên bản dependency

Không dùng phiên bản động như `1.+`, `latest.release`, version range hoặc `SNAPSHOT` cho dependency được dùng trong quy trình tạo image. Những khai báo đó có thể phân giải ra một phiên bản khác ở lần build sau mà không có thay đổi trong mã nguồn.

Với Gradle Version Catalog, có thể khai báo một phiên bản tường minh:

```toml
[versions]
crac-api = "1.4.0"

[libraries]
crac-api = { module = "org.crac:crac", version.ref = "crac-api" }
```

Sau đó tham chiếu alias trong `build.gradle`:

```groovy
dependencies {
    implementation(libs.crac.api)
}
```

`1.4.0` ở đây là ví dụ về cách ghi phiên bản cụ thể, không phải tuyên bố đây là phiên bản mới nhất hoặc tương thích với mọi JDK. Khi áp dụng cho dự án, hãy chọn phiên bản được tài liệu của bản JDK/framework đã chốt hỗ trợ và xác minh bằng build thực tế. Nếu nhà cung cấp JDK đã cung cấp API theo cách khác, hãy tuân theo hướng dẫn đó thay vì thêm một dependency thứ hai một cách máy móc.

Với dependency có ảnh hưởng đến khả năng chạy sau restore, cần kiểm tra cả dependency trực tiếp lẫn dependency bắc cầu. Không chỉ khóa `org.crac:crac` mà bỏ qua phiên bản framework hoặc thư viện quản lý connection pool, HTTP client và scheduler có tích hợp CRaC.

### 3.3. Khóa dependency và xác minh artifact

Version Catalog giúp tập trung khai báo phiên bản, nhưng chưa tự khóa mọi kết quả phân giải dependency. Có thể bật dependency locking trong Gradle:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Sau đó tạo hoặc cập nhật lock state bằng một tác vụ Gradle phù hợp, ví dụ:

```bash
./gradlew dependencies --write-locks
```

Khi dependency thay đổi có chủ đích, hãy xem diff của các lockfile và xác nhận những phiên bản mới. Không xóa lockfile chỉ để giải quyết một lỗi phân giải mà chưa hiểu nguyên nhân.

Có thể bật dependency verification để kiểm tra checksum hoặc chữ ký artifact theo metadata đã được xác nhận. Khi tạo verification metadata, hãy rà soát nguồn tải và giá trị checksum trước khi đưa file metadata vào repository. Việc tự động chấp nhận mọi checksum từ một lần tải không được kiểm tra sẽ làm giảm ý nghĩa của bước xác minh.

Trong CI, nên lưu lại dependency tree của cấu hình runtime để xác định chính xác artifact nào được đóng gói. Khi ứng dụng dùng `org.crac`, hãy kiểm tra không có nhiều phiên bản API xung đột và không có thư viện thay thế lớp CRaC bằng một bản không tương thích.

## 4. Chọn hệ điều hành và nền tảng checkpoint/restore

### 4.1. Xác định nền tảng được JDK hỗ trợ

Các triển khai CRaC phổ biến trên Linux phối hợp với CRIU (Checkpoint/Restore In Userspace) để checkpoint và restore tiến trình. Vì vậy, môi trường thực hành cần một bản phân phối Linux, kernel và cấu hình hệ thống đáp ứng yêu cầu của bản JDK/CRaC đã chọn.

Không nên mặc định rằng mọi hệ điều hành đều hỗ trợ quy trình này như nhau. Máy phát triển Windows hoặc macOS vẫn có thể dùng để viết mã, chỉnh sửa Gradle và thực hiện những bước build thông thường. Tuy nhiên, checkpoint/restore phải được kiểm chứng trên nền tảng mà bản JDK CRaC hỗ trợ. Nếu môi trường triển khai là Linux, hãy chạy smoke test checkpoint/restore trên Linux ngay trong CI hoặc môi trường thử nghiệm tương ứng.

Khi chọn bản phân phối Linux, kiểm tra:

- Phiên bản và cấu hình kernel có đáp ứng yêu cầu của CRIU và JDK hay không.
- Kiến trúc CPU là `x86_64`/`amd64` hay `aarch64`/`arm64`, và JDK có build CRaC cho kiến trúc đó hay không.
- Phiên bản glibc và các thư viện hệ thống có tương thích với JDK cùng thư viện native hay không.
- Phiên bản CRIU được nhà cung cấp JDK yêu cầu hoặc kiểm thử.
- Các tính năng namespace, cgroup, mount và quyền cần thiết có được môi trường container cấp hay không.
- Chính sách bảo mật của host, container runtime và nền tảng điều phối có cho phép thao tác checkpoint/restore hay không.

Không chọn một bản phân phối chỉ vì nó có kích thước container nhỏ. Ví dụ, một image dùng musl hoặc một môi trường tối giản có thể thiếu thư viện hoặc công cụ mà bản JDK/CRIU đã chọn cần. Hãy kiểm tra tài liệu tương thích trước khi dùng các image tối giản như Alpine.

### 4.2. Cố định bản phân phối và kiến trúc

Trong tài liệu môi trường, ghi rõ tên và phiên bản bản phân phối, ví dụ một bản Ubuntu hoặc Debian cụ thể, cùng kiến trúc CPU. Tránh các nhãn trôi nổi như `latest`, `stable` hoặc chỉ ghi `linux`.

Các kiến trúc `amd64` và `arm64` là hai mục tiêu riêng. Một image được tạo trên `amd64` không mặc nhiên restore được trên `arm64`. Nếu sản phẩm hỗ trợ cả hai kiến trúc, hãy có bộ JDK, image, cấu hình CRIU và bài kiểm tra riêng cho từng kiến trúc.

Kiểm tra thông tin hệ điều hành và kiến trúc trên máy Linux:

```bash
cat /etc/os-release
uname -a
uname -m
ldd --version
criu --version
```

Các lệnh trên giúp ghi nhận bản phân phối, kernel, kiến trúc, phiên bản glibc và CRIU. Nếu `criu` chưa có trong môi trường, cần cài đặt theo hướng dẫn của bản phân phối và xác nhận lại phiên bản sau cài đặt.

### 4.3. Phân biệt container image với kernel của host

Container image có thể cố định filesystem, JDK, thư viện và công cụ CRIU bên trong container. Nhưng container dùng kernel của host. Vì vậy, pin digest của container image chưa đủ để cố định toàn bộ môi trường checkpoint/restore.

Trong Docker hoặc Kubernetes, còn phải xem xét:

- Container runtime và phiên bản của nó.
- Quyền hoặc capability cần thiết cho checkpoint/restore.
- Cấu hình PID namespace, mount namespace, network namespace và cgroup.
- Đường dẫn volume và mount point có tồn tại, có cùng ý nghĩa khi restore hay không.
- Security profile như seccomp, AppArmor hoặc SELinux có chặn thao tác cần thiết hay không.
- Cách nền tảng xử lý địa chỉ mạng, port và danh tính instance sau restore.

Không bật quyền rộng chỉ để làm cho thử nghiệm đầu tiên chạy được. Hãy dùng cấu hình quyền tối thiểu theo tài liệu của CRIU, container runtime và nền tảng triển khai, rồi kiểm thử đúng cấu hình đó. Một thử nghiệm chạy trong privileged container nhưng môi trường thật không cấp quyền tương tự không chứng minh rằng quy trình triển khai sẽ hoạt động.

## 5. Xây dựng một ma trận phiên bản tương thích

Trước khi cài đặt, hãy lập ma trận ghi rõ các thành phần và trạng thái kiểm chứng. Ví dụ về cấu trúc hồ sơ:

```yaml
cracEnvironment:
  java:
    vendor: "<JDK vendor>"
    distribution: "<CRaC-enabled distribution>"
    version: "<full version and build>"
    architecture: "amd64"
  api:
    coordinate: "org.crac:crac"
    version: "<pinned version approved for this JDK>"
  operatingSystem:
    distribution: "<Linux distribution>"
    version: "<exact release>"
    architecture: "amd64"
    kernelBaseline: "<tested kernel baseline>"
  criu:
    version: "<tested version>"
  container:
    image: "<repository>:<immutable version>@sha256:<digest>"
    runtime: "<tested runtime and version>"
  build:
    gradleWrapper: "<wrapper version>"
    dependencyLocking: true
    dependencyVerification: true
  validation:
    checkpoint: "PASS/NOT_TESTED"
    restore: "PASS/NOT_TESTED"
    lastVerified: "<date or CI build identifier>"
```

Các giá trị trong dấu ngoặc nhọn là chỗ cần điền theo môi trường đã chọn. Đây là hồ sơ mô tả và kiểm soát phiên bản; không nên sao chép nguyên các placeholder vào cấu hình chạy.

Ma trận có thể được mở rộng theo môi trường `development`, `CI` và `production`, nhưng cần chỉ ra thành phần nào phải giống nhau. Đặc biệt, JDK dùng để tạo image và JDK dùng để restore cần tuân thủ chính sách tương thích đã được kiểm thử. Nếu khác phiên bản, phải có bằng chứng từ tài liệu nhà cung cấp và kết quả thử nghiệm thay vì mặc định rằng khác biệt đó an toàn.

Một ví dụ về cách ghi nhận trạng thái kiểm thử:

| Hạng mục | Giá trị đã chọn | Bằng chứng cần lưu |
|---|---|---|
| JDK | Vendor + phiên bản đầy đủ + build | `java -version`, thuộc tính runtime và nguồn tải |
| CRaC API | `org.crac:crac` + phiên bản | Dependency tree, lockfile và verification metadata |
| Linux | Distro + release + kiến trúc | `/etc/os-release`, `uname -a`, `uname -m` |
| CRIU | Phiên bản chính xác | `criu --version` và log kiểm tra |
| Container | Image tag đầy đủ + digest | Image inspect và cấu hình runtime |
| Checkpoint | Kết quả tạo image | Log checkpoint và vị trí artifact |
| Restore | Kết quả khôi phục và readiness | Log restore, health check và thời gian sẵn sàng |

## 6. Pin container image và công cụ build

### 6.1. Dùng image có phiên bản và digest

Khi nhà cung cấp cung cấp container image CRaC, hãy chọn tag có phiên bản đầy đủ và cố định digest của image đã kiểm tra. Ví dụ cấu trúc khai báo:

```dockerfile
FROM <vendor>/<crac-jdk>:<exact-version>@sha256:<verified-digest>

WORKDIR /app
COPY build/libs/application.jar application.jar

ENTRYPOINT ["java", "-jar", "application.jar"]
```

Đây là mẫu minh họa; thay các placeholder bằng image thực tế từ nhà cung cấp JDK đã chọn. Digest giúp cùng một tham chiếu image trỏ đến cùng nội dung image trong các lần build. Tag có thể được nhà cung cấp cập nhật, vì vậy tag đơn lẻ không cung cấp mức cố định tương đương.

Nếu cần cài CRIU hoặc package hệ thống trong Dockerfile, hãy dùng repository và phiên bản package đã được kiểm soát. Ghi nhận kết quả cài đặt trong image build và xác minh lại bằng `criu --version`. Không cài package không khóa phiên bản trong một bước build mà yêu cầu tái lập chính xác.

### 6.2. Cố định Gradle Wrapper và dependency

Gradle Wrapper giúp mọi máy dùng cùng phiên bản Gradle đã khai báo trong `gradle-wrapper.properties`. Hãy commit wrapper files và kiểm tra URL distribution cùng checksum nếu dự án sử dụng cấu hình xác minh distribution.

Kết hợp ba lớp kiểm soát:

1. **Version Catalog:** tập trung phiên bản dependency trực tiếp như `org.crac:crac`.
2. **Dependency locking:** lưu phiên bản thực tế được Gradle phân giải cho từng configuration.
3. **Dependency verification:** xác minh checksum hoặc chữ ký artifact theo metadata đã duyệt.

Khi build tạo checkpoint image, hãy ghi lại phiên bản Gradle, JDK, dependency tree và digest container. Nhờ đó có thể xác định thay đổi nào đã tạo ra khác biệt giữa hai image.

## 7. Quy trình chọn và chốt bộ môi trường

Có thể thực hiện theo thứ tự sau để tránh chọn các thành phần không tương thích:

**Bước 1 — Chốt mục tiêu triển khai.** Xác định ứng dụng chạy trên Linux nào, kiến trúc CPU nào, dùng container hay máy ảo, và checkpoint/restore được thực hiện ở đâu. Môi trường đích quyết định giới hạn lựa chọn JDK và hệ điều hành.

**Bước 2 — Chọn CRaC-enabled JDK.** Đối chiếu tài liệu nhà cung cấp với OS, kiến trúc và yêu cầu kernel. Ghi vendor, phiên bản đầy đủ, build và nguồn phân phối.

**Bước 3 — Chốt CRaC API.** Xác định JDK/framework đã cung cấp API theo cách nào. Nếu cần dependency `org.crac:crac`, chọn một phiên bản cụ thể được hỗ trợ, khai báo tập trung và kiểm tra dependency tree.

**Bước 4 — Chọn Linux và CRIU.** Chọn bản phân phối cùng kiến trúc được JDK hỗ trợ. Cố định phiên bản CRIU theo hướng dẫn tương thích, sau đó kiểm tra kernel và cấu hình hệ thống trên runner hoặc host đích.

**Bước 5 — Đóng gói runtime.** Dùng container image có phiên bản đầy đủ và digest. Xác định rõ những phần thuộc container image và những phần thuộc host, đặc biệt là kernel, quyền, namespace và cgroup.

**Bước 6 — Khóa công cụ build.** Cố định Gradle Wrapper, dependency lock và verification metadata. Xác minh JDK runtime thực tế trong CI.

**Bước 7 — Chạy thử checkpoint và restore.** Khởi chạy ứng dụng trên đúng môi trường, tạo image, khởi tạo lại từ image và kiểm tra resource callback cùng readiness. Một lần build thành công hoặc một lần khởi động JVM bình thường chưa chứng minh CRaC hoạt động.

**Bước 8 — Lưu ma trận và bằng chứng.** Commit hồ sơ phiên bản, cấu hình build và các lockfile. Lưu log kiểm chứng theo CI build hoặc release để biết bộ môi trường nào đã được chấp nhận.

## 8. Kiểm chứng môi trường bằng một smoke test

Smoke test nên kiểm tra được cả khả năng của nền tảng lẫn hành vi ứng dụng. Một quy trình tối thiểu gồm:

1. In thông tin JDK, vendor, runtime version và kiến trúc.
2. In thông tin Linux, kernel và phiên bản CRIU.
3. Khởi chạy ứng dụng bằng JDK CRaC đã chốt.
4. Xác nhận các `Resource` cần thiết đã được đăng ký.
5. Yêu cầu checkpoint và xác nhận image được tạo thành công.
6. Restore image bằng runtime theo ma trận đã chọn.
7. Xác nhận callback `afterRestore` chạy, các kết nối bắt buộc được tạo lại và readiness chuyển sang thành công.
8. Ghi lại thời gian từ lúc bắt đầu restore đến lúc ứng dụng sẵn sàng.

Ví dụ, ứng dụng có thể ghi log trong hai callback:

```java
public final class ExampleResource implements org.crac.Resource {

    @Override
    public void beforeCheckpoint(
            org.crac.Context<? extends org.crac.Resource> context) {
        System.out.println("Preparing resource before checkpoint");
        // Tạm dừng hoặc đóng tài nguyên theo chính sách của ứng dụng.
    }

    @Override
    public void afterRestore(
            org.crac.Context<? extends org.crac.Resource> context) {
        System.out.println("Restoring resource after checkpoint");
        // Tạo lại hoặc xác thực tài nguyên phụ thuộc môi trường.
    }
}
```

Log giúp nhận biết callback có được gọi trong đúng giai đoạn hay không. Với resource thực tế, cần kiểm tra kết quả phục hồi thay vì chỉ kiểm tra sự xuất hiện của log. Ví dụ, sau restore phải xác nhận database connection có thể thực hiện truy vấn, message consumer đã đăng ký lại và readiness check phản ánh đúng trạng thái.

Smoke test cũng nên được chạy trên đúng kiến trúc và cấu hình container mục tiêu. Nếu production chạy Kubernetes với một security profile cụ thể, kiểm thử chỉ trên laptop hoặc một container có quyền rộng không đủ để xác nhận production tương thích.

## 9. Nâng cấp phiên bản có kiểm soát

JDK, thư viện API, CRIU và bản phân phối Linux đều có thể nhận bản vá bảo mật hoặc thay đổi hỗ trợ. Cố định phiên bản không có nghĩa là giữ mãi một phiên bản cũ; nó có nghĩa là mỗi lần thay đổi đều được xem xét và kiểm chứng.

Khi nâng cấp, hãy thay đổi từng nhóm thành phần có chủ đích và lưu lại ma trận mới. Ví dụ, khi cập nhật JDK patch version, hãy kiểm tra lại tương thích của `org.crac`, framework, native library, CRIU và image restore. Khi cập nhật CRIU hoặc kernel, chạy lại checkpoint/restore trên host có cấu hình tương ứng.

Quy trình nâng cấp nên có các bước:

- Đọc release notes và ma trận hỗ trợ của nhà cung cấp JDK, CRaC API và CRIU.
- Tạo thay đổi phiên bản rõ ràng trong version catalog, lockfile, Dockerfile hoặc hồ sơ môi trường.
- Build lại ứng dụng và tạo checkpoint image mới bằng bộ phiên bản mới.
- Restore image mới trên môi trường mục tiêu và chạy smoke test.
- So sánh thời gian khởi động, restore, readiness và các lỗi tài nguyên với bản đã chấp nhận.
- Chỉ cập nhật bộ phiên bản chuẩn sau khi các kiểm tra bắt buộc thành công.

Không nên dùng checkpoint image được tạo bởi một bộ môi trường cũ như artifact mặc định sau khi nâng JDK, OS hoặc thư viện native. Hãy tạo image mới từ ứng dụng và bộ môi trường mới, trừ khi có tài liệu tương thích và kiểm thử cụ thể chứng minh việc tái sử dụng là hợp lệ.

## 10. Những sai lầm thường gặp

**Chỉ khóa Java major version.** `21` không xác định vendor, patch, build hoặc CRaC capability. Cần lưu phiên bản đầy đủ và xác minh runtime thực tế.

**Nghĩ rằng thêm `org.crac` là đủ.** API Java không thay thế JDK CRaC-enabled, CRIU hoặc khả năng checkpoint/restore của hệ điều hành.

**Dùng dependency version động.** `1.+` hoặc `latest.release` có thể làm build nhận dependency khác mà không có thay đổi được review. Hãy dùng phiên bản cụ thể, lock và xác minh artifact.

**Coi mọi bản Linux là tương đương.** Kernel, kiến trúc, glibc, CRIU, namespace và quyền container đều có thể ảnh hưởng đến restore. Cần ghi rõ bản phân phối và kiểm thử trên nền tảng đích.

**Chỉ pin container tag.** Tag có thể trỏ đến image mới sau này; digest giúp cố định nội dung image. Dù vậy, kernel và một số điều kiện vẫn thuộc host.

**Tạo image trên một kiến trúc rồi restore trên kiến trúc khác.** Không được mặc định `amd64` và `arm64` có thể dùng chung checkpoint image. Hãy xây dựng và kiểm tra riêng từng kiến trúc.

**Chỉ kiểm tra ứng dụng khởi động bình thường.** JVM chạy được không có nghĩa checkpoint/restore hoạt động. Cần tạo image, restore và xác nhận ứng dụng sẵn sàng.

**Nâng cấp một thành phần mà không cập nhật ma trận.** Một thay đổi JDK, CRIU hoặc base image có thể làm bộ môi trường không còn giống bộ đã kiểm thử. Hãy cập nhật hồ sơ và chạy lại smoke test.

## 11. Tự kiểm tra mức độ hiểu

1. **Vì sao ghi “Java 21” chưa đủ để cố định JDK CRaC?** Vì còn thiếu nhà cung cấp, phiên bản patch, build và xác nhận bản JDK đó có hỗ trợ CRaC trên nền tảng mục tiêu.
2. **Thêm `org.crac:crac` có biến JDK thông thường thành CRaC-enabled JDK không?** Không. Dependency cung cấp API Java; khả năng checkpoint/restore cần runtime và nền tảng hỗ trợ.
3. **Vì sao cần khóa phiên bản `org.crac`?** Để mã nguồn và runtime dùng API đã được kiểm chứng, tránh thay đổi dependency ngoài ý muốn giữa các lần build.
4. **Vì sao container digest chưa cố định toàn bộ môi trường CRaC?** Container dùng kernel của host; quyền, namespace, cgroup và một số điều kiện checkpoint/restore nằm ngoài filesystem của image.
5. **Có thể tạo checkpoint image trên `amd64` rồi mặc định restore trên `arm64` không?** Không. Cần tuân theo ma trận tương thích và kiểm thử riêng cho từng kiến trúc.
6. **Điều gì chứng minh môi trường đã được kiểm chứng?** Quy trình thực tế tạo checkpoint image, restore image và xác nhận resource cùng readiness hoạt động trên môi trường mục tiêu.

## Kết luận

Một môi trường CRaC có thể tái lập cần cố định đồng thời JDK CRaC-enabled, API `org.crac`, Linux, CRIU, kiến trúc CPU, container/runtime và công cụ build. Mỗi lựa chọn phải dựa trên tài liệu tương thích của nhà cung cấp và được kiểm tra bằng quy trình checkpoint rồi restore thực tế.

Hãy lưu bộ phiên bản cùng digest, lockfile và bằng chứng smoke test trong repository hoặc hồ sơ phát hành. Khi nâng cấp, tạo một ma trận mới, build image mới và xác nhận restore trên môi trường đích trước khi dùng trong triển khai. Như vậy, nhóm phát triển biết chính xác image được tạo từ bộ môi trường nào và có thể tái tạo kết quả khi cần.
