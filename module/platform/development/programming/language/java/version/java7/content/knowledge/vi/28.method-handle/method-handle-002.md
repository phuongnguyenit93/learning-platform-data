# MethodType: mô tả chữ ký tham số và kiểu kết quả của MethodHandle

## 1. MethodType là gì?

Trong Java, **java.lang.invoke.MethodType** biểu diễn **kiểu của một lời gọi phương thức**: một **kiểu trả về** và một **danh sách có thứ tự các kiểu tham số**. Một **MethodHandle** có đúng một MethodType mô tả loại đối số mà nó nhận và kết quả mà nó tạo ra. JVM sử dụng thông tin này để kiểm tra tính tương thích của lời gọi, đặc biệt với **invokeExact**, **invoke** và cơ chế liên kết lời gọi động.

Ví dụ, phương thức Java:

~~~java
static int add(int left, int right) {
    return left + right;
}
~~~

có chữ ký kiểu:

~~~java
MethodType signature =
        MethodType.methodType(int.class, int.class, int.class);
System.out.println(signature); // (int,int)int
~~~

Hai đoạn trên chỉ để minh họa: ví dụ thứ hai cần import **java.lang.invoke.MethodType** và nằm trong thân một phương thức. Ý nghĩa biểu diễn **(int,int)int** là nhận **hai int**, trả về **một int**. **Kiểu kết quả được đặt trước** trong lời gọi factory **methodType(returnType, parameterTypes...)**, còn biểu diễn chuỗi đặt kiểu trả về **sau dấu ngoặc**.

**MethodType không chứa mã thực thi**, không lưu tên phương thức, tên tham số, annotation, visibility hoặc thông tin throws. Nó là một **type descriptor**, không phải đối tượng phản chiếu đầy đủ về phương thức. Để gọi code, cần **MethodHandle** hoặc cơ chế liên kết phù hợp; tự tạo MethodType không tự tìm hay tạo phương thức.

### Phân biệt những đối tượng dễ nhầm

| Đối tượng | Nó đại diện cho điều gì? |
| --- | --- |
| **java.lang.invoke.MethodType** | Các **Class** của tham số theo thứ tự và **Class** của kiểu kết quả |
| **java.lang.invoke.MethodHandle** | Lời gọi/operation có thể thực thi; **handle.type()** cho biết MethodType thực tế |
| **java.lang.reflect.Method** | Metadata về một phương thức khai báo trong lớp, gồm tên, modifier, kiểu tham số/trả về, annotations... |
| **java.lang.Class<?>** | Một kiểu Java đơn lẻ; không đủ để mô tả toàn bộ danh sách tham số và kết quả |
| **Chuỗi descriptor của JVM** | Dạng ký hiệu mã hóa một MethodType, ví dụ **(II)I** |

Ví dụ **(String,int)boolean** và **(int,String)boolean** khác nhau vì **thứ tự tham số là một phần của chữ ký**. **(int)int** và **(int)long** cũng khác nhau: MethodType luôn xét kiểu kết quả. Trong mã nguồn Java, không thể khai báo hai overload chỉ khác kiểu trả về, nhưng descriptor ở cấp JVM và MethodType vẫn bao gồm kiểu trả về.

## 2. Tạo MethodType với methodType(...)

Phương thức factory phổ biến là **MethodType.methodType(Class<?> returnType, Class<?>... parameterTypes)**; các overload khác cho phép truyền danh sách **List<Class<?>>**, mảng Class hoặc sao chép các tham số từ MethodType khác.

~~~java
import java.lang.invoke.MethodType;

MethodType noArgs = MethodType.methodType(void.class);
// ()void

MethodType oneArg = MethodType.methodType(String.class, int.class);
// (int)String

MethodType twoArgs = MethodType.methodType(boolean.class,
        String.class, long.class);
// (String,long)boolean

MethodType arrayArg = MethodType.methodType(int.class, String[].class);
// (String[])int

MethodType sameParametersDifferentReturn =
        MethodType.methodType(Object.class, twoArgs);
// (String,long)Object
~~~

Đây là các **đoạn minh họa đặt trong phương thức**, không phải chương trình độc lập. Chuỗi comment mô tả **toString()** của MethodType tương ứng.

Quy tắc khi khai báo kiểu:

- **Kiểu trả về** có thể là primitive (**int.class**, **boolean.class**), reference (**String.class**, **List.class**) hoặc **void.class** cho phương thức không trả giá trị.
- **Kiểu tham số không được là void.class**. Không thể có đối số mang kiểu void. Nếu cần không có tham số, truyền **chỉ returnType**, ví dụ **methodType(void.class)**.
- **null** không phải đối tượng Class hợp lệ cho kiểu trả về hay tham số; factory sẽ từ chối dữ liệu không hợp lệ.
- **int.class** khác **Integer.class**; **String[].class** khác **String.class**; **void.class** khác **Void.class**. Đây là những kiểu thực sự khác nhau khi kiểm tra chữ ký.
- **Generic type arguments** không xuất hiện trong Class runtime theo cách mô tả này: **List<String>** được thể hiện bởi **List.class**. MethodType lưu kiểu đã xóa, không lưu **String** của tham số generic.
- Danh sách tham số có thứ tự, có thể rỗng; chỉ số truy cập tham số bắt đầu từ **0**.

Ví dụ **MethodType.methodType(int.class, void.class)** gây **IllegalArgumentException** vì void là kiểu tham số không hợp lệ. Giới hạn số slot tham số ở cấp JVM cũng áp dụng; tham số **long/double** dùng hai slot, khác với các kiểu còn lại thường dùng một slot. Một MethodType quá lớn sẽ bị từ chối. Trong ứng dụng thực tế không nên thiết kế lời gọi có hàng trăm tham số; gom dữ liệu vào object phù hợp khi có thể.

## 3. Đọc chữ ký: tham số và kiểu kết quả

Các API chính:

| API | Ý nghĩa |
| --- | --- |
| **returnType()** | Trả về **Class<?>** biểu diễn kiểu kết quả |
| **parameterCount()** | Số tham số, **không** phải số slot JVM |
| **parameterType(index)** | Kiểu tham số tại vị trí **index** (bắt đầu 0) |
| **parameterArray()** | Mảng Class của các tham số |
| **parameterList()** | Danh sách Class của các tham số |
| **lastParameterType()** | Kiểu của tham số cuối, nếu có |
| **toString()** | Dạng dễ đọc như **(int,String)boolean** |
| **toMethodDescriptorString()** | Descriptor dạng JVM như **(ILjava/lang/String;)Z** |

~~~java
MethodType type = MethodType.methodType(
        String.class, int.class, boolean.class);

System.out.println(type);                       // (int,boolean)String
System.out.println(type.returnType());          // class java.lang.String
System.out.println(type.parameterCount());      // 2
System.out.println(type.parameterType(0));      // int
System.out.println(type.parameterType(1));      // boolean
System.out.println(type.toMethodDescriptorString());
// (IZ)Ljava/lang/String;
~~~

Đoạn trên cần import **MethodType** và chạy bên trong một phương thức. **parameterType(2)** sẽ vượt phạm vi vì chỉ có index **0** và **1**, dẫn tới **IndexOutOfBoundsException**. Tránh gọi **lastParameterType()** khi danh sách tham số rỗng nếu chưa kiểm tra; phương thức này trả về **void.class** khi không có tham số (đây là ký hiệu sentinel, không có nghĩa tham số void hợp lệ).

**toString()** là định dạng để đọc và debug; **toMethodDescriptorString()** dùng quy ước JVM. Các ký hiệu descriptor thường gặp: **I=int**, **J=long**, **Z=boolean**, **V=void**, **[** cho mảng, và **Lpackage/Class;** cho reference. Chẳng hạn:

- **(int,int)int** ↔ **(II)I**
- **()void** ↔ **()V**
- **(String)boolean** ↔ **(Ljava/lang/String;)Z**
- **(String[],int)long** ↔ **([Ljava/lang/String;I)J**

Có thể dựng MethodType từ một chuỗi descriptor hợp lệ bằng **MethodType.fromMethodDescriptorString(descriptor, classLoader)**; các kiểu reference cần được class loader nhìn thấy. **toMethodDescriptorString** không phải một cách kiểm tra tính hợp lệ tuyệt đối của mọi descriptor trong mọi class loader: hai lớp cùng tên nhưng đến từ class loader khác nhau có thể là hai Class khác nhau.

### Equality và tính bất biến

MethodType **immutable**. Các thao tác biến đổi chữ ký tạo hoặc tìm một MethodType khác, không sửa chữ ký gốc. **equals(...)** so sánh cấu trúc kiểu trả về và tham số theo đúng Class tương ứng; không so sánh theo tên phương thức. Cùng tên class được nạp bởi các class loader khác nhau vẫn có thể là **Class khác nhau**.

~~~java
MethodType first = MethodType.methodType(int.class, int.class);
MethodType second = MethodType.methodType(int.class, int.class);
MethodType changed = first.changeReturnType(long.class);

System.out.println(first.equals(second));  // true
System.out.println(first);                 // (int)int
System.out.println(changed);               // (int)long
~~~

Không cần dựa vào so sánh **first == second** để xác định hai chữ ký có cùng ý nghĩa. Factory có thể tái sử dụng instance; hãy dùng **equals(...)** khi kiểm tra nội dung.

## 4. MethodType gắn với MethodHandle như thế nào?

Tạo MethodType là bước **mô tả** chữ ký. Một lời gọi **MethodHandles.Lookup.findStatic** hoặc **findVirtual** dùng chữ ký để tìm thành viên; **MethodHandle.type()** trả lại chữ ký thực tế của handle đã tạo.

### Static method: chữ ký handle giống chữ ký phương thức

~~~java
MethodType maxType = MethodType.methodType(
        int.class, int.class, int.class);
MethodHandle max = MethodHandles.lookup()
        .findStatic(Math.class, "max", maxType);

System.out.println(max.type());  // (int,int)int
int value = (int) max.invokeExact(3, 8);
System.out.println(value);       // 8
~~~

Đoạn minh họa cần import **MethodType**, **MethodHandle**, **MethodHandles**, đặt trong phương thức khai báo **throws Throwable** (hoặc xử lý ngoại lệ). Java có overload **Math.max** cho nhiều kiểu, nên chữ ký **(int,int)int** giúp tìm đúng overload. Nếu yêu cầu sai kiểu, **findStatic** có thể ném **NoSuchMethodException**; nếu không có quyền truy cập, nó có thể ném **IllegalAccessException**.

### Instance method: handle có thêm receiver ở vị trí đầu

Phương thức **String.substring(int, int)** nhận hai tham số int và trả String. Khi **Lookup.findVirtual** tìm phương thức, MethodType truyền vào là **(int,int)String**, tức chữ ký của thành viên **không có receiver**. Nhưng MethodHandle nhận được có chữ ký **(String,int,int)String** vì receiver của lời gọi instance trở thành **tham số đầu tiên**.

~~~java
MethodType memberType = MethodType.methodType(
        String.class, int.class, int.class);

MethodHandle substring = MethodHandles.lookup()
        .findVirtual(String.class, "substring", memberType);

System.out.println(substring.type());
// (String,int,int)String

String part = (String) substring.invokeExact("MethodType", 0, 6);
System.out.println(part); // Method
~~~

Nếu gọi **substring.bindTo("MethodType")**, receiver được gắn sẵn và chữ ký handle giảm thành **(int,int)String**. Kết quả của **substring.type()** luôn mô tả **đối số thực tế mà chính handle đó nhận**, nên rất hữu ích khi chuẩn bị **invokeExact** hoặc biến đổi handle.

### Constructor: chữ ký tìm kiếm khác chữ ký handle kết quả

Với **Lookup.findConstructor(StringBuilder.class, MethodType.methodType(void.class, String.class))**, kiểu tra cứu của constructor là **(String)void** theo quy ước JVM đối với **<init>**. Handle được trả về lại có kiểu **(String)StringBuilder**, vì khi gọi nó sẽ tạo và trả object. Đây là hành vi đặc biệt có chủ đích của constructor lookup; không coi tất cả handle đều giữ nguyên returnType được truyền vào lookup.

### Chữ ký không thay thế kiểm tra quyền truy cập

**MethodType** tự nó không cấp quyền gọi thành viên private hoặc protected. **Lookup** mang ngữ cảnh kiểm tra quyền truy cập; một chữ ký khớp vẫn có thể không lấy được MethodHandle nếu thành viên không thể truy cập. Tránh dùng reflection hoặc lookup đặc biệt để vượt quyền module/package; khi thiết kế API hãy công khai điểm truy cập thích hợp.

## 5. invokeExact: chữ ký của call site phải khớp hoàn toàn

**MethodHandle.invokeExact(...)** là phương thức **signature-polymorphic**: JVM biết chữ ký từ **kiểu tĩnh của các đối số** và **kiểu kết quả được yêu cầu tại vị trí gọi**. Cả danh sách tham số lẫn kiểu trả về phải khớp **handle.type()**.

~~~java
MethodHandle max = MethodHandles.lookup().findStatic(
        Math.class, "max",
        MethodType.methodType(int.class, int.class, int.class));

int correct = (int) max.invokeExact(3, 8); // OK: (int,int)int

// Dòng sau CÓ THỂ BIÊN DỊCH nhưng thất bại tại runtime:
// long wrong = (long) max.invokeExact(3, 8);
// Call-site yêu cầu (int,int)long, khác kết quả int của handle.
~~~

Đoạn trên giả định import thích hợp và phương thức khai báo **throws Throwable**. Ngay cả khi hai tham số đều là int, **đọc kết quả như long** khiến chữ ký trở thành **(int,int)long** và có thể ném **WrongMethodTypeException**. Tương tự:

- **Integer a = (Integer) max.invokeExact(3, 8)** không khớp vì kết quả của handle là **int**, không phải **Integer**.
- **int a = (int) max.invokeExact(3L, 8L)** không khớp vì tham số là **long**, không phải **int**.
- Lời gọi **max.invokeExact(3, 8)** như một statement bỏ qua kết quả có call-site return type **void**, cũng không khớp với handle trả int.
- Dùng cast ngoài lời gọi đúng cách: **(int) max.invokeExact(3, 8)** mô tả kiểu kết quả mà call-site yêu cầu.

Khi thiết kế API động, **luôn kiểm tra handle.type()** thay vì đoán chữ ký từ tên phương thức. Nếu chỉ cần gọi trực tiếp một method đã biết tại compile time, cú pháp gọi thông thường thường đơn giản hơn; MethodHandle hữu ích khi xây dựng dispatcher, adapter, runtime linkage hoặc thư viện framework.

## 6. invoke, asType và biến đổi chữ ký cho phù hợp

**invoke(...)** có thể chấp nhận lời gọi không exact bằng cơ chế adaptation tương đương **asType(...)** nếu conversion hợp lệ. Không phải mọi chuyển đổi giữa primitive, wrapper, reference hay arity đều được phép. Nếu không thể tạo sự tương thích, có thể gặp **WrongMethodTypeException**; khi conversion cast tại runtime thất bại, có thể gặp **ClassCastException**. Unboxing null có thể gây **NullPointerException**.

### asType: thay đổi cách handle chấp nhận/giao kết quả

~~~java
MethodType ints = MethodType.methodType(
        int.class, int.class, int.class);
MethodHandle max = MethodHandles.lookup()
        .findStatic(Math.class, "max", ints);

MethodType boxedType = MethodType.methodType(
        Integer.class, Integer.class, Integer.class);
MethodHandle boxedMax = max.asType(boxedType);

System.out.println(max.type());      // (int,int)int
System.out.println(boxedMax.type()); // (Integer,Integer)Integer

Integer result = (Integer) boxedMax.invokeExact(
        Integer.valueOf(4), Integer.valueOf(9));
System.out.println(result);          // 9
~~~

Đây là ví dụ minh họa đặt trong phương thức **throws Throwable**. **asType** tạo một **adapter handle**: đối số Integer sẽ được unbox sang int và kết quả int được box thành Integer. **max** gốc vẫn giữ chữ ký cũ. Khi gặp null ở vị trí cần unbox, adapter không thể tự biến nó thành int có giá trị hợp lệ.

### Thay đổi số tham số cần combinator, không chỉ sửa MethodType

**asType** không tùy tiện thêm/bớt số lượng tham số. Nếu muốn một handle có thêm đối số được bỏ qua, có thể dùng **MethodHandles.dropArguments**:

~~~java
MethodHandle taggedMax =
        MethodHandles.dropArguments(max, 0, String.class);
// taggedMax.type() = (String,int,int)int

int biggest = (int) taggedMax.invokeExact("tag", 3, 8);
// biggest = 8
~~~

Ở đây **max** là handle **(int,int)int** đã có từ đoạn trước. **dropArguments** tạo adapter có thêm tham số String ở đầu nhưng không chuyển String cho Math.max. Đối với argument được gắn sẵn, có **bindTo** hoặc **MethodHandles.insertArguments**; khi cần gom/trải mảng có các adapter tương ứng như **asCollector** và **asSpreader**. Những adapter này biến đổi **handle thực sự**, khác việc chỉ tạo ra một MethodType mới.

## 7. Biến đổi MethodType mà không sửa phương thức/handle

MethodType là immutable; các phương thức sau chỉ thao tác trên **bản mô tả chữ ký**:

| API | Biến đổi |
| --- | --- |
| **changeReturnType(newType)** | Thay kiểu kết quả |
| **changeParameterType(index, newType)** | Thay một kiểu tham số |
| **insertParameterTypes(position, types...)** | Chèn tham số ở vị trí zero-based |
| **appendParameterTypes(types...)** | Nối tham số vào cuối |
| **dropParameterTypes(start, end)** | Bỏ tham số ở khoảng **[start, end)** |
| **wrap()** | Biến primitive thành wrapper, **void → Void** |
| **unwrap()** | Biến wrapper thành primitive, **Void → void** trong vị trí return |
| **erase()** | Thay reference type bằng Object, giữ primitive/void |
| **generic()** | Thay mọi kiểu tham số và kết quả thành Object |
| **genericMethodType(count)** | Tạo chữ ký count tham số Object, kết quả Object |

~~~java
MethodType original = MethodType.methodType(
        int.class, int.class, long.class);
// (int,long)int

MethodType changedReturn = original.changeReturnType(void.class);
// (int,long)void

MethodType changedArg = original.changeParameterType(1, double.class);
// (int,double)int

MethodType inserted = original.insertParameterTypes(0, String.class);
// (String,int,long)int

MethodType appended = original.appendParameterTypes(boolean.class);
// (int,long,boolean)int

MethodType dropped = original.dropParameterTypes(0, 1);
// (long)int

MethodType boxed = original.wrap();
// (Integer,Long)Integer

MethodType generic = original.generic();
// (Object,Object)Object

System.out.println(original); // (int,long)int: không đổi
~~~

Mỗi khai báo trên là **một MethodType mới về mặt ngữ nghĩa**, không tác động đến phương thức thật hay một MethodHandle đã tồn tại. Chỉ số **changeParameterType** và **dropParameterTypes** là **0-based**, và giới hạn cuối của drop là **exclusive**. Nếu type mới có tham số **void** hoặc sai phạm vi, API sẽ báo lỗi; không thể chỉ đổi MethodType rồi dùng **invokeExact** trên handle cũ với chữ ký mới.

**Lưu ý về generic():** nó chuyển mọi kiểu thành **Object**, kể cả primitive được boxing trong mô tả type; không có nghĩa Java thực hiện bất kỳ adapter nào chỉ vì tạo ra MethodType mới.

## 8. Chương trình Java 17+ chạy được: các chữ ký và kết quả thực tế

Tệp **MethodTypeSignatureDemo.java** dùng hoàn toàn API chuẩn của JDK, không cần thư viện bên ngoài.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodTypeSignatureDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodType signature = MethodType.methodType(
                int.class, int.class, int.class);
        MethodHandle maximum = lookup.findStatic(
                Math.class, "max", signature);

        System.out.println("type=" + maximum.type());
        System.out.println("count=" + signature.parameterCount());
        System.out.println("parameter[0]="
                + signature.parameterType(0).getSimpleName());
        System.out.println("return="
                + signature.returnType().getSimpleName());
        System.out.println("descriptor="
                + signature.toMethodDescriptorString());

        int maxResult = (int) maximum.invokeExact(3, 8);
        System.out.println("max=" + maxResult);

        MethodType substringMember = MethodType.methodType(
                String.class, int.class, int.class);
        MethodHandle substring = lookup.findVirtual(
                String.class, "substring", substringMember);

        System.out.println("virtual=" + substring.type());
        String part = (String) substring.invokeExact(
                "MethodType", 0, 6);
        System.out.println("part=" + part);

        MethodHandle bound = substring.bindTo("MethodType");
        System.out.println("bound=" + bound.type());
        String boundPart = (String) bound.invokeExact(6, 10);
        System.out.println("boundPart=" + boundPart);

        MethodType boxedType = MethodType.methodType(
                Integer.class, Integer.class, Integer.class);
        MethodHandle boxed = maximum.asType(boxedType);
        Integer boxedMax = (Integer) boxed.invokeExact(
                Integer.valueOf(4), Integer.valueOf(9));
        System.out.println("boxed=" + boxed.type());
        System.out.println("boxedMax=" + boxedMax);

        MethodHandle extended =
                MethodHandles.dropArguments(maximum, 0, String.class);
        int extendedMax = (int) extended.invokeExact("tag", 3, 8);
        System.out.println("extended=" + extended.type());
        System.out.println("extendedMax=" + extendedMax);

        MethodHandle constructor = lookup.findConstructor(
                StringBuilder.class,
                MethodType.methodType(void.class, String.class));
        StringBuilder created =
                (StringBuilder) constructor.invokeExact("ok");
        System.out.println("constructor=" + constructor.type());
        System.out.println("constructed=" + created);

        try {
            long wrong = (long) maximum.invokeExact(3, 8);
            System.out.println(wrong); // Không tới đây nếu không khớp chữ ký.
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrongType=WrongMethodTypeException");
        }
    }
}
~~~

Chạy trên **JDK 17+**:

~~~bash
javac MethodTypeSignatureDemo.java
java MethodTypeSignatureDemo
~~~

Kết quả dự kiến:

~~~text
type=(int,int)int
count=2
parameter[0]=int
return=int
descriptor=(II)I
max=8
virtual=(String,int,int)String
part=Method
bound=(int,int)String
boundPart=Type
boxed=(Integer,Integer)Integer
boxedMax=9
extended=(String,int,int)int
extendedMax=8
constructor=(String)StringBuilder
constructed=ok
wrongType=WrongMethodTypeException
~~~

Giải thích từng nhóm kết quả:

1. **type/count/parameter/return/descriptor** cho thấy MethodType mô tả chính xác danh sách tham số có thứ tự và kiểu kết quả của **Math.max(int,int)**.
2. **findVirtual** tạo handle có receiver **String** ở tham số đầu; **bindTo** gắn receiver vào handle nên còn hai tham số int.
3. **asType** thích nghi **(int,int)int** sang **(Integer,Integer)Integer** bằng boxing/unboxing theo các conversion được phép.
4. **dropArguments** cho phép thêm đối số **tag** ở bên ngoài nhưng giữ nguyên phép tính Math.max.
5. **findConstructor** nhận type tra cứu **(String)void** và trả handle **(String)StringBuilder**.
6. **invokeExact** với kiểu kết quả **long** thay vì **int** gây **WrongMethodTypeException**, cho thấy return type là một phần bắt buộc của call-site signature.

Chương trình không dùng reflection sâu, quyền truy cập đặc biệt hoặc API đã lỗi thời. **main throws Throwable** vì **MethodHandle.invokeExact** có thể truyền nguyên ngoại lệ từ mục tiêu; với ứng dụng thực, cần có chính sách xử lý ngoại lệ thay vì ném thẳng khỏi main.

## 9. Các lỗi hay gặp và cách khắc phục

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách giải quyết |
| --- | --- | --- |
| Tạo **methodType(int.class, int.class)** rồi nghĩ có hai tham số | Đối số Class đầu tiên là **returnType** | Đọc factory theo thứ tự **return, params...** |
| Dùng **methodType(void.class, void.class)** | void hợp lệ cho kết quả, không hợp lệ cho tham số | Dùng **methodType(void.class)** cho không tham số |
| Bỏ qua kiểu kết quả khi **invokeExact** | JVM kiểm tra cả return type của call-site | Cast/đọc kết quả với đúng kiểu hoặc dùng adapter phù hợp |
| Dùng **Integer.class** thay **int.class** mà không adapt | Primitive khác wrapper ở MethodType | Chọn exact type hoặc **asType** cho conversion được phép |
| Dùng type đã đổi bằng **changeReturnType** để gọi handle cũ | Đổi descriptor không đổi handle | Tạo adapter MethodHandle hoặc lấy lại handle phù hợp |
| Gọi instance handle thiếu receiver | **findVirtual** trả handle có receiver ở đầu | Truyền receiver hoặc dùng **bindTo** |
| Thêm receiver vào type truyền **findVirtual** | Lookup type của member không chứa receiver | Cung cấp chữ ký member; đọc **handle.type()** sau lookup |
| Giả định constructor handle trả **void** | Chỉ type tra cứu <init> trả void, handle trả object | Đọc **constructorHandle.type()** |
| Nhầm chỉ số tham số với chỉ số tham số SQL/JDBC | MethodType dùng chỉ số **0-based** | Truy cập **parameterType(0)** cho tham số đầu |
| Dùng **invoke** và tưởng mọi conversion đều hợp lệ | asType chỉ hỗ trợ tập conversion nhất định | Kiểm tra **WrongMethodTypeException**, ClassCastException và conversion rules |
| Nhầm **List<String>** và **List<Integer>** là MethodType khác nhau | Type erasure khiến cả hai là **List.class** | Đặt kiểm tra generic riêng, không dựa vào MethodType |
| Coi **toString()** là bytecode descriptor | toString dạng dễ đọc, không phải cú pháp JVM | Dùng **toMethodDescriptorString()** khi cần descriptor |
| So sánh type theo tên class thay vì Class identity | Class loader khác nhau có thể tạo Class khác nhau | Dùng MethodType.equals và bảo đảm class loader đúng |
| **NoSuchMethodException** bị coi là WrongMethodTypeException | Lỗi tra cứu khác với lỗi gọi handle | Kiểm tra member name, return/params, quyền truy cập tại bước lookup |

### Cách tự kiểm tra trước khi gọi một MethodHandle

- **handle.type()** có trả đúng returnType, parameterCount và thứ tự parameterType như call-site mong muốn?
- Nếu handle được tạo từ **findVirtual**, đã tính tham số receiver ở vị trí đầu chưa?
- Với **invokeExact**, đối số primitive/wrapper và kiểu kết quả từ cast/bối cảnh biểu thức đã **khớp tuyệt đối** chưa?
- Nếu cần conversion, **asType** có hỗ trợ và xử lý được null/unboxing không?
- Nếu thêm/bớt đối số hoặc gắn sẵn receiver, đã **tạo adapter handle** chứ không chỉ sửa MethodType chưa?
- Đã phân biệt lỗi **lookup** (không tìm thấy/không truy cập) với lỗi **invocation** (chữ ký sai hoặc mục tiêu ném lỗi) chưa?

## 10. Tổng kết kiến thức cần giữ

- **MethodType** định nghĩa **kiểu trả về + danh sách Class tham số theo thứ tự**; đối số factory đầu tiên là return type.
- **MethodType** bất biến, hỗ trợ đọc và biến đổi mô tả type. Nó không tự chứa phương thức hay thay đổi một MethodHandle.
- **MethodHandle.type()** là nguồn đáng tin để biết chữ ký invocation thực tế. Với instance handle thường có **receiver đầu tiên**; constructor handle trả về instance mới.
- **invokeExact** yêu cầu **exact call-site signature**, bao gồm kiểu trả về; **invoke** và **asType** cho phép những chuyển đổi đã được API hỗ trợ.
- **String/array, primitive/wrapper, void/Void, thứ tự tham số, class loader** đều có thể làm hai chữ ký khác nhau.
- Dùng **toMethodDescriptorString()** để lấy descriptor JVM khi thật sự làm việc với bytecode hoặc runtime linkage. Với business code chỉ cần gọi method tĩnh thông thường, không nhất thiết dùng MethodHandle.

**Tài liệu chuẩn để tra cứu:**

- [Oracle Java SE 25 — MethodType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Oracle Java SE 25 — MethodHandle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Oracle Java SE 26 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
