# Quá trình nội suy thuộc tính và hình thành mô hình có hiệu lực trong Maven

Khi chạy `mvn package`, Maven không sử dụng tệp `pom.xml` như một đoạn XML đứng riêng. Nó **xây dựng một mô hình dự án có hiệu lực** từ POM đang chọn, POM cha, các giá trị mặc định, những profile được kích hoạt và các cấu hình liên quan. Trong quá trình đó, các biểu thức như `${project.version}` hoặc `${java.release}` có thể được **nội suy** (*interpolation*) thành giá trị cụ thể.

Ví dụ một POM có:

```xml
<properties>
    <java.release>17</java.release>
</properties>
<build>
    <finalName>${project.artifactId}-${project.version}</finalName>
</build>
```

Nếu dự án có `artifactId=hello-model` và `version=1.0.0`, tên cuối cùng được Maven tính ra là `hello-model-1.0.0`. Nếu plugin đóng gói JAR theo tên mặc định và không bị cấu hình khác ghi đè, artifact thường nằm ở `target/hello-model-1.0.0.jar`.

Điểm quan trọng là **nội suy thuộc tính chỉ là một phần** trong quá trình hình thành mô hình có hiệu lực. Maven còn phải tìm POM cha, áp dụng kế thừa, chọn profile, quản lý dependency/plugin và kiểm tra mô hình. Vì vậy, hai người có cùng POM nhưng chọn profile, JDK hoặc tham số dòng lệnh khác nhau có thể nhận các cấu hình build khác nhau.

Bài này tập trung vào Maven 3.x và cách làm việc thực tế với `pom.xml`, `${...}`, `<properties>`, POM cha, profile, *effective POM*, cùng công cụ xác minh giá trị Maven thực sự dùng. Một số khác biệt giữa các phiên bản Maven được nêu khi có ảnh hưởng.

## 1. Phân biệt POM nguồn và mô hình có hiệu lực

**POM nguồn (raw/source POM)** là nội dung bạn quản lý trong `pom.xml`. Nó có thể rất ngắn và chứa nhiều tham chiếu tới thuộc tính:

```xml
<groupId>com.example</groupId>
<artifactId>hello-model</artifactId>
<version>1.0.0</version>
<name>${project.artifactId} example</name>
```

Đoạn trên chỉ minh họa một phần của POM; POM đầy đủ cần `<project>` và `<modelVersion>`.

**Effective POM** là cách xem mô hình dự án sau khi Maven đã tổng hợp các cấu hình phù hợp với một phiên chạy cụ thể. Mô hình này có thể chứa:

- Tọa độ dự án nhận từ chính POM hoặc kế thừa từ parent.
- Giá trị từ **Super POM**, chẳng hạn nhiều thiết lập mặc định về repository, thư mục build.
- Các phần của POM cha và tác động của những profile đang hoạt động.
- Các thuộc tính hoặc biểu thức đã được thay bằng giá trị có thể xác định.
- Cấu hình quản lý dependency, plugin và các giá trị mặc định/thiết lập đã hợp nhất theo quy tắc Maven.

Ví dụ, ngay cả khi bạn không viết `<build><directory>target</directory></build>`, Maven vẫn thường dùng thư mục `target`. Tên thư mục này đến từ quy ước và mô hình mặc định, không phải một dòng ẩn trong POM nguồn.

| Khái niệm | Nội dung | Mục đích |
| --- | --- | --- |
| `pom.xml` | XML do dự án quản lý, có thể chứa `${...}` | Nguồn cấu hình dự án, thường commit vào Git. |
| Parent POM | POM được khai báo trong `<parent>` | Cung cấp tọa độ và cấu hình kế thừa. |
| Super POM | POM mặc định do Maven cung cấp | Bổ sung cấu hình nền khi không có khai báo cụ thể. |
| Profile | Các cấu hình được chọn theo lệnh/môi trường | Điều chỉnh mô hình cho phiên build. |
| Interpolation | Thay tham chiếu `${...}` bằng giá trị đã biết | Hoàn thiện những trường có hỗ trợ biểu thức. |
| Effective POM | Mô hình dự án sau khi tổng hợp | Dùng để chẩn đoán Maven thực sự hiểu POM như thế nào. |
| Plugin execution | Chạy goal/phase dựa trên mô hình và tham số plugin | Thực hiện compile, test, package, deploy… |

Maven không đơn giản nối tất cả các POM rồi thay chuỗi văn bản. Nó xử lý các phần tử theo **ngữ nghĩa mô hình**: có trường kế thừa, trường ghi đè, danh sách hợp nhất theo khóa và những bước kiểm tra riêng.

## 2. Các giai đoạn hình thành mô hình Maven

Ở mức khái niệm, Maven Model Builder xử lý một dự án theo luồng sau. Đây là **sơ đồ học tập**; triển khai chi tiết có nhiều bước, thứ tự nội bộ và xử lý hai pha tùy phiên bản Maven.

```text
            pom.xml của dự án
                    |
                    v
          Đọc, kiểm tra cấu trúc
                    |
                    v
        Xác định profile hoạt động
        và đưa tác động của chúng
           vào mô hình tương ứng
                    |
                    v
         Giải quyết POM cha, tiếp
         tục đến các nguồn mặc định
                    |
                    v
         Ghép mô hình theo quy tắc
         inheritance / normalization
                    |
                    v
         Nội suy các giá trị ${...}
         từ những nguồn đã có
                    |
                    v
         Hoàn thiện quản lý plugin,
         dependency và các cấu hình
         có hiệu lực cần thiết
                    |
                    v
            Effective Model
                    |
                    v
          Lập kế hoạch lifecycle,
           thực thi các plugin goal
```

Đọc sơ đồ theo những điểm sau:

1. **Đọc POM và kiểm tra tính hợp lệ.** Maven xác định tọa độ, cấu trúc XML và các phần tử đúng mô hình. POM không có `modelVersion` hợp lệ hoặc sai XML có thể bị từ chối trước khi chạy plugin.
2. **Kích hoạt profile.** Maven đánh giá profile được chọn bằng `-P` và profile tự kích hoạt theo một số điều kiện như JDK, hệ điều hành, thuộc tính hệ thống/user property hoặc tệp. Việc xác định profile diễn ra sớm, **trước khi toàn bộ nội suy POM hoàn thành**.
3. **Giải quyết parent.** Nếu POM con có `<parent>`, Maven phải tìm POM cha phù hợp (qua đường dẫn tương đối hoặc repository), rồi xử lý chuỗi parent theo quy tắc áp dụng.
4. **Ghép kế thừa.** Các thuộc tính và phần cấu hình hợp lệ từ parent được hợp nhất vào con; giá trị con có thể ghi đè giá trị kế thừa.
5. **Nội suy.** Các biểu thức `${...}` trong những vị trí được hỗ trợ được đánh giá từ mô hình đã ghép và các nguồn thuộc tính khác.
6. **Hoàn thiện effective model.** Maven xử lý thêm dependency management, plugin management, thông tin đường dẫn và kiểm tra mô hình; sau đó lifecycle/plugin dùng các cấu hình thích hợp để thực thi công việc.

Tài liệu *Maven Model Builder* mô tả việc xây dựng mô hình thành nhiều bước, gồm profile activation/injection, parent resolution, inheritance assembly, interpolation, dependency/plugin management và effective model validation. **Không xem sơ đồ trên như cam kết rằng mọi biểu thức ở mọi plugin đều được thay đúng một lần ở một thời điểm duy nhất.** Một số tham số được đánh giá thêm khi cấu hình goal của plugin.

Một hệ quả quan trọng: chỉ sửa một thuộc tính trong POM không bảo đảm mọi giai đoạn khác đều đọc được giá trị đó. Đặc biệt, **điều kiện kích hoạt profile không được dùng tùy ý mọi thuộc tính POM như nội suy mô hình thông thường**.

## 3. Cú pháp `${...}` và những nhóm thuộc tính thường gặp

Maven dùng cú pháp `${ten.thuoc.tinh}` để tham chiếu giá trị. Thuộc tính bên trong dấu ngoặc có thể đến từ những nguồn khác nhau.

| Loại | Ví dụ | Nguồn/ý nghĩa |
| --- | --- | --- |
| Project model | `${project.groupId}`, `${project.artifactId}`, `${project.version}` | Tọa độ và trường của dự án sau khi mô hình được xử lý. |
| Project build | `${project.build.directory}`, `${project.build.finalName}` | Thư mục đầu ra và tên artifact do mô hình build xác định. |
| POM properties | `${java.release}`, `${demo.flavor}` | Các khóa trong `<properties>` ở POM hoặc profile phù hợp. |
| CLI user properties | `-Ddemo.flavor=ci` | Giá trị được người chạy truyền qua command line. |
| Java system properties | `${user.home}`, `${java.version}` | Giá trị có sẵn trong JVM chạy Maven. |
| Environment variables | `${env.JAVA_HOME}`, `${env.CI}` | Biến môi trường được đặt trước khi Maven chạy. |
| Maven-related | `${maven.home}`, `${maven.version}` | Thông tin của phiên Maven đang chạy. |
| Settings-related | `${settings.localRepository}` | Thông tin settings trong ngữ cảnh được hỗ trợ; có thể được đánh giá muộn hơn. |
| Project base directory | `${project.basedir}` | Thư mục chứa `pom.xml` đang được xử lý. |

Trong ví dụ:

```xml
<properties>
    <java.release>17</java.release>
    <demo.flavor>local</demo.flavor>
</properties>
<build>
    <finalName>${project.artifactId}-${project.version}-${demo.flavor}</finalName>
</build>
```

Nếu `project.artifactId=hello-model`, `project.version=1.0.0` và `demo.flavor=local`, `finalName` mong đợi là `hello-model-1.0.0-local`.

**Cần phân biệt tên của biểu thức với giá trị nó tham chiếu:**

- `${project.version}` là một trường của mô hình dự án; không cần tạo `<properties><project.version>…</project.version></properties>` để dùng nó.
- `${demo.flavor}` là khóa tùy chỉnh; thông thường phải được định nghĩa ở `<properties>` hoặc truyền từ nguồn khác.
- `${env.JAVA_HOME}` đọc giá trị môi trường; nó **không phải** `${project.basedir}` hoặc đường dẫn Maven Home.
- `${project.build.directory}` thường trỏ đến `target` của dự án, trừ khi cấu hình build thay đổi.

Đừng tùy tiện dùng tên khóa bắt đầu bằng `project.` để làm thuộc tính tùy chỉnh; tên dạng này dễ gây nhầm lẫn với trường Maven cung cấp. Dùng namespace rõ nghĩa như `demo.flavor`, `quality.level` hoặc `myteam.docs.url`.

## 4. Nội suy không giống việc thay thế văn bản một cách mù quáng

Hãy xét một POM con khai báo:

```xml
<name>${project.artifactId} (${demo.flavor})</name>
```

Maven phải có thông tin `artifactId` của dự án và nguồn giá trị `demo.flavor`. Khi nội suy thành công, `name` trở thành tên hiển thị, ví dụ `hello-model (local)`.

Tuy nhiên, có các giới hạn:

- **Không phải mọi trường trong POM đều cho phép cùng một biểu thức.** Những phần Maven cần để tự giải quyết mô hình, như tọa độ parent, bị ràng buộc chặt hơn các giá trị mô tả hay cấu hình plugin.
- **Không phải mọi tham chiếu được giải quyết ngay trong Model Builder.** Một số biểu thức liên quan settings hoặc tham số plugin có thể được đánh giá ở giai đoạn sau.
- **Không có bảo đảm thuộc tính chưa định nghĩa sẽ thành chuỗi rỗng.** Biểu thức có thể còn nguyên, tạo cảnh báo hoặc gây lỗi khi được dùng.
- **Giá trị có thể phụ thuộc môi trường.** Cùng POM nhưng khác `-D`, profile, JDK hoặc environment có thể cho kết quả khác.
- **Các giá trị kế thừa có thể bị ghi đè.** Nếu parent khai báo thuộc tính và con khai báo lại cùng khóa, mô hình con có thể dùng giá trị của mình.

Vì thế cần **kiểm tra effective model và giá trị thực tế** trước khi khẳng định một tên file, URL, version hoặc cấu hình plugin đã được nội suy như mong đợi.

## 5. Ví dụ thực hành: parent, child, property và profile

Phần này tạo một dự án Maven nhỏ sử dụng Java 17. Parent khai báo các giá trị chung; child có `artifactId` riêng và một profile thay đổi thuộc tính `demo.flavor`. Mục tiêu là quan sát quá trình kế thừa và nội suy bằng lệnh Maven thực tế.

### 5.1. Cấu trúc thư mục

```text
model-parent/
├── pom.xml
└── hello-model/
    ├── pom.xml
    └── src/
        └── main/
            └── java/
                └── com/example/model/
                    └── App.java
```

Parent POM ở `model-parent/pom.xml`; child POM ở `model-parent/hello-model/pom.xml`. Mỗi POM có `project.basedir` riêng. Muốn tạo cấu trúc này, có thể dùng IDE hoặc lệnh:

Linux/macOS:

```bash
mkdir -p model-parent/hello-model/src/main/java/com/example/model
cd model-parent
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force model-parent/hello-model/src/main/java/com/example/model
Set-Location model-parent
```

### 5.2. Parent POM hoàn chỉnh

Tệp `model-parent/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.model</groupId>
    <artifactId>model-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>hello-model</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <demo.flavor>local</demo.flavor>
    </properties>

    <build>
        <finalName>${project.artifactId}-${project.version}-${demo.flavor}</finalName>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Giải thích:

- `groupId` và `version` của parent có thể được child kế thừa.
- `packaging=pom` phù hợp cho parent/aggregator.
- `<modules>` đưa `hello-model` vào reactor khi chạy Maven từ thư mục parent; **aggregation** khác **inheritance**.
- `demo.flavor` là thuộc tính tùy chỉnh có giá trị mặc định `local`.
- `maven.compiler.release=17` là thuộc tính được Maven Compiler Plugin hỗ trợ để tạo mã tương thích Java 17.
- `<finalName>` ghép ba giá trị bằng nội suy. Khi tính cho child, `project.artifactId` và `project.version` được hiểu theo **mô hình child đang được build**.
- `pluginManagement` quản lý phiên bản plugin để các plugin tương ứng dùng trong lifecycle nhận được cấu hình đã định. Nó không đồng nghĩa kích hoạt mọi plugin chỉ vì được liệt kê.

### 5.3. Child POM hoàn chỉnh

Tệp `model-parent/hello-model/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.model</groupId>
        <artifactId>model-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>hello-model</artifactId>
    <name>${project.artifactId} (${demo.flavor})</name>
    <description>Ví dụ về mô hình Maven và nội suy thuộc tính.</description>

    <profiles>
        <profile>
            <id>ci</id>
            <properties>
                <demo.flavor>ci</demo.flavor>
            </properties>
        </profile>
    </profiles>
</project>
```

POM con **không khai báo `groupId` và `version` ở cấp `project`**: nó kế thừa hai giá trị từ parent. Ngược lại, nó phải có `artifactId=hello-model` riêng. Khối `<parent>` chứa tọa độ **của cha** để Maven tìm đúng mô hình.

Profile `ci` chỉ đặt một property mới khi được kích hoạt. Khi không bật profile, child kế thừa `demo.flavor=local` từ parent. Khi chạy với `-Pci`, giá trị `demo.flavor` có hiệu lực trong child thành `ci`.

### 5.4. Lớp Java có thể chạy

Tệp `model-parent/hello-model/src/main/java/com/example/model/App.java`:

```java
package com.example.model;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from Maven model");
    }
}
```

Lớp Java này độc lập, không cần dependency ngoài JDK. Thư mục nguồn khớp với package `com.example.model`.

### 5.5. Build với cấu hình mặc định

Trong thư mục `model-parent`:

```bash
mvn -version
mvn clean package
java -cp hello-model/target/classes com.example.model.App
```

Nếu máy có Maven/JDK phù hợp và các plugin có thể được giải quyết, Maven build parent và child; chương trình Java in **đúng một dòng stdout**:

```text
Hello from Maven model
```

Không dự đoán cố định toàn bộ log Maven vì nó phụ thuộc phiên bản, plugin và môi trường. Trong ví dụ, khi không bật profile và không truyền giá trị ghi đè, các giá trị mong đợi của child là:

```text
project.groupId    = com.example.model
project.artifactId = hello-model
project.version    = 1.0.0-SNAPSHOT
demo.flavor        = local
project.name       = hello-model (local)
build.finalName    = hello-model-1.0.0-SNAPSHOT-local
```

Với Maven JAR Plugin và cấu hình này, artifact JAR thường có tên `hello-model-1.0.0-SNAPSHOT-local.jar` trong `hello-model/target`. JAR thông thường không tự có `Main-Class` trong manifest; ví dụ chạy bằng classpath `target/classes` nên không phụ thuộc thiết lập manifest.

## 6. Kiểm chứng kết quả nội suy bằng Maven Help Plugin

### 6.1. Đánh giá từng thuộc tính

Từ thư mục `model-parent`, dùng `-f` trỏ trực tiếp vào child POM. Lệnh sau đọc **giá trị có hiệu lực của child**:

```bash
mvn -f hello-model/pom.xml help:evaluate -Dexpression=project.groupId -q -DforceStdout
mvn -f hello-model/pom.xml help:evaluate -Dexpression=project.artifactId -q -DforceStdout
mvn -f hello-model/pom.xml help:evaluate -Dexpression=project.version -q -DforceStdout
mvn -f hello-model/pom.xml help:evaluate -Dexpression=project.name -q -DforceStdout
mvn -f hello-model/pom.xml help:evaluate -Dexpression=project.build.finalName -q -DforceStdout
```

Với POM ví dụ ở mục 5, **kết quả được kỳ vọng của năm lệnh riêng biệt**, theo thứ tự:

```text
com.example.model
hello-model
1.0.0-SNAPSHOT
hello-model (local)
hello-model-1.0.0-SNAPSHOT-local
```

Đây là bảng kết quả ghép để minh họa, **không phải stdout chung của một lần chạy Maven**. `help:evaluate` được Maven Help Plugin cung cấp; plugin có thể cần tải từ repository lần đầu. `-q -DforceStdout` thường giúp in giá trị ở chế độ log ngắn.

Muốn kiểm tra property tùy chỉnh:

```bash
mvn -f hello-model/pom.xml help:evaluate -Dexpression=demo.flavor -q -DforceStdout
```

Giá trị mong đợi là `local`. Nếu giá trị khác, hãy kiểm tra các profile đang kích hoạt và các `-D` mà lệnh thực sự nhận.

### 6.2. Bật profile để thấy mô hình thay đổi

```bash
mvn -f hello-model/pom.xml -Pci help:evaluate -Dexpression=project.build.finalName -q -DforceStdout
```

Kết quả mong đợi:

```text
hello-model-1.0.0-SNAPSHOT-ci
```

Khi chạy build từ parent, profile `ci` của child được kích hoạt trong phạm vi phù hợp với child:

```bash
mvn -Pci clean package
```

Artifact child khi đó thường mang hậu tố `-ci`. Đừng nhầm `-Pci` (chọn profile) với `-Dci=...` (đặt một user property tên `ci`).

### 6.3. Ghi đè thuộc tính từ dòng lệnh

Người chạy có thể truyền user property qua `-D`:

```bash
mvn -f hello-model/pom.xml -Ddemo.flavor=staging help:evaluate -Dexpression=project.build.finalName -q -DforceStdout
```

Giá trị mong đợi:

```text
hello-model-1.0.0-SNAPSHOT-staging
```

Trong trường hợp thông dụng này, `-Ddemo.flavor=staging` cung cấp user property có độ ưu tiên cao hơn property tương ứng trong POM để nội suy. Tuy nhiên, **không suy ra một thứ tự ưu tiên tuyệt đối giống nhau cho mọi loại trường**; parent resolution, profile activation, model interpolation và plugin parameter evaluation là các bước khác nhau.

Nếu dùng cùng lệnh kiểm tra với `-Pci` và `-Ddemo.flavor=staging`, cần xem nguồn nào đang được Maven áp dụng ở ngữ cảnh thực tế. Để tránh nhầm khi học, thử từng thay đổi riêng, rồi dùng `help:evaluate` xác nhận kết quả kết hợp.

### 6.4. Xem toàn bộ effective POM

```bash
mvn -f hello-model/pom.xml help:effective-pom
```

Hoặc lưu vào tệp để tìm bằng editor:

```bash
mvn -f hello-model/pom.xml help:effective-pom -Doutput=effective-pom.xml
```

Tệp đầu ra là **bản xem mô hình**, không phải POM nguồn cần commit thay thế `hello-model/pom.xml`. Nếu thêm `-Pci` hoặc thay `-D`, hãy dùng cùng tham số khi tạo bản effective POM để có thể so sánh.

Khi chẩn đoán, thường chỉ cần so những vùng liên quan:

- `groupId`, `artifactId`, `version` của child sau kế thừa.
- `<properties>`, nhất là property mà plugin đang sử dụng.
- `<build><finalName>` và những cấu hình plugin hiệu lực.
- `<dependencies>`, `<dependencyManagement>` khi thắc mắc phiên bản dependency.
- `<profiles>` / `help:active-profiles` khi điều kiện môi trường có thể khác.

**Giới hạn:** effective POM không bảo đảm mọi placeholder trong toàn bộ cấu hình mọi plugin đã được đánh giá cuối cùng. Một số biểu thức được giải quyết muộn khi plugin được cấu hình/chạy, và một số giá trị chưa định nghĩa có thể còn nguyên. Hãy kiểm tra thêm hành vi goal và đầu ra thực tế.

## 7. Kế thừa và nội suy: tại sao thứ tự có ý nghĩa?

Một khả năng hữu ích của Maven là **parent có thể sử dụng property mà child ghi đè** trong những trường được nội suy sau kế thừa.

Ví dụ POM cha chứa:

```xml
<properties>
    <demo.flavor>local</demo.flavor>
</properties>
<build>
    <finalName>${project.artifactId}-${demo.flavor}</finalName>
</build>
```

POM con có thể khai báo:

```xml
<properties>
    <demo.flavor>custom</demo.flavor>
</properties>
```

Trong mô hình con, giá trị property riêng của con được áp dụng, nên `finalName` có thể trở thành `hello-model-custom`. Cơ chế này khác với việc lấy một chuỗi đã nội suy sẵn từ mô hình parent rồi dùng nguyên xi cho mọi module.

Nhưng **không phải mọi khái niệm đều kế thừa**:

- `artifactId` của child phải khai báo riêng; nó không được suy từ `artifactId` của parent.
- `packaging` của child có mặc định của chính dự án (thông thường là `jar`) nếu không khai báo; parent thường dùng `pom`.
- `<modules>` của aggregator mô tả những module thuộc reactor, **không phải danh sách dependency hoặc tọa độ kế thừa**.
- Những profile khai báo trong parent **không được kế thừa như một tập profile để child kích hoạt lại độc lập**. Maven đánh giá profile tại POM chứa profile rồi kế thừa **tác động của profile đã hoạt động** trong những phần cấu hình hỗ trợ.

Ví dụ nếu parent có một profile tạo property `demo.flavor=release` và profile đó hoạt động, tác động của nó có thể ảnh hưởng tới mô hình con theo quy tắc kế thừa. Tuy nhiên profile cùng `id` trong child không mặc nhiên được kích hoạt chỉ vì một profile trùng `id` trong parent đang hoạt động.

Khi debug, cần hỏi **biểu thức được đánh giá cho mô hình nào** (cha hay con) và **giá trị đã bị ghi đè ở cấp nào**. Cùng tên property có thể có giá trị khác nhau ở hai module do inheritance, profile và user property.

## 8. Profile activation xảy ra trước nội suy đầy đủ

Profile có thể được kích hoạt bằng `-P` hoặc tự động theo điều kiện như JDK, OS, thuộc tính và tệp. Ví dụ profile tự kích hoạt theo user property:

```xml
<profiles>
    <profile>
        <id>quality</id>
        <activation>
            <property>
                <name>runQuality</name>
                <value>true</value>
            </property>
        </activation>
        <properties>
            <demo.qualityLevel>strict</demo.qualityLevel>
        </properties>
    </profile>
</profiles>
```

Đoạn XML này đặt bên trong `<project>`. Khi lệnh truyền:

```bash
mvn -DrunQuality=true validate
```

profile `quality` có thể được kích hoạt và đưa `demo.qualityLevel=strict` vào mô hình áp dụng. Khóa `runQuality` ở điều kiện được đánh giá từ các nguồn phù hợp cho **activation**. Không được mặc định rằng một property chỉ khai báo trong chính `<properties>` của POM sẽ có thể dùng như user/system property để kích hoạt profile ở thời điểm này.

Đối với điều kiện dựa vào file:

```xml
<activation>
    <file>
        <exists>${project.basedir}/local.flag</exists>
    </file>
</activation>
```

Đây là **ví dụ cần cảnh giác**, bởi đánh giá điều kiện file xảy ra trước nội suy mô hình đầy đủ: Maven 3 hỗ trợ một tập biến giới hạn như `${basedir}`, system/user properties và một số biểu thức môi trường phù hợp; **không nên dựa vào `${project.basedir}` hoặc property POM tùy ý trong trường `<activation><file>` như khi nội suy các trường build thông thường**. Dùng đường dẫn tương đối đơn giản hoặc cú pháp được tài liệu phiên bản Maven xác nhận.

Ví dụ an toàn, rõ ràng hơn cho dự án:

```xml
<activation>
    <file>
        <exists>local.flag</exists>
    </file>
</activation>
```

Khi Maven đánh giá activation, sự tồn tại của file cần được xét theo base directory và quy tắc phiên bản tương ứng; đừng giả định nó nhìn vào một file ở thư mục làm việc khác chỉ vì terminal đang ở đó.

**Điểm cốt lõi:** profile activation và model interpolation là **hai cơ chế riêng có thời điểm khác nhau**. Nếu muốn bật profile chắc chắn cho một lệnh, dùng `-Pprofile-id`; nếu muốn activation tự động theo môi trường, chỉ dùng các biến được hỗ trợ trong điều kiện của phiên bản Maven đang chạy.

## 9. Thứ tự ưu tiên thuộc tính: hiểu theo ngữ cảnh

Câu hỏi thường gặp: “Nếu cùng một khóa `demo.flavor` xuất hiện ở parent, child, profile và `-D`, Maven chọn giá trị nào?”

Với các property thông thường được nội suy vào POM, có thể nhớ các quy tắc thực dụng sau:

1. **Child có thể ghi đè giá trị kế thừa từ parent** ở `<properties>` bằng cách khai báo cùng khóa.
2. **Profile đang hoạt động** có thể đưa thuộc tính vào mô hình và ghi đè các giá trị ở nơi nó được áp dụng, theo quy tắc hợp nhất profile.
3. **User property từ `-Dkey=value`** thường được ưu tiên khi nội suy khóa tương ứng; kiểm tra bằng `help:evaluate` vì biểu thức được giải quyết trong nhiều ngữ cảnh.
4. **System properties/environment** là những nguồn có sẵn, nhưng tên biến và cú pháp tham chiếu có quy tắc riêng; không tự coi `env.MY_VAR` và `MY_VAR` là một khóa.
5. **Trường model như `project.version`** là giá trị thuộc mô hình dự án. Không nên dùng một property tùy ý cùng tên để “ghi đè” tọa độ dự án ở mọi giai đoạn.

Ví dụ, giả sử parent có:

```xml
<properties>
    <demo.flavor>local</demo.flavor>
</properties>
```

và child có:

```xml
<properties>
    <demo.flavor>team</demo.flavor>
</properties>
```

Khi không có profile/`-D` khác tác động, mô hình child thường dùng `team`; mô hình parent vẫn dùng cấu hình parent của chính nó. Nếu lệnh dùng `-Ddemo.flavor=staging`, nội suy ở child có thể dùng `staging`.

**Không viết quy tắc “một thứ tự ưu tiên duy nhất cho mọi nơi”** vì Maven còn có:
- thứ tự hợp nhất parent/child;
- kích hoạt profile trước model interpolation;
- nội suy expression khi cấu hình plugin goal;
- dependencyManagement và pluginManagement;
- nguồn user settings, system properties, environment;
- hạn chế đối với các trường tọa độ phải biết sớm.

Khi mâu thuẫn, chạy cùng POM/CLI/profiles như build thật rồi kiểm tra bằng `help:evaluate`, `help:active-profiles` và `help:effective-pom`.

## 10. Nội suy POM khác resource filtering

Một nhầm lẫn phổ biến là: “Đã khai báo `<properties>` trong POM, vậy Maven sẽ tự thay mọi `${...}` trong mọi tệp của dự án.”

**Không đúng.** Interpolation trong mô hình Maven là việc xử lý **cấu hình POM và các expression hỗ trợ**. Nội dung tệp nguồn `.java`, `.properties`, `.xml` hoặc README **không mặc nhiên được thay thế** chỉ vì có property trong POM.

Ví dụ có tệp `src/main/resources/app.properties`:

```properties
app.name=${project.artifactId}
app.flavor=${demo.flavor}
```

Nếu resource filtering không được bật, các chuỗi `${project.artifactId}` và `${demo.flavor}` có thể được chép nguyên vào output. Muốn thay giá trị khi xử lý resources, cần cấu hình Maven Resources Plugin phù hợp, ví dụ trong POM:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>true</filtering>
        </resource>
    </resources>
</build>
```

Đây là đoạn cấu hình trong `<project>`, không phải POM hoàn chỉnh. Khi bật filtering, plugin có thể thay các token hỗ trợ trong tài nguyên. Cần thận trọng với tệp nhị phân, ký tự escape, thông tin bí mật và khác biệt định dạng token.

Tương tự, **Maven không nội suy mã Java nguồn**. Ví dụ Java:

```java
System.out.println("${demo.flavor}");
```

nếu được biên dịch như văn bản Java thông thường thì in ra chính chuỗi `${demo.flavor}`. Muốn ứng dụng sử dụng giá trị build-time hoặc runtime, cần đưa nó qua cơ chế phù hợp như resource filtering, generated sources, tham số hệ thống hoặc cấu hình ứng dụng. Đây là tầng xử lý khác với model interpolation.

## 11. Vì sao effective POM không phải “toàn bộ sự thật” của build?

Maven Help Plugin hỗ trợ nhìn thấy phần lớn mô hình cuối, nhưng một lệnh build thật còn có:

- **Lifecycle bindings:** `packaging` quyết định những goal plugin nào được gắn mặc định vào các phase. Các mặc định này không nhất thiết tương đương một dòng tự viết trong POM nguồn.
- **Plugin parameter evaluation:** các tham số của plugin có thể đọc giá trị thuộc tính, mặc định goal và ngữ cảnh thực thi khi plugin được gọi.
- **Dependency resolution:** effective POM mô tả dependency, nhưng việc tìm artifact thực tế còn phụ thuộc repository, mirror, local cache và mạng.
- **Toolchain/JDK:** cùng cấu hình compiler release nhưng JDK chạy Maven hoặc toolchain được chọn khác nhau có thể khiến build lỗi.
- **Tài nguyên ngoài mô hình:** biến môi trường, secrets, file trên disk hoặc dịch vụ bên ngoài có thể ảnh hưởng plugin.
- **Profile theo môi trường:** profile kích hoạt vì JDK/OS hoặc file có thể làm effective model khác khi chạy trên CI và máy cá nhân.

Vì thế việc có `BUILD SUCCESS` chưa thay thế việc xác minh kết quả test và artifact; tương tự, việc thấy một giá trị đẹp trong effective POM chưa chứng minh plugin đã thực thi đúng trong mọi môi trường.

**Effective settings** cũng khác **effective POM**:

- `mvn help:effective-settings` hiển thị settings đã tổng hợp (mirror, proxy, servers, localRepository, một số profile settings).
- `mvn help:effective-pom` hiển thị mô hình dự án đã hình thành từ POM và các nguồn liên quan.

Nếu gặp lỗi tải dependency qua mirror, kiểm tra settings là cần thiết; nếu nghi ngờ property, plugin config hoặc kế thừa parent, effective POM hữu ích hơn. Nhiều sự cố phải kiểm tra cả hai.

## 12. Chẩn đoán khi thuộc tính không được nội suy như mong đợi

### Tình huống A: vẫn thấy `${demo.flavor}` nguyên văn

Nguyên nhân có thể là không có định nghĩa property trong ngữ cảnh đang được dùng, tên khóa sai hoặc expression đặt trong trường không hỗ trợ nội suy theo cách mong đợi.

Cách kiểm tra:

```bash
mvn -f hello-model/pom.xml help:evaluate -Dexpression=demo.flavor -q -DforceStdout
mvn -f hello-model/pom.xml help:effective-pom
```

Xác định property tồn tại, profile có hoạt động không, POM con có ghi đè không. Không vội thêm `${demo.flavor}` vào mọi file hoặc thay chuỗi thủ công.

### Tình huống B: giá trị ở máy cá nhân và CI khác nhau

Kiểm tra lệnh thực tế của mỗi môi trường: `-P`, `-D`, JDK, OS, biến `env.*`, settings và file kích hoạt profile. Dùng các lệnh:

```bash
mvn -version
mvn -f hello-model/pom.xml help:active-profiles
mvn -f hello-model/pom.xml help:effective-pom
```

Nếu cần, thêm `-Pci` hoặc cùng cờ `-D` để tái hiện. Đừng cố sửa POM chỉ vì môi trường đã chọn một profile khác theo chủ đích.

### Tình huống C: parent property không có tác dụng ở con

Kiểm tra:

- POM con có `<parent>` với tọa độ chính xác không?
- `<relativePath>` có trỏ đến parent đúng phiên bản không?
- Child có tự khai báo property cùng khóa không?
- Profile đang hoạt động ở parent/child có ghi đè không?
- Bạn đã dùng `-f` trỏ tới **POM con** khi xem effective POM chưa?

Cùng một `artifactId` trong log không bảo đảm bạn đang xem đúng module; hãy đối chiếu `project.basedir` và `project.artifactId`.

### Tình huống D: profile không kích hoạt theo property POM

Một profile có `<activation><property>` nhưng property chỉ được khai báo trong `<properties>` của cùng POM có thể không kích hoạt như bạn dự đoán. Đây là vấn đề **thời điểm profile activation**. Hãy thử kích hoạt rõ bằng `-Pprofile-id` hoặc dùng user/system property được hỗ trợ.

### Tình huống E: file trong resources vẫn chứa `${...}`

Kiểm tra cấu hình Resources Plugin và `filtering`. `pom.xml` có nội suy thành công không có nghĩa một tệp trong `src/main/resources` đã được filter. Xem file thực trong `target/classes` để xác nhận.

### Tình huống F: dependency hoặc plugin dùng version khác với giá trị mong đợi

Kiểm tra `dependencyManagement`, plugin management, parent POM, import BOM và profile. Một số giá trị liên quan dependency/plugin được hợp nhất theo quy tắc riêng, không chỉ lấy property cùng tên trong POM nguồn.

Có thể dùng:

```bash
mvn -f hello-model/pom.xml help:effective-pom
mvn -f hello-model/pom.xml dependency:tree
```

Goal `dependency:tree` cần Maven Dependency Plugin; nó giúp kiểm tra dependency graph thực tế trong phạm vi plugin hỗ trợ. Đừng chỉ suy ra cây dependency từ `<dependencyManagement>` vì các mục ở đó không tự tạo dependency mới.

### Tình huống G: Maven cảnh báo về biểu thức version

Các trường tọa độ `groupId`/`artifactId`/`version` được dùng để định danh POM và giải quyết parent/dependency. Không thể tùy ý đặt mọi biểu thức `${some.property}` trong `<parent><version>` rồi mong Maven xử lý giống `<name>`. Với mô hình phiên bản CI-friendly, Maven hỗ trợ các dạng đặc biệt như `${revision}`, `${sha1}`, `${changelist}` theo điều kiện phiên bản và quy trình phù hợp.

Nếu cần đổi phiên bản parent hoặc module, hãy dùng cơ chế được Maven hỗ trợ, cập nhật các tham chiếu cần thiết và xác minh bằng effective POM. Không dùng property tùy ý để né việc giữ tọa độ parent nhất quán.

## 13. Các nguyên tắc để POM dễ hiểu và tái lập

1. **Đặt thuộc tính dùng chung tại parent khi thực sự dùng chung.** Ví dụ Java release, encoding và những phiên bản plugin được nhóm thống nhất.
2. **Giữ tọa độ rõ ràng.** Parent phải có định danh có thể giải quyết; child có `artifactId` riêng và kế thừa có chủ đích.
3. **Đặt tên property rõ mục đích.** Ví dụ `maven.compiler.release`, `demo.flavor`; tránh trùng tên với namespace model một cách tùy tiện.
4. **Ưu tiên một nguồn cấu hình cho từng quyết định.** Không rải các giá trị giống nhau ở parent, child, profile và command line nếu không có nhu cầu.
5. **Giới hạn profile theo biến thể thật sự.** Đừng dùng profile để che lỗi dependency hoặc biến build phụ thuộc máy mà không tài liệu.
6. **Tách bí mật khỏi POM.** Dữ liệu xác thực repository thường thuộc user/CI settings hoặc secret manager; tránh đưa token vào POM có thể phát hành.
7. **Pin những plugin quan trọng.** Khi cần build có thể tái lập, quản lý phiên bản plugin và JDK/toolchain phù hợp.
8. **Dùng effective POM như bằng chứng mô hình, không thay thế test.** Chạy goal thật, kiểm tra artifact/test output.
9. **Xác minh cùng tham số như CI.** `-f`, `-P`, `-D` và JDK có thể đổi kết quả.
10. **Giữ thay đổi ở đúng cấp.** Property dùng chung sửa ở parent; cấu hình riêng của module sửa ở child; tùy chọn một lần chạy có thể dùng `-D` khi thích hợp.

## 14. Bài tập tự kiểm tra

**Câu 1.** Parent định nghĩa `demo.flavor=local`, child có profile `ci` đặt `demo.flavor=ci`. Không bật profile và không dùng `-D`, `${demo.flavor}` trong child thường là gì?

**Đáp án:** `local`, được kế thừa từ parent.

**Câu 2.** Với cùng dự án, nếu chạy `mvn -Pci clean package`, `project.build.finalName` dự kiến có hậu tố nào?

**Đáp án:** `-ci`, vì profile đang hoạt động thay đổi property `demo.flavor` được dùng trong `finalName`.

**Câu 3.** Nếu parent khai báo `<finalName>${project.artifactId}-${project.version}</finalName>`, child có artifactId riêng, giá trị dùng cho child là artifactId của ai?

**Đáp án:** ArtifactId của **child**; Maven xử lý cấu hình kế thừa trong mô hình child trước khi nội suy phù hợp.

**Câu 4.** Có `${project.version}` trong POM. Đây là property tùy chỉnh cần tự khai báo trong `<properties>` không?

**Đáp án:** Không. Nó tham chiếu trường version trong mô hình Maven đang có hiệu lực.

**Câu 5.** Tại sao profile kích hoạt bằng một property tự khai báo trong cùng POM có thể không bật?

**Đáp án:** Profile activation diễn ra sớm, trước nội suy POM đầy đủ, và chỉ dùng các nguồn/biểu thức được phép cho activation. Dùng `-P` hoặc user/system property đúng loại để kích hoạt.

**Câu 6.** Một file `src/main/resources/app.properties` còn nguyên chuỗi `${project.artifactId}` dù effective POM đã hiển thị artifactId đúng. Đó có phải lỗi model interpolation không?

**Đáp án:** Không nhất thiết. Resource filtering là cơ chế riêng; cần bật và cấu hình Resources Plugin nếu muốn thay placeholder trong tài nguyên.

**Câu 7.** Bạn chạy `mvn help:effective-pom` ở thư mục root nhưng muốn xem thuộc tính riêng của module con. Cần làm gì?

**Đáp án:** Chỉ định chính xác POM con, ví dụ `mvn -f hello-model/pom.xml help:effective-pom`, cùng profile/`-D` đang dùng khi build.

**Câu 8.** Effective POM có một phiên bản dependency nhưng CI tải dependency thất bại. Vì sao kết quả mô hình chưa đủ?

**Đáp án:** Vì dependency resolution còn phụ thuộc repository, mirror, cache, quyền truy cập và kết nối mạng. Cần kiểm tra `help:effective-settings`, log resolution và cấu hình môi trường.

**Câu 9.** Một POM con có cùng property key ở parent và ở con. Giá trị nào thường được dùng khi nội suy trong mô hình con?

**Đáp án:** Giá trị của con có thể ghi đè giá trị kế thừa của cha; còn profile và `-D` có thể tác động thêm. Hãy kiểm chứng bằng `help:evaluate` thay vì suy đoán.

## Tài liệu tham khảo chính thức

- [Apache Maven – Maven Model Builder](https://maven.apache.org/ref/3.9.11/maven-model-builder/): mô tả các giai đoạn Model Builder, profile, inheritance, interpolation và effective model trong Maven 3.9.
- [Apache Maven – Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): ví dụ POM, inheritance, project interpolation và biến POM.
- [Apache Maven – POM Reference](https://maven.apache.org/pom.html): cấu trúc mô hình và các phần tử `properties`, `build`, `parent`, `profiles`.
- [Apache Maven – Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html): các dạng profile, cách kích hoạt, tác động inheritance và giới hạn điều kiện.
- [Apache Maven Help Plugin – effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): cách xem mô hình POM có hiệu lực.
- [Apache Maven Help Plugin – evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html): cách đánh giá expression cụ thể.
- [Apache Maven Help Plugin – active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html): xác định những profile đang hoạt động.
- [Apache Maven Resources Plugin – Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html): xử lý placeholders trong tệp tài nguyên, khác với nội suy mô hình POM.
- [Apache Maven – CI Friendly Versions](https://maven.apache.org/maven-ci-friendly.html): giới hạn và cú pháp phiên bản `revision`, `sha1`, `changelist`.
