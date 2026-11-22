# Java 15 — `Lookup` trả về và `lookupClass()` của lớp ẩn vừa tạo

## 1. Mục tiêu và vấn đề cần hiểu

Từ Java 15, API `MethodHandles.Lookup.defineHiddenClass(...)` cho phép định nghĩa **hidden class** từ classfile bytes. Một chi tiết rất dễ gây nhầm là **giá trị trả về không phải `Class<?>`**, cũng không phải `MethodHandle`: phương thức trả về một **`MethodHandles.Lookup` mới**, mà **lookup class của nó chính là hidden class vừa được định nghĩa**.

Bài học tập trung trả lời năm câu hỏi:

1. `Lookup` ban đầu của lớp gọi và `Lookup` được `defineHiddenClass(...)` trả về khác nhau ở đâu?
2. Gọi `returnedLookup.lookupClass()` thu được gì, và vì sao cần giữ `Class<?>` đó?
3. Dùng `Lookup` trả về để tạo constructor/method handle, kể cả khi thành viên của lớp ẩn là `private`, như thế nào?
4. Những hiểu nhầm nào dễ xảy ra với `lookupClass()`, `getClass()`, `Class.forName(...)` và ngữ cảnh quyền truy cập?
5. Tham số `initialize`, `lookupModes` và việc truyền một `Lookup` có đặc quyền tác động ra sao trong framework sinh mã runtime?

Các API chính vẫn được hỗ trợ trong những JDK hiện đại, không cần dùng tính năng preview. Ví dụ thực hành có thể biên dịch bằng `--release 15` hoặc `--release 17` tùy API bổ sung được sử dụng.

## 2. Ba đối tượng khác nhau: `host Lookup`, `returned Lookup` và `Class<?>`

Xét phần mã minh họa nằm **trong một phương thức**:

~~~java
MethodHandles.Lookup host = MethodHandles.lookup();
MethodHandles.Lookup generated =
        host.defineHiddenClass(classFileBytes, true);
Class<?> hiddenType = generated.lookupClass();
~~~

Trong đoạn này, `classFileBytes` là mảng `byte[]` chứa classfile hợp lệ, có package phù hợp với `host.lookupClass()`. Ý nghĩa từng biến:

| Giá trị | Kiểu Java | Đại diện cho | Điều cần nhớ |
| --- | --- | --- | --- |
| `host` | `MethodHandles.Lookup` | Ngữ cảnh tra cứu, quyền truy cập của **lớp gọi** | `host.lookupClass()` vẫn là lớp gọi |
| `generated` | `MethodHandles.Lookup` | Ngữ cảnh tra cứu của **hidden class mới** | `generated.lookupClass()` trả về lớp ẩn vừa tạo |
| `hiddenType` | `Class<?>` | Đối tượng class đại diện **định nghĩa lớp ẩn cụ thể** | Có thể truyền cho `findConstructor`, `findVirtual`, reflection, kiểm tra `isHidden()` |
| `instance` (nếu tạo sau đó) | Đối tượng triển khai interface/superclass | Một instance của lớp ẩn | `instance.getClass() == hiddenType` nếu đúng instance được tạo từ lớp ấy |

`MethodHandles.lookup()` hoạt động dựa trên ngữ cảnh lớp đang gọi và trả một `Lookup` có quyền tương ứng. `defineHiddenClass(...)` dùng ngữ cảnh đó để định nghĩa lớp mới rồi **trả về một `Lookup` mới**. Lời gọi **không biến đổi `host` thành `generated`** và không thay đổi `host.lookupClass()`.

**`Lookup.lookupClass()` không phải `Object.getClass()`**:

~~~java
Class<?> lookedUp = generated.lookupClass(); // hidden class
Class<?> lookupType = generated.getClass();  // MethodHandles.Lookup.class
~~~

Đoạn trên là minh họa trong phương thức. `lookupClass()` nói **lớp nào là ngữ cảnh của các phép tra cứu member**; `getClass()` nói **đối tượng `generated` thuộc loại Java gì**. Nếu gọi nhầm `getClass()` rồi truyền vào `findConstructor(...)`, bạn đang làm việc với class `MethodHandles.Lookup` thay vì hidden class vừa tạo.

### 2.1. Sơ đồ quan hệ

~~~text
MethodHandles.lookup()
          |
          v
host Lookup
lookupClass() = Host.class
          |
          | defineHiddenClass(classfileBytes, initialize, options...)
          v
returned Lookup (một Lookup mới)
lookupClass() = HiddenClass<?> (Class.isHidden() == true)
          |
          +--> findConstructor(hiddenType, ...)
          |          |
          |          v
          |      MethodHandle --> instance
          |
          +--> findVirtual(hiddenType, "methodName", ...)
          |          |
          |          v
          |      MethodHandle --> gọi member
          |
          +--> lookupClass() --> Class<?> cụ thể của hidden class
~~~

Cũng từ `host` có thể định nghĩa **nhiều hidden class**. Mỗi lần định nghĩa đều trả một `Lookup` dành cho **lớp mới của lần đó**. Nếu cùng mảng bytecode được định nghĩa hai lần thì hai `Class<?>` nhận được là **hai định nghĩa khác nhau**; đừng dùng tên bytecode nguồn để suy ra chúng phải đồng nhất.

## 3. Hợp đồng của `defineHiddenClass(...)` và `lookupClass()`

Chữ ký API trung tâm:

~~~java
MethodHandles.Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException
~~~

Đây là **chữ ký minh họa**; phương thức thuộc `MethodHandles.Lookup`, không phải hàm tự do để copy nguyên vào một file Java.

| Tham số / giá trị trả về | Ý nghĩa |
| --- | --- |
| `bytes` | Bytecode theo cấu trúc classfile của JVM; phải hợp lệ, có phiên bản được runtime hỗ trợ và mô tả lớp ở cùng package với lookup class |
| `initialize` | `true` yêu cầu JVM khởi tạo hidden class trong quá trình định nghĩa; `false` cho phép trì hoãn đến lúc cần khởi tạo |
| `options` | Các tùy chọn như `NESTMATE` hoặc `STRONG` khi thiết kế cần |
| Giá trị trả về | Một **`Lookup` mới** với ngữ cảnh `lookupClass()` chính là hidden class vừa được định nghĩa |

Trong JDK hiện đại, `Lookup` trả về có **original access** và **full privilege access** đối với lớp ẩn mới. Điều đó cho phép framework dùng `returnedLookup.findConstructor(...)`, `findVirtual(...)` hoặc `findStatic(...)` để tạo method handles với kiểm tra quyền dựa trên **lớp ẩn**. Nó **không cấp quyền truy cập không giới hạn tới mọi lớp/module trong JVM**.

`lookupClass()` trả về một `Class<?>`, không cần ép kiểu bằng tên của hidden class. Nó là **đối tượng class thực**, có thể dùng:

~~~java
Class<?> type = generated.lookupClass();
boolean hidden = type.isHidden();
ClassLoader loader = type.getClassLoader();
~~~

Đây là đoạn mã minh họa trong phương thức, với `generated` là lookup đã được định nghĩa thành công. `ClassLoader` và runtime package/module của hidden class chịu các quy tắc gắn với lookup class ban đầu; việc có defining loader **không làm hidden class trở thành lớp có tên tra được bằng loader**.

### 3.1. Điều kiện cấp quyền khi định nghĩa

`defineHiddenClass(...)` yêu cầu `host` có **full privilege access** và bytecode được phép định nghĩa trong module/package tương ứng. Chẳng hạn:

- `MethodHandles.lookup()` khi gọi trong class của mình thường tạo `Lookup` phù hợp để định nghĩa hidden class trong cùng package của class đó.
- `MethodHandles.publicLookup()` chỉ có quyền truy cập public theo những giới hạn của nó, **không đủ quyền** để định nghĩa hidden class.
- Bytecode chỉ ghi một tên class khác package sẽ không giúp vượt qua kiểm tra quyền; API kiểm tra package và cấu trúc classfile.

Lỗi có thể phát sinh ở bước định nghĩa, liên kết, khởi tạo hay dùng handle: `IllegalAccessException` cho thiếu quyền, `IllegalArgumentException` cho khác package, `ClassFormatError` / `VerifyError` cho classfile không hợp lệ, `UnsupportedClassVersionError` cho phiên bản classfile không được hỗ trợ, và các lỗi linking khác. Không nên dùng việc bắt mọi `Throwable` rồi bỏ qua; hãy ghi nguyên nhân có giá trị chẩn đoán mà không làm lộ dữ liệu nhạy cảm.

## 4. Ví dụ chạy được: lấy `Lookup` trả về, tìm constructor private và method private

Để tập trung vào API Lookup thay vì tự viết bytecode generator, chương trình sau **đọc file `.class` của nested class vừa được `javac` tạo**. Đây là cách thử cơ chế; trong framework thực, bytes thường đến từ một trình sinh bytecode runtime.

Lưu toàn bộ vào **`LookupReturnDemo.java`**:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.function.IntUnaryOperator;

public class LookupReturnDemo {
    public static final class Code implements IntUnaryOperator {
        private final int offset;

        private Code(int offset) {
            this.offset = offset;
        }

        @Override
        public int applyAsInt(int value) {
            return value + offset;
        }

        private String describe() {
            return "offset=" + offset;
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes;
        try (InputStream input = LookupReturnDemo.class
                .getResourceAsStream("LookupReturnDemo$Code.class")) {
            if (input == null) {
                throw new IllegalStateException("No class bytes");
            }
            bytes = input.readAllBytes();
        }

        MethodHandles.Lookup host = MethodHandles.lookup();
        MethodHandles.Lookup generated =
                host.defineHiddenClass(bytes, true);
        Class<?> actualClass = generated.lookupClass();

        System.out.println("hostIsHost=" +
                (host.lookupClass() == LookupReturnDemo.class));
        System.out.println("generatedIsHidden=" + actualClass.isHidden());
        System.out.println("differentFromNamed=" +
                (actualClass != Code.class));
        System.out.println("generatedFullPrivilege=" +
                generated.hasFullPrivilegeAccess());

        MethodHandle constructor = generated.findConstructor(
                actualClass, MethodType.methodType(void.class, int.class));
        IntUnaryOperator instance =
                (IntUnaryOperator) constructor.invoke(7);
        MethodHandle describe = generated.findVirtual(
                actualClass, "describe",
                MethodType.methodType(String.class));

        System.out.println("result=" + instance.applyAsInt(35));
        System.out.println("private=" + (String) describe.invoke(instance));
        System.out.println("instanceIsGenerated=" +
                (instance.getClass() == actualClass));

        try {
            host.findVirtual(actualClass, "describe",
                    MethodType.methodType(String.class));
            System.out.println("hostCanAccessPrivate=true");
        } catch (IllegalAccessException expected) {
            System.out.println("hostCanAccessPrivate=false");
        }

        try {
            Class.forName(actualClass.getName());
            System.out.println("foundByName=true");
        } catch (ClassNotFoundException expected) {
            System.out.println("foundByName=false");
        }
    }
}
~~~

Biên dịch và chạy trên JDK hỗ trợ `--release 15`:

~~~bash
javac --release 15 LookupReturnDemo.java
java LookupReturnDemo
~~~

**Stdout chính xác đã được kiểm chứng:**

~~~text
hostIsHost=true
generatedIsHidden=true
differentFromNamed=true
generatedFullPrivilege=true
result=42
private=offset=7
instanceIsGenerated=true
hostCanAccessPrivate=false
foundByName=false
~~~

### 4.1. Đọc kết quả theo trình tự

**`hostIsHost=true`:** Sau khi tạo hidden class, `host.lookupClass()` **vẫn** là `LookupReturnDemo.class`. `host` không bị đổi lớp đích.

**`generatedIsHidden=true`:** `generated.lookupClass()` trả về class vừa tạo; `Class.isHidden()` trả đúng `true`.

**`differentFromNamed=true`:** Class `Code.class` có tên do `javac` biên dịch và class ẩn được `defineHiddenClass(...)` tạo là **hai lớp khác nhau**, dù class ẩn được xây từ bytes ban đầu của `Code`.

**`generatedFullPrivilege=true`:** `Lookup` trả về có full privilege trong ngữ cảnh hidden class mới, nên có thể tạo handle tới các thành viên `private` của chính lớp ấy.

**`result=42`:** `generated.findConstructor(actualClass, MethodType.methodType(void.class, int.class))` tạo một method handle tới constructor `private Code(int)` của hidden class. Gọi handle với `7` tạo instance, sau đó `applyAsInt(35)` trả `42`.

**`private=offset=7`:** `generated.findVirtual(actualClass, "describe", MethodType.methodType(String.class))` tra method `private` trên hidden class. `describe.invoke(instance)` thành công vì handle được tạo trong **ngữ cảnh đặc quyền của returned Lookup**.

**`instanceIsGenerated=true`:** Giá trị `instance.getClass()` chính là `actualClass`. Mọi đoạn code còn giữ instance có thể dùng interface `IntUnaryOperator` đã biết mà không cần tên hidden class.

**`hostCanAccessPrivate=false`:** Ngữ cảnh `host` vốn là lớp gọi. Hidden class mặc định không được thêm vào nest của lớp gọi; vì vậy `host.findVirtual(...)` tới member `private` của hidden class bị từ chối. Đây là bằng chứng quan trọng rằng **Lookup ban đầu và returned Lookup có ngữ cảnh quyền khác nhau**. Nếu framework cần cho hidden class tham gia cùng nest, phải quyết định rõ có sử dụng `ClassOption.NESTMATE` hay không; không suy ra hai ngữ cảnh mặc định là một.

**`foundByName=false`:** `Class.forName(actualClass.getName())` không tìm được hidden class. Tên do `getName()` trả ra không phải tên nhị phân thông thường có thể dùng để liên kết trực tiếp. Vì thế cần giữ `Class<?>`, `Lookup` hoặc `MethodHandle` nhận được khi tạo.

### 4.2. Vì sao dùng `findConstructor` thay cho ép kiểu `(Code)`?

Lớp ẩn được tạo từ classfile bytes của `Code` **không đồng nhất** với `LookupReturnDemo.Code` do `javac` nạp bình thường. Ép instance của hidden class trực tiếp sang `Code` là sai về danh tính kiểu. Ví dụ sử dụng **`IntUnaryOperator`** làm hợp đồng công khai mà cả hai kiểu có thể triển khai, rồi dùng handle để tạo instance.

Một framework cũng có thể định nghĩa interface riêng, chẳng hạn `GeneratedOperation`, và trả cho phần nghiệp vụ giá trị của interface đó. Cách này giữ ranh giới rõ ràng: code sinh xử lý chi tiết runtime, còn người gọi dựa vào hợp đồng ổn định.

## 5. `lookupClass()` không khởi tạo class: vai trò của `initialize`

Định nghĩa class, lấy `Lookup` và gọi `lookupClass()` không đồng nghĩa với việc **thực thi static initializer**. Tham số `initialize` của `defineHiddenClass(bytes, initialize)` quyết định có chủ động yêu cầu khởi tạo ngay không. Khi `initialize=false`, lớp được định nghĩa và liên kết nhưng có thể chỉ khởi tạo lúc lần đầu được sử dụng theo quy tắc Java.

Lưu tệp độc lập **`LookupInitializationDemo.java`**:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class LookupInitializationDemo {
    public static class Generated {
        static {
            System.out.println("generated initialized");
        }

        public static String message() {
            return "ready";
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes;
        try (InputStream in = LookupInitializationDemo.class
                .getResourceAsStream(
                        "LookupInitializationDemo$Generated.class")) {
            if (in == null) {
                throw new IllegalStateException("No bytecode");
            }
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup generatedLookup =
                MethodHandles.lookup().defineHiddenClass(bytes, false);
        Class<?> generatedType = generatedLookup.lookupClass();

        System.out.println("lookup returned");
        System.out.println("isHidden=" + generatedType.isHidden());

        MethodHandle message = generatedLookup.findStatic(
                generatedType, "message",
                MethodType.methodType(String.class));

        System.out.println("method handle ready");
        System.out.println("message=" + (String) message.invoke());
    }
}
~~~

~~~bash
javac --release 15 LookupInitializationDemo.java
java LookupInitializationDemo
~~~

**Stdout chính xác:**

~~~text
lookup returned
isHidden=true
method handle ready
generated initialized
message=ready
~~~

Lời gọi `generatedLookup.lookupClass()` và tạo handle tới `message` chưa yêu cầu initializer chạy. Khi thực sự gọi static method qua handle, JVM khởi tạo lớp và in `generated initialized` trước khi trả `"ready"`. Nếu đổi `defineHiddenClass(bytes, false)` thành `defineHiddenClass(bytes, true)`, initializer của hidden class sẽ chạy trong bước định nghĩa, trước dòng `lookup returned`.

**Điểm thực tế:** `lookupClass()` là phép lấy đối tượng `Class<?>` cho ngữ cảnh của Lookup; nó **không phải một thao tác gọi constructor** và không tự tạo instance. Điều này quan trọng với class có static initialization tốn tài nguyên hoặc có side effect.

## 6. Returned Lookup là capability đặc quyền: `lookupModes()` và giảm quyền

Một `Lookup` không đơn thuần là “con trỏ tới class”. Nó còn ghi nhận những **quyền dùng để tìm member**. Hai lookup cùng `lookupClass()` vẫn có thể **khác `lookupModes()`**, từ đó khác khả năng lấy handle tới method, field hoặc constructor `private`.

Trong JDK hiện đại:

- `hasFullPrivilegeAccess()` cho biết lookup có đủ quyền truy cập đầy đủ theo API hay không.
- `lookupModes()` trả bit mask các chế độ truy cập đang được phép.
- `dropLookupMode(int)` tạo **Lookup mới bị giới hạn hơn**, không làm thay đổi lookup gốc.
- `MethodHandles.publicLookup()` chỉ dùng cho truy cập public được phép, không đủ để gọi `defineHiddenClass`.
- Bit `MethodHandles.Lookup.ORIGINAL` hiện diện trong API từ **Java 16**; không sử dụng hằng số này khi yêu cầu biên dịch tương thích `--release 15`. Điều này khác với sự tồn tại của **returned Lookup có quyền nguyên gốc**, vốn thuộc cơ chế định nghĩa hidden class từ Java 15.

Ví dụ sau dùng `Lookup.ORIGINAL`, nên **biên dịch với Java 17+**. Lưu **`LookupPrivilegeDemo.java`**:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class LookupPrivilegeDemo {
    public static class Generated {
        private static String secret() {
            return "private";
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes;
        try (InputStream in = LookupPrivilegeDemo.class
                .getResourceAsStream(
                        "LookupPrivilegeDemo$Generated.class")) {
            if (in == null) {
                throw new IllegalStateException("No bytes");
            }
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup host = MethodHandles.lookup();
        MethodHandles.Lookup generated =
                host.defineHiddenClass(bytes, false);
        Class<?> type = generated.lookupClass();
        MethodHandles.Lookup restricted =
                generated.dropLookupMode(MethodHandles.Lookup.PRIVATE);

        System.out.println("generatedOriginalAccess=" +
                ((generated.lookupModes()
                        & MethodHandles.Lookup.ORIGINAL) != 0));
        System.out.println("restrictedTargetsHidden=" +
                (restricted.lookupClass() == type));
        System.out.println("restrictedFullPrivilege=" +
                restricted.hasFullPrivilegeAccess());

        try {
            restricted.findStatic(
                    type, "secret",
                    MethodType.methodType(String.class));
            System.out.println("restrictedCanCallPrivate=true");
        } catch (IllegalAccessException expected) {
            System.out.println("restrictedCanCallPrivate=false");
        }

        System.out.println("originalCanCallPrivate=" +
                (String) generated.findStatic(
                        type, "secret",
                        MethodType.methodType(String.class)).invoke());

        try {
            MethodHandles.publicLookup()
                    .defineHiddenClass(bytes, false);
            System.out.println("publicLookupCanDefine=true");
        } catch (IllegalAccessException expected) {
            System.out.println("publicLookupCanDefine=false");
        }
    }
}
~~~

~~~bash
javac --release 17 LookupPrivilegeDemo.java
java LookupPrivilegeDemo
~~~

**Stdout chính xác:**

~~~text
generatedOriginalAccess=true
restrictedTargetsHidden=true
restrictedFullPrivilege=false
restrictedCanCallPrivate=false
originalCanCallPrivate=private
publicLookupCanDefine=false
~~~

### 6.1. Diễn giải kết quả về quyền

- `generatedOriginalAccess=true`: returned Lookup có bit `ORIGINAL` theo API Java 17+; đây là một phần của full privilege access.
- `restrictedTargetsHidden=true`: giảm quyền bằng `dropLookupMode(PRIVATE)` vẫn giữ **cùng lookup class**. `lookupClass()` không tự nói hết quyền.
- `restrictedFullPrivilege=false` và `restrictedCanCallPrivate=false`: không thể tiếp tục dùng lookup bị giới hạn để tra cứu method `private`.
- `originalCanCallPrivate=private`: `generated` ban đầu **không bị biến đổi**, và vẫn truy cập được method `private` của hidden class qua method handle.
- `publicLookupCanDefine=false`: public lookup không có full privilege access bắt buộc của `defineHiddenClass(...)`.

**Nguyên tắc thiết kế:** không truyền returned Lookup có đặc quyền cho plugin hoặc code không tin cậy. Nếu thành phần khác chỉ cần chạy một hành vi, ưu tiên trả **interface instance** hoặc handle phù hợp đã được kiểm tra quyền. Việc chia sẻ toàn bộ Lookup có thể trao thêm khả năng tạo handle vào các thành viên mà thành phần nhận không nên truy cập.

## 7. `lookupClass()` không giúp tra lớp ẩn bằng tên

Mỗi hidden class vẫn có `Class<?>` và có thể gọi `getName()`. Tuy nhiên, tên của hidden class bao gồm phần hậu tố riêng mà JVM tạo và **không phải binary name hợp lệ** để dùng làm đầu vào của `Class.forName(...)`. Không có quy tắc đặt tên ổn định để lưu vào cơ sở dữ liệu rồi tìm lại hidden class qua loader trong lần chạy sau.

So sánh các tác vụ:

| Việc cần làm | Cách đúng |
| --- | --- |
| Lấy kiểu Java của hidden class vừa định nghĩa | `Class<?> type = returnedLookup.lookupClass()` |
| Biết class vừa tạo có phải hidden class | `type.isHidden()` |
| Tạo instance qua constructor được phép | `returnedLookup.findConstructor(type, MethodType.methodType(void.class, ...))` rồi gọi handle |
| Tìm method `private` của hidden class | `returnedLookup.findVirtual(...)` / `findStatic(...)` với đúng tên và `MethodType` |
| Dùng object từ class không có tên công khai | Cung cấp qua interface/superclass hoặc một method handle đã biết |
| Định danh cache của đoạn mã sinh | Key logic ổn định của biểu thức/cấu hình cùng metadata phiên bản |
| Tìm lại hidden class qua `Class.forName(type.getName())` | **Không hỗ trợ** |

Nếu các bytes giống nhau được định nghĩa hai lần, đừng kỳ vọng có “cùng class” để chuyển instance qua lại như một kiểu cụ thể. Có thể xử lý instance qua interface chung, nhưng hai `Class<?>` được tạo khác nhau về identity. Điều này cần được cân nhắc trước khi framework thiết kế cache, serialization, registry và phương thức gọi xuyên module.

## 8. Cách dùng returned Lookup trong một framework sinh mã runtime

Một framework thực tế thường có chuỗi xử lý:

1. **Định nghĩa hợp đồng ổn định:** một interface hoặc method signature mà ứng dụng bên ngoài sẽ sử dụng.
2. **Sinh bytecode trong runtime:** có thể từ mẫu, biểu thức, proxy, trình dịch bytecode hoặc công cụ chuyên biệt. `defineHiddenClass` **không nhận Java source text**.
3. **Lấy Lookup phù hợp:** lookup đầy đủ quyền của class chủ trong package/module đích. Classfile phải phù hợp với package của lookup class và phiên bản JVM.
4. **Định nghĩa và giữ kết quả:**

   ~~~java
   MethodHandles.Lookup returned =
           ownerLookup.defineHiddenClass(bytes, false);
   Class<?> generatedType = returned.lookupClass();
   ~~~

   Đoạn này là minh họa: `ownerLookup` và `bytes` được thành phần runtime tin cậy chuẩn bị trước.

5. **Tra cứu member qua returned Lookup:** tạo handle của constructor/method cần thiết. Đảm bảo `MethodType` chính xác, ví dụ `void.class` trong mô tả constructor và đúng các tham số của constructor.
6. **Cung cấp hợp đồng cho client:** trả instance qua interface hoặc method handle đã được xác định. Nếu client không phải thành phần tin cậy, không để lộ returned Lookup có nhiều quyền hơn cần thiết.
7. **Quản lý cache và vòng đời:** một hidden class có thể unload khi không còn reachable nếu không chọn `STRONG`. Nhưng còn giữ `Class<?>`, method handle, Lookup, instance hoặc cache có thể kéo dài vòng đời của nó. JVM không hứa thời gian unload cố định.

### 8.1. Định nghĩa một lần và tái sử dụng như thế nào?

Ví dụ nếu biểu thức `x -> x + 7` xuất hiện nhiều lần, framework thường không cần `defineHiddenClass(...)` lại mỗi request. Có thể cache **factory/handle** theo key bất biến từ biểu thức và cấu hình. Việc giữ cache cần có chính sách kích thước, thời gian sống và dọn dẹp để không tích tụ class metadata. Không dùng tên động của hidden class làm key vì nó không phải danh tính nghiệp vụ ổn định.

### 8.2. Khi nào cần `ClassOption.NESTMATE`?

Tùy chọn `NESTMATE` có thể cho hidden class tham gia nest của lookup class ban đầu để truy cập private members phù hợp theo luật JVM. Nhưng nó **không phải điều kiện** để returned Lookup truy cập method `private` **của chính hidden class**, như ví dụ `LookupReturnDemo` đã chứng minh.

Phân biệt:

- **Returned Lookup truy cập private members của hidden class:** có thể làm được vì lookup có ngữ cảnh/quyền của hidden class mới.
- **Hidden class truy cập private của host hoặc host truy cập private của hidden class:** cần xét quan hệ nest và quyền; `NESTMATE` có thể liên quan khi thiết kế muốn hai class cùng nest.
- **Public lookup truy cập mọi private trong package:** không được phép.

Đây là ba câu hỏi quyền truy cập khác nhau. Đừng thêm `NESTMATE` như một “cờ sửa lỗi” chung cho bất kỳ `IllegalAccessException` nào.

## 9. Những lỗi thường gặp và cách chẩn đoán

**Lỗi 1 — Tưởng `defineHiddenClass` trả trực tiếp `Class<?>`.**  
Không đúng; nó trả `MethodHandles.Lookup`. Lấy `Class<?>` bằng `returnedLookup.lookupClass()`. Điều này cho phép ngay sau định nghĩa dùng quyền phù hợp để tìm member.

**Lỗi 2 — Gọi `returnedLookup.getClass()` để lấy hidden class.**  
`getClass()` trả class của **đối tượng Lookup**. Phải gọi `lookupClass()`, không bỏ chữ “lookup”.

**Lỗi 3 — Dùng `host.lookupClass()` sau định nghĩa và nghĩ đó là hidden class.**  
Host Lookup không tự thay ngữ cảnh. Biến `returned` giữ lookup của hidden class; kiểm tra bằng `isHidden()`.

**Lỗi 4 — Dùng `host.findVirtual(hiddenType, privateMethod, ...)` rồi ngạc nhiên bị từ chối.**  
Quyền phụ thuộc **Lookup đang dùng**. Trong ví dụ, host không cùng nest mặc định với hidden class và không tra được private member; returned Lookup làm được.

**Lỗi 5 — Chuyển bytecode thành hidden class rồi đòi cast instance sang kiểu có tên ban đầu.**  
Hidden class được định nghĩa mới là **kiểu khác**, dù classfile bytes giống. Dùng interface/superclass chung hoặc handle.

**Lỗi 6 — Lưu `type.getName()` rồi gọi `Class.forName(...)`.**  
Hidden class không có binary name tra bằng tên như lớp thường. Giữ đối tượng `Class<?>` hoặc handle phù hợp trong vòng đời của framework.

**Lỗi 7 — Nghĩ `lookupClass()` cũng chạy static initializer.**  
Nó chỉ lấy Class đối tượng. Với `initialize=false`, initializer có thể chạy khi gọi static method qua handle hoặc khi JVM cần khởi tạo theo luật thường.

**Lỗi 8 — Chỉ kiểm tra `lookupClass()` mà quên `lookupModes()`.**  
Hai Lookup trên cùng lớp có thể khác quyền. `dropLookupMode(PRIVATE)` giảm quyền, còn original Lookup không bị sửa.

**Lỗi 9 — Tra cứu constructor sai `MethodType`.**  
`findConstructor` nhận `MethodType` có **return type `void.class`**, cùng danh sách tham số constructor. Sai signature dẫn đến lỗi tra cứu như `NoSuchMethodException`.

**Lỗi 10 — Tưởng `publicLookup()` cũng định nghĩa hidden class được.**  
`defineHiddenClass` yêu cầu full privilege access. Public lookup không đủ quyền, như ví dụ thứ ba đã xác nhận.

**Lỗi 11 — Đọc bytecode sai package hoặc phiên bản.**  
Classfile phải hợp lệ, có phiên bản JVM hỗ trợ và cùng package với lookup class. Hãy bảo đảm generator sinh đúng classfile, tránh “sửa” bằng cách mở quyền không cần thiết.

**Lỗi 12 — Cho rằng “hidden” là cơ chế sandbox.**  
Không. Lớp ẩn vẫn chạy bytecode với khả năng của chương trình hiện hữu; không chạy bytecode từ nguồn chưa tin cậy chỉ vì nó không thể tra bằng tên.

## 10. Checklist khi review code sử dụng returned Lookup

- [ ] `MethodHandles.lookup()` hoặc một lookup hợp lệ được lấy từ class/package có quyền cần thiết.
- [ ] Bytecode đến từ nguồn tin cậy và classfile đúng phiên bản, cùng package.
- [ ] `defineHiddenClass(...)` được gán vào **biến `MethodHandles.Lookup`**, không nhầm với `Class<?>`.
- [ ] `Class<?> hiddenType = returned.lookupClass()` được giữ để tìm member.
- [ ] `hiddenType.isHidden()` được xác minh trong test của framework nếu cần.
- [ ] `findConstructor/findVirtual/findStatic` dùng **returned Lookup** khi cần quyền của hidden class.
- [ ] `MethodType` khớp chữ ký bytecode; constructor được mô tả với `void.class`.
- [ ] Không dựa vào `getName()` của hidden class để tìm lại qua `Class.forName`.
- [ ] Quyền của Lookup không bị lộ ra ngoài trust boundary; chỉ cung cấp instance/handle cần thiết.
- [ ] `initialize` được chọn có chủ đích, đặc biệt với class có static initializer.
- [ ] Nếu giảm quyền bằng `dropLookupMode`, đã kiểm tra `lookupModes()`/`hasFullPrivilegeAccess()` phù hợp.
- [ ] Cache và vòng đời handle/Class/Lookup được kiểm soát; không kỳ vọng unload ngay khi rời khỏi hàm.

## 11. Tự kiểm tra và câu trả lời

**Câu 1.** `host.defineHiddenClass(bytes, true)` trả về kiểu gì?  
**Đáp án:** `MethodHandles.Lookup`; gọi `lookupClass()` trên Lookup đó để lấy `Class<?>` của lớp ẩn vừa định nghĩa.

**Câu 2.** Sau khi tạo lớp ẩn, `host.lookupClass()` có tự chuyển thành lớp ẩn không?  
**Đáp án:** Không. Lookup ban đầu giữ ngữ cảnh class của nó; Lookup trả về là đối tượng mới có lookup class là hidden class.

**Câu 3.** `generated.getClass() == generated.lookupClass()` có phải đúng không?  
**Đáp án:** Không. Vế trái là `MethodHandles.Lookup.class`, vế phải là hidden class.

**Câu 4.** Có thể lấy handle tới constructor `private` của hidden class thông qua returned Lookup không?  
**Đáp án:** Có, với `findConstructor(hiddenType, MethodType.methodType(void.class, ...))` và quyền tương ứng. Ví dụ đã tạo instance qua constructor `private` và trả `result=42`.

**Câu 5.** `lookupClass()` có yêu cầu chạy static initializer không?  
**Đáp án:** Không. Với `initialize=false`, chương trình ví dụ đã lấy Class và MethodHandle trước, initializer chỉ chạy khi invoke static method.

**Câu 6.** Sau `dropLookupMode(PRIVATE)`, `restricted.lookupClass()` có đổi lớp đích không?  
**Đáp án:** Không. Lớp đích giữ nguyên, nhưng quyền truy cập bị giảm; không còn tìm được method `private` trong ví dụ.

**Câu 7.** `Class.forName(hiddenType.getName())` có tải lại chính hidden class không?  
**Đáp án:** Không. Hidden class không có binary name dùng cho cơ chế tra theo tên đó.

**Câu 8.** Khi nào cần `NESTMATE`?  
**Đáp án:** Khi thiết kế cần hidden class tham gia nest để cho phép quan hệ truy cập private giữa các nestmates theo JVM; nó không cần thiết chỉ để returned Lookup truy cập private của chính hidden class.

**Câu 9.** Vì sao không truyền returned Lookup cho plugin chưa tin cậy?  
**Đáp án:** Lookup là một capability chứa quyền tạo method handles tới các member mà lookup được phép truy cập; chuyển nó có thể trao quyền vượt nhu cầu của plugin.

**Câu 10.** API Java 15 có dùng được `MethodHandles.Lookup.ORIGINAL` khi biên dịch với `--release 15` không?  
**Đáp án:** Không; hằng `ORIGINAL` được thêm trong API Java 16. Ví dụ thứ ba dùng `--release 17`. `defineHiddenClass` và `lookupClass()` đã có từ trước mốc đó.

## 12. Tài liệu tham khảo chính thức

- [Java SE 26 — `MethodHandles.Lookup.defineHiddenClass`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...)): hợp đồng giá trị trả về Lookup trên hidden class, quyền và ngoại lệ.
- [Java SE 26 — `Lookup.lookupClass()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#lookupClass()): ngữ cảnh lớp của một Lookup và mối liên hệ với kiểm tra quyền.
- [Java SE 26 — `Lookup.dropLookupMode()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#dropLookupMode(int)): tạo lookup hạn chế quyền mà không sửa lookup ban đầu.
- [Java SE 26 — `MethodHandles.lookup()` và `publicLookup()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html): nguồn Lookup và khác biệt mức quyền.
- [Java SE 15 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): API gốc khi hidden class được chuẩn hóa từ Java 15.
- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): lý do thiết kế, lớp ẩn và hợp đồng với class loader/JVM.
