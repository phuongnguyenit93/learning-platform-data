# Phụ thuộc nội bộ và những quan hệ ảnh hưởng thứ tự reactor trong Maven

Một project Maven nhiều module không phải chỉ là “chạy các thư mục theo thứ tự được ghi trong `<modules>`”. **Maven Reactor** thu thập các projects tham gia một lệnh build, xác định **quan hệ phụ thuộc có hiệu lực** giữa chúng, sắp xếp một thứ tự xây dựng hợp lệ, rồi thực hiện các lifecycle phases hoặc plugin goals trên các projects được chọn.

Giả sử workspace có ba module:

```text
core       -> thư viện tính tiền
service    -> dùng core để định dạng hóa đơn
app        -> dùng service để in kết quả
```

Nếu `service` khai báo một **project dependency** lên `core` và `app` khai báo dependency lên `service`, reactor phải xây theo chiều:

```text
core  --->  service  --->  app
```

**Ngay cả khi aggregator viết `<modules>` theo thứ tự ngược là `app`, `service`, `core`, Maven vẫn nhận ra các cạnh phụ thuộc và sắp xếp lại.** Việc sửa thứ tự `<modules>` chỉ để chữa lỗi không resolve được artifact thường không giải quyết được nguyên nhân gốc: sai dependency coordinates, thiếu declaration, lỗi reactor selection hoặc lifecycle phase không tạo artifact cần thiết.

Trong tài liệu **Apache Maven 3 – Guide to Working with Multiple Modules**, các quan hệ được dùng để reactor sorting gồm:
1. **Project dependency** đến một module khác trong build.
2. **Plugin declaration** tham chiếu đến một module trong build.
3. **Plugin dependency** tham chiếu đến một module trong build.
4. **Build extension declaration** tham chiếu đến một module trong build.
5. **Parent relationship** khi parent cũng là một project trong reactor.
6. Cuối cùng, **thứ tự trong `<modules>`** để quyết định giữa các projects không bị ràng buộc bởi những quan hệ trên.

**Quan trọng:** reactor chỉ xét các quan hệ **được instantiated/thực sự khai báo sử dụng**. Những entry chỉ nằm trong `<dependencyManagement>` hay `<pluginManagement>` **không tự tạo cạnh quyết định thứ tự build**.

Bài này làm rõ **aggregation, inheritance, dependency graph và reactor sorting**, thực hành **Java 17 + Maven ba module** với thứ tự module cố tình đảo ngược, thử các lệnh `-pl`, `-am`, `-amd`, `-rf`, `-N` và `-T`, rồi chẩn đoán các trường hợp lỗi do vòng phụ thuộc, phiên bản, package phase, plugin hoặc reactor subset.

Các lệnh và POM chính minh họa hành vi **Maven 3.9.x** với JDK 17+, Maven Compiler Plugin 3.14.1, JUnit Jupiter 5.11.4 và Maven Surefire Plugin 3.6.1. Maven 4 có mô hình subprojects và tùy chọn selection/resume được tài liệu riêng giải thích, nên **không áp mọi chi tiết dưới đây cho Maven 4 mà không kiểm tra khác biệt phiên bản**.

## 1. Ba lớp khái niệm: module, dependency và reactor

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Maven project/module** | POM nào mô tả một đơn vị build? | `core/pom.xml` |
| **Aggregator** | Project nào tập hợp các subprojects để chạy chung? | Root có `<modules>` |
| **Parent POM** | Project nào cung cấp inheritance về properties, dependencies, plugins? | Các child có `<parent>` |
| **Project dependency** | Project nào sử dụng artifact của project nào? | `service` phụ thuộc `core` |
| **Reactor** | Maven thu thập, chọn, sắp xếp và build projects như thế nào trong một invocation? | `mvn clean verify` từ root |
| **Repository** | Artifacts đã install/deploy được resolve ở đâu ngoài reactor? | `~/.m2/repository` hoặc remote mirror |
| **Build lifecycle** | Khi xây một module, Maven chạy tới phase nào? | `compile`, `test`, `package`, `verify` |

Cùng một module có thể vừa là child trong aggregator vừa là library dependency của một module khác. Tuy nhiên:

- **Được liệt kê trong `<modules>`** chỉ có nghĩa project được aggregator thu thập, **không tự có mặt trên compile classpath** của project khác.
- **Có `<parent>`** cho phép inheritance và tạo ràng buộc parent trong reactor, **không tự khai báo project dependency đến JAR của parent**.
- **Có `<dependency>`** mới diễn đạt quan hệ sử dụng artifact trong project dependency graph.
- **Có `<dependencyManagement>`** chỉ quản lý version/scope/defaults khi dependency được dùng thực tế; bản thân nó không đưa library vào classpath hay tự tạo cạnh reactor sorting.
- **Có `<pluginManagement>`** giúp định nghĩa version/configuration khi plugin được sử dụng; bản thân entry quản lý không phải plugin declaration thực tế dùng để xét quan hệ với plugin module.

### 1.1. Aggregation không đồng nghĩa inheritance

**Aggregator POM**:

```xml
<modules>
    <module>core</module>
    <module>service</module>
    <module>app</module>
</modules>
```

nói Maven thu thập ba child projects. **Parent reference** trong child:

```xml
<parent>
    <groupId>dev.training.reactor</groupId>
    <artifactId>reactor-order-lab</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

nói child kế thừa cấu hình từ POM đó. Hai cơ chế thường cùng nằm trên một root project, nhưng **có thể tách biệt**: một aggregator có thể tập hợp projects không kế thừa nó, và một project có thể kế thừa parent POM nhưng không được parent đó aggregate trong build hiện tại.

### 1.2. Thứ tự liệt kê và thứ tự xây dựng

Ví dụ aggregator cố ý ghi:

```xml
<modules>
    <module>app</module>
    <module>service</module>
    <module>core</module>
</modules>
```

Thứ tự này chỉ là input thu thập projects và có thể là **tie-breaker** nếu không tồn tại ràng buộc khác. Nếu có graph:

```text
app    --depends-on--> service
service --depends-on--> core
```

thì thứ tự xây dựng hợp lệ là `core` trước `service` trước `app`. Reactor không chạy theo ý người ghi `<modules>` khi điều đó vi phạm project dependency.

## 2. Cách đọc graph mà không đảo chiều quan hệ

Trong bài, quy ước:

> `A --depends-on--> B` nghĩa là **A cần B**; khi build cần đặt **B trước A**.

Ví dụ:

```text
app --depends-on--> service --depends-on--> core
```

Diễn đạt thứ tự build:

```text
core -> service -> app
```

Hai sơ đồ mô tả **cùng một graph**, nhưng mũi tên trong sơ đồ thứ nhất là **cần**, còn mũi tên trong sơ đồ thứ hai là **được build trước**. Luôn ghi rõ chiều khi thảo luận dependency để tránh đảo ngược.

Nếu hai modules không có quan hệ nào:

```text
docs       tooling
   \        /
    (không có project dependency)
```

Maven có thể dùng thứ tự khai báo modules để phân xử khi build **tuần tự**. Nhưng khi dùng reactor parallel build `-T`, các project độc lập có thể chạy đồng thời; **thứ tự xuất hiện của log không phải một contract tuyệt đối**.

## 3. Sáu quan hệ được Reactor sorting xét đến

### 3.1. Quan hệ 1: Project dependency đến module khác

Đây là trường hợp phổ biến nhất. Trong `service/pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>dev.training.reactor</groupId>
        <artifactId>core</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
```

Khi `core` là module trong reactor cùng `groupId:artifactId:version`, Maven biết `service` cần artifact của `core`. Reactor phải đặt `core` trước `service` theo ràng buộc build.

**Lưu ý:** project dependency không đòi scope `compile`. Những dependency thực sự được khai báo ở scope `test`, `provided`, `runtime`... vẫn có thể tạo quan hệ trong build graph khi trỏ đến module trong reactor, dù chúng có **classpaths/transitivity** khác nhau. Đừng nhầm reactor edge với “classpath compile giống nhau cho mọi scope”.

Một dependency trỏ đến GAV sai hoặc version khác có thể không khớp module nào trong reactor. Khi đó Maven có thể phải resolve artifact từ repository; việc thay `<modules>` không chữa được mismatch này.

### 3.2. Quan hệ 2: Plugin declaration tham chiếu đến module khác

Giả sử một module của reactor thật sự xây dựng **Maven plugin artifact** và module khác khai báo dùng plugin đó trong `<build><plugins>`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>dev.training.reactor</groupId>
            <artifactId>custom-build-plugin</artifactId>
            <version>1.0.0</version>
        </plugin>
    </plugins>
</build>
```

Đây là **snippet khái niệm**, không phải phần của lab ba module. Module `custom-build-plugin` phải là Maven plugin hợp lệ, thường dùng packaging `maven-plugin` và cấu hình descriptor/goal phù hợp. Khi plugin project nằm trong reactor, plugin declaration thực tế là một quan hệ mà reactor sorting có thể sử dụng.

**Đừng coi plugin declaration là project dependency của code ứng dụng.** Plugin chạy trong **Maven build classloader/plugin realm**; nó không tự đưa plugin classes lên application runtime classpath.

### 3.3. Quan hệ 3: Plugin dependency đến module khác

Một plugin được cấu hình có thể cần một JAR helper do một module nội bộ tạo:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <dependencies>
        <dependency>
            <groupId>dev.training.reactor</groupId>
            <artifactId>build-helper</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</plugin>
```

Đây là snippet để phân biệt **`<plugin><dependencies>`** với **project `<dependencies>`**; lab chính không có `build-helper`. Khi `build-helper` là một reactor project, plugin dependency có thể tạo ràng buộc sorting.

Nhưng helper trong plugin realm **không trở thành dependency runtime** của Java application chỉ vì plugin dùng nó. Nếu main source muốn import một class từ helper, project cần dependency phù hợp riêng.

### 3.4. Quan hệ 4: Build extension declaration

Maven hỗ trợ build extensions để mở rộng hành vi build, packaging hoặc lifecycle. Một cấu hình minh họa:

```xml
<build>
    <extensions>
        <extension>
            <groupId>dev.training.reactor</groupId>
            <artifactId>internal-build-extension</artifactId>
            <version>1.0.0</version>
        </extension>
    </extensions>
</build>
```

Nếu `internal-build-extension` là module của build, quan hệ này nằm trong tập reactor sorting được Maven 3 guide liệt kê.

**Cảnh báo thực hành:** build extensions có thể được Maven resolve **rất sớm khi đọc/tạo project model**, trước một số phase. Vì vậy dù reactor nhận biết một quan hệ sorting, không có nghĩa một custom extension chưa từng được build sẽ **luôn tự bootstrap thành công trong cùng một invocation**. Hãy kiểm tra plugin/extension packaging, Maven version, cơ chế resolution, hoặc build/install extension trước nếu thực tế cần.

### 3.5. Quan hệ 5: Parent project ở trong reactor

Một child POM có:

```xml
<parent>
    <groupId>dev.training.reactor</groupId>
    <artifactId>reactor-order-lab</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

Nếu parent project nằm trong tập project của reactor, Maven có quan hệ parent-child để xử lý build order/model. Parent thường dùng packaging `pom` và thường xuất hiện trước children trong reactor summary.

Tuy nhiên, **parent reference không giống dependency JAR**:
- Nó cung cấp inheritance: properties, dependencyManagement, pluginManagement và cấu hình khác.
- Nó không tự đưa artifact Java của parent vào test/runtime classpath child.
- Parent POM có thể đến từ repository ngoài reactor, khi đó không cần một module parent trong build hiện tại.
- `relativePath` là hint về vị trí parent POM trên filesystem, không phải quy tắc khiến một module tự trở thành sibling dependency.

### 3.6. Quan hệ 6: Thứ tự trong `<modules>` để phân xử

Sau khi xét các ràng buộc đã instantiated, Maven mới dùng thứ tự khai báo modules khi cần phân xử giữa các projects độc lập. **Không xem thứ tự trong `<modules>` là giải pháp thay thế dependency declaration.**

Ví dụ có bốn modules `core`, `service`, `app` và `docs`:
- `service` cần `core`.
- `app` cần `service`.
- `docs` độc lập.

Reactor phải bảo đảm `core` trước `service` trước `app`. Module `docs` có thể được đặt theo tie-breaker hoặc chạy đồng thời khi parallel build; không nên cố suy luận “docs phải luôn cuối” chỉ vì `<modules>` ghi nó cuối.

## 4. Hai quản lý không tạo cạnh: dependencyManagement và pluginManagement

### 4.1. dependencyManagement chỉ quản lý khi dependency được dùng

Giả sử parent POM chứa:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.training.reactor</groupId>
            <artifactId>core</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Nó **không tự tạo project dependency từ parent đến `core`**, cũng không khiến mọi child phụ thuộc `core`.

Chỉ khi child thực sự khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>dev.training.reactor</groupId>
        <artifactId>core</artifactId>
    </dependency>
</dependencies>
```

thì entry quản lý mới cung cấp version và tạo một project dependency thực tế, từ đó có reactor edge nếu GAV khớp một module hiện diện.

Một BOM imported qua `dependencyManagement` cũng quản lý versions, không tự biến toàn bộ artifacts được liệt kê trong BOM thành dependencies của project.

### 4.2. pluginManagement không tự kích hoạt custom plugin

Ví dụ parent quản lý:

```xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>dev.training.reactor</groupId>
            <artifactId>custom-build-plugin</artifactId>
            <version>1.0.0</version>
        </plugin>
    </plugins>
</pluginManagement>
```

Đây chỉ là entry quản lý. Khi plugin **được instantiate** bằng declaration/goal execution thực tế trong build, reactor mới xét quan hệ plugin tương ứng.

**Nuance:** pluginManagement vẫn có thể điều chỉnh **version/cấu hình của một plugin đã được lifecycle mặc định bind** (như Compiler/Surefire đối với packaging `jar`). Nhưng chỉ một entry management trỏ đến custom plugin module **không tự kích hoạt plugin mới**, không tự tạo một cạnh build order đến plugin module đó.

## 5. Lab hoàn chỉnh: reactor ba module, modules liệt kê ngược

Ta tạo workspace:

```text
reactor-order-lab/
├── pom.xml                      # parent + aggregator
├── core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/training/reactor/core/MoneyMath.java
│       └── test/java/dev/training/reactor/core/MoneyMathTest.java
├── service/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/training/reactor/service/InvoiceService.java
│       └── test/java/dev/training/reactor/service/InvoiceServiceTest.java
└── app/
    ├── pom.xml
    └── src/main/java/dev/training/reactor/app/BillingCli.java
```

**Phân vai:**
- `core` chỉ phụ thuộc Java 17 standard library; xây độc lập với `service/app`.
- `service` **thực sự phụ thuộc** `core`.
- `app` **thực sự phụ thuộc** `service`, và sử dụng chức năng của `core` gián tiếp.
- Root cố ý đặt `<modules>` = `app`, `service`, `core` để kiểm chứng Maven reactor **không làm theo thứ tự đó** nếu có dependency edges.

Lab dùng Maven 3.9.x, JDK 17+, Maven Compiler Plugin 3.14.1, JAR Plugin 3.4.2, Surefire Plugin 3.6.1 và JUnit Jupiter 5.11.4. Lần đầu cần Maven Central hoặc mirror phù hợp để tải plugins/JUnit.

### 5.1. Tạo các thư mục

Linux/macOS, chạy từ thư mục cha:

```bash
mkdir -p reactor-order-lab/core/src/main/java/dev/training/reactor/core
mkdir -p reactor-order-lab/core/src/test/java/dev/training/reactor/core
mkdir -p reactor-order-lab/service/src/main/java/dev/training/reactor/service
mkdir -p reactor-order-lab/service/src/test/java/dev/training/reactor/service
mkdir -p reactor-order-lab/app/src/main/java/dev/training/reactor/app
cd reactor-order-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "reactor-order-lab/core/src/main/java/dev/training/reactor/core" | Out-Null
New-Item -ItemType Directory -Force -Path "reactor-order-lab/core/src/test/java/dev/training/reactor/core" | Out-Null
New-Item -ItemType Directory -Force -Path "reactor-order-lab/service/src/main/java/dev/training/reactor/service" | Out-Null
New-Item -ItemType Directory -Force -Path "reactor-order-lab/service/src/test/java/dev/training/reactor/service" | Out-Null
New-Item -ItemType Directory -Force -Path "reactor-order-lab/app/src/main/java/dev/training/reactor/app" | Out-Null
Set-Location reactor-order-lab
```

Tạo các tệp POM và Java **đúng đường dẫn** như từng mục sau. Các lệnh `mvn` và `java` về sau giả định working directory là root `reactor-order-lab`.

### 5.2. Parent/aggregator POM đầy đủ: `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training.reactor</groupId>
    <artifactId>reactor-order-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <!-- Cố ý đảo ngược thứ tự logic phụ thuộc -->
    <modules>
        <module>app</module>
        <module>service</module>
        <module>core</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>dev.training.reactor</groupId>
                <artifactId>core</artifactId>
                <version>${project.version}</version>
            </dependency>
            <dependency>
                <groupId>dev.training.reactor</groupId>
                <artifactId>service</artifactId>
                <version>${project.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

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
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.6.1</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

**Quan sát:**
- Root có `<packaging>pom</packaging>`, là aggregator và parent; nó **không tạo main JAR**.
- `<modules>` đặt `app` trước `service` trước `core` một cách cố ý, **không quyết định thứ tự nếu có dependency edges**.
- `<dependencyManagement>` cung cấp version `1.0.0` cho internal artifacts khi children khai báo dependency; **chính management entries không tạo edges**.
- `<pluginManagement>` ghim versions để child project dùng khi plugins được thực thi qua lifecycle/default bindings, **không sinh thêm project dependencies đến các plugin artifact này**.
- Property `maven.compiler.release=17` yêu cầu compiler phù hợp target Java 17.
- Root không có unit test source; không đặt `failIfNoTests=true` cho toàn bộ reactor.

### 5.3. Core POM đầy đủ: `core/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.training.reactor</groupId>
        <artifactId>reactor-order-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

**Core không có project dependency tới `service/app`.** Việc kế thừa parent không tự thêm dependency nội bộ nào. JUnit Jupiter ở scope test để phục vụ `MoneyMathTest`; nó là dependency bên ngoài và không phải cạnh reactor giữa các module lab.

### 5.4. Core Java source: `MoneyMath.java`

Tệp `core/src/main/java/dev/training/reactor/core/MoneyMath.java`:

```java
package dev.training.reactor.core;

public final class MoneyMath {

    private MoneyMath() {
    }

    public static int subtotal(int unitPrice, int quantity) {
        if (unitPrice < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                "price and quantity must be non-negative");
        }
        return Math.multiplyExact(unitPrice, quantity);
    }
}
```

Đây là mã Java 17 đầy đủ. `Math.multiplyExact` phát hiện overflow bằng `ArithmeticException` thay vì âm thầm tràn `int`; phép tính `125 × 3` bằng `375`.

### 5.5. Core unit test: `MoneyMathTest.java`

Tệp `core/src/test/java/dev/training/reactor/core/MoneyMathTest.java`:

```java
package dev.training.reactor.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MoneyMathTest {

    @Test
    void multipliesPriceAndQuantity() {
        assertEquals(375, MoneyMath.subtotal(125, 3));
    }

    @Test
    void rejectsNegativeQuantity() {
        assertThrows(IllegalArgumentException.class,
            () -> MoneyMath.subtotal(125, -1));
    }
}
```

Core có **2 JUnit Jupiter tests**. Surefire plugin được bind ở phase `test` theo packaging `jar` và có version từ parent pluginManagement. Không cần tự thêm execution `surefire:test`.

### 5.6. Service POM đầy đủ: `service/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.training.reactor</groupId>
        <artifactId>reactor-order-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>service</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <!-- Dependency thực tế: tạo cạnh reactor service -> core -->
        <dependency>
            <groupId>dev.training.reactor</groupId>
            <artifactId>core</artifactId>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Không ghi `<version>` trong dependency `core` vì parent `dependencyManagement` đã quản lý version. **Cạnh reactor vẫn tồn tại** vì `service` có entry `<dependency>` thật; `dependencyManagement` chỉ bổ sung version.

Khi gặp lỗi kiểu “version is missing”, kiểm tra parent thực sự được resolve, project đã inherit `dependencyManagement` đúng chưa, và GAV trong dependency có khớp entry quản lý không.

### 5.7. Service Java source: `InvoiceService.java`

Tệp `service/src/main/java/dev/training/reactor/service/InvoiceService.java`:

```java
package dev.training.reactor.service;

import dev.training.reactor.core.MoneyMath;

public final class InvoiceService {

    public String receipt(int unitPrice, int quantity) {
        int value = MoneyMath.subtotal(unitPrice, quantity);
        return "Total: " + value + " VND";
    }
}
```

`InvoiceService` import `MoneyMath` từ `core`. Nếu xóa project dependency `core` trong POM service, compiler không bảo đảm thấy `MoneyMath`. Chỉ liệt kê cả hai modules ở root **không sửa được classpath**.

### 5.8. Service unit test: `InvoiceServiceTest.java`

Tệp `service/src/test/java/dev/training/reactor/service/InvoiceServiceTest.java`:

```java
package dev.training.reactor.service;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class InvoiceServiceTest {

    @Test
    void formatsSubtotalFromCore() {
        InvoiceService service = new InvoiceService();
        assertEquals("Total: 375 VND", service.receipt(125, 3));
    }
}
```

Service có **1 JUnit Jupiter test**. Khi chạy lifecycle trên service với dependencies được resolve đúng, test kiểm tra cả logic service và tương tác với compiled `core`.

### 5.9. App POM đầy đủ: `app/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.training.reactor</groupId>
        <artifactId>reactor-order-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <!-- Dependency thực tế: tạo cạnh reactor app -> service -->
        <dependency>
            <groupId>dev.training.reactor</groupId>
            <artifactId>service</artifactId>
        </dependency>
    </dependencies>
</project>
```

App chỉ khai báo trực tiếp `service` vì source `BillingCli` dùng `InvoiceService`. `service` lại có compile dependency đến `core`, nên Maven dependency mechanism có thể đưa `core` vào app runtime classpath theo transitivity trong tình huống lab.

**Tuy nhiên:** không nên dựa quá lâu vào transitive dependency để import trực tiếp API của `core` ở app. Nếu `BillingCli` thực sự import `MoneyMath`, cân nhắc khai báo `core` là **direct dependency** của `app` để hợp đồng POM rõ ràng, tránh phụ thuộc cấu trúc implementation của `service`.

App không có `src/test/java` trong lab; Surefire ở app có thể không tìm thấy test nào và không fail theo policy mặc định. **Không sao chép `failIfNoTests=true` từ core/service sang mọi module** mà không có quyết định policy rõ ràng.

### 5.10. App Java source: `BillingCli.java`

Tệp `app/src/main/java/dev/training/reactor/app/BillingCli.java`:

```java
package dev.training.reactor.app;

import dev.training.reactor.service.InvoiceService;

public final class BillingCli {

    private BillingCli() {
    }

    public static void main(String[] args) {
        InvoiceService service = new InvoiceService();
        System.out.println(service.receipt(125, 3));
    }
}
```

Class Java 17 này có `main()`, chỉ import API từ module `service`. Kết quả stdout phụ thuộc phép tính `core`, nên đây là một phép thử runtime end-to-end nhỏ về ba modules.

## 6. Chạy build và đọc Maven Reactor Build Order

Từ thư mục root:

```bash
mvn -version
mvn -B -ntp clean verify
```

Maven thu thập root aggregator cùng ba child projects. Vì graph quan hệ:
- Root là parent/aggregator của ba child modules.
- `service` phụ thuộc `core`.
- `app` phụ thuộc `service`.

**Thứ tự hợp lệ mà Maven hiển thị trong Reactor Build Order là:**

```text
reactor-order-lab
core
service
app
```

Đây là **thứ tự dự kiến của project entries**, không phải toàn bộ stdout Maven theo ký tự. Tên hiển thị có thể dựa vào artifactId hoặc `<name>`, và log có các dòng `[INFO]` khác. Điều đáng xác minh là **`core` trước `service` trước `app`, bất chấp `<modules>` khai báo ngược**.

### 6.1. Những gì diễn ra trong build

Với `mvn clean verify` tuần tự:
1. Root POM project được xử lý theo các phases phù hợp với packaging `pom`.
2. Core compile `MoneyMath` và chạy 2 unit tests, rồi tạo `core-1.0.0.jar` ở phase package.
3. Service có thể resolve internal `core` từ reactor, compile `InvoiceService` và chạy 1 unit test, rồi tạo `service-1.0.0.jar`.
4. App resolve internal `service` (và các dependencies cần thiết), compile `BillingCli`, tạo `app-1.0.0.jar`.
5. Maven hoàn tất `verify` ở các module có goals tương ứng; không tự deploy artifacts vì chưa đến phase `deploy`.

Đây là mô tả **theo dependency order**. Maven may dùng reactor artifacts/classes theo phase và type; không phải cứ project đứng trước là tất cả những attached artifacts, classifiers hoặc plugin metadata sẽ tồn tại ở mọi phase.

### 6.2. Nội dung test summary mong đợi

```text
core:    Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
service: Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
app:     No tests to run (theo policy/cấu hình mặc định)
```

Đây là **mô tả thống kê**, không phải stdout Maven chính xác. Kiểm tra log goal `surefire:test`, test class names và báo cáo trong từng `target/surefire-reports` nếu CI cần assert số lượng tests.

### 6.3. Kiểm tra output JARs

Từ root sau build:

```bash
jar --list --file core/target/core-1.0.0.jar
jar --list --file service/target/service-1.0.0.jar
jar --list --file app/target/app-1.0.0.jar
```

Những class entries đặc trưng:

```text
core JAR:    dev/training/reactor/core/MoneyMath.class
service JAR: dev/training/reactor/service/InvoiceService.class
app JAR:     dev/training/reactor/app/BillingCli.class
```

Đây không phải toàn bộ danh sách; JARs còn metadata khác. Trong lab, mỗi JAR chính **không tự gộp** dependencies như Shade/Assembly, nên việc app dùng core/service khi chạy Java bên ngoài Maven cần cấp classpath hợp lệ.

### 6.4. Chạy ứng dụng Java từ ba module outputs

Linux/macOS:

```bash
java -cp "app/target/classes:service/target/classes:core/target/classes" dev.training.reactor.app.BillingCli
```

Windows PowerShell:

```powershell
java -cp "app\target\classes;service\target\classes;core\target\classes" dev.training.reactor.app.BillingCli
```

**Stdout chính xác của chương trình Java `BillingCli.main`:**

```text
Total: 375 VND
```

Đây là output Java application, **khác toàn bộ Maven log**. Không thêm JUnit vào runtime classpath vì app chỉ dùng code production.

### 6.5. Vì sao không chạy `java -jar app/target/app-1.0.0.jar`?

Vì POM lab không đặt `Main-Class` vào manifest và cũng không gộp `service`/`core` vào app JAR. Nếu chạy `java -jar` đơn giản, Java launcher có thể báo không có main manifest attribute hoặc thiếu dependencies.

Đó **không phải lỗi reactor sorting**. Reactors sắp xếp build projects; việc package executable distribution/classpath runtime là mối quan tâm khác.

## 7. Maven reactor chọn projects như thế nào?

Reactor có ít nhất hai câu hỏi tách biệt:
1. **Chọn những projects nào tham gia build?** Do aggregator, `-pl`, `-am`, `-amd`, `-rf`, `-N`... ảnh hưởng.
2. **Sau khi chọn, sắp xếp thứ tự build nào?** Do các relationships thực tế tạo ràng buộc và modules order làm tie-break.

Không trộn **selection** với **sorting**. Nếu project cần thiết đã bị loại khỏi selected reactor, Maven không thể build project đó chỉ bằng cách sắp xếp những cái còn lại.

### 7.1. `-pl` / `--projects`: chọn subset

Từ root lab:

```bash
mvn -B -ntp -pl :service test
```

Lệnh này chủ động chọn project `service` (với selector `:artifactId`). Nó **không tự** đưa `core` vào build nếu bạn không thêm `-am`. Trên máy có local repository cũ chứa `core:1.0.0`, việc build service có thể “tình cờ” thành công với artifact cũ. Trên CI sạch, lỗi `Could not resolve dependencies` có thể xuất hiện.

Muốn chọn module bằng đường dẫn tương đối:

```bash
mvn -B -ntp -pl service test
```

**Phân biệt:** `-pl service` thường hiểu là đường dẫn module tên `service`, còn `-pl :service` là project theo `artifactId`. Với dự án lồng nhiều thư mục và tên artifact khác thư mục, selector `:artifactId` giúp rõ mục tiêu. Có thể dùng GAV selector `groupId:artifactId` để tránh trùng artifactId.

### 7.2. `-am` / `--also-make`: thêm upstream dependencies

```bash
mvn -B -ntp -pl :app -am clean verify
```

Lệnh này chọn `app` và các project cần thiết trong **reactor dependency graph** để xây `app`, trong lab là `service` và `core`; Maven cũng xử lý parent/aggregator phù hợp với reactor selection.

Thứ tự logic:

```text
core -> service -> app
```

**`-am` không có nghĩa “build mọi module ở root”.** Nếu root còn một module `docs` độc lập và `app` không phụ thuộc nó, module đó không nhất thiết được chọn chỉ vì `-am`.

`-am` chỉ có thể đưa vào các projects **đang được reactor biết đến**. Nó không tự clone một repository khác, không tự tạo project không có trong modules, và không tự khởi động database/network service.

### 7.3. `-amd` / `--also-make-dependents`: thêm downstream consumers

```bash
mvn -B -ntp -pl :core -amd clean verify
```

Chọn `core` và các projects **phụ thuộc vào nó** trong reactor. Với graph lab, `service` và `app` là downstream dependents theo dependency chain. Đây là cách hữu ích để chạy kiểm tra tác động khi sửa thư viện core.

So sánh:
- `-pl :app -am`: chọn app và **những gì app cần**.
- `-pl :core -amd`: chọn core và **những gì cần core**.
- `-pl :service -am`: chọn service và core; không bắt buộc app.
- `-pl :service -amd`: chọn service và app; **không tự kèm upstream core chỉ vì -amd**, nên cần cẩn thận nếu local repository chưa có core artifact.

Có thể kết hợp `-am` và `-amd` khi phù hợp, nhưng kiểm tra tập modules được chọn thay vì giả định tất cả đều được đưa vào một cách vô hạn.

### 7.4. `-rf` / `--resume-from`: tiếp tục từ module lỗi

Nếu reactor build dừng ở `service`:

```bash
mvn -B -ntp -rf :service verify
```

yêu cầu tiếp tục danh sách build từ module được chỉ định theo cơ chế Maven 3. **Quan trọng:** `-rf` không có nghĩa tự rebuild mọi upstream dependency mà module lỗi cần. Nếu lần trước chỉ chạy tới `verify`, `core` có thể chưa được **install** vào local repository, nên lệnh resume từ service **có thể fail resolve core trên môi trường sạch**.

Giải pháp:
- Chạy lại root `mvn clean verify` khi chi phí chấp nhận được.
- Hoặc build/install upstream artifacts đúng version một cách kiểm soát trước khi resume.
- Hoặc dùng `-pl :service -am verify` để có upstream modules trong invocation, nếu phù hợp.
- Đừng giải quyết bằng cách đổi dependency version về artifact cũ đang có trong local repository.

Maven 4 có thay đổi với cách chọn subprojects/resume; đối chiếu Maven 4 docs trước khi chuyển pipeline dùng `-r` hoặc các lựa chọn mới.

### 7.5. `-N` / `--non-recursive`: chỉ build project hiện tại

```bash
mvn -B -ntp -N validate
```

Tại root, lệnh này **không đi vào submodules**; nó chỉ xử lý root POM. Nó hữu ích cho thao tác parent metadata, nhưng **không** là lệnh kiểm chứng các Java classes trong `core`, `service`, `app`.

`-N` không xóa `<modules>` khỏi POM vĩnh viễn; nó chỉ thay đổi cách một invocation đi vào reactor.

### 7.6. `-T` / `--threads`: parallel reactor build

```bash
mvn -B -ntp -T 2 clean verify
```

Cho phép Maven chạy reactor projects đồng thời khi không vi phạm dependency relationships và plugin constraints. Trong lab là chuỗi `core -> service -> app`, nên **ba module này vẫn có ràng buộc thứ tự**; thêm threads không làm `app` compile trước `service`.

Với nhiều nhánh độc lập, Maven có thể chạy chúng song song. Khi đó thứ tự timestamp/interleaving log của independent modules có thể khác nhau giữa các lần chạy.

**Đừng nhầm `-T 2` với “hai JUnit test methods chạy đồng thời”.** `-T` là reactor/project-level parallelism; parallel JUnit/Surefire cần framework/plugin configuration riêng.

## 8. Lý do `-am` không thay thế lifecycle phase phù hợp

Reactor sắp xếp projects dựa trên dependencies, nhưng **một dependency có thể cần artifact chưa được tạo ở phase hiện tại**.

Ví dụ:
- Project producer có execution tạo **attached test JAR** bằng `maven-jar-plugin:test-jar` ở phase `package`.
- Consumer khai báo dependency type `test-jar` với classifier `tests`.
- Bạn chạy `mvn -pl :consumer -am test`.

Dù `-am` đưa producer vào reactor trước consumer, producer **chỉ chạy đến phase `test`**; attached test JAR **thường chưa được tạo** vì goal `jar:test-jar` gắn với `package`. Consumer có thể không resolve được classifier artifact trên môi trường sạch.

**Giải pháp:** thiết kế phase/workflow để artifact cần thiết thật sự được tạo, thường là build producer qua `package/verify/install`. Không kỳ vọng topological sorting tự gọi trước mọi plugin goal thuộc phase sau.

Tình huống tương tự với:
- Artifact được tạo bởi `shade:shade` hoặc `assembly:single` ở phase package.
- Plugin artifact cần build descriptor riêng.
- Generated sources/resources chỉ tồn tại sau một goal cụ thể.
- Test fixtures được tạo ở phase `pre-integration-test` nhưng bị yêu cầu sớm ở `test`.

Thứ tự reactor là **project order**, không phải lời hứa rằng mọi output của project upstream luôn có sẵn ở mọi phase.

## 9. GAV, version matching và dependency resolution

Để một dependency internal khớp reactor module, cần kiểm tra **artifact coordinates**:

```text
groupId:artifactId:version
dev.training.reactor:core:1.0.0
dev.training.reactor:service:1.0.0
dev.training.reactor:app:1.0.0
```

Các lỗi:
1. `core` module có `version=1.0.0` nhưng consumer request `core:1.1.0`.
2. Consumer nhập nhầm `groupId`, ví dụ `dev.training.reactors`.
3. POM child không kế thừa parent như tưởng và lấy version khác.
4. `dependencyManagement` trỏ version khác so với reactor project.
5. Project không được liệt kê trong aggregator `<modules>` hoặc đang bị loại bởi `-pl`.
6. Artifact có classifier/type khác main JAR nhưng project chỉ tạo main artifact.
7. Maven chọn một dependency từ local/remote repository cũ vì reactor graph thiếu project tương ứng.

### 9.1. Khi thấy local thành công, CI thất bại

Máy dev có thể còn `core:1.0.0` từ lần `mvn install` trước. Nếu thực tế đang chạy chỉ:

```bash
mvn -pl :app test
```

mà không dùng `-am`, Maven có thể lấy các internal JARs từ local repository. Khi tạo CI sạch không có artifacts đó, lỗi resolution sẽ xuất hiện. Hãy dùng root reactor build hoặc `-pl :app -am` để tránh phụ thuộc **cache tình cờ**.

### 9.2. Scope khác version

`<scope>test</scope>` không thay `groupId:artifactId:version`. Một dependency test-scope vẫn cần đúng artifact và có thể tạo dependency edge. Scope chỉ điều khiển classpath/transitivity theo Maven dependency mechanism.

### 9.3. SNAPSHOT và release mismatch

Nếu parent `version=1.0-SNAPSHOT` nhưng một consumer yêu cầu `core:1.0.0`, đó là hai tọa độ khác nhau. Đừng sửa bằng cách đưa tên core lên đầu `<modules>`; phải thống nhất dependency version hoặc công bố artifact đúng version như ý thiết kế.

## 10. Vòng phụ thuộc giữa modules

Reactor yêu cầu **thứ tự topological hợp lệ**. Nếu `A` cần `B` và `B` đồng thời cần `A`:

```text
A --depends-on--> B
B --depends-on--> A
```

sẽ không thể chọn thứ tự để cả hai được xây trước nhau. Maven có thể báo lỗi graph cycle, chẳng hạn `ProjectCycleException` hoặc thông điệp rằng reactor contains a cyclic reference.

**Không giải quyết vòng phụ thuộc bằng cách đổi thứ tự `<modules>`.** Bạn phải sửa **thiết kế dependency graph**, ví dụ:
- Tách API/interface chung sang module thứ ba `contracts`.
- Đảo chiều bằng dependency inversion: module cấp cao dùng interface, implementation do module thấp/cấu hình runtime cung cấp.
- Chuyển test utilities ra module `test-support` riêng khi test code gây vòng.
- Thay cross-module static calls bằng SPI/ServiceLoader hoặc injection theo kiến trúc phù hợp.
- Không thêm dependency `optional` chỉ để che vòng; optional điều khiển transitivity cho consumer, không phải cách phá dependency cycle trong reactor.

Ví dụ graph đã refactor:

```text
contracts
  |       \
  v        v
module-a  module-b
```

Cả `module-a` và `module-b` dùng `contracts` nhưng không phụ thuộc lẫn nhau, nên có thể build sau `contracts` theo thứ tự ràng buộc.

## 11. Plugin project và build extension: khác library dependency thế nào?

| Quan hệ | Đối tượng được dùng | Nơi hiện diện | Có tạo project dependency classpath Java ứng dụng không? |
| --- | --- | --- | --- |
| `<dependencies><dependency>` | Artifact thư viện | Main/test/runtime classpath theo scope | Có, tùy scope. |
| `<build><plugins><plugin>` | Maven plugin | Build plugin realm | Không tự tạo Java application dependency. |
| `<plugin><dependencies>` | Dependency dành cho plugin | Plugin classloader/realm | Không tự. |
| `<build><extensions>` | Maven build extension | Build/model/extension realm | Không tự. |
| `<parent>` | Parent POM | Inheritance/model | Không tự. |
| `dependencyManagement` | Quản lý dependency coordinates | POM model | Chỉ khi dependency được dùng. |
| `pluginManagement` | Quản lý plugin version/config | POM model | Chỉ khi plugin được dùng. |

Tất cả quan hệ **thực sự được instantiate** có thể ảnh hưởng reactor sorting nếu target module ở reactor. Nhưng **chúng không đồng nghĩa** và không tạo cùng loại classpath.

### 11.1. Maven plugin module cần packaging và descriptor phù hợp

Một Maven plugin nội bộ thường có:

```xml
<packaging>maven-plugin</packaging>
```

cùng plugin annotations/descriptors hoặc cơ chế tương thích. Chỉ lấy một `jar` project bất kỳ, đặt trong `<build><plugins>` rồi kỳ vọng goal chạy được là sai. Phải tham khảo **Maven Plugin Tools** và Maven version hiện hành.

### 11.2. Build extension và bootstrapping

Đặc biệt cẩn trọng với build extensions nội bộ vì Maven có thể cần load extension khi hình thành project model. Reactor sorting là một điều kiện cần nhưng **không phải bảo đảm mọi extension chưa tồn tại trong repository đều bootstrap được**. Dự án lớn thường phát hành extension/build parent trước, hoặc sử dụng cơ chế hỗ trợ bootstrap được xác minh riêng.

### 11.3. Parent version và pluginManagement không thay plugin dependency

Nếu một plugin custom được **quản lý** nhưng child chưa khai báo dùng nó hoặc lifecycle chưa instantiate nó, không có plugin relationship chỉ từ entry `pluginManagement`. Đây là khác biệt quan trọng khi đọc POM lớn: phải nhìn **effective project model và executions thực tế**, không suy luận từ một đoạn management được copy vào parent.

## 12. Failure policies khi build reactor

Maven có các tùy chọn điều chỉnh cách phản ứng khi một module thất bại.

| Tùy chọn | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `-ff` / `--fail-fast` | Dừng reactor khi phát hiện failure, hành vi thường mặc định. | Giảm công việc sau lỗi; dependencies downstream thường bị skip. |
| `-fae` / `--fail-at-end` | Tiếp tục xây các projects độc lập có thể xây, rồi báo failure cuối. | Thích hợp thu thập nhiều lỗi, nhưng vẫn không thể build downstream cần module đã fail. |
| `-fn` / `--fail-never` | Maven tiếp tục/không trả exit failure theo cách dùng lệnh. | Rủi ro lớn trong CI; exit code 0 có thể che build failure. |

Ví dụ khi muốn thu thập nhiều kết quả mà không mất cổng kiểm tra:

```bash
mvn -B -ntp -fae clean verify
```

Nếu `core` fail, `service/app` có thể bị skip do phụ thuộc `core`, trong khi các modules độc lập khác vẫn có thể được build. `-fae` không bắt Maven “bỏ qua mọi dependency graph”.

**Trong CI không dùng `-fn` chỉ để tránh pipeline đỏ**, trừ khi job chỉ có nhiệm vụ chẩn đoán và có gate khác kiểm tra thất bại thật. Lỗi build không biến thành thành công vì đặt cờ này.

### 12.1. Reactor Summary là nguồn quan sát

Trong log Maven, phần `Reactor Summary` cho thấy trạng thái mỗi module: `SUCCESS`, `FAILURE`, `SKIPPED`... Nó hữu ích để xác định module đầu tiên fail, modules downstream bị ảnh hưởng và tổng trạng thái. Tuy nhiên tên hiển thị và định dạng dòng log có thể thay đổi giữa versions/plugins.

Phân tích **goal phát sinh lỗi** (compiler, surefire, jar, plugin resolution, dependency resolution) trước khi sửa reactor order.

## 13. Chẩn đoán khi modules không được build theo kỳ vọng

### Lỗi A — Muốn xây core trước nhưng Maven báo missing class ở service

Nguyên nhân có thể:
- Service thiếu project dependency thực tế tới core.
- `groupId/artifactId/version` không trùng.
- Compiler source import package sai.
- Core không nằm trong selected reactor subset.
- Core artifact type/classifier không đúng.

**Cách xử lý:** kiểm tra `service/pom.xml` và expected GAV. Đừng chỉ đổi `<modules>`.

### Lỗi B — Maven vẫn chạy app trước core

Trước hết xác nhận có **actual project dependency chain** `app -> service -> core`. Nếu root chỉ dùng `dependencyManagement` để liệt kê tên modules, Maven chưa có edges. `<modules>` có thể làm app chạy trước khi không có relationship khác. Khắc phục bằng cách khai báo real dependencies trong modules đúng.

### Lỗi C — project đã build nhưng consumer lấy artifact cũ

Có thể bạn chạy `-pl :app` mà không `-am`, hoặc consumer chạy từ một Maven invocation riêng chỉ resolve repository. Dùng reactor root/`-am` để bao gồm upstream modules, hoặc install/deploy đúng version khi intentionally dùng consumer độc lập.

### Lỗi D — Reactor cycle

`A` cần `B` và `B` cần `A`. Maven không tìm được topological order. Tách interface module, đảo chiều phụ thuộc, hoặc refactor kiến trúc. Đổi thứ tự modules, tắt tests hoặc skip plugin không phải cách giải quyết bản chất.

### Lỗi E — `mvn -rf :service verify` fail dependency resolution

`-rf` trong Maven 3 không tự build upstream modules đã bỏ qua. Nếu `core` chưa được install ở repository, service có thể không resolve artifact. Dùng root build hoặc `-pl :service -am verify`.

### Lỗi F — `-am` đã có upstream mà classifier test JAR vẫn missing

Attached test JAR được tạo ở `package` nhưng bạn chỉ chạy tới `test`. Reactor sort đúng nhưng **phase chưa tạo artifact**. Dùng lifecycle phase phù hợp hoặc thiết kế lại publication of test utilities.

### Lỗi G — Build extension hoặc custom plugin chưa được tải

Plugin/build extension realm có resolution requirements khác project library JAR. Có thể cần publish extension/plugin trước hoặc thay mô hình bootstrap. Đừng thêm dependency này vào main `<dependencies>` chỉ để “ép” thứ tự.

### Lỗi H — Multi-module build bị chậm dù dùng -T

Graph tuyến tính `core -> service -> app` ít khả năng parallel. `-T` chỉ giúp khi có các modules độc lập. Chẩn đoán reactor dependency graph và plugin thread-safety thay vì chỉ tăng số threads.

### Lỗi I — Root POM có modules nhưng chạy -N không thấy submodules

`--non-recursive` được yêu cầu, nên Maven chỉ xử lý project hiện tại. Bỏ `-N` nếu muốn reactor đi vào children.

### Lỗi J — Tests không chạy ở app

App lab không có test source. Nếu CI yêu cầu test mỗi module, cần bổ sung unit tests và cấu hình `failIfNoTests` theo module policy. Đây không phải reactor sorting bug.

## 14. Dependency tree, effective POM và reactor log dùng để kiểm tra gì?

| Công cụ | Câu hỏi được trả lời |
| --- | --- |
| `mvn help:effective-pom` | Effective configuration sau inheritance, management, profiles. |
| `mvn dependency:tree` | Project dependency graph đã resolve theo scope/version mediation. |
| `Reactor Build Order` | Projects được Maven sắp xếp thế nào trong invocation. |
| `Reactor Summary` | Modules nào success/failure/skipped. |
| `mvn -pl ... -am` | Module subset gồm upstream dependencies nào. |
| `mvn -pl ... -amd` | Module subset gồm downstream dependents nào. |
| `jar --list` | Artifact có class/resource gì sau packaging. |

**Không có một lệnh nào thay thế tất cả**:
- `dependency:tree` không liệt kê đầy đủ plugin/build extension/parent relationships như một graph tổng của reactor.
- `effective-pom` cho thấy config sau inheritance, nhưng không tự quyết định mọi module sẽ được chọn bởi CLI flags.
- `Reactor Build Order` cho thấy build schedule, nhưng không chứng minh runtime classpath của Java application đã đúng.
- `jar --list` xác nhận contents, không tự nói dependency scope/transitivity.

### 14.1. Xem effective POM của service

```bash
mvn -B -ntp -pl :service org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom
```

Kiểm tra dependency `core` đã nhận version `1.0.0` từ `dependencyManagement`. Nếu command không resolve plugin trên môi trường offline, cần plugin có trong cache hoặc repository hợp lệ; đừng coi plugin download error là lỗi sorting.

### 14.2. Xem dependency tree từ reactor root

Sau khi build install để artifacts có thể resolve độc lập:

```bash
mvn -B -ntp install
mvn -B -ntp -pl :app org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Trong graph của app, bạn nên thấy `service` và `core` theo dependency graph hiện tại, nhưng định dạng cụ thể có thể khác theo Dependency Plugin version.

Lệnh `mvn install` ghi artifacts vào local repository; nó **không cần cho mỗi lần reactor verify**. Chỉ dùng khi muốn thử independent artifact resolution, plugin calls hoặc tình huống có consumer không nằm cùng reactor.

## 15. Thiết kế reactor graph tốt cho dự án thật

Một cấu trúc đa module phổ biến:

```text
platform-bom       [dependencyManagement]
core-api           [public abstractions]
core-impl          [depends on core-api]
service            [depends on core-api / core-impl]
web-app            [depends on service]
integration-tests  [depends on app/artifact or service]
```

Đừng coi đây là template bắt buộc. Mục tiêu thiết kế là:
- Cạnh phụ thuộc đi **một chiều** theo kiến trúc.
- Tránh vòng phụ thuộc.
- Phân biệt API với implementation.
- Tách những module có lifecycle đặc biệt, như Maven plugin, generated sources, test-fixtures, distribution.
- Sử dụng `dependencyManagement` để thống nhất versions nhưng vẫn khai báo `<dependencies>` ở nơi thực sự dùng.
- Tránh bắt mọi module phụ thuộc một “commons” quá lớn nếu không cần.
- Giữ parent/aggregator POM ổn định và rõ ràng.
- Quản lý publication/repository contract khi modules được build hoặc tiêu thụ độc lập.
- Đặt các integration-test modules ở vị trí cần artifacts được package, không dựa vào may mắn của local cache.

### 15.1. Tại sao nên tách API và implementation?

Nếu `service` và `plugin` cần gọi nhau, bạn có thể tách những interfaces chung sang `api`. Khi đó:
- `service` phụ thuộc `api`.
- `plugin` phụ thuộc `api`.
- Không cần hai bên phụ thuộc lẫn nhau.
- Reactor có thể build `api` trước cả hai.

Thiết kế đó giúp reactor sort đơn giản, build nhanh hơn và versioning rõ hơn.

### 15.2. Không biến aggregator thành “dependency god object”

Một root POM thường làm parent aggregator và quản lý cấu hình. Không nên đưa main code cùng một JAR khổng lồ vào parent chỉ để mọi module “nhìn thấy nhau”. Parent packaging `pom` và `<modules>` có mục tiêu điều phối build/metadata, không phải thay Maven dependency declarations.

## 16. CI pipeline và tránh các build xanh giả

Một pipeline multi-module đáng tin cậy nên:

1. **Chạy từ root aggregator đúng** hoặc chọn `-pl` subset với `-am` thích hợp.
2. **Ghim JDK/Maven versions** để local/CI nhất quán.
3. **Không dựa vào local Maven repository stale artifacts**; thử trên CI sạch hoặc local repo tách biệt khi điều tra.
4. **Ghim versions Maven Compiler/Surefire/JAR plugins** qua parent/pluginManagement.
5. **Kiểm tra Reactor Build Order** sau khi thêm/sửa internal dependencies.
6. **Không chỉ đổi `<modules>`** để giải quyết lỗi classpath.
7. **Chọn phase phù hợp** nếu consumer cần attached classifier artifacts hoặc generated resources.
8. **Dùng `-fae` nếu muốn thu thập failures ở nhánh độc lập**, nhưng vẫn fail CI nếu có module lỗi.
9. **Không dùng `-fn` trong release gate**.
10. **Không assume -rf tự mang upstream artifacts** trên Maven 3.
11. **Không suy luận -T cho phép bỏ quan hệ dependency**; song song chỉ ở những nơi graph cho phép.
12. **Giữ unit tests và reports theo từng module**, đọc `Reactor Summary` và exit code.
13. **Tách integration tests/quality gates** vào phases và modules thích hợp.
14. **Theo dõi groupId/artifactId/version của mỗi module** để tránh lệch reactor/repository resolution.
15. **Xác nhận artifact publish đúng tọa độ**, không deploy đè release immutable.
16. **Chạy smoke test Java với classpath thực** ngoài Maven để kiểm chứng runtime dependency graph.

Lệnh baseline cho lab hoặc nhiều multi-module project nhỏ:

```bash
mvn -B -ntp clean verify
```

Nó xây từ root qua lifecycle đến `verify`, không làm thay deploy. Nếu pipeline còn integration environment hoặc publication constraints, cần cấu hình thêm; `verify` không tự tạo mọi service/container.

## 17. Bài tập tự kiểm tra và đáp án

**Câu 1.** Reactor làm gì?

**Đáp án:** Thu thập modules, sắp xếp projects theo những relationships thực tế và build các projects được chọn.

**Câu 2.** Trong lab, `<modules>` ghi thứ tự `app, service, core`. Build order thực tế là gì?

**Đáp án:** Với Maven 3 chạy tuần tự và parent/graph đã khai báo, thứ tự logic là root parent → `core` → `service` → `app`.

**Câu 3.** Vì sao `service` được build sau `core`?

**Đáp án:** Vì `service/pom.xml` có actual project dependency đến `core` với tọa độ được parent dependencyManagement quản lý.

**Câu 4.** Có `core` trong `<dependencyManagement>` của root đã khiến app phụ thuộc core chưa?

**Đáp án:** Chưa. Management chỉ cung cấp version/defaults, không tự tạo dependency/edge.

**Câu 5.** `<pluginManagement>` khai báo custom plugin module có bắt reactor build module đó trước chưa?

**Đáp án:** Không chỉ bởi entry management. Cần một plugin declaration/usage được instantiate.

**Câu 6.** Kể tên ít nhất bốn loại relationship được Maven 3 reactor sorting xét.

**Đáp án:** Project dependency, plugin declaration, plugin dependency, build extension; còn parent relationship khi parent trong reactor và `<modules>` order để phân xử.

**Câu 7.** Parent POM và aggregator POM luôn là cùng một đối tượng không?

**Đáp án:** Không. Chúng thường kết hợp ở root nhưng inheritance và aggregation là hai khái niệm độc lập.

**Câu 8.** `mvn -pl :app -am clean verify` dùng để làm gì?

**Đáp án:** Chọn `app` và những reactor projects mà app cần; trong lab bao gồm `service` và `core`.

**Câu 9.** `mvn -pl :core -amd clean verify` khác `-am` thế nào?

**Đáp án:** `-amd` chọn những dependents/downstream của core; `-am` chọn dependencies/upstream của project được chỉ định.

**Câu 10.** Vì sao `mvn -pl :app test` đôi khi pass local nhưng fail CI?

**Đáp án:** Có thể local repo có artifacts core/service cũ; nếu không `-am`, các upstream projects không nhất thiết được build trong invocation.

**Câu 11.** `-rf :service` có tự build lại core không?

**Đáp án:** Không mặc định trong Maven 3; nếu core chưa install và bị bỏ khỏi selected reactor, service có thể không resolve được dependency.

**Câu 12.** Có thể sửa cycle `A->B->A` chỉ bằng đổi thứ tự modules không?

**Đáp án:** Không. Cần tách interfaces/contracts, sửa chiều dependencies hoặc refactor graph thành không vòng.

**Câu 13.** `-T 2` có chắc khiến app build trước service không?

**Đáp án:** Không. Parallel reactor vẫn phải tôn trọng dependencies; các module độc lập mới có thể chạy đồng thời.

**Câu 14.** Trong lab, chính xác Java stdout khi chạy `BillingCli.main` là gì?

**Đáp án:** Một dòng `Total: 375 VND`.

**Câu 15.** Root có `packaging=pom` thì tự tạo JAR không?

**Đáp án:** Không trong lifecycle mặc định; các child jar projects tạo artifacts riêng.

**Câu 16.** Vì sao `mvn -pl :consumer -am test` có thể thiếu test JAR của upstream?

**Đáp án:** Attached test JAR được tạo ở phase `package`, trong khi test phase có thể chưa tạo artifact đó; reactor sort đúng không thay lifecycle.

**Câu 17.** `-fae` khác `-fn` ở điểm nào quan trọng đối với CI?

**Đáp án:** `-fae` cố hoàn thành các nhánh độc lập rồi báo failure; `-fn` có thể cho exit code 0 dù build có lỗi, không phù hợp release gate.

**Câu 18.** Project dependency và plugin dependency có đưa class lên cùng application classpath không?

**Đáp án:** Không. Project dependency ảnh hưởng classpath theo scope; plugin dependency nằm trong plugin realm.

**Câu 19.** Nếu dependency `core` ở service trỏ version `1.1.0` nhưng reactor có `core:1.0.0` thì sao?

**Đáp án:** Nó có thể không khớp reactor project, Maven phải resolve version 1.1.0 từ repository hoặc báo lỗi. Phải sửa coordinates/version, không đổi thứ tự modules.

**Câu 20.** Muốn biết module đầu tiên fail trong build nhìn ở đâu?

**Đáp án:** Tên goal/error trong Maven log và `Reactor Summary`; sau đó xem stack trace/compilation diagnostics/report theo module.

## 18. Tài liệu chính thức để đối chiếu

- [Apache Maven – Guide to Working with Multiple Modules (Maven 3)](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor collection, sorting rules, instantiated relationships, `-pl`/`-am`/`-amd`/`-rf` và failure policies.
- [Apache Maven – POM Reference](https://maven.apache.org/pom.html): `<modules>`, aggregation vs inheritance, dependencies, dependencyManagement và pluginManagement.
- [Apache Maven – Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): GAV, scopes, version mediation, transitivity và BOM.
- [Apache Maven – Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): goals/phases và default bindings theo packaging `jar`/`pom`.
- [Apache Maven – Introduction to Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html): profile activation có thể thay đổi modules/dependencies ở những cấu hình phù hợp.
- [Apache Maven Plugin Tools – Introduction](https://maven.apache.org/plugin-tools/): phát triển Maven plugin modules và plugin descriptors.
- [Apache Maven JAR Plugin – jar:test-jar](https://maven.apache.org/plugins/maven-jar-plugin/test-jar-mojo.html): attached test JAR tại phase package, chú ý khi reactor consumer cần classifier.
- [Apache Maven – Maven CLI Options Reference](https://maven.apache.org/ref/current/maven-embedder/cli.html): cú pháp và ý nghĩa các options build.
- [Apache Maven – Maven 4 Multiple Subprojects Guide](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html): điểm khác nhau khi dùng Maven 4, không áp dụng vô điều kiện từ Maven 3.
