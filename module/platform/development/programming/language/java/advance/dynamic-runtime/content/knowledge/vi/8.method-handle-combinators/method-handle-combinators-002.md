# 8.2 Gắn đối số cố định bằng `insertArguments` và thêm đối số bị bỏ qua bằng `dropArguments`

Trong Java dynamic runtime, `MethodHandle` mô tả một điểm gọi có kiểu xác định. Đôi khi chữ ký thực tế của method không khớp với chữ ký mà một bộ điều phối, callback hoặc framework cần sử dụng: có tham số muốn **cố định trước**, hoặc có tham số framework bắt buộc cung cấp nhưng logic đích **không cần đọc**. Hai combinator trong `java.lang.invoke.MethodHandles` giải quyết hai tình huống đó:

- `MethodHandles.insertArguments(target, pos, values...)`: **gắn sẵn giá trị** cho một hoặc nhiều tham số liên tiếp của `target`. Handle mới **ít tham số hơn** vì người gọi không cần truyền lại các giá trị đã gắn.
- `MethodHandles.dropArguments(target, pos, types...)`: **thêm tham số được chấp nhận nhưng bỏ qua** vào lời gọi handle. Handle mới **nhiều tham số hơn**; các đối số bổ sung không chuyển tới `target`.

Tên `dropArguments` thường gây nhầm: nó **không xóa tham số khỏi kiểu của handle**. Nó tạo một handle có thể *nhận* thêm đối số và bỏ qua chúng khi chuyển lời gọi vào target.

Bài tập trung vào bản chất hai phép biến đổi, vị trí `pos`, thứ tự và loại tham số, cách đọc `MethodType` trước/sau, ví dụ runnable Java 17+, cách kết hợp với receiver, cũng như lỗi phổ biến khi dùng `invokeExact`.

## 1. Mô hình chung: thay đổi hợp đồng gọi, giữ nguyên công việc của target

Hãy coi một handle có chữ ký:

```text
target: (A, B, C)R
        ^  ^  ^
        0  1  2     Chỉ số tham số bắt đầu từ 0
```

Nếu gắn một giá trị `b0` vào tham số `B`:

```text
insertArguments(target, 1, b0)

Trước: (A, B, C)R
Sau:   (A,    C)R

Người gọi mới: newHandle(a, c)
Tương đương:    target(a, b0, c)
```

Nếu thêm tham số `X`, `Y` ở vị trí 1 để bỏ qua:

```text
dropArguments(target, 1, X.class, Y.class)

Trước: (A,       B, C)R
Sau:   (A, X, Y, B, C)R

Người gọi mới: newHandle(a, x, y, b, c)
Đối số tới target: target(a, b, c)  // x, y bị bỏ qua
```

Với cả hai phép:

- `target` ban đầu **không thay đổi**; API trả về `MethodHandle` mới.
- **Kiểu trả về `R` được giữ nguyên**.
- Không gọi method đích khi chỉ **tạo** adapter bằng combinator; code đích chạy khi bạn **invoke** handle.
- Việc thay đổi danh sách kiểu tham số không cần sinh hay sửa tệp `.class` của method được bọc.
- Chúng tác động lên **tham số hiện có trong `target.type()`**, không nhất thiết là tham số bạn nhìn thấy trong khai báo Java nguồn. Ví dụ instance method handle có thể chứa receiver ở chỉ số 0.

### 1.1. So sánh nhanh

| API | Đầu vào ý tưởng | Handle kết quả | Đối số nào đến method gốc? |
| --- | --- | --- | --- |
| `insertArguments` | Gắn giá trị vào một phần của chữ ký target | **Ít** tham số hơn | Các đối số người gọi truyền cộng với các giá trị đã gắn |
| `dropArguments` | Bổ sung các kiểu được chấp nhận nhưng không dùng | **Nhiều** tham số hơn | Chỉ các đối số tương ứng với tham số target ban đầu |
| `asType` | Thay kiểu tham số/kết quả bằng phép chuyển đổi hợp lệ | Thông thường giữ số lượng tham số | Các giá trị sau khi chuyển đổi |
| `bindTo` | Gắn đối số reference đầu tiên của handle | Giảm một tham số | Giá trị reference đã gắn cùng các đối số còn lại |

`insertArguments` và `dropArguments` đều có thể dùng nối tiếp, tạo chuỗi adapter để khớp chữ ký mà một runtime dispatcher yêu cầu.

## 2. Điều kiện nền tảng: `MethodHandle`, `MethodType` và lời gọi chính xác

Các ví dụ sử dụng:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
```

Khi lookup một method, `MethodType.methodType(returnType, parameterTypes...)` mô tả kiểu trả về **trước**, kiểu tham số **sau**. Ví dụ:

```java
// Fragment: method thực tế có dạng static int sum(int a, int b).
MethodType signature = MethodType.methodType(
        int.class, int.class, int.class);
```

`MethodHandle.type()` trả một `MethodType` tương ứng với cách **gọi handle đó**. Khi biến đổi:

```text
base.type():     (int,int)int
newHandle.type(): (int)int    // Ví dụ sau khi gắn một tham số
```

`invokeExact(...)` phải khớp **toàn bộ** kiểu của handle, gồm kiểu tĩnh của từng đối số **và kiểu kết quả theo ngữ cảnh gọi**. Một ví dụ với handle `(int)int`:

```java
int result = (int) newHandle.invokeExact(5);
```

Đây là **fragment minh họa**, giả định `newHandle` là handle có kiểu `(int)int`. Nếu gọi `invokeExact(5L)` hoặc yêu cầu kết quả `Object` thay vì `int`, JVM có thể ném `WrongMethodTypeException`. Các phép combinator không tự biến `invokeExact` thành lời gọi cho phép ép kiểu tùy ý.

**Ghi nhớ:** Trước khi áp dụng mỗi combinator, đọc `target.type()`. Sau khi áp dụng, đọc tiếp `newHandle.type()` để biết đúng kiểu lời gọi cần dùng.

## 3. `insertArguments` — cố định các tham số tại vị trí cho trước

API:

```java
public static MethodHandle insertArguments(
        MethodHandle target, int pos, Object... values)
```

Cú pháp trên là **chữ ký API minh họa**, không phải đoạn chương trình độc lập.

Ý nghĩa:

1. `target` là handle gốc.
2. `pos` là **vị trí bắt đầu** trong danh sách tham số hiện tại của `target.type()`, đánh số từ 0.
3. `values` là một hoặc nhiều giá trị sẽ được gắn vào các vị trí **liên tiếp**, bắt đầu từ `pos`.
4. Khi gọi handle mới, JVM tự cung cấp các giá trị đã gắn cho target. Người gọi chỉ đưa các tham số còn lại theo đúng thứ tự.

Ví dụ:

```text
target.type()                  = (String, String, int)String

insertArguments(target, 0, "Hi ")
                               = (String, int)String

insertArguments(target, 1, "Bo", 2)
                               = (String)String

insertArguments(target, 2, 3) = (String, String)String
```

Khi gắn ở giữa, không được hiểu `pos` là vị trí theo method nguồn sau khi đã biến đổi một handle khác. Mỗi lần gọi combinator, hãy xét **kiểu của target ngay tại lần gọi đó**.

### 3.1. Các giá trị cố định phải khớp kiểu tham số

Vì `values` có kiểu `Object...`, đối số primitive như `int` được Java **boxing** thành wrapper tương ứng trước khi truyền vào API. `insertArguments` xử lý giá trị đã boxed theo kiểu tham số:

- Đối với target parameter `int`, truyền giá trị `2` (boxed thành `Integer`) là cách đúng; không tự cho rằng chuỗi `"2"` sẽ được parse.
- Với primitive `long`, truyền `2L`, không dựa vào việc `Integer` tự được nới kiểu một cách tùy ý tại bước bind.
- Với reference type, giá trị phải thích hợp cho tham số đích; kiểu không tương thích có thể gây `ClassCastException` ngay lúc tạo adapter.
- `null` không có giá trị primitive để unbox, do đó không thể dùng để bind một tham số primitive; với một reference parameter thì có thể bind `null` nếu hợp lệ.
- Index vượt phạm vi hoặc số lượng giá trị lớn hơn các tham số còn lại gây lỗi tạo adapter. Không có chuyện tự “nới” chữ ký để đủ chỗ cho các giá trị cố định.

Các giá trị được cung cấp cho adapter tại **thời điểm tạo handle**. Với primitive/wrapper bất biến, giá trị có thể xem như đã cố định; với một object/array mutable, adapter giữ **tham chiếu** tới object đó, không tự deep-copy trạng thái bên trong. Phần thực hành 4 sẽ chứng minh.

### 3.2. Binding không thay đổi logic nghiệp vụ

Nếu method gốc là:

```java
static int multiply(int number, int factor) {
    return number * factor;
}
```

Đây là fragment để minh họa. Handle `multiplyHandle` có dạng `(int,int)int`. Bind tham số thứ hai bằng `4`:

```java
MethodHandle quadruple = MethodHandles.insertArguments(
        multiplyHandle, 1, 4);
// quadruple.type(): (int)int
```

Khi gọi `quadruple(7)`, target nhận `multiply(7, 4)` và trả `28`. Không có method `quadruple(int)` mới trong source hay class file: đây là một handle đã được **áp dụng trước một phần đối số** (partial application).

### 3.3. Giới hạn phạm vi của một lần bind

Một lần `insertArguments` chỉ gắn **một đoạn tham số liên tiếp**. Nếu muốn gắn hai vị trí không liền kề, có thể gọi liên tiếp nhiều lần, nhưng phải **tính lại index** sau mỗi lần:

```text
Gốc:                  (A, B, C, D)R
Gắn B tại pos=1:      (A,    C, D)R
Gắn D còn lại pos=2:  (A,    C   )R
```

Đừng tiếp tục dùng index cũ của `D` là 3 ở bước thứ hai, vì handle lúc đó chỉ còn ba tham số với index 0, 1, 2.

## 4. Thực hành 1 — Gắn prefix, các tham số giữa/cuối và primitive

Tạo tệp **`InsertArgumentsDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class InsertArgumentsDemo {
    static String repeatName(String greeting, String name, int times) {
        return greeting + name.repeat(times);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle base = MethodHandles.lookup().findStatic(
                InsertArgumentsDemo.class, "repeatName",
                MethodType.methodType(
                        String.class, String.class, String.class, int.class));

        MethodHandle prefix = MethodHandles.insertArguments(base, 0, "Hi ");
        MethodHandle middleAndLast =
                MethodHandles.insertArguments(base, 1, "Bo", 2);
        MethodHandle count = MethodHandles.insertArguments(base, 2, 3);

        System.out.println("base: " + base.type());
        System.out.println("prefix: " + prefix.type());
        System.out.println("middle+last: " + middleAndLast.type());
        System.out.println("count: " + count.type());
        System.out.println("prefix call: "
                + (String) prefix.invokeExact("Ana", 2));
        System.out.println("middle+last call: "
                + (String) middleAndLast.invokeExact("Hey "));
        System.out.println("count call: "
                + (String) count.invokeExact("!", "go"));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac --release 17 InsertArgumentsDemo.java
java InsertArgumentsDemo
```

**Stdout chính xác:**

```text
base: (String,String,int)String
prefix: (String,int)String
middle+last: (String)String
count: (String,String)String
prefix call: Hi AnaAna
middle+last call: Hey BoBo
count call: !gogogo
```

**Phân tích:**

1. `base` nhận ba tham số `(String greeting, String name, int times)`; chữ ký trả `String`.
2. `prefix` gắn `greeting="Hi "` ở index 0, nên còn nhận `name` và `times`. Chuỗi `"Ana"` được lặp hai lần.
3. `middleAndLast` gắn **hai tham số liền nhau** từ index 1: `name="Bo"` và `times=2`. Handle mới chỉ còn `greeting`.
4. `count` gắn tham số cuối `times=3`, nên còn nhận `greeting` và `name`. Kết quả `!gogogo` cho thấy giá trị số đã cố định.
5. Không một lệnh nào sửa `base.type()` hay thay đổi phương thức `repeatName`. Có thể tạo nhiều adapter độc lập từ cùng target.

## 5. `dropArguments` — chấp nhận thêm tham số rồi bỏ qua

API phổ biến:

```java
public static MethodHandle dropArguments(
        MethodHandle target, int pos, Class<?>... valueTypes)
```

Cú pháp là chữ ký API rút gọn. API cũng có overload nhận `List<Class<?>>`.

Điểm dễ hiểu sai nhất: **`dropArguments` không hề làm giảm số tham số của handle**. Nó nhận các **kiểu tham số cần thêm**, chèn vào chữ ký của handle mới tại `pos`; khi handle mới chạy, giá trị ở các vị trí bổ sung được bỏ qua.

Ví dụ target `(String,String)String`:

```text
target: (String left, String right)String
              0          1

dropArguments(target, 0, Object.class):
        (Object ignored, String left, String right)String

dropArguments(target, 1, int.class, boolean.class):
        (String left, int ignoredA, boolean ignoredB, String right)String

dropArguments(target, 2, long.class):
        (String left, String right, long ignored)String
```

### 5.1. `pos` là vị trí chèn, không phải vị trí bỏ

Với target có `n` tham số, có thể chèn trước tham số index `0..n-1` hoặc chèn **cuối** ở index `n`. Nếu target không có tham số, chèn ở index 0.

Các tham số có sẵn của target **giữ nguyên thứ tự tương đối**. `dropArguments(target, 1, int.class, boolean.class)` chèn `int` trước, `boolean` sau, bắt đầu tại index 1. Nó không gắn giá trị mặc định nào; người gọi adapter vẫn **phải cung cấp** các đối số mới.

Nếu tham số thêm có kiểu `long` hay `double`, chúng chiếm hai parameter slots ở mức JVM. Các loại `void.class` không thể làm kiểu tham số, và chữ ký vượt giới hạn số slot sẽ bị từ chối.

### 5.2. “Ignored” không có nghĩa là biểu thức đối số không được chạy

Java đánh giá biểu thức đối số **trước khi thực hiện lời gọi**, kể cả khi adapter sẽ bỏ giá trị được tính ra. Ví dụ:

```java
String result = (String) withEvaluation.invokeExact(
        "A", expensiveOperation(), "B");
```

Đây là fragment minh họa nếu `withEvaluation.type()` là `(String,int,String)String` và `expensiveOperation()` trả `int`. Java vẫn chạy `expensiveOperation()` để lấy đối số; adapter chỉ bỏ **giá trị** của đối số sau khi đã được đánh giá.

Điều này có ý nghĩa khi đối số bị bỏ qua gây tác dụng phụ, I/O, ném exception hay tiêu tốn tài nguyên. **`dropArguments` không tránh chi phí tính đối số ở caller** và không tự kiểm chứng dữ liệu/ủy quyền trong một context object bị bỏ qua.

### 5.3. Thêm tham số vào handle không nhận đối số

`MethodHandles.constant(String.class, "OK")` tạo handle kiểu `()String`. Một framework có thể yêu cầu callback nhận `(String,int)String`; ta chèn hai tham số bị bỏ qua:

```java
MethodHandle original = MethodHandles.constant(String.class, "OK");
MethodHandle padded = MethodHandles.dropArguments(
        original, 0, String.class, int.class);
// original.type(): ()String
// padded.type():   (String,int)String
```

Đây là fragment hợp lệ trong phạm vi đã import `MethodHandles`. Khi gọi `padded` với `(String,int)`, giá trị trả về luôn là `"OK"`. Ví dụ này hữu ích khi cần khớp **giao diện callback** nhưng logic cố định không sử dụng mọi dữ liệu callback truyền tới.

## 6. Thực hành 2 — Bổ sung đối số bị bỏ qua tại nhiều vị trí

Tạo tệp **`DropArgumentsDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class DropArgumentsDemo {
    static String merge(String left, String right) {
        return left + "|" + right;
    }

    static int ignoredValue() {
        System.out.println("ignored argument expression evaluated");
        return 44;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle base = MethodHandles.lookup().findStatic(
                DropArgumentsDemo.class, "merge",
                MethodType.methodType(
                        String.class, String.class, String.class));
        MethodHandle inMiddle = MethodHandles.dropArguments(
                base, 1, int.class, boolean.class);
        MethodHandle inFront = MethodHandles.dropArguments(
                base, 0, Object.class);
        MethodHandle withEvaluation = MethodHandles.dropArguments(
                base, 1, int.class);

        System.out.println("base: " + base.type());
        System.out.println("middle: " + inMiddle.type());
        System.out.println("middle call: "
                + (String) inMiddle.invokeExact("L", 99, true, "R"));
        System.out.println("front: " + inFront.type());
        System.out.println("front call: "
                + (String) inFront.invokeExact((Object) "metadata", "left", "right"));
        System.out.println("before evaluated call");
        String evaluated = (String) withEvaluation.invokeExact(
                "A", ignoredValue(), "B");
        System.out.println("evaluated call: " + evaluated);

        MethodHandle constant = MethodHandles.constant(String.class, "OK");
        MethodHandle padded = MethodHandles.dropArguments(
                constant, 0, String.class, int.class);
        System.out.println("constant: " + constant.type());
        System.out.println("padded: " + padded.type());
        System.out.println("padded call: "
                + (String) padded.invokeExact("unused", 42));
    }
}
```

```bash
javac --release 17 DropArgumentsDemo.java
java DropArgumentsDemo
```

**Stdout chính xác:**

```text
base: (String,String)String
middle: (String,int,boolean,String)String
middle call: L|R
front: (Object,String,String)String
front call: left|right
before evaluated call
ignored argument expression evaluated
evaluated call: A|B
constant: ()String
padded: (String,int)String
padded call: OK
```

**Điểm đáng chú ý:**

- `inMiddle` có hai tham số mới `int` và `boolean`. Dù truyền `99` và `true`, method `merge` chỉ thấy `"L"` và `"R"`.
- `inFront` có tham số đầu **kiểu chính xác `Object`**. Vì `invokeExact` chú ý kiểu tĩnh, đoạn gọi sử dụng `(Object) "metadata"`; nếu biểu thức có kiểu tĩnh `String`, lời gọi có thể không khớp `(Object,String,String)String`.
- `ignoredValue()` **vẫn chạy** và in log trước dòng `evaluated call: A|B`. Chỉ giá trị `44` bị adapter bỏ.
- `padded` thêm hai tham số vào một handle `()String` và vẫn trả `"OK"`. Các tham số thêm không tác động tới kết quả.

## 7. Kết hợp `insertArguments` và `dropArguments` trên một pipeline

Nhiều ứng dụng cần hai bước cùng lúc: **cố định giá trị chính sách/receiver** và **chấp nhận một số dữ liệu framework gửi vào** nhưng target không cần.

### 7.1. Bind receiver của instance method

Khi dùng `Lookup.findVirtual` cho instance method, handle thường có **receiver ở tham số đầu tiên**:

```text
Source:              String Formatter.join(String left, String right)
Lookup type:         (String,String)String
Virtual handle type: (Formatter,String,String)String
                         ^
                       receiver
```

`insertArguments(virtual, 0, formatterInstance)` gắn receiver và trả handle `(String,String)String`. Sau đó có thể bind `right="tail"` ở index **1 của handle mới** để được `(String)String`; thêm tham số `long` bị bỏ qua ở đầu bằng `dropArguments(..., 0, long.class)` để khớp chữ ký `(long,String)String` của dispatcher.

Chú ý index đã thay đổi sau mỗi phép: receiver là index 0 ở **virtual handle**, nhưng sau bind receiver, index 0 là `left` và index 1 là `right`.

### 7.2. Thực hành 3 — Receiver, giá trị cố định và tham số context bị bỏ qua

Tạo tệp **`ComposableHandleDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class ComposableHandleDemo {
    static class Formatter {
        String join(String left, String right) {
            return left + "/" + right;
        }
    }

    static int multiply(int number, int factor) {
        return number * factor;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle virtual = lookup.findVirtual(
                Formatter.class, "join",
                MethodType.methodType(String.class, String.class, String.class));
        MethodHandle receiverBound =
                MethodHandles.insertArguments(virtual, 0, new Formatter());
        MethodHandle suffixBound =
                MethodHandles.insertArguments(receiverBound, 1, "tail");
        MethodHandle padded =
                MethodHandles.dropArguments(suffixBound, 0, long.class);

        System.out.println("virtual: " + virtual.type());
        System.out.println("receiver bound: " + receiverBound.type());
        System.out.println("suffix bound: " + suffixBound.type());
        System.out.println("padded: " + padded.type());
        System.out.println("padded call: "
                + (String) padded.invokeExact(99L, "head"));

        MethodHandle multiplyHandle = lookup.findStatic(
                ComposableHandleDemo.class, "multiply",
                MethodType.methodType(int.class, int.class, int.class));
        MethodHandle factorBound =
                MethodHandles.insertArguments(multiplyHandle, 1, 4);
        MethodHandle withRequestId =
                MethodHandles.dropArguments(factorBound, 0, String.class);

        System.out.println("multiply: " + multiplyHandle.type());
        System.out.println("factor bound: " + factorBound.type());
        System.out.println("request adapter: " + withRequestId.type());
        System.out.println("request adapter call: "
                + (int) withRequestId.invokeExact("request-42", 7));
    }
}
```

```bash
javac --release 17 ComposableHandleDemo.java
java ComposableHandleDemo
```

**Stdout chính xác:**

```text
virtual: (Formatter,String,String)String
receiver bound: (String,String)String
suffix bound: (String)String
padded: (long,String)String
padded call: head/tail
multiply: (int,int)int
factor bound: (int)int
request adapter: (String,int)int
request adapter call: 28
```

Phân tích pipeline đầu:

```text
findVirtual:
(Formatter,String,String)String
    |
    | insertArguments(..., 0, new Formatter())
    v
(String,String)String
    |
    | insertArguments(..., 1, "tail")
    v
(String)String
    |
    | dropArguments(..., 0, long.class)
    v
(long,String)String
```

Gọi `padded.invokeExact(99L, "head")`: giá trị `99L` bị bỏ qua, `"head"` trở thành `left`, `right` luôn là `"tail"` và receiver luôn là đối tượng `Formatter` đã bind.

Pipeline thứ hai minh họa một callback cần tham số `requestId`:

```text
multiply(number, factor): (int,int)int
   |
   | bind factor = 4
   v
(int)int
   |
   | add ignored String requestId at index 0
   v
(String,int)int
```

Dù callback nhận `"request-42"`, adapter không truyền requestId tới `multiply` và kết quả vẫn là `7 * 4 = 28`. Với use case cần xác thực hoặc kiểm tra requestId, **không thể dựa vào `dropArguments`** vì nó cố ý không xử lý giá trị đó.

## 8. `bindTo` so với `insertArguments`

`MethodHandle.bindTo(value)` cũng cố định một đối số nhưng chỉ hỗ trợ **tham số đầu tiên có kiểu reference**. Nó thường dùng để gắn receiver của instance method:

```java
// Fragment: virtual.type() = (Formatter,String,String)String
MethodHandle viaBindTo = virtual.bindTo(new Formatter());
MethodHandle viaInsert = MethodHandles.insertArguments(
        virtual, 0, new Formatter());
```

Hai handle tương ứng đều có chữ ký `(String,String)String`, nhưng trong ví dụ này hai lần `new Formatter()` tạo **hai receiver object khác nhau**; không nên xem hai giá trị này là “cùng receiver” chỉ vì kiểu handle giống nhau.

Sự khác nhau:

| Nhu cầu | `bindTo` | `insertArguments` |
| --- | --- | --- |
| Gắn đối số reference đầu tiên | Có | Có, dùng `pos=0` |
| Gắn đối số primitive như `int` | Không | Có, dùng wrapper tương ứng |
| Gắn tham số ở giữa/cuối | Không trực tiếp | Có, chọn `pos` |
| Gắn nhiều tham số liền nhau trong một bước | Không | Có |
| Tạo handle mới ít tham số hơn | Có | Có |

Muốn gắn receiver vào vị trí 0, cả hai có thể hợp lý. Khi xử lý các tham số khác hoặc primitive, `insertArguments` linh hoạt hơn.

## 9. Bẫy Java varargs khi bind một mảng

`insertArguments` có tham số `Object... values`, tức là **Java varargs**. Nếu muốn bind một `String[]` làm **một đối số duy nhất**, lời gọi `insertArguments(handle, 0, words)` có thể bị Java hiểu là truyền **nhiều phần tử mảng** vào varargs (vì `String[]` tương thích với `Object[]`). Khi đó số lượng giá trị bind khác dự kiến.

Cách rõ ràng là ép kiểu mảng thành **một `Object`**:

```java
MethodHandle bound = MethodHandles.insertArguments(
        original, 0, (Object) words);
```

Khi target có tham số kiểu `String[]`, adapter sẽ bind **một reference tới mảng**. Đây không phải deep copy. Mã chạy kiểm chứng dưới đây cũng cho thấy thay đổi nội dung mảng **sau khi bind** ảnh hưởng tới kết quả gọi handle.

### 9.1. Thực hành 4 — Mảng được giữ theo tham chiếu

Tạo tệp **`ArrayBindingDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class ArrayBindingDemo {
    static String join(String[] values) {
        return String.join("-", values);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle original = MethodHandles.lookup().findStatic(
                ArrayBindingDemo.class, "join",
                MethodType.methodType(String.class, String[].class));
        String[] words = {"red", "blue"};

        MethodHandle bound =
                MethodHandles.insertArguments(original, 0, (Object) words);
        System.out.println("original: " + original.type());
        System.out.println("bound: " + bound.type());
        System.out.println("first: " + (String) bound.invokeExact());

        words[0] = "green";
        System.out.println("after mutating array: "
                + (String) bound.invokeExact());
    }
}
```

```bash
javac --release 17 ArrayBindingDemo.java
java ArrayBindingDemo
```

**Stdout chính xác:**

```text
original: (String[])String
bound: ()String
first: red-blue
after mutating array: green-blue
```

Ý nghĩa:

1. Chữ ký gốc `(String[])String` có đúng **một** tham số kiểu mảng.
2. `(Object) words` đảm bảo `Object... values` nhận **một phần tử**, là chính mảng `words`.
3. Sau khi bind, `bound.type()` là `()String`, nên lời gọi `bound.invokeExact()` **không có đối số**.
4. Thay `words[0]` đổi trạng thái object được bind, dẫn đến output `green-blue`. Adapter giữ tham chiếu; nó không chụp snapshot bất biến của mảng.

Với dữ liệu cần bất biến, thực hiện **defensive copy** trước khi bind: ví dụ `String[] safe = words.clone();` rồi bind `safe`, và không làm lộ reference `safe` cho nơi có thể sửa nó. `insertArguments` chỉ cố định reference, không áp đặt bất biến cho object.

## 10. So sánh biến đổi chữ ký với biến đổi hành vi

Có hai nhóm API dễ bị nhầm:

### 10.1. `MethodType` chỉ mô tả

`MethodType.dropParameterTypes(1, 2)` **xóa một kiểu tham số khỏi danh sách mô tả**. `MethodType.insertParameterTypes(1, int.class)` **thêm một kiểu tham số vào mô tả**. Chúng không thao tác trên một handle và không tự tạo adapter có thể gọi.

### 10.2. `MethodHandles` tạo adapter có thể gọi

- `MethodHandles.insertArguments(...)` giảm các tham số của một handle vì nó đã **cung cấp giá trị** cho target.
- `MethodHandles.dropArguments(...)` tăng các tham số được handle mới chấp nhận vì nó **phớt lờ giá trị** của các tham số được thêm.
- `MethodHandles.permuteArguments(...)` thay thứ tự ánh xạ tham số, không nhất thiết cần giá trị cố định.
- `MethodHandles.filterArguments(...)` gọi handle lọc để biến đổi các đối số trước khi chuyển vào target.
- `MethodHandle.asType(...)` thay chữ ký mà caller nhìn thấy bằng các phép chuyển đổi loại hợp lệ; không có ý nghĩa “bỏ qua tham số tùy ý” như `dropArguments`.

| Nếu mục tiêu là... | Cách phù hợp |
| --- | --- |
| Khóa `factor` bằng `4` rồi chỉ truyền `number` | `insertArguments(multiplyHandle, 1, 4)` |
| Callback có thêm `requestId` nhưng target không dùng | `dropArguments(target, 0, String.class)` |
| Muốn hai tham số đổi chỗ | Xem `permuteArguments` |
| Muốn chuyển kiểu `int` sang `long` khi gọi | Xem `asType` với type hợp lệ |
| Muốn sửa **mô tả chữ ký** mà chưa có handle | `MethodType.insertParameterTypes` hoặc `dropParameterTypes` |
| Muốn gắn receiver reference đầu handle | `bindTo` hoặc `insertArguments(...,0,...)` |

Không nhầm giảm/tăng **số tham số handle** với thay đổi tham số trong method nguồn: class file của target vẫn giữ chữ ký gốc.

## 11. Bảng diễn tiến chữ ký để tự kiểm tra index

Giả sử `target.type()` là `(String,int,long)boolean`:

| Biến đổi (độc lập từ target, trừ khi ghi rõ) | Handle type sau biến đổi |
| --- | --- |
| `insertArguments(target, 0, "prefix")` | `(int,long)boolean` |
| `insertArguments(target, 1, 7)` | `(String,long)boolean` |
| `insertArguments(target, 1, 7, 9L)` | `(String)boolean` |
| `dropArguments(target, 0, Object.class)` | `(Object,String,int,long)boolean` |
| `dropArguments(target, 2, double.class)` | `(String,int,double,long)boolean` |
| `dropArguments(target, 3, Object.class)` | `(String,int,long,Object)boolean` |
| Bind `int` trước, rồi thêm `Object` ở index 0 | `(Object,String,long)boolean` |

Trong hàng cuối, adapter thứ hai lấy **type đã giảm một tham số** làm đầu vào. Đây là nguyên tắc nhất quán để tránh lỗi off-by-one khi phối hợp nhiều combinator.

### 11.1. Theo dõi bằng `handle.type()` thay vì đoán

Trong công cụ hỗ trợ dynamic invocation, nên ghi rõ từng stage:

```java
// Fragment: target/afterBind/afterDrop là các MethodHandle đã có.
System.out.println("target:    " + target.type());
System.out.println("afterBind: " + afterBind.type());
System.out.println("afterDrop: " + afterDrop.type());
```

Phần code trên là fragment không chạy độc lập. Tên biến và type in ra giúp so sánh với chữ ký callback/framework mong đợi. Không dựa vào tên method gốc để suy ra số tham số của handle đã qua adapter.

### 11.2. Kiểm tra kiểu tĩnh khi gọi `invokeExact`

Giả sử `handle.type()` là `(Object,int)String`. Với `invokeExact`, biểu thức `"metadata"` có kiểu tĩnh `String`, không phải `Object`. Dùng `(Object) "metadata"` để thể hiện đúng call-site type:

```java
// Fragment: handle.type() = (Object,int)String
String value = (String) handle.invokeExact((Object) "metadata", 3);
```

Cách diễn đạt ngắn gọn: khi chạy, object có thể là `String`, nhưng **chữ ký call-site** vẫn phải dùng `Object` nếu handle đòi `Object`. `invoke(...)` có thể cho chuyển đổi tương thích, nhưng không nên để các phép chuyển đổi ngầm che mất lỗi thiết kế adapter.

## 12. Lỗi phổ biến và cơ chế lỗi

| Hiện tượng | Nguyên nhân | Kiểm tra/sửa |
| --- | --- | --- |
| `WrongMethodTypeException` khi `invokeExact` sau `insertArguments` | Vẫn truyền lại tham số đã bind; call-site quá nhiều đối số, sai kiểu hoặc sai kiểu trả về | In `newHandle.type()` và gọi theo chữ ký **đã giảm** |
| `WrongMethodTypeException` khi `invokeExact` sau `dropArguments` | Quên truyền tham số mới hoặc truyền nhầm kiểu tĩnh | In type, thêm đúng tham số cùng index |
| `IllegalArgumentException` khi bind | `pos` ngoài phạm vi hoặc số giá trị bind vượt số tham số có sẵn | Đếm `target.type().parameterCount()` và kích thước `values` |
| `ClassCastException`/`NullPointerException` khi bind | Reference không tương thích hoặc giá trị cho primitive không phù hợp | Khớp kiểu chính xác; primitive dùng wrapper đúng loại, tránh `null` |
| `IllegalArgumentException` khi `dropArguments` | Index chèn không hợp lệ, chứa `void.class` hoặc vi phạm giới hạn chữ ký | Kiểm tra index `0..parameterCount`, kiểu hợp lệ và slot count |
| Method handle có receiver bị bind sai tham số | Quên receiver ở vị trí 0 của handle `findVirtual` | Đọc `virtual.type()`, bind index 0 trước khi bind tham số source |
| Truyền `String[]` vào `insertArguments` và bị hiểu là nhiều values | Varargs `Object...` trải các phần tử mảng | Dùng `(Object) array` để bind **một mảng** |
| Đối số “ignored” vẫn gây side effect | Java đánh giá expression trước khi adapter bỏ giá trị | Giữ đối số đầu vào thuần hoặc điều chỉnh caller; không kỳ vọng adapter ngăn đánh giá |
| Bind object rồi thấy hành vi đổi về sau | Đã bind **tham chiếu** tới object mutable, không clone state | Defensive copy/thiết kế immutable |
| Nhầm `dropArguments` với `MethodType.dropParameterTypes` | Hai API có ngữ nghĩa khác: adapter chấp nhận thêm versus descriptor mất kiểu | Phân biệt class `MethodHandles` và `MethodType` |
| Target có kiểu trả về `int` nhưng caller gán vào `Object` | `invokeExact` ràng buộc cả kiểu return theo ngữ cảnh | Dùng cast/biến `int` đúng type hoặc adapter phù hợp |

Có thể gặp lỗi ngay **lúc tạo adapter** khi tham số/giá trị không hợp lệ; còn `WrongMethodTypeException` ở **lúc gọi** cho thấy chữ ký lời gọi không khớp handle. Đừng bắt các lỗi này một cách im lặng rồi tiếp tục coi dynamic invocation thành công.

### 12.1. Một ví dụ index sai

Giả sử handle ban đầu có `(Formatter,String,String)String` và bạn bind receiver:

```java
MethodHandle noReceiver =
        MethodHandles.insertArguments(virtual, 0, formatter);
// noReceiver.type(): (String,String)String
```

Nếu muốn bind `right`, vị trí đúng trên `noReceiver` là `1`. Dùng index `2` (vị trí `right` trong handle **cũ**) sẽ nằm ngoài phạm vi hoặc tạo sai phép bind. Mọi phép tiếp theo đều phải tính trên type **mới nhất**.

### 12.2. Lời gọi “bỏ qua context” có giới hạn thiết kế

Một chữ ký callback `(RequestContext,int)int` có thể được tạo từ `(int)int` bằng `dropArguments(target, 0, RequestContext.class)`. Nhưng nếu target cần xác thực context, kiểm tra metadata, tracing hoặc điều chỉnh business result, **không được dùng phép bỏ qua**. Bạn cần một method thật hoặc một filter/guard xử lý context trước khi gọi target.

Tương tự, `insertArguments` có thể bind credential, cấu hình hoặc service reference; việc bind không tự bảo vệ giá trị đó khỏi tiết lộ hoặc thay đổi ngoài ý muốn. Cần thiết kế lifecycle và quyền truy cập ở tầng ứng dụng.

## 13. Khi nào dùng trong ứng dụng thật?

### 13.1. Tạo adapter cho callback có chữ ký cố định

Một thư viện yêu cầu callback kiểu `(String requestId, int amount)int` nhưng nghiệp vụ chỉ cần `amount` và một `factor` cố định. Pipeline:

```text
core multiply(amount, factor)       (int,int)int
         |
         | bind factor=4 ở index 1
         v
quadruple(amount)                   (int)int
         |
         | dropArguments index 0, String.class
         v
callback(requestId, amount)         (String,int)int
```

Ví dụ ở `ComposableHandleDemo` làm chính xác việc này. Ưu điểm là chọn adapter ở lúc cấu hình rồi tái sử dụng; không cần tạo lớp wrapper thủ công cho mọi cặp chữ ký đơn giản.

### 13.2. Bind receiver của một dịch vụ đã cấu hình

Đối với method handle `(Service, Input)Output`, nếu chỉ có một instance service sẽ xử lý tất cả lời gọi, `insertArguments(handle, 0, service)` trả `(Input)Output`. Nhưng việc giữ reference cũng kéo theo lifecycle: adapter sẽ còn tham chiếu tới service chừng nào adapter còn được tham chiếu. Nếu service có trạng thái mutable/concurrent, việc bind không cung cấp thread safety hay đảm bảo snapshot.

### 13.3. Giảm duplication của lớp adapter

Khi điều phối nhiều tác vụ theo cấu hình, một bộ dispatcher có thể dùng `MethodHandle` combinator để biến các callable có chữ ký khác nhau thành một **chữ ký thống nhất** (uniform signature). Tuy nhiên không phải mọi kiểu khác biệt đều giải quyết bằng `insertArguments` và `dropArguments`: khi cần đổi thứ tự, ép kiểu, lọc tham số hoặc kết hợp nhiều lời gọi, chọn combinator phù hợp và kiểm tra `handle.type()` sau từng bước.

## 14. Câu hỏi tự kiểm tra

1. Vì sao `dropArguments` mang tên “drop” nhưng lại **tăng** `parameterCount()`?
2. Với `target.type() = (String,int,long)void`, `insertArguments(target, 1, 5)` tạo type nào? Người gọi còn truyền `int` không?
3. Với type `(String,int)String`, kết quả `dropArguments(target, 2, boolean.class)` có chữ ký gì?
4. Cho `virtual.type() = (Editor,String)boolean`. Muốn cố định receiver, nên dùng `pos` nào? Sau đó, tham số đầu của handle mới là gì?
5. Tại sao gọi `insertArguments(handle, 0, words)` với `words` kiểu `String[]` có nguy cơ bind nhiều giá trị?
6. `dropArguments` có làm cho `expensive()` được truyền vào vị trí bỏ qua không chạy không? Vì sao?
7. Vì sao `String result = (String) handle.invokeExact("x", 2)` có thể lỗi khi `handle.type()` là `(Object,int)String`?
8. Sau `insertArguments(target, 1, 4)`, có phải method gốc được sửa bytecode hay bản thân `target.type()` thay đổi không?
9. Với `target.type()=(int,int)int`, muốn thêm `String requestId` bị bỏ qua ở đầu sau khi đã bind tham số cuối, viết hai bước nào?
10. Khi bind một `List` mutable, những thay đổi về sau đối với list có thể ảnh hưởng lời gọi handle không?
11. `bindTo` có thể dùng để cố định một tham số `int` ở giữa chữ ký không?
12. Khi nào bỏ qua một đối số context là ý tưởng sai trong một pipeline callback?

**Gợi ý đáp án:**

1. Vì nó **bỏ qua giá trị khi chuyển tới target**, còn handle mới vẫn nhận thêm tham số.
2. `(String,long)void`; caller không truyền lại `int` vì giá trị đã bind.
3. `(String,int,boolean)String`; `pos=2` chèn ở cuối.
4. `pos=0`; tham số đầu còn lại là `String`.
5. `Object...` có thể diễn giải `String[]` thành nhiều varargs elements; dùng `(Object) words`.
6. Không; Java phải tính expression đối số trước lời gọi, adapter chỉ bỏ giá trị đã tính.
7. `invokeExact` so khớp kiểu **tĩnh** `Object`; literal `"x"` có kiểu tĩnh `String`. Dùng `(Object) "x"`.
8. Không; đó là một adapter mới, method gốc và target cũ vẫn giữ nguyên.
9. `bound = MethodHandles.insertArguments(target, 1, 4)`; tiếp theo `callback = MethodHandles.dropArguments(bound, 0, String.class)`.
10. Có; adapter giữ reference tới list, không clone ngầm.
11. Không; `bindTo` chỉ bind tham số đầu có kiểu reference; dùng `insertArguments`.
12. Khi cần xác thực/kiểm tra/quản lý context, vì dropped argument không bao giờ đến logic đích.

## 15. Tài liệu chuẩn để tra cứu

- [Java SE 21 API — `MethodHandles.insertArguments`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html#insertArguments(java.lang.invoke.MethodHandle,int,java.lang.Object...)): định nghĩa bind các giá trị cố định, vùng `pos`, kiểu tham số và giá trị boxed.
- [Java SE 21 API — `MethodHandles.dropArguments`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html#dropArguments(java.lang.invoke.MethodHandle,int,java.lang.Class...)): tạo handle nhận đối số mới nhưng bỏ qua.
- [Java SE 21 API — `MethodHandle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, `bindTo` và chuyển đổi chữ ký.
- [Java SE 21 API — `MethodType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html): kiểu đối số/kết quả, `parameterCount()` và đối tượng mô tả bất biến.
- [Java SE 21 API — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): cách lấy method handle của static/virtual method và ảnh hưởng của receiver.

Khi thiết kế pipeline MethodHandle, hãy dùng hai quy tắc: **`insertArguments` gắn sẵn giá trị nên người gọi truyền ít hơn**; **`dropArguments` thêm chỗ nhận giá trị rồi bỏ qua nên người gọi truyền nhiều hơn**. Dùng `handle.type()` sau từng bước và kiểm tra lại `invokeExact` theo chữ ký mới sẽ giúp bạn biến đổi lời gọi chính xác mà không cần thay đổi method gốc.