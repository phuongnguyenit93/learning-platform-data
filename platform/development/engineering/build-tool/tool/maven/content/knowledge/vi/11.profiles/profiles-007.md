# Ảnh hưởng của profile khi kế thừa mô hình dự án trong Maven

Một dự án Maven có thể kế thừa cấu hình từ **parent POM** và đồng thời dùng **build profiles** để thay đổi cách build theo môi trường, lệnh chạy hoặc điều kiện kích hoạt. Khi kết hợp hai cơ chế, câu hỏi quan trọng là: **profile được định nghĩa trong parent có truyền xuống dự án con hay không, và nếu có thì truyền cái gì?**

**Quy tắc trọng tâm của Maven:** *Bản thân các khai báo `<profile>` không được kế thừa như những profile của child. Maven kích hoạt và áp dụng (inject) profile vào model nơi profile được định nghĩa từ sớm; sau đó **những hiệu ứng cấu hình của profile đang active** có thể được kế thừa qua parent–child theo quy tắc inheritance thông thường.*

Điều này có nghĩa:

- Parent có profile `strict-quality` nhưng **không active**: phần cấu hình chỉ nằm bên trong profile đó không tự trở thành cấu hình build của child.
- Parent có profile `strict-quality` **active**: các property, plugin execution, dependency management hoặc dependency mà profile thêm vào mô hình parent có thể xuất hiện trong **effective POM** của child.
- Child **không nhận bản sao profile** để có thể xử lý như một khai báo profile cục bộ của riêng nó. Không được nhầm “kế thừa hiệu ứng đã áp dụng” với “kế thừa định nghĩa profile”.
- Profile cùng `id` ở parent, child hoặc settings không mặc nhiên là một profile duy nhất. Đặc biệt, **điều kiện kích hoạt ngầm (implicit activation)** chỉ áp dụng trong ngữ cảnh chứa khai báo profile ấy.

## 1. Phân biệt inheritance, profile activation và effective POM

Maven dùng **POM model** để mô tả build. Parent POM có thể quản lý các giá trị dùng chung: version thư viện, version/configuration plugin, properties, repositories và một số metadata. Child chỉ định parent qua `<parent>`.

Build profile là một **cấu hình có điều kiện** bên trong `<profiles>`. Khi điều kiện profile được thỏa mãn hoặc người dùng kích hoạt trực tiếp, Maven đưa những phần được khai báo trong profile vào model của POM tương ứng.

**Effective POM** là cấu hình kết quả Maven dùng sau các bước quan trọng như đọc Super POM, parent inheritance, profile injection, merge và interpolation. Khi đánh giá một build, effective POM thường hữu ích hơn việc chỉ đọc từng `pom.xml` bằng mắt.

Diễn giải rút gọn:

```text
Parent pom.xml
  ├── phần cấu hình chung (properties, build, ...)
  └── <profiles>
       └── strict-quality
            ├── activation
            ├── properties
            └── build/plugins/executions
                  |
             Maven xét kích hoạt profile ở parent
                  |
       +----------+-----------+
       |                      |
     Không active            Active
       |                      |
   model parent có          model parent được
   cấu hình chung           thêm hiệu ứng profile
       |                      |
       +----------+-----------+
                  |
          Maven áp dụng inheritance
                  |
             Child effective POM
             (child có thể override/merge)
```

Sơ đồ nhấn mạnh **thứ tự khái niệm**, không mô tả toàn bộ các pha nội bộ của Maven Model Builder. Điều kiện profile và cơ chế merge được đánh giá theo ngữ cảnh model, phiên bản Maven và cấu hình thực tế.

### Bảng đối chiếu

| Câu hỏi | Kết luận |
| --- | --- |
| Parent có `<profile id="ci">`, child có thấy nguyên thẻ profile này như khai báo cục bộ không? | **Không.** Profile definition không tự được inherited |
| Parent profile đã active và đặt một property | Property sau injection thường được inherited, trừ khi child override hoặc có cấu hình ưu tiên khác |
| Parent profile active và thêm plugin execution ở `<build><plugins>` | Plugin/execution có thể được inherited; vẫn xét `inherited` và quy tắc merge |
| Parent profile không active nhưng khai báo dependency | Dependency trong profile không được đưa vào model parent cho lượt build đó |
| Child tự định nghĩa profile trùng ID | Đó là profile được khai báo trong child; implicit activation của profile này không tự kích hoạt profile parent |
| Parent đồng thời là aggregator chứa `<modules>` | Aggregation là cơ chế riêng; không thay thế inheritance |
| Settings kích hoạt profile | Settings có thể góp properties/repositories; không cung cấp toàn bộ cấu trúc POM profile |

## 2. Những gì từ profile đang active có thể ảnh hưởng đến child?

### 2.1. Properties

Một profile ở parent có thể đặt property dùng bởi plugin hoặc resource filtering:

```xml
<profiles>
    <profile>
        <id>strict-quality</id>
        <activation>
            <property>
                <name>org.quality</name>
                <value>strict</value>
            </property>
        </activation>
        <properties>
            <training.quality.mode>strict</training.quality.mode>
        </properties>
    </profile>
</profiles>
```

Đây là **đoạn XML đặt trong parent POM**, chưa phải một POM độc lập. Khi Maven được gọi với property CLI:

```bash
mvn -Dorg.quality=strict verify
```

điều kiện kích hoạt của profile trong parent được thỏa mãn. Property `training.quality.mode=strict` được đưa vào model trước khi child kế thừa. Nếu child không ghi đè property cùng tên, child có thể dùng giá trị này trong cấu hình build.

Không đồng nhất hai property:

- `org.quality=strict`: **cờ đầu vào** được truyền qua CLI để kích hoạt profile.
- `training.quality.mode=strict`: **giá trị đầu ra của profile** được inject vào model; plugin hoặc resource có thể đọc nó.

Không nên dựa vào nội suy property vừa được định nghĩa trong POM để làm điều kiện profile cùng cấp một cách tùy tiện, vì Maven xét profile activation rất sớm. Dùng system/user property, JDK/OS hoặc điều kiện được tài liệu Maven cho phép.

### 2.2. dependencyManagement khác dependencies

Giả sử parent profile có:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Nếu profile active, child có thể nhận cấu hình quản lý version JUnit. Nhưng **dependencyManagement không tự đưa JUnit vào dependency graph**. Child chỉ thực sự dùng JUnit khi có `<dependency>` trong `<dependencies>` (hoặc nhận dependency trực tiếp qua inheritance từ nơi khác). Nếu profile không active và child không khai báo version ở chỗ khác, Maven có thể báo thiếu version cho dependency đó.

Nếu parent profile khai báo **`<dependencies>`** thay vì management, dependency có thể được inherited và làm thay đổi classpath của các child. Đây là ảnh hưởng lớn hơn nhiều: có thể kéo theo thư viện bắc cầu, xung đột version, rủi ro bảo mật hoặc licensing.

### 2.3. pluginManagement khác plugins

Một profile có thể thêm:

- `<build><pluginManagement>`: quản lý version/cấu hình plugin khi plugin được sử dụng; không phải mọi goal tự chạy chỉ vì được quản lý.
- `<build><plugins>` và `<executions>`: có thể gắn goal vào lifecycle. Khi hiệu ứng đó được inherited, child có thể phải chạy thêm kiểm tra mới ở `validate`, `verify` hoặc phase khác.

Ví dụ parent có profile thêm Maven Enforcer Plugin vào phase `validate`. Khi profile active, child chạy `mvn verify` sẽ đi qua `validate` và thực thi Enforcer goal. Khi không active, execution này không đến từ profile đó.

Một execution có thể khai báo `<inherited>false</inherited>` hoặc chịu ảnh hưởng cơ chế merge plugin, nên không khẳng định mọi cấu hình plugin trong profile luôn truyền nguyên xi đến mọi child. **Hãy kiểm tra effective POM và log execution.**

### 2.4. Repositories, profiles và ảnh hưởng môi trường

Profile đang active cũng có thể bổ sung repositories hoặc pluginRepositories. Child sau đó có thể resolve dependency/plugin từ nguồn khác với môi trường bình thường. Tuy nhiên, việc có một repository không làm xuất hiện dependency mới nếu không có khai báo hoặc cơ chế resolve liên quan.

Nên hạn chế đặt repository nội bộ đặc thù trong parent profile nếu khiến builds phụ thuộc mạng công ty và khó tái lập bên ngoài. Ở tổ chức có Maven repository manager, có thể cấu hình mirror/credentials qua `settings.xml` được quản lý an toàn.

**Điểm quan trọng:** inheritance áp dụng cho **phần cấu hình parent sau khi profile đã được xử lý**; Maven không copy nguyên danh sách profile parent sang child.

## 3. Profile được kích hoạt ở parent bằng cách nào?

### 3.1. Kích hoạt tường minh với -P

`-P` chọn profile theo ID:

```bash
mvn -Pstrict-quality verify
```

Lệnh này kích hoạt những profile có ID phù hợp trong những ngữ cảnh Maven xét đến, bao gồm parent khi model được xây dựng. Tuy nhiên, không nên suy luận từ việc cùng ID rằng parent và child đã hợp nhất profile: chúng vẫn là các khai báo riêng biệt.

Từ Maven 4 trở đi, các profile ID không resolve được có thể bị coi là lỗi thay vì âm thầm bỏ qua; nếu cố ý dùng một profile không tồn tại ở mọi module, tài liệu Maven 4 cho phép cú pháp optional như `-P?optional-profile`. Với tài liệu/lệnh CI muốn chạy cả Maven 3 và 4, nên giữ danh sách profile được định nghĩa nhất quán và tránh các ID nhập nhằng.

### 3.2. Kích hoạt theo property: dễ kiểm soát trong CI

Ví dụ:

```xml
<activation>
    <property>
        <name>org.quality</name>
        <value>strict</value>
    </property>
</activation>
```

Chạy:

```bash
mvn -Dorg.quality=strict clean verify
```

Property từ CLI hiện diện khi Maven xét profile activation, nên một parent profile dùng điều kiện này có thể active dù child không có thẻ `<profile>` tương ứng. Cách này hữu ích khi nhiều service kế thừa chung parent.

**Không nên đặt mật khẩu hoặc dữ liệu bí mật vào `-D...`** nếu lệnh được ghi lại ở CI log hoặc lịch sử shell. Chỉ dùng property cho tín hiệu cấu hình không nhạy cảm.

### 3.3. Kích hoạt ngầm theo JDK, OS, file

Maven còn hỗ trợ profile activation theo JDK đang chạy Maven, hệ điều hành, file tồn tại/không tồn tại và các property được cho phép. Ví dụ:

```xml
<activation>
    <jdk>[17,)</jdk>
</activation>
```

Một profile như vậy active dựa trên **phiên bản JDK được Maven sử dụng**, không phải chỉ dựa trên giá trị `maven.compiler.release` trong POM. Nếu CI dùng JDK khác máy dev, parent có thể đưa những hiệu ứng khác xuống child.

Kích hoạt theo file dễ gây khác biệt giữa checkout parent và child: đường dẫn/giá trị khả dụng khi profile được xét phụ thuộc model và ngữ cảnh. Theo tài liệu Maven, nội suy cho file activation bị giới hạn; không mặc định rằng mọi property của POM đã được nội suy sẵn. Với các dự án độc lập tham chiếu parent đã publish, cần đặc biệt kiểm tra điều kiện file ở đúng môi trường child.

### 3.4. activeByDefault có điều kiện, không có nghĩa luôn active

```xml
<activation>
    <activeByDefault>true</activeByDefault>
</activation>
```

Profile có `activeByDefault` sẽ tự active trong **ngữ cảnh khai báo** khi không có profile khác ở cùng POM được kích hoạt bằng những cơ chế tương ứng. Một profile khác được active trong **chính POM đó** có thể làm các profile `activeByDefault` ở đó bị tắt.

**Tránh bẫy:** child tự có một profile riêng được bật không tự động chứng minh profile `activeByDefault` ở parent sẽ bị tắt, vì các điều kiện implicit activation được xét trong từng container POM. Hãy nhìn effective POM, không kết luận dựa trên tên profile giống nhau giữa module.

## 4. Ví dụ Java 17 hoàn chỉnh: profile trong parent thay đổi build của child

Mục tiêu ví dụ:

1. Parent luôn quản lý Java 17, JUnit và các Maven plugin version.
2. Parent có profile `strict-quality` **không active mặc định**.
3. Khi gọi Maven với `-Dorg.quality=strict`, parent profile đặt property `training.quality.mode=strict` và thêm **Maven Enforcer goal ở phase validate**.
4. Child **không khai báo profile** nhưng vẫn nhận hiệu ứng của parent profile active; child chạy unit test và tạo JAR.

### 4.1. Cấu trúc thư mục

```text
workspace/
├── organization-parent/
│   └── pom.xml
└── orders-app/
    ├── pom.xml
    └── src/
        ├── main/java/vn/example/orders/App.java
        └── test/java/vn/example/orders/AppTest.java
```

Hai thư mục đứng cạnh nhau để `orders-app/pom.xml` có thể dùng `relativePath` đến parent. Parent **không có `<modules>`** nên không đóng vai trò aggregator cho child.

### 4.2. Parent POM đầy đủ: organization-parent/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.build</groupId>
    <artifactId>organization-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <training.quality.mode>standard</training.quality.mode>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.0</version>
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
                    <artifactId>maven-resources-plugin</artifactId>
                    <version>3.3.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-clean-plugin</artifactId>
                    <version>3.3.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>

    <profiles>
        <profile>
            <id>strict-quality</id>
            <activation>
                <property>
                    <name>org.quality</name>
                    <value>strict</value>
                </property>
            </activation>

            <properties>
                <training.quality.mode>strict</training.quality.mode>
            </properties>

            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-enforcer-plugin</artifactId>
                        <version>3.5.0</version>
                        <executions>
                            <execution>
                                <id>require-approved-build-toolchain</id>
                                <phase>validate</phase>
                                <goals>
                                    <goal>enforce</goal>
                                </goals>
                                <configuration>
                                    <rules>
                                        <requireJavaVersion>
                                            <version>[17,)</version>
                                        </requireJavaVersion>
                                        <requireMavenVersion>
                                            <version>[3.9,)</version>
                                        </requireMavenVersion>
                                    </rules>
                                    <fail>true</fail>
                                </configuration>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        </profile>
    </profiles>
</project>
```

**Giải thích parent:**

- `packaging=pom` cho biết parent là artifact POM, không phải bản JAR ứng dụng.
- Property `training.quality.mode=standard` luôn tồn tại. Khi profile `strict-quality` active, profile override thành `strict` trong model parent.
- `dependencyManagement` quản lý JUnit version nhưng **không tự thêm dependency JUnit** cho child.
- `pluginManagement` quản lý versions của plugin được gọi trong lifecycle JAR.
- Maven Enforcer Plugin được khai báo trong **`<build><plugins>` của profile**, với execution ở `validate`. Vì không nằm trong cấu hình ngoài profile, nó chỉ xuất hiện từ chính profile này khi active.
- Enforcer kiểm tra JDK tối thiểu 17 và Maven tối thiểu 3.9 **trong ví dụ**. Dùng Maven 3.9.x và JDK 17+ để thực hành. Parent POM này có thể tải Maven Enforcer Plugin từ repository ở lần chạy strict đầu tiên.

### 4.3. Child POM đầy đủ: orders-app/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example.build</groupId>
        <artifactId>organization-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../organization-parent/pom.xml</relativePath>
    </parent>

    <groupId>vn.example.app</groupId>
    <artifactId>orders-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Child không chứa `<profiles>`, cũng không khai báo trực tiếp `training.quality.mode` hay Maven Enforcer Plugin. Nó vẫn kế thừa cấu hình bình thường từ parent: Java 17/UTF-8, managed JUnit version và managed plugin versions.

`<relativePath>../organization-parent/pom.xml</relativePath>` trỏ đến POM parent cục bộ. Nếu các dự án được lưu trong những repository khác nhau và parent đã publish vào Maven repository, child có thể dùng `<relativePath/>` để Maven resolve parent từ local/remote repository thay vì tìm `../pom.xml` theo mặc định.

Child khai báo `groupId` và `version` riêng nên version artifact ứng dụng **không bị buộc** trùng version parent về mặt cơ chế, dù chúng cùng là 1.0.0 trong ví dụ. `packaging=jar` khiến lifecycle có goal đóng JAR.

### 4.4. Java và unit test

File `orders-app/src/main/java/vn/example/orders/App.java`:

```java
package vn.example.orders;

public final class App {
    private App() {
    }

    public static String message() {
        return "Profile inheritance demo OK";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

File `orders-app/src/test/java/vn/example/orders/AppTest.java`:

```java
package vn.example.orders;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Profile inheritance demo OK", App.message());
    }
}
```

Đây là Java 17+ có thể biên dịch. Test dùng JUnit Jupiter version được quản lý bởi parent; Surefire Plugin thực thi unit test trong lifecycle JAR theo cấu hình kế thừa.

### 4.5. Build khi parent profile không active

Từ thư mục `workspace/orders-app`, với Maven 3.9.x và JDK 17+:

```bash
java -version
mvn --version
mvn -B clean verify
java -cp target/orders-app-1.0.0.jar vn.example.orders.App
```

Lệnh Java cuối cùng in **chính xác**:

```text
Profile inheritance demo OK
```

Vì `org.quality` chưa được đặt thành `strict` (và không dùng `-Pstrict-quality`), profile trong parent **không active**, nên:

- Giá trị `training.quality.mode` được inherited từ phần parent ngoài profile: `standard`.
- Execution `require-approved-build-toolchain` của Enforcer **không được thêm bởi profile đó**.
- Các plugin/compiler/JUnit version thuộc cấu hình parent ngoài profile vẫn có tác dụng.

Lưu ý: `mvn verify` thành công không chứng minh profile strict đã chạy. Cần kiểm tra log, hiệu ứng hoặc effective POM.

### 4.6. Build khi parent profile active

Vẫn tại `workspace/orders-app`:

```bash
mvn -B -Dorg.quality=strict clean verify
java -cp target/orders-app-1.0.0.jar vn.example.orders.App
```

Với Maven 3.9.x, JDK 17+ và plugins có thể resolve, build phải đi qua execution Enforcer ở phase `validate` trước khi compile/test/package. File JAR và stdout chương trình Java vẫn như trên, vì source Java không phụ thuộc property quality mode.

Nhưng **mô hình build đã khác**:

- `training.quality.mode` trở thành `strict` trong effective model của child.
- `maven-enforcer-plugin` cùng execution `require-approved-build-toolchain` được đưa vào build của child như **hiệu ứng profile parent đang active**.
- Nếu runtime Maven/JDK không đáp ứng quy tắc Enforcer, build có thể thất bại sớm ở `validate` khi plugin được giải quyết và thực thi. Đây là thay đổi hành vi build, không phải thay đổi mã Java.

Các log Maven do plugin in ra có thể khác theo phiên bản, màu terminal và flags; không giả định một chuỗi log cố định. Tập trung xác nhận plugin Enforcer được gọi và execution tương ứng xuất hiện.

### 4.7. Chứng minh bằng effective POM thay vì đoán

Sau khi `target` đã có (do `clean verify`), chạy hai lệnh và **giữ hai file khác nhau**:

```bash
mvn help:effective-pom -Doutput=target/effective-standard.xml
mvn -Dorg.quality=strict help:effective-pom -Doutput=target/effective-strict.xml
```

Lưu ý: `help:effective-pom` cần Maven Help Plugin có thể resolve; nếu mạng bị chặn và plugin chưa cache, lệnh có thể lỗi độc lập với chất lượng parent/child POM.

So sánh:

| Điều cần tìm | effective-standard.xml | effective-strict.xml |
| --- | --- | --- |
| `training.quality.mode` | `standard` | `strict` |
| Enforcer execution `require-approved-build-toolchain` đến từ parent profile | Không | Có |
| `maven.compiler.release` | `17` | `17` |
| JUnit version được quản lý bởi parent ngoài profile | `5.11.0` | `5.11.0` |
| Artifact child | `vn.example.app:orders-app:1.0.0` | Như cũ |

Có thể xem giá trị property bằng Help Plugin:

```bash
mvn -q help:evaluate -Dexpression=training.quality.mode -DforceStdout
mvn -q -Dorg.quality=strict help:evaluate -Dexpression=training.quality.mode -DforceStdout
```

Giá trị mong đợi lần lượt là `standard` và `strict`. Lệnh Help Plugin có thể thêm log/ANSI tùy runtime; hãy kiểm tra giá trị, không yêu cầu stdout trên mọi môi trường phải trùng từng byte.

**Điểm học được:** child vẫn không chứa khai báo `<profile id="strict-quality">`, nhưng effective POM và lifecycle của child thay đổi theo việc profile **ở parent** có active hay không.

## 5. Cùng ID profile ở parent và child không đồng nghĩa cùng profile

Giả sử parent có:

```xml
<profile>
    <id>ci</id>
    <activation>
        <property>
            <name>parent.ci</name>
            <value>true</value>
        </property>
    </activation>
    <properties>
        <quality.source>parent</quality.source>
    </properties>
</profile>
```

Child lại có một profile `ci`:

```xml
<profile>
    <id>ci</id>
    <activation>
        <property>
            <name>child.ci</name>
            <value>true</value>
        </property>
    </activation>
    <properties>
        <quality.child>enabled</quality.child>
    </properties>
</profile>
```

Hai đoạn này phải đặt dưới `<profiles>` trong hai POM tương ứng và chỉ để **minh họa ý nghĩa ID/activation**; không phải hai file POM hoàn chỉnh.

Nếu chỉ chạy `-Dchild.ci=true`, điều kiện profile child có thể đúng, nhưng điều kiện `parent.ci=true` ở parent vẫn không được thỏa mãn. Implicit activation của một profile không lan sang profile khác chỉ vì trùng ID. Ngược lại, `-Dparent.ci=true` có thể làm parent profile active và child nhận hiệu ứng `quality.source`, trong khi profile child vẫn inactive.

Tuy nhiên, `-Pci` là **explicit activation theo ID** và có thể kích hoạt những profile ID `ci` phù hợp trong các POM Maven xét tới, nên hai ngữ cảnh có thể cùng active. Vì vậy, khi cùng một ID xuất hiện ở nhiều POM, phải phân biệt rõ **cơ chế explicit activation** với implicit activation tại từng container.

**Khuyến nghị:** dùng profile ID đủ mô tả ý nghĩa và điều kiện kích hoạt rõ ràng. Tránh tái sử dụng cùng một ID cho những mục đích không tương thích giữa parent và child, nhất là khi pipeline sử dụng `-Pci`.

## 6. Parent inheritance khác aggregation và settings profiles

### 6.1. Parent không phải aggregator

Trong Maven:

- **Inheritance** xảy ra khi child khai báo `<parent>`, bất kể parent có quản lý modules hay không.
- **Aggregation** xảy ra khi một aggregator POM `<packaging>pom</packaging>` liệt kê `<modules>`, giúp Maven build nhiều module trong cùng reactor.

Một root aggregator có thể đồng thời là parent, nhưng không bắt buộc. **Chạy `mvn verify` ở một parent độc lập không chứa `<modules>` sẽ không tự build hàng chục child repositories**. Ngược lại, chỉ khai báo module trong aggregator cũng không làm module đó tự kế thừa POM aggregator.

Với multi-module reactor, mỗi module có POM riêng, có thể có profiles riêng và inheritance riêng. Vì vậy, việc root build `-Pci` không chứng minh mọi module có cùng cấu hình; cần kiểm tra effective POM của từng module bị ảnh hưởng.

### 6.2. Settings profile không thay thế POM profile

Profiles trong `~/.m2/settings.xml` hoặc global settings chủ yếu hỗ trợ:

- `properties` cho môi trường;
- `repositories` và `pluginRepositories`;
- điều kiện activation trong phạm vi settings.

Chúng **không được dùng để khai báo tùy ý** các `<build><plugins><executions>` hay dependencies của project như một POM profile. Một settings profile đang active có thể góp properties/repositories vào effective model hoặc thay đổi tuyến tải plugin/dependency, nhưng không phải một parent POM thực sự.

Cần xem thêm sự ưu tiên của settings khi có properties/profiles cùng tên. Tránh dựa vào “tên profile giống nhau” để kết luận source được áp dụng; dùng `help:active-profiles` và `help:effective-pom` trên môi trường thực tế.

## 7. Tương tác giữa các profile: thứ tự và override

Một dự án con có thể nhận cùng tên property hoặc plugin configuration từ:

1. Super POM và những giá trị mặc định;
2. parent POM ngoài profile;
3. **những profile parent đã active và được inject**;
4. child POM ngoài profile;
5. **những profile của child đang active**;
6. settings properties, system/user properties hoặc CLI options có ảnh hưởng.

Đây là **danh sách nguồn cấu hình**, không phải một thứ tự ưu tiên tuyến tính tuyệt đối cho mọi phần tử. Maven có những quy tắc merge riêng cho properties, dependencies, plugins, execution IDs và các cơ chế profile; kết quả cuối phải xem effective POM.

### Child có thể override hiệu ứng của parent

Ví dụ parent profile active đặt:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Child có thể khai báo:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Trong tình huống này, giá trị child có thể thắng qua inheritance/merge, khiến các module chạy Java 17 thay vì 21. Đây là lý do một parent tổ chức không tự động bảo đảm mọi child tuân thủ policy chỉ bằng property.

Nếu đây là yêu cầu bắt buộc, tổ chức cần cơ chế kiểm soát thích hợp (ví dụ Enforcer rules, CI checks và test dự án), đồng thời quy định rõ những cấu hình child được override.

### Nhiều profile active trong cùng POM

Khi nhiều profile trong **cùng POM hoặc một external settings** cùng active và thay cùng một trường, Maven có các quy tắc merge/override; tài liệu Maven mô tả profile khai báo sau có thể có ưu tiên với trường trùng (các collection có thể được mở rộng thay vì chỉ ghi đè).

Điều này làm cho “`-Pfirst,second` thì first luôn thắng” trở thành giả định sai. Nên tránh nhiều profile chồng chéo tự sửa cùng dependency/plugin execution nếu thứ tự và hành vi chưa được kiểm chứng.

### Bẫy activeByDefault

Nếu POM có profile `local` activeByDefault và profile `ci` được kích hoạt trong **chính POM đó**, `local` có thể tự bị tắt. Khi parent và child khai báo `activeByDefault` riêng, không nên coi tất cả profile mặc định như một pool toàn cục duy nhất.

## 8. Khi profile thay đổi phụ thuộc hoặc plugin: các rủi ro thực tế

| Thay đổi từ profile parent đang active | Ảnh hưởng có thể thấy ở child | Cách kiểm tra |
| --- | --- | --- |
| Đổi `maven.compiler.release` | Source/target Java khác, build fail nếu JDK không phù hợp | Effective POM, Java/Maven version, compile |
| Thêm `dependencyManagement` | Version dependency của child có thể thay đổi | `dependency:tree`, dependency convergence |
| Thêm `<dependencies>` | Child nhận classpath mới và dependency bắc cầu | Dependency tree, unit/integration tests |
| Thêm plugin Enforcer vào `validate` | Build fail sớm vì policy mới | Log `validate`, effective POM |
| Thêm plugin vào `verify` | Build chậm, thêm quality gate | Test/CI pipeline và plugin reports |
| Thêm repositories/pluginRepositories | Nguồn tải artifact và policy bảo mật thay đổi | Effective POM/settings, repository trace |
| Đặt profile theo JDK/OS | Developer và CI khác nhau dù cùng source | `mvn --version`, `help:active-profiles` |
| Kích hoạt profile bằng settings trên CI | Build CI khác local nếu settings thiếu tương đương | `help:effective-settings` và effective POM |

**Chi phí tổ chức:** một thay đổi trong profile parent có thể tạo ra hàng loạt lỗi ở child **khi chúng kích hoạt profile tương ứng**. Với parent release được pin version cụ thể, phát hành parent phiên bản mới **không tự động cập nhật toàn bộ child**; child phải nâng tọa độ parent hoặc có cơ chế giải quyết version khác. Nếu parent là SNAPSHOT hoặc đang được thay đổi cục bộ, cần thận trọng hơn về tính tái lập.

**Ví dụ rủi ro:** parent profile `ci` bổ sung `maven-surefire-plugin` execution mới. Nếu version/config không phù hợp với JUnit hoặc module không có tests, child có thể fail ngay cả khi source không đổi. Nên chạy kiểm thử đại diện cho các loại child trước khi phát hành parent mới.

## 9. Quy trình chẩn đoán khi child build khác kỳ vọng

### 9.1. Xác định POM và parent thật sự dùng

Trong child project:

```bash
mvn --version
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn help:active-profiles
```

Nếu Maven Help Plugin chưa có ở local repository hoặc mạng không truy cập được, các lệnh `help:*` có thể thất bại do plugin resolution. Điều đó không tự chứng minh POM sai.

Kiểm tra trong effective POM:

- `groupId/artifactId/version` và parent coordinates, version parent thật.
- Những properties đã được inject/override.
- `dependencyManagement`, dependencies và plugin execution.
- Plugin version/phase được dùng thực tế.
- Những profile đang active và nguồn khai báo của chúng nếu công cụ/log cung cấp.

### 9.2. So sánh tắt/bật một điều kiện

```bash
# Không đặt org.quality=strict
mvn help:effective-pom -Doutput=target/without-strict.xml

# Kích hoạt profile parent trong ví dụ
mvn -Dorg.quality=strict help:effective-pom -Doutput=target/with-strict.xml
```

Không ghi đè cùng một file output khi muốn diff. Đừng so sánh chỉ số dòng đơn thuần: hãy tìm những giá trị hoặc goal tạo khác biệt như Enforcer execution và `training.quality.mode`.

### 9.3. Phân biệt ba câu hỏi

1. **Profile được định nghĩa ở đâu?** Parent POM, child POM hay settings?
2. **Profile có active trong lượt build này không?** Do `-P`, `-D`, JDK/OS/file, `activeByDefault` hay settings?
3. **Tác dụng nào đã vào effective model và còn sau inheritance?** Property, dependency, plugin, execution hay repository?

Bỏ qua câu hỏi thứ ba rất dễ dẫn tới nhận định sai kiểu “active thì chắc chắn Enforcer chạy”: một plugin/execution có thể bị disable, override hoặc không bind vào phase chạy.

### 9.4. Đừng chẩn đoán nhầm Maven model với artifact

Một Java class in cùng thông báo ở cả hai lượt build **không chứng minh effective POM giống nhau**. Profile có thể thay test plugin, compiler flags hoặc repository nhưng ứng dụng vẫn in cùng chuỗi. Muốn xác nhận profile inheritance, phải kiểm tra model/lifecycle, không chỉ stdout Java.

Tương tự, `mvn -Pci package` có thể thành công dù một profile trong parent không active nếu ID, settings hoặc môi trường không đúng; đọc danh sách profile active, effective POM và log goal cụ thể.

## 10. Thiết kế profile trong parent cho dễ bảo trì

1. **Giữ đường build chuẩn đơn giản.** Parent ngoài profile chứa compiler release, encoding và các plugin/dependency versions ổn định. Profile chỉ chứa khác biệt thực sự cần điều kiện.
2. **Không dùng profile để giấu dependency quan trọng của ứng dụng.** Dependency thiết yếu nên rõ trong POM/parent hoặc được quản lý bằng BOM; chỉ dùng profile để thay dependency khi thực sự có nhu cầu môi trường rõ ràng.
3. **Đặt tên profile mô tả tác dụng.** Ví dụ `strict-quality`, `integration-tests`, `release-signing`, tránh `foo` hay dùng `ci` cho nhiều ý nghĩa khác nhau.
4. **Làm rõ điều kiện kích hoạt.** Ưu tiên `-P` hoặc property `-D...` minh bạch trong CI đối với chính sách quan trọng; hạn chế phụ thuộc kích hoạt ngầm theo file/JDK/OS khi mục tiêu là build tái lập.
5. **Pin plugin versions và parent version.** Phát hành parent release mới thay vì sửa release cũ; nâng child theo đợt có test và kế hoạch rollback.
6. **Kiểm thử nhiều loại child.** Ứng dụng JAR/WAR, library, module có annotation processor, module không có test và project đa module có thể bị ảnh hưởng khác nhau.
7. **Hạn chế plugin executions áp lên mọi child.** Xác định mục tiêu nào bắt buộc, mục tiêu nào opt-in. Dùng `<inherited>false</inherited>` khi phù hợp với mong muốn và kiểm chứng hành vi.
8. **Tách bảo mật khỏi profile nguồn.** Secrets, proxy và tài khoản repository nên ở settings/CI secrets, không commit trong parent POM.
9. **Lưu bằng chứng.** Với mỗi phiên bản parent/profile quan trọng, ghi effective POM, active profiles, logs, Maven/JDK version và kết quả test của child đại diện.
10. **Tài liệu hóa các override được phép.** Nếu child thay `maven.compiler.release` hoặc plugin configuration, tổ chức phải biết khi nào đó là cấu hình hợp lệ hay vi phạm chính sách.

Mục tiêu của parent profile không phải làm mọi dự án “giống hệt nhau”, mà là chia sẻ những biến thể build có kiểm soát, dễ kích hoạt, dễ kiểm chứng và không gây khác biệt ngầm giữa laptop và CI.

## 11. Những hiểu nhầm cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Parent có profile thì child kế thừa nguyên profile đó.” | Child kế thừa **hiệu ứng được inject từ profile parent active**, không copy định nghĩa profile |
| “Chỉ có profile cùng ID thì implicit activation lan từ parent sang child.” | Implicit activation chỉ xét nơi profile được khai báo |
| “`-Pci` và `-Dci=true` luôn tương đương.” | `-P` chọn ID; `-D` chỉ ảnh hưởng nếu activation có điều kiện property tương ứng |
| “Profile parent inactive vẫn thêm plugin Enforcer.” | Các mục chỉ có trong profile inactive không được inject |
| “Có `dependencyManagement` trong profile active thì child tự tải thư viện.” | Management chỉ quản lý khi dependency được sử dụng; không tự thêm dependency |
| “Khai báo plugin trong pluginManagement khiến goal chạy.” | Plugin management không tự bind mọi goal; phải có lifecycle binding/actual plugin execution |
| “Child không có `<profiles>` nên parent profiles không thể ảnh hưởng.” | Parent profile active vẫn có thể thay đổi model con qua inheritance |
| “`activeByDefault` nghĩa là luôn active trên mọi dự án.” | Nó có điều kiện và thuộc ngữ cảnh POM nơi khai báo |
| “Mọi child trong aggregator kế thừa cấu hình root.” | Aggregation và inheritance là cơ chế riêng; child phải khai báo parent |
| “Maven settings profile có thể chứa build plugins như POM profile.” | Settings profiles có tập cấu phần giới hạn |
| “Ứng dụng in cùng stdout nghĩa là profile không ảnh hưởng.” | Profile có thể thay plugin/test/dependencies mà stdout ứng dụng không đổi |
| “Đã sửa parent release thì mọi child lập tức nhận cấu hình mới.” | Child pin version release cũ không tự nâng sang parent version mới |

## 12. Câu hỏi luyện tập và đáp án

**Câu 1.** Parent có profile `strict-quality` được kích hoạt bởi property `org.quality=strict`. Child không có phần `<profiles>`. Lệnh `mvn -Dorg.quality=strict verify` tại child có thể dùng plugin execution do profile parent thêm không?

**Đáp án:** Có, nếu parent profile được kích hoạt, execution có thể được inject vào model parent và inherited vào child (trừ khi có quy định không kế thừa/override phù hợp). Lệnh `verify` chạy qua phase `validate`, nên Enforcer goal bound vào `validate` có thể chạy.

**Câu 2.** Parent và child đều có profile ID `ci` nhưng điều kiện property khác nhau. Chỉ kích hoạt property dành cho child có tự kích hoạt profile parent không?

**Đáp án:** Không. Implicit activation theo property của một profile chỉ xét điều kiện profile đó, không lan sang profile cùng ID ở POM khác. Tuy nhiên, explicit `-Pci` có thể kích hoạt những khai báo ID `ci` phù hợp.

**Câu 3.** Parent active profile thêm JUnit version vào `dependencyManagement`. Child không khai báo JUnit trong `dependencies`. Child có JUnit test classpath tự động không?

**Đáp án:** Không. `dependencyManagement` quản lý metadata/version; child phải có dependency thực tế, hoặc nhận dependency trực tiếp đã được khai báo ở nơi khác qua inheritance.

**Câu 4.** CI build với JDK 21 và laptop với JDK 17. Một profile parent được kích hoạt bằng `<jdk>[21,)</jdk>`. Vì sao hai effective POM có thể khác?

**Đáp án:** Điều kiện kích hoạt dựa vào Java runtime dùng để chạy Maven. Profile active ở CI JDK 21 nhưng không active ở laptop JDK 17, nên các property/plugin/dependency từ profile được inject khác nhau.

**Câu 5.** Parent đã publish version 2.0.0 với profile mới, còn child vẫn pin parent 1.9.0. Khi chạy lại build không đổi POM, child có tự nhận profile mới không?

**Đáp án:** Không với các parent release bất biến và repository giải quyết đúng tọa độ. Muốn nhận thay đổi từ parent 2.0.0, child phải đổi parent version và kiểm thử lại.

## Tài liệu chính thức

- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven — Introduction to the POM: POM inheritance, aggregation](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Maven Model Builder: profile activation, profile injection, inheritance](https://maven.apache.org/ref/3.9.12/maven-model-builder/)
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven Enforcer Plugin — Introduction](https://maven.apache.org/enforcer/maven-enforcer-plugin/)
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
