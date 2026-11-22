# Build song song bằng -T và quan hệ với đồ thị reactor trong Maven

**`mvn -T` cho phép Maven 3 xây nhiều module độc lập cùng lúc, nhưng không làm mất thứ tự phụ thuộc giữa các module.** Maven Reactor xây dựng một đồ thị các project thuộc cùng build, xác định module nào phải hoàn thành trước module khác, rồi chỉ xếp lịch chạy đồng thời cho các module đã sẵn sàng. Số thread lớn không thể biến một chuỗi dependency nối tiếp thành song song; hiệu năng thực tế phụ thuộc **độ rộng đồ thị**, **đường găng (critical path)**, tính thread-safe của plugin, tải CPU/RAM/I/O, test forks và các tài nguyên chia sẻ.

Bài thuộc nhóm **Hiệu năng**, tập trung vào đúng mối quan hệ **tham số `-T` ↔ đồ thị phụ thuộc Reactor**. Ta sẽ:

1. Hiểu cú pháp `-T 4`, `-T 1C`, `-T 1.5C` và sự khác nhau với song song hóa test methods.
2. Đọc đồ thị Reactor, phân biệt các cạnh do `dependencies`/`parent`/plugin/extension tạo ra với thứ tự liệt kê `<modules>`.
3. Xây ví dụ Maven 3.9.x, Java 17 với **5 child modules** tạo hai nhánh độc lập rồi hợp nhất ở CLI; POM, Java source và JUnit tests đều có thể chạy.
4. So sánh `mvn -T 1` và `mvn -T 2`, quan sát build order, chạy Java app có stdout xác định.
5. Xử lý plugin `@threadSafe`, Surefire forks, shared ports/filesystem, fail-fast/fail-at-end, `-pl/-am/-amd/-rf`, cách benchmark thực tế và các rủi ro trong CI.

**Phạm vi phiên bản:** Nội dung và syntax lấy từ tài liệu **Parallel builds in Maven 3** và **Guide to Working with Multiple Modules (Maven 3)** của Apache. Maven 4 có hướng dẫn và cơ chế riêng, không tự suy rằng mọi chi tiết về scheduler hoặc CLI của Maven 3 áp dụng nguyên vẹn cho Maven 4.

## 1. Lệnh -T: số lượng thread dành cho Reactor

Các lệnh hợp lệ trong Maven 3.x:

```bash
mvn -B -T 1 clean verify
mvn -B -T 2 clean verify
mvn -B -T 4 clean verify
mvn -B -T 1C clean verify
mvn -B -T 1.5C clean verify
```

Ý nghĩa:

| Cú pháp | Cách hiểu | Khi nào phù hợp |
| --- | --- | --- |
| Không có `-T` | Maven reactor chạy theo builder tuần tự mặc định | Baseline, chẩn đoán race, các plugin chưa an toàn song song |
| `-T 1` | Yêu cầu tối đa một thread build module | Baseline tương tự chạy tuần tự; vẫn là yêu cầu cấu hình thread |
| `-T 2` | Tối đa hai module build tasks cùng chạy nếu đồ thị cho phép | Bắt đầu thử với CI 2 vCPU/ít RAM |
| `-T 4` | Tối đa bốn module build tasks cùng chạy nếu sẵn sàng | Reactor đủ nhiều nhánh độc lập |
| `-T 1C` | Hệ số một build thread trên mỗi CPU core Maven nhìn thấy | Cân nhắc dựa trên CPU/memory thực tế |
| `-T 1.5C` | Hệ số 1,5 thread trên mỗi CPU core Maven nhìn thấy | Có thể hữu ích khi tasks chờ I/O, nhưng dễ oversubscribe |

Tài liệu Apache ghi chính xác các ví dụ `mvn -T 4 clean install`, `mvn -T 1C clean install` và `mvn -T 1.5C clean install`. Chữ `C` là cách tính **theo số CPU cores mà Maven/Java thấy**, không phải ký hiệu một máy có “một core cố định”; trong container/CI, giới hạn cgroups, CPU quota và `availableProcessors` có thể ảnh hưởng số thread hiệu dụng.

**`-T` là tham số của Maven build session**, không phải Java compiler flag. Không khai `-T` trong `maven-compiler-plugin` và không kỳ vọng nó song song hóa một `javac` invocation hoặc JUnit methods trong cùng một module.

### 1.1. Khi nào -T không mang lại ích lợi?

- Project chỉ có **một module**: không có nhiều reactor projects để chạy đồng thời.
- Project có nhiều module nhưng một đường phụ thuộc dài: phần lớn thời gian chỉ một module đang sẵn sàng.
- Một module đơn lẻ chiếm gần hết thời gian, ví dụ integration test nặng cuối chuỗi.
- CPU/RAM, disk I/O, network repository hoặc test containers đã là điểm nghẽn.
- Plugin thiếu thread safety, tác vụ dùng tài nguyên chung hoặc test thường xuyên flake khi concurrency tăng.
- Tăng thread vượt **số module sẵn sàng** chỉ làm tăng contention/context switching, không sinh thêm công việc song song.

Một ví dụ sai: `-T 16` cho reactor có chuỗi `core → service → app` không tạo ra 16 modules concurrent; khi chỉ một node ready, 15 worker threads sẽ không có module thích hợp để làm.

## 2. Reactor là gì và tạo đồ thị phụ thuộc thế nào?

Maven **Reactor** thu thập các projects/modules của một build nhiều module, sắp xếp thứ tự phù hợp rồi thực thi lifecycle theo lựa chọn. Với xây song song, các module **chỉ có thể chạy sau khi các tiền nhiệm cần thiết đã hoàn thành theo scheduler**.

Một đồ thị hướng không chu trình (DAG) minh họa:

```text
                 parent (pom)
                    |
          +---------+----------+
          |                    |
       core                  catalog
          |                    |
       billing               audit
          |                    |
          +---------+----------+
                    |
                   cli
```

Hướng cạnh phụ thuộc là:

```text
core    -> billing -> cli
catalog -> audit   -> cli
parent  -> các child do parent POM nội bộ
```

Trong hai nhánh chính, `core` không phụ thuộc `catalog`, `billing` không phụ thuộc `audit`, nên **có thể** chạy đồng thời khi đã đủ input. `cli` phụ thuộc cả `billing` và `audit`, nên không được chạy trước khi **cả hai** đã thành công. Parent POM nằm trong reactor và các child tham chiếu parent đó; Maven có thể sắp parent trước các child vì quan hệ parent.

### 2.1. Reactor sorting dùng những quan hệ nào?

Theo hướng dẫn chính thức Apache Maven cho multi-module, những **tham chiếu đã được instantiated** sau có thể ảnh hưởng thứ tự:

1. Một Maven module có `<dependency>` thực sự tới module khác trong cùng reactor.
2. Project sử dụng một plugin được xây bởi module khác trong reactor.
3. Plugin có dependency tới module đang được xây trong reactor.
4. Project dùng một build extension do module reactor khác cung cấp.
5. Child có `<parent>` trỏ tới parent project cũng nằm trong reactor.
6. Thứ tự trong `<modules>` khi không có quan hệ khác quyết định thứ tự.

**Không phải mọi tên artifact nhắc trong POM đều tạo cạnh.** `dependencyManagement` và `pluginManagement` chỉ quản lý cấu hình và phiên bản; **không tạo thay đổi reactor sort order** nếu thiếu việc sử dụng/dependency thực sự. Điều này rất quan trọng khi kiểm graph.

### 2.2. Aggregation khác inheritance

Ví dụ:

```xml
<modules>
    <module>cli</module>
    <module>audit</module>
    <module>billing</module>
    <module>catalog</module>
    <module>core</module>
</modules>
```

`<modules>` chỉ **gom** các module và không phải một danh sách “build cli đầu tiên”. Các phụ thuộc project-to-project sẽ quyết định lại thứ tự. Một child khai `<parent>` để **kế thừa** POM cấu hình; chỉ ở cùng thư mục root trong `<modules>` không tự khiến child kế thừa parent.

Trong ví dụ hoàn chỉnh dưới đây, ta cố tình liệt kê modules gần như **ngược** thứ tự mong muốn để chứng minh Reactor thực thi theo graph thay vì copy danh sách `<modules>`.

### 2.3. Các module độc lập không nhất thiết chạy đúng một thứ tự cố định

Trong hai lần `-T 2`, scheduler có thể bắt đầu `core` trước `catalog` hoặc ngược lại; log từ các modules xen kẽ. Điều cần kiểm là **không bao giờ xử lý `billing` như một output hợp lệ trước khi input `core` đã sẵn sàng**; tương tự `audit` đợi `catalog`, và `cli` đợi hai nhánh.

Không suy ra từ một dòng log xen kẽ rằng Maven đã vi phạm dependency graph. Một module có thể in các dòng logging khác tại thời điểm task scheduling, repository access hoặc test child process; kiểm **reactor summary và task completion**, không chỉ thứ tự những dòng INFO.

## 3. Độ rộng đồ thị, critical path và giới hạn speedup

Hiệu năng `-T` phụ thuộc cấu trúc DAG. Hai khái niệm hữu ích:

- **Work (tổng công):** tổng thời gian CPU/elapsed của từng node nếu chạy tuần tự trong điều kiện tương đương.
- **Critical path (đường găng):** chuỗi quan hệ phụ thuộc có tổng độ dài lớn nhất. Dù có vô hạn threads, build không thể hoàn tất trước khi đường găng kết thúc.
- **Graph width/ready set:** số module đồng thời không bị chặn bởi tiền nhiệm ở một thời điểm. Nếu width là 2, đặt `-T 8` không làm 8 modules cùng hoạt động.

Ví dụ **minh họa toán học, không phải benchmark thực tế**:

| Module | Thời lượng giả định | Phụ thuộc trong reactor |
| --- | ---: | --- |
| parent | 1 giây | Không |
| core | 4 giây | parent |
| catalog | 3 giây | parent |
| billing | 6 giây | core |
| audit | 3 giây | catalog |
| cli | 2 giây | billing và audit |

Nếu làm tuần tự, tổng thời lượng lý tưởng là `1+4+3+6+3+2=19 giây`. Hai nhánh sau parent có độ dài `core + billing = 10 giây` và `catalog + audit = 6 giây`. Đường găng gồm `parent → core → billing → cli`, tổng `1+4+6+2=13 giây`. Với tài nguyên không giới hạn, không có overhead và đúng các thời gian giả định, wall time **không thể nhỏ hơn 13 giây**. Tỷ lệ speedup lý tưởng tối đa khoảng `19/13 ≈ 1,46×`, **không phải 4×** chỉ vì chọn `-T 4`.

Trong đời thực, plugin startup, disk/network I/O, CPU contention, GC, Surefire forks, scheduling overhead và cache có thể làm thời lượng khác. Với project lab rất nhỏ, build song song **có thể chậm hơn** build tuần tự; không hứa tăng tốc cố định.

### 3.1. Tối ưu graph không phải “càng nhiều module càng tốt”

Tách một module lớn thành hàng chục module chỉ để tăng số nút có thể làm tăng compile overhead, module metadata/dependency management và rủi ro build. Thiết kế hợp lý là **tách theo ranh giới chức năng và phụ thuộc thực**, giữ modules nhẹ phục vụ các nhánh downstream có thể build song song; tránh tạo dependency giả hoặc vòng phụ thuộc.

Đừng xóa một dependency thực chỉ để “mở khóa” scheduler; điều đó có thể khiến build dùng artifact cũ ở local repository, làm kết quả sai.

## 4. Lab Maven 3.9.x + Java 17: reactor hai nhánh hội tụ

Đây là một project **runnable từ mã nguồn**, không dùng Docker/database/service bên ngoài. Có **1 parent POM + 5 child modules**, hai module tests có tổng cộng **4 JUnit test methods** và một CLI chạy qua Maven Exec Plugin.

### 4.1. Cấu trúc file

```text
parallel-reactor-lab/
├── pom.xml
├── core/
│   ├── pom.xml
│   └── src/main/java/vn/example/core/Money.java
├── catalog/
│   ├── pom.xml
│   └── src/main/java/vn/example/catalog/TextLabel.java
├── billing/
│   ├── pom.xml
│   ├── src/main/java/vn/example/billing/Invoice.java
│   └── src/test/java/vn/example/billing/InvoiceTest.java
├── audit/
│   ├── pom.xml
│   ├── src/main/java/vn/example/audit/AuditEvent.java
│   └── src/test/java/vn/example/audit/AuditEventTest.java
└── cli/
    ├── pom.xml
    └── src/main/java/vn/example/cli/App.java
```

Các cạnh **do child `<dependencies>` thực sự khai**:

- `billing` dùng API từ `core`.
- `audit` dùng API từ `catalog`.
- `cli` dùng API từ cả `billing` và `audit`.
- `core` và `catalog` không phụ thuộc nhau.
- Tất cả child có cùng parent Maven POM.

Đây là ví dụ đủ rõ cho `-T 2`: sau khi xử lý parent, hai nhánh có thể chạy độc lập, rồi `cli` mới được build.

### 4.2. Root pom.xml: aggregation và plugin versions

File `parallel-reactor-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>parallel-reactor-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>cli</module>
        <module>audit</module>
        <module>billing</module>
        <module>catalog</module>
        <module>core</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.0</version>
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
                    <version>3.5.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-install-plugin</artifactId>
                    <version>3.2.0</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

**Chú ý ba điểm:**

1. `<modules>` cố tình liệt kê `cli` trước `core`. Maven vẫn phải sort `core` trước `billing` và `billing` trước `cli` nhờ declared dependencies.
2. `dependencyManagement` của JUnit **chỉ quản lý version/scope khi child dùng nó**, không tự thêm JUnit vào `core`/`catalog` hoặc tạo Reactor edge tới external JUnit.
3. `pluginManagement` ghim versions cho các plugins mà default lifecycle `jar` sử dụng; nó **không tạo một Maven module dependency edge**. `maven.compiler.release` được Compiler Plugin đọc để compile Java 17.

Root `packaging=pom` không có `src/main/java` và không phải một chương trình Java. Nó tồn tại để gom reactor và chia sẻ cấu hình theo inheritance.

### 4.3. core/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example</groupId>
        <artifactId>parallel-reactor-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>core</artifactId>
    <packaging>jar</packaging>
</project>
```

### 4.4. catalog/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example</groupId>
        <artifactId>parallel-reactor-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>catalog</artifactId>
    <packaging>jar</packaging>
</project>
```

Hai modules này chỉ có parent dependency, **không phụ thuộc nhau**; vì thế là hai candidate chạy song song sau parent.

### 4.5. billing/pom.xml: phụ thuộc core

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example</groupId>
        <artifactId>parallel-reactor-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>billing</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Ở đây `core` là dependency **thực**; Maven phải chờ `core` được build đủ để `billing` resolve nó. JUnit là external test dependency nên không phải node của Reactor nội bộ.

### 4.6. audit/pom.xml: phụ thuộc catalog

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example</groupId>
        <artifactId>parallel-reactor-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>audit</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>catalog</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`audit` có thể bắt đầu sau `catalog` và không cần đợi `billing` nếu đủ threads và resources. Nó cũng có JUnit dependency test scope với version lấy từ root dependencyManagement.

### 4.7. cli/pom.xml: cần cả billing và audit

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example</groupId>
        <artifactId>parallel-reactor-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>cli</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>billing</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>audit</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.7.0</version>
                <configuration>
                    <mainClass>vn.example.cli.App</mainClass>
                    <classpathScope>runtime</classpathScope>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Exec Maven Plugin chỉ được cấu hình ở `cli` để sau `install` có thể gọi `mvn -pl :cli exec:java`. **Không đưa `exec:java` trực tiếp vào lệnh chạy từ root cho mọi module**, vì các module `core/catalog/billing/audit` không có class `vn.example.cli.App` và không phải tất cả modules đều cần goal đó.

### 4.8. core: Money.java

File `core/src/main/java/vn/example/core/Money.java`:

```java
package vn.example.core;

/**
 * Simple money calculations in integer cents.
 */
public final class Money {
    private Money() {
    }

    public static long subtotal(long unitPriceCents, int quantity) {
        if (unitPriceCents < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                    "price and quantity must be nonnegative");
        }
        return Math.multiplyExact(unitPriceCents, (long) quantity);
    }
}
```

Công thức trả tiền bằng integer cents, tránh floating-point rounding. `Math.multiplyExact` bảo vệ tràn `long` bằng exception.

### 4.9. catalog: TextLabel.java

File `catalog/src/main/java/vn/example/catalog/TextLabel.java`:

```java
package vn.example.catalog;

import java.util.Locale;

public final class TextLabel {
    private TextLabel() {
    }

    public static String normalize(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("label must not be blank");
        }
        return value.strip().toUpperCase(Locale.ROOT);
    }
}
```

`strip`/`isBlank`/`Locale.ROOT` cho output ổn định trong Java 17. Class này không tham chiếu `Money`, củng cố hai nhánh độc lập.

### 4.10. billing: Invoice.java

File `billing/src/main/java/vn/example/billing/Invoice.java`:

```java
package vn.example.billing;

import vn.example.core.Money;

public final class Invoice {
    private Invoice() {
    }

    public static long total(long unitPriceCents, int quantity) {
        return Money.subtotal(unitPriceCents, quantity);
    }
}
```

Vì `Invoice` thực sự sử dụng `Money`, POM billing khai dependency core không phải phụ thuộc giả để điều chỉnh sort order.

### 4.11. audit: AuditEvent.java

File `audit/src/main/java/vn/example/audit/AuditEvent.java`:

```java
package vn.example.audit;

import vn.example.catalog.TextLabel;

public final class AuditEvent {
    private AuditEvent() {
    }

    public static String code(String label) {
        return TextLabel.normalize(label);
    }
}
```

Class này thực sự dùng `catalog` nhưng không biết đến `billing`.

### 4.12. cli: App.java và stdout

File `cli/src/main/java/vn/example/cli/App.java`:

```java
package vn.example.cli;

import vn.example.billing.Invoice;
import vn.example.audit.AuditEvent;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("totalCents=" + Invoice.total(150, 2));
        System.out.println("audit=" + AuditEvent.code(" sale "));
    }
}
```

**Stdout chính xác từ chương trình Java**:

```text
totalCents=300
audit=SALE
```

`cli` cần cả nhánh billing và audit để compile/chạy. Nếu Reactor xây `cli` trước `billing` hoặc `audit`, nó có thể lỗi missing classes. Maven sẽ sắp theo dependency graph nên lệnh full reactor hợp lệ không có vấn đề đó.

### 4.13. billing: InvoiceTest.java

File `billing/src/test/java/vn/example/billing/InvoiceTest.java`:

```java
package vn.example.billing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class InvoiceTest {

    @Test
    void computesTotal() {
        assertEquals(300L, Invoice.total(150, 2));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(IllegalArgumentException.class,
                () -> Invoice.total(-1, 2));
    }
}
```

JUnit Jupiter ở test scope của `billing`. Đây là **hai test methods**, không phải các Maven modules mới.

### 4.14. audit: AuditEventTest.java

File `audit/src/test/java/vn/example/audit/AuditEventTest.java`:

```java
package vn.example.audit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AuditEventTest {

    @Test
    void normalizesAuditCode() {
        assertEquals("SALE", AuditEvent.code(" sale "));
    }

    @Test
    void rejectsBlankAuditCode() {
        assertThrows(IllegalArgumentException.class,
                () -> AuditEvent.code(" "));
    }
}
```

Có **hai test methods** ở audit. Tổng hai test classes = **bốn JUnit test methods** trong ví dụ. Hai modules core/catalog không có tests; Surefire mặc định không fail build chỉ vì một module không có test class (miễn là policy không đổi `failIfNoTests`).

## 5. Chạy tuần tự và song song để kiểm đồ thị

### 5.1. Kiểm Java/Maven trước

```bash
java -version
mvn --version
```

Dùng **Maven 3.9.x và JDK 17+**. Khi dùng Java 17, các Java source ở phần 4 compile được. Lần đầu Maven cần có kết nối repository để resolve JUnit/Surefire/Compiler/Exec plugins. Các plugin versions được pin trong POM; không có service ngoài.

### 5.2. Baseline tuần tự

Từ root `parallel-reactor-lab`:

```bash
mvn -B -T 1 clean verify
```

Reactor phải build đủ parent và năm child modules. Quan sát Reactor Build Order: `core` đứng trước `billing`, `catalog` đứng trước `audit`, `billing` và `audit` đứng trước `cli`, dù danh sách `<modules>` trong root có `cli` đầu tiên.

Sau tests, Maven dự kiến có:

```text
billing/target/surefire-reports/TEST-vn.example.billing.InvoiceTest.xml
audit/target/surefire-reports/TEST-vn.example.audit.AuditEventTest.xml
cli/target/cli-1.0.0.jar
```

Tên file Surefire report có thể khác chút theo plugin và test provider; có thể đọc report XML để kiểm tổng cộng **4 executed tests**, zero failures/errors khi code chính xác.

### 5.3. Build song song với hai threads

```bash
mvn -B -T 2 clean verify
```

Theo đồ thị:

- parent xử lý trước các child cần nó;
- `core` và `catalog` có thể cùng lúc;
- khi `core` xong, `billing` có thể bắt đầu ngay cả nếu `catalog` chưa kết thúc, tùy số thread;
- khi `catalog` xong, `audit` có thể bắt đầu;
- `cli` chỉ chạy sau khi cả `billing` và `audit` đã đạt đủ điều kiện Reactor.

**Đây là các điều kiện thứ tự, không phải lịch cố định.** Log có thể xen kẽ. Với tốc độ máy và download/JVM startup khác nhau, không đảm bảo thấy từng cặp module bắt đầu chính xác cùng một mili-giây. Maven vẫn giữ dependency ordering và không chạy hai phiên bản cùng một module như hai node song song.

### 5.4. Thử -T 4 và -T 1C

```bash
mvn -B -T 4 clean verify
mvn -B -T 1C clean verify
```

Có thể cả hai không nhanh hơn `-T 2` với lab này vì sau parent, đồ thị chỉ có **hai nhánh độc lập** và `cli` là nút hợp nhất. Số thread lớn không vượt được critical path. Ngoài ra chính Maven startup/test fork overhead của project nhỏ có thể chiếm phần đáng kể.

Không có output thời gian chuẩn cho các lệnh trên; **phải đo trên máy thật** chứ không bịa “-T 4 nhanh hơn 50%”.

### 5.5. Chạy CLI sau khi install

Để Exec Plugin resolve các sibling module dependencies khi chỉ chọn `cli` trong một Maven invocation riêng, trước tiên cài đủ các modules vào local repository:

```bash
mvn -B -T 2 clean install
mvn -q -pl :cli exec:java
```

Lần hai chỉ chọn project `cli`; `exec:java` nhận mainClass cấu hình trong `cli/pom.xml` và classpath `runtime`, resolve `billing`/`audit` (và transitive core/catalog) từ artifacts đã `install`. **Stdout của chính App**, không tính Maven logs, là:

```text
totalCents=300
audit=SALE
```

Nếu chỉ chạy `mvn -pl :cli exec:java` **trước khi install** sibling artifacts, CLI có thể không resolve đúng reactor dependencies từ local repo. Khi đó dùng full reactor build/install hoặc chạy goal với project selection phù hợp, không copy từng JAR vào classpath thủ công.

### 5.6. Khi muốn chạy trực tiếp Java class?

Plain JAR `cli-1.0.0.jar` không chứa tất cả runtime dependencies và không mặc định có manifest `Main-Class`. Lệnh kiểu:

```bash
java -cp cli/target/cli-1.0.0.jar vn.example.cli.App
```

có thể fail vì thiếu `Invoice`, `AuditEvent` và transitive classes trên runtime classpath. Đây **không phải lỗi Reactor** mà là vấn đề packaging/runtime classpath. `mvn -pl :cli exec:java` sau install có ý nghĩa vì plugin tạo runtime classpath dựa trên Maven dependency model.

## 6. -T xây song song module, không mặc định song song method/test

Có **ba lớp concurrency** khác nhau:

| Lớp | Bộ điều khiển | Đơn vị chạy song song |
| --- | --- | --- |
| Reactor modules | Maven CLI `-T N` | Các Maven projects không bị dependency chặn |
| Test JVM forks | Maven Surefire/Failsafe `forkCount`/`reuseForks` | Các test JVM processes của module |
| Test methods/classes | JUnit Platform config, Surefire/TestNG tùy provider | Test classes hoặc methods trong một JVM/process |

`-T 2` **không tự bật** JUnit Jupiter parallel execution, cũng không có nghĩa mỗi module chỉ chạy tối đa một Java thread. Mỗi module có thể khởi chạy JVM fork cho Surefire, compiler JVM/service hoặc một external tool. Tổng mức CPU/RAM concurrency có thể lớn hơn giá trị `-T`.

### 6.1. forkCount và -T phải được tính cùng nhau

Ví dụ một module cấu hình Surefire:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <forkCount>2</forkCount>
        <reuseForks>true</reuseForks>
    </configuration>
</plugin>
```

Đây là **fragment thay thế cấu hình Surefire của một module**, không có trong POM chạy mặc định của lab. Nếu cùng lúc có nhiều Maven modules ở test phase, mỗi module có thể yêu cầu test fork(s), khiến tổng JVM processes/heap cao hơn trực giác “-T có 2 threads”.

Với test classes dùng DB/ports/files chung, concurrency có thể gây xung đột. Apache Surefire docs nhắc kỹ về `forkCount`, `reuseForks` và việc dùng `${surefire.forkNumber}` cho tên working directory/port khi phù hợp. Phải xem chính xác công thức forkNumber trong plugin docs nếu nhiều modules và forks, không tự hardcode một dãy số cố định.

### 6.2. Vì sao forkCount=0 đặc biệt rủi ro?

Tài liệu Surefire cảnh báo không nên kết hợp parallel Maven reactor builds với test thực thi không fork (`forkCount=0` trong nhiều cấu hình) vì các Maven builder threads cùng process có thể đụng **JVM system properties** và test environment toàn cục. Những biến dùng chung như `basedir`, system properties, locale/timezone hoặc logging configuration dễ race.

Thay vì bật `-T 8` rồi xóa forks để “tiết kiệm RAM”, hãy đánh giá isolation, number of JVMs và test runner setup. Nếu test thật sự cần chạy trong Maven JVM, nên giữ build tuần tự hoặc thiết kế lại test lifecycle có kiểm soát.

### 6.3. JUnit Jupiter parallel chưa chắc được bật bởi Surefire parallel

Với JUnit 5/6, parallel execution của tests được điều khiển qua **JUnit Platform configuration**; các thuộc tính Surefire `parallel` của JUnit4/TestNG không phải cấu hình thay thế tương đương cho mọi JUnit Platform version. Phần lớn dự án bắt đầu với JUnit 5 tests chạy tuần tự trong một module, nhưng vẫn có **concurrency giữa nhiều module** nếu `-T` được bật.

Khi cần song song hóa unit tests trong một module duy nhất, hãy tìm tài liệu **JUnit Jupiter Parallel Execution** và thiết kế tests thread-safe trước, không kỳ vọng `-T` giải quyết.

## 7. Plugin thread safety: @threadSafe không thể bỏ qua

Maven core hỗ trợ parallel reactor builds, nhưng một plugin/goal (**Mojo**) có thể dùng state toàn cục hoặc external tool không an toàn khi nhiều modules gọi đồng thời. Maven plugin descriptor có cờ **`threadSafe`** cho goal; khi session chạy parallel và execution plan có goals **không được đánh dấu thread-safe**, Maven 3 có thể in warning.

Warning thường có ý:

```text
Your build is requesting parallel execution, but this project
contains plugin(s) that have goals not marked as thread-safe.
```

Đây là **mô tả thông điệp**, không phải output đã thu được từ lab. Nếu thấy warning, **không bỏ qua chỉ vì build đã SUCCESS một lần**. Kiểm tên plugin/goal, plugin version và documentation. Nâng cấp tới version đã được xác nhận thread-safe, thử tuần tự và song song nhiều lần, kiểm outputs; nếu cần, tách goal không an toàn sang stage tuần tự.

### 7.1. @threadSafe chỉ là một phần của an toàn thực tế

Một plugin được đánh dấu threadSafe có thể vẫn gặp lỗi do **hệ thống bên ngoài** không cô lập:

- Hai modules dùng cùng file `../target/generated.xml` và cùng ghi.
- Một plugin có static mutable state/singleton không khóa.
- Hai JVM test cùng bind port `8080`.
- Integration tests dùng chung schema database và dọn dữ liệu lẫn nhau.
- Cùng một Docker container name hoặc working directory dùng cho nhiều module.
- Test runner ghi `/tmp/result.txt` với cùng filename.
- Local cache thư viện/plugin bên thứ ba bị ghi không an toàn.
- Generator tạo file dưới một thư mục shared thay vì `${project.build.directory}` riêng.

**Thread-safe code không đồng nghĩa tests được isolation.** Phải loại trừ những external resources singleton và kiểm side effects thực tế.

### 7.2. Giải pháp tốt hơn việc tắt -T toàn hệ thống

- Thiết kế plugin output theo **`${project.build.directory}`** của từng module.
- Dùng thư mục tạm độc lập, ví dụ JUnit `@TempDir` cho filesystem tests.
- Với integration tests, cấp port động hoặc port range riêng và service instance riêng.
- Dùng schema/database riêng cho từng module hoặc serial hóa integration stage phải dùng chung DB.
- Đặt **resource lock**/test isolation ở tầng test framework khi cần.
- Pin plugin versions và chú ý goals có thread-safety documented.
- Tránh thay đổi JVM/global system properties trong test chạy cạnh nhau.
- Nếu một goal bắt buộc tạo artifact tổng hợp duy nhất, chuyển sang **aggregator/final reporting stage** sau khi các modules hoàn tất, không để nhiều modules cùng overwrite file.

Nếu không thể bảo đảm safety, **`mvn -B clean verify` tuần tự là lựa chọn đúng**; hiệu năng không đáng để đánh đổi tính đúng đắn của artifacts.

## 8. Lệnh -pl, -am, -amd và -rf thay đổi đồ thị nào được xây

Tăng `-T` và thu hẹp **tập nodes Reactor** là hai cách khác nhau để tiết kiệm thời gian:

- `-pl` / `--projects`: chỉ chọn các modules được nêu.
- `-am` / `--also-make`: thêm các **reactor dependencies cần thiết** của modules đã chọn.
- `-amd` / `--also-make-dependents`: thêm các **modules phụ thuộc vào** modules đã chọn.
- `-rf` / `--resume-from`: tiếp tục build reactor từ một module sau lỗi hoặc theo thứ tự chọn.
- `-N` / `--non-recursive`: chỉ build POM/module hiện tại, không đi vào các modules; không hữu ích để đo parallel reactor.
- `-T`: quyết định tối đa số module được scheduler xây song song **trong tập đã chọn**, không chọn module nào.

### 8.1. Build CLI và các dependencies

```bash
mvn -B -T 2 -pl :cli -am clean verify
```

Chọn `cli`, thêm các reactor dependencies cần thiết: `billing` và `audit`; chúng lại cần `core`/`catalog`, cùng root parent. Vì vậy với lab này, build phải bao phủ phần lớn/toàn bộ đồ thị cần cho CLI. Đừng dùng `mvn -pl :cli clean verify` trên clean checkout rồi chèn JAR từ một build cũ ở local repo làm “giải pháp”.

### 8.2. Build module core và downstream dependents

```bash
mvn -B -T 2 -pl :core -amd verify
```

Dự kiến chọn `core` và dependents như `billing`, `cli`, **nhưng `cli` còn phụ thuộc nhánh `audit` không thuộc upstream `core`**. Nếu chưa có `audit`/`catalog` artifacts trong repository và chúng không nằm trong tập được chọn, lệnh có thể fail dependency resolution. Đây là ví dụ vì sao `-amd` không tự đồng nghĩa với `-am` hay “mọi module cần để build toàn project”.

Khi cần kiểm mọi module từ source sạch, chạy full reactor `mvn -T 2 clean verify` hoặc chọn target với `-am` đúng cách.

### 8.3. Resume sau một module fail

```bash
mvn -B -T 2 -rf :billing verify
```

`-rf` dựa trên Reactor order/scope của build, không tự rebuild toàn bộ các module upstream đã chạy thành công nếu bạn chỉ resume. Trong multi-module session trước đó, các artifacts upstream có thể chưa được `install`; một lượt resume mới có thể thiếu artifact ở local repo, nhất là nếu phase trước chưa tới `install` hoặc workspace bị clean.

Do vậy, với CI clean job, **full reactor clean verify lại thường đáng tin hơn**. Dùng resume khi bạn hiểu các upstream artifacts đã sẵn sàng và output của chúng còn hợp lệ. Lệnh resume không tự áp “sửa dependency graph”, cũng không nên copy/paste tùy tiện từ log khi working directory/settings khác.

## 9. Build thất bại và -ff / -fae / -fn khi chạy -T

Maven Reactor có các failure policy:

| Cờ | Ý nghĩa | Dùng trong CI |
| --- | --- | --- |
| `-ff` / `--fail-fast` | Dừng scheduling thêm công việc sớm khi module fail (mặc định) | Hợp lý cho fail-fast feedback |
| `-fae` / `--fail-at-end` | Tiếp tục các modules khác vẫn có thể build, báo lỗi cuối reactor | Hữu ích để thu nhiều lỗi độc lập trong một run |
| `-fn` / `--fail-never` | Maven tiếp tục bất chấp failure và có thể trả exit 0 | **Không dùng để làm release gate** |

Ví dụ:

```bash
mvn -B -T 2 -fae clean verify
```

Nếu `billing` fail, `cli` phụ thuộc billing sẽ không có artifact hợp lệ và bị skip hoặc không được xây thành công; **audit** và những modules độc lập có thể tiếp tục. Log Reactor Summary cuối có thể có `SUCCESS`, `FAILURE` và `SKIPPED` theo tình huống. `-fae` không làm dependencies “thành công giả” để dependent build được.

Với `-ff` khi đã có nhiều modules đang chạy, một số tác vụ đã khởi chạy có thể vẫn in logs/cleanup; không diễn giải rằng tất cả JVM đã dừng tức thì đúng ở dòng failure đầu tiên.

`-fn` nguy hiểm: exit code có thể là 0 dù có lỗi trong module; CI dễ đánh giá xanh giả. Không kết hợp `-fn` với deployment/release gates.

## 10. Chọn số thread dựa trên CPU, RAM và workload

Đừng áp dụng một con số `-T` cho mọi repository. Có ba loại workload:

1. **CPU-bound:** javac, code analysis, bytecode transforms; tăng threads quá số vCPU hiệu quả có thể làm contention.
2. **Memory-bound:** nhiều Surefire fork JVMs, compiler workers hoặc plugin ăn heap. `-T` cao dễ OOM dù CPU chưa đầy.
3. **I/O/network-bound:** dependency downloads, file generation, container startup, remote metadata. Một ít concurrency có thể che latency, nhưng quá nhiều threads dễ lock/contention hoặc gây 429 từ artifact repository.

**Quy tắc thực dụng:** bắt đầu tuần tự, sau đó thử `-T 2`, `-T 1C` và tối đa vừa đủ các nhánh graph. Quan sát elapsed time, CPU load, RSS/heap, test fork count, I/O wait, network, flaky test frequency và correctness output. Chỉ tăng khi số liệu chứng minh có lợi.

### 10.1. Benchmark trên Linux/macOS

```bash
time mvn -B -T 1 clean verify
time mvn -B -T 2 clean verify
time mvn -B -T 4 clean verify
```

Không so một lần duy nhất rồi kết luận. Chạy nhiều lượt trong điều kiện **cùng source, JDK, profiles, settings và warmed dependency cache**, tránh so một lượt phải download dependencies với một lượt đã có cache. Có thể đo median/p95 từ CI khi repo đủ lớn. Trong lúc benchmark, tránh các background jobs thay đổi đáng kể CPU/I/O và bảo đảm không chạy nhiều Maven builds **cùng ghi vào một target directory**.

### 10.2. Benchmark trên Windows PowerShell

```powershell
$serial = Measure-Command {
    mvn.cmd -B -T 1 clean verify | Out-Host
}
$parallel = Measure-Command {
    mvn.cmd -B -T 2 clean verify | Out-Host
}
"serial_seconds=" + $serial.TotalSeconds
"parallel_seconds=" + $parallel.TotalSeconds
```

Chú ý: PowerShell `Measure-Command` đo wall-clock time; redirect/Out-Host có overhead riêng, nên giữ cùng cách đo cho hai lệnh. Kết quả phụ thuộc máy; bài không cung cấp số đo giả định như output thực tế.

### 10.3. Định nghĩa tốc độ đo thực

```text
speedup = elapsed_serial / elapsed_parallel
efficiency = speedup / number_of_build_threads
```

Nếu `elapsed_parallel` lớn hơn `elapsed_serial`, speedup nhỏ hơn 1, không phải một thất bại của Maven scheduler; đó là dữ liệu nói cấu trúc graph/workload/tài nguyên hiện tại không hưởng lợi từ tham số `-T` đang thử.

Không đo mỗi tổng CPU time rồi gọi đó là “build nhanh hơn”; người dùng thường quan tâm **wall time** đến khi Reactor Summary hoàn tất và output đúng.

## 11. Cách đọc Maven logs khi chạy -T

Các logs thường có:

- Dòng xác nhận Maven đang dùng multi-threaded builder/number of threads.
- `Reactor Build Order` là **thứ tự topo hợp lệ**, không phải lịch start/completion của từng module chính xác.
- Những đoạn plugin logs có thể xuất hiện **xen kẽ** vì nhiều module thực thi đồng thời.
- `Reactor Summary` ở cuối cho biết mỗi module thành công/thất bại/skip và tổng build elapsed time.

Đừng lấy thứ tự `INFO` in ra làm graph đầy đủ, nhất là khi Surefire JVM forks và plugin logs ghi không đồng bộ. Để kiểm cạnh graph, **đọc effective module POMs và `dependency:tree`**; để tìm race, so sánh `-T 1` và `-T 2` trên cùng source, kiểm shared outputs/resources.

### 11.1. Plugin aggregator và tác vụ global

Một số goals có tính **aggregator** (thu thông tin toàn reactor hoặc sinh một artifact report tổng hợp). Chúng có thể yêu cầu phối hợp/serialize khác các per-module goals, và gọi chúng trong một phase ở nhiều modules có thể làm giảm concurrency hoặc sinh outputs sai. Thiết kế tổng hợp report nên rõ:

```text
Stage 1: -T 2 clean verify    # per-module compile/test/package
Stage 2: reporting goal      # aggregate/coverage/report với plugin thích hợp
Stage 3: deployment approval # nếu có chính sách phát hành
```

Không áp đặt stage 2 chung cho mọi plugin; phải đọc documentation từng goal về aggregator, threadSafe, bind phase và output location. Ví dụ JaCoCo report-aggregate hay một code generator toàn reactor không phải công việc “an toàn song song mặc định” chỉ vì build tool chấp nhận `-T`.

## 12. Tài nguyên chia sẻ: nguyên nhân phổ biến của flaky parallel builds

Dù Reactor sắp đúng dependencies, hai modules độc lập vẫn có thể tranh tài nguyên **không nằm trong Maven dependency graph**.

| Tài nguyên chung | Lỗi thường thấy | Biện pháp |
| --- | --- | --- |
| TCP port cố định `8080` | `BindException: Address already in use` | Port động hoặc port riêng module/fork |
| Một schema database `test` | Unique constraint/cleanup xóa dữ liệu nhau | Schema/database riêng hoặc test stage tuần tự |
| File `/tmp/report.json` | Ghi đè/truncated/corrupt output | `@TempDir`, module-scoped file path |
| Docker container name chung | Container name conflict/stale service | Unique namespace/job ID |
| Một thư mục generated sources ngoài modules | Plugin A xóa file B | Output dưới `${project.build.directory}` từng module |
| System properties trong non-forked tests | Race thay `user.dir`/`basedir` | Fork JVM, không sửa global props tùy tiện |
| Remote service rate limits | HTTP 429/timeouts | Hạn chế concurrency, mock/service quotas |
| Maven local repo shared giữa nhiều CI jobs | Lock/writes/corruption do tool ngoài Maven | CI isolation/cache strategy, tránh cùng target |
| Trình tạo timestamp/random resource | Build output không reproducible | Stable input/outputTimestamp và deterministic generator |
| Test data cố định | Assert thất thường theo lịch chạy | Isolated fixture, idempotent setup/teardown |

**Thêm `-T` không tạo các edge mới cho shared DB/port/file.** Maven chỉ hiểu các quan hệ đã khai trong reactor/POM. Nếu hai tests có dependency ngầm qua external resource, đó là lỗi thiết kế test hoặc pipeline; cần làm resource isolation rõ ràng hoặc serialize có chủ đích.

### 12.1. Kiểm độ ổn định chứ không chỉ một lần BUILD SUCCESS

Một repo trước khi bật parallel trên CI nên:

1. Chạy `mvn -B clean verify` tuần tự làm baseline.
2. Chạy `mvn -B -T 2 clean verify` nhiều lần trên clean target.
3. Đối chiếu số lượng tests, failures/errors/skipped trong Surefire/Failsafe XML.
4. Kiểm artifacts được tạo từ cùng source, không lẫn file của build trước.
5. Chạy test có stress/ports/database trong môi trường cô lập.
6. Nếu gặp race, thử `-T 1` để phân biệt issue concurrency với bug ổn định.
7. Đọc plugin warnings, nâng plugins khi thread-safe release khả dụng.
8. Chỉ áp dụng cho production/release pipelines sau khi chất lượng và performance được chứng minh.

## 13. Java 17 example: xác minh không có data race trong business code

Các class demo ở phần 4 đều sử dụng method **stateless** và không ghi file hay system property. Vì vậy bản thân business logic không tạo shared mutable state giữa modules; build còn phụ thuộc plugins và test toolchain, nhưng workload minh họa không chứa các external resource conflicts.

Có thể thử Java main nhiều lần sau `install`:

```bash
mvn -q -pl :cli exec:java
mvn -q -pl :cli exec:java
```

Cả hai lần dự kiến in:

```text
totalCents=300
audit=SALE
```

**Kết quả chương trình giống nhau không chứng minh JAR files byte-identical** giữa các lần build. Nếu cần reproducible build verification, so hashes của đúng artifacts đã tạo bằng `sha256sum`/`Get-FileHash` hoặc Maven Artifact Plugin compare với reference được giữ nguyên. Đây là bài hiệu năng + Reactor, không biến sự giống nhau của stdout thành kiểm chứng supply chain.

### 13.1. Một script kiểm artifact presence trong multi-module

Linux/macOS sau `mvn clean verify`:

```bash
for module in core catalog billing audit cli; do
    test -s "$module/target/$module-1.0.0.jar"
done
test -s "billing/target/surefire-reports/TEST-vn.example.billing.InvoiceTest.xml"
test -s "audit/target/surefire-reports/TEST-vn.example.audit.AuditEventTest.xml"
```

Đoạn trên dùng shell variable `$module`; khi lưu thành bài Markdown sẽ là `$module` chuẩn POSIX. Có thể thêm script XML parsing để xác nhận `tests=2` trong mỗi module, nhưng **không coi chỉ có file XML là bằng chứng tests pass** nếu build trả exit code thất bại.

Với Windows PowerShell:

```powershell
foreach ($module in @("core", "catalog", "billing", "audit", "cli")) {
    $file = "$module\target\$module-1.0.0.jar"
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Missing JAR: $file"
    }
}
"All five module JARs exist."
```

Các JAR files có thể chứa Maven metadata bên trong; source code không tạo fat executable JAR. Để chạy CLI từ Maven-managed runtime classpath, tiếp tục dùng `mvn -pl :cli exec:java` sau install như phần 5.

## 14. Tuning trong CI: không cho -T vượt tài nguyên runner

Một CI runner “8 CPU” có thể chia CPU quota cho nhiều jobs; mỗi Maven parallel module lại dùng Java compiler, Surefire process và một phần bộ nhớ. Do đó, số thread hiệu quả phụ thuộc **quota và cấu hình tests**, không chỉ tên máy hoặc số logical cores.

### 14.1. Cấu hình CI tối giản

Ví dụ **fragment shell** dành cho job Linux đã checkout source và cung cấp Maven/JDK 17:

```bash
#!/usr/bin/env sh
set -eu

java -version
mvn --version

mvn -B --no-transfer-progress -T 2 clean verify
```

Script không tự cài JDK/Maven, không login repository và không khởi chạy parallel jobs bên ngoài. Đối với project có Maven Wrapper, thay lệnh bằng `./mvnw -B --no-transfer-progress -T 2 clean verify` để sử dụng Maven distribution được pin. Maven Wrapper **không tự cài JDK**, nên runner vẫn phải đáp ứng toolchain.

### 14.2. Khi CI có nhiều jobs song song

Giả sử CI chạy **3 jobs Maven cùng lúc**, mỗi job dùng `-T 4`, và mỗi module có `forkCount=2`. Tổng số active JVM processes/CPU competitors có thể rất cao dù mỗi job chỉ thấy “4 threads”. Cần quản lý giới hạn ở **cả tầng CI jobs và Maven threads**, cộng với Surefire/Failsafe forks và Docker/DB services.

Đừng tự tính công thức “3 × 4 × 2 = 24 CPU cores bắt buộc”; forks chỉ là số tiến trình có thể cạnh tranh, CPU dùng tùy workload. Đo memory peak, OOMKills, garbage collection và tổng elapsed pipeline thay vì chỉ nhìn một job.

### 14.3. Khi nào nên tách stages?

- **Fast unit build:** `-T 2 clean verify` với unit tests stateless.
- **Integration test với resource chung:** chạy tuần tự hoặc cấp resource riêng từng module.
- **Aggregator reporting:** chạy sau modules theo goal/plugin semantics.
- **Release/signing/deploy:** chỉ chạy khi artifact completeness và policy kiểm được; không mặc định dùng `-T` nếu plugin/signature workflow không được kiểm an toàn.

Tách stages không có nghĩa mọi integration tests đều phải tuần tự; chúng vẫn có thể song song nếu được thiết kế isolation tốt. Nhưng đừng bật `-T` vì “CI nhanh hơn” rồi mặc nhiên coi data race là lỗi Maven core.

## 15. So sánh -T với song song hóa trong JUnit và CI matrix

Ví dụ có một module `integration-tests` chứa 500 test methods. `-T 8` chỉ thêm concurrency nếu **có các Maven modules độc lập khác** chạy cùng lúc; nó **không** chia 500 methods đó cho 8 threads trong một module. Muốn tăng tốc suite đơn module, dùng:

- JUnit Jupiter parallel configuration (khi tests an toàn).
- Surefire/Failsafe forks/parallel capabilities theo provider và plugin version.
- Chia test suites hợp lý theo modules hoặc CI matrix, nhưng không tạo dependencies giả.
- Test sharding/tooling có contract rõ về result collection.

CI matrix có thể chạy nhiều Maven commands trong nhiều processes/containers **độc lập**. Đó là concurrency ngoài Reactor; nếu chúng share workspace/target, local ports, DB schema hoặc remote repository, có thể race. Không nhầm với `-T` của một Maven process.

### 15.1. Maven Daemon (mvnd) không phải cú pháp -T

Apache Maven wiki nhắc **mvnd** như một giải pháp thay thế cho parallel builds, với daemon và cơ chế logging/scheduler riêng. Nếu tổ chức đã dùng mvnd, cần đánh giá cách cấu hình concurrency và support matrix của mvnd độc lập; **không suy rằng command `mvn -T 2` và mọi command mvnd có cùng kết quả/logging/performance**.

Trong bài, tất cả lệnh chính đều dành cho **Apache Maven 3.x CLI tiêu chuẩn**.

## 16. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Chọn `-T 16` với một Java module | Không có nhiều reactor nodes ready | Dùng compiler/test-specific tuning, hoặc giữ serial |
| Nghĩ `<modules>` sắp theo danh sách là cố định | Reactor sort theo instantiated edges | Khai dependencies thật, đọc Reactor Build Order |
| Chỉ khai `dependencyManagement` và mong có edge | DependencyManagement không instantiate dependency | Khai child `<dependencies>` thực sự |
| Cho `cli` build trước core vì root liệt kê cli đầu | POM list không thắng dependency graph | Thêm đúng module dependencies; Maven tự sort |
| Nghĩ `-T` tự chạy JUnit methods đồng thời | Reactor module concurrency khác test parallel | Cấu hình JUnit/Surefire đúng tầng |
| Bật `-T` với Surefire non-forked tests chia sẻ props | JVM global state dễ race | Fork tests, cô lập hoặc chạy serial |
| Bỏ qua plugin not thread-safe warning | Plugin có thể race dù build xanh một lần | Nâng plugin, audit goal threadSafe, stress tests |
| Hai modules ghi chung `target/report.xml` | Scheduler không biết file dependency ngầm | Chuyển output về module-local path |
| Test integration dùng cùng port 8080 | Parallel modules tranh cổng | Port động/unique module port |
| Copy JAR vào local repo thay vì khai dependency | Che dependency graph và khó tái lập | Khai module dependency trong POM |
| `-pl :core -amd` tưởng full graph | Downstream có thể cần upstream nhánh khác | Dùng full reactor hoặc `-pl :cli -am` |
| `-rf` sau clean mới mà thiếu upstream jars | Resume không tự build lại tất cả upstream | Dùng full reactor sạch nếu không chắc |
| Dùng `-fn` trong CI | Có thể exit 0 dù module thất bại | Dùng `-ff` hoặc `-fae`, kiểm exit code |
| Tăng threads theo logical CPU không xem RAM | OOM, test forks/GC contention | Benchmark trong quota thật |
| So cold-cache serial với warm-cache parallel | Dependency downloads làm số đo không công bằng | Warm cache hoặc đo có kiểm soát |
| Build song song 1 lần PASS rồi publish | Race/flaky tests có thể chỉ xảy ra ngẫu nhiên | Lặp nhiều lần, giữ baseline serial |
| Bật cache giữa builds chung target directory | Hai Maven processes có thể overwrite outputs | Cô lập workspace/output và cache theo policy |
| Tách module vô cớ để có “nhiều nodes” | Tăng complexity/startup overhead | Thiết kế modules theo domain boundary thực |

### 16.1. Quy trình debug một build chỉ fail khi -T

1. Ghi lại exact Maven/JDK/version, `-T`, modules và profiles đang chạy.
2. Tái hiện `mvn -B clean verify` tuần tự.
3. Thử `mvn -B -T 2 clean verify`, quan sát module nào lỗi/skip.
4. Xem warning plugin goals không marked threadSafe.
5. Đối chiếu declared inter-module dependencies: có thiếu cạnh nào cần thiết không?
6. Xác định shared file/port/database/container/system properties.
7. Kiểm Surefire/Failsafe forkCount và test parallel settings.
8. Dùng module-specific temp paths, ports và DB schemas.
9. So serial/parallel test reports, artifacts, screenshots/logs theo đúng commit.
10. Giảm concurrency hoặc tách integration/reporting stage nếu chưa an toàn.
11. Chạy lặp lại để bảo đảm không còn flaky race.
12. Chỉ áp `-T` lên CI/release sau khi cả correctness lẫn performance đạt yêu cầu.

## 17. Bài tập áp dụng và đáp án

**Bài 1.** Có 6 module nối thành chuỗi `a → b → c → d → e → f`. Chạy `-T 8` có làm 8 modules cùng build không?

**Đáp án:** Không. Mỗi module phải đợi module ngay trước nó; độ rộng graph về phần dependency chỉ là một node ready tại phần lớn thời gian.

**Bài 2.** Root liệt kê `cli` trước `core`, nhưng `cli` transitively phụ thuộc `core`. Module nào phải được xây trước?

**Đáp án:** `core` trước `billing` trước `cli`. Declared inter-module dependencies có ưu tiên trong reactor sorting so với thứ tự liệt kê `<modules>`.

**Bài 3.** Hai modules `core` và `catalog` không phụ thuộc nhau. `-T 2` có bắt buộc chúng start cùng thời điểm không?

**Đáp án:** Không. Chúng **được phép** song song, nhưng lịch thực tế phụ thuộc ready set, parent build, worker availability, I/O/JVM startup.

**Bài 4.** `-T 4` có tự bật `@Test` methods trong `InvoiceTest` chạy song song không?

**Đáp án:** Không. `-T` song song hóa Maven modules; test-level parallelism do Surefire/JUnit/TestNG tùy provider điều khiển.

**Bài 5.** Parent `dependencyManagement` khai `core` version nhưng child `billing` không khai dependency core. Reactor có tự thêm edge `core → billing` không?

**Đáp án:** Không. DependencyManagement chỉ quản lý, không tạo instantiated project dependency.

**Bài 6.** Chạy `mvn -pl :core -amd verify` trong một clean repo mà `cli` cần audit. Tại sao có thể fail?

**Đáp án:** `-amd` chọn downstream dependents, không đảm bảo kéo thêm nhánh `audit/catalog` làm dependencies của `cli` nếu chúng chưa có trong local repo.

**Bài 7.** Hai modules test cùng bind `localhost:8080` và chỉ fail khi `-T 2`. Có phải Maven Reactor sort sai?

**Đáp án:** Không nhất thiết. Chúng có thể độc lập theo POM nhưng tranh external port; dùng port/service isolation hoặc chạy stage phù hợp.

**Bài 8.** Plugin goal không marked threadSafe, nhưng `-T 2` PASS một lần. Có an toàn để release không?

**Đáp án:** Chưa. Cần kiểm plugin documentation/version, shared state, repeated tests và correctness of outputs.

**Bài 9.** `-T 1C` trên runner 8 vCPU có nghĩa chắc chắn 8 modules cùng chạy không?

**Đáp án:** Không. Nó đặt concurrency dựa trên CPU Maven nhìn thấy, còn số modules sẵn sàng và resource limits quyết định mức đồng thời thực.

**Bài 10.** `-fae` cho phép `cli` build thành công dù `billing` fail không?

**Đáp án:** Không. Dependents của failed module không thể được xem là thành công hợp lệ; các modules độc lập có thể tiếp tục và kết quả fail báo cuối.

**Bài 11.** Hai lần Maven build in cùng stdout `totalCents=300`; đã chứng minh outputs byte-identical chưa?

**Đáp án:** Chưa. Muốn kiểm reproducibility phải so bytes/digests/attached artifacts từ cùng inputs.

**Bài 12.** Bật nhiều thread mà elapsed time tăng. Phải làm gì?

**Đáp án:** Đo CPU, RAM, disk I/O, test forks, reactor width và critical path; giảm `-T` hoặc tối ưu dependencies/tests bottleneck thay vì tăng vô hạn.

## 18. Checklist quyết định bật -T trong dự án thật

- [ ] Xác nhận sử dụng Maven 3.x và hiểu syntax `-T N` / `-T nC`.
- [ ] Xem full Reactor modules, declared dependencies, parent/plugin/extension edges.
- [ ] Không dựa vào `dependencyManagement`/thứ tự `<modules>` như dependency edge.
- [ ] Xác định graph width và critical path; biết tại sao thread count không thể vượt graph constraints.
- [ ] Có một baseline `mvn -B clean verify` và cách đo elapsed time nhất quán.
- [ ] Thử từ `-T 2`; `-T 1C` chỉ khi CPU/RAM/I/O và test forks phù hợp.
- [ ] Không nhầm `-T` với Surefire/JUnit method parallelism.
- [ ] Kiểm warning `@threadSafe` và plugin versions/goal descriptors.
- [ ] Tests/resources có isolation: ports, DB, files, containers, JVM props.
- [ ] Multi-module POM đúng dependencies; CLI không cần artifacts cũ “lấp chỗ trống”.
- [ ] `-pl/-am/-amd/-rf` được dùng theo đúng scope và không làm CI kiểm thiếu modules.
- [ ] `-ff`/`-fae` policy rõ, không dùng `-fn` che build failures.
- [ ] Benchmark nhiều lượt, cùng source/JDK/settings/cache policy, ghi median và failure rate.
- [ ] Sau parallel build, test reports/artifacts được đối chiếu với baseline serial.
- [ ] Release/signing/aggregate reporting có kiểm tính tương thích `-T`.
- [ ] CI sizing xét cả concurrent jobs, Maven threads, Surefire forks và memory.
- [ ] Khi chưa an toàn, dùng serial build; ưu tiên correctness/reproducibility hơn tốc độ.
- [ ] Lệnh chạy demo tạo đúng `totalCents=300` và `audit=SALE`, bốn unit tests pass.

## 19. Tài liệu chính thức

- [Apache Maven — Parallel builds in Maven 3](https://cwiki.apache.org/confluence/display/MAVEN/Parallel+builds+in+Maven+3)
- [Apache Maven — Guide to Working with Multiple Modules (Maven 3)](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — CLI Options Reference](https://maven.apache.org/ref/3.9.9/maven-embedder/cli.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Surefire — Fork Options and Parallel Test Execution](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html)
- [Apache Maven Surefire — Test Goal Parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [MojoHaus Exec Maven Plugin — exec:java](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html)
- [JUnit 5 — Parallel Execution](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parallel-execution)
