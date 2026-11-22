# Phụ thuộc thư viện ngoài và phụ thuộc giữa các mô-đun trong Maven

## 1. Vấn đề thực tế: hai kiểu phụ thuộc, một cơ chế phân giải

Trong một ứng dụng Java, mã nguồn thường cần sử dụng hai nhóm thư viện:

1. **Thư viện ngoài (external dependency):** artifact được phát hành bởi Apache, cộng đồng, nhà cung cấp hoặc tổ chức khác, ví dụ `org.apache.commons:commons-lang3`, JUnit, Jackson hay một thư viện JDBC. Maven lấy artifact và thông tin POM của nó từ local/remote repository theo cấu hình.
2. **Thư viện nội bộ giữa các mô-đun (inter-module dependency):** một module của chính hệ thống cung cấp lớp hoặc API cho module khác. Ví dụ module `app` dùng lớp `Greeter` do module `core` cung cấp.

Với Maven, cả hai đều được khai báo trong **`<dependencies>` của module tiêu thụ**. Maven không dùng một loại thẻ đặc biệt chỉ dành cho “thư viện cùng repository”. Mối quan hệ thực sự được xác định bằng **tọa độ artifact**; Reactor giúp build các module liên quan trong cùng một lần chạy, nhưng **không tự thay thế khai báo dependency**.

```text
                           Maven repositories
                                  │
                                  │ external dependency
                                  ▼
                          commons-lang3.jar
                                  ▲
                                  │ compile dependency
                                  │
        Maven Reactor            core
       ┌────────────┐      ┌───────────────┐
       │  root POM  │      │  core/pom.xml │
       │ modules:   │─────▶│  Greeter.java │
       │  - core    │      └───────────────┘
       │  - app     │                 ▲
       └────────────┘                 │ internal dependency
                                     │
                            ┌──────────────────┐
                            │ app/pom.xml      │
                            │ Main.java, tests │
                            └──────────────────┘
```

Điều cần hiểu và chứng minh bằng thực hành:

- `core` **khai báo trực tiếp** Commons Lang vì mã của `core` gọi API của thư viện đó.
- `app` **khai báo trực tiếp** dependency vào artifact `core` vì mã của `app` gọi `Greeter`.
- Commons Lang có thể đi vào **dependency graph của `app` theo đường bắc cầu** từ `core`, tùy scope và các quy tắc phân giải.
- Root `<modules>` chỉ cho Maven biết những project nào được build cùng lần Reactor; khai báo này không tự đưa class `Greeter` vào classpath của `app`.

Một POM rõ ràng phải diễn tả các quan hệ ở đúng nơi, để build được trên máy mới chứ không chỉ hoạt động vì IDE đã tự gắn thư viện.

## 2. Tọa độ artifact và cách Maven tìm thư viện

Một dependency thường có dạng:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
```

Đây là **đoạn XML đặt bên trong `<dependencies>`**, không phải một `pom.xml` hoàn chỉnh. Các thành phần chính:

| Thành phần | Ý nghĩa | Trong ví dụ |
| --- | --- | --- |
| `groupId` | Nhóm hoặc tổ chức phát hành | `org.apache.commons` |
| `artifactId` | Tên artifact trong nhóm | `commons-lang3` |
| `version` | Phiên bản yêu cầu | `3.14.0` |
| `type` | Loại artifact, mặc định là `jar` cho dependency thông thường | Không cần khai báo |
| `classifier` | Biến thể của cùng artifact nếu có, chẳng hạn `tests` hoặc `sources` | Không dùng |
| `scope` | Các classpath và phạm vi lan truyền dependency | Mặc định `compile` |
| `optional` | Giới hạn sự lan truyền dependency tới dự án tiêu thụ thư viện này | Mặc định không optional |
| `exclusions` | Loại một dependency bắc cầu qua một cạnh cụ thể | Không dùng |

Khi Maven cần dependency, nó tra local repository trước và sử dụng remote repositories/mirrors theo chính sách để tải artifact và POM tương ứng. **Thêm dependency vào POM không đồng nghĩa JAR đó được nhúng vào JAR sản phẩm.** Với packaging `jar` thông thường, Maven biên dịch lớp ứng dụng và tạo JAR của module; các thư viện phụ thuộc vẫn là artifact riêng nếu chưa dùng cơ chế đóng gói phù hợp.

### 2.1. Thư viện ngoài không cần nằm trong mã nguồn

Với Maven, cách đúng là khai báo Commons Lang bằng tọa độ, chốt phiên bản và để công cụ phân giải. Không cần copy `commons-lang3.jar` thủ công vào `src/main/java` hoặc thư mục `lib` rồi thêm classpath chỉ trong IDE.

Cách khai báo này giúp:

- Người mới clone repository và agent CI biết cần artifact nào.
- Maven phân tích được dependency trực tiếp và bắc cầu.
- Có thể quản lý version tại parent POM hoặc BOM.
- Công cụ kiểm tra license, lỗ hổng và dependency graph có dữ liệu có cấu trúc.

Tuy nhiên, phân giải thành công còn phụ thuộc repository được phép, mạng, credentials, local cache, metadata và chính sách artifact của tổ chức. Maven **không đảm bảo** mọi tọa độ tùy ý đều tồn tại.

### 2.2. Phụ thuộc module cũng là phụ thuộc vào artifact

Giả sử `core/pom.xml` có:

```xml
<groupId>edu.demo</groupId>
<artifactId>core</artifactId>
<version>1.0.0</version>
```

Khi `app` cần lớp từ `core`, `app/pom.xml` có dependency:

```xml
<dependency>
    <groupId>edu.demo</groupId>
    <artifactId>core</artifactId>
    <version>1.0.0</version>
</dependency>
```

Ở đây `edu.demo:core:1.0.0` có ý nghĩa như mọi artifact Maven khác. Maven có thể tìm bản phù hợp trong Reactor đang chạy hoặc trong repository đã có artifact, tùy lệnh và ngữ cảnh. Đường dẫn thư mục `../core` **không phải** thành phần của dependency declaration.

Nếu hai module ở chung repository nhưng `app` không khai báo `core` làm dependency, việc root chứa cả hai trong `<modules>` chưa đủ để `app` biên dịch được dòng `import edu.demo.core.Greeter;`.

## 3. Ba quan hệ thường bị nhầm trong dự án nhiều module

| Quan hệ | Khai báo | Chức năng |
| --- | --- | --- |
| Kế thừa POM | `<parent>` trong POM con | Nhận cấu hình, properties, dependency/plugin management theo quy tắc Maven |
| Tổng hợp module | `<modules><module>...` trong POM root | Thu thập các project cho một lần Maven Reactor build |
| Phụ thuộc artifact | `<dependencies><dependency>...` tại module tiêu thụ | Cho mã của module biết thư viện nào cần cho compile/runtime/test |

Có thể sử dụng cả ba trong một dự án, nhưng **chúng không thay thế nhau**. Ví dụ module `app` kế thừa cùng POM cha với `core` không khiến `app` tự import được class của `core`. Việc cha quản lý version của `core` trong `dependencyManagement` cũng **không** khiến `core` tự xuất hiện trên classpath của mọi module con.

Maven Reactor sắp xếp các project dựa trên quan hệ đã khai báo, trong đó **dependency thực giữa project** là một cơ sở quan trọng. Thứ tự tên module trong `<modules>` không phải chỉ dẫn bắt buộc build `app` trước `core` khi `app` phụ thuộc `core`. Một entry trong `dependencyManagement` **không tự tạo dependency edge** để Reactor dựa vào đó sắp xếp.

## 4. Ví dụ hoàn chỉnh: core dùng Commons Lang, app dùng core

Ví dụ dưới đây là một dự án Java 17 nhiều module, có test JUnit Jupiter. Nó minh họa **dependency thư viện ngoài**, **dependency nội bộ**, **dependency bắc cầu**, cách Maven Reactor build và cách tạo **runtime classpath** để chạy từ terminal.

Các phiên bản nêu dưới đây là lựa chọn cụ thể để ví dụ có thể kiểm tra, **không phải khẳng định phiên bản mới nhất**. Cần JDK 17 trở lên, Maven 3 tương thích, và quyền tải các dependency/plugin từ repository được cho phép.

### 4.1. Cấu trúc tệp

```text
dependency-demo/
├── pom.xml
├── core/
│   ├── pom.xml
│   └── src/main/java/edu/demo/core/Greeter.java
└── app/
    ├── pom.xml
    ├── src/main/java/edu/demo/app/Main.java
    └── src/test/java/edu/demo/app/GreeterTest.java
```

Root giữ cấu hình chung và liệt kê hai module. `core` là thư viện. `app` chứa chương trình chính và một bài unit test.

### 4.2. Root pom.xml: parent + aggregator

Tệp `dependency-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>dependency-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <commons-lang3.version>3.14.0</commons-lang3.version>
        <junit.version>5.10.2</junit.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>${commons-lang3.version}</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${junit.version}</version>
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
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.2.5</version>
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

Giải thích:

- `packaging=pom` và `<modules>` khiến root đóng vai trò **aggregator**. Root không tự tạo JAR ứng dụng.
- Các POM con ở dưới sẽ khai báo `<parent>` để kế thừa groupId/version và thuộc tính Java 17.
- `dependencyManagement` **quản lý phiên bản** của Commons Lang và JUnit; chưa đặt hai thư viện vào mọi module.
- `pluginManagement` quản lý phiên bản Compiler/Surefire/JAR Plugin; các binding chuẩn của module packaging `jar` áp dụng goal tương ứng khi build.
- Cấu hình dùng `maven.compiler.release=17` nhưng Maven vẫn phải chạy cùng JDK hỗ trợ Java 17. Nó không tự tải JDK.

### 4.3. core/pom.xml: khai báo thư viện ngoài

Tệp `dependency-demo/core/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>edu.demo</groupId>
        <artifactId>dependency-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
    </dependencies>
</project>
```

Module `core` **thực sự sử dụng Commons Lang** vì có một dependency nằm trong `<dependencies>`. Version bị lược bỏ trong POM con vì parent đã quản lý nó. Scope cũng bị lược bỏ, tương đương **`compile`** trong trường hợp mặc định.

Tệp `dependency-demo/core/src/main/java/edu/demo/core/Greeter.java`:

```java
package edu.demo.core;

import org.apache.commons.lang3.StringUtils;

public final class Greeter {
    private Greeter() {
    }

    public static String greeting(String name) {
        if (StringUtils.isBlank(name)) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + StringUtils.capitalize(name.trim()) + "!";
    }
}
```

Lớp này thực sự gọi `StringUtils.isBlank()` và `StringUtils.capitalize()` từ thư viện ngoài. Vì thế `core` cần Commons Lang trên **compile classpath** và trên **runtime classpath** của chương trình nào sử dụng `Greeter`.

### 4.4. app/pom.xml: khai báo phụ thuộc giữa module và dependency test

Tệp `dependency-demo/app/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>edu.demo</groupId>
        <artifactId>dependency-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>

    <dependencies>
        <dependency>
            <groupId>edu.demo</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.6.1</version>
                <executions>
                    <execution>
                        <id>copy-runtime-libraries</id>
                        <phase>prepare-package</phase>
                        <goals>
                            <goal>copy-dependencies</goal>
                        </goals>
                        <configuration>
                            <includeScope>runtime</includeScope>
                            <outputDirectory>${project.build.directory}/lib</outputDirectory>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích các quan hệ:

- `app` kế thừa từ parent, nhưng **dependency vào `core` phải được khai báo riêng**. Version `${project.version}` của module này là `1.0.0`; cách đó phù hợp ví dụ khi các module phát hành cùng version. Nếu module dùng version riêng, phải khai báo đúng version của `core`.
- `junit-jupiter` chỉ là dependency **test** của `app`; version được quản lý tại parent. Nó không tự lan vào runtime sản phẩm.
- Goal `maven-dependency-plugin:copy-dependencies` được gắn vào `prepare-package` để tạo thư mục `app/target/lib` chứa những dependency cần khi chạy. `includeScope=runtime` trong goal này bao gồm dependency scope `runtime` và `compile`, **không bao gồm dependency chỉ dùng cho `test`**.
- Đây là một lựa chọn **chỉ phục vụ việc chạy demo bằng lệnh `java -cp`**. Việc copy các JAR ra `target/lib` không biến `app-1.0.0.jar` thành “fat JAR”. Trong dự án thực tế có thể dùng distribution, Maven Shade Plugin, launcher hoặc container image tùy cách triển khai.

Tệp `dependency-demo/app/src/main/java/edu/demo/app/Main.java`:

```java
package edu.demo.app;

import edu.demo.core.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greeting("maven"));
    }
}
```

Tệp `dependency-demo/app/src/test/java/edu/demo/app/GreeterTest.java`:

```java
package edu.demo.app;

import edu.demo.core.Greeter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreeterTest {
    @Test
    void formatsValidName() {
        assertEquals("Hello, Maven!", Greeter.greeting("maven"));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                     () -> Greeter.greeting("   "));
    }
}
```

Hai test gọi API công khai của module `core` qua dependency `app → core`. Chúng gián tiếp sử dụng Commons Lang vì phương thức `Greeter.greeting` dùng nó ở runtime. `app` **không cần khai báo Commons Lang trực tiếp** trong ví dụ bởi mã nguồn `app` không import API Commons Lang.

### 4.5. Chạy build và chương trình

Từ thư mục `dependency-demo/`:

```bash
mvn -B clean verify
```

Maven Reactor thu thập root, `core`, `app` và xây theo quan hệ dependency. Thông thường `core` được đóng gói trước khi `app` cần artifact đó. Với ví dụ đúng và môi trường có Maven/JDK/repository phù hợp:

- Module `core` biên dịch `Greeter.java` và tạo `core/target/core-1.0.0.jar`.
- Module `app` biên dịch `Main.java`, biên dịch `GreeterTest.java` và Surefire thực thi **2 test thành công**.
- Trong `prepare-package` của `app`, Dependency Plugin sao chép các thư viện runtime vào `app/target/lib`.
- Module `app` tạo JAR `app/target/app-1.0.0.jar`.

Các tệp quan trọng sau build:

```text
core/target/core-1.0.0.jar
app/target/app-1.0.0.jar
app/target/classes/edu/demo/app/Main.class
app/target/test-classes/edu/demo/app/GreeterTest.class
app/target/lib/core-1.0.0.jar
app/target/lib/commons-lang3-3.14.0.jar
app/target/surefire-reports/...
```

Sơ đồ chỉ ghi các đầu ra cần quan sát; các plugin có thể tạo thêm file/thư mục khác. Để xác minh thư viện runtime được copy đúng, kiểm tra file trong `app/target/lib`; nếu không có thì xem log của goal `copy-dependencies` và cấu hình scope.

**Linux/macOS**, tại thư mục root:

```bash
java -cp "app/target/classes:app/target/lib/*" edu.demo.app.Main
```

**Windows PowerShell**, tại thư mục root:

```powershell
java -cp "app\target\classes;app\target\lib\*" edu.demo.app.Main
```

Stdout **của lệnh Java riêng này** là:

```text
Hello, Maven!
```

Dấu `:` tách classpath entry trên Unix; Windows dùng dấu `;`. Mẫu `lib/*` là cú pháp Java classpath wildcard để đưa các JAR trực tiếp trong thư mục đó vào classpath; không cần shell tự mở rộng wildcard. `app/target/classes` chứa lớp `Main`, còn `app/target/lib` chứa `core` và thư viện ngoài cần thiết.

Không dùng `java -jar app/target/app-1.0.0.jar` cho ví dụ này: chưa khai báo `Main-Class` trong manifest và JAR thường cũng chưa chứa dependency. Nếu muốn tạo executable JAR hoặc fat JAR cần cơ chế đóng gói riêng và kiểm tra runtime classpath thực tế.

### 4.6. Chứng minh tính bắc cầu bằng dependency graph

Đứng ở root, chạy:

```bash
mvn -pl :app -am org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

`-pl :app` chọn project có artifactId là `app`; `-am` đưa những project cần thiết trong Reactor vào lần chạy. Goal `tree` có thể in cây dependency của nhiều project được chọn, tùy Reactor; hãy tìm phần ứng với `app`.

Đường quan hệ **về ý nghĩa** cần thấy:

```text
edu.demo:app:jar:1.0.0
+- edu.demo:core:jar:1.0.0:compile
|  \- org.apache.commons:commons-lang3:jar:3.14.0:compile
\- org.junit.jupiter:junit-jupiter:jar:5.10.2:test
   \- ... các thành phần JUnit cần thiết ...
```

Đây là **sơ đồ giản lược, không phải log Maven nguyên văn**; cây thực tế có thêm các dependency bắc cầu của JUnit, các nhánh và định dạng theo Maven Dependency Plugin. Cái cần nhận diện là `app → core → commons-lang3`, và JUnit nằm ở nhánh `test`.

Có thể lọc để kiểm tra Commons Lang:

```bash
mvn -pl :app -am org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -Dincludes=org.apache.commons:commons-lang3
```

Khi lọc, các dòng giữa đường phụ thuộc vẫn có thể xuất hiện để thể hiện cha của artifact khớp. Phạm vi `-am` không cài artifact vĩnh viễn vào local repository; nó dùng module có trong Reactor hiện tại.

## 5. Direct dependency, transitive dependency và quy tắc khai báo đúng chỗ

### 5.1. Trực tiếp và bắc cầu

Trong ví dụ:

- Đối với `core`, Commons Lang là **direct dependency**: nó xuất hiện trực tiếp trong `core/pom.xml`.
- Đối với `app`, `core` là **direct dependency**.
- Đối với `app`, Commons Lang là **transitive dependency** theo cạnh `app → core → commons-lang3`.

Maven đọc POM của các dependency để tạo **dependency graph**. Maven có thể thu thập nhiều cấp bắc cầu, sau đó áp dụng scope, optional, exclusions, dependency management và conflict mediation để tính classpath cuối cùng.

**Quy tắc thực tế:** module nào trực tiếp `import` và gọi API của một thư viện thì nên khai báo dependency trực tiếp vào thư viện đó. Đừng cố tình dùng một thư viện ngoài chỉ vì nó tình cờ xuất hiện qua dependency khác. Nếu ngày mai `core` thôi dùng Commons Lang, dependency bắc cầu trong `app` có thể mất; khi đó mã `app` đang trực tiếp `import StringUtils` có thể đột nhiên không biên dịch.

### 5.2. Vì sao cùng một JAR có thể xuất hiện ở nhiều đường?

Hãy tưởng tượng:

```text
app
├── lib-a:1.0 ──> common-util:1.2
└── lib-b:2.0 ──> common-util:2.0
```

Trong Maven 3, quy tắc mediation phổ biến là **nearest definition**: version nằm gần module tiêu thụ hơn trong cây được ưu tiên; khi bằng độ sâu, thứ tự khai báo có thể quyết định. **Đây không phải thuật toán luôn chọn bản mới nhất.**

Để tránh phụ thuộc vào vị trí ngẫu nhiên trong cây, hãy quản lý/khai báo version có chủ đích trong POM hoặc `dependencyManagement`. Sau mỗi thay đổi, đọc `dependency:tree` và chạy test, bởi một version được chọn về mặt phân giải chưa chắc đã tương thích về mặt API/binary.

### 5.3. Cấu trúc dependency graph không giống đóng gói runtime

`dependency:tree` trả lời “những artifact nào được Maven phân giải trong graph với scope nào?”. Nó không tự chứng minh file JAR cuối cùng chứa toàn bộ lớp và dependency runtime.

Có thể có:

- **JAR thường:** chứa lớp/resource của chính module, dependency cần được cấp qua classpath riêng.
- **WAR:** phân chia thư viện theo quy tắc đóng gói webapp và `provided`.
- **Executable/fat JAR:** do plugin hoặc framework đóng gói thư viện theo cơ chế riêng.
- **Container image:** copy artifact và dependency vào image theo Dockerfile/build pipeline.

Trước khi triển khai, hãy xác minh phương thức đóng gói của chính dự án, không suy từ việc `mvn package` trả về `BUILD SUCCESS`.

## 6. Dependency scope: một thư viện xuất hiện ở classpath nào?

Scope ảnh hưởng việc Maven dùng dependency ở **compile**, **runtime**, **test** và cách nó lan truyền. Trong POM Java thông thường:

| Scope | Dùng ở đâu? | Ví dụ | Lưu ý khi áp dụng |
| --- | --- | --- | --- |
| `compile` (mặc định) | Compile, runtime và test classpath | Commons Lang được `core` import | Có thể lan truyền tới module tiêu thụ |
| `provided` | Compile và test, nhưng không trên runtime classpath thông thường | Servlet API do container cấp | Không nên tự đóng gói trùng với container |
| `runtime` | Runtime và test, không ở compile classpath thông thường | JDBC driver khi mã compile theo `java.sql` | Không phù hợp nếu mã chính import trực tiếp lớp thư viện đó |
| `test` | Biên dịch và thực thi test của module hiện tại | JUnit, Mockito | Không lan truyền thành dependency test của ứng dụng tiêu thụ |
| `system` | Dùng file local được chỉ định thủ công | Legacy JAR không xuất bản | Nên tránh vì khó tái lập và Maven không tải nó qua repository |
| `import` | Chỉ dùng với `type=pom` trong `dependencyManagement` | BOM | Không phải scope classpath cho dependency Java thông thường |

**Một scope cụ thể có thể biến đổi qua đường bắc cầu**, không phải mọi dependency mang `compile` ở một project con đều nhất thiết giữ nguyên scope khi tới mọi project ở xa. Ví dụ nếu `app` khai báo `core` là `test` dependency, Commons Lang của `core` không trở thành dependency compile cho ứng dụng `app`.

Thử tình huống sai:

```xml
<dependency>
    <groupId>edu.demo</groupId>
    <artifactId>core</artifactId>
    <version>1.0.0</version>
    <scope>test</scope>
</dependency>
```

Nếu đặt đoạn này vào `app/pom.xml` của ví dụ, mã `Main.java` vốn import `Greeter` sẽ không còn dependency đó trong compile classpath sản phẩm và **có thể thất bại ở phase `compile`**. Scope `test` chỉ hợp lý khi `core` thực sự được dùng trong test của `app`, không phải trong mã sản phẩm.

Ngược lại, để `junit-jupiter` ở `scope=test` là đúng vì `GreeterTest.java` dùng nó, còn `Main.java` không cần JUnit khi chạy.

## 7. Quản lý phiên bản: dependencies khác dependencyManagement

### 7.1. Một nơi quy định version, từng module tự chọn thư viện cần dùng

Trong root của ví dụ:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn POM**, có ý nghĩa “nếu các module thừa hưởng khai báo dependency tương ứng mà không chọn version riêng, hãy dùng version đã quản lý”. Nó **không** tự thêm Commons Lang vào mọi module.

`core` vì dùng `StringUtils` nên khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
```

`app` không import Commons Lang nên không cần direct declaration cho Commons Lang. Nếu sau này `app` bắt đầu import `StringUtils`, hãy thêm direct dependency vào `app` thay vì phụ thuộc vào sự tồn tại ngẫu nhiên của cạnh bắc cầu.

### 7.2. Quản lý version giữa các module

Khi các module phát hành cùng version, phụ thuộc `core` ở `app` có thể dùng `${project.version}` như trong ví dụ. Đây là quy ước thiết kế của repository, **không phải yêu cầu bắt buộc của Maven**.

Nếu `core` có version `2.4.0` còn `app` có version `1.7.0`, dùng `${project.version}` trong dependency `core` có thể chọn **sai tọa độ**. Khi module có vòng đời version khác nhau, cần quản lý dependency version của `core` rõ ràng (ví dụ property hoặc `dependencyManagement` được kiểm soát). Không dùng đường dẫn thư mục để thay thế version.

### 7.3. BOM giải quyết bộ version, không tự thêm thư viện

BOM là một POM mang danh sách quản lý dependency. Một module/parent có thể import BOM trong `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.platform</groupId>
            <artifactId>platform-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Tọa độ `com.example.platform:platform-bom:1.0.0` là **ví dụ giả định**, không phải artifact cần tải để chạy demo ở phần 4. BOM hữu ích khi quản lý nhiều thư viện tương thích nhau nhưng **không tạo một dependency runtime** hay buộc tất cả module phải dùng toàn bộ thư viện trong BOM.

### 7.4. Plugin dependency không phải application dependency

`<dependencies>` của project quyết định classpath ứng dụng/test. `<build><plugins>` và `<plugin><dependencies>` có vai trò khác: cấu hình công cụ thực thi build và thư viện phục vụ chính plugin. Không thêm Commons Lang vào dependency của Compiler Plugin rồi kỳ vọng `Main.java` nhìn thấy nó, cũng không dùng project `<dependencies>` để “cài thêm plugin Maven”.

## 8. Reactor: khi nào dependency nội bộ được giải quyết từ source, khi nào cần artifact?

### 8.1. Build cả Reactor

Từ root có `<modules>`:

```bash
mvn -B clean verify
```

Maven thu thập tất cả module, dựng dependency graph giữa các project và xây theo thứ tự có thể đáp ứng yêu cầu. Trong ví dụ, `core` được xây trước `app` vì `app` phụ thuộc `core`. Module `app` có thể dùng artifact của `core` trong **cùng Maven session** mà không cần người dùng chạy `mvn install` trước.

Điều đó khác với thao tác mở riêng terminal ở module `app` mà không cung cấp module `core` cho Reactor: khi đó Maven có thể phải tìm artifact `edu.demo:core:1.0.0` trong local/remote repository.

### 8.2. Chỉ build app và những module app cần

Từ root:

```bash
mvn -B -pl :app -am clean verify
```

- `-pl :app` chọn project có artifactId là `app`.
- `-am` yêu cầu build thêm các project trong Reactor mà `app` cần, ví dụ `core` (và các project liên quan theo quy tắc Reactor).
- `clean verify` chạy các lifecycle phase trên tập project được chọn.

Không nhầm với:

```bash
mvn -B -pl :app verify
```

Lệnh không có `-am` **không tự thêm `core`**. Trên máy đã có artifact `core` phù hợp trong cache, nó có thể vẫn chạy được, nhưng trên agent sạch có thể thất bại với lỗi không phân giải được `edu.demo:core:1.0.0`.

### 8.3. Build riêng module và lệnh install

Có thể dùng:

```bash
mvn -B -pl :core -am install
```

Khi thành công, artifact `core` được cài vào local repository của **môi trường đang chạy lệnh**. Sau đó, nếu POM cha và các dependency cần thiết cũng phân giải được, một build `app` tách riêng có thể tìm `core` qua local repository.

Nhưng `mvn install` **không xuất bản artifact lên remote repository** để mọi máy khác truy cập. Khi CI chạy trên agent mới, artifact chỉ tồn tại trong local repository của agent cũ không giúp CI phân giải được. Muốn chia sẻ artifact đã phát hành giữa các build độc lập, tổ chức phải dùng repository/artifact publication được kiểm soát.

### 8.4. Dependency vòng tròn giữa module

Nếu `core` khai báo dependency `app` và `app` khai báo dependency `core`, Maven Reactor có thể không sắp xếp được vì **circular dependency**. Giải pháp là sửa thiết kế API/module: đưa interface hoặc mã dùng chung vào một module thấp hơn, hoặc thay đổi hướng phụ thuộc. Đảo thứ tự `<module>` trong root không chữa được một chu trình dependency thực.

## 9. Optional và exclusions: kiểm soát dependency bắc cầu

### 9.1. Optional dependency

Một thư viện có thể khai báo một dependency để hỗ trợ một tính năng tùy chọn:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>optional-adapter</artifactId>
    <version>1.0.0</version>
    <optional>true</optional>
</dependency>
```

Đây là **minh họa**, không phải artifact chạy được trong demo. Với project khai báo dependency này, thư viện vẫn có thể được sử dụng trong code của project đó. Nhưng khi một project khác phụ thuộc vào project ấy, dependency optional **không tự lan truyền** tới project tiêu thụ.

Nếu một ứng dụng thực sự cần adapter tùy chọn, nó nên khai báo dependency trực tiếp ở POM của nó. Đừng đánh dấu `optional=true` chỉ để che lỗi download; có thể tạo lỗi `ClassNotFoundException` ở runtime khi người tiêu thụ gọi tính năng cần adapter.

### 9.2. Exclusions

Giả sử một thư viện bên thứ ba kéo theo một artifact cũ mà dự án không muốn dùng. Có thể loại nó **trên cạnh dependency đang kéo theo artifact**:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-sdk</artifactId>
    <version>2.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>unneeded-codec</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Các tọa độ `com.example` trong đoạn này là **placeholder minh họa**, không nằm trong dự án runnable. Exclusion không phải cơ chế gỡ một artifact ra khỏi **mọi** đường dependency trên toàn graph: nếu còn một đường khác kéo artifact đó, nó vẫn có thể xuất hiện.

Chỉ dùng exclusions khi đã kiểm tra lý do và kết quả `dependency:tree`, rồi chạy test tích hợp. Loại một thư viện đang được code ở runtime sử dụng có thể khiến build biên dịch thành công nhưng ứng dụng lỗi `NoClassDefFoundError`.

### 9.3. Kiểm soát version conflict có hệ thống

Nếu hai thư viện cần version khác nhau của cùng một artifact, Maven chọn theo quy tắc dependency mediation. Việc thêm `<dependencyManagement>` có thể giúp chốt version, nhưng phải xác minh khả năng tương thích. Một bản thư viện mới không đảm bảo API cũ còn tồn tại hoặc bytecode phù hợp JDK đang chạy.

Ưu tiên các version cụ thể được phê duyệt và dependency graph có thể kiểm chứng; hạn chế version range, snapshot không kiểm soát và các mẹo ép classpath khác biệt giữa IDE/CI.

## 10. Kiểm tra classpath và dependency graph một cách có bằng chứng

### 10.1. Đọc dependency tree

Ở project nhiều module, dùng phiên bản rõ ràng của Maven Dependency Plugin:

```bash
mvn -pl :app -am org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Lệnh có thể in cây cho các module được build cùng session; tìm đúng phần của `app`. Nếu cần kết quả chỉ cho một module sau khi `core` đã được giải quyết/cài đặt, có thể chọn POM module phù hợp. Đừng coi việc `-pl` chỉ chọn module là bằng chứng các artifact nội bộ khác tự động có trong local repository.

### 10.2. So effective POM và dependencies đã khai báo

```bash
mvn -pl :app help:effective-pom
```

Effective POM giúp kiểm tra parent đã mang `dependencyManagement` và plugin version xuống module hay chưa. Nhưng hãy nhớ: `dependencyManagement` và `dependencies` là hai khu vực khác nhau. Một artifact chỉ nằm trong quản lý version chưa chắc xuất hiện trong dependency graph hoặc classpath.

### 10.3. Kiểm tra classpath runtime và artifact

Trong ví dụ:

```bash
mvn -B clean verify
jar tf app/target/app-1.0.0.jar
```

JAR `app` thông thường dự kiến chứa `edu/demo/app/Main.class`; bản thân nó không tự chứa class `edu/demo/core/Greeter.class` hoặc Commons Lang. Những JAR đó được đặt riêng trong `app/target/lib` do Dependency Plugin.

Một lệnh kiểm tra dễ hiểu hơn việc chỉ nhìn log là chạy `java -cp` như ở phần 4.5. Nếu thiếu Commons Lang trên runtime classpath, lớp `Greeter` có thể ném lỗi khi cố tải/call `StringUtils`; vì vậy test và lệnh chạy runtime đều có giá trị, nhưng không thay thế nhau.

### 10.4. So dependency graph với báo cáo build

Khi kết quả khác nhau giữa các máy, đối chiếu:

- Tọa độ chính xác của dependency (groupId, artifactId, version, type, classifier).
- Scope, optional, exclusion và dependencyManagement từ effective POM.
- Maven/JDK/plugin version và repositories/mirrors.
- Module nào có mặt trong Reactor và module nào chỉ được lấy từ local/remote repository.
- Số test thật sự chạy trong Surefire reports, thay vì chỉ nhìn `BUILD SUCCESS`.
- Nội dung artifact và runtime classpath sau packaging.

Đặc biệt, `dependency:tree` không nhất thiết chỉ ra xung đột classpath của mọi launcher ngoài Maven (IDE, script deploy, Java application server). Phải kiểm tra **cách ứng dụng thực sự được chạy**.

## 11. Những lỗi thường gặp khi dùng thư viện ngoài và module nội bộ

| Triệu chứng | Nguồn sai cần xem | Cách kiểm tra và khắc phục |
| --- | --- | --- |
| `package org.apache.commons.lang3 does not exist` | Thiếu direct dependency ở module dùng `StringUtils`, scope sai hoặc phân giải lỗi | Xem `core/pom.xml`, `dependency:tree` và compile classpath |
| `package edu.demo.core does not exist` trong `app` | `app` không khai báo dependency `core` hoặc version sai | Khai báo dependency vào `edu.demo:core:...`, dùng Reactor với `-am` |
| `Could not find artifact edu.demo:core:jar:1.0.0` | Build riêng app không có core trong Reactor/cache/repository | Chạy từ root với `-pl :app -am` hoặc publish/install core đúng quy trình |
| `Could not find artifact commons-lang3` | GAV sai, repository/mirror/credential/network | Kiểm tra tọa độ, `settings.xml`, local repo và lỗi gốc trong log |
| `NoClassDefFoundError: ...StringUtils` lúc chạy | Commons Lang thiếu khỏi runtime classpath dù compile thành công | Kiểm tra scope, `target/lib`, lệnh Java, artifact packaging |
| `NoSuchMethodError` sau nâng thư viện | Version conflict hoặc runtime sử dụng API của version khác | Xem dependency mediation, graph và classpath cuối cùng |
| Chỉ một module chạy test, module còn lại không | Module selection và Surefire/test discovery khác | Xem `Reactor Build Order`, `-pl`, `-am` và Surefire reports từng module |
| Dependency đã có ở parent nhưng module không nhìn thấy | Khai báo ở `dependencyManagement`, chưa ở `dependencies` | Module sử dụng cần khai báo dependency thực |
| Test library xuất hiện ở JAR runtime | Scope khai báo sai hoặc plugin đóng gói quá rộng | Đặt `scope=test`, kiểm tra cách copy/package |
| `app` build được ở IDE nhưng CI compile fail | IDE tự thêm module/library, Maven graph thiếu dependency | Sửa POM, không chỉ cấu hình classpath của IDE |
| Reactor báo cyclic references | Hai hay nhiều module phụ thuộc vòng nhau | Chỉnh kiến trúc module và hướng phụ thuộc, không đổi thứ tự modules |
| Dependency bắc cầu biến mất sau cập nhật | Nhà phát hành thư viện đã đổi POM, scope, optional hoặc exclusions | Module nào dùng API trực tiếp thì khai báo dependency trực tiếp |
| `dependency:copy-dependencies` tạo thư mục không như ý | Output directory/scope/plugin execution sai hoặc goal chưa chạy | Xem `app/pom.xml`, phase `prepare-package`, phạm vi `includeScope` và logs |

Một cảnh báo quan trọng: nếu chỉ thấy lỗi “thiếu JAR” rồi copy thủ công một file vào project, bạn có thể che vấn đề về version/scope. Khi đó build phụ thuộc vào trạng thái máy và khó tái lập trên CI.

## 12. Checklist hoàn thành khi tích hợp dependency

1. **Module nào dùng API nào?** Mỗi module trực tiếp import một thư viện cần dependency trực tiếp tương ứng.
2. **Tọa độ đã đúng chưa?** Kiểm tra groupId, artifactId, version/type/classifier khi cần, và nguồn artifact.
3. **Version do ai quản lý?** Parent/BOM có quản lý không; có vô tình chọn version khác trong module?
4. **Scope có đúng?** `compile` cho thư viện compile/runtime; `test` cho JUnit; `provided`/`runtime` chỉ khi có lý do.
5. **Dependency nội bộ đã được khai báo thật chưa?** Không thay bằng `modules` hoặc `parent`.
6. **Reactor có module cần thiết không?** Với build chọn riêng app, dùng `-pl` và `-am` đúng mục đích.
7. **Có dựa vào dependency bắc cầu để import API trực tiếp không?** Nếu có, khai báo direct dependency để thiết kế vững chắc.
8. **Có exclusions/optional không?** Kiểm tra ảnh hưởng tới runtime và các tính năng tùy chọn.
9. **Artifact runtime được chạy bằng cách nào?** Phân biệt JAR thường, thư viện trong `lib`, fat JAR, WAR và image.
10. **Đã kiểm tra từ môi trường sạch?** Chạy `mvn -B clean verify`, đọc `dependency:tree`, test reports và chạy ứng dụng với classpath thực tế.

**Ghi nhớ:** Maven hiểu thư viện ngoài và module nội bộ qua **cùng cơ chế artifact dependency**. Parent chia sẻ cấu hình, aggregator tập hợp các module để Reactor build, còn dependency declaration nói rõ module nào sử dụng thư viện nào. Scope và dependency graph quyết định classpath; cách đóng gói quyết định những JAR nào thực sự đi cùng ứng dụng khi chạy.

### Tài liệu chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Maven Dependency Plugin 3.6.1 — dependency:tree](https://maven.apache.org/plugins-archives/maven-dependency-plugin-3.6.1/tree-mojo.html)
- [Maven Dependency Plugin 3.6.1 — dependency:copy-dependencies](https://maven.apache.org/plugins-archives/maven-dependency-plugin-3.6.1/copy-dependencies-mojo.html)
- [Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
