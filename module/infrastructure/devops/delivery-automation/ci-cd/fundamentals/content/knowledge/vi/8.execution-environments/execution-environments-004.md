# Ghim hệ điều hành, toolchain và phiên bản công cụ

Pipeline CI/CD có thể được lưu nguyên vẹn trong Git nhưng vẫn tạo ra kết quả khác nhau giữa hai lần chạy. Nguyên nhân thường nằm ở môi trường thực thi: runner được cập nhật, image hệ điều hành thay đổi, JDK hoặc compiler khác phiên bản, build tool tự tải bản mới, hay một CLI được cài từ nguồn không cố định.

**Ghim hệ điều hành, toolchain và phiên bản công cụ** là xác định rõ các thành phần của môi trường dùng để build, kiểm thử, đóng gói và triển khai. Mục tiêu là để nhóm biết pipeline chạy ở đâu, dùng công cụ nào, vì sao tạo ra kết quả đó và cách tái tạo môi trường khi cần điều tra.

Nguyên lý này thuộc nền tảng thực thi của CI/CD. Nó hỗ trợ build nhất quán, kiểm thử đáng tin cậy, quản lý artifact có truy vết và phát hành an toàn. Ghim phiên bản không có nghĩa đóng băng môi trường vô thời hạn; các bản vá hệ điều hành và công cụ vẫn cần được cập nhật qua quy trình có kiểm soát.

## 1. Môi trường thực thi gồm những lớp nào?

Một job CI thường chịu ảnh hưởng của nhiều lớp môi trường:

| Lớp | Thành phần ví dụ | Ảnh hưởng đến pipeline |
|---|---|---|
| Runner/host | Máy ảo, máy vật lý, kernel, CPU, filesystem | Quyết định tài nguyên, kiến trúc và một số hành vi hệ thống |
| Hệ điều hành | Ubuntu, Debian, Windows Server, macOS | Cung cấp thư viện hệ thống, shell, package manager và runtime nền |
| Container/executor image | Image chứa JDK, Node.js, scanner hoặc CLI | Xác định root filesystem và nhiều công cụ có sẵn trong job |
| Toolchain | JDK, compiler, linker, SDK, runtime | Quyết định cách mã nguồn được biên dịch hoặc thực thi |
| Build/test tools | Gradle, Maven, npm, pytest, linter, test runner | Quyết định cách resolve dependency, build và kiểm tra |
| Công cụ triển khai | Docker CLI, kubectl, Helm, Terraform, cloud CLI | Ảnh hưởng cách pipeline tương tác với hạ tầng đích |
| Cấu hình hệ thống | Locale, timezone, biến môi trường, chứng chỉ, package repository | Có thể làm thay đổi đầu ra, kết quả test hoặc kết nối |

Không phải mọi job đều sử dụng tất cả các lớp. Job build Java có thể cần JDK, Gradle và container image; job deploy Kubernetes có thể cần kubectl, Helm và credential ngắn hạn. Hãy xác định đầu vào thực tế của từng job thay vì chỉ ghi tên hệ điều hành.

## 2. Phân biệt runner host và môi trường bên trong container

Runner là máy hoặc executor điều phối và thực thi job. Job có thể chạy trực tiếp trên host, trong container hoặc trên một executor chuyên biệt. Hai cách này có ranh giới khác nhau:

- Khi chạy trực tiếp trên host, job sử dụng hệ điều hành và các công cụ đã cài trên runner. Những thay đổi của runner image có thể ảnh hưởng trực tiếp đến kết quả.
- Khi chạy trong container, job sử dụng root filesystem và phần lớn user-space tools của container image. Tuy nhiên container vẫn dùng kernel của host, chịu ảnh hưởng từ runtime/container engine, CPU architecture và cấu hình runner.
- Với máy ảo hoặc runner tự quản lý, nhóm có thể kiểm soát image máy, kernel và công cụ cài sẵn tốt hơn, nhưng phải chịu trách nhiệm cập nhật và bảo trì.

Vì vậy, pin container image không đồng nghĩa đã pin toàn bộ máy thực thi. Ví dụ, cùng một image Linux có thể chạy trên các runner có kernel hoặc phiên bản container runtime khác nhau. Nếu build phụ thuộc vào kernel, filesystem, CPU instruction hoặc driver, những yếu tố đó cũng cần được kiểm soát hoặc ghi nhận.

## 3. Ghim hệ điều hành và runner image

### Chọn phiên bản hệ điều hành có chủ đích

Các nhãn như `ubuntu-latest`, `windows-latest` hoặc `macos-latest` thường có nghĩa là dùng bản được nhà cung cấp xem là mới nhất tại thời điểm chạy. Bản đích có thể thay đổi theo lịch nâng cấp của nền tảng. Điều đó tiện cho việc nhận cập nhật, nhưng làm tăng biến động của môi trường.

Nếu cần ổn định hơn, chọn dòng hệ điều hành cụ thể được nền tảng hỗ trợ, ví dụ `ubuntu-24.04`, rồi xác định cách kiểm soát image thực tế. Nhãn phiên bản hệ điều hành vẫn có thể nhận bản cập nhật package và runner image trong cùng dòng. Nó cố định thế hệ hệ điều hành, không nhất thiết cố định từng package hoặc kernel patch.

Ví dụ GitHub Actions:

```yaml
jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - name: Inspect environment
        run: |
          uname -a
          cat /etc/os-release
```

Đoạn workflow này chọn dòng Ubuntu cụ thể và ghi lại thông tin thực tế. Nó chưa khóa toàn bộ runner image. Nếu cần kiểm soát sâu hơn, dùng runner tự quản lý với image đã version hóa, hoặc chạy job trong container image có digest cố định.

### Dùng image bất biến khi cần kiểm soát user space

Một container image có thể đóng gói hệ điều hành user space, JDK và công cụ cần thiết. Tag giúp người đọc nhận diện phiên bản; digest xác định chính xác nội dung image.

```yaml
jobs:
  build:
    runs-on: ubuntu-24.04
    container:
      image: registry.example.com/ci/java-build:21.0.5@sha256:<IMAGE_DIGEST>
    steps:
      - name: Inspect toolchain
        run: |
          cat /etc/os-release
          java -version
          ./gradlew --version
      - name: Test
        run: ./gradlew clean test
```

`registry.example.com` và `<IMAGE_DIGEST>` là giá trị minh họa. Trong pipeline thật, digest phải lấy từ registry tin cậy và được review cùng thay đổi. Cũng cần bảo đảm image tương thích với runner architecture và có đúng shell, user, chứng chỉ, quyền filesystem mà job yêu cầu.

### Ghim package hệ điều hành

Chỉ pin base image vẫn chưa đủ nếu Dockerfile cài package từ repository có nội dung thay đổi. Ví dụ, lệnh `apt-get install curl` có thể nhận phiên bản khác vào một ngày khác. Để tăng tính ổn định, có thể:

- Dùng repository snapshot hoặc mirror nội bộ có lịch sử và nội dung được quản lý.
- Chỉ định phiên bản package khi hệ điều hành và repository hỗ trợ.
- Ghi nhận danh sách package đã cài và phiên bản thực tế.
- Tạo lại image định kỳ từ base image và package đã cập nhật, sau đó scan và phát hành digest mới.

Không nên giữ một snapshot lỗi thời vô thời hạn. Snapshot giúp tái tạo đầu vào; quy trình cập nhật bảo mật phải đưa bản vá mới vào snapshot hoặc image đã được kiểm tra.

## 4. Ghim toolchain: JDK, compiler và runtime

Toolchain quyết định cách mã nguồn được biên dịch và thực thi. Với dự án Java, cần xem xét ít nhất:

- Phiên bản JDK dùng để chạy Gradle hoặc Maven.
- Phiên bản compiler và Java language level của source code.
- Vendor hoặc distribution của JDK khi có khác biệt cần kiểm soát.
- Phiên bản runtime dùng khi chạy test hoặc ứng dụng.
- Native toolchain như C/C++ compiler, linker và hệ thống build nếu có JNI hoặc native image.

Khai báo Java toolchain trong Gradle giúp dự án nói rõ major version cần dùng:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Cấu hình này yêu cầu Java 21, nhưng không nhất thiết khóa patch release hoặc vendor cụ thể. Gradle có thể tìm một JDK phù hợp đã cài trên máy hoặc tự provision nếu được cấu hình. Nếu cần kiểm soát patch và vendor, hãy quản lý JDK trong runner/container image hoặc dùng cơ chế cài đặt toolchain với phiên bản cụ thể, rồi ghi nhận kết quả bằng `java -version`.

Ví dụ cài JDK qua action cần pin chính action và chỉ định version của JDK:

```yaml
steps:
  - name: Set up Java
    uses: actions/setup-java@<FULL_COMMIT_SHA>
    with:
      distribution: temurin
      java-version: '21.0.5+11'
```

`<FULL_COMMIT_SHA>` là placeholder phải thay bằng commit SHA đã xác minh. Cấu hình này kiểm soát action và yêu cầu phiên bản JDK cụ thể theo cách action hỗ trợ; runner vẫn là một lớp môi trường riêng cần xem xét.

## 5. Ghim build tool và package manager

Build tool cũng là đầu vào của pipeline. Dùng lệnh cài phiên bản mới nhất hoặc phụ thuộc phiên bản có sẵn trên runner có thể khiến cùng repository tạo kết quả khác nhau.

### Gradle Wrapper

Gradle Wrapper giúp repository chỉ định phiên bản Gradle cần sử dụng thay vì dùng Gradle cài toàn cục trên runner. Trong `gradle/wrapper/gradle-wrapper.properties`, ví dụ:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
distributionSha256Sum=<GRADLE_DISTRIBUTION_SHA256>
```

Giá trị checksum là placeholder; cần lấy checksum chính thức tương ứng với đúng distribution. `distributionSha256Sum` cho phép Wrapper xác minh nội dung file tải về. Nên review cả `gradlew`, `gradlew.bat` và các file wrapper JAR theo quy trình bảo vệ repository.

### Maven Wrapper

Maven Wrapper cung cấp cách tương tự để cố định Maven distribution. Ví dụ trong `.mvn/wrapper/maven-wrapper.properties`:

```properties
distributionUrl=https\://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
distributionSha256Sum=<MAVEN_DISTRIBUTION_SHA256>
```

Checksum cũng cần lấy và xác minh theo đúng distribution. Không nên tải script wrapper hoặc binary từ nguồn không rõ ràng trong lúc pipeline chạy.

### Node.js, Python và package manager

Với các hệ sinh thái khác, có thể quản lý phiên bản bằng file cấu hình được commit cùng repository, chẳng hạn `.nvmrc`, `.python-version`, `.tool-versions` hoặc `mise.toml`. Các file này cần chứa phiên bản cụ thể theo chính sách của dự án. Lockfile như `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock` hoặc lockfile Python giúp cố định dependency đã giải quyết.

Lockfile không thay thế việc pin runtime và package manager. Cần kiểm soát cả phiên bản Node.js/Python, npm/pnpm/Poetry/uv và cách chúng được cài đặt. Pipeline nên dùng chế độ cài đặt tôn trọng lockfile, ví dụ `npm ci`, thay vì tự giải quyết lại dependency mà không cập nhật lockfile.

## 6. Ghim các CLI và công cụ phụ trợ

Job triển khai và kiểm tra thường tải thêm các công cụ như Docker CLI, kubectl, Helm, Terraform, cloud CLI, scanner hoặc linter. Nếu pipeline dùng script tải bản mới nhất hoặc package manager không khóa version, thay đổi công cụ có thể làm hành vi deploy hoặc scan khác đi.

Một số quy tắc thực hành:

- Chỉ định phiên bản cụ thể khi cài CLI; tránh `curl ... | sh` từ URL trỏ đến bản mới nhất mà không xác minh nội dung.
- Ưu tiên package repository hoặc release chính thức; xác minh checksum hoặc chữ ký khi nhà phát hành cung cấp.
- Dùng image công cụ đã được kiểm tra và tham chiếu bằng digest nếu có thể.
- Ghi lại phiên bản CLI trong log để phục vụ điều tra.
- Tách phiên bản CLI khỏi phiên bản API hoặc server mà CLI kết nối; pin client không đảm bảo server có cùng phiên bản.

Ví dụ một job có thể ghi lại các phiên bản trước khi deploy:

```bash
docker version --format '{{.Client.Version}}'
kubectl version --client
helm version --short
terraform version
```

Lệnh cụ thể có thể khác theo phiên bản công cụ. Nếu CLI không hỗ trợ in version theo cú pháp trên, dùng lệnh version chính thức của công cụ.

## 7. Kiểm soát kiến trúc CPU, locale và timezone

Hai runner có cùng tên hệ điều hành và toolchain vẫn có thể khác nhau ở kiến trúc hoặc cấu hình hệ thống. Những khác biệt này đặc biệt quan trọng với native binary, image đa kiến trúc, xử lý ngày giờ và test chuỗi.

**Kiến trúc CPU:** ghi nhận `x86_64`/`amd64` hay `aarch64`/`arm64`. Nếu build image đa kiến trúc, xác định rõ platform cần tạo và kiểm tra manifest list cùng digest. Native dependency hoặc compiler có thể tạo binary riêng theo kiến trúc.

**Locale và encoding:** đặt locale nhất quán, thường dùng UTF-8, để tránh test phụ thuộc cách sắp xếp, định dạng số hoặc xử lý ký tự theo máy chạy. Nếu ứng dụng cần locale cụ thể, cấu hình rõ trong job và test tương ứng.

**Timezone:** dùng UTC cho log, timestamp và test cần tính nhất quán nếu phù hợp với nghiệp vụ. Các test lịch, giờ mùa hè hoặc quy tắc múi giờ địa phương cần dữ liệu timezone và múi giờ được khai báo rõ.

Ví dụ:

```yaml
env:
  LANG: C.UTF-8
  LC_ALL: C.UTF-8
  TZ: UTC
```

Đây là cấu hình tham khảo; cần kiểm tra locale có tồn tại trong image đang dùng và không ghi đè yêu cầu hợp lệ của ứng dụng.

## 8. Tạo môi trường thực thi dùng chung và có truy vết

Với nhiều repository, việc lặp lại cấu hình runner trong từng pipeline dễ tạo ra khác biệt. Nhóm có thể xây dựng image CI chuẩn hoặc template môi trường dùng chung. Một image CI thường chứa:

- Một dòng hệ điều hành đã chọn và package hệ thống cần thiết.
- JDK hoặc runtime theo phiên bản đã kiểm tra.
- Build tool hoặc wrapper prerequisites.
- CLI và scanner cần thiết cho nhóm job cụ thể.
- CA certificates, timezone data, locale và user không đặc quyền.
- Metadata về image version, commit tạo image và danh sách package.

Không nên tạo một image khổng lồ chứa mọi công cụ cho tất cả pipeline. Có thể duy trì một số image theo vai trò như `java-build`, `container-build`, `security-scan` và `deployment`. Điều này giúp giảm bề mặt tấn công và chỉ cập nhật các thành phần liên quan.

Ví dụ Dockerfile minh họa:

```dockerfile
FROM eclipse-temurin:21.0.5_11-jdk-jammy@sha256:<BASE_IMAGE_DIGEST>

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
```

Đây là ví dụ khung, chưa phải Dockerfile production hoàn chỉnh: cần thay digest hợp lệ, quản lý package version hoặc snapshot repository theo chính sách và đánh giá user/quyền chạy. `apt-get update` với repository di động vẫn có thể nhận package khác ở lần build sau; muốn tái lập chặt chẽ cần kiểm soát nguồn package.

Sau khi build image CI, lưu image vào registry, tạo digest, scan và ghi metadata. Pipeline tiêu thụ image bằng digest. Khi cập nhật JDK hoặc package hệ điều hành, tạo image mới với digest mới rồi chạy kiểm tra trước khi thay ref.

## 9. Ghi nhận môi trường thực tế trong mỗi lần chạy

Khai báo version trong file pipeline cho biết điều nhóm mong muốn. Để điều tra, còn cần ghi nhận điều thực sự được sử dụng. Một bước diagnostics có thể lưu:

- OS name, version, kernel và architecture.
- Runner image hoặc container image reference và digest.
- Phiên bản JDK, compiler, Gradle/Maven và package manager.
- Phiên bản CLI quan trọng như Docker, kubectl hoặc scanner.
- Commit SHA, lockfile fingerprint và image digest của artifact đầu ra.
- Locale, timezone và các biến môi trường có ảnh hưởng đến build.

Ví dụ bước diagnostics cho job Java:

```bash
cat /etc/os-release || true
uname -a
java -version
./gradlew --version
locale
date -u
```

Đối với Windows hoặc macOS, dùng lệnh tương ứng để thu thập OS và toolchain. Chỉ lưu biến môi trường không nhạy cảm; không in toàn bộ environment vì có thể làm lộ token, password hoặc thông tin xác thực.

Thông tin môi trường nên gắn với pipeline run và artifact. Khi một lần build thất bại sau khi runner image được cập nhật, nhóm có thể so sánh metadata giữa lần chạy tốt và lần chạy lỗi thay vì chỉ nhìn vào commit nguồn.

## 10. Cập nhật phiên bản và xử lý bản vá bảo mật

Ghim một phiên bản giúp môi trường ổn định, nhưng giữ mãi phiên bản cũ sẽ làm tăng rủi ro bảo mật và mất hỗ trợ. Cần có chu kỳ cập nhật rõ ràng:

1. **Kiểm kê:** liệt kê OS image, runner, JDK, build tool, package manager và CLI đang dùng.
2. **Theo dõi:** nhận thông báo vòng đời hỗ trợ, bản vá bảo mật và thay đổi của nhà cung cấp runner.
3. **Đánh giá:** đọc release notes, advisory, breaking changes và yêu cầu tương thích.
4. **Cập nhật có kiểm soát:** thay version hoặc digest trong pull request; tránh sửa trực tiếp trên runner production mà không ghi nhận.
5. **Xác minh:** chạy build, test, scan và kiểm tra artifact trên môi trường mới.
6. **Triển khai dần:** thử trên một nhóm pipeline hoặc runner trước khi mở rộng.
7. **Quay lui:** giữ image/ref trước đó trong thời gian phù hợp và biết cách chuyển lại khi bản mới gây lỗi.

Với lỗ hổng nghiêm trọng, ưu tiên bản vá theo SLA bảo mật. Có thể dùng quy trình cập nhật khẩn cấp nhưng vẫn phải xác minh nguồn, checksum/chữ ký, kiểm tra tương thích và lưu vết quyết định.

## 11. Những giới hạn cần hiểu khi pin môi trường

Pin OS và toolchain giúp giảm biến động, nhưng không tự bảo đảm build hoàn toàn tái lập:

- Hosted runner có thể thay đổi phần host mà pipeline không kiểm soát trực tiếp.
- Container chia sẻ kernel của host; pin image không pin kernel.
- Package repository có thể thay đổi nếu không dùng snapshot hoặc mirror bất biến.
- Tool có thể gọi dịch vụ từ xa, tải schema hoặc rule database mới trong lúc chạy.
- Timestamp, random seed, thứ tự file, CPU behavior hoặc dữ liệu bên ngoài có thể làm đầu ra khác nhau.
- Một image digest cố định có thể chứa lỗ hổng; pinning không thay thế scan và cập nhật.

Hãy xác định mức kiểm soát cần thiết theo rủi ro và mục tiêu. Với job thông thường, chọn dòng OS cụ thể, dùng wrapper/lockfile và ghi lại version thực tế có thể đủ. Với build cần tái lập hoặc pipeline phát hành quan trọng, cân nhắc runner ephemeral từ image được quản lý, container theo digest, package snapshot, toolchain cố định và provenance đầy đủ.

## 12. Checklist ghim môi trường thực thi

- [ ] Chọn rõ runner OS/version; hiểu nhãn hosted runner có thể được cập nhật đến mức nào.
- [ ] Phân biệt runner host với container/executor image và ghi nhận giới hạn của từng lớp.
- [ ] Pin container image bằng digest khi cần cố định user space.
- [ ] Kiểm soát package repository, package version hoặc snapshot nếu build cần tái lập.
- [ ] Chỉ định JDK/compiler/runtime và ghi nhận version thực tế.
- [ ] Dùng Gradle/Maven Wrapper và xác minh checksum distribution.
- [ ] Ghim package manager, dependency bằng lockfile và integrity hash khi hỗ trợ.
- [ ] Pin phiên bản CLI quan trọng và xác minh nguồn tải.
- [ ] Kiểm soát architecture, locale, encoding và timezone khi chúng ảnh hưởng kết quả.
- [ ] Lưu diagnostics không chứa bí mật cùng pipeline run và artifact.
- [ ] Có quy trình cập nhật bản vá, kiểm thử, rollout và rollback cho image/toolchain.

Khi hệ điều hành, toolchain và công cụ được khai báo rõ, kiểm tra nguồn gốc và cập nhật qua review, môi trường thực thi trở thành một phần có thể truy vết của pipeline. Nhóm có thể giải thích khác biệt giữa các lần chạy, tái tạo lỗi chính xác hơn và đưa bản vá vào sử dụng mà vẫn kiểm soát được chất lượng CI/CD.
