# So sánh cách tiếp cận của Gradle, Maven và Ant

## 1. Cùng giải quyết bài toán build, nhưng tư duy khác nhau

Khi phát triển ứng dụng Java, một công cụ build phải giúp chuyển mã nguồn thành sản phẩm có thể sử dụng: biên dịch, chạy kiểm thử, đóng gói, quản lý thư viện, tạo báo cáo và chuẩn bị phát hành. `Ant`, `Maven` và `Gradle` đều làm được các công việc đó, nhưng mỗi công cụ đặt trọng tâm ở một nơi khác nhau:

- **Ant — mô tả các bước phải làm.** Người viết `build.xml` định nghĩa các `target` và các `task` cụ thể, rồi chỉ rõ quan hệ phụ thuộc giữa các target. Ant giống một bộ công cụ để tự lắp quy trình build.
- **Maven — mô tả dự án theo quy ước và vòng đời có sẵn.** Người viết `pom.xml` khai báo tọa độ dự án, dependencies và plugins; Maven gắn các mục tiêu của plugin vào một lifecycle tiêu chuẩn.
- **Gradle — mô hình hóa dự án và đồ thị công việc có thể mở rộng.** Người viết `build.gradle` (Groovy DSL) hoặc `build.gradle.kts` (Kotlin DSL), áp dụng plugin, cấu hình task và dependency. Gradle xác định những task cần thực hiện theo quan hệ phụ thuộc và các điều kiện thực thi.

Đây là ba *mức độ quy ước và khả năng tùy biến*, không phải ba loại công cụ hoàn toàn loại trừ nhau. Ant dùng XML nhưng cách tổ chức thường mang tính thủ tục; Maven khai báo cấu hình nhưng plugin vẫn thực hiện công việc; Gradle có DSL khai báo song vẫn cho phép viết logic xử lý tùy chỉnh. Vì thế, chỉ nhìn vào cú pháp XML hay Groovy/Kotlin chưa đủ để kết luận một công cụ “declarative” hoặc “imperative”.

## 2. Bảng đối chiếu các quyết định thiết kế

| Góc nhìn | Ant | Maven | Gradle |
| --- | --- | --- | --- |
| Câu hỏi chủ đạo | “Từng bước build phải chạy thế nào?” | “Dự án này là gì và thuộc lifecycle nào?” | “Dự án có những thành phần, task và phụ thuộc nào?” |
| Tệp thường gặp | `build.xml` | `pom.xml` | `settings.gradle` + `build.gradle` hoặc `build.gradle.kts` |
| Mô hình chính | Target chứa task; target có `depends` | Project Object Model (POM), plugin goal, lifecycle phase | Project, plugin, extension, configuration, task graph |
| Quy ước cấu trúc | Ít áp đặt; tự chỉ đường dẫn | Mạnh: `src/main/java`, `src/test/java`, `target/` | Plugin cung cấp quy ước; Java plugin cũng dùng `src/main/java`, `src/test/java` |
| Lệnh tiêu biểu | `ant package` (target do bạn đặt tên) | `mvn package` (phase chuẩn) | `./gradlew build` (task do plugin tạo) |
| Thư viện bên ngoài | Không có dependency manager Maven-style trong Ant lõi; có thể tích hợp Ivy/công cụ khác | Khai báo dependencies trong POM, transitive dependencies và scopes | Khai báo dependencies theo configurations, hỗ trợ dependency graph và variant-aware resolution |
| Mở rộng | Tạo target, task tùy chỉnh hoặc Antlib | Plugin và goal, gắn vào phase | Plugin, task tùy chỉnh, convention plugin, build logic |
| Nhiều module | Phải tổ chức liên kết các build/target rõ ràng | Reactor với parent/aggregator POM và `<modules>` | Multi-project build với `include(...)`, thêm composite build khi cần |
| Tránh làm lại | Phụ thuộc task/mốc thời gian/cách viết target; `javac` có kiểm tra nguồn đã biên dịch | Có khả năng tùy plugin và cơ chế incremental của plugin; lifecycle không tự bảo đảm mọi bước đều incremental | Cơ chế input/output tracking, incremental task, up-to-date check và build cache cho task hỗ trợ |
| Tính thống nhất nhóm | Phụ thuộc nhiều vào quy ước đội tự đặt | Cao khi dự án đi theo lifecycle chuẩn | Cao khi nhóm thống nhất plugin/convention; cấu hình tùy biến quá mức có thể làm khó bảo trì |
| Tình huống phù hợp | Quy trình đặc thù, hệ thống cũ đang dùng Ant, tác vụ xử lý tệp | Dự án JVM có vòng đời truyền thống, muốn tiêu chuẩn rõ và dễ đọc | Dự án JVM/Android hoặc đa module cần cấu hình, tái sử dụng logic và tối ưu build phức tạp |

**Chú ý:** Không có công cụ nào luôn nhanh hơn hoặc luôn dễ bảo trì hơn trong mọi dự án. Phiên bản công cụ, plugin, cache, CI, số module, thay đổi đầu vào và cách viết build đều ảnh hưởng kết quả thực tế.

## 3. Minh họa cùng một dự án Java 17 bằng ba công cụ

Ta dùng một mã nguồn giống hệt nhau để thấy rõ sự khác biệt nằm trong *mô tả build*. Điều kiện: đã cài JDK 17 trở lên và cài Ant, Maven, Gradle tương thích (hoặc dùng wrapper tương ứng). Tạo cấu trúc sau:

~~~text
hello-build/
├── src/
│   └── main/
│       └── java/
│           └── example/
│               └── Hello.java
├── build.xml
├── pom.xml
├── settings.gradle
└── build.gradle
~~~

Nội dung `src/main/java/example/Hello.java`:

~~~java
package example;

public final class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from Java 17!");
    }
}
~~~

Các tệp build dưới đây là **ba cách độc lập** xử lý cùng mã nguồn. Đặt chung trong thư mục chỉ để dễ đối chiếu; từng lệnh build sử dụng tệp của công cụ tương ứng.

### 3.1. Ant: lập trình bằng target và task

Nội dung `build.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="hello-build" default="package" basedir=".">
    <target name="compile">
        <mkdir dir="ant-out/classes"/>
        <javac srcdir="src/main/java"
               destdir="ant-out/classes"
               release="17"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="package" depends="compile">
        <mkdir dir="ant-out"/>
        <jar destfile="ant-out/hello-build.jar"
             basedir="ant-out/classes"/>
    </target>

    <target name="clean">
        <delete dir="ant-out"/>
    </target>
</project>
~~~

Chạy từ thư mục `hello-build`:

~~~bash
ant package
java -cp ant-out/hello-build.jar example.Hello
~~~

Dòng stdout của chương trình Java (không tính log build):

~~~text
Hello from Java 17!
~~~

Ở đây, `package` phụ thuộc `compile` nên Ant thực hiện việc biên dịch trước khi đóng gói. Người viết phải tự chọn thư mục đầu ra, gọi `mkdir`, `javac` và `jar`, rồi nối chúng bằng `depends`. `ant clean` chạy target dọn dẹp riêng. Lợi ích là nhìn thấy từng bước; đổi lại, những dự án tương tự dễ lặp lại phần cấu hình này. Ví dụ này dùng JDK 17 và Ant có hỗ trợ thuộc tính `release` trong task `javac`.

### 3.2. Maven: khai báo dự án và đi theo lifecycle

Nội dung `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>hello-build</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chạy:

~~~bash
mvn -B package
java -cp target/hello-build-1.0.0.jar example.Hello
~~~

Stdout Java vẫn là:

~~~text
Hello from Java 17!
~~~

Không cần viết một bước `javac` hoặc `jar` riêng. Với packaging mặc định `jar`, Maven thực hiện các phase cần thiết đến `package`; các mục tiêu plugin liên quan xử lý mã nguồn ở `src/main/java` và tạo JAR trong `target/`. Phase `test` nằm trước `package`, nhưng ví dụ chưa có mã kiểm thử. Phiên bản compiler plugin được ghim để minh họa tính ổn định của công cụ; trong dự án thực tế nên quản lý tập trung phiên bản các plugin quan trọng.

Dãy phase thường gặp của default lifecycle: `validate → compile → test → package → verify → install → deploy`. Gọi một phase sẽ thực hiện các phase đứng trước nó trong cùng lifecycle. Cần phân biệt `mvn package` là **phase**, còn `mvn compiler:compile` là cách gọi **goal của plugin**.

### 3.3. Gradle: áp dụng plugin, cấu hình mô hình và yêu cầu task

Nội dung `settings.gradle`:

~~~groovy
rootProject.name = 'hello-build'
~~~

Nội dung `build.gradle` (Groovy DSL):

~~~groovy
plugins {
    id 'java'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Chạy bằng Gradle đã cài:

~~~bash
gradle build
java -cp build/libs/hello-build-1.0.0.jar example.Hello
~~~

Stdout Java vẫn là:

~~~text
Hello from Java 17!
~~~

Plugin `java` tạo các task như `compileJava`, `classes`, `jar`, `test`, `assemble`, `check` và `build`, cùng quy ước đường dẫn. Task `build` kết hợp các bước kiểm tra và lắp ráp; không cần tự viết task gọi compiler hoặc packager cho ví dụ cơ bản. Cấu hình `toolchain` yêu cầu trình biên dịch Java 17 phù hợp; nếu máy thiếu JDK 17 và chưa cấu hình tự cung cấp toolchain, Gradle có thể báo lỗi. Đường dẫn JAR dùng tên project trong `settings.gradle` và `version` trong `build.gradle`.

Trong dự án thực tế, ưu tiên lưu **Gradle Wrapper** vào repository và chạy `./gradlew build` trên macOS/Linux hoặc `gradlew.bat build` trên Windows. Wrapper giúp các thành viên dùng cùng bản phân phối Gradle; lệnh `gradle build` ở trên chỉ để ví dụ tự chạy khi đã cài Gradle. Có thể xem danh sách task bằng `gradle tasks`, xem sơ bộ task graph bằng `gradle build --dry-run`.

### 3.4. Kết quả và điều bài này chứng minh

| Lệnh build | Ai quyết định các bước? | Tệp JAR của ví dụ |
| --- | --- | --- |
| `ant package` | Chính các target/task trong `build.xml` | `ant-out/hello-build.jar` |
| `mvn package` | Lifecycle mặc định + plugin goal của Maven | `target/hello-build-1.0.0.jar` |
| `gradle build` | Plugin Java + quan hệ phụ thuộc task Gradle | `build/libs/hello-build-1.0.0.jar` |

Cả ba JAR đều chứa class `example.Hello` và có thể chạy bằng `java -cp <đường-dẫn-jar> example.Hello`. Chúng **không tự động là executable JAR chạy bằng `java -jar`**, vì ví dụ chưa khai báo thuộc tính `Main-Class` trong manifest. Điều đó tách bạch việc đóng gói class với việc tạo ứng dụng tự chạy.

## 4. Phụ thuộc thư viện: khác biệt nổi bật khi dự án lớn lên

Dự án thực tế thường dùng JUnit, logging, web framework, JDBC driver và nhiều thư viện có phụ thuộc bắc cầu (*transitive dependencies*).

**Maven** khai báo dependency trong `pom.xml`, ví dụ đưa JUnit Jupiter vào phạm vi kiểm thử:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là một **đoạn chèn vào bên trong `<project>`**, chưa phải tệp POM hoàn chỉnh thứ hai. Maven dùng tọa độ `groupId:artifactId:version`, tải artifact từ repository đã cấu hình và giải quyết đồ thị phụ thuộc; `test` scope hướng thư viện vào classpath kiểm thử. Để chạy JUnit 5 với Maven, dự án còn cần Surefire plugin tương thích, thay vì suy ra rằng một dependency tự cấu hình mọi test runner.

**Gradle** khai báo repository và dependency trong `build.gradle`:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Đây cũng là **đoạn bổ sung** cho build dùng plugin `java` ở trên. `testImplementation` là configuration dành cho mã kiểm thử; `useJUnitPlatform()` cấu hình task chạy test trên JUnit Platform. Cơ chế resolution của Gradle còn hỗ trợ thuộc tính/biến thể (*variants*), constraints và những chính sách kiểm soát version phức tạp khi dự án cần.

**Ant lõi** tập trung vào task/target, không tự cung cấp mô hình dependency Maven-style để chỉ viết tọa độ rồi tự giải quyết dependency bắc cầu. Có thể quản lý JAR thủ công với `<path>` và classpath, hoặc tích hợp Apache Ivy hay công cụ khác. Vì vậy nói “Ant hoàn toàn không thể quản lý dependencies” là sai; điểm khác biệt nằm ở **những gì công cụ cung cấp sẵn**.

Cả Maven và Gradle đều cần xác định repository phù hợp, kiểm soát nguồn tin cậy và version; việc “có dependency manager” không mặc nhiên tạo ra build có thể tái lập. Với các dependency động/SNAPSHOT và repository thay đổi, đầu ra có thể thay đổi nếu không áp dụng chính sách khóa và xác minh phù hợp.

## 5. Lifecycle, task graph và tùy biến

### Ant: điều phối target trực tiếp

- `depends="compile"` chỉ định quan hệ trước–sau giữa target; bên trong target, các task thường thực hiện theo thứ tự khai báo.
- Tạo thao tác mới bằng target/task và mở rộng bằng task tùy chỉnh hoặc Antlib.
- Phải tự quyết định các target nào đại diện cho “test”, “package”, “publish”; không có lifecycle Java chuẩn đầy đủ giống Maven.

### Maven: lifecycle và plugin execution

- Build theo phase giúp những dự án có cùng cấu trúc dùng các lệnh giống nhau: `mvn test`, `mvn package`, `mvn verify`.
- Plugin có các goal; có thể cấu hình execution và gắn goal vào phase để bổ sung bước như generate source hoặc kiểm tra chất lượng.
- Tùy biến sâu vẫn khả thi, nhưng thay đổi luồng build ra ngoài quy ước có thể làm POM dài và khó theo dõi. Parent POM, `pluginManagement` và profile hỗ trợ chia sẻ/quản lý cấu hình khi dùng đúng mục đích.

### Gradle: cấu hình trước, chạy task được chọn sau

- Gradle có giai đoạn initialization, configuration và execution. Các khối DSL xây dựng/cấu hình mô hình, còn action của task thực hiện khi task cần chạy.
- Quan hệ `dependsOn` xác định phụ thuộc tác vụ; `mustRunAfter` chỉ tác động đến thứ tự khi cả hai task cùng nằm trong graph, không tự kéo task còn lại vào graph.
- Có thể dùng task type, plugin, convention plugin để tái sử dụng logic. Ưu tiên cấu hình lazy bằng API như `tasks.register(...)` và `tasks.named(...)` khi mở rộng.
- Các tính năng như up-to-date checks, build cache, configuration cache chỉ hiệu quả khi task và plugin tương thích, inputs/outputs được khai báo đúng, và môi trường được cấu hình phù hợp.

Một sai lầm thường gặp là đọc `build.gradle` như shell script “dòng nào xuất hiện trước thì chạy trước”. Các câu lệnh cấu hình có thể được đánh giá trong configuration phase, nhưng task action chỉ chạy khi nằm trong graph thực thi. Ngược lại, gọi `mvn package` cũng không có nghĩa Maven chỉ gọi đúng một plugin: phase đó kéo theo các phase trước và các goal được ràng buộc vào chúng.

## 6. Hiệu năng và khả năng mở rộng: đánh giá theo điều kiện

Đánh giá build theo ít nhất ba kịch bản: **clean build** (xóa output), **incremental build** (đổi một file), và **CI build** (runner mới hoặc có cache). Một kết luận từ một lần chạy trên máy cá nhân không đủ để xếp hạng.

- **Ant:** hiệu quả tùy cách thiết kế các target/task và kiểm tra thay đổi của từng task. Build nhỏ, quy trình ngắn có thể chạy rất nhanh; việc tái sử dụng cache và điều phối dự án lớn thường cần cấu hình thêm.
- **Maven:** lifecycle và reactor nhiều module tương đối dễ dự đoán; thời gian phụ thuộc các plugin, số module, tải dependency và cấu hình thực thi. Có các tùy chọn build song song, nhưng không nên suy ra mọi goal đều incremental hoặc cacheable theo cùng cách Gradle.
- **Gradle:** Daemon, task up-to-date check, build cache, parallel execution và configuration cache có thể giảm thời gian lặp lại. Kết quả phụ thuộc khả năng tương thích của plugin và cách khai báo task, không phải chỉ do dùng DSL Gradle. Configuration cache tăng tốc cấu hình ở lần build phù hợp, khác với build cache lưu/tái sử dụng **đầu ra task**.

Ví dụ: chỉ sửa một file Java rồi build lại. Với Gradle Java plugin, `compileJava` có thể chỉ xử lý phần thay đổi cần thiết, còn các task không đổi có thể được đánh dấu up-to-date hoặc lấy kết quả từ cache nếu hợp lệ. Với Maven, mức độ làm lại phụ thuộc compiler plugin và những plugin trong lifecycle. Với Ant, thuộc tính và hành vi của `javac`/`jar` cùng target tự định nghĩa quyết định bao nhiêu bước chạy lại. Muốn so sánh công bằng, hãy giữ cố định JDK, dependency, số worker/CPU, trạng thái cache và thao tác sửa source.

## 7. Cấu trúc dự án, nhiều module và độ dễ bảo trì

Trong **Maven multi-module**, POM aggregator liệt kê modules, còn parent POM có thể chia sẻ dependency/plugin management. Một POM có thể vừa làm parent vừa làm aggregator, nhưng đó là hai vai trò khác nhau. Maven Reactor tính thứ tự build từ quan hệ module, giúp chạy build cho nhiều artifact có phụ thuộc nhau.

Trong **Gradle multi-project**, `settings.gradle` khai báo các subproject và file build mỗi project áp dụng plugin/cấu hình phù hợp. Một convention plugin nội bộ giúp nhiều module dùng chung quy tắc test, compiler hoặc publishing mà không nhân bản script; composite builds là cơ chế khác, dùng để ghép nhiều build độc lập. Với repository lớn, thiết kế ranh giới module và tránh cấu hình toàn bộ project quá mức thường quan trọng hơn việc đổi tên task.

Với **Ant**, có thể phối hợp build con qua `subant`, `antcall` hoặc script điều phối, nhưng quan hệ thư viện, version và ranh giới module cần một thiết kế nhất quán riêng. Ant vẫn hữu ích khi quy trình đặc thù hoặc tích hợp hệ thống cũ khiến lớp quy ước mặc định của Maven/Gradle không phù hợp.

Độ bảo trì không chỉ do công cụ: build script có logic tùy biến tản mát, plugin không ghim version, dependency không kiểm soát hoặc build phụ thuộc biến môi trường bí mật đều có thể gây khó khăn ở bất kỳ hệ sinh thái nào.

## 8. Chọn công cụ nào cho từng tình huống?

| Tình huống | Lựa chọn thường hợp lý | Vì sao và điều cần kiểm tra |
| --- | --- | --- |
| Thư viện/dịch vụ Java chuẩn, cấu trúc quen thuộc, nhóm muốn lifecycle nhất quán | **Maven** | POM và các phase rõ ràng; bảo đảm plugin/version, parent và quy ước CI được quản lý tốt |
| Dự án Android hoặc JVM đa module với nhiều biến thể/cấu hình build | **Gradle** | Hệ plugin, task graph và variant model linh hoạt; Android dùng hệ thống build dựa trên Gradle; cần chuẩn hóa convention và cache |
| Quy trình hiện có dùng Ant hoặc cần chuỗi tác vụ thao tác tệp rất riêng | **Ant** | Dễ kiểm soát từng task; cân nhắc chi phí tự tổ chức dependency/test/packaging và bảo trì XML |
| Dự án nhỏ, ít yêu cầu tùy chỉnh, thành viên mới cần đọc build nhanh | **Maven hoặc Gradle với plugin chuẩn** | Ưu tiên lựa chọn nhóm đã thông thạo; không thêm abstraction khi chưa cần |
| Đội đang vận hành một build ổn định | **Có thể giữ công cụ hiện tại** | Chỉ migrate khi có lợi ích đo được về tính năng, tốc độ hoặc bảo trì; tính chi phí chuyển plugin, CI, release, IDE |

Một checklist lựa chọn thực tế:

1. **Đầu ra:** JAR, WAR, Android APK/AAB, nhiều artifact hay pipeline phi chuẩn?
2. **Quy mô:** Một module hay hàng trăm module cần build có chọn lọc?
3. **Thư viện:** Có dependency graph phức tạp, nhiều repository hoặc variant không?
4. **Khả năng tùy biến:** Cần plugin sẵn có hay task tùy chỉnh và logic tái sử dụng?
5. **Trải nghiệm nhóm:** Có thể đọc, debug, nâng cấp và chạy offline/CI cùng kết quả hay không?
6. **Bằng chứng:** Đã đo clean build, incremental build và CI build trên cùng workload chưa?

## 9. Khả năng tái lập và vận hành trong nhóm

- **Ghim phiên bản công cụ:** dùng Gradle Wrapper (`gradlew`, `gradle/wrapper/*`) hoặc Maven Wrapper (`mvnw`, `.mvn/wrapper/*`) khi dự án chọn công cụ đó. Với Ant, cần chuẩn hóa bản Ant/JDK qua môi trường hoặc quy trình cài đặt.
- **Đồng bộ JDK:** khai báo mức ngôn ngữ/`release`; trong Gradle có thể dùng toolchain. Mức Java của mã nguồn và JDK thực sự dùng để chạy build là hai khái niệm cần phân biệt.
- **Kiểm soát plugins/dependencies:** ghim version, quản lý repository, cân nhắc dependency locking hoặc verification ở nơi được hỗ trợ; tránh phụ thuộc phiên bản động khi cần tính tái lập.
- **Xác định ranh giới cache:** không dùng trạng thái cache để che lỗi task thiếu inputs/outputs hoặc build phụ thuộc file ngoài mà không khai báo.
- **CI dùng cùng lệnh:** chạy build/test/verify và lưu artifact/log để chẩn đoán. Khi migrate, so sánh cả file đầu ra, test report và bước phát hành, không chỉ xem câu lệnh exit code 0.

## 10. Những nhầm lẫn cần tránh

1. **“Ant dùng XML nên declarative giống Maven.”** XML chỉ là cách biểu diễn. Ant thường yêu cầu tác giả định nghĩa chi tiết các bước; Maven có lifecycle và các convention sẵn.
2. **“Maven không tùy biến được.”** Maven có plugin, goal, execution, parent, profile; điểm cần cân nhắc là mức phù hợp của một tùy biến với lifecycle chuẩn.
3. **“Gradle luôn nhanh hơn Maven.”** Không có kết luận chung nếu chưa đo workload, phiên bản plugin, cache và môi trường.
4. **“Trong Gradle, các dòng build script lần lượt chạy như shell.”** DSL cấu hình mô hình, còn task action chạy theo graph và phase thích hợp.
5. **“`build` trong Gradle giống hệt `package` trong Maven.”** Mỗi tên thuộc mô hình khác nhau; Gradle Java plugin `build` thường kết hợp `assemble` và `check`, còn Maven `package` là một phase của lifecycle.
6. **“Có dependency manager thì build tự động tái lập tuyệt đối.”** Repository, version động, plugin, JDK, môi trường và input bên ngoài vẫn phải được kiểm soát.
7. **“JAR nào cũng chạy bằng `java -jar`.”** Cần manifest chỉ định main class (hoặc cơ chế đóng gói thực thi tương ứng); ví dụ ở trên dùng `java -cp` có chủ ý.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Bạn cần thêm một bước tạo file trước khi biên dịch. Trong Ant thường sửa gì? Trong Maven và Gradle sẽ nghĩ theo hướng nào?

*Gợi ý:* Ant thêm target/task và `depends`. Maven tìm plugin goal thích hợp để ràng vào phase. Gradle dùng plugin/task và quan hệ phụ thuộc task, bảo đảm source generation được nối đúng vào compile.

**Câu 2.** Vì sao cùng một mã Java mà `ant package`, `mvn package` và `gradle build` có thể tạo JAR ở ba đường dẫn khác nhau?

*Đáp án:* Ant chỉ định đường dẫn trực tiếp; Maven và Gradle dùng quy ước đầu ra tương ứng của lifecycle/plugin. Đường dẫn không quyết định bản thân bytecode Java có chạy được hay không.

**Câu 3.** Nếu một CI runner mới build chậm hơn máy đã dùng nhiều ngày, có thể kết luận Gradle/Maven/Ant chậm hơn không?

*Đáp án:* Không. Cần phân biệt cache dependency, JDK, daemon, cấu hình và đầu vào; đo trên điều kiện tương đương.

**Câu 4.** Khi nào nên ưu tiên Maven thay vì Gradle?

*Đáp án mẫu:* Khi dự án bám sát lifecycle Java chuẩn, tổ chức cần POM dễ kiểm tra và nhóm đã có hệ plugin/quy ước Maven ổn định; quyết định vẫn phụ thuộc yêu cầu cụ thể.

**Câu 5.** Một plugin Gradle “không tương thích configuration cache” có nghĩa là Gradle không build được dự án?

*Đáp án:* Không nhất thiết. Điều đó nói đến khả năng dùng một cơ chế tối ưu cấu hình trong trường hợp cụ thể; cần xem thông báo và khả năng chạy build bình thường khi không sử dụng cache đó.

## 12. Kết luận

Ant nhấn mạnh **các bước do người viết điều khiển**, Maven nhấn mạnh **mô hình dự án và vòng đời thống nhất**, còn Gradle nhấn mạnh **plugin, mô hình cấu hình và đồ thị task có thể mở rộng**. Để lựa chọn đúng, hãy nhìn vào cấu trúc dự án, độ phức tạp của dependency/build logic, khả năng của nhóm và bằng chứng từ bản build thực tế. Khi học Gradle, đối chiếu với Ant và Maven giúp phân biệt rõ *task graph* của Gradle với *target graph* của Ant và *lifecycle phase* của Maven.
