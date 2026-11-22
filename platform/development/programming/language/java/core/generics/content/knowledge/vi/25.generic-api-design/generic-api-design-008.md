# Ảnh hưởng của đổi giới hạn và thứ tự giới hạn đến tương thích nhị phân trong Java Generics

## 1. Vấn đề: thay một chữ ký generic có thể phá client đã biên dịch

Xét một generic method công khai:

~~~java
public static <T extends java.io.Serializable
        & Comparable<T>> T echo(T value) {
    return value;
}
~~~

Một thư viện có thể muốn “dọn đẹp” chữ ký bằng cách đổi thứ tự giới hạn:

~~~java
public static <T extends Comparable<T>
        & java.io.Serializable> T echo(T value) {
    return value;
}
~~~

Hai chữ ký trên đều chấp nhận `String` vì String thỏa cả `Serializable` và `Comparable<String>`. Ở Java source, chúng trông gần như tương đương về tập kiểu được phép. Nhưng **thứ tự bounds ảnh hưởng đến type erasure**: kiểu đầu tiên trong danh sách bounds xác định erasure của type variable.

- Bản cũ: erasure(T) là `java.io.Serializable`.
- Bản mới: erasure(T) là `java.lang.Comparable`.
- JVM liên kết method dựa trên **tên + bytecode descriptor**, không dựa trên một ý tưởng trừu tượng “hai generic bounds là cùng tập giao”.
- Vì T vừa là tham số vừa là giá trị trả về, **cả parameter descriptor và return descriptor đều đổi**.
- Một client đã compile với method cũ có thể tìm đúng descriptor cũ khi chạy, nhưng class thư viện mới không còn method đó: lỗi `NoSuchMethodError`.

Đây là một **binary compatibility break** (*phá tương thích nhị phân*), ngay cả khi client source có thể biên dịch lại với bản thư viện mới và chạy bình thường.

Chủ đề này tập trung vào kỹ năng **thiết kế và tiến hóa generic API**:
1. Erasure của type variable phụ thuộc bounds nào?
2. Thứ tự bounds có ảnh hưởng tới bytecode descriptor và JVM linkage không?
3. Thay bound mà giữ bound đầu tiên có khác gì thay bound đầu tiên?
4. Binary compatibility khác source compatibility và behavioral compatibility ra sao?
5. Cách kiểm tra bằng `javac`, `javap`, Reflection và phép chạy client cũ với thư viện mới.
6. Cách thiết kế, version, kiểm thử API generic công khai để tránh vô tình phá người dùng.

## 2. Ba lớp tương thích cần phân biệt

Khi nói “đổi generic signature vẫn tương thích”, phải hỏi rõ loại nào:

| Loại tương thích | Câu hỏi đúng | Ví dụ kiểm tra |
| --- | --- | --- |
| **Source compatibility** | Code Java cũ có thể **biên dịch lại** với API mới không? | Biên dịch lại `Client.java` sau khi nâng phiên bản dependency. |
| **Binary compatibility** | Bytecode client **đã biên dịch** có thể liên kết/chạy với binary thư viện mới không? | Giữ nguyên `Client.class` cũ; thay riêng `Api.class`. |
| **Behavioral compatibility** | Sau khi chạy được, API có còn hành vi/ngữ nghĩa mong đợi không? | Kiểm tra exception, side effects, kết quả, contract. |

Một đổi thứ tự bounds có thể:

- **Vẫn source-compatible** đối với một lời gọi cụ thể, ví dụ dùng String.
- **Không binary-compatible** nếu method descriptor bị đổi và thư viện không duy trì descriptor cũ.
- **Thay đổi hành vi** nếu implementation mới thực hiện cast hoặc gọi method khác theo giới hạn mới, dù descriptor vẫn giữ.

Trong tình huống nâng thư viện, các ứng dụng lớn thường có module đã compile ở những thời điểm khác nhau. Chính vì vậy **“source của tôi compile được” không đủ chứng minh “binary cũ vẫn chạy”**.

### 2.1. Vì sao JVM không dựa trên Generic Signature để liên kết method?

Compiler Java tạo **descriptor** cho field và method bằng các JVM types sau erasure. Class file còn có thể lưu **Signature attribute** mang type parameters và actual generic types để phục vụ các công cụ và compiler sau này.

Hai thứ có vai trò khác nhau:

~~~text
Method descriptor:
    (Ljava/io/Serializable;)Ljava/io/Serializable;

Generic Signature:
    mô tả <T extends Serializable & Comparable<T>> T echo(T)
~~~

Descriptor là thông tin quan trọng cho JVM method resolution. Generic Signature là metadata bổ sung; nó không tạo một JVM method riêng cho mỗi type argument. JVM không có hai runtime classes `List<String>` và `List<Integer>` chỉ vì generics ở source.

Vì thế thay metadata generic **có thể** chỉ làm thay đổi source/reflection contracts nếu descriptor giữ nguyên; nhưng đổi erasure thành kiểu khác thì thường **đổi descriptor**, tạo nguy cơ mất liên kết với client cũ.

## 3. Quy tắc erasure của type variable

Java Generics dùng **type erasure**. Đối với type variable có upper bounds, erasure gắn với **leftmost bound**, tức giới hạn đầu tiên, sau khi áp dụng các quy tắc erasure liên quan.

Ví dụ:

| Khai báo type parameter | Erasure của T |
| --- | --- |
| `<T>` | `Object` |
| `<T extends Number>` | `Number` |
| `<T extends java.io.Serializable>` | `Serializable` |
| `<T extends java.io.Serializable & Comparable<T>>` | `Serializable` |
| `<T extends Comparable<T> & java.io.Serializable>` | `Comparable` |
| `<T extends Number & java.io.Serializable & Comparable<T>>` | `Number` |
| `<T extends Number & Comparable<T> & java.io.Serializable>` | `Number` |

**Cực kỳ quan trọng:** Java yêu cầu nếu có **class bound** như Number, nó phải đứng **đầu** trước các interface bounds. Bạn không thể hoán đổi Number xuống sau một interface rồi vẫn giữ cú pháp hợp lệ.

~~~java
// Hợp lệ: class trước, sau đó các interfaces.
<T extends Number & java.io.Serializable & Comparable<T>>

// Không hợp lệ về ngôn ngữ:
// <T extends java.io.Serializable & Number & Comparable<T>>
// Class Number không được đứng sau interface bound.
~~~

Nếu không có class bound tường minh, các giới hạn là interface bounds, và **interface đứng đầu quyết định erasure**.

### 3.1. Intersection type không phải “một JVM class giao”

`T extends Serializable & Comparable<T>` nghĩa là T phải thỏa cả hai interface trong type checking ở compile time.

Nó không tạo ra một runtime class đặc biệt `SerializableAndComparable`. JVM dùng erased type đầu tiên trong descriptors; khi code cần gọi method từ một secondary bound, compiler có thể chèn các `checkcast` phù hợp.

Do đó câu “cả hai interface đều được yêu cầu nên thứ tự không quan trọng” **sai đối với erasure và tương thích nhị phân**.

### 3.2. Bounds cũng quyết định thành viên nào được phép sử dụng

~~~java
static <T extends java.io.Serializable & Comparable<T>>
int compare(T a, T b) {
    return a.compareTo(b);
}
~~~

Compiler chấp nhận `compareTo` vì `Comparable<T>` xuất hiện trong bounds, dù không phải bound đầu tiên.

Nếu **bỏ Comparable<T>** khỏi tập giới hạn, body không còn được bảo đảm có `compareTo`. Nếu chỉ **đổi thứ tự** các bounds nhưng giữ cả hai, về mặt tập các member được phép từ những interfaces này, những khả năng source-level tương ứng nhìn chung vẫn có; tuy nhiên erasure và bytecode signatures có thể đổi.

## 4. Tham số và giá trị trả về T bị xóa thành gì?

Ví dụ:

~~~java
class Library {
    static <T extends Number> T identity(T value) {
        return value;
    }
}
~~~

Ở source:

~~~text
<T extends Number> T identity(T value)
~~~

Sau erasure, JVM descriptor tương ứng:

~~~text
(Ljava/lang/Number;)Ljava/lang/Number;
~~~

Với:

~~~java
static <T extends java.io.Serializable & Comparable<T>>
T echo(T value) {
    return value;
}
~~~

JVM descriptor:

~~~text
(Ljava/io/Serializable;)Ljava/io/Serializable;
~~~

Sau khi đảo interface đầu tiên:

~~~java
static <T extends Comparable<T> & java.io.Serializable>
T echo(T value) {
    return value;
}
~~~

JVM descriptor đổi thành:

~~~text
(Ljava/lang/Comparable;)Ljava/lang/Comparable;
~~~

**Descriptor chứa cả tham số lẫn kiểu trả về**. Với field có kiểu type variable, field descriptor cũng dựa trên erasure của variable tương ứng.

Đừng cho rằng thay bounds chỉ đổi thông tin “mang tính documentation”. Trong ví dụ trên, nó đã thay **binary identity** của phương thức đối với việc liên kết mã đã compile.

## 5. Thực nghiệm 1: giữ cùng hai bounds nhưng đảo vị trí

### 5.1. API cũ

Tạo thư mục chứa source file `api/Api.java`:

~~~java
package api;

public class Api {
    public static <T extends java.io.Serializable & Comparable<T>>
    T echo(T value) {
        return value;
    }
}
~~~

Với Java 17, `javap -s -p api.Api` sau khi compile sẽ cho descriptor của `echo` chứa:

~~~text
descriptor: (Ljava/io/Serializable;)Ljava/io/Serializable;
~~~

### 5.2. Client biên dịch với API cũ

Tệp `Client.java`:

~~~java
import api.Api;

public class Client {
    public static void main(String[] args) {
        System.out.println("result=" + Api.echo("ok"));
    }
}
~~~

`String` thực hiện cả Serializable lẫn Comparable<String>, vì vậy lời gọi hợp lệ.

Ví dụ lệnh dùng **Bash** từ thư mục có `api/Api.java` và `Client.java`:

~~~bash
mkdir -p out/api out/client
javac --release 17 -d out/api api/Api.java
javac --release 17 -cp out/api -d out/client Client.java
java -cp out/client:out/api Client
~~~

Stdout:

~~~text
result=ok
~~~

Trên Windows, dấu phân tách classpath là `;` thay vì `:`:

~~~text
java -cp "out/client;out/api" Client
~~~

**Cần giữ nguyên file `out/client/Client.class`** cho bước sau. Không compile lại Client khi thay thư viện.

### 5.3. API mới: chỉ đổi thứ tự bounds

Thay nội dung `api/Api.java` thành:

~~~java
package api;

public class Api {
    public static <T extends Comparable<T> & java.io.Serializable>
    T echo(T value) {
        return value;
    }
}
~~~

Hai type bounds vẫn giống nhau, chỉ vị trí đổi. Biên dịch lại **riêng thư viện**:

~~~bash
javac --release 17 -d out/api api/Api.java
javap -classpath out/api -p -s api.Api
~~~

Descriptor mới:

~~~text
descriptor: (Ljava/lang/Comparable;)Ljava/lang/Comparable;
~~~

Chạy **Client.class cũ**:

~~~bash
java -cp out/client:out/api Client
~~~

Kết quả là chương trình thất bại với lỗi liên kết:

~~~text
java.lang.NoSuchMethodError:
'java.io.Serializable api.Api.echo(java.io.Serializable)'
~~~

Dòng thực tế có thể có prefix `Exception in thread "main"` và stack trace, vị trí file/line tùy môi trường. Bài này chỉ trích phần chẩn đoán chính, không giả vờ các dòng stack trace luôn giống nhau.

**Nguyên nhân**: Client.class được compile để gọi descriptor cũ nhận/trả Serializable. Class Api mới chỉ còn descriptor nhận/trả Comparable. JVM không nhận ra một method có descriptor cũ, dù source client vẫn viết `Api.echo("ok")` và có thể compile lại được.

### 5.4. Biên dịch lại client khác hoàn toàn giữ binary cũ

Nếu biên dịch lại Client.java với Api mới:

~~~bash
javac --release 17 -cp out/api -d out/client Client.java
java -cp out/client:out/api Client
~~~

Output lại là:

~~~text
result=ok
~~~

Vì compiler mới tạo lời gọi đến descriptor Comparable mới. Điều này chứng minh:
- Client **source** cụ thể có thể vẫn hợp lệ.
- Client **binary** cũ không tương thích với bản Api mới.
- Việc “clean build” toàn bộ project đôi khi che một breaking change vẫn gây lỗi ở plugin, module hoặc thư viện đã phát hành mà người dùng không recompile.

Đây không chỉ là giả định: khi thử bằng JDK thực tế, biên dịch v1/v2 thành công, chạy client cũ với v1 in `result=ok`, thay riêng Api.class v2 gây `NoSuchMethodError` đúng như mô tả.

## 6. Thực nghiệm 2: đổi thứ tự **secondary bounds** nhưng giữ bound đầu tiên

Giả sử class bound đứng đầu:

~~~java
static <T extends Number
        & java.io.Serializable
        & Comparable<T>> T echo(T value) {
    return value;
}
~~~

Nếu chỉ đảo hai interfaces đứng sau Number:

~~~java
static <T extends Number
        & Comparable<T>
        & java.io.Serializable> T echo(T value) {
    return value;
}
~~~

Hai chữ ký này đều có **erasure(T) = Number**, vì leftmost bound vẫn là Number.

Vì vậy descriptor của method `echo(T) : T` ở cả hai trường hợp vẫn là:

~~~text
(Ljava/lang/Number;)Ljava/lang/Number;
~~~

**Kết luận giới hạn:** chỉ đảo secondary bounds và không làm đổi erasure **không tự làm đổi descriptor của method đơn giản này**. Client đã compile có thể vẫn liên kết được nếu method còn nguyên descriptor và các điều kiện binary linkage khác được giữ.

Tuy vậy, thay đổi vẫn quan sát được qua:
- Generic `Signature` metadata.
- Thứ tự `TypeVariable.getBounds()` của Java Reflection.
- Công cụ tạo schema, API documentation hoặc framework có logic phụ thuộc metadata/order.
- Source contract ở các thay đổi khác liên quan secondary bounds, đặc biệt thêm/xóa bound thay vì chỉ đảo.

Không kết luận “vì descriptor giống nhau nên chắc chắn mọi hành vi đều giống nhau”. Hãy kiểm tra implementation, các members kế thừa, code generation và những thành phần dựa vào generic metadata.

### 6.1. Vì sao bound Number phải đứng đầu?

Java bắt buộc nếu một type variable có bound là class và interface, class xuất hiện trước:

~~~java
// Hợp lệ:
<T extends Number & java.io.Serializable & Comparable<T>>

// Không hợp lệ:
// <T extends java.io.Serializable & Number & Comparable<T>>
~~~

Điều này giới hạn những cách sắp xếp hợp lệ. Khi type parameter có class bound, **đổi thứ tự các interface ở phía sau** thường giữ class erasure; nhưng khi **đổi chính class bound**, erasure vẫn có thể thay đổi.

Nếu chỉ có interface bounds, như `Serializable & Comparable<T>`, đảo interfaces có thể **đổi erasure ngay lập tức**.

## 7. Chương trình Java 17+ đọc erasure và bounds bằng Reflection

Lưu thành **BoundOrderDemo.java**:

~~~java
import java.io.Serializable;
import java.lang.reflect.Method;
import java.lang.reflect.Type;
import java.util.Arrays;

public class BoundOrderDemo {
    static class SerializableFirst {
        static <T extends Serializable & Comparable<T>>
        T echo(T value) {
            return value;
        }
    }

    static class ComparableFirst {
        static <T extends Comparable<T> & Serializable>
        T echo(T value) {
            return value;
        }
    }

    static class NumberFirstA {
        static <T extends Number & Serializable & Comparable<T>>
        T echo(T value) {
            return value;
        }
    }

    static class NumberFirstB {
        static <T extends Number & Comparable<T> & Serializable>
        T echo(T value) {
            return value;
        }
    }

    private static String bounds(Method method) {
        return Arrays.stream(
                method.getTypeParameters()[0].getBounds()
        ).map(Type::getTypeName)
         .reduce((a, b) -> a + " | " + b)
         .orElse("");
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Method s = SerializableFirst.class
                .getDeclaredMethod("echo", Serializable.class);

        Method c = ComparableFirst.class
                .getDeclaredMethod("echo", Comparable.class);

        Method n1 = NumberFirstA.class
                .getDeclaredMethod("echo", Number.class);

        Method n2 = NumberFirstB.class
                .getDeclaredMethod("echo", Number.class);

        System.out.println(
                "firstA=" + s.getParameterTypes()[0].getTypeName()
        );
        System.out.println(
                "firstB=" + c.getParameterTypes()[0].getTypeName()
        );
        System.out.println(
                "returnA=" + s.getReturnType().getTypeName()
        );
        System.out.println(
                "returnB=" + c.getReturnType().getTypeName()
        );

        System.out.println("boundsA=" + bounds(s));
        System.out.println("boundsB=" + bounds(c));

        System.out.println(
                "stableA=" + n1.getParameterTypes()[0].getTypeName()
        );
        System.out.println(
                "stableB=" + n2.getParameterTypes()[0].getTypeName()
        );
        System.out.println("stableBoundsA=" + bounds(n1));
        System.out.println("stableBoundsB=" + bounds(n2));

        System.out.println(
                "values=" + SerializableFirst.echo("ok")
                        + "/" + ComparableFirst.echo("ok")
        );
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all BoundOrderDemo.java
java BoundOrderDemo
~~~

Stdout chính xác:

~~~text
firstA=java.io.Serializable
firstB=java.lang.Comparable
returnA=java.io.Serializable
returnB=java.lang.Comparable
boundsA=java.io.Serializable | java.lang.Comparable<T>
boundsB=java.lang.Comparable<T> | java.io.Serializable
stableA=java.lang.Number
stableB=java.lang.Number
stableBoundsA=java.lang.Number | java.io.Serializable | java.lang.Comparable<T>
stableBoundsB=java.lang.Number | java.lang.Comparable<T> | java.io.Serializable
values=ok/ok
~~~

Các dòng đầu dùng `Method.getParameterTypes()` và `getReturnType()` để quan sát **erased classes**: Serializable hoặc Comparable tương ứng bound đứng đầu.

Các dòng `boundsA/boundsB` dùng `TypeVariable.getBounds()` để đọc **generic declarations** đúng thứ tự và đầy đủ. Chúng không phải những types mà JVM bắt buộc phân biệt bằng một class runtime riêng cho mỗi intersection.

Hai dòng `stableA/stableB` cho thấy khi Number vẫn ở vị trí đầu thì erased parameter types đều là Number. Trong khi đó `stableBoundsA/stableBoundsB` vẫn khác nhau vì Reflection giữ thứ tự các secondary bounds.

Cuối cùng, `values=ok/ok` minh họa **cả hai phiên bản có thể chạy tốt nếu client biên dịch phù hợp với từng version**; nó không chứng minh client binary cũ có thể liên kết với version descriptor khác.

## 8. Phân biệt Method descriptor với Generic Signature attribute

Một generic declaration mang nhiều thông tin hơn bytecode descriptor.

Ví dụ method:

~~~java
static <T extends Serializable & Comparable<T>> T echo(T value)
~~~

Có các khái niệm:

| Tầng | Ý nghĩa |
| --- | --- |
| **Source declaration** | T và các bounds tạo quy tắc kiểm tra kiểu cho javac. |
| **Erasure** | T biến thành leftmost bound để tạo erased types. |
| **Method descriptor** | Mô tả parameter/return types mà JVM dùng trong liên kết, ở đây Serializable→Serializable. |
| **Signature attribute** | Giữ lại mô tả type parameters/bounds và những generic constructs phục vụ reflection và compiler. |

Một class file có thể vừa có descriptor đã erasure vừa có `Signature` thể hiện đủ cả hai bounds. Khi đổi thứ tự bounds sau bound đầu giữ nguyên, descriptor có thể không đổi nhưng metadata `Signature` sẽ khác.

Để xem:

~~~bash
javap -v -p BoundOrderDemo
~~~

Nếu method nằm trong nested class:

~~~bash
javap -v -p 'BoundOrderDemo$SerializableFirst'
~~~

Dấu `$` trong binary name chỉ nested class. Ví dụ trên dùng shell có single quotes phù hợp Bash/PowerShell để không nội suy ký tự đặc biệt.

Hãy tìm:
- `descriptor:` — JVM types cho method.
- `Signature:` — generic signature khi có.
- `Code:` — instructions của implementation.
- `ACC_BRIDGE`/`ACC_SYNTHETIC` nếu compiler tạo bridge methods trong một hệ phân cấp lớp có overriding.

**Đừng đọc Signature như thể nó là descriptor dùng để liên kết method.** Điều gây `NoSuchMethodError` ở thực nghiệm chính là sự khác biệt giữa descriptor client đang gọi và descriptor thư viện thực sự cung cấp.

## 9. Đổi bound đầu tiên ảnh hưởng tới method, field và class generic

Không chỉ generic methods riêng lẻ mới bị ảnh hưởng. Một **generic class** có type variable T cũng tạo các member signatures dựa trên erasure(T).

Giả sử thư viện v1:

~~~java
public class Box<T extends java.io.Serializable> {
    public T value;

    public T get() {
        return value;
    }

    public void set(T replacement) {
        value = replacement;
    }
}
~~~

Các kiểu erasure liên quan:
- `value` field descriptor là Serializable.
- `get()` return descriptor là Serializable.
- `set(T)` parameter descriptor là Serializable.

Nếu đổi thành:

~~~java
public class Box<T extends Comparable<T> & java.io.Serializable> {
    public T value;

    public T get() {
        return value;
    }

    public void set(T replacement) {
        value = replacement;
    }
}
~~~

Leftmost bound trở thành Comparable. **Các erased descriptors của field và methods sử dụng T sẽ đổi**. Một client cũ có thể thất bại với:
- `NoSuchFieldError` khi truy cập field theo descriptor cũ.
- `NoSuchMethodError` khi gọi `get` hoặc `set` theo descriptor cũ.

Điểm cần nhớ: `T` xuất hiện ở nhiều nơi trong public/protected bytecode API, nên thay bound đầu tiên có thể tạo **hàng loạt thay đổi binary signatures** chứ không chỉ một generic annotation.

### 9.1. Nếu T chỉ xuất hiện trong metadata thì sao?

Một thay đổi generic bound không luôn phá mọi binary client:
- Nếu descriptor public methods/fields thực sự **không đổi**, những lời gọi tới các descriptors đó không mất liên kết **chỉ vì bound order**.
- Nếu thay đổi chỉ tác động metadata `Signature`, một JVM call thông thường có thể vẫn chạy.
- Dù vậy compiler mới, reflective tools, method selection hoặc implementation behavior vẫn có thể bị ảnh hưởng.

Vì thế **không** nên áp dụng quy tắc tuyệt đối “hễ sửa bounds là binary-incompatible” hoặc “hễ không sửa tên method là compatible”. Phải kiểm tra **erased ABI thực tế**.

## 10. Thay secondary bounds: source compatibility có thể đổi dù binary descriptor giữ

Xét v1:

~~~java
static <T extends Number & java.io.Serializable>
T pass(T value) {
    return value;
}
~~~

Và v2 thêm interface constraint:

~~~java
static <T extends Number & java.io.Serializable & Comparable<T>>
T pass(T value) {
    return value;
}
~~~

Bound đầu vẫn là Number, nên nếu method body/chữ ký khác không đổi, erased descriptor của `pass(T):T` vẫn là Number→Number.

Nhưng **tập các kiểu source được phép truyền có thể thu hẹp**. Một subtype Number implements Serializable nhưng không Comparable<T> có thể được chấp nhận với v1 và bị javac từ chối với v2.

Ví dụ một class Number do ứng dụng định nghĩa implement Serializable nhưng không Comparable:

~~~java
final class Metric extends Number
        implements java.io.Serializable {

    private final int value;

    Metric(int value) {
        this.value = value;
    }

    public int intValue()    { return value; }
    public long longValue()  { return value; }
    public float floatValue(){ return value; }
    public double doubleValue(){ return value; }
}
~~~

`pass(new Metric(1))` hợp lệ với v1 nhưng **không biên dịch với v2** do thiếu `Comparable<Metric>`. Source compatibility của caller đó bị phá dù erasure của T vẫn là Number.

Nếu client đã compile với v1, việc JVM có còn liên kết được với v2 phụ thuộc descriptors và những thay đổi triển khai khác. Trong ví dụ đơn giản `return value`, descriptor Number→Number giống nhau và client cũ có thể vẫn gọi được. Nhưng nếu v2 bắt đầu gọi `compareTo` thông qua bound mới, một object Metric do client cũ gửi tới có thể gây lỗi runtime khi implementation cast/dùng Comparable.

**Không nhầm “link được” với “hành vi vẫn đúng”.** Source contract đã chặt hơn nhưng bytecode cũ có thể tiếp tục gọi method, do JVM không kiểm tra generic bounds như một hợp đồng runtime đầy đủ ở mỗi invocation.

## 11. Đổi từ unbounded T sang bounded T có thể đổi erasure

Ví dụ API ban đầu:

~~~java
static <T> T same(T value) {
    return value;
}
~~~

Erasure của T là Object, nên descriptor:

~~~text
(Ljava/lang/Object;)Ljava/lang/Object;
~~~

Đổi thành:

~~~java
static <T extends CharSequence> T same(T value) {
    return value;
}
~~~

Erasure của T thành CharSequence và descriptor đổi:

~~~text
(Ljava/lang/CharSequence;)Ljava/lang/CharSequence;
~~~

Dù method tên `same` không đổi, và rất nhiều đối số như String vẫn thỏa constraint mới, binary client đã biên dịch tìm Object descriptor có thể bị `NoSuchMethodError` nếu không có phương thức tương thích cũ.

Ngược lại, **thêm một secondary bound** sau một first bound ổn định không tự đổi erasure, nên cần đánh giá riêng.

### 11.1. Thay bound class đầu

~~~java
<T extends Number & java.io.Serializable>
~~~

thành:

~~~java
<T extends Integer & java.io.Serializable>
~~~

**Không hợp lệ** vì Integer là final class, không thể dùng `Integer` làm một superclass bound của một subtype mới? Java type parameter `<T extends Integer>` có thể là khai báo hợp lệ dù class Integer final: giá trị T chỉ có thể là Integer, compiler có thể chấp nhận. Nhưng việc chọn thay giới hạn quá hẹp là vấn đề thiết kế, không phải ví dụ nên dựa vào để minh họa runtime behavior tổng quát.

Một ví dụ rõ ràng hơn:

~~~java
<T extends Number>
~~~

đổi sang:

~~~java
<T extends java.lang.Comparable<T>>
~~~

thay erasure từ Number thành Comparable; nếu method signature sử dụng T, erased ABI tương ứng có thể thay đổi.

**Nguyên tắc:** đổi bound **đầu tiên** hoặc thêm một class bound trước các interface hiện có có thể làm thay đổi erasure, kể cả khi các ràng buộc khác vẫn giữ nguyên.

## 12. Chữ ký throws T và exception bounds

Java cho phép một type variable có bound phù hợp trong `throws`:

~~~java
static <E extends Exception> void propagate(E ex) throws E {
    throw ex;
}
~~~

Ở đây E là một type variable có erasure liên quan bound Exception. Nếu method dùng E làm tham số hoặc kiểu trả về, đổi bound đầu tiên có thể đổi **descriptor của chính vị trí E đó**.

Một điểm khác phải tách biệt: mệnh đề `throws` của Java **không thuộc JVM method descriptor theo nghĩa parameter/return types**. Chỉ đổi danh sách checked exceptions trong `throws` mà không thay erased parameter/return descriptors không nhất thiết làm mất method ở bước resolution.

Tuy nhiên thay `throws` có thể:
- Phá **source compatibility** vì compiler áp dụng checked-exception rules.
- Đổi `Exceptions` attribute hoặc `Signature` metadata.
- Ảnh hưởng Reflection (`getExceptionTypes` / `getGenericExceptionTypes`).
- Ảnh hưởng hành vi thực tế nếu implementation ném exception khác.

Đừng khái quát “mọi thay đổi generic exception bound đều là NoSuchMethodError”. Hãy nhìn xem E có xuất hiện ở **parameter/return descriptor** hay không, rồi kiểm tra các hợp đồng khác.

## 13. Interface methods, overriding và bridge methods

Đổi erasure của type variables trong generic interfaces hoặc superclass không chỉ ảnh hưởng một method độc lập. Nó có thể tương tác với **overriding** và những bridge methods do javac sinh.

Ví dụ:

~~~java
interface Store<T> {
    T get();
    void put(T value);
}

final class StringStore implements Store<String> {
    private String value;

    public String get() {
        return value;
    }

    public void put(String value) {
        this.value = value;
    }
}
~~~

Sau erasure của Store<T> unbounded, interface methods có descriptors tương ứng với Object. Compiler có thể tạo **bridge methods** trong StringStore để một lời gọi qua Store vẫn tới implementation nhận/trả String.

Nếu sau một phiên bản thư viện, interface Store thay thành `Store<T extends CharSequence>`, những method declarations dùng T có thể có descriptors tương ứng với CharSequence thay vì Object.

Rủi ro:
- Một client cũ dùng `invokeinterface Store.get:()Ljava/lang/Object;` có thể không thấy phương thức với descriptor cũ trong phiên bản interface mới.
- Một implementation đã compile từ trước có thể không thỏa mới các contracts/bridge expectations.
- Tùy cách thay đổi interface/class và bytecode cụ thể, có thể xuất hiện `NoSuchMethodError`, `AbstractMethodError` hoặc lỗi liên kết/hành vi khác.

**Không tự đoán lỗi chính xác chỉ từ source snippet** khi có nhiều inheritance/bridge relationships. Cách chắc chắn là kiểm tra `javap -p -s -v` của cả thư viện và class implementation trước/sau, rồi chạy **client và plugin binaries cũ** với bản thư viện mới.

### 13.1. Bridge methods không phải phương thuốc tự động

Compiler tạo bridge methods trong những tình huống cần bảo toàn dispatch theo quy tắc overriding và erasure; không có cam kết nó sẽ tự giữ **mọi descriptor công khai của API version trước** sau khi developer đổi bounds.

Ví dụ static method `Api.echo` ở phần 5 **không được cứu bởi bridge method** chỉ vì đổi thứ tự generic bounds. Khi cần tương thích binary, phải có chiến lược API/compatibility rõ ràng chứ không trông chờ compiler tự sinh adapter cho mọi signature cũ.

## 14. Generic overloads, method lookup và erasure clashes

Generic overload resolution diễn ra ở **compile time** dựa trên các phương thức hiện có và ràng buộc kiểu. Sau erasure, JVM method names/descriptors phải thỏa các quy tắc không va chạm.

Ví dụ:

~~~java
static <T extends java.io.Serializable> void use(T value) {
    System.out.println("serializable");
}
~~~

Nếu đổi bound đầu của T sang Comparable, erased parameter descriptor sẽ đổi. Điều đó không chỉ ảnh hưởng client cũ mà còn có thể tác động cách compiler nhìn tập overloads ở source.

Hai declarations khác nhau có thể gặp **name clash** khi erasure giống nhau, ví dụ:

~~~java
// Các phương thức sau không thể overload chỉ nhờ type argument:
// void add(List<String> values) { }
// void add(List<Integer> values) { }
~~~

Cả hai bị xóa tham số List<String>/List<Integer> về raw List trong bytecode, gây cùng erased signature.

Khi thay bounds, hãy kiểm tra:
- Các overloads có còn hợp lệ ở source không?
- Erased parameter types có đổi không?
- Bytecode method descriptors nào biến mất hoặc xuất hiện?
- Client đã compile có invoke đúng descriptor tồn tại không?
- Các method bridge/synthetic có thay đổi không?

**Cùng tên method** không đủ chứng minh binary compatibility. Một phương thức “trông tương đương” ở Java source có thể không phải binary method mà client cũ đang tham chiếu.

## 15. Reflection đọc bounds theo thứ tự nhưng không tự chứng minh tương thích nhị phân

Các API Reflection hữu ích:

~~~java
Method m = SomeClass.class.getDeclaredMethod(
        "echo", java.io.Serializable.class
);

TypeVariable<Method> t = m.getTypeParameters()[0];

Type[] bounds = t.getBounds();
Class<?> erasedReturn = m.getReturnType();
Class<?>[] erasedParams = m.getParameterTypes();
Type genericReturn = m.getGenericReturnType();
~~~

Nếu bound đầu đã đổi thành Comparable, lookup `getDeclaredMethod("echo", Serializable.class)` có thể thất bại vì erased parameter type mới không còn là Serializable. Phải dùng kiểu parameter thực tế của method.

Trong chương trình `BoundOrderDemo`:
- SerializableFirst có erased parameter/return Serializable.
- ComparableFirst có erased parameter/return Comparable.
- NumberFirstA và NumberFirstB đều có erased parameter/return Number, dù `getBounds()` cho thứ tự secondary bounds khác nhau.

**Reflection rất có ích để kiểm tra metadata**, nhưng để khẳng định backward binary compatibility nên dùng **javap descriptors và chạy binary client cũ**. Các framework dựa trên TypeVariable.getBounds() có thể thay đổi hành vi sau khi secondary bounds bị đảo dù JVM descriptors không đổi.

### 15.1. TypeVariable.getBounds không nên bị sort tùy tiện

Thứ tự bounds trong generic declaration là thông tin có ý nghĩa đối với erasure. Một schema tool tự sort alphabetically rồi dùng phần tử đầu như erasure sẽ tính sai nếu original first bound khác phần tử đầu sau sort.

Khi chỉ muốn hiển thị tập giao các interface cho người đọc, có thể trình bày ở dạng dễ hiểu. Nhưng khi cần tính erasure, **giữ nguyên bound order được khai báo** và không tự tráo thứ tự trước khi xác định leftmost bound.

## 16. Cách kiểm tra ABI trước và sau thay đổi thư viện

Một quy trình thực dụng để review thay đổi:

### 16.1. Chốt phiên bản cũ

Build thư viện cũ thành jar hoặc thư mục class files, và giữ một client sample đã compile:

~~~bash
javac --release 17 -d old-classes api/Api.java
javac --release 17 -cp old-classes -d client-classes Client.java
~~~

Không chỉ giữ source. Điểm khác biệt của binary compatibility chính là **giữ nguyên client .class file**.

### 16.2. Kiểm tra erased descriptors

~~~bash
javap -p -s -classpath old-classes api.Api
javap -p -s -classpath new-classes api.Api
~~~

So sánh:
- Tên class/interface.
- Tên methods và erased parameter/return descriptors.
- Fields và descriptors.
- Visibility/access modifiers, static/instance.
- Những members có thay đổi do inheritance và compiler bridges.

Để xem generic metadata:

~~~bash
javap -p -v -classpath old-classes api.Api
javap -p -v -classpath new-classes api.Api
~~~

So sánh các `Signature` attributes, type parameters, bounds và những attributes khác liên quan.

### 16.3. Chạy binary cũ với thư viện mới

Không recompile Client.class trong bài test này:

~~~bash
java -cp client-classes:new-classes Client
~~~

Trên Windows thay `:` bằng `;` trong classpath. Phải đảm bảo classpath không vô tình lấy Api.class cũ trước Api.class mới, nếu không bài test sẽ cho **false pass**.

### 16.4. Biên dịch lại client để kiểm tra source compatibility

Sau đó mới chạy một bài test riêng:

~~~bash
javac --release 17 -cp new-classes -d recompiled-client Client.java
~~~

Có thể client binary cũ thất bại nhưng source recompile thành công (như thực nghiệm thay bound đầu), hoặc ngược lại có những thay đổi generic signature làm source bị từ chối dù erased descriptor không đổi.

### 16.5. Test hành vi và reflection

Nếu ABI ổn, vẫn cần:
- Tests với các subtype thực sự được APIs chấp nhận.
- Tests dùng raw/legacy clients nếu thư viện có hợp đồng tương thích.
- Reflection/schema/serialization tests nếu sản phẩm đọc `Signature`.
- Integration tests với subclass, implementors, proxies, plugins và method handles khi hệ thống dùng chúng.

Công cụ kiểm tra binary API diff có thể hỗ trợ kiểm tra tự động. Nhưng điều kiện triển khai cụ thể như dynamic classloading, modules, bridges và bytecode generation vẫn cần test phù hợp.

## 17. Bảng đánh giá nhanh từng loại thay đổi bounds

| Thay đổi | Erasure T | Nguy cơ binary | Nguy cơ source/metadata |
| --- | --- | --- | --- |
| `<T>` → `<T extends Number>` | Object → Number | Cao nếu T xuất hiện trong public erased descriptors. | Nhiều caller không còn thỏa bound. |
| `Serializable & Comparable<T>` → `Comparable<T> & Serializable` | Serializable → Comparable | Cao nếu T nằm ở parameters/return/fields. | Có thể vẫn nhận cùng String; order metadata đổi. |
| `Number & Serializable & Comparable<T>` → `Number & Comparable<T> & Serializable` | Number → Number | **Không tự đổi descriptor** của ví dụ dùng T. | `Signature`/Reflection order đổi; cần kiểm tra contract khác. |
| `Number & Serializable` → `Number & Serializable & Comparable<T>` | Number → Number | Descriptor không tự đổi, nhưng implementation/bridge có thể đổi. | Tập type arguments hợp lệ thu hẹp; client recompilation có thể lỗi. |
| `Number & Serializable` → `Number` | Number → Number | Descriptor đơn giản ổn nếu mọi thứ khác giữ nguyên. | Tập type arguments mở rộng; implementation có thể thay đổi. |
| `Number` → `CharSequence` | Number → CharSequence | Có thể làm đổi ABI của members dùng T. | Các callers theo Number có thể bị từ chối. |
| Chỉ đổi `throws` checked exception types | Tham số/trả về không nhất thiết đổi | Không tự đổi method descriptor chỉ vì throws. | Source checked-exception contract và Reflection đổi. |
| Đổi member visibility, static hoặc inheritance | Không chỉ phụ thuộc bounds | Rủi ro riêng theo JVM/JLS binary rules. | Cần đánh giá riêng. |

“Nguy cơ binary” không có nghĩa tất cả clients đều thất bại. Client chỉ gọi những members không thay đổi descriptor có thể không bị tác động. Nhưng nếu public ABI bị mất descriptor đã công bố, **đó là breaking change đối với binary clients phụ thuộc descriptor đó**.

## 18. Thiết kế API để tránh ràng buộc không cần thiết vào erasure

### 18.1. Không dùng intersection bounds chỉ vì trông đẹp

Nếu method chỉ lưu/chuyển tiếp value và không thực sự cần Comparable, thêm Comparable chỉ làm API chặt hơn và có thể ảnh hưởng tính tương thích mà không đem lại khả năng thực sự được dùng.

~~~java
static <T extends java.io.Serializable> T keep(T value) {
    return value;
}
~~~

Nếu chỉ cần truyền object mà không sử dụng Serializable members, thậm chí một `<T> T keep(T)` hoặc API non-generic khác có thể thích hợp hơn; nhưng **không tùy tiện đổi API đã phát hành**, vì chính việc bỏ Serializable bound cũng làm erasure đổi thành Object.

### 18.2. Chọn bound đầu như một quyết định ABI

Khi thiết kế một API **mới** dùng multiple interface bounds, hãy ý thức rằng chọn interface nào đứng đầu không chỉ là thẩm mỹ. Nếu T được dùng trong method parameter/return/field signatures, interface đầu sẽ xuất hiện trong erased descriptors.

Đừng mong sau khi phát hành có thể đảo tùy ý mà không ảnh hưởng người dùng. Chọn thứ tự có lý do thiết kế rồi giữ ổn định trừ khi chấp nhận breaking change và versioning tương ứng.

### 18.3. Tách yêu cầu thao tác khỏi chữ ký công khai khi hợp lý

Có trường hợp một method chỉ cần tiếp nhận type rộng, rồi kiểm tra một khả năng tùy chọn bên trong:

~~~java
static String describe(Object value) {
    return String.valueOf(value);
}
~~~

Nếu API thật sự không cần giả định Comparable hoặc Serializable ở type contract, đừng thêm các bounds đó “để phòng xa”. Tuy nhiên nếu thuật toán bắt buộc cần `compareTo` với compile-time type safety, một bound Comparable có thể là yêu cầu đúng. Mục tiêu là **bounds phản ánh nhu cầu thật** và không được thay đổi vô tội vạ trong released ABI.

### 18.4. Không ép raw/unchecked để “duy trì compatibility”

Một client không compile với bounds mới không nên được sửa bằng raw casts tùy tiện:

~~~java
// Bỏ type checking bằng raw type hoặc unchecked cast
// không khiến JVM descriptor cũ xuất hiện trở lại.
~~~

Raw type/cast làm mất type safety nhưng không sửa một `NoSuchMethodError` do binary descriptor không còn. Phải giải quyết **API linkage**, không phải che compiler diagnostics.

## 19. Chiến lược migration khi buộc phải thay đổi bound đầu

Nếu cần thay bounds và erasure của một public API đã phát hành, các phương án cần cân nhắc:

1. **Giữ ABI cũ nếu có thể:** tránh đổi bound đầu; đưa yêu cầu mới qua helper/overload rõ ràng mà không trùng erasure.
2. **Thêm API mới có tên khác:** ví dụ `echoComparable` thay vì thay tại chỗ `echo`, giúp clients cũ tiếp tục gọi `echo`.
3. **Giữ một adapter với descriptor cũ khi phù hợp:** phương thức cũ chuyển tiếp đến logic mới, nhưng phải kiểm tra type contracts; không thể tự tạo overload chỉ khác return type trong Java source.
4. **Version như breaking change** nếu không thể giữ descriptor cũ, và thông báo yêu cầu rebuild/relink các modules.
5. **Đánh giá class inheritance và bridge methods**: một adapter thủ công có thể không đủ trong generic interfaces/overrides.
6. **Kiểm tra client binary cũ**, không chỉ build lại tất cả code.
7. **Kiểm tra Source API** sau khi thay: những callers dùng type arguments không thỏa bounds mới phải nhận lỗi compile rõ.
8. **Không giả định một JVM compatibility shim luôn hợp lệ**: có thể gặp erased signature clashes hoặc thay đổi dispatch/overload resolution.

Với method đơn giản ở phần 5, có thể giữ method cũ tên `echo` và đưa method mới tên `echoComparable`, tránh mất descriptor cũ. Nếu vừa muốn tên cũ vừa muốn kiểu mới, cần thiết kế cẩn thận để không xung đột giữa erased signatures và hành vi của các overloads.

### 19.1. Adapter có thể giữ descriptor cũ bằng một overload hợp pháp

Ví dụ nếu signatures khác nhau ở erased parameter types, thư viện có thể cung cấp **hai overloads** với tên giống nhau khi Java cho phép và không bị xung đột method resolution:

~~~java
public static <T extends java.io.Serializable & Comparable<T>>
T echo(T value) {
    return value;
}

public static <T extends Comparable<T> & java.io.Serializable>
T echoComparable(T value) {
    return value;
}
~~~

Đây là một lựa chọn giữ **tên cũ + erased signature cũ** và thêm **tên mới**, không phải thủ thuật tự động làm method mới có cả hai descriptors. Tên method mới khiến binary behavior rõ ràng, tránh các vấn đề overload ambiguity khi input String thực hiện nhiều interfaces.

Không nên khẳng định một overload mới của cùng tên với Serializable và Comparable luôn lựa chọn đúng theo lời gọi Java: String là subtype của cả hai nhưng hai interface không nhất thiết có quan hệ subtype, nên việc overload có thể gây **ambiguous method call** khi recompile. Versioning/API mới có tên riêng thường dễ kiểm soát hơn.

## 20. Thứ tự bounds và reflection/schema frameworks

Một số công cụ đọc generic declarations bằng:

~~~java
TypeVariable<?> typeVar =
        SomeClass.class.getTypeParameters()[0];

Type[] bounds = typeVar.getBounds();
~~~

Dù secondary bounds đổi thứ tự và JVM descriptor của member vẫn giữ, công cụ:
- ghi log hoặc hiển thị bounds theo thứ tự khai báo;
- chọn bound đầu như đại diện cho erased runtime class;
- xây schema hoặc mapping constraints;
- so sánh generic signatures khi tạo cache keys;
- sinh mã hoặc proxy dựa trên generic information;

có thể quan sát sự khác biệt.

Khi thay API, **không chỉ kiểm tra liên kết JVM mà bỏ qua public metadata contract** nếu ecosystem của thư viện dùng reflection. Các framework có thể dựa trên metadata theo cách khác nhau; không phải mọi cách dựa trên thứ tự secondary bounds đều hợp lý, nhưng việc thay thứ tự vẫn có thể làm kết quả của chúng khác đi.

### 20.1. Không parse getTypeName để suy erasure theo thứ tự alphabet

`TypeVariable.getBounds()` trả Type[] theo thứ tự, nhưng các bound có thể là ParameterizedType, Class hoặc type variables khác. Muốn giải đúng erasure cần dùng quy tắc JLS và cấu trúc Type, không sort tên String theo alphabet hay đơn giản lấy tên class runtime của generic object.

`java.lang.reflect.Type` trong generics là metadata về chữ ký, không phải type checking của mọi dữ liệu runtime. Không nhầm reflection với một runtime reification đầy đủ của type arguments.

## 21. Những sai lầm thường gặp

### “Intersection bounds chỉ là một tập hợp; đổi thứ tự không thể gây lỗi”

Sai. Với nhiều interface bounds, **leftmost bound quyết định erasure**. Đảo Serializable và Comparable có thể đổi erased descriptors và phá client binary cũ.

### “Đổi bounds luôn gây NoSuchMethodError”

Sai. Nếu erasure/erased descriptor giữ nguyên và những binary contracts khác không đổi, một đổi secondary bound đơn giản có thể không tạo lỗi linkage ở method call. Source/behavior/metadata vẫn phải kiểm tra.

### “Source client vẫn compile nghĩa là binary compatible”

Sai. Client Java source được compile lại có thể gọi descriptor mới, trong khi Client.class cũ vẫn tham chiếu descriptor cũ.

### “Method có cùng tên và cùng T là cùng method đối với JVM”

Sai. JVM phân biệt method bằng name/descriptor; erasure(T) có thể đổi parameter hoặc return descriptors dù source dùng cùng ký hiệu T.

### “Đổi kiểu trong throws chắc chắn đổi JVM descriptor”

Sai. Throws clause không phải parameter/return descriptor. Nhưng nếu type variable cũng nằm ở parameter/return, thay erasure của nó có thể đổi descriptor tại những vị trí đó.

### “Thêm secondary bound không ảnh hưởng source”

Sai. Nó có thể thu hẹp tập các type arguments hợp lệ, ví dụ Number & Serializable trước đây chấp nhận type không Comparable, còn version thêm Comparable<T> thì không.

### “Bridge methods luôn cứu binary compatibility”

Sai. Bridge methods phục vụ những quy tắc polymorphism/erasure nhất định, không tự giữ mọi descriptor cũ sau arbitrary API redesign.

### “Chỉ cần build sạch toàn hệ thống là đã chứng minh API non-breaking”

Sai. Build sạch **recompile clients** và có thể che mất lỗi binary compatibility với plugin/jar đã phát hành. Cần test riêng binary cũ trên thư viện mới.

### “Reflection thấy hai bounds tương tự nên class runtime cũng giống nhau”

Không đủ. Intersection constraints và Generic Signature metadata không đồng nghĩa JVM có một runtime class mới. JVM method descriptor vẫn bị chi phối bởi erasure.

### “Chỉ cần suppress warnings là fix được linkage”

Sai. `@SuppressWarnings` không thay class file descriptors mà Client.class gọi. Muốn giải NoSuchMethodError phải cung cấp method với signature tương thích hoặc phát hành breaking version/recompile đúng phạm vi.

## 22. Checklist khi review một thay đổi generic bound trong thư viện

1. **Ghi lại chữ ký cũ và mới**, bao gồm type parameter bounds và thứ tự.
2. **Xác định leftmost bound** của từng type variable.
3. **Tính erasure trước/sau**: Object, class bound, interface đầu tiên.
4. **Liệt kê chỗ T xuất hiện** trong public/protected method parameters, return types và field declarations.
5. **So sánh JVM descriptors** bằng `javap -p -s` trên binaries thật.
6. **So sánh generic Signatures** bằng `javap -v` và Reflection khi thư viện có public metadata consumers.
7. **Xem throws**: checked exceptions đổi source contract hay chỉ metadata; đừng lẫn với method descriptor.
8. **Kiểm tra interface/superclass hierarchies**, overriding và synthetic/bridge methods.
9. **Biên dịch lại nguồn client** để đánh giá source compatibility, đặc biệt khi thêm bounds.
10. **Giữ Client.class cũ** và chạy với jar mới để kiểm tra binary compatibility.
11. **Đảm bảo classpath không chứa jar cũ** che khuất class mới.
12. **Đánh giá behavior**: cast, invokes, logic dùng secondary bounds và các objects cũ có thể không đáp ứng constraint mới.
13. **Kiểm thử overloads** vì thay erasure có thể ảnh hưởng overload resolution và name clashes.
14. **Kiểm thử reflection/frameworks** nếu schema/proxies/serialization dùng generic bounds.
15. **Cập nhật versioning và release notes** nếu thay đổi không tương thích; thông báo yêu cầu recompilation hoặc API migration.
16. **Giữ adapter tên và descriptors cũ nếu khả thi**, tránh phá clients mà không có lợi ích cần thiết.
17. **Không đánh đồng compiler errors với JVM linkage errors**: lỗi ở giai đoạn nào quyết định phương án khắc phục.

## 23. Câu hỏi tự kiểm tra

**1.** `<T extends Serializable & Comparable<T>>` có erasure T là gì?

**Đáp án:** Serializable, bởi Serializable là leftmost bound.

**2.** Nếu đảo thành `<T extends Comparable<T> & Serializable>`, erasure thành gì?

**Đáp án:** Comparable. Nếu T xuất hiện trong parameters/return của public method, descriptor có thể đổi tương ứng.

**3.** Java có cho viết `<T extends Serializable & Number>` để đưa Serializable lên đầu không?

**Đáp án:** Không. Nếu có class bound Number, class phải đứng đầu trước interface bounds.

**4.** Đảo `Number & Serializable & Comparable<T>` thành `Number & Comparable<T> & Serializable` có đổi erasure T không?

**Đáp án:** Không. Number vẫn là bound đầu tiên, nên erasure T vẫn là Number. Generic Signature/Reflection order vẫn đổi.

**5.** Vì sao String vẫn source-compatible với hai thứ tự Serializable/Comparable?

**Đáp án:** String thỏa cả Serializable và Comparable<String>. Cùng một tập constraints được yêu cầu, dù order thay đổi.

**6.** Vì sao client bytecode cũ có thể nhận NoSuchMethodError khi thư viện đảo hai interface bounds?

**Đáp án:** Client cũ gọi descriptor nhận/trả Serializable; method mới chỉ có descriptor nhận/trả Comparable. JVM không tìm được old method descriptor.

**7.** Nếu biên dịch lại Client.java với thư viện mới mà chạy được thì đã chứng minh binary compatibility chưa?

**Đáp án:** Chưa. Đó là source recompilation; phải chạy chính Client.class cũ với thư viện mới để kiểm tra binary linkage.

**8.** Khi thêm Comparable<T> sau Number mà giữ Number đầu, descriptor của method dùng T có bắt buộc đổi không?

**Đáp án:** Không; erasure T vẫn là Number. Nhưng caller dùng type không Comparable<T> có thể không compile được nữa, và implementation mới có thể gây lỗi khi xử lý binary cũ.

**9.** Field có kiểu T trong `Box<T extends Serializable>` thay sang `Box<T extends Comparable<T>>` có thể ảnh hưởng gì?

**Đáp án:** Field descriptor theo erasure đổi từ Serializable sang Comparable; một client cũ truy cập field theo descriptor cũ có thể gặp NoSuchFieldError.

**10.** Chỉ thay throws clause có tự đổi JVM method descriptor không?

**Đáp án:** Không, throws không phải một phần của JVM parameter/return descriptor. Nhưng source exception analysis, attributes và runtime behavior có thể bị ảnh hưởng.

**11.** Bản thư viện mới có bridge methods thì chắc chắn mọi binary caller cũ sẽ chạy không?

**Đáp án:** Không. Bridge methods chỉ xuất hiện ở các tình huống cụ thể; cần kiểm tra thực tế descriptors và running compatibility.

**12.** Reflection có thể cho thấy đổi secondary bounds không?

**Đáp án:** Có. `TypeVariable.getBounds()` trả các bounds theo thứ tự generic declaration; dù erasure không đổi, thứ tự mảng có thể khác.

**13.** Vì sao tools nên so sánh cả descriptor và Signature attribute?

**Đáp án:** Descriptor ảnh hưởng JVM linkage; Signature ảnh hưởng thông tin generic cho compiler, Reflection và công cụ metadata. Hai tầng có thể thay đổi độc lập.

**14.** Một API library đã phát hành có nên tự ý “sắp xếp bounds theo alphabet” không?

**Đáp án:** Không. Thứ tự bound đầu có thể quyết định erasure. Nếu muốn cải thiện readability, cần xem đó là API change, kiểm chứng ABI và áp dụng chính sách versioning.

**15.** Khi thay bound đầu, cách kiểm tra đáng tin nhất là gì?

**Đáp án:** Giữ bản client class đã compile trước thay đổi, thay riêng library binary, kiểm tra `javap` descriptors và chạy lại client cũ, đồng thời biên dịch lại source client để đánh giá source compatibility riêng.

## 24. Ghi nhớ

**Thứ tự bounds là một phần có ý nghĩa của generic API design, không chỉ là cách trình bày.**

~~~text
<T extends Serializable & Comparable<T>>
            │ bound đầu
            ▼
   erasure(T) = Serializable
            │
            ▼
   erased descriptor của T dùng Serializable

Đảo hai interface bounds:

<T extends Comparable<T> & Serializable>
            │ bound đầu mới
            ▼
   erasure(T) = Comparable
            │
            ▼
   erased descriptor của T dùng Comparable

→ Binary client cũ có thể tìm sai descriptor
→ NoSuchMethodError nếu method cũ không còn
~~~

Khi **bound đầu giữ nguyên** (như `Number & Serializable & Comparable<T>` đổi thành `Number & Comparable<T> & Serializable`), erasure của T vẫn Number: không phải mọi đổi thứ tự đều đổi descriptor. Tuy nhiên generic Signature/Reflection metadata đổi, và thêm/bớt secondary constraints còn có thể ảnh hưởng source compatibility, runtime behavior và code generation.

Để bảo vệ API đã công bố, hãy làm **cả ba bài test**: biên dịch lại source client, chạy client binary cũ với library mới, và kiểm thử hành vi. Kiểm tra `javap -s -p` cho erased descriptors, `javap -v` cho generic Signatures, và đánh giá bridge/inheritance/fields nếu type variable xuất hiện ở nhiều members.

**Nguyên tắc thực tiễn:** chọn bounds dựa trên nhu cầu thật, xem leftmost bound là một phần của thiết kế ABI, tránh đổi thứ tự tùy hứng trong public APIs và không đánh đồng “source vẫn hợp lệ” với “binary đã phát hành vẫn tương thích”.
