# NoSuchMethodError và NoSuchFieldError do lệch phiên bản thư viện trong Java

Một chương trình Java có thể **biên dịch thành công** nhưng khi chạy lại phát sinh:

```text
java.lang.NoSuchMethodError: ...
java.lang.NoSuchFieldError: ...
```

Hai lỗi này thường xuất hiện khi **mã client đã được biên dịch với API của phiên bản thư viện A**, nhưng JVM khi thực thi lại nạp **định nghĩa class từ phiên bản B không còn thành viên đúng tên và descriptor**. Đây là lỗi **binary linkage / binary compatibility**, không đơn thuần là trình biên dịch “không tìm thấy method” trong source code.

Trong Java, bytecode lưu các **symbolic references** tới method/field trong *constant pool* của class caller. Khi liên kết tham chiếu, JVM cần tìm **đúng class và thành viên với tên cùng descriptor** mà bytecode đã ghi nhận. Nếu class được nạp có tồn tại nhưng method/field được tham chiếu **không còn khớp**, JVM có thể ném `NoSuchMethodError` hoặc `NoSuchFieldError`.

Bài thuộc nhóm **Lỗi thường gặp** trong Java core – classloader, tập trung vào: nguyên nhân do lệch phiên bản, cơ chế symbolic resolution, tên + descriptor (bao gồm kiểu trả về và kiểu field), ví dụ Java 17+ tái hiện **cả hai lỗi**, cách kiểm tra class thực sự được loader nào nạp, xử lý dependency conflict, đóng gói JAR/fat JAR, hệ plugin/classloader và chiến lược phòng ngừa.

## 1. Hiểu đúng loại lỗi: LinkageError, không phải Exception thông thường

Thứ bậc quan trọng:

```text
java.lang.Throwable
├── java.lang.Exception
│   └── java.lang.ReflectiveOperationException
│       └── java.lang.NoSuchMethodException
└── java.lang.Error
    └── java.lang.LinkageError
        ├── java.lang.IncompatibleClassChangeError
        │   ├── java.lang.NoSuchMethodError
        │   ├── java.lang.NoSuchFieldError
        │   ├── java.lang.IllegalAccessError
        │   ├── java.lang.AbstractMethodError
        │   └── ...
        ├── java.lang.NoClassDefFoundError
        ├── java.lang.VerifyError
        └── ...
```

`NoSuchMethodError` và `NoSuchFieldError` là **Error** thuộc họ **IncompatibleClassChangeError → LinkageError**, thường biểu hiện rằng các binary class được phối hợp khi chạy **không còn tương thích với nhau**.

**Không nhầm:**

- `NoSuchMethodException`: một API reflection như `Class.getMethod("m", ...)` không tìm ra member theo kiểu tìm kiếm reflection, và caller có thể xử lý checked exception này.
- `NoSuchMethodError`: bytecode đã compile tham chiếu method, nhưng khi JVM resolve runtime symbolic reference, method phù hợp không có.
- `NoSuchFieldException`: reflection `Class.getDeclaredField("x")` không tìm được field.
- `NoSuchFieldError`: bytecode có symbolic reference tới field, JVM field resolution không tìm được field phù hợp.

Trong production, không nên dùng `catch (NoSuchMethodError e) { /* bỏ qua */ }` như cách sửa lâu dài. Bắt lỗi có thể hữu ích trong ví dụ chẩn đoán; ứng dụng thật cần **sửa dependency/runtime classpath và khôi phục binary compatibility**.

## 2. Vì sao source compile được mà runtime vẫn thất bại?

Hãy tưởng tượng có ba artifact:

```text
vendor-api-v1.jar      client.jar       vendor-api-v2.jar
    |                     |                    |
    |  compile dependency |                    |
    +-------------------->|                    |
                          | bytecode client     |
                          | lưu method/field    |
                          | v1 symbols          |
                          |                    |
                          +------------------->| Runtime classloader
                                               | nạp Vendor từ v2
                                               |
                                               v
                                   Method/field của v1 không tồn tại
                                   với đúng descriptor trong v2
                                               |
                                               v
                                       LinkageError ở runtime
```

Lúc biên dịch, `javac` nhìn thấy `lib.Vendor.format()` và `lib.Vendor.LEVEL` trong v1. Trình biên dịch tạo bytecode và constant pool ghi rõ **symbolic references** mà các lệnh gọi sẽ sử dụng. Sau đó build hoặc deployment **không bắt buộc mang theo đúng binary v1**: có thể thư viện bị nâng cấp, hạ cấp, loại bởi dependency mediation hoặc bị JAR khác che khuất trên classpath.

Nếu chỉ chạy lại **client.class cũ** với **vendor-api-v2.jar**, JVM không “biên dịch lại” caller để tự thay `Vendor.format()` bằng tên method mới, và cũng không tự xem một field khác như replacement.

Kết quả là:

- **Compile-time API:** bộ thành viên mà client đã compile against.
- **Runtime definition:** bộ thành viên của class mà JVM **thực sự nạp**.
- **Linkage:** JVM cố nối symbolic reference trong client với runtime definition.
- **Mismatch:** thành viên không tồn tại đúng tên/descriptor → lỗi phù hợp.

Điểm này đặc biệt quan trọng trong ứng dụng đa module, plugin, application server, Gradle/Maven nhiều dependencies và các thư viện có transitive dependencies.

## 3. Method resolution thực sự tìm cái gì?

Một method symbolic reference trong class file lưu:

1. **Class/interface owner** theo binary name.
2. **Method name**, ví dụ `format`.
3. **Method descriptor** gồm **kiểu các tham số** và **kiểu trả về**.

Ví dụ Java:

```java
public static String format()
```

được biểu diễn trong JVM descriptor (không có tham số, trả `java.lang.String`):

```text
format:()Ljava/lang/String;
```

Một overload:

```java
public static int format(int n)
```

sử dụng descriptor:

```text
format:(I)I
```

Các ký hiệu thường gặp:

| Java type | JVM field descriptor |
| --- | --- |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `void` (chỉ kết quả method) | `V` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |

**Return type cũng có trong JVM method descriptor**, mặc dù một số quy tắc source-level về overloading trong Java không cho phân biệt method chỉ dựa kiểu trả về. Vì thế một thay đổi return type có thể phá binary linkage dù method name và danh sách tham số nhìn bằng mắt vẫn giống.

Theo JVMS 17 `5.4.3.3, method resolution dùng tên và descriptor của reference. Nếu lookup thất bại, `NoSuchMethodError` có thể được ném. Tuy nhiên method có thể vẫn được tìm ở class cha hoặc interface theo các quy tắc resolution; **không phải cứ một class xóa declaration cục bộ thì mọi client lập tức lỗi** nếu vẫn có inherited method tương thích.

### Thay đổi nào thường dẫn tới NoSuchMethodError?

| API mà client đã compile | API runtime khác | Nguy cơ |
| --- | --- | --- |
| `String format()` | Xóa `format()` | Cao: reference cũ không resolve được |
| `String format()` | Đổi tên thành `describe()` | Cao: tên khác |
| `String format()` | Đổi thành `String format(String mode)` | Cao: parameter descriptor khác |
| `String format()` | Đổi thành `Object format()` | Có thể NoSuchMethodError do **return descriptor khác** |
| `Vendor()` public no-arg | Chỉ còn constructor `Vendor(int)` | Có thể `NoSuchMethodError: <init>()V` |
| `format()` instance | `format()` static cùng descriptor | Có thể **IncompatibleClassChangeError**, không mặc nhiên là NoSuchMethodError |
| Method còn nhưng giảm visibility | Ví dụ public thành private | Có thể `IllegalAccessError` thay vì NoSuchMethodError |

Đừng gộp mọi sửa API thành một lỗi duy nhất: JVM phân biệt **không tìm được member**, **không có quyền truy cập**, và **sai loại static/instance**.

## 4. Field resolution và vì sao kiểu field có ý nghĩa

Tương tự, symbolic reference tới field lưu:

1. Owner class/interface.
2. Field name.
3. **Field descriptor** = kiểu của field.

Ví dụ:

```java
public static int LEVEL = 7;
```

tạo field reference:

```text
lib/Vendor.LEVEL:I
```

Nếu runtime có `public static long LEVEL = 7L;`, tên `LEVEL` vẫn tồn tại nhưng **descriptor đổi từ `I` sang `J`**. Reference cũ `LEVEL:I` có thể thất bại với `NoSuchFieldError` vì JVM đang tìm một field **đúng tên và descriptor**, không chỉ “tên gần giống”.

Theo JVMS 17 `5.4.3.2, lookup xét class/interface owner, các superinterfaces/superclasses theo quy tắc rồi nếu không tìm ra field với name+descriptor thì ném `NoSuchFieldError`. Có những thay đổi cấu trúc vẫn tương thích nhờ inherited field; cần xét binary thực thay vì đoán từ source diff.

### Thay đổi field và loại lỗi có thể xảy ra

| V1 compile API | V2 runtime API | Nhận xét |
| --- | --- | --- |
| `public static int LEVEL` | Xóa `LEVEL` | Thường dẫn tới `NoSuchFieldError` |
| `public int level` | Đổi tên thành `count` | Reference cũ không thấy tên |
| `public static int LEVEL` | `public static long LEVEL` | Descriptor khác; có thể `NoSuchFieldError` |
| `public int count` | `public static int count` | Opcode field access không phù hợp; có thể `IncompatibleClassChangeError` |
| `public int count` | `private int count` | Có thể `IllegalAccessError` |
| `public static final int VERSION = 1` | Đổi giá trị thành 2 | **Có thể không lỗi** do constant đã inline vào client; vẫn thấy giá trị cũ |

**Trường hợp `static final` compile-time constant** rất đặc biệt: nếu field là *constant variable* (`static final` primitive hoặc `String` với constant expression), `javac` có thể **inline giá trị** vào client thay vì phát lệnh `getstatic`. Khi thay/loại field ở runtime, client cũ có thể **không phát `NoSuchFieldError`** vì bytecode **không còn symbolic field reference** tại chỗ sử dụng ấy, nhưng giá trị lại bị cũ.

Đó là lý do ví dụ tái hiện chính xác ở phần tiếp theo dùng **`public static int LEVEL` không final**, để buộc client bytecode có `getstatic`.

## 5. Ví dụ Java 17+ tái hiện cả hai lỗi bằng v1/v2

Ví dụ có ba nhóm source độc lập: thư viện v1, thư viện v2, và client chỉ compile với v1. **Client KHÔNG được biên dịch lại khi chuyển runtime sang v2** — đây là điều kiện tạo lỗi binary mismatch.

### 5.1 Cấu trúc

```text
linkage-demo/
├── v1-src/
│   └── lib/Vendor.java
├── v2-src/
│   └── lib/Vendor.java
├── client-src/
│   └── app/Client.java
├── v1-classes/          (output thư viện v1)
├── v2-classes/          (output thư viện v2)
└── client-classes/      (output client compile against v1)
```

Tạo các output directories trước khi chạy. Không đặt cùng lúc hai file `lib/Vendor.java` vào **một source root**, vì chúng là **hai phiên bản khác nhau của cùng binary class name**.

### 5.2 Thư viện v1

File `v1-src/lib/Vendor.java`:

```java
package lib;

public final class Vendor {
    public static int LEVEL = 7; // Non-final: client phải dùng getstatic.

    public static String format() {
        return "v1 format";
    }
}
```

Client sẽ compile thành công vì v1 có cả method `format()` và field `LEVEL`.

### 5.3 Thư viện v2 không tương thích

File `v2-src/lib/Vendor.java`:

```java
package lib;

public final class Vendor {
    public static int REVISION = 2;

    public static String describe() {
        return "v2 describe";
    }
}
```

Class **`lib.Vendor` vẫn tồn tại**, nhưng hai thành viên mà client đã sử dụng bị thay tên: `format()` không còn, và `LEVEL` không còn. Nếu compile client trực tiếp với v2, `javac` sẽ báo không tìm thấy symbols; vấn đề ở đây là **client.class đã được compile trước đó với v1** nên lỗi chỉ xuất hiện khi chạy.

### 5.4 Client compile với v1

File `client-src/app/Client.java`:

```java
package app;

import lib.Vendor;

public class Client {
    public static void main(String[] args) {
        try {
            System.out.println("method=" + Vendor.format());
        } catch (NoSuchMethodError error) {
            System.out.println("method link="
                    + error.getClass().getSimpleName());
        }

        try {
            System.out.println("field=" + Vendor.LEVEL);
        } catch (NoSuchFieldError error) {
            System.out.println("field link="
                    + error.getClass().getSimpleName());
        }

        System.out.println("actual loaded class="
                + Vendor.class.getName());
    }
}
```

**Chỉ để học:** hai `catch` được cố ý đặt để chương trình tiếp tục sau mỗi lỗi và chứng minh cả hai lỗi độc lập. Trong ứng dụng thật, lỗi linkage cho thấy dependency graph không phù hợp; cần fail-fast và sửa artifact, không dùng `catch(Error)` để coi trạng thái là bình thường.

### 5.5 Compile cả ba nhóm theo thứ tự đúng

Dùng JDK 17+ từ thư mục `linkage-demo`:

```bash
javac --release 17 -d v1-classes v1-src/lib/Vendor.java
javac --release 17 -cp v1-classes -d client-classes client-src/app/Client.java
javac --release 17 -d v2-classes v2-src/lib/Vendor.java
```

Thứ tự có ý nghĩa:

1. Compile v1 tạo class chứa API mà client cần.
2. Compile client **chỉ với v1**. Constant pool của `app.Client` ghi references tới v1 API.
3. Compile v2 vào output khác, không đụng `client-classes` đã tạo.
4. Chỉ đổi classpath **khi chạy**, không recompile client.

### 5.6 Chạy với v1: binary phù hợp

**Windows:**

```bash
java -cp "client-classes;v1-classes" app.Client
```

**Linux/macOS:**

```bash
java -cp "client-classes:v1-classes" app.Client
```

Stdout **đã kiểm chứng bằng `javac --release 17` và JVM**:

```text
method=v1 format
field=7
actual loaded class=lib.Vendor
```

Client và runtime đang dùng cùng API v1 nên cả hai symbolic references resolve thành công.

### 5.7 Chạy client cũ nhưng chỉ với v2: tái hiện lỗi

**Windows:**

```bash
java -cp "client-classes;v2-classes" app.Client
```

**Linux/macOS:**

```bash
java -cp "client-classes:v2-classes" app.Client
```

Stdout **đã kiểm chứng**:

```text
method link=NoSuchMethodError
field link=NoSuchFieldError
actual loaded class=lib.Vendor
```

Cách diễn giải:

- `NoSuchMethodError`: caller còn reference tới `lib.Vendor.format:()Ljava/lang/String;`, nhưng v2 không định nghĩa member ấy.
- `NoSuchFieldError`: caller còn reference tới `lib.Vendor.LEVEL:I`, nhưng v2 không định nghĩa field đó.
- `actual loaded class=lib.Vendor`: binary name vẫn giống, cho thấy **tìm được class không bảo đảm tìm được method/field cần thiết**. Dòng này **không chứng minh file v1/v2 nào đã được nạp**, vì cả hai có cùng tên — để xem nguồn chính xác phải kiểm tra CodeSource/class-loading diagnostics.

Chính sự khác nhau giữa **thành công khi dùng v1** và **hai lỗi khi chỉ thay runtime bằng v2** làm rõ nguồn gốc **binary incompatibility**.

## 6. Dùng javap xác nhận bytecode đang cần descriptor nào

Tool `javap` cho phép đọc constant pool và bytecode của **client.class cũ**:

```bash
javap -classpath client-classes -c -verbose app.Client
```

Trong kết quả ví dụ đã xác minh, các đoạn quan trọng gồm:

```text
Methodref ... // lib/Vendor.format:()Ljava/lang/String;
Fieldref  ... // lib/Vendor.LEVEL:I
invokestatic ... // Method lib/Vendor.format:()Ljava/lang/String;
getstatic    ... // Field lib/Vendor.LEVEL:I
```

`invokestatic` được phát vì client compile method tĩnh. `getstatic` được phát vì client đọc field tĩnh **không phải compile-time constant**. Các entry trong constant pool ghi rõ **owner/name/descriptor**.

Sau đó xem **bản runtime**:

```bash
javap -classpath v2-classes -public lib.Vendor
```

Bản v2 có `REVISION` và `describe()`, không có `format()`/`LEVEL`. Trên classpath production, thay `v2-classes` bằng đường tới **JAR được JVM thực sự nạp** (không phải chỉ dependency mà IDE hiển thị).

### Vì sao không chỉ xem source?

Source hiện tại có thể là phiên bản khác so với:

- Class files đã được compile từ tuần trước.
- Artifact trong `build/libs` hay `target` của một module khác.
- JAR từ Maven/Gradle local cache hoặc repository.
- JAR được copy vào server `lib`, plugin folder hoặc Docker image.
- Class bị shading/relocation hoặc class loader che khuất.

**Chẩn đoán linkage phải nhìn bytecode caller và binary runtime**, không chỉ code source đang mở.

## 7. ClassLoader chọn bản class runtime nào?

JVM resolve class symbolic reference thông qua **defining loader của class caller và quy tắc class loading liên quan**, không bằng cách “tìm tất cả JAR rồi tự chọn API phù hợp với phương thức”.

Trên application classpath thông thường, cùng binary name xuất hiện trong hai JAR có thể dẫn tới tình huống **JAR đứng trước hoặc loader policy xác định class được định nghĩa trước**, khiến client nạp bản không kỳ vọng. Với custom loader, **parent-first/child-first**, module mapping, code source và class identity đều ảnh hưởng.

Ví dụ:

```text
Client.class (compiled with Vendor v2 API)
         |
         v
Application loader
   |
   +-- old-v1.jar chứa lib/Vendor.class
   +-- new-v2.jar chứa lib/Vendor.class
         |
         v
JVM có thể nạp phiên bản được tìm trước
         |
         v
NoSuchMethodError / NoSuchFieldError
```

**Không có cơ chế tự động “method thiếu thì thử JAR khác”.** Một khi `lib.Vendor` đã được định nghĩa bởi loader tương ứng, nó có identity và members xác định; JVM không chọn file thứ hai chỉ vì symbolic reference tới method không resolve.

Nếu dùng plugin loader khác nhau, cùng tên `lib.Vendor` có thể được hai **defining class loaders** độc lập định nghĩa thành hai runtime types. Khi client và provider nói chuyện qua API chung, mismatch giữa class loaders có thể gây thêm `ClassCastException`, `LinkageError`/loader constraint violation, ngoài các versioning errors đang nghiên cứu.

### In code source và defining loader

Một đoạn debug đặt ở code thực sự nhìn thấy `lib.Vendor`:

```java
Class<?> type = lib.Vendor.class;

System.out.println("name=" + type.getName());
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());

java.security.ProtectionDomain pd = type.getProtectionDomain();
java.security.CodeSource cs = (pd == null) ? null : pd.getCodeSource();

System.out.println("source="
        + (cs == null ? "<unknown>" : cs.getLocation()));
```

Đây là **đoạn minh họa trong method Java**, không có stdout cố định vì loader/module/path thay đổi theo runtime. `CodeSource` có thể `null` (đặc biệt với platform classes, custom loaders hoặc policy cụ thể); không được khẳng định mọi class đều có file URL.

Điểm cần xem nhất là: **loader nào define class, module nào chứa class, CodeSource nào, và JAR/runtime artifact có API descriptor nào**.

### JVM class loading logs

Với HotSpot Java 17+:

```bash
java -Xlog:class+load=info -cp "client-classes;v2-classes" app.Client
```

Lệnh này minh họa Windows; Linux/macOS đổi `;` thành `:`. JVM ghi thông tin class loading; tìm `lib.Vendor` trong log để biết **nguồn mà VM đã nạp**, tùy format/version. Trong production nên dùng output log có kiểm soát vì `class+load=info` có thể sinh nhiều dòng.

Một lựa chọn phổ biến khác để kiểm tra class artifacts là lệnh:

```bash
jar --list --file path/to/vendor-api.jar
```

Kiểm tra đúng `lib/Vendor.class` và không có phiên bản duplicate không mong muốn.

## 8. Không chỉ đổi tên: đổi kiểu trả về hoặc kiểu field cũng phá binary API

Một sự cố rất thực tế:

**V1:**

```java
package lib;
public class Settings {
    public String mode() { return "safe"; }
    public int timeout = 10;
}
```

**V2:**

```java
package lib;
public class Settings {
    public CharSequence mode() { return "safe"; }
    public long timeout = 10;
}
```

Hai đoạn là **hai phiên bản của cùng `lib.Settings`**, không compile cùng lúc trong cùng source root. Source-level code kiểu:

```java
System.out.println(settings.mode());
System.out.println(settings.timeout);
```

có thể có vẻ vẫn gần giống, nhưng **JVM references đã đổi**:

```text
V1 method: lib/Settings.mode:()Ljava/lang/String;
V2 method: lib/Settings.mode:()Ljava/lang/CharSequence;

V1 field:  lib/Settings.timeout:I
V2 field:  lib/Settings.timeout:J
```

Đối với client đã compile với v1, việc chỉ thay runtime `Settings.class` bằng v2 **có thể** tạo `NoSuchMethodError` và `NoSuchFieldError` khi reference cũ không còn được tìm trong class hierarchy.

Một ngoại lệ cần hiểu: compiler có thể tạo **bridge methods** trong một số tình huống generics/covariant overrides để bảo toàn method descriptors, và JVM resolution có lookup trong hierarchy. Vì vậy **không kết luận chắc từ Java source diff**; phải kiểm tra bytecode thật bằng `javap -s -p` hoặc `javap -verbose`.

## 9. Tại sao lỗi có thể chỉ xuất hiện khi một code path được chạy?

JVM phân biệt loading, linking (verification/preparation/resolution) và initialization. Việc resolution symbolic references có thể được JVM thực hiện ở những thời điểm khác nhau phù hợp đặc tả, và nhiều lỗi chỉ trở nên quan sát được khi **tham chiếu cụ thể được sử dụng**.

Ví dụ:

```java
if (featureEnabled) {
    lib.Vendor.format();
}
```

Đây là đoạn minh họa, giả định `featureEnabled` được xác định và client đã compile với API chứa `format()`.

- Nếu code path không chạm tới method, ứng dụng có thể chạy được một thời gian.
- Khi thực hiện reference bị thiếu, lỗi liên kết có thể xảy ra.
- JVM có thể resolve một số tham chiếu sớm, nhưng các lỗi resolution phải được quan sát theo các giới hạn đặc tả tương ứng; không nên dựa vào một timestamp duy nhất cho mọi JVM/JIT mode.

Đây là lý do integration tests chỉ gọi happy path rất hẹp có thể **không phát hiện dependency mismatch**. Thư viện vẫn cần được test trên các chức năng/entrypoints thật, kể cả optional features được triển khai sau.

**Đừng nhầm lỗi được phát hiện muộn với lỗi “method tự biến mất khi chương trình đang chạy”.** Trong JVM, bytecode caller vẫn có reference cũ; chỉ khi resolution xảy ra ta mới nhìn thấy bất tương thích có sẵn.

## 10. Phân biệt với lỗi classloading và access khác

| Lỗi | Nguyên nhân điển hình | Khác gì với hai lỗi trọng tâm? |
| --- | --- | --- |
| `ClassNotFoundException` | Loader được yêu cầu tìm binary class name nhưng không thấy | Thường là checked exception từ lookup API như `loadClass` |
| `NoClassDefFoundError` | VM cần class mà definition không sẵn có hoặc initialization trước đó lỗi | Class/dependency không khả dụng; không phải “thành viên thiếu” |
| `NoSuchMethodError` | Method symbolic reference không được resolve | Owner class có thể đã được nạp, nhưng method name+descriptor không khớp |
| `NoSuchFieldError` | Field symbolic reference không được resolve | Class có thể tồn tại nhưng field name+descriptor không khớp |
| `IllegalAccessError` | Member/class tồn tại nhưng runtime access check không cho phép | Không nhất thiết member biến mất |
| `IncompatibleClassChangeError` | Thay đổi phân loại class/member, ví dụ static ↔ instance sai kỳ vọng | Có thể member tên+descriptor vẫn có, nhưng opcode không phù hợp |
| `AbstractMethodError` | Runtime invocation chọn method abstract/thiếu concrete implementation phù hợp trong một số tình huống | Khác `NoSuchMethodError` lúc resolution |
| `ClassCastException` | Runtime types không tương thích, có thể do hai loader define cùng binary name | Type identity/casting khác field/method resolution |
| `VerifyError` | Class bytecode không qua verification | Vấn đề bytecode validity, không nhất thiết version API |

Không nên viết generic handler bắt `Throwable` rồi đổi tất cả thành thông báo “Class not found”: thông tin class owner, method/field name và descriptor trong stack trace là chìa khóa xác định dependency sai.

## 11. Những nguyên nhân lệch phiên bản thường gặp trong thực tế

### 11.1 Transitive dependency conflict

App phụ thuộc thư viện A và B; A compile với `vendor-core:2.x` trong khi B kéo `vendor-core:1.x`. Maven/Gradle dependency resolution có thể chọn một bản cụ thể theo các quy tắc build, và artifact runtime được chọn có thể **không giống bản mà một dependency đã biên dịch against**.

```text
app
├── feature-a -> vendor-core v2
└── feature-b -> vendor-core v1
                     |
                     v
                runtime chọn 1 version
                     |
                     v
        client binary của nhánh còn lại có thể không tương thích
```

Không có công thức luôn đúng “chọn version cao hơn là hết lỗi”: API v2 có thể xóa thành viên v1 hoặc thư viện v1 không hỗ trợ runtime mới. Cần chọn **tập versions tương thích** và kiểm chứng thực tế.

### 11.2 Duplicated JAR trên classpath/server

`app/lib/vendor-v2.jar` và `server/lib/vendor-v1.jar` cùng có `lib.Vendor`. App classloader có thể delegate parent và nhận class v1 từ server trước khi tự tìm v2. Triệu chứng giống “tôi đã thêm v2 vào app mà vẫn lỗi”.

### 11.3 Shaded/fat JAR đóng gói bản cũ

Build tool tạo uber-JAR nhưng merge classes/resources sai, lưu `lib/Vendor.class` cũ mặc dù dependency metadata hiển thị v2. Cần kiểm tra **artifact cuối thực sự chạy**, không chỉ declared dependencies.

### 11.4 IDE/build cache hoặc incremental build không sạch

Một module đã compile lại v2, nhưng client module khác vẫn dùng class file cũ. Runtime lấy binary mới nhưng caller bytecode chưa recompile, gây mismatch. Clean rebuild cần đi cùng kiểm tra dependency graph; không phải lúc nào “xóa cache” cũng sửa xung đột dependency thực.

### 11.5 Plugin/shared framework version skew

Plugin compile với host SDK v2 nhưng container runtime chỉ export shared API v1. Vì host parent loader define shared API, plugin dù chứa JAR v2 vẫn có thể delegate tới v1 và gặp `NoSuchMethodError`.

### 11.6 Deployment artifact còn cũ

Server, Docker image hoặc classpath script đang tham chiếu JAR cũ, trong khi developer đang xem file mới trên máy khác. Nhìn `CodeSource` và build artifact hash/version là cần thiết.

## 12. Quy trình debug có thứ tự, tránh sửa mò

Khi stack trace có `NoSuchMethodError` hoặc `NoSuchFieldError`, làm theo các bước:

**Bước 1 — Ghi nguyên lỗi và frame caller.**

Ví dụ giả định:

```text
java.lang.NoSuchMethodError:
  'java.lang.String lib.Vendor.format()'
  at app.Client.main(Client.java:7)
```

Từ thông điệp và frame, biết **caller** là `app.Client`, owner là `lib.Vendor`, method kỳ vọng là `format()` trả `String`. Field error tương tự có thể ghi tên field và kiểu kỳ vọng. Format thông báo **không cố định** giữa các phiên bản JVM nên đừng parse string cứng làm logic ứng dụng.

**Bước 2 — Tìm class thực sự được runtime nạp.**

In:

```java
System.out.println(lib.Vendor.class.getClassLoader());
System.out.println(lib.Vendor.class.getModule());
System.out.println(lib.Vendor.class.getProtectionDomain()
        .getCodeSource());
```

Đoạn minh họa cần xử lý trường hợp protection domain/code source null khi triển khai thực; nếu class cần điều tra không load được qua source, dùng `-Xlog:class+load=info` hoặc debugger.

**Bước 3 — Xem method/field đang có trong class runtime.**

```bash
javap -classpath path/to/runtime-vendor.jar -p -s lib.Vendor
```

Với JAR có đúng tên class, `javap` cho các descriptor thay vì chỉ Java signatures đẹp mắt.

**Bước 4 — Xem bytecode caller compile against gì.**

```bash
javap -classpath path/to/client.jar -verbose -c app.Client
```

Tìm `Methodref`/`Fieldref` và opcode. So sánh **owner + name + descriptor** với runtime API.

**Bước 5 — Tìm dependency version thực tế trong build.**

- Maven: `mvn dependency:tree`, kiểm tra scoped/transitive/excluded versions.
- Gradle: `./gradlew dependencies --configuration runtimeClasspath`, hoặc `dependencyInsight` cho module nghi ngờ (Windows Gradle wrapper là `gradlew.bat`).
- Nếu plugin/container: xem cả **host/server libs và plugin classpaths**, không chỉ một build file.

**Bước 6 — Sửa dependency constraints và artifact.**

Chọn một API version được **tất cả caller binaries** hỗ trợ. Nếu API breaking change là chủ đích, rebuild các consumers với phiên bản mới và sửa code. Loại duplicate JAR/parent conflicts. Nếu cần hai versions thật sự, cô lập bằng classloaders/process và chỉ chia sẻ API ổn định.

**Bước 7 — Clean build, redeploy và chạy lại cùng đường runtime.**

Không chỉ reload IDE. Xóa artifact triển khai cũ có chủ đích, build lại module client nếu API thay đổi, kiểm tra container image/server library placement và chạy integration tests bao gồm code path từng lỗi.

### Checklist log tối thiểu khi hỗ trợ production

```text
Error type: NoSuchMethodError / NoSuchFieldError
Caller class and stack frame
Symbolic owner/name/descriptor
Defining loader of caller
Defining loader of owner
Module/layer if named modules used
Owner CodeSource / actual JAR
Classpath/module-path and deployment version
Actual method/field descriptors (javap)
Build dependency graph
```

Thông tin này thường đủ để phân biệt “JAR runtime quá cũ”, “JAR runtime quá mới và xóa API”, “parent loader che bản đúng” và “client.class chưa được rebuild”.

## 13. Cách sửa đúng và cách không nên làm

| Cách làm | Đánh giá |
| --- | --- |
| Đồng bộ phiên bản compiler/runtime dependencies | **Nên**, nhưng phải kiểm tra binary compatibility thực |
| Rebuild client khi dependency API thay đổi | **Nên**, nhất là breaking changes |
| Loại duplicate JAR hoặc cấu hình classloader policy hợp lý | **Nên**, dựa trên CodeSource/loader đã xác minh |
| Dùng dependency management/constraints/locking | **Nên** để build tái lập |
| Thêm compatibility overload/deprecated method giữ descriptor cũ | **Có ích** khi tác giả thư viện cần duy trì binary compatibility |
| Duy trì adapter/bridge tại API boundary | **Có thể**, nếu thiết kế rõ version contract |
| Catch rồi bỏ qua `NoSuchMethodError` | **Không nên** trong nghiệp vụ bình thường |
| Cứ thêm JAR v2 ở cuối classpath khi v1 đã được parent nạp | **Không đủ**; loader có thể vẫn chọn v1 |
| Đổi TCCL và nghĩ `Class.forName(String)`/bytecode linkage đều sẽ dùng loader mới | **Không đúng**; API lựa chọn loader khác nhau |
| Gọi `System.gc()`/`URLClassLoader.close()` để “làm method mới xuất hiện” | **Không đúng**; loader/class đã định nghĩa không tự thay API |
| Xóa toàn bộ cache một cách mù quáng | **Không nên**; xác định nguồn conflict rồi sửa |
| Dựa vào thứ tự classpath không được kiểm soát | **Rủi ro**; ưu tiên một version được kiểm soát và kiểm chứng |

Nếu bạn phát hành thư viện:

- Giữ method/field đã public mà consumers đang sử dụng, hoặc cung cấp **binary-compatible bridge/overload** khi có thể.
- Khi thay tham số/return/field type, đánh giá tác động tới *bytecode descriptors*, không chỉ Java source compilation.
- Tuân thủ versioning policy rõ, công bố breaking changes và runtime requirements.
- Test bằng **binaries được compile với version trước** chạy với version mới để phát hiện lỗi liên kết.
- Phân biệt **source compatibility** với **binary compatibility**: có thay đổi khiến source recompilation thành công nhưng binary cũ không chạy, và ngược lại.
- Không làm biến mất public no-arg constructor đã được caller compile against một cách tình cờ.

## 14. Các tình huống nâng cao: method signature và field constants

### 14.1 Thêm overload mới thường không phá binary cũ

Nếu v1:

```java
public String convert(int value)
```

và v2 vẫn giữ method ấy rồi **thêm**:

```java
public String convert(long value)
```

thì symbolic reference cũ `convert:(I)Ljava/lang/String;` vẫn có thể resolve bình thường. “Thêm overload” nói chung khác hẳn “đổi tham số của method cũ”.

Nếu thay hẳn method v1 bằng overload nhận `long` và xóa bản nhận `int`, client cũ không tự chuyển descriptor; có thể `NoSuchMethodError`.

### 14.2 Đổi instance method thành static: không nhất thiết NoSuchMethodError

Client v1 có `invokevirtual` tới instance method, runtime v2 có cùng tên/descriptor nhưng method thành static: lỗi điển hình là **`IncompatibleClassChangeError`** do opcode yêu cầu instance method nhưng runtime member static. Nên đọc opcode `invokevirtual` / `invokestatic` và error message, không ép mọi linkage về method missing.

### 14.3 Thay field static thành instance: không nhất thiết NoSuchFieldError

Client v1 có `getstatic` mà runtime field mới là instance, JVM có thể báo **`IncompatibleClassChangeError`**. Nếu field đổi cả kiểu dữ liệu, `NoSuchFieldError` có thể xảy ra trước ở giai đoạn lookup. Thứ tự phụ thuộc tham chiếu và loại thay đổi thực tế.

### 14.4 Compile-time constants có thể tạo “lỗi giá trị cũ” âm thầm

V1:

```java
public static final int BUILD_ID = 101;
```

v2:

```java
public static final int BUILD_ID = 202;
```

Client đã compile với v1 thường chứa literal `101` do constant inlining. Khi runtime dùng v2, client có thể **vẫn in 101 mà không ném `NoSuchFieldError`**. Cần recompile consumer để cập nhật giá trị hoặc tránh dựa vào public constant variables khi giá trị được kỳ vọng thay đổi runtime.

Đối với `static final` object không phải compile-time constant (ví dụ một `List` hay expression không phải constant expression), client có thể vẫn phát field reference và chịu linkage rules bình thường.

### 14.5 Generics, erasure và bridge methods

Method Java generic:

```java
public java.util.List<String> items()
```

thường có erased JVM return descriptor `()Ljava/util/List;` (thông tin generic được lưu thêm qua Signature attribute). Đổi generic argument từ `String` sang `Object` có thể không đổi **erased descriptor** và vì vậy không nhất thiết phát `NoSuchMethodError`, dù type-safety/behavior có thể gặp vấn đề.

Đổi raw return type, parameter erasure hoặc bridge methods lại có thể ảnh hưởng descriptors. Khi nghi mismatch, **`javap -s -p` là nguồn kiểm tra chính xác**, không suy từ angle brackets trong source.

## 15. Lưu ý khi triển khai plugin và custom classloader

Trong kiến trúc plugin, host có thể đã nạp SDK/API version cũ qua **parent loader**. Dù plugin JAR chứa SDK mới, child loader sử dụng **parent-first delegation** có thể lấy class API từ host. Khi plugin code được compile với API mới gọi method thiếu trên API cũ, nó phát `NoSuchMethodError`.

```text
Host/System loader: api.Shared v1
       ^
       | parent-first
Plugin loader:
   - plugin.Entry compiled against api.Shared v2
   - plugin.jar có thể chứa api.Shared v2
       |
       v
Runtime plugin.Entry gọi api.Shared.newMethod()
       |
       v
api.Shared v1 do parent define -> NoSuchMethodError
```

Hướng xử lý:

1. **Xác định host-plugin API compatibility matrix.** Plugin phải khai báo minimum host API version và được kiểm tra trước khi load.
2. **Giữ shared API ở loader chung** để host và plugin dùng cùng runtime types. Không tùy tiện “child-first cho cả `api.*`” vì có thể tạo bản sao API gây `ClassCastException`/loader constraints.
3. **Cô lập implementation dependencies** khi chúng không thuộc shared contract, tránh parent che phiên bản plugin cần.
4. **Fail fast ở bootstrap:** kiểm tra version/required capabilities, thay vì đợi method đặc biệt được gọi sau nhiều giờ.
5. **Không hot-replace JAR dưới một loader đang sống** rồi kỳ vọng class definition và method table đổi theo. Dùng deployment/loader mới theo lifecycle đúng nếu cần reload.
6. **Nếu dùng JPMS**, xem module graph và exports/opens ngoài class loading. `IllegalAccessError` có thể là module access, không phải version mismatch.
7. **In class loader của class owner**, không chỉ của plugin entrypoint: cùng plugin thread vẫn có thể gọi API do parent định nghĩa.

Một tình huống khác: ServiceLoader provider được nạp qua TCCL plugin đúng nhưng nó gọi host API thiếu method. **Service discovery thành công không đảm bảo provider đã tương thích binary** với host class definitions. Cần chạy integration contract tests.

## 16. Chẩn đoán bằng dependency graph và artifact consistency

Trước khi sửa, dựng lại đường từ client binary tới runtime class:

```text
Client.class
    |
    | constant_pool Methodref/Fieldref
    v
Required Owner + Name + Descriptor
    |
    | JVM class resolution
    v
Actual Class<?> (defining loader, module, CodeSource)
    |
    | field/method resolution
    v
Runtime available members
    |
    +-- exact match -----------> OK (nếu access/opcode hợp lệ)
    |
    +-- missing match ---------> NoSuchMethodError / NoSuchFieldError
    |
    +-- access mismatch -------> IllegalAccessError
    |
    +-- static mismatch -------> IncompatibleClassChangeError
```

Một khi xác định được **exact runtime JAR**, so manifest/version/checksum với build manifest. Đừng chỉ so tên file: hai artifact có cùng `vendor.jar` nhưng bytecode khác nhau, và một artifact “version 2.1” có thể được repackaged/shaded hoặc có class cũ.

**Build reproducibility**:

- Quản lý dependency versions tập trung và khóa versions được release.
- Không dùng wildcard/uncontrolled directories khi server/plugin cần API riêng.
- Trong CI, kiểm tra dependency conflicts và chạy test bằng **đúng artifact/JRE/runtime classpath** giống production.
- Đối với thư viện công bố API, cân nhắc công cụ so binary APIs giữa releases và chạy old-client-binary compatibility tests.
- Đảm bảo container/server restart hoặc redeploy làm runtime dùng artifact mới, tránh classloaders cũ còn tồn tại dưới dạng plugin deployment khác.

## 17. Tự kiểm tra có đáp án

**Câu 1.** Client dùng `Vendor.format()`, đã biên dịch với v1; runtime lại nạp `Vendor` v2 không có method ấy. Vì sao code compile thành công?

**Đáp án:** `javac` chỉ thấy API v1 lúc compile; runtime class definition v2 khác. JVM link symbolic method reference cũ và không thấy name+descriptor nên `NoSuchMethodError`.

**Câu 2.** `NoSuchMethodException` có giống `NoSuchMethodError` không?

**Đáp án:** Không. `NoSuchMethodException` là checked reflection exception; `NoSuchMethodError` là `LinkageError` khi bytecode symbolic method reference không resolve được.

**Câu 3.** Nếu runtime `Vendor` vẫn có `format()` nhưng trả `Object` thay vì `String`, có chắc không lỗi không?

**Đáp án:** Không. JVM method descriptor gồm return type; client đòi `()Ljava/lang/String;` nhưng bản runtime chỉ có `()Ljava/lang/Object;` có thể bị `NoSuchMethodError`, trừ các điều kiện inheritance/bridge tương thích cụ thể.

**Câu 4.** Vì sao đổi `int LEVEL` sang `long LEVEL` có thể phát `NoSuchFieldError`?

**Đáp án:** Field reference gồm name + type descriptor; `LEVEL:I` khác `LEVEL:J`.

**Câu 5.** Nếu đổi instance field sang static field cùng tên/kiểu, lỗi nào có thể xảy ra?

**Đáp án:** `IncompatibleClassChangeError` do opcode `getfield`/`getstatic` không phù hợp, không nhất thiết `NoSuchFieldError`.

**Câu 6.** Đã thêm JAR mới vào classpath nhưng vẫn lỗi vì sao?

**Đáp án:** Parent-first delegation, classpath precedence, server-provided library hoặc duplicate JAR có thể vẫn khiến runtime nạp bản cũ. In defining loader, module và CodeSource của class thực tế.

**Câu 7.** Cách nào xác minh client.class đang tham chiếu method descriptor nào?

**Đáp án:** `javap -classpath client-classes -verbose -c app.Client`, đọc `Methodref`/`Fieldref` và opcode.

**Câu 8.** Tại sao public `static final int` thay giá trị đôi khi không phát lỗi nhưng client vẫn thấy giá trị cũ?

**Đáp án:** `javac` có thể inline constant vào client bytecode; không còn field lookup ở chỗ dùng ấy. Recompile client hoặc thay thiết kế API nếu giá trị cần cập nhật động.

**Câu 9.** `NoSuchFieldError` có chứng minh toàn bộ class bị thiếu không?

**Đáp án:** Không. Owner class có thể đã load thành công nhưng field name+descriptor không có trong runtime hierarchy. Nếu class thiếu, lỗi thường khác như `ClassNotFoundException`/`NoClassDefFoundError` theo ngữ cảnh.

**Câu 10.** Một plugin compile với SDK v2, host chỉ cung cấp SDK v1. Đổi TCCL có chắc sửa lỗi không?

**Đáp án:** Không. TCCL chỉ ảnh hưởng API chủ động dùng nó; nếu API class đã được parent define từ v1, TCCL không tự thay metadata/method table. Cần version compatibility hoặc classloader architecture khác.

**Câu 11.** Vì sao lỗi chỉ xuất hiện khi bật tính năng hiếm dùng?

**Đáp án:** Symbolic references tới code path đó có thể chỉ được resolve khi thực thi; test startup không nhất thiết chạm tới member bị mismatch. Cần integration tests cho các chức năng trọng yếu.

**Câu 12.** Hướng sửa triệt để là gì?

**Đáp án:** Tìm chính xác binary client expectation và runtime API thực tế; thống nhất/bảo đảm binary-compatible library versions, rebuild callers khi breaking API đổi, loại duplicate/classloader conflicts, đóng gói và redeploy đúng artifact, test end-to-end.

## 18. Checklist xử lý nhanh trước khi deploy

1. **Giữ stack trace đầy đủ** và xác định owner/member/descriptor bị thiếu.
2. **Ghi đúng bản client artifact** được biên dịch và được deploy.
3. **Dùng `javap`** xem symbolic method/field references trong caller class.
4. **Xác định actual runtime class** với class-loading logs, CodeSource và defining loader.
5. **Đọc descriptor runtime** bằng `javap -p -s`.
6. **Kiểm tra duplicate classes/JARs** trên classpath, module path và thư mục của server.
7. **Kiểm tra dependency graph** của cả compileClasspath và runtimeClasspath (Maven/Gradle).
8. **Xem plugin/host parent-first policy** nếu thư viện dùng trong container.
9. **Sửa binary compatibility** chứ không chỉ source API dựa theo IDE.
10. **Rebuild/clean deploy** mọi module caller bị tác động nếu method/field descriptors thay đổi.
11. **Test runtime thật**: old client binaries với new library và các code paths hiếm.
12. **Quản lý versioning và API evolution**: tránh xóa/đổi thành viên công khai thiếu migration plan.
13. **Không dựa vào `System.gc()`/`URLClassLoader.close()`** để chữa linkage mismatch trong class đã define.
14. **Phân biệt lỗi**: `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, `IncompatibleClassChangeError`, `NoClassDefFoundError` có nguyên nhân khác nhau.

## Kết luận

**`NoSuchMethodError` và `NoSuchFieldError` thường báo rằng caller bytecode và runtime class definitions không có cùng binary API**. JVM không tra method/field bằng tên gần giống hay tự biên dịch lại client; nó resolve **symbolic owner + member name + descriptor** theo classloader và các quy tắc JVMS. Thay tên, tham số, kiểu trả về hoặc kiểu field có thể làm binary cũ không còn link, dù class owner vẫn load được.

Cách sửa đáng tin cậy: **tìm class thực sự được nạp → so `javap` client/runtime descriptors → giải quyết dependency version/loader conflict → rebuild và deploy tương thích → chạy tests bằng runtime artifacts thực**. Đây là cách giải quyết nguyên nhân, thay vì che `Error` bằng catch hoặc thêm JAR ngẫu nhiên.

**Tài liệu chuẩn Java SE 17:**

- [JVMS 17 `5.1 – Runtime Constant Pool](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.1): symbolic references cho class, method và field.
- [JVMS 17 `5.4.3.2 – Field Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.2): field name+descriptor, `NoSuchFieldError` và access/link checks.
- [JVMS 17 `5.4.3.3 – Method Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.3): method lookup, `NoSuchMethodError`.
- [JLS 17 Chapter 13 – Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): các thay đổi source/binary giữ hoặc phá compatibility.
- [`NoSuchMethodError` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html) và [`NoSuchFieldError` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchFieldError.html).
- [`ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining loader và delegation.
