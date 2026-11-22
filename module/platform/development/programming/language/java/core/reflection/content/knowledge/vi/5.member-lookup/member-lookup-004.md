# Public member kế thừa khác member được khai báo tại chính lớp

## 1. Hai câu hỏi khác nhau khi tra cứu member

Trong Java Reflection, **public** mô tả khả năng truy cập theo access modifier, còn **declared** mô tả **nơi member được khai báo**. Đây là hai tiêu chí khác nhau. Với một lớp con, có thể có member `public` được thừa kế từ lớp cha nhưng không xuất hiện trong tập member được khai báo trực tiếp tại lớp con.

Ví dụ, `Parent` khai báo phương thức `public void read()` và `Child extends Parent` không override `read()`. Khi nhìn từ `Child.class`:

- `getMethod("read")` tìm thấy phương thức `read` vì đây là phương thức public được thừa kế.
- `getDeclaredMethod("read")` ném `NoSuchMethodException` vì `Child` không khai báo phương thức đó.
- `getMethod("read").getDeclaringClass()` trả về `Parent.class`, cho biết lớp thực sự khai báo method.

**Quy tắc cốt lõi:** API không có chữ `Declared` dùng phép tra cứu công khai có xét thành viên thừa kế (đối với method/field); API có chữ `Declared` chỉ xét member khai báo tại `Class` đang khảo sát, bất kể public/protected/package-private/private. Quy tắc này cần áp dụng **đúng theo loại member**, vì constructor là trường hợp đặc biệt không được thừa kế.

## 2. Chọn phép tra cứu phù hợp với nơi khai báo

- **Cần public method/field đang nhìn thấy qua lớp con:** `getMethod`/`getMethods` hoặc `getField`/`getFields`, có thể bao gồm thành viên kế thừa từ lớp cha hoặc interface.
- **Cần đúng phần khai báo của lớp con, kể cả private:** `getDeclaredMethod`/`getDeclaredMethods` hoặc `getDeclaredField`/`getDeclaredFields`; kết quả không cộng thêm phần khai báo ở superclass.
- **Cần constructor:** `getConstructor`/`getConstructors` chỉ lấy constructor `public` của chính lớp; họ `getDeclaredConstructor`/`getDeclaredConstructors` lấy mọi mức truy cập của chính lớp. Constructor không kế thừa.

Đối với method, tra tên và danh sách **kiểu tham số chính xác**, không truyền kiểu trả về. Những API lấy một thành viên ném `NoSuchMethodException` hoặc `NoSuchFieldException` nếu không tìm được. Khi `getMethods()` có thêm method từ `Object` hoặc `getDeclaredMethods()` chứa bridge/synthetic methods, hãy xét `getDeclaringClass()` và các cờ metadata trước khi kết luận nguồn khai báo. Mảng kết quả không có thứ tự bảo đảm.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Tạo tệp `MemberLookupDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;

public class MemberLookupDemo {
    public static class Parent {
        public String inheritedField = "from parent";
        public void inheritedMethod() {}
        public void overridden() {}
        protected void protectedMethod() {}
        private void hiddenMethod() {}
    }

    public static class Child extends Parent {
        public int localField = 42;
        private String secret = "child secret";
        public void localMethod() {}
        @Override public void overridden() {}
        private void internalMethod() {}
    }

    private static boolean containsMethod(Method[] methods, String name) {
        return Arrays.stream(methods).anyMatch(m -> m.getName().equals(name));
    }

    private static boolean containsField(Field[] fields, String name) {
        return Arrays.stream(fields).anyMatch(f -> f.getName().equals(name));
    }

    public static void main(String[] args) throws Exception {
        Class<Child> type = Child.class;
        System.out.println("getMethod inherited: "
                + type.getMethod("inheritedMethod").getDeclaringClass().getSimpleName());
        System.out.println("getDeclaredMethod overridden: "
                + type.getDeclaredMethod("overridden").getDeclaringClass().getSimpleName());
        System.out.println("getMethods inherited: "
                + containsMethod(type.getMethods(), "inheritedMethod"));
        System.out.println("getDeclaredMethods inherited: "
                + containsMethod(type.getDeclaredMethods(), "inheritedMethod"));
        System.out.println("getDeclaredMethods private: "
                + containsMethod(type.getDeclaredMethods(), "internalMethod"));
        System.out.println("getField inherited: "
                + type.getField("inheritedField").getDeclaringClass().getSimpleName());
        System.out.println("getDeclaredFields inherited: "
                + containsField(type.getDeclaredFields(), "inheritedField"));
        System.out.println("getDeclaredFields private: "
                + containsField(type.getDeclaredFields(), "secret"));
        System.out.println("getMethods protected: "
                + containsMethod(type.getMethods(), "protectedMethod"));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac --release 17 MemberLookupDemo.java
java MemberLookupDemo
~~~

Kết quả chuẩn (đã kiểm tra với Java 21 và chế độ biên dịch Java 17):

~~~text
getMethod inherited: Parent
getDeclaredMethod overridden: Child
getMethods inherited: true
getDeclaredMethods inherited: false
getDeclaredMethods private: true
getField inherited: Parent
getDeclaredFields inherited: false
getDeclaredFields private: true
getMethods protected: false
~~~

**Giải thích từng nhóm kết quả:**

1. `inheritedMethod` được khai báo ở `Parent` và có modifier `public`. `Child` thừa kế nó nên `getMethod` và `getMethods` tìm được; `getDeclaredMethods` của `Child` không có.
2. `overridden` ban đầu ở `Parent` nhưng `Child` override bằng một method của chính mình. Vì vậy `Child.class.getDeclaredMethod("overridden")` thành công và `getDeclaringClass()` là `Child`. Một method có thể **vừa public vừa declared**.
3. `internalMethod` là `private` và được khai báo ở `Child`. `getDeclaredMethods` nhìn thấy metadata của nó, còn `getMethods` không đưa nó vào tập public.
4. `inheritedField` là field public khai báo ở `Parent`, nên `getField` từ `Child` tìm ra nhưng `getDeclaredFields` của `Child` không chứa nó. Field `secret` là private nhưng vẫn có trong `getDeclaredFields`.
5. `protectedMethod` không phải public nên không xuất hiện trong `getMethods()`; nó có thể được xem qua `Parent.class.getDeclaredMethod("protectedMethod")`.

Mảng Reflection không cam kết một thứ tự member cố định. Ví dụ trên kiểm tra **sự tồn tại theo tên**, không phụ thuộc vị trí phần tử; trong code thực tế, nếu cần trình bày có thứ tự thì hãy tự sắp xếp.

## 4. Phân biệt “thừa kế”, “được khai báo” và “có thể truy cập”

- **Inherited:** member của superclass hoặc interface được kế thừa theo quy tắc ngôn ngữ Java. Method/field public của cha thường là trường hợp dễ thấy nhất. Constructor **không bao giờ được kế thừa**.
- **Declared:** member có khai báo nằm trực tiếp trong kiểu đang được phản chiếu. Một method override tại `Child` là declared tại `Child`, dù cùng signature với method cha.
- **Accessible:** khả năng code hiện tại đọc, ghi hoặc invoke một member. Việc Reflection **liệt kê được** member private qua `getDeclared...` không đồng nghĩa code được phép sử dụng member đó.

Vì vậy, đừng suy từ `getDeclaredMethods()` rằng “đây là danh sách các method public”, và cũng đừng suy từ `getMethods()` rằng “toàn bộ method này được viết trong lớp đang xét”.

### Override và hiding thay đổi kết quả như thế nào?

- **Override instance method:** nếu `Child` khai báo method override public của `Parent`, method của `Child` nằm trong `getDeclaredMethods()`; dùng `getMethod(...)` thường cho method áp dụng ở `Child`. Quan sát `getDeclaringClass()` để xác định nguồn khai báo.
- **Field hiding:** nếu `Child` khai báo field trùng tên với field của `Parent`, đó là **hai field khác nhau**, không phải override field. `getDeclaredFields()` của từng lớp cho thấy field riêng; khi xử lý field trùng tên phải xét `getDeclaringClass()`, đừng giả định tên field là duy nhất trong cả hierarchy.
- **Static method hiding:** method static cũng có thể bị che khuất theo quy tắc Java; static method không tham gia polymorphic override như instance method.
- **Interface:** method public (kể cả default method phù hợp) có thể tham gia tập phương thức public của lớp triển khai, nhưng không vì thế trở thành member “declared” trực tiếp trong lớp.

Phân biệt này đặc biệt quan trọng với thư viện tạo JSON, mapper, dependency injection, framework quét annotation, hoặc công cụ sinh tài liệu: lựa chọn API tra cứu sẽ quyết định có nhìn thấy member từ superclass/interface hay không.

## 5. Khi cần toàn bộ member ở nhiều tầng kế thừa

`getDeclaredMethods()` không tự duyệt superclass. Nếu ứng dụng cần thống kê **mọi khai báo của từng lớp** (ví dụ private method ở lớp cha), duyệt lần lượt `getSuperclass()` và gọi `getDeclaredMethods()` trên từng lớp:

~~~java
for (Class<?> current = Child.class;
     current != null;
     current = current.getSuperclass()) {
    for (Method method : current.getDeclaredMethods()) {
        System.out.println(current.getSimpleName() + ": " + method.getName());
    }
}
~~~

Đây là **đoạn code minh họa dùng các lớp `Child`/`Parent` ở ví dụ trên**, không phải một chương trình độc lập. Nó duyệt chuỗi superclass; nếu cần cả khai báo thuộc interface, phải duyệt thêm `getInterfaces()` và xử lý các đường kế thừa trùng lặp. Nếu cần duy nhất các phương thức public của kiểu, `getMethods()` thường phù hợp và ngắn hơn.

Khi đọc metadata và lọc member, có thể dùng `Modifier.isPublic(member.getModifiers())` để kiểm tra modifier, `member.getDeclaringClass()` để tìm kiểu sở hữu, cùng `Method.isBridge()`/`isSynthetic()` hoặc `Field.isSynthetic()` để xử lý artifact do compiler tạo. Kiểm tra từng trường hợp thay vì suy đoán bằng tên hay số lượng phần tử.

## 6. Lưu ý về invoke và đóng gói module

`getDeclaredMethod("internalMethod")` có thể trả về đối tượng `Method` đại diện cho method private của `Child`. Tuy nhiên, thao tác `invoke(...)` vẫn phải tuân thủ kiểm tra quyền truy cập. `setAccessible(true)` không phải đường tắt được bảo đảm luôn thành công: Java Platform Module System có thể chặn deep reflection qua package chưa `opens`, dẫn đến `InaccessibleObjectException`. Hãy ưu tiên API public hợp lệ, chỉ mở truy cập khi thiết kế và quyền của module cho phép.

Đừng nhầm kết quả “không tìm thấy bằng `getMethod`” với “method không tồn tại”: method protected/private có thể tồn tại ở `getDeclaredMethods` của đúng lớp khai báo, còn method public kế thừa có thể tồn tại ở `getMethods` nhưng không ở `getDeclaredMethods` của lớp con.

## 7. Những lỗi thường gặp và cách chọn API

| Tình huống | Chọn API/cách xử lý |
| --- | --- |
| Cần method public mà object của `Child` có thể cung cấp, kể cả từ cha | `Child.class.getMethod(name, parameterTypes...)` hoặc `getMethods()` |
| Cần đúng method khai báo tại `Child`, dù private | `getDeclaredMethod(...)` hoặc `getDeclaredMethods()` |
| Cần field public được thừa kế từ cha | `getField(name)` hoặc `getFields()` |
| Cần field private của `Parent` | `Parent.class.getDeclaredField(name)`, kèm kiểm tra quyền nếu đọc/ghi |
| Cần toàn bộ khai báo từng lớp trong hierarchy | Duyệt `getSuperclass()`, gọi `getDeclaredFields()/getDeclaredMethods()` từng lớp; xử lý interface nếu cần |
| Cần constructor kế thừa của cha | Không có: constructor không kế thừa; tra cứu constructor trên đúng lớp muốn khởi tạo |
| Cần gọi method private sau khi tìm bằng Reflection | Kiểm tra access checks và giới hạn của module, không mặc định `setAccessible(true)` sẽ thành công |

**Tự kiểm tra:** `Child.class.getMethod("inheritedMethod")` thành công, nhưng `Child.class.getDeclaredMethod("inheritedMethod")` ném `NoSuchMethodException`; ngược lại `Child.class.getDeclaredMethod("internalMethod")` tìm thấy metadata method private nhưng `Child.class.getMethod("internalMethod")` không tìm được. Cả hai khác biệt đều xuất phát từ lựa chọn **public lookup** hay **declared-only lookup**, không phải mâu thuẫn của Reflection.
