# Đồng bộ phiên bản giữa các mô-đun mà không phá hợp đồng phụ thuộc trong Maven

## 1. Bài toán và mục tiêu

Trong một Maven Reactor có nhiều mô-đun, việc đổi version không chỉ là thay một chuỗi trong `pom.xml`. Một lần nâng phiên bản cần giữ đúng **tọa độ artifact**, **quan hệ parent–child**, **inter-module dependencies**, **dependencyManagement**, **POM được install/deploy** và **khả năng tương thích API của các consumer**.

Giả sử một repository có:

```text
version-contract-lab/
├── pom.xml               (parent + aggregator)
├── contract-api/          (định nghĩa public API)
├── pricing-core/          (dùng contract-api)
├── invoice-cli/           (dùng pricing-core)
└── standalone-tool/       (độc lập)
```

Ban đầu các module thuộc một release train `1.2.0-SNAPSHOT`. Nhóm muốn đồng bộ toàn bộ sang `1.3.0-SNAPSHOT` mà không làm đứt đường phụ thuộc giữa các module. Nếu chỉ đổi version của parent POM nhưng quên `<parent><version>` trong child hoặc dependency vào sibling, Maven có thể tìm artifact phiên bản cũ, dùng POM không khớp, hoặc fail khi resolve.

Tuy nhiên, **đổi đồng loạt số phiên bản không có nghĩa API vẫn tương thích**. Chẳng hạn xóa method public `PriceQuote.label()` có thể khiến mã consumer fail compile hoặc phát sinh `NoSuchMethodError` khi bytecode cũ chạy với API mới. Vì vậy đồng bộ version có hai lớp:

1. **Tính nhất quán của metadata Maven:** Maven biết đúng artifact nào cần build, resolve, install và deploy.
2. **Hợp đồng tương thích:** các consumers tiếp tục biên dịch, chạy và nhận hành vi dữ liệu được kỳ vọng, hoặc có một kế hoạch migration/breaking release rõ ràng.

Bài học trình bày các chiến lược lockstep và independent versioning; sử dụng parent POM, `dependencyManagement`, BOM, Versions Maven Plugin và CI-friendly versions; đồng thời cung cấp dự án Java 17 + JUnit 5 có thể thực hành.

## 2. Phân biệt ba loại “phiên bản”

| Loại | Ví dụ | Vai trò |
| --- | --- | --- |
| **Project/artifact version** | `demo.contract:contract-api:1.2.0-SNAPSHOT` | Định danh artifact được resolve trong Maven repository |
| **Parent POM version** | `<parent><version>1.2.0-SNAPSHOT</version>` | Phiên bản POM cha mà child dùng để kế thừa cấu hình |
| **Dependency version** | `contract-api:1.2.0-SNAPSHOT` trong dependency của pricing-core | Phiên bản của thư viện mà consumer yêu cầu |
| Dependency/plugin management | `dependencyManagement`, `pluginManagement` | Quản lý phiên bản và cấu hình, không tự thêm dependency/goal tùy ý |
| Runtime/contract version | Public API, event schema, HTTP API version | Quy tắc tương thích mà build version **không tự thực thi** |
| Build/plugin version | Compiler Plugin 3.13.0, Surefire 3.2.5 | Công cụ build, không đồng nghĩa project artifact version |

Trong ví dụ, root POM là `demo.contract:version-contract-lab:pom:1.2.0-SNAPSHOT`; module contract-api là `demo.contract:contract-api:jar:1.2.0-SNAPSHOT`. Chúng cùng số phiên bản nhưng **khác artifactId/packaging**, không phải một artifact.

Khi root đổi sang `1.3.0-SNAPSHOT` theo chiến lược lockstep, các child phải resolve đúng parent version, và inter-module dependencies cần nhắm artifact cùng thế hệ. Nếu một module triển khai riêng có version độc lập, **không** cưỡng ép nó đổi theo nếu đó không phải chính sách release của project.

### 2.1. Maven không tự xác nhận SemVer

Một số nhóm dùng Semantic Versioning như `MAJOR.MINOR.PATCH` để truyền đạt thay đổi breaking/feature/fix. Maven **không phân tích public API** rồi bảo đảm `1.3.0` tương thích với `1.2.0` chỉ dựa vào cách đánh số.

- Thay chữ ký, xóa method/constructor hoặc đổi visibility có thể phá **source/binary compatibility**.
- Đổi ý nghĩa dữ liệu, exception, rounding hoặc serialization có thể phá **behavioral compatibility** dù Java vẫn compile.
- Đổi JSON/XML/SQL/HTTP schemas có thể phá contract của consumer nằm **ngoài Maven Reactor**.
- Bump version đồng bộ thành công không thay thế kiểm thử consumer, API diff và release review.

Quy tắc cần học: **metadata đúng là điều kiện cần, không phải điều kiện đủ để bảo vệ hợp đồng phụ thuộc**.

## 3. Hai chiến lược phát hành: lockstep và phiên bản độc lập

### 3.1. Lockstep versions: tất cả module chung một release train

Mô hình:

```text
contract-api        1.2.0-SNAPSHOT
pricing-core        1.2.0-SNAPSHOT
invoice-cli         1.2.0-SNAPSHOT
standalone-tool     1.2.0-SNAPSHOT
parent              1.2.0-SNAPSHOT
```

Sau một lần thay đổi nhất quán:

```text
contract-api        1.3.0-SNAPSHOT
pricing-core        1.3.0-SNAPSHOT
invoice-cli         1.3.0-SNAPSHOT
standalone-tool     1.3.0-SNAPSHOT
parent              1.3.0-SNAPSHOT
```

Ưu điểm: đơn giản khi tất cả module thuộc một release train, dễ đọc artifacts cùng build và đồng bộ parent POM. Nhược điểm: module độc lập cũng nhận version mới dù code không đổi; mọi consumer cần biết policy nâng cấp.

Thích hợp với repository có một pipeline phát hành đồng bộ, module cùng nhịp, tests và integration environment chung.

### 3.2. Independent versions: mỗi thư viện có vòng đời riêng

Ví dụ minh họa:

```text
contract-api        2.3.1
pricing-core        4.1.0
invoice-cli         7.0.2
standalone-tool     1.5.0
```

Pricing-core có thể yêu cầu contract-api phiên bản đã phát hành `2.3.1`, còn invoice-cli yêu cầu pricing-core `4.1.0`. Không nên đổi tất cả sang `7.0.2` chỉ để “đồng bộ”; những tọa độ đó phản ánh các release contracts khác nhau.

Ưu điểm: mỗi module phát hành theo thay đổi và consumer compatibility riêng. Nhược điểm: quản lý ma trận compatibility, transitive dependencies và BOM phức tạp hơn.

Thích hợp với thư viện được phát hành độc lập, nhiều consumer ngoài repository, hoặc các nhóm có vòng đời release khác nhau.

### 3.3. Câu hỏi trước khi chọn chiến lược

1. Mọi module được build/deploy từ một commit và cùng release train không?
2. Có consumer bên ngoài Reactor hay không?
3. Các module có cùng public compatibility policy không?
4. Có một version cho tất cả artifacts là yêu cầu kinh doanh hay chỉ là thói quen?
5. Khi chỉ một thư viện thay đổi breaking, các ứng dụng khác có cần nhận cùng major version không?
6. CI có đủ contract tests và binary-compatibility checks không?

Trong phần thực hành, **chúng ta chủ đích chọn lockstep**. Các đoạn minh họa phiên bản độc lập ở phần sau **không được trộn** vào POM runnable lockstep mà không điều chỉnh mọi dependency metadata.

## 4. Mối liên hệ giữa parent, aggregator và dependency

Trong root:

```xml
<packaging>pom</packaging>
<modules>
    <module>contract-api</module>
    <module>pricing-core</module>
    <module>invoice-cli</module>
    <module>standalone-tool</module>
</modules>
```

`<modules>` cho phép Reactor thu thập bốn module. Nó **không làm module pricing-core tự nhìn thấy Java classes của contract-api**. Muốn import class, pricing-core phải có dependency thật trong `<dependencies>`.

Trong child:

```xml
<parent>
    <groupId>demo.contract</groupId>
    <artifactId>version-contract-lab</artifactId>
    <version>1.2.0-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

`<parent>` tạo quan hệ kế thừa. Nếu child không khai báo `<version>` riêng, project version được kế thừa từ parent. Đổi version parent mà bỏ sót `<parent><version>` trong child khiến Maven có thể tìm parent phiên bản cũ từ repository hoặc báo `Non-resolvable parent POM`.

**Aggregation và inheritance có thể cùng một root nhưng là hai cơ chế khác nhau.** Một module nằm trong `<modules>` chưa chắc kế thừa root; cần `<parent>` đúng.

### 4.1. Tính nhất quán cần có

| Vị trí | Lockstep trước | Lockstep sau |
| --- | --- | --- |
| Root `<project><version>` | `1.2.0-SNAPSHOT` | `1.3.0-SNAPSHOT` |
| Child `<parent><version>` | `1.2.0-SNAPSHOT` | `1.3.0-SNAPSHOT` |
| Child `<project><version>` nếu khai báo riêng | Nên tránh nếu chỉ kế thừa | Nên tránh nếu chỉ kế thừa |
| Internal dependency trong `dependencyManagement` | Nhắm version root hiện tại | Nhắm root version mới |
| Plugin versions | Được pin độc lập | Không nhất thiết đổi cùng project |
| External dependency versions | Theo compatibility policy | Không tự nâng chỉ vì project version đổi |

**Tránh sửa plugin/library versions hàng loạt cùng lúc** với việc đồng bộ project version nếu mục đích thay đổi chỉ là release identity. Gộp nhiều biến thay đổi làm khó chẩn đoán regression.

## 5. dependencyManagement: quản lý version nhưng không tự tạo dependency

Root POM có thể quản lý internal modules:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>demo.contract</groupId>
            <artifactId>contract-api</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>demo.contract</groupId>
            <artifactId>pricing-core</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Ở chiến lược lockstep, `${project.version}` được resolve theo Maven model đang được build, giúp hai dependency này có cùng project version hiệu lực trong hệ thống ví dụ.

Child pricing-core dùng:

```xml
<dependencies>
    <dependency>
        <groupId>demo.contract</groupId>
        <artifactId>contract-api</artifactId>
    </dependency>
</dependencies>
```

Do dependency được quản lý trong parent, không cần lặp `<version>` ở child. Nếu module không khai báo dependency vào contract-api, **nó không trở thành consumer chỉ vì parent quản lý version này**.

### 5.1. Khi nào không nên dùng project.version?

Trong mô hình **independent versioning**, pricing-core có thể là `4.1.0` nhưng cần contract-api `2.3.1`. Khi đó `${project.version}` sẽ là **sai contract** nếu dùng cho internal dependency.

Mẫu quản lý độc lập:

```xml
<properties>
    <contract-api.version>2.3.1</contract-api.version>
</properties>
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>demo.contract</groupId>
            <artifactId>contract-api</artifactId>
            <version>${contract-api.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn POM độc lập để minh họa**, không gắn trực tiếp vào root POM lockstep ở phần thực hành. Nó có thể bị thay đổi theo quy trình compatibility review và consumer test; không đơn giản tìm “phiên bản mới nhất” rồi thay tự động.

### 5.2. dependencyManagement không bằng dependency mediation

Nếu hai thư viện transitively yêu cầu các version khác nhau của cùng một artifact, Maven có quy tắc **nearest definition** để chọn version khi không có một declaration/management phù hợp. Khi cùng độ sâu, thứ tự khai báo có thể ảnh hưởng lựa chọn.

`dependencyManagement` có thể kiểm soát version được resolve trong phạm vi phù hợp, nhưng **không biến hai version bytecode khác nhau thành một API tương thích**. Phải chạy test, xem dependency tree, hiểu có class/method nào bị đổi, và dùng Enforcer khi cần ngăn xung đột.

## 6. Vì sao đồng bộ số version có thể phá hợp đồng phụ thuộc?

Có ít nhất năm nhóm lỗi độc lập:

1. **Parent mismatch:** Child POM trỏ tới parent version cũ trong khi root đã đổi.
2. **Internal dependency mismatch:** pricing-core mới vẫn kéo contract-api cũ vì version hardcode hoặc dependencyManagement sai.
3. **Binary/source API break:** method bị xóa/đổi chữ ký hoặc package, consumer cũ không dùng được.
4. **Behavior/serialization break:** signature vẫn giống nhưng đầu ra, exceptions, JSON field hay business rule đã thay.
5. **Artifact publication mismatch:** JAR mới đi kèm POM được publish có tọa độ/dependency không resolve được, đặc biệt khi dùng CI-friendly placeholders thiếu flatten trên Maven 3.

Một thay đổi version tốt cần bao phủ cả **cấu trúc build** lẫn **hợp đồng runtime**. Chỉ tìm và thay mọi chuỗi `1.2.0-SNAPSHOT` bằng `1.3.0-SNAPSHOT` không đảm bảo Maven project graph hợp lệ.

## 7. Dự án mẫu: Java 17 + Maven Reactor + JUnit Jupiter 5

Dự án chạy được minh họa:

```text
version-contract-lab/
├── pom.xml
├── contract-api/
│   ├── pom.xml
│   ├── src/main/java/demo/contract/api/PriceQuote.java
│   └── src/test/java/demo/contract/api/PriceQuoteTest.java
├── pricing-core/
│   ├── pom.xml
│   ├── src/main/java/demo/contract/pricing/QuoteFactory.java
│   └── src/test/java/demo/contract/pricing/QuoteFactoryTest.java
├── invoice-cli/
│   ├── pom.xml
│   ├── src/main/java/demo/contract/invoice/InvoiceCli.java
│   └── src/test/java/demo/contract/invoice/InvoiceCliTest.java
└── standalone-tool/
    ├── pom.xml
    ├── src/main/java/demo/contract/standalone/StandaloneTool.java
    └── src/test/java/demo/contract/standalone/StandaloneToolTest.java
```

Dependency graph:

```text
contract-api
    │
    ▼
pricing-core
    │
    ▼
invoice-cli

standalone-tool    (không phụ thuộc ba module còn lại)
```

Tất cả modules dùng **version `1.2.0-SNAPSHOT` qua parent**. JUnit Jupiter được quản lý một lần. Việc nâng parent và child references đồng bộ sẽ không thay public method signatures trong code của ví dụ.

Điều kiện: JDK 17+, Maven 3.9.x hoặc Maven 3 phù hợp với các plugin được chọn, repository cho phép tải JUnit/plugins; không cần database, HTTP server hay service bên ngoài. Versions/plugin artifacts được pin cho khả năng tái hiện bài thực hành, không khẳng định chúng là bản mới nhất.

## 8. POM gốc: một nguồn version, một nơi quản lý dependency

Tệp `version-contract-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.contract</groupId>
    <artifactId>version-contract-lab</artifactId>
    <version>1.2.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>contract-api</module>
        <module>pricing-core</module>
        <module>invoice-cli</module>
        <module>standalone-tool</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>demo.contract</groupId>
                <artifactId>contract-api</artifactId>
                <version>${project.version}</version>
            </dependency>
            <dependency>
                <groupId>demo.contract</groupId>
                <artifactId>pricing-core</artifactId>
                <version>${project.version}</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.10.2</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-clean-plugin</artifactId>
                    <version>3.3.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-resources-plugin</artifactId>
                    <version>3.3.1</version>
                </plugin>
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
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-install-plugin</artifactId>
                    <version>3.1.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Những điều phải nắm:

- `packaging=pom` để root vừa làm aggregator (`<modules>`), vừa làm parent cho bốn module.
- Child POM không khai báo `<version>` riêng, nên kế thừa version của parent.
- Parent `dependencyManagement` quản lý **đúng version nội bộ** bằng `${project.version}` cho release train này.
- Các child chỉ khai báo actual `<dependency>` khi thật sự dùng module khác.
- JUnit version được quản lý nhưng không tự đưa JUnit vào test classpath nếu child không khai báo dependency.
- `pluginManagement` pin plugin versions; khác với việc khai báo một execution goal tùy ý.
- Version Maven project `1.2.0-SNAPSHOT` **không gắn với** plugin version như Compiler 3.13.0 hoặc Surefire 3.2.5.

**Chú ý:** quy tắc quản lý inter-module version bằng project.version hợp với **lockstep release train**. Nếu module có independent version, cần một property/BOM riêng và compatibility policy khác.

## 9. Module contract-api: định nghĩa public API

### 9.1. contract-api/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.contract</groupId>
        <artifactId>version-contract-lab</artifactId>
        <version>1.2.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>contract-api</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Không cần `<version>` ở cấp child project; child kế thừa version từ parent. JUnit dùng trong test scope.

### 9.2. PriceQuote.java

Tệp `contract-api/src/main/java/demo/contract/api/PriceQuote.java`:

```java
package demo.contract.api;

public record PriceQuote(String sku, long totalCents) {

    public PriceQuote {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku required");
        }
        if (totalCents < 0) {
            throw new IllegalArgumentException("negative total");
        }
    }

    public String label() {
        return sku + ": " + totalCents + " cents";
    }
}
```

`record` là tính năng Java 17 hợp lệ. Public contract quan trọng của module này gồm:

- Constructor `PriceQuote(String sku, long totalCents)`.
- Accessors `sku()` và `totalCents()` của record.
- Public method `label()` trả `String`.
- Hành vi validate `sku` và `totalCents`.

Đổi version Maven mà vẫn giữ những chữ ký/hành vi này giúp consumers dễ tiếp tục tương thích. Nhưng nếu muốn bảo đảm binary/source compatibility với một bản đã phát hành, phải kiểm tra ABI và test bằng artifacts đã publish, không chỉ xem source code mới.

### 9.3. PriceQuoteTest.java

Tệp `contract-api/src/test/java/demo/contract/api/PriceQuoteTest.java`:

```java
package demo.contract.api;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceQuoteTest {

    @Test
    void keepsFieldsAndLabel() {
        PriceQuote quote = new PriceQuote("BOOK", 2500);
        assertEquals("BOOK", quote.sku());
        assertEquals(2500, quote.totalCents());
        assertEquals("BOOK: 2500 cents", quote.label());
    }

    @Test
    void rejectsEmptySku() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> new PriceQuote(" ", 100));
        assertEquals("sku required", error.getMessage());
    }

    @Test
    void rejectsNegativeTotal() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> new PriceQuote("BOOK", -1));
        assertEquals("negative total", error.getMessage());
    }
}
```

Có **3 JUnit tests**. Chúng kiểm tra public API và behavior hiện tại, nhưng chưa đủ để xác nhận consumer cũ của phiên bản đã phát hành trước đó vẫn dùng được.

## 10. Module pricing-core: consumer trực tiếp của API

### 10.1. pricing-core/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.contract</groupId>
        <artifactId>version-contract-lab</artifactId>
        <version>1.2.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>pricing-core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>demo.contract</groupId>
            <artifactId>contract-api</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Version của `contract-api` được lấy từ root `dependencyManagement`. Nhờ vậy child không phải lặp `1.2.0-SNAPSHOT` thành một chuỗi dễ quên khi nâng release train. Nếu parent management bị sai, dependency này vẫn có thể resolve nhầm version; vậy phải xem effective POM và dependency tree sau thay đổi.

### 10.2. QuoteFactory.java

Tệp `pricing-core/src/main/java/demo/contract/pricing/QuoteFactory.java`:

```java
package demo.contract.pricing;

import demo.contract.api.PriceQuote;

public final class QuoteFactory {
    private QuoteFactory() {
    }

    public static PriceQuote quote(
            String sku, long unitCents, int quantity) {
        if (unitCents < 0) {
            throw new IllegalArgumentException("negative unit price");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        long total = Math.multiplyExact(unitCents, quantity);
        return new PriceQuote(sku, total);
    }

    public static String example() {
        return quote("BOOK", 2500, 2).label();
    }
}
```

Code dùng public contract `new PriceQuote(...)` và `label()`. `Math.multiplyExact` phát hiện overflow của phép nhân long thay vì đưa ra tổng sai.

### 10.3. QuoteFactoryTest.java

Tệp `pricing-core/src/test/java/demo/contract/pricing/QuoteFactoryTest.java`:

```java
package demo.contract.pricing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class QuoteFactoryTest {

    @Test
    void quotesTwoItems() {
        assertEquals("BOOK: 5000 cents",
                QuoteFactory.quote("BOOK", 2500, 2).label());
    }

    @Test
    void rejectsNonPositiveQuantity() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> QuoteFactory.quote("BOOK", 2500, 0));
        assertEquals("quantity must be positive", error.getMessage());
    }
}
```

Module này có **2 tests**. Việc thay đổi contract-api cần chạy chúng để phát hiện các trường hợp source/binary/hành vi không còn phù hợp.

## 11. Module invoice-cli: consumer gián tiếp của API

### 11.1. invoice-cli/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.contract</groupId>
        <artifactId>version-contract-lab</artifactId>
        <version>1.2.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>invoice-cli</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>demo.contract</groupId>
            <artifactId>pricing-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Invoice-cli khai báo dependency trực tiếp vào pricing-core. Nó **không trực tiếp dùng class PriceQuote trong source code**, nên không cần thêm một dependency direct vào contract-api chỉ để minh họa graph. Pricing-core cần contract-api; Maven Resolver có thể đưa contract-api theo transitive dependency ở các scope phù hợp.

### 11.2. InvoiceCli.java

Tệp `invoice-cli/src/main/java/demo/contract/invoice/InvoiceCli.java`:

```java
package demo.contract.invoice;

import demo.contract.pricing.QuoteFactory;

public final class InvoiceCli {
    private InvoiceCli() {
    }

    public static String summary() {
        return "Invoice => " + QuoteFactory.example();
    }

    public static void main(String[] args) {
        System.out.println(summary());
    }
}
```

### 11.3. InvoiceCliTest.java

Tệp `invoice-cli/src/test/java/demo/contract/invoice/InvoiceCliTest.java`:

```java
package demo.contract.invoice;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class InvoiceCliTest {

    @Test
    void rendersQuoteFromDependencyChain() {
        assertEquals("Invoice => BOOK: 5000 cents",
                InvoiceCli.summary());
    }
}
```

Module có **1 test**, thể hiện hợp đồng end-to-end qua pricing-core và contract-api trong phạm vi Java Reactor.

## 12. Module độc lập để so sánh chiến lược lựa chọn test

### 12.1. standalone-tool/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.contract</groupId>
        <artifactId>version-contract-lab</artifactId>
        <version>1.2.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>standalone-tool</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Module này vẫn nhận parent version theo **lockstep policy** dù không phụ thuộc contract-api. Nó minh họa rằng **đồng bộ release version** không đồng nghĩa module có **dependency graph edge** tới các sibling.

### 12.2. StandaloneTool.java

Tệp `standalone-tool/src/main/java/demo/contract/standalone/StandaloneTool.java`:

```java
package demo.contract.standalone;

public final class StandaloneTool {
    private StandaloneTool() {
    }

    public static String message() {
        return "Standalone OK";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

### 12.3. StandaloneToolTest.java

Tệp `standalone-tool/src/test/java/demo/contract/standalone/StandaloneToolTest.java`:

```java
package demo.contract.standalone;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StandaloneToolTest {

    @Test
    void reportsStableMessage() {
        assertEquals("Standalone OK", StandaloneTool.message());
    }
}
```

Module có **1 test**. Tổng toàn Reactor là **3 + 2 + 1 + 1 = 7 tests**. Khi chỉ kiểm tra các dependent của contract-api, tập module nghiệp vụ thường là contract-api, pricing-core và invoice-cli, tổng **6 tests**; standalone-tool không thuộc downstream nhánh đó.

## 13. Chạy bản ban đầu để lấy baseline

Tại thư mục `version-contract-lab/`:

```bash
mvn -version
mvn -B clean verify
```

Trong môi trường JDK 17/Maven 3 phù hợp, kết quả kỳ vọng:

| Module | Version trước nâng | Tests |
| --- | --- | ---: |
| contract-api | `1.2.0-SNAPSHOT` | 3 |
| pricing-core | `1.2.0-SNAPSHOT` | 2 |
| invoice-cli | `1.2.0-SNAPSHOT` | 1 |
| standalone-tool | `1.2.0-SNAPSHOT` | 1 |
| Root POM | `1.2.0-SNAPSHOT` | Không có Java unit test |
| **Tổng** | | **7** |

Dữ liệu mong đợi: **7 tests run, 0 failures, 0 errors, 0 skipped**. Đọc `Reactor Summary` và báo cáo `target/surefire-reports/TEST-*.xml` theo từng module, không chỉ nhìn `BUILD SUCCESS`.

### 13.1. Chạy CLI để kiểm chứng consumer

Vì các JAR trong ví dụ **không** khai báo `Main-Class`/fat JAR, ta dùng `java -cp` trên các class đã compile. Trên Linux/macOS:

```bash
java -cp "invoice-cli/target/classes:pricing-core/target/classes:contract-api/target/classes" demo.contract.invoice.InvoiceCli
java -cp "standalone-tool/target/classes" demo.contract.standalone.StandaloneTool
```

**Stdout chính xác của riêng hai lệnh Java:**

```text
Invoice => BOOK: 5000 cents
Standalone OK
```

Trên Windows PowerShell, classpath separator là `;`:

```powershell
java -cp "invoice-cli\target\classes;pricing-core\target\classes;contract-api\target\classes" demo.contract.invoice.InvoiceCli
java -cp "standalone-tool\target\classes" demo.contract.standalone.StandaloneTool
```

Lệnh `java -cp` chỉ chạy class đã compile; nó **không thực thi Maven lifecycle** và không tự sinh Surefire reports. Nếu source chưa build, phải chạy `mvn clean verify` trước.

### 13.2. Xem chính xác version và dependency graph

Có thể dùng Maven Help Plugin và Dependency Plugin với version tường minh:

```bash
mvn -B -pl :pricing-core org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom -Doutput=target/effective-pricing-pom.xml
```

Tệp effective POM tại thư mục target của project được chọn (tùy goal/output path resolution) giúp đối chiếu parent version và `dependencyManagement` đã được áp dụng. Nếu cần đường dẫn tuyệt đối trong automation, hãy cấu hình `-Doutput` đầy đủ; không tự đoán tệp được ghi ở root hay module con khi chưa kiểm tra.

Sau khi **install** các module hoặc khi resolution trong Reactor có đủ artifacts, dùng:

```bash
mvn -B -pl :invoice-cli org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Kiểm tra nó resolve pricing-core và contract-api theo version mong đợi. `dependency:tree` đọc graph của một project, **không tự tạo các artifact còn thiếu**; với local repo sạch, có thể cần `mvn clean install` trước để câu lệnh goal riêng lẻ này resolve nội bộ được.

## 14. Đồng bộ version bằng Versions Maven Plugin

**Versions Maven Plugin** của MojoHaus có goal `versions:set` để đổi project version và cập nhật các child project references phù hợp, tránh sửa thủ công từng POM.

Trên một nhánh Git có thể review và từ root project:

```bash
mvn -B org.codehaus.mojo:versions-maven-plugin:2.22.0:set -DnewVersion=1.3.0-SNAPSHOT
```

Đây là **lệnh thực hành người đọc chạy trong repository mẫu**, không phải một thao tác được thực hiện sẵn trong bài. Goal `set` sửa POMs; nó **không** tự chạy compile/test và không tự bảo đảm binary compatibility.

Sau lệnh:

1. Root `<project><version>` dự kiến đổi sang `1.3.0-SNAPSHOT`.
2. Các `<parent><version>` trong child modules được plugin xử lý theo quan hệ parent trong phạm vi hỗ trợ.
3. Mỗi child kế thừa version mới vì không khai báo `<project><version>` riêng.
4. Các dependency nội bộ trong root `dependencyManagement` dùng `${project.version}`, vì thế resolve theo project version mới.
5. Third-party dependency như JUnit 5.10.2 **không cần** đổi chỉ vì release train đổi.

**Không khẳng định một plugin version/update goal tự xử lý mọi trường hợp đặc thù:** POM với module version độc lập, parent bên ngoài, property interpolation lạ hoặc version được hardcode nhiều vị trí cần kiểm tra `git diff` và effective POM.

### 14.1. Backup POMs và hoàn tác

`versions:set` mặc định có thể tạo các file `pom.xml.versionsBackup`; parameter `generateBackupPoms` cho phép thay đổi hành vi. Đọc chính xác docs goal phiên bản đã pin trước khi tự động hóa.

Ví dụ cho một repository đã được commit sạch trước thao tác:

```bash
mvn -B org.codehaus.mojo:versions-maven-plugin:2.22.0:set -DnewVersion=1.3.0-SNAPSHOT -DgenerateBackupPoms=false
```

Tùy chọn `-DgenerateBackupPoms=false` tránh tạo backup files. Chỉ phù hợp khi thay đổi được quản lý bằng Git hoặc có cách phục hồi an toàn; **không dùng nếu còn sửa đổi chưa commit mà chưa có backup**.

Khi backup đang tồn tại, plugin có `versions:revert` và `versions:commit` để hoàn tác/loại backups theo quy trình. **Không chạy revert bừa** trên repository chứa sửa đổi khác của đồng nghiệp, và đừng tự xóa hàng loạt `*.versionsBackup` trước khi review POMs. Với Git, hãy xem diff, commit có chủ đích hoặc revert commit theo quy trình dự án.

### 14.2. Xác minh POMs sau versions:set

Dùng một công cụ diff, ví dụ Git:

```bash
git diff -- pom.xml contract-api/pom.xml pricing-core/pom.xml invoice-cli/pom.xml standalone-tool/pom.xml
```

Trong bài mẫu, điều mong đợi là version root/child references đổi đồng bộ, **không** xóa dependencies hoặc plugin config. Đối chiếu:

- Version root: `1.3.0-SNAPSHOT`.
- `<parent><version>` của **mọi** child: `1.3.0-SNAPSHOT`.
- Child không khai báo version riêng ngoài ý muốn.
- Internal version managed bằng `${project.version}`.
- External dependency version vẫn như trước nếu không chủ động nâng.
- Không có POM trỏ tới parent version cũ hoặc module artifact cũ.

Sau đó chạy:

```bash
mvn -B clean verify
```

**Kỳ vọng:** Reactor xây các module version `1.3.0-SNAPSHOT` và 7 tests vẫn pass. Maven output thật phải được đọc để xác nhận; đây là expected result của ví dụ, không phải báo cáo một lượt build đã chạy ở đây.

### 14.3. versions:update-child-modules dùng trong trường hợp nào?

Nếu parent version đã bị đổi riêng, khiến các child vẫn trỏ parent version cũ và Maven không còn assemble được Reactor hoàn chỉnh, Versions Maven Plugin có goal `versions:update-child-modules` để sửa child parent references. Tài liệu MojoHaus chỉ dẫn dùng `-N` tại root trong tình huống này:

```bash
mvn -N org.codehaus.mojo:versions-maven-plugin:2.22.0:update-child-modules
```

Đây là **công cụ khôi phục khi module parent references đã lệch**, không phải bước bắt buộc sau một `versions:set` chạy đúng. Với project có nhiều tầng parent/aggregator, cần kiểm tra lại từ từng aggregator liên quan. Một goal sửa version không giải quyết mọi dependency compatibility problem.

### 14.4. versions:use-reactor không phải công cụ bảo đảm API tương thích

Versions Maven Plugin còn có `versions:use-reactor`, mục tiêu dùng các project versions tương ứng trong Reactor ở những dependency references phù hợp. Nó có thể hữu ích khi một POM còn trỏ tới artifact version cũ.

Nhưng tự đổi version tham chiếu thành version trong Reactor **không chứng minh** method, serialization hay behavior của module mới tương thích với consumer cũ. Sau mỗi lần rewrite dependency metadata phải chạy compile/test và contract/API review.

## 15. Bài thực hành sau nâng version: chứng minh consumer vẫn dùng được

Sau `versions:set`, từ root:

```bash
mvn -B clean verify
```

Điều cần đối chiếu:

| Hạng mục | Trước | Sau |
| --- | --- | --- |
| Root version | `1.2.0-SNAPSHOT` | `1.3.0-SNAPSHOT` |
| contract-api version | `1.2.0-SNAPSHOT` | `1.3.0-SNAPSHOT` |
| pricing-core version | `1.2.0-SNAPSHOT` | `1.3.0-SNAPSHOT` |
| invoice-cli version | `1.2.0-SNAPSHOT` | `1.3.0-SNAPSHOT` |
| standalone-tool version | `1.2.0-SNAPSHOT` | `1.3.0-SNAPSHOT` |
| Internal dependencies | Theo version cũ | Theo version mới |
| Tổng JUnit tests | 7 pass | 7 pass |
| CLI stdout | `Invoice => BOOK: 5000 cents` | Giữ nguyên |

Kiểm tra CLI sau build mới:

```bash
java -cp "invoice-cli/target/classes:pricing-core/target/classes:contract-api/target/classes" demo.contract.invoice.InvoiceCli
```

Stdout **chính xác của riêng lệnh Java** trên Linux/macOS:

```text
Invoice => BOOK: 5000 cents
```

Dòng output không có số phiên bản vì chương trình mẫu không in artifact metadata. Nếu muốn xác minh GAV, đọc POM/effective POM và artifact filenames hoặc repository metadata — đừng suy ra version từ một chuỗi Java không chứa version.

### 15.1. Test downstream bằng -amd

Nếu chỉ sửa contract-api, Maven Reactor có thể chọn consumers với:

```bash
mvn -B -pl :contract-api -amd clean test
```

Trong dependency graph demo, các module nghiệp vụ được chọn là `contract-api`, `pricing-core` và `invoice-cli`, tổng **3 + 2 + 1 = 6 tests**. `standalone-tool` không có dependency path tới contract-api nên không thuộc downstream selection.

Điều này giúp phát hiện compile/test regression khi module nền tảng đổi, nhưng **không thay full Reactor release verification**. Khi đồng bộ version của **toàn bộ release train**, `mvn -B clean verify` trên toàn Reactor vẫn cần để kiểm tra parent references và standalone-tool.

### 15.2. Vì sao -am khác -amd?

- `-am` (*also-make*) lấy những module **upstream mà seed cần**.
- `-amd` (*also-make-dependents*) lấy những module **downstream phụ thuộc vào seed**.

Với `contract-api` ở đầu graph, `-amd` là hướng impact analysis phù hợp. Với `invoice-cli`, `-am` giúp build cả pricing-core và contract-api nếu local repository chưa có artifacts nội bộ.

Không dùng `-pl :invoice-cli -amd` để kết luận toàn bộ API compatibility khi module contract-api mới chưa được build từ source hiện tại; Maven có thể resolve các dependency upstream từ local repository cũ.

## 16. Hợp đồng nguồn, nhị phân và hành vi: không chỉ Maven version

### 16.1. Source compatibility

Consumer Java đã viết:

```java
String output = new PriceQuote("BOOK", 5000).label();
```

Nếu API mới đổi tên `label()` thành `render()` và **xóa `label()`**, consumer sẽ lỗi compile ở lời gọi cũ. Việc chuyển version từ `1.2.0` lên `1.3.0` hay `2.0.0` không tự sửa Java source.

### 16.2. Binary compatibility

Một JAR consumer được compile từ trước có thể chứa bytecode gọi method descriptor `PriceQuote.label():String`. Nếu bạn thay JAR contract-api ở runtime bằng bản không còn method đó, JVM có thể ném `NoSuchMethodError` khi đi tới call site. Đây là lỗi liên kết nhị phân, khác với lỗi Maven không resolve được GAV.

Để phát hiện, cần API/ABI comparison giữa artifact **đã phát hành** và artifact **ứng viên**, sau đó chạy binary-compatibility tests thực tế khi policy yêu cầu. Những công cụ như **Revapi** hoặc **japicmp** có thể hỗ trợ; `javap` cũng giúp quan sát public signatures nhưng **không tự đánh giá mọi semantics của Java binary compatibility**.

### 16.3. Behavioral compatibility

Giữ method `label()` và signature y hệt chưa đủ nếu nó đổi từ:

```text
BOOK: 5000 cents
```

thành:

```text
BOOK;5000
```

Consumer nào parse chuỗi cũ có thể hỏng. Cùng kiểu dữ liệu, cùng phiên bản dependency, code vẫn compile và run nhưng output contract thay đổi.

Một thay đổi làm tròn giá, timezone, exception type, sort order hoặc serialization field cũng có thể phá behavior. Cần contract tests gắn với consumer thực, không chỉ unit tests của provider.

### 16.4. Phương án mở rộng API không phá client cũ

Nếu muốn thêm biểu diễn mới, có thể giữ method cũ rồi thêm method mới:

```java
public String render() {
    return sku + ";" + totalCents;
}

@Deprecated(forRemoval = false)
public String label() {
    return sku + ": " + totalCents + " cents";
}
```

Đây là **các method bổ sung trong body record `PriceQuote`** của project mẫu, không phải file Java độc lập. Consumer cũ tiếp tục gọi `label()` và nhận format cũ; consumer mới có thể dùng `render()`.

Khi có kế hoạch xóa `label()` ở một breaking release, cần công bố deprecation window, migration guide và version contract. **Đánh dấu `@Deprecated` tự nó không ngăn xóa method hoặc bảo đảm behavior tương thích**.

### 16.5. Không tự xem public record là “bất biến API” khi thay thành class

Java record tự sinh accessor, canonical constructor, equals/hashCode/toString và một số đặc điểm runtime/serialization. Nếu đổi `record PriceQuote` thành class khác, ngay cả khi còn method `sku()` và `totalCents()`, có thể thay đổi binary/serialization/reflection behavior.

Khi public API đã publish, cần đánh giá thay đổi cấu trúc kiểu dữ liệu như một phần contract review, không chỉ chạy bộ test nhỏ của module.

## 17. Đo phiên bản dependency thực sự được resolve

Sau khi cài bản mới vào local Maven repository trong môi trường được kiểm soát:

```bash
mvn -B clean install
mvn -B -pl :invoice-cli org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Cây dependency kỳ vọng của invoice-cli phải đi qua:

```text
demo.contract:invoice-cli:jar:1.3.0-SNAPSHOT
  demo.contract:pricing-core:jar:1.3.0-SNAPSHOT
    demo.contract:contract-api:jar:1.3.0-SNAPSHOT
```

Đây là **sơ đồ rút gọn**, không phải toàn bộ stdout nguyên văn của Dependency Plugin: JUnit và test dependencies có thể được liệt kê, các mốc scope có thể được thêm vào dòng và thứ tự output có thể khác.

Phải đối chiếu:

1. **Chỉ một version hợp lệ** cho mỗi internal artifact trong cây theo policy.
2. Không có chỗ nào kéo `1.2.0-SNAPSHOT` cũ ngoài ý muốn.
3. Scope/optional/exclusions của dependencies đúng thiết kế.
4. Runtime classpath có những artifact bắt buộc.
5. Consumer không bị Maven mediation chọn version mới chỉ vì gần hơn trong graph mà chưa qua compatibility testing.

**Lưu ý:** `dependency:tree` không thay thế kiểm chứng bytecode/JAR tại runtime. Nó cho biết dependency resolution của Maven ở một ngữ cảnh; dependency được container/launcher khác cấp có thể khác.

## 18. Enforcer: phát hiện xung đột, không tự tạo compatibility

**Maven Enforcer Plugin** có các rule như `dependencyConvergence` hoặc `requireUpperBoundDeps`. Một số tổ chức dùng chúng để phát hiện một artifact xuất hiện với nhiều version mâu thuẫn trong dependency tree.

Đoạn cấu hình tham khảo (không thêm vào POM runnable phía trên nếu chưa xét các dependencies hiện có):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-dependency-convergence</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence/>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
```

`dependencyConvergence` yêu cầu các phiên bản dependency của cùng artifact hội tụ theo chính sách rule, có thể báo fail khi hai đường transitive yêu cầu các version khác nhau. `requireUpperBoundDeps` kiểm tra vấn đề upper-bound ở resolution theo cơ chế riêng. **Hai rule không đồng nghĩa**, và không bảo đảm runtime behavior tương thích.

Khi bật Enforcer, phải kiểm tra version/loại dependencies ở từng module, xử lý exclusion/BOM/management một cách có chủ đích. Không “sửa” lỗi convergence chỉ bằng cách cưỡng ép một version bất kỳ rồi bỏ qua test.

## 19. BOM để đồng bộ phiên bản khi có nhiều consumer

**BOM** (*Bill of Materials*) là một POM thường có `packaging=pom`, chứa `dependencyManagement` cho một bộ artifacts được công bố tương thích với nhau.

Ví dụ một BOM phát hành:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.contract</groupId>
    <artifactId>contract-bom</artifactId>
    <version>1.3.0</version>
    <packaging>pom</packaging>
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>demo.contract</groupId>
                <artifactId>contract-api</artifactId>
                <version>1.3.0</version>
            </dependency>
            <dependency>
                <groupId>demo.contract</groupId>
                <artifactId>pricing-core</artifactId>
                <version>1.3.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

Đây là **một POM BOM độc lập minh họa**, không nằm trong project runnable lockstep ban đầu và không tự tạo artifacts contract-api/pricing-core. Cần publish BOM và các artifact tương ứng trước khi consumer dùng.

Consumer có thể import BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>demo.contract</groupId>
            <artifactId>contract-bom</artifactId>
            <version>1.3.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Sau đó consumer khai báo dependency vào contract-api/pricing-core theo đúng nhu cầu, không lặp version. **BOM chỉ quản lý phiên bản**; nó không tự thêm các thư viện vào classpath hoặc bảo đảm mọi API trong BOM tương thích ở runtime.

### 19.1. BOM không quản lý plugin versions

`dependencyManagement` / BOM phục vụ dependency resolution. `pluginManagement` quản lý build plugins. Không kỳ vọng import BOM của một framework sẽ tự pin mọi version Maven Compiler/Surefire/JAR Plugin trong mọi project.

Với Maven multi-module có parent chung, parent thường quản lý cả dependencyManagement và pluginManagement; với external consumers không kế thừa parent, BOM là cách phổ biến để chia sẻ dependency alignment mà không ép quan hệ parent.

### 19.2. BOM không giải quyết độc lập phiên bản magic

Nếu contract-api là `2.3.1` còn pricing-core là `4.1.0` và đã được xác minh tương thích, BOM có thể pin **đúng cặp đó**, không bắt hai artifact phải cùng `4.1.0`. Mục tiêu là một **bộ dependency versions được xác nhận**, không phải mọi con số bằng nhau.

## 20. CI-friendly versions: revision, sha1, changelist

Maven 3.5.0-beta-1 trở đi hỗ trợ những **placeholder đặc biệt** cho project version:

- `${revision}`
- `${sha1}`
- `${changelist}`

Đây là các tên được Maven CI-friendly versions hỗ trợ; **không thay thế** project `<version>` bằng một property bất kỳ như `${myBuildVersion}` rồi mong Maven core xử lý giống nhau.

### 20.1. Root project với revision

Một chiến lược khác so với hardcoded version của project mẫu:

```xml
<groupId>demo.contract</groupId>
<artifactId>version-contract-lab</artifactId>
<version>${revision}</version>
<packaging>pom</packaging>
<properties>
    <revision>1.2.0-SNAPSHOT</revision>
</properties>
```

Child có:

```xml
<parent>
    <groupId>demo.contract</groupId>
    <artifactId>version-contract-lab</artifactId>
    <version>${revision}</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

Lúc này, một CI job có thể chọn version:

```bash
mvn -B -Drevision=1.3.0-SNAPSHOT clean verify
```

**Đoạn này mô tả một mô hình CI-friendly thay thế, không phải hướng dẫn thêm đồng thời những dòng này vào POM hardcoded ở phần 8.** Để chuyển sang mô hình đó, phải thay cả root và các child references một cách nhất quán.

### 20.2. Chú ý đặc biệt trong inter-module dependencies

Tài liệu Maven CI-friendly versions cho **Maven 3** khuyến nghị dùng:

```xml
<dependency>
    <groupId>demo.contract</groupId>
    <artifactId>contract-api</artifactId>
    <version>${project.version}</version>
</dependency>
```

**Không dùng `${revision}` trực tiếp** làm version dependency giữa modules trong cấu hình Maven 3 CI-friendly theo cách tài liệu minh họa, vì dependency resolution có thể fail. Root/child project version có thể dùng `${revision}`, nhưng inter-module dependency version nên theo `${project.version}` hoặc một dependencyManagement đã kiểm chứng tương thích với mô hình này.

Một bản Maven 3 CI-friendly không tự biến mọi POM dependency/parent version thành giá trị đã resolve khi phát hành, vì vậy còn có vấn đề **consumer POM** cần xử lý bằng Flatten Plugin.

### 20.3. Flatten Maven Plugin trước install/deploy Maven 3

Với CI-friendly placeholders trên Maven 3, tài liệu Maven hướng dẫn sử dụng **Flatten Maven Plugin** để tránh publish POM còn `${revision}` không được consumer resolve đúng.

Đoạn plugin ví dụ cho một project đã chuyển sang CI-friendly:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>flatten-maven-plugin</artifactId>
    <version>1.8.0</version>
    <configuration>
        <updatePomFile>true</updatePomFile>
        <flattenMode>resolveCiFriendliesOnly</flattenMode>
    </configuration>
    <executions>
        <execution>
            <id>flatten</id>
            <phase>process-resources</phase>
            <goals>
                <goal>flatten</goal>
            </goals>
        </execution>
        <execution>
            <id>flatten.clean</id>
            <phase>clean</phase>
            <goals>
                <goal>clean</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn POM tham khảo**, không được thêm mặc định vào demo hardcoded version. `resolveCiFriendliesOnly` được thiết kế để resolve các biến revision/sha1/changelist mà giữ các phần POM khác. `updatePomFile=true` quan trọng cả với `packaging=pom` khi cần POM đã flatten được dùng cho install/deploy.

Sau build/install, phải inspect **POM thật được cài/deploy** để chắc chắn consumer nhìn thấy version concrete và dependency metadata hợp lệ. **Đừng chỉ kiểm tra source POM trong Git**.

### 20.4. Maven 4 có thay đổi

Với Maven 4 và model version `4.1.0`, tài liệu chính thức mô tả cơ chế tự resolve parent/subproject dependency versions tốt hơn, không cần cùng mẫu cấu hình Flatten Plugin như Maven 3.

Tuy nhiên không được sao chép một POM model `4.1.0` sang Maven 3 rồi mong build được. Migration cần xác nhận Maven version, cấu trúc subprojects, plugin compatibility, POM được publish và downstream consumers.

## 21. SNAPSHOT, release và tính bất biến

`1.3.0-SNAPSHOT` biểu thị một phiên bản phát triển có thể được publish nhiều lần theo snapshot repository policy; byte artifact được resolve có thể thay đổi giữa các lần build dù tọa độ logic cùng SNAPSHOT.

`1.3.0` thường được tổ chức xem là release version, có chính sách không ghi đè. **Đây là policy quan trọng, không phải một kiểm chứng API compatibility tự động của Maven.**

Khi release:

1. Chọn version và scope release train rõ ràng.
2. Xác nhận không còn dependency SNAPSHOT ngoài policy.
3. Build từ commit và toolchain được duyệt.
4. Chạy full tests, contract/API diff, smoke/integration tests nếu cần.
5. Kiểm tra POM/JAR/checksum/metadata cuối.
6. Gắn SCM tag theo quy trình, tránh nhầm tag với artifact thực được publish.
7. Chỉ deploy khi repository credentials/policy phù hợp.
8. Không viết lại release artifact đã được consumer sử dụng.

Maven Release Plugin hỗ trợ các goals `release:prepare`, `release:perform` và `release:update-versions`. Đây là workflow release có thể tương tác với SCM/tag/deploy; **không chạy tùy tiện trên repository sản xuất chỉ để thử sửa POM**.

Trong bài thực hành chỉ cần `versions:set` + `mvn clean verify`. Không có server deploy thật.

## 22. Đảm bảo consumer POM được phát hành hợp lệ

Đối với một thư viện, bản bàn giao có ít nhất:

```text
contract-api-1.3.0.jar
contract-api-1.3.0.pom
```

Với lockstep release train, những tọa độ tham chiếu mà POM của pricing-core publish cần đúng version của contract-api được phát hành. Nếu POM của pricing-core còn dependency vào `contract-api:1.2.0-SNAPSHOT` trong khi runtime yêu cầu API 1.3.0, consumer ngoại repository có thể kéo sai JAR.

Một quy trình QA POM publish:

- `mvn clean install` trong môi trường đã kiểm soát.
- Xác định local repository path, thường `~/.m2/repository/demo/contract/pricing-core/1.3.0/` đối với release concrete.
- Mở **POM đã install**, kiểm tra parent/dependencies và properties còn cần khi được consumer đọc.
- Tạo một consumer project nhỏ **không nằm trong Reactor producer** và resolve từ repository đã publish/stage.
- Compile và chạy smoke test consumer với đúng dependency versions.
- Không coi “Maven install của producer pass” là bằng chứng consumer có thể resolve POM sau publish.

### 22.1. Vì sao parent POM cũng phải được phát hành?

POM của một child có `<parent>` trỏ tới một artifact. Một consumer tải child POM có thể cần parent POM để build effective model và giải dependency versions. Nếu root parent chưa được install/deploy theo đúng GAV/version, consumer có thể gặp `Non-resolvable parent POM`, dù file child JAR tồn tại.

Với BOM/Flatten strategy, cách xử lý có thể khác, nhưng nguyên tắc giữ nguyên: **POM consumer nhận phải tự resolve được theo repository setup của consumer**.

## 23. Bài kiểm tra hợp đồng trước/sau thay đổi API

### 23.1. Thay đổi tương thích: giữ method cũ

Giả sử release mới muốn định dạng machine-readable. Thêm method `render()` và giữ `label()` có output cũ như phần 16.4. Consumer cũ vẫn compile và nhận chuỗi `BOOK: 5000 cents`; consumer mới có thể chọn API mới.

Các test cần kiểm tra:

- `PriceQuoteTest` giữ `label()`.
- `QuoteFactoryTest` và `InvoiceCliTest` pass.
- Test của consumer ngoài Reactor đã build với artifact cũ tiếp tục chạy.
- API diff tool xác nhận không vô tình xóa public members.
- Các thay đổi hành vi/documentation được công bố rõ ràng.

### 23.2. Thay đổi phá vỡ contract: xóa label()

Nếu xóa `label()` nhưng QuoteFactory vẫn gọi nó, compile sẽ fail. Một lỗi có thể xuất hiện như:

```text
cannot find symbol
  symbol:   method label()
  location: class demo.contract.api.PriceQuote
```

Đây là **mẫu lỗi minh họa**, không phải log thực tế đã chạy. Không được “sửa” bằng cách chỉ nâng version trong POM hoặc xóa test. Cần quyết định:

- Giữ adapter/deprecation nếu muốn compatible release.
- Hoặc phát hành một breaking contract/version và cập nhật/migrate consumers theo plan.
- Kiểm tra những binary consumers vẫn đang chạy phiên bản cũ.

Nếu API có serialization hoặc dữ liệu bên ngoài Java, cần thêm kiểm chứng tương ứng; Maven version metadata không bảo đảm wire compatibility.

## 24. CI gate cho một lần đồng bộ version

Một quy trình an toàn:

```text
Checkout đúng commit, xác nhận working tree sạch
          │
          ▼
Chọn lockstep hay independent version policy
          │
          ▼
Chạy Versions Plugin hoặc thay cấu hình CI-friendly có review
          │
          ▼
git diff: parent versions + dependencyManagement + module references
          │
          ▼
mvn -B clean verify toàn Reactor
          │
          ▼
Reactor Summary + Surefire XML + dependency resolution checks
          │
          ▼
API/ABI diff với artifact đã phát hành + contract tests consumers
          │
          ▼
Install vào repository thử nghiệm, kiểm POM/JAR thật
          │
          ▼
Consumer-from-repository smoke test, security/provenance checks
          │
          ▼
Phát hành theo policy và lưu record version/commit/artifact checksum
```

Không phải Maven tự thực hiện tất cả những bước trên từ một `versions:set`. Bài demo cung cấp những test cần thiết để thấy cách QA phiên bản, còn production cần bổ sung kiểm chứng phù hợp hệ thống.

### 24.1. Không sử dụng local repository cũ làm bằng chứng duy nhất

Một artifact `contract-api:1.2.0-SNAPSHOT` cũ trong `~/.m2` có thể che việc POM consumer chưa đồng bộ hoặc làm test dùng byte không thuộc working tree hiện tại. Khi kiểm chứng internal dependency sau thay đổi nên chạy Reactor từ source của cùng commit, rồi kiểm tra dependency tree/effective POM và artifact bytes.

`mvn clean` chỉ xóa build output trong project; **không tự xóa toàn bộ local Maven repository**. Vì vậy “đã clean” chưa đủ nếu dependency bị resolve ngoài Reactor từ một SNAPSHOT cũ.

### 24.2. -fae và lỗi chưa được kiểm chứng

Nếu chạy:

```bash
mvn -B -fae clean verify
```

Maven có thể tiếp tục những module độc lập sau khi một module fail, nhưng các module downstream của module failed có thể bị `SKIPPED`. Không cộng skipped như pass. CI phải báo rõ module nào đã test, module nào chưa có bằng chứng test thành công.

### 24.3. Điều gì cần lưu trong kết quả review?

- Old/new version policy và lý do thay đổi.
- Danh sách POMs/module metadata đã sửa.
- Maven/JDK/plugin versions và source commit.
- Kết quả `clean verify`, test counts, thất bại/skipped.
- Dependency tree và các conflicts đã xử lý.
- API compatibility report và consumer integration results.
- POM/JAR cuối, repository location và checksum.
- Rollback path, release tag và người phê duyệt theo quy trình.

Đây là bằng chứng giúp tránh việc một build “xanh” nhưng artifact publish không còn dùng được bởi các consumer ngoài repository.

## 25. Troubleshooting

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `Non-resolvable parent POM` sau bump | Child vẫn trỏ parent version cũ | Xem `<parent><version>` và relativePath, thử versions:update-child-modules khi phù hợp |
| `Could not find artifact contract-api:1.2.0-SNAPSHOT` | Dependency version còn cũ | Kiểm tra dependencyManagement, explicit versions và effective POM |
| `Could not find artifact contract-api:1.3.0-SNAPSHOT` | Module chưa build/installed, repo thiếu artifact | Kiểm tra selected Reactor và repository resolution |
| Root nâng version nhưng module vẫn 1.2 | Child có `<version>` riêng hoặc không kế thừa đúng parent | Xem POM và output versions:set |
| Dependency graph sai sau bump | Có version override ngoài management | Chạy effective-pom/dependency:tree |
| Maven build PASS nhưng consumer cũ fail compile | Public method/constructor bị đổi | So API trước/sau, sửa adapter hoặc migration |
| Java chạy nhưng `NoSuchMethodError` | Binary consumer cũ gặp API mới thiếu method | Kiểm tra runtime classpath/ABI và artifacts đang tải |
| Java compile PASS nhưng business output khác | Behavioral contract thay đổi | Bổ sung golden/contract tests và review semantics |
| Consumer ngoài Reactor không resolve POM | Parent/BOM chưa publish hoặc POM chứa placeholder CI-friendly | Kiểm tra POM đã deploy, dùng Flatten trên Maven 3 khi cần |
| `versions:set` tạo backups | Mặc định `generateBackupPoms=true` | Review backups, commit/revert theo policy |
| Đổi `${revision}` nhưng inter-module dependency fail | Dùng placeholder không phù hợp trong dependency version | Tham khảo Maven CI-friendly guide, dùng `${project.version}` |
| POM dùng `${customVersion}` làm project version không hợp lệ | Maven CI-friendly chỉ hỗ trợ tên đặc biệt | Dùng `${revision}`/`${sha1}`/`${changelist}` đúng mô hình |
| BOM được import nhưng class không xuất hiện | BOM chỉ quản lý version, không thêm dependency | Khai báo actual `<dependency>` |
| Hai version transitive cùng tồn tại trong graph | Maven mediation và management chưa phù hợp | Đọc dependency tree, dùng Enforcer |
| Local PASS nhưng CI resolve version khác | SNAPSHOT stale, settings/repositories/profile khác | Kiểm tra source/byte artifacts và dependency graph |
| Đổi plugin version khi bump project gây lỗi | Trộn nhiều thay đổi không cùng mục tiêu | Tách PR nâng plugin/dependency riêng |
| Chỉ test contract-api nhưng pricing-core lỗi | Không chạy downstream consumers | Dùng `-pl :contract-api -amd` hoặc full Reactor |
| Module độc lập bị ép version không phù hợp | Chọn nhầm lockstep cho release policy độc lập | Thiết kế independent versions và BOM tương thích |
| Maven 4 behavior khác Maven 3 | Model 4.1.0 và subproject version resolution khác | Dùng docs đúng Maven version và kiểm consumer POM |
| `release:prepare` sửa SCM/tag ngoài ý muốn | Dùng Release Plugin như lệnh thử nghiệm | Chạy trên branch và theo release process |
| XML test report cũ vẫn trên disk | Workspace/test subset chưa clean | Đối chiếu Reactor Summary và report mới |
| Dependency type/classifier bị bỏ khi quản lý version | BOM/management entry không khớp artifact đặc biệt | Kiểm tra type/classifier/scope của entry |

## 26. Câu hỏi tự kiểm tra

**1.** Tại sao bốn module cùng phiên bản `1.3.0` vẫn có thể không tương thích?

Vì Maven đồng bộ artifact metadata nhưng không tự bảo đảm public signatures, binary linkage, business behavior hoặc external protocols không đổi.

**2.** `dependencyManagement` có tự đưa contract-api vào classpath của standalone-tool không?

Không. Module phải khai báo actual `<dependency>`, và classpath phụ thuộc scope/transitivity tương ứng.

**3.** Trong dự án mẫu, vì sao invoice-cli có thể dùng pricing-core mà không khai báo version?

Vì parent `dependencyManagement` quản lý version pricing-core bằng `${project.version}`; invoice-cli vẫn phải khai báo dependency vào pricing-core.

**4.** Có thể nâng một module độc lập từ `2.3.1` lên `4.1.0` chỉ vì app consumer có version `4.1.0` không?

Không. Independent versions phải dựa trên artifact release/compatibility contract riêng. Bằng nhau về số là không cần thiết.

**5.** Vì sao phải kiểm tra POM đã install/deploy khi dùng `${revision}` trên Maven 3?

Vì consumer POM được publish không được để placeholder chưa resolve theo cách khiến Maven của consumer không xử lý được. Tài liệu Maven hướng dẫn Flatten Plugin.

**6.** Một lần `mvn clean verify` PASS có đủ chứng minh binary compatibility với consumer đã được compile từ phiên bản cũ không?

Không. Cần so ABI/API và, khi cần, chạy binary consumer cũ với artifact mới. Test hiện tại trong cùng Reactor có thể đã được sửa đồng thời với provider.

**7.** Vì sao `versions:set` không thay thế review `git diff`?

Goal có thể cập nhật nhiều POM references, nhưng không hiểu policy phát hành hoặc business contract. Diff giúp phát hiện version override ngoài ý muốn, sai parent và thay đổi cấu hình khác.

## 27. Checklist trước khi chấp nhận một version sync

- [ ] Đã xác định lockstep release train hay module independent versions?
- [ ] Root project version, child parent versions và module own versions nhất quán theo policy?
- [ ] Inter-module dependencies nhắm đúng artifacts/version; không còn hardcode cũ?
- [ ] `dependencyManagement` quản lý version nhưng không làm mất actual `<dependencies>`?
- [ ] Các BOM và property versions chỉ được đổi khi có compatibility review?
- [ ] Không vô tình nâng compiler/test/runtime dependencies ngoài mục tiêu?
- [ ] `versions:set`/`update-child-modules` được chạy trong môi trường có backup/VCS review?
- [ ] `git diff` chỉ có những thay đổi được ủy quyền?
- [ ] `mvn -B clean verify` pass trên toàn Reactor cùng commit/JDK đã chọn?
- [ ] Các downstream consumers có tests/compile QA phù hợp?
- [ ] Không có FAIL/SKIPPED bị tính nhầm là PASS?
- [ ] Dependency tree/effective POM và Maven repository không resolve artifact cũ ngoài ý muốn?
- [ ] API/ABI diff với artifact đã publish được review?
- [ ] Behavioral, serialization, HTTP/data contracts vẫn tương thích hoặc có migration plan?
- [ ] Nếu CI-friendly trên Maven 3, Flatten Plugin và published POM được kiểm chứng?
- [ ] Parent/BOM POMs cũng có thể được consumer resolve sau install/deploy?
- [ ] SNAPSHOT/release repository policies, checksum, provenance và rollback path phù hợp?
- [ ] Nếu có breaking change, version contract và thông tin migration được công bố rõ ràng?

**Kết luận:** đồng bộ version Maven đúng cách là giữ **GAV, parent, dependencyManagement, inter-module resolution và published POM** nhất quán. Với một release train chung, parent inheritance và quản lý dependency version tập trung giúp giảm drift; Versions Maven Plugin hỗ trợ đổi version đồng loạt. Nhưng một chữ số version giống nhau không phải hợp đồng tương thích. Phải kết hợp **full Reactor build, downstream consumer tests, dependency tree, API/ABI diff và kiểm tra artifact thật được publish** để bảo đảm việc đồng bộ không làm hỏng consumer.

### Tài liệu chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Maven CI Friendly Versions](https://maven.apache.org/guides/mini/guide-maven-ci-friendly.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Maven 4 Multi-Subproject Guide](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html)
- [MojoHaus Versions Maven Plugin — versions:set](https://www.mojohaus.org/versions/versions-maven-plugin/set-mojo.html)
- [MojoHaus Versions Maven Plugin — update-child-modules](https://www.mojohaus.org/versions/versions-maven-plugin/examples/update-child-modules.html)
- [MojoHaus Maven Flatten Plugin — Usage](https://www.mojohaus.org/flatten-maven-plugin/usage.html)
- [Apache Maven Enforcer — dependencyConvergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html)
- [Apache Maven Release Plugin — Usage](https://maven.apache.org/components/maven-release/maven-release-plugin/)
