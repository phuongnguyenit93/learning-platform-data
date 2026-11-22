# Phân biệt build offline, làm mới dependency và xóa cache có mục tiêu

## 1. Mục tiêu và vấn đề cần giải quyết

Khi xây dựng ứng dụng Spring Boot bằng Gradle hoặc Maven, bạn có thể gặp các tình huống: mạng công ty tạm ngắt, bản SNAPSHOT trên repository đã đổi nhưng build vẫn dùng bản cũ, một dependency JAR bị hỏng hoặc developer muốn “build sạch hoàn toàn”. Những tình huống này **không thể xử lý bằng cùng một lệnh cache**.

Ba thao tác trong tên bài có ba mục tiêu khác nhau:

1. **Build offline**: không truy cập remote repository để tải/kiểm tra dependency; sử dụng những metadata và artifact đã có cục bộ. Trong Gradle dùng `--offline`; trong Maven dùng `-o`.
2. **Làm mới dependency**: yêu cầu kiểm tra lại thông tin dependency từ repository, kể cả khi cache còn dùng được theo TTL. Trong Gradle dùng `--refresh-dependencies`; Maven có `-U` với semantics riêng.
3. **Xóa cache có mục tiêu**: chỉ dọn phần dữ liệu nghi lỗi hoặc không còn cần thiết, như một dependency cụ thể trong Maven local repository, output của project, hoặc vùng cache đã xác định; **tránh xóa toàn bộ cache người dùng** khi chưa có bằng chứng.

Cả ba khác với **clean build** theo nghĩa xóa file `build/` hoặc `target/`. Đồng thời, cache tải dependency khác với Gradle **configuration cache** và **build cache của task output**.

Sau bài học, bạn cần:

- Giải thích luồng Gradle/Maven tìm artifact trên local cache rồi mới dùng network khi được phép.
- Chọn đúng công cụ khi muốn build không mạng, kiểm tra bản mới từ repository, hoặc xử lý artifact hỏng.
- Hiểu giới hạn của offline mode đối với plugin, parent/BOM, SNAPSHOT và dependencies chưa từng được tải.
- Đọc kết quả `dependencies`, `dependencyInsight`/`dependency:tree`, metadata và log thay vì “xóa sạch để thử”.
- Thực hiện thao tác phục hồi nhỏ nhất, an toàn với build concurrent, CI cache và private repository.
- Phân biệt được lệnh có **thay đổi dependency resolution** với lệnh chỉ **dọn project outputs** hoặc **vô hiệu hóa task/configuration cache**.
- Kiểm chứng một ứng dụng Spring Boot Java 17 chạy được trước và sau thao tác.

**Bối cảnh:** các ví dụ ứng dụng chọn Java 17, Spring Boot 3.3.13, Spring dependency-management plugin 1.1.7 và Gradle wrapper tương thích. Các phiên bản này là ví dụ nhất quán, không phải khẳng định phiên bản mới nhất. Luôn giữ phiên bản build tool đã được repository/CI phê duyệt.

## 2. Sơ đồ quyết định nhanh

~~~text
Build không thể tải dependency / nghi dùng artifact cũ
                         |
             +-----------+------------------+
             |                              |
        Mạng bị ngắt?                  Mạng có sẵn?
             |                              |
             v                              v
   Có đủ dữ liệu local?         Xác định đúng GAV/repository
             |                     và dependency graph
         +---+---+                         |
         |       |                         v
         Có     Không          Snapshot/dynamic/metadata cũ?
         |       |                  |               |
         v       v                  Có              Không
      offline   Cần tải              |               |
      build     online               v               v
                         Refresh dependency     Kiểm tra scope,
                         và kiểm chứng graph    version conflict,
                                                 artifact lỗi
                                                     |
                                                     v
                                      Chỉ xử lý cache nhỏ nhất
                                      hoặc dùng user home riêng
~~~

**Không nhầm các nhánh:**

- Offline không giúp “cập nhật thư viện”.
- Refresh không phải “xóa cache”.
- `clean` không xóa cache downloaded artifacts trong Gradle User Home/Maven local repository.
- Xóa toàn bộ `~/.gradle` hoặc `~/.m2/repository` có thể làm mọi build khác trên máy phải tải lại, thậm chí mất artifact Maven chỉ có bản `install` local.

Đầu tiên xác định lỗi nằm ở **dependency resolution**, **build configuration**, **task output**, **mã nguồn** hay **runtime application**. Chỉ thao tác lên cache liên quan.

## 3. Cache nào đang được nói đến?

| Loại trạng thái/cache | Gradle mặc định hoặc thường gặp | Maven tương ứng | Khi nào cần quan tâm? |
| --- | --- | --- | --- |
| Artifact và dependency metadata | `GRADLE_USER_HOME/caches/modules-2` | `~/.m2/repository` hoặc localRepository tùy chỉnh | Download, offline, SNAPSHOT/changing, repository issues |
| Gradle wrapper distribution | `GRADLE_USER_HOME/wrapper/dists` | Maven wrapper distribution tùy setup | Máy offline chưa có chính build tool |
| Configuration cache | `<root-project>/.gradle/configuration-cache` | Không có built-in tương đương trực tiếp trong Maven workflow cơ bản | Build script/task graph configuration |
| Task output build cache | Local dưới Gradle User Home, có thể remote | Maven Build Cache Extension nếu được cài riêng | Compile/resource/process/outputs của cacheable tasks |
| Task local outputs và execution history | `build/` và project `.gradle/` | `target/` | `UP-TO-DATE`, rebuild, archive tồn dư |
| IDE caches | IntelliJ/Eclipse/VS Code riêng | Tương tự | IDE báo đỏ/sync khác CLI |

Các tên directory có thể đổi theo Gradle version. Đặc biệt, `GRADLE_USER_HOME` không nhất thiết là `~/.gradle` nếu cấu hình môi trường hoặc CLI `-g`. Maven local repository cũng có thể đổi trong `settings.xml`.

**Ví dụ:** khi `./gradlew compileJava` ghi `UP-TO-DATE`, đó thường là kết quả kiểm tra inputs/outputs của task trong workspace, không phải bằng chứng dependency download cache vừa được sử dụng. Khi task báo `FROM-CACHE`, đó là task-output cache, không phải thư viện đã tải từ Maven Central.

## 4. Cách Gradle giải quyết một dependency

Với cấu hình:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Gradle thực hiện những việc có thể bao gồm:

1. Đọc declarations trong build scripts hoặc version catalogs.
2. Áp dụng plugin/BOM/constraints và configurations.
3. Tìm module metadata và artifact theo repositories đã cấu hình.
4. Kiểm tra dữ liệu resolution đã lưu: version, descriptor, metadata của artifact, repository gốc.
5. Nếu cần và được phép dùng mạng, truy vấn remote repository hoặc tải artifact.
6. Lưu data hợp lệ vào dependency cache để những lượt build sau sử dụng.

Dependency cache của Gradle gồm **file store** (JAR/POM/artifacts dựa trên checksum) và **metadata store** (resolved versions, artifact metadata, các lookup). Metadata có thể ghi nhận **một artifact không tồn tại** tại một repository để tránh gọi remote lặp đi lặp lại.

Gradle cũng tách metadata theo repository URL/type/layout, và có “repository stickiness” để tránh âm thầm thay nguồn artifact sau khi đã resolve. Vì thế **đổi repository** có thể làm Gradle cần kiểm tra/tải lại metadata dù cùng một file JAR từng được cache ở nguồn khác. Không nên sao chép cache file ngẫu nhiên giữa repositories rồi coi cache đã đầy đủ.

### 4.1. Vì sao nhìn thấy JAR trong cache chưa chắc offline build được?

Một module có thể kéo theo hàng chục transitive dependencies, platform BOM, annotation processor, Gradle plugin và plugin transitive dependencies. Offline build cần **tất cả dữ liệu cần thiết** cho requested task graph, bao gồm metadata phù hợp và artifacts còn thiếu.

Ví dụ một JAR tồn tại trong `modules-2/files-2.1` nhưng Gradle không có metadata resolution tương ứng cho repository/version yêu cầu; build offline vẫn có thể fail. Dependency resolution không đơn giản là tìm file JAR trùng tên trong thư mục.

### 4.2. Dynamic và changing dependencies

Gradle phân biệt:

- **Fixed release:** ví dụ `com.example:sample-lib:1.2.3`, thường kỳ vọng artifact không thay đổi nội dung khi đã publish.
- **Dynamic version:** ví dụ `com.example:sample-lib:1.+`; phải xác định `1.7` hay `1.8` là bản thực tế được chọn.
- **Changing dependency:** ví dụ `1.2-SNAPSHOT` hoặc dependency được khai báo changing; nội dung có thể đổi dù coordinate không đổi.

Theo Gradle dependency caching docs hiện hành, TTL mặc định cho dynamic version và changing module thường **24 giờ**. TTL được cấu hình lại qua resolutionStrategy. Khi ở offline mode, Gradle không tự đi hỏi remote “đã có bản mới chưa”, kể cả TTL đã hết.

**Groovy DSL — fragment tùy chọn khi có lý do giảm TTL:**

~~~groovy
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor 10, 'minutes'
    resolutionStrategy.cacheChangingModulesFor 4, 'hours'
}
~~~

**Kotlin DSL:**

~~~kotlin
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor(10, "minutes")
    resolutionStrategy.cacheChangingModulesFor(4, "hours")
}
~~~

Đây chỉ là **fragment**, không phải cấu hình mặc định khuyến nghị. Giảm TTL tăng số network checks và có thể làm build thiếu tính tái lập. Release/CI nên ưu tiên pinned versions, dependency locking hoặc một policy version rõ ràng thay vì dynamic/SNAPSHOT tùy tiện.

## 5. Build offline của Gradle: `--offline`

### 5.1. Chính xác `--offline` làm gì?

Gradle `--offline` yêu cầu dependency resolution **không truy cập remote repositories**. Những module/artifact đã có dữ liệu local phù hợp có thể tiếp tục được sử dụng, kể cả khi cache metadata bình thường đã đến hạn kiểm tra. Nếu dữ liệu bắt buộc chưa được cache, build sẽ **FAIL**.

Ví dụ:

~~~bash
./gradlew build --offline
~~~

Cần phân biệt **offline dependency resolution** với “ứng dụng build xong cũng không cần network”. Custom tasks, test integration, Docker image builder, HTTP client trong test hoặc code generator vẫn có thể thực hiện network nếu chúng tự gọi và không bị kiểm soát. `--offline` không tự chặn mọi socket từ mọi process.

### 5.2. Chuẩn bị offline build đúng cách

Khi còn kết nối repository:

~~~bash
./gradlew --version
./gradlew clean build
./gradlew bootJar
~~~

Sau đó thử:

~~~bash
./gradlew build --offline
~~~

Lần chạy online giúp tải dependencies phục vụ task được thực thi; `bootJar` cũng có thể cần runtimeClasspath mà chỉ gọi `dependencies` chưa chắc tải hết artifact file. Nhưng **không bảo đảm** tất cả task tương lai (integration tests, codegen, native image) đều hoạt động offline nếu chưa từng chạy hoặc chưa populate dependencies của chúng.

**Wrapper bootstrap là một trường hợp riêng:** nếu máy chưa tải Gradle distribution được khai báo trong `gradle/wrapper/gradle-wrapper.properties`, wrapper có thể cần network **trước khi Gradle nhận được cờ `--offline`**. Không thể khắc phục thiếu Gradle distribution chỉ bằng việc thêm `--offline` vào lệnh.

### 5.3. Cách quan sát kết quả

~~~bash
./gradlew dependencies --configuration runtimeClasspath --offline
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath --offline
~~~

- Nếu thành công, bạn biết Gradle có thể resolve configuration đó từ dữ liệu cục bộ.
- Nếu thất bại vì module/plugin metadata chưa có, cần tải trước trong môi trường online hoặc dùng repository mirror nội bộ có thể truy cập.
- Nếu classpath resolve được nhưng application test cần gọi external service, build/test vẫn có thể lỗi do network của test, không phải Gradle dependency cache.

### 5.4. Không nên dùng offline để che lỗi repository

Một build chỉ chạy được offline nhưng fail ở online mode có thể đang phụ thuộc metadata cũ hoặc đã đổi repository/permissions. Nó không chứng minh artifact hiện tại từ remote là đúng. Thực hiện một build online có kiểm tra nguồn, version và checksum để giải quyết nguyên nhân. Không dùng “bật offline vĩnh viễn” làm cách né lỗi auth/TLS/repository.

## 6. Làm mới dependency của Gradle: `--refresh-dependencies`

### 6.1. Semantics chính xác

Lệnh:

~~~bash
./gradlew build --refresh-dependencies
~~~

yêu cầu Gradle **bỏ qua kết quả dependency resolution cache cũ cho lượt kiểm tra này**, thực hiện fresh resolve với repositories hiện tại, cập nhật dynamic version listing/module metadata/changing modules theo nhu cầu.

Nhưng nó **không ép tải lại tất cả JAR**. Gradle thường dùng các yêu cầu metadata/checksum hoặc HTTP HEAD để xác minh rằng remote artifact không thay đổi. Nếu file đã cache vẫn có checksum phù hợp, nó có thể được sử dụng lại, tránh network transfer vô ích.

**Vì vậy:** “đã dùng `--refresh-dependencies` nhưng không thấy tải lại toàn bộ JAR” **không tự là lỗi**. Lệnh có thể đã làm đúng chức năng refresh.

### 6.2. Thử riêng trên configuration cần thiết

Nếu nghi `spring-core` hoặc một SNAPSHOT trong runtime classpath:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath --refresh-dependencies
~~~

Đây là cách vừa yêu cầu refresh resolution vừa quan sát version được chọn. Cờ refresh là **cấp invocation**, không có nghĩa Gradle chỉ refresh `spring-core`; việc resolution diễn ra cho những configurations/tasks thực tế được truy cập. Dòng `--dependency spring-core` lọc báo cáo của `dependencyInsight`, **không phải bộ lọc chỉ refresh một artifact**.

Nếu vấn đề thuộc test dependency:

~~~bash
./gradlew dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath --refresh-dependencies
~~~

Nếu vấn đề là plugin resolution, xem `plugins` và `pluginManagement.repositories` trong settings; không tự thêm Maven Central vào application `repositories` rồi nghĩ Gradle đã đổi nguồn cho mọi plugin.

### 6.3. Khi nào refresh hữu ích?

- Mới publish SNAPSHOT/changing module nhưng cache còn dữ liệu cũ.
- Dynamic version như `1.+` mới có release, bạn muốn Gradle đánh giá lại listing ngay.
- Repository/mirror vừa sửa metadata hoặc artifact publication.
- Gradle cache từng ghi nhận module/artifact không tồn tại nhưng repository đã có file.
- Cần kiểm tra dependency resolution theo trạng thái remote hiện tại sau khi sửa credentials/repositories.

### 6.4. Khi nào refresh không phải phương án chính?

- Mã nguồn Java compile lỗi do code sai.
- `NoSuchMethodError` do BOM/conflict đã chọn phiên bản không tương thích; refresh vẫn có thể chọn cùng dependency graph.
- `ClassNotFoundException` vì dependency thiếu trong `implementation`/`runtimeOnly` hoặc sai scope.
- `bootJar` có manifest/main class sai.
- `UP-TO-DATE` xảy ra khi bạn cần ép biên dịch lại; đây là task outcome, không phải dependency cache.
- Remote artifact đã **bị publish sai** nhưng repository mirror vẫn phục vụ dữ liệu cũ; cần sửa publisher/repository, không chỉ refresh client.

Không dùng `--refresh-dependencies` làm mặc định của mọi CI job: nó tăng metadata requests, ảnh hưởng hiệu năng và có thể làm dynamic dependencies thay đổi ngoài ý muốn.

## 7. Đặt cạnh nhau: offline và refresh

| Câu hỏi | `--offline` | `--refresh-dependencies` |
| --- | --- | --- |
| Có truy vấn remote repository trong dependency resolution? | Không | Có thể có, thường sẽ kiểm tra |
| Có thể lấy version mới vừa publish? | Không từ remote | Có, nếu repository cung cấp và resolution rules chọn nó |
| Có thể dùng artifact đã cache? | Có | Có, sau xác minh nếu vẫn đúng |
| Nếu artifact chưa cache? | Build có thể fail | Gradle có thể tải nếu repository cho phép |
| Tác động tới dynamic/changing TTL | Dùng dữ liệu local, không kiểm tra remote | Kiểm tra lại, không phụ thuộc TTL cũ |
| Tự xóa toàn bộ file cache? | Không | Không |
| Tự xóa project `build/`? | Không | Không |
| Tự bỏ cấu hình cache task output? | Không | Không |
| Tự bảo đảm test pass? | Không | Không |

**Đừng kết hợp hai cờ với kỳ vọng “vừa offline vừa cập nhật từ server”**. Hai ý định trái nhau: nếu cần tìm bản mới, phải có nguồn repository truy cập được; nếu thực sự không có mạng, chỉ dữ liệu đã cache mới khả dụng. Tách ra thành hai bước rõ ràng ở các thời điểm khác nhau.

## 8. “Xóa cache” gồm nhiều đối tượng khác nhau

### 8.1. `clean` dọn output, không dọn dependency cache

~~~bash
./gradlew clean
./gradlew clean build
~~~

Gradle Java plugin `clean` xóa thư mục output project (thường `build/`). Nó **không xóa** `GRADLE_USER_HOME/caches/modules-2`, không xóa wrapper distribution và không phải cách reset metadata TTL.

Nếu cần xóa riêng output một subproject:

~~~bash
./gradlew :app:clean
~~~

Dòng này **chỉ hợp lệ** khi multi-project build thực sự có project path `:app`; tên này chỉ minh họa. Chọn `:app:clean` để không tác động tới outputs của mọi module khi chỉ một module lỗi.

### 8.2. `--rerun-tasks` yêu cầu chạy lại task actions

~~~bash
./gradlew compileJava --rerun-tasks
~~~

Nó là thao tác **execution**, không phải dependency refresh. Có thể dùng khi nghi up-to-date check/task cache khiến một task không chạy. Không mặc định dùng nó trên mọi CI run vì mất lợi ích incremental/up-to-date.

### 8.3. `--no-build-cache` tắt output cache cho lượt lệnh

~~~bash
./gradlew compileJava --no-build-cache
~~~

Cờ này **không ép task chạy lại** nếu local output vẫn hợp lệ: `compileJava UP-TO-DATE` vẫn có thể xuất hiện. `FROM-CACHE` là task output restore; `UP-TO-DATE` là local output vẫn còn hợp lệ. Cờ này cũng không yêu cầu Gradle tải lại dependency JAR.

### 8.4. `--no-configuration-cache` tắt reuse configuration

~~~bash
./gradlew help --no-configuration-cache
~~~

Cờ này khiến build cấu hình lại cho lượt invocation nhưng không phải thao tác xóa downloaded dependency cache hoặc output cache. Configuration cache thường nằm dưới `<root-project>/.gradle/configuration-cache`; không tự tìm một thư mục con đó rồi xóa nếu chưa có nguyên nhân rõ.

### 8.5. `./gradlew --stop` chỉ dừng daemons

~~~bash
./gradlew --stop
~~~

Lệnh này yêu cầu dừng Gradle daemons của Gradle version tương ứng; nó **không xóa cache**. Có ích trước các thao tác bảo trì thật nếu nhóm đã phê duyệt, nhưng không đảm bảo mọi process Gradle khác hoặc CI agent khác ngừng dùng cùng storage. Với shared cache, vẫn phải xác nhận concurrency/quyền sở hữu trước khi dọn bất cứ file nào.

## 9. Xóa cache có mục tiêu: chiến lược ưu tiên

**Bậc 1 — Chẩn đoán và thử phương án không phá dữ liệu**

1. Ghi lại lệnh đã fail, exception, module coordinate (GAV) và repository thực tế.
2. Xem `dependencyInsight` (Gradle) hoặc `dependency:tree` (Maven).
3. Kiểm tra cờ offline, dynamic/changing, version lock/BOM và network/credentials.
4. Nếu nghi stale metadata, chạy **một lần** với `--refresh-dependencies` hoặc Maven `-U`.
5. Xây lại đúng task và kiểm tra output/behavior.

**Bậc 2 — Cô lập thay vì xóa cache chung**

Nếu Gradle có biểu hiện nghi cache local hỏng mà refresh không giải quyết, thử với **Gradle User Home riêng**. Điều này tạo môi trường dependency metadata/artifact cache mới mà **không đụng cache của các project khác**. Lệnh với Gradle wrapper:

~~~bash
./gradlew -g .gradle-diagnostic-home clean build
~~~

Ý nghĩa: `-g`/`--gradle-user-home` trỏ Gradle User Home vào thư mục local khác; Gradle có thể tải lại các dependencies và plugin metadata cần thiết. Phải có mạng/repository phù hợp, dung lượng đủ, và không nên commit thư mục diagnostic vào source control. Wrapper bootstrap có các quy tắc download distribution riêng, nên đảm bảo wrapper cũng sẵn sàng.

Nếu build thành công ở user home mới nhưng fail với user home cũ trong cùng JVM/repositories/toolchain, đó là **bằng chứng đáng điều tra về trạng thái cache/môi trường cũ**, chưa phải chứng minh một artifact cụ thể bị hỏng. So sánh dependency graph, repository settings, credentials, wrapper và daemon environment.

Với Maven, bạn có thể dùng **local repository tạm** thay vì xóa `~/.m2/repository`:

~~~bash
mvn -Dmaven.repo.local=./.m2-diagnostic-repo clean verify
~~~

Dùng project có `pom.xml` và Maven phù hợp. Dấu chấm/slash có ý nghĩa đường dẫn tương đối từ current working directory; phải bảo đảm không commit thư mục đó. Nó giúp thử resolution sạch và tách tác động khỏi local repository thường dùng.

**Ưu điểm của cô lập:** giữ nguyên cache hiện có để phục vụ điều tra và không phá builds khác. **Đổi lại:** có thể phải tải lại nhiều dependencies/plugins, chiếm disk và gặp mirror/network limits; không chọn liên tục cho mọi lượt build.

**Bậc 3 — Xóa đúng artifact hoặc directory đã xác định**

Chỉ khi có bằng chứng artifact local cụ thể bị hỏng và có quy trình phê duyệt:

- Dừng/đảm bảo không có process đang sử dụng phần cache đó.
- Xác định **đường dẫn thực** từ log và dependency coordinate, không đoán từ tên JAR.
- Kiểm tra nó nằm trong user home/local repo mong muốn, không phải thư mục dùng chung.
- Ưu tiên **di chuyển để cách ly** vào một vị trí backup được quản lý thay vì xóa không thể khôi phục.
- Xóa/khôi phục đúng file/version, rồi chạy resolve lại online.
- Chỉ dọn bản backup khi có build và runtime validation pass.

**Không chạy** một lệnh như `rm -rf ~/.gradle` hay `rm -rf ~/.m2/repository` chỉ để sửa một dependency. Nó có thể xóa toàn bộ cached plugin artifacts, local-only Maven installs và dữ liệu cần cho offline development.

## 10. Gradle có lệnh “purge một GAV” built-in không?

Trong Gradle CLI cơ sở, không có một cờ phổ thông được khuyến nghị giống `--refresh-one-module=com.example:lib`. `--refresh-dependencies` là **cờ của toàn invocation** và xử lý dependency resolution của các configurations đang được yêu cầu.

Gradle file store dựa trên checksum và metadata binary, có cơ chế locking, reference theo repository. Vì vậy “tìm thư mục bằng tên version rồi xóa” không phải thao tác cache maintenance chính thức, không an toàn khi concurrent builds còn chạy và có thể để metadata chưa đồng bộ.

Nếu bắt buộc xử lý một artifact lỗi, **cách được ưu tiên** là:

1. Dùng `dependencyInsight` xác nhận module/version và nguồn.
2. Dùng `--refresh-dependencies` kiểm tra remote và hashes.
3. Dùng `-g` user home cô lập để xác định cache local có phải nguyên nhân.
4. Chỉ khi repo/team có quy trình bảo trì cache thủ công được duyệt mới can thiệp vào một directory của artifact dưới `modules-2/files-2.1`, sau khi ngừng các process dùng cache và có backup.
5. Chạy lại build online với refresh để Gradle tái tạo trạng thái cần thiết; không sửa metadata binary bằng editor.

Ví dụ **đường dẫn chỉ để nhận diện**, không phải lệnh xóa:

~~~text
~/.gradle/caches/modules-2/files-2.1/
  com.example/
    demo-library/
      1.0.0/
        <checksum-folder>/
          demo-library-1.0.0.jar
~~~

`<checksum-folder>` là ký hiệu, không phải folder cố định. Nếu dependency thật là Spring Boot starter, nó còn liên quan hàng chục transitive artifacts, BOM và metadata. Xóa file starter JAR riêng lẻ không chắc giải quyết được lỗi version conflict hoặc missing class từ thư viện khác.

## 11. Maven: `-o`, `-U` và xóa đúng artifact

Maven có những điểm tương đương nhưng cách cài đặt cache khác Gradle. Maven local repository thường ở `~/.m2/repository` và chứa artifact được download, metadata và cả các module đã `mvn install` tại máy.

### 11.1. Maven offline

~~~bash
mvn -o verify
~~~

`-o` là Maven offline mode, sử dụng local repository; build có thể fail nếu thiếu plugin, parent POM, import BOM, artifacts hoặc transitive dependencies. Giống Gradle, Maven offline **không chặn toàn bộ network do code kiểm thử tự thực hiện**.

Maven wrapper có thể cần tải Maven distribution trước khi chính `mvn` xử lý cờ offline; một máy không có Maven wrapper distribution không được bảo đảm chạy offline chỉ bằng thêm `-o`.

### 11.2. Maven update check

~~~bash
mvn -U verify
~~~

Theo Maven CLI, `-U` bắt Maven kiểm tra cập nhật **SNAPSHOT và các release từng bị thiếu** theo cơ chế resolution. Không nên nói cờ này luôn “tải lại tất cả release JAR”. Đối với **fixed released artifact đã có** trong local repo nhưng file bị hỏng, cần quy trình re-resolve/purge phù hợp thay vì kỳ vọng `-U` luôn thay thế file.

Tương tự Gradle, Maven `-U` có thể phát sinh remote lookups. Nếu repository proxy thiếu quyền hoặc mạng không có, refresh có thể fail; đừng ghép nó với `-o` và kỳ vọng vừa offline vừa tải bản mới.

### 11.3. Maven purge-local-repository: cách giới hạn mục tiêu

Maven Dependency Plugin cung cấp goal `dependency:purge-local-repository` để loại dependencies khỏi local repository. **Không chạy goal trống tham số một cách vô tư**: mặc định nó có thể purge toàn bộ dependency tree của project rồi resolve lại, gây nhiều network requests.

Nếu dependency **đang thuộc cây dependency hiện tại**, lọc bằng `include`:

~~~bash
mvn dependency:purge-local-repository -Dinclude=org.slf4j:slf4j-api -DreResolve=false
~~~

Lệnh trên chỉ là ví dụ cú pháp cho dependency plugin; khi dùng thật thay GAV theo module đang lỗi. `include` thường là cặp `groupId:artifactId`; `-DreResolve=false` tránh goal tự động re-resolve ngay lập tức. Sau đó chạy online:

~~~bash
mvn -U verify
~~~

Maven có thể tải lại artifact bị purge khi build cần; tùy repository, fixed release vẫn phải có trong nguồn remote hoặc mirror. Nếu nguồn đã bỏ artifact thì purge có thể khiến project **không còn build được**.

Với artifact **không thuộc dependency tree hiện tại**, ví dụ parent POM hay Maven plugin, tài liệu Maven Dependency Plugin mô tả tham số `manualInclude`:

~~~bash
mvn dependency:purge-local-repository -DmanualInclude=org.apache:apache
~~~

Đây là **ví dụ lệnh theo tài liệu**, không phải yêu cầu xóa parent POM thật trên máy. Nếu dùng `manualInclude`, chỉ rõ GAV mục tiêu và hiểu việc purge không tự đem artifact trở lại khi chưa có lượt resolve phù hợp. Không kết hợp bừa `manualInclude` với `include/exclude`.

**Quan trọng:** purge goal tự thân cũng cần Maven Dependency Plugin và metadata của nó. Nếu local repo/plugin bị hỏng đến mức không chạy được goal, thử repository cô lập, sửa mirror hoặc dùng quy trình bảo trì do team cho phép.

### 11.4. Maven xóa một version cụ thể bằng filesystem — trường hợp cuối

Cấu trúc Maven local repository thường dễ đọc:

~~~text
~/.m2/repository/
  com/example/demo-library/1.0.0/
    demo-library-1.0.0.jar
    demo-library-1.0.0.pom
    ... metadata / checksum ...
~~~

Nhưng việc xóa thư mục `1.0.0` vẫn là thao tác nguy hiểm nếu:

- Artifact này được `mvn install` tại máy, chưa có bản trên remote.
- Có build Maven khác đang dùng cùng local repository.
- Repository mirror hoặc network không cho tải lại.
- Package/version là một release cố định đã bị xóa trên server.
- Artifact chứa nội dung riêng mà project khác đang phụ thuộc.

Ưu tiên goal `purge-local-repository` và chỉ bảo trì thủ công khi xác định đúng artifact, có backup và biết nguồn thay thế chắc chắn. **Đừng xóa groupId folder cả cây** để sửa một JAR.

## 12. Ví dụ Spring Boot Java 17 chạy được để phân biệt ba thao tác

Chọn một project Gradle Groovy hoặc Kotlin DSL và cùng Java source. Không cần database hay network runtime để tạo giá trị demo.

Cây thư mục:

~~~text
dependency-cache-demo/
├── settings.gradle            # nếu dùng Groovy
├── build.gradle               # nếu dùng Groovy
│   hoặc settings.gradle.kts   # nếu dùng Kotlin
│   hoặc build.gradle.kts      # nếu dùng Kotlin
└── src/main/java/com/example/cache/
    └── DependencyCacheApplication.java
~~~

**Không để đồng thời hai cặp build files trong cùng một module** rồi nghĩ cả hai được thực thi. Nếu dùng Maven cho phần đối chiếu, tạo một project riêng với POM tương ứng.

### 12.1. Gradle Groovy DSL — settings.gradle

~~~groovy
rootProject.name = 'dependency-cache-demo'
~~~

### 12.2. Gradle Groovy DSL — build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

### 12.3. Gradle Kotlin DSL — settings.gradle.kts

~~~kotlin
rootProject.name = "dependency-cache-demo"
~~~

### 12.4. Gradle Kotlin DSL — build.gradle.kts

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

Hai scripts định nghĩa cùng một Java/Spring Boot project, cùng dependency scopes, toolchain và task behavior. Spring Boot plugin thêm task `bootJar` khi kết hợp Java plugin.

### 12.5. Main Java đầy đủ

Tệp `src/main/java/com/example/cache/DependencyCacheApplication.java`:

~~~java
package com.example.cache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DependencyCacheApplication {

    public static void main(String[] args) {
        SpringApplication.run(DependencyCacheApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo() {
        return args -> System.out.println("DEPENDENCY_CACHE_DEMO_OK");
    }
}
~~~

Đây là ứng dụng console. Khi start, Spring Boot log có thể xuất hiện; một dòng **do ứng dụng tự in** chính xác là:

~~~text
DEPENDENCY_CACHE_DEMO_OK
~~~

Vì không có web starter hay background service, process có thể tự kết thúc sau `CommandLineRunner`. Không nên coi việc kết thúc sớm là lỗi dependency cache.

### 12.6. Test Java để build thực sự chạy JUnit

Tệp `src/test/java/com/example/cache/DependencyCacheApplicationTest.java`:

~~~java
package com.example.cache;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DependencyCacheApplicationTest {

    @Test
    void verifiesJavaRuntime() {
        assertEquals(4, 2 + 2);
    }
}
~~~

Task `test` cần `useJUnitPlatform()` và `spring-boot-starter-test` như trong build script. Test đơn giản này giúp chứng minh khi chạy `./gradlew build`, Gradle có thể thực thi JUnit task; nó không thử một remote repository thật nên không gây phụ thuộc mạng ngoài lúc resolution.

### 12.7. Build và chạy

~~~bash
./gradlew --version
./gradlew clean build
java -jar build/libs/dependency-cache-demo-0.1.0.jar
~~~

Với project name/version ở ví dụ và Boot default classifier, `bootJar` thường tạo `build/libs/dependency-cache-demo-0.1.0.jar`. Nếu build thay đổi archiveFileName, dùng output thực tế thay vì copy cứng filename.

**Điều kiện:** có Gradle wrapper hoặc Gradle cài đúng version, Java 17 toolchain phù hợp, network cho lần resolve đầu và các repositories hợp lệ. `build.gradle` không tự sinh wrapper.

## 13. Bốn thí nghiệm có thể lặp lại

### Thí nghiệm A — online rồi offline

Chạy trong project mẫu, lúc còn mạng:

~~~bash
./gradlew clean build
./gradlew dependencyInsight --dependency spring-boot --configuration runtimeClasspath
~~~

Sau đó:

~~~bash
./gradlew clean build --offline
~~~

Nếu offline build thành công, điều đó cho thấy các dependencies/plugins cần thiết cho workflow này đã có sẵn cục bộ và Gradle không cần liên hệ remote để resolve. Nó **không chứng minh một task khác hoàn toàn sẽ chạy offline**, và không chứng minh phần test code sẽ không mở network riêng.

Nếu offline fail, đọc tên module/plugin thiếu. Cần xác định nó đã được download khi online chưa, repository nào chịu trách nhiệm, hoặc công việc khác có classpath riêng. **Không xóa cache khi cache đang thiếu dữ liệu**.

### Thí nghiệm B — làm mới metadata một lần

~~~bash
./gradlew dependencyInsight --dependency spring-boot --configuration runtimeClasspath --refresh-dependencies
~~~

Ghi lại version chọn trước/sau. Vì ví dụ dùng version Spring Boot cố định thông qua plugin/BOM, refresh có thể không thay đổi version nào. Đây vẫn là phép thử hợp lệ để hiểu rằng refresh không “tự nâng tất cả dependencies”.

Nếu có SNAPSHOT hoặc dynamic version trong ứng dụng thực, bạn mới có thể thấy bản được chọn thay đổi — tùy repository đã publish và resolution policy.

### Thí nghiệm C — output clean khác dependency cache

~~~bash
./gradlew clean
./gradlew build --offline
~~~

Lệnh `clean` làm mất outputs local dưới `build`, nhưng dependencies vẫn có thể được phục hồi từ cache Gradle User Home trong offline build. Nếu task `compileJava` chạy lại sau clean, điều đó không đồng nghĩa dependencies bị tải lại.

### Thí nghiệm D — user home cô lập, không động cache hiện tại

Khi có mạng và disk đủ:

~~~bash
./gradlew -g .gradle-diagnostic-home clean build
~~~

Gradle dùng user home khác nên có thể phải resolve/tải lại dependencies/plugins/Gradle distribution theo cách bootstrapping. Thử này làm rõ liệu cache cũ có liên quan lỗi mà **không phá** `~/.gradle` của máy. Sau khi hoàn tất, kiểm tra thư mục diagnostic trước khi quyết định xóa nó; đừng commit artifacts/cache vào Git.

Nếu cần chạy test trên CI, ghi lại build duration, cache hits, network calls và dependency graph. Đừng chỉ dựa vào một lượt build vì máy ảo, mạng và daemon warm-up đều làm thời gian biến động.

## 14. Ma trận chọn lệnh theo tình huống

| Tình huống | Hướng kiểm tra / lệnh phù hợp | Không nên làm |
| --- | --- | --- |
| Mất mạng, đã tải đủ dependencies | Gradle `--offline` / Maven `-o` | Dùng `--refresh-dependencies` mong lấy bản mới |
| Maven SNAPSHOT vừa publish | `mvn -U verify`, xem effective dependency | Xóa toàn bộ `~/.m2/repository` |
| Gradle changing/SNAPSHOT stale | `--refresh-dependencies`, xem `dependencyInsight`/TTL | Gọi `clean` rồi coi cache metadata đã reset |
| Gradle dynamic version cũ | Refresh, kiểm tra version selection và locking | Tin rằng build offline sẽ chọn bản mới |
| Fixed JAR ở Maven local repo bị hỏng | Purge đúng GAV (include/manualInclude), rồi resolve lại | Xóa cả group folder hoặc plugin repo |
| Nghi Gradle local cache corrupt | Refresh; thử `-g` user home riêng | Xóa shared `~/.gradle/caches` khi builds còn chạy |
| `compileJava UP-TO-DATE`, muốn chạy lại compiler | `--rerun-tasks` | `--refresh-dependencies` để ép compile |
| Muốn dọn file JAR build cũ | `./gradlew clean` | Xóa downloaded artifacts |
| Configuration cache stale hoặc lỗi plugin | `--no-configuration-cache` để đối chứng; sửa plugin/build logic | Xóa mọi caches |
| Task output cache không phù hợp | `--no-build-cache` hoặc `--rerun-tasks` khi cần | Tắt dependency cache bằng offline |
| Repository bị TLS/auth/HTTP 403 | Sửa credentials, mirror, truststore/repo config | Xóa cache liên tiếp không giải quyết server |
| CI dùng cache từ nhánh không tin cậy | Phân quyền cache, kiểm chứng outputs | Pull/push remote cache tùy tiện |
| Maven parent POM lỗi ở local repo | Xem effective settings; manualInclude khi phù hợp | Purge toàn cây dependency không liên quan |
| Plugin Gradle chưa tải trên máy offline | Provision wrapper/plugin cache khi online | Đổ lỗi cho main dependency starter |

Các lệnh cần được chạy trong **đúng module/root repository**, với đúng project path, phiên bản plugin và source code thực tế. Thí dụ `:app:clean` chỉ hợp lệ khi settings có module `app`.

## 15. Hệ quả bảo mật và tính tái lập

### 15.1. Cache không thay thế dependency verification

Một JAR có trong local cache không đảm bảo artifact:

- Đến từ repository được tổ chức cho phép.
- Phù hợp checksum hoặc signature đã duyệt.
- Không có lỗ hổng hoặc nguồn gốc bị thay đổi.
- Thuộc version mà BOM/dependency constraints thực sự chọn.

Gradle có dependency verification/locking, Maven có checksum policies và repository controls; xây dựng quy trình supply-chain phù hợp thay vì chỉ dựa vào cache hit. Remote repository credentials không nên hardcode trong build.gradle/pom.xml và không nên được log ra.

### 15.2. Re-publish cùng tọa độ có thể gây bất nhất

Nếu một fixed release `1.0.0` bị publisher thay bytes sau khi đã publish, developer A và CI B có thể có checksum/cached contents khác nhau. Build “thành công” nhưng không tái lập. Giải pháp bền vững là **bất biến hóa release artifact**, phát hành version mới, khóa version/checksum và điều tra publisher. Thói quen chạy refresh mỗi lần không thay được chính sách artifact immutability.

SNAPSHOT có mục tiêu đổi theo thời gian, nên phải chấp nhận rằng offline dùng bản đã cache và online refresh có thể nhận bản khác. Nếu cần reproducible deployment, pin snapshot timestamp/version hoặc dùng release artifacts được quản lý.

### 15.3. Shared cache và concurrency

Gradle file store/metadata có cơ chế locking; tự xóa file trong lúc Gradle daemons/builds đang dùng cache có thể gây lỗi khó tái hiện. Với CI containers, chỉ dùng cơ chế cache copy/read-only sharing được Gradle/CI provider hỗ trợ, tránh nhiều process ghi đồng thời vào một cache directory một cách tự phát.

Maven local repository cũng có thể được nhiều process dùng chung. Goal purge hoặc xóa file thủ công khi Maven build khác đang resolve có thể gây lỗi. Trước khi dọn, xác nhận phạm vi user home/agent và không phá workflows khác.

### 15.4. Phân biệt lỗi offline thật với network do app

Nếu chạy `./gradlew test --offline` và integration test gọi database, HTTP API, Docker Hub hoặc container registry, nó vẫn có thể fail do mạng. Điều đó không chứng minh Gradle đang truy vấn Maven repository trái với `--offline`; tiến trình test có thể có network activity riêng. Kiểm tra log theo process: Gradle resolution vs test/app/docker.

## 16. Lỗi phổ biến và điều tra từng bước

### 16.1. `Offline mode: No cached version available`

Nguyên nhân thường gặp: module hoặc metadata chưa có trong Gradle User Home, dynamic version listing chưa cache phù hợp hoặc Gradle plugin distribution thiếu.

Hướng xử lý: xác nhận đúng module/version/repositories; chạy online một workflow bao phủ cần thiết; thử offline lại. Không xóa dữ liệu local khi bản chất vấn đề là **thiếu** dữ liệu local.

### 16.2. `Could not resolve all files for configuration`

Đây là lỗi bao trùm, cần đọc stack trace hoặc `--info`. Có thể do:

- Sai coordinate/version.
- Không được phép truy cập repository, mirror/proxy lỗi.
- Version conflict hoặc metadata không hợp lệ.
- Offline thiếu artifact.
- File artifact bị hỏng hoặc checksum không khớp.

Xác định tên configuration (compileClasspath/runtimeClasspath/testRuntimeClasspath), artifact và repository trước khi chọn refresh hay purge.

### 16.3. Gradle refresh vẫn lấy bản cũ

Kiểm tra chính sách repository: liệu bản mới đã thực sự được publish vào đúng URL? Dynamic/changing semantics? Dependency locks/BOM/platform constraints có cố định version? Gradle có thể revalidate checksum và giữ file cũ **vì remote vẫn báo cùng artifact**. Thử với user home riêng để phân tách local-cache hypothesis và repository serving issue.

### 16.4. Maven `-U` không thay fixed release JAR

`-U` phục vụ update checking theo Maven semantics, không cam kết re-download mọi fixed release. Nếu local artifact nghi hỏng, dùng goal purge với `include` đúng tọa độ hoặc local repo cô lập. Nếu artifact local là một bản chỉ tồn tại do `mvn install`, phải build lại module/restore artifact từ nguồn tin cậy chứ không xóa.

### 16.5. Build vẫn `FROM-CACHE` dù đã refresh dependency

`FROM-CACHE` là **task output cache hit**. Nếu resolved task inputs thực tế không thay đổi, output vẫn có thể reuse, bất chấp dependency metadata vừa được kiểm tra lại. Khi cần xác nhận task action chạy, dùng `--rerun-tasks`; không nhầm cờ refresh dependency với cờ task execution.

### 16.6. CI cache hit nhưng runtime JAR thiếu class

Có thể là dependency scope thiếu, task output cache có inputs không khai báo đúng, container copy nhầm `-plain.jar` hoặc artifact publication sai. Check runtimeClasspath, output `bootJar`, manifest, Boot archive contents và task cache policy. Tải lại dependency không phải lúc nào cũng sửa runtime packaging.

## 17. Bài tập thực hành có đáp án

### Bài 1. Mạng đứt sau một lần build online

**Câu hỏi:** Project đã chạy `./gradlew clean build` online, giờ mất mạng. Lệnh nào phù hợp nhất để thử build lại từ cache?

**Đáp án:** `./gradlew build --offline`. Nếu fail vì một plugin/metadata/artifact chưa cache, cần chuẩn bị dữ liệu khi có mạng trở lại. Không dùng `--refresh-dependencies` để cập nhật khi đang offline.

### Bài 2. Tải lại một SNAPSHOT của Gradle

**Câu hỏi:** SNAPSHOT vừa publish và cần Gradle kiểm tra bản mới ngay, không chờ TTL. Dùng gì?

**Đáp án:** `--refresh-dependencies`, sau đó kiểm tra graph/behavior. Lệnh yêu cầu remote verification, không đảm bảo mọi JAR sẽ bị download lại.

### Bài 3. `clean` có xóa modules-2 không?

**Đáp án:** Không. `clean` thường chỉ dọn local build outputs. Dependency cache trong Gradle User Home vẫn tồn tại, do đó build sau clean vẫn có thể chạy offline.

### Bài 4. Phân biệt UP-TO-DATE với cache download

**Câu hỏi:** log hiển thị `:compileJava UP-TO-DATE`. Có thể kết luận thư viện đã được refresh chưa?

**Đáp án:** Không. Đây là task up-to-date outcome; nó không nói liệu dependency metadata được hỏi lại hay chưa.

### Bài 5. Maven fixed release bị hỏng

**Câu hỏi:** file một library release `org.slf4j:slf4j-api` tại local repository nghi corrupt. Có nên xóa cả `~/.m2/repository` không?

**Đáp án:** Không. Trước hết kiểm tra stack trace/checksum; dùng Maven Dependency Plugin với `-Dinclude=org.slf4j:slf4j-api` và xem nguồn remote, hoặc repo tạm nếu cần chứng minh giả thuyết. Chỉ purge khi có nguồn tải lại đáng tin.

### Bài 6. User home cô lập

**Câu hỏi:** `./gradlew -g .gradle-diagnostic-home clean build` thành công, build mặc định fail. Có được kết luận tất cả cache dưới `~/.gradle` hỏng không?

**Đáp án:** Không. Nó chỉ cho thấy trạng thái/environment khác giữa hai user homes. Cần so sánh repositories/credentials, metadata, daemon và task cache trước khi đụng cache chung.

### Bài 7. Offline và plugin

**Câu hỏi:** runtime starter JAR đã cache nhưng Gradle wrapper chưa tải distribution và Gradle Plugin Portal metadata chưa có. `--offline` có giúp chạy ngay không?

**Đáp án:** Không chắc; wrapper bootstrap và plugin resolution cũng phải có dữ liệu/công cụ local. Provision online hoặc dùng artifact/mirror nội bộ đúng quy trình trước.

### Bài 8. CI thay đổi repository

**Câu hỏi:** cùng GAV nhưng đổi từ mirror A sang mirror B khiến Gradle có request mới. Có phải cache kém hiệu quả?

**Đáp án:** Không nhất thiết. Gradle ghi metadata theo repository identity để tránh nhầm nguồn; chuyển mirror có thể yêu cầu resolve lại. Kiểm tra policy và artifact identity thay vì copy thủ công data cache.

### Bài 9. Maven manual purge

**Câu hỏi:** parent POM không nằm trong dependency tree nhưng cần purging có mục tiêu. Tham số Maven nào phù hợp?

**Đáp án:** `manualInclude` với groupId/artifactId chính xác theo tài liệu Maven Dependency Plugin, sau khi đã xác nhận parent/plugin artifact cần xử lý và có nguồn thay thế. Không purging toàn bộ dependencies.

### Bài 10. “Offline build xanh” có bảo đảm phát hành an toàn không?

**Đáp án:** Không. Cần dependency verification/locking, test, artifact checks, security review và provenance. Offline chỉ nói quá trình dependency resolution không cần remote ở lần thực thi đó, không nói dữ liệu đã cache đáng tin hay release đã đủ QA.

## 18. Checklist quyết định trước khi can thiệp cache

- [ ] Đã phân loại đúng lỗi: dependency resolution, plugin, configuration, task output, source code hay runtime.
- [ ] Đã ghi lại **group:artifact:version**, configuration, repository và command fail.
- [ ] Đã xem `dependencyInsight`/`dependency:tree` thay vì dựa tên JAR trên disk.
- [ ] Nếu offline, đã bảo đảm wrapper/plugins/dependencies cho requested tasks có sẵn.
- [ ] Nếu stale SNAPSHOT/dynamic, đã dùng `--refresh-dependencies` hoặc Maven `-U` đúng mục tiêu và biết giới hạn của cờ.
- [ ] Không nhầm `clean` với xóa Gradle dependency cache hoặc Maven local repo.
- [ ] Không nhầm `--no-build-cache`/`--no-configuration-cache`/`--rerun-tasks` với dependency refresh.
- [ ] Đã ưu tiên user home/repository **cô lập** trước khi xóa cache chung.
- [ ] Nếu buộc phải purge, chỉ định đúng artifact/version, có backup và nguồn restore online.
- [ ] Đã kiểm tra không có concurrent processes đang dùng phần cache sẽ thay đổi.
- [ ] Không xóa artifacts Maven cài local duy nhất, JAR nội bộ chưa publish hoặc metadata của project khác.
- [ ] Không dùng một script `rm -rf` không kiểm tra absolute path, đặc biệt trên CI/shared agents.
- [ ] Đã chạy lại clean build và smoke-test production artifact sau thay đổi.
- [ ] Đã ghi lại nguyên nhân, phạm vi cache đã tác động và cách tái lập trong CI.

**Kết luận:** **Offline** là chọn **không truy vấn remote** và chấp nhận giới hạn dữ liệu cục bộ; **refresh** là **kiểm tra lại remote resolution** mà không nhất thiết tải lại mọi file; **xóa cache có mục tiêu** là bước bảo trì **cuối cùng**, chỉ áp dụng lên dữ liệu nghi lỗi đã được xác định. Hầu hết vấn đề được xử lý tốt hơn bằng chẩn đoán đúng configuration/repository, một lần refresh có kiểm chứng, hoặc chạy với user home riêng thay vì xóa sạch dữ liệu.

## 19. Tài liệu chính thức

- Gradle — Dependency Caching: https://docs.gradle.org/current/userguide/dependency_caching.html
- Gradle — Command-Line Interface (`--offline`, `--refresh-dependencies`, `--rerun-tasks`, `-g`): https://docs.gradle.org/current/userguide/command_line_interface.html
- Gradle — Gradle User Home: https://docs.gradle.org/current/userguide/directory_layout.html
- Gradle — Dependency Insight: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Apache Maven — Maven CLI Options: https://maven.apache.org/ref/current/maven-embedder/cli.html
- Apache Maven — Local Repositories: https://maven.apache.org/repositories/local.html
- Apache Maven Dependency Plugin — Purging Local Repository Dependencies: https://maven.apache.org/components/plugins/maven-dependency-plugin/examples/purging-local-repository.html
- Apache Maven Dependency Plugin — purge-local-repository goal: https://maven.apache.org/plugins/maven-dependency-plugin/purge-local-repository-mojo.html
- Spring Boot 3.3 Gradle Plugin — Packaging: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html

Khi đổi Gradle wrapper, Maven version hoặc Spring Boot plugin, hãy đối chiếu semantics của các cờ với **tài liệu phiên bản thực tế**. Không dùng “cache bị lỗi” như chẩn đoán mặc định khi chưa biết Gradle/Maven đã resolve artifact nào, từ repository nào và build đang thiếu gì.
