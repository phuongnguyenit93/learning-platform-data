# `--enable-final-field-mutation` và phạm vi module được cấp quyền

Java dùng `final` để biểu thị rằng một field được gán trong quá trình khởi tạo và không bị thay đổi tùy ý sau đó. Tuy nhiên, trong nhiều năm, deep reflection có thể vượt qua giới hạn đóng gói để ghi lại một số `final` instance field sau khi constructor đã chạy. Cách làm này làm suy yếu hợp đồng bất biến mà mã nguồn, Java Memory Model và JIT có thể dựa vào.

JEP 500, **Prepare to Make Final Mean Final**, bắt đầu lộ trình siết chặt hành vi này trong Java 26. Java 26 và Java 27 mặc định vẫn cho phép một lần ghi trái phép qua deep reflection nhưng phát cảnh báo. Một release tương lai sẽ mặc định từ chối các lần ghi không được cấp quyền. Khi thật sự cần duy trì thư viện cũ, `--enable-final-field-mutation` cho phép cấp quyền có chọn lọc theo **module chứa code thực hiện phép ghi**. Đây là tùy chọn runtime, không phải preview feature. [JEP 500](https://openjdk.org/jeps/500) · [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) · [Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/27/migrate/preparing-final-field-mutation-restrictions.html).

Điểm cần nhớ: quyền được cấp cho module của caller (thư viện hoặc ứng dụng gọi `Field.set`), còn package khai báo field phải cho caller quyền truy cập reflection theo quy tắc module. Hai điều kiện này độc lập. `--enable-final-field-mutation` không tự mở package; `--add-opens` không tự cấp quyền ghi `final` field.

## 1. JEP 500 áp dụng cho thao tác nào?

JEP 500 tập trung vào các API Java có thể ghi lại `final` instance field sau khi đối tượng đã được khởi tạo. Những mutation methods gồm:

- `Field.set(Object, Object)` và các overload kiểu nguyên thủy như `setInt`, `setLong`, `setBoolean`, `setByte`, `setChar`, `setShort`, `setFloat`, `setDouble`.
- `MethodHandles.Lookup.unreflectSetter(Field)` khi tạo method handle có quyền ghi vào field phản chiếu.

Ví dụ, lời gọi `field.setAccessible(true)` có thể cho phép truy cập sâu vào một field private nếu module/package đáp ứng điều kiện. Nhưng `setAccessible(true)` thành công không còn đồng nghĩa caller có thể ghi một `final` field. Quyền ghi được kiểm tra riêng khi gọi mutation method.

```java
Field field = Settings.class.getDeclaredField("endpoint");
field.setAccessible(true);
field.set(settings, "https://replacement.example");
```

Từ Java 26, phép ghi ở dòng cuối là hành vi được JEP 500 quản lý. `setAccessible(true)` không phát cảnh báo JEP 500; cảnh báo hoặc exception xuất hiện khi code thực hiện phép ghi trái phép.

JEP 500 không cấm phép gán hợp lệ trong constructor, field initializer hoặc initializer block. Nó cũng không biến một field thường thành immutable. Phạm vi ở đây là các mutation methods dùng để thay đổi `final` field sau khi đối tượng đã được khởi tạo.

## 2. Điều kiện để ghi một `final` field

Theo hợp đồng `Field.set` trong Java 27, một `final` field chỉ có write access khi tất cả các điều kiện sau đều đúng. Gọi `D` là class khai báo field, còn caller là class/module đang gọi mutation method.

1. `setAccessible(true)` đã thành công trên đối tượng `Field`.
2. Final field mutation được bật cho module của caller.
3. Có ít nhất một quan hệ truy cập hợp lệ:
   - `D` và caller nằm trong cùng một module; hoặc
   - field là `public`, `D` là `public`, và package của `D` được export tới module caller; hoặc
   - package chứa `D` được open tới module caller.
4. `D` không phải record class.
5. `D` không phải hidden class.
6. Field không phải `static`.

Nếu caller chưa được enable nhưng field vẫn có thể truy cập bằng reflection, `--illegal-final-field-mutation` quyết định cách xử lý lần ghi đó: `warn` mặc định cho phép ghi và cảnh báo; `deny` ném `IllegalAccessException`. Trường hợp `setAccessible(true)` thất bại thì lời gọi đó ném `InaccessibleObjectException` trước khi `Field.set` được thực hiện. `static final`, record final fields và hidden-class final fields luôn không có write access, kể cả khi caller được enable. Việc mở package bằng `opens` trong module descriptor hoặc `--add-opens` tại startup không thay thế điều kiện cấp quyền final-field mutation.

| Field | Có thể ghi bằng deep reflection sau Java 26? | Giải thích |
|---|---|---|
| `final` instance field của class thông thường | Có điều kiện. | Cần quyền cho caller, quyền truy cập reflection và package/module phù hợp. |
| `static final` field | Không. | `setAccessible(true)` chỉ cho phép đọc; không cấp write access. |
| `final` field khai báo trong record | Không. | Record component state không được sửa qua mutation methods. |
| `final` field khai báo trong hidden class | Không. | Hidden class final fields không được phép ghi theo cơ chế này. |
| Field không có `final` | Không thuộc phạm vi JEP 500. | Vẫn tuân theo quy tắc truy cập reflection/module thông thường. |

Javadoc cũng nhấn mạnh rằng ghi final field chỉ có ý nghĩa trong quá trình deserialization hoặc tái tạo đối tượng có blank final fields, trước khi đối tượng được đưa cho phần khác của chương trình. Ghi sau khi đối tượng đã được chia sẻ có thể tạo kết quả khó dự đoán; một số code có thể tiếp tục quan sát giá trị cũ do các giả định tối ưu hóa.

Tham khảo: [Java 27 `Field.set`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Field.html) · [Java 27 `AccessibleObject`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AccessibleObject.html) · [Java 27 `MethodHandles.Lookup.unreflectSetter`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html).

## 3. `--enable-final-field-mutation` cấp quyền cho module nào?

Tùy chọn này nhận danh sách module chứa code được phép mutate final instance fields. Nó cấp quyền cho **caller module**, không phải module khai báo class/field bị sửa.

| Giá trị | Phạm vi caller được cấp quyền | Khi dùng |
|---|---|---|
| `ALL-UNNAMED` | Tất cả code chạy trong unnamed modules, thường là code trên classpath. | Ứng dụng hoặc thư viện thực hiện phép ghi nằm trên classpath. |
| `com.example.mapper` | Named module `com.example.mapper`. | Thư viện mapper là caller và chạy như named module. |
| `com.example.mapper,com.example.serializer` | Hai named modules được liệt kê. | Chỉ hai module này cần giữ tương thích với hành vi cũ. |

Ví dụ cấp quyền cho code trên classpath:

```bash
java --enable-final-field-mutation=ALL-UNNAMED -jar application.jar
```

Ví dụ cấp quyền cho một hoặc nhiều named modules:

```bash
java --enable-final-field-mutation=com.example.mapper,com.example.serializer \
     --module-path mods \
     -m com.example.application/com.example.application.Main
```

Tên module phải là tên module Java, không phải tên package, tên class, tên JAR hay tên module khai báo field. Ví dụ, nếu `com.example.mapper` gọi `Field.set` để sửa field trong module `com.example.domain`, thì module cần được cấp quyền là `com.example.mapper`.

Quyền này được cấu hình khi JVM khởi động. JEP 500 giới hạn việc cấp quyền cho các module trong boot layer; module được tạo trong một user-defined `ModuleLayer` không thể được chọn bằng danh sách này. `ALL-UNNAMED` là phạm vi rộng cho code trong unnamed modules, vì vậy chỉ dùng khi caller thực sự nằm trên classpath và không thể chuyển sang một module có tên.

### Ví dụ phân biệt caller module và target module

Giả sử cấu trúc ứng dụng như sau:

```text
com.example.domain       khai báo class Account và final field id
com.example.mapper       dùng reflection để khôi phục Account.id
```

`--enable-final-field-mutation=com.example.domain` cấp quyền cho code trong domain module. Nhưng code gọi `Field.set` nằm trong mapper module, nên đó không phải module cần được cấp quyền. Cấu hình đúng là:

```bash
java --enable-final-field-mutation=com.example.mapper ...
```

Nếu mapper chạy trên classpath thay vì module path, dùng `ALL-UNNAMED`. Hãy xác định module từ stack trace cảnh báo JDK 26/27; cảnh báo ghi tên module của code thực hiện phép ghi.

## 4. Vì sao vẫn cần `opens` hoặc `--add-opens`?

`--enable-final-field-mutation` chỉ cấp khả năng mutate cho caller module. Để `Field.setAccessible(true)` có thể bỏ qua kiểm tra truy cập Java, target module còn phải cho phép deep reflection.

Với named module, có thể mở package cụ thể tới module caller trong `module-info.java`:

```java
module com.example.domain {
    exports com.example.domain.model;
    opens com.example.domain.model to com.example.mapper;
}
```

Hoặc mở package ở thời điểm khởi chạy:

```bash
java \
  --enable-final-field-mutation=com.example.mapper \
  --add-opens=com.example.domain/com.example.domain.model=com.example.mapper \
  --module-path mods \
  -m com.example.mapper/com.example.mapper.Main
```

Cú pháp của `--add-opens` là:

```text
--add-opens=module-đích/package-đích=module-caller
```

Với code caller trên classpath, dùng `ALL-UNNAMED` ở phía nhận:

```bash
java \
  --enable-final-field-mutation=ALL-UNNAMED \
  --add-opens=com.example.domain/com.example.domain.model=ALL-UNNAMED \
  -jar application.jar
```

`exports` và `opens` có ý nghĩa khác nhau. `exports` cho phép truy cập các public types/members theo quy tắc module; `opens` cho phép deep reflection. Với private field trong package của một module khác, thông thường cần package được open cho caller để `setAccessible(true)` thành công. Việc gọi `Module::addOpens` động sau khi JVM chạy không thay thế việc package được mở trong module descriptor hoặc qua `--add-opens` ở startup cho điều kiện ghi final field.

| Cấu hình | Tác dụng | Có tự cấp quyền mutate final field không? |
|---|---|---|
| `--enable-final-field-mutation=...` | Bật khả năng mutate cho caller module được chọn. | Có, nhưng vẫn cần các điều kiện truy cập khác. |
| `opens package to caller` trong `module-info.java` | Mở package cho deep reflection từ caller. | Không. |
| `--add-opens=target/package=caller` | Mở package ở startup để caller có thể dùng deep reflection. | Không. |
| `--illegal-final-field-mutation=deny` | Từ chối các lần mutate không được cấp quyền. | Không; đây là chính sách xử lý, không phải danh sách cấp quyền. |

Nếu `setAccessible(true)` thất bại vì package chưa open, ứng dụng có thể nhận `InaccessibleObjectException`. Thêm `--enable-final-field-mutation` không sửa được lỗi đó. Nếu package đã mở nhưng caller chưa được cấp quyền, hành vi được điều khiển bởi `--illegal-final-field-mutation`.

## 5. Các chế độ của `--illegal-final-field-mutation`

Tùy chọn này điều khiển cách JVM xử lý một lần mutate final field bị xem là trái phép. Nó áp dụng toàn hệ thống, không chỉ cho một module cụ thể. Java 26 và Java 27 có bốn chế độ:

| Chế độ | Hành vi | Vai trò |
|---|---|---|
| `warn` | Cho phép phép ghi trái phép tiếp tục nhưng phát cảnh báo ở lần đầu tiên mỗi caller module thực hiện. Tối đa một cảnh báo cho mỗi module. | Mặc định trong JDK 26 và JDK 27; dùng để phát hiện dependency cần nâng cấp. |
| `debug` | Cho phép phép ghi trái phép tiếp tục, đồng thời phát cảnh báo và stack trace cho từng lần mutate. | Điều tra chính xác vị trí code và thư viện gây ra mutation. |
| `deny` | Từ chối phép ghi trái phép; `Field.set` ném `IllegalAccessException`. | Kiểm tra ứng dụng đã sẵn sàng cho mặc định nghiêm ngặt trong release tương lai. |
| `allow` | Cho phép mọi phép ghi trái phép mà không cảnh báo. | Chỉ là biện pháp tạm thời; sẽ bị loại bỏ trong tương lai. |

Các lệnh thường dùng:

```bash
# Mặc định của Java 26/27: cảnh báo một lần cho mỗi caller module
java --illegal-final-field-mutation=warn -jar application.jar

# Điều tra: cảnh báo và stack trace cho từng lần mutate trái phép
java --illegal-final-field-mutation=debug -jar application.jar

# Kiểm thử nghiêm ngặt: mọi lần mutate trái phép phải thất bại
java --illegal-final-field-mutation=deny -jar application.jar
```

`--illegal-final-field-mutation` không quyết định module nào được cấp quyền; `--enable-final-field-mutation` mới làm việc đó. Khi chạy `deny` cùng một danh sách module đã enable, các module trong danh sách vẫn có thể mutate nếu thỏa điều kiện `Field` và package. Những module không được enable sẽ bị từ chối.

Lộ trình của JEP 500 là chuyển mặc định sang `deny` trong một release tương lai; Java 27 vẫn đang ở giai đoạn cảnh báo. Tùy chọn `--illegal-final-field-mutation` cũng được ghi rõ là sẽ bị loại bỏ trong tương lai. Không giả định Java 27 đã mặc định từ chối hoặc tự chọn một phiên bản tương lai cụ thể khi tài liệu chưa công bố mốc đó. [JDK 27 `java` command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).

## 6. Thực hành với hai named modules

Ví dụ sau mô phỏng một thư viện mapper khôi phục `Account.id` bằng reflection. Đây là phép thử có chủ đích để quan sát quyền caller và chế độ `warn`/`deny`; nó cố ý ghi field sau constructor để tạo tình huống migration. Không dùng giá trị đọc lại sau phép ghi này làm logic nghiệp vụ: Javadoc chỉ xem việc ghi final field là có ý nghĩa khi tái tạo đối tượng có blank final field trước khi đối tượng được chia sẻ.

### Module khai báo field

`src/com.example.domain/module-info.java`:

```java
module com.example.domain {
    exports com.example.domain.model;
    opens com.example.domain.model to com.example.mapper;
}
```

`src/com.example.domain/com/example/domain/model/Account.java`:

```java
package com.example.domain.model;

public final class Account {
    private final String id;

    public Account(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
```

### Module thực hiện mutation

`src/com.example.mapper/module-info.java`:

```java
module com.example.mapper {
    requires com.example.domain;
}
```

`src/com.example.mapper/com/example/mapper/Main.java`:

```java
package com.example.mapper;

import com.example.domain.model.Account;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws Exception {
        Account account = new Account("created-by-constructor");

        Field id = Account.class.getDeclaredField("id");
        id.setAccessible(true);
        id.set(account, "restored-by-mapper");

        System.out.println(account.id());
    }
}
```

### Biên dịch và chạy

Biên dịch hai module:

```bash
javac --module-source-path src -d out \
  -m com.example.domain,com.example.mapper
```

Chạy với module mapper được cấp quyền:

```bash
java --module-path out \
  --enable-final-field-mutation=com.example.mapper \
  -m com.example.mapper/com.example.mapper.Main
```

Vì package `com.example.domain.model` đã mở cho `com.example.mapper`, `setAccessible(true)` thành công. Module thực hiện `Field.set` là `com.example.mapper`, nên đó là module được nêu trong `--enable-final-field-mutation`.

### Thử các cấu hình khác nhau

| Cấu hình runtime | Kết quả dự kiến trong JDK 27 |
|---|---|
| Không có `--enable...`, không đặt `--illegal...` | Phép ghi trái phép vẫn có thể chạy và phát cảnh báo một lần cho `com.example.mapper`. |
| `--illegal-final-field-mutation=debug` | Phép ghi vẫn chạy; mỗi lần có cảnh báo và stack trace. |
| `--illegal-final-field-mutation=deny` | `Field.set` ném `IllegalAccessException`. |
| `--enable-final-field-mutation=com.example.mapper` | Caller được cấp quyền; nếu package mở và field đủ điều kiện, phép ghi chạy mà không bị xem là trái phép. |
| `--enable-final-field-mutation=com.example.domain` | Cấp quyền nhầm module; mapper vẫn là caller chưa được enable. |
| Enable đúng mapper nhưng bỏ `opens`/`--add-opens` cho private field ở module domain | `setAccessible(true)` không thể vượt qua ranh giới module; phép ghi không thực hiện được. |

Để kiểm tra riêng tác dụng của `--add-opens`, có thể bỏ dòng `opens` trong `module-info.java` rồi chạy:

```bash
java --module-path out \
  --enable-final-field-mutation=com.example.mapper \
  --add-opens=com.example.domain/com.example.domain.model=com.example.mapper \
  -m com.example.mapper/com.example.mapper.Main
```

Ở đây hai quyền được cấp độc lập: `--enable-final-field-mutation` cấp khả năng mutate cho mapper; `--add-opens` cho phép mapper deep-reflect vào package model.

## 7. Chẩn đoán thư viện đang mutate final field

Code gây mutation thường nằm trong thư viện serialization, mapping, dependency injection, mocking hoặc persistence. Warning cho biết tên field, class khai báo và caller module. Đừng vội thêm `ALL-UNNAMED`; trước tiên hãy xác định thư viện nào thực hiện phép ghi.

### Dùng chế độ `debug`

Chạy ứng dụng với:

```bash
java --illegal-final-field-mutation=debug -jar application.jar
```

Mỗi lần mutate trái phép sẽ có warning và stack trace. Tìm frame đầu tiên thuộc thư viện hoặc code ứng dụng của bạn để xác định nơi cần nâng cấp hoặc thay thế.

### Dùng JDK Flight Recorder

JFR ghi event `jdk.FinalFieldMutation` khi code mutate final instance field qua deep reflection hoặc lấy `MethodHandle` setter bằng `Lookup.unreflectSetter`. Event cho biết class khai báo field, tên field, thread và stack trace.

Khởi động ghi JFR:

```bash
java -XX:StartFlightRecording:filename=final-field-mutation.jfr,dumponexit=true \
     -jar application.jar
```

Sau khi ứng dụng kết thúc hoặc recording đã được dump, đọc event:

```bash
jfr print --events jdk.FinalFieldMutation final-field-mutation.jfr
```

JFR hữu ích khi mutation chỉ xảy ra trong một luồng nghiệp vụ hiếm hoặc khi cần quan sát nhiều request trong môi trường staging. Với một lần tái hiện nhỏ, `--illegal-final-field-mutation=debug` thường cho phản hồi nhanh hơn.

## 8. Quy trình migration khuyến nghị

1. **Chạy bằng JDK 26 hoặc 27 với mặc định `warn`.** Thu thập tất cả warning trong test tích hợp và staging; đừng chỉ kiểm tra startup vì mutation có thể xảy ra ở một nhánh nghiệp vụ muộn.
2. **Bật `debug` hoặc JFR.** Xác định chính xác caller module, thư viện, class khai báo và field bị sửa.
3. **Nâng cấp dependency.** Kiểm tra release mới của thư viện có hỗ trợ Java 26/27 và tránh mutate final fields hay không. Đây là hướng xử lý ưu tiên.
4. **Thay đổi cách tạo object.** Ưu tiên constructor injection, factory, builder, serialization proxy hoặc API khôi phục đối tượng được thiết kế rõ ràng. Đừng sửa final field sau khi object đã được chia sẻ.
5. **Kiểm thử với `deny`.** Chạy `--illegal-final-field-mutation=deny` để tìm mọi phép ghi chưa được cấp quyền. Nếu còn lỗi, sửa thư viện hoặc code gây ra trước khi phát hành.
6. **Chỉ enable ngoại lệ thật sự không thể loại bỏ.** Nếu một thư viện bắt buộc phải mutate final field và chưa thể nâng cấp/thay thế, cấp quyền đúng module caller. Đồng thời xác nhận package target đã mở đúng cho caller.
7. **Thu hẹp phạm vi.** Ưu tiên tên module cụ thể. Dùng `ALL-UNNAMED` chỉ khi caller nằm trên classpath và phạm vi tất cả unnamed modules là chấp nhận được.
8. **Kiểm thử lại trên JDK mục tiêu.** Giữ các cờ runtime trong cấu hình triển khai được quản lý và xác nhận hành vi sau mỗi lần nâng cấp JDK hoặc thư viện.

Không dùng `--illegal-final-field-mutation=allow` làm cấu hình production lâu dài. Chế độ này che giấu mọi mutation trái phép và sẽ bị loại bỏ trong tương lai. Cũng không thêm `--enable-final-field-mutation=ALL-UNNAMED` chỉ để xóa warning; cách đó giữ nguyên phụ thuộc rủi ro và cấp quyền rộng hơn mức cần thiết.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| Enable module khai báo field là đủ. | Phải enable module của caller đang gọi mutation method. |
| `--enable-final-field-mutation` mở package private. | Không; package vẫn phải open hoặc thỏa điều kiện truy cập tương ứng để `setAccessible(true)` thành công. |
| `--add-opens` cho phép ghi final field. | Không; nó chỉ giải quyết deep reflection access, không cấp final-field mutation capability. |
| `--illegal-final-field-mutation=deny` từ chối mọi field `final`, kể cả module đã enable. | Nó từ chối các mutation trái phép; module được enable vẫn có thể ghi nếu tất cả điều kiện khác thỏa mãn. |
| Java 27 đã mặc định deny. | Không; Java 27 vẫn mặc định `warn`. Deny là mặc định dự kiến trong một release tương lai chưa được ấn định ở tài liệu hiện tại. |
| Mọi final field đều có thể ghi nếu thêm cờ. | `static final`, record final fields và hidden-class final fields vẫn không thể ghi bằng mutation methods. |
| Warning chứng minh ứng dụng đã hỏng. | Trong JDK 26/27, warning cho biết mutation vẫn diễn ra nhưng sẽ bị chặn theo lộ trình tương lai nếu không xử lý. |
| Thêm `--enable...` làm code an toàn hơn. | Nó duy trì khả năng tương thích cho caller được chọn; việc mutate final vẫn làm suy yếu bất biến và có thể gây vấn đề tối ưu hóa. |

## 10. Checklist trước khi cấp quyền

- [ ] Đã xác định đúng code thực hiện `Field.set` hoặc `Lookup.unreflectSetter`.
- [ ] Đã xác định caller module từ warning, stack trace hoặc JFR event.
- [ ] Đã xác nhận thư viện chưa có phiên bản thay thế không mutate final fields.
- [ ] Đã hiểu `--enable-final-field-mutation` cấp quyền theo module caller.
- [ ] Nếu caller là classpath, đã đánh giá phạm vi rộng của `ALL-UNNAMED`.
- [ ] Nếu caller là named module, đã dùng đúng tên module trong danh sách phân tách bằng dấu phẩy.
- [ ] Đã xác nhận module target mở package cần thiết cho caller hoặc đáp ứng điều kiện public/export.
- [ ] Đã kiểm tra field là non-static, không thuộc record class hoặc hidden class.
- [ ] Đã chạy thử `--illegal-final-field-mutation=deny` để phát hiện mutation chưa được cấp quyền.
- [ ] Nếu bắt buộc enable, đã giới hạn danh sách module ở mức tối thiểu và kiểm tra trên JDK triển khai.
- [ ] Đã có kế hoạch loại bỏ ngoại lệ khi dependency được nâng cấp hoặc thiết kế object được sửa.

## Tài liệu tham khảo chính thức

- [JEP 500: Prepare to Make Final Mean Final](https://openjdk.org/jeps/500)
- [Java SE 27 — The `java` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [Java SE 27 — `Field`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Field.html)
- [Java SE 27 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java SE 27 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Preparing for final Field Mutation Restrictions — JDK 27 Migration Guide](https://docs.oracle.com/en/java/javase/27/migrate/preparing-final-field-mutation-restrictions.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Avoiding Final Field Mutation — Inside.java](https://inside.java/2026/04/27/avoiding-final-field-mutation/)

*Cập nhật nội dung: 27-11-2026. JDK 26 và 27 vẫn mặc định cảnh báo (`warn`); hãy dùng `deny` trong kiểm thử migration và chỉ cấp quyền module cụ thể khi không thể loại bỏ dependency mutate final field.*
