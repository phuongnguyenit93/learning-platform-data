# Cache JDK trong CI/CD

**Cache JDK** là cách lưu lại bộ cài Java Development Kit đã tải về để các lần chạy CI/CD sau có thể dùng lại mà không phải tải và giải nén lại từ đầu. Việc này giảm thời gian chuẩn bị runner, nhất là khi pipeline chạy trên máy mới, runner ngắn hạn hoặc cần nhiều phiên bản JDK.

Cache JDK chỉ là tối ưu thời gian khởi tạo môi trường. Pipeline vẫn phải chạy đúng JDK đã khai báo, xác minh được vendor, version và architecture, đồng thời có thể tải lại bộ cài khi cache miss. Một cache không tồn tại, bị xóa hoặc không tương thích không được làm thay đổi kết quả build.

## 1. Phân biệt các loại cache liên quan tới Java

Trong CI/CD có nhiều lớp lưu trữ dễ bị gọi chung là “Java cache”, nhưng chúng chứa dữ liệu khác nhau:

| Loại | Nội dung | Mục đích |
|---|---|---|
| **Runner tool cache** | JDK đã cài sẵn trên runner hoặc được cài trong job | Dùng lại toolchain ngay trên runner |
| **JDK installation cache** | Bộ JDK đã tải và giải nén, được lưu giữa các lần chạy | Bỏ qua download/extract khi runner mới cần cùng JDK |
| **Dependency cache** | Maven local repository, Gradle dependency cache, sbt/Ivy cache | Tránh tải lại thư viện của project |
| **Build cache** | Kết quả task/compile có thể tái sử dụng | Tránh thực hiện lại tác vụ build đã có kết quả hợp lệ |
| **Container image layers** | Hệ điều hành, JDK và công cụ đã đóng gói trong image | Chuẩn hóa toolchain và tái sử dụng các layer của image |
| **Artifacts** | JAR, WAR, báo cáo test, binary đầu ra | Chuyển kết quả build giữa các job/stage hoặc lưu làm đầu ra |

Không nên gộp JDK vào Maven/Gradle dependency cache. JDK là toolchain của runner; thư viện Maven/Gradle là đầu vào của project. Hai lớp có vòng đời, kích thước, khóa cache và cách xác minh khác nhau.

Ví dụ, **actions/setup-java** có thể quản lý cả JDK cache và dependency cache. Khi bật dependency cache, JDK cache cũng được bật mặc định ở phiên bản action hiện tại, trừ khi cấu hình **cache-jdk: false**. Điều này không có nghĩa hai loại cache là một: chúng được lưu trong các cache entry riêng.

## 2. Khi nào cache JDK có ích?

Cache JDK thường hữu ích trong các trường hợp:

- GitHub Actions dùng hosted runner mới cho mỗi job và phải cài JDK không có sẵn trong tool cache.
- Self-hosted runner hoặc runner autoscale thường xuyên được tạo mới.
- Pipeline sử dụng nhiều JDK/vendor/architecture và mỗi lần đều phải tải bộ cài lớn.
- Một JDK tùy biến được phân phối từ repository nội bộ.
- Các job matrix cần cùng một JDK identity trên nhiều lần chạy.

Cache có thể ít có ích khi runner đã cài sẵn đúng JDK trong tool cache, image đã chứa JDK, hoặc thời gian download/extract rất nhỏ so với tổng thời gian build. Cache còn có chi phí upload, download, lưu trữ và eviction. Hãy đo cold run và warm run trước khi bổ sung thêm một lớp cache.

## 3. GitHub Actions: dùng actions/setup-java

**actions/setup-java** cài JDK được yêu cầu, thiết lập JAVA_HOME và thêm Java vào PATH. Action tìm runner tool cache trước. Nếu runner đã có JDK phù hợp về version, distribution, package type và architecture, action có thể dùng bản cài sẵn mà không tải lại.

GitHub-hosted runner có một số bản Eclipse Temurin cài sẵn. Khi yêu cầu một distribution hoặc phiên bản không có trong tool cache, action mới cần tải JDK. Với JDK đã tải, tùy chọn cache-jdk cho phép lưu installation để các lần chạy sau khôi phục lại.

### 3.1. Chỉ cache JDK, không cache dependencies

Ví dụ workflow chỉ cần cache JDK Temurin 21:

~~~yaml
name: Java CI

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'
          cache-jdk: true

      - name: Verify selected JDK
        run: |
          java -version
          javac -version

      - name: Build
        run: mvn --batch-mode verify
~~~

Ở ví dụ này:

- distribution: temurin chọn Eclipse Temurin.
- java-version: '21' yêu cầu dòng Java 21.
- cache-jdk: true bật cache của JDK đã tải.
- Không có cache: maven, nên Maven dependency cache không được bật bởi setup-java.

### 3.2. Cache cả JDK và Maven dependencies

Nếu project dùng Maven, có thể bật dependency cache:

~~~yaml
steps:
  - uses: actions/checkout@v7

  - uses: actions/setup-java@v6
    with:
      distribution: temurin
      java-version: '21'
      cache: maven

  - run: mvn --batch-mode verify
~~~

Trong setup-java@v6, cache: maven bật Maven dependency cache và JDK cache theo mặc định. Hai cache vẫn là hai entry riêng. Maven cache chứa thư viện đã tải, còn JDK cache chứa installation của Java.

Nếu muốn giữ Maven cache nhưng không lưu JDK:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '21'
    cache: maven
    cache-jdk: false
~~~

Nếu muốn chỉ cache JDK mà không cache dependency, bỏ cache và đặt cache-jdk: true.

### 3.3. Ma trận hành vi của cache-jdk

| cache | cache-jdk | Dependency/wrapper cache | JDK cache |
|---|---|---|---|
| Không đặt | Không đặt | Tắt | Tắt |
| Không đặt | true | Tắt | Bật |
| Không đặt | false | Tắt | Tắt |
| maven / gradle / sbt | Không đặt | Bật | Bật |
| Có đặt | true | Bật | Bật |
| Có đặt | false | Bật | Tắt |

cache-jdk: false chỉ tắt JDK cache; nó không tắt dependency cache đã được bật bằng cache: maven hoặc cache: gradle.

### 3.4. Cache key của JDK được phân tách như thế nào?

setup-java xây cache identity theo nhiều thuộc tính để không dùng nhầm bộ JDK:

- Runner operating system.
- Architecture đã chuẩn hóa.
- Java distribution/vendor.
- Package type, ví dụ JDK hoặc JRE.
- Phiên bản Java đã resolve chính xác.
- Release identity, thường là checksum có thẩm quyền nếu vendor cung cấp.
- Identity của chế độ xác minh chữ ký.

Vì vậy, JDK 21 Temurin Linux x64 khác với JDK 21 Temurin Windows x64, Zulu Linux x64 hoặc một JDK package type khác. Một build matrix chạy nhiều hệ điều hành, architecture, vendor hay version sẽ tạo nhiều cache entry riêng và tiêu thụ thêm dung lượng cache.

Cache dependency có key khác. Với Maven/Gradle, action tạo key từ OS, architecture, package manager và hash của các file mô tả dependency. Ví dụ Maven key mặc định xét pom.xml, Maven wrapper properties và extensions; Gradle key xét build files, wrapper properties, gradle.properties và version catalog liên quan.

### 3.5. Chọn phiên bản cố định hay phiên bản mới nhất?

java-version: '21' chọn dòng Java 21; patch/build được resolve theo metadata và tool cache của runner. Khi cần build tái lập chặt chẽ, hãy pin version cụ thể thay vì chỉ dùng major version hoặc latest.

check-latest: true yêu cầu action kiểm tra metadata mới nhất thỏa version spec trước khi chọn bản cài. java-version: latest cũng là lựa chọn floating. Chúng hữu ích khi muốn nhận patch mới thường xuyên, nhưng có thể khiến cùng commit dùng patch JDK khác ở hai thời điểm khác nhau.

force-download: true buộc tải lại thay vì dùng runner tool cache hoặc JDK cache restore. Chỉ dùng khi cần kiểm tra lại archive hoặc thay đổi nội dung archive tùy biến mà version label không đổi; đây không phải tùy chọn tối ưu cho mọi build.

### 3.6. Dùng cache read-only cho job không đáng tin cậy

Với pull request từ fork hoặc các job matrix chỉ cần đọc cache, có thể bật:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '21'
    cache: maven
    cache-read-only: true
~~~

cache-read-only: true cho phép khôi phục cache nhưng không lưu thay đổi ở bước post-job. Điều này hữu ích cho job kiểm thử ngắn hạn, pull request hoặc nhiều job chạy song song cùng đọc cache đã được seed trước.

Với workflow có một job chuẩn bị cache và nhiều job kiểm thử, job seed có thể tải dependency cần thiết; các job fan-out dùng cache read-only để tránh nhiều job cùng cố ghi một key. Cache miss vẫn phải được xử lý bằng bước tải/cài bình thường.

### 3.7. Xác minh JDK thực tế sau khi setup

Không chỉ nhìn tên input trong YAML. Hãy kiểm tra JDK mà build step thực sự sử dụng:

~~~sh
java -version
javac -version
java -XshowSettings:properties -version
~~~

Các giá trị hữu ích:

- java.version: version đang chạy.
- java.vendor: vendor.
- os.arch: architecture.
- java.home: thư mục JDK/JRE đang được chọn.

Trên Linux có thể xem đường dẫn executable:

~~~sh
command -v java
command -v javac
echo "$JAVA_HOME"
~~~

Trên Windows PowerShell:

~~~powershell
Get-Command java
Get-Command javac
$env:JAVA_HOME
~~~

Nếu java chạy đúng version nhưng javac không tồn tại, runner có thể đang dùng JRE thay vì JDK, hoặc PATH chưa trỏ tới đúng installation.

## 4. GitLab CI/CD: cache JDK như thế nào?

GitLab CI cache là các file hoặc thư mục được job tải xuống và lưu lại cho những job/pipeline sau. Đường dẫn trong cache:paths phải nằm trong project directory; cache và artifact không thể trỏ trực tiếp tới một thư mục ngoài workspace như /opt/jdk.

Vì vậy, với GitLab có ba cách phổ biến:

1. Cài JDK sẵn trên runner và giữ runner/tool directory bền vững.
2. Dùng container image đã đóng gói đúng JDK, pin version hoặc digest.
3. Nếu runner ngắn hạn và cần tải archive nhiều lần, cache file archive trong project directory, xác minh checksum rồi giải nén vào workspace của job.

Cách thứ hai thường đơn giản nhất khi runner dùng Docker executor: image xác định sẵn JDK và toolchain. Cache GitLab tiếp tục dùng cho Maven/Gradle dependencies. Không cần đóng gói lại cả JDK vào cache mỗi lần nếu image layer đã được lưu tại registry/runner.

### 4.1. Ví dụ GitLab: dùng image có JDK, cache Maven dependencies

Ví dụ image nội bộ đã được build với JDK 21:

~~~yaml
image: registry.example.com/ci/temurin-21:21.0.6_7-jdk

variables:
  MAVEN_OPTS: "-Dmaven.repo.local=$CI_PROJECT_DIR/.m2/repository"

cache:
  key:
    files:
      - pom.xml
      - .mvn/wrapper/maven-wrapper.properties
  paths:
    - .m2/repository/
  policy: pull-push

build:
  stage: build
  script:
    - java -version
    - javac -version
    - ./mvnw --batch-mode verify
~~~

Image chứa JDK; cache chỉ chứa Maven repository. Tag image trong ví dụ là minh họa cho một image đã được quản lý trong registry của tổ chức. Với môi trường production, nên pin image bằng digest hoặc một tag bất biến và cập nhật có kiểm soát.

### 4.2. Ví dụ GitLab: cache JDK archive trong project directory

Nếu không dùng image có JDK và runner thường xuyên bị tạo mới, có thể cache archive JDK trong workspace. Ví dụ dưới đây chỉ dành cho Linux x64; cần khai báo JDK_URL và JDK_SHA256 thành CI/CD variables từ nguồn phát hành đáng tin cậy.

~~~yaml
variables:
  JDK_ARCHIVE: ".cache/jdk/temurin-21.0.6_7-linux-x64.tar.gz"

cache:
  key: "jdk-linux-amd64-temurin-21.0.6_7"
  paths:
    - .cache/jdk/temurin-21.0.6_7-linux-x64.tar.gz
  policy: pull-push

build:
  image: ubuntu:24.04
  stage: build
  script:
    - mkdir -p .cache/jdk
    - if [ ! -f "$JDK_ARCHIVE" ]; then curl --fail --location "$JDK_URL" --output "$JDK_ARCHIVE"; fi
    - echo "$JDK_SHA256  $JDK_ARCHIVE" | sha256sum --check -
    - mkdir -p .jdk
    - tar -xzf "$JDK_ARCHIVE" -C .jdk --strip-components=1
    - export JAVA_HOME="$CI_PROJECT_DIR/.jdk"
    - export PATH="$JAVA_HOME/bin:$PATH"
    - java -version
    - javac -version
    - ./mvnw --batch-mode verify
~~~

Cách hoạt động:

1. Runner khôi phục archive nếu cache key có sẵn.
2. Nếu chưa có archive, job tải file từ URL đã cấu hình.
3. sha256sum --check xác minh nội dung archive trước khi giải nén.
4. JDK được giải nén vào .jdk bên trong workspace.
5. JAVA_HOME và PATH được thiết lập cho các lệnh tiếp theo.
6. GitLab lưu archive theo cache key khi job hoàn tất.

Ví dụ này cache **archive**, không cache thư mục cài đặt ngoài workspace. Mỗi job vẫn giải nén archive vào .jdk. Điều này tránh phụ thuộc vào một đường dẫn cài đặt nằm ngoài project directory và giúp key cache thể hiện rõ OS, architecture, vendor và version.

Nếu checksum thay đổi, hãy cập nhật cache key hoặc version để archive mới không dùng lại entry cũ. Không bỏ qua kiểm tra checksum chỉ để tránh cache miss.

### 4.3. Giới hạn chia sẻ cache giữa các runner

Cache GitLab không bảo đảm luôn có sẵn. Nếu job tiếp theo chạy trên runner khác, cache local của runner trước có thể không tồn tại ở runner mới. Muốn chia sẻ qua nhiều runner, cần cấu hình distributed cache (ví dụ object storage) hoặc dùng các runner cùng chia sẻ cache storage có cùng kiến trúc.

GitLab mặc định tách cache của protected và non-protected branches. Đây là ranh giới bảo mật; không tắt tách biệt này nếu người có quyền chạy pipeline trên branch không được tin cậy.

Cache key có thể dựa trên file bằng cache:key:files. Với cache dependency, dùng pom.xml hoặc lockfile để key thay đổi khi dependency thay đổi. Với JDK archive, key nên chứa version và platform; nếu archive được thay bằng nội dung khác, hãy đổi key hoặc version.

## 5. Jenkins: tái sử dụng JDK trên agent

Jenkins quản lý JDK như một build tool. Quản trị viên khai báo JDK trong **Manage Jenkins → Tools** và đặt một tên logic, ví dụ temurin-21. Agent có thể dùng JDK cài sẵn hoặc auto-install archive khi job lần đầu cần tới tool.

Với auto-install, Jenkins đặt tool dưới thư mục <remote-fs-root>/tools/ trên agent. Các build tiếp theo trên cùng agent có thể dùng lại installation hiện có nếu archive không thay đổi. JDK installer cụ thể có thể cần plugin; Jenkins core không tự cung cấp downloader riêng cho mọi distribution.

### 5.1. Khai báo JDK trong Declarative Pipeline

Sau khi quản trị viên đã cấu hình tool tên temurin-21:

~~~groovy
pipeline {
    agent any

    tools {
        jdk 'temurin-21'
    }

    stages {
        stage('Verify JDK') {
            steps {
                sh 'java -version'
                sh 'javac -version'
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

Declarative tools directive thiết lập JAVA_HOME và đưa thư mục bin vào PATH. Trên Windows agent, dùng bat thay cho sh.

Nếu agent là persistent machine, tool installation được tái sử dụng giữa các build. Nếu agent được tạo mới rồi xóa sau mỗi job, thư mục tool cache cũng biến mất. Khi đó nên dùng image đã cài JDK hoặc một persistent tool volume thay vì kỳ vọng local cache tự tồn tại.

### 5.2. Jenkins với ephemeral container agents

Khi Jenkins chạy agent bằng container ngắn hạn, có thể tạo image build chứa JDK và Maven/Gradle cần thiết. Pin image version/digest để các job dùng cùng toolchain. Registry và node image cache sẽ tái sử dụng image layers; dependency cache vẫn được quản lý riêng.

Không chia sẻ một thư mục JDK cài sẵn giữa các agent khác hệ điều hành hoặc architecture. Mỗi agent cần tool home hợp lệ với môi trường của chính nó.

## 6. Thiết kế cache key đúng

JDK là binary phụ thuộc nền tảng. Cache key cần đủ chi tiết để một job không khôi phục nhầm archive hoặc installation của môi trường khác.

Một key tốt nên thể hiện:

| Thành phần | Vì sao cần có |
|---|---|
| OS | Linux, Windows và macOS có layout/binary khác nhau |
| Architecture | x64 và aarch64 không thể dùng chung binary |
| Distribution/vendor | Temurin, Zulu, Corretto, Oracle và các vendor khác có release khác nhau |
| Java version/build | Tránh vô tình dùng patch/build cũ hoặc mới hơn mong muốn |
| Package type | JDK và JRE không giống nhau; build cần javac cần JDK |
| Archive checksum/release identity | Phát hiện archive đổi nội dung dù tên file không đổi |
| Signature verification mode | Không khôi phục installation từ cache có mức xác minh yếu hơn yêu cầu |

Ví dụ key có ý nghĩa:

~~~text
jdk-linux-x64-temurin-jdk-21.0.6_7-sha256-<digest>
~~~

Đây là mẫu minh họa. Với setup-java, các chiều nhận diện này được action quản lý tự động. Với GitLab cache tự cấu hình, hãy đưa các chiều phù hợp vào cache:key và đổi key khi version hoặc checksum thay đổi.

Không dùng key chung như jdk-cache cho mọi runner, vendor và version. Key quá rộng có thể khiến job khôi phục binary sai nền tảng hoặc sai toolchain.

## 7. Bảo mật và tính toàn vẹn của JDK cache

JDK là executable code được chạy trong pipeline. Nếu archive hoặc cache bị thay đổi, job có thể thực thi binary không đáng tin cậy. Cần bảo vệ cả nguồn tải, bước xác minh và quyền ghi cache.

Thực hành nên áp dụng:

- Tải JDK từ vendor hoặc repository nội bộ đã được phê duyệt.
- Xác minh checksum SHA-256 từ nguồn độc lập đáng tin cậy.
- Xác minh chữ ký package khi vendor và công cụ hỗ trợ.
- Pin version và architecture trong workflow.
- Chỉ cho branch/job đáng tin cậy tạo hoặc cập nhật cache dùng chung.
- Dùng read-only cache cho pull request hoặc job chỉ tiêu thụ cache.
- Không lưu token, credentials, private key hoặc file cấu hình bí mật trong cache.
- Không tắt kiểm tra integrity chỉ để ép cache hit.
- Có quy trình cập nhật và loại bỏ cache khi phát hiện JDK bị thu hồi hoặc có lỗ hổng.

setup-java tự xác minh checksum archive khi distribution công bố checksum có thẩm quyền. Action cũng hỗ trợ xác minh chữ ký cho một số distribution như Temurin và Microsoft; nếu yêu cầu xác minh bắt buộc, cấu hình chế độ enforce tương ứng và kiểm tra log của action.

Một điểm cần phân biệt: setup-java có thể tìm thấy JDK trong runner tool cache trước khi tải. Installation có sẵn trong tool cache không được tải lại và không có lịch sử xác minh archive được lưu cùng cache đó. Nếu quy trình yêu cầu phải tải và xác minh lại archive, hãy xem xét force-download: true và hiểu rõ chi phí tải lại.

Không chia sẻ cache giữa branch tin cậy và branch không tin cậy nếu chính sách bảo mật không cho phép. Cache là một nguồn đầu vào có thể được khôi phục vào workspace; quyền ghi cache cần được giới hạn giống như quyền ghi artifact.

## 8. Cache miss, invalidation và cleanup

Cache miss là tình huống bình thường. Job phải tiếp tục được bằng cách tải/cài JDK từ nguồn đã cấu hình. Không để build phụ thuộc tuyệt đối vào việc cache entry còn tồn tại.

Các nguyên nhân cache miss thường gặp:

- Job đổi OS hoặc architecture.
- Vendor hoặc package type thay đổi.
- JDK version/build mới làm key khác.
- Checksum hoặc release identity đổi.
- Cache đã hết hạn hoặc bị eviction.
- Runner khác không dùng chung cache storage.
- Path hoặc cache key trong workflow thay đổi.
- Cache restore bị lỗi hoặc archive không hợp lệ.

Khi cần invalidation:

1. Xác định chính xác JDK version, vendor, OS và architecture cần thay.
2. Cập nhật version hoặc checksum trong cấu hình.
3. Tạo cache key mới để job không khôi phục entry cũ.
4. Chạy một job seed để tải, xác minh và lưu JDK mới.
5. Xác minh version/vendor/architecture sau khi setup.
6. Theo dõi cache cũ và xóa theo retention policy của nền tảng nếu cần.

Không xóa toàn bộ cache chỉ vì một job có cache miss. Cache miss có thể là do key mới đúng như mong muốn. Chỉ clear cache khi xác định entry cũ bị hỏng, chứa dữ liệu không còn hợp lệ hoặc chiếm quá nhiều dung lượng.

Với GitHub Actions, cache entry có thể bị eviction nếu không được sử dụng trong thời gian retention của nền tảng. Với GitLab, quản trị viên có thể áp dụng lifecycle policy cho object storage. Jenkins tool installation được quản lý theo vòng đời agent và thư mục tools của agent.

## 9. Phân biệt JDK cache với dependency cache trong thực tế

| Triệu chứng | Lớp cần kiểm tra |
|---|---|
| Job mất thời gian tải Temurin/Corretto/Oracle JDK | Runner tool cache hoặc JDK installation cache |
| Maven tải nhiều artifact từ Maven Central | Maven local repository cache |
| Gradle tải plugin/dependency nhiều lần | Gradle dependency/build cache |
| Cài JDK lại mỗi lần Jenkins agent mới được tạo | Jenkins tool installation hoặc container image |
| GitLab job khác runner không tìm thấy archive | Distributed cache/shared runner cache |
| Java version không đúng dù cache hit | JAVA_HOME, PATH, version resolution và runner tool cache |
| javac không tồn tại | Đang dùng JRE hoặc chọn sai package type |
| Cache restore nhanh nhưng giải nén lâu | Kích thước archive, tốc độ disk và số file nhỏ |
| Build sai sau khi đổi JDK | Cache key thiếu version/vendor/architecture hoặc toolchain không được pin |

Khi build sai, hãy kiểm tra JDK thực tế trước khi xóa cache. Chạy java -version và javac -version để xác định toolchain mà job đang dùng.

## 10. Ví dụ Java 17+ xác nhận toolchain trong pipeline

Chương trình nhỏ sau in ra version, vendor, architecture và thư mục Java đang chạy. Nó giúp phát hiện workflow chọn nhầm JDK sau khi khôi phục cache hoặc thay đổi PATH.

Tạo file JdkProbe.java:

~~~java
public class JdkProbe {
    public static void main(String[] args) {
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("java.home=" + System.getProperty("java.home"));
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~sh
javac --release 17 JdkProbe.java
~~~

Chạy:

~~~sh
java JdkProbe
~~~

Ví dụ output trên JDK 24.0.2 Azul x64:

~~~text
java.version=24.0.2
java.vendor=Azul Systems, Inc.
os.arch=amd64
java.home=C:\Users\Phuong PC\.jdks\azul-24.0.2
~~~

java.home phụ thuộc máy/runner nên sẽ khác giữa các môi trường. Các dòng version, vendor và architecture mới là dữ liệu cần đối chiếu với workflow đã khai báo.

Trong pipeline, có thể chạy chương trình này ngay sau bước setup JDK và lưu stdout vào log job. Nếu cache hit nhưng version/vendor không đúng, hãy kiểm tra JAVA_HOME, thứ tự PATH, tool cache và cache identity trước khi sửa build script.

## 11. Đo hiệu quả và troubleshooting

Để xác định cache có thực sự giúp pipeline nhanh hơn, ghi lại thời gian từng bước:

| Chỉ số | Ý nghĩa |
|---|---|
| JDK setup duration | Thời gian setup JDK ở cold run và warm run |
| Cache restore duration | Thời gian tải cache từ storage |
| JDK download duration | Thời gian tải archive từ vendor/repository |
| Extraction duration | Thời gian giải nén JDK |
| Cache save duration | Thời gian đóng gói/upload sau job |
| Cache hit/miss rate | Tần suất dùng lại được entry |
| Cache storage growth | Số entry và dung lượng tích lũy |

Nếu cache restore và extraction lâu hơn download JDK, cache có thể không đem lại lợi ích. Với hosted runner đã có sẵn Temurin phù hợp, runner tool cache có thể nhanh hơn việc khôi phục JDK archive từ xa.

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| JDK luôn được tải lại trên GitHub Actions | Chưa bật cache-jdk, cache key khác hoặc runner tool cache không có version phù hợp | Kiểm tra action version, cache setting, version/vendor/architecture và log setup |
| Có cache: maven nhưng không hiểu vì sao JDK cache tăng | setup-java bật JDK cache mặc định khi dependency cache được bật | Đặt cache-jdk: false nếu muốn chỉ giữ dependency cache |
| JDK cache hit nhưng Java version sai | Dùng major/floating version hoặc JAVA_HOME/PATH trỏ tới JDK khác | Pin patch version khi cần và chạy java -version/javac -version |
| GitLab cache không có ở job tiếp theo | Job chạy trên runner khác không có shared/distributed cache | Dùng distributed cache, runner chung hoặc JDK image |
| GitLab báo cache path không hợp lệ | Đang dùng đường dẫn ngoài project directory | Cache archive trong workspace hoặc cài JDK bằng image/runner tool |
| Cache archive được khôi phục nhưng không giải nén được | File hỏng, archive sai định dạng hoặc key quá rộng | Xác minh SHA-256, đổi key và tải lại từ nguồn tin cậy |
| javac không tìm thấy | Chỉ cài JRE hoặc PATH trỏ sai | Chọn package jdk và kiểm tra JAVA_HOME |
| Jenkins tải JDK mỗi build | Agent ephemeral hoặc installer không giữ installation | Dùng persistent agent/tool volume hoặc container image |
| Build matrix dùng nhầm cache | Key không phân tách OS/architecture/version/vendor | Thêm các chiều này vào key hoặc dùng key tự động của setup-java |
| Cache hit nhưng build không tái lập | JDK version, build tool hoặc dependencies đang dùng version floating | Pin JDK, Maven/Gradle wrapper và dependency versions |

## 12. Quy trình triển khai cache JDK

1. Xác định CI platform, loại runner và runner có persistent storage hay không.
2. Chọn JDK vendor, package type, version/build và architecture.
3. Kiểm tra runner tool cache hoặc base image đã có đúng JDK chưa.
4. Chọn cơ chế: setup-java cache-jdk, GitLab archive/image, hoặc Jenkins tool installation.
5. Thiết kế key có OS, architecture, vendor, version và checksum/release identity.
6. Bật checksum/signature verification theo khả năng của distribution.
7. Cấu hình quyền ghi cache cho job tin cậy và read-only cho job chỉ tiêu thụ.
8. Xác minh bằng java -version, javac -version và JdkProbe.
9. Chạy cold run để tạo cache và warm run để xác nhận hit.
10. So sánh setup duration, restore/save duration và tổng pipeline duration.
11. Đặt chính sách invalidation, retention và cleanup.
12. Bảo đảm cache miss vẫn cài được JDK hợp lệ từ nguồn tin cậy.

### Checklist

- [ ] Đã phân biệt runner tool cache, JDK cache, dependency cache, build cache và artifacts.
- [ ] Đã chọn đúng JDK distribution, package type và version.
- [ ] Đã phân tách cache key theo OS và architecture.
- [ ] Đã pin version hoặc hiểu rõ hành vi của version range/latest.
- [ ] Đã xác minh checksum/chữ ký của JDK archive khi hỗ trợ.
- [ ] Đã kiểm soát job/branch có quyền ghi cache.
- [ ] Đã xác minh JAVA_HOME, PATH và javac.
- [ ] Đã kiểm tra cache hit và cache miss.
- [ ] Đã xác nhận pipeline vẫn chạy khi cache bị eviction.
- [ ] Đã đo cold/warm run và tính cả chi phí restore/save.
- [ ] Đã có quy trình đổi key khi version hoặc checksum thay đổi.
- [ ] Đã đặt retention/cleanup cho cache cũ.

Cache JDK hiệu quả khi giúp runner tái sử dụng đúng bộ JDK mà không làm giảm tính tái lập hoặc tính toàn vẹn của build. Hãy kiểm tra runner tool cache trước, chọn đúng cơ chế cho nền tảng, tách JDK khỏi dependency cache, pin version/architecture và xác minh binary sau khi setup. Cache miss phải luôn có đường cài đặt lại an toàn.

## Tài liệu tham khảo

- [GitHub — actions/setup-java README and cache options](https://github.com/actions/setup-java)
- [GitHub — actions/setup-java advanced usage: Caching JDK installations](https://github.com/actions/setup-java/blob/main/docs/advanced-usage.md#caching-jdk-installations)
- [GitLab — Caching in GitLab CI/CD](https://docs.gitlab.com/ci/caching/)
- [GitLab — CI/CD YAML cache reference](https://docs.gitlab.com/ci/yaml/#cache)
- [Jenkins — Managing Tools and JDK installations](https://www.jenkins.io/doc/book/managing/tools/)