# Super POM và nguồn của các giá trị mặc định trong Maven

## 1. Mục tiêu

Khi bắt đầu một dự án Maven, bạn có thể tạo `pom.xml` chỉ vài dòng mà vẫn thấy Maven nhận diện `src/main/java`, tạo `target/`, tìm dependency ở Maven Central, biên dịch và đóng gói JAR. Những hành vi này **không có nghĩa tất cả cấu hình đều nằm trong tệp `pom.xml` bạn đang mở**. Maven xây dựng một mô hình dự án hiệu lực từ nhiều lớp cấu hình và cơ chế mặc định.

Sau bài này, bạn sẽ:

- Giải thích **Super POM** là gì, quan hệ của nó với POM dự án và parent POM.
- Nhận diện các mặc định quan trọng: repository `central`, thư mục nguồn/đích, tài nguyên và nơi xuất báo cáo.
- **Phân biệt nguồn của mặc định**: Super POM, model Maven, parent POM, profile, packaging/lifecycle binding, plugin, `settings.xml` và lệnh chạy.
- Dùng `mvn help:effective-pom`, `help:effective-settings` và log Maven để tìm giá trị cuối cùng thay vì đoán.
- Thực hành Java 17 với POM tối thiểu rồi thêm cấu hình build có chủ đích.

**Phạm vi:** chủ yếu minh họa Maven 3.x và mô hình POM 4.0.0 quen thuộc. Chi tiết chính xác của Super POM, phiên bản plugin mặc định và cơ chế phân giải có thể thay đổi giữa các bản Maven; khi phân tích dự án thực tế, phải quan sát **chính phiên bản Maven đang chạy**.

## 2. Super POM là gì?

**Super POM** là POM nền tảng do Maven cung cấp. Trong Maven 3, mọi dự án POM đều kế thừa các giá trị từ Super POM theo cơ chế dựng model, kể cả khi tệp `pom.xml` của dự án **không khai báo `<parent>`**. Bạn không cần và cũng không nên thêm một thẻ `<parent>` trỏ đến Super POM.

Có thể hình dung quan hệ:

~~~text
Super POM (được Maven cung cấp)
         │
         ▼
Parent POM của công ty/framework (nếu dự án khai báo)
         │
         ▼
pom.xml hiện tại
         │
         ├── các profile đang hoạt động / giá trị được nội suy
         ▼
Effective POM: mô hình POM đã hợp nhất dùng cho build
         │
         ├── packaging + lifecycle bindings
         ├── plugin goals và tham số plugin
         └── settings / repositories / môi trường thực thi
                    ↓
              Hành vi build thực tế
~~~

Sơ đồ là **mô hình tư duy**, không phải thuật toán ưu tiên tuyến tính cho mọi trường. `settings.xml` chẳng hạn không phải một parent POM được trộn nguyên văn vào POM; nó tác động đến các khía cạnh như mirror, proxy, server và profile cấu hình. Tương tự, các goal được kích hoạt bởi loại packaging không đơn thuần là một chuỗi XML được sao chép từ Super POM.

Với POM có parent do bạn khai báo, chuỗi kế thừa thường đi từ Super POM lên các parent tới POM hiện tại. Những trường có thể kế thừa hoặc hợp nhất bao gồm `properties`, `dependencies`, `dependencyManagement`, `build`, cấu hình plugin và `repositories`. Quy tắc ghép danh sách, plugin và các thuộc tính đặc biệt phức tạp hơn quy tắc “con luôn ghi đè cha” đơn giản.

**Không được nhầm:**

- `<modelVersion>4.0.0</modelVersion>` là phiên bản **mô hình POM**, không phải Maven CLI 4.0.
- “Super POM của Maven 3.x” không phải một artifact parent do bạn thêm vào `<dependencies>`.
- Super POM khác “parent POM của Spring Boot/công ty” và khác POM của một dự án đa module.

## 3. Các giá trị thường được Super POM cung cấp

Maven 3.x Super POM có các thiết lập nền thường gặp. Bảng dưới mô tả **giá trị điển hình trong Maven 3**, không cam kết mọi phiên bản Maven đều có XML y hệt.

| Nhóm | Giá trị thường gặp | Ý nghĩa |
| --- | --- | --- |
| `repositories` | Repository tên `central`, URL `https://repo.maven.apache.org/maven2` | Nguồn tải dependency mặc định. |
| `pluginRepositories` | Repository plugin tên `central` | Nguồn tải Maven plugin mặc định. |
| `build.directory` | `${project.basedir}/target` | Thư mục sản phẩm build. |
| `build.outputDirectory` | `${project.build.directory}/classes` | Nơi đặt lớp Java đã biên dịch và resource chính. |
| `build.testOutputDirectory` | `${project.build.directory}/test-classes` | Nơi đặt lớp/tài nguyên test. |
| `build.sourceDirectory` | `${project.basedir}/src/main/java` | Nguồn Java chính. |
| `build.testSourceDirectory` | `${project.basedir}/src/test/java` | Nguồn Java test. |
| `build.resources` | `${project.basedir}/src/main/resources` | Tài nguyên của ứng dụng. |
| `build.testResources` | `${project.basedir}/src/test/resources` | Tài nguyên cho test. |
| `build.finalName` | `${project.artifactId}-${project.version}` | Phần tên cơ sở của sản phẩm build. |
| `reporting.outputDirectory` | `${project.build.directory}/site` | Thư mục kết quả site/báo cáo. |

Ví dụ, với tọa độ:

~~~xml
<groupId>org.example.learning</groupId>
<artifactId>super-pom-demo</artifactId>
<version>1.0-SNAPSHOT</version>
~~~

kết hợp cấu hình build mặc định, bạn thường thấy:

~~~text
super-pom-demo/
├── pom.xml
├── src/main/java/...
├── src/main/resources/...
└── target/
    ├── classes/
    ├── test-classes/
    └── super-pom-demo-1.0-SNAPSHOT.jar
~~~

Cây `target/` trên **chỉ là minh họa khi các bước build tương ứng đã chạy**. Super POM không tự tạo các tệp/thư mục này ngay lúc mở POM. Plugin trong những phase liên quan mới thực hiện biên dịch, copy tài nguyên và đóng gói.

### Repository `central` có ý nghĩa gì?

Super POM của Maven 3 khai báo repository tải dependency và plugin mặc định. Đó là lý do POM chỉ có GAV vẫn có thể sử dụng plugin hoặc dependency công khai sau khi Maven phân giải chúng.

Nhưng:

- `central` không phải `~/.m2/repository`. `central` là **repository từ xa**; `~/.m2/repository` là **repository cục bộ/cache** theo cấu hình Maven.
- `settings.xml` có thể chứa `<mirrors>` chuyển yêu cầu tới repository proxy của tổ chức, dù effective POM còn hiển thị `central`.
- Snapshot có thể bị vô hiệu trên cấu hình Central mặc định; muốn dùng snapshot phải có repository phù hợp và chính sách cho phép.
- `<repositories>` phục vụ **dependency**, còn `<pluginRepositories>` phục vụ **plugin**. Repository upload sản phẩm dự án thuộc cấu hình phân phối khác, không phải tự động upload lên Central.

Không suy luận URL Maven vừa kết nối thực tế chỉ từ `repositories` trên effective POM; cần xem `settings.xml` hiệu lực và log phân giải artifact.

### Những gì *có thể* khác theo bản Maven

Các phiên bản Maven Core có thể điều chỉnh Super POM, bao gồm một số mục `pluginManagement`, profile lịch sử cho release hoặc property mặc định. Ví dụ các bản Maven 3 có thể quản lý một số phiên bản plugin trong Super POM; **không nên ghi nhớ cứng plugin version trong một bài học nền tảng**. Dùng `mvn --version` và tài liệu của phiên bản Maven được sử dụng để đối chiếu.

Một số giá trị nhìn như “mặc định Maven” lại được cung cấp bởi **model builder, lifecycle mapping hoặc plugin**, không nhất thiết là XML xuất hiện trong Super POM. Đó là điểm mấu chốt của phần tiếp theo.

## 4. Nguồn của các giá trị mặc định: đừng quy hết về Super POM

Để tìm đúng nguyên nhân của một hành vi, hãy xác định nó thuộc lớp nào.

| Nguồn | Ví dụ | Cách nhận diện |
| --- | --- | --- |
| **Super POM** | `repositories`/`pluginRepositories` mặc định, thư mục build, resources | Xem Super POM tương ứng và `help:effective-pom`. |
| **Model Maven / POM descriptor** | `packaging` mặc định là `jar` nếu không khai báo | Xem POM reference và giá trị `project.packaging`. |
| **Parent POM người dùng khai báo** | `maven.compiler.release`, `pluginManagement`, dependency versions | Xem `<parent>`, POM parent và effective POM. |
| **POM hiện tại** | `<build><directory>build-output</directory>` | Tìm khai báo trực tiếp trong `pom.xml`. |
| **Profile đang hoạt động** | Property, repository hoặc plugin tùy môi trường | Xem `help:active-profiles` và effective POM theo đúng lệnh chạy. |
| **Packaging/lifecycle binding** | `jar:jar` gắn vào phase `package` đối với packaging `jar` | Kiểm tra packaging, tài liệu lifecycle binding và log plugin thực thi. |
| **Plugin descriptor / plugin configuration** | Encoding, timeout, includes, tham số của compiler plugin | Xem tài liệu/`help:describe` cho đúng goal và phiên bản plugin. |
| **`settings.xml`** | Mirror, proxy, repository credentials, profile bên ngoài | Xem `help:effective-settings`; xử lý bí mật cẩn thận. |
| **Dòng lệnh và môi trường** | `-D...`, `-P...`, `-s ...`, `JAVA_HOME`, `mvnw` | Ghi lại invocation, active profiles, phiên bản Maven và Java. |

### 4.1. `packaging=jar` không phải bằng chứng của một thẻ Super POM

Với Maven POM 4.0.0, nếu không khai báo `<packaging>`, giá trị mặc định là **`jar`**. Điều này được quy định bởi mô hình Maven. Không cần tự tìm cho bằng được một dòng `<packaging>jar</packaging>` trong Super POM.

Tương tự, một số thông số mặc định của plugin không nhất thiết được lưu trong Super POM. Thí dụ `maven-compiler-plugin` có cấu hình `release`/`source`/`target` và phiên bản plugin cụ thể; nếu dự án không chốt phiên bản và mục tiêu Java, **đừng mặc định compiler sẽ nhắm Java 17** chỉ vì bạn đang chạy Maven bằng JDK 17.

### 4.2. Packaging quyết định goal được gắn vào phase

Với dự án có `<packaging>jar</packaging>`, các binding mặc định thường bao gồm:

| Phase default lifecycle | Goal điển hình |
| --- | --- |
| `process-resources` | `maven-resources-plugin:resources` |
| `compile` | `maven-compiler-plugin:compile` |
| `process-test-resources` | `maven-resources-plugin:testResources` |
| `test-compile` | `maven-compiler-plugin:testCompile` |
| `test` | `maven-surefire-plugin:test` |
| `package` | `maven-jar-plugin:jar` |

Các binding này gắn với **loại packaging/lifecycle mapping**, không phải suy ra chỉ từ `<build><plugins>` trong POM. Dự án `war` có goal đóng gói khác; dự án `pom` không đương nhiên tạo JAR ứng dụng. Plugin cấu hình thêm có thể làm thay đổi tập goal được chạy.

**Phase và goal là hai khái niệm khác nhau:** `mvn package` đi qua các phase trước đó trong default lifecycle, còn `mvn jar:jar` là gọi trực tiếp goal đóng gói và không bảo đảm các bước biên dịch trước đó đã được chạy.

### 4.3. Parent POM không giống Super POM

Một dự án có thể thêm:

~~~xml
<parent>
    <groupId>org.example.learning</groupId>
    <artifactId>learning-parent</artifactId>
    <version>1.0</version>
</parent>
~~~

Đây là **parent POM do dự án chọn**. Maven cần resolve artifact parent này từ đường dẫn tương đối/repository theo quy tắc thích hợp. Nó có thể khai báo `properties`, `dependencyManagement` và `pluginManagement` mà POM con thừa kế.

Super POM thì do Maven cung cấp **ngầm định**, không cần resolve bằng tọa độ trên. Hai cơ chế có liên quan trong cây kế thừa nhưng không đồng nhất. Không phải dự án nào cũng có parent tự khai báo; **mọi dự án Maven 3 vẫn dựa trên Super POM**.

## 5. Thực hành A — POM tối thiểu để quan sát giá trị được thừa hưởng

Tạo thư mục `super-pom-demo` và chỉ một tệp `pom.xml`:

~~~text
super-pom-demo/
└── pom.xml
~~~

Nội dung `pom.xml` tối thiểu:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.learning</groupId>
    <artifactId>super-pom-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
</project>
~~~

Đây là POM hợp lệ để **quan sát model**. Nó không có lớp Java nên không dùng để minh họa một chương trình thực thi; đồng thời vì **chưa chỉ rõ cấu hình Java compiler**, không nên lấy `mvn package` trên POM tối thiểu này làm chuẩn bảo đảm build mã Java 17.

Kiểm tra Maven/JDK đang được dùng tại terminal:

~~~bash
mvn --version
java -version
javac -version
~~~

Chạy trong thư mục có `pom.xml`:

~~~bash
mvn validate
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

`validate` kiểm tra tính cơ bản của project model; `help:effective-pom` ghi mô hình POM hiệu lực ra tệp `effective-pom.xml`. File này được yêu cầu tạo ở **thư mục hiện tại** nhờ `-Doutput=effective-pom.xml`; không cần giả định thư mục `target/` đã tồn tại.

Mở file đã sinh, tìm những nhóm sau:

~~~text
<packaging>jar</packaging>
<repositories>
<pluginRepositories>
<build>
<directory>...
<outputDirectory>...
<sourceDirectory>...
<testSourceDirectory>...
<resources>
<testResources>
<reporting>
~~~

Các thẻ/đường dẫn được hiển thị có thể đã **được nội suy thành đường dẫn tuyệt đối** và không giống cú pháp biến `${project.basedir}` trong tài liệu Super POM. Không suy luận khác nhau về string hiển thị đồng nghĩa khác nhau về vị trí vật lý.

Những câu hỏi cần trả lời sau khi xem:

1. Tại sao `packaging` có giá trị `jar` dù POM nguồn không viết thẻ này?
2. Vì sao `build.directory` và `sourceDirectory` xuất hiện?
3. Maven lấy URL `central` từ đâu?
4. POM có parent do bạn khai báo không? Nếu không, vì sao effective POM vẫn có rất nhiều trường?

**Không chỉnh sửa `effective-pom.xml` để thay cấu hình dự án.** Đây là báo cáo kết quả model, sẽ được tạo lại; nơi chỉnh là POM/parent/profile/settings thích hợp.

## 6. Truy vết nguồn bằng verbose effective POM

Maven Help Plugin hỗ trợ in nhận xét về vị trí nguồn của các phần tử:

~~~bash
mvn help:effective-pom -Dverbose=true -Doutput=effective-pom-verbose.xml
~~~

Trong file xuất ra, plugin có thể đưa comment XML mô tả **nguồn gốc khai báo** của từng phần tử (POM hiện tại, parent hoặc nguồn model) theo khả năng của phiên bản plugin. Điều này đặc biệt có ích khi một giá trị như `<directory>` hoặc phiên bản plugin đã được định nghĩa trong parent mà người đọc không nhìn thấy.

Để có kết quả dễ tái hiện hơn trong CI, có thể **chốt phiên bản Maven Help Plugin** được chọn thay vì phụ thuộc việc phân giải prefix `help`. Ví dụ lệnh dạng đầy đủ:

~~~bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom-verbose.xml
~~~

Bản plugin `3.5.2` được dùng như ví dụ phiên bản cụ thể; việc tải plugin có thể cần mạng nếu cache chưa có. Khi cần kiểm tra một dự án sử dụng Maven 3 cũ, hãy xác minh phiên bản plugin Help tương thích.

**Giới hạn:** Không phải mọi hành vi build đều hiện thành trường có comment chỉ rõ nguồn. Packaging lifecycle binding, plugin parameters, user properties và ảnh hưởng từ Maven settings có thể phải điều tra qua kênh khác. `help:effective-pom` là **mô hình cấu hình hiệu lực**, không phải transcript toàn bộ hoạt động Maven đã thực thi.

## 7. Thực hành B — từ mặc định sang cấu hình Java 17 rõ ràng

Bây giờ bổ sung lớp Java chạy được và cấu hình compiler vào cùng dự án. Cây thư mục:

~~~text
super-pom-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    └── learning/
                        └── App.java
~~~

**Thay toàn bộ `pom.xml` tối thiểu ở bước A** bằng phiên bản đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.learning</groupId>
    <artifactId>super-pom-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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

**Vì sao POM này vẫn không liệt kê thư mục nguồn, `jar`, repositories, mọi plugin?** Những mặc định còn phù hợp tiếp tục được Maven xử lý qua Super POM, model và binding. Người dùng chỉ khai báo **điều cần cố định**: release 17, UTF-8 và phiên bản compiler plugin.

Tạo `src/main/java/org/example/learning/App.java`:

~~~java
package org.example.learning;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Super POM demo: " + (2 + 4));
    }
}
~~~

Đây là chương trình Java 17 độc lập. Tên file, package và tên class đều khớp nhau. Chạy:

~~~bash
mvn clean package
java -cp target/super-pom-demo-1.0-SNAPSHOT.jar org.example.learning.App
~~~

**Stdout chính xác của lệnh Java thứ hai:**

~~~text
Super POM demo: 6
~~~

Lệnh Maven thường in `BUILD SUCCESS` khi build thành công; log chi tiết có thể khác theo plugin và môi trường. JAR ở `target/super-pom-demo-1.0-SNAPSHOT.jar` là hệ quả của `packaging=jar` và `finalName` mặc định, còn nội dung bytecode được sinh nhờ compiler goal chạy qua lifecycle binding.

Không sử dụng `java -jar` với ví dụ này: POM chưa cấu hình thuộc tính `Main-Class` trong manifest JAR. `java -cp ... org.example.learning.App` là cách chạy phù hợp.

Muốn đối chiếu trực tiếp compiler Java với JDK, có thể thử riêng ở thư mục dự án (không dùng Maven):

~~~bash
javac --release 17 -d manual-classes src/main/java/org/example/learning/App.java
java -cp manual-classes org.example.learning.App
~~~

Stdout lệnh Java vẫn là:

~~~text
Super POM demo: 6
~~~

Lệnh `javac` là **cách biên dịch thủ công**, không chứng minh rằng Maven đã gọi cùng đúng tham số; để xem Maven thực sự gọi compiler plugin ra sao, kiểm tra POM, phiên bản plugin và log `mvn -X compile`. Thư mục `manual-classes` không phải `target/classes` mặc định của Maven.

## 8. Thực hành C — ghi đè một mặc định có chủ đích

Giả sử bạn muốn output Maven trong `build-output` thay vì `target`. Trong `pom.xml` của bước B, **thay phần `<build>` cũ** bằng:

~~~xml
<build>
    <directory>build-output</directory>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </plugin>
    </plugins>
</build>
~~~

Đây là **mảnh XML thay thế cho thẻ `<build>`**, không phải một POM XML độc lập. Đừng tạo hai thẻ `<build>` cấp dự án.

Sau đó:

~~~bash
mvn clean package
mvn help:evaluate -Dexpression=project.build.directory -q -DforceStdout
~~~

Giá trị của `project.build.directory` sẽ trỏ tới `build-output` trong thư mục dự án (có thể hiển thị dạng đường dẫn tuyệt đối). Các đầu ra khác, khi còn dùng biến `${project.build.directory}`, cũng thay đổi theo, ví dụ:

~~~text
build-output/
├── classes/org/example/learning/App.class
└── super-pom-demo-1.0-SNAPSHOT.jar
~~~

Cây trên tiếp tục là minh họa giản lược. Chạy ứng dụng theo đường dẫn **mới**:

~~~bash
java -cp build-output/super-pom-demo-1.0-SNAPSHOT.jar org.example.learning.App
~~~

**Stdout:**

~~~text
Super POM demo: 6
~~~

`target` cũ từ bước trước có thể vẫn nằm trên đĩa vì bạn đã đổi `build.directory`. `mvn clean` trong cấu hình mới dọn output được cấu hình **hiện tại**, không có trách nhiệm rà quét tự động mọi thư mục build lịch sử. Nếu cần dọn `target` cũ, xác nhận đó là thư mục chỉ chứa output của dự án trước khi thao tác thủ công; không xóa mù.

Từ thí nghiệm này, hãy phân biệt: Super POM đặt mặc định, còn POM hiện tại có thể thay đổi nó; các giá trị phụ thuộc `project.build.directory` sẽ đi theo cấu hình hiệu lực.

## 9. Parent POM và thứ tự cấu hình: ví dụ dễ kiểm chứng

Trong dự án thật, parent POM thường quản lý phiên bản plugin và thuộc tính Java dùng chung. Ví dụ **tệp parent** ở `parent-demo/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.learning</groupId>
    <artifactId>learning-parent</artifactId>
    <version>1.0</version>
    <packaging>pom</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

**Tệp con** ở `parent-demo/child/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.example.learning</groupId>
        <artifactId>learning-parent</artifactId>
        <version>1.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>child</artifactId>
    <packaging>jar</packaging>
</project>
~~~

Parent phải có `packaging=pom`. Child không khai báo `groupId`, `version` và thuộc tính compiler riêng nhưng có thể **kế thừa** chúng từ parent. Vì child đóng gói `jar`, compiler goal được lifecycle binding gọi, và phiên bản compiler plugin có thể được lấy từ `pluginManagement` kế thừa ở parent. `pluginManagement` **quản lý cấu hình/phiên bản**, không tự khiến mọi plugin trong danh sách chạy nếu không có binding/khai báo sử dụng tương ứng.

Từ thư mục `parent-demo/child`, thử:

~~~bash
mvn help:evaluate -Dexpression=project.groupId -q -DforceStdout
mvn help:evaluate -Dexpression=project.version -q -DforceStdout
mvn help:evaluate -Dexpression=maven.compiler.release -q -DforceStdout
mvn help:effective-pom -Dverbose=true -Doutput=child-effective-pom.xml
~~~

Kết quả các giá trị chính kỳ vọng lần lượt là:

~~~text
org.example.learning
1.0
17
~~~

Đây là **ba giá trị từ ba invocation riêng**, không phải toàn bộ stdout gộp trong một lệnh. Mỗi dòng có thể có log khác nếu môi trường/plugin không dùng chế độ quiet như ví dụ.

Nếu thêm trong POM con:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

thì property Java release do child khai báo thường thay property `17` của parent đối với model hiệu lực, **nhưng cần JDK hỗ trợ release 21 để build**. Đây chỉ là **mảnh XML minh họa** thêm vào cấp `project` của child; đừng áp dụng thay đổi đó trong ví dụ Java 17 nếu JDK máy bạn chưa đáp ứng.

Đối với một dự án thật, các thành phần dependency management, plugin executions, resources và một số cấu trúc XML được **merge** theo khóa/cơ chế riêng; không phải chỉ “ghi đè cả thẻ”. Khi có bất ngờ, dùng `effective-pom` của đúng module để kiểm tra.

## 10. Profiles, properties và dòng lệnh tác động thế nào?

POM hiệu lực phụ thuộc **bối cảnh chạy Maven**, không chỉ nội dung file. Ví dụ một profile trong `pom.xml`:

~~~xml
<profiles>
    <profile>
        <id>ci</id>
        <properties>
            <build.label>ci-run</build.label>
        </properties>
    </profile>
</profiles>
~~~

Đây là mảnh cấu hình đặt trực tiếp trong `<project>`, tách khỏi `<build>`. Khi kích hoạt:

~~~bash
mvn -Pci help:evaluate -Dexpression=build.label -q -DforceStdout
~~~

Giá trị `build.label` được profile `ci` cung cấp là:

~~~text
ci-run
~~~

Nếu không kích hoạt profile và không có nguồn nào khác khai báo property đó, giá trị không được định nghĩa trong model. Nói “mặc định project luôn có `build.label`” là sai.

### Property interpolation

Maven hỗ trợ một số nhóm biểu thức như:

- `${project.version}`: lấy version của model dự án.
- `${project.basedir}`: đường dẫn gốc dự án.
- `${env.JAVA_HOME}`: giá trị biến môi trường khi được truy cập qua nhóm `env`.
- `${java.home}`: Java system property của JVM chạy Maven.
- `${my.property}`: property được khai báo ở `<properties>`/profile hoặc được cung cấp theo cách thích hợp.

Không nhầm **tên property** với một **trường model**. Ví dụ `-Dproject.build.directory=xyz` không phải cách có tính tổng quát được bảo đảm để ghi đè mọi trường `<build><directory>`; Maven xử lý biểu thức, user properties và cấu hình plugin theo cơ chế tương ứng. Muốn thay thư mục build một cách rõ ràng, nên cấu hình `<build><directory>...</directory>` hoặc một property tự định nghĩa được tham chiếu hợp lệ.

Lệnh `-Dkey=value` có thể cung cấp user property; `-Pprofile-id` kích hoạt profile; `-s path/to/settings.xml` chọn user settings thay vì mặc định; Maven Wrapper `./mvnw` có thể chọn bản Maven khác với lệnh `mvn` toàn cục. **Lệnh thực tế** là một phần của việc giải thích nguồn mặc định.

### `settings.xml` không phải POM parent

Hai vị trí settings thường gặp là:

~~~text
<MAVEN_HOME>/conf/settings.xml
~/.m2/settings.xml
~~~

Tùy cài đặt, hệ điều hành và cách gọi Maven, đường dẫn thực tế có thể khác; đây là hai vị trí điển hình cho *global settings* và *user settings*. Settings có thể cung cấp:

- `mirrors`, ví dụ repository proxy nội bộ thay vì truy cập Central trực tiếp.
- `proxies` cho kết nối mạng.
- `servers` chứa thông tin xác thực cho repository.
- `profiles`/`activeProfiles` với các property và repository theo môi trường.
- `localRepository` nếu không dùng vị trí cache mặc định.

Dùng:

~~~bash
mvn help:effective-settings
mvn help:active-profiles
~~~

**Cảnh báo bảo mật:** `settings.xml` hoặc đầu ra của `effective-settings` có thể liên quan tới thông tin môi trường và credential; tùy plugin/phiên bản, một số giá trị được che nhưng không nên mặc định mọi bí mật luôn được xử lý an toàn. Đừng tải file, log debug hay output chứa token/password lên nơi công cộng. Chỉ chia sẻ phần đã rà soát và ẩn thông tin nhạy cảm.

## 11. Khi POM hiệu lực và hành vi thực tế khác nhau

Giả sử chạy:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

và nhìn thấy `https://repo.maven.apache.org/maven2` ở `repositories`. Nhưng log Maven lại báo tải dependency từ một mirror nội bộ. Không có mâu thuẫn: **mô hình POM chứa repository logic**, còn mirror được áp dụng ở lớp repository resolution từ settings.

Tương tự, bạn có thể thấy cấu hình compiler plugin trong `effective-pom.xml` nhưng khi chạy `mvn package` lỗi:

~~~text
release version 17 not supported
~~~

Lỗi này thường liên quan **JDK/compiler thực thi** không hỗ trợ `--release 17` hoặc cấu hình compiler/toolchain khác với kỳ vọng, chứ không phải Super POM “đã biến Java thành phiên bản 17”. Hãy so sánh `mvn --version`, `javac -version`, POM hiệu lực và toolchains nếu có.

Hay `mvn package` tạo JAR dù POM không có `maven-jar-plugin` trong `<build><plugins>` do **packaging binding**. Ngược lại, khai báo `pluginManagement` chưa chắc khiến goal chạy nếu không có binding hoặc execution được kích hoạt.

Một cách phân tích hệ thống:

~~~text
Giá trị/hành vi bất ngờ
        ↓
Đọc POM hiện tại, <parent> và profile
        ↓
Xem effective POM + verbose origin
        ↓
Xem packaging và các goal thực sự chạy trong log
        ↓
Kiểm tra effective settings, mirror, Java/Maven version
        ↓
Xác định đúng nơi sửa, rồi chạy lại để kiểm chứng
~~~

Không sửa ngay `~/.m2/repository` hoặc xóa cache vì thấy phiên bản plugin lạ. Trước tiên phải xác định nguồn resolution và plugin version đó.

## 12. Lệnh chẩn đoán quan trọng

| Lệnh | Trả lời câu hỏi | Lưu ý |
| --- | --- | --- |
| `mvn --version` | Maven và JVM nào đang chạy lệnh? | Đặc biệt quan trọng nếu có Maven Wrapper/IDE/CI. |
| `mvn help:effective-pom` | Model POM hợp nhất hiện tại ra sao? | Kế thừa, profile đang hoạt động và interpolation. |
| `mvn help:effective-pom -Dverbose=true` | Những khai báo có nguồn từ đâu? | Comment nguồn tùy phiên bản plugin; không thay được log. |
| `mvn help:evaluate -Dexpression=project.packaging -q -DforceStdout` | Packaging hiệu lực là gì? | Với POM không khai báo packaging, thường nhận `jar`. |
| `mvn help:evaluate -Dexpression=project.build.directory -q -DforceStdout` | Output directory đã resolve là gì? | Thường `target` hoặc đường dẫn đã override. |
| `mvn help:active-profiles` | Profile nào đang active? | Profile là nguyên nhân phổ biến của khác biệt môi trường. |
| `mvn help:effective-settings` | Settings được Maven tính toán như thế nào? | Không chia sẻ công khai trước khi kiểm tra thông tin nhạy cảm. |
| `mvn -X package` | Maven thực thi những goal nào và dùng môi trường gì? | Log dài; xem cả lỗi và tránh lộ thông tin hệ thống. |
| `mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Ddetail` | Plugin cung cấp goal/parameter nào? | Có thể cần plugin Help hoặc plugin đích được tải vào cache. |

Nếu một lệnh `help` thất bại khi không có mạng, có thể do Maven Help Plugin chưa được cache, proxy/mirror thiếu cấu hình, hoặc repository không truy cập được. Đây không phải bằng chứng rằng project không kế thừa Super POM.

## 13. Những lỗi hiểu nhầm phổ biến

| Nhầm lẫn | Vì sao sai | Cách hiểu/kiểm tra đúng |
| --- | --- | --- |
| “Không có `<parent>` nên không dùng Super POM.” | Super POM được Maven 3 đưa vào model ngầm định. | Xem effective POM trên một dự án tối thiểu. |
| “Mọi mặc định đều từ Super POM.” | Model builder, packaging lifecycle và plugin cũng có mặc định riêng. | Phân nhóm nguồn trước khi suy luận. |
| “`modelVersion=4.0.0` nghĩa là tôi đang chạy Maven 4.” | Đây là phiên bản mô hình POM XML. | Dùng `mvn --version`. |
| “POM không viết `<packaging>` thì Maven không biết tạo gì.” | Mặc định của model là `jar`. | `help:evaluate` với `project.packaging`. |
| “Thấy `central` trong effective POM thì Maven phải kết nối trực tiếp Central.” | Mirror/proxy trong settings có thể chuyển endpoint thực tế. | So effective settings và log phân giải. |
| “`pluginManagement` làm mọi plugin chạy.” | Đây là nơi quản lý cấu hình/phiên bản; cần binding hoặc invocation phù hợp. | Xem packaging, execution và log. |
| “Dùng JDK 17 thì compiler mặc định luôn build bytecode Java 17.” | Target Java do compiler plugin/configuration/toolchain quyết định. | Khai báo `maven.compiler.release=17` và plugin tương thích. |
| “`mvn clean` dọn toàn bộ file sinh ra bởi mọi cấu hình cũ.” | Clean gắn với output directory hiện tại và plugin config. | Kiểm tra đường dẫn hiệu lực trước khi xóa file. |
| “Có `src/main/resources` nên luôn copy resource vào mọi artifact.” | Plugin/resources phase và packaging mới quyết định sản phẩm. | Xem `target/classes` và nội dung JAR. |
| “Sửa `effective-pom.xml` sẽ thay build.” | Đây chỉ là đầu ra để xem model. | Sửa đúng POM/parent/profile/settings. |
| “POM trong IDE giống terminal nên kết quả chắc chắn giống.” | IDE, CLI hoặc CI có thể dùng JDK/Maven/settings/profile khác. | Ghi nhận chính xác môi trường và invocation. |
| “Cùng một project mà plugin version phải giống mọi máy.” | Super POM, Maven Core, parent, profile và version resolution có thể khác. | Chốt plugin version quan trọng và kiểm tra effective POM/log. |

## 14. Bài thực hành tự kiểm tra

Thực hiện đúng thứ tự, không cần repository ngoài dự án demo:

1. Tạo POM tối thiểu `super-pom-demo` ở mục 5; chạy `mvn validate` và `mvn help:effective-pom`. Ghi lại `packaging`, `repositories`, `build.directory`, `sourceDirectory`.
2. Bật `-Dverbose=true` khi chạy Help Plugin; so sánh những giá trị do file POM nguồn khai báo và những giá trị nhận từ model/kế thừa.
3. Thay POM như mục 7, tạo `App.java` và chạy `mvn clean package` cùng `java -cp ... org.example.learning.App`. Đối chiếu chính xác chuỗi `Super POM demo: 6`.
4. Đổi `build.directory` thành `build-output`, chạy build, kiểm tra JAR mới ở thư mục mới. Giải thích tại sao file trong `target` cũ không nhất thiết tự mất.
5. Dùng `help:evaluate` để tìm `project.packaging` và `project.build.directory`. Nêu một giá trị đến từ model default và một giá trị đến từ override POM.
6. Đọc ví dụ parent/child ở mục 9 và giải thích vì sao `maven.compiler.release` được kế thừa dù POM con không khai báo trực tiếp.
7. Nếu môi trường có mirror, kiểm tra sự khác nhau giữa repository trong effective POM và địa chỉ thực tế trong log (không đăng nội dung settings nhạy cảm).
8. Trả lời: tại sao Java 17 cần được chốt chủ đích? Vì sao `mvn package` có thể tạo JAR mà bạn không viết `jar:jar` trong POM? Và vì sao Super POM không thay thế được thông tin từ `settings.xml`?

### Ghi nhớ cuối bài

**Super POM cung cấp cấu hình nền** để nhiều dự án Maven có thể bắt đầu bằng POM rất ngắn. Nhưng “mặc định Maven” là kết quả của **nhiều lớp có vai trò khác nhau**: model POM, chuỗi kế thừa, profile, plugin/lifecycle binding, settings, lệnh gọi và môi trường.

Khi có hành vi không như mong đợi, hãy dùng nguyên tắc: **tìm giá trị hiệu lực → xác định nguồn cung cấp → đối chiếu goal và môi trường thực thi → sửa đúng lớp cấu hình**. `mvn help:effective-pom` là công cụ trọng tâm để bắt đầu, không phải lời giải duy nhất cho mọi khác biệt.

## Tài liệu chính thức

- Apache Maven — Introduction to the POM: https://maven.apache.org/guides/introduction/introduction-to-the-pom.html
- Apache Maven — POM Reference (Super POM, inheritance, packaging): https://maven.apache.org/pom.html
- Maven Help Plugin — `help:effective-pom`: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Maven Help Plugin — Usage: https://maven.apache.org/plugins/maven-help-plugin/usage.html
