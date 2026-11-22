# 5.7. Giới hạn ghi `static final`, field của record và field của hidden class

Trong Java, reflection cho phép lấy metadata và đọc giá trị của một field bằng `java.lang.reflect.Field`. Tuy nhiên, **tìm thấy field và được quyền đọc không đồng nghĩa với được quyền ghi**. Với Java 17, ngay cả sau khi gọi `field.setAccessible(true)` thành công, một số field `final` vẫn thuộc loại **không thể sửa bằng Core Reflection** (*non-modifiable final fields*):

1. Mọi field `static final` được khai báo trong class hoặc interface.
2. Mọi field `final` được khai báo trong **record class**.
3. Mọi field `final` được khai báo trong **hidden class**.

Đây là giới hạn riêng của thao tác ghi `Field.set(...)`/`setInt(...)` và các setter tương ứng, không đơn thuần là kiểm tra `public`/`private`. Bài học giải thích cơ chế, ranh giới từng loại, cách nhận biết lỗi, một chương trình Java 17+ chạy được và cách thiết kế ứng dụng để không phụ thuộc vào việc sửa các field bị hạn chế.

## 1. Phân biệt `final`, quyền truy cập và khả năng ghi

**`final`** trên field nghĩa là mã Java thông thường chỉ được gán giá trị trong các vị trí khởi tạo mà ngôn ngữ cho phép; sau khi khởi tạo, không thể trực tiếp gán lại bằng lệnh `instance.field = ...` hay `Class.FIELD = ...`. Đối với field tham chiếu, `final` bảo vệ **tham chiếu**, không tự làm đối tượng được tham chiếu trở nên bất biến.

**Quyền truy cập** là một vấn đề khác: field `private` có thể bị chặn ngay cả khi không có `final`. `Field.setAccessible(true)` yêu cầu bỏ qua những kiểm tra truy cập Java thông thường, trong phạm vi mà module Java Platform Module System (JPMS) cho phép. Nó **không loại bỏ modifier `final`**, không biến mọi field thành mutable và không vô hiệu hóa quy tắc non-modifiable final.

Trong Java 17, `Field.set(Object receiver, Object newValue)` đối với field `final` chỉ có thể ghi khi **đồng thời** thỏa:

- Gọi `setAccessible(true)` trên chính đối tượng `Field` đó đã thành công.
- Field là **instance field**, tức không có `static`.
- Lớp **khai báo field** không phải **record class**.
- Lớp **khai báo field** không phải **hidden class**.

Ngay cả khi thỏa các điều kiện trên, thao tác ghi một ordinary final instance field bằng reflection chỉ có ý nghĩa trong những quy trình rất đặc biệt, như tái dựng/deserialization **trước khi đối tượng được công bố cho code khác**. Dùng để sửa đối tượng đang hoạt động có thể dẫn tới kết quả khó dự đoán do semantics của `final`, khả năng tối ưu hóa/JIT và Java Memory Model. Đây **không phải** một cơ chế cập nhật trạng thái ứng dụng được khuyến nghị.

| Field được xét | `setAccessible(true)` có thể thành công? | `Field.set*` có được ghi `final`? | Cách khởi tạo/cập nhật đúng |
| --- | --- | --- | --- |
| `static final` ở class/interface thường | Có, nếu quyền truy cập/module cho phép | **Không** | Đặt giá trị lúc khai báo hoặc static initializer; dùng field không `final` nếu cần thay đổi |
| Record component như `record Point(int x)` | Có, nếu quyền truy cập/module cho phép | **Không** | Khởi tạo qua canonical constructor; tạo record mới khi dữ liệu thay đổi |
| `final` instance/static của hidden class | Có, nếu quyền truy cập/module cho phép | **Không** | Khởi tạo trước khi dùng; tách trạng thái mutable nếu cần |
| `final` instance của class thông thường (không phải record/hidden) | Có, nếu quyền truy cập/module cho phép | Có thể trong điều kiện hẹp trên Java 17; **không an toàn để dựa vào** | Constructor/factory/deserialization đúng lifecycle |
| Field **không final** | Tùy quyền truy cập | Có thể, nếu receiver và kiểu dữ liệu hợp lệ | Setter/API có chủ đích hoặc reflection khi thật sự cần |

Các điều kiện trên mô tả contract của **Java 17 Core Reflection**. Những công cụ ngoài Core Reflection, API nội bộ hoặc biến thể JVM không tạo ra cam kết chung rằng giới hạn này có thể/được phép vượt qua.

## 2. `static final`: không thể ghi lại bằng `Field.set`

`static` nghĩa là field thuộc về class, không thuộc một instance. `final` nghĩa là reference hoặc giá trị chỉ được gán hợp lệ trong quá trình khởi tạo đã định. Cặp `static final` thường dùng cho hằng số:

```java
class Configuration {
    static final int MAX_RETRIES = 3;
    static final String SERVICE_NAME = "orders";
}
```

Đây là các **constant variable** kiểu primitive/String với constant expression nên code Java khác có thể **inline giá trị lúc biên dịch**. Thay đổi bytecode hoặc cố can thiệp runtime vào storage không đảm bảo những chỗ dùng hằng số sẽ quan sát được giá trị mới.

Không phải mọi `static final` đều là compile-time constant:

```java
class Defaults {
    static final Integer TIMEOUT = Integer.valueOf(30);
    static final java.util.List<String> TAGS = new java.util.ArrayList<>();
}
```

`TIMEOUT` không phải constant variable theo JLS do dùng wrapper và factory; `TAGS` giữ tham chiếu `final` nhưng danh sách có thể bị thay đổi qua `TAGS.add(...)` nếu không được bảo vệ. **Cả hai field vẫn không được gán lại bằng `Field.set(...)`** trên Java 17.

Ví dụ thao tác reflection minh họa:

```java
Field field = Configuration.class.getDeclaredField("MAX_RETRIES");
field.setAccessible(true);
int oldValue = field.getInt(null); // OK, receiver null cho static field
field.setInt(null, 7);             // IllegalAccessException
```

Ở đây `getDeclaredField` thành công, `setAccessible(true)` có thể thành công và `getInt(null)` đọc được, nhưng `setInt` bị từ chối do field là `static final`. Trong thao tác static, đối số receiver được bỏ qua, truyền `null` là cách rõ ràng nhất.

**Không nên nhầm:** `Field.setInt(...)` ném **checked `IllegalAccessException`** cho trường hợp này, mặc dù `setAccessible(true)` đã thành công. `InaccessibleObjectException` lại thường liên quan đến **bản thân yêu cầu mở truy cập** bị module chặn, là một giai đoạn khác.

Với interface, mọi field khai báo đều mặc định `public static final`, nên cùng chịu giới hạn. Nếu mục tiêu là thay đổi cấu hình runtime, thay một hằng `static final` bằng cơ chế cấu hình mutable có chủ đích, immutable snapshot được thay thế atomically, hoặc đối tượng cấu hình được cấp phát lại; cân nhắc thread-safety khi dữ liệu được nhiều luồng dùng chung.

## 3. Field của record: bảo toàn trạng thái component đã khởi tạo

Record được hỗ trợ chính thức từ Java 16. Ví dụ:

```java
record Point(int x, int y) {}

Point original = new Point(2, 5);
Point changed  = new Point(8, original.y()); // tạo record mới
```

Compiler tạo các field tương ứng với record component `x` và `y`; mỗi field component là **`private final` instance field**. Record là final class; không thể khai báo thêm instance field trong body của record. Việc thiết lập component xảy ra trong quá trình chạy canonical constructor (hoặc compact constructor với cơ chế gán tự động của Java), không phải bằng thao tác `Field.set` sau khi tạo record.

Với `record Point(int x, int y)`:

```java
Field x = Point.class.getDeclaredField("x");
x.setAccessible(true);
System.out.println(x.getInt(original)); // 2
x.setInt(original, 99);                 // IllegalAccessException
```

**Tại sao không cho phép sửa?** Contract record dựa trên bộ component ổn định: accessor `x()`, `y()`, cùng `equals`, `hashCode`, `toString` mặc định sử dụng trạng thái component. Sửa lén component sau khi khởi tạo phá vỡ ngữ nghĩa mà API record cần duy trì.

Phân biệt:

- `record Point(int x)` có thể khai báo **static field** `static int counter`; nếu **không final** và quyền truy cập hợp lệ, field đó vẫn có thể được cập nhật. Quy tắc không có nghĩa “mọi field trong record đều cấm ghi”.
- Nếu record có `static final`, field đó đã bị hạn chế theo quy tắc `static final`.
- Nếu component kiểu tham chiếu tới đối tượng mutable, **đối tượng được tham chiếu có thể vẫn mutable**. Ví dụ `record Basket(List<String> items) {}` không tự bảo vệ `items` khỏi các thay đổi trong `List`. Cần defensive copy nếu muốn bất biến sâu:

```java
record Basket(java.util.List<String> items) {
    Basket {
        items = java.util.List.copyOf(items);
    }
}
```

Trong compact constructor trên, giá trị tham số `items` được chuẩn hóa trước khi compiler gán vào field component. `List.copyOf` cũng loại trừ phần tử `null` và tạo bản sao không thể sửa qua API List, nhưng không sao chép sâu các đối tượng thành phần nếu chúng mutable.

## 4. Field `final` của hidden class: ranh giới được giữ khi tạo lớp động

**Hidden class** là lớp được tạo động từ bytecode bằng API như `MethodHandles.Lookup.defineHiddenClass(...)` (từ Java 15), thường phục vụ runtime/framework tạo implementation, lambda hoặc logic hỗ trợ. Một hidden class:

- Được định nghĩa từ class-file bytes trong ngữ cảnh của một `Lookup`.
- Có thể kiểm tra bằng `Class.isHidden()`.
- Không có binary name dùng được để tìm bằng `Class.forName(...)` hoặc `ClassLoader.loadClass(...)` như class bình thường.
- Vẫn có metadata và field phản chiếu, ví dụ `hiddenType.getDeclaredField("value")`.
- Có thể có field thường hoặc field `final`. **Chỉ các field `final` khai báo trong hidden class là non-modifiable final theo nhóm này**; field non-final vẫn chịu các quy tắc truy cập/kiểu thông thường.

Ví dụ ý tưởng:

```java
Class<?> hiddenType = lookup.defineHiddenClass(bytes, true).lookupClass();
System.out.println(hiddenType.isHidden()); // true

Field value = hiddenType.getDeclaredField("value");
value.setAccessible(true);
Object current = value.get(hiddenInstance); // có thể đọc
value.set(hiddenInstance, replacement);     // IllegalAccessException nếu final
```

Đây là đoạn **minh họa trong ngữ cảnh** đã có biến `lookup`, `bytes`, `hiddenInstance`, `replacement` hợp lệ; ví dụ đầy đủ dưới đây xây dựng tất cả các biến này.

Việc truyền class-file bytes không phải chi tiết trang trí: `defineHiddenClass` không nhận `Class<?>` có sẵn, mà nhận **bytecode** và trả về một `Lookup` trên lớp vừa tạo. Package của class bytes phải phù hợp với lookup class, và module/quyền truy cập phải đáp ứng yêu cầu API. Nếu bytecode không hợp lệ hoặc package sai, thao tác định nghĩa lớp sẽ thất bại **trước khi tới bước ghi field**.

**Không nên suy diễn:** “hidden class” không giống “field private”. Một hidden class có thể chứa field public và vẫn bị cấm ghi nếu field đó là `final`. `setAccessible(true)` không thay đổi điều này.

## 5. Chính xác `setAccessible`, `canAccess` và `Field.set` kiểm tra điều gì?

Ba thao tác trả lời những câu hỏi khác nhau.

| API | Câu hỏi | Kết quả quan trọng |
| --- | --- | --- |
| `SomeType.class.getDeclaredField(...)` | Có field được khai báo trực tiếp với tên này không? | `Field` hoặc `NoSuchFieldException` |
| `field.trySetAccessible()` | Có thể yêu cầu bỏ qua kiểm tra truy cập không? | `true`/`false`; không có nghĩa writable |
| `field.setAccessible(true)` | Cho phép bỏ qua kiểm tra Java language access nếu luật module cho phép? | Có thể thành công hoặc ném `InaccessibleObjectException` |
| `field.canAccess(receiver)` | Với receiver này, **hiện tại có thể truy cập** field không? | `boolean`, không bảo đảm gọi `set` sẽ thành công |
| `field.get(receiver)`, `getInt(receiver)` | Có thể đọc giá trị không? | Giá trị hoặc ngoại lệ truy cập/receiver/kiểu |
| `field.set(receiver, value)`, `setInt(receiver, value)` | Có thể ghi giá trị hợp lệ không? | Thành công hoặc `IllegalAccessException`/`IllegalArgumentException`/lỗi receiver |

`getDeclaredField` là phương thức của **`Class`**; không phải của `Field`. Khi đọc code, cần phân biệt đúng lớp sở hữu API.

Có hai lớp giới hạn độc lập:

1. **Java access control/JPMS:** `public`, `private`, phạm vi package, `exports` và `opens` quyết định khả năng truy cập. Đối với package của module khác không mở để deep reflection, `setAccessible(true)` có thể ném `InaccessibleObjectException`; `trySetAccessible()` có thể trả `false`.
2. **Non-modifiable final:** ngay cả khi lớp và module cho phép truy cập, `Field.set` không cấp quyền ghi ba nhóm đã nêu. Khi điều kiện ghi không thỏa, `IllegalAccessException` vẫn có thể xảy ra.

Để kiểm tra giới hạn theo metadata, có thể xây một **bộ nhận diện sơ bộ** (chỉ là điều kiện về loại `final` trên Java 17, không phải bộ xác nhận quyền ghi đầy đủ):

```java
static boolean isNonModifiableFinal(java.lang.reflect.Field field) {
    int modifiers = field.getModifiers();
    Class<?> owner = field.getDeclaringClass();

    return java.lang.reflect.Modifier.isFinal(modifiers)
            && (java.lang.reflect.Modifier.isStatic(modifiers)
                || owner.isRecord()
                || owner.isHidden());
}
```

Trả `false` **không hứa** `Field.set` chắc chắn thành công: quyền truy cập có thể thiếu; receiver sai lớp, loại giá trị không phù hợp, hoặc JVM áp dụng giới hạn khác. Còn `true` mô tả đúng ba nhóm non-modifiable final ở JDK 17.

**Ngoại lệ nên đọc đúng nghĩa:**

- `NoSuchFieldException`: lookup sai tên hoặc không tìm thấy field trong phạm vi API được gọi.
- `InaccessibleObjectException`: không cho mở truy cập bằng `setAccessible(true)`, thường do module/package.
- `IllegalAccessException`: truy cập hoặc ghi bị từ chối ở `Field.get/set`; với ba nhóm final, thao tác ghi bị từ chối kể cả khi mở truy cập đã thành công.
- `IllegalArgumentException`: receiver sai loại, giá trị truyền cho setter không chuyển đổi hợp lệ; không tự kết luận đó là lỗi `final`.
- `NullPointerException`: receiver `null` cho instance field; đối với static field, receiver bị bỏ qua.
- `ExceptionInInitializerError`: static initialization được kích hoạt và thất bại, không phải lỗi thuộc tính `final`.

## 6. Ví dụ Java 17+ chạy được: ba nhóm bị cấm ghi và một nhóm cần thận trọng

Chương trình dưới đây biên dịch **một file duy nhất**, minh họa việc đọc thành công rồi bị từ chối ghi đối với `static final`, record component và `final` field của hidden class. Nó còn so sánh với ordinary final instance field: Core Reflection Java 17 có thể ghi loại này khi mở truy cập, nhưng không nên dựa vào kết quả để thiết kế ứng dụng.

Đặt tên file là **`FinalFieldRulesDemo.java`**:

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Field;

public class FinalFieldRulesDemo {
    private static final int STATIC_CONSTANT = 7;

    record Point(int x) {}

    static final class Ordinary {
        final int x;
        Ordinary(int x) { this.x = x; }
    }

    // Template được javac biên dịch thành file .class riêng.
    static class HiddenTemplate {
        public final int x;
        public HiddenTemplate(int x) { this.x = x; }
    }

    public static void main(String[] args) throws Exception {
        // A. static final: mở truy cập/đọc được, không ghi được.
        Field staticField =
                FinalFieldRulesDemo.class.getDeclaredField("STATIC_CONSTANT");
        staticField.setAccessible(true);
        System.out.println("static read: " + staticField.getInt(null));
        try {
            staticField.setInt(null, 8);
        } catch (IllegalAccessException e) {
            System.out.println("static write: " + e.getClass().getSimpleName());
        }

        // B. Record component: private final instance field.
        Point point = new Point(3);
        Field recordField = Point.class.getDeclaredField("x");
        recordField.setAccessible(true);
        System.out.println("record read: " + recordField.getInt(point));
        try {
            recordField.setInt(point, 9);
        } catch (IllegalAccessException e) {
            System.out.println("record write: " + e.getClass().getSimpleName());
        }

        // C. Ordinary final: Java 17 có thể ghi qua reflection
        // trong một số điều kiện; không dùng kỹ thuật này làm thiết kế.
        Ordinary ordinary = new Ordinary(4);
        Field ordinaryField = Ordinary.class.getDeclaredField("x");
        ordinaryField.setAccessible(true);
        ordinaryField.setInt(ordinary, 10);
        System.out.println(
                "ordinary reflection read: " + ordinaryField.getInt(ordinary));

        // D. Lấy bytecode từ class nested mà javac vừa tạo.
        byte[] templateBytes;
        try (InputStream in = FinalFieldRulesDemo.class.getResourceAsStream(
                "FinalFieldRulesDemo$HiddenTemplate.class")) {
            if (in == null) {
                throw new IllegalStateException(
                        "Missing compiled HiddenTemplate class");
            }
            templateBytes = in.readAllBytes();
        }

        // Tạo hidden class từ bytecode, không phải dùng Class.forName.
        Class<?> hiddenType = MethodHandles.lookup()
                .defineHiddenClass(templateBytes, true,
                        MethodHandles.Lookup.ClassOption.NESTMATE)
                .lookupClass();

        Object hidden = hiddenType.getDeclaredConstructor(int.class)
                .newInstance(5);
        Field hiddenField = hiddenType.getDeclaredField("x");
        hiddenField.setAccessible(true);

        System.out.println("hidden: " + hiddenType.isHidden());
        System.out.println("hidden read: " + hiddenField.getInt(hidden));
        try {
            hiddenField.setInt(hidden, 6);
        } catch (IllegalAccessException e) {
            System.out.println("hidden write: " + e.getClass().getSimpleName());
        }
    }
}
```

Để bytecode của `HiddenTemplate` có thể được tìm bằng `getResourceAsStream`, hãy giữ các file `.class` mà `javac` tạo ra **cùng trên classpath**, ví dụ chạy ngay tại thư mục đang biên dịch:

```bash
javac --release 17 FinalFieldRulesDemo.java
java FinalFieldRulesDemo
```

`stdout` chuẩn của chương trình:

```text
static read: 7
static write: IllegalAccessException
record read: 3
record write: IllegalAccessException
ordinary reflection read: 10
hidden: true
hidden read: 5
hidden write: IllegalAccessException
```

**Giải thích kết quả:**

1. `STATIC_CONSTANT` được tìm và đọc là `7`; `setInt(null, 8)` ném `IllegalAccessException` vì là `static final`.
2. `Point.x` đọc được `3` sau khi mở truy cập; setter ném `IllegalAccessException` vì là component `final` của record.
3. `Ordinary.x` thuộc class thường nên ở Java 17 có thể được set bằng reflection sau `setAccessible(true)`. Dòng `ordinary reflection read: 10` chỉ xác minh giá trị qua **chính `Field.getInt`**; không dùng kết quả này để suy diễn rằng mọi code/JIT/luồng sẽ thấy giá trị mới.
4. `HiddenTemplate` được biên dịch thành class-file bytes. `defineHiddenClass(..., NESTMATE)` định nghĩa một lớp mới, `isHidden()` trả `true`; field `x` đọc được `5` nhưng không ghi thành `6` qua reflection.
5. Ví dụ không cần `--add-opens` vì toàn bộ code do ta sở hữu trong cùng unnamed module, với điều kiện truy cập phù hợp. Với lớp từ module khác, bước `setAccessible(true)` có thể thất bại **trước khi** tới phép ghi.

`Lookup.ClassOption.NESTMATE` cho hidden class tham gia nest của lookup class, giúp thao tác trong ví dụ có quyền truy cập thích hợp. Nó **không** cấp phép ghi các field `final` của hidden class.

## 7. Vì sao không thể “sửa” bằng những mẹo phổ biến?

### 7.1. `setAccessible(true)` không mở khóa `final`

API này xử lý kiểm tra **accessibility**, không thay đổi loại field. Với ba nhóm non-modifiable final, nó chỉ có thể cho phép đọc (và metadata access), không có quyền ghi. `trySetAccessible()==true` hoặc `canAccess(receiver)==true` cũng **không** chứng minh field writable.

### 7.2. Không thể dựa vào sửa modifier `final` bằng reflection

Đoạn code truyền miệng như tìm `Field.class.getDeclaredField("modifiers")` rồi xóa bit `Modifier.FINAL` không phải API hợp lệ, không bảo đảm chạy trên Java hiện đại và không thay đổi hợp đồng non-modifiable final. Hơn nữa, `Class.getDeclaredFields()` có thể che giấu các trường nội bộ nhạy cảm của core reflection. Đừng sử dụng cách này trong giáo trình, thư viện hoặc code production.

### 7.3. `VarHandle` không phải đường vòng ghi `final`

`java.lang.invoke.VarHandle` có thể đọc field `final` khi lookup đủ quyền, nhưng với một VarHandle trỏ tới **read-only variable** như final field, các access mode ghi (ví dụ `set`, `setVolatile`) và cập nhật nguyên tử không được hỗ trợ; gọi chúng dẫn tới `UnsupportedOperationException`. Có thể hỏi `handle.isAccessModeSupported(VarHandle.AccessMode.SET)` trước khi sử dụng.

```java
// Minh họa trong ngữ cảnh đã có VarHandle handle cho final field:
if (!handle.isAccessModeSupported(
        java.lang.invoke.VarHandle.AccessMode.SET)) {
    System.out.println("write unsupported");
}
```

Các API nội bộ/không được hỗ trợ như `sun.misc.Unsafe`, can thiệp bộ nhớ, agent đặc quyền hoặc sửa bytecode để cưỡng ép mutate field không phải giải pháp thay thế được bảo đảm. Nếu có hiệu ứng ở một runtime cụ thể, vẫn có thể sai về class loading, constant folding, memory model, module boundary hoặc phiên bản JVM. **Không dựa vào những đường vòng đó để bảo toàn tính đúng đắn của ứng dụng.**

### 7.4. Dùng `--add-opens` chỉ khi lỗi thật là module access

`--add-opens module/package=targetModule` (hoặc `ALL-UNNAMED` theo mô hình chạy) có thể giải quyết một số trường hợp module không cho deep reflection và giúp `setAccessible(true)` thành công, nhưng **không nâng quyền ghi** `static final`/record final/hidden-class final trên Java 17.

Phải phân biệt:

- `setAccessible(true)` báo `InaccessibleObjectException` → xem lại `opens` và module.
- `setAccessible(true)` thành công nhưng `setInt` báo `IllegalAccessException` cho non-modifiable final → phải thay thiết kế dữ liệu/lifecycle.
- `setInt` báo `IllegalArgumentException` → kiểm tra giá trị, receiver, kiểu primitive/wrapper và chuyển đổi.

## 8. Thiết kế đúng khi dữ liệu cần thay đổi

| Nhu cầu | Hướng thiết kế |
| --- | --- |
| Cập nhật thông số khi chương trình đang chạy | Đưa trạng thái vào field mutable được quản lý, đối tượng cấu hình có API thay thế, hoặc cấu hình external được reload; đồng bộ hóa phù hợp |
| Giá trị hằng dùng chung không bao giờ đổi | Giữ `static final`; nạp từ cấu hình ban đầu qua initializer/factory nếu không phải constant expression |
| Thay một component của record | Tạo **record mới** với component mới; cập nhật tham chiếu ở tầng quản lý state |
| Record chứa collection có yêu cầu bất biến | Sao chép bảo vệ ở constructor và accessor khi cần; kiểm tra phần tử mutable |
| Thêm trạng thái hoạt động cho hidden class | Dùng field **non-final** nếu mô hình yêu cầu và luật truy cập cho phép, hoặc giữ mutable state ở một đối tượng bên ngoài |
| Serialization/deserialization đối tượng cũ | Ưu tiên constructor/factory/serializer phù hợp; chỉ thao tác đặc biệt với ordinary blank final trước khi publish nếu có hợp đồng rõ |
| Framework không thể tạo object do lỗi quyền truy cập | Rà soát `exports`/`opens`, API public, caller lookup và module structure; không xem đó là quyền sửa `final` |

Với record, một pattern hữu ích là tạo instance mới:

```java
record Settings(String host, int port) {
    Settings withPort(int newPort) {
        return new Settings(host, newPort);
    }
}

Settings oldSettings = new Settings("localhost", 8080);
Settings updated = oldSettings.withPort(9090);
```

Đoạn trên minh họa phương thức thiết kế *copy with change* cho dữ liệu bất biến. `oldSettings` không đổi; `updated` là instance khác. Trong hệ thống nhiều luồng, tầng lưu trạng thái có thể dùng `AtomicReference<Settings>` hoặc cơ chế đồng bộ phù hợp để thay toàn bộ snapshot một cách rõ ràng.

## 9. Quy trình chẩn đoán khi `Field.set` thất bại

Giả sử framework báo `IllegalAccessException` khi muốn ghi một field. Trước khi xử lý, ghi lại:

1. `field.getDeclaringClass().getName()` và tên field từ `field.getName()`.
2. Modifier `static`, `final` qua `Modifier.isStatic(...)` và `Modifier.isFinal(...)`.
3. `field.getDeclaringClass().isRecord()` và `.isHidden()`.
4. Trạng thái `canAccess`/`trySetAccessible`, thông tin module của lớp khai báo và caller.
5. Đối tượng receiver (`null` cho static) và kiểu dữ liệu được gán (cho instance kiểm tra receiver tương thích).
6. Loại exception gốc từ thao tác **mở truy cập** hay **ghi**; giữ stack trace để không trộn hai giai đoạn.

Mã phân loại sơ bộ, **chỉ dùng để quan sát**:

```java
static String fieldCategory(java.lang.reflect.Field field) {
    Class<?> owner = field.getDeclaringClass();
    int flags = field.getModifiers();
    boolean finalField = java.lang.reflect.Modifier.isFinal(flags);

    if (!finalField) return "not final";
    if (java.lang.reflect.Modifier.isStatic(flags)) return "static final";
    if (owner.isRecord()) return "record final";
    if (owner.isHidden()) return "hidden-class final";
    return "ordinary instance final";
}
```

Trong trường hợp hidden class đồng thời có `static final`, thứ tự trong helper trên phân loại thành `static final` vì nó đã đủ để chặn ghi. Hai điều kiện có thể cùng đúng; helper không có ý định đánh dấu chúng loại trừ nhau.

Ví dụ một lỗi:

```text
java.lang.IllegalAccessException: Cannot set static final int field ...
```

Cách hiểu: lookup đã biết field, nhưng **thao tác ghi** bị chặn. Thử chuyển sang `getDeclaredField`, `setAccessible` hay `--add-opens` không giải quyết được quy tắc `static final` nếu quyền đọc đã đủ.

## 10. Bài tập tự kiểm tra

**A.** Một field `private static final int LIMIT` trong class cùng module: `setAccessible(true)` thành công, `getInt(null)` trả `10`. Gọi `setInt(null, 20)` có thành công không? Vì sao?

**B.** `record User(long id, String name) {}`: framework tìm được `Field name` và `trySetAccessible()` trả `true`. Liệu có thể gọi `nameField.set(user, "new")`? Nếu muốn đổi tên phải làm thế nào?

**C.** Một lớp được tạo bằng `Lookup.defineHiddenClass` có `final int code` và `int counter`. Theo quy tắc non-modifiable final Java 17, field nào chắc chắn bị chặn ghi bằng `Field.set`, và field nào *có thể* ghi khi quyền truy cập cho phép?

**D.** `static final List<String> NAMES = new ArrayList<>()`: không thể gán lại reference qua reflection; vậy `NAMES.add("x")` có thể làm gì? Muốn bất biến thật sự phải thiết kế ra sao?

**E.** Cùng một field record, `setAccessible(true)` có thể thành công nhưng `Field.set(...)` trả `IllegalAccessException`. Hai kết quả này có mâu thuẫn không?

**Đáp án:**

- **A:** Không; `LIMIT` là `static final`, thuộc nhóm non-modifiable final. Setter ném `IllegalAccessException` ngay cả khi có quyền đọc.
- **B:** Không; component `name` được lưu trong `private final` field của record. Tạo `new User(user.id(), "new")` và thay reference quản lý đối tượng.
- **C:** `code` bị chặn do `final` trong hidden class; `counter` không `final` nên có thể ghi nếu access/receiver/kiểu dữ liệu hợp lệ.
- **D:** Lời gọi `add` có thể làm thay đổi **nội dung list** vì `final` chỉ khóa reference. Muốn danh sách bất biến, dùng immutable snapshot và không để lộ mutable backing collection.
- **E:** Không. `setAccessible` xét quyền bỏ qua access checks; `Field.set` còn xét quy tắc ghi non-modifiable final.

## 11. Nguồn đối chiếu Java 17

- [Javadoc `java.lang.reflect.Field` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): `setAccessible` và `set`, ba loại non-modifiable final fields và điều kiện ghi ordinary final.
- [Javadoc `MethodHandles.Lookup` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass` và `NESTMATE`.
- [Javadoc `VarHandle` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): access mode không hỗ trợ trên read-only/final field.
- [Java 17 Records](https://docs.oracle.com/en/java/javase/17/language/records.html): record component, constructor và mô hình dữ liệu.

**Ghi nhớ:** `setAccessible(true)` có thể mở quyền đọc hoặc bỏ qua một số access checks, **không mở khóa mọi `final` field**. Trên Java 17, `static final`, `final` của record và `final` của hidden class là ba nhóm **không được ghi bằng `Field.set*`**. Khi dữ liệu cần thay đổi, hãy đưa sự thay đổi vào constructor, đối tượng mới hoặc trạng thái mutable được thiết kế rõ ràng.
