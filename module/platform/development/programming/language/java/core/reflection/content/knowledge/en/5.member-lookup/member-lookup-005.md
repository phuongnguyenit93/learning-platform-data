# Tra cứu một thành viên và liệt kê nhiều thành viên bằng Java Reflection

## 1. Mục tiêu và phạm vi

Khi đã có đối tượng `Class<?>`, Java Reflection cho phép **tra cứu một thành viên theo tên/chữ ký** hoặc **liệt kê các thành viên** của một kiểu ngay tại thời điểm chạy. “Thành viên” ở đây chủ yếu gồm:

- **Field**: trường dữ liệu, được mô tả bằng `java.lang.reflect.Field`.
- **Method**: phương thức, được mô tả bằng `java.lang.reflect.Method`.
- **Constructor**: hàm tạo, được mô tả bằng `java.lang.reflect.Constructor`. Hàm tạo không được kế thừa và được tra cứu bằng API riêng.

Bài học tập trung vào **tìm và đọc metadata**, chưa cần gọi `Method.invoke()`, đọc/ghi `Field.get()/set()` hay tạo đối tượng bằng `Constructor.newInstance()`. Việc lấy được metadata của thành viên `private` **không đồng nghĩa** được phép truy cập hoặc thực thi thành viên đó.

Giả sử có `Class<?> type = SomeClass.class;`. Hai họ phương thức quan trọng nhất là:

- `getXxx(...)`: tìm **thành viên `public`**, trong nhiều trường hợp bao gồm thành viên `public` được kế thừa.
- `getDeclaredXxx(...)`: tìm thành viên **khai báo trực tiếp trong chính kiểu**, bất kể mức truy cập (`public`, `protected`, package-private, `private`), nhưng **không tự đi lên lớp cha**.

Lưu ý: khác biệt về kế thừa của constructor được nêu riêng bên dưới.

## 2. Bảng API tra cứu nhanh

| Nhu cầu | Tra cứu một thành viên | Liệt kê nhiều thành viên | Phạm vi |
| --- | --- | --- | --- |
| Phương thức `public` | `getMethod(name, parameterTypes...)` | `getMethods()` | `public` của kiểu và các phương thức `public` kế thừa/phơi bày qua phân cấp kiểu |
| Phương thức khai báo trực tiếp | `getDeclaredMethod(name, parameterTypes...)` | `getDeclaredMethods()` | Khai báo ngay trong kiểu; mọi mức truy cập |
| Trường `public` | `getField(name)` | `getFields()` | `public` của kiểu và trường `public` được kế thừa |
| Trường khai báo trực tiếp | `getDeclaredField(name)` | `getDeclaredFields()` | Khai báo ngay trong kiểu; mọi mức truy cập |
| Hàm tạo `public` | `getConstructor(parameterTypes...)` | `getConstructors()` | Chỉ constructor `public` của chính lớp |
| Hàm tạo khai báo trực tiếp | `getDeclaredConstructor(parameterTypes...)` | `getDeclaredConstructors()` | Constructor của chính lớp; mọi mức truy cập |

Chữ `Declared` nghĩa là **được khai báo ở kiểu đang xét**, không phải “cho phép truy cập riêng tư”. Với `getMethod()`/`getMethods()`, phương thức `public` từ superclass, interface hoặc `Object` có thể xuất hiện; `getDeclaredMethods()` không tự kèm chúng. Khi liệt kê, không được mặc định rằng phần tử đầu tiên là thành viên mong muốn: **thứ tự trả về không được bảo đảm**.

### 2.1. Vì sao phương thức cần cả kiểu tham số?

Java cho phép overload:

```java
void process(String text) {}
void process(int count) {}
```

Muốn tra cứu chính xác phải chỉ ra chữ ký tham số:

```java
Method byText = type.getDeclaredMethod("process", String.class);
Method byCount = type.getDeclaredMethod("process", int.class);
```

Đối số sau tên phương thức là các đối tượng `Class<?>` của **kiểu tham số theo đúng thứ tự**. Không truyền kiểu trả về: `getDeclaredMethod`/`getMethod` chỉ nhận tên và kiểu tham số. Phương thức không có tham số được tìm bằng `getDeclaredMethod("run")` hoặc `getDeclaredMethod("run", new Class<?>[0])`.

Tra cứu dùng kiểu chính xác ở mức reflection: `int.class` khác `Integer.class`; không tự boxing, unboxing hay widening khi **tìm chữ ký**. Với `String...`, chữ ký runtime là `String[]`, nên dùng `String[].class`. Với tham số `List<String>`, do type erasure, phần tham số dùng để tìm thường là `List.class`, không có `List<String>.class`.

### 2.2. Field và constructor khác method ở đâu?

- `getField("id")` và `getDeclaredField("id")` tra cứu theo **tên trường**, không có danh sách kiểu tham số. Trường có thể che khuất trường cùng tên ở lớp cha; kiểm tra `Field.getDeclaringClass()` để biết trường thực sự thuộc lớp nào.
- `getConstructor(String.class)` chỉ tìm constructor `public`; `getDeclaredConstructor(String.class)` tìm constructor được khai báo ngay trong lớp, kể cả `private`. Không có “constructor kế thừa” nên cả hai API đều không đi lên superclass.
- Nếu `Class` biểu diễn interface, primitive hoặc array, tập constructor có thể rỗng; không giả định mọi `Class` đều có constructor không tham số.

## 3. Ví dụ đầy đủ: tìm một thành viên và liệt kê nhiều thành viên

Lưu đoạn sau vào tệp `MemberLookupDemo.java`. Ví dụ cố ý có kế thừa, overload, field `private` và constructor `private` để so sánh hai họ API.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

public class MemberLookupDemo {
    static class Parent {
        public int id = 10;
        protected void protectedHook() {}
        public void inheritedAction() {}
    }

    static class Child extends Parent {
        public String label;
        private int counter;

        public Child() {}
        private Child(int counter) { this.counter = counter; }

        public String show(String prefix) { return prefix + label; }
        public String show(int times) { return label + times; }
        private void reset() { counter = 0; }
    }

    static String params(Class<?>[] types) {
        return Arrays.stream(types)
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args)
            throws NoSuchMethodException, NoSuchFieldException {
        Class<Child> type = Child.class;

        // Tra cứu một thành viên theo tên/chữ ký chính xác.
        Method one = type.getDeclaredMethod("show", String.class);
        Field field = type.getDeclaredField("counter");
        Constructor<Child> constructor = type.getDeclaredConstructor(int.class);

        System.out.println("one method: " + one.getName() + "("
                + params(one.getParameterTypes()) + ") -> "
                + one.getReturnType().getSimpleName());
        System.out.println("one field: " + field.getName()
                + ": " + field.getType().getSimpleName());
        System.out.println("one constructor: "
                + constructor.getDeclaringClass().getSimpleName() + "("
                + params(constructor.getParameterTypes()) + ")");

        // Thành viên public của lớp cha tìm được qua getMethod/getField.
        System.out.println("inherited field owner: "
                + type.getField("id").getDeclaringClass().getSimpleName());
        System.out.println("inherited method owner: "
                + type.getMethod("inheritedAction")
                      .getDeclaringClass().getSimpleName());

        // Liệt kê và sắp xếp để kết quả không phụ thuộc thứ tự của Reflection.
        System.out.println("declared fields: "
                + Arrays.stream(type.getDeclaredFields())
                        .map(Field::getName).sorted().toList());
        System.out.println("public fields: "
                + Arrays.stream(type.getFields())
                        .map(Field::getName).sorted().toList());
        System.out.println("declared methods: "
                + Arrays.stream(type.getDeclaredMethods())
                        .map(Method::getName).distinct().sorted().toList());
        System.out.println("public constructors: "
                + Arrays.stream(type.getConstructors())
                        .map(c -> c.getDeclaringClass().getSimpleName()
                                + "(" + params(c.getParameterTypes()) + ")")
                        .sorted().toList());
        System.out.println("declared constructors: "
                + Arrays.stream(type.getDeclaredConstructors())
                        .map(c -> c.getDeclaringClass().getSimpleName()
                                + "(" + params(c.getParameterTypes()) + ")")
                        .sorted().toList());

        // Declared không duyệt lên superclass.
        try {
            type.getDeclaredMethod("inheritedAction");
        } catch (NoSuchMethodException ex) {
            System.out.println("declared inheritedAction: not found");
        }
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac MemberLookupDemo.java
java MemberLookupDemo
```

Kết quả chuẩn (đã kiểm tra bằng JDK 21):

```text
one method: show(String) -> String
one field: counter: int
one constructor: Child(int)
inherited field owner: Parent
inherited method owner: Parent
declared fields: [counter, label]
public fields: [id, label]
declared methods: [reset, show]
public constructors: [Child()]
declared constructors: [Child(), Child(int)]
declared inheritedAction: not found
```

**Giải thích kết quả:**

1. `getDeclaredMethod("show", String.class)` chọn đúng overload nhận `String`; overload nhận `int` là một `Method` khác. Việc lấy `getName()` khi liệt kê rồi gọi `distinct()` chỉ dùng để trình bày **tên duy nhất**; thao tác đó **không thể hiện được hai chữ ký overload**.
2. `getDeclaredField("counter")` thấy trường `private` trong `Child`. `getFields()` chỉ cho ra `id` (`public` từ `Parent`) và `label` (`public` ở `Child`).
3. `getDeclaredConstructor(int.class)` tìm được constructor `private`. `getConstructors()` chỉ có `Child()` vì constructor đó `public`.
4. `getMethod("inheritedAction")` thành công vì phương thức được khai báo `public` ở `Parent`; `getDeclaredMethod("inheritedAction")` trên `Child.class` ném `NoSuchMethodException` vì `Child` không khai báo phương thức ấy.
5. Việc `getDeclaredMethods()` thấy `reset` không trao quyền chạy phương thức `private`. Ví dụ chỉ xem metadata. `Parent.protectedHook()` không xuất hiện trong `Child.getMethods()` vì không phải `public`, cũng không nằm trong `Child.getDeclaredMethods()` vì khai báo ở lớp cha.

## 4. Đọc metadata sau khi đã tìm được thành viên

Các đối tượng `Field`, `Method`, `Constructor` cho biết **tên, kiểu, nơi khai báo, modifier và chữ ký**:

| Đối tượng | API nên biết | Ý nghĩa |
| --- | --- | --- |
| `Field` | `getName()`, `getType()`, `getDeclaringClass()`, `getModifiers()` | Tên trường, kiểu trường, lớp/interface khai báo, cờ truy cập/đặc tính |
| `Method` | `getName()`, `getParameterTypes()`, `getReturnType()`, `getDeclaringClass()`, `getModifiers()` | Tên, danh sách kiểu tham số, kiểu trả về, nơi khai báo, modifier |
| `Constructor<?>` | `getParameterTypes()`, `getDeclaringClass()`, `getModifiers()` | Chữ ký tham số, lớp sở hữu và modifier của constructor |
| Cả ba | `isSynthetic()` | Có thể là thành viên do compiler sinh ra; phải hiểu mục tiêu liệt kê trước khi lọc |

Ví dụ, sau khi có `Method one` và `Field field` trong chương trình trên:

```java
System.out.println(one.getDeclaringClass().getSimpleName()); // Child
System.out.println(field.getType() == int.class);            // true
System.out.println(java.lang.reflect.Modifier.isPrivate(
        field.getModifiers()));                               // true
```

Đoạn ngắn này **được chèn vào trong `main` của ví dụ trước**, không phải chương trình Java độc lập. `getParameterTypes()` trả về mảng `Class<?>[]` theo thứ tự khai báo; với phương thức generic, có thể dùng thêm `getGenericParameterTypes()` khi cần thông tin khai báo generic (không được bảo đảm phản ánh kiểu cụ thể sau erasure).

Để hiển thị **đầy đủ chữ ký từng overload** khi liệt kê, thay vì `map(Method::getName).distinct()`, dùng biểu diễn gồm cả tham số:

```java
Arrays.stream(type.getDeclaredMethods())
        .filter(m -> m.getName().equals("show"))
        .map(m -> m.getName() + "(" + params(m.getParameterTypes()) + ")")
        .sorted()
        .forEach(System.out::println);
```

Đoạn này cũng đặt trong `main` của chương trình trước; kết quả:

```text
show(String)
show(int)
```

Ở đây dùng `sorted()` vì reflection không cam kết thứ tự của các phương thức. Đối với công cụ tài liệu/debug, nên hiển thị `getDeclaringClass()`, các kiểu tham số và modifier thay vì chỉ tên.

## 5. Tìm thành viên kế thừa nhưng không public

Khi cần tìm một trường hoặc phương thức `protected`/package-private/`private` nằm trên một superclass, `Child.class.getDeclaredXxx(...)` **không tự tìm lớp cha**; `getXxx(...)` cũng không tìm thành viên không `public`. Nếu nghiệp vụ thực sự yêu cầu duyệt superclass, thực hiện vòng lặp tường minh.

Ví dụ tiện ích tìm **field khai báo ở lớp gần nhất** trong chuỗi superclass:

```java
static Field findFieldInHierarchy(Class<?> start, String name)
        throws NoSuchFieldException {
    for (Class<?> current = start; current != null;
         current = current.getSuperclass()) {
        try {
            return current.getDeclaredField(name);
        } catch (NoSuchFieldException ignored) {
            // Chưa được khai báo ở lớp này: tiếp tục lên superclass.
        }
    }
    throw new NoSuchFieldException(name);
}
```

Đây là **phương thức tiện ích**, cần đặt trong một lớp Java và import `java.lang.reflect.Field`. Nếu gọi `findFieldInHierarchy(Child.class, "id")`, nó trả về `Field` được khai báo ở `Parent`; nếu gọi với `"counter"`, nó chọn trường ở `Child`. Vòng lặp này chỉ xét **chuỗi superclass** và không tìm field khai báo trong các interface; đó là phạm vi chủ ý của ví dụ.

Với method, có thể dùng tương tự `getDeclaredMethod(name, parameterTypes)` ở từng superclass khi cần kiểm tra khai báo cụ thể. Tuy nhiên **method của interface không nằm trong chuỗi `getSuperclass()`**; muốn quét đầy đủ interface và các superinterface cần duyệt riêng `getInterfaces()`. Trường hợp đó thường nên bắt đầu bằng `getMethods()` nếu chỉ quan tâm API `public`.

Cũng phải phân biệt: **tìm metadata theo phân cấp** và **quyết định phương thức nào sẽ chạy khi dispatch động** là hai vấn đề khác nhau. `getDeclaringClass()` nói nơi đối tượng metadata được khai báo; không thay thế việc hiểu overriding, hiding hoặc quyền truy cập.

## 6. Những tình huống dễ nhầm

### 6.1. Không tìm thấy member không nhất thiết là member không tồn tại

- `getMethod("reset")` trên `Child.class` thất bại vì `reset` là `private`; `getDeclaredMethod("reset")` tìm thấy.
- `getDeclaredMethod("inheritedAction")` thất bại trên `Child.class` vì method nằm ở superclass; `getMethod("inheritedAction")` tìm thấy.
- `getConstructor(int.class)` thất bại trên `Child.class` vì constructor nhận `int` là `private`; `getDeclaredConstructor(int.class)` tìm thấy.
- `getDeclaredMethod("show", Integer.class)` thất bại vì overload tương ứng nhận `int`, không phải `Integer`.

Các phương thức tìm một thành viên thường ném `NoSuchMethodException` hoặc `NoSuchFieldException` khi không tìm được. Nếu không có member là trường hợp bình thường, hãy bắt ngoại lệ **đúng phạm vi** hoặc trả về `Optional` từ một hàm tiện ích; tránh bắt tràn lan `Exception` rồi che lỗi lập trình.

### 6.2. `getDeclared*` không có nghĩa là được tự do dùng `private`

Reflection có thể **phát hiện** member không public, nhưng hành động đọc/ghi/gọi member phải qua kiểm tra quyền truy cập riêng. Trên Java 9+ với Java Platform Module System, việc cố `setAccessible(true)` có thể bị từ chối (`InaccessibleObjectException`), ngay cả khi `getDeclaredField()` đã trả về `Field`. `trySetAccessible()` cũng có thể trả `false`. Vì vậy không thiết kế chương trình với giả định “tìm thấy là gọi được”; khi làm thư viện/framework, ưu tiên API public hoặc cơ chế `opens` có chủ đích.

### 6.3. Compiler có thể sinh thêm member

Trong chương trình thực, `getDeclaredMethods()` có thể thấy **bridge method** do generics/covariant return sinh ra, hoặc method/field synthetic. `Method.isBridge()` và `Member.isSynthetic()` giúp phân biệt. Nếu đang tạo bảng tài liệu hướng đến developer, có thể cân nhắc lọc; nếu đang phân tích runtime/bytecode, không nên lọc tùy tiện.

Không coi số phần tử, thứ tự, hay biểu diễn `toString()` của các `Member` là giao diện ổn định cho kiểm thử. Cách an toàn hơn là lấy thông tin có cấu trúc, sắp xếp và so sánh đúng trường cần thiết. Constructor có thể không tồn tại theo chữ ký mong muốn; **Java không tự sinh constructor không tham số** khi lớp đã khai báo constructor khác.

### 6.4. Khác nhau giữa khai báo và kế thừa

- `getDeclaredFields()` không có field ở superclass; `getFields()` chỉ bao gồm field `public` được hiển thị theo quan hệ kiểu.
- `getDeclaredMethods()` không tự có method ở superclass/interface; `getMethods()` phục vụ việc khám phá method `public` và có thể bao gồm method từ `Object`.
- Constructor không được kế thừa, nên `getConstructors()` không bao giờ có constructor của `Parent` khi gọi trên `Child.class`.
- Tên method không duy nhất khi có overload; khi phân loại, hãy dùng **tên + kiểu tham số**, bổ sung kiểu trả về/chủ sở hữu khi kiểm tra các trường hợp cầu nối hoặc runtime phức tạp.

## 7. Chọn API đúng trong thực tế

| Tình huống | Lựa chọn khởi đầu | Vì sao |
| --- | --- | --- |
| Framework cần tìm method `public` có tên và chữ ký xác định trên object | `type.getMethod(name, parameterTypes)` | Chấp nhận method `public` kế thừa |
| Công cụ audit cần xem mọi field khai báo trong một lớp | `type.getDeclaredFields()` | Bao gồm non-public của đúng lớp |
| Debug danh sách method được khai báo trực tiếp | `type.getDeclaredMethods()` | Không lẫn toàn bộ method `public` kế thừa |
| Kiểm tra factory constructor `public` | `type.getConstructor(parameterTypes)` | Chỉ constructor `public` |
| Xem các constructor không public để phân tích metadata | `type.getDeclaredConstructors()` | Không yêu cầu đã được cấp quyền gọi chúng |
| Tìm trường khai báo ở superclass, bất kể modifier | Duyệt `getSuperclass()` + `getDeclaredField()` | Cần kiểm soát chính xác phạm vi duyệt |

Khi đã biết kiểu tại compile time và chỉ cần gọi method thông thường, gọi trực tiếp thường đơn giản, an toàn kiểu hơn và dễ bảo trì hơn. Reflection hữu ích nhất khi tên/chữ ký được quyết định tại runtime, chẳng hạn mapper, serializer, container, plugin loader, test/discovery tool và công cụ introspection. Với lượt tra cứu lặp rất nhiều, có thể lưu cache `Method`/`Field` theo lớp và chữ ký; cần tính đến vòng đời của `ClassLoader` để tránh giữ class không cần thiết.

## 8. Tự kiểm tra

1. `Child.class.getDeclaredField("id")` và `Child.class.getField("id")` khác nhau thế nào? **Đáp án:** lời gọi đầu ném `NoSuchFieldException` vì `id` khai báo ở `Parent`; lời gọi sau trả về field `public` kế thừa.
2. Vì sao `Child.class.getDeclaredMethod("show")` thất bại dù trong lớp có hai method `show`? **Đáp án:** cả hai đều nhận một tham số; lời gọi đang yêu cầu method `show()` không tham số.
3. Làm sao lấy overload `show(int)`? **Đáp án:** `Child.class.getDeclaredMethod("show", int.class)`.
4. Vì sao `Child.class.getConstructors()` chỉ có một phần tử trong ví dụ? **Đáp án:** chỉ `Child()` là `public`; `Child(int)` là `private`, và constructor của `Parent` không kế thừa.
5. Nên dùng API nào khi muốn đếm các method khai báo ngay trong lớp, kể cả `private`? **Đáp án:** `getDeclaredMethods()`; nếu đếm theo nghiệp vụ, xem xét synthetic/bridge và overload trước khi thống kê.

**Ghi nhớ:** Trước khi tra cứu một thành viên, hãy trả lời ba câu hỏi: **(1)** cần method, field hay constructor; **(2)** chỉ cần `public` hay mọi mức truy cập; **(3)** cần cả thành viên kế thừa hay chỉ phần khai báo trực tiếp. Ba quyết định đó dẫn đến đúng cặp API `get...`/`getDeclared...` và giúp tránh phần lớn lỗi `NoSuchMethodException`/`NoSuchFieldException`.
