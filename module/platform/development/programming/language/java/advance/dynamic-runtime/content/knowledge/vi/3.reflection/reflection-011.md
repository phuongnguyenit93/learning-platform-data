# 3.11. Phân biệt lỗi tìm kiếm, lỗi đối số, lỗi truy cập và `InvocationTargetException`

Reflection cho phép Java tìm lớp, phương thức, constructor và field bằng thông tin chỉ biết khi chạy. Một lời gọi reflection thường trải qua nhiều bước khác nhau: **tìm thành viên → kiểm tra khả năng truy cập → kiểm tra đối tượng/đối số → thực thi mã đích**. Mỗi bước thất bại theo cách khác nhau, nên cùng một triệu chứng “reflection không chạy” có thể đòi hỏi cách sửa hoàn toàn khác.

Bài này phân biệt bốn nhóm lỗi chính trong `java.lang.reflect`, chỉ ra cách đọc nguyên nhân gốc và xây dựng ví dụ Java 17+ có thể biên dịch/chạy độc lập.

## 1. Bản đồ nhanh: lỗi xuất phát ở đâu?

| Nhóm | Thời điểm | Ngoại lệ điển hình | Ý nghĩa và hướng kiểm tra |
| --- | --- | --- | --- |
| **Tìm kiếm (lookup)** | Chưa có đúng lớp/thành viên | `ClassNotFoundException`; `NoSuchMethodException`; `NoSuchFieldException` | Tên, chữ ký, phạm vi tìm kiếm, class loader |
| **Đối số/receiver** | Đã có `Method`/`Constructor`/`Field`, nhưng dữ liệu truyền không phù hợp | `IllegalArgumentException`; `NullPointerException` | Số lượng, kiểu đối số, đối tượng nhận, primitive/wrapper, cách truyền varargs |
| **Truy cập (access)** | Đã tìm thấy thành viên, nhưng caller không được phép dùng | `IllegalAccessException`; `InaccessibleObjectException`; đôi khi `SecurityException` | `public`/`private`, lớp khai báo, module `exports`/`opens`, `setAccessible` |
| **Mã đích ném lỗi** | Lời gọi đã đi vào phương thức/constructor | `InvocationTargetException` | Lấy `getCause()` để xem ngoại lệ thật từ mã đích |

**Phân biệt checked/unchecked:**

- `ClassNotFoundException`, `NoSuchMethodException`, `NoSuchFieldException`, `IllegalAccessException` và `InvocationTargetException` là **checked exception**. Khi gọi API trực tiếp, mã phải bắt hoặc khai báo `throws`.
- `IllegalArgumentException`, `NullPointerException`, `InaccessibleObjectException`, `SecurityException` là **unchecked exception**.
- `InstantiationException` là checked exception khác của `Constructor.newInstance` khi không thể khởi tạo kiểu (ví dụ lớp abstract); nó không đồng nghĩa với bốn nhóm trên.
- `ExceptionInInitializerError` là một `Error` do khởi tạo lớp thất bại, có thể phát sinh riêng từ `Class.forName` hoặc lúc khởi tạo lớp; không mặc nhiên được gói trong `InvocationTargetException`.

Bảng mô tả **vị trí lỗi thường xảy ra**, không cam kết thứ tự mọi phép kiểm tra nội bộ của JVM. Nếu một lời gọi vừa sai receiver vừa không có quyền truy cập, hãy sửa từng điều kiện và quan sát lỗi thực tế.

## 2. Nhóm tìm kiếm: chưa tìm được đúng lớp hoặc thành viên

Đây là lỗi xảy ra khi reflection **chưa thu được metadata đúng thứ cần gọi**. Các API và ngoại lệ tương ứng:

| Thao tác | API điển hình | Ngoại lệ |
| --- | --- | --- |
| Nạp tên nhị phân của lớp | `Class.forName("pkg.Type")` | `ClassNotFoundException` |
| Tìm phương thức theo tên và kiểu tham số | `getMethod`, `getDeclaredMethod` | `NoSuchMethodException` |
| Tìm constructor theo kiểu tham số | `getConstructor`, `getDeclaredConstructor` | `NoSuchMethodException` |
| Tìm field theo tên | `getField`, `getDeclaredField` | `NoSuchFieldException` |

**Không có ngoại lệ chuẩn tên `NoSuchConstructorException`.** Constructor không khớp chữ ký vẫn báo `NoSuchMethodException`.

### 2.1. `getMethod` và `getDeclaredMethod` khác nhau

- `type.getMethod("run", String.class)` tìm phương thức **public**, bao gồm phương thức public phù hợp được kế thừa (và từ interface, theo quy tắc API).
- `type.getDeclaredMethod("run", String.class)` chỉ tìm phương thức **khai báo trực tiếp trên `type`**, nhưng tìm được cả `private`/`protected`/package-private. Nó **không** tự tìm trong lớp cha.
- Tìm được một phương thức private **không đồng nghĩa với quyền gọi**. Việc gọi vẫn có thể bị `IllegalAccessException`.
- Chữ ký tra cứu dùng tên và các kiểu tham số **chính xác**: `int.class` khác `Integer.class`; `String[].class` khác `String.class`. API không tự giải quyết overload như một lời gọi Java bình thường; kiểu trả về không được truyền làm tiêu chí tra cứu.

Ví dụ minh họa (đặt trong ngữ cảnh có các class tương ứng; chưa phải chương trình độc lập):

```java
Class<?> type = SomeService.class;
Method m = type.getDeclaredMethod("process", int.class);

// Nếu process khai báo tham số Integer thay vì int,
// getDeclaredMethod ở trên sẽ ném NoSuchMethodException.
```

Các lỗi tìm kiếm thường xuất phát từ: sai tên (kể cả chữ hoa/thường), sai overload, nhầm `getMethod` với `getDeclaredMethod`, tìm constructor có chữ ký khác, kiểu bị nạp bởi class loader khác, hoặc nạp lớp bằng tên không đúng. Với inner/nested class, tên nhị phân có dấu `$` giữa phần tên lớp bao ngoài và lớp bên trong; cách an toàn để lấy tên là `SomeNestedClass.class.getName()`.

`Class.forName(String)` mặc định có thể kích hoạt khởi tạo lớp. Nếu tên lớp **có tồn tại nhưng static initializer thất bại**, lỗi có thể là `ExceptionInInitializerError`; đó **không phải** `ClassNotFoundException`. Khi cần trì hoãn khởi tạo, cân nhắc `Class.forName(name, false, loader)`.

### 2.2. Cách xử lý lỗi tìm kiếm

Ghi lại tên lớp, tên thành viên, danh sách `Class<?>` tham số và class loader đang dùng. Nếu thấy `NoSuchMethodException`, hãy so sánh chữ ký mong đợi với chữ ký khai báo thực tế, đồng thời kiểm tra phạm vi `public` hay `declared`. Việc gọi `setAccessible(true)` **không giải quyết được** tình huống phương thức chưa được tìm thấy.

Không tự động thay `getDeclaredMethod` bằng `getMethod` (hoặc ngược lại) chỉ để “hết lỗi”; lựa chọn API phải phản ánh hợp đồng mong muốn. Với API thư viện, việc thay đổi chữ ký/phiên bản có thể là nguyên nhân thật.

## 3. Nhóm đối số: đã có thành viên nhưng dữ liệu truyền sai

Khi đã có đối tượng `Method` hoặc `Constructor` hợp lệ, việc gọi `invoke`/`newInstance` còn cần receiver và đối số đúng. Các lỗi thường gặp:

1. **Sai số đối số:** method yêu cầu hai tham số nhưng `invoke` nhận một hoặc ba.
2. **Sai kiểu đối số:** truyền `Integer` vào tham số `String`; hoặc truyền kiểu không thể chuyển đổi theo quy tắc invocation.
3. **Sai receiver:** dùng đối tượng không phải instance của lớp khai báo phương thức instance.
4. **Receiver `null` cho phương thức instance:** `Method.invoke(null, ...)` ném `NullPointerException`. Với **phương thức static**, receiver không được dùng và có thể là `null`.
5. **Nhầm cách trải `Object...` của `Method.invoke`** với tham số mảng của chính phương thức đích.

Ví dụ minh họa:

```java
Method echo = Example.class.getMethod("echo", String.class);
Example service = new Example();

echo.invoke(service, "Java"); // OK
echo.invoke(service, 42);     // IllegalArgumentException: sai kiểu
echo.invoke(service);         // IllegalArgumentException: thiếu đối số
echo.invoke(null, "Java");    // NullPointerException: thiếu receiver instance
```

Ở đây `Example` được giả định có phương thức public `String echo(String text)`; đoạn này là mã minh họa.

**Lưu ý chuyển đổi:** Reflection hỗ trợ một số chuyển đổi invocation phù hợp như *unboxing* và *widening primitive* (ví dụ một đối số `Integer` cho tham số `long`), nhưng không ép thu hẹp primitive như `long` xuống `int`, không tự chuyển `"42"` thành số và không biến `Integer` thành `String`. Vì vậy không được kết luận rằng mọi khác biệt primitive/wrapper đều gây lỗi, cũng không được cho rằng reflection sẽ chuyển đổi bất kỳ kiểu nào.

### 3.1. Bẫy đặc biệt: mảng và varargs của `Method.invoke`

`Method.invoke` khai báo tham số cuối là `Object... args`. Nếu **bản thân phương thức đích** nhận một `String[]`, phải bảo đảm mảng đó trở thành **một đối số**, không bị Java trải thành nhiều đối số reflection:

```java
Method accept = Example.class.getMethod("accept", String[].class);

// Đúng: ép mảng thành một Object để invoke nhận đúng một tham số.
accept.invoke(service, (Object) new String[] {"A", "B"});

// Cần tránh truyền String[] trực tiếp ở vị trí varargs của invoke:
// accept.invoke(service, new String[] {"A", "B"});
// Java có thể coi các phần tử mảng là nhiều đối số của invoke.
```

Ví dụ giả định `Example` có `public void accept(String[] values)`. `Method.invoke` không tự “trải varargs” theo lời gọi trực tiếp đến method đích; số đối số Java phản chiếu truyền tới vẫn phải khớp chữ ký method đích.

### 3.2. Field và constructor cũng có lỗi đối số

- `Field.get(receiver)`, `Field.set(receiver, value)` có thể báo `IllegalArgumentException` nếu receiver/value không phù hợp; với field instance và receiver `null`, có thể báo `NullPointerException`. Field static không dùng receiver.
- `Constructor.newInstance(args)` báo `IllegalArgumentException` cho danh sách đối số không khớp; constructor không tồn tại thì `getDeclaredConstructor(...)` báo `NoSuchMethodException` **trước đó**.
- `Constructor.newInstance` còn có thể báo `InstantiationException` nếu kiểu không thể tạo instance như lớp abstract. Lỗi này không phải lỗi đối số và cũng không có nghĩa constructor đã chạy rồi ném exception.

**Điểm quan trọng:** Một `IllegalArgumentException` ném **trực tiếp từ `Method.invoke`** thường báo sai cách gọi reflection; một `IllegalArgumentException` ném **bên trong phương thức đích** lại xuất hiện ở caller reflection dưới dạng **`InvocationTargetException` có cause là `IllegalArgumentException`**. Chỉ nhìn tên lớp ngoại lệ gốc mà bỏ qua wrapper sẽ dễ chẩn đoán nhầm.

## 4. Nhóm truy cập: tồn tại nhưng không được phép gọi

Java kiểm tra quyền truy cập khi sử dụng reflection. Tình trạng của **lớp khai báo**, thành viên, package/module và caller đều có thể liên quan.

### 4.1. `IllegalAccessException` khi thao tác bị từ chối

Các phương thức như `Method.invoke`, `Constructor.newInstance`, `Field.get` và `Field.set` có thể ném **checked `IllegalAccessException`** nếu caller không có quyền truy cập theo ngôn ngữ/module. Việc lấy metadata bằng `getDeclaredMethod` không tự bỏ qua quyền đó.

`AccessibleObject.canAccess(receiver)` (Java 9+) có thể kiểm tra quyền sử dụng hiện tại; gọi nó phải truyền receiver hợp lệ cho thành viên instance, và `null` cho thành viên static. Nếu receiver sai, chính `canAccess` có thể ném `IllegalArgumentException`.

Ví dụ minh họa:

```java
Method hidden = Example.class.getDeclaredMethod("hidden");
boolean allowed = hidden.canAccess(service); // có thể là false

// Nếu hidden là private và caller ở ngoài phạm vi được truy cập:
hidden.invoke(service); // IllegalAccessException
```

### 4.2. `setAccessible`, `trySetAccessible` và JPMS

`setAccessible(true)` yêu cầu bỏ qua một số kiểm tra truy cập của Java, **nhưng không có quyền bất biến để mở mọi thứ**.

- `member.trySetAccessible()` trả `true` nếu bật được chế độ truy cập; nếu bị giới hạn bởi module và không mở được, thường trả `false`.
- `member.setAccessible(true)` có thể ném **unchecked `java.lang.reflect.InaccessibleObjectException`** khi JVM không cho phép mở thành viên đó.
- `IllegalAccessException` thường xuất hiện ở thời điểm **dùng** thành viên không được phép. `InaccessibleObjectException` thường xuất hiện ở thời điểm **cố mở** quyền truy cập bằng `setAccessible(true)`.
- Dưới Java Platform Module System (JPMS), `exports` cho phép module khác sử dụng API public của package theo điều kiện khai báo; `opens` cho phép *deep reflection* tới thành viên không public theo điều kiện khai báo. Một package chỉ `exports` không mặc nhiên cho phép `setAccessible(true)` vào mọi thành viên private.
- `SecurityException` vẫn là loại lỗi bảo mật có thể phát sinh từ một số API trong môi trường có chính sách kiểm tra quyền phù hợp; không nên đồng nhất nó với `IllegalAccessException`.

Với mã của chính mình, ưu tiên API public hoặc thiết kế module `opens package.name to consumer.module;` khi thực sự cần framework phản chiếu vào nội bộ. Tùy môi trường, tùy chọn chạy `--add-opens module/package=target` có thể hỗ trợ thí nghiệm/chạy ứng dụng khi không sửa được module descriptor; không coi đây là cách sửa mặc định cho thiết kế production.

`setAccessible(true)` cũng không biến thành viên không tồn tại thành tồn tại, không sửa sai đối số và không cam kết có thể thay đổi mọi field `final`.

## 5. `InvocationTargetException`: mã đích đã chạy và ném lỗi

Chữ ký đại diện của API reflection:

```java
Object result = someMethod.invoke(receiver, arguments);
Object created = someConstructor.newInstance(arguments);
```

Nếu **chính phương thức hoặc constructor được gọi** ném một `Throwable`, API reflection sẽ bọc lỗi đó trong **checked `InvocationTargetException`**. Mục đích là phân biệt ngoại lệ nghiệp vụ của mã đích với lỗi thiết lập lời gọi reflection.

```java
try {
    someMethod.invoke(receiver, arguments);
} catch (InvocationTargetException wrapper) {
    Throwable actual = wrapper.getCause(); // lỗi thực sự từ mã đích
    System.err.println("Target threw: " + actual);
    // Ở đây quyết định cách báo/lan truyền actual theo hợp đồng ứng dụng.
}
```

- `getCause()` trả lại ngoại lệ gốc. `getTargetException()` là API cũ với ý nghĩa tương đương; trong mã mới thường chọn `getCause()`.
- Ngoại lệ gốc có thể là `IOException`, `IllegalArgumentException`, `NullPointerException`, `RuntimeException` tùy ý, thậm chí `Error`. Đừng chỉ ghi log “`InvocationTargetException`” mà mất stack trace/cause.
- **Cùng một loại `IllegalArgumentException` nhưng khác giai đoạn:** nếu tham số đưa tới `invoke` sai, API ném `IllegalArgumentException` trực tiếp; nếu phương thức chạy và tự ném `IllegalArgumentException`, caller nhận `InvocationTargetException` với cause là `IllegalArgumentException`.
- Khi constructor tự ném lỗi, `Constructor.newInstance` cũng bọc nó trong `InvocationTargetException`.
- `Field.get`/`Field.set` không thực thi một method/constructor đích, nên bản thân hai thao tác này không dùng `InvocationTargetException` để bọc một lời gọi nghiệp vụ.
- `ExceptionInInitializerError` khi khởi tạo lớp và một số lỗi JVM khác có thể phát sinh bên ngoài wrapper; không ép mọi lỗi reflection vào nhóm `InvocationTargetException`.

Tránh việc chỉ `catch (Exception e)` rồi trả `null` hoặc in mỗi `e.getMessage()`: cách đó làm mất thông tin giai đoạn và nguyên nhân gốc.

## 6. Ví dụ Java 17+ hoàn chỉnh

Lưu **toàn bộ** đoạn sau thành file `ReflectionFailureGuide.java`. Hai top-level class cùng một file là hợp lệ vì chỉ có `ReflectionFailureGuide` được khai báo `public`; `SampleService` cố tình tách riêng để phép gọi phương thức private từ `ReflectionFailureGuide` bị kiểm tra quyền truy cập (không phải Java nestmate).

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionFailureGuide {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<SampleService> type = SampleService.class;
        SampleService service = new SampleService();

        // 1. Không tìm thấy phương thức, field, constructor.
        try {
            type.getDeclaredMethod("missing");
        } catch (NoSuchMethodException e) {
            System.out.println("lookup.method: " + e.getClass().getSimpleName());
        }

        try {
            type.getDeclaredField("missing");
        } catch (NoSuchFieldException e) {
            System.out.println("lookup.field: " + e.getClass().getSimpleName());
        }

        try {
            type.getDeclaredConstructor(String.class);
        } catch (NoSuchMethodException e) {
            System.out.println("lookup.constructor: " + e.getClass().getSimpleName());
        }

        // 2. Đã tìm được Method, nhưng đối số hoặc receiver sai.
        Method echo = type.getMethod("echo", String.class);
        try {
            echo.invoke(service, 42);
        } catch (IllegalArgumentException e) {
            System.out.println("argument: " + e.getClass().getSimpleName());
        }

        try {
            echo.invoke(null, "Java");
        } catch (NullPointerException e) {
            System.out.println("receiver: " + e.getClass().getSimpleName());
        }

        // 3. Tìm được phương thức private nhưng không được phép gọi.
        Method hidden = type.getDeclaredMethod("hidden");
        System.out.println("access.canAccess: " + hidden.canAccess(service));
        try {
            hidden.invoke(service);
        } catch (IllegalAccessException e) {
            System.out.println("access: " + e.getClass().getSimpleName());
        }

        // 4. Đối số hợp lệ, mã đích tự ném IllegalArgumentException.
        Method explode = type.getMethod("explode");
        try {
            explode.invoke(service);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            System.out.println("target.method: " + e.getClass().getSimpleName()
                    + " -> " + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }

        // 5. Constructor chạy rồi tự ném IllegalStateException.
        Constructor<SampleService> ctor = type.getDeclaredConstructor(int.class);
        try {
            ctor.newInstance(1);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            System.out.println("target.constructor: " + e.getClass().getSimpleName()
                    + " -> " + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }

        // 6. Một lời gọi hợp lệ để đối chiếu.
        System.out.println("success: " + echo.invoke(service, "Java"));
    }
}

class SampleService {
    public SampleService() {}

    public SampleService(int value) {
        throw new IllegalStateException("ctor failed");
    }

    public String echo(String text) {
        return "Hello " + text;
    }

    private void hidden() {}

    public void explode() {
        throw new IllegalArgumentException("from method");
    }
}
```

Ở thư mục chứa file, chạy:

```bash
javac --release 17 ReflectionFailureGuide.java
java ReflectionFailureGuide
```

`stdout` đúng:

```text
lookup.method: NoSuchMethodException
lookup.field: NoSuchFieldException
lookup.constructor: NoSuchMethodException
argument: IllegalArgumentException
receiver: NullPointerException
access.canAccess: false
access: IllegalAccessException
target.method: InvocationTargetException -> IllegalArgumentException: from method
target.constructor: InvocationTargetException -> IllegalStateException: ctor failed
success: Hello Java
```

**Giải thích theo dòng kết quả:**

1. Ba dòng `lookup.*` được tạo trước khi có Method/Field/Constructor tương ứng. Phương thức không tồn tại, field không tồn tại và constructor sai chữ ký là ba lỗi tìm kiếm riêng.
2. `argument`: `echo(String)` đã được tìm thấy, nhưng `42` là `Integer` và không thể thay `String`. `receiver`: phương thức instance không nhận receiver `null`.
3. `access.canAccess: false` và `access: IllegalAccessException`: `hidden()` là private của một top-level class khác. `getDeclaredMethod` lấy được metadata nhưng không cấp quyền gọi.
4. `target.method`: `explode()` thực sự được chạy, tự ném `IllegalArgumentException("from method")`. Reflection bọc ngoại lệ đó. Vì thế mặc dù cả dòng `argument` lẫn `target.method` có chữ “`IllegalArgumentException`”, **điểm lỗi hoàn toàn khác nhau**.
5. `target.constructor`: `SampleService(int)` bắt đầu chạy và tự ném `IllegalStateException`; `Constructor.newInstance` trả lỗi dưới dạng `InvocationTargetException`.
6. `success`: khi có đúng chữ ký, receiver, quyền truy cập và đối số, lời gọi trả `Hello Java`.

Ví dụ trên dùng lớp ở default package để có thể chạy bằng hai lệnh; khi chuyển vào project, nên đặt hai lớp trong package phù hợp. Nếu đưa chúng vào **các module khác nhau**, các điều kiện `exports`/`opens` và quyền truy cập thực tế có thể thay đổi kết quả.

## 7. Cách thiết kế xử lý lỗi trong ứng dụng

Một lớp adapter chạy plugin hoặc gọi API bằng reflection nên xác định ranh giới từng thao tác và ghi đủ ngữ cảnh để người vận hành biết **đã tìm đúng thành viên hay chưa, có quyền sử dụng không, dữ liệu có phù hợp không, và mã đích đã bắt đầu chạy chưa**.

Quy trình khuyến nghị:

1. **Lookup:** xác định class loader thích hợp; nạp `Class<?>` và tra cứu member bằng tên/chữ ký chính xác. Nếu không tìm thấy, báo rõ class và signature; phân biệt API công khai với thành viên `declared`.
2. **Access:** dùng API công khai khi có thể. Nếu cần deep reflection, kiểm tra `canAccess`/`trySetAccessible` và cấu hình module, xử lý riêng trường hợp `InaccessibleObjectException`.
3. **Argument validation:** đối chiếu receiver với `getDeclaringClass()` và kiểu tham số từ `getParameterTypes()`; kiểm tra số đối số và việc chuyển đổi primitive/wrapper/array. Không log giá trị nhạy cảm nếu không cần.
4. **Invoke:** gọi `Method.invoke` hoặc `Constructor.newInstance`. Bắt riêng `IllegalAccessException`, `IllegalArgumentException` (và `NullPointerException` khi thích hợp), `InvocationTargetException`.
5. **Unwrap target failure:** lấy `InvocationTargetException.getCause()`, giữ nguyên cause và stack trace; phân loại lỗi nghiệp vụ, lỗi có thể retry và lỗi lập trình theo hợp đồng của module. Không retry mù quáng một phương thức có side effect vì nó **đã có thể chạy được một phần trước khi ném lỗi**.

Ví dụ khung xử lý (minh họa trong một phương thức đã có biến `method`, `receiver` và `args`; không phải chương trình độc lập):

```java
try {
    Object result = method.invoke(receiver, args);
    // Xử lý result.
} catch (IllegalAccessException e) {
    // Thiếu quyền truy cập: kiểm tra visibility và opens/exports.
    throw new IllegalStateException("Reflection access denied", e);
} catch (IllegalArgumentException e) {
    // Receiver/arity/kiểu đối số sai trước khi thực thi mã đích.
    throw new IllegalArgumentException("Invalid reflective invocation", e);
} catch (InvocationTargetException e) {
    Throwable cause = e.getCause();
    // Mã đích đã chạy; giữ cause và quyết định cách báo lỗi theo hợp đồng.
    throw new IllegalStateException("Target execution failed", cause);
}
```

Ở biên API thực tế, nếu lỗi đích là checked business exception cần bảo toàn hoặc cần ánh xạ sang response nghiệp vụ, hãy thiết kế chữ ký/exception mapping tương ứng. Ví dụ gói thành `IllegalStateException` ở trên chỉ là **một chính sách minh họa**, không phải cách xử lý bắt buộc. Nếu `cause` là `Error` nghiêm trọng, ứng dụng cần chính sách lan truyền phù hợp thay vì luôn đổi nó thành lỗi nghiệp vụ có thể tiếp tục.

### 7.1. Thông tin chẩn đoán nên lưu

Khi lỗi không rõ, các thông tin sau thường đủ để khoanh vùng mà không cần dump toàn bộ object:

- Tên nhị phân của class và class loader, tên method/constructor/field, chữ ký từ `getParameterTypes()`.
- Loại member (`static` hay instance), loại receiver, số đối số và kiểu chạy của từng đối số (có thể che giá trị thật).
- Tên module/package của lớp khai báo, trạng thái truy cập và nhu cầu `exports`/`opens`.
- Tên loại exception **ngoài cùng**, stack trace, và **cause** của `InvocationTargetException` nếu có.

Ví dụ, log “`NoSuchMethodException: execute(java.lang.Integer)`” thì kiểm tra xem phương thức khai báo `execute(int)` hay `execute(Integer)`; log “`InvocationTargetException` → `IOException`” thì điều tra mã và dependency mà method đích sử dụng, không sửa chữ ký reflection.

## 8. Những trường hợp dễ chẩn đoán nhầm

| Hiện tượng | Lý giải đúng | Không nên kết luận |
| --- | --- | --- |
| `getDeclaredMethod` tìm ra private method nhưng `invoke` lỗi | Lookup thành công; access thất bại | “Tên method sai” |
| `setAccessible(true)` ném `InaccessibleObjectException` | Package/module không cho phép deep reflection theo ngữ cảnh hiện tại | “Method không tồn tại” |
| `invoke` ném `IllegalArgumentException` trực tiếp | Kiểm tra receiver/arity/đối số của lời gọi reflection | “Logic của method đích tự ném lỗi này” |
| `invoke` ném `InvocationTargetException` với cause `IllegalArgumentException` | Mã đích đã bắt đầu và tự ném lỗi | “Tham số truyền tới `invoke` chắc chắn sai kiểu” |
| `newInstance` ném `InvocationTargetException` | Constructor đã ném lỗi trong khi thực thi | “Không tìm thấy constructor” |
| `getDeclaredConstructor(...)` ném `NoSuchMethodException` | Không có constructor khớp chữ ký ở lớp đó | “Constructor tự ném exception” |
| `Class.forName` ném `ExceptionInInitializerError` | Khởi tạo lớp thất bại (static initializer) | “Chỉ cần đổi tên lớp” |
| `Field.set` lỗi khi field là `final` | Hạn chế truy cập/ghi field, tùy loại field và hoàn cảnh | “Đây là InvocationTargetException” |
| Hai class cùng tên nhưng check kiểu thất bại | Cần kiểm tra class loader và định danh kiểu thực tế | “Tên giống nhau thì luôn tương thích” |

**Chú ý về thứ tự:** Nếu một lời gọi vừa không thể truy cập vừa có đối số không hợp lệ, đừng xây dựng logic ứng dụng phụ thuộc vào việc JVM sẽ báo một loại lỗi cụ thể trước. Hãy kiểm tra từng điều kiện và điều chỉnh từng nguyên nhân.

## 9. Bài tập tự kiểm tra

**Tình huống A:** `type.getMethod("calculate", Integer.class)` ném `NoSuchMethodException`, nhưng source định nghĩa `public int calculate(int n)`. Vì sao? Cách sửa nào đúng?

**Tình huống B:** `getDeclaredMethod("secret")` trả về Method thành công, nhưng `invoke` ném `IllegalAccessException`. Bạn cần kiểm tra điều gì trước khi thử deep reflection?

**Tình huống C:** `Method.invoke` ném `InvocationTargetException` và `getCause()` là `NullPointerException`. NPE này ở đâu?

**Tình huống D:** Một lời gọi plugin tạo bản ghi vào database rồi ném `InvocationTargetException`. Có nên gọi lại ngay mà không xem cause, transaction hoặc side effect?

**Đáp án:**

- **A:** Reflection tìm chữ ký tham số chính xác; `Integer.class` khác `int.class`. Nếu contract là `calculate(int)` thì tra cứu bằng `int.class`.
- **B:** Kiểm tra quyền truy cập của declaring class, member, caller, package/module; dùng `canAccess` để xác nhận trạng thái, thiết kế API public hoặc mở package có chủ đích nếu cần.
- **C:** Method đích đã chạy và ném NPE (hoặc một helper bên trong nó ném NPE); phân tích stack trace của `getCause()`. Trái lại, `invoke` với receiver `null` cho instance method có thể ném NPE **trực tiếp**.
- **D:** Không. Method đã có thể tạo side effect trước khi thất bại. Cần xem cause và tính idempotent/transaction trước khi quyết định retry.

**Ghi nhớ:** **Không tìm thấy → lỗi lookup; tìm thấy nhưng gọi sai dữ liệu → lỗi argument; tìm thấy nhưng không được phép → lỗi access; đã vào mã đích và mã đó ném lỗi → `InvocationTargetException` với `getCause()`.** Nhìn đúng giai đoạn sẽ dẫn tới cách khắc phục đúng.
