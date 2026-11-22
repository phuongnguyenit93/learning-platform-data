# Dự án nhiều module và đồng bộ mức bytecode giữa các artifact

Trong một dự án Java nhiều module, nâng JDK không đơn thuần là thay phiên bản `java` và `javac` trong CI. Một module có thể được biên dịch cho Java 17, module khác cho Java 21, trong khi ứng dụng cuối cùng vẫn được triển khai trên Java 17. Build tổng thể có thể vượt qua một số bước biên dịch nhưng thất bại khi JVM nạp class từ artifact có bytecode quá mới.

Ví dụ một thư viện `common-api.jar` được build với JDK 21 ở mức class file 65, còn một service dùng JDK 17 chỉ hỗ trợ class file đến mức 61. Khi service bắt đầu sử dụng một class của thư viện, nó có thể gặp `UnsupportedClassVersionError`. Việc cả hai module nằm trong cùng Maven reactor hoặc Gradle multi-project build **không làm bytecode của chúng tự động tương thích**.

Vì vậy, trong Java Advance Compatibility Migration cần quản lý rõ ba yếu tố:

1. **Build JDK / toolchain:** JDK nào cung cấp compiler và các build tools?
2. **Target bytecode và Java platform API:** artifact được phép sử dụng những tính năng ngôn ngữ, bytecode và Java API của phiên bản nào?
3. **Runtime tối thiểu của consumer:** JVM nào thực sự phải nạp và chạy artifact đó?

Bài học này hướng dẫn định nghĩa chính sách bytecode cho các module, cấu hình Maven và Gradle, kiểm tra dependencies bắc cầu, xử lý JPMS và multi-release JAR, cùng cách xây dựng release pipeline xác nhận artifact cuối cùng tương thích với JDK đích.

## 1. Một dự án nhiều module có những ranh giới nào?

### 1.1. Module theo nghĩa build tool

Trong Maven, một project tổng có thể bao gồm nhiều child modules:

```text
shop-platform/
  pom.xml
  common-model/
    pom.xml
  pricing-core/
    pom.xml
  payment-adapter/
    pom.xml
  order-service/
    pom.xml
```

Trong Gradle, một multi-project build có thể có cấu trúc tương tự:

```text
shop-platform/
  settings.gradle
  build.gradle
  common-model/
    build.gradle
  pricing-core/
    build.gradle
  payment-adapter/
    build.gradle
  order-service/
    build.gradle
```

Mỗi child module có thể tạo ra một hoặc nhiều artifact: main JAR, test fixtures JAR, sources JAR, generated-code JAR, shadow/fat JAR hoặc container image.

### 1.2. Java module (JPMS) không đồng nghĩa build module

Từ Java 9, Java Platform Module System (JPMS) cho phép một JAR chứa `module-info.class`, khai báo `requires`, `exports` và các quyền truy cập khác. Một Maven/Gradle subproject không bắt buộc là JPMS named module; nó có thể chỉ tạo JAR trên classpath.

Hai khái niệm cần được phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Maven/Gradle module | Đơn vị source, task, dependency và artifact trong build | `:common-model` hoặc `<module>common-model</module>` |
| JPMS module | Đơn vị module graph/runtime có descriptor | `module com.example.common { ... }` |
| JAR artifact | File chứa class/resource được phân phối | `common-model-1.4.0.jar` |
| Deployment unit | Ứng dụng/bản phát hành dùng nhiều artifact | Service JAR + `lib/*.jar` |

Một project có thể tạo nhiều JAR, trong đó chỉ một phần dùng JPMS. Khi lập chính sách bytecode, cần kiểm tra **mọi class thực sự được JVM nạp**, không chỉ tên module trong cấu hình build.

### 1.3. Ví dụ phụ thuộc giữa module

```text
common-model  (Java 17 target)
    |
    +----> pricing-core (Java 17 target)
    |            |
    |            v
    |       order-service (chạy trên Java 17)
    |
    +----> payment-adapter (Java 21 target)
                 |
                 v
            billing-worker (chạy trên Java 21)
```

Nếu `order-service` chỉ phụ thuộc `common-model` và `pricing-core` thì vẫn có thể giữ Java 17, trong khi `billing-worker` dùng Java 21. Tuy nhiên, nếu `order-service` vô tình phụ thuộc ngược vào `payment-adapter` đã build với Java 21, graph trở nên không tương thích với runtime Java 17.

Đây là một lý do nên tách các thư viện dùng chung khỏi adapter hoặc implementation dành riêng cho JDK mới.

## 2. Class-file version là gì?

### 2.1. JVM đọc class file, không đọc nhãn “compiled on JDK X”

Một file `.class` chứa header bao gồm magic number `CAFEBABE` và cặp version minor/major. **Major version** chỉ ra mức định dạng class file cần được JVM hỗ trợ.

Các mốc thường gặp:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 9 | 53 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 23 | 67 |
| Java 24 | 68 |
| Java 25 | 69 |

Ví dụ, khi runtime Java 17 cố nạp class có major 65, nó không thể thực thi class đó theo hợp đồng JVM và có thể báo:

```text
java.lang.UnsupportedClassVersionError:
  com/example/pricing/NewCalculator has been compiled by
  a more recent version of the Java Runtime
  (class file version 65.0),
  this version of the Java Runtime only recognizes
  class file versions up to 61.0
```

Thông báo cụ thể phụ thuộc JDK. Ý nghĩa chung là artifact chứa class được biên dịch cho JVM mới hơn bản đang chạy.

### 2.2. Compiler mới vẫn có thể tạo bytecode cũ

Dùng JDK 21 để biên dịch không có nghĩa file class bắt buộc mang major 65. Nếu dùng `javac --release 17`, compiler JDK 21 có thể tạo bytecode major 61 và giới hạn việc sử dụng các Java SE API tương ứng Java 17.

Ví dụ:

```shell
javac --release 17 -d out src/com/example/App.java
```

Mặt khác, nếu chỉ chạy:

```shell
javac -d out src/com/example/App.java
```

trên JDK 21, mặc định ngôn ngữ và class-file target thường đi theo mức JDK đang chạy compiler. Một module vô tình bỏ cấu hình `--release` có thể tạo bytecode mới hơn phần còn lại của repository.

### 2.3. Tính tương thích là một chiều

Với class bytecode thông thường, JVM mới thường hỗ trợ các class-file versions cũ còn trong phạm vi hỗ trợ của nó. Nhưng điều ngược lại không đúng:

```text
Java 21 runtime
   |
   +-- Nạp Java 17 bytecode: thường được hỗ trợ
   +-- Nạp Java 21 bytecode: được hỗ trợ
   +-- Nạp Java 25 bytecode: không hỗ trợ

Java 17 runtime
   |
   +-- Nạp Java 17 bytecode: được hỗ trợ
   +-- Nạp Java 21 bytecode: không hỗ trợ
```

Đây chỉ là điều kiện ở **class-file level**. Một class major 61 vẫn có thể không chạy trên JDK 17 nếu nó cần thư viện khác không tồn tại, native ABI sai, reflection bị chặn, hoặc runtime configuration không hợp lệ.

### 2.4. Preview features là trường hợp bổ sung

Class file biên dịch với preview feature có thể mang minor version đặc biệt `65535` và yêu cầu runtime hỗ trợ preview của **đúng release** liên quan, cùng tùy chọn `--enable-preview` khi cần.

Một artifact dùng preview của Java 21 không nên được quảng bá như thư viện Java 17 thông thường hoặc là artifact portable giữa mọi JDK mới. Với library dùng chung và bản phát hành cần chạy lâu dài, ưu tiên các tính năng đã trở thành final trừ khi chính sách sản phẩm chấp nhận ràng buộc preview rất rõ.

## 3. “Đồng bộ bytecode” thực sự cần đồng bộ cái gì?

Không nhất thiết mọi module trong repository phải có cùng major version. Điều bắt buộc là **mọi artifact có thể đi vào classpath/module path của một runtime phải đáp ứng ngưỡng của runtime đó**.

Một chính sách có thể là:

```text
common-model        <= Java 17
business-api        <= Java 17
pricing-core        <= Java 17
legacy-adapter      <= Java 17
nextgen-adapter     <= Java 21
order-service       runs on Java 17
billing-worker      runs on Java 21
```

Với `order-service`, toàn bộ dependency closure có thể được JVM nạp phải phù hợp với Java 17. Với `billing-worker`, Java 21 có thể nạp cả các module build cho Java 17 và Java 21.

### 3.1. Phải xem dependency closure, không chỉ module trực tiếp

Giả sử:

```text
order-service (Java 17)
    |
    v
payment-sdk (major 61)
    |
    v
crypto-provider (major 65)
```

Mặc dù `payment-sdk` được biên dịch cho Java 17, nó mang dependency bắc cầu yêu cầu Java 21. Nếu `order-service` cần một class trong `crypto-provider`, JVM Java 17 vẫn có thể lỗi.

Thêm một rule:

> Mức Java tối thiểu của một deployable artifact phải lớn hơn hoặc bằng mức Java tối thiểu của mọi class thực sự có thể được nạp từ dependency closure của nó.

Cần thận trọng với lazy loading: startup có thể thành công nhưng một request cụ thể hoặc plugin được kích hoạt muộn mới truy cập class không tương thích. Vì vậy smoke test khởi động là cần thiết nhưng chưa đủ.

### 3.2. Đồng bộ bytecode khác đồng bộ API

Một thư viện major 61 có thể chứa public API yêu cầu JDK khác hoặc một dependency khác. Ví dụ code được biên dịch bằng `-source 17 -target 17` dưới compiler JDK 21 có thể vô tình tham chiếu Java API chỉ có từ Java 21 nếu không giới hạn bootclasspath/platform API đúng cách.

Do đó, chính sách phải xem hai điều:

1. Class file phù hợp target.
2. Java platform API được tham chiếu có sẵn trên runtime tối thiểu.

`--release` giải quyết hai mục tiêu tốt hơn việc chỉ đặt `source` và `target` trong trường hợp sử dụng `javac` hiện đại.

## 4. Ba tham số hay bị nhầm: source, target và release

### 4.1. `--source`

`--source 17` yêu cầu compiler kiểm tra cú pháp/tính năng Java ở mức source 17. Nó không tự chứng minh Java API được gọi đã có từ Java 17.

### 4.2. `--target`

`--target 17` yêu cầu javac tạo class file phù hợp với target version đã chọn. Điều đó kiểm soát bytecode format, nhưng không nhất thiết kiểm soát đầy đủ API platform nếu compiler dùng class library của JDK mới.

### 4.3. `--release`

`--release 17` trên javac hiện đại kết hợp hạn chế source language, class-file target và Java SE API có sẵn cho release 17.

Ví dụ:

```shell
javac --release 17 -d build/classes src/com/example/Entry.java
```

Đây thường là lựa chọn được khuyến nghị cho Java-only module khi mục tiêu là tạo artifact tương thích với một bản Java cụ thể.

| Cấu hình | Kiểm soát cú pháp | Kiểm soát class major | Giới hạn Java SE API |
|---|---|---|---|
| `--source` đơn lẻ | Có | Phụ thuộc cài đặt khác/default | Không đầy đủ |
| `--target` đơn lẻ | Không phải mục tiêu chính | Có | Không đầy đủ |
| `--source` + `--target` | Có | Có | Không đầy đủ nếu dùng JDK mới để compile |
| `--release` | Có | Có | Có, trong phạm vi Java SE platform API |

`--release` không kiểm tra API của **third-party dependencies** đã được chọn trong graph và không tự kiểm tra native library, reflection hoặc behavior runtime.

### 4.4. Build JDK khác runtime JDK

Ví dụ một dự án dùng JDK 21 làm toolchain nhưng muốn phát hành Java 17-compatible library:

```text
Build JDK                 : 21
javac --release           : 17
Artifact class major      : 61
Supported runtime floor   : 17
CI test runtimes          : 17 và 21
```

Build thành công trên JDK 21 chưa chứng minh thư viện chạy trên JDK 17; phải chạy ít nhất bộ test phù hợp với Java 17 để xác nhận dependency/runtime closure.

## 5. Lập ma trận mức bytecode cho toàn repository

Một ma trận giúp tránh việc từng module tự quyết target:

| Module | Loại artifact | Build JDK | Target release | Runtime tối thiểu | Consumer |
|---|---|---:|---:|---:|---|
| `common-model` | Library JAR | 21 | 17 | 17 | Các service cũ và mới |
| `pricing-api` | Library JAR | 21 | 17 | 17 | Pricing service, order service |
| `pricing-core` | Library JAR | 21 | 17 | 17 | Order service |
| `nextgen-payment` | Adapter JAR | 21 | 21 | 21 | Billing worker |
| `order-service` | Application JAR | 21 | 17 | 17 | Production Java 17 |
| `billing-worker` | Application JAR | 21 | 21 | 21 | Production Java 21 |

Các con số là ví dụ thiết kế, không phải thông tin về một repository cụ thể.

### 5.1. Quy tắc cho public library

Nếu `common-model` được chia sẻ bởi consumer còn dùng Java 17, nên giữ class-file target và dependencies phù hợp Java 17. Không nâng target lên Java 21 chỉ vì tất cả developer đã cài JDK 21.

Một library có thể được biên dịch bằng compiler mới nhưng xuất bản dưới bytecode cũ. Điều quan trọng là không sử dụng source/API chỉ có ở release cao hơn trong phần library phải hỗ trợ runtime cũ.

### 5.2. Quy tắc cho application

Application deployable có thể chọn target bằng runtime production. Nếu service chỉ chạy trên Java 21, các module implementation riêng của nó có thể dùng Java 21. Nhưng thư viện chia sẻ với Java 17 vẫn cần giữ target cũ hoặc tách artifact.

### 5.3. Quy tắc cho test code

Test sources không nhất thiết có cùng target với main sources. Một build có thể compile main library cho Java 17 nhưng test framework chạy trên Java 21. Việc đó có thể hợp lý, song **không đủ để chứng minh Java 17 compatibility**.

Cần ít nhất một job thực thi bộ test dành cho thư viện trên runtime thấp nhất được cam kết, hoặc một test suite riêng xác minh API và runtime closure. Test fixtures được publish cho các consumer khác cũng cần chính sách bytecode như library bình thường.

## 6. Maven multi-module: tập trung cấu hình tại parent POM

### 6.1. Parent aggregator và các child modules

Một root `pom.xml` ví dụ:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example.shop</groupId>
  <artifactId>shop-platform</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>

  <modules>
    <module>common-model</module>
    <module>pricing-core</module>
    <module>order-service</module>
  </modules>

  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
  </properties>
</project>
```

Khi các child khai báo parent tương ứng, thuộc tính và cấu hình plugin được kế thừa theo quy tắc Maven. Nếu root chỉ là aggregator mà child **không kế thừa** root làm parent, các property này không tự động có hiệu lực ở child.

### 6.2. Quản lý compiler plugin tập trung

Trong parent POM:

```xml
<build>
  <pluginManagement>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>
    </plugins>
  </pluginManagement>
</build>
```

Ví dụ minh họa việc pin compiler plugin và release target; dự án cần chọn phiên bản plugin phù hợp với Maven/JDK đang sử dụng.

Lưu ý `pluginManagement` định nghĩa version/configuration cho plugin khi được sử dụng, không nhất thiết tự thêm execution của mọi plugin vào lifecycle. Với packaging `jar`, compiler plugin thường được Maven lifecycle sử dụng, nhưng cách kế thừa và override cần được kiểm tra bằng effective POM thực tế.

### 6.3. Child module kế thừa parent

`common-model/pom.xml` có thể khai báo:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>com.example.shop</groupId>
    <artifactId>shop-platform</artifactId>
    <version>1.0.0</version>
  </parent>

  <artifactId>common-model</artifactId>
</project>
```

Với cấu hình parent ở trên, module này dự kiến được biên dịch cho Java 17. Nếu một child sử dụng plugin execution tùy chỉnh, Kotlin/Scala compiler, annotation processor riêng hoặc dùng cấu hình build khác, vẫn cần xác nhận đầu ra thực tế.

### 6.4. Override có chủ đích cho module Java 21

Nếu `billing-worker` chỉ chạy trên Java 21, có thể override property ở child:

```xml
<properties>
  <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Tuy nhiên, nếu cấu hình compiler plugin ở parent **hard-code** `<release>17</release>` thì property override này sẽ không có tác dụng như mong đợi. Cách dễ kiểm soát hơn là parent tham chiếu property:

```xml
<properties>
  <java.release>17</java.release>
</properties>

<build>
  <pluginManagement>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>${java.release}</release>
        </configuration>
      </plugin>
    </plugins>
  </pluginManagement>
</build>
```

Khi đó child có thể đặt `<java.release>21</java.release>`. Trong POM thực tế cần bảo đảm chỉ có một nguồn quyết định `release` hiệu lực, tránh cấu hình xung đột giữa properties và plugin executions.

### 6.5. Maven reactor không chuẩn hóa bytecode tự động

Lệnh từ root:

```shell
./mvnw clean verify
```

sẽ xây các modules theo dependency graph của Maven reactor, nhưng **không có nghĩa mọi module dùng cùng `--release`**. Child có thể override cấu hình compiler hoặc dùng compiler plugin/version khác.

Các mốc cần xác minh:

- Effective POM của từng child.
- Build JDK và Maven Toolchains thực tế.
- Compiler plugin version và `release` cuối cùng.
- Main và test compile configurations.
- Generated classes do processor hoặc plugin phát sinh.
- Nested/shaded JAR được đưa vào deployable artifact.

### 6.6. Kiểm tra effective POM

```shell
./mvnw -pl common-model help:effective-pom
```

Hoặc xem cấu hình cho module riêng trong quy trình CI. Báo cáo giúp xác định cấu hình được kế thừa sau khi kết hợp parent, profiles và plugins.

Maven profile kích hoạt theo JDK, OS hoặc property có thể làm thay đổi compiler target. Cần ghi nhận active profiles và lệnh release thực tế; không chỉ đọc parent POM.

## 7. Maven Toolchains và môi trường biên dịch

### 7.1. Pin compiler JDK

Java toolchain giúp Maven sử dụng một JDK cụ thể cho tool hỗ trợ toolchain, thay vì luôn dùng JDK chạy Maven.

Tình huống:

```text
Maven process chạy bằng JDK 21
Java compiler được chọn từ JDK 21
--release 17
Đầu ra main JAR có major 61
```

Điều này phù hợp nếu build tool và plugin hỗ trợ JDK 21. Nhưng để xác nhận runtime Java 17, cần có test bằng Java 17, không chỉ compile.

### 7.2. Ví dụ cấu hình Toolchains Plugin

Một cách triển khai trong parent POM:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-toolchains-plugin</artifactId>
  <version>3.2.0</version>
  <executions>
    <execution>
      <goals>
        <goal>toolchain</goal>
      </goals>
    </execution>
  </executions>
  <configuration>
    <toolchains>
      <jdk>
        <version>21</version>
      </jdk>
    </toolchains>
  </configuration>
</plugin>
```

Đây là ví dụ dành cho môi trường đã khai báo JDK 21 trong cấu hình toolchains tương ứng. Cần đối chiếu cú pháp với Maven Toolchains Plugin version đang sử dụng và bảo đảm đường dẫn JDK thực tế có thể được phát hiện. Không nhầm việc chọn compiler JDK với việc đặt bytecode target.

### 7.3. Java 8 target không có nghĩa compile bằng JDK 8

Một compiler JDK mới có thể dùng `--release 8` để tạo code cho Java 8 trong phạm vi được hỗ trợ. Nhưng Java 8 compiler bản thân không hỗ trợ tùy chọn `--release`, và những language features như record hoặc sealed class không thể được biên dịch xuống Java 8 chỉ bằng thay target.

Nếu cần một thư viện hỗ trợ Java 8, source của thư viện phải tránh syntax và API sau Java 8 (trừ khi cấu trúc multi-release hoặc source set riêng được thiết kế đúng). Sau đó cần test trên JVM Java 8 để xác minh dependency closure.

## 8. Gradle multi-project: cấu hình thống nhất từ root

### 8.1. Khai báo modules trong settings

`settings.gradle`:

```groovy
rootProject.name = 'shop-platform'

include 'common-model'
include 'pricing-core'
include 'order-service'
include 'billing-worker'
```

Khai báo này định nghĩa một multi-project build, nhưng bản thân nó không buộc các subprojects dùng cùng Java toolchain hoặc target release.

### 8.2. Một cấu hình chung cho Java subprojects

Ví dụ root `build.gradle` theo Groovy DSL:

```groovy
subprojects {
    plugins.withId('java') {
        java {
            toolchain {
                languageVersion = JavaLanguageVersion.of(21)
            }
        }

        tasks.withType(JavaCompile).configureEach {
            options.release = 17
            options.encoding = 'UTF-8'
        }
    }
}
```

Ý tưởng:

- Chỉ cấu hình khi plugin Java được áp dụng.
- Dùng Java 21 toolchain làm compiler.
- Tạo Java classes ở mức release 17.
- Áp dụng cho những `JavaCompile` tasks trong phạm vi phù hợp.

Trong hệ thống lớn, một **convention plugin** thường dễ mở rộng và kiểm thử hơn cấu hình `subprojects` trực tiếp trong root. Cần chọn theo cấu trúc repository và Gradle version cụ thể.

### 8.3. Child module áp dụng Java plugin

`common-model/build.gradle`:

```groovy
plugins {
    id 'java-library'
}
```

`pricing-core/build.gradle`:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api project(':common-model')
}
```

`order-service/build.gradle`:

```groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':pricing-core')
}

application {
    mainClass = 'com.example.order.Main'
}
```

Nếu cấu hình chung áp dụng đúng, các task JavaCompile có target 17. Tuy nhiên, Gradle build gồm cả Kotlin/Scala/Groovy hoặc task custom thì cần chính sách compiler riêng.

### 8.4. Override mức target cho module riêng

Nếu một subproject chỉ được dùng trên Java 21:

```groovy
plugins {
    id 'java-library'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

**Cẩn trọng thứ tự và xung đột cấu hình.** Nếu root hoặc convention plugin vẫn có logic ghi đè `options.release` sau đó, giá trị cuối có thể không đúng ý định. Với repository lớn, nên thiết kế một property/convention duy nhất để module đặt target, thay vì nhiều chỗ cùng sửa task.

Một convention plugin có thể đọc thuộc tính thống nhất như `javaRelease=17` hoặc `javaRelease=21` theo quy trình đã được kiểm soát. Điều quan trọng là policy được công bố và kết quả task được kiểm chứng.

### 8.5. Toolchain không phải target bytecode

Trong Gradle:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

chỉ định toolchain JDK, không tự buộc artifact phải có major 61. Nếu không có `options.release = 17` hoặc cấu hình source/target tương đương, JavaCompile có thể tạo Java 21 bytecode.

Tương tự, JDK chạy Gradle daemon có thể khác JDK dùng bởi `JavaCompile` và `Test`. Hãy phân biệt ba thông tin khi debug:

```text
Gradle daemon JVM     : ?
JavaCompile toolchain : ?
JavaCompile release   : ?
Test JVM              : ?
```

## 9. Build logic và convention plugins thay vì cấu hình phân tán

Một repository nhiều module dễ phát sinh “configuration drift”:

```text
common-model  release=17
pricing-core  release=17
order-service release=17
payment-api   release=21  <-- vô ý
billing-worker release=21
```

Để hạn chế, xây một convention build logic:

- Định nghĩa default release chung.
- Cho phép override có chủ đích theo module.
- Có danh sách modules được quyền target Java 21.
- Thiết lập encoding và compiler flags nhất quán.
- Cấu hình test runtimes theo chính sách.
- Tạo report về target release của từng artifact.
- Tránh task compile tùy chỉnh bỏ qua policy.

### 9.1. Tên module không quyết định target

Một module có tên `legacy-*` không nhất thiết phải target Java 8; một module `nextgen-*` không tự được phép target Java 21. Policy phải được khai báo và review trong build configuration.

### 9.2. Đừng chỉ xem `sourceCompatibility` và `targetCompatibility`

Một số Gradle build cũ:

```groovy
sourceCompatibility = JavaVersion.VERSION_17
targetCompatibility = JavaVersion.VERSION_17
```

Hai property này có thể kiểm soát ngôn ngữ và bytecode, nhưng không tương đương hoàn toàn với `javac --release 17` về giới hạn Java SE API khi compiler chạy trên JDK mới.

Đối với JavaCompile trên JDK hỗ trợ `--release`, ưu tiên `options.release` nếu mục tiêu là hỗ trợ một runtime cũ. Sau đó test với JDK cũ thật để phát hiện dependency và runtime behavior.

## 10. Java modules, JPMS và module-info.class

### 10.1. Module descriptor có mức bytecode riêng

`module-info.java` là cú pháp Java 9+, do đó không thể biến một JAR thuần Java 8 thành một JPMS named module thông thường chỉ bằng đặt module descriptor vào root với bytecode Java 8.

Một module sử dụng:

```java
module com.example.pricing {
    requires com.example.common;
    exports com.example.pricing.api;
}
```

cần được build theo quy tắc JPMS trên JDK hỗ trợ modules. Nếu Java 17 là runtime tối thiểu, compile module descriptor và classes với `--release 17` là một lựa chọn bình thường.

### 10.2. Named module không làm dependency cũ tự tương thích

JPMS giúp mô tả readability và exports, nhưng không sửa class-file version của transitive dependencies. Nếu module graph có một artifact major 65 và runtime là Java 17, class đó vẫn không thể được nạp.

Cần xác minh cả:

- Module graph/`requires`.
- Package exports và opens.
- Java class major versions.
- Runtime dependencies và service providers.
- Classpath versus module path placement.

### 10.3. Dùng JAR trên classpath không có nghĩa JDK 8-only

Một JAR không có `module-info.class` có thể chứa class major 65. Ngược lại, một JAR có JPMS descriptor có thể có các thành phần được biên dịch cho các release khác nhau theo quy tắc multi-release JAR.

Hãy kiểm tra **file bên trong artifact**, không chỉ sự hiện diện hoặc vắng mặt của module descriptor.

## 11. Multi-release JAR: dùng bytecode khác nhau một cách có chủ đích

### 11.1. Mục tiêu của multi-release JAR

Multi-release JAR (MR-JAR, từ Java 9) cho phép một JAR mang base classes dành cho JDK cũ và các bản class thay thế dành cho JDK mới.

Ví dụ cấu trúc:

```text
library.jar
  META-INF/MANIFEST.MF
  com/example/codec/Codec.class
  META-INF/versions/17/com/example/codec/Codec.class
  META-INF/versions/21/com/example/codec/Codec.class
```

Manifest có:

```text
Multi-Release: true
```

Một runtime hỗ trợ multi-release JAR có thể chọn bản class phù hợp với version của nó. Ví dụ Java 17 dùng variant Java 17; Java 21 có thể dùng variant Java 21; Java 8 dùng base class.

Đây là cơ chế **được thiết kế để nhiều class-file versions cùng nằm trong một artifact**. Vì vậy một checker “mọi class trong JAR phải có major <= 52” sẽ từ chối nhầm một MR-JAR hợp lệ có base Java 8 và các version-specific classes được đặt đúng chỗ.

### 11.2. Quy tắc kiểm tra MR-JAR

Cần xác định:

1. Manifest có `Multi-Release: true`.
2. Base classes dùng target dành cho runtime thấp nhất.
3. Class ở `META-INF/versions/N` chỉ dùng bytecode/API phù hợp với release N theo quy tắc của MR-JAR.
4. Những variant mới không làm public API bất ngờ thay đổi so với base contract.
5. Artifact chạy trên mọi runtime thuộc support matrix.
6. Build/packaging plugin có giữ nguyên entry layout và manifest.

Đừng coi việc bỏ class Java 21 vào `META-INF/versions/21` là đủ để bảo đảm hợp lệ. Phải xác minh cấu trúc, API consistency và behavior khi JVM chọn variant.

### 11.3. `module-info.class` trong multi-release JAR

Một số thư viện hỗ trợ Java 8 nhưng muốn công bố module descriptor từ Java 9 có thể đặt `module-info.class` phù hợp trong vùng versioned entries. Đây là trường hợp đòi build setup đặc biệt.

Không nên chỉ đặt một `module-info.class` major 53 vào root của JAR rồi tuyên bố artifact vẫn hỗ trợ Java 8 theo cách thông thường. Hãy dùng packaging và module metadata được hỗ trợ bởi plugin phù hợp, kiểm thử `jar --describe-module` và thử thực tế trên các JDK mục tiêu.

### 11.4. Giới hạn của MR-JAR

MR-JAR không giải quyết mọi khác biệt:

- Native dependencies có thể vẫn khác theo OS/architecture.
- Module readability hoặc reflective access vẫn phụ thuộc runtime.
- Dependency closure của bản Java 21 có thể khác bản Java 17.
- Classpath scanner hoặc bytecode analysis tool cũ có thể đọc sai versioned entries.
- Shading/relocation có thể làm hỏng bố cục MR-JAR nếu plugin không hỗ trợ.

Chỉ dùng MR-JAR khi cần tối ưu cùng một thư viện cho nhiều JDK và có hạ tầng kiểm thử tương ứng. Nếu phiên bản Java 21 thay đổi API công khai hoặc semantics lớn, phát hành artifact riêng có versioning rõ đôi khi dễ bảo trì hơn.

## 12. Dependency từ bên ngoài cũng quyết định runtime floor

### 12.1. Version mới có thể yêu cầu JDK cao hơn

Giả sử một version của thư viện serialization chuyển compiler target từ Java 11 sang Java 17. Nếu consumer vẫn chạy Java 11, nâng version dù “minor” có thể làm lỗi khi nạp class.

Khi nâng JDK/multi-module, cần kiểm tra:

- Minimum supported Java version của mỗi thư viện.
- Class-file major của JAR thật.
- Variants metadata hoặc module-specific dependencies.
- Release notes về API bị loại bỏ.
- JDK target của annotation processor, codegen plugin và Java agent.
- Native library classifier theo OS/architecture.

### 12.2. Gradle variant matching có thể hỗ trợ chọn thư viện

Gradle Module Metadata có thể công bố attribute như `org.gradle.jvm.version`, giúp consumer lựa chọn những variants tương thích với target JVM theo cấu hình và rule của Gradle.

Tuy nhiên:

- Không phải mọi JAR đều công bố metadata này.
- Maven POM có mức metadata khác với Gradle Module Metadata.
- Một thư viện có thể công bố metadata sai hoặc thiếu.
- Một fat JAR hoặc artifact tự build có thể chứa class versions không phản ánh qua metadata.
- Runtime thực tế vẫn phải được kiểm thử.

Không coi variant selection là chứng nhận rằng toàn bộ graph đã được quét bytecode và xác minh tương thích.

### 12.3. Maven dependency tree không kiểm tra class major

`mvn dependency:tree` hữu ích để thấy các version đã được chọn nhưng bản thân nó không phân tích toàn bộ bytecode. Một dependency được chọn đúng theo POM vẫn có thể chứa class quá mới.

Do đó cần hai bước độc lập:

1. **Dependency resolution inspection:** xác định các artifact thực tế.
2. **Artifact bytecode inspection:** xác định major versions và các đặc điểm đặc biệt như multi-release.

## 13. Shading, fat JAR và executable distribution

### 13.1. Artifact cuối có thể khác module JAR gốc

Một module `order-service` có thể compile với `--release 17` nhưng task `shadowJar` hoặc Spring Boot packaging lại gói chung dependency target Java 21.

Ví dụ:

```text
order-service classes      major 61
common-model classes       major 61
payment-provider classes   major 65
          |
          v
application-all.jar         chứa cả major 61 và 65
```

Nếu deploy trên Java 17, vấn đề vẫn còn dù module chính biên dịch đúng.

Do đó, artifact kiểm tra cuối cùng phải bao gồm:

- Classes của module chính.
- Shaded/relocated class entries.
- Nested dependency JARs nếu đóng gói theo cấu trúc nested.
- Runtime `lib/*.jar` trong application distribution.
- Plugin JARs được nạp động.
- Java agents hoặc native launcher libraries nếu là một phần deployment.

### 13.2. Nested JAR và fat JAR cần cách kiểm tra riêng

Một số executable JAR không giải nén dependency classes vào root mà chứa nested archives:

```text
BOOT-INF/classes/...
BOOT-INF/lib/library-a.jar
BOOT-INF/lib/library-b.jar
```

Một công cụ chỉ quét `*.class` trực tiếp ở root có thể bỏ qua toàn bộ dependency nested. Cần liệt kê hoặc trích xuất nested archives vào khu vực kiểm tra, hoặc dùng tool hỗ trợ format đóng gói đó.

Không chỉ chạy `javap` trên main class của ứng dụng rồi kết luận artifact hoàn chỉnh tương thích.

### 13.3. Bytecode transformer cũng có ảnh hưởng

Shading, relocation, weaving, obfuscation, bytecode enhancement và instrumentation có thể:

- Sinh class file mới.
- Giữ nguyên bytecode major của dependency.
- Gặp lỗi khi xử lý class version mới mà transformer cũ chưa hiểu.
- Thay đổi `module-info.class` hoặc multi-release entries.
- Tạo adapter/runtime proxy ở mức bytecode khác.

Ví dụ thư viện ASM, Byte Buddy hoặc Javassist quá cũ có thể không hỗ trợ class-file versions mới. Nên cập nhật transformer/agent phù hợp với JDK mục tiêu, kiểm tra output sau transform và thử runtime thực tế.

### 13.4. Generated code và annotation processors

Một số code generator tạo **Java source** rồi giao lại cho `javac`, nên `--release` của compile task có thể kiểm soát class output đó. Nhưng công cụ khác có thể trực tiếp ghi bytecode hoặc copy precompiled JAR.

Với mỗi generated artifact, hỏi:

- Source hay bytecode được sinh ra?
- Task nào chịu trách nhiệm?
- Compiler/toolchain nào được dùng?
- Có chạy trong Gradle/Maven configuration chính không?
- Artifact có được đóng gói vào release không?

Không mặc định generated classes tuân theo `options.release` chỉ vì main JavaCompile có cấu hình đúng.

## 14. Kotlin, Groovy, Scala và build đa ngôn ngữ

Một multi-module repository thường chứa hơn một ngôn ngữ JVM. Các ngôn ngữ này có compiler options và phiên bản plugin riêng.

### 14.1. Kotlin JVM target

Ví dụ Kotlin Gradle DSL sử dụng compiler options theo Kotlin Gradle Plugin hỗ trợ API này:

```kotlin
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

kotlin {
    jvmToolchain(21)

    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}
```

`jvmToolchain(21)` chọn toolchain, còn `jvmTarget` ảnh hưởng bytecode Kotlin. Cần kiểm tra Java source compilation target và Kotlin target có phù hợp nhau, đồng thời test trên Java 17 nếu consumer phải hỗ trợ bản này.

Cú pháp phụ thuộc Kotlin Gradle Plugin version; không copy vào project cũ mà không kiểm tra plugin hiện có.

### 14.2. Groovy và Scala

Groovy/Scala có compiler và target options riêng, tùy plugin/version. Các class chúng sinh ra cũng có class-file major và phải tương thích runtime tiêu thụ.

Không dùng riêng Maven Compiler Plugin hoặc Gradle JavaCompile target để kết luận bytecode Groovy/Scala đã đồng bộ. Cần xác định task compile tương ứng và kiểm tra class output.

### 14.3. Test fixtures và codegen

Nếu module publish test fixtures, stubs hoặc generated clients, chúng có thể được tải bởi một dự án khác đang chạy Java cũ. Vì vậy, “chỉ dùng trong test” chưa đủ để bỏ kiểm soát bytecode nếu artifact được phân phối.

Nguyên tắc chung: **bất kỳ artifact JVM nào có consumer độc lập đều cần công bố target và verify output**.

## 15. Kiểm tra class-file version trong artifact

### 15.1. Xem class major bằng javap

Ví dụ sau khi build:

```shell
javap -verbose -classpath path/to/common-model.jar \
    com.example.common.CustomerId
```

Trong output, tìm dòng:

```text
major version: 61
```

Dòng này cho biết class được kiểm tra có major 61, tương ứng Java 17. Nhưng nó không xác nhận mọi class trong JAR đều ở mức đó.

Trên Windows PowerShell, có thể chạy một dòng:

```powershell
javap -verbose -classpath "path/to/common-model.jar" com.example.common.CustomerId
```

Nếu class nằm trong nested JAR, cần trỏ đến classpath phù hợp hoặc giải nén phần cần kiểm tra trước.

### 15.2. Xem nội dung JAR

```shell
jar --list --file path/to/common-model.jar
```

Kiểm tra:

- `.class` ở root hoặc package directory.
- `module-info.class`.
- `META-INF/versions/...`.
- Nested JAR.
- Manifest và `Multi-Release` attribute.

Nếu thấy module `META-INF/versions/21`, không nên tự kết luận JAR Java 17-incompatible khi chưa kiểm tra manifest và base/versioned class selection.

### 15.3. Xem module descriptor

```shell
jar --describe-module --file path/to/library.jar
```

Lệnh giúp xác định metadata module khi có hoặc trạng thái automatic module tùy artifact. Nó không phải công cụ kiểm thử class-file version toàn bộ JAR.

### 15.4. Dùng jdeps để kiểm tra dependencies

```shell
jdeps --jdk-internals path/to/library.jar
```

`jdeps` hữu ích khi kiểm tra sử dụng JDK internal API có thể gặp vấn đề sau migration. Với MR-JAR, có thể dùng tùy chọn `--multi-release` ở những chế độ phân tích được hỗ trợ:

```shell
jdeps --multi-release 17 path/to/library.jar
```

`jdeps` không thay thế bytecode-major scan, và không nhìn thấy mọi dependency được tải động qua reflection hoặc plugin.

## 16. Quét major version bằng Java

Để kiểm tra một JAR không phải MR-JAR, có thể viết một chương trình nhỏ đọc header của các `.class` entries:

```java
import java.io.DataInputStream;
import java.io.IOException;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public final class ClassVersionScanner {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: ClassVersionScanner <jar> <maxMajor>"
            );
        }

        String path = args[0];
        int maxMajor = Integer.parseInt(args[1]);

        boolean failed = false;

        try (JarFile jar = new JarFile(path)) {
            var entries = jar.entries();

            while (entries.hasMoreElements()) {
                JarEntry entry = entries.nextElement();

                if (!entry.getName().endsWith(".class")) {
                    continue;
                }

                try (DataInputStream input =
                         new DataInputStream(jar.getInputStream(entry))) {

                    int magic = input.readInt();
                    int minor = input.readUnsignedShort();
                    int major = input.readUnsignedShort();

                    if (magic != 0xCAFEBABE) {
                        throw new IOException(
                            "Invalid class file: " + entry.getName()
                        );
                    }

                    if (major > maxMajor) {
                        failed = true;
                        System.err.printf(
                            "%s: major=%d minor=%d exceeds %d%n",
                            entry.getName(), major, minor, maxMajor
                        );
                    }
                }
            }
        }

        if (failed) {
            System.exit(1);
        }
    }
}
```

Ví dụ logic:

```shell
java ClassVersionScanner path/to/common-model.jar 61
```

Nếu class có major lớn hơn 61, chương trình báo lỗi và trả exit code 1. Mẫu này phù hợp để minh họa nguyên tắc kiểm tra header, nhưng có các giới hạn quan trọng:

1. Nó chưa xử lý MR-JAR theo semantics của `META-INF/versions/N`.
2. Nó chưa quét các nested JAR.
3. Nó chưa phân biệt các class preview có minor 65535.
4. Nó chưa đánh giá Java platform API hoặc third-party dependencies.
5. Nó chưa xác thực chữ ký hay kiểm tra runtime behavior.

Với production CI, nên dùng plugin/tool đã được quản lý hoặc mở rộng scanner theo định dạng artifact thật. **Không áp dụng kết quả scanner đơn giản này như một phán quyết cuối cùng cho MR-JAR.**

## 17. Cách đọc version của một class file

Nếu muốn tự hiểu header:

```text
Offset    Số byte   Ý nghĩa
0         4         magic: CAFEBABE
4         2         minor_version
6         2         major_version
8         ...       constant pool và các phần khác
```

Ví dụ major 61 là Java 17; major 65 là Java 21.

Một class có major hợp lệ vẫn có thể chứa instruction hoặc metadata không được compiler/runtime dự kiến nếu bytecode bị sửa sai. Việc tự đọc header chỉ trả lời câu hỏi format version, không phải bảo đảm class file hợp lệ. JVM verification hoặc công cụ phân tích bytecode đầy đủ là những lớp kiểm tra khác.

## 18. Bytecode compatibility trong Maven: các cách kiểm soát

### 18.1. Kiểm soát tại compiler

Dùng parent POM với một source of truth cho `maven.compiler.release` hoặc property riêng được compiler plugin tham chiếu.

### 18.2. Kiểm soát dependency và artifact

Dùng `dependencyManagement`/BOM để lựa chọn dependency versions có Java support phù hợp. Pin plugin versions và kiểm tra graph.

### 18.3. Kiểm soát bằng Maven Enforcer hoặc plugin chuyên dụng

Maven Enforcer Plugin có rules hỗ trợ quản lý Maven/JDK versions và dependency graph. Một số rule kiểm tra bytecode version của dependencies, chẳng hạn `enforceBytecodeVersion`, đến từ **extra-enforcer-rules** hoặc công cụ bổ sung, không phải tất cả đều thuộc bộ rules built-in mặc định của Maven Enforcer.

Khi thiết lập, cần kiểm tra:

- Plugin và rules dependency đúng phiên bản.
- Phạm vi include/exclude.
- Test artifacts và optional dependencies.
- Multi-release JAR support.
- Nested archives hoặc shaded output.
- Runtime tối thiểu được công bố.
- Quy tắc xử lý phụ thuộc khác OS/architecture.

Không thêm một tên rule vào POM mà chưa xác nhận plugin dependency cung cấp rule đó.

### 18.4. Maven profiles cho nhiều target

Có thể cần nhiều profile hoặc module-specific properties khi một repository phát hành artifact Java 17 và Java 21. Tuy nhiên, profiles làm tăng rủi ro khác nhau giữa môi trường nếu tự kích hoạt theo JDK/OS.

Ưu tiên cấu hình target của từng module có thể đọc được và kiểm soát bằng version control. Nếu dùng profiles, release pipeline phải ghi rõ profile nào được kích hoạt và xác minh output của từng biến thể.

## 19. Bytecode compatibility trong Gradle: các cách kiểm soát

### 19.1. Kiểm soát JavaCompile

Dùng `java.toolchain` và `tasks.withType(JavaCompile).configureEach { options.release = ... }` theo chính sách đã định.

### 19.2. Kiểm soát dependency graph

Với Gradle Module Metadata, khả năng chọn variant theo `org.gradle.jvm.version` có thể giúp tránh một số dependencies không tương thích. Đồng thời dùng version constraints/BOM/dependency locking để giữ graph có thể truy vết.

Không coi dependency locking là bytecode scanning: lockfile lưu versions được chọn, không bảo đảm class major của mọi JAR.

### 19.3. Kiểm soát sau khi đóng gói

Gradle có thể tạo JAR, Shadow JAR, distribution ZIP hoặc container image. Artifact verification phải kiểm tra đúng output cuối cùng, không chỉ `classes` task.

Ví dụ các task Gradle thông dụng:

```shell
./gradlew :common-model:jar
./gradlew :order-service:distZip
```

Lệnh chỉ minh họa build outputs, không có nghĩa một scanner mặc định đã được kích hoạt. Hãy gắn bước kiểm tra artifact vào pipeline nếu sản phẩm cần chứng nhận mức bytecode.

### 19.4. Metadata khi publish thư viện

Một module Gradle `java-library` khi publish có thể mang thông tin về target JVM thông qua Gradle Module Metadata. Điều này giúp consumer Gradle chọn variant phù hợp trong những tình huống hỗ trợ.

Nhưng người dùng Maven có thể chỉ nhận POM/JAR mà không tiêu thụ đầy đủ metadata Gradle. Vì vậy, công bố minimum Java version rõ ràng trong release notes và kiểm tra JAR thật vẫn cần thiết.

## 20. Các trường hợp dễ bị bỏ sót

### 20.1. Java agent

Application có thể dùng `-javaagent:agent.jar`. Agent là artifact JVM riêng và có thể được nạp rất sớm trong quá trình khởi động. Nếu agent có major quá mới hoặc thư viện ASM nội bộ không hiểu bytecode ứng dụng, runtime có thể lỗi trước khi main class chạy.

### 20.2. Annotation processor

Processor chạy trong quá trình compile và thường cần tương thích với **JDK của compiler**, không nhất thiết cùng target release của classes đầu ra.

Ví dụ một processor chạy bằng JDK 21 có thể dùng API Java 21 để phân tích AST, nhưng phải bảo đảm source/classes mà nó sinh ra vẫn hợp lệ với `--release 17` nếu mục tiêu là Java 17 library.

### 20.3. Test runner và mock framework

JUnit, Mockito, Byte Buddy hoặc code coverage agent có thể yêu cầu JDK tối thiểu khác với main library. Chúng không nhất thiết được publish trong runtime artifact, nhưng sẽ quyết định khả năng chạy test trên JDK 17 trong CI.

Cần tách lỗi “tool test không chạy trên Java 17” khỏi lỗi “library không chạy trên Java 17”. Nếu library cam kết hỗ trợ Java 17 nhưng test stack mới chỉ chạy Java 21, cần một bộ compatibility tests riêng chạy trên Java 17.

### 20.4. Generated clients và stubs

OpenAPI/GraphQL/gRPC generators có thể tạo mã Java hoặc bytecode. Nếu generate step chuyển framework sang code dùng Java 21 API, compiler `--release 17` thường phát hiện API source không phù hợp. Nhưng nếu đưa thẳng một generated JAR major 65 vào distribution, vấn đề có thể chỉ lộ khi chạy.

### 20.5. Runtime plugin loading

Ứng dụng có thể chạy ổn đến khi nạp plugin qua `ServiceLoader`, `ClassLoader` hoặc script engine. Plugin artifact có lifecycle và compatibility matrix riêng; phải được tính vào dependency closure của ứng dụng.

### 20.6. JNI và native dependencies

Bytecode major không nói lên khả năng nạp native library. Một JAR major 61 có thể dùng JNI library chỉ build cho Linux x86_64 hoặc API native không còn tương thích. Khi migration JDK và OS cùng lúc, native compatibility là một trục kiểm thử riêng.

### 20.7. Serialized dữ liệu và schema

Hai module có cùng bytecode target không bảo đảm tương thích Java Object Serialization, JSON, Avro hoặc Protocol Buffers. Nếu record/enum/domain model thay đổi, consumer có thể không đọc được dữ liệu mới dù runtime đều là Java 17.

Cần phân biệt **bytecode compatibility** với **data protocol compatibility**.

## 21. “Cùng mức major” vẫn có thể không chạy cùng nhau

Ví dụ hai artifact đều major 61 nhưng một module đã đổi public API:

```text
library A v1:
  public int calculate(int value);

library A v2:
  public long calculate(long value);
```

Một consumer đã biên dịch với v1 có thể gặp `NoSuchMethodError` khi chạy với v2 nếu method signature bị thay và binary không được tương thích. Cả hai vẫn có thể dùng Java 17 bytecode.

Tương tự:

- `NoClassDefFoundError` khi runtime thiếu dependency.
- `IllegalAccessError` khi quyền truy cập thay đổi.
- `InaccessibleObjectException` khi reflective access bị JPMS chặn.
- `ServiceConfigurationError` khi SPI provider không hợp lệ.
- `ClassCastException` khi class identity khác loader.
- `UnsatisfiedLinkError` khi native library thiếu/sai.

Vì vậy, một pipeline tốt kiểm tra class major **và** thực thi integration tests trên dependency graph thực tế.

## 22. Tổ chức test matrix cho nhiều runtime

### 22.1. Mô hình phổ biến: base library Java 17, service Java 21

| Artifact | Compiler JDK | Target release | Test runtime |
|---|---:|---:|---|
| `common-model.jar` | 21 | 17 | Java 17 và 21 |
| `pricing-core.jar` | 21 | 17 | Java 17 và 21 |
| `payment-adapter.jar` | 21 | 21 | Java 21 |
| `order-service.jar` | 21 | 17 | Java 17 |
| `billing-worker.jar` | 21 | 21 | Java 21 |

Đây là ma trận minh họa. Nếu sản phẩm chạy Java 25, cần bổ sung test thích hợp với JDK 25 và kiểm tra dependency support.

### 22.2. Test runtime tối thiểu quan trọng nhất

Nếu thư viện công bố Java 17 làm minimum, chạy tests chỉ trên Java 21 không đủ. Java 21 hỗ trợ nhiều API/class versions hơn và có thể che lỗi.

Một job đáng có:

```text
Compile with JDK 21 + --release 17
          |
          v
Assemble JAR and dependencies
          |
          v
Run compatibility tests on JDK 17
          |
          v
Run regression tests on JDK 21
```

Nếu project cần chạy Java 17 nhưng test framework hiện tại chỉ hỗ trợ Java 21, nên cân nhắc một smoke/compatibility suite dùng test framework phù hợp Java 17 thay vì bỏ kiểm thử runtime tối thiểu.

### 22.3. Không nhất thiết build bằng mọi JDK

`--release` và toolchains giúp compiler mới tạo artifact target cũ. Tuy nhiên, chạy test trên runtime thật vẫn cần thiết. Có thể chọn chiến lược:

- Một compiler toolchain được pin để build.
- Nhiều runtime JDK để chạy test artifact.
- Một ma trận OS/architecture nếu có native dependencies.
- Một job kiểm tra artifact bytecode và publish metadata.

Tránh tăng số tổ hợp không cần thiết; dựa trên những phiên bản được sản phẩm cam kết hỗ trợ.

## 23. Migration từ Java 8/11/17 lên Java 21/25 trong multi-module build

### Giai đoạn 1: Kiểm kê module và consumers

Lập danh sách:

- Tên và loại từng Maven/Gradle module.
- Artifact được publish.
- Ứng dụng tiêu thụ từng artifact.
- JDK runtime tối thiểu của từng consumer.
- Build JDK, compiler plugin, Gradle/Maven version.
- Các dependencies bắc cầu và native artifacts.
- Các module có JPMS descriptor hoặc MR-JAR.
- Những plugin được tải động và test fixtures được publish.

Đừng bắt đầu bằng cách nâng mọi module lên cùng một `release` cao nhất chỉ vì JDK CI đã được nâng.

### Giai đoạn 2: Đặt chính sách target

Xác định:

```text
Shared libraries for old consumers -> Java 17
New service-only implementation    -> Java 21
Application running on Java 17     -> Java 17 closure
Application running on Java 21     -> Java 21 closure
```

Nếu cùng một library cần API Java 21 nhưng vẫn có consumer Java 17, hãy cân nhắc:

- Tách API nền tảng Java 17 và implementation Java 21.
- Tạo artifact riêng.
- Sử dụng MR-JAR nếu thực sự phù hợp và có test.
- Nâng yêu cầu runtime của consumer theo kế hoạch phát hành.

Không giả định compiler có thể “dịch ngược” Java 21 API xuống Java 17 mà không có thay đổi thiết kế.

### Giai đoạn 3: Chuẩn hóa build configuration

Với Maven:

- Dùng parent thật sự được các child kế thừa.
- Pin maven-compiler-plugin.
- Tập trung `release` qua property/convention.
- Chỉ cho phép override có ghi nhận.
- Quản lý toolchains và profiles.

Với Gradle:

- Pin Gradle Wrapper.
- Dùng toolchains.
- Dùng `options.release` cho Java compilation.
- Áp dụng convention plugin hoặc cấu hình chung có kiểm soát.
- Đồng bộ Kotlin/Groovy/Scala compiler targets.
- Quản lý variants và dependency lock.

### Giai đoạn 4: Nâng dependencies có chủ đích

Đặc biệt quan tâm framework, bytecode libraries, JNI, annotation processors, test runner và Java agents.

Nếu một dependency mới yêu cầu Java 21 mà shared library phải hỗ trợ Java 17, cần chọn version khác hoặc tách dependency/module. Không được giải quyết bằng cách tiếp tục ghi `--release 17` trong module chính và bỏ qua major 65 của dependency.

### Giai đoạn 5: Build và kiểm tra artifact

Đối với mỗi module được publish:

1. Build với toolchain được pin.
2. Kiểm tra class major của artifact gốc.
3. Xem metadata JPMS/MR-JAR nếu có.
4. Kiểm tra transitive dependencies.
5. Kiểm tra fat/nested/shaded artifact nếu là output thực tế.
6. Xác nhận module/variant metadata công bố minimum JVM phù hợp.
7. Lưu checksum và version của artifact đã kiểm tra.

### Giai đoạn 6: Test trên runtime mục tiêu

Chạy:

- Unit tests của module.
- Integration tests giữa modules.
- Service startup smoke tests.
- Runtime tests trên JDK thấp nhất.
- Test dynamic plugins/SPI.
- Test serialization, reflection và native integration khi áp dụng.
- Test trong container hoặc OS triển khai thực tế.

### Giai đoạn 7: Phát hành, canary và rollback

Đảm bảo version của các module được publish rõ ràng, dependency graph được kiểm soát và artifact không bị ghi đè. Khi rollback, phải chọn lại đúng tập artifact đã được kiểm thử, không chỉ rollback main application JAR.

Nếu bản mới thay data schema hoặc protocol, rollback bytecode không đủ; cần có kế hoạch tương thích dữ liệu riêng.

## 24. Các lỗi thường gặp và hướng xử lý

### 24.1. `UnsupportedClassVersionError` chỉ xảy ra ở production

**Dấu hiệu:** CI dùng Java 21 chạy ổn, production Java 17 báo class-file major 65.

**Nguyên nhân khả dĩ:** module hoặc dependency được biên dịch target 21; CI không chạy trên runtime tối thiểu.

**Xử lý:** xác định JAR chứa class, xem major version và resolved dependency graph, giảm target khi hợp lệ hoặc nâng runtime/đổi dependency theo chính sách, bổ sung test trên Java 17.

### 24.2. Parent POM đặt release 17 nhưng một child ra major 65

**Nguyên nhân:** child không kế thừa parent, override plugin configuration, profile khác hoặc plugin/custom compiler không dùng cấu hình chung.

**Xử lý:** xem effective POM, xác nhận toolchain và actual compiler command, cập nhật source of truth, quét JAR output.

### 24.3. Gradle toolchain 21 tạo JAR không hỗ trợ Java 17

**Nguyên nhân:** `java.toolchain` chỉ định compiler, nhưng `JavaCompile.options.release` không được đặt hoặc bị override.

**Xử lý:** đặt `options.release = 17` ở convention phù hợp, kiểm tra bytecode output và test trên Java 17.

### 24.4. Gradle build báo không chọn được dependency variant

**Dấu hiệu:** dependency resolution nói rằng artifact yêu cầu JVM cao hơn target của consumer.

**Nguyên nhân:** Gradle Module Metadata công bố target JVM không tương thích hoặc variant attributes khác không khớp.

**Xử lý:** đọc thông tin variant và minimum Java của thư viện, chọn version/artifact phù hợp, không tắt compatibility checks để “build xanh” khi production thực sự chạy JDK cũ.

### 24.5. Maven build thành công nhưng runtime thiếu method

**Nguyên nhân:** dù cùng major, compile/runtime chọn API version khác hoặc một dependency đã thay đổi ABI.

**Xử lý:** đối chiếu dependency tree, binary compatibility và runtime graph. Không chỉ dựa vào class major.

### 24.6. MR-JAR bị báo chứa class major quá mới

**Nguyên nhân:** scanner chưa hiểu versioned entries hoặc JAR đóng gói sai.

**Xử lý:** kiểm tra manifest `Multi-Release: true`, base entries, `META-INF/versions/N` và quy tắc target theo N. Chạy thử trên những JDK mà artifact hỗ trợ.

### 24.7. Fat JAR có bytecode mới dù module chính target cũ

**Nguyên nhân:** shading/nested dependency chứa classes major cao hơn.

**Xử lý:** quét artifact cuối và mọi nested JAR, thay dependency hoặc nâng runtime. Không chỉ kiểm tra `build/classes/java/main`.

### 24.8. Test thất bại trên JDK 17 nhưng thư viện runtime vẫn tương thích

**Nguyên nhân khả dĩ:** test runner, mocking/coverage agent hoặc test-only dependency yêu cầu Java 21.

**Xử lý:** tách test tool compatibility khỏi main artifact compatibility, dùng bộ test phù hợp JDK 17 để xác minh hợp đồng thư viện.

### 24.9. Module-info.class gây lỗi khi chạy Java cũ

**Nguyên nhân:** JPMS descriptor hoặc classes được đóng gói không đúng cho baseline JDK.

**Xử lý:** xác định ứng dụng chạy classpath/module path, nếu cần hỗ trợ Java 8 thì xem xét MR-JAR đúng chuẩn hoặc artifact riêng, kiểm tra layout với JDK thấp nhất.

### 24.10. Dependency lock giữ một bản không còn hỗ trợ JDK đích

**Nguyên nhân:** lockfile chỉ giữ phiên bản; nó không biến artifact thành tương thích.

**Xử lý:** chọn và thử phiên bản dependency được hỗ trợ, cập nhật lock có kiểm soát, lưu diff và kết quả compatibility test.

## 25. CI gates đề xuất cho repository nhiều module

Một pipeline có thể được hình dung như sau:

```text
Checkout immutable commit
       |
       v
Pin Maven/Gradle + compiler JDK
       |
       v
Resolve/verify dependencies
       |
       v
Compile every module with declared target
       |
       v
Package normal/shaded/nested artifacts
       |
       v
Inspect class-file major + MR-JAR rules
       |
       v
Check dependency closure of each deployable
       |
       v
Test on minimum supported JDK
       |
       v
Integration test on target JDK/OS
       |
       v
Publish immutable artifacts with metadata
       |
       v
Canary + monitoring + rollback readiness
```

### 25.1. Gate theo từng module

Một bảng machine-readable hoặc report trong CI có thể ghi:

| Module | Target chính sách | Major quan sát được | Dependency vượt ngưỡng? | Kết quả |
|---|---:|---:|---|---|
| `common-model` | 17 | 61 | Không | Pass |
| `pricing-core` | 17 | 61 | Không | Pass |
| `nextgen-payment` | 21 | 65 | Không | Pass |
| `order-service` | 17 | 61 | Có (phụ thuộc major 65) | Fail |

Bảng chỉ minh họa kết quả kiểm tra. Với MR-JAR, report cần phân biệt base và versioned classes thay vì chỉ giữ một maximum major cho toàn archive.

### 25.2. Gate trên artifact được deploy

Nếu sản phẩm publish container image, cần kiểm tra nội dung image hoặc ít nhất tập JAR/entrypoint đã được đóng gói vào image, không chỉ JAR ở thư mục `build/libs` trước khi packaging.

Nếu dùng application distribution, kiểm tra mọi JAR trong `lib` và executable startup script trỏ tới JDK phù hợp. Nếu dùng dynamic plugin, bổ sung plugin compatibility gate.

### 25.3. Giữ report để truy vết

Lưu với release:

- JDK compiler vendor/version.
- Gradle/Maven version.
- Target release từng module.
- Dependency graph/lock state.
- Artifact checksums.
- Class-file major reports.
- Test matrix và runtime versions.
- Source revision và provenance.

Thông tin này giúp xác định một lỗi trong production đến từ bytecode không tương thích hay từ một thay đổi API/dependency khác.

## 26. Bài tập thực hành

### Bài tập 1: Phân tích ma trận bytecode

Cho cấu trúc:

```text
shared-api        major 61
reporting-core    major 65
order-service     major 61
billing-worker    major 65

order-service -> shared-api -> reporting-core
billing-worker -> shared-api
```

Service đầu chạy Java 17, service sau chạy Java 21.

Hãy xác định module nào có thể gây `UnsupportedClassVersionError` trong `order-service`, và tại sao `order-service` major 61 chưa đủ chứng minh tương thích.

### Bài tập 2: Sửa cấu hình Maven

Parent POM đặt `maven.compiler.release=17`, nhưng `payment-adapter` cần Java 21. Hãy thiết kế một property `java.release` được compiler plugin tham chiếu, cho phép child override 21 mà các child khác vẫn giữ 17. Sau đó mô tả cách dùng effective POM và `javap -verbose` để kiểm tra kết quả.

### Bài tập 3: Sửa cấu hình Gradle

Một multi-project Gradle build dùng `java.toolchain = 21` ở root. Tất cả modules được kỳ vọng hỗ trợ Java 17, trừ `billing-worker`. Hãy thêm cấu hình `JavaCompile.options.release` chung và cơ chế override có kiểm soát, rồi đề xuất cách kiểm tra artifacts.

### Bài tập 4: Kiểm tra shaded JAR

Module `order-service` biên dịch major 61, nhưng fat JAR gói thêm một transitive dependency major 65. Hãy mô tả cách:

1. Xác định dependency đưa thư viện đó vào.
2. Xác định dependency có thực sự cần ở runtime không.
3. Thử phiên bản phù hợp Java 17 hoặc tách module.
4. Quét shaded/nested artifact sau build.
5. Chạy service trên Java 17 trong CI.

### Bài tập 5: Multi-release JAR

Một library hỗ trợ Java 8, 17 và 21 muốn tối ưu implementation ở runtime mới.

Hãy phác thảo base entries, `META-INF/versions/17` và `META-INF/versions/21`, cùng những quy tắc build/test phải có để Java 8 vẫn dùng được base classes.

## 27. Checklist trước khi hoàn tất migration

### Chính sách kiến trúc

- [ ] Mọi module đều có owner và target Java được công bố.
- [ ] Đã xác định runtime tối thiểu của mỗi deployable artifact.
- [ ] Shared libraries không nâng target vượt nhu cầu của consumers cũ.
- [ ] Dependency graph không đưa artifact major quá mới vào runtime thấp hơn.
- [ ] Có quyết định rõ khi cần module Java 17 và Java 21 cùng tồn tại.

### Maven

- [ ] Child modules kế thừa đúng parent POM.
- [ ] `maven-compiler-plugin` có version và release rõ.
- [ ] Property override không bị hard-code plugin config ghi đè.
- [ ] Toolchain/JDK và Maven profiles được kiểm soát.
- [ ] Effective POM từng module quan trọng đã được xác nhận.
- [ ] BOM/dependencyManagement không đưa vào thư viện vượt runtime floor.

### Gradle

- [ ] Wrapper và JDK toolchain được pin.
- [ ] `JavaCompile.options.release` được cấu hình theo policy.
- [ ] Modules có target đặc biệt được khai báo có chủ đích.
- [ ] Java, Kotlin, Groovy, Scala và generated bytecode được kiểm tra riêng.
- [ ] Gradle variants/dependency metadata phù hợp minimum JVM.
- [ ] Lockfile, transitive graph và runtime configurations được review.

### Artifact và runtime

- [ ] Đã kiểm tra major version trong JAR đã phát hành.
- [ ] Đã quét shaded/nested archives và runtime `lib/*.jar`.
- [ ] `module-info.class` và MR-JAR được xử lý đúng ngữ cảnh.
- [ ] Java agents, plugins và native dependencies được tính vào deployment.
- [ ] Artifact đã được thử trên JVM thấp nhất được cam kết.
- [ ] Integration tests xác nhận API/binary/behavior compatibility, không chỉ class major.
- [ ] Có report và checksum artifact kèm build metadata.
- [ ] Có rollout/rollback plan phù hợp với runtime và dependency versions.

## Kết luận

Trong dự án Maven hoặc Gradle nhiều module, **đồng bộ mức bytecode** không có nghĩa bắt buộc mọi module phải dùng cùng một JDK hay cùng class-file major. Điều cốt lõi là mỗi artifact công bố runtime tối thiểu rõ ràng, và toàn bộ dependency closure của ứng dụng phải tương thích với runtime đó. Một library được build bằng JDK 21 vẫn có thể phát hành bytecode Java 17 bằng `--release 17`; ngược lại, một main module major 61 vẫn có thể thất bại trên Java 17 nếu fat JAR hoặc dependency bắc cầu chứa major 65.

Để migration an toàn, hãy quản lý release target tập trung trong Maven parent POM hoặc Gradle convention plugin, phân biệt toolchain với target bytecode, kiểm tra output thực tế và dependencies, xử lý riêng JPMS/multi-release JAR, đồng thời chạy test trên JDK thấp nhất được hỗ trợ. Kết hợp bytecode inspection, dependency management và runtime integration tests giúp phát hiện lỗi trước khi triển khai, giữ cho các module cũ và mới có thể tiến hóa theo lộ trình mà không phá vỡ consumers.

