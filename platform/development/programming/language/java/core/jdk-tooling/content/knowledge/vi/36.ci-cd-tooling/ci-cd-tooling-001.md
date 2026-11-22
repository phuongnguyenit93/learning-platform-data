# Cài JDK trong CI/CD pipeline

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao CI cần JDK; phân biệt JDK với runtime; chọn đúng phiên bản, vendor, kiến trúc và package; cài hoặc chọn JDK trên hosted runner, self-hosted runner và container; cấu hình JAVA_HOME và PATH; kiểm tra compiler/runtime thực tế; dùng GitHub Actions, GitLab CI, Azure Pipelines và Jenkins để chuẩn bị JDK; quản lý nhiều JDK bằng matrix và Java toolchains; cache JDK/dependency đúng cách; xác minh checksum và nguồn tải; và xử lý lỗi khi pipeline không tìm thấy hoặc dùng nhầm Java.

## 1. JDK trong CI là gì?

CI (Continuous Integration) chạy build và kiểm tra tự động mỗi khi có thay đổi source hoặc theo lịch. Để biên dịch, test, tạo Javadoc và đóng gói ứng dụng Java, CI agent cần một **Java Development Kit (JDK)** phù hợp với project.

JDK cung cấp các công cụ phát triển, ví dụ:

- **java:** khởi chạy ứng dụng Java.
- **javac:** biên dịch source .java thành bytecode .class.
- **jar:** tạo và thao tác với Java archive.
- **javadoc:** tạo tài liệu API.
- Các công cụ chẩn đoán như jcmd, jstack và jmap tùy package.

JDK thường cũng chứa Java runtime cần thiết để chạy chương trình. Một runtime-only image có thể chạy ứng dụng đã build nhưng thiếu javac, nên không phù hợp cho job phải biên dịch source.

**Cài JDK trong CI** nghĩa là làm cho đúng bộ công cụ Java có sẵn trong môi trường build, rồi bảo đảm các lệnh build thực sự sử dụng bộ công cụ đó.

Một pipeline có thể lấy JDK từ:

1. Hosted runner đã cài sẵn JDK.
2. Action/task của CI tải và cài JDK theo version/vendor.
3. Docker/container image đã chứa JDK.
4. JDK archive nội bộ được giải nén trên runner.
5. Tool installation được quản lý tập trung trên Jenkins hoặc self-hosted agent.

Không có một cách duy nhất phù hợp cho mọi CI. Hãy chọn cách tương ứng với loại runner, yêu cầu bảo mật, khả năng truy cập mạng và mức độ tái lập cần thiết.

## 2. Phân biệt JDK, runtime và phiên bản Java

### JDK và runtime

| Thành phần | Có gì | Dùng khi nào |
|---|---|---|
| JDK | Runtime cùng compiler và công cụ phát triển | Compile, test, tạo Javadoc, package |
| Runtime image | Thành phần cần để chạy ứng dụng | Chạy artifact đã build |
| JRE (cách gọi truyền thống) | Java runtime environment | Khái niệm thường gặp ở các bản Java cũ; không phải lúc nào cũng được phân phối như package riêng ở Java hiện đại |

Nếu pipeline chạy javac, nó cần JDK. Lệnh java --version thành công chưa chứng minh compiler đã được cài. Luôn kiểm tra cả:

~~~bash
java --version
javac --version
~~~

### Phiên bản JDK và target của ứng dụng

Có ba lựa chọn cần phân biệt:

- **JDK chạy build:** JVM khởi chạy Maven hoặc Gradle.
- **JDK compiler/toolchain:** compiler được dùng để biên dịch source.
- **Java release target:** phiên bản bytecode và API mà artifact được phép sử dụng.

Ví dụ, project có thể chạy Maven trên JDK 21, dùng compiler JDK 21, nhưng tạo bytecode tương thích Java 17 bằng --release 17.

Vì vậy, java --version chỉ cho biết runtime được tìm thấy qua PATH. Nó chưa chắc cho biết compiler hoặc test task đang sử dụng cùng JDK. Hãy xem thêm mvn --version, ./gradlew --version và cấu hình toolchain của project.

## 3. Chọn JDK trước khi cài

Trước khi cấu hình pipeline, xác định các thuộc tính sau:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Feature version | Project yêu cầu Java 17, 21 hay 25? |
| Vendor/distribution | Dùng Temurin, Oracle, Corretto, Zulu, Microsoft Build of OpenJDK hay distribution đã được tổ chức phê duyệt? |
| Architecture | Runner là x64, ARM64 hay kiến trúc khác? |
| Operating system | Linux, Windows hay macOS? |
| Package | Cần JDK tiêu chuẩn, JDK kèm JMODs hay package đặc biệt? |
| Patch level | Chấp nhận bản cập nhật mới nhất của một feature release hay cần pin một patch cụ thể? |
| Support policy | Phiên bản nào được vendor/tổ chức hỗ trợ và còn nhận security update? |

### Chọn feature release

Project cũ có thể cần JDK 17; project mới có thể chuẩn hóa trên JDK 21 hoặc JDK 25. Hãy căn cứ vào:

- Phiên bản Gradle/Maven và plugin.
- Framework và dependency.
- Language feature được sử dụng.
- Runtime của production.
- Chính sách hỗ trợ và security update.

Không nâng JDK chỉ vì runner có sẵn bản mới nhất. Trước khi nâng, kiểm tra Gradle/Maven, plugin, test engine, annotation processor, native library và dependency có hỗ trợ hay không.

### Chọn vendor

Nhiều distribution cung cấp OpenJDK build. Chúng có thể khác về lịch phát hành, hỗ trợ, package, chứng nhận, chính sách cập nhật và điều khoản sử dụng.

Chọn một distribution được tổ chức chấp thuận, ghi rõ tên trong CI configuration và giữ nhất quán giữa CI, staging và production khi yêu cầu tương thích đòi hỏi.

### Chọn version selector

Một cấu hình như 21 thường có nghĩa là chọn một bản thuộc feature release 21 theo metadata/tool cache của installer. Nó có thể nhận các patch update mới theo thời gian.

Nếu cần tái lập nghiêm ngặt, pin patch/build cụ thể hoặc pin digest của container image. Nếu mục tiêu là tự động nhận security update trong cùng feature release, dùng selector theo major version và lên lịch kiểm tra kết quả cập nhật.

## 4. CI agent và các mô hình cài JDK

### Hosted runner

Hosted runner là máy ảo do CI provider tạo cho job. Một số JDK có thể đã được cài sẵn hoặc nằm trong tool cache.

Không nên giả định mọi hosted image đều có cùng phiên bản Java. Danh sách cài sẵn thay đổi theo OS image và thời điểm. Dùng action/task cài đặt để yêu cầu rõ version và vendor; bước verify giúp phát hiện thay đổi môi trường.

### Self-hosted runner

Self-hosted runner do tổ chức quản lý. Có thể cài JDK trước trên máy, lưu nhiều version hoặc dùng installer trong job.

Ưu điểm là kiểm soát được network, mirror, tool version và tài nguyên. Đổi lại, cần quản lý patch, quyền truy cập, disk space, PATH, JAVA_HOME và việc dọn tool cũ.

### Container-based runner

Job chạy bên trong container image. JDK cần có trong image mà job thực thi; JDK trên host runner không tự động xuất hiện trong container.

Ví dụ image eclipse-temurin:21-jdk chứa JDK 21. Nếu cần Maven, có thể dùng Maven image kết hợp JDK hoặc cài/chạy Maven Wrapper trong image JDK.

### Cài theo từng job hay bake vào image?

| Cách | Phù hợp khi | Điểm cần lưu ý |
|---|---|---|
| CI action/task | Hosted runner hoặc job cần nhiều version | Dễ khai báo version; có thể tải JDK |
| Container image | Job dùng Docker/Kubernetes executor | Pin tag/digest; cập nhật image định kỳ |
| Pre-installed JDK | Self-hosted runner ổn định | Quản lý tool trên từng agent |
| Archive nội bộ | Mạng hạn chế hoặc distribution tùy chỉnh | Xác minh checksum/signature và quản lý phiên bản |
| Package manager của OS | Runner Linux được kiểm soát | Repository và package version phải được pin/kiểm soát |

## 5. JAVA_HOME và PATH

Hai biến này quyết định nhiều lệnh Java mà build tool tìm thấy.

- JAVA_HOME nên trỏ tới thư mục gốc của JDK.
- PATH nên chứa thư mục bin của JDK.

Ví dụ Linux:

~~~bash
export JAVA_HOME=/opt/jdk/temurin-21
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
~~~

Đường dẫn trên là ví dụ; thay bằng thư mục cài đặt thực tế.

Cấu trúc đúng:

~~~text
/opt/jdk/temurin-21/
├── bin/
│   ├── java
│   ├── javac
│   └── jar
├── conf/
├── include/
└── lib/
~~~

JAVA_HOME phải trỏ tới /opt/jdk/temurin-21, không phải /opt/jdk/temurin-21/bin và cũng không phải file java.

### Windows

PowerShell:

~~~powershell
$env:JAVA_HOME = 'C:\Java\jdk-21'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java --version
javac --version
where.exe java
where.exe javac
~~~

Trên Windows, dùng dấu chấm phẩy để phân tách PATH. Linux/macOS dùng dấu hai chấm.

### Kiểm tra lệnh đang được gọi

Linux/macOS:

~~~bash
command -v java
command -v javac
printf '%s\n' "$JAVA_HOME"
~~~

Windows:

~~~powershell
where.exe java
where.exe javac
Write-Output $env:JAVA_HOME
~~~

Nếu java và javac đến từ hai thư mục khác nhau, pipeline có thể chạy bằng runtime này nhưng compile bằng JDK khác. Hãy kiểm tra thứ tự PATH và gọi trực tiếp $JAVA_HOME/bin/java hoặc $JAVA_HOME/bin/javac khi cần chẩn đoán.

### Biến môi trường có tồn tại qua các step không?

Một lệnh export chỉ tác động tới process shell hiện tại và các process con của nó. Với CI có nhiều step riêng biệt, không mặc định rằng export trong step này tồn tại ở step sau.

- GitHub Actions: dùng GITHUB_ENV và GITHUB_PATH để truyền biến/đường dẫn sang step tiếp theo; setup-java tự cấu hình môi trường.
- GitLab CI: các lệnh before_script và script của cùng job chạy trong môi trường job; job khác có môi trường riêng.
- Azure Pipelines: task installer đặt JAVA_HOME/PATH cho các task tiếp theo trong job.
- Jenkins Declarative Pipeline: khối tools thiết lập môi trường cho pipeline hoặc stage tương ứng.

Cài JDK ở một job không tự làm JDK xuất hiện trong job khác, trừ khi các job dùng chung một môi trường bền vững hoặc artifact/image/tool cache được cấu hình rõ ràng.

## 6. Kiểm tra JDK sau khi cài

Một bước verify nên chạy ngay sau bước setup, trước khi gọi Maven hoặc Gradle.

~~~bash
set -eu

if [ -z "$JAVA_HOME" ]; then
  echo "JAVA_HOME is not set" >&2
  exit 1
fi

test -x "$JAVA_HOME/bin/java"
test -x "$JAVA_HOME/bin/javac"

echo "JAVA_HOME=$JAVA_HOME"
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/javac" --version

command -v java
command -v javac
~~~

Các kiểm tra này xác nhận:

1. JAVA_HOME đã được đặt.
2. Có cả Java runtime và Java compiler trong JDK.
3. Có thể chạy trực tiếp binary trong JAVA_HOME.
4. PATH có lệnh Java để build script sử dụng.

Sau đó kiểm tra build tool:

~~~bash
mvn --version
./gradlew --version
~~~

Chỉ chạy lệnh tương ứng với build tool của project. Maven và Gradle hiển thị JVM dùng để khởi chạy chính build tool; cấu hình toolchain có thể chọn compiler/test JDK khác.

## 7. Cài JDK bằng GitHub Actions

actions/setup-java là action chính thức để chọn và cài Java cho workflow. Nó có thể tải distribution được yêu cầu, dùng tool cache trên hosted runner, thiết lập JAVA_HOME và PATH, đồng thời hỗ trợ cache dependency cho Maven, Gradle và sbt.

Ví dụ sau dùng JDK 21 và Maven:

Tạo .github/workflows/java-ci.yml:

~~~yaml
name: Java CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout source
        uses: actions/checkout@v7

      - name: Set up JDK 21
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Verify JDK
        run: |
          echo "JAVA_HOME=$JAVA_HOME"
          java --version
          javac --version

      - name: Build and test
        run: ./mvnw --batch-mode --no-transfer-progress verify
~~~

Giải thích:

- distribution: temurin chọn Eclipse Temurin.
- java-version: '21' chọn feature release 21.
- setup-java đặt JAVA_HOME và thêm bin vào PATH cho các step tiếp theo.
- cache: maven cache dependency Maven và wrapper cache phù hợp.
- ./mvnw dùng Maven Wrapper của repository để cố định phiên bản Maven.
- verify chạy các bước lifecycle cần thiết tới phase verify.

Nếu project dùng Gradle, có thể thay cache và build command:

~~~yaml
      - name: Set up JDK 21
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'
          cache: gradle

      - name: Build and test
        run: ./gradlew --no-daemon check
~~~

Không cần cài Maven hoặc Gradle riêng nếu repository đã commit wrapper và runner có các công cụ cần thiết để wrapper chạy.

### Kiểm tra nhiều JDK bằng matrix

Nếu project hỗ trợ nhiều Java release, dùng matrix để chạy cùng build trên từng version:

~~~yaml
jobs:
  verify:
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false
      matrix:
        java: ['17', '21', '25']

    name: Verify on Java ${{ matrix.java }}

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven

      - run: java --version
      - run: javac --version
      - run: ./mvnw --batch-mode verify
~~~

Mỗi matrix entry là một job với môi trường riêng. JDK được cài trong job đó và không chia sẻ JAVA_HOME với job khác.

Matrix hữu ích khi cần xác nhận tương thích nhiều JDK. Nếu project chỉ hỗ trợ một version, matrix nhiều version có thể làm CI tốn thời gian và tải dependency không cần thiết.

### Cài nhiều JDK trong cùng một job

setup-java hỗ trợ nhiều version trong input java-version. Tất cả JDK được cài; version được thêm cuối cùng trở thành mặc định trong PATH. Các JDK khác có thể được truy cập qua biến version-specific như JAVA_HOME_17_X64.

Dùng cách này khi một job thực sự cần chạy nhiều compiler/test runtime. Nếu chỉ cần test compatibility, matrix thường dễ cô lập và dễ đọc hơn.

### Version và distribution

setup-java v6 hỗ trợ nhiều distribution và cú pháp version. Có thể dùng major version, patch version cụ thể, version range hoặc alias latest tùy hỗ trợ của distribution.

latest thay đổi theo metadata phát hành. Dùng nó cho job cần thử nghiệm với bản GA mới nhất; dùng version rõ ràng cho build release cần tái lập.

Với self-hosted runner, setup-java v6 dùng Node 24; runner cần phiên bản tương thích (từ v2.327.1 theo hướng dẫn action). Kiểm tra yêu cầu runner trước khi nâng action.

## 8. Cài JDK bằng GitLab CI

Với GitLab Runner dùng Docker hoặc Kubernetes executor, cách đơn giản là chọn job image đã có JDK. image là container image được dùng để chạy lệnh của job.

Ví dụ dùng Maven Official Image kết hợp Eclipse Temurin JDK 21:

~~~yaml
stages:
  - verify

default:
  image: maven:3-eclipse-temurin-21-noble

variables:
  MAVEN_OPTS: "-Dmaven.repo.local=$CI_PROJECT_DIR/.m2/repository"

cache:
  key:
    files:
      - pom.xml
  paths:
    - .m2/repository/

verify:
  stage: verify
  script:
    - java --version
    - javac --version
    - mvn --batch-mode --no-transfer-progress verify
~~~

Image Maven có cả Maven và JDK nên job không phải tải riêng Maven. Nếu dùng image chỉ có JDK, hãy dùng Maven Wrapper hoặc cài build tool theo cách được project quản lý.

### Chọn image đúng

- Dùng image JDK nếu project có wrapper hoặc script build đã chuẩn bị Maven/Gradle.
- Dùng Maven image nếu job gọi mvn trực tiếp.
- Dùng tag thể hiện rõ Maven version, JDK distribution/version và base OS khi cần kiểm soát.
- Pin image digest nếu cần cùng một image bất biến giữa các lần chạy.

Tag maven:3-eclipse-temurin-21-noble thể hiện Maven major 3, Temurin 21 và Ubuntu Noble. Tag có thể được cập nhật; digest pin chặt hơn tag.

### Lưu ý về executor

image áp dụng cho executor chạy container như Docker hoặc Kubernetes. Với Shell executor, script chạy trực tiếp trên máy runner; container image trong .gitlab-ci.yml không tự cài JDK cho máy đó.

Với Shell executor, cài JDK trên host runner và cấu hình JAVA_HOME/PATH, hoặc chuyển job sang executor dùng container nếu kiến trúc CI cho phép.

### Cache trong GitLab

Ví dụ trên cache Maven repository tại .m2/repository. Cache dependency giúp giảm thời gian tải artifact; nó không phải là cách cài JDK.

Nếu project dùng Gradle, cache các thư mục dependency/wrapper phù hợp và chọn image có JDK tương thích. Không chia sẻ cache có trạng thái không an toàn giữa các job ghi đồng thời; dùng cache key và chính sách pull/push theo pipeline.

## 9. Cài JDK bằng Azure Pipelines

Azure Pipelines cung cấp task JavaToolInstaller@1. Task này lấy JDK từ tool cache, thư mục local hoặc Azure Storage và thiết lập JAVA_HOME cho các task tiếp theo.

Ví dụ chọn JDK đã có trên Microsoft-hosted agent:

~~~yaml
trigger:
- main

pool:
  vmImage: ubuntu-latest

steps:
- checkout: self

- task: JavaToolInstaller@1
  displayName: Use JDK 21
  inputs:
    versionSpec: '21'
    jdkArchitectureOption: 'x64'
    jdkSourceOption: 'PreInstalled'

- script: |
    echo "JAVA_HOME=$JAVA_HOME"
    java --version
    javac --version
    ./mvnw --batch-mode verify
  displayName: Verify JDK and build
~~~

PreInstalled chỉ hoạt động khi hosted agent image thực sự có version được yêu cầu. Hãy kiểm tra danh sách software của image đang dùng.

### Các nguồn JDK của JavaToolInstaller

| jdkSourceOption | Nguồn | Khi nào dùng |
|---|---|---|
| PreInstalled | JDK đã có trong agent tool cache | Hosted image hoặc agent được chuẩn bị sẵn |
| LocalDirectory | Archive JDK tại local path hoặc source | Self-hosted agent hoặc package đã tải trước |
| AzureStorage | Archive trong Azure Storage | Tổ chức lưu JDK nội bộ |

Với LocalDirectory, cung cấp jdkFile trỏ tới archive và jdkDestinationDirectory để giải nén. Archive cần chứa cấu trúc JDK hợp lệ.

Với AzureStorage, task v1 dùng Azure Resource Manager service connection và Azure RBAC để đọc blob. Cấp quyền Storage Blob Data Contributor cho identity của service connection theo chính sách Azure; tránh đưa storage key hoặc SAS token dài hạn vào YAML.

Task đặt JAVA_HOME và cập nhật PATH cho các bước tiếp theo. Nếu dùng self-hosted agent, hãy xác nhận agent version và quyền truy cập archive/tool cache.

## 10. Cài JDK bằng Jenkins

Jenkins quản lý JDK như một tool installation. Administrator khai báo JDK trong:

**Manage Jenkins → Tools**

Có thể chọn:

- JDK đã cài sẵn trên agent và khai báo đúng JDK home.
- Tự động cài JDK bằng installer được cấu hình.
- Dùng archive từ repository nội bộ qua custom installer.

Trong Declarative Pipeline, khai báo tool theo tên đã đăng ký:

~~~groovy
pipeline {
    agent any

    tools {
        jdk 'Temurin-21'
    }

    stages {
        stage('Verify JDK') {
            steps {
                sh 'echo "JAVA_HOME=$JAVA_HOME"'
                sh 'java --version'
                sh 'javac --version'
            }
        }

        stage('Build') {
            steps {
                sh './mvnw --batch-mode verify'
            }
        }
    }
}
~~~

Temurin-21 là logical name do administrator đặt trong Jenkins Tool Configuration. Nó phải khớp chính xác với tên được tham chiếu trong Jenkinsfile.

Trong Declarative Pipeline, tools đặt JAVA_HOME và thêm thư mục bin vào PATH cho pipeline/stage tương ứng.

### Scripted Pipeline

Với Scripted Pipeline, tool step trả về đường dẫn home của JDK. Cần tự thêm vào environment:

~~~groovy
node {
    def jdkHome = tool name: 'Temurin-21', type: 'jdk'

    withEnv([
        'JAVA_HOME=' + jdkHome,
        'PATH+JDK=' + jdkHome + '/bin'
    ]) {
        sh 'java --version'
        sh 'javac --version'
        sh './mvnw --batch-mode verify'
    }
}
~~~

Trên Windows agent, dùng bat và %JAVA_HOME%\bin theo cú pháp Windows.

### Nhiều Jenkins agent

Một logical JDK có thể nằm ở path khác nhau trên Linux và Windows agent. Cấu hình Tool Locations per agent để Jenkins biết đúng home trên từng node.

Với agent container hoặc ephemeral agent, auto-install có thể phải tải lại JDK mỗi lần container mới được tạo. Nếu startup time đáng kể, bake JDK vào custom agent image rồi đăng ký nó như pre-installed tool.

## 11. Cài JDK bằng container image

Container image là một cách đóng gói môi trường CI. Nếu image đã có JDK, pipeline không cần cài JDK trong mỗi bước.

Ví dụ Dockerfile cho build stage:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build

WORKDIR /workspace
COPY . .

RUN java --version
RUN javac --version
RUN ./mvnw --batch-mode verify
~~~

Nếu image JDK không có Maven, dùng Maven Wrapper hoặc chọn Maven image có JDK phù hợp. Build stage dùng JDK; runtime stage có thể dùng image runtime nhẹ hơn nếu chỉ chạy artifact.

Ví dụ multi-stage:

~~~dockerfile
FROM maven:3-eclipse-temurin-21-noble AS build
WORKDIR /workspace
COPY . .
RUN mvn --batch-mode --no-transfer-progress verify package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/app.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

Tên file app.jar là ví dụ; thay bằng artifact thực tế của project. Build image cần JDK vì có compiler; runtime image có thể dùng runtime phù hợp với cách đóng gói ứng dụng.

### Pin image và cập nhật bảo mật

Tag dễ đọc nhưng có thể trỏ tới image mới sau này. Nếu cần tái lập tuyệt đối, pin digest:

~~~dockerfile
FROM eclipse-temurin:21-jdk@sha256:<verified-image-digest>
~~~

Digest phải lấy từ registry đáng tin cậy cho đúng OS/architecture. Không sao chép digest từ image khác hoặc kiến trúc khác.

Dù pin digest, vẫn cần quy trình cập nhật image để nhận security fixes. Pin là để kiểm soát thời điểm nâng cấp, không phải để giữ mãi image cũ có lỗ hổng.

## 12. Cài JDK thủ công từ archive

Cài thủ công hữu ích khi runner không có action/task phù hợp, môi trường offline hoặc chỉ truy cập internal artifact repository, cần JDK build tùy chỉnh, cần kiểm soát chính xác package/checksum hoặc cần chuẩn bị JDK trước khi job chạy.

Ví dụ Linux với archive .tar.gz:

~~~bash
set -eu

if [ -z "$JDK_ARCHIVE_URL" ] || [ -z "$JDK_SHA256" ]; then
  echo "Set trusted JDK_ARCHIVE_URL and JDK_SHA256" >&2
  exit 1
fi

mkdir -p "$RUNNER_TEMP/jdk"
curl --fail --location --silent --show-error \
  "$JDK_ARCHIVE_URL" \
  --output "$RUNNER_TEMP/jdk.tar.gz"

printf '%s  %s\n' "$JDK_SHA256" "$RUNNER_TEMP/jdk.tar.gz" \
  | sha256sum --check --strict

tar -xzf "$RUNNER_TEMP/jdk.tar.gz" \
  --directory "$RUNNER_TEMP/jdk" \
  --strip-components=1

export JAVA_HOME="$RUNNER_TEMP/jdk"
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
~~~

Đoạn lệnh giả định archive có một thư mục gốc duy nhất và bin nằm bên dưới thư mục đó. Kiểm tra cấu trúc archive của vendor trước khi dùng --strip-components=1; nếu layout khác, điều chỉnh lệnh giải nén.

### Xác minh checksum

Không tải JDK từ URL không rõ nguồn. Lấy SHA-256 hoặc signature từ trang phát hành/repository chính thức của vendor, sau đó so khớp với file đã tải.

Eclipse Temurin cung cấp file checksum SHA-256 bên cạnh archive. Ví dụ trên nhận checksum qua biến JDK_SHA256; giá trị phải được lấy từ metadata tin cậy của đúng file, version, OS và architecture.

Checksum giúp phát hiện file bị thay đổi hoặc hỏng trong quá trình tải. Nếu tổ chức yêu cầu xác thực nguồn phát hành, dùng thêm chữ ký số và public key được xác minh theo quy trình của vendor.

### Dùng package manager của Linux

Trên runner Linux có repository phù hợp, có thể cài package JDK bằng package manager của OS. Ví dụ Ubuntu:

~~~bash
sudo apt-get update
sudo apt-get install --yes openjdk-21-jdk

java --version
javac --version
~~~

Package có thể khác theo phiên bản Ubuntu, repository và kiến trúc. Với build release, hãy kiểm soát repository/package version hoặc dùng installer/image có version rõ ràng để tránh môi trường thay đổi bất ngờ.

## 13. Build tool runtime và Java toolchains

Cài JDK vào CI giải quyết câu hỏi “máy có Java nào?”. Java toolchain giải quyết câu hỏi “task compile/test nào phải dùng JDK nào?”.

Hai cơ chế có liên quan nhưng khác nhau.

### Gradle toolchains

Trong build.gradle:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Trong ví dụ:

- Java toolchain yêu cầu JDK 21 cho các task Java.
- options.release = 17 giới hạn API và bytecode đầu ra ở Java 17.
- JDK chạy Gradle daemon có thể khác compiler toolchain nếu môi trường có nhiều JDK và Gradle được cấu hình phù hợp.

Nếu JDK 21 đã được cài qua CI action hoặc container image, Gradle có thể phát hiện toolchain đó. Gradle cũng hỗ trợ tự provision toolchain khi đã cấu hình toolchain download repository/resolver phù hợp; không mặc định rằng mọi CI build đều tự tải được JDK nếu thiếu cấu hình resolver.

### Maven toolchains

Maven có thể chạy bằng một JDK nhưng yêu cầu compiler/test plugin dùng JDK khác.

Một project có thể khai báo Maven Toolchains Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <goals>
                <goal>toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>21</version>
                <vendor>temurin</vendor>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

Trên máy/agent, file ~/.m2/toolchains.xml ánh xạ requirement sang JDK home:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdk/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Đường dẫn /opt/jdk/temurin-21 là ví dụ; thay bằng thư mục cài thật trên agent. Toolchain chỉ chọn một JDK đã tồn tại; nó không tự cài JDK vào máy.

Một số installer, trong đó có setup-java, có thể tạo Maven toolchains entry cho các JDK đã cài. Nếu dùng chức năng này, kiểm tra version/vendor trong entry có khớp requirement mà POM yêu cầu hay không.

### --release không thay thế việc cài đúng JDK

--release 17 yêu cầu compiler tạo bytecode/API tương thích Java 17. Nó không tự cài compiler JDK 17 và cũng không thay đổi JVM chạy Maven/Gradle.

Nếu cần kiểm thử ứng dụng trên Java 17, hãy chạy test JVM bằng JDK 17 hoặc toolchain launcher 17. Compile thành bytecode 17 trên JDK 21 không thay thế được runtime test trên Java 17.

## 14. Matrix build và kiểm tra tương thích

Matrix cho phép chạy cùng source trên nhiều JDK. Đây là cách tốt để kiểm tra compatibility và phát hiện sớm thay đổi behavior giữa các release.

Ví dụ ma trận mục tiêu:

| Job | JDK | Mục tiêu |
|---|---:|---|
| Compatibility minimum | 17 | Xác nhận project còn hỗ trợ baseline |
| Primary build | 21 | Phiên bản build/runtime chính |
| Forward compatibility | 25 | Phát hiện vấn đề khi nâng JDK |

Không nhất thiết phải chạy toàn bộ integration suite trên mọi version. Có thể chạy unit test trên tất cả version và chạy integration/performance suite trên version chính, tùy thời gian và chính sách project.

Nếu một pipeline cần compile bằng JDK 21 nhưng kiểm tra runtime trên Java 17, có thể tách job:

- Build job cài compiler/toolchain 21.
- Runtime test job cài JDK 17.
- Cùng artifact được chuyển qua pipeline artifact giữa các job.

Nhớ rằng job thường chạy trên agent/container riêng. Artifact truyền qua job là file build output; nó không mang theo JDK đã cài của job trước.

## 15. Cache JDK và cache dependency

Hai loại cache thường bị nhầm:

- **JDK cache:** lưu bộ JDK đã tải để job sau không phải tải lại.
- **Dependency cache:** lưu Maven repository hoặc Gradle caches để tránh tải lại thư viện.

Ví dụ setup-java:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '21'
    cache: maven
~~~

Action cache dependency Maven và wrapper; khi dependency cache được bật, JDK installation cache cũng được bật theo mặc định, trừ khi override.

Trong GitLab, cache:paths cho .m2/repository hoặc Gradle cache là dependency cache. Docker image pull/cache là cơ chế riêng của runner/registry.

### Cache key nên thay đổi khi nào?

Dependency cache key nên phụ thuộc vào file quản lý dependency/wrapper như pom.xml, gradle.lockfile, gradle-wrapper.properties hoặc version catalog phù hợp.

JDK cache identity nên phân biệt OS, architecture, vendor/distribution, package type và version. Không dùng chung JDK cache giữa architecture hoặc vendor khác nhau.

Cache chỉ là tối ưu hiệu năng. Pipeline phải vẫn build được khi cache miss hoặc cache bị xóa.

## 16. Bảo mật và khả năng tái lập

JDK là thành phần quan trọng của build supply chain. Một pipeline có thể bị ảnh hưởng nếu tải nhầm archive, dùng action bị thay đổi hoặc lấy container image không đúng.

Các thực hành nên áp dụng:

1. Chọn distribution và nguồn tải được tổ chức tin cậy.
2. Ghi rõ JDK version, vendor, OS và architecture.
3. Xác minh checksum; xác minh signature nếu quy trình yêu cầu.
4. Dùng CI action chính thức hoặc action đã được review.
5. Với GitHub Actions, pin action vào full-length commit SHA theo chính sách bảo mật; tag major dễ đọc nhưng có thể được di chuyển.
6. Với container, pin digest khi cần image bất biến.
7. Quản lý JDK archive nội bộ qua artifact repository hoặc mirror có kiểm soát.
8. Không lưu private key, token hay credential trong Dockerfile, command line hoặc build log.
9. Cập nhật JDK định kỳ để nhận security fixes.
10. Giới hạn quyền của pipeline, đặc biệt với pull request từ fork.

Không nên tắt xác minh checksum/signature chỉ để pipeline chạy qua lỗi tải. Xác định đúng nguồn lỗi, metadata và key trước khi thay đổi chính sách xác minh.

## 17. Kiểm tra JDK trên các hệ điều hành

### Linux

~~~bash
echo "$JAVA_HOME"
command -v java
command -v javac
java --version
javac --version
~~~

Đường dẫn JDK thường có dạng /usr/lib/jvm/... hoặc thư mục tool cache của CI provider.

### macOS

~~~bash
/usr/libexec/java_home -V
echo "$JAVA_HOME"
java --version
javac --version
~~~

/usr/libexec/java_home có thể liệt kê các JDK được macOS nhận diện. Với CI action, dùng biến JAVA_HOME mà action cung cấp thay vì tự đoán đường dẫn cài.

### Windows

~~~powershell
Write-Output $env:JAVA_HOME
where.exe java
where.exe javac
java --version
javac --version
~~~

Nếu dùng self-hosted Windows runner, kiểm tra PATH không ưu tiên một Java cũ nằm trước JDK vừa cài. Tránh sửa PATH toàn máy nếu chỉ cần cấu hình cho job.

## 18. Ví dụ smoke test xác nhận JDK thực sự compile và chạy được

Tạo file CiJdkCheck.java:

~~~java
public class CiJdkCheck {
    public static void main(String[] args) {
        if (Runtime.version().feature() < 17) {
            throw new IllegalStateException("Java 17 or newer is required");
        }

        System.out.println("JDK_READY");
    }
}
~~~

Biên dịch bằng JDK đã cài:

~~~bash
javac --release 17 -d out CiJdkCheck.java
~~~

Chạy:

~~~bash
java -cp out CiJdkCheck
~~~

Stdout chính xác:

~~~text
JDK_READY
~~~

Chương trình xác nhận compiler có thể biên dịch source với release 17 và runtime hiện tại có feature version từ 17 trở lên. Lệnh java --version và javac --version vẫn nên được lưu trong CI log để biết chính xác version thực tế.

Nếu smoke test pass nhưng project build fail, nguyên nhân có thể nằm ở Maven/Gradle, plugin, dependency, source compatibility hoặc toolchain configuration.

## 19. Lỗi thường gặp và cách xử lý

### java: command not found

**Nguyên nhân:** JDK chưa được cài, PATH chưa có JDK bin, hoặc step đang chạy trong container khác với container đã cài Java.

**Cách xử lý:** xác nhận job image/runner; kiểm tra JAVA_HOME; thêm JAVA_HOME/bin vào PATH; kiểm tra setup action/task đã chạy trước build step.

### javac: command not found

**Nguyên nhân:** chỉ có runtime image/JRE, package JDK thiếu compiler hoặc PATH trỏ tới runtime khác.

**Cách xử lý:** cài JDK đầy đủ; kiểm tra JAVA_HOME/bin/javac; chọn image có hậu tố JDK thay vì JRE; xác minh javac --version.

### JAVA_HOME is not defined correctly

**Nguyên nhân:** biến trỏ vào thư mục bin, file executable hoặc thư mục không tồn tại.

**Cách xử lý:** đặt JAVA_HOME về root JDK; xác nhận tồn tại JAVA_HOME/bin/java và JAVA_HOME/bin/javac; dùng cú pháp path phù hợp OS.

### java và javac khác version

**Nguyên nhân:** PATH có nhiều JDK và thứ tự ưu tiên sai; JAVA_HOME và PATH không cùng trỏ một installation.

**Cách xử lý:** in command -v/where.exe; gọi trực tiếp binary trong JAVA_HOME/bin; sửa PATH hoặc toolchain; chạy lại verify trước build.

### Maven chạy bằng JDK khác compiler

**Nguyên nhân:** Maven runtime lấy từ JAVA_HOME, nhưng compiler plugin dùng Maven Toolchains hoặc compiler executable khác.

**Cách xử lý:** xem mvn --version; kiểm tra ~/.m2/toolchains.xml; kiểm tra Maven Toolchains Plugin và compiler plugin; xác nhận version/vendor requirement khớp toolchain entry.

### Gradle chạy bằng JDK không mong muốn

**Nguyên nhân:** JAVA_HOME, Gradle daemon JVM criteria hoặc project toolchain chỉ định version khác nhau.

**Cách xử lý:** xem ./gradlew --version; kiểm tra Gradle daemon JVM criteria và Java toolchain; dừng daemon cũ sau khi thay đổi runtime nếu cần; xác nhận compiler/test launcher được chọn đúng.

### CI cài JDK thành công nhưng step sau không thấy

**Nguyên nhân:** biến được export trong một shell step không tồn tại ở step mới; job sau chạy trên agent khác; container mới không chứa JDK.

**Cách xử lý:** dùng cơ chế truyền environment của CI provider; cài/setup JDK trong từng job; dùng cùng image hoặc tool installation được quản lý; không dựa vào filesystem của job trước.

### Hosted runner có JDK trên máy developer nhưng CI không có

**Nguyên nhân:** runner image khác OS/version hoặc danh sách pre-installed tool đã thay đổi.

**Cách xử lý:** yêu cầu version bằng setup action/task; in java --version; không dựa vào version mặc định của runner.

### Container có JDK nhưng không có Maven/Gradle

**Nguyên nhân:** image JDK chỉ chứa Java tools.

**Cách xử lý:** dùng Maven/Gradle Wrapper; chọn build image có Maven/Gradle phù hợp; hoặc cài build tool theo version đã pin.

### Lỗi architecture hoặc Exec format error

**Nguyên nhân:** tải JDK cho ARM64 nhưng runner là x64, hoặc ngược lại.

**Cách xử lý:** kiểm tra architecture của runner/container; chọn đúng package; với Docker multi-architecture, xác nhận image manifest hỗ trợ platform cần chạy.

### TLS/certificate error khi tải JDK

**Nguyên nhân:** proxy, internal CA, certificate inspection hoặc truststore không đúng.

**Cách xử lý:** cấu hình proxy và CA theo chính sách tổ chức; dùng mirror nội bộ; không tắt TLS verification như cách sửa mặc định.

### JDK archive giải nén nhưng không chạy

**Nguyên nhân:** archive hỏng, checksum sai, layout không như giả định, quyền execute thiếu hoặc package không phù hợp OS/libc.

**Cách xử lý:** kiểm tra checksum; xem nội dung archive; đặt đúng JAVA_HOME; kiểm tra quyền execute và architecture; dùng package phù hợp runner.

### Pipeline dùng latest và kết quả thay đổi

**Nguyên nhân:** alias hoặc image tag có thể trỏ tới release mới theo thời gian.

**Cách xử lý:** pin feature/patch version hoặc image digest theo yêu cầu reproducibility; chủ động nâng version qua pull request; chạy compatibility matrix.

### JDK mới làm build cũ thất bại

**Nguyên nhân:** Gradle/Maven wrapper, plugin, annotation processor hoặc dependency chưa tương thích JDK mới.

**Cách xử lý:** kiểm tra ma trận tương thích của build tool/plugin; tách JDK chạy build khỏi compiler toolchain khi phù hợp; nâng plugin có kiểm soát; giữ version CI đã được xác nhận cho đến khi migration hoàn tất.

## 20. Quy trình chuẩn để thêm JDK vào CI

1. Xác định Java release mà project cần hỗ trợ.
2. Chọn vendor/distribution và architecture được phê duyệt.
3. Xác định runner là hosted, self-hosted hay container.
4. Chọn action/task, pre-installed tool hoặc container image.
5. Đặt version và cấu hình JAVA_HOME/PATH.
6. Chạy java --version và javac --version.
7. Chạy mvn --version hoặc ./gradlew --version.
8. Kiểm tra compiler/test toolchain nếu project dùng nhiều JDK.
9. Chạy build wrapper và test suite.
10. Cache dependency/JDK sau khi xác định cache key phù hợp.
11. Pin action/image/archive theo chính sách reproducibility.
12. Lưu log version trong CI artifact để có thể truy vết.

Một thay đổi CI tốt nên dễ đọc: reviewer nhìn YAML là biết JDK vendor/version, nguồn cài, build command và cách verify.

## 21. Checklist trước khi merge cấu hình CI

### JDK selection

- [ ] Đã xác định feature release cần dùng.
- [ ] Đã chọn vendor/distribution rõ ràng.
- [ ] Đã chọn đúng OS và architecture.
- [ ] Có chính sách patch update và support.
- [ ] Không phụ thuộc version mặc định không được kiểm soát của runner.

### Installation

- [ ] JDK được cài trong đúng job/container.
- [ ] Package có javac nếu cần compile.
- [ ] JAVA_HOME trỏ tới root JDK.
- [ ] PATH ưu tiên đúng JDK.
- [ ] Biến môi trường tồn tại trong các step cần dùng.
- [ ] Checksum/signature được xác minh khi tải archive.

### Build

- [ ] java --version và javac --version được ghi trong log.
- [ ] Maven/Gradle chạy bằng JVM mong muốn.
- [ ] Toolchain compile/test chọn đúng JDK.
- [ ] Java release target được phân biệt với compiler JDK.
- [ ] Wrapper được commit và sử dụng.
- [ ] Test/build pass trên runner thật.

### Operations and security

- [ ] Action được review và pin theo policy.
- [ ] Container image tag/digest được quản lý.
- [ ] Cache không phải dependency bắt buộc để build thành công.
- [ ] JDK security update có lịch kiểm tra.
- [ ] Không ghi secret vào YAML/log/image layer.
- [ ] Self-hosted agent có quy trình cập nhật và dọn tool cũ.

## 22. Tài liệu tham khảo chính thức

- [actions/setup-java — GitHub](https://github.com/actions/setup-java) — cài Java distribution, chọn version, thiết lập JAVA_HOME/PATH, cache và hỗ trợ nhiều JDK.
- [GitHub Actions: Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use) — pin action theo full-length commit SHA và kiểm soát workflow dependency.
- [GitLab CI/CD YAML syntax](https://docs.gitlab.com/ci/yaml/) — cấu hình image, cache, variables và job script.
- [Run CI/CD jobs in Docker containers — GitLab](https://docs.gitlab.com/ci/docker/using_docker_images/) — cách job dùng Docker image.
- [Eclipse Temurin Official Image](https://hub.docker.com/_/eclipse-temurin) — JDK image và supported architectures.
- [JavaToolInstaller@1 — Microsoft Learn](https://learn.microsoft.com/en-us/azure/devops/pipelines/tasks/reference/java-tool-installer-v1) — chọn JDK từ PreInstalled, LocalDirectory hoặc Azure Storage và thiết lập JAVA_HOME.
- [Managing Tools — Jenkins](https://www.jenkins.io/doc/book/managing/tools/) — cấu hình JDK pre-installed/auto-install và tool locations trên agent.
- [Jenkins Pipeline Syntax](https://www.jenkins.io/doc/book/pipeline/syntax/) — Declarative Pipeline tools directive.
- [Toolchains for JVM projects — Gradle](https://docs.gradle.org/current/userguide/toolchains.html) — chọn compiler, launcher và Javadoc tool theo JDK version.
- [Guide to Using Toolchains — Maven](https://maven.apache.org/guides/mini/guide-using-toolchains) — chọn JDK riêng cho compiler và các plugin toolchain-aware.
- [Archive Installation — Eclipse Adoptium](https://adoptium.net/installation/archives) — cài Temurin archive và xác minh SHA-256 checksum.

Cài JDK trong CI không chỉ là làm cho lệnh java chạy được. Pipeline phải chọn đúng distribution/version, cung cấp compiler khi cần, đặt JAVA_HOME và PATH nhất quán, đồng thời bảo đảm Maven/Gradle dùng đúng toolchain. Hãy verify version ngay sau bước setup và giữ cấu hình có thể tái lập để mọi runner build cùng một project theo chính sách Java đã chọn.
