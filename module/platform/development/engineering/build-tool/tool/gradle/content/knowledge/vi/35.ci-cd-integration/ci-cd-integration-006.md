# Tích hợp Gradle vào GitLab CI hoặc Jenkins theo cùng nguyên tắc

## Mục tiêu bài học

Một dự án Gradle có thể chạy trên máy lập trình viên, GitLab CI và Jenkins mà **không phải viết ba quy trình build khác nhau**. Điều kiện cốt lõi là coi **mã nguồn + Gradle Wrapper + JDK/toolchain + cấu hình build + dependency metadata** là nguồn sự thật, còn GitLab hoặc Jenkins chỉ **điều phối các Gradle tasks**, cấp môi trường, quản lý báo cáo, cache, artifacts và quyền truy cập.

Hai pipeline có DSL khác nhau:

- **GitLab CI** dùng file **.gitlab-ci.yml**, định nghĩa **jobs**, **stages**, **image**, **script**, **cache**, **artifacts**, **rules**.
- **Jenkins Pipeline** dùng **Jenkinsfile** theo Declarative hoặc Scripted syntax, với **agent**, **tools**, **stages**, **steps**, **post**, **junit**, **archiveArtifacts** và Jenkins Credentials khi cần.

Nhưng nguyên tắc giống nhau:

1. **Một phiên bản Gradle thống nhất** bằng **Gradle Wrapper**, không phụ thuộc bản Gradle tùy ý cài trên runner/agent.
2. **Một JDK hợp lệ, được pin/kiểm tra**; source/target/toolchain đúng cho mã Java.
3. **Các task Gradle giống nhau** cho lint, compile, test, package, quality verification và publish; CI không sao chép logic của Gradle bằng script shell thủ công.
4. **Bước test phải chặn bước package/release** khi failed.
5. **Cache dùng để tăng tốc**, còn **artifacts và reports dùng làm bằng chứng hoặc truyền sản phẩm**; không nhầm hai cơ chế.
6. **Kết quả test JUnit XML** được công bố dù tests fail, nhưng pipeline vẫn phải fail.
7. **Không đưa secrets vào repository, Gradle User Home cache công khai hoặc logs**.
8. **Build từ commit được xác định**, không lệ thuộc JAR cũ hay máy developer.
9. **Tách PR/MR verification với deploy**; thao tác phát hành chỉ chạy trên nhánh/tag/approval được phép.
10. **Kiểm tra bằng build thực tế**, không coi YAML/Groovy parse thành công là đủ.

Sau bài học, bạn có thể tự tạo một lab Java 17 hai module, chạy đúng các Gradle tasks trên máy local, thiết lập GitLab pipeline và Jenkins Declarative Pipeline có semantics tương đương, phân tích trạng thái success/failure, đọc test results, download distribution và debug cache/permissions/toolchain.

Ví dụ sử dụng **Gradle Groovy DSL**, kèm đối chiếu Kotlin DSL cho dependency/test configuration. Lab yêu cầu **JDK 17+**, một **Gradle Wrapper tương thích JDK 17**, và quyền lấy JUnit Jupiter dependencies từ Maven Central hoặc repository mirror nội bộ. Các ví dụ CI chạy trên **Linux/POSIX agents**; Windows dùng gradlew.bat và Jenkins bat step, không thể chép nguyên sh/chmod vào Windows agent.

---

## 1. Gradle chịu trách nhiệm điều gì, CI chịu trách nhiệm điều gì?

### 1.1. Ranh giới trách nhiệm

| Việc | Gradle build | GitLab CI / Jenkins |
| --- | --- | --- |
| Khai báo Java modules | settings.gradle(.kts) | Checkout đúng commit |
| Chọn compiler Java | Java toolchain/options.release | Cung cấp/auto-provision JDK phù hợp |
| Khai báo dependencies | dependencies + repositories | Cấp network/credentials đến repository |
| Compile Java | compileJava | Gọi Gradle task |
| Unit/integration tests | Test tasks và test suites | Gọi tasks, công bố JUnit XML |
| Tạo JAR/distribution | jar, assemble, distZip | Lưu/download/promote artifact |
| Quality gate | Gradle test/check/verification rules | Chặn stage sau nếu exit code khác 0 |
| Incremental/up-to-date/build cache | Task fingerprints, cache inputs/outputs | Cấp persistent/local/remote cache storage |
| Version release | Gradle coordinates/release conventions | Approval, protected branch, publishing credentials |
| CI scheduling | Không nằm trong build.gradle | Jobs/stages/agents/rules/triggers |
| Quản lý bí mật | Provider đọc env/credentials an toàn | Vault/GitLab variables/Jenkins credentials |
| Historical reports | Sinh XML/HTML/scan | Upload, hiển thị và giữ trong retention policy |

**Đừng đặt một nửa công thức compile vào .gitlab-ci.yml và nửa còn lại trong Jenkinsfile**. Nếu CI A chạy javac thủ công còn CI B chạy ./gradlew test thì kết quả của hai nơi không so sánh được.

### 1.2. Một entrypoint thống nhất

Trong bài này:

~~~bash
./gradlew --no-daemon --console=plain :core:test :app:test
./gradlew --no-daemon --console=plain :app:distZip
~~~

Hai lệnh trên là **giao diện hợp đồng Gradle**. GitLab và Jenkins đều dùng chúng. Phần khác nhau chỉ là cách mỗi hệ thống:
- Chuẩn bị JDK và workspace.
- Gọi shell.
- Lưu JUnit XML.
- Lưu distribution ZIP.
- Quản lý cache.
- Bảo vệ credentials/release.

### 1.3. Wrapper là nguồn phiên bản Gradle

Một repository chuẩn có:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

File **gradle-wrapper.properties** khai báo distribution URL và có thể kèm **distributionSha256Sum**. **Gradle Wrapper** giúp local/CI dùng cùng bản Gradle, không cần cài một bản Gradle ngẫu nhiên trên máy Jenkins agent hoặc Docker image.

**Không tự tạo gradle-wrapper.jar bằng text hoặc tải JAR bất kỳ**. Tạo bằng task **wrapper** của Gradle hợp lệ, commit đủ các file Wrapper, kiểm tra tính toàn vẹn JAR và distribution checksum theo chính sách bảo mật.

### 1.4. JDK và Gradle version là hai hợp đồng riêng

**Gradle Wrapper version** quyết định Gradle runtime. **JDK chạy Gradle daemon** có thể khác **JDK toolchain dùng để compile code**. Mã Java 17 nên khai báo:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Và khi cần khóa Java API/bytecode target:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

CI phải cung cấp toolchain phù hợp hoặc cấu hình auto-provisioning từ nguồn tin cậy. Không giả định mọi Gradle version đều chạy trên mọi JDK; xem Gradle Compatibility Matrix và pin wrapper.

### 1.5. Vì sao không chạy lệnh gradle do agent cài?

~~~bash
gradle build
~~~

có thể dùng bản Gradle ngoài repository. Developer chạy Gradle 8.x, GitLab chạy Gradle 9.x, Jenkins lại chạy version khác. Khi nâng plugin hoặc Gradle API, sai lệch này gây lỗi khó tái hiện.

Ưu tiên:

~~~bash
./gradlew --version
./gradlew :core:test :app:test
~~~

Trên Windows, dùng **gradlew.bat**. Jenkins có công cụ Gradle tích hợp trong **Tools**, nhưng dự án đã có Wrapper thì không cần thay Wrapper bằng Gradle installation của Jenkins.

---

## 2. Luồng kiểm chứng tiêu chuẩn cho hai nền tảng

Hợp đồng CI đơn giản:

~~~text
git push / merge request / pull request
                 |
                 v
        Checkout fixed commit
                 |
                 v
      Prepare JDK + Wrapper
                 |
                 v
  Test: :core:test :app:test
      |                    |
      +-- JUnit XML -------+----> CI test report
      |
      +-- FAILED ----------> pipeline FAILED, package blocked
      |
      +-- SUCCESS
                 |
                 v
        Package: :app:distZip
                 |
                 v
   distribution ZIP stored as artifact
                 |
                 v
       (optional protected release)
~~~

### 2.1. Test stage

- Phải thực thi tests bằng Gradle.
- Không dùng **--continue** để bỏ qua failed tests rồi cho package thành công.
- Phải giữ exit code khác 0 nếu một test fail hoặc compile fail.
- Nên thu JUnit XML ở chế độ **always**, vì failed test là lúc report hữu ích nhất.
- Báo cáo JUnit từ **build/test-results/test** khác HTML report trong **build/reports/tests/test**.

### 2.2. Package stage

- Chỉ bắt đầu sau test stage thành công.
- Chạy một Gradle task có ý nghĩa artifact, ví dụ **:app:distZip** từ Application plugin.
- Lưu sản phẩm bằng **GitLab artifacts** hoặc **Jenkins archiveArtifacts**.
- Không trông đợi JAR ở workspace stage trước tự còn nguyên nếu jobs dùng máy/container khác.

### 2.3. Release stage

- Không được kích hoạt tự do từ mọi MR/PR.
- Dùng protected branch/tag, manual approval hoặc deployment permissions.
- Credentials chỉ được inject trong giai đoạn cần.
- Publish artifacts có provenance/sha, version và checksum, không dùng kết quả build cũ chưa kiểm chứng.

### 2.4. Cùng nhiệm vụ, khác cú pháp

| Ý nghĩa | GitLab | Jenkins Declarative |
| --- | --- | --- |
| Khai báo pipeline | **.gitlab-ci.yml** | **Jenkinsfile** |
| Runtime/container | **image** tùy runner executor | **agent**, container/node nếu cấu hình |
| Bước công việc | **jobs, stages, script** | **stages, stage, steps, sh** |
| Chặn stage sau khi test fail | Default stage gating | Default stage gating |
| JUnit XML | **artifacts:reports:junit** | **junit** step |
| Artifact ZIP/JAR | **artifacts:paths** | **archiveArtifacts** |
| Cache downloads | **cache: key/paths** | Persistent agent home hoặc Gradle remote cache |
| Secrets | Masked/protected CI/CD variables | Credentials/withCredentials |
| PR/MR selection | **rules, workflow** | Multibranch Pipeline/when |
| Retention | **expire_in** hoặc instance policy | Build discarder/artifact retention policy |

---

## 3. Lab Java 17: mã nguồn chung cho GitLab và Jenkins

Chúng ta tạo hai Gradle subprojects:
- **:core**: thư viện chứa bộ cộng số nguyên.
- **:app**: ứng dụng console phụ thuộc :core, có unit test riêng.

JUnit 5 tests chứng minh từng module chạy đúng. Application plugin tạo **distZip**, một ZIP chứa các JAR cần thiết và scripts khởi chạy, tốt hơn việc coi một thin app.jar là executable độc lập.

### 3.1. Cây thư mục

~~~text
gradle-ci-lab/
├── .gitignore
├── .gitlab-ci.yml
├── Jenkinsfile
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── core/
│   ├── build.gradle
│   ├── src/main/java/lab/core/Calculator.java
│   └── src/test/java/lab/core/CalculatorTest.java
└── app/
    ├── build.gradle
    ├── src/main/java/lab/app/Main.java
    └── src/test/java/lab/app/MainTest.java
~~~

**Chỉ copy các file cấu hình và source được mô tả bên dưới**; Wrapper phải được tạo bằng Gradle hoặc lấy từ nguồn tin cậy. Hai file CI có thể cùng nằm trong repository; GitLab đọc .gitlab-ci.yml và Jenkins đọc Jenkinsfile, không có xung đột chức năng.

### 3.2. settings.gradle

~~~groovy
rootProject.name = 'gradle-ci-lab'
include 'core', 'app'
~~~

### 3.3. build.gradle ở root

~~~groovy
plugins {
    id 'base'
}
~~~

Root giữ vai trò điều phối multi-project build. Mỗi module tự định nghĩa plugin, dependencies, toolchain và test task.

### 3.4. core/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    reports {
        junitXml.required = true
        html.required = true
    }
}
~~~

**JUnit BOM** thống nhất versions giữa JUnit artifacts. **junit-platform-launcher** được đưa vào testRuntimeOnly theo khuyến nghị Gradle hiện đại. Maven Central được dùng để tải framework; project production có thể thay bằng nội bộ proxy/mirror.

### 3.5. core/src/main/java/lab/core/Calculator.java

~~~java
package lab.core;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }
}
~~~

**Math.addExact** ném ArithmeticException nếu tràn số nguyên; lab chỉ dùng các giá trị nhỏ, không có overflow.

### 3.6. core/src/test/java/lab/core/CalculatorTest.java

~~~java
package lab.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

public final class CalculatorTest {

    @Test
    void addsTwoNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void rejectsOverflow() {
        assertThrows(
                ArithmeticException.class,
                () -> Calculator.add(
                        Integer.MAX_VALUE, 1
                )
        );
    }
}
~~~

Hai tests có assertions cụ thể. Một test kiểm tra happy path, một test kiểm tra boundary/negative path.

### 3.7. app/build.gradle

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

dependencies {
    implementation project(':core')

    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'lab.app.Main'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    reports {
        junitXml.required = true
        html.required = true
    }
}
~~~

**implementation project(':core')** để Gradle giải quyết đúng project dependency graph. Không tham chiếu thủ công **../core/build/libs/core.jar**, vì CI jobs/agents có thể có clean workspace và Java library consumer cần transitive metadata/task provenance.

### 3.8. app/src/main/java/lab/app/Main.java

~~~java
package lab.app;

import lab.core.Calculator;

public final class Main {
    private Main() {
    }

    public static String message() {
        return "CI_OK: " + Calculator.add(2, 3);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

### 3.9. app/src/test/java/lab/app/MainTest.java

~~~java
package lab.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

public final class MainTest {

    @Test
    void createsExpectedMessage() {
        assertEquals("CI_OK: 5", Main.message());
    }
}
~~~

Ba JUnit tests tổng cộng trong hai modules: hai ở :core và một ở :app. Khi chạy thành công, GitLab/Jenkins có thể tổng hợp **số test, status và thời gian** từ XML. Không nên tự hardcode test duration; thời gian là phép đo thực tế.

### 3.10. .gitignore

~~~gitignore
.gradle/
**/build/
out/
.idea/
*.iml
~~~

**Không ignore gradle/wrapper/**: đó là phần mã cấu hình Wrapper cần commit. **.gradle/** được CI sử dụng như Gradle User Home cache ở một số môi trường nhưng không được commit vào repository.

### 3.11. Chạy trên máy developer trước CI

Linux/macOS:

~~~bash
chmod +x ./gradlew
./gradlew --version
./gradlew --no-daemon --console=plain :core:test :app:test
./gradlew --no-daemon --console=plain :app:distZip
./gradlew :app:run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat --no-daemon --console=plain :core:test :app:test
.\gradlew.bat --no-daemon --console=plain :app:distZip
.\gradlew.bat :app:run
~~~

Dòng stdout **do chương trình Java in chính xác**:

~~~text
CI_OK: 5
~~~

Gradle còn in task logs, download dependencies ở lần đầu và BUILD SUCCESSFUL; không coi khối trên là transcript toàn bộ console.

### 3.12. Nơi lưu test results

Mặc định thường có:

~~~text
core/build/test-results/test/TEST-lab.core.CalculatorTest.xml
app/build/test-results/test/TEST-lab.app.MainTest.xml

core/build/reports/tests/test/index.html
app/build/reports/tests/test/index.html
~~~

**XML** là dữ liệu cho GitLab/Jenkins test UI. **HTML** hữu ích cho người xem nhưng không thay XML. Các tên file và paths là conventions; nếu build đổi reports.junitXml.outputLocation, CI glob phải được cập nhật.

### 3.13. Distribution ZIP

~~~text
app/build/distributions/app.zip
~~~

Tên thực tế có thể gồm project name/version tùy cấu hình và Gradle version, nên pipeline dùng glob **app/build/distributions/*.zip**. Application distribution thường có:
- Start scripts cho Unix/Windows.
- app JAR.
- core JAR và các runtime dependencies.
- Files cần thiết để chạy ứng dụng.

**app/build/libs/app.jar** mặc định là thin JAR, không nhất thiết chứa core classes hoặc có executable manifest. Nếu muốn artifact có thể giải nén và chạy, **distZip** là lựa chọn phù hợp cho Application plugin.

### 3.14. Java 17 chạy độc lập bằng javac/java

Để kiểm tra mã không phụ thuộc CI system, có thể compile chỉ production sources bằng JDK17.

Linux/macOS:

~~~bash
mkdir -p out/core out/app

javac --release 17 -encoding UTF-8 \
    -d out/core \
    core/src/main/java/lab/core/Calculator.java

javac --release 17 -encoding UTF-8 \
    -cp out/core \
    -d out/app \
    app/src/main/java/lab/app/Main.java

java -cp out/app:out/core lab.app.Main
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out\core,out\app | Out-Null

javac --release 17 -encoding UTF-8 -d out\core core\src\main\java\lab\core\Calculator.java

javac --release 17 -encoding UTF-8 -cp out\core -d out\app app\src\main\java\lab\app\Main.java

java -cp "out\app;out\core" lab.app.Main
~~~

Stdout chính xác:

~~~text
CI_OK: 5
~~~

Lệnh này **không chạy JUnit tests**, nên không thay thế **./gradlew :core:test :app:test**. Nó chỉ kiểm tra source Java và lý do :app cần :core trên classpath.

---

## 4. GitLab CI: pipeline đầy đủ cho lab

GitLab Runner với **Docker executor** hoặc executor hỗ trợ container images có thể sử dụng image **eclipse-temurin:17-jdk**. Nếu dùng **Shell executor**, directive **image** không cung cấp JDK; JDK và Gradle Wrapper prerequisites phải được cài trên host.

### 4.1. File .gitlab-ci.yml

~~~yaml
image: eclipse-temurin:17-jdk

stages:
  - test
  - package

variables:
  GRADLE_USER_HOME: "$CI_PROJECT_DIR/.gradle"

before_script:
  - chmod +x ./gradlew
  - ./gradlew --version

cache:
  key:
    files:
      - gradle/wrapper/gradle-wrapper.properties
  paths:
    - .gradle/wrapper/

unit_tests:
  stage: test
  script:
    - ./gradlew --no-daemon --console=plain :core:test :app:test
  artifacts:
    when: always
    reports:
      junit:
        - "core/build/test-results/test/TEST-*.xml"
        - "app/build/test-results/test/TEST-*.xml"
    paths:
      - core/build/reports/tests/test/
      - app/build/reports/tests/test/
    expire_in: 1 week

package_application:
  stage: package
  script:
    - ./gradlew --no-daemon --console=plain :app:distZip
  artifacts:
    paths:
      - app/build/distributions/*.zip
    expire_in: 1 week
~~~

**Đây là pipeline GitLab đầy đủ cho lab** trong điều kiện Runner có shell POSIX, JDK17 image có thể pull, Wrapper hợp lệ và test dependencies resolve được. Không yêu cầu plugin GitLab đặc biệt phía Gradle.

### 4.2. Giải thích image

**image: eclipse-temurin:17-jdk** đặt một môi trường Linux với JDK17 cho Docker/Kubernetes runner. Image này **không cần cài Gradle**: **./gradlew** tự lấy version theo Wrapper.

Trong production, có thể pin **image digest** thay tag để tăng reproducibility và giảm rủi ro tag bị thay đổi. Tag chỉ là một tên có thể trỏ tới image cập nhật.

### 4.3. Giải thích stages và jobs

~~~yaml
stages:
  - test
  - package
~~~

**unit_tests** phải pass để **package_application** bắt đầu theo mặc định. Nếu javac hoặc JUnit tests fail và Gradle trả exit code khác 0, GitLab đánh dấu job failed và không chạy package ở stage sau.

**Không thêm allow_failure: true** cho test job trong một pipeline chất lượng bắt buộc; nó có thể khiến failure không chặn như mong muốn.

### 4.4. Tại sao không cần clean ở đầu mọi job?

Trên GitLab Runner containers, workspace thường được chuẩn bị theo job isolation. **gradlew clean** không phải bước bắt buộc để đảm bảo build đúng nếu inputs/outputs Gradle được khai báo chuẩn. Dọn mọi thứ mỗi lần còn có thể phá incremental benefits và tốn thời gian.

Nếu muốn đo reproducibility từ clean workspace, tạo job định kỳ riêng với **clean build**, không áp --rerun-tasks/clean vô điều kiện cho mọi PR mà không đo.

### 4.5. GRADLE_USER_HOME trong project directory

GitLab cache paths phải ở vùng runner có thể cache, thường nằm trong **$CI_PROJECT_DIR**. Vì vậy:

~~~yaml
variables:
  GRADLE_USER_HOME: "$CI_PROJECT_DIR/.gradle"
~~~

Từ đó **.gradle/wrapper/** chứa Gradle distribution downloads/wrapper state dùng lại được giữa jobs khi runner cache có entry. Đây là **Gradle User Home cho job**, khác với **project-local .gradle/** nếu Gradle User Home ở vị trí mặc định.

### 4.6. Tại sao mặc định chỉ cache Wrapper?

~~~yaml
cache:
  key:
    files:
      - gradle/wrapper/gradle-wrapper.properties
  paths:
    - .gradle/wrapper/
~~~

Đây là lựa chọn khởi đầu đơn giản phù hợp GitLab SaaS/shared runners:
- Cache size nhỏ hơn việc nén toàn bộ .gradle/caches.
- Cache key thay khi Wrapper distribution thay.
- Không tải toàn bộ dependency cache potentially rất lớn lên/down từ runner storage.
- Tránh đem credentials/logs/init scripts vào cache ngoài chủ đích.

**Nó không cache JUnit dependencies**: các dependencies từ Maven Central có thể được tải lại ở job khác. Với runners dedicated/network đắt, nên đánh giá full Gradle User Home cache hoặc remote build cache có policy rõ.

### 4.7. GitLab test report

~~~yaml
artifacts:
  when: always
  reports:
    junit:
      - "core/build/test-results/test/TEST-*.xml"
      - "app/build/test-results/test/TEST-*.xml"
~~~

**when: always** giúp artifact report được upload ngay cả khi test job failed, miễn các XML files đã được tạo. Nếu compilation fail trước khi Test task chạy, có thể chưa có XML; phải đọc build log thay vì coi “không có report” nghĩa là 0 tests pass.

GitLab hiển thị JUnit test results trên pipeline/merge request pages. Report XML được đưa qua **artifacts:reports:junit**, không phải nhúng HTML và gọi nó là JUnit.

### 4.8. GitLab HTML report

~~~yaml
paths:
  - core/build/reports/tests/test/
  - app/build/reports/tests/test/
~~~

Những HTML files được giữ trong artifacts theo **expire_in** để developer tải về hoặc xem qua GitLab UI. Chúng **không thay thế** XML test report ingestion.

### 4.9. Distribution artifact

~~~yaml
package_application:
  stage: package
  script:
    - ./gradlew --no-daemon --console=plain :app:distZip
  artifacts:
    paths:
      - app/build/distributions/*.zip
~~~

CI giữ bản ZIP của job package. Sau khi pipeline pass, người dùng có thể download artifact đã được lưu bởi GitLab thay vì tự chạy một build khác để lấy ZIP.

**Chú ý:** Đây là artifact của **package job**. Vì test job và package job có thể chạy trên hai containers khác nhau, package job tự compile những outputs cần thiết từ cùng commit; nó không dựa trên JAR ở local filesystem của test job.

### 4.10. Không coi cache là cơ chế truyền artifact

GitLab cache được dùng để **tăng tốc**, không được bảo đảm tồn tại hay chính xác trong tất cả runner configurations. Nếu stage B phải nhận **chính byte artifacts từ stage A**, dùng **artifacts** và **needs/dependencies** phù hợp, không dùng cache.

Pipeline lab không cần stage B nhận một file từ stage A; cả hai chạy Gradle trên cùng source commit, và stage test chỉ làm quality gate. Đây là mô hình có chủ đích.

---

## 5. Jenkins Declarative Pipeline đầy đủ cho cùng lab

Jenkins cần:
- **Pipeline: Declarative** và các Pipeline steps tương ứng.
- Một **Linux agent** có git, shell, quyền tạo workspace và JDK17 được cấu hình.
- Jenkins tool JDK tên **jdk17** được quản trị viên đăng ký dưới **Manage Jenkins → Tools**.
- Jenkinsfile được cấu hình trong Multibranch Pipeline hoặc Pipeline from SCM.
- JUnit và archiveArtifacts steps/plugin có trong Jenkins instance.

### 5.1. Jenkinsfile

~~~groovy
pipeline {
    agent any

    tools {
        jdk 'jdk17'
    }

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Environment') {
            steps {
                sh 'chmod +x ./gradlew'
                sh './gradlew --version'
            }
        }

        stage('Test') {
            steps {
                sh './gradlew --no-daemon --console=plain :core:test :app:test'
            }
        }

        stage('Package') {
            steps {
                sh './gradlew --no-daemon --console=plain :app:distZip'
            }
        }
    }

    post {
        always {
            junit(
                testResults: '**/build/test-results/test/TEST-*.xml',
                allowEmptyResults: true
            )
            archiveArtifacts(
                artifacts: '**/build/reports/tests/test/**',
                allowEmptyArchive: true
            )
        }

        success {
            archiveArtifacts(
                artifacts: 'app/build/distributions/*.zip',
                allowEmptyArchive: false,
                fingerprint: true
            )
        }
    }
}
~~~

**Đây là Jenkins Declarative Pipeline đầy đủ** cho một Linux agent có Jenkins Tools/JUnit steps phù hợp. Trong môi trường mà Jenkins tự checkout repo trước stages, **checkout scm** có thể checkout thêm lần nữa; đó là optimization có thể xử lý sau bằng **skipDefaultCheckout(true)**.

### 5.2. Vì sao Jenkins dùng tools JDK?

~~~groovy
tools {
    jdk 'jdk17'
}
~~~

Jenkins đặt JDK tool đã được cấu hình vào PATH/JAVA_HOME của agent trong Pipeline. **jdk17** là một tên công cụ phải tồn tại trong Jenkins instance, không phải alias được Gradle tự tạo.

Nếu agent dùng Docker image chứa JDK17, có thể không cần tools directive mà thay bằng agent/container config phù hợp. Điểm quan trọng là **JDK runtime thực sự phù hợp Gradle Wrapper**.

### 5.3. Jenkins sh và Windows bat

~~~groovy
sh './gradlew :app:distZip'
~~~

chỉ chạy trên agent có POSIX shell. Nếu Jenkins agent chạy Windows:

~~~groovy
bat 'gradlew.bat :app:distZip'
~~~

và phải thay toàn bộ sh/chmod steps, cung cấp JDK17 PATH/JAVA_HOME phù hợp. Không kỳ vọng cùng Jenkinsfile có sh tự chọn theo OS.

### 5.4. Jenkins stages và fail-fast mặc định

Stage Test gọi:

~~~groovy
sh './gradlew --no-daemon --console=plain :core:test :app:test'
~~~

Nếu Gradle exit code khác 0, **sh** step thất bại và Declarative Pipeline không chạy stage Package như bình thường. Điều này tương ứng với GitLab **stages test → package**.

**Đừng dùng catchError(... buildResult: 'SUCCESS')**, returnStatus rồi bỏ qua exit code, hoặc shell **|| true** để làm test failures trông như thành công.

### 5.5. Jenkins JUnit report

~~~groovy
post {
    always {
        junit(
            testResults: '**/build/test-results/test/TEST-*.xml',
            allowEmptyResults: true
        )
    }
}
~~~

**post.always** chạy kể cả stage Test thất bại, vì vậy Jenkins có thể đọc những XML đã sinh để hiển thị test trends/failures. **allowEmptyResults: true** giúp không thêm lỗi khác nếu build fail ngay ở bước compile trước khi XML xuất hiện.

**Quan trọng:** allowEmptyResults chỉ áp cho step công bố report, **không xác nhận project đã chạy đủ tests**. Nếu policy yêu cầu bắt buộc có XML, thêm một guard kiểm tra expected reports trong successful Test stage hoặc chuyển allowEmptyResults=false sau khi bảo đảm không gây nhiễu lỗi trước test; không coi zero results là pass đúng.

### 5.6. Jenkins lưu HTML và ZIP

~~~groovy
archiveArtifacts(
    artifacts: '**/build/reports/tests/test/**',
    allowEmptyArchive: true
)
~~~

và:

~~~groovy
archiveArtifacts(
    artifacts: 'app/build/distributions/*.zip',
    allowEmptyArchive: false,
    fingerprint: true
)
~~~

Jenkins lưu files dưới build record. **fingerprint** giúp Jenkins theo dõi artifact usage/provenance trong các workflow có support. Nó không thay checksum/signature verification khi phát hành ra public repository.

### 5.7. post.success giới hạn ZIP

ZIP chỉ được lưu ở **success** block trong ví dụ. Nếu tests/package fail, pipeline không công bố một ZIP như kết quả release thành công. Nếu team cần artifact phục vụ debug khi package fail, có thể archive khi always nhưng phải gắn rõ trạng thái không dùng để deploy.

### 5.8. Vì sao có disableConcurrentBuilds?

~~~groovy
options {
    disableConcurrentBuilds()
}
~~~

Nó giảm trường hợp **hai runs của cùng Jenkins job** ghi vào workspace/cache được chia sẻ ngoài ý muốn. Tuy nhiên, các jobs khác vẫn có thể chung Gradle User Home trên một agent; cần user permissions và cache isolation riêng.

### 5.9. Dùng agent Docker khi Jenkins có plugin phù hợp

Ví dụ thay thế top-level agent (không copy đồng thời với agent any):

~~~groovy
agent {
    docker {
        image 'eclipse-temurin:17-jdk'
    }
}
~~~

Tùy Jenkins Docker Pipeline plugin/agent executor, cần Docker daemon và image pull được phép. Nếu dùng container image đã có Java17, có thể bỏ **tools jdk 'jdk17'** và chỉ dùng Wrapper. Phần này là **alternative fragment**, không phải cấu hình bắt buộc cho lab.

### 5.10. Checkout scm và Multibranch Pipeline

**checkout scm** sử dụng SCM context được Jenkins job định nghĩa. Với Multibranch Pipeline, Jenkins có thể tự checkout đúng branch/PR revision theo job configuration. Để tránh checkout hai lần, có thể thêm:

~~~groovy
options {
    skipDefaultCheckout(true)
    timestamps()
}
~~~

và giữ **stage('Checkout')**. Nếu Jenkins job không có scm context phù hợp, phải cấu hình SCM/repository/credentials tại Jenkins job; không tự chèn URL/token vào Jenkinsfile.

---

## 6. Đối chiếu hai pipeline theo từng bước

| Hành động | GitLab CI | Jenkins |
| --- | --- | --- |
| Chọn JDK | image eclipse-temurin:17-jdk | tools jdk 'jdk17' hoặc Docker agent |
| Checkout | GitLab Runner tự chuẩn bị repository | checkout scm |
| Chuẩn bị Wrapper | chmod +x ./gradlew | sh chmod +x ./gradlew |
| Xác minh version | ./gradlew --version | sh './gradlew --version' |
| Test core | :core:test | :core:test |
| Test app | :app:test | :app:test |
| Build distribution | :app:distZip | :app:distZip |
| Test XML | artifacts:reports:junit | post.always junit |
| HTML test reports | artifacts:paths | archiveArtifacts |
| Distribution ZIP | package artifacts:paths | post.success archiveArtifacts |
| Stage gating | test trước package | Test trước Package |
| Cache cơ bản | wrapper-only cache | Persistent agent cache hoặc remote cache |
| Secrets | CI/CD variables | Jenkins credentials |

### 6.1. “Cùng nguyên tắc” không có nghĩa “giống từng keyword”

Không cố viết **cache:** YAML trong Jenkinsfile hoặc **post { junit }** trong GitLab. Chúng là ngôn ngữ orchestration khác nhau. Chỉ giữ **Gradle tasks, inputs, dependencies, reports, exit code semantics và release policy** tương đương.

### 6.2. Công thức kiểm chứng tính tương đương

Sau khi hai pipeline chạy trên **cùng commit**:
1. Wrapper version giống.
2. Java bytecode target/toolchain giống.
3. Cùng :core:test và :app:test.
4. Cùng expected JUnit test counts/IDs (3 tests của lab) khi không bị test filter khác.
5. Cùng :app:distZip và distribution content semantically giống.
6. Pipeline fail khi cố ý tạo failed assertion.
7. Không có secrets leak hoặc bypass quality gate.
8. Mọi khác biệt artifact hash vì archive timestamps/toolchain/OS phải được phân tích, không tự xem như build đúng/hỏng từ một hash duy nhất.

### 6.3. Jenkins và GitLab có thể dùng JVM cache state khác nhau

Ngay cả với cùng commit và tasks, Jenkins long-lived agent có thể thấy UP-TO-DATE/daemon warmed, còn GitLab ephemeral container compile từ đầu hoặc lấy FROM-CACHE. **Kết quả chức năng phải tương đương; thời gian và task outcomes không cần giống nhau**.

---

## 7. Cache, artifacts và reports: không trộn lẫn

### 7.1. Ba đối tượng có mục đích khác nhau

| Đối tượng | Mục đích | Có được dùng làm chứng cứ phát hành? |
| --- | --- | --- |
| **Cache** | Tăng tốc downloads hoặc task output reuse | Không; cache có thể miss/evict và không phải artifact release |
| **Artifact** | Lưu hoặc chuyển kết quả của một job/build | Có nếu sinh từ commit/job tin cậy và verified |
| **Report** | Mô tả kết quả tests/coverage/quality | Có để đánh giá quality gate, cần đúng phạm vi |

### 7.2. GitLab cache không bảo đảm job sau nhận đúng file

GitLab Runner cache có thể được lưu cục bộ trên runner hoặc object storage tùy configuration. Với shared runners, jobs không nhất thiết được lên cùng máy; cache entry có thể không tồn tại hoặc bị eviction.

Do đó:

~~~yaml
cache:
  paths:
    - app/build/distributions/
~~~

không phải cách chuẩn để chuyển release ZIP từ job build sang job deploy. **Artifacts** mới là giao diện cho dữ liệu bắt buộc giữa jobs.

### 7.3. Jenkins persistent workspace không là hợp đồng artifact

Jenkins có thể chạy các stages trong cùng workspace, nên file build/distributions có vẻ tồn tại. Nhưng nếu chuyển stage sang agent/container khác, dùng cleanWs hoặc worker node bị hủy, file đó có thể mất. Khi sản phẩm phải đi giữa nodes/jobs, dùng Jenkins **stash/unstash**, **archiveArtifacts/copyArtifacts**, artifact repository hoặc storage release theo chính sách.

### 7.4. Gradle dependency cache khác Gradle build cache

**Gradle dependency cache** giữ downloaded external modules (Maven/Ivy descriptors, JARs). **Gradle build cache** giữ outputs của cacheable tasks theo input snapshots, có thể tạo trạng thái **FROM-CACHE**.

**GitLab cache** là cơ chế runner lưu folders như .gradle/wrapper/. Nó có thể chứa dependency cache hoặc local build cache nếu cấu hình, nhưng bản thân YAML cache không làm task Gradle trở nên cacheable.

### 7.5. Cache privacy/security

**Gradle User Home** có thể chứa:
- Gradle wrapper distributions.
- Dependency artifacts/metadata.
- Init scripts.
- Gradle properties, có thể chứa credentials.
- Daemon logs.
- Local task output cache.
- Trust/certificate configuration.

Không archive toàn bộ GRADLE_USER_HOME như CI artifact tải công khai. Không dùng cùng writable Gradle User Home cho các untrusted jobs/branches có access khác nhau.

### 7.6. Khi nào cache full .gradle có ích?

Với dedicated GitLab runners và cache storage gần worker, có thể cân nhắc:

~~~yaml
cache:
  key: "$CI_COMMIT_REF_SLUG"
  paths:
    - .gradle/caches/
    - .gradle/wrapper/
~~~

**Đây là alternative fragment**, không áp đồng thời với wrapper-only cache ở mục 4 nếu chưa đánh giá chi phí và bảo mật. Cache đầy đủ có thể rất lớn; runtime/hashing/archive overhead có thể lớn hơn download time.

Không để protected branch và untrusted MR cùng ghi cache keys khi cơ chế isolation chưa đủ. Với workload có nhiều runners, **Gradle Remote Build Cache** thường hiệu quả hơn trong việc chia sẻ task outputs.

---

## 8. Test result publishing và failure semantics

### 8.1. Kết quả một lượt test đúng

Local:

~~~bash
./gradlew --no-daemon :core:test :app:test
~~~

Gradle Test tasks sinh XML:
- Một testcase XML cho mỗi Java test class (các path tùy output config).
- Count tương ứng 3 tests của lab.
- Status success nếu cả ba pass.
- Duration phụ thuộc máy.

GitLab/Jenkins dùng XML này để hiển thị **test history**. Nó không đọc trực tiếp Java source code để suy ra có 3 tests.

### 8.2. Thí nghiệm cố ý gây test fail

Trong **CalculatorTest.java**, chỉ tại branch thử nghiệm, đổi:

~~~java
assertEquals(5, Calculator.add(2, 3));
~~~

thành:

~~~java
assertEquals(6, Calculator.add(2, 3));
~~~

Sau đó chạy:

~~~bash
./gradlew :core:test :app:test
~~~

Kỳ vọng **:core:test** fail do expected=6/actual=5. Nếu Gradle dừng ngay ở task failed, :app:test có thể chưa chạy, nhưng XML đã được sinh cho những tests đã chạy. Trên GitLab, **package_application không chạy** theo stage gating; trên Jenkins, **Package stage không chạy** vì sh trả nonzero.

**Hoàn nguyên assertion trước khi merge**, không push code sai lên nhánh chính để thử CI nếu không có môi trường thử nghiệm riêng.

### 8.3. Báo cáo vẫn phải thu khi test fail

GitLab:

~~~yaml
artifacts:
  when: always
  reports:
    junit: "**/build/test-results/test/TEST-*.xml"
~~~

Jenkins:

~~~groovy
post {
    always {
        junit(
            testResults: '**/build/test-results/test/TEST-*.xml',
            allowEmptyResults: true
        )
    }
}
~~~

Cả hai đều cố gắng đọc XML sau thất bại. **Không được ép Gradle test task ignoreFailures=true** chỉ để report được xuất: task Test vốn có thể tạo report khi tests fail, và CI phải giữ build failed.

### 8.4. Không có XML khác với tests pass

Nếu Java compile fail trước test, hoặc CI glob sai, JUnit report có thể trống. Cần phân biệt:
- Test runner không chạy.
- Không discover test.
- Test files không có.
- Report XML bị thay output location.
- Artifact upload không tìm thấy files.
- Tests chạy ở suite khác tên integrationTest.

**Quality gate** nên kiểm tra số tests kỳ vọng và disallow missing test suites khi có yêu cầu. Đừng coi missing XML là 0 failures và tự công bố xanh.

### 8.5. Unit và integration suites

Nếu project có một test suite **integrationTest**, lệnh **:app:test** không tự đảm bảo nó được chạy. Thêm tasks phù hợp:

~~~bash
./gradlew :core:test :app:test :app:integrationTest
~~~

và mở rộng CI glob:

~~~text
**/build/test-results/integrationTest/TEST-*.xml
~~~

Đây là **fragment cho dự án thực sự đã định nghĩa integrationTest**, không phải lệnh chạy được trong lab hai module hiện tại.

### 8.6. Khi nào dùng check?

Trong Java project, **check** thường phụ thuộc test. Một tổ chức có thể dùng:

~~~bash
./gradlew :core:check :app:check
~~~

thay test selectors để bao gồm thêm verification tasks được nối vào check (Checkstyle, SpotBugs, JaCoCo verification...). Nhưng để so GitLab/Jenkins **cùng nguyên tắc**, phải chọn **cùng check tasks** ở cả hai.

Nếu root apply base, dùng **./gradlew check** có thể kích hoạt matching tasks trong multi-project; tuy nhiên fully qualified **:core:check :app:check** rõ hơn về phạm vi, đặc biệt trong monorepo lớn.

### 8.7. Test duration không đồng nghĩa coverage

JUnit XML cho biết tests run/pass/fail/duration, **không phải JaCoCo line/branch coverage**. Muốn coverage gate, thêm JaCoCo plugin và verification task riêng trong Gradle, sau đó CI gọi task đó ở cả hai nền tảng và lưu XML/HTML coverage reports phù hợp.

---

## 9. Jenkins agent, GitLab Runner và môi trường build

### 9.1. GitLab container

Nếu dùng image eclipse-temurin:17-jdk, Maven dependencies và Gradle distribution có thể cần download trong job. Runner Docker executor thường tạo container mới cho job; cache được GitLab Runner restore nếu có, không phải file hệ thống ngẫu nhiên từ developer.

### 9.2. GitLab shell executor

Shell executor chạy trên host. Directive image không được xử lý như Docker image runtime. JDK17 phải được cài hoặc cung cấp qua môi trường runner, và GRADLE_USER_HOME phải an toàn/isolated.

### 9.3. Jenkins long-lived agents

Jenkins agent có thể giữ **~/.gradle** giữa builds, tăng reuse nhưng cũng tăng:
- Khả năng state cũ che lỗi.
- Dung lượng ổ đĩa sử dụng.
- Rủi ro build logic/credentials của jobs khác chạm vào shared user home.
- Gradle Daemon/JDK compatibility differences.

Vì vậy cần host policy, workspace isolation, Gradle User Home permissions và định kỳ kiểm thử từ clean checkout.

### 9.4. Jenkins ephemeral Kubernetes/Docker agents

Nếu agent mới mỗi run, behavior gần GitLab ephemeral runner. Đừng giả định ~/.gradle persisted; dùng volume/cache service/remote build cache khi hiệu quả và được kiểm soát. Tương tự, không dựa vào old workspace files.

### 9.5. --no-daemon có phải lựa chọn duy nhất?

**--no-daemon** trong các ví dụ bảo đảm không dùng daemon lâu dài giữa các invocations; với JVM args không tương thích client, Gradle vẫn có thể khởi tạo **single-use daemon**. Trên ephemeral runner, cách này giảm daemon residue. Trên Jenkins long-lived agent, warm daemon có thể nhanh hơn; hãy đo theo workflow thực và áp cùng chính sách khi so benchmarking.

**Không coi --no-daemon là security sandbox**. Nó không ngăn plugin/tasks đọc filesystem hoặc network theo quyền agent.

### 9.6. --parallel và --max-workers

Gradle có thể chạy tasks song song khi build được cấu hình phù hợp. Trong CI:
- Chọn **--max-workers** theo CPU/RAM thật.
- Đo trước khi bật **--parallel** cho mọi job.
- Không chạy nhiều Gradle processes cạnh tranh cùng RAM/CPU mà không giám sát.
- CI resource requests/limits cũng cần được pin để so thời gian hợp lệ.

Ví dụ:

~~~bash
./gradlew :core:test :app:test --parallel --max-workers=2
~~~

Đây là **thử nghiệm performance**, không phải luôn tối ưu. Với lab hai modules nhỏ, overhead có thể nhiều hơn lợi ích.

---

## 10. Reproducible builds và dependency governance

### 10.1. Pin Gradle Wrapper

Commit Wrapper đầy đủ. Nên cấu hình distribution SHA-256 trong gradle-wrapper.properties và xác minh Gradle Wrapper JAR theo quy trình được tài liệu Gradle khuyến nghị. Không chạy arbitrary wrapper scripts từ untrusted MR với high-privilege credentials.

### 10.2. JDK17 không đủ nếu dependencies floating

Nếu dùng dynamic dependency:

~~~groovy
implementation 'org.example:library:1.+'
~~~

hoặc **latest.release**, cùng commit có thể resolve binary mới vào ngày hôm sau. Muốn reproducibility:
- Dùng fixed versions hoặc platform/BOM phù hợp.
- Dùng dependency locking/verification khi cần.
- Dùng internal repository proxy và quản lý supply chain.
- Ghi lại plugin versions, dependency versions và checksums.

Lab pin JUnit BOM version 5.11.4; JUnit Jupiter/Platform artifacts nhận versions từ BOM.

### 10.3. GitLab và Jenkins có thể resolve dependencies khác nhau

Nếu một bên có repository credentials khác, artifact repository mirror khác hoặc network policy khác, resolution có thể khác. Build script phải khai báo repositories và versions rõ; CI chỉ cung cấp môi trường/credentials thông qua cơ chế an toàn.

### 10.4. --offline và --refresh-dependencies không phải defaults CI

**--offline** chỉ dùng artifacts đã cache, có thể fail ở clean runner. **--refresh-dependencies** buộc kiểm tra lại dependencies, tốn network/time; không nên chạy mặc định mọi build trừ khi có lý do.

### 10.5. Không copy local JAR từ build/libs làm dependency

Dùng **implementation project(':core')** cho nội bộ. Nếu app lại khai báo:

~~~groovy
implementation files('../core/build/libs/core.jar')
~~~

một clean CI job chưa có JAR sẽ compile fail; ngay cả khi tồn tại JAR cũ, task dependency và transitive metadata không được đảm bảo. Project dependency là hợp đồng đúng cho multi-project builds.

### 10.6. Builds có thể chạy trên nhiều OS

JVM Java code thường portable, nhưng scripts và output packaging có thể khác Unix/Windows:
- Dấu phân cách classpath khác.
- chmod không có trên Windows.
- Path case sensitivity khác.
- File permissions/archive timestamps có thể khác.
- Native dependencies, shell tasks và locale ảnh hưởng reproducibility.

Khi pipeline cần binary reproducibility, pin container/OS toolchain và kiểm tra checksum/archive normalization, không suy luận mọi zip bytes phải khớp giữa hai máy.

---

## 11. Thiết kế pipeline theo merge request/pull request và nhánh chính

### 11.1. Verification chạy cho thay đổi chưa tin cậy

PR/MR pipeline thường chạy:
- Compile/test/quality checks.
- Không có publishing credentials.
- Không deploy production.
- Không được ghi vào shared remote cache có quyền cao nếu mã chưa tin cậy.
- Không tự thực hiện destructive release operations.

### 11.2. GitLab rules mẫu

Một job release riêng (fragment, không tự chạy trong lab):

~~~yaml
release_application:
  stage: deploy
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
      when: manual
    - when: never
  script:
    - ./gradlew --no-daemon publish
~~~

**Phải thêm deploy vào stages**, cấu hình publishing tasks/repository, protected variables, permissions và approval. Đây không phải khối có thể dán vào pipeline lab rồi chạy ngay, vì lab chưa có **publish**. Chỉ minh họa branch gating và manual approval.

### 11.3. Jenkins when cho branch

Fragment Declarative Pipeline:

~~~groovy
stage('Release') {
    when {
        branch 'main'
    }
    steps {
        input message: 'Approve release?'
        sh './gradlew --no-daemon publish'
    }
}
~~~

**Khi dùng Multibranch Pipeline**, branch directive có semantics tương ứng. Để runnable phải định nghĩa publishing task, credential bindings, access controls và stage order; **main** có thể không phải default branch của mọi repository.

### 11.4. Không phụ thuộc duy nhất vào script if

Branch rules là một lớp, nhưng không thay server-side protected branches/tags, Jenkins job permissions, GitLab protected variables, protected environments và repository credentials permissions. Mã CI có thể bị chỉnh trong PR; secrets không được trao cho untrusted fork code chỉ vì YAML/Jenkinsfile tự hứa không in secret.

### 11.5. Test branch pipeline khác release pipeline

Một design hai luồng:
- MR/PR: **test + package artifact preview**, không publish.
- Protected branch/tag: **test + package + signing/publish/deploy** với approval và provenance.

Cả hai vẫn dùng cùng Gradle tasks khi có thể; release khác ở permissions và output promotion.

---

## 12. Credentials an toàn cho Gradle trong CI

### 12.1. Không hardcode token

Sai:

~~~groovy
publishing {
    repositories {
        maven {
            credentials {
                password = 'real-token-here'
            }
        }
    }
}
~~~

Đừng commit credentials trong build.gradle, .gitlab-ci.yml, Jenkinsfile hoặc gradle.properties của repository. Không bật debug logs chứa Authorization headers, không echo tokens.

### 12.2. Gradle đọc môi trường qua Provider API

Fragment trong project có maven-publish:

~~~groovy
def repoUser = providers.environmentVariable('REPO_USER')
def repoPassword = providers.environmentVariable('REPO_PASSWORD')

publishing {
    repositories {
        maven {
            url = uri('https://repo.example.invalid/releases')
            credentials {
                username = repoUser.getOrElse('')
                password = repoPassword.getOrElse('')
            }
        }
    }
}
~~~

**Đây là fragment về cách nhận credentials**, không phải endpoint publish thực sự: URL là placeholder bất khả dụng cho lab. Trong production, chọn repository URL thật, không để token hiện ở logs. Một số Gradle plugin/configuration APIs nhận Provider trực tiếp; cấu hình cần kiểm tra theo version cụ thể để tránh resolve secrets quá sớm.

### 12.3. GitLab variables

Tạo **REPO_USER**, **REPO_PASSWORD** trong GitLab **Settings → CI/CD → Variables**, bật masked/protected/hidden theo tính năng của instance và policy của team. Chỉ cấp cho protected branches/tags khi deploy.

Không cần viết giá trị token vào YAML; job process nhận env vars được GitLab cung cấp khi rules/permissions cho phép.

### 12.4. Jenkins withCredentials

Fragment trong một release stage có publishing task:

~~~groovy
withCredentials([
    usernamePassword(
        credentialsId: 'maven-release',
        usernameVariable: 'REPO_USER',
        passwordVariable: 'REPO_PASSWORD'
    )
]) {
    sh './gradlew --no-daemon publish'
}
~~~

Jenkins chỉ inject credentials trong block được phép; Jenkins credential ID **maven-release** phải tồn tại. Không in env dumps, không bật shell tracing **set -x**, và đừng tin masking có thể chống mọi cách lộ secrets.

### 12.5. Secret exposure trong Gradle User Home

Gradle User Home có thể chứa gradle.properties, init scripts và logs. Không chia sẻ toàn bộ user home giữa untrusted jobs hoặc archive nó thành artifact tải công khai. Đặt quyền filesystem private và giới hạn remote cache writes.

### 12.6. Nếu cần signing keys

Không đặt signing key text trong Git. Dùng secret file/variable được CI cung cấp trong release stage, cleanup sau khi dùng và kiểm tra artifact signatures. Tách key dùng production với preview builds.

---

## 13. Những cải tiến Gradle nên được giữ trong build scripts

### 13.1. Tạo task quality gate thống nhất

Trong ứng dụng thật, có thể dùng:

~~~bash
./gradlew :core:check :app:check
~~~

thay cặp test tasks nếu các checks bao gồm lints, static analysis, tests, coverage verification. Khi đó cả GitLab và Jenkins phải đổi command cùng lúc.

### 13.2. Không viết shell grep để đếm errors thay Gradle

Sai về thiết kế:

~~~bash
./gradlew test | grep FAILED
~~~

Một pipeline shell có thể trả exit code của grep thay vì Gradle, vô tình che compile/test failures tùy shell. Chạy Gradle trực tiếp để CI nhận đúng exit code, rồi dùng JUnit XML/reporting API để đọc tests.

Nếu cần log capture, dùng cơ chế shell pipefail chính xác và kiểm tra exit code, không dựa vào text “BUILD SUCCESSFUL” tự parse.

### 13.3. Không chạy --continue để phát hành khi tests fail

**--continue** yêu cầu Gradle thực hiện thêm các tasks độc lập sau failure, hữu ích để thu nhiều lỗi trong cùng một CI verification run, nhưng **build vẫn phải fail**. Không dùng **ignoreFailures=true** hoặc GitLab **allow_failure:true** cho quality gates bắt buộc.

### 13.4. Đặt quality checks trước publishing

Publishing task có side effect ghi repository, không thể coi là task cacheable bình thường. Chỉ gọi publish trên trusted, gated branch/tag, sau khi test/quality passes. Nếu cần **chính artifact đã test** được publish, thiết kế pipeline để build một lần và truyền artifact đã kiểm chứng qua artifact repository hoặc CI artifacts có checksum/provenance.

### 13.5. Tên task có thể khác tùy plugin

Core Java plugin có **test**, **check**, **jar**. Application plugin có **run**, **distZip**, **distTar**. Android, Kotlin Multiplatform, custom Test Suites có task names khác. Luôn xác minh:

~~~bash
./gradlew tasks --all
./gradlew :app:tasks --all
~~~

Không giả định **:app:distZip** tồn tại trong project chỉ áp **java-library** mà không có Application/Distribution plugin.

---

## 14. Tối ưu hiệu năng pipeline mà không giảm độ tin cậy

### 14.1. Đo baseline trước

Ghi:
- Total job wall time GitLab/Jenkins.
- Gradle startup/configuration/task execution.
- Wrapper download time.
- Dependency cache hits/downloads.
- Build cache hits (FROM-CACHE).
- Số tasks UP-TO-DATE, tests count.
- CPU/RAM của runner.
- Artifact upload/download time.

**Không coi GitLab job duration là Gradle task execution time**: job duration còn gồm image pull, checkout, cache restore, script overhead và artifact upload.

### 14.2. Cache Wrapper trước

Tại GitLab shared runner, wrapper-only cache dễ đo và giảm download distribution. Nếu quá nhỏ để có lợi, vẫn có thể bỏ; không ép cache mọi thứ.

### 14.3. Gradle Remote Build Cache

Khi nhiều ephemeral runners hoặc Jenkins agents phải compile cùng inputs, một **Gradle Remote Build Cache** có thể chia sẻ cacheable task outputs. Điều kiện:
- Build logic model inputs/outputs đúng.
- Toolchain/Gradle versions đủ thống nhất.
- Outputs deterministic/relocatable.
- Cache service có TLS/access controls.
- Quyền push giới hạn trusted CI.
- Không lưu secrets trong cached outputs.

### 14.4. Configuration cache

Có thể thử:

~~~bash
./gradlew :core:test :app:test --configuration-cache
~~~

Nhưng không phải mọi build logic/plugin tương thích ngay. Trong CI ephemeral, configuration cache hit có thể hiếm nếu state không persisted, nhưng bật kiểm tra compatibility vẫn có lợi. Không trộn metrics trước/sau khi đổi nhiều flags.

### 14.5. Jenkins daemon reuse

Jenkins long-lived agent có thể dùng Gradle Daemon để giảm startup, nếu agents tách trust domains và quản lý memory. GitLab ephemeral container thường dùng --no-daemon. Hai nền tảng có thể có times khác nhau dù compile/test semantics giống nhau.

### 14.6. Không cache build/ bừa bãi

**build/** chứa Gradle outputs, nhưng cache/upload cả build/ giữa jobs không luôn an toàn, có thể:
- Kéo outputs cũ ngoài provenance.
- Phá Gradle task history assumptions.
- Dễ bị race/overlap.
- Tốn mạng/archiving time.
- Gây nhầm output cần phát hành.

Nếu stage cần một sản phẩm cụ thể, dùng **artifacts**; nếu muốn tăng tốc tasks, dùng **Gradle build cache** được thiết kế cho task outputs.

### 14.7. Test parallelism

Gradle Test tasks có **maxParallelForks** và **forkEvery**; trong build thật, một số tests không an toàn để chạy parallel. Bắt đầu từ correctness, tăng concurrency có đo CPU/RAM, không thay concurrency giữa hai CI vendors rồi giải thích sự khác biệt bằng Gradle.

---

## 15. Troubleshooting GitLab CI theo triệu chứng

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| **./gradlew: Permission denied** | Executable bit thiếu | chmod +x gradlew hoặc commit executable bit đúng |
| **gradlew: not found** | Chạy sai working directory/Wrapper thiếu | Kiểm tra checkout và files |
| **Unable to find image** | Runner không có Docker executor hoặc image tag/network lỗi | Kiểm tra runner executor/Image Registry |
| **Java version not supported** | JDK không tương thích Gradle Wrapper | Pin JDK/toolchain, xem Gradle compatibility |
| **No matching toolchains found** | Image thiếu JDK17 theo toolchain config | Cung cấp JDK đúng hoặc provisioning |
| **Could not resolve junit...** | Maven Central không truy cập, DNS/proxy/SSL | Cấu hình repository mirror/credentials/network |
| **JUnit tab trống** | XML path glob sai, tests chưa chạy | Xem build/test-results/test, CI artifacts |
| **Tests failed nhưng package vẫn chạy** | allow_failure:true hoặc stages/rules không gating | Bỏ allow_failure, kiểm stage graph |
| **Cache không hit giữa jobs** | Runner cache backend/key khác hoặc eviction | Kiểm cache settings và policy; coi cache là optional |
| **cache.zip quá lớn** | Đang cache toàn .gradle/caches không chọn lọc | Wrapper-only hoặc remote cache |
| **Reports không upload khi job fail** | artifacts.when không always | Đặt when: always cho JUnit/report job |
| **Missing ZIP artifact** | Task distZip chưa chạy hoặc path glob sai | Xem :app:distZip outputs và artifact paths |
| **Runner shell bỏ qua image** | Shell executor không chạy container image | Cài JDK trên host hoặc dùng Docker executor |
| **No permissions for protected variables** | Job không ở protected ref | Kiểm rules, protected variables/branches |
| **Changes only affect one module nhưng build quá lâu** | CI luôn clean, cache miss hoặc compile scope lớn | Đo profile, review task inputs/CI strategy |
| **Artifacts expired** | expire_in ngắn hoặc retention policy | Đổi retention hợp lý; release artifact lưu riêng |
| **MR from fork lộ token** | Secrets gán vào untrusted pipeline | Restrict variables/runners/trust boundary |
| **Job dùng Gradle version khác dev** | Dùng gradle CLI thay Wrapper | Chuyển sang ./gradlew và pin wrapper |

### 15.1. Lệnh debug trong GitLab job

~~~bash
pwd
java -version
./gradlew --version
./gradlew :core:tasks --all
./gradlew :app:tasks --all
./gradlew --no-daemon --info :core:test :app:test
~~~

Tránh **env** hoặc **printenv** toàn bộ khi job có credentials. Để debug dependencies, có thể chạy **dependencies --configuration testRuntimeClasspath** trong môi trường không làm lộ internal repository secrets.

---

## 16. Troubleshooting Jenkins theo triệu chứng

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| **No such DSL method junit** | Jenkins JUnit plugin/step không cài | Cài/enable plugin tương ứng |
| **No such DSL method archiveArtifacts** | Pipeline Basic Steps/Core plugin không có | Kiểm Jenkins plugins |
| **No tool named jdk17** | tools JDK chưa được cấu hình | Manage Jenkins → Tools, tạo JDK đúng tên |
| **sh: command not found** | Agent Windows hoặc không có POSIX shell | Dùng bat hoặc đổi Linux agent |
| **checkout scm** lỗi | SCM context/credentials/repo URL không hợp lệ | Sửa Pipeline from SCM/Multibranch config |
| **Pipeline always SUCCESS dù Gradle test fail** | returnStatus bỏ qua, catchError hoặc shell piping | Để sh fail theo exit code |
| **JUnit report empty** | Tests chưa chạy, glob sai, XML khác path | Kiểm files dưới build/test-results |
| **Artifact archiving failed** | ZIP không có vì stage Package fail | Xem task :app:distZip và post.success |
| **Workspace bị ghi chồng** | Builds chạy đồng thời/agent workspace reuse | disableConcurrentBuilds/isolated workspaces |
| **Gradle User Home permission denied** | File owner/quyền agent sai | Sửa permissions, private agent cache |
| **Java version mismatch** | Jenkins tool JDK khác toolchain/Wrapper | Kiểm java -version, ./gradlew --version |
| **Failed to connect to daemon** | Daemon state/JVM memory/network permissions | --stop trong môi trường riêng, xem daemon logs |
| **Test report có 0 tests nhưng xanh** | allowEmptyResults=true hoặc skip test task | Add guard test count, gọi tasks thực |
| **Pipeline checkout hai lần** | Default checkout + explicit checkout | skipDefaultCheckout(true) hoặc bỏ explicit checkout |
| **Job dùng Gradle installation Jenkins** | Pipeline gọi gradle thay ./gradlew | Chuyển sang Wrapper |
| **Publish từ PR không được phép** | Branch gating/credentials policy thiếu | protected stages/credentials/approval |
| **Agent cache đầy ổ** | ~.gradle tồn tại lâu, cleanup thiếu | Cache cleanup policy/monitor disk |
| **Artifacts bị mất giữa agents** | Không stash/unstash/archive | Dùng artifact handoff rõ |
| **Các branches dùng chung writable cache** | Thiếu workspace/cred isolation | Separate Gradle homes/permissions/remote cache policy |

### 16.1. Kiểm tra Jenkinsfile trước khi merge

- Dùng Jenkins Declarative Pipeline linter/Replay/test branch theo policy.
- Xác nhận mọi Jenkins plugins/steps đều được cài.
- Xác nhận agent type, JDK tool ID, SCM context.
- Chạy pipeline thật; parse Jenkinsfile thành công không chứng minh Gradle tasks có thể chạy.
- Kiểm tra JUnit UI và artifact archive sau thành công/thất bại.

---

## 17. Các trường hợp nâng cao: monorepo, modules và phân tách jobs

### 17.1. Monorepo có nhiều modules

Trong Gradle multi-project build:

~~~bash
./gradlew :api:test :service:test :web:test
~~~

là lựa chọn tường minh. Khi số modules tăng, có thể dùng root **check** hoặc các convention/plugin-defined aggregate verification tasks. Đừng suy đoán tên project chỉ từ filesystem; tất cả modules phải được include trong settings.

### 17.2. Split test jobs theo module

GitLab có thể chạy unit tests modules song song bằng jobs:

~~~yaml
test_core:
  stage: test
  script:
    - ./gradlew :core:test
  artifacts:
    when: always
    reports:
      junit: "core/build/test-results/test/TEST-*.xml"

test_app:
  stage: test
  script:
    - ./gradlew :app:test
  artifacts:
    when: always
    reports:
      junit: "app/build/test-results/test/TEST-*.xml"
~~~

**Alternative fragment**, không dán thêm vào pipeline lab nếu muốn giữ một job unit_tests. Nếu split, cả hai jobs phải pass mới cho package stage; có thể tăng tốc khi runner capacity đủ, nhưng tăng số Gradle startups/cache duplication.

### 17.3. Jenkins parallel test stages

Declarative Pipeline có directive **parallel**. Ví dụ:

~~~groovy
stage('Test Parallel') {
    parallel {
        stage('Core') {
            steps {
                sh './gradlew :core:test'
            }
        }

        stage('App') {
            steps {
                sh './gradlew :app:test'
            }
        }
    }
}
~~~

**Alternative fragment**; phải xem Jenkins agent/workspace isolation. Hai Gradle invocations **không nên cùng ghi chung project build/ directories hoặc Gradle User Home bất cẩn**. An toàn hơn là mỗi nhánh dùng agent/workspace riêng hoặc giữ một Gradle invocation với task parallelism nội bộ.

### 17.4. Artifact handoff bắt buộc

Nếu build job tạo một ZIP đã được kiểm thử và deploy job phải dùng **chính ZIP đó**, GitLab dùng **artifacts + needs**; Jenkins dùng **stash/unstash** trong cùng Pipeline hoặc một artifact repository. Không cho deploy job tự build lại source nếu yêu cầu provenance chính xác của tested binary.

### 17.5. Checksum và provenance

Pipeline nên gắn artifact với commit SHA, Gradle/JDK versions, build ID và checksum. Một artifact filename như **app.zip** không đủ để chứng minh nó đến từ commit nào.

Có thể dùng OS tools **sha256sum** hoặc **Get-FileHash** khi build artifact đã tồn tại; giữ hash manifest trong artifact storage/release metadata.

### 17.6. Dynamic versions gây khác artifact dù cùng commit

Nếu dependency dùng dynamic/changing versions, hai jobs cùng source commit nhưng chạy khác thời điểm có thể resolve artifacts khác. Dependency locking/verification, fixed versions và artifact promotion giúp reproducibility.

---

## 18. Tích hợp chất lượng Gradle: từ test đến check và coverage

### 18.1. Một task CI contract

Khi project đã có Quality plugins, có thể công bố một **CI entrypoint** ở Gradle:

~~~groovy
tasks.register('ciVerify') {
    group = 'verification'
    dependsOn(
        ':core:check',
        ':app:check'
    )
}
~~~

Đây là fragment trong **root build.gradle** khi :core và :app áp Java plugins và có check tasks; nó minh họa logic CI verification được đặt trong Gradle thay vì copy danh sách tasks vào hai CI DSLs.

Lúc này GitLab và Jenkins đều có thể dùng:

~~~bash
./gradlew --no-daemon ciVerify
~~~

### 18.2. Nếu cần JaCoCo

Java module:

~~~groovy
plugins {
    id 'java'
    id 'jacoco'
}
~~~

rồi cấu hình **jacocoTestReport**/**jacocoTestCoverageVerification** theo coverage policy. **jacocoTestCoverageVerification** không được check tự gọi trong mọi cấu hình; nếu muốn gate, nối **check.dependsOn** phù hợp.

GitLab có thể upload XML/HTML coverage và Jenkins archive reports; bản thân JUnit XML không đo line/branch coverage.

### 18.3. Static analysis

Checkstyle/SpotBugs/PMD có tasks và reports riêng. Pipeline chỉ gọi common Gradle task/check lifecycle, không viết phân tích lỗi duplicated trong YAML/Jenkinsfile.

### 18.4. Integration tests

Nếu integrationTest cần Docker/database, CI phải cung cấp services/containers; build Gradle cần test suite và dependency graph rõ. GitLab services và Jenkins Docker agent/testcontainers infrastructure là khác nhau ở orchestration, nhưng **test task Gradle và expected behavior** vẫn cần cùng contract.

### 18.5. Khi check không tồn tại

Một root project chỉ áp **base** có thể không có một task test riêng. Tạo CI entrypoint phù hợp/fully qualified tasks; đừng lầm vì một task tên **check** thành công mà không chạy bất kỳ tests. Log phải chứng minh đúng Test tasks đã được thực thi hoặc được hợp lệ UP-TO-DATE/FROM-CACHE theo policy.

---

## 19. CI pipeline debugging một cách có hệ thống

### 19.1. Phân loại lỗi

1. **Executor failure**: container image không pull, Jenkins agent offline.
2. **Checkout failure**: token SCM, branch/commit, submodules.
3. **Environment failure**: JDK/Gradle Wrapper/certificates.
4. **Dependency resolution failure**: Maven registry, proxy, TLS, credentials.
5. **Build configuration failure**: plugin resolution, Groovy/Kotlin DSL syntax, project path.
6. **Compilation failure**: source Java/Kotlin hoặc toolchain mismatch.
7. **Test failure**: JUnit assertion/application behavior.
8. **Reporting failure**: glob XML/HTML/artifact path sai.
9. **Packaging failure**: distZip/jar/distribution task.
10. **Publishing failure**: credentials, authorization, repository endpoints/approvals.

Giải đúng tầng; đừng tắt tests vì cache bị miss, hoặc thêm global Gradle installation vì một artifact path sai.

### 19.2. Lệnh triage ít gây tác động

~~~bash
java -version
./gradlew --version
./gradlew projects
./gradlew :app:tasks --all
./gradlew --no-daemon :core:test :app:test --stacktrace
~~~

**--stacktrace** hữu ích để thấy lỗi Gradle; **--info** tăng log chi tiết; **--debug** có thể in thông tin nhạy cảm, nên chỉ dùng có kiểm soát. Không in toàn bộ env variables.

### 19.3. Kiểm tra JUnit XML path

Lệnh Linux/POSIX:

~~~bash
find core/build/test-results app/build/test-results \
    -type f -name 'TEST-*.xml'
~~~

Nếu không có, xác minh Test tasks chạy chưa và reports.junitXml.required có bật. Không xóa XML cũ rồi dùng số lượng XML có sẵn trong một workspace lâu sống như bằng chứng test run mới.

### 19.4. Kiểm tra distribution

~~~bash
find app/build/distributions -maxdepth 1 \
    -type f -name '*.zip'
~~~

Nếu không có, chạy **./gradlew :app:distZip** trực tiếp trong cùng môi trường CI và đọc lỗi. Đừng thay CI glob thành mọi ZIP của repository khi có nguy cơ lấy sản phẩm sai.

### 19.5. Kiểm tra commit

GitLab thường có **CI_COMMIT_SHA**; Jenkins Multibranch checkout có **GIT_COMMIT** tùy plugin/SCM. In commit ID không chứa secret nhưng cần xác nhận checkout đang ở SHA intended. Nếu build chạy tag/merge commit đặc biệt, ghi rõ identity trước khi publish.

---

## 20. Bài tập thực hành và đáp án

### Bài 1 — Vì sao dùng ./gradlew thay gradle?

**Đáp án:** Wrapper pin Gradle distribution theo repository; không phụ thuộc bản cài trên runner/Jenkins agent. Giảm version drift.

### Bài 2 — GitLab dùng image Java17 nhưng Jenkins dùng JDK21

**Đáp án:** CI environments không đồng nhất. Dù Java toolchain target17 có thể compile cùng bytecode, Gradle daemon/runtime và plugins vẫn có thể khác. Pin/kiểm tra JDK theo policy trước khi so kết quả/timing.

### Bài 3 — Tests fail nhưng GitLab package vẫn chạy

**Đáp án:** kiểm tra stage graph, allow_failure/needs/rules và script exit code. Quality gate phải chặn package.

### Bài 4 — Jenkins sh trả nonzero thì sao?

**Đáp án:** mặc định step fail, Declarative Pipeline dừng các stages tiếp theo bình thường; post.always vẫn có thể thu JUnit reports.

### Bài 5 — JUnit XML khác HTML report thế nào?

**Đáp án:** XML là machine-readable test results để CI tích hợp; HTML dùng người xem. Cần artifacts:reports:junit ở GitLab, junit step ở Jenkins.

### Bài 6 — JUnit report khi test fail có nên upload?

**Đáp án:** có, dùng artifacts.when:always hoặc post.always, nhưng **không** set ignoreFailures/allow_failure để đổi trạng thái build thành xanh.

### Bài 7 — GitLab cache có thay artifacts không?

**Đáp án:** không. Cache là optimization không bảo đảm sẵn; artifacts là cơ chế lưu/chuyển kết quả của job.

### Bài 8 — Jenkins stage sau dùng file build/ cũ từ máy khác?

**Đáp án:** không an toàn. Dùng stash/unstash/archive/artifact repository hoặc chạy Gradle tasks từ source đúng commit ở stage mới.

### Bài 9 — GRADLE_USER_HOME dùng làm gì?

**Đáp án:** Gradle distributions, dependency cache, init scripts, logs, local build cache và properties. GitLab có thể đặt trong CI_PROJECT_DIR để cache paths hợp lệ; cần bảo vệ secrets.

### Bài 10 — Nên cache toàn bộ .gradle mặc định?

**Đáp án:** không. Cân nhắc kích thước, cache I/O, runner backend và nguy cơ secrets; wrapper-only cache là baseline tốt trên shared runners.

### Bài 11 — Task FROM-CACHE là GitLab cache hit?

**Đáp án:** không nhất thiết. FROM-CACHE là trạng thái Gradle task output cache; GitLab cache chỉ cung cấp lưu trữ folders.

### Bài 12 — Thin app.jar có tự chứa core.jar?

**Đáp án:** không. Dùng Application plugin distZip hoặc cấu hình packaging phù hợp để phân phối dependencies, không coi JAR mỏng là artifact standalone.

### Bài 13 — Một module có project(':core'), CI có cần build core.jar trước?

**Đáp án:** không cần thủ công. Gradle biết project dependency và chọn producer artifact/classes phù hợp. Không thêm lệnh xây JAR bằng tay vào CI.

### Bài 14 — Vì sao lab test có thể chạy lần đầu chậm?

**Đáp án:** Wrapper distribution và JUnit dependencies cần tải, JDK/daemon/JIT cold, Gradle configuration cache chưa có; đó khác compile/test logic correctness.

### Bài 15 — GitLab runner shell executor dùng image không?

**Đáp án:** image directive không tự tạo container trong Shell executor; cần JDK17 trên host hoặc đổi runner executor phù hợp.

### Bài 16 — Jenkins tools jdk 'jdk17' fail?

**Đáp án:** Jenkins administrator chưa cấu hình JDK tool có tên jdk17; tạo tool hoặc dùng container/agent provisioning.

### Bài 17 — Windows Jenkins agent chạy sh?

**Đáp án:** không đúng. Dùng bat và gradlew.bat, không gọi chmod; có thể tạo Jenkinsfile đa nền tảng có branching riêng khi cần.

### Bài 18 — Main.java in gì?

**Đáp án:** **CI_OK: 5** đúng một dòng từ Java main với Calculator.add(2,3). Gradle logs còn có thêm.

### Bài 19 — Tổng số tests trong lab?

**Đáp án:** ba JUnit tests (hai core, một app) nếu đủ source files và test platform được resolve/chạy. Actual durations tùy môi trường.

### Bài 20 — Không thấy XML nhưng pipeline xanh

**Đáp án:** kiểm test tasks, path globs, test discovery, allowEmptyResults. Đặt guard bắt buộc report/test count theo policy; không xem missing XML là pass.

### Bài 21 — MR từ fork có thể chạy release?

**Đáp án:** không nên. Release cần branch/tag protection, credentials restrictions và approvals ngoài script conditions.

### Bài 22 — withCredentials có an toàn tuyệt đối không?

**Đáp án:** không. Nó giới hạn/phơi bày env secrets theo block và Jenkins masking, nhưng code độc hại có thể chủ động exfiltrate; chỉ cấp trên trusted jobs/agents.

### Bài 23 — Cùng commit nhưng ZIP hash khác?

**Đáp án:** kiểm JDK/OS/Gradle/plugin versions, archive timestamps/file order/permissions/dependency resolution và build script reproducibility trước khi kết luận. Cùng semantics không tự bảo đảm byte-for-byte identical.

### Bài 24 — Dùng cache thay remote artifact repository để release?

**Đáp án:** không. Release cần artifact provenance, immutability, version/signature/retention và permission policy; cache có thể bị eviction và không phải cơ chế phát hành.

### Bài 25 — Khi nào dùng :core:check :app:check thay test?

**Đáp án:** khi Gradle đã nối đầy đủ lint, unit tests, static analysis, coverage gates vào check lifecycle. Cả hai CI phải dùng cùng tasks.

### Bài 26 — Vì sao không cần chmod trên Windows?

**Đáp án:** gradlew.bat là batch script; Unix executable permission của gradlew không áp dụng cùng cách trên Windows.

### Bài 27 — Jenkins checkout scm cần gì?

**Đáp án:** Jenkins job SCM context và credentials được cấu hình đúng; không phải phép màu tự tìm repository từ thư mục workspace.

### Bài 28 — Cách kiểm tra pipeline equivalence?

**Đáp án:** cùng commit/Wrapper/JDK/toolchain, cùng Gradle task selectors, JUnit results/test count, distribution artifacts và failure gating; khác biệt runner speed/cache states không nhất thiết làm semantics khác.

### Bài 29 — Dùng --offline mặc định mọi CI có tốt?

**Đáp án:** không. Clean runner thiếu cached artifacts sẽ fail; offline phù hợp khi dependency closure đã được chuẩn bị và policy yêu cầu.

### Bài 30 — Hai jobs GitLab package/test có dùng một workspace?

**Đáp án:** không nên giả định. Runner có thể checkout cùng commit vào các containers khác nhau; package tự build từ source, bắt buộc transfer thì dùng artifacts/needs.

### Bài 31 — CI pipeline dùng grep để xác định BUILD SUCCESSFUL?

**Đáp án:** không. Dựa vào process exit code của Gradle tasks và machine-readable reports, không parse console text bằng grep dễ che lỗi pipeline.

### Bài 32 — CI có nghĩa phải chạy --no-daemon?

**Đáp án:** không bắt buộc. Ephemeral runners có thể phù hợp, long-lived Jenkins agents có thể hưởng lợi từ daemon reuse. Đo performance và quản lý tài nguyên theo environment.

### Bài 33 — Build cache là bảo chứng correctness?

**Đáp án:** không. Nếu task model hidden inputs sai, cache có thể tái sử dụng artifact không đúng; cần tests, Gradle input/output contracts và trust controls.

### Bài 34 — Jenkins archiveArtifacts có thay publish Maven module không?

**Đáp án:** không. Archiving giữ file dưới Jenkins build record; publication tới Maven repository cần coordinates, metadata, credentials và Gradle maven-publish tasks.

### Bài 35 — CI verification đã xanh, có tự động deploy được không?

**Đáp án:** cần thêm artifact provenance, approvals, protected credentials/branches và target environment checks; không coi test pass là toàn bộ release authorization.

---

## 21. Checklist triển khai trước khi merge pipeline

- [ ] Repository có Gradle Wrapper đầy đủ và được xác minh checksum?
- [ ] Gradle Wrapper version được pin và phù hợp JDK runtime?
- [ ] Java toolchains/options.release được khai báo trong Gradle?
- [ ] GitLab và Jenkins dùng cùng Gradle task selectors?
- [ ] Không chạy system gradle thay vì ./gradlew?
- [ ] Lab/local build đã qua compile/test/package trước khi đưa CI?
- [ ] Gradle project dependencies dùng project(':...'), không hardcode JAR path?
- [ ] Test stage chạy đủ modules/suites quan trọng?
- [ ] Có positive và negative/edge-case assertions trong tests?
- [ ] Test failure giữ CI exit code nonzero?
- [ ] Package/deploy stage không chạy khi tests fail?
- [ ] GitLab artifacts:reports:junit đúng XML path?
- [ ] GitLab artifacts.when:always cho test reports?
- [ ] Jenkins post.always có junit step đúng glob?
- [ ] Jenkins không vô tình bỏ qua nonzero sh return?
- [ ] Không dùng allowEmptyResults làm quality pass policy khi thiếu tests?
- [ ] HTML report chỉ dùng để xem, XML dùng CI test UI?
- [ ] Distribution ZIP/JAR artifacts được chọn đúng task output?
- [ ] Artifact từ job nào và commit nào được ghi rõ?
- [ ] Caching không dùng thay artifacts bắt buộc?
- [ ] GRADLE_USER_HOME có permissions/isolation hợp lý?
- [ ] Cache key có invalidation policy khi Wrapper/dependencies thay?
- [ ] Không archive secrets, init scripts hoặc Gradle User Home toàn bộ?
- [ ] GitLab runner executor hỗ trợ image hoặc JDK được cài trên host?
- [ ] Jenkins agent Linux/Windows khớp sh/bat và tool JDK?
- [ ] SCM checkout đúng branch/commit SHA?
- [ ] Plugin/JUnit dependencies có repository/mirror tin cậy?
- [ ] No-op/incremental/clean performance được đo riêng?
- [ ] CI không bật --refresh-dependencies hay clean không có lý do?
- [ ] Mã PR/MR không có quyền phát hành và không truy cập production secrets?
- [ ] Protected branch/tag/environment và approvals được cấu hình server-side?
- [ ] Publishing credentials dùng protected variables/Jenkins Credentials?
- [ ] Có retention policy cho reports/artifacts và disk cleanup?
- [ ] Có cơ chế đo/đọc Gradle task outcomes: UP-TO-DATE/FROM-CACHE/EXECUTED?
- [ ] Quality gates và artifact promotion đã được kiểm thử bằng trường hợp cố ý fail?
- [ ] Nếu CI chạy nhiều agents/jobs, workspace/cache không bị ghi chồng?
- [ ] Repository không chứa token, absolute developer paths hoặc môi trường giả định?
- [ ] Có quy trình update Wrapper/JDK/plugins và regression pipeline tests?

## 22. Tài liệu chính thức và nguồn tham khảo

- [Gradle — Gradle on GitLab CI](https://docs.gradle.org/current/userguide/gitlab-ci.html): minimal .gitlab-ci.yml, Wrapper, JUnit artifacts, cache strategies, protected release pipelines.
- [Gradle — Gradle on Jenkins](https://docs.gradle.org/current/userguide/jenkins.html): Jenkinsfile examples, JUnit reports, archive/caching, credentials.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): wrapper task, scripts, wrapper JAR validation, distribution checksum.
- [Gradle — Continuous Integration](https://docs.gradle.org/current/userguide/continuous_integration.html): khuyến nghị Gradle và CI.
- [Gradle — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): project dependency, api/implementation.
- [Gradle — The Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): run, distZip, distribution archives.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): JUnit Platform, Test task, XML/HTML reports.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cacheable task outputs, FROM-CACHE.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration reuse, compatibility.
- [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html): GRADLE_USER_HOME, daemon and JVM options.
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html): protected Gradle User Home, credentials/secrets.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): JDK/Gradle versions.
- [GitLab — Caching in CI/CD](https://docs.gitlab.com/ci/caching/): cache key, scope, cache so với artifacts.
- [GitLab — Job Artifacts](https://docs.gitlab.com/ci/jobs/job_artifacts/): artifacts paths, retention, dependency passing.
- [GitLab — Unit Test Reports](https://docs.gitlab.com/ci/testing/unit_test_reports/): artifacts:reports:junit, MR/Pipeline UI.
- [GitLab — CI/CD YAML Reference](https://docs.gitlab.com/ci/yaml/): image, stages, jobs, rules, artifacts, cache.
- [Jenkins — Pipeline Syntax](https://www.jenkins.io/doc/book/pipeline/syntax/): Declarative agent/tools/stages/steps/post/when.
- [Jenkins — Using a Jenkinsfile](https://www.jenkins.io/doc/book/pipeline/jenkinsfile/): SCM checkout, credentials, testing, pipelines as code.
- [Jenkins — Pipeline Steps for JUnit](https://www.jenkins.io/doc/pipeline/steps/junit/): junit step và test reporting.
- [Jenkins — Pipeline Basic Steps](https://www.jenkins.io/doc/pipeline/steps/workflow-basic-steps/): archiveArtifacts, stash/unstash.
- [Jenkins — Credentials Binding Plugin](https://www.jenkins.io/doc/pipeline/steps/credentials-binding/): withCredentials và secrets best practices.

**Kết luận:** **GitLab CI và Jenkins là hai cách điều phối cùng một Gradle build, không phải hai build systems khác nhau.** Hãy chuẩn hóa Gradle Wrapper, JDK/toolchain và các task Gradle; dùng GitLab jobs/stages hay Jenkins stages/steps để thực thi cùng hợp đồng; publish JUnit XML và artifacts theo cơ chế riêng của mỗi nền tảng; cache chỉ để tối ưu; giữ test failure thành pipeline failure; giới hạn secrets và deployment theo trust boundary. Khi một build chạy thành công từ checkout sạch với cùng Gradle tasks trên cả GitLab và Jenkins, bạn có nền tảng CI/CD có thể vận hành, đo đạc và mở rộng an toàn.