# Build mã từ nguồn chưa tin cậy trong môi trường có quyền hạn phù hợp

> **Ngữ cảnh:** An toàn phụ thuộc — Build Tool Maven. Bài học hướng dẫn xây dựng và kiểm tra một dự án Maven đến từ pull request, fork, archive tải về hoặc một dependency/parent POM chưa được thẩm định mà **không trao cho mã đó quyền của tài khoản phát hành, máy developer hay hạ tầng nội bộ**.

## 1. Hiểu đúng mô hình bảo mật của Maven

Maven là hệ thống **thực thi build**, không chỉ là bộ đọc cấu hình XML. Maven đọc POM, parent POM, profiles, build extensions, resolves plugins/dependencies và chạy các goals trong lifecycle. Những thành phần đó có thể thực thi mã với **quyền của tiến trình Maven**.

Tài liệu bảo mật Apache Maven nêu rõ rằng Maven giả định bạn tin tưởng `pom.xml`, mã nguồn, dependencies, plugins và repositories được dùng trong build; muốn build mã chưa tin cậy, **người vận hành phải cung cấp lớp cô lập phù hợp**.

Vì vậy, quy tắc căn bản:

**Hãy xem `mvn clean verify` trên một repository chưa tin cậy như việc chạy chương trình của người khác, không phải như việc mở một file văn bản.**

Một dự án Java có thể chứa code hợp pháp, nhưng thay đổi độc hại có thể ẩn ở POM, test, plugin, annotation processor, build extension, Maven Wrapper hoặc một dependency. Không cần có method tên `main` để thực thi mã ngoài ý muốn.

### Mục tiêu bảo vệ

- **Confidentiality:** mã chưa tin cậy không đọc được token, mật khẩu, SSH keys, Maven `settings.xml` có secrets, source của repository khác, cloud credentials, metadata credentials hoặc dữ liệu nội bộ.
- **Integrity:** mã đó không push Git, ghi đè Maven repository, làm nhiễm shared cache, sửa output của job khác, sửa host filesystem hoặc mở quyền truy cập ngoài dự kiến.
- **Availability:** không thể tiêu thụ không giới hạn CPU, RAM, số process, dung lượng disk hoặc thời gian của runner/host.
- **Traceability:** biết Git commit/checksum nào được build, với Maven/JDK/image nào, reports nào được tạo và artifact nào đủ điều kiện đi tới giai đoạn đáng tin hơn.

Không có một flag Maven duy nhất cung cấp cả bốn. Cần thiết kế **trust boundary** bằng cách kết hợp tách quyền CI, môi trường ephemeral, network controls, filesystem permissions, limits và chính sách tiếp nhận artifacts.

## 2. Nguồn chưa tin cậy là những gì?

“Chưa tin cậy” không chỉ có nghĩa code của hacker. Đó là mọi input **chưa đi qua chính sách đánh giá và phê duyệt của bạn**.

Ví dụ:

1. Pull request từ fork hoặc contributor chưa được cấp quyền trong repository.
2. Source archive được tải từ website, email hoặc ticket.
3. Repository Git bên thứ ba dùng làm template/example.
4. PR do nội bộ tạo nhưng thay đổi `pom.xml`, `.mvn` hoặc CI workflow chưa được review.
5. Dependency/parent POM/plugin có provenance chưa xác minh hoặc đang lấy từ repository mới.
6. Build script và test code do bot/AI tạo mà chưa được người có trách nhiệm rà soát.
7. Artifact, test report, coverage report, cache được chuyển từ một workflow không đáng tin sang workflow có secrets.
8. Một project từng an toàn nhưng cho phép dependency/plugin SNAPSHOT hoặc dynamic version tự cập nhật.

**Lưu ý:** việc một contributor đã được mời vào tổ chức hoặc dependency nằm ở repository nổi tiếng **không tự chứng minh mọi version và mọi mã trong nó đều an toàn**. Độ tin cậy phải gắn với identity, commit/version, nội dung và quy trình kiểm duyệt.

## 3. Maven thực thi mã ở những điểm nào?

| Bề mặt | Khi nào có thể hoạt động | Rủi ro cần xét |
| --- | --- | --- |
| `pom.xml` và POM parent | Khi Maven dựng model/build plan | Chọn plugins, executions, profiles, repositories, dependencies và mục tiêu thực thi |
| `.mvn/extensions.xml` | Khi Maven khởi tạo core extensions | Extension có thể được tải/khởi chạy **trước** nhiều goals thông thường |
| `.mvn/maven.config`, `.mvn/jvm.config` | Khi Maven launcher/JVM đọc cấu hình | Có thể thay tham số, repo, JVM options; xem kỹ cấu hình từ source |
| `mvnw`, `mvnw.cmd`, Maven Wrapper assets | Khi chạy `./mvnw`/`mvnw.cmd` | Đây là launcher/script từ source; có thể chạy code trước Maven |
| Build plugins: `exec`, `antrun`, custom Mojo, generator | Các phases/goals đã bind hoặc gọi trực tiếp | Có thể chạy process, ghi file, mở network, gọi command tùy plugin |
| Annotation processors/compiler plugins | Phase `compile`/`test-compile` | Processor Java có thể thực thi trong quá trình biên dịch |
| Unit/integration tests | Surefire ở `test`, Failsafe ở `integration-test`/`verify` | Tests là **mã chương trình**, không phải dữ liệu vô hại |
| Build extensions, custom lifecycle packaging | Từ build model và Maven runtime | Thay đổi hành vi build/lifecycle, có thể có quyền rộng |
| Dependencies và test libraries | Khi plugin/framework/test/app load hoặc chạy classes | Bytecode bên thứ ba có thể thực thi khi được sử dụng |
| Report/scan plugins | Khi gọi một goal như `site`, `dependency:tree` hoặc `help:*` | Scanner/reporting goal vẫn là một plugin chạy trong môi trường có quyền |
| Git hooks, native tools, shell scripts | Khi workflow dùng các lệnh bên ngoài Maven | Có thể thực thi nội dung ngoài `src/main/java` |

**Phân biệt cho chính xác:** download một file JAR dependency **không tự làm mọi class của JAR đó được chạy**. Rủi ro xuất hiện khi JAR/plugin/extension/processor/test được load hoặc có luồng thực thi khác sử dụng nó. Nhưng vì Maven có nhiều điểm load và thực thi, không nên coi một build thông thường là phép kiểm an toàn đối với project chưa tin cậy.

### Vì sao `mvn validate` chưa hẳn “an toàn để thăm dò”?

Phase `validate` có thể đã có plugin execution được bind. Core extensions có thể được nạp trước khi lifecycle chạy. Ngay cả lệnh như:

```bash
mvn validate
mvn help:effective-pom
mvn dependency:tree
```

cũng phải được thực hiện **sau khi thiết lập trust boundary** với một repository thực sự chưa tin cậy. Đừng chạy chúng trên laptop có toàn quyền Git/SSH/cloud chỉ vì nghe có vẻ “read-only”.

### Tại sao `-DskipTests` không biến build thành an toàn?

```bash
mvn -DskipTests clean package
mvn -Dmaven.test.skip=true package
```

Cờ skip có thể bỏ chạy test hoặc cả compile test sources tùy plugin; chúng **không vô hiệu hóa toàn bộ build plugins, extensions, Java compiler/annotation processors hoặc execution ở lifecycle phases khác**.

Tương tự, `mvn -o` (offline) giới hạn **Maven artifact resolution**, nhưng **không phải firewall cho arbitrary plugin/test code**. Muốn chặn network egress, cần kiểm soát ở container/VM/network policy.

## 4. Threat model: mã chưa tin cậy sẽ làm gì nếu có quyền?

Hãy giả định một PR có thể thay `pom.xml` hoặc file test. Nếu job chạy bằng tài khoản có quyền rộng, mã được thực thi trong build có thể:

- Đọc `~/.m2/settings.xml` và credentials đã cấu hình.
- Đọc `~/.ssh/id_*`, SSH agent socket, `~/.git-credentials` hoặc Git remote URL chứa token.
- Đọc environment variables chứa repository token, cloud access keys, signing keys.
- Dùng `GITHUB_TOKEN` hoặc CI token có quyền write để push branch/tag hoặc sửa workflow.
- Kết nối tới network nội bộ, dịch vụ chỉ runner truy cập được hoặc cloud metadata endpoint.
- Ghi đè thư mục source/outputs của jobs khác nếu filesystem mount có quyền ghi.
- Nhiễm shared Maven local repository hoặc CI caches được trusted job tái sử dụng.
- Tạo quá nhiều processes, threads, file descriptors, logs hoặc dữ liệu để làm cạn resources.
- Gắn mã độc vào JAR/ZIP hoặc artifacts mà downstream job lầm tưởng là đáng tin.

**Không cần mô phỏng hành vi tấn công để hiểu bài.** Đây là lý do chính sách phải loại bỏ quyền từ **môi trường** thay vì chỉ cố tìm “dòng Java độc hại”.

## 5. Phân tách ba mức tin cậy trong CI

| Mức | Đối tượng | Quyền nên cấp |
| --- | --- | --- |
| **Untrusted build** | PR/fork/third-party source chưa review | Read-only source, ephemeral workspace, không có publisher secrets, không có Git write, network bị chặn hoặc chỉ đi tới nguồn allowlist; CPU/RAM/time limits |
| **Trusted verification/review** | Code và reports đã qua bước nhận dạng, reviewer/automation được kiểm soát | Quyền đọc source, kiểm tra outputs/report như **dữ liệu**, có thể truy cập hệ thống kiểm tra nội bộ nếu cần và theo whitelist |
| **Privileged release/deploy** | Commit/tag đã approved và provenance đã xác nhận | Short-lived credentials có phạm vi tối thiểu để publish artifacts/deploy; phải kiểm tra trust boundary trước khi nhận input từ job thấp quyền |

**Luồng đúng:**

```text
Untrusted commit / fork PR
          |
          v
  Low-privilege checkout
          |
          v
  Disposable isolated sandbox
  - no secrets
  - no host mounts except reviewed read-only source
  - no privileged token
  - restricted/no network
  - CPU/memory/process/time bounds
          |
          v
  Test results + candidate artifacts (UNTRUSTED DATA)
          |
          v
  Scan / verify / review / approval
          |
          v
  Trusted rebuild from approved commit
          |
          v
  Publish with scoped credentials
```

Một báo cáo `BUILD SUCCESS` ở tầng untrusted **chỉ cho biết code chạy và tests đã hoàn thành trong sandbox**, không tự nâng độ tin cậy của artifact hoặc biến PR thành release-ready.

## 6. Nguyên tắc quyền tối thiểu

### 6.1. Không cung cấp secret ngay từ đầu

Khi thực thi mã chưa tin cậy, loại khỏi environment:

- `GITHUB_TOKEN` có quyền write, PAT, GitHub App private key, GitLab CI job token có quyền nhạy cảm.
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, cloud provider token.
- SSH private keys, `SSH_AUTH_SOCK`, host SSH agent socket.
- `MAVEN_OPTS`/`JAVA_TOOL_OPTIONS` có chứa secrets hoặc đường dẫn credentials.
- `~/.m2/settings.xml` có username/password/token, `settings-security.xml` có secret encryption material.
- Docker/Kubernetes client contexts, `/var/run/docker.sock` và Kubernetes service-account tokens.
- Files trong home của developer hoặc directories chứa các repos khác.

**Ngay cả token read-only cũng có giá trị cần bảo vệ.** Nếu thực sự phải fetch private source, nên làm ở bước checkout được kiểm soát trước, rồi **đưa một source export đã được rà soát, không có .git/credentials**, vào sandbox.

### 6.2. Non-root và không nâng quyền

- Chạy process bằng user ID không phải root (Linux UID/GID không đặc quyền).
- Không sử dụng `--privileged`.
- Drop Linux capabilities không cần thiết.
- Chặn privilege escalation bằng `no-new-privileges`.
- Giữ seccomp/AppArmor/SELinux security profiles thích hợp; không tắt vì build gặp lỗi mà chưa điều tra.
- Không chia sẻ host process/pid/net namespace, devices hoặc Docker daemon socket.

### 6.3. File system tối thiểu

- Mount source **read-only**, hoặc copy từ source export read-only vào sandbox scratch.
- Workspace writable chỉ tồn tại bên trong VM/container tạm.
- Root filesystem read-only khi runtime hỗ trợ.
- Maven local repository **riêng từng run**, không cho mã chưa tin cậy ghi vào cache/trusted home dùng cho các jobs khác.
- Giới hạn disk/temp size; tránh symlink/hardlink escape khi thu thập output.
- Không mount `/`, `$HOME`, `~/.m2`, `~/.ssh`, `/etc`, cloud metadata secrets hay source repos khác từ host.

### 6.4. Network

- Tốt nhất cho phép thử đầu: **no network** sau khi Maven dependencies/plugins đã được chuẩn bị bằng quy trình đáng tin.
- Nếu cần mạng: allowlist chính xác repository proxy/hosts, không cho outbound Internet tùy ý hay internal control plane.
- Chặn metadata service, link-local/internal endpoints; DNS egress cũng cần kiểm soát.
- Với remote repository, pin trust/TLS, quản lý mirrors qua settings **không chứa secrets trong sandbox**, scan/vet packages/plugin inputs.
- Network “có proxy” không tự là sandbox; code có thể gửi dữ liệu qua một endpoint proxy được cho phép nếu không có kiểm soát nội dung/chính sách.

### 6.5. Giới hạn tài nguyên và thời gian

- CPU và RAM quota.
- `pids-limit`/thread/process limits.
- Disk/temp quotas.
- Job timeout và cancel policy.
- Logging/output size limit.
- Ngân sách cho dependencies download và concurrent builds.

Không tin mã thử nghiệm sẽ tự kết thúc đúng hạn. Một vòng lặp vô hạn hoặc fork bomb có thể làm hỏng runner nếu không giới hạn resource.

## 7. Docker là công cụ hỗ trợ, không phải “bảo đảm an toàn tuyệt đối”

Docker có các lựa chọn hữu ích như:

- `--network none`: container không có kết nối network ngoài sandbox trong cấu hình thông thường.
- `--read-only`: root filesystem của container ở chế độ read-only.
- `--cap-drop ALL`: loại các Linux capabilities được cấp mặc định.
- `--security-opt no-new-privileges`: ngăn tiến trình nhận thêm privileges.
- `--user UID:GID`: không chạy với UID 0.
- `--pids-limit`, `--memory`, `--cpus`: đặt trần tài nguyên.
- `--tmpfs`: tạo vùng ghi tạm, mất khi container bị hủy.
- `--mount type=bind,...,readonly`: chỉ cho đọc một thư mục host đã duyệt.

**Quan trọng:** container dùng kernel của host; cấu hình Docker không thể loại trừ mọi lỗi kernel/runtime. Với mã rủi ro cao hoặc host có dữ liệu quan trọng, dùng **ephemeral VM/microVM** hoặc sandbox bổ sung như gVisor/Kata (nếu được tổ chức hỗ trợ), và vận hành trên runner không chia sẻ secrets/production network.

### Điều không bao giờ làm chỉ để build PR

```bash
# PHẢN VÍ DỤ — KHÔNG CHẠY với mã chưa tin cậy:
docker run --privileged -v /var/run/docker.sock:/var/run/docker.sock ...
docker run -v "$HOME:/home/host-user" ...
docker run --network host ...
```

Đây là fragment minh họa **thiết lập nguy hiểm**, không phải command hoàn chỉnh. Docker socket cho phép thao tác với host Docker daemon; nếu daemon đặc quyền, hậu quả có thể tương đương host control. `--privileged` loại bỏ nhiều lớp cô lập. Bind-mount toàn bộ home sẽ phơi bày secrets ngay cả khi mount read-only.

## 8. Một quy trình build offline trong sandbox có quyền tối thiểu

Đây là **mẫu cho môi trường Linux** có Docker Engine được quản trị và source export không chứa credentials. Nó trình bày các lớp phòng vệ thực tế, **không yêu cầu bạn đưa Docker socket vào sandbox**.

### 8.1. Các điều kiện bắt buộc trước khi chạy

Một người/vòng CI đáng tin cần chuẩn bị **bên ngoài** sandbox:

1. Một **source export sạch**, ví dụ `/srv/quarantine/untrusted-source`, chỉ chứa source cần build (không có `.git` chứa remote URL/token, không có `.ssh`, settings, secrets, archive chưa kiểm tra).
2. Một Maven local repository **đã vet và chỉ chứa artifacts/plugins công khai được phép**, ví dụ `/srv/cache/maven-public-vetted`. Bao gồm dependencies/plugins/transitive artifacts cần cho `mvn clean verify`.
3. Docker Maven image `maven:3.9.16-eclipse-temurin-17` đã được provision bởi bộ phận đáng tin. Trong production, **pin image bằng immutable digest** đã xác minh thay vì chỉ dùng tag di động.
4. Các paths trên được tạo ở runner chuyên dụng, không trỏ tới home hay directory chứa tài sản của team khác.
5. Runner/daemon/container runtime đã được patch/hardened, phù hợp độ rủi ro. Nếu quy định tổ chức yêu cầu VM riêng, không thay VM bằng container chỉ vì ví dụ ngắn.
6. Nguồn đã được kiểm tra về symlinks/traversal và những file nhạy cảm; source export là dữ liệu không tin cậy nhưng không vô tình chứa secrets sẵn.

**Không dùng một lệnh Maven trong privileged host để “chuẩn bị cache nhanh” từ project chưa tin cậy.** Dependency prefetch cũng có thể load build extensions/plugins. Seed cache phải được xây dựng bởi pipeline đáng tin riêng, với policy repository/provenance, hoặc trong sandbox giai đoạn có network restricted và sau đó chuyển sang offline.

### 8.2. Lệnh minh họa

```bash
docker run --rm \
  --pull never \
  --network none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 128 \
  --memory 1g \
  --cpus 2 \
  --user 10001:10001 \
  --tmpfs /work:rw,nosuid,nodev,size=512m,mode=1777 \
  --tmpfs /tmp:rw,nosuid,nodev,size=512m,mode=1777 \
  --mount type=bind,src=/srv/quarantine/untrusted-source,dst=/src,readonly \
  --mount type=bind,src=/srv/cache/maven-public-vetted,dst=/seed,readonly \
  -e HOME=/tmp \
  -e MAVEN_CONFIG=/tmp/.m2 \
  --workdir /work \
  --entrypoint /bin/sh \
  maven:3.9.16-eclipse-temurin-17 \
  -c '
    set -eu
    cp -R /src/. /work/
    mkdir -p /tmp/m2
    cp -R /seed/. /tmp/m2/
    printf "<settings xmlns=\"http://maven.apache.org/SETTINGS/1.2.0\"/>\n" > /tmp/settings.xml
    mvn -o -B -ntp \
      -s /tmp/settings.xml \
      -Duser.home=/tmp \
      -Dmaven.repo.local=/tmp/m2 \
      clean verify
    java -jar target/untrusted-build-lab-1.0.0.jar
  '
```

**Đây là lệnh có điều kiện, không phải cách chạy một project bất kỳ mà không cần chuẩn bị.** Nó giả định image, source export và vetted cache **đã tồn tại**; nếu thiếu dependency/plugin, `mvn -o` sẽ fail, và **đó là hành vi an toàn hơn tự bật Internet hoặc gắn credential vào container**.

### 8.3. Giải thích từng ranh giới

- `--pull never` không tự kéo image trong bước untrusted. Admin đã chuẩn bị image trước. Để production tái lập/chống thay image, dùng digest immutable đã được kiểm chứng.
- `--network none` chặn outbound network của container; `mvn -o` bổ sung cơ chế Maven offline artifact resolution. Hai biện pháp **bổ trợ, không thay thế nhau**.
- `--read-only` giữ image root filesystem không ghi được; chỉ `/work` và `/tmp` là tmpfs writable.
- `mode=1777` ở tmpfs cho non-root UID có quyền tạo file trong hai vùng scratch; không đặt chúng thành host bind mounts.
- `--user 10001:10001` loại việc chạy Maven dưới root.
- `--cap-drop ALL` và `no-new-privileges` giảm khả năng làm thao tác đặc quyền.
- `--pids-limit`, `--memory`, `--cpus` giảm tác động resource exhaustion; vẫn cần **CI timeout** bên ngoài container.
- `/src` được bind read-only từ source export. `cp -R` đưa nó vào `/work` scratch để Maven có thể tạo `target`.
- `/seed` là vetted cache read-only từ host, **không phải shared writable Maven cache**. Code chưa tin cậy chỉ được sửa bản copy `/tmp/m2` và bản copy này mất đi khi container kết thúc.
- `-s /tmp/settings.xml` sử dụng settings không có `<servers>`/credentials trong ví dụ. Global Maven settings của image cũng phải được admin kiểm tra.
- `--entrypoint /bin/sh` dùng launcher của image, **không chạy `./mvnw` từ source**. Tuy vậy Maven có thể đọc `.mvn/extensions.xml`/POM trong sandbox — đó chính là lý do sandbox tồn tại.
- `java -jar` chạy **artifact vừa được package** trong cùng môi trường sandbox, không đưa nó lên host.
- `--rm` xóa container khi thoát; build outputs trong tmpfs biến mất. Nếu cần lưu, phải có quy trình **export/quarantine** riêng (mục 15).

### 8.4. Không nhầm stdout với giấy chứng nhận an toàn

Nếu source demo ở mục 10 được build thành công, chương trình in:

```text
SANDBOX_OK=5
```

Một repository chưa tin cậy khác có thể in bất kỳ nội dung nào, thay POM, chạy test code hoặc đưa nội dung tùy ý vào log. Không lấy stdout/`BUILD SUCCESS` làm bằng chứng không có malicious behavior.

### 8.5. Giới hạn của lệnh Docker này

- Chỉ dành cho **Linux Docker host** đã harden; cú pháp/mounts khác trên Windows/macOS Docker Desktop.
- Cần đủ Maven dependencies/plugins trong `/seed`. Offline Maven có thể đòi metadata/plugins mà prefetch thiếu; **không tự sửa bằng cách cho internet toàn quyền**.
- Với project có database, Docker-in-Docker, browser hoặc native tools, build có thể fail do sandbox policy. **Không mở thêm host mounts/privileges vô tội vạ** để làm xanh.
- Container không được coi là strong security boundary chống mọi kernel/runtime escape. Với mã thực sự nguy hiểm, chọn VM/microVM và policy nghiêm hơn.
- Nếu build cần nhiều hơn 512 MiB scratch, chính sách quotas phải được đánh giá/điều chỉnh bởi người có thẩm quyền; không tắt giới hạn chỉ vì timeout.
- Output không tự thoát khỏi container. Nếu cần đưa report ra CI, thiết kế cơ chế thu thập file tạm với validation và **không truyền dữ liệu đó trực tiếp vào privileged shell**.

## 9. Java 17 demo: project Maven đơn giản để kiểm tra lệnh trong sandbox

Demo sau chỉ thực hiện phép cộng và hai JUnit tests; **không chứa payload độc hại**. Độ an toàn của bài học đến từ cách chạy, không phải giả lập tấn công.

Lưu tất cả files vào source export được phép thử. **Trước khi chạy bất kỳ repository ngoài nào, phải áp dụng cùng trust boundary như ví dụ Docker**.

### 9.1. Cấu trúc project

```text
untrusted-build-lab/
├── pom.xml
└── src/
    ├── main/java/dev/lesson/sandbox/SafeCalculator.java
    └── test/java/dev/lesson/sandbox/SafeCalculatorTest.java
```

### 9.2. `pom.xml` hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>untrusted-build-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>dev.lesson.sandbox.SafeCalculator</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là POM Java bình thường, không có external network trong application code. Nhưng vì POM là một **input mà PR có thể thay**, quy tắc an toàn là **không được tin POM mới chỉ vì nó trông giống ví dụ**; phải dùng sandbox kể cả với code demo nếu source đến từ người chưa tin cậy.

### 9.3. `src/main/java/dev/lesson/sandbox/SafeCalculator.java`

```java
package dev.lesson.sandbox;

public final class SafeCalculator {

    private SafeCalculator() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }

    public static void main(String[] args) {
        System.out.println("SANDBOX_OK=" + add(2, 3));
    }
}
```

`Math.addExact` là Java standard library; nó ném `ArithmeticException` khi phép cộng `int` bị tràn.

### 9.4. `src/test/java/dev/lesson/sandbox/SafeCalculatorTest.java`

```java
package dev.lesson.sandbox;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class SafeCalculatorTest {

    @Test
    void addsTwoNumbers() {
        assertEquals(5, SafeCalculator.add(2, 3));
    }

    @Test
    void detectsIntegerOverflow() {
        assertThrows(
                ArithmeticException.class,
                () -> SafeCalculator.add(Integer.MAX_VALUE, 1)
        );
    }
}
```

Có **hai JUnit unit tests**. Plugin Surefire 3.5.2 phát hiện class `*Test` và JUnit Jupiter engine từ dependency; không cần Gradle hay application server.

### 9.5. Lệnh chạy sau khi đã tạo môi trường cô lập

Ở trong sandbox đã chuẩn bị cache, Maven thực thi:

```bash
mvn -o -B -ntp -s /tmp/settings.xml \
  -Duser.home=/tmp \
  -Dmaven.repo.local=/tmp/m2 \
  clean verify

java -jar target/untrusted-build-lab-1.0.0.jar
```

**Đầu ra do Java main in (không phải toàn bộ Maven log):**

```text
SANDBOX_OK=5
```

Các file Maven sẽ tạo (ở scratch trong container):

```text
target/classes/dev/lesson/sandbox/SafeCalculator.class
target/test-classes/dev/lesson/sandbox/SafeCalculatorTest.class
target/surefire-reports/
target/untrusted-build-lab-1.0.0.jar
```

**Không chạy lệnh này trên host có Maven credentials, source bí mật hoặc quyền phát hành** chỉ để “tiết kiệm cấu hình sandbox”.

### 9.6. Không làm gì sau build?

Kết quả `verify` pass không làm project tự trở thành trusted. Nếu muốn release, source commit phải qua review/security policy; artifacts phải được kiểm tra rồi được build lại trong **trusted release environment** không kế thừa cache/outputs không đáng tin.

## 10. Tại sao không chỉ quét POM rồi mới quyết định sandbox?

Static review hữu ích để **hiểu rủi ro**, nhưng không thể chứng minh code không có hành vi nguy hiểm, vì:

- POM có thể khai parent POM hoặc profile cung cấp executions khác với snippet đang xem.
- Maven core extensions được load sớm và có thể đến từ project configuration.
- Plugin/transitive dependencies có bytecode không nằm trong repository.
- Test code hoặc annotation processors có thể thực thi logic ẩn.
- Một plugin trông hợp lệ vẫn có thể có version compromise hoặc configuration nguy hiểm.
- Cấu hình có thể thay theo `-D` properties, OS, Java version, environment, active profiles.

Vì vậy nên dùng **static inspection để phân loại và thiết kế sandbox**, không coi inspection là giấy phép chạy ngoài sandbox.

### Những nơi cần đọc bằng công cụ xem file, không thực thi

- `pom.xml` root và mọi module/parent POMs mà bạn có thể kiểm tra.
- `.mvn/extensions.xml`, `.mvn/maven.config`, `.mvn/jvm.config`.
- `mvnw`, `mvnw.cmd`, `.mvn/wrapper/*` nếu workflow định dùng wrapper.
- `<build><plugins>`, `<pluginManagement>`, `<executions>`, `<profiles>`, `<repositories>`, `<pluginRepositories>`.
- Java `META-INF/services/javax.annotation.processing.Processor`, configured annotation processors, test code/fixtures.
- CI workflow YAML, Git hooks/scripts, submodules, generator scripts, shell/PowerShell execution.
- Maven `settings.xml`, global settings và trusted parent POMs **chỉ trong môi trường người quản trị kiểm soát**.

**Đừng dùng `mvn help:effective-pom` như công cụ static viewer bên ngoài sandbox.** Nó khởi động Maven trên project và có thể nạp extensions. Nếu muốn kiểm tra effective POM, hãy chạy command đó **bên trong sandbox**, rồi xem kết quả như output chưa tin cậy.

## 11. Maven repositories: cho tải artifact không đồng nghĩa cho thực thi đáng tin

Maven có thể tải:

- Build plugins từ `pluginRepositories`.
- Project dependencies từ `repositories`.
- Parent POM và plugin dependencies từ những nguồn resolver tìm tới theo settings/POM/super POM.
- Artifacts transitive theo dependency graph.

Quyền truy cập artifact repository **không nên được nhầm** với quyền phát hành. Với untrusted build, thường chỉ cần **download** từ proxy/mirror được kiểm soát; không cấp token `deploy`.

### 11.1. Mirror do trusted infrastructure kiểm soát

Ví dụ settings cho một trusted public artifact proxy (không có credentials, chỉ là domain minh họa):

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <mirrors>
        <mirror>
            <id>reviewed-proxy</id>
            <url>https://repo.example.invalid/public-vetted/</url>
            <mirrorOf>*</mirrorOf>
        </mirror>
    </mirrors>
</settings>
```

**Đây là XML minh họa, chưa dùng được** vì `repo.example.invalid` không phải endpoint hoạt động. `mirrorOf=*` buộc Maven mirror các repository requests qua một đích tương ứng, nhưng:

- Nó không cấp policy kiểm duyệt artifact nếu proxy cho tải mọi byte không kiểm tra.
- Nó không phải firewall ngăn plugin/test tự mở HTTP connections.
- Nó có thể ảnh hưởng repositories khác (kể cả file/local URL theo rules); phải kiểm tra business requirements.
- Nó không tự xác minh signature/provenance hoặc ngăn malicious code chạy.
- Nó không thay thế cô lập host/process/filesystem.

**Kiểm soát egress phải ở network layer.** Nếu có internet allowlist, pipeline vẫn cần chặn cloud metadata/internal services và giới hạn DNS/redirect behavior theo kiến trúc.

### 11.2. Maven local repository riêng

Một project untrusted không được phép ghi vào `~/.m2/repository` của release runner hoặc developer. Dùng một path scratch:

```bash
mvn -Dmaven.repo.local=/tmp/untrusted-m2 clean verify
```

**Chỉ chạy lệnh này trong sandbox.** Tham số này chỉ chọn đường Maven local repository; bản thân nó **không sandbox** POM/plugins. Nếu directory là shared cache giữa jobs, code trong sandbox có thể ghi artifact giả/metadata độc hại vào đó và ảnh hưởng job khác.

Trong Docker demo, cache vetted host chỉ được **mount read-only**, rồi copy vào `/tmp/m2` writable riêng. Không xuất ngược bản copy đó về shared cache.

### 11.3. Thứ tự xây trusted cache

Vì `--network none` không thể tự tải JUnit/plugins, cần cache đã chuẩn bị. Một mẫu vận hành:

1. Trusted pipeline xác định build policy/toolchain và dependency allowlist.
2. Tải/provision artifacts vào cache **trong môi trường mạng restricted, có kiểm tra và không có release secrets**.
3. Vet origin, versions, checksums/signatures theo chính sách.
4. Publish một bản cache/OCI layer immutable để sandbox **chỉ đọc**.
5. Sandbox copy cache đó vào private scratch rồi chạy `mvn -o`.
6. Nếu thiếu artifact, quay lại trusted provisioning process; **không bật quyền mạng tùy ý trong untrusted job**.

**Không nên chạy `mvn dependency:go-offline` trên source chưa tin cậy ở privileged host để tạo cache.** Goal này vẫn chạy Maven/plugin và có thể kích hoạt extensions; nếu phải dùng, chạy trong môi trường cô lập phù hợp.

## 12. Không trộn build PR và release pipeline

Một pipeline thường có những job như:

```text
PR/Fork event
  |
  +--> Checkout/inspect with read-only rights
  |          |
  |          +--> Disposable untrusted Maven sandbox
  |                     |
  |                     +--> Tests, compile, report
  |                     +--> Logs + candidate artifact
  |
  +--> Review changes / scan candidate outputs as untrusted data
             |
             v
       Approved commit on protected branch/tag
             |
             v
       Trusted rebuild in controlled environment
             |
             v
       Sign/publish with short-lived scoped credentials
```

**Với untrusted PR, build job không có quyền `deploy`/`release:prepare`/push Git**, kể cả mã nguồn khai goal như vậy. Bảo vệ bằng credentials và network policies, không chỉ bằng lời hứa POM sẽ không gọi plugin deploy.

### GitHub Actions: trigger nào là bẫy?

GitHub phân biệt:

- `pull_request`: thông thường phù hợp hơn để build PR từ fork, với token read-only và không cấp secrets của base repo theo chính sách fork; vẫn cần giới hạn build sandbox/resources.
- `pull_request_target`: chạy workflow trong ngữ cảnh base repo, có thể có **privileged token và secrets**. **Không checkout rồi build/test code từ fork trong job privileged này**.
- `workflow_run`/`issue_comment` cũng có thể có quyền cao hơn; nếu chúng download artifacts do PR tạo rồi **thực thi** artifacts hoặc đưa nội dung vào shell, vẫn có nguy cơ vượt trust boundary.

**Không “lách” bằng cách cấp một token write cho PR để tests truy cập private registry.** Tách bước cần quyền khỏi bước thực thi code chưa tin cậy. Nếu cần scan private dependencies, dùng môi trường có quyền network/proxy rất hẹp, không đưa publisher credentials vào process chứa untrusted code.

### YAML tối thiểu để thể hiện phân quyền

```yaml
name: Untrusted PR Verify

on:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - name: Show checked-out commit
        run: git rev-parse HEAD
```

**Đây chỉ là đoạn cấu hình minh họa quyền thấp và checkout, không phải pipeline sandbox đầy đủ.** Nó chưa chạy Maven, chưa bảo vệ network hoặc filesystem; với repository chưa tin cậy, **bước build phải dùng sandbox** như phần 8 hoặc hosted isolated runner policy do platform cung cấp. Không đặt publisher secrets trong job này.

Cũng không nên coi `permissions: contents: read` là đồng nghĩa không còn token: nếu GitHub cấp `GITHUB_TOKEN` read-only, nó vẫn có quyền đọc một số nội dung. `persist-credentials: false` giúp không lưu checkout token trong Git config, nhưng chính sách secrets và isolated execution mới là ranh giới quan trọng.

## 13. Vì sao dùng self-hosted runner chung nguy hiểm?

Một runner tự quản lý có thể có:

- Disk chứa artifact của job trước.
- Credentials/service tokens trong home/environment.
- Docker socket, cloud CLI credentials và Kube config.
- Access tới private package registry, VPN, databases hoặc metadata service.
- Shared Maven cache và Git worktrees.
- Network route tới production control plane.

Nếu chạy một PR chưa tin cậy dưới tài khoản runner đó, code có thể đọc/ghi tất cả những gì identity hiện tại cho phép — container sơ sài với host mount rộng không giải quyết vấn đề.

**Ưu tiên runner ephemeral riêng từng job**, reset/discard sau khi hoàn thành. Với self-hosted infrastructure, áp dụng network segmentation, short-lived workload identity, tắt service account token mount nếu không cần (ví dụ Kubernetes `automountServiceAccountToken: false`), filesystem isolation và log/audit.

Không đặt build untrusted cùng node/VM có production credentials nếu có thể tránh. Docker-in-Docker/host Docker socket không phải giải pháp an toàn mặc định.

## 14. Cách tiếp nhận build artifacts từ môi trường thấp quyền

Output của untrusted build vẫn là **dữ liệu chưa tin cậy**. Một file tên `target/app.jar` không trở thành an toàn chỉ vì Surefire báo xanh.

Các rủi ro downstream:

- Một JAR chứa class thực thi logic nguy hiểm.
- Archive path traversal (ví dụ đường dẫn `../`) nếu job privileged giải nén thiếu validation.
- Symlinks/hardlinks trong tar/zip trỏ ra ngoài directory staging.
- Test report XML/HTML có dữ liệu được chèn để làm hỏng report viewer hoặc khai thác parser.
- File chứa tên/giá trị cố tình gây shell injection khi CI script ghép không quote.
- Cache hoặc artifact có đường dẫn trùng tên input tin cậy, dẫn tới cache poisoning.
- User-generated logs chứa escape/control sequences, secrets mà job khác đã vô tình cấp.

### Quy trình đúng

1. Lưu candidate artifacts dưới quyền/namespace **quarantine**, gắn Git SHA và job ID.
2. Không auto-execute JAR/scripts đó trong publisher.
3. Scan/validate archive entries, sizes, decompression limits, allowed file types, symlink policy.
4. Parse reports bằng tool được harden, xem toàn bộ nội dung như **data**, không ghép vào shell command hoặc workflow YAML.
5. Nếu cần công bố release, **rebuild từ commit đã approved** bằng trusted toolchain/caches, đối chiếu provenance/checksums và chạy release tests.
6. Publisher dùng token scope tối thiểu, publish đúng artifact/GAV/version sau approval.
7. Không upload caches từ PR vào shared caches mà release job sẽ trust.

**Một checksum đúng chỉ chứng minh byte identity của một file**, không cho biết file an toàn về mặt nghiệp vụ hay security. SBOM/provenance/attestation và vulnerability scanning bổ trợ, không thay isolation.

## 15. Tình huống thực tế: chọn policy nào?

| Trường hợp | Policy phù hợp | Tại sao |
| --- | --- | --- |
| PR công khai chỉ cần compile/unit tests | Ephemeral runner, no release secrets, read-only token nếu thật sự cần, resource/time limits, network restricted | Build code có thể chạy arbitrary logic, không cần deploy |
| Source archive từ website lạ | Disposable VM/microVM không secrets; offline/vetted deps khi có thể | Không biết POM/extensions/wrapper có gì |
| PR cần private Maven dependency | Trusted provisioning proxy hoặc restricted dependency fetch, không đưa publisher token vào process untrusted | Download permission khác write/publish |
| Parent POM mới trỏ custom plugin repository | Static review + sandbox + allowlisted repository manager | Parent POM/plugin cũng là executable build input |
| Dự án cần database IT | Ephemeral test DB mạng riêng, account chỉ truy cập synthetic data, không route production | IT không cần production credentials/data |
| Dự án cần Docker để integration tests | Dedicated ephemeral VM/runner với nested isolation phù hợp, không chia host Docker socket mặc định | Docker socket có quyền quản lý host |
| Build yêu cầu native code/process spawning | Sandbox có allowlisted syscalls/tools, no privileges, quotas | Test capabilities không đồng nghĩa admin access |
| Tạo release từ protected branch | Trusted job sau approvals, short-lived signer/publisher token và source provenance | Release cần quyền cao nhưng không được dùng code PR chưa review |
| CI chỉ muốn xem POM/dependency tree | Static file inspection bên ngoài; nếu gọi Maven, vẫn chạy trong sandbox | Maven extension/goal có thể thực thi |
| Cần ghép report PR với comment bot | Bot xử lý report như dữ liệu, không thực thi/deserialize tùy tiện, có quyền ghi đúng API scope | Job có token không được chạy mã PR |

### Khi nào quyết định “không build”?

Có thể hợp lý khi:

- Chưa có sandbox đáp ứng độ rủi ro.
- Project bắt buộc chạy privileged Docker host/production VPN để test.
- Dependency nguồn gốc không kiểm soát, có yêu cầu cấp secrets vào Maven process.
- Network/proxy policy không thể chặn truy cập tài nguyên nội bộ.
- Runtime không thể giới hạn resource/time hoặc chưa có khả năng cleanup.
- Bên ngoài yêu cầu chạy `curl ... | sh` từ URL không được thẩm định ngay trên runner tin cậy.

Trong các trường hợp này, **không chạy** cho đến khi có môi trường tương ứng tốt hơn; chuyển sang static review/VM riêng hoặc yêu cầu thay đổi test architecture. Một build đỏ do thiếu quyền không phải lý do để cấp admin cho mã chưa tin cậy.

## 16. Những hiểu nhầm nguy hiểm

### “Chỉ chạy compile chứ không chạy main nên an toàn”

Sai. Annotation processors, compiler plugins, build extensions và goals ở phases sớm có thể chạy code. Không cần chạy `java -jar` mới có side effect.

### “Chạy `mvn -o` thì Java không thể gọi network”

Sai. Offline mode của Maven kiểm soát artifact resolution qua Maven; custom plugin/test có thể mở sockets nếu network namespace cho phép. Muốn giới hạn egress, dùng firewall/network isolation.

### “Bỏ qua tests sẽ chặn code lạ”

Sai. `-DskipTests` không tắt mọi plugin/goals/extension/compile logic.

### “Docker là đủ, cứ mount `~/.m2` để build nhanh”

Không. Home Maven repo có thể chứa `settings.xml`, credentials và cached artifacts ảnh hưởng trusted jobs. Nếu mount write vào shared cache, project chưa tin cậy có thể làm nhiễm repository. Chỉ cung cấp cache public vetted read-only, copy thành scratch riêng.

### “Source mount read-only thì không thể gây hại host”

Không đúng hoàn toàn. Code có thể đọc những gì được mount, dùng network, Docker socket hoặc kernel attack surface nếu các quyền khác còn mở. Read-only ngăn sửa source mount, không đồng nghĩa ngăn exfiltration hay host compromise.

### “Cứ bật `--privileged` để integration test chạy”

Đó là xóa bỏ lớp bảo vệ mạnh. Đánh giá nhu cầu Testcontainers/Docker-in-Docker và dùng runner/VM chuyên dụng có quyền giới hạn; không trao Docker daemon host cho PR chưa tin cậy.

### “Pull request đã pass tests thì có thể dùng artifact của nó để release”

Không. Tests do PR có thể bị sửa và artifact vẫn là output chưa được phê duyệt. Release nên có provenance/approved commit/trusted rebuild và quyền publish được tách.

### “Maven settings dùng mirror là đã chặn plugin gửi dữ liệu ra ngoài”

Không. Mirror điều khiển Maven repository resolution, không ràng buộc network API của mã/plugin tùy ý. Firewall/container egress policy phải độc lập.

### “`permissions: contents: read` nghĩa là không có rủi ro”

Không. Read-only token vẫn có thể tiết lộ private data nếu không ngăn exfil. Bảo vệ cần xem toàn bộ secrets, môi trường, caches và runner network.

## 17. Diagnostic khi sandbox build fail

| Triệu chứng | Khả năng cao | Hướng xử lý an toàn |
| --- | --- | --- |
| Maven offline không tìm được plugin | Seed cache thiếu plugin/transitive artifacts | Quay lại trusted cache-provisioning; không mở unrestricted network |
| `Could not resolve dependencies` | Cache thiếu, artifact không được phép, repo policy chặn | Kiểm tra GAV và approval list; không nhét private token vào sandbox |
| `Permission denied` ở `target` | Workspace read-only/nonroot không ghi được | Dùng scratch writable nội bộ; không chuyển host source mount sang rw |
| Không có `java.home`/user home | UID non-root không có home, runtime config sai | Set HOME/user.home tới tmpfs, không mount host home |
| `OutOfMemoryError`/job killed | Resource limits quá thấp hoặc code bất thường | Review logs và quotas, không auto-unlimit cho untrusted job |
| Timeout ở test | Test chờ network/DB/time hoặc vòng lặp | Xác định sandbox limitation, dùng synthetic dependencies; không cấp production network |
| Test cần Docker socket | Plugin/Testcontainers cần daemon | Dùng dedicated disposable VM hoặc mô hình builder an toàn, không mount host socket |
| Parent/plugin repository bị chặn | Build đang cố sử dụng endpoint ngoài allowlist | Review POM/parent; vet repository hoặc từ chối |
| Build pass nhưng output không thấy trên host | Scratch tmpfs xóa sau `--rm` | Đúng design; export theo quarantine workflow riêng |
| Maven Wrapper fail | Launcher/permissions/URL wrapper khác chính sách | Không chạy wrapper chưa review; dùng pinned Maven image |
| POM goal execute trước `test` | Maven lifecycle plugin execution | Review effective POM **trong sandbox**, không skip test là đủ |
| CI PR build có secrets | Trigger/checkout/job permissions sai | Tắt job, rotate secrets bị lộ, tách trusted/untrusted workflows |
| Trusted pipeline nhận malicious report | Report/artifact treated as executable | Quarantine, sanitize parser/unpack và audit cache paths |

**Đừng diễn giải “sandbox chặn được thao tác” là lỗi cần sửa bằng cách tắt sandbox.** Với untrusted code, giới hạn là một phần chức năng bảo mật dự kiến.

### Lệnh xem Maven runtime *chỉ bên trong sandbox*

```bash
mvn -version
mvn -o -B -ntp -s /tmp/settings.xml \
  -Dmaven.repo.local=/tmp/m2 \
  help:effective-pom
mvn -o -B -ntp -s /tmp/settings.xml \
  -Dmaven.repo.local=/tmp/m2 \
  dependency:tree
```

Các goals này có thể cần plugins đã seed. **Chỉ chạy sau khi isolation được thiết lập**, không chạy để “chứng minh an toàn” ở host.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `mvn clean verify` từ một PR chưa review phải được xem là chạy mã?

**Đáp án:** Maven có thể thực thi plugins, extensions, annotation processors, tests và các công cụ khác được cấu hình bởi POM/source.

**Câu 2.** `-DskipTests` có ngăn mọi hành vi thực thi không?

**Đáp án:** Không. Nó không tắt extension/plugin/goals ở phases khác và không phải security boundary.

**Câu 3.** `mvn -o` có phải firewall không?

**Đáp án:** Không. Nó giới hạn Maven artifact resolution offline; arbitrary code vẫn có thể kết nối nếu network policy cho phép.

**Câu 4.** Tại sao không mount `~/.m2` writable từ host vào container?

**Đáp án:** Có thể lộ settings/secrets, và build chưa tin cậy có thể ghi artifacts/metadata gây cache poisoning cho các jobs sau.

**Câu 5.** Trong demo, vì sao Maven local repo được copy từ `/seed` vào `/tmp/m2`?

**Đáp án:** `/seed` vetted cache chỉ đọc, còn `/tmp/m2` là private scratch writable để Maven vận hành không thay shared trusted cache.

**Câu 6.** `--network none` cộng `mvn -o` có bảo đảm chống mọi host compromise không?

**Đáp án:** Không. Chúng giảm network/exfil, nhưng vẫn cần nonroot, read-only, capabilities/seccomp, resource limits, VM isolation và patched runtime khi phù hợp.

**Câu 7.** `pull_request_target` với checkout từ fork và chạy Maven có nguy hiểm không?

**Đáp án:** Có, nếu job có secrets/write token. Không chạy untrusted PR code trong privileged workflow; dùng `pull_request` hoặc phân tách trust boundary theo GitHub policy.

**Câu 8.** Build pass trong sandbox có nên ngay lập tức publish JAR bằng release token không?

**Đáp án:** Không. Candidate artifact vẫn là dữ liệu chưa tin cậy; cần review, approved commit, trusted rebuild và provenance/scan.

**Câu 9.** Lệnh Docker mẫu có chạy được với Maven local repository rỗng và không có mạng không?

**Đáp án:** Thường không, vì phải resolve plugins/dependencies. Cần seed vetted cache đủ hoặc một trusted/provisioned image trước; không tự cấp network unrestricted.

**Câu 10.** Nếu tests yêu cầu production database, cách đúng có phải đưa production DB credentials vào PR build không?

**Đáp án:** Không. Dùng synthetic data và ephemeral test DB riêng, hoặc chuyển loại kiểm thử cần quyền cao sang trusted post-approval environment.

**Câu 11.** Khi dùng Docker container, tại sao không mount `/var/run/docker.sock`?

**Đáp án:** Nó cung cấp quyền điều khiển Docker daemon host; trong môi trường daemon đặc quyền có thể dẫn tới kiểm soát host.

**Câu 12.** Một file report từ PR có được xem là trusted chỉ vì phần mở rộng `.xml`/`.json` không?

**Đáp án:** Không. Cần parse an toàn như dữ liệu chưa tin cậy và không chạy code/command lấy từ report.

## 19. Checklist trước khi cho phép build mã chưa tin cậy

- [ ] Xác định source/commit/archive và lý do nó chưa tin cậy.
- [ ] Không chạy Maven/Wrapper/goals của source trên laptop hoặc privileged runner.
- [ ] Có static review cho POM, parent, profiles, `.mvn`, plugins, repositories và CI configs.
- [ ] Không xem static review là thay thế sandbox.
- [ ] Sandbox có isolation phù hợp mức độ rủi ro; dùng VM/microVM khi cần.
- [ ] Runner ephemeral, không lưu trạng thái/credentials giữa jobs.
- [ ] Không có secrets, Git write token, signing key, Maven deploy password hay cloud credentials.
- [ ] Không mount `$HOME`, `~/.m2/settings.xml`, `~/.ssh`, Docker socket hoặc cloud credential directories.
- [ ] Source export không chứa `.git` credential leaks hay secret files.
- [ ] Source mount read-only; scratch workspace riêng.
- [ ] Maven local repo riêng, không ghi ngược vào trusted/shared cache.
- [ ] Non-root UID, capabilities tối thiểu, `no-new-privileges`.
- [ ] Không dùng `--privileged`, host network hay unrestricted device mounts.
- [ ] Network blocked hoặc only allowlisted vetted dependency hosts.
- [ ] Chặn egress tới cloud metadata/internal control plane.
- [ ] Maven/JDK/container image pin versions và kiểm tra nguồn, digest khi production.
- [ ] CPU/RAM/pids/disk/time/log-size limits rõ ràng.
- [ ] Offline build có vetted Maven cache đầy đủ; không bật unrestricted network khi cache thiếu.
- [ ] Không nhầm `-DskipTests`/`mvn -o`/Maven mirror thành security sandbox.
- [ ] CI trigger phù hợp: không build fork PR với privileged `pull_request_target`.
- [ ] Log/report/artifact từ untrusted jobs luôn được xử lý như untrusted data.
- [ ] Không tái sử dụng PR-written caches trong release jobs.
- [ ] Có validate/sanitize archive outputs trước khi downstream đọc hoặc giải nén.
- [ ] Release chạy từ approved commit/tag với trusted rebuild và scoped publisher credentials.
- [ ] Có ghi nhận Git SHA, build image/toolchain, permissions và audit logs.
- [ ] Có quy trình dừng, điều tra và rotate/revoke secrets nếu phát hiện rò rỉ.

**Kết luận:** Maven có thể thực thi mã không tin cậy ngay trong build model/plugins/extensions/compile/tests. Vì vậy **quyền của môi trường build chính là giới hạn thiệt hại nếu mã đó hành xử xấu**. Một quy trình đúng phải cô lập source trong runner ephemeral, không cấp secrets/Git write/repository deploy, hạn chế mạng và filesystem, chạy non-root với resource quotas, và chỉ chuyển **dữ liệu** qua bước review sang trusted release pipeline. `BUILD SUCCESS` chứng minh build chạy được trong điều kiện thử; **không phải giấy chứng nhận an toàn của source**.

## Nguồn chính thức và đọc thêm

- [Apache Maven — Security Reports và Security Model](https://maven.apache.org/security)
- [Apache Maven — Build Lifecycle và Plugin Executions](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Plugins and Goals](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Maven Wrapper](https://maven.apache.org/wrapper/)
- [Docker — docker container run Reference](https://docs.docker.com/reference/cli/docker/container/run/)
- [Docker — Rootless Mode](https://docs.docker.com/engine/security/rootless/)
- [GitHub Actions — Securely Using pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)
- [GitHub Actions — Secure Use Reference](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub Actions — Compromised Runners](https://docs.github.com/en/actions/concepts/security/compromised-runners)
- [OpenSSF — Scorecard Project](https://github.com/ossf/scorecard)

*Bài dùng Maven 3.9.16, JDK 17 và Maven plugins được pin. Docker command là ví dụ có điều kiện, chỉ nên chạy trên runner đã chuẩn bị nguồn/cache/image phù hợp; không có bất kỳ mã PR chưa tin cậy, Docker container hay build thực tế nào được chạy khi biên soạn bài học.*
