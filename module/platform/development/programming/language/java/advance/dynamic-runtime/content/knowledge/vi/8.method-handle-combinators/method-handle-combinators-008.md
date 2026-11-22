# 8.8 Mô tả vòng lặp bằng loop, countedLoop và iteratedLoop

`java.lang.invoke.MethodHandles` không chỉ kết hợp các lời gọi theo kiểu `filterArguments`, `guardWithTest` hoặc `foldArguments`; nó còn có **loop combinators** để biểu diễn vòng lặp hoàn toàn bằng `MethodHandle`. Ba API trọng tâm:

- **`MethodHandles.loop(...)`** — tổ hợp một hoặc nhiều *clause*, mỗi clause có các handle `init`, `step`, `pred`, `fini`. Phù hợp khi có nhiều biến trạng thái và logic thoát phức tạp.
- **`MethodHandles.countedLoop(...)`** — vòng lặp có bộ đếm nguyên `int`, với số lượt hoặc đoạn chỉ số xác định. Phù hợp khi số vòng/giới hạn đã biết hoặc tính được từ tham số.
- **`MethodHandles.iteratedLoop(...)`** — lần lượt lấy phần tử từ `Iterator` (mặc định từ một `Iterable`). Phù hợp khi đầu vào là tập phần tử cần xử lý.

Cả ba tồn tại từ Java 9 và sử dụng được trên **Java 17+**. Chúng *tạo ra một handle mới mô tả điều khiển luồng*, chứ không lập tức chạy vòng lặp khi gọi factory. Vòng lặp thực thi khi bạn gọi `handle.invokeExact(...)` hoặc `handle.invoke(...)`.

## 1. Bản đồ tư duy: một loop handle nhận đầu vào, giữ trạng thái, trả kết quả

~~~text
                MethodHandles factory
     handles init / step / pred / fini / iterator
                         |
                         v
                 MethodHandle loop
                 type: (A...)R
                         |
                   invokeExact(a...)
                         |
           +-------------+--------------+
           |                            |
     vòng lặp hoạt động            kết thúc vòng
     trên state (V...)           trả R / void
           |
     gọi các handle con
~~~

Có ba nhóm kiểu dễ bị nhầm:

| Ký hiệu | Ý nghĩa | Đi đâu trong chữ ký? |
| --- | --- | --- |
| `A...` | **External arguments**, đối số bất biến truyền vào loop khi gọi | Là tham số của loop handle `(A...)R`; cũng có thể được chuyển tới các clause |
| `V...` | **Loop variables**, biến trạng thái cập nhật sau mỗi bước | Nội bộ vòng lặp; các handle `step`/`pred`/`fini` có thể nhận chúng, nhưng chúng **không** tự biến thành tham số công khai của loop |
| `R` | Giá trị cuối của loop | Kiểu trả về của loop handle; ở `countedLoop` và `iteratedLoop` thường là `V` của accumulator |

Một loop combinator **không gọi trực tiếp mã Java dạng `for` hoặc `while` được bạn truyền dưới dạng chuỗi**. Bạn chuẩn bị những `MethodHandle` có chữ ký chính xác; combinator xác minh và ghép chúng thành một phương thức có thể gọi.

### So sánh nhanh

| Điểm | `loop` | `countedLoop` | `iteratedLoop` |
| --- | --- | --- | --- |
| Điều kiện tiếp tục | Một hoặc nhiều `pred` trả `boolean` | Bộ đếm `i` so với số lượt/giới hạn | `Iterator.hasNext()` |
| Điều kiện thoát | `pred` trả `false`; gọi `fini` cùng clause | Hết chỉ số/số vòng | Iterator hết phần tử |
| Trạng thái | Nhiều clause, nhiều kiểu `V1, V2...` | Bộ đếm `int` và accumulator tùy chọn `V` | Giá trị phần tử `T` và accumulator tùy chọn `V` |
| Hàm cập nhật | `step` của mỗi clause | `body(V,i,A...)` | `body(V,T,A...)` |
| Độ phức tạp | Linh hoạt nhất, khó ghép đúng kiểu nhất | Ít boilerplate hơn | Diễn đạt duyệt phần tử tự nhiên |
| Chữ ký kết quả | `(A...)R` với `R` từ `fini` | `(A...)V` hoặc `void` | `(A...)V` hoặc `void` |

## 2. `MethodHandles.loop` — tổng quát nhất, nhưng phải hiểu clause và thứ tự

Khai báo API:

~~~java
public static MethodHandle loop(MethodHandle[]... clauses)
~~~

Mỗi clause là một mảng `MethodHandle[]` từ 0 đến 4 phần tử, được hiểu theo thứ tự:

~~~text
{ init, step, pred, fini }
    |      |      |      |
    |      |      |      +--> tạo giá trị trả về khi pred của clause này là false
    |      |      +---------> quyết định tiếp tục / dừng (boolean)
    |      +----------------> cập nhật biến vòng lặp của clause (nếu có)
    +-----------------------> tạo giá trị state ban đầu
~~~

Các vị trí sau có thể bỏ qua bằng `null`. Clause ngắn hơn 4 phần tử được bổ sung các vị trí `null` ở cuối. Ví dụ `new MethodHandle[]{null, increment}` chỉ cung cấp `step`, để `init` mặc định và không có `pred`/`fini` riêng.

Một lời gọi mẫu:

~~~java
MethodHandle loop = MethodHandles.loop(
        new MethodHandle[] { null, increment },
        new MethodHandle[] { seed, accumulate, keepGoing, finish });
~~~

Đây là **đoạn mô tả cấu trúc**, chưa phải chương trình độc lập: các biến handle được tạo ở ví dụ đầy đủ bên dưới. Clause đầu giữ bộ đếm; clause sau giữ accumulator và quyết định khi nào kết thúc.

### 2.1. Chữ ký của các handle thành phần

Giả sử có hai loop variables `i:int` và `acc:int`, và một external argument `limit:int`:

~~~text
loop variable types:      (int i, int acc)
external arguments:       (int limit)

counter init:             (int limit)int       (hoặc null -> 0)
counter step:             (int i, int acc, int limit)int

accumulator init:         (int limit)int
accumulator step:         (int i, int acc, int limit)int
accumulator pred:         (int i, int acc, int limit)boolean
accumulator fini:         (int i, int acc, int limit)int

result loop type:         (int limit)int
~~~

Lưu ý: **`loop` không yêu cầu mọi handle phải nhận toàn bộ tham số**. Các tham số thiếu ở *cuối* danh sách có thể được bổ sung như bởi `dropArguments`, miễn các danh sách có cấu trúc *effectively identical*: giống nhau hoặc một danh sách là **prefix** của danh sách dài nhất trong nhóm phù hợp. Đừng hiểu điều này là combinator tự reorder hay tự convert kiểu tham số tuỳ ý; các kiểu có mặt vẫn phải khớp đúng thứ tự quy định.

Với nhiều clause, các **non-init** handle nhận các biến vòng lặp `V...` theo **thứ tự clause**, tiếp theo mới đến external arguments `A...`. Một `init` không nhận `V...` vì khi khởi tạo chưa có state; nó chỉ nhận một prefix của `A...`.

### 2.2. Cơ chế chạy thật: `step` đứng trước `pred`

Điểm quan trọng nhất của `MethodHandles.loop`: **sau khi khởi tạo toàn bộ state, combinator đi qua từng clause theo thứ tự; tại mỗi clause nó chạy `step` trước rồi mới kiểm tra `pred` (nếu có)**. Đây không phải vòng `while (pred) { step; }` thông thường.

~~~text
1. Lưu external arguments A...
2. Gọi các init theo thứ tự clause để tạo V1, V2, ...
3. Bắt đầu chu kỳ:
   - clause 1: step1 -> cập nhật V1 -> pred1 (nếu có)
       nếu pred1=false: chạy fini1 và return
   - clause 2: step2 -> cập nhật V2 -> pred2 (nếu có)
       nếu pred2=false: chạy fini2 và return
   - ...
4. Nếu không clause nào dừng: lặp chu kỳ tiếp theo.
~~~

Giá trị `step` cập nhật state **ngay lập tức**, nên clause phía sau thấy state mới của clause phía trước. Nếu nhiều predicate, **predicate đầu tiên trả `false` sẽ quyết định finalizer được gọi**. Nếu không có predicate nào có thể trả `false`, vòng có thể chạy vô hạn (trừ lỗi/exception). Bắt buộc phải có **ít nhất một `pred` không null**; predicate phải trả primitive `boolean`.

Những default khi phần tử bị bỏ:

- `init` không có: biến loop nhận **default value** tương ứng kiểu (`int=0`, reference=`null`...).
- `step` không có: dùng phép giữ nguyên state tương ứng (identity).
- `pred` không có: xem như luôn `true`, nên clause đó không thể tự thoát.
- `fini` không có: trả giá trị mặc định của **kiểu trả về chung** của các finalizer; nếu không có finalizer nào, kết quả loop là `void`.
- Các clause hoàn toàn null bị bỏ qua; cấu trúc không được thiếu toàn bộ predicate có khả năng quyết định thoát.

### 2.3. Vì sao `loop` khác `whileLoop`?

`MethodHandles.whileLoop(init,pred,body)` được dựng trên combinator tổng quát nhưng thiết kế rõ **kiểm tra predicate trước body**, giống `while` trong Java. `doWhileLoop(init,body,pred)` kiểm tra predicate sau body. Còn `loop` với các clause đã trình bày thực thi **`step` trước `pred` theo thứ tự từng clause**, cho phép mô tả nhiều biến vòng lặp tùy ý.

Do đó **không copy máy móc** một vòng `while` Java sang đúng một clause `{init,step,pred,fini}` rồi mặc định thứ tự chạy tương đương. Nếu mục tiêu chỉ là vòng `while`/`do-while` thông thường, dùng factory chuyên biệt sẽ dễ đọc và ít lỗi hơn.

## 3. Ví dụ `loop` nhiều clause: tính giai thừa

Mục tiêu với `limit >= 0`:

~~~java
int factorial(int limit) {
    int product = 1;
    for (int i = 1; i <= limit; i++) {
        product *= i;
    }
    return product;
}
~~~

Đây là **hàm Java thông thường để so sánh**, không phải method handle độc lập. Với generic `loop`, dùng hai state:

- `i` khởi tạo mặc định 0, `step` tăng lên 1.
- `product` khởi tạo 1, `step` nhân với `i` đã tăng.
- `predicate` kiểm tra `i < limit` **sau khi nhân**.
- `fini` trả `product`.

Như vậy chu kỳ cuối cùng khi `i == limit` vẫn thực hiện phép nhân trước khi predicate trả `false`; với `limit=5` có tích `1*2*3*4*5=120`. `limit=0` cũng trả 1 (phép nhân đầu với 1 không thay đổi product), đúng quy ước `0!=1`. Ví dụ thực tế cần kiểm tra `limit >= 0` và overflow của `int`: factorial 13 trở lên tràn `int`.

Các helper trong chương trình đầy đủ:

~~~java
private static int one(int limit) { return 1; }
private static int next(int i, int acc, int limit) { return i + 1; }
private static int multiply(int i, int acc, int limit) { return i * acc; }
private static boolean keepGoing(int i, int acc, int limit) { return i < limit; }
private static int result(int i, int acc, int limit) { return acc; }
~~~

Khi tạo các static handles bằng `Lookup.findStatic(...)` rồi gọi:

~~~java
MethodHandle factorial = MethodHandles.loop(
        new MethodHandle[] { null, inc },
        new MethodHandle[] { initFactorial, mult, predicate, finish });
~~~

Nhận `factorial.type() = (int)int` và có thể gọi với `(int) factorial.invokeExact(5)`. Dù `inc`, `mult`, `predicate`, `finish` đều có nhiều tham số, **hàm bên ngoài chỉ nhận `limit`**. Các state `i`, `acc` được quản lý trong loop handle.

## 4. `countedLoop`: lặp theo bộ đếm, có hai overload

Hai factory:

~~~java
public static MethodHandle countedLoop(
        MethodHandle iterations, MethodHandle init, MethodHandle body);

public static MethodHandle countedLoop(
        MethodHandle start, MethodHandle end,
        MethodHandle init, MethodHandle body);
~~~

Chúng là convenience wrappers trên generic `loop` và tự tạo bộ đếm `int i`. Sự khác nhau là **định nghĩa dãy chỉ số**:

| Overload | Dãy chỉ số `i` | Ví dụ |
| --- | --- | --- |
| `countedLoop(iterations, init, body)` | `0` đến `iterations(...)-1` | `iterations=4` → `0,1,2,3` |
| `countedLoop(start, end, init, body)` | `start(...)` đến `end(...)-1` | `start=2,end=5` → `2,3,4` |

Dù đếm bao nhiêu lần, **chữ ký của `body` có thứ tự đặc biệt**:

~~~text
Có accumulator V:
    body(V accumulator, int counter, A... externalArgs) -> V

Không có accumulator:
    body(int counter, A... externalArgs) -> void
~~~

`V` là kiểu state và cũng là kiểu trả về của `body` (nếu không void). `init` nếu được cung cấp phải trả `V` và chỉ nhận tham số ngoài `A...`, không nhận counter. `iterations`, `start` và `end` phải trả **primitive `int`**. Các danh sách external parameters của các handle phải tương thích theo quy tắc prefix trong Javadoc.

### 4.1. Ba-handle overload: số lượt lặp động

Mô tả tương đương (giản lược về cú pháp, đúng về vòng đếm):

~~~java
int n = iterations(externalArgs);
int acc = init(externalArgs);
for (int i = 0; i < n; i++) {
    acc = body(acc, i, externalArgs);
}
return acc;
~~~

`n` ở đây chỉ là kết quả tính từ external arguments; không phải đối số được tự chèn thêm vào lời gọi bên ngoài. Nếu số lượt bằng 0 hoặc âm, **không chạy body**, và trả giá trị accumulator ban đầu; nếu `init=null` thì dùng default value `V`.

Ví dụ tính tổng số chẵn theo **chỉ số** trong `n` lần lặp:

~~~java
private static int iterations(int n) { return n; }
private static int initial(int n) { return 0; }
private static int evenIndexSum(int total, int i, int n) {
    return total + 2 * i;
}
~~~

Các handle lần lượt có type:

~~~text
iterations   : (int)int
initial      : (int)int
evenIndexSum : (int,int,int)int

countedLoop  : (int)int
~~~

Với `n=4`, `i=0,1,2,3` và tổng `2*0+2*1+2*2+2*3=12`. Với `n=0`, loop trả 0 mà không gọi body. Vòng lặp vẫn có một external argument `n`, được các phần tử nào cần thì sử dụng.

**Không nhầm thứ tự:** `evenIndexSum(total, i, n)` nhận **accumulator trước**, sau đó mới counter, rồi đến external arguments. Viết `evenIndexSum(i,total,n)` vẫn có thể có cùng kiểu `(int,int,int)int` và được combinator chấp nhận, nhưng logic sẽ âm thầm sai. Đặt tên biến rõ vai trò giúp tránh lỗi rất khó phát hiện.

### 4.2. Bốn-handle overload: đoạn `[start,end)`

Tương đương:

~~~java
int endExclusive = end(externalArgs);
int begin = start(externalArgs);
V acc = init(externalArgs);
for (int i = begin; i < endExclusive; i++) {
    acc = body(acc, i, externalArgs);
}
return acc;
~~~

Theo pseudocode của Javadoc, `end` được đánh giá trước `start` và `init`; đừng phụ thuộc vào side effects của các handle khởi tạo để định nghĩa ý nghĩa chương trình. Khi `start >= end`, body không chạy.

Ví dụ muốn tính `2+3+4=9`:

~~~java
private static int from(int start, int end) { return start; }
private static int to(int start, int end) { return end; }
private static int zeroRange(int start, int end) { return 0; }
private static int addIndex(int total, int i, int start, int end) {
    return total + i;
}
~~~

`from` và `to` cùng type `(int,int)int`, `zeroRange` cũng vậy, còn `addIndex` có type `(int,int,int,int)int`. Factory trả handle kiểu `(int,int)int`. Gọi `ranged.invokeExact(2,5)` được 9; gọi `ranged.invokeExact(5,2)` được 0.

### 4.3. `init=null` và `body` trả `void`

Nếu `body` trả `V` và `init=null`, combinator tạo state ban đầu bằng **default value của V**: `0` cho `int`, `false` cho `boolean`, `null` cho reference. Nếu `body` cần object accumulator mà bạn không tạo ở `init`, `null` có thể gây lỗi khi body dereference state; vì thế với `List` hoặc `StringBuilder`, nên có `init` tạo object hợp lệ.

Nếu `body` trả `void`, sẽ không có accumulator trả về. Chữ ký body lúc đó là `(int i, A...)void`; loop handle nhận `A...` và trả `void`. Dùng khi muốn hiệu ứng phụ như ghi log, điền mảng hoặc cập nhật object bên ngoài. Các ví dụ có kết quả thường dễ kiểm chứng hơn ví dụ side-effect; ưu tiên functional accumulator khi có thể.

`countedLoop` không tự song song hóa và không chia việc cho nhiều thread; nó thực hiện vòng đếm tuần tự. Nếu `body` tốn kém hoặc có trạng thái chia sẻ, nguyên tắc concurrency và exception thông thường vẫn áp dụng.

## 5. `iteratedLoop`: dùng `Iterator` thay vì bộ đếm số nguyên

Chữ ký:

~~~java
public static MethodHandle iteratedLoop(
        MethodHandle iterator, MethodHandle init, MethodHandle body);
~~~

Sơ đồ tham số:

~~~text
iterator: (A...)Iterator<T>    (handle trả Iterator hoặc subtype)
init    : (A...)V             (hoặc null -> default V)
body    : (V accumulator, T element, A... externalArgs)V
----------------------------------------------------------
result  : (A...)V

Nếu body trả void:
body    : (T element, A... externalArgs)void
result  : (A...)void
~~~

Cơ chế:

~~~java
Iterator<T> it = iterator(externalArgs);
V acc = init(externalArgs);
while (it.hasNext()) {
    T element = it.next();
    acc = body(acc, element, externalArgs);
}
return acc;
~~~

Đây là **pseudocode** cho trường hợp accumulator không void. Biến `element` đến từ `Iterator.next()`, không phải counter `int`.

### 5.1. `iterator=null`: tự gọi `Iterable.iterator()`

Khi truyền `null` ở vị trí `iterator`, combinator dùng một iterator handle mặc định hành xử như `Iterable.iterator()` trên **external argument đầu tiên**. Kiểu của argument đầu phải là `Iterable` hoặc subtype tương thích; đó là lý do cách gọi sau hợp lệ:

~~~java
MethodHandle iterated = MethodHandles.iteratedLoop(null, initText, join);
Iterable<String> values = List.of("A", "B", "C");
String joined = (String) iterated.invokeExact(values);
~~~

Đây là những statement minh họa sau khi `initText` và `join` được tạo đúng kiểu; ví dụ đầy đủ xuất hiện ở phần kế tiếp. Type của handle được tạo là `(Iterable)String` nếu signature của `initText`/`join` dùng `Iterable.class` làm external argument. Khi gọi `invokeExact`, biến `values` có static type `Iterable<String>` (erasure là `Iterable`), phù hợp với handle. Nếu dùng một biến declared `List<String>` trực tiếp tại call site, descriptor có thể là `List` và **không khớp `invokeExact`**; hãy gán/cast sang `Iterable` hoặc dùng `invoke` với conversion phù hợp.

Không có cách viết `Iterable<String>.class` hay `Iterator<String>.class`: type arguments bị erasure, chữ ký `MethodType` dùng `Iterable.class`/`Iterator.class`.

### 5.2. `iterator` khác null: chủ động tạo Iterator

Bạn cũng có thể truyền handle như:

~~~java
private static Iterator<String> iteratorFor(Iterable<String> data) {
    return data.iterator();
}
~~~

Khi lookup helper này với return type `Iterator.class` và input `Iterable.class`, có thể gọi:

~~~java
MethodHandle explicit = MethodHandles.iteratedLoop(iteratorHandle, initText, join);
~~~

`iteratorHandle` được trả về từ `Lookup.findStatic(...)` và phải có return type là `Iterator` hoặc subtype; nó có thể tiếp nhận external arguments `A...`. Cách này thích hợp khi cần đọc từ một adapter, lựa chọn iterator đặc biệt, hoặc tính iterator từ một input không phải `Iterable`; vẫn phải thỏa quy tắc chữ ký của các clause.

### 5.3. Accumulator là kết quả, không phải phần tử

Ví dụ nối chuỗi:

~~~java
private static String empty(Iterable<String> input) { return ""; }

private static String combine(String accumulated, String item,
                              Iterable<String> input) {
    return accumulated.isEmpty() ? item : accumulated + "|" + item;
}
~~~

Handle `initText` có type `(Iterable)String`; `join` có type `(String,String,Iterable)String`. Dù `input` là external argument thứ nhất của **loop**, trong `body` nó đứng **sau** hai vị trí nội bộ `accumulated` và `item`.

Duyệt `["A","B","C"]` theo thứ tự iterator trả ra:

~~~text
acc khởi tạo:  ""
item A:       "A"
item B:       "A|B"
item C:       "A|B|C"
kết quả:      "A|B|C"
~~~

Với danh sách rỗng, `init` vẫn được gọi, `body` không được gọi lần nào, kết quả là chuỗi rỗng. Vòng lặp không đảm bảo một **thứ tự duyệt mới**: thứ tự phụ thuộc iterator của collection bạn cung cấp, và iterator có thể không ổn định nếu collection được thay đổi đồng thời.

### 5.4. Kiểu phần tử runtime và erasure

`Iterator<String>` chỉ là generic contract lúc compile; ở mức method handle, iterator trả phần tử qua erased `Object`. Combinator cần chuyển từng phần tử về `T` mà `body` khai báo, sử dụng các quy tắc chuyển kiểu phù hợp `MethodHandle.asType`.

Do đó nếu nguồn Iterator thật chứa phần tử sai kiểu, bạn có thể gặp `ClassCastException` hoặc lỗi conversion khác **lúc lặp**, chứ không phải luôn thấy lỗi ngay khi gọi `iteratedLoop`. Việc thay đổi collection lúc đang duyệt có thể kích hoạt lỗi của iterator (chẳng hạn `ConcurrentModificationException` với iterator fail-fast trong những tình huống nhất định). Combinator không nuốt các lỗi đó và cũng **không tự đóng** một resource/stream tùy ý; nếu iterator nắm resource cần đóng, phải quản lý vòng đời bên ngoài.

## 6. Chương trình Java 17+ hoàn chỉnh cho cả ba combinator

Tạo file **`LoopCombinatorsDemo.java`**. Ví dụ này có: một generic `loop` với hai clause, cả hai overload `countedLoop`, `iteratedLoop` với iterator mặc định và iterator tường minh, và trường hợp đầu vào rỗng.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Iterator;
import java.util.List;

public class LoopCombinatorsDemo {
    private static int one(int limit) { return 1; }
    private static int next(int i, int acc, int limit) { return i + 1; }
    private static int multiply(int i, int acc, int limit) { return i * acc; }
    private static boolean keepGoing(int i, int acc, int limit) { return i < limit; }
    private static int result(int i, int acc, int limit) { return acc; }

    private static int iterations(int n) { return n; }
    private static int initial(int n) { return 0; }
    private static int evenIndexSum(int total, int i, int n) { return total + 2 * i; }

    private static int from(int start, int end) { return start; }
    private static int to(int start, int end) { return end; }
    private static int zeroRange(int start, int end) { return 0; }
    private static int addIndex(int total, int i, int start, int end) { return total + i; }

    private static String empty(Iterable<String> input) { return ""; }
    private static String combine(String accumulated, String item, Iterable<String> input) {
        return accumulated.isEmpty() ? item : accumulated + "|" + item;
    }
    private static Iterator<String> iteratorFor(Iterable<String> input) {
        return input.iterator();
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // 1. Generic loop: hai clause, state i và acc.
        MethodHandle initFactorial = lookup.findStatic(
                LoopCombinatorsDemo.class, "one", MethodType.methodType(int.class, int.class));
        MethodHandle inc = lookup.findStatic(
                LoopCombinatorsDemo.class, "next",
                MethodType.methodType(int.class, int.class, int.class, int.class));
        MethodHandle mult = lookup.findStatic(
                LoopCombinatorsDemo.class, "multiply",
                MethodType.methodType(int.class, int.class, int.class, int.class));
        MethodHandle predicate = lookup.findStatic(
                LoopCombinatorsDemo.class, "keepGoing",
                MethodType.methodType(boolean.class, int.class, int.class, int.class));
        MethodHandle finish = lookup.findStatic(
                LoopCombinatorsDemo.class, "result",
                MethodType.methodType(int.class, int.class, int.class, int.class));

        MethodHandle generic = MethodHandles.loop(
                new MethodHandle[] { null, inc },
                new MethodHandle[] { initFactorial, mult, predicate, finish });
        System.out.println("generic type = " + generic.type());
        System.out.println("factorial(5) = " + (int) generic.invokeExact(5));
        System.out.println("factorial(0) = " + (int) generic.invokeExact(0));

        // 2. Counted loop: i = 0..n-1.
        MethodHandle count = lookup.findStatic(
                LoopCombinatorsDemo.class, "iterations",
                MethodType.methodType(int.class, int.class));
        MethodHandle start = lookup.findStatic(
                LoopCombinatorsDemo.class, "initial",
                MethodType.methodType(int.class, int.class));
        MethodHandle body = lookup.findStatic(
                LoopCombinatorsDemo.class, "evenIndexSum",
                MethodType.methodType(int.class, int.class, int.class, int.class));
        MethodHandle counted = MethodHandles.countedLoop(count, start, body);
        System.out.println("counted type = " + counted.type());
        System.out.println("counted(4) = " + (int) counted.invokeExact(4));
        System.out.println("counted(0) = " + (int) counted.invokeExact(0));

        // 3. Counted loop theo đoạn [start,end).
        MethodHandle lo = lookup.findStatic(
                LoopCombinatorsDemo.class, "from",
                MethodType.methodType(int.class, int.class, int.class));
        MethodHandle hi = lookup.findStatic(
                LoopCombinatorsDemo.class, "to",
                MethodType.methodType(int.class, int.class, int.class));
        MethodHandle initRange = lookup.findStatic(
                LoopCombinatorsDemo.class, "zeroRange",
                MethodType.methodType(int.class, int.class, int.class));
        MethodHandle rangeBody = lookup.findStatic(
                LoopCombinatorsDemo.class, "addIndex",
                MethodType.methodType(int.class, int.class, int.class, int.class, int.class));
        MethodHandle ranged = MethodHandles.countedLoop(lo, hi, initRange, rangeBody);
        System.out.println("range type = " + ranged.type());
        System.out.println("range[2,5) = " + (int) ranged.invokeExact(2, 5));
        System.out.println("range[5,2) = " + (int) ranged.invokeExact(5, 2));

        // 4. Iterator mặc định (iterator=null), external arg là Iterable.
        MethodHandle initText = lookup.findStatic(
                LoopCombinatorsDemo.class, "empty",
                MethodType.methodType(String.class, Iterable.class));
        MethodHandle join = lookup.findStatic(
                LoopCombinatorsDemo.class, "combine",
                MethodType.methodType(String.class, String.class, String.class, Iterable.class));
        MethodHandle iterated = MethodHandles.iteratedLoop(null, initText, join);
        Iterable<String> data = List.of("A", "B", "C");
        System.out.println("iterated type = " + iterated.type());
        System.out.println("joined = " + (String) iterated.invokeExact(data));
        Iterable<String> emptyItems = List.of();
        System.out.println("empty joined = [" + (String) iterated.invokeExact(emptyItems) + "]");

        // 5. Iterator handle tự cung cấp.
        MethodHandle iterator = lookup.findStatic(
                LoopCombinatorsDemo.class, "iteratorFor",
                MethodType.methodType(Iterator.class, Iterable.class));
        MethodHandle explicit = MethodHandles.iteratedLoop(iterator, initText, join);
        System.out.println("explicit type = " + explicit.type());
        System.out.println("explicit joined = " + (String) explicit.invokeExact(data));
    }
}
~~~

Chạy từ thư mục chứa file với JDK 17 trở lên:

~~~bash
javac --release 17 LoopCombinatorsDemo.java
java LoopCombinatorsDemo
~~~

**`stdout` chính xác:**

~~~text
generic type = (int)int
factorial(5) = 120
factorial(0) = 1
counted type = (int)int
counted(4) = 12
counted(0) = 0
range type = (int,int)int
range[2,5) = 9
range[5,2) = 0
iterated type = (Iterable)String
joined = A|B|C
empty joined = []
explicit type = (Iterable)String
explicit joined = A|B|C
~~~

Mã đã được biên dịch với `javac --release 17` trên JDK 21 và chạy thành công; output trên khớp với các lệnh `System.out.println`. Dùng `--release 17` đảm bảo ngôn ngữ và Java SE API mục tiêu tương thích Java 17.

### 6.1. Đọc kết quả từng nhóm

**Generic loop:** `generic.type()` là `(int)int`, tức bên ngoài chỉ cung cấp `limit`, còn nội bộ quản lý `i` và `acc`. Hai clause nhận cùng state theo thứ tự và `pred` sau phép nhân, cho `factorial(5)=120`.

**Counted:** `counted.type()` là `(int)int`. `body` lấy `total` rồi `i`, nên `counted(4)=0+2+4+6=12` và `counted(0)=0`.

**Range:** `ranged.type()` là `(int,int)int` vì đầu vào gồm `start` và `end`. Đoạn `[2,5)` có đúng ba chỉ số 2,3,4; đoạn `[5,2)` không có phần tử, trả state ban đầu 0.

**Iterated:** `iterated.type()` và `explicit.type()` đều là `(Iterable)String`. Ở trường hợp đầu, `iterator=null` khiến combinator dùng `Iterable.iterator()`; ở trường hợp hai, nó gọi `iteratorFor`. Các phần tử đi qua `combine` theo thứ tự `A,B,C`. Trường hợp danh sách rỗng trả `""`, nên output là `empty joined = []`.

## 7. Khớp `MethodType` và cách gọi đúng qua `invokeExact`

Ba combinator sinh một `MethodHandle` có type được tính từ chữ ký của các thành phần. Chúng không tự tạo ra một method “nhận mọi `Object`”, và `invokeExact` **không tự ép kiểu** cho tham số và giá trị trả về.

Ví dụ:

~~~java
// generic.type() == (int)int
int ok = (int) generic.invokeExact(5);

// iterated.type() == (Iterable)String
Iterable<String> words = List.of("x", "y");
String joined = (String) iterated.invokeExact(words);
~~~

Đây là đoạn minh họa trong method có các handle `generic` và `iterated` được tạo trước. Những cách gọi dễ sai:

~~~java
// long result = (long) generic.invokeExact(5);
// Sai: call site mong đợi long, handle trả int.

// List<String> list = List.of("x", "y");
// String result = (String) iterated.invokeExact(list);
// Sai: call site đưa vào List, handle đòi Iterable.
~~~

`MethodHandle.invoke(...)` có thể áp dụng một số chuyển đổi theo quy tắc `asType`, còn `invokeExact(...)` yêu cầu call-site descriptor trùng hoàn toàn với `handle.type()`. Khi thiết kế thư viện có input động, có thể dùng `asType`/`bindTo`/`dropArguments`/`filterArguments` nếu cần **thích nghi một cách có chủ đích**, không thêm cast ngẫu nhiên.

Các helper dùng trong code thực cần được tra cứu với đúng chữ ký primitive và reference. Ví dụ `MethodType.methodType(boolean.class,int.class,int.class,int.class)` là chữ ký predicate của generic loop, khác với `MethodType.methodType(Boolean.class,...)`. Sai một kiểu tham số hoặc thứ tự có thể gây `NoSuchMethodException` tại lookup, hoặc `IllegalArgumentException` khi ghép combinator.

## 8. Tại sao `loop` không phải tự động dễ đọc hơn một vòng `for` Java?

Với công việc bình thường, chương trình:

~~~java
int sum = 0;
for (int i = 0; i < values.length; i++) {
    sum += values[i];
}
~~~

rõ ràng hơn nhiều so với dựng graph MethodHandle. Đoạn này chỉ minh họa trong scope có `int[] values`; không phải file Java độc lập. Loop combinators có giá trị khi **bản thân thao tác cần được xây dựng ở runtime**, ví dụ:

- Một thư viện xử lý data pipeline lưu các stage dưới dạng `MethodHandle` và muốn đưa logic lặp vào cùng chuỗi combinator.
- Runtime compiler hoặc DSL interpreter cấu hình predicate/step/initializer động nhưng vẫn muốn một lời gọi `MethodHandle` có type cụ thể.
- Các adapter method handle cần ghép vòng xử lý với `guardWithTest`, `filterArguments`, `collectArguments` hoặc dynamic call sites.
- Một hệ thống sinh bộ xử lý dữ liệu theo schema runtime, nơi các bước đã là handle và không thể hard-code nguyên hàm `for` từ compile-time.

**Không nên** chuyển mọi `for-each` thành `iteratedLoop` để “tối ưu”. Hiệu năng phụ thuộc cách xây dựng handle, mức độ ổn định của call site, JIT, việc tạo object và workload. Đo bằng benchmark phù hợp (như JMH); đừng khẳng định combinator luôn nhanh hơn vòng lặp Java thông thường.

## 9. Các lỗi phổ biến và cách debug

| Triệu chứng | Giai đoạn | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- | --- |
| `IllegalArgumentException` khi dựng `loop` | Tạo handle | Clause không hợp lệ, thiếu predicate, kiểu `init`/`step` khác nhau, finalizer không đồng nhất | In `type()` từng thành phần, kiểm tra thứ tự `init,step,pred,fini` |
| Vòng chạy sai số lần với `loop` | Khi chạy | Hiểu nhầm `pred` chạy **trước** `step` | Nhớ mỗi clause chạy step rồi mới pred; vẽ trace một chu kỳ |
| Vòng vô hạn | Khi chạy | Không predicate nào trả `false` | Bảo đảm có đường thoát thực tế và input được giới hạn |
| `IllegalArgumentException` khi dựng `countedLoop` | Tạo handle | `iterations`/`start`/`end` không trả `int`; `body` không có counter `int` đúng vị trí | Kiểm tra `(V,int,A...)V` hoặc `(int,A...)void` |
| Kết quả `countedLoop` sai dù type đúng | Khi chạy | Đảo vị trí hai `int` `acc` và `i`; compiler không bắt được | Đặt tên rõ và kiểm tra ví dụ với ít lượt |
| `ClassCastException` khi lặp | Khi chạy | Iterator cung cấp element không hợp với `T` của body sau erasure | Validate nguồn dữ liệu hoặc body type |
| `IllegalArgumentException` khi dựng `iteratedLoop` | Tạo handle | Iterator handle không trả `Iterator`, hoặc external args không tương thích | Dùng return type `Iterator.class` và kiểm tra `(A...)` |
| `WrongMethodTypeException` khi gọi `invokeExact` | Khi chạy | Kiểu call site khác `handle.type()`, kể cả kiểu trả về | In `handle.type()`; cast/gán biến đúng kiểu hoặc chủ động adapt |
| `NoSuchMethodException` khi `Lookup.findStatic` | Lookup | Helper function name hoặc descriptor primitive/reference sai | So lại method declaration và `MethodType` |
| `IllegalAccessException` khi `Lookup.findStatic` | Lookup | Method `private` không truy cập được từ lookup class | Tạo lookup ở caller có quyền hoặc chỉnh public API phù hợp |
| `NullPointerException` trong body | Khi chạy | `init=null` tạo state reference `null` rồi body dereference | Cấp `init` tạo state hợp lệ |
| Loop dừng đột ngột vì exception | Khi chạy | `step`/`pred`/`body`/iterator ném lỗi | Xử lý nguyên nhân; combinator không tự retry hay rollback state |

### Debug có hệ thống

1. **In kiểu trước khi ghép:** `System.out.println(init.type())`, `body.type()`, `pred.type()` và, sau khi tạo, `loop.type()`. Kiểu mismatch nên được xử lý ở bước này.
2. **Nhận diện state và external args:** viết sơ đồ `(V...,A...)`, tránh đảo `i` với accumulator vì cả hai thường cùng là `int`.
3. **Test đầu vào biên:** 0 iterations, `start==end`, `start>end`, empty Iterator, one-element Iterator, `limit` nhỏ. Với generic `loop`, test chính thứ tự step/pred.
4. **Đánh giá lỗi theo giai đoạn:** `Lookup.findStatic` có thể ném `NoSuchMethodException`/`IllegalAccessException`; combinator có thể ném `IllegalArgumentException`; khi gọi handle có thể gặp `WrongMethodTypeException` hoặc exception từ target.
5. **Không giấu cause:** `MethodHandle` thường truyền exception của target trực tiếp, không mặc định bọc trong `InvocationTargetException` như `java.lang.reflect.Method.invoke`.
6. **Giới hạn tác dụng phụ:** một `step` có side effect có thể đã chạy trước khi `pred` phát hiện dừng trong generic `loop`. Nếu body làm I/O hoặc ghi dữ liệu, logic recovery phải được thiết kế ở tầng ứng dụng.

## 10. Những ràng buộc cần nhớ khi dùng API này

### 10.1. Kiểu tham số thực sự là hợp đồng

Các công thức nên thuộc lòng:

~~~text
loop:
  clause = [init, step, pred, fini]
  result.type() = (A...)R

countedLoop(iterations, init, body):
  iterations: (A...)int
  init:       (A...)V           [hoặc null]
  body:       (V,int,A...)V     [hoặc (int,A...)void]
  result:     (A...)V           [hoặc void]

countedLoop(start,end,init,body):
  start/end:  (A...)int
  init:       (A...)V           [hoặc null]
  body:       (V,int,A...)V     [hoặc (int,A...)void]
  result:     (A...)V           [hoặc void]

iteratedLoop(iterator,init,body):
  iterator:   (A...)Iterator    [hoặc null, dùng Iterable ở A đầu]
  init:       (A...)V           [hoặc null]
  body:       (V,T,A...)V       [hoặc (T,A...)void]
  result:     (A...)V           [hoặc void]
~~~

**Ghi chú:** `(A...)` trong bảng là dạng đầy đủ để dễ hiểu. Javadoc cho phép nhiều handle nhận các **prefix** hiệu quả của external parameter list và bổ sung tham số trailing không dùng; `iteratedLoop` còn có logic adapt từ erased `Iterator.next():Object` sang `T`. Đây không phải cơ chế tự reorder arbitrary arguments.

### 10.2. `null` ở mỗi API có nghĩa khác nhau

- `loop`: một vị trí clause `null` nghĩa là thiếu `init`/`step`/`pred`/`fini` và combinator cung cấp default theo quy tắc; không cho phép toàn bộ vòng thiếu predicate.
- `countedLoop`: `init=null` hợp lệ; `iterations` hoặc `start/end` không được null; `body` không được null.
- `iteratedLoop`: **`iterator=null` là lựa chọn thiết kế hợp lệ** để dùng `Iterable.iterator()` từ external argument đầu, `init=null` hợp lệ, nhưng `body=null` không hợp lệ.

Không dùng một quy tắc “null nào cũng là empty loop” cho cả ba. Null tại những vị trí bắt buộc có thể ném `NullPointerException` ngay khi tạo handle.

### 10.3. Không trộn loại lỗi và điều kiện dừng

Dừng thông thường là:

- `loop`: một `pred` trả `false` và `fini` tạo result.
- `countedLoop`: bộ đếm đã đi hết số lượt hoặc đạt end-exclusive.
- `iteratedLoop`: `Iterator.hasNext()` trả `false`.

Còn target handle ném exception là **thất bại**, không phải một giá trị `false` hay một lần lặp rỗng. Nếu cần xử lý recoverable exceptions có hệ thống, thiết kế thành combinator xử lý lỗi như `MethodHandles.catchException`, `tryFinally` hoặc một lớp điều phối bao quanh; điều kiện/kiểu của chúng cần được thiết kế phù hợp thay vì bắt mọi `Throwable` mù quáng.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Trong generic `loop` có `new MethodHandle[]{init,step,pred,fini}`, hàm nào chạy trước ở mỗi clause: `step` hay `pred`?

**Đáp án:** `step` trước, state được cập nhật, rồi mới chạy `pred`. Khác với `whileLoop` chuyên biệt có predicate trước body.

**Câu 2.** Có `countedLoop(iterations, init, body)` với `iterations=4`; counter chạy qua những giá trị nào?

**Đáp án:** `0,1,2,3`. End-exclusive, tổng bốn lượt.

**Câu 3.** Với overload bốn handle `countedLoop(start,end,init,body)`, `start=3` và `end=3`, body chạy mấy lần?

**Đáp án:** Không lần nào; trả accumulator do `init` tạo (hoặc default `V` khi `init=null`).

**Câu 4.** Nếu `body(int acc,int i,int n)` trả `int`, kiểu `init` phải trả gì?

**Đáp án:** `int` (kiểu `V` của body), và các tham số của init phải tương thích với external parameter list `A...`. Counter `i` không nằm trong tham số của init.

**Câu 5.** `iteratedLoop(null,init,body)` sẽ lấy iterator ở đâu?

**Đáp án:** Từ `Iterable.iterator()` trên external argument **đầu tiên**, có kiểu `Iterable` hoặc subtype hợp lệ.

**Câu 6.** `iteratedLoop` có thể có body trả `void` không?

**Đáp án:** Có. Body khi đó có dạng `(T,A...)void` và loop handle trả `void`, không có accumulator kết quả.

**Câu 7.** Nếu body nhận `String element` nhưng iterator thực trả `Integer` thì chuyện gì xảy ra?

**Đáp án:** Combinator có thể được tạo vì Iterator generic bị erased; lúc lặp, chuyển kiểu phần tử sang `String` có thể ném `ClassCastException`.

**Câu 8.** `generic.type()` là `(int)int`. Có thể dùng `long x=(long)generic.invokeExact(5)` mà không adapt không?

**Đáp án:** Không. `invokeExact` yêu cầu kiểu kết quả call site đúng `int`; dùng `int` rồi chuyển thành `long` sau đó, hoặc dùng adapter phù hợp.

**Câu 9.** Nên dùng `loop` cho mọi phép lặp để tăng hiệu năng?

**Đáp án:** Không. Với logic biết ở compile time, `for`/`while` thông thường rõ ràng hơn; MethodHandle combinators hữu ích khi chính chương trình điều khiển được tạo từ các handle tại runtime. Hiệu năng cần benchmark.

## Tài liệu chính thức

- [Java SE 21 — MethodHandles.loop, countedLoop và iteratedLoop](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Java SE 17 — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Java SE 21 — MethodHandle.invokeExact và invoke](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 21 — MethodType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html)
