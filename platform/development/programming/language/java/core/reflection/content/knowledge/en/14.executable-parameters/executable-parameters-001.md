# Executable dùng chung cho Method và Constructor trong Java Reflection

Trong Reflection của Java, **Method** đại diện một phương thức, còn **Constructor<T>** đại diện một constructor. Cả hai cùng kế thừa lớp trừu tượng **java.lang.reflect.Executable**, được giới thiệu từ Java 8, vì chúng có rất nhiều thông tin chung: danh sách tham số, kiểu generic, annotation, ngoại lệ khai báo, modifiers, biến kiểu và cờ varargs/synthetic.

Executable hữu ích nhất khi viết công cụ xử lý metadata của cả method lẫn constructor, chẳng hạn framework dependency injection, validation, binding, serialization, lập tài liệu API hoặc bộ phân tích chữ ký. Thay vì viết hai vòng lặp gần giống nhau cho Method và Constructor, ta có thể viết một hàm nhận Executable và đọc những thuộc tính chung.

**Giới hạn cốt lõi:** Executable là lớp nền dùng để **mô tả và phân tích** một thành phần có thể thực thi. Nó không có một phương thức invoke/newInstance chung: để gọi thực tế, phải phân biệt Method.invoke(...) và Constructor.newInstance(...).

## 1. Quan hệ kiểu và phạm vi trách nhiệm

Sơ đồ lớp đơn giản:

~~~text
java.lang.Object
    └── java.lang.reflect.AccessibleObject
          └── java.lang.reflect.Executable
                ├── java.lang.reflect.Method
                └── java.lang.reflect.Constructor<T>
~~~

Executable còn triển khai các interface **Member**, **AnnotatedElement**, **GenericDeclaration** và kế thừa chức năng truy cập reflective của **AccessibleObject**. Trên Java 17, đây là abstract sealed class chỉ cho phép Method và Constructor trực tiếp kế thừa.

| Khái niệm | Vai trò |
| --- | --- |
| **Method** | Đại diện phương thức khai báo bởi class/interface; có tên, kiểu trả về, receiver và phương thức invoke |
| **Constructor<T>** | Đại diện constructor của class T; gọi newInstance để tạo instance của class khai báo |
| **Executable** | Cung cấp API metadata chung cho Method và Constructor |
| **Parameter** | Đại diện một tham số trong chữ ký runtime của một Executable |
| **AccessibleObject** | Cung cấp các API như setAccessible/trySetAccessible để yêu cầu điều chỉnh kiểm tra truy cập |

Ví dụ về đa hình:

~~~java
import java.lang.reflect.Executable;
import java.lang.reflect.Method;
import java.lang.reflect.Constructor;

Method method = String.class.getMethod("substring", int.class);
Constructor<StringBuilder> constructor = StringBuilder.class.getConstructor();
Executable e1 = method;
Executable e2 = constructor;

System.out.println(e1.getParameterCount()); // 1
System.out.println(e2.getParameterCount()); // 0
~~~

Đoạn này có thể đặt trong một method khai báo throws ReflectiveOperationException. Hai đối tượng đều gọi được **getParameterCount()**, vì phương thức đó nằm ở Executable. Nhưng chỉ **method** có **invoke(receiver, args...)**, và chỉ **constructor** có **newInstance(args...)**.

Không cố ép Executable thành Method nếu chưa kiểm tra kiểu. Có thể phân nhánh bằng:

~~~java
if (executable instanceof Method m) {
    // Có thể dùng Method.getReturnType(), Method.invoke(...)...
} else if (executable instanceof Constructor<?> c) {
    // Có thể dùng Constructor.newInstance(...)...
}
~~~

Đây là fragment: biến executable phải tồn tại trong ngữ cảnh.

## 2. Những API metadata dùng chung

Các nhóm dưới đây là trọng tâm của lớp Executable.

| API | Kiểu kết quả | Chức năng |
| --- | --- | --- |
| **getDeclaringClass()** | Class<?> | Lớp/interface khai báo thành phần |
| **getName()** | String | Tên phương thức hoặc tên constructor theo quy ước Reflection |
| **getModifiers()** | int | Modifiers như public/private/protected; giải mã bằng Modifier |
| **getParameterCount()** | int | Tổng tham số runtime, kể cả một số tham số implicit/synthetic |
| **getParameterTypes()** | Class<?>[] | Kiểu tham số sau erasure, theo thứ tự |
| **getGenericParameterTypes()** | Type[] | Thông tin kiểu generic được khai báo khi có metadata |
| **getParameters()** | Parameter[] | Đối tượng Parameter cho từng tham số runtime |
| **getParameterAnnotations()** | Annotation[][] | Annotation trên khai báo từng tham số |
| **getAnnotatedParameterTypes()** | AnnotatedType[] | Annotation đặt ở vị trí sử dụng kiểu tham số (TYPE_USE) |
| **getExceptionTypes()** | Class<?>[] | Các kiểu exception trong throws theo runtime Class |
| **getGenericExceptionTypes()** | Type[] | Các kiểu exception trong throws có thông tin generic |
| **getAnnotatedExceptionTypes()** | AnnotatedType[] | Annotation TYPE_USE trên kiểu exception |
| **getTypeParameters()** | TypeVariable<?>[] | Type variables được khai báo bởi chính method/constructor |
| **isVarArgs()** | boolean | Có khai báo tham số cuối dạng varargs hay không |
| **isSynthetic()** | boolean | Thành phần có do compiler sinh ra dạng synthetic hay không |
| **toGenericString()** | String | Biểu diễn chữ ký có generic và modifiers |
| **getAnnotatedReturnType()** | AnnotatedType | Thông tin kiểu trả về có annotation theo hợp đồng của từng subtype |
| **getAnnotatedReceiverType()** | AnnotatedType hoặc null | Kiểu receiver được khai báo tại vị trí phù hợp; không phải mọi executable đều có receiver |

Một số phương thức như **getParameterCount()**, **getParameters()**, **getGenericParameterTypes()** có phần triển khai chung trong Executable; một số phương thức khác là abstract, được Method và Constructor cài đặt. Từ góc độ người dùng API, vẫn có thể gọi chúng thông qua biến kiểu Executable.

### Chữ ký không phải là lời gọi thực thi

Executable cung cấp **getParameterCount()**, nhưng không tự cung cấp **invoke()**. Để thực thi:

- **Method.invoke(Object receiver, Object... args)** gọi method đã chọn; với static method, receiver có thể là null.
- **Constructor.newInstance(Object... initargs)** tạo đối tượng của declaring class.
- Cả hai đều có thể tạo **InvocationTargetException** nếu phần thân method hoặc constructor ném ngoại lệ.
- **IllegalAccessException** liên quan tới quyền gọi; **IllegalArgumentException** thường liên quan receiver hoặc arguments không phù hợp. Các chi tiết kiểm tra access thuộc Method/Constructor và môi trường module.

Khi viết một metadata scanner, tốt nhất giữ biến kiểu **Executable** trong phần phân tích chung, và chỉ phân nhánh đến subtype khi cần invoke hoặc API đặc thù.

## 3. Parameter: đối tượng đại diện từng tham số

API **getParameters()** trả mảng **Parameter[]**, mỗi phần tử có:

- **getName()**: tên tham số đọc từ class file nếu có, hoặc tên tổng hợp như arg0, arg1.
- **isNamePresent()**: class file có chứa tên tham số trong metadata thích hợp hay không.
- **getType()**: Class<?> sau type erasure.
- **getParameterizedType()**: Type biểu diễn khai báo generic.
- **getAnnotations()**, **getAnnotation(...)**: annotation gắn trực tiếp lên khai báo tham số.
- **getAnnotatedType()**: AnnotatedType cho các annotation trên vị trí dùng kiểu.
- **isVarArgs()**: tham số có đại diện danh sách biến số đối số hay không.
- **isImplicit()** và **isSynthetic()**: tham số ngầm định trong source hoặc do compiler tạo.
- **getDeclaringExecutable()**: trở lại Method/Constructor khai báo tham số.

**Tên tham số không luôn được giữ trong file .class.** Với javac, hãy biên dịch cùng **-parameters** khi công cụ dựa vào tên như name, amount hoặc requestId. Không có tùy chọn đó, tên có thể trở thành arg0, arg1; không được coi các tên này là tên nguồn ổn định.

~~~bash
javac --release 17 -parameters -encoding UTF-8 ExecutableDemo.java
java ExecutableDemo
~~~

Mặc dù **-g** thêm một số thông tin debug, nó không thay thế mục đích của **-parameters** để các API Reflection về tên tham số có thể dùng đúng theo hợp đồng. Tên tham số của một số cấu trúc đặc biệt như record có thể được compiler lưu theo quy tắc riêng; đừng vì thế suy ra mọi method đều có tên.

### Erasure: Class<?> khác Type

Giả sử method có chữ ký:

~~~java
public <E extends Number> void submit(List<E> values, E limit) {}
~~~

Thông tin thông thường:

| Tham số | getParameterTypes() | getGenericParameterTypes() |
| --- | --- | --- |
| values | List.class | ParameterizedType biểu diễn List<E> |
| limit | Number.class | TypeVariable E |

Lệnh tìm method phải dùng kiểu tham số sau erasure:

~~~java
clazz.getDeclaredMethod("submit", java.util.List.class, Number.class);
~~~

clazz là biến kiểu Class<?> trong ví dụ. Không thể truyền một ParameterizedType biểu diễn List<E> vào **getDeclaredMethod**, bởi phương thức đó nhận **Class<?>...**.

**getTypeParameters()** của method submit có một TypeVariable tên E; điều này khác việc **getGenericParameterTypes()** trả E ở vị trí tham số. Với Constructor của generic class, getTypeParameters() chỉ mô tả type variable được khai báo **riêng ở constructor**, không tự bao gồm tất cả type variable của class.

## 4. Ví dụ Java 17+ đầy đủ: phân tích Method và Constructor qua Executable

Chương trình sau minh họa một hàm **inspect(Executable)** xử lý đồng thời constructor và method, in thông tin tên/kiểu tham số, generic, throws, varargs, annotations và sau đó gọi từng thành phần bằng API riêng.

Lưu toàn bộ mã vào file **ExecutableDemo.java**:

~~~java
import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.List;

public class ExecutableDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface Label { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Marked {}

    public static class Service {
        private final List<String> names;

        public Service(@Label("ctor") @Marked List<String> names) throws IOException {
            this.names = names;
        }

        public <E extends Number> @Marked List<E> process(
                @Label("key") String key, @Marked List<E> values, int... limits)
                throws IOException {
            return values;
        }

        public int size() { return names.size(); }
    }

    private static void inspect(Executable executable) {
        System.out.println("kind=" + (executable instanceof Method ? "method" : "constructor"));
        System.out.println("owner=" + executable.getDeclaringClass().getSimpleName());
        System.out.println("count=" + executable.getParameterCount());
        System.out.println("varargs=" + executable.isVarArgs());
        Parameter[] parameters = executable.getParameters();
        for (int i = 0; i < parameters.length; i++) {
            Parameter parameter = parameters[i];
            System.out.println("p" + i + "=" + parameter.getName()
                    + ":" + parameter.getType().getSimpleName()
                    + ",namePresent=" + parameter.isNamePresent()
                    + ",generic=" + parameter.getParameterizedType().getTypeName());
        }
        System.out.println("throws=" + executable.getExceptionTypes()[0].getSimpleName());
        System.out.println("typeVariables=" + executable.getTypeParameters().length);
    }

    public static void main(String[] args) throws Exception {
        Constructor<Service> constructor = Service.class.getConstructor(List.class);
        Method method = Service.class.getMethod("process", String.class, List.class, int[].class);

        inspect(constructor);
        inspect(method);

        System.out.println("constructor label="
                + constructor.getParameters()[0].getAnnotation(Label.class).value());
        System.out.println("method p1 type annotation="
                + method.getAnnotatedParameterTypes()[1].isAnnotationPresent(Marked.class));
        System.out.println("method return type annotation="
                + method.getAnnotatedReturnType().isAnnotationPresent(Marked.class));
        System.out.println("method type variable=" + method.getTypeParameters()[0].getName());
        System.out.println("return=" + method.getReturnType().getSimpleName());

        Service service = constructor.newInstance(List.of("A", "B"));
        Object result = method.invoke(service, "ok", List.of(3, 4), new int[] {1, 2});
        System.out.println("invoke=" + result);
        System.out.println("service size=" + service.size());
    }
}
~~~

Biên dịch/chạy (JDK 17 trở lên):

~~~bash
javac --release 17 -parameters -encoding UTF-8 ExecutableDemo.java
java ExecutableDemo
~~~

Stdout đã được kiểm tra trên JDK 21 sau khi biên dịch với **--release 17 -parameters**:

~~~text
kind=constructor
owner=Service
count=1
varargs=false
p0=names:List,namePresent=true,generic=java.util.List<java.lang.String>
throws=IOException
typeVariables=0
kind=method
owner=Service
count=3
varargs=true
p0=key:String,namePresent=true,generic=java.lang.String
p1=values:List,namePresent=true,generic=java.util.List<E>
p2=limits:int[],namePresent=true,generic=int[]
throws=IOException
typeVariables=1
constructor label=ctor
method p1 type annotation=true
method return type annotation=true
method type variable=E
return=List
invoke=[3, 4]
service size=2
~~~

### Phân tích kết quả

1. **Cùng một hàm inspect** nhận cả Constructor<Service> và Method qua **Executable**. Đoạn chương trình chỉ cần phân biệt method/constructor để in kind; các API còn lại trong inspect đều nằm ở phần chung.
2. Constructor khai báo một tham số List<String> nên **count=1**, kiểu erased là List nhưng generic giữ được **java.util.List<java.lang.String>**. Không có type variable khai báo riêng, nên **typeVariables=0**.
3. Method process có ba tham số: String, List<E> và int...; erasure của List<E> thành List. Varargs **int...** có kiểu tham số runtime **int[]**, vì vậy **varargs=true** nhưng getParameterTypes() của tham số cuối là mảng.
4. Type variable E extends Number được khai báo trên chính method, do đó **typeVariables=1** và tên là **E**.
5. **@Label** là annotation ở vị trí PARAMETER, đọc bằng Parameter.getAnnotation(Label.class). **@Marked** là TYPE_USE annotation, đọc qua AnnotatedType của tham số hoặc kiểu trả về. Hai nhóm annotation có nguồn thông tin khác nhau.
6. getExceptionTypes() thấy **IOException** vì cả constructor và method đều khai báo throws IOException. Nó mô tả chữ ký khai báo; không khẳng định mỗi lần gọi sẽ ném IOException.
7. Việc khởi tạo dùng **Constructor.newInstance**; gọi method dùng **Method.invoke**. Kết quả trả về từ Method.invoke là Object và được in như một List gồm 3, 4.

### Thử bỏ -parameters

Biên dịch lại trong thư mục riêng hoặc xóa class cũ và chạy:

~~~bash
javac --release 17 -encoding UTF-8 ExecutableDemo.java
java ExecutableDemo
~~~

Khi không có metadata tham số được giữ bởi -parameters, phần tên trong output thường đổi thành **arg0**, **arg1**, **arg2**, và **isNamePresent()** thành false, ví dụ:

~~~text
p0=arg0:List,namePresent=false,generic=java.util.List<java.lang.String>
~~~

Thông tin generic như List<String> và type variable E **không phụ thuộc vào -parameters giống tên biến**: nó đến từ thông tin generic signature của class file. Hãy phân biệt rõ các loại metadata để chẩn đoán.

## 5. Declaration annotations và type-use annotations

Một annotation gắn **trực tiếp lên khai báo tham số** khác một annotation gắn lên **kiểu** được sử dụng tại vị trí tham số.

Ví dụ mã ngắn (không phải chương trình độc lập):

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Input {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Checked {}

void save(@Input @Checked List<String> values) {}
~~~

Trong một đoạn mã thực tế cần import java.lang.annotation.* và java.util.List.

- **getParameterAnnotations()** trả mảng hai chiều: mỗi vị trí tương ứng tập các annotation khai báo của một tham số.
- **getParameters()[i].getAnnotations()** cũng cho các declaration annotations trên Parameter đó.
- **getAnnotatedParameterTypes()[i].getAnnotations()** cho các annotation TYPE_USE ở vị trí kiểu tham số tương ứng.
- **getAnnotatedReturnType()** dùng cho type-use annotation tại kiểu trả về; với Method, có thể đọc cùng **getReturnType()** hoặc **getGenericReturnType()** tùy mục tiêu.
- **getAnnotatedExceptionTypes()** mô tả type-use annotation của các exception trong throws.
- **getAnnotatedReceiverType()** mô tả receiver type ở nơi hợp lệ (chẳng hạn receiver parameter được khai báo tường minh); có thể trả null nếu không có receiver thích hợp.

Không ép mọi annotation vào cùng một loại. Một validation framework muốn biết annotation trên tham số nên đọc cả loại **declaration** lẫn loại **type-use** tùy meta-annotation @Target của chúng.

**Chú ý:** mảng annotation không được đảm bảo phản ánh tất cả thông tin source nếu annotation không có RetentionPolicy.RUNTIME. Các annotation SOURCE/CLASS có thể không hiển thị theo các API phản chiếu runtime như các annotation RUNTIME.

## 6. Implicit, synthetic parameters và sự khác nhau giữa các mảng

Một executable không chỉ có các tham số hiển thị tường minh trong source. Compiler có thể đưa thêm **implicit** hoặc **synthetic** parameters. Hai trường hợp dễ gặp:

- Constructor của **non-static inner class** thường có thêm tham số tham chiếu tới enclosing instance ở vị trí đầu.
- Constructor liên quan một số cấu trúc compiler như enum có thể xuất hiện những tham số được bổ sung ngoài danh sách người lập trình viết.

Ví dụ:

~~~java
class Outer {
    class Inner {
        Inner(int number) {}
    }
}
~~~

Đối với kiểu inner không static, constructor trong bytecode cần nhận một instance của Outer. Khi Reflection tra constructor, trong trường hợp javac thông thường sẽ phải dùng:

~~~java
Outer outer = new Outer();
Constructor<Outer.Inner> c =
        Outer.Inner.class.getDeclaredConstructor(Outer.class, int.class);
Outer.Inner instance = c.newInstance(outer, 10);
~~~

Đây là fragment cần import java.lang.reflect.Constructor và đặt trong method xử lý checked exceptions. Với **static nested class**, không có outer instance bổ sung theo cơ chế này.

**Quan trọng khi xử lý metadata:**

- **getParameterCount()** tính cả tham số implicit/synthetic hiện diện ở runtime.
- **getParameterTypes()** cho các kiểu thực tế dùng trong descriptor, cần thiết cho lookup.
- **getParameters()** cho Parameter và các cờ **isImplicit()/isSynthetic()** khi metadata cho phép diễn giải.
- **getGenericParameterTypes()** có thể trả danh sách có số lượng khác trong một số tình huống có implicit/synthetic parameters và generic signature; chính tài liệu API cảnh báo điều này.
- Các mảng annotation cũng có thể phản ánh tham số bổ sung theo quy tắc riêng; đừng máy móc ghép mảng từ hai API khác nhau bằng index mà không kiểm tra quan hệ và độ dài.

Khi làm thư viện mapping tham số, phải kiểm thử trên class thực tế và trên compiler/JDK mục tiêu. Nếu cần xem descriptor ở bytecode, có thể dùng **javap -v** với file .class để xem MethodParameters, Signature và RuntimeVisibleParameterAnnotations/RuntimeVisibleTypeAnnotations.

## 7. isVarArgs() và cách truyền đối số thực tế

Với method:

~~~java
void log(String label, int... numbers) {}
~~~

Compiler biến kiểu tham số cuối thành mảng int[]. Một Method tìm được theo:

~~~java
Method method = clazz.getDeclaredMethod("log", String.class, int[].class);
~~~

là hợp lệ nếu clazz mô tả class khai báo log.

**isVarArgs()** chỉ cho biết phương thức được **khai báo bằng cú pháp biến số đối số**. Nó không có nghĩa Reflection tự luôn thực hiện overload resolution hay tự gom các số thành mảng như cú pháp gọi Java ở source:

~~~java
method.invoke(receiver, "sum", new int[] {1, 2, 3});
~~~

Trong đó receiver là instance thích hợp; tham số thứ ba được truyền như một đối số mảng. Nếu method chỉ nhận một tham số kiểu String[] và cần truyền mảng làm **một phần tử** của varargs Object... của Method.invoke, ép rõ sang Object:

~~~java
method.invoke(receiver, (Object) new String[] {"a", "b"});
~~~

Dòng sau chỉ đúng khi method nhận **một String[]**, khác với method log(String,int...) phía trên. Cast (Object) đặc biệt có ích để tránh Java tự trải mảng tham chiếu String[] thành các phần tử varargs ở **chính lệnh Method.invoke**.

Tương tự, **Constructor.newInstance(Object... args)** cũng nhận mảng arguments theo runtime signature, chứ không chạy bộ chọn overload như javac. Không dùng isVarArgs() để giả định mọi lệnh gọi reflective sẽ tự chuyển số phần tử tùy ý thành một mảng.

## 8. Quyền truy cập qua AccessibleObject và JPMS

Method và Constructor kế thừa khả năng yêu cầu bỏ qua một số kiểm tra Java language access từ AccessibleObject:

~~~java
if (executable.trySetAccessible()) {
    // Caller có thể yêu cầu tắt kiểm tra access trong giới hạn cho phép.
}
~~~

Đây là fragment giả định đã có biến Executable.

Trên Java Platform Module System (JPMS), private member của class thuộc một named module khác có thể nằm trong package **không mở cho module đang thực hiện Reflection**. Lệnh **setAccessible(true)** có thể ném **InaccessibleObjectException**, còn **trySetAccessible()** có thể trả false. Package được **exports** cho public API không tự cho phép deep reflection vào private method/constructor; thông thường cần **opens** phù hợp.

Nếu mục đích chỉ là đọc metadata, nhiều API như getDeclaredMethods/getDeclaredConstructors/getParameters vẫn sử dụng được dù sau đó không có quyền invoke non-public member. Vì vậy:

1. Phân tích metadata với Executable trước.
2. Chỉ yêu cầu deep reflective access khi thực sự cần invoke/newInstance.
3. Kiểm tra module/package và caller chính xác nếu bị chặn.
4. Không dùng setAccessible để vượt quyền đối với thành viên nội bộ khi API công khai đã đáp ứng yêu cầu.

Việc **setAccessible(true) thành công** cũng không làm thay đổi chữ ký Method/Constructor, generic return types, số tham số hoặc annotation. Đây là thay đổi kiểm tra quyền truy cập khi dùng Reflection, không phải sửa class file.

## 9. Dùng Executable để viết scanner chung an toàn

Một scanner dùng cho cả Method và Constructor có thể nhận danh sách Executable rồi in những trường chung:

~~~java
static void describe(Executable e) {
    System.out.println("member: " + e.getName());
    for (Parameter p : e.getParameters()) {
        System.out.println(p.getType().getTypeName()
                + " " + p.getName()
                + " (namePresent=" + p.isNamePresent() + ")");
    }
}
~~~

Đây là một method fragment cần import java.lang.reflect.Executable và java.lang.reflect.Parameter. Có thể gọi với Method hoặc Constructor. Khi quét toàn class, có thể lấy:

~~~java
for (Method m : type.getDeclaredMethods()) {
    describe(m);
}
for (Constructor<?> c : type.getDeclaredConstructors()) {
    describe(c);
}
~~~

Biến type là Class<?> đã xác định; hai lệnh getDeclared... không duyệt superclass theo cùng cách getMethods(), và constructor **không được kế thừa**.

Khi nâng cấp scanner cho framework thực tế:

- Kiểm tra **Modifier** cùng **getDeclaringClass()**; không dựa vào thứ tự của getDeclaredMethods()/getDeclaredConstructors().
- Kiểm tra **Method.isBridge()** (chỉ Method có) và **Executable.isSynthetic()** để giảm trường hợp compiler-generated members khi xuất tài liệu source API.
- Dùng **isNamePresent()** trước khi lấy tên tham số làm tên property/JSON key/argument binding.
- Phân biệt **getParameterTypes()** khi cần descriptor runtime với **getGenericParameterTypes()** khi cần phân tích T, List<T> hoặc wildcard.
- Phân biệt **declaration annotation** và **type-use annotation**.
- Khi có implicit/synthetic parameters, kiểm tra độ dài và metadata trước khi ghép nhiều mảng theo index.
- Dùng subtype-specific API để xử lý **kiểu trả về của Method** hoặc **khởi tạo của Constructor**.

Một framework không nên mặc định lấy tên tham số, annotation và generic type làm toàn bộ hợp đồng xác thực: nhiều dữ liệu có thể thiếu vì cách build, retention, obfuscation hoặc compiler. Hãy có đường fallback và thông báo lỗi rõ ràng.

## 10. Lỗi phổ biến và câu hỏi tự kiểm tra

### Lỗi thường gặp

1. **Cố gọi executable.invoke(...)**: Executable không khai báo invoke/newInstance chung. Phân biệt Method và Constructor bằng instanceof, rồi dùng đúng API.
2. **Cho rằng generic Type luôn là Class<?>**: với List<String>, Type có thể là ParameterizedType; với T có thể là TypeVariable. Không ép kiểu bừa.
3. **Lấy getParameters()[i].getName() làm tên source chắc chắn**: thiếu -parameters thường sinh arg0/arg1, isNamePresent() là false.
4. **Nhầm isVarArgs với tự gom arguments**: reflective invocation cần đối số đúng descriptor; last parameter là array.
5. **Nhầm annotation trên tham số và annotation trên kiểu**: getParameterAnnotations() và getAnnotatedParameterTypes() phục vụ mục đích khác nhau.
6. **Giả định tham số runtime luôn bằng số tham số viết trong source**: implicit/synthetic parameters có thể thay đổi parameter count và mô hình generic metadata.
7. **Tin rằng getExceptionTypes() liệt kê mọi exception có thể xảy ra khi gọi**: nó chỉ phản ánh throws declaration, còn runtime exception/error vẫn có thể phát sinh.
8. **Gọi setAccessible(true) để sửa metadata**: API chỉ thay đổi khả năng bỏ qua một số kiểm tra access; JPMS vẫn bảo vệ các package chưa opens phù hợp.
9. **Bỏ qua bridge/synthetic methods** khi duyệt toàn class; method do compiler tạo có thể làm kết quả scanner khác với source.
10. **Dựa vào thứ tự array getDeclaredMethods() hoặc getDeclaredConstructors()**: không có thứ tự ổn định theo source được bảo đảm.

### Tự kiểm tra

**Câu 1.** Biến Executable e đang trỏ tới Constructor<?>. Có thể gọi e.getParameters() không? Có thể gọi e.newInstance() trực tiếp không?

**Đáp án:** getParameters() được vì thuộc API Executable; newInstance() không phải API chung nên cần cast/kiểm tra Constructor<?>.

**Câu 2.** Method nhận List<String> và int... . Những kiểu nào dùng khi getDeclaredMethod?

**Đáp án:** List.class và int[].class, theo thứ tự. Với varargs, tham số cuối có runtime type là mảng.

**Câu 3.** Một Parameter có name là arg1 và isNamePresent() trả false. Có nên dùng arg1 làm tên dữ liệu API cố định không?

**Đáp án:** Không. Đây thường là tên tự sinh do thiếu metadata. Dùng -parameters hoặc cấu hình ánh xạ tên rõ ràng.

**Câu 4.** Khi đọc một parameter vừa có @Label khai báo vừa có @Marked TYPE_USE, nên dùng API gì?

**Đáp án:** Parameter.getAnnotation(Label.class) cho declaration annotation và getAnnotatedType()/getAnnotatedParameterTypes() cho type-use annotation.

**Câu 5.** Method có generic type parameter E extends Number; getParameterTypes() cho tham số kiểu E trả gì, và getGenericParameterTypes() trả gì?

**Đáp án:** Thường là Number.class và TypeVariable E; type erasure được dùng để lookup, còn generic metadata phục vụ phân tích khai báo.

**Câu 6.** Constructor của non-static inner class có thể có thêm tham số gì?

**Đáp án:** Tham số enclosing instance của outer class, thường ở đầu descriptor runtime. Dùng đúng Class<?> khi tra cứu và kiểm tra Parameter flags nếu metadata có.

**Ghi nhớ:** **Executable là API metadata chung cho Method và Constructor**. Dùng nó để phân tích tham số, generic, annotations, exceptions, varargs và modifiers; khi cần thực thi phải dùng **Method.invoke** hoặc **Constructor.newInstance**. Khi phụ thuộc vào tên tham số, build với **-parameters** và xác nhận **isNamePresent()**.

### Tài liệu tham khảo

- Java SE 17 — Executable: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html
- Java SE 17 — Parameter: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html
- Java SE 17 — Method: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 17 — Constructor<T>: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html
- Java SE 17 — AccessibleObject: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Oracle Java Tutorials — Obtaining Names of Method Parameters: https://docs.oracle.com/javase/tutorial/reflect/member/methodparameterreflection.html
