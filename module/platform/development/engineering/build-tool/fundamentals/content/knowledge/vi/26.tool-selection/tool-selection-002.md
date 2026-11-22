# Maven: mô hình dự án, POM và vòng đời theo quy ước

Maven là công cụ build và quản lý dự án Java dựa trên một mô hình dự án chuẩn, một file mô tả cấu hình trung tâm là **Project Object Model (POM)** và các **lifecycle** được xác định trước. Thay vì phải viết một chuỗi task cho mọi thao tác cơ bản, dự án Maven khai báo thông tin, dependency và plugin trong POM; Maven dùng các quy ước về thư mục, cấu trúc project và lifecycle để biết cách biên dịch, kiểm thử, đóng gói và cài đặt artifact.

Triết lý thường được mô tả là **convention over configuration**: dự án tuân theo quy ước mặc định thì cần ít cấu hình. Khi có yêu cầu riêng, POM có thể ghi đè hoặc mở rộng hành vi bằng plugin, property, profile và cấu hình build.

Ba khái niệm cần nắm:

- **Mô hình dự án:** Maven hiểu project gồm tọa độ, packaging, dependency, module, plugin, profile và metadata như thế nào.
- **POM:** file XML mô tả project và các quy tắc cần thiết để Maven xây dựng project đó.
- **Lifecycle:** chuỗi phase chuẩn, trong đó plugin goals được gắn vào để thực hiện công việc.

~~~text
                 pom.xml
                    |
                    v
             Maven project model
        /           |             \
       v            v              v
  Dependencies   Plugins       Packaging/modules
       \            |              /
        \           |             /
         v          v            v
             Lifecycle phases
                    |
                    v
       Compile -> Test -> Package
                    |
                    v
           Install / Deploy
~~~

Khi chạy lệnh mvn package, Maven không tìm một task tên package do người viết tự định nghĩa. Nó đi đến phase package trong default lifecycle, lần lượt chạy các phase trước đó và thực thi những plugin goals được gắn với các phase ấy.

## 1. Convention over configuration

Maven cung cấp sẵn các quy ước để các project có cấu trúc nhất quán. Với một ứng dụng Java thông thường, mã nguồn production nằm trong src/main/java, tài nguyên production trong src/main/resources, mã test trong src/test/java và tài nguyên test trong src/test/resources.

Maven biết các vị trí này mà không cần khai báo từng thư mục trong POM. Khi project dùng cấu trúc mặc định, POM có thể khá ngắn.

~~~text
my-app/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/app/
    │   └── resources/
    └── test/
        ├── java/
        │   └── com/example/app/
        └── resources/
~~~

Các thư mục output mặc định:

- target/classes: class đã biên dịch và resource production.
- target/test-classes: class và resource của test.
- target/surefire-reports: báo cáo test của Maven Surefire theo cấu hình mặc định phổ biến.
- target/: thư mục output chung của project, được lệnh mvn clean dọn.

### Lợi ích của quy ước

- Thành viên mới dễ nhận ra mã nguồn, test, resource và output.
- Plugin có thể hoạt động với cấu hình mặc định.
- Các project trong cùng tổ chức có cấu trúc gần giống nhau.
- POM tập trung vào những điểm khác biệt thay vì mô tả lại mọi bước cơ bản.
- CI có thể dùng một nhóm lệnh chuẩn cho nhiều project.

### Khi nào cần cấu hình khác?

Một project có thể dùng thư mục source đặc biệt, code generator, frontend build hoặc nhiều loại artifact. Khi đó, POM/plugin cần khai báo rõ vị trí và thứ tự công việc. Chỉ thay đổi convention khi có lý do cụ thể; cấu trúc riêng không nhất thiết sai nhưng làm tăng phần cấu hình và yêu cầu onboarding.

## 2. POM là gì?

POM là viết tắt của **Project Object Model**. POM chính là mô hình Maven dùng để hiểu một project và cách xây dựng nó. File phổ biến nhất là pom.xml ở thư mục gốc project.

POM có thể mô tả:

- Tọa độ định danh project.
- Loại artifact được tạo.
- Dependency trực tiếp và cách quản lý dependency.
- Parent POM và các module con.
- Plugin và cấu hình build.
- Profile và property.
- Repository và distribution management.
- Thông tin project, license, developer và SCM.

Một POM tối thiểu cho ứng dụng Java:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>hello-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
</project>
~~~

modelVersion là phiên bản mô hình POM, không phải version của ứng dụng. groupId, artifactId và version xác định tọa độ của artifact. packaging cho Maven biết loại sản phẩm project tạo ra và lifecycle bindings mặc định tương ứng.

POM có thể khai báo thêm name, description, URL, organization, developers, licenses, SCM và issue management. Các metadata này hữu ích cho tài liệu và publication, nhưng không phải tất cả đều cần để biên dịch một project nhỏ.

## 3. Tọa độ Maven: groupId, artifactId và version

Maven xác định artifact bằng các tọa độ chính:

- **groupId:** nhóm hoặc namespace sở hữu artifact, thường dùng dạng tên miền đảo ngược.
- **artifactId:** tên artifact cụ thể trong group.
- **version:** phiên bản artifact.

Ví dụ tọa độ:

~~~text
com.example.platform:payment-core:2.3.0
~~~

Tọa độ trên thường được viết theo thứ tự groupId:artifactId:version. Trong repository Maven, đường dẫn được tạo từ groupId, artifactId và version.

Với groupId com.example.platform, artifactId payment-core và version 2.3.0, file JAR thường có tên:

~~~text
com/example/platform/payment-core/2.3.0/payment-core-2.3.0.jar
~~~

### Packaging và classifier

Ngoài GAV, artifact có thể có packaging/type và classifier để phân biệt các dạng output. Ví dụ một project có thể publish JAR chính và JAR chứa source:

~~~text
payment-core-2.3.0.jar
payment-core-2.3.0-sources.jar
payment-core-2.3.0-javadoc.jar
~~~

Classifier thường giúp phân biệt artifact bổ sung cùng tọa độ chính. Packaging trong POM mô tả loại artifact chính của project, chẳng hạn jar, war hoặc pom.

### Version release và snapshot

Version release như 2.3.0 thường đại diện cho một bản phát hành bất biến theo policy repository. Version snapshot như 2.4.0-SNAPSHOT đại diện cho bản phát triển có thể được cập nhật trong snapshot repository.

Không nên dùng snapshot như một dependency release cần tái lập nghiêm ngặt. Cần quản lý version cụ thể, repository và policy redeploy phù hợp.

## 4. Cấu trúc cơ bản của POM

Một POM thường có các nhóm thông tin chính:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>...</parent>

    <groupId>com.example</groupId>
    <artifactId>hello-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Hello Application</name>
    <properties>...</properties>

    <dependencies>...</dependencies>

    <dependencyManagement>...</dependencyManagement>

    <build>...</build>

    <profiles>...</profiles>
</project>
~~~

Đây là sơ đồ vị trí các phần tử, không phải POM hoàn chỉnh để copy. parent là tùy chọn. Nếu groupId hoặc version được kế thừa từ parent, project con có thể không cần khai báo lại.

### Properties

Properties cho phép đặt giá trị dùng lại trong POM, chẳng hạn phiên bản Java mục tiêu hoặc version dependency được quản lý. Maven nội suy property trong những trường hỗ trợ biểu thức property.

Ví dụ:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <junit.version>5.11.4</junit.version>
</properties>
~~~

Một property chỉ có tác dụng khi được tham chiếu bởi plugin hoặc dependency configuration phù hợp. Đặt property java.version không tự bảo đảm mọi compiler plugin đều sử dụng nó nếu plugin không được cấu hình để đọc property đó.

### Build

Phần build thường chứa plugin, resource, source directory và các thiết lập build. plugins cấu hình plugin được project sử dụng. pluginManagement quản lý version và cấu hình mặc định của plugin cho project con hoặc plugin được khai báo ở nơi khác.

## 5. Một POM ứng dụng Java hoàn chỉnh hơn

Ví dụ sau thể hiện một project JAR có dependency, encoding, Java release và plugin version được khai báo tường minh:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>hello-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Hello Application</name>
    <description>Example Java application built with Maven</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

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

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ví dụ chọn version plugin cụ thể để giảm sự phụ thuộc vào default plugin version của môi trường. Trong project thật, hãy dùng version đã được kiểm tra với Maven/JDK của tổ chức và cập nhật theo chính sách.

Với POM trên:

- mvn compile biên dịch mã nguồn production.
- mvn test chạy các phase trước test và thực thi unit test.
- mvn package tạo JAR sau khi chạy các phase trước package.
- mvn verify tiếp tục qua package và các bước xác minh được cấu hình.
- mvn install cài artifact vào local Maven repository.

POM không cần liệt kê thủ công từng lệnh javac, jar hay từng thư mục output. Maven plugin và lifecycle thực hiện những công việc đó theo quy ước.

## 6. Maven model được hình thành như thế nào?

POM mà Maven sử dụng trong thực tế có thể đến từ nhiều lớp cấu hình. Maven xây dựng một effective model từ:

1. POM của project hiện tại.
2. POM parent được kế thừa.
3. Super POM mặc định của Maven.
4. Profile đang active và các property liên quan.
5. Các quy tắc model interpolation và inheritance.

Kết quả được gọi là **effective POM**. Nó thể hiện cấu hình sau khi Maven đã kết hợp các nguồn liên quan.

### Super POM

Maven có một Super POM cung cấp cấu hình mặc định nền tảng, bao gồm một số repository, plugin và cấu hình build. Project không cần copy toàn bộ Super POM vào file riêng.

Khi build có hành vi khó hiểu, hãy kiểm tra effective POM để thấy cấu hình thực tế Maven đang sử dụng thay vì chỉ đọc một đoạn pom.xml.

### Xem effective POM

Có thể dùng Maven Help Plugin:

~~~shell
mvn help:effective-pom
~~~

Có thể lưu output để điều tra:

~~~shell
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Effective POM có thể chứa nhiều cấu hình được kế thừa và có thể dài. Nếu chia sẻ output, hãy kiểm tra xem có đường dẫn nội bộ hoặc dữ liệu nhạy cảm nào được đưa vào không.

### Xem profile đang active

~~~shell
mvn help:active-profiles
~~~

Lệnh này giúp xác định profile nào đang ảnh hưởng đến model. Nếu hai máy có profile khác nhau, dependency, plugin hoặc property có thể được cấu hình khác nhau dù cùng checkout.

## 7. Dependency trong POM

Dependency khai báo thư viện mà project cần. Mỗi dependency thường có groupId, artifactId, version và scope.

Ví dụ:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>payment-core</artifactId>
        <version>2.3.0</version>
    </dependency>
</dependencies>
~~~

Khi Maven resolve dependency, nó tải artifact cùng metadata cần thiết từ repository đã cấu hình. Dependency có thể kéo theo dependency bắc cầu (transitive dependencies).

### Dependency scope

Scope xác định dependency được sử dụng ở những classpath/lifecycle nào và có được truyền bắc cầu hay không.

| Scope | Compile classpath | Runtime classpath | Test classpath | Ghi chú |
|---|---:|---:|---:|---|
| compile | Có | Có | Có | Mặc định nếu không ghi scope; thường được truyền bắc cầu. |
| provided | Có | Không như dependency runtime đóng gói | Có | Môi trường chạy dự kiến cung cấp, ví dụ servlet API trong một số ứng dụng WAR. |
| runtime | Không cho compile source chính | Có | Có | Thư viện chỉ cần khi chạy, ví dụ JDBC driver. |
| test | Không | Không | Có | Chỉ phục vụ test; không truyền bắc cầu như dependency compile/runtime thông thường. |
| system | Có | Theo cách cấu hình classpath | Có | Tham chiếu file cục bộ; không khuyến nghị vì kém di động. |
| import | Không phải scope dependency thông thường | Không | Không | Dùng trong dependencyManagement để import BOM với packaging pom. |

Scope ảnh hưởng classpath, không phải chỉ là nhãn mô tả. Chọn sai scope có thể làm project biên dịch được nhưng runtime thiếu class, hoặc vô tình đưa thư viện test vào sản phẩm.

### Dependency bắc cầu

Nếu project A phụ thuộc B và B phụ thuộc C, Maven có thể đưa C vào dependency graph của A theo quy tắc scope và mediation. Điều này giúp consumer không cần khai báo lại mọi dependency của thư viện mà nó sử dụng gián tiếp.

Tuy nhiên, nếu mã nguồn A sử dụng trực tiếp API của C, thường nên khai báo C trực tiếp. Việc dựa vào một dependency bắc cầu không phải hợp đồng rõ ràng của project.

### Exclusions và optional

Có thể loại một dependency bắc cầu không mong muốn bằng exclusions. Một dependency có thể được đánh dấu optional để không tự động truyền đến consumer theo cách dependency thông thường.

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-client</artifactId>
    <version>1.4.0</version>
    <exclusions>
        <exclusion>
            <groupId>commons-logging</groupId>
            <artifactId>commons-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Exclusion nên có lý do rõ ràng và được kiểm tra tương thích. Loại một dependency mà thư viện vẫn cần ở runtime có thể tạo lỗi ClassNotFoundException hoặc NoClassDefFoundError.

## 8. Dependency mediation và dependency tree

Nhiều dependency có thể yêu cầu các version khác nhau của cùng một thư viện. Maven dùng quy tắc mediation để chọn version theo dependency graph, trong đó nguyên tắc nearest definition là một phần quan trọng.

Không nên đoán version cuối cùng chỉ bằng cách nhìn dependency trực tiếp. Hãy xem dependency tree:

~~~shell
mvn dependency:tree
~~~

Có thể lọc theo artifact:

~~~shell
mvn dependency:tree -Dincludes=org.slf4j
~~~

Nếu cần kiểm soát version đồng nhất trong nhiều module, dùng dependencyManagement hoặc BOM. Khi có xung đột, xác định dependency nào kéo version không mong muốn và quản lý version ở nơi phù hợp.

### BOM là gì?

Bill of Materials (BOM) là một POM tập trung quản lý version của một nhóm dependency. Consumer có thể import BOM vào dependencyManagement để dùng các version đã được kiểm tra cùng nhau mà không phải ghi version tại từng dependency.

Ví dụ:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>5.11.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

BOM quản lý version nhưng không tự thêm mọi artifact trong BOM vào project. Project vẫn khai báo dependency thực sự cần sử dụng.

## 9. dependencyManagement khác dependencies

Hai phần tử này thường bị nhầm lẫn.

- dependencies khai báo dependency mà project thực sự sử dụng.
- dependencyManagement quản lý version và cấu hình mặc định cho dependency khi project hoặc module khai báo nó.

Ví dụ parent POM:

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

Module con vẫn phải khai báo dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu chỉ có dependencyManagement mà không có dependency tương ứng, Maven không tự thêm thư viện vào classpath.

Điều này đặc biệt hữu ích trong multi-module project: parent quản lý version tập trung, module con chỉ khai báo thư viện mà nó thật sự cần.

## 10. Parent POM và kế thừa cấu hình

Một project có thể khai báo parent POM để kế thừa thông tin và cấu hình chung. Parent có thể cung cấp:

- groupId/version mặc định.
- Properties.
- Dependency management.
- Plugin management.
- Repository hoặc profile theo chính sách.
- Cấu hình build chung.

Ví dụ module con:

~~~xml
<parent>
    <groupId>com.example.platform</groupId>
    <artifactId>platform-parent</artifactId>
    <version>3.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>

<artifactId>orders-service</artifactId>
<packaging>jar</packaging>
~~~

Nếu parent có thể tìm thấy qua relativePath, Maven có thể đọc file parent trong checkout. Nếu không, Maven tìm parent theo tọa độ trong repository phù hợp.

### Kế thừa không phải aggregation

Parent-child inheritance và multi-module aggregation là hai khái niệm khác nhau:

- **Inheritance:** project con kế thừa cấu hình từ parent.
- **Aggregation:** một POM khai báo các module để Maven reactor build chúng trong cùng lần chạy.

Một POM có thể vừa là parent vừa là aggregator, nhưng không bắt buộc. Parent có thể nằm trong repository riêng; aggregator có thể chỉ gom module mà không cung cấp nhiều cấu hình kế thừa.

### relativePath

Maven mặc định có thể tìm parent POM ở đường dẫn tương đối theo quy ước. Có thể đặt relativePath cụ thể hoặc để rỗng nếu muốn Maven chỉ resolve parent theo tọa độ repository. Cần bảo đảm local checkout và repository publication không tạo ra hai parent model khác nhau ngoài dự kiến.

## 11. Multi-module project và Maven reactor

Multi-module project dùng một aggregator POM có packaging là pom, khai báo các module con.

Ví dụ cấu trúc:

~~~text
platform/
├── pom.xml
├── platform-api/
│   └── pom.xml
├── platform-service/
│   └── pom.xml
└── platform-web/
    └── pom.xml
~~~

POM gốc:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.platform</groupId>
    <artifactId>platform-parent</artifactId>
    <version>3.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>platform-api</module>
        <module>platform-service</module>
        <module>platform-web</module>
    </modules>
</project>
~~~

Mỗi module có POM riêng và có thể khai báo parent là platform-parent.

### Reactor làm gì?

Maven reactor:

1. Tìm các project được khai báo trong aggregator.
2. Tạo danh sách project/module cần build.
3. Xem xét quan hệ phụ thuộc giữa module.
4. Sắp xếp thứ tự build hợp lệ.
5. Thực hiện lifecycle được yêu cầu cho các module.
6. Báo kết quả theo module trong reactor summary.

Nếu platform-service phụ thuộc platform-api, reactor biết cần xử lý module API trước module service khi dependency đó thuộc reactor. Không cần publish API vào local repository trước chỉ để service sử dụng nó trong cùng reactor build.

### Chọn module trong reactor

Chỉ định module:

~~~shell
mvn -pl platform-service verify
~~~

Thêm các module mà module được chọn phụ thuộc:

~~~shell
mvn -pl platform-service -am verify
~~~

Chọn các module phụ thuộc vào module được chỉ định:

~~~shell
mvn -pl platform-api -amd verify
~~~

-pl chọn project, -am thêm upstream dependencies trong reactor và -amd thêm downstream dependents. Các tùy chọn này hữu ích khi làm việc với repository lớn.

## 12. Packaging định hình lifecycle mặc định

Phần tử packaging xác định loại artifact project tạo ra và có ảnh hưởng đến plugin goals được gắn vào default lifecycle.

Các giá trị thường gặp:

| Packaging | Mục đích |
|---|---|
| jar | Thư viện hoặc ứng dụng Java đóng gói JAR. |
| war | Web application archive. |
| pom | Parent/aggregator POM hoặc BOM; không tạo JAR ứng dụng thông thường. |
| ear | Enterprise application archive trong môi trường hỗ trợ. |
| maven-plugin | Maven plugin artifact. |

Packaging không chỉ là phần mở rộng file. Nó giúp Maven chọn default lifecycle bindings tương ứng.

Ví dụ, jar packaging gắn các goal mặc định để xử lý resource, compile, test compile, test và tạo JAR. war packaging có những binding riêng để tạo WAR. Các binding cụ thể phụ thuộc Maven version và packaging/plugin mapping.

### Packaging jar

Một project có packaging là jar thường tạo file trong target/ với tên dựa trên artifactId và version:

~~~text
target/hello-app-1.0.0.jar
~~~

### Packaging war

Project web dùng:

~~~xml
<packaging>war</packaging>
~~~

Maven WAR Plugin tạo WAR theo cấu trúc web application. Dependency scope provided thường được dùng cho API do servlet container cung cấp, tùy kiến trúc và phiên bản nền tảng.

### Packaging pom

POM aggregator/parent thường dùng:

~~~xml
<packaging>pom</packaging>
~~~

Nó không tạo JAR ứng dụng. Nó quản lý module, dependency hoặc plugin configuration.

## 13. Maven có ba lifecycle độc lập

Maven định nghĩa ba lifecycle tích hợp sẵn:

1. **default:** build và phân phối project.
2. **clean:** xóa output do build tạo.
3. **site:** tạo và triển khai project site/documentation.

Mỗi lifecycle gồm một chuỗi phase theo thứ tự. Plugin goals được gắn vào phase để thực hiện công việc cụ thể.

### Default lifecycle

Đây là lifecycle thường dùng nhất khi build Java. Các phase chính theo thứ tự:

| Phase | Vai trò khái quát |
|---|---|
| validate | Kiểm tra project có hợp lệ và đủ thông tin cơ bản. |
| initialize | Khởi tạo trạng thái build. |
| generate-sources | Sinh mã nguồn trước compile. |
| process-sources | Xử lý source đã có. |
| generate-resources | Sinh resource. |
| process-resources | Xử lý/copy resource vào output. |
| compile | Biên dịch source production. |
| process-classes | Xử lý output sau compile. |
| generate-test-sources | Sinh test source. |
| process-test-sources | Xử lý test source. |
| generate-test-resources | Sinh test resource. |
| process-test-resources | Xử lý/copy test resource. |
| test-compile | Biên dịch test source. |
| process-test-classes | Xử lý output test sau compile. |
| test | Chạy unit test. |
| prepare-package | Chuẩn bị trước khi đóng gói. |
| package | Tạo artifact chính như JAR/WAR. |
| pre-integration-test | Chuẩn bị môi trường integration test. |
| integration-test | Chạy integration test. |
| post-integration-test | Dọn hoặc kết thúc môi trường integration test. |
| verify | Kiểm tra artifact và kết quả build sau các bước trước. |
| install | Cài artifact vào local repository. |
| deploy | Publish artifact lên remote repository theo cấu hình. |

Các phase là điểm điều phối chuẩn. Không phải mọi project đều có plugin goal gắn vào mọi phase.

### Clean lifecycle

Các phase:

- pre-clean
- clean
- post-clean

Thông thường mvn clean chạy đến phase clean, gọi plugin clean để xóa thư mục output của project, thường là target/.

### Site lifecycle

Các phase:

- pre-site
- site
- post-site
- site-deploy

Lifecycle này phục vụ tạo và triển khai tài liệu/site của project. Nó không phải bước bắt buộc trong mọi lần compile hoặc package.

## 14. Phase và plugin goal khác nhau thế nào?

**Phase** là một điểm trong lifecycle chuẩn. **Goal** là một hành động cụ thể do plugin cung cấp.

Ví dụ:

- Phase compile thuộc default lifecycle.
- Goal compiler:compile thuộc Maven Compiler Plugin.
- Phase test thuộc default lifecycle.
- Goal surefire:test thuộc Maven Surefire Plugin.
- Phase package thuộc default lifecycle.
- Goal jar:jar thuộc Maven JAR Plugin.

Maven liên kết các plugin goals với phase dựa trên packaging mặc định hoặc cấu hình POM. Khi người dùng gọi một phase, Maven thực thi các phase trước đó theo thứ tự và các goals được gắn vào những phase đó.

### Một phase có thể có nhiều goal

Ví dụ phase package có thể thực hiện goal tạo JAR, goal tạo archive bổ sung hoặc goal plugin riêng được project cấu hình. Thứ tự execution trong cùng phase có thể phụ thuộc cấu hình plugin và cách Maven xây dựng execution plan.

### Một goal có thể được gọi trực tiếp

Có thể gọi trực tiếp một plugin goal:

~~~shell
mvn compiler:compile
~~~

Lệnh này gọi goal cụ thể, không đồng nghĩa chạy toàn bộ các phase trước compile. Vì vậy, các bước như validate, generate-sources hoặc process-resources có thể không được thực hiện như khi gọi lifecycle phase compile.

Với thao tác build thông thường, nên gọi lifecycle phase như compile, test, package hoặc verify. Gọi goal trực tiếp hữu ích khi chẩn đoán hoặc chạy một thao tác plugin độc lập.

## 15. Vì sao gọi một phase sẽ chạy các phase trước?

Lifecycle là chuỗi phase có thứ tự. Khi chạy:

~~~shell
mvn package
~~~

Maven thực hiện các phase trong default lifecycle từ đầu đến package, bao gồm những phase như validate, process-resources, compile, test-compile và test. Sau đó, các goal được gắn với package phase được thực hiện.

Tương tự:

- mvn compile chạy các phase trước compile.
- mvn test chạy đến test.
- mvn package chạy đến package.
- mvn verify chạy đến verify.
- mvn install chạy đến install.
- mvn deploy chạy đến deploy.

Điều này giúp một lệnh ngắn biểu diễn một quy trình nhất quán. Người dùng không cần tự liệt kê mọi plugin goal cần chạy theo thứ tự.

### Kết hợp nhiều lifecycle

Lệnh:

~~~shell
mvn clean package
~~~

yêu cầu Maven chạy clean lifecycle đến phase clean, sau đó chạy default lifecycle đến phase package.

Lệnh:

~~~shell
mvn clean verify
~~~

xóa output cũ rồi chạy default lifecycle đến verify. Đây là lệnh thường dùng trong CI khi muốn kiểm tra và đóng gói project từ trạng thái build sạch.

## 16. Default lifecycle bindings cho Java JAR

Với packaging jar, Maven có các default plugin goal bindings. Chi tiết chính xác phụ thuộc Maven version và packaging mapping, nhưng quy trình phổ biến có thể hình dung như sau:

| Phase | Goal mặc định thường gặp | Công việc |
|---|---|---|
| process-resources | resources:resources | Copy resource production. |
| compile | compiler:compile | Biên dịch Java production. |
| process-test-resources | resources:testResources | Copy test resources. |
| test-compile | compiler:testCompile | Biên dịch test source. |
| test | surefire:test | Chạy unit tests. |
| package | jar:jar | Tạo JAR. |
| install | install:install | Cài artifact vào local repository. |
| deploy | deploy:deploy | Upload artifact đến remote repository. |

Bảng này mô tả binding mặc định phổ biến của JAR packaging, không phải danh sách cố định cho mọi Maven version và plugin override. POM có thể thay version, thêm execution hoặc cấu hình plugin.

Điểm quan trọng: khi chạy mvn package, Maven biết cách compile, test và tạo JAR nhờ packaging mapping và plugin goals. Project không cần tự viết script gọi compiler rồi gọi JAR tool.

## 17. Các lệnh Maven thường dùng và ý nghĩa

| Lệnh | Kết quả |
|---|---|
| mvn validate | Chạy đến phase validate. |
| mvn compile | Biên dịch mã nguồn production. |
| mvn test | Biên dịch và chạy unit test. |
| mvn package | Chạy các phase trước đó và tạo artifact. |
| mvn verify | Chạy đến verify, gồm các kiểm tra được gắn vào lifecycle. |
| mvn install | Chạy đến install và đưa artifact vào local repository. |
| mvn deploy | Chạy đến deploy và publish artifact theo cấu hình. |
| mvn clean | Xóa output build. |
| mvn clean verify | Xóa output cũ rồi build/test/verify. |
| mvn -q test | Chạy test với mức output console ít hơn. |
| mvn -X test | Chạy debug log chi tiết; cần cẩn thận với dữ liệu nhạy cảm. |

### package, install và deploy khác nhau

- package tạo artifact trong thư mục output của project, thường là target/.
- install đưa artifact và metadata vào local Maven repository để project khác trên cùng môi trường có thể resolve.
- deploy upload artifact lên remote repository đã khai báo trong distributionManagement.

install không có nghĩa cài ứng dụng vào hệ điều hành. deploy trong Maven lifecycle cũng không phải triển khai ứng dụng lên production server; nó là publish artifact lên repository. Việc deploy ứng dụng là một quy trình vận hành khác.

### Bỏ qua test

Maven có các tùy chọn bỏ qua test execution hoặc cả test compilation. Cần hiểu rõ khác biệt:

- -DskipTests thường bỏ qua việc chạy test nhưng vẫn biên dịch test.
- -Dmaven.test.skip=true có thể bỏ qua cả test compilation và test execution theo plugin hỗ trợ.

Không nên dùng các cờ này để che giấu test failure trong pipeline release. Chỉ dùng khi có lý do rõ và có bước test thay thế phù hợp.

## 18. Plugin: Maven mở rộng hành vi build như thế nào?

Maven core cung cấp model và lifecycle. Plugin cung cấp các thao tác cụ thể như compile, test, package, checkstyle, generate source, create site hoặc deploy.

Một plugin có thể cung cấp nhiều goals. Ví dụ Maven Compiler Plugin có goal compile và testCompile. Maven Surefire Plugin có goal test. Maven JAR Plugin có goal jar.

### Khai báo plugin trong POM

Ví dụ:

~~~xml
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
~~~

Version tường minh giúp project không phụ thuộc vào plugin version ngầm định của môi trường. Plugin configuration áp dụng cho các goal tương ứng theo cách plugin định nghĩa.

### Plugin execution

Có thể gắn một goal vào phase cụ thể bằng execution:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-checkstyle-plugin</artifactId>
    <version>3.6.0</version>
    <executions>
        <execution>
            <id>check-style</id>
            <phase>verify</phase>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Ví dụ này yêu cầu goal check chạy trong verify phase. Vì verify nằm sau package, lệnh mvn verify sẽ đi qua package trước rồi thực hiện kiểm tra đã gắn vào verify.

### Plugin version và reproducibility

Nếu POM không chỉ định plugin version, Maven có thể chọn version theo default lifecycle mapping hoặc metadata/cấu hình hiện hành. Để build ổn định, nên quản lý version plugin quan trọng tường minh, đặc biệt compiler, test, packaging, code generation và publication.

## 19. pluginManagement khác plugins

Hai phần này có vai trò khác nhau:

- build/plugins khai báo plugin được project sử dụng trong build.
- build/pluginManagement định nghĩa version/configuration mặc định để plugin được khai báo ở project con hoặc phần plugins sử dụng.

Ví dụ parent POM:

~~~xml
<build>
    <pluginManagement>
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
    </pluginManagement>
</build>
~~~

Module con có thể khai báo plugin trong plugins để kích hoạt cấu hình được quản lý:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Nếu plugin chỉ nằm trong pluginManagement, không nên mặc định rằng mọi plugin goal đã được thêm vào lifecycle của mọi module. pluginManagement chủ yếu quản lý cấu hình/version; việc kích hoạt còn phụ thuộc plugin được khai báo hoặc default lifecycle binding.

Điều này tương tự dependencyManagement: quản lý cấu hình không đồng nghĩa tự thêm dependency/plugin vào project.

## 20. Surefire và Failsafe trong lifecycle

Maven thường dùng hai plugin khác nhau cho hai nhóm kiểm thử:

- **Surefire:** chạy unit test trong test phase.
- **Failsafe:** chạy integration test trong integration-test và verify phase theo cấu hình.

Surefire thường tìm test theo quy ước tên lớp, chẳng hạn các lớp có tên kết thúc bằng Test, Tests hoặc TestCase theo pattern plugin và version. Có thể cấu hình include/exclude hoặc test framework provider.

Failsafe được thiết kế để chạy integration test và trì hoãn việc báo build failure đến verify, cho phép post-integration-test thực hiện dọn môi trường.

Một luồng khái quát:

~~~text
test
 |
 v
package
 |
 v
pre-integration-test
 |
 v
integration-test  (Failsafe: integration-test)
 |
 v
post-integration-test (cleanup)
 |
 v
verify (Failsafe: verify)
~~~

Nếu chỉ gọi mvn test, integration test được gắn ở integration-test phase thường chưa chạy. Nếu muốn xác minh cả integration test và bước kiểm tra sau package, dùng mvn verify hoặc lifecycle mục tiêu phù hợp.

### Cấu hình Failsafe

Ví dụ cấu hình plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Trong dự án thực tế, có thể cần include/exclude pattern, profile hoặc service setup/cleanup. Đừng chỉ gọi goal integration-test riêng rồi cho rằng toàn bộ lifecycle và cleanup đã được thực hiện.

## 21. Resource và generated source theo convention

Maven resource plugin xử lý resource theo cấu trúc mặc định. Resource production trong src/main/resources được copy vào output classpath; test resource trong src/test/resources được copy vào test output.

Nếu cần lọc resource để thay property, có thể cấu hình resource filtering. Cần cẩn thận với binary file và nội dung có ký tự giống cú pháp Maven property; filtering không phù hợp có thể làm hỏng file.

### Generated source

Code generator thường được gắn vào một phase trước compile, chẳng hạn generate-sources hoặc generate-test-sources. Plugin cần tạo source vào thư mục output và đăng ký thư mục đó để compiler nhận diện.

Không nên phụ thuộc vào source generated còn sót trong target/ từ build cũ. mvn clean xóa target, do đó lifecycle phải có thể tạo lại mọi generated input cần thiết.

### Thư mục output

Maven thường dùng target/ cho output của project. Plugin nên ghi file vào thư mục build của module tương ứng để tránh nhiều module ghi đè cùng một file trong multi-module build.

## 22. Profiles: cùng một POM, cấu hình theo điều kiện

Maven profile cho phép bật nhóm cấu hình theo điều kiện hoặc theo lựa chọn người dùng. Profile có thể thêm dependency, property, repository, plugin hoặc module tùy phạm vi và phần tử được phép.

Ví dụ profile bật integration test:

~~~xml
<profiles>
    <profile>
        <id>integration-tests</id>
        <properties>
            <run.integration.tests>true</run.integration.tests>
        </properties>
    </profile>
</profiles>
~~~

Kích hoạt tường minh:

~~~shell
mvn -Pintegration-tests verify
~~~

Profile cũng có thể được kích hoạt theo JDK, OS, property hoặc file tồn tại. Profile đặt trong POM thường được chia sẻ qua source control; profile trong settings có phạm vi môi trường/người dùng.

### Profile không phải cách che giấu dependency

Nếu một dependency bắt buộc cho mọi build nhưng chỉ được khai báo trong profile chỉ active trên máy lập trình viên, CI có thể thiếu dependency. Hãy chỉ dùng profile khi sự khác biệt thực sự theo môi trường hoặc mục đích build.

### Kiểm tra profile

~~~shell
mvn help:active-profiles
~~~

Khi local và CI khác nhau, kiểm tra profile đang active và các property được truyền qua command line hoặc settings.

## 23. POM, settings.xml và repository configuration

Không phải mọi cấu hình Maven đều thuộc POM.

- **POM:** mô tả project và quy tắc build có thể chia sẻ trong repository.
- **settings.xml:** cấu hình môi trường người dùng hoặc CI, chẳng hạn server credentials, mirrors, proxies và active profiles ở cấp settings.
- **Local repository:** cache artifact tải về và artifact được install trên máy.
- **Remote repository:** nguồn dependency hoặc đích publish.

Ví dụ settings.xml có thể chứa mirror:

~~~xml
<settings>
    <mirrors>
        <mirror>
            <id>company-mirror</id>
            <mirrorOf>*</mirrorOf>
            <url>https://repo.example.com/maven-all</url>
        </mirror>
    </mirrors>
</settings>
~~~

Nếu mirror áp dụng cho mọi repository, Maven chuyển request qua URL mirror. Credential tương ứng thường được cấu hình trong phần servers với id phù hợp.

### Không commit secret vào POM

POM có thể commit repository URL nếu đó là cấu hình chung, nhưng không nên chứa username/password/token. Credentials nên được cung cấp qua settings.xml hoặc secret mechanism của CI.

### Effective settings

Có thể xem cấu hình settings sau khi áp dụng:

~~~shell
mvn help:effective-settings
~~~

Output có thể chứa URL, username hoặc thông tin môi trường. Không nên lưu hoặc chia sẻ output này công khai nếu chưa kiểm tra dữ liệu nhạy cảm.

## 24. Repository đọc và đích deploy

POM có thể khai báo repositories để tải dependency và distributionManagement để xác định nơi publish artifact.

Ví dụ dependency repository:

~~~xml
<repositories>
    <repository>
        <id>company-public</id>
        <url>https://repo.example.com/maven-public</url>
    </repository>
</repositories>
~~~

Ví dụ publication target:

~~~xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.com/maven-releases</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.com/maven-snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

Credential được ánh xạ trong settings.xml qua server id tương ứng. Build/test job thông thường cần quyền đọc. Job gọi deploy mới cần quyền ghi vào repository đích.

mvn deploy trong Maven lifecycle publish artifact lên remote Maven repository. Nó không tự triển khai ứng dụng lên server production hoặc Kubernetes. Deployment application là một bước riêng, có thể tiêu thụ artifact hoặc container image đã publish.

## 25. Maven Wrapper và tính nhất quán môi trường

Maven Wrapper giúp project chỉ định phiên bản Maven. Repository thường chứa:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
~~~

Chạy trên Linux/macOS:

~~~shell
./mvnw --version
./mvnw clean verify
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd clean verify
~~~

Wrapper không tự cố định mọi thứ. Vẫn cần quản lý:

- JDK chạy Maven và compiler toolchain.
- Plugin version.
- Dependency version và repository.
- Profile/property.
- External tool và service.
- Credentials và proxy.
- OS/architecture nếu có native dependency.

Trong CI, dùng wrapper đã commit và ghi nhận java -version cùng mvnw --version để dễ truy vết.

## 26. Chẩn đoán cấu hình và lifecycle

Khi Maven chạy khác kỳ vọng, hãy xác định model thực tế và phase/goal đã được thực thi.

Một số lệnh hữu ích:

~~~shell
mvn help:effective-pom
mvn help:active-profiles
mvn dependency:tree
mvn -X test
~~~

-X tạo debug log rất chi tiết; cần cẩn thận để không lưu credential hoặc thông tin nội bộ vào log chia sẻ.

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Maven không tìm thấy dependency | Tọa độ/version sai hoặc repository không có artifact | POM, dependency tree, repository URL |
| Build local được nhưng CI thiếu dependency | Local cache hoặc profile riêng che giấu lỗi | Cold repository, active profiles, settings |
| Java source dùng API mới nhưng compiler báo lỗi | Compiler release/JDK không khớp | JDK thực tế, compiler plugin, toolchain |
| Unit test không chạy | Test naming, Surefire version/provider, include/exclude | Surefire configuration và report |
| Integration test không chạy | Chỉ gọi test phase thay vì integration-test/verify | Lifecycle command và Failsafe execution |
| Plugin không tải được | Plugin repository/mirror/credentials | pluginRepositories, settings mirrors, server id |
| Parent POM không resolve | Parent tọa độ hoặc relativePath sai | Parent declaration và repository |
| Module build sai thứ tự | Thiếu dependency giữa module hoặc không build từ aggregator | Reactor graph, module POM |
| Deploy bị 401/403 | Server id hoặc credential/permission sai | distributionManagement và settings servers |
| Artifact không xuất hiện ở remote repo | Chưa chạy deploy hoặc deploy target sai | Lifecycle phase, distributionManagement |
| clean xóa file cần thiết | File được đặt trong target nhưng không có task tạo lại | Generated input và plugin binding |
| POM có cấu hình nhưng không có hiệu lực | Chỉ nằm trong dependencyManagement/pluginManagement hoặc profile không active | Effective POM và active profiles |

### Trình tự điều tra

1. Xác nhận Maven version và JDK.
2. Xác nhận project root/POM được dùng.
3. Xem effective POM và active profiles.
4. Xác định command đang gọi phase hay goal trực tiếp.
5. Xem dependency tree hoặc plugin execution.
6. Kiểm tra repository/mirror và credentials.
7. Kiểm tra output trong target và báo cáo tương ứng.
8. Xác nhận reactor module list nếu là multi-module project.

Đọc lỗi đầu tiên có nguyên nhân rõ thay vì chỉ nhìn dòng BUILD FAILURE cuối cùng.

## 27. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| POM chỉ là file liệt kê thư viện | POM là mô hình project, gồm tọa độ, packaging, dependency, plugin, module, profile và metadata. |
| modelVersion là version ứng dụng | modelVersion xác định phiên bản cấu trúc POM. |
| dependencyManagement tự thêm dependency | Nó quản lý version/configuration; project vẫn cần khai báo dependency trong dependencies. |
| pluginManagement tự chạy mọi plugin | Nó quản lý plugin version/configuration; không nhất thiết kích hoạt plugin goal. |
| Parent POM và aggregator là một khái niệm | Parent dùng để kế thừa; aggregator gom module vào reactor. |
| mvn package chỉ chạy goal package | Nó chạy các phase trước package rồi thực hiện các goal được bind. |
| Phase và goal là một | Phase thuộc lifecycle; goal là hành động do plugin cung cấp. |
| mvn test luôn chạy integration test | Integration test thường gắn vào integration-test/verify qua Failsafe. |
| mvn install cài ứng dụng lên máy | Nó cài artifact vào local Maven repository. |
| mvn deploy triển khai app lên production | Nó publish artifact lên remote Maven repository. |
| clean xóa dependency cache | clean thường xóa output project như target, không xóa local repository. |
| Mọi project phải khai báo tất cả thư mục source | Maven có convention mặc định cho source, resource và output. |
| Chỉ cần POM là đủ cho mọi môi trường | JDK, settings, credentials, repository và external tools vẫn cần được cung cấp. |

## 28. Bài thực hành

Thực hành với một project Java mới:

1. Tạo một POM tối thiểu có groupId, artifactId, version và packaging jar.
2. Tạo source trong src/main/java và resource trong src/main/resources.
3. Tạo test trong src/test/java và test resource nếu cần.
4. Chạy mvn validate, mvn compile và mvn test; quan sát các thư mục output.
5. Thêm JUnit dependency với scope test và xác nhận dependency không nằm trong runtime dependency của ứng dụng.
6. Thêm Maven Compiler Plugin với version cụ thể và release mục tiêu.
7. Chạy mvn package và kiểm tra JAR trong target/.
8. Chạy mvn install rồi xác nhận artifact xuất hiện trong local Maven repository.
9. Tạo một parent POM có dependencyManagement và pluginManagement, sau đó tạo hai module con.
10. Khai báo module dependency và chạy build từ aggregator để quan sát reactor order.
11. Thêm một profile integration-tests và kiểm tra active profile.
12. Cấu hình Failsafe cho một integration test đơn giản, chạy mvn test rồi mvn verify để thấy khác biệt lifecycle.
13. Xem effective POM, active profiles và dependency tree.
14. Thêm distributionManagement trong project thử nghiệm và chỉ publish khi có repository sandbox cùng credential phù hợp.

Sau bài thực hành, bạn cần giải thích được Maven dùng POM để tạo project model thế nào, vì sao convention giảm cấu hình, dependencyManagement khác dependencies ra sao, parent khác aggregator thế nào và lifecycle phase khác plugin goal ra sao.

## 29. Tiêu chí hoàn tất một Maven project có thể build theo quy ước

Một project Maven có thể xem là được cấu hình rõ khi:

1. POM xác định tọa độ và packaging phù hợp.
2. Source/resource/test tuân theo convention hoặc đường dẫn tùy chỉnh được khai báo.
3. Dependency trực tiếp có version/scope được quản lý.
4. Dependency bắc cầu và BOM được kiểm soát khi cần.
5. Parent/module relationship rõ ràng.
6. Plugin quan trọng có version và configuration phù hợp.
7. Lệnh lifecycle chuẩn tạo đúng artifact và chạy đúng test.
8. Profile đang active được xác định và không phụ thuộc ngầm vào máy cá nhân.
9. Repository, settings và credentials được phân tách an toàn.
10. Effective POM, dependency tree và output có thể được dùng để truy vết khi có lỗi.

Maven hoạt động hiệu quả khi project mô tả đúng model và tuân theo lifecycle chuẩn. POM xác định project cần gì và được cấu hình ra sao; convention xác định vị trí và cách tổ chức mặc định; lifecycle điều phối các plugin goals theo thứ tự. Khi hiểu ba phần này, bạn có thể đọc một project Maven, dự đoán một lệnh build sẽ làm gì và mở rộng cấu hình mà không phải viết lại toàn bộ quy trình.

