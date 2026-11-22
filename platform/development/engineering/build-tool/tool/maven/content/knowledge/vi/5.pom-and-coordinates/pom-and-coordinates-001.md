# Project Object Model (POM) và cấu trúc XML cơ bản của `pom.xml`

## 1. POM là gì trong Apache Maven?

**POM (Project Object Model)** là mô hình mô tả một dự án Maven, được lưu trong tệp XML có tên **`pom.xml`**. Đây là đầu vào trung tâm để Maven hiểu dự án đang xây dựng: nó có tên và phiên bản nào, tạo loại artifact nào, cần những thư viện gì và cần cấu hình plugin nào khi build.

Đặt `pom.xml` ở **thư mục gốc của dự án hoặc module**. Khi chạy `mvn validate`, `mvn compile`, `mvn test` hay `mvn package` từ thư mục đó, Maven đọc POM, kết hợp cấu hình kế thừa và mặc định, rồi thực hiện những goal tương ứng với vòng đời build. Có thể chỉ định POM khác bằng `mvn -f path/to/pom.xml validate`.

POM chủ yếu mang tính **khai báo (declarative)**: mô tả *dự án là gì và cấu hình như thế nào*. Các pha lifecycle và Maven plugin quyết định *công việc nào sẽ thực thi*. Vì thế không cần viết một danh sách lệnh biên dịch thủ công trong `pom.xml`.

Ví dụ dự án có thể có cấu trúc:

```text
pom-intro/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/maven/App.java
│   │   └── resources/
│   └── test/
│       └── java/
└── target/                   # Maven sinh sau khi build
```

Theo quy ước của Maven, mã Java chính đặt ở `src/main/java`, test ở `src/test/java` và sản phẩm biên dịch thường nằm trong `target`. Không cần khai báo các thư mục này nếu dùng cấu trúc chuẩn.

## 2. Một `pom.xml` tối thiểu và hợp lệ

Mẫu cơ bản dành cho dự án Maven phổ biến sử dụng POM model 4.0.0:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>pom-intro</artifactId>
    <version>1.0.0</version>
</project>
```

Ý nghĩa từng thành phần:

- `<?xml version="1.0" encoding="UTF-8"?>`: khai báo đây là tài liệu XML phiên bản 1.0, sử dụng mã hóa UTF-8. Khai báo XML có thể được lược bỏ trong một số tình huống, nhưng ghi rõ encoding giúp tài liệu dễ kiểm soát.
- `<project>`: **phần tử gốc** của một POM; toàn bộ cấu hình dự án nằm bên trong.
- `xmlns="http://maven.apache.org/POM/4.0.0"`: namespace mặc định của định dạng POM 4.0.0, giúp phân biệt các phần tử `project`, `dependencies`, `build` với phần tử thuộc namespace khác.
- `xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"`: khai báo tiền tố namespace `xsi` để sử dụng thuộc tính `xsi:schemaLocation`.
- `xsi:schemaLocation="... ..."`: một cặp *namespace URI* và *địa chỉ schema XSD* để IDE/công cụ kiểm tra cấu trúc; đây là gợi ý vị trí schema, không phải một repository dùng tải dependency và không bắt buộc Maven phải tải XSD trước mỗi lần build.
- `<modelVersion>4.0.0</modelVersion>`: phiên bản **mô hình POM**, không phải phiên bản Maven đang cài hay phiên bản sản phẩm.
- `<groupId>com.example</groupId>`: định danh nhóm phát hành artifact, thường theo quy ước tên miền đảo ngược.
- `<artifactId>pom-intro</artifactId>`: định danh artifact trong nhóm.
- `<version>1.0.0</version>`: phiên bản của artifact do dự án này tạo ra.
- `</project>`: đóng phần tử gốc; mọi thẻ XML phải được đóng khớp.

Ba trường `groupId`, `artifactId` và `version` hợp thành tọa độ artifact **`com.example:pom-intro:1.0.0`**. Với POM có `<parent>`, `groupId` và `version` có thể được **kế thừa** thay vì khai báo lại; `artifactId` của dự án vẫn cần được xác định. Nếu không chỉ định `<packaging>`, Maven dùng mặc định `jar`.

**Điểm thường nhầm:** `modelVersion=4.0.0` không có nghĩa phải dùng Maven 4, và `version=1.0.0` không phải phiên bản Maven. Một POM model 4.0.0 được dùng rộng rãi với Maven 3.

## 3. Đọc cấu trúc XML của POM cho đúng

XML biểu diễn cấu hình theo **cây phần tử cha–con**. Ví dụ:

```xml
<project>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>sample-library</artifactId>
            <version>1.2.3</version>
        </dependency>
    </dependencies>
</project>
```

Đây chỉ là **đoạn minh họa quan hệ lồng nhau**, không phải `pom.xml` hoàn chỉnh để chạy; `org.example:sample-library:1.2.3` là tọa độ ví dụ, không khẳng định artifact đó tồn tại. Trong cấu trúc này, `dependencies` chứa danh sách các `dependency`; `groupId` bên trong `dependency` chỉ **nhóm của thư viện cần dùng**, không ghi đè `groupId` của project.

Một số quy tắc XML quan trọng:

1. **Thẻ mở và thẻ đóng phải khớp**: `<project> ... </project>`. Phần tử rỗng có thể viết `<tag/>`.
2. **Lồng nhau đúng cấp**: `<dependency>` phải nằm trong `<dependencies>`; `<plugin>` thường nằm trong `<build><plugins>` hoặc vùng quản lý plugin phù hợp.
3. **Phân biệt hoa/thường**: `<groupId>` là tên hợp lệ; `<GroupID>` không đồng nghĩa.
4. **Thoát ký tự XML**: trong văn bản hoặc thuộc tính, ký tự `&` phải viết `&amp;`, ký tự `<` trong văn bản phải viết `&lt;`; nếu cần thể hiện dấu `>` có thể dùng `&gt;`. Không chèn thô `&` trong URL query.
5. **Comment đúng cú pháp**: `<!-- ghi chú -->`. Comment không được chứa chuỗi `--` ở phần thân và không dùng để vô hiệu hóa một khối có comment lồng nhau.
6. **Đường dẫn XML có cấp bậc**: `project/dependencies/dependency` khác `project/build/plugins/plugin/dependencies/dependency`; chỉ dựa vào tên `dependency` là chưa đủ.
7. **Tôn trọng cấu trúc POM**: phần tử phải xuất hiện đúng vị trí mô hình Maven hỗ trợ; đừng tùy tiện đặt `<version>` của dự án bên trong `<build>`.

Các URL namespace không phải địa chỉ đặt project hay server chạy ứng dụng. Chúng chỉ giúp xác định từ vựng XML.

## 4. Các nhóm thẻ thường gặp ở cấp `<project>`

| Thẻ XML | Vai trò | Ghi nhớ |
| --- | --- | --- |
| `modelVersion` | Phiên bản mô hình POM | Với POM 4.0.0, ghi `4.0.0` |
| `groupId` | Định danh nhóm artifact | Có thể kế thừa từ `parent` |
| `artifactId` | Tên định danh artifact | Phải xác định cho project |
| `version` | Phiên bản artifact của project | Có thể kế thừa từ `parent` |
| `packaging` | Kiểu artifact và mapping vòng đời | Mặc định `jar`; thường gặp `pom`, `war` |
| `name` | Tên hiển thị thân thiện | Không thay thế `artifactId` |
| `description`, `url` | Mô tả, liên kết giới thiệu | Metadata, không quyết định đường dẫn nguồn |
| `properties` | Các biến cấu hình/interpolation | Dùng dạng `${ten.thuoc.tinh}` |
| `dependencies` | Các dependency trực tiếp | Mỗi thư viện trong một `dependency` |
| `dependencyManagement` | Quản lý mặc định dependency cho khai báo khác | **Tự nó không thêm** dependency vào classpath |
| `build` | Cấu hình quá trình build, plugin và output | `plugins`, `pluginManagement`, `resources`... |
| `parent` | Khai báo POM cha để kế thừa | Chứa tọa độ POM cha |
| `modules` | Danh sách module của một reactor đa module | Thường trong aggregator POM có `packaging=pom` |
| `profiles` | Những nhóm cấu hình bật có điều kiện | Chỉ dùng khi cần, tránh lạm dụng |

Các thẻ đều là **phần tử**, không phải tham số dòng lệnh. Không cần đặt tất cả chúng vào dự án đơn giản; Maven có **Super POM** và các mặc định để giảm cấu hình lặp.

### Phân biệt `groupId`, `artifactId`, `version` và `packaging`

Ví dụ:

```xml
<groupId>com.example</groupId>
<artifactId>inventory-core</artifactId>
<version>2.1.0</version>
<packaging>jar</packaging>
```

Bốn thẻ trên nằm **trực tiếp trong `<project>`** của POM hợp lệ. Tọa độ cơ bản là `com.example:inventory-core:2.1.0`. Khi đóng gói mặc định, artifact có thể mang tên `inventory-core-2.1.0.jar` dưới `target/`. `packaging` không thay `groupId:artifactId:version`, mà cho biết dạng đóng gói và cách các goal mặc định gắn vào lifecycle.

`groupId` không bắt buộc trùng Java package. Tuy nhiên, dùng tên nhóm hợp lý như `com.example.inventory` giúp nhận diện artifact. `artifactId` cũng không tự định nghĩa tên package Java.

## 5. Ví dụ đầy đủ: POM cho ứng dụng Java 17

Ví dụ dưới đây là **toàn bộ nội dung một `pom.xml` sử dụng được**. Nó cấu hình Maven Compiler Plugin để biên dịch nguồn với mức Java 17:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>pom-intro</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>POM Introduction</name>
    <description>Simple Java 17 application with Maven</description>

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
        </plugins>
    </build>
</project>
```

Đọc ví dụ từ ngoài vào trong:

- `<project>` bao toàn bộ mô tả.
- `groupId/artifactId/version/packaging` nhận diện artifact cần tạo.
- `<name>` và `<description>` bổ sung thông tin cho người đọc/công cụ.
- `<properties>` tập trung cấu hình dùng lại. `maven.compiler.release=17` đặt target Java API/bytecode cho compiler plugin; **máy build vẫn cần JDK phù hợp, ví dụ JDK 17+**.
- `<build><plugins>` khai báo plugin phục vụ build; `maven-compiler-plugin` biên dịch Java. Khóa phiên bản plugin giúp hạn chế sai khác do mặc định thay đổi.
- POM không có `<dependencies>` vì chương trình minh họa chỉ dùng thư viện chuẩn Java. Thiếu `<dependencies>` không phải lỗi.

Dưới thư mục dự án, tạo tệp `src/main/java/com/example/maven/App.java`:

```java
package com.example.maven;

public final class App {
    public static void main(String[] args) {
        System.out.println("Hello from pom.xml");
    }
}
```

Đây là **một chương trình Java độc lập và biên dịch được**. Tên file `App.java` khớp lớp `public class App`; package ánh xạ với đường dẫn dưới `src/main/java`.

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -version
mvn -B -ntp validate
mvn -B -ntp clean package
java -cp target/classes com.example.maven.App
```

Lệnh `mvn -version` giúp kiểm tra Maven và Java đang dùng. `mvn validate` kiểm tra cấu hình dự án ở pha `validate`; nó **không tương đương biên dịch hoặc kiểm thử**. `mvn clean package` dọn output cũ, sau đó thực hiện các pha lifecycle cần thiết và tạo `target/pom-intro-1.0.0.jar` nếu build thành công. Lệnh `java -cp ...` chạy lớp đã biên dịch.

**Stdout chính xác của lệnh `java` cuối cùng**:

```text
Hello from pom.xml
```

Log của các lệnh `mvn` trước đó tùy môi trường và plugin; không đồng nhất với stdout chương trình. Có thể chạy lớp từ JAR thông thường như sau:

```bash
java -cp target/pom-intro-1.0.0.jar com.example.maven.App
```

Vì ví dụ **chưa cấu hình `Main-Class` trong manifest**, không sử dụng `java -jar target/pom-intro-1.0.0.jar` như thể JAR này đã là executable JAR. Thêm manifest hoặc giải pháp đóng gói khác là bước riêng nếu ứng dụng cần chạy bằng `java -jar`.

## 6. Bổ sung `dependencies`: cấu trúc XML lồng nhau

Khi dự án dùng thư viện ngoài, khai báo trực tiếp dưới `<project>`:

```xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

**Đây là đoạn bổ sung để hiểu cấu trúc, không phải một `pom.xml` độc lập.** Có thể chèn khối trên vào POM mẫu ở mục 5 (đúng cấp bên trong `<project>`). Khi khai báo như vậy:
- `dependencies` là **danh sách**; một dự án có thể có nhiều `dependency`.
- Mỗi `dependency` có tọa độ riêng `groupId/artifactId/version`, xác định thư viện được sử dụng.
- `scope=test` cho biết dependency được dùng cho việc biên dịch/chạy test, không mang ý nghĩa là build ứng dụng chính sẽ dùng nó trong runtime.
- Đoạn trên chỉ thêm dependency; muốn **chạy test JUnit** còn cần mã test trong `src/test/java` và cấu hình test runner/plugin hỗ trợ phù hợp.

Đừng nhầm `project/groupId` với `project/dependencies/dependency/groupId`: chúng trùng tên thẻ nhưng **khác vị trí và ý nghĩa**.

Maven có thể tải dependency bắc cầu (transitive dependencies) theo metadata của thư viện. `dependencyManagement` dùng để điều phối phiên bản/cấu hình cho dependency được tham chiếu, đặc biệt trong hệ thống nhiều module; **không tự thêm dependency** chỉ bằng cách quản lý nó.

## 7. Phân biệt `dependencies` và `build/plugins`

Dự án có hai loại “thứ có phiên bản” thường gặp:

| Khối XML | Maven dùng để làm gì? | Ví dụ |
| --- | --- | --- |
| `<dependencies><dependency>...` | Bổ sung thư viện mà mã sản phẩm/test sử dụng | JUnit, thư viện JSON, HTTP client |
| `<build><plugins><plugin>...` | Định nghĩa/cấu hình công cụ thực hiện các bước build | Compiler, Surefire, JAR plugin |

Compiler Plugin là **công cụ build**, không phải thư viện cần import vào code Java. Vì vậy không đưa `maven-compiler-plugin` vào `<dependencies>` để yêu cầu Maven biên dịch.

Ví dụ XML phần plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là **phương án cấu hình plugin minh họa** có thể dùng thay cho cách đặt `maven.compiler.release` trong POM mẫu, chứ không phải một tệp XML độc lập. `<configuration>` chứa tham số riêng của plugin; các thẻ con có ý nghĩa do plugin đó quy định.

`<pluginManagement>` dành cho quản lý phiên bản/cấu hình mặc định của plugin được sử dụng sau này; đưa plugin chỉ vào `pluginManagement` **không bảo đảm** tự phát sinh một lần thực thi mới. Cần hiểu các goal vốn được lifecycle gắn sẵn và các plugin/execution khai báo thực tế.

## 8. `properties` và cách tham chiếu giá trị

`<properties>` là nơi gom các giá trị dùng lại trong POM:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
    <junit.version>5.11.4</junit.version>
</properties>
```

Khi có dependency JUnit, có thể dùng biến:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>${junit.version}</version>
    <scope>test</scope>
</dependency>
```

Maven nội suy `${junit.version}` thành giá trị trong `properties`. Maven còn cung cấp các biểu thức như `${project.groupId}`, `${project.version}` và `${project.basedir}`. Lưu ý cú pháp `${...}` **không phải Java string interpolation**; đây là cơ chế đọc property trong cấu hình Maven.

Không gom mọi chuỗi vào `properties` chỉ để ngắn. Nên tạo property khi có giá trị cần thống nhất nhiều nơi hoặc cấu hình có ý nghĩa rõ ràng.

## 9. Super POM, POM cha và Effective POM

POM trong repository thường **không chứa tất cả cấu hình** mà Maven sẽ dùng. Maven kết hợp nhiều nguồn:

- **Super POM**: cung cấp những thiết lập cơ sở mặc định của Maven, ví dụ quy ước về nguồn, output và một số repository.
- **Parent POM** nếu có: cho phép kế thừa cấu hình, groupId/version, management và những phần khác theo quy tắc Maven.
- **POM hiện tại**: khai báo riêng của module.
- **Profile được kích hoạt**: có thể bổ sung hoặc thay đổi một số cấu hình; activation tùy điều kiện và lệnh chạy.
- **Giá trị mặc định/lifecycle/plugin**: hoàn thiện cách Maven thực thi build.

Muốn xem cấu hình sau khi Maven tính toán, chạy:

```bash
mvn help:effective-pom -Doutput=effective-pom.xml
```

Maven Help Plugin xuất mô hình POM hiệu lực ra file `effective-pom.xml`. Đây là **tệp dùng để kiểm tra**, không cần sửa để quản lý cấu hình; chỉnh `pom.xml` hoặc POM cha mới là cách thay đổi nguồn sự thật. Đừng nhầm file `effective-pom.xml` với file `pom.xml` thật.

### `<parent>` là kế thừa, `<modules>` là tập hợp reactor

Ví dụ một module dùng POM cha:

```xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>platform-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
<artifactId>catalog-service</artifactId>
```

Đây là **đoạn ví dụ nằm trong `<project>` của POM con**, không phải toàn bộ tệp. POM con có thể kế thừa `groupId` và `version` từ POM cha.

Ngược lại, aggregator có thể liệt kê module:

```xml
<packaging>pom</packaging>
<modules>
    <module>catalog-service</module>
    <module>order-service</module>
</modules>
```

Đây cũng chỉ là **đoạn XML** trong một aggregator POM. `<modules>` liệt kê đường dẫn tương đối đến module để Maven đưa chúng vào reactor khi thực thi build từ aggregator; nó **không tự tạo quan hệ kế thừa**, cũng không tự khai báo dependency giữa các module. Parent POM và aggregator có thể là cùng một project, nhưng về mặt khái niệm vẫn là **hai quan hệ khác nhau**.

## 10. Thao tác và lệnh kiểm tra POM

Bắt đầu từ gốc dự án có `pom.xml`:

```bash
mvn -version
mvn validate
mvn help:effective-pom -Doutput=effective-pom.xml
mvn clean package
```

Ý nghĩa:

1. `mvn -version`: xác minh bản Maven và Java đang được terminal sử dụng.
2. `mvn validate`: nạp POM và chạy pha `validate`. Nếu XML sai cú pháp hoặc thiếu mô hình/tọa độ bắt buộc, Maven thường dừng sớm.
3. `mvn help:effective-pom ...`: xem cấu hình Maven thực tế sau khi kế thừa, nội suy và áp dụng profile liên quan.
4. `mvn clean package`: thực hiện build theo lifecycle và plugin; nó có thể thất bại vì mã nguồn, test, JDK, plugin hoặc network dù POM vẫn là XML hợp lệ.

Maven cũng hỗ trợ chỉ rõ file POM:

```bash
mvn -f ./pom.xml validate
```

`-f` hữu ích khi chạy từ vị trí khác hoặc dùng POM có đường dẫn đặc biệt. Trong repository đa module, chọn đúng `pom.xml` của aggregator hoặc module cần kiểm tra để tránh hiểu nhầm kết quả.

**Hai mức kiểm tra khác nhau:**
- *XML well-formed*: đóng mở thẻ đúng, dấu ngoặc/thuộc tính/escape đúng.
- *Maven model hợp lệ*: những thẻ đó nằm đúng vị trí, đúng kiểu và có đủ thông tin để Maven phân giải project.

Một file có XML hợp lệ vẫn có thể là POM sai mô hình hoặc khai báo dependency/plugin không phân giải được.

## 11. Lỗi phổ biến khi tự viết `pom.xml`

| Triệu chứng hoặc lỗi | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| `Non-parseable POM` | Sai cú pháp XML: thiếu thẻ đóng, ký tự `&` chưa escape, comment không hợp lệ | Kiểm tra số dòng/cột Maven báo, đóng thẻ và escape |
| `'modelVersion' is missing` | Không khai báo `<modelVersion>4.0.0</modelVersion>` | Bổ sung vào `<project>` đúng cấu trúc |
| `'artifactId' is missing` hoặc yêu cầu tọa độ | Thiếu trường nhận diện project | Kiểm tra `groupId/artifactId/version` và `parent` |
| `Unrecognised tag: ...` | Dùng tên thẻ sai hoặc đặt ở cấp XML không hợp lệ | Đối chiếu POM reference và vị trí phần tử |
| `'dependencies.dependency.version' is missing` | Dependency thiếu version mà không được quản lý qua `dependencyManagement` | Khai báo version hoặc cấu hình quản lý phiên bản hợp lệ |
| `Non-resolvable parent POM` | Sai tọa độ parent, đường dẫn `relativePath`, repository hoặc mạng | Kiểm tra parent, cấu trúc repository và đường dẫn |
| `Could not resolve dependencies` | Artifact/version không có ở repository, proxy/mạng hoặc credentials | Xác nhận tọa độ và nguồn tải, không sửa ngẫu nhiên tên package |
| `invalid target release: 17` | Maven Compiler Plugin chạy trên JDK không hỗ trợ release 17 | Kiểm tra `mvn -version`/`JAVA_HOME` và dùng JDK phù hợp |
| `No sources to compile` | Chưa có mã Java ở `src/main/java` hoặc module chọn sai | Đối chiếu source root; không phải lúc nào cũng là lỗi POM |
| `no main manifest attribute` khi `java -jar` | JAR chưa cấu hình entrypoint | Dùng `java -cp ... <fully-qualified-class>` hoặc cấu hình manifest khi cần |
| IDE báo lỗi schema namespace | XML namespace/schemaLocation sai hoặc IDE không tải được XSD | Kiểm tra URL schema, cú pháp XML và tình trạng mạng/IDE |

Không coi mọi lỗi build là lỗi XML. `mvn validate` thành công mới chỉ chứng minh Maven đọc và xử lý được những phần cấu hình cần cho pha đó, chưa chứng minh toàn bộ dependency, code và test đúng.

## 12. Cách tổ chức và bảo trì POM dễ đọc

- **Giữ POM nhỏ, rõ ràng**: bắt đầu từ POM tối thiểu rồi thêm `dependencies`, `properties`, `build/plugins` khi phát sinh nhu cầu.
- **Dùng encoding UTF-8** và thụt dòng nhất quán; phân nhóm trường theo chức năng để dễ review diff.
- **Ghi phiên bản plugin rõ ràng**, nhất là plugin quan trọng đối với build; phiên bản dependency cũng phải xác định được trực tiếp hoặc qua dependency management.
- **Không cất mật khẩu/token trong POM**: cấu hình thông tin đăng nhập repository qua `settings.xml` và cơ chế secrets thích hợp; tránh commit thông tin nhạy cảm.
- **Không lạm dụng thay đường dẫn mặc định**: dùng `src/main/java`, `src/test/java` và `target` giúp Maven, IDE và CI hiểu cùng một cấu trúc.
- **Dùng `mvn help:effective-pom` khi bị bất ngờ bởi cấu hình kế thừa**; sửa đúng POM nguồn thay vì sửa output.
- **Kiểm tra commit thay đổi POM bằng build thực tế**: thay dependency, plugin hoặc Java release cần chạy các pha phù hợp, không chỉ xem file “đúng XML”.
- **Phân biệt POM và các tệp khác**: `settings.xml` thường là cấu hình theo máy/người dùng; `mvnw`/`mvnw.cmd` là Maven Wrapper; `pom.xml` là mô hình cấu hình của dự án.

## 13. Tự kiểm tra kiến thức

1. Vì sao `modelVersion` là `4.0.0` nhưng `version` của dự án có thể là `1.0.0` hoặc `2.1.0`?
2. Một thư viện có `groupId/artifactId/version` riêng: các thẻ đó phải nằm ở đâu để thể hiện dependency, thay vì tọa độ của project?
3. Nếu không có `packaging` trong POM Java thông thường, Maven dùng loại packaging nào?
4. Khi POM có `<parent>`, trường nào của project có thể được kế thừa, và thẻ nào vẫn xác định project con?
5. Vì sao một file XML đóng thẻ đúng vẫn có thể khiến Maven báo lỗi `Unrecognised tag`?
6. Lệnh nào giúp xem cấu hình sau kế thừa khi trong `pom.xml` không thấy một thiết lập đang có hiệu lực?
7. Vì sao có `<dependencyManagement>` không đồng nghĩa thư viện đó xuất hiện trên classpath?
8. Với POM Java 17 ở mục 5, lệnh nào biên dịch và lệnh nào chạy `com.example.maven.App`?

**Điều cần nắm vững:** `pom.xml` là bản mô tả XML có cấu trúc của project Maven. `<project>` là gốc, `modelVersion` định danh phiên bản mô hình, tọa độ `groupId:artifactId:version` nhận diện artifact, còn các nhánh `dependencies`, `properties`, `build` và quan hệ `parent/modules` bổ sung cấu hình. Maven kết hợp những khai báo này với quy ước và lifecycle để thực thi build.

## Tài liệu chính thức

- [Apache Maven – Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven – POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven – Naming Maven Coordinates](https://maven.apache.org/guides/mini/guide-naming-conventions.html)
- [Apache Maven – Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven – Getting Started Guide](https://maven.apache.org/guides/getting-started/)
