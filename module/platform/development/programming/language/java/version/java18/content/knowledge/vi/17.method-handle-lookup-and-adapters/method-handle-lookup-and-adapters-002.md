# publicLookup() và lookup() trong thư viện: lớp tạo Lookup quyết định phạm vi quyền

> **Chương:** Lookup và adapter  
> **Phạm vi:** `java.lang.invoke.MethodHandles`, `MethodHandles.Lookup`, `MethodHandle` và `MethodType` trên Java 18 và các JDK hiện đại. Đây là các API công khai vẫn được hỗ trợ; bài học không coi chúng là tính năng mới chỉ xuất hiện từ Java 18.

## 1. Tình huống: thư viện tìm method thay cho ứng dụng

Giả sử ứng dụng `demo.app.App` gọi thư viện `demo.lib.HandleLibrary` để tìm một `static` method bằng `MethodHandles.Lookup.findStatic(...)`. Ứng dụng có một method `private static` muốn dùng trong nội bộ. Thư viện cũng có một method private của riêng mình.

Câu hỏi quan trọng: **nếu thư viện gọi `MethodHandles.lookup()` bên trong phương thức của thư viện, `Lookup` vừa tạo mang quyền của ai?** Câu trả lời là **lớp thực sự thực hiện lời gọi `MethodHandles.lookup()`**, ở đây là `HandleLibrary`. Lời gọi từ `App` vào thư viện không làm `lookup()` tự trở thành lookup của `App`.

Ngược lại, `MethodHandles.publicLookup()` cung cấp một lookup có quyền công khai, thích hợp để tìm các thành viên công khai truy cập được rộng rãi theo quy tắc của Java và JPMS. Nó không có quyền private của `App` hoặc `HandleLibrary`.

Ba tình huống cần tách riêng:

| Cách lấy `Lookup` | Lớp/phạm vi làm cơ sở quyền | Hệ quả thực tế |
| --- | --- | --- |
| `MethodHandles.lookup()` viết trong `App` | `App` cùng các quyền được JVM cấp theo quy tắc truy cập | Có thể tìm private member của chính `App` khi chữ ký phù hợp |
| `MethodHandles.lookup()` viết trong `HandleLibrary` | `HandleLibrary`, **không phải** lớp vừa gọi thư viện | Không tự tìm được private member của top-level class `App` |
| `MethodHandles.publicLookup()` | Quyền truy cập công khai độc lập với đặc quyền private của caller | Tìm được public member của public class có package được xuất công khai phù hợp; không dùng cho private member |

**Mục tiêu bài học:** dự đoán và kiểm chứng quyền của từng lookup; phân biệt lỗi không tìm thấy thành viên với lỗi thiếu quyền; biết khi nào nên dùng public API, khi nào cần truyền một lookup tường minh và vì sao phải bảo vệ các lookup có quyền cao.

## 2. `Lookup` không chỉ là công cụ tìm kiếm tên

Một đối tượng `MethodHandles.Lookup` đại diện cho **ngữ cảnh tra cứu và khả năng truy cập** được JVM xác định. Khi gọi:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle handle = lookup.findStatic(
        SomeClass.class,
        "methodName",
        MethodType.methodType(String.class));
```

`findStatic` kiểm tra lớp đích, tên, chữ ký method và quyền của lookup. Nếu thành công, kết quả là `MethodHandle` đã liên kết đến method tương ứng. Đối với method `static` không có đối số, `MethodType.methodType(String.class)` nghĩa là `()String`.

### 2.1. `lookup()` nhạy với lớp gọi trực tiếp

Trong biểu thức `MethodHandles.lookup()`, vị trí gọi nằm ở **đúng lớp chứa biểu thức**. Không có quy tắc "thừa hưởng quyền" theo chuỗi gọi hàm:

```text
App.main()
  |
  +--> MethodHandles.lookup()
  |      Lookup.lookupClass() = App
  |
  +--> HandleLibrary.findWithLibraryLookup(...)
         |
         +--> MethodHandles.lookup()
                Lookup.lookupClass() = HandleLibrary
```

`lookup.lookupClass()` cho phép quan sát lớp dùng làm cơ sở tra cứu. Tuy nhiên **chỉ biết lookup class chưa mô tả hết quyền**: lookup còn có các access mode và các giới hạn do module, việc chuyển lookup bằng `in(...)` hoặc `privateLookupIn(...)` gây ra. Đừng chỉ so tên lớp để suy ra quyền đầy đủ.

### 2.2. `publicLookup()` chỉ có phạm vi công khai

```java
MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
```

`publicLookup()` hữu ích khi thư viện cần khám phá một điểm vào **public** mà không yêu cầu caller giao lookup có quyền cao. Trong môi trường JPMS, public class/member còn phải thuộc package **được export không giới hạn** để `publicLookup()` có thể truy cập theo hợp đồng. Một `exports pkg to some.module` chỉ cấp quyền cho module được chỉ định; không tương đương việc package được public lookup truy cập từ mọi nơi.

Điều này đặc biệt quan trọng với API plugin: public method trong một lớp mà package chưa export không tự động truy cập được chỉ vì modifier viết là `public`.

### 2.3. Lỗi tại bước tìm khác lỗi tại bước gọi

| Giai đoạn | Ví dụ | Kết quả cần dự kiến |
| --- | --- | --- |
| Tra cứu bằng tên/chữ ký | `findStatic` với sai `MethodType` hoặc không có method tương ứng | `NoSuchMethodException` |
| Kiểm tra quyền | Tìm private method của top-level class khác bằng lookup không đủ quyền | `IllegalAccessException` |
| Lời gọi handle | `invokeExact` có kiểu tại call site không khớp `handle.type()` | `WrongMethodTypeException` |
| Thân method đích | Method đã được gọi và tự ném ngoại lệ | Ngoại lệ của method đích được truyền theo hợp đồng `MethodHandle`, không tự bọc thành `InvocationTargetException` như `Method.invoke` |

Đừng xử lý cả bốn trường hợp như thể chúng đều là lỗi tìm method. Thư viện nên cung cấp thông tin lỗi đủ để phân biệt thiếu phương thức, thiếu quyền và sai chữ ký khi thực thi.

## 3. Thực hành với hai package: App và thư viện

Tạo hai tệp Java trong cấu trúc sau:

```text
lookup-demo/
  src/
    demo/
      app/
        App.java
      lib/
        HandleLibrary.java
```

Ví dụ chạy trên classpath (unnamed module) để tập trung kiểm tra **lớp tạo Lookup**. Ở phần sau sẽ xét thêm giới hạn khi chạy trên module path.

### 3.1. Mã thư viện: `src/demo/lib/HandleLibrary.java`

```java
package demo.lib;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class HandleLibrary {
    private HandleLibrary() {
    }

    private static String internalValue() {
        return "library-only";
    }

    // Lookup tạo tại lớp thư viện: lookupClass là HandleLibrary.
    public static Class<?> libraryLookupClass() {
        return MethodHandles.lookup().lookupClass();
    }

    // Tìm bằng quyền của thư viện, dù ai là người gọi phương thức này.
    public static MethodHandle findWithLibraryLookup(
            Class<?> owner, String name, MethodType type)
            throws NoSuchMethodException, IllegalAccessException {
        return MethodHandles.lookup().findStatic(owner, name, type);
    }

    // Bản thân thư viện tìm được private method của chính lớp mình.
    public static String readOwnPrivate() throws Throwable {
        MethodHandle method = MethodHandles.lookup().findStatic(
                HandleLibrary.class,
                "internalValue",
                MethodType.methodType(String.class));
        return (String) method.invokeExact();
    }

    // Chỉ dùng trong ví dụ với caller và thư viện tin cậy nhau.
    // Thư viện sử dụng đúng Lookup được caller truyền vào.
    public static MethodHandle findWithSuppliedLookup(
            MethodHandles.Lookup supplied,
            Class<?> owner, String name, MethodType type)
            throws NoSuchMethodException, IllegalAccessException {
        return supplied.findStatic(owner, name, type);
    }
}
```

Hàm `findWithLibraryLookup` dùng `MethodHandles.lookup()` ngay tại `HandleLibrary`; quyền của nó **không đổi** khi `App`, một framework khác hoặc một unit test gọi hàm. Ngược lại, `findWithSuppliedLookup` dùng chính đối tượng lookup được nhận từ tham số, vì vậy phạm vi quyền tùy thuộc vào đối tượng mà bên gọi chủ động truyền vào.

### 3.2. Mã ứng dụng: `src/demo/app/App.java`

```java
package demo.app;

import demo.lib.HandleLibrary;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public final class App {
    private static int passed;

    private static String secret() {
        return "app-only";
    }

    public static String publicMessage() {
        return "public-message";
    }

    @FunctionalInterface
    private interface Action {
        void execute() throws Throwable;
    }

    private static void pass(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError(name + ": unexpected result");
        }
        passed++;
        System.out.println("PASS " + name);
    }

    private static void expectFailure(
            String name, Class<? extends Throwable> type, Action action)
            throws Throwable {
        try {
            action.execute();
        } catch (Throwable actual) {
            if (!type.isInstance(actual)) {
                throw new AssertionError(name
                        + ": expected " + type.getName()
                        + ", got " + actual.getClass().getName(), actual);
            }
            pass(name, true);
            return;
        }
        throw new AssertionError(name + ": expected " + type.getName());
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup appLookup = MethodHandles.lookup();
        MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
        MethodType noArgsString = MethodType.methodType(String.class);

        pass("L01 app lookup class",
                appLookup.lookupClass() == App.class);
        pass("L02 library lookup class",
                HandleLibrary.libraryLookupClass() == HandleLibrary.class);

        MethodHandle publicHandle = publicOnly.findStatic(
                App.class, "publicMessage", noArgsString);
        pass("L03 public lookup calls public method",
                "public-message".equals((String) publicHandle.invokeExact()));

        MethodHandle selfPrivate = appLookup.findStatic(
                App.class, "secret", noArgsString);
        pass("L04 app lookup calls own private",
                "app-only".equals((String) selfPrivate.invokeExact()));

        expectFailure("L05 public lookup denies private",
                IllegalAccessException.class, () ->
                publicOnly.findStatic(App.class, "secret", noArgsString));

        expectFailure("L06 library lookup denies app private",
                IllegalAccessException.class, () ->
                HandleLibrary.findWithLibraryLookup(
                        App.class, "secret", noArgsString));

        expectFailure("L07 app lookup denies library private",
                IllegalAccessException.class, () ->
                appLookup.findStatic(
                        HandleLibrary.class, "internalValue", noArgsString));

        pass("L08 library lookup calls own private",
                "library-only".equals(HandleLibrary.readOwnPrivate()));

        // Truyền một năng lực quyền truy cập vào thư viện có chủ đích.
        MethodHandle supplied = HandleLibrary.findWithSuppliedLookup(
                appLookup, App.class, "secret", noArgsString);
        pass("L09 supplied lookup retains caller rights",
                "app-only".equals((String) supplied.invokeExact()));

        // in(...) thay đổi lookup class, không cấp thêm private access.
        MethodHandles.Lookup moved = appLookup.in(HandleLibrary.class);
        expectFailure("L10 in does not preserve app private",
                IllegalAccessException.class, () ->
                moved.findStatic(App.class, "secret", noArgsString));

        expectFailure("L11 wrong return type at lookup",
                NoSuchMethodException.class, () ->
                publicOnly.findStatic(App.class, "publicMessage",
                        MethodType.methodType(int.class)));

        expectFailure("L12 wrong invokeExact call-site type",
                WrongMethodTypeException.class, () -> {
                    int unused = (int) publicHandle.invokeExact();
                });

        System.out.printf("TOTAL=%d PASS=%d FAIL=0%n",
                passed, passed);
        System.out.println("java=" + Runtime.version());
    }
}
```

Trong ca L10, `in(HandleLibrary.class)` làm thay đổi lớp tra cứu sang một top-level class ở package khác; quyền private của `App` bị thu hẹp. Phương thức `Lookup.in(...)` không cấp thêm quyền khi di chuyển sang lớp khác.

### 3.3. Biên dịch và chạy

Với JDK 18 trở lên, đứng tại thư mục `lookup-demo` và thực hiện:

```bash
javac -d out src/demo/lib/HandleLibrary.java src/demo/app/App.java
java -cp out demo.app.App
```

Đường dẫn dùng dấu `/` được `javac` và `java` nhận trên các hệ điều hành thông dụng. Cần khởi động JVM mới nếu bạn thay đổi file `.class`, cách đóng gói hoặc cài đặt quyền module cho các ca kiểm chứng.

Ví dụ kết quả **dự kiến**, không phải log được chạy khi biên soạn:

```text
PASS L01 app lookup class
PASS L02 library lookup class
PASS L03 public lookup calls public method
PASS L04 app lookup calls own private
PASS L05 public lookup denies private
PASS L06 library lookup denies app private
PASS L07 app lookup denies library private
PASS L08 library lookup calls own private
PASS L09 supplied lookup retains caller rights
PASS L10 in does not preserve app private
PASS L11 wrong return type at lookup
PASS L12 wrong invokeExact call-site type
TOTAL=12 PASS=12 FAIL=0
java=<JDK_VERSION>
```

Mỗi dòng `PASS` tương ứng một hành vi cụ thể, kể cả ca **mong đợi ngoại lệ**. Nếu sai khác, chương trình dừng bằng `AssertionError` và không in dòng tổng kết. Bài không gán sẵn thời gian chạy hoặc giá trị PID, vì những thông tin đó chỉ có ý nghĩa khi thu từ một JVM thực.

## 4. Phân tích kết quả: ai tạo lookup và ai cung cấp quyền?

### 4.1. L01–L04: định danh lookup và public/private

`App.main` gọi `MethodHandles.lookup()` nên lookup class là `App`. Bên trong `HandleLibrary.libraryLookupClass()`, `lookup()` được gọi tại lớp `HandleLibrary`, dù ngăn xếp lúc chạy có `App.main` phía trên.

`publicLookup()` tìm được `App.publicMessage` vì `App` là public class trong một package truy cập được trong bản chạy classpath của ví dụ. `appLookup` tìm được `App.secret` do được tạo trong cùng lớp và còn quyền private. Đây là hai con đường hợp lệ nhưng có phạm vi quyền rất khác nhau.

### 4.2. L05–L08: private không chuyển theo call stack

`publicLookup()` không được truy cập `App.secret`. Tương tự, `HandleLibrary.findWithLibraryLookup(App.class, ...)` không thể dùng quyền private của `App`, dù chính `App` là caller của thư viện. `App` cũng không thể dùng lookup của mình để truy cập `HandleLibrary.internalValue` khi hai lớp là top-level class khác nhau.

Trong L08, thư viện tự gọi `MethodHandles.lookup()` để tạo handle tới private method của **chính mình**; đây là quyền phù hợp. Như vậy sự khác biệt xuất phát từ **nơi tạo lookup**, không phải tên method hoặc thứ tự gọi chương trình.

### 4.3. L09: truyền lookup là hành động trao năng lực

Thư viện nhận `appLookup` dưới dạng đối số và dùng `supplied.findStatic(...)`. Khi caller chủ động chuyển lookup có quyền private của mình, thư viện được phép thực hiện những thao tác mà lookup đó cho phép. Đó là một **chuyển giao năng lực có chủ đích**, không phải cơ chế thư viện tự giành thêm quyền.

Trong ứng dụng thực, **chỉ giao lookup có quyền cao cho thành phần đáng tin cậy**. Nếu thư viện chỉ cần gọi một số method cụ thể, API nhận một `MethodHandle` đã chọn hoặc một callback có thể giảm phạm vi quyền so với truyền nguyên đối tượng lookup. Đừng trả một lookup quyền cao từ public API cho mã plugin không tin cậy.

### 4.4. L10–L12: thu hẹp quyền và hai kiểu sai chữ ký

`lookup.in(otherClass)` tạo một lookup mới cho lớp đích và có thể **mất quyền** so với lookup gốc. Nó không trở thành lookup có toàn bộ quyền của `otherClass`. Trong trường hợp L10, lookup sau khi chuyển lớp không còn quyền riêng tư của `App`, nên không thể tìm `App.secret`.

Đối với L11, `publicMessage()` trả `String`, nhưng yêu cầu một method trả `int` làm `findStatic` thất bại bằng `NoSuchMethodException`. Đó là lỗi **tra cứu chữ ký**.

Đối với L12, `publicHandle` có kiểu `()String`, nhưng vị trí gọi `invokeExact` yêu cầu kết quả `int` nên ném `WrongMethodTypeException`. Đó là lỗi **kiểu tại điểm gọi**. `invokeExact` không tự đổi kiểu kết quả vì chữ ký đặt tại call site phải khớp chính xác.

## 5. Ranh giới JPMS: public và public-to-all không giống nhau

Ví dụ trên chạy trên classpath, nơi hai lớp thuộc unnamed module. Khi đóng gói thành **named modules**, bạn cần kiểm tra cả `requires`, `exports`, `opens` và quan hệ giữa module chứa lớp tra cứu với module chứa lớp đích.

Ví dụ một API public được export không giới hạn:

```java
module sample.api {
    exports sample.api;
}
```

Nếu `sample.api` chứa public class và public static method, `publicLookup()` có thể tìm method này khi các điều kiện truy cập khác và chữ ký đều hợp lệ.

Ngược lại:

```java
module sample.api {
    exports sample.api to sample.client;
}
```

Với **qualified export**, quyền public chỉ được cấp cho module được nêu. Một `Lookup` được tạo trong `sample.client` có thể khai thác quyền module thích hợp, nhưng `publicLookup()` không biến qualified export thành xuất công khai cho mọi module. Việc một method được khai báo `public` không đủ để vượt qua quy tắc JPMS.

Đối với private member trong module khác, `privateLookupIn(targetClass, callerLookup)` có thể dùng trong những điều kiện đặc tả cho phép, thường liên quan đến việc package đích được `opens` cho module gọi và lookup nguồn có quyền thích hợp. **`privateLookupIn` không phải cách vượt qua encapsulation**: nếu thiếu quyền hoặc module không mở package cần thiết, thao tác có thể thất bại bằng `IllegalAccessException`.

Bảng quyết định thực tế:

| Nhu cầu thư viện | Cách tiếp cận phù hợp | Điều kiện phải kiểm chứng |
| --- | --- | --- |
| Gọi public static trong API mở công khai | `MethodHandles.publicLookup().findStatic(...)` | Public class/member, package export phù hợp, chữ ký chính xác |
| Gọi private static của chính lớp thư viện | `MethodHandles.lookup()` tại lớp thư viện | Member thuộc phạm vi mà lookup có quyền |
| Gọi private static của ứng dụng | Để ứng dụng gọi trực tiếp hoặc chủ động cung cấp handle/callback; khi cần mới truyền lookup | Không trao quyền rộng cho thư viện không đáng tin cậy |
| Mở quyền trong các named module do mình quản lý | Thiết kế `opens`/`exports` rõ ràng, cân nhắc `privateLookupIn` khi phù hợp | Kiểm tra quyền lookup, module reads và package opens theo Javadoc |
| Chỉ muốn giảm quyền của một lookup | Chọn `publicLookup()` hoặc các API thu hẹp quyền phù hợp (`in`, `dropLookupMode`) | Không suy luận lookup sau biến đổi giữ nguyên mọi access mode |

## 6. Vì sao chỉ chuyển sang `MethodHandle` không giải quyết vấn đề quyền truy cập?

Một số lập trình viên chuyển từ `Method.invoke` sang `MethodHandle` với kỳ vọng giới hạn private/module sẽ biến mất. Thực tế cả hai là API công khai tôn trọng quy tắc quyền truy cập, dù cơ chế kiểm tra và mô hình xử lý lời gọi khác nhau:

- `Class.getDeclaredMethod(...)` có thể **tìm thấy** một private method, nhưng `Method.invoke(...)` có thể không được phép gọi nếu chưa có quyền truy cập phù hợp.
- `Lookup.findStatic(...)` kiểm tra quyền khi tìm method để tạo `MethodHandle`; lookup của lớp không đủ quyền có thể ném `IllegalAccessException`.
- Có được một handle được phép gọi là có một **năng lực truy cập** đã được liên kết. Vì vậy, việc truyền handle giữa các thành phần cũng cần cân nhắc phạm vi tin cậy.
- `MethodHandle.invokeExact` tuân thủ chữ ký tại call site; đổi sang `invoke` chỉ làm thay đổi quy tắc thích nghi kiểu được phép, **không làm cho một lookup thiếu quyền tự nhiên tìm được method private**.

Java 18 có JEP 416 tái triển khai core reflection dựa trên method handles, nhưng đây là thay đổi **triển khai nội bộ**. Nó không làm `MethodHandles.lookup()` mất tính phụ thuộc vào lớp tạo lookup và không khiến `publicLookup()` được quyền gọi thành viên private.

## 7. Lỗi thường gặp khi viết thư viện dùng method handles

| Hiện tượng | Khả năng gây lỗi | Cách kiểm tra/sửa |
| --- | --- | --- |
| Thư viện không tìm được private method của caller | `lookup()` được tạo trong lớp thư viện | Kiểm tra `lookupClass()`; quyết định lại API công khai hoặc truyền handle được cấp rõ ràng |
| `publicLookup()` thất bại với method `public` | Lớp không public, package không export công khai, hoặc sai chữ ký | Kiểm tra cả owner, module/package và `MethodType` |
| `findStatic` ném `NoSuchMethodException` | Sai tên, kiểu tham số, kiểu trả về hoặc method đích không khớp mô tả | So sánh chính xác `MethodType` và `static` của member |
| `findStatic` ném `IllegalAccessException` | Thành viên tồn tại nhưng lookup thiếu quyền hoặc vi phạm ranh giới module | Xem lớp tạo Lookup và khai báo module; không thêm quyền tùy tiện |
| `invokeExact` ném `WrongMethodTypeException` | Kiểu đối số hoặc kiểu kết quả tại vị trí gọi không khớp `handle.type()` | Kiểm tra `handle.type()` và phép ép kiểu ở call site |
| `lookup.in(Target.class)` không mở được private của Target | `in` có thể giảm quyền; không cấp quyền private của Target | Thiết kế API phù hợp hoặc dùng `privateLookupIn` khi điều kiện cho phép |
| Unit test tình cờ truy cập được private | Fixture đặt trong nested class cùng nest hoặc test có quyền khác runtime thực | Dùng top-level class khác và chạy kiểm thử theo cùng cấu hình module với sản phẩm |

Một lỗi phổ biến nữa là xây dựng API thư viện nhận trực tiếp class name và method name rồi sử dụng lookup có quyền rộng cho mọi yêu cầu. Thiết kế này làm tăng số member có thể bị gọi ngoài ý muốn. Thư viện nên giới hạn tập API được phép, xác thực đầu vào và cung cấp capability nhỏ nhất phù hợp với mục tiêu.

## 8. Bảng kiểm chứng áp dụng khi nâng cấp JDK

Để so sánh hành vi Java 18 với một JDK mới hơn, chạy ví dụ trên từng phiên bản JVM, giữ nguyên mã nguồn và cấu hình classpath. Khi chuyển sang module path, ghi riêng ma trận quyền module thay vì so sánh hai môi trường có điều kiện truy cập khác nhau.

| ID | Trường hợp | Kết quả cần có |
| --- | --- | --- |
| L01 | `lookup()` tạo trong `App` | `lookupClass() == App.class` |
| L02 | `lookup()` tạo trong `HandleLibrary` | `lookupClass() == HandleLibrary.class` |
| L03 | `publicLookup()` tìm public static trong public class truy cập được | Tìm và gọi được method |
| L04 | `App` tìm private static của chính mình | Thành công |
| L05 | `publicLookup()` tìm private static của `App` | `IllegalAccessException` |
| L06 | Lookup tạo trong thư viện tìm private static của `App` | `IllegalAccessException` |
| L07 | Lookup tạo trong `App` tìm private static của thư viện | `IllegalAccessException` |
| L08 | Lookup tạo trong thư viện tìm private static của chính thư viện | Thành công |
| L09 | Ứng dụng chủ động truyền lookup của mình vào thư viện tin cậy | Thư viện dùng đúng quyền được trao |
| L10 | `appLookup.in(HandleLibrary.class)` tìm private static của `App` | `IllegalAccessException` |
| L11 | `findStatic` yêu cầu kiểu trả về sai | `NoSuchMethodException` |
| L12 | `invokeExact` yêu cầu kiểu kết quả sai | `WrongMethodTypeException` |

**Ghi báo cáo:** lưu `java -version`, lệnh biên dịch, lệnh chạy, đầu ra và mã thoát. Không dựa vào thứ tự stack trace hay chuỗi thông báo ngoại lệ làm tiêu chí vì nội dung nội bộ có thể khác theo bản JDK.

## 9. Câu hỏi tự kiểm tra

1. Khi `App` gọi `HandleLibrary.findWithLibraryLookup(...)`, vì sao `MethodHandles.lookup()` trong thư viện không nhận quyền private của `App`?
2. `publicLookup()` có thể truy cập method `public` của một named module chỉ `exports ... to sample.client` hay không? Vì sao?
3. Điều gì khác nhau giữa việc **truyền `Lookup`** và **truyền một `MethodHandle` cụ thể** cho thư viện?
4. Khi nào `findStatic` báo `NoSuchMethodException`, khi nào báo `IllegalAccessException`, và khi nào `invokeExact` báo `WrongMethodTypeException`?
5. Vì sao `lookup.in(otherClass)` không phải là cách đạt quyền private của `otherClass`?
6. Nếu chuyển từ classpath sang module path mà một ca public lookup thất bại, cần kiểm tra `exports`/`opens` và quan hệ module thế nào?

**Ghi nhớ:** Quyền của `MethodHandles.lookup()` gắn với **lớp nơi lời gọi đó được thực hiện**. Thư viện không tự nhận quyền của caller bằng cách đặt `lookup()` trong mã thư viện. `publicLookup()` dành cho phạm vi công khai; cần quyền sâu hơn thì caller/module sở hữu phải cung cấp capability hoặc chính sách truy cập phù hợp. Đối chiếu Javadoc của `MethodHandles.lookup`, `publicLookup`, `Lookup.lookupClass`, `Lookup.findStatic`, `Lookup.in` và `privateLookupIn` trên phiên bản JDK thực tế sử dụng.
