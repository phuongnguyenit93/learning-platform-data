# Tạo xung đột phiên bản và xử lý bằng quản lý phụ thuộc trong Maven

## 1. Mục tiêu bài thực hành tổng hợp

Maven có thể tải **hai thư viện trung gian** cùng sử dụng một thư viện nền, nhưng ở **hai phiên bản khác nhau**. Điều nguy hiểm là một project có thể **biên dịch thành công** mà khi chạy lại gặp `NoSuchMethodError` vì classpath thực tế chỉ chứa phiên bản cũ, trong khi một thư viện đã được biên dịch với API mới.

Bài này tạo xung đột bằng **các project tự viết**, không dựa vào một thư viện công khai tình cờ có dependency graph thay đổi theo thời gian. Bạn sẽ:

1. Tạo `formatter-core` version **1.0.0** với một phương thức cơ bản.
2. Tạo `formatter-core` version **2.0.0** giữ API cũ và thêm một phương thức mới.
3. Tạo `legacy-client` phụ thuộc `formatter-core:1.0.0`.
4. Tạo `modern-client` phụ thuộc `formatter-core:2.0.0`.
5. Tạo `demo-app` phụ thuộc **legacy-client trước, modern-client sau**.
6. Đọc `dependency:tree` để thấy Maven chọn **formatter-core:1.0.0** theo quy tắc gần nhất, ưu tiên khai báo trước khi cùng độ sâu.
7. Chạy ứng dụng, quan sát lỗi runtime **`NoSuchMethodError`** khi modern-client gọi API chỉ có ở 2.0.0.
8. Thêm `<dependencyManagement>` vào app để **quản lý tập trung formatter-core:2.0.0**.
9. Xây lại, kiểm dependency graph và stdout sau khi sửa.
10. Bổ sung những cách phát hiện sớm và các trường hợp không nên ép version tùy tiện.

Ví dụ đặt mục tiêu **Maven 3.9.x, JDK 17+**. Bạn không cần cài thư viện third-party để tạo conflict, nhưng Maven vẫn cần tải các build plugins từ repository được cấu hình. Nếu bạn đã có Maven Wrapper, có thể thay `mvn` bằng `./mvnw`; bài không tạo Wrapper files.

**Điểm cốt lõi:** chọn đúng version không chỉ để “xóa cảnh báo conflict”, mà để **đáp ứng ABI/API mà tất cả consumer thực sự cần**.

## 2. Nhận diện đúng một xung đột phiên bản

Một tình huống dependency graph:

~~~text
demo-app:1.0.0
├── legacy-client:1.0.0
│   └── formatter-core:1.0.0
└── modern-client:1.0.0
    └── formatter-core:2.0.0
~~~

Đây là **hai yêu cầu phiên bản của cùng tọa độ `org.example.conflict:formatter-core`**. Nếu scope/type/classifier trùng, Maven dependency mediation thường chỉ chọn **một phiên bản** cho project classpath, không tự cho hai phiên bản cùng tồn tại với cùng class/package để JVM tùy ý quyết định.

Không nhầm xung đột phiên bản với các trường hợp khác:

- Hai artifacts **khác groupId/artifactId** nhưng chứa class trùng tên: duplicate classes, `dependencyManagement` cho một GAV không nhất thiết giải quyết.
- Hai modules có **cùng artifactId nhưng groupId khác nhau**: không phải một tọa độ, Maven có thể chọn cả hai.
- Một dependency thuộc `test` không mặc nhiên xuất hiện trong runtime production.
- Một Maven **plugin dependency** nằm trên plugin classpath riêng; `dependencyManagement` của project không trực tiếp quản lý plugin's transitive classpath.
- Một project bị lỗi HTTP 401, 404 hoặc `.lastUpdated`: đó có thể là lỗi resolution/repository, không phải version mediation.
- `NoClassDefFoundError` và `ClassNotFoundException` nói về class thiếu; `NoSuchMethodError` thường liên quan ABI mismatch, nhưng cũng cần kiểm bytecode/classpath thực tế.

Bài dùng tên package `org.example.conflict` để dễ nhìn cây phụ thuộc, **không phải tọa độ của artifact đang có trên Maven Central**.

## 3. Maven chọn phiên bản nào? Hai quy tắc quan trọng

Theo Apache Maven Dependency Mechanism:

**Quy tắc 1 — nearest definition:** Trong các đường từ project tới cùng một artifact, Maven chọn phiên bản xuất hiện ở **độ sâu ngắn hơn** (gần project hơn).

**Quy tắc 2 — first declaration wins:** Nếu các đường cùng độ sâu, nhánh được khai báo **trước** trong thứ tự dependency liên quan thắng. Đây là lý do thứ tự `legacy-client` và `modern-client` trong POM demo có thể ảnh hưởng phiên bản được chọn.

Ví dụ có hai nhánh dài 2 cạnh:

~~~text
demo-app
├── legacy-client          depth 1
│   └── formatter-core:1.0 depth 2
└── modern-client          depth 1
    └── formatter-core:2.0 depth 2
~~~

Nếu `legacy-client` được khai báo trước, Maven chọn `formatter-core:1.0.0` theo luật cùng độ sâu. Điều đó **không có nghĩa 1.0.0 là mới hơn, an toàn hơn hoặc phù hợp hơn**. Maven mediation là quy tắc giải quyết đồ thị, không là bộ kiểm tương thích runtime.

Ví dụ khác:

~~~text
demo-app
├── formatter-core:2.0.0      depth 1
└── legacy-client:1.0.0       depth 1
    └── formatter-core:1.0.0  depth 2
~~~

Phiên bản **2.0.0 direct** được chọn vì gần project hơn, bất kể thứ tự khi so với nhánh transitive sâu hơn. Nhưng việc khai báo direct dependency chỉ để ép version có ý nghĩa hợp đồng riêng, cần được cân nhắc ở mục 25.

## 4. dependencyManagement thay đổi luật chọn ra sao?

`<dependencyManagement>` quản lý **version/scope/exclusions mặc định cho các project dependencies được dùng**, đặc biệt là phiên bản của phụ thuộc **bắc cầu**, và theo Maven guide **được ưu tiên trước dependency mediation cho transitive dependencies**.

Khi app khai báo:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.conflict</groupId>
            <artifactId>formatter-core</artifactId>
            <version>2.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Maven có thể áp version **2.0.0** cho formatter-core xuất hiện trong các nhánh client trước khi chọn dependency graph của app. App vẫn không tự tải formatter-core nếu **không có nhánh nào phụ thuộc nó**: `dependencyManagement` **quản lý**, còn `dependencies` **khai báo nhu cầu**.

**Quan trọng:** một direct dependency có version explicit trong chính app không nên bị tưởng là bị `dependencyManagement` ghi đè vô điều kiện. Explicit direct declaration có precedence riêng; hãy kiểm effective POM/`dependency:tree`. Trong bài demo, app **không** khai báo formatter-core trực tiếp, nên cơ chế áp version cho phụ thuộc bắc cầu được quan sát rõ ràng.

## 5. Cấu trúc workspace và lý do dùng năm project độc lập

Chúng ta tạo:

~~~text
maven-version-conflict/
├── formatter-v1/
│   ├── pom.xml
│   └── src/main/java/org/example/conflict/Formatter.java
├── formatter-v2/
│   ├── pom.xml
│   └── src/main/java/org/example/conflict/Formatter.java
├── legacy-client/
│   ├── pom.xml
│   └── src/main/java/org/example/legacy/LegacyClient.java
├── modern-client/
│   ├── pom.xml
│   └── src/main/java/org/example/modern/ModernClient.java
└── demo-app/
    ├── pom.xml
    └── src/main/java/org/example/app/Main.java
~~~

**Cần hiểu:** hai thư mục `formatter-v1` và `formatter-v2` có **cùng groupId/artifactId** nhưng **version khác nhau**. Chúng là **hai project build/install độc lập**, không phải một multi-module reactor để chạy `mvn install` từ thư mục root. Thư mục root **không có POM** trong ví dụ. Ta install hai version lần lượt vào cùng một Maven local repository riêng, đúng cách mô phỏng hai artifact releases đã được xuất bản.

Các modules khác cũng build độc lập vì muốn client 1.0.0 được biên dịch **thật** với API v1, client 2.0.0 với API v2. Nếu tất cả cùng recompile bằng một formatter version duy nhất, bạn sẽ không thể tái hiện ABI mismatch đúng như bài học.

## 6. Prerequisites và local repository cô lập

Kiểm phiên bản:

~~~bash
mvn -version
java -version
~~~

Cần Maven 3.9.x và JDK 17+. Maven runtime có thể chạy trên JDK khác trong giới hạn tương thích, nhưng các POM minh họa dùng `maven.compiler.release=17`, vì vậy compiler phải có toolchain/JDK hỗ trợ Java 17.

Để không làm lẫn demo artifacts vào `~/.m2/repository` chính, mọi lệnh Maven ở bài dùng **cùng một repo riêng**. Linux/macOS Bash, chạy từ thư mục `maven-version-conflict`:

~~~bash
REPO="$PWD/.demo-m2"
~~~

PowerShell, cũng từ thư mục root:

~~~powershell
$repo = Join-Path (Get-Location) ".demo-m2"
~~~

Dùng chính biến `REPO` hoặc `$repo` trong tất cả các lệnh. Nếu bạn thay repo path ở giữa các bước, Maven có thể báo `Could not find artifact` vì một client được install ở cache A nhưng app đang dùng cache B — đó là **lỗi cache/registry**, không phải dependency conflict.

Lần đầu build có thể cần internet để tải Maven Compiler, JAR, Install, Dependency plugins. Không chạy `-o` ngay khi cache trống.

## 7. formatter-core v1.0.0: POM đầy đủ

Tạo `formatter-v1/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.conflict</groupId>
    <artifactId>formatter-core</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Formatter API v1 Demo</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
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
                <version>3.1.3</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là POM library thuần Java, không có external runtime dependencies. `groupId:artifactId:version=org.example.conflict:formatter-core:1.0.0` sẽ cho Maven install:

~~~text
.demo-m2/org/example/conflict/formatter-core/1.0.0/
    formatter-core-1.0.0.pom
    formatter-core-1.0.0.jar
~~~

Đường dẫn thể hiện Maven repository layout. Không giả định hai files đã có trước khi thực hiện install thành công.

## 8. formatter-core v1.0.0: Java API cũ

Tạo `formatter-v1/src/main/java/org/example/conflict/Formatter.java`:

~~~java
package org.example.conflict;

public final class Formatter {

    private Formatter() {
    }

    public static String decorate(String name) {
        return "Hello, " + name;
    }
}
~~~

Lớp v1 chỉ có **một phương thức public static** mà client sử dụng:

~~~java
Formatter.decorate("Maven")
~~~

Kết quả trả về:

~~~text
Hello, Maven
~~~

Không có phương thức `decorateLoud(String)` trong v1. Đây là **nguyên nhân kỹ thuật** cho lỗi runtime ở bước sau khi JVM nạp `Formatter.class` từ JAR v1 nhưng modern-client cố liên kết method chỉ tồn tại trong JAR v2.

Không thay đổi package/class name giữa hai phiên bản, để thật sự minh họa conflict của cùng class/API.

## 9. formatter-core v2.0.0: POM đầy đủ

Tạo `formatter-v2/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.conflict</groupId>
    <artifactId>formatter-core</artifactId>
    <version>2.0.0</version>
    <packaging>jar</packaging>
    <name>Formatter API v2 Demo</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
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
                <version>3.1.3</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Lưu ý cả hai POM phiên bản 1 và 2 có **cùng** `groupId` và `artifactId`, chỉ khác version. Không được tùy tiện đổi tên v2 thành `formatter-core2` nếu mục đích là xem Maven conflict mediation: khi đổi artifactId, Maven coi là tọa độ **khác** và graph không còn là hai versions của một artifact.

## 10. formatter-core v2.0.0: giữ API cũ, thêm API mới

Tạo `formatter-v2/src/main/java/org/example/conflict/Formatter.java`:

~~~java
package org.example.conflict;

import java.util.Locale;

public final class Formatter {

    private Formatter() {
    }

    public static String decorate(String name) {
        return "Hello, " + name;
    }

    public static String decorateLoud(String name) {
        return "Hello, " + name.toUpperCase(Locale.ROOT) + "!";
    }
}
~~~

V2 **giữ nguyên** `decorate(String)` như v1 và **thêm** `decorateLoud(String)`. Do đó legacy-client đã compile với v1 vẫn có thể gọi `decorate` khi chạy với v2, ít nhất với API nhỏ của ví dụ.

Nếu gọi:

~~~java
System.out.println(Formatter.decorate("Maven"));
System.out.println(Formatter.decorateLoud("Maven"));
~~~

khi class được nạp từ JAR **v2**, stdout của **hai phương thức trên** là:

~~~text
Hello, Maven
Hello, MAVEN!
~~~

Đây là mảnh code sử dụng API, không phải một Java `Main` độc lập. Ở v1, lời gọi thứ hai **không thể compile** nếu chỉ có v1 API trên compile classpath. Nếu mã đã compile với v2 nhưng runtime nạp v1, lỗi có thể xuất hiện khi JVM thực hiện method linkage.

**Vì sao chọn v2 tương thích ngược?** Để phương án `dependencyManagement=2.0.0` ở phần sau là **có cơ sở**. Trong hệ thống thật, một phiên bản lớn hơn có thể xóa/đổi phương thức, thay hành vi hoặc yêu cầu JDK mới; lúc đó ép bản mới cũng không nhất thiết giải quyết conflict.

## 11. legacy-client: POM đầy đủ phụ thuộc formatter v1

Tạo `legacy-client/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.conflict</groupId>
    <artifactId>legacy-client</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.example.conflict</groupId>
            <artifactId>formatter-core</artifactId>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.3</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`legacy-client` tự khai báo `formatter-core:1.0.0`. Nó không có parent/BOM/dependencyManagement nào thay phiên bản khi build chính client, nên compiler của nó chỉ cần API v1.

`compile` scope mặc định khiến `formatter-core:1.0.0` là **transitive dependency** khi app tiêu thụ `legacy-client:1.0.0`, trừ khi app quản lý/exclude hoặc scope/optional làm thay điều kiện.

## 12. legacy-client: source code đầy đủ

Tạo `legacy-client/src/main/java/org/example/legacy/LegacyClient.java`:

~~~java
package org.example.legacy;

import org.example.conflict.Formatter;

public final class LegacyClient {

    private LegacyClient() {
    }

    public static String render(String name) {
        return "legacy=" + Formatter.decorate(name);
    }
}
~~~

`LegacyClient.render("Maven")` trả:

~~~text
legacy=Hello, Maven
~~~

Client này chỉ gọi API `decorate(String)` có trong **cả v1 và v2** của demo. Chính sự giữ lại phương thức này cho phép app, sau khi dùng v2, tiếp tục chạy phần legacy mà không cần rebuild source client.

Tuy nhiên trong dự án thật, binary compatibility có thể phức tạp hơn: method signature, exceptions, class hierarchy, bytecode target, service provider, resource names và behavior runtime cần được kiểm tra chứ không thể suy từ một ví dụ đơn giản.

## 13. modern-client: POM đầy đủ phụ thuộc formatter v2

Tạo `modern-client/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.conflict</groupId>
    <artifactId>modern-client</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.example.conflict</groupId>
            <artifactId>formatter-core</artifactId>
            <version>2.0.0</version>
        </dependency>
    </dependencies>

    <build>
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
                <version>3.1.3</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đọc đúng:** modern-client có **version 1.0.0 của chính nó**, nhưng phụ thuộc `formatter-core:2.0.0`. Đừng nhầm version của client với version của library nền.

Modern-client phải được compile khi formatter v2 đã install trong local repo mà Maven invocation dùng.

## 14. modern-client: code gọi API chỉ có ở v2

Tạo `modern-client/src/main/java/org/example/modern/ModernClient.java`:

~~~java
package org.example.modern;

import org.example.conflict.Formatter;

public final class ModernClient {

    private ModernClient() {
    }

    public static String render(String name) {
        return "modern=" + Formatter.decorateLoud(name);
    }
}
~~~

`Formatter.decorateLoud` **không có** trong formatter v1. Khi build `modern-client` với formatter v2 đúng, Java compiler tạo bytecode có lời gọi tới method signature:

~~~text
org.example.conflict.Formatter.decorateLoud(java.lang.String)
    -> java.lang.String
~~~

Nếu tại runtime `Formatter.class` lại được nạp từ v1, JVM không tìm thấy method phù hợp, gây `java.lang.NoSuchMethodError`. Đây là ví dụ điển hình của **binary linkage failure** do transitive version conflict.

Đừng “chữa” code modern-client bằng cách bỏ lời gọi v2 chỉ để tránh exception; mục tiêu là sửa **resolved runtime classpath** để đáp ứng thư viện đã được compile.

## 15. demo-app trước khi sửa: POM đầy đủ, thứ tự cố ý gây conflict

Tạo `demo-app/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.conflict</groupId>
    <artifactId>demo-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.example.conflict</groupId>
            <artifactId>legacy-client</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.example.conflict</groupId>
            <artifactId>modern-client</artifactId>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Để ý thứ tự:** legacy-client được khai báo trước modern-client. Cả hai nhánh formatter sâu **2 cạnh** tính từ app, vậy v1 thắng theo **first declaration wins**.

App **không có direct formatter dependency**, **không có dependencyManagement** và không chứa một import BOM nào. Điều đó giúp nhìn thấy dependency mediation mặc định một cách không bị yếu tố quản lý phụ thuộc khác che mất.

**Không đổi version hoặc thứ tự** ở bước này; cần quan sát kết quả lỗi trước.

## 16. demo-app: source Main.java đầy đủ

Tạo `demo-app/src/main/java/org/example/app/Main.java`:

~~~java
package org.example.app;

import org.example.legacy.LegacyClient;
import org.example.modern.ModernClient;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(LegacyClient.render("Maven"));
        System.out.println(ModernClient.render("Maven"));
    }
}
~~~

App chỉ gọi **API của hai clients**, không import trực tiếp `Formatter`. Do đó Java compiler không nhất thiết cần kiểm method `decorateLoud` trong bytecode của modern-client để biên dịch app's `Main`. Một project có thể build JAR thành công trước khi runtime class loading/linkage chạm đến phương thức thiếu.

Đây không phải executable JAR: POM không tạo manifest `Main-Class` và cũng không gói dependencies. Bài chạy bằng `java -cp` với `target/classes` và các runtime JARs đã được copy riêng.

## 17. Build và install đúng thứ tự vào cache chung

Trên **Bash/Linux/macOS**, đứng tại thư mục root `maven-version-conflict`, với biến `REPO` từ mục 6:

~~~bash
mvn -B -ntp -Dmaven.repo.local="$REPO" -f formatter-v1/pom.xml clean install
mvn -B -ntp -Dmaven.repo.local="$REPO" -f formatter-v2/pom.xml clean install
mvn -B -ntp -Dmaven.repo.local="$REPO" -f legacy-client/pom.xml clean install
mvn -B -ntp -Dmaven.repo.local="$REPO" -f modern-client/pom.xml clean install
~~~

Mỗi lệnh phải kết thúc thành công trước khi chuyển sang lệnh sau. Thứ tự có ý nghĩa:

- V1 và V2 được install với hai versions vào cùng local repository.
- Legacy-client compile với dependency v1.
- Modern-client compile với dependency v2.
- App sau đó có thể resolve cả hai clients và các transitive dependencies tương ứng.

Nếu bạn chạy `modern-client install` trước khi `formatter-v2 install`, có thể xuất hiện `Could not find artifact org.example.conflict:formatter-core:2.0.0`. Đó là **artifact chưa được install**, không phải kết quả nearest-definition conflict ở app.

### PowerShell trên Windows

Nếu dùng PowerShell, dùng `$repo` đã khai báo:

~~~powershell
mvn -B -ntp "-Dmaven.repo.local=$repo" -f formatter-v1/pom.xml clean install
mvn -B -ntp "-Dmaven.repo.local=$repo" -f formatter-v2/pom.xml clean install
mvn -B -ntp "-Dmaven.repo.local=$repo" -f legacy-client/pom.xml clean install
mvn -B -ntp "-Dmaven.repo.local=$repo" -f modern-client/pom.xml clean install
~~~

Bốn invocation này không được chạy đồng thời lần đầu, vì client có thể hỏi dependency trước khi dependency được install.

## 18. Xác nhận hai versions thực sự đã được install

Đường dẫn dự kiến trong local repository:

~~~text
.demo-m2/org/example/conflict/
├── formatter-core/
│   ├── 1.0.0/
│   │   ├── formatter-core-1.0.0.jar
│   │   └── formatter-core-1.0.0.pom
│   └── 2.0.0/
│       ├── formatter-core-2.0.0.jar
│       └── formatter-core-2.0.0.pom
├── legacy-client/1.0.0/
│   ├── legacy-client-1.0.0.jar
│   └── legacy-client-1.0.0.pom
└── modern-client/1.0.0/
    ├── modern-client-1.0.0.jar
    └── modern-client-1.0.0.pom
~~~

`.pom` của clients là rất quan trọng: nó ghi **dependency phiên bản gốc** mà Maven đọc khi app resolve transitive graph. Nếu chỉ copy các JAR thủ công vào `target` mà không install POMs, bạn không có đầy đủ metadata để tái hiện Maven dependency mediation.

Kiểm trên Bash:

~~~bash
ls "$REPO/org/example/conflict/formatter-core/1.0.0"
ls "$REPO/org/example/conflict/formatter-core/2.0.0"
~~~

Với PowerShell:

~~~powershell
Get-ChildItem (Join-Path $repo "org/example/conflict/formatter-core/1.0.0")
Get-ChildItem (Join-Path $repo "org/example/conflict/formatter-core/2.0.0")
~~~

Nếu thiếu POM/JAR, trở lại đúng producer `mvn install`; không sửa `demo-app/pom.xml` để che lỗi artifact chưa tồn tại.

## 19. Phân tích dependency:tree trước khi chạy

Từ root workspace Bash:

~~~bash
mvn -B -ntp -Dmaven.repo.local="$REPO" -f demo-app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree \
  -Dverbose
~~~

PowerShell một dòng:

~~~powershell
mvn -B -ntp "-Dmaven.repo.local=$repo" -f demo-app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dverbose
~~~

Version plugin `3.8.1` hỗ trợ `verbose=true` để hiển thị các nodes bị omitted do conflict theo khả năng serializer. Cách format/log prefixes có thể khác plugin version, vì vậy đây là **sơ đồ ngữ nghĩa dự kiến**, không phải console log được chép nguyên:

~~~text
org.example.conflict:demo-app:jar:1.0.0
+- org.example.conflict:legacy-client:jar:1.0.0:compile
|  \- org.example.conflict:formatter-core:jar:1.0.0:compile   <-- selected
\- org.example.conflict:modern-client:jar:1.0.0:compile
   \- org.example.conflict:formatter-core:jar:2.0.0:compile   <-- omitted for conflict
~~~

Maven chọn formatter v1 vì **hai nhánh cùng depth và legacy-client đứng trước**. Nếu không dùng `-Dverbose`, nhánh bị loại có thể không xuất hiện rõ, khiến người mới tưởng modern-client không yêu cầu v2.

Để khoanh vùng artifact:

~~~bash
mvn -B -ntp -Dmaven.repo.local="$REPO" -f demo-app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree \
  -Dverbose -Dincludes=org.example.conflict:formatter-core
~~~

`-Dincludes` giới hạn các nodes hiển thị; nếu muốn thấy đầy đủ đường đi từ clients, xem tree không filter trước.

## 20. Build app trước khi sửa: compile được chưa nói lên runtime đúng

Build `demo-app` và copy **chỉ runtime dependencies** vào project target:

~~~bash
mvn -B -ntp -Dmaven.repo.local="$REPO" -f demo-app/pom.xml \
  clean package \
  org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies \
  -DincludeScope=runtime
~~~

Bash có thể copy nhiều dòng như trên; trên PowerShell một dòng:

~~~powershell
mvn -B -ntp "-Dmaven.repo.local=$repo" -f demo-app/pom.xml clean package org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime
~~~

Nếu tất cả producer JARs/POMs đã install, app có thể build thành công dù formatter v1 sẽ gây runtime error. `copy-dependencies` lấy resolved runtime classpath, do đó ở bước này trong `demo-app/target/dependency` dự kiến có:

~~~text
formatter-core-1.0.0.jar
legacy-client-1.0.0.jar
modern-client-1.0.0.jar
~~~

V2 JAR có thể vẫn **tồn tại trong local repository** nhưng **không nằm trong resolved app runtime copy**. Đây là ranh giới giữa “artifact đã download” và “artifact được chọn cho project”.

Cần chạy `clean package` trước `copy-dependencies` để tránh file formatter v2 còn dư từ lần chạy trước trong `target/dependency` làm demo khó xác định.

## 21. Chạy app trước khi sửa: thấy NoSuchMethodError

Bash/Linux/macOS từ workspace root:

~~~bash
java -cp "demo-app/target/classes:demo-app/target/dependency/*" \
  org.example.app.Main
~~~

PowerShell/CMD trên Windows:

~~~powershell
java -cp "demo-app\target\classes;demo-app\target\dependency\*" org.example.app.Main
~~~

Lời gọi thứ nhất dùng API cũ có ở formatter v1. **Dòng stdout được mong đợi trước khi chương trình lỗi:**

~~~text
legacy=Hello, Maven
~~~

Sau đó JVM sẽ ném lỗi tương tự:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String org.example.conflict.Formatter.decorateLoud(java.lang.String)'
~~~

Phần trên là **trích ý chính minh họa**. Stack trace và số dòng `.java` thực tế tùy file, JDK và môi trường; không bịa trọn stack trace. Process Java có exit status khác 0. Đừng gọi đây là một test đã được chạy thực tế trong workspace của người học — đây là **kết quả dự kiến theo bytecode và dependency graph**.

Vì sao xảy ra? `ModernClient.class` được compile với `Formatter.decorateLoud` của version 2, nhưng Java runtime classpath chỉ chứa `Formatter.class` từ formatter-core **1.0.0**, không có method ấy.

Đây là **binary compatibility** failure, không phải Maven không biết compile Java.

## 22. Kiểm đúng JAR/class bằng JDK tools

Để kiểm method signature trong từng formatter JAR, dùng `javap` — lệnh chỉ phân tích class, không sửa artifacts:

~~~bash
javap -classpath "$REPO/org/example/conflict/formatter-core/1.0.0/formatter-core-1.0.0.jar" \
  org.example.conflict.Formatter
~~~

Với V2:

~~~bash
javap -classpath "$REPO/org/example/conflict/formatter-core/2.0.0/formatter-core-2.0.0.jar" \
  org.example.conflict.Formatter
~~~

Nội dung liên quan dự kiến:

~~~text
V1: public static java.lang.String decorate(java.lang.String);
V2: public static java.lang.String decorate(java.lang.String);
V2: public static java.lang.String decorateLoud(java.lang.String);
~~~

Đây là **mô tả dòng phương thức**, không phải toàn bộ output `javap`; công cụ còn hiển thị class constructor, flags theo JDK.

Cũng có thể xem files mà `copy-dependencies` tạo, hoặc dùng `jar tf`:

~~~bash
jar tf "$REPO/org/example/conflict/formatter-core/1.0.0/formatter-core-1.0.0.jar"
~~~

Cần bảo đảm JAR chứa `org/example/conflict/Formatter.class`, không có class bị relocate/shade ngoài mong muốn. **Nếu runtime classpath có nhiều JARs cùng chứa Formatter.class** do fat-JAR/shading hoặc copy tệp cũ, lỗi có thể khác và cần phân tích class loading riêng; bài demo tránh điều đó bằng `clean` và chỉ một resolved formatter JAR.

## 23. Bước sửa chính: thêm dependencyManagement tại app

Không sửa POM của legacy-client/modern-client. Chỉ mở `demo-app/pom.xml` và **chèn một khối** vào **trực tiếp dưới `<project>`**, ví dụ sau `<properties>` và **trước `<dependencies>`**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.conflict</groupId>
            <artifactId>formatter-core</artifactId>
            <version>2.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Vì app nhận formatter-core **bắc cầu** qua clients, khối này giúp quản lý version về **2.0.0** tại project consumer. Đây là bài học trọng tâm: **không cần thay đổi POM của hai thư viện đã publish**, nhưng app chọn một runtime version thỏa API của cả hai, nhờ v2 còn giữ phương thức v1.

Không thêm `formatter-core` vào `<dependencies>` chỉ để “đảm bảo plugin thấy”: điều đó sẽ là **direct dependency**, một cơ chế khác; ta muốn minh họa rõ `dependencyManagement`.

### Git diff mong đợi

~~~diff
 <properties>
     <maven.compiler.release>17</maven.compiler.release>
     <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
 </properties>
+
+<dependencyManagement>
+    <dependencies>
+        <dependency>
+            <groupId>org.example.conflict</groupId>
+            <artifactId>formatter-core</artifactId>
+            <version>2.0.0</version>
+        </dependency>
+    </dependencies>
+</dependencyManagement>

 <dependencies>
~~~

Đoạn diff là **mô phỏng cấu hình cần chèn**, không phải Git output đã chạy. Dữ liệu `groupId/artifactId/version` phải khớp tọa độ formatter-core trong hai clients.

## 24. App POM hoàn chỉnh sau khi sửa

Để tránh đặt nhầm vị trí XML, đây là **toàn bộ `demo-app/pom.xml` sau sửa**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.conflict</groupId>
    <artifactId>demo-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.example.conflict</groupId>
                <artifactId>formatter-core</artifactId>
                <version>2.0.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.example.conflict</groupId>
            <artifactId>legacy-client</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.example.conflict</groupId>
            <artifactId>modern-client</artifactId>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tất cả những thứ khác giữ nguyên: version app, thứ tự clients, source files. So sánh baseline và after: **chỉ khối `<dependencyManagement>` được thêm**. Đây là cách chứng minh nhân quả, tránh đồng thời đổi nhiều yếu tố.

Nếu một parent POM đã có `dependencyManagement` với formatter version khác, phiên bản quản lý ở child có precedence theo Maven rules; luôn kiểm effective POM của project thực tế.

## 25. Build lại, kiểm dependency tree và output sau khi sửa

Bash từ root, giữ nguyên biến `REPO`:

~~~bash
mvn -B -ntp -Dmaven.repo.local="$REPO" -f demo-app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree \
  -Dverbose
~~~

Tree ngữ nghĩa sau sửa:

~~~text
demo-app
+- legacy-client:1.0.0
|  \- formatter-core:2.0.0   (managed from 1.0.0)
\- modern-client:1.0.0
   \- formatter-core:2.0.0  (other path may be omitted as duplicate)
~~~

**Đây là sơ đồ minh họa**, không cam kết bản text của `dependency:tree` hiển thị đúng từng chú thích trong ngoặc. Điều phải kiểm là **resolved formatter-core version 2.0.0**, không còn chọn v1 cho runtime.

Sau đó build sạch và copy classpath:

~~~bash
mvn -B -ntp -Dmaven.repo.local="$REPO" -f demo-app/pom.xml \
  clean package \
  org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies \
  -DincludeScope=runtime
~~~

Tệp runtime cần có:

~~~text
demo-app/target/dependency/formatter-core-2.0.0.jar
demo-app/target/dependency/legacy-client-1.0.0.jar
demo-app/target/dependency/modern-client-1.0.0.jar
~~~

Không nên còn `formatter-core-1.0.0.jar` ở `target/dependency` sau `clean` nếu đúng plugin/version/scope và không có thao tác copy khác.

Chạy Bash:

~~~bash
java -cp "demo-app/target/classes:demo-app/target/dependency/*" \
  org.example.app.Main
~~~

Stdout **mong đợi, chính xác hai dòng**:

~~~text
legacy=Hello, Maven
modern=Hello, MAVEN!
~~~

Cả clients hoạt động vì formatter v2 hỗ trợ **cả `decorate` và `decorateLoud`**. Java process kết thúc bình thường khi không có lỗi môi trường khác.

### Windows PowerShell tương đương

~~~powershell
mvn -B -ntp "-Dmaven.repo.local=$repo" -f demo-app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dverbose
mvn -B -ntp "-Dmaven.repo.local=$repo" -f demo-app/pom.xml clean package org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime
java -cp "demo-app\target\classes;demo-app\target\dependency\*" org.example.app.Main
~~~

Windows dùng dấu `;` trong classpath separator, Unix dùng dấu `:`. Trong Java launcher, wildcard classpath `*` mở rộng đến các JARs trong thư mục, không phải shell glob expansion; nên quote nguyên classpath.

## 26. Kiểm tra mạnh hơn bằng một test JUnit sau khi sửa

Một thực hành đáng tin không dừng ở việc chạy Main bằng tay. Với project app sau fix, bổ sung **test dependency** vào `<dependencies>`:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
~~~

Trong `<build><plugins>` thêm:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
</plugin>
~~~

Tạo `demo-app/src/test/java/org/example/app/CompatibilityTest.java`:

~~~java
package org.example.app;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.example.legacy.LegacyClient;
import org.example.modern.ModernClient;
import org.junit.jupiter.api.Test;

class CompatibilityTest {

    @Test
    void bothClientsWorkWithSelectedFormatter() {
        assertEquals(
            "legacy=Hello, Maven",
            LegacyClient.render("Maven"));
        assertEquals(
            "modern=Hello, MAVEN!",
            ModernClient.render("Maven"));
    }
}
~~~

Chạy với app đã thêm dependencyManagement:

~~~bash
mvn -B -ntp -Dmaven.repo.local="$REPO" -f demo-app/pom.xml clean verify
~~~

**Kết quả kỳ vọng:** một JUnit test method với hai assertions pass. Nếu bỏ `dependencyManagement` trong app mà vẫn giữ test này, JUnit có thể báo `NoSuchMethodError` khi gọi modern-client. Đây là một **regression test** rất trực tiếp cho mâu thuẫn phiên bản.

**Lưu ý:** đây là **bước mở rộng tùy chọn** sau phần runnable chính; baseline POM ở mục 15 chưa có JUnit. Không gọi lệnh `mvn test` ở baseline rồi khẳng định đã có test nếu chưa thêm dependency/file như trên.

## 27. dependencyManagement không thêm dependency — minh họa phản chứng

Nếu bạn bỏ **cả hai** clients khỏi `demo-app/pom.xml`, nhưng vẫn giữ:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.conflict</groupId>
            <artifactId>formatter-core</artifactId>
            <version>2.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Maven **không tự đưa formatter-core vào classpath** chỉ vì entry xuất hiện trong management. Hãy phân biệt:

- `<dependencies>`: khai báo artifact project cần (trực tiếp) và bắt đầu transitive traversal.
- `<dependencyManagement>`: định nghĩa version/scope/exclusions khi artifact xuất hiện theo dependency graph, không tạo dependency edge mới.
- `<pluginManagement>`: quản lý cấu hình plugin, **không đồng nghĩa build plugin được chạy tự động**.
- `<build><plugins>`: khai báo plugin có thể tham gia lifecycle hoặc invocation.

Trong ví dụ thật, formatter-core có mặt vì **legacy-client** và **modern-client** đều phụ thuộc nó. Management chỉ điều chỉnh **version được chọn**.

## 28. Phương án khác: direct dependency và giới hạn của nó

Thay vì dependencyManagement, app có thể khai báo formatter v2 là một **direct dependency**:

~~~xml
<dependency>
    <groupId>org.example.conflict</groupId>
    <artifactId>formatter-core</artifactId>
    <version>2.0.0</version>
</dependency>
~~~

Khi formatter-core xuất hiện trực tiếp ở depth 1, Maven chọn v2 thay cho các nhánh transitives ở depth 2 theo **nearest definition**.

**Khi nào hợp lý?** Nếu **mã nguồn app trực tiếp import và dùng Formatter**, việc khai báo direct dependency tuân thủ nguyên tắc “declare what you use”.

**Khi nào dependencyManagement hợp lý hơn?** Nếu app không import Formatter mà muốn **chọn thống nhất transitive version** cho nhiều clients/modules. Khi đó `dependencyManagement` mô tả policy version mà không giả vờ app trực tiếp dùng API này.

Không khai cả direct pin và management một cách vô thức. Có thể dùng cả hai khi app thực sự sử dụng library trực tiếp và muốn quản lý transitive versions, nhưng cần giải thích mục đích từng phần.

## 29. Thử đổi thứ tự hai clients: vì sao không nên dùng làm “giải pháp”

Trong POM trước sửa, nếu khai `modern-client` **trước** `legacy-client`, hai formatter paths vẫn cùng depth nhưng version v2 có thể thắng do **first declaration wins**. Với v2 tương thích ngược của demo, app sẽ chạy.

Tuy nhiên đây **không phải chính sách version bền vững**:

- Người khác có thể đổi thứ tự dependencies khi cleanup POM.
- Parent/BOM hoặc một dependency path ngắn hơn có thể thay kết quả.
- Dependencies mới có thể thêm những nhánh version khác.
- `dependency:tree` sẽ thay theo tình huống, CI có thể phụ thuộc thứ tự khó thấy.
- Một bản v2 **không tương thích ngược** có thể vẫn làm legacy-client lỗi.

Khi giải quyết một version conflict thực, hãy đặt **explicit version policy** ở `dependencyManagement`/BOM hoặc khai báo direct dependency khi dùng trực tiếp, rồi có **regression tests**.

## 30. Maven Enforcer: bắt conflict trước khi chạy production

Maven Enforcer Plugin cung cấp các rules khác nhau:

| Rule | Kiểm gì? | Liên quan bài demo |
| --- | --- | --- |
| `dependencyConvergence` | Các đường dependency yêu cầu một artifact cần hội tụ version theo rule. | Có thể phát hiện hai nhánh 1.0.0 và 2.0.0 trước/sau các kiểu quản lý. |
| `requireUpperBoundDeps` | Phiên bản được resolve phải không thấp hơn các yêu cầu transitive theo cách rule phân tích. | Cảnh báo nếu chọn v1 nhưng có nhánh yêu cầu v2. |
| `bannedDependencies` | Cấm một số GAV/versions/scopes theo policy. | Chặn formatter v1 nếu repo policy không cho. |
| `requireJavaVersion` | Xác minh JDK Maven đang chạy. | Bảo vệ build Java17. |
| `requireMavenVersion` | Xác minh Maven runtime version. | Hạn chế Maven versions không hỗ trợ. |

Một **mảnh cấu hình có thể thêm vào `<build><plugins>` của app**:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.6.3</version>
    <executions>
        <execution>
            <id>dependency-guardrails</id>
            <phase>validate</phase>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireUpperBoundDeps/>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

**Đây là bước tùy chọn**. Nếu thêm rule vào POM **trước khi demo lỗi runtime**, Maven có thể fail ở `validate` và không tới bước `package`. Điều đó có giá trị cho CI production, nhưng muốn quan sát `NoSuchMethodError` trong bài thực hành thì chạy demo nền trước rồi mới bật guardrail.

### Về dependencyConvergence

`dependencyConvergence` nghiêm hơn một việc “Maven đã chọn đúng version”: nếu hai thư viện khai báo version khác nhau, rule có thể yêu cầu **đồng bộ các declarations/exclusions**, không chỉ ép một resolved version theo mọi tình huống. Đọc output thực tế và tài liệu rule; không khẳng định `dependencyManagement` luôn làm mọi convergence rule pass trong tất cả graphs.

`requireUpperBoundDeps` cũng không chứng minh v2 tương thích API. Nó giúp phát hiện **selected version quá thấp**, nhưng không thay integration tests.

## 31. Multi-module và quản lý version ở parent POM

Nếu một repo thực có cấu trúc:

~~~text
parent/
├── pom.xml
├── service-api/pom.xml
├── service-core/pom.xml
└── service-web/pom.xml
~~~

Khi nhiều modules dùng formatter-core bắc cầu, có thể đặt management ở **parent POM**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.conflict</groupId>
            <artifactId>formatter-core</artifactId>
            <version>2.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Để có tác dụng, child POMs **phải kế thừa** parent đó hoặc nhập BOM chứa quản lý tương ứng; chỉ khai `<modules>` aggregate không có nghĩa mọi module tự kế thừa dependencyManagement.

Nếu parent đã quản lý version và child khai management riêng cùng tọa độ, Maven dùng precedence theo effective POM, cần kiểm child thực. Đừng copy version v2 vào từng POM nếu mục tiêu là một nguồn sự thật duy nhất và nhiều modules cần cùng policy.

Các lệnh `mvn -pl :service-web -am verify` chỉ áp dụng nếu project thật có reactor modules phù hợp; **không chạy** trên workspace demo năm POM độc lập ở bài này.

## 32. BOM và import scope: quản lý một tập phiên bản

Với hệ thống có hàng trăm dependencies, một BOM POM là cách phát hành tập version policy:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.platform</groupId>
    <artifactId>example-bom</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.example.conflict</groupId>
                <artifactId>formatter-core</artifactId>
                <version>2.0.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

Đây là **một ví dụ BOM độc lập**, không nằm trong năm project runnable trừ khi bạn tạo/publish nó. Consumer sẽ import POM BOM bằng:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.platform</groupId>
            <artifactId>example-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`type=pom` và `scope=import` là điều kiện cho BOM import trong `dependencyManagement`, không phải dependency runtime bình thường.

BOM phải được **resolve** từ local/remote repository; chưa install example-bom mà app import thì Maven có thể báo `Non-resolvable import POM`. Trong thực hành chính, dùng management trực tiếp ở app để không thêm project thứ sáu.

## 33. Scope, exclusions và optional có làm conflict biến mất không?

Một vài controls khác có thể ảnh hưởng graph:

- `scope=compile` (mặc định) khiến client dependency có thể truyền transitive dependency vào app compile/runtime.
- `scope=runtime` dùng cho dependencies cần khi chạy chứ không compile app, nhưng phải đúng nhu cầu code.
- `scope=test` giới hạn tới test classpath; không nên dùng để che lỗi production.
- `optional=true` ở producer có thể ngăn transitive dependency được kéo tự động tới consumer, nhưng consumer cần khai lại nếu code cần. Không dùng như hack “tắt xung đột”.
- `<exclusions>` trên một dependency edge có thể cắt một nhánh transitive; cắt nhầm có thể khiến runtime thiếu class.
- `provided` và `system` có semantics/classpath khác; không thay version management.

Ví dụ một **exclusion fragment** trên dependency modern-client:

~~~xml
<dependency>
    <groupId>org.example.conflict</groupId>
    <artifactId>modern-client</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.example.conflict</groupId>
            <artifactId>formatter-core</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Nếu app chỉ còn nhánh legacy kéo formatter v1, **NoSuchMethodError vẫn có thể xảy ra**. Exclusion không tự chọn một compatible formatter. Phải bổ sung đúng direct/managed version theo nhu cầu.

**Không coi exclusion là thuốc chữa tổng quát**: nó thay đường đi graph, có thể làm thiếu thư viện và che vấn đề compat thay vì giải quyết.

## 34. Dependency management không điều khiển classpath của Maven plugins

Maven có **nhiều classpaths**:

~~~text
Application compile classpath
Application runtime classpath
Application test classpath
Maven build plugin classpaths (tách biệt ứng dụng)
Maven core/extensions classloaders
~~~

`<dependencyManagement>` trong `demo-app` quản lý **project dependencies**. Nó **không tự ép** Maven Compiler Plugin hay Surefire Plugin dùng `formatter-core:2.0.0` trong dependencies riêng của plugin.

Nếu plugin có conflict, cần xem `<build><plugins><plugin><dependencies>`/pluginManagement và plugin version compatibility; không xem mỗi `dependency:tree` của app rồi suy rằng toàn bộ Maven JVM chỉ có một version của mọi artifact.

Cũng không nên sửa `~/.m2/repository` thủ công để “buộc cả Maven plugins dùng version mới”; điều đó gây cache inconsistency.

## 35. Khi version mới không tương thích ngược

Bài demo cố ý giữ `Formatter.decorate` trong v2. Nhưng thử tưởng tượng v2 **xóa phương thức đó** hoặc đổi từ `static` sang instance. Khi dependencyManagement chọn v2, modern-client có thể chạy nhưng legacy-client lại gây `NoSuchMethodError`/`IncompatibleClassChangeError`.

Trường hợp ấy **không có phiên bản duy nhất đơn giản** thỏa cả hai binary clients. Lựa chọn thực tế:

1. Nâng legacy-client lên version mới tương thích với formatter v2.
2. Chọn một version formatter có API superset và có support policy.
3. Nâng đồng bộ BOM/platform modules và rebuild clients theo API mới.
4. Nếu không thể, tách classloader/process/service boundary thay vì ép cả hai vào cùng package classpath.
5. Trong một số kiến trúc được quản lý, Shade relocation có thể tránh duplicate package clashes, nhưng phải hiểu service loaders/reflection/resources và không áp dụng mù.
6. Viết regression tests ở app/integration/consumer runtime.

**Không kết luận “dùng phiên bản cao nhất luôn đúng”**. Version lớn hơn thường chứa features mới nhưng có thể breaking changes, minimum JDK mới, license changes hoặc security regressions. Chọn version theo **compatibility contract**, advisories, runtime tests và support policy.

## 36. Dependency tree, bytecode và runtime classpath phải khớp

Một checklist kiểm ba tầng:

| Tầng | Kiểm gì? | Công cụ |
| --- | --- | --- |
| Declaration | Các POM của clients yêu cầu version nào? | Mở producer POMs, `help:effective-pom`. |
| Resolution | App thực sự chọn formatter version nào? | `dependency:tree -Dverbose`, `dependency:build-classpath`. |
| Bytecode | Client gọi method có chữ ký nào? | `javap -c`/`javap` trên JARs. |
| Runtime | JVM thực sự nạp JAR/class nào? | Inspect `target/dependency`, runtime smoke test. |
| Policy | Graph có conflict/upper-bound violations không? | Maven Enforcer. |
| Build | Tests và packaging có đồng nhất? | Maven verify, JUnit/Failsafe, consumer smoke. |

Cũng có thể dùng Dependency Plugin `build-classpath` để ghi classpath ra file:

~~~bash
mvn -B -ntp -Dmaven.repo.local="$REPO" -f demo-app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath \
  -Dmdep.outputFile=demo-runtime-classpath.txt
~~~

Tùy current working directory, output file path và plugin parameter semantics, hãy đọc file thực để kiểm. Không in raw machine paths/secrets trong public logs. Một classpath có v2 không bảo đảm không có duplicate class trong fat-JAR khác; kiểm classloader nếu trường hợp phức tạp.

## 37. Lỗi thường gặp trong quá trình tái hiện

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Could not find artifact formatter-core:2.0.0` | Chưa install v2 hoặc dùng nhầm local repo. | Install formatter-v2 bằng cùng `REPO`. |
| `legacy-client` compile fail | Formatter v1 chưa install hoặc class/package sai. | Install v1; kiểm `Formatter.java`. |
| `modern-client` compile fail ở `decorateLoud` | Compile với v1 do POM/cache/config sai. | Kiểm modern POM version 2 và resolved graph. |
| `demo-app` compile fail không tìm client | Chưa install legacy/modern hoặc tọa độ sai. | Build/install hai client POMs. |
| App build success nhưng chạy lỗi `NoSuchMethodError` | V1 selected ở runtime. | `dependency:tree` và management pin v2. |
| `NoClassDefFoundError: org/example/conflict/Formatter` | Runtime classpath không có formatter JAR. | Kiểm copy-dependencies/classpath separator. |
| Sau fix tree vẫn v1 | Management đặt nhầm nơi, typo GAV hoặc direct version ghi đè. | Kiểm app POM/effective-pom. |
| Tree v2 nhưng runtime vẫn v1 | `target/dependency` chứa JAR cũ, fat-JAR hoặc path khác. | `clean package copy-dependencies`, inspect JARs. |
| Windows `java -cp` không chạy | Dùng separator `:` thay vì `;` hoặc quote sai. | Dùng classpath PowerShell một dòng. |
| `ClassNotFoundException: Main` | Sai main package/classpath target/classes. | Kiểm `org.example.app.Main` và Java path. |
| Maven Enforcer chặn build trước runtime | Đã bật upper-bound rule sớm. | Demo baseline trước; giữ rule ở CI production. |
| JUnit tests không chạy | Chưa thêm test dependencies/Surefire/test file. | Làm mục 26, kiểm Surefire reports. |
| POM BOM import fail | BOM chưa publish hoặc type/scope sai. | Install/publish BOM, `type=pom`/`scope=import`. |
| Mâu thuẫn vẫn còn sau exclusion | Cắt nhánh không đồng nghĩa chọn version mới. | Review resolved graph và compat. |
| Build ở laptop được nhưng CI fail | Local artifacts chỉ `install`, CI chưa có. | Publish libs vào approved repo hoặc build đúng reactor. |
| Unsupported class file version | JDK runtime < bytecode Java17. | Chạy JDK17+ hoặc recompile với target được support. |
| v2 không tương thích API v1 | Method cũ bị xóa/đổi. | Upgrade clients/choose compatible API; test. |
| Duplicate class ở hai artifacts khác GAV | Maven mediation không áp dụng cho khác tọa độ. | Kiểm duplicate classes/shading policy. |

**Đường debug chuẩn:** nguồn POM → Maven effective dependencies → runtime JARs → Java class linkage → regression tests. Đừng bắt đầu bằng xóa toàn bộ `~/.m2` hoặc ép `-U`; hai thao tác đó không đổi quy tắc nearest-definition.

## 38. Checklist hoàn thành bài thực hành

- [ ] Đã xác minh Maven 3.9.x và JDK17+.
- [ ] Tạo đúng 5 project độc lập với `groupId/artifactId/version` đã cho.
- [ ] Formatter v1 chỉ có `decorate(String)`.
- [ ] Formatter v2 giữ `decorate(String)` và thêm `decorateLoud(String)`.
- [ ] Legacy client compile với formatter v1.
- [ ] Modern client compile với formatter v2.
- [ ] Cả bốn libraries được install vào **cùng local repo `REPO`**.
- [ ] App POM ban đầu khai legacy trước modern và **không có dependencyManagement**.
- [ ] `dependency:tree -Dverbose` trước sửa cho thấy formatter 1 được chọn.
- [ ] App packaging trước sửa hoàn tất; runtime báo `NoSuchMethodError` đúng method mới.
- [ ] Không dùng thêm formatter JAR v2 thủ công vào classpath để che conflict.
- [ ] Chèn đúng `dependencyManagement` formatter-core v2 vào app POM.
- [ ] Đọc lại effective POM và dependency tree sau sửa: resolved formatter v2.
- [ ] Chạy `clean package copy-dependencies` để tránh JAR cũ.
- [ ] Java Main in đúng hai dòng, không còn runtime error.
- [ ] Nếu thêm JUnit ở mục 26, test cả hai clients pass.
- [ ] Nếu bật Enforcer, đã đánh giá rules và output thực tế.
- [ ] Hiểu management không thêm dependency và không tác động Maven plugin classpath.
- [ ] Hiểu direct dep vs transitive version pin vs BOM vs exclusion.
- [ ] Hiểu nếu v2 làm mất API v1 thì ép v2 cũng không an toàn.
- [ ] Có kế hoạch source dependency version alignment và regression tests trong CI.

## 39. Câu hỏi tự kiểm tra

1. **Một artifact trong app có hai transitive versions thì Maven mặc định chọn thế nào?** Dựa nearest-definition; cùng depth thì first declaration wins.
2. **Tại sao trong demo v1 thắng dù modern-client dùng v2?** Hai nhánh cùng depth, legacy khai trước.
3. **Tại sao app compile được nhưng runtime lỗi?** App compile qua API của clients; modern-client bytecode cần phương thức chỉ có trong v2 nhưng runtime chọn v1.
4. **Lỗi runtime trong demo là gì?** `NoSuchMethodError` khi gọi `Formatter.decorateLoud(String)`.
5. **`dependencyManagement` có tự kéo formatter vào app nếu không ai phụ thuộc nó không?** Không.
6. **Đặt formatter version 2.0.0 ở app's dependencyManagement làm gì?** Quản lý version formatter trên các transitive paths trước mediation.
7. **Đổi thứ tự clients cho v2 thắng có phải fix bền vững?** Không; phụ thuộc POM order và future graph.
8. **Direct formatter dependency v2 khác management như thế nào?** Nó thêm direct edge (và version) trong graph; management không thêm edge.
9. **Có phải version lớn nhất luôn binary-compatible?** Không; major/minor cũng có thể breaking.
10. **Maven dependency tree hiển thị v1 là vì v2 không install?** Không; v2 có thể đã install nhưng bị conflict omission.
11. **`-Dverbose` của Dependency Plugin có ích gì?** Hiển thị omitted nodes để thấy các phiên bản thua mediation.
12. **`copy-dependencies -DincludeScope=runtime` được dùng để làm gì?** Copy resolved runtime dependencies, tránh tự dựng classpath sai.
13. **Vì sao phải chạy clean khi thử lại?** Tránh một JAR formatter cũ còn trong target/dependency.
14. **`dependencyConvergence` khác `requireUpperBoundDeps` như thế nào?** Một rule muốn paths hội tụ, rule kia kiểm selected upper bound.
15. **`dependencyManagement` có ép version thư viện bên trong Maven Compiler Plugin không?** Không; plugin classpath riêng.
16. **Nếu v2 xóa `decorate(String)`, chọn v2 có sửa mọi thứ không?** Không; legacy-client có thể bị lỗi, cần upgrade/align clients.
17. **CI có chạy được khi libs chỉ install vào laptop dev không?** Không; CI cần artifact ở registry/cùng build.
18. **Khi nào dùng BOM?** Khi cần quản lý một tập versions cho nhiều modules/projects.
19. **Dùng exclusion để xóa nhánh v2 có bảo đảm runtime được fix không?** Không; nó có thể chỉ giữ v1 và làm modern-client lỗi.
20. **Điều kiện kết luận đã sửa triệt để?** Resolved tree đúng, runtime bytes đúng, clients cùng chạy và regression tests phù hợp.

## 40. Tài liệu chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): nearest definition, first declaration, transitive dependencies và precedence của dependencyManagement.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): `dependencies`, `dependencyManagement`, scopes, exclusions và BOM.
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): local/remote artifacts và vai trò `install`/`deploy`.
- [Apache Maven — Repository Layout](https://maven.apache.org/repositories/layout.html): mapping groupId/artifactId/version thành directories.
- [Apache Maven — Maven Dependency Plugin dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): `-Dverbose`, includes/omitted nodes và serialized graph.
- [Apache Maven — Maven Dependency Plugin copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html): `includeScope=runtime` và thư mục output mặc định.
- [Apache Maven — Maven Dependency Plugin build-classpath](https://maven.apache.org/plugins/maven-dependency-plugin/build-classpath-mojo.html): xem resolved classpath.
- [Apache Maven — Maven Install Plugin](https://maven.apache.org/plugins/maven-install-plugin/): cài local POM/JAR để project khác có thể resolve.
- [Apache Maven — Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/): cấu hình Java release và compile classes.
- [Apache Maven — Maven Enforcer Rule dependencyConvergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html): phát hiện nhiều versions trên các paths.
- [Apache Maven — Maven Enforcer Rule requireUpperBoundDeps](https://maven.apache.org/enforcer/enforcer-rules/requireUpperBoundDeps.html): yêu cầu selected version không thấp hơn transitive bounds.
- [Apache Maven — Maven Enforcer Plugin](https://maven.apache.org/enforcer/maven-enforcer-plugin/): gắn rules vào lifecycle/CI.
- [Apache Maven — Guide to Importing Dependencies (BOM)](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html#bill-of-materials-bom-poms): BOM import với type `pom`/scope `import`.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phases, plugin goals, install và verify.
- [OpenJDK — Java `NoSuchMethodError` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html): liên kết method không tìm thấy tại runtime.
- [Oracle Java Launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): classpath separator/wildcard và Java application launch.

**Kết luận:** Trong Maven, conflict resolution chọn một version theo **độ sâu dependency và thứ tự declaration**, nhưng không tự đảm bảo phiên bản đó tương thích với mọi binary consumer. Bài demo cho thấy cùng formatter-core, hai client được build với versions khác nhau; app chọn v1 và gặp `NoSuchMethodError` dù build có thể thành công. `dependencyManagement` ở app quản lý transitive formatter lên v2 tương thích ngược, sau đó resolved classpath chứa đúng JAR và cả hai clients chạy được. Đừng dùng POM order, exclusions hoặc ép “version mới nhất” thay cho **graph inspection, ABI/API review, runtime smoke và CI regression tests**.
