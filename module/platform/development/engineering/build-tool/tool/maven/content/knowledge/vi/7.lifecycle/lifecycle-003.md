# Chuỗi validate, initialize và chuẩn bị đầu vào trong Maven

## 1. Vì sao build Maven phải đi qua các pha đầu?

Maven tổ chức việc xây dựng một dự án bằng **lifecycle (vòng đời)**, **phase (giai đoạn)** và **plugin goal (công việc thực thi)**. Khi yêu cầu `mvn package`, Maven không nhảy thẳng tới đóng gói JAR. Trong **default lifecycle**, nó đi lần lượt qua các pha trước đó, bao gồm `validate`, `initialize` và các pha chuẩn bị nguồn/tài nguyên.

Trật tự cần nắm:

~~~text
validate
  -> initialize
  -> generate-sources
  -> process-sources
  -> generate-resources
  -> process-resources
  -> compile
  -> ... -> test -> package -> verify -> install -> deploy
~~~

**validate** hướng tới xác nhận tính hợp lệ và điều kiện của project. **initialize** là chỗ khởi tạo trạng thái build cần cho bước sau. Các pha **generate/process** chuẩn bị đầu vào mà compiler hoặc trình đóng gói cần sử dụng. **compile** mới biên dịch mã nguồn sản phẩm.

**Điều quan trọng nhất:** phase xác định **thứ tự**, còn **plugin goal** thực hiện công việc. Một phase có thể không thực thi goal nào nếu dự án chưa gắn plugin vào đó. Vì vậy, không được mặc định rằng cứ chạy `mvn initialize` thì Maven tự tạo tất cả thư mục, tải mọi tài nguyên, sinh code hoặc kiểm tra hết các yêu cầu của dự án.

## 2. Phân biệt công việc trước lifecycle và công việc ở validate

Trước khi thực thi goals của default lifecycle, Maven cần khởi động và xác định project:

1. Nếu chạy bằng **Maven Wrapper** (`./mvnw` hoặc `mvnw.cmd`), Wrapper chuẩn bị Maven distribution thích hợp trước khi Maven xử lý project.
2. Maven đọc **pom.xml**, xử lý parent POM, Super POM, active profiles và thông tin cấu hình cần thiết, rồi lập kế hoạch các project trong reactor và các goals phải thực thi.
3. Maven bắt đầu các phase của lifecycle được yêu cầu, bắt đầu bằng **validate** đối với default lifecycle.

Hệ quả:

- XML POM sai định dạng hoặc parent POM không thể phân giải có thể khiến Maven thất bại **trước khi goal gắn ở validate chạy**.
- Mạng có thể đã được truy cập để tải Maven Wrapper, parent POM hoặc plugin; `mvn validate` không bảo đảm chạy hoàn toàn offline.
- `mvn -version` chủ yếu kiểm tra Maven/JDK đang chạy. Nó không phải một lần chạy default lifecycle và không chạy các executions của project ở validate/initialize.
- `clean` thuộc **clean lifecycle** riêng. `mvn clean package` yêu cầu thực thi clean rồi mới thực thi default lifecycle tới package, không phải `clean` là pha nằm giữa validate và initialize.

## 3. Cấu trúc của vòng đời: phase khác plugin goal

| Thuật ngữ | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Lifecycle** | **default**, **clean**, **site** | Chuỗi phase có thứ tự phục vụ một mục tiêu tổng thể |
| **Phase** | **validate**, **initialize**, **compile** | Mốc trong lifecycle; Maven đi qua theo thứ tự |
| **Plugin** | **maven-enforcer-plugin**, **maven-compiler-plugin** | Thành phần cung cấp các công việc cụ thể |
| **Goal** | **enforcer:enforce**, **compiler:compile** | Đơn vị thực thi thực tế của plugin |
| **Execution** | **<execution><phase>validate</phase>...</execution>** | Quy tắc gắn một hoặc nhiều goals vào phase |
| **Default binding** | **resources:resources** ở **process-resources** khi **packaging=jar** | Maven tự liên kết một số goals do kiểu đóng gói |

Ví dụ `mvn validate` yêu cầu Maven chạy default lifecycle **tới phase validate**; `mvn enforcer:enforce` gọi **goal của plugin trực tiếp**, không đồng nghĩa chạy cả lifecycle đến validate. Muốn kiểm tra plugin nào chạy trong giai đoạn nào, cần xem **build/plugins/executions**, default bindings, parent POM và **effective POM**, không chỉ nhìn vào tên lệnh.

Với dự án Maven **packaging=jar** thông thường, default bindings chủ yếu bắt đầu có việc ở **process-resources**, **compile**, rồi các pha test/đóng gói. **validate** và **initialize** có thể đi qua mà không có goal nào do Maven mặc định gắn sẵn.

## 4. validate: kiểm tra điều kiện, thất bại sớm khi cần

Apache Maven mô tả **validate** là kiểm tra dự án có hợp lệ và các thông tin cần thiết sẵn sàng hay không. Trên thực tế, nhiều nhóm gắn Maven Enforcer Plugin hoặc những checker khác vào đây để kiểm tra:

- Phiên bản Maven đáp ứng yêu cầu của dự án.
- Phiên bản JDK phù hợp.
- Dependency, repository hoặc rule được tổ chức cho phép.
- Property, cấu hình bắt buộc và một số điều kiện của môi trường build.
- Những ràng buộc có thể xác nhận trước khi compile và test.

**Đây không phải các kiểm tra tự động có đầy đủ trong mọi POM.** Một điều kiện chỉ thực sự được kiểm tra nếu có goal/rule thích hợp được kích hoạt và không bị skip.

Ví dụ plugin configuration (đặt trong **<build><plugins>** của một POM):

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>check-build-environment</id>
            <phase>validate</phase>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireMavenVersion>
                        <version>[3.9,)</version>
                    </requireMavenVersion>
                    <requireJavaVersion>
                        <version>[17,)</version>
                    </requireJavaVersion>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Hai rule trên yêu cầu Maven từ **3.9** và Java/JDK từ **17**. Nếu điều kiện không đạt, Enforcer thất bại ở đầu build và các goal phía sau không được thực thi. Nếu điều kiện đạt, việc vượt qua validate **chưa** chứng minh code biên dịch, test pass hay artifact chạy được; các công việc đó diễn ra sau.

Một lỗi do Maven từ chối cấu hình POM ngay khi dựng project model khác với lỗi của **enforcer:enforce**. Khi gỡ lỗi phải phân biệt thông báo nào xuất hiện đầu tiên.

## 5. initialize: khởi tạo trạng thái phục vụ các bước tiếp theo

**initialize** nằm ngay sau **validate**, trước **generate-sources**. Những công việc có thể được gắn ở initialize:

- Tạo thư mục để plugin generator sử dụng sau đó.
- Chuẩn bị file dữ liệu đầu vào hoặc metadata nhất quán cho build.
- Tạo điều kiện ban đầu mà plugin phía sau cần.
- Thiết lập trạng thái/các thông số được plugin hỗ trợ đọc ở thời điểm thực thi.

Nếu dự án không cấu hình goal nào tại initialize, phase này không tự sinh ra thư mục hoặc file tùy ý.

Mảnh cấu hình dùng **maven-antrun-plugin** để tạo file dưới thư mục build:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <executions>
        <execution>
            <id>prepare-bootstrap-file</id>
            <phase>initialize</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <mkdir dir="${project.build.directory}/generated-resources/bootstrap"/>
                    <echo file="${project.build.directory}/generated-resources/bootstrap/bootstrap.txt"
                          message="READY"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Sau `mvn initialize` thành công, file này nằm ở **target/generated-resources/bootstrap/bootstrap.txt** nếu cấu hình output directory là mặc định. Trong file có **READY**. Các lệnh Ant trong ví dụ cho thấy khả năng khởi tạo cụ thể; với dự án lớn, ưu tiên plugin chuyên dụng thay vì nhét quá nhiều scripting vào POM.

File dưới **target/** là **đầu ra do build sinh**, có thể bị `mvn clean` xóa và phải tái tạo được. Không nên ghi đè file do người viết quản lý ở **src/** chỉ để thực hiện phase initialize.

## 6. Bảng so sánh validate và initialize

| Tiêu chí | validate | initialize |
| --- | --- | --- |
| Thứ tự | Pha đầu default lifecycle | Sau validate |
| Trọng tâm | Kiểm tra mô hình/ràng buộc project và môi trường | Khởi tạo dữ liệu/trạng thái cho các phase sau |
| Goal minh họa | **enforcer:enforce** | **antrun:run** |
| Nếu không có goal được gắn | Có thể không thực thi hành động cụ thể | Tương tự |
| Đã biên dịch Java? | Chưa | Chưa |
| Đã đóng gói JAR? | Chưa | Chưa |
| Có thể truy cập mạng? | Có thể, khi cần phân giải POM/plugin | Có thể, tùy goal |
| Có thể làm build thất bại? | Có, nếu model/goal/rule lỗi | Có, nếu goal chuẩn bị lỗi |
| `mvn initialize` có đi qua validate trước? | Có | Có |

Cách đọc đơn giản: **validate quyết định “có đủ điều kiện để tiếp tục không?”**, **initialize chuẩn bị “trạng thái ban đầu để tiếp tục”**. Đây là mục đích được kỳ vọng; tác dụng quan sát được vẫn phụ thuộc vào plugin goals của từng POM.

## 7. Chuỗi chuẩn bị đầu vào trước compile

Các phase sau initialize cho phép tách việc tạo file ra khỏi việc đưa file vào classpath/biên dịch:

| Phase | Mục đích | Ví dụ |
| --- | --- | --- |
| **generate-sources** | Sinh mã nguồn cho compiler | Sinh Java từ schema/protobuf/OpenAPI |
| **process-sources** | Xử lý source trước compile | Xử lý nguồn theo quy tắc dự án |
| **generate-resources** | Sinh hoặc đăng ký resource roots | Sinh metadata hoặc đăng ký thư mục resource đã tạo |
| **process-resources** | Sao chép/lọc resources sang output | Maven Resources Plugin đưa file vào **target/classes/** |
| **compile** | Biên dịch mã Java chính | Maven Compiler Plugin tạo **.class** |

**Nguồn khác đầu ra**:

~~~text
src/main/java/*.java
     |
     | compile
     v
target/classes/*.class

src/main/resources/*
     |
     | process-resources
     v
target/classes/*

target/generated-resources/bootstrap/bootstrap.txt
     |
     | phải đăng ký resource root trước
     | process-resources
     v
target/classes/bootstrap.txt
~~~

Đối với `jar`, các goals **resources:resources** và **compiler:compile** có default binding đến các pha tương ứng. Nhưng **generate-sources** hoặc **generate-resources** có thể không có hành động nếu chưa khai báo generator.

**Có file sinh ra trên đĩa không đồng nghĩa compiler/resources plugin biết đến file ấy.** Nếu generator tạo Java dưới **target/generated-sources/**, nó thường phải đăng ký compile source root. Nếu generator tạo resource dưới thư mục ngoài **src/main/resources/**, cần đăng ký resource root hoặc cấu hình resources plugin để thư mục đó được xử lý.

## 8. Ví dụ đầy đủ với Maven 3.9+ và Java 17

Ví dụ sau minh họa tuần tự ba lớp công việc và cho kết quả chạy Java cụ thể:

1. **validate**: Enforcer kiểm tra Maven/JDK.
2. **initialize**: AntRun tạo **bootstrap.txt**.
3. **generate-resources**: Build Helper đăng ký thư mục chứa file đó thành một resource root.
4. **process-resources**: Maven Resources Plugin sao chép file vào **target/classes**.
5. **compile**: Compiler Plugin biên dịch **App.java**.
6. **package**: JAR Plugin đóng gói class và resource.

### 8.1. Cấu trúc dự án trước khi build

~~~text
lifecycle-initialization/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/lifecycle/
                └── App.java
~~~

**Không cần tạo thủ công target/** hoặc **bootstrap.txt**. Plugin ở initialize sẽ tạo những file build-owned này.

### 8.2. POM hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>lifecycle-initialization</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.5.0</version>
                <executions>
                    <execution>
                        <id>check-environment</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9,)</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>prepare-bootstrap-file</id>
                        <phase>initialize</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}/generated-resources/bootstrap"/>
                                <echo file="${project.build.directory}/generated-resources/bootstrap/bootstrap.txt"
                                      message="READY"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>build-helper-maven-plugin</artifactId>
                <version>3.6.0</version>
                <executions>
                    <execution>
                        <id>register-bootstrap-resource</id>
                        <phase>generate-resources</phase>
                        <goals>
                            <goal>add-resource</goal>
                        </goals>
                        <configuration>
                            <resources>
                                <resource>
                                    <directory>${project.build.directory}/generated-resources/bootstrap</directory>
                                    <filtering>false</filtering>
                                </resource>
                            </resources>
                        </configuration>
                    </execution>
                </executions>
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
    </build>
</project>
~~~

**Đọc POM theo các pha:**

- Enforcer **enforce** được gắn vào **validate** với hai rule kiểm tra môi trường.
- AntRun **run** được gắn vào **initialize**; nó sinh file text **READY** dưới **target/**.
- Build Helper **add-resource** ở **generate-resources** thêm thư mục vừa tạo vào các resource roots của Maven.
- Resources Plugin ở **process-resources** đưa resource đến **target/classes/**.
- Compiler Plugin ở **compile** biên dịch Java 17.
- JAR Plugin ở **package** đưa file trong **target/classes/** vào JAR chính.

Các phiên bản plugin được pin để tránh phụ thuộc tùy tiện vào mặc định của một Maven installation. Nếu parent POM thực tế quản lý plugin versions, hãy điều chỉnh phù hợp với chính sách của project.

### 8.3. Mã Java chạy được

Tạo **src/main/java/com/example/lifecycle/App.java**:

~~~java
package com.example.lifecycle;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        try (InputStream input =
                App.class.getResourceAsStream("/bootstrap.txt")) {
            if (input == null) {
                throw new IOException("Missing bootstrap.txt");
            }

            String value = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            ).trim();
            System.out.println("Prepared: " + value);
        }
    }
}
~~~

Class dùng **getResourceAsStream("/bootstrap.txt")** để đọc resource từ classpath root. Java 17 hỗ trợ các API được dùng. **App** độc lập với Maven khi đã có file class/resource trên classpath.

### 8.4. Quan sát từng mốc

Từ thư mục chứa **pom.xml**:

~~~bash
mvn -version
mvn clean validate
~~~

Ở lượt này, **clean** dọn đầu ra cũ và Enforcer kiểm tra môi trường. **initialize chưa chạy**, nên chưa kỳ vọng file **bootstrap.txt** được tạo bởi AntRun.

Tiếp theo:

~~~bash
mvn initialize
~~~

**validate** tiếp tục được đi qua, sau đó AntRun tạo:

~~~text
target/generated-resources/bootstrap/bootstrap.txt
~~~

Nội dung file là:

~~~text
READY
~~~

Ở giai đoạn này **chưa đến process-resources**, nên không được mặc định file đã có ở **target/classes**.

Tiếp theo:

~~~bash
mvn generate-resources
~~~

Maven đi qua validate, initialize rồi đến generate-resources. Build Helper đăng ký resource root chứa **bootstrap.txt**. Việc **đăng ký** thư mục không phải là hành động copy file sang output.

Tiếp theo:

~~~bash
mvn process-resources
~~~

Maven Resources Plugin nhận resource root và sao chép file sang:

~~~text
target/classes/bootstrap.txt
~~~

Lệnh **process-resources** chưa yêu cầu biên dịch Java. Để biên dịch và chạy class:

~~~bash
mvn compile
java -cp target/classes com.example.lifecycle.App
~~~

Stdout của lệnh Java:

~~~text
Prepared: READY
~~~

Bây giờ có **target/classes/com/example/lifecycle/App.class** và **target/classes/bootstrap.txt**. Khi đóng gói:

~~~bash
mvn clean package
jar tf target/lifecycle-initialization-1.0.0.jar
java -cp target/lifecycle-initialization-1.0.0.jar com.example.lifecycle.App
~~~

JAR chính phải chứa class **App.class** và file **bootstrap.txt**. Lệnh Java cuối in:

~~~text
Prepared: READY
~~~

POM này chưa cấu hình **Main-Class** trong manifest nên **java -jar** không phải lệnh chạy được bảo đảm. Chạy bằng **java -cp** và tên class đầy đủ như ví dụ là đủ vì không có dependency ngoài.

**Lưu ý:** mỗi lệnh Maven trên là một **invocation mới**, các pha trước lại được thực thi. Trong pipeline bình thường, không cần lần lượt gọi từng lệnh để “tiếp tục” từ pha trước; một lệnh **mvn clean package** đã đi qua những pha cần thiết.

## 9. Vì sao sinh file trong initialize chưa có nghĩa đã chuẩn bị đủ đầu vào?

Ví dụ dùng ba hành động độc lập:

~~~text
initialize:
    producer -> target/generated-resources/bootstrap/bootstrap.txt

generate-resources:
    register -> khai báo thư mục đó là resource root

process-resources:
    consumer -> target/classes/bootstrap.txt

compile:
    App.java -> target/classes/com/example/lifecycle/App.class

package:
    đóng gói target/classes vào JAR
~~~

Nếu bỏ **build-helper:add-resource**, file dưới **target/generated-resources** vẫn có thể tồn tại nhưng Maven Resources Plugin không tự suy ra mọi thư mục generated đều phải đưa vào classpath. Nếu không chạy đến **process-resources**, bước copy chưa được yêu cầu. Nếu không chạy đến **compile**, class **App** chưa được tạo bởi vòng build mới.

Cùng nguyên lý áp dụng với generated Java source:

- Generator tạo **.java** trước compile, thường ở **target/generated-sources/**.
- Source root sinh ra phải được đăng ký đúng cách (nhiều generator plugins làm việc này; nếu không có thể dùng helper phù hợp).
- Compiler chỉ biên dịch những source directories nó được cấu hình nhận.

Mốc quan trọng là **file producer đã sinh dữ liệu và consumer đã biết nơi đọc dữ liệu**, không chỉ là tên thư mục bắt đầu bằng “generated”.

## 10. Khi nào gắn công việc vào phase nào?

| Nhiệm vụ | Phase thường phù hợp | Giải thích |
| --- | --- | --- |
| Kiểm tra Maven/JDK versions, một số build policies | **validate** | Fail sớm trước các công việc build nặng |
| Tạo workspace con, trạng thái build hoặc metadata nền | **initialize** | Chuẩn bị điều kiện sử dụng cho các phase sau |
| Sinh mã Java từ schema | **generate-sources** | Đảm bảo code sẵn trước compile |
| Tiền xử lý source theo tool phù hợp | **process-sources** | Chạy sau generate-sources |
| Sinh resource hoặc đăng ký resource roots | **generate-resources** | Chuẩn bị đầu vào của resource processor |
| Sao chép/lọc resource vào output | **process-resources** | File sẵn trong target/classes trước đóng gói |
| Biên dịch Java | **compile** | Tạo class sản phẩm |
| Sinh fixture test | **generate-test-resources** | Tách dữ liệu test khỏi resource production |
| Copy fixture test | **process-test-resources** | Chuẩn bị target/test-classes |

Dự án Maven sử dụng **packaging=jar** có binding mặc định với Compiler/Resources; không nên hiểu các phase **generate-*** đều có generator gắn sẵn.

Cấu hình Maven chịu ảnh hưởng bởi **parent POM**, **pluginManagement**, **active profiles** và properties. Một plugin chỉ được đặt ở **pluginManagement** thường chỉ cung cấp version/configuration cho plugin khi plugin thực sự được dùng; nó không tự gắn một goal tùy ý vào lifecycle.

## 11. Đừng nhầm với phases dành cho test và đóng gói

Sau **compile**, default lifecycle tiếp tục qua những pha quan trọng khác:

~~~text
... compile
 -> process-classes
 -> generate-test-sources
 -> process-test-sources
 -> generate-test-resources
 -> process-test-resources
 -> test-compile
 -> process-test-classes
 -> test
 -> prepare-package
 -> package
 -> verify
 -> install
 -> deploy
~~~

**process-test-resources** khác **process-resources**: nó chuẩn bị tài nguyên kiểm thử trong **target/test-classes**, không mặc định đưa chúng vào JAR sản phẩm. **test-compile** biên dịch test classes. **test** thường chạy qua Surefire; **package** đóng gói artifact.

Đừng đưa test fixtures, mật khẩu thử nghiệm hoặc các source test vào resource root của sản phẩm ở **initialize/generate-resources** chỉ vì chúng cần thiết cho test. Dùng đúng các pha/resource roots của test để giữ ranh giới runtime.

## 12. Trình tự thực thi thực tế và reactor đa module

Giả sử nhiều goals thuộc cùng một phase. Maven có quy tắc để sắp xếp execution, phụ thuộc vào lifecycle bindings, vị trí khai báo và project model hiệu lực. Khi có parent inheritance hoặc nhiều plugin tương tác, không nên dựa vào thứ tự ngầm giữa hai goals cùng phase nếu chúng có quan hệ producer/consumer. Cách dễ kiểm chứng hơn là đặt các bước ở **phase có thứ tự rõ ràng** và quan sát log.

Với **multi-module build**, Maven reactor quyết định trình tự module theo những quan hệ phù hợp. Không được suy ra rằng `mvn package` sẽ chạy **validate của tất cả module trước**, sau đó mới đến **initialize của tất cả module**. Reactor lập kế hoạch thực thi theo module; chạy song song với `-T` còn làm log giữa các module đan xen. Nếu một module cần đầu ra của module khác, phải biểu diễn dependency thực sự trong POM/chu trình build.

**Plugin gắn vào initialize của một module** không có nghĩa mọi module khác sẽ có sẵn file đó ở cùng thời điểm. Phải xác định ownership và nơi tiêu thụ dữ liệu.

## 13. Profiles, properties và đầu vào cấu hình

Một số bước chuẩn bị chỉ chạy khi profile active. Ví dụ project có thể có profile phục vụ integration environment hoặc chính sách CI.

Các nguồn dữ liệu cần phân biệt:

- **pom.xml** và parent POM cung cấp project/plugin configuration.
- **-Dkey=value** cung cấp user properties cho lần gọi Maven.
- **profiles** có thể thay đổi phần model và executions đang active.
- **settings.xml** thường ảnh hưởng kho artifact, mirror, proxy và thông tin xác thực.
- Biến môi trường có thể được plugin cụ thể đọc nếu plugin hỗ trợ.

Ví dụ:

~~~bash
mvn -Dbuild.mode=ci validate
~~~

Lệnh trên chỉ tạo property **build.mode**; Maven không tự hiểu chuỗi **ci** rồi đổi quy trình, trừ khi cấu hình project/plugin thực sự sử dụng property ấy.

Cẩn thận với việc đặt một property ở **initialize** rồi kỳ vọng nó thay đổi hồi tố toàn bộ **effective POM** vốn đã được xây dựng trước lifecycle. Một số plugins đọc properties khi goal chạy; những nơi khác nội suy cấu hình sớm hơn. Nếu cần trạng thái runtime, hãy dùng cơ chế được plugin hỗ trợ và kiểm tra ở consumer; ví dụ sinh file trong bài này tránh phụ thuộc các mốc nội suy property phức tạp.

Dùng Help Plugin để kiểm tra:

~~~bash
mvn help:effective-pom
mvn help:active-profiles
~~~

Help Plugin có thể phải tải từ repository; hai lệnh không tự chứng minh mọi goal ở validate/initialize đã chạy vì chúng là các plugin goals riêng.

## 14. Phân biệt lỗi ở validate, initialize và chuẩn bị resources

| Triệu chứng | Khả năng cao | Cách xác định |
| --- | --- | --- |
| **Malformed POM**, **Non-resolvable parent POM** | Lỗi đọc/xây project model trước khi chạy goal của validate | Xem XML, parent coordinates, relativePath, repo |
| **Enforcer rule failed** | Goal ở validate đang từ chối môi trường/cấu hình | Đọc rule, Maven/JDK versions và effective POM |
| `mvn validate` thành công nhưng `mvn compile` lỗi | Validate chưa kiểm tra code Java | Xem compiler error/source/dependency |
| `mvn initialize` không tạo file | Execution chưa bind hoặc profile chưa active, task không chạy/skip | Xem **build/plugins/executions** và log |
| File sinh dưới **target/generated-resources** nhưng không có trong JAR | Thiếu resource root hoặc bước copy | Kiểm tra Build Helper, **target/classes**, JAR |
| `mvn process-resources` thấy file nhưng `mvn compile` lỗi | Resource processing đã chạy; compiler có lỗi độc lập | Kiểm tra source Java, JDK, compiler release |
| `mvn clean` làm mất file chuẩn bị | Clean xóa build output | Chạy lại lifecycle tới phase cần thiết |
| `mvn validate` cần mạng | Cần resolve plugin/POM/dependency metadata | Xem repo, plugin cache và settings |
| `mvn initialize` chạy hai lần khi gọi hai lệnh riêng | Mỗi lệnh Maven bắt đầu lifecycle từ đầu | Gộp bằng `mvn clean package` khi phù hợp |
| **BUILD SUCCESS** nhưng chưa có JAR | Chỉ chạy validate/initialize/compile | Gọi package và kiểm tra artifact thực tế |
| Plugin ở pluginManagement mà không chạy | Management không tự kích hoạt goal | Xem plugin binding, executions, effective POM |
| CI và máy local ra đầu ra khác nhau | Profile/env/inputs/cache không đồng nhất | Chạy clean build, in versions và active profiles |

Trong log Maven, dòng goal thường có dạng:

~~~text
--- maven-enforcer-plugin:3.5.0:enforce (check-environment) @ lifecycle-initialization ---
--- maven-antrun-plugin:3.1.0:run (prepare-bootstrap-file) @ lifecycle-initialization ---
--- build-helper-maven-plugin:3.6.0:add-resource (register-bootstrap-resource) @ lifecycle-initialization ---
--- maven-resources-plugin:3.3.1:resources (default-resources) @ lifecycle-initialization ---
--- maven-compiler-plugin:3.13.0:compile (default-compile) @ lifecycle-initialization ---
~~~

Các dòng trên minh họa hình thức log, **không phải stdout chính xác hoặc bắt buộc của một invocation**. Những dòng thuộc phase sau không xuất hiện khi lệnh dừng ở phase trước.

Có thể dùng:

~~~bash
mvn -X validate
mvn -X initialize
mvn -X process-resources
~~~

Log **-X** có thể nhiều và có thông tin môi trường; lọc dữ liệu nhạy cảm trước khi chia sẻ.

## 15. Làm giai đoạn chuẩn bị ổn định và có thể tái tạo

**Phân biệt dữ liệu nguồn với đầu ra:** source và POM do con người quản lý trong Git; file sinh dưới **target/** do build tạo và có thể bị xóa. Không phụ thuộc vào một file tạo thủ công còn sót từ build cũ trên laptop.

**Idempotence:** chạy lại validate/initialize nên cho kết quả ổn định. Ví dụ AntRun dùng echo ghi **READY** vào một file cụ thể, không append thêm một dòng mới mỗi lần; sau `mvn clean package` cùng đầu vào, nội dung được tái tạo.

**Không có side effect gây bất ngờ:** tránh tự động xóa database, deploy lên môi trường ngoài hoặc gọi API có tác động lâu dài từ `validate`/`initialize`. Những tác vụ đó cần goal/lệnh có ý nghĩa và quyền thực thi rõ ràng.

**Chọn thời điểm thích hợp:** việc kiểm tra điều kiện nên được đặt sớm; việc sinh code/resource phải hoàn tất trước consumer; kiểm thử và packaging thuộc các phase phía sau. Không dồn toàn bộ tác vụ vào initialize chỉ vì nó được gọi trước compile.

**Khả năng lặp lại trên CI:** pin phiên bản Maven/JDK và plugin phù hợp; chuẩn bị mirror/cache khi môi trường không có Internet; dùng secret manager cho token; ghi nhận input và output. Test bằng một runner sạch để phát hiện dependency vào file cũ ngoài source control.

## 16. Bài tập tự kiểm tra

Giả sử POM hợp lệ có hai executions:

~~~xml
<execution>
    <id>check-environment</id>
    <phase>validate</phase>
    <goals><goal>enforce</goal></goals>
</execution>
~~~

~~~xml
<execution>
    <id>prepare-bootstrap-file</id>
    <phase>initialize</phase>
    <goals><goal>run</goal></goals>
</execution>
~~~

Các execution nằm trong plugins phù hợp và có đầy đủ cấu hình.

**Câu 1:** `mvn validate` có chạy `prepare-bootstrap-file` không? **Không.** Nó chưa tới phase initialize.

**Câu 2:** `mvn initialize` có đi qua validate trước không? **Có.** Nếu goal validate thất bại, initialize không được tiếp tục.

**Câu 3:** Nếu file được tạo ở initialize, nó đã nằm trong JAR chưa? **Chưa chắc.** Cần đăng ký input root, copy/process resources và thực thi package.

**Câu 4:** Nếu `mvn validate` pass nhưng `mvn compile` fail vì Java thiếu class, có mâu thuẫn không? **Không.** Validate không mặc định compile hoặc kiểm tra mọi lỗi mã Java.

**Câu 5:** Chạy `mvn clean package` có bỏ qua validate vì đã clean không? **Không.** Clean là lifecycle riêng được thực thi theo yêu cầu; default lifecycle tới package vẫn đi qua validate và initialize.

## 17. Checklist đọc một POM về vòng đời khởi đầu

1. Xác định **packaging**, Maven/JDK và parent/effective POM.
2. Tìm goals gắn **validate**: rule gì, điều kiện fail gì?
3. Tìm goals gắn **initialize**: tạo file/thư mục/trạng thái nào?
4. Tìm generator ở **generate-sources** hoặc **generate-resources**; file sinh ở đâu?
5. Tìm cơ chế **đăng ký** source/resource roots.
6. Tìm consumer ở **process-resources** và **compile**; file đi đến output nào?
7. Chạy từng phase trong môi trường thử nghiệm nếu cần chẩn đoán, sau đó **clean build** toàn tuyến.
8. Kiểm tra file đã có trong **target/classes** và JAR cuối hay chưa.
9. Quan sát log plugin goal và các active profiles; không chỉ dựa vào tên phase.
10. Kiểm tra bước đầu build có thể tái tạo, an toàn và không phụ thuộc thao tác thủ công ở máy người dùng.

## Tài liệu tham khảo

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven Enforcer Plugin](https://maven.apache.org/enforcer/maven-enforcer-plugin/usage.html)
- [Apache Maven AntRun Plugin](https://maven.apache.org/plugins/maven-antrun-plugin/)
- [Build Helper Maven Plugin — add-resource](https://www.mojohaus.org/build-helper-maven-plugin/add-resource-mojo.html)
- [Apache Maven Resources Plugin — resources](https://maven.apache.org/plugins/maven-resources-plugin/resources-mojo.html)
