# Gọi Ant từ Maven hoặc Gradle trong giai đoạn chuyển tiếp

Khi một dự án Java đang dùng Apache Ant chuyển sang Maven hoặc Gradle, việc viết lại toàn bộ `build.xml` trong một lần thường có rủi ro: những target cũ có thể đang sinh mã nguồn, chuyển đổi tài nguyên, ký gói, gọi công cụ nội bộ hoặc chuẩn bị dữ liệu mà bản dựng mới chưa thay thế được. **Gọi Ant từ Maven hoặc Gradle** là cách giữ các bước cần thiết vẫn hoạt động trong lúc dần chuyển quyền điều phối sang công cụ mới.

Mục tiêu của giai đoạn này là để **Maven/Gradle làm điểm vào chính của bản dựng**, còn Ant chỉ thực hiện các target legacy đã được xác định rõ. Từng target Ant cần biết đầu vào, đầu ra, thứ tự thực thi và điều kiện thất bại. Khi hành vi tương đương đã được thay thế bằng task/plugin mới, có thể gỡ bỏ điểm gọi Ant đó mà không làm gián đoạn toàn bộ quy trình.

Bài này trình bày hai cách tích hợp thực tế: **`maven-antrun-plugin` trong Maven** và **`AntBuilder` trong Gradle**, cách truyền property và chuyển đầu ra vào lifecycle, cùng các vấn đề classpath, lỗi, CI và kế hoạch rút dần Ant.

## 1. Hiểu ranh giới giữa Ant, Maven và Gradle

Ba hệ thống đều có thể chạy công việc build, nhưng cách tổ chức khác nhau:

| Công cụ | Đơn vị tổ chức chủ yếu | Cách xác định thứ tự | Vai trò trong giai đoạn chuyển đổi |
|---|---|---|---|
| Apache Ant | `target` chứa các `task` | `depends` và lệnh chọn target | Giữ hành vi legacy chưa chuyển đổi |
| Maven | `plugin goal` gắn với `lifecycle phase` | Thứ tự phase và execution của plugin | Điều phối quy trình chuẩn hóa theo Maven |
| Gradle | `task` trong task graph | `dependsOn`, task inputs/outputs và quan hệ tác vụ | Điều phối build theo task graph, tích hợp Ant khi cần |

Ví dụ, Ant có target `generate-resources`; bản dựng Maven cần chạy nó trong phase `generate-resources`, còn Gradle cần một task như `legacyGenerateResources` được kết nối làm dependency của `processResources`.

```text
                     Lựa chọn công cụ điều phối
                                 |
                   +-------------+-------------+
                   |                           |
                 Maven                       Gradle
                   |                           |
      phase generate-resources         task legacyGenerateResources
                   |                           |
          maven-antrun-plugin                AntBuilder
                   |                           |
                   +-------------+-------------+
                                 |
                      Ant target legacy
                        generate-resources
                                 |
                                 v
                      generated/legacy.properties
                                 |
                   +-------------+-------------+
                   |                           |
          Maven process-resources     Gradle processResources
                   |                           |
             Đóng gói JAR                Đóng gói JAR
```

Không phải Ant target nào cũng nên gọi từ lifecycle mới. Ưu tiên các target có **đầu ra rõ ràng và có thể chạy độc lập**, chẳng hạn tạo tài nguyên, sinh source hoặc đóng gói một asset. Những target cũ thực hiện nhiều việc trộn lẫn với nhau cần tách trách nhiệm hoặc xây dựng hợp đồng đầu vào/đầu ra trước.

## 2. Chọn kiểu tích hợp trước khi viết cấu hình

Có ba mô hình thường gặp:

| Mô hình | Cách gọi | Khi nên dùng |
|---|---|---|
| **Ant chạy trong JVM của Maven** | `maven-antrun-plugin`, bên trong `<target>` có thể gọi `<ant antfile="...">` | Muốn gắn target Ant vào lifecycle Maven mà không yêu cầu cài Ant CLI trên mọi máy |
| **Ant chạy trong JVM của Gradle** | `ant.ant(...)` hoặc `ant.importBuild(...)` qua `AntBuilder` | Muốn sử dụng target/task Ant trong task graph Gradle |
| **Ant là tiến trình ngoài** | Maven plugin chạy executable hoặc Gradle `Exec` gọi script `ant` | Build legacy lệ thuộc nhiều vào Ant runtime, wrapper, `ANT_OPTS`, listener hay môi trường riêng |

Tích hợp trong JVM thường đơn giản hơn vì Maven/Gradle kiểm soát quá trình chạy. Nhưng Ant được nhúng có thể dùng **phiên bản Ant, classpath, class loader và JVM khác** với Ant CLI trước đây. Không nên suy ra hai cách chạy hoàn toàn tương đương chỉ vì cùng đọc một `build.xml`.

Gọi Ant bằng tiến trình ngoài giúp giữ gần hơn môi trường legacy nhưng đòi hỏi quản lý cách cài Ant, Java, mã thoát tiến trình, quoting và khác biệt hệ điều hành. Đây là phương án cần chọn có chủ đích, không phải bước mặc định cho mọi chuyển đổi.

## 3. Ví dụ xuyên suốt: target Ant sinh tài nguyên

Giả sử dự án đã có một `build.xml` nhỏ thực hiện việc sinh file properties dùng khi đóng gói JAR. Ta muốn giữ logic này tạm thời và gọi nó từ Maven **hoặc** Gradle.

Cấu trúc ban đầu:

```text
transition-demo/
├── legacy/
│   └── build.xml
├── src/
│   └── main/
│       └── java/
│           └── example/
│               └── App.java
├── pom.xml                # cấu hình khi chọn Maven
└── build.gradle           # cấu hình khi chọn Gradle
```

Hai file `pom.xml` và `build.gradle` được trình bày như **hai lựa chọn độc lập** để minh họa; dự án thực tế nên xác định một công cụ chính trong một lần chuyển đổi cụ thể.

Tạo file `legacy/build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="legacy-resources" default="generate-resources" basedir=".">
    <target name="generate-resources">
        <fail unless="generated.dir"
              message="Property generated.dir is required"/>

        <mkdir dir="${generated.dir}"/>

        <echo file="${generated.dir}/legacy.properties"
              encoding="UTF-8"
              message="generated.by=ant"/>
    </target>
</project>
```

Ý nghĩa:

- Target `generate-resources` chỉ tạo một file, không biết Maven hay Gradle đang gọi.
- Property `generated.dir` **bắt buộc**, do công cụ gọi Ant truyền vào.
- Bản dựng legacy tự tạo thư mục đầu ra khi cần.
- File `legacy.properties` chứa thông tin công khai để quan sát kết quả; ví dụ không cần secret hay dịch vụ ngoài.

Có thể tạo `src/main/java/example/App.java` nếu muốn kiểm tra JAR với source tối thiểu:

```java
package example;

public class App {
    public static void main(String[] args) {
        System.out.println("Transition build");
    }
}
```

Trong ví dụ này, Java source không cần dùng `legacy.properties` tại runtime. File được sinh nhằm minh họa **kết nối đầu ra Ant vào quá trình đóng gói**; sau khi build, nó phải xuất hiện trên classpath tài nguyên của JAR.

### 3.1. Kiểm tra hợp đồng khi chạy Ant trực tiếp

Nếu đã cài Ant CLI và đang đứng tại thư mục `transition-demo`:

```bash
ant -f legacy/build.xml \
    -Dgenerated.dir=../build/manual-legacy \
    generate-resources
```

Vì `basedir` của Ant project này là thư mục `legacy`, giá trị tương đối `../build/manual-legacy` đưa kết quả về `transition-demo/build/manual-legacy`. Để tránh phụ thuộc vào cách phân giải tương đối trong ứng dụng thật, khi gọi từ Maven/Gradle ta sẽ truyền **đường dẫn tuyệt đối** tới thư mục đầu ra.

Trên Windows, có thể nhập cùng lệnh thành một dòng:

```text
ant -f legacy/build.xml -Dgenerated.dir=../build/manual-legacy generate-resources
```

Nếu bỏ `-Dgenerated.dir=...`, Ant dừng ở `<fail>` với thông báo property bắt buộc. Đây là cách thiết kế tốt: **target không âm thầm ghi file vào một vị trí ngẫu nhiên** khi chưa được cấu hình.

## 4. Gọi Ant từ Maven bằng `maven-antrun-plugin`

Maven không tự hiểu các `target` trong `build.xml`. Plugin `org.apache.maven.plugins:maven-antrun-plugin` cho phép chạy task Ant trong một Maven execution. Có thể dùng task `<ant>` bên trong cấu hình plugin để thực thi một target từ buildfile legacy.

Ví dụ `pom.xml` tối thiểu, với packaging `jar`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>transition-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
            </resource>
            <resource>
                <directory>${project.build.directory}/generated-resources/legacy</directory>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.2.0</version>
                <executions>
                    <execution>
                        <id>generate-legacy-resources</id>
                        <phase>generate-resources</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <ant antfile="${project.basedir}/legacy/build.xml"
                                     target="generate-resources"
                                     inheritAll="false">
                                    <property name="generated.dir"
                                              location="${project.build.directory}/generated-resources/legacy"/>
                                </ant>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Trong POM trên:

1. `maven-antrun-plugin` được gắn với phase `generate-resources`.
2. Khi đến phase này, Maven chạy goal `antrun:run` và xử lý `<target>` được khai báo trong cấu hình plugin.
3. Ant task `<ant>` mở `legacy/build.xml` và gọi target `generate-resources`.
4. Property `generated.dir` được truyền tường minh dưới dạng đường dẫn do Maven quản lý, trong `target/generated-resources/legacy`.
5. Phase `process-resources` về sau lấy thêm thư mục tài nguyên được sinh thông qua phần `<resources>` và đưa nội dung vào `target/classes`; khi đóng JAR, file sẽ được đưa vào artifact.

Sơ đồ thứ tự:

```text
mvn package
    |
    v
generate-resources
    |-- maven-antrun-plugin:run
    |       |
    |       +-- legacy/build.xml : generate-resources
    |               |
    |               +-- target/generated-resources/legacy/legacy.properties
    |
    v
process-resources
    |-- copy generated resources -> target/classes
    |
    v
compile / test / package
    |
    v
target/transition-demo-1.0.0-SNAPSHOT.jar
```

Trong Maven 3.x và plugin Antrun hiện đại, phần chứa task Ant là `<target>`. Những cấu hình Antrun rất cũ dùng `<tasks>` có thể không còn phù hợp; khi nâng plugin, hãy điều chỉnh theo schema của version được chọn.

### 4.1. Chạy đúng phase và kiểm tra đầu ra

Từ thư mục chứa `pom.xml`:

```bash
mvn generate-resources
```

Lệnh này chạy tới phase `generate-resources` và tạo `target/generated-resources/legacy/legacy.properties`. Nó **chưa** thực hiện phase `process-resources`, nên chưa cần kỳ vọng file đã nằm trong `target/classes`.

Để chạy toàn bộ đến bước đóng gói:

```bash
mvn clean package
```

Sau khi thành công, file tài nguyên được sinh sẽ hiện diện trong `target/classes/legacy.properties` và nằm ở gốc JAR. Có thể dùng JDK để xem danh sách:

```bash
jar tf target/transition-demo-1.0.0-SNAPSHOT.jar
```

Đầu ra danh sách cần có `legacy.properties` bên cạnh các class/resource khác được đóng gói.

### 4.2. Vì sao không nên gắn target tạo tài nguyên vào phase `package`?

Nếu Ant sinh file trong phase `package`, Maven đã đi qua `process-resources` trước đó; file có thể không được copy vào `target/classes` của cùng lượt build. Kết quả là Ant báo sinh file thành công nhưng JAR không chứa tài nguyên mới.

Chọn phase theo **đầu ra mà target tạo**:

| Ant target legacy làm gì? | Điểm gắn Maven thường phù hợp | Lý do |
|---|---|---|
| Sinh Java source | `generate-sources` | Đầu ra có thể được khai báo là source root trước phase compile |
| Sinh tài nguyên ứng dụng | `generate-resources` | Chạy trước `process-resources` |
| Chuẩn bị tài nguyên kiểm thử | `generate-test-resources` | Chạy trước `process-test-resources` |
| Kiểm tra artifact cuối | `verify` | Thực hiện sau các phase đóng gói và kiểm thử thông thường |
| Công bố artifact | Quy trình deploy/release được định nghĩa rõ | Tránh tự động phát hành trong mỗi lượt package |

Chỉ chạy Ant target trong phase nào khi hệ quả của nó phù hợp thứ tự lifecycle đó. Một target sinh source cần **đăng ký thư mục generated source** với Maven (ví dụ qua `build-helper-maven-plugin` hoặc plugin có hỗ trợ), chứ việc tạo file `.java` tự nó chưa bảo đảm Maven compiler nhìn thấy file.

### 4.3. Truyền property có kiểm soát

Cú pháp bên trong `<ant>`:

```xml
<ant antfile="${project.basedir}/legacy/build.xml"
     target="generate-resources"
     inheritAll="false">
    <property name="generated.dir"
              location="${project.build.directory}/generated-resources/legacy"/>
</ant>
```

`inheritAll="false"` giảm việc truyền toàn bộ các property có thể kế thừa từ Ant project gọi sang Ant project con. Những property được khai báo bằng phần tử `<property>` ở đây được truyền rõ ràng. Một số property hệ thống hoặc user property vẫn có quy tắc ưu tiên riêng theo Ant; đừng coi `inheritAll="false"` là môi trường cô lập bảo mật tuyệt đối.

Nếu target Ant cần thêm cấu hình không nhạy cảm, truyền tên và giá trị có ý nghĩa nghiệp vụ, ví dụ:

```xml
<property name="release.channel" value="snapshot"/>
```

Với đường dẫn, dùng `location` để Ant biểu diễn đường dẫn phù hợp. Tránh nối trực tiếp `target/generated...` với separator cố định hoặc buộc target legacy đoán working directory của Maven.

Không đưa token phát hành, mật khẩu hay private key vào POM hoặc property dòng lệnh `mvn -D...`; nếu bước Ant phải gọi dịch vụ có xác thực, để công cụ chuyên trách nhận credential từ môi trường được cấp quyền hoặc secret manager.

## 5. Gọi Ant từ Gradle bằng `AntBuilder`

Gradle có đối tượng `ant` cho phép chạy các task Ant. Trong build script Groovy DSL, có thể gọi task Ant tên `ant` (nghĩa là thực thi một Ant buildfile khác) bằng cú pháp `ant.ant(...)`.

Dùng lại `legacy/build.xml` ở mục 3. Với dự án dùng Java plugin, file `build.gradle`:

```groovy
plugins {
    id 'java'
}

def generatedLegacyResources = layout.buildDirectory.dir('generated/legacy-resources')

tasks.register('legacyGenerateResources') {
    inputs.file(layout.projectDirectory.file('legacy/build.xml'))
    outputs.dir(generatedLegacyResources)

    doLast {
        ant.ant(
            antfile: file('legacy/build.xml'),
            target: 'generate-resources',
            inheritAll: false
        ) {
            property(
                name: 'generated.dir',
                location: generatedLegacyResources.get().asFile.absolutePath
            )
        }
    }
}

tasks.named('processResources') {
    dependsOn(tasks.named('legacyGenerateResources'))
    from(generatedLegacyResources)
}
```

Ý nghĩa từng phần:

- `tasks.register('legacyGenerateResources')` tạo Gradle task đại diện cho hành vi legacy; task này không chạy ở thời điểm khai báo build script.
- `doLast { ... }` chỉ gọi Ant khi Gradle thực thi task đó.
- `ant.ant(...)` gọi Ant task `<ant>` để chạy `legacy/build.xml`, target `generate-resources`.
- `generatedLegacyResources` là đường dẫn đầu ra do Gradle quản lý, thường tương ứng `build/generated/legacy-resources`.
- `inputs.file(...)` và `outputs.dir(...)` cho Gradle biết input buildfile và output directory của task.
- `processResources` phụ thuộc task legacy và lấy thêm các file được sinh để đóng gói vào JAR.

Bên trong Groovy DSL, `ant.ant` không phải lỗi gõ lặp: `ant` thứ nhất là đối tượng `AntBuilder` của Gradle, còn `ant(...)` thứ hai là tên task Ant gọi dự án Ant con.

### 5.1. Chạy task legacy và lifecycle Gradle

Từ thư mục dự án:

```bash
./gradlew legacyGenerateResources
```

Trên Windows:

```powershell
.\gradlew.bat legacyGenerateResources
```

Giả sử repository có Gradle Wrapper, các lệnh trên dùng bản Gradle được wrapper cố định. Nếu không có wrapper, dùng lệnh `gradle legacyGenerateResources` từ bản Gradle đã cài đặt và ghi rõ phiên bản dùng để tái hiện.

Để đóng gói qua Gradle Java plugin:

```bash
./gradlew clean build
```

Vì `processResources` có dependency tới `legacyGenerateResources`, Gradle sẽ chạy Ant target trước bước sao chép tài nguyên vào output. JAR thường được tạo trong `build/libs`. Có thể dùng `jar tf` trên tệp JAR tương ứng để tìm `legacy.properties`.

Chuỗi phụ thuộc dự kiến:

```text
legacyGenerateResources
         |
         v
   processResources
         |
         v
       classes
         |
         v
        jar / build
```

`processResources` là task `Copy` do Java plugin cung cấp. Nếu dự án không áp dụng plugin đó, tên task và cách tích hợp output sẽ khác; khi ấy cần kết nối task Ant với đúng consumer trong dự án thay vì dùng nguyên cấu hình mẫu.

### 5.2. Khai báo đầu vào/đầu ra để Gradle hiểu công việc

Ở ví dụ đơn giản, output chỉ phụ thuộc vào nội dung `legacy/build.xml` và property output directory, nên `inputs.file` + `outputs.dir` minh họa hợp đồng cơ bản.

Dự án thực tế thường có template, source, JAR, file cấu hình hoặc tham số khác. Cần khai báo thêm **đúng những đầu vào ảnh hưởng đến output**, ví dụ:

```groovy
tasks.register('legacyGenerateResources') {
    inputs.file(layout.projectDirectory.file('legacy/build.xml'))
    inputs.files(fileTree('legacy/templates'))
    inputs.property('releaseChannel', 'snapshot')
    outputs.dir(layout.buildDirectory.dir('generated/legacy-resources'))

    doLast {
        // Gọi Ant với cùng tập input và property đã khai báo ở trên.
    }
}
```

Không chỉ khai báo `outputs.dir` rồi cho rằng Gradle sẽ tự biết mọi tệp Ant đọc. Nếu thiếu `inputs`, Gradle có thể đánh giá task là up-to-date dù template hoặc dependency legacy đã thay đổi. Đối với task có tác dụng phụ như upload, gọi API hoặc ghi vào vị trí bên ngoài project, **không khai báo giả một output directory để ép up-to-date**; cần thiết kế hành vi theo đúng semantics tác vụ đó.

Gradle có thể bỏ qua task khi mọi điều kiện cập nhật được đáp ứng; Maven plugin execution lại có lifecycle và chính sách thực thi riêng. Không nên giả định hai công cụ có cơ chế incremental giống nhau.

### 5.3. Gọi một target hay import nhiều target?

Ngoài `ant.ant(...)`, Gradle hỗ trợ `ant.importBuild(...)` để import các target Ant thành Gradle task. Cách này hữu ích khi quá trình chuyển đổi cần chạy nhiều target legacy độc lập:

```groovy
ant.importBuild('legacy/build.xml') { antTargetName ->
    'legacy_' + antTargetName
}
```

Ví dụ target Ant tên `generate-resources` có thể được ánh xạ thành task Gradle `legacy_generate-resources`. Hàm đổi tên giúp tránh trùng với task của plugin Gradle.

Hai cách có phạm vi khác nhau:

| `ant.ant(...)` trong task Gradle | `ant.importBuild(...)` |
|---|---|
| Chọn rõ Ant target trong task bạn định nghĩa | Biến nhiều Ant target thành các task Gradle |
| Dễ khai báo inputs/outputs trên wrapper task | Cần kiểm tra mapping, dependencies và task metadata sau import |
| Hạn chế số target legacy xuất hiện trong Gradle task graph | Phù hợp giai đoạn cần tiếp cận nhiều target cũ |
| Thích hợp khi muốn di chuyển từng bước | Hữu ích khi giữ cấu trúc Ant lâu hơn trong thời gian chuyển đổi |

Không cần dùng cả hai cơ chế để gọi cùng một target trong cùng lượt build; điều đó có thể khiến output được tạo hai lần và khó xác định ai là chủ sở hữu.

## 6. So sánh Maven Antrun và Gradle AntBuilder

| Tiêu chí | Maven Antrun | Gradle AntBuilder |
|---|---|---|
| Điểm tích hợp | Plugin execution gắn Maven phase | Gradle task có `doLast` hoặc import Ant target |
| Cú pháp chính | POM XML, `maven-antrun-plugin:run` | Groovy DSL/Kotlin DSL, AntBuilder |
| Gọi buildfile | Ant `<ant antfile="...">` trong `<target>` | `ant.ant(antfile: ..., target: ...)` |
| Thứ tự | Lifecycle phase và thứ tự plugin executions | Task graph, `dependsOn` và quan hệ producer/consumer |
| Truyền đường dẫn | Maven property `${project.build.directory}`, nested Ant `<property location=...>` | `layout.buildDirectory`, `file(...)`, Ant `property(...)` |
| Đưa output vào tài nguyên JAR | `<build><resources>...` và `process-resources` | `processResources.from(...)` cùng `dependsOn` |
| Incremental / up-to-date | Theo cơ chế Maven/plugin; không mặc định như Gradle | Có thể khai báo inputs/outputs để Gradle theo dõi |
| Ant runtime | Ant do plugin và dependency của nó cung cấp | Ant integration do Gradle cung cấp |
| Khi di chuyển xong | Gỡ execution/plugin và tham chiếu resource nếu không còn cần | Gỡ wrapper task/import và các dependency/consumer liên quan |

Từ góc độ kiến trúc, cả hai cách đều cần giữ một nguyên tắc: **Ant target tạo đầu ra; Maven/Gradle quyết định khi nào chạy và đầu ra đó được tiêu thụ ở đâu**.

## 7. Classpath và phiên bản Ant khi tích hợp

Một lỗi rất thường gặp là target chạy thành công với lệnh:

```bash
ant -f legacy/build.xml some-target
```

nhưng thất bại khi gọi qua Maven/Gradle với `ClassNotFoundException` hoặc `taskdef class not found`.

Lý do là **Ant chạy qua các đường đi khác nhau có thể không thấy cùng một classpath**.

### 7.1. Phân biệt ba classpath

| Classpath | Phục vụ | Lưu ý |
|---|---|---|
| Classpath của Ant runtime | Tìm lớp task Ant, Ant custom task, listener | Maven Antrun và Gradle AntBuilder có runtime riêng |
| Classpath mà target dùng để biên dịch | `<javac>` tìm dependency source | Phải truyền hoặc khai báo rõ trong Ant buildfile |
| Classpath của chương trình Java được fork | `<java fork="true">` chạy ứng dụng | Không tự động giống classpath của Maven/Gradle |

Giả sử target legacy cần task tùy biến:

```xml
<taskdef name="legacyTransform"
         classname="com.example.ant.LegacyTransformTask">
    <classpath>
        <pathelement location="${legacy.lib.dir}/legacy-ant-tasks.jar"/>
    </classpath>
</taskdef>
```

Đường dẫn `legacy.lib.dir` phải được xác định và JAR phải hiện diện khi task được nạp. Trong môi trường mới, nên truyền property hoặc path cần thiết một cách tường minh thay vì dựa vào `ANT_HOME/lib` của máy phát triển.

Với Maven Antrun, thư viện dùng bởi plugin hoặc task có thể cần cấu hình dưới `<plugin><dependencies>` và/hoặc classpath cụ thể theo cách task được nạp. Với Gradle, có thể dùng dependency configuration dành cho task Ant và cung cấp path cho `taskdef`. Cơ chế của Maven project `dependencies` và Gradle Java `implementation` **không đảm bảo** tự động cấp thư viện cho mọi custom Ant task.

### 7.2. Vì sao `-lib` hoặc `ANT_OPTS` có thể không còn tác dụng?

Khi dùng Ant CLI, `-lib` thay đổi đường dẫn nạp thư viện của Ant; `ANT_OPTS` cấu hình JVM khởi chạy Ant. Nhưng Maven Antrun và Gradle AntBuilder thường chạy Ant bên trong JVM của chính công cụ điều phối, nên cấu hình từ Ant launcher riêng không được sử dụng theo cùng cách.

Nếu legacy target thật sự phụ thuộc vào hệ thống listener, JVM flag, extension hoặc bản Ant riêng, hãy ghi lại sự phụ thuộc đó rồi chọn một trong hai hướng:

1. Điều chỉnh tích hợp nhúng: khai báo dependency, property và JVM/task configuration tương thích.
2. Gọi Ant như **tiến trình ngoài** trong một giai đoạn chuyển đổi có kiểm soát.

Không thêm bừa nhiều JAR vào classpath để làm mất lỗi đầu tiên: có thể tạo xung đột phiên bản, lỗi class loader và khác biệt khó giải thích hơn.

## 8. Khi cần giữ Ant CLI như một tiến trình riêng

Trong một số hệ thống cũ, target Ant phụ thuộc script nội bộ, phiên bản JVM cụ thể hoặc task nạp từ `ANT_HOME`. Khi đó có thể tạm giữ lệnh `ant` ngoài tiến trình Maven/Gradle.

### 8.1. Mẫu Gradle `Exec`

Với môi trường Unix-like đã có lệnh `ant` trong `PATH`:

```groovy
tasks.register('legacyExternal', Exec) {
    def generatedDir = layout.buildDirectory.dir('generated/legacy-external')
    inputs.file(layout.projectDirectory.file('legacy/build.xml'))
    outputs.dir(generatedDir)

    commandLine(
        'ant',
        '-f',
        file('legacy/build.xml').absolutePath,
        '-Dgenerated.dir=' + generatedDir.get().asFile.absolutePath,
        'generate-resources'
    )
}
```

Với Windows, command executable có thể là `ant.bat`/`ant.cmd` hoặc một script được dự án kiểm soát, tùy cách cài Ant. Phần trên minh họa **đường gọi tiến trình ngoài**, không phải cấu hình chạy giống hệt trên mọi máy.

Các tham số trong `commandLine` được Gradle truyền thành danh sách đối số; không cần nối một câu lệnh dài chứa nhiều dấu nháy. Tuy nhiên, giới hạn độ dài tiến trình vẫn áp dụng và shell wrapper có thể thêm một tầng quoting.

Cần ghi version Ant/JDK và không phụ thuộc vào cài đặt tình cờ của developer machine. Nếu target tạo file trong thư mục cụ thể, bảo đảm đường dẫn output thuộc Gradle build directory và được khai báo trong outputs.

### 8.2. Maven gọi Ant CLI qua plugin thực thi

Maven có các plugin cho phép gọi executable bên ngoài (chẳng hạn `exec-maven-plugin`). Khi chọn mô hình này, cấu hình cần chỉ rõ:

- Executable hoặc script khởi động Ant.
- Ant buildfile và target.
- Đường dẫn input/output và property không nhạy cảm.
- Mã thoát khác 0 phải làm Maven build thất bại.
- Phạm vi môi trường: Java/Ant version, working directory, biến dùng cho task.

Nếu dùng Ant Antrun nhúng thì **không cần cài `ant` command trên máy**; nếu gọi `ant` qua executable thì cần. Nhầm lẫn hai mô hình dễ dẫn đến CI chạy được cục bộ nhưng thất bại trên runner mới.

## 9. Đồng bộ đường dẫn, property và môi trường giữa hai công cụ

Giai đoạn chuyển tiếp thường lộ ra các giả định cũ như “task luôn chạy ở thư mục root” hoặc “property A đã được target B tạo trước”. Nên chuyển những giả định này thành cấu hình rõ ràng.

### 9.1. Truyền đường dẫn đầu ra tuyệt đối

Ưu tiên:

- Maven: `${project.build.directory}/generated-resources/legacy`.
- Gradle: `layout.buildDirectory.dir('generated/legacy-resources')`.

Ant nhận đường dẫn qua `generated.dir`. Trong target Ant, dùng `${generated.dir}` với `mkdir` và `echo`, không tự xác định tên thư mục `target` hay `build`.

Lợi ích: Maven/Gradle có thể đổi build directory theo cấu hình riêng mà không cần sửa Ant target, và các subproject không cùng ghi vào một output path.

### 9.2. Đừng lạm dụng property toàn cục

Maven property, Gradle project property và Ant property có cơ chế đánh giá và độ ưu tiên khác nhau. Với Ant, nhiều property là bất biến sau khi được gán; property ở CLI hoặc được truyền từ parent có thể có ưu tiên cao.

Đặt tên đầy đủ và chỉ truyền giá trị cần cho target. Ví dụ `generated.dir`, `schema.input.dir`, `release.variant` rõ ràng hơn những tên ngắn dễ đụng như `dir`, `build` hoặc `path`.

Nếu một target còn cần thêm input path, nên bổ sung contract vào Ant:

```xml
<fail unless="schema.input.dir"
      message="schema.input.dir must be provided"/>
```

Việc kiểm tra explicit giúp lỗi xảy ra sớm và dễ hiểu khi Maven/Gradle chưa truyền đúng giá trị.

### 9.3. Khác biệt hệ điều hành

Ant hỗ trợ thuộc tính `location`, `<path>` và `<fileset>` để làm việc với đường dẫn linh hoạt hơn. Khi chuyển đổi, cần đặc biệt chú ý:

- Ký tự `/` và `\`, dấu phân cách classpath `:`/`;`.
- Đường dẫn có dấu cách khi gọi `<exec>` hoặc plugin chạy tiến trình.
- Script `.sh` khác `.bat`/`.cmd`.
- Phân biệt chữ hoa chữ thường của file system.
- Encoding và JDK khi sinh resource có ký tự Unicode.
- Quyền thực thi script và thứ tự các task trên CI.

Không cần biến Ant target thành chương trình kiểm tra hệ điều hành quá phức tạp. Cố gắng truyền path/argument bằng API của công cụ điều phối; chỉ đưa phần phụ thuộc nền tảng vào task thật sự cần nó.

## 10. Xử lý lỗi và bảo toàn ý nghĩa của build thất bại

Một lớp tích hợp tốt phải bảo đảm: **Ant target thất bại thì Maven/Gradle build cũng thất bại**.

Trong Ant buildfile mẫu:

```xml
<fail unless="generated.dir"
      message="Property generated.dir is required"/>
```

Nếu plugin hoặc Gradle AntBuilder gọi target mà không truyền `generated.dir`, task phát sinh `BuildException`; lớp tích hợp thông thường sẽ báo lỗi và làm build dừng.

Nếu target Ant gọi chương trình ngoài:

```xml
<exec executable="schema-generator" failonerror="true">
    <arg value="--output"/>
    <arg file="${generated.dir}"/>
</exec>
```

`failonerror="true"` yêu cầu Ant coi mã thoát lỗi của chương trình ngoài là lỗi task. Nếu thiếu thiết lập này, tùy hành vi của task và command, tiến trình con có thể thất bại mà Ant vẫn tiếp tục, làm Maven/Gradle đánh dấu build thành công giả.

Cần kiểm tra **đầu ra thực tế**, không chỉ dòng `BUILD SUCCESSFUL` hay `BUILD SUCCESS`: file sinh ra có đúng nội dung, có được copy vào artifact, có bị sinh lặp và có được xóa đúng khi clean không.

### 10.1. Thu thập log khi lỗi chỉ xảy ra ở Maven/Gradle

Lệnh thông dụng:

```bash
mvn -e package
mvn -X package
./gradlew legacyGenerateResources --stacktrace
./gradlew legacyGenerateResources --info
./gradlew legacyGenerateResources --debug
```

- `mvn -e` đưa stack trace, `mvn -X` thêm log debug Maven.
- `--stacktrace` của Gradle hiển thị stack trace khi có lỗi; `--info` và `--debug` tăng mức chi tiết.
- Cần đối chiếu lỗi đầu tiên trong Ant target và lớp integration; wrapper exception của Maven/Gradle có thể chỉ là triệu chứng bao quanh `BuildException`.

Mức debug có thể chứa property, đường dẫn nội bộ hoặc dữ liệu nhạy cảm; chỉ ghi log cần thiết và rà soát trước khi chia sẻ.

Khi một Ant target chạy được bằng CLI nhưng lỗi ở Maven/Gradle, so sánh lần lượt Ant version, JDK, classpath task, working directory, property được truyền, file đầu vào và quyền ghi. Không sửa đồng thời nhiều yếu tố; mỗi lần đổi một điều kiện để xác định nguyên nhân.

## 11. Vòng đời tài nguyên: ai tạo, ai dùng, ai xóa?

Một lỗi chuyển đổi phổ biến là **hai công cụ cùng ghi vào một thư mục** hoặc **không công cụ nào chịu trách nhiệm dọn output**.

Với ví dụ này, phân công nên rõ:

| Thành phần | Trách nhiệm |
|---|---|
| Ant target `generate-resources` | Sinh đúng `legacy.properties` vào `generated.dir` được truyền |
| Maven Antrun / Gradle wrapper task | Chạy target và truyền cấu hình |
| Maven `process-resources` / Gradle `processResources` | Đọc tài nguyên được sinh và đưa vào output của Java |
| Maven `clean` / Gradle `clean` | Dọn output dưới build directory theo quy tắc công cụ |
| Task đóng gói | Tạo JAR từ class và resource đã chuẩn bị |

Không nên để Ant tự xóa toàn bộ `target` hoặc `build` khi chạy như một bước bên trong lifecycle Maven/Gradle. Nếu Ant xóa thư mục output chung sau khi compile/test đã ghi dữ liệu, nó có thể phá hỏng phần build khác. Giới hạn thao tác của Ant trong thư mục con dành riêng cho target legacy.

Tương tự, tránh để Gradle `legacyGenerateResources` và một task native mới cùng sinh `legacy.properties` với nội dung khác nhau. Hãy chọn một chủ sở hữu cho từng đầu ra tại mỗi giai đoạn chuyển đổi.

### 11.1. Thứ tự và tính song song

Maven xác định thứ tự theo phase và execution; Gradle xây task graph dựa trên dependency. Trong Gradle, chỉ việc đưa task output vào đường dẫn được sử dụng ở nơi khác **không luôn bảo đảm** thứ tự nếu không khai báo quan hệ producer/consumer đúng. Ví dụ đã dùng `dependsOn` và `from` để thể hiện rõ hợp đồng.

Khi nhiều module cùng build song song, mỗi module nên có output directory riêng. Không ghi chung `/tmp/generated` hoặc một thư mục ngoài repository mà không có cơ chế đồng bộ phù hợp.

## 12. Kế hoạch thay thế Ant theo từng bước

Giai đoạn chuyển tiếp cần có điểm kết thúc rõ ràng. Có thể quản lý theo bảng di chuyển:

| Ant target | Tác dụng | Người tiêu thụ | Cách gọi tạm | Hướng thay thế |
|---|---|---|---|---|
| `generate-resources` | Sinh tài nguyên | Maven/Gradle resource processing | Antrun / AntBuilder | Task/plugin sinh resource native |
| `compile` | Biên dịch Java | Packaging | Chỉ giữ nếu có yêu cầu compiler đặc biệt | Maven Compiler Plugin / Gradle Java plugin |
| `test` | Chạy kiểm thử | Verify/build | Chạy legacy khi chưa chuyển suite | Surefire/Failsafe hoặc Gradle Test |
| `package-legacy` | Đóng gói custom ZIP | Release | Một target Ant riêng | Maven Assembly plugin hoặc Gradle Archive task |
| `publish` | Upload artifact | Release pipeline | Chỉ khi thực sự cần giữ thao tác cũ | Plugin/CI release có quyền hạn và retry rõ ràng |

### Giai đoạn A — Khảo sát và cô lập

Ghi lại các Ant target được sử dụng thật sự, tệp đầu vào, output, công cụ ngoài, property, classpath và side effect. Tách target có output rõ ràng khỏi target đang làm nhiều việc. Xác định bản Ant/JDK và command line baseline.

### Giai đoạn B — Thiết lập lớp tích hợp mỏng

Dùng Antrun hoặc AntBuilder để gọi **đúng target cần thiết**. Truyền đầu ra về build directory của Maven/Gradle và kết nối consumer trong lifecycle. Không gọi toàn bộ `legacy/build.xml` chỉ vì có target mặc định; chọn tên target tường minh để người đọc POM/Gradle script hiểu.

### Giai đoạn C — Thiết lập phép kiểm tra tương đương

Với từng target, so sánh bản cũ và bản tích hợp theo tiêu chí hữu ích: cấu trúc artifact, nội dung file sinh, compiler flags, test result, mã thoát, cấu hình runtime hoặc quyền truy cập tệp. Hành vi có thể khác ở những trường không ổn định như timestamp, thứ tự entry ZIP hoặc path tuyệt đối; nếu yêu cầu reproducible build, cần xử lý những yếu tố đó một cách tường minh.

### Giai đoạn D — Thay từng bước bằng giải pháp native

Ví dụ sau khi chuyển logic tạo `legacy.properties` sang Gradle task hoặc Maven plugin riêng, gỡ execution/wrapper Ant, bỏ dependency và chỉ giữ tài nguyên do cơ chế mới tạo. Không để hai đường cùng chạy để “phòng hờ”, vì chúng sẽ tranh quyền sở hữu đầu ra và có thể che lỗi.

### Giai đoạn E — Gỡ hạ tầng Ant không còn dùng

Khi không còn target legacy nào cần thiết, xóa cấu hình Antrun/AntBuilder, thư viện custom task, script `ant` trong CI và tài liệu cũ liên quan. Nếu vẫn còn một tool Ant riêng phục vụ nghiệp vụ khác, giữ nó dưới phạm vi rõ ràng, không coi dự án đã bỏ Ant hoàn toàn.

## 13. Những lỗi chuyển tiếp thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Maven báo không tìm thấy Ant target | Sai `antfile`, sai tên `target` hoặc đang gọi buildfile khác | Dùng đường dẫn từ `project.basedir` và kiểm tra tên target |
| Maven không chạy Ant khi dùng `mvn compile` | Execution gắn vào phase nằm sau `compile` | Gắn vào phase trước consumer; với resource dùng `generate-resources` |
| Ant sinh file nhưng không có trong Maven JAR | Chưa khai báo resource directory hoặc chạy target quá muộn | Thêm `<resources>`, gắn phase trước `process-resources` |
| Gradle task Ant chạy khi gọi trực tiếp nhưng không chạy lúc `build` | Chưa nối dependency với task tiêu thụ | `processResources.dependsOn(legacyGenerateResources)` hoặc kết nối với consumer đúng |
| Gradle bỏ qua target khi template đổi | Thiếu input trong task metadata | Khai báo đầy đủ `inputs` và `outputs` |
| `taskdef class not found` | Ant nhúng có classpath khác Ant CLI | Cấp JAR custom task cho đúng runtime/classloader |
| Tệp được sinh sai thư mục | Target legacy giả định working directory hoặc build root | Truyền output tuyệt đối; dùng `location` |
| Windows lỗi quoting hoặc script không có | Lệnh chứa đường dẫn có dấu cách hoặc phụ thuộc `ant.sh` | Dùng AntBuilder hoặc cấu hình executable phù hợp OS |
| Build báo thành công khi công cụ con lỗi | `<exec>` không báo lỗi đúng cách | Cấu hình `failonerror="true"` và kiểm tra output |
| Nhiều bản build cùng ghi một file | Output path chia sẻ giữa module/task | Mỗi module và target có thư mục output riêng |
| Xóa output của Maven/Gradle khi chạy Ant | Ant target cleanup quá rộng | Chỉ dọn thư mục legacy-owned, để tool chính quản lý `clean` |
| CI chạy Ant CLI nhưng Maven/Gradle dùng JDK khác | Sai môi trường hoặc launcher | Cố định version, log JDK, Ant và classpath thực tế |
| Vòng lặp build | Ant gọi Maven/Gradle trong khi Maven/Gradle gọi lại Ant | Xác lập một chiều điều phối; loại lời gọi ngược |
| Secret xuất hiện trong log của Ant | Property CLI hoặc task debug in credential | Cấp secret chỉ cho bước cần; không truyền qua property/log |

## 14. Thực hành từng bước với ví dụ nhỏ

Người học có thể thực hiện theo lộ trình:

**Lượt 1 — Chạy Ant riêng:** tạo `legacy/build.xml` như mục 3, truyền `generated.dir` và xác nhận file `legacy.properties` xuất hiện ở thư mục chỉ định. Thử bỏ property để thấy thông báo lỗi cụ thể.

**Lượt 2 — Chọn Maven:** tạo `pom.xml` như mục 4. Chạy `mvn generate-resources` để thấy Ant target được gọi trong phase phù hợp; tiếp tục `mvn clean package` rồi kiểm tra file trong JAR. Theo dõi sự khác nhau giữa thư mục `target/generated-resources/legacy` và `target/classes`.

**Lượt 3 — Hoặc chọn Gradle:** tạo `build.gradle` như mục 5 và dùng Gradle Wrapper nếu có. Chạy `legacyGenerateResources`, sau đó `build`. Kiểm tra file xuất hiện trong `build/generated/legacy-resources` và artifact JAR. Thử thay đổi Ant buildfile để thấy tác động tới metadata `inputs/outputs`.

**Lượt 4 — Giả lập một vấn đề chuyển tiếp:** đổi property Ant yêu cầu từ `generated.dir` thành `new.generated.dir` nhưng chưa sửa cấu hình Maven/Gradle. Khi build thất bại, quan sát chỗ cần cập nhật hợp đồng giữa Ant target và caller. Sau đó sửa property ở cả hai phía và chạy lại.

**Lượt 5 — Di chuyển logic:** thay `<echo>` của Ant bằng bước native trong Maven hoặc Gradle có cùng input/output. Xác nhận artifact cuối có nội dung tương đương, rồi bỏ đường gọi target legacy đó.

Không cần để Maven và Gradle chạy cùng lúc trên một bộ output. Hai hướng tích hợp được thử độc lập để thấy cách mỗi công cụ nối legacy target vào lifecycle.

## 15. Tài liệu tham khảo

- [Apache Ant Manual — Ant Task](https://ant.apache.org/manual/Tasks/ant.html): gọi một Ant buildfile khác, `antfile`, `target` và cách truyền property.
- [Apache Ant Manual — Target](https://ant.apache.org/manual/targets.html): target, dependencies và điều kiện thực thi.
- [Apache Maven Antrun Plugin](https://maven.apache.org/plugins/maven-antrun-plugin/): cách chạy Ant task trong Maven lifecycle.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phases như `generate-resources`, `process-resources`, `package` và `verify`.
- [Gradle User Manual — Ant](https://docs.gradle.org/current/userguide/ant.html): sử dụng `AntBuilder` và `importBuild`.
- [Gradle User Manual — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): khai báo input/output, up-to-date checks.
- [Gradle User Manual — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): `processResources` và các task đóng gói Java.

Gọi Ant từ Maven hoặc Gradle là một **cầu nối có thể tháo bỏ**. Bản dựng mới nên sở hữu thứ tự công việc, vị trí đầu ra và quy trình kiểm tra; Ant chỉ giữ một phần logic legacy có hợp đồng rõ ràng. Khi từng target được thay thế và kết quả được đối chiếu, hệ thống sẽ tiến dần tới một công cụ điều phối chính mà vẫn giữ hành vi cần thiết trong suốt giai đoạn chuyển đổi.
