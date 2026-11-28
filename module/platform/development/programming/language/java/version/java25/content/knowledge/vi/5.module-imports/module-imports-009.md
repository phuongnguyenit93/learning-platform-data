# Chọn module import theo tính rõ ràng, quy ước dự án và khả năng bảo trì

## 1. Bài toán: ít dòng import hơn có đồng nghĩa dễ bảo trì hơn?

Khi dùng Java, cùng một thao tác có thể đòi hỏi nhiều kiểu đến từ những package khác nhau:

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;
~~~

Với **Java 25**, các kiểu công khai trong những package được module `java.base` export có thể được đưa vào phạm vi tham chiếu bằng một dòng:

~~~java
import module java.base;
~~~

Đây là **module import declaration** theo JEP 511, một tính năng **chính thức** từ Java 25, không còn là preview. Nhưng rút từ bốn dòng xuống một dòng **chưa đủ để kết luận** cách mới tốt hơn với mọi file: import theo module mở rộng tập tên có thể được dùng, làm tăng khả năng trùng tên, và đôi khi che khuất thông tin về API mà lớp đang phụ thuộc.

Bài **Chọn module import theo tính rõ ràng, quy ước dự án và khả năng bảo trì** thuộc chương **Module import** của module **JAVA_VERSION_JAVA25**. Nội dung chọn lọc kiến thức **còn đúng và hữu ích ở Java 25 trở về sau**, không áp dụng hướng dẫn cũ yêu cầu bật `--enable-preview` cho JEP 511.

Module JAVA_VERSION_JAVA25 còn đề cập compact source files, instance main, constructor linh hoạt, `ScopedValue`, API dẫn xuất khóa, AOT cache và JFR. Ở bài này, những khả năng đó chỉ xuất hiện như **bối cảnh sử dụng kiểu Java**; trọng tâm là cách viết import sao cho người đọc hiểu phụ thuộc và bản build tiếp tục ổn định khi dự án lớn lên.

### Sau bài này bạn có thể

1. Nêu chính xác ý nghĩa của `import module M;`, đặc biệt điều kiện **export** và **readability**.
2. Phân biệt module import, single-type import, package wildcard import và `requires` trong `module-info.java`.
3. Quyết định khi nào ưu tiên `import module java.base;` hoặc một module nghiệp vụ; khi nào dùng danh sách type import rõ ràng.
4. Phát hiện xung đột `List`, `Date` hoặc các kiểu cùng tên từ những module/package khác nhau.
5. Xây dựng quy ước import phù hợp cho script ngắn, compact source file, module JPMS, thư viện dùng chung và dự án nhiều nhóm.
6. Giữ code dễ đọc khi thêm dependency hoặc nâng phiên bản JDK mà không làm thay đổi vô tình kiểu được resolve.
7. Viết kiểm tra build/CI và quy trình code review khi chuyển từ kiểu import này sang kiểu import khác.

> **Phạm vi kỹ thuật:** Java SE 25/JDK 25, JEP 511 và Java Language Specification (JLS) `7.5.5. Các ví dụ độc lập, dùng những API có sẵn trong JDK; một ví dụ về module tự định nghĩa chỉ mang tính mô hình. Trên Java 25, `import module` **không cần `--enable-preview`**.

## 2. Module import làm gì theo Java 25?

Cú pháp:

~~~java
import module java.base;
~~~

Hoặc tổng quát:

~~~text
import module <module-name>;
~~~

Theo JLS `7.5.5, một **single-module-import declaration** làm cho các kiểu **public top-level class/interface** thuộc những package được module chỉ định export đến compilation unit hiện tại có thể được tham chiếu bằng **simple name** (*on demand*).

Nó còn bao gồm các kiểu public từ package được những module liên quan export khi chúng được đọc nhờ **`requires transitive`** trong chuỗi phụ thuộc của module import.

Ví dụ:

~~~java
import module java.base;

class InventorySummary {
    public static void main(String[] args) {
        Map<String, Integer> stock = Map.of(
            "book", 3,
            "pen", 12
        );

        List<String> lowStock = stock.entrySet().stream()
            .filter(entry -> entry.getValue() < 5)
            .map(Map.Entry::getKey)
            .toList();

        System.out.println(lowStock);
    }
}
~~~

Khi chạy với JDK 25:

~~~bash
java InventorySummary.java
~~~

`Map` thuộc `java.util`, `List` cũng thuộc `java.util`, và `Stream` được dùng qua API của các collection trong Java SE. Các kiểu public của những package được `java.base` export đều nằm trong tập ứng viên import.

**Không có nghĩa** JVM phải load mọi class trong `java.base` khi thực thi. `import` là cơ chế hỗ trợ **phân giải tên ở mã nguồn**, không phải lệnh eager-load tất cả classes.

### Các giới hạn nền tảng

- Chỉ các kiểu **accessible** mới dùng được. `import module` không phá được ranh giới `exports` của JPMS.
- Không tự động import **static method/field**. Nếu muốn gọi `emptyList()` thay vì `Collections.emptyList()`, vẫn cần `import static java.util.Collections.emptyList;` hoặc tên đầy đủ.
- Không tự đưa mọi **nested class** vào scope như single-type import trực tiếp. Có thể dùng `Map.Entry` hoặc import kiểu lồng rõ ràng khi cần.
- Không làm cho một module trở thành dependency ở runtime. **Module readability** phải thỏa mãn độc lập.
- Không tác động file Java khác trong cùng package; phạm vi `import` chỉ trong **compilation unit** chứa nó.
- Không tạo API mới trong JDK, không thay đổi thuật toán, performance hoặc cách tải JAR chỉ vì thay các câu lệnh import.

## 3. Bốn cách đưa kiểu vào phạm vi tham chiếu

Giả sử một class dùng `List`, `Map` và `Collectors`.

| Cách viết | Ví dụ | Phạm vi đưa tên vào | Đặc điểm |
| --- | --- | --- | --- |
| Single-type | `import java.util.List;` | Một kiểu cụ thể | Nguồn gốc kiểu rõ, dễ review |
| Package on-demand | `import java.util.*;` | Các kiểu accessible của một package | Gọn hơn, nhưng không bao gồm subpackage |
| Module on-demand | `import module java.base;` | Các kiểu accessible thuộc các exported packages và transitive dependencies phù hợp | Gọn khi dùng nhiều package của một module |
| Fully qualified name | `java.util.List<String>` | Chỉ tham chiếu cụ thể tại chỗ | Rõ tuyệt đối ở điểm dùng, hơi dài nếu lặp |

**Đừng nhầm hai kiểu wildcard:**

~~~java
import java.util.*;       // Không import java.util.stream.Stream.
import module java.base;  // Có thể làm Stream xuất hiện qua java.util.stream.
~~~

`java.util.*` chỉ nhắc tới một package, **không duyệt xuống tất cả subpackage**. `import module java.base` bao phủ các package được module này export, không chỉ một cây package tùy ý.

### Ví dụ so sánh

**Import từng type:**

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class MapReport {
    public static void main(String[] args) {
        Map<Character, String> grouped = Stream.of(
                "apple", "banana", "cherry")
            .collect(Collectors.toMap(
                text -> text.charAt(0),
                Function.identity()));

        System.out.println(grouped);
    }
}
~~~

**Import theo module:**

~~~java
import module java.base;

public class MapReport {
    public static void main(String[] args) {
        Map<Character, String> grouped = Stream.of(
                "apple", "banana", "cherry")
            .collect(Collectors.toMap(
                text -> text.charAt(0),
                Function.identity()));

        System.out.println(grouped);
    }
}
~~~

Hai phiên bản hướng tới **cùng kiểu, cùng logic và cùng kết quả**. Mức độ “tốt” nên được đánh giá qua khả năng hiểu source, số kiểu sử dụng, rủi ro nhập nhằng và quy ước trong repository.

## 4. Cây quyết định: khi nào nên dùng import module?

~~~mermaid
flowchart TD
    A[Cần dùng kiểu từ module đã đọc được?] --> B{Có module rõ ràng và được export?}
    B -- Không --> X[Giải quyết requires / dependency / exports]
    B -- Có --> C{Chỉ dùng vài kiểu rõ nguồn gốc?}
    C -- Có --> D[Ưu tiên single-type imports]
    C -- Không --> E{Dùng nhiều package trong một module nhất quán?}
    E -- Không --> D
    E -- Có --> F{Dễ trùng tên hoặc public API nhạy cảm?}
    F -- Có --> G[Dùng explicit imports hoặc kết hợp]
    F -- Không --> H{Dự án/toolchain chấp nhận Java 25?}
    H -- Không --> D
    H -- Có --> I[Cân nhắc import module]
    I --> J[Compile + review + kiểm tra quy ước]
    G --> J
    D --> J
~~~

### Quy tắc ngắn cho nhóm phát triển

1. **Ít kiểu, nguồn gốc quan trọng:** dùng `import java.util.List;`, `import java.time.Instant;`.
2. **Nhiều kiểu thuộc một module cohesive:** cân nhắc `import module java.base;` hoặc `import module java.xml;`.
3. **Có tên phổ biến dễ đụng nhau:** giữ single-type import cho `List`, `Date`, `Element`, `Label` hoặc dùng fully qualified names ở điểm nhạy cảm.
4. **Public API, thư viện, code sống lâu:** ưu tiên sự tường minh, đừng thay hàng loạt imports chỉ vì muốn ít dòng hơn.
5. **Compact source file nhỏ:** chấp nhận import ngầm định của `java.base`, không cần thêm một dòng import trùng.
6. **Nhiều module/phiên bản thư viện:** bảo đảm `module-info.java` và dependency graph trước; import chỉ giúp tên ngắn hơn.
7. **Repository có style guide:** tuân theo quy ước hiện tại hoặc thay đổi nó bằng một RFC/PR riêng, không pha trộn tùy hứng.

## 5. Tình huống A — chương trình thử nghiệm, ví dụ học tập

Nếu chương trình chỉ có một tệp và dùng nhiều collection, stream, date/time trong `java.base`, module import rất hữu ích.

Tệp `DailyNotes.java`:

~~~java
import module java.base;

public class DailyNotes {
    public static void main(String[] args) {
        List<String> tasks = List.of(
            "Đọc code",
            "Chạy test",
            "Review PR");

        Map<Integer, String> index = new LinkedHashMap<>();
        for (int i = 0; i < tasks.size(); i++) {
            index.put(i + 1, tasks.get(i));
        }

        LocalDate today = LocalDate.now();

        index.forEach((key, value) ->
            System.out.println(today + " #" + key + ": " + value));
    }
}
~~~

Chạy:

~~~bash
java DailyNotes.java
~~~

Tại đây, `List`/`Map`/`LinkedHashMap` thuộc `java.util`, `LocalDate` thuộc `java.time`. Thay vì bốn single-type imports, một `import module java.base;` phù hợp vì mọi kiểu nằm trong cùng module chuẩn và mục tiêu chính là đọc logic chương trình.

### Khi dùng compact source file Java 25

Tệp `QuickNotes.java`:

~~~java
void main() {
    List<String> tasks = List.of("Compile", "Test", "Deploy");
    Map<String, Integer> lengths = tasks.stream()
        .collect(Collectors.toMap(
            Function.identity(),
            String::length));

    IO.println(lengths);
}
~~~

Chạy:

~~~bash
java QuickNotes.java
~~~

Đây là **compact source file** (JEP 512). Theo Java SE 25, một compact compilation unit đã **ngầm import on-demand những kiểu public trong các package được `java.base` export**, tương đương `import module java.base;`. Vì vậy `List`, `Map`, `Collectors` và `Function` dùng được mà không cần import explicit.

**Không thêm dòng `import module java.base;` chỉ vì máy móc** nếu compilation unit vốn đã có import ngầm định tương đương. Khi chuyển sang class tường minh, cần thêm các imports hoặc chọn module import theo quy ước.

## 6. Tình huống B — code nghiệp vụ trong dự án lâu dài

Một service nhỏ có thể chỉ dùng vài kiểu chuẩn:

~~~java
package vn.acme.orders;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record OrderSnapshot(
        UUID orderId,
        Instant createdAt,
        List<String> items) {
}
~~~

Với **public contract** kiểu `OrderSnapshot`, tên import tường minh giúp:

- Người review nhìn thấy những type API đang sử dụng mà không cần tra tìm cả module.
- Công cụ phân tích và code navigation dễ đối chiếu với dependency danh nghĩa.
- Rủi ro nhận nhầm một kiểu cùng simple name khi thêm import/module mới nhỏ hơn.
- Các thay đổi API trong release có thể được so sánh rõ giữa các PR.

`import module java.base;` **cũng là Java hợp lệ** cho ví dụ trên, nhưng số dòng tiết kiệm không đáng kể. Đây là **khuyến nghị quy ước bảo trì**, không phải yêu cầu bắt buộc của ngôn ngữ.

### Kịch bản dễ chọn sai

Một controller nhận cả dữ liệu JDBC và domain object, dùng `Date` và `Time` nhiều nơi. Nếu dùng module import rộng, người đọc phải xác định đó là `java.util.Date`, `java.sql.Date`, `java.time` type hay class khác. Với code có ý nghĩa nghiệp vụ và thời gian, nên chọn kiểu hiện đại **đúng mục đích** (ví dụ `LocalDate`, `Instant` hoặc kiểu JDBC cụ thể), import tường minh hoặc ghi canonical name khi có va chạm.

**Import không sửa được mô hình domain.** Đổi từ `java.util.Date` sang `java.time.Instant` là **thay đổi API**, không chỉ thay đổi style.

## 7. Tình huống C — dùng module chuyên biệt trong JDK

Không phải mọi module import đều rộng như `java.base`.

### 7.1. Ví dụ java.sql không cần database thật

Tệp `JdbcInfo.java`:

~~~java
import module java.sql;
import java.util.Enumeration;

public class JdbcInfo {
    public static void main(String[] args) {
        Enumeration<Driver> drivers = DriverManager.getDrivers();

        int count = 0;
        while (drivers.hasMoreElements()) {
            Driver driver = drivers.nextElement();
            System.out.println(driver.getClass().getName());
            count++;
        }

        System.out.println("Available JDBC drivers: " + count);
    }
}
~~~

`Driver` và `DriverManager` thuộc `java.sql`, còn `Enumeration` thuộc `java.util` nên ví dụ import tường minh `java.util.Enumeration`. Cách kết hợp này giữ nguồn gốc kiểu rõ ràng và tránh dựa vào chuỗi `requires transitive` không cần thiết. Lưu ý một JDK sạch có thể không có JDBC driver từ bên thứ ba, nên kết quả count = 0 là **bình thường**, không có nghĩa `import module` không hoạt động.

Chạy:

~~~bash
java JdbcInfo.java
~~~

Nếu một ứng dụng thực tế kết nối PostgreSQL, driver JAR và cấu hình database vẫn phải có trên classpath/module path. `import module java.sql;` **không tải driver**, không mở database connection và không cấu hình datasource.

### 7.2. Ví dụ java.xml

Tệp `XPathReport.java`:

~~~java
import module java.xml;

public class XPathReport {
    public static void main(String[] args) throws Exception {
        XPath xpath = XPathFactory.newInstance().newXPath();
        String xml = "<catalog><item>Java 25</item></catalog>";

        InputSource source = new InputSource(new StringReader(xml));
        String value = xpath.evaluate("/catalog/item", source);

        System.out.println(value);
    }
}
~~~

`XPath`/`XPathFactory` được export từ các package trong `java.xml`. Tuy nhiên, `InputSource` cũng nằm trong package do `java.xml` export, còn `StringReader` thuộc `java.base` và được đưa vào scope nếu module graph cho phép đọc transitively.

Để **tránh phụ thuộc vào một giả định transitive không cần thiết** khi code sản phẩm sử dụng `StringReader`, nên thêm một import rõ:

~~~java
import module java.xml;
import java.io.StringReader;
~~~

Đây là một ví dụ quy ước **kết hợp module import với single-type import** để tập trung giải thích vai trò API ở điểm cần thiết. Chẳng có luật nào buộc mọi import trong một file phải thuộc cùng một dạng.

> Lưu ý kỹ thuật: module import chỉ có hiệu lực khi module được code hiện tại **đọc**. Trên classpath, các Java SE modules thông dụng như `java.sql`/`java.xml` thường có trong tập modules được resolve. Trong named JPMS module, điều này phụ thuộc `module-info.java` và `requires`.

## 8. Ranh giới quan trọng: import module khác requires module

Hai khai báo trông giống nhau nhưng **phục vụ hai tầng khác nhau**:

~~~java
import module java.sql;
~~~

~~~java
module vn.acme.reporting {
    requires java.sql;
}
~~~

| Câu lệnh | Nơi sử dụng | Ý nghĩa |
| --- | --- | --- |
| `import module java.sql;` | Một tệp source Java | Cho phép dùng simple names từ exported packages được đọc |
| `requires java.sql;` | Trong `module-info.java` của một named module | Khai báo module dependency và module readability |
| `requires transitive java.sql;` | Trong `module-info.java` | Người đọc module hiện tại cũng đọc `java.sql` |
| `exports vn.acme.reporting.api;` | Trong `module-info.java` | Cho phép các module khác truy cập public types của package được export |
| `opens ...` | Trong `module-info.java` | Điều khiển mở package cho deep reflection theo quy tắc JPMS |

**Không thể thay `requires java.sql;` bằng `import module java.sql;`** nếu source thuộc named module chưa có quyền đọc `java.sql`. Theo JLS, module import sẽ gây compile-time error khi module được import không được module hiện tại đọc.

### 8.1. Ví dụ named Java module có thể biên dịch

Cấu trúc:

~~~text
module-import-demo/
└── src/
    └── main/
        └── java/
            ├── module-info.java
            └── vn/
                └── acme/
                    └── reporting/
                        └── Main.java
~~~

`module-info.java`:

~~~java
module vn.acme.reporting {
    requires java.sql;
}
~~~

`vn/acme/reporting/Main.java`:

~~~java
package vn.acme.reporting;

import module java.sql;
import java.util.Enumeration;

public class Main {
    public static void main(String[] args) {
        int count = 0;
        Enumeration<Driver> drivers = DriverManager.getDrivers();

        while (drivers.hasMoreElements()) {
            System.out.println(drivers.nextElement().getClass().getName());
            count++;
        }

        System.out.println("Detected drivers: " + count);
    }
}
~~~

Biên dịch từ thư mục gốc ví dụ:

~~~bash
javac --release 25 -d out \
    src/main/java/module-info.java \
    src/main/java/vn/acme/reporting/Main.java
~~~

Chạy:

~~~bash
java --module-path out --module vn.acme.reporting/vn.acme.reporting.Main
~~~

Lệnh này không đòi hỏi JDBC driver bên ngoài chỉ để liệt kê drivers. `requires java.sql;` cho phép named module đọc `java.sql`; `import module java.sql;` giải quyết simple names.

### 8.2. Nếu bỏ requires?

Vẫn giữ `import module java.sql;` ở `Main.java` nhưng xóa `requires java.sql;` trong `module-info.java`. Trong named module `vn.acme.reporting`, compiler không được phép dùng module chưa được đọc, do đó build thất bại. Đừng chữa bằng `--add-reads` ở mọi môi trường nếu dependency đó là phần thiết kế lâu dài: **khai báo requires rõ ràng** là lựa chọn đúng cho named module.

## 9. Import không vượt qua exports hay phạm vi public

Một thư viện JPMS có thể khai báo:

~~~java
module vn.acme.catalog {
    exports vn.acme.catalog.api;
}
~~~

Và giữ implementation trong:

~~~text
vn.acme.catalog.api.Product
vn.acme.catalog.internal.ProductStore
~~~

Giả sử module consumer đã khai báo:

~~~java
module vn.acme.orders {
    requires vn.acme.catalog;
}
~~~

Trong một source thuộc `vn.acme.orders`:

~~~java
import module vn.acme.catalog;
~~~

Những public top-level types từ `vn.acme.catalog.api` có thể trở thành ứng viên import. Type trong package `vn.acme.catalog.internal` **không được export** nên không dùng được chỉ nhờ câu lệnh module import.

`public class` cũng không đồng nghĩa package của nó được JPMS export. Để truy cập từ named module khác, cần cả **accessibility của type** và **readability/export** phù hợp.

### Qualified exports và requires transitive

Ví dụ giả định:

~~~text
module catalog {
    exports api;
    exports special to orders;
    requires transitive pricing;
    requires audit;
}
~~~

Nếu `orders` đọc `catalog`, import module catalog có thể đưa kiểu public từ `api`, `special` (vì export riêng tới orders) và exported packages của `pricing` trong tập đọc transitive. Nó **không** nhập package chỉ export cho module khác hoặc các kiểu từ `audit` nếu catalog chỉ `requires audit` thông thường.

Đây là lý do module import không đơn giản tương đương “import tất cả package trong JAR”. Nó phản ánh **contract của JPMS** và quan hệ module được read.

~~~mermaid
flowchart LR
    O[Module orders] -->|requires| C[Module catalog]
    C -->|exports api| P[Public API types]
    C -->|exports special to orders| S[Qualified API types]
    C -->|requires transitive| R[Module pricing]
    C -->|requires| A[Module audit]
    R -->|exports| T[Pricing public API]
    A -.->|Không mặc định thêm qua import catalog| X[Audit public API]
~~~

Khi thư viện sửa `exports` hoặc `requires transitive`, **tập simple names** của `import module ...` cũng có thể đổi. Với nhiều repository, đó là một yếu tố cần tính khi chọn module import trong code có tuổi thọ dài.

## 10. Xung đột tên: vấn đề lớn nhất về tính rõ ràng

Module import là **on-demand**: tên chỉ được giải quyết khi thực sự sử dụng. Nếu hai module/package có các top-level types cùng simple name, compiler có thể báo **ambiguous reference**.

### 10.1. Ví dụ List của java.util và java.awt

Tệp `AmbiguousList.java`:

~~~java
import module java.base;
import module java.desktop;

class AmbiguousList {
    public static void main(String[] args) {
        List<String> values = List.of("a", "b");
        System.out.println(values);
    }
}
~~~

Trên JDK 25, `List` có thể là `java.util.List` (interface) hoặc `java.awt.List` (class). Trình biên dịch không chọn một kiểu theo “ý định có vẻ hợp lý” của người viết; sẽ có lỗi ambiguous reference.

Chạy để thấy lỗi có kiểm soát:

~~~bash
javac --release 25 AmbiguousList.java
~~~

Đây là **ví dụ cố ý không biên dịch được**, không đưa vào nhánh build sản phẩm.

### 10.2. Sửa bằng single-type import

~~~java
import module java.base;
import module java.desktop;
import java.util.List;

class ResolvedList {
    public static void main(String[] args) {
        List<String> values = List.of("a", "b");
        System.out.println(values);
    }
}
~~~

`import java.util.List;` cung cấp một lựa chọn tường minh cho simple name `List`, giải quyết va chạm từ module imports.

Nếu file thực sự cần **cả hai** kiểu, có thể viết:

~~~java
import java.util.List;

class BothLists {
    void use() {
        List<String> items = List.of("a", "b");
        java.awt.List awtList = new java.awt.List();
        awtList.add(items.get(0));
    }
}
~~~

Tùy giao diện hoặc môi trường runtime, `java.awt.List` có thể cần môi trường đồ họa; đây là **ví dụ type resolution**, không phải hướng dẫn chạy GUI trên headless server.

### 10.3. Một module import cũng có thể gây trùng tên

Không phải chỉ khi import **hai module** mới có ambiguity. Một module có thể export **nhiều package** với các kiểu cùng simple name.

Ví dụ `java.desktop` export những package chứa `Element` từ `javax.swing.text` và `javax.swing.text.html.parser`. Một file chỉ có:

~~~java
import module java.desktop;

class ParseModel {
    Element element;  // Có thể ambiguous nếu không chọn kiểu cụ thể
}
~~~

Có thể sửa bằng:

~~~java
import module java.desktop;
import javax.swing.text.Element;
~~~

**Quy ước review:** sau khi thay nhiều single-type imports bằng một module import, **compile lại toàn bộ source có sử dụng các simple names dễ va chạm**, kể cả những tên không trùng trong các import cũ.

### 10.4. Java 25 còn có các kiểu mới với tên quen thuộc

Ví dụ Oracle Java 25 nêu tên `Label` xuất hiện trong cả `java.lang.classfile.Label` (từ `java.base`) và `java.awt.Label` (từ `java.desktop`). Điều này minh họa rủi ro khi tập API được export **mở rộng theo phiên bản JDK**.

Nếu code liên quan bytecode/class-file API, dùng tên rõ như:

~~~java
import java.lang.classfile.Label;
~~~

Nếu code thuộc AWT, dùng:

~~~java
import java.awt.Label;
~~~

Không nên chỉ dựa vào thói quen “Label chắc chắn là AWT” sau khi có module import rộng.

## 11. Thứ tự phân giải tên và cách sửa khi lỗi

Khi compiler gặp simple name như `List`, nó áp dụng các quy tắc scope, shadowing và import theo JLS. Đối với module import, các điểm quan trọng là:

1. Kiểu khai báo trong phạm vi gần, kiểu trong cùng package và các quy tắc shadowing có thể chi phối lookup.
2. **Single-type import** tường minh có thể giải quyết ambiguity từ module imports.
3. **Package on-demand import** có thể được ưu tiên so với module on-demand import theo quy tắc Java 25.
4. Hai kiểu có cùng simple name đến từ các module imports mà không có lựa chọn rõ hơn sẽ gây compile-time error.
5. Hai conflicting single-type imports khác nhau **không** được cứu bằng việc thêm module import.

Để giảm độ phức tạp cho người đọc, dự án nên chọn một quy ước dễ dự đoán: nếu một simple name có thể thuộc nhiều package, **ưu tiên import từng type**; đừng buộc người review ghi nhớ mọi quy tắc shadowing.

### Ví dụ import package rõ hơn module import

~~~java
import module java.desktop;
import java.util.*;

class PackageWins {
    java.util.List<String> items =
        List.of("one", "two");
}
~~~

Dòng `import java.util.*;` làm `java.util.List` có thể được chọn từ package import theo quy tắc hiện hành. Tuy nhiên, trong code sống lâu, biến thể **rõ ràng hơn** thường là:

~~~java
import module java.desktop;
import java.util.List;
~~~

Thêm một single-type import làm trực tiếp hiện ý định sử dụng và giúp công cụ review dễ hiểu.

> Dùng `java.util.List<String>` ở field declaration trong ví dụ để nhấn mạnh canonical name; nếu đã chọn package hoặc single-type import phù hợp, có thể viết ngắn thành `List<String>`.

## 12. import module java.se: có nên dùng cho mọi chương trình?

`java.se` là **aggregator module**: nó không export package trực tiếp nhưng yêu cầu transitively các module Java SE khác, nên `import module java.se;` có thể đưa **rất nhiều** public types vào scope.

~~~java
import module java.se;

class AllJavaSe {
    public static void main(String[] args) {
        System.out.println(LocalDate.now());
    }
}
~~~

Theo tài liệu Java 25, với chương trình trong **unnamed module/classpath**, cần chú ý `java.se` không thuộc tập **default root modules** thông thường; ví dụ cần làm cho module đó được resolve bằng `--add-modules java.se`:

~~~bash
java --add-modules java.se AllJavaSe.java
~~~

Trong named module, cách đúng là khai báo dependency/readability tương ứng ở `module-info.java` khi có chủ đích, chứ không kỳ vọng import sẽ tự kích hoạt cả nền tảng.

### Vì sao không dùng java.se mặc định?

- **Ý định phụ thuộc quá rộng:** một class chỉ dùng `Map` và `LocalDate` mà import toàn bộ Java SE không làm dependency dễ hiểu hơn.
- **Xung đột tên:** nhiều package hơn có thể đưa `List`, `Date`, `Element`, `Label` từ các ngữ cảnh khác nhau vào scope.
- **Khó kiểm soát trong review:** thay đổi module graph/JDK có thể mang thêm kiểu vào tập candidates.
- **Phụ thuộc vào cấu hình launch/module resolution:** có thêm điều kiện môi trường phải diễn giải.
- **Code conventions khó duy trì:** developer có thể tưởng mình được dùng mọi kiểu nền tảng mà không xem xét module design.

`import module java.se;` vẫn là lựa chọn hợp lệ cho **thí nghiệm, công cụ nhỏ hoặc một nguồn đặc biệt cần API từ rất nhiều standard modules**. Nó không phải “cú pháp bị cấm” — chỉ có phạm vi rộng hơn đa số file sản phẩm cần thiết.

## 13. Import module trong module-info.java có cần không?

Java SE 25 cho phép import declarations xuất hiện trong **modular compilation unit**, tức file chứa `module` declaration. Ví dụ công cụ thư viện cung cấp một provider sử dụng `Driver` từ `java.sql`:

~~~java
import module java.sql;

module vn.acme.jdbc {
    requires transitive java.sql;
    provides Driver with vn.acme.jdbc.AcmeDriver;
}
~~~

Ví dụ này minh họa khả năng dùng simple name `Driver` trong `provides`, giả định `AcmeDriver` là một implementation hợp lệ của `java.sql.Driver` và các quy tắc dịch vụ/module đều được thỏa mãn.

Tuy nhiên, khi review **module descriptor**, nhiều nhóm sẽ ưu tiên:

~~~java
module vn.acme.jdbc {
    requires transitive java.sql;
    provides java.sql.Driver
        with vn.acme.jdbc.AcmeDriver;
}
~~~

Tên `java.sql.Driver` làm quan hệ dịch vụ tường minh trong tập tin kiến trúc quan trọng nhất của module. **Không có luật bắt buộc** dùng dạng thứ hai, nhưng nó dễ đọc hơn với người mới học JPMS và giúp tránh coi `import module` là một thay thế cho `requires`.

## 14. Quy ước import phù hợp từng loại dự án

Một style guide hiệu quả cần trả lời: loại code nào được ưu tiên module import, loại code nào cần explicit type imports, làm gì khi xuất hiện ambiguity và ai chịu trách nhiệm thay đổi quy ước.

| Loại code | Lựa chọn mặc định nên cân nhắc | Lý do |
| --- | --- | --- |
| Một file demo/CLI ngắn | `import module java.base;` hoặc compact source import ngầm | Giảm nhiễu, tập trung thuật toán |
| Ví dụ thao tác nhiều API của `java.xml` | `import module java.xml;` | API của module khá cohesive |
| File chỉ dùng 2–4 kiểu | Single-type imports | Dễ biết dependency |
| Public domain contract, DTO, API library | Single-type imports | Tính ổn định và rõ nghĩa quan trọng |
| Code chứa `List`, `Date`, `Element`, `Label` | Single-type hoặc canonical names | Tránh ambiguity |
| Named module dùng JPMS | `requires`/`exports` rõ ràng; chọn imports theo file | Không trộn hai tầng trách nhiệm |
| Code nhận nhiều transitive dependencies | Explicit imports cho kiểu quan trọng | Tránh che dấu dependency thực tế |
| Generated code | Theo generator/template được phiên bản hóa | Tránh diff vô ích khi regenerate |
| Legacy code đang chạy ổn | Chỉ chuyển đổi khi có lợi ích cụ thể | Không tăng rủi ro chỉ vì style mới |
| Dự án đa JDK/chưa nâng compiler | Giữ cú pháp mà release thấp nhất hiểu | JDK < 25 không hiểu final syntax theo cùng điều kiện |

Đây là **khuyến nghị đội ngũ**, không phải hạn chế của Java. Một repository có thể chọn cho phép module import rộng hơn nếu sở hữu bộ test, IDE support và review convention phù hợp.

### Ví dụ policy ngắn có thể đưa vào tài liệu dự án

> **Java 25 import convention**
>
> - Dùng single-type imports cho code thuộc public API, domain model và module boundary quan trọng.
> - Cho phép `import module java.base;` trong demos, compact utilities hoặc tệp dùng đủ nhiều package Java SE để cải thiện tính đọc.
> - Cho phép `import module M;` với thư viện JPMS cohesive khi project khai báo dependency/readability và test compile rõ.
> - Khi có simple-name collision, bổ sung explicit single-type import hoặc canonical name, không dùng tên nhập nhằng.
> - Tránh `import module java.se;` mặc định trong production code.
> - Không sử dụng `--enable-preview` cho JEP 511 trên JDK 25.
> - Không thực hiện đổi import hàng loạt trong cùng PR với nâng cấp library/build hoặc refactor nghiệp vụ lớn.

Một policy ít dòng nhưng có **ví dụ ngoại lệ** thường dễ tuân thủ hơn một lệnh cấm tuyệt đối.

## 15. Khả năng bảo trì khi thư viện và module graph thay đổi

Có hai loại thay đổi đáng chú ý:

### 15.1. Thư viện thêm package/type export mới

Giả sử phiên bản trước của module `vn.acme.catalog` export một package duy nhất. Bản mới export thêm package có kiểu `Result` trùng tên với kiểu từ module khác. Source dùng:

~~~java
import module vn.acme.catalog;
import module vn.acme.analysis;

class Workflow {
    Result output;
}
~~~

Nếu `Result` từng phân giải được nhưng nay có thêm kiểu trùng tên, sau nâng cấp có thể cần thêm import tường minh. Đây là **rủi ro ở compile-time**, nên build CI sẽ phát hiện nếu mọi source được biên dịch lại.

**Cách giảm rủi ro:** ưu tiên `import vn.acme.catalog.api.Result;` trong code công khai hoặc dài hạn, test module integration trước khi tăng version.

### 15.2. Thư viện đổi requires transitive hoặc qualified exports

Khi provider điều chỉnh `requires transitive`, những packages gián tiếp nằm trong phạm vi module import cũng có thể thay đổi. Một source dùng type từ dependency gián tiếp đôi khi biên dịch được nhờ transitive imports, nhưng không thể chắc chắn đó là contract ổn định mãi mãi.

**Cách giảm rủi ro:** nếu code của bạn **phụ thuộc trực tiếp** một API, hãy nêu rõ nó trong review và lựa chọn import hợp lý; trong named module, xem liệu dependency cần khai báo `requires` trực tiếp thay vì chỉ dựa vào transitive chain.

### 15.3. Code review nhìn thấy gì?

Một dòng `import module java.base;` rất ngắn nhưng **không mô tả từng kiểu** đang được file sử dụng. Điều này không xấu tự thân; nhiều ngôn ngữ có cách import nhóm. Nhưng trong Java codebase lớn, người review cần:

- Xác định kiểu tại chỗ bằng IDE/Javadoc khi có tên phổ biến.
- Nhận diện các API ngoài boundary, ví dụ code domain bắt đầu dùng XML/desktop/JDBC.
- Hiểu module import là **tiện ích cú pháp**, không phải một thay đổi kiến trúc hay tăng quyền truy cập.
- Biết khi nào phải quay về single-type import để ý định rõ hơn.

Điều quan trọng hơn số dòng import là **chi phí nhận thức khi đọc và sửa code**.

## 16. Cách tổ chức import trong repository

Java không bắt buộc một thứ tự trình bày duy nhất. Nên dùng formatter/linter thống nhất để tránh mỗi PR thay đổi lại phần đầu file.

### Một nhóm import mẫu

~~~java
package vn.acme.reports;

import java.time.LocalDate;
import java.util.Map;

import module java.sql;

import static java.util.Objects.requireNonNull;
~~~

Nếu nhóm muốn sắp theo thứ tự **standard → module imports → static**, hãy tài liệu hóa. Nếu formatter của dự án sắp thứ tự khác hoặc chưa nhận cú pháp Java 25, đừng sửa thủ công rồi để formatter đảo lại. Nâng version IDE/linter/formatter phù hợp mới là việc cần làm.

**Đề xuất quy ước nhất quán:**

1. Một file dùng cả single-type và module imports là chấp nhận được.
2. Không viết một import module thừa chỉ để trùng những kiểu đã được import qua cơ chế khác.
3. Không ép mọi file Java 25 dùng module import; chọn theo mục đích.
4. Không viết hai single-type imports có cùng simple name; dùng canonical name ở điểm cần thiết.
5. Khi nhập nhằng, ưu tiên cách khiến **ý định type** hiện rõ trong source và CI.
6. Cấu hình **import organizer** của IDE để không tự động đổi cả file về wildcard nếu style guide không cho phép.
7. Nếu có nhiều repo, đặt quy ước chung nhưng cho phép ngoại lệ theo loại artifact (script, demo, library, service).

## 17. Quy trình chuyển đổi import an toàn

Giả sử một file có 10 dòng import thuộc `java.base`, nhóm muốn thử thay bằng `import module java.base;`.

### Bước 1 — xác định động cơ

Có cải thiện rõ ràng về khả năng đọc không? Hay chỉ nhằm “dùng feature mới”? Nếu source chỉ có ba imports và API contract nhạy cảm, lợi ích có thể quá nhỏ.

### Bước 2 — xác nhận toolchain

~~~bash
java -version
javac -version
~~~

Dùng **JDK 25** cho bài; nếu build bằng Maven/Gradle, đảm bảo compiler/toolchain và release target phù hợp. Khi `--release` thấp hơn 25, syntax module import final có thể không được hỗ trợ cho target đó.

### Bước 3 — thay đổi phạm vi nhỏ

Trước:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
~~~

Sau:

~~~java
import module java.base;
~~~

Không thay đổi logic class, public API, dependency versions cùng lúc nếu có thể tránh.

### Bước 4 — kiểm tra các simple names

Tìm `List`, `Date`, `Element`, `Label` và những tên dễ trùng trong source. Nếu cần, giữ một số single-type imports trong khi dùng module import cho những kiểu khác.

### Bước 5 — biên dịch và chạy tests

Với một tệp độc lập:

~~~bash
javac --release 25 -encoding UTF-8 -d out InventorySummary.java
java --class-path out InventorySummary
~~~

Với dự án dùng build tool, chạy build/test theo wrapper và target JDK của repo:

~~~bash
./mvnw clean verify
~~~

Hoặc:

~~~bash
./gradlew clean test
~~~

**Không** chạy cả hai nếu dự án chỉ dùng một build tool. Trên Windows, dùng `mvnw.cmd` hoặc `gradlew.bat` tùy shell.

### Bước 6 — review diff và commit có chủ đích

Diff lý tưởng chỉ đổi import declarations và các explicit imports cần giải quyết tên trùng. Nếu formatter gây thay đổi hàng nghìn dòng không liên quan, điều chỉnh style plugin trước khi merge.

### Bước 7 — kiểm tra khi nâng version

Khi nâng JDK hoặc thư viện JPMS, phải **recompile toàn bộ source** để phát hiện ambiguity mới. Một JAR đã biên dịch sẽ không “tự đổi nghĩa” do việc thay import trong source; import chỉ ảnh hưởng giai đoạn biên dịch.

## 18. Maven, Gradle và yêu cầu JDK 25

### Maven

Trong `pom.xml` với phiên bản Maven Compiler Plugin hỗ trợ Java 25:

~~~xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Chạy build bằng Maven Wrapper đã cài đúng phiên bản plugin và JDK:

~~~bash
./mvnw -version
./mvnw clean verify
~~~

### Gradle

Với Gradle release hỗ trợ Java 25:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 25
    options.encoding = 'UTF-8'
}
~~~

Lệnh:

~~~bash
./gradlew --version
./gradlew clean test
~~~

**Phân biệt:** JDK 25 được dùng để **biên dịch**, còn `--release 25` xác định Java language/API target. Một đội cần hỗ trợ runtime cũ **không nên** thay toàn bộ imports thành `import module` nếu target release cũ chưa hiểu cú pháp này.

Đối với project JPMS dùng custom named modules, Maven/Gradle vẫn phải quản lý **module path, module-info.java và dependencies**. Module import không thay nhiệm vụ đó.

## 19. Bài test cho xung đột và khả năng đọc

Một kiểm thử về style cần đáng tin hơn việc chỉ đếm số dòng import.

### 19.1. Positive compile test

`Positive.java`:

~~~java
import module java.base;

class Positive {
    public static void main(String[] args) {
        Map<String, Integer> values = Map.of("a", 1);
        System.out.println(values);
    }
}
~~~

Chạy:

~~~bash
javac --release 25 Positive.java
java Positive
~~~

Kết quả phải chứa `{a=1}`.

### 19.2. Negative compile test

`Negative.java`:

~~~java
import module java.base;
import module java.desktop;

class Negative {
    List<String> items;
}
~~~

Chạy:

~~~bash
javac --release 25 Negative.java
~~~

Đây là **test cố ý biên dịch lỗi** vì `List` nhập nhằng. Nếu tự động hóa, script phải coi **exit code khác 0 là kết quả mong đợi** đối với tệp test này; không đưa nó vào source set sản phẩm.

### 19.3. Resolution test

`Resolved.java`:

~~~java
import module java.base;
import module java.desktop;
import java.util.List;

class Resolved {
    List<String> items = List.of("ok");
}
~~~

Chạy:

~~~bash
javac --release 25 Resolved.java
~~~

Nó hợp lệ nhờ single-type import `java.util.List`. Khi cần chạy thành chương trình, bổ sung main; ở đây mục tiêu là **kiểm chứng type resolution khi compile**.

### 19.4. Test khi nâng thư viện

Trong pipeline hãy kiểm tra:

- Source được biên dịch với JDK 25 (không phụ thuộc JDK cài trên máy developer).
- Module path hoặc classpath có những module cần đọc.
- Import không tạo ambiguity sau khi dependency graph thay đổi.
- Tests xác nhận logic không đổi; API behavior/public signatures không đổi vì refactor imports.
- Formatter/static analysis hỗ trợ cú pháp Java 25.
- Không có `--enable-preview` áp vào JEP 511 chỉ vì sao chép cấu hình từ thời preview.

## 20. Những quan niệm sai cần loại bỏ

### Sai lầm 1: “import module nạp toàn bộ các class vào RAM”

**Không đúng.** Import là xử lý **compile-time name lookup**, không phải tải/eager-load class ở runtime. Lượng memory/lazy class loading phụ thuộc code và JVM khác.

### Sai lầm 2: “import module thay requires”

**Không đúng.** Named module vẫn cần readability/export. Compiler báo lỗi nếu import module mà module không đọc được.

### Sai lầm 3: “Một module import là một package wildcard”

**Không đúng.** Nó mở các public top-level types từ **nhiều exported packages** của một module và các exports qua quan hệ transitive được phép.

### Sai lầm 4: “import module nhìn thấy cả internal packages”

**Không đúng.** JPMS exports/accessibility vẫn áp dụng; `public` class trong package không export không trở thành public API của module.

### Sai lầm 5: “Nếu chỉ import java.base thì không thể ambiguity”

**Không chắc.** Một module có thể export nhiều package có cùng simple names. Các imports và khai báo khác trong file cũng ảnh hưởng đến lookup.

### Sai lầm 6: “Import module java.se luôn tốt nhất”

**Không chắc.** `java.se` quá rộng với nhiều mã nghiệp vụ; trên unnamed module còn phải bảo đảm aggregator được resolve. Ưu tiên một module cụ thể hoặc type imports theo ngữ cảnh.

### Sai lầm 7: “Không bao giờ được trộn module import với import từng kiểu”

**Không đúng.** Kết hợp là một cách chính thức để giải quyết trùng tên và tăng độ tường minh. Nhóm có thể có policy stylistic riêng, nhưng đó không phải ràng buộc của ngôn ngữ.

### Sai lầm 8: “Module import tự được áp dụng cho cả package”

**Không đúng.** Import chỉ có phạm vi trong compilation unit chứa nó. Các file sibling cùng package không hưởng module import từ nhau.

### Sai lầm 9: “Mọi cú pháp module import ở Java 25 vẫn là preview”

**Không đúng.** JEP 511 đã **final** trong Java 25. Hướng dẫn bắt buộc `--enable-preview` là kiến thức lịch sử, không dùng cho bài tập Java 25 này.

### Sai lầm 10: “Nếu đổi import thì source không cần test”

**Không đúng.** Dù mục đích là đổi style, code có thể không còn compile vì type ambiguity, module readability hoặc toolchain chưa hỗ trợ; recompile và test là bước bắt buộc trước merge.

## 21. Bài tập thực hành theo mức độ

### Bài tập A — so sánh ba phong cách

Tạo chương trình xử lý `List`, `Map`, `Stream`, `LocalDate` theo ba cách: single-type imports, package wildcard imports và `import module java.base;`. So sánh số dòng import, tính dễ tra cứu nguồn gốc kiểu và mức độ thay đổi khi thêm một kiểu mới.

**Đạt khi:** cả ba phiên bản biên dịch trên JDK 25, bạn giải thích được tại sao `java.util.*` không bao gồm `java.util.stream.Stream`.

### Bài tập B — thiết kế quy ước cho repository

Nhóm có ba khu vực:

- `examples/` chứa chương trình ngắn.
- `domain-api/` chứa records và DTO công khai.
- `integration/` chứa adapter dùng SQL/XML.

Đề xuất policy cho mỗi khu vực, đồng thời nêu hai ngoại lệ hợp lý.

**Đạt khi:** policy không cấm tuyệt đối module import và không buộc toàn bộ mã sản phẩm dùng module import.

### Bài tập C — sửa ambiguity

Dùng `AmbiguousList.java`, xác nhận compiler báo lỗi. Thêm `import java.util.List;` rồi compile lại. Tìm thêm ví dụ `java.util.Date`/`java.sql.Date` hoặc `java.awt.Label`/`java.lang.classfile.Label`.

**Đạt khi:** giải thích được vì sao một import tường minh giải quyết tên trùng.

### Bài tập D — JPMS boundary

Tạo module `vn.acme.reporting` có `requires java.sql;` và source có `import module java.sql;`. Biên dịch/chạy, rồi bỏ `requires java.sql;` và quan sát compiler.

**Đạt khi:** phân biệt được **readability** với **import tên**; biết sửa module descriptor thay vì lạm dụng `--add-reads`.

### Bài tập E — code review và migration

Chọn một file có 10 single-type imports từ `java.base`. Viết PR thử chuyển sang module import với checklist: lợi ích đọc code, nguy cơ ambiguity, JDK target, formatter, test và release compatibility.

**Đạt khi:** PR có phạm vi nhỏ, test chạy và lý do thay đổi không chỉ là “cú pháp mới”.

### Bài tập F — compact source file

Tạo `QuickNotes.java` với `void main()`, `List` và `Collectors` mà không khai báo imports. Chạy trên Java 25, sau đó chuyển thành explicit class và xác minh imports cần thiết.

**Đạt khi:** hiểu rằng compact source file tự có module import ngầm định của `java.base` trong Java 25, không phải mọi ordinary class đều có đặc quyền đó.

### Checklist hoàn thành

- [ ] Hiểu cú pháp `import module M;` và phạm vi compilation unit.
- [ ] Biết import theo module chỉ đưa public top-level types thuộc exported packages được đọc.
- [ ] Phân biệt module import, package wildcard và single-type import.
- [ ] Không nhầm `import module` với `requires` / `exports` trong JPMS.
- [ ] Dự đoán và sửa được ambiguity `List`/`Date`/`Element`/`Label`.
- [ ] Biết khi nào dùng `java.base`, `java.sql`, `java.xml` và khi nào tránh `java.se` quá rộng.
- [ ] Có quy ước cho example/compact source khác với public API và large codebase.
- [ ] Không đưa `--enable-preview` vào bài JEP 511 final của Java 25.
- [ ] Chạy compiler và tests với JDK/toolchain tương thích khi đổi import style.
- [ ] Nêu được lợi ích và rủi ro bảo trì của từng quyết định.

## 22. Nguồn tham khảo chính thức

1. [JEP 511 — Module Import Declarations](https://openjdk.org/jeps/511): đặc tả và động cơ đưa module import thành tính năng chính thức ở Java 25.
2. [Oracle Java 25 — Module Import Declarations](https://docs.oracle.com/en/java/javase/25/language/module-import-declarations.html): ví dụ `java.base`, `java.se`, type ambiguity và compact source files.
3. [JLS Java SE 25 `7.5.5 — Single-Module-Import Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.5.5): phạm vi, exports, transitive readability, named/unnamed modules và ambiguity.
4. [JLS Java SE 25 `7.3 — Compilation Units](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.3): ordinary, compact và modular compilation units.
5. [JLS Java SE 25 `7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7): `requires`, `requires transitive`, `exports`, `opens`.
6. [Oracle Java 25 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): JEP 511 đã là tính năng permanent trong Java 25.
7. [JDK 25 `javac` Tool Guide](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): biên dịch với `--release 25` và module path.

**Kết quả mong đợi:** người học không chỉ biết viết `import module java.base;`, mà còn biết **khi nào nên và không nên dùng** để tối ưu tính rõ ràng, quy ước nhóm và độ bền của code qua các lần nâng JDK/library. Quyết định import tốt là quyết định thể hiện được ý định phụ thuộc, dễ review, không tạo ambiguity và được chứng minh bằng compile/test trên Java 25.
