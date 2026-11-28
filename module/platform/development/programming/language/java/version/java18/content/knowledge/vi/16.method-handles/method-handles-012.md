# Đối số null với kiểu tĩnh xác định và trường hợp receiver null

## 1. Mục tiêu và phạm vi

Bài học thuộc chương **MethodHandle** của mô-đun **JAVA_VERSION_JAVA18**. Mô-đun khám phá những điểm còn hữu ích từ Java 18 trên JDK hiện đại, bên cạnh UTF-8 mặc định, máy chủ web đơn giản và Javadoc snippet, đồng thời rèn cách kiểm chứng hợp đồng API về phân giải tên, reflection và `MethodHandle`. Trọng tâm ở đây là hai tình huống dễ nhầm: truyền **giá trị `null` có kiểu tĩnh xác định** và truyền **`null` vào vị trí receiver** của một method handle gọi instance method.

`MethodHandle` thuộc `java.lang.invoke` là đối tượng có kiểu phương thức (`MethodType`) mô tả chính xác danh sách kiểu tham số và kiểu trả về. Khác với cách gọi phương thức Java thông thường có thể được trình biên dịch chọn overload, một handle đã được tìm và lưu giữ có một kiểu cụ thể. Chính kiểu **ở vị trí gọi** quyết định lời gọi `invokeExact` có hợp lệ hay không; còn giá trị `null` chỉ được xét khi đã đạt đến bước truyền đối số/thực thi.

Sau khi học, bạn có thể:

- Xác định tham số và kiểu trả về của `MethodHandle.type()`, đặc biệt tham số receiver đối với instance method.
- Dùng ép kiểu tường minh như `(String) null` để cố định kiểu tĩnh tại call site của `invokeExact`.
- Phân biệt `WrongMethodTypeException`, `ClassCastException`, `NullPointerException` và ngoại lệ do chính phương thức đích ném.
- Kiểm chứng sự khác nhau giữa `invokeExact`, `invoke` và một handle đã được điều chỉnh bằng `asType`.
- Giải thích tại sao `null` có thể là đối số hợp lệ của một tham số tham chiếu, nhưng receiver `null` khi gọi instance method lại dẫn đến thất bại.
- Tránh suy diễn hành vi từ các API cũ hay từ chi tiết triển khai JVM không được hợp đồng công khai bảo đảm.

## 2. Kiểu `MethodType` và kiểu tĩnh tại call site

Giả sử một phương thức static:

```java
static String describe(String text) {
    return text == null ? "<null>" : "[" + text + "]";
}
```

Có thể lấy handle bằng:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle describe = lookup.findStatic(
        Example.class,
        "describe",
        MethodType.methodType(String.class, String.class));
```

Kiểu của handle là **`(String)String`**: nhận đúng một `String`, trả về `String`. `MethodType` không lưu riêng một kiểu cho giá trị `null`. Vì `String` là kiểu tham chiếu, đối số mang giá trị `null` có thể được chuyển vào phương thức; phương thức đích tự quyết định cách xử lý.

Trong lời gọi `invokeExact`, JVM cần kiểu tại **call site** khớp chính xác với `MethodType` của handle, gồm **tất cả kiểu tham số và kiểu kết quả**. Dù cùng là giá trị null ở runtime, hai biểu thức sau tạo những kiểu tĩnh khác nhau:

```java
String a = (String) describe.invokeExact((String) null);

// Chữ ký call site là (Object)String, không khớp (String)String.
String b = (String) describe.invokeExact((Object) null);
```

Lệnh đầu hợp lệ và trả `"<null>"`. Lệnh thứ hai biên dịch được nhưng khi thực thi ném `WrongMethodTypeException` vì kiểu đối số ở call site là `Object` thay vì `String`. **Giá trị thực tế ở cả hai trường hợp đều là null**; điều làm chúng khác nhau là kiểu tĩnh đã được xác định khi biên dịch.

Không dựa vào `invokeExact(null)` không ép kiểu trong ví dụ cần kiểm chứng chính xác: cách biểu thức `null` được định kiểu tại call site có thể không khớp descriptor mong muốn. Hãy viết rõ `(String) null` (hoặc biến khai báo `String value = null`) để người đọc và trình biên dịch đều thấy kiểu mục tiêu.

### Kiểu kết quả cũng phải đúng

```java
// Đúng: call site mong muốn String.
String value = (String) describe.invokeExact((String) null);

// Sai kiểu kết quả: call site mong muốn Object, handle trả String.
Object wider = describe.invokeExact((String) null);
```

Lệnh thứ hai có thể ném `WrongMethodTypeException`: với `invokeExact`, việc `String` là subtype của `Object` **không đủ** để tự điều chỉnh kiểu trả về. Ép kiểu kết quả tường minh `(String)` có vai trò xác định kiểu trả về của lời gọi signature-polymorphic. Nếu muốn nhận kết quả ở kiểu `Object` mà có chuyển đổi thích nghi, dùng `invoke` hoặc tạo adapter có kiểu tương ứng.

Đặc biệt, lời gọi `invokeExact` viết như một statement bỏ qua giá trị trả về có call site mong muốn kiểu `void`. Khi handle thực sự trả `String` hay `int`, việc bỏ qua giá trị theo cách đó không tương đương việc gọi Java thông thường; nó có thể gây lỗi kiểu phương thức. Vì thế các ví dụ đều nhận kết quả vào biến đúng kiểu.

## 3. Ba đối tượng “null” cần phân biệt

| Tình huống | Ví dụ | Điều quyết định kết quả |
| --- | --- | --- |
| `null` là đối số của **phương thức static** nhận kiểu tham chiếu | `describe.invokeExact((String) null)` | Kiểu call site khớp; logic của `describe` có thể chấp nhận null |
| `null` là **receiver** của instance method | `length.invokeExact((String) null)` | Có thể khớp kiểu handle, nhưng không có instance thực để gọi; thường ném `NullPointerException` |
| Chính biến **`MethodHandle` là null** | `MethodHandle absent = null; absent.invokeExact(...)` | Không có đối tượng handle để gọi, nên ném `NullPointerException` |
| `null` đi vào tham số primitive qua chuyển đổi | `twice.invoke((Integer) null)` với target nhận `int` | Chuyển đổi unboxing `Integer` null sang `int` thất bại bằng `NullPointerException` |
| `null` có kiểu tĩnh sai ở `invokeExact` | `describe.invokeExact((Object) null)` | Lỗi khớp kiểu call site `WrongMethodTypeException`, dù giá trị null |

Điểm cốt lõi: **null là giá trị; kiểu tĩnh, vị trí receiver và chuyển đổi tại lời gọi là ba khái niệm riêng**. Chỉ nhìn thấy chữ `null` trong mã không đủ để đoán loại ngoại lệ.

## 4. `invokeExact` và `invoke` xử lý null khác nhau thế nào?

Hai phương thức `MethodHandle.invokeExact` và `MethodHandle.invoke` là phương thức *signature-polymorphic*; trình biên dịch cho phép biểu diễn các dạng tham số/kiểu trả về tương ứng với call site. Khác biệt chính:

- `invokeExact` yêu cầu descriptor tại call site **trùng chính xác** với `MethodType` của handle. Nó không tự thêm chuyển đổi kiểu chỉ để lời gọi khớp.
- `invoke` cho phép những thích nghi mà `MethodHandle.asType` hỗ trợ giữa kiểu call site và kiểu handle. Chuyển đổi kiểu tham chiếu có thể yêu cầu cast; chuyển đổi primitive có thể cần boxing, unboxing hoặc widening hợp lệ.
- `asType(MethodType)` trả một handle đã thích nghi với kiểu mới (nếu có thể). Bạn vẫn có thể gọi **`invokeExact`** trên handle mới khi kiểu call site đã khớp kiểu mới.

Với handle `(String)String`:

```java
// Khớp chính xác: (String)String.
String exact = (String) describe.invokeExact((String) null);

// invoke có thể thích nghi từ (Object)String về (String)String.
// Cast một Object null sang String vẫn cho giá trị null.
String generic = (String) describe.invoke((Object) null);

// Điều chỉnh handle thành (Object)String trước khi gọi exact.
MethodHandle adapted = describe.asType(
        MethodType.methodType(String.class, Object.class));

String adjusted = (String) adapted.invokeExact((Object) null);
```

Trong cả ba dòng thành công, phương thức `describe` nhận `null` và trả `"<null>"`. Nhưng khả năng thích nghi **không phải phép chuyển đổi tùy ý**:

```java
// Đối số Object là Integer không thể cast thành String.
String bad = (String) describe.invoke((Object) Integer.valueOf(7));
```

Trường hợp này có thể ném `ClassCastException` khi adapter chuyển đối số `Object` sang `String`, trước khi thân `describe` được chạy.

`WrongMethodTypeException` là một subtype của `RuntimeException`, dùng để chỉ lời gọi/kiểu handle không tương thích với descriptor mong muốn. `ClassCastException` và `NullPointerException` có thể xuất hiện **trong bước thích nghi hoặc khi thực thi target**. Hãy ghi đúng bước thất bại thay vì gom chúng thành một lỗi “MethodHandle không nhận null”.

### Ví dụ đối chiếu tham số primitive

Giả sử có:

```java
static int twice(int x) {
    return x * 2;
}
```

Handle tìm được có kiểu `(int)int`:

```java
MethodHandle twiceHandle = lookup.findStatic(
        Example.class, "twice",
        MethodType.methodType(int.class, int.class));

int ok = (int) twiceHandle.invokeExact(4); // 8

// invoke thích nghi (Integer)int -> (int)int qua unboxing;
// unbox một Integer null sẽ ném NullPointerException.
int bad = (int) twiceHandle.invoke((Integer) null);
```

Đây là null ở **đối số thường**, không phải receiver. `int` là kiểu primitive nên không có giá trị null hợp lệ. Trước khi vào `twice`, adapter phải unbox một `Integer` và không thể unbox giá trị null.

Nếu thay `invoke` bằng `invokeExact((Integer) null)`, kiểu call site sẽ không trùng `(int)int`; phép thử chuyển sang nhánh `WrongMethodTypeException` thay vì đi tới bước unboxing.

## 5. Receiver null: khớp kiểu nhưng không có đối tượng để gọi

Với phương thức instance `String.length()`, việc tra cứu:

```java
MethodHandle length = lookup.findVirtual(
        String.class,
        "length",
        MethodType.methodType(int.class));
```

trả handle có kiểu **`(String)int`**. Tham số `String` đầu tiên **chính là receiver**. Đây là điểm khác với `findStatic`, vốn không có receiver ngầm.

```java
int n = (int) length.invokeExact("Java"); // 4

// Call site đúng kiểu (String)int nhưng receiver là null.
int missing = (int) length.invokeExact((String) null);
```

Dòng thứ hai có kiểu tĩnh hoàn toàn hợp lệ; lỗi xảy ra ở runtime vì lời gọi instance method không có đối tượng receiver, dẫn đến `NullPointerException`. **Không được kết luận rằng mọi null truyền vào `MethodHandle` đều gây `WrongMethodTypeException`.** Ở đây lỗi không nằm ở kiểu; receiver null là nguyên nhân.

Nếu viết:

```java
int wrong = (int) length.invokeExact((Object) null);
```

call site lại có kiểu `(Object)int`. Khi đó `invokeExact` sẽ thất bại ở bước đối chiếu kiểu bằng `WrongMethodTypeException`. Việc giá trị receiver vẫn là null không xóa được sự khác nhau giữa hai tình huống.

Cũng cần phân biệt:

```java
MethodHandle absent = null;
int value = (int) absent.invokeExact("Java");
```

`absent` là chính **đối tượng MethodHandle** và đang null; đây là lỗi dereference handle, khác việc truyền receiver null vào một handle hợp lệ. Việc dùng handle không-null là điều kiện đầu tiên trước khi xem xét kiểu và giá trị các đối số.

### Liên hệ với reflection

Ở reflection, `Method.invoke(receiver, arguments)` cung cấp receiver dưới dạng tham số riêng của API. Với `MethodHandle` trả về từ `findVirtual`, receiver xuất hiện như **tham số đầu tiên trong `MethodType`**. Do đó khi đọc log kiểu handle, phải chỉ ra tham số nào là receiver để diễn giải lỗi null.

Khi target method ném ngoại lệ, `MethodHandle.invokeExact` hoặc `invoke` nhìn chung truyền ngoại lệ của target ra caller trực tiếp; nó không mặc định bọc lỗi theo cơ chế `InvocationTargetException` như `Method.invoke`. Vì vậy một `NullPointerException` khi gọi qua method handle không nên bị chẩn đoán như một lỗi wrapper reflection.

## 6. Ví dụ Java tự chứa để kiểm chứng bốn nhánh

Chương trình sau sử dụng API vẫn được hỗ trợ từ JDK 18 trở lên; không cần thư viện ngoài, DNS hay truy cập private member. Nó tạo các handle hợp lệ rồi chủ động đưa vào từng tình huống: đúng kiểu với null thường, sai kiểu tĩnh ở `invokeExact`, receiver null, `invoke` thích nghi từ `Object`, và null đi qua unboxing.

Lưu thành `NullMethodHandleDemo.java`:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class NullMethodHandleDemo {
    public static String describe(String value) {
        return value == null ? "<null>" : "[" + value + "]";
    }

    public static int twice(int number) {
        return number * 2;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle describe = lookup.findStatic(
                NullMethodHandleDemo.class,
                "describe",
                MethodType.methodType(String.class, String.class));

        MethodHandle length = lookup.findVirtual(
                String.class,
                "length",
                MethodType.methodType(int.class));

        MethodHandle twice = lookup.findStatic(
                NullMethodHandleDemo.class,
                "twice",
                MethodType.methodType(int.class, int.class));

        require(describe.type().equals(
                    MethodType.methodType(String.class, String.class)),
                "Unexpected type of describe");
        require(length.type().equals(
                    MethodType.methodType(int.class, String.class)),
                "Virtual handle must have receiver parameter");

        // 1. null ở tham số tham chiếu, kiểu tĩnh String:
        String direct = (String) describe.invokeExact((String) null);
        require("<null>".equals(direct), "Null argument was not accepted");
        System.out.println("reference-null=OK:" + direct);

        // 2. Cũng là null nhưng kiểu call site Object:
        try {
            String ignored = (String) describe.invokeExact((Object) null);
            throw new AssertionError("Expected WrongMethodTypeException");
        } catch (WrongMethodTypeException expected) {
            System.out.println("exact-object-null=WrongMethodTypeException");
        }

        // 3. invoke có thể thích nghi Object -> String, null vẫn hợp lệ:
        String generic = (String) describe.invoke((Object) null);
        require("<null>".equals(generic), "invoke adaptation failed");
        System.out.println("invoke-object-null=OK:" + generic);

        // 4. asType tạo handle mới có chữ ký chính xác (Object)String:
        MethodHandle adapted = describe.asType(
                MethodType.methodType(String.class, Object.class));
        String adjusted = (String) adapted.invokeExact((Object) null);
        require("<null>".equals(adjusted), "asType adaptation failed");
        System.out.println("adapted-exact-null=OK:" + adjusted);

        // 5. Instance method: tham số đầu tiên là String receiver.
        int validLength = (int) length.invokeExact("Java");
        require(validLength == 4, "Unexpected length");
        try {
            int ignored = (int) length.invokeExact((String) null);
            throw new AssertionError("Expected null receiver failure");
        } catch (NullPointerException expected) {
            System.out.println("null-receiver=NullPointerException");
        }

        // 6. Primitive parameter: null Integer cần unbox thành int.
        try {
            int ignored = (int) twice.invoke((Integer) null);
            throw new AssertionError("Expected null unboxing failure");
        } catch (NullPointerException expected) {
            System.out.println("null-unboxing=NullPointerException");
        }

        // 7. Đối tượng MethodHandle null, khác receiver null.
        MethodHandle absent = null;
        try {
            String ignored = (String) absent.invokeExact((String) null);
            throw new AssertionError("Expected null MethodHandle failure");
        } catch (NullPointerException expected) {
            System.out.println("null-handle=NullPointerException");
        }

        System.out.println("PASS");
    }
}
```

Biên dịch và chạy bằng JDK 18 hoặc phiên bản mới hơn:

```bash
javac NullMethodHandleDemo.java
java NullMethodHandleDemo
```

Đầu ra kỳ vọng, không tính chi tiết của stack trace:

```text
reference-null=OK:<null>
exact-object-null=WrongMethodTypeException
invoke-object-null=OK:<null>
adapted-exact-null=OK:<null>
null-receiver=NullPointerException
null-unboxing=NullPointerException
null-handle=NullPointerException
PASS
```

Bài thực hành dùng các phép kiểm tra `require` để không phụ thuộc vào tùy chọn bật Java `assert`. Các nhánh lỗi được bắt theo loại ngoại lệ cụ thể và dùng dữ liệu hoàn toàn cục bộ.

### Vì sao không đo thời gian trong ví dụ này?

Bài học kiểm chứng **hợp đồng kiểu và null**. Thời gian ném ngoại lệ không cho biết lý do kiểu, receiver hay adapter thất bại; một lần chạy có thể bị ảnh hưởng bởi khởi tạo lớp, JIT và tải máy. Hãy xác minh kiểu của handle, cách gọi và loại ngoại lệ trước khi triển khai bất kỳ benchmark riêng nào.

## 7. Bảng chẩn đoán nhanh

| Biểu thức (giả sử có các handle đã tạo ở trên) | Kiểu tại call site | Kết quả kỳ vọng |
| --- | --- | --- |
| `(String) describe.invokeExact((String) null)` | `(String)String` | Thành công, target nhận null |
| `(String) describe.invokeExact((Object) null)` | `(Object)String` | `WrongMethodTypeException` |
| `(String) describe.invoke((Object) null)` | `(Object)String`, có thích nghi | Thành công, chuyển Object null sang String null |
| `(String) describe.invoke((Object) 7)` | `(Object)String`, có thích nghi | `ClassCastException` khi cast Integer thành String |
| `(String) adapted.invokeExact((Object) null)` | `(Object)String`, khớp handle mới | Thành công |
| `(int) length.invokeExact((String) null)` | `(String)int` | `NullPointerException` khi dùng receiver null |
| `(int) length.invokeExact((Object) null)` | `(Object)int` | `WrongMethodTypeException` |
| `(int) twice.invoke((Integer) null)` | `(Integer)int`, cần unboxing | `NullPointerException` khi unbox null |
| `(String) absent.invokeExact((String) null)` khi `absent == null` | Call site khớp theo ví dụ | `NullPointerException` do biến handle null |

Bảng giả định trạng thái ban đầu đúng như chương trình đã cung cấp, các handle không bị thay thế và không có exception khác từ mã người dùng. Một đối tượng handle được tạo bằng `asType` có kiểu riêng; phải kiểm tra `adapted.type()` thay vì tiếp tục dùng kiểu của handle gốc để suy luận.

## 8. Những bẫy thường gặp khi kiểm chứng null

### 8.1. So sánh theo giá trị mà quên kiểu tĩnh

Hai cách ép kiểu khác nhau có thể dẫn đến hai descriptor call site khác nhau dù giá trị runtime giống hệt nhau. Một phép kiểm tra `value == null` không thể thay thế việc xác nhận `MethodHandle.type()`.

### 8.2. Hiểu nhầm mọi `NullPointerException` đều do receiver

Nếu `invoke` cần unbox `Integer` null thành `int`, nó có thể ném `NullPointerException` trước khi chạy target. Nếu target static nhận `String` null rồi tự gọi `value.length()`, NPE đến từ **thân target**, dù không có receiver ở handle. Cần xem stack trace và cấu hình lời gọi để xác định nguồn.

### 8.3. Quên kiểu trả về ở `invokeExact`

`MethodHandle` có kiểu `(String)String` không phù hợp với call site `(String)Object` dù `String` có thể gán sang `Object` ở Java thông thường. Khi dùng `invokeExact`, hãy viết ép kiểu hoặc biến nhận kết quả đúng với kiểu trả về của handle.

### 8.4. Nhầm receiver của target với chính handle

Với `findVirtual`, `length.type()` chứa tham số receiver `String`. Biến `length` phải khác null để thực hiện lời gọi. Receiver null và biến handle null đều có thể ném `NullPointerException`, nhưng là **hai lỗi ở hai tầng khác nhau**.

### 8.5. Dựa vào `invokeWithArguments` để kết luận về `invokeExact`

`invokeWithArguments` là một API có chính sách truyền đối số và thích nghi riêng. Kết quả của nó không chứng minh tính hợp lệ của descriptor tại call site `invokeExact`. Để kiểm chứng kiểu tĩnh, hãy gọi trực tiếp `invokeExact` với ép kiểu rõ ràng và đối chiếu với `type()`.

### 8.6. Bỏ qua nguyên nhân khi thử nghiệm khác biệt quyền truy cập

Nếu `findVirtual` hoặc `findStatic` thất bại ngay lúc tra cứu vì không tìm thấy phương thức hay không đủ quyền, đó là vấn đề khác với truyền null vào một handle hợp lệ. Trong ví dụ, các handle đều trỏ tới phương thức public có thể tra cứu được, giúp cô lập riêng hành vi null.

## 9. Bài tập ứng dụng

**Bài tập 1 — Xác định lỗi trước khi chạy.** Cho `MethodHandle` kiểu `(String)int` đại diện cho `String.length`. Dự đoán và giải thích:

```java
int a = (int) length.invokeExact((String) null);
int b = (int) length.invokeExact((Object) null);
int c = (int) length.invoke((Object) null);
```

*Gợi ý đáp án:* `a` có descriptor đúng nhưng receiver null nên NPE; `b` sai kiểu `Object` so với `String` nên `WrongMethodTypeException`; `c` có thể thích nghi tham số Object null về String null rồi đến bước gọi instance method và ném NPE.

**Bài tập 2 — Null tham chiếu có phải luôn lỗi?** Tạo static method `static String fallback(String text)` trả `"unknown"` khi text null. Tìm handle kiểu `(String)String`; thử `(String) handle.invokeExact((String) null)` và `(String) handle.invoke((Object) null)`. Cả hai có thể thành công vì target chấp nhận null.

**Bài tập 3 — Null unboxing.** Tạo static method `static int square(int x)` và handle kiểu `(int)int`. So sánh `(int) handle.invoke((Integer) null)` với `(int) handle.invokeExact((Integer) null)`. Trường hợp đầu cần unboxing null; trường hợp sau không khớp descriptor. Ghi hai ngoại lệ tương ứng.

**Bài tập 4 — Explicit adaptation.** Với handle gốc `(String)String`, hãy dùng `asType(MethodType.methodType(String.class, Object.class))` để tạo handle `(Object)String`. Thử gọi `invokeExact((Object) null)` và `invokeExact((Object) Integer.valueOf(1))`. Phân biệt nhánh cast null thành công với cast Integer sang String thất bại.

**Bài tập 5 — Đọc log.** Một chương trình có hai dòng `WrongMethodTypeException` và `NullPointerException`. Hãy yêu cầu log in `handle.type()`, mô tả call site bằng kiểu tĩnh trong mã, đánh dấu vị trí receiver và ghi rõ có dùng `invoke`/`invokeExact`/`asType` không. Chỉ sau đó mới kết luận lỗi do kiểu, unboxing, null receiver, null handle hay thân target.

## 10. Ghi nhớ hợp đồng

1. `MethodHandle.type()` mô tả cả kiểu tham số và kiểu trả về; đối với handle gọi instance method, receiver là **tham số đầu tiên**.
2. `invokeExact` đòi kiểu tĩnh tại call site **khớp hoàn toàn** với kiểu handle; `(String) null` và `(Object) null` có thể dẫn đến hai kết quả khác nhau.
3. `null` là giá trị hợp lệ của kiểu tham chiếu. Nếu target cho phép null, lời gọi hoàn toàn có thể thành công.
4. Receiver null ở lời gọi instance method dẫn đến `NullPointerException` khi lời gọi thực sự cần đối tượng; đây là nhánh khác với `WrongMethodTypeException` do sai descriptor.
5. `invoke` và `asType` có thể thích nghi kiểu khi chuyển đổi được hỗ trợ, nhưng chuyển đổi vẫn có thể ném `ClassCastException` hoặc `NullPointerException`.
6. Null ở **biến `MethodHandle`**, null ở **receiver**, và null được **unbox sang primitive** là các nguyên nhân khác nhau, cần quan sát riêng.
7. Khi kiểm chứng trên JDK hiện đại, hãy ghi rõ kiểu handle, kiểu call site, phương thức gọi, giá trị null ở vị trí nào và loại ngoại lệ; không dựa trên chi tiết nội bộ hoặc giả định lỗi thời.

Nắm rõ kiểu tĩnh và vị trí của giá trị null giúp bạn viết phép thử `MethodHandle` có thể tái lập, phân biệt được lỗi kiểu với lỗi receiver và đọc đúng hợp đồng API còn áp dụng trên các JDK được hỗ trợ.
