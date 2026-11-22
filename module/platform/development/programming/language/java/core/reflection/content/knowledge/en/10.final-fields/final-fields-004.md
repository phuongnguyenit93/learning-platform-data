# Final field trong record và hidden class: giới hạn Reflection ở Java 17+

## 1. Vấn đề cần hiểu

Một sai lầm khi học Java Reflection là cho rằng: **nếu `Field.setAccessible(true)` thành công thì bất kỳ trường `final` nào cũng có thể bị sửa**. Điều này **không đúng**.

Kể từ Java 17 (và trong các API tương ứng đã có ở những phiên bản trước), Java phân biệt một nhóm **non-modifiable final fields**. Ba nhóm quan trọng theo tài liệu `java.lang.reflect.Field` và `AccessibleObject` là:

1. Mọi trường `static final` được khai báo ở bất kỳ class/interface nào.
2. Mọi trường `final` được khai báo trong **record class**.
3. Mọi trường `final` được khai báo trong **hidden class**.

Với nhóm này, kể cả khi mã gọi đã bật thành công quyền truy cập sâu bằng `setAccessible(true)` hoặc `trySetAccessible()`, Reflection chỉ có thể **bỏ qua kiểm tra quyền truy cập để đọc**; nó **không cấp quyền ghi** lên trường đó.

Ví dụ ý tưởng:

```java
Field field = SomeRecord.class.getDeclaredField("name");
field.setAccessible(true);      // Có thể thành công nếu module cho phép.
Object value = field.get(obj);  // Có thể đọc được.
field.set(obj, "changed");      // IllegalAccessException: final field không sửa được.
```

Đây là các dòng minh họa cần có định nghĩa `SomeRecord` và đối tượng `obj` tương ứng, không phải chương trình Java độc lập. Chương trình biên dịch/chạy đầy đủ ở mục 7 sẽ chứng minh quy tắc bằng cả record và hidden class.

Bài này tập trung vào **quyền ghi của `Field` khi declaring class là record hoặc hidden class**. Cần phân biệt với hai khái niệm khác: các mức truy cập Java (`private`/`public`) và field hiding (lớp con khai báo trường trùng tên với lớp cha). **Hidden class** là loại class do runtime định nghĩa theo cơ chế riêng; nó không có nghĩa “field bị class khác che khuất”.

## 2. Tại sao `final` quan trọng, và vì sao Reflection có ngoại lệ?

### 2.1. `final` trong lập trình Java thông thường

Trường instance `final` thường được gán khi khởi tạo đối tượng và không thể gán lại bằng cú pháp Java thông thường sau khi đã khởi tạo hợp lệ. Ví dụ:

```java
final class Ticket {
    private final String code;

    Ticket(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}
```

`Ticket.code` là trường `private final`: phía bên ngoài không được gán bằng `ticket.code = "x"`. Điều đó không nhất thiết có nghĩa **mọi** thao tác phản chiếu vào mọi trường final instance thông thường đều bị cấm ở cấp API.

Trên Java 17, tài liệu `Field.set` vẫn ghi nhận trường hợp rất hẹp mà Reflection có thể ghi một **instance final field trong lớp thông thường** khi `setAccessible(true)` đã thành công. Việc đó chủ yếu có ý nghĩa trong quy trình khôi phục/deserialization đối tượng có blank final field **trước khi** đối tượng được công bố cho phần khác của chương trình. Nếu thay đổi final field sau đó, kết quả quan sát có thể không dự đoán được vì tối ưu hóa và các bảo đảm đặc biệt của mô hình bộ nhớ Java.

**Không dùng khả năng lịch sử này làm cơ sở thiết kế API sửa immutable object.** Quy tắc record và hidden class còn chặt hơn: trường `final` do các class này khai báo là **non-modifiable**, dù kiểm tra truy cập đã được bỏ qua thành công.

### 2.2. Cùng là `final` nhưng điều kiện ghi khác nhau

| Declaring class / loại field | Có thể xin bypass kiểm tra quyền để đọc? | `Field.set(...)` có được ghi field `final`? |
|---|---|---|
| Trường `static final` trong class/interface bất kỳ | Có, nếu được runtime cho phép | **Không** |
| Trường instance `final` khai báo ở `record` | Có, nếu được runtime cho phép | **Không** |
| Trường `final` khai báo ở `hidden class` | Có, nếu được runtime cho phép | **Không** |
| Trường instance `final` của class thông thường, không phải record/hidden | Có, tùy quyền/module | Trên Java 17 có điều kiện hỗ trợ rất hẹp khi suppress access checks; không nên dùng để cập nhật đối tượng đang hoạt động |
| Trường instance **không** `final` | Có, tùy quyền/module | Có thể ghi nếu các điều kiện khác (receiver, kiểu dữ liệu, quyền...) hợp lệ |

Bảng diễn tả hành vi của **Java 17 Reflection API**; nó không bảo đảm quyền truy cập thành công giữa các named modules hoặc quyền ghi vào những loại field không final. Với instance field, receiver phải là đối tượng tương thích; với static field, `Field.set` bỏ qua receiver và có thể truyền `null`.

Lưu ý phạm vi quy tắc: ở **hidden class**, chỉ **field có modifier `final`** thuộc nhóm không được phép ghi; các field không final trong hidden class không tự động trở thành bất biến chỉ vì class là hidden.

## 3. Record: component tạo ra private final field

### 3.1. Record là gì trong phạm vi bài này?

Record là dạng khai báo class dành cho dữ liệu có cấu trúc; các **record components** nằm trong header. Ví dụ:

```java
record UserId(long value, String source) {
}
```

Với `UserId`, compiler tạo ra các thành phần tương ứng với record component, trong đó có:

- Hai **private final instance fields** tương ứng với `value` và `source`.
- Hai accessor methods `value()` và `source()`.
- Canonical constructor nhận các tham số tương ứng với record header (nếu không tự khai báo hình thức hợp lệ khác).
- Các triển khai cho `equals`, `hashCode` và `toString` theo contract của record.

Record là một class `final`, không thể làm superclass để kế thừa theo cách thông thường, và record không được tùy ý khai báo thêm instance fields ngoài những trường tương ứng với components theo luật ngôn ngữ. Record có thể có static fields và methods riêng. Các component field là `private final` bất kể syntax header chỉ ghi `record UserId(long value, ...)`.

Record cung cấp **shallow immutability** ở mức component references: không thể gán lại component field sau khi khởi tạo, nhưng nếu một component giữ tham chiếu tới đối tượng mutable như `List`, trạng thái bên trong đối tượng được tham chiếu vẫn có thể thay đổi nếu không được sao chép/bảo vệ. Bất biến của field và bất biến sâu của toàn bộ object graph là hai điều khác nhau.

### 3.2. Reflection thấy record field như thế nào?

`Class.isRecord()` trả `true` với record class. Đối tượng `Class` còn hỗ trợ `getRecordComponents()` để liệt kê các component ở mức semantic của record.

```java
record UserId(long value, String source) {}

Class<?> type = UserId.class;
System.out.println(type.isRecord());        // true

Field field = type.getDeclaredField("source");
System.out.println(field.getName());        // source
System.out.println(Modifier.isFinal(field.getModifiers())); // true
```

Đoạn ví dụ này giả định các import `java.lang.reflect.Field` và `java.lang.reflect.Modifier`, và có xử lý `NoSuchFieldException`. Nó minh họa việc tìm metadata mà chưa thực hiện đọc/ghi giá trị.

Có hai con đường đọc thông tin:

- **Theo API record:** `userId.source()` hoặc method accessor trả giá trị; đây là cách thuận tiện trong code ứng dụng.
- **Theo Reflection:** `getDeclaredField("source")` rồi `Field.get(userId)` nếu quyền truy cập cho phép.

Dùng `getRecordComponents()` khi muốn biết **record components theo đúng thứ tự khai báo**, loại dữ liệu, accessor và annotation liên quan. Dùng `getDeclaredFields()` khi thực sự cần metadata của các trường: một record còn có thể có trường static không phải component. Không giả định `getDeclaredFields()` bằng `getRecordComponents()` theo cả nội dung lẫn thứ tự.

### 3.3. Tại sao `setAccessible(true)` không sửa record component?

Giả sử có record:

```java
record Person(String name, int age) {}
```

`name` và `age` là những final fields do record class khai báo. Dù có metadata và quyền truy cập phù hợp:

```java
Person p = new Person("An", 25);
Field nameField = Person.class.getDeclaredField("name");

if (nameField.trySetAccessible()) {
    System.out.println(nameField.get(p)); // An
    nameField.set(p, "Bình");             // IllegalAccessException
}
```

Đây là đoạn minh họa trong ngữ cảnh đã import `Field` và xử lý checked exceptions. `trySetAccessible() == true` chỉ cho thấy runtime cho phép **bỏ qua kiểm tra mức truy cập**. Nó không biến final field trong record thành writable.

**Cách đúng khi cần giá trị mới** là tạo instance record mới thông qua constructor/factory hợp lệ:

```java
Person updated = new Person("Bình", p.age());
```

Record là một cách truyền dữ liệu theo giá trị component, không phải cơ chế cập nhật trường riêng lẻ sau khởi tạo. Nếu lưu record trong một collection/map, hãy thay reference tới record bằng instance mới theo thiết kế của ứng dụng.

## 4. Hidden class: runtime định nghĩa class nhưng không cho ghi final field

### 4.1. Hidden class không phải private class

**Hidden class** được giới thiệu qua cơ chế Java runtime/Method Handles, phục vụ triển khai động (chẳng hạn những class nội bộ do framework hoặc runtime tạo), nơi class không cần được tìm qua tên nhị phân theo cơ chế bình thường.

Các điểm khác với class khai báo và nạp thông thường:

- Có thể được định nghĩa từ class-file bytes qua `MethodHandles.Lookup.defineHiddenClass(byte[], boolean, ClassOption...)`.
- `Class.isHidden()` trả `true` với hidden class.
- Hidden class **không được phát hiện bằng cơ chế tra cứu thông thường dựa trên binary name**, ví dụ không thể dựa vào `Class.forName(className)` để tìm hidden class theo cách tìm class thông thường.
- Nó vẫn có đối tượng `Class<?>`, có constructors, methods và fields mà code giữ tham chiếu tới class có thể dùng Reflection/Method Handles để khảo sát.
- Hidden class được định nghĩa trong ngữ cảnh package/module/lookup phù hợp và có những quy tắc riêng về discoverability, liên kết và vòng đời; không tự động đồng nghĩa với `private` hoặc với việc mã ngoài không thể cầm `Class<?>` của nó.

Hidden class khác hoàn toàn với:

- **Nested class**: class khai báo bên trong class khác.
- **Anonymous class**: class không có tên đơn giản trong source.
- **Field hiding**: class con định nghĩa field cùng tên với class cha.
- **`private` member/class**: quyền truy cập ngôn ngữ.

Một nested class bình thường **không tự động là hidden class**; ví dụ `Outer.Inner.class.isHidden()` thông thường trả `false`. Muốn có hidden class thật sự phải sử dụng cơ chế định nghĩa phù hợp hoặc được runtime/framework tạo.

### 4.2. Tại sao final field của hidden class không sửa được?

Java Reflection coi mọi `final field` **khai báo trong hidden class** là non-modifiable. Điều kiện “hidden” áp dụng cho **declaring class của field**: hãy kiểm tra `field.getDeclaringClass().isHidden()` thay vì chỉ xem class của object đang được truyền làm receiver.

```java
Field f = hiddenClass.getDeclaredField("token");

System.out.println(f.getDeclaringClass().isHidden()); // true
System.out.println(Modifier.isFinal(f.getModifiers())); // true
```

Nếu `token` là final, dù `f.setAccessible(true)` thành công theo điều kiện truy cập, `f.set(hiddenObject, "new")` sẽ ném `IllegalAccessException`. Dòng này minh họa metadata; cách tạo hidden class và `hiddenObject` đầy đủ sẽ có ở mục 7.

Ràng buộc này giúp runtime dựa vào ý nghĩa ổn định của các trường final trong class được tạo động. Các class động thường tham gia thực thi tối ưu hóa hoặc liên kết đặc biệt, nên việc cho phép Reflection tự ý gán lại những giá trị final đã khởi tạo sẽ phá vỡ giả định triển khai.

Đối với **non-final field** khai báo trong hidden class, việc có thể `Field.set` hay không vẫn phải xét quyền truy cập, receiver và kiểu dữ liệu. Không coi `isHidden()` là một lệnh cấm tất cả thao tác với field.

### 4.3. Khởi tạo hidden class và sử dụng class-file bytes

`Lookup.defineHiddenClass` yêu cầu:

- Class-file bytes hợp lệ, phù hợp với package của lookup class và các ràng buộc của API.
- Một `MethodHandles.Lookup` có đủ quyền (full privilege access).
- Lựa chọn khởi tạo và các `ClassOption` nếu cần. `NESTMATE` cho phép định nghĩa hidden class là nestmate của lookup class theo API.

API trả một `Lookup` tương ứng với hidden class đã định nghĩa; `lookupClass()` lấy đối tượng `Class<?>` của hidden class đó. Chỉ gọi `Class.isHidden()` trên **class thực sự trả về từ `defineHiddenClass`** mới kiểm tra đúng trường hợp này. Không đánh đồng template class mà mình dùng để lấy bytes với hidden class mới được VM định nghĩa.

## 5. Quyền truy cập và quyền ghi là hai điều kiện độc lập

### 5.1. `trySetAccessible` có ý nghĩa gì?

`Field` kế thừa `AccessibleObject`. Một số API thường gặp:

| API | Vai trò |
|---|---|
| `field.canAccess(receiver)` | Hỏi hiện tại có thể truy cập field bằng receiver phù hợp không; không đổi trạng thái |
| `field.trySetAccessible()` | Thử bật access-check suppression; trả boolean thành công/thất bại |
| `field.setAccessible(true)` | Yêu cầu bật access-check suppression; có thể ném `InaccessibleObjectException` nếu không được mở |
| `field.get(receiver)` | Đọc giá trị khi được phép |
| `field.set(receiver, value)` | Yêu cầu ghi giá trị, còn chịu các hạn chế riêng cho final field |

Với final field non-modifiable, `setAccessible(true)` **không bật khả năng ghi**. Đây không phải mâu thuẫn: **bỏ qua kiểm tra quyền truy cập Java** và **được phép sửa trường final** là hai điều kiện khác nhau.

Một trình tự điển hình:

```text
getDeclaredField(...)                    -> Field metadata
   |
   +-- trySetAccessible() == false       -> không mở được access-check suppression
   |
   +-- trySetAccessible() == true        -> có thể bypass Java access checks
           |
           +-- get(receiver)             -> có thể đọc
           |
           +-- set(receiver, newValue)
                  |
                  +-- field final trong record/hidden?
                         |
                         +-- Có          -> IllegalAccessException
                         +-- Không       -> xét tiếp static final, loại field,
                                          receiver, kiểu dữ liệu, điều kiện khác
```

Sơ đồ chỉ minh họa nhánh quyền ghi liên quan bài học, không liệt kê mọi ngoại lệ/validation của Reflection. Một lần `get` còn có thể thất bại nếu receiver sai hoặc chương trình gọi không có quyền; một lần `set` vào trường không final cũng cần kiểm tra kiểu và receiver.

### 5.2. Module boundary vẫn có hiệu lực

Java Platform Module System (JPMS) có cơ chế strong encapsulation. Với class ở named module khác, `trySetAccessible()` có thể trả `false` nếu package không `opens` thích hợp cho module của caller. Khi `setAccessible(true)` không thể bật, nó có thể ném `InaccessibleObjectException`.

Với code ví dụ chạy trên classpath trong **unnamed module**, gọi `trySetAccessible()` trên private field cùng module có thể thành công. Nhưng không nên suy rộng rằng mọi framework truy cập private field của mọi module đều thành công.

Điểm rất quan trọng: **kể cả package đã được `opens` đầy đủ**, field `final` do record hoặc hidden class khai báo vẫn không trở thành writable bằng `Field.set`.

## 6. Quy tắc chính xác của `Field.set` trên Java 17

Theo hợp đồng của `Field.set(Object, Object)`, một field final chỉ có thể được cấp quyền ghi theo đường Reflection này nếu đồng thời thỏa tất cả điều kiện:

1. `setAccessible(true)` (hoặc `trySetAccessible` thành công với hiệu quả tương đương) đã bật suppression trên **chính đối tượng `Field` đó**.
2. Field **không phải `static`**.
3. Declaring class của field **không phải hidden class**.
4. Declaring class của field **không phải record class**.

Nếu một trong các điều kiện trên không thỏa, `Field.set` ném `IllegalAccessException` cho final field. Những điều kiện này tách biệt khỏi kiểm tra object receiver và khả năng chuyển kiểu giá trị đầu vào.

| Kiểm tra | Ví dụ | Kết luận |
|---|---|---|
| `Modifier.isFinal(f.getModifiers())` | `true` | Field có modifier final |
| `Modifier.isStatic(f.getModifiers())` | `true` | Final + static là non-modifiable |
| `f.getDeclaringClass().isRecord()` | `true` | Final field trong record là non-modifiable |
| `f.getDeclaringClass().isHidden()` | `true` | Final field trong hidden class là non-modifiable |
| `f.trySetAccessible()` | `true` | Có thể suppression access checks; **không** suy ra quyền ghi |

Có thể dùng các kiểm tra trên để xác định trước rằng code của mình **không nên gọi `set`**. Tuy nhiên mã ứng dụng vẫn nên xử lý exception nếu có thao tác Reflection thật, vì metadata, quyền module, kiểu receiver và môi trường chạy có thể tạo thêm lỗi.

## 7. Chương trình Java 17+ đầy đủ: đọc được nhưng không sửa được

Ví dụ này **thực sự tạo hidden class**, không chỉ đặt tên một class bình thường là "Hidden". Nó chứa:

- `Order` là record với component `label`, từ đó compiler tạo final field.
- `HiddenTemplate` là static nested class thường, dùng **class-file bytes** để tạo một **hidden class mới** qua `Lookup.defineHiddenClass`.
- `Ordinary` để so sánh metadata: một class thông thường có private final field nhưng không phải record/hidden class.

### 7.1. Mã nguồn

Lưu thành file **`RecordHiddenFinalDemo.java`**:

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

public class RecordHiddenFinalDemo {
    record Order(int id, String label) {}

    public static class HiddenTemplate {
        private final String code;

        public HiddenTemplate(String code) {
            this.code = code;
        }
    }

    static class Ordinary {
        private final String code;

        Ordinary(String code) {
            this.code = code;
        }
    }

    public static void main(String[] args) throws Exception {
        Order order = new Order(7, "ready");
        Field recordField = Order.class.getDeclaredField("label");

        System.out.println("record class: " + Order.class.isRecord());
        System.out.println("record field final: "
                + Modifier.isFinal(recordField.getModifiers()));
        System.out.println("record open: " + recordField.trySetAccessible());
        System.out.println("record read: " + recordField.get(order));

        try {
            recordField.set(order, "updated");
            System.out.println("record write: success");
        } catch (IllegalAccessException ex) {
            System.out.println("record write: "
                    + ex.getClass().getSimpleName());
        }

        String resource = "RecordHiddenFinalDemo$HiddenTemplate.class";
        byte[] bytes;
        try (InputStream in =
                RecordHiddenFinalDemo.class.getResourceAsStream(resource)) {
            if (in == null) {
                throw new IllegalStateException("Missing " + resource);
            }
            bytes = in.readAllBytes();
        }

        Class<?> hidden = MethodHandles.lookup()
                .defineHiddenClass(bytes, true,
                        MethodHandles.Lookup.ClassOption.NESTMATE)
                .lookupClass();

        Object hiddenObject =
                hidden.getDeclaredConstructor(String.class)
                        .newInstance("sealed");
        Field hiddenField = hidden.getDeclaredField("code");

        System.out.println("hidden class: " + hidden.isHidden());
        System.out.println("hidden field final: "
                + Modifier.isFinal(hiddenField.getModifiers()));
        System.out.println("hidden open: " + hiddenField.trySetAccessible());
        System.out.println("hidden read: " + hiddenField.get(hiddenObject));

        try {
            hiddenField.set(hiddenObject, "updated");
            System.out.println("hidden write: success");
        } catch (IllegalAccessException ex) {
            System.out.println("hidden write: "
                    + ex.getClass().getSimpleName());
        }

        Field ordinary = Ordinary.class.getDeclaredField("code");
        System.out.println("ordinary record: "
                + ordinary.getDeclaringClass().isRecord());
        System.out.println("ordinary hidden: "
                + ordinary.getDeclaringClass().isHidden());
        System.out.println("ordinary final: "
                + Modifier.isFinal(ordinary.getModifiers()));
    }
}
```

Chạy trong thư mục chứa file bằng JDK 17+:

```bash
javac --release 17 RecordHiddenFinalDemo.java
java RecordHiddenFinalDemo
```

Lệnh `javac` tạo các class files cần thiết trong cùng thư mục. Khi chạy trực tiếp với classpath hiện hành, resource `RecordHiddenFinalDemo$HiddenTemplate.class` sẽ tồn tại để `getResourceAsStream` đọc bytes. Nếu đóng gói ứng dụng theo cách đặc biệt, bạn phải bảo đảm class-file resource đó được phân phối và đọc được.

### 7.2. Kết quả chuẩn

```text
record class: true
record field final: true
record open: true
record read: ready
record write: IllegalAccessException
hidden class: true
hidden field final: true
hidden open: true
hidden read: sealed
hidden write: IllegalAccessException
ordinary record: false
ordinary hidden: false
ordinary final: true
```

Đầu ra trên được kiểm chứng bằng cách biên dịch mã nguồn với `--release 17` và chạy trên JDK tương thích. Nó giả định môi trường classpath/unnamed module thông thường, không thêm SecurityManager hoặc cơ chế đặc biệt chặn quyền Reflection.

### 7.3. Giải thích kỹ luồng record

- `Order.class.isRecord()` trả `true` vì `Order` là record.
- `getDeclaredField("label")` tìm trường do record khai báo, có modifier `final`.
- `trySetAccessible()` trả `true` trong ví dụ này vì caller có điều kiện truy cập phù hợp (cùng unnamed module).
- `get(order)` đọc thành công `"ready"`.
- `set(order, "updated")` vẫn ném `IllegalAccessException` do quy tắc **non-modifiable final field của record**. Lỗi **không phải** vì không tìm được trường, không phải vì sai kiểu `String` và không phải vì `trySetAccessible()` trả `false`.

### 7.4. Giải thích kỹ luồng hidden class

- `HiddenTemplate` khi khai báo trong source chỉ là nested class thông thường; nó **không** phải hidden class.
- `getResourceAsStream` lấy chính bytecode đã biên dịch của template. `defineHiddenClass` dùng bytes này để tạo một class mới, trả một `Lookup`; `lookupClass()` là **hidden class thực sự**.
- `hidden.isHidden()` trả `true`. Khác biệt này chứng minh ví dụ đang thao tác với hidden class, không phải chỉ class có tên chứa chữ “Hidden”.
- Constructor được gọi qua Reflection để tạo `hiddenObject`. Field `code` được khai báo với `private final` trong class tương ứng.
- `hiddenField.trySetAccessible()` thành công, `get(hiddenObject)` đọc được `"sealed"`.
- `set(hiddenObject, "updated")` ném `IllegalAccessException` vì declaring class của final field là **hidden class**.

### 7.5. So sánh với class thường

`Ordinary` có `private final String code`, nhưng `isRecord()` và `isHidden()` đều trả `false`. Chương trình **không thử sửa field** của `Ordinary` vì việc phản chiếu sửa final field của class thường sau khởi tạo không phải kỹ thuật nên áp dụng trong mã nghiệp vụ. Mục đích của nó là làm rõ: **`final` thôi chưa diễn tả đầy đủ những hạn chế đặc biệt trong record/hidden class**.

## 8. Những trường hợp biên và ngoại lệ cần phân biệt

### 8.1. Lỗi tra cứu khác lỗi ghi

| Tình huống | Kết quả thường gặp |
|---|---|
| Tên field không tồn tại trong kiểu được yêu cầu | `NoSuchFieldException` khi `getDeclaredField` |
| Đã tìm thấy field nhưng không có quyền truy cập thông thường | `IllegalAccessException` ở `Field.get/set` |
| Package module khác không cho mở deep reflection | `trySetAccessible()` có thể trả `false`; `setAccessible(true)` có thể ném `InaccessibleObjectException` |
| Final field thuộc record/hidden class, access suppression đã bật | `Field.set(...)` vẫn ném `IllegalAccessException` |
| Instance field nhưng receiver là `null` | `NullPointerException` |
| Receiver không phải instance tương thích của declaring class | `IllegalArgumentException` |
| Value sai kiểu hoặc không chuyển được theo quy tắc `Field.set` | `IllegalArgumentException` |

Việc `Field.set` thất bại với record final field **không có nghĩa** class record không tìm được bằng Reflection. Tương tự, hidden class vẫn có thể được khảo sát qua `Class<?>` của nó ngay cả khi cơ chế lookup bằng binary name không áp dụng.

### 8.2. Final field và static field

Một record có thể khai báo static fields hợp lệ. Nếu field là `static final`, nó cũng bị cấm sửa qua `Field.set` theo quy tắc chung áp dụng cho mọi class. Với non-final static fields, Reflection có thể ghi trong điều kiện được phép, nhưng điều đó **không liên quan trực tiếp** đến việc ghi component fields của record.

### 8.3. Đọc có đồng nghĩa thay được cấu trúc bất biến?

Không. `Field.get` trả giá trị của field. Với field kiểu tham chiếu, giá trị này có thể là tham chiếu tới một đối tượng mutable. Ví dụ:

```java
record Team(java.util.List<String> members) {}

var names = new java.util.ArrayList<String>();
names.add("An");
Team team = new Team(names);
names.add("Bình");
System.out.println(team.members().size()); // 2
```

Record component `members` là final và không thể gán lại bằng Reflection, nhưng `ArrayList` mà nó trỏ tới vẫn mutable. Nếu muốn record có ý nghĩa bất biến sâu hơn, dùng defensive copy, ví dụ trong compact canonical constructor:

```java
record SafeTeam(java.util.List<String> members) {
    SafeTeam {
        members = java.util.List.copyOf(members);
    }
}
```

Đây là các đoạn minh họa độc lập về **shallow immutability**, không phải thao tác ghi Field. `List.copyOf` tạo danh sách không hỗ trợ sửa qua API mutator và từ chối phần tử `null`; nếu các phần tử bản thân là đối tượng mutable thì còn cần cơ chế riêng để bảo đảm deep immutability.

## 9. Có thể dùng `VarHandle` hoặc Method Handles để sửa final field này không?

Không nên hiểu rằng một API reflection khác sẽ tự động cung cấp quyền ghi mà `Field.set` đã cấm.

- `VarHandle` dùng để truy cập biến theo các access modes được hỗ trợ. Một VarHandle cho final field thường chỉ có các mode đọc; `set` và các mode ghi không được hỗ trợ. Có thể dùng `isAccessModeSupported(...)` để kiểm tra trước.
- `MethodHandles.Lookup` giúp truy cập method/field theo quyền lookup, nhưng không nên dựa vào việc tạo setter cho final field của record/hidden class. Tham chiếu lookup không phải giấy phép sửa mọi final field.
- Bỏ qua kiểm tra truy cập Java (`setAccessible`) khác với bỏ qua đặc tính **non-modifiable** của field.
- API nội bộ/unsupported hoặc sửa bộ nhớ ngoài cơ chế chuẩn có thể phá vỡ giả định của runtime, gây hỏng dữ liệu và không tạo thành contract ổn định cho ứng dụng.

Nếu cần “cập nhật record”, **tạo record mới** từ dữ liệu cũ và dữ liệu cần thay đổi:

```java
record Position(int x, int y) {}

Position p1 = new Position(2, 3);
Position p2 = new Position(8, p1.y());
// p1 vẫn là Position(2, 3); p2 là Position(8, 3).
```

Đối với hidden class, hãy thiết kế factory/constructor và các trạng thái mutable được khai báo rõ ràng từ đầu nếu cần thay đổi sau tạo; không biến final field thành nơi cập nhật ngầm.

## 10. Khi nào giới hạn này ảnh hưởng framework?

### 10.1. Serialization và deserialization

Nhiều thư viện truyền thống tạo instance rỗng rồi gán trường qua `Field.set`. Chiến lược đó không thể áp dụng nguyên xi cho **record components final**.

Với record, serializer/deserializer hiện đại thường cần:

1. Đọc danh sách `RecordComponent`, tên và kiểu.
2. Thu thập các giá trị constructor arguments từ dữ liệu đầu vào.
3. Gọi **canonical constructor** của record theo đúng thứ tự/kiểu component.
4. Dùng accessor hoặc read-only Reflection khi xuất dữ liệu.

Cơ chế cụ thể tùy thư viện; cần kiểm tra tài liệu phiên bản đang dùng. Không tự sửa `private final` record fields sau khi constructor đã chạy.

### 10.2. Dependency injection, ORM, bytecode tooling

Công cụ tiêm phụ thuộc bằng cách gán field trực tiếp cần nhận biết final fields. Nếu field thuộc record hoặc hidden class thì không thể kỳ vọng `Field.set` hoạt động chỉ vì access suppression đã bật.

Với record, ưu tiên **constructor injection** hoặc biến đổi mô hình thành đối tượng mới theo hợp đồng bất biến. Với hidden class, framework tạo bytecode nên quyết định rõ dữ liệu nào là final trong quá trình định nghĩa, constructor/factory nào khởi tạo nó và dữ liệu nào thực sự mutable.

### 10.3. Công cụ khảo sát và debug

Nếu công cụ chỉ cần **hiển thị metadata** như tên, modifiers, kiểu hoặc declaring class, dùng `getDeclaredFields()` và các phương thức metadata. Không gọi `setAccessible` chỉ để lấy tên field.

Nếu cần đọc private final field, kiểm tra quyền truy cập và phạm vi module. Nếu không được phép, báo rõ **access blocked**. Nếu cần sửa final field của record/hidden class, nên báo **non-modifiable by Reflection** thay vì tiếp tục thử những biến thể `Field.set` khác nhau.

## 11. Những hiểu nhầm phổ biến

**Hiểu nhầm 1: “Có `Field` là sửa được.”** Sai. Có metadata chỉ chứng minh thành viên tồn tại. Khả năng đọc/ghi còn phụ thuộc quyền, receiver, kiểu và quy tắc của final field.

**Hiểu nhầm 2: “`setAccessible(true)` thành công nghĩa là được ghi.”** Sai. Nó chỉ suppress kiểm tra truy cập theo ngôn ngữ Java trong giới hạn runtime; nhóm non-modifiable final fields vẫn chỉ có thể được đọc.

**Hiểu nhầm 3: “Record là class final, nên chỉ có class mới final.”** Sai. Record components còn tương ứng với các private final instance fields; chính các fields này là trọng tâm hạn chế Reflection.

**Hiểu nhầm 4: “Hidden class là class có tên bí mật/private.”** Sai. Hidden class là kiểu do runtime định nghĩa qua cơ chế riêng, có `isHidden() == true` và đặc tính lookup riêng.

**Hiểu nhầm 5: “Chỉ `static final` bị cấm sửa.”** Sai. Trên Java 17, final fields do record và hidden class khai báo cũng bị cấm ghi qua `Field.set`, kể cả field instance.

**Hiểu nhầm 6: “Mọi field của hidden class đều không sửa được.”** Sai. Ràng buộc đặc biệt nói đến **final fields**; non-final fields vẫn xét theo các quy tắc truy cập và gán thông thường.

**Hiểu nhầm 7: “Record bảo đảm mọi thứ bên trong hoàn toàn immutable.”** Sai. Component reference final không tự đóng băng mutable object mà nó trỏ tới; có thể cần defensive copying.

**Hiểu nhầm 8: “`getDeclaringClass()` trả class của receiver là đủ.”** Sai. Field có thể được tìm qua kiểu con nhưng khai báo ở kiểu cha. Quy tắc record/hidden class dựa vào **declaring class của field**.

**Hiểu nhầm 9: “Có thể khắc phục bằng `--add-opens`.”** Sai đối với đặc tính non-modifiable. Mở package có thể giải quyết quyền deep reflection qua ranh giới module, nhưng không cho phép `Field.set` ghi final fields của record/hidden class.

**Hiểu nhầm 10: “`IllegalAccessException` lúc ghi final nghĩa là chương trình không được quyền đọc.”** Không nhất thiết. Ví dụ chạy được phía trên đã đọc thành công rồi mới bị từ chối ghi.

## 12. Checklist thực hành và câu hỏi tự kiểm tra

Khi viết công cụ xử lý Reflection fields, có thể làm theo trình tự:

1. Tìm `Field` theo class và tên phù hợp, ví dụ `getDeclaredField(name)`.
2. Đọc `f.getDeclaringClass()` để xác định **lớp thực sự khai báo** field.
3. Dùng `Modifier.isFinal(f.getModifiers())` và `Modifier.isStatic(...)` để xác định modifier.
4. Nếu `final` và (static hoặc `getDeclaringClass().isRecord()` hoặc `getDeclaringClass().isHidden()`), coi field là **non-modifiable qua `Field.set`**.
5. Nếu chỉ cần đọc giá trị, xét `canAccess(receiver)` và dùng `trySetAccessible()` nếu thật sự cần, nhưng tôn trọng ranh giới module.
6. Ưu tiên accessor/constructor/factory của record và API chính thức của đối tượng; không mặc định đọc/ghi private field.
7. Nếu một framework cần cập nhật, thiết kế lại quá trình tạo instance; đừng dựa vào mutation sau khởi tạo của final field.
8. Phân loại ngoại lệ chính xác: không tìm thấy field, không được mở quyền, receiver sai, hoặc field cố định không thể ghi.

**Câu hỏi tự kiểm tra:**

- `Field.setAccessible(true)` thành công có bảo đảm `Field.set` thành công trên `record Point(int x)` không? Vì sao?
- Sự khác biệt giữa `Class.isRecord()` và `Class.isHidden()` là gì?
- Một field `private int counter` trong hidden class (không `final`) có bị cấm sửa chỉ vì class là hidden không?
- Vì sao class `HiddenTemplate` được khai báo trong source không tự trở thành hidden class? Dòng nào tạo hidden class thật?
- `getDeclaredField` thành công nhưng `set` ném `IllegalAccessException` có thể do những nguyên nhân nào?
- `opens package` có bỏ được cấm ghi final component của record không?
- Làm thế nào đổi `Person("An", 25)` thành một bản ghi mới mang tên `"Bình"` mà không sửa field cũ?
- Tại sao một record có component kiểu `List<String>` vẫn có thể quan sát thấy thay đổi bên trong danh sách đó?

**Kết luận học tập:** Record và hidden class bảo vệ ý nghĩa của **final fields** bằng một hạn chế Reflection riêng. Có thể nhìn thấy, mở quyền để đọc và đọc được field nhưng **`Field.set` vẫn không được ghi**. Hãy xác định declaring class, modifier và mục đích thao tác trước khi chọn phương thức Reflection.

Tài liệu chuẩn để đối chiếu: [Java SE 17 — `Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html), [`AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html), [`Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [`MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html) và [`RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html).