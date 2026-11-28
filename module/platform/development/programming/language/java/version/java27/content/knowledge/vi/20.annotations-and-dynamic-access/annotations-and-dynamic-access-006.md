# MethodHandle, lookup và lựa chọn thay thế reflection trong Java 27

Trong chương **Annotation và truy cập động**, Java cho phép chương trình tìm và gọi hành vi tại thời điểm chạy, thay vì luôn viết sẵn lời gọi `object.method(...)` trong mã nguồn. Hai cơ chế quan trọng là **Reflection API** (`java.lang.reflect`) và **Method Handle API** (`java.lang.invoke`).

Một **`MethodHandle`** là một đối tượng có kiểu mô tả một thao tác có thể gọi được: gọi phương thức instance, gọi phương thức `static`, gọi constructor, đọc/ghi field hoặc thực hiện một phép biến đổi được cấu thành từ các handle khác. **`MethodHandles.Lookup`** là đối tượng mang ngữ cảnh/quyền truy cập dùng để *tìm hoặc tạo* handle. **`MethodType`** mô tả chính xác kiểu trả về và danh sách kiểu tham số của một handle.

Trong Java 27, Method Handle là API chính thức và hữu ích cho framework, thư viện động, trình xử lý annotation lúc runtime, bộ định tuyến lệnh hoặc cơ chế tạo lời gọi có thể kết hợp. Tuy nhiên **MethodHandle không thay thế mọi mục đích của reflection**: reflection vẫn phù hợp cho khám phá class/member, đọc annotation, duyệt cấu trúc type, trong khi MethodHandle thường phù hợp cho **thực thi một thao tác đã tìm ra**, đặc biệt khi cùng thao tác được gọi nhiều lần.

Bài này tập trung vào API còn được hỗ trợ, phân biệt quyền truy cập Java và JPMS, và tránh suy diễn rằng MethodHandle có thể tự động vượt qua các ranh giới module hoặc luôn nhanh hơn mọi lời gọi reflection.

## 1. Vì sao cần MethodHandle khi Java đã có Reflection API?

Với lời gọi tĩnh, compiler biết phương thức nào sẽ chạy:

```java
String text = "MethodHandle";
String prefix = text.substring(0, 6);
System.out.println(prefix); // Method
```

Với reflection, ta có thể lấy một `Method` từ tên và kiểu tham số:

```java
import java.lang.reflect.Method;

Method method = String.class.getMethod(
    "substring", int.class, int.class
);

String value = (String) method.invoke("MethodHandle", 0, 6);
System.out.println(value); // Method
```

`Method.invoke` nhận đối số linh hoạt qua varargs và kết quả kiểu `Object`; các giá trị nguyên thủy sẽ được boxing/unboxing khi phù hợp. Nếu phương thức đích ném exception, reflection thường bọc exception đó trong `InvocationTargetException`.

Với MethodHandle:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle substring = lookup.findVirtual(
    String.class,
    "substring",
    MethodType.methodType(String.class, int.class, int.class)
);

String value = (String) substring.invokeExact("MethodHandle", 0, 6);
System.out.println(value); // Method
```

`MethodHandle` có một **method type rõ ràng** và dùng các phép gọi đặc biệt `invokeExact` hoặc `invoke`. JVM có thể tối ưu việc thực thi chuỗi handle khi có điều kiện thích hợp. Tuy vậy, hiệu năng phụ thuộc cách xây dựng handle, call site, JIT, mức độ thay đổi kiểu đích và workload.

### 1.1. So sánh nhanh ba cách

| Tiêu chí | Lời gọi Java thông thường | `Method.invoke` | `MethodHandle` |
| --- | --- | --- | --- |
| Chọn phương thức | Do mã Java/compiler xác định | Tra cứu `Method` theo metadata | Tra cứu handle theo tên và `MethodType`, hoặc tạo từ reflective member |
| Kiểu đối số tại call site | Được compiler kiểm tra | Nhận dạng varargs/`Object` | `invokeExact` đòi chữ ký chính xác; `invoke` có adaptation |
| Khám phá annotation/member | Không phải mục đích chính | Rất phù hợp | Không cung cấp API quét annotation trực tiếp |
| Lỗi từ phương thức đích | Ném trực tiếp | Bọc bằng `InvocationTargetException` | Ném trực tiếp từ handle invocation |
| Tổ hợp lời gọi | Viết thêm Java code | Không phải điểm mạnh | Có combinator như `bindTo`, `asType`, `filterReturnValue`, `guardWithTest` |
| Quyền truy cập | Compiler/JVM kiểm tra | Reflection + JPMS | Quyền gắn với `Lookup` tại bước tạo handle + các quy tắc runtime |
| Hiệu năng | Thường là lựa chọn cơ bản tốt nhất | Phụ thuộc đường gọi và tối ưu JDK | Có tiềm năng tối ưu, không phải bảo đảm nhanh hơn |

**Nguyên tắc:** Nếu có thể gọi trực tiếp và type đã biết trong mã, thường không cần thay lời gọi ấy bằng MethodHandle chỉ để “tối ưu”.

## 2. Ba thành phần cốt lõi: `MethodHandle`, `MethodType`, `Lookup`

Có thể hình dung quá trình:

```text
MethodHandles.lookup()
        |
        v
      Lookup  -- findVirtual / findStatic / findConstructor / unreflect -->
        |                                                    |
        +-------------- access check -----------------------+
                                                             |
                                                             v
                                                       MethodHandle
                                                       type() -> MethodType
                                                             |
                                     invokeExact / invoke / bindTo / asType
                                                             |
                                                             v
                                                       Kết quả hoặc lỗi
```

### 2.1. `MethodType`: hàm từ danh sách tham số đến kết quả

`MethodType` được khai báo bằng:

```java
MethodType.methodType(ReturnType.class, Parameter1.class, Parameter2.class);
```

Ví dụ:

```java
import java.lang.invoke.MethodType;

MethodType addType =
    MethodType.methodType(int.class, int.class, int.class);

// (int,int)int
System.out.println(addType);

MethodType logType =
    MethodType.methodType(void.class, String.class);

// (String)void
System.out.println(logType);
```

Lưu ý thứ tự: đối số **đầu tiên** của `methodType(...)` là kiểu trả về. Các đối số sau là kiểu tham số.

Đừng nhầm `MethodType` với generic type token hoặc `java.lang.reflect.Type`. Nó mô tả **JVM method signature** bằng các kiểu `Class<?>` cụ thể; generic type arguments như `List<String>` và `List<Integer>` đều bị xóa kiểu tại runtime thành `List` trong một method descriptor thích hợp.

### 2.2. Type của handle gọi phương thức instance bao gồm receiver

Giả sử:

```java
String value = "Hello";
String result = value.substring(1, 3);
```

Khi `findVirtual(String.class, "substring", methodType(String.class, int.class, int.class))`:

- **MethodType đưa vào `findVirtual`** mô tả khai báo phương thức `substring(int,int) -> String`, **không ghi receiver**.
- **Handle nhận được** có kiểu `(String,int,int)String`: receiver là tham số đầu tiên khi gọi handle.

```java
var handle = MethodHandles.lookup().findVirtual(
    String.class,
    "substring",
    MethodType.methodType(String.class, int.class, int.class)
);

System.out.println(handle.type()); // (String,int,int)String
```

Đối với phương thức `static`, không có receiver ngầm định. Đối với constructor, handle trả instance đã tạo, không trả `void`.

### 2.3. `Lookup` mang quyền tìm thành viên

`MethodHandles.lookup()` tạo `Lookup` theo **ngữ cảnh mã gọi tại vị trí khai báo**. Vì vậy cùng một lời gọi tìm phương thức private có thể thành công khi chạy trong class có quyền truy cập, nhưng thất bại khi chạy từ package/module khác.

Đừng hiểu `Lookup` là “chìa khóa vạn năng” của toàn bộ JVM. Quyền của nó phụ thuộc caller, quan hệ lớp/nest/module, modifier và cơ chế JPMS.

## 3. Ví dụ đầy đủ: tìm instance method, static method và constructor

Ví dụ dưới đây chạy độc lập, không cần framework:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Objects;

public class MethodHandleBasicsDemo {
    public static final class Greeting {
        private final String prefix;

        public Greeting(String prefix) {
            this.prefix = Objects.requireNonNull(prefix);
        }

        public String greet(String name) {
            return prefix + ", " + name;
        }

        public static String normalize(String value) {
            return value.strip();
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // (String)Greeting: constructor nhận String, trả Greeting.
        MethodHandle ctor = lookup.findConstructor(
            Greeting.class,
            MethodType.methodType(void.class, String.class)
        );

        Greeting greeting = (Greeting) ctor.invokeExact("Hello");

        // (Greeting,String)String: có receiver là Greeting.
        MethodHandle greet = lookup.findVirtual(
            Greeting.class,
            "greet",
            MethodType.methodType(String.class, String.class)
        );

        String message = (String) greet.invokeExact(greeting, "Java 27");
        System.out.println(message); // Hello, Java 27

        // (String)String: static method không có receiver.
        MethodHandle normalize = lookup.findStatic(
            Greeting.class,
            "normalize",
            MethodType.methodType(String.class, String.class)
        );

        String cleaned = (String) normalize.invokeExact("  JPMS  ");
        System.out.println(cleaned); // JPMS
    }
}
```

Điểm quan trọng:

1. `findConstructor` nhận `MethodType` có return type `void.class`, vì **constructor trong Java không có return type khai báo**. Handle trả về instance, do đó `ctor.type()` là `(String)Greeting`.
2. `findVirtual` dùng method type **không chứa receiver**, nhưng handle được gọi phải truyền receiver.
3. `findStatic` sử dụng đúng signature của phương thức `static`.
4. Các lời gọi `invokeExact` có kiểu receiver, tham số và **kiểu kết quả tại call site** đúng với `handle.type()`.
5. `main` khai báo `throws Throwable`, vì `MethodHandle.invokeExact` có thể chuyển tiếp `Throwable` từ phương thức đích. Trong ứng dụng thực, cần xử lý exception theo hợp đồng nghiệp vụ thay vì ném mọi thứ ra ngoài.

### 3.1. Khi không tìm thấy hoặc không có quyền

- Sai tên hoặc sai chữ ký phương thức/constructor: `NoSuchMethodException` (hoặc một lỗi tra cứu tương ứng cho field).
- Thành viên tồn tại nhưng `Lookup` không có quyền: `IllegalAccessException`.
- Đối số hoặc kiểu kết quả không phù hợp ở lần gọi: thường `WrongMethodTypeException` cho sai descriptor; một số adaptation có thể dẫn đến `ClassCastException`.
- Receiver `null` cho thao tác instance: có thể dẫn đến `NullPointerException` khi thực thi.
- Phương thức đích tự ném exception: exception đó đi ra ngoài trực tiếp theo ngữ nghĩa handle invocation.

Các lỗi được phát hiện ở **hai thời điểm khác nhau**: khi **tạo handle** và khi **gọi handle**. Đừng gộp tất cả thành một exception “reflection failed” không có ngữ cảnh.

## 4. `invokeExact`: chính xác cả tham số lẫn kiểu trả về

`MethodHandle.invokeExact(...)` là một phương thức **signature-polymorphic**. Trình biên dịch và JVM dùng các kiểu tại **call site** để xác định method descriptor cần thiết. Không phải cơ chế varargs bình thường và không tự áp dụng các chuyển đổi linh hoạt như `Method.invoke`.

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

var add = MethodHandles.lookup().findStatic(
    Math.class,
    "addExact",
    MethodType.methodType(int.class, int.class, int.class)
);

// Handle có type (int,int)int.
int sum = (int) add.invokeExact(3, 4);
System.out.println(sum); // 7
```

Nếu một biểu thức gọi yêu cầu return type `long` trong khi handle thực tế trả `int`, descriptor không khớp:

```java
// Sai dù primitive int có thể widen thành long ở lời gọi Java thường:
// long sum = (long) add.invokeExact(3, 4);
// Có thể ném WrongMethodTypeException khi chạy.
```

Tương tự, đừng truyền `Integer` object vào call site đang yêu cầu đúng `int` nếu bạn dùng `invokeExact` mà không chủ động chuyển thành primitive `int`.

### 4.1. `void` và các ngữ cảnh không dùng kết quả

Ngay cả việc **bỏ qua return value** cũng ảnh hưởng đến call-site type:

```java
// Handle add trả int, nhưng lời gọi sau xuất hiện như lời gọi void.
// add.invokeExact(3, 4); // Sai descriptor, có thể ném WrongMethodTypeException.
```

Chỉ cần dùng kết quả đúng kiểu hoặc chuyển handle bằng API thích hợp. Khi kiểm tra đoạn mã lỗi kiểu handle, hãy in `handle.type()` và so sánh với kiểu Java mà call site thực sự yêu cầu.

### 4.2. Không phải compiler luôn biết handle trỏ tới đâu

Một biến `MethodHandle` có **kiểu tĩnh là MethodHandle**, không chứa `MethodType` dưới dạng generic type parameter. Vì thế compiler có thể cho phép biểu thức `invokeExact` biên dịch nhưng lúc chạy JVM báo mismatch với `handle.type()`.

**Hợp đồng type ở đây được kiểm tra mạnh tại runtime**, không phải compiler chứng minh toàn bộ target signature tại compile time.

## 5. `invoke`: thích ứng kiểu theo quy tắc `asType`

`MethodHandle.invoke(...)` cũng là signature-polymorphic, nhưng có thể tự áp dụng các chuyển đổi được cho phép bởi cơ chế `asType`.

```java
var add = MethodHandles.lookup().findStatic(
    Math.class,
    "addExact",
    MethodType.methodType(int.class, int.class, int.class)
);

int exact = (int) add.invokeExact(3, 4);
long adapted = (long) add.invoke(3, 4);

System.out.println(exact);   // 7
System.out.println(adapted); // 7
```

Ở dòng thứ hai, `invoke` có thể thích ứng return value `int` thành `long` cho call site.

Khác biệt cốt lõi:

| API | Điều kiện | Phù hợp |
| --- | --- | --- |
| `invokeExact` | Call-site descriptor khớp chính xác `handle.type()` | Hot path đã biết type, hợp đồng chặt |
| `invoke` | Call-site descriptor có thể thích ứng với `handle.type()` theo `asType` | Cần một số chuyển đổi hợp lệ |
| `invokeWithArguments` | Nhận danh sách/varargs đối số động, qua cơ chế gọi linh hoạt | Code động cần truyền đối số như `Object` nhưng thường có overhead |

Chuyển đổi không hợp lệ vẫn dẫn đến lỗi. **`invoke` không tự tìm overload khác theo tên**, không tự chọn một phương thức mới và không hợp pháp hóa mọi phép cast kiểu.

### 5.1. `asType`: chuyển đổi handle một lần

Thay vì muốn mỗi call site diễn tả adaptation, bạn có thể tạo một handle khác với method type được thích ứng:

```java
import java.lang.invoke.MethodType;

var add = MethodHandles.lookup().findStatic(
    Math.class,
    "addExact",
    MethodType.methodType(int.class, int.class, int.class)
);

var addAsLong = add.asType(
    MethodType.methodType(long.class, int.class, int.class)
);

long result = (long) addAsLong.invokeExact(20, 22);
System.out.println(result); // 42
```

`addAsLong` vẫn gọi `Math.addExact(int,int)`, nhưng expose return type `long` bằng chuyển đổi hợp lệ. Nếu yêu cầu chuyển đổi không thể thực hiện theo quy tắc API, việc tạo adapter có thể thất bại bằng `WrongMethodTypeException` hoặc việc thực thi chuyển đổi có thể ném lỗi tương ứng.

**Không nhầm `asType` với `cast` một object bất kỳ**. Mỗi adaptation có quy tắc cụ thể cho primitive conversion, reference casting, boxing/unboxing và `void`.

## 6. `Lookup`: kiểm soát quyền theo ngữ cảnh gọi

Đây là phần quan trọng nhất khi dùng MethodHandle trong framework và modular application. Một `Lookup` là đối tượng **mang khả năng truy cập** (*capability*): khi nó cho phép tra cứu thành viên, kết quả có thể trở thành một handle gọi được ngay cả khi code cầm handle về sau không trực tiếp được phép truy cập thành viên đó bằng cú pháp Java.

```java
import java.lang.invoke.MethodHandles;

class Vault {
    private String secret() {
        return "only Vault can call this directly";
    }

    MethodHandles.Lookup lookupForTrustedCode() {
        return MethodHandles.lookup();
    }
}
```

`lookupForTrustedCode()` minh họa một **rủi ro thiết kế**: nếu trả một `Lookup` có quyền mạnh cho code không đáng tin, code đó có thể lấy các handle mà nó không thể tự tạo trong ngữ cảnh của mình. **Không public hóa Lookup có quyền private trừ khi đó là chủ ý và đã đánh giá rủi ro.**

### 6.1. `MethodHandles.lookup()` và `publicLookup()`

- `MethodHandles.lookup()` tạo lookup theo **caller class** tại nơi gọi, với quyền truy cập tương ứng.
- `MethodHandles.publicLookup()` tạo lookup giới hạn cho thành viên **public có thể truy cập công khai**, phù hợp cho tiện ích thao tác các public API được export vô điều kiện theo quy tắc module.

```java
var publicLookup = MethodHandles.publicLookup();

var length = publicLookup.findVirtual(
    String.class,
    "length",
    MethodType.methodType(int.class)
);

int size = (int) length.invokeExact("Java");
System.out.println(size); // 4
```

**Không dùng `publicLookup()` rồi mong lấy được private method**. Tìm kiếm phải tuân theo visibility, và trong ứng dụng JPMS, package cần được export phù hợp. Với qualified exports, lookup theo module/caller cụ thể có thể cần thiết.

### 6.2. `Lookup.in(...)` không tăng quyền

```java
var narrowed = MethodHandles.lookup().in(SomeClass.class);
```

`in` thay đổi lookup class và **có thể làm giảm** quyền so với lookup ban đầu, chứ không cung cấp quyền tùy ý đối với `SomeClass`. Đây không phải cách vượt `private` hoặc `opens`. Khi cần private access hợp lệ sang một class khác, xem `privateLookupIn`.

### 6.3. Quyền tra cứu khác quyền gọi sau khi đã có handle

Java thực hiện kiểm tra quyền khi giải quyết member/handle qua `Lookup`, và có các kiểm tra áp dụng tại runtime. Không nên coi handle là tên phương thức có thể tái tra cứu tùy ý ở nơi khác. Một handle đã được cấp hợp lệ có thể được **truyền** cho code khác sử dụng, nên API nào nhận/trả handle phải xem đó là khả năng truy cập cần bảo vệ.

## 7. `privateLookupIn`: truy cập private có kiểm soát

Khi một thư viện hoặc framework được **ủy quyền** để nhìn vào private member của class đích, API hiện hành là:

```java
MethodHandles.Lookup targetLookup =
    MethodHandles.privateLookupIn(Target.class, callerLookup);
```

`privateLookupIn` không tự bỏ qua encapsulation. Lookup gốc cần quyền phù hợp (bao gồm các điều kiện về private/module access); nếu hai class thuộc các module khác nhau, **module caller phải đọc module đích** và **package chứa `Target` phải `opens` tới module caller**, theo quy tắc JPMS.

### 7.1. Ví dụ cùng module

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class PrivateAccessDemo {
    static final class Account {
        private String format(String id) {
            return "ACC-" + id;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup caller = MethodHandles.lookup();
        MethodHandles.Lookup accountLookup =
            MethodHandles.privateLookupIn(Account.class, caller);

        var format = accountLookup.findVirtual(
            Account.class,
            "format",
            MethodType.methodType(String.class, String.class)
        );

        Account account = new Account();
        String output = (String) format.invokeExact(account, "42");
        System.out.println(output); // ACC-42
    }
}
```

Đoạn mã đặt class đích là nested class trong cùng chương trình, nên việc cấp quyền là minh bạch. `privateLookupIn` hữu ích đặc biệt khi cần lookup với ngữ cảnh một class khác và điều kiện module cho phép.

### 7.2. Ví dụ module descriptor cho framework

Giả sử framework nằm trong module `com.example.mapper`, class cần ánh xạ nằm trong package `com.example.domain.model` của module `com.example.domain`.

**Module chứa model:**

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.mapper;
}
```

**Module framework:**

```java
module com.example.mapper {
    requires com.example.domain;
}
```

Framework có thể dùng `privateLookupIn` khi đã có lookup hợp lệ và thỏa điều kiện module/package. Ví dụ chỉ thể hiện **quy tắc quyền truy cập**; trong một kiến trúc thực tế, framework tổng quát thường không nên khai báo `requires` tới từng module ứng dụng. Có thể phải thiết kế service API, module layers hoặc cơ chế injection phù hợp để tạo đúng read edges.

`exports` chỉ cấp quyền truy cập code Java thông thường đến **public API**; nó **không tự cấp** quyền private lookup. `opens` cấp quyền deep reflection/lookup cho runtime nhưng **không tự cho phép import public type** như `exports`.

### 7.3. Khi `privateLookupIn` thất bại

Các nguyên nhân thường gặp:

1. Lookup caller không có quyền cần thiết.
2. Module caller không đọc module chứa target.
3. Package target chưa open tới caller module.
4. Target class hoặc class loader/module layer không nằm trong cấu hình có thể truy cập.
5. Mã đang cố truy cập member không tồn tại hoặc sai `MethodType`.

Đừng dùng `--add-opens` một cách tràn lan để làm mọi lỗi biến mất. Ưu tiên chỉnh module descriptor theo đúng contract hoặc sử dụng public API. `--add-opens` có thể hữu ích khi di trú/test nhưng là quyền runtime bổ sung có phạm vi cụ thể.

## 8. `findVirtual`, `findStatic`, `findConstructor`, `findSpecial`

Những phương thức tìm handle cơ bản của `Lookup`:

| Lookup API | Mục đích | Type của handle sau khi tạo |
| --- | --- | --- |
| `findVirtual(refc, name, methodType)` | Gọi instance method | Thêm receiver vào đầu danh sách tham số |
| `findStatic(refc, name, methodType)` | Gọi static method | Giữ kiểu tham số và return type đã khai báo |
| `findConstructor(refc, methodType)` | Tạo object | Return type là type của instance được tạo |
| `findSpecial(refc, name, methodType, specialCaller)` | Thực hiện lời gọi theo `invokespecial` (vd. super/default method) | Theo semantics special invocation và quyền |
| `findGetter` / `findSetter` | Đọc/ghi field | Tạo handle với kiểu getter/setter tương ứng |
| `unreflect(Method)` | Tạo handle từ reflective `Method` | Phụ thuộc static/instance và member |
| `unreflectConstructor(Constructor)` | Tạo handle constructor đã tìm bằng reflection | Return type là class được tạo |

`findSpecial` liên quan đến quyền **special caller** và ngữ nghĩa lời gọi super/default method. Nó không đơn thuần là “tìm mọi private method” và không nên chọn thay `findVirtual` chỉ vì một method không public.

### 8.1. Handle cho getter của field

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

class Reading {
    public final int value;

    Reading(int value) {
        this.value = value;
    }
}

MethodHandle getter = MethodHandles.lookup()
    .findGetter(Reading.class, "value", int.class);

int result = (int) getter.invokeExact(new Reading(42));
System.out.println(result); // 42
```

Với field `final`, không thể tùy tiện tạo setter như thể field mutable. Khi cần truy cập biến và thao tác nguyên tử, hãy cân nhắc **`VarHandle`**.

## 9. `VarHandle`: lựa chọn phù hợp cho truy cập biến

`VarHandle` nằm trong `java.lang.invoke` nhưng **khác** `MethodHandle`. Nó mô tả một vị trí dữ liệu có thể đọc/ghi qua những **access modes** như `get`, `set`, `getVolatile`, `setVolatile`, `compareAndSet`, `getAndAdd`, tùy loại biến và tính hợp lệ của mode.

Một ví dụ về thao tác nguyên tử với field:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleDemo {
    static final class Counter {
        volatile int value;
    }

    public static void main(String[] args) throws Throwable {
        VarHandle value = MethodHandles.lookup()
            .findVarHandle(Counter.class, "value", int.class);

        Counter counter = new Counter();

        boolean changed = value.compareAndSet(counter, 0, 1);
        System.out.println(changed); // true

        int old = (int) value.getAndAdd(counter, 5);
        int now = (int) value.getVolatile(counter);

        System.out.println(old); // 1
        System.out.println(now); // 6
    }
}
```

`findVarHandle` cũng thực hiện access check theo `Lookup`; không thể dùng nó để vượt private fields trong một module không mở cho caller.

### 9.1. Khi nào dùng VarHandle thay cho reflection Field?

- Khi cần thao tác biến với memory-order semantics chính xác: plain, opaque, acquire/release, volatile.
- Khi cần atomic operation như CAS hoặc get-and-add.
- Khi xây dựng cấu trúc dữ liệu cạnh tranh hoặc framework cấp thấp có lý do rõ ràng.

Với logic nghiệp vụ thông thường, hãy ưu tiên field access qua API public, `AtomicInteger` hoặc class concurrent của JDK khi phù hợp. **VarHandle không tự khiến toàn bộ thuật toán thread-safe**; phải hiểu memory model và invariant đa biến.

### 9.2. Method handle cho field và VarHandle là hai công cụ khác nhau

`findGetter` tạo `MethodHandle` để đọc field. `findVarHandle` tạo một `VarHandle` để thực thi các access mode; từ `VarHandle` có thể lấy các method handle tương ứng với access mode bằng API liên quan, nhưng điều đó không khiến mọi field có thể ghi hoặc mọi thao tác trở thành atomic.

Không dùng VarHandle chỉ để đọc một property đơn giản nếu getter Java thường đã đáp ứng yêu cầu.

## 10. Chuyển từ Reflection API sang MethodHandle bằng `unreflect`

Một thư viện thường cần **khám phá** phương thức và annotation qua reflection, sau đó muốn gọi phương thức đã chọn nhiều lần.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Method;

Method method = String.class.getMethod("toUpperCase");

MethodHandle upper = MethodHandles.publicLookup()
    .unreflect(method);

String result = (String) upper.invokeExact("java");
System.out.println(result); // JAVA
```

`Class.getMethod`, `getDeclaredMethods`, `Method.getAnnotation` và các API reflection là công cụ đúng để **đọc metadata**. `unreflect` dùng reflective `Method` để tạo handle thực thi.

**`unreflect` không tự bypass access checks.** Quyền vẫn dựa trên `Lookup` và các quy tắc Reflection/JPMS có liên quan. Đừng cho rằng việc cầm một `Method` là đủ để có quyền lấy handle private tùy ý.

### 10.1. `setAccessible` và `InaccessibleObjectException`

Khi reflection cần vượt access checks của Java, `AccessibleObject.setAccessible(true)` cũng chịu các giới hạn JPMS. Nếu module đích không mở package cho module gọi, runtime có thể ném `InaccessibleObjectException`.

`privateLookupIn` và `setAccessible` không phải hai “cửa sau” đi vòng mô hình module; cả hai đều phải tuân theo quyền truy cập và open packages.

## 11. Kết hợp các MethodHandle thành phép gọi mới

Một điểm mạnh của MethodHandle là có thể **tạo handle mới từ handle có sẵn** mà không cần sinh class thủ công. Các phép biến đổi thường gặp:

| Combinator / adapter | Ý nghĩa |
| --- | --- |
| `bindTo(receiver)` | Gắn cố định receiver/tham số reference đầu |
| `insertArguments(target, pos, values...)` | Gắn trước các đối số ở vị trí chỉ định |
| `dropArguments(target, pos, types...)` | Thêm tham số nhận vào nhưng bỏ qua |
| `filterArguments(target, pos, filters...)` | Biến đổi đầu vào trước khi gọi target |
| `filterReturnValue(target, filter)` | Biến đổi kết quả của target |
| `guardWithTest(test, target, fallback)` | Chọn một trong hai handle theo predicate |
| `asType(newType)` | Tạo adapter chuyển đổi call-site type |
| `asCollector` / `asSpreader` | Chuyển đổi giữa array argument và dãy đối số |
| `permuteArguments` | Đổi thứ tự hoặc tái sử dụng tham số theo mapping |

Mỗi combinator có yêu cầu nghiêm ngặt về kiểu tham số và kết quả. **Đừng đoán** vị trí tham số sau mỗi lần biến đổi: xem `handle.type()` để kiểm tra.

### 11.1. `bindTo`: giữ cố định receiver

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

var length = MethodHandles.lookup().findVirtual(
    String.class, "length", MethodType.methodType(int.class)
);

var javaLength = length.bindTo("Java 27");

// Ban đầu: (String)int. Sau bindTo: ()int.
System.out.println(javaLength.type()); // ()int

int size = (int) javaLength.invokeExact();
System.out.println(size); // 7
```

`bindTo` thường được dùng để tạo callback cho một đối tượng cụ thể. Nó cũng giữ tham chiếu tới receiver được bind trong thời gian handle còn reachable; cần lưu ý vòng đời khi cache handle lâu dài.

### 11.2. `insertArguments`: giữ cố định tham số

```java
var add = MethodHandles.lookup().findStatic(
    Math.class,
    "addExact",
    MethodType.methodType(int.class, int.class, int.class)
);

// Gắn đối số thứ hai = 10.
var plusTen = MethodHandles.insertArguments(add, 1, 10);

System.out.println(plusTen.type()); // (int)int
int result = (int) plusTen.invokeExact(32);
System.out.println(result); // 42
```

`insertArguments` cho phép gắn cả primitive argument theo kiểu thích hợp. Khác với `bindTo`, nó không chỉ giới hạn vào reference argument đầu tiên.

### 11.3. `filterReturnValue`: biến đổi kết quả theo pipeline

```java
var upper = MethodHandles.lookup().findVirtual(
    String.class,
    "toUpperCase",
    MethodType.methodType(String.class)
);

var length = MethodHandles.lookup().findVirtual(
    String.class,
    "length",
    MethodType.methodType(int.class)
);

// upper: (String)String; length: (String)int
var upperLength = MethodHandles.filterReturnValue(upper, length);

// upperLength: (String)int
int result = (int) upperLength.invokeExact("hello");
System.out.println(result); // 5
```

Combinator này nối kết quả `String` của `upper` làm đầu vào cho `length`. Nếu return/parameter types không tương thích với contract của `filterReturnValue`, việc tạo handle thất bại.

Các combinator hữu ích trong framework hoặc runtime cần nhiều phép biến đổi có thể cache/tái sử dụng, nhưng có thể làm code khó đọc nếu lạm dụng cho nghiệp vụ đơn giản.

## 12. Annotation discovery + MethodHandle execution: ví dụ thực tế

Trong cùng một hệ thống, annotation và MethodHandle có vai trò bổ sung: annotation mô tả **metadata**; reflection khám phá; MethodHandle tạo lời gọi.

Ví dụ sau tìm các handler được gắn `@Action`, kiểm tra signature và cache handle đã bind tới instance. Code độc lập, chạy được với Java hiện đại:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

public class ActionDispatcherDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Action {
        String value();
    }

    static final class Handlers {
        @Action("greet")
        public String greet(String name) {
            return "Hello, " + name;
        }

        @Action("shout")
        public String shout(String value) {
            return value.toUpperCase();
        }
    }

    static Map<String, MethodHandle> discover(Handlers target)
            throws IllegalAccessException {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType expected =
            MethodType.methodType(String.class, String.class);

        Map<String, MethodHandle> routes = new HashMap<>();

        for (Method method : Handlers.class.getDeclaredMethods()) {
            Action annotation = method.getAnnotation(Action.class);
            if (annotation == null) {
                continue;
            }

            // unreflect instance method: (Handlers,String)String
            // bindTo target: (String)String
            MethodHandle handle = lookup.unreflect(method).bindTo(target);
            if (!handle.type().equals(expected)) {
                throw new IllegalArgumentException(
                    "Invalid action signature: " + method.getName()
                );
            }

            if (routes.putIfAbsent(annotation.value(), handle) != null) {
                throw new IllegalArgumentException(
                    "Duplicate action: " + annotation.value()
                );
            }
        }

        return Map.copyOf(routes);
    }

    public static void main(String[] args) throws Throwable {
        Map<String, MethodHandle> routes =
            discover(new Handlers());

        MethodHandle greet = routes.get("greet");
        if (greet == null) {
            throw new IllegalStateException("Missing greet handler");
        }

        String result = (String) greet.invokeExact("Java 27");
        System.out.println(result); // Hello, Java 27
    }
}
```

Phân tích:

1. `@Retention(RUNTIME)` bảo đảm annotation có thể được đọc qua Reflection API tại runtime.
2. `getDeclaredMethods()` dùng để **khám phá** methods; thứ tự trả về **không được bảo đảm**, nên code không phụ thuộc thứ tự duyệt.
3. `getAnnotation(Action.class)` kiểm tra metadata.
4. `lookup.unreflect(method)` lấy handle trên cơ sở quyền của lookup hợp lệ.
5. `bindTo(target)` loại receiver khỏi method type để có chữ ký thống nhất `(String)String`.
6. Kiểm tra `handle.type()` làm hợp đồng handler rõ ràng; `putIfAbsent` phát hiện action trùng.
7. `Map.copyOf` tạo map không thể sửa về cấu trúc; các handle và receiver vẫn giữ tham chiếu theo vòng đời map.
8. `invokeExact` gọi đúng chữ ký; không cần tra cứu lại method ở mỗi request.

**Trong production:** cần bổ sung kiểm soát quyền cho action, xử lý exception nghiệp vụ, công bố định dạng input/output, cơ chế đăng ký/thu hồi handler, quy tắc cho class loader/module và cache lifetime. Annotation không phải cơ chế authorization; kẻ gửi request không tự nhiên được phép gọi mọi method chỉ vì method được gắn annotation.

## 13. JPMS và strong encapsulation

Trong ứng dụng có `module-info.java`, quyền truy cập cần xét đồng thời:

- **Readability:** module caller có đọc module target không?
- **Exports:** package của public API có được export tới module caller không?
- **Opens:** package của target có được mở cho deep reflection/private lookup không?
- **Quyền của `Lookup`:** lookup object mang ngữ cảnh/capability nào khi tạo?

Bảng tham khảo:

| Mục tiêu | Thường cần |
| --- | --- |
| Gọi public method thuộc public class trong exported package | Readability + exports + quyền type/member |
| Tạo public handle qua `publicLookup` | Type/member public và package có khả năng truy cập công khai theo JPMS |
| Deep reflection vào private field ở module khác | Package target mở tới caller module và quyền reflection phù hợp |
| `privateLookupIn` sang module khác | Caller lookup có quyền yêu cầu; module caller đọc target; target package mở tới caller |
| Gọi private method nhờ handle đã cấp hợp lệ | Sở hữu handle hợp lệ; phải xem đây là capability nhạy cảm |
| Import type từ package chỉ `opens`, không `exports` | **Không đủ** để Java source truy cập trực tiếp |

### 13.1. Không dùng tùy chọn mở nội bộ JDK như thiết kế lâu dài

Một số hệ thống di trú dùng `--add-opens` để thử nghiệm hoặc để framework cũ chạy. Với Java 27, không nên xây library mới bằng cách truy cập không được hỗ trợ vào các package nội bộ JDK. Ưu tiên public APIs của JDK hoặc hợp đồng module `opens` rõ ràng giữa những module do bạn kiểm soát.

`privateLookupIn` cũng **không** là cách lách strong encapsulation của JDK. Nếu package không được mở, việc yêu cầu quyền private sẽ thất bại theo quy tắc API.

## 14. Ngoại lệ và cách báo lỗi có ngữ cảnh

Khác nhau giữa lỗi **lookup**, **adaptation** và **target execution**:

| Giai đoạn | Ví dụ lỗi | Cách xử lý |
| --- | --- | --- |
| Tìm phương thức | `NoSuchMethodException` | Kiểm tra tên, overload, `MethodType`, receiver/static |
| Kiểm tra truy cập | `IllegalAccessException` | Kiểm tra `Lookup`, modifier, JPMS exports/opens |
| Thích ứng/call-site type | `WrongMethodTypeException` | In `handle.type()`, đối chiếu call-site descriptor |
| Ép kiểu reference | `ClassCastException` | Xác thực input và conversion contract |
| Receiver không hợp lệ/null | `NullPointerException` hoặc lỗi loại liên quan | Kiểm tra receiver và phương thức đích |
| Thực thi phương thức | Bất kỳ `Throwable` từ target | Xử lý như lỗi nghiệp vụ, không mặc định bọc trong `InvocationTargetException` |

Để thông báo lỗi dễ chẩn đoán, nên ghi (không lộ bí mật) các trường như:
- Tên operation/handler.
- Target class, method name, và `MethodType` mong đợi.
- `handle.type()` thực tế.
- Tên module/package liên quan nếu lỗi access.
- Mã correlation ID của request nếu chạy trong server.

Đừng log toàn bộ argument payload một cách vô điều kiện: đối số có thể chứa token hoặc dữ liệu nhạy cảm.

### 14.1. Phân biệt phản chiếu method và handle khi target ném exception

```java
// Reflection:
try {
    method.invoke(receiver, args);
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable original = ex.getCause();
    // Xử lý nguyên nhân thực tế.
}
```

Trong cơ chế MethodHandle, exception từ target được ném trực tiếp; nếu gọi `invokeExact`, API khai báo `throws Throwable`, nên thiết kế ranh giới catch/throws theo ứng dụng. Không mặc nhiên cast mọi `Throwable` thành `Exception` nếu hợp đồng xử lý lỗi chưa rõ.

## 15. Performance: có nên thay Reflection API bằng MethodHandle?

**Không có quy tắc “MethodHandle luôn nhanh hơn Reflection”.** Các JDK hiện đại đã tối ưu nhiều đường gọi reflection, và chính reflection core được triển khai dựa trên MethodHandle từ Java 18 (JEP 416). Mức khác biệt thực tế phụ thuộc:

- Handle được tìm **một lần và cache**, hay tra cứu mới ở mỗi request.
- Call site có kiểu ổn định hay liên tục thay đổi.
- Có `invokeExact` với descriptor phù hợp hay adaptation phức tạp.
- Có boxing/unboxing, spreader/collector hoặc `invokeWithArguments`.
- Số lượng combinator, cơ hội inline của JIT và mức độ polymorphic.
- Reflection đã cache `Method` chưa, kích thước method đích và chi phí nghiệp vụ so với overhead gọi.
- Thời gian warm-up, GC và cấu hình JDK/JVM cụ thể.

### 15.1. Tránh so sánh sai lệch

Một benchmark kém:

```java
for (int i = 0; i < n; i++) {
    var handle = MethodHandles.lookup().findVirtual(...);
    handle.invoke(...);
}
```

Nó đo cả **chi phí lookup** lặp lại, trong khi một framework thực tế có thể cache handle sau khi kiểm tra annotation lúc khởi động.

Một benchmark khác chỉ đo một thao tác cộng cực nhỏ có thể phóng đại chi phí invocation trong khi ứng dụng thực gọi database hoặc xử lý I/O. Hãy đo workload đại diện, warm-up JVM và dùng JMH hay công cụ benchmark tương đương khi cần số liệu đáng tin cậy.

### 15.2. Khi nào có ích?

- Framework dispatch gọi cùng handler nhiều lần.
- Thư viện cần compose các thao tác có chữ ký kiểu rõ.
- Runtime code generation hoặc các API liên quan `invokedynamic`.
- Nơi reflection để khám phá ban đầu rồi dùng handle đã cache để thực thi thường xuyên.

Đối với thao tác không thường xuyên, reflection đơn giản, dễ debug và hiệu năng đã đủ có thể là lựa chọn tốt hơn.

## 16. Lambda, method reference và `LambdaMetafactory`

Một lambda như:

```java
java.util.function.Function<String, Integer> length = String::length;
```

được biểu diễn bằng một functional interface có kiểu rõ ràng. Compiler/runtime có thể dùng `invokedynamic` và các cơ chế liên quan `LambdaMetafactory` để tạo đối tượng triển khai phù hợp, nhưng bạn **không cần tự gọi `LambdaMetafactory`** chỉ để dùng lambda.

`java.lang.invoke.LambdaMetafactory` là API nâng cao khi một framework cần kết nối method handle với một functional interface theo hợp đồng nghiêm ngặt. API này có giới hạn về kind của implementation handle, chữ ký và điều kiện accessibility; không thể chuyển mọi handle tùy ý thành lambda chỉ bằng một phép cast.

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Viết callback với type đã biết | Lambda hoặc method reference |
| Gọi phương thức Java thông thường | Lời gọi trực tiếp |
| Đọc metadata và annotation | Reflection |
| Tạo callable target theo tên/signature runtime | MethodHandle + Lookup |
| Xây dựng functional interface từ cơ chế dynamic linking phức tạp | `LambdaMetafactory` khi có lý do kỹ thuật rõ |
| Đọc/ghi biến và CAS | VarHandle hoặc API concurrent phù hợp |

Không nên biến code nghiệp vụ bình thường thành chuỗi method handle chỉ vì lambda trong JVM có liên quan đến `invokedynamic`.

## 17. Bảo mật: `Lookup` và handle là quyền truy cập có thể truyền đi

Rủi ro lớn không phải MethodHandle “bỏ qua Java security” mà là **mã có quyền tạo và chuyển giao handle một cách vô ý**.

Hãy bảo vệ hệ thống bằng các nguyên tắc sau:

1. Không trả một `Lookup` có quyền private cho plugin/caller không đáng tin.
2. Giới hạn package `opens` tới module thực sự cần deep reflection.
3. Không coi annotation là danh sách quyền tự động: chỉ đăng ký handler đã được kiểm định.
4. Validate method signature và dữ liệu trước khi invoke.
5. Dùng allowlist cho tên operation có thể gọi từ network/API boundary.
6. Không tùy ý mở các private members của JDK hoặc application chỉ để sửa lỗi access.
7. Nếu cache handle bound tới receiver, đánh giá nguy cơ giữ object lâu hơn vòng đời mong muốn.
8. Xử lý class loader/module layer lifecycle khi hot-reload plugin; cache handle có thể giữ class/class loader reachable.
9. Giữ exception và telemetry đủ để chẩn đoán, không lộ secret qua log.

Một handle hợp lệ có thể là một **capability** mang quyền gọi hành vi không có trong API public. Việc giữ/cấp phát handle là một phần của thiết kế API và trust boundary.

## 18. Khi nào nên dùng và khi nào nên tránh?

Quyết định có thể theo các câu hỏi:

| Câu hỏi | Hướng lựa chọn |
| --- | --- |
| Tên method và type đã biết lúc compile? | Gọi trực tiếp, dùng interface/lambda |
| Cần liệt kê methods hoặc đọc `@Annotation`? | Reflection |
| Cần gọi cùng member được khám phá nhiều lần? | Reflection để discover, MethodHandle đã cache để invoke nếu thấy có lợi |
| Cần public member trong một modular library? | Đảm bảo `requires`/`exports`, dùng Lookup phù hợp |
| Cần private access qua module? | Có thể dùng `privateLookupIn` **chỉ khi** module/package cấp quyền |
| Chỉ muốn lấy/đặt field? | Getter/setter thường; VarHandle khi cần memory semantics hay atomic access |
| Cần tạo adapter có thể kết hợp? | MethodHandle combinators |
| Framework chỉ chạy vài thao tác lúc khởi động? | Reflection đơn giản có thể là đủ |
| Tác vụ chủ yếu là I/O hoặc nghiệp vụ nặng? | Tối ưu phần tốn thời gian trước, đừng giả định invocation là bottleneck |
| API cần kiểm soát quyền? | Thiết kế contract, module boundary và authorization; đừng giao quyền ngầm qua handle |

## 19. Lỗi thường gặp và cách khắc phục

| Hiểu nhầm/lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| `findVirtual` truyền cả receiver vào `MethodType` đầu vào | `findVirtual` tự thêm receiver vào type của handle | Chỉ khai báo tham số thực của instance method |
| Dùng return type `void` khi gọi handle trả `int` qua `invokeExact` | Return type là một phần call-site descriptor | Cast/nhận đúng return type hoặc chủ động adapter |
| Mong `invokeExact` tự boxing/widening | Nó yêu cầu chính xác descriptor | Dùng `invoke`/`asType` nếu cần adaptation hợp lệ |
| Nghĩ `invoke` sẽ tự tìm overload khác | Handle đã trỏ tới một target cụ thể | Tra cứu target đúng name/signature |
| Tưởng `lookup.in(Target.class)` cấp private access | `in` không tăng quyền | Dùng `privateLookupIn` với quyền và module opens hợp lệ |
| Gọi `publicLookup()` để lấy private method | Lookup public không có quyền đó | Chỉ truy cập API public hoặc cấp quyền có kiểm soát |
| Nghĩ `setAccessible(true)` hay `privateLookupIn` vượt JPMS | Strong encapsulation vẫn được kiểm tra | Export/open package đúng và cấp read edge |
| `unreflect(Method)` bỏ mọi kiểm tra quyền | Vẫn cần Lookup đủ quyền | Xác định quyền của caller và member |
| Cache bound handle trong static map mà quên vòng đời object | Handle giữ receiver/class reachable | Thiết kế cache lifecycle, remove khi không dùng |
| Đọc annotation bằng MethodHandle thuần | MethodHandle là callable, không cung cấp API khám phá metadata | Dùng Reflection API |
| Dùng VarHandle mà không hiểu memory order | Có thể tạo race/invariant sai | Dùng Atomic classes/concurrent collections hoặc thiết kế concurrency bài bản |
| Benchmark lookup + invoke mỗi vòng rồi kết luận API chậm | Đo cả bước tra cứu không đại diện | Cache handle và benchmark phần hot path |
| Bắt `InvocationTargetException` quanh `invokeExact` | Target exception không bị Reflection API wrapper | Bắt và xử lý lỗi target trực tiếp |
| Nghĩ MethodHandle thay được authorization | Việc gọi được target không đồng nghĩa caller nghiệp vụ được cấp quyền | Kiểm soát operation và tham số ở boundary |

## 20. Câu hỏi tự kiểm tra

**1.** `findVirtual(String.class, "length", MethodType.methodType(int.class))` trả handle type nào?

**Trả lời:** `(String)int`; một tham số receiver `String` được thêm vào khi gọi handle.

**2.** `invokeExact` khác `invoke` như thế nào?

**Trả lời:** `invokeExact` đòi descriptor ở call site khớp đúng `handle.type()`, gồm kiểu trả về. `invoke` có thể thích ứng type theo quy tắc `asType`.

**3.** `MethodHandles.lookup()` có phải luôn tìm được private method của class bất kỳ không?

**Trả lời:** Không. Quyền phụ thuộc caller/nest/module/visibility. `privateLookupIn` cũng phải tuân theo điều kiện quyền và JPMS opens.

**4.** Framework muốn liệt kê mọi method mang `@Action`: nên dùng API nào?

**Trả lời:** Reflection để khám phá annotation; có thể tạo MethodHandle sau đó nếu cần thực thi nhiều lần.

**5.** Khi nào `VarHandle` phù hợp?

**Trả lời:** Khi cần truy cập field/array với access mode và memory semantics cụ thể, nhất là atomic/volatile operations; không cần cho mọi property thông thường.

**6.** Handle nhận từ `bindTo(receiver)` có thể ảnh hưởng GC không?

**Trả lời:** Có thể. Handle giữ tham chiếu tới receiver đã bind, vì vậy cache handle lâu dài có thể kéo dài vòng đời receiver.

## 21. Checklist khi đưa MethodHandle vào hệ thống thực tế

- [ ] Có lý do kỹ thuật rõ để dùng dynamic invocation thay vì direct call/lambda?
- [ ] `MethodType` đầu vào chính xác: return type, primitive/reference, static/instance?
- [ ] Đã hiểu receiver là tham số đầu của virtual handle?
- [ ] Caller có `Lookup` quyền phù hợp, không cấp quyền quá rộng?
- [ ] JPMS `requires`, `exports`, `opens` được đặt ở module và package đúng?
- [ ] Mọi call-site `invokeExact` có kiểu tham số và return type đúng?
- [ ] Có kiểm tra lỗi lookup, adaptation và target exception riêng?
- [ ] Nếu đọc annotation, đã dùng Reflection API và retention hợp lệ?
- [ ] Handle được cache theo vòng đời hợp lý, không vô tình giữ object/class loader?
- [ ] Có giới hạn các operation được phép gọi qua untrusted input?
- [ ] Có benchmark workload thật trước khi tối ưu chỉ vì kỳ vọng MethodHandle nhanh hơn?
- [ ] Đã thử đường gọi trong modular JAR tương tự môi trường production?

**Ghi nhớ:** *`MethodType` nói handle nhận và trả kiểu gì; `Lookup` quyết định ta có quyền tạo handle nào; `MethodHandle` biểu diễn thao tác có thể gọi và có thể biến đổi*. Reflection dùng để khám phá, MethodHandle dùng để thực thi và tổ hợp có kiểm soát — hai API bổ sung cho nhau, không phải hai lựa chọn loại trừ tuyệt đối.

## Tài liệu tham khảo chính thức

- [Java SE 27 API — `MethodHandle`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandle.html): method type, `invokeExact`, `invoke`, `invokeWithArguments`, adaptation và exceptions.
- [Java SE 27 API — `MethodHandles`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.html): lookup factories và các combinator.
- [Java SE 27 API — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): lookup context, access modes, `findVirtual`, `findStatic`, `findConstructor`, `privateLookupIn` và `unreflect`.
- [Java SE 27 API — `MethodType`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodType.html): các kiểu JVM method signatures.
- [Java SE 27 API — `VarHandle`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/VarHandle.html): field/array access modes và memory ordering.
- [Java SE 27 API — `AccessibleObject`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AccessibleObject.html): reflection access checks và JPMS.
- [Java SE 27 API — `LambdaMetafactory`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html): động tạo functional interface theo hợp đồng API.
- [JLS 27 §15.12.3 — Compile-Time Step 3: Is the Chosen Method Appropriate?](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html#jls-15.12.3): các quy tắc lời gọi và signature-polymorphic methods.
- [JLS 27 §7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se27/html/jls-7.html#jls-7.7): readability, exports và opens.
- [OpenJDK JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi triển khai reflection trên JDK hiện đại.
