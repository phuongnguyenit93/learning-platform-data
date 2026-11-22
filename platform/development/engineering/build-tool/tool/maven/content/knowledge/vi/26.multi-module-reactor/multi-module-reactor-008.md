# Dùng -amd để chọn những mô-đun phụ thuộc vào mô-đun đã chọn

## 1. Bài toán: kiểm tra tác động ngược trong Maven Reactor

Một repository Maven nhiều mô-đun có thể chứa thư viện nền tảng `shared-model` và những module đang dùng nó. Khi thay đổi public API của `shared-model`, unit test của chính module này có thể pass nhưng mã downstream vẫn lỗi compile hoặc có regression. Chạy toàn bộ repository luôn an toàn hơn về phạm vi, nhưng với một hệ thống lớn rất tốn thời gian.

Maven có tùy chọn **`-amd`** (*also make dependents*) để mở rộng một tập module đã chọn sang các module **đang phụ thuộc vào** chúng trong **Reactor** hiện tại, kể cả các quan hệ gián tiếp.

Ví dụ chạy từ root multi-module project:

```bash
mvn -B -pl :shared-model -amd test
```

Trong đó:

- `-pl :shared-model` chọn project có artifactId `shared-model` làm điểm xuất phát.
- `-amd` hoặc `--also-make-dependents` tìm **các project phụ thuộc vào shared-model**, trực tiếp hoặc qua những module khác.
- `test` chạy default lifecycle đến phase kiểm thử trên các project được chọn; không chỉ gọi một goal đơn lẻ.
- `-B` bật batch mode cho môi trường CI hoặc terminal không cần giao diện tương tác.

**Đừng nhầm:** `-amd` mở rộng theo chiều **consumer/dependent**. `-am` (*also make*) đi chiều ngược lại, thêm **dependencies/prerequisites** của project được chọn.

Bài học trình bày mô hình dependency graph, so sánh các lệnh Reactor, tình huống thiếu artifact upstream, khác biệt Maven 3/4, các lỗi CI và một dự án **Java 17 + JUnit Jupiter 5 gồm năm module** để kiểm chứng trên thực tế.

## 2. Reactor biết những project nào?

**Maven Reactor** là cơ chế của Maven core để thu thập, sắp xếp và build một tập Maven projects trong một lệnh đa mô-đun. Root aggregator POM thường khai báo:

```xml
<packaging>pom</packaging>
<modules>
    <module>shared-model</module>
    <module>price-engine</module>
    <module>checkout-cli</module>
    <module>catalog-cli</module>
    <module>standalone-cli</module>
</modules>
```

`<modules>` đưa các project vào phạm vi Reactor, **không tự thiết lập dependency giữa chúng**. Dependency nghiệp vụ nằm trong `<dependencies>` của từng POM con.

Reactor xét các quan hệ đã được khai báo thực sự khi sắp thứ tự project: project dependency vào module trong build, plugin declaration/plugin dependency hoặc build extension là một module, và quan hệ parent khi nằm trong Reactor. Nếu không có cạnh buộc thứ tự, Maven có thể dùng thứ tự khai báo trong `<modules>` để ổn định thứ tự. Riêng `dependencyManagement` và `pluginManagement` quản lý version/cấu hình nhưng **không tự thêm dependency instantiated** vào đồ thị.

Mục tiêu `-amd` là kiểm tra ảnh hưởng trong **Reactor đã được thu thập**. Nó không đọc `git diff`, không tìm tất cả Java classes có import, và không quét các consumer ở một repository khác.

### 2.1. Một đồ thị năm module

```text
                         shared-model
                          /        \
                         v          v
                 price-engine    catalog-cli
                       |
                       v
                  checkout-cli

standalone-cli      (không dùng các module ở trên)
```

Trong sơ đồ, **mũi tên đi từ dependency sang dependent**. Nói cách khác:

- `price-engine` phụ thuộc `shared-model`.
- `catalog-cli` phụ thuộc `shared-model`.
- `checkout-cli` phụ thuộc `price-engine`, nên bị ảnh hưởng gián tiếp nếu public API của shared-model thay đổi.
- `standalone-cli` không phụ thuộc nhánh trên.

Ở POM của price-engine, hướng dependency thực tế là:

```xml
<dependency>
    <groupId>demo.reactor</groupId>
    <artifactId>shared-model</artifactId>
    <version>1.0.0</version>
</dependency>
```

Còn checkout-cli khai báo:

```xml
<dependency>
    <groupId>demo.reactor</groupId>
    <artifactId>price-engine</artifactId>
    <version>1.0.0</version>
</dependency>
```

Bởi vậy, lệnh chọn shared-model bằng `-amd` sẽ mở rộng qua cả **price-engine → checkout-cli** và nhánh **catalog-cli**. Nó không đơn giản chỉ lấy module có dependency **trực tiếp**.

## 3. Ngữ nghĩa của -pl, -amd, -am và -rf

| Cờ | Dạng dài | Tác dụng |
| --- | --- | --- |
| `-pl` | `--projects` | Chọn một hoặc nhiều project làm tập đầu vào |
| **`-amd`** | **`--also-make-dependents`** | Mở rộng sang các project phụ thuộc vào tập đã chọn |
| `-am` | `--also-make` | Mở rộng sang project dependencies/prerequisites của tập đã chọn |
| `-rf` | `--resume-from` | Tiếp tục Reactor từ một project đã chỉ định, khác impact selection |
| `-N` | `--non-recursive` | Không thu thập các modules con theo cách recursive thông thường |
| `-fae` | `--fail-at-end` | Tiếp tục những project có thể build sau khi một project fail rồi báo lỗi cuối |

Ví dụ đọc nhanh:

```bash
mvn -pl :shared-model -amd test
mvn --projects :shared-model --also-make-dependents test
```

Hai câu lệnh tương đương về mục tiêu trong một Reactor/Maven version tương thích.

### 3.1. -pl có ba kiểu selector quan trọng

```bash
mvn -pl :shared-model -amd test
mvn -pl shared-model -amd test
mvn -pl demo.reactor:shared-model -amd test
```

- `:shared-model`: chọn theo artifactId trong Reactor, phù hợp khi artifactId duy nhất.
- `shared-model`: **đường dẫn module tương đối**, không phải artifactId được Maven suy diễn.
- `demo.reactor:shared-model`: chọn theo groupId:artifactId, giúp phân biệt module trùng artifactId.

Nếu module nằm tại `libs/shared-model`, path selector phải phù hợp đường dẫn từ root. Nếu project được truy cập qua `-f <root-pom>` hoặc chạy ở thư mục con, xác nhận phạm vi/đường dẫn selection thực tế; đừng đoán từ tên module.

### 3.2. Chọn nhiều seed

```bash
mvn -pl :shared-model,:price-engine -amd test
```

Đây là tập **hợp** các project downstream của hai seed; một project trùng đường không bị chạy hai lần chỉ vì có hai path dependency. Thực tế CI có thể đưa nhiều modules đã thay đổi vào `-pl`, sau đó dùng `-amd` để tính phạm vi consumer cần test.

### 3.3. Maven không tự tìm module bị sửa

`-amd` **không** phân tích Git changes. Nếu muốn chỉ test những consumers của module bị sửa, bạn phải tự xác định seed bằng Git/CI rồi truyền `-pl`. Lệnh:

```bash
mvn -amd test
```

không phải cách đáng tin cậy để chọn “module đã đổi” vì không chỉ rõ seed. Trong workflows dễ review, luôn ghi rõ `-pl` (hoặc tập project khác được xác định rõ).

## 4. So sánh hướng mở rộng của -am và -amd

Dùng graph của ví dụ:

```text
shared-model → price-engine → checkout-cli
shared-model → catalog-cli

standalone-cli (độc lập)
```

Các tập module nghiệp vụ mong đợi:

| Lệnh | Tập project theo quan hệ nghiệp vụ |
| --- | --- |
| `mvn -pl :shared-model test` | shared-model |
| `mvn -pl :shared-model -amd test` | shared-model, price-engine, checkout-cli, catalog-cli |
| `mvn -pl :price-engine -am test` | shared-model, price-engine |
| `mvn -pl :price-engine -amd test` | price-engine, checkout-cli |
| `mvn -pl :price-engine -am -amd test` | shared-model, price-engine, checkout-cli |
| `mvn -pl :catalog-cli -amd test` | catalog-cli |
| `mvn -pl :standalone-cli -amd test` | standalone-cli |

Đây là **các module ứng dụng trong dependency graph của demo**, không cam kết mọi log Maven có đúng một thứ tự duy nhất. Parent/aggregator, plugin edges và cách thu thập subprojects có thể ảnh hưởng kết quả thực tế tùy Maven version. **Đọc `Reactor Build Order` và `Reactor Summary` sau mỗi lệnh** để xác minh selection.

Dễ nhớ:

- `-am` hỏi: “**Tôi cần build thêm cái gì để module này chạy được?**”
- `-amd` hỏi: “**Những module nào cần module này và nên được kiểm thử khi nó thay đổi?**”

### 4.1. -amd không bảo đảm đủ upstream prerequisites

Giả sử gọi:

```bash
mvn -pl :price-engine -amd test
```

Tập module nghiệp vụ được chọn là price-engine và checkout-cli. Nhưng price-engine cần shared-model để compile. `-amd` không có nhiệm vụ thêm shared-model chỉ vì nó là upstream prerequisite. Nếu `demo.reactor:shared-model:1.0.0` chưa có trong repository mà Maven có thể truy cập, build có thể fail ở dependency resolution.

Hãy xét hai cách xử lý:

```bash
# Đưa prerequisite của seed vào Reactor
mvn -pl :price-engine -am -amd test

# Hoặc chuẩn bị artifacts trước, rồi mới chạy subset downstream
mvn -B clean install
mvn -pl :price-engine -amd test
```

Cách hai cần thận trọng vì **artifact được install có thể cũ hơn mã nguồn trong working tree**. Nếu regression test phải kiểm tra code mới, nên dùng Reactor tập hợp nguồn phù hợp từ cùng checkout/commit.

Ở graph phức tạp, khi kết hợp `-am` và `-amd`, kiểm tra thêm prerequisite của các dependent đã được mở rộng; đừng giả định mọi upstream nằm ngoài scope Reactor sẽ được tự tìm/build. Điều kiện cơ bản vẫn là **dependency graph khai báo đúng và tất cả artifacts cần thiết resolve được**.

## 5. Project runnable: cấu trúc tệp

Ta xây năm modules bằng Maven 3.9.x, JDK 17 và JUnit Jupiter 5.10.2.

```text
reactor-amd-demo/
├── pom.xml
├── shared-model/
│   ├── pom.xml
│   ├── src/main/java/demo/reactor/shared/Product.java
│   └── src/test/java/demo/reactor/shared/ProductTest.java
├── price-engine/
│   ├── pom.xml
│   ├── src/main/java/demo/reactor/price/PriceCalculator.java
│   └── src/test/java/demo/reactor/price/PriceCalculatorTest.java
├── checkout-cli/
│   ├── pom.xml
│   ├── src/main/java/demo/reactor/checkout/CheckoutCli.java
│   └── src/test/java/demo/reactor/checkout/CheckoutCliTest.java
├── catalog-cli/
│   ├── pom.xml
│   ├── src/main/java/demo/reactor/catalog/CatalogCli.java
│   └── src/test/java/demo/reactor/catalog/CatalogCliTest.java
└── standalone-cli/
    ├── pom.xml
    ├── src/main/java/demo/reactor/standalone/StandaloneCli.java
    └── src/test/java/demo/reactor/standalone/StandaloneCliTest.java
```

Các phiên bản pin phục vụ bài thực hành, không được hiểu là phiên bản Maven/plugin mới nhất tại thời điểm đọc. Cần quyền tải dependencies/plugins từ repository đã được cho phép hoặc có cache hợp lệ.

## 6. Root POM: aggregator và parent

Tệp `reactor-amd-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.reactor</groupId>
    <artifactId>reactor-amd-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>shared-model</module>
        <module>price-engine</module>
        <module>checkout-cli</module>
        <module>catalog-cli</module>
        <module>standalone-cli</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.10.2</version>
                <scope>test</scope>
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

Root này có **hai vai trò**:

1. **Aggregator**: liệt kê modules để Maven Reactor thu thập.
2. **Parent**: các child POM khai báo `<parent>` để thừa kế GAV và cấu hình plugin/dependency management.

Chỉ `<modules>` không có nghĩa modules là consumers của nhau. `dependencyManagement` quản lý version JUnit, nhưng từng child phải khai báo dependency `junit-jupiter` thật sự. `pluginManagement` quản lý các plugin versions; không tự gắn một arbitrary custom goal vào lifecycle, nhưng packaging=jar có default bindings để dùng Compiler/Surefire/JAR Plugin.

Trong ví dụ, root packaging=pom không có Java test. Vì vậy full Reactor có **năm module Java có test**, còn root không làm tăng số testcase.

## 7. Module shared-model

### 7.1. shared-model/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.reactor</groupId>
        <artifactId>reactor-amd-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>shared-model</artifactId>
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

Không có dependency nào vào các module nghiệp vụ khác. `shared-model` là upstream chung của graph.

### 7.2. Product.java

Tệp `shared-model/src/main/java/demo/reactor/shared/Product.java`:

```java
package demo.reactor.shared;

public record Product(String sku, int unitPriceCents) {
    public Product {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku required");
        }
        if (unitPriceCents < 0) {
            throw new IllegalArgumentException("price must be >= 0");
        }
    }
}
```

Java 17 hỗ trợ `record`, accessor `sku()`/`unitPriceCents()` và compact constructor. Hai accessor này là một phần public API; các module downstream có thể bị lỗi nếu chữ ký method thay đổi.

### 7.3. ProductTest.java

Tệp `shared-model/src/test/java/demo/reactor/shared/ProductTest.java`:

```java
package demo.reactor.shared;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ProductTest {
    @Test
    void retainsSkuAndPrice() {
        Product product = new Product("BOOK", 2500);
        assertEquals("BOOK", product.sku());
        assertEquals(2500, product.unitPriceCents());
    }

    @Test
    void rejectsNegativePrice() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> new Product("BOOK", -1));
        assertEquals("price must be >= 0", error.getMessage());
    }
}
```

Module shared-model có **2 JUnit tests**. Chúng đủ kiểm tra nội bộ một phần hành vi Product nhưng không chứng minh consumers vẫn tương thích.

## 8. Module price-engine phụ thuộc shared-model

### 8.1. price-engine/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.reactor</groupId>
        <artifactId>reactor-amd-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>price-engine</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>demo.reactor</groupId>
            <artifactId>shared-model</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Quan hệ `price-engine → shared-model` trong XML dependency khiến Maven phải build shared-model trước price-engine khi cả hai thuộc selected Reactor.

### 8.2. PriceCalculator.java

Tệp `price-engine/src/main/java/demo/reactor/price/PriceCalculator.java`:

```java
package demo.reactor.price;

import java.util.Objects;
import demo.reactor.shared.Product;

public final class PriceCalculator {
    private PriceCalculator() {
    }

    public static int subtotalCents(Product product, int quantity) {
        Objects.requireNonNull(product, "product");
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return Math.multiplyExact(product.unitPriceCents(), quantity);
    }

    public static String sampleSummary() {
        Product product = new Product("BOOK", 2500);
        int total = subtotalCents(product, 2);
        return product.sku() + " total: " + total + " cents";
    }
}
```

`Math.multiplyExact` nhận ra integer overflow; với ví dụ 2500 × 2 thì kết quả chính xác là 5000.

### 8.3. PriceCalculatorTest.java

Tệp `price-engine/src/test/java/demo/reactor/price/PriceCalculatorTest.java`:

```java
package demo.reactor.price;

import demo.reactor.shared.Product;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorTest {
    @Test
    void calculatesSubtotal() {
        assertEquals(5000,
            PriceCalculator.subtotalCents(new Product("BOOK", 2500), 2));
    }

    @Test
    void rejectsZeroQuantity() {
        IllegalArgumentException error = assertThrows(
            IllegalArgumentException.class,
            () -> PriceCalculator.subtotalCents(new Product("BOOK", 2500), 0));
        assertEquals("quantity must be positive", error.getMessage());
    }
}
```

Module price-engine có **2 tests**. Nếu Product thay đổi API, lỗi có thể xuất hiện ở compile hoặc test của price-engine.

## 9. Module checkout-cli phụ thuộc gián tiếp vào shared-model

### 9.1. checkout-cli/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.reactor</groupId>
        <artifactId>reactor-amd-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>checkout-cli</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>demo.reactor</groupId>
            <artifactId>price-engine</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Checkout-cli không trực tiếp import Product, chỉ gọi API của PriceCalculator; vì vậy nó không cần dependency direct vào shared-model. Nhưng **Reactor graph vẫn có đường phụ thuộc gián tiếp** checkout-cli → price-engine → shared-model.

### 9.2. CheckoutCli.java

Tệp `checkout-cli/src/main/java/demo/reactor/checkout/CheckoutCli.java`:

```java
package demo.reactor.checkout;

import demo.reactor.price.PriceCalculator;

public final class CheckoutCli {
    private CheckoutCli() {
    }

    public static String summary() {
        return PriceCalculator.sampleSummary();
    }

    public static void main(String[] args) {
        System.out.println(summary());
    }
}
```

### 9.3. CheckoutCliTest.java

Tệp `checkout-cli/src/test/java/demo/reactor/checkout/CheckoutCliTest.java`:

```java
package demo.reactor.checkout;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CheckoutCliTest {
    @Test
    void showsPriceFromUpstreamEngine() {
        assertEquals("BOOK total: 5000 cents", CheckoutCli.summary());
    }
}
```

Checkout-cli có **1 test**. Đường dependency gián tiếp không khiến Maven bỏ sót nó khi chọn downstream bằng `-amd`.

## 10. Module catalog-cli: nhánh downstream khác

### 10.1. catalog-cli/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.reactor</groupId>
        <artifactId>reactor-amd-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>catalog-cli</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>demo.reactor</groupId>
            <artifactId>shared-model</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 10.2. CatalogCli.java

Tệp `catalog-cli/src/main/java/demo/reactor/catalog/CatalogCli.java`:

```java
package demo.reactor.catalog;

import demo.reactor.shared.Product;

public final class CatalogCli {
    private CatalogCli() {
    }

    public static String summary() {
        Product product = new Product("BOOK", 2500);
        return "Product " + product.sku() + " costs "
                + product.unitPriceCents() + " cents";
    }

    public static void main(String[] args) {
        System.out.println(summary());
    }
}
```

### 10.3. CatalogCliTest.java

Tệp `catalog-cli/src/test/java/demo/reactor/catalog/CatalogCliTest.java`:

```java
package demo.reactor.catalog;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CatalogCliTest {
    @Test
    void readsSharedProductContract() {
        assertEquals("Product BOOK costs 2500 cents",
                     CatalogCli.summary());
    }
}
```

Catalog-cli có **1 test**; nó là downstream trực tiếp của shared-model nhưng **không phụ thuộc** price-engine. Vì vậy `-pl :price-engine -amd` không cần chọn catalog-cli.

## 11. Module standalone-cli: một nhánh không liên quan

### 11.1. standalone-cli/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.reactor</groupId>
        <artifactId>reactor-amd-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>standalone-cli</artifactId>
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

Module này là sibling của các module khác nhưng **không có dependency nghiệp vụ** nối tới shared-model. Việc cùng kế thừa root POM không có nghĩa nó là consumer của Java classes trong shared-model.

### 11.2. StandaloneCli.java

Tệp `standalone-cli/src/main/java/demo/reactor/standalone/StandaloneCli.java`:

```java
package demo.reactor.standalone;

public final class StandaloneCli {
    private StandaloneCli() {
    }

    public static String summary() {
        return "Independent module";
    }

    public static void main(String[] args) {
        System.out.println(summary());
    }
}
```

### 11.3. StandaloneCliTest.java

Tệp `standalone-cli/src/test/java/demo/reactor/standalone/StandaloneCliTest.java`:

```java
package demo.reactor.standalone;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class StandaloneCliTest {
    @Test
    void reportsIndependentModule() {
        assertEquals("Independent module", StandaloneCli.summary());
    }
}
```

Có **1 test** độc lập. Lệnh `-pl :shared-model -amd` nên bỏ qua module này trong downstream selection; full Reactor test vẫn bao gồm nó.

## 12. Chạy full Reactor build trước khi phân tích tập con

Từ **root `reactor-amd-demo`**:

```bash
mvn -version
mvn -B clean verify
```

Với JDK 17, Maven 3.9.x và các plugin/dependencies có thể tải được, **kết quả kỳ vọng**:

| Module | Unit tests |
| --- | ---: |
| shared-model | 2 |
| price-engine | 2 |
| checkout-cli | 1 |
| catalog-cli | 1 |
| standalone-cli | 1 |
| **Tổng năm module** | **7** |

Các module có thể có JAR tại:

```text
shared-model/target/shared-model-1.0.0.jar
price-engine/target/price-engine-1.0.0.jar
checkout-cli/target/checkout-cli-1.0.0.jar
catalog-cli/target/catalog-cli-1.0.0.jar
standalone-cli/target/standalone-cli-1.0.0.jar
```

Chúng là JAR thông thường, ví dụ không cấu hình `Main-Class`/fat JAR. Muốn chạy class CLI trực tiếp, truyền classpath.

Trên Linux/macOS:

```bash
java -cp standalone-cli/target/classes demo.reactor.standalone.StandaloneCli
java -cp "catalog-cli/target/classes:shared-model/target/classes" demo.reactor.catalog.CatalogCli
java -cp "checkout-cli/target/classes:price-engine/target/classes:shared-model/target/classes" demo.reactor.checkout.CheckoutCli
```

Stdout lần lượt của **ba lệnh Java**:

```text
Independent module
Product BOOK costs 2500 cents
BOOK total: 5000 cents
```

Trên Windows PowerShell, dùng dấu phân cách classpath `;` thay cho dấu `:`:

```powershell
java -cp "catalog-cli\target\classes;shared-model\target\classes" demo.reactor.catalog.CatalogCli
java -cp "checkout-cli\target\classes;price-engine\target\classes;shared-model\target\classes" demo.reactor.checkout.CheckoutCli
```

Nếu muốn dùng JAR file thay vì `target/classes`, phải bảo đảm đủ runtime JAR dependencies trên classpath; `java -jar` không phải lệnh phù hợp với những JAR không có Main-Class.

## 13. Bài thực hành chính: -pl :shared-model -amd test

Chạy từ root:

```bash
mvn -B -pl :shared-model -amd clean test
```

Theo graph demo, Maven chọn những **module nghiệp vụ**:

```text
shared-model    ← seed
price-engine    ← consumer trực tiếp
checkout-cli    ← consumer gián tiếp thông qua price-engine
catalog-cli     ← consumer trực tiếp
```

Module `standalone-cli` không thuộc downstream graph nên không cần chạy trong tác vụ này. Đây là một tập **đóng theo downstream dependency** của shared-model, không phải full Reactor.

Số test kỳ vọng:

```text
shared-model: 2
price-engine: 2
checkout-cli: 1
catalog-cli: 1
------------------
6 tests
```

Tập này có đầy đủ các module nghiệp vụ upstream cho những consumers được chọn trong ví dụ (shared-model ở gốc nhánh). Vì vậy nó có thể build từ source checkout sạch mà không phải install shared-model trước vào local repository, miễn dependencies/plugin bên ngoài có thể resolve.

### 13.1. Reactor Build Order và Reactor Summary

Quan sát log Maven:

```text
[INFO] Reactor Build Order:
...
[INFO] Reactor Summary ...
```

Đây là **các dòng đánh dấu cần tìm**, không phải output đầy đủ cố định. Điều bắt buộc trong dependency order:

- shared-model build trước price-engine và catalog-cli.
- price-engine build trước checkout-cli.
- catalog-cli và checkout-cli có thể nằm ở những vị trí khác nhau nếu không có quan hệ giữa chúng.

Một root parent/aggregator có thể tác động hiển thị theo Maven version và collection mode; đừng suy ra mọi dự án có cùng chính xác số dòng log. Kiểm chứng số test ở **Surefire reports của bốn modules nghiệp vụ**.

### 13.2. Kiểm chứng report của module thực sự chạy

Những đường dẫn quan trọng:

```text
shared-model/target/surefire-reports/TEST-*.xml
price-engine/target/surefire-reports/TEST-*.xml
checkout-cli/target/surefire-reports/TEST-*.xml
catalog-cli/target/surefire-reports/TEST-*.xml
```

Sau full build, `standalone-cli/target/surefire-reports` có thể còn file từ lượt trước. **Một file report tồn tại không chứng minh module đã được chọn trong lần build hiện tại.** Dùng Reactor Summary và các file được sinh mới, không cộng nhầm output stale.

## 14. So sánh các thí nghiệm -pl / -am / -amd

### 14.1. Chỉ seed

```bash
mvn -B -pl :shared-model test
```

Dự kiến **2 tests** của shared-model. Không chạy consumers vì thiếu `-amd`.

### 14.2. Chọn prerequisite của price-engine

```bash
mvn -B -pl :price-engine -am test
```

Dự kiến shared-model + price-engine, **4 tests** tổng. Checkout-cli là downstream của price-engine, không phải prerequisite của price-engine nên không do `-am` chọn.

### 14.3. Chọn downstream của price-engine

```bash
mvn -B -pl :price-engine -amd test
```

Dự kiến price-engine + checkout-cli, **3 tests** nếu shared-model dependency resolve được từ repository. Trên local Maven repository sạch, nếu chưa install shared-model, Maven có thể dừng vì:

```text
Could not resolve dependencies for project demo.reactor:price-engine:jar:1.0.0
... demo.reactor:shared-model:jar:1.0.0 ...
```

Đây là **phác họa lỗi**; Maven có thể hiển thị message khác theo version/setting. Nguyên nhân là `-amd` không có nhiệm vụ xây upstream shared-model.

### 14.4. Chọn cả prerequisite và downstream

```bash
mvn -B -pl :price-engine -am -amd clean test
```

Với graph demo, tập module nghiệp vụ mong đợi:

```text
shared-model   (prerequisite)
price-engine   (seed)
checkout-cli   (dependent)
```

Tổng số test tương ứng **2 + 2 + 1 = 5**. Catalog-cli là consumer của shared-model nhưng **không phải** consumer của price-engine; trong ví dụ này không có lý do downstream từ price-engine để chọn nó.

**Thận trọng:** ở một đồ thị phức tạp, những module dependent được `-amd` thêm có thể cần module prerequisite khác không liên quan trực tiếp đến seed. Kiểm tra log Reactor, dependency resolution và Maven version; không khẳng định mọi graph luôn được đóng đầy đủ chỉ nhờ kết hợp flags.

### 14.5. Chuẩn bị artifact local rồi chọn một nhánh

Nếu muốn thử `-pl :price-engine -amd test` một cách riêng lẻ sau checkout sạch, có thể cài các modules trước:

```bash
mvn -B clean install
mvn -B -pl :price-engine -amd test
```

Lúc này Maven có thể resolve shared-model từ local repository do `install` đã thực hiện. Tuy nhiên **không được nhầm test source mới với dependency version cũ**: local install từ hôm trước có thể có cùng tọa độ nhưng code khác. Khi review PR, ưu tiên build ở một Reactor thống nhất hoặc xác minh dependency bytes được lấy từ đúng commit.

### 14.6. Module không có dependents

```bash
mvn -B -pl :standalone-cli -amd test
```

Với graph demo, chỉ standalone-cli có **1 test**. `-amd` không tạo downstream nếu không có đường dependency trong Reactor.

## 15. -amd không chỉ có giá trị ở compile

Dùng `-amd` với phase `test` kiểm tra unit tests; với `verify`, Maven đi qua packaging và mọi goal đã gắn tới verify trong các module được chọn. Việc chọn phase phụ thuộc mục tiêu:

| Lệnh | Kiểm chứng |
| --- | --- |
| `mvn -pl :shared-model -amd compile` | Các module downstream còn compile được không? |
| `mvn -pl :shared-model -amd test` | Compile và unit tests theo lifecycle có pass không? |
| `mvn -pl :shared-model -amd verify` | Package và các bước QA đã cấu hình tới verify có pass không? |
| `mvn -pl :shared-model -amd -DskipTests package` | Build packaging nhưng **không chứng minh unit tests pass** |
| `mvn -fae -pl :shared-model -amd verify` | Cố tiếp tục những nhánh độc lập khi có failure, rồi báo lỗi cuối |

Không suy ra `verify` tự chạy integration tests nếu project chưa khai báo Failsafe/integration-test goals tương ứng. Và một direct goal như `mvn compiler:compile` không tương đương lifecycle phase `compile` vì các phase chuẩn bị không tự chạy đầy đủ.

## 16. Những điều dễ nhầm về dependency graph

### 16.1. dependencyManagement không phải actual dependency

Một parent có thể quản lý version của shared-model:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>demo.reactor</groupId>
            <artifactId>shared-model</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Nhưng nếu một child không có `<dependency>` tới shared-model trong `<dependencies>`, management **không tự biến child thành consumer**. Vì vậy `-amd` không được dùng để suy ra downstream từ những lời khai báo quản lý version thuần túy.

### 16.2. Parent và aggregator khác dependency classpath

- `<parent>`: thừa kế cấu hình POM, có thể ảnh hưởng thứ tự Reactor.
- `<modules>`: liệt kê project để thu thập vào Reactor.
- `<dependencies>`: thể hiện dependency artifact Java; Maven dùng để giải quyết compile/runtime classpath.

Một child kế thừa parent nhưng không tự import classes của các sibling. Nếu Java source cần code từ module khác, hãy khai báo GAV dependency thực sự thay vì chỉ đặt cả hai dưới root.

### 16.3. Dependency transitiveness không thay cho direct dependency khi source trực tiếp dùng một class

Nếu checkout-cli trực tiếp import `Product` từ shared-model, cách khai báo tốt là thêm **dependency trực tiếp** vào shared-model trong POM checkout-cli, thay vì dựa hoàn toàn vào transitiveness qua price-engine.

Điều này làm dependency graph thể hiện đúng coupling thật; khi price-engine thay dependency của nó, checkout-cli không vô tình mất class mà source đang dùng. Trong ví dụ, CheckoutCli chỉ gọi PriceCalculator nên khai báo direct vào price-engine là đủ.

### 16.4. Một module Maven không nằm trong Reactor hiện tại

Nếu consumer nằm ở repository khác, hoặc không được root aggregator thu thập, `-amd` không tìm thấy nó chỉ vì một dependency của consumer có cùng GAV với seed. Cần contract tests, integration tests hoặc CI cross-repository để kiểm tra ảnh hưởng ngoài Reactor.

## 17. Khác biệt Maven 3 và Maven 4

Ví dụ này nhắm **Maven 3.9.x**. Maven 4 có cập nhật về **subproject collection** và những tương tác `-pl`, `-N`, `-am`, `-amd` khi chạy từ một module con hoặc aggregator lồng nhau.

Hai ý nghĩa cơ bản vẫn giữ:

```text
-am  → also make dependencies
-amd → also make dependents
```

Tuy nhiên, khi nâng Maven 3 → Maven 4, không nên copy cứng Reactor Build Order của build cũ sang build mới. Hãy kiểm tra Maven version bằng `mvn -version`, đọc tài liệu tương ứng và chạy một build selection nhỏ trên CI để xác nhận kết quả, đặc biệt với nested aggregators và module path selectors.

Để dễ kiểm tra/giải thích ở Maven 3, lệnh trong bài chạy **từ root aggregator POM**. Nếu bạn đứng trong module con, scope Reactor mà Maven thu thập có thể hẹp hơn và `-amd` không tự tìm siblings/consumers bên ngoài scope hiện tại.

## 18. -rf, -N, -fae và -T không phải -amd

### 18.1. -rf = resume-from

```bash
mvn -B -rf :checkout-cli test
```

`-rf` là tiếp tục Reactor từ một vị trí, **không** là tìm các dependent của checkout-cli và **không** đảm bảo upstream đã build trong lần chạy này. Sau failure, nếu upstream artifact chưa được install hoặc không nằm trong selected set, resume có thể fail ở dependency resolution.

### 18.2. -N = non-recursive

```bash
mvn -N validate
```

Maven không đi xuống các modules con khi dùng non-recursive theo kiểu Maven 3. Nếu bạn làm hẹp phạm vi thu thập trước khi dùng `-amd`, có thể không còn downstream modules để chọn. Một câu lệnh Reactor nhiều module nên chạy từ root với scope thích hợp.

### 18.3. -fae = fail-at-end

```bash
mvn -B -fae -pl :shared-model -amd test
```

Khi price-engine fail compile/test, Maven có thể tiếp tục catalog-cli nếu nhánh đó không phụ thuộc price-engine, sau đó báo failure chung. Nhưng checkout-cli có thể bị **SKIPPED** do price-engine thất bại. `-fae` hữu ích để thấy nhiều lỗi ở các nhánh độc lập mà không che kết quả cuối.

### 18.4. -fn = fail-never

`-fn` có thể khiến Maven trả exit code 0 dù có module failure. Không dùng nó làm merge gate nếu CI chỉ dựa vào exit code. Muốn tiếp tục nhiều nhánh mà vẫn báo fail, thường phù hợp hơn với `-fae`.

### 18.5. -T = build song song

```bash
mvn -B -T 2 -pl :shared-model -amd test
```

Maven có thể chạy các module độc lập song song nhưng phải tôn trọng dependency graph; log có thể xen nhau. Khi debug module selection lần đầu, chạy tuần tự trước để dễ đối chiếu.

## 19. QA kết quả: Reactor Summary và Surefire XML

Bốn bước kiểm tra đáng tin:

1. **CLI thật**: ghi lệnh Maven, version và working directory.
2. **Reactor Build Order**: xem tập module được chọn và thứ tự build hợp lệ.
3. **Reactor Summary**: phân biệt `SUCCESS`, `FAILURE` và `SKIPPED`; một module bị skipped không được coi là đã test pass.
4. **Surefire reports**: đọc các file `TEST-*.xml` mới của đúng modules và đối chiếu test count, failure/error/skip.

Với lệnh `mvn -B -pl :shared-model -amd clean test`, kiểm tra các thư mục:

```text
shared-model/target/surefire-reports/
price-engine/target/surefire-reports/
checkout-cli/target/surefire-reports/
catalog-cli/target/surefire-reports/
```

Số test theo ví dụ là **6**, không phải 7. Module standalone-cli là module thứ năm nhưng không thuộc downstream closure.

**Bẫy stale reports:** nếu bạn đã chạy full build trước đó, file `standalone-cli/target/surefire-reports/TEST-*.xml` có thể vẫn nằm trên disk dù lần `-amd` mới không chạy standalone-cli. Đừng dùng sự tồn tại của file này làm bằng chứng module đã được chọn; dựa vào Reactor Summary và artifact/report của đúng run.

## 20. Thiết kế CI impact build

Quy trình tham khảo:

```text
1. Git diff/CI xác định các module bị sửa (bước riêng ngoài Maven)
2. Chuyển danh sách modules thành selector -pl
3. Dùng -amd để tìm downstream consumers trong Reactor
4. Dùng -am nếu cần các upstream prerequisites chưa sẵn có
5. Chạy test/verify theo test policy
6. Thu Reactor Summary và Surefire XML từ đúng modules
7. Nếu có failure, lưu reports/logs và báo rõ skipped modules
8. Chạy full build hoặc integration/contract tests khi thay đổi ngoài graph
```

Ví dụ khi sửa shared-model:

```bash
mvn -B -pl :shared-model -amd clean verify
```

Nó là **impact build dựa trên Maven dependency graph**, không phải “test toàn bộ mọi ứng dụng sử dụng API này qua HTTP”. Nếu thay parent POM được kế thừa bởi nhiều modules hoặc thay cấu hình CI/deployment ảnh hưởng toàn repository, một full Reactor build thường có giá trị hơn selection chỉ theo Java dependency edge.

### 20.1. Tránh phụ thuộc JAR cũ trong local repository

Nếu developer đã install `shared-model:1.0.0` hôm trước và hôm nay sửa class Product, lệnh:

```bash
mvn -B -pl :price-engine -amd test
```

có thể resolve `shared-model:1.0.0` **bản cũ** từ `~/.m2` thay vì code mới, vì shared-model không được chọn trong Reactor này. Test pass lúc ấy **không chứng minh** code đang sửa đã được dùng.

Đối với thay đổi shared-model, chọn chính shared-model làm seed với `-amd`, hoặc build prerequisites từ working tree nhất quán, rồi xác minh version/source/artifact thực tế.

### 20.2. Không làm rò test results từ build khác

CI cần thu report ngay cả khi Maven trả exit code khác 0, nhưng không gộp stale XML từ một job/run trước. Từng module nên có report directory riêng dưới `target/surefire-reports`. Nếu dùng `-fae`, các modules bị skipped có thể không sinh report mới, cần ghi chúng là **chưa được xác minh**.

### 20.3. Dependency graph không thể phát hiện mọi ảnh hưởng

Những quan hệ ngoài phạm vi Maven có thể gồm HTTP API, Kafka events, database schema, files JSON/YAML dùng chung, Docker image, external projects hoặc runtime reflection. Chúng không tự xuất hiện trong `-amd`. Dùng thêm schema/contract tests, staging smoke tests và full integration CI theo mức độ rủi ro.

## 21. Troubleshooting

| Dấu hiệu | Nguyên nhân có khả năng | Cách khắc phục |
| --- | --- | --- |
| `-amd` chỉ chọn seed | Không có downstream trong Reactor scope | Kiểm tra POM dependencies và root `<modules>` |
| Module consumer không được chọn | Không khai báo dependency thật hoặc module ngoài Reactor | Kiểm tra các POM và scope collection |
| Module cùng aggregator bị bỏ qua | Aggregation không sinh dependency giữa siblings | Chỉ thêm dependency nếu code thật sự cần |
| `-pl shared-model` không tìm thấy | Bare string được hiểu là path, không phải artifactId | Thử `-pl :shared-model` hoặc path đúng |
| ArtifactId không duy nhất | Nhiều modules trùng artifactId | Dùng groupId:artifactId hoặc directory selector |
| Build downstream không resolve shared-model | `-amd` không tự đưa toàn bộ upstream vào | Thêm `-am` hoặc chuẩn bị artifact đúng |
| Local PASS nhưng CI FAIL | Local repo có artifact stale, profile/JDK khác | Dùng clean Reactor build, pin môi trường |
| Biến API Product nhưng checkout-cli không được test | Checkout-cli không nằm trong Reactor scope hoặc graph khai báo sai | Kiểm tra transitive path và module collection |
| `dependencyManagement` có shared-model nhưng consumer không xuất hiện | Management không phải direct dependency | Khai báo `<dependency>` ở consumer |
| Lệnh gọi goal trực tiếp khiến compile/test thiếu resource | Không chạy lifecycle phases chuẩn bị | Dùng `mvn ... test`/`verify` |
| `-rf` bị hiểu như dependent selector | Resume-from khác also-make-dependents | Dùng `-pl -amd` cho impact test |
| `-N` làm mất downstream | Non-recursive thu hẹp Reactor | Chạy từ root không dùng `-N` |
| -fae có SKIPPED modules | Upstream build thất bại | Sửa upstream rồi chạy lại |
| CI trả success dù test fail | Dùng `-fn` hoặc flags skip test | Dùng default fail-fast hoặc `-fae` |
| Số test không khớp ví dụ | Đã chọn subset, skip flags, profile/test naming thay đổi | Đọc Reactor Summary + Surefire XML |
| Maven 4 chọn tập khác Maven 3 | Subproject collection/aggregation thay đổi | Dùng docs đúng version và xác minh CLI |
| Có circular dependency | Reactor không sắp thứ tự hợp lệ | Tách module API để loại vòng phụ thuộc |
| Lệnh -amd lâu như full build | Seed gần root và có nhiều dependent | Xem graph, chia module hợp lý, cân nhắc CI tầng |
| CI không phát hiện consumer ngoại repo | `-amd` chỉ biết Reactor hiện tại | Thêm contract/integration tests |

## 22. Câu hỏi tự kiểm tra

**1.** Với graph `A → B → C` (mũi tên dependency → consumer), `-pl :A -amd` chọn gì?

**Đáp án:** A, B và C; C là dependent gián tiếp của A.

**2.** Với graph trên, `-pl :B -am` chọn gì?

**Đáp án:** A và B; C là consumer, không phải prerequisite.

**3.** Vì sao `-pl :B -amd test` có thể fail trên local repo sạch?

**Đáp án:** B cần A nhưng `-amd` không tự thêm A như upstream; nếu A chưa có trong repository/selected Reactor, Maven không resolve được.

**4.** Vì sao cùng nằm trong root `<modules>` không khiến B là dependent của A?

**Đáp án:** Aggregation chỉ thu thập projects; không khai báo dependency giữa siblings.

**5.** `-amd` có tự chọn một HTTP service viết bằng Node.js ở repository khác không?

**Đáp án:** Không. Nó không phân tích network API contracts hoặc repositories ngoài Reactor.

**6.** Một module bị SKIPPED do upstream fail có thể tính là test pass không?

**Đáp án:** Không. Module chưa chạy đủ lifecycle/test; cần sửa nguyên nhân rồi chạy lại.

## 23. Checklist trước khi merge thay đổi module nền tảng

- [ ] Đã chọn module **bị thay đổi** làm seed bằng `-pl`?
- [ ] Selector đúng artifactId/GAV/path, không chọn nhầm module?
- [ ] Root Reactor hiện tại có thu thập tất cả consumers liên quan?
- [ ] Biết rõ `-amd` là downstream, `-am` là upstream?
- [ ] Nếu có nhiều seed, đã lấy hợp downstream closure phù hợp?
- [ ] Các upstream prerequisites có nằm trong selected set hoặc resolve từ artifact đúng source/version?
- [ ] Không nhầm `dependencyManagement`/`pluginManagement` với dependency thực?
- [ ] Dùng lifecycle phase `test`/`verify` thay vì direct goal thiếu bước chuẩn bị?
- [ ] Đã xem Reactor Build Order và Summary, không chỉ đọc một dòng `BUILD SUCCESS`?
- [ ] Surefire XML mới có số tests/failures/errors/skips đúng policy?
- [ ] Nếu dùng `-fae`, đã ghi rõ SKIPPED và FAILURE?
- [ ] Không dùng `-fn` hoặc `skipTests` để kết luận regression pass?
- [ ] Local repository không chứa dependency version stale che code mới?
- [ ] Maven 3/4, JDK và các plugin versions đã được cố định đủ để lặp lại?
- [ ] Những ảnh hưởng ngoài Maven graph có contract/integration tests phù hợp?
- [ ] Với thay đổi release quan trọng, đã xem xét full Reactor build/staging smoke test?

**Kết luận:** `-amd` / `--also-make-dependents` giúp Maven Reactor chọn những module **phụ thuộc trực tiếp hoặc gián tiếp** vào module được chọn qua `-pl`. Khi thay `shared-model`, ta có thể chạy regression của price-engine, checkout-cli và catalog-cli mà bỏ qua standalone-cli. Cần phân biệt `-amd` với `-am`, bảo đảm upstream artifacts đúng source/version và xác minh lựa chọn bằng Reactor Summary cùng test reports. Đó là cách dùng `-amd` để tăng tốc kiểm tra ảnh hưởng mà không tạo sự tự tin sai về chất lượng.

### Tài liệu tham khảo chính thức

- [Apache Maven — Guide to Working with Multiple Modules (Maven 3)](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Guide to Working with Multiple Subprojects in Maven 4](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Maven: The Complete Reference — Advanced Reactor Options](https://www.sonatype.com/maven-complete-reference/running-maven)
