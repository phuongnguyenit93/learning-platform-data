# Kiểu tĩnh của đối số và phép ép kiểu kết quả quyết định descriptor của invokeExact()

> **Chương:** MethodHandle — **mô-đun:** `JAVA_VERSION_JAVA18`. Bài học kiểm chứng một hợp đồng vẫn áp dụng trên Java 18 và các JDK hiện đại: call site của `MethodHandle.invokeExact()` mang một **symbolic type descriptor** do Java compiler xác định bằng **kiểu tĩnh của mỗi biểu thức đối số** và **kiểu trả về suy từ phép cast/ngữ cảnh dùng kết quả**. Đây là chìa khóa để giải thích `WrongMethodTypeException` mà không dựa vào class nội bộ hay cơ chế legacy.

Hai lời gọi dưới đây có thể cho kết quả khác nhau, dù giá trị runtime đều là chuỗi:

```java
Object value = "hello";
String ok = (String) echo.invokeExact((String) value); // khớp (String)String
String bad = (String) echo.invokeExact(value);         // (Object)String: sai
```

`invokeExact()` không tự suy luận kiểu tham số từ class runtime rồi đổi descriptor. Nó yêu cầu **chính xác** chữ ký đã được gắn vào call site trùng với `MethodHandle.type()`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt kiểu `MethodHandle.type()` với descriptor của từng `invokeExact` call site.
2. Hiểu vì sao đây là phương thức *signature-polymorphic* dù Javadoc hiển thị `Object...`.
3. Suy ra kiểu tham số từ kiểu tĩnh của biểu thức, kể cả `int/Integer/long`, `String/Object` và `null`.
4. Suy ra kiểu trả về từ cast đặt trực tiếp trên lời gọi, expression không cast hoặc statement.
5. Giải thích vì sao gán kết quả sang `Object` không đồng nghĩa caller yêu cầu trả `String`.
6. Dùng `MethodType`, `javap` và ví dụ Java để chứng minh descriptor và `WrongMethodTypeException`.
7. Phân biệt `invokeExact`, `invoke` và adapter `asType` khi cần chuyển kiểu.

## 2. Method type của handle và descriptor của call site

Một `MethodHandle` là tham chiếu thực thi có kiểu. `mh.type()` trả về một `MethodType` gồm danh sách kiểu tham số và kiểu trả về, ví dụ:

```java
MethodType mt = MethodType.methodType(String.class, String.class);
// mt.toString() == "(String)String"
```

Descriptor bytecode tương ứng:

```text
(Ljava/lang/String;)Ljava/lang/String;
```

Với `invokeExact()`, **toàn bộ kiểu** phải khớp:

| `mh.type()` | Call-site descriptor | Kết quả |
|---|---|---|
| `(String)String` | `(String)String` | Khớp, gọi target |
| `(String)String` | `(Object)String` | `WrongMethodTypeException` |
| `(String)String` | `(String)Object` | `WrongMethodTypeException` |
| `(String)String` | `(String)void` | `WrongMethodTypeException` |
| `(int)int` | `(Integer)int` | `WrongMethodTypeException` |
| `(long)long` | `(int)long` | `WrongMethodTypeException` |

Số lượng, thứ tự, từng kiểu tham số **và kiểu trả về** đều quan trọng. Hai kiểu reference có quan hệ kế thừa như `String` và `Object` vẫn không phải cùng một kiểu trong phép so sánh exact. Hai kiểu primitive có thể widening theo Java như `int` và `long` cũng không phải cùng một kiểu.

### 2.1. Chữ ký Java `Object...` không có nghĩa mọi đối số bị đóng gói thành mảng

Javadoc công bố `invokeExact(Object... args) throws Throwable`, nhưng đây là phương thức *signature-polymorphic*. Java compiler có thể biên dịch các lời gọi với mọi số lượng/kiểu tham số hợp lệ ở source và phát `invokevirtual` với **symbolic descriptor riêng**. Nó không sử dụng chữ ký `Object[]` thông thường để buộc mọi call site có cùng một descriptor.

Ví dụ, nếu handle có kiểu `(int)int`:

```java
int answer = (int) mh.invokeExact(21); // call site: (I)I
```

Compiler không tự thực hiện method-invocation conversions tại call site để làm cho descriptor khớp. Chuyển `int → long`, boxing `int → Integer` hay đổi `Object → String` phải được biểu diễn rõ trong source hoặc qua một MethodHandle adapter.

## 3. Quy tắc tham số: kiểu tĩnh, không phải class runtime

Giả sử `echo.type() == (String)String`:

| Biểu thức truyền vào | Kiểu tĩnh ở call site | Có khớp tham số `String`? |
|---|---|---|
| `"abc"` | `String` | Có |
| `String s = "abc"; echo.invokeExact(s)` | `String` | Có |
| `Object o = "abc"; echo.invokeExact(o)` | `Object` | Không |
| `echo.invokeExact((String) o)` | `String` | Có, nếu cast đối số thành công |
| `CharSequence cs = "abc"; echo.invokeExact(cs)` | `CharSequence` | Không |
| `echo.invokeExact(null)` | `java.lang.Void` (đặc biệt) | Không |
| `echo.invokeExact((String) null)` | `String` | Có |

Với hai biến chứa cùng object:

```java
String a = "abc";
Object b = a;
```

`a` và `b` có kiểu tĩnh khác nhau. Compiler phát descriptor từ **biểu thức source**, không tự nhìn vào class runtime của object rồi thay thế `Object` bằng `String`.

### 3.1. Cast đối số khác cast kết quả

```java
String bad = (String) echo.invokeExact(b);
String good = (String) echo.invokeExact((String) b);
```

Cast ngoài cùng ở dòng đầu xác định **kiểu trả về `String`**, nhưng kiểu tham số vẫn là `Object`. Ở dòng thứ hai, cast trên `b` làm tham số có kiểu tĩnh `String`; cast ngoài cùng làm kiểu trả về `String`. Descriptor từ đó khớp `(String)String`.

Nếu `b` thực tế không chứa chuỗi, `(String) b` có thể ném `ClassCastException` trước khi handle chạy. Khớp descriptor không có nghĩa bỏ qua hợp đồng dữ liệu.

### 3.2. Primitive: không có tự widening hoặc boxing

Với handle `(long)long`:

```java
long good = (long) longHandle.invokeExact(1L);
long bad  = (long) longHandle.invokeExact(1);
```

Literal `1L` có kiểu `long`; literal `1` có kiểu `int`. `invokeExact` không tự widening như lời gọi method Java thông thường. Tương tự, biến `Integer boxed` sẽ tạo tham số `Integer`, không phải `int`, trừ khi dùng `boxed.intValue()` hoặc biểu thức `int` tương đương.

## 4. Quy tắc kiểu trả về: cast, expression và statement

Theo `MethodHandle` Javadoc, compiler xác định **return type của call-site descriptor** như sau:

1. Có **cast trực tiếp trên biểu thức `invokeExact`**: dùng kiểu được cast (kể cả primitive, nhưng không phải `void`).
2. Lời gọi là **biểu thức** mà không có cast trực tiếp: dùng `Object`.
3. Lời gọi là **expression statement** độc lập: dùng `void`.

Giả sử `echo.type() == (String)String`:

| Cách viết | Return type của call site | Kết quả |
|---|---|---|
| `String s = (String) echo.invokeExact("x");` | `String` | Khớp |
| `Object o = (String) echo.invokeExact("x");` | `String` | Khớp, gán rộng sau lời gọi |
| `Object o = echo.invokeExact("x");` | `Object` | Sai |
| `Object o = (Object) echo.invokeExact("x");` | `Object` | Sai |
| `echo.invokeExact("x");` | `void` | Sai |

**Không được suy diễn return type của descriptor từ kiểu biến nhận kết quả.** Biến `Object o` có thể nhận chuỗi một cách bình thường trong Java, nhưng `Object o = echo.invokeExact("x")` yêu cầu handle có kiểu trả về **`Object`** ở call site. Nếu handle thực sự trả `String`, `invokeExact` ném `WrongMethodTypeException`.

### 4.1. Cast gần lời gọi nhất quyết định kiểu trả về

```java
Object ok = (String) echo.invokeExact("abc");
String bad = (String) (Object) echo.invokeExact("abc");
```

Ở dòng đầu, call site trả `String` và phép gán lên `Object` xảy ra sau. Ở dòng hai, **cast gần lời gọi nhất** là `(Object)`; descriptor yêu cầu return `Object` và không khớp với handle trả `String`. Cast `(String)` ngoài cùng không thể sửa mismatch đã phát sinh.

### 4.2. Cast primitive đặt tại call site khác widening sau lời gọi

Giả sử `twice.type() == (int)int`:

```java
int good  = (int) twice.invokeExact(5);   // (int)int: đúng
long also = (int) twice.invokeExact(5);   // (int)int rồi widening sang long
long bad  = (long) twice.invokeExact(5);  // (int)long: sai
```

Dòng cuối yêu cầu handle **trả `long`**, không có nghĩa “gọi handle trả `int` và đổi kết quả sau”.

### 4.3. Bỏ kết quả là yêu cầu kiểu `void`

```java
twice.invokeExact(5); // call site (int)void: sai nếu handle trả int
```

Lời gọi đứng một mình là *statement*, nên descriptor return là `void`. Ngược lại, với handle có kiểu `(String)void`:

```java
announce.invokeExact("ready"); // đúng
```

Bạn không thể viết cast `(void)` trong Java. Nếu cần bỏ kết quả từ handle trả giá trị, hãy nhận nó bằng cast đúng rồi không sử dụng biến, hoặc cân nhắc một adapter có kiểu trả về `void` phù hợp.

## 5. Lab tự chứa: kiểm tra các descriptor thực tế

Tạo `InvokeExactDescriptorLab.java` và chạy với JDK 18 trở lên. Chương trình chủ động bắt các mismatch để tiếp tục kiểm thử tất cả trường hợp.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class InvokeExactDescriptorLab {

    public static int twice(int value) {
        return value * 2;
    }

    public static String echo(String value) {
        return value == null ? "<null>" : value;
    }

    public static long next(long value) {
        return value + 1L;
    }

    public static void announce(String value) {
        System.out.println("ANNOUNCE: " + value);
    }

    @FunctionalInterface
    interface CheckedCall {
        void run() throws Throwable;
    }

    private static void expectWrong(String label, CheckedCall call)
            throws Throwable {
        try {
            call.run();
        } catch (WrongMethodTypeException expected) {
            System.out.println("WRONG: " + label);
            return;
        }
        throw new AssertionError(
                "Phải nhận WrongMethodTypeException: " + label);
    }

    public static void main(String[] args) throws Throwable {
        var lookup = MethodHandles.lookup();

        MethodHandle twiceHandle = lookup.findStatic(
                InvokeExactDescriptorLab.class,
                "twice", MethodType.methodType(int.class, int.class));

        MethodHandle echoHandle = lookup.findStatic(
                InvokeExactDescriptorLab.class,
                "echo", MethodType.methodType(String.class, String.class));

        MethodHandle nextHandle = lookup.findStatic(
                InvokeExactDescriptorLab.class,
                "next", MethodType.methodType(long.class, long.class));

        MethodHandle announceHandle = lookup.findStatic(
                InvokeExactDescriptorLab.class,
                "announce", MethodType.methodType(void.class, String.class));

        MethodHandle substring = lookup.findVirtual(
                String.class, "substring",
                MethodType.methodType(String.class, int.class));

        System.out.println("twice.type() = " + twiceHandle.type());
        System.out.println("echo.type() = " + echoHandle.type());
        System.out.println("twice descriptor = " +
                twiceHandle.type().toMethodDescriptorString());

        // A. Trùng cả kiểu đối số lẫn kết quả: (int)int.
        int answer = (int) twiceHandle.invokeExact(21);
        System.out.println("twice(21) = " + answer);

        // B. Integer không phải int trong descriptor.
        Integer boxed = 21;
        expectWrong("Integer đối số", () -> {
            int ignored = (int) twiceHandle.invokeExact(boxed);
        });
        int unboxed = (int) twiceHandle.invokeExact(boxed.intValue());
        System.out.println("unboxed = " + unboxed);

        // C. Return type Object hay long khác int.
        expectWrong("Object kết quả", () -> {
            Object ignored = twiceHandle.invokeExact(21);
        });
        expectWrong("long kết quả", () -> {
            long ignored = (long) twiceHandle.invokeExact(21);
        });
        long afterWidening = (int) twiceHandle.invokeExact(21);
        System.out.println("afterWidening = " + afterWidening);

        // D. Lời gọi đứng riêng yêu cầu return void.
        expectWrong("statement nhưng target trả int", () -> {
            twiceHandle.invokeExact(21);
        });

        // E. Kiểu tĩnh của tham số reference.
        Object text = "hello";
        expectWrong("Object đối số thay vì String", () -> {
            String ignored = (String) echoHandle.invokeExact(text);
        });
        String correct = (String) echoHandle.invokeExact((String) text);
        System.out.println("echo = " + correct);

        // F. Không cast result => Object; cast String => String.
        expectWrong("thiếu cast kết quả", () -> {
            Object ignored = echoHandle.invokeExact("ok");
        });
        Object widenedObject = (String) echoHandle.invokeExact("ok");
        System.out.println("widenedObject = " + widenedObject);

        expectWrong("cast gần lời gọi là Object", () -> {
            String ignored = (String) (Object)
                    echoHandle.invokeExact("ok");
        });

        // G. Literal null không cast có descriptor Void.
        expectWrong("null không cast", () -> {
            String ignored = (String) echoHandle.invokeExact(null);
        });
        String nullValue = (String)
                echoHandle.invokeExact((String) null);
        System.out.println("castNull = " + nullValue);

        // H. Không tự widening int -> long.
        expectWrong("int đối số thay vì long", () -> {
            long ignored = (long) nextHandle.invokeExact(10);
        });
        long next = (long) nextHandle.invokeExact(10L);
        System.out.println("next = " + next);

        // I. Handle trả void cần statement.
        announceHandle.invokeExact("ready");
        expectWrong("Object result nhưng handle trả void", () -> {
            Object ignored = announceHandle.invokeExact("ready");
        });

        // J. findVirtual thêm receiver làm tham số đầu.
        String suffix = (String) substring.invokeExact("abcdef", 2);
        System.out.println("suffix = " + suffix);

        CharSequence receiver = "abcdef";
        expectWrong("CharSequence receiver thay vì String", () -> {
            String ignored = (String)
                    substring.invokeExact(receiver, 2);
        });
        String fixedReceiver = (String)
                substring.invokeExact((String) receiver, 2);
        System.out.println("fixedReceiver = " + fixedReceiver);
    }
}
```

Chạy bằng Java source-file mode:

```text
java InvokeExactDescriptorLab.java
```

Kết quả rút gọn:

```text
twice.type() = (int)int
echo.type() = (String)String
twice descriptor = (I)I
twice(21) = 42
WRONG: Integer đối số
unboxed = 42
WRONG: Object kết quả
WRONG: long kết quả
afterWidening = 42
WRONG: statement nhưng target trả int
WRONG: Object đối số thay vì String
echo = hello
WRONG: thiếu cast kết quả
widenedObject = ok
WRONG: cast gần lời gọi là Object
WRONG: null không cast
castNull = <null>
WRONG: int đối số thay vì long
next = 11
ANNOUNCE: ready
WRONG: Object result nhưng handle trả void
suffix = cdef
WRONG: CharSequence receiver thay vì String
fixedReceiver = cdef
```

Các dòng lỗi là kết quả dự kiến của `expectWrong`; đây không phải lỗi ngẫu nhiên do môi trường. Mọi trường hợp đều cho thấy type tại call site không khớp `MethodHandle.type()`.

## 6. Đọc chính xác từng cặp lỗi

### 6.1. Mismatch ở tham số

```java
Object input = "abc";

// Call site (Object)String: WrongMethodTypeException.
String wrong = (String) echoHandle.invokeExact(input);

// Call site (String)String: đúng.
String correct = (String) echoHandle.invokeExact((String) input);
```

Cast trên **kết quả** không sửa kiểu **đối số**. Với `Integer` truyền vào handle nhận `int`, dùng `boxed.intValue()` khi cần primitive. Với `long`, dùng literal `10L` hoặc cast đối số sang `long`.

### 6.2. Mismatch ở kết quả

```java
// Giả sử echoHandle.type() == (String)String.
Object wrong = echoHandle.invokeExact("x");          // return Object
Object ok = (String) echoHandle.invokeExact("x");    // return String

// Cast gần nhất là Object, nên vẫn WRONG:
String wrongNested =
        (String) (Object) echoHandle.invokeExact("x");
```

Những dòng `wrong` là ví dụ độc lập cố ý ném exception; không chạy chúng liền nhau mà không bắt lỗi.

### 6.3. Mismatch vì bỏ kết quả

```java
// Giả sử twiceHandle.type() == (int)int.
twiceHandle.invokeExact(7);                // (I)V: WRONG
int result = (int) twiceHandle.invokeExact(7); // (I)I: đúng
```

Nếu method đích là `void`, lời gọi dạng statement lại chính xác.

### 6.4. Literal null là trường hợp đặc biệt

`MethodHandle` Javadoc nêu rằng một đối số `null` không cast được ghi ký hiệu bằng kiểu `java.lang.Void` trong descriptor. `Void` ở đây không phải object được truyền thực tế.

```java
// Giả sử echoHandle.type() == (String)String.
String wrong = (String) echoHandle.invokeExact(null);
String correct = (String) echoHandle.invokeExact((String) null);
```

Cast chỉ sửa descriptor. Target vẫn có thể từ chối `null` bằng `NullPointerException` hoặc xử lý nó hợp lệ tùy contract.

## 7. Receiver của `findVirtual` cũng là tham số có kiểu tĩnh

Khi tạo handle tới instance method, receiver nằm trong `MethodHandle.type()` với tư cách tham số đầu.

```java
MethodHandle substring = MethodHandles.lookup().findVirtual(
        String.class, "substring",
        MethodType.methodType(String.class, int.class));
```

Kiểu thực tế là:

```text
(String,int)String
```

không phải `(int)String` như chữ ký source của `String.substring(int)` có thể khiến bạn tưởng.

```java
String result = (String) substring.invokeExact("abcdef", 2);

CharSequence receiver = "abcdef";
String wrong = (String) substring.invokeExact(receiver, 2);
String fixed = (String) substring.invokeExact((String) receiver, 2);
```

`wrong` yêu cầu call site `(CharSequence,int)String` và mismatch; `fixed` có `(String,int)String`. Với `bindTo`, bạn có thể tạo handle mới đã gắn receiver; `type()` của handle mới sẽ không còn tham số receiver đứng đầu. Kiểm tra lại `type()` sau mọi bước tạo adapter.

## 8. `invokeExact()`, `invoke()` và `asType()` khác nhau thế nào?

| API | Quy tắc | Khi nào chọn |
|---|---|---|
| `mh.invokeExact(args)` | Call-site descriptor phải bằng `mh.type()` | Code đã biết signature chính xác |
| `mh.invoke(args)` | Nếu mismatch, có thể thích nghi như gọi `mh.asType(callSiteType)` | Khi cần chuyển đổi hợp lệ |
| `mh.asType(newType)` | Tạo handle **mới** có kiểu `newType` với bộ chuyển đổi | Muốn chuẩn hóa signature tại ranh giới adapter |
| `mh.invokeWithArguments(...)` | Nhận đối số động, thường qua `Object`/danh sách | Công cụ hoặc framework thực sự cần lời gọi động |

`invoke()` không tự thực hiện **mọi** chuyển đổi mong muốn. Nếu `asType` không thích nghi được, lời gọi có thể gây `WrongMethodTypeException`; một phép cast/unbox lúc thực thi cũng có thể thất bại theo contract.

### 8.1. Ví dụ adapter chuyển `Integer → int` và `int → long`

Giả sử `twiceHandle.type() == (int)int`:

```java
MethodHandle adapted = twiceHandle.asType(
        MethodType.methodType(long.class, Integer.class));

System.out.println(adapted.type()); // (Integer)long

Integer boxed = 20;
long answer = (long) adapted.invokeExact(boxed); // 40
```

`asType` tạo handle thích nghi từ `(int)int` sang `(Integer)long`: unbox tham số và widen kết quả theo luật được hỗ trợ. **`adapted.invokeExact` vẫn là exact** vì call site đã khớp kiểu của *adapter*, không phải vì `invokeExact` tự chuyển đổi.

Một lời gọi inexact tương đương về ý tưởng:

```java
Integer boxed = 20;
long answer = (long) twiceHandle.invoke(boxed);
```

`invoke` yêu cầu call-site type `(Integer)long`, sau đó có thể thích nghi với `(int)int`. Đừng thay `invokeExact` bằng `invoke` chỉ để che lỗi thiết kế khi một interface thực ra đã yêu cầu kiểu cố định.

## 9. Chứng minh descriptor trong bytecode bằng `javap`

Compiler ghi `invokevirtual` riêng với symbolic descriptor xác định tại từng lời gọi. Dùng một class nhỏ để kiểm tra thay vì suy đoán từ stack trace.

Tạo `DescriptorBytecode.java`:

```java
import java.lang.invoke.MethodHandle;

public class DescriptorBytecode {
    public static int exactInt(MethodHandle handle) throws Throwable {
        return (int) handle.invokeExact(10);
    }

    public static Object exactObject(MethodHandle handle) throws Throwable {
        return (Object) handle.invokeExact(10);
    }

    public static void exactVoid(MethodHandle handle) throws Throwable {
        handle.invokeExact(10);
    }
}
```

Biên dịch và xem bytecode:

```text
javac DescriptorBytecode.java
javap -c -v DescriptorBytecode
```

Tìm `java/lang/invoke/MethodHandle.invokeExact` và đọc descriptor của `invokevirtual`:

| Method | Call-site descriptor |
|---|---|
| `exactInt` | `(I)I` |
| `exactObject` | `(I)Ljava/lang/Object;` |
| `exactVoid` | `(I)V` |

Cả ba method **biên dịch được**, vì `invokeExact` là signature-polymorphic. Nhưng nếu caller truyền handle có kiểu `(int)int`, chỉ `exactInt` khớp. Khi chạy các method khác, JVM báo `WrongMethodTypeException`.

Các chỉ số constant pool/offset có thể thay đổi giữa compiler và JDK build; chỉ dựa vào descriptor, không hard-code vị trí bytecode.

## 10. Phân biệt mismatch với lỗi của method đích

| Lỗi | Bối cảnh | Hướng xử lý |
|---|---|---|
| `WrongMethodTypeException` | Descriptor gọi sai `mh.type()` | Kiểm tra kiểu tĩnh và cast kết quả |
| `ClassCastException` trong cast đối số | Giá trị runtime không đổi được sang kiểu ép | Validate input tại ranh giới trước khi gọi |
| `NullPointerException` từ target | Target không chấp nhận null dù call site exact | Xem contract nghiệp vụ của target |
| `Throwable` từ target | Method đích đã chạy và ném lỗi | Bảo toàn ngoại lệ gốc; `invokeExact` không tự bọc kiểu `InvocationTargetException` như Core Reflection |
| `IllegalAccessException` từ `Lookup.findStatic`/`findVirtual` | Không có quyền tạo handle | Kiểm tra member visibility, lookup context và JPMS |
| Mismatch khi dùng `invoke()` | `asType` không thể thích nghi call-site type | Dùng conversion/adapter được hỗ trợ |

`invokeExact` và `invoke` khai báo `throws Throwable`. Method chứa lời gọi phải khai báo `throws Throwable` hoặc bắt và xử lý `Throwable` theo hợp đồng. Đừng bắt rồi nuốt `WrongMethodTypeException` để tự thử các cast ngẫu nhiên, vì lỗi thường nằm ở thiết kế signature.

Để chẩn đoán, ghi `handle.type()`, đoạn source tại call site và khi cần `javap -c -v`. Không suy ra kiểu tĩnh chỉ từ `arg.getClass()`.

## 11. Checklist sửa lỗi cho dự án thực tế

1. **In kiểu handle:** `mh.type()` và `mh.type().toMethodDescriptorString()`.
2. **Đếm tham số:** số lượng và thứ tự phải khớp; nhớ receiver của `findVirtual`.
3. **Đọc kiểu tĩnh từng argument:** phân biệt `Object/String`, `Integer/int`, `int/long` và literal `null`.
4. **Tìm cast trên từng argument:** cast có chuyển đúng kiểu biểu thức không? Có thể ném `ClassCastException` trước khi invoke không?
5. **Kiểm tra return:** cast nào gần biểu thức `invokeExact` nhất? Nếu không cast, nó là expression (Object) hay statement (void)?
6. **Đối chiếu toàn bộ descriptor:** cả parameter list và return type đều phải đúng `mh.type()`.
7. **Quyết định adapter:** nếu cần chuyển đổi thật, cân nhắc `asType` hay `invoke` thay vì ép kiểu tùy tiện.
8. **Viết test cặp dương/âm:** một call site đúng và các biến thể mismatch có chủ đích.
9. **Kiểm tra bytecode khi cần:** `javap -c -v` giúp xác nhận kiểu compiler đã phát.
10. **Không dựa vào implementation internals:** hợp đồng `MethodHandle` vẫn ổn định trên JDK hiện đại; debug dựa vào API công khai, không vào class/stack frame nội bộ.

Trong ứng dụng cần xử lý đối số động lấy từ map hoặc framework context, có thể gom logic gọi handle vào một adapter nhỏ, kiểm tra kiểu và thực hiện conversions có chủ đích. Đừng rải `invokeExact` với biến `Object` ở nhiều nơi rồi thử-cast cho tới khi hết lỗi.

## 12. Bài tập tự kiểm tra

1. `MethodHandle.type()` mô tả những kiểu gì?
2. Vì sao biến `Object x = "abc"` tạo descriptor khác biến `String x = "abc"`?
3. Với handle `(String)String`, descriptor return của `Object x = h.invokeExact("x")` là gì?
4. Vì sao `Object x = (String) h.invokeExact("x")` có thể chạy, trong khi `Object x = (Object) h.invokeExact("x")` sai?
5. Trong `(String) (Object) h.invokeExact("x")`, cast nào quyết định descriptor?
6. Với handle `(int)int`, vì sao `long x = (int) h.invokeExact(1)` đúng nhưng `long x = (long) h.invokeExact(1)` sai?
7. Với handle `(String)void`, lời gọi dạng statement có gì khác lời gọi dùng như expression?
8. Với handle `(long)long`, literal `1` và `1L` khác nhau ở call site thế nào?
9. Vì sao `null` không cast có kiểu descriptor `Void`, và làm sao truyền null typed `String`?
10. `findVirtual` thay đổi tham số đầu của handle so với chữ ký method source thế nào?
11. `invokeExact` khác `invoke` ở yêu cầu khớp kiểu và chuyển đổi thế nào?
12. Vì sao `asType` không làm `invokeExact` trở thành inexact?
13. Dùng `javap` thế nào để xác nhận một call site gửi `(I)I` hay `(I)V`?
14. Vì sao `WrongMethodTypeException` thường xuất hiện trước khi method đích chạy?

**Tiêu chí hoàn thành:** Bạn có thể nhìn một lời gọi `invokeExact()` và tự suy ra symbolic descriptor từ các kiểu tĩnh và cast, đối chiếu đúng với `mh.type()`, giải thích `WrongMethodTypeException` và chọn giải pháp có chủ đích.

## 13. Tài liệu chuẩn

- [MethodHandle — Java SE 18 API](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/invoke/MethodHandle.html): phần *Method handle compilation*, signature polymorphism và descriptor.
- [MethodHandle — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html): quy tắc kiểu tĩnh, cast/Object/void, trường hợp null và `WrongMethodTypeException`.
- [MethodType — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodType.html): kiểu phương thức bất biến và descriptor string.
- [MethodHandles.Lookup — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findStatic`, `findVirtual` và kiểm tra quyền khi tạo handle.
- [WrongMethodTypeException — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html): lỗi do descriptor không phù hợp.
- [Java Virtual Machine Specification, mục 4.3.3 — Method Descriptors](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html#jvms-4.3.3): cú pháp descriptor `(I)I`, `(Ljava/lang/String;)Ljava/lang/String;` và `V`.
- [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): ngữ cảnh Java 18 và cách phân biệt implementation Core Reflection với hợp đồng riêng của MethodHandle.

