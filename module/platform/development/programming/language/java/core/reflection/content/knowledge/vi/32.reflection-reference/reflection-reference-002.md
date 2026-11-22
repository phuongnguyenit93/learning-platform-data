# Bảng tra cứu: Class, Member, Executable, Field, Method và Constructor (Java Reflection)

## 1. Mục tiêu và cách đọc bảng

Java Reflection dùng các đối tượng metadata để mô tả kiểu và thành viên của chương trình lúc chạy. Sáu tên trong đề bài **không nằm trên cùng một mức của hệ phân cấp kiểu**:

- `Class<T>`: mô tả **một kiểu Java** (class, interface, enum, annotation, record, mảng, kiểu nguyên thủy hoặc `void`).
- `Member`: **interface** chung cho thành viên dạng field, method, constructor trong reflection.
- `Executable`: **abstract class** chung cho phương thức và constructor; có chung API về tham số, exceptions, annotations.
- `Field`: metadata của **trường dữ liệu**.
- `Method`: metadata của **phương thức**.
- `Constructor<T>`: metadata của **constructor** của một class.

Mục đích chính của bảng là xác định: **đối tượng nào giữ thông tin gì, API nào để tra cứu, và API nào dùng để thực thi hoặc truy cập giá trị**. Không nên học thuộc một danh sách method mà bỏ qua quan hệ của các kiểu.

## 2. Sơ đồ quan hệ chính xác

~~~text
java.lang.Object
  |
  +-- java.lang.Class<T>
  |     implements Type, AnnotatedElement, GenericDeclaration, ...
  |     (KHÔNG implements java.lang.reflect.Member)
  |
  +-- java.lang.reflect.AccessibleObject
        implements AnnotatedElement
        |
        +-- java.lang.reflect.Field
        |     implements Member
        |
        +-- java.lang.reflect.Executable (abstract)
              implements Member, GenericDeclaration
              |
              +-- java.lang.reflect.Method
              |
              +-- java.lang.reflect.Constructor<T>

java.lang.reflect.Member  (interface)
  |-- Field implements Member
  |-- Executable implements Member
      |-- Method inherits Member
      +-- Constructor<T> inherits Member
~~~

**Ba kết luận quan trọng:**

1. `Class<T>` là cửa vào tìm metadata và có thể đại diện cho **lớp lồng nhau**, nhưng bản thân `Class<T>` **không triển khai interface `Member`**. Đừng nhầm khái niệm “member class” của Java language với kiểu `java.lang.reflect.Member`.
2. `Field` và `Executable` đều là `AccessibleObject` và đều triển khai `Member`, nhưng `Field` **không** kế thừa `Executable`.
3. `Method` và `Constructor<T>` kế thừa API tham số từ `Executable`; tuy nhiên **chúng không dùng cùng API thực thi**: method gọi `invoke`, constructor tạo instance qua `newInstance`.

`AccessibleObject` không có nghĩa “mặc định được phép truy cập mọi thứ”: đây là lớp nền hỗ trợ kiểm tra/điều chỉnh quyền truy cập reflection trong giới hạn Java/JPMS. `AnnotatedElement` là interface cho các phương thức đọc annotation.

## 3. Bảng so sánh sáu API cốt lõi

| Kiểu | Bản chất | Đại diện cho | Cách lấy thường dùng | API đặc trưng |
| --- | --- | --- | --- | --- |
| `Class<T>` | Class trong `java.lang` | Một kiểu | `User.class`, `obj.getClass()`, `Class.forName(name)` | `getName`, `getSuperclass`, `getInterfaces`, `getDeclaredMethod`, `getDeclaredField`, `getDeclaredConstructor` |
| `Member` | Interface trong `java.lang.reflect` | Hợp đồng chung cho field/method/constructor | Nhận `Field`/`Method`/`Constructor` dưới kiểu `Member` | `getDeclaringClass`, `getName`, `getModifiers`, `isSynthetic` |
| `Executable` | Abstract class trong `java.lang.reflect` | Phần chung của method/constructor | Nhận `Method` hoặc `Constructor` dưới kiểu `Executable` | `getParameterCount`, `getParameters`, `getParameterTypes`, `getExceptionTypes`, `isVarArgs` |
| `Field` | Class trong `java.lang.reflect` | Một trường khai báo trong class/interface | `clazz.getField` / `getDeclaredField` | `getType`, `getGenericType`, `get`, `set`; getter/setter primitive như `getInt`/`setInt` |
| `Method` | Class kế thừa `Executable` | Một phương thức với tên + parameter types + return type | `clazz.getMethod` / `getDeclaredMethod` | `getReturnType`, `getGenericReturnType`, `invoke`, `isBridge`, `isDefault` |
| `Constructor<T>` | Class kế thừa `Executable` | Một constructor của class `T` | `clazz.getConstructor` / `getDeclaredConstructor` | `newInstance`, `getDeclaringClass`, các API tham số từ `Executable` |

**Không có `Member.invoke()` hay `Executable.invoke()` chung cho mọi subtype.** Nếu chỉ giữ biến kiểu `Member`, ta đọc được metadata phổ quát nhưng không thể gọi ngay `get`/`set`/`invoke`/`newInstance` mà không phân nhánh theo subtype.

### 3.1. Ghi chú về các kiểu trung gian và interface khác

- `java.lang.reflect.Type` là interface biểu diễn **kiểu** trong generic reflection. `Class<?>` vừa là một `Type`, nhưng `ParameterizedType` và `TypeVariable` là các biến thể khác; không mặc định mọi `Type` ép được về `Class`.
- `GenericDeclaration` áp dụng cho `Class`, `Method`, `Constructor` thông qua `Executable`; có `getTypeParameters()` cho khai báo type variables như `<T>`.
- `AnnotatedElement` cho phép đọc annotation trên class, field, method, constructor. Annotation ở **tham số** còn có thể lấy từ `Parameter`.
- `Parameter` là metadata **từng tham số** của `Executable`; không phải một trong sáu kiểu của bảng, nhưng rất thường gặp khi gọi `getParameters()`.
- `Modifier` là utility class với `Modifier.isPublic(int)`, `isPrivate(int)`, `isStatic(int)`... Nó giúp diễn giải bitmask trả về từ `Member.getModifiers()`.

## 4. Từ `Class<?>` đến Member: chọn phạm vi tra cứu

`Class<?>` là điểm xuất phát để lấy `Field`, `Method` và `Constructor`. Các cặp `getX`/`getDeclaredX` không thay đổi **kiểu đối tượng kết quả**; chúng thay đổi **phạm vi tra cứu**:

| Loại | Public/member lookup | Khai báo trực tiếp ở mọi mức truy cập |
| --- | --- | --- |
| Field | `getField(name)`, `getFields()` | `getDeclaredField(name)`, `getDeclaredFields()` |
| Method | `getMethod(name, types...)`, `getMethods()` | `getDeclaredMethod(name, types...)`, `getDeclaredMethods()` |
| Constructor | `getConstructor(types...)`, `getConstructors()` | `getDeclaredConstructor(types...)`, `getDeclaredConstructors()` |

Với field và method, tra cứu public có thể thấy member kế thừa; bản declared chỉ thấy khai báo ngay trên kiểu hiện tại. **Constructor không kế thừa**, nên cả hai nhóm constructor đều thuộc chính class đang hỏi. Kết quả mảng không bảo đảm thứ tự; một chữ ký method cần **tên + kiểu tham số chính xác sau erasure**, chẳng hạn `int.class` khác `Integer.class`.

Sự khác biệt này là **quy tắc tìm metadata**, không phải quyền dùng metadata. Một `Method` private có thể xuất hiện từ `getDeclaredMethod` nhưng `invoke` vẫn đòi access phù hợp. Cần biết nơi khai báo, đọc `member.getDeclaringClass()`; nó không nhất thiết trùng runtime class của receiver. Chương trình ở mục 7 thể hiện rõ `Field`/`Method`/`Constructor` và hành động tương ứng của mỗi subtype.

## 5. Member và Executable: API dùng chung và những khác biệt

### 5.1. Member — interface mức tối thiểu

Mọi `Field`, `Method`, `Constructor` triển khai `Member` và cung cấp:

| Phương thức | Diễn giải | Ghi chú |
| --- | --- | --- |
| `getDeclaringClass()` | Class/interface khai báo member | Không mặc định là subclass của object nhận lời gọi |
| `getName()` | Tên member | Với `Constructor`, tên là **tên binary của declaring class** (không phải một method tên `<init>`) |
| `getModifiers()` | Bitmask modifier | Dùng `Modifier.isPublic/isStatic/isFinal`... |
| `isSynthetic()` | Member do compiler tạo theo ngữ nghĩa synthetic | Có ích khi quét bridge/synthetic members |

**Không ép mọi subtype về `Method`.** Nếu code scan nhận `Member member`, kiểm tra loại bằng `instanceof Field`, `instanceof Method`, `instanceof Constructor<?>` khi cần hành vi chuyên biệt.

### 5.2. Executable — method/constructor dùng chung tham số

Với biến kiểu `Executable executable`, áp dụng được cả method lẫn constructor:

- `getParameterCount()` và `getParameterTypes()`: số lượng và kiểu tham số runtime (sau type erasure).
- `getParameters()`: mảng `Parameter` với `getName()`, `isNamePresent()`, `getType()`, `getAnnotations()`...
- `getGenericParameterTypes()`, `getAnnotatedParameterTypes()`: biểu diễn generic và type-use annotation của tham số.
- `getExceptionTypes()` / `getGenericExceptionTypes()`: kiểu exceptions khai báo trong phần `throws`.
- `getParameterAnnotations()`: annotations ở từng vị trí tham số.
- `isVarArgs()`, `getTypeParameters()`: method/constructor varargs và khai báo type variables.
- `toGenericString()`: mô tả chữ ký có thông tin generic; dùng để chẩn đoán, không dùng như parser API ổn định.

Tên tham số gốc **không bảo đảm được giữ lại** trong bytecode khi không biên dịch với `javac -parameters`. Khi đó `Parameter.getName()` có thể là `arg0`, `arg1` và `isNamePresent()` là false. Số lượng/kiểu tham số vẫn có thể tra cứu như thường.

## 6. Field, Method và Constructor: API riêng và tác dụng

| Loại | Thông tin chỉ ra | Hành động | Lưu ý quan trọng |
| --- | --- | --- | --- |
| `Field` | Tên, modifier, type (raw/generic), annotation của field | `field.get(receiver)`, `field.set(receiver, value)`, getter/setter primitive | Truy cập field không phải gọi getter/setter; field instance cần receiver phù hợp |
| `Method` | Return type, parameter types, exceptions, bridge/default/synthetic flags | `method.invoke(receiver, args...)` | Exception do method đích ném bị `InvocationTargetException` bọc |
| `Constructor<T>` | Tham số, exceptions, modifier/annotations của constructor | `constructor.newInstance(args...)` | Tạo object của declaring class; lỗi trong constructor có thể bị `InvocationTargetException` bọc |

Các điểm phân biệt thường bị hỏi:

- `Field.getType()` trả một `Class<?>` của kiểu field sau erasure; `Field.getGenericType()` trả `Type`, có thể là `ParameterizedType` đối với `List<String>`.
- `Method.getReturnType()` trả `Class<?>`. `Method.getGenericReturnType()` có thể trả `ParameterizedType`/`TypeVariable`; constructor **không** có kiểu trả về như method và **không có** API `getReturnType()`.
- `Method.isBridge()` nhận diện bridge method do compiler sinh, thường để bảo toàn đa hình với generic/covariant return; `Method.isDefault()` xác nhận default method của interface.
- `Constructor.newInstance(...)` nên được dùng thay cho `Class.newInstance()` (API cũ deprecated) vì tường minh constructor và có cách bọc lỗi nhất quán hơn.
- `Field.get`/`set` và `Method.invoke` cho static member dùng receiver `null`; instance member cần receiver tương thích.
- Không phải `getDeclaredXxx` tìm được là có thể invoke/get/set ngay: Java access checks và giới hạn JPMS vẫn áp dụng.

### 6.1. Access checks và JPMS

`Field`, `Method`, `Constructor` kế thừa `AccessibleObject`:

- `canAccess(receiver)` hỏi khả năng truy cập với receiver thích hợp; đối với static member hoặc constructor, receiver truyền `null`.
- `trySetAccessible()` cố bật chế độ bỏ qua một số Java access checks, trả true/false tùy khả năng; `setAccessible(true)` có thể ném `InaccessibleObjectException` nếu module không mở quyền cần thiết.
- Không tự động gọi `setAccessible(true)` trên toàn bộ thành viên khi scan: chỉ xin quyền thực sự cần, xử lý lỗi và tôn trọng exports/opens của module.

**Reflection access không thay thế authorization nghiệp vụ.** `public` hoặc đọc được metadata không có nghĩa request HTTP hiện tại được phép gọi method.

## 7. Ví dụ Java 17+ hoàn chỉnh: sáu kiểu trong một chương trình

Lưu thành **MemberTableDemo.java**. Ví dụ dùng lookup theo tên/chữ ký để tránh phụ thuộc thứ tự mảng reflection, minh họa một field private, một field generic, một method và một constructor public.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Field;
import java.lang.reflect.Member;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.ParameterizedType;
import java.util.List;

public class MemberTableDemo {
    public static final class Sample {
        private final String title;
        public List<String> tags = List.of("reflection");

        public Sample(String title) {
            this.title = title;
        }

        public String echo(String prefix) {
            return prefix + ":" + title;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Sample> type = Sample.class;

        Field title = type.getDeclaredField("title");
        Field tags = type.getDeclaredField("tags");
        Method echo = type.getDeclaredMethod("echo", String.class);
        Constructor<Sample> ctor = type.getDeclaredConstructor(String.class);

        System.out.println("Class: " + type.getSimpleName());
        System.out.println("Class is Member: "
                + Member.class.isAssignableFrom(Class.class));
        System.out.println("Field: " + title.getName()
                + " | type=" + title.getType().getSimpleName()
                + " | private=" + Modifier.isPrivate(title.getModifiers()));
        System.out.println("Method: " + echo.getName()
                + " | return=" + echo.getReturnType().getSimpleName()
                + " | params=" + echo.getParameterCount());
        System.out.println("Constructor: " + ctor.getDeclaringClass().getSimpleName()
                + " | params=" + ctor.getParameterCount());

        System.out.println("Field is Executable: "
                + Executable.class.isAssignableFrom(Field.class));
        System.out.println("Method is Executable: " + (echo instanceof Executable));
        System.out.println("Constructor is Executable: " + (ctor instanceof Executable));
        System.out.println("Method is Member: " + (echo instanceof Member));

        ParameterizedType generic = (ParameterizedType) tags.getGenericType();
        System.out.println("Generic field raw=" + tags.getType().getSimpleName()
                + ", actual=" + generic.getActualTypeArguments()[0].getTypeName());
        System.out.println("Inherited public method declares="
                + type.getMethod("toString").getDeclaringClass().getSimpleName());

        Sample sample = ctor.newInstance("Java");
        System.out.println("Invoke result: " + echo.invoke(sample, "Hi"));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 MemberTableDemo.java
java MemberTableDemo
~~~

Output dự kiến:

~~~text
Class: Sample
Class is Member: false
Field: title | type=String | private=true
Method: echo | return=String | params=1
Constructor: Sample | params=1
Field is Executable: false
Method is Executable: true
Constructor is Executable: true
Method is Member: true
Generic field raw=List, actual=java.lang.String
Inherited public method declares=Object
Invoke result: Hi:Java
~~~

**Đọc kết quả đúng theo hệ phân cấp:**

1. `Class is Member: false` chứng minh kiểu `Class` không triển khai interface `Member`.
2. Field `title` private vẫn tìm được bằng `getDeclaredField` nhưng ví dụ **không** đọc hoặc sửa giá trị private field bằng reflection, nên không cần bật `setAccessible`.
3. `Method` và `Constructor` là `Executable`, còn `Field` thì không.
4. Field `tags` khai báo `List<String>`: `getType()` trả raw `List`, còn `getGenericType()` biểu diễn `ParameterizedType` có argument `java.lang.String`.
5. `type.getMethod("toString")` lấy một method public kế thừa từ `Object`, khác `getDeclaredMethod` chỉ tìm method của `Sample`.
6. `ctor.newInstance("Java")` tạo object; `echo.invoke(sample, "Hi")` thực thi method và trả `"Hi:Java"`.

Nếu dùng `type.getField("title")` thay vì `getDeclaredField("title")` thì nhận `NoSuchFieldException`, vì `title` là private. Nếu dùng `type.getDeclaredMethod("toString")` thì cũng nhận `NoSuchMethodException` vì `Sample` không khai báo override `toString`.

## 8. Cách chọn đúng API theo câu hỏi thực tế

| Câu hỏi của bạn | API thích hợp | Vì sao? |
| --- | --- | --- |
| Đối tượng này thuộc kiểu runtime nào? | `object.getClass()` | Nhận `Class<?>` của object |
| Tìm method public có thể gọi theo kiểu? | `type.getMethod("save", Id.class)` | Cho phép method public được kế thừa |
| Tìm method được khai báo trực tiếp, kể cả private? | `type.getDeclaredMethod(...)` | Phạm vi đúng class; quyền invoke là bước khác |
| Đọc metadata tên/modifier/declaring class của nhiều member? | Biến/collection kiểu `Member` | Không phụ thuộc subtype cụ thể |
| Tạo cùng logic kiểm tra signature cho method và constructor? | Biến kiểu `Executable` | Chung `getParameters/getExceptionTypes/isVarArgs` |
| Tìm thông tin kiểu của field? | `Field.getType/getGenericType` | Field có loại dữ liệu, không có return type |
| Thực thi method? | `Method.invoke` | Receiver + đối số; exception từ method đích được bọc |
| Tạo object bằng constructor? | `Constructor.newInstance` | Không dùng `Method.invoke` cho constructor |
| Đọc annotation trên member? | `AnnotatedElement.getAnnotation(...)` | `Class` và member classes cùng hỗ trợ interface phù hợp |
| Tìm annotation trên parameter? | `Executable.getParameters()` → `Parameter.getAnnotation(...)` | Parameter là thành phần riêng, không phải `Member` |

**Trường hợp generic:** nếu `Type t = field.getGenericType()`, hãy kiểm tra `t instanceof ParameterizedType` trước khi cast. Với field kiểu `String`, `getGenericType()` có thể trả `Class<String>`, không phải `ParameterizedType`. Khi generic signature không hợp lệ hoặc thiếu type, API metadata generic có thể ném những lỗi đặc thù khác.

## 9. Lỗi phổ biến và giới hạn

1. **Nhầm Class với Member:** một nested class là member theo ngôn ngữ Java, nhưng metadata `Class<?>` của nó không thể ép thành `java.lang.reflect.Member`.
2. **Dùng Executable cho Field:** `Field` không có `getParameters()`, cũng không có `invoke()`.
3. **Gọi Constructor như Method:** constructor không có kiểu trả về hoặc `Method.invoke`; dùng `Constructor.newInstance`.
4. **Nhầm public với declared:** `getDeclaredMethod` không quét member kế thừa; `getMethod` không tìm private method.
5. **Nhầm metadata với quyền sử dụng:** `getDeclaredField` tìm được private field không có nghĩa `field.get(receiver)` luôn hợp lệ.
6. **Đoán thứ tự mảng reflection:** `getDeclaredFields()` và `getDeclaredMethods()` không cam kết trả theo thứ tự source.
7. **Nhầm raw type với generic type:** `getType/getReturnType/getParameterTypes` chưa giữ toàn bộ cấu trúc parameterized type; dùng `getGenericType/getGenericReturnType/getGenericParameterTypes` khi cần.
8. **Hiểu sai tên constructor:** trong reflection `Constructor.getName()` là **binary name** của declaring class, không phải tên `<init>` trong bytecode.
9. **Dùng reflection trong hot path mà không cache:** nếu phải lặp lại lookup cùng chữ ký, có thể cache `Method/Field/Constructor` theo đúng declaring class và signature; đo trước khi tối ưu.
10. **Không xử lý exception thích hợp:** lookup thường ném `NoSuchFieldException`/`NoSuchMethodException`; invoke/newInstance có thể ném `IllegalAccessException`, `IllegalArgumentException`, `InvocationTargetException`; ngoại lệ lớp đích phải được kiểm tra từ `getCause()`.

## 10. Checklist ghi nhớ nhanh

- `Class` = **mô tả kiểu và điểm xuất phát lookup**.
- `Member` = **interface metadata chung** của field/method/constructor.
- `Executable` = **lớp chung method + constructor**, chuyên thông tin parameters/exceptions.
- `Field` = **dữ liệu**: type, get, set.
- `Method` = **hành vi có tên**: return type, invoke, bridge/default.
- `Constructor` = **khởi tạo object**: parameters, newInstance.
- `getXxx` thường tìm public phù hợp và có thể kế thừa đối với field/method; `getDeclaredXxx` tìm member khai báo trực tiếp, kể cả non-public.
- Chọn API bằng **ngữ nghĩa của thao tác**, sau đó mới cân nhắc cache, quyền truy cập, lỗi và hiệu năng.

**Câu hỏi tự kiểm tra:**

1. Vì sao `Member.class.isAssignableFrom(Class.class)` trả false?
2. Nếu muốn kiểm tra số lượng tham số của cả method và constructor, dùng chung kiểu nào?
3. Vì sao field private vẫn được tìm thấy bằng `getDeclaredField` nhưng chưa chắc truy cập được bằng `Field.get`?
4. `Method.getReturnType` và `Field.getType` giống và khác nhau thế nào?
5. Tại sao `getMethod("toString")` thành công, còn `getDeclaredMethod("toString")` trên `Sample` lại không?
6. Khi phản xạ vào `List<String>`, vì sao nên xem `Type`/`ParameterizedType` thay vì chỉ `Class<?>`?

### Nguồn tra cứu API chính thức

- `Class` (Java SE 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- `Member`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Member.html
- `Executable`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html
- `Field`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html
- `Method`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html
- `Constructor`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html
- `AccessibleObject`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- `Parameter`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html