# Tra cứu thành viên theo kiểu sau type erasure trong Java Reflection

Khi tìm method, constructor hoặc field của lớp generic bằng Java Reflection, cần phân biệt **kiểu runtime để tra cứu** với **khai báo generic trong mã nguồn**. Java dùng *type erasure*: type variable như T thường bị thay bằng Object hoặc bound đầu tiên, còn List<String> chỉ mang raw type List trong chữ ký dùng để tìm method. Thông tin generic được khai báo vẫn có thể nằm trong thuộc tính Signature của class file để các API getGeneric... đọc lại.

Bài này giải thích cách chọn đúng Class<?> khi lookup, cách xem Type để phân tích generic, cách generic hoạt động qua kế thừa và vì sao compiler sinh bridge method.

## 1. Quy tắc xóa kiểu liên quan đến lookup

| Kiểu tham số được khai báo | Class<?> dùng để tìm sau erasure | Nguyên nhân |
| --- | --- | --- |
| T (không có bound) | Object.class | Erasure của type variable không bị ràng buộc |
| T extends Number | Number.class | Erasure bằng bound |
| T extends Number & Comparable<T> | Number.class | Chọn bound đầu tiên |
| List<String> | List.class | Xóa type argument String |
| List<? extends Number> | List.class | Wildcard không làm đổi raw type |
| T[] với T không có bound | Object[].class | Xóa kiểu phần tử thành Object |
| String... | String[].class | Varargs là một tham số mảng |

Xét khai báo:

~~~java
class Holder<T extends Number> {
    void set(T value) {}
    void setAll(java.util.List<String> values) {}
}
~~~

Đây là hai cách tra cứu đúng:

~~~java
Holder.class.getDeclaredMethod("set", Number.class);
Holder.class.getDeclaredMethod("setAll", java.util.List.class);
~~~

Không tìm set bằng Integer.class dù trong ứng dụng bạn có thể truyền Integer cho T; kiểu khai báo đã xóa là Number. Cũng không truyền một ParameterizedType biểu diễn List<String> vào getDeclaredMethod vì API này nhận mảng Class<?> mô tả **kiểu tham số sau erasure**.

Hai overload chỉ khác generic type argument dẫn đến cùng erasure sẽ xung đột lúc biên dịch. Đoạn sau **cố ý không biên dịch được**:

~~~java
void process(java.util.List<String> items) {}
void process(java.util.List<Integer> items) {} // name clash: same erasure
~~~

Đối tượng new ArrayList<String>() và new ArrayList<Integer>() đều có runtime class java.util.ArrayList; gọi getClass() không khôi phục được tham số kiểu String/Integer từ instance thông thường.

## 2. API tìm thành viên và phạm vi tra cứu

**Method**

- getDeclaredMethod(name, Class<?>...) tìm method được khai báo **ngay trong lớp** ở mọi mức truy cập, kể cả private; không tìm method kế thừa.
- getMethod(name, Class<?>...) tìm method **public**, gồm cả public method kế thừa.
- getDeclaredMethods() / getMethods() trả danh sách để tìm overload, lọc bridge hoặc kiểm tra thông tin generic.
- getDeclaredMethod/getMethod đối sánh tên và danh sách parameter types sau erasure; **không yêu cầu kiểu trả về**. Với bridge method có cùng tên và tham số, dùng isBridge()/isSynthetic() khi duyệt danh sách.
- Đối với void update(int id, List<String> values), cần int.class và List.class theo đúng thứ tự. int.class khác Integer.class; String[].class khác String.class trong varargs.

~~~java
clazz.getDeclaredMethod("update", int.class, java.util.List.class);
~~~

**Constructor**

- getDeclaredConstructor(Class<?>...) tìm constructor khai báo trong lớp ở mọi mức truy cập.
- getConstructor(Class<?>...) chỉ tìm constructor public.
- Nếu constructor nhận T extends Number thì tra cứu bằng Number.class, dù dữ liệu truyền khi tạo instance là Integer.

**Field**

- getDeclaredField(name) tìm field khai báo trực tiếp, kể cả private; getField(name) tìm field public và có thể thấy field kế thừa.
- Field được tìm bằng **tên**, không có tham số kiểu trong lệnh tìm. Sau đó Field.getType() trả kiểu đã xóa, còn Field.getGenericType() trả thông tin generic được khai báo khi có metadata.
- Field T value của class Holder<T extends Number> sẽ có getType() là Number.class, và getGenericType() thường là TypeVariable tên T.

Tra cứu được một thành viên chưa đồng nghĩa có thể truy cập/gọi thành công. Private access và module encapsulation vẫn áp dụng; type erasure không cho phép vượt qua kiểm soát truy cập.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Tạo file **ErasureLookupDemo.java** với toàn bộ mã sau:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.Arrays;
import java.util.List;

public class ErasureLookupDemo {
    static class Store<T extends Number> {
        private T lastValue;
        public Store() {}
        public Store(T initial) { lastValue = initial; }
        public void put(T value) {}
        public void putList(List<String> values) {}
        public T first() { return null; }
        public void labels(String... values) {}
    }

    static class Base<T> {
        public T get() { return null; }
    }

    static class InheritsText extends Base<String> {}

    static class TextStore extends Base<String> {
        @Override
        public String get() { return "hello"; }
    }

    public static void main(String[] args) throws Exception {
        Constructor<?> constructor = Store.class.getDeclaredConstructor(Number.class);
        System.out.println("ctor/erased = " + constructor.getParameterTypes()[0].getTypeName());

        Field field = Store.class.getDeclaredField("lastValue");
        System.out.println("field/erased = " + field.getType().getTypeName());
        System.out.println("field/generic = " + field.getGenericType().getTypeName());

        Method put = Store.class.getDeclaredMethod("put", Number.class);
        System.out.println("put/erased = " + put.getParameterTypes()[0].getTypeName());
        System.out.println("put/generic = " + put.getGenericParameterTypes()[0].getTypeName());

        Method putList = Store.class.getDeclaredMethod("putList", List.class);
        System.out.println("putList/erased = " + putList.getParameterTypes()[0].getTypeName());
        Type declaredType = putList.getGenericParameterTypes()[0];
        if (declaredType instanceof ParameterizedType parameterized) {
            System.out.println("putList/typeArg = "
                    + parameterized.getActualTypeArguments()[0].getTypeName());
        }

        Method first = Store.class.getDeclaredMethod("first");
        System.out.println("first/erased = " + first.getReturnType().getTypeName());
        System.out.println("first/generic = " + first.getGenericReturnType().getTypeName());

        Method labels = Store.class.getDeclaredMethod("labels", String[].class);
        System.out.println("labels/isVarArgs = " + labels.isVarArgs());

        try {
            Store.class.getDeclaredMethod("put", Integer.class);
        } catch (NoSuchMethodException ex) {
            System.out.println("put(Integer) = not found");
        }

        Method inherited = InheritsText.class.getMethod("get");
        System.out.println("InheritsText.get/erased = " + inherited.getReturnType().getSimpleName());
        System.out.println("InheritsText.get/generic = " + inherited.getGenericReturnType().getTypeName());

        Method[] declared = TextStore.class.getDeclaredMethods();
        Arrays.sort(declared, (left, right) -> Boolean.compare(left.isBridge(), right.isBridge()));
        for (Method method : declared) {
            if (method.getName().equals("get")) {
                System.out.println("TextStore.get = " + method.getReturnType().getSimpleName()
                        + ", bridge=" + method.isBridge());
            }
        }

        Type parent = TextStore.class.getGenericSuperclass();
        if (parent instanceof ParameterizedType parameterized) {
            System.out.println("TextStore<Base> arg = "
                    + parameterized.getActualTypeArguments()[0].getTypeName());
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~bash
javac -encoding UTF-8 ErasureLookupDemo.java
java ErasureLookupDemo
~~~

Output stdout đã được kiểm chứng bằng JDK 21 và sử dụng các tính năng tương thích Java 17:

~~~text
ctor/erased = java.lang.Number
field/erased = java.lang.Number
field/generic = T
put/erased = java.lang.Number
put/generic = T
putList/erased = java.util.List
putList/typeArg = java.lang.String
first/erased = java.lang.Number
first/generic = T
labels/isVarArgs = true
put(Integer) = not found
InheritsText.get/erased = Object
InheritsText.get/generic = T
TextStore.get = String, bridge=false
TextStore.get = Object, bridge=true
TextStore<Base> arg = java.lang.String
~~~

Giải thích kết quả:

1. **Kiểu sau erasure**: Store<T extends Number> khai báo constructor và method nhận T, nhưng getDeclaredConstructor/getDeclaredMethod phải nhận Number.class. Field và kiểu trả về T cũng có raw Class là Number.
2. **Khai báo generic được lưu lại**: getGenericType/getGenericParameterTypes/getGenericReturnType cho TypeVariable T; putList có ParameterizedType với actual type argument String dù lookup chỉ dùng List.class.
3. **Phương thức kế thừa**: InheritsText extends Base<String> nhưng không override get(); Method kế thừa từ Base vẫn có erased return type Object và generic return T. Muốn biết String là đối số kiểu của Base tại lớp con cần phân tích getGenericSuperclass().
4. **Bridge method**: TextStore override get() trả String. Trình biên dịch thêm bridge get() trả Object (isBridge() == true) để lệnh gọi qua Base tiếp tục dispatch đúng sau erasure. Thứ tự getDeclaredMethods() không được bảo đảm; ví dụ chủ động sắp xếp trước khi in để stdout ổn định.

## 4. Class<?> để tìm; Type để đọc chữ ký generic

| Việc cần làm | API | Dạng kết quả |
| --- | --- | --- |
| Tìm method hoặc constructor | getMethod/getDeclaredMethod/getConstructor/getDeclaredConstructor | Truyền Class<?>... đã xóa kiểu |
| Đọc kiểu tham số runtime | Method.getParameterTypes(), Constructor.getParameterTypes() | Class<?>[] |
| Đọc kiểu trả về/field runtime | Method.getReturnType(), Field.getType() | Class<?> |
| Đọc generic của method | Method.getGenericParameterTypes(), Method.getGenericReturnType() | Type[], Type |
| Đọc generic của constructor | Constructor.getGenericParameterTypes() | Type[] |
| Đọc generic của field | Field.getGenericType() | Type |
| Đọc generic superclass/interfaces | Class.getGenericSuperclass(), Class.getGenericInterfaces() | Type, Type[] |

Type là một interface tổng quát; không phải Type nào cũng là Class. Các trường hợp thường gặp:

- **Class<?>**: kiểu không parameterized tại vị trí đang xem.
- **ParameterizedType**: List<String>, Map<String, Integer>; dùng getRawType() và getActualTypeArguments().
- **TypeVariable<?>**: T; dùng getName() và getBounds().
- **WildcardType**: dấu ? trong List<? extends Number>; dùng getUpperBounds()/getLowerBounds().
- **GenericArrayType**: kiểu mảng còn chứa generic type variable, ví dụ T[].

Không cast Type trực tiếp sang ParameterizedType mà thiếu kiểm tra instanceof. Metadata generic nói về **chữ ký khai báo**. Nó không phải cơ chế runtime kiểm tra tất cả phần tử thực tế trong List đã đúng String, đặc biệt khi có raw types hoặc unchecked conversion.

Dùng lớp Store từ ví dụ trên, đoạn sau minh họa việc tách raw type và type argument (đây là **đoạn trích phụ thuộc Store**, không phải file chạy độc lập):

~~~java
Method m = Store.class.getDeclaredMethod("putList", List.class);
Type t = m.getGenericParameterTypes()[0];
if (t instanceof ParameterizedType p) {
    System.out.println(p.getRawType());               // interface java.util.List
    System.out.println(p.getActualTypeArguments()[0]); // class java.lang.String
}
~~~

Để suy ra ràng buộc T = String từ subclass extends Base<String>, phải duyệt generic superclass/interfaces, lấy các actual type arguments rồi ánh xạ chúng tới type variables ở lớp khai báo. getMethod() của phương thức kế thừa không tự thay mọi TypeVariable trong method đó bằng kiểu cụ thể của subclass.

## 5. Quy trình xử lý một yêu cầu lookup

1. **Xác định nơi khai báo và visibility.** Chọn getDeclaredMethod/getDeclaredConstructor/getDeclaredField khi cần member khai báo trực tiếp (kể cả non-public); chọn getMethod/getConstructor/getField khi yêu cầu public tương ứng.
2. **Đổi từng parameter type sang erasure.** Bỏ type arguments của parameterized type; thay T bằng Object hoặc erasure của bound đầu tiên; với mảng giữ dạng array class; với primitive dùng chính xác int.class/long.class...
3. **Tra tên + tham số đúng thứ tự.** Ví dụ foo(T, List<String>, int[]) với T extends Number cần Number.class, List.class, int[].class. Field chỉ tra theo tên.
4. **Đọc generic metadata khi bài toán cần.** Dùng getGeneric... và instanceof để phân biệt ParameterizedType, TypeVariable, WildcardType, GenericArrayType; khi liên quan kế thừa thì thêm ánh xạ type variables qua superclass/interfaces.
5. **Nếu liệt kê method sau override generic**, kiểm tra isBridge()/isSynthetic(); tùy nhu cầu có thể loại bridge khi tạo tài liệu hướng đến source API, nhưng giữ bridge khi phân tích dispatch JVM.

## 6. Lỗi phổ biến và cách nhận diện

- **NoSuchMethodException**: truyền Integer.class cho T extends Number; truyền Integer.class thay int.class; truyền String.class thay String[].class cho varargs; hoặc nhầm getDeclaredMethod với getMethod khi member thực ra được kế thừa.
- **Nhầm type argument với runtime parameter type**: getDeclaredMethod dùng List.class dù source ghi List<String> hay List<Integer>. Không có List<String>.class.
- **Nhầm generic superclass với chữ ký của method kế thừa**: extends Base<String> không làm Base.get() đột nhiên có erased return type String.
- **Không kiểm tra bridge methods**: getDeclaredMethods() có thể chứa method compiler sinh ra; không dựa vào thứ tự mảng Method khi tìm một phiên bản cụ thể.
- **Lạm dụng getGeneric... để xác nhận giá trị runtime**: thông tin kiểu generic phần lớn chỉ mô tả khai báo. Các phép cast/gọi invoke vẫn có thể gặp lỗi và còn bị ràng buộc bởi quyền truy cập hoặc module boundary.
- **Đọc return type như tham số tra cứu**: getMethod/getDeclaredMethod không nhận return type; nếu cần phân tích return type hãy đọc Method.getReturnType()/getGenericReturnType() sau khi lấy Method.

## 7. Bài tập tự kiểm tra

Với method khai báo **<T extends CharSequence> void consume(T[] data, List<? super String> output)**, nó được tìm bằng:

~~~java
clazz.getDeclaredMethod("consume", CharSequence[].class, java.util.List.class);
~~~

T[] được xóa thành CharSequence[] do bound của T; List<? super String> được xóa thành List. Khi đọc getGenericParameterTypes()[0], bạn thường nhận GenericArrayType chứa TypeVariable T; tham số thứ hai là ParameterizedType chứa WildcardType có lower bound String. Tra cứu bằng String[].class là sai dù một lời gọi thực tế có thể truyền mảng String[].

**Ghi nhớ:** dùng các Class<?> đã erasure để **tìm** thành viên; dùng Type để **phân tích** thông tin generic đã khai báo. Với generic inheritance và override, kiểm tra thêm generic superclass cùng bridge methods.

### Tài liệu tham khảo

- Java Language Specification 17, §4.6 — Type Erasure: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6
- JDK 17 Class API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- JDK 17 Method API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- JDK 17 ParameterizedType API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html
