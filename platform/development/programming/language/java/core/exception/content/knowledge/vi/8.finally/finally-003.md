# Finally khi `return`, `break` hoặc `continue` trong Java

Trong Java, khối `finally` gắn với một cấu trúc `try` được thiết kế để thực hiện các công việc cuối cùng khi luồng điều khiển **rời khỏi cấu trúc `try/catch`**. Điểm dễ nhầm là: việc rời khỏi `try` không chỉ xảy ra khi chạy hết các lệnh bình thường hoặc khi có ngoại lệ; nó còn xảy ra khi mã thực thi `return`, `break` hoặc `continue`.

**Quy tắc cốt lõi:** Nếu luồng đang ở trong một `try` có `finally`, khi `try` hoặc một `catch` liên quan bắt đầu hoàn tất vì `return`, `break`, `continue` hay ngoại lệ, Java thông thường thực thi `finally` **trước khi hoàn tất việc chuyển điều khiển ra ngoài**. Sau khi `finally` kết thúc bình thường, tác động đang chờ của `return`, `break`, `continue` hoặc ngoại lệ tiếp tục được thực hiện.

Cần hiểu cả ngoại lệ đặc biệt: nếu **chính `finally` hoàn tất bất thường** (ví dụ `throw` hoặc `return` trong `finally`), nó có thể thay thế nguyên nhân hoàn tất đang chờ. Vì vậy, `finally` không phải lúc nào cũng “chỉ dọn dẹp rồi giữ nguyên kết quả”.

Bài này thuộc Java Core – Exception, nhóm **Khối finally** và tập trung cụ thể vào ba lệnh chuyển điều khiển `return`, `break` và `continue`.

## 1. Ôn lại cấu trúc và phạm vi của `finally`

Cú pháp phổ biến:

~~~java
try {
    // Công việc chính.
} catch (SomeException e) {
    // Xử lý loại ngoại lệ tương ứng.
} finally {
    // Dọn dẹp hoặc hành động cuối cùng.
}
~~~

Có thể sử dụng `try/finally` **không có `catch`**:

~~~java
try {
    perform();
} finally {
    cleanup();
}
~~~

Hai đoạn là **cú pháp minh họa**, giả định các phương thức `perform()` và `cleanup()` đã tồn tại. Khối `finally` thuộc về cấu trúc `try` cụ thể đó, không phải một hàm toàn cục “luôn chạy khi cả ứng dụng thoát”.

Trong điều kiện Java chạy thông thường, `finally` được thực thi khi rời vùng `try/catch` theo các đường:

| Đường rời cấu trúc | `finally` thông thường chạy? | Điều diễn ra tiếp theo nếu `finally` hoàn tất bình thường |
| --- | --- | --- |
| Chạy hết khối `try` | Có | Chương trình tiếp tục sau `try/catch/finally` |
| Ngoại lệ được bắt và `catch` kết thúc bình thường | Có | Tiếp tục sau cấu trúc |
| Ngoại lệ chưa được bắt ở đây | Có | Tiếp tục lan truyền đến handler bên ngoài |
| `return` trong `try` hoặc `catch` | Có | Hoàn tất trả về từ phương thức |
| `break` rời vòng lặp/switch từ bên trong vùng `try` | Có | Chuyển tới vị trí sau cấu trúc bị `break` |
| `continue` tới vòng lặp kế tiếp từ bên trong vùng `try` | Có | Thực hiện bước tiếp theo theo loại vòng lặp |

**Cụm “thông thường” quan trọng:** không có cam kết `finally` sẽ chạy khi JVM bị kết thúc cưỡng bức, tiến trình bị hệ điều hành dừng, `Runtime.halt` chấm dứt VM, mất điện, hoặc luồng không bao giờ rời vùng `try`. Những giới hạn này được giải thích ở phần cuối.

## 2. `return` trong `try`: `finally` chạy trước khi caller nhận giá trị

Ví dụ:

~~~java
static int calculate() {
    try {
        System.out.println("try: prepare return");
        return 42;
    } finally {
        System.out.println("finally: cleanup");
    }
}
~~~

Nếu gọi `System.out.println("result=" + calculate());`, stdout là:

~~~text
try: prepare return
finally: cleanup
result=42
~~~

Thứ tự là:

1. Java bắt đầu đánh giá biểu thức sau `return` (`42` trong ví dụ).
2. Phương thức chuẩn bị hoàn tất bằng cách trả giá trị.
3. Trước khi thoát, Java chạy `finally`.
4. `finally` kết thúc bình thường.
5. Giá trị `42` mới được trả về cho caller; caller in `result=42`.

Không phải cứ gặp `return` là “bỏ qua mọi câu lệnh còn lại” theo nghĩa bỏ qua `finally`. Các câu lệnh **sau `return` trong cùng khối** không thể tiếp tục bình thường, nhưng `finally` đi kèm vẫn được xử lý theo luật ngôn ngữ.

### Biểu thức `return` được đánh giá trước `finally`

Xem ví dụ:

~~~java
static int snapshot() {
    int value = 3;
    try {
        return value;
    } finally {
        value = 9;
        System.out.println("finally value=" + value);
    }
}
~~~

Nếu gọi `System.out.println("snapshot=" + snapshot());`:

~~~text
finally value=9
snapshot=3
~~~

Lý do: biểu thức `return value;` được đánh giá **trước** khi `finally` chạy. Với kiểu nguyên thủy `int`, giá trị dự kiến trả đã là `3`. Việc gán lại biến cục bộ `value = 9` trong `finally` không khiến biểu thức `return` cũ được đánh giá lại, nên caller vẫn nhận `3`.

Điều này không có nghĩa Java ngăn `finally` thay đổi trạng thái mọi đối tượng liên quan: trường hợp trả tham chiếu sẽ được xét riêng.

## 3. Trả về đối tượng: `finally` có thể thay đổi trạng thái của đối tượng

Một tham chiếu cũng được đánh giá trước khi `finally` chạy. Nhưng nếu tham chiếu trỏ tới **đối tượng có thể thay đổi** và `finally` sửa chính đối tượng đó, caller có thể quan sát được thay đổi.

~~~java
static StringBuilder createText() {
    StringBuilder result = new StringBuilder("A");
    try {
        return result;
    } finally {
        result.append("B");
    }
}
~~~

Sau `System.out.println(createText());`, kết quả là:

~~~text
AB
~~~

Diễn giải:

- Biểu thức `return result;` đã chọn tham chiếu đến `StringBuilder`.
- `finally` gọi `append("B")` trên **cùng đối tượng**.
- Caller nhận tham chiếu đã chọn, nay trỏ đến đối tượng có nội dung `"AB"`.

Phân biệt **gán lại biến tham chiếu** và **thay đổi đối tượng**:

~~~java
static StringBuilder replaceLocalReference() {
    StringBuilder result = new StringBuilder("A");
    try {
        return result;
    } finally {
        result = new StringBuilder("B");
    }
}
~~~

Ở phương thức trên, caller vẫn nhận đối tượng `"A"` vì tham chiếu trả về đã được xác định trước `finally`; phép gán `result = ...` chỉ thay đổi biến cục bộ.

Đây là lý do không nên diễn giải cứng nhắc “`finally` không ảnh hưởng kết quả trả về”. Nó **không đánh giá lại giá trị trả của biểu thức ban đầu**, nhưng hoàn toàn có thể thay đổi trạng thái nhìn thấy từ ngoài, hoặc tự thay thế kết quả bằng một lệnh chuyển điều khiển khác.

## 4. `break` bên trong `try`: `finally` chạy trước khi rời vòng lặp

`break` không nhảy qua `finally`. Nếu một nhánh ở bên trong `try` thực hiện `break` để thoát khỏi vòng lặp bao quanh, Java thực thi `finally` liên quan trước khi chuyển điều khiển tới vị trí sau vòng lặp.

~~~java
static void breakExample() {
    for (int i = 0; i < 3; i++) {
        try {
            System.out.println("try " + i);
            if (i == 1) {
                break;
            }
        } finally {
            System.out.println("finally " + i);
        }
    }
    System.out.println("after loop");
}
~~~

Kết quả:

~~~text
try 0
finally 0
try 1
finally 1
after loop
~~~

Ở `i = 0`, thân `try` chạy xong bình thường; `finally` chạy rồi vòng lặp chuyển tới lần kế. Ở `i = 1`, `break` được thực hiện, nhưng `finally 1` **vẫn in trước** khi thoát khỏi vòng lặp. `i = 2` không xảy ra.

**Điểm cần nhớ:** `break` xác định đích nhảy theo cú pháp vòng lặp/switch; `finally` là phần cần thực thi trong quá trình rời các vùng `try` mà đường nhảy đó đi qua. `finally` không “hủy” `break` khi hoàn tất bình thường.

### `break` có nhãn

Trong vòng lặp lồng nhau, `break label;` có thể thoát nhiều tầng. Nếu đường thoát rời nhiều khối `try` có `finally`, chúng được thực thi **từ vùng trong ra vùng ngoài**.

~~~java
static void labeledBreak() {
    OUTER:
    for (int i = 0; i < 2; i++) {
        try {
            for (int j = 0; j < 2; j++) {
                try {
                    System.out.println("body " + i + "," + j);
                    break OUTER;
                } finally {
                    System.out.println("inner finally");
                }
            }
        } finally {
            System.out.println("outer finally");
        }
    }
    System.out.println("after labeled break");
}
~~~

Đây là phương thức Java hợp lệ. Khi gọi một lần, stdout là:

~~~text
body 0,0
inner finally
outer finally
after labeled break
~~~

Vùng `try` trong được rời trước, sau đó vùng `try` ngoài. Vì đích của `break OUTER` nằm ngoài cả hai, cả hai `finally` chạy trước khi chương trình in dòng sau vòng lặp.

## 5. `continue` bên trong `try`: `finally` chạy trước vòng lặp kế tiếp

`continue` bỏ phần thân vòng lặp còn lại của lượt hiện tại để chuyển sang tiến trình của lượt tiếp theo. Nếu `continue` xuất phát từ một `try` có `finally`, `finally` liên quan chạy **trước** bước cập nhật/kiểm tra để sang lượt mới.

~~~java
static void continueExample() {
    for (int i = 0; i < 3; i++) {
        try {
            System.out.println("try " + i);
            if (i < 2) {
                continue;
            }
            System.out.println("body " + i);
        } finally {
            System.out.println("finally " + i);
        }
    }
    System.out.println("after loop");
}
~~~

Kết quả:

~~~text
try 0
finally 0
try 1
finally 1
try 2
body 2
finally 2
after loop
~~~

Ở `i = 0` và `i = 1`, lệnh `continue` bỏ qua `System.out.println("body " + i)`, nhưng không bỏ qua `finally`. Ở `i = 2`, điều kiện `i < 2` sai, chương trình in `body 2` rồi vẫn chạy `finally 2`.

Với vòng `for (init; condition; update)`, sau khi `finally` hoàn tất bình thường trên đường `continue`, Java thực hiện bước **update** rồi kiểm tra điều kiện cho lần lặp kế. Với `while` hoặc `do/while`, bước tiếp theo tương ứng là đánh giá điều kiện vòng lặp theo quy tắc của loại vòng đó.

### `continue` có nhãn

`continue OUTER;` chuyển tới lần lặp tiếp theo của vòng lặp được gắn nhãn `OUTER`, không nhất thiết vòng gần nhất. Nếu đường nhảy rời một hoặc nhiều cấu trúc `try`, các `finally` liên quan vẫn được thực thi trước khi chuyển tới bước của vòng lặp đích.

~~~java
static void labeledContinue() {
    OUTER:
    for (int i = 0; i < 2; i++) {
        try {
            for (int j = 0; j < 2; j++) {
                try {
                    System.out.println("body " + i + "," + j);
                    continue OUTER;
                } finally {
                    System.out.println("inner finally " + i);
                }
            }
        } finally {
            System.out.println("outer finally " + i);
        }
    }
}
~~~

Kết quả khi gọi một lần:

~~~text
body 0,0
inner finally 0
outer finally 0
body 1,0
inner finally 1
outer finally 1
~~~

Không có lần `j = 1` vì `continue OUTER` bỏ phần còn lại của vòng trong và chuyển thẳng đến lượt tiếp theo của `OUTER`, **sau khi** các `finally` cần thiết đã chạy.

## 6. Chương trình Java 17+ hoàn chỉnh: cả `return`, `break` và `continue`

Tạo tệp **`FinallyControlFlowDemo.java`**:

~~~java
public class FinallyControlFlowDemo {
    public static void main(String[] args) {
        System.out.println("== RETURN ==");
        System.out.println("return result: " + returnNormally());
        System.out.println("snapshot result: " + returnSnapshot());

        System.out.println("== BREAK ==");
        breakDemo();

        System.out.println("== CONTINUE ==");
        continueDemo();

        System.out.println("== EXCEPTION ==");
        try {
            throwingDemo();
        } catch (IllegalStateException e) {
            System.out.println("caught: " + e.getMessage());
        }

        System.out.println("== OVERRIDE ==");
        System.out.println("overridden result: " + overrideReturn());
    }

    static int returnNormally() {
        try {
            System.out.println("try return");
            return 10;
        } finally {
            System.out.println("finally after return");
        }
    }

    static int returnSnapshot() {
        int n = 3;
        try {
            return n;
        } finally {
            n = 9;
            System.out.println("finally local=" + n);
        }
    }

    static void breakDemo() {
        for (int i = 0; i < 3; i++) {
            try {
                System.out.println("break try " + i);
                if (i == 1) {
                    break;
                }
            } finally {
                System.out.println("break finally " + i);
            }
        }
        System.out.println("break exit");
    }

    static void continueDemo() {
        for (int i = 0; i < 3; i++) {
            try {
                System.out.println("continue try " + i);
                if (i < 2) {
                    continue;
                }
                System.out.println("continue body " + i);
            } finally {
                System.out.println("continue finally " + i);
            }
        }
        System.out.println("continue exit");
    }

    static void throwingDemo() {
        try {
            throw new IllegalStateException("boom");
        } finally {
            System.out.println("finally before propagation");
        }
    }

    // Chỉ để minh họa lỗi thiết kế: đừng return trong finally.
    static int overrideReturn() {
        try {
            return 1;
        } finally {
            System.out.println("finally overrides return");
            return 2;
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac FinallyControlFlowDemo.java
java FinallyControlFlowDemo
~~~

**Stdout xác định:**

~~~text
== RETURN ==
try return
finally after return
return result: 10
finally local=9
snapshot result: 3
== BREAK ==
break try 0
break finally 0
break try 1
break finally 1
break exit
== CONTINUE ==
continue try 0
continue finally 0
continue try 1
continue finally 1
continue try 2
continue body 2
continue finally 2
continue exit
== EXCEPTION ==
finally before propagation
caught: boom
== OVERRIDE ==
finally overrides return
overridden result: 2
~~~

### Đối chiếu với các quy tắc

**`returnNormally()`:** Phương thức chuẩn bị trả `10`; trước khi caller in kết quả, nó chạy khối `finally`. Không có `return` khác trong `finally` nên giá trị `10` được giữ nguyên.

**`returnSnapshot()`:** Giá trị nguyên thủy `3` được xác định trước `finally`; sửa biến cục bộ thành `9` và in giá trị `9` không thay đổi kết quả mà caller nhận.

**`breakDemo()`:** Khi `i = 1`, lệnh `break` yêu cầu rời vòng `for` nhưng `finally` ở chính lượt đó vẫn chạy. Không có `break try 2` vì vòng đã kết thúc.

**`continueDemo()`:** Hai lượt đầu có `continue` nên không in `continue body 0` hoặc `continue body 1`; cả hai vẫn in `finally` trước khi lặp tiếp.

**`throwingDemo()`:** Ngoại lệ `IllegalStateException` được ném trong `try`; `finally` in dòng dọn dẹp trước khi `catch` bên ngoài nhận ngoại lệ. Không có `catch` bên trong phương thức `throwingDemo`.

**`overrideReturn()`:** Cả `return 1` trong `try` và `return 2` trong `finally` đều là cú pháp hợp lệ, nhưng lệnh `return 2` của `finally` **thay thế** kết quả dự kiến `1`. Đây là phản ví dụ cố ý; không nên dùng kiểu này trong ứng dụng thật.

## 7. Khi `finally` tự `return` hoặc `throw`: nó có thể ghi đè luồng đang chờ

Đây là ngoại lệ quan trọng đối với câu nói đơn giản “`finally` luôn chạy rồi quay lại luồng ban đầu”.

Nếu `finally` **kết thúc bình thường**, nguyên nhân hoàn tất trước đó được giữ lại:

~~~java
static int keepsReturn() {
    try {
        return 7;
    } finally {
        System.out.println("cleanup");
    }
}
~~~

Nếu `finally` **tự hoàn tất bất thường** bằng `return` hoặc `throw`, kết quả từ `try` có thể bị thay thế.

### Trường hợp A: `return` trong `finally` ghi đè `return` từ `try`

~~~java
static int replacesReturn() {
    try {
        return 7;
    } finally {
        return 9;
    }
}
~~~

Phương thức trả `9`, không phải `7`. Lệnh `return` của `finally` là lý do hoàn tất được giữ lại. Trong công việc thực tế, **tránh viết `return` trong `finally`** vì nó làm luồng điều khiển khó suy luận và có thể che mất thất bại.

### Trường hợp B: `return` trong `finally` che ngoại lệ

~~~java
static int hidesFailure() {
    try {
        throw new IllegalStateException("original failure");
    } finally {
        return 9;
    }
}
~~~

Đây là **một phương thức Java hợp lệ nhưng cực kỳ không nên dùng**. Nếu gọi `hidesFailure()`, phương thức có thể trả `9` mà ngoại lệ gốc `IllegalStateException` không còn được truyền ra ngoài. Điều này làm người gọi tưởng thao tác thành công và mất tín hiệu lỗi.

### Trường hợp C: `throw` trong `finally` thay thế `return`

~~~java
static int throwsInsteadOfReturning() {
    try {
        return 7;
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
~~~

Phương thức không trả `7`. Nó ném `IllegalStateException("cleanup failed")`. Nếu caller không bắt, ngoại lệ tiếp tục lan truyền.

### Trường hợp D: `throw` trong `finally` thay thế ngoại lệ từ `try`

~~~java
static void replacesFailure() {
    try {
        throw new IllegalArgumentException("original failure");
    } finally {
        throw new IllegalStateException("cleanup failure");
    }
}
~~~

Ngoại lệ thoát ra là `IllegalStateException("cleanup failure")`. Ngoại lệ gốc không tự được lưu thành `cause` hoặc `suppressed` chỉ bởi vì hai lệnh `throw` xảy ra trong `try/finally` thủ công. Nếu cần giữ nhiều lỗi, hãy tổ chức cơ chế xử lý và liên kết nguyên nhân phù hợp; với tài nguyên `AutoCloseable`, try-with-resources thường giải quyết việc giữ lỗi tốt hơn.

**Quy tắc tổng quát:** Khi khối `finally` hoàn tất bất thường vì một nguyên nhân mới, nguyên nhân đó có thể **thay thế** lý do rời `try/catch` đang chờ, dù lý do cũ là `return`, `break`, `continue` hay một ngoại lệ.

## 8. `finally` có thể thay đổi mục tiêu `break` hoặc `continue` không?

Cần phân biệt hai trường hợp.

- Nếu `finally` chỉ chạy các lệnh bình thường và kết thúc, yêu cầu `break` hoặc `continue` ban đầu sẽ được thực hiện tiếp.
- Nếu `finally` phát sinh ngoại lệ, trả khỏi phương thức, hoặc tự chuyển điều khiển theo cách hợp lệ, luồng đang chờ có thể bị thay thế.

Ví dụ:

~~~java
static void breakCancelledByException() {
    for (int i = 0; i < 1; i++) {
        try {
            break;
        } finally {
            throw new IllegalStateException("cleanup failed");
        }
    }
}
~~~

Đây là phương thức minh họa hợp lệ: `break` được yêu cầu nhưng `finally` ném ngoại lệ; phương thức kết thúc bất thường và caller nhận `IllegalStateException` nếu không có handler ở đây. Vì vậy không thể diễn giải `finally` như một “hàm callback luôn trả về” trong mọi trường hợp.

Ngược lại, nếu `finally` chỉ ghi log:

~~~java
static void breakPreserved() {
    while (true) {
        try {
            break;
        } finally {
            System.out.println("cleanup");
        }
    }
    System.out.println("done");
}
~~~

Thứ tự là `cleanup` rồi `done`. `finally` không thay đổi mục tiêu `break`.

Một ví dụ tương tự với `continue`:

~~~java
static void continuePreserved() {
    for (int i = 0; i < 2; i++) {
        try {
            continue;
        } finally {
            System.out.println("finally " + i);
        }
    }
    System.out.println("done");
}
~~~

Stdout:

~~~text
finally 0
finally 1
done
~~~

Không cần gán giá trị trả về cho `continue`; nó điều hướng vòng lặp. `finally` chạy trước mỗi bước tiếp theo.

## 9. `finally` lồng nhau: chạy từ trong ra ngoài

Khi `return`, `break`, `continue` hoặc ngoại lệ phải rời nhiều vùng `try`, Java thực hiện các khối `finally` liên quan theo trật tự tháo dần vùng lồng nhau.

~~~java
static int nestedFinally() {
    try {
        try {
            System.out.println("inner try");
            return 5;
        } finally {
            System.out.println("inner finally");
        }
    } finally {
        System.out.println("outer finally");
    }
}
~~~

Kết quả khi gọi `nestedFinally()`:

~~~text
inner try
inner finally
outer finally
~~~

Sau đó caller nhận `5` nếu cả hai `finally` hoàn tất bình thường.

Trong một chương trình có nhiều lời gọi phương thức, luồng ném ngoại lệ còn có thể làm Java chạy các `finally` của **các phương thức đang thoát khỏi stack** trước khi tới handler bên ngoài. Đối với `return`, chỉ các vùng `try` liên quan trên đường rời phương thức hiện tại được thực hiện; `return` không tự đi ngược qua caller.

## 10. `finally` với `catch` và ngoại lệ

Ví dụ:

~~~java
static int recover(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        System.out.println("parse failed");
        return -1;
    } finally {
        System.out.println("cleanup");
    }
}
~~~

Nếu `text` là `"17"`, phương thức in `cleanup` rồi trả `17`. Nếu là `"abc"`, `catch` in `parse failed`, chuẩn bị trả `-1`, `finally` in `cleanup`, rồi mới trả `-1`.

Điều này minh họa rằng `finally` chạy cả sau `return` xuất phát từ **khối `catch`**, không chỉ từ thân `try`.

Trong ví dụ ở phần trước, `throwingDemo()` cho thấy trường hợp không có handler trong phương thức; `finally` vẫn chạy trước khi ngoại lệ đi ra caller. Khi một ngoại lệ phát sinh trong chính `finally`, việc lựa chọn ngoại lệ cuối cùng phụ thuộc quy tắc hoàn tất bất thường đã giải thích.

Một khối `catch` **không bắt lại** ngoại lệ mới phát sinh trong khối `finally` cùng cấp của cấu trúc `try` đó; lỗi mới được truyền ra các vùng xử lý bao ngoài.

## 11. So sánh với try-with-resources

Mục đích phổ biến của `finally` là giải phóng tài nguyên:

~~~java
java.io.InputStream stream = openStream();
try {
    useStream(stream);
} finally {
    stream.close();
}
~~~

Đây là **đoạn minh họa**, giả định `openStream()` và `useStream(...)` có sẵn và phương thức bao quanh xử lý checked exceptions phù hợp. Nếu `useStream` thực hiện `return`, `break`, `continue` hoặc ném lỗi khiến mã rời cấu trúc, Java vẫn đi qua lệnh `stream.close()` trong `finally` theo quy tắc.

Tuy nhiên `close()` cũng có thể ném ngoại lệ và **làm che lỗi hoặc thay đổi kết quả trả về**. Với tài nguyên triển khai `AutoCloseable`, nên ưu tiên **try-with-resources**:

~~~java
static String firstLine(String text) throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 new java.io.BufferedReader(
                         new java.io.StringReader(text))) {
        return reader.readLine();
    }
}
~~~

Phương thức này có thể đặt trong một lớp Java 17+. Tài nguyên `reader` được đóng tự động sau khi thân `try` chuẩn bị hoàn tất và trước khi `return` của phương thức thực sự hoàn tất.

Với try-with-resources, nếu thân `try` đã ném một ngoại lệ và `close()` cũng ném lỗi, Java thường giữ **ngoại lệ từ thân `try` làm ngoại lệ chính** và đưa lỗi đóng tài nguyên vào `getSuppressed()`. Cơ chế này khác với việc viết `finally { resource.close(); }` thủ công, nơi lỗi mới từ `close()` có thể thay thế lỗi cũ.

Nếu thân `try` đang **trả về bình thường** nhưng việc `close()` ném lỗi, lời gọi vẫn có thể kết thúc bất thường thay vì trả kết quả. Vì vậy, ý tưởng “đã đến `return` là chắc chắn caller nhận kết quả” cũng không đúng trong try-with-resources.

## 12. Những trường hợp `finally` không được bảo đảm sẽ chạy

`finally` cung cấp hành vi dọn dẹp mạnh mẽ trong luồng thực thi Java thông thường, nhưng không phải bảo đảm bất chấp mọi hoàn cảnh.

Các tình huống cần lưu ý:

- **VM hoặc tiến trình bị chấm dứt:** chẳng hạn `Runtime.getRuntime().halt(...)`, hệ điều hành chấm dứt tiến trình hoặc lỗi JVM nghiêm trọng.
- **`System.exit(...)` khi thực sự làm VM kết thúc:** chương trình không thực hiện quá trình tháo stack Java theo nghĩa bảo đảm chạy `finally` cho mọi luồng.
- **Không bao giờ rời khối `try`:** ví dụ luồng bị kẹt trong vòng lặp vô hạn mà không có bước thoát.
- **Hoạt động không thể tiếp tục bình thường do môi trường:** mất điện, dừng cưỡng bức hoặc lỗi ngoài khả năng ứng dụng kiểm soát.

Ngay cả khi `finally` chạy, nó cũng có thể bị lỗi giữa chừng; đừng giả định mọi câu lệnh trong `finally` chắc chắn đã hoàn tất. Nếu cần cam kết bền vững về dữ liệu, giao dịch hay tiến trình, phải có thiết kế thích hợp như quản lý transaction, ghi nhận sự kiện, cơ chế phục hồi khi khởi động lại hoặc bảo đảm ở hệ thống lưu trữ.

**Không nên dùng `System.exit` để “kiểm tra” thứ tự `finally` trong chương trình chính** vì nó kết thúc tiến trình và có thể gây nhiễu cho việc chạy các ví dụ khác. Hãy thử các tình huống `return`, `break`, `continue` với những phương thức nhỏ như phần trên.

## 13. Các sai lầm phổ biến

### Sai lầm 1: “`return` chạy thì `finally` bị bỏ qua”

Sai. Khi `return` nằm trong `try`/`catch` có `finally`, `finally` thông thường chạy **trước khi caller nhận kết quả**.

### Sai lầm 2: “`finally` sửa biến nguyên thủy thì giá trị `return` sẽ đổi theo”

Không nhất thiết. Giá trị biểu thức `return` được xác định trước `finally`. Với `int value = 3; try { return value; } finally { value = 9; }`, kết quả trả bình thường vẫn là `3`.

### Sai lầm 3: “`finally` không thể tác động tới đối tượng được trả”

Sai. Nếu biểu thức trả về tham chiếu đến một đối tượng mutable, `finally` có thể sửa trạng thái của cùng đối tượng đó trước khi caller nhận tham chiếu. Đây khác với việc gán lại biến tham chiếu cục bộ.

### Sai lầm 4: “`break` hoặc `continue` sẽ nhảy thẳng qua `finally`”

Sai. Các vùng `finally` bị rời bởi đường nhảy vẫn chạy theo thứ tự trước khi Java thực hiện đích nhảy, trừ khi có lý do hoàn tất bất thường mới thay thế.

### Sai lầm 5: “`continue` khiến vòng `for` bỏ qua cả bước tăng biến”

Sai. Sau `finally` hoàn tất bình thường, `continue` trong vòng `for` đi tới phần cập nhật `update` rồi kiểm tra điều kiện vòng kế. Nó bỏ phần thân còn lại của lượt hiện tại, không mặc định bỏ cơ chế cập nhật vòng.

### Sai lầm 6: “`finally` chỉ chạy khi có ngoại lệ”

Sai. `finally` còn chạy khi `try` hoàn tất bình thường, khi `catch` đã xử lý lỗi, và khi chuẩn bị rời do `return`/`break`/`continue`.

### Sai lầm 7: “Đặt `return` trong `finally` để bảo đảm có kết quả”

Đây là thực hành nguy hiểm. `return` trong `finally` có thể thay thế `return` ở `try` và **nuốt ngoại lệ đang truyền**, khiến caller không biết thao tác đã thất bại.

### Sai lầm 8: “Nếu `finally` ném lỗi thì ngoại lệ cũ tự động là cause”

Không. Trong `try/finally` thủ công, Java không tự động nối ngoại lệ cũ thành `cause` của lỗi mới. Cần chủ động thiết kế xử lý lỗi, hoặc tận dụng quy tắc suppressed exceptions của try-with-resources khi phù hợp.

### Sai lầm 9: “Các `finally` lồng nhau chạy từ ngoài vào trong”

Sai. Khi thoát nhiều vùng `try` lồng nhau, khối `finally` của vùng trong chạy trước, sau đó mới tới vùng ngoài.

### Sai lầm 10: “`finally` bảo đảm tuyệt đối kể cả JVM bị kill”

Không. Những cơ chế làm VM/tiến trình dừng cưỡng bức hoặc không thoát khỏi `try` có thể ngăn `finally` được thực hiện.

### Sai lầm 11: “Một lệnh `return` khác trong `finally` chỉ sửa code style”

Không. Nó thay đổi **ngữ nghĩa thực thi** và có thể che lỗi. Một số công cụ phân tích mã sẽ cảnh báo, nhưng quy tắc ngôn ngữ mới là lý do chính cần tránh.

### Sai lầm 12: “`break` trong `switch statement` và `yield` của `switch expression` giống nhau”

Không. Trong `switch statement` kiểu cổ điển, `break` kết thúc statement; trong `switch expression`, `yield` cung cấp giá trị biểu thức. Khi các đường này rời cấu trúc `try` có `finally`, `finally` liên quan vẫn được xử lý. Đừng thay `yield` bằng `break value` trong Java 17.

## 14. Bài tập tự kiểm tra

**Câu 1.** Phương thức chứa `try { return 5; } finally { System.out.println("cleanup"); }` in dòng nào trước khi caller nhận `5`?

**Câu 2.** `int x = 1; try { return x; } finally { x = 2; }` trả `1` hay `2`? Vì sao?

**Câu 3.** Nếu `try` trả về một `StringBuilder`, `finally` gọi `append(...)` trên cùng đối tượng, caller có thể thấy nội dung mới không?

**Câu 4.** `break` trong `try` của vòng `for` khiến `finally` có chạy trước khi rời vòng không?

**Câu 5.** Với `continue` trong vòng `for`, bước cập nhật biến vòng xảy ra trước hay sau `finally` liên quan?

**Câu 6.** Khi `break OUTER` thoát khỏi hai `try` lồng nhau, khối `finally` nào chạy trước?

**Câu 7.** Nếu `try` định trả `7` nhưng `finally` chứa `return 9;`, caller nhận gì?

**Câu 8.** Nếu `try` ném `IllegalArgumentException` nhưng `finally` chứa `return 0;` trong phương thức trả `int`, ngoại lệ còn truyền ra caller không?

**Câu 9.** Nếu `try` định `return 7` nhưng `finally` ném `IllegalStateException`, kết quả là gì?

**Câu 10.** Vì sao lỗi xảy ra trong `finally { resource.close(); }` có thể che ngoại lệ ban đầu từ `try`?

**Câu 11.** Try-with-resources lưu lỗi đóng tài nguyên ở đâu khi thân `try` đã ném ngoại lệ chính?

**Câu 12.** Khi một `catch` thực hiện `return -1;`, `finally` cùng cấu trúc có thông thường được chạy không?

**Câu 13.** Một vòng lặp vô hạn nằm trong `try` và không bao giờ thoát. Có cơ sở nào để khẳng định `finally` sẽ chạy ngay không?

**Câu 14.** Việc dùng `System.exit(...)` có thể phá vỡ kỳ vọng “mọi `finally` đều chạy” như thế nào?

**Câu 15.** Nếu một `finally` hoàn tất bình thường, nó giữ hay thay thế lý do hoàn tất đang chờ của `try`?

### Đáp án gợi ý

1. In `cleanup` trước rồi caller mới nhận `5`.
2. Trả `1` vì giá trị biểu thức `return` được đánh giá trước khi `finally` sửa biến.
3. Có, vì tham chiếu trả về vẫn trỏ tới cùng đối tượng có thể thay đổi.
4. Có, theo luồng Java thông thường.
5. Sau `finally`, trước khi kiểm tra điều kiện cho lượt tiếp theo.
6. `finally` ở vùng trong chạy trước.
7. Nhận `9`; `return` từ `finally` thay thế kết quả đang chờ.
8. Không, lỗi có thể bị che và caller nhận `0`; đây là mã nguy hiểm.
9. Phương thức ném `IllegalStateException`, không trả `7`.
10. Vì `throw` mới từ `finally` có thể thay thế lý do hoàn tất bất thường trước đó.
11. Thường ở `getSuppressed()` của ngoại lệ chính.
12. Có; `finally` chạy trước khi `return -1` được hoàn tất.
13. Không; phải có đường thực thi rời `try` thì mới đi đến xử lý dọn dẹp.
14. VM có thể kết thúc mà không tháo hết các khung stack Java để chạy `finally`.
15. Giữ lý do hoàn tất cũ; chỉ khi `finally` tự hoàn tất bất thường mới có thể thay thế.

## 15. Ghi nhớ

**`finally` không chỉ dành cho exception.** Với `return`, Java đánh giá biểu thức trả về trước, chạy `finally` liên quan rồi mới hoàn tất trả về nếu `finally` kết thúc bình thường. Với `break` và `continue`, Java thực hiện các `finally` cần thiết trước khi rời vòng lặp hoặc đi đến lượt tiếp theo. Với các vùng lồng nhau, `finally` chạy từ trong ra ngoài khi thoát nhiều phạm vi. **Tránh `return` hoặc `throw` ngoài ý muốn trong `finally`**, vì chúng có thể ghi đè giá trị trả về, yêu cầu nhảy hoặc ngoại lệ ban đầu.