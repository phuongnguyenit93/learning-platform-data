# Theo dõi thứ tự thực thi và kiểu trung gian khi kết hợp hàm trong Java

## 1. Mục tiêu và mô hình tư duy

Kết hợp hàm (*function composition*) biến nhiều bước xử lý nhỏ thành một hàm có thể tái sử dụng. Để đọc đúng một chuỗi hàm, luôn trả lời **hai câu hỏi độc lập**:

1. **Bước nào chạy trước, bước nào chạy sau?** Tên các phương thức `andThen` và `compose` quyết định thứ tự khi hàm được gọi, không phải chỉ dựa vào thứ tự xuất hiện của tên biến trong biểu thức.
2. **Đầu ra của từng bước có kiểu gì, và bước tiếp theo nhận kiểu gì?** Trình biên dịch Java kiểm tra sự tương thích giữa các kiểu này ngay khi xây dựng chuỗi hàm.

Ví dụ với ba phép biến đổi:

```text
A --f--> B --g--> C --h--> D
```

Nếu `f` là `Function<A, B>`, `g` là `Function<B, C>` và `h` là `Function<C, D>` thì `f.andThen(g).andThen(h)` có kiểu `Function<A, D>`. Khi gọi `apply(a)`:

```text
a (A)
  │ f.apply(a)
  ▼
b (B)
  │ g.apply(b)
  ▼
c (C)
  │ h.apply(c)
  ▼
d (D)
```

Chú ý: một biểu thức **tạo hàm kết hợp** không có nghĩa là tất cả các bước đã thực thi. Với các phương thức mặc định của `Function`, chuỗi sẽ chạy khi gọi `apply` lên hàm đã kết hợp. Do đó cần phân biệt **thời điểm tạo pipeline** và **thời điểm chạy pipeline**.

## 2. `andThen`: chạy hàm hiện tại trước, hàm tiếp theo sau

Với:

```java
Function<A, B> f = /* ... */;
Function<B, C> g = /* ... */;

Function<A, C> pipeline = f.andThen(g);
```

Đây là **mã minh họa về kiểu generic**, không phải chương trình Java độc lập; `A`, `B`, `C` là các kiểu giả định.

Quy tắc:

```text
f.andThen(g).apply(a) = g.apply(f.apply(a))
                         ^ chạy sau
                 ^ chạy trước
```

- `f` nhận `A`, trả `B`.
- `g` nhận kết quả `B` của `f`, trả `C`.
- Cả chuỗi nhận `A`, trả `C`.
- Nếu có nhiều bước, `f.andThen(g).andThen(h)` thực thi theo thứ tự `f → g → h`.

Trong API thật, `Function<T, R>.andThen` có tham số kiểu `Function<? super R, ? extends V>` và trả `Function<T, V>`. Điều đó cho phép bước sau nhận một **siêu kiểu** của `R`, và kết quả của nó là một **kiểu con** thích hợp của `V`; không nhất thiết hai khai báo generic phải viết giống từng ký tự.

## 3. `compose`: chạy hàm đối số trước, rồi hàm hiện tại

Với:

```java
Function<A, B> f = /* ... */;
Function<B, C> g = /* ... */;

Function<A, C> pipeline = g.compose(f);
```

Cũng là **đoạn minh họa kiểu**, không phải tệp biên dịch độc lập.

Quy tắc:

```text
g.compose(f).apply(a) = g.apply(f.apply(a))
                          ^ chạy sau
                  ^ chạy trước
```

Nói cách khác:

- `f.andThen(g)`: “thực hiện `f`, **sau đó** `g`”.
- `g.compose(f)`: “trước khi thực hiện `g`, thực hiện `f`”.

Hai cách biểu diễn tương đương về thứ tự gọi và sự truyền giá trị nếu `f` và `g` cố định, nhưng **không cần so sánh identity của hai đối tượng hàm kết hợp** để kết luận chúng tương đương về hành vi.

| Biểu thức | Thứ tự thực thi khi gọi `apply(x)` | Kiểu tổng quát |
| --- | --- | --- |
| `f.andThen(g)` | `f` → `g` | `A → C` |
| `g.compose(f)` | `f` → `g` | `A → C` |
| `f.andThen(g).andThen(h)` | `f` → `g` → `h` | `A → D` |
| `h.compose(g).compose(f)` | `f` → `g` → `h` | `A → D` |

Khi nhiều bước được kết hợp, cách đọc đáng tin cậy là vẽ mũi tên dữ liệu từ **đầu vào đầu tiên** đến **đầu ra cuối cùng**, thay vì cố đoán thứ tự từ cách lồng ngoặc.

## 4. Ví dụ Java 17+ chạy được: ghi log từng bước và xem kiểu trung gian

Tạo tệp `FunctionOrderDemo.java`:

```java
import java.util.function.Function;

public class FunctionOrderDemo {
    static String normalize(String raw) {
        System.out.println("1.normalize: [" + raw + "]");
        return raw.trim();
    }

    static Integer parse(String digits) {
        System.out.println("2.parse: [" + digits + "]");
        return Integer.parseInt(digits);
    }

    static String describe(Integer number) {
        System.out.println("3.describe: " + number);
        return "double=" + (number * 2);
    }

    public static void main(String[] args) {
        Function<String, String> normalize = FunctionOrderDemo::normalize;
        Function<String, Integer> parse = FunctionOrderDemo::parse;
        Function<Integer, String> describe = FunctionOrderDemo::describe;

        // Xây dựng chuỗi: chưa chạy normalize/parse/describe.
        Function<String, String> pipeline =
                normalize.andThen(parse).andThen(describe);

        System.out.println("Before apply");
        System.out.println(pipeline.apply(" 21 "));

        // Cùng hướng dữ liệu khi viết với compose:
        Function<String, Integer> firstTwo = parse.compose(normalize);
        System.out.println("Compose:");
        System.out.println(firstTwo.apply(" 7 "));
    }
}
```

Biên dịch và chạy:

```bash
javac FunctionOrderDemo.java
java FunctionOrderDemo
```

Kết quả chuẩn:

```text
Before apply
1.normalize: [ 21 ]
2.parse: [21]
3.describe: 21
double=42
Compose:
1.normalize: [ 7 ]
2.parse: [7]
7
```

Phân tích lần gọi thứ nhất:

| Thời điểm | Hàm | Giá trị vào và kiểu | Giá trị ra và kiểu |
| --- | --- | --- | --- |
| 1 | `normalize` | `" 21 "` — `String` | `"21"` — `String` |
| 2 | `parse` | `"21"` — `String` | `21` — `Integer` |
| 3 | `describe` | `21` — `Integer` | `"double=42"` — `String` |

Kiểu của toàn chuỗi là `Function<String, String>`, **nhưng có một giá trị trung gian kiểu `Integer`**. Không được suy từ kiểu đầu vào/đầu ra chung rằng mọi bước bên trong cũng chỉ xử lý `String`.

Dòng `Before apply` xuất hiện trước các log hàm, chứng minh đoạn tạo `pipeline` không chạy các phép biến đổi. Trong `System.out.println(pipeline.apply(...))`, đối số `pipeline.apply(...)` được tính trước, vì thế log của từng stage xuất hiện trước dòng kết quả `double=42`. Với `parse.compose(normalize)`, log cũng cho thấy `normalize` chạy trước `parse`.

## 5. Phân tích kiểu bằng chữ ký hàm

Khi pipeline phức tạp, viết bảng các loại dữ liệu trước khi viết code. Ví dụ chuyển từ dữ liệu nhập đến phiếu báo:

```text
String --parse--> Integer --price--> Long --format--> String
```

Với:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, Long> price = quantity -> quantity * 10L;
Function<Long, String> format = total -> "Total: " + total;

Function<String, String> receipt =
        parse.andThen(price).andThen(format);
```

Đây là đoạn mã nằm **trong phương thức hoặc khối khởi tạo** có import `java.util.function.Function`. Mỗi cặp đầu ra/đầu vào được nối hợp lệ: `Integer → Integer` và `Long → Long`. Chẳng hạn `receipt.apply("3")` trả `"Total: 30"`.

Phương thức `andThen` cũng hỗ trợ tương thích theo quan hệ cha–con:

```java
Function<String, String> trim = String::trim;
Function<CharSequence, Integer> count = CharSequence::length;
Function<String, Integer> trimmedLength = trim.andThen(count);
```

Khi `trim` trả `String`, bước `count` nhận `CharSequence` được, vì `String implements CharSequence`. Đây là kết nối hợp lệ, dù kiểu generic được khai báo khác nhau.

Trái lại, chuỗi sau **sai kiểu**:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<String, String> upper = String::toUpperCase;

// Không biên dịch: parse trả Integer, upper nhận String.
Function<String, String> wrong = parse.andThen(upper);
```

Đây là **phản ví dụ cố ý không biên dịch**. Cách sửa phụ thuộc bài toán: nếu muốn viết hoa trước khi parse thì cả ý nghĩa nghiệp vụ lẫn kiểu chuyển đổi đều phải xem xét lại; nếu muốn định dạng kết quả số sau parse, bước sau phải nhận `Integer` (hoặc một siêu kiểu phù hợp):

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Number, String> label = n -> "number=" + n;
Function<String, String> correct = parse.andThen(label);
```

Ở đây `Number` là siêu kiểu của `Integer`. Trình biên dịch đảm bảo chữ ký tương thích; **nó không chứng minh** rằng mọi chuỗi đầu vào đều parse được. `"abc"` vẫn có thể gây `NumberFormatException` khi chạy.

## 6. Khác nhau giữa suy luận kiểu khi ghép và kiểu lúc chạy

Trong Java, `Function<T,R>` là một functional interface generic. Khi xây dựng chuỗi, trình biên dịch suy ra các tham số kiểu dựa trên target type, chữ ký của `compose`/`andThen` và cách khai báo các hàm thành phần. Đây là **kiểm tra tĩnh**.

Khi chạy, do *type erasure*, kiểu generic không trở thành nhãn kiểu đầy đủ của mọi bước tại runtime. Có thể gỡ lỗi bằng giá trị, log theo stage và khai báo kiểu rõ ràng, nhưng không nên dựa vào `function.getClass()` hoặc cố phục hồi mọi tham số generic từ đối tượng lambda để xác định pipeline.

Một thói quen tốt khi gặp lỗi biên dịch khó đọc:

1. Gán mỗi phép biến đổi cho một biến `Function<Input, Output>` có kiểu cụ thể.
2. Viết mũi tên dữ liệu và kiểm tra kiểu **đầu ra của bước trước → đầu vào của bước sau**.
3. Nối hai bước một lần, gán vào biến có kiểu mong đợi.
4. Chỉ sau khi kiểu và hành vi đã đúng mới rút gọn thành một biểu thức.

Ví dụ:

```java
Function<String, String> clean = String::trim;
Function<String, Integer> toNumber = Integer::parseInt;
Function<String, Integer> cleanNumber = clean.andThen(toNumber);
```

Khai báo tường minh có thể giúp phân biệt lỗi suy luận kiểu với lỗi logic thứ tự. Với biểu thức lambda đặt trực tiếp trong `andThen`, kiểu tham số được suy từ đầu ra của stage trước; nếu không đủ rõ, hãy viết kiểu đầu vào như `(Integer n) -> n * 2` hoặc đặt lambda vào biến `Function<Integer, Integer>`.

## 7. Theo dõi pipeline bằng wrapper log có kiểu

Khi không muốn đặt `println` trực tiếp trong từng hàm nghiệp vụ, có thể bao một hàm bằng một hàm theo dõi **giữ nguyên chữ ký `A → B`**. Tạo `TracePipelineDemo.java`:

```java
import java.util.function.Function;

public class TracePipelineDemo {
    static <A, B> Function<A, B> trace(
            String name, Function<A, B> step) {
        return input -> {
            System.out.println(name + " input=" + input);
            B output = step.apply(input);
            System.out.println(name + " output=" + output);
            return output;
        };
    }

    public static void main(String[] args) {
        Function<String, String> trim =
                trace("trim", String::trim);
        Function<String, Integer> length =
                trace("length", String::length);

        Function<String, Integer> flow = trim.andThen(length);
        System.out.println("result=" + flow.apply("  Java  "));
    }
}
```

Chạy:

```bash
javac TracePipelineDemo.java
java TracePipelineDemo
```

Output:

```text
trim input=  Java  
trim output=Java
length input=Java
length output=4
result=4
```

Phương thức `trace` nhận `Function<A,B>` và trả về `Function<A,B>`, vì vậy thêm logging **không làm đứt chuỗi kiểu**. Quan sát được giá trị trung gian `"Java"`, sau đó `4`. Trong môi trường thật, nên dùng logger thay vì `System.out`, gắn tên stage rõ ràng, không ghi dữ liệu nhạy cảm và chỉ kích hoạt mức log thích hợp. Wrapper này thêm side effect log và chi phí thực thi; không nên xem logging là điều kiện để pipeline đúng.

Nếu cần biết kiểu runtime của giá trị trung gian, chỉ kiểm tra ở những nơi thật sự cần thiết, có xử lý `null` và hiểu rằng `getClass()` phản ánh lớp của **giá trị**, không phục hồi được chữ ký generic của toàn pipeline. Kiểu dòng dữ liệu chủ yếu được mô tả bằng khai báo `Function<A,B>` ở thời điểm biên dịch.

## 8. Thứ tự thực thi cũng quyết định side effect, lỗi và giá trị `null`

Ghép hàm theo các phương thức mặc định của `Function` thực hiện các stage theo trình tự đã chọn. Vì thế:

- Nếu stage đầu ghi log, thay đổi trạng thái hoặc gọi I/O, side effect xảy ra trước stage sau.
- Nếu stage trước ném exception, stage sau không được gọi; exception được truyền về nơi gọi `apply` nếu không có code xử lý riêng.
- Nếu stage trước trả `null`, stage sau **có thể** nhận `null`; nó chạy được hay ném exception tùy định nghĩa của stage sau. Không có cơ chế tự động bỏ qua `null`.
- Truyền đối số `null` vào `andThen(null)` hoặc `compose(null)` sẽ bị từ chối bằng `NullPointerException` khi tạo tổ hợp theo phương thức mặc định của `Function`. Điều này khác với một stage hợp lệ tự trả `null` lúc chạy.
- Những bước có trạng thái hoặc gọi dịch vụ ngoài sẽ khiến thứ tự ảnh hưởng trực tiếp đến kết quả; không tự ý đổi `f.andThen(g)` thành `g.andThen(f)` chỉ vì cả hai đều xử lý cùng kiểu dữ liệu.

Chẳng hạn với `Function<String, Integer> parse = Integer::parseInt;` và `Function<Integer, Integer> doubleValue = n -> n * 2;`, biểu thức `parse.andThen(doubleValue).apply("x")` ném `NumberFormatException` ở bước `parse`; `doubleValue` chưa chạy.

Sự có mặt của generic đúng kiểu không đồng nghĩa với không có lỗi lúc chạy. Một số phép biến đổi còn cần hợp đồng về thứ tự và khả năng đảo ngược; chẳng hạn sau khi chuyển chuỗi thành số, không thể khôi phục chính xác khoảng trắng ban đầu chỉ bằng biến đổi ngược.

## 9. Phân biệt với các phép kết hợp interface chức năng khác

Không phải mọi phương thức có tên `andThen` đều truyền kết quả trung gian theo quy tắc `Function<A,B>`:

| API | Thứ tự/đặc điểm | Dòng dữ liệu |
| --- | --- | --- |
| `Function.andThen` | Chạy hàm hiện tại rồi hàm sau | Đầu ra hàm trước là đầu vào hàm sau |
| `Function.compose` | Chạy hàm `before` rồi hàm hiện tại | Đầu ra hàm `before` vào hàm hiện tại |
| `Consumer.andThen` | Chạy consumer thứ nhất rồi thứ hai | Cả hai nhận **cùng đối số**, không truyền kết quả vì `accept` trả `void` |
| `Predicate.and` | Tính điều kiện thứ hai chỉ khi điều kiện thứ nhất là `true` | Có **short-circuit**, không luôn chạy cả hai |
| `Predicate.or` | Tính điều kiện thứ hai chỉ khi điều kiện thứ nhất là `false` | Có **short-circuit** |
| `BiFunction.andThen` | Gọi hàm hai đối số trước rồi biến đổi kết quả | `(T,U) → R → V` |

Ví dụ có chủ đích về short-circuit:

```java
Predicate<String> nonNull = value -> value != null;
Predicate<String> atLeastThree = value -> value.length() >= 3;
Predicate<String> valid = nonNull.and(atLeastThree);

// valid.test(null) == false và không gọi atLeastThree.
// valid.test("Java") == true.
```

Đây là đoạn mã nằm trong phương thức, cần import `java.util.function.Predicate`. Nếu đảo thứ tự thành `atLeastThree.and(nonNull)`, lời gọi `test(null)` sẽ ném `NullPointerException` trước khi kịp kiểm tra không-null. Với `Consumer.andThen`, hai hành động thường được gọi tuần tự, nhưng nếu hành động thứ nhất ném exception thì hành động thứ hai không được gọi.

Ngoài ra, pipeline của `Stream.map(...).filter(...)` có **đánh giá lười (lazy evaluation)** và có thể liên quan đến xử lý song song; không tự động áp mô hình thời điểm chạy và thứ tự side effect của `Function.andThen` cho mọi thao tác trên Stream. Trong Stream, phải phân tích terminal operation, tính chất short-circuit và đặc điểm tuần tự/song song riêng.

## 10. Những lỗi hay gặp và cách kiểm tra

**Lỗi 1 — Đọc ngược `compose`.** Gặp `g.compose(f)`, hãy viết ngay `g(f(x))`; thế là rõ `f` chạy trước.

**Lỗi 2 — Chỉ xem kiểu cuối.** `Function<String,String>` có thể là `String → Integer → String`. Hãy lập bảng kiểu sau từng stage, không suy tất cả stage đều nhận và trả `String`.

**Lỗi 3 — Nối sai kiểu rồi cố ép cast.** Ép kiểu thô hoặc dùng `Function` raw type che mất sự bảo đảm của trình biên dịch và chuyển lỗi sang runtime. Sửa chữ ký và hướng dữ liệu thật của các bước.

**Lỗi 4 — Tưởng xây pipeline là đã chạy.** `Function<X,Y> combined = first.andThen(second);` chỉ tạo một hàm kết hợp. Kiểm chứng log khi gọi `combined.apply(x)`.

**Lỗi 5 — Bỏ qua thứ tự của side effect.** Với các bước có I/O, ghi trạng thái, log hoặc exception, đổi thứ tự có thể làm sai kết quả hoặc ngăn một bước được chạy.

**Lỗi 6 — Nhầm `andThen` của `Function` với `Consumer`, `Predicate` hay `Stream`.** Mỗi loại có quy tắc truyền dữ liệu, dừng sớm và thời điểm thực thi riêng.

**Lỗi 7 — Chỉ nhìn object lambda khi debug.** `getClass()`, danh tính tham chiếu và `toString()` của lambda không cho biết đầy đủ các kiểu trung gian và thứ tự thực thi. Nên log ở ranh giới stage và giữ kiểu khai báo rõ ràng.

## 11. Bài tự kiểm tra

Xét các hàm sau (đoạn mã đặt trong một phương thức):

```java
Function<String, String> a = String::trim;
Function<String, Integer> b = String::length;
Function<Integer, Integer> c = n -> n + 10;

Function<String, Integer> result = c.compose(b).compose(a);
```

Hãy trả lời trước khi chạy:

1. Với `result.apply("  ab  ")`, hàm nào chạy trước?
2. Kiểu trung gian sau `a`, sau `b` và sau `c` là gì?
3. Kết quả cuối cùng là gì?
4. Viết cùng pipeline bằng `andThen`.

Đáp án: trình tự `a → b → c`; sau `a` là `"ab"` kiểu `String`, sau `b` là `2` kiểu `Integer`, sau `c` là `12` kiểu `Integer`. Kết quả cuối là `12`; biểu thức tương đương là `a.andThen(b).andThen(c)`, cũng có kiểu `Function<String,Integer>`.

## 12. Quy tắc thực hành

Khi đọc hoặc thiết kế kết hợp hàm, viết được đầy đủ hai dòng sau:

```text
Thứ tự thực thi: stage1 -> stage2 -> stage3
Dòng kiểu:        Input  -> Mid1   -> Mid2   -> Output
```

Nếu muốn hàm A chạy trước B, viết `A.andThen(B)` hoặc `B.compose(A)`. Kiểm tra chữ ký từng nối, gọi `apply` khi cần chạy, và dùng log/wrapper có kiểu để quan sát kết quả trung gian. Cách này giúp phân biệt lỗi **thứ tự**, lỗi **kiểu tại thời điểm biên dịch** và lỗi **dữ liệu/thực thi** — ba vấn đề thường xuất hiện đồng thời khi kết hợp nhiều hàm.

**Tài liệu tham khảo:** Java SE API của `java.util.function.Function` (`compose`, `andThen`), `Consumer`, `Predicate` và `BiFunction`; Java Language Specification về target typing và lambda expressions.