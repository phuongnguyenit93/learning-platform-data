# Giới hạn khai báo trùng tên với biến bao ngoài trong lambda Java

## 1. Bài toán và quy tắc cốt lõi

Lambda giúp truyền hành vi như một giá trị của **giao diện hàm** (*functional interface*), ví dụ `IntUnaryOperator operation = x -> x + 1;`. Khi viết lambda trong một phương thức, chương trình thường đã có tham số hoặc biến cục bộ ở phạm vi bao ngoài. Câu hỏi quan trọng là: **lambda có được dùng lại những tên đó để khai báo tham số hoặc biến cục bộ mới không?**

Trong Java, **không được khai báo tham số hoặc biến cục bộ trong lambda trùng tên với biến cục bộ, tham số phương thức, tham số `catch` hay tham số lambda khác vẫn đang nằm trong phạm vi bao ngoài tại chỗ khai báo**. Đây là lỗi biên dịch do hai khai báo xung đột tên; không phải lỗi chỉ xuất hiện khi chạy.

Ví dụ cố ý **không biên dịch**:

```text
void demo() {
    int number = 10;
    IntUnaryOperator operation = number -> number + 1;
    // Sai: tham số lambda 'number' trùng biến cục bộ ở ngoài.
}
```

Ngược lại, lambda được phép **đọc** biến cục bộ bên ngoài nếu đáp ứng điều kiện `final` hoặc *effectively final*, và tham số lambda có thể **trùng tên với trường (field) của lớp**. Cần phân biệt chính xác các trường hợp này.

Sau bài học, bạn có thể xác định tên nào được dùng, tên nào bị cấm, sửa xung đột tên, giải thích sự khác biệt giữa lambda và lớp ẩn danh, đồng thời hiểu quan hệ với việc bắt giữ biến (*variable capture*).

## 2. Phân biệt các khái niệm về phạm vi

**Phạm vi (scope)** là vùng chương trình mà một tên khai báo có thể được sử dụng để tham chiếu đến biến hoặc tham số ấy. Một phương thức, khối lệnh `{ ... }`, phần `catch` hoặc biểu thức lambda đều có những quy định về phạm vi riêng.

**Biến bao ngoài (enclosing variable)** ở bài này chủ yếu là biến cục bộ hoặc tham số đang tồn tại trong phạm vi chứa biểu thức lambda. Ví dụ `int offset = 3;` khai báo trước lambda trong cùng phương thức là biến cục bộ bao ngoài.

**Che khuất tên (shadowing)** là việc khai báo một tên mới trùng một tên đã có, khiến tên mới được ưu tiên ở vị trí tương ứng. Java cho phép một số kiểu che khuất, ví dụ tham số lambda che khuất **trường của lớp**; nhưng không cho phép tham số hoặc biến cục bộ lambda khai báo trùng **biến cục bộ đang trong phạm vi bao ngoài**.

**Bắt giữ biến (capture)** xảy ra khi lambda sử dụng biến cục bộ hoặc tham số ngoài phần khai báo của nó, ví dụ `n -> n + offset` đọc `offset`. Khi bắt giữ biến cục bộ, biến đó phải `final` hoặc *effectively final* (không được gán lại sau khi khởi tạo).

Bốn khái niệm có quan hệ nhưng không đồng nhất: **xung đột tên là vấn đề khai báo; bắt giữ là việc tham chiếu biến đã khai báo; thay đổi giá trị là vấn đề ràng buộc `final`**.

## 3. Quy tắc dành cho các loại tên

| Loại tên hiện có ở phạm vi bao ngoài | Khai báo trùng làm tham số/biến cục bộ lambda? | Giải thích |
| --- | --- | --- |
| Biến cục bộ của phương thức | **Không**, khi biến vẫn trong phạm vi | Xung đột khai báo biến |
| Tham số của phương thức bao ngoài | **Không** | Tham số là tên đang trong phạm vi |
| Tham số của `catch` bao ngoài | **Không**, khi lambda nằm trong khối `catch` | Trùng tên tham số ngoại lệ |
| Tham số của lambda bao ngoài | **Không** trong lambda lồng bên trong | Tên tham số trước còn trong phạm vi |
| Biến cục bộ được khai báo ở khối `{ ... }` đã kết thúc | **Có thể** dùng lại sau khi rời phạm vi đó | Tên cũ không còn trong phạm vi |
| Tham số `n` của một lambda độc lập khác | **Có thể** dùng lại | Hai lambda không lồng nhau có phạm vi tham số riêng |
| Trường `private int amount` của lớp | **Có thể** dùng `amount` làm tham số | Tham số che khuất trường; dùng `this.amount` để đọc trường |
| Trường `static` của lớp | **Có thể** dùng cùng tên, với truy cập trường qua tên lớp | Không có xung đột biến cục bộ; nên phân biệt rõ tên trong mã |

Điểm mấu chốt: **không cấm tất cả tên trùng trong Java**. Cần xem tên trùng là *loại khai báo nào*, phạm vi của nó còn hiệu lực không và hai lambda có lồng nhau hay không.

## 4. Lambda không tạo vùng đặt lại tên biến bao ngoài

Ví dụ dưới đây có biến `value` trong phương thức:

```text
import java.util.function.IntUnaryOperator;

class DuplicateParam {
    void test() {
        int value = 10;
        IntUnaryOperator op = value -> value + 1;
    }
}
```

Đây là **mã cố ý không biên dịch**. `value` ở bên trái `->` là khai báo **tham số mới**, nhưng `value` bên ngoài vẫn còn trong phạm vi của phương thức `test()`. Trình biên dịch báo biến đã được khai báo trong phương thức.

Sửa bằng cách đổi tên tham số:

```java
int value = 10;
IntUnaryOperator op = input -> input + value;
```

Hai lệnh trên minh họa cho thân một phương thức có `import java.util.function.IntUnaryOperator;`. Ở đây `input` là tham số của lambda và `value` là biến bao ngoài được **bắt giữ**. Nếu muốn cộng hằng số 10, có thể giữ `value` không bị gán lại; đừng đặt tên tham số cùng tên biến đó.

Một lỗi tương tự xảy ra khi khai báo **biến cục bộ trong thân khối lambda**:

```text
import java.util.function.IntUnaryOperator;

class DuplicateLocal {
    void test() {
        int total = 10;
        IntUnaryOperator op = x -> {
            int total = x + 1;
            return total;
        };
    }
}
```

Mã trên cố ý không biên dịch vì khai báo `int total` bên trong lambda trùng biến `total` ở phương thức bao ngoài. Sửa thành `int result = x + 1;` rồi `return result;`, hoặc dùng trực tiếp `x -> x + 1`.

Quy tắc tương tự áp dụng nếu phạm vi bao ngoài chứa **tham số phương thức**, chẳng hạn `void evaluate(int input) { IntUnaryOperator op = input -> input + 1; }` — tham số lambda `input` bị trùng. Hãy đổi thành `n -> n + input` nếu muốn bắt giữ `input`.

## 5. Một chương trình minh họa các trường hợp hợp lệ

Tạo tệp `LambdaNameScopeDemo.java`:

```java
import java.util.function.Function;
import java.util.function.IntUnaryOperator;

public class LambdaNameScopeDemo {
    private final int amount = 40;

    void demonstrate() {
        int offset = 3;
        IntUnaryOperator plusOffset = number -> number + offset;
        System.out.println(plusOffset.applyAsInt(4));

        IntUnaryOperator first = n -> n + 1;
        IntUnaryOperator second = n -> n * 2;
        System.out.println(first.applyAsInt(4));
        System.out.println(second.applyAsInt(4));

        IntUnaryOperator fieldExample = amount -> amount + this.amount;
        System.out.println(fieldExample.applyAsInt(2));

        Function<Integer, IntUnaryOperator> makeAdder =
                increment -> number -> number + increment;
        System.out.println(makeAdder.apply(5).applyAsInt(7));

        {
            int blockValue = 2;
            IntUnaryOperator useBlock = n -> n + blockValue;
            System.out.println(useBlock.applyAsInt(9));
        }
        IntUnaryOperator afterBlock = blockValue -> blockValue + 1;
        System.out.println(afterBlock.applyAsInt(3));
    }

    public static void main(String[] args) {
        new LambdaNameScopeDemo().demonstrate();
    }
}
```

Biên dịch và chạy với Java 17 hoặc mới hơn:

```bash
javac --release 17 -encoding UTF-8 LambdaNameScopeDemo.java
java LambdaNameScopeDemo
```

Kết quả chính xác:

```text
7
5
8
42
12
11
4
```

Phân tích lần lượt:

1. `offset` là biến cục bộ bao ngoài, còn `number` là tham số lambda. Tên không trùng nên hợp lệ; lambda đọc `offset = 3` và `4 + 3 = 7`. `offset` được bắt giữ và không bị gán lại.
2. `first` và `second` đều dùng tên tham số `n`. Chúng là **hai lambda độc lập**, không lồng nhau, nên có thể tái sử dụng tên. `first(4)` cho `5`; `second(4)` cho `8`.
3. Lớp có trường `amount = 40`. Tham số `amount` của lambda được phép che khuất trường này. `amount` ở bên trái phép cộng là tham số nhận `2`; `this.amount` truy cập trường của đối tượng đang thực thi `demonstrate()`, nên ra `42`.
4. `makeAdder` có hai lambda **lồng nhau** nhưng tên là `increment` và `number`, không trùng. Lambda trong dùng `increment` của lambda ngoài: `makeAdder.apply(5).applyAsInt(7)` cho `12`.
5. Biến `blockValue = 2` chỉ tồn tại trong khối `{ ... }`. `useBlock` đọc nó hợp lệ và cho `9 + 2 = 11`. Khi đã ra khỏi khối, tên `blockValue` không còn trong phạm vi; lambda `afterBlock` được phép khai báo **tham số mới cùng tên** và cho `3 + 1 = 4`.

Đây là ví dụ quan trọng về khác biệt giữa **cùng tên ở hai phạm vi không chồng lấn** và **khai báo trùng khi phạm vi bao ngoài vẫn đang hoạt động**.

## 6. Lambda lồng nhau: không khai báo lại tham số ngoài

Xét một hàm trả về hàm khác:

```java
Function<Integer, IntUnaryOperator> makeAdder =
        increment -> number -> number + increment;
```

Câu lệnh trong mục 5 hợp lệ vì tham số lambda ngoài là `increment`, còn lambda trong là `number`. Nếu đổi cả hai thành `x`:

```text
Function<Integer, IntUnaryOperator> bad =
        x -> x -> x + 1;
```

Đây là **đoạn cố ý không biên dịch**. Lambda trong nằm trong phần thân lambda ngoài, nên tham số `x` ngoài vẫn còn trong phạm vi. Không thể khai báo tham số `x` mới ở lambda trong. Ngoài việc chọn hai tên khác nhau, cần suy nghĩ tên biểu thị vai trò: `amount -> number -> amount + number` dễ hiểu hơn.

Ngược lại, hai lambda xuất hiện ở hai lệnh độc lập có thể dùng lại `x`:

```java
IntUnaryOperator plusOne = x -> x + 1;
IntUnaryOperator doubleIt = x -> x * 2;
```

Đây là hai lệnh đặt trong thân phương thức có import `IntUnaryOperator`, không cần đổi `x` thành `y` ở lambda thứ hai. Phạm vi tham số của lambda thứ nhất không kéo dài sang lambda thứ hai.

## 7. Trường của lớp khác biến cục bộ

Với lớp sau:

```java
class Formatter {
    private String prefix = "Hello ";

    java.util.function.Function<String, String> create() {
        return prefix -> prefix + this.prefix;
    }
}
```

Đây là khai báo lớp hợp lệ trong Java 17. `prefix` ở bên trái `->` là **tham số của lambda**. `this.prefix` là trường của đối tượng `Formatter`. Hai tên giống nhau nhưng ở hai loại khai báo khác nhau nên hợp lệ. Việc sử dụng cùng tên có thể gây khó đọc; trên thực tế nên viết `name -> name + this.prefix` hoặc đặt tên phản ánh nghiệp vụ.

Đối với trường `static`, cách truy cập rõ ràng nhất là `TenLop.tenTruong` để phân biệt với tham số trùng tên. `this` trong lambda giữ nghĩa của ngữ cảnh bao ngoài: trong phương thức thực thể, `this` là đối tượng chứa biểu thức lambda, **không phải một đối tượng riêng mới của phần thân lambda**. Trong phương thức `static` không có `this`.

Khả năng sử dụng `this.amount` không chứng minh lambda có phạm vi lớp riêng. Java cho phép kiểu **che khuất trường** này, nhưng vẫn cấm khai báo trùng tên với biến cục bộ bao ngoài đang trong phạm vi.

## 8. Đối chiếu với lớp ẩn danh (anonymous class)

Một lớp ẩn danh tạo ra phần thân lớp và phương thức riêng. Vì vậy tham số phương thức của lớp ẩn danh có thể dùng tên giống biến cục bộ phương thức chứa lớp đó, trong khi tham số lambda trực tiếp cùng tên sẽ bị cấm.

Chương trình độc lập sau minh họa:

```java
import java.util.function.IntUnaryOperator;

public class AnonymousScopeContrast {
    void demonstrate() {
        int number = 10;
        IntUnaryOperator operation = new IntUnaryOperator() {
            @Override
            public int applyAsInt(int number) {
                return number + 1;
            }
        };
        System.out.println(operation.applyAsInt(5));
        System.out.println(number);
    }

    public static void main(String[] args) {
        new AnonymousScopeContrast().demonstrate();
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 AnonymousScopeContrast.java
java AnonymousScopeContrast
```

Kết quả:

```text
6
10
```

Trong `applyAsInt(int number)`, tham số thuộc **phương thức của lớp ẩn danh** và được phép dùng tên `number`. Còn biến cục bộ `number = 10` của `demonstrate()` không bị thay đổi. Nếu viết `IntUnaryOperator operation = number -> number + 1;` ngay tại đó, Java báo lỗi trùng khai báo tên.

Ngoài khác biệt đặt tên, `this` bên trong phương thức của lớp ẩn danh trỏ tới **đối tượng lớp ẩn danh**, còn `this` trong lambda (khi hợp lệ) trỏ tới **đối tượng ở ngữ cảnh bao ngoài**. Chỉ nên chọn lớp ẩn danh khi thật sự cần cấu trúc đối tượng/phương thức đó; nếu dùng lambda, cách sửa đơn giản nhất thường là chọn tên tham số khác.

## 9. Những trường hợp phạm vi khác cần tránh nhầm

### 9.1. Tham số `catch` vẫn đang trong phạm vi

```text
try {
    throw new IllegalStateException();
} catch (IllegalStateException error) {
    IntUnaryOperator op = error -> error + 1;
}
```

Đây là **đoạn cố ý không biên dịch** (giả sử đã import `IntUnaryOperator`). Trong khối `catch`, tên `error` là tham số ngoại lệ đang trong phạm vi. Lambda không được khai báo tham số mới cùng tên đó; chọn `n -> n + 1` để tránh xung đột.

### 9.2. Khối lệnh giới hạn tuổi thọ của tên

```java
{
    int temp = 5;
    System.out.println(temp);
}
IntUnaryOperator op = temp -> temp + 1;
```

Đoạn trên là các lệnh trong thân phương thức đã import `IntUnaryOperator`. Khi khối thứ nhất kết thúc, `temp` không còn trong phạm vi, nên lambda được phép khai báo tham số `temp` mới. Điều này khác trường hợp khai báo `int temp = 5;` trong chính khối bao ngoài của lambda.

### 9.3. Quy tắc tên vẫn áp dụng với kiểu tường minh hoặc `var`

```text
int index = 10;
IntUnaryOperator a = (int index) -> index + 1; // Sai
IntUnaryOperator b = (var index) -> index + 1; // Sai
```

Đây là mã cố ý không biên dịch. Ghi kiểu tường minh hoặc dùng `var` không làm thay đổi quy tắc trùng tên. `index` đã tồn tại trong phạm vi phương thức, nên cả hai khai báo tham số lambda đều xung đột.

## 10. Liên hệ với bắt giữ biến và effectively final

Khác biệt giữa **khai báo trùng tên** và **đọc biến bao ngoài** rất quan trọng.

```java
int base = 10;
IntUnaryOperator addBase = n -> n + base;
```

Đây là hai lệnh hợp lệ trong thân phương thức đã import `IntUnaryOperator`. `base` là biến cục bộ được lambda **bắt giữ**, còn `n` là tham số riêng. Vì `base` không bị gán lại, nó là *effectively final*.

Nếu bổ sung `base = 20;` trong cùng phương thức, Java không cho lambda bắt giữ `base` nữa, dù đã đặt tên `n` hoàn toàn khác. Đây là **lỗi về điều kiện bắt giữ biến**, khác với **lỗi khai báo trùng tên**.

Ngược lại, `IntUnaryOperator wrong = base -> base + 1;` bị cấm **ngay ở tên tham số** nếu biến cục bộ `base` bao ngoài vẫn còn trong phạm vi, kể cả khi lambda không đọc biến cục bộ ấy.

Ràng buộc *effectively final* áp dụng với biến cục bộ hoặc tham số được bắt giữ; nó không có nghĩa mọi đối tượng được tham chiếu trở nên bất biến. Một lambda có thể dùng trường trạng thái của lớp; khi nhiều luồng cùng truy cập trường có thể thay đổi, cần cân nhắc an toàn luồng riêng.

## 11. Sửa lỗi đặt tên một cách có chủ đích

Khi trình biên dịch báo `variable ... is already defined in method ...`, hãy kiểm tra theo trình tự:

1. Xác định **dòng khai báo trùng**: tên phía trái `->`, một biến trong thân `{ ... }`, hay tham số của lambda lồng.
2. Tìm biến cục bộ/tham số cùng tên tại phạm vi bao ngoài đang còn hiệu lực. Đừng chỉ tìm trường của lớp; trùng tên trường có thể hợp lệ.
3. Nếu đang muốn **dùng giá trị bao ngoài**, giữ tên biến cũ để tham chiếu nhưng **đổi tên tham số lambda** cho đúng vai trò, ví dụ `input -> input + offset`.
4. Nếu đang muốn **một biến mới**, đặt tên khác trong thân lambda, ví dụ `result` thay vì dùng lại `total`.
5. Nếu hai lambda **không lồng nhau**, có thể tái sử dụng tên ngắn `x` khi không có biến cục bộ cùng tên ở phạm vi bao ngoài.
6. Chỉ tách khối `{ ... }` khi việc giới hạn phạm vi phù hợp với cấu trúc chương trình; không dùng lớp ẩn danh chỉ để né quy tắc đặt tên của lambda.

Ví dụ trước và sau:

```text
// Sai nếu 'limit' là biến cục bộ bao ngoài:
int limit = 5;
Predicate<Integer> invalid = limit -> limit > 0;

// Hợp lệ: đặt tên tham số theo vai trò và đọc biến bao ngoài:
int limit = 5;
Predicate<Integer> valid = value -> value > limit;
```

Hai cặp lệnh ở trên là các ví dụ độc lập để so sánh, không ghép nguyên khối trong cùng một phương thức vì sẽ khai báo `limit` hai lần. Với biến cục bộ `limit` không bị gán lại, cách thứ hai bắt giữ biến hợp lệ.

## 12. Bài tập tự kiểm tra

**Bài 1.** Trong phương thức đã có `int offset = 5;`, lambda `offset -> offset + 1` có hợp lệ khi gán vào `IntUnaryOperator` không?

Đáp án: **Không**. Tham số lambda trùng biến cục bộ `offset` đang trong phạm vi. Nếu muốn cộng thêm 5, viết `n -> n + offset`.

**Bài 2.** Hai biến `IntUnaryOperator a = x -> x + 1;` và `IntUnaryOperator b = x -> x * 2;` được khai báo trong cùng phương thức, không có biến `x` bao ngoài. Có lỗi trùng tên không?

Đáp án: **Không**. Đây là hai lambda độc lập; tên tham số của lambda thứ nhất không tồn tại trong phạm vi lambda thứ hai.

**Bài 3.** Một lớp có `private int score = 10;`. Lambda `score -> score + this.score` trong phương thức thực thể hợp lệ không? Khi tham số nhận `3`, kết quả là bao nhiêu?

Đáp án: **Có**, vì tên `score` trùng **trường**, không trùng biến cục bộ. Kết quả là `3 + 10 = 13`. Nên đặt tên tham số khác nếu cần mã dễ hiểu hơn.

**Bài 4.** Tại sao `amount -> amount -> amount + 1` không hợp lệ khi kiểu đích là `Function<Integer, IntUnaryOperator>`?

Đáp án: lambda trong khai báo tham số `amount` trùng tham số `amount` của lambda ngoài đang trong phạm vi. Có thể đổi thành `amount -> number -> amount + number`.

**Bài 5.** Tách `{ int temp = 2; ... }` thành một khối độc lập đã kết thúc; sau khối có thể khai báo tham số lambda tên `temp` không?

Đáp án: **Có**, nếu không còn khai báo `temp` khác trong phạm vi bao ngoài tại vị trí lambda. Phạm vi tên cũ đã kết thúc.

## 13. Điều cần ghi nhớ

- Tham số và biến cục bộ trong lambda **không được trùng tên với biến cục bộ/tham số còn trong phạm vi bao ngoài**; áp dụng cả phương thức, khối `catch` và lambda lồng.
- Trùng tên với **trường của lớp** có thể hợp lệ: tham số lambda che khuất trường, còn `this.fieldName` truy cập trường trong ngữ cảnh thực thể.
- **Hai lambda độc lập** có thể cùng dùng tên tham số; **lambda lồng nhau** không được khai báo lại tên tham số ngoài.
- Khi khối cục bộ kết thúc, tên của biến cục bộ trong khối không còn trong phạm vi, nên có thể dùng lại tên ở nơi thích hợp.
- **Bắt giữ biến** là tham chiếu biến bao ngoài, không phải khai báo biến mới; biến cục bộ được bắt giữ phải `final` hoặc *effectively final*.
- Lớp ẩn danh có phạm vi phương thức riêng và quy tắc `this` khác lambda. Đổi tên tham số thường là cách khắc phục đơn giản và rõ ràng nhất.

Tham khảo đặc tả Java: [JLS §15.27.1 — Lambda Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.1), [JLS §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3), và [JLS §15.27.2 — Lambda Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.2).