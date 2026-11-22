# Điểm khác biệt cốt lõi khi tiếp cận Maven, Ant và Gradle

## 1. Cùng giải một bài toán, nhưng bắt đầu từ ba câu hỏi khác nhau

Một dự án Java thường cần lấy mã nguồn, biên dịch thành `.class`, chạy kiểm thử, đóng gói JAR/WAR và có thể xuất bản artifact để dự án khác sử dụng. JDK cung cấp trình biên dịch và công cụ chạy Java; **Ant, Maven và Gradle điều phối các công việc build** đó theo những mô hình khác nhau.

- **Ant hỏi “cần thực hiện những bước nào?”** Người viết mô tả các tác vụ cụ thể, quan hệ trước–sau và đường dẫn đầu vào/đầu ra. Nó gần với một chương trình tự động hóa các lệnh build.
- **Maven hỏi “đây là loại dự án nào và cần đi qua những giai đoạn chuẩn nào?”** Người viết khai báo mô hình dự án trong POM; vòng đời, quy ước thư mục và plugin quyết định cách thực hiện công việc.
- **Gradle hỏi “mô hình dự án gồm những thành phần và tác vụ phụ thuộc nhau ra sao?”** Người viết cấu hình dự án bằng DSL Groovy/Kotlin, áp dụng plugin và tùy biến đồ thị tác vụ; Gradle quyết định tác vụ cần thực thi cho lệnh được yêu cầu.

Đây là **ba mức trừu tượng và cách tổ chức build**, không chỉ là so sánh XML với Groovy/Kotlin, và cũng không phải bảng xếp hạng công cụ “mới hơn thì luôn tốt hơn”.

## 2. Bảng đối chiếu bản chất

| Góc nhìn | Ant | Maven | Gradle |
|---|---|---|---|
| Đơn vị tư duy chính | `target` gồm những `task` cụ thể | POM, vòng đời `lifecycle`, `phase` và `plugin goal` | Project, plugin và đồ thị `task` |
| Tệp build thường gặp | `build.xml` | `pom.xml` | `build.gradle` hoặc `build.gradle.kts` |
| Cách mô tả công việc | Chủ động viết cách chạy từng bước | Khai báo dự án và cấu hình các plugin được ràng buộc vào vòng đời | Khai báo/cấu hình các task và plugin bằng DSL |
| Quy ước thư mục Java | Không áp đặt cấu trúc dự án Java đầy đủ | Mặc định `src/main/java`, `src/test/java`, `target/` | Plugin Java mặc định dùng `src/main/java`, `src/test/java`, `build/` |
| Lệnh đóng gói điển hình | `ant jar` nếu có target `jar` | `mvn package` với dự án đóng gói JAR | `./gradlew build` hoặc `assemble` khi áp dụng plugin Java |
| Phụ thuộc thư viện | Cần cấu hình classpath hoặc tích hợp Ivy/công cụ khác | Khai báo dependency/scope; Maven giải quyết phụ thuộc bắc cầu qua repository | Khai báo dependency/configuration; Gradle giải quyết phụ thuộc qua repository |
| Mở rộng | Viết target/task hoặc dùng Ant task bổ sung | Cấu hình/viết plugin, profile, execution | Plugin, task tùy biến, convention plugin, cấu hình nhiều dự án |
| Build gia tăng và cache | Có kiểm tra thời điểm tệp ở một số task; phần lớn cần tự tổ chức | Plugin có thể tránh việc không cần thiết; không mặc định có cùng mô hình cache của Gradle | Hỗ trợ theo dõi input/output, up-to-date check, build cache khi task/plugin tương thích |

Các dòng trên mô tả **hành vi điển hình theo cấu hình/plugin**, không phải giới hạn tuyệt đối. Ant có thể quản lý phụ thuộc bằng Ivy; Maven có thể tùy biến mạnh bằng plugin; Gradle có thể chạy tác vụ rất đơn giản hoặc mô hình build phức tạp.

## 3. Đọc đúng ngôn ngữ của từng công cụ

### Ant: target là công thức thực hiện

Một tệp Ant mô tả các target như `compile`, `test`, `jar`. Quan hệ `depends` xác định target nào cần hoàn tất trước. Bên trong target là các tác vụ như `mkdir`, `javac`, `copy`, `jar`, `junit` (nếu đã cấu hình hỗ trợ).

Ví dụ, `jar` phụ thuộc `compile`: yêu cầu `ant jar` sẽ chạy `compile` trước rồi mới đóng gói. Ant **không tự suy ra** rằng mọi dự án Java phải có giai đoạn `test` hoặc `package`; tác giả tệp build xác định các target đó. Điều này hữu ích khi cần điều phối các bước tùy ý, nhưng tính nhất quán giữa các dự án tùy thuộc người thiết kế.

### Maven: phase mô tả mốc của vòng đời, plugin goal thực hiện công việc

POM khai báo định danh artifact (`groupId`, `artifactId`, `version`), cách đóng gói (`packaging`), dependency và cấu hình plugin. Maven có các vòng đời chuẩn, trong đó vòng đời `default` chứa những phase như `validate`, `compile`, `test`, `package`, `verify`, `install`, `deploy`.

Khi chạy `mvn package`, Maven đi qua các phase cần thiết đến `package`; với packaging `jar`, các goal của plugin liên quan được gắn vào những phase phù hợp để biên dịch, kiểm thử và đóng gói. **Phase không tự biên dịch Java**; plugin goal thực hiện thao tác thật. Một phase không có goal được gắn vào có thể không làm gì.

`mvn install` đưa artifact vào **kho Maven cục bộ** (`~/.m2/repository`); `mvn deploy` xuất bản tới kho từ xa khi đã cấu hình. “Deploy” ở đây không có nghĩa tự khởi chạy ứng dụng trên máy chủ.

### Gradle: plugin cung cấp mô hình và task, đồ thị quyết định trình tự

Tệp Gradle là DSL dựa trên Groovy hoặc Kotlin. Plugin `java` cung cấp các task như `compileJava`, `test`, `jar`, `assemble`, `check`, `build`. Trong mô hình Java thông thường, `build` nối các công việc đóng gói và kiểm tra theo quan hệ phụ thuộc; `assemble` hướng tới sản phẩm build, còn `check` hướng tới xác minh.

Gradle có **giai đoạn cấu hình** (xác định project, plugin, task và quan hệ) và **giai đoạn thực thi** (chạy các task được chọn). Vì vậy, không nên đặt thao tác có tác dụng phụ hoặc công việc tốn kém trực tiếp trong phần cấu hình chỉ vì muốn nó xảy ra khi chạy `build`; hãy đặt công việc đó trong task phù hợp.

Với task hỗ trợ khai báo input/output đúng, Gradle có thể xác định task đã cập nhật và tận dụng build cache. Khả năng này **không bảo đảm Gradle luôn nhanh hơn Maven hoặc Ant**: hiệu quả còn phụ thuộc phiên bản, plugin, I/O, số module, cấu hình cache và máy chạy CI.

## 4. Thực hành: cùng một chương trình Java, ba cấu hình build

Đặt các ví dụ trong **ba thư mục dự án riêng**, mỗi thư mục có cùng tệp `src/main/java/demo/App.java`. Dùng JDK 17+, phiên bản Ant/Maven/Gradle tương thích; máy cần có công cụ tương ứng hoặc Gradle Wrapper. Các dự án dưới đây không có dependency ngoài và không có bài test, để chỉ quan sát đường đi biên dịch → JAR.

```java
package demo;

public class App {
    public static void main(String[] args) {
        System.out.println("Build tools: OK");
    }
}
```

**Ant — `build.xml`:** tác giả viết rõ target và vị trí đầu ra.

```xml
<project name="demo-ant" default="jar">
    <target name="clean">
        <delete dir="build"/>
        <delete dir="dist"/>
    </target>

    <target name="compile">
        <mkdir dir="build/classes"/>
        <javac srcdir="src/main/java"
               destdir="build/classes"
               release="17"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="jar" depends="compile">
        <mkdir dir="dist"/>
        <jar destfile="dist/demo-ant.jar" basedir="build/classes"/>
    </target>
</project>
```

Chạy `ant jar` rồi `java -cp dist/demo-ant.jar demo.App`. Nếu muốn xóa đầu ra cũ trước, chạy `ant clean jar`. Target `jar` không tự chạy kiểm thử vì ví dụ chưa khai báo target/test dependency.

**Maven — `pom.xml`:** khai báo tọa độ, packaging mặc định JAR và cấu hình trình biên dịch; vòng đời chuẩn xử lý thứ tự.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example</groupId>
    <artifactId>demo-maven</artifactId>
    <version>1.0.0</version>
    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Chạy `mvn package` rồi `java -cp target/demo-maven-1.0.0.jar demo.App`. `target/` là thư mục đầu ra mặc định. Lần đầu Maven có thể cần tải plugin từ repository. Trong dự án thực, `package` còn đi qua phase kiểm thử; ví dụ này không có test.

**Gradle — `build.gradle` (Groovy DSL):** áp dụng plugin Java để nhận các task chuẩn, rồi cấu hình toolchain và tên JAR.

```groovy
plugins {
    id 'java'
}

group = 'org.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('jar') {
    archiveBaseName.set('demo-gradle')
}
```

Chạy `./gradlew build` nếu dự án có Gradle Wrapper (hoặc `gradle build` khi đã cài Gradle), rồi `java -cp build/libs/demo-gradle-1.0.0.jar demo.App`. Trên Windows có thể chạy `gradlew.bat build` từ Command Prompt. `build/libs/` là vị trí JAR mặc định của plugin Java; cấu hình `toolchain` yêu cầu Gradle tìm được JDK 17 thích hợp.

**Kết quả khi chạy `demo.App` của cả ba JAR:**

```text
Build tools: OK
```

Lệnh `java -cp ... demo.App` cố ý chỉ rõ main class. Các cấu hình minh họa **chưa thêm thuộc tính `Main-Class` vào manifest**, nên đừng mặc định `java -jar ...` sẽ chạy được.

Điều đáng chú ý là cùng một mã Java không quyết định công cụ build: Ant mô tả cách tạo JAR, Maven dựa vào packaging/vòng đời/plugin, còn Gradle dựa vào plugin Java và đồ thị task. Đường dẫn và tên artifact khác nhau vì các quy ước/cấu hình build.

## 5. Quản lý phụ thuộc: khác biệt ảnh hưởng trực tiếp đến dự án thật

Với thư viện bên ngoài, một dòng khai báo dependency trong Maven thường cung cấp tọa độ `groupId:artifactId:version` cùng scope như `compile`, `test`, `runtime`. Maven tìm artifact trong các repository đã cấu hình, dựng đồ thị phụ thuộc bắc cầu và áp dụng quy tắc hòa giải phiên bản. Với Gradle, dependency nằm trong cấu hình như `implementation`, `api`, `testImplementation` hoặc `runtimeOnly` (tùy plugin); Gradle cũng có repository, đồ thị phụ thuộc và quy tắc chọn phiên bản, nhưng **ngữ nghĩa configuration không đồng nhất với Maven scope**.

Ant lõi chủ yếu làm việc với classpath và các tệp JAR đã chỉ định; muốn tải, quản lý và giải quyết phụ thuộc bắc cầu một cách hệ thống, dự án thường tích hợp Apache Ivy hoặc công cụ bổ sung. Do đó, sự khác biệt không nằm ở chỗ “Ant không thể dùng thư viện”, mà ở **mức hỗ trợ quản lý dependency có sẵn trong mô hình build**.

Dù chọn Maven hay Gradle, cần phân biệt ba đối tượng:

- **Dependency artifact:** thư viện mà một dự án cần để biên dịch/chạy/kiểm thử.
- **Build output:** các tệp sinh ra trong `target/`, `build/` hoặc thư mục tự cấu hình; có thể xóa rồi xây dựng lại.
- **Artifact repository:** kho lưu và phân phối artifact có định danh/phiên bản, như Maven Central hoặc kho nội bộ; khác với thư mục output và khác với build cache.

Để CI có kết quả dễ tái lập, hãy cố định phiên bản plugin/dependency cần thiết, dùng Maven Wrapper hoặc Gradle Wrapper khi phù hợp, thống nhất JDK/toolchain và cấu hình repository đáng tin cậy. Cache có thể giúp nhanh hơn nhưng không thay thế kiểm soát phiên bản.

## 6. Cách chọn và những nhầm lẫn thường gặp

**Nên nghĩ tới Ant** khi cần một chuỗi thao tác riêng, có nhiều bước sao chép, chuyển đổi tệp, tích hợp công cụ cũ hoặc duy trì hệ thống đã dùng Ant. Đổi lại, nhiều quy ước build và quan hệ kiểm thử/đóng gói phải được tác giả thiết lập tường minh.

**Nên nghĩ tới Maven** khi muốn dự án Java theo cấu trúc thống nhất, một vòng đời quen thuộc cho nhóm/CI, quản lý phụ thuộc tập trung trong POM và dễ tận dụng hệ plugin sẵn có. Maven cũng hỗ trợ dự án nhiều module qua reactor; không nên hiểu rằng Maven chỉ phù hợp dự án đơn.

**Nên nghĩ tới Gradle** khi cần điều phối nhiều loại tác vụ, tùy biến sâu, cấu hình project lớn/nhiều module hoặc muốn sử dụng các tính năng build gia tăng và cache có điều kiện. Đổi lại, nhóm cần quản lý chất lượng build script, plugin và ranh giới cấu hình/thực thi để tránh logic khó theo dõi.

Một số lỗi suy luận cần tránh:

1. **Nhầm target, phase và task:** `ant jar` gọi target do dự án định nghĩa; `mvn package` chạy đến phase chuẩn; `gradle build` chạy một task trong đồ thị. Không mặc định cả ba đều hiểu cùng một lệnh `build` hoặc `package`.
2. **Tưởng Maven/Gradle tự thay JDK:** công cụ build vẫn cần trình biên dịch/toolchain phù hợp với phiên bản Java của mã nguồn.
3. **Cho rằng XML là nguyên nhân chính của khác biệt:** Ant và Maven đều dùng XML nhưng khác nhau về *các bước do người viết điều phối* và *vòng đời theo mô hình dự án*. Gradle dùng DSL, song các task và plugin mới là phần quyết định behavior build.
4. **Nhầm đóng gói với xuất bản hoặc triển khai:** tạo JAR, đưa artifact vào local/remote repository và chạy ứng dụng trên môi trường production là các công việc khác nhau.
5. **Kết luận công cụ nào luôn nhanh, dễ hoặc linh hoạt hơn:** điều này phụ thuộc loại dự án, plugin, cấu hình, năng lực nhóm, chiến lược cache và yêu cầu tích hợp.

**Cách đọc một dự án lạ:** nếu thấy `build.xml`, hãy tìm target mặc định và `depends`; nếu thấy `pom.xml`, hãy đọc packaging, dependency, plugin và phase CI gọi; nếu thấy `build.gradle(.kts)`, hãy đọc plugin, task, dependency, quan hệ task và wrapper. Hãy chạy lệnh build chuẩn của chính repository đó và kiểm tra artifact/kiểm thử thực tế trước khi quyết định đổi công cụ.
