# 8.9 Xây chuỗi xử lý có kiểu và kiểm tra MethodType sau từng phép kết hợp

Khi dùng `java.lang.invoke.MethodHandle`, một lời gọi động không nhất thiết phải trỏ tới một phương thức đơn lẻ. Ta có thể xây dựng **chuỗi xử lý có kiểu** (*typed invocation pipeline*) bằng cách nối nhiều handle: chuẩn hóa dữ liệu, chuyển đổi kiểu, kiểm tra điều kiện, chọn nhánh, cố định đối số và tạo kết quả. Mỗi phép kết hợp tạo ra **một MethodHandle mới**; **`MethodType` của handle mới là hợp đồng cần kiểm tra ngay** trước khi nối thêm bước khác.

Ví dụ mục tiêu: từ đầu vào dạng chuỗi `" 1_240 "`, chuẩn hóa thành `"1240"`, chuyển sang số `1240`, phân nhánh theo ngưỡng rồi biến thành `"result=large:1240"`. Các giai đoạn sử dụng kiểu khác nhau: `String → String → int → String → String`. Một pipeline đúng phải tương thích kiểu tại **từng điểm nối**, không chỉ có kết quả cuối cùng trông đúng.

Bài học thuộc chủ đề **kết hợp lời gọi** và tập trung vào cách đọc, tính toán và xác nhận `MethodType` sau mỗi adapter/combinator. Ví dụ đều dành cho **Java 17+**, có mã hoàn chỉnh, lệnh biên dịch và stdout dự kiến.

## 1. Nền tảng: MethodHandle, MethodType và ký hiệu chữ ký

`MethodHandle` là đối tượng có thể gọi; `MethodType` là mô tả **các kiểu tham số và kiểu trả về ở tầng thực thi** của handle đó. Ta tạo `MethodType` bằng API:

~~~java
MethodType a = MethodType.methodType(String.class, String.class);
MethodType b = MethodType.methodType(int.class, String.class);
MethodType c = MethodType.methodType(String.class, int.class);
MethodType d = MethodType.methodType(boolean.class, int.class);
~~~

Đây là **đoạn minh họa**; cần `import java.lang.invoke.MethodType;` và đặt trong ngữ cảnh class/method. Các chữ ký tương ứng là:

| Biểu thức `MethodType` | Chuỗi hiển thị qua `toString()` | Diễn giải |
| --- | --- | --- |
| `methodType(String.class, String.class)` | `(String)String` | Nhận `String`, trả `String` |
| `methodType(int.class, String.class)` | `(String)int` | Nhận `String`, trả `int` |
| `methodType(String.class, int.class)` | `(int)String` | Nhận `int`, trả `String` |
| `methodType(boolean.class, int.class)` | `(int)boolean` | Nhận `int`, trả `boolean` |

Thứ tự tham số là **thứ tự thực sự khi gọi handle**; với `findVirtual`, tham số receiver được đưa vào đầu `MethodType` của handle chưa gắn, mặc dù nó không có trong danh sách tham số khai báo của instance method.

Các API quan trọng:

- `handle.type()`: trả `MethodType` hiện tại; **đừng suy đoán từ tên phương thức gốc** sau khi đã qua nhiều adapter.
- `type.returnType()`: trả `Class<?>` của kết quả, có thể là primitive hoặc `void.class`.
- `type.parameterCount()`, `type.parameterType(index)`, `type.parameterArray()`: kiểm tra danh sách đầu vào.
- `type.equals(expected)`: so sánh **chữ ký toàn bộ**, kể cả return type, theo cấu trúc.
- `type.toMethodDescriptorString()`: lấy JVM method descriptor, ví dụ `(Ljava/lang/String;)I` cho `(String)int`.
- `type.changeReturnType(...)`, `type.changeParameterType(...)`, `type.insertParameterTypes(...)`, `type.dropParameterTypes(...)`: **chỉ tạo MethodType mô tả mới**, không tự thay đổi cách gọi của một handle.

`MethodType` không lưu thông tin generic như `List<String>`. Nó dùng runtime `Class<?>` và primitive types sau erasure. Nếu đã biết một `MethodHandle`, muốn thay đổi cách gọi hãy dùng `asType` hoặc các combinator phù hợp, không phải chỉ thay object `MethodType` ở một biến.

## 2. Suy luận chữ ký trước khi kết hợp

Cách dễ tránh sai là coi mỗi handle như một hàm có miền và đối miền được ghi ngay cạnh nó:

~~~text
normalize : (String)String
parse     : (String)int
isLarge   : (int)boolean
largeText : (int)String
smallText : (int)String
label     : (String)String
~~~

Như vậy có thể thiết kế chuỗi:

~~~text
                 ┌── isLarge : (int)boolean ─┐
(String)          │                          │
   │             ▼                          ▼
normalize    parseInt       guardWithTest(largeText, smallText)
   │             │                          │
   └── (String)int ──────────────────────────┘
                               │
                          (String)String
                               │
                        label : (String)String
                               │
                          (String)String
~~~

Đồ thị là sơ đồ **luồng giá trị và chữ ký**; một combinator không tự suy luận luồng này từ các generic Java. Ta phải chủ động chọn thứ tự nối và đảm bảo kiểu khớp. Những phép như `filterReturnValue` và `filterArguments` có hợp đồng kiểu **khác nhau**:

- `filterReturnValue(target, filter)`: lấy **kết quả của target** đưa vào filter, thường dùng để nối hậu xử lý.
- `filterArguments(target, pos, filters...)`: đưa kết quả của filter vào **một hoặc nhiều vị trí tham số của target**, dùng cho tiền xử lý đầu vào.
- `guardWithTest(test, target, fallback)`: kiểm tra điều kiện và gọi một trong hai nhánh có chữ ký thích hợp.
- `collectArguments(target, pos, filter)`: thay một tham số của target bằng **toàn bộ danh sách tham số của filter** nhằm tính ra đối số đó.

Mỗi phép cho ta handle mới, với kiểu có thể được tính trước và kiểm tra bằng `type()`.

## 3. Bảng công thức chữ ký cho các combinator thường dùng

Trong bảng dưới, `A`, `B`, `X`, `R` và `S` là **ký hiệu vị trí kiểu** để đọc công thức, không phải tên class có thật. Các ví dụ không biểu diễn mọi biến thể (như target trả `void`).

| Phép kết hợp | Ví dụ kiểu đầu vào | Kiểu handle kết quả |
| --- | --- | --- |
| `filterReturnValue(t, f)` | `t: (A)R`, `f: (R)S` | `(A)S` |
| `filterArguments(t, 0, f)` | `t: (A,B)R`, `f: (X)A` | `(X,B)R` |
| `collectArguments(t, 0, f)` | `t: (A,B)R`, `f: (X,Y)A` | `(X,Y,B)R` |
| `guardWithTest(test, yes, no)` | `test: (A)boolean`, `yes/no: (A)R` | `(A)R` |
| `insertArguments(t, 1, b)` | `t: (A,B)R`, `b` tương thích `B` | `(A)R` |
| `bindTo(a)` | `t: (A,B)R`, `A` là reference | `(B)R` |
| `dropArguments(t, 0, X.class)` | `t: (A)R` | `(X,A)R`, `X` bị bỏ qua |
| `permuteArguments(t, newType, reorder)` | `t: (A,B)R` | Theo `newType` và ánh xạ vị trí hợp lệ |
| `asType(newType)` | `t: (A)R` | `newType` nếu adapter chuyển kiểu được |
| `filterReturnValue(t, f)` với `t: (A)void` | `f: ()S` | `(A)S`; nhánh riêng cho `void` |

**Điểm quan trọng:** `filterArguments` và `collectArguments` đều có thể đưa một filter vào target, nhưng số lượng tham số của handle mới được quyết định khác nhau. `filterArguments` thay **kiểu của một slot** tương ứng với kết quả của filter; `collectArguments` cũng thay một slot nhưng có thể **mở rộng thành nhiều đầu vào** từ filter, hoặc chèn side effect theo một số dạng với filter trả `void`. Vì thế luôn đọc chữ ký sau khi kết hợp.

Các API này thường ném `IllegalArgumentException` ngay lúc *tạo* handle nếu kiểu/position không hợp lệ. `invokeExact` ném `WrongMethodTypeException` lúc *gọi* nếu chữ ký call site không đúng với `type()`. Đây là hai thời điểm phát hiện lỗi khác nhau.

## 4. filterReturnValue: xây đường đi từ output của bước trước

Nếu `normalize` có `(String)String` và `parse` có `(String)int`:

~~~java
MethodHandle normalizedNumber =
        MethodHandles.filterReturnValue(normalize, parse);
// normalizedNumber.type(): (String)int
~~~

Về mặt giá trị, `normalize` chạy trước; kết quả `String` được đưa vào `parse`; kết quả `int` cuối cùng trở thành kết quả của handle mới. Việc dùng `filterReturnValue` hợp lệ vì tham số của `parse` khớp **return type của `normalize`**. Nếu `parse` cần `int` thay vì `String`, combinator này sẽ không nối trực tiếp được.

Tiếp tục, nếu `classify` có kiểu `(int)String`:

~~~java
MethodHandle pipeline =
        MethodHandles.filterReturnValue(normalizedNumber, classify);
// pipeline.type(): (String)String
~~~

Sự thay đổi có thể đọc thành:

~~~text
normalize       : (String)String
parse           : (String)int
normalizedNumber: (String)int
classify        : (int)String
pipeline        : (String)String
~~~

Tại đây giá trị cuối được tính **khi invoke**; combinator không xử lý thử đầu vào ngay khi tạo. Nếu `parse` nhận chuỗi không hợp lệ, `NumberFormatException` vẫn phát sinh tại lúc thực thi pipeline.

**Đối với target trả `void`:** filter hậu xử lý dùng với `filterReturnValue` phải là filter không có tham số nhận kết quả của target. Đừng giả định mọi target luôn cung cấp một giá trị cho filter.

## 5. filterArguments và collectArguments: tiền xử lý đầu vào

Giả sử `target` có kiểu `(int)String` và `parse` có kiểu `(String)int`. Cần dùng một `String` để tạo đối số `int`:

~~~java
MethodHandle byFilter =
        MethodHandles.filterArguments(target, 0, parse);
// byFilter.type(): (String)String
~~~

`pos = 0` nghĩa là filter thay kiểu của **tham số đầu tiên** của target. Trước đây caller truyền `int`; nay caller truyền `String`, filter chuyển thành `int` rồi target nhận giá trị đã chuyển.

Nếu muốn một filter nhận **hai** tham số để tính ra một đối số của target, dùng `collectArguments`. Ví dụ target có kiểu `(int,int)int` (nhận *subtotal* và *shipping*), còn filter có kiểu `(int,int)int` (tính *subtotal* từ đơn giá và số lượng). Ghép:

~~~java
MethodHandle withSubtotal =
        MethodHandles.collectArguments(target, 0, subtotal);
// withSubtotal.type(): (int,int,int)int
~~~

Ba tham số mới là `(unitPrice, quantity, shipping)`. Hai tham số đầu đưa vào `subtotal`, giá trị trả về được đặt ở slot `0` của target, còn `shipping` giữ nguyên. Sau đó nếu cố định phí vận chuyển:

~~~java
MethodHandle fixedShipping =
        MethodHandles.insertArguments(withSubtotal, 2, 5);
// fixedShipping.type(): (int,int)int
~~~

`insertArguments` cố định tham số index `2` là `5`; handle mới chỉ nhận đơn giá và số lượng. Chữ ký thay đổi **ngay khi tạo handle mới**, không phải khi lần đầu gọi.

### Điểm cần chú ý khi có nhiều filter

`filterArguments(target, pos, filters...)` gắn các filter lần lượt với các tham số liên tiếp của target (bắt đầu tại `pos`). Các filter phải trả đúng kiểu của slot tương ứng. Với `collectArguments`, chỉ định một filter và một vị trí; danh sách tham số của filter được **thế vào** vị trí đó. Trong một pipeline dài, hãy viết ra chữ ký của từng thao tác trước khi nối để không nhầm số lượng và thứ tự đối số.

## 6. guardWithTest: rẽ nhánh mà vẫn giữ cùng hợp đồng kiểu

`MethodHandles.guardWithTest(test, target, fallback)` tạo một handle chọn đường đi dựa trên giá trị `boolean`:

~~~text
test      : (int)boolean
target    : (int)String   [nếu true]
fallback  : (int)String   [nếu false]
------------------------------------
guard     : (int)String
~~~

Trong ví dụ này, ba handle có chung kiểu tham số đầu vào `int`; test trả `boolean`, hai nhánh trả `String`. Kết quả `guard` có `(int)String`. Ta có thể đưa `guard` vào sau parse để hình thành pipeline `(String)String`.

Nếu test là `(String)boolean` nhưng target/fallback là `(int)String`, không thể trông chờ `guardWithTest` tự parse input: **phải chủ động thích nghi hoặc nối đúng một bước chuyển kiểu**. Test và nhánh phải có chữ ký tương thích theo quy tắc của combinator, không chỉ có tên method gần giống nhau.

Một ưu điểm của `guardWithTest` là mỗi lần gọi nó chỉ thực thi **test và nhánh được chọn**, không tính cả hai nhánh rồi mới lấy một kết quả. Nếu test hoặc nhánh ném ngoại lệ, ngoại lệ vẫn lan ra qua pipeline như các lời gọi handle thông thường.

## 7. Một helper để kiểm tra MethodType sau **từng** bước

Đừng chỉ gọi `System.out.println(handle.type())` một cách thủ công. Khi xây pipeline lớn, bạn có thể xác nhận bằng một hàm nhỏ:

~~~java
static void check(String stage, MethodHandle handle, MethodType expected) {
    MethodType actual = handle.type();
    if (!actual.equals(expected)) {
        throw new AssertionError(
                stage + ": expected " + expected + ", actual " + actual);
    }
    System.out.println(stage + " -> " + actual);
}
~~~

Đây là **phương thức minh họa**, cần đặt trong class và import `java.lang.invoke.*`. `MethodType.equals` kiểm tra **return type lẫn toàn bộ danh sách tham số**, khác với việc chỉ kiểm tra `parameterCount()`. Việc ném `AssertionError` trong bài học giúp lỗi xuất hiện rõ ràng, kể cả khi chương trình chạy không bật cờ `-ea`.

Cách dùng:

~~~java
MethodType expected =
        MethodType.methodType(int.class, String.class);
check("normalize+parse", normalizedNumber, expected);
~~~

Nếu chữ ký dự kiến sai, chương trình dừng **trước lời gọi xử lý dữ liệu thật** và nêu tên stage cùng expected/actual. Trong thư viện sản xuất, có thể thay `AssertionError` bằng exception cấu hình thích hợp hoặc dùng test unit tự động; điều quan trọng là đảm bảo lỗi cấu hình pipeline được phát hiện sớm.

Khi cần log thêm dạng JVM descriptor:

~~~java
System.out.println(expected.toMethodDescriptorString());
// (Ljava/lang/String;)I
~~~

`MethodType.toString()` phục vụ việc đọc chữ ký cho con người, còn `toMethodDescriptorString()` cho cú pháp descriptor JVM; trong cả hai trường hợp **không parse chuỗi làm nguồn chân lý về kiểu**. Dùng trực tiếp đối tượng `MethodType` và các API của nó.

## 8. Ví dụ hoàn chỉnh 1: normalize → parse → guard → decorate

Tạo file **TypedPipelineDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class TypedPipelineDemo {
    public static String normalize(String raw) {
        return raw.strip().replace("_", "");
    }

    public static int parse(String text) {
        return Integer.parseInt(text);
    }

    public static boolean isLarge(int number) {
        return number >= 1000;
    }

    public static String largeText(int number) {
        return "large:" + number;
    }

    public static String smallText(int number) {
        return "small:" + number;
    }

    public static String decorate(String value) {
        return "result=" + value;
    }

    static void check(String stage, MethodHandle handle, MethodType expected) {
        MethodType actual = handle.type();
        if (!actual.equals(expected)) {
            throw new AssertionError(
                    stage + ": expected " + expected + ", actual " + actual);
        }
        System.out.println(stage + " -> " + actual);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodType stringToString =
                MethodType.methodType(String.class, String.class);
        MethodType stringToInt =
                MethodType.methodType(int.class, String.class);
        MethodType intToBoolean =
                MethodType.methodType(boolean.class, int.class);
        MethodType intToString =
                MethodType.methodType(String.class, int.class);

        MethodHandle normalize = lookup.findStatic(
                TypedPipelineDemo.class, "normalize", stringToString);
        MethodHandle parse = lookup.findStatic(
                TypedPipelineDemo.class, "parse", stringToInt);
        MethodHandle test = lookup.findStatic(
                TypedPipelineDemo.class, "isLarge", intToBoolean);
        MethodHandle large = lookup.findStatic(
                TypedPipelineDemo.class, "largeText", intToString);
        MethodHandle small = lookup.findStatic(
                TypedPipelineDemo.class, "smallText", intToString);
        MethodHandle decorate = lookup.findStatic(
                TypedPipelineDemo.class, "decorate", stringToString);

        check("normalize", normalize, stringToString);
        check("parse", parse, stringToInt);
        check("test", test, intToBoolean);

        MethodHandle chooser =
                MethodHandles.guardWithTest(test, large, small);
        check("chooser", chooser, intToString);

        MethodHandle normalizedNumber =
                MethodHandles.filterReturnValue(normalize, parse);
        check("normalize+parse", normalizedNumber, stringToInt);

        MethodHandle classified =
                MethodHandles.filterReturnValue(normalizedNumber, chooser);
        check("classified", classified, stringToString);

        // Cùng ý nghĩa, viết theo hướng tiền xử lý đối số:
        MethodHandle alternate =
                MethodHandles.filterArguments(chooser, 0, normalizedNumber);
        check("alternate", alternate, stringToString);

        MethodHandle labeled =
                MethodHandles.filterReturnValue(classified, decorate);
        check("labeled", labeled, stringToString);

        MethodHandle adapted = labeled.asType(
                MethodType.methodType(Object.class, Object.class));
        check("adapted", adapted,
                MethodType.methodType(Object.class, Object.class));

        String first = (String) labeled.invokeExact(" 1_240 ");
        String second = (String) labeled.invokeExact(" 9 ");
        String same = (String) alternate.invokeExact(" 1_240 ");
        Object boxed = adapted.invokeExact((Object) " 9 ");

        System.out.println("case-1 -> " + first);
        System.out.println("case-2 -> " + second);
        System.out.println("alternate call -> " + same);
        System.out.println("adapted call -> " + boxed);
    }
}
~~~

Biên dịch/chạy từ thư mục chứa file, dùng JDK 17 trở lên:

~~~bash
javac TypedPipelineDemo.java
java TypedPipelineDemo
~~~

Stdout:

~~~text
normalize -> (String)String
parse -> (String)int
test -> (int)boolean
chooser -> (int)String
normalize+parse -> (String)int
classified -> (String)String
alternate -> (String)String
labeled -> (String)String
adapted -> (Object)Object
case-1 -> result=large:1240
case-2 -> result=small:9
alternate call -> large:1240
adapted call -> result=small:9
~~~

### Đọc kết quả ở từng mốc

**Mốc 1 — chuẩn hóa:** `normalize.type()` là `(String)String`. Input `" 1_240 "` được `strip()` thành `"1_240"` và `replace("_", "")` thành `"1240"`.

**Mốc 2 — parse:** `parse.type()` là `(String)int`. Khi ghép `filterReturnValue(normalize, parse)`, kết quả thành `(String)int`: caller vẫn truyền chuỗi, nhưng nhận số nguyên.

**Mốc 3 — phân nhánh:** `guardWithTest(test, large, small)` nhận số `int` và trả chuỗi `String`, có kiểu `(int)String`. Giá trị `1240` chọn nhánh `largeText`, `9` chọn `smallText`.

**Mốc 4 — đường chính:** `filterReturnValue(normalizedNumber, chooser)` nối `(String)int` vào `(int)String`, tạo `(String)String`. Đầu vào của caller vẫn là một `String`; phép gọi bên trong diễn ra theo thứ tự đã cấu hình.

**Mốc 5 — đường tương đương:** `filterArguments(chooser, 0, normalizedNumber)` cũng tạo `(String)String` vì nó sử dụng kết quả của filter làm tham số `int` đầu tiên của `chooser`. Hai đường thể hiện cùng phép biến đổi trong trường hợp này, nhưng tính chất tham số/điểm nối của chúng khác nhau.

**Mốc 6 — trang trí:** `filterReturnValue(classified, decorate)` bổ sung tiền tố `"result="` và vẫn giữ `(String)String`.

**Mốc 7 — adapter:** `asType((Object)Object)` tạo handle có chữ ký `(Object)Object`. `invokeExact((Object) " 9 ")` được khai báo nhận `Object` và kết quả được gán vào biến `Object`, nên call site khớp với handle đã thích nghi. Bên trong adapter kiểm tra/cast đầu vào thành `String` và đưa kết quả `String` ra dưới dạng `Object`.

Lưu ý **vòng đời giá trị khác vòng đời handle**: tất cả combinator ở trên chỉ xây “mạng lưới lời gọi”; phép chuẩn hóa, parse, test và format **thực sự chạy** khi gọi `labeled.invokeExact(...)`, không chạy ngay trong lúc xây pipeline.

## 9. Ví dụ hoàn chỉnh 2: collectArguments, insertArguments, permuteArguments, dropArguments

Pipeline thứ hai mô phỏng bài toán hóa đơn: từ **đơn giá, số lượng** tính thành tiền, cộng **phí vận chuyển cố định**, rồi tạo chuỗi biên nhận gắn với tên người mua. Ta sẽ đổi thứ tự tham số và thêm tham số ngữ cảnh bị bỏ qua để thấy `MethodType` đổi như thế nào.

Tạo file **ReceiptPipelineDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class ReceiptPipelineDemo {
    public static int subtotal(int unitPrice, int quantity) {
        return unitPrice * quantity;
    }

    public static int addShipping(int sub, int shipping) {
        return sub + shipping;
    }

    public static String receipt(String buyer, int total) {
        return buyer + ": " + total;
    }

    static void check(String stage, MethodHandle handle, MethodType expected) {
        MethodType actual = handle.type();
        if (!actual.equals(expected)) {
            throw new AssertionError(
                    stage + ": expected " + expected + ", actual " + actual);
        }
        System.out.println(stage + " -> " + actual);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType ints =
                MethodType.methodType(int.class, int.class, int.class);

        MethodHandle subtotal = lookup.findStatic(
                ReceiptPipelineDemo.class, "subtotal", ints);
        MethodHandle addShipping = lookup.findStatic(
                ReceiptPipelineDemo.class, "addShipping", ints);
        MethodHandle receipt = lookup.findStatic(
                ReceiptPipelineDemo.class, "receipt",
                MethodType.methodType(
                        String.class, String.class, int.class));

        check("subtotal", subtotal, ints);
        check("addShipping", addShipping, ints);

        // addShipping(subtotal, shipping):
        // subtotal được tính từ (unitPrice, quantity).
        MethodHandle collected =
                MethodHandles.collectArguments(addShipping, 0, subtotal);
        check("collected", collected,
                MethodType.methodType(
                        int.class, int.class, int.class, int.class));

        // Cố định shipping ở tham số thứ ba.
        MethodHandle fixedShipping =
                MethodHandles.insertArguments(collected, 2, 5);
        check("fixedShipping", fixedShipping, ints);

        // receipt(buyer, fixedShipping(unitPrice, quantity))
        MethodHandle pipeline =
                MethodHandles.collectArguments(receipt, 1, fixedShipping);
        check("pipeline", pipeline,
                MethodType.methodType(
                        String.class,
                        String.class, int.class, int.class));

        // Đổi từ (buyer, unitPrice, quantity) sang
        // (unitPrice, quantity, buyer).
        MethodHandle reordered = MethodHandles.permuteArguments(
                pipeline,
                MethodType.methodType(
                        String.class,
                        int.class, int.class, String.class),
                2, 0, 1);
        check("reordered", reordered,
                MethodType.methodType(
                        String.class,
                        int.class, int.class, String.class));

        // Thêm tham số context bị bỏ qua ở index 0.
        MethodHandle withContext = MethodHandles.dropArguments(
                reordered, 0, String.class);
        check("withContext", withContext,
                MethodType.methodType(
                        String.class,
                        String.class, int.class, int.class, String.class));

        String first = (String) pipeline.invokeExact("Lan", 7, 3);
        String second = (String) reordered.invokeExact(7, 3, "Minh");
        String third = (String) withContext.invokeExact(
                "request-42", 7, 3, "Hoa");

        System.out.println("direct -> " + first);
        System.out.println("reordered call -> " + second);
        System.out.println("context call -> " + third);
    }
}
~~~

~~~bash
javac ReceiptPipelineDemo.java
java ReceiptPipelineDemo
~~~

Stdout:

~~~text
subtotal -> (int,int)int
addShipping -> (int,int)int
collected -> (int,int,int)int
fixedShipping -> (int,int)int
pipeline -> (String,int,int)String
reordered -> (int,int,String)String
withContext -> (String,int,int,String)String
direct -> Lan: 26
reordered call -> Minh: 26
context call -> Hoa: 26
~~~

### Kiểm tra lý do của từng chữ ký

1. **`subtotal`** có `(int,int)int`: đơn giá `7` nhân số lượng `3` cho kết quả `21`.
2. **`addShipping`** có `(int,int)int`: nhận *subtotal* và *shipping*, trả tổng.
3. **`collectArguments(addShipping, 0, subtotal)`** thế kết quả `subtotal(unitPrice,quantity)` vào tham số `sub` của `addShipping`. Do filter nhận hai tham số `int`, handle mới nhận ba tham số `(unitPrice, quantity, shipping)`, nên kiểu là `(int,int,int)int`.
4. **`insertArguments(collected, 2, 5)`** gắn `shipping=5` ở index 2. Handle mới có `(int,int)int`, không còn yêu cầu caller truyền shipping.
5. **`collectArguments(receipt, 1, fixedShipping)`** thế số tiền tính được vào tham số thứ hai (index 1) của `receipt(String buyer,int total)`, tạo `(String,int,int)String`.
6. **`permuteArguments(...)`** thay đổi thứ tự đối số sang `(int,int,String)String`. Mảng ánh xạ `2,0,1` có nghĩa: tham số cũ `buyer` lấy từ vị trí mới `2`, `unitPrice` lấy từ vị trí `0`, `quantity` lấy từ vị trí `1`. Đây là **ánh xạ old slot → new slot**, không phải thứ tự danh sách trường được đánh số tùy ý.
7. **`dropArguments(reordered, 0, String.class)`** chèn thêm một `String context` ở đầu nhưng **không truyền nó vào thao tác gốc**. Handle mới có `(String,int,int,String)String`; tên ngữ cảnh không ảnh hưởng kết quả tính tiền.
8. Cả ba lời gọi đều tính `7 × 3 + 5 = 26`, nhưng mỗi handle có chữ ký đầu vào khác nhau.

**Lưu ý bảo trì:** `dropArguments` không “tự động log” hay “tự động xác minh” tham số mới. Nó **bỏ qua** giá trị đó; nếu cần kiểm tra context, hãy thiết kế filter/guard thật sự thực thi kiểm tra. Tương tự, `permuteArguments` không chuyển đổi kiểu: các vị trí trong chữ ký mới phải tương thích với vị trí được chọn của target, và có thể có ánh xạ lặp hoặc bỏ bớt nguồn theo hợp đồng API khi hợp lệ.

## 10. invokeExact và invoke: nơi pipeline gặp call site

Giả sử pipeline cuối có `type() == (String)String`. Lời gọi đúng:

~~~java
String output = (String) pipeline.invokeExact(" 7 ");
~~~

Đây là call site `(String)String`. Kiểu trả về cũng là một phần của chữ ký, không chỉ kiểu tham số. Lời gọi sau biên dịch được nhưng sai khi chạy:

~~~java
Object wrong = pipeline.invokeExact(" 7 ");
~~~

Call site này yêu cầu `(String)Object`; `invokeExact` **không tự coi `String` và `Object` tương đương** và có thể ném `WrongMethodTypeException`. Ngược lại, `invoke` thử thích nghi các kiểu theo quy tắc `asType` trong phạm vi được hỗ trợ.

Để thấy sự khác biệt rõ ràng, xét hai handle:

~~~java
// pipeline có kiểu (String)String.
MethodHandle generic = pipeline.asType(
        MethodType.methodType(Object.class, Object.class));
// generic có kiểu (Object)Object.

Object result = generic.invokeExact((Object) " 7 ");
~~~

`asType` tạo adapter mới; chữ ký **gốc** của `pipeline` không thay đổi. `generic.invokeExact` giờ có call site `(Object)Object` và khớp chữ ký adapter. Khi giá trị thực là `String`, chuyển đổi tham chiếu có thể thành công. Nếu truyền object không thể cast sang `String`, sẽ gặp `ClassCastException` trong adapter.

Các ngoại lệ cần phân biệt:

- **`IllegalArgumentException` khi kết hợp:** vị trí tham số sai, kiểu input/output của filter và target không tương thích, hoặc kiểu nhánh guard không hợp lệ.
- **`WrongMethodTypeException` khi invokeExact:** chữ ký call site không khớp `handle.type()`; với `invoke` có thể xảy ra nếu không tạo được chuyển đổi kiểu cần thiết.
- **`ClassCastException` khi chạy adapter:** một giá trị tham chiếu thực tế không phù hợp kiểu đích.
- **Ngoại lệ nghiệp vụ từ phương thức đích:** ví dụ `NumberFormatException` khi parse chuỗi không hợp lệ, được truyền qua pipeline, không tự bị bọc vào `InvocationTargetException` chỉ vì dùng method handle.

Không phải adapter nào cũng tránh boxing/unboxing hoặc conversion; cần nhìn vào chữ ký của cả handle trước và sau `asType`. Một pipeline dùng primitive `int` ở giữa có thể giữ primitive trên toàn đường đi nếu combinator khớp kiểu chính xác, thay vì ép mọi bước về `Object`.

## 11. Bắt lỗi khi **tạo** pipeline, không chờ tới khi xử lý dữ liệu

Một nguyên tắc triển khai tốt là xem thời điểm tạo pipeline như một giai đoạn **kiểm thử cấu hình**. Ví dụ:

~~~java
MethodHandle wrongFilter = /* một handle (int)String */;
MethodHandle target = /* một handle (String)int */;
// filterReturnValue(target, wrongFilter) là hợp lệ:
// target trả int, wrongFilter nhận int.
~~~

Hai dòng khai báo trên là **mã minh họa khái niệm**, không phải code có thể biên dịch độc lập. Nếu thay `wrongFilter` bằng một handle `(long)String`, kết hợp trực tiếp bằng `filterReturnValue` sẽ thất bại vì output `int` của target không khớp input `long` của filter theo yêu cầu combinator. Khi thực sự muốn widen `int` thành `long`, hãy thêm một adapter hợp lệ hoặc sửa thiết kế chữ ký, đừng ép nhầm sang một method không tương thích.

Cách tiếp cận **type-first**:

1. Vẽ input/output của từng bước, ví dụ `(String)String`, `(String)int`, `(int)String`.
2. Tìm handle với `Lookup` bằng đúng `MethodType` của method khai báo. Đối với `findVirtual`, nhớ receiver được thêm vào `type()` của handle được tìm.
3. Sau **mỗi phép** `filterReturnValue`, `filterArguments`, `collectArguments`, `guardWithTest`, `insertArguments`, `permuteArguments`..., gọi `type()`.
4. So sánh với một `MethodType` dự kiến; nên kiểm tra cả số lượng, thứ tự, lớp tham số và kiểu trả về, không chỉ log kết quả.
5. Chỉ khi các kiểm tra chữ ký qua hết mới gọi `invokeExact` trên pipeline cuối với biểu thức call site đúng.
6. Kiểm thử thêm cả giá trị hợp lệ, không hợp lệ, `null`, overflow và ngoại lệ target theo yêu cầu nghiệp vụ.

**Không sử dụng `MethodType.toString()` để parse ngược thành kiểu**: có thể gặp class inner, mảng, cùng tên class nhưng khác class loader hoặc generic bị erasure. Đối tượng `MethodType` và `Class<?>` là thông tin chuẩn xác hơn.

### Phát hiện mất thông tin và side effect

Một phép kết hợp có thể **bỏ qua tham số** (ví dụ `dropArguments`), **đổi thứ tự đầu vào** (`permuteArguments`), **cố định một giá trị** (`insertArguments`) hoặc **chỉ thực thi một nhánh** (`guardWithTest`). Kiểm tra chữ ký là **điều kiện cần**, nhưng không phải **điều kiện đủ** để bảo đảm logic nghiệp vụ đúng. Cần unit test việc gắn đúng vị trí, thứ tự chạy, nhánh được chọn, và việc dữ liệu ngữ cảnh có được sử dụng hay vô tình bị bỏ qua.

## 12. Một số combinator nâng cao trong pipeline

Sau khi nắm các phép cơ bản, Java còn cung cấp nhiều công cụ khác. Điểm chung vẫn là **tính chữ ký mới, kiểm tra `type()`, rồi kiểm tra giá trị**:

| API | Mục đích | Điều nên xem trước khi dùng |
| --- | --- | --- |
| `foldArguments` | Tính kết quả của một combiner rồi đưa vào target (hoặc thực hiện side effect trong trường hợp combiner trả `void`) | Thứ tự tham số và số lượng giá trị được chuyển tiếp; dễ nhầm với `collectArguments` |
| `filterReturnValue` | Hậu xử lý kết quả target | Return type target và kiểu input filter |
| `filterArguments` | Tiền xử lý từng tham số target | `pos`, từng filter, result type của filter |
| `collectArguments` | Tính một tham số target bằng một filter đa tham số | `pos`, danh sách tham số mới và target slot |
| `guardWithTest` | Chọn giữa hai nhánh có chữ ký phù hợp | Test phải trả boolean; nhánh được chọn không đòi kiểu mới tùy ý |
| `catchException` | Chặn một loại exception phù hợp và chuyển sang handler | Exception class, chữ ký của handler và target |
| `tryFinally` | Bảo đảm một cleanup handle chạy khi target kết thúc | Chữ ký của cleanup và cách chuyển tiếp kết quả/exception |
| `filterArguments`/`filterReturnValue` kết hợp `asType` | Thích nghi đầu vào và đầu ra khi cần | Chuyển đổi nào là hợp lệ, nơi có boxing/cast |
| `dropArguments` | Chấp nhận thêm tham số nhưng không sử dụng | Tránh vô tình bỏ qua dữ liệu quan trọng |
| `permuteArguments` | Đảo vị trí hoặc tổ chức lại danh sách đầu vào | Kích thước và kiểu của mọi vị trí được ánh xạ |

Các API nâng cao có quy tắc chữ ký riêng; bảng chỉ cho biết **vai trò**, không thay thế việc đọc hợp đồng chi tiết khi triển khai. Khi một chuỗi trở nên khó kiểm soát, chia thành nhiều handle trung gian đặt tên có ý nghĩa là lựa chọn dễ review hơn một biểu thức `MethodHandles.*` lồng sâu nhiều tầng.

## 13. Thiết kế pipeline an toàn và dễ bảo trì

### A. Lưu cả handle lẫn kiểu dự kiến trong thiết kế

Nếu pipeline là thành phần cấu hình lâu dài, nên xem `MethodType` là một **schema thực thi**. Ví dụ luồng nghiệp vụ luôn yêu cầu `(String)String` thì khi hoàn thành mọi bước, assert `pipeline.type().equals(MethodType.methodType(String.class,String.class))`.

Các handle là immutable theo nghĩa `asType`/combinator trả **handle mới** mà không sửa handle gốc. Điều này giúp lưu từng bước để kiểm tra, đồng thời cho phép cache các pipeline đã được xác thực. Tuy nhiên, các giá trị hoặc receiver **được gắn bên trong** handle có thể là object mutable; tính bất biến của handle không biến target trở thành thread-safe.

### B. Quyền truy cập vẫn thuộc về Lookup

Các bước `findStatic`/`findVirtual` và những thao tác tạo direct handle dùng quyền của `MethodHandles.Lookup`. Combinator **không tự cấp quyền mới**; nó biến đổi cách gọi của một handle đã tạo. Khi tích hợp framework/module, phải xử lý đúng package exports/opens và ranh giới truy cập. Không phát tán handle mang quyền nhạy cảm cho mã không tin cậy.

### C. Tránh tự động chuyển mọi kiểu sang Object

Dùng `(Object)Object` cho tất cả bước trông có vẻ linh hoạt, nhưng làm mất tín hiệu mạnh của `MethodType`, phát sinh cast, boxing/unboxing và chuyển lỗi về lúc runtime. Nếu pipeline có các phép tính số nguyên, giữ `int` ở những đoạn phù hợp. Chỉ dùng `asType` khi có lý do rõ ràng, và kiểm tra adapter trước khi gọi.

### D. Quan sát lỗi đúng tầng

- Lỗi **tìm handle**: sai tên/chữ ký hoặc thiếu quyền, thường liên quan `NoSuchMethodException`/`IllegalAccessException`.
- Lỗi **tạo pipeline**: không khớp kiểu hoặc vị trí ở combinator; thường là `IllegalArgumentException`.
- Lỗi **gọi pipeline**: `WrongMethodTypeException` do call-site signature không phù hợp với handle.
- Lỗi **dữ liệu nghiệp vụ**: NumberFormatException, null, chia cho không hoặc lỗi từ method mục tiêu.

Giữ stage name trong thông báo kiểm tra kiểu sẽ giảm đáng kể công sức tìm lỗi. Khi dùng `main throws Throwable` trong ví dụ, đó là để minh họa chữ ký rộng của `invokeExact`/`invoke`; trong dịch vụ thực nên xử lý ngoại lệ chính xác theo ngữ cảnh.

### E. Tối ưu sau khi xác thực tính đúng

Tìm handle và tạo adapter trong luồng khởi tạo, sau đó **tái sử dụng pipeline** khi hợp lý. JIT có thể tối ưu tốt chuỗi MethodHandle ổn định, nhưng hiệu năng thực phụ thuộc JVM, mức độ ổn định call site, combinator, boxing, dữ liệu và cách benchmark. Không kết luận rằng một pipeline nhiều combinator luôn nhanh hơn method call trực tiếp hoặc Reflection. Nếu hiệu năng quan trọng, đo cùng workload, warmup và điều kiện tải thực tế.

## 14. Lỗi phổ biến khi kiểm tra chuỗi có kiểu

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `filterReturnValue` thất bại ngay lúc tạo | Return type của target không phù hợp parameter type của filter | In `target.type()` và `filter.type()`; sửa kiểu hoặc thêm adapter có chủ đích |
| `filterArguments` báo lỗi | Sai index, filter không nhận đúng đầu vào hoặc trả sai kiểu slot | Đối chiếu vị trí `pos` và từng `MethodType` |
| `collectArguments` tạo nhiều tham số hơn dự kiến | Filter đa tham số được mở rộng vào danh sách tham số target | Viết lại chữ ký mới trước khi ghép, kiểm tra `parameterCount()` |
| `guardWithTest` không tạo được handle | Test/target/fallback có kiểu không phù hợp nhau | Test trả boolean, nhánh đồng nhất chữ ký thích hợp |
| `permuteArguments` sai thứ tự | Đọc nhầm mảng reorder | Ánh xạ mỗi tham số target cũ tới một vị trí tham số handle mới; unit test thứ tự |
| `dropArguments` khiến dữ liệu context không tác dụng | Parameter mới chỉ được nhận rồi bỏ qua | Dùng filter/guard nếu muốn validate hoặc sử dụng context |
| `insertArguments` cố định nhầm giá trị | Index sau mỗi biến đổi đã thay đổi | Gọi `type()` trước mỗi lần bind, đặt tên từng handle mới |
| `invokeExact` có `WrongMethodTypeException` dù argument đúng | Return type của call site bị suy ra khác, hoặc có primitive mismatch | Cast/gán đúng kiểu và kiểm tra đủ return type |
| `invoke`/`asType` có `ClassCastException` | Giá trị Object thật không thể chuyển thành tham chiếu đích | Ràng buộc input hoặc đổi thiết kế adapter |
| Code chạy tốt với `String` nhưng hỏng khi null | Bước gọi `strip()` hoặc parse không chấp nhận null | Xác định chính sách null trước khi xây pipeline |
| Log chữ ký đúng nhưng logic sai | Kiểu không chứng minh đúng thứ tự xử lý hay đúng giá trị đã bind | Test đầu vào/đầu ra và side effects của từng stage |
| Generic signature bị hiểu thành MethodType | `MethodType` không lưu `List<String>` sau erasure | Khi cần metadata generic, sử dụng Reflection API thích hợp |

## 15. Bài tập tự kiểm tra (kèm lời giải)

**Bài 1.** Cho `normalize: (String)String` và `parse: (String)int`, áp dụng `filterReturnValue(normalize, parse)` có kiểu gì?  
**Lời giải:** `(String)int`. Pipeline nhận đầu vào String của normalize, trả int của parse.

**Bài 2.** Cho `target: (int)String`, `filter: (String)int`; hãy viết tổ hợp tiền xử lý và kiểu kết quả.  
**Lời giải:** `MethodHandles.filterArguments(target, 0, filter)` có kiểu `(String)String`.

**Bài 3.** Cho `target: (int,int)int` và `filter: (int,int)int`, `collectArguments(target, 0, filter)` có mấy tham số?  
**Lời giải:** Ba tham số, kiểu `(int,int,int)int`. Hai int dùng làm input filter, int còn lại là tham số thứ hai của target.

**Bài 4.** Muốn chuyển `(int,int,int)int` thành `(int,int)int` bằng cách cố định giá trị thứ ba là `5`, dùng gì?  
**Lời giải:** `MethodHandles.insertArguments(handle, 2, 5)`. Các index tính trên `handle.type()` **ở thời điểm biến đổi**, không phải chữ ký ban đầu trước mọi adapter.

**Bài 5.** Vì sao `guardWithTest(test, yes, no)` không tự chuyển input String thành int?  
**Lời giải:** Combinator kiểm tra sự tương thích chữ ký, không tự chạy `Integer.parseInt`. Phải nối một handle chuyển `String → int` vào đúng vị trí trước guard.

**Bài 6.** Pipeline có `(String)String`, câu `Object result = pipeline.invokeExact("A");` có chắc chắn hợp lệ?  
**Lời giải:** Không. Call site yêu cầu trả `Object`, không khớp return `String` của handle; có thể ném `WrongMethodTypeException`. Nên dùng `String result = (String) pipeline.invokeExact("A");`.

**Bài 7.** `dropArguments(target, 0, String.class)` bổ sung đầu vào `String context` để làm gì?  
**Lời giải:** Cho phép caller truyền thêm tham số `context` mà target không dùng. Không thể dùng nó như phép validate/log nếu không có stage khác thực hiện việc đó.

**Bài 8.** Câu lệnh `MethodType t = pipeline.type().changeReturnType(Object.class);` đã sửa pipeline chưa?  
**Lời giải:** Chưa. Nó chỉ tạo `MethodType` mới. Muốn thích nghi handle phải xây adapter như `pipeline.asType(t)` nếu hợp lệ.

**Bài 9.** Tại sao `MethodType.equals` đáng tin hơn chỉ kiểm tra `parameterCount()`?  
**Lời giải:** Hai handle cùng số tham số vẫn có thể khác **thứ tự/kiểu tham số** hoặc **return type**. `equals` so sánh toàn bộ chữ ký.

**Bài 10.** `filterReturnValue` và `filterArguments` đều có thể cho `(String)String` trong ví dụ đầu, vậy có tương đương mọi trường hợp?  
**Lời giải:** Không. Một phép nối theo **kết quả target**, một phép lọc **tham số target**. Chúng chỉ diễn đạt phép chuyển tương ứng trong ngữ cảnh đã chọn; thứ tự, số tham số và side effects có thể khác trong pipeline tổng quát.

## 16. Tổng kết và checklist ngắn

- **Mỗi MethodHandle luôn có `MethodType` hiện tại.** Sau *mỗi phép kết hợp* phải hỏi lại `handle.type()`, vì kiểu của handle mới có thể khác hoàn toàn chữ ký ban đầu.
- **Thiết kế bằng chữ ký trước khi viết combinator:** vẽ luồng input/output, định vị điểm nối, kiểm tra chỗ cần receiver, primitive và nhánh.
- **Dùng đúng công cụ:** `filterReturnValue` cho hậu xử lý; `filterArguments` cho biến đổi slot input; `collectArguments` cho tính một argument từ nhiều argument; `guardWithTest` cho lựa chọn theo boolean.
- **Theo dõi phép thay đổi danh sách tham số:** `insertArguments` cố định, `dropArguments` thêm nhưng bỏ qua, `permuteArguments` đổi vị trí, `asType` thích nghi các kiểu khi hợp lệ.
- **Kiểm tra chính xác `MethodType.equals` theo từng stage**, không chỉ log kiểu và không chỉ test kết quả cuối. Với pipeline sinh động, assert kiểu tại biên giữa các stage giúp lỗi xuất hiện sớm.
- **`invokeExact` còn kiểm tra return type ở call site.** Với primitive và kiểu tham chiếu, không giả định JVM sẽ tự chuyển `int`/`Integer` hoặc `String`/`Object`.
- **Kiểu đúng chưa bảo đảm logic đúng:** unit test thứ tự tham số, nhánh được chọn, exception, null, side effect và trạng thái của receiver.
- **Ưu tiên giữ primitive khi có ý nghĩa và cache pipeline ổn định.** Tối ưu bằng đo đạc, không dựa vào giả định mọi tổ hợp handle luôn nhanh.

Cách làm bền vững là **tính kiểu → kết hợp → kiểm tra kiểu → thử giá trị**, lặp lại sau từng phép biến đổi. Khi giữ được chuỗi `MethodType` rõ ràng, các pipeline `java.lang.invoke` sẽ dễ kiểm chứng, gỡ lỗi và mở rộng hơn nhiều so với cách nối các handle rồi chỉ phát hiện lỗi tại lời gọi cuối.
