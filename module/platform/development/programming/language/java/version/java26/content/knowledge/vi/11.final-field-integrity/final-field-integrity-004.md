# Phân biệt đọc reflection, mở package và quyền sửa final

*Tình trạng được đối chiếu với JDK 26 tại ngày 27/11/2026.*

JEP 500 – **Prepare to Make Final Mean Final** bắt đầu siết việc sửa field `final` bằng deep reflection từ JDK 26. Mục tiêu là bảo vệ tính toàn vẹn của dữ liệu mà chương trình và JVM được phép giả định là không đổi sau khởi tạo.

Khi làm việc với reflection, cần tách ba quyền độc lập:

1. **Đọc field:** caller có được phép đọc giá trị field qua `Field.get()` hay không?
2. **Mở package:** caller có được phép vượt qua kiểm tra truy cập Java để đọc member private bằng deep reflection hay không?
3. **Sửa final:** module của caller có được cấp khả năng sửa final instance field hay không?

`setAccessible(true)` và `--add-opens` liên quan đến quyền truy cập sâu. `--enable-final-field-mutation` cấp quyền mutation final cho module gọi. Mở package không tự cấp quyền sửa final; cấp quyền mutation cũng không tự mở package.

## 1. Đọc field bằng reflection không đồng nghĩa với sửa field

Reflection có thể đọc field public theo quy tắc truy cập thông thường. Với field private trong một module khác, caller cần package được mở cho module của mình để bật deep reflection.

Ví dụ lớp cần đọc:

```java
package com.example.model;

public final class Settings {
    private final String endpoint = "https://api.example.com";
}
```

Đọc field:

```java
import java.lang.reflect.Field;

public class ReadPrivateField {
    static String readEndpoint(Object settings)
            throws ReflectiveOperationException {

        Class<?> settingsClass = Class.forName("com.example.model.Settings");
        Field field = settingsClass.getDeclaredField("endpoint");

        if (!field.trySetAccessible()) {
            throw new IllegalAccessException(
                    "Package is not open to this caller"
            );
        }

        return (String) field.get(settings);
    }
}
```

`trySetAccessible()` thử bật cờ accessible và trả về `false` nếu không thể mở quyền truy cập sâu. Có thể dùng `setAccessible(true)` thay thế; phương thức này ném `InaccessibleObjectException` khi không thể bật quyền. Không dùng `isAccessible()` trong code mới vì phương thức đó đã deprecated; nếu cần kiểm tra quyền truy cập hiện tại, dùng `canAccess(receiver)`.

Việc đọc giá trị final bằng `Field.get()` không phải final field mutation. JEP 500 không yêu cầu bật `--enable-final-field-mutation` chỉ để đọc field final. Tuy vậy, caller vẫn phải có quyền truy cập member theo quy tắc Java và module.

## 2. Mở package để deep reflection

Trong hệ thống module, một package có thể được export hoặc open. Hai cơ chế này phục vụ mục đích khác nhau:

| Cơ chế | Ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| `exports` | Cho module khác truy cập các kiểu và member public của package theo quy tắc Java | API public giữa các module |
| `opens` | Cho phép deep reflection trên các kiểu và member của package | Framework cần đọc member private, ví dụ mapper hoặc serializer |
| `--add-exports` | Mở quyền truy cập public ở runtime cho package cụ thể | Tương thích tạm thời với API public trong module chưa export |
| `--add-opens` | Mở deep reflection ở runtime cho package cụ thể | Tương thích tạm thời với framework cần truy cập private member |

Ví dụ module khai báo package mở có giới hạn:

```java
module model {
    exports com.example.api;
    opens com.example.model to app;
}
```

Trong đó module `app` có thể dùng deep reflection trên package `com.example.model`. Nếu không sửa được module descriptor, có thể mở package khi chạy:

```bash
java --add-opens model/com.example.model=app \
     --module-path mods -m app/com.example.Main
```

Với code trên class path, caller thuộc unnamed module:

```bash
java --add-opens model/com.example.model=ALL-UNNAMED \
     --module-path mods -cp app.jar com.example.Main
```

Mở package giúp `trySetAccessible()` hoặc `setAccessible(true)` có thể thành công đối với member private. Nó không cấp quyền sửa final field. `--add-exports` cũng không thay thế `--add-opens` khi framework cần đọc private member.

## 3. JDK 26 tách quyền đọc khỏi quyền sửa final

Đối với một non-static final field trong lớp thông thường (không phải record class hoặc hidden class), API reflection có thể cho phép đọc sau khi bật accessible. Quyền ghi được kiểm tra riêng tại thời điểm gọi mutation method như `Field.set()`.

Để mutation được xem là hợp lệ trên JDK 26, cần đồng thời đáp ứng:

- `setAccessible(true)` hoặc `trySetAccessible()` đã bật thành công quyền truy cập cho Field.
- Module của caller được cấp quyền final field mutation bằng `--enable-final-field-mutation`.
- Declaring class và caller đáp ứng điều kiện module access: cùng module, hoặc field/class public trong package được export phù hợp, hoặc package của declaring class được open cho module caller.
- Field là non-static và không thuộc nhóm final field không thể sửa.

Vì vậy, một lời gọi `setAccessible(true)` thành công không đảm bảo `Field.set()` sẽ thành công. Tương tự, `--enable-final-field-mutation` không tự cấp quyền đọc private member nếu package không mở.

### Ví dụ đọc được nhưng không có quyền ghi

Giả sử package đã mở cho caller:

```java
Field field = Settings.class.getDeclaredField("endpoint");
field.setAccessible(true);

String value = (String) field.get(settings); // Có thể đọc
field.set(settings, "https://new.example.com"); // Cần quyền mutation riêng
```

Nếu caller chưa được cấp quyền final field mutation, JDK 26 mặc định vẫn cho phép mutation nhưng phát cảnh báo. Khi chạy với chế độ `deny`, lời gọi ghi bị từ chối bằng `IllegalAccessException`.

## 4. Cấp quyền mutation cho đúng module gọi

Tùy cách triển khai, caller có thể thuộc unnamed module (code trên class path) hoặc một named module (code trên module path).

Cho phép code trên class path:

```bash
java --enable-final-field-mutation=ALL-UNNAMED \
     -cp app.jar com.example.Main
```

Cho phép một số named module:

```bash
java --enable-final-field-mutation=app,serializer \
     --module-path mods \
     -m app/com.example.Main
```

Giá trị của `--enable-final-field-mutation` là danh sách module caller được cấp quyền, hoặc `ALL-UNNAMED` cho code trên class path. Cờ này không chỉ định package đích và không làm package tự động mở.

Nếu cần vừa đọc private field vừa ghi final instance field của một module khác, thường phải cấu hình cả hai:

```bash
java \
  --add-opens=model/com.example.model=app \
  --enable-final-field-mutation=app \
  --module-path mods \
  -m app/com.example.Main
```

Trong ví dụ, module `app` là caller cần quyền mutation và package `com.example.model` thuộc module `model` được mở cho `app`. Nếu caller chạy trên class path, thay `app` bằng `ALL-UNNAMED` ở cả hai vị trí phù hợp.

Đây là ngoại lệ tương thích dành cho trường hợp thật sự cần thiết. Không nên bật `ALL-UNNAMED` theo thói quen vì nó cấp khả năng mutation cho toàn bộ code trên class path.

## 5. Những final field không thể sửa bằng Field.set()

Ngay cả khi package đã mở và caller được cấp quyền mutation, một số final field vẫn là non-modifiable final fields. `setAccessible(true)` chỉ mở quyền đọc; mutation method vẫn ném `IllegalAccessException`.

| Loại field | Đọc bằng reflection nếu có quyền truy cập | Ghi bằng `Field.set()` |
|---|---|---|
| `static final` trong class hoặc interface | Có thể | Không |
| Field final được khai báo trong record class | Có thể | Không |
| Field final được khai báo trong hidden class | Có thể | Không |
| Non-static final trong class thông thường | Có thể | Chỉ khi đáp ứng đủ điều kiện truy cập và được cấp quyền mutation |

Ví dụ:

```java
record User(String id, String name) {}

final class RuntimeConfig {
    static final String APPLICATION_NAME = "Inventory";
    private final String region = "ap-southeast-1";
}
```

Các component field của record là final field và không thể được sửa bằng deep reflection. `APPLICATION_NAME` là static final nên cũng không thể sửa. `region` là non-static final trong class thông thường; đây là nhóm field duy nhất trong ví dụ có thể được mutation theo cơ chế opt-in của JDK 26.

Đừng nhầm khả năng sửa final instance field với khả năng sửa static final. Java đã bảo vệ static final khỏi mutation qua các mutation methods này; `--enable-final-field-mutation` không thay đổi điều đó.

## 6. JDK 26 cảnh báo như thế nào?

JDK 26 bắt đầu giai đoạn chuyển tiếp theo JEP 500. Khi code thực hiện final field mutation mà chưa được cấp quyền riêng, chế độ mặc định `warn` vẫn cho phép mutation tiếp tục nhưng phát cảnh báo ở lần mutation đầu tiên của mỗi caller module.

Ví dụ cảnh báo:

```text
WARNING: Final field endpoint in class com.example.model.Settings
has been mutated reflectively by class com.example.mapper.FieldMapper
in unnamed module ...
WARNING: Use --enable-final-field-mutation=ALL-UNNAMED to avoid a warning
WARNING: Mutating final fields will be blocked in a future release unless
final field mutation is enabled
```

Cảnh báo chỉ ra field bị sửa, class thực hiện mutation và module của caller. Với class path, nhiều thư viện có thể cùng nằm trong unnamed module; vì vậy một warning không có nghĩa chỉ có một vị trí mutation. Mặc định chỉ phát tối đa một warning cho mỗi caller module.

Các chế độ của `--illegal-final-field-mutation`:

| Chế độ | Hành vi trong JDK 26 | Mục đích |
|---|---|---|
| `allow` | Cho phép mutation bất hợp lệ mà không cảnh báo | Chỉ nên dùng tạm thời |
| `warn` | Cho phép mutation và cảnh báo lần đầu theo module | Mặc định JDK 26 |
| `debug` | Cho phép mutation, phát cảnh báo và stack trace cho mỗi lần | Tìm chính xác vị trí code vi phạm |
| `deny` | Từ chối mutation bất hợp lệ; `Field.set()` ném `IllegalAccessException` | Kiểm tra sẵn sàng cho mặc định nghiêm ngặt trong tương lai |

`--illegal-final-field-mutation` là tùy chọn chuyển tiếp và dự kiến bị loại bỏ khi chính sách mặc định mới được áp dụng. Trong tương lai, hành vi từ chối mutation sẽ trở thành mặc định. `--enable-final-field-mutation` là cơ chế opt-in có phạm vi rõ ràng cho các module thật sự cần tương thích.

## 7. Vì sao --add-opens không thay thế --enable-final-field-mutation?

Đây là nhầm lẫn phổ biến khi nâng cấp ứng dụng từ JDK cũ.

`--add-opens` chỉ giải quyết quyền truy cập sâu. Nó cho phép reflection vượt qua kiểm tra truy cập Java đối với package được mở. JEP 500 bổ sung một cổng kiểm soát khác: caller phải được cấp quyền sửa final field.

| Cấu hình | Đọc private field | Ghi final instance field thông thường |
|---|---|---|
| Không mở package, không cấp mutation | Không có deep access nếu caller không có quyền thông thường | Không hợp lệ |
| Chỉ `--add-opens` | Có thể đọc | JDK 26 mặc định cảnh báo nhưng vẫn cho phép; chế độ `deny` từ chối |
| Chỉ `--enable-final-field-mutation` | Không tự mở private package | Không đủ nếu caller chưa có quyền truy cập field |
| Mở package và cấp mutation cho caller | Có thể đọc | Hợp lệ nếu field không thuộc nhóm non-modifiable |
| Mở package, cấp mutation nhưng field là static final/record/hidden class final | Có thể đọc | Vẫn không thể sửa |

`Module.addOpens()` ở runtime cũng không cấp quyền ghi final field. API Java 26 nêu rõ việc mở package bằng phương thức này không cho phép module đích lấy method handle có quyền ghi final field. Hãy cấu hình module openness và final mutation capability ngay từ đầu theo đúng phạm vi cần thiết.

## 8. MethodHandles cũng chịu giới hạn final field

JEP 500 không chỉ áp dụng cho `Field.set()`. `MethodHandles.Lookup.unreflectSetter(Field)` là một mutation method và phải đáp ứng điều kiện final field mutation tương tự.

Ví dụ:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Field;

static MethodHandle finalFieldSetter(Field field)
        throws IllegalAccessException {

    field.setAccessible(true);

    return MethodHandles.lookup().unreflectSetter(field);
}
```

Đoạn code chỉ lấy method handle có quyền ghi nếu field và caller đáp ứng đầy đủ điều kiện. Việc tạo handle cũng là hành vi xin quyền mutation; không thể lách JEP 500 bằng cách chuyển từ `Field.set()` sang `MethodHandle`.

Các API đọc như `Field.get()` hoặc getter method handle không phải mutation method. Cần xác định rõ code chỉ đọc hay đang yêu cầu quyền ghi trước khi điều chỉnh module và JVM options.

## 9. Cách tìm thư viện đang sửa final field

Trong thực tế, mutation thường đến từ serializer, dependency injection framework, ORM, mapper, mocking framework hoặc thư viện tái dựng object. Hãy tìm nguyên nhân trước khi cấp quyền toàn cục.

**Cách 1: chạy debug mode**

```bash
java --illegal-final-field-mutation=debug \
     -jar application.jar
```

JDK phát warning và stack trace cho mỗi lần mutation bất hợp lệ. Stack trace giúp xác định thư viện, phương thức và call site cần cập nhật.

**Cách 2: dùng JDK Flight Recorder**

```bash
java -XX:StartFlightRecording=filename=final-fields.jfr \
     -jar application.jar

jfr print --events jdk.FinalFieldMutation final-fields.jfr
```

Sự kiện `jdk.FinalFieldMutation` ghi nhận final instance field bị sửa thông qua deep reflection hoặc việc lấy setter MethodHandle bằng `unreflectSetter()`. Sự kiện cung cấp class khai báo field, tên field, thread và stack trace khi recording có cấu hình ghi stack trace.

Nên chạy kiểm tra trên các luồng chức năng đại diện: khởi động ứng dụng, deserialize dữ liệu, khởi tạo dependency, đọc/ghi database, xử lý request và test tích hợp. Chỉ chạy startup có thể bỏ sót mutation phát sinh ở nhánh nghiệp vụ ít dùng.

## 10. Thay thế mutation bằng thiết kế phù hợp

Không nên giữ final field mutation chỉ để tránh sửa một thư viện cũ. Hãy chọn cách tái cấu trúc theo mục đích thực tế:

| Mục đích cũ | Hướng thay thế |
|---|---|
| Deserialize object bằng cách tạo object rỗng rồi ghi field final | Dùng constructor hoặc factory được serializer hỗ trợ; ưu tiên constructor-based deserialization |
| Dependency injection ghi private final field sau khi tạo object | Inject qua constructor |
| ORM ghi final field sau khi dựng entity | Dùng constructor mapping hoặc cơ chế materialization được framework hỗ trợ |
| Mocking framework sửa final field | Cập nhật framework và dùng extension/mock API được hỗ trợ |
| Test cần thay giá trị cấu hình | Truyền dependency qua constructor hoặc factory trong test |
| Framework phải tái dựng object đặc biệt | Cô lập quyền mutation cho đúng module và đúng use case trong thời gian chuyển đổi |

Final field giúp chương trình có thể dựa vào giá trị không đổi sau khi khởi tạo. Nếu object cần thay cấu hình hoặc trạng thái trong vòng đời, dùng field mutable có kiểm soát, immutable replacement hoặc object mới thay vì phá vỡ hợp đồng final.

## 11. Quy trình nâng cấp và kiểm thử

1. Nâng JDK lên 26 trong môi trường test và giữ cấu hình mặc định để quan sát warning.
2. Chạy toàn bộ test tích hợp và workload đại diện; lưu log warning.
3. Chạy lại với `--illegal-final-field-mutation=debug` để tìm thư viện và call site gây mutation.
4. Cập nhật hoặc thay thư viện có thể tránh mutation; ưu tiên constructor, factory và API chính thức.
5. Nếu còn use case bắt buộc, xác định module caller chính xác và package đích cần mở; cấp `--enable-final-field-mutation` có phạm vi nhỏ nhất.
6. Chạy test với `--illegal-final-field-mutation=deny` cùng các quyền opt-in thực sự cần thiết.
7. Xác nhận không còn mutation ngoài danh sách được chấp thuận; theo dõi JFR và kiểm tra các đường chạy hiếm.
8. Gỡ các cờ chuyển tiếp không còn cần thiết trước khi triển khai production.

Ví dụ kiểm tra nghiêm ngặt cho code class path nhưng không cho phép bất kỳ final mutation bất hợp lệ nào:

```bash
java --illegal-final-field-mutation=deny \
     -jar application.jar
```

Nếu một thư viện vẫn cần mutation hợp lệ trên non-static final field của class thường, phải cấp quyền có chủ đích cho module đó và mở package tương ứng. Chế độ `deny` vẫn từ chối những mutation không nằm trong phạm vi opt-in hoặc thuộc nhóm non-modifiable.

## 12. Những điều cần nhớ khi thiết kế API

- `final` biểu thị trạng thái được cố định sau khởi tạo; không dùng reflection để biến nó thành field mutable.
- Đọc private field và sửa final field là hai quyền khác nhau.
- `setAccessible(true)` bỏ qua kiểm tra truy cập Java khi module/package cho phép; nó không cấp final mutation capability.
- `--add-opens` mở package cho deep reflection; nó không cấp quyền sửa final.
- `--enable-final-field-mutation` cấp capability cho module caller; nó không tự mở package đích.
- Static final, record final và hidden-class final không thể sửa bằng mutation methods.
- `Field.set()` và `Lookup.unreflectSetter()` đều chịu final field restrictions.
- JDK 26 mặc định `warn`; dùng `debug` để truy tìm và `deny` để kiểm tra khả năng tương thích tương lai.
- Không bật `ALL-UNNAMED` hoặc `allow` như một giải pháp lâu dài cho lỗi thư viện.

## Tài liệu tham chiếu

1. [JEP 500 – Prepare to Make Final Mean Final](https://openjdk.org/jeps/500)
2. [Oracle – Preparing for final Field Mutation Restrictions, JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html)
3. [Oracle Java SE 26 API – Field.setAccessible](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Field.html#setAccessible(boolean))
4. [Oracle Java SE 26 API – Field mutation methods](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/doc-files/MutationMethods.html)
5. [Oracle Java SE 26 API – Module.addOpens](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html#addOpens(java.lang.String,java.lang.Module))
6. [Oracle – Significant Changes in JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html)
7. [Inside.java – Quality Outreach Heads-up: JDK 26 Final Field Mutation Warnings](https://inside.java/2026/05/15/quality-heads-up/)

