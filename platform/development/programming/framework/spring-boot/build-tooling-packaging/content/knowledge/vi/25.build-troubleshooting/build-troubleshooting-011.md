# Xử lý cache cũ, đầu ra không được tạo lại và bản dựng không tái lập trong Spring Boot

## 1. Mục tiêu và nguyên tắc chẩn đoán

Khi sửa code hoặc dependency nhưng JAR/image vẫn giống bản cũ, file generated không đổi, hoặc hai lần build cùng source cho ra digest khác nhau, nguyên nhân có thể nằm ở nhiều tầng. Một lệnh clean tổng quát có thể làm triệu chứng biến mất tạm thời nhưng không chỉ ra lỗi nằm ở đâu.

Bài học dùng **Java 17, Spring Boot 3.3.13**, Maven hoặc Gradle, Docker BuildKit và Cloud Native Buildpacks (CNB). Phiên bản được chọn làm ví dụ; dự án thực tế cần đối chiếu plugin, wrapper và builder đang dùng. Các command dưới đây là hướng dẫn, không phải kết quả build đã chạy.

Sau khi hoàn thành, bạn có thể:

1. Phân biệt dependency cache, task-output cache, incremental build state, Docker layer cache, CNB cache và runtime cache.
2. Tìm lý do Maven/Gradle không chạy lại task hoặc goal cần thiết.
3. Xác định file JAR/WAR/image thực sự được tạo và đang được sử dụng.
4. Sửa task generated output khai báo thiếu input/output khiến Gradle bỏ qua việc tạo lại.
5. Làm mới dependency có kiểm soát mà không xóa toàn bộ local repository.
6. Kiểm chứng một bản build có tái lập từng byte hay không và tìm nguyên nhân sai khác.

**Nguyên tắc:** xác định output sai ở đâu, task nào tạo nó, và input nào ảnh hưởng đến output. Sau đó mới chọn biện pháp khắc phục.

## 2. Phân biệt các loại cache

| Cơ chế | Lưu gì? | Dấu hiệu | Làm mới đúng phạm vi |
| --- | --- | --- | --- |
| Maven local repository | Dependency/plugin artifacts và metadata đã resolve. | Maven dùng version cũ hoặc SNAPSHOT chưa cập nhật. | Kiểm tra dependency tree; dùng -U có chủ đích; purge đúng artifact nếu hỏng. |
| Gradle dependency cache | Metadata và artifact của module dependency. | Dependency resolution dùng metadata/version cũ. | --refresh-dependencies; kiểm tra lock và dependencyInsight. |
| Gradle incremental state | Thông tin inputs/outputs của task trong workspace. | Task hiện UP-TO-DATE dù developer nghĩ input đã đổi. | Sửa khai báo inputs/outputs; --rerun-tasks để chẩn đoán. |
| Gradle build cache | Output của task cacheable, local hoặc remote. | Task hiện FROM-CACHE và khôi phục output đã build trước. | --no-build-cache để thử không lấy output cache; clean chỉ xóa project outputs. |
| Docker BuildKit cache | Kết quả Dockerfile instructions/layers. | Một RUN vẫn dùng kết quả cũ dù package repository ngoài mạng đã có bản mới. | --no-cache hoặc --no-cache-filter; --pull để cập nhật base image. |
| CNB build cache | Cached layers do buildpacks đóng góp. | Build image restore layer cũ hoặc cache không được reuse. | cleanCache của Spring Boot plugin hoặc cache policy của pack/CNB. |
| CNB launch layers/previous image | Layer có thể tái sử dụng từ image trước hoặc registry. | Image export reuse runtime layer khi metadata còn hợp lệ. | Kiểm tra previous image và metadata; không đánh đồng với build cache volume. |
| Build workspace | File tạm trong builder/buildpacks. | Workspace volume phình to hoặc chứa file tạm cũ. | Quản lý workspace theo project/image và lifecycle riêng. |
| Runtime cache | Redis, HTTP cache, local cache, session, application data. | Container mới vẫn trả dữ liệu cũ dù image đúng. | Điều tra cache contract của ứng dụng; không dùng Maven/Gradle clean. |

### 2.1. Incremental build khác build cache

- **UP-TO-DATE:** Gradle so sánh inputs/outputs của task trong workspace hiện tại và bỏ qua task khi không có thay đổi cần xử lý.
- **FROM-CACHE:** Gradle tìm output của task theo cache key và phục hồi output từ local/remote build cache.
- **Dependency cache:** lưu metadata và binaries của libraries; không phải output của task compile/package.
- **Configuration cache:** lưu kết quả cấu hình build; không phải cache JAR/classes.

Maven có local repository cho dependencies/plugins và clean lifecycle để xóa generated project output. Không giả định Maven có cùng task-output cache model với Gradle.

### 2.2. Output cũ không nhất thiết do cache

Các nguyên nhân thường gặp:

- Đang xem nhầm plain JAR thay vì Boot JAR, nhầm module hoặc thư mục build.
- Goal/task tạo artifact chưa được gọi hoặc không nằm trong lifecycle/task graph.
- Maven profile chưa active, Gradle task bị exclude hoặc có điều kiện onlyIf.
- Generated source/resource nằm ngoài source set hoặc chưa nối vào compile/processResources.
- App/container vẫn chạy image ID cũ dù tag đã được cập nhật.
- Artifact bị copy sang thư mục deploy trước khi build hoàn tất.
- Dependency version thực tế khác với version developer nhìn thấy trong file khai báo.
- Runtime cache hoặc browser cache trả dữ liệu cũ trong khi binary đã mới.

## 3. Quy trình chẩn đoán có bằng chứng

Trước khi xóa cache, thu thập:

1. Git commit và trạng thái working tree.
2. Java/JDK, Maven hoặc Gradle Wrapper version.
3. Build command, profile, properties và task/goal được gọi.
4. Tên và đường dẫn artifact dự kiến.
5. Artifact có tồn tại không, size, modified time và SHA-256.
6. Task outcomes hoặc Maven plugin goals trong log.
7. Dependency graph/version đã resolve.
8. Nếu là image: image reference, immutable digest, container ID và Docker context.
9. Nếu nghi ngờ reproducibility: logs và artifacts của hai build độc lập.

~~~bash
git status --short
git rev-parse HEAD
java -version
./mvnw -version
# Hoặc:
./gradlew --version
~~~

Kiểm tra output thực tế:

~~~bash
# Maven
ls -l target
sha256sum target/*.jar

# Gradle
ls -l build/libs
sha256sum build/libs/*.jar
~~~

Trên PowerShell có thể dùng Get-ChildItem và Get-FileHash -Algorithm SHA256. Đường dẫn nào không tồn tại thì không hash đường dẫn đó. Modified time không phải bằng chứng đủ: file có thể được copy giữ timestamp, archive timestamp có thể được chuẩn hóa, hoặc build tool có thể khôi phục output từ cache.

Kiểm tra nội dung JAR:

~~~bash
jar tf target/release-demo.jar
~~~

Với Spring Boot executable JAR, tìm META-INF/MANIFEST.MF, org/springframework/boot/loader/, BOOT-INF/classes/ và BOOT-INF/lib/. Nếu thấy *-plain.jar, đó có thể là archive Java thông thường chưa được Spring Boot repackage.

## 4. Maven: kiểm tra lifecycle, plugin execution và dependencies

### 4.1. Phase và goal

Maven có ba lifecycle chính: clean, default và site. Trong default lifecycle, các phase thường dùng:

- validate: kiểm tra project.
- generate-sources / generate-resources: tạo source/resource.
- process-resources: copy/filter resources.
- compile: compile main source.
- test-compile / test: compile và chạy test.
- package: đóng gói JAR/WAR.
- verify: chạy quality checks sau package.

Gọi mvn verify sẽ chạy các phase trước đó theo thứ tự. Gọi riêng mvn compile không tạo artifact package mới. Plugin goal chỉ chạy nếu được bind vào phase hoặc được gọi trực tiếp.

~~~bash
./mvnw --batch-mode clean verify
~~~

### 4.2. clean làm gì và không làm gì?

Maven Clean Plugin mặc định dọn project output directories như target/, classes/, test classes và reporting output. Nó **không xóa toàn bộ Maven local repository** (~/.m2/repository), Docker/BuildKit cache hoặc CNB volumes.

Nếu generator ghi output ngoài target/, mvn clean có thể không dọn file đó. Hãy đặt generated output dưới target/ hoặc cấu hình fileset riêng trong Maven Clean Plugin. Tránh để generated outputs rải trong source tree.

### 4.3. Kiểm tra POM hiệu lực và profile

~~~bash
./mvnw help:active-profiles
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
~~~

Đọc effective POM để kiểm tra plugin version, execution/phase binding, profile, skip property, finalName, output directory, classifier và resource filtering. Parent POM hoặc pluginManagement có thể override cấu hình.

### 4.4. Debug goal bị bỏ qua

~~~bash
./mvnw --batch-mode -X clean package
~~~

-X tạo debug logs rất dài; chỉ bật khi cần và tránh chia sẻ log có credentials hoặc repository URLs nhạy cảm. Tìm plugin/goal liên quan, phase được gọi, skip message và output path.

Một số skip flags thường gặp:

| Property | Tác động điển hình |
| --- | --- |
| -DskipTests | Bỏ chạy tests; thường vẫn compile test sources. |
| -Dmaven.test.skip=true | Bỏ cả test compilation và execution. |
| -Dspring-boot.repackage.skip=true | Bỏ Spring Boot repackage nếu plugin version hỗ trợ. |
| -Dspring-boot.build-image.skip=true | Bỏ image build goal nếu plugin version hỗ trợ. |

Kiểm tra property đúng với plugin version của project. Nếu pipeline báo success nhưng test/package/repackage/image không chạy, xem command line và logs.

### 4.5. Dependency cũ

~~~bash
./mvnw dependency:tree -Dverbose
./mvnw help:effective-pom
~~~

Kiểm tra dependency mediation, exclusions, dependencyManagement, profiles và repositories. Version trong một dependency declaration không luôn là version cuối cùng được resolve.

Nếu dùng SNAPSHOT hoặc repository cập nhật theo thời gian:

~~~bash
./mvnw -U clean verify
~~~

-U yêu cầu Maven kiểm tra cập nhật cho SNAPSHOT và một số artifact thiếu theo resolver. Nó **không** buộc compiler compile lại nếu output không đổi và không xóa toàn bộ ~/.m2. Nếu artifact local bị hỏng, xác định đúng group/artifact/version rồi purge đúng phạm vi; không xóa cả local repository theo phản xạ.

### 4.6. Generated sources/resources không xuất hiện

Kiểm tra generator được bind vào đúng phase:

- Java source generator thường chạy ở generate-sources.
- Resource generator thường chạy ở generate-resources.
- Source/resource được tạo phải được đăng ký vào Maven compile/resource roots.
- clean phải xóa generated output để lần build sau tạo lại.
- Generator chạy thủ công ngoài lifecycle có thể không được CI gọi.

Multi-module build:

~~~bash
./mvnw -pl :service-api -am clean verify
~~~

Thay service-api bằng artifactId thực. -pl chọn module, -am build cả module phụ thuộc cần thiết.

## 5. Gradle: đọc task outcomes trước khi xóa build directory

### 5.1. Ý nghĩa task outcomes

| Outcome | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| EXECUTED hoặc không có nhãn | Task actions đã chạy. | Kiểm tra logs và output path. |
| UP-TO-DATE | Inputs/outputs được xem là không đổi trong workspace. | Nếu input thực sự đổi, task có thể khai báo thiếu input hoặc đọc nhầm file. |
| FROM-CACHE | Output được phục hồi từ build cache. | Cache key cho rằng task inputs tương ứng với output đã lưu. |
| NO-SOURCE | Không có source input cần xử lý. | Kiểm tra source set và generated source dependency. |
| SKIPPED | Task bị bỏ qua theo điều kiện/command. | Kiểm tra onlyIf, enabled, -x và skip properties. |
| FAILED | Task thực thi nhưng lỗi. | Đọc failure đầu tiên và dependency task liên quan. |

~~~bash
./gradlew clean build --info
./gradlew bootJar --dry-run
./gradlew tasks --all
./gradlew help --task bootJar
~~~

Trong multi-project build, dùng full task path như :api:bootJar hoặc :web:bootBuildImage để tránh chạy nhầm subproject.

### 5.2. Chẩn đoán up-to-date và build cache riêng

~~~bash
./gradlew bootJar --rerun-tasks --no-build-cache --info
~~~

- --rerun-tasks bỏ qua up-to-date checks và buộc task graph chạy lại.
- --no-build-cache tắt việc lấy task outputs từ Gradle build cache trong build đó.
- clean dọn project outputs như build/, nhưng không tự xóa Gradle User Home hoặc remote build cache.

Nếu chạy cưỡng bức tạo output đúng, hãy tìm lý do task trước đó được xem là up-to-date/from-cache. Đừng để pipeline release luôn dùng --rerun-tasks để che task model sai.

### 5.3. Dependency cache và --refresh-dependencies

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-core
./gradlew clean build --refresh-dependencies
~~~

--refresh-dependencies yêu cầu Gradle làm mới trạng thái dependency resolution. Gradle vẫn có thể kiểm tra checksum/metadata và giữ artifact đã có nếu repository xác nhận chúng không đổi; nó không có nghĩa luôn tải lại mọi JAR.

Dùng khi dependency dynamic/changing hoặc metadata repository cần được làm mới. Với release dependency version cố định, kiểm tra dependency graph và lockfile trước khi kết luận cache sai.

### 5.4. Task custom khai báo thiếu input gây output cũ

Ví dụ sai: task tạo build-info.properties từ project version nhưng chỉ khai báo output.

~~~groovy
tasks.register('generateBuildInfo') {
    def output = layout.buildDirectory.file('generated/resources/build-info.properties')
    outputs.file(output)

    doLast {
        def target = output.get().asFile
        target.parentFile.mkdirs()
        target.setText("version=¤{project.version}\n", 'UTF-8')
    }
}
~~~

Nếu project.version đổi nhưng Gradle không được thông báo đây là input, task có thể vẫn UP-TO-DATE và file giữ version cũ.

Cách sửa: khai báo mọi giá trị ảnh hưởng output là input và khai báo output rõ ràng.

~~~groovy
def generatedResources = layout.buildDirectory.dir('generated/resources')

tasks.register('generateBuildInfo') {
    def output = generatedResources.map { it.file('build-info.properties') }

    inputs.property('appVersion', project.version.toString())
    inputs.file(layout.projectDirectory.file('src/main/templates/build-info.properties.template'))
    outputs.file(output)

    doLast {
        def target = output.get().asFile
        target.parentFile.mkdirs()
        def template = file('src/main/templates/build-info.properties.template').getText('UTF-8')
        target.setText(template.replace('@version@', project.version.toString()), 'UTF-8')
    }
}

sourceSets {
    main {
        resources.srcDir(generatedResources)
    }
}

tasks.named('processResources') {
    dependsOn tasks.named('generateBuildInfo')
}
~~~

Template src/main/templates/build-info.properties.template:

~~~properties
application.version=@version@
~~~

appVersion là input property, template là input file, build-info.properties là output file và processResources phụ thuộc generator. Khi version/template đổi, Gradle có căn cứ để chạy lại generator.

Nếu task phụ thuộc environment variable, file ngoài project, JDK/tool hoặc hệ thống bên ngoài, hãy khai báo những giá trị có ảnh hưởng output là inputs. Không khai báo mọi biến môi trường một cách bừa bãi.

### 5.5. Output chồng lấn và task graph

Hai task cacheable không nên ghi vào cùng output directory/file nếu chúng không được thiết kế để phối hợp. Kiểm tra:

- Producer task có là dependency của consumer task không?
- Generated source/resource đã được thêm vào source set chưa?
- dependsOn có đúng task path không?
- onlyIf/enabled/-x có bỏ qua task không?
- Có hai task ghi cùng file không?
- Output path có thay đổi theo project/module/profile không?

Không dựa vào thứ tự task trên command line để ngầm bảo đảm producer chạy trước consumer; khai báo dependency rõ ràng trong build graph.

## 6. Spring Boot build output và build-info timestamp

### 6.1. Kiểm tra đúng task/goal tạo Boot archive

Maven:

~~~bash
./mvnw clean package
ls -l target/*.jar
jar tf target/release-demo.jar
~~~

Gradle:

~~~bash
./gradlew clean bootJar
ls -l build/libs/*.jar
jar tf build/libs/release-demo.jar
~~~

Tên file tùy finalName, archiveFileName, classifier và module. Maven Spring Boot repackage tạo executable archive từ archive đã package; Gradle bootJar tạo Boot executable JAR. Dự án có thể đồng thời tạo plain JAR và Boot JAR.

### 6.2. build-info có thể khiến mỗi lần build khác nhau

Spring Boot Gradle bootBuildInfo mặc định đưa build.time (thời điểm build) vào META-INF/build-info.properties. Task vì thế có thể luôn chạy lại và output thay đổi. Nếu ưu tiên hiệu năng/reproducibility, loại time:

~~~groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
~~~

Spring Boot Maven Plugin có time property và excludeInfoProperties. Có thể loại time:

~~~xml
<configuration>
    <excludeInfoProperties>
        <excludeInfoProperty>time</excludeInfoProperty>
    </excludeInfoProperties>
</configuration>
~~~

Đây là cấu hình bên trong plugin execution build-info. Nếu release policy yêu cầu timestamp, giữ nó và chấp nhận artifact thay đổi theo thời gian; đừng gọi hai file khác digest là lỗi cache khi nguyên nhân là build metadata.

### 6.3. Resource metadata và CNB

Paketo/Spring Boot buildpacks có thể chuẩn hóa metadata như last-modified của application resources để hỗ trợ image caching/reproducibility. Không nên để logic runtime phụ thuộc timestamp file trong archive/image nếu buildpack có thể thay đổi metadata đó.

Nếu static resource caching cần Last-Modified, kiểm tra cấu hình Spring Web resource handling và buildpack behavior. Timestamp khác không tự chứng minh bytes của resource đã thay đổi.

## 7. Docker BuildKit: cache instruction không kiểm tra trạng thái mạng

### 7.1. Quy tắc cache của Dockerfile

Docker kiểm tra từng instruction để quyết định tái sử dụng layer. Với COPY/ADD, checksum dựa trên metadata/nội dung file liên quan; mtime không được dùng riêng để invalidation. Với RUN, Docker thường dùng command string và layer trước đó làm căn cứ, không chạy lại lệnh chỉ vì package repository ngoài mạng đã có version mới.

~~~dockerfile
FROM eclipse-temurin:17-jdk
RUN apt-get update && apt-get install -y curl
COPY pom.xml .
RUN ./mvnw dependency:go-offline
COPY src ./src
RUN ./mvnw package
~~~

Nếu RUN apt-get update được cache hit, Docker không tự biết repository apt đã thay đổi. Nếu muốn cập nhật base image, dùng --pull; nếu cần bỏ layer cache, dùng --no-cache hoặc --no-cache-filter cho stage cụ thể.

### 7.2. Lệnh chẩn đoán

~~~bash
docker build -t demo:local .
docker build --pull -t demo:local .
docker build --no-cache -t demo:local .
docker build --pull --no-cache -t demo:local .
~~~

--no-cache không đồng nghĩa pull mọi base image mới nhất; --pull là tùy chọn riêng. Dùng cả hai chỉ khi cần base image mới và thực thi lại Dockerfile instructions.

BuildKit hỗ trợ --no-cache-filter để vô hiệu cache cho một stage cụ thể. Dùng khi đã xác định stage cần chạy lại, tránh làm lại stage không liên quan.

### 7.3. Build secrets không tự làm cache invalidation

Nội dung secret mount không tham gia cache checksum. Nếu secret value thay đổi nhưng command và input khác không đổi, RUN step có thể vẫn cache hit. Nếu kết quả thực sự phụ thuộc secret version, dùng một non-secret cache-version input thay đổi theo credential/config version, hoặc thiết kế lại để output không phụ thuộc secret. Không đưa chính secret vào ARG chỉ để bust cache.

### 7.4. SOURCE_DATE_EPOCH và cache

Docker hỗ trợ SOURCE_DATE_EPOCH để chuẩn hóa timestamp cho file/build metadata. Giá trị thay đổi có thể invalidation WORKDIR và các instruction tiếp theo. Nếu dùng Git commit timestamp, cache có thể miss ở mỗi commit; đó là trade-off giữa provenance timestamp và cache reuse.

Chọn timestamp policy rõ ràng: giá trị cố định cho artifact có tính tái lập trong cùng release inputs, hoặc commit timestamp nếu cần gắn mốc source và chấp nhận cache invalidation.

## 8. Cloud Native Buildpacks: build cache, launch cache và workspace

Spring Boot Maven spring-boot:build-image và Gradle bootBuildImage dùng CNB để tạo OCI image. Khi image không phản ánh JAR mới hoặc layer cũ vẫn được tái sử dụng, phân biệt:

- **Build cache:** cached layers do buildpacks đóng góp cho lần build sau.
- **Launch layers / previous image:** layer có thể tái sử dụng khi metadata tương thích, kể cả từ image trong registry.
- **Build workspace:** vùng tạm để builder/buildpacks thao tác.
- **Docker image store:** các image/builder/run image đã pull hoặc tạo trên daemon.

Làm sạch CNB cache cho một lần build:

Maven:

~~~bash
./mvnw spring-boot:build-image -Dspring-boot.build-image.cleanCache=true
~~~

Gradle:

~~~bash
./gradlew bootBuildImage --cleanCache
~~~

cleanCache tác động tới cache của buildpacks theo image build. Nó không xóa Maven local repository, Gradle dependency cache, Docker BuildKit cache, mọi Docker image hoặc runtime application cache.

### 8.1. Image name và cache identity

Spring Boot plugin mặc định lưu CNB cache trong Docker named volumes có tên suy ra từ full target image name. Nếu tag image đổi theo version/commit, cache volume identity cũng có thể đổi và làm giảm khả năng reuse.

Kiểm tra image name/tag, Docker context/daemon, builder/run image và buildpack versions, cache volume names nếu đã cấu hình, và logs analyze/restore/build/export. Đừng xóa mọi Docker volumes chỉ vì một lần build không dùng cache như mong đợi.

### 8.2. Image cũ có thể do build input cũ

Trước khi clean CNB cache, xác nhận executable JAR đầu vào mới: Maven đã chạy package/repackage; Gradle đã chạy bootJar; plugin đọc đúng archive; không chọn nhầm plain JAR; image tag/digest sau build đúng; container đã được recreate từ image mới.

Nếu JAR đầu vào đã cũ, clean CNB cache không sửa được lỗi ở Maven/Gradle layer.

## 9. Bản dựng không tái lập: định nghĩa và nguyên nhân

**Reproducible build** là khả năng tạo artifact giống từng byte khi dùng cùng source code, build environment và build instructions. Hai file cùng version nhưng khác digest chưa chắc là cache bug; có thể build time, archive ordering, toolchain hoặc input môi trường khác nhau.

### 9.1. Nguồn gây sai khác thường gặp

| Nguồn | Ví dụ | Cách kiểm soát |
| --- | --- | --- |
| Timestamp | ZIP/JAR entry times, build-info time, generated file time. | Fixed output timestamp; loại build time nếu không cần. |
| File ordering | Entry order trong JAR/ZIP phụ thuộc filesystem traversal. | Reproducible file order và deterministic packaging. |
| Toolchain | JDK vendor/patch, Maven/Gradle/plugin version. | Pin Wrapper, JDK distribution/version và plugin versions. |
| Dependency resolution | SNAPSHOT, dynamic versions, version ranges, metadata thay đổi. | Pin versions, dependency locking/verification và repository policy. |
| Environment | Locale, timezone, OS, architecture, environment variables. | Build container/toolchain chuẩn hóa; khai báo input cần thiết. |
| Workspace path | Generator ghi absolute path vào file/debug metadata. | Dùng relative paths hoặc loại machine-specific paths. |
| Git metadata | Commit timestamp/hash hoặc branch nhúng trong archive. | Quy định rõ source metadata; không nhúng giá trị thay đổi không cần thiết. |
| Docker base image | Tag latest hoặc tag mutable. | Pin digest và builder/run image digest. |
| Network downloads | Package manager tải version mới từ repository ngoài. | Pin version/checksum và controlled mirrors. |
| Custom task | Task đọc file/env nhưng không khai báo input. | Khai báo inputs/outputs đầy đủ, deterministic task action. |
| Build cache | Task cacheable nhưng output không deterministic hoặc key thiếu input. | Sửa task model, test no-cache và independent rebuild. |

### 9.2. Gradle archive reproducibility

Gradle archive tasks hỗ trợ chuẩn hóa timestamps và file order:

~~~groovy
tasks.withType(org.gradle.api.tasks.bundling.AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Với Gradle 9, các giá trị này đã là mặc định cho Java plugin archive tasks; cấu hình tường minh vẫn hữu ích khi cần thể hiện policy hoặc dùng Gradle cũ hơn. Kiểm tra plugin khác có tự tạo archive riêng hay không.

### 9.3. Maven reproducible output timestamp

Maven khuyến nghị đặt property:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Giá trị trên chỉ là ví dụ cố định. Trong release process, chọn timestamp theo policy project. Đảm bảo archive plugins đang dùng hỗ trợ reproducible builds; Maven property không thể sửa plugin tùy biến tạo output ngẫu nhiên.

Có thể dùng Maven Artifact Plugin để kiểm tra build plan và so sánh artifact:

~~~bash
./mvnw artifact:check-buildplan
./mvnw clean install
./mvnw clean verify artifact:compare
~~~

So sánh trong cùng máy giúp tìm sai khác cơ bản nhưng chưa chứng minh build độc lập tái lập được; cần rebuild từ workspace/môi trường khác.

### 9.4. Spring Boot build-info time

Spring Boot Gradle bootBuildInfo mặc định tạo build.time theo thời điểm build. Task vì thế có thể luôn chạy lại và output thay đổi. Nếu yêu cầu reproducibility, loại time bằng springBoot.buildInfo.excludes.

Maven build-info hỗ trợ time và excludeInfoProperties; có thể dùng project.build.outputTimestamp để cung cấp timestamp ổn định hoặc tắt property time theo cấu hình plugin. Không vừa yêu cầu bit-for-bit identical vừa nhúng timestamp hiện tại vào JAR.

### 9.5. Reproducibility của container image

Để tăng khả năng tái lập: pin builder/run image bằng digest, pin buildpack/dependency versions, kiểm soát image metadata/created date, chuẩn hóa archive timestamps/order, ghi rõ architecture/platform và không phụ thuộc network resource thay đổi ngoài kiểm soát.

Image có thể khác digest dù JAR giống nhau do base/run image hoặc image metadata khác. So sánh JAR trước, rồi mới so image layers/config để xác định sai khác ở tầng nào.

## 10. Phân biệt ba triệu chứng bằng dấu hiệu

| Triệu chứng | Dấu hiệu | Hướng chẩn đoán đầu tiên |
| --- | --- | --- |
| Output không được tạo | File không tồn tại hoặc task/goal không xuất hiện trong log. | Task graph/lifecycle, profile, skip flags, output path và generator binding. |
| Output cũ được giữ lại | File tồn tại nhưng nội dung/digest không phản ánh source/dependency mới. | Sai artifact path, task UP-TO-DATE/from-cache, undeclared input, source set hoặc image/container cũ. |
| Build không tái lập | Hai clean builds cùng commit/toolchain cho digest khác nhau. | So JAR entries, timestamps, generated metadata, dependencies, environment và image base digest. |

Output không tồn tại cần tìm task/goal; output cũ cần tìm input/task graph; non-reproducible cần so sánh hai build độc lập.

## 11. Thí nghiệm có kiểm soát: thay đổi từng biến một

### A. Baseline

1. Chọn commit và ghi git rev-parse HEAD.
2. Ghi Java/Maven/Gradle versions.
3. Ghi command, active profile, build task/goal và artifact path.
4. Chạy build bình thường và lưu log.
5. Ghi size/SHA-256 của JAR và image digest nếu có.

### B. Rebuild trong workspace hiện tại

Maven:

~~~bash
./mvnw clean verify
~~~

Gradle:

~~~bash
./gradlew clean build --info
~~~

So sánh output với baseline. Nếu khác, kiểm tra input nào thay đổi (timestamp, generated build-info, dependency metadata) trước khi kết luận cache gây lỗi.

### C. Buộc task chạy lại và tắt Gradle build cache

~~~bash
./gradlew bootJar --rerun-tasks --no-build-cache --info
~~~

Nếu output mới đúng, xem lại task outcomes và khai báo inputs/outputs. Nếu output vẫn sai, nguyên nhân có thể nằm trong source, generator, plugin hoặc artifact path.

### D. Làm mới dependency resolution

Maven:

~~~bash
./mvnw -U clean verify
./mvnw dependency:tree -Dverbose
~~~

Gradle:

~~~bash
./gradlew clean build --refresh-dependencies
./gradlew dependencies --configuration runtimeClasspath
~~~

So sánh resolved dependency versions trước/sau. Không thay dependency version trong cùng thí nghiệm nếu mục tiêu là đo cache.

### E. Clean CNB cache một lần

Chỉ sau khi xác nhận JAR đầu vào mới:

~~~bash
# Maven
./mvnw spring-boot:build-image -Dspring-boot.build-image.cleanCache=true

# Gradle
./gradlew bootBuildImage --cleanCache
~~~

So logs/layers với lần build thường. Nếu image vẫn cũ, kiểm tra archive đầu vào, builder image, output tag và container đang chạy.

### F. Clean Docker layer cache có kiểm soát

~~~bash
docker build --pull --no-cache -t demo:diagnostic .
~~~

Nếu image mới đúng nhưng build thường cũ, xác định instruction nào được cache và input nào instruction đó không quan sát được. Sửa Dockerfile/input pinning; đừng duy trì no-cache như cách chữa mặc định.

### G. Kiểm tra reproducibility độc lập

Tạo hai workspace sạch từ cùng commit, dùng cùng JDK/build tool/dependencies đã khóa:

~~~bash
git worktree add --detach ../repro-a <COMMIT_SHA>
git worktree add --detach ../repro-b <COMMIT_SHA>

cd ../repro-a
./mvnw clean verify
sha256sum target/release-demo.jar

cd ../repro-b
./mvnw clean verify
sha256sum target/release-demo.jar
~~~

Thay COMMIT_SHA và tên artifact bằng giá trị thực. Với Gradle, chạy ./gradlew clean bootJar --no-build-cache ở mỗi workspace và so build/libs/*.jar.

Nếu digest khác, dùng diffoscope, cmp, jar tf và kiểm tra metadata. Đảm bảo hai workspace có cùng wrapper/JDK/dependency locks và không dùng dynamic inputs khác nhau. Rebuild độc lập trong container/máy khác là bằng chứng mạnh hơn hai lần build trong cùng workspace.

## 12. Tìm nguyên nhân sai khác bên trong JAR

### 12.1. So danh sách entries

~~~bash
jar tf build-a/release-demo.jar > build-a.entries.txt
jar tf build-b/release-demo.jar > build-b.entries.txt
diff -u build-a.entries.txt build-b.entries.txt
~~~

Nếu danh sách entries khác, xem resource/generated classes nào được thêm/bỏ hoặc thứ tự archive thay đổi. Nếu danh sách giống, bytes bên trong vẫn có thể khác.

### 12.2. So metadata và manifest

~~~bash
unzip -p build-a/release-demo.jar META-INF/MANIFEST.MF
unzip -p build-b/release-demo.jar META-INF/MANIFEST.MF
~~~

Kiểm tra Implementation-Version, Build-Time, Start-Class, Main-Class, classpath và custom attributes. Nếu META-INF/build-info.properties có build.time, hai lần build có thể khác chỉ vì timestamp.

### 12.3. So bytecode

~~~bash
javap -classpath build-a/release-demo.jar -c com.example.demo.OrderService
javap -classpath build-b/release-demo.jar -c com.example.demo.OrderService
~~~

Với executable Boot JAR, class trong BOOT-INF/classes có thể cần extract archive hoặc dùng classpath phù hợp. javap cho biết bytecode thực tế trong class; không chỉ dựa vào timestamp file source.

### 12.4. Dùng diffoscope

diffoscope phân tích archive lồng nhau và trình bày khác biệt ở mức file/metadata. Đây là công cụ hữu ích khi hai JAR khác digest nhưng danh sách entries gần như giống nhau. Chạy trong môi trường an toàn vì output diff có thể chứa source/config nội bộ.

## 13. Kiểm tra container đang chạy có dùng image mới

Khi image tag đã được build lại, container cũ vẫn có thể chạy image ID cũ. Tag là tên tham chiếu có thể di chuyển; container được tạo từ image cụ thể.

~~~bash
docker image inspect demo:local
docker ps --no-trunc
docker inspect <CONTAINER_ID>
~~~

Đối chiếu image ID của tag hiện tại, image ID container đang dùng, container creation time, registry digest và endpoint đang được gọi. Sau khi xác nhận image mới, recreate container theo quy trình deploy. Đừng xóa cache để sửa trường hợp traffic vẫn đi vào container cũ.

## 14. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| Maven BUILD SUCCESS nhưng JAR không đổi. | Chỉ chạy test/compile; repackage không chạy; xem nhầm artifact. | Chạy clean verify/package, kiểm tra effective POM và JAR path. |
| mvn clean xong generated file vẫn còn. | Generator ghi ngoài output directories mặc định. | Đưa output vào target hoặc cấu hình clean fileset. |
| Maven vẫn dùng SNAPSHOT cũ. | Update policy/metadata cache hoặc repository không có bản mới. | Kiểm tra dependency tree và repository; dùng -U có chủ đích. |
| Maven dependency version không như khai báo. | Dependency mediation, BOM, parent/profile hoặc transitive dependency. | dependency:tree -Dverbose và effective POM. |
| Gradle UP-TO-DATE dù version đổi. | Task thiếu inputs.property cho version. | Khai báo input đúng và test lại. |
| Gradle FROM-CACHE trả output cũ. | Cache key thiếu input hoặc task không deterministic. | Sửa task inputs/outputs, thử --no-build-cache và --rerun-tasks. |
| Gradle NO-SOURCE. | Source set sai hoặc generated sources chưa được tạo. | Kiểm tra sourceSets và producer task dependency. |
| Gradle SKIPPED. | onlyIf false, task disabled hoặc bị -x loại. | Kiểm tra task configuration và command line. |
| Generated source không compile. | Generator chưa nối vào compileJava/source directory. | Khai báo dependsOn/sourceSets và output directory. |
| Build chạy trong IDE khác CLI. | IDE dùng JDK/Gradle/Maven/profile/environment khác. | So toolchain, wrapper, active profiles và command line. |
| Docker RUN vẫn dùng package cũ. | RUN instruction cache hit; command không đổi nên không kiểm tra network state. | Pin package versions hoặc dùng --no-cache-filter/--no-cache để chẩn đoán. |
| Docker base image vẫn cũ. | Base image tag dùng từ local cache. | Dùng --pull; pin digest cho release. |
| Docker COPY không invalidate khi chỉ đổi mtime. | Docker không dùng mtime riêng làm cache checksum. | Kiểm tra file bytes/metadata; không touch file chỉ để bust cache. |
| CNB image không nhận code mới. | JAR đầu vào cũ hoặc build goal/task không chạy. | Xác nhận package/bootJar trước, sau đó inspect image. |
| CNB cache không reuse giữa tags. | Cache volume identity phụ thuộc full image name. | Cấu hình cache volume names ổn định. |
| Hai JAR khác digest nhưng code giống. | Timestamp, ordering, manifest/build-info hoặc environment metadata khác. | diffoscope, inspect archive metadata, chuẩn hóa timestamp/order. |
| Hai image khác digest nhưng JAR giống. | Base/run image, builder, buildpack hoặc image metadata khác. | So image layers, builder/run digests và created date. |
| Build developer pass, CI fail. | JDK/OS/locale/env/dependency resolution khác hoặc generated output không được checkout. | So toolchain/inputs, dùng wrapper và lock dependencies. |
| Clean build vẫn dùng dependency cũ. | Local/remote repository đang trả cùng version. | Kiểm tra checksum, repository URL và resolved version; clean không purge dependency repository. |
| Cache disabled nhưng output vẫn cũ. | Build input/path sai, app/container cũ hoặc task không được gọi. | Kiểm tra commit, task graph, artifact digest và container image ID. |
| Rebuild độc lập không giống nhau. | Nondeterministic task, timestamp, dynamic dependency, environment leak. | Diffoscope, pin inputs/toolchain, chuẩn hóa archive và sửa task. |

## 15. Làm sạch an toàn và có giới hạn

Trước khi xóa cache, ghi lại cache directory/volume chính xác, tool/project/module sở hữu, có job khác đang dùng không, dữ liệu có thể tái tạo không và cache có được chia sẻ qua CI runner/remote cache không.

| Mục tiêu | Lệnh/biện pháp |
| --- | --- |
| Xóa generated Maven output | ./mvnw clean |
| Chạy lại Gradle task bỏ qua up-to-date | ./gradlew <task> --rerun-tasks |
| Tắt Gradle task build cache một lần | ./gradlew <task> --no-build-cache |
| Làm mới Gradle dependency resolution | ./gradlew <task> --refresh-dependencies |
| Kiểm tra Maven SNAPSHOT update | ./mvnw -U <phase> |
| Làm sạch CNB buildpack cache một lần | Maven cleanCache=true hoặc Gradle --cleanCache |
| Bỏ Docker layer cache | docker build --no-cache |
| Pull base image mới | docker build --pull |

Không xóa toàn bộ ~/.m2, ~/.gradle, Docker volumes hoặc remote cache trên shared runner chỉ để thử một giả thuyết. Nếu remote cache chứa output sai, xác định cache key/task, sửa task model trước, rồi invalidate đúng namespace/key theo policy. Nếu chỉ xóa entry mà không sửa task inputs, output sai có thể được cache lại.

## 16. Checklist chốt lỗi

### Source và toolchain

- [ ] Commit SHA và working tree đã được ghi nhận.
- [ ] Java/JDK, Wrapper, Maven/Gradle và plugin versions đã được ghi.
- [ ] Profile, environment và build properties đã được xác định.
- [ ] Dependency versions đã được kiểm tra từ resolved graph.

### Output generation

- [ ] Đã xác định đúng module, goal/task và output path.
- [ ] Plugin execution/task có mặt trong lifecycle/task graph.
- [ ] Không có skip flag, onlyIf hoặc exclude task ngoài ý muốn.
- [ ] Generated sources/resources đã được nối vào compile/processResources.
- [ ] Custom task khai báo đầy đủ inputs và outputs.
- [ ] Không có overlapping output directories giữa các task.

### Cache

- [ ] Đã phân biệt dependency cache, Gradle task cache, Docker cache và CNB cache.
- [ ] Đã kiểm tra task outcome/logs trước khi clean.
- [ ] Chỉ clean đúng cache cần kiểm chứng.
- [ ] Đã thử no-cache/forced rerun có kiểm soát nếu cần.
- [ ] Đã xác nhận output mới không chỉ là file cũ được copy sang vị trí khác.

### Reproducibility và runtime

- [ ] Hai build dùng cùng source commit và build instructions.
- [ ] JDK/toolchain, plugin và dependencies được pin.
- [ ] Archive timestamps và file order được chuẩn hóa.
- [ ] Build-info timestamp/dynamic metadata được xử lý theo policy.
- [ ] Docker base/builder/run images được pin theo digest khi cần.
- [ ] Đã so digest và dùng diffoscope/entry inspection khi khác biệt.
- [ ] JAR/image được triển khai đúng digest và container đang chạy dùng image mới.
- [ ] Runtime cache được điều tra riêng nếu response vẫn cũ.

## 17. Bài thực hành và tiêu chí đạt

### Bài A — Maven output cũ

1. Tạo Spring Boot Maven project Java 17 có endpoint trả về chuỗi phiên bản.
2. Build JAR và ghi SHA-256.
3. Sửa code response, chạy clean verify hoặc clean package.
4. Kiểm tra target/classes, JAR manifest và bytecode bằng javap.
5. Thử chỉ chạy test rồi giải thích vì sao JAR package có thể chưa được tạo lại.
6. Kiểm tra active profiles/effective POM và dependency tree.

### Bài B — Gradle task thiếu input

1. Tạo custom task sinh build-info.properties từ project.version.
2. Chỉ khai báo output, build lần đầu.
3. Đổi version và quan sát task outcome.
4. Thêm inputs.property('appVersion', project.version.toString()).
5. Đổi version lần nữa, xác nhận task chạy lại và file generated đổi.
6. Thêm generated resources directory vào source set và nối task vào processResources.

### Bài C — phân biệt dependency cache và task cache

1. Build Gradle app hai lần, ghi UP-TO-DATE/FROM-CACHE.
2. Chạy clean build --no-build-cache.
3. Chạy --refresh-dependencies và so resolved dependency graph.
4. Giải thích vì sao clean, --no-build-cache và --refresh-dependencies tác động lên các trạng thái khác nhau.

### Bài D — Docker/CNB stale image

1. Build container image từ Spring Boot JAR.
2. Sửa code, package JAR mới và build image.
3. Kiểm tra image digest và container image ID.
4. Thử docker build --pull --no-cache với Dockerfile workflow riêng.
5. Với CNB, thử cleanCache một lần sau khi xác nhận JAR input đã mới.
6. Ghi layer/task nào được rebuild và vì sao.

### Bài E — reproducible build

1. Pin commit, JDK, wrapper và dependency versions.
2. Tạo hai workspace độc lập từ cùng commit.
3. Build với task cache disabled và cùng môi trường.
4. So SHA-256 của JAR.
5. Nếu khác, dùng diffoscope, jar tf, manifest/build-info và archive timestamps để tìm nguyên nhân.
6. Chuẩn hóa output timestamp/file order và lặp lại.
7. Nếu so container image, pin builder/run/base image digest và so sánh JAR riêng với image layers.

**Tiêu chí đạt:** người học giải thích được một trường hợp output không được tạo lại, chứng minh task/goal nào bị bỏ qua hoặc cache hit, sửa một khai báo input/output bị thiếu, phân biệt dependency cache với task-output/image cache, và thực hiện hai clean builds độc lập để đánh giá reproducibility. Nếu chưa chạy Docker/CNB hoặc chưa có môi trường độc lập, ghi rõ giới hạn kiểm chứng; không đánh dấu cache/reproducibility PASS chỉ từ một lần build thành công.

## Tài liệu tham khảo chính thức

- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Clean Plugin — clean:clean](https://maven.apache.org/plugins/maven-clean-plugin/clean-mojo.html)
- [Maven Clean Plugin — FAQ](https://maven.apache.org/components/plugins/maven-clean-plugin/faq.html)
- [Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Gradle — Understanding Tasks and Task Outcomes](https://docs.gradle.org/current/userguide/more_about_tasks.html)
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html)
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle — Solving Common Caching Problems](https://docs.gradle.org/current/userguide/common_caching_problems.html)
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html)
- [Gradle — AbstractArchiveTask](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html)
- [Spring Boot 3.3 — Maven Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html)
- [Spring Boot 3.3 — Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html)
- [Spring Boot — Maven build-info](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-info.html)
- [Spring Boot — Gradle build-info and Actuator](https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html)
- [Cloud Native Buildpacks — Caching Strategies](https://buildpacks.io/docs/for-buildpack-authors/concepts/caching-strategies/)
- [Docker — Build Cache Invalidation](https://docs.docker.com/build/cache/invalidation/)
- [Reproducible Builds — diffoscope](https://diffoscope.org/)

**Ghi nhớ:** clean chỉ xử lý generated outputs thuộc phạm vi build tool; dependency cache, Gradle task cache, Docker layer cache và CNB cache là những cơ chế riêng. Khi output cũ, hãy truy ra task/goal, input và artifact path. Khi hai bản build khác nhau, so sánh từ JAR đến image, chuẩn hóa timestamp/toolchain/dependencies rồi rebuild trong môi trường độc lập để chứng minh tính tái lập.