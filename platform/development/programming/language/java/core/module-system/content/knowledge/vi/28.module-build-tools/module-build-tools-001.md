# Module path trong Maven

Java Platform Module System (JPMS) sử dụng **module path** để tìm các module có tên khi biên dịch, phân giải dependency và khởi chạy ứng dụng. Trong dự án Maven, module path có liên hệ chặt chẽ với **module-info.java**, các dependency trong **pom.xml** và những plugin thực hiện compile, test, package. Hiểu sự phối hợp này giúp tránh lỗi **module not found**, **package is not visible**, xung đột package và lỗi chỉ xuất hiện sau khi đóng gói.

Điểm cốt lõi: **Maven quản lý artifact và build lifecycle**, trong khi **JPMS quản lý module graph và khả năng truy cập giữa các module**. Hai hệ thống bổ trợ nhau nhưng không thay thế nhau.

## 1. Module path khác classpath như thế nào?

Classpath truyền thống cung cấp các JAR/thư mục để class loader tìm class. Khi class được nạp từ classpath, nó thường thuộc **unnamed module** của class loader đó.

Module path cung cấp các JAR hoặc thư mục được Java nhận diện thành **named module**. Java có thể đọc module descriptor, phân giải quan hệ **requires**, kiểm tra package được **exports** và áp dụng các ranh giới JPMS.

| Khía cạnh | Classpath | Module path |
|---|---|---|
| Cách tìm | Tìm class/resource qua các entry | Tìm module theo tên và descriptor |
| Module của class | Thường là unnamed module | Named hoặc automatic module |
| Dependency | Không dựa vào requires | requires trong module-info.java |
| Quyền public API | Chủ yếu theo truy cập Java truyền thống | Cần readability và package được export |
| Lỗi thiếu module | Có thể lộ khi dùng class | Có thể lộ khi phân giải module graph |
| Thư viện JAR cũ | Hoạt động theo classpath | Có thể trở thành automatic module |

Maven có thể truyền các dependency tới công cụ JDK theo cách thích hợp với dự án. Tuy nhiên, việc một artifact tồn tại trong Maven repository **không tự đảm bảo** nó nằm trong module graph lúc chạy.

## 2. Maven module không đồng nghĩa Java module

Trong Maven, “module” thường là **project con của một reactor build**. Ví dụ POM tổng có:

~~~xml
<modules>
    <module>catalog-api</module>
    <module>catalog-app</module>
</modules>
~~~

Hai phần tử trên là hai thư mục project mà Maven sẽ tổ chức build cùng nhau.

Trong JPMS, module là đơn vị có tên được mô tả bởi **module-info.java**:

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

Phân biệt rõ:

- **catalog-api** có thể là Maven artifactId.
- **com.example.catalog.api** là Java module name.
- **Maven dependency** khai báo artifact cần để build.
- **JPMS requires** khai báo module cần được đọc.
- Một Maven project không có module-info.java vẫn có thể là project Java chạy theo classpath.
- Một JAR không có descriptor trên module path có thể trở thành automatic module.

Khi code yêu cầu **requires com.example.catalog.api**, tên được sử dụng là tên Java module thực tế, không nhất thiết là tên artifactId.

## 3. Khi nào Maven Compiler Plugin sử dụng module path?

Một dấu hiệu quan trọng của dự án modular là có file:

~~~text
src/main/java/module-info.java
~~~

Ví dụ:

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
}
~~~

Với JDK hỗ trợ JPMS và phiên bản Maven Compiler Plugin phù hợp, dự án có module-info.java được biên dịch theo ngữ cảnh named module. Plugin hỗ trợ tổ chức các artifact cần thiết cho javac để module graph được phân giải.

Các điều kiện quan trọng:

1. JDK dùng để build phải hỗ trợ JPMS (Java 9 trở lên).
2. Compiler plugin phải hỗ trợ dự án modular.
3. module-info.java nằm đúng vị trí và biên dịch được.
4. Các dependency Maven cần thiết được resolve thành artifact.
5. Tên module trong requires khớp với tên thật của dependency.
6. Package API mà code sử dụng phải được export cho module gọi.

Không nên cho rằng mọi dependency Maven đều tự động ở module path với mọi project. Đường đi thực tế phụ thuộc dự án có modular hay không, plugin, JDK và cấu hình build.

## 4. Ví dụ dự án Maven nhiều module

Một ứng dụng gồm hai phần:

- **catalog-api** chứa contract dùng chung.
- **catalog-app** có main class và sử dụng catalog-api.

Cấu trúc:

~~~text
catalog-parent/
├── pom.xml
├── catalog-api/
│   ├── pom.xml
│   └── src/main/java/
│       ├── module-info.java
│       └── com/example/catalog/api/
│           └── ProductCatalog.java
└── catalog-app/
    ├── pom.xml
    └── src/main/java/
        ├── module-info.java
        └── com/example/catalog/app/
            └── Main.java
~~~

Descriptor API:

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

API:

~~~java
package com.example.catalog.api;

public interface ProductCatalog {
    String findName(String sku);
}
~~~

Descriptor ứng dụng:

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
}
~~~

Main:

~~~java
package com.example.catalog.app;

import com.example.catalog.api.ProductCatalog;

public final class Main {
    public static void main(String[] args) {
        ProductCatalog catalog = sku -> "Product-" + sku;
        System.out.println(catalog.findName("A-100"));
    }
}
~~~

Module app đọc module API qua requires. Module API export package chứa ProductCatalog. Đây là hai điều kiện độc lập: có quan hệ đọc và package được công khai.

## 5. Cấu hình POM tổng

File **catalog-parent/pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>catalog-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>catalog-api</module>
        <module>catalog-app</module>
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
                    <version>3.14.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.4</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

Cấu hình này minh họa các ý tưởng:

- **packaging=pom** giúp project tổng làm parent/aggregator.
- **modules** liệt kê project con của Maven reactor.
- **maven.compiler.release=17** yêu cầu compilation cho nền tảng Java 17.
- **maven-compiler-plugin** là plugin biên dịch source.
- **maven-surefire-plugin** dùng khi chạy unit test.
- **pluginManagement** thống nhất version/config của plugin được sử dụng qua lifecycle hoặc khai báo trong project con.

Các phiên bản plugin là ví dụ cấu hình. Trong dự án thực, hãy cố định phiên bản đã được nhóm kiểm thử và cập nhật có kiểm soát thay vì để plugin version thay đổi ngầm.

## 6. POM của catalog-api

File **catalog-api/pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>catalog-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>catalog-api</artifactId>
    <packaging>jar</packaging>
</project>
~~~

Source chứa **module-info.java**, nên output compile sẽ có **module-info.class**. Trong JAR modular, file này xuất hiện ở phần gốc của JAR và xác định module name.

Maven không tự đặt Java module name bằng artifactId. Trong ví dụ, module name được lấy từ descriptor **com.example.catalog.api**.

## 7. POM của catalog-app và dependency Maven

File **catalog-app/pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>catalog-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>catalog-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>catalog-api</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
~~~

Trong app tồn tại hai khai báo bổ trợ:

POM cung cấp artifact:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>catalog-api</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Module descriptor cung cấp quan hệ đọc:

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
}
~~~

Khai báo dependency Maven mà không có requires có thể chưa đủ để code của named module sử dụng public API từ named module khác. Ngược lại, nếu có requires nhưng POM không cung cấp dependency cho compiler, lỗi **module not found** có thể xuất hiện.

## 8. Build các Maven modules trong reactor

Đứng tại thư mục **catalog-parent**:

~~~bash
mvn clean compile
~~~

Maven reactor xây dựng các project con theo quan hệ dependency. Trong ví dụ, catalog-api được build trước catalog-app.

Output:

~~~text
catalog-api/target/classes/
├── module-info.class
└── com/example/catalog/api/ProductCatalog.class

catalog-app/target/classes/
├── module-info.class
└── com/example/catalog/app/Main.class
~~~

Muốn build riêng ứng dụng và các dependency của nó trong reactor:

~~~bash
mvn -pl catalog-app -am clean package
~~~

- **-pl catalog-app** chọn Maven project.
- **-am** thêm các project trong reactor mà project được chọn phụ thuộc.
- **clean package** xóa output cũ, compile rồi tạo JAR.

Chỉ chạy **mvn -pl catalog-app package** có thể thất bại nếu dependency catalog-api chưa có sẵn ở local repository và không được build trong cùng invocation.

Tùy chọn **-pl** sử dụng Maven reactor project selector, **không phải** Java module name dùng sau **--module**.

## 9. Đóng gói và chạy bằng module path

Đóng gói toàn bộ reactor:

~~~bash
mvn clean package
~~~

Ví dụ các artifact:

~~~text
catalog-api/target/catalog-api-1.0.0.jar
catalog-app/target/catalog-app-1.0.0.jar
~~~

Chạy trực tiếp bằng Java launcher:

~~~bash
java --module-path \
     "catalog-api/target/catalog-api-1.0.0.jar:catalog-app/target/catalog-app-1.0.0.jar" \
     --module com.example.catalog.app/com.example.catalog.app.Main
~~~

Java chọn module gốc **com.example.catalog.app**, đọc requires trong module-info.class, rồi phân giải **com.example.catalog.api** từ module path.

Trên Windows, dấu phân cách các phần tử module path là **;**:

~~~powershell
java --module-path "catalog-api\target\catalog-api-1.0.0.jar;catalog-app\target\catalog-app-1.0.0.jar" --module com.example.catalog.app/com.example.catalog.app.Main
~~~

Trên Linux/macOS, dấu phân cách là **:**. Các lệnh trên là ví dụ nhỏ, chỉ đủ khi ứng dụng không có thêm module dependency cần thiết khác.

Khi phát hành, hãy bảo đảm cả runtime dependencies cùng xuất hiện trên module path hoặc các nguồn module phù hợp. Maven repository được sử dụng để build không phải là module path mặc định khi người dùng khởi chạy JAR riêng lẻ.

## 10. Kiểm tra module name trong artifact cuối cùng

Sau khi đóng gói, cần kiểm tra JAR thực tế thay vì suy luận từ tên artifact.

~~~bash
jar --list --file catalog-api/target/catalog-api-1.0.0.jar
~~~

Output kỳ vọng có:

~~~text
module-info.class
com/example/catalog/api/ProductCatalog.class
~~~

Kiểm tra module descriptor:

~~~bash
jar --describe-module --file catalog-api/target/catalog-api-1.0.0.jar
~~~

Kết quả phải thể hiện tên module **com.example.catalog.api** và exported package.

Với app:

~~~bash
jar --describe-module --file catalog-app/target/catalog-app-1.0.0.jar
~~~

Kết quả tương ứng phải chỉ ra **com.example.catalog.app** và dependency **com.example.catalog.api**.

Nếu tên Java module khác tên mà app viết trong requires, compiler hoặc runtime có thể báo lỗi dù Maven dependency đã resolve thành công.

## 11. Automatic module của dependency chưa modular hóa

Không phải thư viện nào trong Maven Central hoặc repository nội bộ cũng có module-info.class.

Ví dụ một JAR cũ:

~~~text
legacy-utils-2.1.jar
└── com/vendor/legacy/Util.class
~~~

Nếu JAR này được đặt trên module path, Java có thể nhận diện nó thành **automatic module**. Tên module có thể đến từ thuộc tính manifest **Automatic-Module-Name** hoặc được suy ra từ tên JAR.

Một descriptor có thể cần:

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
    requires legacy.utils;
}
~~~

Tên **legacy.utils** ở đây chỉ hợp lệ nếu đó thật sự là Java module name của dependency.

Kiểm tra:

~~~bash
jar --describe-module --file path/to/legacy-utils-2.1.jar
~~~

Không nên dùng artifactId làm module name nếu chưa xác minh.

Automatic module hỗ trợ chuyển đổi, nhưng export mọi package và có quy tắc readability rộng hơn named module có descriptor rõ ràng. Nó cũng có thể gây xung đột **split package** với các module khác.

## 12. Maven scope không phải JPMS directive

Maven có các scope như **compile**, **provided**, **runtime** và **test**. Scope xác định artifact cần thiết ở những giai đoạn build/runtime tương ứng.

JPMS lại có các directive như:

~~~java
requires com.example.catalog.api;
requires static com.example.annotations;
requires transitive com.example.shared.api;
~~~

Hai hệ thống giải quyết các vấn đề khác nhau:

- Maven **compile scope** thường cung cấp artifact cho compile và runtime.
- Maven **provided scope** thường có ở compile/test nhưng không mặc định là dependency cần phân phối runtime.
- Maven **runtime scope** phục vụ runtime và test hơn là compile source chính.
- Maven **test scope** dành cho biên dịch/chạy test.
- **requires** yêu cầu dependency module khi compile và runtime resolution.
- **requires static** yêu cầu dependency tại compile time nhưng có thể vắng mặt ở runtime.
- **requires transitive** lan truyền khả năng đọc module cho các module đọc module hiện tại.

Một dependency scope **provided** không khiến Maven tự sinh directive **requires static**. Nhóm phát triển phải thiết kế các khai báo cho nhất quán.

Nếu module descriptor dùng requires bắt buộc nhưng dependency bị loại khỏi runtime, ứng dụng có thể lỗi module resolution ngay khi khởi chạy.

## 13. Cấu hình Maven Compiler Plugin cụ thể

Có thể cấu hình plugin trong build:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Dự án có thể dùng **maven.compiler.release** trong properties hoặc **release** của plugin như hai cách cấu hình cùng ý định.

Không nên tự thêm tham số **--module-path** vào compilerArgs khi compiler plugin đã tổ chức dependency đúng. Làm vậy có thể tạo module path trùng lặp hoặc phụ thuộc một máy cụ thể. Chỉ thêm compilerArgs khi hiểu rõ mục tiêu và tương tác với plugin.

Để kiểm tra cấu hình build:

~~~bash
mvn -X clean compile
~~~

Chế độ debug cho biết thông tin plugin, dependency và quá trình thực hiện compile. Khi lỗi, hãy xác định đó là lỗi Maven artifact resolution hay lỗi JPMS module resolution.

## 14. Module path và unit test bằng Maven Surefire

Trong project modular, test runtime có thể khác compile runtime. Maven Surefire Plugin hỗ trợ các dự án JPMS và cung cấp tùy chọn **useModulePath**.

Ví dụ:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.4</version>
            <configuration>
                <useModulePath>true</useModulePath>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Khi test, cần xét:

- Test classes được tổ chức thành module riêng hay được patch vào module production.
- Framework test và test engine được nạp theo cơ chế nào.
- Module test có đọc được module chứa code cần kiểm thử không.
- Test framework có cần reflection vào package chưa open không.
- Những module trong dependency test có nằm trong cấu hình thực thi test hay không.

Các test framework như JUnit có thể dùng reflection để khám phá test class. Trong JPMS, quyền reflection sâu có thể cần **opens** hoặc cấu hình test phù hợp. Không nên mặc định tắt module path để làm test chạy nếu mục tiêu là kiểm chứng hệ thống modular.

Điều quan trọng là tham số truyền cho javac không tự động xuất hiện trong JVM test mà Maven Surefire khởi chạy. Hãy cấu hình đúng giai đoạn cần sử dụng.

## 15. Các runtime options thường gặp

Trong giai đoạn chuyển đổi JPMS, có thể cần những tùy chọn Java bổ sung:

| Tùy chọn | Mục đích |
|---|---|
| **--add-reads A=B** | Thêm readability từ module A tới B |
| **--add-exports A/p=B** | Cho phép module B truy cập public types trong package p của A |
| **--add-opens A/p=B** | Mở package p của A cho deep reflection từ B |
| **--add-modules M** | Thêm module gốc để phân giải |

Ví dụ khi một framework nằm trên classpath cần truy cập sâu package model của named module:

~~~bash
java --module-path dist/modules \
     --add-opens com.example.catalog.app/com.example.catalog.app.model=ALL-UNNAMED \
     --module com.example.catalog.app/com.example.catalog.app.Main
~~~

Đây là ví dụ cú pháp; chỉ sử dụng khi module/app thật sự có package được nêu và framework cần quyền này. Thay thế tên module/package theo cấu trúc thực tế.

Các tùy chọn trên không thay thế dependency Maven hoặc directive requires. Chúng xử lý quyền và cấu hình riêng của JPMS. Khi có thể, nên giải quyết vấn đề thông qua module descriptor và API được export đúng thay vì duy trì launcher workaround lâu dài.

## 16. Tại sao Maven dependency đã có nhưng javac vẫn lỗi?

Một project có thể khai báo:

~~~xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>legacy-utils</artifactId>
    <version>2.1</version>
</dependency>
~~~

Maven tìm được JAR, nhưng Java compiler còn quan tâm:

1. JAR thuộc classpath hay module path?
2. Java module name của JAR là gì?
3. module-info.java có requires đúng tên đó không?
4. Package muốn sử dụng có được export không?
5. Có xung đột package giữa các module không?

Vì thế, lỗi **package is not visible** hoặc **module not found** không nhất thiết được giải quyết bằng việc thêm lại cùng dependency trong pom.xml.

Một quy trình chẩn đoán hữu ích:

~~~bash
mvn dependency:tree
jar --describe-module --file path/to/dependency.jar
mvn -X compile
~~~

**dependency:tree** giúp xem graph artifact của Maven, nhưng không trực tiếp thay cho việc kiểm tra Java module graph thực tế.

## 17. Split package trong Maven modular build

Nếu hai dependency chứa cùng package Java và đều được dùng như module riêng, JPMS có thể gặp xung đột.

Ví dụ:

~~~text
catalog-common.jar
└── com/example/shared/Formatter.class

legacy-format.jar
└── com/example/shared/LegacyParser.class
~~~

Hai JAR có các class khác nhau nhưng cùng package **com.example.shared**. Đó là split package khi cả hai trở thành module riêng.

Maven có thể resolve cả hai artifact hợp lệ, nhưng module resolution hoặc định nghĩa module bằng class loader có thể thất bại.

Giải pháp:

- Xác định module sở hữu duy nhất cho package.
- Loại dependency trùng/không cần thiết.
- Dùng phiên bản thư viện modular phù hợp.
- Tách shared code sang một module chung.
- Chỉ dùng relocation/shading nếu kiểm soát được class và metadata liên quan.

Không nên thêm **--add-reads** hoặc **--add-opens** với kỳ vọng chúng loại bỏ split package: các tùy chọn này không thay đổi ownership của package.

## 18. Maven Shade Plugin cần được kiểm soát

Trong ứng dụng classpath, Maven Shade Plugin thường dùng để tạo fat JAR. Với JPMS, việc hợp nhất nhiều JAR modular vào một JAR có thể dẫn đến:

- Nhiều file module-info.class cạnh tranh.
- Descriptor bị bỏ, ghi đè hoặc không còn phản ánh đúng class.
- Package implementation của nhiều module bị gộp lại.
- Service provider metadata không được xử lý đúng.
- Sự khác biệt giữa classpath launch và module-path launch.

Nếu muốn phát hành một ứng dụng JPMS đúng nghĩa, ưu tiên giữ các module được phân phối như những artifact riêng và chạy bằng **java --module-path ... --module ...** hoặc một runtime image phù hợp.

Nếu dự án thật sự cần fat JAR, phải xác định rõ nó còn được chạy như named module hay chuyển sang cơ chế classpath, rồi kiểm tra artifact sau shading. Không nên cho rằng output sau shading vẫn modular chỉ vì source đầu vào có module-info.java.

## 19. Xác minh dependency bằng jdeps

JDK cung cấp **jdeps** để phân tích dependency giữa các class/JAR và đánh giá việc modular hóa.

Ví dụ:

~~~bash
jdeps --module-path \
      "catalog-api/target/catalog-api-1.0.0.jar:catalog-app/target/catalog-app-1.0.0.jar" \
      --module com.example.catalog.app
~~~

Có thể dùng jdeps cùng module path đã xây dựng để xem các dependency tĩnh. Công cụ này giúp hỗ trợ kiểm tra, nhưng không thay cho việc chạy ứng dụng thực tế.

Một số dependency chỉ xuất hiện khi reflection, đọc cấu hình, dùng ServiceLoader hoặc gọi Class.forName. Phân tích tĩnh có thể không phát hiện toàn bộ những dependency đó.

Để kiểm chứng bản phát hành, hãy kết hợp:

- Kiểm tra JAR và module-info.class.
- Kiểm tra tên module thực tế.
- Kiểm tra dependencies bằng jdeps.
- Chạy lệnh Java với đúng module path runtime.
- Chạy unit test/integration test ở cấu hình gần production.

## 20. Lỗi thường gặp và hướng xử lý

### module not found

Compiler hoặc launcher không tìm thấy module nêu trong requires hoặc root selection. Kiểm tra JAR dependency có thật, tên Java module và đường dẫn module path.

### package ... is not visible

Module nguồn có thể chưa đọc module đích hoặc package đích chưa export. Phân biệt readability với package accessibility.

### class not found khi chạy

Thư viện có thể đã có trong Maven build nhưng không được phân phối trong runtime module path/classpath. Kiểm tra script khởi chạy, dependency scope và artifact thực tế.

### Test compile được nhưng Surefire lỗi

Test JVM có thể dùng module path, class loader hoặc quyền reflection khác. Kiểm tra Surefire config, test dependencies và module opens cần thiết.

### Java module name khác artifactId

Đừng suy luận module name từ Maven coordinate. Dùng **jar --describe-module** để xác nhận.

### Automatic module làm lộ package nội bộ

Automatic module export tất cả package. Nếu cần encapsulation chọn lọc, hãy dùng modular JAR có descriptor tường minh.

### Build chạy ở máy cá nhân nhưng lỗi CI

Kiểm tra JDK, Maven version, Maven Wrapper, plugin version, cấu hình test và đường dẫn module path trên từng hệ điều hành. Tránh hardcode dấu phân cách đường dẫn hoặc folder của máy phát triển trong POM.

## 21. Checklist triển khai thực tế

Đối với một dự án Maven dùng JPMS:

1. Chọn phiên bản Java release thống nhất với JDK của pipeline.
2. Quản lý phiên bản Maven Compiler Plugin và Surefire Plugin.
3. Thêm **module-info.java** cho các project muốn thành named module.
4. Khai báo dependency bằng **pom.xml** để Maven tìm được artifact.
5. Khai báo **requires** bằng đúng tên module Java.
6. Export đúng các package API; giữ package implementation không export.
7. Kiểm tra automatic module và split package trong dependency.
8. Build reactor với **mvn clean package** hoặc chọn project qua **-pl ... -am**.
9. Kiểm tra artifact bằng **jar --describe-module**.
10. Chạy ứng dụng bằng module path trên chính JAR đã đóng gói.
11. Cấu hình Surefire và quyền reflection phù hợp cho test.
12. Chạy integration test trong môi trường gần giống runtime triển khai.
13. Cập nhật script phân phối khi có dependency/module mới.
14. Loại các workaround --add-reads/--add-exports/--add-opens khi không còn cần.

Một build Maven thành công mới chứng minh rằng lifecycle build đã chạy xong, chưa đủ để khẳng định module path production đúng. Phần xác nhận cuối cùng phải dựa trên JAR và lệnh chạy thật.

## 22. Ghi nhớ

- **Classpath** dùng cho mô hình class loader truyền thống; **module path** cung cấp named/automatic module cho JPMS.
- Maven reactor module không tự động là Java module.
- **module-info.java** là thành phần chính giúp compiler nhận diện named module.
- Maven dependency cung cấp artifact; directive **requires** biểu diễn quan hệ đọc trong JPMS.
- Maven artifactId không nhất thiết trùng Java module name.
- **maven.compiler.release** hoặc **release** của compiler plugin cần phù hợp với JDK sử dụng.
- Maven Compiler Plugin và Maven Surefire Plugin xử lý những giai đoạn khác nhau; cấu hình runtime test có thể khác compilation.
- Dependency scope Maven không tự biến thành directive requires hoặc requires static.
- JAR không có descriptor trên module path có thể trở thành automatic module.
- Fat JAR/shading có thể làm hỏng ranh giới module nếu không được thiết kế riêng.
- Dùng **jar --describe-module**, **jdeps** và lệnh **java --module-path** để xác nhận artifact phát hành.

Tóm lại, module path trong Maven là điểm gặp nhau giữa quản lý artifact của Maven và module graph của JPMS. Muốn ứng dụng modular đáng tin cậy, hãy giữ **pom.xml** và **module-info.java** nhất quán, cấu hình compiler/test tương thích với JDK, rồi kiểm tra kết quả trên những JAR sẽ thực sự được triển khai.
