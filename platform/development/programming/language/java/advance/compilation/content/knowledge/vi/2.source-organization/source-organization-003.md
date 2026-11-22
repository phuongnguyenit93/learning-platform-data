# Import, static import và giới hạn của việc nhập tên trong Java

Trong Java, `import` giúp mã nguồn tham chiếu đến một **kiểu** (class, interface, enum, annotation, kiểu lồng) bằng tên ngắn; `import static` giúp tham chiếu đến **thành viên static** bằng tên ngắn. Cả hai chủ yếu phục vụ **phân giải tên lúc biên dịch**, không phải lệnh nạp lớp, cấp phát đối tượng, tải dependency hay đóng gói mã.

Đây là chủ đề về **tổ chức mã nguồn**: hiểu một khai báo import áp dụng ở đâu, vì sao hai kiểu có cùng tên làm compiler bối rối, và những công việc vẫn phải tự xử lý bằng cấu hình build/runtime.

## 1. Bản chất: tên đơn giản và tên đủ điều kiện

Hai đoạn sau nói đến cùng kiểu `java.util.List`:

~~~java
// Không import; mã minh họa nằm bên trong một method
java.util.List<String> languages = java.util.List.of("Java", "Kotlin");
~~~

~~~java
// Đặt ở đầu tệp .java
import java.util.List;

// Trong class/method của tệp đó:
List<String> languages = List.of("Java", "Kotlin");
~~~

`java.util.List` là tên đủ điều kiện/canonical của kiểu trong ví dụ; `List` là tên đơn giản. `import java.util.List;` làm cho compiler có thể hiểu `List` trong phạm vi compilation unit tương ứng. Nó **không đổi tên class thật**, không chuyển mã vào package hiện tại và không làm thư viện có mặt trên classpath.

Một *compilation unit* Java thông thường tương ứng một tệp `.java`. Phạm vi khai báo import nằm ở compilation unit **có chứa chính khai báo import ấy**. Hai tệp `A.java` và `B.java` cùng `package lesson;` vẫn có danh sách import độc lập.

Thứ tự cấu trúc điển hình trong nguồn Java:

~~~java
package lesson;

import java.util.List;
import static java.lang.Math.max;

public class Example {
    List<String> values = List.of("a", "b");

    public int greater(int a, int b) {
        return max(a, b);
    }
}
~~~

Khai báo `package` đứng trước imports, và imports đứng trước khai báo class/interface/enum cấp cao nhất. Không đặt import bên trong method hay thân class. Dòng import không phải biểu thức và không sinh side effect khi chương trình chạy.

## 2. Bốn dạng import truyền thống (hợp lệ trên Java 17)

| Loại | Cú pháp | Tên có thể sử dụng |
| --- | --- | --- |
| Single-type import | `import java.util.List;` | `List` |
| Type-import-on-demand | `import java.util.*;` | `List`, `ArrayList`,... khi cần và không nhập nhằng |
| Single-static import | `import static java.lang.Math.max;` | `max(4, 9)` |
| Static-import-on-demand | `import static java.lang.Math.*;` | `max(...)`, `min(...)`, `PI`,... |

`*` chỉ có nghĩa “xem xét các tên được phép theo nhu cầu” trong một package hoặc một kiểu đã chỉ rõ. Không có ý nghĩa đệ quy qua mọi package con, không làm JVM nạp tất cả class và không sao chép toàn bộ code vào class đang biên dịch.

### 2.1. Single-type import

~~~java
import java.util.List;
import java.util.ArrayList;
~~~

Cho phép viết:

~~~java
// Trong một method của class có các imports bên trên
List<String> names = new ArrayList<>();
~~~

Nếu thiếu import `ArrayList`, compiler không tự suy ra rằng import `List` nghĩa là import luôn những class implement `List`. Khi cần, dùng tên đủ điều kiện:

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
~~~

Có thể import **kiểu lồng** bằng canonical name của kiểu:

~~~java
import java.util.Map.Entry;

// Trong method, Java 9+:
Entry<String, Integer> pair = java.util.Map.entry("x", 1);
~~~

Dòng import rút gọn tên `Entry`. Nó không tự import kiểu ngoài `Map`; vì thế ví dụ vẫn gọi `java.util.Map.entry(...)` theo tên đủ điều kiện. Với nested class không-static, import tên kiểu cũng không thay thế yêu cầu có outer instance khi khởi tạo đối tượng.

### 2.2. Type import theo nhu cầu

~~~java
import java.util.*;
~~~

Các kiểu công khai có thể truy cập **trực tiếp thuộc package `java.util`** được xét khi compiler gặp tên đơn giản tương ứng. Ví dụ `List`, `ArrayList`, `Collections`.

Nhưng `java.util.*` **không** nhập:

- Các kiểu của subpackage `java.util.concurrent` (như `ConcurrentHashMap`). Nếu cần, dùng `import java.util.concurrent.ConcurrentHashMap;`.
- Tên đơn giản của nested type `Map.Entry` chỉ vì `Map` thuộc package được import. Dùng `import java.util.Map.Entry;` nếu muốn viết `Entry`.
- Static method/field của `Collections`, `Arrays` hoặc các class khác. Muốn gọi `emptyList()` không kèm `Collections.` thì dùng `import static`.
- Tất cả dependency của các class, hay những JAR không nằm trong cấu hình build.

Type-import-on-demand cũng có thể đặt một **kiểu** trước `.*`: ví dụ `import java.util.Map.*;` xét các member types có thể truy cập của `Map` như `Entry`. Nó vẫn không nhập static method `Map.of` để gọi `of(...)` trần.

### 2.3. Single-static import

~~~java
import static java.lang.Math.max;
import static java.lang.Math.PI;
import static java.util.Collections.emptyList;
~~~

Cho phép viết:

~~~java
int biggest = max(4, 9);         // Math.max(4, 9)
boolean overThree = PI > 3.0;   // Math.PI > 3.0
int count = emptyList().size(); // Collections.emptyList().size()
~~~

Một single-static import theo tên method có thể đưa **nhiều overload** cùng tên vào việc tìm lời gọi phù hợp, chẳng hạn các overload của `Math.max`. Compiler chọn overload theo kiểu và số lượng đối số, không theo thứ tự dòng import.

Static import có thể áp dụng cho static methods, static fields, member types static có thể truy cập và enum constants. Chẳng hạn:

~~~java
import static java.time.DayOfWeek.MONDAY;
// Trong method: MONDAY.getValue() -> 1 theo ISO-8601
~~~

Enum constant `MONDAY` là một static field của kiểu enum `DayOfWeek`. Ngược lại, `String.length()` là instance method: không thể dùng `import static java.lang.String.length;` để biến nó thành hàm độc lập; cần có đối tượng chuỗi.

### 2.4. Static import theo nhu cầu

~~~java
import static java.lang.Math.*;
~~~

Lúc này `max(...)`, `min(...)`, `sqrt(...)`, `PI`,... là các tên static có thể được xét theo nhu cầu. Compiler vẫn áp dụng quy tắc overload, quyền truy cập và xung đột tên.

Cần phân biệt rõ:

- `import java.lang.Math.*;`: một dạng **type-import-on-demand** nhằm tới member types của `Math`, không đưa static method `max` vào phạm vi tên ngắn.
- `import static java.lang.Math.*;`: nhằm tới các **static members** của `Math`, bao gồm methods và fields, không nhập các class khác trong package `java.lang`.

## 3. Ví dụ hoàn chỉnh có thể chạy trên Java 17+

Tạo tệp `src/lesson/ImportDemo.java` với toàn bộ nội dung sau:

~~~java
package lesson;

import java.util.ArrayList;
import java.util.List;

import static java.lang.Math.PI;
import static java.lang.Math.max;
import static java.time.DayOfWeek.MONDAY;
import static java.util.Collections.emptyList;

public final class ImportDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Java");

        System.out.println(names);
        System.out.println(max(4, 9));
        System.out.println(PI > 3.0);
        System.out.println(MONDAY.getValue());
        System.out.println(emptyList().size());
    }
}
~~~

Chạy từ thư mục gốc có thư mục `src`:

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/lesson/ImportDemo.java
java -cp out lesson.ImportDemo
~~~

Nếu `out` đã tồn tại thì bỏ qua `mkdir out`. Ví dụ dùng một mục classpath nên lệnh `java -cp out ...` hoạt động cả trên PowerShell và shell Unix.

**Stdout chính xác:**

~~~text
[Java]
9
true
1
0
~~~

Diễn giải:

1. `List` và `ArrayList` được compiler hiểu nhờ **type imports**. `new ArrayList<>()` mới là thao tác tạo đối tượng lúc chạy.
2. `max(4, 9)` gọi overload `Math.max(int, int)` và in `9`.
3. `PI` rút gọn `Math.PI`; so sánh `PI > 3.0` là `true`.
4. `MONDAY` là enum constant; `DayOfWeek.MONDAY.getValue()` trả về `1`.
5. `emptyList()` là static method trả về danh sách trống, nên kích thước bằng `0`.

Viết `Math.max(4, 9)` thay `max(4, 9)` cho cùng kết quả. Static import không tạo một bản sao method và không làm method chạy tại thời điểm import.

## 4. Những tên đã thấy được mà không cần import

**`java.lang`:** Một compilation unit Java thông thường có type-import-on-demand mặc định cho các kiểu trong `java.lang`, vì vậy viết `String`, `System`, `Math`, `Object` được. Tuy nhiên, không có static import mặc định cho `Math.max`: vẫn gọi `Math.max(2, 3)`.

**Cùng package:** hai class trong `package lesson;` có thể tham chiếu nhau bằng tên ngắn khi kiểu có thể truy cập và compiler thấy nguồn/bytecode tương ứng. Không cần `import lesson.Helper;` chỉ để dùng một class `Helper` trong cùng package.

Ví dụ hai tệp độc lập với ví dụ mục 3:

~~~java
// src/lesson/Helper.java
package lesson;

public final class Helper {
    public static String message() {
        return "ok";
    }
}
~~~

~~~java
// src/lesson/UseHelper.java
package lesson;

public final class UseHelper {
    public static void main(String[] args) {
        System.out.println(Helper.message());
    }
}
~~~

Lệnh:

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/lesson/Helper.java src/lesson/UseHelper.java
java -cp out lesson.UseHelper
~~~

Kết quả stdout:

~~~text
ok
~~~

Nếu dùng cùng workspace ví dụ trước và `out` đã tồn tại, bỏ qua `mkdir out`.

**Tên đầy đủ:** bất cứ khi nào phù hợp với khả năng truy cập, có thể viết `java.util.List` thay vì nhập tên ngắn `List`. Tên đầy đủ đặc biệt hữu ích khi có nhiều kiểu cùng simple name. Ngoài ra, kiểu khai báo trong compilation unit hoặc member type trong phạm vi bao quanh có thể hiện diện theo quy tắc scope của Java mà không cần khai báo import mới.

## 5. Khi import gây xung đột tên

### 5.1. Hai single-type imports trùng simple name

**Đoạn sau cố ý sai, chỉ dùng để nhận diện lỗi biên dịch:**

~~~java
import java.util.Date;
import java.sql.Date;

class Example {
    Date date;
}
~~~

`java.util.Date` và `java.sql.Date` là hai kiểu **khác nhau**, cùng simple name `Date`. Không được viết hai single-type imports trùng simple name mà trỏ tới hai kiểu khác nhau; compiler sẽ báo lỗi, kể cả trước khi field `date` được dùng.

Cách giải quyết:

~~~java
import java.util.Date;

class Example {
    Date utilDate;
    java.sql.Date sqlDate;
}
~~~

Đây chỉ là ví dụ về xung đột tên, không phải lời khuyên chọn `java.util.Date` thay cho API `java.time` trong thiết kế ứng dụng mới.

### 5.2. Hai wildcard imports trùng tên khi sử dụng

**Đoạn sau cũng cố ý sai ở chỗ dùng `Date`:**

~~~java
import java.util.*;
import java.sql.*;

class Example {
    Date date;  // Ambiguous: java.util.Date hay java.sql.Date?
}
~~~

Có thể khai báo cả hai wildcard imports, nhưng khi viết `Date`, compiler không chọn theo “import nào đứng trước”. Để sửa, dùng `java.util.Date` rõ ràng hoặc thêm một single-type import cụ thể.

Ví dụ hợp lệ:

~~~java
import java.util.Date;
import java.sql.*;

class Example {
    Date utilDate;              // java.util.Date
    java.sql.Date sqlDate;      // java.sql.Date
}
~~~

Trong trường hợp không bị khai báo gần hơn che khuất, **single-type import cụ thể** giúp xác định simple name rõ hơn các ứng viên chỉ được nhìn thấy nhờ import-on-demand. Đây là **quy tắc phân giải tên**, không phải quy tắc ưu tiên dựa trên thứ tự các dòng import.

### 5.3. Static import cũng có trùng tên

**Đoạn sau cố ý sai khi sử dụng `MAX_VALUE`:**

~~~java
import static java.lang.Integer.MAX_VALUE;
import static java.lang.Long.MAX_VALUE;

class Example {
    long limit = MAX_VALUE; // Có hai static fields khác nhau cùng tên
}
~~~

Cách sửa tường minh:

~~~java
class Example {
    long intLimit = Integer.MAX_VALUE;
    long longLimit = Long.MAX_VALUE;
}
~~~

Nếu là **method overload**, compiler còn xét kiểu đối số; nhiều method cùng tên chưa chắc lỗi nhưng có thể gặp overload ambiguity. Vì vậy static import wildcard của nhiều utility classes dễ khiến người đọc khó xác định method thực sự được gọi.

### 5.4. Tên gần hơn có thể che tên imported

Các khai báo kiểu/biến/thành viên trong những phạm vi phù hợp có thể shadow hoặc obscure tên đưa vào bằng import. Không nên suy luận rằng một dòng `import` sẽ luôn buộc mọi simple name giống nó trong tệp phải chỉ cùng một khai báo.

Khi cần xác nhận, đổi tạm sang tên đủ điều kiện (`java.util.List`) hoặc `Type.member` (`Math.max`), rồi kiểm tra phần mà IDE/compiler đang phân giải. Java không có cú pháp `import java.util.Date as UtilDate;` trong bộ cú pháp Java 17; đó là cách viết của ngôn ngữ khác, không phải alias import Java.

## 6. Những giới hạn quan trọng của import

### 6.1. Không nhập package con

`import java.util.*;` không đưa `ConcurrentHashMap` từ `java.util.concurrent` vào vùng tên ngắn. Package `java.util.concurrent` là package riêng dù có chung tiền tố tên. Không có `import java.util.**;` trong Java.

### 6.2. Không tự nhập static members hoặc kiểu lồng

`import java.util.Collections;` chỉ giúp viết `Collections`. Nó không tự cho phép viết `emptyList()`; cần `Collections.emptyList()` hoặc `import static java.util.Collections.emptyList;`.

Tương tự, `import java.util.Map;` không có nghĩa có thể viết `Entry` ở mọi nơi; muốn dùng kiểu lồng bằng tên ngắn, import `java.util.Map.Entry` hoặc dùng `Map.Entry`.

### 6.3. Không vượt qua access control

Một kiểu nằm trong package khác nhưng không public không tự trở nên public nhờ import. Static import cũng không cho phép truy cập private static field của class khác. Compiler vẫn kiểm tra quyền truy cập, package, quan hệ kiểu, visibility của module và tên khai báo hợp lệ.

Import sai tới kiểu không tồn tại hoặc không thể truy cập thường là **lỗi biên dịch ngay ở import**, kể cả nếu tên đó không xuất hiện sau này.

### 6.4. Không tải thư viện hoặc phân phối runtime dependencies

~~~java
import com.vendor.Client;
~~~

Dòng này không tải `client.jar` từ Internet. Compiler vẫn cần dependency chứa `com.vendor.Client` trên classpath/module path thích hợp. Build tool như Gradle/Maven hoặc cấu hình `javac -cp` mới cung cấp kiểu cho quá trình compile.

Ví dụ:

~~~bash
javac -cp lib/client.jar -d out src/lesson/App.java
~~~

Lệnh này **chỉ minh họa khi `lib/client.jar` đã có thật** và source/import phù hợp; nó không tạo hoặc tải thư viện. Khi chạy, JVM cũng cần dependency tương thích theo classpath/module path, cách phân phối JAR hoặc class loader phù hợp. Dùng nhiều entry trong `-cp` cần dấu `;` trên Windows, dấu `:` trên Linux/macOS.

Biên dịch được nhưng runtime báo `ClassNotFoundException` hoặc `NoClassDefFoundError` có thể do thư viện không được cung cấp khi chạy, phiên bản không tương thích hoặc lớp khởi tạo thất bại trước đó. Thêm import mới **không tự chữa** những vấn đề phân phối và nạp lớp này.

### 6.5. Không thay cho `requires` trong JPMS

Trong một named module:

~~~java
// module-info.java
module lesson.app {
    requires java.sql;
}
~~~

Trong compilation unit của module:

~~~java
package lesson;

import java.sql.Connection;

public final class Holder {
    private Connection connection;
}
~~~

`requires java.sql;` xác lập quan hệ đọc module theo JPMS, còn `import java.sql.Connection;` rút gọn tên kiểu **trong một tệp**. Đối với type/static imports thông thường, import không thay `requires`. Ngược lại, module dependency cũng không tự động tạo simple names cho mọi kiểu của module. Package cần được export phù hợp và kiểu vẫn cần accessible.

### 6.6. Không nạp lớp hoặc khởi tạo static chỉ vì dòng import

`import static lesson.Settings.VALUE;` giúp dùng tên `VALUE` (nếu thành viên accessible). Nhưng bản thân dòng import không chạy `Settings`, không gọi method, không chạy `static { ... }` và không tạo đối tượng. Việc class loading, linking và initialization diễn ra theo các yêu cầu lúc chạy của JVM.

Một field hằng thỏa quy tắc *constant variable* còn có thể được compiler inline vào nơi sử dụng. Vì vậy không thể suy luận runtime class initialization chỉ từ việc đọc một static import.

### 6.7. Import không dùng tới khác với import không hợp lệ

`javac` thông thường chấp nhận một import hợp lệ nhưng không được dùng; IDE/linter có thể đề nghị xóa để mã nguồn rõ hơn. Một import sai tên, sai quyền truy cập hoặc xung đột single-type imports vẫn có thể là lỗi compile dù nội dung code không nhắc tới nó.

## 7. Java 25 bổ sung `import module`

Bốn dạng nêu trên đều tương thích Java 17. Từ **Java 25**, *module import declarations* là tính năng ngôn ngữ chính thức:

~~~java
// Java 25+, không hợp lệ nếu compile với --release 17
import module java.base;
~~~

Dạng này nhập theo nhu cầu các **public top-level types** thuộc các package do module export phù hợp; ví dụ `java.base` export `java.util`, `java.util.function`, `java.util.stream`. Vì vậy một dòng `import module java.base;` có thể thay nhiều type imports thông thường trong source Java 25+.

Module import vẫn có thể gây nhập nhằng nếu các package cung cấp kiểu trùng tên. Nó khác `import static` và không có tác dụng chạy chương trình, đóng gói JAR hay tải dependency. Trong dự án yêu cầu **JDK 17 / `--release 17`**, dùng các dạng import truyền thống và không đưa `import module` vào mã nguồn.

## 8. Thực hành lựa chọn cú pháp

| Trường hợp | Cách viết dễ đọc |
| --- | --- |
| Một kiểu được dùng nhiều lần | `import java.util.List;` rồi viết `List` |
| Hai kiểu có cùng tên (`Date`, `List`...) | Import một kiểu, dùng tên đầy đủ cho kiểu còn lại |
| Một static method chỉ xuất hiện 1–2 lần | `Math.max(a, b)` để thấy rõ nguồn |
| Công thức dùng nhiều `min`, `max` | Cân nhắc static imports cụ thể |
| Static methods tên quá chung (`of`, `get`...) | Ưu tiên `Type.member` tránh đọc nhầm |
| Nhiều kiểu trong cùng package | Dùng explicit hoặc wildcard theo quy ước dự án; wildcard không làm chương trình nặng hơn |
| Dự án compile bằng Java 17 | Tránh cú pháp `import module` của Java 25 |

Nhóm các import thành thư viện chuẩn, thư viện ngoài, class dự án, static imports là một **quy ước format**. Compiler không chọn tên theo thứ tự các nhóm này. Một số dự án cấu hình IDE/Checkstyle tự sắp xếp import; nên tuân thủ quy ước của dự án để giữ diff nhỏ và tránh nhập nhằng.

## 9. Câu hỏi tự kiểm tra

1. **`import java.util.*;` có nhập `ConcurrentHashMap` không?** Không. `ConcurrentHashMap` thuộc `java.util.concurrent`, một package riêng.
2. **`import java.lang.Math;` có cho viết `max(2,3)` không?** Không. Cần `Math.max(2,3)` hoặc `import static java.lang.Math.max;`.
3. **`import static java.lang.System.out;` có hợp lệ không?** Có, vì `out` là static field công khai. `out.println("ok");` gọi method trên đối tượng `PrintStream` được field đó tham chiếu.
4. **A.java import `List`; B.java cùng package có tự dùng `List` không?** Không; mỗi compilation unit có imports riêng.
5. **Khai báo `import static Math.*` có đóng gói toàn bộ `Math` vào artifact không?** Không. Import không quyết định nội dung JAR.
6. **Hai wildcard imports chứa kiểu cùng tên có luôn lỗi ngay không?** Không nhất thiết; khi simple name đó được dùng và không giải quyết được xung đột thì compiler báo ambiguous.
7. **Một single-type import cụ thể giải quyết `Date` giữa `java.util.*` và `java.sql.*` thế nào?** `import java.util.Date;` chỉ rõ tên `Date` trong trường hợp không có shadowing gần hơn; kiểu SQL vẫn có thể dùng `java.sql.Date`.
8. **Import đúng nhưng compiler báo `package ... does not exist` thì xử lý gì?** Kiểm tra typo, artifact tồn tại, version API, classpath/module path và access. Import không cung cấp dependency.
9. **Lệnh `java -jar app.jar` lỗi vì thiếu lớp sau khi compile thành công: thêm import có giúp không?** Không. Phải bảo đảm dependency runtime được đóng gói/cung cấp đúng.
10. **`import module java.base;` chạy với `--release 17` được không?** Không. Đây là cú pháp chuẩn hóa ở Java 25.

## 10. Checklist khi review import

1. Tên canonical/package của kiểu đúng chưa? Kiểu đó public/accessible không?
2. Thành viên cần gọi là static hay instance? Nếu instance, phải gọi trên đối tượng.
3. Có simple names trùng nhau từ wildcard, static imports hoặc khai báo gần hơn không?
4. Mỗi tệp `.java` đã khai báo những imports nó cần chưa? Có thể dùng tên đầy đủ thay thế không?
5. Dependency có trong đường tìm kiếm của compiler **và** môi trường runtime không?
6. Nếu dùng named modules, quan hệ `requires`/`exports` phù hợp chưa?
7. Mức phiên bản Java trong build có hỗ trợ cú pháp import đang viết không?

**Kết luận:** `import` chọn **tên kiểu**, `import static` chọn **tên thành viên static**, và cả hai chỉ tạo thuận tiện về tên trong compilation unit. Chúng không nhập package con đệ quy, không sửa quyền truy cập, không tải thư viện, không thay module dependencies, không đóng gói JAR và không tự thực thi chương trình.

### Tài liệu tham khảo

- [Java Language Specification, `7.5 — Import Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.5).
- [Oracle Java 25 — Module Import Declarations](https://docs.oracle.com/en/java/javase/25/language/module-import-declarations.html).
