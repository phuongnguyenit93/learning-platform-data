# bindTo() và insertArguments(): cố định receiver hoặc tham số theo đúng vị trí và kiểu

## 1. Mục tiêu: cố định đối số mà không làm sai chữ ký MethodHandle

Trong module **JAVA_VERSION_JAVA18**, chương **Lookup và adapter** hướng dẫn cách tạo, biến đổi và gọi `MethodHandle` trên JDK hiện đại. Bài này tập trung vào hai adapter vẫn được dùng rộng rãi:

- `MethodHandle.bindTo(Object value)`: cố định **tham số tham chiếu đầu tiên** của một method handle.
- `MethodHandles.insertArguments(MethodHandle target, int pos, Object... values)`: cố định một hoặc nhiều tham số **liên tiếp bắt đầu tại vị trí được chỉ định**, kể cả tham số primitive khi giá trị tương thích.

Một cách hiểu cốt lõi:

> Adapter tạo ra **method handle mới** có một số đối số đã được lưu sẵn. Khi gọi handle mới, caller chỉ truyền các đối số **chưa được cố định**.

Bài thuộc chương về lookup và adapter, không phải mẹo tối ưu phụ thuộc vào một phiên bản triển khai JDK. Trong Java 18 và các JDK hiện đại, việc đọc chính xác `MethodType` trước/sau adapter là hợp đồng quan trọng hơn mọi suy đoán về chi phí nano-giây.

Sau bài này, bạn có thể:

1. Đọc chữ ký handle bằng `type()`, phân biệt receiver của instance method với các tham số nghiệp vụ.
2. Dùng `bindTo` để giữ receiver, đồng thời hiểu nó cũng có thể giữ **tham số đầu tiên không phải receiver** nếu đó là reference type.
3. Dùng `insertArguments` với đúng vị trí `pos`, đúng số lượng và đúng kiểu các giá trị bị giữ.
4. Tính lại thứ tự chỉ số sau từng bước bind, tránh cố định nhầm tham số.
5. Gọi `invokeExact` với chữ ký chính xác; nhận diện lỗi kiểu và giới hạn với primitive, mảng, varargs, `null`.
6. Thiết kế test chứng minh kết quả, `MethodType`, và sự độc lập giữa handle gốc và handle đã adapter.

## 2. MethodType là hợp đồng của mỗi handle

### 2.1. Phương thức instance có receiver tường minh trong MethodHandle

Giả sử:

```java
public final class Formatter {
    public String render(int times, String word) {
        return word.repeat(times);
    }
}
```

Dùng lookup:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle render = lookup.findVirtual(
        Formatter.class,
        "render",
        MethodType.methodType(String.class, int.class, String.class));
```

Chữ ký `MethodType` truyền vào `findVirtual` mô tả **tham số đã khai báo trong method Java**, không gồm receiver. Nhưng handle trả về có kiểu:

```text
(Formatter, int, String)String
    ^         ^      ^       ^
    |         |      |       |
 receiver   times   word   return type
```

Trong một `MethodHandle` lấy bằng `findVirtual`, receiver là **tham số đầu tiên của handle**. Khi gọi handle chưa bind, phải truyền receiver tường minh:

```java
Formatter f = new Formatter();
String result = (String) render.invokeExact(f, 2, "ab"); // "abab"
```

Điều này khác cú pháp Java bình thường `f.render(2, "ab")`, nơi receiver đứng trước dấu chấm và không xuất hiện trong danh sách đối số của method.

### 2.2. Phương thức static không có receiver

Với:

```java
public static String label(String marker, int n, String value) {
    return marker + ":" + n + ":" + value;
}
```

Handle tạo bởi:

```java
MethodHandle label = lookup.findStatic(
        Example.class, "label",
        MethodType.methodType(
                String.class, String.class, int.class, String.class));
```

có kiểu:

```text
(String, int, String)String
  pos0    pos1   pos2      return
```

Ở đây vị trí `0` là tham số nghiệp vụ `marker`, **không phải receiver**. `bindTo("X")` vẫn có thể cố định vị trí `0` của handle này, vì đó là reference type. Do đó không nên dịch `bindTo` thành “luôn bind receiver”; nói chính xác hơn là “bind đối số reference **đầu tiên**”.

### 2.3. Xem chữ ký thực tế trước khi adapter

```java
MethodType before = render.type();
System.out.println(before);             // (Formatter,int,String)String
System.out.println(before.parameterCount());  // 3
System.out.println(before.parameterType(0));  // class Formatter
System.out.println(before.returnType());      // class java.lang.String
```

`MethodType` là bất biến. Adapter tạo một handle mới với `MethodType` mới; `render.type()` của handle gốc không bị sửa.

Nếu logic phụ thuộc vào index `pos`, hãy luôn đối chiếu `target.type().parameterType(pos)` với kiểu mong muốn. Index là **zero-based trên chính handle đang được adapter**, không phải thứ tự tham số của method Java ban đầu hay thứ tự giá trị bạn vừa truyền trong lời gọi Java thông thường.

## 3. bindTo(): giữ tham số tham chiếu đầu tiên

### 3.1. Ví dụ điển hình: giữ receiver của instance method

```java
Formatter receiver = new Formatter();

MethodHandle original = lookup.findVirtual(
        Formatter.class, "render",
        MethodType.methodType(String.class, int.class, String.class));

MethodHandle boundReceiver = original.bindTo(receiver);
```

Kiểu trước và sau:

```text
original      : (Formatter, int, String)String
boundReceiver : (           int, String)String
```

Caller không truyền receiver lần nữa:

```java
String text = (String) boundReceiver.invokeExact(3, "ha");
// "hahaha"
```

`boundReceiver` giữ **tham chiếu đến object receiver**. Nó không tạo bản sao object; nếu receiver có trạng thái mutable, các lần gọi sau có thể thấy trạng thái đã thay đổi. Khi giữ receiver trong cache có vòng đời dài, hãy cân nhắc nguy cơ giữ object và class loader không còn cần thiết.

### 3.2. Không có phép tìm overload hay đổi method đích

`bindTo(receiver)` không gọi lại `findVirtual`. Nó không tự nhìn kiểu runtime receiver rồi chọn một overload khác. Nó chỉ tạo adapter cho handle đã chọn và giữ đối số đầu tiên.

Nếu method đã chọn là `render(int, String)`, bind receiver vẫn giữ nguyên phương thức này. Dispatch override ở runtime của virtual method vẫn tuân theo semantics của JVM cho virtual invocation; bind không biến nó thành một lời gọi static mới tới implementation tùy ý.

### 3.3. Tham số đầu tiên là reference type — không bắt buộc là receiver

```java
MethodHandle label = lookup.findStatic(
        Example.class, "label",
        MethodType.methodType(
                String.class, String.class, int.class, String.class));

// MethodHandle label: (String,int,String)String
MethodHandle marked = label.bindTo("TAG");

// MethodHandle marked: (int,String)String
String output = (String) marked.invokeExact(7, "ok");
// "TAG:7:ok"
```

`bindTo` có thể bind tham số `String marker` của static method vì kiểu của tham số đầu tiên là reference. **Không có receiver nào** trong ví dụ này.

### 3.4. Không bind được tham số primitive đứng đầu bằng bindTo

Giả sử `add(int, int)` có handle kiểu `(int,int)int`:

```java
MethodHandle add = lookup.findStatic(
        Example.class, "add",
        MethodType.methodType(int.class, int.class, int.class));

// Không dùng:
add.bindTo(Integer.valueOf(5)); // IllegalArgumentException
```

`bindTo(Object)` chỉ dành cho **leading reference parameter**. Nó không tự unbox để bind một tham số primitive đứng đầu. Cách phù hợp ở đây là `MethodHandles.insertArguments(add, 0, Integer.valueOf(5))`.

### 3.5. bindTo(null): phân biệt reference hợp lệ và yêu cầu receiver

Với một handle có leading reference parameter, giá trị `null` có thể được cố định vào tham số đó. Điều này **không** đảm bảo lúc invoke thành công:

- Nếu tham số là dữ liệu nullable và method biết xử lý `null`, lời gọi có thể thành công.
- Nếu tham số là receiver của một instance method, việc gọi method thông qua receiver `null` thường phát sinh `NullPointerException` khi thực thi.

Do đó, cần tách **bind có đúng kiểu tham chiếu** và **method sau bind có thể thực thi đúng logic**. Nếu API không cho phép receiver null, kiểm tra `Objects.requireNonNull(receiver)` trước khi bind giúp báo lỗi tại nơi tạo handle.

## 4. insertArguments(): cố định theo vị trí và kiểu

### 4.1. Chữ ký adapter

```java
MethodHandle partial = MethodHandles.insertArguments(
        target, pos, value0, value1 /*, ... */);
```

Trong đó:

- `target` là handle đang xét, **không nhất thiết là handle gốc**.
- `pos` là **vị trí tham số đầu tiên cần cố định**, tính từ `0` trên `target.type()`.
- `values` là các giá trị cố định vào các vị trí `pos`, `pos + 1`, ... **liên tiếp**.
- Handle mới loại các vị trí đã cố định khỏi danh sách tham số. **Thứ tự tương đối của các tham số còn lại không đổi**.

Ví dụ:

```text
target: (Formatter, int, String)String
index:       0       1     2

insertArguments(target, 1, 3)
             giữ times=3
result: (Formatter, String)String
index:        0       1
```

Ở đây chỉ số `1` của handle mới là tham số `String`, không còn là `int` như handle cũ.

### 4.2. Cố định primitive ở vị trí bất kỳ

```java
MethodHandle repeatThree = MethodHandles.insertArguments(
        original, 1, Integer.valueOf(3));

// repeatThree: (Formatter,String)String
String text = (String) repeatThree.invokeExact(receiver, "ha");
// "hahaha"
```

`insertArguments` hỗ trợ binding primitive qua các giá trị boxed tương thích, theo quy tắc chuyển đổi mà API chấp nhận. Để code dễ kiểm chứng, truyền wrapper **đúng** kiểu của primitive cần bind, ví dụ `Integer.valueOf(3)` cho `int`, `Long.valueOf(3L)` cho `long`, thay vì trông chờ chuyển đổi ngầm từ một wrapper khác.

### 4.3. Cố định cả receiver và tham số kế tiếp

```java
MethodHandle fixedTwo = MethodHandles.insertArguments(
        original, 0, receiver, Integer.valueOf(2));

// fixedTwo: (String)String
String result = (String) fixedTwo.invokeExact("ab");
// "abab"
```

Các giá trị `receiver` và `Integer.valueOf(2)` được bind vào hai tham số **kề nhau** ở index `0` và `1`. Khi muốn bind vị trí không liên tiếp, thực hiện nhiều adapter theo thứ tự tính toán lại index.

### 4.4. Cố định một tham số không phải leading parameter

```java
MethodHandle fixedWord = MethodHandles.insertArguments(
        original, 2, "ha");

// fixedWord: (Formatter,int)String
String result = (String) fixedWord.invokeExact(receiver, 3);
// "hahaha"
```

`bindTo("ha")` không thể thay thế trường hợp này vì `bindTo` luôn nhìn **tham số đầu tiên**. `insertArguments` là lựa chọn tự nhiên khi bạn biết vị trí tham số muốn giữ.

### 4.5. Điều kiện vị trí và số lượng giá trị

Với target có `N` tham số và `K` giá trị cần bind, phạm vi hợp lệ phải thỏa:

```text
0 <= pos
pos + K <= N
```

Ví dụ handle có ba tham số, bind hai giá trị ở `pos = 2` là vượt danh sách; `insertArguments` sẽ báo `IllegalArgumentException`. Khi kiểu giá trị không tương thích với formal parameter ở vị trí tương ứng, việc tạo adapter cũng thất bại thay vì âm thầm chọn một overload khác.

Với source code dùng `MethodHandles.insertArguments`, kiểu `Object...` của tham số `values` chỉ là cơ chế truyền danh sách các giá trị cố định, **không thay đổi** `MethodType` của target hay định nghĩa “tham số liên tiếp”.

## 5. Chương trình đầy đủ: bind receiver, primitive, nhiều tham số và mảng

Lưu chương trình sau thành `BoundArgumentsLab.java` bằng UTF-8. Đây là ví dụ có thể chạy với JDK 18 hoặc mới hơn, chỉ sử dụng API chuẩn `java.lang.invoke`, không cần thư viện ngoài.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public final class BoundArgumentsLab {
    public static final class Formatter {
        private final String prefix;

        public Formatter(String prefix) {
            this.prefix = prefix;
        }

        public String render(int count, String word) {
            return prefix + word.repeat(count);
        }
    }

    public static String label(String marker, int n, String text) {
        return marker + ":" + n + ":" + text;
    }

    public static int add(int left, int right) {
        return left + right;
    }

    public static String nullable(String value) {
        return value == null ? "NULL" : "VALUE:" + value;
    }

    public static String join(String heading, String... parts) {
        return heading + ":" + String.join(",", parts);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        Formatter receiver = new Formatter(">");

        // 1. findVirtual trả handle có receiver ở vị trí 0.
        MethodHandle render = lookup.findVirtual(
                Formatter.class,
                "render",
                MethodType.methodType(
                        String.class, int.class, String.class));

        requireType(render, MethodType.methodType(
                String.class, Formatter.class, int.class, String.class));

        // 2. bindTo giữ receiver.
        MethodHandle boundReceiver = render.bindTo(receiver);
        requireType(boundReceiver, MethodType.methodType(
                String.class, int.class, String.class));
        require("BOUND_RECEIVER", ">hahaha",
                (String) boundReceiver.invokeExact(3, "ha"));

        // 3. insertArguments ở pos=0 giữ cùng receiver.
        MethodHandle viaInsert = MethodHandles.insertArguments(
                render, 0, receiver);
        requireType(viaInsert, MethodType.methodType(
                String.class, int.class, String.class));
        require("INSERT_RECEIVER", ">abab",
                (String) viaInsert.invokeExact(2, "ab"));

        // 4. Giữ tham số primitive count ở vị trí 1 của render.
        MethodHandle fixedCount = MethodHandles.insertArguments(
                render, 1, Integer.valueOf(2));
        requireType(fixedCount, MethodType.methodType(
                String.class, Formatter.class, String.class));
        require("INSERT_PRIMITIVE", ">xyxy",
                (String) fixedCount.invokeExact(receiver, "xy"));

        // 5. Giữ tham số cuối word ở vị trí 2.
        MethodHandle fixedWord = MethodHandles.insertArguments(
                render, 2, "z");
        requireType(fixedWord, MethodType.methodType(
                String.class, Formatter.class, int.class));
        require("INSERT_LAST", ">zzz",
                (String) fixedWord.invokeExact(receiver, 3));

        // 6. Giữ hai vị trí liên tiếp: receiver + count.
        MethodHandle fixedTwo = MethodHandles.insertArguments(
                render, 0, receiver, Integer.valueOf(2));
        requireType(fixedTwo, MethodType.methodType(
                String.class, String.class));
        require("INSERT_TWO", ">mm",
                (String) fixedTwo.invokeExact("m"));

        // 7. Giữ tất cả vị trí: handle mới không nhận tham số.
        MethodHandle fixedAll = MethodHandles.insertArguments(
                render, 0, receiver, Integer.valueOf(3), "q");
        requireType(fixedAll, MethodType.methodType(String.class));
        require("INSERT_ALL", ">qqq",
                (String) fixedAll.invokeExact());

        // 8. Bind theo từng bước: index của handle mới đã thay đổi.
        MethodHandle firstStep = render.bindTo(receiver);
        // firstStep: (int,String)String, count giờ là pos 0.
        MethodHandle secondStep = MethodHandles.insertArguments(
                firstStep, 0, Integer.valueOf(2));
        requireType(secondStep, MethodType.methodType(
                String.class, String.class));
        require("CHAINED", ">hehe",
                (String) secondStep.invokeExact("he"));

        // 9. Static method: bindTo giữ first reference parameter,
        //    không phải receiver.
        MethodHandle label = lookup.findStatic(
                BoundArgumentsLab.class,
                "label",
                MethodType.methodType(
                        String.class, String.class, int.class, String.class));

        MethodHandle marked = label.bindTo("TAG");
        requireType(marked, MethodType.methodType(
                String.class, int.class, String.class));
        require("STATIC_BIND", "TAG:7:ok",
                (String) marked.invokeExact(7, "ok"));

        MethodHandle fixedMiddle = MethodHandles.insertArguments(
                label, 1, Integer.valueOf(9));
        requireType(fixedMiddle, MethodType.methodType(
                String.class, String.class, String.class));
        require("STATIC_MIDDLE", "T:9:yes",
                (String) fixedMiddle.invokeExact("T", "yes"));

        // 10. Với leading primitive, bindTo bị từ chối.
        MethodHandle add = lookup.findStatic(
                BoundArgumentsLab.class,
                "add",
                MethodType.methodType(int.class, int.class, int.class));

        try {
            add.bindTo(Integer.valueOf(5));
            throw new AssertionError("bindTo không được nhận primitive");
        } catch (IllegalArgumentException expected) {
            System.out.println("PRIMITIVE_BIND_TO=REJECTED_AS_EXPECTED");
        }

        MethodHandle addFive = MethodHandles.insertArguments(
                add, 0, Integer.valueOf(5));
        requireType(addFive, MethodType.methodType(int.class, int.class));
        int sum = (int) addFive.invokeExact(7);
        if (sum != 12) {
            throw new AssertionError("Expected 12 but got " + sum);
        }
        System.out.println("PRIMITIVE_INSERT=PASS");

        // 11. null chỉ được giữ vào reference parameter.
        MethodHandle nullable = lookup.findStatic(
                BoundArgumentsLab.class,
                "nullable",
                MethodType.methodType(String.class, String.class));
        MethodHandle fixedNull = nullable.bindTo(null);
        requireType(fixedNull, MethodType.methodType(String.class));
        require("NULL_REFERENCE", "NULL",
                (String) fixedNull.invokeExact());

        // 12. Varargs tại method đích vẫn là String[] trong MethodType.
        MethodHandle join = lookup.findStatic(
                BoundArgumentsLab.class,
                "join",
                MethodType.methodType(
                        String.class, String.class, String[].class));

        // Cố định mảng thành một đối số duy nhất.
        MethodHandle joined = MethodHandles.insertArguments(
                join.asFixedArity(),
                1,
                (Object) new String[] {"a", "b"});
        requireType(joined, MethodType.methodType(
                String.class, String.class));
        require("ARRAY_ARGUMENT", "H:a,b",
                (String) joined.invokeExact("H"));

        // 13. Sai call-site type của invokeExact -> WrongMethodTypeException.
        Object genericWord = "ha";
        try {
            String result = (String) boundReceiver.invokeExact(
                    2, genericWord);
            throw new AssertionError("invokeExact không được tự cast Object");
        } catch (WrongMethodTypeException expected) {
            System.out.println("INVOKE_EXACT_TYPE=REJECTED_AS_EXPECTED");
        }

        // 14. Index vượt phạm vi -> IllegalArgumentException.
        try {
            MethodHandles.insertArguments(render, 3, "unused");
            throw new AssertionError("pos + K vượt parameterCount");
        } catch (IllegalArgumentException expected) {
            System.out.println("BAD_POSITION=REJECTED_AS_EXPECTED");
        }

        // Handle gốc vẫn giữ nguyên chữ ký và sử dụng được.
        requireType(render, MethodType.methodType(
                String.class, Formatter.class, int.class, String.class));
        require("ORIGINAL_UNCHANGED", ">aa",
                (String) render.invokeExact(receiver, 2, "a"));

        System.out.println("ALL_BOUND_ARGUMENT_CHECKS=PASS");
    }

    private static void requireType(
            MethodHandle handle, MethodType expected) {
        MethodType actual = handle.type();
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected type " + expected + ", got " + actual);
        }
    }

    private static void require(
            String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
        System.out.println(label + "=PASS");
    }
}
```

### 5.1. Biên dịch và chạy

```bash
javac -encoding UTF-8 BoundArgumentsLab.java
java BoundArgumentsLab
```

Đây là bài kiểm tra thuần Java, không cần bật preview feature hoặc thêm module ngoài `java.base`. `String.repeat` đã có từ Java 11; `MethodHandle.bindTo`, `MethodHandles.insertArguments` và `invokeExact` vẫn là API được hỗ trợ trên các JDK hiện đại.

Các dòng kiểm tra chính được mong đợi:

```text
BOUND_RECEIVER=PASS
INSERT_RECEIVER=PASS
INSERT_PRIMITIVE=PASS
INSERT_LAST=PASS
INSERT_TWO=PASS
INSERT_ALL=PASS
CHAINED=PASS
STATIC_BIND=PASS
STATIC_MIDDLE=PASS
PRIMITIVE_BIND_TO=REJECTED_AS_EXPECTED
PRIMITIVE_INSERT=PASS
NULL_REFERENCE=PASS
ARRAY_ARGUMENT=PASS
INVOKE_EXACT_TYPE=REJECTED_AS_EXPECTED
BAD_POSITION=REJECTED_AS_EXPECTED
ORIGINAL_UNCHANGED=PASS
ALL_BOUND_ARGUMENT_CHECKS=PASS
```

Nếu JVM báo lỗi khác kỳ vọng, trước tiên xem `MethodType` tại mỗi bước. Đừng vội sửa `invokeExact` thành `invoke` để bỏ qua lỗi kiểu: mục tiêu bài là hiểu đúng hợp đồng adapter, không phải làm cho một lời gọi sai chữ ký được ép kiểu ngầm đến khi chạy.

### 5.2. Bảng tóm tắt của chương trình

| Nguồn và phép biến đổi | Kiểu handle mới | Giá trị caller phải truyền |
| --- | --- | --- |
| `render` gốc | `(Formatter,int,String)String` | `receiver, count, word` |
| `render.bindTo(receiver)` | `(int,String)String` | `count, word` |
| `insertArguments(render,0,receiver)` | `(int,String)String` | `count, word` |
| `insertArguments(render,1,2)` | `(Formatter,String)String` | `receiver, word` |
| `insertArguments(render,2,"z")` | `(Formatter,int)String` | `receiver, count` |
| `insertArguments(render,0,receiver,2)` | `(String)String` | `word` |
| `insertArguments(render,0,receiver,3,"q")` | `()String` | không tham số |
| `label.bindTo("TAG")` | `(int,String)String` | `n, text` |
| `insertArguments(add,0,5)` | `(int)int` | một số int |

Đọc hàng dữ liệu theo đúng thứ tự tham số của **handle nguồn**. Hai adapter có thể tạo ra cùng kiểu mới nhưng lưu những giá trị khác nhau, nên `MethodType` chỉ mô tả chữ ký; nó không hiển thị mọi giá trị đã được bind bên trong adapter.

## 6. Cố định đúng vị trí sau nhiều lần adapter

### 6.1. Index được tính lại sau mỗi bước

Một nguồn lỗi phổ biến là lấy index theo chữ ký ban đầu khi thao tác trên handle đã được bind.

Bắt đầu bằng:

```text
H0 = render
H0.type(): (Formatter, int, String)String
index          0       1     2
```

Bind receiver:

```text
H1 = H0.bindTo(receiver)
H1.type(): (int, String)String
index       0     1
```

Lúc này, muốn giữ `count=3` phải dùng vị trí `0`, không phải vị trí `1` như ở H0:

```java
MethodHandle h1 = render.bindTo(receiver);
MethodHandle h2 = MethodHandles.insertArguments(h1, 0, 3);

// h2.type(): (String)String
String output = (String) h2.invokeExact("ab"); // ">ababab"
```

Nếu gọi `insertArguments(h1, 1, 3)`, adapter sẽ cố gán số `3` cho tham số `String` ở vị trí `1`. Đây là **lỗi kiểu của giá trị bind**, không phải lỗi `invokeExact`. Kiểm tra `h1.type()` trước khi tạo h2 giúp phát hiện sai index ngay khi review.

### 6.2. Muốn giữ hai tham số không liền nhau?

Giả sử handle ban đầu:

```text
(Formatter, int, String)String
  pos0       pos1  pos2
```

Muốn giữ `Formatter receiver` và `String word`, nhưng để `int count` còn tự do. Hai tham số này không liền nhau ở handle gốc; vì vậy không thể truyền một `pos` duy nhất và hai giá trị vào `insertArguments` để chỉ giữ pos0 + pos2 mà bỏ qua pos1.

Cách rõ ràng:

```java
MethodHandle h1 = MethodHandles.insertArguments(
        render, 2, "ha");
// h1: (Formatter,int)String

MethodHandle h2 = MethodHandles.insertArguments(
        h1, 0, receiver);
// h2: (int)String

String result = (String) h2.invokeExact(2); // ">haha"
```

Trong chuỗi adapter này, bind vị trí sau cùng trước giúp giữ nguyên chỉ số của những tham số đứng trước. Tuy nhiên không có quy tắc “luôn bind từ cuối về đầu” bắt buộc. Quy tắc thật sự là **mỗi lần dùng pos theo kiểu hiện tại của handle đang xử lý**.

### 6.3. Không được dùng vị trí âm hoặc vượt chữ ký

Với handle kiểu `(Formatter,int,String)String`:

| Lời gọi | Hợp lệ? | Vì sao |
| --- | --- | --- |
| `insertArguments(render,0,receiver)` | Có | Giữ pos0 |
| `insertArguments(render,1,3)` | Có | Giữ pos1 |
| `insertArguments(render,2,"x")` | Có | Giữ pos2 |
| `insertArguments(render,0,receiver,3)` | Có | Giữ pos0–pos1 |
| `insertArguments(render,2,"x","y")` | Không | Giữ hai vị trí nhưng chỉ còn một vị trí từ pos2 |
| `insertArguments(render,-1,receiver)` | Không | Index âm |
| `insertArguments(render,3,"x")` | Không | Pos3 không tồn tại để giữ một giá trị |

Đừng dựa vào exception rồi thử lại pos khác cho đến khi chạy được. Trong code thư viện, nên thiết kế adapter từ `MethodType` đã biết và dùng test xác nhận kiểu trước/sau.

## 7. invokeExact(), invoke() và kiểu call site

### 7.1. invokeExact đòi chữ ký tĩnh chính xác

Khi đã bind receiver:

```text
boundReceiver.type() = (int,String)String
```

Lời gọi đúng:

```java
String answer = (String) boundReceiver.invokeExact(2, "ab");
```

Compiler tạo một call site có tham số `(int,String)` và return type `String`. Với `invokeExact`, kiểu tại call site phải **khớp chính xác** với `MethodType` của handle.

Lời gọi sau **không tương đương**:

```java
Object word = "ab";

String answer = (String) boundReceiver.invokeExact(2, word);
// Call site là (int,Object)String, không phải (int,String)String.
```

Dù `word` thực sự chứa String, **kiểu tĩnh** của biến ở call site là `Object`. Lời gọi ném `WrongMethodTypeException`. Sửa bằng cách sử dụng đúng kiểu tĩnh/cast:

```java
String answer = (String) boundReceiver.invokeExact(2, (String) word);
```

Tương tự, handle có tham số primitive `int` không nhận call site tham số `Integer` trong `invokeExact` chỉ vì object có thể unbox được ở mã Java thường. Nếu cần gọi đúng hợp đồng, biểu đạt rõ `int` tại call site.

### 7.2. invoke có thể thực hiện chuyển đổi, nhưng không thay MethodType gốc

`MethodHandle.invoke` hỗ trợ thích nghi kiểu theo quy tắc `asType` của MethodHandle khi phù hợp. Nó có thể hữu ích cho adapter động nhưng không nên dùng để che việc tính sai vị trí/kiểu từ đầu.

Nếu cần một chữ ký đã chuyển đổi ổn định, hãy tạo handle mới bằng `asType` và kiểm tra `type()` của nó:

```java
MethodHandle target = boundReceiver;  // (int,String)String
MethodType newType = MethodType.methodType(
        Object.class, int.class, Object.class);

MethodHandle adapted = target.asType(newType);
// adapted.type(): (int,Object)Object
```

`asType` và `insertArguments` giải quyết **hai việc khác nhau**:

- `asType` thay kiểu biên của handle bằng các conversion được phép.
- `insertArguments` giảm số tham số vì lưu sẵn một số giá trị.

Không nhầm với `MethodHandle.asVarargsCollector` hay `asCollector`, vốn xử lý dạng đối số mảng/varargs.

### 7.3. bindTo và insertArguments không thay thế lookup/access check

`findVirtual`, `findStatic` và `findSpecial` dùng `MethodHandles.Lookup` để kiểm tra quyền truy cập khi tạo handle. `bindTo` và `insertArguments` thao tác trên handle **đã có**; chúng không “nâng quyền” để lấy một private method từ module không mở package.

Nếu lookup không được phép, hãy dùng API public đúng hợp đồng hoặc một `Lookup` được cấp quyền phù hợp. Đừng xem cố định receiver như cách vượt JPMS/module encapsulation.

## 8. Mảng, varargs và tham số Object... của insertArguments

### 8.1. Varargs trong khai báo đích là tham số mảng

Với:

```java
public static String join(String heading, String... parts) {
    return heading + ":" + String.join(",", parts);
}
```

`String...` được biểu diễn trong `MethodType` như `String[].class`:

```java
MethodHandle join = lookup.findStatic(
        Example.class, "join",
        MethodType.methodType(
                String.class, String.class, String[].class));
```

Để cố định **cả mảng** ở vị trí thứ hai:

```java
MethodHandle withParts = MethodHandles.insertArguments(
        join.asFixedArity(),
        1,
        (Object) new String[] { "a", "b" });

// withParts.type(): (String)String
String result = (String) withParts.invokeExact("H"); // "H:a,b"
```

Ở đây có **hai cơ chế varargs riêng biệt**:

1. Method nguồn `join(String, String...)` có một tham số mảng cuối; handle tạo cho method varargs có thể là variable-arity collector.
2. `MethodHandles.insertArguments(..., Object... values)` nhận **danh sách các giá trị để bind** bằng varargs của chính API adapter.

`join.asFixedArity()` giúp thao tác với kiểu `String[]` như **một đối số mảng** của method đích. Cast `(Object) new String[] {...}` giúp lời gọi `insertArguments` nhận đúng một giá trị bind là mảng String, thay vì để Java coi mảng String là danh sách các phần tử trong `Object...`.

Cũng có thể truyền rõ một danh sách values kiểu `Object[]`:

```java
String[] values = { "a", "b" };
MethodHandle withParts = MethodHandles.insertArguments(
        join.asFixedArity(), 1, new Object[] { values });
```

Nếu bỏ cast và viết `insertArguments(join, 1, new String[] {"a","b"})`, Java có thể phát cảnh báo varargs và diễn giải tham số cuối thành danh sách nhiều values, làm số lượng hoặc kiểu values bị bind không đúng ý định.

### 8.2. Bound array vẫn có trạng thái có thể thay đổi

Adapter lưu **giá trị tham chiếu** đã bind, không thực hiện deep copy toàn bộ object graph:

```java
String[] parts = { "a", "b" };
MethodHandle fixed = MethodHandles.insertArguments(
        join.asFixedArity(), 1, (Object) parts);

String before = (String) fixed.invokeExact("H"); // "H:a,b"
parts[0] = "changed";
String after = (String) fixed.invokeExact("H");  // "H:changed,b"
```

Vì mảng mutable được chia sẻ, đây là **đầu vào đã cố định về tham chiếu**, chứ không phải dữ liệu bất biến. Nếu yêu cầu adapter ổn định trước mọi mutation từ bên ngoài, sao chép mảng khi tạo và không để caller giữ tham chiếu có thể thay đổi của bản sao đó.

### 8.3. Binding String... không phải phép thêm đối số mặc định

`insertArguments` không tạo ra overload mới và không cho phép caller sau này đưa thêm các phần tử tùy ý của varargs nếu tham số mảng đã bị cố định. Sau khi bind `parts`, handle mới chỉ còn `(String)String`; muốn cho caller truyền thêm các phần tử, thiết kế handle khác dùng collector/adapters phù hợp thay vì lạm dụng `insertArguments`.

## 9. Phân biệt các lỗi: bind sai kiểu, sai index và invoke sai chữ ký

| Tình huống | Lỗi hoặc hành vi cần dự kiến | Cách sửa |
| --- | --- | --- |
| `bindTo` trên handle có tham số đầu `int` | `IllegalArgumentException` | Dùng `insertArguments(target, 0, Integer.valueOf(...))` |
| `bindTo` với object không phù hợp leading reference type | Binding không hợp lệ, thường `ClassCastException` | Kiểm tra `target.type().parameterType(0)` |
| `insertArguments` với `pos < 0` | `IllegalArgumentException` | Dùng index không âm của handle hiện tại |
| `insertArguments` khi `pos + values.length > parameterCount` | `IllegalArgumentException` | Giảm số values hoặc chọn pos hợp lệ |
| `insertArguments` với value không thể gán cho parameter tương ứng | Lỗi kiểu khi tạo adapter | Chọn đúng wrapper/reference theo `MethodType` |
| Gọi `invokeExact` bằng `Object` khi handle chờ `String` | `WrongMethodTypeException` | Đảm bảo kiểu tĩnh call site trùng `MethodType` |
| Bind receiver null rồi gọi instance method | Thường `NullPointerException` tại lời gọi | Kiểm tra receiver trước khi bind nếu API cấm null |
| Giữ `String[]` bằng cú pháp `Object...` mơ hồ | Có thể bind từng phần tử thay vì cả mảng | Dùng `asFixedArity()` và cast `(Object) array` |
| Bind nhầm vị trí sau adapter | Giá trị được kiểm tra theo formal type **mới**, có thể lỗi kiểu hoặc ra kết quả sai | In/so `handle.type()` sau từng bước |
| Handle đã bind nhưng method đích ném exception | Exception của method đích truyền theo semantics của MethodHandle | Điều tra logic đích, không đổ cho lookup |
| Lookup private member không đủ quyền | `IllegalAccessException` hoặc lỗi lookup/access liên quan | Dùng `Lookup` có quyền theo JPMS, không tìm cách lách bằng bind |

### 9.1. Lỗi sai vị trí có thể không gây exception

Đây là trường hợp nguy hiểm hơn. Với:

```java
public static String pair(String first, String second) {
    return first + "/" + second;
}
```

Handle có kiểu `(String,String)String`. Cả hai giá trị đều String, vì vậy:

```java
MethodHandle fixed = MethodHandles.insertArguments(pairHandle, 1, "X");
String result = (String) fixed.invokeExact("Y");
// "Y/X", không phải "X/Y".
```

Nếu người viết muốn cố định `first = "X"` nhưng dùng `pos = 1`, adapter vẫn được tạo thành công vì kiểu ở vị trí 1 cũng là String. Chỉ **test giá trị đầu ra** mới phát hiện lỗi; việc xem `MethodType` không đủ phân biệt hai giá trị cùng kiểu đã bị hoán đổi vai trò.

Hãy thiết kế test với các giá trị khác nhau, dễ nhận biết như `"FIRST"` và `"SECOND"`; tránh dùng cùng giá trị cho mọi tham số vì dễ che giấu lỗi index.

### 9.2. Lỗi bị phát hiện ở các giai đoạn khác nhau

```text
Lookup method
    |
    | không đủ quyền / không có chữ ký
    v
Có MethodHandle gốc
    |
    | bindTo / insertArguments
    | sai pos hoặc kiểu bound value?
    v
Có MethodHandle đã adapter
    |
    | invokeExact
    | call-site type không khớp?
    v
Lời gọi tới method đích
    |
    | dữ liệu / logic method có hợp lệ?
    v
Kết quả
```

**Phân loại theo giai đoạn** giúp sửa lỗi nhanh: `WrongMethodTypeException` ở `invokeExact` khác lỗi bị từ chối lúc tạo adapter; lỗi logic của target khác cả hai.

## 10. Cách chọn adapter trong ứng dụng

### 10.1. Khi nên dùng bindTo

Chọn `bindTo` nếu:

- Handle có **leading reference parameter** rõ ràng.
- Bạn cần cố định tham chiếu receiver, hoặc một tham số tham chiếu ở vị trí đầu.
- Code sau bind cần một handle gọn hơn, dễ gọi đi gọi lại.

Ví dụ tạo callback cho một service instance:

```java
MethodHandle unbound = lookup.findVirtual(
        Greeter.class, "greet",
        MethodType.methodType(String.class, String.class));

MethodHandle callback = unbound.bindTo(greeterInstance);
// callback.type() == (String)String
```

`callback` phù hợp để lưu cùng vòng đời của `greeterInstance`. Khi không cần chi phí adapter/reflection, một lambda trực tiếp có kiểu tĩnh như `greeterInstance::greet` có thể dễ bảo trì hơn; không mặc định dùng MethodHandle trong mọi callback.

### 10.2. Khi nên dùng insertArguments

Chọn `insertArguments` nếu:

- Cần bind một tham số **không ở đầu**.
- Cần bind tham số **primitive**.
- Cần bind một đoạn **tham số liên tiếp** cùng lúc.
- Cần phối hợp với các adapter khác và muốn kiểm soát chính xác `pos`.

Ví dụ giữ một “mode” ở giữa chữ ký:

```java
MethodHandle encoder = lookup.findStatic(
        Codec.class, "encode",
        MethodType.methodType(
                byte[].class, String.class, int.class, boolean.class));

MethodHandle strictUtf8 = MethodHandles.insertArguments(
        encoder, 1, Integer.valueOf(65001), Boolean.TRUE);

// strictUtf8.type(): (String)byte[]
```

Đây là ví dụ minh họa adapter: giá trị `65001` chỉ là tham số nghiệp vụ giả định của `Codec.encode`, **không phải API charset của Java** và không khuyến nghị dùng code page số để chọn charset. Trong code thực, hãy dùng `StandardCharsets.UTF_8`/`Charset` khi làm việc với dữ liệu mã hóa văn bản.

### 10.3. Có thể kết hợp cả hai

```java
MethodHandle receiverBound = original.bindTo(receiver);
MethodHandle fullyConfigured = MethodHandles.insertArguments(
        receiverBound, 0, Integer.valueOf(2), "ok");

// original       : (Formatter,int,String)String
// receiverBound  : (int,String)String
// fullyConfigured: ()String
```

Trong pipeline này, `insertArguments` nhận `pos = 0` vì receiver đã được bind xong. Không dùng `pos = 1` theo handle gốc.

### 10.4. Chú ý lifetime, mutability và class loader

Một handle được bind giữ tham chiếu đến các giá trị đã giữ lại. Điều này có thể tác động tới vòng đời:

- Cache handle gắn với receiver của mỗi request có thể giữ cả request/session sau khi request kết thúc.
- Bind một mảng/map mutable thì nội dung bên trong có thể thay đổi giữa các lần invoke.
- Cache handle gắn với class từ plugin class loader cũ có thể làm loader đó khó được garbage collect.
- Adapter không tự tạo thêm thread hay tài nguyên đóng được; nhưng object bound có thể sở hữu tài nguyên (file/socket/database) cần quản lý theo vòng đời riêng.

Nếu cache rộng, hãy xem **ai sở hữu receiver** và thời hạn cache. Không dùng `bindTo` như một cơ chế sao chép dữ liệu hay cô lập trạng thái giữa các thread.

### 10.5. Hiệu năng chỉ kết luận sau benchmark phù hợp

`bindTo` và `insertArguments` hữu ích vì biểu đạt **partial application** và giảm các tham số phải truyền. Tuy vậy, không có hứa hẹn rằng mọi handle sau bind đều nhanh hơn một lambda/direct call hoặc `Method.invoke` trên mọi JDK.

Nếu cần tối ưu thật sự, dùng JMH hoặc bài đo chuyên dụng trên JDK đang triển khai. Phân biệt chi phí **tạo adapter một lần** với chi phí **invoke adapter nhiều lần**; kiểm tra warmup, kiểu call site, JIT inlining, bộ dữ liệu và allocation. Không xây adapter mới ở mỗi vòng đo rồi so với phương án cache sẵn trừ khi production thực sự tạo adapter mỗi lần.

## 11. Checklist kiểm chứng và thiết kế test

Trước khi chấp nhận adapter mới vào code, nên trả lời được:

- [ ] Handle nguồn có `MethodType` nào, gồm cả receiver nếu là instance method?
- [ ] Đối số muốn bind nằm ở index nào trên **handle hiện tại**?
- [ ] `bindTo` có được dùng đúng leading **reference** parameter không?
- [ ] `insertArguments` có dùng pos hợp lệ và các giá trị đúng thứ tự, đúng kiểu không?
- [ ] Nếu bind primitive, đã dùng wrapper đúng loại và không giả định `bindTo` sẽ unbox?
- [ ] Nếu bind `null`, method đích có hợp đồng xử lý `null` không?
- [ ] Nếu bind array, đã tránh spread `Object...` ngoài ý muốn chưa?
- [ ] Có test `handle.type()` **trước và sau** từng bước adapter không?
- [ ] Có test kết quả bằng các giá trị phân biệt vị trí (FIRST/SECOND) không?
- [ ] Lời gọi `invokeExact` có đúng kiểu tĩnh cho mọi đối số và return type không?
- [ ] Handle gốc có còn hoạt động với chữ ký cũ sau khi tạo adapter không?
- [ ] Bound receiver/dữ liệu có vòng đời và mutability phù hợp cache/thread không?
- [ ] Quyền `Lookup`/module access đã được xác lập trước khi bind không?

Nếu tất cả chỉ được kiểm tra bằng “chạy ra chuỗi có vẻ đúng”, test chưa đủ để phát hiện nhầm vị trí khi các tham số cùng kiểu.

## 12. Bài tập thực hành

**Bài A — giữ receiver:** từ `Formatter.render(int,String)`, dùng `bindTo` và in `type()` trước/sau. Gọi với `(int,String)` và xác nhận receiver không còn xuất hiện trong danh sách tham số của handle mới.

**Bài B — giữ primitive:** dùng `insertArguments(render,1,Integer.valueOf(4))`. Kiểm tra handle mới có kiểu `(Formatter,String)String`. Thử thay bằng `render.bindTo(Integer.valueOf(4))`, giải thích vì sao đó không cố định count và có thể lỗi kiểu.

**Bài C — giữ tham số không đầu:** từ `label(String,int,String)`, giữ `n=7` tại vị trí `1`. Xác minh kiểu mới `(String,String)String` và kết quả có đúng giá trị n.

**Bài D — bind không liên tiếp:** giữ receiver tại pos0 và word tại pos2 của handle gốc, để count còn tự do. Thực hiện qua hai bước, in `type()` sau mỗi bước và chứng minh cách tính index.

**Bài E — sai index nhưng đúng kiểu:** dùng `pair(String,String)`, thử bind `pos=0` rồi `pos=1` cùng giá trị. Chứng minh `MethodType` mới giống nhau nhưng kết quả khác nhau; viết assertion để bắt lỗi.

**Bài F — mảng/varargs:** tạo `join(String,String...)` và bind cả mảng `String[]` ở vị trí `1` bằng `asFixedArity()`, cast `(Object)`; thử thay đổi nội dung mảng sau khi bind để quan sát object reference được giữ.

**Bài G — invokeExact tĩnh/động:** thử gọi handle `(int,String)String` bằng biến `Object` mang String; bắt `WrongMethodTypeException` và sửa call site bằng cast tường minh.

**Bài H — dữ liệu và vòng đời:** bind một receiver có trạng thái mutable (ví dụ counter), gọi nhiều lần và ghi nhận trạng thái thay đổi. Giải thích vì sao cache bound handle quá lâu có thể giữ receiver ngoài vòng đời dự kiến.

**Tiêu chí hoàn thành:** bạn luôn biểu diễn được kiểu nguồn, các vị trí bind, kiểu mới và kiểu call site; chọn đúng `bindTo` khi có leading reference parameter, `insertArguments` khi cần vị trí/primitive/đa giá trị; chứng minh handle gốc không đổi; và có test bắt được lỗi bind sai vị trí dù các tham số cùng kiểu.

### Tài liệu tham khảo

- [MethodHandle — Java SE API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html): `bindTo`, `type`, `invoke`, `invokeExact`, `asFixedArity`.
- [MethodHandles — Java SE API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html): `insertArguments`, `Lookup.findVirtual`, `Lookup.findStatic`.
- [MethodType — Java SE API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html): phương thức mô tả return type và parameter types.
- [Java Language Specification — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12): kiểu call site và lời gọi method.
- [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): bối cảnh Java 18, phân biệt core reflection với API MethodHandle hiện đại.
