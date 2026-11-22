# Thiết kế parent, BOM và ứng dụng nhiều mô-đun với Apache Maven

## 1. Mục tiêu của bài thực hành tổng hợp

Khi một ứng dụng Java lớn dần, việc giữ mọi class trong một Maven project và khai báo phiên bản dependencies lặp lại ở nhiều `pom.xml` trở nên khó bảo trì. Maven có ba cơ chế liên quan nhưng **không đồng nghĩa**:

1. **Parent POM (kế thừa):** chuẩn hóa thuộc tính Java, plugin versions, plugin configuration và những chính sách build mà project con kế thừa.
2. **BOM (Bill of Materials):** công bố danh mục phiên bản nhất quán trong `<dependencyManagement>` để các project khác có thể **import**, dù không sử dụng parent POM của bên phát hành.
3. **Multi-module Reactor (tổng hợp):** tập hợp modules bằng `<modules>` để Maven sắp xếp và build các project liên quan theo quan hệ dependencies.

Bài tập xây một hệ thống **Java 17 + Maven 3.9.x (POM model 4.0.0)**, gồm:

- BOM độc lập `edu.demo:commerce-bom:1.0.0`.
- Parent kiêm aggregator `edu.demo:commerce-parent:1.0.0`.
- Ba module: `commerce-api`, `pricing-engine`, `checkout-app`.
- Consumer **không kế thừa parent**, chỉ import BOM và dùng hai library modules từ Maven repository.
- Tests JUnit Jupiter 5: **3 tests ở API, 2 ở engine, 2 ở app, 2 ở consumer**.
- Các lệnh build, install, chạy ứng dụng và xác minh dependency versions/scope.
- Phép thử lỗi có chủ đích và phương pháp CI/release đúng thứ tự.

**Kết quả cần đạt:** một lần Maven Reactor build có thể compile/package các modules theo đúng thứ tự, các modules dùng cùng phiên bản thư viện mà không copy version vào từng POM, và consumer độc lập resolve được **JAR + POM + BOM + parent POM** từ một repository hợp lệ.

Bài ưu tiên thiết kế **chạy được từ source sạch**, thay vì chỉ đặt XML minh họa cạnh nhau mà không có chuỗi build rõ ràng.

## 2. Phân biệt chính xác parent, aggregator và BOM

| Khái niệm | Nằm ở đâu? | Tác dụng | Không tự làm gì? |
| --- | --- | --- | --- |
| Parent POM | Child khai báo `<parent>` | Kế thừa properties, dependency/plugin management và cấu hình phù hợp | Không tự thêm tất cả siblings vào classpath |
| Aggregator | Root khai báo `<modules>` | Gom modules thành một Reactor build | Không tạo quan hệ dependency chỉ vì cùng modules |
| BOM | POM `packaging=pom` có `<dependencyManagement>` | Quản lý versions của các dependencies được khai báo | Không kéo mọi JAR trong BOM vào classpath |
| Module dependency | Child có `<dependencies>` trỏ GAV khác | Thêm classpath relation và tạo cạnh sắp xếp Reactor | Không quản lý plugin compiler/surefire |
| Plugin management | Parent có `<pluginManagement>` | Chuẩn hóa plugin version/default config | Không tự kích hoạt mọi custom plugin goal |
| Project dependency management | Parent/BOM có `<dependencyManagement>` | Quản lý GAV/version/scope khi dependency được dùng | Không tạo một direct dependency mới |

**Mô hình suy nghĩ đúng:**

- “Build cùng nhau” = **aggregation**.
- “Kế thừa chuẩn build” = **parent**.
- “Dùng chung phiên bản dependencies” = **dependencyManagement/BOM**.
- “Dùng class của nhau” = **dependency thật trong `<dependencies>`**.

Một POM có thể đồng thời là parent và aggregator. Nhưng **BOM không cần là parent**, và một BOM tốt cho consumer có thể phát hành độc lập để tránh buộc consumer kế thừa cả cấu hình build của hệ thống bên phát hành.

## 3. Kiến trúc của ví dụ

Toàn bộ project thực hành:

```text
commerce-lab/
├── commerce-bom/
│   └── pom.xml
├── commerce-parent/
│   ├── pom.xml
│   ├── commerce-api/
│   │   ├── pom.xml
│   │   ├── src/main/java/edu/demo/api/Product.java
│   │   └── src/test/java/edu/demo/api/ProductTest.java
│   ├── pricing-engine/
│   │   ├── pom.xml
│   │   ├── src/main/java/edu/demo/pricing/PriceFormatter.java
│   │   └── src/test/java/edu/demo/pricing/PriceFormatterTest.java
│   └── checkout-app/
│       ├── pom.xml
│       ├── src/main/java/edu/demo/app/CheckoutApp.java
│       └── src/test/java/edu/demo/app/CheckoutAppTest.java
└── standalone-client/
    ├── pom.xml
    ├── src/main/java/edu/demo/client/ClientApp.java
    └── src/test/java/edu/demo/client/ClientAppTest.java
```

**Quan hệ Maven Reactor:**

```text
commerce-parent (packaging=pom)
      |
      +-- commerce-api
      |         |
      |         v
      +-- pricing-engine  (depends on commerce-api)
      |         |
      |         v
      +-- checkout-app   (depends on commerce-api + pricing-engine)

commerce-bom   (POM riêng, build/install trước)
      |
      +---- import bởi commerce-parent
      +---- import bởi standalone-client

standalone-client (POM độc lập, build sau install)
      |
      +---- dependency: commerce-api
      +---- dependency: pricing-engine
```

**Chủ ý về vòng phụ thuộc:** BOM được giữ ở project **riêng ngoài Reactor** và **install trước**. Root parent import BOM đã có trong repository, sau đó các modules trong Reactor resolve lẫn nhau. Như vậy ví dụ không dựa vào việc một Maven 3 build phải import một BOM chưa được install nhưng đang được build cùng Reactor. Với một hệ thống khác có quy trình publication riêng, có thể thiết kế BOM là module được release độc lập; vẫn phải tôn trọng thứ tự resolve và published metadata.

## 4. Phiên bản, điều kiện môi trường và quy ước

Ví dụ sử dụng:

- Maven **3.9.x**; Maven 4 có thể build POM model `4.0.0` khi plugins và JDK tương thích, nhưng **không yêu cầu Maven 4** ở bài này.
- JDK **17+** với `maven.compiler.release=17`.
- Maven Compiler Plugin `3.13.0`.
- Maven Surefire Plugin `3.2.5`.
- Maven Resources Plugin `3.3.1`, Clean Plugin `3.3.2`, JAR Plugin `3.4.2`, Install Plugin `3.1.2`.
- JUnit Jupiter `5.10.2`.
- Apache Commons Lang `3.14.0`, được code của engine sử dụng thật.

Các phiên bản được chọn nhằm cố định bài thực hành, **không khẳng định mới nhất** hoặc phù hợp mọi security baseline. Nếu dự án của tổ chức có BOM, mirror hoặc JDK policy khác, chọn các phiên bản đã được duyệt rồi thử lại toàn bộ build.

Tên GAV trong ví dụ:

| Vai trò | GAV | Packaging |
| --- | --- | --- |
| BOM | `edu.demo:commerce-bom:1.0.0` | `pom` |
| Parent + aggregator | `edu.demo:commerce-parent:1.0.0` | `pom` |
| Module API | `edu.demo:commerce-api:1.0.0` | `jar` |
| Module engine | `edu.demo:pricing-engine:1.0.0` | `jar` |
| Module app | `edu.demo:checkout-app:1.0.0` | `jar` |
| Consumer ngoài | `edu.demo:standalone-client:1.0.0` | `jar` |

**Dùng đúng GAV** trong BOM và child POM. Sai một chữ của `artifactId` có thể làm Maven tìm một artifact khác hoặc báo missing dependency.

## 5. Thiết kế BOM độc lập

File `commerce-bom/pom.xml` là một **project không có Java source**. Nó ghi versions tập trung cho các artifacts cùng hệ và thư viện ngoài:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>commerce-bom</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>edu.demo</groupId>
                <artifactId>commerce-api</artifactId>
                <version>1.0.0</version>
            </dependency>
            <dependency>
                <groupId>edu.demo</groupId>
                <artifactId>pricing-engine</artifactId>
                <version>1.0.0</version>
            </dependency>
            <dependency>
                <groupId>edu.demo</groupId>
                <artifactId>checkout-app</artifactId>
                <version>1.0.0</version>
            </dependency>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>3.14.0</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.10.2</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.1. Tại sao BOM không có `<parent>`?

Trong thiết kế thực hành này, BOM **cố ý không kế thừa** `commerce-parent`. Khi một consumer chỉ cần version catalog, Maven không phải tải thêm parent build POM của BOM. BOM vì thế có thể install hoặc deploy **trước** parent, tránh dependency vòng:

```text
BOM → parent?    (KHÔNG, trong ví dụ này)
Parent → import BOM    (CÓ)
```

Một BOM của hệ thống thực **có thể** có parent hợp lệ, nhưng lúc đó cả parent chain cần được publish và resolve bởi consumers. Độc lập giúp demo rõ ràng và portable hơn.

### 5.2. Vì sao BOM chỉ có dependencyManagement?

`<dependencyManagement>` **không tự đưa** `commerce-api`, `pricing-engine`, Commons Lang hoặc JUnit vào classpath của một project import BOM. Nó chỉ cung cấp **metadata phiên bản** khi project khai báo dependency thật.

Ví dụ consumer sau import BOM có thể viết:

```xml
<dependency>
    <groupId>edu.demo</groupId>
    <artifactId>pricing-engine</artifactId>
</dependency>
```

Maven lấy version `1.0.0` từ BOM, nhưng **chỉ** vì consumer có dependency này. Nếu không khai báo, engine không tự xuất hiện.

### 5.3. Vì sao BOM dùng `packaging=pom` trong Maven 3?

Đây là cú pháp BOM tiêu chuẩn cho Maven 3/POM model `4.0.0`. Maven 4 model `4.1.0` có thêm `packaging=bom` trong build model, nhưng không cần tính năng đó để minh họa một BOM có thể import được bởi Maven 3. Khi phát hành BOM mới bằng Maven 4, vẫn phải kiểm **consumer POM** tương thích.

## 6. Import BOM vào parent kiêm aggregator

File `commerce-parent/pom.xml` dùng hai cơ chế khác nhau:

- `<modules>` cho **Reactor aggregation**.
- `<dependencyManagement>` `scope=import`, `type=pom` để **nhập BOM**.

POM hoàn chỉnh:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>commerce-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>commerce-api</module>
        <module>pricing-engine</module>
        <module>checkout-app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>edu.demo</groupId>
                <artifactId>commerce-bom</artifactId>
                <version>1.0.0</version>
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
                    <configuration>
                        <failIfNoTests>true</failIfNoTests>
                    </configuration>
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

### 6.1. Vì sao không đưa JUnit vào `<dependencies>` của root?

Nếu root parent khai báo JUnit trong `<dependencies>` thông thường, child modules **kế thừa một dependency thật** theo Maven inheritance; điều này có thể khiến mọi child có JUnit dù không dùng.

Ở ví dụ này parent **chỉ import BOM vào `dependencyManagement`**, còn modules quyết định dependency nào cần. Chỉ các modules có tests mới khai báo JUnit test dependency, làm classpath rõ hơn.

### 6.2. PluginManagement khác Plugins

`<pluginManagement>` chỉ định **version/configuration defaults** cho plugins khi chúng được dùng. Với các child packaging `jar`, những lifecycle goals mặc định như compiler, Surefire, JAR Plugin được Maven liên kết, nên chúng có thể nhận cấu hình/version đã quản lý.

Nhưng nếu có một plugin custom goal không thuộc default lifecycle, nó **không tự chạy** chỉ vì xuất hiện trong `pluginManagement`. Phải khai báo plugin thực sự ở `<build><plugins>` và execution/goal phù hợp.

### 6.3. Parent không được import BOM từ “chính mình”

Vì `commerce-bom` tồn tại ngoài `commerce-parent` Reactor, BOM được cài trước khi Maven bắt đầu dựng effective POM của parent/children. Maven 3 không phải giải quyết một BOM mới chỉ tồn tại dưới dạng source module chưa vào repository.

**Trình tự build bắt buộc của lab:** BOM install → parent Reactor install → consumer verify.

## 7. Module API: cấu hình POM

File `commerce-parent/commerce-api/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>edu.demo</groupId>
        <artifactId>commerce-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>commerce-api</artifactId>
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

Phần `<parent>` khai báo **full GAV**; child không phải lặp lại `groupId=edu.demo`, `version=1.0.0`. `relativePath` giúp Maven tìm parent source POM khi checkout đủ repository. BOM import trong parent sẽ cung cấp JUnit version 5.10.2 cho child.

**Lưu ý:** `relativePath=../pom.xml` là quan hệ inheritance, **không** phải cách thêm source của module khác vào compile classpath.

## 8. API Java 17: Product.java

File `commerce-parent/commerce-api/src/main/java/edu/demo/api/Product.java`:

```java
package edu.demo.api;

public record Product(String sku, long cents) {

    public Product {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku required");
        }
        if (cents < 0) {
            throw new IllegalArgumentException("negative cents");
        }
    }
}
```

`record` là cú pháp Java hiện đại và được hỗ trợ ở `release=17`. Constructor compact kiểm invariant: SKU không rỗng và giá không âm. `Product` không phụ thuộc Commons Lang; module API có thể dùng độc lập chỉ với JDK.

### 8.1. API unit tests

File `commerce-parent/commerce-api/src/test/java/edu/demo/api/ProductTest.java`:

```java
package edu.demo.api;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ProductTest {

    @Test
    void storesProductData() {
        Product product = new Product(" tea ", 2500);
        assertEquals(" tea ", product.sku());
        assertEquals(2500L, product.cents());
    }

    @Test
    void rejectsBlankSku() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> new Product("  ", 100));
        assertEquals("sku required", error.getMessage());
    }

    @Test
    void rejectsNegativePrice() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> new Product("tea", -1));
        assertEquals("negative cents", error.getMessage());
    }
}
```

**Kỳ vọng API: 3 tests, failures 0, errors 0, skipped 0.** Trường hợp `Product(" tea ", 2500)` giữ nguyên SKU có khoảng trắng; việc normalize SKU thuộc engine ở phần sau, tránh API tự biến đổi dữ liệu mà test không ghi nhận.

## 9. Module pricing-engine: POM và dependencies có scope đúng

File `commerce-parent/pricing-engine/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>edu.demo</groupId>
        <artifactId>commerce-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>pricing-engine</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>edu.demo</groupId>
            <artifactId>commerce-api</artifactId>
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
</project>
```

Đây là **chỗ kết nối cả ba cơ chế**:

- **Inheritance:** child nhận compiler release/plugin configuration từ parent.
- **BOM:** dependency entries không có `<version>`, vì parent import BOM quản lý `commerce-api=1.0.0`, Commons Lang 3.14.0, JUnit 5.10.2.
- **Reactor:** vì `pricing-engine` có dependency thật tới `commerce-api`, Maven xây API trước engine.

Nếu chỉ có `<module>commerce-api</module>` trong parent mà engine **không khai báo `<dependency>`** tới API, Java compiler của engine sẽ không tự thấy `edu.demo.api.Product`.

## 10. Pricing logic dùng dependency ngoài thật

File `commerce-parent/pricing-engine/src/main/java/edu/demo/pricing/PriceFormatter.java`:

```java
package edu.demo.pricing;

import java.util.Locale;
import edu.demo.api.Product;
import org.apache.commons.lang3.StringUtils;

public final class PriceFormatter {
    private PriceFormatter() {
    }

    public static String format(Product product) {
        String normalized = StringUtils.upperCase(
                StringUtils.trimToEmpty(product.sku()),
                Locale.ROOT);
        return "SKU " + normalized + ": "
                + product.cents() + " cents";
    }
}
```

`PriceFormatter` sử dụng **hai APIs khác nhau**:

1. `edu.demo.api.Product` từ sibling `commerce-api` **đã được engine khai báo**.
2. `org.apache.commons.lang3.StringUtils` từ Commons Lang **đã được BOM quản lý version** và engine khai báo dependency thật.

Stdout khi gọi Java expression:

```java
PriceFormatter.format(new Product(" tea ", 2500))
```

trả về:

```text
SKU TEA: 2500 cents
```

Đây là **biểu thức minh họa**, không phải một Java file chạy độc lập. `CheckoutApp` ở phần sau có `main`.

### 10.1. Engine tests

File `commerce-parent/pricing-engine/src/test/java/edu/demo/pricing/PriceFormatterTest.java`:

```java
package edu.demo.pricing;

import edu.demo.api.Product;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PriceFormatterTest {

    @Test
    void normalizesSku() {
        assertEquals("SKU TEA: 2500 cents",
                PriceFormatter.format(new Product(" tea ", 2500)));
    }

    @Test
    void supportsZeroCents() {
        assertEquals("SKU BOOK: 0 cents",
                PriceFormatter.format(new Product("book", 0)));
    }
}
```

**Engine có 2 JUnit tests.** Nếu bỏ Commons Lang dependency hoặc đặt sai scope `test`, main compile của `PriceFormatter` sẽ fail. Nếu engine không khai báo `commerce-api`, Java compiler không tìm được class `Product`.

## 11. Module checkout-app: phụ thuộc trực tiếp cả API và engine

File `commerce-parent/checkout-app/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>edu.demo</groupId>
        <artifactId>commerce-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>checkout-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>edu.demo</groupId>
            <artifactId>commerce-api</artifactId>
        </dependency>
        <dependency>
            <groupId>edu.demo</groupId>
            <artifactId>pricing-engine</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Tại sao app khai báo **trực tiếp cả API lẫn engine**? Vì app source import `Product` và `PriceFormatter` trực tiếp. `Product` cũng có thể xuất hiện bắc cầu qua engine, nhưng dựa vào bắc cầu để sử dụng API trực tiếp làm code dễ vỡ khi engine thay dependency graph. Maven khuyến nghị khai báo trực tiếp thư viện mà source dùng trực tiếp.

Vì app không import `StringUtils`, nó **không cần khai báo Commons Lang trực tiếp**. Khi chạy, Commons Lang sẽ đến từ dependency bắc cầu của engine theo compile/runtime scope, miễn published POM của engine có metadata đúng.

## 12. Java application có main() và test

File `commerce-parent/checkout-app/src/main/java/edu/demo/app/CheckoutApp.java`:

```java
package edu.demo.app;

import edu.demo.api.Product;
import edu.demo.pricing.PriceFormatter;

public final class CheckoutApp {
    private CheckoutApp() {
    }

    public static String receipt(String sku, long cents) {
        Product product = new Product(sku, cents);
        return "CHECKOUT => " + PriceFormatter.format(product);
    }

    public static void main(String[] args) {
        System.out.println(receipt(" tea ", 2500));
    }
}
```

Sau khi project được compile và runtime classpath đúng, stdout **chính xác của riêng Java main**:

```text
CHECKOUT => SKU TEA: 2500 cents
```

Lưu ý: Maven Jar Plugin tạo JAR **bình thường**, không phải fat JAR. Do đó lệnh `java -jar checkout-app-1.0.0.jar` **không phải** demo đúng nếu chưa khai báo `Main-Class` và gộp/cấp đủ dependencies. Phần lệnh chạy dưới đây dùng **Maven Exec Plugin runtime classpath** để tránh sai lầm này.

File `commerce-parent/checkout-app/src/test/java/edu/demo/app/CheckoutAppTest.java`:

```java
package edu.demo.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CheckoutAppTest {

    @Test
    void createsCheckoutReceipt() {
        assertEquals("CHECKOUT => SKU TEA: 2500 cents",
                CheckoutApp.receipt(" tea ", 2500));
    }

    @Test
    void createsZeroPriceReceipt() {
        assertEquals("CHECKOUT => SKU BOOK: 0 cents",
                CheckoutApp.receipt("book", 0));
    }
}
```

**Checkout app có 2 JUnit tests.**

## 13. Kịch bản build đúng thứ tự bằng Bash

Chạy tại thư mục `commerce-lab/` trên Linux/macOS. Cần Maven 3.9.x/JDK 17+ và quyền truy cập Maven Central hoặc mirror được phép.

Tạo **local Maven repository riêng** để chứng minh thứ tự install và không tác động cache người dùng:

```bash
REPO="$(mktemp -d)"

# 1. Publish version catalog vào chính local repository thử nghiệm.
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
    -f commerce-bom/pom.xml clean install

# 2. Build cả Reactor: parent + 3 module, rồi install artifacts.
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
    -f commerce-parent/pom.xml clean install

# 3. Consumer độc lập resolve BOM và libraries từ repository vừa install.
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
    -f standalone-client/pom.xml clean verify
```

Các lệnh ở bước 3 yêu cầu **các file của consumer được tạo theo phần 15–17**. Bash variables tồn tại trong cùng shell; nếu mở terminal khác, `$REPO` không còn tự có giá trị cũ.

Kỳ vọng theo thứ tự:

1. BOM `commerce-bom:1.0.0` được install như một POM artifact, **không tạo Java JAR**.
2. Parent `commerce-parent:1.0.0` đọc BOM từ repository vừa install; Reactor build `commerce-api` → `pricing-engine` → `checkout-app` theo dependencies thực.
3. `clean install` chạy các tests của modules, package JARs và install cả parent POM/modules.
4. Consumer ở một project **ngoài parent Reactor** đọc BOM và các published POM/JAR qua GAV, không dùng `target/classes` của sibling project.

**Không dùng `mvn deploy` lên production** trong bài tập. `install` chỉ lưu artifacts vào local repository của phiên thử nghiệm.

### 13.1. Nếu chỉ muốn kiểm modules mà chưa install

Sau khi BOM đã install, có thể:

```bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
    -f commerce-parent/pom.xml clean verify
```

Bước này đủ để kiểm Reactor compile/test/package nhưng **chưa install** API/engine parent POM để consumer chạy riêng. Khi kiểm độc lập, dùng `install` hoặc publish staging repository trước.

### 13.2. Tại sao build BOM trước?

Maven cần resolve BOM ở lúc **xây model** của parent, trước khi compiler/test chạy. BOM độc lập có thể được install ngay cả khi các JAR mà nó quản lý version chưa được tạo, vì dependencyManagement **không tải tất cả managed JARs** chỉ để import catalog.

Nếu chạy parent build khi BOM chưa có trong local/remote repo, Maven thường báo:

```text
Non-resolvable import POM: edu.demo:commerce-bom:pom:1.0.0
```

Đây là **model resolution error**, không phải lỗi Java import và cũng không được sửa bằng cách xóa unit tests. Cách đúng là publish BOM trước hoặc dùng một BOM version đã được tổ chức phát hành.

## 14. Chạy trên Windows PowerShell

Từ `commerce-lab/`, tạo isolated Maven local repository:

```powershell
$repo = Join-Path $env:TEMP (
    'commerce-lab-m2-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $repo | Out-Null

mvn -B -ntp "-Dmaven.repo.local=$repo" `
    -f commerce-bom/pom.xml clean install
if ($LASTEXITCODE -ne 0) {
    throw 'BOM install failed'
}

mvn -B -ntp "-Dmaven.repo.local=$repo" `
    -f commerce-parent/pom.xml clean install
if ($LASTEXITCODE -ne 0) {
    throw 'Parent Reactor install failed'
}

mvn -B -ntp "-Dmaven.repo.local=$repo" `
    -f standalone-client/pom.xml clean verify
if ($LASTEXITCODE -ne 0) {
    throw 'Independent consumer verify failed'
}
```

`Guid.NewGuid()` ngăn dùng lại một repo cũ chứa phiên bản thử nghiệm. **Đừng xóa** `~/.m2/repository` để reset bài tập; repo riêng tránh ảnh hưởng build của dự án khác. Nếu dùng Maven Wrapper, thay `mvn` bằng command wrapper phù hợp **nhất quán cho cả ba lệnh** và kiểm version thật.

PowerShell sử dụng backtick để nối dòng; backtick phải nằm cuối dòng, không có trailing spaces. Không dùng cú pháp Bash `\` để nối dòng trong PowerShell.

## 15. Consumer độc lập: import BOM nhưng không kế thừa parent

File `standalone-client/pom.xml` **không** chứa `<parent>edu.demo:commerce-parent...</parent>`. Consumer chỉ cần version catalog và dependencies của mình:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>standalone-client</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>edu.demo</groupId>
                <artifactId>commerce-bom</artifactId>
                <version>1.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>edu.demo</groupId>
            <artifactId>commerce-api</artifactId>
        </dependency>
        <dependency>
            <groupId>edu.demo</groupId>
            <artifactId>pricing-engine</artifactId>
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
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 15.1. Vì sao consumer cần tự pin plugin versions?

BOM quản lý **project dependencies**, không tự quản lý Maven Compiler, Surefire hay JAR Plugins. Consumer không kế thừa parent nên nó cần pin build plugins của riêng nó (hoặc kế thừa parent/organizational build policy khác).

Đây là **ranh giới thiết kế chủ đích**: một công ty có thể cho consumer dùng version catalog mà **không buộc họ dùng compiler level, test runner và plugin policy** của publisher.

### 15.2. Vì sao import BOM không tự “import parent POM” của consumer?

`<dependencyManagement>` với `type=pom`/`scope=import` lấy **managed dependency entries** từ BOM. Nó **không** biến BOM thành parent để kế thừa `<build><plugins>`, `<modules>` hay arbitrary project properties theo đúng nghĩa parent inheritance.

Tuy nhiên, JAR modules đã publish có thể khai báo **parent riêng của chúng** trong POM. Khi resolve `pricing-engine`, Maven vẫn có thể cần tải `commerce-parent:1.0.0` để xây effective dependency model của artifact đó. Đây là nhu cầu **transitive artifact metadata resolution**, không phải consumer đang trực tiếp kế thừa parent.

## 16. Java consumer: gọi các module đã install

File `standalone-client/src/main/java/edu/demo/client/ClientApp.java`:

```java
package edu.demo.client;

import edu.demo.api.Product;
import edu.demo.pricing.PriceFormatter;

public final class ClientApp {
    private ClientApp() {
    }

    public static String message() {
        return "CONSUMER => " + PriceFormatter.format(
                new Product(" sugar ", 175));
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Kết quả stdout **của riêng chương trình Java**:

```text
CONSUMER => SKU SUGAR: 175 cents
```

Vì consumer gọi cả `Product` và `PriceFormatter`, nó khai báo trực tiếp **cả API lẫn engine**. Commons Lang không được import trực tiếp trong consumer source, nên nó đến qua runtime dependency của `pricing-engine`.

## 17. JUnit tests của consumer độc lập

File `standalone-client/src/test/java/edu/demo/client/ClientAppTest.java`:

```java
package edu.demo.client;

import edu.demo.api.Product;
import edu.demo.pricing.PriceFormatter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ClientAppTest {

    @Test
    void consumesInstalledLibraries() {
        assertEquals("CONSUMER => SKU SUGAR: 175 cents",
                ClientApp.message());
    }

    @Test
    void usesPricingEngineWithDirectApi() {
        assertEquals("SKU PEN: 0 cents",
                PriceFormatter.format(new Product(" pen ", 0)));
    }
}
```

**Consumer có 2 tests.** Chúng được compile/run trong **một Maven project khác**. Nếu `pricing-engine` JAR không có trên repository hoặc published POM không có parent/dependency metadata hợp lệ, consumer có thể fail dù Reactor producer `verify` đã pass.

### 17.1. Đừng lẫn Maven Reactor test với consumer test

Có hai đợt độc lập:

```text
Producer: commerce-parent Reactor
  commerce-api:    3 tests
  pricing-engine:  2 tests
  checkout-app:    2 tests
  ------------------------
  Total:           7 tests

Consumer: standalone-client
  ClientAppTest:   2 tests
```

**Tổng cộng 9 tests trên hai Maven invocations**, không phải một Surefire report có 9 tests.

## 18. Chạy Java main với đúng Maven runtime classpath

Sau `clean install` của producer và `clean verify` của consumer, có thể chạy app bằng **Exec Maven Plugin** để không tự dựng classpath thiếu Commons Lang.

Bash — dùng cùng `$REPO`:

```bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
    -f commerce-parent/checkout-app/pom.xml \
    org.codehaus.mojo:exec-maven-plugin:3.3.0:java \
    -Dexec.mainClass=edu.demo.app.CheckoutApp \
    -Dexec.classpathScope=runtime
```

Dòng Java main in:

```text
CHECKOUT => SKU TEA: 2500 cents
```

Với consumer:

```bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
    -f standalone-client/pom.xml \
    org.codehaus.mojo:exec-maven-plugin:3.3.0:java \
    -Dexec.mainClass=edu.demo.client.ClientApp \
    -Dexec.classpathScope=runtime
```

Dòng Java main in:

```text
CONSUMER => SKU SUGAR: 175 cents
```

Maven console còn in `[INFO]` và `BUILD SUCCESS`; **không coi hai chuỗi trên là nguyên văn toàn bộ Maven stdout**. `exec.classpathScope=runtime` dùng project runtime dependency graph, phù hợp bài kiểm chứng Commons Lang được kéo bắc cầu.

PowerShell (với `$repo` còn trong shell):

```powershell
mvn -B -ntp "-Dmaven.repo.local=$repo" `
    -f commerce-parent/checkout-app/pom.xml `
    org.codehaus.mojo:exec-maven-plugin:3.3.0:java `
    -Dexec.mainClass=edu.demo.app.CheckoutApp `
    -Dexec.classpathScope=runtime
if ($LASTEXITCODE -ne 0) { throw 'Checkout run failed' }

mvn -B -ntp "-Dmaven.repo.local=$repo" `
    -f standalone-client/pom.xml `
    org.codehaus.mojo:exec-maven-plugin:3.3.0:java `
    -Dexec.mainClass=edu.demo.client.ClientApp `
    -Dexec.classpathScope=runtime
if ($LASTEXITCODE -ne 0) { throw 'Consumer run failed' }
```

Các lệnh `exec:java` là **smoke test sau build**, không thay cho JUnit tests và không biến JAR thường thành executable/fat JAR.

## 19. Kiểm chứng Maven Reactor và thứ tự build

Khi gọi:

```bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
    -f commerce-parent/pom.xml clean verify
```

Reactor cần xử lý:

```text
commerce-parent    (pom)
commerce-api       (jar)
pricing-engine     (jar; depends on commerce-api)
checkout-app       (jar; depends on api + engine)
```

Thứ tự giữa ba JAR modules là **bắt buộc bởi dependencies thực**, không chỉ bởi danh sách `<modules>`. Maven Reactor sorting xét project dependencies và các quan hệ đã được instantiated. `dependencyManagement`/`pluginManagement` **không tự tạo cạnh sắp xếp**.

### 19.1. Dùng `-pl` và `-am` đúng nghĩa

Muốn build app và những modules cần thiết:

```bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
    -f commerce-parent/pom.xml \
    -pl :checkout-app -am clean verify
```

- `-pl :checkout-app`: chọn project có artifactId tương ứng.
- `-am`: also make, build các Reactor project **phụ thuộc cần thiết**.
- Nếu thiếu `-am`, chỉ chọn app trong một local repo chưa có API/engine có thể fail dependency resolution.
- `-amd`: also make dependents, dùng để build các modules **phụ thuộc vào project được chọn**, là chiều ngược với `-am`.
- `-rf`: resume from module sau khi build fail, có thể cần bảo đảm những dependencies trước đó đã install/có trong reactor phù hợp.

**Không dùng `-pl` để “tăng tốc” nhưng bỏ qua các modules cần kiểm trong release QA**. Tối ưu local workflow và kiểm chứng cả hệ là hai mục tiêu khác nhau.

### 19.2. Root và module POM độc lập

Chạy lệnh từ root `commerce-parent` giúp Reactor biết đủ graph. Chạy:

```bash
mvn -f commerce-parent/pricing-engine/pom.xml verify
```

chỉ với module đó có thể cần `commerce-api` đã install trong Maven local repository; `relativePath` giúp tìm parent POM, nhưng không tự đưa toàn bộ sibling modules vào Reactor. Khi học multi-module, nên bắt đầu với `-f commerce-parent/pom.xml` và `-pl/-am` rõ ràng.

## 20. Xác minh phiên bản hiệu lực bằng Dependency Plugin

Sau khi BOM install, đọc dependency tree của engine bằng full plugin coordinates:

```bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
    -f commerce-parent/pricing-engine/pom.xml \
    org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Lệnh đọc tree cho một module độc lập có thể cần `commerce-api` đã được install; vì phần 13 chạy `clean install` producer trước, điều kiện này được đáp ứng.

Một phần tree mong đợi:

```text
edu.demo:pricing-engine:jar:1.0.0
+- edu.demo:commerce-api:jar:1.0.0:compile
+- org.apache.commons:commons-lang3:jar:3.14.0:compile
\- org.junit.jupiter:junit-jupiter:jar:5.10.2:test
   ... JUnit transitive test artifacts ...
```

Đây là **sơ đồ rút gọn**, không phải output Maven nguyên văn; trong thực tế còn JUnit Platform và các artifacts bắc cầu khác.

Kiểm `standalone-client`:

```bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
    -f standalone-client/pom.xml \
    org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Kỳ vọng thấy `commerce-api:1.0.0`, `pricing-engine:1.0.0`, Commons Lang 3.14.0 qua engine và JUnit 5.10.2 ở test scope.

### 20.1. Dùng effective POM để hiểu inheritance và import

```bash
mvn -B "-Dmaven.repo.local=$REPO" \
    -f commerce-parent/pricing-engine/pom.xml \
    org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
```

Ở effective POM của engine, kiểm:

- `groupId`/`version` inherited từ parent.
- `maven.compiler.release=17`.
- Plugin versions/config từ `pluginManagement`.
- `dependencyManagement` entries từ BOM.
- `commons-lang3`, `commerce-api` và JUnit đã có **versions được quản lý**.

`effective-pom` là **effective build model**, còn `dependency:tree` cho graph dependencies thực sự được resolve. Cả hai hữu ích; không thay thế nhau.

### 20.2. Khi local dependency mediation chọn version khác

Một BOM quản lý version, nhưng project vẫn có thể override version tường minh trong `<dependencies>` hoặc nhận một chính sách `dependencyManagement` khác có độ ưu tiên phù hợp. Khi nhiều BOM cùng quản lý một GAV, thứ tự import và declarations trực tiếp có thể ảnh hưởng version được chọn.

Để tránh khó đoán, **đừng import hai BOM có cùng GAV nhưng versions xung đột mà không có quy tắc rõ ràng**. Đọc effective POM và dependency tree của chính consumer, không chỉ tin rằng “BOM cuối được khai báo luôn thắng” hoặc “nearest wins giải quyết mọi trường hợp”.

## 21. BOM không quản lý plugins

Một hiểu nhầm thường gặp:

```xml
<dependencyManagement> ... import BOM ... </dependencyManagement>
```

sẽ **không pin Maven Compiler Plugin, Surefire Plugin hay JAR Plugin**. BOM là cơ chế của project dependencies. Versions/config của build plugins nên đặt trong:

```xml
<build>
    <pluginManagement>
        <plugins>
            <!-- compiler/surefire/other plugin versions -->
        </plugins>
    </pluginManagement>
</build>
```

của parent, hoặc trong `<build><plugins>` của project consumer riêng.

Với example, `commerce-parent` quản lý plugin versions, còn `commerce-bom` quản lý JUnit/Commons/API versions. Đó là **ranh giới trách nhiệm** giúp consumer lấy version catalog mà không bị buộc kế thừa cấu hình build của tác giả.

## 22. Scope compile, runtime, test và transitive dependencies

Trong lab:

| Dependency | Khai báo ở đâu? | Scope | Hệ quả |
| --- | --- | --- | --- |
| API | engine POM | compile mặc định | Engine compile/run được với Product |
| Commons Lang | engine POM | compile mặc định | Engine dùng StringUtils; consumer nhận bắc cầu |
| JUnit | từng module test và consumer | test | Chỉ phục vụ test, không truyền như app runtime |
| Engine | app/consumer POM | compile mặc định | Dùng PriceFormatter |
| API | app/consumer POM | compile mặc định | Dùng trực tiếp Product |

BOM có thể khai báo `<scope>` trong managed entry, nhưng **ví dụ này để từng module quyết định scope**; JUnit luôn ở test scope, Commons là compile khi engine cần nó.

Nếu consumer chỉ import BOM nhưng **không có `<dependency>`**, nó không nhận các JAR trong catalog. Nếu consumer có direct dependency tới engine nhưng code source cũng trực tiếp import Product, nên có direct API dependency như ví dụ — không dựa vào bắc cầu dù Maven hiện tại có thể vẫn compile.

### 22.1. Optional/provided và exclusions

Khi một dependency upstream đánh dấu `optional=true`, dùng scope `provided` hoặc có `<exclusions>`, downstream không mặc định nhận nó như một runtime transitive dependency bình thường. Nếu ai đó thay Commons Lang trong engine sang `provided`, unit tests ở engine vẫn có thể pass nhưng consumer runtime có thể thiếu `StringUtils`.

Vì vậy consumer smoke phải thực sự chạy `PriceFormatter.format`, không chỉ kiểm class/API có trong JAR.

## 23. Kiểm metadata sau install: POM và JAR là hai artifact khác nhau

Lệnh producer:

```bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
    -f commerce-parent/pom.xml clean install
```

tạo/cài artifacts dự kiến trong Maven local repo:

```text
edu/demo/commerce-parent/1.0.0/commerce-parent-1.0.0.pom
edu/demo/commerce-api/1.0.0/commerce-api-1.0.0.pom
edu/demo/commerce-api/1.0.0/commerce-api-1.0.0.jar
edu/demo/pricing-engine/1.0.0/pricing-engine-1.0.0.pom
edu/demo/pricing-engine/1.0.0/pricing-engine-1.0.0.jar
edu/demo/checkout-app/1.0.0/checkout-app-1.0.0.pom
edu/demo/checkout-app/1.0.0/checkout-app-1.0.0.jar
```

Và BOM cài ở bước trước:

```text
edu/demo/commerce-bom/1.0.0/commerce-bom-1.0.0.pom
```

Đây là **đường dẫn kiểu Maven repository** được mong đợi cho local install; repository thực có thể thêm metadata/checksum/tracking files.

**Không chỉ nhìn JAR:** published `pricing-engine.pom` có `<parent>` tới `commerce-parent`; consumer phải resolve được parent POM để xây dependency metadata. Parent lại import BOM, nên **cả BOM + parent POM phải có mặt ở repository được consumer phép đọc**.

Nếu chỉ copy `pricing-engine.jar` thủ công mà quên POM/parent/BOM, consumer có thể compile được một vài class nhưng không nhận Commons Lang transitive dependency đúng. Dùng Maven install/deploy qua project POM đầy đủ.

## 24. Kế hoạch deploy thật: thứ tự và bất biến

Ở production, `install` **không** phân phối artifact cho máy/CI khác. Cần `deploy` đến repository staging/production theo quyền/phê duyệt.

Một trình tự phát hành hợp lý cho cấu trúc lab:

```text
BOM 1.0.0
   |
   v
Deploy BOM POM đến repository staging
   |
   v
Parent + modules source build
   |
   v
Deploy parent POM, API JAR/POM, engine JAR/POM, app JAR/POM
   |
   v
Fresh consumer job dùng repository staging
   |
   v
Kiểm dependency graph, compile, tests, runtime smoke
   |
   v
Approve/promote đúng candidate đã QA
```

**Quan trọng:**

- BOM quản lý các module GAV 1.0.0, nhưng không nhất thiết tải chúng lúc chính BOM được build.
- Parent import BOM; CI producer cần repository có BOM version đó.
- Published child POMs có parent reference nên **parent POM cũng phải deploy**.
- Consumer đọc đủ BOM, parent, modules; thiếu một phần sẽ fail dù local developer có thể đã cache.
- Không redeploy đè release version `1.0.0` không đổi khi đã được phát hành như một immutable release.
- Với SNAPSHOT, dùng update policy/metadata phù hợp và kiểm artifact provenance; đừng coi cùng GAV là cùng byte.
- Credentials lưu trong `settings.xml`/CI secret store, không ghi vào POM public hoặc log.
- Consumer run trên **local repository mới** để tránh vô tình lấy artifact cũ từ cache.

### 24.1. Có nên phát hành BOM chung version với tất cả modules?

Ví dụ giữ `1.0.0` cho BOM và modules để dễ học. Hệ thống thật có thể dùng:

- **Release train:** BOM version tương ứng một tập versions đã được QA chung.
- **Independent module versions:** BOM `2026.11` quản lý API `2.4.1`, engine `3.1.0` và JUnit/Commons versions khác.
- **Enterprise platform BOM:** một BOM kết hợp nhiều thư viện được phê duyệt, với quy tắc nâng version và compatibility.

Không có quy tắc Maven bắt BOM GAV phải cùng version với mọi artifact mà nó quản lý. Version alignment là **quyết định release policy**.

## 25. CI pipeline: kiểm theo stage và giữ evidence

Một pipeline rút gọn:

```text
Checkout + chọn JDK17/Maven3.9.x
        |
        v
BOM validate/install hoặc resolve BOM release từ approved repo
        |
        v
Parent Reactor clean verify
        |
        v
Parent Reactor install/deploy staging
        |
        v
Consumer fresh-cache resolve BOM + parent + JARs
        |
        v
Consumer clean verify + runtime smoke
        |
        v
Dependency tree + published POM QA
        |
        v
Release approval
```

Nên lưu evidence:

| Artifact/report | Điều cần chứng minh |
| --- | --- |
| `commerce-api/target/surefire-reports/TEST-edu.demo.api.ProductTest.xml` | 3 tests chạy thật |
| `pricing-engine/target/surefire-reports/TEST-edu.demo.pricing.PriceFormatterTest.xml` | 2 tests chạy thật |
| `checkout-app/target/surefire-reports/TEST-edu.demo.app.CheckoutAppTest.xml` | 2 tests chạy thật |
| `standalone-client/target/surefire-reports/TEST-edu.demo.client.ClientAppTest.xml` | 2 tests chạy thật |
| Published BOM `.pom` | GAV/managed versions đúng |
| Published parent `.pom` | Parent metadata và BOM import resolve được |
| Published API/engine JAR+POM | Classpath/metadata đầy đủ |
| Consumer dependency tree | Chọn đúng versions và scopes |
| Runtime smoke stdout | Commons Lang transitive đủ cho engine |
| Maven/JDK version + commit | Khả năng tái hiện build |
| Repository/staging/checksum | Xác định candidate dùng để QA |

Mỗi Surefire XML thuộc **Maven project cụ thể**, không phải một file chung tổng 9 tests. Nếu module không có test hoặc Surefire bị skip, không đánh dấu toàn pipeline PASS chỉ vì `BUILD SUCCESS` ở một mục lẻ.

### 25.1. Nên dùng reactor khi nào, consumer độc lập khi nào?

- **Reactor build** xác minh dependencies giữa modules trong source checkout và kết quả compile/test/package.
- **Independent consumer** xác minh artifact/published POM trên repository và runtime classpath ngoài checkout.
- Hai phép kiểm **bổ sung cho nhau**, không thay nhau.

Một Reactor có thể cung cấp sibling class outputs mà chưa cần artifact đã deploy; vậy `mvn clean verify` xanh chưa chứng minh metadata/các artifacts publish đầy đủ.

## 26. Negative tests: sửa một biến và biết lỗi phải xảy ra

Các thử nghiệm sau chỉ thực hiện trên **copy/branch học tập**, không phá release thật.

### 26.1. Chưa install BOM mà chạy parent

Dùng một local Maven repo mới chưa có `commerce-bom:1.0.0`, rồi chạy parent. Kỳ vọng **Non-resolvable import POM** vì parent import BOM. Cách sửa: install/deploy BOM trước, không thêm BOM vào classpath test.

### 26.2. Chỉ có `<modules>`, bỏ dependency tới API

Trong `pricing-engine/pom.xml`, bỏ `<dependency>` tới `commerce-api` nhưng giữ import `Product` trong Java. Kỳ vọng `package edu.demo.api does not exist` hoặc cannot find symbol ở compile. **Aggregation không tự tạo classpath.**

### 26.3. Chỉ có dependencyManagement, bỏ dependency thật

Trong `pricing-engine/pom.xml`, bỏ entry Commons Lang khỏi `<dependencies>` nhưng BOM vẫn quản lý version. Compiler sẽ không thấy `StringUtils`. **Managed dependency không được tự thêm vào classpath.**

### 26.4. Thay JUnit sang compile scope

Nếu JUnit trong child không khai báo `<scope>test</scope>`, nó có thể theo compile mặc định, khiến unit testing library rơi vào graph không cần thiết và có thể lan sang downstream. Build có thể vẫn pass, nhưng đó là **QA về dependency hygiene**, không phải “đã đúng” chỉ vì pass.

### 26.5. Bỏ parent POM khi publish

Copy chỉ `pricing-engine-1.0.0.jar` và `.pom` sang một repository thử nghiệm mà không publish `commerce-parent`/BOM. Consumer từ fresh local repo có thể fail `Non-resolvable parent POM`. Đừng tạo POM tối giản để che vấn đề; publish đúng metadata chain hoặc thiết kế consumer POM/flatten strategy có kiểm chứng.

### 26.6. Consumer phụ thuộc engine nhưng chạy thiếu Commons Lang

Nếu published engine POM bị mất Commons Lang dependency hoặc scope sai, consumer có thể có `PriceFormatter.class` nhưng khi gọi method lại gặp `NoClassDefFoundError` cho `StringUtils`. Consumer runtime smoke là phép thử có giá trị.

### 26.7. App dùng `java -jar` nhưng JAR không executable

`checkout-app` packaging `jar` mặc định không gộp dependencies và không khai báo Main-Class. Lỗi khi chạy bằng `java -jar` không chứng minh multi-module thiết kế sai. Dùng Maven Exec Plugin hoặc thiết kế executable JAR riêng với manifests/runtime dependency management phù hợp.

### 26.8. Quên `-am` khi chỉ chọn checkout-app

Trong repo chưa install API/engine, `mvn -pl :checkout-app clean verify` có thể fail resolution vì chỉ chọn app. Bổ sung `-am` để Reactor build modules cần thiết; không sửa `groupId`/`version` ngẫu nhiên.

## 27. Lỗi thực tế và bảng chẩn đoán

| Triệu chứng | Nguyên nhân ưu tiên | Hướng xử lý |
| --- | --- | --- |
| `Non-resolvable import POM` | BOM chưa ở repository/mirror hoặc GAV sai | Install/publish BOM trước |
| `Non-resolvable parent POM` | Parent chưa publish/relativePath sai | Publish parent; kiểm POM chain |
| `No version for dependency` | BOM chưa import hoặc GAV không được quản lý | Effective POM và BOM version |
| Compiler không thấy `Product` | Thiếu direct API dependency | Thêm `<dependencies>` vào module đúng |
| Compiler không thấy `StringUtils` | Thiếu Commons Lang hoặc scope sai | Xem tree/scopes/BOM |
| Test compile thiếu JUnit | Test dependency thiếu | Khai báo JUnit test scope |
| `release version 17 not supported` | JDK Maven/compiler quá cũ | `mvn -version`, toolchains |
| JUnit tests chạy 0 | Surefire discovery/config sai | `failIfNoTests`, TEST XML |
| Tests module API PASS, app FAIL | Graph/version khác hoặc logic khác | Reactor summary, module reports |
| `-pl` không build API | Quên `-am` | Dùng `-am` hoặc install prerequisites |
| Consumer không resolve engine | Chưa install/deploy JAR+POM | Kiểm repository/GAV |
| Consumer nhận engine cũ | Local cache hoặc SNAPSHOT policy | Fresh repo, artifact provenance |
| Runtime thiếu Commons Lang | Engine POM không truyền transitive dependency | Published POM và tree |
| Parent có `<modules>` nhưng child không kế thừa | Child thiếu `<parent>` | Parent GAV trong child |
| BOM import không quản lý plugins | Nhầm dependencyManagement/pluginManagement | Pin plugins trong parent/consumer |
| Dùng `packaging=jar` cho parent | Parent aggregator không đúng packaging | Parent `packaging=pom` |
| Dùng JUnit scope compile trong mọi module | Scope policy quá rộng | JUnit test scope |
| Build IDE xanh, CI đỏ | IDE JDK/Maven/settings khác | Wrapper + `mvn -version`, effective POM |
| HTTP 401/403 repository | Server ID/credentials/quyền | Settings/CI secrets, không tắt TLS |
| `-o` fail ở repo mới | Artifacts chưa cache | Build online qua approved repo |
| BOM có version release nhưng modules SNAPSHOT | Catalog không khớp GAV | Đồng bộ version/release plan |
| Plugin version thay đổi ngầm | Parent không pin plugin | pluginManagement và effective POM |
| `dependency:tree` thiếu managed dependency | BOM chỉ quản lý, child không khai báo | Thêm actual dependency |
| `jar tf` thiếu class | Packaging/source roots khác | Compiler/JAR config, build logs |
| Consumer tests pass nhưng staged deploy fail | Consumer dùng local install cache | Fresh-cache staging test |
| Circular project dependency | API import engine hoặc module dependency vòng | Tách API domain, sửa graph |
| Multi-module build quá chậm | Build phạm vi lớn hơn cần thiết | `-pl/-am` cho dev, full verify cho release |

### 27.1. Thứ tự debug hiệu quả

1. Chạy đúng Maven/JDK, kiểm `mvn -version`.
2. Xác nhận BOM POM `edu.demo:commerce-bom:1.0.0` có sẵn.
3. Kiểm parent GAV và `<relativePath>`.
4. Kiểm `<modules>` đúng folders và các child `<parent>` đúng.
5. Đọc effective POM và dependency tree.
6. Kiểm dependency thật (API/engine/Commons/JUnit) và scopes.
7. Kiểm Reactor Summary, module bị lỗi và Surefire XML.
8. Kiểm POM/JAR installed, không chỉ project `target`.
9. Chạy independent consumer từ repository sạch khi kiểm release.
10. Ghi nguyên nhân và cách sửa có bằng chứng.

## 28. Mở rộng thiết kế cho production

### 28.1. Parent nhiều cấp

Tổ chức có thể có `corporate-build-parent` → `commerce-parent` → child modules. Mỗi tầng nên giữ trách nhiệm rõ: security/license/tools ở corporate parent, cấu hình Java/test/release ở commerce parent, cấu hình riêng trong module.

**Không dùng parent POM như một túi chứa toàn bộ dependencies mà mọi child phải nhận.** Ưu tiên `dependencyManagement` và quản lý plugin phù hợp.

### 28.2. BOM nhiều nền tảng

Một platform có thể import BOM từ Spring, Jakarta, JUnit hoặc BOM nội bộ. Phải hiểu các managed GAV xung đột và precedence, kiểm effective POM của từng module. Không dùng `LATEST` hay version ranges không kiểm soát trong BOM release catalog.

### 28.3. Multi-repository thay vì monorepo

Nếu API, engine và app nằm ở các repositories độc lập, **không có Reactor chung** để resolve từ source checkout. Khi đó mỗi artifact cần được publish đúng thứ tự và BOM cần trỏ versions đã thực sự tồn tại trên repository. `-am` không thể build các project ở một repository khác nếu chúng không thuộc Reactor graph hiện tại.

### 28.4. Java modules khác Maven modules

Maven `<module>` là cách aggregate project. Java Platform Module System dùng `module-info.java` với `requires`/`exports`; hai cơ chế này khác nhau. Project Maven multi-module **không bắt buộc** dùng JPMS.

### 28.5. Maven 4 và model 4.1.0

Bài demo dùng POM `modelVersion=4.0.0` để chạy được với Maven 3. Maven 4 có tính năng `<subprojects>`, parent/version inference và `packaging=bom` ở model `4.1.0`, nhưng chuyển source POM sang model mới có tác động tới **source build compatibility với Maven 3**. Đừng đổi đồng loạt nếu CI/IDE/release tooling còn dùng Maven 3. Một BOM consumer vẫn cần metadata tương thích với công cụ tiêu thụ.

## 29. Câu hỏi tự kiểm tra

**1. Vì sao cùng một project có thể vừa là parent vừa là aggregator?**

Vì inheritance và aggregation độc lập: root có `<modules>`, children có `<parent>`. Một POM `packaging=pom` có thể thực hiện cả hai vai trò.

**2. BOM import có tự kéo tất cả JAR mà BOM quản lý vào classpath không?**

Không. BOM chỉ quản lý metadata versions cho các dependencies được khai báo.

**3. Parent `pluginManagement` có tự chạy mọi plugin goals không?**

Không. Nó quản lý cấu hình/version. Default lifecycle plugins có thể nhận quản lý; custom goals cần plugin usage/execution rõ ràng.

**4. Vì sao engine POM thiếu `<version>` ở commerce-api mà vẫn build được?**

Do parent import BOM quản lý version `commerce-api:1.0.0`. Maven Reactor còn có API project cùng GAV để build đúng thứ tự.

**5. Nếu engine chỉ thêm `<module>commerce-api</module>` vào root mà bỏ `<dependency>` tới API thì sao?**

Engine không có classpath dependency tới API, nên Java compiler không tự tìm được `Product`.

**6. Tại sao cần install BOM trước parent?**

Vì parent phải resolve BOM import khi xây model. BOM trong bài được thiết kế độc lập và có thể publish trước ngay cả khi managed modules chưa được build.

**7. Consumer độc lập có phải kế thừa commerce-parent không?**

Không. Nó import BOM để quản lý versions và tự pin build plugins. Nhưng engine POM đã publish vẫn có thể tham chiếu commerce-parent trong metadata chain.

**8. Tại sao consumer khai báo trực tiếp API dù engine đã phụ thuộc API?**

Vì consumer source cũng import `Product` trực tiếp; khai báo direct dependency giúp classpath contract rõ, không dựa tình cờ vào transitive graph.

**9. Vì sao `mvn clean verify` ở Reactor chưa đủ chứng minh release metadata?**

Vì Reactor có thể resolve sibling artifacts từ source outputs, trong khi independent consumer cần JAR/POM/BOM/parent đã install/deploy.

**10. Có nên chỉ deploy JAR `pricing-engine` mà bỏ POM?**

Không. Maven cần POM để resolve transitive dependencies và parent/BOM metadata; chỉ có JAR có thể che lỗi runtime.

**11. Khi nào `-pl :checkout-app -am` hữu ích?**

Khi developer chỉ muốn build app cùng các Reactor dependencies cần thiết, thay vì full test tất cả modules không liên quan. Release gate vẫn cần kế hoạch kiểm toàn hệ.

**12. BOM và parent phải có cùng artifact version không?**

Không bắt buộc. Version alignment là quyết định release policy; chỉ cần quản lý/công bố versions chính xác và kiểm chúng tồn tại.

## 30. Checklist nghiệm thu bài thực hành

- [ ] Maven 3.9.x/JDK 17+ được xác nhận bằng `mvn -version`?
- [ ] Project có đúng folder/POM/source/test paths?
- [ ] `commerce-bom` là POM độc lập, `packaging=pom`?
- [ ] BOM quản lý versions API, engine, app, Commons Lang và JUnit?
- [ ] BOM không chứa child `<modules>` hoặc Java sources không cần?
- [ ] BOM được install trước parent?
- [ ] `commerce-parent` vừa là aggregator vừa làm parent?
- [ ] Root có `<modules>` API, engine, app?
- [ ] Mọi child có `<parent>` GAV và relativePath đúng?
- [ ] Parent import BOM với `<type>pom</type>` và `<scope>import</scope>`?
- [ ] Parent quản lý Java release 17 và plugin versions?
- [ ] Modules khai báo dependencies thật, không dựa vào BOM/aggregation để có classpath?
- [ ] API code chỉ dùng Java standard library?
- [ ] Engine dùng thật Commons Lang và có API direct dependency?
- [ ] App dùng API + engine và khai báo cả hai trực tiếp?
- [ ] JUnit chỉ ở test scope trong modules/consumer?
- [ ] Có 3 API, 2 engine, 2 app tests chạy và pass?
- [ ] Producer Reactor `clean install` thành công?
- [ ] Parent POM, BOM POM và các JAR/POM đã install đủ?
- [ ] Consumer độc lập không có parent commerce-parent?
- [ ] Consumer import BOM và resolve API/engine version không cần viết lại?
- [ ] Consumer 2 JUnit tests pass từ local repository đã install?
- [ ] Runtime smoke app in `CHECKOUT => SKU TEA: 2500 cents`?
- [ ] Runtime smoke consumer in `CONSUMER => SKU SUGAR: 175 cents`?
- [ ] `dependency:tree` hiển thị các artifact/scopes đúng?
- [ ] Effective POM cho thấy inheritance/plugin management/BOM import?
- [ ] `-pl/-am` được dùng đúng hướng khi build module?
- [ ] Đã tách local install và remote staging deployment?
- [ ] Đã kiểm consumer từ fresh cache nếu mục tiêu là release/provenance?
- [ ] Không ghi passwords/tokens hoặc repository path cá nhân vào POM?
- [ ] Không redeploy đè release GAV đã immutable?
- [ ] CI lưu Surefire XML, Maven/JDK versions, artifact metadata và approvals?
- [ ] Không tuyên bố đã chạy Maven nếu mới chỉ kiểm cú pháp/tài liệu?

**Kết luận:** thiết kế Maven multi-module tốt cần phân ranh giới **parent kế thừa cấu hình**, **BOM quản lý phiên bản** và **aggregator/Reactor tổ chức build**. Parent có thể đồng thời là aggregator nhưng BOM không phải parent của consumer. Với POM model 4.0.0, một BOM độc lập được install/publish trước, parent import BOM và quản lý plugins, còn modules khai báo những **dependencies thật** để Maven sắp xếp/compile. Để chứng minh thiết kế không chỉ hoạt động trong source checkout, hãy build/install parent + modules rồi kiểm một **consumer độc lập** sử dụng JAR/POM/BOM/parent từ repository, chạy tests và runtime smoke trên classpath đúng.

### Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html)
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Install Plugin — Usage](https://maven.apache.org/plugins/maven-install-plugin/usage.html)
- [Apache Maven — What's New in Maven 4](https://maven.apache.org/whatsnewinmaven4.html)
- [MojoHaus Exec Maven Plugin — exec:java](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html)
