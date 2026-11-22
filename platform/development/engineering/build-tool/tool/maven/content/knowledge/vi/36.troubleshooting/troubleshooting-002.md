# Malformed POM, modelVersion và lỗi mô hình không hợp lệ trong Maven

## 1. Vì sao Maven báo lỗi ngay khi chưa biên dịch một dòng Java?

`pom.xml` là **Project Object Model (POM)**: tài liệu XML mô tả định danh dự án, parent, dependencies, repositories, plugins, packaging, profiles và các quy tắc build. Maven phải **đọc và xây dựng project model** trước khi có thể thực thi phần lớn lifecycle goals. Vì thế một lỗi POM có thể khiến lệnh `mvn test`, `mvn package` hay `mvn validate` dừng **trước khi đến Compiler Plugin hoặc Surefire**.

Các thông báo như `Non-parseable POM`, `Malformed POM`, `Unrecognised tag`, `Missing 'modelVersion'`, `The project ... has 1 error`, `Non-resolvable parent POM` thường bị gọi chung là “POM hỏng”. Tuy nhiên **nguyên nhân và cách sửa khác nhau**:

1. **XML không hợp lệ**: parser XML không thể tạo cây XML vì thiếu dấu đóng, ký tự `&` chưa escape hoặc quote sai.
2. **XML hợp lệ nhưng sai cấu trúc Maven**: tag tồn tại nhưng nằm **sai vị trí** hoặc không thuộc Maven POM model.
3. **Thiếu/sai thông tin bắt buộc của model**: `modelVersion`, GAV, parent coordinates, packaging hoặc phiên bản dependency không hợp lệ.
4. **Không tạo được effective model**: parent POM/BOM không resolve, property chưa có, profile hoặc repository configuration gây vấn đề.
5. **Model đã hợp lệ nhưng plugin/lifecycle fail**: dependency download, Java compile, plugin configuration hoặc test fail; không nên gán nhầm mọi lỗi `BUILD FAILURE` thành malformed POM.

**Mục tiêu chẩn đoán:** nhận biết lỗi thuộc tầng nào, sửa tại đúng vị trí được báo, rồi chạy lại một Maven verification có kiểm soát. **Không xóa cache, đổi `modelVersion` hoặc dùng skip flags để “làm xanh” build khi chưa biết nguyên nhân.**

### Kết quả mong đợi sau bài học

- Giải thích được `modelVersion` **không phải** phiên bản Maven binary, Java hay artifact.
- Phân biệt XML well-formedness, Maven raw model validation và effective model resolution.
- Nhận biết các lỗi `<dependency>`, `<plugin>`, `<parent>`, `<modules>`, `<profiles>` đặt sai cấu trúc.
- Đọc thông báo Maven có file path, line, column, tag và danh sách lỗi thay vì đoán.
- Sử dụng `mvn validate`, `help:effective-pom`, XML parser và `mvnval` đúng trường hợp.
- Thực hành một project **Java 17 + Maven + JUnit Jupiter** có POM hợp lệ, sau đó chủ động tạo và sửa những lỗi POM trong **bản sao an toàn**.

## 2. Dòng xử lý POM của Maven: biết đang hỏng ở tầng nào

Dưới đây là một cách tư duy đơn giản hóa về quá trình Maven đi từ file XML đến artifact:

~~~text
Chọn pom.xml (working directory hoặc -f)
             |
             v
Đọc bytes / kiểm tra encoding / XML well-formedness
             |
             v
Đọc Maven raw model (modelVersion, nodes, GAV...)
             |
             v
Validate raw model / các quy tắc POM
             |
             v
Resolve parent POM, imported BOM, profiles/properties
             |
             v
Tạo và kiểm tra effective model
             |
             v
Resolve plugins/dependencies khi goal cần
             |
             v
Thực thi lifecycle: validate -> compile -> test -> package -> verify
~~~

Một số bước có thể được thực hiện theo thứ tự/chi tiết khác giữa Maven 3 và Maven 4, nhưng sơ đồ phân loại nguyên nhân vẫn hữu ích.

**Nếu XML chưa parse được**, `mvn help:effective-pom` cũng không thể tạo effective POM. **Nếu parent POM không resolve được**, điều đó không chứng minh XML của child sai. **Nếu Surefire test fail**, project model có thể đã hoàn toàn hợp lệ.

### Ma trận loại lỗi

| Thông báo thường thấy | Tầng | Bước kiểm tra đầu tiên |
| --- | --- | --- |
| `Non-parseable POM` / XML parser error | XML syntax, encoding | Dòng/cột báo lỗi, XML parser |
| `Malformed POM` / `Unrecognised tag` | Cấu trúc Maven model | Tag nằm ở đâu trong cây POM? |
| `Missing 'modelVersion'` / unsupported model version | POM schema/model identity | Giá trị và vị trí của `modelVersion` |
| `Missing 'artifactId'` / invalid coordinates | Raw/effective model | GAV và parent inheritance |
| `Non-resolvable parent POM` | Inheritance/resolution | Parent GAV, `relativePath`, repositories |
| `Non-resolvable import POM` | BOM import/resolution | Imported BOM GAV, `type=pom`, `scope=import` |
| Duplicate dependency/plugin warning/error | Model validation | Gộp khai báo trùng, xem Maven version |
| Unknown packaging | Lifecycle mapping | Giá trị `<packaging>` và extension nếu có |
| Plugin configuration/goal error | Plugin execution | Plugin docs, effective POM, goal log |

**Không dựa duy nhất vào chữ “POM” trong error line.** Hãy xem **cụm lỗi đầu tiên và vị trí gốc**, vì Maven có thể liệt kê hàng chục lỗi dây chuyền sau một dấu đóng XML bị thiếu.

## 3. `modelVersion` chính xác là phiên bản của cái gì?

Trong POM chuẩn Maven 3:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.maven</groupId>
    <artifactId>minimal-demo</artifactId>
    <version>1.0.0</version>
</project>
~~~

Trong ví dụ trên có **bốn nhóm version khác nhau**:

| Thuộc tính | Ví dụ | Vai trò |
| --- | --- | --- |
| POM **`modelVersion`** | `4.0.0` | Phiên bản **cấu trúc tài liệu POM** được Maven hỗ trợ |
| Maven executable | Maven `3.9.x`, `3.10.x` hoặc `4.x` | Phiên bản chương trình `mvn` đang chạy |
| Project **`version`** | `1.0.0` | Phiên bản artifact trong GAV |
| Java language/API target | `maven.compiler.release=17` | Phiên bản Java mà source/output nhắm tới |

**Không sửa** `<modelVersion>4.0.0</modelVersion>` thành `3.9.9`, `17` hoặc `1.0.0` để khớp Maven/Java/project đang dùng.

### Maven 3 so với Maven 4

- **Maven 3:** POM model được hỗ trợ là **`4.0.0`**. Dùng namespace `http://maven.apache.org/POM/4.0.0`.
- **Maven 4:** vẫn hỗ trợ POM model **`4.0.0`** để tương thích các dự án Maven 3. Ngoài ra Maven 4 có **model `4.1.0`** với namespace `http://maven.apache.org/POM/4.1.0`, dùng cho **build POM** khi thực sự cần tính năng mới.
- Maven 4 phân biệt **build POM** và **consumer POM**; không nên tự suy rằng đổi mọi POM sang `4.1.0` là yêu cầu nâng cấp bắt buộc.
- Một repository cần chạy bằng Maven 3 thì **giữ model `4.0.0`**, trừ khi đã có kế hoạch chuyển công cụ và kiểm tra tương thích khác.

Tài liệu POM 4.0.0 chính thức dùng `modelVersion=4.0.0`. Maven 4 documentation mô tả bổ sung model 4.1.0. **Không viết `modelVersion=4.1.0` trong ví dụ nhằm chạy Maven 3**.

### `xsi:schemaLocation` có phải phiên bản Maven không?

Không. `xsi:schemaLocation` khai báo cặp **namespace URI** và **địa chỉ XSD** để IDE/XML validators hiểu cấu trúc. Tham khảo:

~~~xml
xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd"
~~~

Nó **không tự cài hoặc nâng cấp Maven**. Maven cũng không đơn giản dựa vào việc tải XSD từ internet rồi mới đọc mọi POM; Maven có model reader/validator riêng. Một XSD editor báo OK **chưa chứng minh** parent/BOM đã resolve hoặc plugin config hợp lệ.

## 4. POM tối thiểu và các thông tin bắt buộc

Một project Maven 3 độc lập cần cấu trúc:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example.maven</groupId>
    <artifactId>simple-project</artifactId>
    <version>1.0.0</version>
</project>
~~~

Định danh của artifact là:

~~~text
vn.example.maven:simple-project:1.0.0
~~~

Maven dùng **groupId:artifactId:version**, thường gọi là **GAV**, để xác định artifact. Nếu `<packaging>` không khai báo, project POM 4.0.0 thông thường mặc định **`jar`**.

**Ngoại lệ quan trọng:** một child POM có `<parent>` hợp lệ có thể **kế thừa `groupId` và `version`** từ parent. Nhưng `artifactId` của chính child vẫn cần được khai báo. Đừng báo “missing groupId” chỉ vì nó không nằm trực tiếp trong child POM nếu parent inheritance hợp lệ.

Ví dụ child:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example.maven</groupId>
        <artifactId>company-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>child-app</artifactId>
</project>
~~~

Đoạn trên **chỉ là cấu trúc minh họa**, chưa thành dự án build được độc lập nếu không có parent ở đường dẫn hoặc repository được cấu hình. Parent có các phần tử GAV **riêng**; nó không đồng nghĩa với `<modules>` của aggregator.

## 5. `Non-parseable POM`: XML không well-formed

Đây là loại lỗi ở tầng thấp nhất. Maven chưa thể đọc ra project model vì XML parser không tạo được cây tài liệu.

### 5.1. Thiếu dấu đóng

**Sai — đoạn XML có chủ ý bị lỗi:**

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example.maven</groupId>
    <artifactId>broken-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>lib</artifactId>
            <version>1.2.0</version>
        </dependency>
</project>
~~~

`<dependencies>` chưa đóng. Parser có thể báo rằng thẻ `<project>` xuất hiện khi vẫn đang chờ `</dependencies>`. **Vị trí báo lỗi có thể ở gần cuối file**, dù nguyên nhân là một tag mở từ nhiều dòng trước.

**Sửa:** thêm `</dependencies>` trước `</project>`.

### 5.2. Dấu `&` chưa escape

**Sai:**

~~~xml
<name>Research & Development</name>
~~~

Ký tự `&` trong XML mở đầu entity. Vì không có entity hợp lệ nên parser có thể báo lỗi dạng `The entity name must immediately follow the '&' in the entity reference`.

**Đúng:**

~~~xml
<name>Research &amp; Development</name>
~~~

Các ký tự phải chú ý:
- Dấu `&` trong text/attribute → `&amp;`.
- Dấu `<` trong text → `&lt;`.
- Dấu `>` thường có thể xuất hiện trong text nhưng `&gt;` giúp rõ ý; chuỗi `]]>` không được xuất hiện nguyên dạng trong character data.
- Quote trong **attribute** cần escape phù hợp với kiểu dấu nháy bao quanh.

Không thay tất cả `&` thành `&amp;` một cách mù quáng nếu nó **đã** là `&amp;` hoặc một entity hợp lệ, vì sẽ double-escape.

### 5.3. Lỗi quote và nesting

**Sai — thuộc tính không có dấu nháy:**

~~~xml
<project xmlns=http://maven.apache.org/POM/4.0.0>
~~~

**Đúng:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
~~~

**Sai — đóng sai thứ tự:**

~~~xml
<dependencies>
    <dependency>
    </dependencies>
</dependency>
~~~

**Đúng:**

~~~xml
<dependencies>
    <dependency>
    </dependency>
</dependencies>
~~~

Đây là lỗi XML, không phải lỗi compiler Java. Lệnh `javac` hoặc chỉnh version dependency không giúp sửa một thẻ XML bị sai nesting.

### 5.4. Encoding, copy/paste và ký tự điều khiển

Một POM khai báo:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
~~~

nên được lưu bằng **UTF-8 thực sự**. Nếu file bytes thuộc charset khác, parser có thể báo malformed input hoặc ký tự không hợp lệ. Một số ký tự điều khiển bị cấm trong XML 1.0, dù editor vẫn hiển thị file.

**Không tự “chữa encoding” bằng cách xóa hết dấu tiếng Việt, thay toàn bộ file bằng ASCII hoặc ép UTF-8 với tùy chọn gây mất bytes**. Kiểm tra encoding thực, lưu lại bằng editor tin cậy, xem Git diff để tránh mất nội dung.

## 6. `Malformed POM`: XML hợp lệ nhưng cấu trúc Maven sai

Một XML parser thông thường có thể đọc đoạn này:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example.maven</groupId>
    <artifactId>bad-shape</artifactId>
    <version>1.0.0</version>
    <dependency>
        <groupId>org.example</groupId>
        <artifactId>some-lib</artifactId>
        <version>2.0.0</version>
    </dependency>
</project>
~~~

Nhưng `<dependency>` là **phần tử sai ở cấp root**. Maven POM model yêu cầu các dependency trực tiếp nằm trong `<dependencies>`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.example</groupId>
        <artifactId>some-lib</artifactId>
        <version>2.0.0</version>
    </dependency>
</dependencies>
~~~

Nếu một Maven version phát hiện tag không mong đợi, thông báo có thể chứa **`Malformed POM`**, **`Unrecognised tag: 'dependency'`** hoặc mô tả tương tự kèm line/column. Không cam kết chính xác chữ/cột cho mọi phiên bản.

**Quy tắc sửa:** đối chiếu **cây cấu trúc Maven POM Reference**, không chỉ kiểm tra XML có đủ dấu đóng.

### 6.1. `dependencies` và `dependencyManagement` khác nhau

Khai báo dependency thật:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.10.2</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Quản lý version nhưng **chưa thêm dependency vào classpath**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`dependencyManagement` có lớp `<dependencies>` bên trong. Nếu viết `<dependencyManagement><dependency>...</dependency></dependencyManagement>`, XML có thể vẫn well-formed nhưng **không đúng Maven model**.

`dependencyManagement` không tự làm Surefire chạy JUnit hoặc tạo classpath dependency, vì dự án phải khai báo một **actual dependency** tương ứng nếu muốn sử dụng.

## 7. `plugins`, `pluginManagement` và `executions` phải đặt đúng chỗ

Một plugin được dùng trong build thường nằm dưới:

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

Một plugin version được quản lý cho project/con cháu có thể nằm trong:

~~~xml
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
~~~

**Không đặt `<plugin>` trực tiếp dưới `<project>` hoặc đặt `<plugins>` trực tiếp dưới `<dependencies>`.** Đây là lỗi cấu trúc. Tuy nhiên **đặt plugin đúng vị trí nhưng sai tên cấu hình nội bộ** có thể chỉ bị phát hiện khi plugin goal chạy: không phải mọi lỗi plugin parameter đều được Maven core validator phát hiện.

### 7.1. `executions` phải chứa `execution`

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.2.5</version>
            <executions>
                <execution>
                    <id>custom-tests</id>
                    <phase>test</phase>
                    <goals>
                        <goal>test</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Đoạn này chỉ minh họa cấu trúc `executions`; **không cần** khai báo execution này trong dự án demo vì Surefire đã được bind theo lifecycle mặc định cho packaging `jar`. Thêm một execution tùy tiện có thể khiến test chạy nhiều lần.

Nếu plugin goal không tồn tại, đó có thể là **plugin resolution/execution error** chứ không phải malformed XML. Đừng sửa `modelVersion` để giải quyết.

## 8. `modelVersion` thiếu, sai giá trị hoặc sai vị trí

### 8.1. Bỏ hẳn `modelVersion`

**Sai — thiếu phần tử bắt buộc:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <groupId>vn.example.maven</groupId>
    <artifactId>missing-model</artifactId>
    <version>1.0.0</version>
</project>
~~~

Ở Maven 3, phần tử `<modelVersion>` là yêu cầu của POM model 4.0.0. Maven có thể báo thiếu giá trị đó **ngay trước khi chạy lifecycle**.

**Sửa:** thêm ở cấp root:

~~~xml
<modelVersion>4.0.0</modelVersion>
~~~

### 8.2. Nhầm với Maven executable

**Sai:**

~~~xml
<modelVersion>3.9.9</modelVersion>
~~~

Maven executable version **không được điền** vào `<modelVersion>`. Để xem Maven đang dùng:

~~~bash
mvn --version
~~~

### 8.3. Nhầm với Java version

**Sai:**

~~~xml
<modelVersion>17</modelVersion>
~~~

Java target nằm ở property hoặc Compiler Plugin configuration, ví dụ:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

**`project.version=1.0.0`** là phiên bản artifact; **`modelVersion=4.0.0`** là POM schema; **`maven.compiler.release=17`** là Java language/API target; **`mvn --version`** cho phiên bản chương trình Maven.

### 8.4. Maven 4 model 4.1.0

Một Maven 4 build POM có thể dùng:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.1.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.1.0 https://maven.apache.org/xsd/maven-4.1.0.xsd">
    <modelVersion>4.1.0</modelVersion>
    <groupId>vn.example.maven</groupId>
    <artifactId>maven4-only-demo</artifactId>
    <version>1.0.0</version>
</project>
~~~

Đây là **đoạn minh họa dành cho Maven 4**, **không thuộc project runnable Maven 3 ở phần thực hành**. Không dùng cấu hình này khi CI đang chạy Maven 3.

Maven 4 vẫn hỗ trợ model 4.0.0, nên **đừng tự động nâng mọi POM lên 4.1.0 để sửa một lỗi XML/parent**.

## 9. Sai namespace, schemaLocation và lỗi chữ hoa–thường

Các tag Maven **phân biệt chữ hoa–thường**. `<modelVersion>` không phải `<ModelVersion>`, `<artifactId>` không phải `<artifactID>`.

Ví dụ sai về tên tag:

~~~xml
<ModelVersion>4.0.0</ModelVersion>
~~~

Nếu XML vẫn hợp lệ, Maven có thể báo unrecognised tag hoặc thiếu modelVersion theo cơ chế parser/model reader. **Sửa tên element**, không phải sửa Java code.

Namespace chuẩn POM 4.0.0 là:

~~~text
http://maven.apache.org/POM/4.0.0
~~~

XSD tham chiếu:

~~~text
https://maven.apache.org/xsd/maven-4.0.0.xsd
~~~

Khi copy từ web, đừng tự đổi toàn bộ `http://maven.apache.org/POM/...` thành URL `https://...` vì **namespace URI là định danh XML**, không đơn giản là link tải file. `xsi:schemaLocation` có **hai vế**: namespace và XSD location; thiếu một vế có thể khiến IDE/XSD validator báo lỗi.

**Không chẩn đoán toàn bộ Maven model chỉ bằng XSD editor.** Maven core còn kiểm tra semantics, inheritance, profiles, repositories và plugins, những thứ XSD không thể tự resolve.

## 10. Project coordinates và `packaging` cũng có lỗi mô hình

Một POM root thiếu `<artifactId>` sẽ không có artifact identity đầy đủ. Một POM độc lập thiếu `<groupId>` hoặc `<version>` cũng không có GAV đầy đủ, trừ khi kế thừa hợp lệ từ parent.

**Sai — root project không có artifactId:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example.maven</groupId>
    <version>1.0.0</version>
</project>
~~~

**Đúng:** thêm `<artifactId>...</artifactId>` với giá trị theo project contract.

### `packaging` không phải tên tùy ý

Các packaging core thông dụng gồm `jar`, `war`, `pom`, `maven-plugin` và vài loại khác. Project aggregator/parent POM có `<modules>` thường cần `<packaging>pom</packaging>`.

**Sai trong aggregator thông thường:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example.maven</groupId>
    <artifactId>root-aggregator</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <modules>
        <module>api</module>
        <module>service</module>
    </modules>
</project>
~~~

**Sửa:** khi root đúng là aggregator, đổi `<packaging>` thành `pom`, kiểm tra các module paths và child POMs. Không đổi packaging một project sản phẩm thành `pom` chỉ để chặn lỗi, vì điều đó thay loại artifact và lifecycle bindings.

Plugin hoặc extension có thể cung cấp packaging đặc biệt. Nếu Maven báo unknown packaging, kiểm tra plugin/extension định nghĩa lifecycle mapping, không mặc định mọi giá trị ngoài `jar/war/pom` đều vô hiệu.

## 11. `Non-resolvable parent POM` không đồng nghĩa XML malformed

Một child POM XML hợp lệ có thể khai báo parent:

~~~xml
<parent>
    <groupId>vn.example.maven</groupId>
    <artifactId>company-parent</artifactId>
    <version>2.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Nhưng:
- File `../pom.xml` không tồn tại.
- File có nhưng GAV của parent không khớp.
- Parent chưa có trong local/remote repository.
- Repository/mirror/settings không thể truy cập.
- Parent version bị gõ sai.
- Parent hiện tại không có `<packaging>pom</packaging>` như yêu cầu của parent.

Maven có thể báo **`Non-resolvable parent POM`** hoặc **`'parent.relativePath' points at wrong local POM`**.

**Mô hình chẩn đoán:**

1. Đọc **GAV trong `<parent>`** của child, không đoán theo folder name.
2. Xem `relativePath` từ **vị trí child `pom.xml`**, không phải từ shell cwd.
3. Kiểm tra file parent local nếu được khai báo.
4. Nếu dùng repository, xác định parent artifact đã được publish/resolved chưa.
5. Đọc `settings.xml`/mirrors và network/permission errors nếu có.
6. Chạy từ **root reactor** khi project có multi-module đúng.
7. Không sửa `<modelVersion>` để “chữa” một parent không tải được.

### `relativePath` rỗng có ý nghĩa riêng

Trong Maven 3, `<relativePath/>` bỏ qua tìm parent theo relative filesystem path và cho phép resolution từ local/remote repositories; Maven 4 có thêm cơ chế nhận diện project trong build. Chỉ dùng `<relativePath/>` khi parent **thực sự được quản lý từ repository** theo project design, không phải như mẹo giấu parent POM sai.

**Đừng xóa thư mục `.m2` toàn bộ** để đoán lỗi parent: điều đó có thể làm mất caches hợp lệ và tăng lưu lượng mạng. Kiểm tra GAV/URL/credentials trước; nếu cần dùng local repository thử riêng trong sandbox.

## 12. BOM import sai vẫn khác lỗi XML syntax

Imported BOM phổ biến trong Maven 3:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example.platform</groupId>
            <artifactId>company-bom</artifactId>
            <version>3.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Một BOM import cần đúng **groupId, artifactId, version, type `pom` và scope `import`** trong dependencyManagement. Nếu BOM chưa publish hoặc mirror/network lỗi, Maven có thể báo **`Non-resolvable import POM`**. Nếu `<dependency>` bị đặt sai cấp, lại có thể báo **Malformed POM/Unrecognised tag**.

**Không tự suy BOM import làm dependency của ứng dụng**: `dependencyManagement` là quy tắc quản lý phiên bản; dependency thực phải được khai báo riêng.

Nếu lỗi `dependencies.dependency.version is missing`, trước hết xem dependency đó có được parent/imported BOM quản lý không, BOM có resolve thành công không và version policy thực tế.

## 13. Trùng khai báo dependency/plugin: warning và stricter model validation

Ví dụ **khai báo trùng dependency với cùng groupId/artifactId/type/classifier**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.10.2</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.0</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**Đây là đoạn POM cố ý sai**, không phải project đầy đủ. Maven có thể cảnh báo/hoặc báo lỗi model validation tùy context và phiên bản. Cách sửa đúng là **chỉ giữ một khai báo có version được duyệt**, hoặc quản lý version tập trung trong dependencyManagement.

Tương tự, **khai báo lặp `<plugin>`** trong cùng `<build><plugins>` gây model ambiguity; gộp cấu hình/executions đúng theo project policy.

**Đặc biệt với Maven 3.10.0:** release notes của Apache Maven ghi nhận **stricter POM validation**: nhiều lỗi trước đây chỉ WARNING trong nhánh 3.9 được nâng thành FAILURE cho project model (trong đó có duplicate plugins, version/repository ID không hợp lệ). Không được suy rằng mọi duplicate dependency đều được xử lý giống nhau trong mọi context; đọc đúng thông báo và phiên bản Maven đang chạy.

Release notes có nhắc một cơ chế tạm tắt stricter validation, nhưng **đừng coi nó là giải pháp lâu dài**: POM không hợp lệ vẫn có thể gây lỗi với CI/Maven 4 hoặc consumers. Ưu tiên sửa khai báo trùng và phiên bản sai.

## 14. Lỗi nằm trong `profiles` hoặc `pluginManagement`

Profiles có thể thêm dependencies, plugins, repositories và properties khi active:

~~~xml
<profiles>
    <profile>
        <id>ci</id>
        <properties>
            <build.mode>ci</build.mode>
        </properties>
    </profile>
</profiles>
~~~

Đoạn này là một fragment hợp lệ nếu nằm **trực tiếp dưới `<project>`**, không phải `<build><plugins>`.

Một cấu trúc XML well-formed nhưng `<profile>` đặt sai cấp có thể bị Maven báo malformed. Một profile có model hợp lệ nhưng được activate do `-Pci` có thể khiến **effective model** khác local build; xem active profiles trước khi kết luận lỗi không tái hiện.

Kiểm tra:

~~~bash
mvn -B -ntp help:active-profiles
mvn -B -ntp help:effective-pom -Doutput=target/effective-pom.xml
~~~

Những goals trên **chỉ chạy khi Maven đã đọc được POM và resolve được model đủ dùng**; nếu raw XML malformed, chúng không thể giúp tạo effective POM.

### `pluginManagement` khác `<plugins>`

- `<pluginManagement>` quản lý default plugin version/configuration cho nơi plugin được sử dụng/inherited.
- `<plugins>` là danh sách plugin được đưa vào build model.
- Một plugin được liệt kê trong `<pluginManagement>` không có nghĩa mọi goal tùy ý của plugin đó đã được bind vào lifecycle.

Vì vậy nếu POM parse được nhưng goal không chạy, hãy kiểm tra **execution binding** trước khi quy nó về malformed POM.

## 15. Lỗi POM không phải lúc nào cũng nằm trong `pom.xml` bạn vừa mở

Maven có thể đọc **root POM, parent POM, child POM, imported BOM hoặc POM từ repository**. Với multi-module:

~~~text
platform/
├── pom.xml              aggregator + parent
├── api/pom.xml          child
└── service/pom.xml      child
~~~

Lỗi ở `service/pom.xml` có thể xuất hiện khi chạy Maven từ root. Cần đọc **file path chính xác trong thông báo**, không tự động sửa root POM.

Nếu chạy Maven sai working directory, Maven có thể báo **không tìm thấy POM** trong current folder; đây không phải malformed POM của project.

Chỉ rõ POM khi cần:

~~~bash
mvn -B -ntp -f pom.xml validate
~~~

Hoặc tại root aggregator:

~~~bash
mvn -B -ntp -f platform/pom.xml validate
~~~

**Vị trí ví dụ `platform/pom.xml` chỉ đúng khi shell đang ở thư mục cha của `platform`**. Trong thực hành dùng `-f` với đường dẫn thực và được phép, không chẩn đoán bằng cách thay đổi ngẫu nhiên current directory.

Với parent GAV khác actual parent POM, xem `<parent>`/`relativePath` trước. Với module path không tồn tại, xem `<modules>` và filesystem/checkout; không tự tạo directory rỗng chỉ để qua validator.

## 16. Quy trình chẩn đoán an toàn: từ lỗi đầu tiên

### Bước 1 — xác định Maven runtime và POM

~~~bash
mvn --version
mvn -B -ntp -f pom.xml validate
~~~

**Lưu ý:** `mvn validate` là Maven lifecycle phase. Maven cần build project model và có thể chạy **plugins đã bind tại validate**. Nó **không phải** một XML parser thuần hoặc lệnh luôn không có side effects. Trên POM từ nguồn không tin cậy, hãy chạy trong sandbox với quyền thấp và không đưa release credentials.

### Bước 2 — lấy file, line/column và nguyên nhân gốc

Thông báo Maven điển hình có file path và khu vực dòng/cột. Cách đọc:

~~~text
[ERROR] Non-parseable POM .../pom.xml:
... expected START_TAG or END_TAG ...
@ line 28, column 5
~~~

Đây là **mẫu minh họa cấu trúc log**, không phải output cố định của mọi parser/version. Hãy:
- Đọc lỗi đầu tiên, file path, line, column.
- Xem khoảng 5–10 dòng **trước và sau** vị trí.
- Kiểm tra XML closing tags, quotes, `&`, namespace.
- Nếu lỗi ở `</project>`, tìm tag chưa đóng phía trên.
- Sửa **một nhóm lỗi gốc**, chạy lại parser/validate trong sandbox.

### Bước 3 — kiểm tra XML well-formedness độc lập

Nếu có `xmllint`:

~~~bash
xmllint --noout pom.xml
~~~

Lệnh này kiểm tra **XML syntax**, không chứng minh Maven model đúng hoặc parent/BOM resolve được. Có thể dùng XML validator trong IDE với schema 4.0.0 cho kiểm tra cấu trúc bổ sung.

**PowerShell 5.1/Windows** — kiểm tra XML (không chạy Maven):

~~~powershell
[xml]$pom = Get-Content -LiteralPath .\pom.xml -Raw -Encoding UTF8
$pom.DocumentElement.LocalName
~~~

Với một POM well-formed có root `<project>`, dòng cuối in:

~~~text
project
~~~

Parser này **không biết Maven POM semantics**. Nếu file không well-formed, bước tạo `[xml]` có thể throw exception. `Get-Content -Encoding UTF8` chỉ thích hợp khi POM bytes thực sự là UTF-8; đừng dùng nó để ghi đè file encoding chưa được kiểm tra.

### Bước 4 — nếu XML hợp lệ, kiểm tra Maven model

~~~bash
mvn -B -ntp -f pom.xml validate
~~~

Lúc này tập trung vào:
- `modelVersion` và namespace.
- Element sai vị trí (`dependency`, `plugin`, `executions`, `profiles`).
- GAV bắt buộc/inherited version.
- Parent/BOM import coordinates.
- Duplicate dependency/plugin declarations.
- Packaging và modules paths.

### Bước 5 — khi model đủ hợp lệ, xem effective POM

~~~bash
mvn -B -ntp -f pom.xml help:effective-pom -Doutput=target/effective-pom.xml
~~~

Effective POM cho biết cấu hình **sau inheritance, property interpolation, profile activation và defaults**. Nếu chưa resolve được parent/BOM, lệnh cũng có thể fail; khi đó sửa resolution trước.

### Bước 6 — đối chiếu Git diff/CI

~~~bash
git status --short
git diff --check -- pom.xml
git diff -- pom.xml
~~~

`git diff --check` giúp thấy một số lỗi whitespace, **không validate XML hay Maven model**. Nếu POM thay sau khi merge, so commit SHA và CI logs để biết thay đổi nào thực sự gây lỗi.

Không dùng `git reset --hard` hoặc `git clean -fdx` trên workspace chung để xóa lỗi POM; có thể làm mất thay đổi khác. Khi cần tái hiện, dùng checkout riêng.

## 17. Maven 4.1: `mvnval` để phân biệt raw và effective validation

Theo tài liệu Maven hiện hành, **`mvnval` là công cụ POM Validation Tool được phân phối cùng Maven 4.1.0**. Nếu máy thực sự có Maven phiên bản hỗ trợ, nó cung cấp hai chế độ hữu ích.

### Raw mode: không truy cập repository

~~~bash
mvnval --mode raw pom.xml
~~~

Raw mode đọc và validate raw POM, **không cần tải parent/BOM từ repository**. Hữu ích khi parent chưa publish, máy offline hoặc đang muốn tìm nhiều lỗi syntax/model trong nhiều POMs.

### Effective mode: cần resolution

~~~bash
mvnval --mode effective pom.xml
~~~

Effective mode kiểm tra raw và resolve parents/BOMs để đánh giá model đầy đủ, có thể dùng network/local cache.

### Nhiều POM và JSON output

~~~bash
mvnval --mode raw parent/pom.xml api/pom.xml service/pom.xml
mvnval --mode raw --format json pom.xml
~~~

Đây là công cụ **Maven 4.1+**, không giả định `mvnval` tồn tại ở Maven 3.9 hay 3.10. Nếu CLI báo `command not found`, kiểm tra Maven installation trước; **đừng đổi modelVersion lên 4.1.0 chỉ để lệnh có mặt**.

Tài liệu `mvnval` phân biệt exit codes: **0 không có lỗi/cảnh báo, 1 có errors, 4 chỉ có warnings**, cùng các codes cho usage/interruption. Trong CI có thể chọn warning policy theo ngữ cảnh; không bỏ qua exit 4 mà không biết đó là warning-only.

**`mvnval --mode raw` không chứng minh dependency có thể tải hoặc Java code compile**. Nó chỉ xác nhận tầng raw model mà nó kiểm tra.

## 18. Dự án Java 17 runnable để thực hành và tái hiện lỗi

Tạo project đơn module:

~~~text
pom-diagnostics-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/maven/PomDiagnostics.java
    └── test/java/vn/example/maven/PomDiagnosticsTest.java
~~~

**Yêu cầu:** JDK 17+, Maven 3.9+ (hoặc Maven 3.10+ với modelVersion 4.0.0), repository được phép cho Maven plugins và JUnit Jupiter. Demo **không cần database, Docker, SCM remote hay deploy repository**.

Mục tiêu:
1. POM hợp lệ để `mvn validate` và `mvn clean verify` chạy.
2. Java application tạo JAR có `Main-Class`.
3. JUnit Jupiter test chạy bằng Maven Surefire.
4. Sau khi baseline PASS, tạo các lỗi XML/model riêng biệt trong **bản sao POM**, xem error, sửa rồi verify lại.

### 18.1. `pom.xml` — bản hợp lệ đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.maven</groupId>
    <artifactId>pom-diagnostics-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>POM Diagnostics Demo</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.maven.PomDiagnostics</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Kiểm tra về cấu trúc:**
- Root `<project>` đúng namespace 4.0.0 và `<modelVersion>4.0.0</modelVersion>`.
- GAV đầy đủ `vn.example.maven:pom-diagnostics-demo:1.0.0`.
- `jar` packaging hợp lệ và Main-Class được Jar Plugin tạo.
- `<dependencies>` chứa đúng một JUnit Jupiter dependency với scope `test`.
- Maven plugins nằm trong `<build><plugins><plugin>...`.
- Compiler Plugin `release=17` dùng JDK hỗ trợ.
- Surefire chạy JUnit test; `failIfNoTests=true` giúp tránh suite rỗng.
- Không có `distributionManagement`; bài không chạy `mvn deploy`.

Các versions pin làm **baseline ví dụ**, không khẳng định mới nhất; trong production cần chọn các versions theo parent/toolchain/repository policy.

### 18.2. `src/main/java/vn/example/maven/PomDiagnostics.java`

~~~java
package vn.example.maven;

public final class PomDiagnostics {
    private PomDiagnostics() {
    }

    public static String message() {
        return "POM MODEL: OK";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

### 18.3. `src/test/java/vn/example/maven/PomDiagnosticsTest.java`

~~~java
package vn.example.maven;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PomDiagnosticsTest {
    @Test
    void messageIsStable() {
        assertEquals("POM MODEL: OK", PomDiagnostics.message());
    }
}
~~~

Bài test ngắn giúp phát hiện test phase thật sự chạy. **Lỗi Maven model xảy ra trước khi test này được compile hoặc thực thi**; đó là dấu hiệu phân loại quan trọng.

## 19. Chạy baseline: ba bước và stdout chính xác

Từ thư mục project, sau khi tạo đúng ba file:

~~~bash
mvn --version
mvn -B -ntp -f pom.xml validate
mvn -B -ntp -f pom.xml clean verify
java -jar target/pom-diagnostics-demo-1.0.0.jar
~~~

**Output chính xác của riêng lệnh `java -jar` cuối cùng**:

~~~text
POM MODEL: OK
~~~

Giải thích:
- `validate` xác nhận Maven đã xây dựng model đủ để thực hiện phase và các checks bind ở validate (demo không có Enforcer execution ở validate).
- `clean verify` compile Java 17, compile test, Surefire chạy **1 JUnit test method**, rồi package JAR.
- `java -jar` chạy artifact cuối nhờ Main-Class.
- Không `install`, không `deploy`, không upload remote.

Maven console chứa nhiều dòng phụ thuộc version/plugin cache, nên **không coi transcript của một máy là stdout cố định cho mọi người**.

Các file kỳ vọng:

~~~text
target/classes/vn/example/maven/PomDiagnostics.class
target/test-classes/vn/example/maven/PomDiagnosticsTest.class
target/surefire-reports/...
target/pom-diagnostics-demo-1.0.0.jar
~~~

Nếu chỉ chạy `mvn validate`, `target` JAR **chưa được tạo**. Nếu một JAR từ lượt cũ vẫn còn, đừng xem đó là bằng chứng validate đã package.

## 20. Thực hành tạo lỗi 1 — XML unescaped ampersand

Trong **bản sao POM dùng cho bài học**, sửa:

~~~xml
<name>POM & XML Diagnostics</name>
~~~

Đây là **XML sai**, vì `&` chưa escape. Chạy:

~~~bash
mvn -B -ntp -f pom.xml validate
~~~

Maven sẽ **không thể parse XML**, nên không đến test/compile. Error text có thể chứa `Non-parseable POM`, message về entity/reference và line/column tương ứng.

Sửa:

~~~xml
<name>POM &amp; XML Diagnostics</name>
~~~

Sau đó chạy lại `mvn validate`, rồi `mvn clean verify`. **Không cần thay Java source hoặc dependency versions.**

## 21. Thực hành tạo lỗi 2 — đặt `<dependency>` sai cấp

Để tạo lỗi cấu trúc có chủ đích, đặt fragment này **trực tiếp dưới `<project>`** thay vì trong `<dependencies>`:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.10.2</version>
</dependency>
~~~

XML parser vẫn có thể đọc, nhưng Maven model 4.0.0 **không có element `<dependency>` trực tiếp dưới `<project>`**. Maven có thể báo `Malformed POM`/`Unrecognised tag`.

Sửa bằng cách để dependency trong `<dependencies>`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.10.2</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Không thêm bản sao nếu dependency đã tồn tại; **chỉ khôi phục một khai báo gốc**. Việc tạo hai khai báo cùng GAV làm phát sinh lỗi model khác và khiến thí nghiệm khó đọc.

## 22. Thực hành tạo lỗi 3 — `modelVersion` và namespace

**Thí nghiệm A:** xóa `<modelVersion>4.0.0</modelVersion>` trong bản sao POM, chạy `mvn validate`, ghi message về model version missing.

**Thí nghiệm B:** đặt:

~~~xml
<modelVersion>17</modelVersion>
~~~

Giải thích vì sao con số 17 chỉ phù hợp với:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

**Thí nghiệm C:** giả sử IDE có Maven 4, đổi một POM thử nghiệm sang model 4.1.0 để hiểu khác biệt. **Không dùng file 4.1.0 đó làm project Maven 3 chính** và không cho rằng model upgrade giúp sửa syntax.

Sau mỗi thí nghiệm, phục hồi `<modelVersion>4.0.0</modelVersion>` đúng cấp root, giữ namespace 4.0.0. Chỉ thay **một yếu tố mỗi lần**, đọc error first-line và kiểm chứng lại.

## 23. Thực hành tạo lỗi 4 — child parent không resolve

Trong một **project multi-module sandbox tách riêng**, viết child fragment:

~~~xml
<parent>
    <groupId>vn.example.maven</groupId>
    <artifactId>unknown-parent</artifactId>
    <version>99.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Đây là **fragment minh họa**, không chèn vào POM runnable đơn module ở mục 18 khi chỉ muốn thử `modelVersion`. Nếu parent không tồn tại hoặc path trỏ POM có GAV khác, Maven có thể báo `Non-resolvable parent POM`/wrong `relativePath`.

Bài học:
- Parent GAV phải khớp parent POM thực tế.
- `relativePath` tính từ child POM.
- Repository có thể cần publish parent nếu build độc lập.
- `help:effective-pom` cũng có thể fail nếu model inheritance chưa giải quyết.
- **XML có thể hoàn toàn hợp lệ trong tình huống này**.

Không tự tạo artifact parent giả trong `.m2` để che lỗi; sửa đúng GAV/path hoặc build từ root theo thiết kế.

## 24. Thực hành tạo lỗi 5 — trùng plugin/dependency

Trong một bản sao POM, thêm **hai `<plugin>` có cùng groupId/artifactId** trong một `<build><plugins>`. Xem Maven phiên bản đang chạy: ở các bản mới, validation có thể nghiêm ngặt hơn; không hứa cùng một log trên Maven 3.9, 3.10 và 4.

Các hành động an toàn:
1. Gộp duplicate plugins thành **một plugin declaration**.
2. Gộp executions/config theo đúng mục tiêu.
3. Nếu hai dependencies cùng coordinates nhưng khác version, chọn **một version được phê duyệt**, hoặc quản lý version trong dependencyManagement.
4. Không disable model validation trong CI chỉ để duy trì POM mâu thuẫn.

Với cùng test suite, phiên bản plugin khác nhau có thể còn tạo hành vi khác. Đây là lý do cần chốt Maven runtime trong bug report.

## 25. Khác biệt giữa lỗi cấu trúc, lỗi resolution và plugin failure

| Dấu hiệu | Độ sâu Maven đã đi đến | Kết luận ban đầu |
| --- | --- | --- |
| XML parser báo `The entity name...` | Chưa tạo XML tree | Sửa `&`, quotes hoặc XML syntax |
| `Unrecognised tag 'dependency'` | Đã nhìn thấy XML elements | Sửa nesting theo Maven POM schema |
| `Missing 'modelVersion'` | Raw model thiếu trường bắt buộc | Sửa modelVersion/version model |
| `Non-resolvable parent POM` | Tới inheritance/resolution | Sửa parent GAV/path/repository |
| `Non-resolvable import POM` | Tới dependencyManagement BOM resolution | Sửa BOM GAV/import/repository |
| `Failed to execute goal compiler:compile` | Model đã đủ hợp lệ để thực thi goal | Kiểm tra Java/JDK/compiler config |
| `There are test failures` | Tests đã chạy | Xem Surefire report, không sửa modelVersion |
| `Plugin prefix not found` | Plugin goal resolution | Kiểm tra goal spelling/plugin groups/repositories |

**Không sửa một lỗi downstream bằng cách thay một trường upstream không liên quan.** Ví dụ Java `cannot find symbol` không tự chứng minh `pom.xml` malformed, dù nguyên nhân classpath từ POM có thể liên quan.

## 26. CI và IDE: chặn POM hỏng từ sớm

Một pipeline an toàn có thể thực hiện:

~~~text
Checkout reviewed commit
        |
        v
Read Maven/JDK versions and POM path
        |
        v
XML well-formedness check (nếu tool có)
        |
        v
Maven model validation / mvnval raw nếu có
        |
        v
Maven validate và effective model resolution
        |
        v
Maven clean verify / tests / artifact checks
        |
        v
Lưu logs, Git SHA, Maven version và kết quả
~~~

Lệnh cơ bản cho Maven 3:

~~~bash
mvn --version
mvn -B -ntp -f pom.xml validate
mvn -B -ntp -f pom.xml clean verify
~~~

CI **phải fail khi `validate` hoặc `verify` trả exit code khác 0**. Không dùng `-DskipTests` để đổi trạng thái POM hỏng thành xanh; model error xảy ra trước test và skip test không giải quyết nguyên nhân.

### Pull request chứa POM không đáng tin

`mvn validate` **có thể chạy plugins** bind ở validate và Maven có thể tải plugins/dependencies. Với PR từ nguồn chưa được tin cậy, chạy trong sandbox, quyền chỉ đọc và **không cấp release token/Git push key**, vì Maven plugins có khả năng thực thi code trong quá trình build.

`mvnval --mode raw` ở Maven 4.1+ hữu ích cho kiểm tra POM **không truy cập repository**, nhưng không thay việc chạy Maven build/test thực ở environment kiểm soát.

### Ghi bug report để người khác tái hiện

Ghi đủ:
- Git commit SHA, path đúng của POM và module.
- Lệnh Maven **nguyên văn**, working directory, active profiles.
- `mvn --version` và JDK của Maven process.
- Error đầu tiên, **file path, line, column**.
- Khi nào lỗi bắt đầu: diff POM, parent/BOM/plugin versions.
- Trạng thái parent/BOM resolution, settings/mirror nếu có liên quan.
- Kết quả `xmllint`/`mvnval raw` hoặc Maven `validate`.
- Nếu đã qua model stage, plugin/test report tương ứng.

Không đăng công khai full `mvn -X` logs khi chưa redaction; chúng có thể chứa URLs, paths, settings hoặc chi tiết nội bộ.

## 27. Các anti-pattern chẩn đoán POM

**1. “Cứ đổi modelVersion cho bằng Maven version.”** Sai: Maven 3 dùng model 4.0.0, Maven 4 cũng hỗ trợ model 4.0.0.

**2. “XML parser OK thì Maven model chắc chắn OK.”** Sai: `<dependency>` đặt dưới `<project>` vẫn là XML well-formed nhưng sai Maven schema.

**3. “XSD editor xanh thì parent/BOM resolve được.”** Sai: XSD không truy cập repository/resolve inheritance giống Maven.

**4. “`help:effective-pom` giúp sửa POM chưa parse được.”** Không thể tạo effective model nếu raw model/XML không được đọc.

**5. “Thiếu `groupId` trong child POM chắc chắn sai.”** Child có thể kế thừa từ parent hợp lệ.

**6. “`dependencyManagement` tự tải mọi dependency được quản lý.”** Không; phải có dependency thực được dùng.

**7. “Trùng dependency/plugin chỉ là cosmetic warning.”** Stricter validators và các Maven versions mới có thể fail; model ambiguity cần sửa.

**8. “Unknown packaging nghĩa là Java code sai.”** Không; xem packaging/lifecycle mapping trước.

**9. “`Non-resolvable parent POM` là lỗi XML malformed.”** Không nhất thiết; thường liên quan GAV, path và repositories.

**10. “Xóa sạch `.m2`/workspace để thử.”** Có thể mất dữ liệu/cache và gây downloads lớn; xác định lỗi gốc trước.

**11. “Cứ chạy `mvn -X` rồi gửi log công khai.”** Cẩn trọng secrets/config nội bộ; redaction trước.

**12. “`mvn validate` luôn chỉ đọc và không thực thi code.”** Không: validate-bound plugin goals có thể chạy.

**13. “Bỏ Maven model validation cho CI qua build.”** Không giúp bảo đảm publishable POM và có thể làm consumer hỏng.

**14. “Cập nhật Maven 3 sang 4 đồng nghĩa bắt buộc đổi POM 4.1.0.”** Không; Maven 4 tiếp tục hỗ trợ model 4.0.0.

## 28. Bài tập tự luyện

1. Phân biệt lỗi `Non-parseable POM` với `Malformed POM` và `Non-resolvable parent POM`.
2. Viết POM tối thiểu Maven 3 có GAV `vn.example.maven:hello:1.0.0` và `modelVersion` đúng.
3. Đổi `<name>Research &amp; Development</name>` thành `&` không escape, dùng XML parser giải thích vì sao fail.
4. Đặt `<dependency>` trực tiếp trong root và mô tả vì sao XML well-formed vẫn sai Maven model.
5. So `modelVersion=4.0.0`, Maven 3.9/3.10 executable và `maven.compiler.release=17`.
6. Tạo demo Java 17 ở mục 18, chạy `mvn validate`, `mvn clean verify` và `java -jar`; xác nhận stdout đúng.
7. Xóa `modelVersion` trên bản sao rồi đọc lỗi Maven có line/column, khôi phục lại.
8. Tạo child với `<parent>` GAV sai; kiểm tra `relativePath` và phân biệt model validation với resolution.
9. Trong demo sandbox, tạo duplicate plugin rồi so messages giữa Maven versions nếu bạn có nhiều Maven installations.
10. Nếu có Maven 4.1+, dùng `mvnval --mode raw` và `--mode effective` trên cùng POM có parent chưa publish, so phạm vi/khả năng truy cập mạng.
11. Thiết kế CI gate chặn POM sai trước build/test nhưng không cho PR truy cập deploy secrets.
12. Viết một bug report có command, Maven/JDK version, POM path, lỗi đầu tiên và hướng sửa đã xác minh.

## 29. Checklist xử lý một POM không hợp lệ

1. Xác minh đúng `pom.xml` và working directory/`-f`.
2. Ghi lại Maven version/JDK và command.
3. Đọc **lỗi đầu tiên**, file path, line/column.
4. Kiểm tra encoding, XML tags, quote, dấu `&`.
5. Nếu XML hợp lệ, xem root `<project>` và `modelVersion`.
6. Với Maven 3, dùng model 4.0.0, đúng POM namespace.
7. Phân biệt project version và Java compiler release.
8. Kiểm tra GAV, parent inheritance và packaging.
9. Kiểm tra dependencies/dependencyManagement nesting.
10. Kiểm tra plugins/pluginManagement/executions nesting.
11. Kiểm tra parent/BOM import GAV và repository resolution.
12. Kiểm tra `relativePath` theo vị trí child POM.
13. Kiểm tra modules/aggregator, `<packaging>pom</packaging>`.
14. Gộp dependency/plugin declarations trùng hoặc mâu thuẫn.
15. Nếu có Maven 4.1+, dùng `mvnval --mode raw` để tìm nhiều model problems.
16. Nếu model đủ hợp lệ, dùng `help:effective-pom` để kiểm tra inheritance/profiles.
17. Phân biệt model error với plugin/dependency/Java/test failure.
18. Chạy Maven `validate` rồi `clean verify` trong môi trường an toàn.
19. Đọc Surefire/JAR outputs chỉ sau khi model đã pass và lifecycle thực sự chạy.
20. Giữ Git diff nhỏ, không thay đổi version/packaging không liên quan.
21. Không xóa dữ liệu chung, không skip checks để che lỗi.
22. Ghi nguyên nhân gốc và bài học vào review/CI record.

### Tổng kết

**“Malformed POM” là vấn đề cấu trúc model, nhưng không phải mọi lỗi liên quan `pom.xml` đều là malformed XML.** Một POM có thể sai ở cú pháp XML (`Non-parseable POM`), hợp lệ XML nhưng đặt tag sai vị trí (`Malformed POM`/`Unrecognised tag`), thiếu trường quan trọng (`modelVersion`, GAV), không resolve được parent/BOM hoặc chỉ thất bại ở plugin/test sau khi model đã hợp lệ.

Đặc biệt, **`modelVersion=4.0.0` không có nghĩa bạn dùng Maven 4 executable**: nó là phiên bản schema POM chuẩn cho Maven 3 và vẫn được Maven 4 hỗ trợ; Maven 4 mới có thêm model 4.1.0 cho build POM khi cần. Hãy **đọc lỗi đầu tiên và đúng line/column**, kiểm tra XML trước, kiểm tra cấu trúc Maven sau, rồi xác minh effective model và lifecycle. **Đừng dùng các workaround như bỏ validation, đổi ngẫu nhiên modelVersion hoặc xóa caches** để che sai lầm có thể sửa trực tiếp.

### Tài liệu chính thức

- [Apache Maven — POM 4.0.0 Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — What's New in Maven 4](https://maven.apache.org/whatsnewinmaven4.html)
- [Apache Maven — Maven 4 Migration Guide](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html)
- [Apache Maven — Maven 3.10.0 Release Notes, Stricter POM Validation](https://maven.apache.org/docs/3.10.0/release-notes.html)
- [Apache Maven — Maven POM Validation Tool `mvnval`](https://maven.apache.org/tools/mvnval.html)
- [Apache Maven — Maven Model 4.0.0 API](https://maven.apache.org/ref/3-LATEST/apidocs/org/apache/maven/model/Model.html)
- [Apache Maven — Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Apache Maven — Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven — Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
