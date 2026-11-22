# Phân biệt bootstrap class loader với bootstrap method của invokedynamic

Trong Java có hai thuật ngữ đều chứa chữ **bootstrap**, nhưng nói về **hai cơ chế JVM hoàn toàn khác nhau**:

1. **Bootstrap class loader** (bộ nạp lớp bootstrap) là thành phần của cơ chế **nạp và định nghĩa class**: nó chịu trách nhiệm cho nhiều lớp nền tảng của Java runtime, chẳng hạn `java.lang.String` và `java.lang.invoke.LambdaMetafactory` trên JDK 17 thông thường. Trong API `Class.getClassLoader()`, lớp do bootstrap class loader định nghĩa được biểu diễn bởi `null`.
2. **Bootstrap method (BSM) của `invokedynamic`** là một **phương thức hoặc method handle dùng để liên kết một dynamic call site**. JVM gọi nó trong quá trình resolve/liên kết một lệnh `invokedynamic`, mong nhận một `java.lang.invoke.CallSite`. BSM có thể do thư viện/JDK hoặc **chính ứng dụng** định nghĩa; không có yêu cầu rằng class chứa BSM phải được bootstrap class loader nạp.

**Câu nhớ nhanh:** *Bootstrap class loader trả lời “ai định nghĩa class này?”; bootstrap method của `invokedynamic` trả lời “liên kết điểm gọi động này với target nào?”*

Sự trùng chữ *bootstrap* mang ý nghĩa “thiết lập thứ ban đầu” trong hai ngữ cảnh khác nhau, **không có quan hệ đồng nhất**. Dù BSM là method của một class được bootstrap loader nạp (ví dụ `LambdaMetafactory`), điều đó là **đặc điểm của ví dụ**, không phải quy tắc định nghĩa BSM.

Bài học này giới thiệu cơ chế ở mức class loading và bytecode, các mục `CONSTANT_InvokeDynamic` / `BootstrapMethods` trong ClassFile, vai trò `MethodHandles.Lookup` và `CallSite`, lỗi thường gặp, cùng một **chương trình Java 17 biên dịch/chạy được** và lệnh `javap` để tự quan sát.

## 1. Bảng so sánh trực tiếp

| Tiêu chí | Bootstrap class loader | Bootstrap method của invokedynamic |
| --- | --- | --- |
| Bản chất | Thành phần của cơ chế tải và định nghĩa class trong JVM | Method handle/phương thức JVM sử dụng để link một dynamic call site |
| Đơn vị xử lý | Class/interface được JVM định nghĩa từ bytecode/runtime image | Một call-site specifier của bytecode `invokedynamic` |
| Mục đích | Làm cho một `Class<?>` tồn tại với đúng defining loader/type identity | Tạo kết quả liên kết dưới dạng `CallSite` với target `MethodHandle` phù hợp |
| Đầu vào đặc trưng | Tên class, bytecode/module/source tùy loader/runtime | `Lookup` của caller, tên điểm gọi, `MethodType`, static bootstrap arguments |
| Kết quả | Một định nghĩa `Class<?>` có thể được JVM sử dụng | Một `CallSite`; lần gọi động dùng target của call site |
| API quan sát | `Class.getClassLoader()`; `ClassLoader`; `jcmd`/class loading logs | `javap -v -p`: `InvokeDynamic`, `BootstrapMethods`; `java.lang.invoke` |
| Có nhất thiết nằm trong Java code ứng dụng? | Bootstrap loader là cơ chế runtime, không nhất thiết là đối tượng Java `ClassLoader` bình thường | Custom bootstrap method có thể viết bằng Java; thường khai báo public static và trả `CallSite` |
| Có nhất thiết liên quan tới nhau? | Không | Không; việc BSM được định nghĩa trong class bootstrap-loaded chỉ là một khả năng |
| Lỗi đặc trưng | `ClassNotFoundException`, `NoClassDefFoundError`, `LinkageError` liên quan loading/linking | `BootstrapMethodError` nếu liên kết BSM/call site không hợp lệ hoặc BSM thất bại |

Cả hai cùng tham gia hoạt động chung của JVM, nhưng **điểm bắt đầu, mục tiêu, điều kiện lỗi và vòng đời khác nhau**.

## 2. Bootstrap class loader: định nghĩa class nền tảng

Một kiểu tham chiếu trong JVM được định danh bằng cặp:

~~~text
Type identity = (binary name, defining class loader)
~~~

Bootstrap class loader là loader nền tảng cốt lõi. Java API dùng `null` để đại diện cho nó tại `Class.getClassLoader()`; đây **không phải NullPointerException, không phải “class chưa được nạp”**, mà là cách biểu diễn có chủ đích.

Ví dụ Java 17 thông thường:

~~~java
System.out.println(String.class.getClassLoader() == null);
System.out.println(
        java.lang.invoke.LambdaMetafactory.class.getClassLoader() == null);
~~~

Đây là **fragment** cần đặt trong method; hai dòng in `true` trên JDK 17 tiêu chuẩn.

### Vai trò trong mô hình delegation

Một lộ trình nạp class điển hình:

~~~text
Custom/plugin class loader
          |
          v
Application/system class loader
          |
          v
Platform class loader
          |
          v
Bootstrap class loader
          |
          v
Các class nền tảng thích hợp, ví dụ java.lang.String
~~~

Đây là mô hình khái quát parent delegation, **không bảo đảm mọi custom loader đều tuân thủ một cây duy nhất**. Java 9+ có runtime image theo module; không nên tưởng rằng bootstrap loader chỉ đọc từ `rt.jar` (file đó đã bị loại bỏ từ Java 9) hay rằng mọi class `jdk.*`/`javax.*` đều do bootstrap nạp.

Một custom loader thông thường không được tự định nghĩa lớp trong package bắt đầu bằng `java.` bằng `defineClass`; API có các ràng buộc và có thể ném `SecurityException`. Một số module nền tảng được gán cho **platform loader**, nên với class cụ thể hãy kiểm tra `Class.getClassLoader()`/`Class.getModule()` thay vì đoán chỉ từ tên package.

### Khi nào hoạt động?

Bootstrap class loader tham gia mỗi khi JVM cần nạp những lớp nền tảng phù hợp: khởi động JVM, resolve dependency, dùng API Java, link một method hoặc quá trình khởi tạo khác. **Nó không được gọi theo nghĩa “một phương thức BSM chạy mỗi khi gặp lambda”**. Nó là cơ chế **định nghĩa kiểu**, không phải factory cho dynamic call site.

Một class ứng dụng bình thường khi chạy bằng:

~~~bash
java BootstrapTerminologyDemo
~~~

thường do **system/application class loader** định nghĩa, trong khi các lớp `java.lang.*`/`java.lang.invoke.*` nền tảng của ví dụ do bootstrap loader định nghĩa. Cả hai có thể cùng được sử dụng trong quá trình liên kết một lệnh `invokedynamic`.

## 3. Bootstrap method của invokedynamic là gì?

`invokedynamic` là một opcode trong JVM instruction set, lần đầu được giới thiệu từ Java 7 (JSR 292). Khác lời gọi cố định như `invokestatic` hay `invokevirtual` vốn có symbolic reference đến method/class theo cơ chế riêng, `invokedynamic` dùng một **call-site specifier** trong constant pool để yêu cầu JVM **liên kết một điểm gọi động**.

Mỗi `invokedynamic` được biểu diễn bằng một entry kiểu `CONSTANT_InvokeDynamic_info` trong constant pool và tham chiếu tới một entry thuộc class-file attribute **`BootstrapMethods`**. Entry này mô tả BSM thông qua một `CONSTANT_MethodHandle` cùng các tham số bootstrap tĩnh nếu có.

~~~text
ClassFile chứa phương thức của caller
  |
  +-- bytecode: invokedynamic #N
  |                   |
  |                   v
  +-- constant_pool[N]: CONSTANT_InvokeDynamic_info
  |           +-- tên điểm gọi + method descriptor
  |           +-- bootstrap_method_attr_index
  |                                 |
  |                                 v
  +-- BootstrapMethods attribute
              +-- bootstrap_method_ref
              |       (CONSTANT_MethodHandle)
              +-- bootstrap_arguments[]
                      |
                      v
         JVM resolve/liên kết dynamic call site
                      |
                      v
         Invoke bootstrap method handle
                      |
                      v
              CallSite / target
                      |
                      v
           lệnh invokedynamic gọi target
~~~

BSM không có nhiệm vụ “nạp toàn bộ ứng dụng”. Vai trò của nó là giúp JVM quyết định **MethodHandle target cho một dynamic call site cụ thể**. Chính JVM chịu trách nhiệm quản lý resolution/linkage, kiểm tra method type và lựa chọn kết quả liên kết theo quy tắc JVMS.

### Dạng chữ ký BSM dễ gặp

Một BSM điển hình có ba đối số đầu do JVM cung cấp:

~~~java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String invokedName,
        MethodType invokedType,
        Object... staticArguments) throws Throwable
~~~

Đây là **chữ ký khái quát**, không phải method runnable độc lập. BSM thực tế có thể dùng các kiểu cố định khác cho static arguments. Những loại method handle được phép làm bootstrap method còn chịu quy tắc của JVMS; **không nên khẳng định mọi BSM bắt buộc là một public static Java method y hệt chữ ký trên**. Trên thực tế nhiều BSM hữu ích là static method.

Ý nghĩa:

- `caller` / `Lookup`: bối cảnh class caller và khả năng lookup/access tương ứng; không nên nhầm với class loader mặc định toàn JVM.
- `invokedName`: tên của dynamic call site theo constant pool, **không nhất thiết là tên một Java method thật trên class được gọi**.
- `invokedType` / `MethodType`: kiểu tham số/return mà lệnh `invokedynamic` yêu cầu.
- `staticArguments`: tham số được biên dịch ghi trong entry `BootstrapMethods`; ví dụ các `MethodType`, `MethodHandle`, chuỗi recipe cho nối chuỗi.
- `CallSite`: đối tượng nắm một **target `MethodHandle`** tương thích với descriptor điểm gọi.

Sau khi liên kết thành công, việc thực thi tiếp theo của dynamic call site **không cần gọi lại BSM mỗi lần** để nhận cùng kết quả liên kết. JVM gọi target đã liên kết theo quy tắc `CallSite`. Một số điều kiện như **resolution đồng thời** có thể khiến BSM được thực thi nhiều lần trong quá trình tranh chấp liên kết; không được xem BSM là constructor bảo đảm đúng **một lần toàn cục**.

## 4. Vì sao BSM không bắt buộc được bootstrap class loader nạp?

Xét hai trường hợp:

**Trường hợp A — thư viện nền tảng:**

~~~text
Lớp application: Demo (application loader)
    |
    +-- bytecode invokedynamic (lambda)
           |
           +-- BSM handle trỏ LambdaMetafactory.metafactory
                    |
                    +-- LambdaMetafactory thuộc java.base,
                        thường bootstrap-loaded
                    |
                    +-- trả CallSite hợp lệ cho lambda
~~~

**Trường hợp B — bootstrap method tự viết:**

~~~text
Lớp application: App (application loader)
    |
    +-- invokedynamic có BSM handle tới com.acme.runtime.DynamicLinker
           |
           +-- DynamicLinker cũng có thể application/plugin-loaded
           |
           +-- DynamicLinker.bootstrap(...) trả CallSite
~~~

Đối với trường hợp B, JVM vẫn phải **resolve class chứa BSM** và method handle theo quy tắc class loading/access. Nhưng việc class ấy thuộc application loader **không làm BSM mất tư cách bootstrap method**. Từ *bootstrap* ở đây nghĩa là **khởi tạo thông tin liên kết cho call site**, không phải phải chạy bên trong bootstrap class loader.

Một phương thức Java public static do ứng dụng viết chỉ trở thành **BSM của một call site** khi **ClassFile thực sự có bootstrap method reference thích hợp** và JVM resolve call site bằng nó. Chỉ đặt tên method là `bootstrap`, chỉ gọi nó từ source Java, hoặc chỉ import `java.lang.invoke.*` **không tự sinh lệnh `invokedynamic` trỏ tới method ấy**.

Trong Java source thông thường, tạo custom `invokedynamic` call-site specifier thường cần compiler/runtime tạo bytecode phù hợp hoặc công cụ sinh/chỉnh sửa ClassFile (ASM, Byte Buddy, compiler của một ngôn ngữ JVM, v.v.). Ví dụ phần tiếp theo dùng `javac` Java 17 sinh `invokedynamic` chuẩn cho lambda và nối chuỗi, **không tự tạo BSM tùy biến bằng source thuần**.

## 5. Ví dụ Java 17 độc lập: phân biệt hai khái niệm ngay khi chạy

Tạo **một file** `BootstrapTerminologyDemo.java`:

~~~java
import java.lang.invoke.LambdaMetafactory;

public class BootstrapTerminologyDemo {
    @FunctionalInterface
    interface TextTask {
        String run();
    }

    static String makeMessage(String name) {
        return "Hello, " + name;
    }

    public static void main(String[] args) {
        System.out.println("String bootstrap-loaded: " +
                (String.class.getClassLoader() == null));

        System.out.println("LambdaMetafactory bootstrap-loaded: " +
                (LambdaMetafactory.class.getClassLoader() == null));

        System.out.println("Demo application-loaded: " +
                (BootstrapTerminologyDemo.class.getClassLoader()
                        == ClassLoader.getSystemClassLoader()));

        TextTask task = () -> "lambda target";
        System.out.println("Lambda result: " + task.run());

        String name = args.length == 0 ? "Java" : args[0];
        System.out.println("Concat result: " + makeMessage(name));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên, trong thư mục chứa file:

~~~bash
javac --release 17 BootstrapTerminologyDemo.java
java BootstrapTerminologyDemo
~~~

**Stdout chính xác** với lệnh trên trong môi trường JDK 17 tiêu chuẩn:

~~~text
String bootstrap-loaded: true
LambdaMetafactory bootstrap-loaded: true
Demo application-loaded: true
Lambda result: lambda target
Concat result: Hello, Java
~~~

### Mỗi dòng đang đo điều gì?

1. `String.class.getClassLoader() == null` chứng tỏ `String` là class do **bootstrap class loader** định nghĩa theo quy ước API.
2. `LambdaMetafactory.class.getClassLoader() == null` minh họa BSM thư viện JDK cũng được chứa trong một **class bootstrap-loaded**. Điều này **không đồng nhất** class loader với bootstrap method.
3. `BootstrapTerminologyDemo.class.getClassLoader() == ClassLoader.getSystemClassLoader()` cho biết trong cách khởi chạy classpath tiêu chuẩn này, demo là class thuộc **application/system loader**.
4. Biểu thức lambda `() -> "lambda target"` được `javac` Java 17 thông thường biên dịch thành dynamic call site sử dụng `LambdaMetafactory.metafactory`; gọi `task.run()` thực thi implementation trả chuỗi.
5. Nối chuỗi động `"Hello, " + name` trong `makeMessage` được compiler Java 17 thông thường biên dịch thông qua cơ chế **`invokedynamic` với `StringConcatFactory.makeConcatWithConstants`**. Đầu ra là `Hello, Java`.

**Chú ý độ chắc chắn của ví dụ:** Các dòng in được xác định bởi code và cách chạy classpath tiêu chuẩn. Chi tiết về **số lượng lệnh `invokedynamic`, thứ tự constant-pool entries và chỉ số bootstrap method** trong `javap` có thể khác giữa bản JDK/compiler hoặc tùy chọn biên dịch; chúng **không được dùng làm giá trị stdout cố định**.

### 5.1. Kiểm tra bytecode bằng javap -v -p

Chạy:

~~~bash
javap -v -p BootstrapTerminologyDemo
~~~

Lệnh trên in nhiều thông tin ClassFile. Hãy tìm các cụm:

~~~text
InvokeDynamic
BootstrapMethods:
LambdaMetafactory.metafactory
StringConcatFactory.makeConcatWithConstants
~~~

Đây là **các chuỗi cần tìm trong bản disassembly**, không phải bản sao đầy đủ của output `javap` (các chỉ số constant pool khác nhau). Với `javac --release 17` mặc định, nên quan sát:

- Một `invokedynamic` liên quan đến **tạo lambda** `TextTask`, có BSM là `java/lang/invoke/LambdaMetafactory.metafactory`.
- Ít nhất một `invokedynamic` liên quan đến **nối chuỗi**, có BSM là `java/lang/invoke/StringConcatFactory.makeConcatWithConstants`.
- Một **`BootstrapMethods` attribute** trong ClassFile liệt kê method handles và bootstrap arguments.
- Một hoặc nhiều `InvokeDynamic` constant-pool entries chỉ về thông tin bootstrap và tên/type của call site.

Một đoạn **minh họa rút gọn**, không phải toàn bộ kết quả của compiler:

~~~text
BootstrapMethods:
  ... REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants
  ... REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory
~~~

Trong bản in thật, `javap` kèm method descriptor, constant-pool indices và `Method arguments:`. Mã `() -> "lambda target"` còn có thể xuất hiện dưới dạng method tổng hợp `lambda$main$0` trong class chứa lambda. Tên/chỉ số và cách tổ chức implementation có thể thay đổi; điều quan trọng là **call-site reference và BSM handle được compiler ghi vào ClassFile**.

### 5.2. Câu hỏi đọc ngược kết quả

Khi `LambdaMetafactory` được nạp bởi bootstrap class loader nhưng lambda nằm trong `BootstrapTerminologyDemo`:

- **Ai định nghĩa `LambdaMetafactory.class`?** Bootstrap class loader, theo `getClassLoader() == null`.
- **Ai định nghĩa `BootstrapTerminologyDemo.class`?** Application/system class loader trong demo.
- **Ai quyết định cách liên kết `invokedynamic` của lambda?** JVM sử dụng **bootstrap method handle** trỏ `LambdaMetafactory.metafactory` để nhận một `CallSite` phù hợp.
- **Tên “bootstrap” nào có ý nghĩa khi đọc `BootstrapMethods` attribute?** **Bootstrap method của call-site linkage**, không phải danh sách class do bootstrap class loader nạp.

Nếu đổi BSM sang một method phù hợp được ứng dụng định nghĩa trong ClassFile khác, loader chứa BSM có thể là application/plugin loader nhưng cơ chế `invokedynamic` vẫn đúng nguyên tắc.

## 6. Chu trình liên kết invokedynamic chi tiết

Có thể hình dung theo các bước:

### Bước A — class chứa invokedynamic được định nghĩa

Một defining class loader (application loader, plugin loader hoặc loader khác) định nghĩa class chứa `invokedynamic`. JVM đọc ClassFile và thông tin constant pool/attributes của class.

**Điều này chưa đồng nghĩa mỗi dynamic call site đã link ngay.** JVM quyết định thời điểm resolution phù hợp; không nên gán cứng rằng BSM luôn chạy đúng lúc `ClassLoader#defineClass` hoặc chỉ khi lệnh được thực thi lần đầu.

### Bước B — JVM resolve call-site specifier

Khi cần liên kết một `invokedynamic`, JVM resolve thông tin tương ứng:

~~~text
CONSTANT_InvokeDynamic_info
  bootstrap_method_attr_index
  name_and_type_index
       |
       v
BootstrapMethods[bootstrap_method_attr_index]
  bootstrap_method_ref
  bootstrap_arguments[]
~~~

BSM method handle có thể trỏ tới một method trong class do **một class loader bất kỳ phù hợp** định nghĩa. Quá trình resolve method handle này có thể dẫn đến nạp những class liên quan, nhưng **không đổi identity của các class đã định nghĩa**.

### Bước C — JVM truyền arguments tới BSM

JVM cung cấp bối cảnh caller (`Lookup`), tên `invokedynamic`, descriptor (`MethodType`) và các bootstrap arguments tĩnh. Ví dụ `LambdaMetafactory.metafactory` sử dụng các thông tin phương thức SAM, target implementation method và instantiated method type để trả một call site cho lambda.

Đối với string concatenation, `StringConcatFactory` có thể sử dụng recipe và các constants để xây một target làm phép nối chuỗi phù hợp.

### Bước D — BSM trả CallSite

`java.lang.invoke.CallSite` chứa target `MethodHandle`. Tùy mục tiêu liên kết, có các implementation như:

- **`ConstantCallSite`:** target không thay đổi sau khi được thiết lập; phù hợp nhiều dynamic call sites ổn định.
- **`MutableCallSite`:** target có thể được đổi theo cơ chế của API, cần chú ý visibility giữa threads.
- **`VolatileCallSite`:** mục đích cung cấp ngữ nghĩa quan sát update target theo điều kiện giống volatile phù hợp API.

`invokedynamic` yêu cầu method type của call site/target tương thích với descriptor được dùng. BSM không thể trả `null` hoặc một CallSite có type sai rồi mong JVM tự ép một cách tùy tiện; resolution sẽ thất bại theo quy tắc liên kết.

### Bước E — lệnh invokedynamic gọi target đã link

Sau khi call site được liên kết hợp lệ, `invokedynamic` dùng target `MethodHandle`. JVM có thể tối ưu hóa và biên dịch JIT đường đi; nhưng về mặt ngữ nghĩa, **BSM thiết lập đường liên kết**, còn **target thực thi logic của lời gọi**.

### Cẩn thận với phát biểu “bootstrap method chỉ chạy một lần”

Với một call-site specifier đã liên kết, BSM không chạy lại trên mỗi lần thực thi target. Tuy nhiên, khi **nhiều thread cùng đua liên kết** một điểm gọi chưa được resolve, JVMS cho phép thực hiện BSM đồng thời nhiều lần rồi chọn một kết quả để liên kết. Vì vậy:

- Đừng đặt **side effect quan trọng cần đúng-một-lần** trong BSM mà không có thiết kế đồng bộ/idempotency thích hợp.
- Không coi BSM như constructor singleton global của JVM.
- Có thể có nhiều `invokedynamic` call sites sử dụng cùng BSM mà vẫn có quá trình liên kết riêng.
- Liên kết có thể có điều kiện fail/cache lỗi theo quy tắc JVM, không phải luôn thử lại mỗi lần gọi.

## 7. BSM tự viết khác với phương thức bình thường ở đâu?

Về **mã Java**, BSM có thể là một method tĩnh trả `CallSite`. Ví dụ **fragment minh họa**, không phải chương trình chạy trực tiếp và **chưa có lệnh `invokedynamic` tham chiếu tới nó**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class DynamicLinker {
    public static String hello() {
        return "hello from target";
    }

    public static CallSite bootstrap(
            MethodHandles.Lookup caller,
            String name,
            MethodType invokedType) throws Throwable {

        MethodHandle target = caller.findStatic(
                DynamicLinker.class, "hello", invokedType);

        return new ConstantCallSite(target);
    }
}
~~~

Điều kiện để đoạn BSM này được sử dụng đúng:

1. Một ClassFile phải chứa **`CONSTANT_InvokeDynamic_info` / `BootstrapMethods`** tham chiếu `DynamicLinker.bootstrap` bằng method handle hợp lệ.
2. Descriptor `invokedType` của call site phải phù hợp target `DynamicLinker.hello`: trong ví dụ, không có tham số, trả `String`.
3. `Lookup` phải có quyền truy cập target method theo ngữ cảnh caller (ở ví dụ này `hello` public), cùng những điều kiện liên kết khác.
4. JVM resolve và gọi BSM, BSM trả `ConstantCallSite`. Sau đó target mới được `invokedynamic` gọi.

Nếu chỉ viết:

~~~java
DynamicLinker.bootstrap(lookup, "hello", methodType);
~~~

đây chỉ là một **lời gọi method Java thông thường** trong source (với biến `lookup`, `methodType` phù hợp). Nó không tự tạo một bytecode `invokedynamic` để JVM liên kết bằng BSM đó. **Sự khác nhau nằm ở cách ClassFile trỏ đến BSM trong một call-site specifier**, không nằm ở việc method có tên `bootstrap` hay được gọi từ đâu.

### BSM có thể là code ứng dụng/plugin

`DynamicLinker` hoàn toàn có thể được nạp bởi một custom/plugin class loader hợp lệ. Nó vẫn là BSM nếu được JVM resolve từ `BootstrapMethods` attribute của một class caller. Trái lại, `LambdaMetafactory` ở JDK 17 là class nền tảng nhưng **không phải chính bootstrap class loader**; nó là một class chứa các phương thức factory có thể được dùng làm BSM.

## 8. invokedynamic, LambdaMetafactory và nối chuỗi

Hai trường hợp `javac` Java 17 thường tự sinh `invokedynamic` mà người viết source không phải trực tiếp viết opcode:

### 8.1. Lambda expression

~~~java
Runnable task = () -> System.out.println("work");
task.run();
~~~

Đây là fragment hợp lệ trong method. Compiler thường mã hóa **tạo instance functional interface** bằng `invokedynamic`. BSM điển hình là `LambdaMetafactory.metafactory` hoặc một biến thể khác như `altMetafactory` khi cần thuộc tính bổ sung.

**Không nhầm hai thời điểm:**

- Khi `invokedynamic` tạo lambda được liên kết, BSM cung cấp call site/target cho cơ chế tạo functional-interface instance.
- Khi code gọi `task.run()`, đó là **lời gọi interface lên lambda object** được tạo, không có nghĩa JVM gọi `LambdaMetafactory.metafactory` lại ở mỗi lần `run()`.

Một lambda có thể được JVM triển khai qua class sinh động hoặc hidden class ở những implementation hiện đại, nhưng **chi tiết lớp hỗ trợ là nội bộ runtime**; không nên viết logic nghiệp vụ giả định tên class lambda, tên module hoặc bytecode được sinh luôn bất biến.

### 8.2. Nối chuỗi bằng dấu +

~~~java
String who = "Java";
String greeting = "Hello, " + who;
~~~

Nếu compiler xác định biểu thức có phần phải động, `javac` Java 17 mặc định thường sinh `invokedynamic` liên quan `StringConcatFactory.makeConcatWithConstants`. Những phép nối **toàn hằng** có thể được constant-fold ngay tại compile time và **không cần invokedynamic**.

Trong demo phần 5, `makeMessage(String name)` nhận một tham số runtime, nên đường nối chuỗi động có thể nhìn thấy qua `javap -v -p`.

### 8.3. Về ngôn ngữ JVM khác

`invokedynamic` được thiết kế để hỗ trợ liên kết động do JVM quản lý, hữu ích cho compiler và runtime của những ngôn ngữ JVM khác hoặc các cơ chế call-site linh hoạt. Nó không chỉ phục vụ lambda/nối chuỗi. BSM có thể cung cấp target được tùy biến theo call-site name, signature và static args, miễn tuân thủ hợp đồng liên kết.

## 9. Phân biệt với ConstantDynamic (condy)

Trong ClassFile Java hiện đại còn có `CONSTANT_Dynamic_info`, thường gọi **dynamic constant** hoặc *condy*. Nó cũng sử dụng **`BootstrapMethods` attribute** để mô tả bootstrap method, nhưng mục tiêu khác:

| Cơ chế | Bootstrap method dùng để tạo ra gì? |
| --- | --- |
| **`CONSTANT_InvokeDynamic_info` / invokedynamic** | Một **`CallSite`** để liên kết điểm gọi động. |
| **`CONSTANT_Dynamic_info` / dynamic constant** | Một **giá trị constant** đã được resolve theo loại yêu cầu, không phải CallSite bắt buộc. |

BSM của condy có các đối số đầu tương tự nhưng đối số kiểu đích là **`Class<?>`** của constant chứ không phải `MethodType` của call site; kết quả là giá trị constant theo quy tắc JVM. Không nên thấy chữ `BootstrapMethods` trong ClassFile rồi mặc định đó luôn là metadata riêng của `invokedynamic`.

Cả hai vẫn khác **bootstrap class loader**: condy BSM cũng không bắt buộc sống trong class do bootstrap class loader định nghĩa.

## 10. Lỗi thường gặp: loading failure khác bootstrap linking failure

| Triệu chứng | Cơ chế cần điều tra | Gợi ý |
| --- | --- | --- |
| `ClassNotFoundException` khi custom loader tìm class | **Class loading** | Classpath/module path, tên nhị phân, parent delegation, nguồn bytes. |
| `NoClassDefFoundError` khi cần định nghĩa phụ thuộc | **Loading/linking của class** | Thiếu class, initialization failure trước đó, loader visibility. |
| `ClassCastException: A cannot be cast to A` | **Type identity** | Hai defining loader khác nhau định nghĩa cùng tên; không phải bản thân BSM bắt buộc sai. |
| `SecurityException` khi cố định nghĩa `java.*` | **Protected platform namespace** | Không tự override class nền tảng bằng loader ứng dụng. |
| `BootstrapMethodError` khi sử dụng invokedynamic | **Bootstrap linkage** | BSM method handle sai, BSM ném exception, trả `null`/`CallSite` sai type, quyền truy cập phụ thuộc. |
| `WrongMethodTypeException` ở MethodHandle invocation | **Signature/type của method handle** | `MethodType`, `invokeExact`/`invoke` và khả năng adaptation. |
| `IllegalAccessError`/lỗi truy cập | **Resolution/module access** | Lookup caller, `exports`/`opens`, member access và defining loader. |
| `ExceptionInInitializerError` từ static initializer | **Class initialization** | `<clinit>` ném exception; đây là pha khác với BSM liên kết call site. |

`BootstrapMethodError` thuộc họ `LinkageError`. Nó thường báo thất bại trong resolve/bootstrap dynamic call site hoặc dynamic constant; **không có nghĩa bootstrap class loader đã hỏng**. Khi thấy lỗi, hãy đọc toàn bộ stack trace và **cause**, tìm method handle/BSM đang được dùng và type mà site mong đợi.

Một BSM có thể thất bại bởi method handle target sai descriptor, không đủ quyền access, exception trong user code hoặc cấu hình phụ thuộc thiếu. Cần kiểm tra cả **ClassFile** và **loader đã định nghĩa BSM class**, nhưng không tự sửa bằng cách ép BSM về bootstrap loader.

### Những điều kiện không thể bỏ qua

- `CallSite` trả về phải không null và có target `MethodHandle` với type phù hợp với invokedynamic descriptor.
- Nếu dùng `ConstantCallSite`, target ổn định; `MutableCallSite`/`VolatileCallSite` có ngữ nghĩa cập nhật riêng, không phải “mọi lần gọi đều link lại”.
- BSM được JVM gọi **trong quá trình linking**; lỗi có thể phát sinh lười khi call site được resolve, không nhất thiết ngay lúc nạp class chứa bytecode.
- BSM method handle/caller context chịu kiểm tra resolution/access như những symbolic references liên quan khác. Tên class loader không tự cấp quyền bỏ qua JPMS.
- Đừng nuốt `BootstrapMethodError` rồi thử chạy một method tùy tiện khác nếu không có fallback được thiết kế riêng; có thể che lỗi ABI/linkage nghiêm trọng.

## 11. Chẩn đoán thực tế: nhìn class loader và bytecode theo hai hướng

Khi gặp một class dùng lambda/chuỗi hoặc một framework có dynamic bytecode, nên điều tra theo thứ tự:

### Bước 1 — class nào đang chứa invokedynamic?

Chạy:

~~~bash
javap -v -p -classpath . BootstrapTerminologyDemo
~~~

Hãy xác định method có `invokedynamic`, constant-pool entry `InvokeDynamic` và phần `BootstrapMethods`. Nếu class nằm trong JAR, dùng classpath phù hợp thay `.` và tên binary class tương ứng.

### Bước 2 — method handle bootstrap trỏ đi đâu?

Trong `BootstrapMethods`, tìm tên chủ sở hữu/BSM:

~~~text
java/lang/invoke/LambdaMetafactory.metafactory
java/lang/invoke/StringConcatFactory.makeConcatWithConstants
com/acme/runtime/DynamicLinker.bootstrap
~~~

Đây là các **ví dụ tên symbolic**, không mặc định cùng tồn tại trong một ClassFile. Với chương trình ở phần 5 chỉ có hai nhóm đầu.

### Bước 3 — loader nào định nghĩa caller, BSM owner và các API types?

Ví dụ **fragment**:

~~~java
System.out.println(callerClass.getClassLoader());
System.out.println(bsmOwnerClass.getClassLoader());
System.out.println(callerClass.getModule());
System.out.println(bsmOwnerClass.getModule());
~~~

Đoạn này đòi có hai biến `Class<?>` `callerClass` và `bsmOwnerClass` hợp lệ. Không thay `bsmOwnerClass` bằng `BootstrapMethods`: **attribute không phải class Java**. Khi thấy `null` ở `getClassLoader()`, đó thường là dấu hiệu defining loader là bootstrap, **không chứng minh method đang được JVM dùng làm BSM**.

### Bước 4 — kiểm tra signature và bootstrap arguments

BSM `invokedynamic` phải nhận arguments theo JVMS và trả `CallSite` đúng signature. Với `LambdaMetafactory`, kiểm tra functional interface, implementation method handle và instantiated method type. Với `StringConcatFactory`, kiểm tra recipe/constants và dynamic argument count phù hợp.

### Bước 5 — tách ba nguyên nhân thường bị gộp

1. **Loader không tìm được BSM owner hoặc dependency**: lỗi loading/visibility ban đầu.
2. **BSM owner được nạp nhưng BSM invocation thất bại**: lỗi bootstrap linkage.
3. **BSM liên kết thành công nhưng target/user logic lỗi khi chạy**: có thể là exception từ target, **không nhất thiết `BootstrapMethodError`**.

Các công cụ quan sát có thể hỗ trợ nhưng không nên đồng nhất:

- `-Xlog:class+load=info` (HotSpot Java 17) có thể giúp quan sát nguồn/class được nạp.
- `javap -v -p` giúp xem `invokedynamic`/`BootstrapMethods` trong file đã biên dịch.
- Stack trace/cause và thread dump giúp phân biệt lỗi BSM, initialization và code target.
- Thông tin `Class.getClassLoader()` / `Class.getModule()` giúp theo dõi type identity/module.

Ví dụ chạy có logging:

~~~bash
java -Xlog:class+load=info BootstrapTerminologyDemo
~~~

**Không có stdout cố định** cho lệnh này vì logging có nhiều dòng phụ thuộc JDK/runtime và môi trường; hãy tập trung vào class nguồn và loader, không coi log là bản thay thế `javap`.

## 12. Những hiểu lầm phổ biến

**“Bootstrap method phải được bootstrap class loader nạp.”** Sai. BSM là một method handle để link call site; BSM owner có thể là class ứng dụng/plugin nếu JVM có thể resolve và truy cập hợp lệ.

**“`LambdaMetafactory` là bootstrap class loader.”** Sai. `LambdaMetafactory` là **một class** cung cấp các method factory như `metafactory`; bootstrap class loader là thành phần nạp class đó. Hai đối tượng có bản chất hoàn toàn khác.

**“Nếu `SomeClass.class.getClassLoader() == null` thì phương thức trong class đều là bootstrap methods.”** Sai. `null` nói về loader đã **định nghĩa Class**, không nói method nào xuất hiện trong `BootstrapMethods` attribute của caller.

**“Mọi lệnh nối chuỗi Java 17 đều cần BSM.”** Sai. Compiler có thể gộp các hằng tại compile time. Nối chuỗi có giá trị động mới thường được `javac` mã hóa qua StringConcatFactory.

**“invokedynamic có nghĩa JVM bỏ qua type checking.”** Sai. Call-site descriptor, MethodHandle target, verifier và access rules vẫn được kiểm tra; dynamic linkage không phải cơ chế tắt an toàn kiểu.

**“BSM chạy lại mỗi khi gọi lambda hoặc gọi target.”** Sai. BSM tham gia liên kết call site; target chạy khi invokedynamic được thực thi sau khi đã link. Có ngoại lệ về race resolution, nhưng không phải gọi lại BSM cho mỗi invocation.

**“BSM luôn được gọi đúng một lần.”** Cũng sai. JVM có thể thực hiện bootstrap method hơn một lần trong điều kiện resolution đồng thời cho cùng site rồi chọn một kết quả phù hợp. Không dựa vào BSM như once-only hook cho side effect.

**“Đổi class loader của thread là cách sửa BootstrapMethodError.”** Không có quy tắc như vậy. TCCL chỉ ảnh hưởng những API dùng context loader; linking một symbolic BSM/call site còn phụ thuộc ClassFile owner, access, method type, module và defining loader phù hợp.

**“Chữ BootstrapMethods chỉ xuất hiện cho invokedynamic.”** Không hoàn toàn: dynamic constants (`CONSTANT_Dynamic`) cũng dùng bootstrap methods attribute.

**“Bấm vào lambda expression trong source là thấy BSM.”** Không hẳn. Lambda source không khai báo BSM trực tiếp; compiler ghi `invokedynamic`/`BootstrapMethods` vào ClassFile. Dùng `javap -v -p` để chứng minh.

## 13. Tự kiểm tra kiến thức

**Câu 1.** `String.class.getClassLoader() == null` cho biết điều gì?

**Đáp án:** `String` được bootstrap class loader định nghĩa theo cách biểu diễn Java API. Nó **không** nói rằng constructor hay mọi method của `String` là BSM.

**Câu 2.** `LambdaMetafactory.metafactory` được `javap` liệt kê trong `BootstrapMethods`. Đây là class loader hay method dùng liên kết call site?

**Đáp án:** Một **bootstrap method** dùng trong `invokedynamic` linking; class `LambdaMetafactory` được bootstrap loader nạp là một chuyện khác.

**Câu 3.** Custom BSM trong `com.acme.DynamicLinker` (application loader) có hợp lệ không?

**Đáp án:** Có thể hợp lệ nếu ClassFile có method handle BSM đúng, JVM resolve/access được class/method và BSM trả `CallSite` đúng method type. Không bắt buộc thuộc bootstrap loader.

**Câu 4.** BSM cho invokedynamic thường trả về gì?

**Đáp án:** Một `java.lang.invoke.CallSite` (ví dụ `ConstantCallSite`) với target method handle phù hợp.

**Câu 5.** Ai cung cấp `Lookup`, `name`, `MethodType` cho BSM?

**Đáp án:** JVM theo thông tin call-site specifier/constant pool và bối cảnh caller khi link `invokedynamic`.

**Câu 6.** Nếu method target đã được link rồi, JVM có phải gọi lại BSM mỗi lần thực thi target không?

**Đáp án:** Không. Call site giữ target theo ngữ nghĩa loại `CallSite`; BSM thuộc pha link, còn target thuộc pha chạy.

**Câu 7.** Một `BootstrapMethodError` có chứng minh bootstrap class loader bị lỗi không?

**Đáp án:** Không. Nó báo vấn đề bootstrap linking (hoặc dynamic constant resolution) và cần kiểm tra BSM handle, arguments, method types và cause.

**Câu 8.** Tại sao `javac --release 17` thường sinh `invokedynamic` cho lambda mà không cần user viết BSM?

**Đáp án:** Java compiler tự tạo `CONSTANT_InvokeDynamic_info` và `BootstrapMethods` tham chiếu thư viện như `LambdaMetafactory`. JVM làm linking theo metadata đó khi chạy.

## Ghi nhớ

- **Bootstrap class loader** = bộ nạp lớp nền tảng, giúp **định nghĩa Class<?>**; những class do nó định nghĩa trả `null` từ `Class.getClassLoader()`.
- **Bootstrap method của invokedynamic** = method handle dùng để **link một call site**, thường nhận `Lookup` + tên + `MethodType` + static args và trả `CallSite`.
- Hai khái niệm có chữ *bootstrap* nhưng **khác nhiệm vụ**. BSM có thể nằm trong JDK hoặc class ứng dụng; nó **không bị ràng buộc phải chạy trong một class bootstrap-loaded**.
- Quan sát class loading bằng `Class.getClassLoader()`; quan sát dynamic linking bằng `javap -v -p`, `InvokeDynamic` và `BootstrapMethods`.
- Khi debug, phân biệt **class loading failure, bootstrap-linking failure và lỗi target execution**; đừng suy từ `BootstrapMethodError` rằng bootstrap class loader hỏng.

**Tài liệu chuẩn Java SE 17:**

- *Java Virtual Machine Specification*, §5.3 (Creation of Classes and Interfaces), §5.4.3.6 (Dynamically-Computed Call Site and Constant Resolution): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- *Java Virtual Machine Specification*, §4.4.10 (`CONSTANT_Dynamic`/`CONSTANT_InvokeDynamic`), §4.7.23 (`BootstrapMethods`): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- *Java Virtual Machine Specification*, §6.5, `invokedynamic`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- Java SE 17 API, `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `java.lang.invoke.LambdaMetafactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html
- Java SE 17 API, `StringConcatFactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html
- Java SE 17 API, `CallSite`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html
