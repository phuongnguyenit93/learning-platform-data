# Ảnh hưởng của requires transitive đến các kiểu có thể được nhập

## Mục tiêu bài học

Trong Java 25, **Module Import Declarations** đã trở thành tính năng chính thức theo **JEP 511**. Cú pháp `import module M;` cho phép dùng tên ngắn của nhiều kiểu công khai thuộc các package mà module `M` export, thay vì khai báo nhiều `import some.package.Type;`. Điểm quan trọng hơn là **phạm vi các kiểu được nhập còn phụ thuộc vào `requires transitive` trong module descriptor**.

Bài **Ảnh hưởng của requires transitive đến các kiểu có thể được nhập** thuộc chương **Module import** của module học **JAVA_VERSION_JAVA25**. Mục tiêu là hiểu đúng sự tương tác giữa *module graph* của JPMS, các package được export và cách trình biên dịch đưa tên kiểu vào phạm vi của một tệp nguồn.

Sau bài học, người học có thể:

1. Phân biệt `requires`, `requires transitive`, `exports`, `exports ... to ...` và `import module`.
2. Tính được tập kiểu có thể được import qua một module, kể cả các quan hệ `requires transitive` nhiều cấp.
3. Giải thích vì sao một module được phụ thuộc bằng `requires` thông thường **không** tự đóng góp các kiểu cho `import module` của module cha.
4. Xây ví dụ JPMS gồm API, model, implementation và application, sau đó thay `requires transitive` để quan sát khác biệt.
5. Xử lý lỗi readability, qualified exports, trùng tên kiểu và sự khác nhau giữa import tên với quyền truy cập.
6. Áp dụng quy tắc này khi thiết kế API công khai, đánh giá thay đổi module descriptor và nâng cấp lên JDK 25.

> **Mốc phiên bản:** JEP 511 được chuẩn hóa trong **Java SE 25**; không cần `--enable-preview` khi biên dịch bằng JDK 25. Không dùng các mẫu cú pháp từ những bản preview cũ làm cơ sở cho code production. Tài liệu này giả định JDK 25 và dự án dùng Java Platform Module System (**JPMS**); các thư viện đặt trên classpath/unnamed module được giải thích riêng ở cuối bài.

## 1. Bốn khái niệm thường bị nhầm

Trong JPMS, cần tách hai câu hỏi:

- **Một module có quyền thấy API nào?** Trả lời bằng **readability** (`requires`) kết hợp **exports** của module đích.
- **Trong một tệp nguồn, có thể viết tên ngắn của kiểu nào mà không ghi tên package?** Trả lời bằng **import declarations**, trong đó có `import module M;`.

| Cú pháp | Được đặt ở đâu? | Tác dụng |
|---|---|---|
| `requires M;` | `module-info.java` | Module hiện tại đọc module `M`; không tự truyền quan hệ đọc `M` cho consumer |
| `requires transitive M;` | `module-info.java` | Đọc `M` và truyền quan hệ readability tới module đọc module hiện tại |
| `exports p;` | `module-info.java` | Cho phép module khác truy cập các kiểu `public` trong package `p`, nếu đọc được module |
| `exports p to X;` | `module-info.java` | Chỉ export package `p` cho module đích được nêu, ví dụ `X` |
| `import module M;` | Tệp nguồn `*.java` | Import *on demand* các kiểu `public` thuộc package mà `M` và các module đi qua `requires transitive` export phù hợp |

`import module M;` **không** giống `requires M;`. Lệnh import **không thay đổi module graph**, không tạo quan hệ readability mới, không tự export package và không mở quyền truy cập reflection. Nó làm cho tên kiểu có thể được sử dụng ở dạng đơn giản trong **compilation unit** chứa chính lệnh import đó.

## 2. Quy tắc chính thức của Java 25

Theo **JLS Java SE 25 §7.5.5 — Single-Module-Import Declarations**, cú pháp là:

~~~java
import module M;
~~~

Đối với tệp nguồn thuộc module hiện tại `C`, khai báo này import theo nhu cầu (*on demand*) các **public top-level classes và interfaces** thuộc:

1. Những package do `M` **export tới `C`**.
2. Những package được export tới `C` bởi các module mà `C` đọc được **do đọc `M`**, tức là qua chuỗi phụ thuộc `requires transitive` thích hợp.

Các kiểu enum, record hay annotation interface công khai ở cấp top-level cũng nằm trong những nhóm class/interface tương ứng của Java. Import này không biến các member nested types hoặc các phương thức static thành những tên được import trực tiếp; khi cần, hãy dùng cú pháp Java thông thường.

**Điều kiện trước tiên:** `C` phải **đọc được `M`**. Nếu module chứa tệp nguồn không đọc module được nêu trong `import module M;`, trình biên dịch báo lỗi. Viết lệnh import không phải cách né việc khai báo `requires`.

Có thể mô tả quy tắc dưới dạng thuật toán:

1. Xác nhận module đích `M` tồn tại, được resolve và module hiện tại đọc được `M`.
2. Đưa vào tập đang xét các package mà `M` export cho module hiện tại.
3. Duyệt các module được đọc gián tiếp do các cạnh **`requires transitive`** đi từ `M` và các module tiếp theo trên đường đi.
4. Lấy các package được export cho module hiện tại từ những module ấy.
5. Chỉ dùng **kiểu top-level `public`** trong các package đủ điều kiện, rồi áp dụng các quy tắc scope, shadowing và ambiguity của Java.

**Công thức tư duy:** `import module M` là tập *exported public types* theo đường `M → requires transitive → ...`, **không phải** “mọi class nằm ở runtime classpath”, “mọi module `M` sử dụng” hay “mọi dependency Maven/Gradle của `M`”.

## 3. Đọc sơ đồ `requires transitive`

Giả sử có module `M0` chạy ứng dụng, `M1` công bố API, `M4` cung cấp model, và `M5` là dependency implementation của API.

~~~mermaid
flowchart LR
    M0["M0 — consumer"] -->|"requires M1"| M1["M1 — API"]
    M1 -->|"requires transitive M4"| M4["M4 — model"]
    M1 -->|"requires M5"| M5["M5 — implementation"]
~~~

Các module descriptor (lược bỏ tên package chi tiết):

~~~java
// M0/module-info.java
module M0 {
    requires M1;
}
~~~

~~~java
// M1/module-info.java
module M1 {
    exports p1;
    exports p2 to M0;
    exports p3 to M3;
    requires transitive M4;
    requires M5;
}
~~~

~~~java
// M4/module-info.java
module M4 {
    exports p10;
}
~~~

~~~java
// M5/module-info.java
module M5 {
    exports p11;
}
~~~

Với một tệp thuộc `M0`:

~~~java
package app;
import module M1;

class Demo {
    // Các tên kiểu đơn giản được xét ở đây.
}
~~~

Các package được đóng góp bởi **một** `import module M1;`:

| Package | Có được import on demand? | Lý do |
|---|---|---|
| `p1` của M1 | **Có** | M1 export công khai |
| `p2` của M1 | **Có** | M1 export riêng cho M0 |
| `p3` của M1 | **Không** | M1 chỉ export cho M3, không phải M0 |
| `p10` của M4 | **Có** | M1 có `requires transitive M4` và M4 export `p10` |
| `p11` của M5 | **Không** | M1 chỉ có `requires M5` thông thường |

Đây là đúng mẫu trong JLS §7.5.5: *M0 không tự nhập p11 chỉ vì M1 dùng M5 ở bên trong*. Tên kiểu `public` ở `p11` cũng không tự động xuất hiện qua `import module M1`.

### 3.1. Hệ quả đối với readability

Với `M0 requires M1` và `M1 requires transitive M4`:

- M0 đọc M1.
- M1 đọc M4.
- M0 **cũng đọc M4** do quan hệ transitive được công bố bởi M1.
- M0 có thể dùng kiểu `public` của package mà M4 export tới M0; `import module M1` giúp không phải ghi nhiều lệnh import kiểu tường minh.

Ngược lại, `M1 requires M5` khiến **M1 đọc M5**, nhưng **không** tự khiến M0 đọc M5. Nếu M0 cần dùng kiểu ở M5, phải thiết kế lại phụ thuộc và import phù hợp; không thể yêu cầu `import module M1` tự vượt qua ranh giới đó.

### 3.2. Đường `requires transitive` có thể nhiều cấp

Giả sử thêm:

~~~java
module M4 {
    requires transitive M6;
    exports p10;
}
~~~

~~~java
module M6 {
    exports p20;
}
~~~

Khi đó đọc M1 có thể làm M0 đọc M4 rồi M6, và `import module M1;` cũng đưa các kiểu `public` ở `p20` vào tập ứng viên nhập, miễn package được export phù hợp.

Đừng hiểu quy tắc là “chỉ đi thêm đúng một cạnh”. Nó dựa vào **module readability do các phụ thuộc transitive tạo ra** và có thể lan qua nhiều cấp. Nếu một cạnh trong đường đi đổi thành `requires` thông thường, đường mở rộng transitive bị dừng ở đó.

## 4. Dự án thực hành bốn module

Ta sẽ xây một chương trình Java 25 tối giản có bốn module:

| Module | Vai trò | Quan hệ |
|---|---|---|
| `demo.model` | Cung cấp kiểu dữ liệu công khai `Receipt` | Export package `demo.model` |
| `demo.impl` | Hỗ trợ xử lý nội bộ `Formatter` | Export package `demo.impl` để API sử dụng |
| `demo.api` | Công bố `ReceiptService` trả về `Receipt` | `requires transitive demo.model`; `requires demo.impl` |
| `demo.app` | Consumer chạy chương trình | **Chỉ** `requires demo.api` |

Các tệp nguồn:

~~~text
src/
├── demo.model/
│   ├── module-info.java
│   └── demo/model/Receipt.java
├── demo.impl/
│   ├── module-info.java
│   └── demo/impl/Formatter.java
├── demo.api/
│   ├── module-info.java
│   └── demo/api/ReceiptService.java
└── demo.app/
    ├── module-info.java
    └── demo/app/Main.java
~~~

### 4.1. Module model

Tệp `src/demo.model/module-info.java`:

~~~java
module demo.model {
    exports demo.model;
}
~~~

Tệp `src/demo.model/demo/model/Receipt.java`:

~~~java
package demo.model;

public record Receipt(String code) {}
~~~

`Receipt` là record top-level `public` trong package được export công khai; vì vậy nó có thể được sử dụng bởi module khác nếu module đó đọc `demo.model`.

### 4.2. Module implementation

Tệp `src/demo.impl/module-info.java`:

~~~java
module demo.impl {
    exports demo.impl;
}
~~~

Tệp `src/demo.impl/demo/impl/Formatter.java`:

~~~java
package demo.impl;

public final class Formatter {
    private Formatter() {}

    public static String normalize(String input) {
        return input.trim().toUpperCase();
    }
}
~~~

Ở đây `demo.impl` export package để `demo.api` có thể sử dụng `Formatter`. Tuy nhiên, **export công khai không đủ** để ứng dụng `demo.app` truy cập nếu `demo.app` không đọc module này. Trên thực tế, thư viện có thể tổ chức implementation bằng cơ chế khác để không cần export; ví dụ này cố ý đơn giản để làm rõ sự khác nhau giữa **exports** và **readability**.

### 4.3. Module API — phần quyết định

Tệp `src/demo.api/module-info.java`:

~~~java
module demo.api {
    requires transitive demo.model;
    requires demo.impl;

    exports demo.api;
}
~~~

Tệp `src/demo.api/demo/api/ReceiptService.java`:

~~~java
package demo.api;

import demo.model.Receipt;
import demo.impl.Formatter;

public final class ReceiptService {
    private ReceiptService() {}

    public static Receipt issue(String rawCode) {
        return new Receipt(Formatter.normalize(rawCode));
    }
}
~~~

Hợp đồng public `ReceiptService.issue(...)` trả về `Receipt`, tức là **lộ một kiểu từ `demo.model` trong API**. `requires transitive demo.model` cho consumer khả năng đọc model thông qua API module. Ngược lại, `Formatter` chỉ phục vụ implementation, nên `requires demo.impl` thông thường là lựa chọn đúng.

### 4.4. Module app — chỉ cần yêu cầu API

Tệp `src/demo.app/module-info.java`:

~~~java
module demo.app {
    requires demo.api;
}
~~~

Tệp `src/demo.app/demo/app/Main.java`:

~~~java
package demo.app;

import module demo.api;

public class Main {
    public static void main(String[] args) {
        Receipt receipt = ReceiptService.issue(" r-001 ");

        System.out.println(receipt.code()); // R-001
    }
}
~~~

Trong `Main.java` **không** có:

~~~java
import demo.api.ReceiptService;
import demo.model.Receipt;
~~~

Hai kiểu `ReceiptService` và `Receipt` đều có thể dùng bằng tên ngắn từ `import module demo.api;`, nhưng vì **hai lý do khác nhau**:

- `ReceiptService` thuộc package `demo.api` mà module được import trực tiếp export.
- `Receipt` thuộc package `demo.model` được đọc nhờ `demo.api requires transitive demo.model`, rồi export công khai từ model.

Còn `Formatter` không được nhập bởi `import module demo.api;`, vì đường tới `demo.impl` chỉ là `requires` thường. `demo.app` cũng không tự đọc `demo.impl`.

### 4.5. Biên dịch và chạy bằng JDK 25

Tại thư mục chứa `src/`, `java` và `javac` phải cùng thuộc JDK 25:

~~~bash
java -version
javac -version
~~~

Dùng JPMS module source path để biên dịch toàn bộ module (tạo sẵn thư mục đầu ra nếu môi trường yêu cầu):

~~~bash
javac --module-source-path src \
      -d out \
      -m demo.model,demo.impl,demo.api,demo.app
~~~

Sau đó chạy:

~~~bash
java --module-path out -m demo.app/demo.app.Main
~~~

Kết quả mong đợi:

~~~text
R-001
~~~

Các lệnh trên là **hướng dẫn thực hành để chạy trong dự án mẫu**, không phải kết quả đã thực thi trong tài liệu. Khi dùng PowerShell, viết `javac --module-source-path src -d out -m demo.model,demo.impl,demo.api,demo.app` trên một dòng; ký tự nối dòng kiểu Bash không tương thích với PowerShell.

## 5. Thí nghiệm A: bỏ `transitive` khỏi API module

Đổi duy nhất descriptor của `demo.api`:

~~~java
module demo.api {
    requires demo.model; // ĐÃ BỎ transitive
    requires demo.impl;

    exports demo.api;
}
~~~

Giữ nguyên `demo.app`:

~~~java
module demo.app {
    requires demo.api;
}
~~~

Và giữ nguyên `Main.java` với `import module demo.api;`.

**Kết quả kỳ vọng:** `Receipt` không còn tự thuộc tập các kiểu được import nhờ `demo.api`; đồng thời `demo.app` không còn đọc `demo.model` qua API module. Code sử dụng `Receipt` trong consumer có thể báo lỗi biên dịch do không đọc được kiểu ở module model hoặc không tìm được tên kiểu tương ứng.

Bài học ở đây không chỉ là thay đổi một lệnh import. Đối với API có phương thức công khai trả về `Receipt`, bỏ `requires transitive demo.model` có thể làm **hỏng khả năng biên dịch của consumer** dù source code ở `ReceiptService` không đổi. Module dependency là một phần của hợp đồng thư viện.

**Một cách khôi phục trực tiếp:** cho `demo.app` khai báo:

~~~java
module demo.app {
    requires demo.api;
    requires demo.model;
}
~~~

Rồi thêm import riêng của model:

~~~java
import module demo.api;
import module demo.model;
~~~

Hoặc:

~~~java
import module demo.api;
import demo.model.Receipt;
~~~

Khi đó consumer tự khai báo dependency tới `demo.model`, không còn phụ thuộc vào tính transitive của `demo.api`. Đây là lựa chọn hợp lệ nếu ứng dụng **chủ đích** dùng model trực tiếp; tuy nhiên nó làm coupling của consumer rõ ràng hơn và cho thấy tại sao thiết kế public API ban đầu cần cân nhắc `requires transitive`.

**Không đúng:** chỉ thêm `import module demo.model;` mà quên readability ở `module-info.java` khi model không được đọc. Theo JLS, import module không cấp quyền đọc module.

## 6. Thí nghiệm B: import implementation qua API có được không?

Giữ bản API đã có `requires transitive demo.model` và `requires demo.impl`. Trong `Main.java`, thử:

~~~java
package demo.app;
import module demo.api;

public class Main {
    public static void main(String[] args) {
        Formatter.normalize(" r-001 "); // KHÔNG BIÊN DỊCH
    }
}
~~~

Mặc dù `demo.api` gọi `Formatter` thành công, `Formatter` không trở thành một kiểu nhập qua `import module demo.api;`, vì `demo.api` chỉ `requires demo.impl` thông thường.

Muốn app trực tiếp dùng Formatter, app phải đọc `demo.impl` và import riêng:

~~~java
// module demo.app
module demo.app {
    requires demo.api;
    requires demo.impl;
}
~~~

~~~java
package demo.app;
import module demo.api;
import demo.impl.Formatter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Formatter.normalize(" r-001 "));
    }
}
~~~

Tuy có thể biên dịch, đây thường **không phải kiến trúc mong muốn** khi `demo.impl` chỉ là chi tiết nội bộ. Thay vì cho mọi consumer dùng implementation, hãy để API public cung cấp thao tác cần thiết, và giới hạn package export theo chính sách thiết kế module.

## 7. Qualified exports: được đọc chưa chắc được nhập

Đường transitive chỉ xác định khả năng đọc module. **Export visibility** vẫn là cổng thứ hai. Cần kiểm tra package có được export **tới module consumer hiện tại** hay không.

Ví dụ (một biến thể mô tả, không phải toàn bộ dự án ở mục 4):

~~~java
module library.api {
    requires transitive library.model;

    exports library.api;
    exports library.friend to consumer.app;
    exports library.operator to admin.tool;
}
~~~

~~~java
module library.model {
    exports library.model;
    exports library.model.internal to admin.tool;
}
~~~

Khi `consumer.app` đọc `library.api` và viết `import module library.api;`:

| Package | Được import vào consumer.app? | Giải thích |
|---|---|---|
| `library.api` | Có | Export không điều kiện |
| `library.friend` | Có | Qualified export tới consumer.app |
| `library.operator` | Không | Chỉ export cho admin.tool |
| `library.model` | Có | Đọc model nhờ transitive, model export công khai |
| `library.model.internal` | Không | Chỉ export cho admin.tool |

Lệnh `import module` không làm package `library.operator` hoặc `library.model.internal` thành public đối với consumer.app. Cũng không thể dùng cách ghi `import library.model.internal.*;` để vượt qua export restriction nếu module hiện tại không được phép truy cập.

### 7.1. `exports` khác `opens`

`exports` kiểm soát khả năng truy cập thông thường khi biên dịch và liên kết kiểu public giữa các module. `opens` phục vụ reflective access theo quy tắc JPMS; nó **không phải** một cách thay thế `exports` để `import module` đưa các kiểu vào tên ngắn.

Không nên “sửa” lỗi import bằng cách mở toàn bộ module, chuyển thư viện sang unnamed module hoặc dùng cờ `--add-opens` bừa bãi. Hãy sửa đúng **readability** và **exports** hoặc giữ API nội bộ theo thiết kế.

## 8. So sánh `requires transitive` với `import module`

Hai công cụ bổ trợ nhau nhưng tác động ở các mức khác nhau.

| Khía cạnh | `requires transitive` | `import module` |
|---|---|---|
| Vị trí | `module-info.java` | Một compilation unit `*.java` |
| Tác động chính | Module readability graph | Tên kiểu có thể dùng mà không ghi package |
| Phạm vi | Module đang khai báo và các module đọc nó | Chỉ tệp nguồn chứa import |
| Có làm thay đổi runtime module graph? | Có, là module dependency | Không |
| Có giúp downstream đọc dependency? | Có | Không |
| Có tự công khai package không? | Không; vẫn cần `exports` | Không |
| Có ảnh hưởng tính tương thích của public API? | Có thể rất lớn | Chủ yếu là ergonomics của tệp nguồn |
| Có phải feature preview ở Java 25? | Không, JPMS ổn định từ trước | Không; JEP 511 chính thức ở Java 25 |

Ví dụ cùng một app có thể không dùng `import module demo.api;` mà vẫn khai báo:

~~~java
import demo.api.ReceiptService;
import demo.model.Receipt;
~~~

Nó vẫn cần **`module demo.app { requires demo.api; }`** và `demo.api requires transitive demo.model` để đọc được model trong trường hợp không khai báo model trực tiếp. `import module` chỉ giảm số import; `requires transitive` mới là điều khiến đường đi API tới model trở thành khả năng đọc của consumer.

## 9. Ví dụ chuẩn trong JDK: `import module java.sql;`

Trong Java 25, JDK module `java.sql` công bố API JDBC và có phụ thuộc `requires transitive` tới các module khác, gồm `java.logging` và `java.xml`. Vì vậy `import module java.sql;` có thể đưa nhiều kiểu public từ các package được export bởi các module đó vào phạm vi tên ngắn. Ví dụ chương trình đơn giản:

~~~java
// JdbcImports.java
import module java.sql;

public class JdbcImports {
    public static void main(String[] args) {
        // DriverManager thuộc java.sql
        DriverManager.getDrivers().asIterator()
                .forEachRemaining(d -> System.out.println(d.getClass()));

        // Logger thuộc java.util.logging, được đọc qua java.sql
        Logger logger = Logger.getLogger("demo");
        logger.info("JDBC module import hoạt động");

        // XPath thuộc javax.xml.xpath, từ java.xml
        XPath xpath = XPathFactory.newInstance().newXPath();
        System.out.println(xpath);
    }
}
~~~

Cần chú ý: kiểu `XPath` và `XPathFactory` của `java.xml` chỉ xuất hiện nhờ import này vì `java.sql` transitive-requires `java.xml`, và package của chúng được export phù hợp. Các phương thức `DriverManager.getDrivers()` cũng dùng thêm API thông thường của Java. Chương trình không cần kết nối database; danh sách JDBC drivers có thể rỗng nếu không có driver nào trên module path/classpath.

Chạy dạng source-file mode bằng JDK 25:

~~~bash
java JdbcImports.java
~~~

Nếu muốn kiểm chứng chính xác dependency của JDK đang chạy:

~~~bash
java --describe-module java.sql
java --describe-module java.xml
java --describe-module java.logging
~~~

Đây là lệnh **kiểm tra descriptor của module chuẩn**; không đoán module graph từ tên jar hoặc sự hiện diện của package trên ổ đĩa.

### 9.1. `java.se` và `java.base`

Java 25 cũng cho phép `import module java.se;`. Module `java.se` chủ yếu là module tổng hợp, không tự export package, nhưng **requires transitive** nhiều module chuẩn; do đó có thể nhập các kiểu public từ những module được đọc thông qua nó.

Khi dùng source-file mode trong unnamed module, `java.se` không nhất thiết là root mặc định để resolve. Tài liệu Oracle minh họa thêm:

~~~bash
java --add-modules java.se SomeProgram.java
~~~

Không suy diễn rằng `import module java.se;` tự đưa mọi module chưa resolve vào graph. Luôn xem **module resolution/readability** là điều kiện trước của import.

Trong **compact source files** được chính thức hóa bởi **JEP 512** ở Java 25, có sẵn hiệu lực như `import module java.base;`. Điều đó không biến một tệp ordinary source thành compact source hoặc khiến mọi module được import tự động; `import module java.base;` tường minh vẫn hữu ích khi viết ordinary source file.

## 10. Trùng tên kiểu và thứ tự ưu tiên import

Module import là dạng **on-demand**. Nếu hai module export kiểu cùng simple name, trình biên dịch chỉ có thể xác định tên đúng khi ngữ cảnh và các quy tắc về import/shadowing giải quyết được.

Ví dụ:

~~~java
import module java.base;
import module java.desktop;

class Demo {
    List<String> names; // Có thể ambiguous:
                        // java.util.List và java.awt.List
}
~~~

Trong Java 25, `java.base` còn có `java.lang.classfile.Label`, trong khi `java.desktop` có `java.awt.Label`. Import cả hai module có thể làm tên `Label` trở nên ambiguous khi dùng dạng đơn giản.

Cách sửa tốt là **single-type import tường minh**:

~~~java
import module java.base;
import module java.desktop;
import java.util.List;

class Demo {
    List<String> names = List.of("A", "B");
}
~~~

Hoặc dùng tên đầy đủ:

~~~java
class Demo {
    java.util.List<String> names = java.util.List.of("A", "B");
    java.awt.List awtList = new java.awt.List();
}
~~~

Import một kiểu cụ thể có thể giải quyết xung đột tên với nhiều module-on-demand imports. Import không làm các kiểu cùng tên thành một kiểu; luôn phân biệt package/type thực tế.

**Nguyên tắc bảo trì:** module import giúp mã ngắn hơn khi muốn dùng nhiều kiểu từ một API module, nhưng ở tệp công khai hoặc nơi có nhiều module exporting names giống nhau, **explicit type imports** thường rõ ràng và an toàn hơn trước những thay đổi của thư viện.

## 11. Ranh giới của JPMS và build tool

### 11.1. Không phải dependency Maven/Gradle nào cũng là `requires transitive`

Các công cụ build giải quyết dependency artifact để tạo compile/runtime classpath hoặc module path. Chúng **không tự quyết định** mọi quan hệ JPMS:

- `implementation` trong Gradle không mặc nhiên tương đương `requires` trong `module-info.java`.
- Một Maven transitive dependency không có nghĩa module Java cũng `requires transitive` module đó.
- Module graph dựa vào những descriptor **đã resolve thực sự**, trong đó có các module automatic/unnamed theo quy tắc riêng.
- Để `import module M;` hoạt động trong **named module**, module hiện tại phải đọc được `M`.

Khi một project chuyển dần từ classpath sang module path, cần xác minh module name, `module-info.java`, `requires`, `exports`, và việc library có được resolve như named/automatic module hay không. Đừng dùng một kết quả “IDE tự hoàn thành import” để kết luận JPMS access đang đúng.

### 11.2. Java 25 vẫn hỗ trợ ordinary source files

JEP 511 không bắt buộc thay toàn bộ `import package.Type;` thành `import module M;`. Có thể dùng xen kẽ:

~~~java
package demo.app;

import module demo.api;
import java.time.Instant;
import java.util.List;

class Example {
    List<Instant> timestamps;
}
~~~

Không phải mọi module đều phù hợp để import rộng. Với API lớn, lệnh `import module` có thể làm các kiểu trùng tên tăng lên khi dependency transitive hoặc exports thay đổi trong phiên bản tương lai. Chỉ áp dụng nơi tính rõ ràng và lợi ích ngắn gọn cân bằng với rủi ro.

## 12. Tương thích khi thay đổi `requires transitive`

Giả sử `library.api` đang có:

~~~java
module library.api {
    requires transitive library.model;
    exports library.api;
}
~~~

Nếu chuyển thành `requires library.model;`, **module consumer trước đây có thể mất readability** tới model, và `import module library.api;` cũng không còn nhập các kiểu model. Hệ quả có thể xuất hiện khi compile lại, và trong một số trường hợp cũng ảnh hưởng binary đã build dựa vào readability trước đó.

JLS Java SE 25 §13.3 ghi nhận việc **xóa `requires` hoặc xóa modifier `transitive`** có thể phá tương thích binary của chương trình phụ thuộc vào quan hệ module readability ấy. Ngược lại, thêm `requires` hoặc `requires transitive` thường không trực tiếp phá binary theo cách đó, nhưng vẫn có thể làm lộ xung đột module/package trong quá trình resolution.

Một checklist review thay đổi `module-info.java` nên hỏi:

1. API public có trả về hoặc nhận kiểu từ module dependency không?
2. Consumer hiện có đang đọc kiểu đó thông qua `requires transitive` không?
3. Tệp nguồn consumer có dùng `import module api.module;` không?
4. Export của model là public hay qualified? Qualified export có bao gồm đúng các consumer cần thiết không?
5. Sau khi sửa descriptor, chạy lại các module consumer **từ source** và kiểm chứng runtime module graph chưa?
6. Có xung đột simple names mới xuất hiện do mở rộng tập imported types không?

**Không nên chuyển mọi `requires` thành `requires transitive`** chỉ để giảm lỗi import. Modifier transitive phải diễn tả một **phụ thuộc API công khai** có chủ đích. Nếu dependency chỉ phục vụ implementation, `requires` thường là lựa chọn đúng, giúp hạn chế coupling và giữ API surface rõ ràng.

## 13. Ma trận kiểm thử thực hành

Với dự án ở mục 4, thực hiện các trường hợp sau trên JDK 25:

| Mã | Thao tác | Kỳ vọng |
|---|---|---|
| T1 | API `requires transitive demo.model`, app `requires demo.api` | `import module demo.api` nhập được ReceiptService và Receipt |
| T2 | API đổi `requires transitive demo.model` thành `requires demo.model` | Consumer không còn tự đọc model; code sử dụng Receipt bị lỗi nếu không thêm dependency trực tiếp |
| T3 | App thêm `requires demo.model` và explicit import Receipt | Compile thành công nếu model export đúng |
| T4 | App chỉ thêm `import module demo.model` nhưng không đọc model | Compile-time error do module chưa được đọc |
| T5 | App cố dùng Formatter chỉ với `import module demo.api` | Không có simple name Formatter từ API import |
| T6 | App `requires demo.impl` và explicit import Formatter | Kiểu accessible nếu package được export công khai |
| T7 | API dùng `exports p to admin.tool`, app không phải admin.tool | App không được import kiểu public trong package p |
| T8 | Thêm `requires transitive` nhiều tầng | Những public types từ export hợp lệ ở cuối chuỗi xuất hiện |
| T9 | Import java.base và java.desktop cùng dùng `List` | Ambiguous; sửa bằng explicit single-type import |
| T10 | Thử `import module M` với module không resolve/không read | Compiler báo lỗi; phải sửa graph thay vì import lặp |
| T11 | Import một module trong hai source files khác nhau | Import chỉ có hiệu lực ở compilation unit chứa nó |
| T12 | Chạy app bằng `java --module-path out -m demo.app/demo.app.Main` | Kiểm chứng runtime module resolution và kết quả R-001 |

Ghi lại **lệnh chạy, phiên bản `javac`, thông báo compiler và descriptor trước/sau**. Không chỉ chụp màn hình IDE: lỗi khả năng đọc module có thể được IDE tự động gợi ý cách sửa khác với thiết kế JPMS mong muốn.

## 14. Những nhầm lẫn phổ biến

| Nhầm lẫn | Thực tế Java 25 |
|---|---|
| “`import module M` tự `requires M`” | Không; module hiện tại phải đọc M trước |
| “`requires transitive` là import” | Không; nó mở rộng readability cho downstream |
| “Mọi dependency mà M `requires` đều được import qua M” | Không; với module import chỉ mở rộng theo đường `requires transitive` |
| “`public` là đủ, package export hay không không quan trọng” | Sai; cần public + export phù hợp + readability |
| “`exports p to X` nghĩa là ai cũng import p” | Sai; chỉ những module được nêu có quyền |
| “`opens` tương đương `exports` cho compiler” | Sai; opens phục vụ reflective access |
| “Maven transitive dependency = JPMS requires transitive” | Sai; đây là hai hệ quan hệ khác nhau |
| “Import rộng không có rủi ro” | Sai; simple-name ambiguity có thể phát sinh |
| “Module imports vẫn là preview trong Java 25” | Sai; JEP 511 đã chính thức, không cần `--enable-preview` |
| “Compact source files cần `import module java.base` bằng tay” | Không; Java 25 đã implicit import `java.base` cho compact files |

## 15. Bài tập tự luyện

**Bài A — Đọc module graph.** Cho `A requires B`, `B requires transitive C`, `C requires transitive D`, `B requires E`. A có `import module B`. Hãy liệt kê package nào được nhập nếu B, C, D, E mỗi module export một package public và các export đều không qualified. Giải thích vì sao package của E không thuộc kết quả.

**Bài B — Thiết kế API.** Bạn viết module `orders.api` có public method trả về `orders.model.OrderSummary`, đồng thời dùng `orders.jdbc` trong implementation. Hãy chọn `requires` hay `requires transitive` cho từng dependency và giải thích ảnh hưởng tới consumer có `import module orders.api`.

**Bài C — Qualified exports.** Thêm một package `orders.internal` chỉ export cho `orders.admin`. Xác định vì sao `orders.consumer` không thể nhập các kiểu của package này kể cả khi có đường đọc module transitive. Đưa ra phương án API public phù hợp thay vì dùng `--add-exports` để né kiến trúc.

**Bài D — Thay đổi không tương thích.** Một thư viện thay `requires transitive model` thành `requires model` khi nâng phiên bản. Hãy thiết kế CI test biên dịch module consumer để phát hiện thay đổi đó và nêu điều kiện trước khi chấp nhận migration.

## 16. Checklist áp dụng trong codebase hiện đại

Trước khi dùng module import trong Java 25:

- **JDK:** Xác nhận `javac -version` là 25+; tính năng JEP 511 đã final, không sử dụng preview flags.
- **Module graph:** Đọc `module-info.java`, xác minh module đang được import có thể được đọc.
- **Transitivity:** Với kiểu đi qua module khác, kiểm tra có đường `requires transitive` đúng hay không.
- **Exports:** Chỉ kỳ vọng các kiểu public thuộc package export công khai hoặc qualified export tới consumer.
- **API design:** Chỉ dùng `requires transitive` khi downstream cần đọc dependency do public API bộc lộ.
- **Readability vs import:** Không thay `requires` bằng một câu `import module` trong tệp.
- **Ambiguity:** Khi type name trùng, dùng explicit single-type import hoặc tên đầy đủ.
- **Compatibility:** Test cả nguồn consumer và runtime khi thay `transitive` trong module descriptor.
- **Toolchain:** Kiểm tra Maven/Gradle đang đưa modules lên module path phù hợp, không đánh đồng transitive artifact dependencies với JPMS dependencies.
- **Bảo trì:** Ưu tiên rõ ràng về module boundary và public API hơn việc giảm vài dòng import.

## Tài liệu tham khảo chính thức

- [JEP 511 — Module Import Declarations](https://openjdk.org/jeps/511): tính năng chính thức trong Java 25 và động cơ thiết kế.
- [Oracle Java SE 25 — Module Import Declarations](https://docs.oracle.com/en/java/javase/25/language/module-import-declarations.html): cách dùng, ví dụ `java.sql`, ambiguity và `java.se`.
- [JLS Java SE 25 §7.5.5 — Single-Module-Import Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.5.5): phạm vi nhập theo exports và `requires transitive`.
- [JLS Java SE 25 §7.7.1 — Dependences](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7.1): `requires`, `requires transitive` và module readability.
- [JLS Java SE 25 §13.3 — Evolution of Modules](https://docs.oracle.com/javase/specs/jls/se25/html/jls-13.html#jls-13.3): tác động binary compatibility khi đổi module descriptor.
- [Java SE 25 — java.lang.module](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/package-summary.html): resolution và cách tính readability graph.
