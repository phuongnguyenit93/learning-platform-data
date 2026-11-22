# Parent POM và những thành phần dự án con có thể kế thừa trong Maven

## 1. Parent POM là gì và giải quyết vấn đề nào?

Trong Maven, `pom.xml` mô tả một dự án: tọa độ artifact, dependency, plugin, thuộc tính, repository và các bước build. Khi nhiều dự án con dùng chung quy ước, sao chép cùng cấu hình vào từng `pom.xml` làm tăng nguy cơ lệch phiên bản và khó nâng cấp. **POM inheritance (kế thừa POM)** cho phép một dự án con khai báo `<parent>` và nhận các cấu hình Maven được phép kế thừa từ POM cha.

Parent POM thường có `<packaging>pom</packaging>`. Nó là một artifact POM có tọa độ riêng (groupId, artifactId, version); có thể phát hành lên repository để các dự án khác kế thừa. Parent POM có thể nằm ngay trong repository hiện tại hoặc là parent dùng chung của một tổ chức.

Một cây quan hệ thường gặp:

~~~text
Maven Super POM (mặc định do Maven cung cấp)
          |
          v
org.example:company-parent:1.0.0  (packaging=pom)
          |
          +-- org.example:service-core:1.0.0 (packaging=jar)
          |
          +-- org.example:service-api:1.0.0  (packaging=jar)
~~~

Các dự án con có thể dùng chung phiên bản plugin, quy tắc compiler, mã hóa ký tự, repository và thông tin tổ chức, đồng thời mỗi dự án vẫn có `artifactId`, mã nguồn, dependency và mục đích đóng gói riêng.

**Không đồng nhất parent POM với một module chứa Java class.** Parent quản lý **mô hình cấu hình build**; việc mã nguồn Java của dự án con dùng được class từ dự án khác vẫn phải được biểu diễn qua dependency phù hợp.

## 2. Cách dự án con chỉ định parent POM

Ví dụ parent `org.example:company-parent:1.0.0` ở `../pom.xml`, dự án con có cấu hình tối thiểu:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example</groupId>
        <artifactId>company-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>service-core</artifactId>
</project>
~~~

Đoạn này là một POM con hợp lệ nếu parent đúng tọa độ và có thể được Maven tìm thấy. Giải thích:

- `<parent>` chứa **tọa độ của POM cha**; nó không chỉ là tên thư mục.
- `<artifactId>service-core</artifactId>` là artifactId **riêng của con**, bắt buộc khai báo cho dự án con.
- Con có thể **không khai báo `groupId` và `version`**, vì chúng được kế thừa từ parent nếu không bị con ghi đè; con có tọa độ hiệu lực `org.example:service-core:1.0.0`.
- `<relativePath>../pom.xml</relativePath>` là đường dẫn tới POM cha tính tương đối từ thư mục chứa `pom.xml` của dự án con. Maven kiểm tra tọa độ POM ở vị trí này trước khi dùng cơ chế tra repository tương ứng.
- Không ghi `<packaging>` ở con nghĩa là con dùng **giá trị mặc định `jar`**, chứ không kế thừa `pom` từ parent.

Nếu cấu trúc thư mục chuẩn có parent ở ngay bên trên, `<relativePath>` có mặc định là `../pom.xml` và có thể bỏ qua. Nếu parent nằm ở `../build-parent/pom.xml` thì đặt đúng đường dẫn đó. Với parent chỉ được giải quyết từ repository, `<relativePath/>` rỗng giúp Maven 3 bỏ qua kiểm tra đường dẫn filesystem; Maven 4 có thêm khả năng tìm parent giữa các project của build. Đừng chỉnh `relativePath` chỉ để che lỗi tọa độ `groupId/artifactId/version` không khớp.

Kế thừa có thể nhiều tầng: POM con kế thừa cha; cha kế thừa ông hoặc một parent khác; cuối cùng các POM dùng mặc định từ **Super POM** của Maven. Đó không phải kế thừa class Java.

## 3. Những thành phần thường được kế thừa

Theo cơ chế Maven POM inheritance, con nhận phần lớn các thành phần cấu hình từ parent, sau đó có thể bổ sung hoặc ghi đè theo quy tắc từng trường.

| Nhóm trong POM cha | Dự án con nhận được gì? | Điều cần nhớ |
| --- | --- | --- |
| `groupId`, `version` | Tọa độ mặc định nếu con không khai báo riêng. | Con vẫn có `artifactId` riêng. |
| `description`, `url`, `inceptionYear` | Thông tin mô tả dự án theo quy tắc kế thừa. | URL có thể được Maven điều chỉnh khi kế thừa; kiểm tra effective POM. |
| `organization`, `licenses`, `developers`, `contributors`, `mailingLists` | Metadata tổ chức/người đóng góp. | Con có thể bổ sung hoặc thay dữ liệu theo quy tắc merge. |
| `scm`, `issueManagement`, `ciManagement` | Thông tin repository, issue tracker và CI. | URL SCM/website của module có thể cần xác minh riêng. |
| `properties` | Các giá trị chung như `maven.compiler.release`, `project.build.sourceEncoding`. | Con có thể định nghĩa lại property cùng tên. |
| `dependencyManagement` | Quy tắc version, scope và thuộc tính dependency được quản lý. | **Không tự thêm dependency** vào classpath. |
| `dependencies` | Các dependency thực sự khai báo trên parent, được hợp nhất vào danh sách dependency con. | Dùng thận trọng để tránh mọi con phải nhận dependency không cần thiết. |
| `repositories` và `pluginRepositories` | Cấu hình nguồn tải dependency/plugin. | Quyền truy cập cần cấu hình ngoài POM, ví dụ `settings.xml`. |
| `build` | Nhiều cài đặt build, plugins, pluginManagement, resources, cấu hình và executions. | Có quy tắc merge; plugin/execution có thể `<inherited>false</inherited>`. |
| `reporting` | Cấu hình các báo cáo và report plugin áp dụng cho con. | Phải chạy goal/lifecycle phù hợp mới tạo report. |
| Một số cấu hình phân phối và site | Ví dụ `distributionManagement` theo quy tắc model. | Kiểm tra URL/repository/đường dẫn site hiệu lực trước khi deploy. |

Cấu hình Maven còn chịu ảnh hưởng của `settings.xml`, profile được kích hoạt, Super POM và giá trị dòng lệnh. Vì vậy bảng này mô tả **khả năng kế thừa**, không khẳng định hai project luôn có effective POM giống nhau.

Đặc biệt, metadata `developers` hoặc `scm` được kế thừa là **dữ liệu cấu hình**, không bảo đảm các thông tin đó chính xác cho mọi dự án con sau khi chuyển repository hoặc tách dự án.

## 4. Những thành phần không được kế thừa nguyên dạng

Một số phần thường phải xác định tại mỗi module hoặc thuộc trách nhiệm của reactor/aggregation:

| Thành phần | Có kế thừa từ parent theo cách thông thường không? | Giải thích |
| --- | --- | --- |
| `artifactId` | **Không**. | Mỗi dự án phải có artifactId riêng. |
| `name` | **Không**. | Tên hiển thị của dự án con do con khai báo hoặc để mặc định. |
| `prerequisites` | **Không**. | Không xem việc đặt cấu hình này ở parent là ràng buộc tương đương cho con. |
| `profiles` | **Không kế thừa nguyên khối profile**. | **Tác động của profile đang active ở parent** có thể đi vào mô hình con. |
| `packaging` | **Không dùng packaging của parent làm mặc định cho con**. | Parent là `pom`; con không khai báo packaging thường là `jar`. |
| `modules` | Không phải danh sách module tự phát sinh ở con. | `modules` mô tả aggregation/reactor ở POM khai báo, không phải danh sách dependency hoặc quan hệ kế thừa class. |
| Mã nguồn Java, resource và file sinh trong `target/` | **Không**. | Maven kế thừa **mô hình build**, không sao chép mã nguồn hay artifact của parent. |
| Thông tin xác thực trong `settings.xml` | Không phải mục cấu hình POM được kế thừa. | Mỗi máy/CI cung cấp credentials bằng cơ chế bảo mật phù hợp. |

**Ví dụ dễ nhầm:** Vì parent có `<packaging>pom</packaging>`, dự án con **không bị buộc là POM-only project**. Nó vẫn có thể đóng gói JAR hoặc WAR theo cấu hình của chính mình.

**Profile nuance:** POM con không nhận bản sao mục `<profiles>` của parent để tự kích hoạt như profile riêng của con. Maven đánh giá profile của mô hình parent; nếu profile ở parent được kích hoạt, **những hiệu ứng của nó** (như property, dependency, plugin) có thể được kế thừa. Vì vậy cần xem effective POM trong đúng môi trường/kích hoạt thay vì chỉ đọc tên profile.

## 5. dependencyManagement khác dependencies thế nào?

Đây là khác biệt quan trọng nhất trong các dự án dùng parent.

**`<dependencyManagement>` quản lý các thông số khi dependency được yêu cầu; `<dependencies>` thực sự đưa dependency vào model của dự án.**

Parent khai báo version tập trung:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **mảnh cấu hình nằm trong `<project>` của parent**, không phải POM độc lập. Dự án con chỉ cần chọn dependency muốn dùng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
    </dependency>
</dependencies>
~~~

Maven sử dụng quy tắc management để xác định version `5.11.4` và scope `test`. Nếu con **không hề khai báo** dependency JUnit, chỉ có mục `dependencyManagement` ở parent sẽ **không** làm JUnit tự xuất hiện trên test classpath.

Ngược lại, nếu parent đặt JUnit trực tiếp trong `<dependencies>`, các con kế thừa dependency thực sự đó dù bản thân không khai báo. Đây có thể là chủ ý cho những dependency chung, nhưng cũng có thể làm mọi module phụ thuộc dư thừa.

Ví dụ parent:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
        <version>2.0.16</version>
    </dependency>
</dependencies>
~~~

Khi kế thừa, child sẽ có dependency `slf4j-api` trong model hiệu lực. Nếu chỉ muốn thống nhất version mà cho từng child chọn có dùng hay không, dùng `dependencyManagement` thay cho cách đưa tất cả vào `dependencies`.

**Các lưu ý nâng cao:**

- Khi con khai báo version/scope riêng, những giá trị cụ thể của con có thể ghi đè quy tắc quản lý tương ứng. Kiểm tra effective POM và dependency tree để biết version thực sự.
- `dependencyManagement` có thể ảnh hưởng cả lựa chọn version của **transitive dependencies** trong một dependency graph; dùng version cũ ở parent có thể làm thư viện phụ thuộc không tương thích.
- **BOM import** là cơ chế khác với parent inheritance: dependency có `type=pom`, `scope=import` trong `dependencyManagement` nhập các mục dependency management của BOM. Nó **không** kéo theo `build/plugins`, `properties` hay metadata của BOM như một parent POM.
- Maven có thể dùng cả parent và BOM: parent quy định plugin/build policies, BOM quy định bảng version dependency.

Khi tìm nguyên nhân lệch version, dùng:

~~~bash
mvn -pl :service-core dependency:tree
mvn -pl :service-core help:effective-pom
~~~

Các lệnh cần project và plugin tương ứng; Maven có thể tải plugin/dependency nếu cache chưa có.

## 6. pluginManagement khác build/plugins thế nào?

Maven plugin là công cụ đảm nhiệm compile, test, package, report... **Cấu hình plugin** cũng có hai mức:

1. `<build><pluginManagement><plugins>...`: cung cấp **version/cấu hình mặc định** cho plugin khi plugin được dùng trong dự án con, hoặc khi lifecycle mặc định gắn goal tương ứng. Nó **không tự chạy một plugin bất kỳ** chỉ vì plugin được liệt kê trong pluginManagement.
2. `<build><plugins>...`: khai báo plugin tham gia cấu hình build. Plugin và execution của parent thường được kế thừa, trừ khi dùng cấu hình chặn kế thừa. Việc goal thực sự chạy phụ thuộc lifecycle binding, `<executions>`, hoặc việc gọi plugin goal trực tiếp.

Ví dụ parent quản lý plugin compiler và Surefire:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Khi con đóng gói kiểu `jar`, lifecycle mặc định gọi compiler và Surefire ở các phase phù hợp, nên phiên bản được quản lý sẽ có tác dụng. Nếu parent chỉ quản lý một plugin **không nằm trong lifecycle mặc định và không được khai báo/chạy nơi khác**, Maven sẽ không tự thực thi plugin đó.

Còn cấu hình parent trực tiếp trong `build/plugins`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <systemPropertyVariables>
                    <demo.mode>parent</demo.mode>
                </systemPropertyVariables>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Dự án con kế thừa cấu hình plugin (và có thể override). Vì cấu hình này đặt ở parent, **nhiều dự án con sẽ cùng được áp dụng**, nhưng chỉ khi chúng thực sự chạy goal phù hợp.

**Tránh đặt plugin có side effect trong parent `build/plugins` một cách vô tình**. Nếu một goal làm publish, generate hoặc sửa file, execution được kế thừa có thể chạy ở mọi module. Dùng pluginManagement để quản lý nhưng chỉ bật plugin ở module thực sự cần, hoặc đặt `<inherited>false</inherited>` khi phù hợp.

## 7. Cách Maven hợp nhất cấu hình cha và con

Maven thường tạo **effective model** từ parent, Super POM, profile được kích hoạt và khai báo ở POM con. Cách merge phụ thuộc kiểu phần tử:

- Property cùng tên: cấu hình cụ thể của con có thể override giá trị kế thừa của parent.
- Danh sách dependencies/plugins: Maven hợp nhất theo định danh phù hợp; các khai báo tương ứng có thể được kết hợp thay vì sao chép trùng đơn giản.
- Plugin execution có `id` trùng nhau giữa cha và con sẽ được merge theo quy tắc model; cần kiểm tra những goal/configuration cuối cùng thực sự tồn tại.
- Với `<configuration>` của plugin, con thường ghi đè giá trị trùng khóa, nhưng các phần tử con, thuộc tính và danh sách XML có quy tắc merge riêng.
- Tài liệu Maven hỗ trợ các marker như `combine.self="override"` và `combine.children="append"` để điều chỉnh cách ghép **một phần cấu hình plugin**. Chúng không phải cơ chế ghi đè chung cho mọi XML trong POM.

Ví dụ con muốn thay toàn bộ phần `configuration` được kế thừa ở một plugin cụ thể:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration combine.self="override">
        <failIfNoTests>true</failIfNoTests>
    </configuration>
</plugin>
~~~

Đây là đoạn XML cần đặt trong `<build><plugins>` của POM con, không phải POM hoàn chỉnh. `combine.self="override"` làm phần configuration này thay cấu hình tương ứng của cha; có thể **mất các tùy chọn khác** như `systemPropertyVariables` đã cấu hình ở parent. Chỉ dùng khi thực sự muốn thay toàn bộ phần tử đó.

Nếu **không** muốn một plugin parent đi xuống child, có thể đặt:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <inherited>false</inherited>
    <executions>
        <execution>
            <id>parent-only-action</id>
            <phase>validate</phase>
            <goals><goal>run</goal></goals>
            <configuration>
                <target><echo message="Only in parent"/></target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **mảnh plugin** trong parent, minh họa thuộc tính `inherited=false`; không nên thêm nó vào dự án chỉ để thử vì nó tạo thêm hành vi ở phase validate. Một plugin thực thi trong parent và không được kế thừa chỉ có nghĩa con không nhận khai báo này từ parent; con vẫn có thể tự khai báo và chạy plugin đó.

Ở cấp `<execution>` cũng có thể quy định `<inherited>false</inherited>` để chỉ chặn một execution cụ thể. Điều này hữu ích khi parent vừa muốn chia sẻ một số execution vừa muốn giữ tác vụ khác riêng tại parent.

## 8. Ví dụ hoàn chỉnh: parent POM + một dự án Java 17 kế thừa

Ví dụ này có thể tạo trên máy và chạy với JDK 17+, Maven 3.9.x tương thích và kết nối repository khi cần tải plugin/dependency.

Mục tiêu: parent quản lý **groupId/version**, Java release, phiên bản JUnit và phiên bản plugin; con chọn dependency JUnit, có artifactId riêng, **ghi đè property** và kế thừa cấu hình Surefire.

Cấu trúc:

~~~text
inheritance-demo/
├── pom.xml                           # Parent đồng thời là aggregator
└── service-core/
    ├── pom.xml                       # Child
    └── src/
        ├── main/java/org/example/Greeting.java
        └── test/java/org/example/GreetingTest.java
~~~

### 8.1. Parent: inheritance-demo/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <name>Company Parent</name>

    <modules>
        <module>service-core</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <demo.mode>parent</demo.mode>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.4</version>
                <scope>test</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <configuration>
                    <systemPropertyVariables>
                        <demo.mode>${demo.mode}</demo.mode>
                    </systemPropertyVariables>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chú ý: `<modules>` làm cho POM gốc **aggregate** module `service-core` khi chạy reactor ở root. Trong khi đó, POM con ở mục 8.2 có `<parent>` để **kế thừa**. Hai quan hệ này độc lập về khái niệm nhưng được dùng cùng lúc trong ví dụ.

### 8.2. Child: service-core/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example</groupId>
        <artifactId>company-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>service-core</artifactId>
    <name>Service Core</name>

    <properties>
        <demo.mode>service</demo.mode>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Đọc hai POM cùng nhau:

- Child có `artifactId=service-core`, `name=Service Core` do nó tự khai báo.
- Child **không có `groupId`/`version`** nhưng nhận `org.example` và `1.0.0` từ parent.
- Child **không khai báo `packaging`** nên dùng mặc định `jar`, không dùng `pom` của parent.
- Child chỉ khai báo JUnit bằng groupId/artifactId; version `5.11.4` và scope `test` đến từ parent `dependencyManagement`.
- Property `demo.mode=service` **ghi đè** `demo.mode=parent` được kế thừa.
- Build của child nhận cấu hình Surefire trong parent `build/plugins`; `<demo.mode>${demo.mode}</demo.mode>` được đánh giá theo property hiệu lực của child, vì vậy test JVM nhận `demo.mode=service`.
- Compiler Plugin và Surefire Plugin nhận phiên bản được quản lý từ parent `pluginManagement`; các goal mặc định của lifecycle `jar` sẽ dùng chúng.

### 8.3. Java source: service-core/src/main/java/org/example/Greeting.java

~~~java
package org.example;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello from child";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Đây là chương trình Java độc lập không dùng thư viện bên ngoài, hợp lệ với Java 17.

### 8.4. Unit test: service-core/src/test/java/org/example/GreetingTest.java

~~~java
package org.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void verifiesInheritedBuildConfiguration() {
        assertEquals("Hello from child", Greeting.message());
        assertEquals("service", System.getProperty("demo.mode"));
    }
}
~~~

Test xác nhận hai điều: mã chính hoạt động, và cấu hình Maven Surefire được kế thừa đã đưa property `demo.mode` của **child** vào test JVM. `junit-jupiter` đến từ dependency trong child với version/scope được quản lý ở parent.

### 8.5. Build, chạy và kiểm tra đầu ra

Từ thư mục root `inheritance-demo/`:

~~~bash
mvn -B -ntp clean verify
java -cp service-core/target/classes org.example.Greeting
~~~

Nếu build/test hoàn tất thành công, **stdout chính xác của riêng lệnh `java`** là:

~~~text
Hello from child
~~~

Lệnh Maven có log riêng; không cần khớp từng dòng log. Những tệp đầu ra trọng tâm:

~~~text
service-core/target/
├── classes/org/example/Greeting.class
├── test-classes/org/example/GreetingTest.class
├── surefire-reports/
│   ├── TEST-org.example.GreetingTest.xml
│   └── org.example.GreetingTest.txt
└── service-core-1.0.0.jar
~~~

Thư mục `target/` có thể chứa thêm metadata từ compiler, resource và plugin. Parent với `packaging=pom` không tạo JAR chính giống child.

Cách kiểm tra model hiệu lực:

~~~bash
mvn -pl :service-core help:effective-pom
mvn -pl :service-core dependency:tree
mvn -pl :service-core help:evaluate -Dexpression=project.groupId -q -DforceStdout
mvn -pl :service-core help:evaluate -Dexpression=project.version -q -DforceStdout
~~~

Ở hai lệnh `help:evaluate` cuối, giá trị kỳ vọng lần lượt là `org.example` và `1.0.0` (Help Plugin có thể in thêm cảnh báo trong một số môi trường). Trong effective POM, tìm `maven.compiler.release=17`, `demo.mode=service`, cấu hình Surefire, dependency JUnit và version plugin. Lệnh `dependency:tree` cho thấy dependency thực sự của child, không chỉ những dependency nằm trong dependencyManagement.

Nếu bạn dùng Maven Wrapper, thay `mvn` bằng `./mvnw` trên Unix/macOS, hoặc `.\mvnw.cmd` trong Windows. Ví dụ không tự tạo Wrapper.

## 9. Parent POM và aggregator POM: hai quan hệ riêng

Dự án đa module thường có cấu trúc parent vừa chứa `<modules>`, vừa là `<parent>` của các module. Tuy nhiên cần phân biệt:

**Inheritance** được khai báo tại **child**:

~~~xml
<parent>
    <groupId>org.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
</parent>
~~~

**Aggregation** được khai báo tại **aggregator**:

~~~xml
<modules>
    <module>service-core</module>
    <module>service-api</module>
</modules>
~~~

Các đoạn trên là **mảnh POM**, không phải dự án XML hoàn chỉnh. Quan hệ này có thể tồn tại độc lập:

- Một project kế thừa parent **được phát hành từ nơi khác** nhưng không nằm trong danh sách modules của parent đó.
- Một aggregator có thể gom một project **không hề khai báo aggregator làm parent**.
- Parent/aggregator có thể là cùng một POM nếu nhóm chủ động thiết kế như vậy.
- `<modules>` dùng cho Maven **reactor** tìm và sắp xếp project khi build nhiều module, không tự thêm module vào dependency classpath của module khác.
- Nếu `service-api` cần class của `service-core`, nó phải khai báo dependency `org.example:service-core` với version phù hợp; chỉ có cùng parent/aggregator là chưa đủ.

Khi chạy từ root:

~~~bash
mvn clean verify
mvn -pl :service-core test
mvn -pl :service-api -am verify
~~~

Lệnh cuối chỉ áp dụng nếu đã tạo `service-api` và thêm nó vào reactor; nó là ví dụ về `-pl` chọn module và `-am` xây thêm dependency module cần thiết. Trong **dự án mẫu mục 8 chỉ có `service-core`**, hãy sử dụng hai lệnh đầu. Không sao chép lệnh của module chưa tồn tại.

## 10. Profiles của parent và những gì được kế thừa

Một hiểu lầm phổ biến là: “Parent có profile id `ci` thì con chắc chắn có cùng profile đó.” **Sai về mặt cấu trúc:** profile definition không được copy nguyên trạng vào `<profiles>` của child. Maven đánh giá profile trong ngữ cảnh model tương ứng; **tác động của profile đang active** ở parent có thể được kế thừa.

Ví dụ parent có:

~~~xml
<profiles>
    <profile>
        <id>ci</id>
        <activation>
            <property>
                <name>env.CI</name>
            </property>
        </activation>
        <properties>
            <demo.mode>ci</demo.mode>
        </properties>
    </profile>
</profiles>
~~~

Đây là một đoạn bổ sung trong `<project>` của parent. Khi biến môi trường `CI` được Maven nhìn thấy dưới dạng property `env.CI` và profile được kích hoạt, model parent có thể nhận các hiệu ứng cấu hình của profile. Child tiếp tục áp dụng quy tắc override riêng, nên trong ví dụ mục 8, nếu child cố định `<demo.mode>service</demo.mode>`, cần xem effective POM để biết giá trị cuối sau khi Maven hợp nhất.

Không dựa vào trùng id profile giữa hai POM như thể đó là cùng một profile kế thừa. Để xem trạng thái thực tế:

~~~bash
mvn -pl :service-core help:active-profiles
mvn -pl :service-core help:effective-pom
~~~

Lưu ý: một profile định nghĩa trong `settings.xml` và một profile trong POM có quy tắc nguồn cấu hình riêng. Khi áp dụng profile cho đa module, cần kiểm thử ở chính runner CI và phiên bản Maven được dự án dùng.

## 11. Super POM và thứ tự xác định cấu hình

Maven có **Super POM** cung cấp các giá trị mặc định như repositories và một số cấu hình build/lifecycle. Khi child kế thừa parent, Maven xây dựng mô hình cuối từ nhiều lớp:

~~~text
Super POM + mặc định của Maven
             |
             v
Parent POM của tổ chức
             |
             v
Child POM (khai báo riêng và override)
             |
             v
Profile được kích hoạt + cài đặt môi trường
             |
             v
Effective model dùng để thực thi plugin/lifecycle
~~~

Đây là **sơ đồ khái niệm**, không biểu diễn chính xác thứ tự mọi bước của Maven Model Builder; profile có thể được kích hoạt và đưa vào model sớm trước khi ghép kế thừa.

Không nên suy luận mọi giá trị đều theo một phép “child luôn thắng” đơn giản: plugin configuration, dependency management, profile, repositories và thông tin URL có quy tắc merge riêng. Để giải quyết khác biệt thực tế, dùng **effective POM**, kết hợp tài liệu plugin và log build.

**Ví dụ:** Một child định nghĩa `<maven.compiler.release>21</maven.compiler.release>` sẽ có thể thay giá trị `17` của parent, nhưng JDK đang chạy Maven vẫn phải hỗ trợ Java release 21; việc override property không tự cài JDK.

## 12. Lỗi thường gặp khi cấu hình kế thừa POM

| Triệu chứng | Nguyên nhân phổ biến | Cách kiểm tra |
| --- | --- | --- |
| `Non-resolvable parent POM` | Parent chưa có trong repository, path sai, không truy cập được repo hoặc version sai. | So `groupId/artifactId/version` và `relativePath`; kiểm tra kết nối repository. |
| Parent có `<packaging>pom</packaging>`, child không tạo JAR | Child không đúng lifecycle, thiếu source, build fail hoặc loại packaging bị cấu hình sai. | Kiểm tra child effective POM và `mvn -pl :child package`. |
| Child không dùng version dependency ở parent | Parent đặt sai mục, version child khác hoặc BOM/management khác tác động. | So `dependencyManagement` với `dependencies` và chạy `dependency:tree`. |
| Đặt plugin trong `pluginManagement` mà goal không chạy | Plugin mới được quản lý version/config, chưa được khai báo hoặc bind execution. | Xem `build/plugins`, lifecycle binding và effective POM. |
| Plugin đột nhiên chạy trên mọi child | Parent đặt execution ở `build/plugins` và cho phép kế thừa. | Tìm execution, `inherited` và phase trong effective POM. |
| Child dùng property khác kỳ vọng | Property bị override ở con, profile active, CLI `-D` hoặc settings. | Chạy `help:effective-pom`/`help:evaluate` với đúng profile. |
| Child không nhận profile parent theo tên | Definition của profile không được kế thừa. | Kiểm tra tác động profile active và model hiệu lực. |
| Module có cùng parent nhưng không gọi được class của nhau | Kế thừa POM không tạo dependency Java. | Thêm dependency giữa các module và kiểm tra reactor. |
| Build từ root thành công, build riêng child thất bại | Parent/sibling artifact chưa được giải quyết từ filesystem/repository. | Kiểm tra `relativePath`, local repo, dependency module và cơ chế reactor. |
| Báo trùng plugin hoặc execution | Plugin/configuration của parent và child bị khai báo/merge sai. | Kiểm tra `id` của executions, một plugin khai báo một lần trong cùng danh sách build. |

Với dự án đa module, đừng chỉnh sửa ngẫu nhiên đường dẫn parent để tránh lỗi. Một parent được Maven resolve phải có **tọa độ khớp** với `<parent>` của child; đường dẫn `relativePath` chỉ hỗ trợ Maven tìm đúng artifact POM.

## 13. Thực hành thiết kế parent POM tốt

1. **Đặt phần thật sự dùng chung ở parent.** Các property như Java release/encoding, version plugin cốt lõi, repository và metadata tổ chức là ứng viên tốt.
2. **Dùng `dependencyManagement` để quản lý version**, cho từng child khai báo dependency cần thiết. Chỉ đặt dependency trong `dependencies` của parent khi thật sự muốn tất cả child nhận nó.
3. **Dùng `pluginManagement` cho version/default**, và `build/plugins` cho plugin mà các child cần kích hoạt hoặc kế thừa execution. Cân nhắc `<inherited>false</inherited>` với bước chỉ nên chạy ở parent.
4. **Để artifactId, name và packaging đặc thù ở child.** Parent có `packaging=pom` nhưng không áp đặt loại artifact của các child.
5. **Phân biệt parent và aggregator.** Nếu muốn build cùng reactor, thêm `<modules>` ở aggregator; nếu muốn dùng chung cấu hình, thêm `<parent>` ở từng child.
6. **Đặt version parent rõ ràng và có kế hoạch nâng cấp.** Child cần trỏ đúng version parent đã được phát hành hoặc đúng source parent trong repository; thay parent có thể làm toàn bộ effective model đổi.
7. **Không đặt credentials trong parent POM.** Dùng `settings.xml`/secret manager cho thông tin truy cập repository.
8. **Xem effective POM của một child đại diện** trước khi áp dụng thay đổi toàn bộ dự án. Chạy test và kiểm tra tác động của plugin/plugin executions ở các module có packaging khác nhau.

Khi review pull request thay parent, tập trung vào thay đổi có thể tác động nhiều module: phiên bản dependency quản lý, plugin executions kế thừa, Java release, profiles và repository. Một dòng đổi trong parent có thể khiến toàn bộ child build khác trước.

## 14. Câu hỏi tự kiểm tra

1. **Child có cần khai báo lại `groupId` và `version` không?** Không, nếu muốn nhận đúng hai giá trị của parent; nhưng child vẫn cần `artifactId` riêng.
2. **Parent dùng packaging `pom` thì child mặc định dùng `pom`?** Không. Packaging mặc định của child thường là `jar` nếu không khai báo riêng.
3. **Parent đặt JUnit trong `dependencyManagement`, child không có `dependencies`: JUnit có tự lên classpath?** Không. Parent chỉ quản lý tọa độ/version; child phải chọn dependency.
4. **Parent đặt plugin trong `pluginManagement` thì Maven tự chạy plugin đó?** Không phải plugin bất kỳ. Nó được dùng khi plugin được khai báo/chạy hoặc xuất hiện trong lifecycle binding phù hợp.
5. **Nếu child cần class từ sibling, cùng parent có đủ không?** Không. Cần dependency giữa hai Maven artifacts, không phải quan hệ parent.
6. **Profile `ci` định nghĩa ở parent có xuất hiện nguyên vẹn trong danh sách profiles của child?** Không. Chỉ các tác động được kích hoạt của profile trong parent có thể đi vào effective model của child.
7. **Cách biết child thực sự kế thừa phiên bản plugin và dependency nào?** Xem `help:effective-pom`, `dependency:tree` và log plugin trong đúng build/profile.
8. **Vì sao cần hạn chế plugin execution trực tiếp ở parent?** Vì chúng có thể được kế thừa và chạy trên nhiều child, gây tác động ngoài dự kiến nếu không kiểm soát `inherited`/phase.

## 15. Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the POM: Project Inheritance, Aggregation và Super POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html).
- [Apache Maven — POM Reference: Inheritance, Dependency Management, Plugins](https://maven.apache.org/pom.html).
- [Apache Maven — Introduction to Build Profiles: Profile Inheritance](https://maven.apache.org/guides/introduction/introduction-to-profiles.html).
- [Apache Maven — Guide to Working with Multiple Modules (Maven 3)](https://maven.apache.org/guides/mini/guide-multiple-modules.html).
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html).

**Ghi nhớ:** Parent POM giúp các child chia sẻ **cấu hình Maven**: tọa độ mặc định, properties, dependency management, dependency khai báo chung, plugin/build/report và metadata. Child giữ nhận dạng `artifactId`, tên, packaging và mã nguồn của mình. Muốn biết thực sự kế thừa gì, đọc **effective POM** của đúng child; muốn build nhiều module cùng nhau, dùng **reactor/aggregation**, còn muốn dùng class của module khác, khai báo **dependency**.
