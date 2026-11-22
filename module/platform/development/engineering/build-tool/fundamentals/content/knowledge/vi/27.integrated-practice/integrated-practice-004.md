# Tách mô-đun thư viện và mô-đun ứng dụng để kiểm chứng ranh giới

Khi một dự án Java phát triển, việc đặt toàn bộ mã nguồn, cấu hình, dependency và điểm khởi chạy trong một module có thể khiến các phần nghiệp vụ, giao tiếp bên ngoài và cấu hình triển khai phụ thuộc chéo. Một thay đổi ở ứng dụng có thể làm thư viện không thể build độc lập; thư viện có thể vô tình phụ thuộc framework hoặc cấu hình chỉ tồn tại ở ứng dụng.

Tách **mô-đun thư viện** và **mô-đun ứng dụng** là cách xác định và kiểm chứng ranh giới trách nhiệm. Thư viện cung cấp API và logic có thể tái sử dụng. Ứng dụng sử dụng API đó, điều phối luồng xử lý và kết nối với môi trường chạy. Quan hệ phụ thuộc nên đi theo một hướng: **ứng dụng phụ thuộc thư viện; thư viện không phụ thuộc ứng dụng**.

Việc tách module không chỉ là chuyển file sang hai thư mục. Ranh giới chỉ có ý nghĩa khi build graph, dependency, package/API, test và artifact đều phản ánh cùng một kiến trúc. Bài học này xây dựng một ví dụ nhỏ bằng Java, triển khai với Gradle và Maven, sau đó kiểm tra xem hai module có thật sự độc lập hay không.

## 1. Mục tiêu và kết quả mong đợi

Ta sẽ xây dựng một hệ thống đơn giản gồm:

- **pricing-library:** chứa API và quy tắc tính giá. Module này không có main method, không biết cách khởi chạy ứng dụng và không phụ thuộc vào module ứng dụng.
- **storefront-app:** chứa entry point, điều phối yêu cầu, cấu hình và phần giao tiếp với người dùng. Module này phụ thuộc vào pricing-library.

~~~mermaid
flowchart LR
    APP["storefront-app<br/>Ứng dụng, entry point, orchestration"] --> LIB["pricing-library<br/>API và logic tính giá"]
    JDK["Java platform"] --> APP
    JDK --> LIB
~~~

Sau bài thực hành, cần có thể chứng minh:

1. Hai module có source set và output riêng.
2. Library build và test được mà không cần application.
3. Application khai báo dependency tới library qua build tool.
4. Library không import package hoặc phụ thuộc artifact của application.
5. Public API của library đủ để application sử dụng mà không cần truy cập implementation nội bộ.
6. Unit test của library tập trung vào hợp đồng thư viện; test tích hợp/khởi chạy thuộc application.
7. Build tool tạo artifact riêng cho từng module.
8. Thay đổi ở application không làm library phải phụ thuộc ngược trở lại.

## 2. Phân biệt module build, package Java và JPMS

Từ module có thể chỉ ba khái niệm khác nhau.

| Khái niệm | Phạm vi | Ví dụ |
|---|---|---|
| Module của build tool | Đơn vị build có source, dependency và task riêng | Gradle subproject hoặc Maven reactor module |
| Java package | Nhóm namespace của class | com.acme.pricing.api |
| JPMS module | Module ở cấp Java Platform Module System, có module descriptor | module com.acme.pricing trong module-info.java |

Trong bài này, trước hết ta tách module ở cấp build tool. Mỗi module có source directory, dependency và artifact riêng. Điều đó chưa tự động tạo ra JPMS module. Một build nhiều module vẫn có thể dùng classpath truyền thống. Nếu muốn giới hạn package được export ở cấp JVM bằng JPMS, có thể bổ sung module-info.java sau khi ranh giới build đã rõ.

### 2.1. Vì sao không chỉ tạo hai package?

Nếu chỉ tạo hai package trong cùng một module, chúng vẫn thường được biên dịch, test và đóng gói cùng nhau. Build tool không thể độc lập build library mà không xử lý phần application; dependency ở cấp module cũng chưa được thể hiện.

Hai build module riêng cho phép:

- chạy test library độc lập;
- khai báo dependency theo hướng;
- xuất artifact library riêng;
- dùng library trong ứng dụng khác;
- áp dụng versioning hoặc publishing riêng khi cần;
- phát hiện dependency cycle ở build graph.

Package vẫn quan trọng để kiểm soát API bên trong từng module. Module boundary và package boundary bổ trợ cho nhau.

### 2.2. Không phải cứ tách thư mục là đã tách module

Một thư mục có tên pricing-library chưa trở thành module nếu build tool không khai báo nó trong project/module graph. Ngược lại, một module được khai báo trong Gradle settings hoặc Maven parent POM nhưng vẫn chứa package lẫn lộn thì ranh giới trách nhiệm chưa rõ.

Hãy kiểm tra cả cấu trúc thư mục, build configuration, dependency graph, source code và artifact.

## 3. Thiết kế trách nhiệm trước khi di chuyển code

Trước khi tạo module, hãy quyết định phần nào thuộc library và phần nào thuộc application.

### 3.1. Trách nhiệm của library

Library nên sở hữu:

- kiểu dữ liệu và API mà consumer cần;
- quy tắc nghiệp vụ có thể tái sử dụng;
- validation gắn với hợp đồng nghiệp vụ;
- thuật toán hoặc service logic không phụ thuộc entry point;
- abstraction/port cần thiết để tách logic khỏi hạ tầng;
- unit test cho hành vi công khai và các quy tắc nội bộ.

Library nên tránh:

- main method hoặc logic khởi động ứng dụng;
- đọc biến môi trường trực tiếp để quyết định cấu hình toàn hệ thống;
- phụ thuộc controller, UI, HTTP route hoặc framework của application;
- truy cập database cụ thể nếu đó là trách nhiệm adapter của ứng dụng;
- phụ thuộc file cấu hình triển khai của application;
- tham chiếu class trong package của application.

Một library có thể phụ thuộc vào thư viện bên thứ ba nếu đó là một phần hợp lý của API hoặc implementation. Nhưng dependency cần được chọn có chủ đích và không nên kéo theo toàn bộ framework của ứng dụng.

### 3.2. Trách nhiệm của application

Application nên sở hữu:

- main method hoặc entry point;
- cấu hình runtime và dependency injection;
- controller, CLI, HTTP endpoint hoặc giao diện;
- adapter kết nối database, message broker và external service;
- orchestration giữa các use case;
- logging, metrics và cấu hình triển khai;
- integration test xác minh các thành phần được nối với nhau.

Application phụ thuộc vào library qua API ổn định. Nếu library cần gọi một hành vi do application cung cấp, hãy định nghĩa interface/port ở phía library và để application triển khai interface đó. Không tạo dependency ngược chỉ để library gọi trực tiếp một class của application.

### 3.3. Quy tắc hướng phụ thuộc

~~~text
Application
    |
    v
Library API
    |
    v
Library implementation
~~~

Trong ví dụ đơn giản, API và implementation có thể ở cùng library module. Nếu cần tách sâu hơn, có thể tạo module API riêng và module implementation riêng, nhưng không cần thêm module khi chưa có lý do.

Một nguyên tắc hữu ích:

- library không biết application tồn tại;
- application biết library qua public API;
- cả hai có thể dùng Java platform và các dependency nền tảng được chọn;
- dependency dùng chung phải được đặt ở đúng tầng, tránh tạo module common không có ranh giới rõ ràng.

## 4. Ví dụ nghiệp vụ: tính giá đơn hàng

Application nhận một yêu cầu tính giá, tạo dữ liệu đầu vào và gọi library. Library tính subtotal, discount và total rồi trả kết quả. Application hiển thị kết quả.

### 4.1. API của library

Library cung cấp ba kiểu public:

- PriceRequest: dữ liệu đầu vào;
- PriceQuote: kết quả tính toán;
- PriceCalculator: API thực hiện tính giá.

~~~java
package com.acme.pricing.api;

import java.math.BigDecimal;
import java.util.Objects;

public record PriceRequest(
        BigDecimal unitPrice,
        int quantity,
        BigDecimal discountRate) {

    public PriceRequest {
        Objects.requireNonNull(unitPrice, "unitPrice");
        Objects.requireNonNull(discountRate, "discountRate");
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must not be negative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (discountRate.signum() < 0
                || discountRate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException("discountRate must be between 0 and 1");
        }
    }
}
~~~

~~~java
package com.acme.pricing.api;

import java.math.BigDecimal;

public record PriceQuote(
        BigDecimal subtotal,
        BigDecimal discount,
        BigDecimal total) {
}
~~~

~~~java
package com.acme.pricing.api;

import java.math.BigDecimal;
import java.math.RoundingMode;

public final class PriceCalculator {

    public PriceQuote calculate(PriceRequest request) {
        BigDecimal subtotal = request.unitPrice()
                .multiply(BigDecimal.valueOf(request.quantity()))
                .setScale(2, RoundingMode.HALF_UP);
        BigDecimal discount = subtotal
                .multiply(request.discountRate())
                .setScale(2, RoundingMode.HALF_UP);
        BigDecimal total = subtotal.subtract(discount);
        return new PriceQuote(subtotal, discount, total);
    }
}
~~~

Các class này không biết HTTP, console, database hay framework. Library chỉ nhận input và trả kết quả. Application không cần biết thuật toán làm tròn được triển khai ra sao.

### 4.2. Entry point của application

~~~java
package com.acme.storefront;

import com.acme.pricing.api.PriceCalculator;
import com.acme.pricing.api.PriceQuote;
import com.acme.pricing.api.PriceRequest;

import java.math.BigDecimal;

public final class Main {

    public static void main(String[] args) {
        PriceCalculator calculator = new PriceCalculator();
        PriceRequest request = new PriceRequest(
                new BigDecimal("25.00"),
                4,
                new BigDecimal("0.10"));
        PriceQuote quote = calculator.calculate(request);
        System.out.println("Subtotal: " + quote.subtotal());
        System.out.println("Discount: " + quote.discount());
        System.out.println("Total: " + quote.total());
    }
}
~~~

Application import public API của library. Library không import com.acme.storefront. Đây là hướng phụ thuộc cần giữ.

### 4.3. Tổ chức API và implementation

Ví dụ dùng một class PriceCalculator đơn giản để tập trung vào ranh giới module. Trong dự án lớn hơn, có thể tách package:

~~~text
pricing-library
└── com.acme.pricing
    ├── api
    │   ├── PriceRequest
    │   ├── PriceQuote
    │   └── PriceCalculator
    └── internal
        └── RoundingPolicy
~~~

Class trong internal nên không được xem là hợp đồng cho consumer. Có thể dùng package-private visibility khi các class cần truy cập chỉ nằm trong cùng package, hoặc giữ implementation public khi framework/extension point thực sự yêu cầu. Đừng biến mọi class thành public chỉ để application truy cập.

## 5. Cấu trúc thư mục mục tiêu

Sau khi tách, cấu trúc có thể như sau:

~~~text
storefront/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle.properties
├── pricing-library/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/com/acme/pricing/api/
│       │   ├── PriceRequest.java
│       │   ├── PriceQuote.java
│       │   └── PriceCalculator.java
│       └── test/java/com/acme/pricing/api/
│           └── PriceCalculatorTest.java
└── storefront-app/
    ├── build.gradle.kts
    └── src/
        ├── main/java/com/acme/storefront/
        │   └── Main.java
        └── test/java/com/acme/storefront/
            └── ApplicationFlowTest.java
~~~

Mỗi module có source set riêng. Thư mục test của library kiểm tra hành vi library; thư mục test của application kiểm tra orchestration và tích hợp với library. Nếu dùng Maven, cấu trúc tương tự nhưng mỗi module có pom.xml và thư mục con được khai báo trong parent aggregator.

## 6. Gradle: khai báo multi-project build

Gradle multi-project build dùng settings file để xác định project root và các subproject.

### 6.1. settings.gradle.kts

~~~kotlin
rootProject.name = "storefront"

include("pricing-library")
include("storefront-app")
~~~

Hai tên trong include tương ứng với hai project con. Theo mặc định, Gradle ánh xạ chúng tới thư mục cùng tên ở root. Có thể tùy chỉnh projectDir nếu cấu trúc repository khác.

### 6.2. build.gradle.kts ở root

~~~kotlin
allprojects {
    group = "com.acme"
    version = "1.0.0"
    repositories {
        mavenCentral()
    }
}

subprojects {
    tasks.withType<JavaCompile>().configureEach {
        options.release = 17
        options.encoding = "UTF-8"
    }
}
~~~

Root build file đặt group/version và repository chung. Java release 17 là lựa chọn minh họa; hãy dùng target phù hợp với hợp đồng hỗ trợ của dự án.

Có thể cấu hình Java toolchain ở từng module hoặc qua convention plugin dùng chung. Nếu cần kiểm soát JDK compiler thực tế, khai báo toolchain rõ ràng trong build script của module có Java plugin:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Java release và toolchain giải quyết hai vấn đề khác nhau: toolchain chọn JDK; release giới hạn API/bytecode mục tiêu.

### 6.3. pricing-library/build.gradle.kts

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Plugin java-library phù hợp với module cung cấp API cho module khác. Nó bổ sung cấu hình api và implementation để kiểm soát dependency được expose qua compile classpath của consumer.

Trong ví dụ này library chỉ dùng Java platform nên không cần dependency production bên ngoài. JUnit chỉ nằm trong testImplementation, không đi vào runtime API của library.

### 6.4. storefront-app/build.gradle.kts

~~~kotlin
plugins {
    application
}

dependencies {
    implementation(project(":pricing-library"))
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
}

application {
    mainClass = "com.acme.storefront.Main"
}

tasks.test {
    useJUnitPlatform()
}
~~~

Điểm quan trọng là application khai báo project dependency tới pricing-library. Gradle đưa dependency vào compile/runtime classpath phù hợp và lập task dependency để library được build trước khi application cần output của nó.

Không thêm dependency ngược từ pricing-library sang storefront-app. Nếu làm vậy, ranh giới kiến trúc đã bị đảo và build graph có thể tạo cycle.

### 6.5. Chạy các task Gradle

Liệt kê project:

~~~bash
./gradlew projects
~~~

Chỉ test library:

~~~bash
./gradlew :pricing-library:test
~~~

Test application:

~~~bash
./gradlew :storefront-app:test
~~~

Build toàn bộ:

~~~bash
./gradlew clean build
~~~

Chạy application:

~~~bash
./gradlew :storefront-app:run
~~~

Xem dependency runtime của application:

~~~bash
./gradlew :storefront-app:dependencies --configuration runtimeClasspath
~~~

Các lệnh có dấu hai chấm ở đầu là task path đầy đủ trong multi-project build. Dùng task path giúp biết chính xác module nào đang được kiểm tra.

## 7. Gradle: hiểu api và implementation

Khi dùng java-library plugin, cần chọn cấu hình dependency theo việc dependency có xuất hiện trong public API của library hay không.

| Configuration | Ý nghĩa |
|---|---|
| api | Dependency cần có trên compile classpath của consumer vì public API của library sử dụng kiểu từ dependency đó |
| implementation | Dependency chỉ phục vụ implementation của library, không cần expose cho compile classpath consumer |
| compileOnly | Cần khi compile nhưng không được đưa vào runtime theo cấu hình thông thường |
| runtimeOnly | Chỉ cần khi chạy |
| testImplementation | Chỉ dùng cho test compile/runtime của module |

Ví dụ nếu PriceCalculator nhận/trả một kiểu thuộc thư viện bên ngoài và consumer cần tham chiếu kiểu đó, dependency có thể cần nằm trong api. Nếu library dùng thư viện đó nội bộ và public API chỉ dùng kiểu Java của chính nó, implementation thường phù hợp hơn.

### 7.1. Vì sao không nên khai báo mọi thứ là api?

Khai báo quá nhiều dependency là api làm compile classpath của consumer phình ra và khiến chi tiết implementation trở thành một phần của hợp đồng. Khi library thay implementation, consumer có thể bị ràng buộc với dependency mà họ không cần biết.

Chỉ expose dependency khi public API thật sự yêu cầu consumer nhìn thấy kiểu đó.

### 7.2. Vì sao application dùng implementation cho project dependency?

Application là consumer của library. Nếu application không cung cấp API công khai cho module khác cần dùng lại, dependency project thường được khai báo implementation.

Nếu application có public API được module khác sử dụng và kiểu API đó trực tiếp chứa kiểu của library, khi đó cần cân nhắc api. Quyết định dựa trên hợp đồng public của consumer module, không chỉ dựa vào việc dependency có được gọi trong code hay không.

## 8. Maven: tạo parent aggregator và hai module

Maven multi-module build dùng một POM packaging pom để liệt kê các module trong reactor.

### 8.1. Cấu trúc thư mục Maven

~~~text
storefront/
├── pom.xml
├── pricing-library/
│   ├── pom.xml
│   └── src/
│       ├── main/java/com/acme/pricing/api/
│       └── test/java/com/acme/pricing/api/
└── storefront-app/
    ├── pom.xml
    └── src/
        ├── main/java/com/acme/storefront/
        └── test/java/com/acme/storefront/
~~~

### 8.2. Parent pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.acme</groupId>
    <artifactId>storefront-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>pricing-library</module>
        <module>storefront-app</module>
    </modules>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.11.4</junit.version>
    </properties>
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit</groupId>
                <artifactId>junit-bom</artifactId>
                <version>${junit.version}</version>
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
                    <version>3.13.0</version>
                    <configuration>
                        <release>${maven.compiler.release}</release>
                        <encoding>${project.build.sourceEncoding}</encoding>
                    </configuration>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

POM này vừa là aggregator (liệt kê module) vừa là parent (cung cấp cấu hình được kế thừa). Hai vai trò có thể nằm trong cùng một POM nhưng về khái niệm là khác nhau: aggregator quyết định reactor gồm module nào; parent cung cấp metadata/configuration cho child POM.

Các version plugin và JUnit trong ví dụ là giá trị minh họa cần được pin và kiểm tra tương thích trong dự án thật.

### 8.3. pricing-library/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>storefront-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>pricing-library</artifactId>
    <packaging>jar</packaging>
    <dependencies>
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
                <artifactId>maven-compiler-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Library chỉ khai báo JUnit ở test scope. Không có dependency tới storefront-app.

### 8.4. storefront-app/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>storefront-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>storefront-app</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>pricing-library</artifactId>
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
                <artifactId>maven-compiler-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dependency tới pricing-library được khai báo bằng tọa độ Maven. Khi cả hai module nằm trong cùng reactor và version khớp, Maven xây library trước application theo dependency graph.

### 8.5. Chạy Maven reactor

Build toàn bộ:

~~~bash
./mvnw clean verify
~~~

Chỉ build/test library:

~~~bash
./mvnw -pl pricing-library verify
~~~

Build application cùng các module cần thiết trong reactor:

~~~bash
./mvnw -pl storefront-app -am verify
~~~

Xem dependency tree của application:

~~~bash
./mvnw -pl storefront-app dependency:tree
~~~

Nếu chọn riêng application mà không dùng -am, Maven có thể cần library đã được cài/publish vào repository. -am yêu cầu Maven build thêm các module mà project được chọn phụ thuộc trong reactor hiện tại.

## 9. Maven parent, aggregator và dependency là ba quan hệ khác nhau

Một lỗi thiết kế thường gặp là nhầm việc module kế thừa parent với việc module phụ thuộc module khác.

| Quan hệ | Khai báo ở đâu | Ý nghĩa |
|---|---|---|
| Aggregation | modules trong POM packaging pom | Đưa các module vào cùng reactor build |
| Inheritance | parent trong child POM | Kế thừa properties, dependency management, plugin config và metadata |
| Dependency | dependencies trong child POM | Dùng artifact của module/dependency khác |

Trong ví dụ:

- parent aggregator chứa pricing-library và storefront-app;
- cả hai module kế thừa storefront-parent;
- storefront-app phụ thuộc pricing-library;
- pricing-library không phụ thuộc storefront-app.

Việc cả hai module cùng kế thừa parent không có nghĩa chúng phụ thuộc vào nhau ở runtime.

## 10. Kiểm chứng dependency direction

Sau khi cấu hình, không chỉ dựa vào tên thư mục. Hãy kiểm tra dependency graph của build tool.

### 10.1. Kiểm tra trong Gradle

~~~bash
./gradlew projects
./gradlew :storefront-app:dependencies --configuration runtimeClasspath
./gradlew :pricing-library:dependencies --configuration runtimeClasspath
~~~

Trong graph cần thấy pricing-library là dependency của storefront-app. Library không nên có dependency project ngược về storefront-app. Nếu thấy application hoặc framework chỉ thuộc app xuất hiện trong library, hãy kiểm tra khai báo dependency và source import.

### 10.2. Kiểm tra trong Maven

~~~bash
./mvnw -pl storefront-app dependency:tree
./mvnw -pl pricing-library dependency:tree
./mvnw -pl storefront-app help:effective-pom
~~~

Dependency tree cho thấy dependency được resolve theo module. Effective POM giúp kiểm tra dependency/plugin config sau khi kế thừa; nó không thay thế dependency tree.

### 10.3. Dependency cycle

Nếu library phụ thuộc app và app phụ thuộc library, hai module có dependency cycle. Build tool có thể báo lỗi lập lịch/build reactor hoặc không thể xác định thứ tự build hợp lệ.

Ngay cả khi cycle được né bằng cách đặt class chung vào một module thứ ba, cần xem lại hướng phụ thuộc. Một library dùng lại được không nên cần application cụ thể để hoạt động.

## 11. Kiểm chứng bằng source import và package

Dependency graph là lớp kiểm tra đầu tiên. Source code cũng cần thể hiện ranh giới.

### 11.1. Library không import application

Tìm các import có package application trong source library. Ví dụ:

~~~java
import com.acme.storefront.Main;
import com.acme.storefront.config.ApplicationSettings;
~~~

Nếu những import này xuất hiện trong library, có thể trách nhiệm đang bị đặt sai tầng. Library không nên biết tên command hoặc HTTP route, cấu hình deployment, controller/UI model, class khởi chạy hay adapter database cụ thể của application.

### 11.2. Application chỉ dùng public API

Application nên import package được thiết kế làm API:

~~~java
import com.acme.pricing.api.PriceCalculator;
import com.acme.pricing.api.PriceRequest;
import com.acme.pricing.api.PriceQuote;
~~~

Tránh import package internal hoặc class implementation chỉ để né một API chưa đầy đủ. Nếu application cần một khả năng hợp lệ nhưng library chưa cung cấp, hãy thiết kế API rõ ràng thay vì mở rộng quyền truy cập tùy tiện.

### 11.3. Public không đồng nghĩa public API được hỗ trợ

Trong Java, class public trên classpath thường có thể được consumer truy cập. Nhưng nhóm vẫn cần xác định package/class nào là hợp đồng được hỗ trợ.

Có thể đặt API trong package có tên rõ như api, giữ implementation package-private khi có thể, không export package internal nếu dùng JPMS, ghi tài liệu về API ổn định/nội bộ và kiểm tra public API thay đổi qua release.

Tên package chỉ là quy ước; compiler không tự cấm consumer import package internal nếu class public và module không áp dụng JPMS.

## 12. Kiểm chứng bằng unit test và integration test

Test cũng cần phản ánh ranh giới module.

### 12.1. Unit test thuộc library

Library test kiểm tra validation của PriceRequest, quy tắc tính subtotal, cách tính discount, quy tắc làm tròn, các trường hợp biên và bất biến của PriceQuote.

~~~java
package com.acme.pricing.api;

import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import static org.junit.jupiter.api.Assertions.assertEquals;

class PriceCalculatorTest {

    @Test
    void calculatesDiscountedTotal() {
        PriceCalculator calculator = new PriceCalculator();
        PriceRequest request = new PriceRequest(
                new BigDecimal("25.00"),
                4,
                new BigDecimal("0.10"));
        PriceQuote quote = calculator.calculate(request);
        assertEquals(new BigDecimal("100.00"), quote.subtotal());
        assertEquals(new BigDecimal("10.00"), quote.discount());
        assertEquals(new BigDecimal("90.00"), quote.total());
    }
}
~~~

Test này nằm trong pricing-library. Nó không cần khởi chạy application, web server hoặc database.

### 12.2. Test thuộc application

Application test kiểm tra orchestration, chẳng hạn application nhận input và gọi library đúng cách. Nếu app có HTTP adapter, test controller/endpoint có thể kiểm tra mapping và status code. Nếu app kết nối database, integration test kiểm tra adapter và cấu hình persistence.

Không đưa toàn bộ integration test vào library chỉ vì library chứa logic nghiệp vụ. Library không nên cần khởi động hạ tầng application để test thuật toán của nó.

### 12.3. Contract test giữa hai module

Test application có thể xác nhận application sử dụng public API theo cách mong đợi: tạo/nhận public types, mapping input/output, xử lý exception/error contract và không phụ thuộc implementation nội bộ. Không nên copy toàn bộ unit test của library sang application.

### 12.4. Chạy test độc lập

Gradle:

~~~bash
./gradlew :pricing-library:test
~~~

Maven:

~~~bash
./mvnw -pl pricing-library test
~~~

Nếu test library chỉ chạy được khi application đã build, đó là dấu hiệu có dependency ẩn hoặc test setup sai ranh giới.

## 13. Kiểm tra ranh giới tự động bằng ArchUnit

Dependency graph ở cấp build tool chứng minh module nào khai báo dependency tới module nào. ArchUnit có thể bổ sung kiểm tra dependency ở cấp bytecode/package.

Ví dụ rule đặt trong test của application, nơi classpath có cả application và library:

~~~java
package com.acme.storefront;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.Test;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

class ModuleBoundaryTest {

    @Test
    void pricingMustNotDependOnStorefront() {
        JavaClasses classes = new ClassFileImporter()
                .importPackages("com.acme");
        ArchRule rule = noClasses()
                .that().resideInAPackage("com.acme.pricing..")
                .should().dependOnClassesThat()
                .resideInAPackage("com.acme.storefront..");
        rule.check(classes);
    }
}
~~~

Rule này kiểm tra class trong package pricing không có bytecode dependency tới package storefront. Nó giúp bắt import/dependency ở cấp class.

### 13.1. Thêm dependency ArchUnit cho test

Gradle:

~~~kotlin
dependencies {
    testImplementation("com.tngtech.archunit:archunit-junit5:1.3.0")
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>com.tngtech.archunit</groupId>
    <artifactId>archunit-junit5</artifactId>
    <version>1.3.0</version>
    <scope>test</scope>
</dependency>
~~~

Đặt dependency trong module chứa architecture test. Version là ví dụ; cần pin version tương thích với JUnit và Java target của dự án.

### 13.2. Giới hạn của package rule

Rule trên chỉ nhìn thấy class mà ClassFileImporter import được. Nếu application class không nằm trên test classpath, rule không thể phát hiện dependency tới class đó vì class không được import.

Để kiểm chứng đúng, đặt architecture test ở module có thể nhìn thấy cả hai module, import package phù hợp, bảo đảm test runtime classpath có cả library và application output; đồng thời kiểm tra dependency graph của build tool như một lớp kiểm soát riêng.

ArchUnit không thay thế Gradle/Maven dependency graph. Hai công cụ kiểm tra hai cấp khác nhau.

### 13.3. Kiểm tra package internal

~~~java
@Test
void applicationUsesOnlyPublicPricingApi() {
    JavaClasses classes = new ClassFileImporter()
            .importPackages("com.acme");
    ArchRule rule = noClasses()
            .that().resideInAPackage("com.acme.storefront..")
            .should().dependOnClassesThat()
            .resideInAPackage("com.acme.pricing.internal..");
    rule.check(classes);
}
~~~

Nếu module không có package internal thì rule có thể được thêm khi cần. Đừng tạo rule quá rộng đến mức mọi refactor package đều phải sửa test dù hợp đồng không thay đổi.

## 14. JPMS: siết ranh giới ở cấp Java Platform Module System

Sau khi build module đã tách rõ, có thể cân nhắc JPMS để kiểm soát package export/import ở cấp Java runtime.

Trong pricing-library:

~~~java
module com.acme.pricing {
    exports com.acme.pricing.api;
}
~~~

Trong storefront-app:

~~~java
module com.acme.storefront {
    requires com.acme.pricing;
}
~~~

Module descriptor của library chỉ export package API. Package internal không được export cho module khác truy cập theo cơ chế module thông thường.

### 14.1. JPMS không tự sinh từ Gradle/Maven subproject

Việc include project trong Gradle hoặc liệt kê module trong Maven POM không tự tạo module-info.java. Build module là khái niệm của build tool; JPMS module là khái niệm của Java runtime/compiler.

Có thể có multi-project build mà mọi artifact vẫn chạy trên classpath. Ngược lại, một JAR có module-info.java vẫn có thể được build như một module duy nhất trong Gradle/Maven.

### 14.2. Khi nào nên dùng JPMS?

JPMS hữu ích khi cần giới hạn package được export, khai báo module dependency tường minh, giảm truy cập reflective không cần thiết, phát triển thư viện có API công khai/implementation nội bộ rõ ràng và chạy trong môi trường hỗ trợ module path.

Nó có thể làm cấu hình test/framework phức tạp hơn nếu framework dùng reflection hoặc cần mở package. Không nên thêm JPMS chỉ để có module-info.java mà chưa xác định lợi ích.

## 15. Kiểm tra artifact của từng module

Một mục tiêu của việc tách module là có thể nhận diện artifact riêng.

### 15.1. Gradle output

~~~text
pricing-library/build/libs/pricing-library-1.0.0.jar
storefront-app/build/libs/storefront-app-1.0.0.jar
~~~

Library JAR chứa class/resource của library. Application JAR chứa class/resource của app. Application runtime dependency graph có thêm library.

Liệt kê nội dung:

~~~bash
jar --list --file pricing-library/build/libs/pricing-library-1.0.0.jar
jar --list --file storefront-app/build/libs/storefront-app-1.0.0.jar
~~~

### 15.2. Maven output

~~~text
pricing-library/target/pricing-library-1.0.0.jar
storefront-app/target/storefront-app-1.0.0.jar
~~~

Maven JAR Plugin tạo JAR riêng cho từng module packaging jar. Application JAR thông thường không tự nhúng dependency JAR của library. Nếu cần phân phối app chạy độc lập, cần cấu hình executable/fat JAR hoặc distribution phù hợp.

### 15.3. Không nhầm dependency với nội dung JAR

Application khai báo dependency tới library không có nghĩa file storefront-app.jar luôn chứa class của library. Với thin JAR, library là một JAR riêng trên runtime classpath. Build tool hoặc distribution plugin có thể gom dependency vào gói khác.

Hãy phân biệt compile/runtime dependency graph, nội dung của từng JAR và distribution cuối cùng được chuyển cho người vận hành.

## 16. Tách module nhưng vẫn phân phối ứng dụng hoàn chỉnh

Việc giữ library thành artifact riêng không buộc người dùng cuối phải tự quản lý mọi JAR. Các lựa chọn gồm:

- publish library JAR lên Maven repository để ứng dụng khác dùng;
- tạo application distribution có app JAR và thư mục lib;
- tạo executable/fat JAR bằng plugin phù hợp;
- tạo container image chứa runtime và application artifact;
- giữ library nội bộ trong cùng reactor nhưng vẫn đóng gói runtime dependency theo mô hình triển khai.

Điều quan trọng là ranh giới source/build vẫn rõ, còn định dạng phân phối phụ thuộc nhu cầu consumer.

### 16.1. Versioning

Trong monorepo, các module có thể dùng chung version như ví dụ. Khi library được phát hành độc lập, có thể cần version riêng để consumer nâng cấp mà không phát hành lại toàn bộ application.

Nếu version library và application độc lập, application khai báo version library rõ ràng; release library tạo artifact bất biến; application kiểm thử với version được chọn; dependency update được review như thay đổi source; deployment record ghi nhận version/digest thực tế.

Không publish lại nội dung khác dưới cùng tọa độ/version.

## 17. Tránh những cách tách module sai

### 17.1. Library phụ thuộc application để lấy cấu hình

Ví dụ không tốt: library import ApplicationSettings hoặc đọc singleton của app. Cách này tạo dependency ngược và làm library không thể dùng độc lập.

Cách xử lý:

- truyền cấu hình cần thiết qua constructor/method parameter;
- định nghĩa interface/port trong library nếu cần một hành vi do consumer cung cấp;
- application tạo adapter/implementation và inject vào library;
- giữ cấu hình triển khai ở application.

### 17.2. Đưa mọi thứ vào common/shared

Tạo module common chứa DTO, util, constants, config, service và helper không liên quan làm module trở thành nơi gom code tùy tiện. Các module khác dần phụ thuộc vào common và ranh giới mờ đi.

Chỉ tạo shared module khi có nhóm API/chức năng ổn định được nhiều consumer dùng. Mỗi thành phần phải có chủ sở hữu và mục đích rõ ràng.

### 17.3. Library chứa framework application

Nếu library kéo theo web framework, persistence provider hoặc server runtime chỉ vì một class dùng annotation, consumer có thể bị ràng buộc với framework đó.

Hãy xem annotation/framework type có thực sự thuộc public contract không. Có thể đặt adapter framework ở application hoặc module adapter riêng, giữ core library thuần Java.

### 17.4. Application truy cập implementation nội bộ

Nếu application import package internal, thay đổi implementation có thể phá consumer. Hãy bổ sung API phù hợp hoặc chuyển phần orchestration vào application.

### 17.5. Dùng test dependency làm production dependency

JUnit, Mockito, Testcontainers và fixture không nên nằm trong production dependency graph của library/application. Dùng testImplementation trong Gradle hoặc test scope trong Maven.

### 17.6. Tách quá nhiều module

Mỗi module thêm một ranh giới build, cấu hình, artifact và chi phí điều phối. Nếu hai phần luôn thay đổi cùng nhau, không có consumer độc lập và không có hợp đồng riêng, có thể package riêng là chưa cần thiết.

Tách module khi có lợi ích rõ như build/test độc lập, ownership, reuse, dependency direction hoặc release boundary.

## 18. Kiểm tra ranh giới bằng thay đổi có chủ đích

Một cách kiểm chứng tốt là thực hiện một số thay đổi nhỏ rồi quan sát module nào cần build lại.

| Thay đổi | Kỳ vọng |
|---|---|
| Sửa test của library | Library test chạy lại; application production code không cần đổi |
| Sửa implementation library nhưng giữ API | Library build/test lại; application có thể compile lại theo dependency/task graph, nhưng source app không cần sửa |
| Sửa public API library | Application consumer có thể cần cập nhật source/compile |
| Sửa main method application | Library không cần đổi source hoặc dependency |
| Sửa cấu hình HTTP/database của app | Library không cần biết thay đổi |
| Thêm dependency chỉ cho app adapter | Dependency chỉ xuất hiện trong application graph |
| Thêm test library | Dependency test chỉ nằm trong test configuration của library |

Build tool incremental behavior có thể chạy thêm task phụ thuộc; điều quan trọng là source/dependency direction không bị đảo. Đừng yêu cầu application không bao giờ compile lại khi library thay đổi API hoặc output.

### 18.1. Kiểm chứng build độc lập

Gradle:

~~~bash
./gradlew :pricing-library:clean :pricing-library:test
~~~

Maven:

~~~bash
./mvnw -pl pricing-library clean verify
~~~

Nếu lệnh chỉ chọn library mà vẫn yêu cầu application artifact, hãy xem source/test dependency hoặc cấu hình build có kéo application ngược vào không.

### 18.2. Kiểm chứng application cần library

Gradle:

~~~bash
./gradlew :storefront-app:build
~~~

Maven:

~~~bash
./mvnw -pl storefront-app -am verify
~~~

Application phải resolve được library qua dependency đã khai báo. Nếu thiếu dependency, compiler sẽ không tìm thấy public API.

### 18.3. Kiểm chứng library không bị app làm bẩn

Có thể tạm loại application khỏi một build thử nghiệm, sau đó chạy library test. Nếu library vẫn build/test được thì đây là bằng chứng tốt về tính độc lập ở cấp build.

Không cần xóa module khỏi repository; chỉ cần gọi task/module selection phù hợp.

## 19. Quy trình thực hành từ dự án một module

Nếu bắt đầu từ một project hiện có, hãy tách theo trình tự để giảm rủi ro.

1. **Lập danh sách class:** phân loại domain/API, implementation nghiệp vụ, entry point, adapter và cấu hình.
2. **Xác định public API:** chọn những type mà consumer thật sự cần dùng.
3. **Tạo build module library:** thêm Gradle subproject hoặc Maven module.
4. **Di chuyển code library:** giữ package ổn định nếu có thể để giảm thay đổi import.
5. **Di chuyển unit test:** đặt test gần module sở hữu logic.
6. **Build library độc lập:** sửa dependency hoặc fixture nào đang tham chiếu application.
7. **Tạo module application:** chuyển main, adapter và cấu hình vào module này.
8. **Khai báo dependency một chiều:** application phụ thuộc library.
9. **Chạy application test:** xác nhận public API đủ dùng.
10. **Kiểm tra dependency graph:** xác nhận không có cycle hoặc dependency ngược.
11. **Kiểm tra artifact:** xác nhận mỗi module tạo output riêng.
12. **Chạy build toàn bộ:** xác nhận reactor/project graph hoàn chỉnh.
13. **Thử thay đổi từng module:** quan sát phạm vi task và source bị ảnh hưởng.
14. **Ghi tài liệu boundary:** nêu trách nhiệm, public API và cách build/test module.

Không nên di chuyển tất cả file trong một lần rồi chỉ sửa compile errors. Phân loại trách nhiệm trước giúp tránh mang nguyên dependency cycle sang cấu trúc mới.

## 20. Checklist xác nhận ranh giới

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Library có build độc lập không? | Task/command chỉ chọn library chạy thành công |
| Library có unit test riêng không? | Test source nằm trong module library |
| App có dependency tới library không? | Gradle dependency hoặc Maven dependency tree thể hiện |
| Library có dependency ngược không? | Build graph và source imports không có app |
| Public API có rõ ràng không? | Package/type public được xác định |
| App có truy cập implementation nội bộ không? | Imports/rule architecture không vi phạm |
| Test dependency có bị đóng gói vào runtime không? | Dependency configuration/scope đúng |
| Artifact module có riêng không? | JAR output riêng cho library và app |
| App distribution có đủ runtime dependency không? | Runtime classpath/distribution được kiểm tra |
| Ranh giới có được kiểm tra tự động không? | Architecture test hoặc build policy |
| Thay đổi app có buộc library biết app không? | Dependency direction vẫn một chiều |
| Consumer khác có thể dùng library không? | Có thể khai báo artifact và dùng public API |

## 21. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Gradle không nhận subproject | Thiếu include trong settings hoặc projectDir sai | Kiểm tra settings.gradle.kts và cấu trúc thư mục |
| Maven báo không tìm thấy library | Chọn riêng app nhưng library chưa có trong repository | Dùng -am trong reactor hoặc cài/publish library trước |
| Library compile được nhưng app không thấy type | Dependency project/artifact chưa khai báo hoặc API không public | Kiểm tra dependency và visibility |
| Build cycle giữa hai module | Dependency khai báo hai chiều | Chuyển abstraction về tầng phù hợp, bỏ dependency ngược |
| Library test cần application config | Test fixture hoặc trách nhiệm bị đặt sai | Đưa logic/config cần thiết vào library API hoặc test library độc lập |
| App import package internal | Public API chưa đủ hoặc implementation đặt sai tầng | Thiết kế API hoặc chuyển orchestration về app |
| JUnit xuất hiện trong runtime JAR | Test dependency khai báo sai scope/configuration | Dùng testImplementation hoặc test scope |
| Application JAR không chạy bằng java -jar | JAR thin, thiếu main manifest hoặc dependency ngoài | Cấu hình launcher/distribution và runtime classpath |
| Maven child không kế thừa plugin config | Plugin chỉ nằm trong pluginManagement nhưng child không kích hoạt | Khai báo plugin trong build/plugins hoặc parent theo ý định |
| Version library không khớp | Module dùng version khác hoặc tọa độ sai | Đồng bộ version/property và kiểm tra reactor |
| Architecture test không phát hiện dependency | Class của module kia không nằm trong import/classpath | Đặt test nơi nhìn thấy cả hai module và kiểm tra build graph riêng |

### 21.1. Maven không resolve module trong reactor

Khi chạy:

~~~bash
./mvnw -pl storefront-app verify
~~~

Maven có thể tìm artifact library trong local/remote repository nếu module library không được chọn trong reactor. Khi muốn build các module cần thiết trong cùng reactor, dùng:

~~~bash
./mvnw -pl storefront-app -am verify
~~~

Tùy chọn -am (also make) chọn thêm các project mà project được chỉ định phụ thuộc. Nó không tự thêm module không liên quan.

### 21.2. Gradle không tìm thấy project dependency

Kiểm tra tên project trong settings, đường dẫn project, khai báo project dependency, cấu trúc multi-project build và task path.

~~~kotlin
dependencies {
    implementation(project(":pricing-library"))
}
~~~

Project path phải khớp tên đã include.

### 21.3. Library có main method

Java không cấm library có class chứa main method, nhưng nếu mục tiêu là một thư viện thuần API thì entry point thường thuộc application. Nếu consumer cần một demo hoặc CLI cho library, hãy cân nhắc tạo module sample/demo riêng thay vì biến library thành ứng dụng.

## 22. Mở rộng: khi nào cần thêm module thứ ba?

Sau khi tách library và application, có thể xuất hiện nhu cầu thêm module:

~~~text
storefront/
├── pricing-library/
├── storefront-app/
├── pricing-persistence-adapter/
└── pricing-test-support/
~~~

Chỉ thêm module khi có trách nhiệm hoặc dependency boundary riêng.

### 22.1. Adapter module

Nếu library định nghĩa port/interface nhưng application có nhiều cách triển khai persistence hoặc external integration, có thể tách adapter:

~~~text
storefront-app -> pricing-persistence-adapter -> pricing-library
~~~

Hướng phụ thuộc cụ thể phụ thuộc thiết kế API/port. Một mô hình thường dùng là core/library khai báo interface; adapter phụ thuộc core để triển khai interface; application kết nối cả hai.

~~~mermaid
flowchart TD
    APP["storefront-app"] --> CORE["pricing-library<br/>domain + port"]
    ADAPTER["pricing-persistence-adapter"] --> CORE
    APP --> ADAPTER
~~~

Core không cần biết adapter tồn tại. Application lắp ghép implementation khi khởi động.

### 22.2. Test support module

Nếu nhiều module cần fixture hoặc builder dùng riêng trong test, có thể tạo test-support module. Tuy nhiên, tránh đưa test utility vào production dependency graph.

Gradle có Java Test Fixtures plugin hỗ trợ chia sẻ fixture cho test consumer. Maven có thể dùng test-jar hoặc module test-support riêng tùy cấu trúc. Cần kiểm soát rõ scope để không đóng gói test support vào artifact production.

### 22.3. Không tạo module chỉ để chứa một class

Một class có thể ở package riêng mà không cần module riêng. Module nên có ranh giới trách nhiệm, dependency hoặc vòng đời build đủ rõ để biện minh cho chi phí cấu hình và quản lý.

## 23. Bài tập thực hành tổng hợp

### Bài 1 — Tách library khỏi application

Tạo hai module pricing-library và storefront-app. Đưa PriceRequest, PriceQuote và PriceCalculator vào library; đưa Main vào application. Xác nhận app import API từ library.

### Bài 2 — Build library độc lập

Chạy task/command chỉ chọn library. Nếu build cần application, tìm dependency hoặc test fixture đang tham chiếu ngược. Sửa cho đến khi library build và test độc lập.

### Bài 3 — Kiểm tra dependency direction

Xem Gradle dependency report hoặc Maven dependency tree của cả hai module. Ghi lại hướng dependency. Xác nhận application phụ thuộc library và library không phụ thuộc application.

### Bài 4 — Tách test theo trách nhiệm

Đưa test quy tắc tính giá vào library. Đưa test luồng ứng dụng vào app. Chạy từng nhóm độc lập và giải thích tại sao test thuộc module đó.

### Bài 5 — Giới hạn API

Tạo một implementation class trong package internal. Thử truy cập từ app. Chuyển app sang dùng public API và giữ implementation không được consumer phụ thuộc trực tiếp.

### Bài 6 — Thêm architecture rule

Dùng ArchUnit trong app test để cấm package pricing phụ thuộc package storefront và cấm application phụ thuộc package pricing.internal. Chạy test và thử tạo một dependency vi phạm để quan sát rule fail.

### Bài 7 — Kiểm tra artifact

Build cả hai module. Liệt kê nội dung JAR. Xác định class nào thuộc library, class nào thuộc app và cách runtime nhận library dependency.

### Bài 8 — Thử thay đổi implementation

Thay cách tính discount trong library nhưng giữ public API. Chạy library test và app test. Xác định module nào cần thay đổi source và module nào chỉ cần kiểm chứng lại.

### Bài 9 — Thử thay đổi public API

Đổi constructor hoặc signature của PriceCalculator. Quan sát compile error ở application. Sửa consumer để phù hợp và ghi nhận vì sao public API là hợp đồng giữa module.

### Bài 10 — Thử tạo dependency cycle

Tạm thêm dependency từ library sang application. Quan sát build graph hoặc compiler/import failure. Gỡ dependency ngược và chuyển abstraction về vị trí phù hợp.

### Bài 11 — So sánh Gradle và Maven

Thực hiện cùng cấu trúc bằng cả hai build tool. So sánh cách khai báo module, project dependency, task selection, reactor build và artifact output.

### Bài 12 — Ghi lại ranh giới

Viết tài liệu ngắn cho từng module gồm trách nhiệm, public API, dependency được phép, test thuộc module và lệnh build độc lập. Một developer mới phải hiểu được hướng phụ thuộc mà không cần suy đoán từ tên thư mục.

## 24. Câu hỏi tự kiểm tra

1. Vì sao tách library và application thành hai build module?
2. Build module khác Java package và JPMS module như thế nào?
3. Trách nhiệm nào nên thuộc library và trách nhiệm nào nên thuộc application?
4. Vì sao dependency nên đi từ application tới library?
5. Nếu library cần gọi hành vi do application cung cấp, có thể tránh dependency ngược bằng cách nào?
6. Gradle settings file có vai trò gì trong multi-project build?
7. Vì sao library dùng java-library plugin thay vì chỉ java plugin khi cần cung cấp API?
8. Gradle api khác implementation như thế nào?
9. Maven aggregator, parent và dependency là ba quan hệ gì?
10. Maven -pl và -am giúp build module ra sao?
11. Vì sao library cần unit test độc lập?
12. Integration test nào nên nằm ở application?
13. ArchUnit kiểm tra được ranh giới nào và cần classpath ra sao?
14. Build module không tự động trở thành JPMS module vì sao?
15. Vì sao application JAR không nhất thiết chứa class của library?
16. Khi nào cần adapter hoặc test-support module?
17. Dấu hiệu nào cho thấy module boundary đang bị vi phạm?
18. Làm thế nào chứng minh library có thể được dùng bởi một application khác?

Tách library và application có giá trị khi ranh giới được thể hiện nhất quán trong build graph, API, source import, test và artifact. Library giữ logic có thể tái sử dụng và hợp đồng ổn định; application điều phối và kết nối với môi trường chạy. Khi build được library độc lập, application chỉ dùng public API và các kiểm tra kiến trúc xác nhận không có dependency ngược, nhóm đã có bằng chứng thực tế rằng module boundary hoạt động đúng.
