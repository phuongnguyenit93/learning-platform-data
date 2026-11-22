# Các bộ biến đổi zero, empty và dropArgumentsToMatch

`MethodHandles` cung cấp các factory và combinator để tạo hoặc điều chỉnh `MethodHandle` mà không cần viết một method adapter riêng cho từng chữ ký. Ba API `zero()`, `empty()` và `dropArgumentsToMatch()` giải quyết ba nhu cầu khác nhau: tạo handle trả về giá trị mặc định, tạo handle bỏ qua mọi đối số với chữ ký định trước, và thêm các tham số giả để một handle khớp với danh sách kiểu tham số lớn hơn.

Để dùng đúng các API này, cần hiểu `MethodType` là hợp đồng kiểu của một handle: kiểu trả về và thứ tự chính xác của các tham số. Các combinator tạo một handle mới với kiểu có thể khác handle gốc; chúng không sửa method gốc và không tự chuyển đổi các kiểu không khớp.

## Mục tiêu

- Hiểu `MethodHandles.zero(Class<?>)` và giá trị mặc định mà handle trả về.
- Dùng `MethodHandles.empty(MethodType)` để tạo handle nhận tham số nhưng bỏ qua chúng.
- Phân biệt `zero()` với `empty()` và `constant()`.
- Dùng `dropArgumentsToMatch()` để làm khớp một handle với danh sách kiểu tham số có sẵn.
- Hiểu chính xác vai trò của `skip`, `newTypes` và `pos`.
- Đọc và kiểm tra chữ ký trước/sau biến đổi bằng `MethodHandle.type()`.
- Tránh lỗi kiểu khi gọi `invokeExact()`.

## 1. MethodHandle và MethodType

`MethodHandle` là tham chiếu có kiểu tới một thao tác có thể gọi được, chẳng hạn method, constructor, field accessor hoặc một handle được tạo bởi combinator. Mỗi handle có một `MethodType` xác định kiểu trả về và các kiểu tham số theo thứ tự.

Ví dụ:

~~~java
MethodType type = MethodType.methodType(
    String.class, String.class, int.class
);
~~~

Chữ ký tương ứng là:

~~~text
(String, int)String
~~~

Đọc chữ ký của handle:

~~~java
System.out.println(handle.type());
~~~

Khi kết hợp nhiều handle, hãy xem `type()` là cách kiểm tra hợp đồng của kết quả. Các combinator thường kiểm tra kiểu ngay khi tạo handle; nếu các danh sách kiểu không tương thích, chúng ném `IllegalArgumentException` thay vì tạo một handle có thể gọi sai.

## 2. zero(): handle không tham số trả về giá trị mặc định

API:

~~~java
MethodHandle zero = MethodHandles.zero(Class<?> type);
~~~

`zero(type)` tạo một handle không có tham số, có kiểu trả về là `type`. Mỗi lần gọi, handle trả về giá trị mặc định của kiểu đó và không có side effect.

Ví dụ:

~~~java
MethodHandle zeroInt = MethodHandles.zero(int.class);
int value = (int) zeroInt.invokeExact();
System.out.println(value);
~~~

Output:

~~~text
0
~~~

### 2.1. Giá trị mặc định theo kiểu

| Kiểu trả về | Giá trị của zero() |
| --- | --- |
| `boolean` | `false` |
| `byte`, `short`, `int` | `0` |
| `long` | `0L` |
| `char` | `\u0000` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| Kiểu tham chiếu | `null` |
| `void` | Không có giá trị trả về |

`zero(String.class)` có kiểu `()String` và trả về `null`. `zero(int.class)` có kiểu `()int` và trả về `0`. `zero(void.class)` tạo handle `()void` không trả về giá trị.

`zero()` là một factory cho handle hằng mặc định, không phải lời gọi một method được chỉ định và cũng không phải handle có thể thay đổi giá trị.

### 2.2. zero() và constant() khác nhau

`MethodHandles.constant(type, value)` tạo handle không tham số trả về một giá trị cụ thể đã cho. `zero(type)` tạo handle trả về giá trị mặc định của kiểu.

| API | Giá trị trả về |
| --- | --- |
| `zero(int.class)` | Luôn là `0` |
| `constant(int.class, 42)` | Luôn là `42` |
| `zero(String.class)` | `null` |
| `constant(String.class, "ready")` | `"ready"` |

`constant()` cần giá trị tương thích với kiểu trả về. `zero()` không nhận giá trị; nó xác định giá trị mặc định từ kiểu.

## 3. empty(): handle bỏ qua mọi tham số

API:

~~~java
MethodHandle empty = MethodHandles.empty(MethodType type);
~~~

`empty(type)` tạo handle có đúng `MethodType` được yêu cầu. Handle nhận đủ các đối số theo chữ ký nhưng bỏ qua tất cả, không thực hiện công việc và trả giá trị mặc định phù hợp với kiểu trả về:

- Kiểu trả về primitive: trả zero value.
- Kiểu trả về tham chiếu: trả `null`.
- Kiểu trả về `void`: không trả giá trị.

Ví dụ handle nhận `String` và `int` nhưng không dùng chúng:

~~~java
MethodType type = MethodType.methodType(
    String.class, String.class, int.class
);
MethodHandle empty = MethodHandles.empty(type);
String result = (String) empty.invokeExact("ignored", 7);
System.out.println(result == null);
~~~

Output:

~~~text
true
~~~

### 3.1. Quan hệ giữa zero() và empty()

Về ngữ nghĩa, `empty(type)` tương đương tạo một `zero()` cho kiểu trả về rồi thêm các tham số giả để khớp chữ ký:

~~~java
MethodHandle empty = MethodHandles.dropArguments(
    MethodHandles.zero(type.returnType()),
    0,
    type.parameterList()
);
~~~

Điều này giải thích sự khác nhau:

- `zero(int.class)` có chữ ký `()int`: không nhận đối số.
- `empty(methodType(int.class, String.class))` có chữ ký `(String)int`: nhận một chuỗi nhưng bỏ qua nó và trả `0`.

### 3.2. Khi nào dùng empty()?

`empty()` hữu ích khi cần một handle dự phòng có cùng chữ ký với một handle khác, nhưng nhánh đó không cần thực hiện công việc.

Ví dụ, `guardWithTest(test, target, fallback)` yêu cầu hai nhánh target và fallback có kiểu tương thích. Có thể dùng `empty(target.type())` làm nhánh fallback nếu hành vi mong muốn là bỏ qua lời gọi và trả giá trị mặc định:

~~~java
MethodHandle fallback = MethodHandles.empty(target.type());
MethodHandle guarded = MethodHandles.guardWithTest(
    test, target, fallback
);
~~~

Đây chỉ là lựa chọn khi no-op/default result đúng với logic ứng dụng. Nếu nhánh fallback cần báo lỗi, trả giá trị nghiệp vụ hoặc ghi log, hãy tạo handle fallback riêng.

## 4. dropArgumentsToMatch(): thêm tham số giả để khớp chữ ký

API Java 9:

~~~java
MethodHandle dropArgumentsToMatch(
    MethodHandle target,
    int skip,
    List<Class<?>> newTypes,
    int pos
);
~~~

`dropArgumentsToMatch()` tạo adapter cho `target` để danh sách tham số của handle kết quả phù hợp với một danh sách kiểu có sẵn (`newTypes`). Nếu cần, API chèn thêm các tham số giả; các tham số mới được thêm sẽ bị bỏ qua trước khi gọi target.

API này giữ nguyên kiểu trả về của target. Nó không chuyển đổi kiểu của phần tham số cần khớp và không thay đổi thứ tự của các tham số đã khớp.

### 4.1. Ý nghĩa từng đối số

| Đối số | Ý nghĩa |
| --- | --- |
| `target` | Handle gốc cần điều chỉnh |
| `skip` | Số tham số đầu tiên của target được giữ nguyên, không tham gia bước matching |
| `newTypes` | Danh sách kiểu tham số mà handle kết quả cần tương thích |
| `pos` | Vị trí trong `newTypes` nơi phần tham số còn lại của target phải bắt đầu khớp |

Phần tham số của target sau `skip` phải khớp chính xác với một đoạn liên tiếp của `newTypes`, bắt đầu tại `pos`.

### 4.2. Quy tắc tạo chữ ký kết quả

Có thể biểu diễn quy tắc bằng hai danh sách:

- Target: `S..., M...` — `S` là `skip` tham số đầu tiên được giữ nguyên; `M` là phần tham số cần khớp.
- `newTypes`: `P..., M..., A...` — `P` là các kiểu đứng trước vị trí `pos`; `M` là đoạn khớp; `A` là các kiểu còn lại sau đoạn khớp.

Handle kết quả có danh sách tham số:

~~~text
S..., P..., M..., A...
~~~

Các kiểu `P` và `A` được chèn thành tham số giả như `dropArguments()`. Khi gọi handle kết quả, giá trị ở các vị trí giả bị bỏ qua; chỉ các tham số được giữ và đoạn `M` được chuyển vào target.

### 4.3. Ví dụ khớp ở giữa danh sách

Giả sử target có kiểu:

~~~text
(String)String
~~~

Ta muốn handle kết quả có kiểu:

~~~text
(int, String, long)String
~~~

Đoạn `String` của target nằm ở vị trí thứ hai trong danh sách mới. Dùng `skip = 0` và `pos = 1`:

~~~java
MethodHandle adapted = MethodHandles.dropArgumentsToMatch(
    target,
    0,
    Arrays.asList(int.class, String.class, long.class),
    1
);
~~~

Handle kết quả nhận ba đối số. `int` và `long` là tham số giả, còn `String` được chuyển vào target.

~~~java
String result = (String) adapted.invokeExact(7, "hello", 99L);
~~~

Nếu target nối thêm `"value="` vào chuỗi, kết quả là `value=hello`. Hai giá trị `7` và `99L` bị bỏ qua.

### 4.4. Ý nghĩa của skip

`skip` cho phép giữ lại một số tham số đầu tiên của target trước khi bắt đầu matching.

Ví dụ target có kiểu:

~~~text
(Request, String)String
~~~

Đặt `skip = 1` nghĩa là giữ nguyên tham số `Request`. Phần còn lại `(String)` sẽ được khớp vào `newTypes` tại vị trí `pos`.

Nếu `newTypes` là `[int, String, long]` và `pos = 1`, kiểu kết quả là:

~~~text
(Request, int, String, long)String
~~~

`Request` là tham số gốc được giữ lại; `int` và `long` là tham số giả được chèn trước/sau đoạn `String` được khớp.

## 5. So sánh dropArguments() và dropArgumentsToMatch()

Hai API cùng có thể tạo tham số giả, nhưng cách chỉ định khác nhau:

| API | Cách xác định tham số được thêm |
| --- | --- |
| `dropArguments(target, pos, types)` | Chỉ rõ vị trí chèn và danh sách kiểu cần bỏ qua |
| `dropArgumentsToMatch(target, skip, newTypes, pos)` | Cung cấp danh sách kiểu đích và đoạn kiểu phải khớp; API tự chèn các kiểu còn thiếu |

Dùng `dropArguments()` khi vị trí và kiểu tham số giả đã biết rõ. Dùng `dropArgumentsToMatch()` khi cần làm một handle phù hợp với một danh sách tham số đã có, ví dụ chữ ký chung mà nhiều handle trong một combinator phải tuân theo.

`dropArgumentsToMatch()` không xóa tham số thật khỏi target. Nó thêm các vị trí giả vào adapter để target có thể được gọi từ một chữ ký rộng hơn.

## 6. Kiểm tra MethodType trước và sau khi biến đổi

Đừng đoán chữ ký của handle sau khi kết hợp. Hãy in `type()` để xác nhận:

~~~java
System.out.println("target type: " + target.type());
System.out.println("adapted type: " + adapted.type());
~~~

Với ví dụ khớp ở giữa:

~~~text
target type: (String)String
adapted type: (int,String,long)String
~~~

Kiểu trả về không đổi. Danh sách tham số mới bao gồm các kiểu giả trước và sau tham số `String` thật.

## 7. invokeExact() và kiểu đối số

`MethodHandle.invokeExact()` là signature-polymorphic. Kiểu mà compiler suy ra tại call site phải khớp chính xác với kiểu handle. Ví dụ:

~~~java
int value = (int) zeroInt.invokeExact();
String text = (String) zeroText.invokeExact();
~~~

Với `invokeExact()`, kiểu trả về cũng là một phần của chữ ký call site. Nếu biểu thức được compiler suy ra là `Object` trong khi handle trả `String`, có thể nhận `WrongMethodTypeException`.

Đối số primitive cũng cần đúng kiểu: `7` là `int`, còn `99L` là `long`. Nếu muốn chuyển đổi kiểu linh hoạt hơn, `invoke()` có thể thực hiện các phép chuyển đổi cho phép theo quy tắc MethodHandle, nhưng không nên dùng nó để che giấu một chữ ký sai.

Trước khi gọi, kiểm tra:

1. Số lượng đối số.
2. Thứ tự kiểu tham số.
3. Kiểu primitive hay reference.
4. Kiểu trả về tại call site nếu dùng `invokeExact()`.

## 8. Lỗi và điều kiện không hợp lệ

| Tình huống | Kết quả | Cách xử lý |
| --- | --- | --- |
| `type` truyền cho `zero()` là null | `NullPointerException` | Truyền một `Class<?>` hợp lệ |
| `MethodType` truyền cho `empty()` là null | `NullPointerException` | Tạo MethodType trước khi gọi |
| `newTypes` hoặc phần tử trong list là null | `NullPointerException` | Kiểm tra danh sách kiểu |
| `newTypes` chứa `void.class` | `IllegalArgumentException` | `void` chỉ được dùng làm kiểu trả về, không làm kiểu tham số |
| `skip` âm hoặc lớn hơn số tham số target | `IllegalArgumentException` | Chọn số tham số đầu cần giữ trong phạm vi arity |
| `pos` âm hoặc lớn hơn kích thước `newTypes` | `IllegalArgumentException` | Chọn vị trí bắt đầu matching hợp lệ |
| Đoạn kiểu ở `newTypes` không khớp target sau skip | `IllegalArgumentException` | Đảm bảo các `Class<?>` khớp chính xác và đúng thứ tự |
| Call site không khớp chữ ký khi dùng `invokeExact()` | `WrongMethodTypeException` | Kiểm tra `MethodHandle.type()` và kiểu biểu thức gọi |

`dropArgumentsToMatch()` kiểm tra tương thích kiểu khi tạo adapter. Nếu đoạn kiểu không khớp, không có cơ chế tự đoán, reorder hoặc convert kiểu.

## 9. Ví dụ hoàn chỉnh chạy trên Java 9

Chương trình sau kiểm tra cả ba API:

- `zero(int.class)` trả về `0`; `zero(String.class)` trả về `null`.
- `empty()` bỏ qua tham số; với return type `void` thì không trả giá trị, với return type `String` thì trả `null`.
- `dropArgumentsToMatch()` thêm tham số giả trước và sau tham số `String` thật để tạo chữ ký `(int,String,long)String`.

**Tệp:** `MethodHandleZeroEmptyDropMatchDemo.java`

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Arrays;

public class MethodHandleZeroEmptyDropMatchDemo {
    private static String label(String value) {
        return "value=" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle zeroInt = MethodHandles.zero(int.class);
        MethodHandle zeroText = MethodHandles.zero(String.class);
        System.out.println("zero int: " + (int) zeroInt.invokeExact());
        System.out.println("zero reference is null: "
            + ((String) zeroText.invokeExact() == null));

        MethodHandle emptyVoid = MethodHandles.empty(
            MethodType.methodType(void.class, String.class, int.class));
        emptyVoid.invokeExact("ignored", 7);
        System.out.println("empty void: completed");

        MethodHandle emptyText = MethodHandles.empty(
            MethodType.methodType(String.class, String.class, int.class));
        System.out.println("empty reference is null: "
            + ((String) emptyText.invokeExact("ignored", 7) == null));

        MethodHandle target = MethodHandles.lookup().findStatic(
            MethodHandleZeroEmptyDropMatchDemo.class,
            "label",
            MethodType.methodType(String.class, String.class)
        );
        MethodHandle adapted = MethodHandles.dropArgumentsToMatch(
            target,
            0,
            Arrays.asList(int.class, String.class, long.class),
            1
        );

        System.out.println("target type: " + target.type());
        System.out.println("adapted type: " + adapted.type());
        System.out.println("adapted result: "
            + (String) adapted.invokeExact(7, "hello", 99L));
    }
}
~~~

Biên dịch và chạy với JDK 9 trở lên:

~~~text
javac --release 9 MethodHandleZeroEmptyDropMatchDemo.java
java MethodHandleZeroEmptyDropMatchDemo
~~~

Output:

~~~text
zero int: 0
zero reference is null: true
empty void: completed
empty reference is null: true
target type: (String)String
adapted type: (int,String,long)String
adapted result: value=hello
~~~

Giải thích:

1. `zeroInt` có kiểu `()int`; không có tham số và trả `0`.
2. `zeroText` có kiểu `()String`; không có tham số và trả `null`.
3. `emptyVoid` có kiểu `(String,int)void`; nhận hai tham số nhưng không thực hiện hành động.
4. `emptyText` có kiểu `(String,int)String`; bỏ qua hai tham số và trả `null`.
5. `target` trỏ tới method `label(String)` nên có kiểu `(String)String`.
6. `dropArgumentsToMatch()` đặt `String` vào vị trí `pos = 1`, chèn `int` trước và `long` sau, tạo handle `(int,String,long)String`.
7. Khi gọi, chỉ chuỗi `"hello"` được chuyển tới `label`; hai tham số còn lại bị bỏ qua.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nghĩ `zero()` nhận tham số khi gọi | Nhầm kiểu factory với chữ ký handle | `zero(type)` luôn tạo handle không tham số |
| Nghĩ `empty()` không nhận đối số | Nhầm với `zero()` | `empty()` giữ nguyên toàn bộ tham số của MethodType nhưng bỏ qua chúng |
| Nghĩ `empty()` luôn trả `null` | Bỏ qua kiểu trả về | Primitive trả zero value, reference trả null, void không trả giá trị |
| Dùng `zero()` khi cần chữ ký có tham số | `zero()` chỉ tạo `()T` | Dùng `empty(MethodType)` hoặc thêm tham số bằng combinator |
| Nhầm `dropArgumentsToMatch()` có ba đối số | Bỏ sót tham số cuối | Java 9 có bốn đối số: target, skip, newTypes, pos |
| Đặt `pos` theo vị trí trong target | `pos` là vị trí trong `newTypes` | Tính vị trí bắt đầu của đoạn kiểu khớp trong danh sách mới |
| Cho rằng `skip` là số tham số của newTypes | `skip` đếm tham số đầu target được giữ nguyên | Đếm từ đầu danh sách tham số target |
| Nghĩ combinator tự chuyển kiểu | Matching yêu cầu kiểu tương ứng khớp chính xác | Dùng adapter chuyển kiểu riêng nếu thực sự cần |
| Không kiểm tra kiểu kết quả | Chữ ký đã thay đổi sau khi combinator chạy | In `type()` trước khi invoke |
| Gọi `invokeExact()` với kiểu trả về suy luận sai | Call site không khớp MethodType | Ép kiểu trả về đúng kiểu của handle |

## 11. Quy tắc thực hành

1. Dùng `zero(type)` khi cần handle `()type` trả giá trị mặc định.
2. Dùng `empty(methodType)` khi cần handle có chữ ký đầy đủ nhưng bỏ qua mọi đối số.
3. Dùng `constant(type, value)` khi cần trả một giá trị cụ thể thay vì giá trị mặc định.
4. Dùng `dropArguments()` khi vị trí và kiểu tham số giả đã biết.
5. Dùng `dropArgumentsToMatch()` khi cần khớp target với một danh sách kiểu tham số có sẵn.
6. Ghi nhớ `dropArgumentsToMatch(target, skip, newTypes, pos)` có bốn đối số trong Java 9.
7. Xác định `skip` từ đầu danh sách target và `pos` từ đầu danh sách `newTypes`.
8. Đảm bảo đoạn kiểu cần khớp giống hệt về kiểu và thứ tự.
9. In `MethodHandle.type()` sau mỗi bước kết hợp phức tạp.
10. Dùng `invokeExact()` khi call site biết chính xác chữ ký và giữ kiểu trả về đúng.

## 12. Tự kiểm tra

- `zero(int.class)` có chữ ký gì? `()int`.
- `zero(String.class)` trả về gì? `null`.
- `empty((String,int)void)` làm gì? Nhận hai tham số, bỏ qua chúng và không trả kết quả.
- `empty((String,int)String)` trả gì? `null`.
- `empty()` có thể hiểu như tổ hợp nào? `dropArguments(zero(returnType), 0, parameterList)`.
- `dropArgumentsToMatch()` trong Java 9 có bao nhiêu đối số? Bốn.
- `skip` chỉ gì? Số tham số đầu của target được giữ nguyên, không tham gia matching.
- `pos` chỉ gì? Vị trí trong `newTypes` nơi đoạn tham số còn lại của target phải khớp.
- Với target `(String)String`, newTypes `[int,String,long]`, pos=1, kiểu kết quả là gì? `(int,String,long)String`.
- Các tham số giả được truyền cho target không? Không; chúng bị bỏ qua.
- `dropArgumentsToMatch()` có tự convert hoặc reorder kiểu không? Không.
- Làm sao xác nhận chữ ký mới? Gọi `adapted.type()`.

Điểm cốt lõi: **`zero()` tạo handle không tham số trả giá trị mặc định; `empty()` giữ chữ ký nhưng bỏ qua mọi tham số; `dropArgumentsToMatch()` thêm tham số giả để khớp một danh sách kiểu có sẵn.** Luôn kiểm tra `MethodType` trước khi gọi handle.