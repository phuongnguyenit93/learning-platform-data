# Chẩn đoán ClassNotFoundException, NoClassDefFoundError và NoSuchMethodError

## Mục tiêu và phạm vi

Một ứng dụng Spring Boot có thể **compile và chạy test thành công** nhưng vẫn lỗi ngay khi khởi động, khi Spring tạo bean, khi một request đi qua code ít dùng hoặc chỉ khi chạy bằng executable JAR/container. Ba lỗi thường bị gom chung thành “thiếu thư viện” là:

- `ClassNotFoundException` — một thao tác yêu cầu tìm class bằng tên chuỗi nhưng classloader không tìm được định nghĩa.
- `NoClassDefFoundError` — JVM/classloader cần định nghĩa class trong quá trình liên kết hoặc thực thi nhưng không tìm được class mà bytecode đang tham chiếu; đôi khi lỗi này xuất hiện sau khi khởi tạo class thất bại trước đó.
- `NoSuchMethodError` — class đã được tìm thấy nhưng phiên bản được nạp lúc runtime không có method mà caller đã được compile để gọi.

Cả ba đều liên quan tới class loading/linking, nhưng chúng chỉ ra **ba dạng sai lệch khác nhau**. Chọn đúng cách điều tra sẽ giúp tránh thêm dependency trùng, nâng version tùy tiện hoặc xóa cache mà không xử lý nguyên nhân.

Sau bài này, bạn có thể:

1. Phân biệt checked exception với linkage error và đọc đúng exception đầu tiên trong stack trace.
2. Giải thích compile classpath, runtime classpath, transitive dependencies, classloader và binary compatibility.
3. Tái hiện độc lập cả ba lỗi bằng Java 17+.
4. Dùng Gradle `dependencies`/`dependencyInsight` và Maven `dependency:tree` để tìm dependency thực sự được chọn.
5. Kiểm tra executable Spring Boot JAR, `BOOT-INF/classes`, `BOOT-INF/lib`, manifest và classpath order.
6. Xác định vấn đề do thiếu artifact, dependency scope, version skew, duplicate classes, reflection, ServiceLoader, static initializer hoặc classloader isolation.
7. Xác minh bản sửa bằng đúng artifact, JRE, command và container giống môi trường triển khai.
8. Thiết lập dependency alignment, lock/constraint, CI smoke test và quy trình phát hành tránh tái diễn.

**Bối cảnh:** Java 17+, Spring Boot 3.x (các ví dụ tương thích với dòng 3.3), Gradle 8.x hoặc Maven 3.x. Các lệnh giả định JDK 17 có `java`, `javac`, `jar`, `javap`, `jdeps`; thay đường dẫn và tên module theo project thực tế.

---

## 1. Bản đồ class loading và linking

### 1.1 Từ source đến runtime

Khi compile một ứng dụng, compiler cần tìm các class mà source tham chiếu. Khi chạy, JVM lại cần tìm class và method tương ứng từ **những file thực sự có trong runtime classpath/module path**.

```text
Java source
    |
    v
Compile classpath
  JDK + compile dependencies
    |
    v
.class bytecode
    |
    v
Package artifact
  plain JAR / Spring Boot executable JAR / WAR
    |
    v
Runtime classpath or module path
  application classes + runtime dependencies
    |
    v
ClassLoader: load -> link -> initialize
    |
    v
Method invocation / object creation / reflection
```

Build thành công chỉ chứng minh compiler đã nhìn thấy type cần thiết trong compile classpath. Nó **không chứng minh** dependency ấy được đưa vào runtime artifact, cũng không chứng minh runtime đang nạp đúng phiên bản.

Ví dụ: một project khai báo library ở `compileOnly`, compile code gọi library thành công nhưng executable JAR không mang library đó. Hoặc app được compile với API v2 nhưng container lại nạp API v1. Hai trường hợp tạo ra các lỗi khác nhau.

### 1.2 Ba giai đoạn dễ nhầm

- **Loading:** tìm bytecode và tạo đối tượng `Class` cho một tên class bằng classloader.
- **Linking:** verify bytecode, chuẩn bị dữ liệu runtime và resolve symbolic references tới class, field, method.
- **Initialization:** chạy static field initializers và static initializer block của class.

JVM có thể trì hoãn một số thao tác resolve tới lúc code cần dùng. Vì vậy ứng dụng có thể khởi động được rồi mới ném `NoClassDefFoundError` hoặc `NoSuchMethodError` ở một request cụ thể.

### 1.3 Classpath không phải danh sách dependencies trong build file

Build file có thể chứa:

- Direct dependency do team khai báo.
- Transitive dependency do thư viện khác kéo vào.
- Dependency chỉ dành cho compile.
- Dependency chỉ dành cho test.
- Dependency được cung cấp bởi container bên ngoài.
- Nhiều phiên bản hoặc nhiều artifact chứa cùng tên class.

Điều cần điều tra là **runtime graph đã resolve** và **artifact cuối cùng đã đóng gói**, không chỉ là dòng dependency trực tiếp trong source.

---

## 2. So sánh ba lỗi

| Lỗi | Bản chất | Thường xảy ra khi | Dấu hiệu đầu tiên cần xem |
| --- | --- | --- | --- |
| `ClassNotFoundException` | Checked exception, kế thừa `ReflectiveOperationException` | `Class.forName`, `ClassLoader.loadClass` hoặc cơ chế nạp class theo tên | Tên class được yêu cầu và classloader nào đang tìm |
| `NoClassDefFoundError` | `Error`, kế thừa `LinkageError` | JVM cần định nghĩa class khi tạo object/gọi code hoặc resolve reference | Class nào thiếu; message có phải “Could not initialize class” không |
| `NoSuchMethodError` | `Error`, kế thừa `IncompatibleClassChangeError` | Bytecode đã compile gọi method không có trong class runtime được nạp | Method signature, class thực tế được nạp và phiên bản JAR |

### 2.1 `ClassNotFoundException`

Java API mô tả exception này được ném khi ứng dụng yêu cầu tải class bằng **tên dạng String** thông qua `Class.forName`, `ClassLoader.findSystemClass` hoặc `ClassLoader.loadClass` nhưng không tìm thấy định nghĩa tương ứng.

Đây là checked exception. Code dùng reflection có thể bắt nó và xử lý như một trường hợp plugin không có mặt:

```java
try {
    Class<?> pluginType = Class.forName("com.example.plugins.CsvPlugin");
    System.out.println("loaded=" + pluginType.getName());
} catch (ClassNotFoundException ex) {
    System.err.println("Plugin class is unavailable: " + ex.getMessage());
}
```

Nguyên nhân phổ biến:

- Tên fully-qualified sai package, sai chữ hoa/chữ thường hoặc typo.
- Plugin JAR chưa được thêm vào classpath.
- Class có trong compile classpath nhưng không có trong runtime classpath.
- Code dùng nhầm classloader (ví dụ system classloader trong ứng dụng có nested JAR).
- Module/plugin được triển khai ở vị trí khác với vị trí loader đang tìm.
- Class được nạp từ config, database hoặc service registry nhưng giá trị tên class cũ.

### 2.2 `NoClassDefFoundError`

Đây là một `LinkageError`. JVM hoặc một classloader cần nạp định nghĩa class trong lúc thực hiện lời gọi method, tạo instance hoặc resolve một reference nhưng không tìm thấy class definition. Tình huống thường gặp là class đã có khi caller được compile, nhưng runtime không còn thấy nó.

Ví dụ message:

```text
java.lang.NoClassDefFoundError: com/vendor/payment/PaymentClient
```

Đừng chỉ tìm class được nêu ở dòng đầu. Một class có thể tồn tại nhưng **một dependency mà chính class đó cần** lại bị thiếu. Xem toàn bộ cause chain và stack trace để tìm nơi đầu tiên JVM cố nạp type.

Một trường hợp đặc biệt:

```text
java.lang.NoClassDefFoundError: Could not initialize class com.example.config.DatabaseSettings
```

Class có thể đã được tìm thấy nhưng lần khởi tạo trước đó thất bại trong static initializer. Lỗi đầu tiên thường là `ExceptionInInitializerError` với cause thực tế (ví dụ đọc config, thiếu environment variable, lỗi parse hoặc exception trong static block). JVM đánh dấu class đó không thể khởi tạo trong classloader hiện tại; lần dùng tiếp theo có thể báo `NoClassDefFoundError`. Hãy tìm **lỗi khởi tạo đầu tiên**, không chỉ sửa classpath.

### 2.3 `NoSuchMethodError`

Đây là `LinkageError` cho trường hợp caller yêu cầu gọi method nhưng class runtime không còn định nghĩa method phù hợp. Compiler thường đã bắt lỗi này nếu compile toàn bộ source với cùng một API. Nó xuất hiện lúc runtime khi **binary được compile với một phiên bản class khác** so với class được nạp.

Ví dụ:

```text
java.lang.NoSuchMethodError:
  'java.lang.String com.vendor.Client.execute(java.lang.String, int)'
```

Có thể caller được compile với `vendor-client 2.x`, nhưng runtime lại nạp `vendor-client 1.x` chưa có overload `execute(String, int)`. Hoặc dependency tree chọn một phiên bản transitive cũ, một shaded JAR chứa class cũ đứng trước class mới, hay ứng dụng deploy cùng một library version khác với version đã dùng ở CI.

Chữ ký method ở bytecode gồm tên và descriptor (kiểu tham số, kiểu trả về). Đổi tham số, đổi kiểu trả về hoặc xóa method có thể phá binary compatibility. Đổi static/instance cũng có thể gây một loại `IncompatibleClassChangeError` khác; không nên kết luận mọi mismatch đều phải là `NoSuchMethodError`.

### 2.4 Đừng nhầm với lỗi gần tên

| Lỗi | Ý nghĩa khác |
| --- | --- |
| `NoSuchMethodException` | Checked exception khi reflection tìm method theo API như `Class.getMethod`; không đồng nghĩa `NoSuchMethodError` |
| `NoSuchFieldError` | Bytecode tham chiếu field không còn trong class runtime |
| `IncompatibleClassChangeError` | Cấu trúc binary không tương thích, ví dụ thay đổi static/instance hoặc class/interface |
| `UnsupportedClassVersionError` | JVM quá cũ so với class file version |
| `ClassCastException` | Có thể do cùng tên class được nạp bởi hai classloader khác nhau; không nhất thiết là thiếu JAR |
| `ExceptionInInitializerError` | Lần khởi tạo static đầu tiên thất bại; có thể dẫn tới NCDFE ở lần dùng sau |

Không sửa sai loại lỗi. Ví dụ `--add-opens` thường liên quan quyền truy cập reflection trên JPMS; nó không tự bổ sung class còn thiếu hoặc method bị xóa.

---

## 3. Vì sao lỗi có thể chỉ xuất hiện lúc chạy?

### 3.1 Compile classpath và runtime classpath

Một thư viện có thể được khai báo cho compiler nhưng không được đóng gói khi chạy. Cần hiểu scope/configuration tương ứng:

| Gradle configuration | Compile app | Runtime app thông thường | Runtime test |
| --- | --- | --- | --- |
| `implementation` | Có | Có | Có |
| `api` (trong Java Library) | Có, đồng thời là API của component | Có | Có |
| `runtimeOnly` | Không cần cho compile source | Có | Có |
| `compileOnly` | Có | Không tự có | Không tự có |
| `testImplementation` | Chỉ test | Không | Có |
| `testRuntimeOnly` | Không | Không | Có |
| `developmentOnly` | Tùy plugin/config | Dành cho development, không mặc định là dependency production | Theo cấu hình build |

Với Maven, cần hiểu các scope `compile`, `runtime`, `provided` và `test`. Dependency `provided` thường được môi trường triển khai cung cấp; nếu chạy executable JAR độc lập mà dependency đó không được đóng gói, runtime có thể thiếu class.

**Ví dụ sai:** một ứng dụng import class từ thư viện nhưng khai báo Gradle `compileOnly` vì “compile không lỗi”. Nếu runtime không có container/platform cung cấp library đó, việc tạo object hoặc gọi method có thể ném `NoClassDefFoundError`.

### 3.2 Direct dependency không cho biết phiên bản cuối

Ứng dụng khai báo:

```groovy
dependencies {
    implementation 'org.example:client-api:2.4.0'
}
```

Nhưng một dependency khác có thể kéo phiên bản khác của module liên quan. Gradle và Maven có cơ chế version selection/mediation; phải đọc output resolve để biết bản được chọn và lý do chọn.

### 3.3 Test không luôn giống production

Các khác biệt thường gặp:

- Test classpath có `testImplementation`/`testRuntimeOnly` mà production không có.
- IDE thêm module hoặc library vào run configuration.
- Gradle `bootRun` chạy từ project classpath; production chạy executable JAR.
- Container cung cấp thư viện qua parent classloader nhưng local không có, hoặc ngược lại.
- Production dùng Java version, image, profile, launcher hoặc environment khác.
- Một method chỉ được gọi ở luồng hiếm (scheduled job, message consumer, error path) nên linkage chưa xảy ra khi startup.

Hãy kiểm tra **cùng artifact và cùng lệnh chạy** trước khi kết luận môi trường production “tự nhiên” lỗi.

---

## 4. Quy trình điều tra có thứ tự

### 4.1 Bắt đầu từ exception đầu tiên

1. Lưu nguyên stack trace đầy đủ, kể cả nested causes và dòng “Caused by”.
2. Xác định exception đầu tiên, class/method được nêu và frame đầu tiên thuộc code ứng dụng.
3. Ghi lại thời điểm: build, test, startup, tạo bean, request, background job hay shutdown.
4. Xác định command chạy thật: IDE, `bootRun`, `java -jar`, servlet container hay container image.
5. Ghi JDK/JRE version và artifact name/digest đang chạy.

Đừng chỉ copy dòng cuối của log hoặc chỉ tìm từ khóa trong message. Lỗi đầu tiên có thể giải thích vì sao những lần sau sinh thêm lỗi khác.

### 4.2 Lấy dependency graph của đúng configuration

- Với `NoClassDefFoundError`, tập trung `runtimeClasspath` (hoặc Maven runtime tree).
- Với lỗi chỉ xuất hiện ở test, kiểm tra `testRuntimeClasspath`.
- Với `NoSuchMethodError`, tìm đúng artifact chứa class được nêu và xem tất cả đường dependency đưa artifact đó vào.
- Nếu dùng Gradle plugin, tách `buildEnvironment` (plugin/buildscript classpath) khỏi runtime classpath của application.

### 4.3 Kiểm tra artifact cuối cùng

Xác minh:

- App class có trong archive.
- Library JAR có trong runtime package.
- Manifest có đúng launcher/start class.
- Artifact đang chạy là file vừa được build/publish, không phải bản cũ từ thư mục khác.
- Container image đang dùng đúng digest/tag.
- Không chạy nhầm plain JAR thay vì Spring Boot executable JAR.

### 4.4 Xác định classloader đã nạp class từ đâu

Khi nghi có duplicate JAR hoặc version cũ, hãy log class loading của đúng process. Tìm tên class và source/location được JVM báo. Nếu cùng class có ở nhiều artifact, xác định artifact nào thắng theo classpath order.

### 4.5 Chỉ sửa sau khi đã có bằng chứng

Một bản sửa tốt chỉ ra được:

- Class/method nào bị thiếu.
- Artifact nào đáng lẽ phải cung cấp nó.
- Runtime graph đã chọn artifact/version nào.
- Artifact hoặc classloader thực tế đang cung cấp class.
- Vì sao compile/test không phát hiện.
- Thay đổi tối thiểu và smoke test chứng minh lỗi đã hết.

---

## 5. Gradle: xem dependency tree và version selection

### 5.1 Xem runtime dependency graph

Trong project Gradle:

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
```

Để so sánh compile và test:

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
```

Tên project path `:app` chỉ là ví dụ. Với single-project build, bỏ prefix này. Các output thường đánh dấu conflict resolution, dependency constraint, dependency không resolve hoặc đường transitive.

### 5.2 Dùng `dependencyInsight` cho một module

Ví dụ tìm Spring Core:

```bash
./gradlew :app:dependencyInsight \
  --dependency spring-core \
  --configuration runtimeClasspath
```

Hoặc tìm Jackson:

```bash
./gradlew :app:dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

Lệnh này giúp trả lời:

- Module nào yêu cầu dependency?
- Có bao nhiêu đường transitive?
- Version nào được chọn?
- Vì sao version đó được chọn (conflict resolution, constraint, forced version, platform/BOM…)?

Đối với `NoSuchMethodError`, đây thường là bước quan trọng nhất: tìm class bị nêu trong lỗi, xác định artifact chứa class và kiểm tra version được chọn ở runtime.

### 5.3 Kiểm tra dependency trong buildscript/plugin riêng

Nếu lỗi xảy ra khi chạy plugin/task Gradle, kiểm tra:

```bash
./gradlew buildEnvironment
```

`buildEnvironment` hiển thị buildscript/plugin dependencies. Nó không thay thế `runtimeClasspath` của ứng dụng. Đừng dùng output này để kết luận ứng dụng Spring Boot đã đóng gói đủ thư viện.

### 5.4 Platform/BOM để đồng bộ phiên bản

Với Spring Boot, dùng dependency management do Boot plugin/parent/BOM cung cấp và tránh tự pin lẻ từng module Spring Framework hoặc Jackson sang các version không tương thích.

Ví dụ Gradle dùng platform:

```groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

Nếu project đã dùng Spring Boot Gradle plugin với dependency management thích hợp, không cần import BOM lặp lại chỉ vì thấy ví dụ này. Kiểm tra một nguồn quản lý version thống nhất.

### 5.5 Dependency constraints và locking

Khi cần bảo đảm dependency graph ổn định giữa CI và developer:

- Dùng dependency constraints/platform để định nghĩa version policy.
- Bật dependency locking cho các configuration cần reproducibility.
- Review lockfile khi nâng dependency.
- Chạy integration/smoke tests sau khi thay đổi graph.
- Không force một version chỉ để hết lỗi nếu version đó không tương thích với consumer khác.

Locking giữ lựa chọn dependency đã resolve ổn định; nó không tự sửa một bộ version sai. Cần xác định version tương thích trước khi ghi lock state.

---

## 6. Maven: dependency tree và effective POM

### 6.1 Xem dependency tree

Chạy từ thư mục module:

```bash
./mvnw dependency:tree
```

Tập trung runtime scope:

```bash
./mvnw dependency:tree -Dscope=runtime -Dverbose
```

Lọc một artifact cụ thể:

```bash
./mvnw dependency:tree \
  -Dincludes=org.springframework:spring-core
```

`dependency:tree` cho thấy dependency hierarchy mà Maven resolve. `-Dverbose` hữu ích khi cần thấy node bị omitted do conflict/version mediation.

### 6.2 Kiểm tra effective POM

```bash
./mvnw help:effective-pom
```

Dùng khi version được quản lý qua parent POM, `dependencyManagement`, profile hoặc imported BOM. File `pom.xml` tại module có thể không chứa version cuối trực tiếp; effective POM giúp xem cấu hình sau khi kế thừa và áp dụng profile.

### 6.3 Tạo runtime classpath để kiểm tra

```bash
./mvnw dependency:build-classpath \
  -DincludeScope=runtime \
  -Dmdep.outputFile=target/runtime-classpath.txt
```

Kiểm tra file output để xác định JAR nào có mặt. Đây là classpath của Maven project theo cấu hình plugin, không tự chứng minh executable Spring Boot JAR đã đóng gói đúng các file đó; vẫn phải kiểm tra artifact.

### 6.4 Maven dependency management

Khi nhiều module Spring Boot dùng cùng hệ sinh thái dependency, dùng Spring Boot parent hoặc import BOM đúng version. Tránh khai báo các module thuộc cùng release train ở các version riêng lẻ nếu không có lý do tương thích đã kiểm chứng.

Nếu tổ chức dùng Maven Enforcer, cân nhắc rule dependency convergence/ban duplicate classes theo policy. Rule convergence phát hiện một số version conflict; nó không thể chứng minh mọi class trong hai artifact khác tọa độ không bị trùng.

---

## 7. Spring Boot executable JAR: kiểm tra đúng package

### 7.1 Cấu trúc Boot JAR

Spring Boot executable JAR không phải JAR thường chỉ có application class. Nó dùng launcher và nested JAR layout:

```text
app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
└── BOOT-INF/
    ├── classes/
    │   └── com/example/Application.class
    ├── lib/
    │   ├── spring-core-....jar
    │   ├── spring-context-....jar
    │   └── dependency-....jar
    ├── classpath.idx
    └── layers.idx
```

Application classes nằm dưới `BOOT-INF/classes`; dependencies nằm trong các JAR lồng dưới `BOOT-INF/lib`. Spring Boot launcher thiết lập classloader để tải chúng.

### 7.2 `bootJar` và plain `jar`

Gradle Spring Boot plugin thường tạo:

- `bootJar`: executable archive có Boot loader và runtime dependencies lồng bên trong.
- `jar`: JAR Java thông thường; trong nhiều cấu hình plugin, file plain JAR được gắn classifier `plain`.

Nếu deploy nhầm `*-plain.jar` bằng `java -jar`, file đó có thể thiếu Boot loader và dependencies. Tên file không đủ để xác nhận; hãy inspect manifest và entries.

### 7.3 Kiểm tra archive

Liệt kê entries:

```bash
jar tf build/libs/app-1.0.0.jar
```

Lọc application classes và nested libraries trên Linux/macOS:

```bash
jar tf build/libs/app-1.0.0.jar | grep -E 'BOOT-INF/classes|BOOT-INF/lib'
```

PowerShell:

```powershell
jar tf build/libs/app-1.0.0.jar |
    Select-String 'BOOT-INF/classes|BOOT-INF/lib'
```

Kiểm tra manifest:

```bash
unzip -p build/libs/app-1.0.0.jar META-INF/MANIFEST.MF
```

Manifest của executable JAR cần launcher phù hợp trong `Main-Class` và application entry point trong `Start-Class`. Tên launcher cụ thể phụ thuộc Spring Boot version.

### 7.4 Không chạy Boot fat JAR bằng classpath thường

Lệnh:

```bash
java -jar build/libs/app-1.0.0.jar
```

để Boot launcher xử lý nested dependencies.

Lệnh:

```bash
java -cp build/libs/app-1.0.0.jar com.example.Application
```

không tự mở các JAR bên trong `BOOT-INF/lib` như classpath entries. Java classpath chuẩn không tự hiểu nested JAR. Dùng đúng launch mode cho artifact.

### 7.5 So sánh `bootRun` và `java -jar`

Nếu `bootRun` chạy nhưng executable JAR lỗi:

1. Kiểm tra task `bootJar` đã chạy và file output đúng.
2. Kiểm tra runtime dependencies trong `BOOT-INF/lib`.
3. Kiểm tra `compileOnly`, `runtimeOnly`, `developmentOnly` và exclusions.
4. Kiểm tra manifest và Boot loader.
5. Chạy chính file JAR bằng đúng Java version.
6. Nếu chỉ khác classpath order, kiểm tra `BOOT-INF/classpath.idx`.

Spring Boot classpath index (nếu có) được dùng khi chạy JAR/WAR qua `java -jar`; nó không được dùng khi chạy trong IDE hoặc qua `bootRun`. Vì vậy cùng source code có thể nạp một bản class khác nếu hai môi trường có classpath order khác nhau.

### 7.6 Kiểm tra dependency bị thiếu do scope

Trong ứng dụng Spring Boot, runtime dependency cần thiết phải thuộc runtime graph được đóng gói. Một dependency `compileOnly` không tự đi vào `BOOT-INF/lib`. Dependency `runtimeOnly` có thể được đóng gói dù source không import class của nó trực tiếp.

Với WAR deploy lên servlet container ngoài, `provided`/`providedRuntime` có thể là chủ đích. Khi chạy standalone, hãy hiểu môi trường nào chịu trách nhiệm cung cấp dependency đó.

---

## 8. Classloader và Spring Boot nested JAR

### 8.1 Parent delegation và class identity

Classloader không chỉ tìm file; nó còn xác định identity của class. Hai class có cùng tên fully-qualified nhưng được định nghĩa bởi hai classloader khác nhau là hai kiểu runtime khác nhau.

Điều này có thể dẫn đến `ClassCastException` kiểu:

```text
com.example.Plugin cannot be cast to com.example.Plugin
```

Nhìn tên giống hệt nhưng classloader khác nhau. Tình huống xuất hiện trong plugin systems, application servers, DevTools restart classloader hoặc thư viện được đóng gói trùng trong nhiều nơi.

### 8.2 Thread Context ClassLoader

Nhiều SPI/framework dùng Thread Context ClassLoader (TCCL) để tìm provider hoặc plugin. Trong Spring Boot executable JAR, dependencies được tải bởi Boot launcher classloader.

Spring Boot khuyến nghị dùng:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> plugin = Class.forName(
        "com.example.plugins.CsvPlugin",
        true,
        loader
);
```

Khi cần classloader rõ ràng, truyền loader phù hợp thay vì mặc định dùng `ClassLoader.getSystemClassLoader()`. Với nested JAR, system classloader không nhìn thấy nested dependency như một JAR thường trên system classpath.

### 8.3 `ServiceLoader`

Một ví dụ SPI:

```java
ServiceLoader<PaymentProvider> providers =
        ServiceLoader.load(PaymentProvider.class);
```

`ServiceLoader.load(service)` thường dựa vào TCCL để tìm provider. Kiểm tra:

- Provider class có trong runtime package không?
- File `META-INF/services/com.example.PaymentProvider` có trong artifact không?
- Nội dung file có đúng tên provider fully-qualified không?
- Nếu dùng shaded/uber JAR, các file service descriptor đã được merge chưa?
- Provider có thiếu transitive dependency không?

Lỗi SPI đôi khi được bọc trong `ServiceConfigurationError` với cause là CNFE, NCDFE hoặc exception khởi tạo. Đọc cause chain.

### 8.4 Spring Boot DevTools

DevTools restart dùng classloader riêng để reload code phát triển. Một class xuất hiện ở cả base classloader và restart classloader có thể gây duplicate identity hoặc lỗi cast/serialization. Nếu lỗi chỉ xảy ra khi DevTools bật:

- Thử chạy với DevTools tắt để xác nhận phạm vi.
- Kiểm tra thư viện nào đang nằm trong restart classloader.
- Cấu hình restart include/exclude theo hướng dẫn DevTools.
- Không đưa DevTools vào production artifact như dependency runtime bình thường.

Đừng dùng việc tắt DevTools làm “bản sửa” production nếu runtime package vẫn sai.

### 8.5 Nested JAR và thư viện cần file vật lý

Một số thư viện giả định dependency JAR tồn tại như file độc lập, có thể tự mở lại JAR hoặc dùng native integration. Nested JAR không phải lúc nào cũng là file path thông thường. Spring Boot hỗ trợ cấu hình `requiresUnpack` cho các dependency đặc biệt cần được unpack trước khi dùng. Chỉ cấu hình khi thư viện thực sự yêu cầu; đây không phải cách chữa chung cho CNFE.

---

## 9. Trường hợp đặc thù Spring Boot 3: javax và jakarta

Spring Boot 3 chuyển sang hệ sinh thái Jakarta EE cho nhiều API web/persistence. Ví dụ:

| API cũ | API mới |
| --- | --- |
| `javax.servlet.*` | `jakarta.servlet.*` |
| `javax.persistence.*` | `jakarta.persistence.*` |
| `javax.validation.*` | `jakarta.validation.*` |

Đây không phải quy tắc “mọi package `javax` đều bị xóa”: nhiều package Java SE như `javax.sql` vẫn thuộc JDK. Chỉ những API Java EE đã chuyển namespace mới cần được phân tích theo version.

Nếu một library cũ được compile với `javax.servlet.Servlet` nhưng app Spring Boot 3 chỉ cung cấp `jakarta.servlet.Servlet`, class cũ có thể ném CNFE/NCDFE khi nạp hoặc liên kết. Thêm cả hai API một cách tùy tiện có thể che dấu mismatch và tạo hệ thống khó dự đoán.

Cách xử lý:

1. Xác định class/method thực sự tham chiếu namespace nào bằng stack trace và `javap`.
2. Kiểm tra version library có hỗ trợ Jakarta/Spring Boot 3 không.
3. Nâng sang release tương thích hoặc dùng bridge/migration path được vendor hỗ trợ.
4. Không tự rename package trong bytecode hoặc thêm API cũ chỉ để qua bước startup.
5. Chạy integration test trên đúng Boot major version và runtime container.

---

## 10. Chẩn đoán `ClassNotFoundException`

### 10.1 Đọc tên class được yêu cầu

Message thường nêu fully-qualified class name. Kiểm tra:

- Tên có đúng package và chữ hoa/chữ thường không?
- Có dùng tên binary đúng cho nested class (dấu `$`) không?
- Class có thật trong JAR dự kiến không?
- JAR đó có trên runtime classpath của process đang lỗi không?
- Loader đang dùng có quyền nhìn thấy vị trí đó không?

Tên class trong reflection là tên binary, ví dụ `com.example.Outer$Inner`, không phải cú pháp source `com.example.Outer.Inner` trong mọi trường hợp.

### 10.2 Class tồn tại trong source nhưng không có trong artifact

Kiểm tra output compile:

```bash
find build/classes/java/main -type f
```

PowerShell:

```powershell
Get-ChildItem build/classes/java/main -Recurse -Filter *.class
```

Sau đó kiểm tra JAR:

```bash
jar tf build/libs/app.jar | grep 'BOOT-INF/classes/com/example'
```

Nếu class có trong `build/classes` nhưng không có trong executable JAR, kiểm tra source set, module packaging, custom `bootJar` configuration và task output.

### 10.3 Reflection dùng sai tên

Ví dụ:

```java
String className = "com.example.plugins.CsvPlugin";
Class<?> type = Class.forName(className);
```

Hãy kiểm tra nguồn cung cấp `className`: properties, database, environment, remote configuration hoặc plugin manifest. Nếu có profile-specific config, staging và production có thể đang chỉ tới hai tên class khác nhau.

### 10.4 Chọn classloader đúng

Nếu plugin nằm trong application classloader hoặc Boot nested JAR, dùng loader phù hợp:

```java
ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName(
        "com.example.plugins.CsvPlugin",
        false,
        contextLoader
);
```

Tham số `false` yêu cầu không initialize class ngay khi load. Điều này hữu ích khi cần tách lỗi “không tìm thấy class” khỏi lỗi static initializer. Khi thật sự cần khởi tạo, JVM sẽ initialize theo quy tắc thông thường.

### 10.5 Đừng che mất cause

Nếu CNFE được bọc trong một exception khác, log cause và classloader identity. Không chỉ log `ex.getMessage()` rồi bỏ stack trace; điều đó làm mất vị trí và cause quan trọng.

---

## 11. Chẩn đoán `NoClassDefFoundError`

### 11.1 Tìm đúng artifact cung cấp class

Ví dụ message:

```text
NoClassDefFoundError: org/apache/commons/lang3/StringUtils
```

Tìm artifact dự kiến chứa class này, kiểm tra dependency tree và xem artifact có nằm trong runtime package hay không. Với Spring Boot JAR, kiểm tra `BOOT-INF/lib`.

Không kết luận “thiếu commons-lang3” chỉ vì tên class giống artifact. Hãy xác minh class thật có trong JAR bằng `jar tf`.

### 11.2 Kiểm tra scope/exclusion

Các nguyên nhân thường gặp:

- Dependency được khai báo `compileOnly`.
- Maven dependency có scope `provided` nhưng standalone app không được cung cấp.
- Dependency bị `exclude` ở một module cha.
- Optional dependency không được consumer khai báo.
- Build script custom chỉ đóng gói một tập JAR thủ công và bỏ sót transitive dependency.
- Một runtime profile/conditional configuration nạp class chỉ ở production.

Khi một library có public API tham chiếu type của dependency, producer cần khai báo dependency contract phù hợp để consumer resolve được. Không dựa vào việc library “tình cờ” có JAR trên máy developer.

### 11.3 Phân biệt thiếu class với lỗi khởi tạo static

Nếu message là `Could not initialize class ...`:

1. Tìm log trước đó trong cùng process.
2. Tìm `ExceptionInInitializerError` đầu tiên.
3. Đọc cause (ví dụ `IllegalStateException`, `NullPointerException`, config missing, native library load failure).
4. Sửa nguyên nhân static initialization.
5. Restart process/classloader sau khi sửa; class đã bị đánh dấu erroneous trong loader hiện tại.

Ví dụ anti-pattern:

```java
public final class LegacyConfig {
    static {
        // Đọc file hoặc kết nối mạng ngay khi class được nạp.
        // Nếu thất bại, class có thể không initialize được.
    }
}
```

Không thực hiện network I/O, đọc secret hoặc khởi tạo hệ thống phức tạp trong static initializer nếu có thể chuyển sang lifecycle có kiểm soát (Spring bean initialization, factory hoặc explicit startup component).

### 11.4 Kiểm tra dependency của dependency

Một JAR có thể tồn tại nhưng một type mà nó cần lại không có. Ví dụ app tìm thấy `com.vendor.Client` nhưng khi JVM verify/link method của class đó, nó cần `com.vendor.internal.Transport` không được đóng gói.

Vì vậy, khi sửa NCDFE:

- Kiểm tra dependency tree đầy đủ, không chỉ direct dependency.
- Xem exclusions/optional scopes.
- Kiểm tra JAR thực có chứa class bị nêu.
- Kiểm tra classloader có nhìn thấy dependency transitive đó.
- Kiểm tra các class được load sau khi một static initializer thất bại.

### 11.5 Native library là trường hợp khác

Nếu class tồn tại nhưng method `native` không có native implementation, lỗi thường là `UnsatisfiedLinkError`. Kiểm tra OS/architecture, native library path và version ABI. Đừng nhầm nó với missing Java class.

---

## 12. Chẩn đoán `NoSuchMethodError`

### 12.1 Xác định method signature trong lỗi

Đọc đầy đủ:

- Class được gọi.
- Tên method.
- Kiểu tham số.
- Kiểu trả về nếu message/descriptor hiển thị.
- Caller frame đầu tiên trong stack trace.

Đừng chỉ so tên method trong source. Hai method cùng tên nhưng parameter/return descriptor khác nhau là hai binary methods khác nhau.

### 12.2 Caller và callee được compile từ hai phiên bản khác nhau

Tình huống kinh điển:

1. `orders-service` compile với `payment-client 2.0`.
2. Method `authorize(String, Duration)` có ở version 2.0.
3. Production runtime resolve `payment-client 1.5`.
4. Caller bytecode vẫn chứa reference tới method version 2.0.
5. JVM không tìm thấy method tương ứng và ném `NoSuchMethodError`.

Recompile riêng app mà dependency runtime vẫn là 1.5 không giải quyết được. Cần align version hoặc compile/test lại với đúng version được deploy.

### 12.3 Transitive version conflict

Một starter/framework có thể kéo version mới, trong khi một library khác kéo version cũ. Dùng `dependencyInsight`/`dependency:tree` để xem version được chọn và đường dẫn.

Với Spring ecosystem:

- Dùng Spring Boot BOM/parent để quản lý version của Spring modules.
- Hạn chế override riêng `spring-core`, `spring-beans`, `spring-context`, `spring-web`.
- Kiểm tra Jackson, Hibernate, logging và các integration libraries theo version matrix.
- Nâng một starter/library tương thích thay vì chỉ nâng một JAR con.
- Chạy integration test sau khi alignment.

### 12.4 Duplicate class trong nhiều artifact

Version resolution thường giải quyết xung đột của cùng một module coordinate. Nhưng hai artifact có GAV khác nhau vẫn có thể chứa cùng fully-qualified class. Khi đó dependency tree có thể không báo “version conflict” dù runtime có duplicate class.

Dùng class-load log để xem class được nạp từ JAR nào. Nếu một JAR shaded chứa bản copy của library, dependencyInsight có thể không cho thấy class trùng đó.

### 12.5 Method signature và binary compatibility

Các thay đổi API có thể làm binary cũ không tương thích:

- Xóa method hoặc constructor đã được caller compile sử dụng.
- Đổi kiểu tham số hoặc thêm/bớt tham số.
- Đổi kiểu trả về.
- Thay đổi generic erasure làm descriptor khác.
- Thay đổi class hierarchy khiến method lookup khác.
- Đổi static/instance có thể gây `IncompatibleClassChangeError`.

Khi publish library dùng bởi nhiều service, coi API và binary compatibility là hợp đồng. Dùng semantic versioning, compatibility tests hoặc API checks phù hợp với chính sách release.

### 12.6 Không ép version tùy tiện

`force` một module có thể làm hết lỗi ở một caller nhưng phá consumer khác đang cần API version mới. Hãy xác định version nào phù hợp với tất cả dependency paths, rồi dùng BOM/constraint/platform và test graph sau khi resolve.

---

## 13. Các lệnh chẩn đoán JVM và bytecode

### 13.1 Xem class được nạp từ đâu

Java 17 unified logging:

```bash
java -Xlog:class+load=info -jar build/libs/app.jar
```

Output có thể lớn. Lọc tên class trên Linux/macOS:

```bash
java -Xlog:class+load=info -jar build/libs/app.jar 2>&1 |
  grep 'com.vendor.Client'
```

PowerShell:

```powershell
java -Xlog:class+load=info -jar build/libs/app.jar 2>&1 |
    Select-String 'com.vendor.Client'
```

Dòng log cho biết class được load và source/location mà JVM ghi nhận. Đây là bằng chứng tốt khi nghi class cũ được nạp từ một JAR không mong đợi.

### 13.2 Xem method thật trong runtime JAR

`javap` đọc/disassemble class file:

```bash
javap -classpath path/to/vendor-client.jar \
  -p -s com.vendor.Client
```

- `-p` hiển thị cả member private.
- `-s` hiển thị internal type descriptor.
- `-c` hiển thị bytecode instructions.
- `-verbose` hiển thị thêm constant pool và thông tin class.

So sánh output của JAR compile-time với JAR runtime. Đảm bảo lệnh `javap` đang trỏ đúng file, không chỉ trỏ một classpath có nhiều phiên bản.

### 13.3 Xem dependency references tĩnh

```bash
jdeps --multi-release 17 -verbose:class \
  -classpath "lib-a.jar;lib-b.jar" \
  app.jar
```

Trên Linux/macOS, phân tách classpath bằng dấu `:`; trên Windows dùng dấu `;`. `jdeps` phân tích dependency ở mức package/class của bytecode. Với Spring Boot nested JAR, hãy chạy trên dependency JAR hoặc archive đã extract phù hợp; không coi kết quả `jdeps` trên outer executable JAR là bằng chứng đầy đủ về mọi nested dependency.

`jdeps` phân tích static references, không thay thế runtime test cho reflection, ServiceLoader, generated classes hoặc code chỉ được nạp theo tên chuỗi.

### 13.4 Kiểm tra Java runtime

```bash
java -version
javac -version
jar --version
```

Nếu build bằng JDK 21 nhưng production dùng Java 17, kiểm tra thêm `UnsupportedClassVersionError`. Đây là lỗi class file version khác với ba lỗi chính trong bài.

---

## 14. Bài lab 1: tái hiện ClassNotFoundException

Tạo file `Lookup.java`:

```java
public class Lookup {

    public static void main(String[] args) {
        String className = args.length == 0
                ? "demo.Plugin"
                : args[0];

        try {
            Class<?> type = Class.forName(className);
            System.out.println("LOADED=" + type.getName());
        } catch (ClassNotFoundException ex) {
            System.out.println("CLASS_NOT_FOUND=" + ex.getMessage());
        }
    }
}
```

Compile và chạy với tên class chưa tồn tại:

```bash
javac Lookup.java
java Lookup demo.Plugin
```

Stdout chính xác:

```text
CLASS_NOT_FOUND=demo.Plugin
```

Thêm class `demo.Plugin` vào classpath hoặc sửa tên class để chương trình load thành công. Thử truyền tên package sai để thấy lỗi đến từ lookup string, không phải dependency compiler.

**Kết luận:** `Class.forName` yêu cầu class theo tên và trả về checked exception khi loader không tìm thấy. Trong ứng dụng thật, kiểm tra cấu hình plugin, tên class và classloader đang được truyền.

---

## 15. Bài lab 2: tái hiện NoClassDefFoundError

Tạo hai source file:

`src/helper/demo/OptionalFeature.java`:

```java
package demo;

public final class OptionalFeature {

    private OptionalFeature() {
    }

    public static String value() {
        return "feature-present";
    }
}
```

`src/app/demo/UsesFeature.java`:

```java
package demo;

public class UsesFeature {

    public static void main(String[] args) {
        System.out.println(OptionalFeature.value());
    }
}
```

Compile helper trước, rồi compile application với helper class trên compile classpath:

```bash
javac -d helper-classes src/helper/demo/OptionalFeature.java
javac -cp helper-classes -d app-classes src/app/demo/UsesFeature.java
```

Chạy **chỉ** app classes, cố ý bỏ helper khỏi runtime classpath:

```bash
java -cp app-classes demo.UsesFeature
```

Kết quả là JVM ném `NoClassDefFoundError` cho `demo.OptionalFeature` (kèm cause tìm class không thành công). Đây là lỗi runtime: compile đã nhìn thấy class, nhưng runtime classpath không có nó.

Chạy lại với helper classes:

```bash
java -cp "app-classes:helper-classes" demo.UsesFeature
```

Stdout chính xác trên Linux/macOS:

```text
feature-present
```

Trên Windows, classpath separator là dấu chấm phẩy:

```powershell
java -cp "app-classes;helper-classes" demo.UsesFeature
```

**Liên hệ Spring Boot:** nếu class là dependency, đảm bảo dependency nằm trong runtime configuration và được đóng gói vào `BOOT-INF/lib`. Nếu class là application code, đảm bảo nó có trong `BOOT-INF/classes`.

---

## 16. Bài lab 3: tái hiện NoSuchMethodError do lệch version

### 16.1 Tạo library version 1

`src/lib-v1/demo/Greeter.java`:

```java
package demo;

public class Greeter {

    public String greet(String name) {
        return "Hello " + name;
    }
}
```

### 16.2 Tạo library version 2

`src/lib-v2/demo/Greeter.java`:

```java
package demo;

public class Greeter {

    public String greet(String name) {
        return "Hello " + name;
    }

    public String greet(String name, String prefix) {
        return prefix + " " + name;
    }
}
```

### 16.3 Caller compile với version 2

`src/app/demo/App.java`:

```java
package demo;

public class App {

    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("Linh", "Welcome"));
    }
}
```

Build hai JAR:

```bash
javac -d lib-v1-classes src/lib-v1/demo/Greeter.java
jar --create --file greeter-v1.jar -C lib-v1-classes .

javac -d lib-v2-classes src/lib-v2/demo/Greeter.java
jar --create --file greeter-v2.jar -C lib-v2-classes .
```

Compile caller với v2:

```bash
javac -cp greeter-v2.jar -d app-classes src/app/demo/App.java
```

### 16.4 Chạy caller với version 1

Linux/macOS:

```bash
java -cp "app-classes:greeter-v1.jar" demo.App
```

Windows:

```powershell
java -cp "app-classes;greeter-v1.jar" demo.App
```

JVM ném `NoSuchMethodError` cho `Greeter.greet(String, String)` vì bytecode của App đã compile với v2 nhưng runtime nạp v1.

Chạy với v2:

```bash
java -cp "app-classes:greeter-v2.jar" demo.App
```

Stdout chính xác:

```text
Welcome Linh
```

### 16.5 Quan sát bytecode

```bash
javap -classpath app-classes -c -p demo.App
javap -classpath greeter-v1.jar -p -s demo.Greeter
javap -classpath greeter-v2.jar -p -s demo.Greeter
```

So sánh method descriptor: v2 có overload được caller tham chiếu; v1 không có. Đây là bằng chứng binary mismatch, không phải thiếu class `Greeter`.

---

## 17. Spring Boot case study: chạy local được, production lỗi

Giả sử một service dùng thư viện `com.vendor:payment-client`. Developer chạy `bootRun` và test đều pass. Container production báo:

```text
java.lang.NoSuchMethodError:
  'com.vendor.Result com.vendor.PaymentClient.authorize(
      java.lang.String, java.time.Duration)'
```

Quy trình:

1. Ghi lại image digest và JAR thực tế trong image.
2. Chạy `java -version` trong đúng container runtime.
3. Chạy `./gradlew :app:dependencyInsight --dependency payment-client --configuration runtimeClasspath`.
4. Kiểm tra file `BOOT-INF/lib/payment-client-*.jar` trong executable JAR.
5. Dùng `javap -classpath` để kiểm tra method trong JAR runtime.
6. So sánh version và checksum của JAR được dùng lúc compile với JAR trong artifact.
7. Kiểm tra một starter/transitive library có đang kéo version cũ không.
8. Dùng BOM/constraint để chọn version tương thích, build lại image và chạy smoke test.
9. Promote đúng image digest đã kiểm thử.

Nếu lỗi chỉ xảy ra khi chạy `java -jar` nhưng không xảy ra qua `bootRun`, so sánh runtime graph và `BOOT-INF/classpath.idx`. Nếu class-load log cho thấy class được nạp từ một JAR ngoài dự kiến, điều tra classpath order/duplicate classes.

Một tình huống khác: production báo `NoClassDefFoundError: jakarta/servlet/Servlet`. Kiểm tra app có chạy embedded hay deploy WAR, servlet API có được cung cấp đúng môi trường không và dependency scope có loại nó khỏi executable package không. Nếu lỗi nhắc `javax.servlet.Servlet` trên Boot 3, kiểm tra library cũ chưa migrate sang Jakarta.

---

## 18. Ma trận triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân có khả năng | Bằng chứng nên lấy | Hướng sửa |
| --- | --- | --- | --- |
| CNFE từ `Class.forName` | Tên class sai hoặc loader không thấy plugin | Tên String, loader identity, runtime graph | Sửa FQCN/loader hoặc thêm plugin JAR |
| CNFE chỉ ở production | Runtime config/loader khác local | Config thực, class-load log | Đồng bộ config và classloader |
| NCDFE tên class thuộc dependency | Dependency không có trong runtime | Gradle/Maven runtime tree, archive entries | Đổi scope hoặc thêm dependency đúng |
| NCDFE tên class của app | Class không được package | `jar tf` và output classes | Sửa source set/packaging |
| NCDFE chỉ với plain JAR | Plain JAR thiếu Boot loader/nested dependencies | Manifest, `BOOT-INF/lib` | Deploy `bootJar`/executable WAR đúng |
| NCDFE “Could not initialize class” | Static initializer đã thất bại trước đó | ExceptionInInitializerError đầu tiên | Sửa cause, khởi động process/classloader mới |
| NCDFE của transitive type | Dependency của library bị thiếu | Dependency tree đầy đủ | Bổ sung dependency contract/runtime |
| NoSuchMethodError ở Spring class | Spring modules không cùng release train | dependencyInsight/tree, class-load source | Dùng Boot BOM/compatible versions |
| NoSuchMethodError của vendor SDK | Caller và runtime SDK lệch version | `javap` trên caller và runtime JAR | Align SDK version, rebuild và test |
| NoSuchMethodError chỉ trong container | Image chứa artifact/JAR cũ hoặc duplicate | Digest, archive contents, load log | Rebuild/pin artifact, bỏ duplicate |
| Lỗi chỉ khi plugin chạy | Classloader isolation/TCCL/SPI | Loader identity, service descriptor | Dùng loader phù hợp, sửa packaging SPI |
| ClassCastException cùng tên class | Hai classloader định nghĩa cùng class | `getClassLoader()` của hai object | Sửa classloader boundary/duplicate |
| `NoSuchMethodException` qua reflection | Method không có hoặc tìm sai visibility/signature | `getDeclaredMethods`/reflection config | Sửa reflection lookup, không xử lý như linkage |
| `UnsupportedClassVersionError` | Runtime JDK quá cũ | `java -version` và class file target | Dùng JRE phù hợp hoặc build target tương thích |

---

## 19. Checklist sửa lỗi và xác minh

### 19.1 Trước khi thay đổi dependency

- [ ] Đã lưu stack trace đầy đủ và xác định exception đầu tiên.
- [ ] Đã xác định đúng class/method trong message.
- [ ] Đã biết lỗi xảy ra ở compile, test, startup, request hay background task.
- [ ] Đã ghi JDK, runtime command, artifact name và image digest.
- [ ] Đã phân biệt runtime graph với compile/test graph.
- [ ] Đã xác định JAR thật sự cung cấp class/method.

### 19.2 Khi sửa

- [ ] Thay scope/exclusion/coordinate đúng nguyên nhân.
- [ ] Align các module thuộc cùng release train bằng BOM/platform.
- [ ] Loại duplicate class/JAR nếu có bằng chứng.
- [ ] Dùng Boot executable archive đúng task và đúng launch mode.
- [ ] Không nhúng dependency test/dev vào production.
- [ ] Không hardcode classpath thủ công nếu build tool đã quản lý graph.
- [ ] Không catch `Error` rồi tiếp tục chạy trong trạng thái classloader hỏng.
- [ ] Không xóa toàn bộ Gradle/Maven cache trước khi xác định version selection.

### 19.3 Sau khi sửa

- [ ] Chạy unit/integration tests.
- [ ] Sinh executable JAR/WAR từ build sạch.
- [ ] Inspect manifest và archive entries.
- [ ] Kiểm tra runtime dependency graph.
- [ ] Chạy đúng artifact bằng đúng Java command.
- [ ] Smoke test trong cùng container base image/runtime.
- [ ] Xác minh class-load source nếu từng có duplicate/version skew.
- [ ] Ghi image digest/artifact checksum và promote chính artifact đã test.
- [ ] Có rollback nếu dependency upgrade ảnh hưởng service khác.

---

## 20. Phòng ngừa trong build và release pipeline

### 20.1 Reproducible dependency graph

- Dùng Gradle Wrapper/Maven Wrapper đã được review.
- Pin plugin và dependency versions theo policy.
- Dùng BOM/platform cho hệ sinh thái có version alignment.
- Dùng dependency locking/verification khi cần reproducibility.
- Review thay đổi dependency tree trong pull request.
- Hạn chế dynamic versions và snapshot trong production.

### 20.2 Kiểm tra artifact thực tế

Một pipeline hữu ích:

```text
Resolve dependencies
      |
      v
Compile + unit tests
      |
      v
Integration tests
      |
      v
Build executable JAR/WAR
      |
      v
Inspect manifest + runtime libraries
      |
      v
Run java -jar smoke test
      |
      v
Build container from this artifact
      |
      v
Run container smoke test
      |
      v
Record digest + promote same image
```

Build/test source thôi chưa đủ. Smoke test nên chạy **đúng executable artifact** và **đúng container image** mà production sẽ sử dụng.

### 20.3 API/binary compatibility của library nội bộ

Nếu team publish Java libraries dùng chung:

- Không xóa/đổi method public đã được service khác compile sử dụng nếu không có major-version migration.
- Có API compatibility test hoặc binary compatibility checker.
- Phát hành version mới theo policy rõ ràng.
- Kiểm thử consumer sample với artifact vừa publish.
- Không publish lại binary khác dưới cùng release GAV.
- Ghi release notes về method/API thay đổi.

### 20.4 Observability và incident record

Khi sự cố xảy ra, lưu:

```text
Exception class + full message:
First cause:
First application frame:
Class or method named:
Runtime Java version:
Launch command:
Artifact filename + checksum:
Container image digest:
Gradle/Maven runtime dependency tree:
Resolved artifact version:
Class-load source:
Fix:
Regression test:
Verification environment:
```

Không ghi credentials, token hoặc secret trong log chẩn đoán. Nếu cần chia sẻ dependency tree hoặc image metadata, redaction thông tin nội bộ theo policy.

---

## 21. Bài thực hành tổng hợp

### A. Phân loại exception

Với mỗi tình huống, dự đoán lỗi và giải thích:

1. `Class.forName("com.example.Plugin")` nhưng plugin JAR không có trên classpath.
2. App compile với class `PaymentClient`, nhưng runtime JAR thiếu class này.
3. Caller compile với `Client.send(String, int)`, runtime version chỉ có `send(String)`.
4. Static initializer ném exception ở lần đầu, lần truy cập tiếp theo báo “Could not initialize class”.
5. Reflection gọi `getMethod` với signature không tồn tại.
6. Hai class cùng tên được nạp bởi hai classloader khác nhau rồi ép cast qua boundary.

### B. Gradle dependency diagnosis

1. Chạy `dependencies --configuration runtimeClasspath`.
2. Chạy `dependencyInsight` cho class/library xuất hiện trong stack trace.
3. So sánh compileClasspath và runtimeClasspath.
4. Tìm dependency path đưa version không mong muốn vào.
5. Sửa bằng platform/constraint/exclusion đúng nguyên nhân.
6. Chạy test và xem lại resolved graph.

### C. Maven dependency diagnosis

1. Chạy `dependency:tree -Dscope=runtime -Dverbose`.
2. Lọc artifact bằng `-Dincludes`.
3. Xem effective POM để tìm parent/BOM/profile.
4. Kiểm tra scope và dependency mediation.
5. Build executable artifact và xác minh library có trong package.
6. Chạy consumer/smoke test từ artifact mới.

### D. Spring Boot packaging

1. Build cả plain JAR và executable JAR.
2. Dùng `jar tf` để so sánh entries.
3. Kiểm tra `META-INF/MANIFEST.MF`.
4. Chạy executable JAR bằng `java -jar`.
5. Thử class-load logging để xác định source của một class.
6. Giải thích vì sao `java -cp app.jar` không tự load nested JAR.
7. So sánh `bootRun` với `java -jar` và giải thích vai trò classpath index.

### E. Binary compatibility lab

1. Hoàn thành lab version 1/version 2 ở phần 16.
2. Chạy caller với v1 và v2.
3. Dùng `javap -c -s` để xem bytecode/descriptor.
4. Sửa runtime JAR sang version tương thích.
5. Thêm regression test hoặc consumer compatibility check vào CI.
6. Giải thích vì sao chỉ compile lại application với cùng dependency cũ không giải quyết lỗi.

### F. Viết incident report

Dùng mẫu phần 20.4 để ghi lại một lỗi thật hoặc lỗi lab. Phải phân biệt **giả thuyết** với **bằng chứng đã thu được**. Không ghi “đã fix” khi mới thay version mà chưa chạy đúng executable artifact/container.

---

## 22. Tài liệu tham khảo chính thức

- Java SE 17 API — `ClassNotFoundException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html
- Java SE 17 API — `NoClassDefFoundError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html
- Java SE 17 API — `NoSuchMethodError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html
- Java SE 17 API — `LinkageError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html
- Java Language Specification — Chapter 13, Binary Compatibility: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html
- Oracle JDK 17 — `javap` command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Oracle JDK 17 — `jdeps` command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- Gradle User Manual — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle User Manual — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Apache Maven Dependency Plugin — `dependency:tree`: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Spring Boot — Nested JARs and executable JAR structure: https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html
- Spring Boot — Executable JAR restrictions and classloader guidance: https://docs.spring.io/spring-boot/specification/executable-jar/restrictions.html
- Spring Boot 3.3 — Efficient Deployments and unpacking executable JAR: https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html
- Spring Boot — Build and packaging how-to: https://docs.spring.io/spring-boot/how-to/build.html

**Ghi nhớ:** `ClassNotFoundException` thường là lookup theo tên String; `NoClassDefFoundError` cho biết JVM không tìm được định nghĩa class cần thiết hoặc class đã thất bại khi initialize; `NoSuchMethodError` thường chỉ ra binary/API version mismatch. Hãy điều tra **runtime dependency graph, artifact thực tế, classloader và method descriptor**, rồi xác minh bản sửa bằng đúng executable JAR và container sẽ chạy production.
