# Thiết kế named module cho thư viện công khai

## 1. Bối cảnh và mục tiêu

Một thư viện Java công khai thường phải đáp ứng hai nhóm người dùng: ứng dụng dùng `classpath` truyền thống và ứng dụng dùng Java Platform Module System (JPMS) từ Java 9 trở lên. Khi xuất bản dưới dạng **named module**, thư viện có tên module ổn định, mô tả phụ thuộc bằng `module-info.java` và công bố rõ những package nào thuộc API được phép truy cập.

Mục tiêu của thiết kế không chỉ là làm cho JAR chứa `module-info.class`. Một thư viện tốt cần:

- Cho ứng dụng khác sử dụng API qua `requires <module-name>` mà không cần truy cập package nội bộ.
- Giữ tên module, API xuất bản và các kiểu xuất hiện trong chữ ký phương thức ổn định qua các bản phát hành.
- Khai báo đủ phụ thuộc lúc biên dịch/chạy; tránh tạo phụ thuộc ngầm giữa các module.
- Có chủ đích với reflection, ServiceLoader, thư viện chưa modular hóa và khả năng chạy trên classpath.
- Được kiểm chứng bằng một ứng dụng tiêu thụ thực tế và công cụ của JDK.

**Phạm vi ví dụ:** JDK 17+, Java thuần, tên module minh họa là `com.example.greetings`. Đổi tên và package theo tên miền/namespace thực tế trước khi xuất bản.

## 2. Hiểu đúng ranh giới của named module

Đối với một JAR đặt trên `--module-path`, descriptor `module-info.class` cho phép JPMS nhận diện đây là **explicit named module**. Tên module là định danh logic, không đồng nhất với tên file JAR, Maven `groupId` hoặc Maven `artifactId`.

Các quan hệ cần phân biệt:

| Thành phần | Ý nghĩa với thư viện công khai |
| --- | --- |
| `module com.example.greetings` | Đặt tên module ổn định để ứng dụng tiêu thụ khai báo `requires` |
| `exports com.example.greetings.api` | Công khai các `public` type trong package API cho module khác ở thời điểm biên dịch và chạy |
| Package không được `exports` | Có thể chứa `public` class, nhưng code từ module khác không được truy cập trực tiếp qua module path |
| `requires other.module` | Module hiện tại đọc các public API đã export của dependency |
| `requires transitive other.module` | Những module đọc module hiện tại cũng đọc được dependency đó |
| `opens package` | Cho phép deep reflection vào package lúc chạy; không đồng nghĩa với `exports` |
| `uses` / `provides ... with` | Khai báo điểm mở rộng qua `ServiceLoader`, tránh buộc consumer phụ thuộc implementation |

`public` trên class/method chỉ giải quyết mức truy cập trong Java; JPMS thêm ranh giới package/module. Vì vậy một class `public` nằm trong package không export vẫn được xem là implementation detail ở phía consumer dùng module path.

### Tên module và package

Đặt tên module bằng reverse DNS, ví dụ `com.example.greetings`; thông thường thống nhất prefix với package, nhưng không có quy tắc buộc chúng phải trùng hoàn toàn. Chọn tên có thể duy trì nhiều năm. Đừng gắn version vào tên module, ví dụ `com.example.greetings.v2` chỉ để phản ánh thay đổi bản phát hành: module name là một phần hợp đồng tích hợp của consumer.

Cùng một package không được phân tán vào hai module được phân giải chung trong một layer. Đây là rủi ro **split package**; nên thiết kế package boundary rõ từ đầu.

## 3. Thiết kế mặt công khai trước khi viết module-info.java

Chia package theo vai trò thay vì export toàn bộ cây source:

- `com.example.greetings.api`: facade, interface, value type, exception mà khách hàng cần sử dụng.
- `com.example.greetings.spi`: hợp đồng dành cho plugin/nhà cung cấp dịch vụ, chỉ export nếu muốn cho người khác triển khai.
- `com.example.greetings.internal`: parser, cache, thuật toán, helper, default implementation; giữ không export.
- `com.example.greetings.model`: chỉ export khi model thực sự là API; không export đơn thuần vì framework cần reflection.

Đánh giá **toàn bộ chữ ký public/protected** của type trong package export: tham số, kiểu trả về, superclass, interface, generic bound, checked exception, annotation có ý nghĩa với consumer. Nếu một API trả về kiểu nằm trong package bị giấu, consumer sẽ khó biên dịch hoặc sử dụng đúng hợp đồng. Có hai lựa chọn: xuất bản kiểu đó một cách có chủ đích hoặc đổi API để phụ thuộc vào abstraction công khai.

Ví dụ API nên cho consumer gọi:

```java
import com.example.greetings.api.Greetings;
String message = Greetings.greet("An");
```

Consumer không nên phải biết `GreetingFormatter` ở package `internal`, và không nên cần `--add-exports` để dùng thư viện.

**Nguyên tắc:** export tối thiểu những package có hợp đồng hỗ trợ lâu dài. Mỗi package export tạo cam kết tương thích cho các release sau.

## 4. Ví dụ hoàn chỉnh: thư viện và ứng dụng tiêu thụ

Cấu trúc project mẫu:

```text
project/
├── lib/
│   └── src/main/java/
│       ├── module-info.java
│       └── com/example/greetings/
│           ├── api/Greetings.java
│           └── internal/GreetingFormatter.java
└── app/
    └── src/main/java/
        ├── module-info.java
        └── com/example/greetings/demo/Main.java
```

### 4.1. Descriptor của thư viện

File `lib/src/main/java/module-info.java`:

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

Thư viện này không cần directive `requires java.base;` vì mọi module đều đọc `java.base` theo mặc định. Package `internal` không có trong `exports`, nên không trở thành API truy cập trực tiếp từ bên ngoài.

### 4.2. API công khai

File `lib/src/main/java/com/example/greetings/api/Greetings.java`:

```java
package com.example.greetings.api;

import com.example.greetings.internal.GreetingFormatter;

public final class Greetings {
    private Greetings() {
    }

    public static String greet(String name) {
        return GreetingFormatter.format(name);
    }
}
```

### 4.3. Implementation được đóng gói

File `lib/src/main/java/com/example/greetings/internal/GreetingFormatter.java`:

```java
package com.example.greetings.internal;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String format(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Xin chào, " + name.trim() + "!";
    }
}
```

`GreetingFormatter` vẫn có thể là `public` để các package bên trong **cùng một module** gọi được; khả năng truy cập của consumer từ module khác bị giới hạn bởi descriptor.

### 4.4. Consumer là named module khác

File `app/src/main/java/module-info.java`:

```java
module com.example.greetings.demo {
    requires com.example.greetings;
}
```

File `app/src/main/java/com/example/greetings/demo/Main.java`:

```java
package com.example.greetings.demo;

import com.example.greetings.api.Greetings;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greetings.greet("An"));
    }
}
```

Nếu consumer thử import `com.example.greetings.internal.GreetingFormatter`, trình biên dịch từ chối truy cập vì package này không được export sang module consumer. Đó là hành vi bảo vệ ranh giới mong muốn.

### 4.5. Biên dịch, đóng JAR và chạy

Trong thư mục `project/`, dùng JDK 17+ và PowerShell:

```powershell
New-Item -ItemType Directory -Force out/lib, out/app | Out-Null
javac --release 17 -d out/lib lib/src/main/java/module-info.java lib/src/main/java/com/example/greetings/api/Greetings.java lib/src/main/java/com/example/greetings/internal/GreetingFormatter.java
jar --create --file out/com.example.greetings.jar -C out/lib .
javac --release 17 --module-path out/com.example.greetings.jar -d out/app app/src/main/java/module-info.java app/src/main/java/com/example/greetings/demo/Main.java
java --module-path "out/com.example.greetings.jar;out/app" --module com.example.greetings.demo/com.example.greetings.demo.Main
```

Kết quả mong đợi:

```text
Xin chào, An!
```

Trên Linux/macOS, dấu phân cách nhiều entry trong module path là `:` thay cho `;`. Các lệnh `javac` trên liệt kê tường minh toàn bộ file Java để dễ tái hiện; dự án thực tế nên để Maven/Gradle đảm nhiệm biên dịch và đóng gói.

Kiểm tra descriptor đã nằm trong JAR:

```powershell
jar --describe-module --file out/com.example.greetings.jar
```

Thông tin phải phản ánh module `com.example.greetings` và package export `com.example.greetings.api`. Không cần công khai package `internal` để consumer hoạt động.

## 5. Chọn requires, requires transitive và requires static

### `requires`: phụ thuộc trực tiếp

Khai báo `requires com.example.parser;` khi code trong thư viện cần đọc API đã export của module `com.example.parser`. Các module khác yêu cầu thư viện của bạn không tự động đọc module parser qua quan hệ này.

### `requires transitive`: dependency hiện diện trong API

Giả sử package API của `com.example.reports` công khai phương thức trả về `java.sql.Connection`:

```java
package com.example.reports.api;

public interface ConnectionFactory {
    java.sql.Connection open() throws java.sql.SQLException;
}
```

Descriptor phù hợp:

```java
module com.example.reports {
    requires transitive java.sql;
    exports com.example.reports.api;
}
```

Một module `requires com.example.reports;` khi đó cũng đọc `java.sql`, nên API có thể sử dụng được đúng kiểu mà nó phơi ra. Chỉ dùng `transitive` khi dependency thực sự là một phần hợp đồng công khai; dùng tràn lan khiến đồ thị phụ thuộc rộng và khó kiểm soát.

### `requires static`: dependency chỉ bắt buộc tại thời điểm biên dịch

`requires static com.example.annotations;` diễn đạt dependency cần cho biên dịch nhưng không nhất thiết có khi chạy. Cách này phù hợp với một số annotation API hoặc integration tùy chọn. Nó **không tự bảo đảm** mã vẫn hoạt động khi gọi vào những kiểu không hiện diện ở runtime: hãy thiết kế đường thực thi và thử nghiệm khi dependency bị bỏ đi.

Module descriptor không khóa phiên bản dependency bằng một cú pháp tương đương Maven version range. Phiên bản được xử lý bởi hệ thống build/phân phối, kết hợp với chính sách tương thích API.

## 6. exports, qualified exports và opens: chọn đúng quyền truy cập

### `exports` là API tĩnh

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

Mọi module đọc được `com.example.greetings` có thể dùng public type trong package `api`.

### Qualified export dành cho tích hợp giới hạn

```java
module com.example.greetings {
    exports com.example.greetings.api;
    exports com.example.greetings.internal.bridge to com.example.greetings.testkit;
}
```

Chỉ module `com.example.greetings.testkit` được phép truy cập public type trong `internal.bridge` qua module path. Cách này phù hợp với integration có kiểm soát nhưng tạo kết nối tên module cụ thể; đừng dùng nó để “vá” API chưa rõ ranh giới.

### `opens` dành cho deep reflection

Các framework serialization, ORM hoặc dependency injection đôi khi cần truy cập constructor/field không public bằng reflection. Khi có yêu cầu thực sự, ưu tiên mở đúng package cho đúng module:

```java
module com.example.greetings {
    exports com.example.greetings.api;
    opens com.example.greetings.model to com.fasterxml.jackson.databind;
}
```

Directive minh họa này chỉ phù hợp khi project có package `model` và module thư viện Jackson tương ứng trong đồ thị module. `opens` cho phép deep reflection lúc chạy, nhưng không cho phép consumer biên dịch code truy cập các type như `exports`. Nếu cần cả API tĩnh và reflection, thiết kế hai quyền theo nhu cầu. Tránh `open module` (mở toàn bộ package) khi chỉ một package cần reflection.

Cũng tránh phụ thuộc lâu dài vào tham số JVM như `--add-opens` hoặc `--add-exports` cho API phổ thông; chúng thường là dấu hiệu cần chỉnh descriptor, packaging hoặc cách tích hợp.

## 7. Điểm mở rộng bằng ServiceLoader

Một thư viện cần plugin có thể công khai **SPI nhỏ**, giữ implementation mặc định trong package nội bộ và cho bên thứ ba đóng gói provider riêng.

Giả sử có interface:

```java
package com.example.greetings.spi;

public interface GreetingProvider {
    String greet(String name);
}
```

Descriptor phía thư viện khi tự tìm provider và có provider mặc định:

```java
module com.example.greetings {
    exports com.example.greetings.api;
    exports com.example.greetings.spi;

    uses com.example.greetings.spi.GreetingProvider;
    provides com.example.greetings.spi.GreetingProvider
        with com.example.greetings.internal.DefaultGreetingProvider;
}
```

Implementation `DefaultGreetingProvider` phải thực hiện đúng hợp đồng provider của `ServiceLoader` (ví dụ public class implements SPI, có constructor không tham số phù hợp), nhưng package chứa nó **không cần export** cho consumer.

Thư viện truy vấn service:

```java
ServiceLoader<GreetingProvider> providers =
    ServiceLoader.load(GreetingProvider.class);

for (GreetingProvider provider : providers) {
    System.out.println(provider.greet("An"));
}
```

Module plugin bên ngoài có thể khai báo:

```java
module com.partner.greetings.french {
    requires com.example.greetings;

    provides com.example.greetings.spi.GreetingProvider
        with com.partner.greetings.french.FrenchGreetingProvider;
}
```

Điều kiện quan trọng: module provider phải nằm trong cấu hình module được phân giải khi chạy (đặc biệt trong runtime image hoặc module layer tùy chỉnh). Không giả định thứ tự các provider do `ServiceLoader` trả về; nếu ứng dụng cần ưu tiên, hãy xác lập tiêu chí lựa chọn trong hợp đồng SPI. Giữ SPI hẹp và ghi rõ tương thích phiên bản để đối tác dễ triển khai.

`uses` dành cho module gọi `ServiceLoader`. `provides` dành cho module đóng góp implementation. Chúng bổ sung cho `exports`, không thay thế quyền truy cập cần thiết vào interface SPI.

## 8. Đóng gói và tương thích với hệ sinh thái

### 8.1. Một artifact, hai cách sử dụng

Một modular JAR chứa `module-info.class` vẫn có thể được đưa vào classpath truyền thống, nơi cơ chế module resolution/encapsulation không được áp dụng theo cùng cách với named module. Vì vậy, với thư viện hướng đến nhiều đối tượng:

- Chạy thử consumer bằng `--module-path` và descriptor `requires`.
- Chạy thử consumer truyền thống bằng `-cp`/`--class-path`.
- Đảm bảo các dependency và resource cần thiết xuất hiện trong cả hai chế độ.
- Không dựa vào việc JPMS giấu package nội bộ như biện pháp bảo mật dữ liệu; classpath cho phép truy cập theo các quy tắc khác.

Một thiết kế API sạch vẫn hữu ích cho classpath consumer, nhưng lớp bảo vệ module mạnh nhất hiện diện khi ứng dụng chạy dưới dạng named modules.

### 8.2. Maven hoặc Gradle

Đặt `module-info.java` ở `src/main/java/module-info.java`, các lớp ở namespace package tương ứng. Với Maven, có thể đặt:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Sử dụng phiên bản plugin compiler hỗ trợ dự án modular và kiểm tra output JAR. Với Gradle, cấu hình Java toolchain và Java module path phù hợp. Chỉ thêm `Automatic-Module-Name` vào manifest khi bạn chủ động phát hành **JAR chưa có descriptor** để ổn định tên automatic module; nó không thay thế `module-info.java` của explicit named module.

### 8.3. Dependency chưa modular hóa

JAR không có descriptor đặt trên module path có thể được coi là **automatic module**. Tên có thể đến từ manifest `Automatic-Module-Name` hoặc được suy ra từ filename; tên suy ra dễ thay đổi theo cách đóng gói. Dùng `jar --describe-module --file <dependency.jar>` để xem tên trước khi khai báo `requires`.

Nếu dependency vẫn ở classpath, nó thuộc unnamed module; một explicit named module không thể chỉ viết `requires` để đọc unnamed module như đọc named module khác. Đưa dependency phù hợp lên module path, dùng bản đã modular hóa, hoặc tổ chức adapter/compatibility layer theo nhu cầu; tránh dựa vào các JVM flag ngoại lệ trong API được phát hành rộng rãi.

### 8.4. Java 8 và multi-release JAR

Đặt `module-info.class` ở root JAR khiến cách build thông thường cần JDK 9+ để tạo descriptor. Nếu phải hỗ trợ Java 8, có thể cân nhắc **multi-release JAR**: bytecode ứng dụng tương thích Java 8 ở root, descriptor dành cho Java 9+ tại `META-INF/versions/9/module-info.class`, kèm manifest `Multi-Release: true`. Đây là chiến lược đóng gói riêng, cần kiểm tra thực tế trên cả JDK 8 và phiên bản JDK hỗ trợ; không nên chọn nếu thư viện chỉ nhắm JDK 17+.

## 9. API evolution: những quyết định khó đảo ngược

Khi một thư viện đã công khai named module, API contract gồm nhiều lớp:

| Thành phần thay đổi | Tác động có thể xảy ra |
| --- | --- |
| Đổi tên `module` | Consumer phải sửa `requires`, module launch và cấu hình build |
| Bỏ `exports` hoặc đổi package | Consumer ở module khác mất quyền truy cập source/binary |
| Đổi public method/constructor/type | Có thể phá source compatibility hoặc binary compatibility |
| Thêm kiểu dependency vào chữ ký API | Có thể cần `requires transitive` và dependency runtime rõ ràng |
| Bỏ service interface hoặc thay đổi SPI | Plugin provider của bên thứ ba có thể không còn tải/chạy |
| Tạo split package trong dependency graph | Có thể khiến module resolution/compilation thất bại |
| Mở thêm package bằng `opens` | Tăng bề mặt reflection và mức độ phụ thuộc vào framework |

Một chiến lược hợp lý là giữ **facade/interface ổn định** ở package export và thay đổi implementation trong package kín. Xem tên module và exported package là hợp đồng công khai, có versioning/release notes thích hợp. Semantic Versioning có thể là quy ước phát hành, nhưng JPMS không tự giải quyết chọn phiên bản hoặc cho phép hai version cùng tên module trong một layer.

Đối với annotation processor, reflection framework, serializer hay test framework, kiểm tra khả năng tương thích thực tế của từng dependency; đừng quyết định `opens` chỉ từ việc framework “có dùng reflection”.

## 10. Kiểm chứng kỹ thuật trước khi xuất bản

### 10.1. Kiểm tra descriptor và phụ thuộc

```powershell
jar --describe-module --file out/com.example.greetings.jar
jdeps --module-path out/com.example.greetings.jar --check com.example.greetings
```

`jar --describe-module` xác nhận artifact có descriptor, tên module và directives như kỳ vọng. `jdeps --check` giúp nhìn đồ thị dependency và những quan hệ đáng cân nhắc; nó không thay thế phép thử tích hợp.

### 10.2. Kiểm tra consumer biên dịch và thực thi

Duy trì project consumer nhỏ, độc lập với source của thư viện. Trên module path, xác nhận:

1. Module consumer chỉ cần `requires com.example.greetings;` cho API công khai thuần Java của ví dụ.
2. Import `com.example.greetings.api.Greetings` biên dịch, chạy và in ra nội dung mong đợi.
3. Import package `internal` bị từ chối ở biên dịch, thể hiện encapsulation.
4. Nếu có reflection hoặc provider, tải/khởi tạo thực tế trên module path; kiểm tra cả đường đi khi thiếu dependency optional.
5. Chạy song song thử nghiệm classpath nếu thư viện cam kết hỗ trợ ứng dụng chưa modular hóa.

Đối với JUnit, integration test hoặc Mockito/Byte Buddy có thể cần cấu hình module path, `--patch-module` hay `--add-opens` **trong môi trường test**; không mặc định suy ra cần mở cùng quyền trong artifact công khai.

### 10.3. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Khả năng nguyên nhân | Cách xử lý hướng thiết kế |
| --- | --- | --- |
| `package ... is not visible` | API chưa export hoặc consumer chưa đọc đúng module | Kiểm tra `exports` và `requires` |
| `module not found: ...` | Dependency/module path sai hoặc dùng sai tên automatic module | Xem `jar --describe-module`, đường dẫn và tên thực |
| `java.lang.reflect.InaccessibleObjectException` | Framework cần deep reflection nhưng package chưa mở | Dùng qualified `opens` đúng package/module nếu hợp đồng cho phép |
| `ServiceConfigurationError` | Provider không hợp lệ, thiếu class/dependency, chưa resolve module | Kiểm tra `uses`/`provides`, constructor/provider factory, resolution |
| `package is accessible from more than one module` | Split package giữa các module được phân giải | Tái tổ chức namespace hoặc dependency |
| API compile nhưng runtime lỗi liên quan dependency | Dependency optional/automatic/module resolution chưa được thử đủ | Rà soát module path và đường thực thi runtime |

Các thông báo cụ thể khác nhau theo JDK và tình huống; đọc cả nguyên nhân gốc của stack trace trước khi chọn giải pháp.

## 11. Checklist thiết kế cho tác giả thư viện

Trước khi phát hành, tự xác nhận:

- **Tên ổn định:** module name mang tính lâu dài, không phụ thuộc tên JAR có version.
- **API có chủ đích:** chỉ export package cần được người dùng gọi; không ép consumer import `internal`.
- **Chữ ký rõ ràng:** public API không vô tình phơi ra kiểu implementation và dependency bị giấu.
- **Dependency đúng:** khai báo `requires`, `requires transitive`, `requires static` theo tình huống; tránh transitive tùy tiện.
- **Reflection tối thiểu:** chỉ `opens` package cần thiết; chỉ định module đích khi có thể.
- **SPI đúng hợp đồng:** interface đủ ổn định, provider được phân giải, có chiến lược lựa chọn nếu nhiều provider.
- **Packaging được xác minh:** modular JAR chứa đúng descriptor; tên automatic dependency không bị đoán sai.
- **Tương thích được thử:** consumer trên module path và classpath hoạt động theo các chế độ thư viện công bố.
- **Phát hành có kiểm soát:** mọi thay đổi module name, exports, dependencies và public types được xem xét như thay đổi API.

## 12. Bài tập tự thực hành

Mở rộng ví dụ theo ba bước: (1) tạo interface `GreetingStyle` ở package `api` và cài đặt trong `internal`; (2) tạo một module consumer mới gọi API, thử import trực tiếp implementation nội bộ và quan sát lỗi biên dịch; (3) thêm `GreetingProvider` ở package `spi`, khai báo `uses`/`provides` và chạy consumer với một provider module ngoài. Khi mỗi bước chạy được, mô tả module nào đọc module nào, package nào export và package nào chỉ mở cho reflection (nếu có).

**Điểm cần nhớ:** named module của thư viện công khai là một **hợp đồng API và dependency**. Thiết kế từ boundary và consumer trước, sau đó để `module-info.java` phản ánh chính xác hợp đồng đó.