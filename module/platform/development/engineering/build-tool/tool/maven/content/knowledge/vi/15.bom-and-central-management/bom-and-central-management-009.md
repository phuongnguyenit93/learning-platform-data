# Giới hạn của dependencyManagement đối với phụ thuộc của Maven plugin

## 1. Tình huống: BOM đã khóa version nhưng plugin vẫn dùng bản khác

Giả sử một dự án Maven đã nhập BOM hoặc khai báo `dependencyManagement` để dùng `org.apache.commons:commons-lang3:3.14.0`. Khi xem `dependency:tree`, bạn thấy ứng dụng chọn đúng bản `3.14.0`. Thế nhưng lúc thực thi một Maven plugin, log debug lại cho thấy plugin nạp `commons-lang3:3.12.0` trong classpath riêng của nó.

Hai kết quả này **không mâu thuẫn**. Maven giải quyết **phụ thuộc của dự án** và **phụ thuộc dùng để chạy plugin** trong những ngữ cảnh khác nhau. `<project><dependencyManagement>` và BOM import **không tự áp chính sách version** sang các dependency, kể cả dependency bắc cầu, của Maven plugins trong cùng effective POM.

Đây là một giới hạn được Apache Maven nêu rõ trong tài liệu *Introduction to the Dependency Mechanism*: dependency management của dự án chi phối project dependencies, **không chi phối dependencies của plugins**. Muốn cấu hình dependency mà một plugin sử dụng, người phát triển phải dùng cách được Maven và plugin hỗ trợ, thường là `<build><plugins><plugin><dependencies>` hoặc cấu hình plugin cụ thể; đồng thời cần quản lý phiên bản **chính plugin** qua `pluginManagement`.

**Câu hỏi trung tâm:** Nếu bạn đặt `commons-lang3=3.14.0` trong BOM, plugin có nhất thiết chuyển sang dùng 3.14.0 không? **Không.** Ứng dụng và plugin có thể cùng phụ thuộc một tọa độ thư viện nhưng chọn hai phiên bản khác nhau theo hai luồng phân giải.

Mục tiêu sau bài học:

1. Phân biệt project dependency graph, plugin dependency graph và plugin execution/class realm.
2. Hiểu chính xác `dependencyManagement`/BOM ảnh hưởng tới phần nào của POM và **không ảnh hưởng** tới phần nào.
3. Phân biệt `dependencyManagement` với `pluginManagement`; tránh hiểu nhầm `pluginManagement` là BOM cho mọi dependency của plugin.
4. Biết khai báo `<plugin><dependencies>` để bổ sung/đổi dependency plugin một cách có chủ đích.
5. Dùng `dependency:tree`, `dependency:resolve-plugins`, `help:effective-pom` và Maven `-X` để kiểm tra từng lớp.
6. Chạy ví dụ Java 17 có cùng thư viện `commons-lang3` nhưng khác version trong application graph và plugin realm.
7. Đánh giá rủi ro binary compatibility, bảo mật, dependency convergence và tính tái lập của plugin overrides.
8. Chọn cách sửa đúng khi phát sinh lỗi ở plugin, không làm thay đổi classpath ứng dụng một cách vô ích.

## 2. Ba khối cấu hình thường bị nhầm lẫn

### 2.1. `<dependencies>` và `<dependencyManagement>` của dự án

Project dependencies nằm dưới:

~~~xml
<project>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Đoạn trên chỉ là **minh họa cấu trúc**, không phải POM đầy đủ. Nếu `<version>` được quản lý ở `dependencyManagement` thì dự án có thể bỏ version ở dependency trực tiếp:

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

Các tác dụng chính:

- Quản lý phiên bản/metadata cho dependencies của **project** khi chúng xuất hiện trực tiếp hoặc bắc cầu theo quy tắc Maven.
- Có thể thay đổi version mà dependency transitive được chọn, thay vì chỉ dùng nguyên tắc *nearest definition*.
- Tập trung hóa policy dependency ở parent POM hoặc BOM.
- **Không tự đưa** artifact mới vào project nếu chưa có dependency nào cần nó.
- **Không phải cấu hình global** ép mọi plugin cùng dùng version đó.

Cần phân biệt “quản lý” với “sử dụng”: chỉ khai `commons-lang3` ở `dependencyManagement` chưa khiến `commons-lang3` xuất hiện trên application classpath.

### 2.2. `<build><plugins>` và `<pluginManagement>`

Maven plugin là công cụ phục vụ build, ví dụ Maven Compiler Plugin, Surefire Plugin, Maven Antrun Plugin, Maven JAR Plugin. Plugin bản thân cũng có một artifact/version và có các dependencies để chạy goal.

Cấu hình plugin thường nằm dưới:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.0</version>
        </plugin>
    </plugins>
</build>
~~~

Để quản lý cấu hình và version **plugin** trên nhiều module, Maven hỗ trợ `pluginManagement`:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

`pluginManagement` không tự động thực thi một goal tùy ý. Nó cung cấp version/configuration/executions và cả các khai báo plugin dependencies mà plugin tương ứng có thể nhận khi plugin **được sử dụng** bởi `<plugins>`, lifecycle binding hoặc ngữ cảnh Maven thích hợp. Đừng nhầm `pluginManagement` với `dependencyManagement`, vì hai phần tử quản lý **hai nhóm cấu hình khác nhau**.

### 2.3. `<plugin><dependencies>` — dependency để plugin thực thi

Maven có đường dẫn cấu hình dành riêng cho một plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <version>3.1.0</version>
            <dependencies>
                <dependency>
                    <groupId>org.apache.commons</groupId>
                    <artifactId>commons-lang3</artifactId>
                    <version>3.12.0</version>
                </dependency>
            </dependencies>
        </plugin>
    </plugins>
</build>
~~~

**Điểm khác:** phần `<dependencies>` trong `<plugin>` này gắn artifact vào **dependency resolution của plugin**, không phải danh sách dependencies của mã nguồn ứng dụng. Version `3.12.0` được khai **rõ ràng trong plugin dependency**, độc lập với version `3.14.0` được quản lý cho project.

Có thể khai cùng thông tin trong một entry `pluginManagement` dành cho plugin đó, rồi để module sử dụng plugin. Đây là cách **quản lý cấu hình plugin cụ thể** ở parent, không phải cách biến project dependencyManagement thành plugin BOM.

## 3. Hình dung hai đồ thị phụ thuộc

~~~text
Maven project: my-app
│
├── Project dependency resolution
│   ├── <dependencyManagement> / BOM của project
│   │   └── commons-lang3 : 3.14.0
│   └── <dependencies>
│       └── commons-lang3 : 3.14.0  → compile/runtime classpath
│
└── Maven build plugins
    └── maven-antrun-plugin : 3.1.0
        ├── <plugin><dependencies>
        │   └── commons-lang3 : 3.12.0
        └── các thư viện khác theo plugin POM/resolver
            → plugin class realm khi goal chạy
~~~

Maven tạo **plugin realm/classloader** để nạp mã của plugin và những dependencies thích hợp của nó. Project compile/runtime classpath là một ngữ cảnh khác được xây dựng từ project dependencies. Vì thế:

- `dependency:tree` của project có thể cho thấy `commons-lang3:3.14.0`.
- Debug plugin realm có thể cho thấy `commons-lang3:3.12.0`.
- Hai version khác nhau không nhất thiết xung đột trong cùng một classloader.
- Việc plugin **nhìn hoặc xử lý project classpath** là một chức năng của plugin, không đồng nghĩa dependencies để **chạy chính plugin** được chọn theo project `dependencyManagement`.

**Tránh nói tuyệt đối rằng plugin và project “không thể giao tiếp”.** Nhiều plugin nhận project artifacts, mở classpath ứng dụng, chạy compiler, fork JVM hoặc khởi động tests; chúng *có thể sử dụng* project dependencies theo chức năng của mình. Phần không tự áp là **cơ chế management của project sang dependency graph nội bộ của plugin**.

## 4. BOM import chỉ quản lý dependencies của project

BOM (*Bill of Materials*) là một POM, thường có `<packaging>pom</packaging>` và danh sách `<dependencyManagement>`. Project nhập BOM bằng `type=pom` và `scope=import` **bên trong `dependencyManagement`**.

Ví dụ cấu trúc (artifact `com.example:team-bom:1.0.0` chỉ là minh họa; không được giả định tồn tại trên Maven Central):

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>team-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Nếu BOM quản lý `org.apache.commons:commons-lang3:3.14.0` thì `commons-lang3` có thể được chọn 3.14.0 cho project, theo ưu tiên và các khai báo khác. Nhưng BOM **không tự đưa `commons-lang3:3.14.0` vào plugin class realm**.

Điểm cần nắm:

1. `import` scope dành cho dependency có `type=pom` trong **project dependencyManagement**; không phải “scope import cho plugin dependency”.
2. Các mục do BOM nhập trở thành phần của danh sách managed project dependencies.
3. Một BOM chỉ có `dependencyManagement` **không tương đương với một parent POM** có thể cung cấp `pluginManagement`. Maven không tự nhập `<build><pluginManagement>` của một BOM chỉ vì bạn dùng BOM import.
4. Khi tổ chức muốn quản lý **cả** project dependency policy **và** plugin policy, thường dùng **BOM cho project libraries** và **parent POM chứa pluginManagement** (hoặc một cấu hình plugin được kiểm soát riêng) cho build plugins.
5. Dependency version của plugin có thể sử dụng một property chung **khi được khai trực tiếp** trong `<plugin><dependencies>`, nhưng đó là **interpolation property** chứ không phải tự động áp `dependencyManagement`.

Ví dụ dùng chung property một cách có chủ đích:

~~~xml
<properties>
    <commons.lang3.version>3.14.0</commons.lang3.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>${commons.lang3.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <version>3.1.0</version>
            <dependencies>
                <dependency>
                    <groupId>org.apache.commons</groupId>
                    <artifactId>commons-lang3</artifactId>
                    <version>${commons.lang3.version}</version>
                </dependency>
            </dependencies>
        </plugin>
    </plugins>
</build>
~~~

Đây là **đoạn cấu hình của `<project>`**, không phải POM hoàn chỉnh. Hai chỗ cùng version vì **người viết đã khai hai chỗ**, không vì Maven tự nối hai dependency graphs. Hơn nữa, nâng version cho cả plugin bằng property chỉ an toàn khi plugin tương thích với bản library đó.

## 5. Bảng phân biệt để chọn chỗ sửa

| Thành phần | Đối tượng | Có tác động tới plugin transitive dependencies? | Cách kiểm tra |
| --- | --- | --- | --- |
| `project/dependencies` | Dependencies của project | **Không trực tiếp** | `dependency:tree` |
| `project/dependencyManagement` | Quản lý project dependencies | **Không** tự chi phối plugin transitive graph | `dependency:tree`, `effective-pom` |
| BOM import vào `dependencyManagement` | Danh sách managed dependencies của project | **Không** | Effective POM và project tree |
| `build/plugins/plugin/version` | Version của plugin | Chọn một bản plugin, **có thể đổi chính graph dependencies của plugin** | Build log, plugin realm, `help:effective-pom` |
| `build/pluginManagement` | Cấu hình/version/executions/dependencies cho plugin khi được dùng | Có thể cung cấp **plugin-specific** dependency declarations | Effective POM, log goal |
| `build/plugins/plugin/dependencies` | Dependencies của **chính plugin** | **Có**, trong phạm vi plugin và quy tắc resolver | `-X`, `dependency:resolve-plugins` |
| Plugin-specific config, ví dụ annotation processor path | Đường dẫn công cụ do plugin kiểm soát | Phụ thuộc semantics của plugin, **không giống mặc định plugin realm** | Tài liệu plugin và debug log |

**Quy tắc ghi nhớ:** hỏi “thư viện này được mã ứng dụng sử dụng, hay plugin cần để chạy chính nó?” trước khi chọn `dependencyManagement` hay `plugin/dependencies`.

## 6. Một lỗi thường gặp: tưởng dependencyManagement là global override

Giả sử POM có:

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

Sau đó trong log `mvn -X` vẫn có một artifact `commons-lang3` với version khác dưới class realm của plugin. **Không nên kết luận Maven đã bỏ qua BOM hoặc đang bị hỏng cache.**

Thay vì cập nhật POM bằng cách thêm thêm một phiên bản vào `dependencyManagement`, xác định:

1. Log thuộc **project dependency graph** hay **plugin class realm**?
2. Plugin cụ thể là gì (groupId/artifactId/version/goal)?
3. Version được chọn của plugin có bị quản lý bởi parent `pluginManagement` không?
4. Plugin có khai `<plugin><dependencies>` riêng hoặc tự phụ thuộc thư viện đó transitively không?
5. Plugin có tài liệu hỗ trợ phiên bản thư viện/công cụ đó không?
6. Nếu cần đổi, phải đổi plugin version, thêm/cập nhật plugin-specific dependency hoặc dùng tham số plugin được hỗ trợ.

**Tác động gián tiếp không bị phủ nhận:** khi project `dependencyManagement` đổi project classpath, một plugin như Compiler, Surefire, JAR hoặc Assembly có thể **xử lý đầu vào khác đi** vì project artifacts thay đổi. Nhưng việc đó khác với việc version của thư viện **nạp trong plugin realm** đã bị quản lý.

## 7. Thực hành Java 17: cùng commons-lang3, hai version tách biệt

Ví dụ này cố ý đặt **`commons-lang3:3.14.0` trong project** nhưng **`commons-lang3:3.12.0` trong dependency của Maven Antrun Plugin**. Người học có thể chứng minh project tree không bị plugin dependency chi phối, và plugin realm được cấu hình riêng.

Điều kiện:

- JDK 17 trở lên.
- Maven 3.9.x hoặc phiên bản Maven tương thích với plugins minh họa; nên kiểm tra bằng `mvn -version`.
- Kết nối Maven Central hoặc repository/mirror của tổ chức ở lần tải artifact/plugin đầu.
- Thư mục học tập không cần Spring Boot, JUnit, Docker hay database.

Tên các phiên bản dùng trong lab: Maven Compiler Plugin `3.14.0`, Maven Antrun Plugin `3.1.0`, Maven Help Plugin `3.5.2`, Maven Dependency Plugin `3.11.0`, Exec Maven Plugin `3.5.1`. Tất cả đều được chỉ định rõ khi sử dụng. Các bản `commons-lang3:3.12.0` và `3.14.0` là hai artifact thực tế được phát hành.

Cấu trúc:

~~~text
plugin-dependency-lab/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── example/
                    └── PluginIsolationApp.java
~~~

### 7.1. Toàn bộ pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>plugin-dependency-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <commons.project.version>3.14.0</commons.project.version>
    </properties>

    <!-- Version này áp cho project dependency, KHÔNG tự áp cho plugin -->
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>${commons.project.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <!-- Plugin dùng để minh họa class realm riêng -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>

                <!-- Dependency dành cho plugin, version explicit -->
                <dependencies>
                    <dependency>
                        <groupId>org.apache.commons</groupId>
                        <artifactId>commons-lang3</artifactId>
                        <version>3.12.0</version>
                    </dependency>
                </dependencies>

                <executions>
                    <execution>
                        <id>announce-plugin-realm</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <echo message="ANTRUN GOAL EXECUTED"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>

            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Lưu ý quan trọng về thiết kế thử nghiệm:**

- `<dependencyManagement>` đặt `commons-lang3` của **project** thành `3.14.0`.
- Trong `<project><dependencies>`, `commons-lang3` không có version; Maven lấy version đã được quản lý.
- Maven Antrun Plugin có **plugin dependency riêng** `commons-lang3:3.12.0` được khai báo chính xác bên dưới `<plugin><dependencies>`.
- `antrun:run` được bind vào `validate` để bắt buộc plugin được giải quyết/chạy trong mỗi lệnh build tới phase `validate`.
- Antrun chỉ in thông báo, **không trực tiếp gọi API commons-lang3**; bằng chứng về version plugin dependency sẽ đến từ **debug plugin realm hoặc báo cáo plugin resolution**, không phải dòng echo.
- Các plugin khác trong POM không bị áp `commons-lang3:3.12.0` bởi block của Antrun; khai báo plugin dependencies có **phạm vi plugin tương ứng**.

### 7.2. Java class có thể chạy thật

Tạo `src/main/java/dev/example/PluginIsolationApp.java`:

~~~java
package dev.example;

import org.apache.commons.lang3.StringUtils;

public final class PluginIsolationApp {
    private PluginIsolationApp() {
    }

    public static void main(String[] args) {
        System.out.println(StringUtils.upperCase("project realm ok"));
    }
}
~~~

Ứng dụng **dùng project classpath** và khai trực tiếp API `StringUtils` của `commons-lang3`. Phương thức `upperCase(String)` tồn tại ở những version mẫu. Kết quả không thể hiện số version vì cả hai bản đều có API đó; version nào được dùng phải được xác nhận bằng dependency tree và plugin debug.

### 7.3. Chạy build và ứng dụng

Tại thư mục `plugin-dependency-lab`:

~~~bash
java -version
mvn -version
mvn -B -ntp clean package
mvn -B -ntp org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=dev.example.PluginIsolationApp
~~~

`clean package` chạy lần lượt các phase; goal Antrun ở `validate` in thông điệp `ANTRUN GOAL EXECUTED`, sau đó Maven compile ứng dụng và đóng gói JAR. Lệnh `exec:java` sử dụng classpath phù hợp của project để chạy main class đã biên dịch.

**Dòng stdout do chương trình Java in ra:**

~~~text
PROJECT REALM OK
~~~

Lưu ý Maven còn in các dòng log khác. Thông điệp Ant `ANTRUN GOAL EXECUTED` cũng có thể được ghi với tiền tố `[echo]`; không coi hai thông điệp đó là toàn bộ stdout của các lệnh Maven.

### 7.4. Xem project dependency tree

Chạy:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Trong tree của project, tìm node tương đương:

~~~text
org.apache.commons:commons-lang3:jar:3.14.0:compile
~~~

Đây là **dòng rút gọn**, log thực tế có root artifact, đầu dòng `+-` và tiền tố `[INFO]` khác nhau. Kết quả quan trọng là **3.14.0** trong project dependency tree, mặc dù Antrun đã khai dependency plugin version **3.12.0**.

Nếu bạn chỉ dùng `dependency:tree` để tìm `commons-lang3:3.12.0` của plugin, thông thường **sẽ không thấy**: goal này hiển thị **project dependency graph**, không phải mọi thư viện nạp để chạy Maven plugins.

### 7.5. Kiểm tra dependency mà plugin sử dụng

Chạy Antrun dưới chế độ Maven debug:

~~~bash
mvn -B -ntp -X validate
~~~

Tìm các dòng được log ở mức debug, chẳng hạn:

~~~text
Created new class realm plugin>org.apache.maven.plugins:maven-antrun-plugin:3.1.0
Populating class realm plugin>org.apache.maven.plugins:maven-antrun-plugin:3.1.0
Included: org.apache.commons:commons-lang3:jar:3.12.0
~~~

**Đây là các mẫu nhận diện nội dung log, không phải stdout nguyên văn được đảm bảo 100%.** Tên class realm, thứ tự log, prefix `[DEBUG]` và dạng tọa độ có thể thay đổi theo Maven core/plugin version. Nếu không thấy một dòng đúng hệt, tìm `maven-antrun-plugin`, `commons-lang3` và `3.12.0` trong log `-X`, rồi xác nhận chúng nằm ở **plugin realm** thay vì một đoạn mô tả project dependencies.

Cần xác minh cả hai sự thật:

1. `dependency:tree` cho biết app dùng `commons-lang3:3.14.0`.
2. Plugin realm của `maven-antrun-plugin` có thể chứa `commons-lang3:3.12.0` vì POM đã khai plugin-specific dependency.

Đừng kết luận lỗi classloader chỉ vì có hai version trong tổng log của Maven. Hai version có thể thuộc hai phạm vi classloader khác nhau.

### 7.6. Dùng dependency:resolve-plugins để tìm plugin artifacts

Maven Dependency Plugin có goal **`dependency:resolve-plugins`** dành cho plugins và dependencies của chúng:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:resolve-plugins
~~~

Theo mô tả chính thức, goal này phân giải plugins được project dùng và báo artifact/dependency của chúng; mặc định `excludeTransitive=false`. Output phụ thuộc danh sách plugin thực tế, version và các artifact đã được phân giải.

**Giới hạn:** `resolve-plugins` không phải là `dependency:tree` với chú thích `omitted for conflict` cho một plugin realm cụ thể. Nếu cần xác định **chính xác thư viện nạp khi chạy một goal**, `-X` cùng goal đó và plugin execution log thường cung cấp ngữ cảnh tốt hơn. Đừng suy chỉ từ một danh sách download/cache.

### 7.7. Dùng effective POM để tách hai khai báo

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom.xml
~~~

Trong file `effective-pom.xml`, tìm:

- `/project/dependencyManagement/dependencies`: `commons-lang3` được quản lý version 3.14.0.
- `/project/dependencies`: dependency trực tiếp của project.
- `/project/build/plugins/plugin[artifactId='maven-antrun-plugin']/dependencies`: version 3.12.0 dành riêng cho plugin.
- `/project/build/plugins/plugin[artifactId='maven-antrun-plugin']/executions`: goal `antrun:run` ở phase `validate`.

Đường dẫn ở đây là **mô tả vị trí XML**, không phải XPath hoàn chỉnh để copy vào parser mà không xử lý namespace POM.

`-Dverbose=true` ở Help Plugin hỗ trợ chú thích nguồn của các phần tử khi phiên bản plugin hỗ trợ. Effective POM thể hiện **cấu hình model**; nó chưa đủ để khẳng định mọi transitive plugin dependency đã được chọn như thế nào. Cần đối chiếu runtime/debug của plugin.

## 8. Thí nghiệm thay một phía và dự đoán kết quả

Sau khi chạy lab nguyên bản, thực hiện hai thay đổi **tách biệt** (mỗi lần sửa POM rồi chạy lại, sau đó hoàn nguyên).

### 8.1. Chỉ đổi version của project dependencyManagement

Trong `<properties>`:

~~~xml
<commons.project.version>3.13.0</commons.project.version>
~~~

Giữ **nguyên** plugin dependency `commons-lang3:3.12.0`. Bản `3.13.0` có tồn tại trên Maven Central.

Dự đoán:

- `dependency:tree` của project chuyển sang `commons-lang3:3.13.0`.
- Plugin-specific declaration cho Antrun vẫn là `commons-lang3:3.12.0` và sẽ được plugin resolution xử lý độc lập, trừ khi có yếu tố khác trong graph plugin ảnh hưởng.
- Ứng dụng Java vẫn in `PROJECT REALM OK` do API minh họa không đổi.
- Sửa `dependencyManagement` không tự sửa version trong `<plugin><dependencies>`.

Nếu bạn muốn xem bản 3.14.0 trở lại, đổi property về `3.14.0`.

### 8.2. Chỉ đổi dependency của plugin

Giữ project dependencyManagement là `3.14.0`, nhưng đổi dưới `maven-antrun-plugin`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
~~~

Dự đoán:

- Project `dependency:tree` vẫn chọn version `3.14.0`.
- Plugin Antrun sẽ được yêu cầu dùng `commons-lang3:3.14.0` theo plugin dependency declaration mới; debug/plugin resolution cần kiểm chứng version nạp thực tế.
- Các plugin khác không tự nhận bản `3.14.0` qua thay đổi này.

**Kết luận:** một version xuất hiện ở hai nơi là **hai quyết định cấu hình**. Giữ chúng giống nhau có thể là chính sách hợp lý khi plugin cần API tương ứng, nhưng Maven không tự đồng bộ từ project `dependencyManagement`.

### 8.3. Chỉ đổi version của Maven plugin

Giả sử tổ chức có bản plugin mới đã thay một dependency transitive để khắc phục lỗi. Nâng `<version>` của **chính plugin** có thể giải quyết vấn đề mà **không cần override** thư viện nội bộ.

Thay đổi này không được thực hiện mù trong lab: phải xem release notes, compatibility của plugin với Maven core/JDK, behavior của goals và các dependencies được plugin POM mang theo. Tăng plugin version có thể thay graph plugin và cả behavior build, chứ không chỉ đổi một JAR.

## 9. Quản lý plugin ở parent POM qua pluginManagement

Trong hệ thống đa module, một parent POM thường quản lý version của các build plugins:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <dependencies>
                    <dependency>
                        <groupId>org.apache.commons</groupId>
                        <artifactId>commons-lang3</artifactId>
                        <version>3.12.0</version>
                    </dependency>
                </dependencies>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Đây là **fragment của parent POM**. Module cần sử dụng plugin thì có thể khai dưới `build/plugins`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <!-- Thêm execution/goal phù hợp ở module hoặc parent -->
        </plugin>
    </plugins>
</build>
~~~

**Sự phân công:**

- Parent `dependencyManagement` quản lý dependencies của project modules.
- Parent `pluginManagement` quản lý khai báo và thông số các plugins.
- Một entry plugin trong `pluginManagement` có thể cung cấp `<dependencies>` **cho plugin đó** khi được sử dụng.
- `pluginManagement` **không phải một danh sách quản lý version tự động cho mọi transitive library của mọi plugin**.
- Nếu plugin không được dùng bởi execution/binding/direct goal thích hợp, một khai báo quản lý đơn thuần không bảo đảm plugin goal sẽ chạy.

Đây là cách giữ chính sách build nhất quán cho nhiều modules mà không trông chờ BOM import điều khiển plugin class realm.

### 9.1. Không nhầm parent POM với BOM import

Một parent POM có thể chứa đồng thời `dependencyManagement` và `pluginManagement`. Khi một module khai `<parent>`, Maven có thể kế thừa cả hai theo quy tắc inheritance/merge.

Nhưng khi một module chỉ khai **import BOM** bằng `type=pom`, `scope=import` ở `dependencyManagement`, Maven chỉ nhập danh sách **managed project dependencies** của BOM, **không nhập toàn bộ cấu hình build/pluginManagement** như khi kế thừa parent. Vì vậy đừng mô tả BOM là “quản lý mọi thư viện, plugin và compiler của công ty” nếu BOM chỉ chứa dependencies.

## 10. Một số trường hợp dễ gây kết luận sai

### 10.1. Maven Compiler Plugin dùng project classpath

Compiler Plugin nạp mã của chính plugin và điều khiển compiler. Còn compiler biên dịch source code lại dùng project classpath và các compiler flags. Nếu project `dependencyManagement` thay version của một thư viện ứng dụng, Compiler Plugin có thể biên dịch với thư viện mới **qua classpath đầu vào**, dù các dependencies để **chạy Compiler Plugin** không bị BOM quản lý.

Không được nói “dependencyManagement không liên quan gì tới plugin” một cách tuyệt đối: nó **có thể đổi dữ liệu đầu vào mà plugin làm việc trên**, chỉ không tự quản lý plugin realm.

### 10.2. Surefire, Failsafe và test runtime

Surefire/Failsafe có plugin dependencies, providers, test classpath và có thể fork JVM để chạy tests. Version JUnit, Mockito, SLF4J trong `<project><dependencies>` hoặc `dependencyManagement` ảnh hưởng **test classpath**. Nó **không tự nâng** những thư viện nội bộ mà Surefire/Failsafe plugin dùng để triển khai goal.

Khi lỗi xảy ra ở **test code**, kiểm tra project test graph; khi lỗi xảy ra ở **plugin provider/goal/classloader**, kiểm tra plugin version, plugin realm, provider/version compatibility. Hai loại lỗi có thể có thông điệp gần giống nhau nhưng cách chữa khác hẳn.

### 10.3. Annotation processors có đường cấu hình riêng

Compiler Plugin có những tham số đặc biệt liên quan đến annotation processors, ví dụ cấu hình `annotationProcessorPaths` trong các phiên bản plugin hỗ trợ. Đây là **classpath/đường phân giải phục vụ trình biên dịch** do Compiler Plugin quy định, không nhất thiết là plugin `<dependencies>` thông thường.

Một số phiên bản Compiler Plugin còn có tham số liên quan việc sử dụng dependency management cho dependencies bắc cầu của processor path. **Phải tra đúng tài liệu của phiên bản Compiler Plugin đang dùng**; không áp quy tắc “BOM điều khiển mọi annotation processor” hoặc “BOM không thể ảnh hưởng bất kỳ processor nào” một cách tuyệt đối.

**Bài học chung:** xác định dependency thuộc project graph, plugin realm, provider/tool path hay classpath khác do plugin cấu hình. Mỗi ngữ cảnh có quy tắc resolution riêng.

### 10.4. Plugin có dependency đã đóng gói/shaded

Một plugin có thể đã *shade* hoặc nhúng thư viện vào chính JAR của plugin. Nếu vậy, thêm một version mới dưới `<plugin><dependencies>` **không chắc thay thế mã đã đóng gói sẵn**. Việc nâng plugin hoặc nhận bản vá từ tác giả có thể là cách đúng hơn.

Không cố sửa lỗ hổng bảo mật bằng cách thêm một JAR khác version rồi tuyên bố tất cả class của plugin đã được thay. Xác minh chính xác artifact, bytecode, class loading và thử plugin goal thực tế.

### 10.5. Plugin transitive dependencies cũng có version conflict riêng

Các dependencies mà plugin sử dụng có thể tiếp tục kéo thêm nhiều thư viện transitively và gặp conflict trong **plugin graph**. Một entry trong project `dependencyManagement` không làm Maven hòa giải các conflict đó theo chính sách project.

Khai thêm `<plugin><dependencies>` có thể bổ sung hoặc yêu cầu phiên bản khác và làm thay đổi graph plugin, nhưng không bảo đảm mọi override đều an toàn. Thư viện plugin cũ có thể gọi API đã bị xóa ở version mới, gây `NoSuchMethodError` hoặc `ClassNotFoundException` trong Maven build, ngay cả khi ứng dụng của bạn vẫn compile thành công.

### 10.6. Dependencies của plugin không phải dependencies của ứng dụng

Nếu một plugin được khai dùng `commons-lang3`, điều đó **không tự thêm `commons-lang3` vào runtime classpath của ứng dụng**. Muốn source code Java ứng dụng import `org.apache.commons.lang3.StringUtils`, hãy khai project dependency tương ứng ở `<project><dependencies>`.

Ngược lại, một thư viện chỉ có trong project dependencies không nhất thiết xuất hiện trong class realm của plugin. Không xem việc “Maven đã download file này” là chứng cứ nó đã được chọn trong đúng classloader.

## 11. Quy trình điều tra một lỗi ở plugin dependency

**Bước 1 — đọc loại lỗi.**

- `Cannot resolve plugin` hoặc `PluginResolutionException`: có thể là thiếu plugin/artifact, repository, credentials hoặc plugin dependency.
- `NoClassDefFoundError`, `ClassNotFoundException`, `NoSuchMethodError` khi đang chạy plugin goal: có thể là mismatch trong plugin realm, plugin provider hoặc runtime path.
- Lỗi biên dịch Java như `package ... does not exist`: thường liên quan project compile classpath; không vội sửa plugin dependencies.
- `Tests run: 0` hoặc test runtime lỗi: xem Failsafe/Surefire discovery, provider, test classpath và cấu hình plugin.

**Bước 2 — ghi lại ngữ cảnh thực tế.**

~~~bash
mvn -version
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom.xml
~~~

Đặc biệt xem Maven Wrapper, JDK đang chạy Maven, profile đang active, parent/pluginManagement và version plugin. Một plugin version khác có thể có transitive graph khác.

**Bước 3 — xác nhận project graph.**

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Mục tiêu: xác định phiên bản ứng dụng đang dùng. **Không dùng kết quả này làm bằng chứng đầy đủ cho plugin realm.**

**Bước 4 — xác nhận plugin artifacts và dependency.**

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:resolve-plugins
~~~

Lệnh giúp xác định plugin dependencies. Nếu cần tìm classloader đúng goal, chạy **chính goal bị lỗi** với `-X` và nhìn phần plugin realm. Debug output có thể dài và chứa cấu hình môi trường, repository URLs hoặc dữ liệu nhạy cảm; phải lọc trước khi gửi ra ngoài.

**Bước 5 — xem plugin POM và tài liệu tương thích.**

Đọc version plugin được chọn, POM artifact của plugin, dependency graph của nó và release notes. Nếu gặp `NoSuchMethodError` trong plugin, xác định class/method thuộc artifact nào và version nào đang được plugin realm nạp. **Đừng cho rằng version trong project BOM là version plugin đã load.**

**Bước 6 — chọn cách sửa ít rủi ro.**

Ưu tiên thứ tự cân nhắc:

1. Nâng **chính plugin** lên version được dự án hỗ trợ và đã chứa bản vá/compatible dependency.
2. Nếu tài liệu plugin cho phép, dùng plugin-specific configuration cho công cụ/provider/processor path.
3. Nếu cần thiết và an toàn, khai dependency cụ thể dưới `<plugin><dependencies>` với version đã kiểm thử.
4. Tập trung cấu hình nhiều module bằng parent `pluginManagement`, không dùng project BOM như công cụ ép plugin library.
5. Kiểm tra dependency của project bằng `dependencyManagement`/BOM **khi lỗi thực sự nằm ở project graph**.

**Bước 7 — xác minh lại.**

Chạy goal plugin hoặc lifecycle build có liên quan và `mvn clean verify` khi phù hợp. Kiểm tra plugin realm/debug, project tree và test runtime. Một build xanh ở `validate` không chứng minh ứng dụng chạy đúng nếu vấn đề là runtime API compatibility; cần test theo chính đường bị lỗi.

## 12. Những sai lầm thường gặp và hướng sửa

| Nhận định hoặc thao tác sai | Cách hiểu/hướng sửa |
| --- | --- |
| “BOM nhập vào dependencyManagement sẽ ép mọi plugin dùng đúng version đó.” | Sai; BOM quản lý project dependencies. Xem plugin realm, version plugin và plugin-specific dependencies. |
| “Đặt version compiler plugin ở dependencyManagement.” | Compiler Plugin là **plugin**; pin version trong `build/plugins` hoặc parent `pluginManagement`. |
| “pluginManagement tự chạy mọi goal đã khai.” | Không; plugin cần được sử dụng/bind phù hợp. |
| “Đặt commons-lang3 ở plugin dependencies giúp App.java import được StringUtils.” | Sai; mã ứng dụng cần project dependency. |
| “Maven dependency:tree liệt kê toàn bộ plugin transitive graph.” | Sai; tree thông thường dành cho project dependencies. Dùng `resolve-plugins`/` -X `. |
| “Một plugin tải JAR 3.12.0 có nghĩa app dùng 3.12.0.” | Không; cần xem classpath của project hoặc runtime thích hợp. |
| “Hai version khác nhau trong log luôn gây conflict.” | Không nhất thiết; có thể thuộc class realms khác nhau. |
| “Thay version project dependencyManagement sẽ sửa NoSuchMethodError trong plugin.” | Chưa chắc; thường cần sửa plugin/version của chính plugin. |
| “Override plugin dependency mới nhất luôn tốt hơn.” | Không; plugin có thể chưa tương thích hoặc đã shade thư viện cũ. |
| “Chỉ cần đổi plugin dependency version ở parent BOM import.” | BOM import không mang theo pluginManagement; cần parent POM hoặc plugin declaration riêng. |
| “Version annotation processor luôn do dependencyManagement quản lý.” | Tùy Compiler Plugin và cấu hình processor path; đọc đúng documentation plugin. |
| “Maven -X luôn an toàn để gửi qua ticket công khai.” | Debug có thể lộ metadata/môi trường hoặc secret; lọc/ẩn thông tin nhạy cảm. |

## 13. Checklist thiết kế build Maven có BOM và plugin

- [ ] Phân biệt hai câu hỏi: version **ứng dụng sử dụng** và version **plugin dùng để chạy goal**.
- [ ] Nhập BOM dưới `project/dependencyManagement` với `type=pom` và `scope=import`; không giả định nó nhập plugin policy.
- [ ] Giữ `pluginManagement` ở parent khi muốn quản lý version/configuration plugins xuyên modules.
- [ ] Pin version của các Maven plugins quan trọng.
- [ ] Không dùng project `dependencyManagement` để kỳ vọng sửa plugin transitive dependencies.
- [ ] Nếu thêm `plugin/dependencies`, chọn version tương thích theo tài liệu plugin.
- [ ] Đã kiểm tra `dependency:tree` cho project graph.
- [ ] Đã kiểm tra `dependency:resolve-plugins` và/hoặc `-X` cho plugin artifacts/realm.
- [ ] Đã dùng `help:effective-pom` xác nhận vị trí của dependencyManagement và plugin dependencies.
- [ ] Khi sửa lỗi, đã xác định classpath thuộc project, plugin, provider hay annotation processor.
- [ ] Không nâng một thư viện trong plugin realm để vá lỗ hổng khi plugin đã shade mã cần vá.
- [ ] Đã chạy goal plugin bị ảnh hưởng và toàn bộ build/test cần thiết.
- [ ] Khi thấy version khác nhau giữa local và CI, kiểm tra Maven core, JDK, parent, pluginManagement và repository.
- [ ] Không commit log debug hoặc effective settings chứa thông tin nhạy cảm.
- [ ] Ghi trong PR nguyên nhân, phiên bản trước/sau, scope sửa và kết quả thử.

## 14. Bài tập tự kiểm tra

**Bài 1 — xác định phạm vi.** Trong `<dependencyManagement>` của project có `commons-lang3:3.14.0`; trong plugin `maven-antrun-plugin` có dependency `commons-lang3:3.12.0`. `dependency:tree` của project cần cho thấy bản nào nếu project có dependency không khai version?

**Đáp án:** `3.14.0`, vì project dependencyManagement quản lý version của project dependency; `3.12.0` ở plugin realm không được tự thêm vào project graph.

**Bài 2 — BOM.** Một team-bom nhập vào `dependencyManagement` quản lý JUnit, SLF4J và Jackson. Maven Surefire Plugin và Maven Compiler Plugin có tự nâng dependencies nội bộ theo BOM không?

**Đáp án:** không. BOM có thể điều khiển JUnit/SLF4J/Jackson trên project test/runtime classpath mà plugins sử dụng làm **đầu vào**; nó không tự quản lý dependencies nội bộ để chạy plugin goal.

**Bài 3 — plugin version.** Nên đặt `maven-compiler-plugin:3.14.0` trong `dependencyManagement` hay `pluginManagement`?

**Đáp án:** `pluginManagement` (hoặc `build/plugins` của module), vì đó là version của một plugin, không phải dependency thông thường của project.

**Bài 4 — parent và BOM.** Project chỉ nhập `team-bom` với `scope=import`. Nó có tự kế thừa `build/pluginManagement` từ POM của BOM không?

**Đáp án:** không. Import BOM nhập managed project dependencies; kế thừa parent `<parent>` mới là một cơ chế khác có thể mang theo pluginManagement.

**Bài 5 — thí nghiệm.** Đổi `commons.project.version` trong lab từ `3.14.0` thành `3.13.0` mà giữ plugin dependency `3.12.0`. Dự đoán `dependency:tree` và plugin `-X`.

**Đáp án:** project tree chọn 3.13.0; plugin declaration vẫn yêu cầu 3.12.0, và cần xem plugin realm để xác nhận version thực sự nạp.

**Bài 6 — lỗi classloader.** Một plugin lỗi `NoSuchMethodError` từ thư viện mà nó cần. Thêm version mới ở project `dependencyManagement` đã đủ chứng minh lỗi được khắc phục chưa?

**Đáp án:** chưa. Cần xác định lỗi thuộc classrealm nào, kiểm tra plugin version/dependency của chính plugin, thử sửa có hỗ trợ và chạy lại plugin goal.

**Bài 7 — dependencyManagement có ảnh hưởng gián tiếp tới plugin không?**

**Đáp án:** có thể ảnh hưởng **dữ liệu mà plugin thao tác** (ví dụ project/test classpath), nhưng không tự thay version các thư viện plugin nạp trong class realm của nó.

**Bài 8 — gợi ý thiết kế parent POM.** Team muốn quản lý cả version dependencies ứng dụng và version Maven plugins. Nên tổ chức thế nào?

**Đáp án:** project dependency versions trong BOM/parent `dependencyManagement`; Maven plugin versions/configuration trong parent `pluginManagement`; plugin-specific dependencies chỉ khai ở từng plugin khi thực sự cần và đã kiểm tra compatibility.

## 15. Tổng kết

`dependencyManagement` là công cụ quan trọng để ổn định **dependency graph của dự án**, kể cả khi dùng BOM import. Nhưng nó có **ranh giới rõ ràng**: các thư viện để chạy **Maven plugin** và các dependency bắc cầu của plugin không tự bị quản lý bởi project dependencyManagement.

Hãy xem:

~~~text
project dependency policy  → dependencyManagement / BOM
plugin version & setup     → pluginManagement / build/plugins
plugin-specific libraries  → plugin/dependencies (hoặc cấu hình plugin phù hợp)
chứng cứ project graph     → dependency:tree
chứng cứ plugin resolution → dependency:resolve-plugins / -X plugin realm
model sau khi ghép          → help:effective-pom
~~~

Khi sửa vấn đề version, hãy tìm **đúng lớp** trước; không sửa BOM nếu lỗi thực chất nằm ở plugin realm, và không override plugin library nếu lỗi là project runtime classpath.

## 16. Tài liệu tham khảo chính thức

1. [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): dependency management, transitive dependencies, BOM import; xác nhận rõ project dependency management không chi phối plugin dependencies.
2. [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): cấu hình plugin, version, `<dependencies>` dưới plugin, `pluginManagement`.
3. [Apache Maven — POM Reference](https://maven.apache.org/pom.html): cấu trúc `dependencies`, `dependencyManagement`, `build/plugins` và `pluginManagement`.
4. [Maven Dependency Plugin — dependency:resolve-plugins](https://maven.apache.org/plugins/maven-dependency-plugin/resolve-plugins-mojo.html): giải quyết plugins và dependencies của chúng.
5. [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): xem resolved **project dependency graph**.
6. [Maven Help Plugin — help:effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): xem POM sau inheritance/profile/management.
7. [Maven Help Plugin — help:describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html): xem tham số/goal của plugin khi điều tra hành vi thực tế.
