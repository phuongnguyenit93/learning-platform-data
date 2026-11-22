# Dừng phần biểu thức hoặc câu lệnh chưa hoàn tất khi phát sinh Exception

> Java Core – Exception · Nhóm: Luồng thực thi · Ví dụ chạy độc lập với Java 17+.

## 1. Điều gì bị dừng khi một ngoại lệ xuất hiện?

Java đánh giá biểu thức để tạo ra giá trị, thực hiện phép gán hoặc gọi phương thức; đồng thời chạy các câu lệnh theo luồng điều khiển. Nếu một bước ném ngoại lệ, bước đó **không hoàn thành bình thường**. Những bước còn lại đòi hỏi nó phải hoàn thành sẽ bị bỏ qua. Java chuyển điều khiển đến bộ xử lý ngoại lệ phù hợp, hoặc truyền lỗi ra phương thức gọi.

Đặc tả Java gọi trường hợp này là *abrupt completion* (kết thúc bất thường), đối lập với *normal completion* (kết thúc bình thường).

Ví dụ giả định:

```java
int result = first() + second() + third();
```

Nếu `first()` hoàn thành nhưng `second()` ném ngoại lệ:

1. `first()` **đã chạy**; tác dụng phụ nó tạo ra vẫn tồn tại.
2. `second()` **đã bắt đầu**, nhưng không trả về kết quả bình thường.
3. `third()` **không được gọi** theo luồng đánh giá bình thường.
4. Không có tổng hoàn chỉnh để gán cho `result`; câu lệnh gán chưa hoàn tất.
5. Nếu có nhánh `catch` phù hợp, mã trong nhánh ấy được chạy. Java không tự quay lại thực hiện `third()` sau khi xử lý ngoại lệ.

Chìa khóa là phân biệt **phần việc chưa được thực hiện** với **những tác dụng phụ đã xảy ra trước điểm lỗi**. Ngoại lệ không tự hoàn tác tác dụng phụ.

## 2. Cơ sở ngôn ngữ: biểu thức và câu lệnh kết thúc bất thường

Theo [Java Language Specification §15.6](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.6), nếu việc tính biểu thức bao ngoài phụ thuộc một biểu thức con, mà biểu thức con kết thúc bất thường, biểu thức bao ngoài cũng kết thúc bất thường vì cùng lý do. Những bước đánh giá thông thường tiếp theo sẽ không thực hiện.

JLS §15.7 quy định thứ tự đánh giá toán hạng và đối số. Trong những trường hợp tương ứng, Java đánh giá từ trái sang phải. Nếu bước ở bên trái ném ngoại lệ, phần phụ thuộc phía sau không được đánh giá.

Câu lệnh cũng có thể kết thúc bất thường. JLS §14.1 liệt kê các lý do như ném ngoại lệ (`throw`), `return`, `break`, `continue` và `yield` khi thích hợp. **Không phải mọi abrupt completion đều là exception**: ví dụ `return` là chuyển điều khiển theo cấu trúc ngôn ngữ, không phải tự động ném một đối tượng `Throwable`. Ở bài này ta xem xét riêng tình huống ngoại lệ.

```text
Đánh giá biểu thức / chạy câu lệnh
               |
           Bước hiện tại
            /      \
    Bình thường   Ném exception
        |               |
        v               v
   Bước tiếp theo     Dừng đường đánh giá
   nếu được chọn      thông thường còn lại
                        |
                        v
                  Rời phạm vi liên quan
                  / chạy cleanup theo quy tắc
                        |
                        v
                  catch phù hợp hoặc
                  truyền exception ra caller
```

Sơ đồ là quy trình khái quát. `finally` và `try-with-resources` có quy tắc thực thi riêng khi rời phạm vi. Một số cách chọn nhánh như `&&`, `||`, `?:` chủ động bỏ qua toán hạng khi không cần đánh giá, **ngay cả khi không có ngoại lệ**.

## 3. Những vị trí thường bị ngắt giữa chừng

### 3.1. Toán hạng của phép toán

```java
int total = calculateLeft() + fail() + calculateRight();
```

Với lời gọi `fail()` ném ngoại lệ, `calculateRight()` chưa chạy; kết quả toàn phép cộng chưa hoàn tất. Nếu `calculateLeft()` đã tăng bộ đếm hoặc ghi log, tác dụng phụ ấy vẫn đã xảy ra.

Lưu ý thứ tự đánh giá khác thứ tự ưu tiên toán tử. Dấu ngoặc và độ ưu tiên quyết định cấu trúc biểu thức, còn JLS quyết định thứ tự đánh giá các phần trong cấu trúc. Đừng suy rằng mọi biểu thức bên phải theo mặt chữ luôn được chạy.

Đối với phép chia số nguyên, toán hạng được đánh giá trước, phép chia mới xảy ra:

```java
int result = left() / right();
```

Nếu `left()` và `right()` đều trả về bình thường, `right()` trả về 0, thì phép chia ném `ArithmeticException` sau khi hai lời gọi đã chạy. Nếu `left()` đã ném lỗi trước, `right()` chưa chạy. Số thực `double` chia cho `0.0` lại tuân quy tắc số thực, thường cho Infinity hoặc NaN, nên không dùng nó thay cho ví dụ chia số nguyên.

### 3.2. Danh sách đối số của phương thức hoặc constructor

```java
send(readId(), parseAmount(), auditCode());
```

Nếu `parseAmount()` ném ngoại lệ, `readId()` có thể đã hoàn thành, `auditCode()` chưa chạy và phần thân `send` không được thực thi. Java đánh giá các biểu thức đối số theo thứ tự trái sang phải; một đối số kết thúc bất thường ngăn phần còn lại.

Với constructor, các biểu thức đối số cũng tuân thứ tự trái sang phải. Đối với lời gọi qua đối tượng và truy cập trường/mảng, cần đọc các quy tắc đánh giá đặc thù nếu muốn biết chính xác thời điểm kiểm tra `null` và những side effect liên quan.

### 3.3. Phép gán chưa hoàn tất

Giả sử:

```java
int amount = 100;
int[] effects = {0};

try {
    amount = ++effects[0] + fail();
} catch (IllegalStateException ex) {
    System.out.println("caught");
}
```

Đây là **đoạn mã minh họa**, giả định `fail()` được định nghĩa trả về `int` nếu thành công nhưng sẽ ném `IllegalStateException` trong tình huống thử. `++effects[0]` tăng phần tử mảng từ 0 lên 1 trước lỗi. Vế phải của phép gán không hoàn tất, nên `amount` vẫn là 100. **Giá trị của `effects[0]` đã đổi**, vì nó là tác dụng phụ của một biểu thức con đã chạy.

Việc gán không hoàn thành không tương đương với việc rollback toàn bộ biểu thức hoặc giao dịch.

### 3.4. Truy cập mảng, ép kiểu và dereference

```java
int result = numbers[index()] + bonus();
```

Giả sử `numbers` là mảng có một phần tử, `index()` trả về 5. `index()` có thể đã tạo side effect; phép truy cập phần tử ném `ArrayIndexOutOfBoundsException`; `bonus()` chưa chạy.

Tương tự, `ClassCastException`, `NullPointerException` hoặc ngoại lệ phát sinh khi gọi API có thể khiến biểu thức bao ngoài dừng. Tuy nhiên, thứ tự tính biểu thức đích, đối số và kiểm tra runtime có những quy tắc chính xác; không nên phát biểu chung rằng hễ NPE thì mọi tham số chưa bao giờ được đánh giá.

### 3.5. Short-circuit khác với ngoại lệ

```java
boolean safe = false && mayThrow();
int chosen = true ? 7 : mightFail();
```

Trong hai dòng này, phần bên phải `&&` và nhánh không được chọn của `?:` không chạy vì quy tắc *conditional evaluation*, dù **không có lỗi nào xảy ra**.

Nếu là toán tử boolean `&` hoặc `|`, Java vẫn đánh giá vế phải khi vế trái hoàn thành bình thường. Nhưng một exception thực sự từ vế trái vẫn chấm dứt biểu thức bao ngoài, khiến vế sau không được đánh giá.

## 4. Chương trình chạy được: lần theo phần đã chạy và phần bị bỏ qua

Lưu trọn mã nguồn dưới đây thành tệp **`AbruptCompletionDemo.java`**. Không cần thư viện ngoài, input file hay tham số chạy.

```java
public class AbruptCompletionDemo {

    private static int trace(String label, int value) {
        System.out.println(label);
        return value;
    }

    private static int explode(String label) {
        System.out.println(label);
        throw new IllegalStateException(label);
    }

    private static boolean failBoolean() {
        System.out.println("never-run");
        throw new IllegalStateException("boolean failure");
    }

    private static void accept3(int a, int b, int c) {
        System.out.println("accept3 called");
    }

    public static void main(String[] args) {
        binaryExpression();
        argumentList();
        unfinishedAssignment();
        arrayAccess();
        interruptedStatements();
        finallyOnUnwind();
        conditionalEvaluation();
    }

    private static void binaryExpression() {
        System.out.println("== binary ==");
        try {
            int result = trace("left", 2)
                    + explode("middle")
                    + trace("right", 4);
            System.out.println("result=" + result);
        } catch (IllegalStateException ex) {
            System.out.println("catch=" + ex.getMessage());
        }
    }

    private static void argumentList() {
        System.out.println("== arguments ==");
        try {
            accept3(
                    trace("arg1", 10),
                    explode("arg2"),
                    trace("arg3", 30));
        } catch (IllegalStateException ex) {
            System.out.println("catch=" + ex.getMessage());
        }
    }

    private static void unfinishedAssignment() {
        System.out.println("== assignment ==");
        int balance = 100;
        int[] effects = {0};

        try {
            balance = ++effects[0] + explode("assignment-failure");
        } catch (IllegalStateException ex) {
            System.out.println("catch=" + ex.getMessage());
        }

        System.out.println("balance=" + balance
                + ", effects=" + effects[0]);
    }

    private static void arrayAccess() {
        System.out.println("== array ==");
        int[] scores = {10};

        try {
            int result = scores[trace("index", 4)]
                    + trace("rhs", 20);
            System.out.println("result=" + result);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("catch=ArrayIndexOutOfBoundsException");
        }
    }

    private static void interruptedStatements() {
        System.out.println("== statements ==");
        try {
            System.out.println("before");
            int value = explode("fail-statement");
            System.out.println("after");
        } catch (IllegalStateException ex) {
            System.out.println("catch=" + ex.getMessage());
        }
        System.out.println("resume-after-catch");
    }

    private static void finallyOnUnwind() {
        System.out.println("== finally ==");
        try {
            try {
                trace("inside", 1);
                explode("cleanup-failure");
            } finally {
                System.out.println("finally");
            }
        } catch (IllegalStateException ex) {
            System.out.println("catch=" + ex.getMessage());
        }
    }

    private static void conditionalEvaluation() {
        System.out.println("== conditional ==");
        boolean ok = false && failBoolean();
        System.out.println("false && failBoolean()=" + ok);

        int chosen = true
                ? trace("selected", 7)
                : explode("unused");
        System.out.println("chosen=" + chosen);
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 AbruptCompletionDemo.java
java AbruptCompletionDemo
```

Stdout **chính xác**:

```text
== binary ==
left
middle
catch=middle
== arguments ==
arg1
arg2
catch=arg2
== assignment ==
assignment-failure
catch=assignment-failure
balance=100, effects=1
== array ==
index
catch=ArrayIndexOutOfBoundsException
== statements ==
before
fail-statement
catch=fail-statement
resume-after-catch
== finally ==
inside
cleanup-failure
finally
catch=cleanup-failure
== conditional ==
false && failBoolean()=false
selected
chosen=7
```

Những chuỗi **không được in** cũng là bằng chứng: `right`, `arg3`, `accept3 called`, `rhs`, `after`, `never-run` và `unused`. Trình biên dịch không cần biết trước `explode` chắc chắn ném exception; trên lý thuyết hàm có kiểu trả về `int` nhưng khi chạy nó ném trước khi có giá trị.

## 5. Phân tích từng tình huống

### Phép toán đang tính: `binaryExpression`

`trace("left", 2)` in `left` và hoàn thành. `explode("middle")` in `middle` rồi ném `IllegalStateException`. Giá trị cho vế cộng tiếp theo không tồn tại, nên `trace("right", 4)` không chạy. Câu lệnh in `result` không chạy. Nhánh `catch` in `catch=middle`.

### Tham số thứ hai lỗi: `argumentList`

`trace("arg1", 10)` chạy. `explode("arg2")` ném lỗi; `trace("arg3", 30)` chưa chạy. Vì vậy không in `accept3 called`: thân `accept3` chưa bắt đầu.

### Side effect đã hoàn thành: `unfinishedAssignment`

`++effects[0]` đã làm giá trị từ 0 thành 1. Khi `explode("assignment-failure")` ném lỗi, phép gán ngoài cùng không hoàn tất, nên `balance` vẫn là 100. Do đó dòng cuối in `balance=100, effects=1`. **Hai biến có trạng thái sau lỗi khác nhau** dù cùng xuất hiện trong một câu lệnh.

### Truy cập ngoài giới hạn: `arrayAccess`

`trace("index", 4)` in `index`, sau đó Java phát hiện chỉ số 4 vượt quá mảng có một phần tử. `ArrayIndexOutOfBoundsException` khiến phép cộng với `trace("rhs", 20)` không được thực hiện. Nhánh catch in tên kiểu lỗi cố định, không phụ thuộc cách JVM diễn đạt message.

### Câu lệnh tiếp theo không chạy: `interruptedStatements`

Chương trình in `before`. Biểu thức khởi tạo biến `value` gọi `explode("fail-statement")` và ném exception. Dòng `after` **không được thực hiện**. Sau khi catch in thông báo lỗi, lệnh nằm sau cấu trúc `try/catch` chạy và in `resume-after-catch`. Java không tiếp tục từ giữa câu lệnh khởi tạo `value`.

### Cleanup khi chuyển điều khiển: `finallyOnUnwind`

`explode("cleanup-failure")` làm thân `try` kết thúc bất thường. Trước khi handler ở cấp ngoài nhận lỗi, khối `finally` ở cấp trong được chạy và in `finally`. Vì khối này hoàn tất bình thường, ngoại lệ gốc tiếp tục đến catch ngoài, nơi in `catch=cleanup-failure`. Việc chạy `finally` không đồng nghĩa quay lại bước đang tính dở.

### Không đánh giá nhánh không được chọn: `conditionalEvaluation`

`false && failBoolean()` không gọi `failBoolean()`, nên không ném ngoại lệ. Toán tử điều kiện chọn `trace("selected", 7)`, không chạy `explode("unused")`. Đây là bỏ qua do chọn nhánh bình thường, cần phân biệt với dừng vì exception.

## 6. Nếu không có catch tại chỗ thì câu lệnh nào chạy tiếp?

Xét luồng:

```text
main()
  |
  +-- process()
        |
        +-- stepA()   → thành công, side effects còn lại
        |
        +-- stepB()   → ném exception
        |
        +-- stepC()   → không chạy
  |
  +-- phần sau lời gọi process() trong try → không chạy
  |
  +-- catch tương ứng → xử lý lỗi
  |
  +-- câu lệnh sau try/catch → chạy nếu handler hoàn tất bình thường
```

Ngoại lệ lan ra phương thức gọi khi không được xử lý tại chỗ. Nó không tự động kết thúc toàn JVM: một handler ở lớp gọi bên ngoài có thể xử lý và tiếp tục ở vị trí mới. Nếu không có handler, exception có thể đi tới uncaught-exception handler của thread.

Đối chiếu thêm:

| Điểm phát sinh | Bước không hoàn tất | Điểm tiếp tục khi xử lý được |
| --- | --- | --- |
| Khởi tạo biến `int x = bad();` | Giá trị khởi tạo và câu lệnh tiếp theo trong khối đang bị rời | Bên trong `catch` phù hợp |
| Đối số hàm `run(a(), bad(), c())` | `c()` và phần thân `run` | `catch` của phạm vi gọi |
| Điều kiện `if (badBoolean())` | Chưa chọn nhánh true/false | `catch` phù hợp |
| Điều kiện `while (badBoolean())` | Lượt đánh giá điều kiện không hoàn thành | `catch` ngoài hoặc trong cấu trúc phù hợp |
| Giá trị `return bad();` | Chưa có giá trị return bình thường | Handler được tìm qua các phạm vi |
| Đọc từng bản ghi với catch **trong** vòng lặp | Chỉ phần còn lại của xử lý bản ghi lỗi | Mã trong handler rồi logic vòng lặp kế tiếp |
| Exception thoát ra khỏi vòng lặp, catch **ngoài** | Vòng lặp không tự quay lại | Handler ngoài vòng lặp |

Nếu muốn thử lại sau lỗi, ứng dụng phải **chủ động viết vòng lặp/retry** và xem lại tác dụng phụ của lần thử trước. Việc bắt lỗi đơn thuần không có chức năng thực thi lại.

## 7. Vì sao `finally` và tài nguyên vẫn có thể chạy?

Theo JLS §14.20, khi rời một khối `try` vì exception, các phần xử lý liên quan được áp dụng theo quy tắc:

- Nếu tìm thấy `catch` phù hợp, khối catch được thực thi thay cho việc tiếp tục phần thân try.
- `finally` liên quan được thực hiện khi rời cấu trúc trong những tình huống mà ngôn ngữ quy định. Nếu `finally` hoàn tất bình thường, lý do kết thúc bất thường trước đó có thể tiếp tục được truyền đi.
- Nếu `finally` kết thúc bất thường vì ngoại lệ khác hoặc `return`, kết quả điều khiển trước có thể bị thay thế. Vì thế hạn chế `throw` và `return` trong `finally`.
- `try-with-resources` đóng tài nguyên theo cơ chế tự động. Nếu phần thân ném lỗi rồi `close()` cũng ném lỗi, ngoại lệ từ thân khối được ưu tiên và lỗi đóng thường xuất hiện trong `getSuppressed()` của ngoại lệ chính.

Các thao tác này là những **đường dọn dẹp riêng**, không phải tiếp tục đánh giá những toán hạng hoặc câu lệnh đã bị bỏ qua. Những tình huống JVM bị chấm dứt đột ngột có thể ngăn cleanup chạy như thường lệ; không diễn giải `finally` thành cam kết tuyệt đối cho mọi trường hợp.

## 8. Điều gì xảy ra với trạng thái và giao dịch?

Exception thay đổi luồng điều khiển, **không tạo phép rollback tự động**. Từ ví dụ `unfinishedAssignment`, ta biết `effects[0]` vẫn là 1. Nguyên lý tương tự áp dụng cho nhiều tác dụng phụ:

- Gán biến, thay đổi trường, cập nhật collection đã hoàn thành trước lỗi.
- Ghi một phần nội dung xuống tệp.
- Gửi một HTTP request hoặc phát một sự kiện ra hệ thống khác.
- Thay đổi dữ liệu database, tùy tình trạng transaction và cơ chế rollback thực tế.

Muốn có tính nguyên tử, cần thiết kế rõ ràng: validate trước khi ghi, dùng transaction, staging, thao tác bù (compensation), hoặc mô hình xử lý lỗi từng đơn vị dữ liệu. Không nên cố xử lý bằng một `catch (Exception)` chỉ để che dấu thất bại.

Ví dụ một biểu thức phức tạp thường làm khó phân tích:

```java
save(updateCounter() + parseInput() + recordAudit());
```

Đoạn trên là **mã minh họa, không độc lập** vì chưa định nghĩa phương thức. Khi `parseInput()` lỗi, `updateCounter()` đã có thể cập nhật trạng thái, còn `recordAudit()` và `save()` chưa chạy. Nếu nghiệp vụ cho phép, có thể đổi thiết kế để kiểm tra input trước khi tạo side effect:

```java
int parsed = parseInput();
int counted = updateCounter();
int audit = recordAudit();
save(parsed + counted + audit);
```

Đây là quyết định **đổi thứ tự xử lý có chủ đích**; không tự thay đổi thứ tự một API thực tế nếu chưa kiểm tra hợp đồng và yêu cầu nghiệp vụ.

## 9. Bài tập tự dự đoán output

Đoạn dưới đây đặt trong thân một phương thức Java hợp lệ. Nó minh họa chính xác việc một câu lệnh gán bị gián đoạn nhưng phép tăng tiền tố đã hoàn thành.

```java
int x = 4;
try {
    x = ++x + Integer.parseInt("oops");
    System.out.println("done");
} catch (NumberFormatException ex) {
    System.out.println("caught");
}
System.out.println("x=" + x);
```

Phân tích: `++x` đổi `x` thành 5, sau đó `Integer.parseInt("oops")` ném `NumberFormatException`. Phép cộng/gán ngoài cùng không có giá trị hoàn tất, nên không ghi đè `x` bằng kết quả tổng. Dòng `done` không chạy; catch in thông báo rồi dòng sau in trạng thái hiện tại.

Stdout:

```text
caught
x=5
```

**Câu hỏi kiểm tra:**

1. Nếu `bad()` là đối số thứ hai trong lời gọi ba đối số và nó ném lỗi, đối số nào có thể đã chạy, đối số nào chưa chạy và thân hàm đích có được gọi không?
2. Tại sao `++effects[0]` đã có hiệu lực trong khi phép gán `balance = ...` không hoàn tất?
3. Nếu không có catch trong phương thức hiện tại, Java có chạy câu lệnh ngay sau nơi ném rồi mới thoát method không?
4. `finally` chạy khi có exception có đồng nghĩa toàn bộ biểu thức ban đầu đã được tính tiếp không?
5. `false && mayThrow()` khác với lỗi exception giữa phép cộng thế nào?
6. Vì sao không nên giả định rằng `getMessage()` của ngoại lệ runtime luôn giống nhau trên mọi JDK?

**Gợi ý:** (1) Các đối số bên trái hoàn thành trước đó có thể đã chạy; đối số bên phải và thân hàm chưa chạy. (2) Side effect của biểu thức con hoàn thành trước lỗi vẫn tồn tại. (3) Không, exception lan ra caller. (4) Không, đó là cleanup. (5) Short-circuit là hoàn thành bình thường theo lựa chọn nhánh. (6) Message có thể phụ thuộc triển khai/ngữ cảnh; nên test kiểu lỗi và hành vi.

## 10. Các lỗi hiểu sai cần tránh

- “Hễ exception thì toàn biểu thức chưa làm gì.” **Sai:** những bước đã thực hiện và side effect có thể còn lại.
- “Catch xong, Java quay về chạy tiếp toán hạng kế tiếp.” **Sai:** điều khiển chuyển sang handler và sau handler.
- “Tham số sau tham số lỗi vẫn chạy vì cùng nằm trong dấu ngoặc hàm.” **Sai** theo thứ tự đánh giá đối số.
- “Phép gán không hoàn tất nên mọi biến bên trong vế phải giữ nguyên.” **Sai:** side effect có thể đã xảy ra.
- “Nhánh bên phải `&&` không chạy nghĩa là có exception.” **Sai:** short-circuit thông thường không tạo exception.
- “Dùng `finally` sẽ khiến phép toán lỗi chạy tiếp.” **Sai:** đó là cleanup khi rời phạm vi.
- “Không bắt exception trong loop thì loop tự sang bản ghi sau.” **Sai:** exception có thể thoát hẳn loop.
- “Exception chỉ áp dụng cho `RuntimeException`.” **Sai:** checked exception, unchecked exception và `Error` đều có thể làm dừng đường thực thi.
- “Dùng `catch (Throwable)` là bảo đảm an toàn.” **Sai:** nó bao gồm cả các `Error` nghiêm trọng mà ứng dụng thường không có khả năng phục hồi.
- “Ngoại lệ tự rollback database/file.” **Sai:** rollback phụ thuộc cơ chế riêng.
- “Java ngẫu nhiên chọn thứ tự đánh giá.” **Sai:** JLS quy định nhiều thứ tự cần tuân thủ. Vẫn nên giảm biểu thức nhiều side effect để dễ bảo trì.

## 11. Tài liệu chuẩn

- [JLS 17 §15.6 – Normal and Abrupt Completion of Evaluation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.6): quy tắc khi biểu thức con ném ngoại lệ.
- [JLS 17 §15.7 – Evaluation Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7): toán hạng, đối số và thứ tự đánh giá.
- [JLS 17 §14.1 – Normal and Abrupt Completion of Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.1): các lý do kết thúc bất thường của câu lệnh.
- [JLS 17 §14.20 – The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): catch, finally và try-with-resources.
- [JLS 17 §15.12.4 – Runtime Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): cách đánh giá biểu thức đích và đối số của lời gọi.

**Kết quả học tập:** Khi nhìn một câu lệnh Java có ngoại lệ, bạn phải chỉ ra được *bước gây lỗi*, *những bước đã chạy*, *những bước bị bỏ qua*, *side effect còn lại*, *đường cleanup* và *điểm tiếp tục sau handler*.