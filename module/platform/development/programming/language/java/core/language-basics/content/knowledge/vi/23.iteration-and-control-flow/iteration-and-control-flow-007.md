# `return` kết thúc phương thức đang chạy trong Java

> **Java core — language-basics / Duyệt và chuyển luồng**  
> **Môi trường:** JDK 17+, chương trình một file, không dùng thư viện ngoài.  
> **Mục tiêu:** Hiểu `return` kết thúc **lần gọi phương thức hiện tại**, phân biệt `return` với `break`/`continue`, sử dụng guard clause, trả kết quả đúng kiểu và nhận biết hành vi của `finally` hoặc callback.

## 1. `return` làm gì?

`return` dừng phần thực thi còn lại của **phương thức đang chạy** và chuyển điều khiển về chỗ gọi. Có hai dạng cơ bản:

~~~java
static void logPositive(int x) {
    if (x <= 0) {
        return; // Không có giá trị vì đây là phương thức void.
    }
    System.out.println("positive=" + x);
}

static int absolute(int x) {
    if (x >= 0) {
        return x; // Trả một giá trị int.
    }
    return -x; // Chỉ minh họa khi x không phải Integer.MIN_VALUE.
}
~~~

- `return;` dùng trong phương thức `void` (hoặc constructor để kết thúc sớm), **không trả giá trị**.
- `return expression;` dùng cho phương thức có kiểu trả về tương thích với kiểu của biểu thức.
- Khi đi tới `return`, các câu lệnh bình thường sau nó trong cùng đường thực thi sẽ **không chạy**.
- Sau khi callee `return`, **caller tiếp tục** tại câu lệnh sau lời gọi; `return` không có nghĩa thoát toàn bộ ứng dụng.

Lưu ý: `-Integer.MIN_VALUE` bị tràn trong kiểu `int`, vì vậy ví dụ `absolute` không phải hàm trị tuyệt đối đúng cho mọi giá trị `int`. Khi cần xử lý toàn miền, cân nhắc `Math.absExact` (Java 15+) hoặc nâng kiểu theo yêu cầu.

## 2. `return` khác `break` và `continue`

| Câu lệnh | Đích tác động | Sau đó làm gì? |
| --- | --- | --- |
| `return;` hoặc `return value;` | Phương thức/lambda hiện tại | Rời đơn vị gọi hiện tại, trả quyền điều khiển về nơi gọi |
| `break;` | Vòng lặp hoặc `switch` statement gần nhất thích hợp | Tiếp tục sau vòng lặp/switch |
| `continue;` | Vòng lặp gần nhất | Chuyển sang bước tiếp theo theo cấu trúc vòng lặp |
| `throw exception;` | Luồng xử lý ngoại lệ | Tìm handler; nếu không có thì truyền ngoại lệ ra ngoài |

Ví dụ tìm **phần tử dương đầu tiên** trong một mảng:

~~~java
static int firstPositive(int[] values) {
    for (int value : values) {
        if (value > 0) {
            return value; // Kết thúc cả phương thức, không chỉ vòng lặp.
        }
    }
    return -1; // Chỉ chạy khi không tìm thấy phần tử dương.
}
~~~

Với `{-2, 0, 7, 9}` kết quả là 7; phần tử 9 không cần xem nữa. Với mảng rỗng hoặc không có số dương, kết quả là -1. Vì một số dương không thể bằng -1 nên sentinel này không bị nhầm với kết quả thành công; nhưng trong các bài toán khác, dùng `OptionalInt` hoặc trạng thái riêng có thể rõ ràng hơn.

## 3. `return` bên trong vòng lặp lồng nhau

`return` không chỉ dừng vòng lặp trong cùng khối; nó thoát **toàn bộ phương thức** đang thực thi:

~~~java
static String locate(int[][] matrix, int target) {
    for (int row = 0; row < matrix.length; row++) {
        for (int col = 0; col < matrix[row].length; col++) {
            if (matrix[row][col] == target) {
                return "row=" + row + ",col=" + col;
            }
        }
    }
    return "NOT_FOUND";
}
~~~

Với `{{1, 2}, {3, 4}}` và target 3, phương thức trả `"row=1,col=0"` ngay; vòng trong **và** vòng ngoài đều không lặp tiếp.

Nếu thay `return` trong ví dụ bằng `break` không nhãn thì Java chỉ thoát vòng `for` **trong cùng**, rồi vòng ngoài vẫn có thể chạy. Nếu chỉ muốn dừng vòng trong hoặc điều khiển luồng ở phạm vi hẹp hơn phương thức, `break` hoặc `continue` thường đúng mục đích hơn.

## 4. Guard clause: thoát sớm thay vì lồng nhiều `if`

*Guard clause* kiểm tra trường hợp không đáp ứng tiền đề và `return` sớm:

~~~java
static String normalize(String name) {
    if (name == null || name.isBlank()) {
        return "MISSING";
    }
    return name.trim().toUpperCase(java.util.Locale.ROOT);
}
~~~

Mã này tách xử lý dữ liệu không hợp lệ khỏi đường xử lý chính. `||` có cơ chế ngắn mạch: khi `name == null`, Java không gọi `name.isBlank()`, tránh `NullPointerException`.

Có thể viết nhiều `return` trong một phương thức khi mỗi đường đi rõ ràng. Với hàm có kiểu trả về không phải `void`, **mọi đường kết thúc bình thường** phải tạo một giá trị tương thích. Ví dụ:

~~~java
// KHÔNG BIÊN DỊCH: thiếu return khi x <= 0.
// static String broken(int x) {
//     if (x > 0) return "POSITIVE";
// }
~~~

Nếu tất cả đường đi đã trả kết quả, phần thân còn lại không được chứa câu lệnh chắc chắn không thể thực thi:

~~~java
// KHÔNG BIÊN DỊCH: unreachable statement.
// static int wrong() {
//     return 1;
//     // System.out.println("never");
// }
~~~

Trong Java, `return` không được dùng trong biểu thức như toán tử số học; nó là một **câu lệnh chuyển luồng**.

## 5. Caller tiếp tục sau khi callee trả về

~~~java
static int compute(int value) {
    System.out.println("computeEnter=" + value);
    if (value < 0) {
        return -1;
    }
    System.out.println("computeMultiply");
    return value * 2;
}

static void runCall() {
    System.out.println("callerBefore");
    int result = compute(-4);
    System.out.println("callerAfter=" + result);
}
~~~

Khi gọi `runCall()`, thứ tự sẽ là `callerBefore`, `computeEnter=-4` và `callerAfter=-1`. Dòng `computeMultiply` bị bỏ qua vì callee trả về sớm, nhưng caller **không bị kết thúc**.

Tương tự, `return;` trong `main` chỉ kết thúc phương thức `main`; nó không phải lời gọi `System.exit(...)`. Một chương trình có thể còn công việc trên các luồng khác sau khi `main` kết thúc.

## 6. `finally` và biểu thức trả về

Khi `return` nằm trong `try` kèm `finally`, thông thường Java phải thực thi `finally` **trước khi hoàn tất việc trở về caller**:

~~~java
static int withFinally() {
    try {
        System.out.println("tryBlock");
        return 10;
    } finally {
        System.out.println("finallyBlock");
    }
}
~~~

Lời gọi `System.out.println("finallyValue=" + withFinally());` in lần lượt:

~~~text
tryBlock
finallyBlock
finallyValue=10
~~~

Biểu thức `return 10` được đánh giá trước khi `finally` chạy. `finally` có thể ghi log, giải phóng tài nguyên hoặc làm sạch trạng thái. Nếu `finally` tự `return` hay ném ngoại lệ thì nó **có thể thay thế kết quả/ngoại lệ trước đó**; tránh viết `return` trong `finally` vì dễ che giấu lỗi.

Với tài nguyên như file/stream, **try-with-resources** thường tốt hơn giải phóng thủ công. `finally` không bảo đảm chạy trong mọi hoàn cảnh ngoài mô hình thực thi bình thường (ví dụ khi JVM bị kết thúc đột ngột).

## 7. `return` bên trong lambda không kết thúc caller bên ngoài

Trong Java 17, một lambda có thân dạng khối có thể dùng `return;` để kết thúc **lần gọi lambda** hiện tại. Nó không tự kết thúc phương thức bao ngoài:

~~~java
static void visit() {
    java.util.List.of(1, 2, 3).forEach(number -> {
        if (number == 2) {
            return; // Chỉ thoát callback cho số 2.
        }
        System.out.println("lambda=" + number);
    });
    System.out.println("lambdaAfter");
}
~~~

Ví dụ in `lambda=1`, `lambda=3`, `lambdaAfter`. Mỗi phần tử có một lời gọi callback riêng, nên `return` ở giá trị 2 **không chấm dứt `forEach`**. Muốn dừng sớm toàn bộ việc duyệt theo kiểu thông thường, vòng `for`/enhanced `for` và `break`/`return` ở cấp phương thức thường rõ ràng hơn.

**Phân biệt quan trọng:** `return` từ một phương thức được gọi trong thân loop quay trở lại **caller** của chính phương thức đó; muốn thoát phương thức chứa loop, phải viết `return` trong phương thức chứa loop.

## 8. Ví dụ Java 17+ chạy độc lập

Tạo file **ReturnFlowDemo.java**:

~~~java
import java.util.List;
import java.util.Locale;

public final class ReturnFlowDemo {
    private static String sign(int value) {
        if (value < 0) {
            return "NEGATIVE";
        }
        if (value == 0) {
            return "ZERO";
        }
        return "POSITIVE";
    }

    private static int firstPositive(int[] values) {
        for (int value : values) {
            if (value > 0) {
                return value;
            }
        }
        return -1;
    }

    private static String locate(int[][] matrix, int target) {
        for (int row = 0; row < matrix.length; row++) {
            for (int col = 0; col < matrix[row].length; col++) {
                if (matrix[row][col] == target) {
                    return "row=" + row + ",col=" + col;
                }
            }
        }
        return "NOT_FOUND";
    }

    private static String normalize(String name) {
        if (name == null || name.isBlank()) {
            return "MISSING";
        }
        return name.trim().toUpperCase(Locale.ROOT);
    }

    private static void audit(int value) {
        if (value <= 0) {
            System.out.println("auditSkipped=" + value);
            return;
        }
        System.out.println("auditValue=" + value);
    }

    private static int compute(int value) {
        System.out.println("computeEnter=" + value);
        if (value < 0) {
            return -1;
        }
        System.out.println("computeMultiply");
        return value * 2;
    }

    private static int withFinally() {
        try {
            System.out.println("tryBlock");
            return 10;
        } finally {
            System.out.println("finallyBlock");
        }
    }

    private static int countDown(int remaining) {
        if (remaining <= 0) {
            return 0; // Base case của đệ quy.
        }
        return 1 + countDown(remaining - 1);
    }

    private static void visit() {
        List.of(1, 2, 3).forEach(number -> {
            if (number == 2) {
                return; // Chỉ kết thúc một lần gọi lambda.
            }
            System.out.println("lambda=" + number);
        });
        System.out.println("lambdaAfter");
    }

    public static void main(String[] args) {
        System.out.println("signMinus=" + sign(-3));
        System.out.println("signZero=" + sign(0));
        System.out.println("signPlus=" + sign(4));

        System.out.println("firstPositive="
                + firstPositive(new int[] {-2, 0, 7, 9}));
        System.out.println("firstAbsent="
                + firstPositive(new int[] {-5, 0}));
        System.out.println("firstEmpty="
                + firstPositive(new int[] {}));

        int[][] grid = {{1, 2}, {3, 4}};
        System.out.println("locate3=" + locate(grid, 3));
        System.out.println("locate9=" + locate(grid, 9));

        System.out.println("normalizeNull=" + normalize(null));
        System.out.println("normalizeBlank=" + normalize("  "));
        System.out.println("normalizeValue=" + normalize(" java "));

        audit(-2);
        audit(5);

        System.out.println("callerBefore");
        int failed = compute(-4);
        System.out.println("callerAfter=" + failed);

        int success = compute(3);
        System.out.println("callerValue=" + success);

        System.out.println("finallyValue=" + withFinally());
        System.out.println("recursiveSteps=" + countDown(3));

        visit();
        System.out.println("mainDone");
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ReturnFlowDemo.java
java ReturnFlowDemo
~~~

**Expected stdout chính xác:**

~~~text
signMinus=NEGATIVE
signZero=ZERO
signPlus=POSITIVE
firstPositive=7
firstAbsent=-1
firstEmpty=-1
locate3=row=1,col=0
locate9=NOT_FOUND
normalizeNull=MISSING
normalizeBlank=MISSING
normalizeValue=JAVA
auditSkipped=-2
auditValue=5
callerBefore
computeEnter=-4
callerAfter=-1
computeEnter=3
computeMultiply
callerValue=6
tryBlock
finallyBlock
finallyValue=10
recursiveSteps=3
lambda=1
lambda=3
lambdaAfter
mainDone
~~~

Các dòng `callerBefore` đến `callerAfter` cho thấy callee trả về nhưng caller vẫn chạy. `tryBlock` xuất hiện trước `finallyBlock` và giá trị trả về được in sau cùng. `lambdaAfter` chứng minh `return` trong callback không chặn phương thức bao ngoài.

## 9. Checklist và bài tập

| Tình huống | Kiểm tra |
| --- | --- |
| Phương thức `void` cần dừng sớm | Dùng `return;` không kèm giá trị |
| Phương thức trả `T` | Dùng `return expression;` có kiểu tương thích, đủ đường đi |
| Muốn rời toàn bộ phương thức giữa vòng lặp | Dùng `return` trong chính phương thức đó |
| Chỉ muốn rời vòng lặp | Dùng `break` thích hợp |
| Bỏ qua lượt hiện tại | Dùng `continue` |
| `return` trong `try` có `finally` | Hiểu thứ tự cleanup và tránh return trong finally |
| `return` trong callback `forEach` | Chỉ kết thúc callback, không phải phương thức bao ngoài |

**Bài 1.** Viết hàm `String category(int number)` trả `"NEG"`, `"ZERO"` hoặc `"POS"` bằng guard clauses và đủ ba đường kết thúc.

**Bài 2.** Tìm giá trị chẵn đầu tiên trong mảng bằng enhanced `for` và `return`; chọn cách biểu diễn trường hợp không tìm thấy sao cho không nhầm với kết quả hợp lệ.

**Bài 3.** Với mảng hai chiều, so sánh `break` vòng trong và `return` khi đã tìm thấy tọa độ cần tìm.

**Bài 4.** Viết một phương thức `void` bỏ qua dữ liệu null bằng `return;` và in dữ liệu khác null; dự đoán đường nào được thực thi.

**Bài 5.** Thêm một câu lệnh in vào `finally` rồi quan sát thứ tự so với giá trị `return`. Vì sao không nên `return` từ `finally`?

**Bài 6.** Thay vòng `for-each` bằng `List.forEach` lambda chứa `return;`; dự đoán liệu các phần tử phía sau có tiếp tục được duyệt không.

### Ghi nhớ

**`return` kết thúc lần gọi phương thức (hoặc lambda) đang chạy**, không tự động tắt toàn chương trình. Trong vòng lặp lồng nhau, `return` rời cả phương thức; `break` chỉ rời cấu trúc điều khiển phù hợp. Dùng `return;` cho `void` và `return value;` cho phương thức có kết quả. Guard clause làm luồng xử lý rõ ràng; chú ý `finally` và phạm vi lambda khi suy luận thứ tự thực thi.
