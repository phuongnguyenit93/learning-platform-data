# Quan hệ giữa module import, tính đọc được và đồ thị phụ thuộc module

## 1. Vì sao cần phân biệt ba lớp cơ chế?

Bài thuộc chương **Module import** của module **JAVA_VERSION_JAVA25**. Khi học Java 25 theo hướng phát triển hiện đại — từ compact source file, module import và flexible constructor bodies đến `ScopedValue`, KDF API, AOT cache và JFR — một vấn đề quan trọng là không đánh đồng cú pháp giúp mã nguồn ngắn gọn với cơ chế phụ thuộc và đóng gói của Java Platform Module System (JPMS).

**JEP 511 — Module Import Declarations** đã trở thành tính năng **chính thức trong Java 25**. Cú pháp:

~~~java
import module java.base;
~~~

giúp sử dụng tên ngắn của các kiểu `public` trong những package được module `java.base` export. Tuy nhiên, bản thân câu lệnh này **không thêm module vào đồ thị phân giải, không tạo cạnh `requires`, không mở package nội bộ và không biến kiểu không thể truy cập thành kiểu truy cập được**.

Đây là ba câu hỏi độc lập nhưng liên quan:

1. **Module resolution:** module nào có mặt trong **đồ thị module đã được phân giải**?
2. **Readability và accessibility:** module chứa mã nguồn hiện tại có **đọc được** module cung cấp kiểu không, và package/type đó có **được export, public và truy cập được** không?
3. **Name import:** khi quyền truy cập đã hợp lệ, có thể gọi một kiểu bằng **tên ngắn** thay vì tên đầy đủ không?

> Tư duy đúng: **resolve/read/export là điều kiện của khả năng truy cập; import chỉ là cơ chế sử dụng tên.** Nếu thiếu các điều kiện về module, thêm một dòng `import module ...;` không thể sửa vấn đề.

Sau bài này, bạn sẽ có thể:

- Giải thích JEP 511 ở Java 25 và vì sao không cần `--enable-preview`.
- Phân biệt `import module M;` với `requires M;` và `requires transitive M;`.
- Lần theo đường đi từ các module gốc (*roots*) tới đồ thị resolution và các cạnh readability.
- Giải thích việc `exports` và `exports ... to ...` quyết định những package/type nào thực sự có thể được import.
- Phân tích vì sao `requires transitive` của module được import ảnh hưởng tập kiểu được đưa vào phạm vi.
- Dự đoán lỗi compile khi thiếu `requires`, thiếu export, nhầm module path hoặc trùng tên kiểu.
- Dùng `java --describe-module`, `--show-module-resolution`, `jdeps` và kiểm thử biên dịch để xác minh graph.
- Thiết kế quan hệ module ổn định, không lạm dụng `--add-reads` / `--add-exports` hoặc API nội bộ.

## 2. JEP 511 trong Java 25: import theo module là gì?

### 2.1. Cú pháp và phạm vi

Java 25 hỗ trợ **single-module-import declaration**:

~~~java
import module <module-name>;
~~~

Ví dụ:

~~~java
import module java.base;

public class Summary {
    public static void main(String[] args) {
        List<String> values = List.of("Java", "25");
        Path output = Path.of("summary.txt");
        System.out.println(values + " -> " + output);
    }
}
~~~

`List` thuộc `java.util` và `Path` thuộc `java.nio.file`. Cả hai package được `java.base` export, nên một lệnh `import module java.base;` thay cho hai lệnh import thông thường.

**Đặc điểm chính:**

- Lệnh import ảnh hưởng **một compilation unit** (một tệp nguồn Java chứa lệnh đó), không tự động áp dụng cho toàn package hay project.
- Chỉ import **theo nhu cầu sử dụng** (*on demand*) các kiểu top-level `public` được phép truy cập từ những package xuất ra.
- Ngoài module được nêu, nó còn xem xét các package export từ các module mà **module hiện tại đọc được do đọc module được import**, chủ yếu qua chuỗi `requires transitive`.
- Không import static fields/methods. Ví dụ `Collections.emptyList()` vẫn phải gọi qua kiểu `Collections`, hoặc dùng `import static` nếu cần tên hàm trực tiếp.
- Không phải lệnh tải tất cả class vào bộ nhớ; compiler giải quyết tên lúc compile.
- Module import đã **final** từ Java 25. Không dùng `--enable-preview` chỉ vì có `import module`.

Tài liệu chuẩn: JLS Java SE 25 `7.5.5 và JEP 511.

### 2.2. So sánh với các loại import quen thuộc

| Câu lệnh | Phạm vi đưa tên vào tệp nguồn | Có tạo cạnh `requires` không? |
| --- | --- | --- |
| `import java.util.List;` | Một kiểu `List` cụ thể | **Không** |
| `import java.util.*;` | Các kiểu có thể truy cập trong package `java.util` | **Không** |
| `import module java.base;` | Kiểu từ các package export của `java.base` và phần transitive phù hợp | **Không** |
| `import static java.lang.Math.max;` | Thành viên static `max` | **Không** |
| `requires java.sql;` trong `module-info.java` | Khai báo phụ thuộc module, tạo readability trực tiếp | **Có** |
| `requires transitive java.sql;` | Khai báo phụ thuộc và truyền readability cho module phụ thuộc vào module này | **Có** |

**Không đồng nhất `import module java.base;` với `requires java.base;`.** `java.base` được mọi named module khác đọc ngầm theo JPMS. Trong khi đó, việc đưa những kiểu từ `java.util`, `java.nio.file` vào phạm vi tên ngắn là công việc của lệnh import.

### 2.3. Trường hợp compact source file

JEP 512 (cũng đã **final** trong Java 25) cho phép compact source file với một implicit class. JLS quy định mọi **compact compilation unit** được xem như có sẵn:

~~~java
import module java.base;
~~~

Vì vậy đoạn:

~~~java
// Demo.java, compact source file
void main() {
    List<String> words = List.of("module", "import");
    Path p = Path.of("notes.txt");
    IO.println(words + " / " + p);
}
~~~

hợp lệ với Java 25 khi chạy `java Demo.java`, không cần lệnh import tường minh và **không cần preview**.

**Phân biệt:** ordinary compilation unit vẫn tự import `java.lang.*` như trước; nó **không mặc nhiên được xem là có `import module java.base;`**. Đừng hiểu rằng mọi tệp Java thường từ Java 25 sẽ tự biết `List` và `Path` bằng tên ngắn.

## 3. Ba lớp: resolution, readability, accessibility rồi mới import

### 3.1. Module resolution tạo ra đồ thị nào?

Java module system giải quyết các module gốc (*root modules*) và những module chúng phụ thuộc. Một module có thể **observable** (JDK hoặc module path biết đến nó), nhưng vẫn **chưa được resolve** vào graph cho lần chạy/biên dịch cụ thể.

Giả sử:

~~~java
// module-info.java của com.acme.app
module com.acme.app {
    requires com.acme.contract;
}
~~~

Và:

~~~java
// module-info.java của com.acme.contract
module com.acme.contract {
    requires transitive java.logging;
    requires java.xml;
    exports com.acme.contract.api;
}
~~~

Đồ thị module có thể chứa `com.acme.app`, `com.acme.contract`, `java.logging`, `java.xml` và `java.base` cùng các dependency khác của runtime. Cần phân biệt **module được resolve** với **module được đọc bởi một module cụ thể**.

`com.acme.app` đọc `com.acme.contract` do `requires`. Nó cũng đọc `java.logging` qua `requires transitive` của `com.acme.contract`. Nhưng nó **không mặc nhiên đọc `java.xml`** chỉ vì `com.acme.contract` có một `requires java.xml` thông thường.

### 3.2. Readability là đồ thị có hướng

Các cạnh “đọc được” được tính từ `requires` và mở rộng theo `requires transitive`. Dùng sơ đồ:

~~~mermaid
flowchart LR
    A["com.acme.app"] -->|"requires"| B["com.acme.contract"]
    B -->|"requires transitive"| L["java.logging"]
    B -->|"requires"| X["java.xml"]
    A -.->|"readability được truyền"| L
    A -.- Z["KHÔNG có readability ngầm đến java.xml"]
~~~

Đường nét đứt từ `com.acme.app` đến `java.logging` là quan hệ được suy ra, **không phải** một dòng `requires java.logging;` được tự thêm vào `module-info.java` của app.

Chúng ta cần hai khái niệm chính:

- `requires M;`: module hiện tại đọc module M (cùng các readability transitive mà M mang theo).
- `requires transitive N;` trong M: mọi module đọc M sẽ đọc thêm N. Điều này hữu ích khi API công khai của M dùng kiểu được N export.

**Cảnh báo:** “A đã resolve được C” không đồng nghĩa “A đọc được C”. Resolution là vấn đề module có mặt trong graph; readability là khả năng một module truy cập tên và kiểu của module khác.

### 3.3. Export quyết định package nào nhìn thấy từ bên ngoài

Ngay cả khi A **đọc** B, A chỉ có thể dùng những kiểu thực sự có thể truy cập từ B.

Ví dụ:

~~~java
module com.acme.contract {
    requires transitive java.logging;
    exports com.acme.contract.api;
}
~~~

Trong module đó:

~~~text
com.acme.contract
├── api/
│   └── Message.java       // public record Message(...)
└── internal/
    └── SecretEngine.java  // public class, nhưng package KHÔNG export
~~~

Từ `com.acme.app`:

- `com.acme.contract.api.Message` có thể truy cập vì `com.acme.app` đọc module `com.acme.contract`, package `api` được export và bản thân kiểu là `public`.
- `com.acme.contract.internal.SecretEngine` **không thể** dùng trực tiếp vì package `internal` không được export, dù class được khai báo `public`.

`import module com.acme.contract;` **không làm thay đổi kết quả này**.

Một qualified export:

~~~java
exports com.acme.contract.friend to com.acme.app;
~~~

chỉ cho phép module **`com.acme.app`** nhìn thấy package `friend` theo quy định, không phải tất cả module khác. Import module vẫn tôn trọng điều kiện export hướng tới module hiện tại.

### 3.4. Vì sao `opens` không thay `exports`?

`opens` và `open module` dành cho quyền truy cập reflective theo quy tắc JPMS. Ví dụ framework serialization/DI có thể cần reflective access vào một package. Nhưng:

~~~java
opens com.acme.contract.internal to com.fasterxml.jackson.databind;
~~~

**không** biến các kiểu ở package đó thành API compile-time cho `import module com.acme.contract;`. Đừng dùng `opens` để “sửa” lỗi không tìm thấy kiểu qua module import.

| Cơ chế | Tác dụng chính | Có đủ để dùng tên kiểu `public` từ module khác trong source không? |
| --- | --- | --- |
| `requires` | Khai báo phụ thuộc và readability | Cần thêm `exports` phù hợp |
| `requires transitive` | Truyền readability cho module tiêu thụ | Cần thêm `exports` phù hợp |
| `exports p;` | Cho phép truy cập kiểu public trong package p từ module đọc được module này | Có, khi readability và access cùng đúng |
| `exports p to A;` | Export có chọn lọc cho A | Có, chỉ cho A khi readability đúng |
| `opens p;` | Cho phép reflective access theo quy tắc JPMS | **Không** thay compile-time `exports` |
| `import module M;` | Đưa tên kiểu hợp lệ vào scope của compilation unit | **Không** thêm quyền hay phụ thuộc |

## 4. Chính xác `import module M` lấy các kiểu từ đâu?

JLS 25 `7.5.5 cho biết `import module M;` đưa vào scope, *on demand*, các kiểu top-level `public` trong:

1. Những package được **M export cho module hiện tại**.
2. Những package được export từ **các module mà module hiện tại đọc được do đọc M**, nhờ các quan hệ **`requires transitive`**.

Quan trọng: điều kiện `module hiện tại đã đọc được M` phải đúng trước. Nếu không đọc được M, lệnh `import module M;` là lỗi compile-time. Không phải cứ nhìn thấy module trong `java --list-modules` là có thể import trực tiếp trong một named module bất kỳ.

### 4.1. Ví dụ lý thuyết với năm module

Mô hình được JLS dùng để giải thích ý nghĩa (đổi tên package để dễ theo dõi):

~~~java
module M0 {
    requires M1;
}

module M1 {
    exports p1;
    exports p2 to M0;
    exports p3 to M3;
    requires transitive M4;
    requires M5;
}

module M4 { exports p10; }
module M5 { exports p11; }
~~~

Trong một tệp nguồn thuộc module M0:

~~~java
package client;

import module M1;

// Có thể dùng kiểu public của p1 và p2.
// Có thể dùng kiểu public của p10 (qua requires transitive M4).
// Không tự lấy kiểu p3 vì package export cho M3, không cho M0.
// Không tự lấy kiểu p11 vì M1 chỉ requires M5, không transitive.
class Example { }
~~~

Bảng diễn giải:

| Package | Nơi khai báo | M0 có đọc module chứa package không? | Package export cho M0? | Có thể được `import module M1` đưa vào scope? |
| --- | --- | --- | --- | --- |
| `p1` | M1 | Có | Có, export chung | **Có** |
| `p2` | M1 | Có | Có, export riêng tới M0 | **Có** |
| `p3` | M1 | Có | **Không**, chỉ tới M3 | **Không** |
| `p10` | M4 | Có, qua M1 `requires transitive M4` | Có | **Có** |
| `p11` | M5 | **Không**, M1 chỉ `requires M5` | Có | **Không** |

**Không nhầm:** `M5` vẫn có thể được **resolve** trong graph vì M1 cần nó để hoạt động; điều đó không làm M0 đọc M5. Để M0 dùng API từ M5, phải thiết kế readability cho M0, thường bằng `requires M5;` trực tiếp hoặc thay contract của M1 khi có lý do kiến trúc.

### 4.2. Ví dụ chuẩn `java.sql` kéo theo các exported packages transitive

Tài liệu Oracle Java 25 minh họa:

~~~java
import module java.sql;
~~~

Lệnh này không chỉ nhập các kiểu `java.sql.Connection` và `java.sql.DriverManager` mà còn có thể đưa tên ngắn từ `java.logging` và `java.xml` vào scope vì `java.sql` dùng `requires transitive` với các module đó.

Trong named module:

~~~java
module com.acme.dbclient {
    requires java.sql;
}
~~~

Và:

~~~java
package com.acme.dbclient;

import module java.sql;

import java.util.Objects;

class ApiTypes {
    Connection connection;
    java.util.logging.Logger logger;
    org.w3c.dom.Document xmlDocument;

    void check() {
        Objects.requireNonNull(connection);
    }
}
~~~

`Connection`, `Logger`, `Document` đều từ các exported packages có thể truy cập sau khi đọc `java.sql` và các module transitive mà nó kéo theo. Việc viết fully qualified names cho `Logger`/`Document` ở đây nhằm làm ví dụ dễ đọc; có thể thử dùng tên ngắn khi không có conflict.

Nếu bỏ `requires java.sql;` khỏi `module-info.java`, `import module java.sql;` sẽ không giúp tự tạo cạnh đọc cho `com.acme.dbclient`, và mã sẽ thất bại khi compile.

**Lưu ý:** classpath/unnamed module có cách xác định root modules/readability riêng, nên một tệp chạy kiểu `java File.java` có thể dùng `import module java.sql;` thuận lợi mà không có `module-info.java`. Đừng dùng kết quả của ứng dụng classpath để suy ra rằng một named module cũng tự đọc `java.sql`.

## 5. Thực hành có thể tự tái hiện: hai named modules

Ta tạo một project nhỏ chỉ để chứng minh **cùng một `import module` nhưng quyền truy cập phụ thuộc vào `module-info.java`**. Không dùng thư viện ngoài, không cần preview và không tạo thêm file dữ liệu đặc biệt.

### 5.1. Sơ đồ cấu trúc

~~~text
src/
├── com.acme.contract/
│   ├── module-info.java
│   └── com/acme/contract/
│       ├── api/Message.java
│       └── internal/SecretEngine.java
└── com.acme.cli/
    ├── module-info.java
    └── com/acme/cli/Main.java
~~~

Ý định thiết kế:

- `com.acme.contract` là module cung cấp contract và export một API.
- `com.acme.cli` là module sử dụng contract.
- Contract truyền khả năng đọc `java.logging` sang client bằng `requires transitive java.logging`.
- Contract dùng `java.xml` trong nội bộ, nhưng không quảng bá phụ thuộc này như một phần API cho client.
- Package `internal` không được export.

### 5.2. Module cung cấp API

File `src/com.acme.contract/module-info.java`:

~~~java
module com.acme.contract {
    requires transitive java.logging;
    requires java.xml;

    exports com.acme.contract.api;
}
~~~

File `src/com.acme.contract/com/acme/contract/api/Message.java`:

~~~java
package com.acme.contract.api;

public record Message(String text) { }
~~~

File `src/com.acme.contract/com/acme/contract/internal/SecretEngine.java`:

~~~java
package com.acme.contract.internal;

public final class SecretEngine {

    public String secret() {
        return "not an exported API";
    }
}
~~~

Dù `SecretEngine` là `public`, package `internal` không được export. Mã bên ngoài module không nên dùng trực tiếp kiểu này.

### 5.3. Module sử dụng API

File `src/com.acme.cli/module-info.java`:

~~~java
module com.acme.cli {
    requires com.acme.contract;
}
~~~

File `src/com.acme.cli/com/acme/cli/Main.java`:

~~~java
package com.acme.cli;

import module com.acme.contract;

public class Main {

    public static void main(String[] args) {
        Message message = new Message("Hello Java 25");

        // Logger được module import đưa vào scope vì
        // com.acme.contract requires transitive java.logging.
        Logger logger = Logger.getLogger(Main.class.getName());

        logger.info(message.text());
    }
}
~~~

Tại sao `Message` hợp lệ? Vì module CLI đọc `com.acme.contract` và package `com.acme.contract.api` được export. Tại sao `Logger` hợp lệ? Vì CLI đọc `java.logging` **qua** phụ thuộc transitive được contract cung cấp, và `java.util.logging` được export.

### 5.4. Biên dịch và chạy

Trong thư mục gốc có `src`:

~~~bash
java -version
javac -version

javac --release 25 --module-source-path src -d mods \
  -m com.acme.contract,com.acme.cli

java --module-path mods \
  -m com.acme.cli/com.acme.cli.Main
~~~

Các dòng có dấu `\` là kiểu tiếp dòng trên shell Linux/macOS. Trong PowerShell, chạy mỗi lệnh trên **một dòng**:

~~~powershell
javac --release 25 --module-source-path src -d mods -m com.acme.contract,com.acme.cli
java --module-path mods -m com.acme.cli/com.acme.cli.Main
~~~

Kết quả dự kiến có thông điệp từ `java.util.logging.Logger`, chẳng hạn:

~~~text
INFO: Hello Java 25
~~~

Định dạng log/thời gian có thể khác tùy runtime. Hãy kiểm tra JDK thực sự là 25, vì `import module` chỉ trở thành syntax chính thức từ Java 25.

### 5.5. Ba thí nghiệm cố ý làm sai

**Thí nghiệm A — Bỏ `requires com.acme.contract;` khỏi CLI:**

~~~java
module com.acme.cli {
    // không còn requires com.acme.contract
}
~~~

Lúc này `import module com.acme.contract;` **không cấp quyền đọc**. Compiler phải báo lỗi liên quan tới module không đọc được hoặc kiểu không truy cập được. Sửa bằng cách khôi phục `requires`, **không** phải bằng cách thêm `import module` lần nữa.

**Thí nghiệm B — Bỏ `exports com.acme.contract.api;` khỏi contract:**

~~~java
module com.acme.contract {
    requires transitive java.logging;
    requires java.xml;
    // không exports com.acme.contract.api;
}
~~~

CLI vẫn đọc contract, nhưng `Message` không còn là API được export cho module khác. `import module` không vượt qua encapsulation. Sửa bằng `exports` theo yêu cầu thiết kế API; không nên mở rộng `opens` hay `--add-exports` làm phương án chính.

**Thí nghiệm C — Thử dùng SecretEngine:**

~~~java
// Trong Main.java
SecretEngine engine = new SecretEngine(); // Không hợp lệ!
~~~

Package `com.acme.contract.internal` không được export. Dù thêm:

~~~java
import com.acme.contract.internal.SecretEngine;
~~~

compiler vẫn không cho dùng API này từ module CLI theo quy tắc JPMS. Nguyên nhân là **accessibility**, không phải thiếu câu import. Thay bằng method public trong API của contract nếu tính năng đó thực sự cần được cung cấp.

### 5.6. Thí nghiệm transitive vs non-transitive

Trong module contract hiện tại:

~~~java
requires transitive java.logging;
requires java.xml;
~~~

`java.util.logging.Logger` có thể đi vào `com.acme.cli` qua `import module com.acme.contract;`. Nhưng kiểu `org.w3c.dom.Document` từ `java.xml` **không** được đưa vào scope nhờ import đó, vì contract chỉ có `requires java.xml;` không truyền readability cho CLI.

Nếu CLI thật sự cần làm việc trực tiếp với XML API, một lựa chọn rõ ràng là khai báo:

~~~java
module com.acme.cli {
    requires com.acme.contract;
    requires java.xml;
}
~~~

rồi:

~~~java
import org.w3c.dom.Document;
~~~

Hoặc `import module java.xml;` sau khi module đã đọc được. Không sửa contract thành `requires transitive java.xml;` chỉ để giảm số dòng import nếu XML **không** phải thành phần API công khai của contract.

## 6. `requires transitive`: công cụ thiết kế API, không phải cách làm import gọn bằng mọi giá

Một API module có thể dùng kiểu từ module khác trong **public signature**:

~~~java
// module com.acme.contract
module com.acme.contract {
    requires transitive java.logging;
    exports com.acme.contract.api;
}
~~~

Giả sử public API của contract có:

~~~java
package com.acme.contract.api;

import java.util.logging.Logger;

public interface LogAware {
    Logger logger();
}
~~~

Khi client chỉ `requires com.acme.contract;`, nó sẽ đọc `java.logging` theo transitive requirement, do đó có thể sử dụng kiểu `Logger` trong chữ ký API mà không buộc tự viết `requires java.logging;`.

**Thiết kế hợp lý:** dùng `requires transitive` khi phụ thuộc N là một phần của API mà người tiêu thụ M cần đọc. `requires` thông thường nên đủ cho implementation detail của M.

**Không đồng nhất** truyền readability với “re-export package”: module M không trở thành chủ sở hữu package của N; Java chỉ cho module tiêu thụ đọc N theo graph. Và lệnh `import module M;` không biến N thành một phần nhị phân của M.

### Một vòng đời khi refactor API

Ban đầu `com.acme.contract` tự định nghĩa kiểu `LoggerAdapter`. Sau này nhóm chuyển phần logging contract sang `com.acme.logging.api`:

~~~java
module com.acme.contract {
    requires transitive com.acme.logging.api;
    exports com.acme.contract.api;
}
~~~

Client vẫn `requires com.acme.contract;`, nhưng đọc thêm `com.acme.logging.api` thông qua mối quan hệ transitive. Tùy cấu trúc exports, `import module com.acme.contract;` còn có thể đưa tên ngắn các kiểu export từ module API mới vào scope. Đây là lợi ích cho quá trình refactor có kiểm soát; đổi tên type, package, signature vẫn phải có kiểm thử tương thích.

## 7. `import module java.se`: trường hợp module tổng hợp

`java.se` là module tập hợp các thành phần chuẩn của Java SE. Bản thân nó không export package riêng nhưng có nhiều `requires transitive` tới những module Java SE khác; trong Java 25, `java.se` còn bao gồm transitive dependence với `java.base`. Vì vậy:

~~~java
import module java.se;
~~~

có thể đưa tên ngắn của các kiểu được export từ nhiều module Java SE vào cùng compilation unit. Tuy nhiên, có hai điểm phải chú ý:

**Thứ nhất: module phải được resolve/read.** Với ứng dụng classpath/unnamed module, `java.se` **không nằm trong nhóm root module mặc định**. Tài liệu Oracle Java 25 hướng dẫn thêm:

~~~bash
javac --release 25 --add-modules java.se Example.java
java --add-modules java.se Example
~~~

Với named module, thiết kế rõ ràng:

~~~java
module com.acme.example {
    requires java.se;
}
~~~

**Thứ hai: phạm vi kiểu quá rộng dễ gây nhập nhằng.** Ví dụ `java.util.List` và `java.awt.List` đều có tên ngắn `List`, hay `java.lang.classfile.Label` và `java.awt.Label`. `import module java.se;` có thể đưa nhiều kiểu trùng tên vào phạm vi hơn so với các import tập trung.

Vì thế **không dùng `java.se` mặc định chỉ để “import mọi thứ” cho ứng dụng lớn**. Hãy dùng module import cụ thể hoặc import một kiểu riêng khi muốn API phụ thuộc được minh bạch.

## 8. Xung đột tên và quy tắc ưu tiên

Khi nhiều module có kiểu top-level `public` cùng tên, module import không tự biết bạn định dùng kiểu nào.

### 8.1. Ví dụ `List`: java.base vs java.desktop

~~~java
import module java.base;
import module java.desktop;

class AmbiguousTypes {

    // LỖI COMPILE: List có thể là java.util.List hoặc java.awt.List.
    List items;
}
~~~

Cả hai module đều có package export chứa kiểu tên `List`. Cách giải quyết:

~~~java
import module java.base;
import module java.desktop;

import java.util.List;

class FixedTypes {
    List<String> items = List.of("A", "B");
    java.awt.List awtList; // dùng tên đầy đủ khi thật sự cần AWT
}
~~~

Một **single-type-import** tường minh có thể chọn `java.util.List` thay vì hai lựa chọn on-demand. Hoặc giữ cả hai bằng tên đầy đủ để người đọc không phải đoán.

### 8.2. Có khi một module import cũng gây nhập nhằng

JLS Java 25 nêu ví dụ `import module java.desktop;` và tên `Element`: các package `javax.swing.text` và `javax.swing.text.html.parser` đều export một kiểu tên `Element`. Không cần nhiều `import module` mới gặp conflict.

Đừng nhầm compiler báo `reference to Element is ambiguous` với lỗi module không đọc được. Cách sửa phù hợp là **single-type-import** hoặc **fully qualified name**, không phải `--add-reads` hay `--add-exports`.

### 8.3. Quy tắc code review đề xuất

- Dùng module import khi nó giảm đáng kể boilerplate cho các API gắn kết trong cùng một module.
- Nếu xuất hiện nhiều tên trùng, thêm explicit import cho những kiểu thường dùng.
- Nếu danh sách tên trở nên khó đọc, chuyển về import từng kiểu; code rõ ràng thường quan trọng hơn tiết kiệm vài dòng.
- Không dùng `import module java.se;` như một thay thế mặc định cho import rõ ràng trong public library.
- Giữ kiểu công khai trong exported package; tránh import nội bộ module khác thông qua tùy chọn mở encapsulation.

## 9. Classpath, module path và automatic modules

### 9.1. Unnamed module

Các file hoặc JAR truyền thống trên classpath thường thuộc **unnamed module**. Trong bối cảnh này, nguồn vẫn dùng được module import Java 25:

~~~java
// XmlCheck.java, không có module-info.java
import module java.xml;

public class XmlCheck {
    public static void main(String[] args) throws Exception {
        DocumentBuilderFactory factory =
            DocumentBuilderFactory.newInstance();
        System.out.println(factory.getClass().getName());
    }
}
~~~

Ví dụ dùng `DocumentBuilderFactory` thuộc `javax.xml.parsers`, một package được `java.xml` export.

~~~bash
javac --release 25 XmlCheck.java
java XmlCheck
~~~

`java.xml` là module chuẩn được mặc định resolve trong bối cảnh classpath thông dụng; nếu runtime image bị rút gọn, phải xác minh module đó còn tồn tại. Không có `module-info.java` **không có nghĩa JPMS hoàn toàn bị bỏ qua**: JDK vẫn dùng module graph để quản lý các module hệ thống.

### 9.2. Named module

Khi có `module-info.java`, `requires` là hợp đồng dependency rõ ràng. Named module **không tự động đọc mọi module có trên module path**. Ví dụ:

~~~java
module com.acme.xmlapp {
    requires java.xml;
}
~~~

Chỉ sau khi đọc `java.xml` thì `import module java.xml;` trong mã module đó mới hợp lệ. Chuyển một ứng dụng từ classpath sang module path có thể làm lộ những phụ thuộc từng được cho là “ngầm có sẵn”.

### 9.3. Automatic modules

Một JAR chưa có `module-info.class` có thể được xử lý như **automatic module** trên module path. Nó có tên module, export package theo quy tắc automatic module, và được cấu hình readability khác với explicit named module.

`import module M;` có thể được dùng với module đó **nếu M được resolve và được đọc**. Tuy nhiên tên automatic module suy ra từ tên JAR hoặc manifest có thể thay đổi khi thư viện phát hành module descriptor chính thức. Không nên thiết kế public API phụ thuộc vào tên automatic module thiếu ổn định mà không đánh giá rủi ro. Ưu tiên thư viện có tên module ổn định.

### 9.4. `--add-modules` khác `--add-reads`

| Tùy chọn | Chủ yếu ảnh hưởng điều gì? | Có tương đương `requires` trong mã nguồn không? |
| --- | --- | --- |
| `--module-path` | Nơi tìm module có thể quan sát | **Không** |
| `--add-modules M` | Thêm module vào nhóm root/resolution | **Không**; chưa tự cho named module A đọc mọi M |
| `--add-reads A=B` | Bổ sung cạnh readability cho module A ở lần chạy/biên dịch tương ứng | Chỉ là override, không thay contract trong `module-info.java` |
| `--add-exports M/p=A` | Mở quyền truy cập package `p` từ M cho A trong bối cảnh cụ thể | Không tương đương thiết kế public export |
| `--add-opens M/p=A` | Cho phép reflective access sâu hơn | **Không** tự import kiểu để compile |
| `import module M;` | Đưa tên ngắn của kiểu hợp lệ vào scope tệp nguồn | **Không** thay đổi module graph |

Các cờ `--add-reads` / `--add-exports` có vai trò đặc biệt khi chuyển đổi hệ thống cũ hoặc thử nghiệm tương thích. **Không xem chúng là cách cấu hình mặc định** để bỏ qua API boundaries của module hiện đại. Ưu tiên sửa `module-info.java` và thiết kế export đúng mức.

## 10. Dùng công cụ JDK 25 để nhìn thấy graph thật

Khi nghi ngờ module path, dependency hoặc import sai, đừng chỉ đọc thông báo lỗi của IDE. Dùng công cụ của JDK đang chạy.

### 10.1. Kiểm tra phiên bản, module có mặt và descriptor

~~~bash
java -version
javac -version
java --list-modules
java --describe-module java.sql
java --describe-module java.se
~~~

`--list-modules` cho biết module có thể thấy từ runtime image, **không phải** toàn bộ quan hệ readability của một ứng dụng cụ thể.

`--describe-module java.sql` giúp xem các directive `requires`, `exports` của module JDK. Với JDK 25, tìm những `requires transitive` tới các module được import gián tiếp.

### 10.2. In quá trình resolution

Với project hai module đã compile ở mục 5:

~~~bash
java --show-module-resolution --module-path mods \
  -m com.acme.cli/com.acme.cli.Main
~~~

Đầu ra liệt kê các module và quan hệ được đưa vào quá trình resolution. Hãy tìm `com.acme.cli`, `com.acme.contract` và `java.logging` / `java.xml`, sau đó so với `module-info.java`. **Không kết luận readability chỉ bằng việc thấy tên module xuất hiện**; cần xem đường đi các `requires` và `requires transitive`.

### 10.3. Phân tích dependency bằng jdeps

~~~bash
jdeps --module-path mods --module com.acme.cli
~~~

`jdeps` giúp nhìn dependency từ class/module ở mức bytecode. Nó có thể xác nhận lớp thực sự phụ thuộc package/type nào, nhưng không phải công cụ kiểm tra toàn bộ semantics của *source-level import*. Một module import có thể đưa rất nhiều kiểu vào scope trong lúc source chỉ sử dụng một kiểu; `jdeps` tập trung vào **phụ thuộc thực tế sau biên dịch**, không liệt kê “mọi tên có thể được import”.

### 10.4. Ba lỗi và cách phân biệt

| Thông báo/triệu chứng | Lớp nguyên nhân | Hướng sửa |
| --- | --- | --- |
| `module M is not read by the current module` | Readability | Thêm `requires M;` phù hợp hoặc sửa đường `requires transitive` |
| `module not found: M` | Resolution / module path / version | Kiểm tra module tồn tại, module path và root resolution |
| `package p is not visible` hoặc `package p is not exported` | Accessibility / exports | Dùng API của exported package, hoặc thay module contract nếu chủ sở hữu đồng ý |
| `cannot find symbol T` nhưng module đúng | Import scope, tên kiểu hoặc thiếu dependency | Xác minh T có public/export, tên đầy đủ và đúng JDK |
| `reference to T is ambiguous` | Nhiều kiểu cùng tên cùng được import on demand | Thêm explicit single-type import hoặc dùng tên đầy đủ |
| `class file has wrong version` / syntax không được nhận | Compiler/JDK không phải bản phù hợp | Xác minh `javac -version`, Gradle/Maven toolchain |
| IDE xanh nhưng CI lỗi | Classpath/module path khác hoặc thiếu module-info ở pipeline | So task compile, flags và module dependencies |

Đừng đưa `--enable-preview` vào lệnh compile để “sửa” `import module` trên JDK 25: JEP 511 đã final. Nếu compiler vẫn không nhận cú pháp, trước tiên xác minh **JDK thực sự đang sử dụng**.

## 11. Các quy tắc thiết kế module nên áp dụng

### 11.1. Thiết kế readability ở nơi sở hữu module contract

Nếu module `orders` cung cấp API cho `billing`, một mô hình hợp lý:

~~~java
// orders/module-info.java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

~~~java
// billing/module-info.java
module com.example.billing {
    requires com.example.orders;
}
~~~

Bên trong billing:

~~~java
package com.example.billing;

import module com.example.orders;

// Dùng các kiểu public trong com.example.orders.api khi cần.
class BillingService { }
~~~

Đừng thêm `requires transitive com.example.orders;` ở `billing` trừ khi **các module đọc billing cũng cần đọc orders như một phần public API của billing**. Điều này giúp tránh làm lan rộng đồ thị phụ thuộc không cần thiết.

### 11.2. Public API và implementation detail

Với một thư viện, **export ít package nhất cần thiết**. Không export package `internal` chỉ vì một lớp từ module tiêu thụ đang truy cập trực tiếp nó. Nếu nhiều module cần một kiểu, chuyển kiểu đó vào package API có chủ đích và kiểm thử khả năng tương thích.

Module import càng gọn thì càng dễ che khuất việc một module đang dùng nhiều phần của API; vì vậy ở code production nên kết hợp kiểm tra:

- `module-info.java` có `requires` phù hợp cho mỗi phụ thuộc.
- Các `exports` tương ứng thực sự thuộc public contract.
- Không có chu trình phụ thuộc ngoài chủ đích.
- Không dựa vào `--add-exports` trong launcher để truy cập JDK internals.
- Không dùng `requires transitive` chỉ để né explicit import trong code client.
- Các dependency được resolve đúng trên cả local, CI và runtime image (kể cả `jlink`).

### 11.3. Khi nào nên chọn import module?

**Nên cân nhắc** khi một module có nhiều exported packages mà client sử dụng như một API gắn kết, ví dụ `java.sql` hoặc `java.xml`. Cú pháp gọn có ích cho code mẫu, CLI utility và ứng dụng dùng nhiều kiểu từ một module.

**Nên cân nhắc import từng kiểu** khi code sản phẩm nhỏ, cần thể hiện chính xác các phụ thuộc hoặc đang gặp xung đột tên. Không có quy định bắt buộc chuyển tất cả `import java.util.List;` sang `import module java.base;` trong Java 25.

**Không dùng làm “module dependency manager”:** import module không tải Maven/Gradle dependency, không đưa JAR lên module path, không thay `requires` và không ảnh hưởng việc module tự động được giải quyết ở runtime.

## 12. Liên hệ với các khả năng Java 25 còn áp dụng

Đề bài nằm trong module Java 25 hiện đại, nên cần đặt `import module` trong bức tranh rộng hơn mà không áp dụng hướng dẫn từ preview cũ:

| Khả năng Java 25 | Trạng thái trong JDK 25 | Liên hệ với module import / graph |
| --- | --- | --- |
| Module import declarations — JEP 511 | **Final** | Giải quyết tên ngắn của các kiểu export từ module đã đọc |
| Compact source files — JEP 512 | **Final** | Compact unit được import `java.base` ngầm |
| Flexible constructor bodies — JEP 513 | **Final** | Tính năng ngôn ngữ khác, không sửa readability |
| Scoped Values — JEP 506 | **Final** | API runtime thuộc thư viện JDK, không đòi import module nào mới nếu dùng từ `java.base` |
| Key Derivation Function API — JEP 510 | **Final** | Dùng API công khai và module JDK phù hợp, không cần preview |
| AOT cache — JEP 514/515 | Tùy chọn runtime JDK 25 | Tối ưu khởi động, không đổi phạm vi tên hay `requires` trong source |
| JFR observability | Công cụ runtime | Quan sát hành vi, không tự cấp quyền module |
| Vector API — JEP 508 | **Incubator** trong JDK 25 | Module `jdk.incubator.vector` cần được resolve/đọc; `import module` không thay `--add-modules` hoặc `requires` |

**Ghi nhớ:** không áp cờ `--enable-preview` cho JEP 511 hoặc 512 ở Java 25. Các vòng preview của Java 23/24 đã kết thúc; khi học JDK 25 cần dựa trên JLS/Javadoc tương ứng. Tính năng thử nghiệm khác vẫn có quy trình bật riêng, nhưng đó không phải yêu cầu của module import.

## 13. Bài thực hành tổng hợp

**Bối cảnh:** nhóm xây một ứng dụng Java 25 gồm `com.acme.contract` và `com.acme.cli`. Nhiệm vụ là phát hiện chỗ nhầm giữa source import và module dependency.

### Phần A — Baseline hợp lệ

1. Tạo cây nguồn ở mục 5.
2. Biên dịch bằng JDK 25, không bật preview.
3. Chạy module CLI, xác nhận log sử dụng `Message` và `Logger`.
4. Mở module descriptor và giải thích vì sao `Logger` được import qua `requires transitive java.logging`.

**Đạt** khi giải thích được hai đường đọc: CLI → contract và CLI → logging thông qua contract.

### Phần B — Thử lỗi readability

1. Bỏ `requires com.acme.contract;` trong CLI, giữ `import module com.acme.contract;`.
2. Biên dịch và ghi lỗi về module không đọc được.
3. Khôi phục `requires` và biên dịch lại.

**Đạt** khi chứng minh **import không tạo requires**.

### Phần C — Thử lỗi exports

1. Bỏ `exports com.acme.contract.api;` khỏi contract, giữ các `requires`.
2. Thử dùng `Message` từ CLI.
3. Ghi lỗi và khôi phục `exports`.
4. Thử import `SecretEngine` thuộc package internal.

**Đạt** khi giải thích được vì sao `public` của class không đủ khi package chưa export.

### Phần D — Thử transitive

1. Giữ `requires transitive java.logging`, kiểm tra `Logger` dùng được trong CLI.
2. Đổi tạm thành `requires java.logging` (không transitive); biên dịch lại.
3. Nếu CLI thực sự cần logging API, tự thêm `requires java.logging;` trong CLI rồi kiểm tra cơ chế import/tên kiểu; hoặc khôi phục transitive nếu logging là API contract.
4. Giải thích tại sao `java.xml` không được CLI đọc mặc định dù contract `requires java.xml`.

**Đạt** khi phân biệt dependency của contract với dependency bị truyền qua public API.

### Phần E — Thử xung đột tên

1. Viết một tệp import `java.base` và `java.desktop`.
2. Dùng `List`, quan sát lỗi ambiguous.
3. Thêm `import java.util.List;` và biên dịch lại.
4. Viết giải thích vì sao thay đổi import không sửa đồ thị module.

**Đạt** khi sửa được lỗi chỉ bằng thay đổi **name binding**, không dùng VM flags.

### Phần F — Truy vết graph

1. Chạy `java --describe-module com.acme.contract` trên module path phù hợp.
2. Dùng `java --show-module-resolution` khi chạy ứng dụng.
3. Dùng `jdeps` để xác định các kiểu/package được class thực sự sử dụng.
4. Đối chiếu với bảng ở mục 4 để giải thích module resolved và readable khác nhau ở đâu.

**Đạt** khi đưa ra kết luận có bằng chứng compiler, module descriptor và runtime resolution.

## 14. Các câu hỏi tự đánh giá

1. Trong Java 25, `import module M;` có tự tạo `requires M;` không? Vì sao?
2. Ba điều kiện resolution, readability và accessibility khác nhau ở đâu?
3. Một module xuất hiện trong `java --list-modules` có mặc nhiên được mọi named module đọc không?
4. Vì sao `public class SecretEngine` ở package không export vẫn không thể dùng từ module khác?
5. `requires transitive N;` ảnh hưởng tới những module nào và dùng khi nào trong public API?
6. Vì sao client đọc `java.logging` từ `com.acme.contract` nhưng không tự đọc `java.xml` trong ví dụ?
7. `import module java.sql;` có thể đưa tên ngắn từ những module nào ngoài `java.sql`?
8. `import module java.se;` có nghĩa gì khi bản thân `java.se` không export package? Vì sao classpath có thể cần `--add-modules java.se`?
9. `exports p to A;` khác `exports p;` ra sao?
10. Vì sao `opens p;` không tự giúp compile code truy cập kiểu ở package đó?
11. Khi `java.util.List` và `java.awt.List` đều được import on demand, cách giải quyết lỗi ambiguous nào rõ ràng nhất?
12. `--module-path`, `--add-modules` và `--add-reads` khác nhau ở điểm nào?
13. Vì sao `jdeps` không nhất thiết liệt kê tất cả kiểu một câu `import module M;` **có thể** đưa vào scope?
14. Compact source file Java 25 tự nhận những kiểu nào từ `java.base` và có cần preview không?
15. Khi chuyển từ classpath sang named module, vì sao code trước đây compile được có thể đột nhiên lỗi visibility/readability?
16. Làm thế nào để thiết kế một contract module không lạm dụng `requires transitive`?
17. Khi nào dùng `import module` tạo lợi ích rõ ràng và khi nào import từng kiểu phù hợp hơn?
18. Trước khi nâng JDK hoặc tạo runtime image rút gọn, cần kiểm chứng những module nào hiện diện và được resolve?

## 15. Tài liệu tham khảo

- [Java SE 25 JLS `7.5.5 — Single-Module-Import Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.5.5): định nghĩa import, điều kiện module phải được đọc, transitive packages và ví dụ ambiguity.
- [Java SE 25 JLS `7.7.1 — Dependences](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7.1): `requires`, `requires transitive` và phụ thuộc ngầm `java.base`.
- [Oracle Java SE 25 — Module Import Declarations](https://docs.oracle.com/en/java/javase/25/language/module-import-declarations.html): ví dụ `java.base`, `java.sql`, `java.se` và ambiguity.
- [OpenJDK JEP 511 — Module Import Declarations](https://openjdk.org/jeps/511): thiết kế tính năng đã final trong Java 25.
- [Java SE 25 — java.lang.module API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/package-summary.html): module resolution và readability graph.
- [Java SE 25 JLS `7.3 — Compilation Units](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.3): implicit module import trong compact compilation units.
- [OpenJDK JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512): compact source file là tính năng chính thức từ Java 25.
- [Oracle JDK 25 java command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `--module-path`, `--add-modules`, `--show-module-resolution`.
- [Oracle JDK 25 javac command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--module-source-path`, `--release 25` và named module compilation.
- [Oracle JDK 25 jdeps command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html): kiểm tra module/package dependencies ở mức bytecode.

