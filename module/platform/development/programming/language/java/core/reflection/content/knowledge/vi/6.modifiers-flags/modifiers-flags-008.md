# AccessFlag, accessFlags() và khác biệt theo phiên bản JDK trong Java Reflection

## 1. Từ modifier của Java đến access flag của JVM

Một khai báo Java có thể có các từ khóa như `public`, `private`, `static`, `final`, `abstract`, `synchronized`, `volatile`. Khi biên dịch, JVM class file lưu nhiều đặc tính của class, field, method và các cấu trúc khác dưới dạng **bit flag**. Tuy nhiên, không phải mọi khái niệm trong cú pháp Java đều ứng với một bit flag, và có flag chỉ xuất hiện ở cấp JVM.

Cần tách hai góc nhìn:

- **Java language modifier**: điều mà `java.lang.reflect.Modifier` và `getModifiers()` chủ yếu mô hình hóa, phù hợp khi cần đọc quyền truy cập, `static`, `final`, `volatile`, v.v. theo ngôn ngữ Java.
- **JVM access/module flag**: các cờ tại vị trí cụ thể của class file, gồm cả `SYNTHETIC`, `BRIDGE`, `VARARGS`, `ANNOTATION`, `ENUM`, `MANDATED`, `MODULE` và các cờ liên quan module. Từ **JDK 20**, API `java.lang.reflect.AccessFlag` cùng `accessFlags()` đưa cách nhìn này vào core reflection.

Ví dụ, phương thức bridge do compiler tạo có cờ `ACC_BRIDGE` mà từ khóa Java không tương ứng trực tiếp; trong khi `sealed` được biểu diễn bằng metadata `PermittedSubclasses` của class file, **không có** cờ `ACC_SEALED`.

Không được hiểu mọi flag chỉ là “modifier viết trước khai báo”. Một class, field, method, method parameter hoặc mục trong module có **tập cờ hợp lệ khác nhau**.

## 2. Hai API: getModifiers() và accessFlags()

### Cách cũ và vẫn hữu ích: getModifiers() + Modifier

`Class.getModifiers()`, `Field.getModifiers()`, `Method.getModifiers()`, `Constructor.getModifiers()` và `Parameter.getModifiers()` trả về một `int` dạng bit mask. Các phương thức tĩnh trong `Modifier` giải mã theo mục đích của ngôn ngữ:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

class Demo {
    public static final int LIMIT = 10;
}

Field field = Demo.class.getDeclaredField("LIMIT");
int modifiers = field.getModifiers();

boolean isPublic = Modifier.isPublic(modifiers);
boolean isStatic = Modifier.isStatic(modifiers);
boolean isFinal = Modifier.isFinal(modifiers);
String readable = Modifier.toString(modifiers);
```

Đoạn trên là **mảnh mã minh họa** để đặt trong một phương thức có khai báo `throws ReflectiveOperationException`; riêng tệp này chưa phải chương trình chạy độc lập. `Modifier.toString(modifiers)` có ích khi hiển thị modifier nguồn, nhưng `getModifiers()` không phải trình đọc toàn bộ flag trong class file.

Ưu điểm của `getModifiers()`: có từ các bản JDK cũ, dễ kiểm tra các modifier thông dụng, tương thích thư viện chạy trên JDK 8/11/17. Nếu chỉ cần `public/static/final` cho một field, nó thường là lựa chọn hợp lý.

### Từ JDK 20: accessFlags()

`accessFlags()` trả về `Set<AccessFlag>` không thể thay đổi, ví dụ kiểm tra:

```java
Set<AccessFlag> flags = field.accessFlags(); // JDK 20+
boolean isVolatile = flags.contains(AccessFlag.VOLATILE);
```

Tập có thể rỗng; đừng suy luận rằng phần tử xuất hiện theo thứ tự cố định khi in `Set`. So sánh bằng `contains`/`containsAll` thay vì chuyển sang chuỗi. `AccessFlag` là `enum` nên tên cờ phân biệt rõ `VOLATILE` (field) với `BRIDGE` (method) dù trùng bit mask.

Các điểm gọi thông dụng từ JDK 20:

| Đối tượng Reflection | Cách đọc cờ | Chú ý |
| --- | --- | --- |
| `Class<?>` | `clazz.accessFlags()` | Cờ của class/interface; xử lý riêng array, primitive, `void` theo quy tắc `Class`. |
| `Field` | `field.accessFlags()` | Ví dụ `PUBLIC`, `STATIC`, `FINAL`, `VOLATILE`, `TRANSIENT`, `ENUM`, `SYNTHETIC` tùy field. |
| `Method` | `method.accessFlags()` | Ví dụ `SYNCHRONIZED`, `NATIVE`, `ABSTRACT`, `BRIDGE`, `VARARGS`, `SYNTHETIC`. |
| `Constructor<?>` | `constructor.accessFlags()` | Thừa kế triển khai từ `Executable`; áp dụng các cờ hợp lệ với constructor. |
| `Parameter` | `parameter.accessFlags()` | Metadata tham số; cần xem xét khả năng dữ liệu tham số hiện diện trong class file. |

`Member` định nghĩa `default accessFlags()` để hỗ trợ tương thích API, nhưng triển khai mặc định ném `UnsupportedOperationException`. Các implementation core reflection tiêu chuẩn của `Field`/`Method`/`Constructor` cung cấp phương thức này; không suy đoán mọi implementation `Member` tự viết đều hỗ trợ.

**Nhớ:** `accessFlags()` không trả về modifier nguồn dưới dạng chuỗi, không tự kiểm tra bạn có quyền `setAccessible`, và không thay thế mọi API đặc trưng như `Method.isBridge()`, `Class.isRecord()` hoặc `Class.isSealed()`.

## 3. Chương trình Java 20+ có thể chạy để đối chiếu hai API

Lưu vào tệp `AccessFlagLessonDemo.java`:

```java
import java.lang.reflect.AccessFlag;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;

public class AccessFlagLessonDemo {
    static class Sample {
        public volatile int state;
        public synchronized void log(String... values) { }
    }

    interface Formatter<T> { T format(T value); }

    static final class TextFormatter implements Formatter<String> {
        public String format(String value) { return value; }
    }

    public static void main(String[] args) throws Exception {
        Field field = Sample.class.getDeclaredField("state");
        Method method = Sample.class.getDeclaredMethod("log", String[].class);
        Method bridge = Arrays.stream(TextFormatter.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .findFirst()
                .orElseThrow();

        System.out.println("field Modifier.isVolatile = "
                + Modifier.isVolatile(field.getModifiers()));
        System.out.println("field AccessFlag.VOLATILE = "
                + field.accessFlags().contains(AccessFlag.VOLATILE));
        System.out.println("method VARARGS = "
                + method.accessFlags().contains(AccessFlag.VARARGS));
        System.out.println("method SYNCHRONIZED = "
                + method.accessFlags().contains(AccessFlag.SYNCHRONIZED));
        System.out.println("bridge BRIDGE = "
                + bridge.accessFlags().contains(AccessFlag.BRIDGE));
        System.out.println("field mask 0x0040 = "
                + AccessFlag.maskToAccessFlags(0x0040, AccessFlag.Location.FIELD));
        System.out.println("method mask 0x0040 = "
                + AccessFlag.maskToAccessFlags(0x0040, AccessFlag.Location.METHOD));
    }
}
```

Biên dịch/chạy với JDK 20 trở lên; ví dụ đã được biên dịch và chạy thành công bằng JDK 24:

```bash
javac AccessFlagLessonDemo.java
java AccessFlagLessonDemo
```

Stdout chính xác:

```text
field Modifier.isVolatile = true
field AccessFlag.VOLATILE = true
method VARARGS = true
method SYNCHRONIZED = true
bridge BRIDGE = true
field mask 0x0040 = [VOLATILE]
method mask 0x0040 = [BRIDGE]
```

Vì `Sample.state` được khai báo `volatile`, cả `Modifier.isVolatile` và tập `AccessFlag` đều nhận diện thuộc tính này. Method `log(String... values)` là method varargs đồng thời `synchronized`. Generic interface `Formatter<T>` khi bị type erasure yêu cầu một adapter `format(Object)`: compiler sinh **bridge method** trong `TextFormatter`. `Method.isBridge()` và `accessFlags().contains(AccessFlag.BRIDGE)` xác nhận nó. Đây là cờ JVM mà người viết Java thông thường không gõ thành modifier trong nguồn.

Hai dòng cuối đặc biệt quan trọng: cùng bit `0x0040` nhưng ở vị trí `FIELD` nó nghĩa là `VOLATILE`, còn ở vị trí `METHOD` nó nghĩa là `BRIDGE`. Việc decode mà bỏ qua ngữ cảnh có thể tạo kết quả sai nghiêm trọng.

## 4. AccessFlag enum và cách diễn giải theo Location

`AccessFlag` biểu diễn các cờ như `PUBLIC` (`0x0001`), `STATIC` (`0x0008`), `FINAL` (`0x0010`), `VOLATILE` (`0x0040`), `BRIDGE` (`0x0040`), `TRANSIENT` (`0x0080`), `VARARGS` (`0x0080`), `SYNTHETIC` (`0x1000`), `ANNOTATION` (`0x2000`), `ENUM` (`0x4000`).

Các nhóm điển hình:

| Vị trí trong class file | Một số flag có thể gặp | Giải thích |
| --- | --- | --- |
| `CLASS` / `INNER_CLASS` | `PUBLIC`, `FINAL`, `INTERFACE`, `ABSTRACT`, `ANNOTATION`, `ENUM`, `SYNTHETIC`; `STATIC` ở thông tin nested class | Class metadata và thông tin về kiểu lồng nhau có quy tắc khác nhau. |
| `FIELD` | `PUBLIC`, `PRIVATE`, `STATIC`, `FINAL`, `VOLATILE`, `TRANSIENT`, `SYNTHETIC`, `ENUM` | `VOLATILE` và `TRANSIENT` chỉ có ý nghĩa tương ứng ở field. |
| `METHOD` | `PUBLIC`, `PRIVATE`, `STATIC`, `FINAL`, `SYNCHRONIZED`, `BRIDGE`, `VARARGS`, `NATIVE`, `ABSTRACT`, `STRICT`, `SYNTHETIC` | `STRICT` phụ thuộc đời class file. |
| `METHOD_PARAMETER` | `FINAL`, `SYNTHETIC`, `MANDATED` | Mô hình cờ trong mục `MethodParameters`, không đồng nhất với `METHOD`. |
| `MODULE`, `MODULE_REQUIRES`, `MODULE_EXPORTS`, `MODULE_OPENS` | `OPEN`, `TRANSITIVE`, `STATIC_PHASE`, `SYNTHETIC`, `MANDATED` tùy chỗ | Các cờ của module descriptor; không phải `public/private` của Java field. |

**Không phải mọi tổ hợp trên bảng đều hợp lệ.** Đây là các ví dụ cờ theo nhóm, còn JVMS quyết định vị trí, tổ hợp và đời class file cụ thể.

Dùng `AccessFlag.Location` để nêu **vị trí** khi giải mã bit:

```java
AccessFlag.maskToAccessFlags(0x0040, AccessFlag.Location.FIELD);
AccessFlag.maskToAccessFlags(0x0040, AccessFlag.Location.METHOD);
```

Hai lời gọi lần lượt trả tập chỉ gồm `VOLATILE` và tập chỉ gồm `BRIDGE`. Đối với mask chứa bit không được định nghĩa ở vị trí yêu cầu, `maskToAccessFlags` có thể ném `IllegalArgumentException`. Không nên tự viết vòng lặp trên mọi enum constant để đoán ý nghĩa từ `(mask & flag.mask()) != 0` mà không kiểm tra location.

Các phương thức cốt lõi:

- `flag.mask()`: trả int mask, **không phải định danh duy nhất** của flag.
- `flag.sourceModifier()`: cho biết cờ có modifier tương ứng trực tiếp trong ngôn ngữ Java hay không. Điều này không nói cờ đang có trên một đối tượng cụ thể.
- `flag.locations()`: tập các vị trí hợp lệ trong phiên bản class file hiện hành mà API đang mô hình hóa. Tập có thể rỗng với cờ đã hết hiệu lực.
- `flag.locations(ClassFileFormatVersion version)`: xác định vị trí hợp lệ theo đời class file được chọn.
- `AccessFlag.maskToAccessFlags(mask, location)`: diễn giải bit đúng ngữ cảnh theo phiên bản hiện hành; từ JDK 25 có overload nhận thêm `ClassFileFormatVersion`.

Ví dụ tại sao không thể coi `mask` là danh tính:

```java
System.out.println(AccessFlag.VOLATILE.mask() == AccessFlag.BRIDGE.mask());
// true

System.out.println(AccessFlag.TRANSIENT.mask() == AccessFlag.VARARGS.mask());
// true
```

Đây là hai dòng minh họa độc lập về biểu thức, không phải tệp Java hoàn chỉnh.

## 5. Khác biệt theo các phiên bản JDK

| Dòng JDK | API và hệ quả |
| --- | --- |
| **JDK 8, 11, 17, 19 và cũ hơn 20** | **Không có** `java.lang.reflect.AccessFlag` và `accessFlags()`. Dùng `getModifiers()` + `Modifier`, các hàm `isBridge()`/`isSynthetic()`/`isVarArgs()`, và công cụ đọc class file khi cần cờ JVM đầy đủ. |
| **JDK 20** | Bổ sung `AccessFlag`, `AccessFlag.Location`, `Class.accessFlags()`, `Member.accessFlags()` và `Parameter.accessFlags()`. Có `mask()`, `sourceModifier()`, `locations()`, `locations(ClassFileFormatVersion)`, `maskToAccessFlags(mask, location)`. |
| **JDK 21** | Các API trên sẵn có ở bản LTS; ví dụ code trong bài chạy bằng JDK 21. Phù hợp nếu dự án cần LTS và muốn truy cập cờ dạng enum. |
| **JDK 24** | Bổ sung **Class-File API** chuẩn ở package `java.lang.classfile` (JEP 484), trong đó có giao diện `AccessFlags` để đọc/biến đổi file class. Giao diện `java.lang.classfile.AccessFlags` và enum `java.lang.reflect.AccessFlag` là **hai loại API khác mục đích**. |
| **JDK 25** | Thêm overload `AccessFlag.maskToAccessFlags(int, AccessFlag.Location, ClassFileFormatVersion)` để diễn giải mask theo một phiên bản class-file được chỉ định. API có thể còn phát triển ở các bản JDK mới; xem Javadoc đúng phiên bản bạn chạy. |

**Đọc đúng chữ “Since”:** `AccessFlag` có `Since: 20`. Khi trang Javadoc JDK 25 trình bày một overload có `Since: 25`, đó là năm xuất hiện của **overload ấy**, không phải thời điểm toàn bộ enum mới được tạo. Tránh kết luận rằng API chỉ có từ JDK 21 vì đang đọc tài liệu Java 21.

**Phiên bản của JDK đang chạy không đồng nghĩa phiên bản mọi class file được nạp.** Chẳng hạn, có thể chạy JDK 21 để nạp class được biên dịch với `javac --release 17`. Cần xem **class file major version** nếu muốn phân tích flag đã tồn tại vào thời điểm class file được tạo. `AccessFlag.locations(cffv)` mô tả quy tắc của đời class file được hỏi, không tự đổi phiên bản của bytecode đang được xem.

### Trường hợp lịch sử: ACC_STRICT và strictfp

Cờ `AccessFlag.STRICT` (mask `0x0800`) tương ứng `ACC_STRICT` trên **method** và chỉ được JVMS định nghĩa cho class file major version **46–60**, tương ứng Java SE 1.2–16. Từ Java 17, ngữ nghĩa phép toán dấu phẩy động đã luôn strict theo JEP 306; đừng suy rằng method compiled trên JDK hiện đại vẫn phải có `ACC_STRICT` khi có ý tưởng tương tự `strictfp`.

Để phân tích định dạng cũ trên JDK 20+, tra:

```java
import java.lang.reflect.AccessFlag;
import java.lang.reflect.ClassFileFormatVersion;

boolean oldVersionAllowsStrict =
        AccessFlag.STRICT.locations(ClassFileFormatVersion.RELEASE_16)
                .contains(AccessFlag.Location.METHOD);

boolean newVersionAllowsStrict =
        AccessFlag.STRICT.locations(ClassFileFormatVersion.RELEASE_17)
                .contains(AccessFlag.Location.METHOD);
```

Đây là **mảnh mã minh họa** trong một class/method. `oldVersionAllowsStrict` là `true`, `newVersionAllowsStrict` là `false`. Điều này mô tả **định dạng class file**; không nên dùng nó để kết luận hành vi số học của ứng dụng hiện tại.

### Biên dịch và tương thích nhị phân

Một ứng dụng target JDK 17 **không thể biên dịch source** có import `java.lang.reflect.AccessFlag` bằng `javac --release 17`, kể cả bạn đang cài JDK 24. API này chưa tồn tại trong Java 17. Nếu mục tiêu runtime là Java 17, hãy giữ `Modifier` và các API tương thích hoặc dùng build/module đặc thù để đọc class file.

Nếu code được biên dịch với JDK 21 và có gọi `accessFlags()`, việc sao chép class đã biên dịch sang JRE 17 không trở thành tương thích: JRE 17 thiếu API (và bytecode class target mới có thể bị từ chối trước với `UnsupportedClassVersionError`). Đừng chỉ thử “bỏ import” để chữa lỗi tương thích.

## 6. AccessFlag, Modifier và các API kiểm tra trạng thái khác không đồng nghĩa

### Synthetic, bridge và varargs

- `Class.isSynthetic()`, `Field.isSynthetic()`, `Method.isSynthetic()` hoặc `Member.isSynthetic()` trả lời câu hỏi tổng quát về synthetic; `AccessFlag.SYNTHETIC` phản ánh access flag ở vị trí tương ứng. Synthetic không phải một modifier người dùng gõ trước khai báo Java.
- `Method.isBridge()` là cách lâu đời để nhận diện bridge method; `method.accessFlags().contains(AccessFlag.BRIDGE)` là cách biểu diễn enum trên JDK 20+.
- `Executable.isVarArgs()` cho biết method/constructor dùng variable arity; `AccessFlag.VARARGS` là cờ class file tương ứng. **Một `String[]` tham số cuối không tự động biến method thành varargs**; phải có khai báo `String...` hoặc cờ từ class file.
- `Parameter.isImplicit()`, `Parameter.isSynthetic()` và `Parameter.accessFlags()` phục vụ metadata tham số. Một phần thông tin tên/cờ tham số phụ thuộc `MethodParameters` attribute do compiler phát ra, nên đừng giả định mọi class file cũ đều lưu đủ.

### Sealed và record không có cờ AccessFlag tương ứng

Với Java 17+:

```java
boolean isSealed = SomeType.class.isSealed();
boolean isRecord = SomeType.class.isRecord();
```

Đây là mảnh mã minh họa: `SomeType` đại diện class mà dự án định nghĩa. Không có `AccessFlag.SEALED` hay `AccessFlag.RECORD` tương ứng. `sealed` dùng metadata `PermittedSubclasses`, còn record dùng `Record` attribute và các quy ước biên dịch. Đừng kết luận kiểu record dựa vào `FINAL`, hay kiểu sealed dựa vào `ABSTRACT`.

### Access flag khác với quyền truy cập reflection đang được phép

`AccessFlag.PRIVATE` cho biết member là private về mặt metadata. Nó không tự cấp quyền đọc/ghi field private, gọi method private hay mở module. `AccessibleObject.canAccess`, `trySetAccessible()` và các quy tắc module/JPMS vẫn quyết định có truy cập phản chiếu sâu được hay không. Tương tự, cờ `OPEN` trong module là metadata module chứ không tương đương `private` trên field.

### Class, nested class, primitive và array có ngoại lệ

`Class.accessFlags()` của array và primitive/`void` có quy tắc suy diễn riêng theo Javadoc; không giả định lúc nào cũng đọc trực tiếp danh sách bit thô từ `ClassFile` tương ứng (primitive/void và array không có class file độc lập giống class thông thường). Với nested type, `STATIC` có thể được ghi trong `InnerClasses` attribute; cần phân biệt `CLASS` và `INNER_CLASS` khi tự giải mã class file.

Ví dụ, `String[].class.accessFlags()` không có cùng ý nghĩa kiểm tra cấu trúc file với việc đọc thô một `String[].class` trên đĩa: không tồn tại file `String[].class` như một khai báo class riêng để mở.

## 7. Khi cần xem class file thật: công cụ và API phù hợp

Reflection làm việc trên `Class`/`Field`/`Method` **đã được load**; nó trình bày cái nhìn đã chuẩn hóa theo API Java. Nếu nhiệm vụ là phân tích bytecode, byte-level flags, version hoặc attributes, lựa chọn phù hợp hơn là:

1. `javap -v SomeType`: nhìn major version, `flags: (0x...)`, phương thức synthetic/bridge và các attributes. Với ví dụ `AccessFlagLessonDemo`, có thể chạy `javap -v AccessFlagLessonDemo$TextFormatter`; trong shell có quy tắc escape ký tự `$`, vì vậy phải quote tên class phù hợp. Kết quả có thể dài, chủ động tìm các dòng `flags`.
2. Từ **JDK 24**, dùng `java.lang.classfile` và `AccessFlags` khi cần phân tích/biến đổi class file có cấu trúc bằng mã Java. Đây là Class-File API, không phải method `accessFlags()` trên đối tượng reflection.
3. Với hệ thống vẫn chạy JDK 17, có thể dùng `javap` hoặc thư viện bytecode tương thích (ví dụ ASM đúng phiên bản class file) khi thật sự cần bridge/synthetic flags và attributes ngoài khả năng `Modifier`.

Không dùng `getModifiers()` làm raw flag mask cho mọi `AccessFlag.Location`. Trường hợp có bit trùng nghĩa khác nhau, hoặc method của JVM có bridge/synthetic, chuyển đổi “chung” như vậy không bảo đảm chuẩn xác. Cũng không coi `AccessFlag.maskToAccessFlags` như một API kiểm tra quyền theo `SecurityManager` hay module access.

## 8. Quy trình chọn cách đọc flag

**Nếu chỉ kiểm tra modifier quen thuộc và còn hỗ trợ JDK 17:** dùng `Modifier.isPublic(field.getModifiers())`, `Modifier.isStatic(...)`, `Modifier.isFinal(...)`. Với bridge/varargs/synthetic, dùng API riêng như `isBridge()`/`isVarArgs()`/`isSynthetic()`.

**Nếu chạy JDK 20+ và muốn tên cờ rõ ràng:** dùng `field.accessFlags().contains(AccessFlag.VOLATILE)`, `method.accessFlags().contains(AccessFlag.BRIDGE)`. Đây là cách dễ tránh lỗi trùng mask.

**Nếu có số bit thô:** trước hết xác định `AccessFlag.Location` chính xác; tiếp theo xác định đời class file. Với JDK 25+ có thể dùng overload ba tham số để decode đúng phiên bản; ở các JDK trước đó cần kiểm tra giới hạn API đang có, cùng tài liệu JVMS nếu phân tích class file khác đời.

**Nếu cần cấu trúc record/sealed hoặc metadata không phải access flags:** hỏi API chuyên biệt (`isRecord()`, `isSealed()`) hoặc đọc class file đầy đủ. Đừng cố “sáng tạo” cờ không được định nghĩa.

**Nếu đọc field/method từ framework:** phân biệt “đã khai báo flag gì” với “có thể phản chiếu truy cập được không”. Chúng là hai câu hỏi độc lập.

## 9. Lỗi phổ biến và bài tập tự kiểm tra

1. **Gọi `accessFlags()` ở JDK 17:** không biên dịch; API được giới thiệu ở JDK 20.
2. **Đảo nghĩa `0x0040`:** field dùng `VOLATILE`, method dùng `BRIDGE`.
3. **Tin vào `getModifiers()` như toàn bộ raw class flags:** API thiên về modifier Java và không thay các API cờ/attribute đặc thù.
4. **Tưởng `sealed`, `record` là `AccessFlag`:** thực tế phải dùng metadata/API khác.
5. **Đoán flag chỉ từ JDK runtime:** class file đang xét có thể được build bằng `--release` cho đời cũ.
6. **Phụ thuộc thứ tự in `Set`:** đọc bằng `contains` hoặc so sánh tập, không so thứ tự.
7. **Hiểu `SYNTHETIC` là “bất kỳ thứ gì compiler tạo ra”:** JVMS đặt cờ/attribute với quy tắc cụ thể; chỉ dùng metadata được đọc từ class file/API, không đoán qua tên `$` hoặc pattern sinh mã.
8. **Quên sai khác giữa đọc metadata và truy cập private:** flag không mở quyền Reflection và không vượt quy tắc module.

Tự kiểm tra:

- `AccessFlag.TRANSIENT.mask() == AccessFlag.VARARGS.mask()` là `true`, vậy chỉ từ một số mask ta có kết luận được flag không? **Không**, cần location.
- `AccessFlag.STRICT.locations(ClassFileFormatVersion.RELEASE_17)` có chứa `METHOD` không? **Không**, vì `ACC_STRICT` chỉ áp dụng đến major version 60.
- `method.accessFlags().contains(AccessFlag.BRIDGE)` và `method.isBridge()` đều có thể sử dụng trên JDK 17? **Không**: `isBridge()` có từ trước, `accessFlags()` chỉ từ JDK 20.
- Class là `record` nhưng không có cờ `AccessFlag.RECORD` thì có mâu thuẫn không? **Không**: đặc tính record được biểu diễn ngoài tập access flags.

## 10. Tài liệu tham khảo chính thức

- [Oracle Javadoc Java 20 — AccessFlag (Since: 20)](https://docs.oracle.com/en/java/javase/20/docs/api/java.base/java/lang/reflect/AccessFlag.html)
- [Oracle Javadoc Java 21 — AccessFlag và Location](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessFlag.html)
- [Oracle Javadoc Java 21 — Class.accessFlags()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#accessFlags())
- [Oracle Javadoc Java 21 — Modifier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Modifier.html)
- [Oracle Javadoc Java 25 — AccessFlag và overload theo ClassFileFormatVersion](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessFlag.html)
- [Dev.java — Reading Modifiers](https://dev.java/learn/api/reflection-method-handles/reflection/modifiers/)
- [JEP 484 — Class-File API (JDK 24)](https://openjdk.org/jeps/484)
- [JEP 306 — Restore Always-Strict Floating-Point Semantics (JDK 17)](https://openjdk.org/jeps/306)
