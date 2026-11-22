# Kế thừa groupId, version và giữ artifactId riêng trong Maven POM

Trong một dự án Maven gồm nhiều module, thường có nhiều tệp `pom.xml` cùng thuộc một nhóm phần mềm và cùng chu kỳ phiên bản. Nếu mỗi module lặp lại `groupId` và `version`, chỉ cần đổi tên nhóm hoặc nâng phiên bản đã phải sửa nhiều nơi, dễ tạo ra những module mang tọa độ không nhất quán.

**POM inheritance (kế thừa POM)** cho phép một module **nhận `groupId` và `version` từ POM cha**, trong khi vẫn khai báo **`artifactId` riêng** để giữ danh tính của chính module đó.

Ví dụ:

```text
POM cha:
    com.example.training:training-parent:1.0.0-SNAPSHOT

POM con sau khi kế thừa:
    com.example.training:greeting-api:1.0.0-SNAPSHOT
```

Hai dự án có cùng `groupId` và `version` nhưng có `artifactId` khác nhau. **`training-parent` là artifact của POM cha; `greeting-api` là artifact của POM con.** Maven không tự đổi artifactId của POM con thành artifactId của cha.

Bài này giải thích cách Maven nhận diện parent, quy tắc thừa kế các tọa độ, ví dụ Maven/Java 17 có thể chạy, cách kiểm tra effective POM, khi nào nên ghi đè và những lỗi thường gặp.

## 1. Ôn lại tọa độ Maven và quan hệ parent–child

Một artifact Maven được nhận diện thông dụng bằng ba thành phần `groupId:artifactId:version`:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `groupId` | Nhóm/không gian định danh cho dự án hoặc tổ chức. | `com.example.training` |
| `artifactId` | Tên định danh của artifact trong nhóm. | `greeting-api` |
| `version` | Phiên bản artifact. | `1.0.0-SNAPSHOT` |

Khi tệp POM là dự án độc lập, bạn thường khai báo đủ cả ba:

```xml
<groupId>com.example.training</groupId>
<artifactId>greeting-api</artifactId>
<version>1.0.0-SNAPSHOT</version>
```

Đây chỉ là **đoạn XML trong phần tử `<project>`**, chưa phải một POM hoàn chỉnh.

Khi dùng parent, `groupId` và `version` của con có thể được **kế thừa** thay vì lặp lại. Tệp POM con cần chỉ ra parent bằng phần tử `<parent>`, gồm **tọa độ của chính POM cha**:

```xml
<parent>
    <groupId>com.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</parent>

<artifactId>greeting-api</artifactId>
```

Các thành phần cần phân biệt:

- `<parent><groupId>`, `<parent><artifactId>` và `<parent><version>` **xác định cha là ai** để Maven tìm và nạp mô hình cha.
- `<project><artifactId>` nằm ngoài `<parent>` **xác định chính dự án con**.
- Vì POM con không khai báo `<project><groupId>` và `<project><version>`, Maven lấy hai giá trị tương ứng từ parent.
- Tọa độ cuối của con vẫn là `com.example.training:greeting-api:1.0.0-SNAPSHOT`.

**Mấu chốt:** `parent.artifactId` là tên của cha, còn `project.artifactId` là tên của con. Đừng lấy `training-parent` làm artifactId của mọi module chỉ vì module đó kế thừa parent.

## 2. Quy tắc kế thừa chính xác

Maven sử dụng POM cha trong quá trình xây dựng mô hình dự án con. Với hai trường `groupId` và `version` ở cấp `project`:

1. Nếu **POM con không khai báo** trường đó, Maven kế thừa giá trị của cha.
2. Nếu **POM con khai báo rõ** trường đó, giá trị của con có thể ghi đè giá trị kế thừa.
3. `artifactId` của chính POM con vẫn **phải khai báo riêng** để định danh artifact con.
4. `artifactId` nằm trong `<parent>` **không thay thế** cho `artifactId` ở cấp `<project>`.

Bảng các trường hợp, giả sử parent có tọa độ `com.example.training:training-parent:1.0.0`:

| Khai báo ở cấp `project` của con | Tọa độ hiệu lực của con |
| --- | --- |
| Chỉ `<artifactId>api</artifactId>` | `com.example.training:api:1.0.0` |
| `<groupId>com.example.services</groupId>` và `<artifactId>api</artifactId>` | `com.example.services:api:1.0.0` |
| `<artifactId>api</artifactId>` và `<version>2.0.0</version>` | `com.example.training:api:2.0.0` |
| `<groupId>com.example.services</groupId>`, `<artifactId>api</artifactId>`, `<version>2.0.0</version>` | `com.example.services:api:2.0.0` |
| Không có `<artifactId>` của con | POM con thiếu định danh bắt buộc; Maven không tự lấy artifactId của parent để dùng thay. |

Việc ghi đè `groupId` hoặc `version` đôi khi cần thiết, nhưng nên có chủ đích. Nếu mục tiêu là một tập module cùng nhóm và cùng release, **để con kế thừa** giúp giảm việc cập nhật thủ công.

### Vì sao artifactId không được kế thừa như hai trường còn lại?

Mỗi module Maven là một dự án có danh tính riêng. Nếu POM cha và mọi POM con đều có cùng `groupId`, `artifactId` và `version` thì không còn phân biệt được các artifact ở cùng tọa độ. Maven cho phép nhiều dự án cùng nhóm và phiên bản, nhưng `artifactId` phải phản ánh module của chính mình.

Ví dụ trong một ứng dụng:

```text
com.example.training:training-parent:1.0.0-SNAPSHOT   (packaging pom)
com.example.training:domain-model:1.0.0-SNAPSHOT      (packaging jar)
com.example.training:service-api:1.0.0-SNAPSHOT       (packaging jar)
com.example.training:cli-tool:1.0.0-SNAPSHOT          (packaging jar)
```

Các module có thể kế thừa cùng parent, nhưng một dependency muốn dùng `service-api` phải trỏ tới `service-api`, không trỏ tới `training-parent`. `artifactId` ở con chính là điều giữ cho các artifact phân biệt được.

## 3. Tệp parent POM và cách khai báo `<parent>`

POM cha dùng để chia sẻ cấu hình thường có `<packaging>pom</packaging>`. Nó có thể đồng thời làm POM tổng hợp nhiều module, nhưng **kế thừa** và **tổng hợp** là hai quan hệ khác nhau (xem mục 7).

Một POM con tối thiểu có parent thường gồm `modelVersion`, `parent` và `artifactId`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.training</groupId>
        <artifactId>training-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>greeting-api</artifactId>
</project>
```

Đây là **POM con hoàn chỉnh về cấu trúc XML**; để thực sự chạy build, Maven phải tìm được POM cha trùng tọa độ. Trong ví dụ, parent được đặt ở thư mục phía trên, nên `../pom.xml` là đường dẫn thích hợp.

Các chi tiết đáng chú ý:

- `<parent>` là **tham chiếu đến POM cha**. Maven cần giải quyết parent trước khi hoàn thiện mô hình dự án con.
- Ba trường trong `<parent>` phải khớp với tọa độ thật của cha: `com.example.training:training-parent:1.0.0-SNAPSHOT`.
- `<relativePath>../pom.xml</relativePath>` chỉ nơi tìm POM cha trong cây thư mục cục bộ. Đây là đường dẫn **tương đối từ vị trí POM con**, không phải từ thư mục chạy lệnh Maven.
- Nếu không ghi `relativePath`, Maven thường mặc định kiểm tra `../pom.xml`. Viết tường minh giúp người học thấy rõ quan hệ đường dẫn.
- Nếu parent được lấy từ repository và không muốn Maven tìm một POM ở đường dẫn cục bộ mặc định, có thể dùng `<relativePath/>`.
- Nếu parent không thể giải quyết từ vị trí phù hợp hoặc repository, Maven không thể xây dựng đúng mô hình con và sẽ báo lỗi.

**Chú ý:** `<version>` trong `<parent>` là phiên bản **cha được tham chiếu**. Nó phải được biết để tìm cha; không thể bỏ trường này chỉ vì dự án con muốn kế thừa `project.version`.

## 4. Ví dụ thực hành hoàn chỉnh với Java 17

Ví dụ sau tạo một dự án gồm parent POM và module Java tên `greeting-api`. Mục tiêu là **cho thấy POM con không khai báo groupId/version mà vẫn build được và có tọa độ chính xác**.

### 4.1. Cấu trúc thư mục

```text
training-parent/
├── pom.xml
└── greeting-api/
    ├── pom.xml
    └── src/
        └── main/
            └── java/
                └── com/
                    └── example/
                        └── training/
                            └── App.java
```

`training-parent/pom.xml` là POM cha và aggregator. `training-parent/greeting-api/pom.xml` là POM con. `App.java` thuộc package Java `com.example.training`; tên package đó có thể trùng quy ước `groupId` nhưng đây là **hai khái niệm độc lập**. Maven không yêu cầu package Java và groupId phải giống hệt.

Có thể tạo thư mục bằng IDE hoặc dùng lệnh:

Linux/macOS:

```bash
mkdir -p training-parent/greeting-api/src/main/java/com/example/training
cd training-parent
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path training-parent/greeting-api/src/main/java/com/example/training
Set-Location training-parent
```

### 4.2. Parent: `training-parent/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>greeting-api</module>
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
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Phân tích:

- `groupId` = `com.example.training` và `version` = `1.0.0-SNAPSHOT` là hai giá trị POM con có thể kế thừa.
- `artifactId` = `training-parent` là **tên của chính parent artifact**.
- `packaging=pom` là loại đóng gói thường dùng cho POM cha và cần thiết khi POM chứa `<modules>` theo kiểu aggregator.
- `<modules>` khai báo đường dẫn tới module để Maven Reactor có thể build khi chạy từ root. Cấu hình này **không tự tạo quan hệ kế thừa**; quan hệ kế thừa nằm trong `<parent>` của con.
- `maven.compiler.release=17` làm cấu hình Java 17 có thể được con kế thừa và sử dụng bởi Compiler Plugin.
- `pluginManagement` chọn phiên bản Maven Compiler Plugin khi nó được sử dụng. Chỉ đặt plugin trong `pluginManagement` không tự buộc mọi plugin bất kỳ chạy; với module `jar`, pha compile thông thường có Compiler Plugin gắn vào lifecycle.

Ví dụ dùng Maven phiên bản có khả năng chạy Compiler Plugin 3.14.1 và JDK 17+. Nếu máy chưa cache plugin và dependency, Maven cần truy cập repository để tải chúng.

### 4.3. Child: `training-parent/greeting-api/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.training</groupId>
        <artifactId>training-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>greeting-api</artifactId>
    <name>Greeting API</name>
    <description>Module minh họa kế thừa groupId và version.</description>
</project>
```

Đây là điểm chính của bài học: **không có `<groupId>` hoặc `<version>` trực tiếp ở cấp `<project>` của con**. Maven lấy chúng từ cha. Con có `<artifactId>greeting-api</artifactId>` riêng và giữ tên đó khi build.

Tọa độ hiệu lực:

```text
Parent: com.example.training:training-parent:1.0.0-SNAPSHOT
Child:  com.example.training:greeting-api:1.0.0-SNAPSHOT
```

Vì POM con không khai báo `<packaging>`, mặc định của nó là `jar`, trong khi parent có `packaging=pom`. **`packaging` không được thừa kế như `groupId` và `version`**; dự án con nhận loại đóng gói mặc định hoặc giá trị riêng do nó khai báo.

### 4.4. Lớp Java: `greeting-api/src/main/java/com/example/training/App.java`

```java
package com.example.training;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from greeting-api");
    }
}
```

Đây là một chương trình Java 17+ độc lập về phần mã nguồn, không dùng thư viện ngoài. Tệp và package đã khớp cấu trúc thư mục tiêu chuẩn của Maven.

### 4.5. Build và chạy

Trong thư mục `training-parent` (gốc chứa parent POM):

```bash
mvn -version
mvn clean package
java -cp greeting-api/target/classes com.example.training.App
```

Sau khi `mvn clean package` thành công, lệnh Java cuối in **chính xác**:

```text
Hello from greeting-api
```

Log Maven có thể thay đổi theo JDK, Maven, các plugin được tải và môi trường; không nên dự đoán toàn bộ log. Các đầu ra Maven thường nằm dưới `greeting-api/target`, ví dụ `greeting-api/target/classes/com/example/training/App.class` và `greeting-api/target/greeting-api-1.0.0-SNAPSHOT.jar`.

Có thể build riêng module con **từ aggregator POM** bằng:

```bash
mvn -pl :greeting-api -am clean package
```

`-pl` (projects list) chọn module trong reactor theo `artifactId`, còn `-am` (also make) yêu cầu Maven bổ sung các project liên quan cần build theo dependency reactor. Trong ví dụ chỉ có một module Java nên lệnh chủ yếu giúp minh họa cách lựa chọn; `-am` không thay thế việc khai báo dependency giữa các module.

Trên Windows PowerShell, các lệnh `mvn` và `java` có cú pháp tương tự nếu Maven/JDK đã ở `PATH`. Trên dự án dùng Maven Wrapper, có thể thay `mvn` bằng `./mvnw` trên Linux/macOS hoặc `.\mvnw.cmd` trên PowerShell.

## 5. Kiểm tra Maven đã kế thừa tọa độ thật như mong đợi chưa

Đừng chỉ nhìn POM con và đoán giá trị. Maven có công cụ kiểm tra mô hình đã xử lý.

### 5.1. Dùng Maven Help Plugin để đánh giá các thuộc tính

Đứng ở thư mục `training-parent`, dùng `-f` trỏ trực tiếp POM con:

```bash
mvn -f greeting-api/pom.xml help:evaluate -Dexpression=project.groupId -q -DforceStdout
mvn -f greeting-api/pom.xml help:evaluate -Dexpression=project.artifactId -q -DforceStdout
mvn -f greeting-api/pom.xml help:evaluate -Dexpression=project.version -q -DforceStdout
```

Với ví dụ trên, **ba giá trị kỳ vọng** theo thứ tự là:

```text
com.example.training
greeting-api
1.0.0-SNAPSHOT
```

Đây là ba giá trị kỳ vọng **từ ba lệnh riêng**, không phải một stdout duy nhất. Trên một số phiên bản/thiết lập, lần đầu Help Plugin có thể tạo log tải plugin hoặc cảnh báo; `-q -DforceStdout` giúp thu gọn output.

Để xem cha được tham chiếu:

```bash
mvn -f greeting-api/pom.xml help:evaluate -Dexpression=project.parent.artifactId -q -DforceStdout
```

Giá trị kỳ vọng là `training-parent`. So sánh nó với `project.artifactId=greeting-api` sẽ thấy rõ Maven đang phân biệt **artifact của cha** và **artifact của con**.

### 5.2. Xem effective POM

```bash
mvn -f greeting-api/pom.xml help:effective-pom
```

Effective POM là mô hình Maven đã tổng hợp sau inheritance, defaults và những cấu hình liên quan. Trong kết quả của module con, các tọa độ hiệu lực sẽ phản ánh `groupId=com.example.training`, `artifactId=greeting-api`, `version=1.0.0-SNAPSHOT`.

Để ghi mô hình ra tệp dễ xem:

```bash
mvn -f greeting-api/pom.xml help:effective-pom -Doutput=effective-pom.xml
```

Vị trí tệp output phụ thuộc cách Help Plugin xử lý đường dẫn và thư mục thực thi. Hãy tìm tệp theo thông báo của plugin và **đừng lấy output được tạo làm POM nguồn thay thế**. Khi kiểm tra một module khác, chỉ định `-f` của module đó để tránh xem nhầm effective POM của parent.

### 5.3. Đừng nhầm các thuộc tính khác tên

| Biểu thức | Kỳ vọng với module `greeting-api` |
| --- | --- |
| `${project.groupId}` | `com.example.training` |
| `${project.artifactId}` | `greeting-api` |
| `${project.version}` | `1.0.0-SNAPSHOT` |
| `${project.parent.groupId}` | `com.example.training` |
| `${project.parent.artifactId}` | `training-parent` |
| `${project.parent.version}` | `1.0.0-SNAPSHOT` |
| `${project.basedir}` | Thư mục chứa `greeting-api/pom.xml`, không phải gốc parent. |

Ví dụ này chỉ có **một cấp kế thừa** và không override groupId/version, nên một số giá trị `project` và `project.parent` trùng nhau. Trong trường hợp con ghi đè groupId hoặc version, chúng có thể khác.

## 6. Khi nào con cần tự khai báo groupId hoặc version?

Kế thừa hai trường này là lựa chọn thích hợp cho các module cùng nhóm và cùng vòng đời phát hành, nhưng Maven **không cấm con đặt giá trị khác**.

### 6.1. Ghi đè groupId

POM con có thể chứa:

```xml
<parent>
    <groupId>com.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</parent>

<groupId>com.example.integrations</groupId>
<artifactId>external-adapter</artifactId>
```

Đây là đoạn minh họa bên trong `<project>`. POM con sẽ có tọa độ `com.example.integrations:external-adapter:1.0.0-SNAPSHOT`. Tọa độ của parent vẫn là `com.example.training:training-parent:1.0.0-SNAPSHOT`.

Việc đổi groupId có thể hữu ích khi con nằm trong nhóm namespace khác nhưng vẫn cần chung cấu hình build. Tuy nhiên, điều này thay đổi tọa độ artifact, nên mọi dependency, repository policy, script hoặc tài liệu tham chiếu tới module cần được xem xét.

### 6.2. Ghi đè version

POM con có thể khai báo:

```xml
<parent>
    <groupId>com.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</parent>

<artifactId>experimental-tool</artifactId>
<version>0.5.0-SNAPSHOT</version>
```

Khi đó, `project.version` của con là `0.5.0-SNAPSHOT`, trong khi `project.parent.version` vẫn là `1.0.0-SNAPSHOT`. Có hai phiên bản với **hai vai trò khác nhau**. Module vẫn kế thừa cấu hình parent được tham chiếu; việc version của con khác không làm Maven tự đổi phiên bản cha.

Dù Maven cho phép điều này, các module được phát hành cùng nhau thường tránh override version nếu muốn duy trì một phiên bản thống nhất. Với các module phát hành độc lập, chiến lược phiên bản cần được mô tả rõ và quản lý nhất quán.

### 6.3. Không ghi đè khi không có lý do

Nếu mọi module đều cần cùng groupId/version, cách gọn nhất vẫn là:

```xml
<parent>
    <groupId>com.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</parent>
<artifactId>some-module</artifactId>
```

Giảm lặp khiến lỗi phát hành khó xảy ra hơn, nhất là khi repository có nhiều module. Nhưng cần nhớ POM con vẫn phải ghi **tọa độ parent** trong `<parent>`, bao gồm phiên bản cha cần giải quyết.

## 7. Inheritance và aggregation là hai quan hệ riêng

Đây là nơi dễ hình thành hiểu lầm nhất trong Maven multi-module.

**Inheritance (kế thừa):** module con khai báo `<parent>` và Maven tổng hợp mô hình POM cha vào POM con theo các quy tắc kế thừa. Cơ chế này cho phép con nhận `groupId`, `version` và nhiều cấu hình build từ cha.

**Aggregation (tổng hợp):** một POM có `<modules>` liệt kê các dự án Maven thuộc reactor, để khi chạy từ aggregator Maven có thể xử lý chúng cùng nhau. Cơ chế này không tự tạo `<parent>` trong các POM module.

Sơ đồ:

```text
                    training-parent/pom.xml
                           |
           +---------------+----------------+
           |                                |
    <modules>                         <parent> trong
    liệt kê greeting-api              greeting-api/pom.xml
           |                                |
           v                                v
   Aggregation: đưa module       Inheritance: nhận groupId,
   vào reactor khi build         version và cấu hình cha
```

Trong ví dụ mục 4, cùng một POM làm **cả hai việc**:

- Root có `<modules><module>greeting-api</module></modules>`.
- `greeting-api/pom.xml` có `<parent>...training-parent...</parent>`.

Nếu root **chỉ có `<modules>`** mà POM con **không có `<parent>`**, Maven vẫn có thể thu thập/build các module khi chúng được khai báo đầy đủ, nhưng module **không tự kế thừa** tọa độ từ root.

Nếu POM con **có `<parent>`** nhưng root **không liệt kê nó trong `<modules>`**, con vẫn có thể kế thừa cấu hình nếu Maven giải quyết được cha; tuy nhiên chạy `mvn package` từ root sẽ không tự thu thập con đó bằng aggregation.

**Gốc Git và gốc Maven cũng không đồng nghĩa.** Một repository có thể chứa nhiều dự án Maven không cùng reactor; mỗi POM có `project.basedir` riêng. Để biết Maven thực sự đang xử lý project nào, dùng `-f` hoặc `help:evaluate` như đã trình bày.

## 8. Cập nhật phiên bản parent và các module

Giả sử toàn bộ dự án đang dùng `1.0.0-SNAPSHOT` và cần chuyển sang `1.1.0-SNAPSHOT`.

Ban đầu parent có:

```xml
<groupId>com.example.training</groupId>
<artifactId>training-parent</artifactId>
<version>1.0.0-SNAPSHOT</version>
```

POM con tham chiếu:

```xml
<parent>
    <groupId>com.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</parent>
<artifactId>greeting-api</artifactId>
```

Khi đổi phiên bản parent, **các con cũng cần tham chiếu phiên bản parent mới** theo quy trình cập nhật POM. Không thể chỉ sửa `<version>` ở parent rồi mặc định `<parent><version>` trong mọi POM con tự cập nhật. Nếu con còn trỏ đến `1.0.0-SNAPSHOT` trong khi parent cục bộ đã là `1.1.0-SNAPSHOT`, Maven có thể từ chối đường dẫn parent cục bộ do tọa độ không khớp, hoặc cố tìm bản parent cũ trong repository.

Trong dự án nhiều module, có thể dùng **Maven Versions Plugin** hoặc công cụ quản lý release phù hợp để hỗ trợ cập nhật các tham chiếu phiên bản, sau đó xem diff và kiểm tra effective POM. Không nên chạy lệnh thay phiên bản hàng loạt khi chưa xác định module nào kế thừa thống nhất và module nào cố ý có phiên bản riêng.

Một quy trình kiểm tra hợp lý:

1. Xác định parent mới và các module thực sự dùng parent đó.
2. Cập nhật phiên bản POM cha và tham chiếu `<parent><version>` ở các POM con liên quan.
3. Kiểm tra các phiên bản được khai báo rõ ở cấp con; quyết định có cần đổi hay giữ nguyên.
4. Chạy `mvn validate`/`mvn verify` phù hợp với reactor.
5. Xem `help:evaluate` hoặc `help:effective-pom` cho các module quan trọng để bảo đảm tọa độ đúng.

**Đừng dùng một thuộc tính tùy ý như `${project.version}` bên trong `<parent><version>` để tránh cập nhật**: Maven cần giải quyết parent trước khi có mô hình con hoàn chỉnh. Maven có cơ chế phiên bản CI-friendly riêng như `${revision}` trong các trường hợp được hỗ trợ, nhưng đó là chủ đề nâng cao và cần cấu hình/phát hành nhất quán.

## 9. Kế thừa tọa độ không đồng nghĩa tự tạo dependency giữa các module

Giả sử có hai module:

```text
training-parent/
├── pom.xml
├── greeting-api/pom.xml
└── greeting-client/pom.xml
```

Cả hai đều có:

```xml
<parent>
    <groupId>com.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</parent>
```

Nhưng một module **không tự được thêm vào classpath của module kia** chỉ vì chúng cùng parent, groupId và version. Nếu `greeting-client` muốn sử dụng lớp Java trong `greeting-api`, nó phải khai báo dependency phù hợp:

```xml
<dependencies>
    <dependency>
        <groupId>com.example.training</groupId>
        <artifactId>greeting-api</artifactId>
        <version>${project.version}</version>
    </dependency>
</dependencies>
```

Đây là đoạn minh họa bên trong POM `greeting-client`, giả định **hai module cùng project.version**. `${project.version}` ở đây được xử lý theo mô hình của **module đang khai báo dependency**, không có nghĩa Maven luôn lấy version của mọi module khác. Nếu `greeting-api` có version khác, tham chiếu đó có thể sai.

Để tránh lặp phiên bản dependency, parent còn có thể dùng `<dependencyManagement>`. Nhưng đây là cơ chế **quản lý phiên bản dependency**, khác với việc con kế thừa `project.version` và khác với việc thực sự thêm dependency vào `<dependencies>`.

| Cơ chế | Mục đích | Tự đưa thư viện của module khác vào classpath? |
| --- | --- | --- |
| `<parent>` | Chọn POM cha; kế thừa `groupId`, `version` và cấu hình. | Không. |
| `<modules>` | Thu thập module để build trong Maven reactor. | Không. |
| `<dependencyManagement>` | Cung cấp cấu hình/phiên bản dependency khi có nơi sử dụng. | Không. |
| `<dependencies>` | Khai báo dependency mà module thực sự cần. | Có, theo scope và quy tắc Maven. |

Một build nhiều module có thể thành công nhờ reactor, nhưng việc giải quyết classpath vẫn dựa trên dependencies và cấu hình thực sự của từng module.

## 10. Những lỗi hay gặp khi kế thừa `groupId` và `version`

### Lỗi 1. Bỏ `artifactId` của con vì tưởng Maven kế thừa cả ba tọa độ

**Sai:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example.training</groupId>
        <artifactId>training-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </parent>
</project>
```

POM con thiếu `artifactId` của chính nó. Phải khai báo thêm, chẳng hạn:

```xml
<artifactId>greeting-api</artifactId>
```

Đây là trường hợp lỗi định danh của dự án, không phải lỗi download dependency. `artifactId` trong phần `<parent>` không được dùng thay `project.artifactId`.

### Lỗi 2. Viết `artifactId` của cha ở cấp dự án con

Ví dụ con ghi `<artifactId>training-parent</artifactId>` thay vì `greeting-api`, khiến tọa độ con có thể đụng với cha nếu cùng groupId/version. Hãy đặt `artifactId` ở cấp con theo đúng tên module, thường nhất quán với tên artifact được người khác sử dụng.

### Lỗi 3. Nhầm `relativePath` và tọa độ parent

Nếu parent ở `../pom.xml` nhưng `<parent><artifactId>` ghi sai, Maven không thể coi POM đó là đúng cha chỉ vì file tồn tại. `relativePath` là **gợi ý nơi tìm**, còn ba tọa độ parent mới là **định danh cần khớp**.

Nếu parent nằm ở vị trí khác, sửa đường dẫn tương đối, ví dụ `../parent/pom.xml`; nếu parent là bản phát hành nằm trong repository, cân nhắc `<relativePath/>` và bảo đảm repository có artifact cha phù hợp.

### Lỗi 4. Đổi version parent nhưng quên update `<parent><version>` trong con

Khi parent đổi từ `1.0.0` sang `1.1.0`, POM con vẫn tham chiếu `1.0.0` sẽ tiếp tục cố giải quyết phiên bản cha cũ. Cập nhật tham chiếu và xác minh kết quả kế thừa; không coi `project.version` của con và `parent.version` là một trường được lưu duy nhất.

### Lỗi 5. Tự khai báo `groupId`/`version` ở mọi POM con dù tất cả đều giống cha

Không sai cú pháp, nhưng làm tăng công việc bảo trì và rủi ro lệch tọa độ. Nếu muốn con luôn theo parent, nên bỏ hai trường trùng và chỉ giữ `artifactId` riêng.

### Lỗi 6. Nhầm aggregation với inheritance

Có `<modules>` nhưng POM con không khai báo `<parent>`: module được thu thập vào reactor nhưng không kế thừa tọa độ từ aggregator. Có `<parent>` nhưng không có `<modules>`: kế thừa vẫn có thể hoạt động, nhưng module không tự được build khi chạy reactor từ root.

### Lỗi 7. Cho rằng parent là dependency thư viện Java

`<parent>` dùng để kế thừa mô hình POM, **không thêm code của parent vào classpath**. POM cha thường có packaging `pom`, không phải JAR chứa lớp nghiệp vụ. Muốn dùng code của module khác, khai báo dependency thực sự.

### Lỗi 8. Dựa vào tên thư mục thay vì kiểm tra tọa độ Maven

Thư mục `greeting-api` có thể chứa một POM khai báo `artifactId` khác. Maven dùng POM làm nguồn mô hình; tên thư mục không tự quyết định tọa độ. Kiểm tra `project.artifactId` bằng Help Plugin.

### Lỗi 9. Nhầm `project.version` của module với `project.parent.version`

Khi con override `version`, hai giá trị này có thể khác. Dependency tới module khác bằng `${project.version}` chỉ an toàn khi chiến lược phiên bản phù hợp. Đối chiếu effective POM và tọa độ artifact đích.

### Lỗi 10. Không kiểm tra POM cha có giải quyết được trên CI

Máy phát triển có thể đã cài bản parent vào local repository, trong khi CI sạch chưa có. Nếu parent không nằm ở đường dẫn `relativePath` mong đợi và không có trong các repository truy cập được, CI có thể báo lỗi **Non-resolvable parent POM**. Kiểm tra cấu trúc dự án và quy trình cung cấp parent thay vì chỉ sửa `groupId`.

## 11. Quy trình thiết kế POM con gọn và ổn định

Với một repository gồm nhiều module chung nhóm/version, có thể đi theo thứ tự:

1. **Chọn tọa độ parent**: tên nhóm, artifactId của parent và version dùng chung.
2. **Khai báo parent packaging `pom`** và cấu hình thật sự có thể chia sẻ (Java version, encoding, plugin versions...).
3. **Ở mỗi POM con, khai báo `<parent>` đúng ba tọa độ parent** và `relativePath` nếu cần.
4. **Đặt `artifactId` riêng** theo chức năng của từng module; không lặp `groupId`/`version` khi muốn kế thừa.
5. **Chỉ thêm `<groupId>` hoặc `<version>` ở con** nếu module có chiến lược định danh/phiên bản riêng.
6. **Dùng `<modules>` ở aggregator** nếu cần chạy nhiều module cùng một Maven reactor.
7. **Khai báo dependencies riêng** cho quan hệ dùng code giữa các module.
8. **Chạy build và kiểm tra effective coordinates**, nhất là sau thay đổi parent/version.

Để tự kiểm tra nhanh một module:

```bash
mvn -f greeting-api/pom.xml help:evaluate -Dexpression=project.groupId -q -DforceStdout
mvn -f greeting-api/pom.xml help:evaluate -Dexpression=project.artifactId -q -DforceStdout
mvn -f greeting-api/pom.xml help:evaluate -Dexpression=project.version -q -DforceStdout
```

Kết quả mong đợi cho bài thực hành vẫn là `com.example.training`, `greeting-api` và `1.0.0-SNAPSHOT`. Nếu khác, hãy xem POM con có ghi đè giá trị hay Maven đang giải quyết nhầm parent/POM không.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Parent có `groupId=org.example`, `artifactId=company-parent`, `version=2.3.0`. Con khai báo đúng `<parent>` trỏ tới parent đó, rồi chỉ có `<artifactId>billing-service</artifactId>`. Tọa độ con là gì?

**Đáp án:** `org.example:billing-service:2.3.0`. Con kế thừa groupId/version và giữ artifactId riêng.

**Câu 2.** Vì sao con vẫn phải khai báo `<parent><artifactId>company-parent</artifactId>` nếu đã có `<artifactId>billing-service</artifactId>`?

**Đáp án:** Hai phần tử có vai trò khác nhau: artifactId trong `parent` xác định POM cha cần giải quyết; artifactId cấp `project` định danh artifact con.

**Câu 3.** Con ghi thêm `<version>3.0.0</version>` bên ngoài `<parent>`, trong khi parent version là `2.3.0`. `project.version` và `project.parent.version` là gì?

**Đáp án:** `project.version=3.0.0`; `project.parent.version=2.3.0`. Con ghi đè version của chính nó và vẫn tham chiếu parent phiên bản `2.3.0`.

**Câu 4.** Parent có `<modules><module>billing-service</module></modules>` nhưng POM `billing-service` không có `<parent>`. Nó có tự kế thừa groupId/version từ aggregator không?

**Đáp án:** Không. `modules` là aggregation, còn inheritance yêu cầu con khai báo `parent` phù hợp.

**Câu 5.** Parent đổi version từ `2.3.0` sang `2.4.0`, nhưng con vẫn ghi `<parent><version>2.3.0</version>`. Có bảo đảm con tự nhận phiên bản mới không?

**Đáp án:** Không. Con vẫn trỏ tới phiên bản parent cũ. Cần cập nhật tham chiếu parent và kiểm tra lại phiên bản hiệu lực.

**Câu 6.** Hai module `billing-api` và `billing-storage` cùng parent, groupId và version. `billing-api` muốn import lớp của `billing-storage`. Chỉ kế thừa cùng parent đã đủ chưa?

**Đáp án:** Chưa. Cần dependency phù hợp tới artifact `billing-storage` trong POM `billing-api`; quan hệ kế thừa POM không tự tạo dependency mã Java.

**Câu 7.** Vì sao chạy lệnh `help:evaluate` cho từng module tốt hơn suy đoán từ POM cha?

**Đáp án:** Vì POM con có thể ghi đè `groupId`/`version`, parent có thể khác với dự kiến, hoặc bạn có thể đang build sai POM. Effective model cho biết tọa độ Maven thực sự sử dụng.

## Tài liệu tham khảo chính thức

- [Apache Maven – Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): ví dụ chuẩn về inheritance; bỏ `groupId`/`version` trong child POM; phân biệt inheritance và aggregation.
- [Apache Maven – POM Reference](https://maven.apache.org/pom.html): `parent`, `relativePath`, các trường định danh, `dependencyManagement` và `pluginManagement`.
- [Apache Maven – Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor, xử lý thứ tự module và các tùy chọn `-pl`, `-am`.
- [Apache Maven – Help Plugin: evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html): xem từng giá trị `project.groupId`, `project.artifactId`, `project.version`.
- [Apache Maven – Help Plugin: effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): xem mô hình POM cuối cùng sau kế thừa.
- [Apache Maven – Versions Plugin](https://www.mojohaus.org/versions/versions-maven-plugin/): công cụ hỗ trợ cập nhật phiên bản khi quản lý nhiều POM.
