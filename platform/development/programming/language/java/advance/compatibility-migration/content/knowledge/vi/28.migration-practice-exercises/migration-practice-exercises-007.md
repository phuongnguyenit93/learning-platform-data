# Tái hiện lỗi reflection và loại bỏ nhu cầu dùng --add-opens

## 1. Bối cảnh bài thực hành

Một dự án Java cũ có thể dùng reflection để đọc/ghi trường `private`, gọi constructor nội bộ hoặc truy cập API không được công bố của JDK. Cách làm ấy đôi khi chạy trên Java 8 hoặc một cấu hình Java 9–15, nhưng gặp lỗi khi nâng lên JDK 17, JDK 21 hoặc các bản mới hơn có **strong encapsulation**.

Một lỗi điển hình:

~~~text
java.lang.reflect.InaccessibleObjectException:
  Unable to make field private final byte[] java.lang.String.value accessible:
  module java.base does not "opens java.lang" to unnamed module ...
~~~

Giải pháp “chữa cháy” thường thấy:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED \
     -cp out LegacyStringProbe
~~~

Cờ này có thể giúp tái hiện và khoanh vùng vấn đề, nhưng nó **không làm code dựa vào trường nội bộ trở thành API tương thích**, cũng không phải phương án mặc định để phát hành lâu dài.

Bài thực hành thuộc **Java Advance Compatibility Migration — Bài thực hành**, có mục tiêu: **tái hiện lỗi reflection, xác định nguyên nhân tại ranh giới module và thay code/configuration để ứng dụng chạy mà không cần `--add-opens` dòng lệnh**.

Chúng ta sẽ làm hai bài lab độc lập:

1. **Lab A:** Một ứng dụng classpath đọc trường `String.value` của JDK, thất bại vì `java.base` không mở `java.lang`. Chuyển sang public Java APIs.
2. **Lab B:** Hai named modules, một module cố truy cập trường `private` của module kia. Sửa ưu tiên bằng public API; nếu framework thực sự cần reflective access, dùng `opens ... to ...` có phạm vi trong module descriptor thay cho JVM flag diện rộng.

Các phần sau mở rộng sang thư viện bên thứ ba, frameworks, annotation/serialization, agents, CI, kiểm thử tương thích và cách gỡ cờ còn sót.

## 2. Mục tiêu và tiêu chí hoàn thành

Sau khi học, người đọc có thể:

- Nhận biết `InaccessibleObjectException` phát sinh từ `AccessibleObject.setAccessible(true)`.
- Phân biệt `exports` và `opens`, cũng như reflective access với Java bytecode access thông thường.
- Dùng một JVM flag tạm thời để **đối chứng**, không biến nó thành dependency vĩnh viễn.
- Thay truy cập private internals của JDK bằng Java public APIs, giữ đúng behavior.
- Thiết kế API hoặc module descriptor để framework xử lý được private members trong phạm vi cho phép.
- Phát hiện `--add-opens` được inject từ CLI, Gradle/Maven, test runner, `JAVA_TOOL_OPTIONS`, container hay agent.
- Viết regression tests chứng minh ứng dụng chạy trên JDK đích **không có cờ mở package trái phép**.
- Phân biệt lỗi module encapsulation với `NoSuchMethodError`, `VerifyError`, `UnsatisfiedLinkError` hoặc lỗi thiếu JAR.

**Kết quả cuối:** Cùng chức năng nghiệp vụ chạy trên JDK mục tiêu, không cần `--add-opens=java.base/java.lang=ALL-UNNAMED`; những thay đổi access hợp pháp đối với module do dự án sở hữu được mô tả và kiểm thử rõ ràng.

## 3. Điều kiện tiên quyết

Sử dụng một JDK hỗ trợ JPMS, khuyến nghị **JDK 17 hoặc JDK 21** để quan sát strong encapsulation một cách rõ ràng.

Kiểm tra:

~~~bash
java -version
javac -version
~~~

Hai lệnh phải phản ánh JDK mà bạn định chạy lab. Nếu máy có nhiều JDK, xác nhận `JAVA_HOME`, `PATH` và JVM thực của terminal.

Cần có:

- JDK với `java` và `javac` (không chỉ một runtime tối giản).
- Trình soạn thảo và terminal (Bash/zsh, PowerShell hoặc tương đương).
- Quyền tạo thư mục và file thử nghiệm.
- Không cần Gradle, Maven hay dependency bên thứ ba cho hai lab chính.

**Giới hạn:** Ví dụ `String.value` được thiết kế cho những JDK HotSpot/OpenJDK thông dụng, nơi trường này tồn tại và là implementation detail. Tên/kiểu trường này **không thuộc Java SE public contract**; JVM khác hoặc JDK tương lai có thể không chứa trường hoặc biểu diễn dữ liệu giống như ví dụ. Khi đó kết quả có thể là `NoSuchFieldException` thay vì `InaccessibleObjectException`, và chính điều này càng chứng minh việc phụ thuộc vào nội bộ là không an toàn.

## 4. Thư mục làm bài

Tạo workspace độc lập, không sửa trực tiếp mã production:

~~~text
reflection-lab/
├── src/
│   ├── LegacyStringProbe.java
│   └── PublicStringProbe.java
├── out/                   # tạo bởi javac
├── modsrc/                # dùng ở Lab B
└── mods/                  # output Lab B
~~~

Trên Bash:

~~~bash
mkdir -p reflection-lab/src
cd reflection-lab
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force reflection-lab/src
Set-Location reflection-lab
~~~

Các đoạn code được lưu vào đúng filename tương ứng. Những output text được ghi trong bài là **kết quả mong đợi minh họa**, không phải log đã chạy trực tiếp trong phiên soạn bài.

## 5. Lab A — Code cũ truy cập private field của JDK

Tạo file `src/LegacyStringProbe.java`:

~~~java
import java.lang.reflect.Field;

public final class LegacyStringProbe {
    public static void main(String[] args) throws Exception {
        String text = "Hello Java";

        Field field = String.class.getDeclaredField("value");
        System.out.println("Declared field type: "
                + field.getType().getTypeName());

        // Dòng gây lỗi khi java.base/java.lang không được mở:
        field.setAccessible(true);

        Object rawValue = field.get(text);
        System.out.println("Internal value runtime type: "
                + rawValue.getClass().getTypeName());
    }
}
~~~

Đây là **anti-pattern có chủ đích để tái hiện lỗi**. Không copy cách truy cập `String.value` vào code nghiệp vụ.

### 5.1. Phân tích từng lệnh

`String.class.getDeclaredField("value")` tìm một field được khai báo trực tiếp trong class `String`, kể cả khi nó là `private`. Việc **lấy metadata Field** không nhất thiết đã đòi quyền đọc nội dung.

`field.setAccessible(true)` yêu cầu bỏ qua Java access checks trong phạm vi mà luật module cho phép. Trên JDK với strong encapsulation, module `java.base` không mở package `java.lang` cho classpath code ở unnamed module, nên yêu cầu bị từ chối.

`field.get(text)` chỉ chạy nếu bước mở access trước đó thành công. Giá trị raw internal representation của `String` không phải API ổn định và không được dùng để suy luận encoding logic của chuỗi.

## 6. Biên dịch và chạy để tái hiện

Từ thư mục `reflection-lab`:

~~~bash
javac --release 17 -d out src/LegacyStringProbe.java
java -cp out LegacyStringProbe
~~~

Nếu dùng JDK 21, lệnh `--release 17` vẫn có thể phù hợp vì code này chỉ cần API Java 17 hoặc cũ hơn. Nếu dùng một JDK thấp hơn 17, hãy đổi target theo khả năng compiler, nhưng kết quả về module access có thể khác theo release.

Trên JDK 17/21 HotSpot phổ biến, output trước khi thất bại có dạng:

~~~text
Declared field type: byte[]
Exception in thread "main"
  java.lang.reflect.InaccessibleObjectException:
  Unable to make field private final byte[] java.lang.String.value accessible:
  module java.base does not "opens java.lang" to unnamed module ...
    at java.base/java.lang.reflect.AccessibleObject...
    at java.base/java.lang.reflect.Field...
    at LegacyStringProbe.main(LegacyStringProbe.java:...)
~~~

Wording, line numbers và chi tiết stack trace có thể khác theo JDK build.

### 6.1. Những điều đã chứng minh

1. Class ứng dụng đã compile và JVM có thể nạp nó.
2. `String.value` có thể tồn tại nhưng không được phép truy cập từ caller.
3. Lỗi nằm tại yêu cầu **deep reflection** vào `java.base/java.lang`, không phải Java source không compile được.
4. Thông điệp đã chỉ rõ **module sở hữu**, **package**, và **module của caller**.

### 6.2. Những điều chưa chứng minh

- Chưa chứng minh cờ mở package là giải pháp bền vững.
- Chưa chứng minh kiểu field luôn là `byte[]` trong mọi JDK.
- Chưa chứng minh việc đọc private value đáp ứng đúng nghĩa nghiệp vụ của chuỗi.
- Chưa chứng minh các lỗi khác của ứng dụng sẽ biến mất nếu thêm flag.

## 7. Giải mã thông điệp `InaccessibleObjectException`

Ví dụ:

~~~text
module java.base does not "opens java.lang" to unnamed module
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| `java.base` | Module chứa class mà caller đang tìm cách reflect |
| `java.lang` | Package chứa field/method cần deep access |
| `opens` | Quyền deep reflection đối với package |
| `unnamed module` | Code chạy trên classpath, không thuộc named module |
| `setAccessible(true)` | Yêu cầu suppress access checks bị từ chối |

Một lỗi ở package khác có thể có dạng:

~~~text
module java.base does not "opens java.util" to unnamed module
~~~

hoặc:

~~~text
module com.example.model does not
  "opens com.example.model.internal"
  to module com.example.consumer
~~~

Phân tích **module nguồn, package nguồn và caller module** trước khi định chọn cách sửa. Đừng chỉ nhìn tên exception rồi tự thêm một chuỗi flags phổ biến.

## 8. Thử `--add-opens` đúng một lần để đối chứng

Chạy lại class cũ:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED \
     -cp out LegacyStringProbe
~~~

Với JDK HotSpot hiện giữ trường `String.value`, chương trình có thể đi qua `setAccessible(true)` và in:

~~~text
Declared field type: byte[]
Internal value runtime type: byte[]
~~~

Điều này xác nhận lý do thất bại có liên quan tới **module openness**, thay vì field hoàn toàn không tồn tại. Tuy nhiên, đây chỉ là một **thử nghiệm khoanh vùng**.

### 8.1. `ALL-UNNAMED` nghĩa là gì?

Classpath code nằm trong các unnamed modules tương ứng với class loaders. `ALL-UNNAMED` là target đặc biệt dành cho toàn bộ unnamed modules trong cú pháp launcher flag. Việc mở `java.base/java.lang` cho tất cả unnamed modules **rộng hơn** quyền cần của một call site cụ thể.

### 8.2. Flag không làm public API thay đổi

`String.value` vẫn là `private` và vẫn là implementation detail. `--add-opens` cho phép truy cập phản chiếu trong phạm vi được chỉ định, nhưng không hứa rằng field đó sẽ không bị đổi tên, kiểu, layout hoặc behavior trong JDK update tiếp theo.

### 8.3. Ghi lại bằng chứng đối chứng

~~~text
Without --add-opens: InaccessibleObjectException
With --add-opens: reflective access proceeds
Likely cause: deep reflection into strongly encapsulated JDK package
Preferred fix: remove dependency on JDK-private representation
~~~

**Không thêm flag vào Dockerfile hoặc startup script production chỉ vì lab chạy khi có nó.**

## 9. Vì sao reflection vào `String.value` là một thiết kế rủi ro?

Trước Java 9, nhiều JDK dùng một biểu diễn nội bộ khác với các phiên bản có **Compact Strings**. Trên các JDK triển khai Compact Strings, dữ liệu có thể được giữ trong một `byte[]` kèm thông tin về cách biểu diễn. Điều này là **chi tiết JVM implementation**, không phải hợp đồng public của `java.lang.String`.

Code truy cập field nội bộ có thể:

- Giả định sai `char[]` trong khi runtime dùng `byte[]`.
- Hiểu nhầm Java UTF-16 code units với bytes của internal storage.
- Bỏ qua thông tin về coder/encoding nội bộ.
- Phụ thuộc vào layout private field không được bảo đảm.
- Làm lộ dữ liệu nhạy cảm nếu log nội dung thô.
- Hỏng vì strong encapsulation dù vẫn compile bình thường.

Một ứng dụng muốn **đếm ký tự**, **mã hóa ra bytes**, **đọc code points** hoặc **so sánh chuỗi** nên dùng Java public API theo đúng nhu cầu, không cần đọc raw field.

## 10. Lab A — Sửa bằng Java public APIs

Tạo file `src/PublicStringProbe.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class PublicStringProbe {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00"; // A và một emoji.

        int utf16Units = text.length();
        int codePoints =
                text.codePointCount(0, text.length());
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

        System.out.println("UTF-16 code units: " + utf16Units);
        System.out.println("Unicode code points: " + codePoints);
        System.out.println("UTF-8 bytes: " + utf8.length);

        // Assertions không phụ thuộc flag -ea.
        if (utf16Units != 3 || codePoints != 2
                || utf8.length != 5) {
            throw new AssertionError("Unexpected String semantics");
        }

        String roundTrip =
                new String(utf8, StandardCharsets.UTF_8);
        if (!text.equals(roundTrip)) {
            throw new AssertionError("UTF-8 round-trip failed");
        }

        System.out.println("PASS");
    }
}
~~~

Các API sử dụng:

- `String.length()`: số **UTF-16 code units**, không nhất thiết là số Unicode code points.
- `String.codePointCount(...)`: số Unicode code points trong một khoảng.
- `String.getBytes(StandardCharsets.UTF_8)`: chuyển chuỗi thành bytes theo encoding được **chỉ định công khai**.
- `new String(bytes, StandardCharsets.UTF_8)`: giải mã bytes UTF-8 thành chuỗi.
- `String.equals(...)`: so sánh nội dung chuỗi theo contract.

Không cần tìm private field nào cả.

## 11. Compile và chạy bản đã sửa

~~~bash
javac --release 17 -d out src/PublicStringProbe.java
java -cp out PublicStringProbe
~~~

Output mong đợi:

~~~text
UTF-16 code units: 3
Unicode code points: 2
UTF-8 bytes: 5
PASS
~~~

**Không có `--add-opens`.** Mã chỉ gọi public APIs đã được Java SE hỗ trợ.

### 11.1. Tại sao 3, 2 và 5?

Chuỗi gồm ký tự `A` và emoji được biểu diễn bằng một surrogate pair trong UTF-16:

- `A` chiếm một UTF-16 code unit.
- Emoji chiếm hai UTF-16 code units.
- Tổng `length()` = 3.
- Về code points, chuỗi có 2.
- Trong UTF-8, `A` là 1 byte và emoji là 4 bytes, tổng 5.

Điều này chứng minh một API public cần được chọn **theo semantic requirement**, không phải theo khả năng tiếp cận mảng bytes nội bộ.

### 11.2. Code points không phải user-perceived characters

Một grapheme cluster có thể gồm nhiều code points (ví dụ ký tự và combining marks). Nếu nhu cầu là đếm “ký tự nhìn thấy”, `codePointCount` chưa đủ trong mọi ngôn ngữ. Khi đó cần một giải pháp xử lý grapheme boundary phù hợp, ví dụ Java text APIs/Unicode library với phạm vi support được kiểm chứng.

**Không có một phép thay thế một-một cho mọi kiểu dùng sai `String.value`**; phải hiểu mục đích gốc.

## 12. So sánh trước và sau

| Tiêu chí | Legacy reflection | Public API |
| --- | --- | --- |
| Truy cập private JDK field | Có | Không |
| `setAccessible(true)` | Có | Không |
| Cần `--add-opens` trên JDK 17/21 | Có thể cần để code cũ chạy | Không |
| Phụ thuộc layout của `String` | Có | Không |
| Unicode/encoding semantics | Dễ suy luận sai | Chỉ định qua APIs |
| JDK update compatibility | Rủi ro cao | Theo Java SE API contract |
| Test/triage | Khó giải thích behavior | Có thể kiểm thử bằng input/output |
| Bảo mật và least privilege | Mở package JDK | Không cần mở |

### 12.1. Mục tiêu là giảm đặc quyền

Thành công không chỉ là “exception biến mất”. Thành công là **không còn lý do để bật quyền truy cập private internals**. Một public API có ý nghĩa nghiệp vụ rõ giúp tránh cả lỗi encapsulation lẫn việc phụ thuộc implementation layout.

## 13. Phân biệt `exports` và `opens`

Trong Java Platform Module System (JPMS), hai khái niệm này giải quyết vấn đề khác nhau:

| Cơ chế | Cho phép làm gì? | Có mở private members cho deep reflection? |
| --- | --- | --- |
| `exports p` | Cho modules khác truy cập public types/members của package `p` theo access rules | Không tự động |
| `exports p to m` | Qualified public API export tới module `m` | Không tự động |
| `opens p` | Cho runtime deep reflection vào package `p` | Có, theo luật reflective access |
| `opens p to m` | Chỉ mở `p` cho module `m` | Có, chỉ trong phạm vi target |
| `open module m` | Mở các packages của module cho deep reflection | Có, rất rộng |
| `--add-opens=m/p=t` | Mở package `p` ở module `m` cho target `t` qua launcher | Có, phạm vi tùy target |

**`exports` không tương đương `opens`.** Việc một class `public` được export không có nghĩa một class khác được tự do đọc `private` fields của nó.

### 13.1. Deep reflection không có nghĩa gọi public method

Gọi `customer.id()` là truy cập API bình thường khi type và method public được export phù hợp. Gọi `Customer.class.getDeclaredField("id")` rồi `setAccessible(true)` là yêu cầu deep reflection qua Java access checks.

Trong thiết kế ổn định, hãy ưu tiên API công khai có chủ đích. `opens` dành cho những runtime frameworks thật sự cần cơ chế reflective binding.

## 14. Lab B — Hai named modules trong một ứng dụng

Ở Lab A, caller chạy trên **classpath** nên được mô tả là `unnamed module`. Trong Lab B, ta tạo **hai named modules** để quan sát lỗi rõ hơn.

Mục tiêu:

- Module `com.example.model` sở hữu object `Customer`.
- Module `com.example.reader` sử dụng API của `Customer`.
- Package chứa `Customer` được `exports`, nhưng không `opens`.
- Code reader cố dùng reflection để đọc field `private id` và nhận `InaccessibleObjectException`.

Cấu trúc:

~~~text
reflection-lab/
└── modsrc/
    ├── com.example.model/
    │   ├── module-info.java
    │   └── com/example/model/api/Customer.java
    └── com.example.reader/
        ├── module-info.java
        └── com/example/reader/Main.java
~~~

Tên module/package và đường dẫn là ví dụ. Bài này không cần Maven/Gradle; các modules được compile bằng `javac --module-source-path`.

## 15. Khai báo module cung cấp model

File `modsrc/com.example.model/module-info.java`:

~~~java
module com.example.model {
    exports com.example.model.api;
}
~~~

File `modsrc/com.example.model/com/example/model/api/Customer.java`:

~~~java
package com.example.model.api;

import java.util.Objects;

public final class Customer {
    private final String id;

    public Customer(String id) {
        this.id = Objects.requireNonNull(id);
    }

    public String id() {
        return id;
    }
}
~~~

Trong module này:

- `Customer` là public class ở package được export.
- Constructor và `id()` là public APIs.
- Field `id` vẫn private và không thuộc contract phản chiếu được mở cho các module khác.

Không có lý do nghiệp vụ nào bắt buộc consumer phải đọc field trực tiếp; `id()` đã được cung cấp rõ ràng.

## 16. Tạo consumer cố tình vi phạm encapsulation

File `modsrc/com.example.reader/module-info.java`:

~~~java
module com.example.reader {
    requires com.example.model;
}
~~~

File `modsrc/com.example.reader/com/example/reader/Main.java`:

~~~java
package com.example.reader;

import com.example.model.api.Customer;
import java.lang.reflect.Field;

public final class Main {
    public static void main(String[] args) throws Exception {
        Customer customer = new Customer("C-100");

        Field field =
                Customer.class.getDeclaredField("id");
        field.setAccessible(true); // Deep reflection: bị từ chối.

        System.out.println(field.get(customer));
    }
}
~~~

Consumer có `requires com.example.model`, nên có thể thấy public class `Customer` trong exported package. Nhưng `requires` và `exports` **không làm field private truy cập được qua `setAccessible(true)`**.

## 17. Biên dịch và chạy Lab B

Từ thư mục `reflection-lab`, với cấu trúc `modsrc` đã tạo:

~~~bash
javac --release 17 \
  --module-source-path modsrc \
  -d mods \
  -m com.example.model,com.example.reader

java --module-path mods \
  --module com.example.reader/com.example.reader.Main
~~~

Trên JDK 17/21, ví dụ dự kiến báo lỗi dạng:

~~~text
java.lang.reflect.InaccessibleObjectException:
  Unable to make field private final java.lang.String
  com.example.model.api.Customer.id accessible:
  module com.example.model does not
  "opens com.example.model.api"
  to module com.example.reader
~~~

Đây là lỗi **giữa hai module do dự án sở hữu**, không phải lỗi do field private của JDK.

### 17.1. Vì sao `exports` chưa đủ?

`exports com.example.model.api` cho consumer dùng:

~~~java
new Customer("C-100").id()
~~~

Nó không trao quyền bỏ qua `private` access checks. Muốn code bên ngoài dùng một giá trị, package owner cần thiết kế public API phù hợp hoặc quyết định một chính sách reflective openness có phạm vi.

## 18. Lab B — Sửa ưu tiên: dùng getter/public API

Thay file `modsrc/com.example.reader/com/example/reader/Main.java`:

~~~java
package com.example.reader;

import com.example.model.api.Customer;

public final class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("C-100");
        System.out.println(customer.id());
    }
}
~~~

Giữ nguyên cả hai `module-info.java`: model vẫn chỉ `exports` package API và **không cần `opens`**.

Biên dịch/chạy lại:

~~~bash
javac --release 17 \
  --module-source-path modsrc \
  -d mods \
  -m com.example.model,com.example.reader

java --module-path mods \
  --module com.example.reader/com.example.reader.Main
~~~

Output mong đợi:

~~~text
C-100
~~~

Không có `--add-opens` và cũng không cần bất kỳ deep-reflection permission mới nào.

### 18.1. Vì sao giải pháp này bền vững hơn?

Module sở hữu type định nghĩa chính xác dữ liệu nào được phép xuất ra. Consumer không phụ thuộc private field name, memory layout, setter, constructor internals hoặc annotation metadata không thuộc API contract.

Nếu cần thêm validation, access control hoặc che dữ liệu, module model có thể triển khai phía sau method mà không buộc các consumers sửa reflection rules.

## 19. Lab B — Trường hợp framework thực sự cần reflection

Không phải mọi use case có thể sửa thành getter call. JSON serializers, ORM frameworks, dependency injection, test frameworks hoặc một số component scanners có thể cần inspect/construct objects qua reflection theo hợp đồng của framework.

Nếu **module model do bạn kiểm soát** và **framework thật sự cần deep reflection**, có thể viết một module descriptor có mở package cho module được tin cậy:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.api to com.example.reader;
}
~~~

Nếu consumer vẫn là code reflection ban đầu ở Lab B, chạy lại với module descriptor mới có thể đi qua `setAccessible(true)` mà **không thêm JVM flag `--add-opens`**.

**Nhưng phải phân biệt:** Phương án này **không loại bỏ reflection**; nó thay một launcher override bằng một **permission được khai báo tại module owner** và giới hạn theo target module.

### 19.1. Qualified opens khác ALL-UNNAMED

`opens com.example.model.api to com.example.reader` chỉ mở package cho module được chỉ định. Nó không đồng nghĩa mở toàn bộ `java.base/java.lang` cho tất cả unnamed modules.

Tuy nhiên, `opens` có hiệu lực ở **cấp package**, không phải chỉ mở đúng field `id`. Vì vậy phải đánh giá dữ liệu nào trong package trở nên có thể truy cập qua deep reflection.

### 19.2. Đừng tự thêm tên module của framework

Một framework có thể dùng nhiều modules, chạy ở classpath/unnamed module hoặc có package/module names khác theo version. Hãy xem **tài liệu JPMS của framework thực sự đang dùng** trước khi thêm qualified `opens`.

Đặc biệt, cú pháp:

~~~text
opens com.example.model.api to ALL-UNNAMED;
~~~

**không phải cú pháp `module-info.java` hợp lệ** chỉ vì `ALL-UNNAMED` có ý nghĩa trong launcher flag. Với unnamed modules, phải chọn mô hình packaging/opens phù hợp theo policy, hoặc tránh deep reflection.

## 20. Tiêu chí chọn giữa public API và `opens`

| Tình huống | Phương án ưu tiên | Lý do |
| --- | --- | --- |
| Code nghiệp vụ muốn đọc dữ liệu object | Public method/DTO/API | Không cần deep access |
| Code muốn serialize dữ liệu public | Public serializer/record/API nếu framework hỗ trợ | Contract rõ |
| Framework thực sự cần private field binding | Qualified `opens` của module sở hữu package khi phù hợp | Phạm vi quyền có chủ đích |
| Framework đòi private JDK internals | Nâng framework hoặc thay công nghệ | Bạn không sở hữu JDK package |
| Unit test đọc private field chỉ để assert | Test qua behavior/public contract | Tránh coupling vào implementation |
| Cần atomic update private state của chính class | `Atomic*` hoặc `VarHandle` nội bộ | Giữ quyền ở nơi sở hữu state |
| Agent bên thứ ba mở package JDK để instrument | Tìm version/vendor-supported mode | Không đổi rộng JVM policy mù quáng |
| Plugin không có public extension point | Thiết kế SPI/adapter hợp lệ | Không dựa vào private implementation |

**Nguyên tắc ra quyết định:** ưu tiên **loại bỏ nhu cầu** deep reflection; nếu không thể, giới hạn và sở hữu rõ access policy. Không coi `opens` là một API design strategy thay thế cho public contracts trong mọi trường hợp.

## 21. `setAccessible` và `trySetAccessible`

Java reflection cung cấp:

~~~java
field.setAccessible(true);
~~~

và trên JDK hỗ trợ:

~~~java
boolean allowed = field.trySetAccessible();
~~~

`trySetAccessible()` có thể trả về `false` khi access không thể được bật, thay vì ném `InaccessibleObjectException` trong những tình huống tương ứng. Nhưng:

- Nó **không vượt qua module encapsulation**.
- Nó **không tự cung cấp dữ liệu** hay API thay thế.
- Một test chỉ thấy `false` không giải quyết business requirement.
- Những thất bại do security controls khác có thể có cách biểu hiện khác theo JDK.

Nó có thể hữu ích khi một tính năng tùy chọn được thiết kế hợp pháp để fallback, nhưng **không phải bản sửa migration** nếu code vẫn phụ thuộc private JDK state.

### 21.1. Có nên catch `InaccessibleObjectException`?

Bắt exception có chủ đích để hiển thị thông báo tương thích hoặc chọn một fallback **đúng semantic contract** có thể hợp lệ. Bắt rồi bỏ qua:

~~~java
try {
    field.setAccessible(true);
} catch (RuntimeException ignored) {
    // Tiếp tục với state không rõ.
}
~~~

là anti-pattern. Nó che nguyên nhân và có thể khiến logic sau đó hoạt động sai.

## 22. `MethodHandles` không phải cửa hậu mặc định

Java cung cấp `java.lang.invoke.MethodHandles` cho method/field access theo access control. Nhưng:

~~~java
MethodHandles.privateLookupIn(Target.class, lookup);
~~~

**không phải một cách vượt qua module boundaries**. Nó cần điều kiện access/opens phù hợp với caller và target module. Chuyển `setAccessible(true)` sang `privateLookupIn` mà không thay thiết kế có thể chỉ đổi exception.

### 22.1. Dùng public method qua MethodHandle khi cần động

Ví dụ một public Java API:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class PublicHandleDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle length = MethodHandles.publicLookup()
                .findVirtual(
                        String.class,
                        "length",
                        MethodType.methodType(int.class));

        int result = (int) length.invokeExact("Java");
        System.out.println(result);
    }
}
~~~

Output:

~~~text
4
~~~

Ví dụ cần dynamic invocation tới một **public** member đã được JDK hỗ trợ; không truy cập `String.value`, không cần `--add-opens`.

### 22.2. Khi nào dùng `VarHandle`?

`VarHandle` phù hợp khi chính mã sở hữu state cần truy cập kiểu biến hoặc thao tác atomic/memory-order theo API Java. Nó không phải giấy phép để sửa các private fields của JDK hoặc module khác.

Với bộ đếm thông thường, `AtomicInteger` thường đơn giản hơn:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class Counter {
    private final AtomicInteger count = new AtomicInteger();

    public int incrementAndGet() {
        return count.incrementAndGet();
    }

    public int value() {
        return count.get();
    }
}
~~~

Code này không cần reflect vào nội bộ `AtomicInteger` hay truy cập private field của class khác.

## 23. Khi nào lỗi không xuất hiện trên Java 8 mà xuất hiện ở Java 17?

Trước hệ thống modules, nhiều JDK classes có thể được gọi qua reflection và `setAccessible(true)` trong những điều kiện bảo mật nhất định. Từ Java 9, JPMS giới thiệu boundaries. Sau giai đoạn cho phép một số illegal reflective access nhằm hỗ trợ migration, JDK 17 mạnh hóa encapsulation của những nội bộ JDK theo JEP 403.

Điều đó không có nghĩa:

- Mọi reflection đều bị cấm.
- Reflection vào các public APIs hợp lệ bị cấm.
- Reflection vào code của chính bạn luôn thất bại.
- `--add-opens` là lựa chọn duy nhất.
- JDK 17 tự sinh ra các bug làm class `String` “bị hỏng”.

Thay vào đó, code cũ đang dựa vào **một quyền truy cập không được cam kết**, và sự thay đổi runtime làm lộ dependency ấy.

### 23.1. `--illegal-access=permit` không còn là lời giải

Một số hướng dẫn migration cũ khuyên:

~~~text
--illegal-access=permit
~~~

Từ JDK 17, tùy chọn này đã trở nên obsolete/không còn cho phép relaxed strong encapsulation như trước. Trạng thái chính xác ở những releases mới hơn cần kiểm tra theo launcher documentation, nhưng **đừng dùng nó như cách sửa** cho JDK 17/21.

### 23.2. Không rút ra kết luận từ một JVM duy nhất

Để tái hiện, ghi rõ Java feature release, full patch/build, vendor, module/classpath mode và JVM flags. Nếu library dùng native agents hoặc nhiều class loaders, chúng cũng có thể ảnh hưởng behavior.

## 24. Kiểm kê reflection trước khi refactor

Một ứng dụng lớn có thể có nhiều chỗ dùng deep reflection, từ code nội bộ đến third-party libraries.

Nguồn thường gặp:

- `Field.setAccessible(true)`, `Method.setAccessible(true)`, `Constructor.setAccessible(true)`.
- `AccessibleObject.trySetAccessible()`.
- `Class.getDeclaredFields()/getDeclaredMethods()`.
- `MethodHandles.privateLookupIn(...)`.
- Các hàm utility như `ReflectionUtils` của framework.
- ORM/serialization/deserialization với private fields.
- Dependency injection và test/mocking tools.
- Java agents hoặc bytecode instrumentation.
- Thư viện dùng `sun.*`, `com.sun.*` hoặc JDK internals.
- JVM startup flags đặt trong container/CI.

### 24.1. Quét source bằng ripgrep

Nếu dự án có `rg`:

~~~bash
rg -n -- \
  'setAccessible\(|trySetAccessible\(|getDeclaredField|privateLookupIn|--add-opens|--illegal-access|sun\.|com\.sun\.' \
  .
~~~

Kết quả chỉ là **candidate list**. Không phải mọi `getDeclaredField` đều sai; không phải mọi reflection có source text trực tiếp. Các thư viện nhúng hoặc bytecode sinh động có thể không xuất hiện trong search.

### 24.2. Windows PowerShell

Một ví dụ tìm trong những file text phổ biến:

~~~powershell
Get-ChildItem -Recurse -File -Include *.java,*.xml,*.gradle,*.properties,*.yaml,*.yml |
    Select-String -Pattern 'setAccessible\(', 'trySetAccessible\(', '--add-opens'
~~~

Đây là lệnh minh họa để kiểm kê nội bộ dự án được phép. Với repository lớn, nên giới hạn directories để tránh quét build outputs/dependency caches không cần thiết.

## 25. `jdeps --jdk-internals` có giúp phát hiện reflection không?

`jdeps` có thể tìm những **static references** tới JDK internal APIs:

~~~bash
jdeps --jdk-internals path/to/application.jar
~~~

Nếu JAR là multi-release JAR, dùng release view phù hợp:

~~~bash
jdeps --multi-release 17 \
  --jdk-internals path/to/application.jar
~~~

Tuy nhiên, code kiểu:

~~~java
Class.forName("java.lang.SomeInternalType");
~~~

hoặc:

~~~java
String name = "value";
String.class.getDeclaredField(name);
~~~

có thể không hiện đầy đủ trong phân tích static dependency. Vì vậy cần kết hợp:

1. Source search.
2. Dependency/agent inventory.
3. Runtime logs có stack trace gốc.
4. Test thực tế trên JDK mới **không có quyền mở package bổ sung**.

Không sử dụng một báo cáo `jdeps` trống như bằng chứng “không có illegal reflection”.

## 26. Truy nguồn thư viện bên thứ ba gây lỗi

Trong thực tế, stack trace có thể chỉ:

~~~text
java.lang.reflect.InaccessibleObjectException: ...
    at java.base/java.lang.reflect.AccessibleObject...
    at third.party.reflect.ReflectionHelper...
    at third.party.serializer.Serializer...
    at com.example.app.Main...
~~~

Khi đó, sửa `Main` chưa chắc đủ. Cần xác định:

- Library phát sinh lời gọi `setAccessible`.
- Version đang chạy thật, kể cả transitive dependencies.
- Artifact có bị shade vào một JAR khác không.
- Library vendor có bản hỗ trợ Java 17/21 không.
- Framework có mode dùng public getters, constructors, records hay explicit adapters không.
- Library có yêu cầu `opens` ở **package do ứng dụng sở hữu** thay vì mở JDK internals không.
- Có multiple agents/bytecode transformers tác động vào cùng class không.

### 26.1. Quy trình ưu tiên

1. **Upgrade thư viện** tới phiên bản được công bố hỗ trợ JDK mục tiêu.
2. Dùng public extension points/configuration chính thức.
3. Sửa DTO/model/serializer để không yêu cầu đọc private JDK internals.
4. Nếu vẫn cần reflection trong **module tự sở hữu**, cân nhắc qualified `opens`.
5. Chỉ tạm dùng flag có phạm vi rõ khi đang trong migration được phê duyệt; đặt ngày loại bỏ.

Không tự ý override ASM/Byte Buddy trong classpath ứng dụng khi agent đã shade các dependencies ấy; có thể không sửa được chính library đang thực thi.

## 27. Reflection, serialization và DTO: thiết kế API thay thế

Một serialization layer cũ có thể quét mọi fields rồi ghi giá trị trực tiếp. Với classes do bạn sở hữu, có nhiều lựa chọn:

- Public getters/constructors theo convention framework.
- Immutable DTOs với canonical constructors.
- Records trên Java release phù hợp.
- Explicit mapping functions.
- Custom serializers/deserializers dùng public API.
- Framework-supported annotations trên fields/methods được phép.
- Qualified `opens` nếu framework thật sự yêu cầu deep field binding trong named module.

### 27.1. Ví dụ mapping không cần private reflection

~~~java
public final class CustomerDto {
    private final String id;
    private final String displayName;

    public CustomerDto(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Một mapper gọi `getId()` và `getDisplayName()` có public API rõ. Tùy framework, cấu hình getter/constructor-based serialization thay cho private-field reflection có thể loại bỏ nhu cầu opens.

### 27.2. Thận trọng với semantic compatibility

Nếu trước đây serializer đọc mọi private fields (kể cả secrets, caches hoặc internal flags), chuyển sang public getters có thể thay đổi JSON/schema. Cần đối chiếu **golden fixtures**, versioned API contract và dữ liệu đã lưu. Loại bỏ `--add-opens` không được vô tình làm lộ dữ liệu hoặc thay đổi wire protocol.

## 28. Reflection trong unit tests: sửa test design thay vì mở JDK

Một unit test có thể dùng reflection để đọc private field chỉ nhằm kiểm tra implementation:

~~~java
Field field =
        SomeService.class.getDeclaredField("cache");
field.setAccessible(true);
Object cache = field.get(service);
~~~

Nếu private state là chi tiết implementation, cách tốt hơn thường là **kiểm tra observable behavior**:

- Cache hit làm giảm số lần gọi dependency.
- Validation đúng trên input biên.
- Service trả kết quả dự kiến khi state thay đổi theo public API.
- Tính atomicity/concurrency được kiểm bằng contract và synchronization test.

Nếu test cần injection hoặc observability để kiểm tra lớp phức tạp, cân nhắc constructor injection, test fixture/seam có phạm vi package/module hợp lý, hoặc test-specific interface được thiết kế rõ.

### 28.1. Mockito/Byte Buddy cũng phải tương thích JDK

Một số test tools dùng Java instrumentation và dynamic attach. Trên JDK 21 có bối cảnh cảnh báo dynamic agent loading từ JEP 451; điều đó **không đồng nghĩa** với `InaccessibleObjectException` do `String.value`.

Nếu lỗi từ mocking/bytecode parser, cần xem agent mode, library version, class-file support và vendor guidance. Đừng biến việc thêm `--add-opens` thành đáp án cho mọi lỗi test.

## 29. `--add-opens`, `--add-exports` và `--add-reads` khác nhau

| Flag | Vai trò | Không tự giải quyết |
| --- | --- | --- |
| `--add-opens=M/P=T` | Cho target `T` deep reflection vào package `P` của module `M` | Missing class/method, malformed bytecode |
| `--add-exports=M/P=T` | Cho target truy cập public types ở package không export | Deep reflection tới private members |
| `--add-reads=M=T` | Thêm module readability edge cho module `M` đọc module `T` | Không tự mở private fields |
| `--enable-native-access=...` | Cơ chế kiểm soát native access ở JDK phù hợp | Không mở Java packages cho deep reflection |

Ví dụ:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
--add-exports=java.base/jdk.internal.misc=ALL-UNNAMED
~~~

Hai lệnh có phạm vi quyền khác nhau và đều có rủi ro khi mở JDK internals cho code không được thiết kế để phụ thuộc vào chúng. **Không khuyến nghị thêm các dòng này vào production** nếu không có lý do cụ thể và phê duyệt.

### 29.1. Dùng flags đúng cú pháp nhưng không đúng mục tiêu

Nếu stack trace báo:

~~~text
java.lang.NoSuchMethodError: ...
~~~

thì một `--add-opens` không thể tạo lại method đã mất. Nếu `VerifyError` báo stack map frames không hợp lệ, một `--add-exports` cũng không sửa bytecode. Chỉ chọn flag khi **lỗi thực sự là module access** và có lộ trình loại bỏ.

## 30. Tìm flags ẩn trong quá trình launch

Một ứng dụng có thể “không cần `--add-opens` ở local” nhưng thực ra JVM đang nhận nó từ nơi khác.

Những nơi phải kiểm tra:

| Nơi cấu hình | Ví dụ nguồn flags |
| --- | --- |
| Java launcher | Command-line options |
| Environment | `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` |
| Gradle | `org.gradle.jvmargs`, `Test.jvmArgs`, run task |
| Maven | Surefire/Failsafe `argLine`, `.mvn/jvm.config` |
| IDE | Run/Debug configuration, test runner |
| Docker | Entrypoint, command, environment |
| Kubernetes | Pod spec, Helm chart, mutating admission/injection |
| App server | Server-specific JVM options |
| Platform agent | JVM args injected by observability/security |

### 30.1. Vấn đề khi so local với CI

~~~text
Developer JVM: --add-opens present via IDE
CI JVM:        --add-opens present via Test.jvmArgs
Production:    no --add-opens
~~~

Local và CI đều xanh nhưng production vẫn gặp `InaccessibleObjectException`. Vì vậy migration test phải có **ít nhất một đường chạy không có những flags mở package cũ**, trên artifact/runtime tương đương production.

## 31. Ví dụ loại bỏ flags khỏi Gradle tests

Giả sử cấu hình cũ:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs '--add-opens=java.base/java.lang=ALL-UNNAMED'
}
~~~

Sau khi sửa code/framework:

~~~groovy
tasks.withType(Test).configureEach {
    // Không thêm quyền truy cập private JDK internals.
    // Các JVM options khác chỉ được giữ nếu có lý do riêng.
}
~~~

Đây là ví dụ minh họa sự khác nhau, không phải cấu hình Gradle hoàn chỉnh. Khi thay đổi, cần kiểm tra `org.gradle.jvmargs`, test forks, IDE runner và các plugin khác có đang bổ sung cờ không.

### 31.1. Gradle daemon và test JVM là hai tiến trình có thể khác nhau

Một flag trong `org.gradle.jvmargs` có thể ảnh hưởng Gradle daemon; một flag trong `Test.jvmArgs` ảnh hưởng JVM test fork. Đừng xóa từ một chỗ rồi kết luận mọi process không còn cờ.

### 31.2. Hướng dẫn kỹ thuật là kiểm chứng, không chỉ sửa văn bản

Sau khi xóa cờ, chạy suite trên JDK mục tiêu và kiểm tra lỗi reflection. Nếu CI vẫn xanh vì một plugin tự inject cờ, report cần chỉ ra chính xác nguồn injection trước khi gọi migration hoàn tất.

## 32. Ví dụ loại bỏ flags khỏi Maven tests

Một cấu hình cũ có thể dùng:

~~~xml
<configuration>
  <argLine>--add-opens=java.base/java.lang=ALL-UNNAMED</argLine>
</configuration>
~~~

Sau khi code/framework không còn cần access này, bỏ option khỏi `argLine` nhưng **giữ nguyên những options test cần thiết khác** như coverage agent, memory settings hoặc JVM properties có chủ đích.

### 32.1. Cẩn trọng khi có JaCoCo

JaCoCo hoặc plugin khác có thể đặt/ghép giá trị `argLine`. Nếu thay toàn bộ property mà không hiểu lifecycle, có thể làm mất coverage. Hãy sửa cấu hình theo đúng phiên bản Maven Surefire/Failsafe/JaCoCo hiện dùng.

### 32.2. Maven runtime không nhất thiết là test runtime

`mvn -version` ghi JVM chạy Maven, nhưng Surefire có thể fork một JDK khác theo toolchain. Thu thập fingerprint ngay **bên trong test JVM** để chứng minh kết quả trên đúng release/vendor.

## 33. Loại bỏ flags trong container và Kubernetes

Một JVM chạy trong container có thể nhận flags từ:

~~~text
Dockerfile ENTRYPOINT
startup.sh
JAVA_TOOL_OPTIONS
JDK_JAVA_OPTIONS
Kubernetes container args
Helm values
platform-injected javaagent startup config
~~~

Sau khi refactor reflection:

1. Xác định nơi khai báo flag authoritative.
2. Xóa đúng option không còn cần.
3. Dựng immutable runtime image/deployment manifest mới.
4. Kiểm tra full JVM command line và environment đã redact.
5. Chạy smoke/integration trên image cuối.
6. So logs/metrics/traces trước và sau.
7. Canary, sau đó mới tăng rollout.

### 33.1. Đừng chỉ sửa shell script trong repository

Nếu platform tự bổ sung `--add-opens` qua một agent injector, script đã sửa chưa chứng minh process production không còn nhận cờ. Phải xác nhận **effective runtime arguments** từ deployment thật hoặc một replica staging tương đương.

## 34. Kiểm thử hồi quy: cùng hành vi, không còn quyền mở nội bộ

Định nghĩa **hai nhóm tests**:

**Nhóm 1 — Contract tests**

- String processing/encoding đúng với Unicode.
- Serializer/mapper output không đổi ngoài thay đổi được phê duyệt.
- Object construction, validation và error handling đúng.
- Reflection framework vẫn hoạt động ở module/package được khai báo hợp lệ.
- Các workflows quan trọng không lỗi khi classes được nạp muộn.

**Nhóm 2 — Runtime configuration tests**

- JDK target full build đã được xác định.
- Test JVM không có các `--add-opens` workaround cũ.
- Classpath/module path tương đương deployment.
- Không có warning/error illegal reflective access từ dependencies được hỗ trợ.
- Agent/native libraries không âm thầm yêu cầu cờ rộng khác.
- Không có functional/performance regression do thay serializer/framework.

### 34.1. Một test chỉ kiểm tra exit code là chưa đủ

`PublicStringProbe` in `PASS` là smoke test nhỏ. Ứng dụng thật cần test tất cả call paths có khả năng đụng reflection: startup, first request, batch scheduling, serializer edge cases, proxy initialization và long-running workload.

### 34.2. Test âm tính phải chứng minh thiếu cờ

Để tránh “pass nhầm”, có thể tạo CI job khởi chạy một **process mới** với danh sách JVM args đã kiểm soát, dùng policy cấm `--add-opens` cho target JDK packages được yêu cầu loại bỏ. Không chỉ xóa flag khỏi script rồi giữ biến môi trường `JAVA_TOOL_OPTIONS` đang inject nó.

## 35. Ma trận thực hành theo JDK và loading mode

| Case | Runtime | Loading mode | Cờ mở JDK package | Kỳ vọng |
| --- | --- | --- | --- | --- |
| A1 | JDK 17 | Classpath | Không | Legacy probe nhận `InaccessibleObjectException` |
| A2 | JDK 17 | Classpath | Tạm có, đối chứng | Probe có thể đi qua `setAccessible` |
| A3 | JDK 17 | Classpath | Không | Public probe PASS |
| A4 | JDK 21 | Classpath | Không | Public probe PASS |
| B1 | JDK 17/21 | Named modules | Không | Lab B legacy consumer lỗi |
| B2 | JDK 17/21 | Named modules | Không | Consumer public `id()` PASS |
| B3 | JDK 17/21 | Named modules với qualified `opens` | Không | Deep reflection vào package tự sở hữu được phép |
| P1 | JDK target | Production-like app image | Không có workaround cũ | Contract/integration/observability PASS |

Với các JDK vendors khác, kết quả chi tiết của Lab A có thể thay đổi do `String` implementation; **contract test của bản sửa dùng public API** là mục tiêu bền vững cần giữ.

### 35.1. Khi nào test Java 8?

Nếu sản phẩm còn hỗ trợ Java 8, phải thiết kế matrix riêng và compile sources với mức tương thích tương ứng. Lab JPMS không chạy trên Java 8 vì không có module system như Java 9+. Không coi việc Lab A cũ có thể truy cập private field trên Java 8 là lý do hợp lệ để giữ code đó trên JDK 17+.

## 36. Bẫy khi cố sửa lỗi bằng `open module`

Thay:

~~~java
module com.example.model {
    exports com.example.model.api;
}
~~~

thành:

~~~java
open module com.example.model {
    exports com.example.model.api;
}
~~~

có thể khiến nhiều reflective access trở nên khả dụng. Nhưng đây là **quyết định mở toàn bộ packages trong module cho deep reflection**, rộng hơn nhiều so với qualified `opens`.

Nếu chỉ một serializer module cần đọc một DTO package, ưu tiên phương án cụ thể hơn. Nếu DTO có public API phù hợp, hãy tránh opens luôn.

**Không sử dụng `open module` chỉ để im lặng một stack trace** mà chưa đánh giá những private members khác trong module.

## 37. Lưu ý khi chuyển từ classpath sang module path

Một library vốn chạy trên classpath có thể dùng deep reflection vào class ứng dụng mà không gặp rào cản JPMS cùng kiểu với named modules. Khi chuyển sang module path với explicit `module-info.java`, access checks sẽ khác.

Các tình huống:

- Consumer và target đều là unnamed modules.
- Target ở named module, consumer ở unnamed module.
- Cả hai đều là named modules.
- Target là JDK module, consumer là app/framework module.
- Application dùng custom class loader, agent hoặc nested JAR launcher.

Một lỗi chỉ xuất hiện trên module path không nhất thiết do JDK update; nó có thể đến từ thay đổi **packaging mode**. Cần ghi chính xác command line, module graph và class source.

### 37.1. `module-info.java` là hợp đồng runtime

Thêm exports/opens phải review như thay đổi access boundary, không chỉ là “thêm dependency để compiler im lỗi”. Nếu module là thư viện công khai, thay đổi descriptor ảnh hưởng consumers và framework behavior.

## 38. Những lỗi dễ nhầm với `InaccessibleObjectException`

| Lỗi | Đặc điểm | Hướng xử lý đầu tiên |
| --- | --- | --- |
| `InaccessibleObjectException` | Deep reflection bị module access checks từ chối | Public API hoặc scoped opens nếu sở hữu package |
| `IllegalAccessException` | Reflection caller không được quyền truy cập theo API/checks | Kiểm tra public/member access và module contract |
| `IllegalAccessError` | Bytecode linkage access violation | ABI/module exports và runtime class versions |
| `NoSuchFieldException` | Field không tồn tại với tên được tra cứu | Bỏ phụ thuộc private layout, xem source |
| `NoSuchMethodError` | Runtime method descriptor không khớp | Dependency graph/binary compatibility |
| `NoClassDefFoundError` | Class không thể định nghĩa hoặc initialization đã thất bại | Lỗi đầu tiên, classpath/module path |
| `VerifyError` | JVM verifier từ chối bytecode | Transformer/generator/frames |
| `UnsupportedClassVersionError` | JVM không hỗ trợ class-file major | Compiler `--release` và runtime |
| `UnsatisfiedLinkError` | JNI/native library or symbol binding | OS/ABI/native dependency |

Nếu exception xuất hiện trong framework stack, đọc **nguyên nhân đầu tiên** và class/module đúng trước khi sửa. Một library có thể gặp `NoClassDefFoundError` sau khi static initializer từng ném `InaccessibleObjectException` hoặc một error khác; cần giữ log khởi tạo đầu tiên.

## 39. Triaging theo stack trace thực tế

Một quy trình phân tích:

1. **Chọn lỗi đầu tiên** cùng các `Caused by`; không chỉ exception cuối của startup.
2. **Xác định member** bị truy cập: field, method hay constructor; thuộc class/package nào.
3. **Xác định caller** trong stack trace: code ứng dụng, framework, test tool hay Java agent.
4. **Xác định module owner và target** từ thông điệp.
5. **Kiểm tra nguồn flags** effective JVM options (CLI, IDE, CI, env, container).
6. **Tái hiện tối thiểu** bằng một class/test không cần application state thật.
7. **Đối chứng** với `--add-opens` chỉ trong môi trường test được phép.
8. **Tìm public APIs hoặc vendor-supported library upgrade**.
9. **Sửa code hoặc module descriptor có phạm vi**, rồi xóa flag workaround.
10. **Chạy lại regression tests** trên final runtime image và kiểm tra observability.

### 39.1. Không “đổi một flag rồi thử may” hàng loạt

Nếu error nói:

~~~text
module java.base does not "opens java.util" to module xyz
~~~

thì thêm:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

không nhất thiết tác động tới lỗi ấy vì **package và target đều khác**. Nhưng giải pháp đúng vẫn không phải tự động mở cả hai packages; cần xác định lý do library truy cập internals.

## 40. Mẫu quyết định kỹ thuật (ADR) cho việc loại bỏ flag

~~~markdown
# ADR: Remove illegal deep reflection in Java migration

## Context
- JDK target/build:
- Component and version:
- Exact first exception:
- Member/module/package being accessed:
- Current --add-opens workaround:

## Root cause
- Why legacy code needed reflective access:
- Runtime behavior required by business contract:

## Options
- Public Java API / redesign:
- Supported framework/library upgrade:
- Qualified opens for owned named module:
- Transitional launcher flag with expiry:

## Decision
- Chosen replacement and reason:
- Access boundary after migration:
- Behavior/data/API compatibility requirements:

## Validation
- Negative test without --add-opens:
- Contract/integration tests and JDK matrix:
- Runtime image/agent verification:

## Rollout and ownership
- Owner:
- Release:
- Rollback constraints:
- Removal date for transitional flags:
~~~

Mẫu này hữu ích khi một flag được nhiều teams copy sang nhiều services. Có ADR và owner giúp ngăn cờ quay lại mà không có lý do.

## 41. Anti-patterns cần tránh

**“Mở `java.base/java.lang` cho mọi unnamed module là vô hại.”** Sai: mở quyền deep reflection vào package lõi của JDK cho mọi code nằm trong phạm vi target; giảm encapsulation và không đảm bảo tương thích tương lai.

**“Đổi `setAccessible` thành `privateLookupIn` sẽ vượt JPMS.”** Sai: MethodHandles cũng chịu module access restrictions.

**“Dùng `trySetAccessible` trả false là đã sửa xong.”** Sai nếu business path vẫn cần dữ liệu đó và không có fallback đúng.

**“`exports` là đủ để truy cập private fields.”** Sai: `exports` điều khiển truy cập tới public members, không tự cấp deep reflection.

**“`opens ... to ALL-UNNAMED` có thể viết vào `module-info.java`.”** Không phải cú pháp hợp lệ của module descriptor.

**“Thêm `open module` cho nhanh.”** Có thể mở rộng bề mặt quyền quá mức.

**“Một class không có module-info nghĩa là không chịu JPMS.”** Không đúng: code trên classpath vẫn ở unnamed module; các JDK named modules vẫn enforce openness của mình.

**“Một test pass khi có `--add-opens` chứng minh code tương thích JDK mới.”** Không đủ; code vẫn phụ thuộc JDK internals.

**“Reflection vào `String.value` nhanh hơn API public nên đáng giữ.”** Không thể kết luận không benchmark/semantic checks, và rủi ro correctness/compatibility cao.

**“JDK 17 cấm mọi reflection.”** Sai: public reflection được phép theo access rules, và chính module owner có thể mở package khi hợp lý.

**“Xóa cờ trong Gradle là xong.”** Không nếu Maven/IDE/container/`JAVA_TOOL_OPTIONS` còn inject.

**“Mọi `IllegalAccessError` là do thiếu `--add-opens`.”** Không đúng; linkage access và deep reflection là hai loại kiểm tra khác nhau.

**“Có thể tắt agent/coverage để hết lỗi mà không ảnh hưởng release quality.”** Không nếu chúng là gate bắt buộc; phải nâng hoặc cấu hình đúng công cụ.

**“Dùng public getter luôn giữ JSON giống trước.”** Không chắc; phải test serialization/schema contract.

**“Đổi thành qualified opens nghĩa là không còn reflection.”** Không đúng: chỉ thay nơi khai báo permission.

## 42. Checklist hoàn thành bài thực hành

- [ ] Xác định JDK vendor/full version/build đang dùng.
- [ ] Chạy `LegacyStringProbe` không flag và ghi nhận lỗi phù hợp.
- [ ] Đọc được module owner, package và caller từ exception.
- [ ] Dùng `--add-opens` chỉ làm phép đối chứng trong môi trường test.
- [ ] Giải thích vì sao `String.value` không phải public API ổn định.
- [ ] Tạo/chạy `PublicStringProbe` với UTF-16, code points và UTF-8 semantics đúng.
- [ ] Xác nhận public probe PASS không cần `--add-opens`.
- [ ] Tạo hai named modules và tái hiện lỗi deep reflection giữa modules.
- [ ] Sửa consumer dùng `Customer.id()` và chạy thành công không có flag.
- [ ] Phân biệt rõ `exports` và `opens`.
- [ ] Hiểu qualified `opens` chỉ dành cho những reflective consumers thực sự cần.
- [ ] Không nhầm `opens` với loại bỏ reflection.
- [ ] Kiểm kê các nguồn `setAccessible` và `--add-opens` trong code/build/CI/container.
- [ ] Kiểm tra third-party framework/agent versions được hỗ trợ trên JDK đích.
- [ ] Không dùng `--illegal-access=permit` như lời giải dài hạn cho JDK 17/21.
- [ ] Không mở JDK internals diện rộng hoặc tắt security controls không có phê duyệt.
- [ ] Có contract/integration tests trên JVM không có các workaround cũ.
- [ ] Đã kiểm tra semantics, serialization và data compatibility sau refactor.
- [ ] Đã xác nhận final runtime image và effective JVM args.
- [ ] Có owner, ADR/release notes, rollback policy và mốc gỡ nếu còn flag tạm.

## 43. Câu hỏi tự kiểm tra

**1. Tại sao `getDeclaredField("value")` có thể thành công nhưng `setAccessible(true)` thất bại?**

Vì truy vấn metadata về một field không tự có nghĩa caller được quyền deep reflection để bỏ qua access checks. JPMS có thể từ chối việc mở quyền vào package JDK.

**2. `--add-opens=java.base/java.lang=ALL-UNNAMED` có làm `String.value` trở thành API được bảo đảm không?**

Không. Nó chỉ mở quyền reflection trong phạm vi mục tiêu; tên/kiểu/layout private field vẫn không có compatibility contract.

**3. Nếu module export package, có thể reflect vào field private của một class public không?**

Không mặc định. Cần openness hợp lệ cho deep reflection, hoặc tốt hơn là public API phù hợp.

**4. Chuyển từ flag sang `opens package to module` có phải đã loại bỏ reflection không?**

Không. Nó loại bỏ nhu cầu launcher override trong một kiến trúc module phù hợp, nhưng vẫn dùng deep reflection với permission được khai báo.

**5. `MethodHandles.privateLookupIn` có vượt qua module boundary không?**

Không. Nó yêu cầu quyền truy cập hợp lệ, bao gồm opens giữa modules khi điều kiện API đòi hỏi.

**6. Vì sao CI test xanh chưa chứng minh production không cần flag?**

Vì flags có thể được inject bởi IDE/test runner/build plugin/environment/container platform. Cần xác nhận effective JVM arguments và test artifact giống production.

**7. Khi nào sửa code nghiệp vụ, khi nào nâng thư viện?**

Nếu reflection do code mình viết, ưu tiên public API/redesign. Nếu phát sinh trong dependency, xác định version, tìm bản vendor-supported hoặc cấu hình chính thức; không can thiệp private JDK fields từ bên ngoài.

**8. Tại sao sau khi bỏ reflection phải kiểm thử Unicode/serialization?**

Vì API công khai có semantic contract khác với private layout. Một sửa chữa “không còn exception” vẫn có thể đổi encoding, data shape hoặc business behavior.

## 44. Gợi ý mở rộng bài thực hành

Khi đã hoàn tất hai lab:

1. Thử một code path dùng `Field.trySetAccessible()` và ghi chính xác false/exception khi không đủ quyền; thực hiện trong test thay vì production.
2. Viết unit test khẳng định public API behavior khi input chứa emoji và combining marks.
3. Tạo thêm một package `com.example.model.internal` và thử export/open riêng; kiểm tra việc mở package không làm biến thành business API.
4. Đóng gói named modules vào modular JARs, chạy lại dưới `--module-path`.
5. Thử cùng app trên classpath và module path để thấy khác biệt về openness của các class do bạn sở hữu.
6. Mô phỏng một framework cần reflection vào DTO; xác định **module name thật** của framework thay vì đoán một giá trị.
7. Gỡ tất cả các instance của một `--add-opens` workaround khỏi test/CI/deployment và dùng automated guard cho những chỗ không được phép tái xuất hiện.
8. Kiểm tra release notes của dependency dùng reflection để biết phiên bản đầu tiên chính thức hỗ trợ JDK mục tiêu.

**Không mở package nội bộ JDK hàng loạt chỉ để tăng số bài test pass.** Mục tiêu mở rộng là hiểu và giảm coupling.

## 45. Tài liệu tham khảo theo đúng JDK release

Các nguồn nên đối chiếu khi áp dụng vào dự án:

- **OpenJDK JEP 261 — Module System:** module graph, `exports`, `opens` và các launcher options.
  https://openjdk.org/jeps/261
- **OpenJDK JEP 403 — Strongly Encapsulate JDK Internals:** lý do thay đổi behavior của illegal reflective access từ JDK 17.
  https://openjdk.org/jeps/403
- **Java SE API — `AccessibleObject`:** `setAccessible`, `trySetAccessible` và điều kiện access/module checks.
  https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- **Java SE API — `InaccessibleObjectException`:** loại lỗi khi reflective access không thể được bật.
  https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html
- **Java Language Specification / JPMS:** `module-info.java`, qualified `opens`/`exports`, module access control.
- **`java` Launcher documentation:** cú pháp `--add-opens`, `--add-exports`, module path và runtime options.
- **Java SE API — `MethodHandles` và `VarHandle`:** method/field access theo cơ chế được hỗ trợ.
- **`jdeps` Tool Guide:** `--jdk-internals` và phân tích dependencies.
- **Gradle/Maven test plugin documentation:** nguồn JVM arguments và cách xác nhận test JVM.
- **Framework/agent vendor support matrices:** cách cấu hình reflective serialization, proxy/bytecode instrumentation trên JDK mục tiêu.

Tài liệu module/launcher có thể thay đổi theo release. Không suy ra trạng thái flags trên một JDK mới chỉ từ behavior JDK 17; hãy xác minh đúng runtime mà sản phẩm phát hành.

## 46. Kết luận

Lỗi `InaccessibleObjectException` trong Java Advance Compatibility Migration thường chỉ ra code đang yêu cầu **deep reflection vượt phạm vi module access cho phép**. Trong Lab A, truy cập `String.value` thất bại vì `java.base` không mở `java.lang` cho caller; bật `--add-opens` cho thấy nguyên nhân nhưng không biến private JDK internals thành một API ổn định. Giải pháp bền vững là chuyển sang `String.length()`, `codePointCount()`, `getBytes(StandardCharsets.UTF_8)` hoặc public API đúng với nhu cầu.

Trong Lab B, consumer cố reflect vào `Customer.id` giữa hai named modules. Cách sửa ưu tiên là gọi **public method `Customer.id()`**, giữ module descriptor chỉ export contract cần thiết. Khi một framework thực sự cần deep reflection vào package do bạn sở hữu, qualified `opens` có thể thay thế launcher override rộng, nhưng đó là một **permission có phạm vi**, không phải việc loại bỏ reflection.

Hoàn thành migration nghĩa là **xóa dependency vào private internals, xóa các `--add-opens` workarounds không còn cần, xác minh effective JVM arguments trên môi trường thật và chạy regression tests giữ nguyên semantics**. Khi đó ứng dụng không chỉ “qua được một exception”, mà còn bền vững hơn trước JDK updates, module boundaries và yêu cầu bảo mật của hệ thống.
