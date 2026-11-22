# 14.6. Mô tả hằng động bằng `DynamicConstantDesc` và phân giải theo quyền của `Lookup`

**Hằng động** (*dynamically-computed constant*, viết tắt *condy*) cho phép một mục hằng trong class file được tính thông qua bootstrap method khi JVM phân giải mục hằng đó, thay vì bắt buộc lưu sẵn giá trị literal. Trong Java 17, `java.lang.constant.DynamicConstantDesc<T>` là **mô tả danh nghĩa** (*nominal descriptor*) cho hằng động, còn `java.lang.invoke.MethodHandles.Lookup` cung cấp **ngữ cảnh tìm tên và kiểm tra quyền truy cập** khi ta chủ động gọi `resolveConstantDesc(lookup)`.

Ba điều cần ghi nhớ từ đầu:

1. `DynamicConstantDesc` mô tả **bootstrap + tên hằng + kiểu hằng + tham số bootstrap**. Tạo descriptor không chạy bootstrap và không tự đọc được field hay method private.
2. `resolveConstantDesc(lookup)` mới giải mô tả bằng quyền/class loader/module của `Lookup`. **Cùng một descriptor** có thể phân giải thành công với Lookup có quyền private nhưng thất bại với Lookup đã bị giảm quyền.
3. **Phân giải bằng Java API không cache kết quả.** Điều này khác với cơ chế JVM cache giá trị khi phân giải một mục `CONSTANT_Dynamic` thực sự trong runtime constant pool. Một bootstrap có side effect có thể chạy mỗi lần gọi `resolveConstantDesc`.

Bài trình bày cách tạo descriptor bằng API Java 17, cơ chế resolution, ranh giới quyền truy cập, những lỗi dễ nhầm và chương trình thực hành được biên dịch bằng `javac --release 17`.

## 1. Hai tầng: `CONSTANT_Dynamic` trong class file và `DynamicConstantDesc` trong Java

Trong định dạng class file, `CONSTANT_Dynamic_info` là một symbolic reference tới hằng được tính động. Nó nêu một bootstrap method và bộ tham số tĩnh, cùng thông tin tên/kiểu hằng. Khi một mục hằng động cần được phân giải, JVM gọi bootstrap phù hợp và kiểm tra kết quả. Đây là cơ chế ở **runtime constant pool** của class đã load.

`DynamicConstantDesc<T>` lại là **đối tượng Java mô tả** cùng thông tin ở cấp API `java.lang.constant`. Các công cụ đọc, phân tích hoặc tạo bytecode dùng descriptor để biểu diễn dữ liệu dạng class file. Ứng dụng cũng có thể dựng descriptor và thử phân giải bằng `resolveConstantDesc(lookup)` mà không cần tự tạo class file có instruction `ldc` trỏ vào `CONSTANT_Dynamic`.

| Khái niệm | Là gì? | Lúc nào tính giá trị? |
| --- | --- | --- |
| `CONSTANT_Dynamic_info` | Mục danh nghĩa trong constant pool của class file | JVM tính khi resolve symbolic reference đó |
| `DynamicConstantDesc<T>` | Đối tượng Java **mô tả** một hằng động | Chưa tính khi gọi factory `ofNamed` hay `of` |
| `resolveConstantDesc(Lookup)` | API dùng lookup để reflectively giải descriptor | Khi gọi API; **không tự cache** cho lần gọi kế tiếp |
| `ConstantDesc` | Interface chung cho các nominal descriptors | Mỗi implementation định nghĩa cách resolve thích hợp |

**Không nhầm với `static final`:** modifier này khóa việc gán lại field trong Java, không tự biến field thành mục `CONSTANT_Dynamic`. Dù có thể dùng bootstrap chuẩn để đọc một `static final` field, hai khái niệm không đồng nhất.

**Không nhầm với `invokedynamic`:** bootstrap cho call site động dùng ba prefix parameters `Lookup, String, MethodType` và phải tạo `CallSite`; bootstrap cho **dynamic constant** dùng `Lookup, String, Class<?>` và tạo một giá trị hằng tương thích kiểu đã mô tả. `DynamicCallSiteDesc` là loại mô tả khác.

Cơ chế condy được đưa vào class file Java 11 (JEP 309). API nominal constant descriptors, trong đó có `DynamicConstantDesc`, xuất hiện từ Java 12 (JEP 334).

## 2. Cấu tạo một descriptor

Một `DynamicConstantDesc<T>` chứa bốn phần danh nghĩa:

```text
DynamicConstantDesc<T>
  ├─ bootstrapMethod  : DirectMethodHandleDesc
  ├─ constantName     : String
  ├─ constantType     : ClassDesc
  └─ bootstrapArgs    : ConstantDesc[] (có thể rỗng)
```

| API | Ý nghĩa |
| --- | --- |
| `bootstrapMethod()` | Descriptor của method handle trỏ tới bootstrap method |
| `constantName()` | Tên hằng động, xuất hiện trong thông tin `NameAndType` |
| `constantType()` | `ClassDesc` mô tả kiểu giá trị cần tạo, ví dụ `String` hoặc `int` |
| `bootstrapArgs()` | Mảng static bootstrap arguments dạng `ConstantDesc` |
| `bootstrapArgsList()` | Danh sách bootstrap arguments không sửa được qua List API |
| `resolveConstantDesc(lookup)` | Giải descriptor bằng quyền `Lookup` và trả giá trị thực |

Các kiểu ở đây **chưa phải thực thể runtime**: `ClassDesc` chưa phải `Class<?>` đã được load; `DirectMethodHandleDesc` chưa phải `MethodHandle` đã resolve. Một descriptor có thể được dựng và đọc metadata mà không có quyền gọi bootstrap hoặc truy cập field được mô tả.

Đoạn minh họa trong ngữ cảnh có biến `desc`:

```java
System.out.println(desc.constantName());
System.out.println(desc.constantType());
System.out.println(desc.bootstrapMethod());
System.out.println(desc.bootstrapArgsList());
```

Bốn lệnh trên **chỉ đọc metadata**, không chạy bootstrap. Đoạn này chưa độc lập vì chưa tạo `desc`; phần chương trình đầy đủ ở mục 7 sẽ xây và giải descriptor thật.

### 2.1. Tên hằng và kiểu hằng

Tên phải là **unqualified name hợp lệ** theo quy tắc JVM, không phải đường dẫn tùy ý. `ofNamed` có thể ném `IllegalArgumentException` ngay khi tạo descriptor nếu tên sai định dạng. Tên `"greeting"` trong ví dụ chỉ được truyền cho bootstrap; nó không tự đồng nghĩa với tên một Java field.

`constantType()` là `ClassDesc`. `ConstantDescs.CD_String` mô tả `String`, `ConstantDescs.CD_int` mô tả `int`. Khi resolve, hệ thống cần chuyển descriptor kiểu thành `Class<?>` thích hợp và kiểm tra kết quả bootstrap có thể dùng làm giá trị hằng kiểu đó hay không.

Generic `<T>` giúp biểu thị ý định ở source Java nhưng **không thay thế các kiểm tra resolution/type**. Bạn có thể tạo mô tả sai hoặc tham chiếu method thiếu quyền dù khai báo biến là `DynamicConstantDesc<String>`.

### 2.2. Static bootstrap arguments

Các tham số phụ phải là những giá trị có thể biểu diễn trong hệ `ConstantDesc`, chẳng hạn literal `String`, primitive wrapper thích hợp, `ClassDesc`, `MethodHandleDesc` hoặc descriptor lồng nhau. Với tham số tự nó là descriptor, quá trình resolve có thể đòi truy cập thêm class/method/field theo `Lookup`.

Không thể đưa trực tiếp `new Object()` hay một DTO runtime không có biểu diễn constant phù hợp vào `ConstantDesc...` để JVM tự serialize nó. Nếu bootstrap cần dữ liệu runtime đặc biệt, thiết kế biểu diễn hợp lệ bằng hằng/descriptor, hoặc chọn cơ chế truyền dữ liệu khác.

## 3. Ba factory: `ofNamed`, `of`, `ofCanonical`

### 3.1. `ofNamed`: mô tả đầy đủ

```java
static <T> DynamicConstantDesc<T> ofNamed(
        DirectMethodHandleDesc bootstrapMethod,
        String constantName,
        ClassDesc constantType,
        ConstantDesc... bootstrapArgs)
```

Ví dụ trong ngữ cảnh đã có class `DynamicConstantLookupDemo`:

```java
ClassDesc owner = ClassDesc.of("DynamicConstantLookupDemo");
DirectMethodHandleDesc bsm = ConstantDescs.ofConstantBootstrap(
        owner, "counted", ConstantDescs.CD_String,
        ConstantDescs.CD_String);

DynamicConstantDesc<String> description = DynamicConstantDesc.ofNamed(
        bsm, "greeting", ConstantDescs.CD_String, "world");
```

`owner` mô tả lớp chứa bootstrap; `bsm` mô tả method `counted`; `constantName` là `"greeting"`; kiểu hằng là `String`; static arg `"world"` cũng có kiểu `String`. Đây chưa phải việc gọi `counted`: `ofNamed` chỉ xây descriptor.

`ConstantDescs.ofConstantBootstrap(owner, name, returnType, staticArgTypes...)` là factory chuyên dùng cho bootstrap của dynamic constant. Nó tự ghép **prefix signature `Lookup, String, Class`** vào descriptor method, rồi thêm các kiểu static arguments đã cung cấp. Đừng nhầm nó với API tạo CallSite bootstrap, trong đó tham số thứ ba là `MethodType`.

### 3.2. `of`: tên mặc định, kiểu theo bootstrap

`DynamicConstantDesc.of(bootstrap)` và `DynamicConstantDesc.of(bootstrap, bootstrapArgs...)` sử dụng `ConstantDescs.DEFAULT_NAME`. Kiểu hằng được đặt theo **return type mô tả trên bootstrap method**, không dựa vào giá trị bootstrap chưa chạy.

Dùng `of` nếu bootstrap không quan tâm tên hằng riêng và kiểu có thể suy ra đúng từ chữ ký. Dùng `ofNamed` nếu cần kiểm soát tên cụ thể, kiểu hằng hoặc static arguments tương ứng với định dạng class file.

### 3.3. `ofCanonical` có thể trả subtype khác

`DynamicConstantDesc.ofCanonical(...)` trả về **`ConstantDesc`**, không hứa luôn là `DynamicConstantDesc`. Với một số bootstrap well-known, API có thể chuyển mô tả sang loại chuyên biệt hơn, ví dụ một `ClassDesc` hay một descriptor liên quan enum/VarHandle.

Khi viết công cụ đọc constant pool, `ofCanonical` có thể hữu ích để biểu diễn ý nghĩa chuẩn của hằng. Nhưng **không ép kiểu mù** kết quả sang `DynamicConstantDesc<?>`; nếu thực tế trả `ClassDesc` thì ép kiểu sẽ lỗi.

## 4. Signature của bootstrap method cho hằng động

Một bootstrap tự viết thường có mẫu:

```java
public static String counted(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type,
        String suffix) {
    return name + ":" + suffix;
}
```

Mã trên là ví dụ về signature, không phải chương trình độc lập. Ý nghĩa:

1. **`lookup`:** ngữ cảnh phân giải tên và kiểm tra access; không mặc nhiên toàn quyền.
2. **`name`:** tên của hằng đang được resolve.
3. **`type`:** class mirror đại diện cho kiểu hằng cần trả, được xác định bởi `constantType`.
4. **`suffix`:** static bootstrap argument đã được resolve, ví dụ chuỗi `"world"`.

Bootstrap có thể bỏ qua `name` hoặc `type` nếu contract cho phép, nhưng việc bỏ qua không giúp che lỗi ở giai đoạn resolve class, method hoặc static args. Kết quả cuối phải phù hợp với kiểu hằng.

Method descriptor của bootstrap ở ví dụ hoàn chỉnh là:

```text
(MethodHandles.Lookup, String, Class, String)String
```

Đây là chữ ký **method bootstrap**, không phải type của một MethodHandle target dành cho `invokedynamic`. Những phần như `ClassDesc` và `DirectMethodHandleDesc` chỉ mô tả ký hiệu; khi resolve, bootstrap được tìm như một method thực theo quyền `Lookup`.

### 4.1. Bootstrap có thể thực thi mã có side effect

`resolveConstantDesc` có thể gọi tới phương thức tự định nghĩa, và phương thức đó có thể đọc field, tăng counter, cấp phát đối tượng hoặc ném exception. Vì thế một descriptor **không chỉ là dữ liệu hiển thị vô hại khi quyết định resolve nó**. Trước khi phân giải descriptor đến từ plugin hay đầu vào không tin cậy, phải kiểm tra chính sách cho phép và tránh trao `Lookup` quyền cao ngoài ý muốn.

Một bootstrap “hằng” tốt thường có kết quả ổn định cho những input cố định, nhưng API không cấm ví dụ có side effect. Chương trình dưới đây cố tình tăng counter để chứng minh sự khác nhau giữa descriptor resolution và caching của constant pool.

## 5. `Lookup` quyết định quyền ở thời điểm resolution

Chữ ký thực của `DynamicConstantDesc` trên Java 17:

```java
public T resolveConstantDesc(MethodHandles.Lookup lookup)
        throws ReflectiveOperationException;
```

`resolveConstantDesc` dùng `lookup` làm **ngữ cảnh truy cập và tìm tên**. Ở mức khái niệm, resolution có thể cần:

1. Giải `ClassDesc` của kiểu hằng, các class liên quan và static arguments.
2. Giải bootstrap `DirectMethodHandleDesc` thành một MethodHandle thực.
3. Kiểm tra xem từ ngữ cảnh caller có quyền truy cập method/field/class cần dùng hay không.
4. Chuẩn bị `Lookup`, tên, kiểu và các static arguments đã resolve để gọi bootstrap.
5. Thực thi bootstrap và kiểm tra kết quả trả về tương thích `constantType`.

Đây là sơ đồ giải thích, không khẳng định thứ tự chi tiết của mọi thao tác liên kết trên mọi triển khai JVM. Quy tắc chính thức về resolution và access control nằm trong JVMS `5.4.3.6` và `5.4.4`.

**Các bước có thể thất bại khác nhau:** class không tìm thấy, bootstrap method thiếu, chữ ký khác, module không mở/không export theo yêu cầu, Lookup thiếu quyền private, bootstrap tự ném lỗi, static arg không hợp lệ, hoặc kết quả không khớp type.

### 5.1. `MethodHandles.lookup()` không bằng `publicLookup()`

`MethodHandles.lookup()` trả một `Lookup` dựa trên **caller class tại vị trí gọi**, có thể mang quyền private vào class đó và nestmates tương ứng. `MethodHandles.publicLookup()` chỉ đại diện access mức public trong điều kiện class/module/loader cho phép; nó không phải một “superuser” và đôi khi còn dùng class-loader ngữ cảnh khác.

Để cách ly chính yếu **quyền private** mà không đưa thêm khác biệt class-loader vào bài, ví dụ kiểm thử dùng:

```java
MethodHandles.Lookup full = MethodHandles.lookup();
MethodHandles.Lookup restricted =
        full.dropLookupMode(MethodHandles.Lookup.PRIVATE);
```

Cả hai được tạo trong class của ví dụ. `restricted` là Lookup **đã bị hạ quyền**, nên không còn đặc quyền truy cập field private ở chính class đó. `dropLookupMode` có quy tắc suy giảm các access modes liên quan; không suy rằng trạng thái còn lại luôn chỉ khác đúng một bit. Có thể kiểm tra `lookup.lookupClass()` và `lookup.lookupModes()` để biết ngữ cảnh thực tế.

### 5.2. Phân giải public và private field từ cùng descriptor family

`ConstantDescs.BSM_GET_STATIC_FINAL` mô tả bootstrap chuẩn `ConstantBootstraps.getStaticFinal`. Nó có thể đọc một static final field phù hợp và chịu access checks theo `Lookup` được truyền.

Với:

```java
public static final String OPEN = "open";
private static final String SECRET = "hidden";
```

Nếu cùng class dùng Lookup đầy đủ, hai field đều có thể được resolve qua bootstrap chuẩn. Với Lookup đã bỏ `PRIVATE`, `OPEN` vẫn có thể truy cập nhờ quyền public (giả sử class/module thích hợp), nhưng `SECRET` **không** hợp lệ. Đây là **ràng buộc quyền**, không phải khác biệt giữa `final` và non-final, cũng không phải một vấn đề về kiểu `String`.

Việc tạo:

```java
DynamicConstantDesc<String> secret = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_GET_STATIC_FINAL,
        "SECRET", ConstantDescs.CD_String,
        ClassDesc.of("DynamicConstantLookupDemo"));
```

không tự trao quyền private và không đọc field ngay. Phép phân giải với `full` hay `restricted` mới quyết định khả năng đọc. Trong thực tế bootstrap chuẩn còn có thể báo `IllegalAccessError` với `IllegalAccessException` làm cause; **không nên chỉ dựa vào một tên ngoại lệ để mô tả toàn bộ contract**.

### 5.3. Module, package và class loader cũng thuộc ngữ cảnh

`Lookup` không chỉ là một cờ `private`. Nó có lookup class, các access modes, các luật package/module và khả năng resolve class qua class loader. Hai class cùng binary name được load bởi hai class loader khác nhau có thể là **hai type runtime khác nhau**. `ClassDesc` tự nó mô tả tên, không mang theo một đối tượng `Class<?>` đã được liên kết duy nhất.

Trong JPMS, readability/export/open liên quan tới loại truy cập bạn cần. `MethodHandles.privateLookupIn(...)` chỉ hợp lệ khi caller/module được phép; nó không phải đường vòng để tự ý vượt module boundary. Nếu `resolveConstantDesc` bị từ chối, xác minh lookup context, package và loại member trước khi thay đổi JVM flags.

### 5.4. Không cấp `Lookup` quyền cao cho descriptor không tin cậy

Một descriptor chỉ có metadata ở bước tạo, nhưng khi **resolve** nó, bootstrap code có thể thực thi với ngữ cảnh truy cập được đưa vào. Vì vậy việc phân giải một descriptor lấy từ nguồn ngoài cần được đánh giá gần giống một thao tác có thể **thực thi mã**. Không gửi `fullLookup` tới plugin tùy ý rồi hy vọng generic `DynamicConstantDesc<String>` bảo đảm an toàn.

## 6. Descriptor không cache; runtime constant pool của JVM có cache

Javadoc của `DynamicConstantDesc.resolveConstantDesc` nêu rõ **không cache giá trị phân giải**. Ví dụ bootstrap tăng biến đếm:

```java
String first = description.resolveConstantDesc(full);  // "greeting:world:1"
String second = description.resolveConstantDesc(full); // "greeting:world:2"
```

`description` là cùng object ở cả hai dòng, nhưng bootstrap có thể được gọi lại. Hai descriptor khác object mà `equals(...)` trả `true` cũng không tự chia sẻ một cache kết quả: `equals` ở đây là so sánh **bootstrap method descriptor + tên + kiểu + static arguments**.

Ngược lại, khi JVM phân giải một mục `CONSTANT_Dynamic` thực sự trong runtime constant pool, kết quả liên kết được **ghi nhớ cho symbolic reference tương ứng**; lần truy cập tiếp theo tới mục đã resolve không gọi lại bootstrap. Thậm chí các lần resolution thất bại còn có quy tắc ghi nhớ lỗi của JVM.

| Thao tác | Có tự chạy bootstrap? | Kết quả có được cache tự động? |
| --- | --- | --- |
| `DynamicConstantDesc.ofNamed(...)` | Không | Không có giá trị để cache |
| `description.resolveConstantDesc(full)` lần 1 | Có thể có | **Không** cache cho lần 2 |
| `description.resolveConstantDesc(full)` lần 2 | Có thể chạy lại | **Không** cache cho lần 3 |
| JVM resolve một `CONSTANT_Dynamic` trong class file | Có khi lần đầu cần resolve | **Có** cho symbolic reference đó |
| `description.equals(other)` | Không | Chỉ so metadata |

**Lưu ý:** JVM cache theo mục symbolic reference liên quan, không phải một “cache toàn cục theo tên hằng”. Hai class/constant-pool entries không tự chia sẻ cùng kết quả chỉ vì metadata giống nhau. Nếu ứng dụng tự cache descriptor resolution, nó phải xét quyền `Lookup`, class-loader identity, concurrency và side effects — không thể chỉ lấy `constantName` làm key.

## 7. Ví dụ Java 17+ đầy đủ: mô tả, phân giải, quyền và no-cache

Lưu **toàn bộ** source sau vào file `DynamicConstantLookupDemo.java`. Đây là một class public trong unnamed package để chạy độc lập với `javac` và `java`. `counted` là custom bootstrap method; hai descriptor còn lại dùng `ConstantDescs.BSM_GET_STATIC_FINAL`; descriptor cuối dùng `BSM_NULL_CONSTANT`.

```java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.DirectMethodHandleDesc;
import java.lang.constant.DynamicConstantDesc;
import java.lang.invoke.MethodHandles;

public class DynamicConstantLookupDemo {
    public static final String OPEN = "open";
    private static final String SECRET = "hidden";
    private static int counter;

    public static String counted(MethodHandles.Lookup lookup,
                                 String name, Class<?> type, String suffix) {
        if (type != String.class) {
            throw new IllegalArgumentException("expected String");
        }
        return name + ":" + suffix + ":" + (++counter);
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        MethodHandles.Lookup full = MethodHandles.lookup();
        MethodHandles.Lookup restricted =
                full.dropLookupMode(MethodHandles.Lookup.PRIVATE);
        ClassDesc owner = ClassDesc.of("DynamicConstantLookupDemo");

        DirectMethodHandleDesc bsm = ConstantDescs.ofConstantBootstrap(
                owner, "counted", ConstantDescs.CD_String,
                ConstantDescs.CD_String);
        DynamicConstantDesc<String> description = DynamicConstantDesc.ofNamed(
                bsm, "greeting", ConstantDescs.CD_String, "world");
        DynamicConstantDesc<String> sameDescription = DynamicConstantDesc.ofNamed(
                bsm, "greeting", ConstantDescs.CD_String, "world");

        System.out.println("name=" + description.constantName());
        System.out.println("type=" + description.constantType().displayName());
        System.out.println("bootstrap=" + description.bootstrapMethod().methodName());
        System.out.println("args=" + description.bootstrapArgsList().size());
        System.out.println("equal=" + description.equals(sameDescription));
        System.out.println("created.counter=" + counter);
        System.out.println("first=" + description.resolveConstantDesc(full));
        System.out.println("second=" + description.resolveConstantDesc(full));

        DynamicConstantDesc<String> open = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_GET_STATIC_FINAL, "OPEN",
                ConstantDescs.CD_String, owner);
        DynamicConstantDesc<String> secret = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_GET_STATIC_FINAL, "SECRET",
                ConstantDescs.CD_String, owner);

        System.out.println("open.full=" + open.resolveConstantDesc(full));
        System.out.println("open.restricted=" + open.resolveConstantDesc(restricted));
        System.out.println("secret.full=" + secret.resolveConstantDesc(full));

        boolean denied = false;
        try {
            secret.resolveConstantDesc(restricted);
        } catch (ReflectiveOperationException | LinkageError e) {
            denied = true;
        }
        System.out.println("secret.restricted.denied=" + denied);

        DynamicConstantDesc<String> nullable = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_NULL_CONSTANT, "empty", ConstantDescs.CD_String);
        System.out.println("null.result=" + (nullable.resolveConstantDesc(full) == null));
    }
}
```

Biên dịch với API Java 17 và chạy trong cùng thư mục:

```bash
javac --release 17 DynamicConstantLookupDemo.java
java DynamicConstantLookupDemo
```

`stdout` của ví dụ:

```text
name=greeting
type=String
bootstrap=counted
args=1
equal=true
created.counter=0
first=greeting:world:1
second=greeting:world:2
open.full=open
open.restricted=open
secret.full=hidden
secret.restricted.denied=true
null.result=true
```

Source này đã biên dịch thành công với tùy chọn `--release 17` và được chạy kiểm chứng trên OpenJDK 24. API sử dụng là API chuẩn của Java 17; cờ `denied=true` tránh khóa ví dụ vào tên exception cụ thể của một lần resolution thất bại trên một phiên bản JVM.

### 7.1. Vì sao các dòng có kết quả như vậy?

**`name=greeting`, `type=String`, `bootstrap=counted`, `args=1`:** chính là metadata đã cung cấp cho `ofNamed`, chưa phải kết quả chạy bootstrap.

**`equal=true`:** hai descriptor riêng có cùng cấu trúc; tiêu chí equals không phải object identity hoặc bằng nhau về kết quả từng lần resolution.

**`created.counter=0`:** tạo descriptor và xem metadata không gọi bootstrap `counted`. Nếu tạo descriptor mà counter đã tăng, đó là do code khác chủ động chạy side effect, không phải do `ofNamed` theo contract.

**`first=greeting:world:1`, `second=greeting:world:2`:** gọi `resolveConstantDesc(full)` hai lần làm `counted` chạy hai lần. Đây là sự khác biệt trực tiếp giữa **descriptor resolution không cache** và **runtime constant pool cache**.

**`open.full=open` / `open.restricted=open`:** `OPEN` là field public, được bootstrap chuẩn `getStaticFinal` phân giải thành công với Lookup có hoặc không có quyền private, trong ngữ cảnh class/package của ví dụ.

**`secret.full=hidden`:** `full` được tạo bên trong chính `DynamicConstantLookupDemo`, đủ quyền truy cập thành viên private của class đó.

**`secret.restricted.denied=true`:** cùng descriptor `SECRET` nhưng `restricted` đã mất quyền `PRIVATE`; lời giải bị từ chối. Ngoại lệ cụ thể có thể được biểu diễn qua `ReflectiveOperationException` hoặc `LinkageError` tùy giai đoạn và cause chain; phiên bản OpenJDK được thử đã báo `IllegalAccessError` có `IllegalAccessException` làm cause, nên ví dụ chỉ in thông tin “bị từ chối” ổn định.

**`null.result=true`:** `BSM_NULL_CONSTANT` có thể trả null cho một **reference type** như `String`. Không được suy rằng một constant primitive như `int` có thể mang null, hoặc rằng có thể truyền một `null` bất kỳ làm bootstrap argument trong factory.

## 8. Kiểm tra lỗi theo từng giai đoạn

| Giai đoạn | Dấu hiệu thường gặp | Hướng xử lý |
| --- | --- | --- |
| Tạo descriptor | `IllegalArgumentException` với tên sai định dạng | Kiểm tra `constantName` là unqualified name hợp lệ |
| Giải class | `ClassNotFoundException`/`LinkageError` | Kiểm tra `ClassDesc`, lookup class loader và module readability |
| Giải bootstrap handle | Method không tồn tại hoặc không truy cập được | Kiểm tra owner, method name, static modifier, signature và quyền Lookup |
| Giải bootstrap args | Descriptor lồng nhau không resolve được | Kiểm tra từng `ConstantDesc` và ngữ cảnh access |
| Gọi bootstrap | Chính bootstrap ném runtime exception/error | Xem stack trace/cause, không nhầm với lỗi mô tả |
| Kiểm tra kiểu kết quả | Trả sai type hoặc null cho primitive | Căn chỉnh `constantType` và bootstrap contract |
| Truy cập private | Có thể thấy `IllegalAccessError` với cause `IllegalAccessException` | Xác minh `lookupModes`/module/owner; không tự động nâng quyền |
| Gọi lần hai | Counter thay đổi, không có cache | Đúng contract `resolveConstantDesc`; nếu cần cache, thiết kế riêng |

`resolveConstantDesc` khai báo checked `ReflectiveOperationException`, nhưng **không có nghĩa mọi lỗi đều là checked exception**. Lỗi liên kết có thể là `LinkageError`/`BootstrapMethodError`; bootstrap có thể tự ném exception hoặc error. Code `catch (Exception e)` không bắt được mọi `Error`.

**Không** sửa bằng cách nuốt `Throwable` rồi trả `null` trong production: làm vậy có thể biến lỗi liên kết và quyền truy cập thành dữ liệu sai hợp lệ giả, đồng thời che nguyên nhân gốc.

### 8.1. Debug bằng metadata và quyền

Với biến `desc` và `lookup` hợp lệ trong code:

```java
System.out.println("name: " + desc.constantName());
System.out.println("type: " + desc.constantType());
System.out.println("bootstrap: " + desc.bootstrapMethod());
System.out.println("static args: " + desc.bootstrapArgsList());
System.out.println("lookup class: " + lookup.lookupClass());
System.out.println("lookup modes: " + lookup.lookupModes());
```

Đoạn này **không phải file độc lập**, mà là checklist log ở caller. Khi báo lỗi thực, ghi thêm cause chain và class loader/module phù hợp; tránh log giá trị bí mật của resolved constant.

**Lưu ý:** Một `ClassDesc` chưa tự ghim một `Class<?>` runtime duy nhất. Cùng tên lớp nhưng class loader khác có thể dẫn đến class khác hoặc không tìm thấy lớp. Nếu một `publicLookup()` không giải được class của ứng dụng, lỗi có thể xảy ra trước khi kiểm tra quyền private field. Vì thế ví dụ dùng `dropLookupMode(PRIVATE)` trên một lookup đã resolve được class để phân biệt riêng vấn đề access.

## 9. Các bootstrap descriptor chuẩn và khi nào dùng

`java.lang.constant.ConstantDescs` cung cấp một số descriptor cho bootstrap có sẵn:

| Bootstrap descriptor | Tác dụng | Ràng buộc đáng nhớ |
| --- | --- | --- |
| `BSM_GET_STATIC_FINAL` | Lấy giá trị static final field | Phải thấy được class/field theo `Lookup` |
| `BSM_NULL_CONSTANT` | Tạo null constant | Chỉ với kiểu tham chiếu |
| `BSM_ENUM_CONSTANT` | Lấy enum constant | Tên/enum type phải hợp lệ |
| `BSM_PRIMITIVE_CLASS` | Lấy Class mirror của primitive | Tên descriptor/type phải đúng |
| `BSM_INVOKE` | Gọi MethodHandle để tạo constant | Method handle và static args phải resolve được |
| `BSM_VARHANDLE_FIELD` / `BSM_VARHANDLE_STATIC_FIELD` | Tạo VarHandle cho field | Không bỏ qua ranh giới truy cập field |

Ưu tiên bootstrap chuẩn khi nó khớp mục tiêu, thay vì tự viết method làm lại cùng việc mà không kiểm soát đầy đủ signature và access. Nếu dùng custom bootstrap, hãy dùng `ConstantDescs.ofConstantBootstrap(...)` để mô tả prefix parameters chính xác, rồi viết method thật có signature tương ứng.

Không chọn bootstrap bằng cách dò tên một cách chủ quan; hãy so method descriptor, static arguments, return type, và quyền của caller. Khi mô hình có thể biểu diễn bằng một `ClassDesc`/`EnumDesc` chuyên biệt, `ofCanonical` có thể cung cấp loại mô tả thích hợp hơn cho công cụ phân tích class file.

## 10. Các sai lầm cần tránh

**Sai lầm 1: “Có `DynamicConstantDesc<String>` tức là giá trị đã có sẵn.”** Descriptor chứa metadata, không lưu sẵn `String` result. Gọi `resolveConstantDesc` mới thực thi resolution.

**Sai lầm 2: “Gọi `ofNamed` thành công tức là có quyền truy cập field/method.”** Factory kiểm tra cấu trúc đầu vào, không thay cho runtime name resolution hoặc access control.

**Sai lầm 3: “Mọi `Lookup` đều như nhau vì chỉ là đối số đầu tiên của bootstrap.”** Quyền PRIVATE/MODULE, caller lookup class và class loader quyết định khác biệt thực chất.

**Sai lầm 4: “Hằng là thứ không bao giờ chạy bootstrap quá một lần.”** Cần phân biệt **JVM constant-pool resolution** có cache với Java API `resolveConstantDesc` **không cache**.

**Sai lầm 5: “`ClassDesc` là `Class<?>`.”** `ClassDesc` là tên/symbolic description; chỉ resolution mới xác định class cụ thể trong loader/module context.

**Sai lầm 6: “`ofCanonical` luôn trả DynamicConstantDesc.”** Return type của nó là `ConstantDesc`; có thể canonicalize thành loại descriptor khác.

**Sai lầm 7: “Có thể truyền bất kỳ object runtime làm bootstrapArgs.”** `bootstrapArgs` cần `ConstantDesc` tương ứng, không phải mảng DTO tùy ý.

**Sai lầm 8: “Cứ catch `ReflectiveOperationException` là đã bắt hết mọi lỗi.”** `LinkageError` và các failure của bootstrap vẫn có thể xảy ra; phải giữ nguyên cause để chẩn đoán.

**Sai lầm 9: “`Lookup` quyền cao dùng resolve descriptor từ plugin cũng chỉ là đọc metadata.”** Resolve có thể thực thi bootstrap code; phải kiểm soát nguồn descriptor và quyền được cấp.

## 11. Bài tập tự kiểm tra

**A.** Một descriptor của static final field private được tạo thành công bằng `ofNamed`. Có thể kết luận nó resolve được với mọi `Lookup` không? Tại sao?

**B.** Hai descriptor có cùng bootstrap, tên, kiểu và args, nên `equals(...)` trả true. Bootstrap tăng counter. Hai lần `resolveConstantDesc` có được bảo đảm cùng giá trị không?

**C.** Bootstrap method dùng `(Lookup, String, MethodType)` làm ba tham số đầu. Đây có phải signature đúng cho dynamic constant bootstrap không?

**D.** Trong cùng class, `full = MethodHandles.lookup()` và `restricted = full.dropLookupMode(PRIVATE)`. Với bootstrap chuẩn đọc field, `public static final` và `private static final` khác nhau ra sao?

**E.** `DynamicConstantDesc.ofCanonical(...)` trả `ConstantDesc`. Có nên ép kiểu trực tiếp thành `DynamicConstantDesc` không?

**F.** JVM đã phân giải thành công một `CONSTANT_Dynamic`. Sử dụng lại symbolic reference đó có tái chạy bootstrap không? Nếu gọi `desc.resolveConstantDesc(lookup)` lần nữa thì sao?

**G.** Khi static bootstrap argument là `ClassDesc`, có cần phân giải nó theo class loader/module/Lookup context không?

**H.** Vì sao không nên dùng `Lookup` toàn quyền để resolve một descriptor từ nguồn không tin cậy?

**Đáp án:**

- **A:** Không. `ofNamed` chỉ tạo metadata. Khi resolve, việc tìm field/BSM còn phụ thuộc access mode, class loader và module context của Lookup.
- **B:** Không. `equals` chỉ so thông tin mô tả; API resolution không cache, nên bootstrap có side effect có thể tạo kết quả khác nhau.
- **C:** Không. `MethodType` là tham số thứ ba cho bootstrap của `invokedynamic`/CallSite; dynamic constant dùng `Class<?>`.
- **D:** Field public có thể đọc nếu class/module phù hợp; field private bị từ chối khi Lookup không còn quyền private.
- **E:** Không. `ofCanonical` có thể trả `ClassDesc` hoặc descriptor chuyên biệt khác; cần dùng interface `ConstantDesc` hoặc kiểm tra kiểu thực tế.
- **F:** JVM ghi nhớ kết quả resolution của mục constant pool đó và không tái chạy bootstrap cho cùng symbolic reference. Gọi `resolveConstantDesc` Java API lại có thể chạy bootstrap mỗi lần.
- **G:** Có. Class descriptor không tự là Class đã load; phải resolve trong ngữ cảnh phù hợp, có thể thất bại khi class không tìm thấy hoặc không truy cập được.
- **H:** Vì resolution có thể tìm và thực thi bootstrap code; dùng Lookup có quyền cao có thể mở khả năng truy cập không dự kiến.

## 12. Nguồn tham khảo Java 17

- [Oracle Javadoc — `DynamicConstantDesc`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/DynamicConstantDesc.html): các factory, metadata, `resolveConstantDesc` và no-cache semantics.
- [Oracle Javadoc — `ConstantDesc`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/ConstantDesc.html): symbolic resolution và Lookup context.
- [Oracle Javadoc — `ConstantDescs`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/ConstantDescs.html): `ofConstantBootstrap` và các BSM chuẩn.
- [Oracle Javadoc — `ConstantBootstraps`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html): `getStaticFinal`, `nullConstant`.
- [Oracle Javadoc — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): quyền truy cập, `lookupClass`, `lookupModes`, `dropLookupMode` và module.
- [JVMS Java SE 17, `5.4.3.6](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6): thuật toán phân giải hằng động/call site.
- [JVMS Java SE 17, `5.4.4](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4): access control khi linking.

**Tổng kết:** `DynamicConstantDesc<T>` là **một mô tả**, không phải giá trị đã tính. `resolveConstantDesc(lookup)` xác định giá trị dựa trên **quyền và môi trường resolution của Lookup**, có thể chạy bootstrap và **không cache** cho lần gọi Java API tiếp theo. Đừng nhầm nó với caching của `CONSTANT_Dynamic` trong runtime constant pool hoặc coi việc tạo descriptor là bằng chứng được phép truy cập một member private.
