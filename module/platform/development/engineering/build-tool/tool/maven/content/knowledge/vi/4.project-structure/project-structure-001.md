# pom.xml và thư mục gốc của một dự án Maven

Một dự án Maven thường bắt đầu bằng một tệp `pom.xml`. Tệp này cho Maven biết **đang build dự án nào, dự án dùng những thư viện và plugin gì, cách đóng gói ra sao**. Thư mục chứa `pom.xml` là **thư mục gốc của dự án Maven** (project base directory, thường được gọi là `project.basedir`). Từ điểm gốc này, Maven xác định các đường dẫn mặc định như `src/main/java`, `src/test/java` và `target`.

Hai ý quan trọng cần nắm từ đầu:

1. **`pom.xml` mô tả dự án và cách Maven build dự án.** Nó là mô hình cấu hình XML, không phải tệp script chạy từng dòng lệnh.
2. **Thư mục gốc của dự án là mốc tính đường dẫn.** Việc mở terminal ở một thư mục khác không tự làm các thư mục `src` của dự án đổi vị trí, nếu bạn vẫn yêu cầu Maven build đúng POM bằng `-f`.

Trong repository nhiều module, mỗi module Maven có thể có `pom.xml` và `project.basedir` riêng. Không phải lúc nào thư mục gốc Git cũng trùng với thư mục gốc Maven.

## 1. POM là gì và Maven tìm nó ở đâu?

**POM** là viết tắt của *Project Object Model*. Với Maven 3, tệp POM thông thường có tên `pom.xml` và sử dụng mô hình `modelVersion` `4.0.0`. Khi chạy một lệnh như:

```bash
mvn package
```

Maven mặc định tìm POM trong thư mục làm việc hiện tại, đọc thông tin dự án và thực thi các plugin tương ứng với các pha của vòng đời build.

Ví dụ:

```text
workspace/
└── hello-maven/                 <- thư mục gốc dự án Maven
    ├── pom.xml                  <- POM của hello-maven
    ├── src/
    │   └── main/
    │       └── java/
    └── target/                  <- xuất hiện sau khi build
```

Nếu terminal đang ở `workspace/hello-maven`, lệnh `mvn package` làm việc với `hello-maven/pom.xml`. Nếu terminal đang ở `workspace` nhưng không có `workspace/pom.xml`, lệnh này thường báo lỗi thiếu POM/dự án. Bạn có thể chỉ định rõ POM:

```bash
mvn -f hello-maven/pom.xml package
```

Tùy chọn `-f` (hay `--file`) cho phép dùng một tệp POM khác, hoặc một thư mục chứa `pom.xml`. Đường dẫn `hello-maven/pom.xml` ở ví dụ được tính từ vị trí chạy lệnh; sau khi chọn được POM, các đường dẫn dự án thông thường được tính từ thư mục chứa POM đó.

**Phân biệt ba loại “gốc”:**

- **Working directory (cwd):** nơi terminal/tiến trình được khởi chạy. Kiểm tra bằng `pwd` (Linux/macOS) hoặc `Get-Location` (PowerShell).
- **Project basedir:** thư mục chứa tệp POM được Maven chọn; dùng trong biểu thức `${project.basedir}`.
- **Repository/Git root:** thư mục gốc quản lý phiên bản Git; có thể chứa một hoặc nhiều dự án Maven độc lập.

`MAVEN_HOME` (nơi cài Maven), `~/.m2` (cấu hình và repository riêng người dùng) và `project.basedir` là các vị trí **khác nhau**.

## 2. Những thành phần cơ bản của `pom.xml`

Một POM Maven độc lập tối thiểu có cấu trúc:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>hello-maven</artifactId>
    <version>1.0.0</version>
</project>
```

Ý nghĩa:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `<project>` | Phần tử gốc của mô hình POM. | Bao toàn bộ nội dung cấu hình. |
| `<modelVersion>` | Phiên bản mô hình POM. | `4.0.0`; **không phải** phiên bản Maven đã cài. |
| `<groupId>` | Định danh nhóm/tổ chức phát hành. | `com.example` |
| `<artifactId>` | Tên artifact/dự án trong nhóm. | `hello-maven` |
| `<version>` | Phiên bản artifact. | `1.0.0` hoặc `1.0.0-SNAPSHOT` |
| `<packaging>` | Kiểu đóng gói, tùy chọn. | `jar` (mặc định), `war`, `pom`... |

Ba tọa độ `groupId:artifactId:version` nhận diện artifact Maven; với ví dụ trên là `com.example:hello-maven:1.0.0`. Mặc định `packaging` là `jar` nếu không khai báo. Tên tệp JAR đầu ra thường được ghép từ `artifactId` và `version`, chẳng hạn `hello-maven-1.0.0.jar`, trừ khi build được cấu hình khác.

Trong POM con kế thừa một POM cha, `groupId` và `version` có thể được kế thừa nên không nhất thiết phải viết lại. POM độc lập ở ví dụ trên khai báo đủ cả ba tọa độ để dễ hiểu.

### POM còn mô tả những gì?

Các phần thường xuất hiện khi dự án phát triển lớn hơn:

- `<name>`, `<description>`, `<url>`: thông tin nhận diện và tài liệu dự án.
- `<properties>`: các thuộc tính dùng lại, ví dụ phiên bản Java hoặc mã hóa nguồn.
- `<dependencies>`: các thư viện cần dùng và phạm vi phụ thuộc như `compile`, `test`.
- `<dependencyManagement>`: quản lý phiên bản và một số cấu hình dependency để các nơi khai báo dùng lại; **không tự thêm dependency** vào classpath chỉ vì nó được liệt kê ở đây.
- `<build>` và `<plugins>`: cấu hình plugin thực thi compile, test, package và các tác vụ khác.
- `<build><pluginManagement>`: quản lý phiên bản/cấu hình plugin cho nơi sử dụng; không đồng nghĩa mọi plugin ở đây sẽ được chạy.
- `<parent>`: kế thừa cấu hình từ một POM cha.
- `<modules>`: liệt kê các module tham gia một build nhiều module.
- `<profiles>`: các biến thể cấu hình có điều kiện.

POM thuộc nguồn dự án và thường được commit vào Git. Các bí mật riêng của tài khoản như mật khẩu repository hoặc token CI không nên ghi trực tiếp vào `pom.xml`; dùng user settings, biến môi trường và cơ chế secret thích hợp.

## 3. Cấu trúc thư mục chuẩn tính từ project root

Maven ưu tiên **convention over configuration**: nếu đặt tệp vào các vị trí tiêu chuẩn, phần lớn plugin cơ bản hiểu chúng mà không cần khai báo lại đường dẫn.

```text
hello-maven/
├── pom.xml
├── README.md                         <- tài liệu dự án (tùy chọn)
├── .gitignore                        <- quy tắc Git (tùy chọn)
├── .mvn/                              <- cấu hình Maven riêng dự án (tùy chọn)
│   ├── maven.config
│   ├── jvm.config
│   └── wrapper/
│       └── maven-wrapper.properties
├── mvnw                               <- Maven Wrapper Linux/macOS (tùy chọn)
├── mvnw.cmd                           <- Maven Wrapper Windows (tùy chọn)
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/demo/
│   │   │       └── App.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
│       ├── java/
│       │   └── com/example/demo/
│       │       └── AppTest.java
│       └── resources/
│           └── test-data.txt
└── target/                            <- kết quả build, thường không commit
    ├── classes/
    ├── test-classes/
    └── hello-maven-1.0.0.jar
```

Sơ đồ minh họa những mục **có thể có** sau khi build, không yêu cầu tạo tất cả trước. Ý nghĩa các vị trí:

| Vị trí tương đối với `project.basedir` | Mục đích |
| --- | --- |
| `pom.xml` | Mô hình cấu hình của chính dự án này. |
| `src/main/java` | Mã Java ứng dụng/thư viện; các thư mục bên trong thường theo tên package. |
| `src/main/resources` | Tài nguyên được đưa vào classpath chính, ví dụ cấu hình và tệp dữ liệu. |
| `src/test/java` | Mã kiểm thử Java. |
| `src/test/resources` | Tài nguyên dành cho kiểm thử. |
| `target/classes` | Các `.class` và tài nguyên chính sau khi biên dịch/xử lý resources. |
| `target/test-classes` | Class và tài nguyên kiểm thử sau khi biên dịch kiểm thử. |
| `target/` | Thư mục đầu ra của build (mặc định), có thể chứa JAR, WAR, báo cáo và kết quả trung gian. |
| `.mvn/` | Tùy chọn Maven/JVM riêng cho dự án, extensions và cấu hình Wrapper khi được sử dụng. |
| `mvnw`, `mvnw.cmd` | Script Maven Wrapper, cho phép dự án chọn một bản phân phối Maven cụ thể. |

Với dự án đóng gói `war`, `src/main/webapp` còn là vị trí tiêu chuẩn cho tài nguyên web. Với plugin chuyên biệt có thể có các thư mục khác. Không nên mặc định mọi thư mục trùng tên `src/anything` sẽ được Maven build: các nguồn tùy chỉnh phải được plugin hoặc cấu hình build hỗ trợ.

**Quy tắc quan trọng:** `src` chứa đầu vào do người phát triển quản lý; `target` là kết quả tạo ra bởi build. Lệnh `mvn clean` thường xóa `target` mặc định rồi build sau sẽ tạo lại. Vì thế không lưu mã nguồn hoặc dữ liệu quan trọng chỉ trong `target` và thường thêm `target/` vào `.gitignore`.

## 4. Ví dụ hoàn chỉnh: tự tạo dự án Maven dùng Java 17

Để thấy rõ quan hệ giữa POM, project root và đầu ra, hãy tạo cấu trúc:

```text
hello-maven/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── demo/
                        └── App.java
```

Bạn có thể tự tạo các thư mục bằng IDE/File Explorer hoặc chạy lệnh sau trước khi chép nội dung tệp.

Linux/macOS:

```bash
mkdir -p hello-maven/src/main/java/com/example/demo
cd hello-maven
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path hello-maven/src/main/java/com/example/demo
Set-Location hello-maven
```

### 4.1. Nội dung `pom.xml` tại gốc dự án

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>hello-maven</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
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
    </build>
</project>
```

Giải thích những điểm liên quan trực tiếp đến cách build:

- `packaging=jar` yêu cầu đóng gói đầu ra thành JAR. Trong ví dụ, viết rõ giá trị này dù nó cũng là mặc định.
- `maven.compiler.release=17` yêu cầu Compiler Plugin biên dịch với mức Java 17. Máy chạy build cần JDK hỗ trợ Java 17 và được Maven chọn đúng.
- Hai phiên bản plugin được chỉ định để kết quả ít bị ảnh hưởng bởi phiên bản mặc định của Maven. Plugin có thể được tải từ repository trong lần build đầu; cần kết nối mạng nếu cache chưa có.
- Không cần ghi đường dẫn `src/main/java` hoặc `target` trong POM vì Maven đã có quy ước mặc định. Khi cần khác, có thể tùy chỉnh `<build><sourceDirectory>` hoặc `<build><directory>`, nhưng chỉ nên làm khi có lý do rõ ràng.

### 4.2. Nội dung `src/main/java/com/example/demo/App.java`

```java
package com.example.demo;

public final class App {
    public static void main(String[] args) {
        System.out.println("Hello Maven");
    }
}
```

Vị trí tệp `src/main/java/com/example/demo/App.java` tương ứng với khai báo package `com.example.demo`. Dấu `.` trong package trở thành dấu phân cách thư mục `/` trong cấu trúc nguồn Java thông thường.

### 4.3. Build và chạy

Trong thư mục `hello-maven` (nơi chứa `pom.xml`):

```bash
mvn -version
mvn validate
mvn clean package
java -cp target/hello-maven-1.0.0.jar com.example.demo.App
```

Lệnh cuối chạy lớp `com.example.demo.App` đã được biên dịch và đóng trong JAR. **Stdout chính xác của chương trình Java**:

```text
Hello Maven
```

Các dòng log từ lệnh Maven phía trước phụ thuộc phiên bản, máy và trạng thái dependency cache, nên không có một mẫu stdout Maven cố định áp dụng cho mọi môi trường.

Sau khi `mvn clean package` thành công, cấu trúc đầu ra có thể bao gồm:

```text
hello-maven/
└── target/
    ├── classes/
    │   └── com/example/demo/App.class
    ├── maven-archiver/
    └── hello-maven-1.0.0.jar
```

**Chú ý:** JAR trên được tạo dưới dạng JAR thư viện/thông thường; nó **không mặc nhiên có** `Main-Class` trong manifest. Vì thế ví dụ dùng `java -cp ... com.example.demo.App`. Muốn chạy `java -jar` thì cần cấu hình manifest hoặc plugin đóng gói phù hợp.

Nếu máy chưa có Maven trên `PATH`, có thể dùng Maven Wrapper của dự án (nếu được cung cấp): `./mvnw clean package` trên Linux/macOS hoặc `.\mvnw.cmd clean package` trong PowerShell. Wrapper không xuất hiện tự động chỉ vì có `pom.xml`.

## 5. Maven chọn đường dẫn tương đối như thế nào?

Đối với dự án một POM, các đường dẫn mặc định có thể hiểu như sau:

```text
${project.basedir}
├── pom.xml
├── src/main/java            -> mã nguồn chính
├── src/test/java            -> mã nguồn kiểm thử
└── target/                  -> đầu ra
```

Khi Maven xử lý một POM được chỉ định, `${project.basedir}` thường là thư mục chứa POM đó. Maven có thể dùng thuộc tính này trong các cấu hình đường dẫn:

```xml
<properties>
    <example.docsDir>${project.basedir}/docs</example.docsDir>
</properties>
```

Ở đây `${project.basedir}` là **biểu thức Maven** được nội suy khi xử lý POM, không phải biến shell như `$PWD` và không phải `${user.home}`. Sử dụng đường dẫn tương đối trong cấu hình plugin thường được giải nghĩa theo quy tắc riêng của từng tham số; cần kiểm tra mô tả plugin nếu hành vi không như dự đoán.

Giả sử có:

```text
work/
├── docs/
└── service-a/
    ├── pom.xml
    └── src/main/java/...
```

Nếu bạn đang ở `work/` và chạy:

```bash
mvn -f service-a/pom.xml package
```

Maven build dự án `service-a`; nó vẫn đọc mã nguồn mặc định dưới `work/service-a/src/main/java`, không chuyển sang `work/src/main/java`. Tương tự, đầu ra mặc định nằm ở `work/service-a/target`.

### Xác nhận project root thực tế bằng Maven

Chạy trong thư mục dự án, hoặc thêm `-f` nếu đứng nơi khác:

```bash
mvn help:evaluate -Dexpression=project.basedir -q -DforceStdout
```

Kết quả là đường dẫn dự án mà Maven xác định (ví dụ `/home/user/work/service-a`; giá trị thực phụ thuộc máy). Cần Maven Help Plugin; lần đầu có thể phải tải plugin. Có thể dùng thêm:

```bash
mvn help:evaluate -Dexpression=project.artifactId -q -DforceStdout
mvn help:evaluate -Dexpression=project.packaging -q -DforceStdout
```

Lệnh này hữu ích khi IDE, shell hoặc CI chọn sai working directory hay sai POM. Nếu trong repository có nhiều POM, hãy chỉ định `-f` và đối chiếu `project.basedir` trước khi sửa cấu trúc dự án.

## 6. `pom.xml` trong dự án nhiều module

Với dự án Maven nhiều module, thư mục gốc phía trên có thể chứa một **aggregator POM** liệt kê các module. Mỗi module vẫn có thư mục riêng và một POM riêng:

```text
shop-platform/
├── pom.xml                     <- aggregator POM
├── common/
│   ├── pom.xml                 <- POM của module common
│   └── src/main/java/...
└── api/
    ├── pom.xml                 <- POM của module api
    └── src/main/java/...
```

Ví dụ nội dung POM ở `shop-platform/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.shop</groupId>
    <artifactId>shop-platform</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>common</module>
        <module>api</module>
    </modules>
</project>
```

Ở đây `<module>common</module>` là đường dẫn tương đối từ thư mục chứa aggregator POM. Maven sẽ tìm POM của module tại `common/pom.xml`. Tương tự với `api`. Khai báo `<modules>` tạo **aggregation**, để Maven Reactor thu thập và sắp xếp các dự án con khi build từ aggregator; nó không tự tạo thư mục hoặc POM của module.

Lệnh thường dùng:

```bash
# Đứng tại shop-platform/
mvn clean verify

# Chỉ build module api và các module reactor mà api phụ thuộc
mvn -pl :api -am verify
```

`-pl` chọn dự án trong reactor, `-am` yêu cầu build thêm các module cần thiết mà chúng phụ thuộc. Nếu `api` không khai báo dependency tới `common`, `-am` không tự suy ra quan hệ chỉ dựa vào tên/thư mục.

### Aggregator và parent là hai quan hệ khác nhau

**Aggregation** được khai báo bằng `<modules>` ở POM tổng hợp. **Inheritance** được khai báo bằng `<parent>` trong POM con, nhằm kế thừa cấu hình. Một POM có thể đồng thời là aggregator và parent nhưng không bắt buộc.

Ví dụ phần đầu `shop-platform/api/pom.xml` khi muốn kế thừa parent:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.shop</groupId>
        <artifactId>shop-platform</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>api</artifactId>
    <packaging>jar</packaging>
</project>
```

POM `api` kế thừa `groupId` và `version` của parent, nhưng có `artifactId` riêng. `relativePath` trỏ tới tệp POM cha từ vị trí POM con; giá trị mặc định thông dụng của nó là `../pom.xml`. Cấu hình này chỉ giải thích quan hệ kế thừa; `api` chỉ thực sự nằm trong reactor của `shop-platform` khi aggregator liệt kê module phù hợp.

**Điểm dễ nhầm:** thư mục `shop-platform` là gốc của aggregator, còn `shop-platform/api` là `project.basedir` của riêng module `api`. Nếu không cấu hình khác, đầu ra của module `api` nằm ở `shop-platform/api/target`, chứ không tự gom vào `shop-platform/target`.

Một repository Git còn có thể chứa nhiều dự án Maven độc lập mà **không** có aggregator POM. Chỉ nhìn thấy nhiều tệp `pom.xml` chưa đủ để kết luận chúng thuộc một reactor.

## 7. POM bạn viết và effective POM khác nhau

Khi build, Maven không chỉ nhìn văn bản `pom.xml`. Nó tổng hợp mô hình dự án từ:

- POM của chính dự án;
- cấu hình được kế thừa từ parent POM (nếu có);
- **Super POM** với các giá trị mặc định;
- các profile và thuộc tính có hiệu lực trong phiên build.

Kết quả được gọi là **effective POM**. Nó giải thích vì sao một dự án chỉ có POM tối thiểu vẫn biết thư mục nguồn `src/main/java`, thư mục kết quả `target` và cơ chế mặc định của nhiều plugin.

Để xem mô hình sau khi Maven tổng hợp:

```bash
mvn help:effective-pom
```

Nếu chỉ định `-f` cho build thực tế, cũng dùng cùng `-f` khi xem effective POM:

```bash
mvn -f service-a/pom.xml help:effective-pom
```

Lưu ý effective POM có thể dài hơn rất nhiều so với tệp nguồn và có thể chứa nhiều thông tin kế thừa. Không nên chép toàn bộ effective POM để thay `pom.xml` của dự án. Muốn sửa một thiết lập, hãy tìm nơi định nghĩa thực sự trong POM dự án, parent, profile hoặc cấu hình liên quan.

## 8. Phân biệt `pom.xml` với những tệp ở gần project root

| Tệp/thư mục | Có phải POM không? | Ý nghĩa |
| --- | --- | --- |
| `pom.xml` | Có | Mô tả Maven project, dependencies, plugins, packaging, modules. |
| `.mvn/maven.config` | Không | Các cờ Maven CLI mặc định của dự án. |
| `.mvn/jvm.config` | Không | Các tùy chọn JVM chạy Maven, ví dụ giới hạn heap. |
| `.mvn/wrapper/maven-wrapper.properties` | Không | Bản phân phối Maven mà Wrapper chọn. |
| `mvnw`, `mvnw.cmd` | Không | Script khởi chạy Maven thông qua Wrapper. |
| `.git/`, `.gitignore` | Không | Metadata Git và quy tắc bỏ qua tệp; không xác định mặc nhiên project basedir. |
| `settings.xml` ở `~/.m2` | Không | Cấu hình theo người dùng, như mirror, proxy, credentials. |
| `target/` | Không | Đầu ra build, thường là thư mục có thể tái tạo. |

`pom.xml` thuộc phạm vi dự án, còn `~/.m2/settings.xml` thuộc phạm vi tài khoản. Tệp cấu hình Wrapper không thay thế `pom.xml`: Wrapper chọn Maven để chạy, còn POM mô tả dự án được build.

## 9. Những sai lầm thường gặp và cách xử lý

**1. Đứng sai thư mục rồi chạy `mvn package`.** Maven không tìm thấy POM hoặc build một POM khác. Kiểm tra `pwd`/`Get-Location`, mở đúng thư mục gốc, hoặc dùng `mvn -f path/to/pom.xml package`.

**2. Đặt `pom.xml` trong `src/main/java`.** Maven mặc định tìm POM ở project root, không tìm trong thư mục chứa mã Java. Chuyển POM về thư mục gốc muốn dùng; giữ `src/main/java` ở bên dưới.

**3. Nhầm `pom.xml` là nơi lưu mã nguồn Java.** POM mô tả cách build; mã nguồn Java là những tệp `.java` trong cây nguồn. Không viết Java trực tiếp bên trong POM XML.

**4. Thấy `src/main/java` trống rồi tưởng Maven tự tìm mã nguồn ở bất cứ đâu.** Plugin tuân theo các thư mục chuẩn hoặc cấu hình được khai báo rõ. Nếu nguồn ở đường dẫn tùy chỉnh, cần thiết lập plugin/build đúng cách.

**5. Đưa `target/` vào Git hoặc sửa file trong `target/` để làm thay đổi bền vững.** `target` bị tái tạo hoặc xóa khi clean; thay đổi nguồn trong `src` và POM rồi build lại.

**6. Nhầm thư mục chứa `.git` là project root của mọi module.** Trong monorepo, một thư mục con có `pom.xml` riêng; kiểm tra `project.basedir` của đúng module.

**7. Dùng `<modules>` rồi cho rằng các module đã kế thừa mọi dependency/version.** Aggregation và inheritance là hai cơ chế khác nhau. Muốn kế thừa, POM con phải khai báo `<parent>` phù hợp.

**8. Khai báo dependency trong `<dependencyManagement>` rồi tưởng lớp Java đã import được nó.** Khối này chủ yếu quản lý cấu hình dependency; dependency cần dùng vẫn phải nằm trong `<dependencies>` của dự án hoặc được kế thừa theo mô hình áp dụng.

**9. Đổi `MAVEN_HOME` để thay vị trí `pom.xml` hoặc `target`.** Maven Home là nơi cài công cụ Maven. Vị trí của POM quyết định `project.basedir`; vị trí đầu ra có thể được cấu hình ở POM/plugin.

**10. Nhầm tệp JAR đã tạo với JAR chạy được bằng `java -jar`.** Đóng gói `jar` không tự khai báo entry point. Khi chưa có `Main-Class`, hãy dùng `java -cp ... tên.lớp.Main` hoặc cấu hình plugin thích hợp.

## 10. Bài tập tự kiểm tra

**Câu 1.** Có cây thư mục `repo/backend/pom.xml` và `repo/backend/src/main/java`. Terminal đang ở `repo/`. Cần chạy lệnh nào để build `backend` mà không đổi thư mục?

**Gợi ý đáp án:** `mvn -f backend/pom.xml package`. Project basedir được chọn là `repo/backend`; mã nguồn chuẩn vẫn nằm bên dưới `repo/backend/src/main/java`.

**Câu 2.** Một dự án không khai báo `<packaging>`. Maven dùng kiểu đóng gói mặc định nào, và output đi đâu?

**Gợi ý đáp án:** Mặc định là `jar`, đầu ra thường nằm trong `target` của dự án, tức `${project.basedir}/target`, trừ khi cấu hình build thay đổi.

**Câu 3.** Tại sao module `api` có `pom.xml` riêng nhưng vẫn có thể kế thừa phiên bản Java từ POM ở thư mục cha?

**Gợi ý đáp án:** Vì `api/pom.xml` khai báo `<parent>` và kế thừa cấu hình hợp lệ từ POM cha. Việc có tên `api` trong `<modules>` của aggregator tự nó không tạo ra quan hệ kế thừa.

**Câu 4.** Làm sao biết chính xác Maven đang build POM nào khi dự án có nhiều thư mục?

**Gợi ý đáp án:** Kiểm tra đối số `-f`/thư mục chạy; dùng `mvn help:evaluate -Dexpression=project.basedir -q -DforceStdout` và kiểm tra `project.artifactId`. Có thể xem `mvn help:effective-pom` để xác định cấu hình cuối cùng.

## Tài liệu Apache Maven tham khảo

- [Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): vai trò, cú pháp và các thành phần POM; Super POM; parent và aggregation.
- [POM Reference](https://maven.apache.org/pom.html): mô hình XML và các thuộc tính cấu hình Maven.
- [Introduction to the Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html): cấu trúc thư mục và đầu ra mặc định.
- [Maven Getting Started Guide](https://maven.apache.org/guides/getting-started/index.html): quan hệ giữa `pom.xml`, `src` và `${project.basedir}`.
- [Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor và lệnh chọn module.
- [Maven CLI Options](https://maven.apache.org/ref/3.9.7/maven-embedder/cli.html): tùy chọn `-f`, `-pl`, `-am`.
- [Maven Help Plugin – evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html) và [effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): kiểm tra basedir và cấu hình hiệu lực.
- [Maven Compiler Plugin – Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html): tùy chọn `maven.compiler.release`.
