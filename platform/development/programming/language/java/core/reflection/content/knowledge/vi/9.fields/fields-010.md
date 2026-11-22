# Giá trị `null` với field tham chiếu và primitive trong Java Reflection

Khi thao tác với `java.lang.reflect.Field`, cần phân biệt **kiểu khai báo của field**, **giá trị thực tế**, và **đối tượng chứa field**. Một field có kiểu tham chiếu có thể chứa `null`; field có kiểu nguyên thủy (*primitive*) không thể chứa `null`. Tuy nhiên, cả hai đều được đọc qua `Field.get(Object)`, vốn có **kiểu trả về `Object`**. Chính điều đó dễ gây hiểu nhầm khi viết mapper, serializer hoặc framework Reflection.

Bài học giải thích vì sao `Field.get()` của primitive trả về wrapper thay vì `null`, vì sao `Field.set(..., null)` thất bại trên primitive, sự khác nhau giữa `Integer` và `int`, cách Reflection chuyển đổi kiểu số, và ý nghĩa hoàn toàn khác của tham số receiver `null`.

## 1. Trước tiên: `null` là giá trị của tham chiếu, không phải của primitive

Java có tám kiểu primitive: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`. Primitive lưu giá trị thuộc miền kiểu của nó; **không có trạng thái `null`**. Ngược lại, field kiểu tham chiếu như `String`, `Integer`, `List<String>` hoặc kiểu ứng dụng có thể chứa một object reference hoặc `null`.

| Field khai báo | Kiểu field thực tế | Giá trị mặc định trước khi gán tường minh | Có thể gán `null`? |
|---|---|---|---|
| `String name;` | Tham chiếu `String` | `null` | Có |
| `Integer age;` | Tham chiếu wrapper `Integer` | `null` | Có |
| `int age;` | Primitive `int` | `0` | Không |
| `boolean enabled;` | Primitive `boolean` | `false` | Không |
| `char letter;` | Primitive `char` | `'\\u0000'` | Không |
| `double amount;` | Primitive `double` | `0.0` | Không |

Trong ví dụ trên, giá trị mặc định áp dụng cho **instance field** của object đã được cấp phát hoặc **static field** khi chuẩn bị class theo quy tắc của JVM; **biến cục bộ** không được tự động gán giá trị mặc định để có thể sử dụng ngay.

Đừng nhầm hai khai báo:

```java
Integer quantity = null; // hợp lệ: Integer là kiểu tham chiếu
int count = 0;           // hợp lệ: int là primitive
// int missing = null;   // lỗi biên dịch: null không chuyển thành int
```

`Integer` là một lớp wrapper của `int`, nhưng `Integer.class.isPrimitive()` trả `false`. Một wrapper `Integer` có thể `null`; một primitive `int` thì không.

## 2. Đọc bằng `Field.get`: primitive được boxing

Chữ ký quan trọng:

```java
Object value = field.get(receiver);
```

`Field.get(Object obj)` trả về `Object`. Nếu field là kiểu tham chiếu, kết quả chính là giá trị tham chiếu mà field đang giữ, **có thể `null`**. Nếu field là primitive, Reflection **boxing** giá trị thành wrapper tương ứng trước khi trả về.

| Kiểu field được khai báo | Giá trị trong field | `Field.get(...)` trả về |
|---|---|---|
| `String` | `null` | `null` |
| `Integer` | `null` | `null` |
| `Integer` | `Integer.valueOf(5)` | Một `Integer` có giá trị `5` |
| `int` | `5` | Một `Integer` có giá trị `5`; không phải `null` |
| `boolean` | `false` | Một `Boolean` có giá trị `false` |
| `char` | `'A'` | Một `Character` có giá trị `'A'` |

Vì vậy, cách kiểm tra `if (field.get(obj) == null)` có thể phát hiện một **tham chiếu null**, nhưng **không thể** phát hiện trạng thái “chưa gán” trên primitive. Nếu primitive mang giá trị `0`, `false` hoặc `'\\u0000'`, đó vẫn là **giá trị hợp lệ** của field.

Đặc biệt, Java Reflection **không** tự coi `0` hay `false` là `null`. Nếu một hệ thống muốn thể hiện trạng thái “không có dữ liệu”, nó cần quy ước riêng, wrapper nullable, kiểu `Optional` phù hợp hoặc metadata khác; không thể dựa vào primitive để chứa `null`.

### Đọc kiểu nguyên thủy với các getter chuyên biệt

`Field` có các phương thức `getBoolean`, `getByte`, `getShort`, `getChar`, `getInt`, `getLong`, `getFloat`, `getDouble`. Những phương thức này trả về **primitive** tương ứng, không trả wrapper hay `null`.

```java
Field score = Person.class.getField("score"); // giả sử public int score
int result = score.getInt(person);
```

Đây là đoạn minh họa, giả định `Person` và `person` đã được khai báo. `getInt` có thể đọc những primitive field chuyển được sang `int` bằng **widening primitive conversion** (ví dụ field `byte` hoặc `short`); nó **không** tự unbox một **field khai báo `Integer`**.

Ví dụ, với field khai báo `Integer nullableScore`, `field.get(person)` trả `Integer` hoặc `null`; còn `field.getInt(person)` ném **`IllegalArgumentException`**, kể cả khi `nullableScore` thực tế khác `null`. Căn cứ là **kiểu khai báo của field**, không phải wrapper object tình cờ nằm trong đó.

## 3. Ghi bằng `Field.set`: xử lý `null` theo kiểu đích

Chữ ký:

```java
field.set(receiver, value);
```

`receiver` là object sở hữu **instance field** hoặc có thể là `null` đối với **static field**. `value` là giá trị **muốn ghi vào field**. Hai tham số này hoàn toàn khác vai trò.

### Field tham chiếu nhận `null`

```java
Field name = Person.class.getField("name"); // giả sử public String name
name.set(person, null);                     // hợp lệ nếu có quyền ghi
```

Một tham chiếu có thể nhận `null`, kể cả wrapper như `Integer` hoặc `Boolean`. Ngoài `null`, giá trị ghi phải tương thích với kiểu khai báo của field theo quy tắc gán/Reflection. Một field `String` không thể nhận một `Integer` chỉ vì cả hai đều là `Object`.

### Primitive field từ chối `null`

```java
Field age = Person.class.getField("age"); // giả sử public int age
age.set(person, null);                    // ném IllegalArgumentException
```

Vì `int` không có `null`, `Field.set` không thể biến `null` thành `0` hay một giá trị mặc định khác. Thao tác ném **`IllegalArgumentException`**. Đây là lỗi **chuyển đổi giá trị muốn ghi**, không phải do Reflection không tìm thấy field.

Cần tránh suy luận “Java tự unboxing nên `null` được chuyển thành primitive mặc định”: unboxing một wrapper `null` trong biểu thức Java thông thường cũng không tạo ra giá trị hợp lệ.

### Ghi primitive qua wrapper và widening

Khi `value` là wrapper **khác null**, `Field.set` có thể unbox rồi thực hiện **widening primitive conversion** nếu kiểu đích cho phép:

```java
Field count = Person.class.getField("count"); // giả sử public int count
count.set(person, Integer.valueOf(11));       // thành công
count.set(person, Short.valueOf((short) 12)); // thành công: short -> int
count.set(person, Long.valueOf(13L));         // ném IllegalArgumentException
```

Đây là ví dụ minh họa. `long -> int` là **narrowing**, nên không được tự chuyển trong `Field.set`. Không có chuyện Reflection tự động dùng `String.valueOf` hoặc parse chuỗi:

```java
// Giả sử count có kiểu int:
count.set(person, "42"); // KHÔNG tự parse; ném IllegalArgumentException
```

Nếu dữ liệu bên ngoài là `String`, bước **parse và validate** phải làm trước khi ghi. Nếu input là `null` mà field đích là primitive, mapper phải đặt quy tắc rõ ràng: từ chối thiếu dữ liệu, bỏ qua assignment để giữ giá trị hiện tại, hoặc chọn một mặc định được đặc tả; không nên lặng lẽ đổi `null` thành `0`/ `false` mà không có hợp đồng dữ liệu.

### Setter chuyên biệt

`Field.setInt(receiver, 10)` hoặc `Field.setBoolean(receiver, true)` nhận **primitive** ngay ở tham số thứ hai, không có chỗ cho `null`. Việc chuyển đổi kiểu vẫn tuân theo quy tắc phù hợp của các specialized setters. `setInt` không dùng để gán một field **khai báo kiểu `Integer`**, vì field đó là kiểu tham chiếu.

## 4. Ví dụ Java 17+ hoàn chỉnh, đã kiểm tra biên dịch và stdout

Lưu thành tệp **`FieldNullDemo.java`**:

```java
import java.lang.reflect.Field;

public class FieldNullDemo {
    public static class Sample {
        public String nickname;
        public Integer nullableCount;
        public int count = 7;
        public boolean enabled;
        public static String appName;
        public static int globalCount = 3;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Sample sample = new Sample();
        Class<Sample> type = Sample.class;
        Field nickname = type.getField("nickname");
        Field nullableCount = type.getField("nullableCount");
        Field count = type.getField("count");
        Field enabled = type.getField("enabled");
        Field appName = type.getField("appName");
        Field globalCount = type.getField("globalCount");

        System.out.println("reference initial: " + nickname.get(sample));
        System.out.println("wrapper initial: " + nullableCount.get(sample));
        Object countObject = count.get(sample);
        System.out.println("primitive get: " + countObject + " / " + countObject.getClass().getSimpleName());
        System.out.println("boolean get: " + enabled.get(sample));
        System.out.println("types: " + count.getType().getName() + ", " + nullableCount.getType().getName());
        System.out.println("count primitive: " + count.getType().isPrimitive());
        System.out.println("nullableCount primitive: " + nullableCount.getType().isPrimitive());

        nickname.set(sample, null);
        nullableCount.set(sample, null);
        System.out.println("both reference null: " + (nickname.get(sample) == null && nullableCount.get(sample) == null));

        try {
            count.set(sample, null);
        } catch (IllegalArgumentException e) {
            System.out.println("primitive rejects null: " + e.getClass().getSimpleName());
        }

        count.set(sample, Integer.valueOf(11));
        System.out.println("count via wrapper: " + count.getInt(sample));

        count.set(sample, Short.valueOf((short) 12));
        System.out.println("count via widening: " + count.getInt(sample));

        try {
            count.set(sample, Long.valueOf(13L));
        } catch (IllegalArgumentException e) {
            System.out.println("narrowing rejected: " + e.getClass().getSimpleName());
        }

        try {
            nullableCount.getInt(sample);
        } catch (IllegalArgumentException e) {
            System.out.println("typed getter on wrapper field: " + e.getClass().getSimpleName());
        }

        System.out.println("static reference before: " + appName.get(null));
        appName.set(null, "demo");
        System.out.println("static reference after: " + appName.get(null));
        System.out.println("static primitive: " + globalCount.getInt(null));

        try {
            nickname.get(null);
        } catch (NullPointerException e) {
            System.out.println("instance receiver null: " + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp, sử dụng JDK 17 hoặc mới hơn:

```bash
javac FieldNullDemo.java
java FieldNullDemo
```

**Stdout:**

```text
reference initial: null
wrapper initial: null
primitive get: 7 / Integer
boolean get: false
types: int, java.lang.Integer
count primitive: true
nullableCount primitive: false
both reference null: true
primitive rejects null: IllegalArgumentException
count via wrapper: 11
count via widening: 12
narrowing rejected: IllegalArgumentException
typed getter on wrapper field: IllegalArgumentException
static reference before: null
static reference after: demo
static primitive: 3
instance receiver null: NullPointerException
```

**Giải thích output:**

1. `nickname` và `nullableCount` đều là **reference fields**, được mặc định bằng `null`. `enabled` là primitive boolean nên mặc định `false`.
2. `count` khai báo `int` và chứa `7`; `Field.get` boxing thành `Integer`. Bởi vậy `countObject.getClass().getSimpleName()` in `Integer`, không có giá trị `null`.
3. `Field.getType()` cho biết **kiểu khai báo**: `int` đối với `count`, `java.lang.Integer` đối với `nullableCount`. `isPrimitive()` phân biệt hai trường hợp ngay cả khi cả hai có thể đọc qua `Object`.
4. Ghi `null` cho hai field tham chiếu thành công. Ghi `null` cho primitive `count` ném `IllegalArgumentException`.
5. `Integer(11)` được unbox thành `int`; `Short(12)` được unbox rồi widening từ `short` sang `int`; `Long(13)` không thể narrowing sang `int` theo API này.
6. `nullableCount.getInt(sample)` thất bại **vì declared type là `Integer`**, không phải vì giá trị field đang `null`. Ngay cả nếu field chứa `Integer.valueOf(5)`, specialized getter này vẫn không đọc được field tham chiếu.
7. `appName.get(null)` và `appName.set(null, "demo")` thao tác với **static field**; `null` ở đây là **receiver**, không phải giá trị phải ghi. Ngược lại, `nickname.get(null)` là instance field có receiver `null`, nên ném `NullPointerException`.

## 5. Hai vị trí `null` trong `Field.get`/`Field.set` có ý nghĩa khác nhau

Nhìn chữ ký:

```java
Object read = field.get(receiver);
field.set(receiver, value);
```

Hãy phân biệt hai trường hợp hoàn toàn độc lập.

| Thao tác | `receiver` | `value` | Kết quả |
|---|---|---|---|
| Đọc instance field | Object instance hợp lệ | Không áp dụng | Thành công nếu có quyền đọc |
| Đọc instance field | `null` | Không áp dụng | `NullPointerException` |
| Đọc static field | `null` | Không áp dụng | Hợp lệ; receiver bị bỏ qua |
| Ghi instance reference field | Object instance hợp lệ | `null` | Hợp lệ nếu field ghi được |
| Ghi instance primitive field | Object instance hợp lệ | `null` | `IllegalArgumentException` |
| Ghi static reference field | `null` | `null` | Hợp lệ nếu field ghi được |
| Ghi static primitive field | `null` | `null` | `IllegalArgumentException` |

Với static field, tham số receiver của `Field.get`/`Field.set` **không được dùng để chỉ instance** và có thể truyền `null`. Khi truy cập static field, JVM có thể phải **khởi tạo lớp khai báo** nếu chưa được khởi tạo; lấy metadata `Field` trước đó không tự đồng nghĩa đã chạy static initializer.

Với instance field, receiver phải là instance tương thích với lớp khai báo field. Nếu truyền **đối tượng không phù hợp**, Reflection có thể ném `IllegalArgumentException`. Nếu receiver là `null`, lỗi là `NullPointerException`. Đừng nhầm hai lỗi receiver này với `IllegalArgumentException` do **value không phù hợp kiểu primitive** trong `Field.set`.

Ví dụ rất dễ bị đọc nhầm:

```java
Field global = Sample.class.getField("appName");
global.set(null, null); // receiver null: hợp lệ cho static;
                        // value null: hợp lệ vì appName là String
```

Ở đây `global.set(null, null)` hoàn toàn có thể hợp lệ nếu field là **static, kiểu tham chiếu và có quyền ghi**.

## 6. Kiểm tra kiểu khai báo trước khi xử lý dữ liệu nullable

Trong code generic mapper, type của field là nguồn thông tin đáng tin cậy hơn việc suy từ giá trị hiện tại:

```java
// Đoạn minh họa trong một mapper: field đã được tìm,
// target là instance phù hợp; incoming đến từ bên ngoài.
Class<?> targetType = field.getType();

if (incoming == null && targetType.isPrimitive()) {
    throw new IllegalArgumentException(
            "Missing value for primitive field: " + field.getName());
}

field.set(target, incoming);
```

Đoạn này **không phải chương trình chạy độc lập**; các biến `field`, `target`, `incoming` là đầu vào của logic mapper. Nó chủ động từ chối input `null` trước khi gọi `Field.set` với primitive. Khi `incoming` khác `null`, vẫn cần bảo đảm object có kiểu tương thích với field (bao gồm unboxing/widening đúng luật); kiểm tra `null` **không thay thế toàn bộ validation**.

Nếu hệ thống cần phân biệt **“không cung cấp giá trị”** với **“cung cấp giá trị `0`”**, chỉ dùng primitive field là chưa đủ. Các phương án thường gặp:

- Dùng `Integer`, `Boolean`, `Double`... để thể hiện trạng thái nullable; quyết định khi nào phải từ chối `null`.
- Theo dõi sự hiện diện của input bằng key presence, dữ liệu request hoặc một trường cờ riêng, thay vì coi `0` là “không tồn tại”.
- Áp dụng mặc định **ở tầng business validation** một cách có chủ đích. Ví dụ, với một field `int retries`, thiếu dữ liệu có thể bị từ chối hoặc được gán `3` theo hợp đồng. Reflection tự nó không quyết định mặc định đó.
- Với object bất biến hoặc record, ưu tiên constructor/factory để thiết lập state hợp lệ thay vì cố ghi sâu vào field `final`.

Cẩn trọng khi dữ liệu từ JSON/database phân biệt `null` với giá trị thiếu: `null`, không có key và `0` là **ba trạng thái khác nhau** tùy schema. Reflection chỉ thực hiện đọc/ghi theo kiểu Java; không tự suy diễn ngữ nghĩa nghiệp vụ.

## 7. Access, `final` và lỗi không liên quan đến `null`

Trước khi đọc/ghi thành công, Reflection còn kiểm tra visibility và module access:

- `getField("name")` tra cứu field **public**; `getDeclaredField("name")` tra cứu field khai báo trực tiếp, bao gồm `private`. Tìm được private field **không tự có quyền** đọc/ghi nó.
- `Field.get`/`Field.set` có thể ném **`IllegalAccessException`** nếu caller không đủ quyền. Với named modules, `setAccessible(true)` có thể bị từ chối bằng **`InaccessibleObjectException`** nếu package chưa `opens` phù hợp.
- `final` không thay đổi quy tắc `null` của field; nhưng việc **ghi** `final` bằng Reflection còn có giới hạn riêng. Đặc biệt không nên coi `setAccessible(true)` là cách bảo đảm thay đổi mọi trường final, record component hay internal state.
- `getType()` lấy kiểu khai báo; nó không đọc giá trị và không cần receiver. `Field.get(null)` trên một static field có thể kích hoạt initialization của class đích.
- Nếu lỗi xảy ra trong quá trình khởi tạo tĩnh, thao tác trên static field có thể thất bại vì initializer của lớp; đó không phải bằng chứng rằng static receiver `null` bị cấm.

| Lỗi | Ngữ cảnh điển hình | Phân biệt với `null` value |
|---|---|---|
| `IllegalArgumentException` | Ghi `null` vào primitive, ghi wrapper không tương thích, narrowing bị cấm hoặc receiver sai kiểu | Cần xác định lỗi do **value** hay **receiver** |
| `NullPointerException` | Gọi `Field.get(null)`/`Field.set(null, ...)` trên **instance field** | `null` ở **receiver**, không phải field value |
| `IllegalAccessException` | Không được phép đọc/ghi member | Lỗi access, không phải primitive không có null |
| `NoSuchFieldException` | Không tìm được field đúng tên/phạm vi tra cứu | Xảy ra tại bước lookup |
| `InaccessibleObjectException` | Không thể bật deep access theo JPMS bằng `setAccessible(true)` | Lỗi encapsulation |
| `ExceptionInInitializerError` | Static initializer ném exception trong quá trình khởi tạo class | Có thể xuất hiện khi thực sự sử dụng static field |

## 8. Những nhầm lẫn thường gặp

1. **“`Field.get` trả `Object`, nên primitive field cũng có thể cho `null`.”** Sai: primitive được **boxing** thành wrapper không null.
2. **“`Integer` là primitive.”** Sai: `Integer` là reference type và có thể chứa `null`.
3. **“`Field.set(obj, null)` sẽ tự gán `0` cho `int`.”** Sai: thao tác ném `IllegalArgumentException`.
4. **“`Field.getInt` đọc được field khai báo `Integer` nếu wrapper không null.”** Sai: getter chuyên biệt này yêu cầu kiểu **primitive** có conversion phù hợp.
5. **“`Field.set` nhận mọi kiểu số và tự ép về primitive.”** Sai: chỉ unboxing/widening hợp lệ; **narrowing** không tự xảy ra.
6. **“`Field.get(null)` trả null vì receiver null.”** Sai: với **static field**, receiver null là hợp lệ và kết quả phụ thuộc giá trị field. Với instance field, receiver null gây lỗi.
7. **“`0` tương đương một field không có dữ liệu.”** Sai: `0` là giá trị primitive hợp lệ; missing/null cần biểu diễn ở mức model/schema khác nếu có ý nghĩa.
8. **“Field public luôn ghi được.”** Chưa đủ: quyền module, `final`, kiểu value và khả năng tương thích của receiver đều có thể ảnh hưởng.
9. **“`null` luôn dẫn đến `NullPointerException`.”** Sai: đối với `Field.set(receiver, null)` trên primitive thường là **`IllegalArgumentException`**; `NullPointerException` áp dụng trong trường hợp receiver instance bằng `null`.
10. **“Gọi `getClass()` lên giá trị vừa đọc luôn an toàn.”** Sai: với **reference field đang null**, `field.get(receiver)` trả `null`; gọi `getClass()` trên kết quả đó gây `NullPointerException`. Dùng `field.getType()` nếu muốn biết **declared type**.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Một class có `public int n;` (không gán tường minh). `Field.get(object)` trả giá trị nào?

**Đáp án:** Một `Integer` có giá trị `0` do boxing primitive `int`. Không phải `null`.

**Câu 2.** Một class có `public Integer n;` (không gán tường minh). `Field.get(object)` và `Field.getInt(object)` có gì khác?

**Đáp án:** `get` trả `null`. `getInt` ném `IllegalArgumentException` vì declared type là `Integer` (reference), dù sau này field được gán một wrapper không null.

**Câu 3.** `Field.set(instance, null)` có luôn gây lỗi không?

**Đáp án:** Không. Với reference field có thể ghi, việc gán `null` hợp lệ. Với primitive field, `null` bị từ chối bằng `IllegalArgumentException`.

**Câu 4.** `field.get(null)` có luôn gây `NullPointerException` không?

**Đáp án:** Không. Với static field, `null` là receiver hợp lệ. Với instance field, receiver null dẫn đến `NullPointerException`.

**Câu 5.** Field `public int n;` có được nhận `Short.valueOf((short) 5)` qua `Field.set` không? Có được nhận `Long.valueOf(5L)` không?

**Đáp án:** `Short` được unbox rồi widening `short -> int`, nên có thể gán. `Long` đòi hỏi narrowing `long -> int`, nên `Field.set` ném `IllegalArgumentException`.

**Câu 6.** Một serializer nhận JSON `{"age": null}` nhưng Java model khai báo `int age`. Reflection tự chọn xử lý ra sao?

**Đáp án:** `Field.set(target, null)` không thể đặt primitive `int` thành null và sẽ ném `IllegalArgumentException`. Serializer/application phải áp dụng schema: từ chối, đặt mặc định tường minh, hoặc đổi model sang `Integer` nếu nullable là trạng thái hợp lệ.

## Tài liệu chuẩn

- Java SE API — `java.lang.reflect.Field`: `get(Object)`, `getInt(Object)`, `set(Object, Object)`, `setInt(Object, int)`, `getType()` và các exception.
- Java SE API — `java.lang.Class`: `isPrimitive()`.
- Java Language Specification — §4.2 Primitive Types and Values; §4.3 Reference Types and Values; §4.12.5 Initial Values of Variables; §5.1.2 Widening Primitive Conversion; §5.1.7 Boxing Conversion; §5.1.8 Unboxing Conversion.

**Ghi nhớ:** `null` là trạng thái của **tham chiếu**; primitive không lưu được `null`. `Field.get` boxing primitive thành wrapper không null; `Field.set(receiver, null)` chỉ hợp lệ nếu **kiểu field** và quyền ghi cho phép. `receiver == null` lại là câu chuyện khác: dùng được với **static field**, nhưng không dùng được để đọc/ghi **instance field**.