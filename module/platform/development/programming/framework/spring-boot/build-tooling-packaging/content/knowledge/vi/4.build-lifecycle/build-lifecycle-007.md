# Đọc kế hoạch thực thi bằng trợ giúp Maven và Gradle --dry-run

## 1. Vì sao cần đọc kế hoạch trước khi chạy build?

Một lệnh trông đơn giản như **mvn package** hoặc **./gradlew build** thực tế có thể kích hoạt nhiều công việc: xử lý resources, biên dịch, chạy unit test, kiểm tra chất lượng, tạo JAR và đóng gói executable JAR cho Spring Boot. Khi dự án có nhiều module hoặc plugin tự thêm tác vụ, người phát triển thường không biết chính xác bước nào sẽ được gọi và vì sao.

**Đọc kế hoạch thực thi** là xác định, trước khi cho build thực sự chạy:

- Lệnh đích là **phase/goal** của Maven hay **task** của Gradle?
- Những bước nào được lên lịch, bước nào được gọi vì phụ thuộc?
- Thứ tự dự kiến là gì và plugin nào thêm bước đó?
- Lệnh có thể biên dịch, chạy test, xóa output, tạo JAR, ghi repository hoặc triển khai không?
- Kế hoạch có thay đổi khi bật profile, truyền property, chọn module hoặc loại trừ task không?

Kỹ năng này rất hữu ích khi phân tích một bản dựng Spring Boot chậm, giải thích vì sao **repackage** chạy, xem pipeline có gọi test không, hoặc kiểm tra phạm vi của một lệnh mới trước khi thử trên dự án thật.

**Điểm khác biệt phải nhớ:** Gradle có tùy chọn chung **--dry-run** (viết tắt **-m**) để hiển thị các task dự kiến được chọn mà không chạy task actions. Maven không có một tùy chọn **--dry-run** chung tương đương cho toàn bộ lifecycle. Với Maven, phải ghép thông tin từ **lifecycle**, **effective POM**, **active profiles** và trợ giúp của từng plugin để dự đoán chuỗi goal.

## 2. Hiểu đúng “kế hoạch”: phase, goal và task

| Câu hỏi | Maven | Gradle |
| --- | --- | --- |
| Đơn vị mà người dùng thường gọi | Lifecycle **phase** như package, verify; hoặc plugin **goal** như spring-boot:repackage | **Task** như compileJava, test, bootJar, build |
| Cách hình thành bước chạy | Binding từ packaging và các plugin executions; thứ tự phase của lifecycle | Quan hệ task dependency, task ordering và task graph do plugin/build script cấu hình |
| Lệnh xem cấu hình | help:effective-pom, help:active-profiles, help:describe | tasks, help --task, properties |
| Lệnh xem danh sách bước dự kiến mà không chạy actions | Không có dry-run chung của Maven CLI | ./gradlew build --dry-run |
| Điều còn phải kiểm tra | Goals được bind theo phase, plugin config, active profile, lệnh gọi trực tiếp | Logic cấu hình task, điều kiện onlyIf, task graph, excluded task, môi trường runtime |

### 2.1. Maven: phase không phải plugin goal

**package** là một phase của default lifecycle. Khi gọi **mvn package**, Maven thực hiện các phase trước đó trong cùng lifecycle và những plugin goals được bind vào các phase liên quan. Với packaging dạng **jar** thông thường, một số binding mặc định có thể gồm:

~~~text
process-resources  -> resources:resources
compile            -> compiler:compile
process-test-resources -> resources:testResources
test-compile       -> compiler:testCompile
test               -> surefire:test
package            -> jar:jar
~~~

Đây là sơ đồ **minh họa các binding thông dụng**, không phải output nguyên văn của một lệnh Maven. Mỗi dự án còn có thể thêm goal vào phase qua plugin, parent POM, profile, extension hoặc packaging khác. Có phase không bind goal nên không làm việc đáng kể. Các bước của clean, default và site là các lifecycle riêng; **mvn clean package** chạy clean rồi đến các phase dẫn tới package.

### 2.2. Gradle: task graph không đồng nghĩa danh sách khai báo task

**build** là một task thường được Java plugin cung cấp; nó phụ thuộc vào các task khác. Khi gọi **./gradlew build**, Gradle lập đồ thị những task được yêu cầu và dependency bắc cầu, sau đó sắp xếp lịch thực thi theo các ràng buộc. Tùy plugin, có thể xuất hiện **compileJava**, **processResources**, **classes**, **jar**, **assemble**, **test**, **check**, **build**, cùng các task của Spring Boot như **bootJar**.

**./gradlew tasks** liệt kê các task có trong dự án. Nó chưa trả lời đầy đủ câu hỏi “nếu chạy build thì những task nào thực sự được chọn?”. Để xem kế hoạch của một lệnh cụ thể, dùng **--dry-run** với chính task đó.

## 3. Gradle: ba lớp quan sát kế hoạch

### 3.1. Khám phá những task có sẵn

Chạy trong thư mục gốc của dự án đã có Gradle Wrapper:

~~~bash
./gradlew tasks
./gradlew tasks --all
./gradlew help --task build
./gradlew help --task bootJar
~~~

- **tasks**: liệt kê các task theo nhóm và mô tả mà plugin/build script cung cấp.
- **tasks --all**: cung cấp danh sách rộng hơn, kể cả những task không nằm trong danh sách mặc định.
- **help --task build**: cho biết đường dẫn, loại task, mô tả và các tùy chọn của task tên build.
- **help --task bootJar**: hữu ích khi ứng dụng đã áp dụng Spring Boot Gradle Plugin và tạo task bootJar. Với một module không áp dụng plugin đó, task có thể không tồn tại.

Ở dự án nhiều module, có thể xem task của một module bằng cách chỉ rõ đường dẫn, ví dụ **:app:bootJar**; tên **app** ở đây chỉ là ví dụ, phải thay bằng tên project thực tế. Đường dẫn có dấu **:** đứng đầu là đường dẫn task Gradle, không phải cú pháp Maven.

Lệnh trợ giúp giúp biết task **là gì**, còn dry-run giúp thấy **những task nào thuộc kế hoạch của một đích cụ thể**.

### 3.2. Xem nhiệm vụ dự kiến bằng --dry-run

~~~bash
./gradlew build --dry-run
./gradlew test -m
./gradlew bootJar --dry-run
./gradlew clean bootJar --dry-run
~~~

Cả **--dry-run** và **-m** đều yêu cầu Gradle vô hiệu hóa các **task actions** và in những task sẽ được chọn. Chúng không chạy hành động biên dịch, test hay đóng gói như một build thật.

Ví dụ **minh họa** một dự án Spring Boot Gradle có Java plugin, khi chạy **./gradlew bootJar --dry-run** có thể thấy các dòng tương tự:

~~~text
> Task :compileJava SKIPPED
> Task :processResources SKIPPED
> Task :classes SKIPPED
> Task :resolveMainClassName SKIPPED
> Task :bootJar SKIPPED

BUILD SUCCESSFUL
~~~

Đây không phải output cố định: số task, đường dẫn, thứ tự và tên task thay đổi theo version Gradle, Spring Boot plugin, cách cấu hình và module. Từ chuỗi này ta suy ra **bootJar phụ thuộc các bước cần thiết để tạo archive**. Ta **không** được suy ra Java đã biên dịch thành công, test đã chạy, hay JAR đã được tạo.

**Chữ SKIPPED trong dry-run có nghĩa task actions được bỏ qua do chế độ xem kế hoạch**; không có nghĩa task ấy sẽ luôn bị skip khi chạy thật. Tương tự, **BUILD SUCCESSFUL** trong dry-run chỉ cho biết Gradle lập/cấu hình được kế hoạch trong điều kiện đó, không xác nhận kết quả biên dịch, kiểm thử hay runtime.

### 3.3. Xem đồ thị rõ hơn khi Gradle hỗ trợ

Các bản Gradle có **--task-graph** (tùy chọn xuất hiện từ Gradle 9.1) có thể in thông tin đồ thị phụ thuộc ngoài cách hiển thị dry-run. Hãy kiểm tra **./gradlew --version** và **./gradlew --help** trước khi dùng, bởi nhiều dự án Spring Boot đang ghim Gradle 8.x sẽ **không có** tùy chọn này.

Ngay cả khi chỉ có **--dry-run**, thứ tự task được in vẫn hữu ích để đọc trình tự dự kiến. Tuy nhiên, một danh sách tuyến tính **không hiển thị đầy đủ mọi cạnh phụ thuộc**: thấy B sau A chưa chứng minh trực tiếp rằng B dependsOn A. Muốn khẳng định quan hệ, xem build script, plugin documentation và task graph được Gradle cung cấp.

## 4. Ví dụ Gradle có thể thực hành: xem trước mà không chạy actions

Để quan sát một đồ thị nhỏ, tạo một project Gradle với tệp **settings.gradle**:

~~~groovy
rootProject.name = 'task-plan-demo'
~~~

Và tệp **build.gradle**:

~~~groovy
plugins {
    id 'base'
}

tasks.register('prepareDemo') {
    group = 'demo'
    description = 'Chuan bi du lieu demo'
    doLast {
        println('prepare executed')
    }
}

tasks.register('packageDemo') {
    group = 'demo'
    description = 'Dong goi demo'
    dependsOn('prepareDemo')
    doLast {
        println('package executed')
    }
}
~~~

Đây là **cấu hình Gradle Groovy DSL độc lập cho demo**, không phải Java class; bạn cần Gradle tương thích và **Gradle Wrapper** nếu muốn chạy bằng các lệnh **./gradlew** bên dưới. Plugin **base** có sẵn trong Gradle, không tải thêm Spring Boot. Hai task là task tự tạo nên không phụ thuộc vào số phiên bản Spring Boot đang dùng.

Trước hết xem thông tin:

~~~bash
./gradlew tasks --all
./gradlew help --task packageDemo
./gradlew packageDemo --dry-run
~~~

Dry-run sẽ báo rằng **prepareDemo** và **packageDemo** đều nằm trong kế hoạch; nó không in hai chuỗi **prepare executed** và **package executed** vì các chuỗi đó nằm trong **doLast actions**. Dạng output dự kiến (chỉ hai dòng task chính):

~~~text
> Task :prepareDemo SKIPPED
> Task :packageDemo SKIPPED
~~~

Nếu chạy thật:

~~~bash
./gradlew packageDemo
~~~

Hai task được thực thi theo thứ tự **prepareDemo** trước **packageDemo**, và phần doLast in ra chính xác các thông điệp của ví dụ:

~~~text
prepare executed
package executed
~~~

Gradle có thể in thêm thông tin về task, thời gian và trạng thái build; đoạn trên chỉ trích **hai dòng doLast**. Dùng **--dry-run** để trả lời “task nào được lên lịch”, rồi chỉ chạy thật khi cần xác nhận tác dụng của task.

**Thí nghiệm quan trọng:** đổi **dependsOn('prepareDemo')** trong packageDemo thành không có dependsOn, rồi chạy lại **./gradlew packageDemo --dry-run**. Lúc đó danh sách kế hoạch chỉ còn **packageDemo** (trừ khi một cấu hình khác thêm dependency). Điều này cho thấy dry-run phản ánh **đồ thị thực sự được cấu hình** chứ không phải cứ chạy một task thì Gradle chạy mọi task được khai báo.

## 5. Maven: đọc kế hoạch qua lifecycle và các công cụ trợ giúp

### 5.1. Maven không có --dry-run toàn cục giống Gradle

Không nên hướng dẫn **./mvnw package --dry-run** như một cách chuẩn để in toàn bộ plugin goals mà không thực thi. Trong Maven CLI, **--dry-run** không phải tùy chọn chung của lifecycle tương tự Gradle. Một số **plugin goals riêng lẻ** có thể có tham số **dryRun**, nhưng hiệu lực chỉ áp dụng **cho goal đó** khi tài liệu plugin quy định; nó không hủy thực thi các goal khác trong lifecycle.

Không dùng **-DdryRun=true** rồi mặc định toàn bộ Maven build sẽ chỉ mô phỏng. Đây đơn thuần là một user property; nếu không goal nào đọc nó, build có thể vẫn chạy bình thường, kể cả test, ghi file, cài artifact hay deploy.

**Cách đúng:** tìm hiểu lifecycle của lệnh mục tiêu, đọc **effective POM** đã xét kế thừa/profile, kiểm tra plugin executions và tra thông tin goal. Khi thực sự phải xem log trình tự các plugin goals, Maven cần chạy lệnh với phạm vi phù hợp; đó **không còn là dry-run**.

### 5.2. Xem Maven đang dùng phiên bản và lệnh nào

~~~bash
./mvnw --version
./mvnw --help
~~~

**--version** xác định bản Maven/JDK đang chạy; **--help** hiển thị các tùy chọn hỗ trợ. Trong project dùng Maven Wrapper trên Windows, gọi **mvnw.cmd** tương ứng. Dùng Wrapper giúp thống nhất bản Maven, nhưng nó không tự bảo đảm các plugin và JDK giống nhau ở mọi môi trường.

### 5.3. Đọc POM hiệu lực thay vì chỉ nhìn pom.xml tại root

~~~bash
./mvnw help:effective-pom
./mvnw help:effective-pom -Dverbose=true
./mvnw help:active-profiles
~~~

- **help:effective-pom** hiển thị cấu hình POM sau khi Maven xét parent, super POM, profile và phần cấu hình kế thừa.
- **-Dverbose=true** thêm chú thích về nguồn gốc các phần tử trong effective POM (khi dùng phiên bản Maven Help Plugin hỗ trợ); rất hữu ích để biết execution đến từ parent hay chính module.
- **help:active-profiles** cho biết profile nào hiện đang hoạt động, qua đó giải thích những plugin/dependency/config bổ sung.

Ví dụ pipeline thực chạy **./mvnw -Pci verify -DskipITs=true** thì khi xem cấu hình phải xét chính **-Pci** và property liên quan:

~~~bash
./mvnw -Pci help:active-profiles
./mvnw -Pci help:effective-pom -Dverbose=true -DskipITs=true
~~~

Nếu các property/profile khác nhau giữa bước xem và bước chạy, thông tin suy ra có thể không mô tả đúng build thật. Các lệnh trợ giúp thường không gọi compile/test/package, nhưng vẫn có thể tải plugin/dependency metadata vào cache, và không phải cam kết tuyệt đối không có tác động bên ngoài nào.

**Giới hạn quan trọng:** effective POM cho biết **cấu hình**, không phải một log đã liệt kê toàn bộ goal theo thứ tự. Những binding mặc định theo **packaging**, goal được plugin gọi thêm, logic plugin lúc chạy hoặc goal được gọi trực tiếp cần được phân tích tiếp. Đừng xem danh sách plugin theo thứ tự trong XML rồi kết luận đó chính là toàn bộ thứ tự thực thi.

### 5.4. Xem một plugin goal có tác dụng gì

~~~bash
./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail=true
./mvnw help:describe -Dplugin=org.apache.maven.plugins:maven-surefire-plugin -Dgoal=test -Ddetail=true
~~~

**help:describe** cho biết goal, mục đích, tham số và các thuộc tính được công bố bởi plugin descriptor. Ví dụ:

- **spring-boot:repackage**: đóng gói lại JAR/WAR để hỗ trợ thực thi theo cách Spring Boot.
- **surefire:test**: thực hiện unit test theo cấu hình của Maven Surefire Plugin.
- **jar:jar**: tạo Java JAR thông thường.

Thông tin này giúp hiểu “plugin goal đó làm gì?”, nhưng bản thân việc mô tả goal **không chứng minh goal có được bind vào phase package của dự án hiện tại hay không**. Muốn biết có nằm trong kế hoạch, phải kết hợp lifecycle, packaging và phần **executions** của POM đã hiệu lực.

Có thể dùng trợ giúp riêng của Spring Boot plugin nếu dự án đã cấu hình plugin:

~~~bash
./mvnw spring-boot:help -Dgoal=repackage -Ddetail=true
~~~

Các lệnh **help:describe** và **spring-boot:help** chỉ là công cụ tra cứu plugin; chúng không chạy repackage.

## 6. Ví dụ Maven cho Spring Boot: dự đoán lệnh package

Giả sử dự án có **pom.xml** dùng **spring-boot-starter-parent**, đóng gói kiểu **jar** và khai báo **spring-boot-maven-plugin**:

~~~xml
<!-- Trích đoạn minh họa bên trong một pom.xml hoàn chỉnh -->
<packaging>jar</packaging>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Đây là **một đoạn POM**, không phải tệp XML tự chạy độc lập: project thật phải có **project**, **modelVersion**, **groupId/artifactId/version**, **parent** và những dependency cần thiết. **spring-boot-starter-parent** cung cấp execution **repackage** được cấu hình theo quy ước; khi không dùng parent này, phải xem project có bind goal repackage vào lifecycle hay không.

Giả sử định chạy:

~~~bash
./mvnw clean package
~~~

Cách đọc kế hoạch:

1. **clean** thuộc clean lifecycle: mục đích là xóa sản phẩm build trước đó (thường thông qua **clean:clean**).
2. **package** thuộc default lifecycle: Maven đi qua các phase trước đó; với packaging **jar**, các mục thông thường liên quan resources, compile, test và **jar:jar**.
3. Spring Boot Maven Plugin được parent/cấu hình project bind **repackage** vào package: sau khi JAR gốc được tạo, goal này đóng gói lại thành executable JAR theo quy ước Spring Boot.
4. Plugin custom có execution ở phase khác, hoặc profile đang bật, có thể thêm goal; cần xem effective POM và lifecycle bindings.
5. Vì đây **không phải dry-run**, nếu thực sự gọi **./mvnw clean package**, Maven sẽ thực thi những plugin goals tương ứng và có thể tạo/xóa file, chạy test, cập nhật cache.

Có thể hình dung sơ đồ kiểm tra **mang tính khái niệm**:

~~~text
Người dùng: ./mvnw clean package
       |
       +--> clean lifecycle: clean:clean
       |
       +--> default lifecycle đến package
                 |
                 +--> resources:resources
                 +--> compiler:compile
                 +--> resources:testResources
                 +--> compiler:testCompile
                 +--> surefire:test
                 +--> jar:jar
                 +--> spring-boot:repackage (nếu execution đã bind)
~~~

Thứ tự trên trình bày **những goal tiêu biểu**, bỏ qua các phase không gắn goal và các plugin khác. Trong thực tế, nội dung và thứ tự cuối cùng còn phụ thuộc packaging, phiên bản Maven, parent POM, custom executions, profiles và lệnh gọi.

Các bước đọc mà không chạy package:

~~~bash
./mvnw help:active-profiles
./mvnw help:effective-pom -Dverbose=true
./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail=true
~~~

Sau đó tìm trong effective POM phần **spring-boot-maven-plugin**, mục **executions**, **goals**, **phase** (nếu được khai báo), parent/plugin management và các binding ngầm theo packaging. Nếu có execution repackage, xác định nó có thực sự được kích hoạt ở phase package trong phiên bản plugin đang dùng. Với Spring Boot starter parent đúng chuẩn, goal repackage đã được cấu hình sẵn khi khai báo plugin.

## 7. Phân biệt “xem giúp đỡ”, “dry-run” và “chạy thật”

| Lệnh | Đọc được gì? | Điều không được kết luận |
| --- | --- | --- |
| **./gradlew tasks --all** | Task nào tồn tại | Task nào chắc chắn sẽ chạy khi gọi build |
| **./gradlew help --task bootJar** | Mô tả/đường dẫn/tùy chọn của bootJar | Toàn bộ phụ thuộc bắc cầu của bootJar |
| **./gradlew bootJar --dry-run** | Task nào được Gradle chọn, thứ tự hiển thị dự kiến | Java đã compile, tests đã pass, JAR đã sinh |
| **./mvnw help:effective-pom** | POM sau kế thừa và active profiles | Một danh sách đầy đủ mọi goal theo thứ tự runtime |
| **./mvnw help:describe ...** | Goal có chức năng và tham số gì | Goal đó chắc chắn được gọi trong project |
| **./mvnw package** | Chạy thật lifecycle đến package | An toàn nếu chỉ muốn đọc kế hoạch |
| **./gradlew build** | Chạy thật các task theo graph và trạng thái | An toàn nếu chỉ muốn xem task graph |

**Lưu ý về tác động phụ:** “dry-run” của Gradle vô hiệu hóa **task actions**, nhưng trước đó Gradle vẫn cần khởi động, evaluate settings/build scripts, áp dụng plugin và dựng đồ thị. Nếu một build script hoặc plugin thực hiện I/O, network hoặc side effect ngay ở **configuration phase**, chỉ dùng **--dry-run** không ngăn được mọi side effect đó. Vì vậy không gọi đây là “chế độ sandbox tuyệt đối”.

Thêm nữa, dry-run có thể không phản ánh chính xác trạng thái **UP-TO-DATE**, **FROM-CACHE** hay test outcomes khi chạy thật. Các điều kiện hoặc task được tạo/điều chỉnh dựa trên môi trường và input có thể làm kế hoạch đổi khi các đầu vào ấy đổi.

## 8. Đọc đúng kế hoạch khi có nhiều module

### 8.1. Gradle multi-project

Giả sử settings có hai Gradle subproject **api** và **batch** (chỉ là tên ví dụ). Để xem kế hoạch đóng gói Boot JAR riêng cho **api**:

~~~bash
./gradlew :api:bootJar --dry-run
~~~

Để so sánh với build tổng:

~~~bash
./gradlew build --dry-run
~~~

Lệnh thứ hai có thể chọn nhiều project hoặc nhiều task hơn tùy cách Gradle resolve tên task và graph của root. Quan sát **đường dẫn task** trong output: **:api:compileJava** khác **:batch:compileJava** và khác **:compileJava** ở root. Không thể suy ra mọi subproject đều sẽ build chỉ từ chữ build.

Khi cần lọc một task:

~~~bash
./gradlew :api:build -x :api:test --dry-run
~~~

Đồ thị mới phản ánh test đã bị loại trừ khỏi lệnh này. **Không** dùng kết quả đó để kết luận pipeline không chạy test nếu pipeline thực tế không có **-x**. Bỏ test có thể làm mất kiểm tra chất lượng; lệnh chỉ phục vụ quan sát sự thay đổi kế hoạch.

### 8.2. Maven multi-module

Maven dựa vào reactor và tùy chọn chọn module. Ví dụ:

~~~bash
./mvnw -pl api help:effective-pom
./mvnw -pl api help:active-profiles
~~~

**-pl api** chọn project/module theo selector phù hợp của reactor. Muốn tra kế hoạch cho module còn phụ thuộc vào các project khác trong reactor, phải xét **-am** (also-make) khi gọi build thật. Trên thực tế, cách chính xác để giới hạn module còn phụ thuộc định danh module và cấu trúc pom.xml; kiểm tra bằng **./mvnw --help** và tài liệu Maven về reactor.

Với Maven multi-module, plan phải xét **lifecycle goals trong từng module**, packaging của từng POM, thứ tự reactor theo quan hệ dependency, plugin executions được kế thừa và active profiles. Không thể thay việc phân tích này bằng một dòng **--dry-run** chung.

## 9. Đọc log, xử lý khác biệt giữa kế hoạch và thực thi

### Dấu hiệu cần chú ý

| Hiện tượng | Giải thích khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Gradle dry-run có **:bootJar** nhưng lệnh thật không có JAR | Task bị disabled, lỗi task trước đó, cấu hình output hoặc task không thực thi thành công | Đọc log thật, task conditions và build/libs |
| Gradle output có **SKIPPED** cho mọi task dry-run | Đúng đặc tính của --dry-run | Không báo build/test PASS dựa vào nó |
| Gradle hiện thêm task từ plugin | Plugin thêm dependency vào graph | help --task, build.gradle, tài liệu plugin |
| Maven chạy **repackage** ngoài dự đoán | Parent POM hoặc execution bind goal vào package | help:effective-pom -Dverbose=true, goal descriptor |
| Maven không chạy repackage khi package | Chưa khai báo plugin/execution, đổi parent hoặc profile | POM hiệu lực, binding của goal |
| Maven thực thi goal ở phase khác dự đoán | Execution có phase hoặc default phase riêng; lifecycle/packaging khác | Plugin executions + lifecycle reference |
| CI có nhiều task/goal hơn laptop | Active profile/property, wrapper version, module selector, JDK khác | Ghi lại nguyên lệnh CI và so sánh cùng cờ |
| Gradle khởi động script/plugin và tải dữ liệu dù có --dry-run | Configuration phase vẫn chạy | Kiểm tra build script/plugin, cache và log |
| Lệnh có **-DdryRun=true** với Maven nhưng vẫn xóa/build | Property không phải global Maven dry-run | Tra tài liệu chính plugin có hỗ trợ dryRun không |

### Hai tình huống Spring Boot thường gặp

**Tình huống A: “Tôi chỉ muốn xem bootJar sẽ kéo theo bước nào.”**

Dùng:

~~~bash
./gradlew help --task bootJar
./gradlew bootJar --dry-run
~~~

Lệnh đầu xem task có tồn tại và mục đích của nó. Lệnh sau xem chuỗi task dự kiến. Nếu muốn chứng minh artifact thực sự có thể chạy, sau đó cần **chạy build thật và java -jar** trên môi trường phù hợp; dry-run không chứng minh điều đó.

**Tình huống B: “Vì sao mvn package tự chạy Spring Boot repackage?”**

Dùng:

~~~bash
./mvnw help:effective-pom -Dverbose=true
./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail=true
~~~

Tìm parent, plugin execution và binding với package. Nếu project kế thừa **spring-boot-starter-parent** và khai báo Spring Boot Maven Plugin, execution repackage thông thường đã được parent quản lý. Không có điều kiện nào buộc phải chạy **mvn package** chỉ để xem sơ bộ cấu hình này.

## 10. Cách làm thực tế để tránh đọc nhầm kế hoạch

Một quy trình ngắn, áp dụng được cả khi chưa biết cấu hình dự án:

**Bước 1 — Ghi nguyên lệnh đích.** Ví dụ **./gradlew clean bootJar --no-daemon** hoặc **./mvnw -Pci clean verify**. Các cờ, module selectors và active profiles là một phần của kế hoạch; bỏ chúng sẽ thay đổi kết quả.

**Bước 2 — Kiểm tra công cụ.** Xem **./gradlew --version** hoặc **./mvnw --version**. Đối chiếu tên task/goal với đúng phiên bản plugin; đừng áp dụng ví dụ từ một bản Gradle/Maven khác một cách máy móc.

**Bước 3 — Truy vấn bằng công cụ phù hợp.**
- Gradle: **tasks**, **help --task**, rồi **--dry-run** cho **chính lệnh đích**.
- Maven: **help:active-profiles**, **help:effective-pom**, **help:describe**, rồi kết hợp lifecycle/packaging bindings và plugin executions.

**Bước 4 — Giải thích quan hệ.** Khi thấy một task/goal “đến ngoài dự kiến”, xác định nó được gọi do command trực tiếp, dependency/binding, plugin, parent hay profile. Xem đúng module nếu là multi-module.

**Bước 5 — Ghi rõ giới hạn.** Đặt nhãn **“kế hoạch dự kiến”** cho output dry-run/cấu hình trợ giúp, không gọi đó là kết quả build/test. Những tác vụ nào ghi/xóa artifact hoặc tiếp xúc môi trường bên ngoài cần được xem xét trước khi chạy thật.

**Bước 6 — Xác minh khi cần.** Chạy bản dựng thực tế trong môi trường được phép và phù hợp; so sánh log thực, kết quả test và JAR/image tạo ra với những gì dự đoán. Kế hoạch cho biết “sẽ làm gì”, log và artifact cho biết “đã làm được gì”.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Bạn chạy **./gradlew bootJar --dry-run**, output có **:compileJava SKIPPED** và **:bootJar SKIPPED**. Kết luận nào đúng?

**Đáp án:** Compile và bootJar nằm trong kế hoạch, task actions bị bỏ qua. Không được kết luận code đã biên dịch, test đã pass hay JAR đã được tạo.

**Câu 2.** Bạn chạy **./mvnw help:effective-pom** và nhìn thấy Spring Boot Maven Plugin. Có chắc **mvn package** sẽ chạy repackage không?

**Đáp án:** Chưa chắc chỉ từ tên plugin. Cần kiểm tra goal **repackage** được bind trong executions/lifecycle (trong project dùng **spring-boot-starter-parent**, binding thường đã có), cùng packaging và profiles đang hoạt động.

**Câu 3.** Có thể dùng **./mvnw package -DdryRun=true** để bảo đảm Maven không xóa file hay chạy test không?

**Đáp án:** Không. **dryRun** không phải cờ chung của Maven lifecycle. Chỉ một goal có tham số như vậy mới diễn giải property đó theo quy định riêng; các goal khác vẫn có thể chạy.

**Câu 4.** Vì sao **./gradlew tasks --all** chưa trả lời đủ câu hỏi “./gradlew build sẽ chạy gì”?

**Đáp án:** Danh sách các task đã được khai báo không đồng nghĩa tập các task được chọn cho một lệnh. Cần **./gradlew build --dry-run** để xem đồ thị task được lập cho chính lệnh đó.

**Câu 5.** Dùng **--dry-run** của Gradle có bảo đảm tuyệt đối không có truy cập I/O hoặc side effect nào?

**Đáp án:** Không. Gradle vẫn evaluate configuration và plugin; script không đúng chuẩn có thể làm việc ngoài task actions trong giai đoạn cấu hình.

## 12. Ghi nhớ và tài liệu chính thức

- Với **Gradle**, đọc theo chuỗi **tasks → help --task → task --dry-run**. Xem output như **kế hoạch của task graph**, không phải kết quả build. Nếu phiên bản hỗ trợ **--task-graph**, có thể dùng để xem phụ thuộc rõ hơn.
- Với **Maven**, đọc theo chuỗi **lifecycle/packaging → active profiles → effective POM → plugin executions/goal help**. Maven không có dry-run chung của lifecycle giống Gradle.
- Khi phân tích **Spring Boot packaging**, kiểm tra **bootJar** của Gradle hoặc goal **repackage** của Maven, kèm cách plugin được áp dụng/bind trong dự án.
- Luôn phân biệt **bước dự kiến**, **bước thực sự chạy** và **artifact thật**.

### Tài liệu tham khảo chính thức

- Gradle — Command-Line Interface, phần Execution options và --dry-run: https://docs.gradle.org/current/userguide/command_line_interface.html
- Gradle — Understanding Tasks và nhiệm vụ trợ giúp: https://docs.gradle.org/current/userguide/more_about_tasks.html
- Gradle — Configuration Cache, dry-run ở giai đoạn cấu hình: https://docs.gradle.org/current/userguide/configuration_cache_adoption.html
- Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — Running Apache Maven: https://maven.apache.org/run.html
- Maven Help Plugin — Goals, effective POM và describe: https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html
- Maven Help Plugin — Effective POM: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Maven Help Plugin — Configuring describe: https://maven.apache.org/plugins/maven-help-plugin/examples/describe-configuration.html
- Spring Boot Maven Plugin — Using the Plugin: https://docs.spring.io/spring-boot/maven-plugin/using.html
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
