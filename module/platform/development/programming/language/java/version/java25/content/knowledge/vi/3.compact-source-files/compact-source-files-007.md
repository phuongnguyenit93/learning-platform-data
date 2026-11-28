# Giới hạn về package, tổ chức mã và khả năng tái sử dụng của tệp nguồn gọn

## 1. Mục tiêu và phạm vi Java 25

Trong **JAVA_VERSION_JAVA25**, Java 25 cung cấp những khả năng vẫn phù hợp với phát triển Java hiện đại: tệp nguồn gọn, module import, hàm khởi tạo linh hoạt, `ScopedValue`, API dẫn xuất khóa, AOT cache và quan sát bằng JFR. Bài này tập trung vào một trong những cải tiến dễ tiếp cận nhất: **compact source files** (tệp nguồn gọn) và các giới hạn của chúng đối với **package**, **tổ chức mã** và **tái sử dụng**.

Theo **JEP 512 — Compact Source Files and Instance Main Methods**, tính năng này được **chính thức hóa trong Java 25**; không cần `--enable-preview` khi sử dụng cú pháp đã hoàn thiện. Những ví dụ preview và cách gọi cũ của Java 21–24 chỉ có giá trị lịch sử, không phải hướng dẫn nên ưu tiên trong dự án Java 25 mới.

Mục tiêu sau bài học:

- Biết khi nào một tệp `.java` được xem là **compact source file** và phân biệt nó với tệp Java thông thường.
- Giải thích vì sao tệp gọn **không khai báo `package`** và lớp được khai báo ngầm **không thể gọi bằng tên** trong Java source.
- Hiểu phạm vi của field, method và nested type trong tệp gọn; tránh ngộ nhận chúng là API cấp package.
- Biết cách tách helper tái sử dụng, nâng cấp chương trình thành **lớp tường minh thuộc named package**, và tổ chức build/test khi quy mô tăng.
- Chọn tệp gọn đúng ngữ cảnh: học tập, ví dụ nhỏ, tiện ích một lần, entry point thử nghiệm; không biến nó thành cấu trúc mặc định cho thư viện hoặc ứng dụng có nhiều module.

## 2. Compact source file thực chất là gì?

Một **compact source file** là đơn vị biên dịch Java có các khai báo method/field/member type trực tiếp sau phần `import` mà **không viết một khai báo `class` bao quanh**. Compiler vẫn tạo ra một **lớp top-level được khai báo ngầm** (implicitly declared class), chứa những thành viên đó.

Ví dụ lưu thành `Hello.java`:

```java
String greeting() {
    return "Xin chào Java 25";
}

void main() {
    IO.println(greeting());
}
```

Chạy trực tiếp bằng **JDK 25**:

```bash
java Hello.java
```

Kết quả:

```text
Xin chào Java 25
```

Mặc dù không thấy chữ `class`, hai method `greeting()` và `main()` là **instance methods của cùng lớp được khai báo ngầm**, không phải các hàm toàn cục. Java vẫn là ngôn ngữ định nghĩa hành vi bên trong class.

Lớp được khai báo ngầm có các đặc tính theo **JLS Java 25, mục 8.1.8**:

| Đặc tính | Ý nghĩa thực tế |
|---|---|
| Top-level class, `final` | Không thể kế thừa lớp được khai báo ngầm |
| Thuộc **unnamed package** | Không có tên package để định danh và import như API dự án |
| Quyền truy cập của lớp ở cấp package | Không phải một `public class` để các package bên ngoài dùng |
| Kế thừa trực tiếp `Object` | Không thể chỉ định `extends OtherBase` |
| Không khai báo `implements` | Không thể biến lớp ngầm thành một implementation public của interface |
| Có default constructor không tham số | Không được tự viết constructor khác |
| Tên lớp do host/compiler xác định | Không được tham chiếu lớp ngầm **bằng tên trong source code** |
| Phải có `main` phù hợp quy tắc khởi chạy | Tệp gọn hướng đến chương trình chạy được, không phải thư viện helper không entry point |
| Có thể chứa field, method và member type | Vẫn có cấu trúc class trong phạm vi tệp, nhưng không tự tạo public API tái sử dụng |

Compiler `javac` thường chọn tên file bỏ đuôi `.java` để đặt tên class file, chẳng hạn `Hello.class`. Đây là **chi tiết triển khai** phục vụ compile/launch; **không** có nghĩa viết `new Hello()` trong Java source là hợp lệ.

Nguồn chuẩn: [JLS Java 25 — Compilation Units `7.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.3), [JLS — Implicitly Declared Classes `8.1.8](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.8).

## 3. Giới hạn về package: không có `package com.example`

### 3.1. Tệp gọn luôn thuộc unnamed package

Một tệp compact compilation unit **không có `package` declaration**. JLS Java 25 định nghĩa nó là một kiểu compilation unit riêng:

```text
CompilationUnit
  ├─ OrdinaryCompilationUnit
  ├─ CompactCompilationUnit
  └─ ModularCompilationUnit
```

Trong khi ordinary compilation unit cho phép một `package` declaration tùy chọn, compact compilation unit chỉ gồm **import declarations** và **class member declarations**, trong đó phải có ít nhất một method declaration và lớp ngầm phải có candidate `main`.

Ví dụ **không hợp lệ**:

```java
// Sai: package declaration không thuộc cú pháp của compact source file.
package com.example.scripts;

void main() {
    IO.println("Không thể đặt compact source vào named package");
}
```

Muốn tệp thuộc `com.example.scripts`, cần viết một **lớp tường minh**:

```java
package com.example.scripts;

public final class App {
    void main() {
        IO.println("Đây là lớp có tên thuộc named package");
    }
}
```

Java 25 cũng cho phép **instance main trong một lớp có tên**, vì vậy việc chuyển sang ordinary class **không nhất thiết phải quay lại `public static void main(String[] args)`** nếu đang chạy trên Java 25. Chỉ việc thêm `class App { ... }` và chuyển các member vào trong lớp đã làm rõ identity của entry point.

### 3.2. Unnamed package không phải named package rỗng

**Unnamed package** là khái niệm đã có từ lâu trong Java; nó giúp chạy các chương trình nhỏ không cần định danh namespace. Tệp Java thông thường cũng có thể ở unnamed package:

```java
// Helper.java — ordinary compilation unit trong unnamed package.
final class Helper {
    static String format(String input) {
        return input.strip().toUpperCase();
    }
}
```

Điểm khác biệt:

- `Helper.java` **không** phải compact source file, vì nó chỉ chứa khai báo lớp tường minh `Helper`.
- Một tệp khác không có `package` có thể sử dụng `Helper` khi ở cùng unnamed package theo cách compiler/source-path nhận diện.
- Ngược lại, code thuộc **named package** không thể import/reference trực tiếp các class trong unnamed package bằng cách thông thường.

Đừng coi việc xếp các file cạnh nhau trong một thư mục như một chiến lược đóng gói thư viện Java nghiêm túc. Đối với dự án cần namespace bền vững, nên đặt API trong named package ngay khi xuất hiện nhu cầu chia sẻ code.

### 3.3. Unnamed module và JPMS không giúp “đặt tên” lớp ngầm

Các class không nằm trong module có tên thường thuộc **unnamed module**. Compact source file nằm trong unnamed package của unnamed module; điều này **không tạo ra** một package exportable để ứng dụng JPMS khác gọi các member của lớp ngầm.

Cần phân biệt:

- `import module java.base;` là cú pháp **module import declaration** của Java 25, dùng để import các public types được module `java.base` export.
- Compact source file **tự có import-on-demand tương đương `import module java.base;`**.
- Import module chỉ giúp viết ngắn **tên type** (`List`, `Map`, `Path`...), **không** đổi package của lớp ngầm và **không** làm class ấy trở thành public API.

Điều này rất quan trọng khi đem ví dụ nhỏ vào dự án dùng `module-info.java`: chỉ sửa imports không thể thay thế bước thiết kế named packages và exported APIs.

## 4. Giới hạn về tên lớp, constructor và interface

Hãy xem tệp `CounterDemo.java`:

```java
int value = 0;

void increment() {
    value++;
}

void main() {
    increment();
    IO.println("value=" + value);
}
```

Trong `main()`, có thể gọi `increment()` và dùng `value` vì đó là các member của **đối tượng lớp ngầm hiện tại**. Có thể dùng `this.increment()` hoặc method reference như `this::increment` trong ngữ cảnh instance phù hợp.

Nhưng những cách sau **không hợp lệ** để tạo ra API:

```java
// Sai: lớp ngầm không nằm trong scope để được tham chiếu bằng tên.
void main() {
    CounterDemo another = new CounterDemo();  // lỗi compile
    another.increment();
}
```

Cũng không thể viết constructor `CounterDemo() { ... }` trong compact source file, khai báo `extends`, `implements` hay annotation trên chính declaration của implicit class. Khi cần inject dependency qua constructor, implement interface, cấu hình inheritance hoặc công bố type cho framework, **dùng lớp tường minh**.

### Lưu ý: instance main là tính năng độc lập với compact source

Trong Java 25, có thể viết:

```java
package com.example.cli;

public class Main {
    void main(String[] args) {
        IO.println("Xin chào " + (args.length == 0 ? "bạn" : args[0]));
    }
}
```

Ở đây là **ordinary compilation unit** vì có `package` và `public class Main`, dù entry point là **instance main**. Không nên đồng nhất “có `void main()`” với “phải là tệp nguồn gọn”. Đó là hai khả năng được chuẩn hóa cùng JEP 512 nhưng dùng độc lập tùy hoàn cảnh.

## 5. Giới hạn về tổ chức mã và các thành viên trong tệp

### 5.1. Các khai báo trực tiếp thuộc implicit class

Trong compact source file, sau imports có thể viết:

- **Fields:** ví dụ `int total = 0;`.
- **Methods:** ví dụ `int calculate(int n)`, `void main()`, `static String label()`.
- **Member classes/interfaces/records/enums** ở vị trí khai báo member, ví dụ `record Item(...) {}`.
- Method và field access modifiers phù hợp với quy tắc class member.

Không được khai báo **constructor**, **instance initializer** hoặc **static initializer block** trực tiếp cho implicit class. Đây là giới hạn cụ thể của grammar, không chỉ là lời khuyên về style.

Ví dụ hợp lệ, tệp `Basket.java`:

```java
// List được tự import từ java.base trong compact source file.
record Item(String sku, int quantity) {}

List<Item> sampleItems() {
    return List.of(new Item("BOOK", 2), new Item("PEN", 3));
}

int totalQuantity(List<Item> items) {
    return items.stream().mapToInt(Item::quantity).sum();
}

void main() {
    IO.println("Tổng số lượng: " + totalQuantity(sampleItems()));
}
```

`Item` trong ví dụ là **nested record của implicit class**, không phải public top-level record có thể được import từ các package khác. Nếu `Item` trở thành data transfer object dùng chung, hãy tách nó thành một **`public record Item` trong named package**.

### 5.2. Một file không có khả năng “export method” toàn cục

Giả sử có tệp `Pricing.java`:

```java
int doublePrice(int price) {
    return price * 2;
}

void main() {
    IO.println(doublePrice(10));
}
```

Bạn **không thể** coi `doublePrice` là “hàm toàn cục Java” rồi gọi trong mọi tệp bằng `Pricing.doublePrice(...)`, vì `Pricing` là tên được dùng cho class file, không phải type name được phép tham chiếu từ Java source.

Cố đặt hàng chục utility methods vào một compact file rồi mong các file khác reuse sẽ dẫn tới coupling khó quản lý, thiếu API boundaries và thiếu nơi tạo instance công khai. Cách đúng là **tách utility/service** thành named class.

### 5.3. Không thể bỏ `main` để tạo một compact library file

Ví dụ sau **không hợp lệ với ý định dùng compact source file**:

```java
// Sai: lớp ngầm không có candidate main.
int square(int n) {
    return n * n;
}
```

Lớp ngầm phải khai báo một candidate `main` theo JLS. Nếu muốn một helper thuần túy, dùng ordinary class:

```java
package com.example.math;

public final class Squares {
    private Squares() {}

    public static int square(int n) {
        return Math.multiplyExact(n, n);
    }
}
```

`Math.multiplyExact` còn giúp phát hiện overflow thay vì âm thầm trả về một số sai trong ví dụ tính toán số nguyên. Đây là một helper bình thường, có tên và package để các thành phần khác có thể import, test và reuse.

## 6. Import của Java 25: tiện cho entry point, không thay cho kiến trúc

Trong Java 25, mọi compact source file **tự import** các public top-level types thuộc các packages mà module `java.base` export. Vì vậy có thể viết:

```java
void main() {
    List<String> names = List.of("An", "Bình", "Chi");
    var normalized = names.stream()
            .map(String::strip)
            .toList();

    IO.println(normalized);
}
```

Không cần viết `import java.util.List;` cho ví dụ này. Trong một ordinary source file, muốn dùng `List` mà không viết fully qualified name thì cần `import java.util.List;` hoặc `import module java.base;` (Java 25).

**Các giới hạn quan trọng:**

1. Import tự động chỉ áp dụng cho các **public top-level types trong các package exported bởi `java.base`**; không tự động import toàn bộ thư viện chuẩn như `java.sql`, `java.net.http` hay `java.desktop`.
2. Các thư viện bên ngoài như Jackson hoặc client HTTP vẫn cần dependencies và imports bình thường.
3. Java 25 đặt `IO` ở `java.lang.IO`. Các static methods **không** được import ngầm: viết `IO.println(...)` hoặc chủ động `import static java.lang.IO.println;`. Không dùng ví dụ preview cũ chỉ gọi `println(...)` mà không có static import.
4. Auto import nhiều type đơn giản có thể làm xuất hiện **tên trùng/nhập nhằng** khi thêm modules/imports khác; xử lý bằng single-type import hoặc tên đầy đủ.
5. Import giúp code ngắn, nhưng không làm implicit class có package name, API công khai hoặc khả năng được xây dựng như named module.

Ví dụ cần `java.net.http`:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;

void main() {
    try (var client = HttpClient.newHttpClient()) {
        var request = HttpRequest.newBuilder(
                URI.create("https://example.com"))
                .GET()
                .build();
        IO.println(request.uri());
    }
}
```

Đây là ví dụ dùng type từ module `java.net.http` ở Java 25. Nó **không gửi network request**, chỉ xây request để minh họa import và API. Không suy rằng `java.net.http.HttpClient` được import tự động từ `java.base`; phần `import` ở đầu là cần thiết trừ khi chọn `import module java.net.http;` cùng điều kiện module readability phù hợp.

## 7. Tái sử dụng trong và ngoài một compact source file

Đánh giá ba cấp độ reuse:

| Cấp độ | Khả thi? | Khuyến nghị |
|---|---|---|
| Gọi method/field trong **cùng một compact file** | Có, như class members thông thường | Tốt cho demo, script và entry point nhỏ |
| Dùng **named helper class** từ compact file | Có, nếu helper có thể truy cập qua classpath/module và import hợp lệ | Tách business logic cần tái sử dụng sang named class |
| Tệp Java khác gọi member của **implicit class** | Không như một API đặt tên thông thường, vì implicit class không thể được tham chiếu bằng tên trong Java source | Chuyển sang explicit class có package rõ ràng |
| Dùng implicit class làm public service/interface implementation | Không, vì không có khai báo `implements` và class không public/named | Chuyển sang ordinary class |
| Tạo thư viện JAR có public API từ method trực tiếp của compact file | Không phải mô hình API phù hợp | Định nghĩa các public classes/interfaces/records riêng |
| Viết entry point ngắn gọi library có tên | Có, và là cách sử dụng tốt | Giữ file gọn chỉ làm orchestration |

### 7.1. Tách named helper dù entry point vẫn gọn

Ví dụ hai tệp cùng unnamed package trong thư mục thực hành.

`MoneyFormatter.java` (ordinary class):

```java
final class MoneyFormatter {
    private MoneyFormatter() {}

    static String formatVnd(long amount) {
        return String.format("%,d VND", amount);
    }
}
```

`InvoiceDemo.java` (compact source):

```java
void main() {
    IO.println(MoneyFormatter.formatVnd(125_000));
}
```

Có thể biên dịch và chạy bằng JDK 25:

```bash
javac MoneyFormatter.java InvoiceDemo.java
java InvoiceDemo
```

Điều này minh họa **compact file sử dụng named helper**. Nó **không** làm `InvoiceDemo` trở thành helper được import ngược từ project khác. Khi muốn reuse `MoneyFormatter` từ named packages, cần chuyển chính helper vào named package và thay đổi quyền truy cập theo API được công bố.

### 7.2. Dùng named package ngay khi chia sẻ qua nhiều module

Ví dụ chuyển formatter thành:

```java
// src/main/java/com/example/pricing/MoneyFormatter.java
package com.example.pricing;

import java.text.NumberFormat;
import java.util.Locale;

public final class MoneyFormatter {
    private MoneyFormatter() {}

    public static String formatVnd(long amount) {
        var formatter = NumberFormat.getNumberInstance(Locale.forLanguageTag("vi-VN"));
        return formatter.format(amount) + " VND";
    }
}
```

Compact entry point có thể sử dụng API đó nếu dependency được đưa vào classpath/module path phù hợp:

```java
// InvoiceDemo.java, compact source file
import com.example.pricing.MoneyFormatter;

void main() {
    IO.println(MoneyFormatter.formatVnd(125_000));
}
```

Đây là hướng tổ chức tốt hơn cho ứng dụng tăng trưởng:

- Lớp `MoneyFormatter` có **tên và package rõ ràng**, có thể import và kiểm thử độc lập.
- Entry point vẫn ngắn, chỉ gọi public API.
- Sau này có thể chuyển `InvoiceDemo` thành named class mà không cần thay logic formatter.
- Nếu dùng JPMS module có tên, `MoneyFormatter` phải nằm trong exported package và module consumer phải có `requires` thích hợp; đây là câu chuyện về module boundaries, không phải shortcut của compact files.

## 8. Lộ trình chuyển từ script gọn sang chương trình có cấu trúc

Giả sử ban đầu `Report.java` là compact source file:

```java
List<Integer> durations = List.of(120, 80, 100);

double average() {
    return durations.stream()
            .mapToInt(Integer::intValue)
            .average()
            .orElse(0.0);
}

void main() {
    IO.println("Thời gian trung bình: " + average() + " ms");
}
```

Khi cần thêm unit test, dependency injection hoặc chia module, có thể tiến từng bước.

**Bước A — chuyển sang lớp có tên, giữ nguyên hành vi:**

```java
package com.example.reporting;

import java.util.List;

public final class Report {
    private final List<Integer> durations = List.of(120, 80, 100);

    double average() {
        return durations.stream()
                .mapToInt(Integer::intValue)
                .average()
                .orElse(0.0);
    }

    void main() {
        IO.println("Thời gian trung bình: " + average() + " ms");
    }
}
```

Đây là ordinary class, có thể chạy bằng Java 25 theo **instance-main protocol**, nhưng logic và data vẫn còn gắn chặt entry point.

**Bước B — trích xuất logic có thể kiểm thử:**

```java
// src/main/java/com/example/reporting/Statistics.java
package com.example.reporting;

import java.util.List;

public final class Statistics {
    private Statistics() {}

    public static double average(List<Integer> values) {
        return values.stream()
                .mapToInt(Integer::intValue)
                .average()
                .orElse(0.0);
    }
}
```

```java
// src/main/java/com/example/reporting/Report.java
package com.example.reporting;

import java.util.List;

public final class Report {
    void main() {
        var durations = List.of(120, 80, 100);
        var average = Statistics.average(durations);
        IO.println("Thời gian trung bình: " + average + " ms");
    }
}
```

**Bước C — thêm test cho phần có API ổn định:**

```java
// src/test/java/com/example/reporting/StatisticsTest.java
package com.example.reporting;

import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;

class StatisticsTest {
    @Test
    void computesAverage() {
        assertEquals(100.0, Statistics.average(List.of(80, 100, 120)));
    }
}
```

Ví dụ JUnit trên yêu cầu JUnit dependency/test runner tương thích; JUnit không nằm sẵn trong JDK. Sử dụng build tool để kiểm tra `Statistics` và giữ entry point tập trung vào khởi chạy/orchestration.

**Sơ đồ tiến hóa:**

```mermaid
flowchart LR
    A["Compact file\nmain + helper methods"] --> B["Named class\ntrong named package"]
    B --> C["Tách logic thành\npublic API / services"]
    C --> D["Tests + library/module boundaries"]
    D --> E["CI, deployment,\nobservability"]
```

Không cần chuyển đổi chỉ vì một file gọn vượt một số dòng cố định. Điểm quyết định là **nhu cầu gọi từ nơi khác, phân tách trách nhiệm và tạo hợp đồng ổn định**.

## 9. So sánh compact, ordinary unnamed và ordinary named

| Thuộc tính | Compact file | Ordinary file ở unnamed package | Ordinary file ở named package |
|---|---|---|---|
| Có khai báo `class` bao quanh main? | Không bắt buộc; implicit class được tạo | Có lớp tường minh | Có lớp tường minh |
| Có `package com.example;`? | **Không** | Không | **Có** |
| Tên lớp có thể dùng trong Java source? | **Không** đối với implicit class | Có | Có |
| Được tạo instance và dùng constructor tùy biến? | **Không** đối với implicit class | Có | Có |
| Có thể `extends` / `implements` trên lớp chính? | **Không** đối với implicit class | Có | Có |
| Dễ import để tái sử dụng từ named package? | Không | Không | Có nếu public và có quyền module |
| Có thể dùng `void main()` instance ở Java 25? | Có | Có | Có |
| Có `import module java.base` ngầm? | Có | Không (trừ `java.lang` được import ngầm như Java thông thường) | Không |
| Phù hợp demo nhanh / học tập | Rất phù hợp | Có thể, nhưng thừa khai báo | Có thể nhưng nhiều cấu trúc hơn |
| Phù hợp public API, library, DI framework | Không dành cho mục tiêu này | Hạn chế namespace | Phù hợp hơn |

**Đừng trộn lẫn** hai khác biệt:

- **Unnamed package** liên quan đến namespace và khả năng import theo package.
- **Implicitly declared class** liên quan đến class identity, construction, inheritance và tên có thể tham chiếu.

Một ordinary class trong unnamed package vẫn có tên và có constructor; một compact file không có những khả năng đó đối với lớp ngầm. Vì thế, bài toán reuse của compact source file còn hạn chế hơn việc chỉ thiếu `package`.

## 10. Chạy, biên dịch, debug và build

### 10.1. Khởi chạy tệp gọn trực tiếp

Với `Hello.java`:

```bash
java --version
java Hello.java
java --source 25 Hello.java
```

Khi dùng Java 25 cho cả compile và run, **không cần `--enable-preview`** cho compact source files hoặc instance main methods đã final. Lệnh `java Hello.java` sử dụng **source-file mode**: launcher compile nguồn rồi chạy chương trình. `--source 25` giúp ghi rõ mức source cho công cụ khởi chạy.

### 10.2. Biên dịch ra class file rồi chạy

```bash
javac --release 25 Hello.java
java Hello
```

`javac` có thể tạo `Hello.class` theo tên file nguồn. Dùng lệnh `java Hello` để khởi chạy class file là khác với việc viết `new Hello()` trong Java source: tên được chọn có thể sử dụng bởi launcher, nhưng implicit declaration **không nằm trong scope** của mã nguồn để có thể tham chiếu tường minh.

Với project có cấu trúc chuẩn như `src/main/java/...`, muốn tổ chức code vào named packages, xây API và chạy bằng Gradle/Maven, **nên chuyển entry point thành ordinary class** rồi sử dụng cấu hình build/toolchain như các Java application thông thường. Không giả định mọi plugin/scanner/framework tự nhận diện compact entry point như một class có public API tường minh; cần kiểm chứng tooling thực tế nếu quyết định giữ cách này trong artifact sản xuất.

### 10.3. Source-file mode không phải công cụ đóng gói thư viện

Java launcher có chế độ chạy source file và hỗ trợ các source dependencies theo quy tắc launcher phiên bản hiện hành, nhưng mục tiêu chính là **khởi chạy chương trình**. Nó không tự biến các methods trong implicit class thành exported API hoặc tái sử dụng như JAR library.

Khi ứng dụng cần versioning, dependency management, reflection framework, AOT setup, packaging và test coverage được quản trị trong CI, hãy thiết kế named classes/modules đúng mức; giữ compact source file như công cụ thử nghiệm hoặc entry point tùy chọn nếu nó thực sự đơn giản.

## 11. Các trường hợp sai và cách sửa

| Tình huống | Vì sao sai hoặc gây hiểu nhầm | Cách sửa |
|---|---|---|
| `package com.example; void main() {...}` | Compact syntax không chấp nhận `package` declaration | Viết explicit class bên trong named package |
| `new FileName()` từ một compact file | Implicit class không nằm trong scope để tham chiếu bằng tên | Đổi thành named class |
| File chỉ có methods helper, không có `main` | Implicit class phải có candidate `main` | Dùng ordinary utility/service class |
| Viết constructor trực tiếp trong compact file | Không có constructor declaration cho implicit class | Dùng explicit class khi cần constructor |
| Viết `implements Runnable` trên lớp ngầm | Không khai báo header class và không có direct superinterfaces | Định nghĩa class có tên và `implements` |
| Dùng `IO.println(...)` nhưng chạy trên JDK cũ | `java.lang.IO` được giới thiệu cho Java 25; runtime thấp hơn không có API tương ứng | Dùng đúng JDK/toolchain hoặc API phù hợp mục tiêu |
| Gọi `println(...)` mà không có static import | Java 25 không tự import static methods của `IO` | Dùng `IO.println(...)` hoặc `import static` |
| Mong `List` tự có trong ordinary named class | Auto module import `java.base` chỉ áp dụng cho compact files | Thêm `import java.util.List;` hoặc `import module java.base;` |
| Cho rằng nested `record Item` là top-level API | `Item` là member type của implicit class | Tách `public record Item` sang named package |
| Đưa toàn bộ business logic vào `main()` | Khó test/reuse, phình to entry point | Trích xuất service/helper có tên, package, tests |
| Giữ tên package “rỗng” cho thư viện dùng chung | Named packages không thể import unnamed package như API chuẩn | Chuyển thư viện sang named package có namespace ổn định |

### Tình huống dễ nhầm: bản preview cũ

Một số bài hướng dẫn Java 21–24 từng giới thiệu `Unnamed Classes and Instance Main Methods` ở chế độ preview hoặc dùng các shortcut nhập/xuất cũ. Với Java 25, dùng **JEP 512 final**:

- `void main()` và compact source files không còn cần preview.
- `IO` hiện là `java.lang.IO`; dùng `IO.println(...)` theo cú pháp final.
- Các static methods của `IO` **không** còn được ngầm import cho compact source files.
- Module import declarations (JEP 511) cũng đã final ở Java 25, nên không cần áp dụng các ví dụ preview cũ để import các types từ `java.base`.

Nếu phải duy trì code viết trong giai đoạn preview, hãy biên dịch với Java 25 và sửa đúng những khác biệt về I/O và cú pháp, thay vì sao chép nguyên tutorial cũ.

## 12. Khi nào nên dùng và khi nào nên chuyển đổi?

**Nên cân nhắc compact source file khi:**

- Dạy Java cơ bản, ví dụ thuật toán, kịch bản chạy ngắn và demo tính năng Java 25.
- Viết chương trình một file để đọc dữ liệu mẫu, mô phỏng xử lý hoặc thử API mới mà không cần namespace/public API.
- Làm entry point rất mỏng cho một helper/library có tên, khi cách chạy và packaging đã được kiểm tra rõ.
- Muốn giảm boilerplate ở giai đoạn prototype trước khi xác định ranh giới module.

**Nên chuyển sang ordinary class trong named package khi:**

- Nhiều file hoặc module cần tái sử dụng logic.
- Cần export API, generate Javadoc rõ ràng, công bố library hoặc đặt namespace không trùng với phần mềm khác.
- Framework cần cấu hình/annotate class, xây instance, thực hiện DI, reflection hoặc proxying trên một type có tên.
- Cần triển khai theo module Java/JPMS, phân quyền truy cập package và quản lý phụ thuộc qua `module-info.java`.
- Cần maintain lâu dài, có bộ unit/integration tests và đội phát triển khác nhau cùng sửa code.

**Lựa chọn kiến trúc:** giữ Java 25 compact source như **đường vào đơn giản**, không như sự thay thế package, class, interface và module boundaries. Java 25 hỗ trợ hai phong cách song song; khả năng tiến hóa giữa chúng là một ưu điểm quan trọng của JEP 512.

## 13. Thực hành kiểm chứng

### Bài 1 — Chạy một tệp compact

Tạo `Hello.java` có `void main()`, một helper method và `IO.println(...)`. Chạy bằng Java 25, kiểm tra kết quả; sau đó thêm `int counter` và xem các member truy cập nhau như trong một instance class.

**Câu hỏi:** file này có khai báo Java function toàn cục không? Vì sao không?

### Bài 2 — Kiểm tra giới hạn package và identity

Lần lượt thử trong bản sao tệp:

1. Thêm `package com.example;` lên đầu compact file.
2. Tham chiếu `new Hello()` trong Java source.
3. Xóa `main()` chỉ giữ helper.
4. Viết block `static { ... }` trực tiếp trong compact file.

Dự đoán lỗi trước khi biên dịch, rồi giải thích dựa trên **JLS `7.3 và `8.1.8**, thay vì chỉ nhớ thông báo lỗi của một bản compiler cụ thể.

### Bài 3 — Phân biệt member type với public API

Trong compact file, khai báo `record Item(String id, int amount) {}` và dùng nó trong `main()`. Sau đó chuyển `Item` sang `com.example.model.Item` với `public record`, thêm import trong entry point và thử dùng từ một lớp khác thuộc named package.

**Tiêu chí đạt:** hiểu tại sao nested record của implicit class không tương đương public top-level record.

### Bài 4 — Tách helper tái sử dụng

Bắt đầu từ `MoneyFormatter.java` + `InvoiceDemo.java` trong ví dụ ở trên. Tiếp tục chuyển `MoneyFormatter` sang `com.example.pricing`, thêm unit test và tách logic khỏi `main()`.

**Tiêu chí đạt:** có named reusable API trong package rõ ràng, còn compact entry point chỉ gọi API.

### Bài 5 — Dùng API Java 25 đúng phiên bản

Tạo chương trình compact dùng `List`, `Path`, `IO` mà không cần import từng type của `java.base`, sau đó thử một API ngoài `java.base` như `java.net.http.HttpRequest` với explicit import. Chạy thử trên đúng Java 25 rồi so với ordinary class để thấy khác biệt tự import.

### Bảng kết quả cần ghi

| Kiểm tra | Kết quả mong đợi | Bằng chứng |
|---|---|---|
| `java Hello.java` trên JDK 25 | Chạy thành công, không cần preview | Phiên bản JDK và stdout |
| Compact file chứa `package` | Compile error | Lỗi compiler |
| Compact file không có candidate `main` | Compile error | Lỗi compiler |
| Gọi implicit class bằng tên trong source | Compile error | Lỗi compiler |
| Compact file dùng named helper | Compile/run thành công khi classpath và source đúng | Stdout + cấu trúc file |
| Named package dùng `public` helper | Import và unit test thành công | Tests |
| Gọi `IO.println` trong Java 25 | Hợp lệ | Biên dịch và chạy |
| Gọi `println` không có `import static` | Không hợp lệ | Lỗi compiler |

## 14. Checklist khi review code

- [ ] Xác nhận source/target là Java 25; không sử dụng cú pháp preview cũ hoặc yêu cầu `--enable-preview` không cần thiết.
- [ ] Tệp compact không có `package` declaration hoặc header `class` giả định.
- [ ] Hiểu các field/method/type cấp file thực chất thuộc implicit class, không phải top-level functions.
- [ ] Tệp có candidate `main` phù hợp.
- [ ] Không cố tham chiếu implicit class bằng tên, viết constructor, `extends` hay `implements` cho nó.
- [ ] Không nhầm unnamed package với named package hoặc unnamed module với API exportable.
- [ ] Không nhầm nested record/class ở compact file với public reusable top-level type.
- [ ] Dùng đúng `IO.println`/`java.lang.IO` ở Java 25; không phụ thuộc cách static import cũ từ preview.
- [ ] Dùng auto import `java.base` đúng phạm vi; thêm imports hoặc `import module` cho modules khác khi cần.
- [ ] Đã tách các hàm hoặc dữ liệu thực sự tái sử dụng sang named helper API.
- [ ] Nếu code chuyển sang package/module, đã điều chỉnh build, imports, visibility và test.
- [ ] Có lộ trình refactor thành ordinary class khi ứng dụng cần namespace, DI, Javadoc hoặc đóng gói thư viện.

### Tài liệu tham khảo chính thức

1. [JEP 512 — Compact Source Files and Instance Main Methods (Final, Java 25)](https://openjdk.org/jeps/512)
2. [Oracle Java 25 — Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html)
3. [Java Language Specification Java SE 25 — mục 7.3 Compilation Units](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.3)
4. [Java Language Specification Java SE 25 — mục 8.1.8 Implicitly Declared Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.8)
5. [Java Language Specification Java SE 25 — mục 6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3)
6. [Oracle Java 25 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html)
7. [Oracle Java 25 — The java Command, Source-File Mode](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
8. [JEP 511 — Module Import Declarations (Final, Java 25)](https://openjdk.org/jeps/511)
