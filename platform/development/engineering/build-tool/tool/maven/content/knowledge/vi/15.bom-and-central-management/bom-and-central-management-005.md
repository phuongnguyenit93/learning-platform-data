# Phân biệt dùng một POM làm parent với nhập nó như BOM

## 1. Hai cách tái sử dụng một POM, hai kết quả khác nhau

Trong Maven, cùng một file `pom.xml` có thể được dùng để **làm parent POM** của một project hoặc, nếu đáp ứng cấu trúc phù hợp, được **import như một BOM**. Hai thao tác đều có thể giúp project dùng chung phiên bản dependency, nhưng mục đích và phạm vi kế thừa rất khác nhau.

**Làm parent:**

```xml
<parent>
    <groupId>dev.lesson</groupId>
    <artifactId>shared-platform</artifactId>
    <version>1.0.0</version>
</parent>
```

**Import như BOM:**

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>shared-platform</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **hai đoạn XML đặt trong POM của project consumer**, không phải hai POM hoàn chỉnh. Trong cả hai trường hợp, `shared-platform` là một artifact có `packaging=pom` đã tồn tại hoặc có thể resolve. Nhưng:

- **`<parent>` thiết lập quan hệ kế thừa project model:** child có thể kế thừa `groupId`, `version`, `properties`, `dependencyManagement`, cấu hình build, plugin management, các plugin executions phù hợp và nhiều phần khác của parent.
- **BOM import chỉ mang vào danh sách managed dependencies** của effective POM được import: giúp quản lý version/scope và metadata liên quan của dependency, **không kế thừa cấu hình build, properties tùy ý, plugin versions, groupId hay project version** của POM đó.

Vì vậy câu hỏi không phải “cách nào tốt hơn trong mọi trường hợp?”, mà là **“tôi cần kế thừa cả tiêu chuẩn build, hay chỉ muốn sử dụng bộ version dependency?”**.

## 2. So sánh nhanh những gì thực sự được dùng lại

| Khía cạnh | Dùng `<parent>` | Import POM dưới dạng BOM |
| --- | --- | --- |
| Vị trí khai | `<project><parent>` | `<project><dependencyManagement><dependencies>` |
| Tọa độ POM | `groupId:artifactId:version` | `groupId:artifactId:version` + `type=pom` + `scope=import` |
| Yêu cầu packaging của POM nguồn | `pom` | `pom` trong cách import Maven 3.x/POM model 4.0.0 |
| Quan hệ với POM consumer | **Inheritance** | **Import managed-dependency metadata** |
| `groupId` và `version` của consumer | Có thể kế thừa khi child không tự khai | **Không** tự kế thừa |
| `artifactId` của consumer | Phải có artifactId riêng | Phải có artifactId riêng |
| `<properties>` của POM nguồn | Có thể kế thừa | **Không** được import như properties của consumer |
| `<dependencyManagement>` | Được kế thừa/hợp nhất | Các managed entries từ effective BOM được nhập |
| `<dependencies>` của POM nguồn | Có thể được thừa kế thành dependency của child | **Không** tự nhập các dependency này |
| `<build><plugins>` và plugin executions | Có thể kế thừa tùy `inherited`/merge rules | **Không** |
| `<pluginManagement>` | Có thể kế thừa | **Không** |
| `<repositories>` của nguồn | Có thể được kế thừa | Không import làm repositories của consumer |
| Có thể sử dụng nhiều POM cùng lúc? | **Một parent trực tiếp** | Có thể import **nhiều BOM** |
| Tự thêm toàn bộ thư viện được quản lý vào classpath? | Dependency management không; inherited `dependencies` có thể có | **Không** |
| Mục đích chính | Chuẩn hóa mô hình và build của các project con | Đồng bộ phiên bản/metadata dependencies giữa các project |

Phân biệt **“kế thừa `dependencies` của parent”** với **“import `dependencyManagement` từ BOM”** là điểm then chốt. Nếu parent có một dependency thông thường trong `<dependencies>`, child có thể được kế thừa dependency ấy. Còn BOM import **không tự kéo tất cả JAR** được liệt kê trong POM nguồn, kể cả khi BOM có `<dependencies>`.

## 3. Parent POM: thống nhất cả thông số project lẫn cách build

Một parent POM có thể tập trung nhiều quy định tổ chức như:

- Group/version mặc định của các module cùng release.
- `<properties>`: encoding, `maven.compiler.release`, tên môi trường hoặc các tham số mặc định dùng chung.
- `<dependencyManagement>`: các phiên bản dependency chuẩn.
- `<pluginManagement>`: phiên bản Compiler, Surefire, Jar, JaCoCo, Checkstyle plugins.
- `<build><plugins>`: plugin configurations/executions thực sự muốn áp dụng theo cơ chế inheritance.
- Repository, plugin repository, reporting và metadata phù hợp.

Ví dụ parent POM:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>dev.lesson</groupId>
                <artifactId>greeting-api</artifactId>
                <version>1.0.0</version>
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
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Một child có thể chỉ cần khai:

```xml
<parent>
    <groupId>dev.lesson</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
</parent>
<artifactId>order-service</artifactId>
<dependencies>
    <dependency>
        <groupId>dev.lesson</groupId>
        <artifactId>greeting-api</artifactId>
    </dependency>
</dependencies>
```

Đây là **đoạn trích** cần đặt trong `<project>` đầy đủ. Child không ghi `groupId` và `version` top-level vì có thể kế thừa từ parent; dependency `greeting-api` cũng không cần version vì parent quản lý. Thuộc tính Java release và compiler plugin version được kế thừa từ cấu hình build của parent.

### `pluginManagement` có tự chạy mọi plugin không?

**Không.** `pluginManagement` chủ yếu cung cấp cấu hình/phiên bản cho plugin khi plugin được sử dụng, ví dụ plugin được gọi tường minh hoặc được đưa vào lifecycle thông qua packaging. Nó **không** tự tạo mọi plugin execution tùy ý. Nếu cần một mục kiểm tra luôn chạy tại `verify`, phải cấu hình plugin execution và phase phù hợp, đồng thời xét quy tắc inheritance.

Ngược lại, plugin executions nằm trong `<build><plugins>` của parent có thể được child kế thừa theo mặc định, trừ khi cấu hình kế thừa khác đi. **BOM import không mang theo bất kỳ phần build plugin đó.**

### `relativePath` và cách Maven tìm parent

```xml
<parent>
    <groupId>dev.lesson</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../company-parent/pom.xml</relativePath>
</parent>
```

`relativePath` giúp Maven tìm POM cha **trên filesystem** trước khi chuyển sang các nguồn repository phù hợp. Mặc định thường là `../pom.xml`. Nếu muốn tìm qua repository, có thể dùng `<relativePath/>` trong Maven 3 để bỏ kiểm tra path local. Maven xác minh tọa độ parent; **không nên trỏ `relativePath` vào một POM khác GAV** dù có tên file giống nhau.

Điều kiện để parent có hiệu lực: Maven phải dựng được **effective parent model**, kể cả khi parent không được build trong cùng lệnh. Parent vẫn có thể đến từ local/remote Maven repository.

## 4. BOM import: chỉ đưa quy tắc quản lý dependencies vào consumer

BOM (Bill of Materials) thông dụng trong Maven 3 là một POM có `<packaging>pom</packaging>`, tập trung khai `<dependencyManagement>` của một nhóm thư viện tương thích.

Ví dụ `greeting-bom/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.lesson</groupId>
    <artifactId>greeting-bom</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>dev.lesson</groupId>
                <artifactId>greeting-api</artifactId>
                <version>1.0.0</version>
            </dependency>
            <dependency>
                <groupId>dev.lesson</groupId>
                <artifactId>greeting-client</artifactId>
                <version>1.0.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

Một ứng dụng đã kế thừa parent của tổ chức có thể **đồng thời** import BOM của một bộ thư viện khác:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>greeting-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
<dependencies>
    <dependency>
        <groupId>dev.lesson</groupId>
        <artifactId>greeting-client</artifactId>
    </dependency>
</dependencies>
```

Maven đưa các **managed entries** từ effective POM của BOM vào quá trình quản lý dependency của consumer. `greeting-client` xuất hiện vì consumer khai nó trong `<dependencies>`, **không phải** vì import BOM tự thêm nó.

### Quy tắc đặt `scope=import`

Trong Maven 3/POM model 4.0.0, `import` là một scope **đặc biệt**, chỉ sử dụng với dependency có **`<type>pom</type>`** bên trong **`<dependencyManagement>`**.

Sai mục đích:

```xml
<dependencies>
    <dependency>
        <groupId>dev.lesson</groupId>
        <artifactId>greeting-bom</artifactId>
        <version>1.0.0</version>
        <type>pom</type>
        <scope>import</scope>
    </dependency>
</dependencies>
```

Cách trên đặt import trong `<dependencies>` thường, không đúng nơi mà Maven xử lý BOM import.

### `import` không biến dependency thành `compile`

`compile`, `runtime`, `test`, `provided` ảnh hưởng classpath và tính bắc cầu của dependency thực tế. `import` **không phải** scope runtime/compile của một thư viện: nó ra lệnh cho Maven lấy **danh sách dependency được quản lý** từ POM khác. BOM không tạo “một JAR chứa tất cả thư viện”, cũng không tự làm các dependency trong BOM xuất hiện trên classpath.

## 5. Cùng một POM có thể vừa làm parent vừa được import không?

**Có**, nếu POM nguồn là một POM thích hợp với `packaging=pom` và có `<dependencyManagement>`. Trong Maven 3, một project consumer có thể dùng nó theo **một trong hai cách**:

- Child dùng `<parent>`: nhận cơ chế inheritance của parent, gồm cả managed dependencies và những phần build được kế thừa.
- Project khác import nó với `<type>pom</type>`/`<scope>import</scope>`: chỉ nhận nội dung dependency management phù hợp, **không** nhận các properties/pluginManagement của POM nguồn.

Không phải vì file nguồn được đặt tên `*-parent` hoặc `*-bom` mà Maven quyết định phạm vi. **Vị trí và cú pháp tham chiếu trong POM consumer** quyết định Maven sẽ sử dụng nó như quan hệ parent hay BOM import.

Tuy có thể dùng chung một POM cho hai vai trò trong dự án nhỏ, **không phải lúc nào cũng nên gộp** ở hệ thống lớn. Lý do:

1. Thay đổi compiler, test plugin hoặc reporting của parent là thay đổi **build policy**, không nhất thiết cần ép các team khác nâng bộ dependency.
2. BOM là hợp đồng **version alignment** có thể được dùng bởi project đã có parent của họ.
3. Tách parent POM và BOM giúp nâng cấp, tương thích, kiểm thử, quản lý release độc lập hơn.
4. Gộp chúng có thể làm người dùng BOM tưởng đang nhận cả chuẩn build, trong khi thực tế không.

Ví dụ tiếp theo cố ý dùng **chính một POM `shared-platform` cho cả hai vai trò** để chứng minh hai cách hoạt động khác nhau.

## 6. Thực hành Java 17: một platform POM, hai cách tiêu thụ

Ví dụ này gồm bốn Maven project độc lập. Ba mục tiêu quan sát:

1. Cả `parent-app` và `bom-app` cùng dùng được `greeting-api:1.0.0` **không cần khai version ở dependency**.
2. `parent-app` thừa kế `groupId/version`, property `platform.label` và cấu hình compiler từ `shared-platform`.
3. `bom-app` chỉ nhận managed dependency entry. Nó **phải khai riêng** tọa độ project, Java release và compiler plugin configuration/version nếu muốn chủ động cùng tiêu chuẩn build.

### 6.1. Cấu trúc thư mục

```text
inherit-vs-import/
├── greeting-api/
│   ├── pom.xml
│   └── src/main/java/dev/lesson/api/Greeting.java
├── shared-platform/
│   └── pom.xml
├── parent-app/
│   ├── pom.xml
│   └── src/main/java/dev/lesson/parent/App.java
└── bom-app/
    ├── pom.xml
    └── src/main/java/dev/lesson/bom/App.java
```

**Lưu ý:** Không có POM aggregator ở `inherit-vs-import/`, và bốn project **không** được build như một reactor bằng một lệnh duy nhất. Các lệnh bên dưới sử dụng `mvn -f`. Điều này giúp phân biệt rõ **parent/BOM resolution** với **multi-module aggregation**.

### 6.2. Thư viện thật — `greeting-api/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>greeting-api</artifactId>
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

File `greeting-api/src/main/java/dev/lesson/api/Greeting.java`:

```java
package dev.lesson.api;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello from shared API";
    }
}
```

Thư viện không có dependency ngoài. `greeting-api` cung cấp một method tĩnh để hai ứng dụng gọi; version thật của nó là `1.0.0`.

### 6.3. POM dùng chung — `shared-platform/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>shared-platform</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <platform.label>parent-inherited</platform.label>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>dev.lesson</groupId>
                <artifactId>greeting-api</artifactId>
                <version>1.0.0</version>
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
            </plugins>
        </pluginManagement>
    </build>
</project>
```

POM này **có cả**:

- Metadata quản lý dependency `greeting-api:1.0.0`.
- Property `maven.compiler.release=17` và `platform.label=parent-inherited`.
- Compiler Plugin version `3.13.0` trong `pluginManagement`.
- Tọa độ parent tiềm năng `dev.lesson:shared-platform:1.0.0`.

Vì packaging là `pom`, nó không phải một JAR chứa lớp `Greeting`.

### 6.4. Ứng dụng dùng `shared-platform` làm parent — `parent-app/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.lesson</groupId>
        <artifactId>shared-platform</artifactId>
        <version>1.0.0</version>
        <relativePath>../shared-platform/pom.xml</relativePath>
    </parent>

    <artifactId>parent-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>greeting-api</artifactId>
        </dependency>
    </dependencies>
</project>
```

`parent-app` **không khai** các thành phần sau ở top level:

- `groupId`: kế thừa `dev.lesson`;
- `version`: kế thừa `1.0.0`;
- `maven.compiler.release`: kế thừa `17`;
- `platform.label`: kế thừa `parent-inherited`;
- compiler plugin version: có `pluginManagement` từ parent;
- version của `greeting-api`: kế thừa `dependencyManagement` từ parent.

Trong lifecycle `jar`, compiler plugin mặc định sẽ được sử dụng và cấu hình quản lý của parent áp dụng. Vì `maven.compiler.release=17` đã kế thừa, mã của module được biên dịch hướng đến Java 17 nếu JDK/toolchain tương thích.

File `parent-app/src/main/java/dev/lesson/parent/App.java`:

```java
package dev.lesson.parent;

import dev.lesson.api.Greeting;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("parent: " + Greeting.message());
    }
}
```

### 6.5. Ứng dụng chỉ import cùng POM như BOM — `bom-app/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>bom-app</artifactId>
    <version>2.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>dev.lesson</groupId>
                <artifactId>shared-platform</artifactId>
                <version>1.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>greeting-api</artifactId>
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

Tại sao `bom-app` cần những dòng mà `parent-app` không cần?

- `<groupId>` và `<version>2.0.0</version>` là tọa độ của **chính `bom-app`**; BOM version `1.0.0` **không trở thành version của ứng dụng**.
- `<maven.compiler.release>17</maven.compiler.release>` và `project.build.sourceEncoding` được **khai trực tiếp** ở consumer vì BOM import **không kế thừa** properties tương ứng.
- Compiler Plugin version `3.13.0` được khai tại consumer; `pluginManagement` của `shared-platform` **không** đi theo import.
- `greeting-api` không cần version vì imported managed entry từ `shared-platform` đã cung cấp `1.0.0`.

File `bom-app/src/main/java/dev/lesson/bom/App.java`:

```java
package dev.lesson.bom;

import dev.lesson.api.Greeting;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("bom: " + Greeting.message());
    }
}
```

### 6.6. Build bốn project

Yêu cầu: JDK 17+, phiên bản Maven tương thích với Compiler Plugin `3.13.0`, và khả năng tải plugin Maven qua repository/mirror nếu chưa có cache.

Từ thư mục `inherit-vs-import/`:

```bash
mvn -version
mvn -f greeting-api/pom.xml clean install
mvn -f shared-platform/pom.xml install
mvn -f parent-app/pom.xml clean package
mvn -f bom-app/pom.xml clean package
```

**Vì sao thứ tự này đúng?**

1. `greeting-api` được cài vào local Maven repository để cả hai ứng dụng resolve dependency.
2. `shared-platform` được cài dưới dạng **POM artifact**. `parent-app` có thể dùng `relativePath` để tìm parent trên filesystem, còn **`bom-app` cần resolve imported BOM** từ repository. Việc install trước giúp không phụ thuộc một submodule chưa được phát hành.
3. Hai ứng dụng đều build bằng Maven nhưng **qua hai cơ chế nhận cấu hình khác nhau**.

Kết quả chính sau khi build:

```text
greeting-api/target/greeting-api-1.0.0.jar
parent-app/target/parent-app-1.0.0.jar
bom-app/target/bom-app-2.0.0.jar
```

Không có `shared-platform-1.0.0.jar` chứa thư viện ứng dụng; `shared-platform` có packaging `pom`.

### 6.7. Chạy chương trình Java và quan sát stdout

Với **Linux/macOS/Bash**, đứng tại `inherit-vs-import/`:

```bash
java -cp "parent-app/target/parent-app-1.0.0.jar:greeting-api/target/greeting-api-1.0.0.jar" dev.lesson.parent.App
java -cp "bom-app/target/bom-app-2.0.0.jar:greeting-api/target/greeting-api-1.0.0.jar" dev.lesson.bom.App
```

Stdout chính xác của hai ứng dụng, theo thứ tự lệnh:

```text
parent: Hello from shared API
bom: Hello from shared API
```

Với **Windows PowerShell**, dấu phân tách classpath là `;`:

```powershell
java -cp "parent-app\target\parent-app-1.0.0.jar;greeting-api\target\greeting-api-1.0.0.jar" dev.lesson.parent.App
java -cp "bom-app\target\bom-app-2.0.0.jar;greeting-api\target\greeting-api-1.0.0.jar" dev.lesson.bom.App
```

**Quan trọng:** Đây là hai ứng dụng riêng biệt; output trên thể hiện nội dung của hai lần chạy liên tiếp. JAR thông thường không tự đóng gói toàn bộ dependency, nên câu lệnh Java phải đưa `greeting-api` vào runtime classpath. Không mặc định chạy `java -jar` vì chúng chưa cấu hình manifest `Main-Class`.

### 6.8. Kiểm chứng inheritance khác import bằng Maven Help Plugin

Chạy:

```bash
mvn -f parent-app/pom.xml -q help:evaluate -Dexpression=project.groupId -DforceStdout
mvn -f parent-app/pom.xml -q help:evaluate -Dexpression=project.version -DforceStdout
mvn -f parent-app/pom.xml -q help:evaluate -Dexpression=platform.label -DforceStdout
```

Kỳ vọng **ba giá trị** tương ứng:

```text
dev.lesson
1.0.0
parent-inherited
```

Đó là kết quả từ **ba lần gọi Maven**, không phải tự động in ba giá trị trong một command.

Với BOM consumer:

```bash
mvn -f bom-app/pom.xml -q help:evaluate -Dexpression=project.version -DforceStdout
```

Giá trị kỳ vọng:

```text
2.0.0
```

Đây là version do `bom-app` tự khai, **không phải** version `1.0.0` của imported POM.

Thử đánh giá:

```bash
mvn -f bom-app/pom.xml help:evaluate -Dexpression=platform.label
```

Vì `bom-app` không tự khai `platform.label` và không có parent `shared-platform`, imported BOM **không tự mang property `platform.label` sang**. Help Plugin có thể báo expression không có giá trị/không hợp lệ tùy version; không giả định sẽ in đúng chuỗi rỗng. Đây là một phép kiểm tra quan trọng vì BOM đôi khi chứa properties riêng dùng để tính version của các managed entries.

### 6.9. So sánh effective POM và dependency tree

```bash
mvn -f parent-app/pom.xml help:effective-pom
mvn -f bom-app/pom.xml help:effective-pom

mvn -f parent-app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
mvn -f bom-app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Trong effective POM của `parent-app`, hãy tìm:

- `groupId=dev.lesson` và `version=1.0.0` được kế thừa;
- property `platform.label`;
- property `maven.compiler.release=17`;
- managed dependency `greeting-api:1.0.0`;
- compiler plugin version `3.13.0` đến từ `pluginManagement`.

Trong effective POM của `bom-app`, bạn sẽ thấy `groupId=dev.lesson`, `version=2.0.0` **do chính nó tự khai**; managed `greeting-api:1.0.0` có thể xuất hiện do import; Java release và compiler version hiện diện vì **chính BOM app đã khai**, không phải do import. `platform.label` không được kế thừa.

Cây dependency dự kiến về mặt nội dung:

```text
dev.lesson:parent-app:jar:1.0.0
\ - dev.lesson:greeting-api:jar:1.0.0:compile

dev.lesson:bom-app:jar:2.0.0
\ - dev.lesson:greeting-api:jar:1.0.0:compile
```

Cú pháp nhánh và tiền tố log `[INFO]` trong output thực có thể khác. **`shared-platform` không xuất hiện như một JAR dependency thông thường** trong cây của hai ứng dụng: làm parent hoặc import BOM không đồng nghĩa tạo classpath dependency trực tiếp tới artifact POM.

## 7. Nếu POM nguồn có `<dependencies>` thì sao?

Đây là một điểm phân biệt hữu ích trong dự án có parent lớn.

Giả sử POM dùng chung khai trực tiếp:

```xml
<dependencies>
    <dependency>
        <groupId>org.example</groupId>
        <artifactId>runtime-helper</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
```

Đây chỉ là **đoạn minh họa** với tọa độ giả định, không thêm vào ví dụ runnable ở trên.

- Nếu POM này là **parent**, dependency thông thường trong `<dependencies>` của parent **có thể được kế thừa thành dependency của child**, theo cơ chế merge/inheritance.
- Nếu **import POM đó như BOM**, Maven chỉ nhập managed entries của `dependencyManagement`; mục `<dependencies>` thông thường **không** trở thành dependency của consumer.

Vì inherited `dependencies` có thể làm phình classpath của tất cả child, **parent dùng chung thường nên đặt version tại `dependencyManagement` và để child khai dependency thực sự cần** thay vì đưa mọi thư viện vào `<dependencies>` của parent.

## 8. `dependencyManagement` không phải `pluginManagement`

Hai phần này đều dùng chữ “management” nhưng điều khiển **hai cơ chế riêng**.

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>greeting-api</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Quản lý **project dependencies** và có thể ảnh hưởng dependency bắc cầu.

```xml
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
```

Quản lý **plugin version/configuration** cho compiler plugin khi được gọi/bind vào lifecycle.

**BOM import không lấy `pluginManagement` của POM nguồn.** Việc BOM quản lý `greeting-api` không nói gì về compiler plugin; ngược lại, compiler plugin version được đặt trong parent không tự thay version của dependency `greeting-api`.

Không nên dùng dependency management để mong “ép phiên bản transitive dependency của plugin Maven”. Plugin dependencies là classpath riêng của plugin; cần giải quyết với cơ chế cấu hình plugin phù hợp.

## 9. Kế thừa, tổng hợp module và import BOM là ba quan hệ khác nhau

Một POM có thể:

- Được chỉ định là `<parent>` bởi project con → **inheritance**.
- Khai `<modules>` như một POM aggregator → **reactor aggregation**.
- Được import trong `<dependencyManagement>` → **managed-dependency import**.

Ba quan hệ **không tự suy ra nhau**.

Ví dụ:

```xml
<modules>
    <module>service-a</module>
    <module>service-b</module>
</modules>
```

Đoạn `<modules>` cho Maven biết các module tham gia build reactor khi chạy từ POM aggregator. Nó **không bắt buộc** `service-a` và `service-b` kế thừa aggregator làm parent. Ngược lại, child có thể có một parent ngoài repository và vẫn tham gia reactor của aggregator khác.

Một POM có `<packaging>pom</packaging>` cũng **chưa đủ** để gọi nó là BOM theo mục đích sử dụng. Packaging POM chỉ là yêu cầu nền tảng phù hợp, còn nội dung `dependencyManagement` và cách consumer import mới là điểm quyết định.

### Tại sao imported BOM cần có sẵn trước khi consumer dựng model?

Maven phải dựng effective model, bao gồm những import BOM, **trước khi thực hiện compile/package**. Nếu BOM chỉ là một module chưa tồn tại/resolve được trong một build reactor và consumer cố import nó ngay, model building có thể thất bại. Đặc biệt tránh vòng tham chiếu khi một BOM nhập lại POM của consumer hoặc tổ tiên của nó.

Với demo phía trên, `mvn -f shared-platform/pom.xml install` diễn ra trước `mvn -f bom-app/pom.xml clean package` để bảo đảm imported POM có sẵn trong local repository.

## 10. Khi có nhiều BOM, parent và override version

Một tổ chức có thể đặt managed dependencies ở parent, trong BOM import và ngay tại POM ứng dụng. Maven phải hợp nhất các khai báo này để xác định **managed version** và cuối cùng resolve dependency tree.

### Consumer quản lý tường minh một dependency

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>greeting-api</artifactId>
            <version>1.1.0</version>
        </dependency>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>shared-platform</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn minh họa**: nếu consumer tự khai managed version `greeting-api:1.1.0`, nó có thể override entry cùng dependency từ imported BOM. Nhưng `greeting-api:1.1.0` phải thực sự tồn tại và tương thích; không dùng snippet này thay cho file demo mà chưa phát hành phiên bản mới.

### Trực tiếp khai dependency có version

```xml
<dependencies>
    <dependency>
        <groupId>dev.lesson</groupId>
        <artifactId>greeting-api</artifactId>
        <version>1.2.0</version>
    </dependency>
</dependencies>
```

Đây là một **direct dependency** có version được chỉ định; nó không dùng version thiếu trong khai báo để BOM tự điền. Khi muốn tất cả version đến từ BOM, thường nên bỏ `<version>` ở direct dependencies được quản lý.

### Hai imported BOM quản lý cùng một artifact

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>foundation-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>feature-bom</artifactId>
            <version>2.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Nếu hai BOM đều cung cấp managed entry cho **cùng dependency** và consumer chưa có entry cụ thể để override, quy tắc import Maven thông thường là **BOM được import trước thắng** cho entry trùng. Đây không phải quy tắc “chọn phiên bản mới hơn”; càng không phải nearest definition trên dependency graph.

Nếu một dependency nằm trong `dependencyManagement` của parent và cũng được cung cấp qua import trong child, cách merge hiệu lực sẽ ảnh hưởng phiên bản thực tế. Thay vì đoán từ vài đoạn POM, hãy dùng:

```bash
mvn help:effective-pom
mvn dependency:tree
```

Chạy ở đúng project cần kiểm tra. **Effective POM** cho thấy quản lý dependency/plugin và properties sau hợp nhất; **dependency tree** cho thấy artifact/version/scope cuối cùng được dùng.

### Dependency management cũng ảnh hưởng transitives

Nếu một thư viện được kéo qua dependency bắc cầu và consumer quản lý version của thư viện ấy, Maven có thể dùng managed version của consumer thay version mà dependency trung gian đề xuất. Parent và BOM có thể cung cấp cùng loại quản lý này. Điều đó không bảo đảm tương thích ABI; sau khi thay version, cần compile/test/runtime verification.

## 11. Chọn parent, BOM hoặc kết hợp thế nào cho dự án thực tế?

### Trường hợp A: cùng tổ chức, tiêu chuẩn build giống nhau

Nhiều module backend trong một repository dùng chung Java 17, Surefire, JaCoCo, Checkstyle, release process và repositories. **Parent POM** phù hợp vì giúp các module kế thừa một chuẩn build. Đặt dependency versions trong `dependencyManagement`; child chỉ khai dependency thật sự cần.

### Trường hợp B: chia sẻ thư viện cho nhiều team đã có parent riêng

Một team phát hành bộ Java SDK gồm `api`, `client`, `testing`. Các team tiêu thụ có parent công ty hoặc framework khác nhau. **BOM riêng** là lựa chọn phù hợp vì consumer import được phiên bản chuẩn mà **không phải đổi parent** hay kế thừa các plugin không mong muốn.

### Trường hợp C: một project muốn cả tiêu chuẩn build và version của thư viện bên ngoài

Hoàn toàn có thể:

```xml
<parent>
    <groupId>dev.company</groupId>
    <artifactId>company-build-parent</artifactId>
    <version>3.0.0</version>
</parent>

<artifactId>inventory-service</artifactId>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.vendor</groupId>
            <artifactId>vendor-sdk-bom</artifactId>
            <version>2.1.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn trích minh họa**; các artifact `dev.company` và `dev.vendor` chỉ có thể resolve nếu tổ chức thật sự phát hành chúng.

Ý tưởng: parent quản lý **cách build**, BOM quản lý **version dependencies của SDK**. Đây thường là kiến trúc rõ ràng nhất nếu hai phần có vòng đời nâng cấp độc lập.

### Trường hợp D: cùng một POM dùng cho cả hai vai trò

Khả thi như ví dụ Java 17, nhưng cần tài liệu hóa cho người dùng rằng **import không kéo build policy**. Nếu số consumer tăng, cân nhắc tách hai artifact chuyên trách để giảm coupling giữa thay đổi plugin và thay đổi dependency version.

## 12. Nâng cấp và quản lý phiên bản

Khi thay parent:

```xml
<parent>
    <groupId>dev.lesson</groupId>
    <artifactId>shared-platform</artifactId>
    <version>1.1.0</version>
</parent>
```

Project con có thể đồng thời nhận thay đổi ở **managed dependencies, compiler/test plugins, build properties và những cấu hình inherited khác**. Do đó nâng parent thường cần chạy lại build, unit/integration tests và xem effective POM.

Khi nâng BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>shared-platform</artifactId>
            <version>1.1.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Nếu chỉ import như BOM, project tiêu thụ có thể nhận **bộ phiên bản dependency mới**, nhưng **không tự nhận compiler version, parent properties hoặc plugin execution mới** chỉ vì BOM nguồn cũng thay đổi những cấu hình đó.

**Nguyên tắc phát hành:** coi parent và BOM là các API cấu hình của tổ chức. Ghi release notes, version rõ ràng, kiểm thử trước khi nâng, tránh `LATEST`/version động không kiểm soát. Nếu dùng chung một POM cho hai vai trò, ghi rõ những thay đổi ảnh hưởng parent consumers và những thay đổi thực sự ảnh hưởng BOM consumers.

## 13. Các lỗi phổ biến và chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Non-resolvable parent POM` | Parent chưa publish/install, `relativePath` sai, GAV sai, lỗi repository/auth | Xác minh parent GAV, `relativePath` hoặc repository; đừng đổi POM khác tên để “chạy tạm” |
| `Non-resolvable import POM` | BOM chưa có trong local/remote repository, type/version sai | Install/publish BOM riêng trước; kiểm tra `type=pom`, GAV và settings |
| `'dependencies.dependency.version' is missing` | Dependency không có version và không được managed | Kiểm tra effective `dependencyManagement`, BOM import hợp lệ hoặc parent |
| BOM import rồi mà compiler không đổi | Import không kế thừa `pluginManagement` | Cấu hình compiler trực tiếp hoặc kế thừa parent có build policy |
| BOM import rồi `platform.label` không có | Properties của BOM không tự nhập thành properties consumer | Khai property ở consumer/parent, xem biểu thức trong effective POM |
| Child đổi version ngoài ý muốn | Child bỏ `version` nên kế thừa parent | Khai version child nếu release riêng; kiểm tra `project.version` |
| Import BOM không làm JAR xuất hiện | Management không phải dependency declaration | Khai thư viện cần dùng trong `<dependencies>` |
| Trùng version ở nhiều BOM | Thứ tự import, local override hoặc parent management | Kiểm tra effective POM và dependency tree |
| Build reactor lỗi ngay khi BOM chưa build | Import cần resolve POM trong bước model building | Tách BOM và install/publish trước, tránh vòng phụ thuộc |
| Test pass nhưng production lỗi | Managed version tương thích không được kiểm chứng đủ, classpath khác | Chạy integration/smoke tests trên artifact cuối |

**Không dùng HTTP 401/403, lỗi Maven repository hoặc một test compile thất bại để suy ra chắc chắn POM không thể vừa làm parent vừa là BOM**; vấn đề có thể nằm ở quyền truy cập hoặc cách dựng model. Thu thập lỗi nguyên văn và kiểm tra GAV/source POM.

## 14. Những hiểu nhầm cần tránh

**“Cứ `<packaging>pom</packaging>` là BOM.”** Sai. Packaging `pom` có thể dùng cho parent, aggregator, BOM, POM metadata hoặc những kết hợp. BOM import được xác định bởi `dependencyManagement` + `type=pom` + `scope=import`.

**“Import BOM giống kế thừa parent nhưng chỉ bỏ groupId.”** Sai. BOM import không kế thừa gần như toàn bộ model build; nó mang **dependency management**.

**“Cứ import BOM thì mọi thư viện trong BOM có trên classpath.”** Sai. `dependencyManagement` không tự thêm dependency. Các JAR chỉ vào graph nếu có khai dependency thích hợp/đường transitives đủ điều kiện.

**“Đã dùng parent thì không thể import BOM.”** Sai. Một project có một parent trực tiếp nhưng có thể import nhiều BOM và dùng BOM khác với parent của nó.

**“Parent POM nào cũng tự build các module con.”** Sai. Quan hệ `<parent>` không bằng khai `<modules>` trong aggregator; cả hai có thể tồn tại độc lập.

**“BOM import quản lý version của tất cả Maven plugins.”** Sai. Plugin management là cơ chế khác. Đừng lẫn `dependencyManagement` với `pluginManagement`.

**“Property định nghĩa trong BOM chắc chắn gọi được ở project consumer.”** Sai. Những biểu thức trong BOM được xử lý trong effective model của BOM; imported BOM không tự truyền arbitrary properties của nó sang consumer.

**“BOM version phải bằng version của ứng dụng.”** Sai. BOM `1.0.0` có thể quản lý thư viện `1.0.0` hoặc những version khác, trong khi project import BOM có version `2.0.0` như ví dụ.

**“Nâng BOM an toàn vì chỉ đổi số version.”** Không chắc. Nâng version có thể đổi API/ABI, transitive dependencies và hành vi runtime. Cần kiểm tra dependency tree và tests.

## 15. Checklist thực hành

- [ ] Tôi hiểu đang cần **inheritance của build/project model** hay chỉ cần **managed dependency versions**.
- [ ] POM nguồn có packaging `pom` và có managed dependencies phù hợp nếu dùng làm BOM Maven 3.
- [ ] `<parent>` ở cấp project, POM parent resolve được qua `relativePath` hoặc Maven repositories.
- [ ] BOM import nằm **trong `dependencyManagement`**, có `<type>pom</type>` và `<scope>import</scope>`.
- [ ] Khi import BOM, tôi không trông chờ kế thừa compiler/test plugins, properties, groupId hay project version.
- [ ] Project khai những thư viện thực sự dùng trong `<dependencies>`, chỉ bỏ version khi đã được quản lý.
- [ ] Tôi phân biệt `dependencyManagement` với `pluginManagement` và `<modules>` của aggregator.
- [ ] Tôi đã kiểm tra managed-version conflict khi có nhiều BOM hoặc parent dependency management.
- [ ] Tôi đã xem `help:effective-pom` của **đúng consumer** để biết model hiệu lực.
- [ ] Tôi đã xem `dependency:tree` để biết **những JAR thật sự được resolve**.
- [ ] Khi nâng parent hoặc BOM, tôi chạy `mvn clean verify` và các integration tests phù hợp.

**Kết luận:** Dùng một POM làm **parent** nghĩa là **kế thừa một phần lớn mô hình cấu hình project và build**. Import nó như **BOM** nghĩa là **lấy các managed-dependency entries để quyết định version/metadata của thư viện**. Hai cách có thể tham chiếu **cùng một POM `packaging=pom`** nhưng tạo hiệu quả khác nhau: `parent-app` nhận cả property/compiler policy, còn `bom-app` phải tự cấu hình build dù cả hai dùng cùng `greeting-api:1.0.0`.

## Tài liệu chính thức

- [Apache Maven — POM Reference: Inheritance, Parent POM, Dependency Management, Aggregation](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the Dependency Mechanism: Importing Dependencies và BOM](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven Help Plugin — help:effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven — What's New in Maven 4](https://maven.apache.org/whatsnewinmaven4.html)

> Ghi chú phiên bản: Maven 4/model 4.1.0 có thêm BOM packaging chuyên biệt trong những trường hợp hỗ trợ. Bài học này chủ ý dùng cú pháp Maven 3/POM model 4.0.0 phổ biến và có thể được Maven 4 xử lý theo đường tương thích; với tính năng mới hãy đối chiếu hướng dẫn đúng Maven release đang dùng.
