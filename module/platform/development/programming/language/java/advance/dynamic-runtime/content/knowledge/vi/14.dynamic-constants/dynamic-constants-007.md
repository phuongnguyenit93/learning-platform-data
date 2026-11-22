# 14.7 Phân biệt descriptor danh nghĩa với đối tượng `Class` hoặc handle đang tồn tại

Trong hệ thống hằng động (*dynamic constant*, **condy**) và các API `java.lang.constant` của Java 17, một **descriptor danh nghĩa** (*nominal descriptor*) là **bản mô tả bằng tên, kiểu và cấu trúc**, có thể lưu/trao đổi để sau này phân giải thành một giá trị thực. Nó **không phải** chính đối tượng runtime mà JVM đang dùng.

Ví dụ trực giác:

- `ClassDesc.of("java.lang.String")` **mô tả** hằng class `String.class`; nó **không phải** `String.class`.
- `MethodTypeDesc` mô tả chữ ký method bằng các `ClassDesc`; nó **không phải** `MethodType` đã chứa các đối tượng `Class<?>` runtime.
- `MethodHandleDesc` mô tả cách tìm một method/field/constructor; nó **không phải** `MethodHandle` có thể gọi bằng `invokeExact`.
- `DynamicConstantDesc` mô tả **cách tính một hằng động** bằng bootstrap method, tên, kiểu và các đối số bootstrap; bản mô tả này **không phải** kết quả đã tính của bootstrap.

Sự khác biệt quan trọng nhất: **descriptor không tự mang class loader, quyền truy cập thực tế hay kết quả bootstrap đã được tính**. Để biến bản mô tả thành đối tượng hiện hữu, cần có ngữ cảnh phân giải, thường là `MethodHandles.Lookup`; việc phân giải có thể thất bại hoặc tạo kết quả khác nhau theo môi trường.

Bài dùng **Java SE 17+** và đặt chủ đề trong ngữ cảnh hằng động, không chỉ dừng ở reflection thông thường.

## 1. Từ hằng trong class file đến descriptor danh nghĩa

JVM class file chứa *constant pool* với những entry có thể biểu diễn kiểu class, method type, method handle, chuỗi, số và hằng động. Một số entry lưu **tham chiếu ký hiệu** thay vì con trỏ đến đối tượng đã được nạp.

Ở Java 12+, package `java.lang.constant` đưa ra các đối tượng Java mô hình hóa cách mô tả những constant-pool entries. Mục đích là để code phân tích/generating bytecode, công cụ runtime hoặc thư viện trao đổi một **công thức mang tính danh nghĩa** mà không buộc phải resolve ngay class/method bên dưới.

Hai tầng cần tách:

~~~text
TẦNG MÔ TẢ (NOMINAL)
  ClassDesc / MethodTypeDesc / MethodHandleDesc / DynamicConstantDesc
                │
                │ resolveConstantDesc(Lookup)
                │ kiểm tra class loader + quyền truy cập + kiểu
                ▼
TẦNG RUNTIME (LIVE)
  Class<?> / MethodType / MethodHandle / giá trị hằng động
                │
                ▼
    so sánh identity, gọi handle, sử dụng giá trị
~~~

Đường từ trên xuống **có điều kiện**, không bảo đảm luôn thành công. Một `ClassDesc` hợp lệ có thể mô tả class **chưa tồn tại** hoặc không truy cập được trong ngữ cảnh hiện tại. Tương tự, `MethodHandleDesc` có thể mô tả method không có trong class đã nạp.

### 1.1. Bảng ánh xạ những kiểu quan trọng

| Bản mô tả danh nghĩa | Đối tượng/value tương ứng khi resolve | Chứa thông tin gì? |
| --- | --- | --- |
| `ClassDesc` | `Class<?>` | Tên kiểu hoặc field descriptor, ví dụ `Ljava/lang/String;` |
| `MethodTypeDesc` | `MethodType` | Các kiểu tham số, kiểu trả về dưới dạng `ClassDesc` |
| `MethodHandleDesc` / `DirectMethodHandleDesc` | `MethodHandle` | Kind (static/virtual/constructor/field...), owner, tên, kiểu lookup hoặc adapter |
| `DynamicConstantDesc<T>` | Giá trị kiểu `T` tương ứng | Bootstrap method descriptor, tên hằng, `ClassDesc` của kiểu hằng và các static bootstrap arguments |
| `String`, `Integer`, `Long`, `Float`, `Double` | Chính các giá trị tương ứng | Những hằng có biểu diễn trực tiếp trong constant pool có thể tự là `ConstantDesc` |

**Ngoại lệ có chủ ý:** không phải **mọi** `ConstantDesc` đều là một object “khác” với giá trị của nó. Ví dụ `String` là `ConstantDesc` cho chính nó. Quy tắc đối chiếu “descriptor ≠ live object” đặc biệt quan trọng đối với `ClassDesc`, `MethodTypeDesc`, `MethodHandleDesc` và `DynamicConstantDesc`.

## 2. `ClassDesc` không phải `Class<?>`

Một tên như `java.lang.String` là **tên danh nghĩa**. JVM chỉ có thể trả lời `Class<?>` nào tương ứng khi đã biết **ngữ cảnh nạp lớp** và quyền truy cập.

~~~java
ClassDesc nominal = ClassDesc.of("java.lang.String");
System.out.println(nominal.descriptorString());
// Ljava/lang/String;

Class<?> live = (Class<?>) nominal.resolveConstantDesc(
        MethodHandles.lookup());
System.out.println(live == String.class); // true
~~~

Đoạn này minh họa trong một method có import phù hợp; chương trình hoàn chỉnh ở phần 7.

- `ClassDesc.of("java.lang.String")` **tạo bản mô tả** từ binary name, chưa tìm `Class` thật.
- `ClassDesc.ofDescriptor("Ljava/lang/String;")` tạo bản mô tả tương đương từ **JVM field descriptor string**.
- `resolveConstantDesc(lookup)` **phân giải** theo class loader và quyền của `Lookup`, trả đối tượng `Class`.
- `nominal.equals(otherNominal)` so cấu trúc danh nghĩa; `liveClassA == liveClassB` so **cùng đối tượng class runtime**.

### 2.1. Hai cách ghi tên không được lẫn

| Ý nghĩa | Ví dụ |
| --- | --- |
| Binary name dùng với `ClassDesc.of` | `java.lang.String` |
| JVM field descriptor dùng với `ClassDesc.ofDescriptor` | `Ljava/lang/String;` |
| Descriptor primitive `int` | `I` hoặc `ConstantDescs.CD_int` |
| Descriptor mảng `String[]` | `[Ljava/lang/String;` |
| Binary name của nested class `Outer.Inner` | `pkg.Outer$Inner` |

Không truyền `"Ljava/lang/String;"` vào `ClassDesc.of` như thể đó là binary name; dùng `ClassDesc.ofDescriptor`. Với primitive, dùng các hằng định nghĩa sẵn trong `ConstantDescs` hoặc descriptor primitive tương ứng.

### 2.2. Có mô tả vẫn chưa chắc có class

~~~java
ClassDesc unknown = ClassDesc.of("example.missing.NotThere");
System.out.println(unknown.descriptorString());
// Lexample/missing/NotThere;
~~~

Dòng trên thành công dù ứng dụng không có class `example.missing.NotThere`. Chỉ khi thử phân giải:

~~~java
Class<?> missing = (Class<?>) unknown.resolveConstantDesc(
        MethodHandles.lookup());
~~~

mới có thể ném `ClassNotFoundException` (một `ReflectiveOperationException`) hoặc lỗi truy cập/liên kết khác tùy tình huống.

**Không dùng khả năng xây `ClassDesc` thành công làm phép kiểm tra dependency đã cài đặt, module đã readable hoặc class đã được nạp.**

## 3. Cùng descriptor danh nghĩa có thể resolve thành hai `Class` khác nhau

Trong JVM, định danh runtime của một class thường được xác định bằng **binary name + defining class loader**. Hai class loader độc lập có thể định nghĩa hai class **cùng tên** nhưng không phải cùng một kiểu Java.

~~~text
                   ClassDesc
          "app.api.Payload"
                │
       ┌────────┴────────┐
       ▼                 ▼
  Lookup ở loader A  Lookup ở loader B
       │                 │
       ▼                 ▼
  Class<?> A          Class<?> B
  tên "app.api.Payload" ở cả hai
              A != B
~~~

`ClassDesc` **không chứa** reference đến loader A hay B, nên bản mô tả có thể `equals` nhau, trong khi các đối tượng `Class<?>` nhận được từ hai ngữ cảnh khác nhau **không `==` nhau**.

Hệ quả thực tế:

- Một API trả `ClassDesc` đang nói “kiểu có **tên này**”, chứ chưa bảo đảm đó là `Class<?>` mà một plugin hoặc framework cụ thể đã load.
- `Class.cast`, `instanceof`, reflection và `MethodHandle` kiểm tra theo **kiểu runtime thực**, không theo chuỗi tên. Có tên giống nhau vẫn có thể gây `ClassCastException`.
- Nếu library nhận descriptor và cần resolve nó, hãy truyền/thiết kế đúng `Lookup` của caller có quyền và loader thích hợp. Không tự tiện thay bằng `ClassLoader.getSystemClassLoader()` nếu ứng dụng có plugin loader riêng.
- Các giới hạn module (JPMS) và quyền truy cập có thể khiến resolution thất bại ngay cả khi class tồn tại.

Phần 8 cung cấp một ví dụ **chạy thực tế với hai `URLClassLoader`** xác nhận nhận định này.

## 4. `MethodTypeDesc` không phải `MethodType`

`MethodTypeDesc` chứa **chữ ký danh nghĩa** bằng các `ClassDesc`. Ví dụ một method nhận `String` và trả `String`:

~~~java
MethodTypeDesc nominalType = MethodTypeDesc.of(
        ConstantDescs.CD_String, ConstantDescs.CD_String);
System.out.println(nominalType.descriptorString());
// (Ljava/lang/String;)Ljava/lang/String;

MethodType liveType = (MethodType) nominalType.resolveConstantDesc(
        MethodHandles.lookup());
System.out.println(liveType);
// (String)String
~~~

Ở ví dụ này:

- `MethodTypeDesc` trả lời câu hỏi *method có tham số/kiểu trả về được mô tả thế nào?*
- `MethodType` là đối tượng runtime đã mang các đối tượng `Class<?>` thật của tham số và kết quả.
- Dạng `(Ljava/lang/String;)Ljava/lang/String;` là **JVM method descriptor**, còn `(String)String` là dạng in dễ đọc của `MethodType`. Hai cách biểu diễn không phải cùng object.

**Điểm tương thích Java 17:** phương thức `resolveConstantDesc` khi gọi qua nhiều interface descriptor trong Java 17 có kiểu trả về khai báo là `Object`, vì vậy ví dụ dùng cast tường minh `(MethodType)`, `(Class<?>)` hoặc `(MethodHandle)` khi cần. Không chép nguyên chữ ký trả về covariant từ Java mới hơn vào bài Java 17 mà không kiểm chứng.

Mô tả có thể tồn tại trước khi class liên quan được nạp. `MethodTypeDesc` còn có thể biểu diễn những chữ ký không thể tạo thành `MethodType` hợp lệ (ví dụ vượt giới hạn số slot tham số JVM). Đó là một lý do nữa khiến **tạo description** và **resolve thành live type** là hai bước khác nhau.

## 5. `MethodHandleDesc` không phải `MethodHandle`

Một `MethodHandleDesc` cho phép nói về **handle sẽ được tìm**, mà chưa có handle đang sẵn sàng gọi. Với method `public static String decorate(String)` trong class `NominalVsLiveDemo`:

~~~java
MethodTypeDesc signature = MethodTypeDesc.of(
        ConstantDescs.CD_String, ConstantDescs.CD_String);

DirectMethodHandleDesc nominalHandle = MethodHandleDesc.ofMethod(
        DirectMethodHandleDesc.Kind.STATIC,
        ClassDesc.of("NominalVsLiveDemo"),
        "decorate",
        signature);

MethodHandle liveHandle = (MethodHandle) nominalHandle.resolveConstantDesc(
        MethodHandles.lookup());
System.out.println(liveHandle.type()); // (String)String
~~~

Đoạn trên là một **trích đoạn** từ chương trình hoàn chỉnh ở phần 7.

Bản mô tả có các thành phần: **reference kind** (`STATIC`), **owner** (`ClassDesc`), **member name** (`decorate`), và **lookup method type** (`(String)String` ở dạng descriptor). Khi phân giải, JVM/`Lookup` mới kiểm tra method thực sự tồn tại, có đúng kind và chữ ký, và caller có quyền tìm method hay không.

| `MethodHandleDesc` | `MethodHandle` |
| --- | --- |
| Mô tả symbolic target/adapter | Reference runtime đến khả năng gọi method/field/constructor hoặc adapter |
| Có thể tạo dù method chưa có trong classpath | Chỉ tồn tại khi đã lấy được handle hợp lệ |
| Không có `invokeExact` để chạy nghiệp vụ | Có `invokeExact`, `invoke`, `type()`, combinator... |
| Dùng `resolveConstantDesc(lookup)` để tìm handle thật | Có thể `describeConstable()` để đề nghị tạo descriptor ngược, **nếu biểu diễn được** |
| So descriptor bằng `equals` | Không suy identity từ cùng descriptor; chú trọng `type()` và ngữ nghĩa khi gọi |

Đối với method instance (ví dụ kind `VIRTUAL`), **lookup descriptor** của method chỉ mô tả các tham số method khai báo, còn **invocation type của handle** thường có thêm **receiver ở tham số đầu**. Không nhầm `lookupDescriptor` với `invocationType()` khi thiết kế method handle danh nghĩa.

### 5.1. Descriptor của method vắng mặt vẫn tạo được

~~~java
DirectMethodHandleDesc missing = MethodHandleDesc.ofMethod(
        DirectMethodHandleDesc.Kind.STATIC,
        ClassDesc.of("NominalVsLiveDemo"),
        "noSuchMethod",
        MethodTypeDesc.of(
                ConstantDescs.CD_String, ConstantDescs.CD_String));
~~~

Tạo descriptor này **không gọi** và **không tìm** `noSuchMethod`. Nhưng `missing.resolveConstantDesc(lookup)` sẽ thất bại, chẳng hạn với `NoSuchMethodException` ở ví dụ đã kiểm chứng.

Với tên method thực nhưng caller thiếu quyền truy cập, lỗi có thể là `IllegalAccessException`. Với class không thể resolve, lỗi có thể đến sớm hơn ở bước class resolution. Đừng biến tất cả lỗi này thành “MethodHandleDesc sai cú pháp”.

### 5.2. Không phải handle runtime nào cũng mô tả ngược được

Interface `Constable` có `describeConstable()` trả `Optional<ConstantDesc>` (hoặc subtype phù hợp). `MethodHandle` implement `Constable`, nhưng không phải mọi chuỗi adapter, handle bind object, closure hay handle động đều có biểu diễn danh nghĩa phù hợp.

~~~java
java.util.Optional<java.lang.constant.MethodHandleDesc> description =
        liveHandle.describeConstable();
~~~

Đây là đoạn minh họa với biến `liveHandle` có sẵn. `Optional.empty()` là một trường hợp hợp lệ; **không** gọi `orElseThrow()` vô điều kiện để suy rằng mọi handle đều có descriptor. Direct handle đơn giản thường có thể mô tả ngược, còn các handle tổ hợp có thể không.

Ngay cả khi `describeConstable()` trả `Optional` có giá trị, đó vẫn là **description**, không phải một cơ chế giữ nguyên **object identity** của handle hoặc toàn bộ state của chương trình để mang qua JVM khác.

## 6. `DynamicConstantDesc` và hằng động thực trong constant pool

Đây là mối liên hệ trực tiếp với chủ đề **14. Hằng động**.

### 6.1. Condy thực sự trong class file

Một class file Java 11+ có thể chứa entry `CONSTANT_Dynamic_info` (tag 17), chỉ đến:

~~~text
CONSTANT_Dynamic_info:
  bootstrap_method_attr_index  -> bootstrap method + static arguments
  name_and_type_index          -> constant name + field descriptor

Ví dụ lý thuyết:
  name: MY_VALUE
  type: Ljava/lang/String;
  bootstrap: ConstantBootstraps.invoke
  static args: method handle mô tả decorate(String)String, "Java"
~~~

Đây là **sơ đồ**, không phải dump `javap` từ chương trình phần 7. `CONSTANT_Dynamic_info` được resolve khi bytecode `ldc` / `ldc_w` / `ldc2_w` dùng hằng đó (hoặc nó được resolve làm static bootstrap argument).

Trong quá trình **resolution**, JVM lấy:

1. `MethodHandles.Lookup` gắn với class chứa symbolic reference.
2. **Tên hằng** dạng `String`, ví dụ `MY_VALUE`.
3. **Kiểu hằng thực** dưới dạng `Class<?>` (ví dụ `String.class`), **không phải** `MethodType`.
4. Các **static bootstrap arguments** đã được resolve.

BSM được thực thi để tính **một giá trị** phù hợp với field descriptor của hằng, chẳng hạn một `String` hoặc `Class<?>`. JVM xác minh/chuyển đổi kết quả theo quy tắc JVMS. Sau resolution thành công, cùng symbolic reference trong runtime constant pool trả lại **kết quả đã liên kết** mà không chạy lại BSM; lỗi resolution cũng được ghi nhớ.

### 6.2. `DynamicConstantDesc` chỉ là bản mô tả, chưa phải entry JVM đã link

`DynamicConstantDesc.ofNamed(...)` tạo một **nominal descriptor trong heap Java**:

~~~java
DynamicConstantDesc<String> desc = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_INVOKE,
        "MY_VALUE",
        ConstantDescs.CD_String,
        nominalHandle,
        "Java");
~~~

Đây là trích đoạn có `nominalHandle` từ phần 5. Nó mô tả bootstrap chuẩn `ConstantBootstraps.invoke`, tên hằng, kiểu `String`, và hai static arguments (mô tả method handle + chuỗi `Java`). **Chưa có giá trị `String` nào được tính chỉ vì xây object `desc`.**

Ý nghĩa mỗi thành phần:

| Thành phần | Giá trị ví dụ | Chưa phải |
| --- | --- | --- |
| `bootstrapMethod()` | `ConstantDescs.BSM_INVOKE` — một `DirectMethodHandleDesc` | Live `MethodHandle` của BSM |
| `constantName()` | `MY_VALUE` | Tên field Java buộc phải tồn tại |
| `constantType()` | `ConstantDescs.CD_String` — `ClassDesc` cho loại kết quả | Live `String.class` hay một string value |
| `bootstrapArgs()` | Descriptor của `decorate` và chuỗi `"Java"` | Lời gọi `decorate("Java")` đã diễn ra |
| `resolveConstantDesc(lookup)` | Tính giá trị theo ngữ cảnh hiện tại | Bước “tạo descriptor” đơn thuần |

**Hai nghĩa của từ `Class` trong ví dụ cần phân biệt:**

- `ClassDesc.of("java.lang.String")` ở phần 2 **mô tả class constant** có giá trị khi resolve là **`String.class`**.
- `dynamic.constantType() == ConstantDescs.CD_String` nói **kiểu của hằng động sẽ trả về là `String`**, nên `dynamic.resolveConstantDesc(...)` trả một **chuỗi**, không phải đối tượng `Class<?>`.

Nếu hằng động muốn trả chính một `Class<?>`, `constantType` sẽ mô tả kiểu `java.lang.Class`, ví dụ `ConstantDescs.CD_Class`; kết quả của BSM vẫn phải là một giá trị có kiểu tương ứng. Không nhầm kiểu của **kết quả** với class mà kết quả đang mô tả.

### 6.3. Điểm khác nhau lớn: có cache hay không?

Hai con đường sau **không có cùng nghĩa cache**:

~~~text
A. Phân giải descriptor từ API Java:
  DynamicConstantDesc instance
    ├─ resolveConstantDesc(lookup) -> chạy bootstrap, tạo value A
    └─ resolveConstantDesc(lookup) -> có thể chạy bootstrap lại, value B

B. JVM resolve CONSTANT_Dynamic_info của class file:
  constant-pool symbolic reference
    ├─ resolution lần đầu -> chạy bootstrap, ghi nhận kết quả
    └─ các lần dùng sau    -> cùng kết quả, KHÔNG chạy lại bootstrap
~~~

Javadoc Java 17 của `ConstantDesc.resolveConstantDesc` nói rõ **không cache kết quả phân giải**. Trong khi đó JVMS `5.4.3` quy định **resolution của một symbolic reference trong runtime constant pool** được ghi nhớ; bootstrap của condy thực không tự chạy lại mỗi lần dùng cùng symbolic reference. Cần phân biệt cả hai trước khi suy về performance, side effect hoặc identity.

Trong chương trình phần 7, gọi `dynamic.resolveConstantDesc(lookup)` hai lần khiến hàm `decorate` tăng counter hai lần. Đây **không phải** bằng chứng JVM đã chạy bootstrap **hai lần cho cùng một entry `CONSTANT_Dynamic_info`**; chương trình này không phát ra entry condy tương ứng.

### 6.4. Không nhầm condy với `invokedynamic`

| Điểm | `CONSTANT_Dynamic_info` (condy) | `CONSTANT_InvokeDynamic_info` |
| --- | --- | --- |
| Bytecode sử dụng phổ biến | `ldc` / `ldc_w` / `ldc2_w` | `invokedynamic` |
| Kiểu mô tả trong `NameAndType` | **Field descriptor** của giá trị (ví dụ `Ljava/lang/String;`) | **Method descriptor** của điểm gọi (ví dụ `(I)Ljava/lang/String;`) |
| BSM nhận kiểu đích | `Class<?>` | `MethodType` |
| Kết quả bootstrap | Một **giá trị hằng** | Một **`CallSite`** |
| Sau khi liên kết | Dùng lại giá trị đã resolve của symbolic reference | Chỉ thị đã link dùng site đã chọn để dispatch target |
| Mô hình danh nghĩa Java | `DynamicConstantDesc` | Không đồng nhất với `DynamicConstantDesc`; thông tin điểm gọi là metadata `invokedynamic` |

Mặc dù đều dùng BSM, **hằng động** không phải là “một method handle luôn được gọi mỗi lần”, còn **invokedynamic** không phải “một hằng chuỗi được tính một lần”. BSM của condy có thể **trả về MethodHandle hoặc Class object như một giá trị**, nhưng vẫn là hằng được resolve, không tự biến thành call site.

## 7. Ví dụ Java 17 hoàn chỉnh: tạo descriptor, resolve, gọi handle và quan sát condy descriptor

Lưu chương trình dưới tên **`NominalVsLiveDemo.java`**. Chạy trên class path trong thư mục chứa file. Đoạn này **thực thi `DynamicConstantDesc.resolveConstantDesc` qua API Java**, không tự biên dịch thành một constant-pool `CONSTANT_Dynamic_info`. Nó đặc biệt hữu ích vì cho thấy sự khác biệt giữa lúc **mô tả** và lúc **resolve**.

~~~java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.DirectMethodHandleDesc;
import java.lang.constant.DynamicConstantDesc;
import java.lang.constant.MethodHandleDesc;
import java.lang.constant.MethodTypeDesc;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class NominalVsLiveDemo {
    static int calls;

    public static String decorate(String input) {
        calls++;
        return "value(" + input + "):" + calls;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        ClassDesc classDesc = ClassDesc.of("java.lang.String");
        ClassDesc equivalent = ClassDesc.ofDescriptor("Ljava/lang/String;");
        System.out.println("class symbolic: " + classDesc.descriptorString());
        System.out.println("same description: " + classDesc.equals(equivalent));
        Class<?> actualClass = (Class<?>) classDesc.resolveConstantDesc(lookup);
        System.out.println("resolved class is String: " + (actualClass == String.class));

        MethodTypeDesc typeDesc = MethodTypeDesc.of(
                ConstantDescs.CD_String, ConstantDescs.CD_String);
        MethodType actualType = (MethodType) typeDesc.resolveConstantDesc(lookup);
        System.out.println("method descriptor: " + typeDesc.descriptorString());
        System.out.println("runtime method type: " + actualType);

        DirectMethodHandleDesc handleDesc = MethodHandleDesc.ofMethod(
                DirectMethodHandleDesc.Kind.STATIC,
                ClassDesc.of("NominalVsLiveDemo"),
                "decorate", typeDesc);
        MethodHandle actualHandle = (MethodHandle) handleDesc.resolveConstantDesc(lookup);
        System.out.println("handle descriptor type: " +
                handleDesc.invocationType().descriptorString());
        System.out.println("runtime handle type: " + actualHandle.type());
        System.out.println("direct handle describable: " +
                actualHandle.describeConstable().isPresent());

        DynamicConstantDesc<String> dynamic = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_INVOKE,
                "MY_VALUE",
                ConstantDescs.CD_String,
                handleDesc,
                "Java");
        System.out.println("dynamic name: " + dynamic.constantName());
        System.out.println("dynamic type: " + dynamic.constantType().descriptorString());
        System.out.println("calls before resolve: " + calls);
        System.out.println("resolve first: " + dynamic.resolveConstantDesc(lookup));
        System.out.println("resolve second: " + dynamic.resolveConstantDesc(lookup));
        System.out.println("calls after resolve: " + calls);
        System.out.println("handle invocation: " + (String) actualHandle.invokeExact("API"));

        ClassDesc missing = ClassDesc.of("example.missing.NotThere");
        System.out.println("missing symbol: " + missing.descriptorString());
        try {
            missing.resolveConstantDesc(lookup);
            throw new AssertionError("Expected missing class failure");
        } catch (ReflectiveOperationException e) {
            System.out.println("missing resolve: " + e.getClass().getSimpleName());
        }

        DirectMethodHandleDesc absentMethod = MethodHandleDesc.ofMethod(
                DirectMethodHandleDesc.Kind.STATIC,
                ClassDesc.of("NominalVsLiveDemo"),
                "noSuchMethod", typeDesc);
        System.out.println("missing method described: " +
                absentMethod.methodName());
        try {
            absentMethod.resolveConstantDesc(lookup);
            throw new AssertionError("Expected missing method failure");
        } catch (ReflectiveOperationException e) {
            System.out.println("missing method resolve: " + e.getClass().getSimpleName());
        }
    }
}
~~~

Lệnh chạy với **JDK 17 trở lên**:

~~~bash
javac --release 17 NominalVsLiveDemo.java
java NominalVsLiveDemo
~~~

**Stdout chính xác đã kiểm chứng** (OpenJDK 21 chạy mã biên dịch ở mức Java 17):

~~~text
class symbolic: Ljava/lang/String;
same description: true
resolved class is String: true
method descriptor: (Ljava/lang/String;)Ljava/lang/String;
runtime method type: (String)String
handle descriptor type: (Ljava/lang/String;)Ljava/lang/String;
runtime handle type: (String)String
direct handle describable: true
dynamic name: MY_VALUE
dynamic type: Ljava/lang/String;
calls before resolve: 0
resolve first: value(Java):1
resolve second: value(Java):2
calls after resolve: 2
handle invocation: value(API):3
missing symbol: Lexample/missing/NotThere;
missing resolve: ClassNotFoundException
missing method described: noSuchMethod
missing method resolve: NoSuchMethodException
~~~

**Đọc kết quả theo từng tầng:**

1. Hai `ClassDesc` cấu trúc giống nhau nên `same description: true`. Chỉ ở bước resolution mới lấy được `Class<?>` thực, rồi kiểm tra `== String.class`.
2. `MethodTypeDesc` in ra JVM descriptor, còn `MethodType` in `(String)String`. Đó là hai object ở hai tầng khác nhau.
3. `handleDesc` mô tả `decorate(String)String`; `actualHandle` là handle thật. Có thể gọi `actualHandle.invokeExact("API")`; không thể dùng `invokeExact` trực tiếp trên `handleDesc`.
4. `calls before resolve: 0` chứng minh **chỉ xây `DynamicConstantDesc` chưa thực thi `decorate`**.
5. Hai lần gọi `resolveConstantDesc` tạo `value(Java):1` và `value(Java):2` — **không có cache** ở con đường API này.
6. Sau đó `handle invocation` cho `value(API):3`, chứng minh live handle là một khả năng gọi đang tồn tại với state của class thật.
7. `ClassDesc` cho class vắng mặt và `MethodHandleDesc` cho method vắng mặt đều xây thành công; chúng chỉ lỗi khi **resolve**.

Lưu ý: chương trình cố tình dùng `static int calls` để quan sát tác dụng phụ. Một bootstrap hằng thực trong class file có quy tắc cache khác; không dùng counter của chương trình này để suy số lần BSM của JVM cho condy thực.

## 8. Ví dụ Java 17 hoàn chỉnh: cùng `ClassDesc` nhưng hai class loader khác nhau

Đây là bài thực hành chuyên về **identity**. Lưu file **`LoaderResolutionDemo.java`** cùng thư mục (hoặc một thư mục mới) với nội dung:

~~~java
import java.lang.constant.ClassDesc;
import java.lang.invoke.MethodHandles;
import java.net.URL;
import java.net.URLClassLoader;

public class LoaderResolutionDemo {
    public static class Marker {}

    public static void main(String[] args) throws Throwable {
        ClassDesc nominal = ClassDesc.of(Marker.class.getName());
        URL root = LoaderResolutionDemo.class.getProtectionDomain().getCodeSource().getLocation();

        try (URLClassLoader loaderOne = new URLClassLoader(
                     new URL[] {root}, ClassLoader.getPlatformClassLoader());
             URLClassLoader loaderTwo = new URLClassLoader(
                     new URL[] {root}, ClassLoader.getPlatformClassLoader())) {

            Class<?> first = Class.forName(Marker.class.getName(), false, loaderOne);
            Class<?> second = Class.forName(Marker.class.getName(), false, loaderTwo);
            MethodHandles.Lookup accessOne =
                    MethodHandles.privateLookupIn(first, MethodHandles.lookup());
            MethodHandles.Lookup accessTwo =
                    MethodHandles.privateLookupIn(second, MethodHandles.lookup());

            System.out.println("one name: " + first.getName());
            System.out.println("same name: " + first.getName().equals(second.getName()));
            System.out.println("same live Class: " + (first == second));
            System.out.println("same nominal: " +
                    first.describeConstable().orElseThrow().equals(
                            second.describeConstable().orElseThrow()));
            System.out.println("resolve one: " + (nominal.resolveConstantDesc(accessOne) == first));
            System.out.println("resolve two: " + (nominal.resolveConstantDesc(accessTwo) == second));
        }
    }
}
~~~

Lưu ý về điều kiện chạy: biên dịch file này ra **thư mục class bình thường** rồi chạy từ class path; ở đây `CodeSource` là URL của thư mục chứa các file `.class`. Hai `URLClassLoader` dùng **platform loader làm parent** để không tự động ủy quyền nạp `LoaderResolutionDemo$Marker` cho application loader. Vì cả hai có thể đọc cùng bytecode nhưng tự định nghĩa class, chúng tạo **hai `Class<?>` khác nhau**. `privateLookupIn` cấp ngữ cảnh lookup phù hợp cho từng bản trong ví dụ chạy trên class path/unnamed module; trong named module có thể cần cấu hình `opens` phù hợp.

~~~bash
javac --release 17 LoaderResolutionDemo.java
java LoaderResolutionDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
one name: LoaderResolutionDemo$Marker
same name: true
same live Class: false
same nominal: true
resolve one: true
resolve two: true
~~~

Ý nghĩa:

- `first.getName().equals(second.getName())` là `true` nhưng `first == second` là `false`.
- Hai bản `ClassDesc` do `Class.describeConstable()` tạo ra **bằng nhau về mô tả**.
- `nominal.resolveConstantDesc(accessOne)` phân giải ra `first`, trong khi `nominal.resolveConstantDesc(accessTwo)` phân giải ra `second`.
- Vì vậy **descriptor danh nghĩa không gắn chặt với một đối tượng `Class<?>` hoặc loader cụ thể**. Đừng lấy `ClassDesc.equals` làm thay thế cho kiểm tra loader identity khi viết plugin framework.

Trong ví dụ không tạo live `MethodHandle` từ hai loader vì chỉ cần chứng minh khác biệt ở **Class** là đủ. Khi handle được phân giải trong hai môi trường như vậy, kiểu của `MethodHandle` có thể tham chiếu những `Class<?>` khác identity và hành vi cast/invocation cũng chịu ảnh hưởng.

## 9. `Constable.describeConstable` là đường ngược có điều kiện

API `java.lang.constant.Constable` hỗ trợ hỏi một đối tượng runtime có thể **tự mô tả** bằng descriptor hay không:

~~~text
LIVE OBJECT                    NOMINAL DESCRIPTOR
String.class        --describeConstable()--> ClassDesc
MethodType          --describeConstable()--> MethodTypeDesc
direct MethodHandle --describeConstable()--> MethodHandleDesc
                                       │
                                       ▼
                        resolveConstantDesc(lookup)
                                       │
                                       ▼
                        LIVE OBJECT tương ứng
~~~

Nhưng `describeConstable()` trả **`Optional`**, không phải cam kết luôn có giá trị. Một handle phức tạp do combinator hoặc bind state runtime có thể không có representation danh nghĩa tương đương, nên có thể trả `Optional.empty()`.

Hơn nữa, kể cả với một descriptor hợp lệ:

- Descriptor có thể được resolve trong **ngữ cảnh `Lookup` khác**, dẫn tới live class/handle khác hoặc lỗi truy cập.
- Không có cam kết **object identity** giữa object ban đầu và object được tạo lại từ description. `Class<?>` cùng loader có thể là cùng class, nhưng `MethodHandle` mới không cần `==` handle trước.
- `describeConstable()` không phải serialization tổng quát của heap, thread, class loader hay captured state.

**Cách so sánh đúng:** dùng `equals` cho nominal descriptor, dùng `Class<?> ==` khi cần class identity, dùng `MethodType.equals` để kiểm tra chữ ký runtime, và gọi `MethodHandle` theo hợp đồng kiểu/đối số thay vì suy luận từ tên in ra.

## 10. Những nhầm lẫn thường gặp khi làm việc với condy

| Nhận định sai | Điều thực sự cần nhớ |
| --- | --- |
| “`ClassDesc` là một `Class<?>` nhẹ.” | Nó là **bản mô tả danh nghĩa**, không có quyền truy cập, loader và metadata runtime như `Class<?>`. |
| “Tạo được `ClassDesc.of(name)` tức là class tồn tại.” | Chỉ resolve mới biết; có thể gặp `ClassNotFoundException` hoặc vấn đề access/linkage. |
| “Hai `ClassDesc` bằng nhau thì hai runtime `Class` chắc chắn là một.” | Không. Resolver dùng `Lookup` và loader; hai loader có thể định nghĩa hai class khác nhau cùng tên. |
| “`MethodTypeDesc` chính là `MethodType`.” | `MethodTypeDesc` chứa chữ ký ở dạng danh nghĩa; `MethodType` chứa class runtime đã resolve. |
| “`MethodHandleDesc` gọi được bằng `invokeExact`.” | Chỉ **`MethodHandle` đã resolve** có các API gọi. |
| “Một mô tả method hợp lệ bảo đảm method tồn tại.” | Có thể mô tả method vắng mặt; resolution mới tìm và kiểm tra quyền. |
| “Mọi `MethodHandle.describeConstable()` đều có giá trị.” | Trả `Optional`, có thể rỗng cho handle không biểu diễn được trong constant pool. |
| “`DynamicConstantDesc.ofNamed` đã chạy BSM.” | Chỉ xây recipe; BSM được gọi khi cố resolve bằng API hoặc khi JVM link hằng động thật. |
| “`constantType()` trả chính giá trị hằng động.” | Nó trả **`ClassDesc` mô tả kiểu kết quả**, không trả value. |
| “`resolveConstantDesc` cache như `ldc` thật.” | Java API này **không cache**; resolution của symbolic reference condy trong JVM **được ghi nhớ**. |
| “Condy và `invokedynamic` đều trả `CallSite`.” | Condy trả **giá trị kiểu field descriptor**; invokedynamic yêu cầu **`CallSite`**. |
| “`javac` tạo `CONSTANT_Dynamic_info` mỗi khi tôi tạo `DynamicConstantDesc`.” | Tạo descriptor bằng Java source **không chèn** constant-pool entry vào class file. Cần công cụ/generator bytecode phù hợp nếu muốn thật sự emit condy. |
| “Thêm `--add-opens` chữa mọi lỗi loader.” | Quyền module và class identity là hai vấn đề riêng; flag không hợp nhất hai bản class do loader khác nhau định nghĩa. |

## 11. Quy trình thực hành khi debug

1. **Xác định loại đang có:** `ClassDesc` hay `Class<?>`? `MethodHandleDesc` hay `MethodHandle`? `DynamicConstantDesc` hay chính giá trị? Dùng tên class/API thật, không dựa vào chuỗi `toString()`.
2. **Ghi cấu trúc danh nghĩa:** `descriptorString()`, owner, kind, method name, `invocationType()`, constant name/type, bootstrap method và bootstrap args.
3. **Ghi ngữ cảnh resolve:** `Lookup.lookupClass()`, class loader/module của caller, quyền module/package. Với nhiều plugin, dùng đúng `Lookup` có quyền trong vùng cần phân giải.
4. **Resolve có kiểm soát:** gọi `resolveConstantDesc(lookup)` trong test chấp nhận `ReflectiveOperationException` và `LinkageError` phù hợp; tránh chạy bootstrap có side effects trong đường chẩn đoán không được phép.
5. **Đối chiếu runtime:** `Class<?> ==`, `MethodType.equals`, `MethodHandle.type()`; nếu được phép, gọi handle với `invokeExact` đúng descriptor và input kiểm soát.
6. **Nếu liên quan condy thực:** đọc `javap -v -p` hoặc công cụ classfile để tìm `CONSTANT_Dynamic_info`, `BootstrapMethods`, tên/field descriptor; đừng chỉ nhìn object `DynamicConstantDesc` trong heap rồi mặc định classfile có condy.
7. **Phân biệt cache:** ghi rõ đang test `DynamicConstantDesc.resolveConstantDesc` từ Java API hay đang thực thi `ldc` tham chiếu hằng động JVM đã link.
8. **Giữ boundary giữa tên và authority:** không xem một chuỗi descriptor do bên ngoài gửi vào như quyền tự động truy cập class/method riêng tư. `Lookup` và kiểm tra của JVM vẫn có ý nghĩa.

## 12. Câu hỏi tự kiểm tra

**1.** `ClassDesc.of("my.plugin.Service")` tạo được khi JAR chưa có trên classpath. Điều đó chứng minh `Service.class` đã tồn tại chưa?  
**Đáp:** Chưa. Descriptor chỉ lưu mô tả danh nghĩa. Resolution trong một loader/`Lookup` thực mới quyết định class có tồn tại/truy cập được hay không.

**2.** Hai class loader riêng biệt cùng định nghĩa `my.plugin.Service`. Hai `ClassDesc` tạo từ tên đó bằng nhau; các `Class<?>` tương ứng có nhất thiết `==` không?  
**Đáp:** Không. Runtime class identity còn phụ thuộc defining loader.

**3.** `MethodHandleDesc.ofMethod(...)` trỏ tới một method không tồn tại. Khi nào thường phát hiện lỗi?  
**Đáp:** Khi `resolveConstantDesc(lookup)` cố tìm method, không phải lúc tạo description.

**4.** Một `DynamicConstantDesc<String>` có `constantType()==CD_String`. Gọi `constantType()` có trả chuỗi `String` đã được bootstrap tạo không?  
**Đáp:** Không. Nó trả một `ClassDesc` cho **loại kết quả**, không phải value.

**5.** Với `DynamicConstantDesc.resolveConstantDesc(lookup)` hai lần, bootstrap có thể chạy hai lần không? Nếu cùng `CONSTANT_Dynamic_info` được dùng nhiều lần bằng `ldc` thì sao?  
**Đáp:** API reflective **không cache**, nên có thể thực thi BSM hai lần. JVM resolution thành công của **cùng symbolic reference** trong runtime constant pool được ghi nhớ; các lần dùng sau không gọi lại BSM.

**6.** Bạn cần gọi một method được mô tả bởi `DirectMethodHandleDesc`. Trước khi `invokeExact`, cần API nào?  
**Đáp:** `resolveConstantDesc(lookup)` để nhận `MethodHandle` có kiểu phù hợp, sau đó gọi `invokeExact` với descriptor chính xác.

**7.** Vì sao không nên dùng kết quả `describeConstable()` để kiểm tra hai function object có cùng identity?  
**Đáp:** Nó mô tả công thức danh nghĩa khi biểu diễn được, **không** cam kết identity của object runtime hoặc captured state.

**8.** Một bootstrap cho hằng động trả `MethodHandle`. Điều đó có biến condy thành `invokedynamic` không?  
**Đáp:** Không. Condy vẫn là hằng với kiểu kết quả `MethodHandle`; `invokedynamic` là điểm gọi động được link tới `CallSite`.

## Tài liệu chuẩn (Java 17)

- [`java.lang.constant`: Nominal Descriptors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/package-summary.html)
- [`ConstantDesc.resolveConstantDesc` và quy tắc không cache](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/ConstantDesc.html)
- [`ClassDesc`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/ClassDesc.html)
- [`MethodTypeDesc`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/MethodTypeDesc.html)
- [`MethodHandleDesc` và `DirectMethodHandleDesc`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/MethodHandleDesc.html)
- [`DynamicConstantDesc`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/DynamicConstantDesc.html)
- [`Constable`, `ConstantDescs`, `ConstantBootstraps`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/Constable.html)
- [JVMS 17 `4.4.10: `CONSTANT_Dynamic_info`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4.10)
- [JVMS 17 `5.4.3: Resolution và bộ nhớ kết quả](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3)
- [JVMS 17 `5.4.3.6: Resolution of dynamic constants and call sites](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)