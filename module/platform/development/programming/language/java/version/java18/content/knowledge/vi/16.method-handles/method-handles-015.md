# WrongMethodTypeException, ClassCastException và NullPointerException: phân biệt lỗi cấu trúc với lỗi giá trị

> **Phạm vi:** Bài thuộc chương **MethodHandle** của module `JAVA_VERSION_JAVA18`. Từ Java 18, JEP 416 tái triển khai core reflection dựa trên method handles, nhưng `java.lang.invoke.MethodHandle` đã là API công khai từ trước và tiếp tục hữu ích trên các JDK hiện đại. Bài này tập trung vào hợp đồng `MethodHandle.type()`, `invokeExact`, `invoke` và `asType` để phân biệt **lỗi cấu trúc chữ ký** (`WrongMethodTypeException`), **lỗi kiểu đối tượng tại runtime** (`ClassCastException`) và **lỗi giá trị null** (`NullPointerException`). Ví dụ chỉ dùng API Java được hỗ trợ chính thức, không dựa vào chi tiết JIT hay API nội bộ.

## 1. Vì sao ba ngoại lệ này dễ bị nhầm?

Khi gọi một phương thức qua `MethodHandle`, có ít nhất ba thông tin khác nhau:

1. **Kiểu của handle:** Một `MethodType` cố định, bao gồm kiểu trả về và danh sách kiểu tham số. Có thể đọc bằng `handle.type()`.
2. **Kiểu của call site:** Kiểu lời gọi do compiler/JVM xác định từ các biểu thức đối số và ngữ cảnh kiểu trả về tại chỗ gọi `invokeExact` hoặc `invoke`.
3. **Giá trị runtime:** Đối tượng hoặc primitive thực sự được truyền; với reference có thể là `null` hoặc instance của một lớp cụ thể.

Hai dòng code đều có thể đưa chuỗi `"Java"` đến một handle nhận `String`, nhưng hành vi khác nhau khi **kiểu tĩnh tại call site** khác nhau:

~~~java
String text = "Java";
Object sameText = text;

// Giả sử length có type (String)int:
int a = (int) length.invokeExact(text);      // Hợp lệ.
int b = (int) length.invokeExact(sameText);  // WrongMethodTypeException.
~~~

Trong dòng thứ hai, giá trị runtime vẫn là `String`. Lỗi xảy ra vì call site yêu cầu signature `(Object)int`, còn handle có signature `(String)int`. `invokeExact` không tự chuyển kiểu tham chiếu theo giá trị runtime.

Với `invoke`, JDK có thể thích nghi kiểu giữa call site và handle:

~~~java
int c = (int) length.invoke(sameText); // Hợp lệ: Object thực tế là String.
~~~

Nhưng sự thích nghi này **không có nghĩa** mọi giá trị có thể chuyển đổi:

~~~java
Object other = Integer.valueOf(10);
int d = (int) length.invoke(other); // ClassCastException khi cast sang String.
~~~

Sơ đồ chẩn đoán:

~~~text
               Gọi MethodHandle
                      |
                      v
         Chữ ký call site và handle
                có tương thích?
              /                 \
            Không                Có
             |                    |
             v                    v
 WrongMethodTypeException   Chuyển đổi đối số / receiver
                                  |
                        +---------+---------+
                        |                   |
                 Sai lớp thực tế      Giá trị null không dùng được
                        |                   |
                        v                   v
               ClassCastException    NullPointerException
                                            |
                                            v
                           (hoặc code đích tự dereference null)
~~~

Sơ đồ là mô hình chẩn đoán thông dụng, **không phải thứ tự bắt buộc** của mọi adapter. Ngoại lệ cụ thể phụ thuộc phương thức gọi, signature, chuỗi adapter và code đích.

## 2. Đọc đúng `MethodType` trước khi gọi

Một `MethodHandle` có kiểu mô tả bằng `MethodType`:

~~~java
MethodHandle length = MethodHandles.lookup().findVirtual(
        String.class,
        "length",
        MethodType.methodType(int.class)
);
System.out.println(length.type()); // (String)int
~~~

`findVirtual` nhận `MethodType` của phương thức đích **không liệt kê receiver** (ở đây `String.length()` không có tham số khai báo). Handle tìm được lại có receiver `String` như tham số đầu tiên, vì gọi instance method cần đối tượng đích. Do đó `length.type()` là `(String)int`.

Với static method, handle không có receiver bổ sung:

~~~java
MethodHandle parse = MethodHandles.lookup().findStatic(
        Integer.class,
        "parseInt",
        MethodType.methodType(int.class, String.class)
);
System.out.println(parse.type()); // (String)int
~~~

Dù hai handle cùng có type `(String)int`, `length` gọi `String.length()` còn `parse` gọi `Integer.parseInt(String)`. Type chỉ mô tả hình dạng lời gọi; nó không chứng minh **ý nghĩa** của phương thức.

| Phép kiểm tra | API | Câu hỏi được trả lời |
|---|---|---|
| Kiểu đầy đủ | `handle.type()` | Handle cần các tham số nào và trả kiểu gì? |
| Số tham số | `handle.type().parameterCount()` | Call site phải cung cấp bao nhiêu đối số? |
| Kiểu tham số vị trí `i` | `handle.type().parameterType(i)` | Vị trí `i` là `String`, `int` hay kiểu nào? |
| Kiểu trả về | `handle.type().returnType()` | Call site cần nhận kết quả kiểu gì? |
| Dựng signature kỳ vọng | `MethodType.methodType(...)` | Handle có đúng hợp đồng cấu trúc mong muốn? |

Ví dụ kiểm tra kiểu trước khi chọn chiến lược gọi:

~~~java
MethodType expected = MethodType.methodType(
        int.class, String.class
);
if (!length.type().equals(expected)) {
    throw new IllegalArgumentException(
            "Unexpected handle type: " + length.type());
}
~~~

Lỗi cấu trúc có thể được phát hiện sớm khi tạo hoặc thích nghi handle; không nhất thiết phải chờ đến `invokeExact` mới có lỗi.

## 3. `WrongMethodTypeException`: cấu trúc lời gọi không phù hợp

`java.lang.invoke.WrongMethodTypeException` là lỗi về **method type / chữ ký**. Nó không có nghĩa rằng một đối tượng được truyền có nội dung sai hay thuộc lớp sai ở thời điểm chạy.

### 3.1. `invokeExact` yêu cầu khớp chính xác cả tham số và kiểu trả về

`MethodHandle.invokeExact` là phương thức *signature polymorphic*. Compiler hình thành **call-site descriptor** từ kiểu tĩnh của từng đối số và ngữ cảnh nhận kết quả; JVM yêu cầu descriptor này khớp chính xác với `handle.type()`.

Ví dụ với handle `(String)int`:

~~~java
String message = "Java";
int ok = (int) length.invokeExact(message); // Đúng: (String)int.

Object messageAsObject = message;
int wrongArgument =
        (int) length.invokeExact(messageAsObject);
        // WrongMethodTypeException: call site (Object)int.
~~~

Đổi kiểu **tĩnh** của biến thành `Object` đã đủ làm sai chữ ký, dù giá trị vẫn là `String`. Khi biết chắc kiểu và đã kiểm tra thích hợp, có thể biểu diễn đúng call site:

~~~java
int fixed = (int) length.invokeExact((String) messageAsObject);
~~~

Phép cast `(String) messageAsObject` là **Java cast tại call site**, thực hiện trước khi gọi `invokeExact`. Nếu object thực tế là `Integer`, chính phép cast này có thể ném `ClassCastException`; đây không phải vì `invokeExact` tự chuyển đổi giá trị.

**Kiểu trả về cũng là một phần của chữ ký.** Hai lời gọi sau không tương đương:

~~~java
int n = (int) length.invokeExact("Java");    // Đúng: trả int.
long m = (long) length.invokeExact("Java");  // WrongMethodTypeException.
~~~

Ở dòng thứ hai, kiểu trả về được yêu cầu tại call site là `long`. `invokeExact` không tự mở rộng kiểu trả về từ `int` sang `long`. Nếu cần, hãy nhận đúng kiểu `int` rồi chuyển đổi bằng Java:

~~~java
int raw = (int) length.invokeExact("Java");
long widened = raw; // Java thực hiện int -> long sau lời gọi.
~~~

Tương tự, dùng `length.invokeExact("Java");` như một statement bỏ kết quả có thể tạo call site có kiểu trả về `void`, không khớp với `int` của handle, và gây `WrongMethodTypeException`.

### 3.2. `invoke` có thích nghi kiểu nhưng không phải chuyển đổi tùy ý

`MethodHandle.invoke` cũng là phương thức signature polymorphic, song cho phép các phép biến đổi tương đương với khả năng thích nghi của `asType` giữa call site và handle.

~~~java
Object candidate = "Java";
int n = (int) length.invoke(candidate);  // Object -> String: hợp lệ.
~~~

Vì chuyển đổi reference từ `Object` sang `String` có thể thực hiện bằng runtime cast, JVM có thể tạo adapter cho call site `(Object)int`. Nếu object thực tế là `String`, lời gọi thành công; nếu là `Integer`, adapter có thể ném `ClassCastException`.

Ngược lại, nếu chuyển đổi giữa hai **kiểu của chữ ký** không thể được thiết lập theo quy tắc `asType`, `invoke` cũng có thể ném `WrongMethodTypeException`, ngay cả trước khi xét giá trị.

Ví dụ cụ thể về kiểu không thích nghi được:

~~~java
MethodHandle identityInt = MethodHandles.identity(int.class);
// type: (int)int.

try {
    MethodHandle bad = identityInt.asType(
            MethodType.methodType(boolean.class, int.class));
    throw new AssertionError("Expected WrongMethodTypeException");
} catch (WrongMethodTypeException expected) {
    System.out.println("Cannot adapt int return to boolean");
}
~~~

Để biến `(int)int` thành `(int)boolean`, adapter phải chuyển kết quả primitive `int` thành `boolean`; `asType` không hỗ trợ chuyển đổi đó. Việc tạo adapter thất bại về cấu trúc.

### 3.3. Khi nào nên sửa `WrongMethodTypeException`?

- In `handle.type()` và đối chiếu kiểu tĩnh các đối số ở nơi gọi.
- Kiểm tra **kiểu trả về được yêu cầu**, kể cả trường hợp gọi như statement.
- Với `invokeExact`, viết rõ cast kết quả và bảo đảm từng kiểu tham số khớp.
- Nếu cố ý cần chuyển đổi được Java MethodHandle API hỗ trợ, dùng `invoke` hoặc dựng adapter rõ ràng bằng `asType`.
- Không “sửa” bằng cách bắt exception rồi ép kiểu object ở ngoài khi bản thân call site vẫn có chữ ký sai.
- Nếu signature bắt đầu từ `findVirtual` hoặc `findStatic`, cần phân biệt receiver có xuất hiện trong `MethodHandle.type()` hay không.

## 4. `ClassCastException`: adapter chuyển reference nhưng giá trị không đúng lớp

`ClassCastException` thường cho thấy một phép **reference cast** được phép ở cấp cấu trúc nhưng thất bại khi gặp object cụ thể.

Ví dụ:

~~~java
MethodHandle length = MethodHandles.lookup().findVirtual(
        String.class, "length",
        MethodType.methodType(int.class)
);

Object value = Integer.valueOf(2026);
int n = (int) length.invoke(value); // ClassCastException.
~~~

Call site của `invoke` dùng `Object` trong khi handle cần `String`. Chuyển đổi reference `Object → String` là phép cast có thể thử, nên không nhất thiết là `WrongMethodTypeException`. Khi kiểm tra object runtime, `Integer` không phải `String` và phép cast thất bại.

### 4.1. Tạo adapter bằng `asType` và kiểm chứng khác biệt

~~~java
MethodHandle adapted = length.asType(
        MethodType.methodType(int.class, Object.class)
);
System.out.println(adapted.type()); // (Object)int.

int ok = (int) adapted.invokeExact((Object) "Java"); // 4.

Object wrongValue = Integer.valueOf(7);
int wrong = (int) adapted.invokeExact(wrongValue);
// ClassCastException khi adapter cast Object -> String.
~~~

Ở đây **`invokeExact` vẫn được sử dụng đúng chữ ký `(Object)int`** của adapter. Lỗi `ClassCastException` nằm trong **adapter**, do giá trị thực tế không phải `String`. Điều này cho thấy tên `invokeExact` không hứa rằng mọi ngoại lệ sau khi call-site descriptor khớp đều là lỗi của code đích.

### 4.2. Nguồn gốc `ClassCastException` không chỉ đến từ adapter

Phương thức đích hoặc các bộ biến đổi do ứng dụng tạo cũng có thể tự ném `ClassCastException`, ví dụ:

~~~java
static int parsePayload(Object payload) {
    String text = (String) payload; // Có thể ném ClassCastException.
    return text.length();
}
~~~

Khi gọi qua `MethodHandle`, ngoại lệ từ code đích thường đi ra trực tiếp theo quy tắc của API MethodHandle; không bị bọc tự động thành `InvocationTargetException` như đường gọi `java.lang.reflect.Method.invoke`.

Vì thế, chỉ nhìn thấy tên `ClassCastException` chưa đủ biết **adapter** hay **body của phương thức đích** là nơi thực hiện phép cast. Kiểm tra stack trace, lớp nhận vào và các adapter đang sử dụng.

## 5. `NullPointerException`: giá trị null không đáp ứng yêu cầu thực thi

`NullPointerException` có thể xuất hiện ngay cả khi **chữ ký call site hoàn toàn khớp**. Hai nguồn thường gặp là:

1. Cố gắng **unbox `null`** thành một primitive.
2. Gọi instance method trên receiver `null`, hoặc code đích dereference một reference null.

### 5.1. Unboxing null khi `invoke` thích nghi `Object → int`

~~~java
MethodHandle identityInt = MethodHandles.identity(int.class);
// type: (int)int.

Object absent = null;
int result = (int) identityInt.invoke(absent);
// NullPointerException khi adapter cần unbox null thành int.
~~~

Call site có type `(Object)int`. `invoke` có thể thích nghi nó đến `(int)int` thông qua unboxing từ một wrapper tương thích. Với `Integer.valueOf(7)`, chuyển đổi hợp lệ:

~~~java
int ok = (int) identityInt.invoke((Object) Integer.valueOf(7));
// ok == 7.
~~~

Với `null`, không tồn tại giá trị primitive tương ứng. `NullPointerException` là **lỗi giá trị runtime**, không phải sai cấu trúc không thể thích nghi.

### 5.2. Receiver null với instance method

~~~java
MethodHandle length = MethodHandles.lookup().findVirtual(
        String.class, "length",
        MethodType.methodType(int.class)
);

String missing = null;
int result = (int) length.invokeExact(missing);
// NullPointerException: receiver của String.length() là null.
~~~

Call site `(String)int` trùng chính xác với `length.type()`. Tuy nhiên, muốn gọi `length()` phải có instance `String` hợp lệ. Một reference `null` có kiểu tĩnh `String` vẫn không thể làm receiver cho instance method.

### 5.3. Phân biệt null cho reference và null cho primitive

Nếu handle nhận tham số reference như `String`, một đối số `null` có thể **phù hợp về kiểu**. Phương thức đích có thể xử lý null hoặc ném `NullPointerException` theo logic:

~~~java
static String label(String input) {
    return input == null ? "(none)" : input;
}
~~~

Một handle tìm đến `label(String)` có thể gọi với `(String) null` và nhận `"(none)"`. Không có quy tắc nào nói mọi `MethodHandle` nhận null đều ném `NullPointerException`.

| Tình huống | Kiểu phù hợp? | Kết quả có thể có |
|---|---|---|
| `invokeExact`: receiver `String`, giá trị `null` | Có | `NullPointerException` khi instance method cần receiver |
| `invoke`: tham số đích `int`, đối số `Object` chứa `null` | Có thể tạo adapter | `NullPointerException` khi unbox |
| Tham số reference `String` và body xử lý null | Có | Có thể trả kết quả bình thường |
| Tham số reference `String` và body gọi `input.length()` | Có | `NullPointerException` trong code đích |
| `invokeExact`: call site dùng `Object` khi handle cần `String` | Không khớp | `WrongMethodTypeException`, kể cả giá trị là null |

Chỉ dựa vào exception class không đủ để kết luận rằng null đến từ input, receiver, adapter hay dữ liệu bên trong target. Trường hợp nào cũng cần xem call site, handle type và stack trace.

## 6. Chương trình hoàn chỉnh tái hiện cả ba lỗi

Tạo file `MethodHandleErrorDemo.java`. Ví dụ sử dụng `String.length` và `MethodHandles.identity(int.class)`, đều là API Java hiện đại được hỗ trợ.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodHandleErrorDemo {

    public static void main(String[] args) throws Throwable {

        MethodHandle length = MethodHandles.lookup().findVirtual(
                String.class,
                "length",
                MethodType.methodType(int.class)
        );
        MethodHandle identityInt = MethodHandles.identity(int.class);

        System.out.println("length.type(): " + length.type());
        System.out.println("identityInt.type(): " + identityInt.type());

        // Trường hợp thành công với invokeExact.
        String good = "Java";
        int lengthValue = (int) length.invokeExact(good);
        System.out.println("Success: " + lengthValue);

        // 1. Sai cấu trúc: Object tại call site, String ở handle.
        try {
            Object sameValue = "Java";
            int ignored = (int) length.invokeExact(sameValue);
            System.out.println(ignored);
        } catch (WrongMethodTypeException expected) {
            System.out.println("WrongMethodTypeException: call-site type");
        }

        // 2. Cấu trúc có thể thích nghi, object runtime sai lớp.
        try {
            Object wrongValue = Integer.valueOf(10);
            int ignored = (int) length.invoke(wrongValue);
            System.out.println(ignored);
        } catch (ClassCastException expected) {
            System.out.println("ClassCastException: runtime reference");
        }

        // 3a. Adapter có thể unbox Object -> int nhưng giá trị null.
        try {
            Object missingNumber = null;
            int ignored = (int) identityInt.invoke(missingNumber);
            System.out.println(ignored);
        } catch (NullPointerException expected) {
            System.out.println("NullPointerException: unboxing null");
        }

        // 3b. Call site khớp, receiver instance lại null.
        try {
            String missingReceiver = null;
            int ignored = (int) length.invokeExact(missingReceiver);
            System.out.println(ignored);
        } catch (NullPointerException expected) {
            System.out.println("NullPointerException: null receiver");
        }

        // Cùng một signature: khi dữ liệu đúng, invoke thích nghi được.
        Object validValue = "Hello";
        int adaptedValue = (int) length.invoke(validValue);
        System.out.println("Adapted success: " + adaptedValue);
    }
}
~~~

Biên dịch và chạy từ thư mục có file nguồn, với JDK 18 trở lên:

~~~shell
javac -encoding UTF-8 MethodHandleErrorDemo.java
java MethodHandleErrorDemo
~~~

Đầu ra dự kiến:

~~~text
length.type(): (String)int
identityInt.type(): (int)int
Success: 4
WrongMethodTypeException: call-site type
ClassCastException: runtime reference
NullPointerException: unboxing null
NullPointerException: null receiver
Adapted success: 5
~~~

### Phân tích từng trường hợp

| Dòng minh họa | Handle type | Kiểu call site | Giá trị runtime | Điều được kiểm chứng |
|---|---|---|---|---|
| `length.invokeExact(good)` | `(String)int` | `(String)int` | `"Java"` | Khớp cả chữ ký và giá trị |
| `length.invokeExact(sameValue)` | `(String)int` | `(Object)int` | `"Java"` | **WrongMethodTypeException** dù giá trị thực tế đúng lớp |
| `length.invoke(wrongValue)` | `(String)int` | `(Object)int` | `Integer(10)` | **ClassCastException** khi adapter kiểm tra kiểu runtime |
| `identityInt.invoke(missingNumber)` | `(int)int` | `(Object)int` | `null` | **NullPointerException** khi cần unbox |
| `length.invokeExact(missingReceiver)` | `(String)int` | `(String)int` | `null` | **NullPointerException** do receiver của instance method |
| `length.invoke(validValue)` | `(String)int` | `(Object)int` | `"Hello"` | Adapter thành công với object runtime hợp lệ |

**Điểm mấu chốt:** `WrongMethodTypeException` được quyết định theo **kiểu chữ ký**, `ClassCastException` thường liên quan **lớp thực tế của reference**, còn `NullPointerException` liên quan **giá trị null không dùng được trong một thao tác cụ thể**. Ngoại lệ thứ hai và thứ ba cũng có thể do code đích tự ném, nên phải đọc ngữ cảnh.

## 7. `asType`: tách lỗi khi tạo adapter và lỗi khi chạy adapter

`MethodHandle.asType(MethodType newType)` trả về một handle thích nghi tới `newType` theo các chuyển đổi được hỗ trợ. Có thể có **hai thời điểm lỗi** khác nhau.

### 7.1. Không tạo được adapter vì chuyển đổi chữ ký không được hỗ trợ

~~~java
MethodHandle original = MethodHandles.identity(int.class);
// (int)int

MethodType requested = MethodType.methodType(
        boolean.class, int.class
);

try {
    MethodHandle incompatible = original.asType(requested);
    throw new AssertionError("Unexpected adapter: " + incompatible);
} catch (WrongMethodTypeException expected) {
    System.out.println("No legal int -> boolean result conversion");
}
~~~

Lỗi nằm ở bước **thiết lập adapter**: kiểu trả về `int` không thể chuyển sang `boolean` bằng `asType`. Chưa có dữ liệu runtime nào được truyền.

### 7.2. Tạo adapter được, nhưng giá trị lúc chạy không phù hợp

~~~java
MethodHandle original = MethodHandles.lookup().findVirtual(
        String.class, "length", MethodType.methodType(int.class)
);

MethodHandle adapter = original.asType(
        MethodType.methodType(int.class, Object.class)
);
// adapter.type() == (Object)int

int ok = (int) adapter.invokeExact((Object) "Java"); // 4

Object bad = Integer.valueOf(5);
int failure = (int) adapter.invokeExact(bad); // ClassCastException
~~~

Việc dựng adapter đã thành công, vì cast `Object → String` là thao tác runtime được hỗ trợ. Tuy nhiên, không phải **mọi instance của `Object`** đều là `String`. Với `Integer`, cast thất bại khi adapter chạy.

### 7.3. Vì sao `asType` không giống ép kiểu tùy tiện?

`asType` có quy tắc cho chuyển đổi reference, boxing/unboxing và một số chuyển đổi primitive, đồng thời có thể từ chối signature không tương thích. Không nên suy rằng nó tự:

- Parse chuỗi `"123"` thành số `123`.
- Kiểm tra giá trị số rồi narrowing sang một primitive bất kỳ.
- Chuyển mọi wrapper như `Long` thành `Integer`.
- Thay thế kiểm tra quyền truy cập của `MethodHandles.Lookup`.
- Chuyển `null` thành instance hợp lệ của lớp receiver.

Các API adapter khác, như `MethodHandles.explicitCastArguments`, có **quy tắc chuyển đổi riêng**. Khi cần chuyển đổi đặc biệt, đọc hợp đồng API tương ứng thay vì giả định chúng hoạt động như `invoke` hoặc `Method.invoke` của core reflection.

## 8. Phân biệt lỗi từ quá trình lookup và lỗi lúc invocation

Không phải mọi exception khi sử dụng `MethodHandle` đều là một trong ba lỗi chủ đề bài.

| Giai đoạn | API minh họa | Lỗi tiêu biểu | Hướng xử lý |
|---|---|---|---|
| Tra cứu thành viên | `lookup.findVirtual`, `findStatic` | `NoSuchMethodException` | Kiểm tra tên, kiểu tham số, kiểu trả về, static/instance |
| Kiểm tra quyền lookup | `lookup.findVirtual`, `privateLookupIn` | `IllegalAccessException` | Kiểm tra access mode, module và quyền mở package |
| Dựng adapter | `handle.asType(newType)` | `WrongMethodTypeException` | Kiểm tra chuyển đổi của hai `MethodType` |
| Gọi chính xác | `handle.invokeExact(...)` | `WrongMethodTypeException` | Khớp call-site descriptor cả tham số và kết quả |
| Gọi thích nghi | `handle.invoke(...)` | `WrongMethodTypeException` nếu không có chuyển đổi tương ứng | So sánh `handle.type()` với kiểu call site |
| Adapter ép kiểu reference | `invoke` hoặc `asType` adapter | `ClassCastException` | Kiểm tra class của object runtime |
| Adapter unbox | `invoke` hoặc `asType` adapter | `NullPointerException` | Kiểm tra object null trước khi unbox |
| Gọi instance method | Handle instance với receiver null | `NullPointerException` | Kiểm tra receiver |
| Thực thi code đích | Body của phương thức bất kỳ | Ngoại lệ do body ném | Xem stack trace và ngữ nghĩa code đích |

### MethodHandle khác `Method.invoke` ở cách truyền exception

Với core reflection, khi phương thức đích ném exception, `java.lang.reflect.Method.invoke` thường bọc exception từ đích vào `InvocationTargetException`.

Với `MethodHandle.invoke` / `invokeExact`, exception do code đích ném được truyền ra theo hợp đồng gọi handle, **không được tự động bọc thành `InvocationTargetException`** chỉ vì đi qua method handle. Hai API cũng có quy tắc signature và adaptation khác nhau. Vì vậy, khi chuyển một dispatcher từ reflection sang method handles, cần xem lại cách phân loại và báo cáo lỗi.

Ví dụ code đích:

~~~java
public static int validate(int value) {
    if (value < 0) {
        throw new IllegalArgumentException("Negative input");
    }
    return value;
}
~~~

Nếu lấy handle `(int)int` của `validate` và gọi với `-1`, `IllegalArgumentException` đến từ **logic đích**. Không nên kết luận đó là lỗi adapter; kiểm tra stack trace và thông điệp được giữ lại.

## 9. Thiết kế kiểm chứng trước khi gọi trong ứng dụng thực tế

Một cơ chế plugin, RPC dispatcher hoặc pipeline mapping dữ liệu có thể xây `MethodHandle` khi khởi động rồi gọi nhiều lần. Hãy tách lỗi triển khai khỏi dữ liệu người dùng.

### 9.1. Kiểm tra cấu trúc khi chuẩn bị

Nếu ứng dụng yêu cầu handle `(String)int`, hãy so `MethodType` ngay khi đăng ký:

~~~java
static void requireLengthContract(MethodHandle handle) {
    MethodType expected = MethodType.methodType(
            int.class, String.class
    );

    if (!handle.type().equals(expected)) {
        throw new IllegalArgumentException(
                "Expected " + expected + ", got " + handle.type());
    }
}
~~~

Cách kiểm tra sớm này giúp lỗi về cấu hình không đợi đến khi một request thật tới nơi. Nếu muốn cho phép adapter thì cần cấu hình rõ những phép biến đổi nào được chấp nhận.

### 9.2. Kiểm tra giá trị ở ranh giới dữ liệu

Nếu dữ liệu đến từ JSON, cấu hình hoặc plugin, nên xác định chính sách về kiểu và null **trước** khi đưa vào handle:

~~~java
static String requireText(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException(
                "Expected a non-null String");
    }
    return text;
}
~~~

Pattern matching với `instanceof` được hỗ trợ trên JDK 18 trở lên. Hàm này chủ động chuyển lỗi dữ liệu đầu vào thành thông báo theo hợp đồng nghiệp vụ, thay vì để runtime adapter ném `ClassCastException` hoặc `NullPointerException` khó đọc ở tầng thấp.

Sau khi xác minh:

~~~java
String checked = requireText(input);
int size = (int) length.invokeExact(checked);
~~~

Đoạn mã giả định `input` là giá trị dữ liệu được nhận và `length` là handle `(String)int` đã nêu. Việc kiểm tra bảo đảm type tĩnh `String` ở call site và loại trừ null theo yêu cầu của ứng dụng.

### 9.3. Ghi log đủ để tìm nguyên nhân, tránh lộ dữ liệu

| Thông tin | Có nên ghi? | Lý do |
|---|---|---|
| `handle.type()` | Có | Thấy hợp đồng của handle |
| Đường code/call site và kiểu tham số mong đợi | Có | Xác định sai cấu trúc |
| Lớp runtime của đối số (hoặc nhãn `null`) | Có, khi phù hợp | Giúp phân biệt cast sai với null |
| Loại ngoại lệ và stack trace/cause | Có | Xác định adapter hay code đích |
| Nội dung raw của token, thông tin người dùng hoặc secret | Hạn chế | Không cần thiết để phân loại lỗi kiểu |
| Chuỗi `toString()` của mọi object | Không mặc định | Có thể tiết lộ dữ liệu hoặc thực thi logic ngoài ý muốn |

Một stack trace đầy đủ thường hữu ích hơn việc bắt ba ngoại lệ rồi ghi chung “invoke failed”.

## 10. Các trường hợp dễ gây nhầm trên JDK hiện đại

### 10.1. Cùng giá trị runtime, khác kiểu tĩnh

~~~java
String s = "OK";
Object o = s;

int good = (int) length.invokeExact(s);
int bad  = (int) length.invokeExact(o);   // WrongMethodTypeException.
int fine = (int) length.invoke(o);        // Có thể thích nghi.
~~~

`invokeExact` quan tâm **kiểu tĩnh** của call site; `invoke` có thể dùng adapter. Đừng đọc type runtime `s.getClass()` rồi kết luận mọi lời gọi đều giống nhau.

### 10.2. Gán kết quả vào kiểu rộng hơn có thể đổi descriptor

~~~java
int a = (int) length.invokeExact("Hi");  // (String)int.
long b = (long) length.invokeExact("Hi"); // (String)long, sai chữ ký.
~~~

Muốn nới kiểu thì nới **sau** khi lời gọi đã trả về `int`:

~~~java
long c = (int) length.invokeExact("Hi");
~~~

Ở dòng cuối, `(int)` giúp call site yêu cầu đúng kiểu trả về; phép gán sang `long` được Java xử lý tiếp.

### 10.3. Null có thể bị từ chối trước khi target chạy

Nếu `identityInt` có type `(int)int` và `invoke` nhận `Object null`, adapter không thể unbox null. `NullPointerException` xuất hiện mà `identityInt` không cần thực hiện tác vụ nghiệp vụ nào. Khác với null receiver: ở đó call site có thể khớp hoàn toàn nhưng việc gọi instance method cần dereference receiver.

### 10.4. MethodHandle được gắn với receiver nhưng vẫn có kiểu chính xác

Ví dụ:

~~~java
MethodHandle bound = length.bindTo("Hello");
System.out.println(bound.type()); // ()int.

int n = (int) bound.invokeExact(); // 5.
~~~

Sau `bindTo`, receiver được cố định trong handle và không còn là tham số tại call site. Cố gọi `bound.invokeExact("Hello")` sẽ sai chữ ký `()int` dù chuỗi có vẻ hợp lệ. Nếu thay receiver/null hoặc tạo adapter khác, hãy **đọc lại type của handle mới**; đừng tái sử dụng giả định về type cũ.

### 10.5. Đừng nhầm khác biệt API với thay đổi triển khai Java 18

JEP 416 thay đổi cách core reflection hoạt động bên trong JDK. Nó **không biến** `Method.invoke` thành phương thức signature polymorphic và không làm mất các quy tắc `invokeExact` / `invoke` của `MethodHandle`. Việc dùng chung hạ tầng triển khai không có nghĩa hai public API phải có cùng kiểu ngoại lệ, quy tắc boxing, adaptation hoặc access check.

Không nên chọn cách xử lý lỗi dựa vào giả định về lớp `jdk.internal.*`, cache JIT hoặc chi tiết bytecode nội bộ; sử dụng `MethodType`, hợp đồng API và thử nghiệm trên JDK đang dùng.

## 11. Checklist chẩn đoán theo đúng thứ tự

Khi gặp lỗi ở lời gọi động, có thể kiểm tra tuần tự:

1. **Lấy handle:** `handle` được tạo từ API nào? `findVirtual`, `findStatic`, `bindTo` hay `asType` có làm thay đổi số lượng/kiểu tham số?
2. **Đọc chữ ký:** In `handle.type()`. Với instance handle, receiver thường xuất hiện đầu tiên, trừ khi đã được bind.
3. **Đọc call site:** Kiểu tĩnh của từng đối số là gì? Kiểu kết quả được yêu cầu là `int`, `long`, `Object` hay `void`?
4. **Xác định chế độ:** `invokeExact` phải khớp chính xác; `invoke` có thể thích nghi theo hợp đồng `asType`.
5. **Kiểm tra khả năng adaptation:** Nếu chữ ký không thể biến đổi, phân loại `WrongMethodTypeException` là lỗi cấu trúc/config.
6. **Kiểm tra object runtime:** Reference có đúng lớp mà adapter yêu cầu không? Nếu không, xét `ClassCastException`.
7. **Kiểm tra null:** Null được truyền cho primitive sau unboxing, cho instance receiver, hay cho body code đích?
8. **Phân biệt nguồn exception:** Adapter, truy cập receiver hay logic phương thức đích? Đọc stack trace thay vì chỉ tên ngoại lệ.
9. **Sửa tại tầng đúng:** Sửa cấu trúc khi lỗi type, validate dữ liệu khi lỗi class/null, sửa nghiệp vụ khi code đích ném lỗi.
10. **Kiểm chứng lại:** Thử cả giá trị hợp lệ, sai lớp, null, sai call-site signature và adapter không hợp lệ.

| Dấu hiệu | Loại lỗi cần ưu tiên kiểm tra | Việc cần làm |
|---|---|---|
| Giá trị đúng lớp nhưng `invokeExact` vẫn lỗi | `WrongMethodTypeException` | Kiểu tĩnh call site, **kể cả kiểu trả về** |
| `asType` từ `int` return sang `boolean` return lỗi ngay | `WrongMethodTypeException` | Quy tắc chuyển đổi giữa các `MethodType` |
| `invoke` chấp nhận chữ ký `Object` nhưng gặp `Integer` thay vì `String` | `ClassCastException` | Kiểu thực tế và adapter cast |
| `invoke` chuyển `Object null` sang `int` | `NullPointerException` | Null trước unboxing |
| `invokeExact` dùng `String null` làm receiver | `NullPointerException` | Tính hợp lệ của receiver |
| Lỗi xảy ra sau khi target thực thi | Ngoại lệ từ body, có thể trùng ba loại trên | Stack trace và logic đích |

## 12. Bài tập tự kiểm tra

1. Handle có type `(String)int`. Vì sao `invokeExact((Object) "Java")` gây `WrongMethodTypeException` dù giá trị runtime đúng là `String`?
2. Vì sao `long n = (long) handle.invokeExact("Java")` có thể gây `WrongMethodTypeException` nếu handle trả `int`? Hãy sửa mà không thay handle.
3. `invoke` khác `invokeExact` như thế nào khi call site nhận `Object` nhưng handle yêu cầu `String`?
4. Vì sao adapter `(Object)int` có thể tạo thành công từ handle `(String)int`, rồi vẫn ném `ClassCastException` ở lần gọi với `Integer`?
5. Nếu `MethodHandles.identity(int.class).invoke((Object) null)` được gọi với kiểu trả về `int`, loại ngoại lệ nào thường xảy ra? Lỗi thuộc cấu trúc hay giá trị?
6. Với handle instance `(String)int`, tại sao receiver `String null` không tạo `WrongMethodTypeException` nhưng vẫn thất bại?
7. Hãy dùng `asType` yêu cầu chuyển kết quả `int` sang `boolean`, rồi giải thích lý do có `WrongMethodTypeException` trước khi gọi handle.
8. Khi `bindTo("Hello")` trên handle của `String.length()`, type mới là gì? `invokeExact("Hello")` còn hợp lệ không?
9. Trong trường hợp code đích tự ném `ClassCastException`, làm sao phân biệt nó với exception từ adapter?
10. Vì sao không nên bắt toàn bộ `Throwable` và luôn báo “sai tham số” khi `MethodHandle.invoke` thất bại?
11. Khi chuyển từ `Method.invoke` sang `MethodHandle.invokeExact`, cần thay đổi những giả định nào về exception và chữ ký?
12. Chỉnh chương trình hoàn chỉnh ở mục 6: thêm một trường hợp sai kiểu trả về cho `invokeExact` và một trường hợp `asType` không tạo được adapter; đối chiếu ngoại lệ, stack trace và thời điểm lỗi.

**Ghi nhớ:** `WrongMethodTypeException` thường cho biết **không thể dùng chữ ký hiện tại** để gọi hoặc tạo adapter; với `invokeExact` phải khớp cả đối số lẫn kiểu trả về. `ClassCastException` thường xuất hiện khi reference conversion **hợp lệ về mặt hình dạng** nhưng object runtime không thuộc lớp mong đợi. `NullPointerException` xuất hiện khi **null** không thể được unbox, làm instance receiver hoặc bị dereference trong code đích. Cả ba loại có thể được ném ở nhiều tầng, nên hãy kiểm tra `handle.type()`, kiểu call site, giá trị runtime và stack trace trước khi chọn cách sửa.

## Tài liệu tham khảo chính thức

- [Java SE 25: `MethodHandle` — `invokeExact`, `invoke`, `asType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html).
- [Java SE 25: `MethodType` — mô tả kiểu của method handle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html).
- [Java SE 25: `WrongMethodTypeException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html).
- [Java SE 25: `MethodHandles` — `lookup`, `identity`, `explicitCastArguments`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html).
- [Java SE 25: `ClassCastException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassCastException.html).
- [Java SE 25: `NullPointerException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/NullPointerException.html).
- [OpenJDK JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416).

