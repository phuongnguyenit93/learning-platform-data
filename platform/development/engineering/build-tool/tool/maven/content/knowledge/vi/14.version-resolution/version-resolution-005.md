# Ảnh hưởng của `dependencyManagement` đến phiên bản dependency bắc cầu trong Maven

## 1. Vấn đề: vì sao một dự án có thể dùng phiên bản khác với POM của thư viện?

Giả sử ứng dụng `app` phụ thuộc vào thư viện `lib-a`, và `lib-a` khai báo `commons-lang3:3.12.0`. Bạn đọc POM của `lib-a`, tưởng rằng ứng dụng chắc chắn sử dụng phiên bản 3.12.0. Tuy nhiên **POM hiệu lực của `app`** có thể quản lý `commons-lang3:3.14.0` bằng `<dependencyManagement>`. Kết quả: khi Maven giải quyết đồ thị dependency **cho `app`**, phiên bản được chọn có thể là **3.14.0**.

Đây là cơ chế quan trọng của Maven: **`dependencyManagement` có thể kiểm soát phiên bản dependency bắc cầu**, ngay cả khi phiên bản đó được khai báo trong POM của một thư viện khác. Nó giúp dự án chủ động quản lý classpath, nhưng cũng có thể gây lỗi tương thích nếu ép một phiên bản mà thư viện trung gian không hỗ trợ.

Mục tiêu bài học:

1. Nắm được `dependency` trực tiếp, dependency bắc cầu (*transitive dependency*), dependency mediation và `dependencyManagement`.
2. Phân biệt **nearest definition / first declaration** với **managed version**.
3. Biết vì sao `dependencyManagement` không tự tải/thêm thư viện vào classpath.
4. Thấy rõ khác biệt giữa **quyết định phiên bản của `lib-a`** và **quyết định phiên bản khi `app` dùng `lib-a`**.
5. Thực hành dự án Maven đa module với Java 17, kiểm tra `dependency:tree` và chạy chương trình.
6. Hiểu thứ tự ưu tiên giữa khai báo trực tiếp, quản lý ở parent/child và BOM nhập bằng `import`.
7. Biết kiểm tra xung đột version, scope, version compatibility và các tình huống có nguy cơ runtime failure.

Bài này chủ yếu dùng Maven 3.x, POM model 4.0.0, JDK 17+ và những artifact thực có trên Maven Central. Các phiên bản được chọn để bài dễ tái hiện, **không mặc định là phiên bản mới nhất hoặc phù hợp nhất với mọi dự án**.

## 2. Dependency trực tiếp và dependency bắc cầu

**Dependency trực tiếp** là thư viện được khai báo dưới `<dependencies>` của chính project hiện tại:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example.training</groupId>
        <artifactId>lib-a</artifactId>
        <version>1.0-SNAPSHOT</version>
    </dependency>
</dependencies>
~~~

**Dependency bắc cầu** là thư viện mà project nhận được thông qua POM của dependency khác. Nếu `lib-a` có dependency compile tới Commons Lang, đồ thị của `app` thường bao gồm cả Commons Lang:

~~~text
app
└── lib-a:1.0-SNAPSHOT       (trực tiếp)
    └── commons-lang3:3.12.0 (bắc cầu, theo POM gốc của lib-a)
~~~

Maven giải quyết đồ thị từ các POM liên quan, rồi tính phiên bản/scope sẽ đưa vào classpath của project hiện tại. Dependency bắc cầu không đòi hỏi bạn lặp lại mọi dependency dưới POM của `app`, nhưng việc dùng thư viện qua transitive dependency cần được hiểu rõ để tránh phụ thuộc ngầm không ổn định.

### Scope vẫn ảnh hưởng việc dependency có bắc cầu hay không

Một dependency không phải lúc nào cũng được lan truyền. Ví dụ:

- `compile` thường lan truyền tới consumer và có trong compile/runtime classpath.
- `runtime` có thể được lan truyền với scope phù hợp.
- `provided` và `test` không lan truyền như dependency runtime/compile thông thường.
- `optional=true` có thể ngăn dependency được đưa vào consumer tự động.
- `<exclusions>` có thể chặn một nhánh dependency cụ thể.

**`dependencyManagement` không tạo lại một dependency đã bị loại khỏi đồ thị.** Muốn kiểm soát phiên bản, artifact trước tiên phải thực sự được tham chiếu qua direct/transitive dependency, hoặc bạn phải khai báo nó trực tiếp.

## 3. Dependency mediation khi chưa có managed version

Nếu nhiều nhánh yêu cầu các phiên bản khác nhau của **cùng tọa độ artifact**, Maven cần chọn một phiên bản. Với các phiên bản thông thường không có ràng buộc đặc biệt, Maven dựa trên quy tắc **nearest definition**: phiên bản ở đường đi ngắn nhất từ project tới dependency được ưu tiên.

Ví dụ:

~~~text
app
├── lib-a
│   └── helper
│       └── common-lib:2.0 (độ sâu 3)
└── lib-b
    └── common-lib:1.0     (độ sâu 2)
~~~

Nếu không có chính sách quản lý hoặc khai báo trực tiếp buộc một phiên bản khác, Maven thường chọn **`common-lib:1.0`** vì nó gần `app` hơn. **Nearest không có nghĩa newest**: Maven không mặc định luôn chọn phiên bản số lớn nhất.

Nếu hai phiên bản ở cùng độ sâu, **nhánh được khai báo trước** trong thứ tự giải quyết dependency thường thắng theo quy tắc *first declaration wins*. Vì vậy chỉ đổi thứ tự dependency trong POM đôi khi làm thay đổi kết quả mediation.

Ví dụ ở cùng độ sâu:

~~~text
app
├── lib-a
│   └── common-lib:2.0
└── lib-b
    └── common-lib:1.0
~~~

Nếu `lib-a` được khai báo trước `lib-b` và không có managed version hoặc các ràng buộc khác, `2.0` thường được chọn. Đây là hành vi mediation, **không phải quản lý phiên bản**.

### Khai báo trực tiếp có thể kiểm soát phiên bản

Nếu `app` trực tiếp khai báo:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>common-lib</artifactId>
    <version>2.0</version>
</dependency>
~~~

thì đường đi từ `app` tới `common-lib` có độ sâu **1**, thường thắng các nhánh bắc cầu dài hơn. Khai báo trực tiếp rất phù hợp khi source code của `app` thực sự gọi API trong thư viện đó.

Tuy nhiên thêm một dependency trực tiếp **chỉ để chọn version** có thể làm POM khó đọc. Đó là lý do Maven cung cấp `<dependencyManagement>`: quản lý phiên bản mà không nhất thiết biến dependency thành một thư viện trực tiếp được sử dụng.

## 4. `dependencyManagement` thay đổi luật chọn phiên bản như thế nào?

Mảnh POM cấp project:

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

Đọc đúng ý nghĩa:

- `<dependencyManagement>` định nghĩa **chính sách quản lý** cho dependency khớp tọa độ.
- `org.apache.commons:commons-lang3:3.14.0` là phiên bản được quản lý.
- Nếu `commons-lang3` được tham chiếu **bắc cầu** qua một dependency của project hiện tại, Maven có thể chọn **3.14.0** thay vì phiên bản ghi trong POM của thư viện trung gian.
- Nếu project trực tiếp khai báo `commons-lang3` **không có `<version>`**, bản managed version có thể cung cấp version cho khai báo ấy.
- **Chỉ có `dependencyManagement`, không có đường dẫn dependency tới artifact, thì artifact không tự xuất hiện trên classpath.**

Điểm then chốt được tài liệu Maven diễn đạt: **dependency management có ưu tiên cao hơn dependency mediation đối với dependency bắc cầu**. Nói cách khác, thay vì để nearest/first chọn tùy đồ thị, người sở hữu project có thể chốt version bắc cầu bằng chính sách trong effective POM.

### Minh họa trước và sau

Giả sử POM `lib-a` khai báo:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.12.0</version>
</dependency>
~~~

Khi `app` **không** có quản lý version thích hợp, trường hợp chỉ một đường đi có thể có:

~~~text
app
└── lib-a:1.0-SNAPSHOT
    └── commons-lang3:3.12.0
~~~

Khi `app` có chính sách quản lý `commons-lang3:3.14.0`:

~~~text
app
└── lib-a:1.0-SNAPSHOT
    └── commons-lang3:3.14.0  (version được quản lý cho app)
~~~

POM gốc đã xuất bản của `lib-a` vẫn ghi `3.12.0`. Maven **không sửa file POM của thư viện trung gian**: nó chỉ quyết định graph/classpath **trong ngữ cảnh `app`**.

### Không lẫn “quản lý” và “khai báo sử dụng”

| Nơi khai báo | Ý nghĩa | Có tự đưa JAR vào graph? |
| --- | --- | --- |
| `<dependencies><dependency>` | Dự án thực sự dùng dependency trực tiếp. | Có, theo scope và resolution. |
| `<dependencyManagement><dependencies>` | Quản lý version/scope/exclusions/type và thuộc tính phù hợp khi dependency được tham chiếu. | **Không**. |
| `<build><pluginManagement>` | Quản lý version/configuration của build plugins. | Không thêm project dependency. |
| `<build><plugins>` | Khai báo/cấu hình plugins dùng trong build. | Không tương đương khai báo dependency ứng dụng. |

**Lưu ý đặc biệt:** `dependencyManagement` của dự án **không áp đặt phiên bản cho các dependency của Maven plugin**. Plugin có dependency graph riêng; nếu cần kiểm soát plugin, dùng `pluginManagement`, phiên bản plugin và cấu hình plugin theo tài liệu tương ứng.

## 5. Thứ tự ưu tiên: trực tiếp, managed, nearest và parent

Khi giải thích kết quả, trước tiên phân biệt **dependency trực tiếp trong project hiện tại** và **dependency bắc cầu**.

| Tình huống | Version chọn theo cơ chế thông thường |
| --- | --- |
| `app` khai báo trực tiếp `commons-lang3:3.12.0` có `<version>`. | **3.12.0** cho dependency trực tiếp đó; version tường minh thường thắng bản 3.14.0 được quản lý. |
| `app` khai báo trực tiếp `commons-lang3` **không có version**, effective `dependencyManagement` quản lý 3.14.0. | **3.14.0**, được điền từ quản lý. |
| `app` chỉ phụ thuộc `lib-a`, `lib-a` phụ thuộc `commons-lang3:3.12.0`, `app` quản lý 3.14.0. | **3.14.0** cho đường đi bắc cầu trong `app`. |
| `app` có hai nhánh kéo về 3.12.0 và 3.14.0, không có quản lý, độ sâu khác nhau. | Theo **nearest definition**. |
| Hai nhánh có độ sâu bằng nhau, không có quản lý. | Theo **first declaration wins** khi không có ràng buộc khác. |
| Không nhánh nào tham chiếu `commons-lang3` và `app` không khai báo trực tiếp, nhưng có quản lý 3.14.0. | **Không có commons-lang3** trong graph chỉ vì khai báo quản lý. |

Đây là bảng giải thích cơ bản cho version cố định và tọa độ artifact thông thường. Maven còn xử lý version ranges, scope, exclusions, classifier, type, profiles và dependency mediation. Đừng dùng quy tắc trên để bỏ qua một ràng buộc version đặc biệt hoặc một graph được điều chỉnh bởi plugin.

### Parent và POM hiện tại

`dependencyManagement` thường nằm trong **parent POM** để các module kế thừa một bộ version thống nhất. Nếu parent quản lý `commons-lang3:3.14.0`, module con dùng bản managed version đó **trừ khi module con có khai báo hoặc quản lý phù hợp hơn**.

Nếu cùng một dependency được khai báo trong `dependencyManagement` của **POM con** và **parent**, phần quản lý ở POM hiện tại thường được ưu tiên cho chính project đó. Tuy nhiên, **một direct dependency với version tường minh** vẫn cần được phân biệt với entry quản lý.

Đặc biệt: khi parent quản lý 3.14.0 nhưng một module có direct dependency **tường minh** 3.12.0, module đó có thể dùng 3.12.0. Một module **khác** kế thừa cùng parent có thể quản lý transitive dependency thành 3.14.0. Đây là tình huống của bài thực hành dưới đây.

## 6. Thực hành Java 17: project đa module và phiên bản bắc cầu

Ta tạo một Maven reactor với ba POM: parent ở thư mục gốc, `lib-a` và `app`. Bài này có thể build bằng Maven 3.x/JDK 17+ khi truy cập được các artifact và plugin cần thiết.

Mô hình mục tiêu:

~~~text
version-management-demo/
├── pom.xml                       # parent + aggregator
├── lib-a/
│   ├── pom.xml
│   └── src/main/java/com/example/lib/TextFormatter.java
└── app/
    ├── pom.xml
    └── src/main/java/com/example/app/App.java
~~~

**Dòng dependency:**

~~~text
app (kế thừa parent quản lý commons-lang3:3.14.0)
   │
   ▼
lib-a:1.0-SNAPSHOT
   │
   ▼
commons-lang3:3.12.0 (version lib-a khai báo)
   │
   ▼
app chọn commons-lang3:3.14.0 cho graph của app
~~~

`lib-a` và `app` là hai project khác nhau. Chúng đều kế thừa parent nhưng giải quyết dependency của mình theo **POM hiệu lực và các khai báo trực tiếp riêng**.

### 6.1. Parent/aggregator: `version-management-demo/pom.xml`

Tạo tệp sau tại thư mục gốc:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.training</groupId>
    <artifactId>version-management-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>lib-a</module>
        <module>app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>3.14.0</version>
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
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-install-plugin</artifactId>
                    <version>3.1.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

Giải thích:

- `<packaging>pom</packaging>` là kiểu packaging cho parent/aggregator, không tự tạo JAR Java chính.
- `<modules>` khai báo các module thuộc cùng Maven reactor.
- `dependencyManagement` quản lý **commons-lang3 3.14.0** cho các project kế thừa khi applicable.
- `maven.compiler.release=17` và các plugin version chốt thông số build nhất quán.
- `pluginManagement` không thêm dependency ứng dụng; nó quản lý phiên bản/config plugin dùng bởi các lifecycle bindings hoặc khai báo plugin tương ứng.

**Nhầm lẫn cần tránh:** chỉ đặt `commons-lang3` ở `dependencyManagement` của parent **không đưa Commons Lang tự động vào parent, `lib-a` hay `app`**. Thư viện chỉ có mặt khi dependency graph của module thực sự yêu cầu.

### 6.2. Module `lib-a`: cố ý khai báo trực tiếp 3.12.0

Tạo `lib-a/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.training</groupId>
        <artifactId>version-management-demo</artifactId>
        <version>1.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>lib-a</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.12.0</version>
        </dependency>
    </dependencies>
</project>
~~~

Ở `lib-a`, `commons-lang3` là dependency **trực tiếp** với version tường minh **3.12.0**. Mặc dù parent quản lý 3.14.0, direct version tường minh của `lib-a` vẫn được dùng khi Maven giải quyết dependency **cho chính `lib-a`**.

Tạo `lib-a/src/main/java/com/example/lib/TextFormatter.java`:

~~~java
package com.example.lib;

import org.apache.commons.lang3.StringUtils;

public final class TextFormatter {
    private TextFormatter() {
    }

    public static String format(String value) {
        return StringUtils.capitalize(value);
    }
}
~~~

`TextFormatter.format("maven")` trả về `"Maven"`. API `StringUtils.capitalize` được dùng bởi cả phiên bản 3.12.0 và 3.14.0 trong bài, vì vậy ví dụ không phụ thuộc một method chỉ tồn tại ở phiên bản mới. **Một dự án thực tế vẫn phải kiểm tra tương thích API/binary khi thay version**; ví dụ này không chứng minh mọi thư viện đều tương thích giữa các phiên bản.

### 6.3. Module `app`: chỉ khai báo dependency vào `lib-a`

Tạo `app/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.training</groupId>
        <artifactId>version-management-demo</artifactId>
        <version>1.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.training</groupId>
            <artifactId>lib-a</artifactId>
            <version>1.0-SNAPSHOT</version>
        </dependency>
    </dependencies>
</project>
~~~

`app` **không khai báo `commons-lang3` trực tiếp**. Nó nhận dependency này thông qua `lib-a`. Parent mà `app` kế thừa đã quản lý phiên bản 3.14.0, do đó `app` có thể chọn `commons-lang3:3.14.0` cho đường đi bắc cầu.

Lưu ý: ví dụ POM con ở trên cần **sửa một dòng schemaLocation** theo đúng cặp namespace và XSD sau (dòng này đã được dùng trong parent và `lib-a`):

~~~xml
xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd"
~~~

Tệp `app/pom.xml` sẽ có đúng dòng này trong thẻ `project` khi bạn tạo file thực hành. Cách viết phải đảm bảo khai báo namespace và schemaLocation nhất quán; không coi đoạn sửa riêng là một POM thứ hai.

Tạo `app/src/main/java/com/example/app/App.java`:

~~~java
package com.example.app;

import com.example.lib.TextFormatter;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Hello, " + TextFormatter.format("maven") + "!");
    }
}
~~~

Class `App` chỉ gọi API của `lib-a`, không import trực tiếp `StringUtils`. Khi chạy, `lib-a` vẫn cần Commons Lang có mặt trên runtime classpath. Việc `app` không trực tiếp import Commons Lang không có nghĩa dependency bắc cầu đó là không cần thiết.

### 6.4. Build toàn reactor

Mở terminal tại thư mục `version-management-demo`, nơi có parent `pom.xml`:

~~~bash
mvn --version
java -version
mvn clean install
~~~

Lệnh `mvn clean install` build các module theo thứ tự mà reactor tính từ quan hệ dependency, sau đó cài POM/JAR vào **local Maven repository**. Việc chạy `install` giúp các lệnh kiểm tra riêng module ở những bước sau có thể phân giải artifact `com.example.training:lib-a:1.0-SNAPSHOT` từ local repository.

Khi tất cả plugin/dependency tải được và Java compiler tương thích, bạn sẽ có các file như:

~~~text
version-management-demo/
├── pom.xml
├── lib-a/target/lib-a-1.0-SNAPSHOT.jar
└── app/target/app-1.0-SNAPSHOT.jar
~~~

Cây đã rút gọn, không liệt kê các lớp, trạng thái plugin hoặc metadata. `mvn clean install` **không đồng nghĩa upload lên Maven Central**; nó chỉ đưa artifact vào kho Maven cục bộ của môi trường đang dùng.

### 6.5. Quan sát `lib-a` dùng version nào

Chạy từ thư mục **gốc** reactor:

~~~bash
mvn -f lib-a/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.7.1:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Khi chạy trên POM `lib-a`, ta kiểm tra dependency trực tiếp:

~~~text
com.example.training:lib-a:jar:1.0-SNAPSHOT
\- org.apache.commons:commons-lang3:jar:3.12.0:compile
~~~

Đoạn trên là **mô hình kết quả cần tìm**, không phải toàn bộ stdout cố định của Maven. Prefix `[INFO]`, thứ tự/độ chi tiết log và ký hiệu vẽ cây có thể thay đổi theo plugin hoặc terminal.

### 6.6. Quan sát `app` chọn version bắc cầu nào

Cũng từ thư mục gốc:

~~~bash
mvn -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.7.1:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Dependency tree của `app` sẽ thể hiện đường đi logic:

~~~text
com.example.training:app:jar:1.0-SNAPSHOT
\- com.example.training:lib-a:jar:1.0-SNAPSHOT:compile
   \- org.apache.commons:commons-lang3:jar:3.14.0:compile
~~~

**Điểm cần xác nhận:** bên dưới `lib-a`, version Commons Lang được chọn cho `app` là **3.14.0**, khác với 3.12.0 trong POM của `lib-a`.

Nếu muốn xem thêm thông tin về version bị quản lý hoặc xung đột, Maven Dependency Plugin có tùy chọn:

~~~bash
mvn -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.7.1:tree -Dverbose -Dincludes=org.apache.commons:commons-lang3
~~~

Plugin có thể thể hiện chú thích dạng `version managed from 3.12.0` hoặc các nhánh bị loại/omitted. Cách hiển thị thay đổi theo phiên bản plugin và bộ lọc, nên **không kiểm thử bằng cách bắt buộc toàn bộ log phải khớp một chuỗi duy nhất**. Kiểm tra artifact cuối cùng có tọa độ `commons-lang3:3.14.0` mới là trọng tâm.

### 6.7. Chạy Java với runtime classpath đúng

Plain Maven JAR **không tự đóng gói tất cả dependency JAR**. Để chạy chương trình, cần `app`, `lib-a` và Commons Lang trên runtime classpath. Sau `mvn clean install`, có thể nhờ Maven Dependency Plugin tạo một file chứa classpath cho `app`:

~~~bash
mvn -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.7.1:build-classpath -DincludeScope=runtime -Dmdep.outputFile=target/runtime-classpath.txt
~~~

Lệnh này tạo file classpath tại `app/target/runtime-classpath.txt` theo project `app`; file chứa đường dẫn các JAR dependency đã phân giải, thông thường bao gồm `lib-a` và **commons-lang3 3.14.0**. `includeScope=runtime` yêu cầu lọc các dependency dùng ở runtime (bao gồm scope compile/runtime phù hợp). Dữ liệu đầu vào được lấy từ graph của `app`, **không phải chỉ từ POM của `lib-a`**.

**Bash (Linux/macOS), đứng tại thư mục gốc reactor:**

~~~bash
CP="$(cat app/target/runtime-classpath.txt)"
java -cp "app/target/classes:$CP" com.example.app.App
~~~

**PowerShell (Windows), đứng tại thư mục gốc reactor:**

~~~powershell
$cp = (Get-Content -LiteralPath "app\target\runtime-classpath.txt" -Raw).Trim()
java -cp "app\target\classes;$cp" com.example.app.App
~~~

**Stdout chính xác của lệnh Java khi classpath có đầy đủ dependency:**

~~~text
Hello, Maven!
~~~

Lưu ý:

- Trên Linux/macOS, ký tự ngăn cách classpath thường là `:`; trên Windows là `;`. Dependency Plugin tạo classpath tương ứng với môi trường nơi nó chạy.
- `app/target/classes` chứa `App.class` của app; file classpath do Maven tạo chứa những dependency JAR khác.
- Bạn có thể dùng `app/target/app-1.0-SNAPSHOT.jar` thay cho `app/target/classes` trong lệnh `java -cp`. Nhưng **`java -jar` không được bảo đảm chạy** vì POM chưa khai báo `Main-Class` và JAR không chứa dependency.
- Nếu dự án dùng custom local repository, công cụ lấy classpath tự động ít phụ thuộc vào vị trí `~/.m2/repository` hơn cách tự viết đường dẫn tuyệt đối.
- Lệnh `dependency:build-classpath` có thể cần tải Maven Dependency Plugin nếu chưa có trong cache. Trên máy không có mạng hoặc dùng mirror nội bộ, hãy đảm bảo repository được cấu hình hợp lệ.

## 7. Thử thay đổi chính sách và dự đoán kết quả

### 7.1. Bỏ `dependencyManagement` khỏi parent

Để kiểm tra tác động thực, hãy **chỉ trong bản copy bài tập**, tạm bỏ phần quản lý `commons-lang3:3.14.0` ở parent; giữ nguyên direct dependency trong `lib-a` là 3.12.0 và không thêm Commons Lang trực tiếp vào `app`.

Khi chỉ còn một đường đi tới Commons Lang, `app` dự kiến nhận `3.12.0` từ `lib-a`. Chạy lại `mvn clean install`, rồi dùng `dependency:tree` trên `app` để xác minh.

**Không thực hiện cách này trên dự án production** mà chưa rà soát tác động của việc bỏ quản lý version: nhiều module khác có thể đang trông đợi bản managed version.

### 7.2. Khai báo trực tiếp không có version tại `app`

Giữ parent quản lý 3.14.0. Nếu `app` **thực sự import và gọi Commons Lang trực tiếp**, hãy bổ sung vào `<dependencies>` của `app`:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
</dependency>
~~~

Đây là **mảnh XML thêm vào `<dependencies>` của `app`**, không phải POM độc lập. Maven lấy version **3.14.0** từ quản lý vì dependency trực tiếp không khai báo version.

Khi một lớp của `app` trực tiếp import `org.apache.commons.lang3.StringUtils`, cách khai báo dependency trực tiếp này cũng là **thực hành tốt**: không phụ thuộc vào việc `lib-a` có tiếp tục mang dependency bắc cầu đó hay không.

### 7.3. Khai báo trực tiếp và có version khác

Nếu `app` khai báo:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.12.0</version>
</dependency>
~~~

thì version tường minh ở khai báo trực tiếp của `app` thường **được dùng cho dependency trực tiếp đó**, dù parent có managed version 3.14.0. Khi giải quyết project hiện tại, cần phân biệt **version trực tiếp bạn viết** với **chính sách managed version dành cho transitive dependency**.

Đừng thêm một dependency trực tiếp chỉ để “đánh bại” parent mà không giải thích ý định. Nếu cả nhóm cần một version mới cho mọi module, cập nhật chính sách `dependencyManagement` có thể rõ ràng hơn; nếu module có nhu cầu tương thích riêng, hãy ghi chú và kiểm thử lý do override.

### 7.4. Đặt `dependencyManagement` ở chính `app`

Nếu `app` thêm một mục quản lý `commons-lang3:3.15.0` trong `<dependencyManagement>` của **POM app**, mục quản lý đó thường ưu tiên hơn mục tương ứng kế thừa từ parent cho **app**.

Ví dụ mảnh cấu hình cấp project:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.15.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Nếu dependency graph của `app` có đường đi tới Commons Lang, bản managed version mới có thể được chọn cho `app`. **`lib-a` vẫn có chính sách riêng**, không tự sửa POM hoặc bytecode đã build của `lib-a`.

Khi thử version mới, cần xác minh artifact đó tồn tại, tương thích binary, các dependency đi kèm và hành vi runtime. Không dùng việc dependency tree “chọn được version” làm bằng chứng ứng dụng chắc chắn tương thích.

## 8. BOM: quản lý cả bộ phiên bản và ảnh hưởng đến transitives

**BOM (Bill of Materials)** là một POM dùng để quản lý tập phiên bản của nhiều artifact liên quan. Project có thể nhập BOM bằng `type=pom` và `scope=import` **bên trong `dependencyManagement`**.

Ví dụ **mảnh cấu hình có tọa độ BOM thực**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>5.10.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Một dự án dùng BOM đó có thể khai báo JUnit Jupiter API mà không lặp version:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter-api</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**Chú ý:** hai đoạn trên là **mảnh cấu hình**, cần chèn đúng cấp vào POM thích hợp; không chèn cả hai vào `lib-a` hoặc `app` của bài thực hành nếu không có mục đích kiểm thử JUnit.

Maven nhập danh sách managed dependencies từ BOM; BOM **không tự đưa toàn bộ các thư viện nó quản lý vào classpath**. Nếu một artifact đã được đưa vào graph qua đường đi bắc cầu, version quản lý lấy từ BOM có thể ảnh hưởng cách version được chọn.

### BOM và parent khác nhau

- **Parent POM:** truyền cấu hình qua `<parent>` và quan hệ kế thừa, bao gồm `dependencyManagement`, properties, pluginManagement và các thành phần khác.
- **Imported BOM:** đưa **các mục quản lý dependency** của một POM khác vào chính sách managed versions; không thay parent của project, không tự kế thừa toàn bộ build/plugins từ BOM.
- Maven POM truyền thống chỉ cho một khai báo `<parent>` ở một project, trong khi có thể nhập nhiều BOM trong dependencyManagement.

Nếu muốn ổn định cả bộ thư viện trong một framework, BOM rất hữu ích. Tuy nhiên một BOM của version mới không phải đảm bảo các module bên thứ ba trong dự án đã tương thích. Hãy đọc release notes và chạy test.

### Xung đột giữa nhiều BOM

Giả sử một POM nhập BOM X rồi BOM Y, cả hai quản lý cùng artifact A nhưng với hai version khác nhau. Theo ví dụ chính thức của Maven, **nếu POM hiện tại không khai báo quản lý A riêng, BOM được nhập trước có thể quyết định version cho A**.

Ngược lại, một mục managed A được khai báo **trực tiếp trong POM hiện tại** có thể được ưu tiên trước bản từ các BOM nhập. Đây là lý do thứ tự nhập BOM và việc override tại dự án cần được kiểm tra chứ không đoán.

Không bắt buộc “BOM có version cao hơn sẽ tự thắng”. Hãy kiểm tra `help:effective-pom` và `dependency:tree` trong **module thực sự sử dụng thư viện**.

## 9. Quản lý theo khóa tọa độ: không chỉ mỗi `artifactId`

Một entry quản lý không áp dụng đơn giản cho mọi thư viện có cùng tên `artifactId`. Maven sử dụng thông tin tọa độ để xác định dependency được quản lý, trong đó thường quan trọng là:

- `groupId` và `artifactId`;
- `type` (mặc định thường là `jar` khi không khai báo);
- `classifier` nếu có;
- các trường quản lý như version, scope, exclusions khi phù hợp.

Ví dụ `org.example:tools:jar` không nhất thiết là cùng managed key với `org.example:tools:test-jar` có classifier `tests`. Khi một managed version “không có tác dụng”, kiểm tra tọa độ đầy đủ và artifact type/classifier chứ không chỉ tên.

### Managed scope và exclusions không được bỏ qua

`dependencyManagement` có thể quản lý nhiều thông tin hơn `<version>`. Ví dụ:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>service-client</artifactId>
            <version>2.3.0</version>
            <scope>runtime</scope>
            <exclusions>
                <exclusion>
                    <groupId>com.example</groupId>
                    <artifactId>legacy-bridge</artifactId>
                </exclusion>
            </exclusions>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **mảnh cấu hình minh họa**, không phải artifact được bảo đảm tồn tại. Nó cho thấy managed entry có thể mô tả scope/exclusions cho dependency được khai báo/tham chiếu trong ngữ cảnh phù hợp.

Không kết luận việc đặt `scope=runtime` trong management tự tạo một dependency runtime. Artifact phải được tham chiếu. Hơn nữa, scope hiệu lực còn phụ thuộc đường đi transitive và quy tắc scope mediation. Luôn kiểm tra graph thực.

**Phân biệt với exclusions tại dependency trực tiếp:** khi chỉ muốn loại một thư viện khỏi **một đường đi** cụ thể, đặt `<exclusions>` ở dependency kéo thư viện đó vào thường rõ ràng hơn. Nếu exclusion thiếu dependency thực sự cần lúc chạy, ứng dụng có thể lỗi. Đừng lạm dụng exclusions để che version conflict mà chưa xác định nguyên nhân.

## 10. Effective POM không thay thế dependency tree

Hai công cụ trả lời hai câu hỏi khác nhau.

| Công cụ | Hỏi điều gì? | Giới hạn |
| --- | --- | --- |
| `mvn help:effective-pom` | POM hiện tại sau kế thừa, profile và hợp nhất quản lý dependency có gì? | Không phải danh sách toàn bộ các đường đi transitive cuối cùng theo dạng graph dễ đọc. |
| `mvn dependency:tree` | Những dependency nào thực sự được giải quyết và version/scope nào được chọn trong project? | Cần xem đúng module, filter và tùy chọn hiển thị; output có thể bị rút gọn. |
| `mvn dependency:build-classpath` | Classpath của các dependency được chọn cho một scope cụ thể là gì? | Không tự thêm output classes của chính app; môi trường Java launcher cần được cấu hình. |
| `mvn help:active-profiles` | Profile Maven nào đang active? | Không tự giải thích mọi version conflict. |
| `mvn --version` | Maven/JDK nào đang thực hiện resolution/build? | Không phải chính sách version của dependencies. |

### Các lệnh kiểm tra nhanh

~~~bash
mvn -f app/pom.xml help:effective-pom -Doutput=effective-pom.xml
mvn -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.7.1:tree
mvn -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.7.1:tree -Dverbose
~~~

Trong effective POM của `app`, tìm mục managed `commons-lang3 3.14.0`. Trong dependency tree, tìm **version cuối cùng** mà `app` thực sự sử dụng. Nếu vẫn thấy 3.12.0, hãy kiểm tra parent có được resolve đúng không, profile có đổi managed version không, direct dependency có version tường minh không, và type/classifier có khớp không.

### Lưu ý khi chạy một module trong reactor

Từ root, nếu chỉ chạy:

~~~bash
mvn -pl app package
~~~

trong lúc `lib-a` chưa được build/cài vào local repository, Maven có thể không tìm được artifact `lib-a:1.0-SNAPSHOT`. Khi cần xây các module phụ thuộc trong cùng reactor, có thể dùng:

~~~bash
mvn -pl app -am package
~~~

`-am` yêu cầu Maven xây thêm những project của reactor mà module được chọn cần. Còn trong hướng dẫn chính, `mvn clean install` đã cài `lib-a` vào local repository để các lệnh `-f app/pom.xml` chạy độc lập dễ hơn.

## 11. Ba ngộ nhận dễ gây lỗi

### 11.1. “Tôi quản lý version 3.14.0 nên mọi module chắc chắn chạy bản đó”

Không chính xác. Parent quản lý version là một **chính sách được kế thừa**, nhưng module có thể có direct version tường minh, mục quản lý riêng hoặc graph khác.

Trong thực hành:

~~~text
lib-a POM: direct commons-lang3:3.12.0
app POM:   transitive commons-lang3 được quản lý thành 3.14.0
~~~

Cả hai có thể đồng thời đúng. Cần kiểm tra **module và ngữ cảnh resolution**.

### 11.2. “Đặt dependency vào `dependencyManagement` là Maven sẽ tự tải và đóng gói nó”

Không. Một entry quản lý không làm dependency có mặt trong graph nếu không có đường dẫn tham chiếu. Và **plain JAR** của Maven không tự gộp toàn bộ dependencies kể cả dependency có scope `compile`. Muốn chạy Java, vẫn cần classpath phù hợp hoặc một plugin/launcher đóng gói theo kiến trúc ứng dụng.

### 11.3. “Dependency tree chọn được bản mới nghĩa là runtime chắc chắn hoạt động”

Không. Bản API mới có thể không tương thích với thư viện trung gian, dù Maven compile và resolve thành công. Ví dụ code đã compile với class/method của 3.12.0 nhưng runtime 3.14.0 lại thay đổi API không tương thích (đây là tình huống **giả định** cho thư viện bất kỳ). Lúc chạy có thể xuất hiện `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi hành vi.

**Mediation giải quyết chọn phiên bản, không tự chứng minh binary compatibility.** Với dự án thật, cần chạy unit test và integration test sau khi đổi managed version, kiểm tra advisories và release notes.

## 12. Quản lý version để nâng cấp bảo mật: lợi ích và giới hạn

Một lý do thực tế để dùng `dependencyManagement` là kiểm soát dependency bắc cầu khi cần tránh một phiên bản có vấn đề.

Ví dụ giả định:

~~~text
app
└── client-sdk
    └── parser-lib:1.2 (phiên bản cần thay)
~~~

Bạn có thể quản lý `parser-lib:1.5` trong effective POM của app, khi đó Maven chọn version mới nếu dependency vẫn được tham chiếu hợp lệ. Nhưng:

1. **Kiểm tra source advisory** để biết bản nào thực sự có bản vá.
2. **Kiểm tra binary/API compatibility** với client-sdk.
3. **Kiểm tra các đường đi khác** có thể kéo thêm version hoặc artifact có tên khác.
4. **Xác nhận bản runtime thật** qua dependency tree, artifact build và classpath/container.
5. **Kiểm thử lại** trước khi phát hành.

Không chọn version theo cảm tính hoặc chỉ vì “số lớn hơn”. Một số bản nâng cấp yêu cầu thay đổi mã hoặc đồng bộ cả họ thư viện theo BOM. Trong hệ sinh thái dùng BOM của framework, cập nhật một dependency riêng lẻ có thể phá ma trận tương thích.

### Version ranges và SNAPSHOT

Một số POM dùng version ranges, version properties hoặc `-SNAPSHOT`. Tác động của management có thể tương tác với các ràng buộc version và resolution policy. Để build dễ tái hiện:

- Ưu tiên version cố định được chấp thuận cho release.
- Hạn chế để môi trường build tự lấy version thay đổi theo thời gian nếu không có quy trình kiểm soát.
- Ghi lại các BOM/parent version đang dùng.
- Kiểm tra graph thực tế thay vì suy luận chỉ từ property.
- Khi có quy tắc bắt buộc về version/range, hãy đối chiếu POM reference và lỗi resolver, không ép một version xung đột rồi coi là build an toàn.

## 13. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| Chỉ thêm `dependencyManagement` nhưng code import class vẫn lỗi compile | Chưa khai báo dependency trực tiếp hoặc không có transitive path tới artifact. | Thêm vào `<dependencies>` nếu source code thực sự dùng thư viện; management chỉ quản lý. |
| POM `lib-a` ghi 3.12.0 nhưng `app` dùng 3.14.0 | `app` hoặc parent quản lý transitive version 3.14.0. | Xem effective POM của `app` và `dependency:tree`. |
| Đổi managed version ở parent nhưng một module vẫn dùng bản cũ | Module có version trực tiếp, quản lý riêng hoặc coordinate/type khác. | So POM và dependency tree **từng module**. |
| Thêm direct dependency có version nhưng vẫn kỳ vọng management ép nó sang version khác | Khai báo trực tiếp và có version tường minh có vai trò riêng. | Bỏ version trực tiếp để dùng management nếu đó là chủ trương, rồi test. |
| Chỉ nhìn nearest path rồi dự đoán sai version | Managed version có thể ưu tiên hơn mediation đối với transitive dependency. | Tìm chính sách `dependencyManagement` và imported BOM. |
| Hai nhánh cùng độ sâu chọn một version “khó hiểu” | `first declaration wins` khi không có quản lý/ràng buộc khác. | Xem thứ tự dependency trong POM và tree đầy đủ. |
| Nhập hai BOM nhưng bản version khác kỳ vọng | BOM import order và mục quản lý tại POM hiện tại có thể quyết định. | Xem thứ tự import, local overrides và effective POM. |
| Quản lý `commons-lang3` nhưng lỗi ở dependency của plugin | Project dependencyManagement không điều khiển plugin transitive dependencies. | Kiểm tra `pluginManagement`, plugin version và plugin dependencies. |
| `mvn dependency:tree` chỉ thấy một phiên bản, tưởng không có conflict | Maven mediation đã chọn một phiên bản, những nhánh bị loại có thể không hiện rõ. | Dùng `-Dverbose` (nếu plugin hỗ trợ), giảm filter, đối chiếu POM nguồn. |
| `NoSuchMethodError` sau khi nâng managed version | Thư viện trung gian có thể không tương thích binary với bản được chọn. | So compile/runtime JAR thực tế, chạy test tích hợp, chọn version tương thích. |
| `ClassNotFoundException` khi chạy JAR | Java launcher classpath thiếu dependency hoặc packaging khác dự kiến. | Dùng dependency classpath thích hợp; đừng nhầm plain JAR với fat JAR. |
| `mvn -f app/pom.xml` không resolve được `lib-a` | Module `lib-a` chưa được cài/không nằm trong reactor của invocation. | Build reactor bằng `mvn clean install` hoặc dùng `-pl app -am` đúng ngữ cảnh. |
| Kết quả local và CI khác nhau | Maven/JDK/parent/profile/settings/BOM khác, snapshot thay đổi hoặc cache riêng. | Ghi cấu hình build, active profiles và dependency tree ở mỗi môi trường. |
| Quản lý không tác động tới artifact có classifier | Entry quản lý không khớp type/classifier của dependency. | Kiểm tra tọa độ đầy đủ và effective POM. |

## 14. Quy trình kiểm chứng chuẩn trong dự án thật

Khi một thư viện xuất hiện với version không mong đợi:

1. **Chọn đúng module:** điều tra project thực sự tạo artifact có lỗi, không chỉ parent.
2. **Xem direct dependency:** trong POM module có khai báo version tường minh không?
3. **Xem management:** POM hiện tại, parent, active profiles và imported BOM quản lý phiên bản nào?
4. **Xem graph:** `dependency:tree` để xác định đường đi và version cuối.
5. **Xem runtime classpath:** artifact nào thực sự được đưa vào launcher, WAR, container hoặc executable archive?
6. **Xác minh compatibility:** API/ABI, các bản vá, ma trận framework, test integration.
7. **Sửa đúng nguồn:** policy ở parent/BOM, khai báo trực tiếp hoặc scope/exclusion theo nhu cầu.
8. **Build sạch và kiểm chứng lại:** lưu dependency tree cùng artifact release nếu cần truy vết.

Một cách diễn đạt đơn giản của quyết định version:

~~~text
Có dependency trực tiếp với version tường minh?
   ├── Có → xem version trực tiếp trong POM hiện tại.
   └── Không
        ├── Có managed version khớp tọa độ?
        │      └── Có → dùng chính sách management phù hợp.
        └── Không → theo dependency mediation / ràng buộc version.
                       
Sau đó: xác nhận tree + test + runtime artifact.
~~~

Đây chỉ là **sơ đồ suy nghĩ nhanh**, không phải mã giả đầy đủ của Maven Resolver. Trong trường hợp version ranges, scopes, exclusions, BOM phức tạp hoặc plugin-specific resolution, kết quả phải được kiểm tra bằng công cụ Maven thực tế.

## 15. Bài tập và câu hỏi tự đánh giá

### Thực hành 1 — Tái hiện kết quả 3.12.0 và 3.14.0

1. Tạo đủ ba POM và hai class Java 17 như hướng dẫn.
2. Chạy `mvn clean install` từ root.
3. Chạy dependency tree ở `lib-a`, xác nhận nó dùng Commons Lang **3.12.0**.
4. Chạy dependency tree ở `app`, xác nhận nó dùng Commons Lang **3.14.0**.
5. Dùng `dependency:build-classpath` tạo runtime classpath, chạy `App` và xác nhận **`Hello, Maven!`**.
6. Giải thích: tại sao POM của `lib-a` không bị Maven sửa thành 3.14.0?

### Thực hành 2 — Thử các nguồn version khác nhau

1. Trên bản copy bài tập, bỏ entry managed Commons Lang trong parent và kiểm tra transitive version của `app`.
2. Khôi phục management 3.14.0, rồi thêm direct dependency Commons Lang tại `app` **không có version**. Quan sát management cung cấp version nào.
3. Thử khai báo direct version 3.12.0 tại `app`, giải thích vì sao khác trường hợp transitive được quản lý.
4. Đặt một managed version khác ở POM `app` và kiểm tra ưu tiên với parent.
5. Dùng một BOM tương ứng cho một họ thư viện khác, giải thích vì sao `import` BOM **không tự thêm tất cả JAR vào classpath**.

### Câu hỏi tự kiểm tra

- Khi nào Maven dùng nearest definition, khi nào dùng first declaration?
- `dependencyManagement` có tự tạo dependency mới không?
- Quản lý ở parent có thể ảnh hưởng đến transitive dependency của module con thế nào?
- Direct dependency có version tường minh có phải luôn giống bản do parent quản lý không?
- `dependencyManagement` có thay version của dependencies thuộc Maven plugins không?
- Vì sao cần dùng cả `help:effective-pom` và `dependency:tree`?
- Nếu version được chọn khác với version mà thư viện trung gian đã compile, còn rủi ro gì?
- Khi nào nên khai báo dependency trực tiếp dù thư viện đã đến qua transitive graph?

## 16. Kết luận

**`dependencyManagement` không phải danh sách JAR cần cài mà là chính sách quản lý phiên bản và một số thuộc tính của dependency.** Khi một dependency bắc cầu xuất hiện trong graph, managed version có thể được ưu tiên hơn kết quả nearest/first mediation. Direct dependency có version tường minh và parent/child/BOM management lại có những quy tắc ưu tiên riêng.

Trong thực hành, `lib-a` khai báo Commons Lang **3.12.0** nhưng `app` kế thừa management **3.14.0**, nên `app` có thể dùng bản 3.14.0 trong graph của mình mà không sửa POM của `lib-a`. Chốt đúng version giúp build dễ kiểm soát; **tương thích API/binary và runtime classpath vẫn phải được xác minh bằng kiểm thử**.

**Ghi nhớ:** *Kiểm tra POM hiệu lực để biết chính sách; kiểm tra dependency tree để biết phiên bản được chọn; kiểm tra artifact/runtime để biết chương trình thực sự dùng gì.*

## Tài liệu chính thức

- Maven — Introduction to the Dependency Mechanism (dependency mediation, dependency management, BOM): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven — POM Reference: https://maven.apache.org/pom.html
- Maven Dependency Plugin — `dependency:tree`: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Maven Dependency Plugin — `dependency:build-classpath`: https://maven.apache.org/plugins/maven-dependency-plugin/build-classpath-mojo.html
- Maven Help Plugin — `help:effective-pom`: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
