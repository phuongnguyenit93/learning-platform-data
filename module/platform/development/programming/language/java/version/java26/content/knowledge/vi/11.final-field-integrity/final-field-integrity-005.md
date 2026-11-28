# Giới hạn với static final, record và hidden class

`final` là cam kết rằng một field chỉ được gán trong quá trình khởi tạo hợp lệ. Tuy nhiên, deep reflection từng cho phép một số thư viện thay đổi `final` instance field sau khi constructor đã chạy. Điều này làm suy yếu tính toàn vẹn của object: code có thể tin rằng giá trị không đổi trong khi một thư viện khác âm thầm ghi đè nó.

**JEP 500 — Prepare to Make Final Mean Final** bắt đầu siết việc này từ JDK 26. JDK 26 và JDK 27 cảnh báo khi code dùng deep reflection để sửa các final instance field còn có thể sửa. Một số loại field vốn đã là *non-modifiable* và không thể ghi bằng reflection: `static final` trong mọi class/interface, final field của record và final field của hidden class. Những giới hạn này không thể được bỏ qua bằng `setAccessible`, `--add-opens` hay `--enable-final-field-mutation`.

## 1. Deep reflection và final-field integrity

Reflection thông thường cho phép xem metadata và truy cập thành viên theo quy tắc access control. *Deep reflection* là việc bỏ qua một phần encapsulation để truy cập thành viên private, thường qua `AccessibleObject.setAccessible(true)` hoặc `trySetAccessible()`.

Với một field `final`, cần phân biệt ba hành động:

- **Đọc field:** có thể được cho phép nếu quyền truy cập phù hợp.
- **Bật accessible:** bỏ qua một số kiểm tra truy cập Java; việc này không tự cấp quyền ghi final field.
- **Ghi field:** phải thỏa điều kiện riêng của API Reflection và chính sách final-field mutation của JVM. Một số nhóm field luôn không thể ghi.

Ví dụ một class thông thường:

```java
final class ServiceConfig {
    private final String endpoint;

    ServiceConfig(String endpoint) {
        this.endpoint = endpoint;
    }

    String endpoint() {
        return endpoint;
    }
}
```

Một thư viện có thể tìm field `endpoint`, gọi `trySetAccessible()` rồi gọi `Field.set(...)`. Trước JDK 26, hành vi này có thể thành công nếu các điều kiện truy cập được đáp ứng. Từ JDK 26, lần mutation đầu tiên trong một module sẽ phát cảnh báo theo mặc định. JDK 27 tiếp tục hành vi cảnh báo này.

Mục tiêu của JEP 500 là khôi phục ý nghĩa đáng tin cậy của `final`. Khi JVM có thể tin rằng field không bị thay đổi ngoài quá trình khởi tạo, nó có thêm cơ sở để tối ưu truy cập, đồng thời chương trình dễ suy luận hơn về trạng thái object và tính đúng đắn khi chạy đồng thời.

## 2. Ba nhóm field không thể sửa bằng reflection

Java SE xác định các nhóm sau là *non-modifiable final fields*. Khi `setAccessible(true)` thành công, nó chỉ cho phép đọc field; `Field.set(...)` và các mutation method tương ứng vẫn không được ghi.

| Nhóm field | Ví dụ | Có thể ghi bằng deep reflection? | Vì sao |
| --- | --- | --- | --- |
| `static final` khai báo trong bất kỳ class hoặc interface nào | hằng primitive, `String`, object reference | Không | Giá trị static final được xem là bất biến sau khởi tạo; constant variable còn có thể được compiler inline |
| Field `final` khai báo trong record class | Các field tương ứng với record component | Không | Giá trị record được xác lập qua constructor/canonical constructor; record được thiết kế như aggregate dữ liệu có trạng thái ổn định |
| Field `final` khai báo trong hidden class | Field của class được tạo bằng `Lookup.defineHiddenClass(...)` | Không | Hidden class có thể được runtime/framework tạo và tối ưu với giả định field final không đổi |

`--enable-final-field-mutation` chỉ cấp khả năng sửa một số final instance field của class thông thường. Tùy chọn này không mở quyền ghi cho ba nhóm trên.

### `static final`: cả primitive, String và object reference

```java
final class GlobalSettings {
    static final int DEFAULT_PORT = 443;
    static final String SCHEME = "https";
    static final Object TOKEN = new Object();
}
```

Cả ba field đều không thể được ghi bằng `Field.set(...)`, dù `TOKEN` là object reference chứ không phải constant variable theo JLS. `static final` object reference không thể bị thay bằng một object khác thông qua reflection. Tuy nhiên, nếu object được tham chiếu là mutable, các trạng thái bên trong object vẫn có thể thay đổi qua API của chính object; `final` bảo vệ reference, không tự biến object thành immutable sâu.

Với primitive hoặc `String` được khởi tạo bằng constant expression, compiler có thể inline giá trị tại nơi sử dụng. Do đó, việc cố sửa một static final constant bằng reflection vừa không được phép, vừa không phải cách thay đổi cấu hình hợp lệ.

### Record: tạo instance mới qua constructor

```java
record UserProfile(String id, String displayName) {}

UserProfile original = new UserProfile("u-01", "An");
UserProfile renamed = new UserProfile(original.id(), "Bình");
```

Các field thành phần của record là final và không thể sửa bằng reflection. `setAccessible(true)` không thay đổi điều đó. Nếu cần một giá trị khác, hãy tạo record instance mới qua canonical constructor hoặc một factory/copy method do ứng dụng định nghĩa.

Record không đồng nghĩa với deep immutability: một component có thể trỏ tới collection mutable. Dù vậy, reference component của record vẫn không được thay bằng reflection.

### Hidden class: không dùng reflection để sửa trạng thái final

Hidden class thường được tạo động bởi framework hoặc runtime thông qua `MethodHandles.Lookup.defineHiddenClass(...)`. Hidden class không được tra cứu như class thông thường bằng tên nhị phân; nó hữu ích cho mã được sinh động và implementation nội bộ.

Final field khai báo trong hidden class luôn non-modifiable. Nếu framework cần dữ liệu khởi tạo, hãy truyền dữ liệu vào constructor hoặc factory của hidden class khi tạo instance. Không thiết kế vòng đời object theo giả định có thể tạo instance trước rồi sửa final field bằng reflection.

## 3. `setAccessible(true)` không có nghĩa là được quyền ghi

Ví dụ sau có thể đọc một static final field nếu access control cho phép, nhưng thao tác ghi sẽ thất bại:

```java
import java.lang.reflect.Field;

Field field = GlobalSettings.class.getDeclaredField("DEFAULT_PORT");
field.setAccessible(true);

int current = field.getInt(null); // Đọc được nếu accessible đã bật
System.out.println(current);

field.setInt(null, 8443); // IllegalAccessException: static final không modifiable
```

Với record:

```java
record UserProfile(String id) {}

UserProfile user = new UserProfile("u-01");
Field field = UserProfile.class.getDeclaredField("id");
field.setAccessible(true);

System.out.println(field.get(user));
field.set(user, "u-02"); // IllegalAccessException: record final field không modifiable
```

`setAccessible(true)` có thể tự ném `InaccessibleObjectException` nếu module/package không cho phép mở quyền truy cập. Nếu nó thành công với non-modifiable final field, quyền đó chỉ đủ để đọc; `Field.set` vẫn ném `IllegalAccessException`.

`--add-opens` cũng chỉ mở package để deep reflection có thể truy cập thành viên. Nó không biến `static final`, record field hoặc hidden-class final field thành field có thể ghi.

## 4. So sánh với final instance field của class thông thường

JDK 26 không cấm mọi final field mutation trong mọi trường hợp. Một final instance field của class thường vẫn có thể được ghi bằng deep reflection nếu thỏa tất cả điều kiện sau:

1. `setAccessible(true)` thành công cho `Field`.
2. Mutation được bật cho module của code thực hiện việc ghi.
3. Có cơ sở truy cập phù hợp: class đích và code gọi ở cùng module; hoặc field/class public trong package được export phù hợp; hoặc package khai báo field được open cho module gọi.
4. Field là instance field, không phải `static`.
5. Class khai báo field không phải record class và không phải hidden class.

Nếu một điều kiện không thỏa, `Field.set(...)` ném `IllegalAccessException`. Việc mở package bằng `--add-opens` giải quyết điều kiện encapsulation, còn `--enable-final-field-mutation` cấp khả năng mutation cho module gọi. Hai tùy chọn có mục đích khác nhau.

Ví dụ dưới đây minh họa final instance field trong class thường:

```java
import java.lang.reflect.Field;

final class LegacyConfig {
    private final String endpoint;

    LegacyConfig(String endpoint) {
        this.endpoint = endpoint;
    }

    String endpoint() {
        return endpoint;
    }
}

public class FinalFieldMutationDemo {
    public static void main(String[] args) throws Exception {
        LegacyConfig config = new LegacyConfig("https://old.example");

        Field field = LegacyConfig.class.getDeclaredField("endpoint");
        if (!field.trySetAccessible()) {
            throw new IllegalStateException("Package is not accessible");
        }

        field.set(config, "https://new.example");
        System.out.println(config.endpoint());
    }
}
```

Trên JDK 26/27, nếu mutation chưa được bật cho module gọi, JVM mặc định vẫn cho phép thao tác nhưng phát cảnh báo ở lần đầu tiên trong module đó. Có thể bật có chủ đích cho code trên classpath bằng:

```bash
java --enable-final-field-mutation=ALL-UNNAMED -cp out FinalFieldMutationDemo
```

Với ứng dụng module-path, chỉ định tên module chứa code thực hiện mutation:

```bash
java --module-path mods --enable-final-field-mutation=com.example.migrator -m com.example.app/com.example.Main
```

Nếu field nằm trong package của một module khác, package đó còn phải mở cho module gọi, ví dụ:

```bash
java --module-path mods --enable-final-field-mutation=com.example.migrator --add-opens=com.example.model/com.example.config=com.example.migrator -m com.example.app/com.example.Main
```

Đây là lối tương thích tạm thời cho class thông thường; không áp dụng được cho `static final`, record final field hoặc hidden-class final field. Tài liệu Reflection cũng khuyến nghị chỉ ghi final instance field trong giai đoạn deserialization/tái tạo object có blank final field, trước khi object được công bố cho phần còn lại của chương trình. Sửa field sau khi object đã được sử dụng có thể dẫn tới hành vi khó dự đoán.

## 5. Hai tùy chọn JDK 26/27 có vai trò khác nhau

JDK cung cấp hai tùy chọn liên quan đến final-field mutation:

| Tùy chọn | Phạm vi | Mục đích |
| --- | --- | --- |
| `--enable-final-field-mutation=...` | Cấp khả năng cho module được chỉ định | Cho phép module đó sửa các final instance field đủ điều kiện bằng deep reflection |
| `--illegal-final-field-mutation=...` | Chính sách xử lý mutation không được bật | Cảnh báo, ghi stack trace, cho phép tạm thời hoặc từ chối mutation không được cấp quyền |

Các mode của `--illegal-final-field-mutation`:

| Mode | Hành vi trên JDK 26/27 |
| --- | --- |
| `allow` | Cho phép illegal final field mutation không có cảnh báo |
| `warn` | Cho phép mutation và phát cảnh báo ở lần đầu tiên trong mỗi module; đây là mặc định hiện tại |
| `debug` | Cho phép mutation, phát cảnh báo và stack trace cho từng mutation |
| `deny` | Từ chối mutation không được bật và ném `IllegalAccessException` |

Các mode này không bỏ qua những nhóm field vốn non-modifiable. Ví dụ, chạy với `--illegal-final-field-mutation=allow` cũng không làm `static final`, record field hay hidden-class final field có thể ghi.

JDK 27 tiếp tục mặc định `warn`. Tài liệu launcher cho biết `deny` sẽ trở thành mặc định trong một bản JDK tương lai; tùy chọn `--illegal-final-field-mutation` cũng được dự kiến loại bỏ khi quá trình chuyển đổi hoàn tất. Vì vậy, không nên dùng `allow` như cấu hình production dài hạn.

## 6. Tìm thư viện nào đang sửa final field

Mutation thường đến từ thư viện serialization, dependency injection, ORM, mocking hoặc framework ánh xạ object. Thay vì đoán thư viện nào gây ra, hãy chạy ứng dụng với chế độ `debug`:

```bash
java --illegal-final-field-mutation=debug -jar application.jar
```

JVM phát cảnh báo kèm stack trace cho từng mutation không được bật. Stack trace cho biết thư viện gọi `Field.set(...)` hoặc tạo setter handle từ reflected final field.

Có thể ghi nhận bằng Java Flight Recorder (JFR):

```bash
java -XX:StartFlightRecording:filename=final-field-audit.jfr -jar application.jar
jfr print --events jdk.FinalFieldMutation final-field-audit.jfr
```

Event `jdk.FinalFieldMutation` ghi nhận mutation của final instance field thông qua deep reflection hoặc `Lookup.unreflectSetter(...)` có write access. Event cung cấp class khai báo field, tên field, thread và stack trace để lần về dependency gây mutation.

JFR không biến mutation thành hợp lệ và cũng không ghi nhận một thao tác ghi đã bị từ chối như thể nó thành công. Dùng event để tìm các mutation thực sự diễn ra trong workload đã chạy; chạy đủ các luồng nghiệp vụ, test và đường khởi tạo để tăng độ bao phủ.

## 7. Kiểm tra khả năng tương thích với chế độ deny

Sau khi cập nhật thư viện, chạy test và ứng dụng với:

```bash
java --illegal-final-field-mutation=deny -jar application.jar
```

Nếu ứng dụng vẫn chạy qua các luồng khởi tạo, deserialize và xử lý request, đó là bằng chứng tốt hơn rằng code không còn phụ thuộc vào mutation chưa được cấp quyền. Nếu một module thực sự cần mutation trong giai đoạn chuyển đổi, có thể bật có chọn lọc cho module đó:

```bash
java --module-path mods --enable-final-field-mutation=com.example.legacyserializer --illegal-final-field-mutation=deny -m com.example.app/com.example.Main
```

Kết hợp hai tùy chọn giúp các module đã được phê duyệt tiếp tục hoạt động, trong khi mutation từ module khác bị từ chối. Chỉ dùng opt-in khi không thể cập nhật hoặc thay thế thư viện ngay; ghi lại module, package, field và kế hoạch loại bỏ ngoại lệ.

## 8. Cách thiết kế thay thế

| Nhu cầu cũ | Cách làm phù hợp |
| --- | --- |
| Sửa `static final` để đổi cấu hình sau khi class load | Đưa cấu hình vào object cấu hình được tạo lúc khởi động; dùng dependency injection hoặc immutable configuration snapshot |
| Sửa component của record | Tạo record mới qua canonical constructor hoặc factory/copy method |
| Sửa final field của hidden class | Truyền dữ liệu vào constructor/factory khi tạo hidden-class instance |
| Framework gán final instance field sau constructor | Cập nhật framework để dùng constructor binding, factory hoặc cơ chế deserialization được hỗ trợ |
| Thay đổi trạng thái thường xuyên sau khi object được tạo | Dùng field mutable có encapsulation và đồng bộ phù hợp thay vì khai báo `final` rồi sửa qua reflection |

Không dùng `Unsafe`, native code hoặc MethodHandle khác để lách các giới hạn này. `MethodHandles.Lookup.unreflectSetter(Field)` là một trong các mutation method được tài liệu JDK nêu rõ và cũng chịu chính sách final-field mutation. Chuyển từ `Field.set` sang `unreflectSetter` không giải quyết được vấn đề tương thích.

## Ghi nhớ

- JEP 500 bắt đầu cảnh báo deep-reflective mutation của final instance field từ JDK 26; JDK 27 vẫn mặc định cảnh báo.
- `static final` của mọi class/interface, final field của record và final field của hidden class là non-modifiable; `setAccessible(true)` chỉ cho phép đọc.
- `--enable-final-field-mutation` không mở khóa ba nhóm non-modifiable này.
- Final instance field của class thông thường chỉ có thể ghi khi package/access hợp lệ và module gọi được cấp capability.
- `--add-opens` giải quyết encapsulation; nó không tự cấp quyền sửa final field.
- Dùng `--illegal-final-field-mutation=debug` hoặc JFR event `jdk.FinalFieldMutation` để tìm thư viện gây mutation.
- Chạy với `--illegal-final-field-mutation=deny` để kiểm tra khả năng tương thích với hướng mặc định tương lai.
- Ưu tiên constructor, factory, record copy và immutable configuration thay cho việc sửa final field sau khởi tạo.

## Tài liệu tham khảo

- [JEP 500 — Prepare to Make Final Mean Final](https://openjdk.org/jeps/500) — lộ trình tăng cường tính toàn vẹn của final field.
- [Preparing for final Field Mutation Restrictions, Java SE 26](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html) — cảnh báo, hai tùy chọn launcher, JFR và hướng dẫn migration.
- [Field, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Field.html) — điều kiện write access và danh sách non-modifiable final fields.
- [Mutation Methods, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/doc-files/MutationMethods.html) — `Field.set*` và `Lookup.unreflectSetter`.
- [The `java` Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — `--enable-final-field-mutation` và `--illegal-final-field-mutation`.
- [Significant Changes in JDK 27 Release](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html) — xác nhận cảnh báo final-field mutation vẫn áp dụng trong JDK 27.
- [The `java` Command, Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — mode `warn`/`debug`/`allow`/`deny` và lộ trình chuyển sang deny.
- [JLS 26 §8.10 — Record Classes](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10) — ngữ nghĩa record class và component fields.
