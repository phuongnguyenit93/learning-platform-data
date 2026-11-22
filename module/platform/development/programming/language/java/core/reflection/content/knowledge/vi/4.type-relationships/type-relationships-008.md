# Chọn kiểu khai báo hoặc kiểu thực tế khi khám phá thành viên bằng Java Reflection

Khi một biến được khai báo bằng lớp cha hoặc interface nhưng đang tham chiếu đến một đối tượng thuộc lớp con, Reflection có thể khám phá **hai tập thành viên khác nhau** tùy theo đối tượng `Class<?>` được chọn. Quyết định này ảnh hưởng đến phương thức, trường dữ liệu, kết quả tra cứu và tính ổn định của công cụ sử dụng Reflection.

## 1. Phân biệt ba khái niệm về kiểu

Xét:

```java
Animal animal = new Dog();
```

- **Kiểu khai báo (declared/static type)** của biến `animal` là `Animal`. Trình biên dịch kiểm tra những lời gọi thông thường như `animal.speak()` dựa trên hợp đồng của `Animal`. Kiểu này được biết từ khai báo trong mã nguồn, hoặc từ metadata của trường, tham số, kiểu trả về.
- **Kiểu thực tế (runtime type)** của đối tượng là `Dog`. Biểu thức `animal.getClass()` trả về đối tượng `Class` mô tả `Dog`, bất kể biến đang mang kiểu `Animal`.
- **Lớp khai báo thành viên (declaring class)** là nơi một `Method` hoặc `Field` thực sự được khai báo. Kiểm tra bằng `member.getDeclaringClass()`; lớp này có thể khác lớp `Class` dùng để tìm kiếm.

Hai cách bắt đầu Reflection vì vậy mang ý nghĩa khác nhau:

```java
Class<?> contractType = Animal.class;       // Khám phá từ kiểu khai báo
Class<?> runtimeType = animal.getClass();   // Khám phá từ kiểu thực tế: Dog
```

`Animal.class` là lựa chọn tường minh của lập trình viên; Java không tự suy ra kiểu khai báo của biến từ một đối tượng đã được truyền vào phương thức chỉ nhận `Object`. Còn `getClass()` luôn dựa trên đối tượng thực tế và sẽ ném `NullPointerException` nếu tham chiếu là `null`.

**Điểm mấu chốt:** chọn `Class<?>` nào quyết định **điểm xuất phát để khám phá metadata**. Điều đó không đồng nghĩa với việc chỉ định phương thức thực thi khi gọi một phương thức instance có thể override.

## 2. Chọn kiểu nào dẫn đến tập thành viên nào?

Giả sử `Parent` khai báo `parentOnly()`, còn `Child extends Parent` khai báo thêm `childOnly()` và override `describe()`.

| Cách lấy `Class<?>` | Ý nghĩa khi khám phá | Thành viên `childOnly()` |
| --- | --- | --- |
| `Parent.class` | Khám phá API xuất phát từ `Parent` | Không xuất hiện |
| `Child.class` | Khám phá API xuất phát từ `Child` | Có thể xuất hiện |
| `parentRef.getClass()`, khi `parentRef = new Child()` | Khám phá đúng lớp runtime `Child` | Có thể xuất hiện |
| `method.getDeclaringClass()` | Xác định nơi phương thức được khai báo, không tự khám phá lại | Phụ thuộc chính `method` |

Tuy nhiên, kết quả còn phụ thuộc **họ API Reflection** được gọi trên `Class<?>`:

| API | Khám phá gì? | Có bao gồm thành viên kế thừa? |
| --- | --- | --- |
| `getDeclaredMethods()` / `getDeclaredMethod(name, parameterTypes...)` | Phương thức khai báo trực tiếp ở kiểu đang xét, bất kể `public`, `protected`, package-private hoặc `private` | Không |
| `getMethods()` / `getMethod(name, parameterTypes...)` | Phương thức `public` của kiểu và phương thức `public` được kế thừa; có thể gồm phương thức từ interface và `Object` | Có, theo quy tắc kế thừa |
| `getDeclaredFields()` / `getDeclaredField(name)` | Trường khai báo trực tiếp ở kiểu đang xét, với mọi mức truy cập | Không |
| `getFields()` / `getField(name)` | Các trường `public` của kiểu và những trường `public` kế thừa theo quy tắc Java | Có |
| `getDeclaredConstructors()` / `getDeclaredConstructor(...)` | Constructor khai báo trên chính lớp, mọi mức truy cập | Không; constructor không được kế thừa |
| `getConstructors()` / `getConstructor(...)` | Constructor `public` của chính lớp | Không; constructor không được kế thừa |

Lưu ý rằng từ `declared` trong tên API nghĩa là “**được khai báo trực tiếp trên kiểu đang xét**”, **không** có nghĩa là “theo kiểu khai báo của biến”. Ví dụ, `object.getClass().getDeclaredMethods()` vẫn liệt kê các phương thức khai báo tại lớp runtime của `object`.

Các phương thức `getDeclared*` vẫn có thể trả về metadata của thành viên không public; **nhìn thấy metadata không đồng nghĩa có quyền truy cập hoặc gọi thành viên đó**. Việc sử dụng `setAccessible(true)` có thể bị giới hạn bởi cơ chế module (JPMS), quyền truy cập hoặc môi trường chạy.

## 3. Ví dụ Java 17+ chạy được: lớp cha, lớp con và lời gọi thực tế

Tạo tệp `ReflectionTypeChoiceDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionTypeChoiceDemo {
    static class Parent {
        public String describe() {
            return "Parent";
        }

        public String parentOnly() {
            return "parent-only";
        }

        private String secret = "parent-secret";
    }

    static final class Child extends Parent {
        @Override
        public String describe() {
            return "Child";
        }

        public String childOnly() {
            return "child-only";
        }

        private int childCount = 3;
    }

    private static boolean declaresMethod(Class<?> type, String name) {
        for (Method method : type.getDeclaredMethods()) {
            if (method.getName().equals(name)) {
                return true;
            }
        }
        return false;
    }

    private static boolean declaresField(Class<?> type, String name) {
        for (Field field : type.getDeclaredFields()) {
            if (field.getName().equals(name)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Parent reference = new Child();

        Class<?> declaredType = Parent.class;
        Class<?> runtimeType = reference.getClass();

        System.out.println("Declared type: " + declaredType.getSimpleName());
        System.out.println("Runtime type: " + runtimeType.getSimpleName());

        System.out.println("Parent declares childOnly: "
                + declaresMethod(declaredType, "childOnly"));
        System.out.println("Child declares parentOnly: "
                + declaresMethod(runtimeType, "parentOnly"));

        Method inherited = runtimeType.getMethod("parentOnly");
        System.out.println("parentOnly declared in: "
                + inherited.getDeclaringClass().getSimpleName());

        Method parentMethod = declaredType.getMethod("describe");
        System.out.println("Parent.describe invoked on Child: "
                + parentMethod.invoke(reference));

        Method childMethod = runtimeType.getMethod("childOnly");
        System.out.println("Child.childOnly invoked: "
                + childMethod.invoke(reference));

        System.out.println("Child declares childCount: "
                + declaresField(runtimeType, "childCount"));
        System.out.println("Child declares secret: "
                + declaresField(runtimeType, "secret"));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac ReflectionTypeChoiceDemo.java
java ReflectionTypeChoiceDemo
```

Kết quả:

```text
Declared type: Parent
Runtime type: Child
Parent declares childOnly: false
Child declares parentOnly: false
parentOnly declared in: Parent
Parent.describe invoked on Child: Child
Child.childOnly invoked: child-only
Child declares childCount: true
Child declares secret: false
```

Giải thích các điểm dễ nhầm:

1. `declaredType` đại diện cho `Parent`; nó không có metadata của `childOnly()`. Trong mã Java thông thường, `reference.childOnly()` cũng không biên dịch được vì biến `reference` mang kiểu `Parent`.
2. `runtimeType.getDeclaredMethods()` chỉ có phương thức được **khai báo trực tiếp** tại `Child`, không chứa `parentOnly()`. Nhưng `runtimeType.getMethod("parentOnly")` tìm thấy phương thức `public` kế thừa, và `getDeclaringClass()` trả về `Parent`.
3. `Parent.class.getMethod("describe")` trả về metadata của `Parent.describe()`. Khi `invoke(reference)` trên đối tượng `Child`, cơ chế dispatch động của phương thức instance dẫn tới phiên bản override `Child.describe()`, nên in ra `Child`. Phương thức `static` hoặc `private` không tham gia override theo cách này.
4. `Child.class.getDeclaredField("childCount")` tồn tại; `Child.class.getDeclaredField("secret")` sẽ ném `NoSuchFieldException` vì `secret` được khai báo ở `Parent`. Ví dụ dùng vòng lặp để kiểm tra thay vì ném exception.

Hai hàm `declaresMethod` và `declaresField` trong ví dụ chỉ kiểm tra **tên**, phù hợp vì các tên đang xét không quá tải. Khi tra cứu một phương thức cụ thể trong ứng dụng thật, phải xét cả danh sách kiểu tham số, ví dụ `getMethod("find", String.class, int.class)`.

## 4. Phân biệt khám phá metadata và cách Java dispatch lời gọi

Có hai câu hỏi độc lập:

- **Có tìm ra `Method` hay không?** Phụ thuộc `Class<?>` bắt đầu tìm và việc dùng `getMethod` hay `getDeclaredMethod`.
- **Khi `Method.invoke(receiver, args)`, phần thân nào chạy?** Với phương thức instance có thể override, Java áp dụng dispatch động theo lớp thực tế của `receiver`; đối tượng nhận vẫn phải tương thích với phương thức được khai báo và phải thỏa điều kiện truy cập.

Do đó:

```java
Parent instance = new Child();
Method method = Parent.class.getMethod("describe");
Object value = method.invoke(instance); // "Child"
```

Không nên hiểu `Parent.class` là cách “ép chạy thân `Parent.describe()`” khi có override. Nếu yêu cầu thực sự là gọi implementation cụ thể của lớp cha, đó là bài toán cơ chế gọi phương thức khác, không giải được chỉ bằng việc đổi `Class<?>` cho `getMethod()`.

Ngược lại, Reflection trên lớp runtime có thể nhìn thấy method riêng của lớp con, dù biến trong Java chỉ là `Parent`. Điều này hữu ích cho chẩn đoán hoặc framework, nhưng có thể làm code phụ thuộc vào implementation không nằm trong hợp đồng public.

## 5. Khám phá trường kế thừa: đi qua cây lớp khi cần

Các trường (fields) **không có dispatch động như phương thức instance**. Khi lớp con che khuất tên trường ở lớp cha (field hiding), hai khai báo vẫn là hai `Field` riêng và `getDeclaringClass()` giúp phân biệt nguồn gốc của chúng.

Để biết những trường được khai báo **trên từng lớp** từ lớp runtime đến `Object`, duyệt cây lớp:

```java
Class<?> type = instance.getClass();

while (type != null) {
    for (java.lang.reflect.Field field : type.getDeclaredFields()) {
        System.out.println(type.getName() + " -> " + field.getName());
    }
    type = type.getSuperclass();
}
```

Đây là **đoạn minh họa** sử dụng biến `instance` đã tồn tại, không phải một chương trình độc lập. Kết quả thứ tự của `getDeclaredFields()` không được API bảo đảm; nếu cần thứ tự ổn định thì sắp xếp trước khi xử lý.

Vòng lặp `getSuperclass()` chỉ đi theo **chuỗi lớp cha**, không tự đi sâu vào các interface. Nếu cần khám phá interface, xét `getInterfaces()`, cây interface và quy tắc thành viên tương ứng. Không sử dụng vòng lặp này để mặc định bỏ qua kiểm tra quyền truy cập; liệt kê tên trường khác với đọc giá trị trường.

Khi đã có đối tượng `Field`, hãy xem `field.getDeclaringClass()` và `field.getType()` để biết lớp khai báo và kiểu khai báo của trường. `field.getType()` cũng không tự biến thành kiểu thực tế của giá trị đang nằm trong trường; nếu cần phân tích giá trị, phải đọc giá trị hợp lệ trước rồi mới cân nhắc `value.getClass()` khi `value != null`.

## 6. Khi nào nên chọn kiểu khai báo, khi nào chọn kiểu thực tế?

### Chọn kiểu khai báo hoặc interface khi làm việc theo hợp đồng

Thích hợp khi tạo bộ gọi API, kiểm tra annotation trên một hợp đồng đã xác định, xác minh phương thức mà người dùng được phép gọi, hoặc cần kết quả không phụ thuộc vào lớp implementation có thể thay đổi.

```java
Class<?> apiType = Runnable.class;
Method method = apiType.getMethod("run");
```

`Runnable.class` thể hiện đúng hợp đồng `Runnable`. Việc đối tượng runtime có thêm phương thức phụ không làm mở rộng danh sách API mà thành phần của bạn dự định hỗ trợ. Nhưng nếu nghiệp vụ cần annotation khai báo trên implementation, Reflection chỉ trên interface có thể **không đủ**: phải thiết kế chính sách tìm annotation cụ thể và kiểm tra vị trí khai báo phù hợp.

### Chọn kiểu thực tế khi cần biết đối tượng thực sự có gì

Thích hợp khi viết công cụ debug, serializer có chính sách rõ ràng, diagnostic inspector hoặc code dùng metadata riêng của implementation:

```java
Object value = obtainValue(); // Hàm ứng dụng cung cấp, chỉ là minh họa
if (value != null) {
    Class<?> runtimeType = value.getClass();
    for (Method method : runtimeType.getDeclaredMethods()) {
        System.out.println(method.getName());
    }
}
```

Đây cũng là **đoạn minh họa**, chưa phải chương trình chạy độc lập do `obtainValue()` là hàm do ứng dụng định nghĩa. `getDeclaredMethods()` ở đây chỉ thu phương thức khai báo trực tiếp của implementation. Nếu cần danh sách API `public` mà đối tượng có thể sử dụng, xem xét `getMethods()` thay cho `getDeclaredMethods()`.

**Trường hợp proxy/framework:** đối tượng runtime có thể là proxy hoặc lớp sinh tự động. `getClass()` khi đó trả về kiểu proxy, không nhất thiết là lớp nghiệp vụ bạn dự kiến. Với code dựa trên hợp đồng, ưu tiên `interface.class` hoặc `Class<?>` được chỉ định rõ; với việc bóc tách kiểu đích của proxy, sử dụng cơ chế mà framework thực tế cung cấp thay vì đoán lớp cha.

### Muốn tìm đúng thành viên đang được khai báo ở đâu

Dùng `getDeclaringClass()` sau khi tìm thấy `Method` hoặc `Field`. Một phương thức trả về từ `Child.class.getMethod("parentOnly")` có thể thuộc `Parent`; đây không phải lỗi hay một bản sao của phương thức trên `Child`.

### Muốn xử lý lớp con an toàn từ biến kiểu cha

Nếu thực sự cần một hành vi chỉ `Child` có, trước hết xác định đối tượng có đúng kiểu không:

```java
if (Child.class.isInstance(reference)) {
    Child child = Child.class.cast(reference);
    System.out.println(child.childOnly());
}
```

Đây là đoạn minh họa dùng các lớp và biến của ví dụ phía trên. `isInstance` cho biết đối tượng có tương thích với kiểu được kiểm tra hay không; `cast` thực hiện ép kiểu có kiểm tra, giúp tránh `ClassCastException`. Đừng chọn `getClass()` chỉ để lách thiết kế API khi có thể biểu diễn hợp đồng bằng interface hoặc lớp cha.

## 7. Lỗi phổ biến và cách kiểm tra

| Nhầm lẫn | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| `reference.getClass()` trả về kiểu khai báo của biến | Nó trả về kiểu runtime | Dùng `DeclaredType.class`, hoặc metadata của chính khai báo nếu đang phân tích source/field/parameter |
| `getDeclaredMethods()` lấy tất cả phương thức có thể gọi, kể cả kế thừa | Nó chỉ lấy khai báo trực tiếp trên `Class<?>` được chọn | Dùng `getMethods()` nếu cần phương thức public kế thừa; hoặc duyệt hierarchy theo chính sách |
| `getMethods()` cho thấy cả phương thức private | API này chỉ liệt kê phương thức public phù hợp | Với metadata khai báo riêng, dùng `getDeclaredMethods()` và xử lý quyền truy cập |
| `Child.class.getDeclaredField("baseField")` tìm được trường của cha | Trường khai báo tại lớp cha không nằm trong `getDeclaredFields()` của con | Tra tại `Parent.class` hoặc duyệt `getSuperclass()` |
| Phương thức lấy từ `Parent.class` luôn chạy phiên bản `Parent` | Override instance được dispatch động khi `invoke` | Phân biệt phương thức được tìm thấy với phần thân được thực thi |
| Chỉ lọc `Method.getName()` là đủ trong mọi trường hợp | Một tên có thể có nhiều overload; trình biên dịch có thể tạo bridge/synthetic method | Kèm kiểu tham số, kiểm tra `isBridge()`/`isSynthetic()` khi phù hợp |
| Tin vào thứ tự của `getDeclaredMethods()` hay `getDeclaredFields()` | API không cam kết thứ tự ổn định | Sắp xếp bằng tiêu chí minh bạch nếu thứ tự có ý nghĩa |
| Xem được một `private Field` nghĩa là đọc được giá trị | Metadata không tự cấp quyền truy cập | Tôn trọng truy cập Java và giới hạn module; chỉ truy cập khi có quyền và lý do hợp lệ |

Một quy trình lựa chọn ngắn cho công cụ Reflection:

1. Xác định mục tiêu: **kiểm tra hợp đồng** hay **khám phá implementation thực tế**.
2. Chọn nguồn `Class<?>`: `Contract.class` khi theo API, hoặc `obj.getClass()` khi theo đối tượng và `obj != null`.
3. Chọn phạm vi thành viên: `getDeclared*` để xem khai báo tại chính lớp; `get*` khi cần thành viên public, bao gồm các thành viên có thể kế thừa.
4. Kiểm tra `getDeclaringClass()` để không nhầm thành viên kế thừa với thành viên tự khai báo. Nếu phải khám phá private/protected ở cha, duyệt hierarchy có chủ đích.
5. Nếu chuẩn bị gọi bằng `invoke`, kiểm tra signature, receiver, quyền truy cập và lưu ý dispatch động; không suy luận execution chỉ từ đối tượng `Class<?>` dùng để tìm.

## 8. Tự kiểm tra

Với `Parent parent = new Child();` trong chương trình ở mục 3, thử tự trả lời:

- `parent.getClass() == Child.class` có đúng không? **Đúng**, vì đối tượng thực tế là `Child`.
- `Child.class.getDeclaredMethod("parentOnly")` có thành công không? **Không**, sẽ ném `NoSuchMethodException` do phương thức được khai báo ở `Parent`.
- `Child.class.getMethod("parentOnly").getDeclaringClass()` trả về gì? **`Parent.class`**, do đây là phương thức public được kế thừa.
- `Parent.class.getMethod("describe").invoke(parent)` cho kết quả gì? **`"Child"`**, do dispatch động chọn phần override ở lớp runtime.
- Nếu cần kiểm tra tất cả trường được khai báo trực tiếp trên từng lớp trong hệ phân cấp, nên dùng gì? **`getDeclaredFields()` trên từng `Class<?>`**, kết hợp duyệt `getSuperclass()` và chính sách xử lý interface nếu cần.

Kết luận cho bài này: **kiểu khai báo trả lời câu hỏi về hợp đồng; kiểu thực tế trả lời câu hỏi về đối tượng hiện có; lớp khai báo thành viên trả lời câu hỏi về nguồn gốc metadata**. Chọn đúng điểm xuất phát rồi mới quyết định `get*` hay `getDeclared*` sẽ giúp tránh bỏ sót thành viên kế thừa, nhầm method override và vô tình ràng buộc code vào chi tiết implementation.