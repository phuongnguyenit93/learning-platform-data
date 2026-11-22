# 3.1 Phân biệt `getMethods`, `getFields`, `getConstructors` với các biến thể `getDeclared`

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Chọn đúng API Reflection để liệt kê method, field hoặc constructor trên một `Class<?>`.
- Giải thích hai tiêu chí độc lập: **phạm vi kế thừa** và **mức truy cập** (`public`, `protected`, package-private, `private`).
- Hiểu vì sao `getDeclaredXxx()` có thể thấy thành viên `private` nhưng không thấy thành viên kế thừa; vì sao constructor là một ngoại lệ quan trọng.
- Tra cứu một thành viên theo tên và danh sách kiểu tham số, rồi kiểm tra `getDeclaringClass()` trước khi sử dụng.
- Phân biệt **tìm thấy metadata** với **được phép truy cập/gọi** thành viên, nhất là từ Java 9+ khi có module.

> Ý chính: **Không có `getDeclared()` chung.** `Declared` là một phần trong tên các API cụ thể: `getDeclaredMethods()`, `getDeclaredFields()`, `getDeclaredConstructors()` (và các phiên bản tìm một thành viên). `Declared` có nghĩa là **được khai báo bởi chính kiểu đang xét**, chứ không có nghĩa là “chỉ lấy private”.

## 2. Ma trận so sánh sáu API

Đầu vào của các API là một đối tượng `Class<?>`, chẳng hạn `Child.class` hoặc `object.getClass()`. Chúng trả về metadata thuộc `java.lang.reflect`; chúng không tự gọi method, đọc field hoặc khởi tạo object.

| API | Loại metadata | Mức truy cập được liệt kê | Có xét thành viên kế thừa? |
| --- | --- | --- | --- |
| `getMethods()` | `Method[]` | Các method `public` | **Có**: của class và được kế thừa từ superclass/superinterface |
| `getDeclaredMethods()` | `Method[]` | `public`, `protected`, package-private, `private` | **Không**: chỉ method khai báo tại kiểu hiện tại |
| `getFields()` | `Field[]` | Các field `public` | **Có**: của class và được kế thừa từ superclass/superinterface |
| `getDeclaredFields()` | `Field[]` | `public`, `protected`, package-private, `private` | **Không**: chỉ field khai báo tại kiểu hiện tại |
| `getConstructors()` | `Constructor<?>[]` | Các constructor `public` của chính class | **Không**: constructor không được kế thừa |
| `getDeclaredConstructors()` | `Constructor<?>[]` | Mọi constructor khai báo tại chính class | **Không**: constructor không được kế thừa |

Hai câu hỏi giúp chọn API:

1. **Cần xem thành viên public trong tập API nhìn thấy qua kiểu, có cả phần kế thừa?** Chọn `getMethods()` hoặc `getFields()`.
2. **Cần khảo sát thành viên do chính kiểu khai báo, kể cả private?** Chọn `getDeclaredMethods()` hoặc `getDeclaredFields()`.

Với constructor, chỉ cần hỏi **public hay mọi mức truy cập**; không có constructor kế thừa để tìm.

### 2.1. `getMethods()` và `getDeclaredMethods()`

- `getMethods()` trả về các method `public` được công bố trên class/interface và từ hệ phân cấp mà API này xét. Với một **class**, kết quả thường có cả các public method từ `Object`; với một **interface**, không tự thêm các method `Object` ngầm định.
- `getDeclaredMethods()` liệt kê các method thực sự khai báo trong kiểu đó: có thể chứa cả `private`, `protected`, package-private và `public`, nhưng **không duyệt lên superclass**. Method `public` kế thừa vẫn không xuất hiện nếu class con không tự khai báo/ghi đè nó.
- Method `private` ở class cha không “được kế thừa” theo nghĩa thông thường; nếu cần quan sát nó, phải lấy `Parent.class.getDeclaredMethods()`.
- Method do compiler tạo, chẳng hạn **bridge method** phục vụ generics/covariant return, cũng có thể xuất hiện. Đừng mặc định mỗi phần tử tương ứng một method viết trực tiếp trong mã nguồn.

### 2.2. `getFields()` và `getDeclaredFields()`

- `getFields()` trả về các field `public` của kiểu và các field `public` kế thừa. Hằng số khai báo trong interface là `public static final` theo mặc định, nên có thể xuất hiện qua class triển khai interface đó.
- `getDeclaredFields()` trả về mọi field **khai báo tại chính kiểu** bất kể modifier; không bao gồm field từ cha hoặc interface mà kiểu chỉ kế thừa.
- Field và method có quy tắc “ẩn”/“ghi đè” khác nhau: field **không override** theo cơ chế dispatch đa hình của method. Vì vậy không nên suy luận “cùng tên” nghĩa là cùng thành viên; đọc `Field.getDeclaringClass()` để xác định chủ sở hữu.

### 2.3. `getConstructors()` và `getDeclaredConstructors()`

- `getConstructors()` chỉ trả về các constructor `public` của **class hiện tại**.
- `getDeclaredConstructors()` trả về mọi constructor của **class hiện tại**, gồm constructor `private`, `protected`, package-private và `public`.
- **Constructor không được kế thừa**; `Child.class.getConstructors()` không bao giờ liệt kê constructor của `Parent` chỉ vì `Child extends Parent`.
- Constructor mặc định do trình biên dịch cung cấp (khi class không khai báo constructor nào) vẫn có thể được phản ánh như constructor của class đó. Interface, primitive, `void` và array không có constructor được liệt kê qua các API này.
- `getConstructors()` trả về mảng rỗng nếu class không có public constructor; điều đó **không** chứng minh class không thể có constructor private.

## 3. Ví dụ Java 17+ chạy độc lập

Ví dụ có superclass, interface với default method và hằng số, method/field public kế thừa, thành viên private của class con, cùng hai constructor ở mức truy cập khác nhau.

Lưu toàn bộ mã sau thành **`ReflectionInventoryDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;

interface Tagged {
    int CODE = 7; // ngầm định public static final
    default String tag() {
        return "tag";
    }
}

class Parent {
    public String inheritedField = "parent";
    protected int protectedField;
    private int privateField;

    public Parent() {}

    public void inheritedMethod() {}
    protected void protectedMethod() {}
    private void privateMethod() {}
}

class Child extends Parent implements Tagged {
    public int ownField;
    private int secret;

    public Child() {}
    private Child(int id) {}

    public void ownMethod() {}
    private void hiddenMethod() {}
}

public class ReflectionInventoryDemo {
    private static boolean hasMethod(Method[] methods, String name) {
        return Arrays.stream(methods)
                .anyMatch(method -> method.getName().equals(name));
    }

    private static boolean hasField(Field[] fields, String name) {
        return Arrays.stream(fields)
                .anyMatch(field -> field.getName().equals(name));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Class<Child> type = Child.class;

        System.out.println("inheritedMethod / getMethods: "
                + hasMethod(type.getMethods(), "inheritedMethod"));
        System.out.println("inheritedMethod / getDeclaredMethods: "
                + hasMethod(type.getDeclaredMethods(), "inheritedMethod"));
        System.out.println("tag / getMethods: "
                + hasMethod(type.getMethods(), "tag"));
        System.out.println("hiddenMethod / getMethods: "
                + hasMethod(type.getMethods(), "hiddenMethod"));
        System.out.println("hiddenMethod / getDeclaredMethods: "
                + hasMethod(type.getDeclaredMethods(), "hiddenMethod"));

        System.out.println("inheritedField / getFields: "
                + hasField(type.getFields(), "inheritedField"));
        System.out.println("CODE / getFields: "
                + hasField(type.getFields(), "CODE"));
        System.out.println("inheritedField / getDeclaredFields: "
                + hasField(type.getDeclaredFields(), "inheritedField"));
        System.out.println("secret / getFields: "
                + hasField(type.getFields(), "secret"));
        System.out.println("secret / getDeclaredFields: "
                + hasField(type.getDeclaredFields(), "secret"));

        System.out.println("constructors / getConstructors: "
                + type.getConstructors().length);
        System.out.println("constructors / getDeclaredConstructors: "
                + type.getDeclaredConstructors().length);

        System.out.println("inheritedMethod owner: "
                + type.getMethod("inheritedMethod")
                        .getDeclaringClass().getSimpleName());
        System.out.println("private ctor owner: "
                + type.getDeclaredConstructor(int.class)
                        .getDeclaringClass().getSimpleName());
    }
}
```

Chạy từ thư mục chứa file bằng JDK 17 trở lên:

```bash
javac ReflectionInventoryDemo.java
java ReflectionInventoryDemo
```

Kết quả chuẩn của ví dụ:

```text
inheritedMethod / getMethods: true
inheritedMethod / getDeclaredMethods: false
tag / getMethods: true
hiddenMethod / getMethods: false
hiddenMethod / getDeclaredMethods: true
inheritedField / getFields: true
CODE / getFields: true
inheritedField / getDeclaredFields: false
secret / getFields: false
secret / getDeclaredFields: true
constructors / getConstructors: 1
constructors / getDeclaredConstructors: 2
inheritedMethod owner: Parent
private ctor owner: Child
```

**Giải thích theo kết quả:**

- `inheritedMethod` là public method khai báo ở `Parent` và được `Child` kế thừa. Vì vậy `Child.class.getMethods()` thấy nó, còn `getDeclaredMethods()` của `Child` không thấy.
- `tag` là default method từ interface `Tagged`, có mặt trong tập public method của `Child`.
- `hiddenMethod` và field `secret` là private member do `Child` khai báo: chỉ các biến thể `getDeclared...` tương ứng liệt kê được chúng.
- `inheritedField` là public field của `Parent`, còn `CODE` là hằng số public của `Tagged`; `getFields()` của `Child` có thể thấy cả hai.
- `Child` khai báo một constructor public không tham số và một constructor private nhận `int`: kết quả lần lượt là **1** và **2**. Constructor `Parent()` không nằm trong kết quả của `Child`.
- `getDeclaringClass()` xác định **class khai báo thật sự**, không chỉ class mà ta đang dùng để truy vấn.

Đoạn mã kiểm tra **có/không** thay vì in trực tiếp toàn bộ mảng: thứ tự các phần tử mà Reflection trả về **không được bảo đảm**, và số public method từ thư viện nền tảng có thể làm danh sách dài, khó đối chiếu.

## 4. Tra cứu một thành viên theo tên

Khi biết sẵn tên hoặc chữ ký, dùng dạng số ít để tránh tự lặp qua mảng:

| Tìm trong public API, có kế thừa khi phù hợp | Tìm thành viên khai báo ngay tại kiểu |
| --- | --- |
| `getMethod("name", parameterTypes...)` | `getDeclaredMethod("name", parameterTypes...)` |
| `getField("fieldName")` | `getDeclaredField("fieldName")` |
| `getConstructor(parameterTypes...)` | `getDeclaredConstructor(parameterTypes...)` |

Ví dụ, sau khi có `Class<Child> type = Child.class`:

```java
// Các dòng này là trích đoạn minh họa, dùng trong ngữ cảnh ví dụ trên.
Method fromParent = type.getMethod("inheritedMethod");
Method ownPrivate = type.getDeclaredMethod("hiddenMethod");
Field inherited = type.getField("inheritedField");
Field ownPrivateField = type.getDeclaredField("secret");
var publicCtor = type.getConstructor();
var privateCtor = type.getDeclaredConstructor(int.class);
```

Các điểm cần nhớ:

- Đối với method, các tham số `Class<?>...` biểu diễn **kiểu tham số theo đúng thứ tự**, không phải giá trị argument: `getMethod("setAge", int.class)` khác `getMethod("setAge", Integer.class)`. Method không tham số dùng `getMethod("run")`.
- Kiểu trả về **không** nằm trong danh sách đối số của `getMethod`/`getDeclaredMethod`. Nếu cần phân biệt các dạng bridge/covariant, kiểm tra thêm `getReturnType()`, `isBridge()` và `isSynthetic()`.
- `getMethod` tìm public method theo quy tắc tìm kiếm thành viên của Reflection; `getDeclaredMethod` chỉ tra trong khai báo của đúng kiểu đó. Các API constructor tương ứng chỉ xét chính class.
- Không tìm thấy sẽ ném `NoSuchMethodException` (method/constructor) hoặc `NoSuchFieldException` (field); **không trả về `null`**. Nhiều chương trình cần `try/catch` hoặc khai báo `throws`.
- `getDeclaringClass()` trên `Method`, `Field`, `Constructor` giúp xác thực thành viên lấy được thuộc class/interface nào.

## 5. `getDeclaredXxx` không có nghĩa là đã được quyền truy cập

**Hai bước khác nhau:** (1) tìm metadata của thành viên, (2) thao tác trên thành viên bằng `Method.invoke`, `Field.get/set` hay `Constructor.newInstance`.

Ví dụ: `Child.class.getDeclaredMethod("hiddenMethod")` tìm được private method; thao tác `invoke` từ một class không có quyền truy cập vẫn có thể bị từ chối. Nếu ứng dụng có lý do hợp lệ cần reflective access, có thể kiểm tra:

```java
// Trích đoạn: giả sử đã có Child child và Method hidden lấy được ở trên.
if (hidden.trySetAccessible()) {
    hidden.invoke(child);
} else {
    // Không được mở truy cập; chọn public API hoặc cách tích hợp khác.
}
```

- `trySetAccessible()` trả về `false` khi không thể bật quyền truy cập sâu; `setAccessible(true)` có thể ném `InaccessibleObjectException` nếu module không mở package cho bên gọi.
- Trên Java 9+ (đặc biệt khi dùng named modules), **exports** và **opens** khác nhau: `exports` hỗ trợ truy cập kiểu/public API thông thường, còn reflective access vào non-public member của module khác thường cần package được `opens` thích hợp.
- Một thành viên có modifier `public` vẫn có thể không gọi được từ mọi nơi nếu kiểu khai báo hoặc ranh giới module không truy cập được. Việc xuất hiện trong `getMethods()` hoặc `getFields()` không phải giấy phép vượt qua access control.
- Chỉ mở quyền truy cập khi có chủ đích rõ ràng; ưu tiên API public. Không mặc định thêm `--add-opens` để khắc phục mọi lỗi, vì đó là thay đổi cấu hình đóng gói và có tác động tới tính bảo trì.

Lưu ý: đoạn `trySetAccessible` là **mã minh họa**, không phải một chương trình Java độc lập. Nó có thể đòi hỏi xử lý thêm checked exceptions từ `invoke` trong mã thực tế.

## 6. Những góc cạnh dễ gây nhầm lẫn

### 6.1. `getDeclaredMethods()` không đi lên cây kế thừa

Giả sử `GrandParent -> Parent -> Child`. Gọi `Child.class.getDeclaredMethods()` chỉ xét method do `Child` khai báo; gọi `Parent.class.getDeclaredMethods()` mới xét method khai báo ở `Parent`. Nếu cần mọi mức truy cập trên nhiều lớp, có thể **tự duyệt superclass**:

```java
// Trích đoạn minh họa, cần import java.lang.reflect.Method, java.util.*.
List<Method> declaredOnClassChain = new ArrayList<>();
for (Class<?> current = Child.class;
        current != null;
        current = current.getSuperclass()) {
    declaredOnClassChain.addAll(Arrays.asList(current.getDeclaredMethods()));
}
```

Đoạn trên cố ý chỉ duyệt **chuỗi superclass**, chưa duyệt các interface. Nếu yêu cầu bao gồm member khai báo trong interface cha, phải duyệt `getInterfaces()` đệ quy riêng, có tập `visited` để tránh thăm lặp và xử lý trùng chữ ký khi cần. Duyệt thủ công cũng không tự cho phép gọi private member.

### 6.2. `getMethods()` không đồng nghĩa với “mọi method có thể có”

- Nó chỉ liệt kê method **public** theo quy tắc của API; `protected`, package-private và `private` không được lấy chỉ vì chúng xuất hiện đâu đó trong hierarchy.
- Với class, các public method kế thừa từ `Object` (ví dụ `toString`) cũng có thể có mặt. Với interface, các method của `Object` ngầm định không được tự động thêm vào `getMethods()`.
- Method `static` của interface không được kế thừa bởi class triển khai như default method, vì vậy không suy ra `Child.class.getMethods()` phải thấy mọi static method của `Tagged`.
- Override, interface đa kế thừa, bridge method và return type hiệp biến có thể làm kết quả phức tạp hơn việc ghép thô các mảng của cha/con.

### 6.3. Không dựa vào thứ tự hoặc số lượng tuyệt đối

Javadoc không bảo đảm thứ tự của các mảng trả về. Nếu làm UI sinh tài liệu, snapshot test hoặc báo cáo, hãy **sắp xếp chủ động** theo tiêu chí phù hợp: tên, danh sách kiểu tham số, `getDeclaringClass()` và return type đối với method. Cũng đừng suy ra “có hai phần tử cùng tên tức là API lỗi”: method overload và bridge method là các trường hợp hợp lệ.

### 6.4. “Declared” là khai báo tại bytecode/class, không nhất thiết có dòng nguồn tương ứng

Compiler có thể sinh synthetic field/method, bridge method hoặc tham số constructor phục vụ các cấu trúc ngôn ngữ. Các API `getDeclared...` có thể phản ánh chúng. Khi dùng Reflection để sinh schema/JSON hoặc liệt kê API người dùng cần thấy, cân nhắc `Member.isSynthetic()`, `Method.isBridge()`, modifier và yêu cầu nghiệp vụ; không loại bỏ tất cả thành viên synthetic một cách mù quáng.

### 6.5. Class đặc biệt

- Với `String[].class`, các API liệt kê declared method/field không hoạt động như với class nguồn thông thường; array không có constructor riêng được liệt kê. `getMethods()` của array trả về public method kế thừa từ `Object` nhưng không liệt kê `clone()`.
- Với `int.class` hoặc `void.class`, không có constructor/method/field được khai báo như một class Java thông thường.
- Interface không có constructor; `getDeclaredMethods()` của interface có thể liệt kê các method do interface tự khai báo, gồm default, static và private method (nếu phù hợp phiên bản Java).

## 7. Chọn API trong tình huống thực tế

| Nhu cầu | API nên bắt đầu | Lý do |
| --- | --- | --- |
| Liệt kê public method mà caller có thể tìm qua một class, kể cả kế thừa | `getMethods()` | Bao phủ public method ở hierarchy |
| Tạo tài liệu cho các method *được khai báo trực tiếp* trong một class | `getDeclaredMethods()` | Không nhập method kế thừa; lọc modifier/bridge nếu cần |
| Quét annotation trên field do chính class sở hữu, kể cả private | `getDeclaredFields()` | Không bỏ sót field non-public do class khai báo |
| Liệt kê public constant từ class/interface và phần kế thừa | `getFields()` | Bao gồm public field từ hierarchy phù hợp |
| Tìm public no-arg constructor | `getConstructor()` | Chỉ constructor public của class hiện tại |
| Phân tích hoặc tìm private constructor | `getDeclaredConstructors()` / `getDeclaredConstructor(...)` | Thấy mọi mức truy cập, nhưng việc gọi còn bị kiểm soát |
| Thu thập private và protected field từ nhiều superclass | Duyệt `getSuperclass()` + `getDeclaredFields()` từng lớp | Không có một lệnh `getDeclaredFields()` tự duyệt toàn bộ hierarchy |

Đối với framework như DI, serializer hoặc ORM, **tiêu chí “ở đâu khai báo” và “mức truy cập nào” phải được xác định trước**. Chọn `getFields()` cho một entity có private field sẽ dễ dẫn tới kết quả thiếu dữ liệu; ngược lại, dùng `getDeclaredMethods()` để tìm public handler kế thừa có thể bỏ sót handler nằm ở cha.

## 8. Bài tập tự kiểm tra

1. `Parent` có `protected void audit()`, `Child` không override. `Child.class.getMethods()` và `Child.class.getDeclaredMethods()` có chứa `audit` không? **Đáp án:** cả hai không. `Parent.class.getDeclaredMethods()` có.
2. `Child` có `public void run()` và `private void reset()`. Muốn xem cả hai mà không xét method kế thừa, dùng gì? **Đáp án:** `Child.class.getDeclaredMethods()`.
3. `Parent` có `public Parent(String id)`, `Child` chỉ khai báo `public Child()`. `Child.class.getConstructors()` có constructor nhận `String` của `Parent` không? **Đáp án:** không, constructor không kế thừa.
4. `Child` có `private int count`. `Child.class.getDeclaredField("count")` chạy thành công có bảo đảm `field.get(child)` thành công từ class khác không? **Đáp án:** không; phải kiểm tra quyền truy cập và giới hạn module.
5. Một mảng `Method[]` từ `getDeclaredMethods()` xuất hiện bridge method. Có nên mặc định xem đó là lỗi Reflection? **Đáp án:** không; đây có thể là metadata hợp lệ do compiler tạo, cần kiểm tra `isBridge()`/`isSynthetic()` theo mục đích xử lý.

## 9. Ghi nhớ nhanh và tài liệu tham khảo

**Public + có kế thừa (method/field)** → `getMethods()` / `getFields()`. **Khai báo tại đúng kiểu + mọi mức truy cập** → `getDeclaredMethods()` / `getDeclaredFields()`. **Constructor không kế thừa** → `getConstructors()` chỉ public, `getDeclaredConstructors()` lấy mọi mức truy cập của chính class.

Khi nghi ngờ, kiểm tra `getDeclaringClass()`, `getModifiers()`, `isSynthetic()`, `isBridge()` (với method) và xử lý access control tách biệt với quá trình tra cứu.

- [Oracle Java SE 17 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): hợp đồng của `getMethods`, `getFields`, `getConstructors` và toàn bộ biến thể `getDeclared`.
- [Oracle Java SE 17 — `java.lang.reflect.AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible`, `setAccessible` và phạm vi kiểm soát truy cập phản chiếu.
- [Oracle Java SE 17 — `java.lang.Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): mô hình package `exports` và `opens` khi dùng module.
