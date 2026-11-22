# Kết hợp vòng lặp qua loop, whileLoop và doWhileLoop

## 1. Vì sao MethodHandles có combinator cho vòng lặp?

`MethodHandle` biểu diễn một lời gọi có kiểu cụ thể. Ngoài việc tra cứu và gọi một method, Java 9 bổ sung các combinator trong `MethodHandles` để ghép nhiều handle nhỏ thành một luồng điều khiển hoàn chỉnh.

Ba combinator liên quan đến vòng lặp:

- `whileLoop(init, pred, body)`: kiểm tra điều kiện trước mỗi lần chạy thân vòng lặp.
- `doWhileLoop(init, body, pred)`: chạy thân trước, sau đó mới kiểm tra điều kiện.
- `loop(clauses...)`: combinator tổng quát hơn, hỗ trợ nhiều biến vòng lặp và nhiều clause phối hợp với nhau.

Các combinator trả về một `MethodHandle` mới. Khi gọi handle kết quả, JVM thực hiện luồng lặp đã được mô tả bởi những handle thành phần. Chúng không phải cú pháp vòng lặp mới của Java và cũng không nhận lambda tùy ý; mỗi phần phải là một MethodHandle có chữ ký phù hợp.

## 2. Kiểu dữ liệu và vai trò của các handle thành phần

Với hai convenience combinator `whileLoop` và `doWhileLoop`, có thể hình dung một biến trạng thái vòng lặp kiểu `V` và các tham số đầu vào cố định kiểu `A...`:

| Thành phần | Chữ ký khái quát | Vai trò |
|---|---|---|
| `init` | `(A...) -> V` | Tạo trạng thái ban đầu |
| `pred` | `(V, A...) -> boolean` | Quyết định tiếp tục hay dừng |
| `body` | `(V, A...) -> V` | Tạo trạng thái kế tiếp |
| Loop handle | `(A...) -> V` | Thực thi vòng lặp và trả trạng thái cuối |

`A...` là các tham số đầu vào của toàn bộ vòng lặp. Chúng được giữ nguyên qua các lần lặp; `V` là biến trạng thái được cập nhật sau mỗi lần gọi body.

Nếu body trả về `void`, vòng lặp không có biến trạng thái kiểu `V` và kết quả của loop handle cũng là `void`. Initializer là tùy chọn; khi `init == null`, biến vòng lặp được khởi tạo bằng giá trị mặc định của kiểu tương ứng.

Điều quan trọng là các chữ ký phải khớp nhau. Predicate phải trả về primitive `boolean`; body phải nhận trạng thái hiện tại và trả về trạng thái kế tiếp cùng kiểu. Các tham số ngoài phải tương thích giữa các handle.

## 3. whileLoop: kiểm tra điều kiện trước thân

Chữ ký:

~~~java
MethodHandle whileLoop(
        MethodHandle init,
        MethodHandle pred,
        MethodHandle body)
~~~

Thứ tự thực thi tương đương:

~~~java
V state = init(arguments);
while (pred(state, arguments)) {
    state = body(state, arguments);
}
return state;
~~~

Predicate được gọi trước mỗi lần chạy body. Nếu predicate trả false ngay lần đầu, body không chạy lần nào.

Ví dụ đếm từ 0 đến giới hạn:

~~~java
static int zero(int limit) {
    return 0;
}

static boolean below(int counter, int limit) {
    return counter < limit;
}

static int increment(int counter, int limit) {
    return counter + 1;
}
~~~

Khi ghép các handle này, loop handle có kiểu `(int)int`. Gọi với giới hạn 3 trả về 3; gọi với giới hạn 0 trả về 0 vì predicate sai ngay từ đầu.

## 4. doWhileLoop: chạy thân ít nhất một lần

Chữ ký:

~~~java
MethodHandle doWhileLoop(
        MethodHandle init,
        MethodHandle body,
        MethodHandle pred)
~~~

Thứ tự thực thi tương đương:

~~~java
V state = init(arguments);
do {
    state = body(state, arguments);
} while (pred(state, arguments));
return state;
~~~

Khác biệt chính là body được gọi trước predicate. Vì vậy, nếu initializer tạo trạng thái 0 và body tăng 1, lời gọi `doWhileLoop(...).invokeExact(0)` trả về 1. Body luôn chạy ít nhất một lần, miễn là việc khởi tạo và body hoàn tất bình thường.

Thứ tự tham số của factory cũng phản ánh cách dùng: `init, body, pred`. Đừng truyền nhầm thứ tự `init, pred, body` như ở `whileLoop`.

## 5. loop: combinator tổng quát với nhiều clause

`MethodHandles.loop` cho phép mô tả một vòng lặp bằng một hoặc nhiều clause. Mỗi clause là một mảng gồm tối đa bốn MethodHandle theo đúng thứ tự:

~~~java
MethodHandle[] clause = {
    init,  // initializer
    step,  // cập nhật biến vòng lặp
    pred,  // điều kiện thoát
    fini   // tính kết quả khi clause này thoát
};

MethodHandle loop = MethodHandles.loop(clause);
~~~

Có thể bỏ một thành phần bằng `null`. Các vị trí không được bỏ sẽ được giữ đúng thứ tự; mảng ngắn hơn bốn phần tử được hiểu như đã thêm các giá trị null ở cuối.

Ý nghĩa từng vị trí:

- **init**: chạy một lần trước vòng lặp để khởi tạo biến trạng thái của clause. Init nhận các tham số ngoài của loop, không nhận biến vòng lặp vì chúng chưa được tạo.
- **step**: cập nhật biến trạng thái ở mỗi lượt. Giá trị trả về của step trở thành giá trị hiện tại mới.
- **pred**: trả boolean để quyết định có thoát hay không. Khi pred trả false, loop gọi finalizer tương ứng.
- **fini**: tạo kết quả trả về khi predicate của clause đó yêu cầu thoát. Nếu một clause không có finalizer phù hợp, kết quả của loop có thể là void theo cấu trúc các clause.

Các biến vòng lặp được sắp theo thứ tự clause. Các hàm không phải init có thể nhận các biến vòng lặp đã tạo cùng tham số ngoài của loop. Những hàm không cần toàn bộ tham số có thể bỏ qua phần tham số ở cuối theo các quy tắc kết nối của combinator.

### Thứ tự thực thi của generic loop

Khi gọi loop handle:

1. Các init được chạy theo thứ tự clause để tạo các biến vòng lặp.
2. Ở mỗi lượt, từng clause được xử lý theo thứ tự.
3. Với mỗi clause, step chạy trước pred.
4. Nếu step trả về giá trị, biến trạng thái tương ứng được cập nhật ngay và giá trị mới có thể được các hàm tiếp theo quan sát.
5. Nếu pred trả false, fini của clause đó được gọi và kết quả được trả về từ toàn bộ loop.
6. Nếu tất cả predicate luôn trả true, loop không có đường thoát thông thường; nó chỉ dừng nếu một handle ném exception hoặc có cơ chế thoát khác trong logic.

Điểm dễ nhầm: generic `loop` không giống một vòng `while` duy nhất có predicate đứng đầu. Trong mỗi clause, step chạy trước pred. Nếu cần semantics predicate trước body, dùng `whileLoop` để biểu đạt trực tiếp và dễ đọc hơn.

## 6. Ví dụ generic loop: tính giai thừa bằng hai biến trạng thái

Ta có thể biểu diễn `factorial(n)` với hai biến vòng lặp:

- `counter`: bộ đếm, ban đầu là 0, mỗi lượt tăng 1.
- `accumulator`: tích lũy, ban đầu là 1, mỗi lượt nhân với counter mới.

Clause thứ nhất chỉ cập nhật counter. Clause thứ hai khởi tạo accumulator, nhân accumulator với counter, kiểm tra điều kiện và trả accumulator khi kết thúc.

~~~java
static int one(int limit) {
    return 1;
}

static int incrementCounter(int counter, int accumulator, int limit) {
    return counter + 1;
}

static int multiply(int counter, int accumulator, int limit) {
    return counter * accumulator;
}

static boolean keepGoing(int counter, int accumulator, int limit) {
    return counter < limit;
}

static int result(int counter, int accumulator, int limit) {
    return accumulator;
}
~~~

Các clause được ghép như sau:

~~~java
MethodHandle[] counterClause = {
    null,
    MH_incrementCounter
};

MethodHandle[] accumulatorClause = {
    MH_one,
    MH_multiply,
    MH_keepGoing,
    MH_result
};

MethodHandle factorial = MethodHandles.loop(
        counterClause, accumulatorClause);
~~~

Counter không có initializer nên dùng giá trị mặc định 0. Accumulator được khởi tạo bằng 1. Mỗi lượt generic loop tăng counter trước, sau đó nhân accumulator với counter mới, rồi kiểm tra `counter < limit`. Khi điều kiện sai, finalizer trả accumulator.

Với `limit = 5`, các giá trị lần lượt là:

| Lượt | Counter sau step | Accumulator sau step | Predicate |
|---:|---:|---:|---|
| 1 | 1 | 1 | true |
| 2 | 2 | 2 | true |
| 3 | 3 | 6 | true |
| 4 | 4 | 24 | true |
| 5 | 5 | 120 | false |

Kết quả cuối cùng là 120. Với giới hạn 0, loop vẫn thực hiện một step trước predicate; counter thành 1, accumulator vẫn là 1, predicate sai và finalizer trả 1. Ví dụ này minh họa rõ thứ tự step-before-predicate của generic `loop`.

## 7. Chương trình Java hoàn chỉnh: cả ba combinator

Ví dụ dưới đây tạo MethodHandle bằng `MethodHandles.lookup().findStatic`, sau đó ghép `whileLoop`, `doWhileLoop` và `loop`. Mã nguồn có thể biên dịch và chạy độc lập.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class MethodHandleLoopDemo {
    private static int zero(int limit) {
        return 0;
    }

    private static boolean below(int counter, int limit) {
        return counter < limit;
    }

    private static int increment(int counter, int limit) {
        return counter + 1;
    }

    private static int one(int limit) {
        return 1;
    }

    private static int incrementCounter(
            int counter, int accumulator, int limit) {
        return counter + 1;
    }

    private static int multiply(
            int counter, int accumulator, int limit) {
        return counter * accumulator;
    }

    private static boolean keepGoing(
            int counter, int accumulator, int limit) {
        return counter < limit;
    }

    private static int result(
            int counter, int accumulator, int limit) {
        return accumulator;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodType intFromInt =
                MethodType.methodType(int.class, int.class);
        MethodType boolFromTwoInts =
                MethodType.methodType(boolean.class, int.class, int.class);
        MethodType intFromTwoInts =
                MethodType.methodType(int.class, int.class, int.class);
        MethodType intFromThreeInts =
                MethodType.methodType(
                        int.class, int.class, int.class, int.class);
        MethodType boolFromThreeInts =
                MethodType.methodType(
                        boolean.class, int.class, int.class, int.class);

        MethodHandle init = lookup.findStatic(
                MethodHandleLoopDemo.class, "zero", intFromInt);
        MethodHandle pred = lookup.findStatic(
                MethodHandleLoopDemo.class, "below", boolFromTwoInts);
        MethodHandle body = lookup.findStatic(
                MethodHandleLoopDemo.class, "increment", intFromTwoInts);

        MethodHandle whileLoop =
                MethodHandles.whileLoop(init, pred, body);
        MethodHandle doWhileLoop =
                MethodHandles.doWhileLoop(init, body, pred);

        int whileResult = (int) whileLoop.invokeExact(3);
        int doWhileResult = (int) doWhileLoop.invokeExact(3);
        int doWhileZero = (int) doWhileLoop.invokeExact(0);

        System.out.println("whileLoop(3) = " + whileResult);
        System.out.println("doWhileLoop(3) = " + doWhileResult);
        System.out.println("doWhileLoop(0) = " + doWhileZero);
        System.out.println("whileLoop type = " + whileLoop.type());
        System.out.println("doWhileLoop type = " + doWhileLoop.type());

        MethodHandle one = lookup.findStatic(
                MethodHandleLoopDemo.class, "one", intFromInt);
        MethodHandle incrementCounter = lookup.findStatic(
                MethodHandleLoopDemo.class,
                "incrementCounter", intFromThreeInts);
        MethodHandle multiply = lookup.findStatic(
                MethodHandleLoopDemo.class, "multiply", intFromThreeInts);
        MethodHandle keepGoing = lookup.findStatic(
                MethodHandleLoopDemo.class,
                "keepGoing", boolFromThreeInts);
        MethodHandle result = lookup.findStatic(
                MethodHandleLoopDemo.class, "result", intFromThreeInts);

        MethodHandle[] counterClause = {
            null, incrementCounter
        };
        MethodHandle[] accumulatorClause = {
            one, multiply, keepGoing, result
        };

        MethodHandle factorial = MethodHandles.loop(
                counterClause, accumulatorClause);

        int factorialFive = (int) factorial.invokeExact(5);
        int factorialZero = (int) factorial.invokeExact(0);

        System.out.println("loop factorial(5) = " + factorialFive);
        System.out.println("loop factorial(0) = " + factorialZero);
        System.out.println("generic loop type = " + factorial.type());
    }
}
~~~

Lưu mã nguồn trong `MethodHandleLoopDemo.java`, biên dịch và chạy với Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all MethodHandleLoopDemo.java
java MethodHandleLoopDemo
~~~

Kết quả:

~~~text
whileLoop(3) = 3
doWhileLoop(3) = 3
doWhileLoop(0) = 1
whileLoop type = (int)int
doWhileLoop type = (int)int
loop factorial(5) = 120
loop factorial(0) = 1
generic loop type = (int)int
~~~

Ví dụ cũng có thể biên dịch với `javac --release 9 -Xlint:all`. Các combinator `loop`, `whileLoop` và `doWhileLoop` đều có từ Java 9; cú pháp gọi `invokeExact` yêu cầu kiểu tại call site khớp chính xác với kiểu MethodHandle.

## 8. MethodType và kiểm tra tương thích

Trước khi tạo loop handle, các MethodHandle thành phần phải có chữ ký tương thích. Có thể kiểm tra bằng:

~~~java
System.out.println(init.type());
System.out.println(pred.type());
System.out.println(body.type());
System.out.println(loop.type());
~~~

Với ví dụ `whileLoop`:

~~~text
init: (int)int
pred: (int, int)boolean
body: (int, int)int
loop: (int)int
~~~

Tham số đầu của predicate/body là biến trạng thái; tham số thứ hai là loop parameter `limit`. Loop handle kết quả chỉ nhận loop parameter `limit`, còn trạng thái được giữ nội bộ.

Nếu các kiểu không tương thích hoặc các clause generic không thể được kết nối theo quy tắc, combinator ném `IllegalArgumentException` khi tạo loop handle. Nếu lời gọi `invokeExact` có kiểu call-site khác với kiểu handle, có thể gặp `WrongMethodTypeException`. Vì vậy nên kiểm tra `MethodType` sớm, trước khi thực thi trong đường đi chính.

## 9. Chọn combinator nào?

| Nhu cầu | Nên dùng | Lý do |
|---|---|---|
| Điều kiện được kiểm tra trước mỗi lượt | `whileLoop` | Semantics rõ ràng như while |
| Body phải chạy ít nhất một lần | `doWhileLoop` | Semantics rõ ràng như do-while |
| Nhiều biến trạng thái hoặc nhiều điều kiện thoát | `loop` | Mỗi clause có init/step/pred/fini riêng |
| Lặp một số lần đã biết | `countedLoop` | Combinator chuyên cho số lần lặp |
| Duyệt Iterator | `iteratedLoop` | Combinator chuyên cho Iterator |

Dù `loop` có thể mô tả nhiều kiểu vòng lặp, không nên dùng nó cho mọi trường hợp. Convenience combinator thường dễ đọc và ít yêu cầu ghép chữ ký hơn. Dùng generic `loop` khi cần phối hợp nhiều biến vòng lặp hoặc nhiều predicate/finalizer.

## 10. Lỗi thường gặp

- **Đảo thứ tự tham số của doWhileLoop:** chữ ký là `init, body, pred`, khác `whileLoop`.
- **Cho rằng whileLoop luôn chạy body:** nếu predicate sai ban đầu, body không được gọi.
- **Cho rằng doWhileLoop có thể chạy 0 lần:** body luôn chạy ít nhất một lần nếu khởi tạo và body hoàn tất bình thường.
- **Nhầm thứ tự generic loop:** trong từng clause, step chạy trước predicate; đừng giả định predicate chạy đầu lượt.
- **Sai kiểu return của predicate:** predicate phải trả primitive `boolean`.
- **Sai kiểu trạng thái:** initializer và step của cùng biến phải có kiểu trả về tương thích/đồng nhất theo quy tắc combinator.
- **Nhầm loop parameters với loop variables:** tham số ngoài được giữ nguyên qua các lượt; biến vòng lặp được khởi tạo và cập nhật nội bộ.
- **Bỏ qua finalizer:** với generic loop, finalizer của clause thoát quyết định giá trị trả về.
- **Tạo loop không có đường thoát:** nếu mọi predicate luôn true, vòng lặp không kết thúc bình thường.
- **Gọi invokeExact với kiểu không khớp:** kiểm tra `MethodHandle.type()` và kiểu tĩnh tại call site.
- **Dùng generic loop quá phức tạp:** ưu tiên whileLoop/doWhileLoop khi chỉ có một biến trạng thái và một điều kiện.

## 11. Checklist khi ghép MethodHandle loop

1. Vòng lặp cần kiểm tra predicate trước hay sau body?
2. Biến trạng thái có kiểu gì và initializer trả đúng kiểu đó chưa?
3. Predicate có trả boolean và nhận đúng biến trạng thái cùng tham số ngoài không?
4. Body có nhận trạng thái hiện tại và trả trạng thái kế tiếp đúng kiểu không?
5. Với generic loop, mỗi clause đã đặt đúng vị trí init/step/pred/fini chưa?
6. Các clause có cùng thứ tự biến vòng lặp và loop parameters tương thích không?
7. Có ít nhất một đường thoát bình thường và finalizer trả đúng kết quả không?
8. Kiểu MethodHandle kết quả có đúng với lời gọi `invokeExact` không?

## 12. Tài liệu tham khảo

- [MethodHandles — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/invoke/MethodHandles.html)
- [MethodHandles — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [MethodHandle — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html)