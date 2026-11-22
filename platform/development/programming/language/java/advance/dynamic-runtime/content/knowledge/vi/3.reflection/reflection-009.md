# 3.9. Đọc, ghi field bằng Reflection và phân biệt static, instance, final

Trong Java, **field** là biến được khai báo trong class hoặc interface. Thông thường, mã Java truy cập field theo kiểu tĩnh và quy tắc quyền truy cập khi biên dịch. Reflection (`java.lang.reflect.Field`) cho phép chương trình **tìm metadata của field theo tên lúc chạy**, đọc giá trị hoặc ghi giá trị khi thỏa các điều kiện về kiểu, đối tượng đích, quyền truy cập và tính bất biến.

Điểm quan trọng là **Reflection không làm mọi field trở thành có thể ghi**. Field `static` khác field của từng đối tượng; field `final` có giới hạn riêng; field `private` vẫn chịu kiểm tra truy cập của Java Platform Module System (JPMS). Bài này tập trung vào cách đọc/ghi field một cách đúng đắn trên Java 17+, và cách nhận diện khi nào phải dừng việc ghi.

## 1. Phân biệt field, `Field` và giá trị field

Ví dụ:

```java
class Counter {
    int value = 10;
}
```

`value` là field được khai báo trong `Counter`. `Counter.class.getDeclaredField("value")` trả về một **đối tượng metadata** kiểu `java.lang.reflect.Field`, mô tả khai báo đó: tên, kiểu, modifier và class khai báo. Đối tượng `Field` không phải bản sao của số `10`.

Cùng một `Field` metadata có thể đọc field từ **nhiều instance** khác nhau:

- `Field.get(counterA)` trả về giá trị thuộc `counterA`.
- `Field.get(counterB)` trả về giá trị thuộc `counterB`.
- `Field.set(counterA, newValue)` tác động tới `counterA`, không tự thay đổi `counterB`.

Với `static` field, giá trị thuộc về class đã khai báo (theo bản định nghĩa class được runtime nạp), nên hai instance cùng nhìn thấy một giá trị chung. Một đối tượng `Field` đại diện cho khai báo của field, còn **tham số receiver** quyết định instance nào được đọc/ghi nếu field không phải `static`.

Reflection làm việc trực tiếp với field; nó **không tự gọi getter/setter JavaBeans**. Vì thế, `Field.set` có thể bỏ qua logic xác thực, tính toán, logging hoặc invariant nằm trong `setX(...)`. Chỉ dùng cách truy cập trực tiếp khi có lý do rõ ràng, chẳng hạn framework serialization, mapping hoặc công cụ chẩn đoán.

## 2. Tìm đúng khai báo field

Các API chính:

| API | Kết quả | Điểm dễ nhầm |
| --- | --- | --- |
| `type.getDeclaredField("name")` | Field đúng tên **được khai báo trực tiếp** trong `type`, với mọi mức truy cập | Không tự tìm field được kế thừa từ superclass |
| `type.getField("name")` | Field `public` tìm được theo quy tắc tra cứu public members, bao gồm inherited public fields | Không tìm field private/package-private chỉ vì dùng Reflection |
| `type.getDeclaredFields()` | Mảng các field khai báo trực tiếp, với mọi visibility | Không bảo đảm thứ tự trả về; có thể có field synthetic |
| `type.getFields()` | Mảng public fields mà class/interface phơi ra | Không bảo đảm thứ tự và không trả về private fields |
| `field.getDeclaringClass()` | Class hoặc interface **thật sự khai báo** field | Rất hữu ích khi có kế thừa hoặc field hiding |
| `field.getName()`, `field.getType()` | Tên, kiểu khai báo (`Class<?>`) | `getType()` trả về kiểu đã xóa generic (erasure) khi thích hợp |
| `field.getModifiers()` | Bit mask modifier | Dùng `java.lang.reflect.Modifier` để kiểm tra `static`, `final`, `public`, v.v. |

Ví dụ tư duy: `Parent` có `public int number`, còn `Child extends Parent` không khai báo `number`. `Child.class.getField("number")` tìm được field public thừa kế và `getDeclaringClass()` trả về `Parent.class`. Ngược lại, `Child.class.getDeclaredField("number")` ném `NoSuchFieldException`. Khi cần field private của `Parent`, hãy lấy từ `Parent.class.getDeclaredField(...)`, rồi xem có được phép truy cập hay không.

Nếu `Child` **tự khai báo** thêm một field cùng tên `number`, đó là **field hiding**, không phải override. Hai khai báo là hai field riêng biệt; có thể lấy mỗi `Field` từ class khai báo tương ứng. Field không sử dụng cơ chế virtual dispatch như phương thức instance được override.

## 3. Phân biệt field instance, static và final

| Loại field | Thuộc về | Receiver khi `Field.get`/`set` | Khả năng ghi thông thường |
| --- | --- | --- | --- |
| Instance, không `final` | Từng object | Một object đúng kiểu class khai báo hoặc subtype | Có, nếu qua kiểm tra truy cập và tương thích kiểu |
| `static`, không `final` | Class khai báo | Truyền `null` (quy ước rõ ràng; receiver không được dùng) | Có, nếu có quyền và kiểu tương thích |
| Instance `final` | Từng object | Object thích hợp khi đọc | **Đọc được; tránh sửa bằng Reflection**. Một số trường hợp có thể ghi dưới điều kiện hẹp của JDK, nhưng không bảo đảm ngữ nghĩa ổn định |
| `static final` | Class khai báo | Truyền `null` khi đọc | **Không hỗ trợ sửa bằng `Field.set`**, kể cả khi yêu cầu bỏ kiểm tra access thành công |

Nhận diện modifier bằng API, đừng suy từ tên:

```java
boolean isStatic = java.lang.reflect.Modifier.isStatic(field.getModifiers());
boolean isFinal = java.lang.reflect.Modifier.isFinal(field.getModifiers());
```

Các tổ hợp `static`/`final` là **hai chiều độc lập**: `static` nói giá trị gắn với class hay instance; `final` nói field có thể được gán lại theo quy tắc Java hay không. `private`/`public` là một chiều khác, nói về visibility.

Đối với một field instance, truyền receiver `null` vào `get`/`set` là sai; receiver không thuộc class khai báo hoặc subtype thích hợp cũng không hợp lệ. Đối với field static, dùng `null` giúp biểu thị rõ rằng không có object riêng nào được truy cập. Đọc/ghi static field qua Reflection có thể kích hoạt khởi tạo class khai báo nếu class chưa được khởi tạo.

## 4. Ví dụ hoàn chỉnh Java 17+: đọc/ghi field và kiểm tra modifier

Lưu toàn bộ đoạn sau thành **`FieldAccessDemo.java`**. File có một public class `FieldAccessDemo` và một package-private class `Device` để minh họa rõ việc truy cập field `private` bằng Reflection.

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

class Device {
    static int total = 2;
    int level = 7;
    private String label = "alpha";
    final long id = 101L;
    static final String UNIT = "dB";
}

public class FieldAccessDemo {
    private static void describe(Field field) {
        int modifiers = field.getModifiers();
        String scope = Modifier.isStatic(modifiers) ? "static" : "instance";
        String mutability = Modifier.isFinal(modifiers) ? "final" : "mutable";
        System.out.println(field.getName() + ": " + scope + ", " + mutability);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Device first = new Device();
        Device second = new Device();

        // Instance field: mỗi Device giữ một giá trị riêng.
        Field level = Device.class.getDeclaredField("level");
        System.out.println("instance before: "
                + level.getInt(first) + ", " + level.getInt(second));
        level.setInt(first, 12);
        System.out.println("instance after: "
                + first.level + ", " + second.level);

        // Static field: truyền null, không dùng receiver cụ thể.
        Field total = Device.class.getDeclaredField("total");
        System.out.println("static before: " + total.getInt(null));
        total.setInt(null, 5);
        System.out.println("static after: " + Device.total);

        // Private field: yêu cầu cho phép bỏ kiểm tra visibility.
        Field label = Device.class.getDeclaredField("label");
        if (!label.trySetAccessible()) {
            throw new IllegalStateException("Cannot access label");
        }
        System.out.println("private before: " + label.get(first));
        label.set(first, "beta");
        System.out.println("private after: " + label.get(first));

        // Final fields: chỉ đọc, không thử ghi.
        Field id = Device.class.getDeclaredField("id");
        Field unit = Device.class.getDeclaredField("UNIT");

        describe(level);
        describe(total);
        describe(id);
        describe(unit);
        System.out.println("final values: "
                + id.getLong(first) + ", " + unit.get(null));
    }
}
```

Chạy trong một thư mục trống bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 FieldAccessDemo.java
java FieldAccessDemo
```

Kết quả dự kiến trên classpath thông thường (unnamed module):

```text
instance before: 7, 7
instance after: 12, 7
static before: 2
static after: 5
private before: alpha
private after: beta
level: instance, mutable
total: static, mutable
id: instance, final
UNIT: static, final
final values: 101, dB
```

Giải thích:

1. `level` thuộc từng instance: `setInt(first, 12)` chỉ đổi `first.level`; `second.level` vẫn `7`. Đây là instance field bình thường, **không liên quan đến override**.
2. `total` thuộc class `Device`: `getInt(null)` đọc giá trị chung và `setInt(null, 5)` cập nhật giá trị chung. Không cần tạo object chỉ để truy cập static field.
3. `label` là private. `getDeclaredField` **tìm được metadata** không có nghĩa đã được phép đọc/ghi. Trong ví dụ nằm trên classpath, hai class thuộc unnamed module, nên `trySetAccessible()` có thể cấp quyền truy cập sâu; trong named module khác, kết quả có thể bị từ chối.
4. `id` là instance `final`, đọc với `first`; `UNIT` là `static final`, đọc với `null`. Không có lệnh ghi vào bất kỳ final field nào.
5. `describe` dùng modifier từ metadata, không suy đoán từ cách khai báo biến `Field`.

Mã minh họa trực tiếp sử dụng field package-private (`level`, `total`) vì cả hai class cùng package. Nếu class khai báo nằm ở package/module khác, đừng mặc định reflective access vẫn được phép.

## 5. `get`/`set` và các biến thể cho primitive

`Field.get(Object receiver)` trả về `Object`:

- Với field kiểu tham chiếu (`String`, `List`, ...), giá trị thường là reference tương ứng hoặc `null`.
- Với primitive (`int`, `boolean`, `double`, ...), giá trị được boxing thành wrapper khi trả về dưới dạng `Object`.
- Với field `static`, truyền `null` làm receiver.
- Với field instance, truyền object có class tương thích với class khai báo field.

`Field.set(Object receiver, Object value)` ghi vào field khi writable, quyền truy cập hợp lệ, và có chuyển đổi kiểu được API cho phép. Với primitive, có thể truyền wrapper phù hợp rồi Reflection thực hiện unboxing/chuyển đổi mở rộng hợp lệ. Không có phép ép kiểu thu hẹp (narrowing) tùy ý; không thể gán `String` vào field `int` bằng `set` rồi hy vọng Java tự phân tích chuỗi.

API chuyên biệt tránh boxing khi đọc/ghi primitive:

| Kiểu field | Đọc | Ghi khi không `final` và có quyền |
| --- | --- | --- |
| `int` | `getInt(receiver)` | `setInt(receiver, intValue)` |
| `long` | `getLong(receiver)` | `setLong(receiver, longValue)` |
| `boolean` | `getBoolean(receiver)` | `setBoolean(receiver, booleanValue)` |
| `double` | `getDouble(receiver)` | `setDouble(receiver, doubleValue)` |
| Kiểu tham chiếu | `get(receiver)` | `set(receiver, value)` |

Chọn accessor đúng kiểu field. Các getter/setter primitive có một số quy tắc **widening conversion** được API hỗ trợ; chúng **không** tự động hỗ trợ narrowing conversion. Trước khi ánh xạ một chuỗi cấu hình sang số, hãy parse và validate giá trị riêng; Reflection không thay thế bước chuyển đổi dữ liệu.

Nếu có metadata từ nguồn không tin cậy, nên kiểm tra trước:

```java
Class<?> declaredType = field.getType();
Class<?> owner = field.getDeclaringClass();
boolean staticField = Modifier.isStatic(field.getModifiers());
boolean finalField = Modifier.isFinal(field.getModifiers());
```

Đây là **đoạn minh họa rời**, sử dụng biến `field` đã có, không phải chương trình độc lập. Với field tham chiếu, có thể dùng `declaredType.isInstance(value)` khi `value != null` để sàng lọc kiểu gán; `null` chỉ phù hợp với field tham chiếu. Với primitive, tự chuẩn hóa kiểu/giá trị thay vì coi `isInstance` là quy tắc đầy đủ.

## 6. Quyền truy cập: tìm thấy field ≠ đọc/ghi được

Một số khái niệm cần tách rõ:

- **Discovery:** `getDeclaredField("label")` lấy metadata, kể cả private field; nếu tên không tồn tại trong đúng class khai báo, ném `NoSuchFieldException`.
- **Access check:** `field.get(...)` và `field.set(...)` vẫn kiểm tra người gọi có quyền truy cập hay không nếu chưa bỏ kiểm tra language access. Truy cập không hợp lệ có thể ném `IllegalAccessException`.
- **Suppress access checks:** `field.trySetAccessible()` cố bật quyền truy cập sâu và trả về `true`/`false`; `field.setAccessible(true)` có thể ném `InaccessibleObjectException` nếu module không cho phép. Đây không phải một cơ chế phá vỡ mọi boundary.
- **Module boundary:** với **named modules** trên Java 17+, `exports` thường liên quan việc sử dụng public API từ module khác; để Reflection truy cập sâu vào non-public members ở module khác, package cần được **opens** theo quan hệ module phù hợp (hoặc cơ chế được runtime cho phép). `exports` không đồng nghĩa `opens`.

`field.canAccess(receiver)` giúp kiểm tra khả năng truy cập hiện tại từ caller, nhưng cũng yêu cầu argument phù hợp: `null` cho static và object đúng kiểu cho instance. Nó không thay thế kiểm tra visibility/module. Quyền truy cập sâu còn chịu chính sách bảo mật của môi trường; `trySetAccessible()` có thể không thành công.

Khi làm framework, ưu tiên `public` API hoặc `opens` được cấu hình chủ ý. Đừng lấy việc gọi `setAccessible(true)` thành công trên chương trình classpath làm bằng chứng rằng ứng dụng modular hoặc JDK internals sẽ hoạt động giống vậy.

### Ví dụ lỗi thường thấy ở named module

Một thư viện khai báo package chứa private field nhưng **chỉ `exports`**, không `opens`, thì code Reflection ở module khác có thể lấy một số metadata nhưng không thể bỏ kiểm tra access để đọc/ghi private field. Khi đó:

- `trySetAccessible()` thường trả về `false` nếu không có quyền mở package.
- `setAccessible(true)` có thể ném `InaccessibleObjectException`.
- Thay vì tự động thêm quyền truy cập toàn cục, hãy xem lại module descriptor (`opens package.name to module.name;`) hoặc chuyển sang public accessor phù hợp.

Thông báo lỗi module thường chỉ rõ package nào chưa được mở và module người gọi nào cần quyền. Chỉ cấu hình mở đúng package cho thành phần thực sự cần quyền; không nên coi mọi field private là hợp đồng công khai cho ứng dụng phụ thuộc.

## 7. Vì sao `final` phải được xử lý riêng?

`final` ngăn phép gán lại field theo mô hình Java thông thường sau khi đã được khởi tạo đúng quy tắc. Reflection có những chi tiết lịch sử cho phép ghi **một số** instance final fields trong điều kiện hạn chế, nhưng đó không phải lựa chọn để cập nhật trạng thái ứng dụng:

- **`static final`** được coi là non-modifiable final field đối với `Field.set`; không thể dùng `setAccessible(true)` để biến nó thành field writable.
- **Instance final** chỉ có thể ghi phản chiếu trong các trường hợp rất hẹp, khi access checks có thể được bỏ và runtime cho phép. Field final của **record** hoặc **hidden class** cũng thuộc nhóm không thể sửa bằng cơ chế này.
- Nếu một final field đã được công bố tới thread khác, việc thay đổi sau khởi tạo có thể phá vỡ giả định về an toàn khởi tạo và visibility. JVM/JIT có thể tối ưu dựa trên tính final; đừng suy rằng mọi lần đọc sau đó đều thấy cùng một giá trị vừa ghi.
- **Compile-time constant** là trường hợp đặc biệt: `static final` primitive hoặc `String` được gán constant expression có thể được inline vào bytecode của code tiêu thụ. Ngay cả ý định cưỡng ép đổi giá trị bằng thủ thuật ngoài `Field.set` cũng có thể tạo kết quả không nhất quán.

Vì vậy, quy tắc thực hành là **đọc final field nếu được phép, không ghi final field bằng Reflection**. Khi cần thay giá trị, thiết kế object mutable với API rõ ràng hoặc tạo object mới. Với dữ liệu bất biến, ưu tiên constructor, builder hoặc record constructor, không vá trạng thái bằng Reflection sau khi object được sử dụng.

## 8. Lỗi runtime phổ biến khi thao tác field

| Triệu chứng / exception | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `NoSuchFieldException` | Sai tên hoặc gọi `getDeclaredField` trên subclass trong khi field được khai báo ở superclass | Kiểm tra `getDeclaringClass`, vị trí khai báo và tên chính xác |
| `IllegalAccessException` | Không đủ quyền đọc/ghi field; hoặc cố ghi field bị bảo vệ | Kiểm tra visibility, module openness, modifier `final`; ưu tiên API công khai |
| `InaccessibleObjectException` | Cố suppress access checks nhưng package/module không cho phép | Mở package có chủ đích nếu thiết kế yêu cầu, hoặc bỏ deep reflection |
| `IllegalArgumentException` | Receiver không đúng class, hoặc giá trị/kiểu accessor không tương thích với field | Kiểm tra `getType`, `isStatic` và chuyển đổi dữ liệu trước |
| `NullPointerException` | Dùng receiver `null` cho thao tác instance field, hoặc lỗi dereference trong code gọi | Truyền đúng object cho instance field; `null` chỉ dành cho static |
| `SecurityException` | Chính sách bảo mật hoặc kiểm tra quyền cản trở một thao tác reflective | Thiết kế lại phạm vi quyền, không bỏ qua exception |
| Giá trị đọc không giống kỳ vọng | Đang đọc field bị ẩn (field hiding), static field chung, hoặc dựa vào final bị cưỡng ép sửa | In `getDeclaringClass`, `getModifiers`; kiểm tra class thực tế và cách khởi tạo |

**Khác với `Method.invoke`:** đọc/ghi field bằng `Field.get`/`set` không có cơ chế wrap exception từ một thân phương thức đích bằng `InvocationTargetException`, bởi không có method body được invoke. Tuy nhiên, việc truy cập static field có thể liên quan khởi tạo class và xuất hiện lỗi khởi tạo riêng. Không dùng cùng một bộ xử lý exception cho mọi API Reflection mà không phân biệt nguồn gốc lỗi.

## 9. Field hiding và kế thừa: đừng nhầm với dynamic dispatch

Giả sử `Parent` khai báo `public int score = 1`, còn `Child extends Parent` cũng khai báo `public int score = 2`. Hai field này **cùng tên nhưng khác khai báo**. Với một object `Child`:

- `Parent.class.getDeclaredField("score").getInt(child)` đọc field của `Parent`, kết quả `1`.
- `Child.class.getDeclaredField("score").getInt(child)` đọc field của `Child`, kết quả `2`.
- `Field` không tự chọn field theo lớp runtime của receiver như cơ chế override phương thức.

Ví dụ này giả định hai class và field public được khai báo đúng như mô tả. Điều này cũng giải thích vì sao nên tránh field hiding: hai giá trị cùng tên rất dễ gây nhầm lẫn khi serialize, map dữ liệu hoặc debug. Nếu framework quét toàn bộ hierarchy bằng `getDeclaredFields`, cần nhận diện trùng tên bằng **declaring class + field name**, không đơn giản chỉ bằng tên.

## 10. Cách dùng Reflection field an toàn trong ứng dụng thực tế

Một luồng thao tác đáng tin:

1. **Xác định hợp đồng dữ liệu:** field phải thuộc class nào, tên gì, kiểu nào, có được phép thay đổi hay không. Đừng để dữ liệu ngoài chọn tùy ý private field theo tên.
2. **Tìm đúng khai báo:** ưu tiên `getDeclaredField` khi biết chính xác owner; nếu muốn truy cập public field kế thừa thì dùng `getField`.
3. **Kiểm tra metadata:** `Modifier.isStatic` để chọn receiver `null` hay object; `Modifier.isFinal` để chặn ghi; `getType()` để kiểm tra giá trị.
4. **Kiểm tra quyền truy cập:** ưu tiên public API. Nếu deep reflection thật sự cần, dùng `trySetAccessible()` và có nhánh xử lý khi bị từ chối; hiểu rõ ranh giới module.
5. **Đọc/ghi đúng kiểu:** dùng `get`/`set` cho reference hoặc accessor primitive phù hợp; validate giá trị trước khi ghi.
6. **Giữ invariant và thread-safety:** nếu field được quản lý bởi setter, lock, volatile, atomic hoặc framework lifecycle, không tự ý bỏ qua cơ chế đó. Reflection không tự tạo synchronization.
7. **Xử lý lỗi có ngữ cảnh:** báo tên field, class khai báo và thao tác read/write; không làm rò dữ liệu nhạy cảm từ giá trị field ra log.

Với hệ thống cần truy cập field thường xuyên hoặc cần các access mode về bộ nhớ/concurrency, `VarHandle` trong `java.lang.invoke` là một lựa chọn đáng nghiên cứu. Tuy nhiên, nó vẫn có yêu cầu access và kiểu rõ ràng; nó không biến final field thành mutable field. Với phần lớn business logic, constructor/getter/setter/interface vẫn dễ kiểm tra và bảo trì hơn Reflection.

## 11. Tự kiểm tra nhanh

1. Một `Field` lấy từ `Device.class.getDeclaredField("level")` có thể đọc từ `first` và `second` không? **Có**, vì metadata là chung cho khai báo; mỗi instance giữ giá trị riêng.
2. `getInt(null)` đúng với `level` không? **Không**, đó là instance field. `null` phù hợp với `total` là static field.
3. `getDeclaredField("x")` có tự tìm private field `x` trong superclass không? **Không**, cần tìm trên class khai báo.
4. `getDeclaredField("label")` thành công nghĩa là `Field.get` chắc chắn chạy được? **Không**, metadata discovery và access checks là hai chuyện khác nhau.
5. `trySetAccessible()` luôn trả `true` nếu biết đúng tên private field? **Không**, JPMS và chính sách truy cập có thể chặn.
6. `static final String UNIT` có thể được sửa ổn định bằng `Field.set(null, "...")` không? **Không**; `static final` không writable bằng API này và constant inlining càng làm việc sửa cưỡng ép nguy hiểm.
7. Field `score` của `Parent` có tự dispatch thành field `score` của `Child` khi receiver là `Child` không? **Không**; `Field` trỏ đến khai báo xác định, field hiding không phải method overriding.
8. Reflection `Field.set` có tự gọi setter chứa validation không? **Không**, nó ghi trực tiếp vào field khi được phép.

**Ghi nhớ:** xác định **class khai báo → tìm `Field` → kiểm tra `static`/`final`/type → xác định receiver → kiểm tra access/module → `get` hoặc `set` hợp lệ**. Với static field, receiver là `null`; với instance field, phải có object phù hợp; với final field, ưu tiên chỉ đọc. Đây là ranh giới quan trọng nhất để Reflection phục vụ chương trình mà không phá vỡ tính đúng đắn của object.