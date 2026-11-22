# getMethods() khác getDeclaredMethods() trong Java Reflection

`Class.getMethods()` và `Class.getDeclaredMethods()` đều trả về `Method[]` để khám phá phương thức của một kiểu Java, nhưng giải quyết **hai nhu cầu khác nhau**. Nhầm hai API này sẽ làm công cụ Reflection bỏ sót phương thức kế thừa, bỏ sót private method, chọn sai phương thức để invoke hoặc phụ thuộc vô tình vào implementation.

- **`getMethods()`:** lấy các phương thức **public** của kiểu đang xét, gồm phương thức public được khai báo trực tiếp và phương thức public được kế thừa theo quy tắc Java.
- **`getDeclaredMethods()`:** lấy **các phương thức được khai báo trực tiếp** trên chính class/interface đang xét, ở **mọi mức truy cập**: public, protected, package-private và private; **không** bao gồm phương thức kế thừa.

Từ `declared` trong tên API có nghĩa là **được khai báo trực tiếp tại Class đang xét**, không phải kiểu khai báo của biến tham chiếu. Để dùng đúng, phải chọn cả đối tượng `Class<?>` và nhóm API tìm kiếm phù hợp.

## 1. So sánh trực tiếp hai API

Hai chữ ký API thuộc `java.lang.Class`:

```java
public Method[] getMethods()
public Method[] getDeclaredMethods()
```

Cả hai trả về `java.lang.reflect.Method`, nhưng khác **phạm vi tra cứu** và **quy tắc visibility**.

| Loại phương thức | `getMethods()` | `getDeclaredMethods()` |
| --- | --- | --- |
| Public, khai báo ngay trong class | Có | Có |
| Protected, khai báo ngay trong class | Không | Có |
| Package-private, khai báo ngay trong class | Không | Có |
| Private, khai báo ngay trong class | Không | Có |
| Public, kế thừa từ lớp cha | Có | Không |
| Public instance/default, kế thừa từ interface | Có | Không |
| Private/protected được khai báo ở lớp cha | Không | Không |
| Public từ `Object` trên class thông thường | Có, theo quy tắc chọn method cụ thể nhất | Không, trừ khi đang xét chính `Object.class` |
| Bridge/synthetic method do compiler khai báo ở class file | Có thể có nếu public và được chọn trong kết quả | Có thể có, ở mọi access |
| Constructor | Không | Không |
| Class initializer `<clinit>` | Không | Không |

Không nên suy diễn rằng `getMethods()` bằng cách nối tất cả mảng `getDeclaredMethods()` của class cha/con: Java áp dụng quy tắc method membership, overriding/hiding, lựa chọn phương thức cụ thể hơn và interface inheritance. Một mảng không bảo đảm thứ tự; nếu cần kết quả ổn định, **tự sắp xếp**.

Một class có thể chứa phương thức `private` nhưng `getMethods()` vẫn không thấy. Ngược lại, một class không khai báo phương thức nào vẫn có thể trả về rất nhiều phần tử từ `getMethods()` nhờ kế thừa phương thức public của `Object`.

## 2. Chọn đúng Class trước khi chọn API

Xét đoạn minh họa:

```java
Parent ref = new Child();

Class<?> staticType = Parent.class;
Class<?> runtimeType = ref.getClass(); // Child.class
```

Kiểu khai báo của `ref` là `Parent`. Kiểu thực tế của đối tượng được tham chiếu là `Child`. Hai API hoạt động trên **kiểu mà bạn gọi chúng**, vì vậy:

- `Parent.class.getDeclaredMethods()`: chỉ phương thức khai báo tại `Parent`.
- `Parent.class.getMethods()`: tập phương thức public của `Parent`, bao gồm public method kế thừa.
- `Child.class.getDeclaredMethods()`: chỉ phương thức khai báo tại `Child`, kể cả method private.
- `Child.class.getMethods()`: public method của `Child` và public method kế thừa thích hợp.

Một đối tượng Reflection `Method` còn có `getDeclaringClass()` để biết **lớp/interface nào thực sự khai báo phương thức đó**. Lớp khai báo có thể khác `Class<?>` dùng để bắt đầu tìm kiếm.

## 3. Chương trình Java 17+ đầy đủ

Tạo tệp `MethodDiscoveryDemo.java`:

```java
import java.lang.reflect.Method;

public class MethodDiscoveryDemo {
    interface Named {
        default String label() {
            return "from-interface";
        }
    }

    static class Parent {
        public String parentOnly() {
            return "parent";
        }

        public String describe() {
            return "Parent";
        }

        protected void protectedParent() {
        }

        private void privateParent() {
        }
    }

    static final class Child extends Parent implements Named {
        @Override
        public String describe() {
            return "Child";
        }

        public String childOnly() {
            return "child";
        }

        protected void protectedChild() {
        }

        private void privateChild() {
        }
    }

    static boolean contains(Method[] methods, String name) {
        for (Method method : methods) {
            if (method.getName().equals(name)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<?> type = Child.class;
        Method[] publicMethods = type.getMethods();
        Method[] declaredMethods = type.getDeclaredMethods();

        System.out.println("public parentOnly: "
                + contains(publicMethods, "parentOnly"));
        System.out.println("declared parentOnly: "
                + contains(declaredMethods, "parentOnly"));
        System.out.println("public childOnly: "
                + contains(publicMethods, "childOnly"));
        System.out.println("declared childOnly: "
                + contains(declaredMethods, "childOnly"));
        System.out.println("public label: "
                + contains(publicMethods, "label"));
        System.out.println("declared label: "
                + contains(declaredMethods, "label"));
        System.out.println("public privateChild: "
                + contains(publicMethods, "privateChild"));
        System.out.println("declared privateChild: "
                + contains(declaredMethods, "privateChild"));
        System.out.println("public protectedChild: "
                + contains(publicMethods, "protectedChild"));
        System.out.println("declared protectedChild: "
                + contains(declaredMethods, "protectedChild"));
        System.out.println("public toString: "
                + contains(publicMethods, "toString"));
        System.out.println("declared toString: "
                + contains(declaredMethods, "toString"));

        Method inherited = type.getMethod("parentOnly");
        System.out.println("parentOnly declared in: "
                + inherited.getDeclaringClass().getSimpleName());

        Method overridden = type.getMethod("describe");
        System.out.println("describe declared in: "
                + overridden.getDeclaringClass().getSimpleName());

        Method fromParent = Parent.class.getMethod("describe");
        System.out.println("invoke Parent.describe on Child: "
                + fromParent.invoke(new Child()));

        try {
            type.getDeclaredMethod("parentOnly");
        } catch (NoSuchMethodException e) {
            System.out.println("declared parentOnly lookup: missing");
        }

        try {
            type.getMethod("privateChild");
        } catch (NoSuchMethodException e) {
            System.out.println("public privateChild lookup: missing");
        }
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac MethodDiscoveryDemo.java
java MethodDiscoveryDemo
```

Kết quả stdout:

```text
public parentOnly: true
declared parentOnly: false
public childOnly: true
declared childOnly: true
public label: true
declared label: false
public privateChild: false
declared privateChild: true
public protectedChild: false
declared protectedChild: true
public toString: true
declared toString: false
parentOnly declared in: Parent
describe declared in: Child
invoke Parent.describe on Child: Child
declared parentOnly lookup: missing
public privateChild lookup: missing
```

Chương trình kiểm tra **có tồn tại theo tên hay không**, nên output cố định dù thứ tự phần tử Reflection trả về thay đổi. Trong ứng dụng thật, tên method có thể overload; cần kiểm tra thêm tham số chứ không chỉ dùng hàm `contains` này.

Ý nghĩa từng nhóm kết quả:

1. `parentOnly()` là phương thức public **kế thừa** từ `Parent`. Tập `getMethods()` của `Child` nhìn thấy; tập `getDeclaredMethods()` không thấy.
2. `childOnly()` là public method **khai báo trực tiếp** ở `Child`, nên thấy trong cả hai tập.
3. `label()` là default method public của interface `Named`. `Child` kế thừa nó nhưng không tự khai báo; do đó chỉ thấy trong tập public tổng hợp.
4. `privateChild()` và `protectedChild()` được khai báo tại `Child`. Chúng xuất hiện trong tập declared; không phải public nên không xuất hiện trong tập `getMethods()`.
5. `toString()` có từ `Object`. Class thông thường kế thừa public method này, còn `Child` không trực tiếp khai báo nó.
6. `getDeclaringClass()` của `parentOnly` là `Parent`. Còn `describe` được override ở `Child`, nên method public được chọn trên `Child` có declaring class là `Child`.
7. `Parent.class.getMethod("describe").invoke(new Child())` trả về `"Child"` vì **dynamic dispatch** của instance method. Chọn metadata từ lớp cha không ép JVM gọi phần thân lớp cha.
8. `getDeclaredMethod("parentOnly")` trên `Child` và `getMethod("privateChild")` đều thất bại, nhưng vì **hai lý do khác nhau**: cái đầu không thuộc phần khai báo trực tiếp; cái sau không phải public.

## 4. Interface, Object và những trường hợp đặc biệt

### Public default method của interface

```java
interface HasName {
    default String name() {
        return "unknown";
    }
}

class Person implements HasName {
}
```

Trong đoạn minh họa này:

- `Person.class.getMethods()` thấy `name()` vì đây là public instance method được kế thừa từ interface.
- `Person.class.getDeclaredMethods()` không thấy `name()` vì class không khai báo phương thức đó.
- `HasName.class.getDeclaredMethods()` thấy `name()` vì interface khai báo trực tiếp.

Ngược lại, một **static method khai báo trên interface không được thừa kế bởi implementing class** theo cùng cách như default instance method. Một private method của interface cũng không phải public member method của class triển khai. Luôn phân biệt static/default/private khi xử lý interface.

### Object methods trên class và interface

Đối với class thường, `getMethods()` bao gồm public method thích hợp từ `Object`, trừ khi một override cụ thể hơn thay thế phương thức đó trong kết quả. Đối với **interface**, mảng `getMethods()` **không tự chứa các method ngầm định từ `Object`**. Vì vậy:

```java
interface Empty {
}
```

`Empty.class.getMethods()` là một mảng rỗng; không tự thêm `toString()` hoặc `hashCode()`. Đây là điểm khác với `new Object().getClass().getMethods()`.

Đối với **array class**, `getMethods()` trả các public method kế thừa từ `Object`, nhưng không trả `clone()`. Còn `getDeclaredMethods()` trên array type, primitive type hoặc `void` trả mảng rỗng.

### Phương thức override và method bị ẩn

Khi lớp con override instance method public của lớp cha, `getMethods()` áp dụng quy tắc chọn phương thức phù hợp và ưu tiên khai báo cụ thể hơn. Với method static, việc lớp con khai báo method cùng signature là **hiding**, không phải dynamic override. Do vậy đừng chỉ so sánh tên để suy luận method sẽ chạy khi invoke.

## 5. Lấy một Method theo tên và chữ ký

Hai API tương ứng với việc lấy một phương thức cụ thể:

```java
Class<?> type = Example.class;

Method first = type.getMethod("run", String.class);
Method second = type.getDeclaredMethod("run", String.class);
```

Đây là đoạn minh họa, `Example` cần tồn tại và có method phù hợp; xử lý `NoSuchMethodException` khi tra cứu thất bại.

| API | Phạm vi |
| --- | --- |
| `getMethod(name, parameterTypes...)` | Tìm **public member method**, kể cả được kế thừa |
| `getDeclaredMethod(name, parameterTypes...)` | Tìm method **được khai báo trực tiếp**, bất kể access |

Tham số của hai phương thức nhận các `Class<?>` đại diện cho **kiểu tham số hình thức** (formal parameter types), theo đúng thứ tự, **không phải kiểu trả về**. Với overload:

```java
class Printer {
    public void print(String text) {
    }

    public void print(int number) {
    }
}
```

Các lệnh tìm method đúng:

```java
Method textMethod = Printer.class.getMethod("print", String.class);
Method numberMethod = Printer.class.getMethod("print", int.class);
```

Đây là mã minh họa; khai báo `Method` cần `import java.lang.reflect.Method;` và lời gọi có thể ném `NoSuchMethodException`.

`getMethod("print", Object.class)` không tự áp dụng phép chọn overload theo chuyển kiểu `Object`/`String` trong mã nguồn: phải dùng đúng danh sách kiểu tham số đã khai báo. Đối với varargs, metadata của tham số cuối là kiểu **mảng**, ví dụ `String[].class`; dùng `Method.isVarArgs()` để biết đặc tính varargs.

`getMethod` và `getDeclaredMethod` không trả constructor. Nếu cần tìm constructor, dùng `getConstructor(...)` hoặc `getDeclaredConstructor(...)`.

## 6. Có Method metadata không đồng nghĩa được invoke

`getDeclaredMethods()` liệt kê cả private method, nhưng khả năng nhìn thấy metadata **không tự cấp quyền** gọi method đó.

```java
Method method = type.getDeclaredMethod("privateAction");
Object result = method.invoke(target);
```

Đây là đoạn minh họa, chỉ chạy được khi `type`, `target`, chữ ký và quyền truy cập phù hợp. `invoke` có thể ném `IllegalAccessException` nếu method không accessible; một method được invoke có thể ném ngoại lệ nghiệp vụ được bọc trong `InvocationTargetException`.

Một số code sử dụng `method.setAccessible(true)` hoặc `trySetAccessible()` để yêu cầu cho phép truy cập sâu. Nhưng trên Java 17+, **strong encapsulation của JPMS** có thể từ chối vì package của named module không mở cho caller. `setAccessible(true)` có thể ném `InaccessibleObjectException`; `trySetAccessible()` có thể trả `false`. Điều này không liên quan đến việc method có được trả về bởi `getDeclaredMethods()` hay không.

Với API ứng dụng, ưu tiên phương thức public hoặc interface/factory rõ ràng. Dùng Reflection sâu cho thành viên không public khi thật sự có lý do và được cấp quyền phù hợp.

## 7. Bridge và synthetic methods khiến mảng khác mã nguồn

`getDeclaredMethods()` không hứa mỗi phần tử tương ứng với một method do người lập trình tự viết. Compiler có thể sinh thêm **bridge** hoặc **synthetic methods**, điển hình khi generic erasure hoặc covariant return type ảnh hưởng đến phương thức override.

```java
class Holder<T> {
    public T value() {
        return null;
    }
}

class TextHolder extends Holder<String> {
    @Override
    public String value() {
        return "text";
    }
}
```

Đoạn minh họa này thường được `javac` biên dịch ra một method `String value()` và một bridge method tương thích chữ ký JVM mang kiểu trả về `Object`. Vì vậy `TextHolder.class.getDeclaredMethods()` có thể chứa hơn một method cùng tên `value`.

Kiểm tra metadata:

```java
for (java.lang.reflect.Method method
        : TextHolder.class.getDeclaredMethods()) {
    System.out.println(method.getName()
            + ", bridge=" + method.isBridge()
            + ", synthetic=" + method.isSynthetic());
}
```

Đoạn mã cần `TextHolder` đã được khai báo ở trên, không phải một chương trình độc lập. Thứ tự dòng không được bảo đảm. `getMethods()` cũng có thể trả method bridge public trong tập kết quả phù hợp.

Nên lọc `isBridge()` hoặc `isSynthetic()` **theo mục đích**: với bộ duyệt “API do developer chủ động khai báo” thường có thể cần lọc; với công cụ phân tích bytecode/compatibility thì nên giữ để phản ánh class file thực tế.

Về lý thuyết một class file có thể có nhiều method cùng **tên và kiểu tham số** nhưng khác kiểu trả về, dù Java source không cho phép khai báo overload chỉ khác return type. Vì vậy các phương thức tra cứu đơn `getMethod`/`getDeclaredMethod` có quy tắc lựa chọn khi nhiều ứng viên cùng tên và tham số; không giả định mảng `getDeclaredMethods()` luôn có đúng một phần tử ứng với mỗi cặp tên/tham số.

## 8. Duyệt đủ hierarchy khi cần cả method không public kế thừa về mặt cấu trúc

Không có một lời gọi `getDeclaredMethods()` nào trên `Child.class` tự lấy cả private/protected method khai báo ở mọi lớp cha. Nếu đang viết inspector cần xem **mỗi khai báo trên toàn class hierarchy**, hãy duyệt:

```java
Class<?> current = Child.class;

while (current != null) {
    for (java.lang.reflect.Method method
            : current.getDeclaredMethods()) {
        System.out.println(current.getSimpleName()
                + "." + method.getName());
    }
    current = current.getSuperclass();
}
```

Đây là đoạn minh họa sử dụng `Child` từ ví dụ ở mục 3. Các lưu ý:

- Vòng lặp chỉ duyệt **chuỗi class cha**, không duyệt superinterfaces. Muốn phân tích interface phải xử lý thêm `getInterfaces()` và hierarchy của chúng.
- Phương thức override ở lớp con và phương thức cùng chữ ký ở lớp cha có thể xuất hiện như **hai khai báo riêng**; đừng tự loại trùng nếu cần biết nguồn gốc từng method.
- Thứ tự mảng `getDeclaredMethods()` không được bảo đảm; cần sắp xếp nếu xuất báo cáo ổn định.
- Một phương thức private của lớp cha có thể được liệt kê metadata, nhưng không vì thế trở thành method public kế thừa của lớp con.

Nếu mục tiêu chỉ là API public có thể gọi từ bên ngoài, `getMethods()` thường ngắn gọn và sát hơn, không cần tự duyệt toàn bộ hierarchy.

## 9. Sắp xếp và lọc Method để công cụ ổn định

Khi in danh sách Reflection ra tài liệu, UI hoặc kết quả kiểm thử, không phụ thuộc thứ tự do JVM trả về. Ví dụ:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

class MethodPrinter {
    static void printPublic(Class<?> type) {
        Method[] methods = type.getMethods();

        Arrays.sort(methods,
                Comparator.comparing(Method::getName)
                        .thenComparing(Method::toGenericString));

        for (Method method : methods) {
            System.out.println(method.getName() + " -> "
                    + method.getDeclaringClass().getName());
        }
    }
}
```

Đoạn này là class tiện ích minh họa, không có `main` riêng. Comparator làm thứ tự nhất quán **đối với cùng tập metadata**. Tập public methods vẫn có thể thay đổi khi kiểu hoặc phiên bản JDK đổi.

Một số bộ lọc hữu ích:

- `Modifier.isPublic(method.getModifiers())` để kiểm tra cờ public khi đang phân tích `getDeclaredMethods()`.
- `method.getDeclaringClass() == type` để tìm method có declaring class chính là kiểu đang xét.
- `method.isBridge()` / `method.isSynthetic()` để xử lý các method do compiler sinh.
- `method.getParameterTypes()`, `method.getReturnType()`, `method.isVarArgs()` khi cần phân biệt method theo chữ ký.
- `method.getAnnotation(YourAnnotation.class)` khi cần annotation cụ thể; phải xác định chính sách tìm annotation trên khai báo trực tiếp, override hoặc interface thay vì giả định annotation trên method tự động kế thừa.

Đừng lọc `getMethods()` bằng `getDeclaringClass()==type` rồi cho rằng kết quả bằng `getDeclaredMethods()`: cách đó vẫn **thiếu các method không public**.

## 10. Nên chọn API nào?

| Nhu cầu | Khuyến nghị |
| --- | --- |
| Liệt kê public API của class/interface cùng public methods được kế thừa | `getMethods()` |
| Tìm public member method theo tên + danh sách kiểu tham số | `getMethod(...)` |
| Kiểm kê method khai báo trực tiếp tại class, kể cả private/protected | `getDeclaredMethods()` |
| Tìm một method trực tiếp bất kể access | `getDeclaredMethod(...)` |
| Quét annotation trên toàn bộ khai báo của class hierarchy | Duyệt từng class và dùng `getDeclaredMethods()`, thêm interface khi cần |
| Chỉ lấy method thuộc một class nhất định | Kiểm tra `getDeclaringClass()`, đồng thời chọn tập đầu vào tương ứng yêu cầu access |
| Xuất kết quả theo thứ tự nhất quán | Sắp xếp `Method[]` bằng comparator |
| Gọi method không public | Xác minh nhu cầu, quyền truy cập Java/JPMS và receiver trước khi invoke |

Một lưu ý về proxy/framework: `obj.getClass()` có thể trả **runtime proxy class**, không phải class khai báo hợp đồng nghiệp vụ. Nếu muốn kiểm tra đúng API mà consumer được phép dùng, hãy bắt đầu bằng `YourInterface.class` hoặc class hợp đồng được cấu hình. Nếu mục tiêu là debug implementation, dùng runtime class với chính sách lọc phù hợp.

## 11. Sai lầm thường gặp

1. **Nhầm declared với kiểu biến:** `object.getClass().getDeclaredMethods()` khám phá method trực tiếp của **runtime class**, không phải kiểu static của biến.
2. **Tưởng `getMethods()` chỉ lấy method tự viết:** nó lấy cả public method từ superclass, interface và thường từ `Object`.
3. **Tưởng `getDeclaredMethods()` bao gồm private method ở lớp cha:** chỉ bao gồm private method khai báo **trên chính kiểu đang xét**.
4. **Thấy `Method` rồi lập tức `invoke`:** quyền truy cập, đối tượng receiver, kiểu tham số, JPMS và checked exceptions vẫn cần được xử lý.
5. **Lọc theo tên nhưng quên overload:** cần xét kiểu tham số, đôi khi kiểu trả về và bridge method.
6. **So số method trực tiếp với số khai báo Java source:** compiler có thể thêm bridge/synthetic methods.
7. **Tin vào thứ tự Reflection:** hai mảng không được API cam kết sắp xếp.
8. **Tự thêm method của `Object` vào interface:** `getMethods()` của interface không chứa các method ngầm định từ `Object`.
9. **Dùng `getMethods()` để tìm constructor:** constructor có API riêng.
10. **Suy ra dynamic dispatch từ declaring class:** phương thức có thể được tìm từ lớp cha nhưng invoke trên đối tượng lớp con vẫn chạy bản override.

## 12. Tự kiểm tra

Với `MethodDiscoveryDemo` ở mục 3:

1. `Child.class.getDeclaredMethods()` có chứa `parentOnly()` không? **Không**, vì method được khai báo ở `Parent`.
2. `Child.class.getMethods()` có chứa `parentOnly()` không? **Có**, vì public method được kế thừa.
3. `Child.class.getDeclaredMethods()` có chứa `privateChild()` không? **Có**, vì method khai báo trực tiếp, dù private.
4. `Child.class.getMethods()` có chứa `privateChild()` không? **Không**, vì tập này chỉ tìm public member methods.
5. `Child.class.getMethods()` có chứa `Named.label()` không? **Có**, vì đây là public default instance method được kế thừa.
6. `Method parentMethod = Parent.class.getMethod("describe"); parentMethod.invoke(new Child())` trả gì? **`"Child"`**, vì dispatch của phương thức instance override.
7. Nếu cần liệt kê private method từ từng lớp cha và lớp con, dùng một lần `getDeclaredMethods()` trên `Child` đã đủ chưa? **Chưa**; phải duyệt class hierarchy.

**Ghi nhớ:** `getMethods()` trả lời câu hỏi **“kiểu này có những phương thức public nào theo quy tắc kế thừa?”**; `getDeclaredMethods()` trả lời câu hỏi **“chính kiểu này khai báo những phương thức nào, ở mọi mức truy cập?”**. Luôn kết hợp đối tượng `Class<?>` xuất phát, `Method.getDeclaringClass()` và kiểm tra quyền truy cập để diễn giải đúng.

### Tài liệu chính thức

- [Java SE 17 — java.lang.Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 — java.lang.reflect.Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [dev.java — Invoking Methods](https://dev.java/learn/api/reflection-method-handles/reflection/methods/)