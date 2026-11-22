# exclusions và phạm vi loại trừ theo từng đường phụ thuộc trong Maven

## 1. Mục tiêu: hiểu rõ “loại trừ trên một đường đi”, không phải “cấm toàn bộ”

Trong Maven, khi project `app` khai báo dependency `library-a`, Maven thường tự phân giải cả dependency mà `library-a` cần. Đó là **transitive dependency** (phụ thuộc bắc cầu). Vì một artifact có thể được kéo vào từ nhiều thư viện khác nhau, đôi khi classpath xuất hiện một thư viện không mong muốn: bản cũ, thành phần có lỗ hổng, logger gây trùng binding hoặc một module không dùng tới.

`<exclusions>` cho phép **ngăn một artifact đi vào project qua một dependency cụ thể**. Nó được đặt **bên trong `<dependency>` tạo ra nhánh không mong muốn**, với mỗi `<exclusion>` chỉ định `groupId` và `artifactId` của artifact cần loại trừ.

Ý nghĩa quan trọng nhất:

> **Exclusion áp dụng cho toàn bộ cây phụ thuộc đi qua cạnh `<dependency>` chứa exclusion; nó không cấm artifact đó xuất hiện qua một cạnh/đường phụ thuộc khác.**

Ví dụ sơ đồ dưới đây dùng tên module tượng trưng:

```text
app
├── library-a
│   └── common-lib       <-- sẽ bị loại qua nhánh library-a
│       └── common-util
└── library-b
    └── common-lib       <-- vẫn có thể xuất hiện qua library-b
        └── common-util
```

Nếu trong `app/pom.xml` bạn thêm exclusion của `common-lib` **vào dependency `library-a`**, Maven không chọn đường `app → library-a → common-lib`. Nhưng đường `app → library-b → common-lib` không bị cấm. Bản `common-lib` được phân giải từ đường còn lại và phần phụ thuộc của nó có thể vẫn xuất hiện trong classpath.

Maven **không có một phần tử `<exclusions>` đặt tùy ý ở root `<project>` để cấm một artifact toàn cục**. Nếu muốn chính sách “artifact X không bao giờ được xuất hiện”, phải kiểm tra **tất cả các đường hợp lệ** và thường dùng Maven Enforcer `bannedDependencies` để **báo lỗi build** nếu artifact bị cấm còn hiện diện.

Bài này hướng dẫn cách đọc dependency graph, viết đúng XML, nhận biết giới hạn theo đường đi, xem tree, kiểm tra tác dụng qua một dự án Java 17 nhiều module và xử lý các sai lầm thường gặp.

## 2. Bốn khái niệm dễ nhầm

### 2.1. Direct dependency và transitive dependency

Một dependency được khai báo trực tiếp trong `<dependencies>` của project là **direct dependency**.

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>library-a</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
```

Nếu POM của `library-a` khai báo `common-lib`, `common-lib` là transitive dependency của project. Maven đọc metadata/POM để xây dependency graph và chọn các artifact phù hợp theo scope, optional, exclusions, dependency management và quy tắc giải quyết version.

### 2.2. Dependency graph là đồ thị, dù hiển thị thường là một cây

Khi nhiều dependency kéo vào cùng một artifact, graph có thể chứa nhiều đường:

```text
app -> library-a -> common-lib
app -> library-b -> common-lib
app -> library-c -> other-lib -> common-lib
```

Công cụ `dependency:tree` biểu diễn **kết quả phân giải và mediation** thành cây dễ đọc; một artifact được gộp/loại đường trùng nên **không nhất thiết mọi đường trong graph khái niệm đều xuất hiện như các nút lặp lại ở output mặc định**. Không nên kết luận rằng “không thấy nhánh thứ hai nghĩa là nó không tồn tại trong mọi điều kiện”.

Điều quan trọng không phải tên artifact được in bao nhiêu lần, mà là **liệu còn một đường đi hợp lệ tới artifact ấy sau khi áp dụng exclusion và các quy tắc phân giải khác hay không**.

### 2.3. “Scope” có hai ý nghĩa cần tách biệt

- **`<scope>compile</scope>` / `runtime` / `test` / `provided`...** là *dependency scope*: điều khiển classpath/lifecycle mà dependency có mặt.
- **“Phạm vi exclusion theo đường phụ thuộc”** trong tên bài là *phạm vi áp dụng theo cạnh/nhánh của graph*, **không phải** phần tử XML `<scope>` của Maven.

`<exclusion>` thông thường chỉ chứa `<groupId>` và `<artifactId>`, không có thẻ `<scope>` hoặc `<version>` để bảo rằng “chỉ loại trừ bản 1.0 ở runtime”. Muốn thay version hay scope được chọn, hãy dùng cơ chế khác phù hợp; exclusion là một công cụ khác.

### 2.4. Dependency mediation và exclusions khác nhau

Nếu `library-a` kéo `common-lib:1.0` còn `library-b` kéo `common-lib:2.0`, Maven phải **chọn một version phù hợp** theo quy tắc mediation và dependencyManagement. Với Maven 3, quy tắc điển hình là **nearest definition**; cùng độ sâu thì thứ tự khai báo có thể quyết định. `dependencyManagement` của consumer có thể áp đặt version quản lý cho một dependency.

**Exclusion không phải một thuật toán chọn version.** Nó loại đường mang artifact bị chỉ định; sau đó graph còn lại vẫn có thể cần version mediation. Nếu bạn chỉ muốn tránh bản quá cũ nhưng cần thư viện, nhiều trường hợp nên **quản lý version đúng và kiểm tra compatibility**, không xóa hẳn artifact.

## 3. Cú pháp chuẩn `<exclusions>` trong `pom.xml`

Giả sử `project-app` phụ thuộc trực tiếp vào `library-a`, còn `library-a` kéo theo `legacy-api`. Bạn muốn ngăn `legacy-api` đi qua nhánh `library-a`:

```xml
<dependencies>
    <dependency>
        <groupId>com.example.libs</groupId>
        <artifactId>library-a</artifactId>
        <version>1.0.0</version>
        <exclusions>
            <exclusion>
                <groupId>com.example.legacy</groupId>
                <artifactId>legacy-api</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
</dependencies>
```

Đây là **đoạn trích** đặt bên trong `<project>` của `pom.xml`, không phải tệp POM độc lập. Tọa độ `com.example.libs:library-a:1.0.0` và `com.example.legacy:legacy-api` là ví dụ; chỉ build được nếu những artifact này thực sự tồn tại trong repository mà máy đang dùng.

Chi tiết:

1. `<exclusions>` nằm trong chính **dependency mang vào nhánh không mong muốn** — ở đây là `library-a`.
2. Một phần tử `<exclusion>` chỉ ra **cặp `groupId` và `artifactId`** của artifact cần cắt. Không đặt `version` hoặc `scope` trong nó.
3. Exclusion được áp dụng **xuyên xuống các dependency bắc cầu bên dưới nhánh `library-a`**, không chỉ “con trực tiếp” của `library-a`.
4. Nếu `legacy-api` có các dependency riêng, việc cắt đường tới `legacy-api` cũng khiến **những dependency chỉ đến được qua đường đó** không còn được đưa vào project. Nhưng artifact của chúng vẫn có thể vào qua đường khác.
5. Các dependency khác cùng nằm dưới `library-a` không bị loại nếu không nằm trong nhánh bị cắt và không bị quy tắc khác loại.
6. Muốn loại nhiều artifact qua cùng một nhánh thì đặt nhiều `<exclusion>` trong cùng `<exclusions>`.

Ví dụ loại hai artifact khác nhau khỏi đường đi qua `library-a`:

```xml
<exclusions>
    <exclusion>
        <groupId>com.example.legacy</groupId>
        <artifactId>legacy-api</artifactId>
    </exclusion>
    <exclusion>
        <groupId>com.example.logging</groupId>
        <artifactId>unused-logging</artifactId>
    </exclusion>
</exclusions>
```

Đoạn này **chỉ hợp lệ khi được đặt trong một `<dependency>`**. Đừng chép nó trực tiếp xuống cuối `<project>`.

### Nếu artifact ở sâu nhiều cấp thì đặt exclusion ở đâu?

Giả sử:

```text
app -> library-a -> library-helper -> legacy-api -> legacy-util
```

Bạn không sở hữu POM của `library-a` hoặc `library-helper`. Vẫn có thể đặt exclusion cho `legacy-api` **trên dependency `library-a` trong POM của app**, không cần sửa thư viện trung gian. Maven sẽ cắt đường xuống artifact `legacy-api` trong nhánh đó; nếu `legacy-util` chỉ đi qua `legacy-api` thì nó cũng biến mất khỏi graph của app.

Điều này khác với việc “exclude một phần tử chỉ cách một cấp”. Exclusion của Maven tác động đến **toàn bộ dependency subtree dưới dependency được gắn**, như tài liệu chính thức mô tả.

## 4. Nhiều đường đến cùng artifact: tại sao loại một lần chưa đủ?

Xét graph:

```text
               app
              /   \
       library-a   library-b
           |          |
       legacy-api  legacy-api
```

Trường hợp A — không có exclusion: nếu không có những quy tắc khác tác động, Maven có thể đưa `legacy-api` vào từ hai đường và chọn version phù hợp.

Trường hợp B — thêm exclusion cho `legacy-api` chỉ ở dependency `library-a`:

```text
app
├── library-a
│   └── (legacy-api excluded trên nhánh a)
└── library-b
    └── legacy-api   <-- đường còn hợp lệ
```

`legacy-api` **vẫn có thể có trong classpath** qua `library-b`. Đây là hành vi **đúng**, không phải Maven “bỏ qua” exclusion.

Trường hợp C — cần chặn cả hai đường:

```xml
<dependencies>
    <dependency>
        <groupId>com.example.libs</groupId>
        <artifactId>library-a</artifactId>
        <version>1.0.0</version>
        <exclusions>
            <exclusion>
                <groupId>com.example.legacy</groupId>
                <artifactId>legacy-api</artifactId>
            </exclusion>
        </exclusions>
    </dependency>

    <dependency>
        <groupId>com.example.libs</groupId>
        <artifactId>library-b</artifactId>
        <version>1.0.0</version>
        <exclusions>
            <exclusion>
                <groupId>com.example.legacy</groupId>
                <artifactId>legacy-api</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
</dependencies>
```

Bây giờ `legacy-api` sẽ không được đưa vào **qua hai nhánh này**. Nhưng nếu `app` khai báo trực tiếp `legacy-api` hoặc `library-c` vẫn kéo nó theo một đường thứ ba, artifact đó vẫn có thể xuất hiện. **Không có một lần exclusion nào mặc nhiên bao phủ mọi đường của toàn project.**

Một lưu ý quan trọng: nếu project của bạn **thực sự dùng** các class của `legacy-api`, loại bỏ toàn bộ đường đi có thể gây lỗi compile hoặc `ClassNotFoundException`/`NoClassDefFoundError` khi chạy. Exclusion **không sửa code** của thư viện upstream và **không bảo đảm tính tương thích** sau khi dependency biến mất.

## 5. Exclusions so với `optional`, `scope` và `dependencyManagement`

| Cơ chế | Khai báo ở đâu | Ảnh hưởng chính | Không làm gì |
| --- | --- | --- | --- |
| `<exclusions>` | Trong một dependency declaration | Ngăn artifact cụ thể đi qua nhánh phụ thuộc ấy | Không cấm tất cả nhánh khác; không chọn version |
| `<optional>true</optional>` | POM của thư viện khai báo dependency | Cho phép chính thư viện dùng dependency, nhưng không tự kéo nó tới consumer qua quan hệ đó | Không làm consumer không thể khai báo dependency trực tiếp |
| `<scope>test</scope>` | Dependency declaration hoặc quản lý tương ứng | Phân loại classpath/giai đoạn sử dụng dependency | Không phải quy tắc exclude theo từng nhánh |
| `<dependencyManagement>` | POM/parent/BOM | Quản lý version, scope và một số thông tin dependency khi chúng được sử dụng | Không mặc nhiên thêm hoặc cấm artifact toàn cục |
| Enforcer `bannedDependencies` | Cấu hình Maven Enforcer Plugin | Kiểm tra graph, **fail build** khi thấy artifact khớp luật cấm | Không tự xóa artifact khỏi graph |

### 5.1. Ai nên dùng `optional`, ai nên dùng exclusion?

Nếu bạn là **tác giả `library-a`**, chỉ một nhóm tính năng tùy chọn mới cần `legacy-api`, có thể đánh dấu dependency đó `optional=true` hoặc tách module chuyên biệt. Khi consumer thêm `library-a`, `legacy-api` không mặc nhiên đi theo do quan hệ optional; consumer cần thì khai báo lại trực tiếp.

Nếu bạn là **consumer `app`** không kiểm soát POM của `library-a`, exclusion là cách chặn một transitive dependency không cần hoặc gây vấn đề đối với app.

Theo hướng dẫn Maven, `optional` và `exclusions` nên được xem như giải pháp tình huống; giải pháp kiến trúc bền vững hơn thường là **tách đúng module** và hạn chế dependency không cần thiết.

### 5.2. Exclusion không phải việc “chỉ tải dependency của scope compile”

`<scope>` điều chỉnh cách dependency tham gia classpath ở các pha compile, test, runtime. `<exclusions>` nói rằng một artifact nhất định **không được đi qua nhánh này** bất kể nó nằm sâu bao nhiêu trong nhánh. Hai cơ chế có thể được áp dụng đồng thời nhưng có ý nghĩa khác nhau.

Đừng cố sửa vấn đề classpath bằng cách tùy tiện đổi dependency từ `compile` sang `provided` hoặc `test`. Điều đó có thể làm code thiếu thư viện khi chạy hoặc khi đóng gói ứng dụng.

### 5.3. Khi chỉ cần bản mới hơn, đừng exclude để né version cũ

Giả sử consumer nhận `legacy-api:1.0` qua A và `legacy-api:2.0` qua B. Nếu nhu cầu là **dùng bản 2.0 tương thích**, hãy kiểm tra phiên bản được Maven chọn và cân nhắc trực tiếp khai báo đúng version hoặc quản lý version qua `dependencyManagement`. Exclusion ở A có thể khiến 1.0 không còn trong graph ứng viên, nhưng không phải cách quản lý version toàn cục đáng tin cậy trong mọi lần đổi POM.

Trong dự án production, ưu tiên xác định nguyên nhân: compatibility, lỗ hổng, version mediation hay module không còn dùng. Sau đó chọn một giải pháp minh bạch và chạy đầy đủ test.

## 6. Ví dụ Maven 3 + Java 17 chạy được: một artifact đi qua hai nhánh

Ví dụ này có **4 module Java và một POM aggregator/parent**. Không phụ thuộc thư viện Java ngoài; Maven chỉ cần tải các plugin đã khai báo khi local repository chưa có chúng. Các tên và version là minh họa nhưng **mọi module đều được định nghĩa trong bộ file dưới đây**, nên có thể thực hiện bằng một reactor build.

Mục tiêu:

- `left` và `right` **đều** cần `common`.
- `app` phụ thuộc cả `left` và `right`.
- `app` **exclude `common` khi nó đi qua `left`**, nhưng **không exclude** đường đi qua `right`.
- Build `app` vẫn có thể chạy vì `common` được đưa vào qua `right`.
- Nếu tiếp tục exclude `common` trên đường qua `right`, artifact đó có thể biến mất hoàn toàn và chức năng gọi từ `left/right` sẽ gặp lỗi runtime.

### 6.1. Cấu trúc thư mục

```text
exclusion-paths/
├── pom.xml
├── common/
│   ├── pom.xml
│   └── src/main/java/com/example/paths/common/Marker.java
├── left/
│   ├── pom.xml
│   └── src/main/java/com/example/paths/left/Left.java
├── right/
│   ├── pom.xml
│   └── src/main/java/com/example/paths/right/Right.java
└── app/
    ├── pom.xml
    └── src/main/java/com/example/paths/app/App.java
```

Tất cả module có `groupId=com.example.paths`, `version=1.0.0` kế thừa từ parent. Không có cycle: left → common, right → common, app → left và app → right.

### 6.2. `exclusion-paths/pom.xml`: parent và aggregator

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example.paths</groupId>
    <artifactId>exclusion-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>common</module>
        <module>left</module>
        <module>right</module>
        <module>app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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
                    <version>3.5.2</version>
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

`<modules>` gom các project vào một reactor. `<pluginManagement>` quản lý version plugin để những default bindings tương ứng trong JAR project sử dụng version xác định. `maven.compiler.release=17` yêu cầu JDK đủ khả năng biên dịch Java 17.

### 6.3. `exclusion-paths/common/pom.xml` và Java class

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example.paths</groupId>
        <artifactId>exclusion-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>demo-common</artifactId>
</project>
```

`common/src/main/java/com/example/paths/common/Marker.java`:

```java
package com.example.paths.common;

public final class Marker {
    private Marker() {
    }

    public static String value() {
        return "common";
    }
}
```

Class `Marker` là thành phần dùng chung; không cần `main()` vì nó được gọi từ module khác.

### 6.4. `exclusion-paths/left/pom.xml` và Java class

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example.paths</groupId>
        <artifactId>exclusion-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>demo-left</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.example.paths</groupId>
            <artifactId>demo-common</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

`left/src/main/java/com/example/paths/left/Left.java`:

```java
package com.example.paths.left;

import com.example.paths.common.Marker;

public final class Left {
    private Left() {
    }

    public static String message() {
        return "left=" + Marker.value();
    }
}
```

`left` thực sự dùng `Marker`, nên nó **cần common để biên dịch và chạy**. Exclusion ở consumer app **không thay đổi POM hay cách build riêng của left**.

### 6.5. `exclusion-paths/right/pom.xml` và Java class

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example.paths</groupId>
        <artifactId>exclusion-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>demo-right</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.example.paths</groupId>
            <artifactId>demo-common</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

`right/src/main/java/com/example/paths/right/Right.java`:

```java
package com.example.paths.right;

import com.example.paths.common.Marker;

public final class Right {
    private Right() {
    }

    public static String message() {
        return "right=" + Marker.value();
    }
}
```

`right` cũng khai báo dependency thường vào common. Tại consumer app, nhánh này **không có exclusion**, nên common vẫn có một đường hợp lệ để tham gia classpath của app.

### 6.6. `exclusion-paths/app/pom.xml` — exclusion chỉ gắn ở nhánh left

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example.paths</groupId>
        <artifactId>exclusion-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>demo-app</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.example.paths</groupId>
            <artifactId>demo-left</artifactId>
            <version>1.0.0</version>
            <exclusions>
                <exclusion>
                    <groupId>com.example.paths</groupId>
                    <artifactId>demo-common</artifactId>
                </exclusion>
            </exclusions>
        </dependency>

        <dependency>
            <groupId>com.example.paths</groupId>
            <artifactId>demo-right</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

Quan sát đúng vị trí: `<exclusions>` là con của dependency `demo-left`; nó **không nằm bên trong project `demo-left`** và **không đi cùng dependency `demo-right`**.

### 6.7. `exclusion-paths/app/src/main/java/com/example/paths/app/App.java`

```java
package com.example.paths.app;

import com.example.paths.left.Left;
import com.example.paths.right.Right;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(Left.message());
        System.out.println(Right.message());
    }
}
```

Ứng dụng chỉ dùng trực tiếp API của `Left` và `Right`; nó **không trực tiếp import `Marker`**. Đó là thiết kế hợp lý: nếu ứng dụng trực tiếp sử dụng class `Marker` thì cách khai báo dependency rõ ràng nhất là thêm `demo-common` thành **direct dependency** của app, thay vì phụ thuộc tình cờ vào nhánh bắc cầu.

### 6.8. Build và kiểm tra dependency graph

Mở terminal **ở thư mục `exclusion-paths`**, có `pom.xml` root. Chạy:

```bash
mvn -version
mvn clean install
```

Maven phải có JDK 17+ và có thể tải plugin khi cần. Reactor hiểu `demo-common` là dependency của left/right và build các module theo thứ tự hợp lệ trước app. Lệnh `install` còn cài POM/JAR của các module vào **local repository**, giúp các lệnh kiểm tra riêng trong `app` phân giải được dependency.

Sau đó xem cây dependency của riêng app:

```bash
mvn -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Kết quả mang tính cấu trúc (bỏ dòng log và ký tự trình bày phụ thuộc plugin version):

```text
com.example.paths:demo-app:jar:1.0.0
+- com.example.paths:demo-left:jar:1.0.0:compile
\- com.example.paths:demo-right:jar:1.0.0:compile
   \- com.example.paths:demo-common:jar:1.0.0:compile
```

Đây là **mẫu cây kỳ vọng**, không phải khẳng định mọi phiên bản plugin in đúng ký tự `+-`, khoảng trắng hoặc thứ tự log. Điểm cần kiểm tra là:

1. `demo-left` và `demo-right` đều được chọn.
2. `demo-common` **không còn được kéo qua nhánh left**.
3. `demo-common` **vẫn được chọn thông qua right**.
4. Tổng thể chỉ cần một artifact `demo-common:1.0.0` trên classpath; Maven không phải giữ hai bản giống nhau.

Có thể lọc **chỉ phần hiển thị** để xem common rõ hơn:

```bash
mvn -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dincludes=com.example.paths:demo-common
```

**Cảnh báo:** `-Dincludes` / `-Dexcludes` của **goal `dependency:tree`** chỉ điều chỉnh **những nút được in ra**, không giống `<exclusions>` trong POM và **không thay đổi dependencies của build**.

### 6.9. Chạy app bằng classpath thực sự được Maven phân giải

Vì lệnh `install` đã cài các module vào local repository, có thể chạy:

```bash
mvn -f app/pom.xml org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=com.example.paths.app.App
```

Goal `exec:java` có thể tải plugin từ repository trong lần đầu. Nó chạy `App.main` với các dependency của project theo classpath Maven phân giải. **Hai dòng do code Java in ra chính xác là:**

```text
left=common
right=common
```

Maven còn in thông tin plugin và build status tùy phiên bản; những log ấy không được tính là stdout cố định của code Java. Nếu chạy thành công, điều đó phù hợp với việc `common` còn có đường đi qua `right`.

### 6.10. Thí nghiệm đối chứng: exclude cả nhánh right

Để kiểm tra giới hạn, **giữ dependency `demo-left` như cũ**, rồi thêm phần sau **vào dependency `demo-right` trong `app/pom.xml`**:

```xml
<exclusions>
    <exclusion>
        <groupId>com.example.paths</groupId>
        <artifactId>demo-common</artifactId>
    </exclusion>
</exclusions>
```

Đây chỉ là **đoạn cần chèn vào dependency right**, không phải một `pom.xml` hoàn chỉnh và không chèn ở project root.

Bây giờ hai nhánh app → left → common và app → right → common đều bị cắt. Quan sát lại tree:

```bash
mvn -f app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Trong app, `demo-common` sẽ không còn đường bắc cầu hợp lệ qua left/right. Các JAR `demo-left` và `demo-right` vẫn tồn tại, vì exclusion không xóa chúng. Tuy nhiên, khi `App` gọi `Left.message()` và `Right.message()`, hai class ấy vẫn cần `Marker`. Chạy lệnh `exec:java` ở mục trên có thể dẫn tới **`NoClassDefFoundError`** vì `Marker` không còn trên runtime classpath, dù app có thể biên dịch do nó không trực tiếp import `Marker`.

Đó là ví dụ vì sao **exclusion không phải giải pháp an toàn nếu bạn cắt một dependency mà thư viện upstream thực sự cần**. Sau thí nghiệm, **gỡ exclusion mới thêm vào `demo-right`** để trở lại ví dụ thành công. Với ứng dụng thật, việc sửa hoặc thay thế thư viện upstream và kiểm thử chức năng quan trọng hơn việc chỉ làm đẹp cây dependency.

## 7. Cách tìm chính xác đường phụ thuộc cần exclusion

Một quy trình chắc chắn khi gặp artifact ngoài ý muốn:

### Bước 1 — Xác định tọa độ và mục tiêu

Ghi đầy đủ: artifact nào, do vấn đề gì, bạn có muốn nó **biến mất hoàn toàn** hay chỉ **không đi qua một thư viện cụ thể**?

Ví dụ `org.example:old-logger` gây trùng logger với giải pháp hiện tại, hoặc một API cũ không được dùng. Phân biệt tình huống muốn **loại artifact**, muốn **nâng version**, muốn **giảm phạm vi runtime** và muốn **fail build theo policy**.

### Bước 2 — Xem dependency tree

Trong thư mục chứa `pom.xml`:

```bash
mvn dependency:tree
```

Nếu muốn dùng goal và version xác định:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Để tập trung vào artifact:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dincludes=org.example:old-logger
```

`-Dincludes` chỉ lọc output. Cũng có thể xuất `DOT` hoặc `JSON` từ các phiên bản plugin hỗ trợ:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -DoutputType=dot -DoutputFile=dependency-tree.dot
```

Khi kết quả bị mediation hoặc lọc khiến khó nhìn đủ mọi đường, hãy kiểm tra POM của các upstream artifacts và dependency graph, không suy diễn chỉ từ một cây rút gọn.

### Bước 3 — Chọn dependency cạnh trên cùng có thể sửa được

Nếu bạn sở hữu POM app, tìm **direct dependency** thực sự mang artifact cần loại vào. Đặt `<exclusions>` ngay ở dependency này. Không cố sửa trực tiếp JAR trong `~/.m2` và cũng không cần sửa POM của thư viện bên thứ ba.

Nếu artifact được kéo qua **hai direct dependencies**, hãy quyết định xem cần exclusion trên **một** hay **cả hai**. Nếu về sau một dependency mới cũng kéo nó theo, exclusion cũ không tự mở rộng để bao phủ nhánh mới.

### Bước 4 — Kiểm tra lại **graph đã phân giải**

Chạy lại `dependency:tree` không chỉ ở local dev mà ở CI nếu project có profile/BOM khác nhau. Quan sát version thực tế và xem artifact có còn hay không. Có thể kết hợp `dependency:analyze` để phát hiện trường hợp source trực tiếp dùng dependency nhưng chỉ khai báo bắc cầu; kết quả phân tích cũng cần người đọc diễn giải, không thay thế kiểm thử.

### Bước 5 — Chạy test đúng phạm vi

`mvn clean verify` (hoặc pipeline build/test chuẩn của dự án) giúp phát hiện compile errors, unit/integration test regressions và các lỗi khác. Không phải mọi lỗi tương thích đều lộ ra trong build: phải có test chạy chức năng từng sử dụng thư viện bị loại. Nếu là thư viện runtime, kiểm tra cả classpath và artifact đóng gói/phát hành theo cách thực tế.

## 8. Muốn cấm artifact toàn cục? Dùng kiểm tra policy, không trông vào một exclusion

Một exclusion là **cấu hình chọn nhánh**. Nếu tổ chức có chính sách không cho phép `com.example.legacy:legacy-api` xuất hiện ở bất kỳ đường dependency nào, Maven Enforcer có rule **`bannedDependencies`** để **fail build** khi artifact khớp luật cấm. Đoạn ví dụ POM sau là một cấu hình plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-enforcer-plugin</artifactId>
            <version>3.6.3</version>
            <executions>
                <execution>
                    <id>ban-legacy-api</id>
                    <phase>validate</phase>
                    <goals>
                        <goal>enforce</goal>
                    </goals>
                    <configuration>
                        <rules>
                            <bannedDependencies>
                                <searchTransitive>true</searchTransitive>
                                <excludes>
                                    <exclude>com.example.legacy:legacy-api</exclude>
                                </excludes>
                            </bannedDependencies>
                        </rules>
                        <fail>true</fail>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đây là **đoạn `<build>` minh họa**, không tự ghép vào ví dụ ở mục 6 nếu chưa muốn áp dụng policy. Rule sẽ kiểm tra dependency graph được phân giải khi chạy lifecycle có `validate`, và có thể **dừng build** nếu artifact bị cấm còn xuất hiện. Nó **không âm thầm xóa artifact hoặc chỉnh POM**. Bạn vẫn phải thêm exclusion ở từng đường đi phù hợp, chọn version được phép hoặc sửa upstream dependency.

Có thể dùng patterns và version ranges trong cấu hình Enforcer theo tài liệu của chính rule, nhưng cú pháp ấy **khác** `<exclusion>` trong dependency Maven thông thường. Đừng sao chép một chuỗi rule nhiều dấu `:` hoặc wildcard vào `<exclusion>` rồi nghĩ chúng có cùng ngữ nghĩa.

Với yêu cầu bảo mật, cần kết hợp chính sách quản lý phiên bản, cập nhật lỗ hổng và kiểm thử chứ không chỉ thêm exclusion. Một artifact bị loại nhưng code upstream vẫn gọi nó có thể gây lỗi ở runtime; một artifact còn nhưng version được vá có thể là giải pháp đúng hơn tùy trường hợp.

## 9. Những giới hạn và lỗi phổ biến

| Lỗi hoặc hiểu nhầm | Giải thích / cách xử lý |
| --- | --- |
| Thêm exclusion ở `library-a` nhưng artifact vẫn có trong tree | Có đường khác như `library-b`, direct dependency hoặc module khác; tìm tiếp các đường |
| Đặt `<exclusions>` ở root của `pom.xml` | XML không thuộc vị trí cho phép; đặt trong đúng `<dependency>` |
| Thêm `<version>` vào `<exclusion>` | Exclusion thường match `groupId/artifactId`, không phải cơ chế lọc version |
| Exclude `legacy-api` nhưng mục tiêu là cập nhật lên bản mới | Xem `dependencyManagement`/version mediation thay vì loại bỏ API mà chương trình cần |
| Exclude ngay thư viện direct dependency `library-a` trong chính mục `library-a` | Exclusions áp dụng cho **phụ thuộc bắc cầu đi qua A**, không phải cách xóa bản thân A; xóa hoặc sửa direct dependency nếu không cần A |
| Dùng `-Dexcludes=...` với `dependency:tree` rồi nghĩ classpath đã đổi | Chỉ lọc **cây hiển thị**, không sửa dependency graph |
| Đổi `<scope>` để “cắt nhánh” | Scope có ý nghĩa classpath/phases; không tương đương exclusion theo đường |
| App không khai báo thư viện mình trực tiếp import | Thêm **direct dependency** phù hợp; đừng phụ thuộc tình cờ vào transitive path |
| Sau exclusion xuất hiện `NoClassDefFoundError` | Có thể đã loại dependency runtime mà upstream còn cần; khôi phục hoặc sửa kiến trúc |
| Mỗi máy in tree khác nhau | Kiểm tra Maven/JDK, active profiles, BOM/dependencyManagement, repositories, artifact versions và plugin version |
| Exclusion ở app nhưng plugin Maven vẫn có dependency đó | Project dependencies và **plugin dependencies** có cơ chế phân giải riêng; exclusion trên project dependency không tự kiểm soát plugin classpath |
| Chỉ chạy `mvn clean` và mong exclusions được xác minh | `clean` dọn build output, không phải công cụ kiểm tra dependency tree |
| Một nhánh bị exclude nhưng artifact vẫn có trong local repository | Local repository là **cache**; file còn trên đĩa không chứng minh classpath của build đang dùng artifact đó |
| Enforcer `bannedDependencies` báo lỗi dù đã exclude một nhánh | Vẫn còn đường khác tới artifact bị cấm; cần chặn hoặc thay thế các đường hợp lệ khác |

**Phân biệt cache và classpath:** `~/.m2/repository` có thể vẫn chứa JAR đã tải từ những lần build trước. Maven exclusion không “xóa file khỏi `.m2`”; điều cần xác minh là artifact có mặt trong **resolved project dependency graph** và classpath của build hiện tại hay không.

**Phân biệt dependency project và dependency của plugin:** exclusion khai báo trên một project dependency không tự loại dependency được chính Maven Compiler Plugin, Surefire hoặc một plugin khác dùng để chạy. Đây là những graph với mục đích khác nhau.

**Không dùng exclusion để che lỗ hổng trong code:** nếu upstream thực sự cần artifact, một exclusion có thể khiến build chạy được nhưng hỏng ở nhánh tính năng ít được test. Ưu tiên cập nhật/thay thế thư viện hoặc chỉnh phụ thuộc upstream khi có thể.

## 10. Bài tập tự đánh giá

**Bài 1 — một đường còn tồn tại.** Project A phụ thuộc B và C, cả B và C đều kéo D. Exclude D trong dependency B của A. D còn có thể vào A không? **Có**, qua C.

**Bài 2 — loại sâu nhiều cấp.** A → B → C → D → E. A không sở hữu POM của B/C nhưng muốn loại D qua nhánh B. Exclusion đặt ở đâu? **Trong dependency B được khai báo tại A**, target groupId/artifactId của D. E cũng mất theo đường bị cắt nếu không có đường khác.

**Bài 3 — version và đường đi.** B kéo D 1.0, C kéo D 2.0. A muốn D 2.0 mà vẫn cần API của D. Nên cân nhắc **dependency management/direct version** và test compatibility; không coi exclusion là nút tự nâng version.

**Bài 4 — tìm hiểu tool.** Lệnh `mvn dependency:tree -Dexcludes=some.group:some-artifact` có xóa artifact khỏi classpath không? **Không**; tham số này chỉ lọc output của goal hiển thị tree.

**Bài 5 — thử nghiệm thực tế.** Với bộ ví dụ `exclusion-paths`:
1. Kiểm tra `demo-common` đi qua `demo-right` sau khi exclude ở `demo-left`.
2. Thêm exclusion `demo-common` ở dependency right trong app, xem tree và thử chạy `App`. Vì sao lúc ấy có thể xảy ra lỗi runtime?
3. Khôi phục app POM và xác nhận hai dòng `left=common` và `right=common`.

**Bài 6 — chính sách toàn cục.** Nếu policy của nhóm không cho phép artifact D ở bất kỳ đường nào, vì sao chỉ exclude ở B chưa đủ? Khi nào cần Maven Enforcer `bannedDependencies` để fail CI?

Ghi nhớ một câu: **`<exclusions>` cắt một artifact trong nhánh đi qua dependency được gắn cấu hình; nếu còn một nhánh khác đến cùng artifact, Maven vẫn có thể chọn nó.**

### Tài liệu Apache Maven chính thức

- [Introduction to Optional and Excludes Dependencies — exclusions per dependency](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html)
- [Introduction to the Dependency Mechanism — transitive dependency, scope và mediation](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Maven Dependency Plugin — cách dùng](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
- [Maven Enforcer Rule — bannedDependencies](https://maven.apache.org/enforcer/enforcer-rules/bannedDependencies.html)
- [Maven POM Reference — dependency và exclusions](https://maven.apache.org/pom.html)
