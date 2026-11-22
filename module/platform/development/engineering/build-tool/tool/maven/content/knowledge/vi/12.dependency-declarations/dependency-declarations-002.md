# Phụ thuộc trực tiếp, bắc cầu và đồ thị Maven xây dựng

Một ứng dụng Java hiếm khi chỉ dùng các thư viện được liệt kê trực tiếp trong tệp `pom.xml`. Thư viện A có thể cần thư viện B; B lại cần C. Apache Maven đọc thông tin phụ thuộc của các artifact và tính ra **đồ thị phụ thuộc** (*dependency graph*) mà dự án thực sự dùng. Hiểu đồ thị này giúp giải thích vì sao một JAR xuất hiện trong classpath, vì sao Maven chọn phiên bản khác với dự đoán và vì sao build bị lỗi khi nâng cấp một dependency tưởng như không liên quan.

Bài này phân biệt **phụ thuộc trực tiếp** (*direct dependency*) với **phụ thuộc bắc cầu** (*transitive dependency*), mô tả cách Maven thu thập, chọn lọc và hòa giải đồ thị, rồi thực hành với ví dụ Java 17 gồm ba module. Các vấn đề như `scope`, `optional`, `exclusions`, `dependencyManagement` và `dependency:tree` được giải thích trong phạm vi chúng ảnh hưởng tới đồ thị.

> Quy tắc nhớ nhanh: dependency được khai báo trong `<dependencies>` của POM hiện tại là trực tiếp; dependency đi vào qua POM của một dependency khác là bắc cầu. **Đồ thị được Maven sử dụng không nhất thiết giữ nguyên mọi nhánh và mọi phiên bản từng xuất hiện trong các POM nguồn.** Maven còn xét scope, tùy chọn optional, exclusions, quản lý phiên bản và hòa giải xung đột.

## 1. Dependency Maven là gì?

Trong Maven, phần lớn dependency được mô tả bằng tọa độ artifact, thường có ba thành phần chính `groupId:artifactId:version`. Khi cần còn có `type`, `classifier` và `scope`.

Ví dụ một thư viện Java được dùng ở thời điểm biên dịch:

```xml
<dependencies>
    <dependency>
        <groupId>org.example</groupId>
        <artifactId>text-utils</artifactId>
        <version>2.4.0</version>
        <scope>compile</scope>
    </dependency>
</dependencies>
```

Đây chỉ là **đoạn XML trong `<project>`**, chưa phải POM độc lập. `org.example:text-utils:2.4.0` là tọa độ minh họa, không khẳng định có artifact thật tại Maven Central.

Các thành phần quan trọng:

| Trường | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `groupId` | Nhóm định danh. | Thường theo namespace tổ chức. |
| `artifactId` | Tên artifact trong nhóm. | Dùng cùng groupId và version để xác định artifact. |
| `version` | Phiên bản mong muốn hoặc được quản lý. | Có thể bị quy tắc quản lý/hòa giải ảnh hưởng đối với phụ thuộc bắc cầu. |
| `type` | Kiểu artifact, thường mặc định `jar`. | Không phải dependency nào cũng là JAR. |
| `classifier` | Biến thể artifact khi được công bố. | Ví dụ artifact nguồn hoặc bản chuyên biệt. |
| `scope` | Phạm vi phụ thuộc khi compile, test, runtime và truyền qua các nhánh. | `compile` là scope mặc định nếu bỏ qua. |
| `optional` | Đánh dấu dependency không tự truyền tiếp tới người tiêu thụ artifact này. | Có tác dụng đối với dự án phụ thuộc vào thư viện đó. |
| `exclusions` | Ngăn một artifact đi qua nhánh dependency đã chỉ định. | Không tự loại bỏ artifact ở các nhánh khác. |

Maven không chỉ cần file JAR: để biết một thư viện phụ thuộc vào những gì, nó còn sử dụng **POM metadata** của artifact được giải quyết từ reactor/local repository/remote repository phù hợp. Vì vậy một JAR tồn tại trên ổ đĩa không có nghĩa Maven đã có thông tin dependency đúng nếu POM liên quan bị thiếu hoặc sai.

## 2. Phụ thuộc trực tiếp là gì?

**Phụ thuộc trực tiếp** là artifact được dự án hiện tại liệt kê trong `<dependencies>` của mô hình POM có hiệu lực. Phụ thuộc cũng có thể được **kế thừa** từ `<dependencies>` của parent; khi đó nó nằm ở cấp trực tiếp của mô hình con dù dòng khai báo đến từ parent.

Giả sử dự án `shop-app` có:

```xml
<dependencies>
    <dependency>
        <groupId>org.example</groupId>
        <artifactId>order-service</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
```

Với dự án này, `order-service` là dependency trực tiếp. Maven có thể đưa artifact tương ứng lên classpath theo scope và lifecycle đang sử dụng.

Điều này **không đồng nghĩa mã nguồn nhất thiết dùng lớp Java của mọi dependency trực tiếp**. Một dependency có thể chỉ cần lúc runtime; một khai báo cũ có thể không còn được sử dụng. Muốn biết lớp nào được dùng và dependency nào dư thừa, cần phân tích bytecode hoặc mã nguồn bằng công cụ phù hợp, thay vì nhìn riêng danh sách POM.

**Thực hành tốt:** nếu mã nguồn của một module trực tiếp `import` và sử dụng API của thư viện C, nên khai báo C là dependency trực tiếp, thay vì chỉ dựa vào việc thư viện B tình cờ mang C vào bằng phụ thuộc bắc cầu.

## 3. Phụ thuộc bắc cầu là gì?

**Phụ thuộc bắc cầu** là dependency được Maven tìm thấy khi lần theo dependency của một artifact đã được dự án sử dụng.

```text
shop-app
    |
    +-- order-service              (trực tiếp)
            |
            +-- domain-model       (bắc cầu, cấp 2)
                    |
                    +-- value-codec (bắc cầu, cấp 3)
```

Nếu `shop-app` khai báo `order-service`, còn POM của `order-service` khai báo `domain-model`, Maven có thể đưa `domain-model` vào tập dependencies của `shop-app` mà không cần dòng khai báo thứ hai. Tương tự, `value-codec` có thể xuất hiện qua `domain-model`.

Một **cạnh** trong đồ thị biểu thị “artifact bên trái có dependency đến artifact bên phải”. Đồ thị có thể có nhiều đường dẫn tới cùng một artifact. Khi trình bày dạng **cây**, một nút có thể được lặp hoặc bị ẩn khi phiên bản khác bị loại; biểu diễn cây là một cách nhìn của đồ thị, không có nghĩa đồ thị thật luôn là một cây không có nhánh hội tụ.

Các khái niệm:

- **Root:** dự án đang phân tích, ví dụ `shop-app`.
- **Node:** artifact hoặc project với tọa độ, scope và metadata liên quan.
- **Edge:** một khai báo phụ thuộc.
- **Depth (độ sâu):** số cạnh từ dự án gốc đến dependency theo một đường đi.
- **Direct dependency:** thường ở độ sâu 1.
- **Transitive dependency:** được tìm thấy qua đường đi từ độ sâu 2 trở lên.
- **Resolved dependency graph:** đồ thị sau khi Maven áp dụng các quy tắc giải quyết, phạm vi và xung đột.

Maven không có giới hạn số “tầng” bắc cầu cố định; nhưng nếu metadata tạo vòng phụ thuộc không hợp lệ, việc giải quyết có thể thất bại. Dependency graph là công cụ để tìm quan hệ giữa các artifact, không phải “bản đồ import từng lớp Java”.

## 4. Maven hình thành đồ thị phụ thuộc như thế nào?

Ở mức khái niệm, quá trình giải quyết dependencies của một project có thể hiểu như sau:

```text
                  POM hiện tại
                      |
                      v
          Xây dựng effective POM
           parent + profiles + ...
                      |
                      v
         Lấy các dependencies gốc
          và dependencyManagement
                      |
                      v
           Giải quyết artifact/POM
           của các dependency gốc
                      |
                      v
          Lần theo dependency metadata
          để thu thập những nút bắc cầu
                      |
                      v
        Áp dụng scopes, optional, exclusions
             và quản lý phiên bản
                      |
                      v
          Hòa giải phiên bản cạnh tranh
          và hoàn thiện đồ thị được dùng
                      |
                      v
          Lập classpath theo từng mục tiêu
          compile / test / runtime / plugin
```

Sơ đồ này là **mô hình giải thích**, không phải lời khẳng định về thứ tự từng phương thức nội bộ của Maven Resolver. Trong thực tế, các bước thu thập, biến đổi, hòa giải và chọn scope có quan hệ với nhau và có thể được thực hiện qua nhiều giai đoạn.

Những đầu vào tác động mạnh tới kết quả:

1. **Effective POM:** dependencies khai báo trực tiếp và kế thừa từ parent, các profile đang kích hoạt, thông tin `dependencyManagement`.
2. **POM của thư viện được tải:** mỗi artifact có thể có parent, dependencies, optional, exclusions và dependency management của chính nó.
3. **Repository settings:** mirror, local cache, repository truy cập được, quyền và trạng thái mạng.
4. **Scope/type/classifier:** cùng một artifactId có thể có loại hoặc biến thể khác nhau và không phải scope nào cũng được truyền bắc cầu.
5. **Quy tắc chọn phiên bản:** khi có nhiều đường dẫn tới cùng artifact với các phiên bản cạnh tranh, Maven phải chọn một phiên bản được dùng.
6. **Lệnh Maven/goal:** classpath cần cho compile, test và runtime không hoàn toàn giống nhau.

Vì thế, nhìn một POM con **chưa đủ để liệt kê toàn bộ JAR cuối cùng**. Hãy chạy `mvn dependency:tree` trong đúng module và đúng profile của build thật để thấy kết quả Maven đã giải quyết.

## 5. Ví dụ đầy đủ: ba module Java 17 và một nhánh bắc cầu

Dự án mẫu có ba module:

- `api-contract`: định nghĩa cách tạo thông điệp.
- `business-service`: dùng `api-contract` để triển khai dịch vụ.
- `cli-app`: gọi `business-service`.

**Quan hệ dependency:**

```text
cli-app
    |
    +-- business-service      (trực tiếp với cli-app)
             |
             +-- api-contract (bắc cầu với cli-app)
```

Từ góc nhìn `business-service`, `api-contract` lại là dependency **trực tiếp**. Tính trực tiếp/bắc cầu **luôn phụ thuộc dự án gốc đang được xét**.

### 5.1. Cây thư mục

```text
dependency-graph-demo/
├── pom.xml
├── api-contract/
│   ├── pom.xml
│   └── src/main/java/io/example/contract/GreetingContract.java
├── business-service/
│   ├── pom.xml
│   └── src/main/java/io/example/service/BusinessService.java
└── cli-app/
    ├── pom.xml
    └── src/main/java/io/example/app/App.java
```

Bốn tệp `pom.xml` hợp thành một Maven reactor có parent và ba module. Các tệp Java dưới `src/main/java` tương ứng đúng với package.

### 5.2. Parent POM: `dependency-graph-demo/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>io.example.training</groupId>
    <artifactId>dependency-graph-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>api-contract</module>
        <module>business-service</module>
        <module>cli-app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
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

Ở đây `packaging=pom` phù hợp với parent/aggregator. `<modules>` quyết định những module nào được Maven reactor thu thập khi chạy từ root, còn `<parent>` trong mỗi module sẽ quyết định quan hệ kế thừa. Đó là **hai cơ chế khác nhau**.

Parent không khai báo dependency trực tiếp giữa các module, vì không phải mọi module đều dùng mọi thư viện khác. Quan hệ trực tiếp sẽ được đặt trong POM của module thực sự sử dụng.

### 5.3. Module C: `api-contract/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>io.example.training</groupId>
        <artifactId>dependency-graph-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>api-contract</artifactId>
</project>
```

`api-contract` không khai báo dependency bên ngoài. Đây là nút cuối của đường dẫn phụ thuộc trong ví dụ.

Tệp `api-contract/src/main/java/io/example/contract/GreetingContract.java`:

```java
package io.example.contract;

public final class GreetingContract {
    private GreetingContract() {
    }

    public static String format(String name) {
        return "Hello, " + name + "!";
    }
}
```

Lớp này không phụ thuộc thư viện ngoài JDK.

### 5.4. Module B: `business-service/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>io.example.training</groupId>
        <artifactId>dependency-graph-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>business-service</artifactId>

    <dependencies>
        <dependency>
            <groupId>io.example.training</groupId>
            <artifactId>api-contract</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

`api-contract` là **trực tiếp** đối với `business-service`. Không khai báo `scope` nghĩa là `compile` theo mặc định.

Tệp `business-service/src/main/java/io/example/service/BusinessService.java`:

```java
package io.example.service;

import io.example.contract.GreetingContract;

public final class BusinessService {
    private BusinessService() {
    }

    public static String greet(String name) {
        return GreetingContract.format(name);
    }
}
```

Dòng `import io.example.contract.GreetingContract;` thể hiện đúng việc module này dùng mã trong `api-contract`. Nó cần dependency trực tiếp để biên dịch.

### 5.5. Module A: `cli-app/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>io.example.training</groupId>
        <artifactId>dependency-graph-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>cli-app</artifactId>

    <dependencies>
        <dependency>
            <groupId>io.example.training</groupId>
            <artifactId>business-service</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

POM này **không khai báo `api-contract`**. Nhưng metadata của `business-service` có dependency đến `api-contract`, vì vậy Maven có thể đưa `api-contract` vào đồ thị **bắc cầu** của `cli-app`.

Tệp `cli-app/src/main/java/io/example/app/App.java`:

```java
package io.example.app;

import io.example.service.BusinessService;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(BusinessService.greet("Maven"));
    }
}
```

`App` trực tiếp dùng `BusinessService`; không có `import` tới `GreetingContract`. Nhưng khi chạy, `BusinessService` cần lớp từ `api-contract`, nên dependency bắc cầu đó vẫn cần nằm trong classpath runtime.

### 5.6. Biên dịch và chạy

Yêu cầu: JDK 17 trở lên, Maven tương thích và quyền tải các plugin Maven khi local cache chưa có. Đứng ở thư mục `dependency-graph-demo`:

```bash
mvn -version
mvn -B -ntp clean package
```

Từ cùng thư mục root, chạy bằng classpath chứa cả ba module:

Linux/macOS:

```bash
java -cp "cli-app/target/classes:business-service/target/classes:api-contract/target/classes" io.example.app.App
```

Windows PowerShell:

```powershell
java -cp "cli-app\target\classes;business-service\target\classes;api-contract\target\classes" io.example.app.App
```

**Stdout của chương trình Java**, khi chạy với các file trên, là chính xác:

```text
Hello, Maven!
```

Dấu phân tách classpath là `:` trên Linux/macOS và `;` trên Windows. Lệnh trên dùng thư mục `target/classes` cho dễ quan sát; khi chạy ứng dụng thực tế, classpath cần chứa artifact và dependency runtime phù hợp. Maven đóng gói JAR mặc định **không tự tạo fat/uber JAR** chứa mọi dependency.

Nếu loại `api-contract` khỏi classpath thủ công nhưng vẫn gọi `BusinessService.greet`, chương trình có thể gặp `NoClassDefFoundError` hoặc lỗi nạp lớp liên quan. Đó là biểu hiện của một dependency runtime cần thiết bị thiếu.

### 5.7. Vì sao ví dụ có thể build dù POM của app không nhắc `api-contract`?

Maven thấy `cli-app -> business-service -> api-contract`. Do hai cạnh là `compile` scope mặc định, `api-contract` được truyền đến compile và runtime classpath của `cli-app`.

Tuy nhiên, nếu `App.java` bắt đầu **import trực tiếp `io.example.contract.GreetingContract`**, nên thêm `api-contract` vào `<dependencies>` của `cli-app`. Lý do: mã nguồn app lúc này trực tiếp phụ thuộc API của contract; khai báo rõ giúp bảo vệ dự án nếu một ngày `business-service` thay đổi graph của nó.

## 6. Dùng `dependency:tree` để đọc đồ thị thực tế

Maven Dependency Plugin có goal `dependency:tree`. Nó cho biết các dependency và đường đi từ project gốc, theo kết quả Maven giải quyết.

Ở root ví dụ, chạy:

```bash
mvn -B -ntp clean install
```

Lệnh `install` ở đây giúp đưa các artifact module được build vào **local Maven repository**, để sau đó chạy `dependency:tree` riêng cho POM app mà không phụ thuộc vào việc plugin có thể nhìn thấy artifact reactor ở một invocation độc lập. `install` sửa local repository của máy, **không phải deploy lên remote server**.

Sau khi install thành công:

```bash
mvn -f cli-app/pom.xml dependency:tree
```

Một **đoạn cây minh họa** của phần dependencies được chọn trông như sau; plugin có thể in thêm header, thông tin plugin và thời gian:

```text
io.example.training:cli-app:jar:1.0.0
\- io.example.training:business-service:jar:1.0.0:compile
   \- io.example.training:api-contract:jar:1.0.0:compile
```

Độ thụt đầu dòng cho biết `business-service` nằm ngay dưới `cli-app`, còn `api-contract` đi qua `business-service`.

**Lưu ý:** đầu ra của `dependency:tree` là đồ thị phụ thuộc của **project đang chọn**, không phải toàn bộ biểu đồ tất cả module của một repository. Nếu chạy goal này ở một reactor nhiều module, Maven có thể chạy goal cho từng module và in nhiều cây khác nhau. Muốn phân tích `cli-app`, chỉ định đúng POM bằng `-f`.

### 6.1. Tìm lý do một artifact có mặt

Giả sử muốn biết `api-contract` xuất hiện vì nhánh nào:

```bash
mvn -f cli-app/pom.xml dependency:tree -Dincludes=io.example.training:api-contract
```

Tham số `includes` của Dependency Plugin dùng bộ lọc theo tọa độ artifact. Kết quả có thể giữ các nút tổ tiên cần thiết để thể hiện đường đi; không nên mong toàn bộ subtree khác vẫn xuất hiện. Để tìm kiếm dạng phức tạp hơn, có thể dùng cú pháp `groupId:artifactId:type:version` với wildcard được plugin hỗ trợ.

Có thể giới hạn scope:

```bash
mvn -f cli-app/pom.xml dependency:tree -Dscope=runtime
```

Cờ `scope` ở đây là **bộ lọc của plugin** cho cây được giải quyết, không sửa `scope` được khai báo trong POM. Kiểm tra command line và phiên bản plugin nếu đầu ra khác kỳ vọng.

### 6.2. Xuất đồ thị thành file để phân tích

Goal này hỗ trợ dạng `text` mặc định; các phiên bản plugin hiện đại còn hỗ trợ `dot`, `graphml`, `tgf` và `json` (JSON từ Dependency Plugin 3.7.0 trở lên).

Ví dụ:

```bash
mvn -f cli-app/pom.xml dependency:tree -DoutputType=dot -DoutputFile=dependency-tree.dot
```

Đây là **đầu ra DOT chứa dữ liệu đồ thị**, không phải hình PNG/SVG. Muốn xem dưới dạng hình có thể dùng Graphviz hoặc công cụ hỗ trợ DOT. File output nên được tạo ở nơi bạn quản lý; vị trí tương đối của file có thể phụ thuộc project base directory và cách goal xử lý output.

Nếu dùng JSON để xử lý tự động, cần plugin có hỗ trợ `outputType=json`:

```bash
mvn -f cli-app/pom.xml dependency:tree -DoutputType=json -DoutputFile=dependency-tree.json
```

Không nên viết parser dựa vào khoảng trắng cố định của text output nếu cần tích hợp máy-máy ổn định. Các định dạng cấu trúc có thể thuận tiện hơn; dù vậy luôn kiểm tra phiên bản plugin, quy tắc scope và dữ liệu đang được giải quyết.

### 6.3. Thấy dependency nào bị bỏ khi xung đột?

Các bản Maven Dependency Plugin có tham số `verbose` để hiển thị thêm những nút bị bỏ (*omitted nodes*) do hòa giải trùng lặp hoặc xung đột, trong phạm vi plugin hỗ trợ:

```bash
mvn -f cli-app/pom.xml dependency:tree -Dverbose
```

Khi đọc những dòng có chữ “omitted for conflict” hoặc “omitted for duplicate”, đó là lời giải thích vì sao một đường đi **không được giữ như một artifact riêng trong cây cuối**. Cú pháp dòng log có thể thay đổi theo phiên bản plugin; không suy ra Maven đang tải hai phiên bản cùng lúc chỉ vì cả hai từng xuất hiện trong phần chẩn đoán.

Maven có thể cần tải POM/JAR từ remote repository khi local cache thiếu. Nếu goal báo `Could not resolve dependencies` thì đó là lỗi resolution thật, không phải bằng chứng rằng cây dependency không tồn tại.

## 7. Khi hai nhánh yêu cầu hai phiên bản của cùng một artifact

Đây là **dependency conflict** hay xung đột phiên bản. Một thư viện có thể yêu cầu `codec:1.0`, thư viện khác cần `codec:2.0`; Maven phải quyết định phiên bản nào được dùng trong đồ thị của project.

Ví dụ (tọa độ giản lược, không phải output plugin):

```text
app
├── adapter-a:1.0
│   └── codec:2.0
└── adapter-b:1.0
    └── helper:1.0
        └── codec:1.0
```

Đường `app -> adapter-a -> codec` có **hai cạnh**; đường `app -> adapter-b -> helper -> codec` có **ba cạnh**. Với quy tắc hòa giải thông thường của Maven, **“nearest definition”** chọn phiên bản gần root hơn, ở đây là `codec:2.0`.

Điểm cần nhớ: Maven **không đơn giản chọn phiên bản lớn nhất hoặc mới nhất**. Khoảng cách từ root quan trọng hơn số version trong quy tắc mediation mặc định.

### 7.1. Nếu độ sâu bằng nhau, khai báo đầu thắng

```text
app
├── adapter-a:1.0
│   └── codec:2.0
└── adapter-b:1.0
    └── codec:1.0
```

Hai đường đều dài hai cạnh. Với thứ tự dependency của app như trong sơ đồ, **khai báo đầu tiên thắng** khi độ sâu bằng nhau, nên `codec:2.0` có thể được chọn. Nếu đảo thứ tự các khai báo cùng độ sâu, kết quả mediation có thể đổi.

Vì vậy thứ tự dependency đôi khi ảnh hưởng kết quả khi có xung đột cùng độ sâu. Tuy nhiên **không nên dựa vào reorder như một cách quản lý version lâu dài**; lựa chọn phiên bản nên được khai báo rõ khi cần ổn định.

### 7.2. Khai báo dependency trực tiếp để chọn phiên bản

Nếu app thực sự cần `codec:2.0`, có thể khai báo trực tiếp:

```xml
<dependencies>
    <dependency>
        <groupId>org.example</groupId>
        <artifactId>codec</artifactId>
        <version>2.0</version>
    </dependency>
</dependencies>
```

Đây là đoạn XML minh họa. Đường trực tiếp `app -> codec:2.0` có độ sâu 1, thường gần hơn các đường bắc cầu. Nhưng **chọn 2.0 không chứng minh các thư viện ở đường khác tương thích API/ABI**. Phải build, test, và kiểm tra tương thích thực tế.

Một artifact dùng phiên bản cao hơn không tự động “tốt hơn” cho mọi thư viện. Sai khác giữa API mà từng dependency được biên dịch và API có trong classpath runtime có thể gây lỗi như `NoSuchMethodError`, `ClassNotFoundException` hoặc `NoClassDefFoundError`.

## 8. `dependencyManagement`: quản lý phiên bản mà không tự thêm dependency

Có thể đặt quyết định phiên bản vào `<dependencyManagement>` của POM hiện tại hoặc parent:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>codec</artifactId>
            <version>2.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là một **quy tắc quản lý**: khi `codec` được tham chiếu trong ngữ cảnh phù hợp (trực tiếp thiếu version hoặc bắc cầu), Maven có thể dùng version được quản lý. **Chỉ khai báo ở `dependencyManagement` không làm `codec` tự xuất hiện trong classpath** nếu không có dependency thực sự cần nó.

Phân biệt:

| Cơ chế | Tác động |
| --- | --- |
| `<dependencies>` | Khai báo những dependency dự án thực sự sử dụng. |
| `<dependencyManagement>` | Tập trung các quy tắc về version/scope/metadata dependency khi chúng được tham chiếu phù hợp. |
| `<pluginManagement>` | Quản lý cấu hình phiên bản plugin khi plugin được sử dụng; không quản lý graph thư viện của dự án. |
| `<modules>` | Thu thập các module vào Maven reactor; không tự tạo cạnh dependency giữa chúng. |
| `<parent>` | Kế thừa mô hình POM cha; không có nghĩa parent là thư viện Java trên classpath. |

Với **transitive dependencies**, `dependencyManagement` ở dự án root có thể ưu tiên hơn quy tắc nearest-definition trong việc xác định phiên bản. Nhưng đối với một dependency đã khai báo trực tiếp version rõ ràng, không nên mặc định rằng một mục trong `dependencyManagement` sẽ âm thầm ghi đè mọi khai báo trực tiếp. Kiểm tra effective POM và `dependency:tree`.

**Giới hạn quan trọng:** `dependencyManagement` dành cho **project dependencies**, không áp đặt phiên bản lên dependencies nội bộ của Maven plugins. Plugin classpath là một ngữ cảnh giải quyết riêng.

### 8.1. Quản lý các module cùng một phiên bản

Trong ví dụ đa module, parent có thể quản lý version các artifact nội bộ:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.example.training</groupId>
            <artifactId>api-contract</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>io.example.training</groupId>
            <artifactId>business-service</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn thay thế/đề xuất cho parent POM**, không phải toàn bộ POM. Khi cả ba module có cùng version, module con có thể khai báo dependency tới `api-contract` hoặc `business-service` mà không lặp version nếu management phù hợp. **Nếu module được version độc lập**, dùng `${project.version}` của bên phụ thuộc có thể trỏ nhầm phiên bản; khi đó cần cơ chế quản lý version riêng.

## 9. Import BOM để quản lý tập phiên bản

Một **BOM** (*Bill of Materials*) Maven thường là artifact đóng gói `pom` có `dependencyManagement` liệt kê các phiên bản tương thích. Project có thể import BOM trong `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>example-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

`org.example:example-bom:1.0.0` chỉ là tọa độ minh họa. `type=pom` và `scope=import` ở đây có nghĩa nhập danh sách managed dependencies từ BOM theo quy tắc Maven.

**Import BOM không tự đưa tất cả thư viện trong BOM vào ứng dụng.** Từng module vẫn khai báo những dependencies cần sử dụng trong `<dependencies>`. BOM giúp các dependency đó nhận version phù hợp, giảm xung đột khi hệ sinh thái gồm nhiều artifact liên quan.

Khi import nhiều BOM có cùng mục version hoặc khai báo management ở POM hiện tại, quy tắc ưu tiên của Maven quan trọng. Không suy ra version cuối chỉ dựa vào BOM đầu tiên nhìn thấy; kiểm tra effective POM và dependency tree.

## 10. Scope quyết định những dependency nào đi qua các nhánh

Mỗi dependency có `scope` để Maven xác định nó thuộc classpath nào và có truyền bắc cầu hay không.

| Scope | Vai trò thông dụng | Tham gia classpath / khả năng truyền |
| --- | --- | --- |
| `compile` (mặc định) | Cần để biên dịch và thường cả runtime. | Có mặt trong compile, test và runtime classpath; có thể truyền bắc cầu. |
| `provided` | Cần để compile/test, nhưng container/JDK dự kiến cung cấp lúc chạy. | Không có trong runtime classpath của dự án; không truyền tiếp theo cách như compile. |
| `runtime` | Chỉ cần khi chạy, không cần cho main compile. | Có trong runtime và test classpath; có thể truyền bắc cầu theo bảng. |
| `test` | Chỉ dùng khi biên dịch/chạy tests. | Có trong test classpath của project; không truyền tiếp tới project phụ thuộc như compile. |
| `system` | JAR chỉ định bằng đường dẫn máy cục bộ. | Cơ chế cũ, khó tái lập; Maven không tải JAR từ repository, không khuyến nghị. |
| `import` | Chỉ dùng với dependency `type=pom` trong `dependencyManagement`. | Nhập managed dependencies, không tạo cạnh dependency JAR thông thường. |

Ví dụ `cli-app` có dependency trực tiếp `business-service` scope `compile`. Nếu `business-service` phụ thuộc `api-contract` scope `compile`, Maven đưa `api-contract` vào classpath compile/runtime của app. Nếu `business-service` phụ thuộc một thư viện chỉ scope `test`, dependency test này **không tự truyền tới app**.

### 10.1. Bảng truyền scope qua hai cạnh

Bảng quy tắc Maven được đọc như sau: A là dependency **trực tiếp** của project; B là dependency của A. Ô giao nhau cho biết **scope hiệu lực của B** trong project; dấu `—` nghĩa là B bị loại ở đường đi đó.

| Scope của A ở project | B: compile | B: provided | B: runtime | B: test |
| --- | --- | --- | --- | --- |
| `compile` | `compile` | — | `runtime` | — |
| `provided` | `provided` | — | `provided` | — |
| `runtime` | `runtime` | — | `runtime` | — |
| `test` | `test` | — | `test` | — |

Đây là bảng scope transitivity của hướng dẫn Maven. Phải đọc theo **thứ tự cạnh**, không chỉ nhìn scope của nút B một cách độc lập.

Ví dụ:

```text
app --(compile)--> service --(runtime)--> jdbc-driver
```

`jdbc-driver` có scope hiệu lực `runtime` trong `app`: không bắt buộc có trong main compile classpath nhưng cần trong runtime/test khi ứng dụng chạy hoặc kiểm thử.

Một trường hợp khác:

```text
app --(compile)--> service --(test)--> junit
```

`junit` từ test scope của service **không tự trở thành dependency của app**. Nếu app có test riêng cần JUnit, app phải khai báo dependency test của mình.

**Cẩn thận với provided:** Một thư viện khai báo `provided` với giả định môi trường chạy sẽ cung cấp nó. Chỉ thay scope để “làm cho build pass” có thể dẫn đến lỗi khi chạy ở môi trường thực tế.

### 10.2. Phạm vi compile, test và runtime không phải ba đồ thị giống nhau

Một dự án có thể có:
- Thư viện API dùng lúc compile và runtime.
- Driver database chỉ cần runtime.
- Thư viện assertion chỉ cần trong test.
- Servlet API được container cung cấp theo hợp đồng deployment.

Vì thế, một cây dependency được lọc theo scope không nhất thiết cho thấy tất cả artifact có thể được Maven giải quyết trong các bối cảnh khác. Khi debug `ClassNotFoundException` lúc chạy, hãy xem **runtime classpath**, không chỉ nhìn những gì compiler dùng.

## 11. `optional`: dependency của thư viện nhưng không tự truyền tới consumer

Giả sử `business-service` hỗ trợ một tiện ích tùy chọn `advanced-formatter`:

```xml
<dependencies>
    <dependency>
        <groupId>org.example</groupId>
        <artifactId>advanced-formatter</artifactId>
        <version>1.0.0</version>
        <optional>true</optional>
    </dependency>
</dependencies>
```

Đây là đoạn XML minh họa. Đối với chính `business-service`, dependency đó vẫn có thể cần khi compile/test những phần code tương ứng. Nhưng khi `cli-app` phụ thuộc vào `business-service`, Maven **không tự kéo `advanced-formatter` qua nhánh bắc cầu đó** chỉ vì nó được khai báo optional.

Nếu app thật sự cần tính năng tùy chọn, app có thể khai báo `advanced-formatter` là dependency trực tiếp của mình.

`optional` không thay thế việc thiết kế API: nếu API công khai hoặc luồng thực thi mặc định của thư viện B luôn cần lớp C, đánh dấu C optional có thể làm app dùng B gặp lỗi thiếu lớp. Trước khi thêm optional, phải xem C có thực sự chỉ cần cho một tính năng tự chọn hay không.

**Phân biệt:**

- `optional=true` do **nhà phát triển thư viện B** đặt cho dependency C để nói với consumer của B rằng C không được tự truyền tiếp.
- `exclusions` do **bên tiêu thụ A** khai báo trên nhánh A -> B để không nhận C qua nhánh đó.

Hai cơ chế giải quyết hai nhu cầu khác nhau.

## 12. `exclusions`: chặn một nhánh bắc cầu cụ thể

Nếu `cli-app` không muốn nhận `api-contract` qua `business-service`, cú pháp minh họa là:

```xml
<dependencies>
    <dependency>
        <groupId>io.example.training</groupId>
        <artifactId>business-service</artifactId>
        <version>1.0.0</version>
        <exclusions>
            <exclusion>
                <groupId>io.example.training</groupId>
                <artifactId>api-contract</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
</dependencies>
```

**Đây là ví dụ về cơ chế, không phải thay đổi khuyến nghị cho code mẫu ở mục 5.** Trong code thực hành, `BusinessService` gọi lớp `GreetingContract`, nên loại `api-contract` khỏi runtime classpath của app có thể khiến app lỗi khi chạy. Chỉ exclusion khi bạn đã xác minh thư viện bị loại không còn cần thiết hoặc có lựa chọn khác tương thích.

Các điểm quan trọng:

1. `<exclusion>` thường nhận diện artifact bằng `groupId` và `artifactId`; không đặt `<version>` để biểu diễn “chỉ loại đúng một version” trong cú pháp exclusion tiêu chuẩn.
2. Exclusion gắn vào **một cạnh dependency**. Nếu artifact C vẫn xuất hiện qua cạnh A -> D -> C, nó vẫn có thể được giữ.
3. Nếu muốn buộc một phiên bản khác của C mà vẫn dùng C, `dependencyManagement` hoặc dependency trực tiếp thường phù hợp hơn việc exclusion rồi thêm JAR thủ công.
4. Exclusion không xóa artifact khỏi remote repository hoặc local cache; nó thay đổi việc Maven đưa artifact vào đồ thị của **project này**.
5. Không lạm dụng exclusion để “đánh bại” dependency convergence mà bỏ qua kiểm thử; có thể gây lỗi nạp lớp lúc runtime.

Ví dụ đồ thị có hai nhánh:

```text
app
├── web-adapter
│   └── codec             <- nhánh bị exclude trên web-adapter
└── batch-adapter
    └── codec             <- nhánh này vẫn có thể còn
```

Nếu app thực sự không muốn `codec` xuất hiện, phải tìm và xử lý **mọi nhánh liên quan**, đồng thời đánh giá tính tương thích. `dependency:tree -Dincludes=...` giúp định vị đường đi.

## 13. Phân biệt dependency graph với reactor/build order

Dự án Maven nhiều module có thể có hai loại quan hệ:

1. **Aggregation:** POM root có `<modules>` liệt kê module nào thuộc reactor.
2. **Artifact dependency:** POM của module A có `<dependency>` trỏ tới artifact của module B.

Trong ví dụ, root liệt kê `api-contract`, `business-service` và `cli-app`. Đây là aggregation. Còn `cli-app -> business-service -> api-contract` là graph phụ thuộc thực sự, được tạo từ `<dependencies>`.

Maven reactor sử dụng những quan hệ dự án được nhận diện để xác định thứ tự build phù hợp. Thường cần build `api-contract` trước `business-service`, rồi `cli-app`. **Thứ tự thư mục và thứ tự `<module>` không thay thế cạnh dependency**; nếu app cần lớp của module khác, nó phải có dependency tương ứng (trực tiếp hoặc bắc cầu theo quy tắc).

Ví dụ chọn một module và những upstream modules cần thiết:

```bash
mvn -pl :cli-app -am clean package
```

`-pl` (*projects list*) chọn project trong reactor theo selector, `-am` (*also make*) thêm các module reactor mà project được chọn cần để build theo các quan hệ đã biết. Đây là cách build một phần reactor. Nếu chỉ dùng `-pl :cli-app` mà thiếu artifact upstream trong local repo, Maven có thể không giải quyết được dependency trong invocation đó.

**Không nhầm `dependency:tree` với danh sách module.** Một parent aggregator có thể liệt kê ba module nhưng không trực tiếp phụ thuộc các artifact JAR của chúng; graph dependencies của parent POM có thể gần như trống, còn graph của `cli-app` lại có hai thư viện.

## 14. Khi nào nên khai báo bắc cầu thành trực tiếp?

Giả sử app trước đây chỉ gọi `BusinessService.greet`, nhưng giờ code bắt đầu dùng trực tiếp:

```java
import io.example.contract.GreetingContract;
```

Đây là một dòng Java minh họa cần nằm trong lớp Java hợp lệ; nó không phải file độc lập. Nếu một thành phần app trực tiếp gọi API từ `GreetingContract`, nên khai báo `api-contract` trực tiếp trong POM app:

```xml
<dependency>
    <groupId>io.example.training</groupId>
    <artifactId>api-contract</artifactId>
    <version>1.0.0</version>
</dependency>
```

Lợi ích:

- POM thể hiện **sự phụ thuộc thật của mã nguồn app**, không che qua dịch vụ khác.
- Nếu `business-service` bỏ hoặc thay dependency `api-contract`, app vẫn khai báo những gì chính mình cần.
- Người bảo trì dễ hiểu lý do sử dụng artifact và thực hiện nâng cấp.
- Công cụ phân tích dependency có thể kiểm tra các hiện tượng “used undeclared” và “unused declared”.

Goal hỗ trợ trong Maven Dependency Plugin:

```bash
mvn -f cli-app/pom.xml dependency:analyze
```

Nó phân tích các dependency đã biên dịch và cố phát hiện artifact được dùng nhưng chưa khai báo trực tiếp, hoặc được khai báo mà có vẻ không dùng. Tuy nhiên phân tích thường dựa trên bytecode/static inspection: dùng reflection, ServiceLoader, plugin framework hoặc tài nguyên runtime có thể khiến kết quả sai lệch. **Không tự động xóa mọi dependency bị báo unused** mà không kiểm tra cách ứng dụng sử dụng nó ở runtime.

Ngược lại, **không cần đưa toàn bộ dependency bắc cầu thành trực tiếp**: chỉ những artifact app thực sự phụ thuộc vào API/hành vi của chúng theo hợp đồng nên được khai báo trực tiếp. Việc nhân bản toàn bộ graph vào POM khiến quản lý khó và giảm lợi ích transitivity.

## 15. Xung đột phiên bản và vấn đề ổn định build

Khi một dự án lớn có nhiều nhánh transitive, quy tắc nearest-definition có thể chọn một version không đúng kỳ vọng nghiệp vụ. Nếu một thư viện được cập nhật và thay POM phụ thuộc của nó, graph của app có thể đổi **ngay cả khi POM app không sửa**.

Một số hướng giảm rủi ro:

1. **Quản lý phiên bản quan trọng** bằng `dependencyManagement` và/hoặc BOM phù hợp để tránh selection ngẫu nhiên theo độ sâu.
2. **Khai báo trực tiếp** những thư viện mà mã app dùng API.
3. **Pin phiên bản** thay vì dùng ranges động thiếu kiểm soát khi yêu cầu reproducible build.
4. **Kiểm tra dependency tree trước và sau khi nâng cấp** để biết artifact nào vào/ra, phiên bản nào thay đổi.
5. **Chạy unit/integration tests** và, nếu cần, kiểm thử tính tương thích runtime.
6. Dùng **Maven Enforcer Plugin** với quy tắc như `dependencyConvergence` hoặc `requireUpperBoundDeps` khi dự án cần chính sách nhất quán; cấu hình theo tổ chức và hiểu rõ trường hợp có ngoại lệ hợp lệ.
7. **Quản lý bảo mật dependency** bằng công cụ inventory/SBOM và quét lỗ hổng tương thích với hệ thống; việc nhìn graph không tự chứng minh một dependency an toàn.

### 15.1. Vì sao không nên chọn “version lớn nhất” một cách máy móc?

Phiên bản 3.0 của một thư viện có thể phá API so với 2.0. Nếu adapter A cần phương thức đã bị xóa, mediation chọn 3.0 có thể khiến build hoặc runtime thất bại. Việc chọn version phải dựa vào compatibility matrix và kiểm thử, không chỉ giá trị số trong `dependency:tree`.

### 15.2. Có thể có duplicate hoặc omitted nodes

Một artifact cùng tọa độ/phiên bản có thể được yêu cầu theo nhiều nhánh. Maven thường tránh đưa nhiều bản sao tương đương vào graph classpath. Chế độ `-Dverbose` có thể hiển thị những nhánh đã được bỏ để chẩn đoán. Đừng hiểu nhầm rằng sự xuất hiện của một nút trong phần verbose có nghĩa nó luôn được đưa vào classpath cuối.

### 15.3. Version range và SNAPSHOT

Dependency khai báo version range có thể giải quyết khác theo repository metadata và thời điểm truy cập nếu không có cơ chế kiểm soát tốt. SNAPSHOT cũng có thể được cập nhật với cùng base version. Để build có thể tái lập, cần quy trình quản lý phiên bản và repository artifacts nhất quán; không chỉ dựa vào nội dung POM.

## 16. Các lỗi phổ biến khi đọc đồ thị Maven

### Lỗi 1 — Cho rằng mọi dependency có trong POM thư viện đều được truyền bắc cầu

`provided`, `test`, `optional` và `exclusions` có thể làm một artifact không xuất hiện. Kiểm tra graph sau khi giải quyết thay vì sao chép danh sách từ POM của thư viện.

### Lỗi 2 — Tin Maven luôn chọn version mới nhất

Maven dependency mediation thường chọn **nearest definition**; nếu cùng độ sâu, khai báo đầu tiên thắng. `dependencyManagement` còn có thể điều chỉnh version transitive. Không dùng “phiên bản lớn nhất” làm quy tắc dự đoán.

### Lỗi 3 — Nhầm `dependencyManagement` với `dependencies`

Chỉ có management không tự đưa JAR lên classpath. Phải có dependency thực sự được khai báo hoặc được thu thập qua đường đi thích hợp.

### Lỗi 4 — Exclude một dependency nhưng không kiểm tra runtime

Nếu code của thư viện B vẫn cần C mà A loại C khỏi đường bắc cầu duy nhất, ứng dụng có thể gặp lỗi nạp lớp. Test và xem runtime classpath sau exclusion.

### Lỗi 5 — Đánh dấu `optional` cho thư viện luôn cần khi chạy

Optional không có nghĩa “tự tải khi dùng”. Consumer sẽ không tự nhận dependency optional; muốn sử dụng phải khai báo và cung cấp artifact phù hợp.

### Lỗi 6 — Dựa vào dependency transitive trong mã nguồn của chính project

Nếu mã app dùng trực tiếp lớp C nhưng chỉ khai báo B, một bản cập nhật B có thể làm app mất C. Khai báo C trực tiếp.

### Lỗi 7 — Chạy `dependency:tree` ở sai module

Một root POM `packaging=pom` có thể không có graph như module ứng dụng. Sử dụng `-f cli-app/pom.xml` hoặc module selector phù hợp.

### Lỗi 8 — Nhìn `<modules>` rồi cho rằng có dependency

Aggregation không tự tạo classpath. Chỉ khai báo module trong aggregator không khiến module này tự import được lớp từ module khác.

### Lỗi 9 — Cho rằng build thành công chứng minh runtime classpath đủ

Một dependency `provided` có thể cần container cung cấp. Một dependency bị exclusion hoặc chỉ có khi test có thể khiến ứng dụng chạy độc lập lỗi. Xác minh runtime/packaging/deployment thực tế.

### Lỗi 10 — Nhầm plugin dependency với project dependency

Maven plugins có classpath/phụ thuộc riêng. `dependencyManagement` của project không điều khiển mọi phiên bản JAR được plugin sử dụng. Khi debug lỗi plugin, kiểm tra cấu hình và dependency của plugin đó.

### Lỗi 11 — Không xem POM/metadata của artifact đã resolve

Nếu dependency có metadata lỗi, POM không tải được, parent không giải quyết được hoặc repository yêu cầu xác thực, Maven có thể không xây dựng được graph hoàn chỉnh. Kiểm tra repository settings và log resolution, không chỉ danh sách `dependencies`.

### Lỗi 12 — So sánh cây từ hai môi trường không cùng cấu hình

Profile, version, repository, local cache hoặc lệnh khác nhau có thể dẫn tới graph khác nhau. Khi so sánh local với CI, dùng cùng POM, JDK/Maven, profile và chính sách repository để giảm sai lệch.

## 17. Quy trình chẩn đoán dependency thực tế

**Bước 1. Xác định project và lệnh.** Xem root, module/POM, profile và phase mà CI thực thi. Một reactor có nhiều module sẽ có nhiều góc nhìn dependency khác nhau.

**Bước 2. Kiểm tra tọa độ và dependency trực tiếp.** Xem `<dependencies>` trong effective POM, bao gồm phần kế thừa từ parent; xem các phiên bản/điều kiện được quản lý trong `dependencyManagement`.

**Bước 3. Chạy `dependency:tree`.** Chọn đúng module, ví dụ:

```bash
mvn -f cli-app/pom.xml dependency:tree
```

Nếu các module nội bộ chưa có trong local repo, chạy build reactor/install phù hợp trước khi phân tích riêng; hoặc chạy cùng reactor với lựa chọn `-pl`/`-am` phù hợp.

**Bước 4. Tìm đúng nhánh.** Dùng `-Dincludes=groupId:artifactId` để tìm đường dẫn của một artifact đáng ngờ. Nhìn nhãn scope và độ sâu.

**Bước 5. Kiểm tra conflict, optional và exclusions.** Nếu version bị thay, xem mediation và dependencyManagement; nếu dependency biến mất, kiểm tra scope/optional/exclusion.

**Bước 6. Kiểm tra dependency thực sự được sử dụng.** Dùng `dependency:analyze` để có gợi ý về used undeclared/unused declared; đánh giá lại với kiến thức về runtime/reflection.

**Bước 7. Kiểm tra classpath/runtime.** Nếu gặp `ClassNotFoundException` hay `NoSuchMethodError`, xác định artifact và version có thực sự có ở môi trường chạy không. Một cây build thành công không đồng nghĩa đóng gói đã mang đủ runtime dependencies.

**Bước 8. Chốt version và chạy tests.** Điều chỉnh version/management/exclusions có chủ đích, so lại tree và xác minh chức năng ứng dụng. Với hệ thống phân phối, kiểm tra SBOM/security policy nếu được yêu cầu.

## 18. Bài tập tự kiểm tra

**Câu 1.** POM A khai báo B. POM B khai báo C. Trong project A, đâu là dependency trực tiếp và đâu là dependency bắc cầu?

**Đáp án:** B là dependency trực tiếp của A; C là dependency bắc cầu của A. Với B, C lại là trực tiếp.

**Câu 2.** Đường A -> B -> D:2.0 dài hai cạnh; đường A -> C -> E -> D:1.0 dài ba cạnh. Không có management hoặc khai báo trực tiếp khác. Maven thường chọn D phiên bản nào?

**Đáp án:** D:2.0 theo nguyên tắc nearest definition, vì đường đi ngắn hơn.

**Câu 3.** Hai đường A -> B -> D:2.0 và A -> C -> D:1.0 cùng độ sâu. B được khai báo trước C. Phiên bản D nào thường thắng khi không có management?

**Đáp án:** D:2.0 từ nhánh của B do khai báo đầu tiên thắng ở cùng độ sâu.

**Câu 4.** Parent có `dependencyManagement` quản lý `org.example:codec:2.0` nhưng app không khai báo hoặc nhận codec qua bất kỳ nhánh nào. Codec có tự nằm trong classpath không?

**Đáp án:** Không. Management chỉ cung cấp quy tắc cho dependency khi nó được tham chiếu phù hợp; nó không tự tạo dependency.

**Câu 5.** B có dependency C scope `test`. A phụ thuộc B scope `compile`. C có tự trở thành dependency của A không?

**Đáp án:** Không theo bảng truyền scope; dependency test của B không truyền sang A qua nhánh compile này.

**Câu 6.** B đánh dấu C `<optional>true</optional>`. A phụ thuộc B. A có tự nhận C không?

**Đáp án:** Không qua đường B -> C đó. Nếu A cần C, A tự khai báo dependency thích hợp.

**Câu 7.** A exclude C trên dependency B, nhưng A còn phụ thuộc D và D cũng phụ thuộc C. C có thể vẫn xuất hiện không?

**Đáp án:** Có. Exclusion gắn vào nhánh A -> B; đường A -> D -> C vẫn có thể giữ C.

**Câu 8.** App có `<modules>` liệt kê hai module nhưng không có `<dependency>` trỏ giữa chúng. Một module có tự dùng class của module kia không?

**Đáp án:** Không. Modules tạo aggregation, còn classpath cần quan hệ dependency.

**Câu 9.** Trong ví dụ ba module, vì sao `cli-app` không trực tiếp khai báo `api-contract` mà Maven vẫn có thể cung cấp nó khi chạy?

**Đáp án:** `cli-app` dùng `business-service` ở compile scope; `business-service` phụ thuộc `api-contract` ở compile scope. Maven truyền dependency theo đường bắc cầu phù hợp.

**Câu 10.** Vì sao nhìn thấy `codec:1.0` trong log verbose không có nghĩa runtime dùng version 1.0?

**Đáp án:** Đó có thể là một nút “omitted for conflict”; Maven đã chọn một version khác cho graph classpath thực tế.

**Câu 11.** Nếu app import trực tiếp một class thuộc dependency bắc cầu C, nên làm gì?

**Đáp án:** Khai báo C trực tiếp trong app để POM phản ánh sự phụ thuộc API thật và giảm rủi ro khi thư viện trung gian đổi graph.

**Câu 12.** Muốn xem graph của đúng `cli-app` sau khi build tất cả module nội bộ, dùng lệnh nào?

**Đáp án:** Có thể chạy `mvn clean install` từ root dự án mẫu, rồi `mvn -f cli-app/pom.xml dependency:tree`. Đây là cách ví dụ bảo đảm các artifact nội bộ được cài vào local repository trước khi phân tích POM đơn lẻ.

## Tài liệu tham khảo chính thức

- [Apache Maven – Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependencies, nearest definition, scope, optional, exclusion, dependency management, BOM và bảng truyền scope.
- [Apache Maven – POM Reference](https://maven.apache.org/pom.html): cấu trúc `<dependencies>`, `<dependencyManagement>`, `scope`, `optional` và `exclusions`.
- [Apache Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): goal, bộ lọc `includes`/`excludes`, `scope`, `verbose` và `outputType`.
- [Apache Maven Dependency Plugin – Tree Output Formats](https://maven.apache.org/plugins/maven-dependency-plugin/examples/tree-mojo.html): ví dụ `dot`, `graphml`, `tgf`, `json`.
- [Apache Maven Dependency Plugin – dependency:analyze](https://maven.apache.org/plugins/maven-dependency-plugin/analyze-mojo.html): gợi ý used undeclared/unused declared.
- [Apache Maven – Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): Maven reactor, lựa chọn modules và quan hệ dependency khi build.
- [Apache Maven – Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): inheritance, aggregation, effective POM và dependencies.
- [Apache Maven Enforcer Plugin – Dependency Convergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html): ví dụ quy tắc kiểm soát phiên bản dependency.
