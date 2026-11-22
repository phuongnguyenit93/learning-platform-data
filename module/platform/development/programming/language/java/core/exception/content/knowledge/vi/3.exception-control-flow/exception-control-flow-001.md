# Hoàn tất bình thường và hoàn tất đột ngột trong Java

Khi chạy một câu lệnh, Java không chỉ quan tâm đến kết quả tính toán mà còn quan tâm **cách câu lệnh kết thúc**. Java Language Specification (JLS) gọi hai khả năng này là *normal completion* (**hoàn tất bình thường**) và *abrupt completion* (**hoàn tất đột ngột**). Khái niệm này giải thích chính xác vì sao `return` rời phương thức, `break` rời vòng lặp, `continue` bỏ qua phần còn lại của vòng lặp, `yield` cung cấp giá trị cho `switch expression`, ngoại lệ làm thay đổi đường đi và `finally` vẫn được thực thi trong quá trình chuyển quyền điều khiển.

Điểm quan trọng: **“đột ngột” không đồng nghĩa với “đã xảy ra ngoại lệ”**. Một câu lệnh `return 10;` cũng hoàn tất đột ngột theo thuật ngữ của ngôn ngữ, dù phương thức có thể trả về giá trị hoàn toàn thành công.

## 1. Hai kiểu hoàn tất là gì?

### Hoàn tất bình thường — normal completion

Một câu lệnh hoàn tất bình thường khi nó thực hiện xong các bước được quy định cho đường đi bình thường, không có sự kiện chuyển quyền điều khiển đột ngột. Quyền điều khiển thường tiếp tục đến câu lệnh kế tiếp trong cùng khối.

```java
int count = 0;
count++;
System.out.println(count); // In ra 1
```

Ba câu lệnh trên lần lượt hoàn tất bình thường nếu không có ngoại lệ phát sinh. Đoạn này chỉ minh họa trong thân một phương thức; không phải chương trình độc lập. Một khối `{ ... }` cũng hoàn tất bình thường nếu toàn bộ các câu lệnh thực sự được thực hiện trong khối hoàn tất theo cách cho phép khối kết thúc bình thường.

### Hoàn tất đột ngột — abrupt completion

Một câu lệnh hoàn tất đột ngột khi nó không đi hết luồng thực thi bình thường vì xuất hiện **một lý do chuyển quyền điều khiển**. Lý do đó được truyền qua những câu lệnh hoặc khối bao quanh cho đến khi gặp cấu trúc xử lý nó; khi đó cấu trúc bên ngoài có thể tiếp tục hoàn tất bình thường.

JLS §14.1 phân loại tám dạng lý do:

| Lý do | Diễn giải |
| --- | --- |
| `break;` | Chuyển quyền điều khiển ra khỏi cấu trúc `switch` statement hoặc vòng lặp gần nhất phù hợp. |
| `break label;` | Rời câu lệnh được gắn nhãn phù hợp. |
| `continue;` | Chuyển sang lượt lặp tiếp theo của vòng lặp gần nhất phù hợp. |
| `continue label;` | Chuyển sang lượt lặp tiếp theo của vòng lặp có nhãn phù hợp. |
| `return;` | Hoàn tất đột ngột với `return;`, trả quyền điều khiển từ phương thức `void`, constructor hoặc thân lambda phù hợp; không trả về giá trị. |
| `return value;` | Trả về một giá trị từ phương thức/lambda có kiểu trả về phù hợp. |
| `throw exception;` | Ném đối tượng ngoại lệ, bao gồm ngoại lệ do JVM phát sinh trong lúc đánh giá biểu thức. |
| `yield value;` | Chuyển giá trị từ khối của `switch expression` đến toàn bộ biểu thức `switch`. |

**Lưu ý cú pháp:** Hai dạng `break`, hai dạng `continue` và hai dạng `return` là các lý do phân biệt theo JLS; `throw` và `yield` có một dạng lý do tương ứng. Nhãn của `continue label` phải gắn với một vòng lặp bao quanh; nhãn của `break label` có thể gắn với câu lệnh bao quanh phù hợp. Không thể tùy tiện dùng chúng ngoài cấu trúc hợp lệ.

Trong trường hợp `throw`, câu lệnh có thể ném tường minh hoặc một biểu thức như `10 / zero` có thể gây `ArithmeticException`. Khi đánh giá **biểu thức**, theo JLS, hoàn tất đột ngột chỉ xảy ra vì ngoại lệ được ném; `break`, `continue`, `return` và `yield` là cơ chế của **câu lệnh**.

## 2. Quy tắc lan truyền: từ câu lệnh con đến cấu trúc bao quanh

Xem luồng thông thường:

```text
Bắt đầu khối
    │
    ▼
Câu lệnh A ── hoàn tất bình thường ──► Câu lệnh B ──► Câu lệnh C
                                           │
                                           └── hoàn tất đột ngột
                                                     │
                                                     ▼
                                     Tìm cấu trúc xử lý lý do
                                          │             │
                                          ▼             ▼
                                    Được xử lý      Tiếp tục lan ra
                                          │             │
                                          ▼             ▼
                                    Có thể chạy     Có thể thoát khỏi
                                    phần tiếp        phạm vi hiện tại
```

Nếu một biểu thức được dùng trong câu lệnh ném ngoại lệ, câu lệnh bao quanh cũng hoàn tất đột ngột vì cùng lý do đó, trừ khi có quy tắc cụ thể xử lý ngoại lệ. Các bước tiếp theo vốn thuộc đường chạy bình thường sẽ bị bỏ qua.

```java
System.out.println("Trước");
int value = Integer.parseInt("abc");
System.out.println("Sau");
```

Giả sử đoạn này nằm trong phương thức có đường gọi xử lý ngoại lệ: dòng đầu in `Trước`; `parseInt` ném `NumberFormatException`, vì vậy câu lệnh gán và phần còn lại của khối không hoàn tất bình thường. Dòng in `Sau` **không được chạy trên đường đi đó**, trừ khi ngoại lệ được bắt ở một cấu trúc có thể đưa quyền điều khiển trở lại phía sau khối `try` thích hợp. Java không tự động quay lại vị trí đang lỗi để tiếp tục nửa chừng biểu thức.

Tuy vậy, phải xét **mỗi mức cấu trúc riêng**. Một câu lệnh `break` làm thân vòng lặp hoàn tất đột ngột, nhưng vòng lặp có thể **xử lý `break` rồi hoàn tất bình thường**. Tương tự, câu lệnh `return` hoàn tất đột ngột, nhưng lời gọi phương thức bên ngoài có thể đánh giá bình thường và nhận giá trị trả về. Đây là nguồn nhầm lẫn rất phổ biến khi đọc thuật ngữ JLS.

## 3. `break`, `continue` và `yield`: đột ngột ở trong, bình thường ở ngoài

Với `for` hoặc `while`:

- `break` thoát vòng lặp đang nhận lý do `break`; câu lệnh sau vòng lặp có thể chạy tiếp.
- `continue` kết thúc lượt lặp hiện tại; vòng lặp tiếp tục phần cập nhật/điều kiện theo quy tắc của loại vòng lặp.
- Một ngoại lệ **không được bắt** sẽ không được vòng lặp thông thường tự xử lý; nó tiếp tục lan ra.
- `yield` dùng để tạo giá trị từ khối của `switch expression`. Câu lệnh `yield` hoàn tất đột ngột, nhưng `switch expression` nhận giá trị và có thể hoàn tất bình thường. `yield` không tương đương `return` khỏi phương thức.

Ví dụ:

```java
int sum = 0;
for (int i = 0; i < 5; i++) {
    if (i == 1) continue;
    if (i == 3) break;
    sum += i;
}
System.out.println(sum); // In ra 2: cộng i=0 và i=2
```

Các lần `continue` và `break` thuộc đường điều khiển dự kiến. Chúng không tự tạo `Throwable` và không kích hoạt `catch`.

Trong `switch expression`:

```java
int level = 2;
int points = switch (level) {
    case 1 -> 10;
    default -> {
        yield 20;
    }
};
System.out.println(points); // In ra 20
```

Lệnh `yield 20;` kết thúc đột ngột ở cấp câu lệnh, còn biểu thức `switch` cấp ngoài hoàn tất bình thường với giá trị `20`. Mũi tên `case 1 -> 10` cũng cung cấp giá trị nhưng không yêu cầu viết từ khóa `yield`. Hai ví dụ này là đoạn mã đặt bên trong một phương thức, không phải tệp Java độc lập.

## 4. `return` và `throw`: giống nhau ở việc rời đường chạy, khác nhau ở nguyên nhân

`return` truyền kết quả về bên gọi và kết thúc lần thực thi phương thức hiện tại theo cách được quy định. `throw` kích hoạt tìm `catch` tương thích trong các khối đang bao quanh, hoặc lan ngoại lệ ra khỏi lời gọi nếu không được xử lý.

| Tình huống | Câu lệnh bên trong | Kết quả ở cấp ngoài |
| --- | --- | --- |
| `return 5;` trong phương thức `int` | Hoàn tất đột ngột với lý do trả giá trị 5. | Biểu thức gọi phương thức có thể nhận 5 và hoàn tất bình thường. |
| `throw new IllegalArgumentException(...)` | Hoàn tất đột ngột với lý do ném ngoại lệ. | Nếu không có `catch` phù hợp, lời gọi cũng hoàn tất đột ngột. |
| `throw ...` bên trong `try` được `catch` xử lý, rồi `catch` kết thúc bình thường | Khối `try` đầu tiên hoàn tất đột ngột. | Toàn bộ cấu trúc `try-catch` có thể hoàn tất bình thường. |
| `return` trong `try` có `finally` | `return` vẫn là lý do hoàn tất đột ngột của khối `try`. | `finally` chạy trước khi phương thức thực sự chuyển quyền điều khiển ra ngoài, nếu điều kiện thực thi cho phép. |

Một điều cần phân biệt: **kết thúc một lời gọi phương thức** và **hoàn tất một câu lệnh `return`** không phải cùng cấp phân tích. Câu lệnh `return` có lý do *abrupt completion*, nhưng lời gọi có thể đem lại kết quả bình thường cho biểu thức của bên gọi.

## 5. Chương trình Java 17+: quan sát nhiều kiểu hoàn tất

Lưu nội dung sau thành `FlowCompletionDemo.java`:

```java
public class FlowCompletionDemo {
    static void normalBlock() {
        int count = 0;
        {
            count++;
        }
        System.out.println("normal=" + count);
    }

    static int returnWithFinally() {
        try {
            System.out.println("in try");
            return 10;
        } finally {
            System.out.println("in finally");
        }
    }

    static void catchAndContinue() {
        try {
            throw new IllegalArgumentException("bad");
        } catch (IllegalArgumentException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
        System.out.println("after catch");
    }

    static void loopAndYield() {
        int sum = 0;
        for (int i = 0; i < 5; i++) {
            if (i == 1) continue;
            if (i == 3) break;
            sum += i;
        }

        int level = 2;
        int points = switch (level) {
            case 1 -> 10;
            default -> {
                yield 20;
            }
        };
        System.out.println("loop=" + sum + ", switch=" + points);
    }

    public static void main(String[] args) {
        normalBlock();
        System.out.println("method result=" + returnWithFinally());
        catchAndContinue();
        loopAndYield();
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 FlowCompletionDemo.java
java FlowCompletionDemo
```

Kết quả chính xác:

```text
normal=1
in try
in finally
method result=10
caught=bad
after catch
loop=2, switch=20
```

Giải thích đường chạy:

1. Khối lồng nhau trong `normalBlock` kết thúc bình thường, nên câu lệnh in tiếp theo được thực thi.
2. `return 10` làm khối `try` kết thúc đột ngột với lý do `return`. Java vẫn chạy `finally`, sau đó giá trị `10` được trả về lời gọi bên ngoài.
3. `throw` làm khối `try` của `catchAndContinue` hoàn tất đột ngột; `catch (IllegalArgumentException)` xử lý ngoại lệ và hoàn tất bình thường, nên dòng `after catch` vẫn chạy.
4. `continue` bỏ qua lượt `i=1`; `break` dừng vòng lặp ở `i=3`. Tổng là `0 + 2 = 2`. `yield 20` hoàn thành nhiệm vụ cung cấp giá trị cho `switch expression`.

Không có ngoại lệ nào thoát ra ngoài `main` trong ví dụ này, dù nhiều câu lệnh con đã hoàn tất đột ngột.

## 6. `try-catch-finally` quyết định cách hoàn tất như thế nào?

### `try-catch`

Với `try-catch` không có `finally`, trước tiên Java chạy khối `try`:

- Nếu khối `try` hoàn tất bình thường, không cần vào `catch`; cấu trúc `try-catch` hoàn tất bình thường.
- Nếu khối `try` ném ngoại lệ, Java xét các nhánh `catch` theo thứ tự khai báo để chọn nhánh đầu tiên tương thích với kiểu ngoại lệ thực tế.
- Nếu nhánh `catch` được chọn hoàn tất bình thường, cấu trúc `try-catch` cũng hoàn tất bình thường.
- Nếu không có `catch` phù hợp, ngoại lệ tiếp tục lan ra.
- Nếu chính `catch` phát sinh lý do hoàn tất đột ngột mới, cấu trúc bên ngoài nhận lý do mới đó.

`catch` chỉ xử lý lý do `throw` tương thích, **không bắt `return`, `break`, `continue` hoặc `yield`**.

### `try-finally` và `try-catch-finally`

Sau khi phần `try` (và `catch` nếu được chọn) kết thúc, Java thực hiện `finally` trước khi hoàn tất việc chuyển quyền điều khiển theo lý do đang chờ. Từ đó có bốn khả năng cốt lõi:

| Hoàn tất của phần trước `finally` | Hoàn tất của `finally` | Hoàn tất của toàn bộ cấu trúc |
| --- | --- | --- |
| Bình thường | Bình thường | Bình thường |
| Đột ngột vì lý do R | Bình thường | Đột ngột vì R (tiếp tục lý do cũ) |
| Bình thường | Đột ngột vì S | Đột ngột vì S |
| Đột ngột vì R | Đột ngột vì S | Đột ngột vì S; R bị thay thế |

Hệ quả quan trọng: một `return` hay `throw` bên trong `finally` có thể **ghi đè kết quả trả về hoặc che khuất ngoại lệ ban đầu**. Đây là lý do nên dùng `finally` cho công việc dọn dẹp nhưng **tránh `return` trong `finally`**. Logic dọn dẹp cũng cần cẩn thận khi có khả năng ném lỗi mới.

## 7. Chương trình Java 17+: `finally` giữ hoặc thay thế kết quả

Lưu thành `FinallyCompletionDemo.java`:

```java
public class FinallyCompletionDemo {
    static int preservedReturn() {
        int local = 1;
        try {
            return local;
        } finally {
            local = 99;
            System.out.println("finally local=" + local);
        }
    }

    static int replacedReturn() {
        try {
            return 1;
        } finally {
            return 2;
        }
    }

    static void maskedException() {
        try {
            try {
                throw new IllegalStateException("original");
            } finally {
                throw new IllegalArgumentException("cleanup");
            }
        } catch (RuntimeException ex) {
            System.out.println("seen=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("preserved=" + preservedReturn());
        System.out.println("replaced=" + replacedReturn());
        maskedException();
    }
}
```

```bash
javac -encoding UTF-8 FinallyCompletionDemo.java
java FinallyCompletionDemo
```

Kết quả:

```text
finally local=99
preserved=1
replaced=2
seen=cleanup
```

Với `preservedReturn()`, giá trị `local` được đánh giá thành `1` cho câu lệnh `return` **trước** khi `finally` chạy; đổi biến cục bộ sang `99` không làm đổi giá trị nguyên thủy đã được chọn để trả về. Với `replacedReturn()`, `finally` tự hoàn tất đột ngột vì `return 2`, nên kết quả `1` của `try` bị thay bằng `2`.

Ở `maskedException()`, `try` bên trong muốn ném `IllegalStateException("original")` nhưng `finally` lại ném `IllegalArgumentException("cleanup")`. Lý do `throw` mới **thay thế** lý do ban đầu; `catch` bên ngoài thấy `cleanup`. Cách viết này dùng để chỉ ra lỗi thiết kế; không nên dùng `return` hoặc cố tình ném lỗi mới trong `finally` của mã nghiệp vụ. Thông tin lỗi `original` cũng không tự động trở thành `cause` hay `suppressed` trong cấu trúc `try-finally` thông thường.

## 8. `try-with-resources`: hoàn tất và ngoại lệ khi đóng tài nguyên

`try-with-resources` cũng tuân thủ quy tắc hoàn tất nhưng có cơ chế **đóng các tài nguyên** triển khai `AutoCloseable`. Tài nguyên được đóng theo thứ tự ngược với thứ tự khởi tạo. Nếu phần thân `try` ném ngoại lệ và thao tác `close()` cũng ném ngoại lệ, Java thường giữ lỗi từ phần thân làm **ngoại lệ chính** và thêm lỗi đóng tài nguyên vào danh sách **suppressed**. Cơ chế này tránh làm mất lỗi gốc theo cách `finally` ném lỗi mới có thể gây ra.

Lưu thành `ResourceCompletionDemo.java`:

```java
public class ResourceCompletionDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IllegalArgumentException("work failed");
        } catch (Exception ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressed count=" + ex.getSuppressed().length);
            System.out.println("suppressed=" + ex.getSuppressed()[0].getMessage());
        }
        System.out.println("after try");
    }
}
```

```bash
javac -encoding UTF-8 ResourceCompletionDemo.java
java ResourceCompletionDemo
```

Kết quả:

```text
primary=work failed
suppressed count=1
suppressed=close failed
after try
```

Phần thân `try` hoàn tất đột ngột vì `throw`; `close()` cũng thất bại, nhưng lỗi đóng tài nguyên được giữ làm lỗi bị đính kèm. `catch` xử lý ngoại lệ chính và hoàn tất bình thường, nên dòng `after try` vẫn chạy. Nếu phần thân `try` kết thúc bình thường nhưng `close()` thất bại, lỗi đóng tài nguyên có thể trở thành ngoại lệ chính.

Không nên nhầm `getSuppressed()` với `getCause()`: `cause` biểu thị chuỗi nguyên nhân, còn `suppressed` ghi những ngoại lệ bổ sung trong cùng quá trình xử lý.

## 9. Hoàn tất đột ngột còn ảnh hưởng tới biên dịch

Java có **phân tích khả năng đến được câu lệnh** (*reachability*) và **kiểm tra đường trả về** dựa trên đường điều khiển có thể xảy ra. Những quy tắc này được kiểm tra tại lúc biên dịch; chúng liên quan đến nhưng không đồng nhất với quan sát thực tế của một lần chạy.

Ví dụ lỗi biên dịch:

```java
class InvalidExample {
    static int bad(int number) {
        if (number > 0) {
            return number;
        }
        // Thiếu return hoặc throw trên đường number <= 0.
    }
}
```

Đây là ví dụ **cố ý không biên dịch**: phương thức khai báo trả `int` nhưng vẫn có đường đi đến cuối thân phương thức mà không trả giá trị; trình biên dịch báo `missing return statement`. Cách sửa có thể là bổ sung `return` ở đường còn lại hoặc ném ngoại lệ có lý do:

```java
class ValidExample {
    static int positiveOnly(int number) {
        if (number > 0) {
            return number;
        }
        throw new IllegalArgumentException("number must be positive");
    }
}
```

`ValidExample` là mã Java hợp lệ nhưng không có `main` để chạy độc lập. Phương thức có hai đường: trả về giá trị hoặc ném ngoại lệ. Không có đường thực thi hợp lệ nào rơi xuống cuối thân phương thức mà thiếu giá trị trả về.

Ví dụ không tới được câu lệnh:

```java
class UnreachableExample {
    static void bad() {
        return;
        // System.out.println("never"); // Bỏ chú thích sẽ là lỗi unreachable statement.
    }
}
```

Trình biên dịch có thể nhận ra các trường hợp không thể thực thi do câu lệnh chuyển quyền điều khiển vô điều kiện. Tuy nhiên, **đừng xem mọi nhánh không xảy ra trong dữ liệu thử là unreachable theo JLS**: reachability là phân tích tĩnh với các quy tắc ngôn ngữ cụ thể, không phải chứng minh tổng quát mọi điều kiện chạy.

## 10. Cách phân tích một tình huống thực tế

Khi đọc mã kết hợp vòng lặp, ngoại lệ, `try-catch-finally` và `return`, hãy theo bốn bước:

1. **Xác định mức đang xét:** biểu thức, câu lệnh, thân vòng lặp, khối `try`, toàn bộ `try-catch-finally` hay lời gọi phương thức.
2. **Ghi lý do tại điểm chuyển quyền:** `break`, `continue`, `return`, `throw`, `yield`; đối với `throw` ghi cả kiểu và đối tượng ngoại lệ nếu cần.
3. **Đi từ trong ra ngoài:** vòng lặp/switch có nhận và xử lý `break` hoặc `continue` không; `switch expression` có nhận `yield` không; `catch` có bắt được kiểu ngoại lệ không; `finally` có hoàn tất bình thường hay ghi đè lý do không?
4. **Chỉ kết luận ở đúng cấp:** một khối có thể hoàn tất đột ngột nhưng cấu trúc bao ngoài đã xử lý và hoàn tất bình thường. Từ đó mới xác định câu lệnh nào chạy tiếp và phương thức trả về hay ném lỗi.

Ví dụ tư duy nhanh:

```java
int result;
try {
    result = Integer.parseInt("oops");
} catch (NumberFormatException ex) {
    result = -1;
} finally {
    System.out.println("done");
}
System.out.println(result);
```

Đây là đoạn mã minh họa đặt trong một phương thức. `parseInt` ném ngoại lệ, nên câu lệnh gán trong `try` hoàn tất đột ngột. `catch` bắt đúng kiểu, gán `-1` và hoàn tất bình thường. `finally` in `done` và hoàn tất bình thường. Toàn bộ `try-catch-finally` hoàn tất bình thường, rồi dòng cuối in `-1`. Kết quả theo đúng thứ tự là:

```text
done
-1
```

## 11. Những nhầm lẫn cần tránh

- **“Abrupt = lỗi”**: sai. `return`, `break`, `continue`, `yield` đều có thể là hành vi mong muốn.
- **“Có `return` thì `finally` không chạy”**: sai trong luồng Java thông thường; `finally` chạy trước khi hoàn tất chuyển quyền điều khiển.
- **“`finally` luôn giữ ngoại lệ gốc”**: sai. `return` hoặc `throw` từ chính `finally` có thể thay thế lý do trước đó. Dùng `try-with-resources` cho tài nguyên có thể đóng để quản lý suppressed exception phù hợp.
- **“`catch (Exception)` xử lý được mọi lý do abrupt”**: sai. Nó chỉ xử lý những ngoại lệ tương thích với `Exception`; không xử lý `return`, `break`, `continue`, `yield` và không bắt được nhánh `Error`.
- **“Câu lệnh `return` đột ngột nghĩa là lời gọi phương thức cũng thất bại”**: sai. Bên gọi có thể nhận giá trị và tiếp tục bình thường.
- **“`finally` được bảo đảm chạy kể cả khi JVM bị chấm dứt đột ngột”**: không đúng. Các tình huống như tiến trình bị cưỡng bức kết thúc hoặc JVM dừng trước khi thực thi khối không bảo đảm chạy `finally`.
- **“Bắt lỗi là chạy tiếp ngay tại câu lệnh gây lỗi”**: sai. Xử lý diễn ra ở `catch` tương ứng, và sau đó quyền điều khiển đi theo cấu trúc của `try-catch`.

## 12. Tự kiểm tra

1. `return 42;` có phải hoàn tất đột ngột? **Có**, vì lý do `return` với giá trị. Việc lời gọi phương thức nhận được `42` có thể là một kết quả bình thường ở cấp ngoài.
2. `break;` trong vòng lặp có tự ném ngoại lệ không? **Không.** Nó chuyển quyền điều khiển ra ngoài vòng lặp thích hợp.
3. Khi `try` ném lỗi được `catch` bắt và `catch` kết thúc bình thường, cấu trúc `try-catch` có thể kết thúc bình thường không? **Có.**
4. `finally` ném ngoại lệ mới trong lúc một ngoại lệ cũ đang chờ được ném ra thì sao? **Thông thường lý do mới thay thế lý do cũ** trong `try-finally` thông thường; lỗi cũ không tự động được đính kèm.
5. `yield` có thoát khỏi phương thức giống `return` không? **Không.** Nó chuyển giá trị ra khỏi `switch expression` thích hợp.
6. Một biểu thức hoàn tất đột ngột vì `continue` được không? **Không.** Theo JLS, biểu thức chỉ hoàn tất đột ngột do một ngoại lệ bị ném.

## Tham khảo

- [Java Language Specification, Java SE 21 — §14.1 Normal and Abrupt Completion of Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.1).
- [JLS Java SE 21 — §14.20 `try` statement và `finally`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20).
- [JLS Java SE 21 — §14.20.3 `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3).
- [JLS Java SE 21 — §15.6 Normal and Abrupt Completion of Evaluation](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.6).

**Ghi nhớ:** Hai khái niệm *normal completion* và *abrupt completion* mô tả **cách một đơn vị thực thi kết thúc ở một cấp cụ thể**. Hãy xác định lý do abrupt, theo dõi cách cấu trúc bao ngoài xử lý lý do đó và luôn kiểm tra `finally` trước khi kết luận điều gì được trả về, ném ra hoặc chạy tiếp.
