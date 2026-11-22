# Access flag trong Java class file

Access flag là các bit trong cấu trúc class file dùng để mô tả thuộc tính của class, field hoặc method. JVM và các công cụ như javac, javap sử dụng các bit này để hiểu quyền truy cập, tính static/final, đặc điểm của interface, method đồng bộ, method bridge và một số thuộc tính do compiler sinh ra.

Trong class file, access flag được lưu dưới dạng một giá trị bitmask 16 bit (u2). Nhiều flag có thể được kết hợp bằng phép OR bit. Ý nghĩa của một bit phụ thuộc vào vị trí nó xuất hiện: access_flags của class, field_info hay method_info. Vì vậy, không thể đọc một giá trị hex mà bỏ qua cấu trúc đang chứa nó.

Ví dụ, bit 0x0020 có ý nghĩa ACC_SUPER trong class access_flags nhưng là ACC_SYNCHRONIZED trong method access_flags. Tương tự, 0x0040 là ACC_VOLATILE đối với field nhưng là ACC_BRIDGE đối với method.

## 1. Access flag nằm ở đâu trong class file?

Theo định dạng class file của JVM, có ba vị trí quan trọng chứa trường access_flags:

- **ClassFile.access_flags:** mô tả class hoặc interface.
- **field_info.access_flags:** mô tả field.
- **method_info.access_flags:** mô tả method hoặc constructor.

Mỗi vị trí có tập flag hợp lệ riêng. Một số bit có cùng giá trị số nhưng ý nghĩa khác nhau giữa các cấu trúc.

Ví dụ một class file có thể chứa:

~~~text
ClassFile
  access_flags
  this_class
  super_class
  interfaces
  fields
    field_info
      access_flags
      name_index
      descriptor_index
  methods
    method_info
      access_flags
      name_index
      descriptor_index
~~~

Các flag không phải là một chuỗi văn bản lưu trực tiếp trong file. Class file lưu bitmask; javap đọc bitmask và hiển thị tên tương ứng để con người dễ kiểm tra.

Một giá trị có thể gồm nhiều bit cùng bật. Ví dụ:

~~~text
0x0011 = 0x0001 | 0x0010
       = ACC_PUBLIC | ACC_FINAL
~~~

Do đó, khi đọc output của javap, hãy xem cả giá trị hex và danh sách tên flag.

## 2. Flag của class và interface

Các flag class thường gặp trong class file Java hiện đại:

| Flag | Giá trị hex | Ý nghĩa |
|---|---:|---|
| ACC_PUBLIC | 0x0001 | Class có thể được truy cập từ bên ngoài package theo quy tắc Java |
| ACC_FINAL | 0x0010 | Class không thể được subclass |
| ACC_SUPER | 0x0020 | Bật cách xử lý đặc biệt khi gọi superclass method bằng invokespecial |
| ACC_INTERFACE | 0x0200 | Khai báo này là interface |
| ACC_ABSTRACT | 0x0400 | Class/interface là abstract |
| ACC_SYNTHETIC | 0x1000 | Khai báo được compiler sinh ra hoặc không xuất hiện trực tiếp trong source |
| ACC_ANNOTATION | 0x2000 | Interface là annotation interface |
| ACC_ENUM | 0x4000 | Khai báo là enum |
| ACC_MODULE | 0x8000 | Class file là module descriptor module-info.class |

### ACC_PUBLIC

Ví dụ:

~~~java
public class PublicService {
}
~~~

Class có thể được truy cập từ code thuộc package khác, miễn là các quy tắc module và quyền truy cập liên quan cho phép.

Nếu class top-level không khai báo public, nó có package access: code ngoài package không thể truy cập trực tiếp class đó bằng tên kiểu thông thường.

### ACC_FINAL

Ví dụ:

~~~java
public final class ImmutableToken {
}
~~~

Class final không thể được mở rộng bằng extends. Đây là flag ở cấp class, khác với ACC_FINAL trên field (không thể gán lại sau khi khởi tạo) hoặc method (không thể override theo quy tắc Java).

Class vừa abstract vừa final là tổ hợp không hợp lệ vì class abstract cần khả năng được subclass để triển khai các phần abstract, trong khi final cấm subclass.

### ACC_SUPER

ACC_SUPER liên quan tới cách JVM xử lý invokespecial khi method gọi một implementation ở superclass. Đây là flag ở mức class file, không phải modifier mà lập trình viên thường viết trực tiếp trong Java source.

Các class file hiện đại do javac tạo thường có ACC_SUPER. Với class file version từ 51.0 trở lên, flag này được yêu cầu theo JVM Specification. Khi đọc output javap, thấy ACC_SUPER là bình thường và không có nghĩa class khai báo một modifier super trong source.

### ACC_INTERFACE và ACC_ABSTRACT

Một interface được đánh dấu ACC_INTERFACE. Interface cũng có ACC_ABSTRACT.

~~~java
public interface Repository {
    Object findById(long id);
}
~~~

Một abstract class được đánh dấu ACC_ABSTRACT:

~~~java
public abstract class BaseRepository {
    public abstract Object findById(long id);
}
~~~

Không phải mọi class abstract đều là interface. ACC_INTERFACE giúp JVM phân biệt hai loại khai báo.

### ACC_ANNOTATION

Annotation interface là một dạng interface đặc biệt:

~~~java
public @interface Audited {
}
~~~

Trong class file, annotation interface có ACC_ANNOTATION và ACC_INTERFACE. Annotation type được biểu diễn như một interface với cấu trúc metadata annotation tương ứng.

### ACC_ENUM

Enum class và enum constant field có flag ACC_ENUM ở những vị trí tương ứng trong class file.

~~~java
public enum Status {
    NEW,
    ACTIVE,
    CLOSED
}
~~~

Flag này giúp JVM và công cụ nhận diện khai báo enum. Enum còn có các quy tắc riêng về constructor, instance và constant-specific class body.

### ACC_MODULE

Module descriptor được biên dịch thành module-info.class và có ACC_MODULE. Đây không phải flag để đánh dấu một class Java thông thường.

~~~java
module com.example.orders {
    requires java.logging;
    exports com.example.orders.api;
}
~~~

Module descriptor chứa cấu trúc Module attribute và các metadata liên quan. Không đặt ACC_MODULE lên class thông thường.

## 3. Flag của field

Field access_flags mô tả visibility, cách lưu trữ và một số đặc điểm của field.

| Flag | Giá trị hex | Ý nghĩa |
|---|---:|---|
| ACC_PUBLIC | 0x0001 | Field public |
| ACC_PRIVATE | 0x0002 | Field private |
| ACC_PROTECTED | 0x0004 | Field protected |
| ACC_STATIC | 0x0008 | Field thuộc class thay vì từng object |
| ACC_FINAL | 0x0010 | Field chỉ được gán theo các quy tắc final |
| ACC_VOLATILE | 0x0040 | Truy cập field có semantics volatile về visibility và ordering giữa các thread |
| ACC_TRANSIENT | 0x0080 | Field bị loại khỏi cơ chế serialization mặc định của Java Object Serialization |
| ACC_SYNTHETIC | 0x1000 | Field do compiler sinh hoặc không có khai báo trực tiếp trong source |
| ACC_ENUM | 0x4000 | Field biểu diễn enum constant |

Ví dụ:

~~~java
public class FieldFlags {
    public static final int MAX_RETRIES = 3;
    private volatile boolean running;
    protected transient String cachedToken;
}
~~~

Các tổ hợp thường thấy:

- MAX_RETRIES: ACC_PUBLIC, ACC_STATIC, ACC_FINAL.
- running: ACC_PRIVATE, ACC_VOLATILE.
- cachedToken: ACC_PROTECTED, ACC_TRANSIENT.

ACC_VOLATILE và ACC_FINAL không thể kết hợp trên cùng một field theo quy tắc class file. Một field cũng không thể đồng thời là public, private và protected; chỉ một mức visibility được dùng.

### ACC_STATIC

Field static thuộc về class, không phải mỗi instance. Một field static final có thể được dùng cho hằng số compile-time nếu đáp ứng các điều kiện của Java Language Specification, nhưng không phải mọi field static final đều được inline thành constant trong bytecode của nơi sử dụng.

### ACC_FINAL

Field final chỉ được gán trong các vị trí được Java cho phép, chẳng hạn khai báo trực tiếp hoặc constructor/initializer phù hợp. Flag final không có nghĩa object được tham chiếu là immutable; nó chỉ ngăn gán lại biến field.

~~~java
private final List<String> names = new ArrayList<>();
~~~

Không thể gán một List khác cho names sau khi khởi tạo, nhưng vẫn có thể thêm phần tử vào List nếu không có quy tắc khác ngăn cản.

### ACC_VOLATILE

Field volatile dùng để thiết lập các quy tắc visibility và ordering giữa các thread. Khi một thread ghi volatile field và thread khác đọc cùng field, quan hệ happens-before được áp dụng theo Java Memory Model.

~~~java
private volatile boolean stopped;
~~~

volatile không làm cho mọi thao tác ghép như count++ trở thành atomic. Với bộ đếm tăng/giảm đồng thời, cần dùng synchronized, Lock hoặc các lớp atomic phù hợp.

### ACC_TRANSIENT

Field transient bị bỏ qua trong quá trình serialization mặc định của Java Object Serialization.

~~~java
private transient String sessionToken;
~~~

Flag này không tự mã hóa hoặc xóa giá trị khỏi bộ nhớ. Nó chỉ tác động tới cơ chế serialization mặc định; custom serialization như writeObject có thể áp dụng quy tắc khác.

### Field của interface

Field được khai báo trong interface có tính public static final theo Java Language Specification, dù source có viết các modifier đó hay không.

~~~java
interface Limits {
    int DEFAULT_TIMEOUT = 30;
}
~~~

Trong class file, field này có các flag tương ứng với public, static và final.

## 4. Flag của method và constructor

Method access_flags có tập flag riêng:

| Flag | Giá trị hex | Ý nghĩa |
|---|---:|---|
| ACC_PUBLIC | 0x0001 | Method public |
| ACC_PRIVATE | 0x0002 | Method private |
| ACC_PROTECTED | 0x0004 | Method protected |
| ACC_STATIC | 0x0008 | Method static |
| ACC_FINAL | 0x0010 | Method không thể override |
| ACC_SYNCHRONIZED | 0x0020 | JVM thực hiện monitor enter/exit theo semantics synchronized |
| ACC_BRIDGE | 0x0040 | Method bridge do compiler sinh |
| ACC_VARARGS | 0x0080 | Method dùng cú pháp tham số biến độ dài |
| ACC_NATIVE | 0x0100 | Method được triển khai bằng mã native |
| ACC_ABSTRACT | 0x0400 | Method không có implementation bytecode thông thường |
| ACC_STRICT | 0x0800 | Flag strict floating-point của class file cũ; bị bỏ qua từ version 61.0 |
| ACC_SYNTHETIC | 0x1000 | Method do compiler sinh hoặc không xuất hiện trực tiếp trong source |

### Visibility của method

Ví dụ:

~~~java
public void start() {
}

private void resetState() {
}

protected void validate() {
}
~~~

Nếu method không có public, private hoặc protected, nó có package access. Trong class file, không có flag visibility tương ứng được bật cho trường hợp package-private.

Visibility quyết định code nào có thể gọi method theo quy tắc Java và JVM. protected không đồng nghĩa public: ngoài package, quyền truy cập còn phụ thuộc quan hệ subclass và cách tham chiếu receiver.

### ACC_STATIC

Method static thuộc về class:

~~~java
public static int add(int left, int right) {
    return left + right;
}
~~~

Method static không có this và không override theo cơ chế dynamic dispatch như instance method. Method static cùng tên ở subclass là method hiding khi thỏa điều kiện, không phải override thông thường.

### ACC_FINAL

Method final không thể bị override bởi subclass:

~~~java
public final void closeSafely() {
    // cleanup
}
~~~

ACC_FINAL ở method khác với ACC_FINAL ở class và field; cùng tên flag nhưng phạm vi áp dụng khác nhau.

### ACC_SYNCHRONIZED

Method synchronized được JVM quản lý việc lấy và nhả monitor:

~~~java
public synchronized void increment() {
    count++;
}
~~~

Với instance method, monitor là object this. Với static synchronized method, monitor là đối tượng Class tương ứng. JVM đảm bảo monitor được nhả cả khi method kết thúc bình thường hoặc thoát do exception.

ACC_SYNCHRONIZED không phải flag của class. Giá trị bit 0x0020 ở class là ACC_SUPER, còn ở method là ACC_SYNCHRONIZED.

### ACC_ABSTRACT

Method abstract không có phần thân implementation trong class file theo cách thông thường:

~~~java
public abstract class Handler {
    public abstract void handle();
}
~~~

Method abstract không thể đồng thời có một số modifier như private, static, final, synchronized hoặc native vì các tổ hợp đó mâu thuẫn với semantics của method abstract.

### ACC_NATIVE

Method native được triển khai ngoài Java bytecode, thường thông qua JNI hoặc cơ chế native liên quan:

~~~java
public native int readNativeValue();
~~~

ACC_NATIVE cho JVM biết method không có Code attribute thông thường chứa bytecode Java. Việc liên kết tới native implementation là một vấn đề runtime riêng.

## 5. Bridge method, varargs và synthetic flag

Đây là nhóm flag thường khiến người đọc javap thấy method không được viết trực tiếp trong source.

### ACC_BRIDGE

Java generics được triển khai bằng type erasure. Trong một số trường hợp, compiler cần sinh bridge method để giữ đúng polymorphism sau khi kiểu generic bị xóa.

Ví dụ:

~~~java
interface Converter<T> {
    T convert(T value);
}

final class StringConverter implements Converter<String> {
    @Override
    public String convert(String value) {
        return value.trim();
    }
}
~~~

Sau type erasure, method trong Converter có descriptor tương ứng với Object convert(Object). StringConverter triển khai String convert(String), nên javac sinh thêm một bridge method Object convert(Object) để duy trì hợp đồng dispatch.

Khi chạy javap -v -p StringConverter, có thể thấy một method tương tự:

~~~text
public java.lang.Object convert(java.lang.Object);
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
~~~

Bridge method nhận Object, ép kiểu sang String, gọi method convert(String), rồi trả kết quả dưới dạng Object. Đây là chi tiết do compiler tạo ra; không cần tự viết bridge method trong Java source.

### ACC_VARARGS

Method khai báo tham số biến độ dài bằng dấu ba chấm:

~~~java
public void log(String... messages) {
}
~~~

Trong bytecode, tham số varargs được biểu diễn bằng array, nhưng method mang ACC_VARARGS để công cụ nhận diện khai báo varargs ở source.

Ví dụ signature:

~~~text
log(java.lang.String...);
  flags: (0x0081) ACC_PUBLIC, ACC_VARARGS
~~~

ACC_VARARGS không tạo ra một cơ chế gọi riêng trong JVM. Ở mức bytecode, tham số vẫn là một array.

### ACC_SYNTHETIC

Synthetic member là thành phần do compiler sinh hoặc không được biểu diễn như một khai báo thông thường trong source. Ví dụ có thể gồm bridge method, field hỗ trợ inner class ở một số compiler/version hoặc method truy cập tổng hợp.

Không phải mọi compiler đều sinh cùng một tập synthetic member cho cùng một source. Chi tiết phụ thuộc cấu trúc source, phiên bản compiler và cách tối ưu.

Khi viết công cụ phân tích bytecode, không nên giả định mọi member đều được viết trực tiếp bởi developer. Hãy xem ACC_SYNTHETIC và ACC_BRIDGE để quyết định cách hiển thị hoặc xử lý.

## 6. Bitmask và cách đọc giá trị hex

Access flags là bitmask. Mỗi flag tương ứng với một bit; nhiều flag được kết hợp bằng phép OR.

Ví dụ một class public final:

~~~text
ACC_PUBLIC = 0x0001
ACC_FINAL  = 0x0010
ACC_SUPER  = 0x0020

Tổng      = 0x0031
~~~

Một field private static final:

~~~text
ACC_PRIVATE = 0x0002
ACC_STATIC  = 0x0008
ACC_FINAL   = 0x0010

Tổng       = 0x001A
~~~

Một method public synchronized varargs:

~~~text
ACC_PUBLIC       = 0x0001
ACC_SYNCHRONIZED = 0x0020
ACC_VARARGS      = 0x0080

Tổng             = 0x00A1
~~~

Khi kiểm tra bit trong mã phân tích class file, dùng phép AND:

~~~java
boolean isPublic = (accessFlags & 0x0001) != 0;
boolean isFinal = (accessFlags & 0x0010) != 0;
~~~

Không so sánh toàn bộ giá trị bằng phép bằng nếu mục tiêu chỉ là kiểm tra một flag. Ví dụ một class public final có giá trị 0x0031; so sánh accessFlags == 0x0001 sẽ sai dù class có ACC_PUBLIC.

Để bỏ một bit trong biến bitmask có thể dùng phép AND với phần bù bit, nhưng chỉ nên làm khi đang thao tác trên dữ liệu mà chương trình có quyền thay đổi. Công cụ đọc class file thường chỉ cần kiểm tra và hiển thị.

## 7. Cùng một bit có thể mang nghĩa khác theo cấu trúc

Đây là quy tắc quan trọng khi đọc định dạng class file:

| Giá trị | Trong class access_flags | Trong field access_flags | Trong method access_flags |
|---:|---|---|---|
| 0x0001 | ACC_PUBLIC | ACC_PUBLIC | ACC_PUBLIC |
| 0x0002 | Không dùng cho class top-level | ACC_PRIVATE | ACC_PRIVATE |
| 0x0004 | Không dùng cho class top-level | ACC_PROTECTED | ACC_PROTECTED |
| 0x0008 | Không dùng cho class top-level | ACC_STATIC | ACC_STATIC |
| 0x0010 | ACC_FINAL | ACC_FINAL | ACC_FINAL |
| 0x0020 | ACC_SUPER | Không dùng | ACC_SYNCHRONIZED |
| 0x0040 | Không dùng | ACC_VOLATILE | ACC_BRIDGE |
| 0x0080 | Không dùng | ACC_TRANSIENT | ACC_VARARGS |
| 0x0100 | Không dùng | Không dùng | ACC_NATIVE |
| 0x0200 | ACC_INTERFACE | Không dùng | Không dùng |
| 0x0400 | ACC_ABSTRACT | Không dùng | ACC_ABSTRACT |
| 0x0800 | Không dùng | Không dùng | ACC_STRICT |
| 0x1000 | ACC_SYNTHETIC | ACC_SYNTHETIC | ACC_SYNTHETIC |
| 0x2000 | ACC_ANNOTATION | Không dùng | Không dùng |
| 0x4000 | ACC_ENUM | ACC_ENUM | Không dùng |
| 0x8000 | ACC_MODULE | Không dùng | Không dùng |

Bảng này giúp tránh lỗi phổ biến khi parser chỉ dùng một danh sách tên flag chung cho mọi loại member. Một công cụ class file cần biết đang đọc ClassFile, field_info hay method_info trước khi giải mã bit.

Một số tổ hợp flag còn bị JVM Specification cấm. Ví dụ field không thể đồng thời final và volatile; method abstract không thể đồng thời synchronized; class không thể vừa final vừa abstract. Nếu parser gặp tổ hợp bất hợp lệ, cần báo class file không hợp lệ thay vì gán ý nghĩa tùy ý.

## 8. Access flag của nested class và InnerClasses attribute

Một nested class có thể được khai báo private, protected hoặc static:

~~~java
public class Outer {
    private static class Hidden {
    }

    protected class Extension {
    }
}
~~~

Tuy nhiên, các modifier private/protected/static của nested class được ghi trong InnerClasses attribute của class file liên quan. Chúng không phải toàn bộ đều nằm trong ClassFile.access_flags của file Hidden.class hoặc Extension.class.

Vì vậy, khi chạy javap -v, có thể thấy phần class flags và một mục InnerClasses với flag riêng cho nested class. Đừng nhầm hai vị trí metadata này.

Đối với class top-level, Java chỉ cho phép public hoặc package access. private, protected và static không phải modifier hợp lệ cho top-level class.

## 9. Một số metadata không phải access flag

Không phải mọi đặc điểm của class đều được biểu diễn bằng access_flags.

- **Record:** được mô tả bằng Record attribute; không có ACC_RECORD trong tập class access flag tiêu chuẩn.
- **Sealed class:** thông tin permitted subclasses được ghi bằng PermittedSubclasses attribute.
- **Generic signature:** dùng Signature attribute.
- **Runtime annotations:** được ghi trong các annotation attribute tương ứng.
- **Source file name:** thường nằm trong SourceFile attribute.
- **Inner/nested class metadata:** có InnerClasses attribute.
- **Module descriptor:** dùng ACC_MODULE cùng Module attribute và các cấu trúc module liên quan.

Ví dụ record:

~~~java
public record UserId(long value) {
}
~~~

Khi xem class file của record, có thể thấy các flag như public, final và super, cùng Record attribute. Không nên tìm một flag tên ACC_RECORD trong bảng class access_flags.

Ví dụ sealed class:

~~~java
public sealed class Shape permits Circle, Rectangle {
}
~~~

Các lớp được phép kế thừa được mô tả bằng PermittedSubclasses attribute, không phải một access flag riêng.

## 10. Kiểm tra access flag bằng javap

JDK cung cấp javap để đọc cấu trúc class file.

Biên dịch:

~~~bash
javac --release 17 -d out AccessFlagsDemo.java
~~~

Xem khai báo và member, bao gồm private:

~~~bash
javap -p -classpath out AccessFlagsDemo
~~~

Xem thông tin chi tiết class file và access flag:

~~~bash
javap -v -p -classpath out AccessFlagsDemo
~~~

Các tùy chọn:

- **-p** hoặc **-private**: hiển thị tất cả class và member, kể cả private.
- **-v** hoặc **-verbose**: hiển thị constant pool, flags, attributes và thông tin bytecode chi tiết.
- **-c**: hiển thị bytecode của method.
- **-classpath**: chỉ định nơi tìm class file.

Ví dụ phần đầu output có thể tương tự:

~~~text
public final class AccessFlagsDemo
  flags: (0x0031) ACC_PUBLIC, ACC_FINAL, ACC_SUPER
~~~

Một field:

~~~text
private static final int LIMIT;
  flags: (0x001A) ACC_PRIVATE, ACC_STATIC, ACC_FINAL
~~~

Một method synchronized varargs:

~~~text
public synchronized java.lang.String join(java.lang.String...);
  flags: (0x00A1) ACC_PUBLIC, ACC_SYNCHRONIZED, ACC_VARARGS
~~~

Tên method, descriptor và offset trong output phụ thuộc source và compiler. Các giá trị trên tương ứng với ví dụ ở phần thực hành.

Để kiểm tra bridge method:

~~~bash
javap -v -p -classpath out StringConverter
~~~

Tìm method có ACC_BRIDGE và ACC_SYNTHETIC. Có thể dùng javap -c để đọc bytecode của bridge method và thấy thao tác cast trước khi gọi method có kiểu String.

## 11. Ví dụ thực hành hoàn chỉnh với Java 17+

Ví dụ dưới đây tạo một class public final, field private static final, method synchronized varargs và bridge method sinh ra từ generic interface.

Tạo tệp AccessFlagsDemo.java:

~~~java
interface Mapper<T> {
    T map(T value);
}

final class StringMapper implements Mapper<String> {
    @Override
    public String map(String value) {
        return value.trim();
    }
}

public final class AccessFlagsDemo {
    private static final int LIMIT = 3;

    public synchronized String join(String... values) {
        return String.join(",", values);
    }

    private static int clamp(int value) {
        return Math.min(value, LIMIT);
    }

    public static void main(String[] args) {
        StringMapper mapper = new StringMapper();
        AccessFlagsDemo demo = new AccessFlagsDemo();

        System.out.println(mapper.map("  java  "));
        System.out.println(demo.join("one", "two"));
        System.out.println(clamp(5));
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d out AccessFlagsDemo.java
~~~

Chạy:

~~~bash
java -cp out AccessFlagsDemo
~~~

Output:

~~~text
java
one,two
3
~~~

Xem flags của class và member:

~~~bash
javap -v -p -classpath out AccessFlagsDemo
~~~

Các flag đáng chú ý trong AccessFlagsDemo:

- Class: ACC_PUBLIC, ACC_FINAL, ACC_SUPER.
- LIMIT: ACC_PRIVATE, ACC_STATIC, ACC_FINAL.
- join: ACC_PUBLIC, ACC_SYNCHRONIZED, ACC_VARARGS.
- clamp: ACC_PRIVATE, ACC_STATIC.
- main: ACC_PUBLIC, ACC_STATIC.

Xem class StringMapper:

~~~bash
javap -v -p -classpath out StringMapper
~~~

Ngoài method map(String), compiler sinh bridge method map(Object) có ACC_BRIDGE và ACC_SYNTHETIC. Bridge đảm bảo lời gọi thông qua Mapper<String> vẫn đến đúng implementation sau type erasure.

Ví dụ này minh họa rằng source code không thể hiện hết mọi member trong class file. Để hiểu chính xác compiler đã tạo gì, hãy kiểm tra bytecode bằng javap.

## 12. Access flag, reflection và quyền truy cập runtime

Java Reflection cung cấp modifier dưới dạng số nguyên qua các phương thức như:

~~~java
Class<?> type = AccessFlagsDemo.class;
int classModifiers = type.getModifiers();

int methodModifiers =
        type.getDeclaredMethod("main", String[].class).getModifiers();
~~~

Có thể giải mã bằng lớp java.lang.reflect.Modifier:

~~~java
System.out.println(
        java.lang.reflect.Modifier.toString(classModifiers));
~~~

Đối với field, method và class, Reflection hiển thị modifier theo ngữ cảnh tương ứng. Một số flag nội bộ của class file như ACC_SUPER, ACC_BRIDGE hoặc ACC_SYNTHETIC không được thể hiện như modifier source thông thường trong Modifier.toString. Để xem metadata bridge/synthetic, dùng các API như Method.isBridge(), Method.isSynthetic(), Field.isSynthetic() và Class.isSynthetic().

Ví dụ:

~~~java
for (var method : StringMapper.class.getDeclaredMethods()) {
    System.out.println(
            method.getName()
                    + ", bridge=" + method.isBridge()
                    + ", synthetic=" + method.isSynthetic());
}
~~~

Output sẽ liệt kê method map và bridge method do compiler sinh. Thứ tự liệt kê method không được bảo đảm.

Access flag là một phần metadata của class file, còn quyền truy cập thực tế chịu ảnh hưởng của Java language access rules, JVM access checks, package, module, class loader và các cơ chế reflection. Không nên coi việc một bit public/private xuất hiện trong file là toàn bộ mô hình bảo mật của ứng dụng.

## 13. Lỗi thường gặp khi đọc access flag

**Dùng cùng một bảng bit cho class, field và method**

Bit 0x0020 có thể là ACC_SUPER hoặc ACC_SYNCHRONIZED tùy cấu trúc. Luôn giải mã theo đúng loại access_flags.

**Nhầm ACC_FINAL ở class với field hoặc method**

Class final không thể subclass; field final không thể gán lại ngoài vị trí được phép; method final không thể override. Cùng flag nhưng quy tắc áp dụng khác nhau.

**Cho rằng package-private là một flag riêng**

Package-private được biểu diễn bằng việc không bật public, private hoặc protected. Không có ACC_PACKAGE_PRIVATE.

**Cho rằng mọi method trong javap đều do developer viết**

Bridge và synthetic method có thể được compiler sinh ra. Kiểm tra ACC_BRIDGE và ACC_SYNTHETIC khi phân tích bytecode.

**Nhầm ACC_VARARGS với array type**

Varargs được biểu diễn bằng array trong descriptor; ACC_VARARGS đánh dấu semantics khai báo biến độ dài ở source.

**Nhầm record hoặc sealed là access flag**

Record và sealed class dùng attribute riêng để lưu metadata. Không có ACC_RECORD hoặc ACC_SEALED trong bảng access_flags tiêu chuẩn của class.

**Đọc flag của nested class ở sai vị trí**

Modifier của nested class được mô tả trong InnerClasses attribute. ClassFile.access_flags của nested class không chứa mọi modifier của khai báo nested.

**Coi ACC_SUPER là modifier source**

ACC_SUPER là flag phục vụ semantics invokespecial và thường xuất hiện ở class file hiện đại. Java source không có modifier super để thêm vào class declaration.

## 14. Nguyên tắc khi phân tích class file

1. Xác định đang đọc access_flags của ClassFile, field_info hay method_info.
2. Đọc giá trị hex và giải mã từng bit theo đúng bảng tương ứng.
3. Kiểm tra các tổ hợp flag có hợp lệ theo JVM Specification không.
4. Dùng javap -v -p để đối chiếu metadata và member.
5. Phân biệt flag được viết từ source với flag do compiler sinh.
6. Kiểm tra InnerClasses hoặc attribute khác khi cần hiểu nested class, record, sealed class và module.
7. Không coi access flag là toàn bộ cơ chế bảo mật hoặc runtime access check.
8. Khi viết parser, giữ nguyên bit chưa biết nếu muốn hỗ trợ forward compatibility và không diễn giải flag không được định nghĩa cho cấu trúc hiện tại.

Access flag là lớp metadata nhỏ nhưng quan trọng trong định dạng class file. Khi hiểu bitmask và ý nghĩa theo từng cấu trúc, có thể đọc output javap, phân tích compiler-generated member và xây dựng công cụ xử lý bytecode chính xác hơn.
