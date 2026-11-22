# getGenericSuperclass và getGenericInterfaces trong Java Reflection

Khi Java Reflection phân tích một class, có hai câu hỏi khác nhau: **lớp này kế thừa trực tiếp lớp nào?** và **nó khai báo triển khai/mở rộng trực tiếp những interface nào?**. Nếu quan hệ có tham số kiểu, ví dụ **extends Repository<Order>** hoặc **implements Handler<List<String>>**, những API chỉ trả Class thường làm mất thông tin tham số generic. Hai phương thức **Class.getGenericSuperclass()** và **Class.getGenericInterfaces()** giúp đọc những khai báo generic đó từ class file.

Bài này tập trung vào cách dùng hai API, phân biệt Class với Type/ParameterizedType, giới hạn “trực tiếp” trong cây kế thừa, cách xử lý type variable qua nhiều cấp và những trường hợp đặc biệt như interface, raw type, anonymous subclass hay array class. Ví dụ sử dụng Java 17+ và không cần thư viện bên ngoài.

## 1. Phân biệt API thông thường và API generic

Một class có thể khai báo:

~~~java
class Base<T> {}

interface Named<T> {}

class User extends Base<String> implements Named<Integer> {}
~~~

Từ **User.class**, các API liên quan trả:

| API | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| **getSuperclass()** | Class<?> hoặc null | Class superclass trực tiếp, sau erasure; ví dụ Base.class |
| **getGenericSuperclass()** | Type hoặc null | Khai báo superclass trực tiếp, có thể là Base<String> |
| **getInterfaces()** | Class<?>[] | Các interface trực tiếp, kiểu runtime; ví dụ Named.class |
| **getGenericInterfaces()** | Type[] | Các interface trực tiếp, có thể là Named<Integer> |
| **getTypeParameters()** | TypeVariable<?>[] | Các type variable mà chính class/interface khai báo, như T trong Base<T> |
| **getAnnotatedSuperclass()** | AnnotatedType hoặc null | Type use của superclass kèm annotation TYPE_USE nếu có |
| **getAnnotatedInterfaces()** | AnnotatedType[] | Type use của các interface trực tiếp kèm annotation TYPE_USE nếu có |

**Quan trọng:** getGenericSuperclass/getGenericInterfaces không trả về “danh sách tất cả tổ tiên”. Chúng phản ánh **cạnh trực tiếp** trong khai báo class/interface đang xét. Để tìm mọi interface gián tiếp hoặc thay thế type variable trên nhiều lớp, phải tự duyệt tiếp.

Đối với **extends Base<String>**, getSuperclass() cung cấp **Class của Base**, còn getGenericSuperclass() thường cung cấp **ParameterizedType** gồm raw type Base và actual type argument String.

## 2. Cấu trúc Type và ParameterizedType

Đối tượng trả về từ API generic có kiểu tổng quát **java.lang.reflect.Type**. Type là interface chung, không phải mọi Type đều là Class.

| Dạng Type | Ví dụ | Cách nhận biết / truy vấn |
| --- | --- | --- |
| **Class<?>** | Object, String, raw Base, một interface không parameterized | Kiểm tra **instanceof Class<?>** |
| **ParameterizedType** | Base<String>, Handler<List<Integer>> | **getRawType()**, **getActualTypeArguments()**, **getOwnerType()** |
| **TypeVariable<?>** | T, E, X trong khai báo generic | **getName()**, **getBounds()**, **getGenericDeclaration()** |
| **WildcardType** | ? extends Number, ? super String | **getUpperBounds()**, **getLowerBounds()** |
| **GenericArrayType** | T[] nếu thành phần là type variable | **getGenericComponentType()** |

Một phản xạ an toàn luôn **phân nhánh theo loại Type** trước khi ép kiểu:

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;

Type type = User.class.getGenericSuperclass();
if (type instanceof ParameterizedType parameterized) {
    Type raw = parameterized.getRawType();
    Type[] arguments = parameterized.getActualTypeArguments();
    System.out.println(raw);            // class Base, tên phụ thuộc package/nesting
    System.out.println(arguments[0]);   // class java.lang.String
}
~~~

Đây là đoạn minh họa cần có các lớp Base/User cùng compilation unit ở mục 1; hai dòng bình luận không phải stdout chuẩn hóa của một chương trình độc lập.

### Ba thành phần của ParameterizedType

- **getRawType()**: class/interface gốc, ví dụ Base trong Base<String>. Kết quả được khai báo là Type; khi làm việc với Reflection thông thường của JVM, raw type chủ yếu là Class<?>.
- **getActualTypeArguments()**: các đối số kiểu ở cạnh kế thừa đang khai báo, ví dụ String hoặc một Type phức tạp như List<T>. Nếu khai báo nhiều đối số kiểu, thứ tự đúng theo khai báo.
- **getOwnerType()**: kiểu bao ngoài khi parameterized type là kiểu thành viên, ví dụ Outer<String>.Inner<Integer>; với top-level type thì thường null.

**Không dùng cast trực tiếp**:

~~~java
// Không an toàn nếu superclass là Object, raw type hoặc không có superclass:
ParameterizedType p = (ParameterizedType) clazz.getGenericSuperclass();
~~~

Đoạn này cố tình minh họa antipattern. getGenericSuperclass() có thể trả **Class<?>** hoặc **null**; cast trên sẽ gây ClassCastException hoặc dẫn đến NullPointerException về sau.

### Type.getTypeName()

Mỗi Type có **getTypeName()** để lấy chuỗi biểu diễn kiểu, thuận tiện cho log và tài liệu. Tuy nhiên, chuỗi này không phải giao diện chuẩn để parse ngược mọi cấu trúc generic; khi viết tool, xử lý **các đối tượng Type theo loại** vẫn chính xác hơn. Tên đầy đủ có thể bao gồm package, dấu $ của nested class và những biểu thức generic phức tạp.

## 3. getGenericSuperclass(): chỉ lớp cha trực tiếp

Hãy phân biệt các dạng khai báo sau:

~~~java
class Parent<T> {}
class Concrete extends Parent<String> {}
class Plain {}
class RawChild extends Parent {} // Kế thừa raw type, thông tin String không được khai báo
~~~

| Đối tượng Class | getGenericSuperclass() | Giải thích |
| --- | --- | --- |
| Concrete.class | ParameterizedType mô tả Parent<String> | Khai báo superclass có actual type argument |
| Parent.class | Class mô tả Object | Parent không ghi extends và cha mặc định là Object |
| Plain.class | Class mô tả Object | Superclass mặc định |
| RawChild.class | Class mô tả Parent | Raw extends không cung cấp actual type argument |
| Object.class | null | Object không có superclass |
| List.class (interface) | null | Interface không có class superclass |
| int.class, void.class | null | Primitive và void không có superclass |
| String[].class | Class mô tả Object | Array class có superclass Object |

Mỗi lần gọi chỉ đọc **một cấp class superclass**. Ví dụ:

~~~text
Leaf extends Middle<Integer>
Middle<X> extends Parent<List<X>>
Parent<T> extends Object
~~~

Khi gọi **Leaf.class.getGenericSuperclass()**, kết quả là **Middle<Integer>**, không phải Parent<List<Integer>>. Khi gọi **Middle.class.getGenericSuperclass()**, kết quả là **Parent<List<X>>**. Muốn có Parent<List<Integer>> theo ngữ cảnh Leaf, phải ghép hai cạnh và thay **X → Integer** trong chữ ký của Middle.

Đây chính là giới hạn quan trọng nhất của các thư viện tự phân tích hierarchy: chúng có thể đọc đúng Type của mỗi cạnh, nhưng vẫn suy luận sai nếu bỏ qua ánh xạ type variable.

### Class không được khai báo generic vẫn có generic superclass

Concrete có thể không có type variable nào của riêng mình:

~~~java
Concrete.class.getTypeParameters().length == 0
~~~

nhưng vẫn có **Parent<String>** ở getGenericSuperclass(). Ngược lại, Parent.class.getTypeParameters() có T, nhưng Parent.class.getGenericSuperclass() chỉ là Object. Hai API trả lời hai câu hỏi khác nhau: **class này khai báo type variable nào** và **class này dùng kiểu generic gì ở cạnh extends**.

## 4. getGenericInterfaces(): danh sách interface trực tiếp

Với:

~~~java
interface Keyed<T> {}
interface Logged {}
class Service implements Keyed<String>, Logged {}
~~~

**Service.class.getGenericInterfaces()** trả một mảng Type có hai phần tử theo thứ tự khai báo:

1. ParameterizedType biểu diễn Keyed<String>.
2. Class<?> biểu diễn Logged vì interface này không được parameterized tại vị trí đó.

Nếu class không trực tiếp khai báo implements, kết quả thường là **mảng rỗng**, kể cả khi nó **được thừa hưởng** một interface từ superclass.

~~~java
class ParentService implements Keyed<String> {}
class ChildService extends ParentService {}
~~~

**ChildService.class.getGenericInterfaces()** trả mảng rỗng; **ParentService.class.getGenericInterfaces()** chứa Keyed<String>. Điều đó **không có nghĩa** ChildService không phải là Keyed: **Keyed.class.isAssignableFrom(ChildService.class)** vẫn có thể trả true do quan hệ inheritance.

Với một **interface** đang extends các interface khác, getGenericInterfaces() trả các **superinterfaces trực tiếp**, theo thứ tự được khai báo:

~~~java
interface Tag<T> {}
interface Compound<T> extends Tag<java.util.List<T>> {}
~~~

**Compound.class.getGenericInterfaces()** chứa Type đại diện **Tag<List<T>>**, trong đó T là TypeVariable được khai báo bởi Compound. **Compound.class.getGenericSuperclass()** trả **null**, vì Compound là interface và không có class superclass.

### Thứ tự và array type

Java SE 17 chỉ rõ thứ tự các interface từ getInterfaces/getGenericInterfaces theo thứ tự trong **implements** hoặc **extends** clause. Vì vậy khi interface trực tiếp được khai báo là A, B thì mảng tương ứng là A, B.

Với **array class**, getGenericInterfaces() trả hai interface của array runtime: **Cloneable**, **java.io.Serializable**, theo thứ tự đó. Với primitive/void hoặc class/interface không khai báo trực tiếp interface nào thì mảng rỗng. Mảng có superclass Object theo getGenericSuperclass() nhưng không chứa generic element argument theo cơ chế parameterized class.

## 5. Ví dụ chạy hoàn chỉnh trên Java 17+

Chương trình dưới đây cho thấy sự khác biệt giữa generic superclass, generic interfaces, superclass sau erasure, type arguments, raw inheritance và interface được thừa hưởng gián tiếp. Hàm **display(Type)** chủ động in tên ngắn để stdout ổn định, tránh phụ thuộc vào tên đầy đủ của nested class.

Lưu nguyên văn vào **HierarchyReflectionDemo.java**:

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class HierarchyReflectionDemo {
    interface Named<T> {}
    interface Audited {}
    interface Chain<T> extends Named<List<T>> {}

    static class Base<T> {}
    static class Direct extends Base<String> implements Named<Integer>, Audited {}
    static class Middle<X> extends Base<List<X>> implements Named<X> {}
    static class Leaf extends Middle<Integer> {}
    static class Raw extends Base {} // Raw superclass: argument information absent
    static class Plain {}

    private static String display(Type t) {
        if (t == null) return "null";
        if (t instanceof ParameterizedType p) {
            String args = Arrays.stream(p.getActualTypeArguments())
                    .map(HierarchyReflectionDemo::display)
                    .collect(Collectors.joining(", "));
            return display(p.getRawType()) + "<" + args + ">";
        }
        if (t instanceof Class<?> c) return c.getSimpleName();
        if (t instanceof TypeVariable<?> v) return v.getName();
        return t.getTypeName();
    }

    private static String interfacesOf(Class<?> type) {
        return Arrays.stream(type.getGenericInterfaces())
                .map(HierarchyReflectionDemo::display)
                .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) {
        System.out.println("Direct superclass=" + display(Direct.class.getGenericSuperclass()));
        System.out.println("Direct interfaces=" + interfacesOf(Direct.class));
        System.out.println("Direct raw superclass=" + Direct.class.getSuperclass().getSimpleName());

        Type supertype = Direct.class.getGenericSuperclass();
        if (supertype instanceof ParameterizedType p) {
            System.out.println("Direct super raw=" + display(p.getRawType()));
            System.out.println("Direct super arg=" + display(p.getActualTypeArguments()[0]));
        }

        System.out.println("Leaf superclass=" + display(Leaf.class.getGenericSuperclass()));
        System.out.println("Leaf interfaces=" + interfacesOf(Leaf.class));
        System.out.println("Middle superclass=" + display(Middle.class.getGenericSuperclass()));
        System.out.println("Middle interfaces=" + interfacesOf(Middle.class));
        System.out.println("Chain superclass=" + display(Chain.class.getGenericSuperclass()));
        System.out.println("Chain interfaces=" + interfacesOf(Chain.class));
        System.out.println("Raw superclass=" + display(Raw.class.getGenericSuperclass()));
        System.out.println("Plain superclass=" + display(Plain.class.getGenericSuperclass()));
        System.out.println("Object superclass=" + display(Object.class.getGenericSuperclass()));
        System.out.println("List superclass=" + display(List.class.getGenericSuperclass()));
        System.out.println("String[] superclass=" + display(String[].class.getGenericSuperclass()));
    }
}
~~~

Từ thư mục chứa file, biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 HierarchyReflectionDemo.java
java HierarchyReflectionDemo
~~~

Stdout đã được kiểm tra bằng JDK 21 với source tương thích Java 17:

~~~text
Direct superclass=Base<String>
Direct interfaces=[Named<Integer>, Audited]
Direct raw superclass=Base
Direct super raw=Base
Direct super arg=String
Leaf superclass=Middle<Integer>
Leaf interfaces=[]
Middle superclass=Base<List<X>>
Middle interfaces=[Named<X>]
Chain superclass=null
Chain interfaces=[Named<List<T>>]
Raw superclass=Base
Plain superclass=Object
Object superclass=null
List superclass=null
String[] superclass=Object
~~~

### Cách đọc kết quả

- **Direct superclass=Base<String>**: Type chứa đối số String đúng như cạnh extends.
- **Direct raw superclass=Base**: Class.getSuperclass() không giữ String.
- **Direct interfaces=[Named<Integer>, Audited]**: một interface parameterized và một interface không parameterized, theo thứ tự implements.
- **Leaf interfaces=[]**: Leaf không trực tiếp khai báo implements, dù vẫn nhận hợp đồng Named qua Middle.
- **Middle superclass=Base<List<X>>**: Type còn X vì đang đọc cạnh khai báo bởi Middle, chưa thay X bằng Integer của Leaf.
- **Chain superclass=null**: interface không có class superclass. Nhưng **Chain interfaces=[Named<List<T>>]** thể hiện quan hệ extends với interface.
- **Raw superclass=Base**: kế thừa raw type; không có String hay type argument nào để lấy từ cạnh đó.
- **Plain superclass=Object** trong khi **Object superclass=null**.
- **String[] superclass=Object**: array runtime là một class có superclass Object; nó còn trực tiếp thực thi Cloneable và Serializable.

Hàm display() là tiện ích minh họa. Trong ứng dụng thực tế, Type.getTypeName() có thể trả tên đầy đủ như **java.util.List<java.lang.String>** hoặc tên nested class có dấu $, nên không nên sao chép output đã rút gọn để so sánh chuỗi tên runtime.

## 6. Duyệt nhiều cấp và thay thế TypeVariable

Hai API được bàn trong bài cung cấp **các cạnh trực tiếp**. Để truy ra kiểu của một interface hoặc superclass trong ngữ cảnh một class con cuối cùng, cần duyệt **toàn bộ graph kế thừa** và mang theo ánh xạ kiểu generic.

Xét lại chuỗi:

~~~java
class Base<T> {}
class Middle<X> extends Base<List<X>> {}
class Leaf extends Middle<Integer> {}
~~~

Từ Leaf:

1. Đọc **Leaf.class.getGenericSuperclass()** → Middle<Integer>.
2. Trong ParameterizedType này, raw type là Middle.class và actual argument là Integer.class. Tạo ánh xạ **X → Integer** dựa trên Middle.class.getTypeParameters().
3. Đọc **Middle.class.getGenericSuperclass()** → Base<List<X>>.
4. Thay TypeVariable X bằng Integer theo ánh xạ từ bước 2, được **Base<List<Integer>>** trong ngữ cảnh Leaf.
5. Nếu tiếp tục sang Base.class, duy trì thêm ánh xạ **T → List<Integer>** nếu cần hiểu kiểu của các field/method do Base khai báo.

Đây là quá trình **type-variable substitution**, không phải kết quả tự động của một lệnh getGenericSuperclass() duy nhất. Tương tự khi đi từ class đến interface gián tiếp phải duyệt cả superclasses **và** getGenericInterfaces() của mỗi lớp/interface.

### Pseudocode thuật toán phân giải generic hierarchy

~~~text
resolve(targetClass, soughtRawType):
  queue = [(targetClass, emptyMapping)]
  while queue not empty:
    (currentType, mapping) = take(queue)
    raw = rawClassOf(currentType)
    localMapping = bind typeParameters(raw) to actualTypeArguments(currentType)
                   after replacing variables via mapping
    if raw == soughtRawType:
       return localMapping or resolved parameterized view
    enqueue raw.getGenericSuperclass() if non-null
    enqueue each raw.getGenericInterfaces()
    propagate mappings through every edge
  return not found
~~~

Đây là **pseudocode khái niệm**, không phải Java chạy độc lập. Một implementation đầy đủ phải xử lý nhiều dạng Type, chu kỳ do interface graph, owner type của nested class, type variable có bound, wildcard, generic array, raw type và trường hợp nhiều đường đến cùng một interface. Nên lưu một tập các node/ánh xạ đã thăm và xác định rõ hành vi khi thông tin type argument bị raw inheritance làm mất.

Để xác định **một class có implement interface bất kể generic argument**, có thể dùng **Interface.class.isAssignableFrom(SomeClass.class)**. Nhưng phương thức này chỉ trả boolean dựa trên quan hệ raw class, **không** trả List<Integer> hay thay thế các TypeVariable.

### Khi nào không thể suy ra kiểu cụ thể?

Với:

~~~java
class Container<T> {}
Container<String> first = new Container<>();
Container<Integer> second = new Container<>();
~~~

Hai đối tượng đều có **getClass() == Container.class**. Type arguments của đối tượng được tạo thông thường không tồn tại như hai Class runtime khác nhau. **Container.class.getGenericSuperclass()** chỉ trả Object, không thể tự khôi phục String/Integer từ first/second.

Một cách phổ biến để giữ kiểu trong metadata là tạo **anonymous subclass**:

~~~java
Container<String> captured = new Container<String>() {};
Type capturedParent = captured.getClass().getGenericSuperclass();
// capturedParent có thể là ParameterizedType biểu diễn Container<String>
~~~

Đây là fragment dùng Container từ ví dụ; phải import java.lang.reflect.Type. Anonymous subclass này có superclass khai báo trực tiếp **Container<String>**, nên đọc được String ở **Signature của anonymous class**. Nó **không** chứng minh rằng mọi đối tượng Container<String> thông thường đều lưu String. Khi tạo anonymous subclass trong ngữ cảnh generic chưa ràng buộc, metadata có thể chứa TypeVariable chứ không nhất thiết là concrete Class.

## 7. Raw type, wildcard, nested type và annotation

### Raw inheritance

Nếu **class Raw extends Base** thay vì extends Base<String>, getGenericSuperclass() thường là **Class** Base, không phải ParameterizedType. Bạn không thể lấy actual type argument đã không tồn tại trong khai báo. Đừng tự gán Object rồi nói rằng đó là actual type argument trong Signature; **erasure thành Object** là quy tắc về kiểu runtime, khác với việc có **đối số generic được khai báo**.

### Wildcard và generic argument lồng nhau

Một class có thể khai báo superclass hoặc interface với biểu thức kiểu lồng nhau:

~~~java
interface Source<T> {}
class WildcardSource implements Source<List<? extends Number>> {}
~~~

Khi truy xuất interface trực tiếp:

~~~java
Type t = WildcardSource.class.getGenericInterfaces()[0];
if (t instanceof ParameterizedType p) {
    Type nested = p.getActualTypeArguments()[0]; // List<? extends Number>
}
~~~

Đây là ví dụ mảnh code: các class Source/WildcardSource phải được khai báo như trên. nested thường là ParameterizedType của List, và type argument trong List là **WildcardType** với upper bound Number. Không ép luôn nested thành Class, vì nested cũng có thể là TypeVariable, WildcardType ở vị trí khác hoặc dạng generic phức tạp.

### Nested/inner class và owner type

Khi type nằm trong một generic outer class, cấu trúc có thể là Outer<String>.Inner<Integer>. Nếu một subclass extends kiểu đó, **ParameterizedType.getOwnerType()** có thể chứa Outer<String>, còn getActualTypeArguments() của inner phần lớn mô tả type parameters riêng của Inner. Không bỏ qua owner type khi cần xác định đủ thông tin generic.

### Annotation trên vị trí extends/implements

Nếu có **@Target(ElementType.TYPE_USE)** cùng **@Retention(RetentionPolicy.RUNTIME)**, annotation trên kiểu được sử dụng tại khai báo extends/implements có thể được xem qua:

- **getAnnotatedSuperclass()**: AnnotatedType của superclass trực tiếp.
- **getAnnotatedInterfaces()**: AnnotatedType[] của từng interface trực tiếp.
- **AnnotatedParameterizedType.getAnnotatedActualTypeArguments()** khi muốn đào sâu annotation trên các type arguments của một parameterized type.

Khác biệt giữa **getGenericSuperclass()** và **getAnnotatedSuperclass()** là API thứ hai giữ lớp thông tin annotation TYPE_USE. Không phải annotation nào trong source cũng có thể đọc ở runtime; hãy kiểm tra @Retention và nơi đặt annotation.

## 8. Ngoại lệ và độ tin cậy của metadata

Khi parse generic Signature trong file .class, Reflection có thể gặp dữ liệu bị thiếu hoặc không hợp lệ (ví dụ class file đã bị công cụ bytecode biến đổi sai, hoặc dependency dùng trong type argument không còn tại runtime). Tài liệu Java 17 của **getGenericSuperclass** và **getGenericInterfaces** liệt kê:

- **GenericSignatureFormatError**: chữ ký generic trong class file không phù hợp định dạng theo JVM specification.
- **TypeNotPresentException**: kiểu được tham chiếu trong generic superclass/superinterface không tồn tại hoặc không thể resolve khi đọc metadata.
- **MalformedParameterizedTypeException**: kiểu parameterized trong metadata không thể tạo hợp lệ.

Các trường hợp này khác với **ClassNotFoundException** xảy ra khi code trực tiếp nạp class bằng tên. Không cần bắt cả ba ở mọi ứng dụng đơn giản, nhưng một scanner xử lý bytecode từ nguồn không tin cậy nên ghi rõ lỗi, phân biệt metadata bị hỏng với việc một class không khai báo interface/superclass.

Với class biên dịch Java bình thường, thông tin generic nằm trong **Signature attribute** của class file. Phần lớn runtime thực hiện type erasure để thực thi; Signature cung cấp thông tin bổ sung cho Reflection. Nếu Signature bị xóa bởi công cụ build/obfuscator, class vẫn có thể load, nhưng generic metadata có thể không còn đủ.

### Có cần setAccessible(true) để đọc hierarchy?

**Không.** getGenericSuperclass() và getGenericInterfaces() trên Class đọc metadata kiểu/class, không phải lời gọi private method hoặc đọc private field. Quy tắc mở package JPMS bằng opens chủ yếu quan trọng khi thực hiện **deep reflective member access**, chứ không phải điều kiện bắt buộc để chỉ đọc khai báo generic hierarchy.

## 9. Quy trình thực hành cho thư viện phân tích type

Giả sử một framework muốn tìm type argument của Handler<T> mà user class triển khai qua nhiều lớp:

1. **Bắt đầu ở runtime class** được cung cấp, nhưng xác nhận class đó thực sự chứa generic signature đủ để phân tích; instance thông thường có thể đã mất argument do erasure.
2. **Duyệt class superclass trực tiếp** qua getGenericSuperclass() và **interface trực tiếp** qua getGenericInterfaces() tại từng node.
3. **Kiểm tra dạng Type** trước khi xử lý: Class, ParameterizedType, TypeVariable, WildcardType, GenericArrayType.
4. **Gắn type variable với actual type argument** khi đi qua một ParameterizedType và duy trì mapping xuyên các cấp. Không dừng ở raw type hoặc dựa vào tên T/E/X.
5. **Xác định target raw class** nhờ ParameterizedType.getRawType() hay Type là Class, thay vì so chuỗi getTypeName().
6. **Nếu encounter raw inheritance**, công khai rằng generic argument không đủ dữ liệu; tránh tự bịa ra kiểu cụ thể.
7. **Kiểm tra direct/inherited đúng ngữ cảnh**: getGenericInterfaces() trả trực tiếp, còn assignability có thể đúng do cấp tổ tiên.
8. **Có chiến lược với nested owner, wildcard và array** nếu framework cần hỗ trợ đầy đủ các biểu thức kiểu Java.
9. **Viết test cho nhiều tầng** như Leaf → Middle<Integer> → Base<List<X>>, một interface extends interface khác, raw type, anonymous subclass, primitive/array và Java module boundaries.

Đối với tác vụ chỉ cần biết “có phải một interface không?”, dùng **Class.isAssignableFrom** là đủ. Chỉ xây generic type resolver đầy đủ khi cần chính xác **kiểu tham số** của abstraction như Repository<Customer> hoặc Handler<List<Order>>.

## 10. Lỗi hay gặp

- **Ép mọi getGenericSuperclass() thành ParameterizedType:** superclass có thể là Class hoặc null.
- **Đọc getGenericInterfaces() rồi kết luận không implements interface:** class có thể kế thừa interface từ superclass; cần duyệt tiếp hoặc dùng isAssignableFrom để kiểm tra quan hệ raw.
- **Nhầm superclass của interface là Object:** getGenericSuperclass() của interface trả null, dù Java interface vẫn là reference type có quan hệ với Object theo những quy tắc ngôn ngữ khác.
- **Cho rằng kết quả của Leaf đã là Base<List<Integer>>:** Leaf.getGenericSuperclass() chỉ là Middle<Integer>; phải thay X qua cấp Middle.
- **Dùng getInterfaces() và mong nhận generic arguments:** kết quả là Class<?>[], không chứa các Type arguments của cạnh khai báo.
- **Nhầm generic declaration với runtime object:** Container<String> tạo trực tiếp không lưu String dưới dạng một Class riêng.
- **Coi getTypeName() là format ổn định để parse:** tốt hơn dùng Type và các subtype của nó.
- **Quên raw inheritance:** raw Base không tự mang argument String, và không nên coi erasure Object là metadata actual argument được khai báo.
- **Không xử lý nested owner/type-use annotations:** các framework cần metadata đầy đủ nên phân tích thêm getOwnerType/getAnnotatedInterfaces/getAnnotatedSuperclass khi hợp lý.
- **Nhầm Class.getTypeParameters với getGenericSuperclass:** API đầu đọc biến kiểu do chính class khai báo; API sau đọc kiểu superclass ở cạnh extends.

## 11. Tự kiểm tra

**Câu 1.** class Child extends Base<String> nhưng không implements interface nào. getGenericSuperclass() và getGenericInterfaces() trả gì?

**Đáp án:** ParameterizedType mô tả Base<String>; mảng Type[] rỗng.

**Câu 2.** interface Fancy<T> extends Named<List<T>>. Fancy.class.getGenericSuperclass() trả gì?

**Đáp án:** null vì Fancy là interface. Fancy.class.getGenericInterfaces() trả một ParameterizedType mô tả Named<List<T>>.

**Câu 3.** class Leaf extends Middle<Integer>, còn Middle<X> extends Base<List<X>>. Có thể lấy Base<List<Integer>> chỉ bằng Leaf.class.getGenericSuperclass() không?

**Đáp án:** Không. Nó trả Middle<Integer>; cần đọc tiếp Middle.getGenericSuperclass(), rồi thay X bằng Integer.

**Câu 4.** class Raw extends Base. Đọc getGenericSuperclass() thấy Base.class, vậy có thể khôi phục type argument String không?

**Đáp án:** Không. Raw khai báo raw inheritance, không chứa actual type argument String trong cạnh extends.

**Câu 5.** Một class kế thừa implementation của interface I qua superclass, nhưng getGenericInterfaces() trên class ấy trả mảng rỗng. Đây là lỗi Reflection không?

**Đáp án:** Không. API trả interface **trực tiếp**; interface được thừa hưởng gián tiếp phải duyệt tổ tiên. I.class.isAssignableFrom(ThatClass.class) có thể vẫn true.

**Câu 6.** getGenericSuperclass() của String[].class là gì? Còn Object.class và List.class?

**Đáp án:** String[] có superclass Object; Object và interface List trả null.

**Câu 7.** Tại sao new Box<String>() {} có thể cho biết String nhưng new Box<String>() thông thường không cho biết?

**Đáp án:** Dấu {} tạo anonymous subclass có khai báo extends Box<String> trong generic Signature của **anonymous class**. Instance Box thông thường chỉ mang runtime Class Box sau erasure.

**Ghi nhớ:** **getGenericSuperclass()** đọc **một superclass trực tiếp** dưới dạng Type; **getGenericInterfaces()** đọc **các interface trực tiếp** dưới dạng Type[]. Muốn giữ thông tin generic qua nhiều cấp, phải phân tích **ParameterizedType**, **TypeVariable** và thực hiện **thay thế type argument theo từng cạnh kế thừa**.

### Tài liệu tham khảo

- Java SE 17 — Class.getGenericSuperclass/getGenericInterfaces, getAnnotatedSuperclass/getAnnotatedInterfaces: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 — Type: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html
- Java SE 17 — ParameterizedType: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html
- Java SE 17 — TypeVariable: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html
- Java SE 17 — WildcardType: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/WildcardType.html
- Java SE 17 — GenericArrayType: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html
- Java Language Specification 17 — Types, parameterized types và erasure: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html
