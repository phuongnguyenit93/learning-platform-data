# `import` trong `dependencyManagement` và ý nghĩa đối với BOM (Maven)

## 1. Tại sao cần `scope=import`?

Một ứng dụng Java thường dùng cả **bộ thư viện có liên quan**: ví dụ một API, thư viện client, module JSON, module logging hoặc nhiều thành phần của cùng một framework. Các module ấy có thể phát hành phiên bản khác nhau. Nếu mỗi dự án tự khai phiên bản một cách rời rạc, dễ gặp tình trạng:

- module `client` đang là `2.4.0` nhưng `model` vẫn ở `2.1.0`;
- một dependency bắc cầu kéo về phiên bản cũ hơn mong đợi;
- hai microservice sử dụng phiên bản không thống nhất của cùng một bộ thư viện;
- mỗi lần nâng phiên bản phải sửa hàng chục dòng `<version>` trong nhiều POM.

Maven giải quyết nhu cầu quản lý phiên bản bằng **`<dependencyManagement>`**. Để chia sẻ một **bộ quy tắc quản lý dependency** giữa những dự án không nhất thiết có cùng parent, Maven cho phép **nhập một POM** bằng:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>example-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là cấu hình **import BOM (Bill of Materials)** điển hình cho Maven 3.x và POM model 4.0.0. Tọa độ `dev.example:example-bom:1.0.0` chỉ minh họa; nó chưa là thư viện công khai để tự tải. Khi import thành công, Maven dùng **danh sách managed dependencies trong effective POM của BOM** để tham gia quản lý dependency của consumer.

**Ý chính:** `import` là cách **nhập metadata quản lý dependencies**. Nó **không phải** một scope classpath giống `compile`, `runtime` hoặc `test`; bản thân BOM không được dùng như JAR của ứng dụng.

## 2. Phân biệt `<dependencies>` và `<dependencyManagement>`

Hai khối XML trông gần giống nhau nhưng có vai trò rất khác:

| Nơi khai báo | Maven hiểu như thế nào? | Có tự thêm dependency vào classpath? |
| --- | --- | --- |
| `<dependencies>` | Project thực sự cần một dependency trực tiếp | Có, tùy scope và quá trình resolution |
| `<dependencyManagement><dependencies>` | Cung cấp/quản lý version, scope hoặc metadata cho dependency **khi nó được dùng** | **Không** tự thêm dependency |
| BOM được `import` trong `dependencyManagement` | Mang các khai báo managed dependencies từ POM khác vào quản lý của project | **Không** tự thêm tất cả thư viện trong BOM |

Ví dụ, BOM quản lý hai artifact:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>sample-api</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>sample-client</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Nếu ứng dụng **chỉ import BOM**, chưa khai `sample-api` hoặc `sample-client` trong `<dependencies>` và cũng không có nhánh bắc cầu nào cần chúng, Maven **không** tải các JAR đó vào classpath chỉ vì chúng nằm trong BOM.

Nếu ứng dụng khai:

```xml
<dependencies>
    <dependency>
        <groupId>dev.example</groupId>
        <artifactId>sample-client</artifactId>
    </dependency>
</dependencies>
```

thì Maven có thể lấy **version `1.0.0`** từ dependency management sau khi import BOM, không cần lặp `<version>1.0.0</version>` ở mỗi consumer.

BOM quản lý `sample-api` không tự khiến `sample-api` xuất hiện. Nhưng nếu POM của `sample-client` khai `sample-api` là dependency bắc cầu phù hợp, nó có thể vào graph; khi đó management của consumer cũng có thể tác động đến version được chọn.

## 3. Vì sao `import` là một scope “đặc biệt”?

Theo Maven Dependency Mechanism, những scope như `compile`, `provided`, `runtime`, `test` ảnh hưởng đến **giai đoạn sử dụng dependency và classpath**. `import` thì khác:

- `import` chỉ được hỗ trợ cho một dependency **`<type>pom</type>`** nằm bên trong **`<dependencyManagement>`**.
- Maven thay thế import entry bằng **effective managed-dependency list** của POM được chỉ định.
- BOM import không tạo JAR để biên dịch/chạy, không có nghĩa là “tải mọi thư viện để compile”.
- Cơ chế import có thể đệ quy: một BOM có thể import một BOM khác rồi mang theo những managed dependencies đã resolve của BOM ấy.

Bảng so sánh ngắn:

| Scope | Thường nằm ở đâu | Ý nghĩa điển hình |
| --- | --- | --- |
| `compile` | Dependency thực tế trong `<dependencies>` | Có trên compile/runtime/test classpaths và có thể truyền transitively |
| `runtime` | Dependency thực tế | Cần khi chạy/test; không cần trên main compile classpath |
| `test` | Dependency thực tế | Chỉ cho việc compile/chạy tests, không truyền transitively bình thường |
| `provided` | Dependency thực tế | Compile/test có, runtime do môi trường cung cấp; không truyền transitively |
| `import` | **`<dependencyManagement>` + `<type>pom</type>`** | Nhập danh sách managed dependencies; **không đưa artifact vào classpath** |

Viết như sau **không phải cách import BOM hợp lệ**:

```xml
<!-- Sai mục đích: import không nằm trong dependencyManagement -->
<dependencies>
    <dependency>
        <groupId>dev.example</groupId>
        <artifactId>example-bom</artifactId>
        <version>1.0.0</version>
        <type>pom</type>
        <scope>import</scope>
    </dependency>
</dependencies>
```

Đặt import đúng `<dependencyManagement>` như ví dụ đầu bài. Cũng không nên bỏ `<type>pom</type>`, vì mặc định dependency thường có type `jar`; import cần artifact kiểu POM.

## 4. BOM là gì, và khác parent POM thế nào?

**BOM — Bill of Materials** là một POM công bố **danh sách phiên bản phù hợp của một nhóm artifact** để các ứng dụng khác dùng chung. Một BOM theo Maven 3 thường có `<packaging>pom</packaging>` và mục tiêu chính là `<dependencyManagement>`.

**Parent POM** là POM được chọn bằng `<parent>`, có thể truyền cho project con rất nhiều phần của model: properties, dependency management, plugin management, build settings và các khai báo có tính thừa kế.

| Câu hỏi | Parent POM | Imported BOM |
| --- | --- | --- |
| Mỗi project có thể chọn bao nhiêu? | Một parent trực tiếp | Có thể import nhiều BOM |
| Cách dùng | `<parent>...</parent>` | `<dependencyManagement>` với `type=pom`, `scope=import` |
| Có cung cấp managed dependency versions? | Có | Có |
| Có truyền nguyên `<build><plugins>` hoặc `<pluginManagement>` của POM kia? | Có thể theo quy tắc inheritance | **Không** |
| Có truyền mọi `<properties>` của POM kia sang consumer? | Properties của parent có thể được thừa kế | **Không mặc định theo cách import thông thường** |
| Có tự thêm tất cả artifact của POM kia vào runtime? | Không vì chỉ là parent | Không vì chỉ là BOM import |

Vì Maven chỉ có một parent trực tiếp, BOM hữu ích khi project đã kế thừa một parent của công ty nhưng vẫn muốn dùng bộ version của Spring, Jackson, Jakarta hoặc một framework khác.

**Cẩn thận với properties:** nếu BOM tự dùng `${library.version}` trong managed entries, Maven đánh giá chúng trong quá trình xây dựng effective model của BOM. Nhưng consumer **không nên giả định** có thể truy cập trực tiếp mọi `${library.version}` định nghĩa bên trong BOM bằng cùng tên. Nếu muốn kiểm soát version ở consumer, khai `<dependencyManagement>` của consumer hoặc dùng cơ chế được bộ framework đó tài liệu hóa; không dựa vào “property của BOM tự được import”.

Ghi chú phiên bản: Maven 4 đang bổ sung cơ chế chuyên biệt hơn cho BOM (ví dụ model 4.1.0, packaging `bom` và consumer POM tương thích). Bài này tập trung vào cú pháp `type=pom` + `scope=import` thông dụng trong Maven 3.x/POM model 4.0.0; khi nâng Maven 4 cần tham khảo tài liệu phiên bản đang sử dụng.

## 5. Cấu trúc BOM chuẩn theo Maven 3.x

Giả sử nhóm phát hành hai thư viện:

```text
dev.lesson:api-model:1.0.0
dev.lesson:api-service:1.0.0
```

POM BOM `dev.lesson:lesson-bom:1.0.0` có thể là:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.lesson</groupId>
    <artifactId>lesson-bom</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>dev.lesson</groupId>
                <artifactId>api-model</artifactId>
                <version>1.0.0</version>
            </dependency>
            <dependency>
                <groupId>dev.lesson</groupId>
                <artifactId>api-service</artifactId>
                <version>1.0.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

Điều đáng chú ý:

- `<packaging>pom</packaging>`: POM này dùng làm metadata quản lý version; nó không được kỳ vọng tạo JAR ứng dụng.
- Hai artifact `api-model` và `api-service` nằm trong **`dependencyManagement`**, không nằm trong `dependencies` của BOM.
- `version` của BOM (`1.0.0`) và version của các thư viện do nó quản lý có thể giống hoặc khác. BOM có một version riêng để người dùng nâng cấp cả bộ quy tắc.
- Thư viện consumer không tự nhận **mọi** dependency từ BOM. Nó chỉ có thể sử dụng những version được quản lý khi dependency thực sự xuất hiện.

## 6. Consumer import BOM và dùng dependency không khai version

Trong POM của ứng dụng:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>lesson-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>dev.lesson</groupId>
        <artifactId>api-service</artifactId>
    </dependency>
</dependencies>
```

Phần trên là đoạn trích đặt trong `<project>` của POM hợp lệ.

Đọc theo thứ tự:

1. Maven chọn `lesson-bom:1.0.0` và đọc **effective `dependencyManagement`** của BOM.
2. BOM cung cấp thông tin quản lý `dev.lesson:api-service → 1.0.0` và `dev.lesson:api-model → 1.0.0`.
3. `<dependencies>` của ứng dụng yêu cầu **`api-service`** (không cần ghi `version`).
4. Maven có thể resolve `api-service:1.0.0` theo management và đọc POM của thư viện này.
5. Nếu `api-service` phụ thuộc `api-model` theo scope bắc cầu phù hợp, `api-model` vào graph; version do consumer quản lý có thể được sử dụng khi có xung đột.
6. Classpath của ứng dụng chứa **các JAR đã được resolve**, không chứa “JAR của BOM”.

BOM giúp **đồng bộ version**, còn `<dependencies>` và dependency graph mới quyết định **có những artifact nào**.

## 7. Ví dụ Java 17 chạy được: hai thư viện, một BOM và một ứng dụng

Ví dụ này dùng **bốn Maven project độc lập trong các thư mục ngang hàng**, không thiết lập chúng thành một reactor import BOM nội bộ. Cách sắp xếp cố ý tránh vòng tham chiếu và làm rõ rằng **BOM phải có sẵn trong local/remote repository trước khi consumer resolve nó**.

### 7.1. Cấu trúc project

```text
bom-workshop/
├── api-model/
│   ├── pom.xml
│   └── src/main/java/dev/lesson/model/Message.java
├── api-service/
│   ├── pom.xml
│   └── src/main/java/dev/lesson/service/Greetings.java
├── lesson-bom/
│   └── pom.xml
└── consumer/
    ├── pom.xml
    └── src/main/java/dev/lesson/app/App.java
```

Quan hệ dự kiến:

```text
consumer:1.0.0
    └── api-service:1.0.0 (direct)
            └── api-model:1.0.0 (transitive)

lesson-bom:1.0.0
    └── quản lý version của api-service và api-model,
        không phải dependency runtime của consumer
```

### 7.2. `api-model/pom.xml` — thư viện dữ liệu

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>api-model</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
```

File `api-model/src/main/java/dev/lesson/model/Message.java`:

```java
package dev.lesson.model;

public record Message(String text) {
}
```

`record` là cú pháp được hỗ trợ trong Java 17; ví dụ không cần thư viện ngoài.

### 7.3. `api-service/pom.xml` — thư viện sử dụng model

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>api-service</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>api-model</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>

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
```

File `api-service/src/main/java/dev/lesson/service/Greetings.java`:

```java
package dev.lesson.service;

import dev.lesson.model.Message;

public final class Greetings {
    private Greetings() {
    }

    public static Message welcome() {
        return new Message("BOM quan ly phien ban");
    }
}
```

Bản POM này cho biết `api-service` **cần `api-model`**, nên `api-model` có thể được kéo theo khi ứng dụng phụ thuộc `api-service`.

### 7.4. `lesson-bom/pom.xml` — chỉ quản lý phiên bản

Tạo file `lesson-bom/pom.xml` theo đúng XML ở **mục 5**, trong đó `groupId=dev.lesson`, `artifactId=lesson-bom`, `version=1.0.0` và quản lý hai artifact `api-model:1.0.0`, `api-service:1.0.0`.

Không thêm hai thư viện vào `<dependencies>` của BOM để “kéo theo” chúng. BOM là **danh sách version**, không phải module tổng hợp toàn bộ JAR vào ứng dụng.

### 7.5. `consumer/pom.xml` — import BOM và khai API cần dùng

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>dev.lesson</groupId>
                <artifactId>lesson-bom</artifactId>
                <version>1.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>api-service</artifactId>
        </dependency>
    </dependencies>

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
```

Quan sát: `consumer` khai `api-service` **không có `<version>`**, vì BOM cung cấp version. Không có dependency trực tiếp `api-model`, nhưng nó sẽ vào graph do `api-service` phụ thuộc nó.

File `consumer/src/main/java/dev/lesson/app/App.java`:

```java
package dev.lesson.app;

import dev.lesson.service.Greetings;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(Greetings.welcome().text());
    }
}
```

Đoạn `App` sử dụng API của `api-service`. Method `welcome()` trả về `Message` từ `api-model`, nên lúc compile/run cũng cần class `Message` trên classpath; trong ví dụ nó đến theo dependency bắc cầu.

### 7.6. Build từng project theo đúng thứ tự

Yêu cầu: Java Development Kit **17+**, Maven 3.x hiện đại, Internet hoặc repository mirror có các Maven plugin khi chạy lần đầu.

**Đứng ở `bom-workshop/`**, chạy:

```bash
mvn -f api-model/pom.xml clean install
mvn -f api-service/pom.xml clean install
mvn -f lesson-bom/pom.xml install
mvn -f consumer/pom.xml clean package
```

Vì đây là **bốn project độc lập**, thứ tự quan trọng:

1. Cài `api-model` để `api-service` có dependency lúc compile.
2. Cài `api-service` vào local repository.
3. Cài **BOM POM** để `consumer` resolve bản import `lesson-bom:1.0.0`.
4. Build ứng dụng, lúc này cả các JAR và BOM POM đều đã sẵn sàng.

Sau bước thứ ba, local repository chứa file tương tự:

```text
~/.m2/repository/dev/lesson/lesson-bom/1.0.0/lesson-bom-1.0.0.pom
```

Không cần và không thể trông chờ có một `lesson-bom-1.0.0.jar` chứa toàn bộ class, vì packaging của BOM là `pom`. `-f` chỉ chọn POM của project đang chạy, không biến bốn project độc lập thành reactor.

### 7.7. Xem cây dependency thật của consumer

Chạy từ `bom-workshop/`:

```bash
mvn -f consumer/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Về nội dung, cây kỳ vọng:

```text
dev.lesson:consumer:jar:1.0.0
\- dev.lesson:api-service:jar:1.0.0:compile
   \- dev.lesson:api-model:jar:1.0.0:compile
```

Plugin có thể vẽ ký tự nhánh và thông tin `[INFO]` khác ví dụ. Điều quan trọng là **hai artifact JAR** xuất hiện ở compile scope, còn **`lesson-bom` không xuất hiện như một dependency JAR**.

Thử xem POM hiệu lực:

```bash
mvn -f consumer/pom.xml help:effective-pom
```

Tìm `dependencyManagement` của effective POM. Bạn sẽ thấy các managed entries xuất phát từ BOM đã được xử lý trong model hiệu lực. Sau đó so sánh với `dependency:tree`: **managed entries chỉ là metadata; tree mới thể hiện dependency được resolve thực tế**.

### 7.8. Chạy Java và kiểm chứng runtime classpath

Với ba JAR riêng, Java launcher không tự tải dependency Maven từ repository. Đứng tại `bom-workshop/`, trên **Linux/macOS/Bash**:

```bash
java -cp "consumer/target/consumer-1.0.0.jar:api-service/target/api-service-1.0.0.jar:api-model/target/api-model-1.0.0.jar" dev.lesson.app.App
```

Trên **Windows PowerShell**, dùng dấu chấm phẩy thay dấu hai chấm giữa các JAR:

```powershell
java -cp "consumer\target\consumer-1.0.0.jar;api-service\target\api-service-1.0.0.jar;api-model\target\api-model-1.0.0.jar" dev.lesson.app.App
```

**Stdout chính xác của chương trình Java:**

```text
BOM quan ly phien ban
```

Đường dẫn classpath **không có `lesson-bom`**, vì BOM chỉ quản lý version lúc Maven dựng dependency graph, không cung cấp bytecode ở runtime.

**Phép thử tư duy:** nếu bỏ hoàn toàn khai báo `api-service` khỏi `<dependencies>` của consumer (và cũng bỏ tham chiếu `Greetings` trong source để project vẫn compile), BOM import vẫn tồn tại nhưng cây dependency không tự thêm hai JAR này. Điều đó chứng minh import là **quản lý phiên bản**, không phải “phụ thuộc toàn bộ thư viện”.

## 8. Khi có dependency bắc cầu và xung đột phiên bản

Giả sử consumer phụ thuộc hai module trung gian:

```text
consumer
├── service-a:1.0.0
│   └── shared-core:1.1.0
└── service-b:1.0.0
    └── shared-core:1.4.0
```

Nếu không có quản lý version, Maven áp dụng quy tắc **nearest definition**, rồi dùng thứ tự khai báo khi hai đường cùng độ sâu. Không nên giả định Maven luôn chọn **version cao nhất**.

Nếu BOM/`dependencyManagement` của consumer quản lý:

```xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>shared-core</artifactId>
    <version>1.3.0</version>
</dependency>
```

thì Maven có thể dùng managed version `1.3.0` cho dependency bắc cầu `shared-core` thích hợp trong graph của consumer, thay vì version đến từ hai nhánh trên. Đây là cách căn chỉnh version, nhưng chỉ an toàn khi API/ABI của các thư viện tương thích.

**Lưu ý:** `dependencyManagement` không bảo đảm một dependency không có đường dẫn trong graph sẽ xuất hiện. Nó cũng không tự tải những dependency test/provided/optional vốn không được truyền qua graph theo quy tắc thông thường.

Khi code consumer **trực tiếp import class của `shared-core`**, nên cân nhắc khai `shared-core` là dependency trực tiếp trong `<dependencies>`, để POM phản ánh thứ mà source thực sự dùng. BOM vẫn có thể cung cấp version cho khai báo trực tiếp ấy.

## 9. Thứ tự ưu tiên: direct version, quản lý tại project, parent, nhiều BOM

Một câu hỏi khó là: nếu nhiều nơi đề xuất version khác nhau, Maven chọn theo nơi nào?

### 9.1. Dependency trực tiếp khai version

```xml
<dependencies>
    <dependency>
        <groupId>dev.example</groupId>
        <artifactId>sample-client</artifactId>
        <version>2.5.0</version>
    </dependency>
</dependencies>
```

Khi **dependency trực tiếp có `<version>2.5.0</version>`**, đó là version được consumer khai tường minh cho dependency ấy. Một BOM đang quản lý `sample-client` version `2.4.0` không tự thay thế trực tiếp version `2.5.0` trong trường hợp này. Muốn tận dụng BOM đầy đủ, **bỏ version tại direct dependency**.

### 9.2. Consumer khai override trong `dependencyManagement`

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>sample-client</artifactId>
            <version>2.5.1</version>
        </dependency>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>example-bom</artifactId>
            <version>2.4.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Một managed entry **được khai tường minh tại chính consumer** có thể ưu tiên hơn entry cùng tọa độ được nhập từ BOM. Đây là kỹ thuật nâng **một** thư viện mà chưa nâng cả BOM, nhưng nó có thể phá vỡ bộ phiên bản mà nhà phát hành BOM đã kiểm thử; cần test tích hợp thật.

### 9.3. Import hai BOM cùng quản lý một artifact

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>platform-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>feature-bom</artifactId>
            <version>3.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Giả sử cả hai BOM quản lý `org.example:shared-json` nhưng với version khác. Theo tài liệu Maven, nếu **consumer không tự có managed entry cho artifact đó**, **BOM import được khai trước thắng** trong trường hợp xung đột. Đổi thứ tự import có thể đổi version cuối cùng.

Đây là quy tắc dành cho **xung đột giữa các BOM import**, không nên lẫn với quy tắc “nearest definition” dành cho cạnh dependency trong graph.

### 9.4. Parent POM và inheritance

Parent có thể khai `dependencyManagement`; project con có thể override bằng managed entry riêng. Khi dùng cả parent và BOM, hãy kiểm tra **effective POM** vì việc merge các managed entries, import và quản lý của parent có thể ảnh hưởng kết quả. Không chỉ đọc một đoạn XML ở project con rồi suy ra thứ tự ưu tiên trong mọi tình huống.

Cách xác nhận:

```bash
mvn help:effective-pom
mvn dependency:tree
```

Lệnh đầu cho thấy thông tin quản lý hiệu lực trong project; lệnh thứ hai cho thấy **các dependencies cuối cùng** và version/scope thực sự được chọn.

## 10. `scope` của dependency vẫn quan trọng sau khi import BOM

`import` **không biến** mọi dependency thành compile scope. Những dependency đã được khai trong `<dependencies>` của consumer vẫn được xét scope bình thường:

```xml
<dependencies>
    <dependency>
        <groupId>dev.example</groupId>
        <artifactId>sample-client</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Giả sử BOM quản lý version `sample-client`, lệnh Maven có thể resolve version từ BOM trong khi **`scope=test` vẫn giới hạn dependency ở quá trình biên dịch/chạy test**. Nó không trở thành runtime dependency của ứng dụng chỉ vì được quản lý từ BOM.

Tương tự, với `scope=runtime`, dependency có thể ở runtime/test classpath nhưng không nằm trong main compile classpath. Phân biệt:

1. **BOM/`dependencyManagement`:** giúp chọn version và đôi khi cung cấp metadata quản lý như scope khi khai báo thiếu.
2. **Dependency khai thực tế/được kéo qua nhánh transitive:** quyết định artifact có tham gia graph không.
3. **Effective scope và classpath:** quyết định artifact xuất hiện ở compile/test/runtime nào.

Với một dependency khai trong BOM có thêm `<scope>`, consumer phải xem **scope hiệu lực**, chứ không nghĩ “import là một dạng scope áp lên tất cả”. Đây là hai lớp logic khác nhau.

## 11. Các công cụ kiểm tra BOM và classpath thực tế

### `help:effective-pom` — BOM đã quản lý điều gì?

```bash
mvn -f consumer/pom.xml help:effective-pom
```

Lệnh này thường in POM hiệu lực khá dài. Muốn lưu ra file để tìm bằng editor (trên dự án của bạn, không phải tài liệu bài học này):

```bash
mvn -f consumer/pom.xml help:effective-pom -Doutput=effective-pom.xml
```

Kiểm tra managed entries, version, scope, BOM imports và những override có ảnh hưởng. Đây là công cụ quan sát **model**, không phải danh sách classpath thực tế.

### `dependency:tree` — artifact và version nào đã được chọn?

```bash
mvn -f consumer/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Có thể lọc để tập trung một nhóm:

```bash
mvn -f consumer/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dincludes=dev.lesson
```

Cách dùng `-Dincludes` có thể phụ thuộc cú pháp pattern của Dependency Plugin; tài liệu plugin có hướng dẫn lọc theo group/artifact/version/scope. Tùy version, plugin có thể hiển thị các node omitted nếu bật verbose/đầu ra phù hợp.

### `dependency:build-classpath` — classpath được tạo ra là gì?

```bash
mvn -f consumer/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath
```

Lệnh này giúp quan sát đường dẫn các dependency đã resolve cho project theo mục đích của plugin. Nó không mặc định đưa file JAR của chính project đang build vào tất cả trường hợp; muốn chạy Java thủ công vẫn cần xét `target/classes` hoặc JAR của ứng dụng.

### `dependency:analyze` — source có dùng thư viện bắc cầu mà không khai direct không?

```bash
mvn -f consumer/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:analyze
```

Plugin cố phân tích dependency được sử dụng/khai báo dựa trên bytecode, hữu ích để tìm hiện tượng **used undeclared** hay **unused declared**. Nhưng reflection, service loader, generated code và dynamic loading có thể khiến kết quả không hoàn toàn chính xác. Xem đây là **gợi ý**, rồi xác minh bằng test và hiểu biết nghiệp vụ.

## 12. Các lỗi phổ biến khi sử dụng BOM import

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `'dependencies.dependency.version' is missing` | BOM chưa import được, sai artifactId/version, dependency không được BOM quản lý | Kiểm tra `type=pom`, `scope=import`, tọa độ BOM, managed entry thực tế |
| `Non-resolvable import POM` | BOM chưa publish/install, sai repository hoặc network/auth | Kiểm tra GAV và khả năng resolve POM, repository/mirror và settings |
| JAR không xuất hiện sau khi import | Chỉ khai BOM ở dependencyManagement mà chưa khai dependency thực tế | Thêm dependency cần dùng vào `<dependencies>` |
| Version trong tree khác mong muốn | Consumer khai version trực tiếp, managed override, BOM khác được import trước, parent hoặc mediation | So sánh effective POM và dependency tree |
| Test/compile không thấy class | Dependency đang ở `test`, `runtime`, `provided` hoặc đã bị exclude | Kiểm tra scope hiệu lực và classpath của phase |
| `ClassNotFoundException`/`NoClassDefFoundError` khi chạy | Runtime thiếu JAR, scope sai, exclusion hoặc conflict | Kiểm tra runtime dependency graph và classpath khi launch |
| Thêm `import` trong `<dependencies>` | Sai vị trí cú pháp | Di chuyển entry vào `<dependencyManagement><dependencies>` |
| Nhầm BOM với parent | Mong được thừa kế build plugins/properties từ BOM | Dùng parent hoặc khai cấu hình phù hợp; BOM quản lý dependencies |
| Lỗi circular model/import | Consumer và BOM tham chiếu chéo hoặc cố import BOM chưa có sẵn trong cùng reactor | Tách vòng phụ thuộc và publish BOM trước |

### Vì sao import BOM của chính một submodule có thể lỗi?

Maven xây dựng **model của project** (trong đó có import BOM) trước khi có thể lên lịch compile/package của toàn reactor. Nếu bạn đặt BOM ở một submodule chưa có artifact khả dụng trong repository, rồi từ một project đang được xây trong cùng reactor cố import chính BOM chưa resolve được đó, Maven có thể thất bại khi dựng model; không thể trông chờ thứ tự reactor tự làm cho BOM xuất hiện “ngay lúc cần”.

Thực hành an toàn: **publish/install BOM ở bước riêng trước**, hoặc sử dụng BOM đã có sẵn trong repository. Đặc biệt, không thiết kế vòng import-parent qua lại giữa BOM và project tiêu thụ nó.

### Vì sao BOM import không quản lý version của plugin?

Một `<dependencyManagement>` nhập từ BOM thường điều khiển **project dependencies**, không phải **dependencies nội bộ của Maven plugin** hoặc version của plugin ở `<build><plugins>`. Muốn quản lý phiên bản Compiler/Surefire/Resources plugins, dùng `<pluginManagement>` trong parent hoặc khai plugin version trực tiếp. Import BOM **không** thay thế plugin management.

### BOM không phải công cụ kiểm chứng tương thích tuyệt đối

Một BOM do nhà cung cấp phát hành giúp người dùng lựa chọn bộ version mà nhà cung cấp kỳ vọng hoạt động chung. Nhưng **đổi version theo BOM không tự chứng minh** không có lỗ hổng, không có xung đột ABI hay mã nguồn của bạn tương thích. Vẫn phải chạy compile, unit/integration tests và kiểm tra dependency graph trong CI.

## 13. Câu hỏi thường gặp

**Q: Nếu import BOM rồi thì có cần `<dependencies>` không?**  
Có. Bạn vẫn khai những thư viện thực sự cần, chỉ có thể bỏ `<version>` khi đã có managed entry phù hợp.

**Q: BOM có được nằm trong runtime classpath không?**  
Không theo cách import BOM thông thường. POM import mang **metadata**, không phải JAR cho ứng dụng.

**Q: `scope=import` có nghĩa dependency truyền transitively giống `compile` không?**  
Không. Scope `import` chỉ xử lý `dependencyManagement` và POM type; nó không có cùng chức năng classpath/transitivity với compile, runtime hay test.

**Q: Nếu hai BOM quản lý một artifact khác version?**  
Theo quy tắc import Maven, entry của **BOM được import trước** thắng khi consumer không có managed entry riêng cho artifact ấy. Xác minh bằng effective POM.

**Q: Tôi muốn nâng một dependency nhưng giữ BOM đang dùng?**  
Có thể quản lý version của dependency ấy trong `dependencyManagement` của consumer; hãy xem lại tính tương thích, tests và chính sách phát hành.

**Q: Dùng BOM có thay parent POM được không?**  
Không hoàn toàn. BOM chủ yếu quản lý dependencies; parent còn hỗ trợ inheritance về build/plugin/properties và nhiều cấu hình khác.

**Q: Nếu BOM tự import BOM khác?**  
Những managed entries có thể được nhập đệ quy. Tránh vòng tham chiếu và kiểm tra kết quả effective model.

**Q: Maven 4 có thay đổi BOM không?**  
Maven 4 có tính năng BOM/model mới; khi làm việc với dự án POM model 4.0.0/Maven 3.x, cú pháp import chuẩn trong bài vẫn là nền tảng. Đối chiếu tài liệu phiên bản Maven khi áp dụng các tính năng Maven 4 chuyên biệt.

## 14. Checklist áp dụng cho dự án thực tế

- [ ] Tôi hiểu `<dependencyManagement>` **quản lý** dependency, không tự thêm dependency.
- [ ] BOM tồn tại và resolve được từ local/remote repository **trước** khi consumer dựng model.
- [ ] Entry BOM có **`<type>pom</type>`** và **`<scope>import</scope>`**, nằm trong `dependencyManagement`.
- [ ] Tôi kiểm tra danh sách artifact/version mà BOM **thực sự quản lý**.
- [ ] Consumer khai những artifact thật sự dùng trong `<dependencies>`, chỉ bỏ version khi được quản lý.
- [ ] Với nhiều BOM, tôi đã chủ động kiểm soát thứ tự import và các entry override.
- [ ] Tôi không nhầm property/plugin management của parent với dependency management được import.
- [ ] Tôi đã đối chiếu **`help:effective-pom`** và **`dependency:tree`** của đúng project.
- [ ] Tôi đã kiểm tra scope của dependency (compile/runtime/test/provided) và classpath thực tế.
- [ ] Tôi không phụ thuộc mù quáng vào các transitive dependencies mà source trực tiếp sử dụng.
- [ ] Khi nâng BOM hoặc override version, tôi đã chạy `mvn clean verify` và các integration tests cần thiết.

**Tóm tắt:** `<scope>import</scope>` trong `dependencyManagement` là “nhập **quy tắc chọn dependency** từ một POM”, không phải “nhập **toàn bộ JAR** của nó”. BOM giúp căn chỉnh phiên bản cho một nhóm thư viện; `<dependencies>` xác định thư viện được sử dụng; scope và Maven Resolver quyết định classpath thực tế. Muốn biết điều gì được quản lý, xem **effective POM**; muốn biết gì được sử dụng, xem **dependency tree**.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Dependency Mechanism, Importing Dependencies và BOM](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven — What's new in Maven 4?](https://maven.apache.org/whatsnewinmaven4.html)
