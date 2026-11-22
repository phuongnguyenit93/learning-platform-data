# NoSuchFieldException và NoSuchMethodException trong Java Reflection

## 1. Bản chất của lỗi tra cứu thành viên

Khi làm việc với Java Reflection, ứng dụng có thể chỉ biết tên field hoặc method dưới dạng chuỗi ở thời điểm chạy. Những API như `Class.getField`, `Class.getDeclaredField`, `Class.getMethod` và `Class.getDeclaredMethod` sẽ tra cứu metadata của lớp. Nếu **không có thành viên thỏa đúng phạm vi tra cứu và chữ ký yêu cầu**, chúng có thể ném checked exception:

- `java.lang.NoSuchFieldException`: không tìm được field phù hợp với tên và quy tắc tìm kiếm của phương thức được gọi.
- `java.lang.NoSuchMethodException`: không tìm được method/constructor phù hợp với tên, **danh sách kiểu tham số**, phạm vi kế thừa và quy tắc visibility của phương thức tra cứu.

Hai exception đều thuộc họ `ReflectiveOperationException`, nên Java yêu cầu xử lý bằng `try/catch` hoặc khai báo `throws`. Chúng **không đồng nghĩa** với việc class hoàn toàn không có thành viên đó: thành viên có thể tồn tại nhưng là `private`, được khai báo ở superclass, nhận tham số khác, hoặc chỉ có trên một class loader/type khác.

Ví dụ, cùng trường `count` là private trong `Child`:

```java
Child.class.getDeclaredField("count"); // Tìm thấy field private khai báo tại Child
Child.class.getField("count");         // Ném NoSuchFieldException
```

Đây là mảnh minh họa, giả định lớp `Child` như ví dụ đầy đủ bên dưới. Sự khác nhau nằm ở **cách tra cứu**, không phải vì JVM “làm mất” field.

## 2. Bảng chọn đúng API

| Nhu cầu | API | Thành viên được xem xét | Exception nếu không có kết quả |
|---|---|---|---|
| Tìm field `public` có thể kế thừa | `type.getField("name")` | Field public của lớp/interface theo quy tắc tìm kiếm public member, kể cả những field thừa kế hợp lệ | `NoSuchFieldException` |
| Tìm field **khai báo ngay tại lớp** (kể cả private) | `type.getDeclaredField("name")` | Field trong chính `type`, không tự đi lên superclass | `NoSuchFieldException` |
| Tìm method `public` (kể cả inherited) | `type.getMethod("name", ParamType.class)` | Public methods phù hợp theo tên và kiểu tham số | `NoSuchMethodException` |
| Tìm method **khai báo ngay tại lớp** (kể cả private) | `type.getDeclaredMethod("name", ParamType.class)` | Methods của chính `type`, không tự tìm ở superclass | `NoSuchMethodException` |
| Tìm constructor `public` | `type.getConstructor(ParamType.class)` | Public constructor của chính lớp | `NoSuchMethodException` |
| Tìm constructor kể cả `private` | `type.getDeclaredConstructor(ParamType.class)` | Constructor khai báo bởi chính lớp | `NoSuchMethodException` |

**Điểm cần nhớ:** một method có thể được tìm thấy bởi `getDeclaredMethod` nhưng **không truy cập/gọi được** trong hoàn cảnh hiện tại. Bước *tra cứu* khác với bước *cho phép truy cập* và bước *thực thi*.

### “Declared” không có nghĩa là “dùng được mọi nơi”

- `getDeclaredField` và `getDeclaredMethod` trả metadata của thành viên khai báo ở lớp hiện tại, dù `private`, `protected` hay package-private.
- Các quy tắc truy cập vẫn được kiểm tra khi `Field.get/set`, `Method.invoke` hoặc constructor được sử dụng.
- Java Module System có thể chặn hành động cố mở truy cập sâu qua `setAccessible(true)` nếu package không được `opens` phù hợp. Có thể gặp `InaccessibleObjectException` hoặc `IllegalAccessException` tùy hành động.
- Nếu thực sự cần hỗ trợ private member, phải có hợp đồng truy cập rõ ràng; đừng mặc định gọi `setAccessible(true)` là đủ.

## 3. Vì sao NoSuchFieldException xuất hiện?

### 3.1. Tên field không tồn tại hoặc sai chính tả

`getField("userId")` sẽ không tìm ra field tên `userID`. Java phân biệt chữ hoa/chữ thường. Không truyền tên kiểu `"com.example.Person.userId"` hoặc `"Person.userId"`: tham số là **tên thành viên đơn lẻ**, không phải qualified path.

### 3.2. Dùng getField với field không public

`getField` chỉ tìm public field. Một field private có thể tồn tại nhưng lời gọi vẫn ném `NoSuchFieldException`. Nếu ứng dụng sở hữu lớp và thật sự cần metadata private, dùng `getDeclaredField` rồi kiểm tra quyền truy cập riêng.

### 3.3. Dùng getDeclaredField để tìm field kế thừa

`getDeclaredField` chỉ tìm trực tiếp trong `Class` đích. Nếu `Parent` khai báo `public String label`, còn `Child extends Parent` không khai báo lại field đó, `Child.class.getDeclaredField("label")` ném `NoSuchFieldException`. Trong trường hợp public inherited member, `Child.class.getField("label")` phù hợp hơn.

Nếu cần duyệt **mọi mức superclass** (kể cả non-public fields), có thể chủ động lặp `getDeclaredField` từ class hiện tại lên cha. Đừng dùng `getFields()` để mong liệt kê toàn bộ trường private.

### 3.4. Nhầm field với property hoặc accessor

Một JavaBean có thể có `getName()` mà **không có field `name`**, hoặc field có tên khác với property. Với `record`, các record component có accessor method riêng; không đồng nhất mọi property với field public. Hãy xác định đúng metadata cần đọc: field, method, bean property hay record component.

## 4. Vì sao NoSuchMethodException xuất hiện?

### 4.1. Sai tên, phạm vi hoặc visibility

`getMethod` chỉ tìm public method phù hợp, kể cả inherited methods. `getDeclaredMethod` tìm cả method không public nhưng chỉ ở lớp đang tra cứu. Vì vậy method `private void reset()` có thể tìm thấy qua `getDeclaredMethod("reset")` nhưng không qua `getMethod("reset")`.

### 4.2. Danh sách kiểu tham số phải khớp chính xác

`Class.getMethod` và `getDeclaredMethod` nhận tên method và **danh sách `Class<?>` của các tham số khai báo**. Cơ chế tìm kiếm này không thực hiện quy đổi overload giống lời gọi Java thông thường:

- `int.class` **khác** `Integer.class` (không auto-boxing trong tra cứu).
- `String.class` **khác** `Object.class` (không tự chọn overload qua widening/reference conversion).
- `String[].class` là kiểu tham số đã biên dịch của `String...` (varargs), không phải nhiều `String.class` riêng lẻ.
- Với generics, tra cứu theo kiểu **sau type erasure**: ví dụ method nhận `List<String>` thì thường phải tìm với `List.class`. Không tồn tại `List<String>.class`.
- Thứ tự và số lượng tham số phải đúng: `getMethod("move", int.class, long.class)` khác `getMethod("move", long.class, int.class)`.
- Method không tham số: `getMethod("run")` hoặc `getMethod("run", new Class<?>[0])`.

Ví dụ:

```java
// Nếu lớp có greet(String), greet(int), không có greet(Object).
type.getMethod("greet", String.class);  // Tìm được
type.getMethod("greet", int.class);     // Tìm được
type.getMethod("greet", Integer.class); // NoSuchMethodException
type.getMethod("greet", Object.class);  // NoSuchMethodException
```

Ở đây `type` là `Class<Child>` trong ví dụ hoàn chỉnh.

**Kiểu trả về không phải đối số của `getMethod`.** Sau khi tìm được `Method`, dùng `method.getReturnType()` để kiểm tra return type. Với các trường hợp compiler sinh bridge method/covariant return, kết quả tìm kiếm có thể liên quan nhiều method cùng tên và parameter types ở mức bytecode; nếu cần chẩn đoán, xem `isBridge()`, `isSynthetic()` và metadata trả về, thay vì giả định mỗi tên + tham số luôn ánh xạ duy nhất tới một method bytecode.

### 4.3. Tìm nhầm constructor hoặc static initializer

Constructor không có tên như ordinary method để `getMethod("Child")` tra cứu. Dùng `getConstructor(...)` / `getDeclaredConstructor(...)`. Khối `static { ... }` cũng không phải ordinary method public được tìm qua `getMethod`.

### 4.4. Nhìn nhầm interface/class được tải

Hai class loader có thể định nghĩa những kiểu cùng binary name nhưng khác runtime identity. `getMethod("accept", SomeType.class)` sẽ thất bại nếu method thật nhận một `SomeType` khác được nạp bởi loader khác, dù hai `Class.getName()` trông giống nhau. Khi debug hệ plugin, hãy xem cả `getClassLoader()`/`getModule()` và kiểu tham số thực tế.

## 5. Ví dụ Java 17+ chạy độc lập: từ ngoại lệ đến sửa đúng API

Lưu mã sau vào **`MissingMembersDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class MissingMembersDemo {
    static class Parent {
        public String label = "parent";
        public void inherited() {}
    }

    static class Child extends Parent {
        private int count = 7;
        private void reset() {}
        public String greet(String name) { return "Hello, " + name; }
        public String greet(int count) { return "Number: " + count; }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Child> type = Child.class;
        Field inheritedField = type.getField("label");
        System.out.println("getField(label) owner: " +
                inheritedField.getDeclaringClass().getSimpleName());

        try {
            type.getDeclaredField("label");
        } catch (NoSuchFieldException e) {
            System.out.println("getDeclaredField(label): " + e.getClass().getSimpleName());
        }

        Field count = type.getDeclaredField("count");
        System.out.println("getDeclaredField(count) private: " +
                Modifier.isPrivate(count.getModifiers()));

        try {
            type.getField("count");
        } catch (NoSuchFieldException e) {
            System.out.println("getField(count): " + e.getClass().getSimpleName());
        }

        Method inherited = type.getMethod("inherited");
        System.out.println("getMethod(inherited) owner: " +
                inherited.getDeclaringClass().getSimpleName());

        try {
            type.getDeclaredMethod("inherited");
        } catch (NoSuchMethodException e) {
            System.out.println("getDeclaredMethod(inherited): " + e.getClass().getSimpleName());
        }

        Method reset = type.getDeclaredMethod("reset");
        System.out.println("getDeclaredMethod(reset) private: " +
                Modifier.isPrivate(reset.getModifiers()));

        Method greetString = type.getMethod("greet", String.class);
        System.out.println("getMethod(greet,String) return: " +
                greetString.getReturnType().getSimpleName());

        try {
            type.getMethod("greet", Object.class);
        } catch (NoSuchMethodException e) {
            System.out.println("getMethod(greet,Object): " + e.getClass().getSimpleName());
        }

        try {
            type.getMethod("greet", Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("getMethod(greet,Integer): " + e.getClass().getSimpleName());
        }

        System.out.println("getMethod(greet,int) found: " +
                (type.getMethod("greet", int.class) != null));
        System.out.println("invoke greet: " + greetString.invoke(new Child(), "Lan"));
    }
}
```

Chạy trong thư mục có file:

```bash
javac MissingMembersDemo.java
java MissingMembersDemo
```

Kết quả stdout:

```text
getField(label) owner: Parent
getDeclaredField(label): NoSuchFieldException
getDeclaredField(count) private: true
getField(count): NoSuchFieldException
getMethod(inherited) owner: Parent
getDeclaredMethod(inherited): NoSuchMethodException
getDeclaredMethod(reset) private: true
getMethod(greet,String) return: String
getMethod(greet,Object): NoSuchMethodException
getMethod(greet,Integer): NoSuchMethodException
getMethod(greet,int) found: true
invoke greet: Hello, Lan
```

Cách đọc kết quả:

1. `label` thuộc `Parent`: `getField("label")` tìm được public inherited field; `getDeclaredField("label")` thất bại trên `Child`.
2. `count` là private field khai báo ở `Child`: `getDeclaredField` tìm được; `getField` không tìm được.
3. `inherited()` thuộc `Parent`: `getMethod` thấy public inherited method; `getDeclaredMethod` chỉ tra cứu method trực tiếp trong `Child`.
4. `reset()` là private method của `Child`: `getDeclaredMethod` trả metadata; ví dụ chỉ kiểm tra modifiers, không cố gọi method đó qua ranh giới truy cập.
5. `greet` có overload `String` và `int`, không có `Object` hay `Integer`. Hai lần tìm với kiểu không khớp ném `NoSuchMethodException`.
6. `Method.invoke` trên public method được tìm thấy cho ra kết quả. Đây là bước **gọi method**, riêng biệt với bước **tra cứu metadata**.

Ví dụ đã biên dịch và chạy trên JDK 24 với cú pháp tương thích Java 17+. Stdout phía trên là kết quả của chương trình, không chứa tên lớp sinh ngẫu nhiên.

## 6. Quy trình chẩn đoán khi gặp exception

Thay vì sửa tên method/field theo suy đoán, tiến hành có thứ tự.

**Bước 1 — Xác định đúng Class đang tra cứu.** In ra tên, class loader và module của nó khi cần: `type.getName()`, `type.getClassLoader()` và `type.getModule().getName()`. Lưu ý `getClassLoader()` có thể trả `null` với bootstrap loader; tên module cũng có thể `null` với unnamed module.

**Bước 2 — Xác định API và phạm vi.** Nếu truy vấn `getDeclaredMethod` trên class con nhưng method nằm ở cha, đổi sang `getMethod` nếu method public, hoặc chủ động duyệt superclass khi thật sự cần non-public inherited member.

**Bước 3 — Kiểm tra chữ ký chính xác.** Với method, liệt kê `Method.getParameterTypes()` để xem runtime `Class<?>` của từng parameter; không dựa vào chỉ mỗi tên method. Kiểm tra overload, primitive/wrapper, arrays/varargs, generics erasure và method bridge.

**Bước 4 — Kiểm tra visibility và module access.** Nếu tìm thấy member nhưng không thể truy cập, xử lý theo `IllegalAccessException` / `InaccessibleObjectException` hoặc chính sách module, không biến vấn đề đó thành `NoSuchMethodException`.

**Bước 5 — Xác nhận phiên bản và classpath/runtime.** Một dependency được biên dịch ở version mới nhưng thực thi với class version cũ có thể thiếu member. Khi metadata runtime thật sự không có thành viên, điều chỉnh dependency/API hoặc phát hiện capability một cách tường minh.

### Helper liệt kê candidates để debug

Đây là đoạn code minh họa dùng trong một context đã có biến `type` (kiểu `Class<?>`). Nó không phải chương trình chạy độc lập:

```java
for (Method method : type.getDeclaredMethods()) {
    System.out.println(method.toGenericString());
}

for (Field field : type.getDeclaredFields()) {
    System.out.println(field.toGenericString());
}
```

`getDeclaredMethods`/`getDeclaredFields` chỉ liệt kê những thành viên **khai báo trực tiếp** trên `type`. Khi nghi ngờ lỗi do kế thừa, so sánh với `getMethods`/`getFields` hoặc lần theo `getSuperclass()`. Thứ tự phần tử của các mảng Reflection không nên được coi là thứ tự khai báo ổn định.

Để theo dõi tên và parameter types một cách có cấu trúc:

```java
for (Method method : type.getMethods()) {
    if (method.getName().equals("greet")) {
        System.out.println(java.util.Arrays.toString(method.getParameterTypes()));
    }
}
```

Đây cũng là **mảnh minh họa** với `type` đã được định nghĩa. Dùng lọc tên để tránh log toàn bộ API không liên quan và hạn chế làm lộ thông tin nội bộ.

## 7. Phân biệt exception tra cứu và lỗi thực thi

| Hiện tượng | Exception/Error tiêu biểu | Giai đoạn |
|---|---|---|
| Không tìm được field bằng `getField` hoặc `getDeclaredField` | `NoSuchFieldException` (checked) | Tra cứu Reflection |
| Không tìm được method/constructor qua API `Class` | `NoSuchMethodException` (checked) | Tra cứu Reflection |
| Không tìm được chính lớp theo tên chuỗi | `ClassNotFoundException` (checked) | Nạp/tìm class |
| Tìm được member nhưng không có quyền đọc/gọi | `IllegalAccessException`; có thể `InaccessibleObjectException` khi cố mở sâu | Truy cập Reflection |
| Truyền sai đối số cho `Method.invoke` | `IllegalArgumentException` (runtime) | Gọi Reflection |
| Method đích ném exception | `InvocationTargetException` bao lỗi của method đích | Gọi Reflection |
| Bytecode đã biên dịch trỏ tới field/method không còn tương thích khi liên kết/chạy | `NoSuchFieldError` / `NoSuchMethodError` (thuộc `LinkageError`) | Liên kết/phân giải lời gọi bytecode |

**Đặc biệt: `NoSuchMethodException` khác `NoSuchMethodError`.** Exception là kết quả của một **truy vấn Reflection không tìm ra member**; Error thường phản ánh **mất tương thích nhị phân** hoặc dependency runtime không như lúc biên dịch. Không sửa `NoSuchMethodError` bằng cách bắt `NoSuchMethodException` và coi là hết lỗi. Với `NoSuchFieldError` cũng tương tự.

`NoSuchMethodException` còn có thể xuất hiện khi tra cứu constructor qua `getConstructor`/`getDeclaredConstructor` dù tên exception chứa chữ “Method”; không có `NoSuchConstructorException` riêng trong các API này.

## 8. Xử lý lỗi trong ứng dụng thật

### Bắt đúng loại lỗi và ghi lại dữ liệu chẩn đoán hữu ích

```java
try {
    java.lang.reflect.Method method =
            componentType.getMethod("execute", String.class);
    // Tiếp tục dùng method trong luồng đã kiểm soát.
} catch (NoSuchMethodException e) {
    throw new IllegalStateException(
            "Thiếu public method execute(String) trên " +
                    componentType.getName(), e);
}
```

Đây là **mảnh code minh họa**: `componentType` là biến `Class<?>` trong ứng dụng; `componentType.getMethod` chỉ xác nhận metadata. Giữ exception làm `cause` để không làm mất stack trace. Trong hệ plugin hoặc thư viện có nhiều loader, thêm tên loader/module vào log chẩn đoán nếu có ích.

### Chọn fallback khi tính năng thực sự là tùy chọn

Một số thư viện hỗ trợ nhiều phiên bản API có thể dùng Reflection để kiểm tra method mới. Khi đó **chỉ fallback với trường hợp đã dự tính**, không nuốt mọi `ReflectiveOperationException`:

```java
boolean available;
try {
    apiType.getMethod("newFeature");
    available = true;
} catch (NoSuchMethodException e) {
    available = false;
}
```

Mảnh minh họa giả định `apiType` đã có. Điều kiện `available=false` nói rằng method `public newFeature()` **không tra cứu được theo chữ ký không tham số trên `apiType`**, chứ không chứng minh tính năng hoàn toàn không tồn tại. Phải xác định fallback hợp lệ và phiên bản API hỗ trợ trước khi dùng.

Không nên:

- `catch (Exception ignored)` rồi âm thầm bỏ qua lỗi cấu hình, classpath hoặc truy cập.
- Mặc định dùng `getDeclaredMethod` với `setAccessible(true)` để phá giới hạn encapsulation chỉ nhằm xử lý exception.
- Duyệt method theo thứ tự bất kỳ và gọi phần tử đầu tiên trùng tên mà không kiểm tra chữ ký.
- Bỏ qua vấn đề class loader, đặc biệt ở container, plugin hoặc application server.

## 9. Trường hợp nâng cao: field hiding, overload và version drift

**Field hiding:** nếu subclass khai báo field trùng tên với superclass, đó là hai field khác nhau có declaring class khác nhau. `getDeclaredField` trên subclass trả field do subclass khai báo; muốn truy vấn field của cha hãy gọi `Superclass.class.getDeclaredField(...)`. Không giả định chỉ có một field trùng tên trong toàn bộ hierarchy.

**Method overload:** việc trong class tồn tại method `process(int)` không làm `getMethod("process", Integer.class)` thành công. Reflection lookup không chạy Java overload resolution, boxing hoặc varargs packing giúp bạn.

**Varargs:** với `void log(String... messages)`, danh sách parameter types chỉ gồm `String[].class`. Ví dụ tra cứu đúng là `getMethod("log", String[].class)`. Khi gọi qua `Method.invoke` còn có quy tắc truyền mảng Object[] và varargs riêng; tách việc tìm chữ ký khỏi việc chuẩn bị arguments.

**Generics:** compiler xóa phần lớn type arguments nên lookup cần dùng erased parameter class. Khi thư viện/framework sinh bridge method, metadata có thể chứa method `isBridge() == true`; nên phân tích đầy đủ thay vì lấy method đầu tiên cùng tên.

**Version drift:** `getDeclaredMethod` thất bại có thể do library đã đổi API, method được chuyển lên parent class, signature thay đổi hoặc runtime đang dùng JAR khác. Kiểm tra dependency lock/version và class loader thực tế trước khi vá reflection string.

## 10. Checklist thực hành

1. Xác nhận **đúng class** và module/loader cần tra cứu.
2. Chọn `get...` khi cần public inherited member, `getDeclared...` khi cần khai báo trực tiếp.
3. Với method/constructor, đối chiếu **số lượng, thứ tự và Class của từng tham số**, bao gồm primitive, array và erased generic types.
4. Đừng nhầm lỗi “không tìm thấy” với lỗi truy cập hoặc exception do method đích ném.
5. Khi chỉ kiểm tra API tùy chọn, fallback có chủ đích và ghi được nguyên nhân.
6. Khi API thay đổi phiên bản, ưu tiên cập nhật dependency và sử dụng API công khai ổn định.
7. Viết test cho cả đường tra cứu thành công và trường hợp thiếu member được dự tính.

## 11. Tóm tắt

- `NoSuchFieldException` là checked exception khi **tra cứu field** không khớp tên/phạm vi.
- `NoSuchMethodException` là checked exception khi **tra cứu method hoặc constructor** không khớp tên, parameter types hay phạm vi.
- `getField/getMethod` hướng tới **public members** (có xét kế thừa hợp lệ); `getDeclaredField/getDeclaredMethod` hướng tới **members khai báo trực tiếp** bất kể visibility.
- Reflection yêu cầu parameter `Class<?>` **khớp chính xác**; không áp dụng boxing, widening hoặc overload resolution tự động.
- Tìm thấy metadata chưa chứng minh có quyền truy cập hoặc gọi thành công; `NoSuchMethodError` và `NoSuchFieldError` là **linkage errors khác bản chất**.
