# StackFrame và thứ tự từ khung hiện tại trở xuống

`StackWalker` trong Java 9 cung cấp API để duyệt call stack của **luồng hiện tại** theo cách có kiểm soát. Mỗi phần tử là một `StackWalker.StackFrame`, đại diện cho một lời gọi phương thức trên stack. `StackWalker.walk()` đưa các frame vào một `Stream` theo thứ tự từ frame trẻ nhất (youngest, gần điểm thực thi hiện tại nhất) tới frame cũ hơn (older, các caller phía dưới).

Thứ tự này quan trọng khi cần tìm caller, bỏ qua frame hiện tại, giới hạn độ sâu hoặc ghi lại đường đi của một lời gọi. Khi gọi `walk()` bên trong phương thức `inspect()`, frame đầu tiên là `inspect()`, tiếp theo là phương thức đã gọi `inspect()`, rồi tới caller của phương thức đó.

## Mục tiêu

- Hiểu một `StackFrame` đại diện cho điều gì.
- Đọc tên class, tên method, số dòng và vị trí bytecode của frame.
- Hiểu thứ tự stream từ frame hiện tại đi xuống các caller.
- Dùng `skip()`, `limit()`, `filter()` và `findFirst()` để chọn frame cần thiết.
- Biết khi nào cần `RETAIN_CLASS_REFERENCE` để lấy `Class<?>`.
- Hiểu thời gian sống của stream được truyền vào `StackWalker.walk()`.
- Phân biệt frame của stack với `StackTraceElement` và tránh phụ thuộc vào vị trí frame cố định.

## 1. StackWalker và StackFrame

`StackWalker` là API trong `java.lang` được bổ sung ở Java 9. Nó cho phép ứng dụng duyệt stack frame theo nhu cầu, thay vì luôn tạo toàn bộ stack trace rồi mới lọc.

`StackWalker.StackFrame` là interface mô tả một frame. Một frame chứa thông tin về phương thức đang hoạt động tại một điểm trong call stack.

~~~java
StackWalker walker = StackWalker.getInstance();

walker.forEach(frame ->
    System.out.println(frame.getClassName() + "#" + frame.getMethodName())
);
~~~

`forEach()` duyệt các frame theo thứ tự stack. Khi cần lọc, giới hạn số frame hoặc chuyển kết quả thành một kiểu dữ liệu khác, `walk()` linh hoạt hơn vì cung cấp một `Stream<StackFrame>` cho hàm xử lý.

## 2. Các thông tin có trong StackFrame

Java 9 cung cấp các phương thức sau trên `StackWalker.StackFrame`:

| Phương thức | Thông tin trả về |
| --- | --- |
| `getClassName()` | Tên đầy đủ của class khai báo phương thức |
| `getMethodName()` | Tên phương thức của frame |
| `getDeclaringClass()` | Đối tượng `Class<?>` khai báo phương thức; cần option `RETAIN_CLASS_REFERENCE` |
| `getByteCodeIndex()` | Chỉ số bytecode tại điểm thực thi của frame; có thể là `-1` nếu không xác định được |
| `getLineNumber()` | Số dòng nguồn tương ứng; có thể âm nếu không có thông tin dòng |
| `isNativeMethod()` | Frame có đại diện cho native method hay không |
| `toStackTraceElement()` | Chuyển frame thành `StackTraceElement` tương ứng |

### 2.1. Tên class và tên method

`getClassName()` và `getMethodName()` là cách đơn giản để nhận diện frame mà không cần giữ tham chiếu class:

~~~java
String description = frame.getClassName() + "#" + frame.getMethodName();
~~~

Tên method có thể bị trùng giữa các class hoặc giữa các overload. Khi ghi log, thường nên kết hợp tên class, method và số dòng để dễ xác định vị trí.

### 2.2. Lấy Class<?> bằng RETAIN_CLASS_REFERENCE

Mặc định, StackWalker không giữ tham chiếu `Class<?>` trong các frame. Nếu gọi `getDeclaringClass()` trên walker không có option này, API có thể ném `UnsupportedOperationException`.

Để lấy class object, tạo walker với `StackWalker.Option.RETAIN_CLASS_REFERENCE`:

~~~java
StackWalker walker = StackWalker.getInstance(
    StackWalker.Option.RETAIN_CLASS_REFERENCE
);

Class<?> declaringClass = walker.walk(stream ->
    stream.findFirst()
        .map(StackWalker.StackFrame::getDeclaringClass)
        .orElse(null)
);
~~~

Option này hữu ích khi cần so sánh class bằng identity, kiểm tra annotation hoặc truy cập metadata qua reflection. Nếu chỉ cần tên class để log, `getClassName()` là đủ và không cần giữ class reference.

### 2.3. Line number, bytecode index và native method

`getLineNumber()` hữu ích khi ghi log hoặc chẩn đoán lỗi. Giá trị phụ thuộc metadata debug được cung cấp trong class file; không nên giả định mọi frame đều có số dòng hợp lệ.

`getByteCodeIndex()` mô tả vị trí bytecode tại điểm thực thi. Đây là thông tin mức thấp, hữu ích cho công cụ phân tích runtime hơn là logic nghiệp vụ thông thường.

`isNativeMethod()` cho biết frame có thuộc native method hay không. Native frame có thể không có line number hoặc bytecode index tương ứng.

### 2.4. Chuyển thành StackTraceElement

Nếu API khác trong ứng dụng đã dùng `StackTraceElement`, có thể chuyển frame:

~~~java
StackTraceElement element = frame.toStackTraceElement();
System.out.println(element);
~~~

`StackTraceElement` là dạng biểu diễn quen thuộc trong stack trace truyền thống. `StackFrame` thuận tiện hơn khi cần duyệt có kiểm soát và lấy class reference.

## 3. Thứ tự frame: từ hiện tại tới caller

Stream do `StackWalker.walk()` cung cấp được sắp xếp từ frame trẻ nhất tới frame cũ hơn:

1. Frame của phương thức gọi `walk()`.
2. Frame của phương thức đã gọi phương thức đó.
3. Frame của caller tiếp theo.
4. Tiếp tục đi xuống stack cho tới khi hết frame có thể quan sát.

Ví dụ call chain:

~~~text
main()
  -> first()
       -> second()
            -> inspect()
                 -> StackWalker.walk(...)
~~~

Khi `walk()` được gọi trong `inspect()`, thứ tự frame thu được bắt đầu từ `inspect()`, sau đó là `second()`, `first()` và `main()`.

~~~text
Thứ tự stream:
0  inspect()   <- frame hiện tại, gần điểm walk nhất
1  second()    <- caller của inspect()
2  first()     <- caller tiếp theo
3  main()      <- caller ở phía dưới
~~~

Đừng đọc stream theo thứ tự từ `main()` tới phương thức hiện tại. Nếu muốn in từ caller ngoài cùng tới frame hiện tại, cần thu thập các frame trước rồi đảo thứ tự trong collection; bản thân stream của StackWalker vẫn giữ thứ tự youngest-to-oldest.

## 4. Dùng walk() để lấy một phần stack

`walk()` nhận một hàm xử lý stream và trả về kết quả do hàm đó tạo ra:

~~~java
<T> T walk(Function<? super Stream<StackFrame>, ? extends T> function)
~~~

Ví dụ lấy bốn frame đầu tiên:

~~~java
List<String> frames = walker.walk(stream -> stream
    .limit(4)
    .map(frame -> frame.getClassName() + "#" + frame.getMethodName())
    .collect(Collectors.toList())
);
~~~

Trong Java 9, dùng `collect(Collectors.toList())` để thu thập stream. Không dùng `Stream.toList()` trong mã cần tương thích Java 9 vì phương thức đó được bổ sung ở phiên bản Java mới hơn.

### 4.1. Bỏ qua frame hiện tại bằng skip()

Nếu chỉ quan tâm caller của phương thức đang gọi `walk()`, bỏ frame đầu tiên:

~~~java
List<String> callers = walker.walk(stream -> stream
    .skip(1)
    .limit(3)
    .map(frame -> frame.getClassName() + "#" + frame.getMethodName())
    .collect(Collectors.toList())
);
~~~

`skip(1)` bỏ frame hiện tại. Phần còn lại bắt đầu từ caller trực tiếp. Đây là cách thường dùng khi một utility method muốn ghi nhận nơi nó được gọi.

### 4.2. Giới hạn độ sâu bằng limit()

~~~java
List<StackWalker.StackFrame> firstFrames = walker.walk(stream -> stream
    .limit(5)
    .collect(Collectors.toList())
);
~~~

`limit(5)` chỉ lấy tối đa năm frame gần hiện tại nhất. Việc giới hạn giúp tránh duyệt sâu hơn mức cần thiết, nhất là khi chỉ cần caller gần nhất hoặc một đoạn ngắn của call chain.

### 4.3. Lọc frame bằng filter()

Có thể chọn frame thuộc một class hoặc package cụ thể:

~~~java
List<String> applicationFrames = walker.walk(stream -> stream
    .filter(frame -> frame.getClassName().startsWith("com.example."))
    .limit(10)
    .map(frame -> frame.getClassName() + "#" + frame.getMethodName())
    .collect(Collectors.toList())
);
~~~

Filter được áp dụng theo thứ tự stream. Nếu cần lấy caller đầu tiên thỏa điều kiện, kết hợp `filter()` với `findFirst()`.

~~~java
String caller = walker.walk(stream -> stream
    .skip(1)
    .filter(frame -> frame.getClassName().startsWith("com.example."))
    .map(StackWalker.StackFrame::getClassName)
    .findFirst()
    .orElse("unknown")
);
~~~

## 5. Vòng đời của stream trong walk()

Stream được truyền vào hàm của `walk()` chỉ hợp lệ trong thời gian hàm đó đang thực thi. StackWalker đóng stream khi hàm trả về hoặc ném exception.

Vì vậy, hãy tiêu thụ stream ngay bên trong callback và trả về một kết quả đã được tính:

~~~java
List<String> names = walker.walk(stream -> stream
    .map(StackWalker.StackFrame::getClassName)
    .collect(Collectors.toList())
);
~~~

Không trả trực tiếp stream ra ngoài:

~~~java
// Không làm như vậy:
Stream<StackWalker.StackFrame> frames = walker.walk(stream -> stream);
~~~

Stream đã bị đóng khi callback kết thúc; cố sử dụng nó sau đó không hợp lệ. Cũng không lưu một pipeline stream chưa tiêu thụ để xử lý ở một thời điểm khác.

Nếu cần dữ liệu để dùng sau callback, hãy materialize thông tin cần thiết thành `List<String>`, `List<StackTraceElement>` hoặc một kiểu dữ liệu riêng trong callback. Không cần giữ toàn bộ `StackFrame` nếu ứng dụng chỉ cần tên class, method và line number.

## 6. Các option ảnh hưởng đến frame hiển thị

`StackWalker` có các option điều khiển loại frame được giữ lại:

| Option | Ý nghĩa |
| --- | --- |
| `RETAIN_CLASS_REFERENCE` | Cho phép `StackFrame.getDeclaringClass()` trả về `Class<?>` |
| `SHOW_REFLECT_FRAMES` | Bao gồm các frame liên quan đến reflection |
| `SHOW_HIDDEN_FRAMES` | Bao gồm hidden frame mà mặc định bị ẩn |

Ví dụ cấu hình nhiều option:

~~~java
Set<StackWalker.Option> options = EnumSet.of(
    StackWalker.Option.RETAIN_CLASS_REFERENCE,
    StackWalker.Option.SHOW_REFLECT_FRAMES
);

StackWalker walker = StackWalker.getInstance(options);
~~~

Mặc định, các frame reflection và hidden frame không được hiển thị. Bật option chỉ khi công cụ chẩn đoán thực sự cần nhìn thấy các frame đó; chúng có thể làm call chain dài hơn và khiến vị trí frame thay đổi.

Không viết logic nghiệp vụ phụ thuộc vào một chỉ số frame cố định như “frame thứ ba luôn là controller”. Framework, reflection, proxy, lambda hoặc thay đổi cách gọi có thể làm cấu trúc stack khác đi. Hãy lọc theo class/method hoặc truyền context tường minh nếu có thể.

## 7. StackWalker chỉ duyệt stack của luồng hiện tại

`StackWalker.walk()` duyệt call stack của thread đang gọi nó. Một walker không phải công cụ để lấy stack của một thread bất kỳ.

Nếu cần chẩn đoán nhiều thread, phải dùng cơ chế quan sát phù hợp với thread hoặc công cụ quản trị runtime. Không gọi `StackWalker.walk()` từ một thread rồi kỳ vọng nhận được stack của worker thread khác.

StackWalker cũng không phải bản ghi lịch sử lời gọi. Nó chỉ mô tả các frame còn tồn tại tại thời điểm duyệt. Khi một phương thức đã return, frame của phương thức đó không còn trong stack hiện tại.

## 8. Ví dụ hoàn chỉnh chạy trên Java 9

Ví dụ tạo call chain `main() -> first() -> second() -> inspect()`. Từ `inspect()`, chương trình duyệt bốn frame đầu và sau đó bỏ frame hiện tại để chỉ lấy caller.

**Tệp:** `StackWalkerFrameOrderDemo.java`

~~~java
import java.util.List;
import java.util.stream.Collectors;

public class StackWalkerFrameOrderDemo {
    private static final StackWalker WALKER = StackWalker.getInstance(
        StackWalker.Option.RETAIN_CLASS_REFERENCE
    );

    public static void main(String[] args) {
        first();
    }

    private static void first() {
        second();
    }

    private static void second() {
        inspect();
    }

    private static void inspect() {
        List<String> fromCurrentFrame = WALKER.walk(stream -> stream
            .limit(4)
            .map(frame -> frame.getDeclaringClass().getSimpleName()
                + "#" + frame.getMethodName())
            .collect(Collectors.toList())
        );

        List<String> callersOnly = WALKER.walk(stream -> stream
            .skip(1)
            .limit(3)
            .map(frame -> frame.getDeclaringClass().getSimpleName()
                + "#" + frame.getMethodName())
            .collect(Collectors.toList())
        );

        fromCurrentFrame.forEach(System.out::println);
        System.out.println("-- after skipping current frame --");
        callersOnly.forEach(System.out::println);
    }
}
~~~

Biên dịch và chạy với JDK 9 trở lên:

~~~text
javac --release 9 StackWalkerFrameOrderDemo.java
java StackWalkerFrameOrderDemo
~~~

Output:

~~~text
StackWalkerFrameOrderDemo#inspect
StackWalkerFrameOrderDemo#second
StackWalkerFrameOrderDemo#first
StackWalkerFrameOrderDemo#main
-- after skipping current frame --
StackWalkerFrameOrderDemo#second
StackWalkerFrameOrderDemo#first
StackWalkerFrameOrderDemo#main
~~~

Giải thích:

1. `inspect()` là phương thức gọi `WALKER.walk()`, nên nó xuất hiện đầu tiên.
2. `second()` là caller trực tiếp của `inspect()`.
3. `first()` gọi `second()`, nên xuất hiện sau `second()`.
4. `main()` gọi `first()`, nên nằm sâu hơn trong stack.
5. Pipeline thứ hai dùng `skip(1)`, vì vậy frame `inspect()` bị bỏ và danh sách bắt đầu từ `second()`.

Ví dụ dùng `RETAIN_CLASS_REFERENCE` vì cần gọi `getDeclaringClass()`. Nếu chỉ cần tên class, có thể bỏ option và dùng `getClassName()`.

## 9. StackFrame và StackTraceElement

`StackTraceElement` là kiểu dữ liệu quen thuộc được dùng trong `Throwable.getStackTrace()` và các stack trace truyền thống. `StackFrame` là abstraction dành cho StackWalker, hỗ trợ duyệt stream và lấy class reference khi được bật.

| Tiêu chí | StackFrame | StackTraceElement |
| --- | --- | --- |
| Nguồn | `StackWalker.walk()` hoặc `forEach()` | Stack trace của Throwable hoặc chuyển đổi từ StackFrame |
| Cách duyệt | Stream theo thứ tự stack, có thể filter/skip/limit | Thường là mảng các phần tử |
| Class reference | Có thể lấy `Class<?>` khi bật `RETAIN_CLASS_REFERENCE` | Chủ yếu cung cấp tên class dạng String |
| Chuyển đổi | Có `toStackTraceElement()` | Là dạng biểu diễn stack trace |

Nếu cần duyệt một phần stack theo nhu cầu, dùng StackWalker. Nếu cần lưu hoặc hiển thị stack trace theo kiểu truyền thống, `StackTraceElement` vẫn phù hợp.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đọc stack từ `main()` tới frame hiện tại | Nhầm chiều stream | Nhớ thứ tự là youngest-to-oldest, frame hiện tại trước |
| Nghĩ frame đầu tiên luôn là `main()` | Bỏ qua frame của phương thức đang gọi `walk()` | Frame đầu tiên là phương thức gọi `walk()` |
| Gọi `getDeclaringClass()` trên walker mặc định | Chưa bật class reference | Tạo walker với `RETAIN_CLASS_REFERENCE` |
| Trả stream khỏi callback `walk()` | Stream bị đóng khi callback kết thúc | Thu thập dữ liệu ngay bên trong callback |
| Lưu stream chưa tiêu thụ để dùng sau | Stream không còn hợp lệ sau callback | Trả về collection hoặc dữ liệu đã materialize |
| Dùng chỉ số frame cố định để nhận diện caller | Framework, reflection và cách gọi có thể thay đổi stack | Lọc theo class/method hoặc truyền context tường minh |
| Giả định mọi frame có line number hợp lệ | Metadata nguồn có thể không có | Kiểm tra giá trị trả về và dùng `StackTraceElement` để hiển thị |
| Nhầm StackWalker đọc stack của thread khác | Walker chỉ duyệt thread gọi nó | Gọi trên thread cần quan sát hoặc dùng công cụ phù hợp |
| Bật mọi option không cần thiết | Reflection/hidden frames làm stack phức tạp hơn | Chỉ bật option phục vụ nhu cầu chẩn đoán |

## 11. Quy tắc thực hành

1. Đọc stack theo thứ tự từ frame hiện tại đi xuống caller.
2. Dùng `getClassName()` và `getMethodName()` khi chỉ cần thông tin nhận diện dạng chuỗi.
3. Bật `RETAIN_CLASS_REFERENCE` khi thật sự cần `Class<?>` từ `getDeclaringClass()`.
4. Dùng `skip(1)` để bỏ frame của phương thức hiện tại khi cần caller trực tiếp.
5. Dùng `limit()` để tránh duyệt sâu hơn mức cần thiết.
6. Dùng `filter()` theo class/package thay vì phụ thuộc vào vị trí frame cố định.
7. Tiêu thụ stream trong callback `walk()`; chỉ trả về dữ liệu đã materialize.
8. Dùng `toStackTraceElement()` khi cần tích hợp với API stack trace truyền thống.
9. Chỉ bật `SHOW_REFLECT_FRAMES` hoặc `SHOW_HIDDEN_FRAMES` khi chẩn đoán cần các frame đó.
10. Nhớ rằng StackWalker chỉ quan sát stack của thread hiện tại tại thời điểm gọi.

## 12. Tự kiểm tra

- `StackWalker.walk()` trả stream theo thứ tự nào? Từ frame trẻ nhất/gần hiện tại nhất tới caller cũ hơn.
- Frame đầu tiên thường là frame nào? Phương thức đang gọi `walk()`.
- Nếu `inspect()` gọi `walk()` và được gọi bởi `second()`, thứ tự bắt đầu là gì? `inspect()`, rồi `second()`.
- `skip(1)` làm gì trong ví dụ này? Bỏ frame `inspect()` để bắt đầu từ caller trực tiếp.
- Khi nào `getDeclaringClass()` dùng được? Khi walker được tạo với `RETAIN_CLASS_REFERENCE`.
- `getLineNumber()` có luôn trả số dương không? Không; thông tin dòng có thể không khả dụng.
- Stream truyền vào `walk()` có thể lưu để dùng sau callback không? Không; stream bị đóng khi callback kết thúc.
- `StackWalker.walk()` có đọc stack của thread khác không? Không, nó duyệt thread đang gọi.
- Dùng API nào để chuyển StackFrame thành kiểu stack trace truyền thống? `toStackTraceElement()`.

Điểm cốt lõi: **StackWalker trả các StackFrame theo thứ tự từ phương thức hiện tại đi xuống caller.** Dùng `skip()` để bỏ frame hiện tại, `limit()` để giới hạn độ sâu, `filter()` để chọn frame cần thiết và luôn tiêu thụ stream bên trong callback `walk()`.