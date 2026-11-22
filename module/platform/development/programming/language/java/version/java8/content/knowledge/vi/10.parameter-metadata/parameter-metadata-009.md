# Kiểm thử metadata tham số trên artifact thực tế trong Java

**Metadata tham số** (*parameter metadata*) là thông tin về tham số phương thức/constructor được lưu trong bytecode hoặc có thể truy vấn qua reflection. Một đoạn Java viết đúng tên tham số trong source **chưa bảo đảm** sau khi build, đóng gói, tối ưu hóa hoặc publish, người dùng thực sự có thể lấy được tên đó từ file `.class` hoặc `.jar`.

Vì vậy, cách kiểm thử đáng tin không dừng ở việc nhìn vào code nguồn hoặc chạy một ví dụ trong IDE. Hãy **biên dịch thành artifact**, dùng đúng compiler flags, **đọc class file**, **chạy reflection trên chính artifact được phân phối**, rồi xác nhận các hợp đồng mà framework/thư viện thực sự cần.

Ba lớp thông tin cần phân biệt:

1. **Tên tham số**: `account`, `limit`, ... được lưu nhờ compiler option như `javac -parameters`, rồi được phản ánh qua `Parameter.getName()` và `isNamePresent()`.
2. **Kiểu, số lượng và chữ ký tham số**: `String`, `int`, generic parameter types, varargs... được xác định theo method signature/descriptor và những class-file attributes liên quan. **Không cần `-parameters` để `getParameterTypes()` có kiểu cơ bản.**
3. **Annotations trên parameter declaration hay type use**: ví dụ `@ParamTag` trên tham số và `@TypeUseTag` trên kiểu `String`. Việc reflection có đọc được hay không phụ thuộc **vị trí, retention và class-file metadata**; không đồng nhất với tính khả dụng của tên tham số.

Bài thuộc phần **Metadata tham số** trong Java 8. `-parameters`, `java.lang.reflect.Parameter`, `MethodParameters` và type-use annotations đã có từ Java 8 và vẫn áp dụng trong Java hiện đại. Ví dụ độc lập dùng **JDK 17+**, chạy với **hai JAR riêng biệt** để kiểm thử cả đường đúng và đường thiếu cấu hình.

## 1. Định nghĩa “artifact thực tế” và mục tiêu kiểm thử

Trong một dự án Java, “artifact” có thể là:

- Các file `.class` sau khi biên dịch.
- JAR do Maven/Gradle hoặc lệnh `jar` tạo.
- JAR/WAR đã được xử lý bằng shading, relocation, bytecode weaving, instrumentation, obfuscation hoặc công cụ đóng gói khác.
- Output của module/library được phát hành lên repository, được một ứng dụng khác load bằng class loader.

**Điểm kiểm tra đúng nhất là output được ứng dụng tiêu thụ hoặc sẽ được phát hành**, không chỉ output ở bước compile đầu tiên. Nếu pipeline có bước biến đổi bytecode, hãy kiểm lại sau bước biến đổi đó.

### Hợp đồng kiểm thử ví dụ

Ta có method:

~~~java
public static String normalize(
        @ParamTag("account") @ClassOnly("build")
        @TypeUseTag String account,
        @ParamTag("limit") int limit) {
    // ...
}
~~~

Test cần xác minh:

- Có **đúng 2 tham số**, theo thứ tự `String` rồi `int`.
- Khi build với `-parameters`, `isNamePresent() == true` và tên lần lượt là `account`, `limit`.
- Khi build không có `-parameters`, với fixture này `isNamePresent() == false`; `getName()` trả tên tổng hợp `arg0`, `arg1`.
- `@ParamTag` có `RUNTIME` retention phải đọc được trên parameter tương ứng trong **cả hai build**.
- `@ClassOnly` có `CLASS` retention không xuất hiện qua Java reflection thông thường, dù attribute được lưu trong class file.
- `@TypeUseTag` trên kiểu `String` phải đọc qua **`getAnnotatedParameterTypes()`**, không nhầm với annotation trên declaration.
- Method chạy đúng hành vi, và những assertion bị sai phải khiến tiến trình thất bại.

Chính sách test phải cho phép phát hiện **mất metadata** dù hành vi nghiệp vụ của `normalize` vẫn đúng. Một chương trình cho kết quả nghiệp vụ đúng không tự chứng minh reflection metadata còn nguyên.

## 2. Tên tham số nằm ở đâu?

Từ Java 8, `javac -parameters` yêu cầu compiler tạo metadata tên tham số cho reflection:

~~~bash
javac --release 17 -encoding UTF-8 -parameters ArtifactParameterDemo.java
~~~

Flag này làm tên tham số formal của methods/constructors được ghi vào **`MethodParameters` attribute** trong class file theo định dạng JVM.

Đối tượng Java reflection tương ứng:

~~~java
Method method = ArtifactParameterDemo.class
        .getDeclaredMethod("normalize", String.class, int.class);

Parameter[] params = method.getParameters();
System.out.println(params[0].getName());
System.out.println(params[0].isNamePresent());
~~~

Đây là đoạn minh họa trong một method có xử lý `NoSuchMethodException`, với `import java.lang.reflect.*;` và class tương ứng có sẵn. `getDeclaredMethod` phải chọn **chính xác method và danh sách kiểu tham số**, chứ không chọn theo tên parameter.

### `getName()` khác `isNamePresent()` như thế nào?

| Tình trạng class file | `isNamePresent()` | `getName()` |
| --- | --- | --- |
| Có tên tham số phù hợp trong `MethodParameters` | `true` | Tên từ class file, ví dụ `account` |
| Không có tên trong class file (fixture thường biên dịch không `-parameters`) | `false` | Tên tổng hợp dạng `argN`, ví dụ `arg0` |

**Luôn kiểm tra `isNamePresent()` nếu hợp đồng thật sự cần tên gốc.** Chỉ xem `getName()` không đủ: chuỗi `arg0` trông giống tên, nhưng ở case này là fallback, không phải tên source do bạn thiết kế.

Tên `arg0`, `arg1` thường gặp khi build không bật `-parameters`, nhưng đừng kết luận mọi compiler-generated parameter trong mọi loại constructor luôn tuân theo đúng trường hợp đơn giản ấy. `Parameter` còn có `isImplicit()`, `isSynthetic()`, `getModifiers()`, `isVarArgs()`; một số construct do compiler tạo có quy tắc đặc biệt.

### `MethodParameters` khác `LocalVariableTable`

Hai class-file attributes phục vụ mục đích khác nhau:

| Attribute | Khi nào thường xuất hiện? | Mục tiêu |
| --- | --- | --- |
| `MethodParameters` | `javac -parameters` cho source phù hợp | Tên và cờ của formal parameters để reflection `Parameter` dùng |
| `LocalVariableTable` | Thông tin debug, ví dụ `-g`/`-g:vars` | Biến local, slot index và phạm vi bytecode phục vụ debug/tools |
| `RuntimeVisibleParameterAnnotations` | Annotation khai báo trên tham số với retention `RUNTIME` | Reflection runtime thấy parameter declaration annotations |
| `RuntimeInvisibleParameterAnnotations` | Annotation tham số với retention `CLASS` | Metadata trong class file, không hiện qua runtime reflection API thường dùng |
| `RuntimeVisibleTypeAnnotations` | Type-use annotation với retention `RUNTIME` | Runtime metadata trên cách dùng kiểu, gồm parameter type tương ứng |

**Bật `-g` không tự thay thế `-parameters`.** Trong thí nghiệm ở phần 10, cả hai JAR đều được biên dịch có `-g`, nên đều có `LocalVariableTable`; nhưng chỉ JAR biên dịch với `-parameters` có `MethodParameters` cho method được kiểm thử, và chỉ JAR đó cho `isNamePresent() == true`.

Một số framework có cơ chế fallback dựa trên bytecode debug trong những phiên bản/hệ sinh thái nhất định, nhưng đó là **hành vi công cụ cụ thể**, không phải bảo đảm từ `java.lang.reflect.Parameter`. Đối với API reflection chuẩn, hãy dựa trên `MethodParameters`/`isNamePresent()` và kiểm tra artifact.

## 3. Annotation trên tham số không đồng nhất với tên tham số

Xét hai annotation declaration:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface ParamTag {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.PARAMETER)
@interface ClassOnly {
    String value();
}
~~~

`ParamTag` và `ClassOnly` cùng áp dụng cho parameter declaration. Nhưng:

- `RUNTIME`: có thể truy vấn qua reflection trên `Parameter`/`Executable`.
- `CLASS`: compiler lưu metadata trong class file, nhưng Java runtime reflection thông thường không trả annotation đó.
- `SOURCE`: chỉ phục vụ quá trình xử lý source, không được giữ trong class file theo cách của `CLASS`/`RUNTIME`.

Các annotation này **không bắt buộc** compiler lưu tên tham số `account`. Vì vậy:
- JAR **có annotation RUNTIME nhưng không có `-parameters`** vẫn đọc được `@ParamTag("account")` qua reflection, nhưng `getName()` trả `arg0`.
- JAR **có `-parameters` nhưng annotation chỉ `CLASS`** vẫn giữ tên `account`, nhưng `getAnnotation(ClassOnly.class)` trả `null`.

Đừng kết luận metadata **toàn bộ bị mất** chỉ vì một trong hai phép kiểm tra không đạt. Cần nhìn đúng attribute tương ứng.

### `Parameter.getAnnotation` và `Executable.getParameterAnnotations`

Hai lối lấy metadata tham số tương ứng:

~~~java
Parameter[] p = method.getParameters();
ParamTag tag = p[0].getAnnotation(ParamTag.class);

Annotation[][] perParameter = method.getParameterAnnotations();
Annotation[] forFirstParameter = perParameter[0];
~~~

Đoạn minh họa giả định `method` đã được lấy đúng bằng reflection. `getParameterAnnotations()` cho mảng ngoài theo **thứ tự tham số**, mảng trong chứa các annotation runtime-visible liên quan từng tham số. Nếu chỉ cần một annotation type, `Parameter.getAnnotation(...)` thường rõ hơn.

Một method không có parameter thì `getParameters().length == 0`. Đừng truy cập `[0]` mà không xác nhận số lượng hoặc chọn đúng method overload.

## 4. Type-use annotation ở parameter type: đường đọc khác

Java 8 bổ sung type annotations. Annotation có `@Target(ElementType.TYPE_USE)` có thể gắn vào **kiểu của tham số**, không nhất thiết là annotation của **parameter declaration**.

Ví dụ:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeUseTag {}
~~~

Dùng:

~~~java
public static void print(@TypeUseTag String text) { }
~~~

Đây là các khai báo minh họa trong ngữ cảnh class phù hợp. Để đọc metadata trên type use:

~~~java
AnnotatedType[] types = method.getAnnotatedParameterTypes();
boolean tagged = types[0].isAnnotationPresent(TypeUseTag.class);
~~~

Không nên thay bằng:

~~~java
boolean tagged = method.getParameters()[0]
        .isAnnotationPresent(TypeUseTag.class);
~~~

rồi mặc định phải trả `true`. Với annotation **chỉ target TYPE_USE**, vị trí metadata nằm trên type-use; một truy vấn parameter declaration annotation không phải API phù hợp.

Đọc đúng bằng `AnnotatedType` còn quan trọng hơn với generic:

~~~java
void accept(List<@TypeUseTag String> values) { }
~~~

Nếu reflection cần annotation trên **type argument `String`**, phải truy vấn cấu trúc `AnnotatedParameterizedType`, không chỉ hỏi `getAnnotatedParameterTypes()[0].getAnnotations()` về annotation của chính outer list type.

Ví dụ mô hình:

~~~java
AnnotatedParameterizedType listType =
        (AnnotatedParameterizedType) method.getAnnotatedParameterTypes()[0];
AnnotatedType elementType =
        listType.getAnnotatedActualTypeArguments()[0];
boolean elementMarked = elementType.isAnnotationPresent(TypeUseTag.class);
~~~

Đây là đoạn minh họa phụ thuộc việc `method` thực sự nhận `List<@TypeUseTag String>`, có retention `RUNTIME` và được build/đọc đúng. Đừng cast một `AnnotatedType` bất kỳ thành `AnnotatedParameterizedType` khi signature không phù hợp.

## 5. Kiểm thử artifact, không chỉ source hoặc output IDE

Một quy trình tối thiểu có thể tái lập:

~~~text
ArtifactParameterDemo.java
       |
       +-- javac -g -parameters --> out/with/*.class
       |                                |
       |                               jar
       |                                |
       |                       with-parameters.jar
       |                                |
       |                    javap -v + java -cp jar
       |
       +-- javac -g ----------> out/without/*.class
                                        |
                                       jar
                                        |
                             without-parameters.jar
                                        |
                            javap -v + java -cp jar
~~~

Hai nhánh lấy **cùng một source**, khác nhau ở một compiler option. Tạo hai JAR riêng để tránh class output cũ hoặc classpath IDE gây sai lệch kết quả.

Mục tiêu của negative-control build **không có `-parameters`** không phải để khuyến nghị phát hành artifact thiếu metadata. Nó giúp chứng minh **bộ test thật sự phát hiện** khác biệt mà bài muốn kiểm tra. Nếu cả hai nhánh đều trả `isNamePresent() == true` do bạn vô tình test file khác, đó là dấu hiệu classpath/cache/build chưa được kiểm soát.

### Đường kiểm tra 1: reflection

Dùng `java -cp with-parameters.jar ArtifactParameterDemo true` để load class từ JAR được thử. Chương trình tự kiểm tra `isNamePresent`, tên, kiểu, annotation và behavior. Chạy lại JAR không `-parameters` với `false` để xác nhận fallback.

### Đường kiểm tra 2: class-file inspection

Dùng:

~~~bash
javap -v -classpath with-parameters.jar ArtifactParameterDemo
javap -v -classpath without-parameters.jar ArtifactParameterDemo
~~~

Tìm các attribute:

- `MethodParameters` trong method signature thuộc class có `-parameters`.
- `RuntimeVisibleParameterAnnotations` cho `@ParamTag`.
- `RuntimeInvisibleParameterAnnotations` cho `@ClassOnly`.
- `RuntimeVisibleTypeAnnotations` cho `@TypeUseTag`.
- `LocalVariableTable` do `-g` trong cả hai nhánh của ví dụ.

`javap -v` hiển thị **class file** được load từ classpath chỉ định, không đòi IDE. Khi có nhiều module/JAR chứa cùng FQCN, hãy chắc chắn đường dẫn trỏ đúng artifact.

**Đừng phụ thuộc vào số constant-pool entry, bytecode offset hoặc thứ tự các phần không liên quan** vì chúng có thể thay đổi theo compiler/toolchain. Test hợp đồng metadata ở cấp reflection hoặc classfile attribute phù hợp, không snapshot toàn bộ output `javap` theo từng dòng.

## 6. Thiết kế assertions để phát hiện mất tên trong artifact

Không nên chỉ viết:

~~~java
System.out.println(method.getParameters()[0].getName());
~~~

Dòng trên chỉ cung cấp quan sát; nếu metadata sai thì build vẫn có thể thành công. Nên dùng điều kiện thất bại rõ ràng:

~~~java
static void check(boolean condition, String message) {
    if (!condition) throw new AssertionError(message);
}
~~~

Và trong test:

~~~java
Parameter[] params = method.getParameters();
check(params.length == 2, "parameter count");

check(params[0].isNamePresent(), "name missing");
check("account".equals(params[0].getName()), "wrong name");
check(params[0].getType() == String.class, "wrong type");

ParamTag label = params[0].getAnnotation(ParamTag.class);
check(label != null && "account".equals(label.value()),
      "missing runtime annotation");
~~~

Các đoạn này là **mã minh họa**, không tự chạy riêng; chương trình đầy đủ có hàm `check` và đúng method `normalize`.

Không dùng `assert condition;` như cơ chế duy nhất nếu không kiểm soát JVM option `-ea`: Java assertions có thể bị tắt mặc định. `throw new AssertionError(...)` chạy độc lập với cờ đó; framework JUnit thì dùng các assertion methods của test engine.

### Khi kiểm thử tên tham số “không có”

Case không `-parameters` nên xác nhận **`!isNamePresent()`**, không chỉ xác nhận `getName().equals("arg0")`, vì mục tiêu là test flag thực sự mô tả classfile:

~~~java
check(!params[0].isNamePresent(), "should not have real name");
check("arg0".equals(params[0].getName()), "unexpected fallback");
~~~

Đây là kỳ vọng **của fixture đơn giản này** với `javac`, không phải kết luận mọi class sinh ra bởi mọi compiler đều thiếu tên nếu không có đúng flag.

## 7. Trường hợp constructor, synthetic và implicit parameters

`Method` và `Constructor` đều kế thừa `java.lang.reflect.Executable`; các API `getParameters()`, `getParameterTypes()` và `getAnnotatedParameterTypes()` áp dụng cho cả hai.

~~~java
Constructor<Order> ctor =
        Order.class.getDeclaredConstructor(String.class, int.class);
Parameter[] ctorParams = ctor.getParameters();
~~~

Đây là snippet minh họa khi `Order(String,int)` có thật và đã import reflection. Một bộ test metadata đầy đủ cho framework khởi tạo object phải đọc **constructor được dùng thật**, không chỉ method business.

Một số loại class có tham số compiler thêm vào:
- Non-static inner class có thể chứa tham chiếu đến enclosing instance.
- Enum constructors có tham số do compiler/JVM quy định.
- Một số constructs/desugaring sinh tham số mà source không viết trực tiếp.

`Parameter.isImplicit()` và `isSynthetic()` giúp nhận diện các trường hợp nhất định; `isVarArgs()` cho biết parameter là biến-đối-số. **Không tự giả định số tham số reflection đúng bằng số tên xuất hiện trong source** đối với các constructs này.

Đối với **record canonical constructor** (records được giới thiệu ở Java 16), tên component và constructor có những quy tắc classfile/compiler riêng. Đừng đem kết quả một constructor record để chứng minh rằng mọi ordinary method đều giữ tên tham số mà không cần `-parameters`; hãy kiểm thử đúng loại artifact và JDK target.

Nếu framework tìm tham số theo tên, hãy thiết kế test cho chính kind của method/constructor mà framework sử dụng: public constructor, declared constructor, generated proxy method, overloaded method hoặc method được transform sau build.

## 8. Metadata tồn tại không có nghĩa giá trị runtime hợp lệ

Annotation `@ParamTag("account")` chỉ nói metadata có nhãn `account`. Nó không chứng minh tham số String **không null** hoặc **đã qua validation**.

~~~java
public static String normalize(String account, int limit) {
    String value = account.strip().toUpperCase(Locale.ROOT);
    return value.length() > limit ? value.substring(0, limit) : value;
}
~~~

Đây là logic minh họa: nếu `account == null` hoặc `limit < 0`, chương trình có thể gặp exception; metadata tồn tại không tự sửa được hành vi. Trong ứng dụng thực, nên kiểm tra yêu cầu đầu vào, đặc biệt ở trust boundary.

Tương tự, `@Retention(RUNTIME)` giúp reflection thấy annotation; không có nghĩa annotation tự động thực thi authorization, serialization policy, validation hoặc dependency injection. Framework muốn dựa vào metadata thì phải **đọc, diễn giải, và xử lý theo hợp đồng riêng**.

### Rủi ro thông tin nhạy cảm trong tên tham số

Nếu tên parameter chứa ngữ nghĩa nhạy cảm, `-parameters` làm chúng có thể truy vấn từ artifact. Điều này không trực tiếp tiết lộ giá trị bí mật của runtime, nhưng tên tham số là **thông tin cấu trúc API** có thể bị người khác xem. Cân nhắc chính sách phân phối code và tên method/parameter; đừng để giá trị bí mật trong source, annotation values hoặc artifact.

## 9. Cách chạy hai artifact mà không dùng dependency bên ngoài

Bộ kiểm thử tối thiểu ở mục 10 gồm một tệp `ArtifactParameterDemo.java`. Ta biên dịch hai lần ra **hai thư mục khác nhau**, sau đó tạo hai JAR. Phần dưới là lệnh cho shell POSIX (Linux/macOS, hoặc Git Bash):

~~~bash
mkdir -p out/with out/without

javac --release 17 -g -parameters -encoding UTF-8 \
  -d out/with ArtifactParameterDemo.java
javac --release 17 -g -encoding UTF-8 \
  -d out/without ArtifactParameterDemo.java

jar --create --file with-parameters.jar -C out/with .
jar --create --file without-parameters.jar -C out/without .

java -cp with-parameters.jar ArtifactParameterDemo true
java -cp without-parameters.jar ArtifactParameterDemo false

javap -v -classpath with-parameters.jar ArtifactParameterDemo
javap -v -classpath without-parameters.jar ArtifactParameterDemo
~~~

Từng `javac` nên trả exit code 0, lệnh `jar` tạo output dự kiến, hai lệnh `java` phải in **`checks=PASS`**. Các lệnh giả định máy có **JDK 17+**, đã đặt đúng `PATH`, đang đứng tại thư mục có file source, thư mục out/with và out/without chưa chứa class file cũ gây nhiễu. Trong CI nên xóa output directory trước mỗi build.

**Không dùng chung thư mục output cho hai build** rồi kiểm tra theo classpath mơ hồ. Nếu class cũ còn tồn tại, test có thể “đạt” dù không kiểm tra artifact vừa tạo.

### Cấu hình Java 8 thuần có thể thực hiện không?

Có. `-parameters`, `Parameter` reflection, `TYPE_USE`, `RUNTIME` và `CLASS` retention đều có từ Java 8. **Ví dụ runnable cụ thể** dùng `String.strip()` (Java 11+) và `jar --create` cú pháp hiện đại, nên hướng dẫn ở đây chọn JDK 17. Nếu dự án cố định Java 8, đổi logic `strip()` thành API phù hợp target và sử dụng cú pháp `jar` mà toolchain Java 8 hỗ trợ; giữ nguyên nguyên tắc metadata/reflect.

Đừng dùng `--release 17` với JDK 8: `--release` được giới thiệu sau Java 8. Để kiểm chứng đúng API target, build bằng JDK phù hợp hoặc dùng `--release <target>` được JDK hiện tại hỗ trợ.

## 10. Chương trình Java 17 độc lập, kiểm tra từ JAR

Đoạn dưới là **một tệp đầy đủ**: có method, annotation declarations, annotation trên parameter và type use, reflection, assertions và kết quả. Chạy đúng hai JAR sẽ kiểm tra trực tiếp metadata được phân phối thay vì suy luận từ source.

Lưu thành **ArtifactParameterDemo.java**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.*;

public class ArtifactParameterDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface ParamTag { String value(); }

    @Retention(RetentionPolicy.CLASS)
    @Target(ElementType.PARAMETER)
    public @interface ClassOnly { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface TypeUseTag {}

    public static String normalize(
            @ParamTag("account") @ClassOnly("build")
            @TypeUseTag String account,
            @ParamTag("limit") int limit) {
        String value = account.strip().toUpperCase(Locale.ROOT);
        return value.length() > limit ? value.substring(0, limit) : value;
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        check(args.length == 1, "Pass expected name visibility: true/false");
        boolean expectNames = Boolean.parseBoolean(args[0]);
        Method method = ArtifactParameterDemo.class.getDeclaredMethod(
                "normalize", String.class, int.class);
        Parameter[] params = method.getParameters();

        check(params.length == 2, "parameter count");
        check(params[0].isNamePresent() == expectNames, "first name flag");
        check(params[1].isNamePresent() == expectNames, "second name flag");
        check(params[0].getName().equals(expectNames ? "account" : "arg0"), "first name");
        check(params[1].getName().equals(expectNames ? "limit" : "arg1"), "second name");
        check(params[0].getType() == String.class, "first type");
        check(params[1].getType() == int.class, "second type");
        check("account".equals(params[0].getAnnotation(ParamTag.class).value()),
                "runtime parameter annotation 0");
        check("limit".equals(params[1].getAnnotation(ParamTag.class).value()),
                "runtime parameter annotation 1");
        check(params[0].getAnnotation(ClassOnly.class) == null,
                "CLASS retention invisible to reflection");
        check(method.getAnnotatedParameterTypes()[0]
                .isAnnotationPresent(TypeUseTag.class), "type-use metadata");
        check(!params[0].isSynthetic() && !params[0].isImplicit(),
                "regular first parameter");
        check("JAVA".equals(normalize(" java ", 4)), "method behavior");

        System.out.println("namesPresent=" + params[0].isNamePresent());
        System.out.println("names=" + params[0].getName() + "," + params[1].getName());
        System.out.println("types=" + params[0].getType().getSimpleName() + ","
                + params[1].getType().getSimpleName());
        System.out.println("annotations=" + params[0].getAnnotation(ParamTag.class).value()
                + "," + params[1].getAnnotation(ParamTag.class).value());
        System.out.println("classOnlyVisible="
                + (params[0].getAnnotation(ClassOnly.class) != null));
        System.out.println("typeUseVisible=" + method.getAnnotatedParameterTypes()[0]
                .isAnnotationPresent(TypeUseTag.class));
        System.out.println("behavior=" + normalize(" java ", 4));
        System.out.println("checks=PASS");
    }
}
~~~

Với JAR **có `-parameters`**, stdout đã được kiểm thử thực tế:

~~~text
namesPresent=true
names=account,limit
types=String,int
annotations=account,limit
classOnlyVisible=false
typeUseVisible=true
behavior=JAVA
checks=PASS
~~~

Với JAR **không có `-parameters` nhưng vẫn có `-g`**, stdout đã được kiểm thử thực tế:

~~~text
namesPresent=false
names=arg0,arg1
types=String,int
annotations=account,limit
classOnlyVisible=false
typeUseVisible=true
behavior=JAVA
checks=PASS
~~~

Các dòng này là kết quả của **hai lần compile riêng, tạo hai JAR riêng và chạy `java -cp` trực tiếp trên mỗi JAR**. `checks=PASS` được in sau khi toàn bộ điều kiện assertion thành công. Nếu thiếu annotation, sai tên, sai số lượng/kiểu hoặc sai hành vi, chương trình ném `AssertionError` và không đến dòng cuối.

### Đọc kết quả và xác định đúng gốc lỗi

- `namesPresent=true` và `names=account,limit`: artifact với `-parameters` có metadata tên cần cho reflection.
- `namesPresent=false` và `names=arg0,arg1`: build thiếu `-parameters` tạo fallback synthetic names của API reflection cho fixture.
- `types=String,int` ở **cả hai**: generic/static type information cơ bản của method không phụ thuộc vào việc lưu tên formal parameter.
- `annotations=account,limit` ở **cả hai**: runtime-visible annotations vẫn được đọc dù không có tên gốc.
- `classOnlyVisible=false` ở **cả hai**: `@ClassOnly` có retention `CLASS`, không phản chiếu runtime, nhưng có thể kiểm tra trong class file.
- `typeUseVisible=true` ở **cả hai**: `@TypeUseTag` được lưu trên parameter **type use**, đọc bằng `AnnotatedType`.
- `behavior=JAVA`: method vẫn hoạt động độc lập với sự hiện diện của metadata tên.
- `checks=PASS` xác nhận toàn bộ hợp đồng đã được kiểm tra, không phải chỉ in output quan sát.

## 11. Kết quả `javap -v` đối chiếu hai JAR

Cùng hai JAR ấy, `javap -v` cho những nhận định đã xác minh sau:

| Quan sát trên `ArtifactParameterDemo` | Với `-g -parameters` | Với `-g`, không `-parameters` |
| --- | --- | --- |
| `MethodParameters` attribute cho method `normalize` | Có | Không |
| `LocalVariableTable` (debug local variables) | Có | Có |
| `RuntimeVisibleParameterAnnotations` | Có | Có |
| `RuntimeInvisibleParameterAnnotations` | Có | Có |
| `RuntimeVisibleTypeAnnotations` | Có | Có |
| `Parameter.isNamePresent` trên `normalize` | `true` | `false` |
| `Parameter.getName` | `account, limit` | `arg0, arg1` |

**Chú ý:** một classfile có thể có nhiều methods và attributes; khi kiểm tra `javap` trên class lớn, cần xác nhận attribute thuộc **đúng method được test**, không chỉ thấy chuỗi `MethodParameters` xuất hiện đâu đó trong constant pool. Với fixture này, kiểm tra source, method reflection và classfile cho kết quả thống nhất.

Với JAR được đóng gói thông thường bằng `jar --create`, các `.class` được lưu vào JAR và metadata vẫn như đã biên dịch. Nếu đi qua **obfuscator, bytecode transformer, instrumentation agent hoặc bước repackaging** có sửa classfile, hãy làm lại cả hai loại kiểm tra trên **artifact cuối cùng**. Không mặc định tất cả công cụ đều bảo toàn `MethodParameters` hoặc annotation attributes.

### Kiểm tra thành phần JAR

~~~bash
jar tf with-parameters.jar
~~~

Fixture có các entries:
- `ArtifactParameterDemo.class`.
- `ArtifactParameterDemo$ParamTag.class`.
- `ArtifactParameterDemo$ClassOnly.class`.
- `ArtifactParameterDemo$TypeUseTag.class`.

Đây là những lớp/annotation nested do compiler tạo. Nếu thiếu một annotation type nhưng classfile còn tham chiếu đến annotation đó, việc phản chiếu và framework có thể gặp vấn đề do classpath thiếu dependency. Vì vậy **kiểm tra JAR entries và chạy từ đúng artifact** đều quan trọng.

## 12. Kiểm thử artifact trong Maven/Gradle/CI

Khi build dùng Maven hoặc Gradle, compiler flags phải được cấu hình ở **đúng module/source set**, nhất là module chứa các API mà framework phản chiếu.

### Maven Compiler Plugin

Ví dụ cấu hình theo cách hiện hành:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <configuration>
    <release>17</release>
    <parameters>true</parameters>
  </configuration>
</plugin>
~~~

Đoạn này là **fragment trong `pom.xml`**, không phải POM độc lập; plugin version nên được quản lý/pin theo chính sách dự án. `<parameters>true</parameters>` yêu cầu plugin truyền `-parameters` cho compiler phù hợp.

### Gradle Java plugin

Ví dụ Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

Đây là **fragment Gradle build script**; cần `JavaCompile` thuộc Java plugin, toolchain phù hợp và version Gradle đang dùng. Để tương thích với cấu hình dự án phức tạp, đảm bảo flag áp dụng cho **mọi task compile cần thiết**, không chỉ compile ở module test.

### Pipeline CI nên kiểm tra gì?

1. Build sạch từ commit/phiên bản nguồn tương ứng.
2. Khóa JDK/toolchain, dependency versions và cấu hình `-parameters`.
3. Chạy unit tests trên class được biên dịch.
4. Package artifact bằng công cụ phát hành thật.
5. **Chạy artifact metadata verification** trên JAR/WAR/output sau packaging.
6. Kiểm tra classpath không có bản cũ của cùng class.
7. Nếu có shading/obfuscation, thực hiện kiểm tra **sau** bước đó.
8. Fail pipeline khi `isNamePresent()`/tên/annotations/parameter count sai.
9. Lưu version/checksum artifact dùng trong test để truy vết.
10. Không rút gọn bài test thành “code compile thành công” vì compiler có thể bỏ metadata dù logic hợp lệ.

Một **negative control** với build không `-parameters` có ích trong bài thực hành, nhưng CI sản phẩm không nhất thiết phải build hai bản mỗi lần nếu pipeline đã chứng minh được bộ test nhạy với việc mất metadata. Vẫn nên có test artifact cuối khẳng định hợp đồng “tên thật phải hiện diện”.

## 13. Những trường hợp dễ kiểm sai ngoài thực tế

| Sai lầm | Vì sao test có thể đánh lừa | Cách phòng tránh |
| --- | --- | --- |
| Chỉ nhìn chữ ký trong source | Source có tên nhưng classfile có thể không lưu tên | Test `Parameter.isNamePresent` trên artifact |
| Chỉ test classes trong IDE | IDE classpath có thể dùng output khác publish | Chạy `java -cp final.jar` |
| Tưởng `-g` tương đương `-parameters` | `LocalVariableTable` không phải `MethodParameters` | Kiểm tra đúng classfile attribute |
| Tưởng `getName()` luôn là tên source | Có fallback `arg0`, `arg1` | Kiểm tra `isNamePresent()` và tên kỳ vọng |
| Test tên tham số mà không test annotation | Hai nguồn metadata độc lập | Assert cả name và retention-visible annotation |
| Thấy `@ClassOnly` trong source rồi dùng reflection đòi thấy | `CLASS` retention không hiện qua runtime reflection | Dùng `javap -v` hoặc classfile tooling |
| Đọc `@TypeUseTag` bằng `Parameter.getAnnotation` | Annotation nằm ở type use | Dùng `getAnnotatedParameterTypes()` |
| Chọn nhầm method overload | Truy vấn method theo sai parameter types | Dùng `getDeclaredMethod(name, types...)` |
| Khẳng định classfile attribute chỉ bằng grep constant pool | Có thể trùng chuỗi ở vùng không liên quan | Đọc block `javap` của method cụ thể |
| Package JAR rồi chỉ test class directory | Không xác minh artifact thực tế | Load class trực tiếp từ JAR |
| Có hai version cùng FQCN trên classpath | Class loader chọn bản không mong muốn | Classpath tường minh, kiểm tra code source nếu cần |
| Bị obfuscation đổi tên/drop attributes | Reflection contract bị phá | Giữ metadata cần thiết bằng tool-specific rules và test sau transform |
| Dùng sample record constructor để chứng minh ordinary methods | Một số compiler rules đặc biệt | Test chính method/constructor framework cần |
| Chỉ assert `params.length == 2` | Tên/annotation có thể mất mà length vẫn đúng | Assert đa chiều metadata |
| Dùng `assert` không bật `-ea` | Assertion có thể không chạy | Dùng `AssertionError` tường minh/JUnit |
| Chỉ test runtime return value | Business behavior vẫn đúng dù metadata mất | Tách metadata contract test |
| Cho rằng `@Retention(RUNTIME)` thực thi validation | Chỉ giữ metadata, không tự kiểm tra dữ liệu | Framework/guard phải thực thi policy |
| Dùng `-parameters` nhưng artifact của module khác thiếu | Compiler config không phủ hết modules | Cấu hình mọi task/module cần phản chiếu |
| Lưu metadata mà không kiểm tra publish pipeline | Artifact cuối khác artifact được test | Test output ngay trước khi phát hành |
| So sánh toàn bộ `javap -v` text giữa JDKs | Output phụ thuộc toolchain và constant pool | Assert các thuộc tính cần thiết, không snapshot toàn bộ |

## 14. Phân tích tình huống “reflection không thấy parameter name”

Nếu đang debug một ứng dụng framework:

**Bước 1 — xác định object thực sự được reflection:** class và method/constructor signature cụ thể. Với proxy/framework, method object có thể thuộc class sinh ra chứ không phải source class mà bạn nghĩ.

**Bước 2 — xác minh class source:** có đúng hai method overload, hay generated bridge method/copy method? `getDeclaredMethods()` có thể chứa method do compiler sinh; khi cần tìm method nghiệp vụ, kiểm tra `Method.isBridge()`/`isSynthetic()` cho đúng trường hợp.

**Bước 3 — xác minh artifact:** dùng `Class.getProtectionDomain().getCodeSource()` khi thích hợp để xác định code source; chú ý không phải class loader/JPMS context nào cũng cung cấp URI đọc được theo cùng cách. Nếu không thể xác minh trong runtime, dùng manifest, dependency tree, package hash và classpath logs.

**Bước 4 — kiểm `MethodParameters`:** `javap -v` trên JAR nghi vấn, xác nhận có tên hợp lệ cho method đó.

**Bước 5 — kiểm `Parameter.isNamePresent()`:** tránh dùng tên `argN` như thể tên được viết trong source.

**Bước 6 — kiểm annotation riêng:** thông tin `PARAMETER` với `RUNTIME` có thể tồn tại ngay cả khi tên mất. Nếu annotation không có, kiểm `@Retention`/`@Target`, dependency và bytecode transformation.

**Bước 7 — kiểm build configuration:** compiler task của source module, có phải incremental build cũ, có shading/minification nào loại attribute không.

**Bước 8 — thêm test vào CI:** fail ngay nếu artifact tương lai vi phạm hợp đồng.

Không nên sửa bằng cách đoán parameter name trong business code, ví dụ tự suy ra `arg0` nghĩa là `account` cho mọi method. Cách ấy dễ sai khi đổi thứ tự tham số hoặc thêm overload.

## 15. Kiểm thử typed và generic parameter metadata

Tên tham số không phải metadata duy nhất. Một method có thể nhận `List<String>`:

~~~java
public static void process(List<@TypeUseTag String> recipients) { }
~~~

Đây là snippet minh họa trong class có `TypeUseTag` đúng target và retention. Các API liên quan:

- `Parameter.getType()` trả `Class<?>` cho erased type, ở đây thường là `List.class`.
- `Parameter.getParameterizedType()` trả `Type` có thể là `ParameterizedType` chứa type argument `String`.
- `Parameter.getAnnotatedType()` hoặc `Executable.getAnnotatedParameterTypes()` cung cấp `AnnotatedType` để truy vấn type-use annotation lồng ở generic element.
- `Method.getGenericParameterTypes()` cung cấp generic type signature metadata theo API reflection.

Với method có **type variables** (`<T> void accept(List<T>)`), generic type được diễn giải theo khai báo và classfile generic signature. Đừng dùng `getType()` rồi khẳng định có thể đọc được `T` hoặc `@TypeUseTag` chi tiết: chúng cần API khác.

Đối với package/build transform có ý định tối ưu hóa classfile, thông tin generic signature và type-use annotations có thể bị ảnh hưởng độc lập với `MethodParameters`. Kiểm thử **đúng metadata mà framework sử dụng**, không chỉ một flag duy nhất.

## 16. Checklist QA trước khi phát hành

- [ ] Xác nhận compiler/JDK target của module thật.
- [ ] Xác nhận method/constructor signature thật trong artifact.
- [ ] Build sạch ra thư mục output riêng.
- [ ] Tên tham số cần phản chiếu đã được biên dịch với `-parameters`.
- [ ] `Parameter.isNamePresent()` đúng cho từng tham số cần thiết.
- [ ] `Parameter.getName()` khớp các tên kỳ vọng.
- [ ] `getParameterTypes()` hoặc `Parameter.getType()` khớp thứ tự/loại tham số.
- [ ] Runtime parameter annotations được đọc đúng `@Target(PARAMETER)`/`@Retention(RUNTIME)`.
- [ ] CLASS-only annotations không bị nhầm là reflection-visible.
- [ ] Type-use annotations được truy vấn qua `AnnotatedType`.
- [ ] `javap -v` cho thấy các attributes cần thiết trên method đúng.
- [ ] Chạy test bằng `java -cp` trỏ trực tiếp đến JAR cuối.
- [ ] Nếu có transform/obfuscation, đã chạy lại test sau transform.
- [ ] Assertions thực sự làm build fail khi có sai lệch.
- [ ] Classpath/module path không vô tình load output khác.
- [ ] CI ghi nhận artifact/version được kiểm thử và chặn release nếu sai.

## 17. Bài tập thực hành

1. Biên dịch `ArtifactParameterDemo` hai lần với và không `-parameters`, dùng hai thư mục output riêng. Giải thích vì sao `getName()` khác mà `getType()` không khác.
2. Bật `-g` cho cả hai build rồi dùng `javap -v`. Vì sao `LocalVariableTable` không thay thế `MethodParameters`?
3. Chuyển `@ParamTag` từ retention `RUNTIME` sang `CLASS`, build lại và quan sát test reflection thất bại. Attribute nào còn nhìn được trong classfile?
4. Chuyển `@TypeUseTag` từ `TYPE_USE` sang `PARAMETER`, rồi sửa đúng API reflection được dùng. Vì sao không thể chỉ thay tên annotation mà giữ nguyên tất cả phép đọc?
5. Thêm một method overload `normalize(String)` và dùng `getDeclaredMethod(...)` để chọn đúng chữ ký 2 tham số. Điều gì xảy ra khi truyền sai parameter types?
6. Tạo constructor nhận `String id`, `int size`, rồi kiểm thử metadata bằng `Constructor.getParameters()`.
7. Thêm một phương thức nhận `List<@TypeUseTag String>` và dùng `AnnotatedParameterizedType` đọc annotation của type argument.
8. Xóa một attribute không thuộc hợp đồng trong quá trình bytecode transformation, kiểm tra có ảnh hưởng metadata test không; so sánh với tình huống bỏ `MethodParameters`.
9. Viết JUnit test trên JAR đã package thay vì class output IDE. Làm sao đảm bảo class loader không chọn bản class khác trên classpath?
10. Tạo một negative control cố ý thiếu `-parameters` và xác minh test có thể fail nếu vẫn kỳ vọng tên thật; sau đó dùng test hai nhánh để phân biệt đúng các trạng thái.
11. Nếu thư viện chỉ cần annotation `@ParamTag` mà không dùng tên tham số, có nên bắt tất cả module bật `-parameters` không? Phân tích hợp đồng thực tế và chi phí metadata.
12. Đề xuất bước CI kiểm tra artifact sau shading/minification; vì sao test trước bước đó không đủ?
13. Giải thích vì sao `Parameter.isNamePresent() == true` không chứng minh `@ParamTag` runtime-visible tồn tại, và chiều ngược lại cũng không đúng.
14. Nếu thấy tên `arg0`, cần kiểm tra flag/method/classpath nào trước khi đổ lỗi cho reflection?

## 18. Tài liệu chuẩn còn áp dụng

- [Oracle JDK 17 javac — `-parameters` và `-g`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle Java SE 17 — `java.lang.reflect.Parameter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html)
- [Oracle Java SE 17 — `java.lang.reflect.Executable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html)
- [Oracle Java SE 17 — `java.lang.reflect.AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Java Virtual Machine Specification — `4.7.24 The MethodParameters Attribute](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html#jvms-4.7.24)
- [Java Virtual Machine Specification — `4.7 Class File Attributes](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html#jvms-4.7)
- [Oracle JDK 17 javap tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html)
- [Maven Compiler Plugin — parameters](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Gradle JavaCompile — compiler options](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.JavaCompile.html)

**Kết luận:** **Kiểm thử metadata tham số trên artifact thực tế** nghĩa là biên dịch bằng đúng flags, đóng gói, dùng `javap -v` kiểm tra attributes và chạy reflection/assertions trên **chính file được phân phối**. Hãy kiểm tra **tên tham số**, **kiểu/chữ ký**, **annotation retention** và **type use** như những hợp đồng riêng. `-parameters` quyết định việc có tên formal parameter cho reflection thông thường; `-g` không thay thế được. Một JAR chạy đúng chức năng nhưng mất `MethodParameters` vẫn có thể làm framework đọc parameter name thất bại, nên artifact-level tests cần là một phần của build/CI hiện đại.
