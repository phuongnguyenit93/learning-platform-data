# Giải quyết xung đột phiên bản và lớp trùng trên class path

Trong quá trình **Java Advance Compatibility Migration**, một ứng dụng có thể biên dịch thành công trên JDK mới nhưng gặp `NoSuchMethodError`, `NoClassDefFoundError`, `ClassCastException` hoặc lỗi khởi động framework khi chạy. Một nguyên nhân phổ biến là **dependency graph không nhất quán**: nhiều thành phần yêu cầu các phiên bản khác nhau của cùng thư viện, hoặc nhiều JAR cùng đóng gói một class với cùng tên đầy đủ (*fully qualified class name*, FQCN).

Ví dụ, ứng dụng dùng API của `example-util` phiên bản 2 khi compile nhưng classpath production lại nạp `example-util` phiên bản 1. Bytecode đã ghi tham chiếu tới một method mới không tồn tại trong class phiên bản 1; kết quả là lỗi linkage ở runtime. Một tình huống khác: hai thư viện độc lập cùng chứa `com.example.common.JsonHelper`; khi JVM chọn một bản để nạp, code của bên còn lại có thể nhận hành vi khác mong đợi.

**Xung đột phiên bản** và **lớp trùng trên class path** có liên quan nhưng không đồng nhất. Không phải cứ có nhiều đường phụ thuộc tới cùng thư viện là runtime luôn có hai bản JAR; Maven và Gradle có cơ chế chọn phiên bản. Ngược lại, cùng một class có thể được đóng gói trong hai artifact mang tọa độ khác nhau nên công cụ giải quyết version conflict bình thường không phát hiện ra.

Bài học giải thích cơ chế hình thành xung đột, cách JVM nạp lớp, cách khảo sát Maven/Gradle, kỹ thuật loại trừ dependency, quản lý phiên bản tập trung, shading/relocation và quy trình migration an toàn.

## 1. Những khái niệm nền tảng

### 1.1. Direct và transitive dependency

**Direct dependency** là thư viện ứng dụng khai báo trực tiếp. **Transitive dependency** là thư viện được kéo theo bởi một dependency khác.

Ví dụ:

```text
checkout-app
├── payment-sdk:2.0
│   └── common-utils:2.5
└── report-sdk:1.8
    └── common-utils:1.9
```

Hai nhánh yêu cầu `common-utils` ở hai phiên bản khác nhau. Build tool cần quyết định phiên bản nào được chọn cho một configuration hoặc dependency graph.

Sự khác nhau cần nhớ:

- **Declared version:** phiên bản được ghi trong POM, build script hoặc metadata.
- **Requested version:** phiên bản/constraint mà một nhánh dependency yêu cầu.
- **Resolved version:** phiên bản thực sự được chọn sau quá trình giải quyết.
- **Packaged version:** phiên bản thật sự được đưa vào WAR, executable JAR, container hoặc thư mục `lib`.
- **Loaded class:** class mà một classloader thực sự định nghĩa hoặc tìm được khi ứng dụng chạy.

Năm giá trị này có thể khác nhau, nhất là khi có BOM, dependency management, plugin packaging hoặc application server.

### 1.2. Classpath là gì?

Classpath là tập vị trí chứa class và resource mà classloader có thể tìm kiếm, thường gồm thư mục class và JAR:

```bash
java -cp "app.jar:lib/*" com.example.Main
```

Trên Windows, dấu phân tách path thường là `;`:

```powershell
java -cp "app.jar;lib/*" com.example.Main
```

Trong môi trường dùng launcher, ứng dụng server hoặc framework boot loader, classpath thực tế có thể được tạo động; không nhất thiết trùng dòng lệnh mà developer tự xây dựng.

### 1.3. Hai JAR chứa một tên lớp giống nhau

Giả sử:

```text
lib/legacy-utils.jar
  com/example/common/JsonHelper.class

lib/modern-utils.jar
  com/example/common/JsonHelper.class
```

Hai class có **cùng binary name** `com.example.common.JsonHelper`. Trong phạm vi cùng một classloader, classloader sẽ nạp/định nghĩa một phiên bản phù hợp theo quy tắc tìm kiếm của nó; JVM không tự hợp nhất method và field từ cả hai class file.

Điều này khác với việc có hai class cùng tên được nạp bởi **hai classloader khác nhau**: tại runtime, định danh kiểu Java liên quan cả tên lớp và classloader định nghĩa. Vì thế, hai class cùng FQCN nhưng khác defining classloader có thể là hai kiểu không tương thích.

### 1.4. Version conflict khác duplicate class

| Vấn đề | Dấu hiệu | Điểm điều tra chính |
|---|---|---|
| Version conflict | Nhiều nhánh yêu cầu các phiên bản khác nhau của cùng module/library | Dependency resolution và phiên bản được chọn |
| Duplicate class | Nhiều artifact thực sự chứa cùng FQCN | Nội dung JAR và classloader search path |
| Missing dependency | Class không có trong runtime | Dependency scope, packaging, module/class path |
| Binary incompatibility | Method/field descriptor ở runtime khác lúc compile | Phiên bản compile/runtime và ABI |
| Classloader conflict | Cùng tên class được định nghĩa bởi loader khác nhau | Loader hierarchy và isolation policy |
| JPMS split package | Package trùng giữa các named modules | Module graph, package ownership |

Một dự án có thể gặp nhiều vấn đề cùng lúc. Cần chọn cách sửa theo nguyên nhân thật, không chỉ theo exception xuất hiện đầu tiên.

## 2. Tại sao nâng JDK thường làm lộ xung đột sẵn có?

Xung đột dependency đôi khi đã tồn tại trước migration nhưng chỉ gây lỗi khi thay đổi một điều kiện:

1. **Nâng framework:** framework mới yêu cầu version thư viện cao hơn, trong khi SDK cũ kéo về version thấp.
2. **Đổi build tool hoặc plugin:** quy tắc resolution, variant selection và packaging thay đổi.
3. **Thay JDK:** thư viện cũ sử dụng API nội bộ bị encapsulate hoặc bytecode không tương thích.
4. **Chuyển sang container:** classpath đã khác application server cũ, mất những thư viện trước đây được server cung cấp.
5. **Đổi executable packaging:** plugin shade/repackage sao chép class theo cơ chế khác.
6. **Đổi classloader:** servlet container, plugin platform hoặc module layer có thứ tự nạp khác.
7. **Nâng dependency trong một module:** các module còn lại không đồng bộ API và phiên bản phát hành.
8. **Bật dependency locking/verification:** lần đầu phát hiện artifact trước đây được resolve không nhất quán.

Ví dụ: ứng dụng biên dịch bằng JDK 17, sử dụng framework mới đã compile với `library-x:3`, nhưng trong container vẫn còn `library-x:1` được copy từ bộ cài cũ. Việc nâng JDK không trực tiếp làm thay đổi method descriptor; nó chỉ làm lộ sự bất nhất trong quá trình build/deploy.

## 3. Dấu hiệu runtime của xung đột

### 3.1. `NoSuchMethodError`

Giả sử `ApiClient` được biên dịch với thư viện:

```java
// common-utils phiên bản 2
public class Ids {
    public static String normalize(String id) {
        return id.trim().toLowerCase();
    }
}
```

Nhưng runtime nạp phiên bản 1:

```java
// common-utils phiên bản 1
public class Ids {
    public static String trim(String id) {
        return id.trim();
    }
}
```

Consumer cũ đã compile lời gọi:

```java
String normalized = Ids.normalize(" A01 ");
```

Class file chứa symbolic reference đến method `normalize(Ljava/lang/String;)Ljava/lang/String;`. Khi runtime dùng bản không có method đó, có thể nhận:

```text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.common.Ids.normalize(java.lang.String)'
```

Việc method có cùng tên nhưng khác **parameter hoặc return descriptor** cũng có thể gây `NoSuchMethodError`. JVM không chỉ tìm tên method.

### 3.2. `NoClassDefFoundError`

Một library có thể tham chiếu class từ dependency bị thiếu ở runtime:

```text
java.lang.NoClassDefFoundError:
  com/example/json/JsonMapper
```

Nguyên nhân có thể là:

- Dependency bị khai báo scope chỉ dùng lúc compile.
- WAR/container không chứa JAR.
- Dependency bị exclude quá rộng.
- Class đã chuyển package giữa phiên bản.
- Module hoặc classloader không có quyền nhìn thấy class.

`NoClassDefFoundError` cũng có thể xuất hiện sau lỗi khởi tạo class, không chỉ khi thiếu file. Cần xem `Caused by` và trạng thái class initialization.

### 3.3. `IncompatibleClassChangeError`, `NoSuchFieldError`

Một method đổi từ instance sang static, một class đổi loại, hoặc field bị xóa/đổi descriptor có thể dẫn tới lỗi linkage:

```text
java.lang.IncompatibleClassChangeError
java.lang.NoSuchFieldError
```

Đây là tín hiệu rõ về binary contract không khớp giữa những artifact được compile và load. Không nên đổi ngẫu nhiên thứ tự JAR trước khi xác định class thực tế.

### 3.4. `ClassCastException` khi tên class trông giống nhau

Ví dụ:

```text
java.lang.ClassCastException:
  class com.example.Plugin cannot be cast to class com.example.Plugin
```

Thông báo có thể hiển thị cùng FQCN nhưng kèm hai classloader khác nhau. Runtime phân biệt class theo **(binary name, defining classloader)**, không chỉ theo tên in ra.

Vấn đề có thể đến từ plugin isolation, servlet application classloader hoặc cùng một API JAR bị nhúng riêng trong từng plugin.

### 3.5. Lỗi khác chỉ xuất hiện ở đường chạy hiếm gặp

Một số xung đột không gây lỗi lúc startup:

- `ServiceLoader` nạp provider sau khi một tính năng được kích hoạt.
- Framework dùng reflection tới method mới khi xử lý request cụ thể.
- Serializer đụng một annotation class khác phiên bản.
- JDBC/HTTP library có API chỉ được gọi ở chế độ retry hoặc fallback.
- Batch job tải class từ một plugin directory sau nhiều giờ chạy.

Do đó, một smoke test chỉ mở được homepage không đủ chứng minh dependency graph đúng.

## 4. JVM quyết định class nào được nạp như thế nào?

### 4.1. Classloader không “trộn” hai bản class

Một JVM có thể có bootstrap, platform và application classloader, cùng các loader do framework/container tự tạo. Theo mô hình delegation phổ biến, loader hỏi parent trước rồi tìm ở vùng classpath của nó, nhưng một số container/plugin có chính sách child-first hoặc isolation riêng.

Trong phạm vi một classloader và một tên class, runtime không tạo một class tổng hợp từ nhiều JAR. Nó dùng class được tìm/nạp theo quy tắc loader.

**Không có quy tắc áp dụng cho mọi Java runtime rằng “JAR xuất hiện đầu tiên trong danh sách `lib` chắc chắn thắng”.** Kết quả còn phụ thuộc cách launcher mở rộng wildcard, thứ tự classpath, parent delegation và classloader chuyên biệt.

### 4.2. Wildcard classpath không đảm bảo thứ tự ổn định

Ví dụ:

```bash
java -cp "lib/*:app.jar" com.example.Main
```

Launcher hỗ trợ wildcard để bao gồm JAR từ thư mục `lib`, nhưng **thứ tự mở rộng wildcard không nên được xem là hợp đồng ổn định**. Vì vậy, nếu hai JAR chứa cùng class, thay đổi filesystem/build/deploy có thể dẫn đến kết quả khác.

Giải pháp đúng là loại trừ hoặc tổ chức lại class trùng, không cố dựa vào thứ tự không được bảo đảm.

### 4.3. Class identity và loader isolation

Hai plugin có thể mỗi plugin nạp một bản thư viện riêng:

```text
Application ClassLoader
        |
        +-- PluginLoader A -> common-api.jar
        |
        +-- PluginLoader B -> common-api.jar
```

Dù file class giống nhau, nếu mỗi loader định nghĩa `com.example.api.Event` độc lập, object của Plugin A không thể tùy tiện cast sang kiểu `Event` của Plugin B.

Thiết kế plugin an toàn hơn thường là đặt các kiểu API dùng chung ở parent/shared loader và để từng plugin cô lập implementation dependencies. Nhưng điều này còn phụ thuộc contract của framework/plugin system thực tế.

### 4.4. Resource cũng có thể trùng

Trùng lặp không chỉ xảy ra với `.class`. Các resource sau có thể bị ghi đè hoặc chỉ một bản được đọc:

```text
META-INF/services/com.example.spi.Parser
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
log4j2.xml
application.properties
```

Một shading/fat-JAR task sao chép hai resource có cùng tên nhưng không merge đúng có thể làm mất provider hoặc cấu hình auto-configuration. Vì vậy, giải quyết duplicate classes cần đi kèm **resource collision** và **service descriptor merging**.

## 5. Maven giải quyết xung đột phiên bản

### 5.1. Dependency mediation: nearest definition

Maven thường dùng quy tắc **nearest definition** khi nhiều đường dẫn yêu cầu các phiên bản khác nhau của cùng artifact: dependency ở độ sâu ngắn hơn trong graph được ưu tiên. Nếu hai đường cùng độ sâu, thứ tự khai báo có thể ảnh hưởng kết quả.

Ví dụ:

```text
app
├── payment-sdk:2.0
│   └── common-utils:2.5
└── report-sdk:1.8
    └── common-utils:1.9
```

Hai yêu cầu tới `common-utils` cùng độ sâu. Kết quả mediation có thể phụ thuộc thứ tự khai báo trực tiếp các SDK trong POM.

Điểm quan trọng: **Maven không đơn giản luôn chọn phiên bản mới nhất.** Quy tắc này khác hành vi mặc định thường gặp ở Gradle.

Một build có thể chạy với `common-utils:1.9` dù `payment-sdk:2.0` cần API chỉ có từ 2.5. Vì vậy, việc “Maven build thành công” không tự bảo đảm binary/runtime compatibility.

### 5.2. Kiểm tra dependency tree

Trong Maven:

```bash
mvn dependency:tree
```

Tập trung vào artifact:

```bash
mvn dependency:tree -Dincludes=com.example:common-utils
```

Có thể chỉ định plugin version để tạo kết quả tái hiện:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.7.1:tree \
  -Dincludes=com.example:common-utils
```

Tùy version plugin, output có thể cho thấy dependency bị omit do conflict hoặc duplicate. Cần xem **resolved tree**, không chỉ POM khai báo ban đầu.

Nếu dự án có profile hoặc reactor multi-module, chạy với đúng Maven profile, module và scope mà pipeline production sử dụng.

### 5.3. Khai báo phiên bản thống nhất trực tiếp

Một giải pháp là đưa dependency dùng chung vào POM ứng dụng với version được phê duyệt:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>common-utils</artifactId>
        <version>2.5.0</version>
    </dependency>
</dependencies>
```

Direct dependency thường có ưu tiên mediation cao hơn dependency transitively requested, nhưng **không có nghĩa version được chọn chắc chắn tương thích với mọi consumer**. Phải kiểm tra các thư viện dùng chung API và test.

### 5.4. `dependencyManagement` và BOM

Với dự án nhiều module, ưu tiên quản lý version tập trung:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>common-utils</artifactId>
            <version>2.5.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

`dependencyManagement` đặt quy tắc quản lý version; bản thân nó **không tự bổ sung dependency mới** vào classpath nếu module không có dependency tương ứng.

Một BOM có thể cung cấp tập version tương thích:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.platform</groupId>
            <artifactId>platform-bom</artifactId>
            <version>3.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Khi nâng framework hoặc platform BOM, xem toàn bộ version thay đổi chứ không chỉ một thư viện gây lỗi.

### 5.5. Loại trừ dependency transitively requested

Nếu một SDK kéo thư viện cũ mà ứng dụng muốn thay bằng bản mới:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-report-sdk</artifactId>
    <version>1.8.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>common-utils</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Sau đó khai báo version `common-utils` phù hợp ở phần dependency trực tiếp hoặc dependency management.

**Không exclude chỉ để dependency tree “sạch”.** Một SDK có thể cần những API quan trọng của artifact bị loại; nếu version thay thế không tương thích, lỗi sẽ chuyển sang runtime.

Exclusion trong Maven gắn với dependency path khai báo. Nếu cùng artifact được kéo qua nhánh khác, cần kiểm tra toàn bộ graph để biết nó còn được resolve không.

### 5.6. Maven Enforcer hỗ trợ phát hiện sớm

Maven Enforcer có các rule hữu ích:

- `dependencyConvergence`: phát hiện những đường dẫn transitive không thống nhất version theo yêu cầu của rule.
- `requireUpperBoundDeps`: phát hiện một số trường hợp resolved version thấp hơn version transitively requested.
- `bannedDependencies`: cấm artifact/version nằm trong danh sách không được phép.

Ví dụ ý tưởng cấu hình:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-dependencies</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence />
                    <requireUpperBoundDeps />
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Quy tắc này làm build thất bại sớm khi graph không đáp ứng chính sách, nhưng chưa phát hiện tất cả duplicate `.class` nằm trong các artifact có tọa độ khác nhau.

## 6. Gradle giải quyết xung đột phiên bản

### 6.1. Hành vi mặc định khác Maven

Khi nhiều dependency yêu cầu các version khác nhau của cùng module, Gradle thường áp dụng conflict resolution để **chọn version cao hơn có thể chấp nhận**, chịu ảnh hưởng của constraints, metadata, capabilities, component selection và cấu hình resolution.

Ví dụ:

```text
checkout-app
├── payment-sdk -> common-utils:2.5
└── report-sdk  -> common-utils:1.9
```

Gradle có thể resolve `common-utils:2.5` trong `runtimeClasspath` thay vì bản 1.9. Điều đó không chứng minh bản 2.5 vẫn tương thích với `report-sdk`.

Không nên diễn giải giản lược thành “Gradle lúc nào cũng chọn latest release trên Internet”; nó chỉ resolve theo graph, version selectors và rules thực tế.

### 6.2. Xem graph theo configuration

Gradle có nhiều configuration như `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath` hoặc các variant riêng:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Xem lý do chọn version cho artifact:

```bash
./gradlew dependencyInsight \
  --dependency common-utils \
  --configuration runtimeClasspath
```

`dependencyInsight` cho thấy đường kéo dependency và lý do version được chọn, chẳng hạn conflict resolution, constraint hoặc force.

Nếu gặp lỗi ở integration test, xem configuration chứa runtime của test; nếu lỗi ở production, tập trung vào `runtimeClasspath` và artifact đã đóng gói.

### 6.3. Đặt version bằng constraints

Trong Gradle Groovy DSL:

```groovy
dependencies {
    constraints {
        implementation('com.example:common-utils:2.5.0') {
            because 'Platform API version used by payment SDK'
        }
    }
}
```

Constraint tác động đến quá trình resolution khi module đó có mặt trong graph; nó không phải một dependency trực tiếp bổ sung thư viện mới trong mọi trường hợp.

Với hệ thống nhiều module, có thể dùng Java Platform plugin hoặc version catalogs để quản lý danh mục version, nhưng cần phân biệt:

- Version catalog giúp tập trung **khai báo** các version.
- Platform/constraints ảnh hưởng trực tiếp **quá trình resolve** version.
- Dependency locking giúp cố định **kết quả resolution** để tái hiện build.

### 6.4. Fail sớm khi có version conflict

Gradle có thể được cấu hình để không âm thầm chọn một version khi có xung đột:

```groovy
configurations.configureEach {
    resolutionStrategy.failOnVersionConflict()
}
```

Rule này làm lộ conflict thay vì chỉ chọn version theo mặc định. Trên dự án lớn, cần triển khai có kiểm soát vì các graph đã có nhiều yêu cầu version khác nhau có thể bắt đầu thất bại.

Phương pháp giải quyết là thống nhất dependency constraints/versions và chứng minh compatibility, không phải tắt rule ngay khi gặp nhiều lỗi.

### 6.5. Exclude và force

Exclude trong Gradle:

```groovy
dependencies {
    implementation('com.example:report-sdk:1.8.0') {
        exclude group: 'com.example', module: 'common-utils'
    }
    implementation('com.example:common-utils:2.5.0')
}
```

Một số dự án dùng `resolutionStrategy.force` để ghim version. Đây là biện pháp mạnh và có thể che giấu sự không tương thích của dependency, nên chỉ dùng khi đã xác nhận lý do, phạm vi và kế hoạch thay thế bằng constraints/platform hoặc nâng thư viện.

Force không tự sửa binary compatibility, không loại duplicate classes giữa artifact khác tọa độ và không sửa resource collisions.

### 6.6. Dependency locking và verification

Khi đã chọn một graph tương thích, dependency locking giúp giữ kết quả resolve ổn định theo cấu hình được hỗ trợ, thay vì thay đổi bất ngờ theo dynamic version hoặc metadata.

Dependency verification bổ sung kiểm soát tính toàn vẹn/nguồn gốc artifact theo cơ chế của Gradle. Hai tính năng phục vụ mục tiêu khác nhau:

- Locking: artifact/version nào được resolve.
- Verification: artifact tải về có đúng nội dung/ký xác minh được như kỳ vọng không.

Chúng không tự thay thế integration test và binary compatibility checks.

## 7. Vì sao version conflict được giải quyết nhưng duplicate class vẫn tồn tại?

Build tool chủ yếu giải quyết dependency theo **component identity** như group/module/version. Hai artifact khác nhau có thể đóng gói cùng class.

Ví dụ:

```text
lib/json-core-2.0.jar
  com/acme/json/Reader.class

lib/legacy-all-in-one-1.0.jar
  com/acme/json/Reader.class
  com/acme/http/Client.class
```

Version resolution không coi hai artifact này là hai phiên bản của cùng `group:artifact` nếu tọa độ khác nhau. Cả hai JAR có thể được giữ trong runtime classpath và tạo class collision.

Các nguồn tạo duplicate classes thường gặp:

1. Uber JAR hoặc SDK fat JAR đã nhúng dependency.
2. JAR cũ copy nguyên class từ thư viện thứ ba nhưng không relocate.
3. Hai module nội bộ cùng compile package/class giống nhau.
4. Source-generated code có trùng FQCN với thư viện khác.
5. WAR chứa class ở `WEB-INF/classes` và JAR khác trong `WEB-INF/lib`.
6. Application server có shared library và ứng dụng lại bundle cùng package.
7. Một artifact được copy hai lần theo các tên file khác nhau.
8. Shading/assembly task merge hai dependency mà không kiểm soát duplicates.

**Giải quyết xung đột version không đồng nghĩa giải quyết duplicate classes**. Cần kiểm tra cả danh sách JAR và nội dung của chúng.

## 8. Phát hiện class trùng trong JAR

### 8.1. Liệt kê nội dung một JAR

JDK cung cấp `jar`:

```bash
jar tf lib/common-utils-2.5.jar
```

Tìm class cụ thể trong output:

```bash
jar tf lib/common-utils-2.5.jar | grep 'com/example/common/Ids.class'
```

Trên Windows PowerShell:

```powershell
jar tf lib/common-utils-2.5.jar |
    Select-String 'com/example/common/Ids.class'
```

Nếu nghi ngờ class trùng, tìm FQCN đó trong **mọi JAR trên runtime classpath**, không chỉ các dependency trực tiếp.

### 8.2. Quét nhiều JAR bằng PowerShell

Ví dụ khảo sát một thư mục phân phối trên Windows. Lệnh chỉ đọc JAR và in tên artifact chứa một class:

```powershell
$relativeClass = 'com/example/common/Ids.class'

Get-ChildItem -LiteralPath 'dist/lib' -Filter '*.jar' -File |
    ForEach-Object {
        $jar = $_.FullName
        $entries = & jar tf $jar
        if ($entries -contains $relativeClass) {
            Write-Output $jar
        }
    }
```

Đây là cách kiểm tra có mục tiêu; với nhiều JAR lớn hoặc classloader động, nên dùng công cụ quét hiệu quả hơn và lấy tập artifact đúng với runtime thật.

### 8.3. Sự khác biệt với multi-release JAR

Một multi-release JAR có thể chứa:

```text
com/example/Codec.class
META-INF/versions/11/com/example/Codec.class
META-INF/versions/17/com/example/Codec.class
```

Đây **không tự động là duplicate-class bug**. Nếu manifest có `Multi-Release: true`, JVM hỗ trợ cơ chế lựa chọn implementation theo release. Không nên xóa các class trong `META-INF/versions` chỉ vì công cụ quét cơ bản thấy trùng tên logic.

Ngược lại, hai artifact khác nhau chứa cùng binary name ở cùng ngữ cảnh mới là rủi ro cần điều tra.

### 8.4. Kiểm tra bytecode và descriptor

Nếu lỗi nhắc đến method/field:

```bash
javap -classpath lib/common-utils-2.5.jar \
  -s com.example.common.Ids
```

So sánh với bản cũ:

```bash
javap -classpath lib/common-utils-1.9.jar \
  -s com.example.common.Ids
```

`javap -s` giúp xem method descriptors, còn `javap -v` có thể hiển thị thông tin class file chi tiết. Đây là bằng chứng để phân biệt API đã đổi với lỗi do class được nạp sai bản.

## 9. Xác định class thực sự được JVM nạp từ đâu

### 9.1. In nguồn của class bằng Java

Một đoạn chẩn đoán đơn giản:

```java
import java.net.URL;

public final class ClassOrigin {
    public static void main(String[] args) {
        Class<?> type = com.example.common.Ids.class;

        System.out.println("Class: " + type.getName());
        System.out.println("Loader: " + type.getClassLoader());

        URL location = type.getProtectionDomain() == null
                || type.getProtectionDomain().getCodeSource() == null
                ? null
                : type.getProtectionDomain().getCodeSource().getLocation();

        System.out.println("Code source: " + location);
    }
}
```

`CodeSource` là một tín hiệu hữu ích nhưng có thể không có hoặc không phản ánh trực tiếp tệp JAR khi class do custom loader, in-memory instrumentation hoặc đặc điểm container tạo ra. Cần kết hợp log class loading.

### 9.2. Log class loading từ JDK 9 trở lên

Ví dụ với JVM hỗ trợ unified logging:

```bash
java -Xlog:class+load=info -cp "app.jar:lib/*" com.example.Main
```

Output có thể cho thấy class được nạp và nguồn liên quan. Với JDK 8, có thể gặp tùy chọn chẩn đoán lịch sử như `-verbose:class`. Tùy chọn và định dạng log phụ thuộc JDK; luôn xác nhận bằng runtime mục tiêu.

Nếu ứng dụng dùng Spring Boot launcher, WAR container hoặc plugin framework, cần chạy **launcher thật** thay vì tự tạo classpath gần giống.

### 9.3. Kiểm tra nhiều classloader

Khi có nghi ngờ class identity:

```java
Class<?> a = pluginAClassLoader.loadClass("com.example.api.Event");
Class<?> b = pluginBClassLoader.loadClass("com.example.api.Event");

System.out.println(a == b);
System.out.println(a.getClassLoader());
System.out.println(b.getClassLoader());
```

Kết quả `false` cho thấy hai đối tượng `Class` khác nhau dù binary name giống. Nhưng không phải cứ khác loader là sai: plugin isolation có thể chủ đích. Sai khi object/API phải được trao đổi qua một hợp đồng kiểu thống nhất mà các bên lại dùng defining loader khác nhau.

## 10. Sửa bằng cách thống nhất dependency graph

Một cách xử lý có kiểm soát:

1. Xác định method/class đang lỗi và artifact chứa nó.
2. Kiểm tra version khi compile và runtime.
3. Xem dependency tree hoặc `dependencyInsight`.
4. Chọn version phù hợp với **toàn bộ consumers**.
5. Nâng SDK/framework yêu cầu version cũ nếu có thể.
6. Dùng BOM/platform/constraint để thống nhất version.
7. Exclude dependency thừa ở đúng nhánh.
8. Tạo artifact sạch, kiểm tra các JAR thực sự được đóng gói.
9. Chạy consumer integration test trên runtime mục tiêu.

### 10.1. Tại sao không mặc định chọn version cao nhất?

Semantic versioning không phải bảo đảm kỹ thuật rằng một thư viện luôn giữ binary compatibility. Một major version có thể xóa method, thay return descriptor hoặc đổi package.

Ngược lại, việc cố ghim bản cũ có thể làm framework mới lỗi vì nó cần API mới. Phải kiểm tra compatibility matrix, release notes và test giữa các component thực sự.

### 10.2. BOM và constraints chưa đủ nếu package sai

Giả sử Maven/Gradle resolve đúng `common-utils:2.5`, nhưng Dockerfile lại copy một `common-utils-1.9.jar` từ thư mục cũ vào `/app/lib`.

Dependency graph của build có thể hoàn hảo, nhưng runtime classpath production lại lỗi. Do đó, **artifact cuối cùng** và cách launcher nạp class phải được kiểm tra như một bước riêng.

## 11. Sửa duplicate classes bằng loại trừ hoặc thay đổi packaging

Nếu hai JAR chứa cùng FQCN, cần xác định mục đích của từng bản:

- Một bản hoàn toàn dư thừa: loại bản không cần khỏi runtime.
- Một artifact đã nhúng dependency của artifact khác: dùng bản “thin” nếu nhà phát hành có cung cấp.
- Một SDK yêu cầu thư viện riêng nhưng build đã thêm lại cùng class: điều chỉnh packaging/exclusion.
- Hai implementation phải cùng tồn tại: cân nhắc shading với package relocation hoặc classloader isolation có hợp đồng rõ ràng.
- Code nội bộ copy class từ thư viện thứ ba: loại bản copy và phụ thuộc artifact chính thức.

Không nên xóa một JAR chỉ vì nó chứa class trùng; nó có thể còn nhiều class hoặc resources khác được ứng dụng cần.

### 11.1. Shading và relocation

Một thư viện có thể đóng gói dependency dưới namespace riêng để tránh collision:

```text
Trước:
com.vendor.json.Parser

Sau relocation:
com.example.repackaged.vendor.json.Parser
```

Ví dụ fragment cấu hình Maven Shade Plugin:

```xml
<relocations>
    <relocation>
        <pattern>com.vendor.json</pattern>
        <shadedPattern>com.example.internal.shaded.json</shadedPattern>
    </relocation>
</relocations>
```

Đây là fragment trong `maven-shade-plugin`, không phải POM hoàn chỉnh. Relocation cần được áp dụng có chủ đích, vì reflection theo tên class, serialization, resource lookup, annotation metadata và service provider files có thể vẫn tham chiếu package cũ.

**Chỉ gộp hai JAR vào một fat JAR mà không relocate không giải quyết collision**; việc merge có thể chỉ che giấu một bản class bằng bản còn lại.

### 11.2. Resource transformer và service files

Nếu shaded artifact chứa nhiều provider:

```text
META-INF/services/com.example.spi.Parser
```

cần merge service descriptors đúng cách. Maven Shade có resource transformers phục vụ loại tài nguyên này; Gradle Shadow cũng có các cơ chế tương ứng tùy plugin/version.

Nếu không merge đúng, `ServiceLoader` có thể chỉ tìm thấy một provider dù các implementation class đều còn trong JAR.

### 11.3. Rủi ro khi relocate public API

Không nên tự ý relocate kiểu xuất hiện trong **public API** của thư viện, ví dụ method trả về `com.vendor.json.Node`. Nếu tên kiểu thay đổi mà consumer không được điều chỉnh, source/binary compatibility có thể vỡ.

Relocation phù hợp hơn với dependency là **implementation detail**, không bị lộ qua contract public hoặc serialization format.

## 12. JPMS không giống classpath truyền thống

Khi chuyển từ classpath sang module path:

- Mỗi named module có tên và module descriptor/metadata.
- Những package trùng giữa các named modules có thể vi phạm quy tắc module resolution/readability.
- `requires`, `exports`, `opens` và service declarations tác động tới khả năng truy cập.
- Một JAR thiếu `module-info.class` có thể được nhận diện là automatic module trên module path.

### 12.1. Split package

Ví dụ hai module cùng chứa package:

```text
module com.example.api
  com.example.shared.Customer

module com.example.impl
  com.example.shared.CustomerMapper
```

JPMS có thể từ chối cấu hình mà hai module cung cấp cùng package trong phạm vi module graph, dù FQCN không trùng. Đây là **split-package problem**, khác duplicate class trên classpath.

Thêm `Automatic-Module-Name` hoặc thay thứ tự JAR không giải quyết split package. Cần tái tổ chức package/module boundary hoặc thay đổi cách đóng gói.

### 12.2. Duplicate module name

Hai automatic modules có thể suy ra cùng tên từ filenames, hoặc khai báo cùng `Automatic-Module-Name`. Khi đưa vào module path, JVM/build tool có thể báo trùng module name, ngay cả khi classes không trùng.

Đây là một dạng conflict khác: **module identity**, không chỉ dependency version hoặc FQCN.

### 12.3. Không nhầm `--add-opens` với sửa dependency

`--add-opens` chỉ mở package để deep reflection trong JPMS; nó không làm xuất hiện class/method bị thiếu và không chọn đúng version thư viện.

Nếu lỗi là `NoSuchMethodError`, thêm `--add-opens` thường không xử lý nguyên nhân. Cần phân biệt encapsulation với binary linkage.

## 13. Classpath của application server và framework launcher

### 13.1. WAR và servlet container

Một ứng dụng WAR thường có:

```text
WEB-INF/classes/
WEB-INF/lib/*.jar
```

Trong khi servlet container có thể cung cấp shared libraries ở vị trí riêng. Nếu cả WAR và container có cùng API/implementation, classloader policy của container sẽ quyết định hành vi.

Dependency có scope `provided` trong Maven có thể không nằm trong WAR. Scope này chỉ đúng nếu container thực sự cung cấp dependency tương thích.

Khi nâng application server, cần đối chiếu library versions do server cung cấp thay vì chỉ kiểm tra `WEB-INF/lib`.

### 13.2. Spring Boot executable JAR

Một executable JAR kiểu Spring Boot thường có cấu trúc và launcher riêng; nested dependency JAR không giống một classpath liệt kê JAR phẳng bằng wildcard.

Không nên suy rằng `java -cp "lib/*"` tái tạo chính xác hành vi của `java -jar app.jar`. Hãy kiểm tra artifact Boot được package, danh sách `BOOT-INF/lib`, version thực tế và launcher đang dùng.

### 13.3. OSGi hoặc plugin frameworks

Một số nền tảng có dependency isolation theo bundle/plugin. Lỗi có thể do classloader visibility thay vì một version conflict thống nhất toàn JVM.

Trong môi trường này, việc force một version vào root dependency graph có thể không chạm tới classpath riêng của plugin. Cần xác định bundle/plugin classloader và contract trao đổi type trước khi sửa.

## 14. Phạm vi compile, test và production có thể khác nhau

| Phạm vi | Điều cần kiểm tra |
|---|---|
| Compile classpath | Compiler thấy API của version nào? |
| Test runtime classpath | Test framework hoặc mock dependencies có kéo thêm bản khác không? |
| Application runtime classpath | Artifact nào thật sự được nạp trong process production? |
| Build plugin classpath | Plugin Gradle/Maven có phụ thuộc nội bộ riêng không? |
| Application server shared classpath | Server cung cấp dependency/version nào? |
| Plugin classloader | Mỗi plugin có bản thư viện riêng hay dùng API chung? |
| JPMS module path | Module name, readability, split package có phù hợp? |

Ví dụ, test có thể pass khi chạy bằng Gradle `testRuntimeClasspath`, nhưng artifact production do custom packaging task tạo có thêm một JAR cũ. Bởi vậy, phải chạy ít nhất một bài kiểm thử với **chính artifact được phát hành**.

## 15. Dependency alignment với nhiều module nội bộ

Giả sử hệ thống có:

```text
platform-api:3.0
platform-domain:3.0
platform-service:3.0
```

Nếu `platform-service:3.0` sử dụng method mới trong `platform-domain:3.0` nhưng ứng dụng chỉ mang `platform-domain:2.4`, runtime có thể ném `NoSuchMethodError`.

Với nhóm thư viện thường phát hành cùng nhau, có thể áp dụng:

- Một BOM (Maven) hoặc platform constraints (Gradle).
- Quy tắc release train/compatibility matrix.
- Dependency locking để tái hiện graph.
- Kiểm thử consumer với bộ phiên bản được hỗ trợ.
- Policy không cho phép hỗn hợp phiên bản ngoài ma trận đã xác nhận.

Tuy nhiên, **đồng bộ số version không tự đồng bộ binary contract**. Nếu nhóm phát hành cùng version nhưng API bị thay đổi không tương thích, vẫn phải có test hoặc công cụ so sánh API.

## 16. Công cụ hỗ trợ phân tích nhanh

### 16.1. `jdeps`

`jdeps` phân tích dependency tĩnh trong bytecode:

```bash
jdeps --recursive \
  --class-path "lib/*" \
  app.jar
```

Nó giúp phát hiện class/module tham chiếu tới thư viện nào và các dependency còn thiếu trong phân tích. Nhưng `jdeps` không luôn phát hiện reflection, service loading hoặc class được tạo động, và không thay thế classpath inspection.

### 16.2. `javap`

Để đối chiếu method descriptor:

```bash
javap -classpath old-library.jar -s com.example.common.Ids
javap -classpath new-library.jar -s com.example.common.Ids
```

Đây là bằng chứng cho thấy method signature/descriptor đã thay đổi. Khi chẩn đoán lỗi linkage, cần so sánh thêm class được load từ đâu.

### 16.3. Maven Dependency Plugin / Gradle dependencyInsight

Maven:

```bash
mvn dependency:tree -Dincludes=com.example:common-utils
```

Gradle:

```bash
./gradlew dependencyInsight \
  --dependency common-utils \
  --configuration runtimeClasspath
```

Công cụ này trả lời **vì sao một version được chọn**, không tự chứng minh class ở production được load từ chính artifact đó.

### 16.4. Các công cụ phân tích API và duplicate classes

Có thể dùng japicmp hoặc Revapi để kiểm tra breaking changes giữa hai phiên bản library. Một số plugin Maven/Gradle hoặc custom verification tasks có thể quét duplicate `.class` entries trong tập runtime artifacts.

Khi lựa chọn công cụ, cần kiểm tra nó có phân biệt multi-release JAR, resource duplicates, relocated classes và classloader scope hay không.

## 17. Quy trình xử lý sự cố theo từng bước

### Bước 1 — Ghi lại lỗi đầy đủ

Lưu exact exception, nested cause, stack trace và môi trường. Xác định **class/method/field bị lỗi**, không chỉ đọc dòng đầu của exception.

### Bước 2 — Xác định version runtime

Ghi JDK vendor/update, launcher, process arguments, container image và JAR/WAR/deployment artifact. Nếu có nhiều classloader, ghi loading context.

### Bước 3 — Tìm artifact chứa class

Kiểm tra mọi JAR trên runtime classpath, không chỉ dependencies do build tool khai báo. Nếu cùng FQCN xuất hiện trong nhiều JAR, ghi rõ từng artifact và nguồn gốc.

### Bước 4 — Xem dependency graph

Dùng Maven dependency tree hoặc Gradle `dependencyInsight` trên đúng configuration và module. Xác định requested version, selected version và dependency path dẫn tới lựa chọn đó.

### Bước 5 — Xem bytecode

Dùng `javap -s` để so sánh method/field descriptors ở phiên bản compile và runtime. Nếu là lỗi class identity, kiểm tra defining classloaders.

### Bước 6 — Chọn thay đổi phù hợp

- Version conflict: nâng SDK và quản lý version tập trung.
- Duplicate classes: loại JAR dư, chọn thin artifact hoặc shade/relocate có kiểm soát.
- Missing dependency: sửa scope/packaging.
- Container shared library: thống nhất policy classloader hoặc điều chỉnh thư viện được container cung cấp.
- Plugin isolation: thống nhất shared API loader hoặc giữ classloader boundaries rõ.
- JPMS split package: tái tổ chức package/module boundary.

### Bước 7 — Xây dựng lại artifact sạch

Clean build, resolve dependency và package lại. Tránh dựa vào cache hoặc thư mục `lib` sót từ phiên bản trước.

### Bước 8 — Kiểm thử bằng artifact cuối

Chạy ứng dụng trong môi trường giống production, kiểm tra class loading source và những đường nghiệp vụ thực tế từng lỗi.

### Bước 9 — Cố định và giám sát

Lưu resolved dependency graph, lockfiles/BOM, artifact hashes và quy tắc duplicate class detection. Thêm regression test để lỗi không quay lại ở lần nâng tiếp theo.

## 18. Ví dụ tổng hợp: Maven chọn nhầm thư viện thấp hơn

Giả sử:

```text
checkout-app
├── reporting-sdk:1.0 -> common-utils:1.5
└── payment-sdk:3.0   -> common-utils:2.2
```

Ở cấu hình Maven cụ thể, version 1.5 được chọn do mediation. Nhưng `payment-sdk:3.0` đã được biên dịch với method chỉ có ở 2.2. Kết quả:

```text
java.lang.NoSuchMethodError:
 com.example.common.Ids.normalize(...)
```

Điều tra:

1. `mvn dependency:tree` để xem vì sao 1.5 được chọn.
2. `javap -classpath ... -s` để xác nhận 1.5 thiếu method.
3. Xác minh SDK `reporting-sdk:1.0` có tương thích với 2.2 không.
4. Nếu có, quản lý version 2.2 bằng BOM hoặc direct dependency.
5. Nếu không, nâng `reporting-sdk` lên bản tương thích hoặc tách ứng dụng theo giới hạn rõ.
6. Clean package, kiểm tra trong WAR/JAR/container không còn bản 1.5.
7. Test lại trên runtime thực tế.

Nếu runtime vẫn nạp 1.5 dù dependency graph đã chọn 2.2, cần điều tra cơ chế packaging/classloader chứ không tiếp tục sửa POM một cách mù quáng.

## 19. Ví dụ tổng hợp: fat JAR mang class trùng

Giả sử:

```text
checkout-app.jar
  BOOT-INF/lib/json-core-2.0.jar
  BOOT-INF/lib/legacy-client-1.0.jar
```

`legacy-client-1.0.jar` đã nhúng một bản `com.vendor.json.Reader` cũ không relocate, còn `json-core-2.0.jar` có class cùng tên. Lúc này:

- Maven/Gradle có thể không báo version conflict vì hai artifact có tọa độ khác.
- Tùy loader và packaging, một bản class có thể được nạp trước.
- `legacy-client` có thể cần implementation cũ, trong khi code mới cần API 2.0.

Cách xử lý ưu tiên:

1. Tìm phiên bản `legacy-client` mới không embed dependency hoặc đã chuyển sang bản tương thích.
2. Nếu có bản thin, dùng nó và quản lý `json-core` ở cấp ứng dụng.
3. Nếu buộc phải giữ hai implementation, xem xét relocation **bên trong SDK** cho dependency nội bộ.
4. Kiểm tra resources/service descriptors, reflection và serialization sau relocation.
5. Chạy test trên chính artifact Boot cuối.

Không nên chỉ đổi thứ tự tên JAR hoặc đổi file extension để che lỗi.

## 20. Checklist trước khi kết thúc migration

- [ ] Đã phân biệt version conflict, duplicate FQCN, missing class, classloader issue và JPMS split package.
- [ ] Đã ghi đúng JDK, application launcher và runtime artifact.
- [ ] Đã xem Maven/Gradle resolved dependency graph ở đúng configuration.
- [ ] Đã xác định direct và transitive paths gây conflict.
- [ ] Đã kiểm tra phiên bản compile khác runtime hay không.
- [ ] Đã quét class trùng trong các JAR thực sự được deploy.
- [ ] Đã kiểm tra class source và defining classloader khi runtime.
- [ ] Đã so sánh method/field descriptor khi xuất hiện linkage error.
- [ ] Đã kiểm tra classpath WAR, executable JAR, container và shared library của server.
- [ ] Đã đánh giá resource/service descriptor collisions.
- [ ] Đã chọn version thống nhất bằng BOM, dependency management hoặc Gradle constraints.
- [ ] Đã tránh dùng exclusions/force để che lỗi compatibility.
- [ ] Nếu dùng shading, đã xử lý relocation và các resources/reflection liên quan.
- [ ] Nếu dùng JPMS, đã giải quyết split package và duplicate module names.
- [ ] Đã kiểm thử consumer bằng artifact cuối và các đường chạy quan trọng.
- [ ] Đã lưu dependency locks/graph, artifact checksums và regression checks.

## 21. Kết luận

Xung đột phiên bản và lớp trùng trên classpath là hai nhóm rủi ro khác nhau trong Java Compatibility Migration. Maven/Gradle chọn phiên bản theo cơ chế resolution riêng, nhưng JVM lại nạp class theo classloader và artifact runtime thực tế. Một dependency tree đúng không bảo đảm JAR được deploy đúng; một class file có cùng tên không bảo đảm cùng binary contract hoặc cùng defining classloader.

Cách xử lý bền vững là **đi từ exception tới class thực sự được nạp, truy nguyên dependency graph, thống nhất version bằng chính sách quản lý tập trung, loại bỏ class trùng không cần thiết và kiểm thử trên artifact cuối**. Không dựa vào thứ tự JAR tình cờ hoặc ép một version không được kiểm chứng. Khi lớp dependency, packaging và classloading đều được kiểm soát, nâng JDK và thư viện sẽ ít tạo ra lỗi linkage khó tái hiện hơn.
