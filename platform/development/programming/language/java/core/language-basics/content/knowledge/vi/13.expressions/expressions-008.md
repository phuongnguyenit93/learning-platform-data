# Kết thúc bình thường hoặc đột ngột do ngoại lệ — Java 17+

Khi Java **đánh giá một biểu thức** (*expression evaluation*), việc đánh giá có thể:

- **Kết thúc bình thường** (*completes normally*): biểu thức được đánh giá xong; nếu biểu thức có giá trị thì giá trị đó sẵn sàng để dùng trong biểu thức bao ngoài, phép gán, đối số hoặc câu lệnh.
- **Kết thúc đột ngột** (*completes abruptly*): một phần của quá trình đánh giá thất bại, ví dụ ném ngoại lệ (*exception*). Biểu thức **không hoàn tất theo đường bình thường**; các bước phụ thuộc phía sau bị bỏ qua và luồng điều khiển chuyển tới cơ chế xử lý ngoại lệ phù hợp.

~~~java
int sum = 2 + 3;    // Binh thuong: sum nhan 5.

// int bad = 10 / 0; // Khi chay: ArithmeticException.
// Khong co ket qua int binh thuong de gan cho bad.
~~~

Trong Java, một lời gọi trả `void` cũng có thể **kết thúc bình thường** dù không sinh ra giá trị để cộng/gán. Vì vậy không đồng nhất “bình thường” với “luôn trả một đối tượng hoặc một con số”.

**Trọng tâm:** khi một biểu thức con ném ngoại lệ, việc đánh giá biểu thức lớn bị dừng; những tác dụng phụ **đã diễn ra trước lỗi** không tự động được hoàn tác.

## 1. Hai kết quả của đánh giá biểu thức

| Tình huống | Hoàn tất thế nào? | Hệ quả |
| --- | --- | --- |
| `4 + 5` | Bình thường | Có giá trị `int 9` |
| `"Java".length()` | Bình thường | Có giá trị `int 4` |
| `System.out.println("Hi")` | Bình thường nếu in thành công | Lời gọi `void` không cung cấp một giá trị có thể đem cộng |
| `10 / 0` với toán hạng `int` | Đột ngột | Ném `ArithmeticException` |
| `((String) null).length()` | Đột ngột | Ném `NullPointerException` |
| `array[99]` nếu mảng quá ngắn | Đột ngột | Ném `ArrayIndexOutOfBoundsException` |
| `Integer.parseInt("abc")` | Đột ngột | Ném `NumberFormatException` |
| `false && risky()` | Bình thường với `false` | `risky()` **không được gọi** |
| `true ? 1 : riskyInt()` | Bình thường với `1` | Nhánh không được chọn **không được đánh giá** |

Một ngoại lệ được **ném** tại một điểm sẽ tìm khối `catch` phù hợp ở ngăn xếp lời gọi. Nếu không có nơi xử lý, ngoại lệ có thể làm luồng đang chạy chấm dứt. Một `catch` xử lý thành công **không làm Java quay lại tính tiếp biểu thức bị ngắt**; chương trình tiếp tục từ vị trí hợp lệ **sau cấu trúc xử lý**.

## 2. Quy tắc lan truyền từ biểu thức con

Các toán hạng và đối số thông thường được đánh giá **từ trái sang phải**. Nếu một biểu thức con ném ngoại lệ:

1. Các biểu thức con **đã hoàn tất trước đó** vẫn đã được đánh giá; những thay đổi trạng thái trước lỗi vẫn còn, trừ khi ứng dụng có cơ chế hoàn tác riêng.
2. Các biểu thức con **phía sau chưa tới lượt** sẽ không được đánh giá trong cùng phép tính hoặc lời gọi đó.
3. Toàn bộ biểu thức bao ngoài **kết thúc đột ngột**, không trả giá trị bình thường cho phép gán hoặc lời gọi bên ngoài.
4. `catch` phù hợp có thể xử lý lỗi và cho phép chương trình tiếp tục ở một câu lệnh sau `try/catch`.

Ví dụ:

~~~java
int result = left() + fail() + right();
~~~

Nếu `left()` trả giá trị bình thường rồi `fail()` ném exception, `right()` **không chạy** và phép gán cho `result` không hoàn tất. Nếu `left()` đã ghi log hoặc tăng bộ đếm thì thay đổi đó vẫn tồn tại.

Sơ đồ luồng:

~~~text
Danh gia left() ----> Danh gia fail() ----> Danh gia right()
       |                    |
    thanh cong          nem exception
                            |
                            v
                  Bo qua right() va phep gan
                            |
                            v
                    Tim catch phu hop
~~~

Sơ đồ chỉ thể hiện một nhánh thất bại minh họa; nếu `fail()` thành công, việc đánh giá sẽ đi tiếp sang `right()`.

## 3. Demo Java 17+ chạy độc lập

Tạo file UTF-8 tên **`ExpressionCompletionDemo.java`**:

~~~java
public class ExpressionCompletionDemo {
    static int mark(String label, int value) {
        System.out.println("eval=" + label);
        return value;
    }

    static int fail(String label) {
        System.out.println("eval=" + label);
        throw new IllegalStateException("boom-" + label);
    }

    static int combine(int first, int second, int third) {
        System.out.println("combine=called");
        return first + second + third;
    }

    static boolean check(String label, boolean value) {
        System.out.println("eval=" + label);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("== normal ==");
        int normal = mark("left", 2) + mark("right", 3);
        System.out.println("normal=" + normal);

        System.out.println("== abrupt operand ==");
        try {
            int unused = mark("before", 1)
                    + fail("middle")
                    + mark("after", 9);
            System.out.println("unexpected=" + unused);
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        System.out.println("== abrupt argument ==");
        try {
            int unused = combine(
                    mark("arg-1", 10),
                    fail("arg-2"),
                    mark("arg-3", 30));
            System.out.println("unexpected=" + unused);
        } catch (IllegalStateException ex) {
            System.out.println("argumentCaught=" + ex.getMessage());
        }

        System.out.println("== arithmetic ==");
        try {
            int quotient = mark("numerator", 10)
                    / mark("denominator", 0);
            System.out.println("unexpected=" + quotient);
        } catch (ArithmeticException ex) {
            System.out.println("divisionError="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("== references ==");
        String text = null;
        try {
            int size = text.length();
            System.out.println("unexpected=" + size);
        } catch (NullPointerException ex) {
            System.out.println("nullError="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("== arrays ==");
        int[] values = {7, 8};
        try {
            int element = values[mark("bad-index", 3)];
            System.out.println("unexpected=" + element);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("arrayError="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("== skip evaluation ==");
        boolean andResult = false && check("skip-and", true);
        boolean orResult = true || check("skip-or", false);
        int selected = true ? mark("selected", 7)
                : fail("skip-branch");
        System.out.println("and=" + andResult);
        System.out.println("or=" + orResult);
        System.out.println("selected=" + selected);

        System.out.println("== prior side effect ==");
        int counter = 0;
        try {
            int unused = mark("counter-start", counter++)
                    + fail("counter-fail");
            System.out.println("unexpected=" + unused);
        } catch (IllegalStateException ex) {
            System.out.println("sideEffectCaught="
                    + ex.getMessage());
        }
        System.out.println("counterAfter=" + counter);

        System.out.println("== catch and finally ==");
        int recovered;
        try {
            recovered = mark("recover-left", 4)
                    + fail("recover-right");
        } catch (IllegalStateException ex) {
            recovered = 99;
            System.out.println("recoveredFrom=" + ex.getMessage());
        } finally {
            System.out.println("finally=cleanup");
        }
        System.out.println("recoveredValue=" + recovered);
        System.out.println("program=continued");
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) trong thư mục chứa file, dùng **JDK 17 trở lên**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ExpressionCompletionDemo.java
java ExpressionCompletionDemo
~~~

**Exact expected output** của lệnh `java ExpressionCompletionDemo` (không bao gồm đầu ra các lệnh `-version`):

~~~text
== normal ==
eval=left
eval=right
normal=5
== abrupt operand ==
eval=before
eval=middle
caught=boom-middle
== abrupt argument ==
eval=arg-1
eval=arg-2
argumentCaught=boom-arg-2
== arithmetic ==
eval=numerator
eval=denominator
divisionError=ArithmeticException
== references ==
nullError=NullPointerException
== arrays ==
eval=bad-index
arrayError=ArrayIndexOutOfBoundsException
== skip evaluation ==
eval=selected
and=false
or=true
selected=7
== prior side effect ==
eval=counter-start
eval=counter-fail
sideEffectCaught=boom-counter-fail
counterAfter=1
== catch and finally ==
eval=recover-left
eval=recover-right
recoveredFrom=boom-recover-right
finally=cleanup
recoveredValue=99
program=continued
~~~

Những dòng có tiền tố `unexpected=` **không xuất hiện** vì biểu thức tương ứng đã ném ngoại lệ trước khi hoàn tất bình thường.

## 4. Đọc kết quả của demo

### 4.1. Kết thúc bình thường

~~~java
int normal = mark("left", 2) + mark("right", 3);
~~~

`mark("left", 2)` và `mark("right", 3)` chạy theo thứ tự trái → phải, cùng trả `int` bình thường. Phép cộng nhận hai giá trị 2 và 3, hoàn tất với 5, nên phép gán cho `normal` thành công.

### 4.2. Biểu thức con ném exception: phần sau không được chạy

~~~java
mark("before", 1) + fail("middle") + mark("after", 9)
~~~

`mark("before", 1)` đã chạy. `fail("middle")` ghi dấu rồi ném `IllegalStateException`. Vì vậy:

- `mark("after", 9)` **không được gọi**.
- Phép cộng lớn **không có giá trị bình thường**.
- `catch (IllegalStateException ex)` nhận exception và in `boom-middle`.

Biểu thức trong khối `try` không được tiếp tục tại chỗ sau khi exception đã xử lý.

### 4.3. Đối số thất bại: phương thức đích chưa được gọi

~~~java
combine(mark("arg-1", 10), fail("arg-2"), mark("arg-3", 30))
~~~

Đối số đầu tiên chạy, đối số thứ hai ném exception. Đối số thứ ba **không được đánh giá**, và bản thân phương thức `combine` **không được gọi**; vì vậy sẽ không có dòng `combine=called`.

Việc phương thức nhận ba tham số không có nghĩa Java đánh giá đồng thời hoặc đánh giá tất cả bất chấp lỗi.

### 4.4. Ngoại lệ do phép toán

`int` chia cho số nguyên 0 ném `ArithmeticException`. Hai toán hạng trong:

~~~java
mark("numerator", 10) / mark("denominator", 0)
~~~

đều được đánh giá trước khi phép chia phát hiện mẫu số bằng 0. Do đó có cả hai dòng `eval=...`, nhưng không có kết quả `quotient`.

**Lưu ý khác biệt:** `double` chia cho `0.0` tuân theo quy tắc số thực, có thể tạo `Infinity` hoặc `NaN` thay vì `ArithmeticException`. Không áp dụng máy móc quy tắc chia cho 0 của số nguyên cho mọi kiểu số.

### 4.5. Null và truy cập mảng

Gọi `text.length()` khi `text == null` ném `NullPointerException`. Trong `values[mark("bad-index", 3)]`, chỉ số 3 được đánh giá xong rồi thao tác truy cập mảng ném `ArrayIndexOutOfBoundsException` vì mảng chỉ có hai phần tử, chỉ số hợp lệ là 0 và 1.

Tên lớp của ngoại lệ trong log giúp phân biệt **loại thất bại**, nhưng không phải thông báo đầy đủ của ngoại lệ nào cũng giống nhau giữa các JDK. Demo chỉ in `getClass().getSimpleName()` để stdout ổn định.

### 4.6. Phần bị bỏ qua là ngữ nghĩa bình thường, không phải exception

~~~java
boolean a = false && check("skip-and", true);
boolean b = true || check("skip-or", false);
int c = true ? mark("selected", 7) : fail("skip-branch");
~~~

Ở hai biểu thức boolean, vế trái đã đủ xác định kết quả nên không gọi vế phải. Với toán tử ba ngôi, chỉ nhánh được chọn được đánh giá. Tất cả các biểu thức này **kết thúc bình thường**, mặc dù không đánh giá một phần cú pháp.

Vì vậy, **“biểu thức con không được chạy” không đồng nghĩa “có exception”**.

### 4.7. Tác dụng phụ trước lỗi không tự được hoàn tác

~~~java
int counter = 0;
int value = mark("counter-start", counter++)
        + fail("counter-fail");
~~~

`counter++` trả giá trị cũ và tăng `counter` lên 1 trước khi `fail(...)` ném exception. `value` không nhận được một kết quả gán bình thường, nhưng `counter` vẫn bằng 1 sau khi exception được bắt.

Đây không phải transaction. Muốn khôi phục trạng thái cần có thiết kế xử lý/hoàn tác phù hợp; `try/catch` tự thân không khôi phục mọi biến hay thao tác I/O trước đó.

### 4.8. `catch` và `finally` có vai trò khác nhau

Trong phần cuối demo, phép tính cho `recovered` kết thúc đột ngột, nhưng `catch` bắt exception và **chủ động gán giá trị dự phòng 99**. Khối `finally` in dòng dọn dẹp và sau đó chương trình tiếp tục.

- `catch` xử lý loại exception phù hợp; không tự sinh kết quả cho biểu thức đã hỏng.
- `finally` thông thường được thực thi khi rời `try/catch`, kể cả khi có exception, nhưng cũng có các trường hợp JVM/tiến trình không thể hoàn tất dọn dẹp (ví dụ bị kết thúc cưỡng bức).
- Nếu bản thân `finally` ném exception mới, exception đó có thể làm thay đổi cách khối hoàn tất. Tránh `return` hoặc ném exception mới trong `finally` trừ khi thực sự có chủ đích.

Trong mã ứng dụng, ưu tiên **try-with-resources** để đóng các tài nguyên hỗ trợ `AutoCloseable`, thay vì tự xử lý nhiều đường thoát phức tạp khi không cần.

## 5. Chỉ cần một phần lỗi, toàn bộ biểu thức bao ngoài bị ảnh hưởng

Ví dụ:

~~~java
int total = 5 + Integer.parseInt("abc") * 2;
~~~

Biểu thức có cách nhóm `5 + (parseInt("abc") * 2)`. Khi `parseInt` ném `NumberFormatException`:

1. Lời gọi không trả `int` bình thường.
2. Phép nhân không có đủ toán hạng để tính giá trị.
3. Phép cộng không nhận được giá trị cho toán hạng phải.
4. Phép gán cho `total` không hoàn tất.
5. Luồng xử lý chuyển theo quy tắc exception.

Nếu đây là bước xử lý dữ liệu người dùng, nên bắt `NumberFormatException` tại nơi có thể thông báo lỗi, yêu cầu nhập lại hoặc áp dụng một giá trị dự phòng **đã được đặc tả**, không lặng lẽ đoán thay.

## 6. Checked và unchecked exceptions

Sự khác biệt **checked / unchecked** liên quan tới yêu cầu **khai báo hoặc xử lý tại compile time**; không làm thay đổi nguyên tắc một biểu thức ném exception sẽ kết thúc đột ngột.

| Loại | Ví dụ | Compiler yêu cầu gì? |
| --- | --- | --- |
| Checked exception | `java.io.IOException` | Thông thường phải `catch` hoặc khai báo `throws` |
| Unchecked exception | `ArithmeticException`, `NullPointerException`, `NumberFormatException` | Không buộc phải `catch` hoặc khai báo `throws` |
| Lỗi nghiêm trọng thuộc `Error` | `OutOfMemoryError` | Cũng unchecked; thường không nên cố xử lý như lỗi nhập liệu |

Một exception có thể phát sinh sâu trong lời gọi phương thức rồi lan qua các biểu thức bao ngoài. Dù thuộc loại checked hay unchecked, nếu không được xử lý phù hợp thì đường thực thi bình thường không thể hoàn tất như dự kiến.

## 7. Phân biệt “kết thúc đột ngột” của biểu thức với câu lệnh

**Biểu thức** có thể kết thúc đột ngột do exception. **Câu lệnh** trong Java còn có các dạng hoàn tất đột ngột khác như `return`, `break` hoặc `continue` ở ngữ cảnh phù hợp.

~~~java
static int example(boolean stop) {
    if (stop) {
        return 1; // Phương thuc roi tai return.
    }
    return 2;
}
~~~

`return` ở ví dụ là **câu lệnh điều khiển**, không phải một toán tử số hoặc giá trị exception. Do đó khi bàn riêng về **biểu thức ném ngoại lệ**, tránh đánh đồng `return` với “exception được ném từ phép cộng”.

## 8. Cách viết mã dễ bảo trì hơn

Khi một biểu thức có nhiều lời gọi có thể thất bại, thường nên tách các bước để xác định rõ điểm lỗi và chính sách dự phòng:

~~~java
String text = "42";
int parsed;
try {
    parsed = Integer.parseInt(text);
} catch (NumberFormatException ex) {
    parsed = 0; // Chi dung neu bai toan cho phep fallback 0.
}
int total = parsed * 2;
~~~

Cách này làm rõ:

- Dữ liệu nào cần được parse.
- Loại exception nào có thể phát sinh và được bắt.
- Giá trị dự phòng có thực sự được cho phép hay không.
- Phép nhân chỉ bắt đầu **sau khi** bước parse đã được giải quyết.

Không cần bắt mọi `RuntimeException` hoặc `Exception` một cách vô điều kiện. Nên bắt **lỗi có thể xử lý hợp lý tại đúng ranh giới nghiệp vụ**, để các lỗi lập trình không bị che giấu.

## 9. Bài tập tự kiểm tra

1. **Bình thường:** `int n = 3 * (2 + 1);` kết thúc ra sao?  
   *Đáp án:* Bình thường, `n = 9`.
2. **Dừng sớm:** Trong `first() + fail() + last()`, nếu `fail()` ném exception thì `last()` chạy không?  
   *Đáp án:* Không; toàn bộ phép cộng kết thúc đột ngột.
3. **Đối số:** Nếu đối số thứ hai của lời gọi ba đối số ném exception, đối số thứ ba và thân phương thức có chạy không?  
   *Đáp án:* Không.
4. **Ngắn mạch:** `false && risky()` không gọi `risky()`; đây có phải kết thúc đột ngột không?  
   *Đáp án:* Không; toàn biểu thức kết thúc bình thường với `false`.
5. **Trạng thái:** `int x = 0;` rồi đánh giá `x++ + fail()`; bắt exception xong `x` bằng bao nhiêu?  
   *Đáp án:* `1` vì phép tăng đã diễn ra trước khi ném exception.
6. **Chia cho 0:** `int x = 10 / 0;` và `double y = 10.0 / 0.0;` khác nhau ra sao?  
   *Đáp án:* Phép thứ nhất ném `ArithmeticException`; phép thứ hai cho số thực dương vô cực theo quy tắc floating-point.
7. **`catch`:** Bắt được exception từ `Integer.parseInt("abc")` có nghĩa biểu thức ban đầu tự tính tiếp không?  
   *Đáp án:* Không; phải chọn luồng xử lý mới (ví dụ nhập lại hoặc gán fallback hợp lệ).

## Checklist

- [ ] Phân biệt kết thúc **bình thường** với kết thúc **đột ngột do exception**.
- [ ] Khi một biểu thức con thất bại, biểu thức bao ngoài không tạo kết quả bình thường.
- [ ] Những toán hạng/đối số chưa tới lượt sẽ **không được đánh giá** sau exception.
- [ ] Tác dụng phụ đã diễn ra **không tự động rollback**.
- [ ] Hiểu `&&`, `||`, `?:` có thể bỏ qua nhánh **mà vẫn hoàn tất bình thường**.
- [ ] Phân biệt trách nhiệm của `try`, `catch`, `finally`.
- [ ] Biết checked/unchecked là vấn đề hợp đồng compile-time, không thay đổi cơ chế lan truyền exception.
- [ ] Bắt và xử lý lỗi tại nơi ứng dụng có thể đưa ra quyết định chính xác.

**Kết luận:** Đánh giá một biểu thức Java có thể **hoàn thành với kết quả bình thường** hoặc **dừng đột ngột vì ngoại lệ**. Khi ngoại lệ phát sinh, các bước phía sau không tiếp tục, nhưng những tác dụng phụ trước đó vẫn còn; xử lý bằng `catch` là **một luồng điều khiển mới**, không phải “chạy tiếp” phép tính đã hỏng.
