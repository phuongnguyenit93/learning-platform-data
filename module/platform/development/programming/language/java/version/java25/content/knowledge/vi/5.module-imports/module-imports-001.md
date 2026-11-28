# Mục đích và trạng thái chính thức của module import declarations trong Java 25

## 1. Bối cảnh: tại sao Java bổ sung module import?

Trong Java truyền thống, khi một tệp cần dùng nhiều kiểu từ nhiều package, lập trình viên phải khai báo từng kiểu hoặc từng package:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;
~~~

Với một chương trình nhỏ dùng collection, stream, file, time hoặc các API cơ bản, phần `import` đôi khi dài gần bằng logic chính. Trong khi đó, **Java Platform Module System (JPMS)** đã chia Java SE API thành các module như `java.base`, `java.sql` và `java.desktop`. Mỗi module khai báo rõ những package mà nó công khai qua `exports`.

**Module import declarations** tận dụng ranh giới API này để cho phép nhập các kiểu public thuộc những package được module export chỉ bằng một khai báo:

~~~java
import module java.base;
~~~

Điểm cốt lõi: `import module java.base;` **giúp mã nguồn tham chiếu đến các kiểu đã được phép sử dụng bằng tên ngắn**, chứ không có nghĩa mọi class được nạp vào bộ nhớ, một thư viện mới được tự động tải xuống, hay chương trình được chia thành module.

Bài thuộc chương **Module import** của học phần `JAVA_VERSION_JAVA25`. Chủ đề trực tiếp là **“Mục đích và trạng thái chính thức của module import declarations trong Java 25”**. Nội dung tập trung vào cú pháp đã trở thành tính năng chuẩn trong Java 25 và còn hữu ích cho phát triển Java hiện đại; không sử dụng cú pháp preview đã lỗi thời làm lựa chọn mặc định.

### Sau bài này, người học có thể

1. Giải thích đúng mục tiêu và phạm vi của `import module M;`.
2. Xác định trạng thái **final/permanent** của JEP 511 trong Java 25, phân biệt với các giai đoạn preview trước đó.
3. So sánh module import với single-type import, wildcard package import, `import static` và JPMS `requires`.
4. Áp dụng module import ở classpath hoặc named module với điều kiện module **readable**.
5. Phát hiện nhập nhằng tên kiểu và chọn cách giải quyết phù hợp.
6. Quyết định khi nào module import giúp đọc code tốt hơn, khi nào import tường minh phù hợp hơn.
7. Viết và biên dịch ví dụ trên JDK 25 **không dùng `--enable-preview`**.

## 2. Trạng thái chính thức tại Java 25

Module import declarations đã đi qua quá trình thử nghiệm và hoàn thiện:

| Phiên bản Java | JEP | Trạng thái của module import |
| --- | --- | --- |
| Java 23 | JEP 476 | Preview lần đầu |
| Java 24 | JEP 494 | Preview lần hai |
| **Java 25** | **JEP 511** | **Final / permanent** |

Đây là thông tin lịch sử phát triển để hiểu mức độ ổn định, **không phải lời khuyên tiếp tục sử dụng Java 23/24 preview**. Từ **Java 25**, module import declarations là tính năng ngôn ngữ chính thức, có thể biên dịch bình thường mà không bật preview flag chỉ vì sử dụng tính năng này.

Ví dụ:

~~~bash
# JDK 25: biên dịch bằng cú pháp đã được hoàn thiện.
javac --release 25 FruitSummary.java
java FruitSummary
~~~

Nếu source sử dụng `import module` nhưng build tool vẫn cấu hình `--release 21` hoặc `--release 24`, cú pháp sẽ không được chấp nhận ở mức source mục tiêu đó. Nâng **JDK chạy compiler** lên 25 nhưng vẫn biên dịch bằng `--release 21` không có nghĩa có thể sử dụng cú pháp Java 25 trong artifact tương thích Java 21.

**Phân biệt hai câu hỏi:**

- “JDK 25 có phải dòng được hỗ trợ lâu dài không?” — nói về vòng đời JDK và chính sách nhà cung cấp.
- “Module import có phải tính năng ổn định trong JDK 25 không?” — **có**, vì JEP 511 đã hoàn thiện. Quyết định sử dụng còn phụ thuộc source compatibility, module readability và khả năng đọc mã.

Một tính năng chính thức không tự động là yêu cầu bắt buộc cho mọi codebase; import tường minh vẫn được hỗ trợ và tiếp tục có giá trị.

## 3. Cú pháp chuẩn và tác dụng chính xác

Cú pháp là:

~~~java
import module M;
~~~

Trong đó `M` là **tên module có thể đọc được** từ module chứa compilation unit hiện tại. Ví dụ:

~~~java
import module java.base;
import module java.sql;
~~~

Theo đặc tả Java 25, module import cung cấp **on-demand access bằng tên ngắn** đến các kiểu public top-level thuộc:

1. Các package được module `M` export cho module hiện tại.
2. Các package được export bởi những module khác mà module hiện tại đọc được **do việc đọc `M`**, chẳng hạn thông qua phụ thuộc `requires transitive` của `M`.

Những giới hạn cần hiểu chính xác:

- Chỉ áp dụng cho **public top-level classes và interfaces** trong package được export và accessible.
- Không import private/package-private types chỉ vì chúng nằm trong cùng module.
- Không vượt qua các giới hạn `exports` hoặc JPMS strong encapsulation.
- Không có tác dụng như `import static`; các static methods/constants không tự nhiên có tên ngắn chỉ vì module đã import.
- Không import mọi package trên module path; phạm vi phụ thuộc tên module và quan hệ readability được khai báo.
- Có hiệu lực ở **compilation unit chứa khai báo**, không áp dụng toàn bộ project hoặc mọi class trong package.
- Không phải lệnh runtime để nạp hay khởi tạo toàn bộ class của module.

**“On demand” không phải “nạp tất cả”.** Compiler xem những kiểu phù hợp khi giải quyết tên trong source, còn class loading và execution vẫn theo quy tắc của JVM.

## 4. Ví dụ đầu tiên: một dòng thay nhiều import

Tạo tệp `FruitSummary.java`:

~~~java
import module java.base;

public class FruitSummary {

    public static void main(String[] args) {
        List<String> fruits =
                List.of("apple", "apricot", "banana", "blueberry");

        Map<Character, Long> counts = fruits.stream()
                .collect(Collectors.groupingBy(
                        name -> name.charAt(0),
                        TreeMap::new,
                        Collectors.counting()));

        counts.forEach((initial, count) ->
                System.out.println(initial + ": " + count));
    }
}
~~~

Các kiểu trong ví dụ:

| Kiểu | Package | Module |
| --- | --- | --- |
| `List`, `Map`, `TreeMap` | `java.util` | `java.base` |
| `Collectors` | `java.util.stream` | `java.base` |
| `String`, `Long`, `System` | `java.lang` | `java.base` |

Trong một source file Java thông thường, `java.lang` vốn đã được import ngầm. Giá trị bổ sung của module import thể hiện rõ ở `java.util` và `java.util.stream`: không còn cần viết riêng:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
~~~

Biên dịch và chạy trên JDK 25:

~~~bash
javac --release 25 FruitSummary.java
java FruitSummary
~~~

Kết quả dự kiến:

~~~text
a: 2
b: 2
~~~

Ví dụ không dùng API experimental hay preview. Nó cũng không cần `module-info.java` vì class nằm trên classpath/unnamed module trong tình huống đơn giản này và `java.base` luôn là module nền tảng mà Java code đọc được.

### Phần quan trọng trong ví dụ

`import module java.base;` không thay đổi thuật toán stream, cấu trúc collection hay kết quả thực thi. **Lợi ích chính nằm ở khả năng diễn đạt code**, giảm boilerplate và thuận tiện khi viết ví dụ, utility hoặc thử API mới. Không nên suy ra rằng module import tự làm stream nhanh hơn hay giảm bộ nhớ.

## 5. So sánh với bốn cách import liên quan

| Cú pháp | Tác dụng | Không làm gì? |
| --- | --- | --- |
| `import java.util.List;` | Nhập một kiểu theo canonical name | Không nhập `Map` hay kiểu từ package khác |
| `import java.util.*;` | Nhập on-demand các kiểu accessible của một package | Không nhập `java.util.stream.*` |
| `import module java.base;` | Nhập on-demand kiểu public trong các package được export từ module đọc được | Không mở package nội bộ, không đưa mọi module vào classpath |
| `import static java.util.Collections.emptyList;` | Nhập một static member | Không nhập các kiểu khác chỉ nhờ static import |
| `requires java.sql;` trong `module-info.java` | Khai báo **readability dependency** của một named module | Không tự đặt các kiểu `java.sql.Connection` vào scope với tên ngắn |

Điểm dễ nhầm nhất là **`import module` và `requires` giải quyết hai bài toán khác nhau**:

- `requires M;` là một phần của JPMS module descriptor, xác định module hiện tại đọc được module nào.
- `import module M;` là một khai báo **trong Java source file**, quyết định những kiểu accessible có thể được gọi bằng simple name trong tệp đó.

Với **named module**, nếu thiếu một `requires` cần thiết thì chỉ thêm `import module` không làm module trở nên readable. Với **unnamed module** trên classpath, cách chọn root module và module resolution có những quy tắc riêng; không nên khẳng định mọi module bất kỳ sẽ luôn readable chỉ vì nó hiện diện trên module path.

### Wildcard package import khác module import

~~~java
import java.util.*;
~~~

Có thể tham chiếu `List` nhưng không tự nhập `Collectors` từ `java.util.stream`, vì wildcard package import không bao phủ subpackage.

~~~java
import module java.base;
~~~

Có thể tham chiếu cả `List` và `Collectors` vì **cả hai package được `java.base` export**; không phải vì Java tự coi subpackage là phần con của `java.util` khi import.

## 6. Module import không phải khai báo module JPMS

Đây là hai tệp khác nhau:

~~~java
// Tệp module-info.java
module com.example.reporting {
    requires java.sql;
}
~~~

~~~java
// Tệp com/example/reporting/ReportRunner.java
package com.example.reporting;

import module java.sql;

public class ReportRunner {
    public static void main(String[] args) throws Exception {
        // Có thể dùng tên ngắn của kiểu accessible
        // từ package được java.sql export.
        Class<Connection> connectionType = Connection.class;
        System.out.println(connectionType.getName());
    }
}
~~~

Trong ví dụ:

- `module-info.java` xác lập dependency tới `java.sql`.
- `import module java.sql;` giúp kiểu `java.sql.Connection` được tham chiếu bằng tên `Connection` trong riêng `ReportRunner.java`.
- `Class` và `System` thuộc `java.lang`, được import ngầm theo Java bình thường.
- Không cần tạo database connection chỉ để kiểm tra compiler nhận diện API.
- Nếu bỏ `requires java.sql;` khỏi descriptor, named module không đọc được `java.sql` theo cách ví dụ yêu cầu; `import module java.sql;` không tự khắc phục thiếu dependency.

### Cách tổ chức và biên dịch một named module mẫu

~~~text
src/
└── com.example.reporting/
    ├── module-info.java
    └── com/example/reporting/ReportRunner.java
~~~

Một cách biên dịch bằng JDK 25:

~~~bash
javac --release 25 --module-source-path src \
  -d out -m com.example.reporting

java --module-path out \
  -m com.example.reporting/com.example.reporting.ReportRunner
~~~

Cách làm dùng **module-source-path** với đúng cấu trúc thư mục module, không cần thêm Maven/Gradle để hiểu khái niệm. Với dự án thực tế, dùng build tool hỗ trợ Java 25 và JPMS thay vì tự chạy lệnh compile cho toàn bộ repository.

## 7. Import từ module phụ thuộc theo hướng transitive

Một khác biệt quan trọng của module import so với package wildcard là nó có thể làm việc với **các package export từ module đọc được gián tiếp** do đọc module `M`.

Theo tài liệu Java 25, `java.sql` có các dependency transitively readable liên quan đến `java.logging` và `java.xml`. Một khai báo:

~~~java
import module java.sql;
~~~

có thể cho phép tham chiếu các public top-level types accessible trong các package được những module đó export, không cần thêm `import module java.xml;` chỉ để rút gọn tên.

Ví dụ tối giản với classpath trên JDK 25:

~~~java
// Tệp SqlModuleImports.java
import module java.sql;

public class SqlModuleImports {
    public static void main(String[] args) {
        // java.sql
        System.out.println(Connection.class.getName());

        // java.util.logging, do java.logging export
        System.out.println(Logger.class.getName());

        // javax.xml.parsers, do java.xml export
        System.out.println(DocumentBuilder.class.getName());
    }
}
~~~

Ở đây `Connection`, `Logger`, `DocumentBuilder` được dùng để kiểm tra khả năng nhận diện kiểu; chương trình không kết nối DB hoặc phân tích XML. Các module JDK liên quan vẫn phải nằm trong module graph có thể đọc ở cấu hình compile/runtime tương ứng.

**Không suy ra quan hệ transitive chỉ từ tên module.** Để biết một module yêu cầu module nào, kiểm tra descriptor:

~~~bash
java --describe-module java.sql
~~~

Tìm `requires transitive ...` trong output. Đặc tả xác định tập kiểu được import theo **readability thực tế**, không theo suy đoán “`java.sql` chắc chắn import tất cả module Java”.

## 8. Tình huống với `java.se` và module resolution

`java.se` là module tập hợp mô tả Java SE API, thuận tiện cho các ví dụ cần nhiều API chuẩn. Một khai báo:

~~~java
import module java.se;
~~~

có thể nhập on-demand các kiểu thuộc nhiều module Java SE readable và export các package public tương ứng.

Tuy nhiên, khi biên dịch một class **trên classpath/unnamed module**, `java.se` không nhất thiết là root module mặc định. Tài liệu Java 25 nêu việc thêm:

~~~bash
javac --release 25 --add-modules java.se SeExample.java
~~~

Và khi chạy class phụ thuộc các module được thêm, có thể dùng:

~~~bash
java --add-modules java.se SeExample
~~~

Trong dự án modular có descriptor, hãy khai báo `requires` phù hợp và kiểm tra module graph; không coi `import module java.se;` là cách né JPMS dependency declaration.

**Quyết định thiết kế:** trong ứng dụng nhiều module, import tập Java SE quá rộng có thể làm source file khó kiểm soát tên kiểu và tăng nguy cơ nhập nhằng. Với tutorial nhiều API, việc sử dụng `java.se` có thể giảm boilerplate nhưng phải chú ý module resolution.

## 9. Giới hạn truy cập: chỉ có các kiểu accessible

Giả sử thư viện được định nghĩa:

~~~java
// Tệp module-info.java của thư viện
module com.example.library {
    exports com.example.library.api;
    // Không export com.example.library.internal
}
~~~

~~~java
// Package com.example.library.api
package com.example.library.api;

public class PublicService {
}
~~~

~~~java
// Package com.example.library.internal
package com.example.library.internal;

public class HiddenService {
}
~~~

Module khác có khai báo:

~~~java
import module com.example.library;
~~~

không thể vì thế mà sử dụng `HiddenService` từ package không export. Kể cả khi class nội bộ là `public` trong mã nguồn, JPMS vẫn có thể ngăn truy cập từ module khác.

Thêm các ràng buộc:

- Một package export **có điều kiện** (`exports p to ...`) chỉ accessible với các module được chỉ định.
- Một kiểu package-private không trở thành public nhờ module import.
- Import types không đồng nghĩa với quyền truy cập private members.
- `opens` cho reflection là khái niệm khác với `exports`; `import module` không bổ sung quyền mở package để reflective access.

Trong cùng một named module, code có thể tham chiếu các kiểu của chính module theo quy tắc accessibility thông thường; không nên lẫn cơ chế đó với lời hứa rằng import một module khác sẽ làm lộ internal packages.

## 10. Xử lý tên kiểu nhập nhằng

Vì module import nhập on-demand nhiều package, có thể xuất hiện hai kiểu **cùng simple name**. Ví dụ trong các API còn được hỗ trợ:

- `java.util.List` (interface collection) ở `java.base`.
- `java.awt.List` (GUI component) ở `java.desktop`.
- `java.lang.classfile.Label` và `java.awt.Label` cũng có simple name giống nhau.

Ví dụ minh họa lỗi:

~~~java
import module java.base;
import module java.desktop;

public class AmbiguousTypes {
    List<String> values; // Lỗi: java.util.List hoặc java.awt.List?
}
~~~

Compiler không thể chọn kiểu nào chỉ dựa vào tên ngắn `List`. Đây là lý do import thật rộng không phải lúc nào cũng tốt hơn import tường minh.

### Cách 1 — Ưu tiên explicit single-type import

~~~java
import module java.base;
import module java.desktop;
import java.util.List;

public class ResolvedTypes {
    List<String> values = List.of("one", "two");
    java.awt.List awtList; // Dùng tên đầy đủ khi muốn phân biệt.
}
~~~

Single-type import `import java.util.List;` làm rõ ý đồ và được ưu tiên hơn loại import on-demand khi giải quyết tên. `java.awt.List` chỉ được dùng như ví dụ cho xung đột tên đang tồn tại, **không phải lời khuyên chuyển ứng dụng UI mới sang AWT**.

### Cách 2 — Giữ tên fully qualified tại điểm dùng

~~~java
import module java.base;
import module java.desktop;

public class ExplicitTypes {
    java.util.List<String> items = java.util.List.of("one");
}
~~~

Cách này không cần bổ sung một single-type import, phù hợp nếu chỉ có một điểm dùng hoặc code cần phân biệt rõ hai API.

### Cách 3 — Giảm phạm vi module import

Nếu source không dùng API desktop, bỏ `import module java.desktop;` thay vì giữ nó chỉ vì tiện. Với chương trình lớn, một số import tường minh giúp reviewer dễ xác định loại API mà file phụ thuộc.

**Quy tắc ngắn:** một lỗi ambiguity cần được xử lý bằng **giảm phạm vi import**, **explicit import** hoặc **fully qualified name**, không bằng cách tắt kiểm tra compiler hay thay tên class trong thư viện.

## 11. Kết hợp với compact source files trong Java 25

Java 25 cũng hoàn thiện **Compact Source Files and Instance Main Methods** (JEP 512). Hai tính năng có quan hệ hữu ích:

- Một **ordinary class** như `FruitSummary` phải khai báo module import nếu muốn nhập các kiểu trong `java.base` ngoài các import ngầm thông thường.
- Một **compact source file** tự có hiệu lực tương đương việc import on-demand các public top-level types từ những package mà `java.base` export. Vì vậy, không nhất thiết viết thêm `import module java.base;`.

Ví dụ `MiniCollections.java`:

~~~java
void main() {
    var items = List.of("Java", "25", "module import");
    IO.println(items.stream().collect(Collectors.joining(" / ")));
}
~~~

Chạy trên JDK 25:

~~~bash
java MiniCollections.java
~~~

Ở đây `List` và `Collectors` sử dụng được nhờ cơ chế implicit module import của compact source file, còn `IO` là lớp `java.lang.IO` có sẵn trong Java 25.

Không nên suy ngược rằng **mọi ordinary class** mặc định đã có đầy đủ `java.base` imports. Với ordinary class, `java.lang.*` vẫn được nhập ngầm theo quy tắc Java lâu nay; các package khác như `java.util` không tự trở thành import cho tệp chỉ vì nằm trong `java.base`.

Cả JEP 511 và JEP 512 đều đã trở thành tính năng hoàn thiện trong Java 25. Đây là một tổ hợp hữu ích cho học tập, thử API, bài demo hoặc công cụ ngắn; không phải lý do để thay cấu trúc package/module của hệ thống doanh nghiệp mà không có nhu cầu thực tế.

## 12. Mức source, compiler và cách đóng gói

Module import là **tính năng cú pháp của Java source**, nên cần toolchain hiểu Java 25. Không có yêu cầu chuyển ứng dụng sang JPMS named modules chỉ để dùng nó.

### 12.1. Kiểm tra Java compiler

~~~bash
java -version
javac -version
~~~

Nếu sử dụng JDK 25 và muốn dùng module imports:

~~~bash
javac --release 25 FruitSummary.java
java FruitSummary
~~~

Nếu compiler đang chạy trên JDK cũ hơn 25, nó có thể không nhận dạng cú pháp hoặc chỉ hỗ trợ phiên bản preview đã khác. Với dự án có nhiều JDK, cần phân biệt phiên bản của **process javac**, **compiler target/source release** và **JRE thực sự chạy artifact**.

### 12.2. Trong Maven

Ví dụ cấu hình mức source/target API theo Java 25:

~~~xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
</properties>
~~~

Điều kiện: Maven Compiler Plugin, annotation processors và các plugin liên quan phải hỗ trợ JDK 25; Maven/JDK thực tế phải phù hợp. Không phải cứ sửa `pom.xml` là compiler runtime tự nâng cấp.

### 12.3. Trong Gradle

Một cấu hình toolchain Java 25 minh họa:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}
~~~

Cần dùng phiên bản Gradle và plugin tương thích Java 25. Kiểm tra toolchain được resolve và các task compile/test thật sự chạy đúng JDK mục tiêu. Với multi-module builds, một module library có cam kết hỗ trợ Java 21 **không thể** vô tư dùng `import module` trong source được biên dịch `--release 21`.

### 12.4. Khi cần tương thích Java 21

Một thư viện có API dùng chung cho nhiều ứng dụng Java 21 nên tiếp tục biên dịch bằng `--release 21` và không đưa cú pháp Java 25 vào source chung. Có thể dùng Java 25 **để chạy compiler hoặc runtime trong môi trường kiểm thử**, nhưng `--release 21` vẫn giới hạn source/language/API về đích 21.

Không thể “dịch” `import module` thành bytecode riêng để JVM 21 hiểu nếu compiler ở `--release 21` còn chưa chấp nhận cú pháp. Nếu muốn dùng Java 25 trong phần nội bộ riêng, cần phân chia source sets/artifacts và chính sách tương thích rõ ràng thay vì vô tình phá consumer cũ.

## 13. Khi nào module import đáng dùng?

Bản thân JEP 511 là tính năng ổn định; **lợi ích cụ thể mới quyết định nên áp dụng hay không**.

| Ngữ cảnh | Đánh giá | Lý do |
| --- | --- | --- |
| Bài học Java 25, ví dụ API mới | Rất phù hợp | Giảm boilerplate, giúp tập trung vào ý tưởng |
| Utility/CLI nhỏ chạy Java 25 | Phù hợp | Một khai báo gọn cho nhiều API chuẩn |
| Prototype dùng nhiều package thuộc một module | Phù hợp | Dễ thử chức năng mà không sửa nhiều imports |
| Test/demo ngắn trong repo Java 25 | Tùy style guide | Nhanh viết, nhưng reviewer vẫn cần hiểu nguồn kiểu |
| Source file nghiệp vụ lớn | Cân nhắc | Import tường minh có thể thể hiện dependency tốt hơn |
| Named module với phụ thuộc JPMS được kiểm soát chặt | Cân nhắc | `requires` vẫn là khai báo bắt buộc; import rộng không thay ranh giới |
| Thư viện phải biên dịch cho Java 21 | Không phù hợp | Source Java 25 không đạt `--release 21` |
| File dùng nhiều kiểu có tên trùng nhau | Thường nên explicit import | Tránh ambiguity và khó đọc |
| Module có rất nhiều package exports | Cân nhắc | Một dòng import có thể che khuất nguồn của kiểu |

**Không cần tự động thay mọi `import java.util.List;` bằng `import module java.base;`.** Việc đó có thể tạo thay đổi lớn trong Git mà không cải thiện khả năng bảo trì. Trong codebase nhiều người, giá trị là tăng tính dễ đọc/chất lượng lập trình chứ không phải tối đa hóa số dòng import được xóa.

### Một quy ước thực dụng cho nhóm

- Cho phép module import trong tutorial, demo, mã thử nghiệm và các utility nhỏ.
- Trong module nghiệp vụ lớn, ưu tiên imports tường minh nếu chúng giúp reviewer nhận ra dependencies.
- Khi gặp ambiguity, ưu tiên explicit single-type import hoặc fully qualified type thay vì tiếp tục mở rộng imports.
- Không dùng module import để che giấu hoặc bỏ qua `module-info.java`.
- Không trộn source-level Java 25 vào artifact có cam kết tương thích source Java 21.
- Khi nâng JDK/IDE/plugin, chạy compile/test để bảo đảm formatter, source analyzer và compiler hỗ trợ đúng cú pháp.

## 14. Các hiểu nhầm và lỗi thường gặp

### “`import module java.base;` import mọi thư viện trong JDK”

Không. `java.base` chỉ là module nền tảng. Các API như JDBC hoặc desktop thuộc những module khác. Muốn sử dụng các kiểu khác theo simple name, cần module import phù hợp **và** module đó phải được đọc.

### “Cú pháp đúng là `import module java.base.*;`”

Không. Cú pháp chuẩn là:

~~~java
import module java.base;
~~~

Đừng thêm `.*` sau tên module. `import module` không phải phiên bản mới của package wildcard với dấu sao.

### “Vì JDK 25 là LTS nên tính năng vẫn preview”

Không. JEP 511 hoàn thiện trong Java 25; không cần `--enable-preview`. Một số **tính năng khác** trong JDK 25 có thể còn preview/incubator, nhưng không nên suy điều đó cho module import declarations.

### “Import module cũng thêm `requires` tự động”

Không. Với named module, `module-info.java` phải khai báo dependencies cho JPMS readability. Compiler sẽ không tự thêm dependency vì source file viết `import module M;`.

### “Import module giúp truy cập internal package”

Không. Các quy tắc `exports`, qualified exports, access modifiers và encapsulation vẫn áp dụng. Nó không tương đương `opens`, `--add-opens` hoặc `--add-exports`.

### “Nhiều module imports sẽ luôn làm source dễ đọc hơn”

Không nhất thiết. Nếu hai API có kiểu cùng tên như `List` hoặc `Label`, compiler có thể báo ambiguity. Import cụ thể có thể dễ đọc hơn và ít phải giải quyết xung đột.

### “Module imports tự import static methods”

Không. Muốn gọi `emptyList()` không có tiền tố, vẫn cần import static tương ứng:

~~~java
import module java.base;
import static java.util.Collections.emptyList;

public class StaticImportExample {
    public static void main(String[] args) {
        List<String> names = emptyList();
        System.out.println(names);
    }
}
~~~

Không có `import static` thì vẫn có thể gọi `Collections.emptyList()` nhờ kiểu `Collections` accessible qua `java.base`.

### “Cứ import module `java.se` là không cần cấu hình gì”

Không. Module `java.se` có thể không nằm trong root modules mặc định của unnamed module. Ở ví dụ classpath, tài liệu Java 25 hướng dẫn khai báo `--add-modules java.se` khi biên dịch. Với named module, phải kiểm tra `requires`/readability trong descriptor.

### “Module import làm startup nhanh hơn hoặc giảm bytecode”

Không có bảo đảm đó. Đây chủ yếu là tính năng **source-level name resolution**. Khi đánh giá startup, throughput, GC, AOT cache hay JFR, phải đo các cơ chế JVM thực sự liên quan. Không ghi nhận hiệu năng tăng vì chỉ thay imports nếu chưa có bằng chứng benchmark.

### “Mọi class đều được nhập ngầm `java.base`”

Không. **Compact source files** có hành vi implicit module import `java.base` trong Java 25; ordinary classes không tự được nhập tất cả package của `java.base`. Cần phân biệt hai loại source.

## 15. Bài thực hành có hướng dẫn

### Phần A — Xác nhận tính năng đã hoàn thiện

1. Dùng JDK 25, chạy `java -version` và `javac -version`.
2. Tạo `FruitSummary.java` như phần 4.
3. Biên dịch với `javac --release 25 FruitSummary.java`, chạy và ghi kết quả.
4. Thử biên dịch với `--release 21` trong môi trường kiểm thử. Dự kiến compiler không chấp nhận cú pháp module import.
5. Giải thích vì sao **không cần `--enable-preview`** khi dùng JEP 511 trong Java 25.
6. Đối chiếu `java --describe-module java.base` để xem package exports.

### Phần B — Hiểu module exports và transitive readability

1. Biên dịch ví dụ `SqlModuleImports.java` từ phần 7.
2. Quan sát `java --describe-module java.sql` và xác định các dependency transitive.
3. Trong named module, bỏ `requires java.sql;` rồi thử compile; ghi lại lỗi và khôi phục `requires`.
4. Giải thích vì sao `import module java.sql;` không tự thêm dependency.
5. Nếu dùng `java.se` ở classpath, kiểm tra sự khác biệt khi có và không có `--add-modules java.se`.

### Phần C — Giải quyết ambiguity

1. Biên dịch `AmbiguousTypes.java` từ phần 10, ghi nhận tên kiểu compiler báo nhập nhằng.
2. Thêm `import java.util.List;` rồi compile lại.
3. Dùng fully qualified name `java.awt.List` cho một field riêng mà không cần khởi chạy GUI.
4. Xóa `import module java.desktop;` và ghi nhận source đơn giản hơn khi không có nhu cầu dùng API desktop.
5. Mô tả quy tắc review imports bạn muốn áp dụng cho team.

### Phần D — Kết hợp compact source

1. Tạo `MiniCollections.java` như phần 11, chạy bằng `java MiniCollections.java`.
2. Giải thích vì sao `List` và `Collectors` không cần khai báo `import module java.base;` trong compact source file.
3. Chuyển ví dụ thành ordinary class có static main, thử biên dịch khi bỏ module import.
4. Thêm `import module java.base;` trở lại và so sánh.

### Câu hỏi tự đánh giá

1. Module import declarations được final ở Java mấy và theo JEP nào?
2. Vì sao không nên viết `--enable-preview` chỉ để sử dụng `import module` trên Java 25?
3. `import java.util.*;` có import `java.util.stream.Collectors` không? Vì sao?
4. Một module import có nạp toàn bộ class vào JVM khi chương trình khởi động không?
5. `import module java.sql;` và `requires java.sql;` khác nhau thế nào?
6. `requires transitive` ảnh hưởng thế nào tới tập package được module import đưa vào scope?
7. Tại sao `import module java.base;` cùng `import module java.desktop;` có thể làm `List` nhập nhằng?
8. Vì sao `import module` không cho phép truy cập package nội bộ không export?
9. Khi nào `import static` vẫn cần thiết?
10. Tại sao một named module có thể không dùng được `import module M;` dù M nằm trên module path?
11. Với thư viện còn hỗ trợ Java 21, tại sao không nên đưa cú pháp Java 25 vào source chung?
12. Khi nào một danh sách import tường minh vẫn dễ bảo trì hơn một module import?

## 16. Checklist đưa module import vào dự án

- [ ] Compiler/toolchain hỗ trợ Java 25 và dùng đúng `--release`/source level.
- [ ] Feature được hiểu là **JEP 511 final**, không lẫn với preview ở Java 23/24.
- [ ] Module `M` tồn tại, được resolve và readable ở compilation unit dùng `import module M;`.
- [ ] Với named module, `module-info.java` có `requires` phù hợp.
- [ ] Không phụ thuộc vào internal package, `opens` hoặc access modifier bị giới hạn.
- [ ] Đã kiểm tra xung đột simple name sau khi thêm module import.
- [ ] Khi có ambiguity, đã chọn explicit import/fully qualified type hoặc giảm phạm vi.
- [ ] Không kỳ vọng module import thay thế `import static`.
- [ ] Không nhầm ordinary class với compact source file có implicit `java.base` module import.
- [ ] Source compatibility với các consumer còn dùng JDK cũ được kiểm tra.
- [ ] Maven/Gradle/IDE/linter/annotation processor có thể phân tích source Java 25.
- [ ] Đã đánh giá khả năng đọc code; không refactor toàn repo chỉ vì cú pháp mới.
- [ ] Compile/test thành công và không có thay đổi hành vi runtime ngoài dự kiến.

**Tiêu chí hoàn thành:** người học hiểu `import module M;` là cú pháp **chính thức từ Java 25**, cho phép dùng tên ngắn của các public top-level types từ package được module readable export, bao gồm những export liên quan qua readability transitive khi thích hợp. Người học phải phân biệt được **name imports** với **JPMS dependencies**, giải quyết ambiguity và chọn module imports khi chúng thực sự làm source code dễ viết, dễ đọc hơn.

## 17. Tài liệu chính thức và khả năng áp dụng về sau

- [JEP 511 — Module Import Declarations](https://openjdk.org/jeps/511): JEP đưa tính năng vào Java 25 dưới trạng thái final.
- [Oracle Java SE 25 — Module Import Declarations](https://docs.oracle.com/en/java/javase/25/language/module-import-declarations.html): hướng dẫn cú pháp, phạm vi, nhập nhằng và ví dụ `java.sql` / `java.se`.
- [Oracle Java SE 25 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): xác nhận module import declarations đã trở thành tính năng permanent trong Java 25.
- [Oracle Java SE 25 — Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): quan hệ với implicit import của `java.base`.
- [Java SE 25 — java.lang.module API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/package-summary.html): nền tảng module resolution/readability.
- [Java SE 25 — javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): các tham số `--release`, `--module-source-path`, `--add-modules` và biên dịch named module.

**Lưu ý cập nhật kiến thức:** đối với code trên Java 25, JEP 511 đã là **final**, không nên tham chiếu hướng dẫn preview Java 23/24 để khẳng định vẫn phải dùng `--enable-preview`. Khi đưa code sang JDK mới hơn hoặc cập nhật IDE/build tool, hãy kiểm tra tài liệu theo **JDK mục tiêu thực tế**, nhưng không xem module import là một tính năng đã legacy hoặc cần tránh sử dụng chỉ vì nó được giới thiệu qua giai đoạn preview.

