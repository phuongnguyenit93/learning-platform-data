# Cú pháp import module và ví dụ nhập các kiểu từ java.base

> **Chương:** Module import  
> **Phiên bản:** Java 25 — **Module Import Declarations (JEP 511)** là tính năng ngôn ngữ chính thức, không cần `--enable-preview`.  
> **Mục tiêu:** Biết viết `import module java.base;`, dùng được các kiểu từ nhiều package của `java.base`, hiểu phạm vi import, thứ tự ưu tiên khi trùng tên và quan hệ với Java Platform Module System (JPMS).

## 1. Vì sao Java 25 có module import?

Một chương trình Java hiện đại thường sử dụng đồng thời các API từ nhiều package:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;
~~~

Dù các kiểu trên nằm trong những package khác nhau, chúng đều thuộc **module hệ thống `java.base`**. Java 25 cho phép viết một khai báo:

~~~java
import module java.base;
~~~

Sau khai báo này, ta có thể dùng các tên ngắn như `LocalDate`, `List`, `Map`, `Function`, `Collectors`, `Stream` và `TreeMap` mà không phải nhập từng kiểu hoặc từng package.

**Điểm quan trọng:** Đây là cách **nhập tên kiểu để viết mã nguồn**, không phải hành động tải thư viện, cài đặt package hay tự động cho phép truy cập mọi API nội bộ của JDK.

Tính năng được phát triển qua các bản preview trước đó và **được hoàn thiện trong Java 25 theo JEP 511**. Với JDK 25, sử dụng cú pháp chính thức như trong bài; không dùng hướng dẫn preview của JDK 23/24 làm quy trình hiện hành.

### Kết quả cần đạt

Sau bài học, người học có thể:

1. Phân biệt module import, package import, single-type import và `requires`.
2. Biên dịch một lớp thường dùng `import module java.base;` với ít nhất ba package khác nhau.
3. Giải thích vì sao `import module java.base;` không có nghĩa mọi module thuộc JDK đều được nhập.
4. Giải quyết tên kiểu bị trùng khi import nhiều module, ví dụ `java.util.List` và `java.awt.List`.
5. Hiểu sự khác biệt giữa lớp Java thông thường và **compact source file** của Java 25 đối với `java.base`.

## 2. Cú pháp chuẩn của module import

Ngữ pháp theo **Java Language Specification 25, §7.5.5**:

~~~java
import module ten.module;
~~~

Ví dụ:

~~~java
import module java.base;
import module java.sql;
~~~

Giải thích:

| Thành phần | Ý nghĩa |
|---|---|
| `import` | Bắt đầu một khai báo nhập tên trong compilation unit hiện tại |
| `module` | Chỉ rằng đối tượng được nhập là **module**, không phải package |
| `java.base` | Tên module có trong JDK; khác tên package `java.base` vốn không phải đường dẫn package để viết `import java.base.*` |
| `;` | Kết thúc khai báo theo cú pháp Java |

Một **single-module-import declaration** nhập theo nhu cầu sử dụng (*on demand*) các **kiểu top-level `public`** từ:

- Các package được module chỉ định **export** cho module đang biên dịch.
- Các package được export bởi những module khác mà module đang biên dịch có thể đọc thông qua quan hệ đọc module được nêu trong JLS; nhờ đó module import có thể bao gồm API từ các dependency bắc cầu có liên quan.

Vì vậy, `import module M;` **không có nghĩa nhập toàn bộ mọi class** trong JAR/JMOD của `M`: package không được export, kiểu không accessible và kiểu nội bộ không tự nhiên thành API công khai.

### Vị trí đặt khai báo

Trong một **ordinary compilation unit**, thứ tự thường là:

~~~java
package com.example.demo;

import module java.base;
import java.util.UUID;

public class Example {
    // ...
}
~~~

Khai báo `package` (nếu có) đứng trước các `import`; các `import` đứng trước khai báo class/interface/record ở cấp file. `import module` có thể cùng tồn tại với single-type import, package-on-demand import hoặc static import.

**Phạm vi:** khai báo import chỉ áp dụng trong **tệp nguồn Java chứa nó** (*compilation unit*). Import một module trong `A.java` không làm các tên ngắn tự động có hiệu lực trong `B.java`, dù hai tệp ở cùng package.

### Import là “on demand”

Khai báo `import module java.base;` cho phép compiler phân giải các tên kiểu được dùng, chứ không tạo biến, object hay khởi tạo mọi class trong `java.base`. Nó cũng **không biến tất cả package trong module thành package của ứng dụng**.

## 3. Những package quen thuộc do java.base cung cấp

`java.base` là module nền tảng mà mọi module Java đều phụ thuộc ngầm định. Nó cung cấp nhiều API hiện vẫn được dùng rộng rãi:

| Package được export bởi `java.base` | Kiểu có thể dùng với module import | Ví dụ ứng dụng |
|---|---|---|
| `java.lang` | `String`, `Math`, `Runtime`, `IO` | Kiểu nền tảng và console I/O |
| `java.util` | `List`, `Map`, `Set`, `Optional`, `TreeMap` | Collection |
| `java.util.function` | `Function`, `Predicate`, `Consumer` | Hàm và lambda |
| `java.util.stream` | `Stream`, `Collectors` | Xử lý dữ liệu dạng luồng |
| `java.time` | `LocalDate`, `Instant`, `Duration` | Ngày/giờ |
| `java.nio.file` | `Path`, `Files` | Làm việc với đường dẫn/tệp |
| `java.io` | `IOException`, `InputStream` | Luồng I/O |
| `java.net` | `URI`, `Socket` | Kết nối mạng cơ bản |
| `java.security` | `MessageDigest`, `SecureRandom` | API bảo mật |
| `javax.crypto` | `Cipher`, `Mac` | API mật mã thuộc JDK |

**Lưu ý phân vùng module:** `java.net.http.HttpClient` thuộc **`java.net.http`**, không thuộc `java.base`. `java.sql.Connection` thuộc **`java.sql`**; `java.awt.List` thuộc **`java.desktop`**. Muốn dùng kiểu từ các module đó, chương trình phải có khả năng đọc module tương ứng và import phù hợp.

`java.lang` vốn đã **được import ngầm định vào mọi tệp Java**, kể cả ordinary source file. Do đó dùng `String` hoặc `Math` mà không ghi `import module java.base;` không phải bằng chứng module import đã hoạt động. Hãy thử các tên `List`, `Stream`, `Collectors`, `Function` hoặc `LocalDate`.

## 4. Ví dụ 1 — Nhập nhiều package bằng một dòng

Tạo tệp `BaseImportDemo.java` (ordinary source file, chưa cần cấu trúc project phức tạp):

~~~java
import module java.base;

public class BaseImportDemo {

    public static void main(String[] args) {
        Map<String, Long> frequencies = Stream
                .of("java", "module", "java")
                .collect(Collectors.groupingBy(
                        Function.identity(),
                        TreeMap::new,
                        Collectors.counting()));

        LocalDate releaseDate = LocalDate.of(2025, 9, 16);
        Path documentPath = Path.of("docs", "notes.txt");

        System.out.println(frequencies);
        System.out.println(releaseDate);
        System.out.println(documentPath.getFileName());
    }
}
~~~

Trong ví dụ:

- `Map`, `TreeMap` đến từ `java.util`.
- `Stream` và `Collectors` đến từ `java.util.stream`.
- `Function` đến từ `java.util.function`.
- `LocalDate` đến từ `java.time`.
- `Path` đến từ `java.nio.file`.
- `String`, `System` thuộc `java.lang` và vốn đã luôn sẵn dùng.

Chạy trong thư mục chứa `BaseImportDemo.java` với JDK 25:

~~~bash
java --version
javac --version
javac BaseImportDemo.java
java BaseImportDemo
~~~

Kết quả:

~~~text
{java=2, module=1}
2025-09-16
notes.txt
~~~

`TreeMap` giữ thứ tự khóa để dòng đầu tiên có kết quả ổn định, không phụ thuộc thứ tự duyệt mặc định của `HashMap`. `Path.getFileName()` chỉ in `notes.txt`, nên ví dụ không phụ thuộc ký tự phân tách đường dẫn của Windows hay Unix.

**Điều cần quan sát:** chỉ có **một khai báo import** mà các kiểu từ năm package có thể được dùng bằng tên ngắn. Không cần thêm `--enable-preview` vì module import đã là tính năng chính thức trong Java 25.

### Chạy trực tiếp tệp nguồn (source-file mode)

Nếu không muốn tạo class file trước, Java launcher hỗ trợ:

~~~bash
java BaseImportDemo.java
~~~

Lệnh này biên dịch và chạy trực tiếp mã nguồn trong source-file mode. Quy tắc import không khác với cách `javac` rồi `java BaseImportDemo`. Nếu thư mục có class file cũ, nên chọn rõ một cách chạy khi đối chiếu kết quả để tránh nhầm lẫn.

## 5. Ví dụ 2 — So sánh bốn kiểu import

Cùng dùng `List` và `Collectors`, có thể viết các cách sau.

### A. Single-type import: chỉ định chính xác từng kiểu

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

class ExactImports {
    static void main() {
        List<String> values = Stream.of("A", "B").toList();
        System.out.println(values.stream().collect(Collectors.joining(",")));
    }
}
~~~

Ưu điểm: người đọc nhìn vào import biết ngay kiểu đến từ đâu; ít nguy cơ xung đột. Nhược điểm: nhiều dòng khi ứng dụng cần nhiều kiểu từ các package của cùng một module.

### B. Package-on-demand import: chỉ nhập một package

~~~java
import java.util.*;
import java.util.stream.*;

class PackageImports {
    static void main() {
        List<String> values = Stream.of("A", "B").toList();
        System.out.println(values);
    }
}
~~~

`import java.util.*;` **không** nhập các kiểu của package con `java.util.stream`; vì vậy vẫn cần `import java.util.stream.*;`. Dấu chấm trong tên package không tạo cơ chế đệ quy.

### C. Module import: nhập các kiểu công khai được export từ module

~~~java
import module java.base;

class ModuleImports {
    static void main() {
        List<String> values = Stream.of("A", "B").toList();
        System.out.println(values);
    }
}
~~~

Với `java.base`, một dòng thay thế nhiều dòng import theo package. Đây là ưu điểm của JEP 511 trong chương trình sử dụng nhiều phần API của một module.

### D. Fully qualified name: không cần import

~~~java
class QualifiedNames {
    static void main() {
        java.util.List<String> values =
                java.util.stream.Stream.of("A", "B").toList();
        System.out.println(values);
    }
}
~~~

Viết tên đầy đủ hữu ích khi muốn tránh nhầm lẫn; đổi lại code dài hơn. **Module import chỉ cho phép sử dụng tên đơn giản; nó không thay đổi danh tính thật của kiểu.**

### Bảng quyết định

| Cách viết | Mức bao phủ | Thế mạnh | Giới hạn |
|---|---|---|---|
| `import java.util.List;` | Một kiểu cụ thể | Rõ ràng, chống xung đột | Có thể nhiều dòng |
| `import java.util.*;` | Các kiểu accessible trong một package | Gọn khi dùng nhiều kiểu cùng package | Không bao gồm subpackage |
| `import module java.base;` | Các public top-level types thuộc package được export (và phạm vi được đọc bắc cầu) | Rất gọn khi dùng nhiều package | Dễ đụng tên khi mở rộng phạm vi |
| `java.util.List` | Kiểu được gọi bằng tên đầy đủ | Không mơ hồ | Dài hơn trong source |

Không có quy tắc buộc mọi dự án Java 25 phải chuyển từ explicit import sang module import. Với thư viện công cộng hoặc codebase lớn, nhiều nhóm vẫn ưu tiên single-type import để IDE, reviewer và quy tắc style dễ nhận diện dependency.

## 6. Ví dụ 3 — Module import không nhập static method

Module import đưa **tên kiểu** vào phạm vi sử dụng, không tự nhập mọi method hay field tĩnh của các kiểu.

Ví dụ hợp lệ:

~~~java
import module java.base;

class StaticMethods {
    static void main() {
        List<String> words = List.of("one", "two");
        System.out.println(words);
        IO.println("Hello Java 25");
    }
}
~~~

Những điều cần chú ý:

- `List.of(...)` dùng **tên kiểu `List`** đã được import và gọi method static qua tên kiểu.
- `System.out.println(...)` và `IO.println(...)` đều dùng **tên kiểu** làm qualifier.
- Viết `of("one", "two")` hoặc `println("Hello")` trần trong class này **không hợp lệ** nếu không có method tương ứng trong phạm vi hay static import cụ thể.

Nếu thực sự muốn gọi `emptyList()` mà không ghi `Collections.`, dùng static import riêng:

~~~java
import module java.base;
import static java.util.Collections.emptyList;

class StaticImportExample {
    static void main() {
        List<String> words = emptyList();
        System.out.println(words.isEmpty());
    }
}
~~~

Kết quả là `true`. `import module java.base;` và `import static ...;` giải quyết **hai nhu cầu khác nhau**.

## 7. Ví dụ 4 — Xung đột tên khi import nhiều module

Một đặc điểm quan trọng của cơ chế *on demand*: **hai module có thể export các kiểu khác package nhưng cùng simple name**.

- `java.util.List`: interface của Collection API, thuộc `java.base`.
- `java.awt.List`: component GUI, thuộc `java.desktop`.

Tạo `AmbiguousList.java` để quan sát lỗi (cố ý **không biên dịch được**):

~~~java
import module java.base;
import module java.desktop;

class AmbiguousList {
    static void main() {
        List<String> words = List.of("A", "B"); // Lỗi: List mơ hồ
        System.out.println(words);
    }
}
~~~

Biên dịch:

~~~bash
javac AmbiguousList.java
~~~

Compiler báo tham chiếu `List` mơ hồ giữa `java.util.List` và `java.awt.List`; câu chữ chính xác của thông báo lỗi có thể khác theo bản JDK. Đây là lỗi phân giải tên ở **compile time**, không phải lỗi chỉ xuất hiện lúc chạy.

### Cách giải quyết 1: explicit single-type import

Sửa thành:

~~~java
import module java.base;
import module java.desktop;

import java.util.List;

class AmbiguousList {
    static void main() {
        List<String> words = List.of("A", "B");
        System.out.println(words);
    }
}
~~~

Single-type import `import java.util.List;` ưu tiên hơn các kiểu cùng tên được import theo kiểu *on demand*, nên tên ngắn `List` chỉ tới `java.util.List`. Kết quả:

~~~text
[A, B]
~~~

### Cách giải quyết 2: viết tên đầy đủ

Có thể không thêm single-type import và viết:

~~~java
import module java.base;
import module java.desktop;

class QualifiedList {
    static void main() {
        java.util.List<String> words = java.util.List.of("A", "B");
        System.out.println(words);
    }
}
~~~

Cách này rõ ràng nhất khi trong cùng file bạn cần **đồng thời** dùng `java.util.List` và `java.awt.List`.

### Những xung đột khác

Trong Java 25, `java.base` còn có `java.lang.classfile.Label`, trong khi `java.desktop` có `java.awt.Label`. Khi import cả hai module, sử dụng simple name `Label` cũng có thể mơ hồ.

Quan trọng: **không phải khai báo hai module import là lập tức lỗi**; lỗi xuất hiện khi một simple name đang được dùng không thể xác định duy nhất theo luật phân giải tên. Thường nên import tường minh những kiểu dễ trùng tên.

## 8. Import module và JPMS: không đồng nghĩa với requires

Java có hai cơ chế cùng chứa từ “module” nhưng tác dụng hoàn toàn khác nhau.

| Cú pháp | Viết ở đâu? | Mục đích |
|---|---|---|
| `import module java.base;` | Tệp `.java` dùng kiểu | Cho phép dùng simple names của những public top-level types trong các package exported |
| `requires java.sql;` | `module-info.java` | Khai báo module hiện tại **đọc/phụ thuộc** module `java.sql` |
| `exports com.example.api;` | `module-info.java` | Công bố package của module hiện tại cho module khác |
| `import java.sql.Connection;` | Tệp `.java` dùng kiểu | Nhập một kiểu cụ thể |

Theo JLS, `import module M;` chỉ hợp lệ khi module `M` **được module hiện tại đọc**. Khai báo import **không tự thêm quan hệ `requires`**.

### Trường hợp java.base

Mọi module Java đều đọc `java.base` ngầm định (trừ cơ chế đặc biệt của chính `java.base`). Vì vậy trong ordinary Java source, bạn có thể viết:

~~~java
import module java.base;
~~~

mà không phải khai báo thêm `requires java.base;` trong `module-info.java`. Thêm `requires java.base;` chỉ để dùng module import là không cần thiết.

### Trường hợp một module khác: java.sql

Giả sử dự án của bạn là **named module** `com.example.report`:

~~~text
src/
└── com.example.report/
    ├── module-info.java
    └── com/
        └── example/
            └── report/
                └── Report.java
~~~

Tệp `module-info.java`:

~~~java
module com.example.report {
    requires java.sql;
}
~~~

Tệp `Report.java`:

~~~java
package com.example.report;

import module java.sql;

public class Report {
    public static void main(String[] args) {
        SQLException error = new SQLException("demo");
        System.out.println(error.getMessage());
    }
}
~~~

Biên dịch và chạy với JDK 25 từ thư mục chứa `src`:

~~~bash
javac -d out --module-source-path src -m com.example.report
java --module-path out -m com.example.report/com.example.report.Report
~~~

Kết quả:

~~~text
demo
~~~

Ví dụ dùng `SQLException` từ package `java.sql` mà không phải viết `import java.sql.SQLException;`. Nhờ `requires java.sql;`, module `com.example.report` đọc được `java.sql`.

Nếu bỏ `requires java.sql;`, đừng mong `import module java.sql;` tự tạo dependency. Compiler có thể báo module không được đọc/hiển thị. Với những module khác `java.base`, chính xác module nào được đọc và resolved còn tùy cấu hình module path, các dependency transitive và cách ứng dụng được khởi chạy.

**Lưu ý:** Một module import còn có thể bao gồm các kiểu từ module phụ thuộc bắc cầu (thí dụ qua `requires transitive`), nếu module đang biên dịch đọc được những module đó. Đây là quy tắc quan trọng khi nhập các module tổng hợp hoặc module có API phụ thuộc kiểu từ module khác. Không nên diễn giải `import module M;` đơn giản là “import tất cả class trong file JAR của M”.

## 9. Compact source file trong Java 25 được import java.base ngầm định

Trong Java 25, **compact source files và instance main methods (JEP 512)** cũng đã là tính năng chính thức.

Một **compact source file** không khai báo lớp top-level theo cách thông thường mà cho phép viết `void main()` trực tiếp. Theo **JLS 25 §7.3**, mỗi compact compilation unit **được nhập ngầm định `java.base` theo cơ chế module import** — tương đương có:

~~~java
import module java.base;
~~~

ở đầu file. Vì vậy tệp compact sau **không cần viết dòng import**.

Lưu thành `CompactModuleDemo.java`:

~~~java
void main() {
    List<String> words = List.of("java", "25");
    Map<String, Integer> scores = Map.of("module", 1);

    IO.println(words);
    IO.println(scores.get("module"));

    Stream.of("compact", "source").forEach(IO::println);
}
~~~

Chạy:

~~~bash
java CompactModuleDemo.java
~~~

Kết quả:

~~~text
[java, 25]
1
compact
source
~~~

Giải thích:

- `List` và `Map` đến từ `java.util`; `Stream` đến từ `java.util.stream`; chúng sẵn có nhờ **module import ngầm định**.
- `IO` là lớp `java.lang.IO` trong Java 25; gọi `IO.println(...)` là cách viết rõ ràng.
- Phương thức `println` **không được static-import ngầm định** vào file; việc gọi `IO::println` qua tên lớp vẫn đúng.

**Khác biệt với ordinary source file:** Trong file có `class BaseImportDemo`, Java tự import `java.lang.*`, nhưng không tự import toàn bộ `java.base`. Trong compact source file, toàn bộ những public top-level types từ các package được `java.base` export đều có thể được dùng theo tên ngắn mà không cần khai báo module import rõ ràng.

Nếu thêm `import module java.base;` vào compact source file, nó không cần thiết cho mục tiêu nhập kiểu từ `java.base`; khai báo ngầm định đã thực hiện việc đó.

## 10. Những điều import module không làm

Bảng dưới giúp tránh hiểu sai tính năng Java 25.

| Suy luận sai | Thực tế đúng |
|---|---|
| `import module java.base;` “bật” toàn bộ module của JDK | Chỉ nhập kiểu trong phạm vi các package được export của `java.base` và quan hệ đọc module liên quan |
| Import module giúp gọi thẳng static method `println()` | Chỉ đưa tên kiểu vào phạm vi; static import phải khai báo riêng nếu cần |
| `import module M;` tương đương `requires M;` | Import xử lý tên kiểu; `requires` xử lý module readability |
| Một `import module` áp dụng cho cả package của project | Phạm vi chỉ nằm trong compilation unit chứa khai báo |
| Import bao gồm mọi class nội bộ trong `jdk.internal.*` | Chỉ kiểu accessible từ package được export theo JPMS |
| `import module java.base;` cho phép viết `HttpClient` ngay | `HttpClient` của `java.net.http` thuộc module khác |
| `import module java.base;` là cú pháp preview ở Java 25 | Tính năng đã được hoàn thiện trong Java 25; không cần `--enable-preview` |
| Dùng import module bắt buộc để sử dụng `String`, `Math` | Các kiểu public của `java.lang` vốn được nhập ngầm định |
| Import nhiều module luôn gây lỗi compiler | Chỉ gặp lỗi khi không phân giải được một simple name đang dùng hoặc vi phạm quy tắc khác |
| `import java.util.*;` đã bao gồm `java.util.stream` | Package-on-demand import không tự đi vào subpackage |
| Có import là class đã được khởi tạo/nạp sẵn | Import là cơ chế phân giải tên của source; không tự tạo object hay thực thi code |

## 11. Chẩn đoán lỗi khi thử nghiệm

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Compiler không hiểu `import module java.base;` | Đang biên dịch bằng JDK cũ hoặc cấu hình `--release` dưới 25 | Xem `javac --version`, Maven/Gradle toolchain và language level |
| IDE đánh dấu đỏ nhưng CLI `javac` thành công | IDE/project language level đang thấp hơn JDK 25 | Cập nhật JDK SDK/language level và plugin hỗ trợ |
| `reference to List is ambiguous` | Import `java.base` và `java.desktop` cùng đưa hai kiểu `List` vào phạm vi | Thêm `import java.util.List;` hoặc dùng tên đầy đủ |
| `cannot find symbol: HttpClient` | `HttpClient` thuộc `java.net.http`, không thuộc `java.base` | Dùng `import java.net.http.HttpClient;` hoặc module import phù hợp, bảo đảm readability |
| `package ... is not visible` | Named module chưa `requires` module chứa kiểu, hoặc package không export | Kiểm tra `module-info.java`, module path, visibility/exports |
| `module ... is not read` | Import module không thay `requires` | Khai báo module dependency phù hợp trong descriptor |
| `cannot find symbol: println` | Nhầm module import với static import | Dùng `IO.println(...)`, `System.out.println(...)` hoặc static import đúng |
| `cannot find symbol: Stream` dù có `import java.util.*;` | `Stream` thuộc package con `java.util.stream` | Thêm `import java.util.stream.Stream;` hoặc `import module java.base;` |
| Code compile nhưng chạy class cũ | Chưa biên dịch lại hoặc classpath trỏ đến bản cũ | Biên dịch lại và chạy đúng file/class |
| `error: release version 25 not supported` | `javac` đang là phiên bản thấp hơn 25 | Đồng bộ JDK runtime, compiler và công cụ build |
| `import java.base.*;` không hợp lệ | `java.base` là tên **module**, không phải package | Viết `import module java.base;` |

Quy trình nhanh:

~~~bash
java --version
javac --version
javac BaseImportDemo.java
java BaseImportDemo
~~~

Nếu bản CLI chạy được mà IDE/build không chạy, ưu tiên kiểm tra runtime JDK và compiler được IDE/Maven/Gradle chọn. Không khắc phục bằng cách bật preview trên JDK 25; đó là cách làm không cần thiết cho tính năng đã hoàn thiện.

### Kiểm tra module nào chứa một package

Trên JDK 25, có thể xem thông tin module chuẩn bằng:

~~~bash
java --describe-module java.base
java --describe-module java.sql
java --describe-module java.net.http
~~~

Output liệt kê các package được export và dependency của module tương ứng. Lệnh `java --describe-module` chỉ để **quan sát module descriptor**, không thêm import hoặc sửa source. Cách này hữu ích để tránh đoán nhầm rằng mọi API `java.*` đều thuộc `java.base`.

## 12. Bài tập thực hành

### Bài tập A — Rút gọn import

Đoạn code ban đầu:

~~~java
import java.util.List;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

class ExerciseA {
    static void main() {
        String joined = Stream.of("A", "B")
                .map(Function.identity())
                .collect(Collectors.joining("-"));
        List<String> values = List.of(joined);
        System.out.println(values);
    }
}
~~~

Thay **bốn dòng import** bằng một khai báo module import phù hợp, biên dịch với JDK 25 rồi dự đoán output. Sau khi thay bằng `import module java.base;`, kết quả mong đợi là:

~~~text
[A-B]
~~~

### Bài tập B — Tìm lỗi mơ hồ

Cho:

~~~java
import module java.base;
import module java.desktop;

class ExerciseB {
    static void main() {
        List<String> values = List.of("one", "two");
        System.out.println(values);
    }
}
~~~

Giải thích vì sao compiler có thể báo lỗi ở `List`. Sửa bài theo hai cách: single-type import `java.util.List` và tên đầy đủ `java.util.List` ngay trong mã.

### Bài tập C — Chứng minh import module không thay requires

Tạo một named module `demo.sql` và khai báo trong một tệp:

~~~java
import module java.sql;
~~~

Sau đó thử biên dịch khi `module-info.java` **chưa có** `requires java.sql;`, rồi thêm `requires java.sql;` và so sánh. Chỉ sửa dependency ở `module-info.java` mới giúp module đọc được các API cần thiết.

### Bài tập D — Ordinary so với compact source file

Chuyển code từ `BaseImportDemo.java` thành một compact source file dùng `void main()` và bỏ dòng `import module java.base;`. Kiểm tra các kiểu `Map`, `LocalDate`, `Stream` vẫn dùng được ở JDK 25. Giải thích vì sao ordinary source file không có cùng loại implicit module import này.

### Câu hỏi tự kiểm tra

1. Vì sao `import module java.base;` có thể thay thế nhiều import theo package?
2. Sự khác nhau giữa **module được đọc** và **kiểu được nhập theo tên ngắn** là gì?
3. Tại sao single-type import `java.util.List` giải quyết được ambiguity khi có thêm `java.desktop`?
4. Vì sao `java.net.http.HttpClient` không tự xuất hiện từ `import module java.base;`?
5. Vì sao `IO.println(...)` hợp lệ nhưng `println(...)` trần không mặc nhiên hợp lệ trong ordinary class?
6. Trong loại source file nào Java 25 tự áp dụng `import module java.base;`?

## 13. Checklist và cách dùng trong dự án thực tế

- [ ] Đang dùng JDK 25 cho cả `java` và `javac`, không chỉ thiết lập IDE đúng tên nhưng compiler vẫn là JDK cũ.
- [ ] Nắm cú pháp chính xác `import module M;`; không nhầm module với package.
- [ ] Dùng `List`, `Stream`, `Collectors`, `Function`, `LocalDate`, `Path` sau một dòng `import module java.base;`.
- [ ] Hiểu giới hạn về `public`, top-level types, package exports và JPMS readability.
- [ ] Biết cách xử lý ambiguous simple name khi nhập nhiều module.
- [ ] Biết module import không thay `requires` và không tự nhập static members.
- [ ] Phân biệt nhập `java.lang` mặc định với nhập `java.base` ngầm định trong compact source file.
- [ ] Có thể giải thích vì sao code style dự án lớn đôi khi vẫn chọn explicit single-type import.

**Khuyến nghị:** module import rất hữu ích cho chương trình Java 25 ngắn, bài học, prototype và các file thường dùng nhiều package của cùng module. Với codebase nhiều thư viện, ưu tiên tính rõ ràng và quy ước team; sử dụng single-type import ở những vị trí dễ trùng tên để reviewer biết ngay kiểu đến từ đâu.

Không phải thay đổi source sang module import mới tận dụng được các khả năng Java 25 khác như **ScopedValue**, **flexible constructor bodies**, **API dẫn xuất khóa**, **AOT cache** hay **JFR**. Đây là các chủ đề độc lập, và việc chọn kiểu import không quyết định khả năng sử dụng của chúng.

## 14. Tài liệu chính thức (Java 25)

- [JEP 511 — Module Import Declarations](https://openjdk.org/jeps/511): mục tiêu thiết kế và trạng thái được chuẩn hóa ở JDK 25.
- [Java SE 25 JLS §7.5.5 — Single-Module-Import Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.5.5): quy tắc cú pháp, module readability, các kiểu được import và scope.
- [Oracle JDK 25 — Module Import Declarations](https://docs.oracle.com/en/java/javase/25/language/module-import-declarations.html): ví dụ thay nhiều package import bằng `import module java.base;` và xử lý xung đột tên.
- [Java SE 25 JLS §7.3 — Compilation Units](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.3): compact source file tự nhập các kiểu từ `java.base`.
- [Oracle JDK 25 — Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): sử dụng module import ngầm định trong compact source file.
- [Oracle JDK 25 — Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): xác nhận JEP 511 là tính năng chính thức trong Java 25.

> **Ghi nhớ:** `import module java.base;` giúp sử dụng **tên ngắn** của các kiểu `public` từ những package được export bởi `java.base`. Nó **không** thay JPMS `requires`, không nhập static method và không giải quyết mọi tên trùng. Với Java 25, cú pháp này đã chính thức, không phải preview.
