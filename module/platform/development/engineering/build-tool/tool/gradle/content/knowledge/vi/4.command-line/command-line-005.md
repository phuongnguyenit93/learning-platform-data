# Truyền project property bằng -P và JVM system property bằng -D trong Gradle

## 1. Mục tiêu bài học

Khi chạy Gradle từ terminal, đôi khi ta cần thay đổi môi trường build, bật một tùy chọn kiểm tra hoặc cấu hình JVM mà không sửa file build.gradle. Hai cờ thường gặp là **-P** và **-D**. Chúng có cú pháp gần giống nhau nhưng **đưa giá trị vào hai không gian cấu hình khác nhau**.

Sau bài này, bạn cần có khả năng:

- Truyền và đọc đúng **Gradle project property** bằng -P.
- Truyền và đọc đúng **Java system property của JVM chạy Gradle** bằng -D.
- Phân biệt giá trị được Gradle build script nhìn thấy với giá trị trong JVM chạy test hoặc ứng dụng.
- Dùng Provider API để có giá trị mặc định và đọc cấu hình theo cách phù hợp với cơ chế cấu hình của Gradle.
- Kiểm tra thứ tự ưu tiên, cú pháp trên Windows/macOS/Linux, và xử lý lỗi thường gặp.

Bài thuộc nhóm **Dòng lệnh** trong Build Tool Gradle. Trọng tâm là **cách truyền tham số và tác động của tham số**; không cần cài đặt thêm plugin ngoài Gradle để thử ví dụ chính.

## 2. Phân biệt -P và -D trước khi thực hành

| Tiêu chí | -P (project property) | -D (JVM system property) |
| --- | --- | --- |
| Vai trò | Cung cấp thuộc tính cấu hình của Gradle project/build | Thiết lập Java system property cho tiến trình Gradle |
| Cú pháp | -Pten=giaTri | -Dten=giaTri |
| Ví dụ | -PappEnv=staging | -Ddemo.trace=true |
| Cách đọc đề xuất trong build.gradle | providers.gradleProperty("appEnv") | providers.systemProperty("demo.trace") |
| API trực tiếp khác | project.findProperty("appEnv") | System.getProperty("demo.trace") |
| Nơi thường sử dụng | Chọn profile, biến thể build, cờ tác vụ, phiên bản xuất bản | Proxy/TLS, tùy chọn thư viện chạy trong Gradle JVM, cờ hệ thống |
| Có tự động truyền sang JVM test hoặc ứng dụng? | Không | Cũng không |

**Điểm cốt lõi:** -P không đặt Java system property cùng tên; -D không mặc nhiên tạo một Gradle project property cùng tên. Hai cờ không thể hoán đổi tùy ý.

Ngoại lệ có chủ đích là **-Dorg.gradle.project.ten=giaTri**: Gradle diễn giải tên system property theo quy ước đặc biệt này để thiết lập project property **ten**. Quy ước đó không làm thay đổi ý nghĩa của một -D thông thường.

Dùng **Gradle Wrapper** của dự án trong tất cả ví dụ, thay vì phụ thuộc vào phiên bản Gradle đã cài toàn cục.

## 3. Cú pháp chuẩn trên terminal

### 3.1. macOS hoặc Linux

~~~bash
./gradlew help -PappEnv=staging
./gradlew help -Ddemo.trace=true
./gradlew help -PappEnv=staging -Ddemo.trace=true
~~~

### 3.2. Windows PowerShell

~~~powershell
.\gradlew.bat help -PappEnv=staging
.\gradlew.bat help -Ddemo.trace=true
.\gradlew.bat help -PappEnv=staging -Ddemo.trace=true
~~~

Gradle chấp nhận các tùy chọn toàn cục trước hoặc sau tên task. Ví dụ, cả hai lệnh sau mang cùng ý nghĩa về hai giá trị được truyền:

~~~bash
./gradlew -PappEnv=staging -Ddemo.trace=true help
./gradlew help -PappEnv=staging -Ddemo.trace=true
~~~

Trong các ví dụ này, **help** là task Gradle có sẵn; nó không tự in appEnv hay demo.trace. Muốn quan sát giá trị, cần viết build logic đọc chúng hoặc dùng cách kiểm tra phù hợp ở phần sau.

**Truyền giá trị có khoảng trắng:** bao toàn bộ một đối số trong dấu nháy, để shell không tách giá trị thành nhiều đối số:

~~~bash
./gradlew help '-PdisplayName=Team Preview' '-Ddemo.label=Quality Check'
~~~

~~~powershell
.\gradlew.bat help '-PdisplayName=Team Preview' '-Ddemo.label=Quality Check'
~~~

Dấu nháy ở đây dành cho **shell**, không phải ký tự thuộc giá trị nhận được. Shell khác nhau có quy tắc escape ký tự đặc biệt khác nhau; nếu giá trị chứa dấu cách, $, &, dấu nháy hoặc dấu bằng, hãy kiểm tra quy tắc quoting của shell đang chạy. Tên property nên rõ nghĩa, nhất quán về chữ hoa/thường.

## 4. Ví dụ chạy được: quan sát hai loại property

Tạo một thư mục thử nghiệm Gradle có hai file văn bản:

**settings.gradle**

~~~groovy
rootProject.name = 'property-demo'
~~~

**build.gradle** — dùng Groovy DSL, tương thích với các phiên bản Gradle hiện đại:

~~~groovy
tasks.register('showInputs') {
    def appEnvValue = providers.gradleProperty('appEnv').orElse('dev')
    def traceValue = providers.systemProperty('demo.trace').orElse('false')

    inputs.property('appEnv', appEnvValue)
    inputs.property('demo.trace', traceValue)

    doLast {
        println 'appEnv=' + appEnvValue.get()
        println 'demo.trace=' + traceValue.get()
    }
}
~~~

Giải thích từng thành phần:

1. **providers.gradleProperty('appEnv')** yêu cầu Gradle cung cấp giá trị project property appEnv một cách lazy.
2. **providers.systemProperty('demo.trace')** lấy system property demo.trace từ môi trường build Gradle.
3. **orElse('dev')** và **orElse('false')** cung cấp giá trị mặc định nếu property không có.
4. **inputs.property(...)** khai báo hai giá trị là input của task, giúp Gradle biết tác vụ phụ thuộc vào cấu hình nào.
5. **doLast** chỉ thực hiện phần in khi task chạy; **get()** lấy giá trị cuối cùng từ Provider.

Không cần cài plugin Java hay viết file .java để chạy task ví dụ này. Giả sử thư mục thử nghiệm đã có Gradle Wrapper hợp lệ. Nếu tạo dự án từ đầu mà chưa có Wrapper, hãy tạo Wrapper bằng quy trình được hướng dẫn của Gradle trước khi chạy các lệnh sau.

### 4.1. Không truyền tham số

~~~bash
./gradlew showInputs
~~~

Hai dòng do task in ra:

~~~text
appEnv=dev
demo.trace=false
~~~

Gradle cũng sẽ in thông tin về task và trạng thái build, phụ thuộc phiên bản/cấu hình; phần trên chỉ là **hai dòng quan sát cần đối chiếu**, không phải toàn bộ stdout.

### 4.2. Chỉ truyền -P

~~~bash
./gradlew showInputs -PappEnv=staging
~~~

~~~text
appEnv=staging
demo.trace=false
~~~

Property appEnv nhận giá trị staging; system property demo.trace vẫn là mặc định.

### 4.3. Chỉ truyền -D

~~~bash
./gradlew showInputs -Ddemo.trace=true
~~~

~~~text
appEnv=dev
demo.trace=true
~~~

### 4.4. Truyền cả hai trong cùng một lệnh

~~~bash
./gradlew showInputs -PappEnv=production -Ddemo.trace=true
~~~

~~~text
appEnv=production
demo.trace=true
~~~

**Lệnh tương đương trong PowerShell:**

~~~powershell
.\gradlew.bat showInputs -PappEnv=production -Ddemo.trace=true
~~~

Lưu ý: các giá trị nhận được từ tham số dạng key=value là **chuỗi**. Văn bản 'true' không tự động là Boolean true trong build logic, và '42' không tự động là số nguyên 42. Nếu code cần kiểu Boolean/số, hãy chuyển kiểu rõ ràng và kiểm tra đầu vào.

## 5. Cách đọc project property (-P) trong Gradle

### 5.1. Ưu tiên Provider API

Trong build.gradle (Groovy DSL):

~~~groovy
def environment = providers.gradleProperty('appEnv').orElse('dev')
def buildNumber = providers.gradleProperty('buildNumber').orElse('0')

tasks.register('printProjectConfig') {
    doLast {
        println 'Environment: ' + environment.get()
        println 'Build number: ' + buildNumber.get()
    }
}
~~~

Chạy:

~~~bash
./gradlew printProjectConfig -PappEnv=qa -PbuildNumber=105
~~~

Hai dòng do task in ra:

~~~text
Environment: qa
Build number: 105
~~~

Có thể truyền nhiều -P với các tên khác nhau. Provider API giúp tách việc **khai báo nguồn giá trị** khỏi thời điểm thực sự sử dụng, phù hợp với mô hình Gradle hiện đại. Với dự án có Configuration Cache, ưu tiên Provider API thay vì đọc tùy tiện biến môi trường hoặc truy cập Project từ task action.

### 5.2. Các API cũ/dynamic và sự khác biệt

Một đoạn build script vẫn có thể dùng:

~~~groovy
def valueOrNull = project.findProperty('appEnv')
def isPresent = project.hasProperty('appEnv')
~~~

- **findProperty(name)** trả về null khi không tìm thấy.
- **hasProperty(name)** trả về true/false.
- **property(name)** ném MissingPropertyException nếu property không tồn tại.

Tuy nhiên, **providers.gradleProperty(name)** chỉ đọc các nguồn Gradle project property cấp build; nó không tự động đọc các extra property được gán động hoặc property đặt trong gradle.properties riêng của subproject. Trong khi đó, các API dynamic của Project có thể tìm nhiều loại phần tử của project model (extra properties, extension, task...). Vì vậy hai cách đọc có thể cho kết quả khác nhau nếu tên bị trùng hoặc được gán động.

**Khuyến nghị:** đối với cấu hình đến từ lệnh -P, biến môi trường hay gradle.properties, hãy ưu tiên providers.gradleProperty('ten') để diễn đạt rõ mục đích.

### 5.3. Xử lý giá trị Boolean và kiểm tra hợp lệ

Ví dụ một cờ bật/tắt được truyền bằng -Pfeature.enabled=true:

~~~groovy
def featureEnabled = providers.gradleProperty('feature.enabled')
    .map { value -> Boolean.parseBoolean(value) }
    .orElse(false)

tasks.register('showFeatureFlag') {
    doLast {
        println 'Feature enabled: ' + featureEnabled.get()
    }
}
~~~

~~~bash
./gradlew showFeatureFlag -Pfeature.enabled=true
~~~

~~~text
Feature enabled: true
~~~

**Không nên** dùng if (project.findProperty('feature.enabled')) để kiểm tra Boolean: chuỗi "false" vẫn là một giá trị có nội dung và có thể được Groovy coi là truthy. Hàm Boolean.parseBoolean chỉ trả true khi chuỗi tương đương "true" (không phân biệt hoa/thường); các chuỗi khác trả false. Nếu cấu hình quan trọng, hãy kiểm tra chặt chẽ hai giá trị cho phép "true"/"false" và báo lỗi khi nhập sai, thay vì im lặng coi mọi giá trị lạ là false.

## 6. Cách đọc JVM system property (-D)

### 6.1. Trong build script chạy bởi Gradle

~~~groovy
def traceProvider = providers.systemProperty('demo.trace').orElse('false')

tasks.register('showSystemConfig') {
    doLast {
        println 'Trace setting: ' + traceProvider.get()
    }
}
~~~

~~~bash
./gradlew showSystemConfig -Ddemo.trace=true
~~~

~~~text
Trace setting: true
~~~

Có thể kiểm tra trực tiếp bằng Java API thông thường:

~~~groovy
def directTrace = System.getProperty('demo.trace', 'false')
~~~

Nhưng với dữ liệu cấu hình dùng trong build logic, **providers.systemProperty(...)** thường là cách phù hợp hơn vì Gradle có thể theo dõi nguồn cấu hình và tính giá trị khi cần. System.getProperty đọc trực tiếp trạng thái của JVM hiện tại; nơi gọi và thời điểm gọi quyết định giá trị quan sát.

### 6.2. -D là của JVM nào?

Trong lệnh **./gradlew ... -Ddemo.trace=true**, cờ -D được Gradle CLI xử lý để thiết lập system property cho runtime Gradle. Điều này không đồng nghĩa mọi Java process mà Gradle khởi chạy sau đó đều có thuộc tính demo.trace.

Trong một build điển hình có thể có nhiều tiến trình JVM:

- JVM khởi chạy Wrapper/Gradle client.
- JVM chạy Gradle Daemon và thực hiện build logic.
- JVM chạy test của task Test, tách khỏi Daemon.
- JVM chạy ứng dụng qua JavaExec, application plugin, bootRun hoặc công cụ khác.

Việc một task **fork JVM con** tạo ra ranh giới tiến trình: JVM con **không mặc định thừa hưởng toàn bộ Java system properties của Gradle Daemon**. Phải truyền rõ những property mà task con cần bằng cấu hình phù hợp. Vì vậy câu “đã có -D rồi sao test không đọc được?” là lỗi hiểu nhầm rất thường gặp.

### 6.3. Truyền property đến JVM chạy test

Khi dự án dùng Java plugin và có task test:

~~~groovy
plugins {
    id 'java'
}

tasks.named('test', Test) {
    systemProperty(
        'demo.trace',
        providers.systemProperty('demo.trace').orElse('false').get()
    )
}
~~~

Chạy:

~~~bash
./gradlew test -Ddemo.trace=true
~~~

Trong mã test Java (ví dụ một đoạn trong phương thức @Test), giá trị có thể được đọc bằng:

~~~java
String trace = System.getProperty("demo.trace", "false");
System.out.println(trace);
~~~

Đoạn Java trên **chỉ là ví dụ mã nằm bên trong test**, không phải chương trình Java đầy đủ để biên dịch độc lập. Khi test thực sự được chạy và cấu hình Test ở trên có hiệu lực, biến trace nhận chuỗi "true". Dữ liệu in từ test có xuất hiện trên console Gradle hay không còn phụ thuộc test logging; không nên giả định mọi println từ test đều được hiển thị.

### 6.4. Truyền property đến ứng dụng chạy bằng JavaExec

Nếu dự án có task thuộc kiểu JavaExec, ví dụ task run của application plugin, cấu hình có thể là:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'example.Main'
}

tasks.named('run', JavaExec) {
    systemProperty(
        'demo.trace',
        providers.systemProperty('demo.trace').orElse('false').get()
    )
}
~~~

Đây là **mẫu build.gradle cho dự án đã có lớp example.Main** trên source set ứng dụng; cần có lớp main tương ứng mới chạy được. Khi gọi:

~~~bash
./gradlew run -Ddemo.trace=true
~~~

JVM chạy ứng dụng mới nhận được demo.trace theo cấu hình của JavaExec. Với Spring Boot, task bootRun cũng có cơ chế cấu hình JVM/system properties, nhưng cần xem loại task và cấu hình plugin thực tế thay vì giả định -D sẽ truyền qua tự động.

## 7. Những nguồn giá trị khác ngoài -P và -D

Hai cờ CLI là cách ghi đè linh hoạt trong một lần chạy. Gradle còn cho phép đặt cấu hình từ file hoặc biến môi trường.

### 7.1. Cấu hình trong gradle.properties

Ví dụ file gradle.properties tại **gốc build**:

~~~properties
appEnv=dev
buildNumber=0
systemProp.demo.trace=false
~~~

- **appEnv=dev** và **buildNumber=0** là các project property.
- **systemProp.demo.trace=false** khai báo Java system property demo.trace cho runtime Gradle.
- **Không có tiền tố systemProp.**, một dòng tên tùy ý trong file gradle.properties được dùng làm Gradle project property, chứ không tự thành Java system property.

Một lệnh CLI có thể ghi đè các giá trị:

~~~bash
./gradlew showInputs -PappEnv=staging -Ddemo.trace=true
~~~

Lúc này showInputs trong phần 4 sẽ in appEnv=staging và demo.trace=true, mặc dù file mặc định đặt dev/false.

Trong multi-project build, **systemProp.** ở file gradle.properties của subproject không được Gradle áp dụng theo cách tương tự root; đặt các systemProp cần dùng ở root hoặc cấu hình cấp người dùng theo quy tắc của Gradle.

### 7.2. Truyền project property bằng -D với tiền tố đặc biệt

Gradle nhận diện quy ước:

~~~bash
./gradlew showInputs -Dorg.gradle.project.appEnv=qa
~~~

Ở đây project property appEnv có giá trị **qa**, dù không dùng -P. Đây là trường hợp có chủ đích được Gradle hỗ trợ.

So sánh ba lệnh:

~~~bash
./gradlew showInputs -DappEnv=qa
./gradlew showInputs -Dorg.gradle.project.appEnv=qa
./gradlew showInputs -PappEnv=qa
~~~

- Lệnh thứ nhất đặt **system property appEnv**; task showInputs không đọc system property này, nên appEnv của task vẫn lấy từ project property hoặc mặc định.
- Lệnh thứ hai thiết lập **project property appEnv** thông qua quy ước org.gradle.project.
- Lệnh thứ ba thiết lập **project property appEnv** trực tiếp bằng -P; đây là cách rõ ràng nhất khi chỉ muốn truyền project property.

### 7.3. Truyền project property từ biến môi trường

Tên biến dạng **ORG_GRADLE_PROJECT_appEnv** là một cách cung cấp project property appEnv.

macOS/Linux:

~~~bash
ORG_GRADLE_PROJECT_appEnv=staging ./gradlew showInputs
~~~

PowerShell:

~~~powershell
$env:ORG_GRADLE_PROJECT_appEnv = 'staging'
.\gradlew.bat showInputs
~~~

Lệnh PowerShell đầu tiên thay đổi biến môi trường trong phiên terminal hiện tại; muốn hủy giá trị thử nghiệm sau đó, có thể dùng Remove-Item Env:ORG_GRADLE_PROJECT_appEnv.

Cách đưa cấu hình từ biến môi trường hữu ích trong CI vì có thể cung cấp giá trị ở thời điểm chạy mà không cần sửa file trong repository. Dù vậy, vẫn phải sử dụng cơ chế quản lý bí mật của CI đối với dữ liệu nhạy cảm, tránh cố tình in chúng vào log.

### 7.4. Thứ tự ưu tiên của project property

Đối với project property lấy từ các nguồn chuẩn của môi trường build, Gradle ưu tiên thông thường như sau (**cao → thấp**):

1. **-Pten=giaTri** trên CLI.
2. **-Dorg.gradle.project.ten=giaTri** trên CLI hoặc system property tương ứng.
3. **ORG_GRADLE_PROJECT_ten** trong environment.
4. **gradle.properties** trong Gradle User Home, rồi build root, rồi Gradle installation (theo thứ tự áp dụng của Gradle).

Ví dụ:

~~~properties
# gradle.properties ở build root
appEnv=dev
~~~

Nếu đồng thời thiết lập ORG_GRADLE_PROJECT_appEnv=qa và chạy lệnh có -PappEnv=staging, giá trị mà providers.gradleProperty('appEnv') nhận được là **staging**. Nếu bỏ -P nhưng giữ biến môi trường, kết quả là **qa**.

Đây là thứ tự cho **nguồn project property từ môi trường build**. Một extra property hoặc thuộc tính project model được code gán trực tiếp có quy tắc phân giải riêng; không nên sử dụng tên trùng nhau cho nhiều loại dữ liệu.

### 7.5. Thứ tự ưu tiên của JVM system property

Với một Java system property thông thường trong môi trường Gradle, cách chỉ định rõ trực tiếp bằng **-Ddemo.trace=true** có ưu tiên hơn giá trị **systemProp.demo.trace=false** từ gradle.properties. Khi không truyền -D, giá trị trong file có thể được áp dụng.

Không nhầm **-Ddemo.trace=true** với **-Dorg.gradle.jvmargs=...** hoặc **-Dorg.gradle.java.home=...**: các tên org.gradle.* là cấu hình đặc thù của Gradle cho quá trình build/Daemon; hãy tra tài liệu nếu cần điều chỉnh JVM flags hoặc đường dẫn JDK.

## 8. Ví dụ tình huống thực tế

### 8.1. Chọn môi trường phát hành bằng -P

Build script có thể dùng project property appEnv để chọn hành vi một task phát hành:

~~~groovy
def appEnv = providers.gradleProperty('appEnv').orElse('dev')

tasks.register('showPublishTarget') {
    doLast {
        def target = appEnv.get()
        if (!(target in ['dev', 'staging', 'production'])) {
            throw new GradleException('Unsupported appEnv: ' + target)
        }
        println 'Target environment: ' + target
    }
}
~~~

~~~bash
./gradlew showPublishTarget -PappEnv=staging
~~~

~~~text
Target environment: staging
~~~

Đây chỉ là task **minh họa kiểm tra cấu hình**; nó không phát hành artifact. Trong một build thật, tác vụ publish/deploy cần được thiết kế riêng và nên xác minh môi trường trước khi thực hiện thao tác có tác dụng bên ngoài. Tránh dùng -D cho cấu hình được dự định là project property.

### 8.2. Bật chẩn đoán cho code chạy trong Gradle

Một plugin hoặc build script đọc Java system property **demo.trace** có thể nhận giá trị qua:

~~~bash
./gradlew help -Ddemo.trace=true
~~~

Điều kiện là code cần chẩn đoán thật sự đọc property có tên đó trong **Gradle JVM**. Không phải bất kỳ -Ddemo.trace nào cũng làm Gradle tự in thêm log. Nếu cần log chẩn đoán tích hợp của Gradle, các cờ **--info**, **--debug** hoặc **--stacktrace** phục vụ mục đích khác và có hành vi riêng:

~~~bash
./gradlew help --info
./gradlew help --stacktrace
~~~

### 8.3. Dùng kết hợp -P và -D trong một build

Một pipeline có thể chọn profile và bật chẩn đoán đồng thời:

~~~bash
./gradlew test -PappEnv=ci -Ddemo.trace=true
~~~

- **appEnv=ci** là project property dùng trong build.
- **demo.trace=true** là system property trong Gradle runtime.
- Nếu test JVM cũng cần demo.trace, **cần có cấu hình forwarding cho Test**, như phần 6.3; chính lệnh trên không tự chứng minh test đã nhận giá trị.

## 9. Lỗi phổ biến và cách tự kiểm tra

| Triệu chứng | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| Đã truyền -DappEnv=qa mà providers.gradleProperty('appEnv') không đổi | -DappEnv là JVM system property, không phải project property | Dùng -PappEnv=qa hoặc quy ước -Dorg.gradle.project.appEnv=qa |
| Đã truyền -Pdemo.trace=true mà System.getProperty('demo.trace') là null | -P chỉ tạo project property | Dùng -Ddemo.trace=true nếu build logic cần Java system property |
| Truyền -D vào Gradle nhưng test thấy null | Test chạy trong JVM riêng | Cấu hình systemProperty của task Test |
| Giá trị 'false' lại bị xử lý như đã bật | Code kiểm tra chuỗi không rỗng thay vì chuyển Boolean | Dùng Boolean.parseBoolean và xác thực giá trị hợp lệ |
| Gõ -PappEnv=Team Preview bị tách đối số | Chưa quote giá trị chứa dấu cách | Quote toàn bộ đối số: '-PappEnv=Team Preview' |
| Build dùng giá trị khác file gradle.properties | Có nguồn ưu tiên cao hơn như -P hoặc environment | Kiểm tra các nguồn theo thứ tự ưu tiên |
| IDE/CI đọc khác terminal | JVM, môi trường hoặc tham số gọi Gradle không giống nhau | Đối chiếu lệnh gọi, Gradle Wrapper, biến môi trường và cấu hình IDE/CI |
| Cờ -D không làm ứng dụng chạy qua JavaExec đổi giá trị | JVM ứng dụng được fork riêng | Forward vào JavaExec hoặc task tương ứng |

### Checklist chẩn đoán theo thứ tự

1. Ghi lại **lệnh Gradle Wrapper đầy đủ** và shell đang chạy.
2. Kiểm tra tên property có đúng chính tả và đúng chữ hoa/thường không.
3. Xác định code đọc **project property** hay **Java system property**.
4. Chạy task showInputs trong mục 4 để xác nhận cơ chế đọc, không thay đổi mã ứng dụng.
5. Kiểm tra các nguồn khác: gradle.properties, ORG_GRADLE_PROJECT_* và -Dorg.gradle.project.*.
6. Nếu lỗi ở test/ứng dụng, kiểm tra tiến trình JVM thực sự sử dụng property và cấu hình chuyển tiếp.
7. Không đưa password, token, khóa truy cập hay thông tin nhạy cảm vào log hoặc chụp màn hình chẩn đoán.

## 10. Lưu ý về dữ liệu nhạy cảm và tính lặp lại của build

**Không nên đặt secret trực tiếp trong lệnh -P/-D** vì lịch sử shell, process listing hoặc log CI có thể lưu tham số command line. Với pipeline, dùng hệ thống secret của CI và truyền theo cơ chế được dự án duyệt; khi Gradle nhận qua biến môi trường như ORG_GRADLE_PROJECT_*, vẫn phải tránh log giá trị. Không mặc định coi biến môi trường là an toàn tuyệt đối.

Chọn tên property cụ thể theo chức năng (appEnv, buildNumber, demo.trace), có giá trị mặc định hợp lý và xác thực các giá trị quan trọng. Với task có đầu ra phụ thuộc vào property, hãy khai báo property là **task input** (như ví dụ showInputs). Nếu không khai báo đầy đủ các đầu vào, kiểm tra incremental build/up-to-date hoặc caching có thể đánh giá sai việc đầu ra cần được tính lại.

Khi cần xác định build có tái lập được giữa máy cá nhân và CI, hãy lưu lại **phiên bản Gradle Wrapper**, bộ tham số -P/-D có ý nghĩa, nguồn biến môi trường cần thiết, và phiên bản Java/Gradle; đừng chỉ ghi tên task.

## 11. Tóm tắt bằng một quy tắc chọn cờ

- **Cần đưa cấu hình vào build/project?** Dùng **-Pten=giaTri**, đọc bằng **providers.gradleProperty('ten')**.
- **Cần đặt Java system property cho runtime Gradle?** Dùng **-Dten=giaTri**, đọc bằng **providers.systemProperty('ten')**.
- **Muốn dùng -D nhưng tạo project property?** Chỉ khi chủ động dùng quy ước **-Dorg.gradle.project.ten=giaTri**.
- **Cần property trong JVM test/ứng dụng?** Cấu hình task **Test/JavaExec/bootRun** để truyền sang tiến trình tương ứng.

Ví dụ ghép cả hai:

~~~bash
./gradlew showInputs -PappEnv=staging -Ddemo.trace=true
~~~

Hai dòng kết quả của task minh họa:

~~~text
appEnv=staging
demo.trace=true
~~~

## 12. Tài liệu chính thức

1. Gradle – Build Environment Configuration (project properties, system properties, precedence): https://docs.gradle.org/current/userguide/build_environment.html
2. Gradle – Command-Line Interface (cú pháp -P, -D và các cờ chạy task): https://docs.gradle.org/current/userguide/command_line_interface.html
3. Gradle – Testing in Java & JVM Projects (JVM riêng của task Test): https://docs.gradle.org/current/userguide/java_testing.html
4. Gradle – Test task API, systemProperty: https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/Test.html
5. Gradle – Build Cache/Task Inputs: https://docs.gradle.org/current/userguide/incremental_build.html

Tài liệu tại đường dẫn current có thể thay đổi theo phiên bản Gradle mới nhất. Khi một dự án dùng Wrapper cũ, nên tra thêm tài liệu đúng phiên bản đó để xác nhận hành vi cụ thể.