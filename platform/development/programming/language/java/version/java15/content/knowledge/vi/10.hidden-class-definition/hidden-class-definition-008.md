# Tạo đối tượng qua constructor method handle của hidden class (Java 15+)

> **Chủ đề cha: Định nghĩa lớp ẩn (Hidden class).** Java 15 giới thiệu API `MethodHandles.Lookup.defineHiddenClass()` để định nghĩa một lớp chỉ tồn tại như một runtime class, không thể tra cứu qua binary name thông thường. Sau khi có `Class<?>` của lớp này, bạn vẫn có thể **gọi constructor và tạo instance** bằng `MethodHandles.Lookup.findConstructor()` và `MethodHandle`. Bài này sử dụng API đang được hỗ trợ trong Java hiện đại, với ví dụ chạy trên Java 17+.

## Mục tiêu

Sau khi học xong, bạn có thể:

1. Giải thích tại sao hidden class vẫn tạo được đối tượng dù không gọi được `new HiddenClass(...)` từ mã Java thông thường.
2. Tạo hidden class từ class-file bytes và lấy `Lookup` có khả năng truy cập constructor.
3. Phân biệt **chữ ký constructor để tìm kiếm** và **kiểu thực tế của constructor method handle**.
4. Dùng `findConstructor()` để truy cập cả constructor không tham số và constructor có tham số, kể cả `private` khi `Lookup` đủ quyền.
5. Gọi constructor bằng `invokeWithArguments()`, `invoke()` hoặc `invokeExact()` sau khi xử lý đúng kiểu trả về.
6. Nhận biết `NoSuchMethodException`, `IllegalAccessException`, `WrongMethodTypeException`, và các lỗi liên quan đến class-file bytes hoặc class initialization.
7. Thiết kế factory không phụ thuộc runtime name và không dựa vào ép kiểu sang lớp mẫu ban đầu.

## 1. Constructor của hidden class có gì đặc biệt?

Đối với lớp thông thường `Widget`, mã Java có thể viết `new Widget("x")` vì compiler có thể nhúng tham chiếu lớp và constructor vào bytecode. Với **hidden class**, lớp được tạo lúc runtime từ bytes; nó **không có binary name hợp lệ** để mã Java thông thường hoặc `Class.forName()` tìm lại theo tên.

Tuy nhiên, sau khi gọi:

~~~java
// Đoạn mã minh họa bên trong một phương thức, chưa phải chương trình độc lập.
MethodHandles.Lookup hiddenLookup =
    MethodHandles.lookup().defineHiddenClass(classBytes, false);

Class<?> hiddenType = hiddenLookup.lookupClass();
~~~

`hiddenType` là một đối tượng `Class<?>` thật, phản ánh hidden class đã định nghĩa. Nó có thể chứa constructor, field, method và tạo instance như nhiều class runtime khác. Khác biệt là chúng ta **truy cập qua capability** (`Lookup`/`MethodHandle`), thay vì gọi một binary name không tồn tại.

**Bản chất của constructor method handle:** Một `MethodHandle` do `findConstructor()` tạo ra biểu diễn thao tác **cấp phát đối tượng + gọi constructor**. Khi gọi handle, nó trả về tham chiếu đến instance mới. Bạn **không cần** tự cấp phát instance trước rồi “gọi lại” constructor.

### 1.1. Sơ đồ thao tác

~~~text
.class bytes thuộc cùng package với lookup class
                     |
                     v
MethodHandles.lookup()
  .defineHiddenClass(bytes, initialize)
                     |
                     v
Lookup trên hidden class ----- lookupClass() ----> Class<?> hiddenType
          |
          | findConstructor(hiddenType, MethodType(void.class, ...))
          v
MethodHandle constructor factory
  type() = (... tham số ...) -> hiddenType
          |
          | invokeWithArguments / invoke / asType + invokeExact
          v
Object instance ----> hiddenType.isInstance(instance) == true
          |
          | method handle tới instance method, reflection phù hợp, ...
          v
Kết quả hoạt động của đối tượng
~~~

## 2. Các API tham gia

| Thành phần | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `MethodHandles.lookup()` | Tạo `Lookup` với quyền của **lớp đang gọi** | Là capability có quyền; không phát tán bừa bãi |
| `Lookup.defineHiddenClass(bytes, initialize, options...)` | Định nghĩa hidden class từ class-file bytes | Cần full privilege lookup và bytes đúng runtime package |
| `hiddenLookup.lookupClass()` | Lấy đối tượng `Class<?>` của hidden class mới | Không cần binary name |
| `hiddenType.isHidden()` | Kiểm tra đây là hidden class | Dùng API thay vì phân tích suffix tên |
| `hiddenLookup.findConstructor(hiddenType, ctorSignature)` | Tạo method handle để tạo instance | `ctorSignature` có **return type = void.class** |
| `MethodHandle.type()` | Cho biết chữ ký **của handle đã tìm được** | Return type lúc này là **hiddenType**, không phải `void` |
| `handle.invokeWithArguments(args...)` | Gọi linh hoạt từ danh sách đối số | Trả về `Object`, có bước thích ứng kiểu |
| `handle.invoke(args...)` | Gọi theo kiểu call-site, cho phép một số chuyển đổi `asType` | Khác `invokeExact` |
| `handle.invokeExact(args...)` | Gọi với **kiểu call-site khớp chính xác** `handle.type()` | Hidden return type cần adapter nếu không thể gọi trực tiếp từ Java source |
| `handle.asType(methodType(...))` | Tạo adapter có chữ ký mong muốn | Cho phép chuyển hidden return type sang `Object` |

### 2.1. Tại sao tìm constructor phải dùng `void.class`?

Giả sử hidden class có constructor khai báo trong class file tương đương:

~~~java
private Blueprint(String word, int count) { ... }
~~~

Bạn tìm nó bằng chữ ký của **constructor JVM**:

~~~java
MethodType.methodType(void.class, String.class, int.class)
~~~

Constructor trong bytecode có tên đặc biệt `<init>` và descriptor có **kiểu trả về `V` (void)**. Vì thế `Lookup.findConstructor(refc, type)` đòi hỏi `type.returnType() == void.class`.

Nhưng **handle trả về** từ `findConstructor` có kiểu:

~~~text
(String, int) -> hiddenType
~~~

vì nó đại diện cho **factory tạo đối tượng**. Đây không phải mâu thuẫn:

- **Kiểu dùng để tìm:** `(String, int)void`.
- **Kiểu của method handle nhận được:** `(String, int)HiddenClass`.

Nếu truyền `MethodType.methodType(hiddenType, String.class, int.class)` làm tham số tìm constructor, bạn đã nhầm giữa hai khái niệm trên.

### 2.2. Không có tham số và có tham số

Ví dụ một class file có hai constructor:

~~~java
private Blueprint() {
    this("ready", 1);
}

private Blueprint(String word, int count) {
    // Khởi tạo state
}
~~~

Bạn tìm lần lượt:

~~~java
// Các biến hiddenLookup và hiddenType đã tồn tại.
// Đây chỉ là đoạn mã minh họa, không phải tệp Java độc lập.
MethodHandle noArgs = hiddenLookup.findConstructor(
    hiddenType,
    MethodType.methodType(void.class)
);

MethodHandle withArgs = hiddenLookup.findConstructor(
    hiddenType,
    MethodType.methodType(void.class, String.class, int.class)
);
~~~

Việc overload constructor được phân biệt bằng danh sách parameter types **chính xác**. Không tìm constructor chỉ từ số lượng tham số hay từ tên `<init>` bằng cách nối chuỗi.

## 3. Ví dụ đầy đủ: tạo instance bằng constructor method handle

Ví dụ không dùng thư viện ngoài. Để có `.class bytes` thật mà không cần một bytecode generator riêng, chương trình biên dịch một nested class `Blueprint` bình thường rồi đọc chính file `HiddenConstructorDemo$Blueprint.class` của nó làm **mẫu**. Việc gọi `defineHiddenClass()` tạo ra một **lớp mới, khác với `Blueprint.class`**, dù dùng cùng nội dung class-file ban đầu.

Cả hai đều thuộc package `demo.hidden` để đáp ứng ràng buộc **same runtime package** của `defineHiddenClass()`.

### 3.1. Chuẩn bị file

Tạo:

~~~text
src/demo/hidden/HiddenConstructorDemo.java
~~~

**Mã nguồn hoàn chỉnh — Java 17+:**

~~~java
package demo.hidden;

import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenConstructorDemo {
    static class Blueprint {
        private final String word;
        private final int count;

        private Blueprint() {
            this("ready", 1);
        }

        private Blueprint(String word, int count) {
            this.word = word;
            this.count = count;
        }

        private String render() {
            return word.repeat(count);
        }
    }

    public static void main(String[] args) throws Throwable {
        // Lấy class-file bytes đã được javac biên dịch.
        byte[] bytes;
        try (InputStream stream = Blueprint.class.getResourceAsStream(
                "HiddenConstructorDemo$Blueprint.class")) {
            if (stream == null) {
                throw new IllegalStateException("Missing Blueprint.class");
            }
            bytes = stream.readAllBytes();
        }

        // Lớp mới được định nghĩa khi chạy, không có binary name.
        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(bytes, false);
        Class<?> hiddenType = hiddenLookup.lookupClass();

        // Constructor signature trong lookup trả về void.class.
        MethodHandle noArgs = hiddenLookup.findConstructor(
                hiddenType, MethodType.methodType(void.class));
        MethodHandle withArgs = hiddenLookup.findConstructor(
                hiddenType, MethodType.methodType(
                        void.class, String.class, int.class));

        // Method handle của instance method có thêm receiver.
        MethodHandle render = hiddenLookup.findVirtual(
                hiddenType, "render", MethodType.methodType(String.class));

        System.out.println("hidden=" + hiddenType.isHidden());
        System.out.println("noArgsReturnIsHidden=" +
                (noArgs.type().returnType() == hiddenType));
        System.out.println("withArgsParameters=" +
                withArgs.type().parameterCount());
        System.out.println("constructorTypeIsHidden=" +
                (withArgs.type().returnType() == hiddenType));

        // Cách gọi dễ dùng khi return type chỉ biết ở runtime.
        Object first = noArgs.invokeWithArguments();
        Object second = withArgs.invokeWithArguments("Go", 3);

        System.out.println("first=" + (String) render.invoke(first));
        System.out.println("second=" + (String) render.invoke(second));
        System.out.println("isInstance=" + hiddenType.isInstance(second));

        // Adapter có return type Object, phù hợp call site Java.
        MethodHandle genericFactory = withArgs.asType(
                MethodType.methodType(
                        Object.class, String.class, int.class));
        Object third = (Object) genericFactory.invokeExact("Hi", 2);
        System.out.println("exact=" + (String) render.invoke(third));

        // Không thể tìm lại hidden class bằng runtime name.
        try {
            Class.forName(hiddenType.getName());
            System.out.println("classForName=found");
        } catch (ClassNotFoundException expected) {
            System.out.println("classForName=not-found");
        }
    }
}
~~~

### 3.2. Biên dịch và chạy

Chạy từ thư mục chứa `src`:

~~~bash
javac -encoding UTF-8 -d out src/demo/hidden/HiddenConstructorDemo.java
java -cp out demo.hidden.HiddenConstructorDemo
~~~

`javac` sinh **hai file class**:

~~~text
out/demo/hidden/HiddenConstructorDemo.class
out/demo/hidden/HiddenConstructorDemo$Blueprint.class
~~~

File thứ hai phải có trên classpath, vì `getResourceAsStream()` sử dụng nó làm nguồn bytes. Không tự tạo file `.class` bằng cách lưu Java source thành tên có đuôi `.class`.

**Kết quả stdout xác định** (đã kiểm chứng khi chạy với JDK 24):

~~~text
hidden=true
noArgsReturnIsHidden=true
withArgsParameters=2
constructorTypeIsHidden=true
first=ready
second=GoGoGo
isInstance=true
exact=HiHi
classForName=not-found
~~~

### 3.3. Phân tích ví dụ

**Bước 1 — Lấy bytes.** `Blueprint.class.getResourceAsStream(...)` đọc class-file bytes đã qua compiler, không phải một file văn bản. `readAllBytes()` dùng với stream nhỏ trong ví dụ là phù hợp; ở ứng dụng thực cần xác thực nguồn bytes và có giới hạn kích thước.

**Bước 2 — Định nghĩa lớp ẩn.** `MethodHandles.lookup()` gọi trong `HiddenConstructorDemo` có full privilege access của lớp đó. `defineHiddenClass(bytes, false)` định nghĩa hidden class và trả về `Lookup` mới mà `lookupClass()` là hidden class vừa tạo. `false` nghĩa là **không yêu cầu khởi tạo class ngay trong lúc define**; việc khởi tạo có thể xảy ra lúc sử dụng cần initialization (chẳng hạn tạo instance qua constructor).

**Bước 3 — Tìm private constructors.** `hiddenLookup.findConstructor(...)` thành công ngay cả khi `Blueprint` khai báo các constructor là `private`, vì `hiddenLookup` có quyền trên hidden class đã định nghĩa. Không cần `setAccessible(true)`, không cần đoán tên do VM tạo, không cần gọi `Class.forName()`.

**Bước 4 — Đọc chữ ký handle.** `noArgs.type().returnType() == hiddenType` và `withArgs.type().returnType() == hiddenType`. Mỗi constructor handle là factory tạo đối tượng; trong kiểu handle không có tham số receiver. Với `withArgs`, `parameterCount() == 2`.

**Bước 5 — Tạo instance.** `invokeWithArguments()` trả về `Object` cho phép chương trình tiếp tục xử lý khi không thể viết tên hidden class trong source. Kết quả `first=ready` và `second=GoGoGo` chứng minh constructor tương ứng đã chạy và tạo state độc lập.

**Bước 6 — Gọi instance method.** `findVirtual(hiddenType, "render", methodType(String.class))` lấy handle của phương thức `render()`. Handle của instance method chứa receiver là tham số đầu, nên `render.invoke(first)` cần instance hợp lệ. Phương thức ở đây là `private`; lookup trên hidden class có quyền truy cập.

**Bước 7 — Gọi `invokeExact()`.** Vì kiểu thật của `withArgs` trả về hidden class không thể nêu tên trong mã Java, `withArgs.asType(methodType(Object.class, String.class, int.class))` tạo adapter trả về `Object`. Lúc đó `(Object) genericFactory.invokeExact("Hi", 2)` khớp chính xác chữ ký `(String, int)Object`.

**Bước 8 — Không tìm theo tên.** `Class.forName(hiddenType.getName())` không tìm được hidden class; nó không nằm trong cơ chế tra cứu class theo binary name bình thường. Bạn phải giữ `Class<?>`, `Lookup` hoặc constructor `MethodHandle` đã nhận được.

**Vì sao không ép kiểu sang `Blueprint`?** Hidden class mới khác `Blueprint.class` dù được định nghĩa từ bytes của nó. Đừng giả định có thể viết `Blueprint x = (Blueprint) instance`; trong ví dụ, dùng `Object`, `hiddenType.isInstance()` và handle tới method là đúng ý nghĩa runtime.

## 4. Chọn cách gọi handle: `invokeWithArguments`, `invoke`, `invokeExact`

Constructor handle sau khi lookup có một `MethodType` cụ thể. Chọn cách gọi theo mức độ biết trước kiểu ở call site.

### 4.1. `invokeWithArguments(...)`

~~~java
// Đoạn mã minh họa, các biến đã khai báo trong ví dụ đầy đủ.
Object obj = withArgs.invokeWithArguments("Go", 3);
~~~

- Nhận danh sách giá trị động và trả về `Object`.
- Thực hiện thích ứng kiểu, có thể boxing/unboxing hoặc kiểm tra cast nếu cần.
- Thuận tiện khi lớp/parameter types chỉ biết lúc runtime.
- Nếu số tham số hoặc kiểu không thể chuyển đổi, có thể gặp `WrongMethodTypeException`, `ClassCastException` hoặc lỗi tương ứng.
- Không nên mặc định nó có cùng chi phí và đặc tính kiểm tra kiểu như `invokeExact` khi được gọi trong vòng lặp hiệu năng cao; hãy benchmark nếu đây là đường nóng.

### 4.2. `invoke(...)`

~~~java
// Đoạn mã minh họa, không phải một class độc lập.
Object obj = (Object) withArgs.invoke("Go", 3);
~~~

- Call site có thể có kiểu mong muốn khác một chút so với `handle.type()`.
- JVM có thể áp dụng chuyển đổi tương tự `asType()` khi hợp lệ.
- Ở ví dụ, có thể thích ứng kiểu trả về từ hidden class sang `Object`.

Không có nghĩa `invoke()` luôn ép kiểu tùy ý. Chuyển đổi không hợp lệ vẫn thất bại.

### 4.3. `invokeExact(...)`

~~~java
// Đoạn minh họa đã có adapter genericFactory.
Object obj = (Object) genericFactory.invokeExact("Go", 3);
~~~

- Kiểu tham số **và kiểu trả về tại call site** phải khớp **chính xác** `MethodHandle.type()`.
- Constructor handle gốc trả về hidden type, không phải `Object`; cast kết quả thành `Object` ở call site **không đủ** để biến nó thành exact call hợp lệ.
- Cần adapter `asType(MethodType.methodType(Object.class, ...))` trước khi gọi `invokeExact()` nếu muốn chữ ký chứa `Object` ở vị trí return type.
- Truyền `Integer` thay vì `int` ở một exact call site vốn cần `int` có thể gây `WrongMethodTypeException`, dù `invoke()` hoặc `invokeWithArguments()` có thể thực hiện unboxing hợp lệ.

**Cách nhớ:** `invokeWithArguments` cho dữ liệu động; `invoke` có thích ứng kiểu theo quy tắc; `invokeExact` yêu cầu khớp loại chính xác.

### 4.4. Không nhầm kiểu của constructor với kiểu của instance method

| Handle | Phần tham số của `MethodHandle.type()` | Return type |
| --- | --- | --- |
| `findConstructor(hiddenType, methodType(void.class))` | Không có tham số | `hiddenType` |
| `findConstructor(hiddenType, methodType(void.class, String.class, int.class))` | `String, int` | `hiddenType` |
| `findVirtual(hiddenType, "render", methodType(String.class))` | `hiddenType` (receiver) | `String` |

Constructor không có receiver vì nó **tạo mới** đối tượng. `findVirtual` có receiver vì nó **gọi method trên instance đã có**.

## 5. Ví dụ lỗi có chủ đích: method type sai và constructor không tồn tại

Một `Lookup` đủ quyền vẫn không thể tìm constructor có chữ ký không tồn tại. Một method handle hợp lệ cũng không thể được gọi bằng `invokeExact()` với kiểu call site sai.

**Tệp `src/demo/hidden/HiddenConstructorErrors.java`, độc lập, Java 17+:**

~~~java
package demo.hidden;

import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class HiddenConstructorErrors {
    static class Ticket {
        private final int number;

        private Ticket(int number) {
            this.number = number;
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes;
        try (InputStream in = Ticket.class.getResourceAsStream(
                "HiddenConstructorErrors$Ticket.class")) {
            if (in == null) {
                throw new IllegalStateException("Missing Ticket.class");
            }
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup targetLookup =
                MethodHandles.lookup().defineHiddenClass(bytes, false);
        Class<?> target = targetLookup.lookupClass();

        MethodHandle ctor = targetLookup.findConstructor(
                target, MethodType.methodType(void.class, int.class));
        System.out.println("constructorReturnMatches=" +
                (ctor.type().returnType() == target));

        MethodHandle general = ctor.asType(
                MethodType.methodType(Object.class, int.class));

        Object valid = (Object) general.invokeExact(7);
        System.out.println("created=" + target.isInstance(valid));

        try {
            // Call site cần Integer, handle lại cần int nguyên thủy.
            Object invalid = (Object) general.invokeExact(
                    Integer.valueOf(7));
            System.out.println("wrongExact=accepted");
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrongExact=rejected");
        }

        try {
            // Ticket chỉ có constructor nhận một int.
            targetLookup.findConstructor(
                    target, MethodType.methodType(void.class));
            System.out.println("missingConstructor=found");
        } catch (NoSuchMethodException expected) {
            System.out.println("missingConstructor=not-found");
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa `src`:

~~~bash
javac -encoding UTF-8 -d out src/demo/hidden/HiddenConstructorErrors.java
java -cp out demo.hidden.HiddenConstructorErrors
~~~

**Stdout chính xác** (đã kiểm chứng trên JDK 24):

~~~text
constructorReturnMatches=true
created=true
wrongExact=rejected
missingConstructor=not-found
~~~

Giải thích hai lỗi:

- `general.type()` là `(int)Object`. Gọi `invokeExact(Integer.valueOf(7))` tạo call-site parameter type **`Integer`**, không phải `int`, nên bị `WrongMethodTypeException`. Java compiler chấp nhận cú pháp `invokeExact` đặc biệt, nhưng việc so chữ ký chính xác xảy ra lúc liên kết/gọi handle.
- `findConstructor(target, methodType(void.class))` yêu cầu constructor không tham số. `Ticket` chỉ có `Ticket(int)`, nên trả về lỗi `NoSuchMethodException`.

Khi ứng dụng bắt những lỗi này, hãy xử lý ở ranh giới **kiểm tra cấu hình/bytes/chữ ký**, không coi chúng là dấu hiệu rằng phải thử bừa nhiều chữ ký khác nhau.

## 6. Quy tắc về quyền truy cập và bytecode

### 6.1. `Lookup` quyết định quyền, không phải tên lớp

`MethodHandles.Lookup` là một **capability object**: quyền của nó được xác định theo lookup class và lookup modes. Phương thức `findConstructor()` kiểm tra quyền khi tạo handle. Handle đã tạo thường không lặp lại kiểm tra quyền đó mỗi lần `invoke()`.

- `MethodHandles.lookup()` trả lookup với quyền của **lớp gọi**; nó không phải một “superuser lookup” có thể truy cập mọi class.
- `defineHiddenClass()` yêu cầu **full privilege access**, và class-file bytes phải mô tả một lớp thuộc **cùng package** với lookup class.
- `defineHiddenClass()` trả lookup trên hidden class, cho phép tìm các member/constructor của chính lớp mới đó theo quyền được cung cấp.
- `publicLookup()` không thay thế được full-privilege lookup trong việc **định nghĩa** hidden class.
- Không chia sẻ lookup có quyền truy cập private một cách tùy tiện với mã không tin cậy.

Nếu lớp mẫu của bạn là nested class, nó có thể mang các thuộc tính `NestHost`, `InnerClasses`. Khi viết một framework tạo bytecode, phải đảm bảo bytes và quan hệ nest/quan hệ lớp phù hợp; không suy luận rằng chỉ cần gắn suffix vào tên lớp là đã tạo được hidden class hợp lệ.

### 6.2. `NESTMATE` và `STRONG` không phải yêu cầu để gọi constructor

`defineHiddenClass(bytes, initialize, options...)` có các tùy chọn đang được hỗ trợ:

- `ClassOption.NESTMATE` làm hidden class trở thành nestmate của lookup class, hữu ích khi bytecode của hidden class cần quyền truy cập private tới các thành viên của nest host theo đúng quy tắc truy cập.
- `ClassOption.STRONG` thay đổi quan hệ vòng đời/khả năng unloading: lớp được liên kết mạnh với defining loader theo hợp đồng API.
- Trong **ví dụ ở mục 3**, không cần `NESTMATE` chỉ để constructor handle do lookup của **chính hidden class** tạo ra truy cập private constructor của nó.

Đừng thêm option chỉ để “chữa” lỗi `WrongMethodTypeException`: lỗi đó thuộc **kiểu của method handle/call site**, không phải quan hệ nest.

### 6.3. `initialize` là cờ điều khiển thời điểm khởi tạo class

- `defineHiddenClass(bytes, true)` yêu cầu hidden class được **khởi tạo** khi định nghĩa.
- `defineHiddenClass(bytes, false)` không yêu cầu khởi tạo tại thời điểm đó; class có thể được khởi tạo sau khi có một thao tác cần initialization.
- Gọi constructor thông qua method handle là một thao tác cần class được khởi tạo nếu chưa khởi tạo.

Đừng hiểu `false` là “không bao giờ chạy static initializer”, cũng đừng hiểu nó là “bỏ qua constructor”. Constructor thực tế vẫn chạy khi handle được gọi.

## 7. So sánh với cách tạo đối tượng khác

| Cách tạo | Phù hợp với | Giới hạn với hidden class |
| --- | --- | --- |
| `new SomeType(...)` | Lớp có tên tĩnh, biết khi biên dịch | Không thể viết literal binary name của hidden class runtime |
| `Class.forName(name)` | Lớp có binary name hợp lệ và có thể discover | **Không** thể tìm hidden class bằng runtime name |
| `clazz.getDeclaredConstructor(...).newInstance(...)` | Reflection khi đã giữ `Class<?>`; cần chính sách truy cập | Có thể dùng trong phạm vi quyền nhưng không tự tạo danh tính class qua tên; phải xử lý access |
| `hiddenLookup.findConstructor(...).invokeWithArguments(...)` | Factory động, đã có lookup/hiddenType | Thuận tiện, có thích ứng kiểu và trả `Object` |
| `hiddenLookup.findConstructor(...).asType(...).invokeExact(...)` | Factory được chuẩn bị kiểu call site rõ ràng | Cần adapter phù hợp, khớp chính xác kiểu |
| `MethodHandle.invoke(...)` | Truy cập constructor/method handle linh hoạt | Chỉ có những chuyển đổi `asType` hợp lệ, không phải ép kiểu tùy ý |

Reflection không phải “lỗi thời” và vẫn có những trường hợp dùng hợp lý; điểm chính của bài này là **cơ chế constructor method handle**, đặc biệt hữu ích trong các runtime hoặc framework tạo lớp động. `MethodHandle` không tự bảo đảm mọi đường gọi đều nhanh hơn reflection: chi phí khởi tạo handle, số lần gọi, khả năng JIT tối ưu và cách thích ứng kiểu có thể ảnh hưởng. Đo bằng benchmark đáng tin cậy nếu hiệu năng là yêu cầu.

## 8. Thiết kế factory thực tế

Khi một framework định nghĩa hidden class rồi tạo nhiều instance:

1. **Xác thực nguồn class-file bytes.** Không đưa bytecode không tin cậy trực tiếp vào tiến trình và giả định hidden class là sandbox. Hidden class vẫn thực thi bytecode Java thực sự, theo quyền của runtime.
2. **Giữ `Lookup` hoặc constructor `MethodHandle` cần thiết.** Không giữ mỗi `hiddenType.getName()` để tra cứu lại.
3. **Tìm constructor một lần** theo đúng `MethodType` rồi tái sử dụng handle để giảm thao tác lookup lặp lại.
4. **Chọn API gọi rõ ràng.** Dữ liệu động ít lần: `invokeWithArguments`. Call-site biết kiểu ổn định: thích ứng với `asType` và dùng `invokeExact` nếu phù hợp.
5. **Giữ kiểu trả về tường minh.** Khi không thể nêu tên hidden type trong source, sử dụng `Object`, interface/supertype mà hidden class thực sự implement/extend, hoặc wrapper do ứng dụng kiểm soát.
6. **Không ghép tên để quyết định identity.** Hai lần `defineHiddenClass()` từ cùng bytes là hai runtime classes khác nhau. Dùng `Class<?>` (identity) hoặc ID do ứng dụng quản lý.
7. **Quản lý vòng đời.** Nếu cache lâu dài chứa `Class<?>`/`MethodHandle`, bạn có thể duy trì khả năng truy cập class/instance lâu hơn. Thiết kế cache phù hợp thay vì suy luận hidden class sẽ tự mất ngay khi không còn tên.
8. **Kiểm tra lỗi tại đúng lớp.** Lỗi đọc file bytes, lỗi class format/linkage, lỗi quyền của lookup, lỗi chữ ký constructor và lỗi do constructor tự ném ra là các nhóm khác nhau.

### 8.1. Nếu đã có interface chung

Nếu bạn kiểm soát class file và hidden class **thực sự implement một interface** được định nghĩa bình thường, code có thể dùng interface đó để gọi phương thức mà không cần cast sang **tên hidden class**. Ví dụ mô hình:

~~~java
// Đoạn minh họa: giả sử hidden class implement giao diện Renderer.
Object instance = constructor.invokeWithArguments(args);
Renderer renderer = (Renderer) instance;
String result = renderer.render();
~~~

Đoạn trên **không độc lập**: `Renderer` phải là một interface được biên dịch, hidden class phải implement nó và `args` phải phù hợp constructor. Không được suy ra rằng hidden class tạo từ nested `Blueprint` ở ví dụ 3 tự nhiên implement một interface bất kỳ.

## 9. Lỗi thường gặp và cách nhận diện

| Lỗi | Vì sao xảy ra? | Cách khắc phục |
| --- | --- | --- |
| `Class.forName(hiddenType.getName())` không tìm thấy | Hidden class không có binary name có thể tra cứu | Giữ `Class<?>`/`Lookup`/`MethodHandle` |
| `NoSuchMethodException` khi `findConstructor` | Chữ ký constructor không tồn tại | Kiểm tra parameter types và `void.class` khi tìm |
| `IllegalAccessException` | Lookup không đủ quyền với member hoặc không đủ quyền định nghĩa hidden class | Sử dụng lookup thích hợp; không dùng bypass tùy ý |
| `WrongMethodTypeException` tại `invokeExact` | Kiểu call site không đúng `handle.type()`, kể cả kiểu return | Kiểm tra `type()`; tạo adapter `asType(...)` rõ ràng |
| `ClassCastException` khi gọi/invoke | Giá trị không thể chuyển sang kiểu cần thiết | Kiểm tra instance và kiểu đối số |
| `ClassFormatError`/`VerifyError`/`LinkageError` khi định nghĩa | Bytes không phải class file hợp lệ, không đúng bytecode, hoặc không liên kết được | Tạo và xác thực bytes theo JVM class-file spec |
| `IllegalArgumentException` trong `defineHiddenClass` | Package của class file không phù hợp, hoặc input không được phép | Bảo đảm cùng runtime package và class-file hợp lệ |
| `IllegalStateException("Missing Blueprint.class")` | File resource `.class` không có trong output/classpath | Biên dịch cả nested class, giữ file `.class` được sinh |
| `ClassNotFoundException` khi lookup theo tên runtime | Không thể lookup hidden class bằng binary name | Đừng coi tên runtime là cache key phục hồi class |
| Dùng `invokeExact` trực tiếp với return type `Object` trên handle gốc | Handle trả hiddenType, không phải Object | `asType(methodType(Object.class, ...))` trước |
| Constructor chạy nhưng kết quả không phải `Blueprint` | Hidden class mới khác class mẫu gốc | Dùng `Object`, interface chung, hoặc `hiddenType.isInstance` |
| Tự động đổi `initialize=false` thành “không init” | Initialization vẫn xảy ra khi cần | Phân biệt lúc define và lúc new object |
| Xem hidden class là ranh giới bảo mật | Hidden chỉ hạn chế tìm lớp theo tên | Không thi hành bytecode không tin cậy như mã an toàn |

## 10. Bài tập tự kiểm tra

**Câu 1.** Vì sao khi tìm `Hidden(String, int)` phải truyền `methodType(void.class, String.class, int.class)`, nhưng `constructorHandle.type().returnType()` lại là hidden class?

**Đáp án:** `findConstructor` nhận kiểu constructor JVM `<init>` (trả `void`). Handle được tạo là factory cấp phát và gọi constructor, nên trả instance của class đó.

**Câu 2.** Bạn đã có `Class<?> hiddenType`, nhưng không có binary name hợp lệ. Làm cách nào tạo instance?

**Đáp án:** Dùng `Lookup` có quyền thích hợp, gọi `findConstructor(hiddenType, methodType(void.class, ...))`, rồi `invokeWithArguments(...)` hoặc thích ứng handle và gọi `invokeExact(...)`.

**Câu 3.** Vì sao `(Object) rawCtor.invokeExact("Hi", 2)` có thể lỗi dù chữ ký constructor nhận `String, int`?

**Đáp án:** Call site yêu cầu return type `Object`, trong khi `rawCtor.type()` trả hiddenType. `invokeExact` cần khớp cả return type. Dùng `rawCtor.asType(methodType(Object.class, String.class, int.class))` rồi gọi.

**Câu 4.** Đưa `Integer.valueOf(7)` vào một `invokeExact` đang cần `int` có tự unbox không?

**Đáp án:** Không. Kiểu call site là `Integer`, không khớp `int`. Nếu muốn tự động unboxing theo quy tắc `asType`, dùng API gọi/thích ứng có hỗ trợ chuyển đổi và kiểm tra điều kiện.

**Câu 5.** Hai lần `defineHiddenClass(bytes, false)` với cùng bytes có nhất thiết trả về cùng một class không?

**Đáp án:** Không. Chúng tạo các hidden classes riêng biệt. Mỗi lớp có `Class<?>` và runtime identity khác nhau, dù có cùng class-file template.

**Câu 6.** Nếu constructor là `private`, nhất thiết phải gọi `setAccessible(true)` mới tạo được đối tượng?

**Đáp án:** Không. `Lookup` có đủ quyền trên hidden class có thể `findConstructor()` tới private constructor và tạo handle trực tiếp.

**Câu 7.** Bạn đã tạo được handle, nhưng khi gọi constructor, static initializer có thể chạy không nếu `defineHiddenClass(bytes, false)`?

**Đáp án:** Có. Cờ `false` không yêu cầu initialization trong bước định nghĩa; class được khởi tạo sau đó khi có một thao tác cần khởi tạo, chẳng hạn tạo instance.

## Ghi nhớ

- `defineHiddenClass()` trả `Lookup` trên hidden class mới; gọi `lookupClass()` để lấy `Class<?>`.
- `findConstructor(hiddenType, MethodType.methodType(void.class, ...))` tìm constructor; **kiểu handle trả về instance**, không phải `void`.
- Hidden class không thể lookup bằng runtime name thông thường, nhưng **hoàn toàn có thể tạo đối tượng** qua constructor method handle.
- `invokeWithArguments()` thích hợp cho lời gọi động. `invokeExact()` cần **khớp tuyệt đối tham số và return type**; khi return type là hidden class không thể gọi tên trong source, tạo adapter trả về `Object`.
- Quyền truy cập do **`Lookup`** quyết định; không dùng tên class, suffix hoặc thủ thuật reflection để thay thế quyền.
- Hai hidden classes từ cùng bytes vẫn là hai runtime classes riêng biệt. Tái sử dụng handle khi hợp lý, đồng thời quản lý vòng đời và nguồn bytes có chủ đích.

## Tài liệu chính thức

- [Java SE 25 — MethodHandles.Lookup: defineHiddenClass và findConstructor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 25 — MethodHandle: type, invokeExact, invoke và invokeWithArguments](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 25 — MethodType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html)
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371)
- [Java Virtual Machine Specification — `<init>` và method descriptors](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html)
