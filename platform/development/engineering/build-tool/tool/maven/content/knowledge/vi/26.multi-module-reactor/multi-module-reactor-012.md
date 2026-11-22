# Phát hiện vòng phụ thuộc và tách ranh giới mô-đun trong Maven reactor

## 1. Vòng phụ thuộc là gì và tại sao reactor không thể build?

Trong dự án Maven nhiều mô-đun, mỗi module là một Maven project với `pom.xml`, tọa độ `groupId:artifactId:version` (GAV), dependencies và lifecycle riêng. **Reactor** thu thập các module, sắp xếp chúng theo những quan hệ cần thiết rồi thực hiện build.

Giả sử có hai module `billing-core` và `billing-adapter-memory`:

```text
billing-core
    |
    | cần lớp ở billing-adapter-memory
    v
billing-adapter-memory
    |
    | lại cần lớp ở billing-core
    +--------------------------> billing-core
```

Đây là **vòng phụ thuộc (dependency cycle)**: A cần B, đồng thời B lại cần A. Không có thứ tự build nào thỏa mãn đồng thời hai điều kiện “B phải build trước A” và “A phải build trước B”.

Một vòng dài hơn cũng gây vấn đề:

```text
A ---> B ---> C ---> D
^                  |
+------------------+
```

Trong các sơ đồ của bài, mũi tên `A -> B` có nghĩa **A phụ thuộc B**. Khi build, **B cần được sẵn sàng trước A**. Đường quay lại A là dấu hiệu cycle.

Ở Maven, vòng project dependencies trong reactor thường làm quá trình **lập đồ thị/sắp xếp project thất bại trước khi goal như `compile` hoặc `test` chạy**. Thông báo có thể gồm:

```text
[ERROR] The projects in the reactor contain a cyclic reference:
[ERROR] Edge between ... introduces to cycle in the graph ...
```

Đây là **mẫu thông báo rút gọn**, không phải log byte-for-byte. Tên module, cách định dạng `Vertex{...}` và đường đi của cycle tùy phiên bản Maven.

**Cần phân biệt** lỗi “reactor có vòng phụ thuộc” với lỗi thiếu một JAR ở repository, lỗi Java `ClassNotFoundException`, hay warning trùng version. Chúng có nguyên nhân và cách sửa khác nhau.

## 2. Reactor nhìn các quan hệ nào để sắp xếp module?

Theo Apache Maven, reactor sorting xét các quan hệ đã được khai báo và **thực sự sử dụng** trong cùng lượt build:

- Một project có **dependency** vào project khác đang nằm trong reactor.
- Một project khai báo **build plugin** mà plugin đó là project của cùng reactor.
- Một project có **plugin dependency** tới project khác trong reactor.
- Một project có **build extension** tới project khác trong reactor.
- Khi không có ràng buộc nào kể trên, thứ tự trong `<modules>` được dùng như một yếu tố quyết định thứ tự tương đối.

Lưu ý quan trọng: những entry chỉ nằm trong `<dependencyManagement>` hoặc `<pluginManagement>` **không tự sinh quan hệ reactor sorting**. Management quản lý version/configuration, còn dependency/plugin thật sự được sử dụng mới là quan hệ có hiệu lực.

Ví dụ aggregator:

```xml
<packaging>pom</packaging>
<modules>
    <module>billing-api</module>
    <module>billing-core</module>
    <module>billing-adapter-memory</module>
    <module>billing-cli</module>
</modules>
```

Đây là **đoạn root POM**, chưa phải POM đầy đủ. Nó liệt kê **các project tham gia reactor**, không nói rằng `billing-core` có thể import class của `billing-adapter-memory` hay ngược lại.

Quan hệ compile/runtime phải được khai báo trong `<dependencies>` của module sử dụng. Việc chỉ thay vị trí `<module>` trong XML không biến một đồ thị có cycle thành đồ thị hợp lệ.

### Aggregation, inheritance và dependency

| Cơ chế | Khai báo | Vai trò |
| --- | --- | --- |
| Aggregation | Root `<modules>` | Chọn các project cùng tham gia reactor |
| Inheritance | Child `<parent>` | Kế thừa groupId/version/properties/plugins/management |
| Project dependency | `<dependencies><dependency>...` | Đưa artifact vào graph/classpath theo scope |
| Dependency management | `<dependencyManagement>` | Quản lý version/scope mặc định, **không tự thêm dependency** |
| Plugin management | `<pluginManagement>` | Quản lý plugin version/config, **không tự kích hoạt execution mới** |

Một parent/aggregator có thể là cùng một POM, nhưng không nên cho **parent project phụ thuộc ngược vào những child modules** chỉ để lấy class của con: parent là nơi điều phối và quản lý cấu hình, không phải consumer của implementation.

## 3. Cách Maven báo lỗi và đọc vòng trong thông báo

Nếu có dependency cycle trực tiếp:

```text
billing-core -> billing-adapter-memory -> billing-core
```

Maven có thể dừng khi dựng reactor graph. Đầu tiên hãy **đọc đoạn lỗi đầu tiên mô tả cyclic reference**, không chỉ dòng `BUILD FAILURE` phía cuối.

Đặt câu hỏi:
1. Những tọa độ GAV nào xuất hiện trên đoạn cycle?
2. Quan hệ giữa từng cặp phát sinh từ `<dependency>`, build plugin, plugin dependency hay extension?
3. POM nào thực sự định nghĩa quan hệ đó — POM module, parent inheritance, profile đang bật hoặc effective model?
4. Đây là cycle **2 chiều** hay một vòng **3+ module**?
5. Có dependency vừa được thêm để dùng một utility/interface nhỏ từ sibling module không?

Ví dụ trừu tượng:

```text
[ERROR] The projects in the reactor contain a cyclic reference:
[ERROR] billing-core:1.0.0 -> billing-adapter-memory:1.0.0
[ERROR] billing-adapter-memory:1.0.0 -> billing-core:1.0.0
```

Các dòng trên là **đồ thị minh họa do bài học tự viết**, không phải Maven luôn in chính xác định dạng đó. Một số bản Maven in `Edge between ... introduces to cycle in the graph ...` kèm đầy đủ tọa độ.

**Không đoán cycle chỉ dựa vào tên package.** Phải truy được **các cạnh dependency có thật**; class imports giúp tìm nguyên nhân nghiệp vụ nhưng không thay thế việc đọc POM/effective POM.

## 4. Phân biệt loại vòng: Maven module graph, Java code và runtime

### 4.1. Vòng ở cấp Maven project

```text
core/pom.xml:     dependency adapter
adapter/pom.xml:  dependency core
```

Maven cần cả hai artifact trước nhau, nên không thể chọn thứ tự build trong một reactor. Đây là lỗi trọng tâm của bài.

### 4.2. Vòng ở cấp package/class bên trong **một** module

Hai Java classes ở cùng một Maven module có thể gọi lẫn nhau. Compiler có thể compile chúng cùng lượt nếu mã hợp lệ; Maven **reactor sorting không tự coi đó là vòng giữa modules**. Tuy nhiên, coupling vẫn có thể khó bảo trì hoặc gây recursion vô hạn ở runtime.

### 4.3. Vòng gọi hàm lúc chạy

Một service gọi callback, callback quay lại service không nhất thiết là Maven dependency cycle nếu code dùng interface trong module độc lập. Nhưng vòng gọi runtime không có điều kiện dừng vẫn có thể gây `StackOverflowError`.

### 4.4. Vòng transitive dependency từ repository

Một artifact có thể phụ thuộc vào artifact khác theo nhiều tầng. Maven dependency mediation chọn version gần nhất trong nhiều tình huống, **nhưng mediation không phải thuật toán giải quyết một cycle cấu trúc tùy ý**. Nếu graph thật có vòng hoặc POM invalid, cần tìm và sửa quan hệ đúng.

### 4.5. Vòng POM parent/BOM import

Parent resolution và BOM import trong `<dependencyManagement>` là cơ chế model riêng. Một POM cố import BOM được sinh từ submodule mà nó đang làm parent, hoặc các parent khai báo vòng, có thể gây lỗi resolution/model trước cả reactor build. Không gọi mọi lỗi POM/BOM là “project dependency cycle”; cần đọc thông báo thực.

## 5. Tình huống trước khi sửa: core phụ thuộc implementation và implementation lại phụ thuộc core

Giả sử hệ thống thanh toán có:
- `billing-core`: xử lý nghiệp vụ checkout;
- `billing-adapter-memory`: implementation cổng thanh toán trong bộ nhớ phục vụ local/demo.

Một người lập trình viết `CheckoutService` trong **core** và trực tiếp tạo class của **adapter**. Vì vậy core POM cần adapter:

```xml
<!-- ĐOẠN SAI: billing-core/pom.xml trước khi tái cấu trúc -->
<dependencies>
    <dependency>
        <groupId>com.example.billing</groupId>
        <artifactId>billing-adapter-memory</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
```

Nhưng adapter lại muốn dùng các business types từ core:

```xml
<!-- ĐOẠN SAI: billing-adapter-memory/pom.xml trước khi tái cấu trúc -->
<dependencies>
    <dependency>
        <groupId>com.example.billing</groupId>
        <artifactId>billing-core</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
```

**Hai POM fragments trên chỉ dùng để diễn giải lỗi, không phải cấu hình chạy được.** Kết quả:

```text
billing-core -------------------------> billing-adapter-memory
       ^                                      |
       |______________________________________|
```

Nguyên nhân thực không phải Maven “đi sai thứ tự”, mà **ranh giới code** đang khiến lớp nghiệp vụ cấp cao biết trực tiếp implementation hạ tầng, còn implementation lại cần các type nghiệp vụ.

Nếu chỉ đảo thứ tự `<modules>`:

```xml
<modules>
    <module>billing-adapter-memory</module>
    <module>billing-core</module>
</modules>
```

vòng vẫn tồn tại. Reactor không thể làm cho một module “xây trước chính nó”.

## 6. Tư duy sửa: dependency inversion và tách hợp đồng tối thiểu

Thay vì để core import một implementation cụ thể, ta chuyển hợp đồng cần chia sẻ sang module **API/contract** không phụ thuộc implementation. Các module cùng phụ thuộc vào API.

Trước:

```text
core -------> adapter
  ^              |
  |______________|
```

Sau:

```text
                   billing-cli
                     /     \
                    v       v
             billing-core   billing-adapter-memory
                    \       /
                     v     v
                    billing-api
```

Theo quy ước mũi tên, `billing-cli` cần core và adapter, còn cả core/adapter chỉ cần API. **Không có mũi tên từ core tới adapter.**

### Bốn ranh giới rõ ràng

1. **`billing-api`**: chứa interface `PaymentPort` và value object `Receipt`; **không** import core, adapter hay CLI.
2. **`billing-core`**: chứa business logic `CheckoutService`; biết **interface** `PaymentPort`, không biết class `InMemoryPaymentAdapter`.
3. **`billing-adapter-memory`**: cung cấp implementation `InMemoryPaymentAdapter`; biết `PaymentPort` và `Receipt`, không cần biết core.
4. **`billing-cli`**: composition root; biết core và adapter để **lắp ráp object graph** rồi gọi nghiệp vụ.

Cách này không chỉ làm Maven sort được: nó còn giúp đổi implementation (database, HTTP, mock, Kafka...) mà không sửa business core.

**Không tách một module `common` vô hạn chứa mọi thứ.** Chỉ chuyển **những hợp đồng ổn định, dùng chung, thật sự độc lập**. Nếu hai phần luôn phát hành cùng nhau, không có API độc lập và việc tách chỉ tăng ceremony, cũng nên cân nhắc **gộp lại một module** thay vì sinh quá nhiều module giả.

## 7. Ví dụ Maven reactor Java 17 hoàn chỉnh, không có vòng phụ thuộc

Đây là ví dụ **runnable**, gồm **một root aggregator và bốn child modules**. Unit tests của core dùng một fake `PaymentPort` thay vì phụ thuộc implementation module thật.

### 7.1. Cây thư mục

```text
billing-reactor/
├── pom.xml
├── billing-api/
│   ├── pom.xml
│   └── src/main/java/com/example/billing/api/
│       ├── PaymentPort.java
│       └── Receipt.java
├── billing-core/
│   ├── pom.xml
│   ├── src/main/java/com/example/billing/core/
│   │   └── CheckoutService.java
│   └── src/test/java/com/example/billing/core/
│       └── CheckoutServiceTest.java
├── billing-adapter-memory/
│   ├── pom.xml
│   └── src/main/java/com/example/billing/adapter/
│       └── InMemoryPaymentAdapter.java
└── billing-cli/
    ├── pom.xml
    └── src/main/java/com/example/billing/cli/
        └── Main.java
```

**Cách đặt package và file:** `package com.example.billing.api` phải tương ứng với `src/main/java/com/example/billing/api/`. Mỗi `public class/interface/record` nằm trong file trùng tên.

### 7.2. File billing-reactor/pom.xml — root aggregator + parent

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.billing</groupId>
    <artifactId>billing-reactor</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>billing-api</module>
        <module>billing-core</module>
        <module>billing-adapter-memory</module>
        <module>billing-cli</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.jupiter.version>5.11.4</junit.jupiter.version>
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

Root có `packaging=pom` vì là aggregator, không sinh JAR gom tất cả modules. `<modules>` chỉ thu thập child projects; quan hệ phụ thuộc nằm trong mỗi child POM.

Các children dùng root làm `<parent>` để kế thừa groupId, version, Java release và plugin versions. **Kế thừa parent không tự đặt dependency tới mọi sibling.**

### 7.3. File billing-api/pom.xml — module chỉ chứa hợp đồng

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.billing</groupId>
        <artifactId>billing-reactor</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>billing-api</artifactId>
    <packaging>jar</packaging>
</project>
```

**Không có dependency tới core, adapter hay CLI.** Đây là điều kiện quan trọng để module hợp đồng đứng ở đáy đồ thị.

### 7.4. File billing-api/src/main/java/com/example/billing/api/Receipt.java

```java
package com.example.billing.api;

public record Receipt(String id, int amountCents) {
    public Receipt {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("receipt id must not be blank");
        }
        if (amountCents <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}
```

Đây là **Java 17 record**, dùng làm value object của API. Compact constructor kiểm tra ID không rỗng và số tiền dương.

`Receipt` không biết `CheckoutService` hay `InMemoryPaymentAdapter`, vì vậy nó có thể được cả business core lẫn adapter sử dụng mà không gây import ngược.

### 7.5. File billing-api/src/main/java/com/example/billing/api/PaymentPort.java

```java
package com.example.billing.api;

public interface PaymentPort {
    Receipt charge(int amountCents);
}
```

`PaymentPort` là **hợp đồng**. Nó không quy định charge được xử lý qua HTTP, database hay bộ nhớ. Business core chỉ cần biết `charge(int)` sẽ trả `Receipt`.

Kỹ thuật này được gọi là **dependency inversion**: logic cấp cao phụ thuộc abstraction, còn implementation cấp thấp cũng phụ thuộc abstraction. Không nhầm với việc business logic phụ thuộc trực tiếp implementation.

### 7.6. File billing-core/pom.xml — business logic chỉ cần API

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.billing</groupId>
        <artifactId>billing-reactor</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>billing-core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.billing</groupId>
            <artifactId>billing-api</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.jupiter.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

**Không có `<dependency>` từ core tới adapter.** Đây là cạnh đã được loại bỏ so với thiết kế lỗi ban đầu. JUnit chỉ phục vụ unit test, không trở thành dependency runtime của module business.

### 7.7. File billing-core/src/main/java/com/example/billing/core/CheckoutService.java

```java
package com.example.billing.core;

import java.util.Objects;

import com.example.billing.api.PaymentPort;
import com.example.billing.api.Receipt;

public final class CheckoutService {
    private final PaymentPort paymentPort;

    public CheckoutService(PaymentPort paymentPort) {
        this.paymentPort = Objects.requireNonNull(paymentPort);
    }

    public String checkout(int amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        Receipt receipt = paymentPort.charge(amountCents);
        return "Charged " + receipt.id()
                + ": " + receipt.amountCents() + " cents";
    }
}
```

Class có business rule “số tiền phải dương”. Constructor nhận `PaymentPort` **qua interface**, nên `CheckoutService` không import module adapter. Đây là chỗ tách coupling quan trọng.

**Lưu ý:** `PaymentPort.charge()` có thể trả một receipt, nhưng ví dụ chưa xử lý mạng, retries, transactions hoặc bảo mật thanh toán thật. Đây chỉ là demo ranh giới module và build graph.

### 7.8. File billing-core/src/test/java/com/example/billing/core/CheckoutServiceTest.java

```java
package com.example.billing.core;

import org.junit.jupiter.api.Test;

import com.example.billing.api.PaymentPort;
import com.example.billing.api.Receipt;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CheckoutServiceTest {

    @Test
    void chargesThroughPort() {
        PaymentPort fake = cents -> new Receipt("TEST-42", cents);
        CheckoutService service = new CheckoutService(fake);

        assertEquals("Charged TEST-42: 1500 cents",
                service.checkout(1500));
    }

    @Test
    void rejectsNonPositiveAmount() {
        PaymentPort fake = cents -> {
            throw new AssertionError("port must not be called");
        };
        CheckoutService service = new CheckoutService(fake);

        assertThrows(IllegalArgumentException.class,
                () -> service.checkout(0));
    }
}
```

Đây là **JUnit Jupiter test chạy được** (2 test methods). `PaymentPort` là functional interface với một abstract method nên **lambda** là hợp lệ. Test dùng fake local, **không cần billing-adapter-memory**, không cần server/database và không tạo cycle test dependency.

Quan trọng về kiến trúc: **core test không import adapter**. Khi cần integration test adapter thật, có thể viết test ở module adapter hoặc một module integration-test riêng nằm phía trên core/adapter, thay vì làm core phụ thuộc ngược adapter trong test scope.

### 7.9. File billing-adapter-memory/pom.xml — implementation chỉ cần API

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.billing</groupId>
        <artifactId>billing-reactor</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>billing-adapter-memory</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.billing</groupId>
            <artifactId>billing-api</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

Adapter phụ thuộc API để implement interface và tạo `Receipt`. Nó **không phụ thuộc billing-core**, do đó hai project core/adapter **không còn một quan hệ hai chiều**.

### 7.10. File billing-adapter-memory/src/main/java/com/example/billing/adapter/InMemoryPaymentAdapter.java

```java
package com.example.billing.adapter;

import com.example.billing.api.PaymentPort;
import com.example.billing.api.Receipt;

public final class InMemoryPaymentAdapter implements PaymentPort {

    @Override
    public Receipt charge(int amountCents) {
        return new Receipt("LOCAL-001", amountCents);
    }
}
```

Class cung cấp một implementation của hợp đồng `PaymentPort`. Nó dùng `Receipt` từ API, không import bất cứ class nào của `billing-core`.

**Đây là adapter demo**; trong hệ thống thanh toán thật cần identifier khác nhau cho từng giao dịch, persistence/transactions và idempotency. Đừng dùng một receipt ID cố định trong sản phẩm production.

### 7.11. File billing-cli/pom.xml — composition root

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.billing</groupId>
        <artifactId>billing-reactor</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>billing-cli</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.billing</groupId>
            <artifactId>billing-core</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>com.example.billing</groupId>
            <artifactId>billing-adapter-memory</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

CLI phụ thuộc cả core và adapter để lắp ráp đối tượng. Quan hệ đó **không làm core phụ thuộc adapter**, vì mỗi module có POM của riêng mình.

Tại thời điểm compile CLI, `PaymentPort` từ API cũng được resolve transitively qua các dependencies. Nếu mã trong CLI trực tiếp import type API, theo best practice nên khai báo dependency API trực tiếp thay vì trông cậy transitive dependency vô tình.

### 7.12. File billing-cli/src/main/java/com/example/billing/cli/Main.java

```java
package com.example.billing.cli;

import com.example.billing.adapter.InMemoryPaymentAdapter;
import com.example.billing.core.CheckoutService;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        CheckoutService service =
                new CheckoutService(new InMemoryPaymentAdapter());

        System.out.println("Running billing-cli");
        System.out.println(service.checkout(1500));
    }
}
```

Ở đây **composition root** chủ động tạo adapter và truyền vào core service. Runtime vẫn gọi từ core tới đối tượng implementation qua interface, nhưng **compile-time dependency graph không có core -> adapter**.

**Stdout chính xác của chương trình:**

```text
Running billing-cli
Charged LOCAL-001: 1500 cents
```

Đây là output của `Main`, **không phải log Maven**.

## 8. Build và kiểm chứng thực tế

### 8.1. Build toàn reactor

Trong directory `billing-reactor` chứa root `pom.xml`:

```bash
mvn -version
mvn -B -ntp clean verify
```

Yêu cầu JDK 17+, Maven 3.9.x tương thích hoặc Maven 3 bản đáp ứng yêu cầu các plugin đã chốt, repository có JUnit 5 và build plugins.

Một lượt thành công về logic:
1. Maven thu thập root + 4 modules.
2. Reactor thấy `billing-api` là prerequisite của core và adapter.
3. Reactor thấy `billing-cli` cần core và adapter.
4. Maven build các prerequisites trước module consumer.
5. `billing-core` chạy **2 JUnit Jupiter tests**; các module còn lại không nhất thiết có unit tests.
6. Compiler tạo Java 17 classes; JAR Plugin tạo JAR riêng ở từng module.

Cấu trúc output chính:

```text
billing-api/target/billing-api-1.0.0.jar
billing-core/target/billing-core-1.0.0.jar
billing-adapter-memory/target/billing-adapter-memory-1.0.0.jar
billing-cli/target/billing-cli-1.0.0.jar
billing-core/target/surefire-reports/
```

Với root packaging `pom`, **không** có một JAR root tự gộp tất cả modules. Muốn executable distribution, phải cấu hình classpath/manifest hoặc fat JAR riêng.

### 8.2. Build order minh họa

Một thứ tự hợp lệ:

```text
billing-reactor
billing-api
billing-core
billing-adapter-memory
billing-cli
```

`billing-core` và `billing-adapter-memory` cùng phụ thuộc `billing-api`, nhưng **không phụ thuộc lẫn nhau**, nên giữa hai module ấy có thể có nhiều thứ tự hợp lệ. Hãy xem Reactor Build Order thật của Maven, không dựa vào một sơ đồ như log chính xác 100%.

**Thử đổi thứ tự `<modules>` trên bản sao:** đặt `billing-cli` trước `billing-api`. Maven vẫn phải build những prerequisites trước CLI do quan hệ project dependencies. Một đồ thị không có vòng có thể được topo-sort; một đồ thị có vòng thì không.

### 8.3. Chạy Java 17 sau build

Vì POM demo không thêm executable `Main-Class`, **không dùng `java -jar billing-cli-1.0.0.jar`** rồi mặc định application chạy được.

Linux/macOS, từ root `billing-reactor`:

```bash
java -cp "billing-cli/target/classes:billing-core/target/classes:billing-adapter-memory/target/classes:billing-api/target/classes" com.example.billing.cli.Main
```

Windows PowerShell/CMD, từ root:

```powershell
java -cp "billing-cli/target/classes;billing-core/target/classes;billing-adapter-memory/target/classes;billing-api/target/classes" com.example.billing.cli.Main
```

**Stdout chính xác:**

```text
Running billing-cli
Charged LOCAL-001: 1500 cents
```

Nếu chỉ thêm `billing-cli/target/classes` vào classpath mà không có core/adapter/API, JVM có thể báo `NoClassDefFoundError`. Lỗi classpath runtime đó **khác** lỗi reactor cyclic reference; đừng nhầm nguyên nhân.

### 8.4. Test core không cần adapter

Test report dự kiến:

```text
billing-core/target/surefire-reports/
    TEST-com.example.billing.core.CheckoutServiceTest.xml
```

Trong module core, hai unit tests trên dự kiến có **2 tests, 0 failures, 0 errors**. Test method `rejectsNonPositiveAmount` còn xác nhận fake port **không bị gọi** nếu business input sai.

Đây là bằng chứng ranh giới module tốt: core có thể test riêng qua abstraction mà **không biết tên implementation adapter**.

## 9. Phát hiện vòng trước và sau khi refactor

### 9.1. Khi reactor báo cyclic reference, làm gì đầu tiên?

1. Lấy full error Maven ở đoạn `The projects in the reactor contain a cyclic reference`.
2. Vẽ một sơ đồ mũi tên từ từng module tới module nó phụ thuộc.
3. Đọc `<dependencies>` của các POM **trong vòng**, kiểm tra parent/profile/plugin nếu cần.
4. Xác định **lớp hoặc chức năng cụ thể** khiến module A phải import B và B lại import A.
5. Chọn cách tách: đưa hợp đồng chung xuống module API, đảo hướng dependency qua interface, tách composition root hoặc gộp modules khi phù hợp.
6. Sửa imports, constructor wiring và POM dependencies **cùng lúc**.
7. Chạy lại `mvn -B -ntp validate` để xác nhận Maven build graph đã hợp lệ.
8. Chạy `mvn -B -ntp clean verify` để xác nhận compile/tests và runtime classpath.

Nếu project cycle ngay ở bước **reactor construction**, các goals như `dependency:tree` hoặc `help:effective-pom` chạy từ root **có thể không được thực thi**. Đừng coi “không chạy được dependency:tree” là vấn đề cần sửa bằng cờ CLI; **đọc các POM đã liên quan trực tiếp từ error và giải quyết graph trước**.

### 9.2. `dependency:tree` hỗ trợ ở giai đoạn nào?

Khi graph đã hợp lệ, có thể xem dependencies với phiên bản plugin rõ ràng:

```bash
mvn -B -ntp -pl :billing-cli -am \
    org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Đây là **lệnh shell Linux/macOS** có `\` nối dòng. Cách viết một dòng dùng được ở đa số shell:

```bash
mvn -B -ntp -pl :billing-cli -am org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Trong output của `billing-cli`, quan hệ chính sẽ tương đương:

```text
com.example.billing:billing-cli:jar:1.0.0
+- com.example.billing:billing-core:jar:1.0.0:compile
|  \- com.example.billing:billing-api:jar:1.0.0:compile
\- com.example.billing:billing-adapter-memory:jar:1.0.0:compile
   \- com.example.billing:billing-api:jar:1.0.0:compile
```

Đây là **sơ đồ giải thích**, không phải log chính xác: Maven có thể omit một lần xuất hiện của API vì duplicate/conflict mediation, và các modules cũng in cây riêng trong reactor. JUnit của core ở scope test không phải dependency runtime transitive thông thường của CLI.

### 9.3. Xuất graph DOT khi cần điều tra lớn

Maven Dependency Plugin 3.11.0 hỗ trợ `outputType=dot` và `outputFile`:

```bash
mvn -B -ntp -pl :billing-cli \
    org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree \
    -DoutputType=dot \
    -DoutputFile=dependency-tree.dot
```

Dùng lệnh này **sau khi reactor đã xử lý được** và dependencies đã resolve. DOT có thể đưa vào Graphviz (nếu đã cài) để hình dung graph:

```bash
dot -Tpng dependency-tree.dot -o dependency-tree.png
```

Đây là lựa chọn minh họa, **không bắt buộc** để học Maven. Với mono-repo phức tạp, bạn còn nên thu thập các cạnh project/module từ nhiều POM, vì dependency tree được xuất **theo từng project**, không mặc định là một bản vẽ duy nhất của toàn reactor.

### 9.4. Xem effective POM sau khi graph đã hợp lệ

```bash
mvn -f billing-core/pom.xml help:effective-pom
mvn -f billing-adapter-memory/pom.xml help:effective-pom
```

Tìm dependencies thực tế sau khi merge parent/profile, đặc biệt những dependency bị parent `<dependencies>` áp vào mọi child mà team không nhận ra.

**Không dùng hiệu quả của một module đơn lẻ để phủ nhận lỗi toàn reactor.** POM riêng có thể được resolve trong một số tình huống dù build toàn reactor đang cyclic; kết luận phải dựa trên graph của toàn bộ modules được chọn.

## 10. Tại sao các cách “fix nhanh” thường không giải quyết cycle?

| Cách thử | Vì sao không phải cách sửa chuẩn |
| --- | --- |
| Đổi thứ tự `<module>` | Chỉ thay thứ tự liệt kê; cycle vẫn có A cần B và B cần A |
| Đổi `compile` thành `test` chỉ để né lỗi | Một **project dependency thực sự** vẫn có thể tạo quan hệ reactor; test code vẫn bị coupling |
| Đổi `compile` thành `provided` | Thay classpath/transitivity, không tự tách dependency giữa hai project |
| Đặt `<optional>true</optional>` | Optional ảnh hưởng transitivity sang consumer, không xóa direct edge trong reactor |
| Chuyển dependency sang `<dependencyManagement>` và bỏ `<dependency>` | Có thể khiến module **không còn biên dịch**, vì management không cấp classpath |
| Dùng `<exclusions>` bừa bãi | Exclusions chủ yếu chặn **transitive dependency** theo nhánh; không tự xóa direct project dependency sai |
| `mvn -DskipTests` | Skip chạy test, không xóa project dependency graph |
| `mvn -N ...` | Bỏ thu thập modules; có thể tránh thấy cycle nhưng cũng **không build sản phẩm đa module** |
| `-pl` chỉ build một module | Có thể không thu thập toàn bộ cycle, nhưng không chứng minh project tổng thể đã đúng |
| Chạy `install` một module cũ rồi build module kia | Dễ dùng artifact stale và che coupling; không làm checkout mới build được |
| `mvn -fae` / `-fn` | Điều khiển xử lý failure, không tạo được topological order cho graph cyclic |
| `mvn -T 4` | Chạy song song không thể sửa logic phụ thuộc vòng tròn |
| Tăng/giảm dependency version tùy tiện | Version mediation không thay thế refactor quan hệ code sai |
| Chỉ đặt một module vào `pluginManagement` | Không chắc còn thực thi plugin; có thể làm mất chức năng build thật |

**Nguyên tắc:** sửa **cạnh sai của đồ thị** và **đường import Java gây ra cạnh ấy**. Không chỉ chữa dòng POM để Maven hết báo lỗi mà để code compile/run với classpath bị thiếu.

## 11. Test dependencies cũng cần có ranh giới

Một cycle dễ bị bỏ qua:

```text
billing-core (production) -> billing-api
billing-core (test)       -> billing-adapter-memory
billing-adapter-memory    -> billing-core
```

Người viết unit test ở core muốn dùng implementation thật, nên thêm adapter làm `scope=test`. Nhưng implementation lại import core. Như vậy **graph module có thể vẫn có quan hệ hai chiều** dù một chiều chỉ phục vụ test. Không coi `scope=test` là biện pháp an toàn để phá vòng.

Có ba cách thiết kế tốt hơn tùy nhu cầu:
1. **Unit test core bằng fake port** (như ví dụ), không thêm adapter dependency.
2. **Đặt integration tests trong adapter module** nếu adapter có đủ thông tin để kiểm tra hợp đồng.
3. **Tạo một module `billing-integration-tests`** phía trên, phụ thuộc core + adapter + API, dùng Failsafe/JUnit để chạy kiểm thử phối hợp.

Mô hình integration-test module:

```text
billing-integration-tests
          |          \
          v           v
    billing-core  billing-adapter-memory
          \           /
           v         v
             billing-api
```

Đây là **sơ đồ kiến trúc minh họa**, không phải phần bổ sung bắt buộc vào POM demo. Module kiểm thử tích hợp không nên trở thành dependency của core/adapter production, vì sẽ tạo chiều ngược không hợp lý.

### Có cần tách `test-jar`?

Maven JAR Plugin hỗ trợ goal `test-jar` để chia sẻ test utility trong một số tình huống, nhưng việc biến nhiều module phụ thuộc test artifacts của nhau dễ gây vòng khác. Nếu hai module cần cùng test fixture, có thể đưa fixture vào module test-support độc lập hoặc test module cấp cao, thay vì tạo cycle chỉ vì reuse một helper nhỏ.

## 12. Chọn ranh giới module theo trách nhiệm, không theo số lượng class

Một cách thực tế là xác định:
- **Ai sở hữu contract?** Interface/value object ổn định nên thuộc module API hoặc domain module thấp nhất mà các consumer hợp lệ có thể dùng.
- **Ai sở hữu business rule?** Đặt trong core, không import code truy cập DB/HTTP của adapter.
- **Ai sở hữu infrastructure?** Adapter implements interface, không yêu cầu core import implementation.
- **Ai tạo object thật?** Application/composition root ở tầng ngoài biết những implementations cần lắp ráp.
- **Ai gọi ai tại runtime?** Runtime dispatch qua interface không nhất thiết phản ánh chiều compile dependency.

Không phải cứ thấy hai module gọi nhau là phải sinh thêm module `common`. Hãy kiểm tra xem chúng có thật sự là **hai đơn vị có trách nhiệm và vòng đời release riêng** hay không.

### Khi nên gộp hai module thay vì trích xuất API?

Cân nhắc gộp khi:
- Hai phần không có interface ổn định và luôn thay đổi cùng nhau.
- Chúng không có nhu cầu build/deploy/reuse độc lập.
- Mọi phương thức public chỉ là chi tiết nội bộ của một cohesive component.
- Việc tách một API module chỉ để chứa vài getters có thể làm đồ thị khó hiểu hơn.
- Tests cần liên tục chui qua ranh giới vì abstraction giả tạo.

Gộp module loại bỏ **cycle ở cấp Maven project** giữa hai phần, nhưng vẫn cần xử lý quality/coupling bên trong package. Không dùng gộp làm cái cớ bỏ kiến trúc rõ ràng nếu thực sự có hai trách nhiệm độc lập.

### Khi nên tách module API?

Nên cân nhắc khi:
- Core và nhiều adapters cần dùng cùng hợp đồng.
- Có nhiều implementation (in-memory, JDBC, remote gateway).
- Public API ít phụ thuộc và ổn định.
- Team muốn business core test độc lập.
- Adapter thay đổi thường xuyên nhưng core không cần compile lại theo implementation cụ thể.

Module API càng nhỏ và ít dependency càng dễ tái sử dụng. Tránh để API import framework infrastructure (ví dụ Spring/JPA annotations) trừ khi đó là chủ đích và được các consumer chấp nhận.

## 13. Vòng liên quan build plugin và parent POM

Không phải cycle nào cũng là Java project dependency.

### 13.1. Build plugin là module trong cùng reactor

Giả sử:
- `generator-plugin` là một Maven plugin project.
- `business-api` khai báo plugin này để generate sources.
- Bản thân `generator-plugin` lại phụ thuộc classes của `business-api`.

Đây có thể tạo quan hệ vòng ở **reactor sorting**, dù mã Java của `business-api` không trực tiếp import `generator-plugin`. Khi điều tra, kiểm tra:
- `<build><plugins>` thực sự instantiated;
- plugin dependencies;
- build extensions;
- artifacts trong reactor được tham chiếu bởi chúng.

Giải pháp thường là trích **schema/contract/generator model** xuống module độc lập, để plugin và consumer đều dùng model từ tầng thấp, hoặc tách build plugin ra khỏi reactor ứng dụng với version/release lifecycle riêng.

### 13.2. Parent phụ thuộc ngược vào child

Parent POM là chỗ phù hợp cho `dependencyManagement`/`pluginManagement`, **không nên khai báo project dependency tới module con** chỉ để tận dụng code ở child. Những dependency ở `<dependencies>` của parent còn có thể được inherit bởi nhiều child và tạo các cạnh không mong đợi.

**Đừng nhầm**:
- `<dependencyManagement>` có thể quản lý version dependency của child nhưng không tự thêm dependency.
- `<dependencies>` của parent có thể được inherit (tùy cơ chế model) và ảnh hưởng classpath/project graph.
- Import một BOM được build từ submodule trong chính parent importer có thể gây vấn đề bootstrap/model resolution; đây có thể là vòng khác cần xử lý bằng cách tách BOM/parent trách nhiệm.

Với Maven 4, có thêm hướng dẫn về subprojects/root discovery, nhưng nguyên tắc **dependency graph phải không có cycle khi xây project** vẫn giữ giá trị. Khi gặp lỗi cụ thể, xác nhận `mvn -version` và tài liệu đúng bản.

## 14. Lộ trình refactor an toàn trên project thật

Không xóa bừa tất cả dependencies cùng lúc. Hãy làm theo một chuỗi thay đổi nhỏ, review được.

### Bước 1 — Vẽ đồ thị và nêu quyền sở hữu

Liệt kê tất cả modules và các cạnh `A -> B` đang tồn tại. Đánh dấu đúng **đoạn vòng** thay vì xử lý cả repository. Với mỗi cạnh, ghi tên class/interface khiến module A cần B.

### Bước 2 — Chọn dependency direction mong muốn

Đặt nguyên tắc, ví dụ:

```text
apps/entrypoints -> business/core -> contracts/api
adapters         -> contracts/api
```

Adapter và core có thể ngang nhau về mức phụ thuộc nhưng **không import nhau**. App ở tầng ngoài lắp ráp cả hai.

### Bước 3 — Chuyển contracts trước

Di chuyển interface/value object **không phụ thuộc implementation** vào `billing-api`. Nếu contract có tên thuộc tầng hạ tầng cụ thể, cân nhắc đặt tên mang ý nghĩa nghiệp vụ hơn.

Sau đó cập nhật imports của core và adapter tới API.

### Bước 4 — Xóa cạnh core -> adapter

Đổi code core từ:

```java
// SAI VỀ RANH GIỚI — minh họa, không phải class độc lập
private final InMemoryPaymentAdapter adapter =
        new InMemoryPaymentAdapter();
```

thành:

```java
// ĐÚNG VỀ RANH GIỚI — minh họa, xem CheckoutService hoàn chỉnh ở trên
private final PaymentPort paymentPort;
```

Ở các snippet trên, biến được đặt trong class và imports tương ứng; không thể copy nguyên dòng thành file `.java` độc lập.

### Bước 5 — Để app tạo implementation

Chuyển `new InMemoryPaymentAdapter()` vào `billing-cli` (composition root) hoặc wiring module/DI configuration của ứng dụng.

**Nguyên tắc:** core không quyết định chọn adapter nào. Core chỉ xác định hành vi hợp đồng cần có.

### Bước 6 — Cập nhật POM dependencies

- `billing-core -> billing-api`;
- `billing-adapter-memory -> billing-api`;
- `billing-cli -> billing-core` và `billing-cli -> billing-adapter-memory`;
- **không** có `billing-core -> billing-adapter-memory` hay ngược lại.

Chạy `mvn validate` để xác nhận reactor graph hợp lệ **trước** khi chờ compile/test.

### Bước 7 — Test lớp và test artifact

- Unit test core dùng fake port.
- Adapter test kiểm tra contract.
- Integration test tầng trên kết hợp core + adapter.
- Chạy reactor `clean verify`, sau đó khởi động app thật với classpath/packaging đúng.

### Bước 8 — Phòng cycle quay lại

Dùng code review và nếu cần thêm dependency rules để cấm core phụ thuộc adapter. Đừng để quy tắc sống chỉ trong tài liệu; kiểm tra POM changes, imports và CI phù hợp.

## 15. Có thể dùng thuật toán nào để nhận biết cycle?

Đồ thị dependency có **nodes** là modules và **directed edges** là các yêu cầu phụ thuộc. Một graph **không có chu trình** gọi là DAG (directed acyclic graph), cho phép **topological sorting**.

Hai cách phát hiện phổ biến:
- **Depth-first search (DFS) với recursion stack**: nếu trong khi thăm node lại gặp một node đang nằm trên đường DFS hiện tại, có cycle. Có thể tái dựng đường đi để chỉ ra vòng.
- **Kahn's algorithm**: mỗi bước chọn node không còn prerequisites, bỏ nó và giảm số cạnh liên quan. Nếu còn node nhưng không chọn được node tiếp theo, graph có cycle.

Ví dụ:

```text
billing-api                  -> build được đầu tiên
billing-core -> billing-api
billing-adapter -> billing-api
billing-cli -> billing-core, billing-adapter
```

Đổi chiều tư duy cho sort: khi xem `A -> B` là A **phụ thuộc** B, Kahn bắt đầu từ modules có **không có dependency prerequisites**, tức `billing-api`.

Một đường hợp lệ:

```text
billing-api
billing-core
billing-adapter
billing-cli
```

Nhưng core và adapter có thể đổi chỗ vì không có cạnh giữa chúng.

Nếu có:

```text
billing-core -> billing-adapter
billing-adapter -> billing-core
```

không module nào trong cặp có thể được chọn trước sau khi xử lý các prerequisites khác. Đó là nguồn gốc toán học của lỗi Maven reactor cycle.

**Không nhất thiết phải tự code thuật toán** để dùng Maven; Maven đã dựng project dependency graph. Phần này giúp lý giải tại sao thay thứ tự XML hoặc chạy nhiều threads không thể sửa đồ thị cyclic.

## 16. Khi chạy trong multi-module CI

Một pipeline có thể:

```bash
mvn -B -ntp clean verify
```

để kiểm tra toàn bộ reactor. Trước khi merge PR thay đổi dependencies, bảo đảm:
1. Tất cả POM parse được, modules paths đúng.
2. Reactor không có cyclic references.
3. Các module API không phụ thuộc adapters hoặc ứng dụng.
4. Build từ một **checkout sạch** thành công, không dựa vào JAR cũ đã `install`.
5. Test reports phản ánh đúng tests của từng module.
6. Không “fix” bằng skip hoặc chỉ build một phần reactor.

### Chọn một module cùng prerequisites

Sau khi không còn cycle:

```bash
mvn -B -ntp -pl :billing-cli -am clean verify
```

`-pl :billing-cli` chọn app theo artifactId; `-am` xây những reactor modules mà app phụ thuộc vào. Đây là cách kiểm tra một lát cắt hợp lệ, **không thay thế build toàn reactor** trước release.

### Kiểm tra tác động khi đổi API

```bash
mvn -B -ntp -pl :billing-api -amd test
```

`-amd` chọn dependents của API trong reactor, giúp kiểm tra những modules dùng API. Với ứng dụng lớn, các module phụ thuộc qua nhiều tầng cũng có thể tham gia build.

`-am` và `-amd` là công cụ chọn project **khi graph đã có thể xây hợp lệ**; chúng không phải biện pháp phá chu trình.

### Thận trọng với artifact đã `install` từ lượt cũ

Nếu một module compile được khi chạy đơn lẻ trên máy dev nhưng CI root fail cyclic, có thể dev đang lấy **artifact cũ ở local repository** thay vì module đang thay đổi trong reactor. Hãy tin kết quả của build từ checkout sạch hơn là một lượt chạy chỉ hoạt động khi có cache.

Không cần xóa toàn bộ `.m2` để chứng minh cycle; kiểm tra POM graph trực tiếp và chạy lại đúng root reactor.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Khả năng nguyên nhân | Cách xử lý đúng |
| --- | --- | --- |
| `The projects in the reactor contain a cyclic reference` | Có vòng trong quan hệ project/plugin/extension | Xem GAV/edge trong error, refactor graph |
| Core cần implementation, implementation cần core | Ranh giới nghiệp vụ/hạ tầng đảo chiều | Đưa port/contract vào API, composition root tạo adapter |
| Đổi `<modules>` mà lỗi vẫn còn | XML order không xóa dependency edge | Sửa `<dependencies>` và imports |
| Đổi scope thành `test` vẫn lỗi | Direct dependency vẫn là cạnh reactor hoặc tests coupled | Dùng fake/test module cấp cao |
| Đổi scope thành `provided` làm runtime thiếu class | Đã thay classpath thay vì refactor | Trả scope đúng, sửa coupling |
| Đặt optional/exclusions mà không hết vòng | Tác động transitivity, không xóa direct dependency | Tách/đảo hướng trực tiếp |
| `dependency:tree` ở root không chạy | Reactor thất bại trước goal | Đọc POM/error trước, chạy tree sau khi sửa |
| App không import được API | Thiếu dependency GAV hoặc dependency scope sai | Khai báo dependency trong module tiêu thụ |
| Core test import adapter làm cycle | Test fixture đặt sai phía kiến trúc | Dùng fake port hoặc integration-test module |
| Shared API phụ thuộc adapter | API bị nhiễm implementation | Di chuyển infrastructure types ra adapter |
| `ClassNotFoundException` khi chạy CLI | Java classpath thiếu module JAR | Dùng `java -cp` đủ modules hoặc phân phối runnable |
| `mvn -N` chạy được nhưng root fail | Đã né thu thập modules | Xử lý vòng trong full reactor |
| `mvn install` module cũ che lỗi | Dùng local artifact stale | Kiểm tra reactor sạch, POM đúng GAV |
| `pluginManagement` tưởng là dependency | Managed-only không instantiate plugin | Xem instantiated plugins và dependency relations |
| Parent BOM phụ thuộc child import ngược | POM bootstrap/model resolution có vòng | Tách BOM/parent khỏi child cần nó |
| Build nhiều threads vẫn kẹt | Parallelism không giải quyết cycle logic | Loại vòng trước khi tối ưu hiệu năng |
| Release artifact xanh nhưng API khó thay đổi | Ranh giới module phụ thuộc implementation | Test dependency direction và API contracts |
| Không rõ chiều mũi tên graph | Nhầm “A dùng B” với “B cần A” | Quy ước A -> B nghĩa A phụ thuộc B, B build trước A |
| Đổi tên package mà cycle vẫn còn | POM dependencies vẫn hai chiều | Sửa cả imports và Maven POM |
| Nhiều module dồn vào `common` rồi coupling tệ hơn | Shared module thành “god module” | Tách hợp đồng ổn định có chủ sở hữu rõ |

### Debug checklist gọn

1. Đọc **first cyclic-reference error**, ghi đầy đủ các module GAV.
2. Vẽ các cạnh direct dependency/plugin/extension có thật.
3. Tìm đoạn cycle ngắn nhất và chức năng bị kéo qua ranh giới.
4. Quyết định **tách API**, **inversion**, **integration-test module** hoặc **gộp cohesive modules**.
5. Sửa Java imports và POM dependencies đồng bộ.
6. Chạy `mvn validate` từ root để xác nhận topo-sort hợp lệ.
7. Chạy `mvn clean verify` để kiểm tra classes/tests.
8. Chạy app/test integration thực tế, đọc outputs.
9. Dùng `dependency:tree` sau khi reactor hợp lệ để kiểm tra graph còn lại.
10. Thêm quy tắc review/CI để cycle không quay lại.

## 18. Câu hỏi và bài tập

### Bài 1 — Phát hiện vòng trực tiếp

Cho graph `A -> B`, `B -> A`. Có bao nhiêu thứ tự topo hợp lệ?

**Đáp án:** Không có; hai module đều cần module kia build trước.

### Bài 2 — Phát hiện vòng ba module

Cho `web -> service`, `service -> persistence`, `persistence -> web`. Sửa chỉ bằng đảo `<modules>` được không?

**Đáp án:** Không. Cần thay ít nhất một dependency edge và tương ứng code responsibility.

### Bài 3 — Management có tạo dependency?

Parent có `<dependencyManagement>` cho `billing-api` nhưng child không khai báo `<dependency>`. Child có tự import `PaymentPort` không?

**Đáp án:** Không; dependencyManagement quản lý version khi dependency được khai báo, không tự cấp classpath.

### Bài 4 — Core có nên `new` adapter?

Nếu `CheckoutService` trực tiếp `new InMemoryPaymentAdapter()`, điều gì bất lợi?

**Đáp án:** Core phải biết implementation và cần compile dependency adapter; việc adapter cần business types dễ gây cycle, thay adapter khó và core tests phụ thuộc hạ tầng.

### Bài 5 — Sửa bằng port interface

Trong ví dụ, module nào sở hữu `PaymentPort`? Những module nào compile-depend API?

**Đáp án:** `billing-api` sở hữu. `billing-core` và `billing-adapter-memory` có direct dependency tới API; CLI nhận API transitively qua chúng nếu không import API trực tiếp.

### Bài 6 — Thiết kế test

Unit test của core cần giả lập thanh toán. Tại sao fake `PaymentPort` qua lambda tốt hơn thêm test dependency vào adapter thật?

**Đáp án:** Unit test độc lập hạ tầng, có thể xác minh business rule nhanh, không tạo cạnh phụ thuộc ngược giữa modules.

### Bài 7 — Không có `Main-Class`

POM `billing-cli` là packaging `jar`, nhưng chạy `java -jar ...` báo thiếu main manifest attribute. Có phải reactor vẫn bị cycle không?

**Đáp án:** Không. Reactor có thể build hoàn toàn đúng; lỗi launch do JAR/manifest/classpath, không phải dependency cycle.

### Bài 8 — Dùng `-pl` để che lỗi

`mvn -N validate` ở parent chạy được, còn `mvn clean verify` ở root fail cyclic. Kết luận dự án đã đúng chưa?

**Đáp án:** Chưa. `-N` chỉ validate root, không chứng minh full reactor graph không có vòng.

### Bài 9 — Vòng qua test

Core có test dependency tới adapter; adapter lại có compile dependency tới core. Vì sao đổi scope `compile` sang `test` chưa chắc giúp?

**Đáp án:** Cạnh project dependency vẫn tồn tại và test code bị coupling; tách fixtures hoặc dùng port fake/integration-test module.

### Bài 10 — Chọn phương án thay đổi

Hai modules A và B luôn deploy chung, không có API ổn định, các class gọi nhau khắp nơi. Nên ưu tiên tạo module `common` ngay lập tức không?

**Đáp án định hướng:** Chưa chắc. Cân nhắc gộp thành một cohesive module trước, hoặc xác định ranh giới đúng rồi mới tách abstraction.

## 19. Checklist trước khi merge thay đổi multi-module

- [ ] Root aggregator khai báo đúng các module và packaging `pom`.
- [ ] Không có project/module dependency cycles trong full reactor.
- [ ] Phân biệt actual dependencies với `dependencyManagement`/`pluginManagement`.
- [ ] Core không import concrete adapter nếu kiến trúc yêu cầu độc lập infrastructure.
- [ ] API/contract module không phụ thuộc implementation hoặc application.
- [ ] App/composition root lắp ráp concrete implementation và core qua interface.
- [ ] Unit tests ở core dùng fake/mock phù hợp, không tạo dependency vòng chỉ để share fixture.
- [ ] Nếu có integration-test module, nó phụ thuộc xuống core/adapters chứ không ngược lên.
- [ ] Child POMs dùng đúng GAV, scopes và parent inheritance.
- [ ] Không dùng đổi `<modules>` order, `optional`, `exclusions`, `-N`, `-pl` hoặc cached artifacts để che cycle.
- [ ] Có `mvn validate` từ root trên checkout đủ modules.
- [ ] Có `mvn clean verify` từ root trong CI sạch.
- [ ] Đã đọc test reports và thử chạy app với runtime classpath đúng.
- [ ] Đã xác nhận reactor build order thay vì đoán từ thứ tự XML.
- [ ] `dependency:tree` được dùng khi graph có thể build, không kỳ vọng goal chạy trước lỗi graph.
- [ ] Phạm vi tách module hợp lý; không tạo “god common module”.
- [ ] Trường hợp build plugin/extension/BOM cũng được rà soát nếu error đề cập chúng.
- [ ] Đã ghi lại dependency direction mong muốn cho team review.

**Tổng kết:** Vòng phụ thuộc trong Maven reactor là một vấn đề **đồ thị dependency**, không phải lỗi do sắp xếp `<modules>` chưa khéo. Maven không thể topo-sort khi có `A -> B -> A`. Cách sửa bền vững là **thay ranh giới kiến trúc**: tách hợp đồng nhỏ, chuyển core phụ thuộc abstraction, đặt implementation ở adapter và lắp ráp ở ứng dụng; hoặc **gộp** hai module nếu ranh giới tách là giả tạo. Khi graph đã không còn vòng, `mvn validate`, `mvn clean verify`, test reports và runtime test mới xác nhận refactor thật sự hoạt động.

## Tài liệu Apache Maven chính thức

- [Maven — Guide to Working with Multiple Modules (Reactor Sorting)](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven — POM Reference](https://maven.apache.org/pom.html)
- [Maven — Introduction to the POM: inheritance and aggregation](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Maven Dependency Plugin — dependency:tree 3.11.0](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Maven Dependency Plugin — dependency tree output formats](https://maven.apache.org/plugins/maven-dependency-plugin/examples/tree-mojo.html)
- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven — Guide to Multiple Subprojects (Maven 4)](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html)