# Parent dùng chung cho tổ chức và chi phí thay đổi đến các dự án con

Khi một tổ chức có hàng chục dịch vụ Java, việc lặp lại cùng phiên bản plugin, quy tắc biên dịch, cấu hình test và danh sách phiên bản thư viện trong từng `pom.xml` khiến cấu hình khó đồng bộ. Maven cho phép tạo **parent POM dùng chung**: mỗi dự án con khai báo `<parent>` để kế thừa những chính sách build đã được quản lý tập trung.

Lợi ích là giảm sao chép và thống nhất cách build; đổi lại, **mỗi bản cập nhật parent có thể ảnh hưởng đến nhiều dự án con**, làm tăng nhu cầu kiểm tra tương thích, phối hợp nâng cấp, phát hành và khả năng quay lui. Tổ chức cần hiểu chính xác những gì được kế thừa, điều gì chỉ được quản lý phiên bản, và **khi nào thay đổi parent mới thật sự có hiệu lực tại từng dự án**.

## 1. Parent POM là gì và khi nào nên dùng ở cấp tổ chức?

Parent POM là một Maven project có `<packaging>pom</packaging>`, cung cấp các khai báo và cấu hình được **kế thừa** qua quan hệ `<parent>`. Nó có tọa độ Maven riêng, ví dụ:

```text
vn.example.build:organization-parent:pom:1.2.0
```

Một dự án con khai báo tọa độ parent để Maven tìm POM đó và kết hợp model parent với model của chính dự án con trước khi thực hiện build. Dự án con có thể nhận các `properties`, dependency/plugin management, cấu hình plugin, thông tin repositories và một số thành phần POM khác từ parent theo quy tắc inheritance của Maven.

Dùng parent ở cấp tổ chức khi các dự án thực sự có **chính sách build chung**, chẳng hạn:

- Phiên bản JDK/compiler release và encoding thống nhất.
- Bộ Maven plugin, phiên bản và cấu hình plugin đã được thử nghiệm.
- Quy tắc chạy unit test, kiểm tra chất lượng, đóng gói và báo cáo.
- Phiên bản dependency dùng lặp lại, thông qua `dependencyManagement`.
- Quy ước metadata hoặc cấu hình phù hợp nhiều project.

Không nên buộc mọi dự án dùng cùng một parent nếu chúng có hệ sinh thái, tốc độ nâng cấp, runtime hoặc yêu cầu bảo mật khác nhau đáng kể. Một parent quá lớn có thể biến mọi nâng cấp nhỏ thành đợt kiểm thử trên toàn bộ tổ chức.

## 2. Phân biệt parent, aggregator và BOM

Ba cách tổ chức Maven thường bị nhầm:

| Cơ chế | Khai báo chính | Mục đích | Có tự tạo quan hệ kế thừa? |
| --- | --- | --- | --- |
| **Parent POM** | Dự án con khai báo `<parent>` | Kế thừa cấu hình POM và quy tắc build | **Có** |
| **Aggregator POM** | POM tổng khai báo `<modules>` | Gom nhiều module vào một Maven reactor để build cùng | **Không** |
| **BOM** (*Bill of Materials*) | Project import POM trong `<dependencyManagement>` với `type=pom`, `scope=import` | Cấp bộ phiên bản dependency theo nền tảng | **Không**; chỉ import dependency management |

Ví dụ một **aggregator**:

```xml
<modules>
    <module>service-a</module>
    <module>service-b</module>
</modules>
```

Đây là đoạn XML đặt trong POM packaging `pom`. Nó làm Maven biết các module được build cùng nhau, nhưng chỉ thêm `<modules>` **không khiến** các module kế thừa configuration. Ngược lại, một parent POM đã publish trong repository có thể được hàng trăm repository độc lập tham chiếu mà không chứa bất kỳ `<modules>` nào.

Ví dụ import **BOM**, cũng chỉ là đoạn XML bên trong `<dependencyManagement>`:

```xml
<dependency>
    <groupId>vn.example.build</groupId>
    <artifactId>organization-bom</artifactId>
    <version>2.0.0</version>
    <type>pom</type>
    <scope>import</scope>
</dependency>
```

BOM giúp chia sẻ phiên bản thư viện mà **không yêu cầu** các service nhận toàn bộ plugin, profiles, properties, parent coordinates hoặc các execution build khác từ parent. Một kiến trúc linh hoạt là **parent mỏng** cho quy định build và **BOM riêng** cho các phiên bản thư viện ứng dụng.

**Nguyên tắc thiết kế:** khi một yêu cầu chỉ là đồng bộ version thư viện, cân nhắc BOM; khi là chuẩn hóa Maven plugin/build, cân nhắc parent; khi cần thực thi nhiều module cùng nhau, dùng aggregator. Một POM có thể kiêm nhiều vai trò, nhưng cần rõ mục đích và phạm vi ảnh hưởng.

## 3. Parent chia sẻ những gì đến dự án con?

Maven tính **effective POM** bằng cách kết hợp cấu hình của Super POM, parent POM, project con và các profile được kích hoạt, theo những quy tắc merge/override cụ thể.

### 3.1. `properties` và chính sách compiler

Parent có thể đặt:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Nếu child không ghi đè, các property này được dùng trong build của child. Khi child định nghĩa lại `maven.compiler.release`, giá trị sau khi merge có thể khác policy của parent; cần có test hoặc plugin kiểm tra quy tắc nếu tổ chức không muốn cho phép ghi đè. `maven.compiler.release=17` không tự tải JDK 17; môi trường CI phải cung cấp compiler/runtime tương thích.

### 3.2. `dependencyManagement`: quản lý version, không tự thêm dependency

Parent có thể quản lý phiên bản JUnit:

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

Child **chỉ thực sự phụ thuộc JUnit** khi khai báo trong `<dependencies>` (hoặc nhận dependency qua kế thừa từ một khai báo `<dependencies>` của parent):

```xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Vì có management ở parent, child không cần nhắc lại `<version>5.11.0</version>`. Scope `test` do child chọn. Nếu parent chỉ khai báo JUnit trong `dependencyManagement` và child không khai báo nó, JUnit **không tự xuất hiện** như dependency trực tiếp của child. Ngược lại, thêm dependency thực sự trong parent `<dependencies>` có thể làm mọi child nhận dependency đó, tăng bề mặt thay đổi và xung đột.

### 3.3. `pluginManagement` và `plugins`

Hai vùng build có ý nghĩa khác nhau:

- `<build><pluginManagement>` định nghĩa version và cấu hình mặc định cho plugin được dùng bởi project con hoặc lifecycle; **không có nghĩa mọi goal của mọi plugin được quản lý đều tự chạy**.
- `<build><plugins>` là các plugin được khai báo để sử dụng. Những execution của plugin trong parent có thể được kế thừa (theo cờ `inherited` và các quy tắc merge), dẫn đến goal thực thi trong child khi phase được gọi.

Ví dụ, đặt `maven-compiler-plugin` version `3.13.0` trong `pluginManagement` giúp lifecycle compile dùng bản được quản lý. Nếu parent thêm execution chạy formatter vào `validate` trong `<plugins>`, mọi child kế thừa execution đó có thể bị thay đổi kết quả build.

Maven có `<inherited>false</inherited>` cho một số cấu hình plugin/execution nhằm giới hạn kế thừa. Không nên dùng rộng rãi mà thiếu thử nghiệm vì luật merge giữa parent và child phụ thuộc vị trí và ID execution.

### 3.4. Những gì không nên đặt trong parent

- Thông tin bí mật: mật khẩu repository, token, key nội bộ; nên dùng Maven `settings.xml`/secret store của CI.
- Dependency chỉ đúng với một ứng dụng, trừ khi đây là một platform parent đã chủ đích áp đặt.
- Đường dẫn tuyệt đối hoặc lệnh chỉ hoạt động trên máy quản trị.
- Execution tốn kém của tool không phải dự án con nào cũng cần.
- Cấu hình repository không ổn định hoặc phụ thuộc mạng nội bộ mà mọi team không truy cập được.

Parent POM không thay thế cấu hình môi trường (JDK, credentials, Maven Wrapper, CI runners). Nó là một **hợp đồng build được version hóa**, không phải hệ thống quản trị toàn bộ máy phát triển.

## 4. Ví dụ Java 17 hoàn chỉnh: một parent và một service con

Tạo hai project anh em trong cùng một workspace để thực hành parent inheritance mà không phải publish parent ngay. Thư mục:

```text
workspace/
├── build-parent/
│   └── pom.xml
└── order-service/
    ├── pom.xml
    └── src/
        ├── main/java/vn/example/orders/App.java
        └── test/java/vn/example/orders/AppTest.java
```

### 4.1. File `build-parent/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.build</groupId>
    <artifactId>organization-parent</artifactId>
    <version>1.2.0</version>
    <packaging>pom</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                    <artifactId>maven-clean-plugin</artifactId>
                    <version>3.3.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-resources-plugin</artifactId>
                    <version>3.3.1</version>
                </plugin>
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

Parent khai báo `packaging=pom`, chuẩn Java 17/UTF-8, version quản lý cho JUnit và một số Maven plugins. Nó **không khai báo `<modules>`**, vì vậy đây là parent chia sẻ cấu hình, **không tự động là aggregator** cho `order-service`.

### 4.2. File `order-service/pom.xml`

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
        <version>1.2.0</version>
        <relativePath>../build-parent/pom.xml</relativePath>
    </parent>

    <artifactId>order-service</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Child không khai báo `groupId`, `version` hoặc `maven.compiler.release` nên thừa hưởng chúng từ parent. Tọa độ của child là **`vn.example.build:order-service:1.2.0`**; với packaging mặc định `jar`, file đầu ra sẽ thường là `target/order-service-1.2.0.jar`. Lưu ý rằng child **không kế thừa `packaging=pom`** của parent thành packaging của chính mình; nó dùng packaging mặc định `jar` nếu không khai báo.

`<relativePath>../build-parent/pom.xml</relativePath>` là đường dẫn tính từ thư mục chứa POM child. Nó cho phép Maven tìm parent ở cây thư mục cục bộ khi tọa độ khớp, không cần parent đã được publish/installed cho ví dụ này. Trong dự án độc lập tải parent từ repository, có thể dùng `<relativePath/>` để bỏ qua bước tìm parent theo đường dẫn mặc định `../pom.xml`.

### 4.3. File `order-service/src/main/java/vn/example/orders/App.java`

```java
package vn.example.orders;

public final class App {
    private App() {
    }

    public static String message() {
        return "Order service ready";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

### 4.4. File `order-service/src/test/java/vn/example/orders/AppTest.java`

```java
package vn.example.orders;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Order service ready", App.message());
    }
}
```

Test sử dụng JUnit Jupiter. Version `5.11.0` không nằm trong `pom.xml` của child mà được áp dụng qua `dependencyManagement` của parent. Maven Surefire (đã quản lý version) là plugin chạy unit test trong lifecycle JAR.

### 4.5. Chạy và xác minh những gì được kế thừa

Từ thư mục `workspace/order-service`, cần JDK 17+, Maven 3.9.x phù hợp và mạng để tải plugin/dependency lần đầu:

```bash
java -version
mvn --version
mvn -B clean verify
java -cp target/order-service-1.2.0.jar vn.example.orders.App
```

Nếu build `clean verify` thành công, lệnh `java` sau cùng in **chính xác**:

```text
Order service ready
```

Đây là stdout của chương trình `App`, **không phải** toàn bộ log Maven. Unit test không in một dòng này lên stdout: nó so sánh giá trị trả về và báo PASS khi assertion thành công.

Có thể xem effective POM và dependency graph:

```bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn dependency:tree -Dscope=test
```

Các goal `help:effective-pom` và `dependency:tree` cần tương ứng Maven Help/Dependency Plugin có thể tải từ repository; nếu offline chưa cache đủ, chúng có thể thất bại độc lập với mã ứng dụng. Trong effective POM, kiểm tra `groupId=vn.example.build`, `version=1.2.0`, `maven.compiler.release=17`, JUnit Jupiter được quản lý version và các plugin versions tương ứng. `dependency:tree` cho thấy JUnit và dependency bắc cầu ở scope test.

**Không chạy `mvn package` bên trong `build-parent` rồi đợi tự build `order-service`**: parent không có `<modules>`. Hãy chạy goal tại project con, hoặc tạo một aggregator riêng nếu cần reactor tập hợp.

## 5. Parent được tìm và phát hành như thế nào?

Trong repository thực tế, parent thường được build và **publish như artifact kiểu `pom`**, ví dụ `vn.example.build:organization-parent:pom:1.2.0`, vào Maven repository manager đã được doanh nghiệp phê duyệt. Dự án con đặt tọa độ của parent trong `<parent>` và dùng repository/settings hợp lệ để resolve.

Maven có thể tìm parent qua đường dẫn cục bộ `<relativePath>` nếu phù hợp; sau đó có thể resolve từ local repository hoặc remote repository khi được cấu hình. Mặc định `relativePath` là `../pom.xml`. Nếu chỉ có parent publish và repository độc lập, thường đặt:

```xml
<parent>
    <groupId>vn.example.build</groupId>
    <artifactId>organization-parent</artifactId>
    <version>1.2.0</version>
    <relativePath/>
</parent>
```

Đây là **đoạn XML**, đặt bên trong `<project>`. `<relativePath/>` yêu cầu Maven **không tìm parent qua đường dẫn file cục bộ mặc định**; parent phải có sẵn trong repository local/remote phù hợp. Với các project ở nhiều Git repositories, cách này tránh vô tình trỏ tới POM không liên quan ở thư mục cha.

Để publish parent, tổ chức cần pipeline phát hành POM, version quản lý độc lập và quyền truy cập repository. `mvn install` chỉ cài trong **local repository trên máy đó**; `mvn deploy` mới thực hiện publish tới remote repository theo `distributionManagement` và credential phù hợp. Không commit credentials trong parent POM; nên cấu hình chúng ở settings/CI secret store.

## 6. Parent version cố định: thay đổi không tự lan đến mọi child

Đây là điểm quan trọng nhất khi đánh giá chi phí thay đổi.

Giả sử tổ chức đã publish hai phiên bản parent:

```text
vn.example.build:organization-parent:pom:1.2.0
vn.example.build:organization-parent:pom:1.3.0
```

Một child vẫn khai báo:

```xml
<parent>
    <groupId>vn.example.build</groupId>
    <artifactId>organization-parent</artifactId>
    <version>1.2.0</version>
    <relativePath/>
</parent>
```

thì **không tự nhận cấu hình parent 1.3.0** chỉ vì tổ chức đã phát hành bản mới. Để nhận chính sách mới, child phải **đổi version parent**, rồi build/test lại:

```xml
<parent>
    <groupId>vn.example.build</groupId>
    <artifactId>organization-parent</artifactId>
    <version>1.3.0</version>
    <relativePath/>
</parent>
```

Phiên bản parent release nên được coi là **bất biến**. Sửa nội dung và publish lại dưới cùng tọa độ release có thể gây cache khác nhau giữa các máy, làm mất khả năng tái lập build. Nếu dùng parent `-SNAPSHOT`, Maven có thể cập nhật bản snapshot theo chính sách repository, tạo thay đổi mà child chưa sửa Git; vì vậy cần kiểm soát rõ khi áp dụng cho môi trường production.

**Cảnh báo về phiên bản chính child:** ví dụ ở mục 4 kế thừa luôn `<version>1.2.0</version>` của parent. Nếu chỉ đổi `<parent><version>` sang `1.3.0` mà không khai báo `<project><version>` riêng, **tọa độ artifact của child cũng đổi từ `...:order-service:1.2.0` thành `...:order-service:1.3.0`**. Điều này có thể ảnh hưởng downstream dependencies, tên artifact, container image tag, release pipeline và lịch phát hành sản phẩm.

Nếu tổ chức muốn version dịch vụ độc lập với version của build parent, child nên khai báo rõ:

```xml
<parent>
    <groupId>vn.example.build</groupId>
    <artifactId>organization-parent</artifactId>
    <version>1.3.0</version>
    <relativePath/>
</parent>
<groupId>vn.example.services</groupId>
<artifactId>order-service</artifactId>
<version>2.7.0</version>
```

Đây là đoạn POM minh họa: parent version `1.3.0` dùng cho **chính sách build**, còn project version `2.7.0` dùng cho **artifact nghiệp vụ**. Hai vòng đời phiên bản có thể vận hành độc lập.

## 7. Chi phí thay đổi parent lan tới nhiều dự án như thế nào?

Chi phí chính không phải “sửa một dòng XML” ở parent mà là **kiểm chứng những dự án chịu tác động khi nâng version parent**.

| Loại thay đổi parent | Ảnh hưởng có thể phát sinh ở child | Việc cần kiểm tra |
| --- | --- | --- |
| Đổi `maven.compiler.release` từ 17 lên 21 | Runner dùng JDK 17 không biên dịch được target 21; thư viện runtime không tương thích | JDK CI/local, runtime triển khai, toolchain, test trên JDK mục tiêu |
| Nâng `maven-compiler-plugin` | Thay hành vi compile, annotation processing hoặc thông báo lỗi | Build tất cả kiểu module, source/target và generated code |
| Nâng `maven-surefire-plugin` hoặc cấu hình test | Thay cách khám phá/chạy unit test, test providers | JUnit/TestNG, CI report, test pass/fail và thời gian |
| Nâng phiên bản managed dependency/BOM | Thay API hoặc transitive dependency graph của child **có sử dụng dependency đó** | Dependency tree, unit/integration test, tương thích binary/runtime |
| Chuyển goal kiểm tra sang `<plugins>` và bind vào `verify` | Build của nhiều child chậm đi hoặc fail vì rule mới | Plugin execution thực tế, thời gian CI, rule exceptions |
| Thêm dependency ở `<dependencies>` của parent | Mọi child có thể nhận dependency trực tiếp, classpath thay đổi | Conflict/exclusion, license, CVE, classpath |
| Đổi repositories/pluginRepositories | Parent/dependency/plugin có thể không resolve được trên CI | Repository/mirror, quyền truy cập, policy network |
| Đổi metadata/encoding/packaging config | Artifact output, file encoding, manifest hoặc published POM khác | So sánh artifact, checksum, manifest, consumer |
| Đổi `<parent><version>` ở child có kế thừa project version | **Artifact version của child thay đổi** ngoài dự định | Release tagging, downstream compatibility, deploy path |

Đặc biệt nguy hiểm là **thay đổi cấu hình plugin execution**: một goal mới gắn vào `validate` hoặc `verify` có thể làm hàng chục project build chậm hoặc thất bại, dù mã nguồn của chúng không đổi. Chi phí sẽ gồm phân tích tính tương thích, cập nhật CI/JDK, sửa code hoặc config cục bộ, chạy test, review và hỗ trợ team.

Có thể suy nghĩ chi phí một đợt migration theo mô hình:

```text
Tổng effort xấp xỉ:
  xây dựng + QA bản parent mới
+ kiểm thử dự án đại diện
+ tổng effort nâng parent ở từng child
+ tổng effort khắc phục lỗi tương thích
+ release/triển khai/phối hợp giữa các nhóm
+ giám sát và kế hoạch rollback
```

Không thể lấy số dự án nhân với một thời gian cố định: mức độ ảnh hưởng tùy sự khác biệt giữa các project, việc chúng có sử dụng dependency/plugin được đổi hay không, độ bao phủ test, số nền tảng chạy và quyền tự chủ của từng team. Các chỉ số thực tế hữu ích là **tỷ lệ child đã nâng**, **số build/test thất bại vì parent mới**, **thời gian CI thay đổi**, và **thời gian hoàn tất một đợt nâng cấp**.

## 8. Cách thiết kế parent để giảm “bán kính ảnh hưởng”

Một parent dùng chung tốt nên tách phần **policy thật sự chung** khỏi phần **tuỳ chọn theo dự án**:

1. **Ưu tiên management thay vì áp đặt:** giữ version chung trong `dependencyManagement` và `pluginManagement`; chỉ thêm dependency/plugin execution áp dụng cho mọi child khi có chủ đích.
2. **Parent mỏng, tính tương thích rõ ràng:** chia thành parent cho library, service hoặc application platform khi policy khác nhau thật sự. Tránh một parent chứa mọi tool của mọi nhóm.
3. **BOM độc lập nếu chỉ cần versions:** consumer có thể import BOM mà không thay đổi cấu hình build hoặc quan hệ parent.
4. **Project versions độc lập nếu phát hành độc lập:** không để mọi service vô tình đổi tọa độ chỉ vì nâng parent build.
5. **Pin versions của Maven plugins/dependencies:** không phụ thuộc bản mới “tình cờ” từ repository.
6. **Bảo vệ extension point:** xác định những property/execution child được override, những quy định bắt buộc cần kiểm tra bằng CI hoặc công cụ kiểm định, thay vì coi mọi phần tử được khai báo ở parent là bất biến.
7. **Không lồng môi trường vào model:** tách secrets, proxy và credential khỏi parent; dùng Maven settings, CI variables và secret store.
8. **Tài liệu hóa parent:** có compatibility matrix (Maven, JDK, framework), changelog, ví dụ nâng version, nhóm sở hữu và quy trình báo lỗi.

Một số dự án đã kế thừa một parent khác, ví dụ parent của framework. Maven chỉ cho một **`<parent>` trực tiếp**; muốn dùng cả framework parent lẫn parent tổ chức, cần quyết định chuỗi kế thừa (organization parent kế thừa framework parent, hoặc ngược lại), hoặc **dùng BOM và quản lý plugin tường minh**. Không thể khai báo hai thẻ `<parent>` độc lập rồi mong Maven trộn tự động.

## 9. Quy trình thay đổi parent có kiểm soát

### 9.1. Trước khi phát hành

- **Xác định thay đổi chính xác:** POM elements, plugins, managed dependencies, inherited executions, profiles và version chính sách JDK.
- **Phân loại mức ảnh hưởng:** lỗi build tiềm năng, đổi API/runtime, thay artifact output, tăng yêu cầu môi trường hay chỉ sửa metadata.
- **Chọn child đại diện:** library thuần Java, web service, batch job, multi-module, project có annotation processors, test integration, OS/JDK khác nhau.
- **Chạy baseline:** build phiên bản parent cũ thành công trên các project đại diện; ghi version Maven Wrapper/JDK/runner.
- **Tạo parent release mới:** không mutate phiên bản release đang dùng. Viết changelog và hướng dẫn migration.

### 9.2. Phát hành và rollout theo đợt

1. Publish `organization-parent:1.3.0` như POM artifact vào Maven repository manager chính thức.
2. Nâng một hoặc vài child **pilot** từ 1.2.0 lên 1.3.0; không tự đồng loạt cập nhật mọi repository.
3. Chạy compile, unit test, integration test, quality gates và packaging như môi trường production.
4. Kiểm tra Maven effective POM và dependency graph để biết **những gì thật sự thay đổi** sau khi merge.
5. So sánh artifact đầu ra, manifest, thông số Java, thời gian CI và các cảnh báo mới.
6. Nếu pilot đạt yêu cầu, nâng từng nhóm child bằng PR có chủ sở hữu, reviewer và bằng chứng test.
7. Theo dõi tỷ lệ adoption, lỗi tương thích mới và phản hồi; giữ parent cũ đủ thời gian để các dự án chưa kịp nâng vẫn build được.

Đây là **rollout opt-in theo phiên bản**. Nếu mọi child pin parent `1.2.0` thì việc publish 1.3.0 không đồng nghĩa chúng lập tức bị ảnh hưởng. Điều này giúp giảm sự cố đồng loạt, đổi lại có chi phí duy trì song song nhiều nhánh chính sách parent.

### 9.3. Khi cần rollback

Nếu một child nâng version parent và build/test thất bại, có thể revert thay đổi `<parent><version>` về bản release trước rồi chạy lại pipeline với cấu hình cũ, miễn repository còn lưu bản đó và các thay đổi liên quan cũng được hoàn nguyên.

**Không đồng nhất rollback parent với rollback ứng dụng đã deploy.** Nếu project kế thừa version artifact từ parent, nâng version parent có thể đã tạo/publish artifact mang tọa độ khác; quay lại source POM không tự xóa hoặc thu hồi artifact đã phát hành, cũng không rollback môi trường runtime. Cần có chính sách phát hành và deployment rollback riêng.

## 10. Tự kiểm tra tác động bằng lệnh Maven

Trong **thư mục một child** và với settings/repository có đủ quyền truy cập:

```bash
mvn --version
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn dependency:tree
mvn -B clean verify
```

Những lệnh này giúp xác minh:

- Maven/JDK thực tế trên máy có hỗ trợ policy mới không.
- **Effective POM** chứa version project, compiler release, plugin management/actual plugin configuration thế nào sau inheritance.
- **Dependency tree** có thay đổi trực tiếp/bắc cầu hoặc version conflict không.
- Build/test có đi qua các goal thực tế không; với project quan trọng, vẫn phải chạy integration/end-to-end/security tests tùy đặc thù.

Muốn so sánh trước/sau, lưu hai kết quả effective POM và dependency tree ở **hai môi trường build riêng biệt** trước và sau thay đổi; tránh ghi đè cùng một file. Không lấy số lượng dòng khác nhau trong effective POM làm kết luận tự động về mức độ rủi ro; cần đánh giá những plugin, dependencies và thuộc tính nào thực sự ảnh hưởng.

Nếu gặp lỗi parent:

| Dấu hiệu | Chẩn đoán hợp lý |
| --- | --- |
| `Non-resolvable parent POM` | Parent không có ở local/remote repository, credentials/mirror sai, mạng lỗi hoặc tọa độ nhầm |
| `parent.relativePath points at wrong local POM` | File local được tìm không khớp `groupId:artifactId:version` của parent khai báo |
| Child dùng Java khác mong đợi | Effective POM/properties bị override hoặc CI JDK không đúng |
| Version plugin không đúng bản parent quản lý | Child/parent trung gian ghi đè hoặc plugin execution khác |
| Tự nhiên xuất hiện dependency/library mới | Có thể parent dùng `<dependencies>` thay vì chỉ `<dependencyManagement>` |
| Nâng parent làm đổi tên/version JAR | Child có thể kế thừa `<version>` của parent hoặc thay đổi `finalName` |

**Đọc log và effective POM trước khi sửa.** Thay đổi `relativePath` chỉ hợp lý khi hiểu parent sẽ được lấy từ file local hay repository. Đừng tự copy parent POM vào mỗi repo: điều đó sẽ làm mất mục tiêu quản trị tập trung và tăng divergence.

## 11. Câu hỏi tự luyện và đáp án

**Tình huống 1:** parent khai báo `junit-jupiter:5.11.0` trong `dependencyManagement` nhưng child không thêm JUnit vào `<dependencies>`. Child có tự động chạy JUnit tests không?

**Đáp án:** Không. Management chỉ cung cấp version/chi tiết cấu hình khi dependency được sử dụng. Muốn dùng JUnit, child phải khai báo dependency (hoặc nhận từ một `<dependencies>` inherited) và có test cũng như plugin phù hợp.

**Tình huống 2:** parent tổ chức phát hành 1.3.0. Child đang pin 1.2.0. Ngày hôm sau child CI chạy build mà code không đổi. Nó có tự nhận plugin versions của 1.3.0 không?

**Đáp án:** Không, với parent release được pin đúng tọa độ và không bị mutate. Child vẫn resolve parent 1.2.0. Muốn áp dụng 1.3.0 cần cập nhật tham chiếu parent và kiểm chứng lại.

**Tình huống 3:** child `order-service` không khai báo project `version` và đang kế thừa 1.2.0. Team đổi `<parent><version>` thành 1.3.0. Điều gì có thể xảy ra với tọa độ child?

**Đáp án:** Version artifact của child cũng sẽ thành 1.3.0, nếu không có cơ chế override/version khác; cần xem effective POM. Đây là ảnh hưởng release cần phát hiện trước migration.

**Tình huống 4:** một đội chỉ muốn đồng bộ version của 20 thư viện giữa các service đã có framework parent riêng. Có cần ép mọi service chuyển sang một parent tổ chức mới?

**Đáp án:** Không nhất thiết. Cân nhắc import **BOM** vào `dependencyManagement` để thống nhất versions mà không thay quan hệ parent hoặc plugin executions. Các trường hợp conflict/version precedence vẫn cần kiểm tra trong effective POM và dependency tree.

## Tài liệu chính thức

- [Apache Maven — Introduction to the POM: project inheritance, aggregation và variables](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — POM Reference: dependencyManagement, pluginManagement, inheritance](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the Dependency Mechanism: dependencyManagement và BOM](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
