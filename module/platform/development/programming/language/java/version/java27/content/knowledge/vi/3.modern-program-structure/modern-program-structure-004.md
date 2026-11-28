# Package, import kiểu dữ liệu và quy tắc đặt tên

Trong Java, package tổ chức các kiểu dữ liệu thành những không gian tên có cấu trúc; `import` giúp mã nguồn tham chiếu kiểu hoặc thành viên bằng tên ngắn; quy tắc đặt tên giúp dự án tránh xung đột và giữ mã dễ đọc. Ba khái niệm này liên quan với nhau nhưng có vai trò riêng: package xác định nơi một kiểu được khai báo, import hỗ trợ cách viết tên trong một file nguồn, còn quy ước đặt tên giúp con người và công cụ nhận diện cấu trúc chương trình.

Bài viết bám theo Java Language Specification (JLS) của Java SE 27. Các ví dụ dùng cú pháp đã là tính năng chuẩn trong Java 27; đặc biệt, `import module` đã trở thành tính năng chính thức từ Java 25, không còn là preview.

## 1. Package là gì?

Package là không gian tên dùng để nhóm các class, interface, enum, record và các kiểu cấp cao nhất có liên quan. Một kiểu có tên đầy đủ (fully qualified name) gồm tên package và tên kiểu, phân tách bằng dấu chấm.

Ví dụ, kiểu `Order` trong package `com.example.billing` có tên đầy đủ là `com.example.billing.Order`. Một package khác vẫn có thể khai báo kiểu `Order`; hai kiểu không trùng nhau vì tên đầy đủ của chúng khác nhau.

Package mang lại các lợi ích sau:

- **Tổ chức mã nguồn:** nhóm các kiểu theo miền nghiệp vụ hoặc trách nhiệm, chẳng hạn `billing`, `customer`, `inventory`.
- **Tránh trùng tên:** hai package khác nhau có thể chứa các kiểu cùng tên đơn giản như `Order` hoặc `Date`.
- **Kiểm soát truy cập:** thành viên không có modifier truy cập (package-private) chỉ có thể được truy cập từ các kiểu thuộc cùng package, nếu các điều kiện truy cập khác cũng thỏa mãn.
- **Tạo ranh giới API:** khi dùng Java Platform Module System, module có thể chỉ export những package tạo thành API công khai.

Một package con là một package độc lập. Ví dụ `com.example.billing` và `com.example.billing.internal` có tên liên quan về mặt cấu trúc, nhưng không có quan hệ kế thừa quyền truy cập. Class package-private trong `com.example.billing` không tự động truy cập được từ `com.example.billing.internal`.

## 2. Khai báo package trong file Java

Với một ordinary compilation unit, khai báo `package` xác định package của các kiểu cấp cao nhất được khai báo trong file đó. Nếu có khai báo package, nó xuất hiện trước các khai báo `import` và các khai báo kiểu.

```java
package com.example.billing;

import java.math.BigDecimal;

public record Invoice(String number, BigDecimal total) {
}
```

Trong ví dụ này, tên đầy đủ của record là `com.example.billing.Invoice`. `BigDecimal` được dùng qua tên đơn giản vì đã được import.

Một dự án có thể sắp xếp source directory theo cấu trúc package quen thuộc:

```text
src/main/java/
└── com/
    └── example/
        └── billing/
            ├── Invoice.java
            ├── InvoiceService.java
            └── internal/
                └── InvoiceNumberGenerator.java
```

Trong các build tool và compiler dùng file system, đường dẫn thư mục thường phản ánh các thành phần package: `com.example.billing` tương ứng với `com/example/billing`. Đây là cách tổ chức phổ biến và dễ quản lý. Về mặt đặc tả ngôn ngữ, host system quyết định cách lưu trữ và ánh xạ compilation unit; package không phải là một lệnh đọc thư mục ở runtime.

Nếu file nguồn không khai báo `package`, các khai báo của nó thuộc unnamed package. Unnamed package tiện cho ví dụ nhỏ, thử nghiệm hoặc chương trình tạm thời. Một chương trình được tổ chức thành nhiều package nên dùng named package; kiểu trong unnamed package không thể được import vào một named package theo quy tắc import kiểu thông thường.

### Package và quyền truy cập

```java
// File: com/example/billing/InvoiceRules.java
package com.example.billing;

final class InvoiceRules {
    static boolean isValid(String number) {
        return number != null && !number.isBlank();
    }
}
```

`InvoiceRules` không có modifier `public`, vì vậy đây là kiểu package-private. Các kiểu trong `com.example.billing` có thể truy cập nó nếu thỏa mãn các quy tắc khác. Một kiểu thuộc `com.example.billing.internal` không thể truy cập `InvoiceRules` chỉ vì package của nó có cùng tiền tố.

Với một module có tên, `public` cũng chưa chắc đủ để cho phép module khác sử dụng kiểu. Package chứa kiểu đó phải được module export. Ví dụ:

```java
// File: module-info.java
module com.example.billing {
    exports com.example.billing.api;
}
```

Chỉ package `com.example.billing.api` được export trong khai báo này. Những package khác của module vẫn có thể được dùng nội bộ nhưng không trở thành API truy cập thông thường của module khác. `exports` là quy tắc ở mức module; nó không thay thế modifier truy cập của class và member.

## 3. `import` kiểu dữ liệu

Khai báo `import` cho phép dùng tên đơn giản của class hoặc interface từ package khác, hoặc của thành viên `static` từ một class/interface khác. Import chỉ có hiệu lực trong compilation unit chứa nó. Việc import không sao chép mã, không khởi tạo đối tượng và không làm thay đổi dependency runtime.

Các kiểu trong cùng package có thể được tham chiếu bằng tên đơn giản mà không cần import. Các kiểu `public` trong package `java.lang` cũng được import ngầm trong ordinary compilation unit, vì vậy thường có thể viết `String`, `Object`, `Math` mà không cần `import java.lang.*;`.

Với compact compilation unit (cú pháp source file gọn đã trở thành tính năng chuẩn từ Java 25), quy tắc ngầm import rộng hơn: JLS 27 xem như có `import module java.base;` ở đầu file. Không áp dụng quy tắc riêng này cho ordinary compilation unit thông thường.

### 3.1. Import một kiểu cụ thể

```java
import java.time.LocalDate;
import java.util.List;

class Schedule {
    LocalDate startDate;
    List<String> participants;
}
```

Đây là single-type import. Mỗi khai báo chỉ định một class hoặc interface bằng tên đầy đủ. Kiểu được import có thể được dùng bằng tên đơn giản trong file hiện tại.

Import cũng có thể chỉ định một kiểu thành viên (nested type), ví dụ `import java.util.Map.Entry;`. Một package không phải là một kiểu, do đó `import java.util;` không phải cú pháp hợp lệ để import package.

### 3.2. Import theo package bằng `*`

```java
import java.time.*;

class Schedule {
    LocalDate startDate;
    LocalTime startTime;
}
```

Đây là type-import-on-demand. Dấu `*` làm các class và interface có thể truy cập được khai báo trực tiếp trong package trở nên khả dụng theo nhu cầu.

`import java.util.*;` không import các package con như `java.util.concurrent` hoặc `java.util.stream`. Nếu cần kiểu `Stream`, phải import `java.util.stream.Stream` hoặc dùng một khai báo import phù hợp với module chứa package đó. Dấu `*` không có nghĩa là quét đệ quy toàn bộ cây thư mục.

Import theo package không nhất thiết gây lỗi chỉ vì package khác cũng có một kiểu cùng tên. Tuy nhiên, nếu mã dùng tên đơn giản mà hai khai báo import đều có thể cung cấp kiểu đó, tên sẽ trở nên mơ hồ và cần được giải quyết. Khi hai single-type import cùng đưa vào một tên đơn giản nhưng trỏ tới hai kiểu khác nhau, compiler báo lỗi.

### 3.3. Static import

Static import cho phép gọi hoặc tham chiếu thành viên `static` bằng tên đơn giản. Có thể import một thành viên cụ thể:

```java
import static java.lang.Math.PI;
import static java.lang.Math.max;

class Circle {
    double circumference(double radius) {
        return 2 * PI * radius;
    }

    int larger(int first, int second) {
        return max(first, second);
    }
}
```

Hoặc import theo nhu cầu tất cả thành viên `static` có thể truy cập của một kiểu:

```java
import static java.util.Objects.*;

class Customer {
    String name;

    void validate() {
        requireNonNull(name, "name must not be null");
    }
}
```

Static import có thể áp dụng cho field, method và các kiểu thành viên `static`. Dùng import cụ thể thường giúp người đọc nhận ra nguồn gốc của tên ngắn. Dùng `import static SomeType.*;` quá rộng có thể khiến mã khó hiểu hoặc tạo ra tên mơ hồ khi dự án lớn lên.

### 3.4. Module import trong Java 27

Từ Java 25, module import là tính năng chính thức theo JEP 511. Cú pháp:

```java
import module java.base;

class CollectionExample {
    List<String> names = List.of("Ada", "Grace");
    Map<String, Integer> scores = Map.of("Java", 27);
}
```

Khai báo `import module java.base;` đưa vào phạm vi tên đơn giản của compilation unit các class và interface cấp cao nhất có thể truy cập trong những package được module `java.base` export. Vì `java.util` thuộc `java.base`, ví dụ có thể dùng `List` và `Map` mà không cần các import riêng cho từng package.

Module import không có nghĩa là import mọi kiểu trong mọi module của JDK. Nó áp dụng cho các kiểu `public` cấp cao nhất thuộc package mà module được chỉ định export cho module hiện tại, cùng các package được export bởi những module mà module hiện tại đọc được thông qua module đó. Kiểu không `public`, package không export hoặc module không đọc được không trở nên khả dụng chỉ nhờ câu lệnh này.

Trong dự án modular, `requires` và `import module` giải quyết hai việc khác nhau:

- `requires java.sql;` trong `module-info.java` khai báo module hiện tại phụ thuộc và đọc module `java.sql`.
- `import module java.sql;` trong file nguồn cho phép dùng tên đơn giản của các kiểu được export từ module đó.

Ví dụ:

```java
// File: module-info.java
module com.example.reporting {
    requires java.sql;
}
```

```java
// File: com/example/reporting/DatabaseReport.java
package com.example.reporting;

import module java.sql;

final class DatabaseReport {
    Connection connection;
}
```

Module import không thay thế khai báo `requires`. JLS cũng cho phép dùng module import trong source file không thuộc named module, miễn là module được import có thể được đọc trong ngữ cảnh biên dịch đó.

Một module có thể export nhiều package có các kiểu cùng tên đơn giản. Khi đó, module import có thể khiến một tham chiếu như `Element` trở nên mơ hồ. Hãy dùng single-type import hoặc tên đầy đủ để chỉ rõ kiểu cần dùng. Khi muốn import toàn bộ API Java SE, module `java.se` có thể được dùng trong môi trường đã đưa module này vào module graph; với một số cách chạy classpath cần bật root module bằng `--add-modules java.se`.

### 3.5. Phạm vi và cách giải quyết tên

Import chỉ áp dụng cho file đang chứa nó. Ví dụ `InvoiceService.java` import `java.time.Instant` không làm cho `Invoice.java` trong cùng package tự động có thể dùng tên `Instant`.

Khi hai kiểu có cùng tên đơn giản, dùng tên đầy đủ cho ít nhất một kiểu:

```java
class DateConverter {
    java.util.Date legacyDate;
    java.sql.Date databaseDate;
}
```

Ví dụ này dùng hai kiểu `Date` khác nhau mà không cần import cả hai dưới cùng tên đơn giản. `java.sql.Date` vẫn là API Java SE hiện hành; tiền tố `javax` hoặc `java.sql` không tự động cho biết một API đã lỗi thời. Hãy xác định trạng thái của chính API cụ thể thay vì kết luận chỉ từ tiền tố package.

## 4. Quy tắc hợp lệ của identifier

Tên package, class, interface, record, enum, method, field và biến được hình thành từ identifier theo quy tắc của ngôn ngữ. Java phân biệt chữ hoa và chữ thường, vì vậy `Order`, `order` và `ORDER` là ba tên khác nhau.

Theo JLS:

- Ký tự đầu tiên của identifier phải là một Java letter.
- Các ký tự tiếp theo có thể là Java letter hoặc Java digit.
- Java letter bao gồm các chữ cái Unicode; vì thế ngôn ngữ cho phép identifier dùng nhiều hệ chữ.
- Identifier không được trùng reserved keyword, boolean literal (`true`, `false`) hoặc null literal (`null`).
- Dấu `$` được chấp nhận về mặt cú pháp nhưng nên dành cho mã được sinh tự động hoặc tình huống tương thích đặc biệt.
- Dấu gạch dưới `_` là keyword riêng lẻ từ Java 9. Java hiện cho phép `_` làm tên biến cục bộ, tham số lambda hoặc tham số `catch` không sử dụng trong những ngữ cảnh khai báo unnamed variable được quy định, nhưng không thể dùng `_` làm tên package, class hoặc identifier thông thường.

Một số từ như `record`, `sealed`, `permits`, `var` và `yield` là contextual keyword. Chúng được hiểu như keyword trong ngữ cảnh cú pháp tương ứng; riêng quy tắc `TypeIdentifier` không cho phép dùng các từ này làm tên class, interface hoặc type parameter. Khi đặt tên kiểu, hãy tránh các từ khóa và contextual keyword để mã dễ đọc, ít phụ thuộc ngữ cảnh.

Ví dụ:

```java
class OrderItem {          // Hợp lệ
    private String itemId; // Hợp lệ
    private int quantity;  // Hợp lệ
}
```

```java
class record { } // Không hợp lệ: record không phải TypeIdentifier
class _ { }      // Không hợp lệ: _ là keyword
```

Unicode trong identifier hợp lệ theo đặc tả, nhưng với dự án nhiều nhóm, nhiều hệ điều hành hoặc nhiều công cụ, nên thống nhất cách viết tên bằng ký tự Latin ASCII để dễ tìm kiếm, review và tích hợp. Đây là quy ước của dự án, không phải giới hạn cú pháp của Java.

## 5. Quy ước đặt tên package, kiểu và thành viên

Compiler kiểm tra identifier có hợp lệ hay không, nhưng phần lớn quy tắc đặt tên dưới đây là convention nhằm giúp code nhất quán. JLS §6.1 khuyến nghị các convention này cho chương trình Java.

| Thành phần | Quy ước thường dùng | Ví dụ |
| --- | --- | --- |
| Package | Chữ thường; với thư viện hoặc ứng dụng phân phối rộng, dùng tên miền đảo ngược làm tiền tố | `com.example.billing`, `org.example.catalog` |
| Module | Tên có tính duy nhất, thường tương ứng package API chính và dùng tiền tố tên miền đảo ngược | `com.example.billing` |
| Class | UpperCamelCase; danh từ hoặc cụm danh từ mô tả trách nhiệm | `InvoiceService`, `PaymentRequest` |
| Interface | UpperCamelCase; tên mô tả vai trò hoặc khả năng | `PaymentGateway`, `Closeable` |
| Record | UpperCamelCase; danh từ mô tả dữ liệu | `InvoiceLine`, `CustomerAddress` |
| Enum | UpperCamelCase; tên mô tả nhóm trạng thái hoặc lựa chọn | `InvoiceStatus`, `PaymentMethod` |
| Annotation interface | UpperCamelCase; tên mô tả ý nghĩa metadata | `Audited`, `Retryable` |
| Method | lowerCamelCase; thường là động từ hoặc cụm động từ | `calculateTotal()`, `findById()` |
| Field, local variable, parameter | lowerCamelCase; danh từ hoặc cụm danh từ có ý nghĩa | `createdAt`, `customerName` |
| Constant | UPPER_SNAKE_CASE cho hằng số được quy ước của class | `MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT` |
| Enum constant | UPPER_SNAKE_CASE | `PENDING`, `PAID`, `CANCELLED` |
| Type parameter | Một chữ in hoa khi tên kiểu tổng quát; dùng ký hiệu có nghĩa theo vai trò | `T`, `E`, `K`, `V` |

Với package được phát hành cho bên ngoài, JLS đề xuất dùng domain của tổ chức theo thứ tự đảo ngược để giảm nguy cơ trùng tên. Ví dụ tổ chức sở hữu `example.com` có thể dùng tiền tố `com.example`. Tên miền chỉ là cơ sở tạo namespace duy nhất; nó không có nghĩa package phải được tải từ máy chủ web có cùng tên.

Thành phần đầu tiên của tên package hoặc module không được là identifier `java`; namespace bắt đầu bằng `java` được dành riêng cho Java SE Platform. Không tạo package hoặc module ứng dụng như `java.example`; hãy dùng namespace của tổ chức như `com.example` hoặc `org.example`.

Các quy tắc thực hành:

1. Chọn tên package theo miền nghiệp vụ hoặc ranh giới thành phần, không theo tên cá nhân hay máy phát triển.
2. Giữ tên package viết thường để phân biệt trực quan với tên kiểu.
3. Dùng tên class/interface cụ thể, có ý nghĩa; tránh tên chung chung như `Data`, `Manager`, `Helper` nếu không mô tả được trách nhiệm.
4. Đặt tên method theo hành động; tên boolean thường có thể bắt đầu bằng `is`, `has` hoặc `can`.
5. Dùng tên biến mô tả giá trị mà nó giữ; chỉ dùng tên một ký tự cho biến đếm hoặc phạm vi rất ngắn khi ý nghĩa đã rõ.
6. Chỉ dùng UPPER_SNAKE_CASE cho hằng số theo convention; không phải mọi biến `final` đều là constant. Một reference `final` vẫn có thể trỏ tới object mutable.
7. Dùng formatter và quy tắc import thống nhất của repository để sắp xếp import; thứ tự import không làm thay đổi ý nghĩa chương trình.

## 6. Ví dụ tổng hợp

Ví dụ dưới đây kết hợp package, import kiểu, static import, record và quy ước đặt tên:

```java
package com.example.billing;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import static java.util.Objects.requireNonNull;

public record Invoice(
        String number,
        BigDecimal total,
        Instant createdAt,
        List<String> itemIds) {

    public Invoice {
        requireNonNull(number, "number");
        requireNonNull(total, "total");
        requireNonNull(createdAt, "createdAt");
        itemIds = List.copyOf(requireNonNull(itemIds, "itemIds"));
    }
}
```

Có thể đọc cấu trúc này như sau:

- `com.example.billing` là package của record `Invoice`.
- `BigDecimal`, `Instant` và `List` được import theo từng kiểu cụ thể.
- `requireNonNull` là static method được import từ `java.util.Objects`.
- `Invoice` dùng UpperCamelCase; các component `number`, `total`, `createdAt`, `itemIds` dùng lowerCamelCase.
- `List.copyOf` tạo danh sách không sửa đổi được từ đầu vào, tránh giữ trực tiếp một danh sách mutable do caller truyền vào.

Nếu một file khác trong cùng package cần dùng `Invoice`, nó có thể tham chiếu `Invoice` mà không phải import. Nếu file thuộc package khác, kiểu `Invoice` cần được truy cập hợp lệ (ở đây record là `public`) và được import hoặc tham chiếu bằng tên đầy đủ. Nếu package `com.example.billing` nằm trong named module và được module khác sử dụng, module sở hữu nó còn phải export package đó.

## 7. Lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Viết `import java.util;` | Import type cần chỉ định kiểu hoặc dùng `.*` cho import-on-demand | Dùng `import java.util.List;` hoặc `import java.util.*;` |
| Nghĩ `import java.util.*;` bao gồm `java.util.stream` | Import theo package không đệ quy vào package con | Import `java.util.stream.Stream` hoặc dùng module import thích hợp |
| File A import một kiểu nhưng file B cùng package vẫn không nhận ra tên ngắn | Import chỉ có phạm vi trong compilation unit chứa nó | Thêm import cần thiết vào file B hoặc dùng tên đầy đủ |
| Import hai kiểu cùng tên đơn giản | Hai tên không thể được phân biệt qua cùng một simple name | Chỉ import một kiểu và dùng tên đầy đủ cho kiểu còn lại |
| Class ở package con không truy cập được member package-private | Package con là package độc lập | Chuyển kiểu vào cùng package, thay đổi API có chủ đích hoặc thiết kế lại ranh giới |
| `import module` nhưng compiler báo module không đọc được | Module import không tạo dependency trong module graph | Khai báo `requires` phù hợp trong `module-info.java` hoặc cấu hình module path/module graph |
| Import được một kiểu nhưng vẫn báo không truy cập được | Import không vượt qua modifier truy cập hoặc ranh giới `exports` | Kiểm tra `public`, package export và module readability |
| Dùng `_` làm tên biến thông thường | `_` là keyword dành cho khai báo unnamed variable ở các ngữ cảnh được phép | Đặt tên có ý nghĩa như `unusedValue` hoặc dùng `_` đúng ngữ cảnh unnamed variable |

## 8. Checklist khi tạo package và import

- Chọn package theo miền nghiệp vụ hoặc thành phần, dùng namespace duy nhất cho thư viện được phân phối rộng.
- Đặt khai báo package nhất quán trong mọi file thuộc cùng package.
- Dùng named package cho mã ứng dụng có cấu trúc; để unnamed package cho thử nghiệm nhỏ.
- Chọn single-type import khi muốn thể hiện rõ dependency; dùng wildcard hoặc module import khi phạm vi được hiểu rõ và phù hợp với quy ước dự án.
- Nhớ rằng package wildcard không import package con và import không chia sẻ giữa các file.
- Kiểm tra modifier truy cập và `exports` khi một kiểu được dùng từ package hoặc module khác.
- Dùng identifier hợp lệ và tuân thủ convention thống nhất cho package, kiểu, method, field, constant và type parameter.
- Dùng tên đầy đủ khi cần loại bỏ mơ hồ giữa các kiểu cùng tên.

## Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 27 — Chapter 3: Lexical Structure](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-3.html) — identifier, Unicode, reserved keyword và contextual keyword.
- [Java Language Specification, Java SE 27 — Chapter 6: Names](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-6.html) — tên đầy đủ, phạm vi, quy ước đặt tên package, module, class, method, field và type parameter.
- [Java Language Specification, Java SE 27 — Chapter 7: Packages and Modules](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-7.html) — package declaration, unnamed package, import declaration, module import và module export.
- [Java Language Changes for Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html) — trạng thái tính năng ngôn ngữ theo từng bản phát hành.
- [JEP 511: Module Import Declarations](https://openjdk.org/jeps/511) — thiết kế và trạng thái chính thức của module import từ Java 25.
