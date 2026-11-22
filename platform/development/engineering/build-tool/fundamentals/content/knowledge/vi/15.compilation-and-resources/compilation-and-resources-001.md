# Cấu hình tập mã nguồn và tài nguyên cần xử lý

Một dự án Java thường có nhiều loại đầu vào: mã Java chính, mã kiểm thử, tệp cấu hình, template, ảnh, dữ liệu mẫu và mã nguồn được sinh tự động. Công cụ build cần biết mỗi loại tệp nằm ở đâu, thuộc phần nào của dự án và phải được xử lý như thế nào.

Gradle và Maven cung cấp các quy ước thư mục mặc định để tự nhận diện mã nguồn và tài nguyên. Khi dự án tuân theo quy ước, bạn thường không cần cấu hình đường dẫn. Khi cấu trúc khác mặc định, có thêm bộ kiểm thử, có resource cần lọc hoặc có mã sinh tự động, hãy khai báo rõ các source root và resource root trong build configuration.

## 1. Phân biệt mã nguồn và tài nguyên

**Mã nguồn (source code)** là đầu vào mà compiler xử lý để tạo bytecode. Trong dự án Java, đó thường là các tệp `.java`. Compiler kiểm tra cú pháp, kiểu dữ liệu, tham chiếu lớp và tạo các tệp `.class`.

**Tài nguyên (resources)** là các tệp không được biên dịch thành bytecode Java nhưng cần có mặt khi ứng dụng hoặc test chạy. Ví dụ:

- Tệp cấu hình như `.properties`, `.yml`, `.yaml`, `.xml`.
- Template HTML, email hoặc báo cáo.
- Ảnh, font, biểu tượng và tệp tĩnh.
- Dữ liệu mẫu JSON, CSV, XML hoặc SQL dùng trong test.
- Schema, file mapping hoặc metadata mà ứng dụng đọc lúc chạy.

Thông thường, build tool sao chép resource vào output tương ứng để nó có mặt trên classpath. Khi đóng gói JAR, resource của mã chính được đưa vào archive theo đường dẫn tương đối so với resource root.

Ví dụ:

```text
src/main/resources/
└── config/
    └── application.yml
```

Sau khi xử lý, tệp thường nằm trong output tại:

```text
build/resources/main/config/application.yml
```

và trong JAR ở đường dẫn:

```text
config/application.yml
```

Khi đọc từ classpath, ứng dụng thường yêu cầu `config/application.yml`, không yêu cầu đường dẫn vật lý `src/main/resources/config/application.yml`.

## 2. Cấu trúc source set Java mặc định

Gradle Java plugin và Maven đều theo một quy ước thư mục Java phổ biến:

```text
my-project/
├── build.gradle                 # hoặc build.gradle.kts
├── settings.gradle              # hoặc settings.gradle.kts
└── src/
    ├── main/
    │   ├── java/                # Mã Java chính
    │   │   └── com/example/app/
    │   │       └── Application.java
    │   └── resources/            # Tài nguyên chính
    │       └── application.yml
    └── test/
        ├── java/                # Mã Java kiểm thử
        │   └── com/example/app/
        │       └── ApplicationTest.java
        └── resources/            # Tài nguyên kiểm thử
            └── test-data.json
```

| Source set | Java source root | Resource root | Mục đích |
|---|---|---|---|
| `main` | `src/main/java` | `src/main/resources` | Mã và tài nguyên tạo nên sản phẩm chính. |
| `test` | `src/test/java` | `src/test/resources` | Mã và tài nguyên phục vụ kiểm thử. |

Source set là một nhóm logic gồm mã nguồn, tài nguyên, classpath và output. Nó không chỉ là tên một thư mục. Java plugin tạo source set `main` và `test` theo mặc định; mỗi source set có các task và configuration tương ứng.

Mã trong `src/test/java` được biên dịch riêng và dùng khi chạy test. Tài nguyên trong `src/test/resources` có mặt trên test runtime classpath, không tự động trở thành tài nguyên production trong JAR chính.

### 2.1. Source root và package Java

Source root là thư mục bắt đầu của cây package. Ví dụ:

```text
src/main/java/                 # Source root
└── com/
    └── example/
        └── order/
            └── OrderService.java
```

Tệp `OrderService.java` có thể khai báo:

```java
package com.example.order;

public class OrderService {
    public void createOrder() {
        // Xử lý tạo đơn hàng
    }
}
```

Phần `com/example/order` tương ứng với package `com.example.order`. Source root `src/main/java` không phải một phần của package. Nếu khai báo nhầm `src/main/java/com` làm source root, package sẽ bị lệch so với cấu trúc mong muốn.

### 2.2. Output mặc định

Với Gradle Java plugin, output thường được đặt trong `build/`:

```text
build/
├── classes/java/
│   ├── main/             # Bytecode của main
│   └── test/             # Bytecode của test
├── resources/
│   ├── main/             # Resource của main
│   └── test/             # Resource của test
└── libs/
    └── my-project.jar
```

Với Maven, output mặc định thường nằm trong `target/`:

```text
target/
├── classes/              # Bytecode và resource chính
├── test-classes/         # Bytecode và resource kiểm thử
└── my-project-1.0.jar
```

Tên thư mục cụ thể có thể thay đổi theo plugin và cấu hình. Hãy coi `build/` hoặc `target/` là nơi công cụ build quản lý kết quả. Không nên đặt mã nguồn do con người duy trì vào đó vì task `clean` có thể xóa toàn bộ output.

## 3. Gradle: cấu hình source set và source directory

Với Gradle Java plugin, `sourceSets` là nơi cấu hình các nhóm mã nguồn. Mỗi source set có Java source directories, resource directories, compile classpath, runtime classpath và output.

### 3.1. Thêm một source directory vào cấu hình mặc định

Giả sử dự án giữ nguyên `src/main/java` nhưng có thêm mã Java dùng chung trong `src/shared/java`:

```groovy
plugins {
    id 'java'
}

sourceSets {
    main {
        java {
            srcDir 'src/shared/java'
        }
    }
}
```

`srcDir` bổ sung thư mục vào tập source directories hiện có. Sau cấu hình, Gradle biên dịch mã chính từ cả `src/main/java` và `src/shared/java`.

Có thể bổ sung nhiều thư mục:

```groovy
sourceSets {
    main {
        java {
            srcDirs = ['src/main/java', 'src/shared/java', 'generated/java']
        }
    }
}
```

Lưu ý: `srcDirs = [...]` thay thế danh sách source roots hiện tại. Nếu chỉ muốn thêm một thư mục và giữ quy ước mặc định, dùng `srcDir`.

### 3.2. Thay thế source directory mặc định

Một dự án cũ có thể đặt mã chính trong `legacy/java` và test trong `legacy/test`. Có thể cấu hình:

```groovy
sourceSets {
    main {
        java {
            srcDirs = ['legacy/java']
        }
    }
    test {
        java {
            srcDirs = ['legacy/test']
        }
    }
}
```

Khi gán `srcDirs`, các thư mục mặc định không còn trong danh sách của source set đó trừ khi được thêm lại. Hãy xác nhận toàn bộ mã cần biên dịch đều nằm trong danh sách mới.

### 3.3. Kotlin DSL

Nếu dự án dùng `build.gradle.kts`, cú pháp tương ứng có thể viết:

```kotlin
plugins {
    java
}

sourceSets {
    named("main") {
        java {
            srcDir("src/shared/java")
        }
    }
}
```

Hoặc thay thế danh sách source roots:

```kotlin
sourceSets {
    named("main") {
        java {
            setSrcDirs(listOf("legacy/java", "generated/java"))
        }
    }
}
```

Groovy DSL và Kotlin DSL thể hiện cùng mô hình source set, nhưng cú pháp và cách gọi API khác nhau. Hãy dùng đúng DSL của build script hiện tại.

## 4. Gradle: cấu hình resource directories

Resource directories được cấu hình riêng với Java source directories. Giả sử dự án cần thêm `config/resources` vào resource của mã chính:

```groovy
sourceSets {
    main {
        resources {
            srcDir 'config/resources'
        }
    }
}
```

Sau cấu hình, Gradle xử lý resource từ cả `src/main/resources` và `config/resources`. Cấu trúc thư mục tương đối bên trong mỗi resource root được giữ khi copy vào output.

Ví dụ:

```text
config/resources/
└── templates/
    └── invoice.html
```

Resource có thể được đưa vào output tại:

```text
build/resources/main/templates/invoice.html
```

### 4.1. Thay thế resource roots

Nếu dự án dùng thư mục resource khác hoàn toàn:

```groovy
sourceSets {
    main {
        resources {
            srcDirs = ['legacy/config', 'legacy/templates']
        }
    }
    test {
        resources {
            srcDirs = ['legacy/test-data']
        }
    }
}
```

Việc thay thế resource roots của `main` không làm thay đổi resource roots của `test`. Hai source set được cấu hình độc lập.

### 4.2. Resource có cùng đường dẫn

Nếu hai resource roots chứa tệp cùng đường dẫn tương đối, ví dụ cùng có `config/application.yml`, khi copy vào một output có thể xảy ra xung đột hoặc duplicate entry. Hãy quyết định tệp nào là nguồn chính, đổi cấu trúc hoặc cấu hình chiến lược xử lý duplicate phù hợp.

Không nên dựa vào thứ tự copy ngẫu nhiên để quyết định resource nào thắng. Với task copy, có thể xem xét `duplicatesStrategy`, nhưng lựa chọn như `EXCLUDE` chỉ bỏ bản trùng theo quy tắc task; nó không giải quyết nguyên nhân hai nguồn cấu hình khác nhau cùng tạo một đường dẫn.

## 5. Chọn tệp bằng include và exclude

Đôi khi source root chứa nhiều tệp hơn những gì task cần xử lý. Gradle cho phép lọc theo pattern.

### 5.1. Lọc Java source

Ví dụ chỉ đưa các tệp Java thuộc một khu vực nhất định vào source set:

```groovy
sourceSets {
    main {
        java {
            include '**/*.java'
            exclude '**/experimental/**'
        }
    }
}
```

`include` và `exclude` dùng pattern tương đối với source directory. Nếu loại một thư mục có lớp được tham chiếu từ phần mã còn lại, compiler sẽ báo không tìm thấy lớp hoặc symbol. Lọc source nên phản ánh cấu trúc module có chủ đích, không phải cách tạm thời che lỗi biên dịch.

### 5.2. Lọc resource cho task processResources

Task `processResources` xử lý resource của source set `main`. Có thể giới hạn những tệp được copy:

```groovy
tasks.named('processResources') {
    include '**/*.yml', '**/*.properties', '**/*.html'
    exclude '**/*.secret', '**/local-only/**'
}
```

Đoạn cấu hình này ảnh hưởng đến task xử lý resource chính. Nếu cần lọc resource test, cấu hình `processTestResources` riêng:

```groovy
tasks.named('processTestResources') {
    include '**/*.json', '**/*.xml', '**/*.properties'
}
```

Hãy cẩn thận với include quá hẹp: một tệp cấu hình hoặc schema cần thiết có thể bị bỏ khỏi artifact mà không làm compiler báo lỗi, vì resource không được compiler Java kiểm tra.

### 5.3. Đổi tên hoặc xử lý resource

Task copy có thể đổi tên tệp hoặc áp dụng xử lý cho nhóm tệp cụ thể:

```groovy
tasks.named('processResources') {
    filesMatching('config/default.properties') {
        name = 'application.properties'
    }
}
```

Khi đổi tên, cần xác nhận đường dẫn mà ứng dụng sử dụng để đọc resource. Nếu mã Java vẫn tìm `config/default.properties` nhưng build đổi tên tệp thành `application.properties`, ứng dụng sẽ không tìm thấy tệp theo đường dẫn cũ.

## 6. Resource filtering và thay thế thuộc tính

Một số dự án cần thay placeholder trong resource bằng giá trị cấu hình build, ví dụ version ứng dụng hoặc tên môi trường. Gradle hỗ trợ `expand` cho các tệp template:

```groovy
version = '1.4.0'

tasks.named('processResources') {
    filesMatching('application-template.yml') {
        expand(
            appVersion: project.version,
            buildName: providers.gradleProperty('buildName').orElse('local').get()
        )
        name = 'application.yml'
    }
}
```

Tệp đầu vào có thể chứa placeholder Groovy template:

```yaml
app:
  version: '${appVersion}'
  build: '${buildName}'
```

`expand` thay placeholder bằng các giá trị đã cung cấp. Không áp dụng filtering bừa bãi lên mọi resource. Tệp JavaScript, CSS, JSON hoặc template của framework có thể có cú pháp `${...}` riêng; việc expand có thể thay nhầm nội dung hoặc làm hỏng tệp.

Không đưa secret như mật khẩu, token hoặc private key vào resource được đóng gói. Giá trị môi trường và credentials thường nên được cung cấp lúc triển khai qua secret store hoặc environment của runtime, không ghi cố định vào JAR.

## 7. Các task được tạo từ source set

Java plugin tạo task dựa trên source set. Với source set `main` và `test`, những task thường gặp gồm:

| Task | Vai trò |
|---|---|
| `compileJava` | Biên dịch Java source của `main`. |
| `processResources` | Xử lý resource của `main`. |
| `classes` | Chuẩn bị output mã và resource của `main`. |
| `compileTestJava` | Biên dịch Java source của `test`. |
| `processTestResources` | Xử lý resource của `test`. |
| `testClasses` | Chuẩn bị output mã và resource của `test`. |
| `test` | Chạy test trên output và test runtime classpath. |
| `jar` | Đóng gói output của `main` thành JAR. |

Quan hệ khái quát:

```text
classes
├── compileJava
└── processResources

testClasses
├── compileTestJava
└── processTestResources

test
└── testClasses

jar
└── classes
```

Mã test thường được biên dịch với output của `main` và dependency test trên compile classpath. Khi chạy test, test runtime classpath có output của main, output của test và dependency runtime cần thiết. Task graph thực tế còn có thể bao gồm task khác do plugin hoặc cấu hình bổ sung.

## 8. Cấu hình source set riêng cho integration test

Unit test và integration test có thể cần thư mục, dependency và môi trường chạy khác nhau. Khi đó, dự án có thể tạo source set `integrationTest`.

Ví dụ Groovy DSL:

```groovy
plugins {
    id 'java'
}

sourceSets {
    integrationTest {
        java.srcDir 'src/integrationTest/java'
        resources.srcDir 'src/integrationTest/resources'

        compileClasspath += sourceSets.main.output + configurations.testRuntimeClasspath
        runtimeClasspath += output + compileClasspath
    }
}

configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.register('integrationTest', Test) {
    description = 'Runs integration tests.'
    group = 'verification'
    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    shouldRunAfter tasks.named('test')
}
```

Java plugin tạo các configuration và task cơ bản cho source set mới. Cấu hình trên bổ sung output của main và test dependencies vào classpath của integration test, đồng thời tạo task kiểu `Test` để thực thi test classes của source set đó.

Nếu integration test cần database, container hoặc dịch vụ bên ngoài, task còn cần thiết lập và dọn môi trường phù hợp. `shouldRunAfter` chỉ đặt thứ tự khi cả hai task đã được lên lịch; nó không tự động làm `check` chạy integration test. Muốn đưa integration test vào `check`, có thể khai báo:

```groovy
tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

Chỉ kết nối integration test vào `check` nếu đó là chính sách build mong muốn, vì việc này có thể làm build thường ngày cần nhiều dịch vụ hơn và chạy lâu hơn.

## 9. Mã nguồn được sinh tự động

Một số dự án sinh Java source từ OpenAPI, Protocol Buffers, schema, annotation processor hoặc công cụ nội bộ. Mã sinh nên được đặt trong thư mục output do build tool quản lý, ví dụ:

```text
build/generated/sources/
```

Không nên đặt output generator vào `src/main/java` nếu nó được tạo lại mỗi lần build. Thư mục `src/` thường chứa đầu vào được quản lý bằng Git; thư mục `build/` chứa kết quả có thể tái tạo.

### 9.1. Đăng ký generated source directory

Ví dụ khái quát:

```groovy
def generatedSourcesDir = layout.buildDirectory.dir('generated/sources/example/main')

tasks.register('generateExampleSources') {
    outputs.dir(generatedSourcesDir)

    doLast {
        def outputDir = generatedSourcesDir.get().asFile
        def packageDir = new File(outputDir, 'com/example/generated')
        packageDir.mkdirs()
        new File(packageDir, 'GeneratedInfo.java').text = '''
package com.example.generated;

public class GeneratedInfo {
    public static String value() { return "generated"; }
}
'''
    }
}

sourceSets {
    main {
        java.srcDir(generatedSourcesDir)
    }
}

tasks.named('compileJava') {
    dependsOn tasks.named('generateExampleSources')
}
```

Đây là ví dụ minh họa mối liên hệ giữa generator và compiler. Trong dự án thực tế, nên dùng plugin generator chuyên dụng hoặc task type có khai báo input/output rõ ràng để Gradle theo dõi incremental build và cache chính xác.

Điểm quan trọng là `compileJava` phải chạy sau khi source được sinh ra. Nếu chỉ thêm một thư mục output vào source set mà không khai báo quan hệ task phù hợp, compiler có thể chạy trước generator hoặc không nhận được dependency dữ liệu cần thiết.

### 9.2. Generated resource

Generator cũng có thể tạo resource như JSON, YAML hoặc schema. Khi đó, đăng ký output directory vào resource roots của source set tương ứng và kết nối task generator với task xử lý resource.

Ví dụ khái quát:

```groovy
def generatedResourcesDir = layout.buildDirectory.dir('generated/resources/main')

sourceSets {
    main {
        resources.srcDir(generatedResourcesDir)
    }
}
```

Task tạo resource cần khai báo output directory và được kết nối trước `processResources`. Nếu dùng plugin generator, ưu tiên API tích hợp của plugin vì nó thường thiết lập task dependency và output provider sẵn.

## 10. Maven: cấu hình source và resource roots

Maven dùng `pom.xml` để cấu hình source directory và resource directory. Các đường dẫn mặc định là:

```text
src/main/java
src/main/resources
src/test/java
src/test/resources
```

### 10.1. Thay source directories mặc định

Nếu dự án cũ dùng thư mục khác, có thể cấu hình:

```xml
<build>
    <sourceDirectory>legacy/java</sourceDirectory>
    <testSourceDirectory>legacy/test</testSourceDirectory>
</build>
```

Các đường dẫn được tính tương đối với thư mục project chứa POM. Cấu hình này thay source directory chính và test source directory mặc định.

Maven core chỉ có một source directory chính và một test source directory tiêu chuẩn trong cấu hình cơ bản. Nếu cần thêm nhiều source roots, thường dùng plugin như `build-helper-maven-plugin` hoặc plugin chuyên dụng của generator.

### 10.2. Cấu hình resource directories

Trong POM:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
        </resource>
        <resource>
            <directory>config/resources</directory>
        </resource>
    </resources>

    <testResources>
        <testResource>
            <directory>src/test/resources</directory>
        </testResource>
        <testResource>
            <directory>test-data</directory>
        </testResource>
    </testResources>
</build>
```

Mỗi phần tử `<resource>` hoặc `<testResource>` khai báo một resource root. Maven copy resource chính vào `target/classes` và resource test vào `target/test-classes` theo cấu hình tương ứng.

Nếu khai báo `<resources>` hoặc `<testResources>`, hãy liệt kê tất cả thư mục cần giữ lại. Đừng vô tình bỏ thư mục mặc định khi chỉ muốn bổ sung một resource root.

### 10.3. Include và exclude trong Maven resources

Maven cho phép giới hạn tệp được copy:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <includes>
            <include>**/*.yml</include>
            <include>**/*.properties</include>
        </includes>
        <excludes>
            <exclude>**/*.local.yml</exclude>
        </excludes>
    </resource>
</resources>
```

Tương tự, có thể cấu hình `<includes>` và `<excludes>` trong `<testResource>`. Hãy bảo đảm tệp cần thiết cho runtime không bị lọc mất. Resource không được compiler kiểm tra nên thiếu tệp có thể chỉ xuất hiện khi ứng dụng khởi động hoặc khi test chạy.

### 10.4. Resource filtering trong Maven

Maven hỗ trợ filtering để thay property trong resource:

```xml
<properties>
    <app.version>${project.version}</app.version>
</properties>

<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
        <resource>
            <directory>src/main/filtered-resources</directory>
            <filtering>true</filtering>
            <includes>
                <include>**/application.properties</include>
            </includes>
        </resource>
    </resources>
</build>
```

Tệp được filtering có thể chứa:

```properties
application.version=${app.version}
```

Maven thay placeholder bằng property tương ứng. Chỉ bật filtering cho tệp template có chủ đích. Tệp nhị phân như ảnh, font hoặc archive không nên bị xử lý như văn bản. Cần cẩn thận với cú pháp placeholder của framework hoặc script vì Maven filtering có thể thay nội dung ngoài ý muốn.

Không dùng resource filtering để đóng gói mật khẩu hoặc token vào JAR. Credentials cần được cung cấp ở runtime hoặc qua secret management của môi trường triển khai.

### 10.5. Thêm source root bằng build-helper-maven-plugin

Nếu Maven project cần thêm Java source directory, có thể dùng Build Helper Maven Plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.codehaus.mojo</groupId>
            <artifactId>build-helper-maven-plugin</artifactId>
            <version>3.6.0</version>
            <executions>
                <execution>
                    <id>add-extra-source</id>
                    <phase>generate-sources</phase>
                    <goals>
                        <goal>add-source</goal>
                    </goals>
                    <configuration>
                        <sources>
                            <source>src/shared/java</source>
                        </sources>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Goal `add-source` đăng ký thêm source root trong Maven project model cho các phase sau. Với test source, plugin cũng có goal tương ứng `add-test-source`, thường gắn vào `generate-test-sources`.

Nếu mã nguồn được sinh bởi generator, hãy dùng plugin generator hoặc task Maven phù hợp để tạo output trước `compile`, rồi đăng ký generated source root. Tránh chỉnh sửa thủ công tệp đã sinh vì lần build sau có thể ghi đè.

## 11. So sánh cấu hình Gradle và Maven

| Nhu cầu | Gradle Java plugin | Maven |
|---|---|---|
| Source chính mặc định | `src/main/java` | `src/main/java` |
| Resource chính mặc định | `src/main/resources` | `src/main/resources` |
| Source test mặc định | `src/test/java` | `src/test/java` |
| Resource test mặc định | `src/test/resources` | `src/test/resources` |
| Thêm Java source root | `sourceSets.main.java.srcDir(...)` | `build-helper-maven-plugin:add-source` |
| Thêm resource root | `sourceSets.main.resources.srcDir(...)` | Thêm `<resource><directory>...` |
| Lọc source/resource | `include`, `exclude`, task copy configuration | `<includes>`, `<excludes>`, resource filtering |
| Output chính | Thường `build/classes`, `build/resources` | Thường `target/classes` |
| Output test | Thường `build/classes/java/test`, `build/resources/test` | Thường `target/test-classes` |

Hai công cụ có quy ước thư mục gần nhau nhưng cách mở rộng khác nhau. Gradle biểu diễn mã và resource bằng source set cùng task; Maven dùng các thư mục chuẩn trong project model và plugin gắn với lifecycle phase.

## 12. Tổ chức source set trong dự án nhiều module

Trong Gradle multi-project build, mỗi project con có source set riêng. Ví dụ:

```text
shop/
├── settings.gradle
├── app/
│   ├── build.gradle
│   └── src/
│       ├── main/java/
│       └── main/resources/
├── domain/
│   ├── build.gradle
│   └── src/
│       ├── main/java/
│       └── test/java/
└── infrastructure/
    ├── build.gradle
    └── src/
        ├── main/java/
        └── main/resources/
```

Source root `domain/src/main/java` thuộc source set `main` của project `:domain`. Nó không tự động trở thành source root của project `:app`. Nếu `app` phụ thuộc `domain`, Gradle sử dụng project dependency để đưa output của domain vào classpath theo variant phù hợp.

Trong Maven multi-module project, mỗi module có POM và thư mục `src` riêng. Các đường dẫn resource/source trong POM thường được tính tương đối với thư mục module chứa POM đó.

## 13. Annotation processor không phải resource directory

Annotation processor là chương trình chạy trong quá trình biên dịch để phân tích annotation và có thể sinh mã nguồn hoặc resource. Nó được cấu hình trên processor path, ví dụ Gradle dùng configuration `annotationProcessor` hoặc `testAnnotationProcessor`.

```groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.34'
    annotationProcessor 'org.projectlombok:lombok:1.18.34'

    testCompileOnly 'org.projectlombok:lombok:1.18.34'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.34'
}
```

Annotation processor không được thêm vào `src/main/resources` và không phải plugin Gradle chỉ vì nó chạy trong lúc build. Nó là dependency riêng của compiler process. Nếu processor sinh mã, cần để build tool và compiler tích hợp output directory vào quá trình compile theo cơ chế tương ứng.

## 14. IDE và build tool cần cùng hiểu source roots

IDE thường đọc Gradle/Maven project model để xác định:

- Thư mục nào là mã chính, mã test hoặc generated source.
- Thư mục nào là resource.
- Dependency nào nằm trên compile hoặc runtime classpath.
- Output nào thuộc từng source set/module.

Nếu thay đổi `sourceSets` hoặc POM, hãy đồng bộ lại project trong IDE. Một thư mục được đánh dấu thủ công là source root trong IDE không có nghĩa Gradle hoặc Maven sẽ tự động biên dịch thư mục đó trên terminal/CI.

Khi kết quả IDE và command line khác nhau, chạy lệnh wrapper của dự án để xác nhận build model:

```bash
./gradlew clean build
```

hoặc:

```bash
./mvnw clean verify
```

IDE nên phản ánh cấu hình đã lưu trong build script hoặc POM, để mọi thành viên và CI dùng chung một quy tắc.

## 15. Lỗi thường gặp khi cấu hình source và resource

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra hoặc sửa |
|---|---|---|
| Tệp `.java` có trong repository nhưng không được biên dịch | Thư mục chưa được khai báo là source root hoặc bị `exclude`. | Kiểm tra `sourceSets`/Maven source directory và include/exclude. |
| Package Java không khớp thư mục | Source root đặt sai cấp thư mục. | Xác định lại root package và vị trí khai báo `package`. |
| Ứng dụng không tìm thấy YAML/properties | Resource root chưa được khai báo hoặc resource bị lọc mất. | Kiểm tra `processResources`, `<resources>` và đường dẫn classpath trong JAR. |
| Resource có trên máy nhưng thiếu trong JAR | Tệp nằm ngoài resource roots hoặc bị exclude. | Kiểm tra nội dung output và dùng `jar tf` để xem archive. |
| Test không đọc được dữ liệu JSON | Tệp nằm trong resource root chính hoặc thư mục chưa thuộc test resources. | Đặt vào `src/test/resources` hoặc cấu hình test resource root. |
| Tài nguyên test xuất hiện trong JAR production | Resource bị đặt trong source set `main`. | Chuyển sang `test` resource root và kiểm tra task đóng gói. |
| Mã sinh không được compiler nhận diện | Generator chưa chạy hoặc output directory chưa được đăng ký/đặt quan hệ task. | Kết nối generator với `compileJava`/`processResources` và khai báo output. |
| Build bị lỗi sau `clean` | Dự án phụ thuộc vào generated file cũ hoặc output bị đặt nhầm làm source đầu vào. | Đảm bảo generator có thể tạo lại mọi output từ đầu vào được quản lý. |
| Resource filtering làm hỏng JavaScript/template | Filtering áp dụng lên tệp có cú pháp placeholder riêng. | Chỉ filter đúng tệp văn bản cần thay thế; tách resource filtered và unfiltered. |
| IDE nhận source root nhưng CI không nhận | Đánh dấu source root chỉ tồn tại trong cấu hình IDE cục bộ. | Khai báo trong build script/POM và đồng bộ lại IDE. |

Một lỗi dễ bỏ sót là nhầm đường dẫn tệp vật lý với đường dẫn classpath. Ví dụ `src/main/resources/config/app.yml` thường được copy thành `config/app.yml` trong JAR. Khi ứng dụng đọc bằng classloader, nó cần dùng đường dẫn tương đối với classpath root.

## 16. Cách kiểm tra cấu hình source và resource

### 16.1. Kiểm tra với Gradle

Các lệnh sau giúp xem task và kết quả build:

```bash
# Xem task có trong project
./gradlew tasks --all

# Chạy riêng các bước biên dịch và xử lý resource
./gradlew compileJava processResources

# Kiểm tra test source và test resource
./gradlew testClasses

# Build sạch để phát hiện phụ thuộc vào output cũ
./gradlew clean build
```

Có thể kiểm tra JAR:

```bash
jar tf build/libs/my-project.jar
```

Hãy xác nhận các `.class` và resource mong đợi xuất hiện đúng đường dẫn. Tên JAR thực tế phụ thuộc project name, version và cấu hình archive.

### 16.2. Kiểm tra với Maven

```bash
# Chạy đến bước compile mã chính
./mvnw compile

# Biên dịch và chạy test
./mvnw test

# Tạo artifact sau khi chạy các phase trước
./mvnw package

# Build từ output sạch đến bước xác minh
./mvnw clean verify
```

Kiểm tra nội dung JAR:

```bash
jar tf target/my-project-1.0.jar
```

Nếu resource thiếu, kiểm tra `<resources>`, `<includes>`, `<excludes>` và `filtering`. Nếu source không được biên dịch, kiểm tra `<sourceDirectory>`, `<testSourceDirectory>` và plugin đã thêm source root.

## 17. Nguyên tắc thiết kế cấu hình source và resource

Khi tạo hoặc điều chỉnh dự án, hãy áp dụng các nguyên tắc sau:

1. **Ưu tiên cấu trúc mặc định.** Dùng `src/main/java`, `src/main/resources`, `src/test/java` và `src/test/resources` khi không có yêu cầu đặc biệt.
2. **Tách main và test.** Mã và dữ liệu kiểm thử không nên đi vào artifact production.
3. **Tách source và resource.** Java compiler xử lý source; task resource copy xử lý tệp cần có trên classpath.
4. **Bổ sung thư mục bằng API rõ ràng.** Dùng `srcDir` khi muốn thêm; chỉ gán `srcDirs` khi muốn thay thế toàn bộ danh sách.
5. **Lọc có chủ đích.** Include/exclude quá rộng có thể làm thiếu mã hoặc tài nguyên mà compiler không phát hiện.
6. **Đặt generated output trong thư mục build.** Giữ source do con người duy trì trong source control và để generator tạo lại output.
7. **Khai báo quan hệ task.** Compiler và resource processing phải chờ generator hoàn thành khi chúng sử dụng output của generator.
8. **Không đóng gói secret.** Filtering chỉ nên thay giá trị không nhạy cảm cần thiết cho artifact; credentials phải được cung cấp an toàn ở runtime.
9. **Đồng bộ IDE từ build model.** Cấu hình chính thức nằm trong Gradle/Maven, để terminal và CI có cùng hiểu biết.
10. **Kiểm tra sau clean.** Một build sạch giúp phát hiện tệp sinh cũ, source root sai và output phụ thuộc vào máy cá nhân.

## 18. Ví dụ tổng hợp

Giả sử một ứng dụng Java có cấu trúc:

```text
shop-app/
├── build.gradle
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   └── test/
│       ├── java/
│       └── resources/
├── src-shared/
│   └── java/
├── config/
│   └── resources/
└── generated-input/
```

Project cần biên dịch thêm `src-shared/java`, nạp resource từ `config/resources` và chỉ đưa các tệp cấu hình YAML cùng properties vào artifact. Build script có thể viết:

```groovy
plugins {
    id 'java'
}

sourceSets {
    main {
        java {
            srcDir 'src-shared/java'
        }
        resources {
            srcDir 'config/resources'
        }
    }
}

tasks.named('processResources') {
    include '**/*.yml', '**/*.yaml', '**/*.properties'
}
```

Sau cấu hình, Gradle biên dịch Java từ `src/main/java` và `src-shared/java`. Resource chính được lấy từ `src/main/resources` và `config/resources`, sau đó chỉ các loại tệp được include mới được xử lý. Test vẫn sử dụng source roots và resource roots mặc định.

Hãy chạy `./gradlew clean build`, kiểm tra output và liệt kê nội dung JAR. Nếu một tệp resource không xuất hiện, xác định nó nằm trong root nào và có khớp include pattern không. Nếu một lớp Java không được biên dịch, kiểm tra source root và package tương ứng.

## 19. Kết luận

Source set xác định nhóm mã nguồn, tài nguyên, classpath và output mà build tool xử lý. Với Java plugin của Gradle, `main` và `test` có các Java source roots và resource roots mặc định; có thể bổ sung hoặc thay thế chúng bằng `sourceSets`. Gradle tạo task như `compileJava`, `processResources`, `testClasses` và `jar` để biến các đầu vào đó thành output.

Maven dùng các thư mục mặc định tương tự, cho phép cấu hình source/resource directories trong POM và dùng plugin để bổ sung source roots hoặc sinh mã. Khi cần cấu trúc riêng, resource filtering hoặc generated sources, hãy khai báo rõ đầu vào, output và thứ tự task/phase. Kiểm tra bằng wrapper sau `clean` để bảo đảm IDE, terminal và CI cùng xử lý đúng mã nguồn và tài nguyên của dự án.
