# Giới hạn của `--illegal-access` trên các thế hệ JDK

Khi nâng cấp Java từ JDK 8 sang các phiên bản có Java Platform Module System (JPMS), một ứng dụng đang chạy ổn có thể đột ngột gặp lỗi reflection khi truy cập class, constructor, method hoặc field nội bộ của JDK. Để hỗ trợ quá trình chuyển đổi từ classpath truyền thống, JDK 9 giới thiệu tùy chọn `--illegal-access` nhằm tạm thời nới lỏng một phần kiểm soát truy cập. Tuy nhiên, cơ chế này **chỉ mang tính chuyển tiếp**: hành vi mặc định thay đổi từ JDK 16 và từ **JDK 17, `--illegal-access` không còn tác dụng mở các package nội bộ**.

Đây là một thay đổi quan trọng trong Java Advance Compatibility Migration. Một script triển khai từng khắc phục lỗi bằng `--illegal-access=permit` trên JDK 11 không thể tiếp tục dựa vào cùng câu lệnh trên JDK 17. Đồng thời, tùy chọn này chưa từng là giải pháp tổng quát để truy cập mọi API nội bộ của JDK.

Bài học giải thích phạm vi của từng chế độ, sự thay đổi qua các thế hệ JDK, khác biệt giữa `--illegal-access` và các tùy chọn mở/export package có mục tiêu, cách chẩn đoán lỗi và chiến lược migration không phụ thuộc vào cơ chế tạm thời.

## 1. Bối cảnh: reflection trước và sau JPMS

### 1.1. Java 8 và các phiên bản trước

Trong mô hình classpath truyền thống, một số framework sử dụng reflection để truy cập sâu vào implementation của JDK hoặc thư viện. Ví dụ, chúng có thể gọi `setAccessible(true)` để vượt qua giới hạn truy cập ngôn ngữ Java đối với thành viên không public.

```java
import java.lang.reflect.Field;

public class InspectString {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true);
        System.out.println(field.getType());
    }
}
```

Đây chỉ là **ví dụ về kiểu truy cập cần được khảo sát**, không phải cách truy cập cấu trúc nội bộ `String` nên sử dụng trong ứng dụng thực tế. Implementation của `String` có thể thay đổi giữa các release; riêng việc dùng một field tên `value` đã là một dependency không ổn định.

Java 8 không có JPMS và không hỗ trợ `--illegal-access`. Một số truy cập reflection trong code classpath cũ có thể hoạt động, nhưng điều đó không tạo thành cam kết rằng các field hoặc method nội bộ sẽ tồn tại và có thể truy cập trên Java mới.

### 1.2. JPMS từ JDK 9

JPMS bổ sung khái niệm **named module**, **unnamed module**, quan hệ `reads`, `exports` và `opens`:

- `exports` cho phép code ở module khác truy cập các public type trong package được export, theo quy tắc của JPMS.
- `opens` cho phép deep reflection tới package theo phạm vi được chỉ định.
- Package không được export/open có thể bị encapsulate ngay cả khi class hoặc member tồn tại trong runtime image.
- Code nạp từ classpath thuộc unnamed module và chịu các quy tắc module tương ứng.
- Code trên module path có thể thuộc explicit named module hoặc automatic named module.

Khi các ứng dụng classpath cũ được đưa lên JDK 9, một lượng lớn thư viện vẫn phụ thuộc vào khả năng reflection trước JPMS. Vì vậy, JDK cung cấp `--illegal-access` như một cầu nối để migration, chứ không phải một API bảo đảm dài hạn.

### 1.3. Strong encapsulation bảo vệ điều gì?

Strong encapsulation giới hạn việc truy cập implementation detail của các module. Ví dụ, package `java.base/java.lang` không mặc nhiên được mở cho code trên classpath chỉ vì `java.lang.String` là public class.

Khi một framework cố gọi `setAccessible(true)` vào một private field thuộc package không mở, JDK hiện đại có thể ném:

```text
java.lang.reflect.InaccessibleObjectException:
  Unable to make field ... accessible:
  module java.base does not "opens java.lang" to unnamed module ...
```

Thông báo cho biết module sở hữu package, package bị chặn và module đang thực hiện truy cập. Đây là dữ kiện chính xác hơn việc suy đoán rằng “Java 17 không hỗ trợ reflection”.

**Reflection vẫn được hỗ trợ trong Java hiện đại.** Vấn đề là code đang yêu cầu truy cập sâu vào phần không được mở theo hợp đồng module.

## 2. Dòng thời gian của `--illegal-access`

Không thể hiểu `--illegal-access` nếu bỏ qua phiên bản JDK. Cùng một tham số khởi chạy có thể mang ý nghĩa khác nhau hoặc không còn hiệu lực.

| Thế hệ JDK | Trạng thái `--illegal-access` | Hành vi và hệ quả chính |
|---|---|---|
| JDK 8 trở về trước | Không có tùy chọn này | Chưa có JPMS; không thể dùng flag để xử lý sự cố |
| JDK 9–15 | Có hiệu lực; chế độ mặc định là `permit` | Tạm thời nới lỏng một số package nội bộ tồn tại ở JDK 8 cho code trong unnamed modules; cảnh báo truy cập trái phép |
| JDK 16 | Strong encapsulation trở thành mặc định theo JEP 396 | Có thể sử dụng chế độ `permit`/`warn`/`debug` để tái bật cơ chế nới lỏng tương ứng, nhưng không nên dựa vào dài hạn |
| JDK 17 | `--illegal-access` bị vô hiệu hóa theo JEP 403 | Flag không mở lại package; có thể phát cảnh báo rằng tùy chọn bị bỏ qua |
| JDK sau 17 | Không nên coi flag là cách mở package | Dựa trên API công khai và các lựa chọn `--add-opens`/`--add-exports` có mục tiêu khi thực sự cần; kiểm tra tài liệu JDK đang triển khai |

Hai mốc cần nhớ:

1. **JDK 16: mặc định chuyển sang strong encapsulation.** Việc chuyển từ JDK 11 lên 16 có thể làm lộ lỗi reflection mà JDK 11 từng cho phép.
2. **JDK 17: không thể dùng `--illegal-access=permit` để quay lại hành vi nới lỏng trước đây.** Việc chuyển từ JDK 11 hoặc 16 lên 17 đòi hỏi sửa dependency, code hoặc mở đúng package bằng cơ chế có mục tiêu.

Cơ sở thay đổi này gồm JEP 261 (JPMS), JEP 396 (Strongly Encapsulate JDK Internals by Default) và JEP 403 (Strongly Encapsulate JDK Internals). Đây là các mốc của nền tảng Java, không phải thay đổi riêng của Spring, Maven hay Gradle.

## 3. Các chế độ của `--illegal-access` trên JDK còn hỗ trợ

Trong các release mà tùy chọn còn hiệu lực, cú pháp thường gặp là:

```bash
java --illegal-access=permit -jar app.jar
java --illegal-access=warn   -jar app.jar
java --illegal-access=debug  -jar app.jar
java --illegal-access=deny   -jar app.jar
```

Các chế độ được mô tả dưới đây là **hành vi lịch sử của cơ chế chuyển tiếp**, không phải hướng dẫn bật lại nó trên JDK 17.

### 3.1. `permit` — nới lỏng kèm cảnh báo ban đầu

Chế độ `permit` cho phép một số hoạt động illegal reflective access đối với package JDK thuộc nhóm được hỗ trợ chuyển tiếp. Đây là mặc định trong JDK 9–15.

Khi phát hiện một truy cập trái phép đầu tiên, runtime có thể in cảnh báo dạng:

```text
WARNING: An illegal reflective access operation has occurred
WARNING: Illegal reflective access by ...
WARNING: Please consider reporting this to the maintainers ...
WARNING: All illegal access operations will be denied in a future release
```

Cảnh báo cho biết ứng dụng hoặc thư viện đang phụ thuộc vào khả năng truy cập sắp bị siết chặt. **Không có lỗi ngay lập tức không đồng nghĩa code tương thích với JDK tương lai.**

### 3.2. `warn` — cảnh báo cho từng truy cập được phát hiện

```bash
java --illegal-access=warn -jar app.jar
```

Trong các JDK hỗ trợ, `warn` vẫn duy trì phạm vi nới lỏng tương ứng nhưng tạo cảnh báo chi tiết hơn cho các thao tác illegal reflective access.

Chế độ này hữu ích khi chuẩn bị migration từ JDK 11: nó cho thấy những code path còn dùng reflection vào JDK internals, thay vì chỉ thấy cảnh báo đầu tiên.

Tuy nhiên, nếu một luồng chỉ chạy theo lịch hoặc khi xảy ra lỗi, nó vẫn có thể chưa xuất hiện trong log. Cần kết hợp với kiểm thử và phân tích dependency.

### 3.3. `debug` — cảnh báo kèm thông tin truy vết

```bash
java --illegal-access=debug -jar app.jar
```

Chế độ `debug` cung cấp thông tin như stack trace để truy ra code nào thực hiện truy cập. Nó đặc biệt hữu ích khi lỗi phát sinh từ một thư viện transitively loaded mà ứng dụng không gọi trực tiếp.

Ví dụ khi phân tích output, cần tìm:

- Tên JAR và class gọi reflection.
- Method/framework thực hiện `setAccessible` hoặc API tương đương.
- Package và module JDK bị truy cập.
- Phiên bản thư viện gây ra truy cập.
- Đường chạy nào kích hoạt hành vi.

Không nên bật logging dạng debug này ở production thường xuyên nếu nó gây lượng log lớn hoặc để lộ chi tiết triển khai không cần thiết.

### 3.4. `deny` — từ chối nới lỏng truy cập

```bash
java --illegal-access=deny -jar app.jar
```

Trong các JDK 9–16 hỗ trợ, `deny` yêu cầu runtime không mở các package theo cơ chế nới lỏng mặc định. Đây từng là một cách hữu ích để **kiểm thử sớm mức độ phụ thuộc vào illegal reflective access** trước khi lên JDK 17.

Ví dụ, một ứng dụng JDK 11 chỉ chạy được với `permit` nhưng thất bại với `deny` là dấu hiệu rõ ràng rằng có dependency cần sửa trước migration.

Không nên hiểu `deny` là chặn mọi reflection: các API public và package đã được mở hợp lệ vẫn có thể được dùng theo quy tắc Java/JPMS.

### 3.5. Điểm khác nhau của bốn chế độ

| Chế độ | Nới lỏng phạm vi tương ứng? | Mục đích trong JDK 9–16 |
|---|---|---|
| `permit` | Có | Chuyển tiếp cho ứng dụng cũ, ghi cảnh báo ban đầu |
| `warn` | Có | Tìm nhiều điểm truy cập trái phép qua cảnh báo |
| `debug` | Có | Truy nguồn truy cập qua thông tin truy vết |
| `deny` | Không | Phát hiện sớm dependency vào cơ chế nới lỏng |

Từ JDK 17, bảng này chỉ có ý nghĩa để **hiểu lịch sử vận hành hoặc đọc cấu hình cũ**. Không thể dựa vào `permit`, `warn` hoặc `debug` để khôi phục nới lỏng trên JDK 17.

## 4. Phạm vi rất hẹp của cơ chế nới lỏng

Ngay cả khi `--illegal-access=permit` còn hoạt động, nó cũng không có nghĩa “cho phép mọi thứ”.

### 4.1. Chỉ phục vụ một nhóm package JDK có lịch sử trước JPMS

Cơ chế nới lỏng ban đầu nhắm tới những package nội bộ của các runtime module đã tồn tại trong JDK 8, tạo điều kiện cho ứng dụng classpath cũ chuyển tiếp.

Những package mới xuất hiện sau Java 8 hoặc không thuộc nhóm hỗ trợ chuyển tiếp **không tự nhiên được mở** chỉ vì người dùng đặt `permit`.

Vì vậy, hai lỗi reflection trong cùng một ứng dụng có thể phản ứng khác nhau với flag: một lỗi thuộc nhóm được nới lỏng có thể biến mất trên JDK 11, lỗi khác vẫn bị chặn.

### 4.2. Chủ yếu áp dụng cho code trong unnamed module

`--illegal-access` lịch sử hướng tới code trên classpath, tức các unnamed module. Nó không phải cơ chế cấp quyền mở tất cả package cho mọi named module trên module path.

Nếu một thư viện được chuyển từ classpath sang explicit named module, nó có thể mất hành vi nới lỏng mà runtime trước đây áp dụng cho unnamed module. Khi đó, cần xem xét `exports`, `opens`, `requires` và tên module đích thực tế.

Đừng nhầm lẫn:

```text
Classpath code  -> unnamed module
Module-path JAR -> automatic hoặc explicit named module
```

Hai bối cảnh có quy tắc truy cập khác nhau.

### 4.3. Không giải quyết việc tham chiếu trực tiếp tới mọi JDK internal API

Ví dụ, code compile trực tiếp với một kiểu `sun.*` hoặc package không được export có thể gặp lỗi ở compile time. `--illegal-access` được thiết kế chủ yếu cho **illegal reflective access** chuyển tiếp; nó không phải công cụ chung để export mọi API nội bộ cho compiler.

Khi code thực sự cần tham chiếu kiểu public trong một package không được export, cần phân biệt trường hợp `--add-exports` (dành cho truy cập kiểu) với `--add-opens` (dành cho deep reflection).

### 4.4. Không khôi phục API hoặc công cụ đã bị loại khỏi JDK

Nếu một class, module hoặc công cụ đã bị loại khỏi JDK, mở package không làm class đó xuất hiện trở lại.

Ví dụ:

- JAXB/JAX-WS modules bị loại khỏi JDK từ Java 11.
- Nashorn JavaScript engine bị loại khỏi JDK từ Java 15.
- Một số công cụ JDK cũ hoặc API nội bộ đã biến mất ở các mốc khác nhau.

Lỗi thiếu class do module không còn tồn tại đòi hỏi dependency thay thế, thay API hoặc thiết kế lại chức năng. `--illegal-access` và `--add-opens` không giải quyết thiếu artifact.

### 4.5. Không thay thế kiểm tra behavioral compatibility

Ngay cả khi một phản chiếu vào private field thành công, layout object, kiểu field và invariant nội bộ vẫn có thể thay đổi giữa các JDK. Code truy cập trực tiếp cấu trúc `String`, collection hoặc memory internals có thể đọc sai dữ liệu hoặc phá invariants.

Thành công của `setAccessible(true)` không phải bằng chứng API nội bộ đó an toàn để dùng lâu dài.

## 5. Vì sao JDK 16 và JDK 17 là hai bước ngoặt?

### 5.1. JDK 16: strong encapsulation thành mặc định

Trước JDK 16, nhiều ứng dụng classpath nhận cảnh báo nhưng vẫn chạy nhờ chế độ `permit` mặc định. Với JDK 16, strong encapsulation trở thành mặc định theo JEP 396.

Hệ quả:

- Không có flag bổ sung, các truy cập trước đây được tạm nới lỏng có thể ném exception.
- `--illegal-access=permit` vẫn có thể được dùng trong JDK 16 để quay lại cơ chế chuyển tiếp ở phạm vi lịch sử.
- Nhóm migration có một khoảng chuyển tiếp để tìm và nâng thư viện trước JDK 17.

Vì vậy, nếu hệ thống đang ở JDK 11 và định hướng nâng lên JDK 17, nên coi thành công với `--illegal-access=deny` trên JDK 11/15 là tín hiệu tích cực nhưng **chưa phải bằng chứng đầy đủ**. Cần chạy trên JDK 17 vì còn nhiều thay đổi khác trong các release trung gian.

### 5.2. JDK 17: flag không còn mở package

JEP 403 loại bỏ khả năng kích hoạt lại cơ chế relaxed strong encapsulation bằng `--illegal-access`. Nếu vẫn truyền:

```bash
java --illegal-access=permit -jar app.jar
```

trên JDK 17, runtime có thể cảnh báo rằng tùy chọn đã bị bỏ qua. Các truy cập deep reflection vào package không mở vẫn bị từ chối.

Một cấu hình từng có tác dụng trên JDK 11 **không thể được giữ nguyên và coi là biện pháp khắc phục lỗi trên JDK 17**. Cần tìm đúng package, đúng module gọi và giải pháp cụ thể.

### 5.3. Ngoại lệ cần hiểu đúng: `jdk.unsupported`

JDK vẫn có module `jdk.unsupported` cung cấp một số API được duy trì phục vụ nhu cầu tương thích đặc biệt, như một số kiểu thuộc `sun.misc` và `sun.reflect`. Những API này có chính sách và mức rủi ro riêng, không đồng nghĩa mọi package `sun.*` đều được mở.

Không nên diễn giải “JDK 17 encapsulate mạnh hơn” thành “mọi truy cập sun.* đều biến mất”. Mỗi package cần được xác định module sở hữu và trạng thái export/open thực tế. Tốt nhất vẫn là chuyển sang API chuẩn khi có thể.

## 6. `--add-opens`: biện pháp có mục tiêu khi deep reflection còn cần thiết

Nếu chưa thể thay thư viện ngay, JDK cho phép mở một package cụ thể bằng `--add-opens`.

Cú pháp:

```text
--add-opens <source-module>/<package>=<target-module>
```

Ví dụ, ứng dụng classpath cần phản chiếu vào package `java.lang` của `java.base`:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
```

Ý nghĩa:

- `java.base`: module sở hữu package.
- `java.lang`: package được mở.
- `ALL-UNNAMED`: tất cả unnamed module, thường gồm code từ classpath.

Khác với `--illegal-access=permit` lịch sử, tùy chọn này **chỉ mở package được nêu**, không tự mở toàn bộ nhóm package nội bộ.

### 6.1. Nếu caller là named module

Với ứng dụng modular:

```java
module com.example.app {
    requires com.example.reflection.lib;
}
```

nếu code trong `com.example.reflection.lib` thực sự cần deep reflection vào `java.base/java.lang`, có thể dùng cấu hình:

```bash
java --add-opens java.base/java.lang=com.example.reflection.lib \
  --module-path mods \
  --module com.example.app/com.example.app.Main
```

Không tự động dùng `ALL-UNNAMED` cho code thuộc named module; cần cấp quyền cho đúng tên module đang thực hiện reflection.

### 6.2. Chọn module đích từ stack trace, không đoán

Một lỗi thường cung cấp thông báo tương tự:

```text
module java.base does not "opens java.lang" to unnamed module @...
```

Trong trường hợp đó, flag gợi ý có thể là:

```text
--add-opens java.base/java.lang=ALL-UNNAMED
```

Nhưng nếu thông báo chỉ ra `com.example.framework` là caller, target phải là tên module phù hợp thay vì chỉ định sai module.

Luôn kiểm tra stack trace để xác định **thư viện nào thực hiện truy cập**, bởi caller có thể không phải code ứng dụng.

### 6.3. Mở package không có nghĩa phục hồi API đã mất

`--add-opens` chỉ ảnh hưởng đến quyền truy cập. Nó không tạo class, method hoặc field đã bị xóa, không sửa mismatch của method descriptor và không bảo đảm implementation detail ổn định.

Nếu field `String.value` thay kiểu giữa hai JDK, mở `java.lang` không khiến field trở về kiểu cũ.

### 6.4. Chi phí của `ALL-UNNAMED`

`ALL-UNNAMED` mở package cho code thuộc mọi unnamed module trong phạm vi runtime. Nếu classpath chứa nhiều thư viện chưa được kiểm soát, đây có thể là phạm vi rộng hơn cần thiết.

Vì vậy:

- Ưu tiên nâng thư viện để loại bỏ phụ thuộc vào deep reflection nội bộ.
- Chỉ mở package khi có bằng chứng thực tế.
- Tránh sao chép một danh sách dài `--add-opens` từ môi trường khác.
- Ghi nhận owner và thời điểm dự kiến loại bỏ từng flag.
- Với named module, ưu tiên target cụ thể khi khả thi.

## 7. `--add-exports` khác `--add-opens` thế nào?

Hai lựa chọn cùng liên quan JPMS nhưng giải quyết vấn đề khác nhau.

| Tùy chọn | Mục đích chính | Ví dụ |
|---|---|---|
| `--add-exports` | Cho phép code khác tham chiếu các public type/member trong package vốn chưa được export | Truy cập compile/runtime tới public class nội bộ |
| `--add-opens` | Cho phép deep reflection tới package, kể cả non-public member theo các điều kiện của reflection | Framework dùng `setAccessible(true)` |

Ví dụ export package có public type nội bộ cho unnamed modules:

```bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp "lib/*:app.jar" com.example.Main
```

Ví dụ mở package cho deep reflection:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "lib/*:app.jar" com.example.Main
```

Nếu source code import một type nằm trong package không export, compiler có thể cần `--add-exports` ở compile time. Nếu code gọi `setAccessible` vào private field trong package không mở, JVM có thể cần `--add-opens` ở runtime.

Việc dùng một flag không có nghĩa được phép bỏ qua toàn bộ quy tắc còn lại. Một số tình huống có thể cần cả cấu hình compile và runtime riêng; không nên thêm cả hai nếu chưa chứng minh cần thiết.

### 7.1. `opens` trong `module-info.java`

Nếu bạn **sở hữu** một module, cách bền vững hơn là công bố mức mở phù hợp ngay trong descriptor:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.json;
}
```

Ở đây, module domain chỉ mở `com.example.domain.model` cho `com.example.json`, nếu hai module này tồn tại đúng tên khi triển khai. Điều này khác việc dùng `--add-opens` để can thiệp vào package do JDK hoặc thư viện khác sở hữu.

Khi thay đổi một thư viện bạn không sở hữu, giải pháp lâu dài vẫn nên đến từ phiên bản thư viện được nhà phát hành hỗ trợ, thay vì mặc định thay đổi command line ở mọi deployment.

## 8. Ví dụ đầy đủ: cùng source, khác kết quả giữa JDK 11 và 17

Xét chương trình minh họa:

```java
import java.lang.reflect.Field;

public class DeepReflectionDemo {
    public static void main(String[] args) throws Exception {
        Field valueField = String.class.getDeclaredField("value");
        valueField.setAccessible(true);

        System.out.println("Accessible: " + valueField.getName());
    }
}
```

Biên dịch:

```bash
javac DeepReflectionDemo.java
```

Trên các JDK lịch sử cho phép nới lỏng:

```bash
java --illegal-access=permit DeepReflectionDemo
```

Ở JDK 11, thao tác deep reflection này thường có thể thành công do cơ chế chuyển tiếp, đồng thời phát cảnh báo illegal reflective access.

Để khảo sát code path trên JDK 11:

```bash
java --illegal-access=debug DeepReflectionDemo
```

Trên JDK 16 không có flag, thao tác này có thể thất bại do strong encapsulation mặc định. Thử `--illegal-access=permit` trên JDK 16 có thể tạm mở lại phạm vi lịch sử.

Trên JDK 17:

```bash
java --illegal-access=permit DeepReflectionDemo
```

việc nới lỏng không còn được kích hoạt; `setAccessible(true)` có thể ném `InaccessibleObjectException`.

Cấu hình chuyển tiếp có mục tiêu:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED DeepReflectionDemo
```

có thể cho phép thao tác này về mặt access control. Nhưng đây **không phải lời khuyên truy cập field nội bộ của `String` trong ứng dụng thật**. Sử dụng API chuẩn như `String` methods hoặc công cụ xử lý văn bản phù hợp vẫn là cách an toàn.

### 8.1. Ma trận kết quả minh họa

| Runtime | Không flag | `--illegal-access=permit` | `--add-opens java.base/java.lang=ALL-UNNAMED` |
|---|---|---|---|
| JDK 11 | Có thể được nới lỏng mặc định, kèm warning | Có thể được nới lỏng, kèm warning | Mở đúng package |
| JDK 16 | Thường bị từ chối đối với deep reflection trái phép | Có thể nới lỏng lại phạm vi lịch sử | Mở đúng package |
| JDK 17 | Bị từ chối nếu package chưa mở | Flag không mở lại package | Mở đúng package |

Bảng mô tả tình huống minh họa với package `java.base/java.lang`, không phải quy tắc áp dụng cho mọi package hoặc mọi công cụ reflection. Kết quả còn phụ thuộc caller module, runtime arguments và implementation cụ thể.

## 9. Chẩn đoán lỗi: phân biệt đúng nguyên nhân

Không phải lỗi nạp class hoặc reflection nào cũng do `--illegal-access`.

### 9.1. `InaccessibleObjectException`

Dấu hiệu:

```text
java.lang.reflect.InaccessibleObjectException
module java.base does not "opens java.lang" to ...
```

Nguyên nhân thường là deep reflection vào package không được mở.

Hướng xử lý:

1. Xác định thư viện gọi reflection.
2. Nâng thư viện hoặc chuyển sang API công khai.
3. Nếu bắt buộc chuyển tiếp, cân nhắc `--add-opens` đúng package và đúng caller.
4. Kiểm thử lại trên JDK mục tiêu.

### 9.2. `IllegalAccessError`

Một class có thể đã biên dịch dựa vào việc truy cập class/member mà runtime mới không cho phép. Vấn đề có thể là export, visibility hoặc thay đổi linkage, không đơn thuần là deep reflection.

Cần xem stack trace và bytecode dependency. Nếu public type thuộc package không export, `--add-exports` có thể liên quan; nếu member không public, chỉ export không giúp code truy cập như public API.

### 9.3. `ClassNotFoundException` hoặc `NoClassDefFoundError`

Nếu class hoặc module không được đưa vào runtime, flag mở package không giúp tìm thấy nó. Kiểm tra:

- Dependency có trên classpath hoặc module path không?
- Module đã bị loại khỏi JDK hoặc thay artifact riêng chưa?
- Có xung đột version hoặc classloader không?
- Package thực sự tồn tại trong phiên bản đang triển khai không?

### 9.4. `NoSuchMethodError` hoặc `NoSuchFieldError`

Bytecode đang tham chiếu method/field không có trong class runtime. Đây thường là dấu hiệu không tương thích binary hoặc thay đổi implementation detail.

`--illegal-access` và `--add-opens` không tự phục hồi method/field đã đổi tên, đổi descriptor hoặc bị xóa.

### 9.5. `SecurityException`, permission hoặc sandbox restriction

Một số môi trường có cơ chế bảo mật hoặc policy khác với module encapsulation. Cần đọc loại exception, thông báo và stack trace để phân biệt.

Không nên thêm hàng loạt JVM flags chỉ vì thấy chữ “access” trong exception.

## 10. Công cụ tìm truy cập JDK internals

### 10.1. `jdeps --jdk-internals`

`jdeps` có thể phân tích tham chiếu bytecode tĩnh tới một số JDK internal APIs:

```bash
jdeps --jdk-internals --recursive \
  --class-path "lib/*" app.jar
```

Kết quả giúp xác định code đang tham chiếu class nội bộ và có thể gợi ý API thay thế.

Giới hạn: `jdeps` **không phát hiện đầy đủ** reflection dựa vào chuỗi, class name được sinh động hoặc truy cập qua JNI/native code. Vì vậy, không có cảnh báo từ `jdeps` không chứng minh toàn bộ ứng dụng không dùng JDK internals.

### 10.2. `jdeprscan`

`jdeprscan` hỗ trợ rà soát các API deprecated được dùng trong bytecode:

```bash
jdeprscan --release 17 --class-path "lib/*" app.jar
```

Công cụ này bổ sung góc nhìn về deprecated API, nhưng không có mục tiêu thay thế việc phát hiện mọi illegal reflective access.

### 10.3. Log và stack trace trong các JDK cũ

Nếu vẫn có môi trường JDK 11/15:

```bash
java --illegal-access=warn -jar app.jar
java --illegal-access=debug -jar app.jar
```

Chạy bộ test đủ đại diện để kích hoạt các code path cần kiểm tra. Thu thập tên class, thư viện, method và package truy cập. Sau đó thử JDK 17 trong môi trường test tương ứng production.

Không áp dụng `--illegal-access=debug` trên JDK 17 rồi kỳ vọng nhận lại stack trace của cơ chế cảnh báo cũ.

### 10.4. Kiểm kê JVM arguments hiện tại

Các cấu hình liên quan có thể nằm ở nhiều nơi:

- `JAVA_TOOL_OPTIONS` hoặc các biến môi trường khởi chạy Java.
- Dockerfile và container entrypoint.
- Kubernetes manifest, Helm values hoặc cấu hình systemd.
- Maven Surefire/Failsafe `argLine`.
- Gradle `Test.jvmArgs`, `JavaExec.jvmArgs` hoặc `applicationDefaultJvmArgs`.
- IDE Run Configuration.
- Script batch/shell và trình quản lý service.
- Agent/instrumentation configuration của monitoring hoặc profiling.

Một lỗi hay gặp là thêm `--add-opens` vào JVM chạy Gradle daemon nhưng **test thực tế chạy trong JVM forked riêng**. Trong trường hợp đó, flag phải được truyền vào đúng JVM chứa code reflection gây lỗi.

### 10.5. Kiểm tra đúng runtime đang chạy

Trên máy nhiều JDK, kết quả `java -version` trong terminal chưa chắc phản ánh runtime của container hoặc JVM test fork. Ghi nhận:

```bash
java -version
java --list-modules
```

Nếu đang chẩn đoán tiến trình Java còn chạy, có thể dùng công cụ phù hợp để xem command line thực tế, chẳng hạn:

```bash
jcmd <pid> VM.command_line
```

Chỉ chạy các công cụ chẩn đoán khi có quyền phù hợp và trong môi trường được phép. Kiểm tra thêm vendor/build của JDK để tránh kết luận từ một runtime khác.

## 11. Cấu hình migration trong Maven, Gradle và container

Các ví dụ dưới đây nhằm minh họa vị trí cấu hình **trong JVM sẽ thực thi ứng dụng hoặc test**. Không phải mọi dự án đều cần các flag này.

### 11.1. Maven Surefire

Nếu test chạy với JDK 17 và một thư viện cũ thật sự cần deep reflection vào `java.base/java.lang`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <argLine>
                    --add-opens java.base/java.lang=ALL-UNNAMED
                </argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Trong dự án có JaCoCo hoặc plugin khác dùng `argLine`, cần phối hợp cấu hình để không ghi đè các JVM arguments do plugin cung cấp. Nếu integration test chạy bằng Failsafe hoặc plugin khác, cần cấu hình JVM tương ứng.

### 11.2. Gradle Test task

```groovy
tasks.withType(Test).configureEach {
    jvmArgs '--add-opens', 'java.base/java.lang=ALL-UNNAMED'
}
```

Với Gradle Kotlin DSL:

```kotlin
tasks.withType<Test>().configureEach {
    jvmArgs("--add-opens", "java.base/java.lang=ALL-UNNAMED")
}
```

Tùy chọn này áp dụng cho test worker JVM được cấu hình qua task. Nó không tự động áp dụng cho artifact chạy trong production hoặc cho mọi `JavaExec` task.

### 11.3. Docker / container runtime

Ví dụ launcher:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY app.jar /app/app.jar
ENTRYPOINT ["java", "--add-opens", "java.base/java.lang=ALL-UNNAMED", "-jar", "/app/app.jar"]
```

Đây chỉ là ví dụ về cú pháp; không nên đưa flag này vào mọi image. Nếu thư viện đã được nâng và không còn cần deep reflection, hãy bỏ flag.

Không dùng `--illegal-access=permit` làm cách sửa lỗi container trên JDK 17, vì cơ chế đó không còn mở package.

### 11.4. Named module trên module path

Nếu caller là named module, có thể cấu hình target cụ thể:

```bash
java --add-opens java.base/java.lang=com.example.framework \
  --module-path mods \
  --module com.example.app/com.example.app.Main
```

Phải xác nhận `com.example.framework` thật sự tồn tại như named module tại runtime. Nếu thư viện vẫn ở classpath, target phù hợp có thể là `ALL-UNNAMED`.

## 12. Chiến lược thay thế code phụ thuộc vào JDK internals

Các JVM flag chỉ nên là biện pháp chuyển tiếp. Migration bền vững tập trung vào loại bỏ lý do cần truy cập nội bộ.

### 12.1. Nâng dependency lên phiên bản hỗ trợ JDK mục tiêu

Một số thư viện cũ dùng reflection để tối ưu serialization, proxy, ORM, mocking hoặc bytecode generation. Các phiên bản mới có thể đã đổi cách tương tác với JDK.

Quy trình nên gồm:

1. Xác định JAR và version gây ra truy cập.
2. Tìm phiên bản được nhà phát hành hỗ trợ trên JDK mục tiêu.
3. Nâng dependency và các dependency bắc cầu liên quan.
4. Chạy test trên runtime mục tiêu.
5. Loại bỏ JVM flag chuyển tiếp nếu không còn cần.

Không nên thêm `--add-opens` chỉ vì một issue trên mạng đề xuất như vậy mà chưa kiểm tra dependency version thực tế.

### 12.2. Dùng API công khai thay cho implementation detail

Nếu code tự viết đang truy cập field private của JDK, hãy tìm API chuẩn:

- Truy cập nội dung chuỗi: dùng `String` API thay vì field nội bộ.
- Encode/decode Base64: dùng `java.util.Base64`.
- Thao tác file: dùng `java.nio.file`.
- Đồng bộ và concurrency: dùng `java.util.concurrent`.
- Nghiệp vụ thời gian: dùng `java.time`.
- Classpath/module analysis: dùng `jdeps`, `ModuleLayer` hoặc API/module tools được hỗ trợ theo nhu cầu.

Không có thay thế một-một cho mọi internals; một số tối ưu hóa cũ cần được thiết kế lại.

### 12.3. Nếu bạn sở hữu module bị phản chiếu

Với module tự phát triển, có thể khai báo `opens` có chọn lọc:

```java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.serializer;
}
```

Cách này biểu đạt rõ hợp đồng reflection. Cần tránh `open module` toàn bộ nếu chỉ một package phải được mở.

### 12.4. Khi chưa thể thay ngay

Nếu có lý do vận hành chính đáng để giữ một `--add-opens`:

- Ghi tên package nguồn và module đích.
- Ghi thư viện và phiên bản yêu cầu flag.
- Ghi nguyên nhân cùng stack trace hoặc test tái hiện.
- Gán owner chịu trách nhiệm loại bỏ.
- Lập kế hoạch nâng dependency hoặc sửa code.
- Đưa flag vào cấu hình nhất quán giữa môi trường kiểm thử và production.
- Không coi flag là bảo đảm compatibility trong các JDK tiếp theo.

## 13. Quy trình migration thực hành từ JDK 11 lên 17

### Bước 1: Đóng băng baseline

Lưu JDK vendor/version, dependency graph, script khởi chạy, JVM args và test report khi ứng dụng còn chạy JDK 11.

### Bước 2: Tìm toàn bộ `--illegal-access` và các flags tương tự

Rà soát CI/CD, container, build tool, IDE và scripts. Phân biệt:

```text
--illegal-access=permit
--illegal-access=warn
--illegal-access=debug
--illegal-access=deny
--add-opens
--add-exports
```

Xác định flag nào còn được sử dụng khi chạy thật, flag nào là di sản trong tài liệu.

### Bước 3: Thu thập bằng chứng từ môi trường còn hỗ trợ flag

Nếu có JDK 11, sử dụng chế độ `warn`/`debug` với test suite đại diện để tìm illegal reflective access. Có thể chạy với `deny` để kiểm tra mức sẵn sàng theo strong encapsulation trong phạm vi của JDK đó.

### Bước 4: Phân loại từng phát hiện

| Loại | Ví dụ | Hướng khắc phục |
|---|---|---|
| Thư viện cũ reflect vào JDK internals | Proxy/serializer/ORM | Nâng phiên bản hoặc thay library |
| Ứng dụng tự reflect vào field JDK | `String.value` | Viết lại bằng API công khai |
| Code gọi public type trong package không export | Import `sun.nio.ch` | Thay API hoặc đánh giá `--add-exports` chuyển tiếp |
| Reflection vào module nội bộ do chính nhóm sở hữu | DTO/field trong named module | Cấu hình `opens` có chọn lọc |
| Class/module đã bị xóa khỏi JDK | API cũ không còn | Thêm dependency thay thế hoặc thiết kế lại |
| Lỗi do runtime dependency không khớp | `NoSuchMethodError` | Đồng bộ dependency và binary contracts |

### Bước 5: Nâng framework và dependency

Ưu tiên bản hỗ trợ JDK 17. Kiểm tra cả dependency trực tiếp lẫn transitive, nhất là ASM, Byte Buddy, CGLIB, JAXB/Jackson, ORM, testing tools và instrumentation agents nếu được dùng.

### Bước 6: Chạy trên JDK 17 không dựa vào `--illegal-access`

Thử khởi động, unit/integration test và các luồng sử dụng reflection. Nếu có lỗi, thu thập stack trace đầy đủ và xác định đúng package/module thay vì mở hàng loạt.

### Bước 7: Chỉ thêm `--add-opens` cần thiết trong giai đoạn chuyển tiếp

Nếu thư viện chưa nâng được nhưng cần đưa hệ thống lên JDK 17, thêm flag đúng package và đúng caller như biện pháp tạm thời. Gắn với issue kỹ thuật và kiểm tra lại sau mỗi lần nâng dependency.

### Bước 8: Kiểm tra môi trường triển khai thật

Chạy artifact bằng cùng runtime image, classpath/module path, agent và config như production. Một test pass trong IDE không chứng minh JVM trong container đã nhận đúng flag.

### Bước 9: Xóa cấu hình lỗi thời

Loại `--illegal-access` không còn tác dụng trên JDK 17, đồng thời xóa dần các `--add-opens` không còn cần thiết. Cập nhật tài liệu và pipeline để không truyền tham số vô nghĩa cho các đợt nâng JDK tiếp theo.

## 14. Các hiểu lầm thường gặp

### “`--illegal-access=permit` sửa được lỗi reflection trên Java 17”

**Sai.** Từ JDK 17, flag không tái bật relaxed strong encapsulation. Cần sửa dependency/code hoặc, nếu bất khả kháng, mở chính xác package bằng `--add-opens`.

### “`--illegal-access` từng mở tất cả package JDK”

**Sai.** Cơ chế chuyển tiếp có phạm vi lịch sử giới hạn và không áp dụng rộng cho mọi package, module hoặc kiểu truy cập.

### “Nếu chạy trên JDK 11 không warning thì chắc chắn an toàn”

**Sai.** Chế độ `permit` thường chỉ in cảnh báo ban đầu; các code path chưa chạy không xuất hiện trong log. Reflection động hoặc JNI cũng có thể không được phát hiện đầy đủ.

### “`--add-opens` và `--add-exports` là một”

**Sai.** Một lựa chọn chủ yếu liên quan deep reflection; lựa chọn kia cho phép truy cập public type trong package không export. Cần đọc chính xác lỗi và nhu cầu.

### “Mở package nghĩa là API nội bộ ổn định”

**Sai.** Mở chỉ xử lý rào cản access control. Class, field, method hoặc semantics vẫn có thể đổi hoặc biến mất.

### “Thêm flag vào Maven/Gradle là production tự nhận”

**Sai.** JVM chạy build, JVM test fork và JVM chạy ứng dụng là những process khác nhau. Phải áp dụng cho đúng process.

### “Cứ mở toàn bộ package cho `ALL-UNNAMED` để khỏi lỗi”

**Không nên.** Cách này làm phạm vi truy cập rộng hơn cần thiết, che giấu dependency lỗi thời và tăng công sức migration về sau.

## 15. Checklist trước khi loại bỏ `--illegal-access`

- [ ] Xác định đúng JDK runtime và biết mốc thay đổi ở JDK 16/17.
- [ ] Rà soát mọi JVM argument `--illegal-access` trong build, test và deployment.
- [ ] Phân biệt caller thuộc unnamed module hay named module.
- [ ] Thu thập stack trace, package nguồn và module sở hữu khi reflection lỗi.
- [ ] Chạy `jdeps --jdk-internals` để tìm tham chiếu tĩnh phù hợp.
- [ ] Nâng các framework và dependency phụ thuộc JDK internals.
- [ ] Thay code tự viết bằng API công khai khi khả thi.
- [ ] Không dùng `--illegal-access=permit` làm workaround JDK 17.
- [ ] Nếu cần, dùng `--add-opens` hoặc `--add-exports` đúng loại, đúng package và đúng target.
- [ ] Có owner, bằng chứng và kế hoạch gỡ cho từng flag chuyển tiếp.
- [ ] Kiểm thử cả runtime/module path thực tế và các test forked JVM.
- [ ] Xác minh luồng nghiệp vụ dùng reflection, serialization, proxy và instrumentation.
- [ ] Bỏ flag không còn cần và lưu lại cấu hình khởi chạy cuối.

## 16. Kết luận

`--illegal-access` được đưa vào trong giai đoạn đầu của JPMS để giúp ứng dụng classpath cũ chuyển tiếp khi JDK bắt đầu encapsulate các package nội bộ. Trên JDK 9–15, chế độ mặc định `permit` có thể cho phép một số illegal reflective access kèm cảnh báo; JDK 16 chuyển mặc định sang strong encapsulation nhưng vẫn có cơ chế nới lỏng chuyển tiếp; đến JDK 17, `--illegal-access` không còn mở package.

Để migration bền vững, đừng tiếp tục dựa vào `--illegal-access=permit`. Hãy xác định chính xác code nào đang truy cập internals, nâng thư viện hoặc chuyển sang API công khai, dùng `--add-opens`/`--add-exports` có mục tiêu khi thực sự cần và kiểm thử trên JVM triển khai cuối cùng. Cách này giúp hệ thống chủ động với các thay đổi encapsulation của JDK thay vì phụ thuộc vào một cơ chế tương thích vốn đã kết thúc.
