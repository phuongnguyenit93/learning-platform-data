# Tránh khai báo lặp và kiểm soát thay đổi phiên bản tập trung với Maven BOM

## 1. Vấn đề thực tế: một thư viện, nhiều phiên bản trong nhiều POM

Khi ứng dụng Maven phát triển từ một project đơn thành hệ thống nhiều module, một phiên bản thư viện có thể xuất hiện ở `core/pom.xml`, `app/pom.xml`, một adapter, một service và nhiều project cùng nhóm. Chỉ cần một module quên nâng version, dự án có thể gặp các hiện tượng:

- Module A dùng `commons-lang3:3.14.0`, module B dùng `commons-lang3:3.17.0` trong khi hai module phải giao tiếp hoặc chạy chung.
- Một thư viện của framework được nâng, nhưng các module cùng hệ sinh thái (API, implementation, test libraries) còn ở bản khác.
- Maven build vẫn thành công vì dependency mediation chọn một phiên bản hợp lệ theo quy tắc của Maven, nhưng runtime phát sinh `NoSuchMethodError`, `ClassNotFoundException` hoặc thay đổi hành vi.
- Muốn áp dụng bản vá bảo mật, nhóm phải tìm và sửa một loạt số version trong nhiều POM; khó chứng minh không bỏ sót.
- Đồng đội sửa version trực tiếp trong POM con để giải quyết lỗi tạm, vô tình vượt qua chính sách tập trung mà không có tài liệu ngoại lệ.

Cách xử lý là tách rõ **module cần thư viện nào** khỏi **hệ thống quyết định phiên bản nào**. Maven cung cấp ba công cụ liên quan:

1. **`<dependencyManagement>`**: khai báo tập dependency được quản lý về version và một số thuộc tính khác, không tự thêm tất cả chúng vào mọi module.
2. **Parent POM**: cung cấp quản lý dependency và các quy tắc build chung cho những project thực sự có quan hệ `<parent>`.
3. **BOM (Bill of Materials)**: một POM `packaging=pom` chuyên tập hợp các phiên bản dependency, được project khác nhập vào `dependencyManagement` bằng `type=pom` và `scope=import`. BOM đặc biệt thích hợp khi một họ thư viện cần nâng đồng bộ, hoặc nhiều project không cùng một parent.

Mục tiêu cuối bài: **sửa một phiên bản tại đúng nguồn quản lý**, kiểm tra được từng module đang nhận phiên bản đó, không lặp lại số version trong POM con, vẫn kiểm soát ngoại lệ có chủ đích và biết ranh giới giữa quản lý version với dependency resolution thực tế.

Bài dùng **Maven 3.9.x**, **JDK 17+**, **Commons Lang 3**, **JUnit Jupiter 5** và ví dụ Maven reactor chạy được. Các phiên bản trong bài là ví dụ cố định để dễ kiểm chứng; với hệ thống production, hãy kiểm tra compatibility, bản vá bảo mật và phiên bản được tổ chức phê duyệt trước khi áp dụng.

## 2. Phân biệt dependency thực tế và chính sách version

Một dependency trực tiếp trong một module:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
~~~

Khai báo này đồng thời nói hai điều: “module cần Commons Lang” và “module yêu cầu version 3.14.0”.

Khi có nhiều module, ta thường muốn để mỗi module nói **điều thứ nhất** còn parent/BOM phụ trách **điều thứ hai**.

~~~xml
<!-- Trong parent: chỉ quản lý -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

~~~xml
<!-- Trong child: thực sự sử dụng -->
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
~~~

Khi parent–child được thiết lập đúng và không có override, Maven dùng version được quản lý. Child không phải viết lại số `3.14.0`.

**Quy tắc không được bỏ qua:** dependency trong `dependencyManagement` **không tự đi vào classpath**. Nếu child không khai Commons Lang và dependency đó cũng không đến qua các đường transitive phù hợp, chỉ khai ở management không tạo một `commons-lang3.jar` trong project.

### 2.1. Bảng phân biệt nhanh

| Cấu trúc | Định nghĩa | Có tự thêm dependency khi chỉ khai cấu trúc đó không? |
| --- | --- | --- |
| `dependencies` | Dependency mà project cần | Có, theo scope và quy tắc resolution |
| `dependencyManagement` | Version/scope/cấu hình áp dụng cho dependency được dùng | **Không** |
| `properties` | Giá trị tái sử dụng như `commons.lang3.version` | **Không** |
| `build/pluginManagement` | Phiên bản/cấu hình của Maven **build plugins** | Không thêm project library |
| BOM `type=pom, scope=import` | Nhập tập dependencyManagement từ POM khác | **Không** |
| `modules` | Aggregate các project vào reactor | Không tự tạo parent inheritance hoặc dependency |

Parent là cơ chế **kế thừa mô hình POM**, BOM import là cơ chế **nhập tập quản lý dependency**. Hai cơ chế có thể dùng cùng nhau, nhưng không đồng nghĩa.

## 3. Tại sao copy một số version vào nhiều POM không phải quản lý chung?

Một thiết kế dễ bị trôi phiên bản:

~~~text
system/
├── pom.xml
├── core/pom.xml        commons-lang3 = 3.14.0
├── app/pom.xml         commons-lang3 = 3.14.0
├── batch/pom.xml       commons-lang3 = 3.14.0
└── report/pom.xml      commons-lang3 = 3.14.0
~~~

Khi muốn lên `3.17.0`, người sửa phải tìm mọi vị trí, phân biệt chúng với số version của plugin hoặc project, và tránh bỏ sót. Một số module có thể còn nhận thư viện qua dependency bắc cầu nên không có con số hiện ngay trong POM của mình.

Thiết kế tập trung:

~~~text
system/
├── pom.xml             dependencyManagement:
│                         commons-lang3 = 3.14.0
├── core/pom.xml        commons-lang3 (không version)
├── app/pom.xml         commons-lang3 (không version)
├── batch/pom.xml       commons-lang3 (không version)
└── report/pom.xml      commons-lang3 (không version)
~~~

Để nâng cấp, đổi một vị trí tại parent và kiểm tra tất cả module bị ảnh hưởng.

**Không nhầm “bớt lặp số version” với “không khai dependency ở module”.** Một module trực tiếp import API Commons Lang nên khai Commons Lang **trực tiếp** dù parent đã quản lý version, để thể hiện thiết kế và tránh phụ thuộc tình cờ vào dependency bắc cầu.

### 3.1. Khai báo trùng dependency trong cùng một POM là vấn đề khác

Không viết hai mục cùng `groupId:artifactId:type:classifier` trong cùng một `<dependencies>`, một mục version cũ và một mục version mới, rồi mong Maven “chọn mục sau”:

~~~xml
<!-- Phản ví dụ: không dùng trong POM chạy -->
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.17.0</version>
</dependency>
~~~

Maven có thể cảnh báo về dependency declaration trùng tọa độ và model không ổn định. **Sửa bản ghi có sẵn hoặc chuyển version đến nguồn quản lý**, đừng nhân đôi bản ghi để tạo “override”.

### 3.2. Một property chung có giúp không?

~~~xml
<properties>
    <commons.lang3.version>3.14.0</commons.lang3.version>
</properties>
~~~

Nếu mọi nơi đều sử dụng `<version>${commons.lang3.version}</version>`, bạn đã giảm sự lặp **literal version** nhưng vẫn có thể lặp phần XML mô tả version ở POM con. `dependencyManagement` cho phép child bỏ hoàn toàn phần `<version>`. Trong parent, kết hợp property và management là một cách tổ chức hợp lý:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>${commons.lang3.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi muốn nâng đồng bộ, sửa property ở parent. Nên đặt tên property rõ ràng; tránh một property tên chung như `version` được dùng cho nhiều thư viện không liên quan.

## 4. BOM là gì và khác parent POM như thế nào?

BOM là **Bill of Materials**: một POM chuyên xác định các dependency version được cho là tương thích hoặc được quản lý cùng nhau. Một dự án nhập BOM có thể khai dependencies mà **không viết version**, miễn BOM có managed entry phù hợp.

Cú pháp quan trọng nhất:

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
~~~

Đây là **import BOM**, không phải project dependency runtime. `scope=import` chỉ áp dụng cho một dependency loại `pom` **bên trong `dependencyManagement`**. Nếu bạn đưa `junit-bom` vào `dependencies` thông thường, nó **không** thực hiện cùng hành vi quản lý version của các thư viện JUnit.

Sau khi import đúng BOM, project khai JUnit:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Maven nhận version `junit-jupiter` từ BOM (nếu không có override version cụ thể). Project phải khai `junit-jupiter` ở `dependencies` thì test mới có JUnit. BOM **không tự thêm toàn bộ JUnit** vào classpath.

### 4.1. So sánh parent và BOM

| Parent POM | BOM import |
| --- | --- |
| POM con dùng `<parent>`; mỗi project có tối đa một parent trực tiếp | Project có thể import nhiều BOM vào `dependencyManagement` |
| Có thể kế thừa properties, dependencies, dependencyManagement, pluginManagement và nhiều phần khác của model | **Nhập các managed dependency entries** của BOM, không nhập mọi thứ như parent |
| Phù hợp thống nhất tiêu chuẩn build giữa module cùng nhóm | Phù hợp đồng bộ version của thư viện/framework giữa nhiều project |
| Có thể là aggregator nếu khai `<modules>` | BOM import không tự tạo reactor hoặc project cha |
| Điều khiển plugin version qua `pluginManagement` | BOM không thay thế `pluginManagement` |
| Child phải khai parent thật sự để nhận model | BOM phải được import trong management ở đúng POM hoặc đến từ parent đã cấu hình |

Một hệ thống thực tế có thể dùng **parent công ty** cho Maven/JDK/plugins và **BOM của framework** cho các dependency có tương thích phiên bản. Đó không phải hai cách loại trừ nhau.

### 4.2. BOM không phải “magic version lock” cho mọi thứ

BOM quản lý những artifact **được liệt kê trong BOM**, không tự ghim mọi dependency ngoài hệ. Một thư viện không có trong BOM có thể cần entry quản lý riêng. Ngoài ra, BOM không khóa chính xác mọi input như JDK, Maven, repository metadata hoặc plugin dependencies.

Khi cần build có thể truy vết, vẫn phải ghi commit, version BOM, resolved dependency tree và artifact output. Việc nhập BOM không miễn trừ kiểm thử tích hợp hay kiểm tra an toàn của các phiên bản cụ thể.

## 5. Ba chiến lược tập trung và cách chọn

| Tình huống | Giải pháp | Mức độ tác động |
| --- | --- | --- |
| Project đơn, vài dependency | Khai `<version>` trực tiếp | Cục bộ, dễ đọc |
| Nhiều dependency dùng lại một số version trong cùng project | Dùng `<properties>` | Giảm lặp literal |
| Nhiều module có quan hệ parent | Parent `dependencyManagement` + child `dependencies` không version | Thống nhất các module kế thừa |
| Một họ thư viện có nhiều artifact cần đồng bộ | Import BOM của họ thư viện | Quản lý một tập version tương thích |
| Nhiều project độc lập, không chung parent | Import một BOM nội bộ đã phát hành | Chính sách version dùng lại giữa project |
| Build plugin phải có version thống nhất | Parent `pluginManagement` | Quản lý công cụ build, **khác** thư viện runtime |
| Một module có nhu cầu ngoại lệ | Override có phê duyệt tại child | Rõ lý do, phạm vi và thời hạn |

Trong bài, ta kết hợp **parent dependencyManagement cho Commons Lang** và **JUnit BOM cho các thư viện test**. Điều này thể hiện cả hai cách quản lý tập trung trong một project chạy được.

## 6. Thực hành hoàn chỉnh: reactor parent/core/app không lặp version

### 6.1. Cấu trúc dự án

Tạo dự án `central-bom-demo`:

~~~text
central-bom-demo/
├── pom.xml
├── core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/vn/example/core/Greeting.java
│       └── test/java/vn/example/core/GreetingTest.java
└── app/
    ├── pom.xml
    └── src/
        ├── main/java/vn/example/app/App.java
        └── test/java/vn/example/app/AppTest.java
~~~

Quan hệ:

~~~text
catalog-parent (packaging=pom; aggregator + parent)
    |
    +--> core (packaging=jar)
    |      └── commons-lang3: version từ parent management
    |      └── junit-jupiter: version từ JUnit BOM
    |
    +--> app (packaging=jar)
           └── core:1.0.0 (dependency nội bộ)
           └── commons-lang3: version từ parent management
           └── junit-jupiter: version từ JUnit BOM
~~~

`app` phụ thuộc `core` để dùng `Greeting`. `app` cũng **trực tiếp** dùng `StringUtils`, vì thế nó khai Commons Lang trực tiếp thay vì dựa vào dependency bắc cầu từ `core`. Mỗi module khai thư viện nó thực sự sử dụng nhưng **không lặp version của Commons Lang/JUnit**.

Yêu cầu môi trường: **Maven 3.9.x**, **JDK 17+**. Khi chạy lần đầu, Maven cần tải dependencies/plugins từ repository được cấu hình; trong mạng công ty, dùng `settings.xml` phù hợp policy.

### 6.2. POM cha đầy đủ: `central-bom-demo/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>catalog-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <commons.lang3.version>3.14.0</commons.lang3.version>
        <junit.bom.version>5.11.4</junit.bom.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>${commons.lang3.version}</version>
            </dependency>

            <dependency>
                <groupId>org.junit</groupId>
                <artifactId>junit-bom</artifactId>
                <version>${junit.bom.version}</version>
                <type>pom</type>
                <scope>import</scope>
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
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.4</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-dependency-plugin</artifactId>
                    <version>3.8.1</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

Đọc parent theo nhóm:

- `<modules>` giúp Maven reactor nhìn thấy `core` và `app`.
- `<properties>` ghim Java release, encoding và **hai điểm thay version tập trung**: `commons.lang3.version`, `junit.bom.version`.
- `<dependencyManagement>` quản lý Commons Lang trực tiếp và import JUnit BOM. Không có nghĩa parent hoặc mọi child có cả hai thư viện trên classpath.
- `<pluginManagement>` ghim các plugin build. Nó **không quản lý version Commons Lang/JUnit** và không tự gắn một goal tùy ý vào lifecycle nếu plugin không được sử dụng.
- Parent `packaging=pom` không biên dịch Java hay tạo JAR ứng dụng như một module `jar`.

**Đặc điểm cần nhớ:** `<version>${commons.lang3.version}</version>` được nội suy từ property **trong cùng parent**, còn `junit-bom` xác định nhiều phiên bản JUnit theo chính sách của BOM. Nếu muốn nâng toàn bộ bộ thư viện JUnit sang BOM khác, thay **version BOM đã review**, không thay riêng `junit-jupiter` trong từng child.

### 6.3. POM của core: `central-bom-demo/core/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example</groupId>
        <artifactId>catalog-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Hai dependency **không có `<version>`**. Maven giải quyết version theo entry quản lý trong parent hoặc BOM được parent nhập. `core` khai `<parent>` đúng tọa độ `vn.example:catalog-parent:1.0.0`; nếu bỏ `<parent>`, phần management không tự xuất hiện chỉ vì `core` nằm dưới `<modules>`.

### 6.4. Java core: `Greeting.java`

File `core/src/main/java/vn/example/core/Greeting.java`:

~~~java
package vn.example.core;

import org.apache.commons.lang3.StringUtils;

public final class Greeting {
    private Greeting() {
    }

    public static String hello(String name) {
        if (StringUtils.isBlank(name)) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        return "Hello, " + StringUtils.capitalize(name.trim()) + "!";
    }
}
~~~

`Greeting` trực tiếp import `StringUtils` nên `core` khai Commons Lang ở dependencies. Nếu `name` rỗng hoặc chỉ có whitespace, code ném `IllegalArgumentException`. Cả hai hàm `StringUtils.isBlank` và `StringUtils.capitalize` có trong Commons Lang 3.14.0/3.17.0.

### 6.5. JUnit test của core

File `core/src/test/java/vn/example/core/GreetingTest.java`:

~~~java
package vn.example.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void createsGreeting() {
        assertEquals("Hello, Maven!", Greeting.hello("maven"));
    }

    @Test
    void rejectsBlank() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeting.hello("  "));
    }
}
~~~

Hai test chỉ cần JUnit trong **test classpath**. JUnit BOM quản lý version, nhưng `core` vẫn phải khai `junit-jupiter` với `scope=test`.

### 6.6. POM của app: `central-bom-demo/app/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example</groupId>
        <artifactId>catalog-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
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
                <configuration>
                    <includeScope>runtime</includeScope>
                    <outputDirectory>${project.build.directory}/runtime-libs</outputDirectory>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tại sao `core` có `<version>${project.version}</version>` nhưng Commons Lang/JUnit không có?

- `core` là artifact nội bộ của reactor. Mẫu này dùng version của project hiện hành (`app`, kế thừa `1.0.0`) để khớp version của `core`. Nếu module dùng version độc lập, cần quản lý version nội bộ theo chính sách riêng.
- Commons Lang đã được quản lý bởi parent; JUnit đã được quản lý bởi BOM.
- Khi app trực tiếp dùng `StringUtils`, nó vẫn nên khai Commons Lang trực tiếp; bỏ version là tránh lặp **số version**, không che khuất dependency thật.
- Maven Dependency Plugin trong child có cấu hình copy runtime libs, còn version plugin đến từ `pluginManagement` của parent. Chỉ khai plugin không tự làm goal `copy-dependencies` chạy trong lifecycle; ta sẽ gọi nó sau build.

`<includeScope>runtime</includeScope>` của Dependency Plugin lấy những dependency phù hợp **runtime classpath**, thường gồm `compile` và `runtime`, **không lấy JUnit ở scope test**. Trong mẫu, thư mục runtime-libs của app sẽ có `core-1.0.0.jar` và `commons-lang3-3.14.0.jar` cùng các dependency bắc cầu phù hợp nếu có.

### 6.7. Mã Java của app

File `app/src/main/java/vn/example/app/App.java`:

~~~java
package vn.example.app;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;
import vn.example.core.Greeting;

public final class App {
    private App() {
    }

    public static String message() {
        return Greeting.hello("maven")
                + " " + StringUtils.upperCase("team", Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

`App` dùng `Greeting` từ `core` và `StringUtils` từ Commons Lang. `Locale.ROOT` giúp cách viết hoa của ví dụ không phụ thuộc locale mặc định của máy.

Stdout chính xác khi ứng dụng được chạy với đúng classpath:

~~~text
Hello, Maven! TEAM
~~~

### 6.8. Unit test của app

File `app/src/test/java/vn/example/app/AppTest.java`:

~~~java
package vn.example.app;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void buildsMessage() {
        assertEquals("Hello, Maven! TEAM", App.message());
    }
}
~~~

Tổng cộng reactor có **ba test**: hai ở `core`, một ở `app`. Chúng sẽ được chạy nếu Surefire/JUnit được thiết lập như POM mẫu và không bật skip test.

## 7. Build toàn reactor và quan sát kết quả

### 7.1. Biên dịch/kiểm thử/đưa artifact vào local Maven repository

Từ thư mục **central-bom-demo** (chứa POM cha), chạy:

~~~bash
java -version
mvn -version
mvn clean install
~~~

Maven build parent, `core` rồi `app` theo reactor dependency graph. `install` ở đây có nghĩa là **cài Maven artifacts vào local repository `~/.m2/repository`**, không phải cài ứng dụng vào hệ điều hành. Trong bài thực hành, sử dụng `install` giúp goal `dependency:copy-dependencies` chạy riêng cho app sau đó vẫn tìm được artifact `core:1.0.0` ở local repository.

Mong đợi trong phần quan trọng của output:

~~~text
core: Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
app:  Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **bản tóm tắt kết quả**, không phải nguyên văn từng dòng log của Maven/Surefire (format dòng có thể khác tùy phiên bản). Sau khi build:

~~~text
central-bom-demo/
├── core/target/
│   ├── classes/vn/example/core/Greeting.class
│   ├── test-classes/vn/example/core/GreetingTest.class
│   ├── surefire-reports/
│   └── core-1.0.0.jar
└── app/target/
    ├── classes/vn/example/app/App.class
    ├── test-classes/vn/example/app/AppTest.class
    ├── surefire-reports/
    └── app-1.0.0.jar
~~~

Có thể có thêm metadata hoặc file trung gian; cây chỉ liệt kê các đầu ra cần kiểm tra.

### 7.2. Kiểm tra phiên bản resolved

Dùng hai lệnh tại reactor root:

~~~bash
mvn -pl :core dependency:tree
mvn -pl :app dependency:tree
~~~

Hoặc lọc các thư viện chính:

~~~bash
mvn -pl :core dependency:tree -Dincludes=org.apache.commons:commons-lang3
mvn -pl :app dependency:tree -Dincludes=org.apache.commons:commons-lang3
mvn -pl :app dependency:tree -Dincludes=org.junit.jupiter:junit-jupiter
~~~

Các node mong đợi:

~~~text
org.apache.commons:commons-lang3:jar:3.14.0:compile
org.junit.jupiter:junit-jupiter:jar:5.11.4:test
~~~

Kết quả thứ nhất phải xuất hiện ở cả `core` và `app`, kết quả thứ hai xuất hiện khi lọc dependency test. Tên, vị trí và các dòng dependency bắc cầu trong cây có thể khác nhau; phần quyết định là **tọa độ, phiên bản và scope** thực tế.

### 7.3. Copy các JAR cần cho ứng dụng chạy

Sau `mvn clean install`, chạy:

~~~bash
mvn -pl :app dependency:copy-dependencies
~~~

Goal này dùng `maven-dependency-plugin` đã khai trong `app/pom.xml` và version quản lý từ parent. Thư mục cần quan sát:

~~~text
app/target/runtime-libs/
├── core-1.0.0.jar
└── commons-lang3-3.14.0.jar
~~~

JUnit không cần xuất hiện trong runtime-libs vì nó được khai `scope=test`. Plugin có thể copy thêm các dependency runtime khác nếu thư viện phiên bản được chọn kéo chúng vào; tên trên là các JAR cốt lõi cần thấy trong mẫu này.

### 7.4. Chạy chương trình trên Linux/macOS

Từ reactor root:

~~~bash
java -cp "app/target/app-1.0.0.jar:app/target/runtime-libs/*" vn.example.app.App
~~~

### 7.5. Chạy chương trình trên Windows PowerShell/CMD

~~~bat
java -cp "app\target\app-1.0.0.jar;app\target\runtime-libs\*" vn.example.app.App
~~~

Cả hai cách phải in đúng:

~~~text
Hello, Maven! TEAM
~~~

**Giải thích classpath:** `app-1.0.0.jar` chứa mã App; `runtime-libs/core-1.0.0.jar` cung cấp `Greeting`; `runtime-libs/commons-lang3-3.14.0.jar` cung cấp `StringUtils`. Maven JAR Plugin thông thường **không tự nhúng các dependencies** vào JAR chính. Không dùng `java -jar` khi ví dụ chưa khai manifest `Main-Class` và chưa có launcher đóng gói dependency phù hợp.

## 8. Thực hành nâng phiên bản tập trung: chỉ sửa parent

Giữ nguyên `core/pom.xml`, `app/pom.xml` và mã nguồn. Trong `central-bom-demo/pom.xml`, sửa duy nhất:

~~~xml
<commons.lang3.version>3.14.0</commons.lang3.version>
~~~

thành:

~~~xml
<commons.lang3.version>3.17.0</commons.lang3.version>
~~~

Sau đó:

~~~bash
mvn clean install
mvn -pl :core dependency:tree -Dincludes=org.apache.commons:commons-lang3
mvn -pl :app dependency:tree -Dincludes=org.apache.commons:commons-lang3
mvn -pl :app dependency:copy-dependencies
~~~

Kỳ vọng **cả hai module** đã nhận version mới:

~~~text
org.apache.commons:commons-lang3:jar:3.17.0:compile
~~~

Thư mục `app/target/runtime-libs` sau build sạch sẽ có:

~~~text
commons-lang3-3.17.0.jar
core-1.0.0.jar
~~~

Vẫn chạy được cùng lệnh Java và nhận stdout:

~~~text
Hello, Maven! TEAM
~~~

Đây là điểm mạnh của quản lý tập trung: **một thay đổi ở nguồn quản lý → nhiều project dùng cùng version**, không cần sửa hàng loạt POM con.

Tuy nhiên, *cùng source và test PASS* không bảo đảm mọi hệ thống lớn tương thích với version mới. Thư viện có thể thay đổi API, binary compatibility, transitive dependency hoặc behavior. Vì phạm vi tác động rộng, **càng quản lý tập trung càng cần review và regression test tốt**.

### 8.1. Tránh classpath chứa cả bản cũ và mới

Nếu sau khi nâng version bạn chỉ chạy `dependency:copy-dependencies` mà **không clean**, `runtime-libs` có thể còn `commons-lang3-3.14.0.jar` và được copy thêm `commons-lang3-3.17.0.jar`. Lệnh `java -cp ".../runtime-libs/*"` có thể nạp hai bản cùng thư viện, dẫn đến hành vi khó dự đoán.

Trong bài dùng `mvn clean install` trước bước copy để dọn thư mục `target`, rồi **kiểm tra danh sách JAR thực sự**. Với production package, CI phải đóng gói từ workspace/output sạch theo quy trình đã định nghĩa, không tái sử dụng thư mục lib cũ.

### 8.2. Kiểm soát thay đổi version BOM

Thay vì nâng Commons Lang, nếu nhóm muốn nâng cả họ JUnit lên một version BOM mới **đã xác nhận tồn tại và tương thích**, hãy sửa:

~~~xml
<junit.bom.version>5.11.4</junit.bom.version>
~~~

sang version BOM được phê duyệt, build lại reactor, xem `dependency:tree` cho JUnit components và chạy test. **Không tự đoán** rằng mỗi nhóm artifact JUnit chỉ cần đồng nhất số version theo trực giác; hãy để BOM đã phát hành quản lý tập hợp đúng.

Trong môi trường doanh nghiệp, chính phiên bản BOM là một **đầu vào version-controlled quan trọng**; ghi nó trong commit/build metadata và tránh để dev/CI vô tình dùng BOM khác vì profile hoặc property override.

## 9. BOM nội bộ cho nhiều project độc lập

Parent POM dùng tốt khi tất cả module thuộc cùng một cây kế thừa. Nhưng giả sử nhóm có các repository độc lập:

~~~text
company/
├── billing-service/     parent riêng
├── inventory-service/   parent riêng
└── audit-service/       parent riêng
~~~

Mỗi project chỉ có **một parent trực tiếp** và có thể thuộc những framework khác nhau. Nếu muốn chia sẻ chính sách version mà **không ép các project phải dùng cùng parent**, nhóm có thể phát hành một **BOM nội bộ** như một artifact POM.

### 9.1. Cấu trúc BOM tối giản

Ví dụ một POM **chỉ làm BOM**, không tạo thư viện Java:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.platform</groupId>
    <artifactId>company-dependencies-bom</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>3.14.0</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.4</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

Ví dụ này đủ để minh họa **một BOM POM với hai managed entries**. Nó **không** thay thế tính toàn diện của `org.junit:junit-bom` về cả họ JUnit: nếu một tổ chức thực tế dùng JUnit Platform, API, Engine và nhiều thành phần khác, nên xem xét import chính thức JUnit BOM hoặc quản lý tập entry đầy đủ, tránh BOM nội bộ chỉ ghi một mảnh nhưng được hiểu nhầm là quản lý toàn bộ hệ.

Sau khi BOM được **phát hành vào Maven repository được các project sử dụng truy cập**, project độc lập có thể import:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example.platform</groupId>
            <artifactId>company-dependencies-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Và khai dependency ở chính project:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
~~~

Không có `<version>` trong dependency của project, vì BOM cung cấp version. Đây là cách **nhiều project độc lập dùng chung tập version** mà không cần cùng parent.

### 9.2. Không ghi đè BOM đang phát hành

BOM có tọa độ `vn.example.platform:company-dependencies-bom:pom:1.0.0` là một artifact phát hành. Nếu tổ chức chốt một version BOM, cần coi nó là **bất biến**: muốn nâng Commons Lang, phát hành BOM version mới (ví dụ `1.1.0` theo chính sách version nội bộ), rồi cập nhật version BOM mà các project tiêu thụ.

**Không** đăng lại nội dung POM đã đổi dưới cùng BOM GAV `1.0.0`: cache Maven/repository có thể giữ dữ liệu khác nhau giữa máy, làm build không thể truy vết. Bản phát hành BOM phải có version và provenance rõ ràng.

### 9.3. BOM có thể được import cùng parent hiện có

Một project đã có parent riêng vẫn có thể import BOM trong `dependencyManagement` của mình; không cần bỏ `<parent>`. Tuy nhiên **xung đột với các managed entries từ parent/BOM khác** phải được giải quyết có chủ đích, và effective POM là bằng chứng thực tế.

Không nên dùng BOM để phân phối pluginManagement, resource filtering hoặc profile của công ty; BOM import chủ yếu phục vụ `dependencyManagement`, không có ý nghĩa thay thế mọi phần cấu hình build của parent.

## 10. Quy tắc ưu tiên: nhiều nơi cùng quản lý một artifact

Maven không đơn giản “lấy version số lớn nhất”. Nó kết hợp POM inheritance, dependencyManagement và dependency mediation theo những quy tắc cụ thể.

### 10.1. Dependency trực tiếp có version rõ ràng

Trong parent/BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Nếu `app/pom.xml` ghi một dependency trực tiếp với `<version>3.17.0</version>`, version trực tiếp đó thường được dùng cho dependency của app, thay vì kế thừa version `3.14.0` ở management của parent. Đây là một **ngoại lệ rõ ràng** có thể hợp lệ, nhưng phải được review và ghi nhận.

Nếu muốn chính sách chung chặt chẽ, chỉ dựa vào parent `dependencyManagement` là chưa đủ để cấm mọi override; CI có thể dùng kiểm tra dependency convergence, quy tắc phiên bản hoặc kiểm tra effective model phù hợp.

### 10.2. Child có dependencyManagement riêng

Với cùng một managed coordinate, một entry quản lý **trong POM child** thường ưu tiên hơn entry tương ứng được **kế thừa từ parent**. Ví dụ parent quản lý Commons Lang `3.14.0`; child có `dependencyManagement` quản lý nó là `3.17.0`; dependency trực tiếp của child không viết version. Khi đó resolved version ở child có thể là `3.17.0`.

Điều này giúp một module có ngoại lệ, nhưng nếu nhiều child đều override thì chính sách tập trung bị phân mảnh. Thay vì cố “khóa cứng” bằng nhiều XML trái chiều, hãy dùng **quy tắc kiểm tra tập trung** và ghi rõ ngoại lệ.

### 10.3. Explicit managed entry so với imported BOM

Khi POM nhập BOM và đồng thời **khai một managed entry explicit** cho cùng artifact ngay trong `dependencyManagement`, entry explicit tại POM đó có thể được ưu tiên hơn entry nhập từ BOM. Đừng cố sửa trực tiếp file BOM ở Maven cache; hãy thay version BOM hoặc khai override có chủ đích tại nơi tiêu thụ.

### 10.4. Hai BOM cùng quản lý một tọa độ

Ví dụ:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>example</groupId>
            <artifactId>first-bom</artifactId>
            <version>1.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>example</groupId>
            <artifactId>second-bom</artifactId>
            <version>1.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây chỉ là **ví dụ cú pháp**; hai tọa độ `example:*` không phải BOM được yêu cầu tải thật. Nếu cả hai BOM đều quản lý một artifact chung mà không có entry explicit ưu tiên hơn, trong Maven 3 **BOM được khai trước thường quyết định managed version cho entry trùng**. Không nên dựa vào quy tắc thứ tự này như một chiến lược nâng version bí mật: thay BOM hoặc đặt entry explicit theo chính sách.

### 10.5. Nearest definition khi không có management liên quan

Giả sử dependency graph:

~~~text
app
├── library-a
│   └── util:1.0
└── library-b
    └── helper
        └── util:2.0
~~~

Maven thường chọn version có **đường dẫn ngắn hơn** từ project, theo nguyên tắc nearest-definition. Nếu các đường cùng độ sâu, declaration gặp trước có thể thắng. Đây là **dependency mediation**, không phải chiến lược quản lý tập trung.

Nếu một thư viện quan trọng bị kéo vào theo nhiều nhánh, hãy cân nhắc dùng dependencyManagement để chọn version phù hợp sau khi kiểm tra compatibility. **Không** đảo thứ tự XML cho đến khi ra version tình cờ mong muốn rồi coi đó là giải pháp bảo trì lâu dài.

### 10.6. Kiểm chứng thay vì chỉ nhớ bảng ưu tiên

| Trường hợp | Nguồn quyết định thường thấy |
| --- | --- |
| Direct dependency có version rõ | Version trực tiếp của dependency |
| Direct dependency bỏ version, có management hợp lệ | Managed entry từ model hiệu lực |
| Child managed entry trùng parent managed entry | Child entry |
| POM nhập BOM và có entry explicit phù hợp | Entry explicit phù hợp |
| Hai BOM nhập trùng entry, không có override khác | BOM import trước thường thắng |
| Transitive version xung đột, không có management phù hợp | Nearest definition, tie theo declaration order |
| Không có dependency nào yêu cầu artifact | Chỉ quản lý version không tự tạo dependency |

Bảng trình bày trường hợp tiêu biểu của Maven 3.9. Với `type`, `classifier`, scopes, version ranges, exclusions, parent chains hoặc profile phức tạp, **resolved dependency tree mới cho biết kết quả của project cụ thể**. Không dùng bảng như một lý do bỏ kiểm tra.

## 11. Ranh giới quan trọng: BOM không quyết định Maven plugin version

Hai khối XML thường cùng xuất hiện trong parent:

~~~xml
<dependencyManagement>
    <!-- version của project dependencies -->
</dependencyManagement>

<build>
    <pluginManagement>
        <!-- version của Maven build plugins -->
    </pluginManagement>
</build>
~~~

`dependencyManagement` trong project **không tự điều khiển transitive dependencies của Maven plugin**. Nếu Compiler Plugin hoặc Surefire Plugin cần các thư viện riêng của nó, đừng giả định import một BOM ở project sẽ ép toàn bộ dependency graph của plugin dùng version từ BOM.

Để quản lý **phiên bản plugin**, dùng `pluginManagement` hoặc `build/plugins` với version rõ. Nếu phải điều chỉnh plugin dependencies, cần xem tài liệu và cơ chế riêng của plugin, rồi kiểm chứng output build.

Đây là lý do parent mẫu quản lý Compiler, Surefire, JAR và Dependency Plugin ở `pluginManagement`, còn Commons Lang/JUnit ở `dependencyManagement`/BOM.

## 12. Version tập trung vẫn cần quản lý scope và kiểu artifact

Managed entry được nhận diện theo tọa độ phù hợp, thường có `groupId`, `artifactId`, `type`, `classifier`. Nếu project dùng artifact khác kiểu hoặc classifier so với entry quản lý, đừng đoán version chắc chắn được áp dụng; kiểm tra effective POM.

Scope cũng cần đặt ở đúng nơi:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

BOM quản lý version nhưng **scope test ở child** thể hiện rằng JUnit chỉ dùng cho test. Không nên đặt JUnit làm compile dependency của tất cả module chỉ để Maven “tự nhận” version từ BOM.

Trong parent, có thể quản lý scope ở `dependencyManagement`, nhưng các module có nhu cầu khác nhau nên quy tắc phải được thiết kế rõ. Đặc biệt với runtime/provided/test, việc phân bố classpath ảnh hưởng compile, test và deployment. Version tập trung **không sửa được một scope không phù hợp**.

### 12.1. BOM property có phải override được từ consumer?

Một số BOM nội bộ dùng property để quản lý version **trong chính POM của BOM**. Khi một project khác **import** BOM, các entry được xử lý theo model của BOM; **không nên mặc định** rằng chỉ khai một property trùng tên trong POM project tiêu thụ sẽ đổi version của những entry đã được import.

Muốn override phiên bản một artifact trong BOM ở project tiêu thụ, cách rõ ràng hơn là một **managed entry explicit** trong `dependencyManagement` của project, hoặc nâng BOM lên bản mới đã được phát hành. Sau đó xem effective POM và dependency tree.

Nếu project có quan hệ **parent** với BOM-like POM (inheritance) thì cách property override có thể khác; không đồng nhất cơ chế inheritance với import.

## 13. Debug: effective POM, dependency tree và artifact runtime

Khi một module vẫn nhận version cũ sau khi parent đã được sửa, hãy kiểm tra theo thứ tự.

### 13.1. Effective POM của đúng module

~~~bash
mvn -pl :core help:effective-pom
mvn -pl :app help:effective-pom
mvn -pl :app help:effective-pom -Dverbose
~~~

Mục đích:

- Tìm managed entry Commons Lang và version thực sự trong `dependencyManagement` của module.
- Xem JUnit BOM được import và version JUnit đã xuất hiện trong effective model.
- Tìm một khai báo direct version/child management hoặc profile đang override.
- Xác định plugin version ở `pluginManagement`, tránh nhầm plugin với application dependency.

`-Dverbose` của Help Plugin có thể cung cấp thông tin vị trí nguồn cấu hình, hữu ích khi parent chain dài. Nhưng effective POM là **mô hình cấu hình**, chưa chứng minh hoàn toàn classpath mà ứng dụng đang chạy.

### 13.2. Dependency tree đã resolve

~~~bash
mvn -pl :core dependency:tree
mvn -pl :app dependency:tree
mvn -pl :app dependency:tree -Dincludes=org.apache.commons:commons-lang3
mvn -pl :app dependency:tree -Dincludes=org.junit.jupiter:junit-jupiter
~~~

`dependency:tree` cho thấy version và scope thực tế theo graph. Nếu khó hiểu vì hai nhánh cùng mang một thư viện, thử xem **toàn cây** trước khi lọc; phần bị omitted ở các phiên bản plugin hỗ trợ chế độ verbose có thể giúp giải thích mediation.

Có thể xuất tree dưới định dạng có thể diff khi plugin phù hợp:

~~~bash
mvn -pl :app dependency:tree -DoutputType=json -DoutputFile=dependency-tree.json
~~~

Với Maven Dependency Plugin 3.8.1 mà parent quản lý, định dạng `json` đã được hỗ trợ. File chỉ được tạo nếu bạn chạy goal, không phải Maven tự thêm file này vào Git. Trước và sau nâng BOM, so sánh resolved tree để thấy những artifact nào thực sự đổi.

### 13.3. Artifact và classpath khi chạy

Không nên kết luận “version đúng” chỉ vì POM chứa đúng chữ. Trong bài, sau `mvn clean install` và `dependency:copy-dependencies`, kiểm tra **JAR trong `app/target/runtime-libs`** rồi chạy app bằng chính classpath đó.

Nếu production dùng Spring Boot fat JAR, WAR, container image hoặc application server, kiểm tra **artifact/distribution đã phát hành**, không chỉ Maven cache hoặc đường dẫn trên laptop. Một bản JAR ứng dụng không nhúng dependency có thể trông giống nhau trước/sau nâng version, nhưng **bộ runtime dependency JAR** đã đổi.

### 13.4. Khi Maven không thể resolve BOM

Một BOM phải có artifact `pom` tồn tại ở repository được cấu hình, hoặc đã được build/install trong reactor/local repository hợp lệ. Nếu sai tọa độ, version, repository mirror hoặc quyền truy cập, Maven có thể báo lỗi kiểu:

~~~text
Non-resolvable import POM
~~~

Đây là lỗi **giải quyết POM quản lý**, thường xảy ra trước khi compiler chạy. Kiểm tra `groupId:artifactId:version`, `type=pom`, `scope=import` và cấu hình settings/mirror/repository. Không sửa bừa source Java hoặc thêm dependency version ngẫu nhiên để che lỗi import.

## 14. Đổi một version trung tâm có thể phá nhiều module: cách kiểm soát

Quản lý tập trung giúp nâng cấp nhanh hơn, nhưng làm **phạm vi ảnh hưởng rộng hơn**. Một thay đổi nhỏ ở BOM/parent có thể tác động nhiều module độc lập, thậm chí những project tiêu thụ BOM đã phát hành.

### 14.1. Các nguy cơ phải đánh giá

| Nguy cơ | Tại sao xảy ra? | Kiểm tra |
| --- | --- | --- |
| Breaking API | Library mới bỏ/đổi method/class | Compile toàn reactor, đọc release notes |
| Binary mismatch | Compile với version khác runtime | Kiểm tra classpath/distribution, smoke test |
| Transitive dependency đổi | Version của library cha kéo graph mới | Diff dependency tree trước/sau |
| Scope sai | Dependency có mặt trong test nhưng không ở runtime | Kiểm tra scope + cách đóng gói |
| Nâng BOM nhưng module override riêng | Child có direct version hoặc managed entry khác | Effective POM từng module |
| Import nhiều BOM trùng nhau | BOM import trước/entry explicit quyết định | Review thứ tự và entries |
| JDK minimum thay đổi | Library mới yêu cầu bytecode/JDK cao hơn | Kiểm tra Maven/JDK runtime và compiler |
| Test PASS nhưng behavior thay đổi | Test hiện có chưa bao phủ integration/contract | Bổ sung integration và smoke tests |
| Release không tái tạo được | Dùng SNAPSHOT/range/profile theo máy | Ghim versions, kiểm soát build inputs |
| Version plugin khác | PluginManagement không đồng bộ | Ghim plugin version, kiểm tra toolchain |
| Artifact GAV bị phát hành đè | Hai binary khác nhau cùng tọa độ | Immutable repository và provenance |

### 14.2. Quy trình thay version nên có review

1. **Xác định** tọa độ `groupId:artifactId` hoặc BOM GAV, version cũ, version mục tiêu và lý do đổi.
2. **Tìm đúng nguồn quản lý**: direct dependency, property, parent dependencyManagement, imported BOM hay module override.
3. **Sửa tối thiểu** ở nơi đang quyết định version; không nhân thêm declarations trùng.
4. **Đọc diff POM**: bảo đảm không vô tình sửa project version, plugin version hoặc scope không liên quan.
5. **Build sạch** và chạy test cho các module chịu tác động; với reactor, dùng pipeline QA chính thức.
6. **Diff effective POM và resolved tree** ở ít nhất các module đại diện, tốt nhất toàn bộ module tiêu thụ.
7. **Smoke test runtime artifact** với dependency classpath/phương thức launch thật.
8. **Ghi nhận kết quả** trong PR/build record: commit, BOM/parent version, Maven/JDK version, test, tree changes, hash của artifact/distribution.
9. **Phát hành bất biến** và triển khai chính artifact đã được CI xây dựng. Không build lại tùy máy dưới cùng tọa độ version phát hành.

Quy trình này giúp trả lời câu hỏi không chỉ “đã nâng thư viện chưa?” mà còn “**module nào thật sự chạy thư viện phiên bản nào và có bằng chứng kiểm thử nào?**”

## 15. Giới hạn của dependencyManagement và BOM trong việc ngăn lặp

### 15.1. Không thể xóa mọi khai báo ở child

Một child vẫn cần khai báo dependency nó sử dụng. Điều được tránh lặp chủ yếu là **version và chính sách tương thích**, chứ không phải việc mô tả quan hệ module → library.

Nếu child trực tiếp import `StringUtils` nhưng xóa Commons Lang khỏi dependencies để “không lặp”, nó có thể tình cờ compile nhờ transitive dependency từ `core`. Đó là coupling không rõ ràng: một lần `core` bỏ Commons Lang có thể làm `app` gãy compile. Hãy giữ dependency trực tiếp rõ ràng.

### 15.2. Không thể thay thế compatibility testing

Một BOM có thể là bộ version được nhà cung cấp/framework xác nhận trong phạm vi họ của họ, nhưng không bảo đảm mọi extension và ứng dụng của doanh nghiệp đều tương thích. Maven chỉ giải quyết dependencies theo metadata; nó không tự test mọi hành vi của business logic.

### 15.3. Không thể tự quản lý mọi plugin hoặc repository

BOM import không đóng vai trò `pluginManagement`, `settings.xml`, mirror, proxy hoặc JDK toolchains. Các phần này là đầu vào build khác nhau; nếu không cố định, hai runner vẫn có thể gặp hành vi khác dù cùng BOM.

### 15.4. Quản lý version không giống version locking toàn đồ thị

DependencyManagement quản lý các entry đã khai và có tác động đến transitive resolution theo Maven rules. Nó **không tự tạo lockfile toàn đồ thị** và không luôn quản lý mọi version range, classifier, plugin transitive dependencies hoặc external build input.

Nếu cần reproducibility/attestation cao hơn, hãy phối hợp CI kiểm tra resolved tree, ghim plugin/JDK, repository policy và artifact checksums.

## 16. Chiến lược ngoại lệ: có thể override nhưng phải có kỷ luật

Giả sử tổ chức quản lý `commons-lang3=3.17.0` nhưng một module legacy tạm chỉ chạy ổn với `3.14.0`. Thay vì lén thêm version vào `legacy-adapter/pom.xml`, nên có:

- Một lý do kỹ thuật cụ thể (API/binary compatibility, issue, test đang fail).
- Owner chịu trách nhiệm và điều kiện bỏ ngoại lệ.
- Test riêng của legacy module và các consumer quan trọng.
- Quy tắc CI kiểm tra những module **không được phép** override.
- Một kế hoạch nâng version hoặc thay thư viện trong tương lai.

Ví dụ override **chỉ minh họa**:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
~~~

Nếu version trực tiếp của child khác managed version, module đó đang có ngoại lệ. Không nên tạo một BOM mới cho mỗi module chỉ để che đi những override thiếu review.

Ngoài ra, một project thực sự **phụ thuộc vào một version riêng** khi được đóng gói thành library có thể phát sinh conflict khi ứng dụng lớn đưa nhiều project vào cùng classpath. Tìm hiểu dependency mediation, ABI và library compatibility; ngoại lệ phải được kiểm chứng ở **ứng dụng cuối** chứ không chỉ tại module phát hành library.

## 17. Các lỗi phổ biến và cách sửa

| Lỗi/hiện tượng | Nguyên nhân hay gặp | Cách xử lý có bằng chứng |
| --- | --- | --- |
| Child khai Commons Lang không version và Maven báo thiếu version | Parent không quản lý entry; `<parent>` sai hoặc BOM không được import | Kiểm tra parent coordinates, dependencyManagement và effective POM |
| Khai version trong parent management nhưng child không có library | Management không tự thêm dependency | Child khai dependency ở `<dependencies>` |
| Parent đổi `commons.lang3.version` nhưng app vẫn dùng bản cũ | App có direct version/management override hoặc profile khác | Effective POM và dependency tree của app |
| Module có hai version của cùng library trong graph | Transitive conflict/mediation hoặc duplicate classpath khi đóng gói | Đọc resolved tree, loại nguồn xung đột đúng chỗ |
| Hai bản JAR nằm trong runtime-libs sau upgrade | Output directory chưa được clean | Build/copy lại từ `target` sạch |
| Import BOM không có tác dụng | `type/scope` sai, import ngoài management, BOM không giải quyết được | Kiểm tra cú pháp và POM hiệu lực |
| `Non-resolvable import POM` | BOM không tồn tại/không được quyền tải/repository lỗi | Xác minh tọa độ, mirror, network và credentials |
| Hai BOM có cùng managed artifact | Thứ tự import/entry explicit làm version khác dự đoán | Kiểm tra dependencyManagement hiệu lực, quyết định policy |
| BOM thay version JUnit nhưng Surefire plugin version không đổi | BOM quản lý dependency, không quản lý build plugin | Đổi đúng `pluginManagement` khi cần |
| Thay property ở project dùng BOM nhưng BOM entry không đổi | Property đó được xử lý trong imported BOM, không qua consumer override như mong muốn | Override managed entry rõ ràng hoặc nâng BOM |
| Thêm dependency trùng version cũ và mới trong child | Duplicate dependency declarations | Sửa cùng một khai báo, không nhân đôi |
| Dùng `-U` rồi hy vọng mọi version lên mới nhất | `-U` không phải chiến lược nâng library version | Đổi version quản lý và kiểm tra tree |
| Chạy `mvn clean verify` ở module app riêng nhưng thiếu core artifact | core chưa cài local repository; app không build cùng reactor | Build reactor root hoặc dùng `-pl :app -am` khi phù hợp |
| Dùng `java -jar app.jar` nhưng lỗi main class | Manifest `Main-Class`/runtime libs chưa thiết lập | Chạy `java -cp` như bài hoặc dùng packaging phù hợp |
| `NoSuchMethodError` sau nâng BOM | Runtime classpath khác compile hoặc binary incompatible | Kiểm tra distribution, library versions và integration tests |
| Test PASS nhưng deploy sai | Không kiểm chứng runtime artifacts/method launch | Smoke test đúng package và environment |
| Build bị lệch trên CI dù cùng parent POM | Profiles, settings, JDK, repository hoặc override CLI khác | Chuẩn hóa build inputs và metadata |
| Khai `dependencyManagement` cho Maven plugin mà không hiệu lực | Plugin có cơ chế quản lý khác | Dùng `pluginManagement`/`build/plugins` |

Không sửa một lỗi version chỉ bằng cách tăng bừa lên version cao nhất. Đầu tiên xác định **ai quản lý version**, Maven resolve bản nào và lỗi xảy ra ở compile, test hay runtime.

## 18. Bài tập thực hành

**Bài tập A — Loại số version lặp.** Tạo `central-bom-demo` đúng mẫu. Trong hai POM child, đếm số `<version>` ở Commons Lang và JUnit. Giải thích vì sao chúng có thể thiếu `<version>` mà Maven vẫn build được.

**Bài tập B — Một thay đổi, hai module.** Từ parent đặt `commons.lang3.version=3.14.0`, chạy `mvn clean install` và hai lệnh `dependency:tree`. Đổi parent thành `3.17.0`, build lại rồi chứng minh **cả core lẫn app** nhận version mới.

**Bài tập C — BOM không tự thêm dependency.** Bỏ JUnit dependency trong `core/pom.xml` nhưng vẫn import JUnit BOM ở parent. Dự đoán lỗi biên dịch `GreetingTest.java` khi `@Test`/assertions không còn trên test classpath. Khôi phục dependency và build lại.

**Bài tập D — Direct dependency và transitive dependency.** Bỏ Commons Lang khỏi `app/pom.xml` trong khi `app` vẫn import `StringUtils`, nhưng `app` phụ thuộc `core`, mà `core` lại phụ thuộc Commons Lang. Giải thích vì sao build *có thể* còn hoạt động nhờ transitive dependency nhưng thiết kế đó không rõ trách nhiệm. Khôi phục direct dependency của app.

**Bài tập E — Phân biệt pluginManagement.** Tìm version Compiler/Surefire trong parent. Vì sao không nên chuyển chúng vào `dependencyManagement`? Trình bày hai graph: project dependencies và plugin dependencies.

**Bài tập F — Import BOM.** Dùng snippet `company-dependencies-bom` ở mục 9, chỉ rõ các bước: phát hành POM BOM, project tiêu thụ nhập `type=pom/scope=import`, project khai Commons Lang không version, cuối cùng kiểm tra resolved tree.

**Bài tập G — Xung đột BOM.** Giả sử hai BOM quản lý cùng artifact nhưng khác version. Dự đoán rủi ro khi đổi thứ tự import và cách dùng một managed entry explicit để làm quyết định rõ ràng. Dùng effective POM để kiểm chứng thay vì dựa vào tên BOM.

**Bài tập H — Override đã phê duyệt.** Parent quản lý Commons Lang `3.17.0` nhưng một child direct dependency khai `3.14.0`. Giải thích resolved version dự kiến của child, những kiểm thử cần chạy và cách lưu lý do ngoại lệ.

**Bài tập I — Kiểm tra trước release.** Soạn checklist có tọa độ BOM/parent và version, JDK/Maven, active profiles, resolved dependency trees, unit/integration tests, runtime smoke test, artifact hash và lý do nâng cấp. Vì sao `BUILD SUCCESS` một mình không đủ?

### Tiêu chí hoàn thành

Bạn hiểu đúng khi có thể trả lời:

1. Vì sao **`dependencyManagement` không tự thêm library vào classpath**, dù có nhiều version được quản lý?
2. Với một hệ thống multi-module, cách nào giảm lặp phiên bản nhưng vẫn khiến mỗi module khai dependency nó sử dụng?
3. Khi cần đồng bộ một họ thư viện, BOM được import ở đâu và với `type/scope` nào?
4. Đổi Commons Lang ở parent một lần thì kiểm chứng thế nào để biết **tất cả module liên quan** đã nhận version mới?
5. Direct version, child dependencyManagement và imported BOM có thể ưu tiên nhau như thế nào?
6. Vì sao `pluginManagement` tách biệt với BOM/project dependencyManagement?
7. Khi gặp một exception về version, làm sao biến nó thành quyết định có kiểm thử và truy vết thay vì một override bí mật?

Thông điệp cốt lõi: **quản lý phiên bản tập trung để giảm lặp và lệch phiên bản, nhưng luôn để dependency ở đúng nơi sử dụng và kiểm tra version resolved thực tế**. BOM/parent là nguồn chính sách; `effective-pom` và `dependency:tree` là công cụ chứng minh; test và runtime smoke test xác nhận bản nâng cấp hoạt động.

## 19. Tài liệu chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): dependencyManagement, nearest-definition, BOM import, multiple BOMs và scope.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): phân biệt dependencies, dependencyManagement, properties, parent và pluginManagement.
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): aggregation, reactor, dependencies và inheritance.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): xem resolved graph và các định dạng xuất file.
- [Apache Maven Dependency Plugin — copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html): `includeScope` và `outputDirectory`.
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): xem effective POM sau khi Maven tính inheritance/management.
- [Maven Central — JUnit BOM 5.11.4](https://central.sonatype.com/artifact/org.junit/junit-bom/5.11.4): BOM của họ thư viện JUnit trong ví dụ.
- [Maven Central — Commons Lang 3.14.0](https://central.sonatype.com/artifact/org.apache.commons/commons-lang3/3.14.0) và [3.17.0](https://central.sonatype.com/artifact/org.apache.commons/commons-lang3/3.17.0): hai bản thư viện dùng để luyện tập nâng version.
