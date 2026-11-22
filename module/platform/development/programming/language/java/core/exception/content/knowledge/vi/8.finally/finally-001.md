# Cú pháp `try-finally` và `try-catch-finally` trong Java

`finally` là phần được đặt ở cuối một câu lệnh `try` để thực thi mã khi quyền điều khiển rời khỏi phần `try` (và `catch` nếu có) theo quy tắc của Java. Hai cách viết chính của `try` thông thường có `finally` là **`try-finally`** và **`try-catch-finally`**. Cách thứ nhất thực thi phần cuối mà không có nhánh `catch` tại cùng cấu trúc; cách thứ hai vừa có thể xử lý một số ngoại lệ vừa chạy phần cuối trước khi hoàn tất câu lệnh.

Đây là nội dung về **cú pháp, thứ tự chạy và phạm vi trách nhiệm** của từng khối. Để hiểu đúng `finally`, cần phân biệt hai chuyện: `catch` chọn cách xử lý ngoại lệ tương thích, còn `finally` tham gia vào việc hoàn tất câu lệnh `try` bất kể phần trước đó hoàn tất bình thường hay đột ngột, miễn luồng thực thi thực sự đến được bước thực hiện `finally` của Java.

## 1. Hai cấu trúc cú pháp căn bản

### 1.1. `try-finally`: thực hiện công việc cuối mà không bắt lỗi tại chỗ

```java
try {
    // Những thao tác cần thực hiện.
} finally {
    // Công việc cần thực hiện khi rời try.
}
```

Đây là **mẫu cú pháp**, hai khối comment đại diện cho mã ứng dụng. `try` đứng trước, `finally` đứng sau; không có `catch` nào trong cùng cấu trúc.

Nếu `try` hoàn tất bình thường và `finally` cũng hoàn tất bình thường, chương trình chuyển tiếp tới câu lệnh sau toàn bộ `try-finally`. Nếu `try` ném một ngoại lệ mà `finally` hoàn tất bình thường, ngoại lệ ấy **vẫn được truyền ra ngoài**; không có `catch` tại cấu trúc này để xử lý nó. `finally` tự nó không có nghĩa “đã bắt” hay “đã giải quyết” lỗi.

### 1.2. `try-catch-finally`: bắt lỗi tương thích rồi thực hiện phần cuối

```java
try {
    // Thao tác có thể phát sinh lỗi.
} catch (IllegalArgumentException ex) {
    // Xử lý lỗi tham số phù hợp.
} catch (RuntimeException ex) {
    // Xử lý một số lỗi runtime khác.
} finally {
    // Thực hiện bước cuối khi rời cấu trúc.
}
```

Các khối `catch` là **tùy chọn theo số lượng**, nhưng nếu có thì phải xuất hiện **trước `finally`**. Có thể có một hoặc nhiều `catch`, hoặc không có `catch` nếu đã có `finally`. Với các `catch` cùng cấp, nhánh đầu tiên tương thích với **kiểu thực tế** của ngoại lệ được ném từ `try` sẽ được chọn. Khi `catch` được chọn đã thực hiện xong, `finally` chạy theo quy tắc của câu lệnh, rồi mới chuyển quyền điều khiển ra ngoài.

Trong mẫu trên, `IllegalArgumentException extends RuntimeException` nên nhánh `IllegalArgumentException` phải đứng trước nhánh `RuntimeException`. Nếu đổi thứ tự, nhánh chuyên biệt bị che và mã không biên dịch.

**Mệnh đề `finally` chỉ xuất hiện một lần**, sau toàn bộ danh sách `catch`. Không có cú pháp `catch` đặt sau `finally` trong cùng câu lệnh `try`.

### 1.3. So sánh nhanh

| Thuộc tính | `try-finally` | `try-catch-finally` |
| --- | --- | --- |
| `try` | Bắt buộc | Bắt buộc |
| `catch` | Không có ở cùng cấu trúc | Một hoặc nhiều nhánh |
| `finally` | Bắt buộc | Bắt buộc |
| Có thể bắt lỗi tại cùng cấu trúc? | Không | Có, nếu ngoại lệ tương thích |
| Nếu lỗi từ `try` không được bắt và `finally` hoàn tất bình thường | Lỗi tiếp tục lan ra ngoài | Lỗi tiếp tục lan ra ngoài |
| Nếu mọi phần kết thúc bình thường | Chạy tiếp sau cấu trúc | Chạy tiếp sau cấu trúc |
| Nếu `finally` tự `throw` hoặc `return` | Có thể thay thế lý do hoàn tất trước đó | Có thể thay thế lý do hoàn tất trước đó |

Một `try-catch` **không có `finally`** cũng hợp lệ, nhưng đó là hình thức khác. Ngược lại, một `try` thông thường đứng một mình **không có cả `catch` lẫn `finally`** thì không hợp lệ. Ngoại lệ về yêu cầu cú pháp này là **`try-with-resources`** có phần khai báo tài nguyên trong ngoặc, được trình bày riêng ở phần cuối.

## 2. Thứ tự thực thi trong `try-finally`

Với một `try-finally` thông thường, Java thực hiện phần `try` trước. Sau khi phần `try` hoàn tất, Java thực hiện `finally`, rồi xác định cách hoàn tất toàn bộ câu lệnh.

```text
Bắt đầu try-finally
        |
        v
    Khối try
        |
        +---- Hoàn tất bình thường --------+
        |                                  |
        +---- return / break / continue ---+---> Khối finally
        |                                  |          |
        +---- Ném ngoại lệ ----------------+          v
                                            Xét cách finally hoàn tất
                                                       |
                              +------------------------+------------------+
                              |                                           |
                        Bình thường                                 Đột ngột
                              |                                           |
                 Giữ kết quả/lý do trước đó                  Lý do mới thay thế
```

Ví dụ đặt trong một phương thức:

```java
System.out.println("A");
try {
    System.out.println("B");
} finally {
    System.out.println("C");
}
System.out.println("D");
```

Kết quả:

```text
A
B
C
D
```

Phần `try` hoàn tất bình thường, sau đó `finally` chạy và hoàn tất bình thường. Vì vậy, câu lệnh `System.out.println("D")` được thực hiện.

Nếu thêm `throw new IllegalStateException("failed");` sau khi in `B` trong phần `try`, dòng `C` vẫn được thực hiện trong luồng Java bình thường; nhưng dòng `D` không chạy trên đường ném ngoại lệ ấy, trừ khi có một `catch` **bên ngoài** xử lý sự cố và đặt luồng điều khiển theo một đường khác.

## 3. Thứ tự thực thi trong `try-catch-finally`

Khi có `catch`, Java thực hiện bước chọn bộ xử lý **trước bước hoàn tất `finally`**:

1. Thực hiện khối `try`.
2. Nếu `try` hoàn tất bình thường, bỏ qua mọi `catch` rồi thực hiện `finally`.
3. Nếu `try` ném một đối tượng ngoại lệ, xét các `catch` cùng cấp theo thứ tự khai báo. Chỉ nhánh **đầu tiên tương thích** mới được thực thi.
4. Nếu không có `catch` phù hợp, ngoại lệ tiếp tục là lý do hoàn tất đang chờ, nhưng `finally` vẫn được thực hiện trước khi lan ra ngoài trong quá trình xử lý Java bình thường.
5. Nếu `catch` phù hợp hoàn tất bình thường, cấu trúc có thể hoàn tất bình thường sau khi `finally` hoàn tất bình thường.
6. Nếu `catch` hoàn tất đột ngột vì `throw` hay `return`, `finally` vẫn được thực hiện; nếu `finally` hoàn tất bình thường, lý do đang chờ được giữ lại.
7. Nếu chính `finally` hoàn tất đột ngột, **lý do mới của `finally`** có thể thay thế lý do trước đó.

```text
                      try
                       |
          +------------+-------------+
          |                          |
     Kết thúc thường             Ném ngoại lệ
          |                          |
       Bỏ catch               Tìm catch phù hợp
          |                     |           |
          |                   Có           Không
          |                     |           |
          |               Chạy catch     Lan ngoại lệ
          |                     |           |
          +---------------------+-----------+
                                |
                             finally
                                |
                   Xét cách hoàn tất rồi ra ngoài
```

**Không có đường “thực hiện tất cả các `catch` rồi mới chạy `finally`”.** Mỗi ngoại lệ chính chỉ làm chọn tối đa một nhánh `catch` của cùng một câu lệnh `try`. `finally` không phải là một nhánh `catch` thay thế.

## 4. Ví dụ Java 17+: quan sát cả hai cú pháp

Lưu nguyên tệp `FinallyFormsDemo.java`:

```java
public class FinallyFormsDemo {
    static void onlyFinally(boolean fail) {
        try {
            System.out.println("try-only");
            if (fail) {
                throw new IllegalStateException("failed");
            }
            System.out.println("work-ok");
        } finally {
            System.out.println("finally-only");
        }
        System.out.println("after-only");
    }

    static void catchFinally(int code) {
        try {
            System.out.println("try=" + code);
            if (code == 1) {
                throw new NumberFormatException("invalid number");
            }
            if (code == 2) {
                throw new IllegalStateException("state");
            }
            System.out.println("try-ok");
        } catch (NumberFormatException ex) {
            System.out.println("catch-number=" + ex.getMessage());
        } catch (RuntimeException ex) {
            System.out.println("catch-runtime=" + ex.getMessage());
        } finally {
            System.out.println("finally-mixed");
        }
        System.out.println("after-mixed");
    }

    public static void main(String[] args) {
        onlyFinally(false);

        try {
            onlyFinally(true);
        } catch (IllegalStateException ex) {
            System.out.println("outer=" + ex.getMessage());
        }

        catchFinally(0);
        catchFinally(1);
        catchFinally(2);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 FinallyFormsDemo.java
java FinallyFormsDemo
```

Kết quả chính xác:

```text
try-only
work-ok
finally-only
after-only
try-only
finally-only
outer=failed
try=0
try-ok
finally-mixed
after-mixed
try=1
catch-number=invalid number
finally-mixed
after-mixed
try=2
catch-runtime=state
finally-mixed
after-mixed
```

Giải thích:

- `onlyFinally(false)`: `try` kết thúc bình thường, sau đó `finally` chạy và phương thức in `after-only`.
- `onlyFinally(true)`: `throw` làm phần `try` hoàn tất đột ngột. `finally` vẫn in `finally-only`. Vì cấu trúc này không có `catch` tại chỗ, ngoại lệ tiếp tục tới `catch` bên ngoài ở `main`; `after-only` không được in trong lần gọi đó.
- `catchFinally(0)`: phần `try` không ném lỗi; hai `catch` đều bị bỏ qua; `finally` chạy.
- `catchFinally(1)`: `NumberFormatException` khớp nhánh cụ thể đầu tiên; nhánh `RuntimeException` không chạy.
- `catchFinally(2)`: ngoại lệ không khớp `NumberFormatException` nhưng khớp `RuntimeException`. Sau nhánh này, `finally` chạy và phương thức tiếp tục tới `after-mixed`.

Đoạn mã cố ý dùng ngoại lệ unchecked để tập trung quan sát cú pháp và thứ tự chạy, không cần thêm mệnh đề `throws` trong các chữ ký.

## 5. Checked exception vẫn phải bắt hoặc khai báo

Thêm `finally` **không miễn quy tắc checked exception** của Java. Nếu một lời gọi có thể ném `IOException` và không có `catch` xử lý ngoại lệ đó, phương thức chứa `try-finally` thường phải khai báo `throws IOException` hoặc một kiểu cha được phép.

Lưu thành `CheckedFinallyDemo.java`:

```java
import java.io.IOException;

public class CheckedFinallyDemo {
    static void readConfig() throws IOException {
        try {
            System.out.println("read");
            throw new IOException("config missing");
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        try {
            readConfig();
        } catch (IOException ex) {
            System.out.println("handled=" + ex.getMessage());
        }
        System.out.println("after main catch");
    }
}
```

```bash
javac -encoding UTF-8 CheckedFinallyDemo.java
java CheckedFinallyDemo
```

Kết quả:

```text
read
cleanup
handled=config missing
after main catch
```

Điểm cần nhớ: `readConfig()` công bố `throws IOException` vì lỗi có thể đi ra ngoài phương thức. `finally` chỉ thực hiện bước cuối; `main()` mới có `catch` để xử lý lỗi ấy.

Nếu trong chính `readConfig()` đặt `catch (IOException ex)` **trước `finally`** và xử lý lỗi xong mà không ném tiếp checked exception, việc khai báo `throws IOException` có thể không cần thiết nữa. Dẫu vậy, `catch` chỉ nên xử lý những gì tầng hiện tại thực sự biết cách xử lý, thay vì tự động nuốt lỗi cho mã “gọn”.

## 6. `return`, `break` và `continue` vẫn đi qua `finally`

Theo JLS, những câu lệnh như `return`, `break`, `continue` làm mã đang chạy **hoàn tất đột ngột** với lý do chuyển quyền điều khiển, dù không có ngoại lệ nào được ném. `finally` được thực hiện trước khi lý do đang chờ hoàn tất việc chuyển quyền điều khiển ra khỏi cấu trúc.

Ví dụ chạy được, lưu thành `FinallyControlFlowDemo.java`:

```java
public class FinallyControlFlowDemo {
    static int returnValue() {
        int value = 10;
        try {
            return value;
        } finally {
            value = 99;
            System.out.println("finally value=" + value);
        }
    }

    static void loop() {
        for (int i = 0; i < 3; i++) {
            try {
                if (i == 0) {
                    continue;
                }
                if (i == 1) {
                    break;
                }
            } finally {
                System.out.println("finally i=" + i);
            }
        }
        System.out.println("loop finished");
    }

    public static void main(String[] args) {
        System.out.println("returned=" + returnValue());
        loop();
    }
}
```

```bash
javac -encoding UTF-8 FinallyControlFlowDemo.java
java FinallyControlFlowDemo
```

Kết quả:

```text
finally value=99
returned=10
finally i=0
finally i=1
loop finished
```

Ở `returnValue()`, biểu thức `return value;` đã được đánh giá thành giá trị nguyên thủy `10` trước khi chạy `finally`. Gán lại biến cục bộ thành `99` trong `finally` không đổi giá trị trả về đã xác định. `finally` chạy xong bình thường thì phương thức trả `10`.

Trong vòng lặp, `continue` ở `i = 0` và `break` ở `i = 1` đều làm thực hiện `finally`. Mỗi lần lặp chỉ có một lần chạy `finally` tương ứng; vòng lặp dừng trước `i = 2`.

**Đặc biệt:** đây là ví dụ về `finally` khi rời cấu trúc theo đường điều khiển Java. Không có nghĩa mọi cách chấm dứt JVM đều bảo đảm `finally` chạy, ví dụ tiến trình bị hệ điều hành cưỡng bức kết thúc.

## 7. Nếu chính `finally` ném lỗi hoặc `return` thì sao?

`finally` không bị giới hạn phải hoàn tất bình thường. Nó có thể ném ngoại lệ, thực hiện `return` hoặc có hành vi chuyển quyền điều khiển khác hợp lệ trong ngữ cảnh. Nếu nó hoàn tất đột ngột, lý do mới **có thể thay thế** lý do ban đầu từ `try` hay `catch`.

| Phần `try`/`catch` | Phần `finally` | Kết quả toàn bộ câu lệnh |
| --- | --- | --- |
| Kết thúc bình thường | Kết thúc bình thường | Kết thúc bình thường |
| `return 10` | Kết thúc bình thường | Tiếp tục `return 10` |
| `throw A` | Kết thúc bình thường | Tiếp tục ném ngoại lệ `A` |
| `return 10` | `return 20` | Trả `20`, thay giá trị `10` đã chọn |
| `throw A` | `throw B` | Ném `B`; lý do ném `A` bị thay thế |
| Khối `catch` xử lý lỗi và hoàn tất bình thường | `throw B` | Toàn bộ cấu trúc lại kết thúc vì `B` |

Lưu thành `FinallyOverrideDemo.java`:

```java
public class FinallyOverrideDemo {
    static int overriddenReturn() {
        try {
            return 10;
        } finally {
            return 20; // Minh họa hành vi cần tránh.
        }
    }

    static void maskedException() {
        try {
            throw new IllegalStateException("original");
        } finally {
            throw new IllegalArgumentException("cleanup"); // Không nên viết như vậy.
        }
    }

    public static void main(String[] args) {
        System.out.println("value=" + overriddenReturn());

        try {
            maskedException();
        } catch (RuntimeException ex) {
            System.out.println("observed=" + ex.getMessage());
            System.out.println("cause=" + ex.getCause());
        }
    }
}
```

```bash
javac -encoding UTF-8 FinallyOverrideDemo.java
java FinallyOverrideDemo
```

Kết quả:

```text
value=20
observed=cleanup
cause=null
```

Dù `try` ban đầu muốn trả `10`, lệnh `return 20` trong `finally` đã thay thế nó. Trong `maskedException()`, ngoại lệ `IllegalStateException("original")` không phải đối tượng được truyền ra: `finally` đã ném ngoại lệ mới `IllegalArgumentException("cleanup")`. Ngoại lệ mới này **không tự động chứa ngoại lệ cũ ở `getCause()`**; ví dụ in ra `null`.

Đây là **ví dụ cảnh báo**, không phải mẫu thiết kế nên áp dụng. Tránh `return` trong `finally`, tránh ghi đè ngoại lệ gốc khi dọn dẹp. Với tài nguyên đóng được, ưu tiên `try-with-resources` để Java quản lý ngoại lệ phát sinh khi đóng.

## 8. Ngoại lệ từ `catch` hoặc `finally` không được `catch` “anh em” bắt tiếp

Một nhầm lẫn phổ biến là cho rằng khi một khối `catch` ném lỗi mới, Java sẽ chuyển xuống nhánh `catch` kế tiếp của **cùng** câu lệnh `try`. Điều này sai. Các `catch` cùng cấp là các phương án xử lý lỗi được ném từ khối `try`; chúng không tạo thành một chuỗi xử lý nối tiếp.

```java
try {
    throw new IllegalArgumentException("input");
} catch (IllegalArgumentException ex) {
    throw new IllegalStateException("converted", ex);
} catch (IllegalStateException ex) {
    System.out.println("not selected for converted error");
} finally {
    System.out.println("finally");
}
```

Đây là đoạn minh họa hợp lệ trong phương thức. Nếu không có `catch` ngoài, `IllegalStateException("converted")` vẫn lan ra sau khi in `finally`. Nhánh `catch (IllegalStateException)` cùng cấp **không xử lý** ngoại lệ vừa phát sinh trong nhánh `catch` trước.

Tương tự, một ngoại lệ phát sinh **từ `finally`** không được thử lại qua các nhánh `catch` cùng cấu trúc. Muốn xử lý ngoại lệ mới, phải đặt một cấu trúc `try-catch` bao ngoài hoặc xử lý riêng tại nơi có thể phát sinh.

Cú pháp lồng nhau hợp lệ:

```java
try {
    try {
        throw new IllegalArgumentException("input");
    } catch (IllegalArgumentException ex) {
        throw new IllegalStateException("converted", ex);
    } finally {
        System.out.println("inner-finally");
    }
} catch (IllegalStateException ex) {
    System.out.println("outer-catch=" + ex.getMessage());
}
```

Kết quả đoạn minh họa thứ hai:

```text
inner-finally
outer-catch=converted
```

Điểm quan trọng là **ranh giới của cấu trúc `try`**: lỗi được ném từ khối `catch` của cấu trúc trong sẽ đi ra ngoài và có thể được bộ xử lý của cấu trúc ngoài tiếp nhận.

## 9. Dọn dẹp tài nguyên: `finally` thông thường và `try-with-resources`

`finally` có thể dùng để hoàn trả trạng thái tạm thời hoặc thực hiện thao tác kết thúc cần thiết theo hợp đồng ứng dụng. Nhưng dùng `finally` để đóng mọi đối tượng tài nguyên theo cách thủ công thường làm mã dài, nhất là khi **cả phần nghiệp vụ lẫn thao tác đóng đều có thể ném ngoại lệ**.

Cách thủ công, minh họa:

```java
Resource resource = openResource();
try {
    useResource(resource);
} finally {
    resource.close();
}
```

Đoạn trên **chỉ là mã minh họa**, giả định `Resource`, `openResource()` và `useResource(...)` tồn tại. Nó có các giới hạn: `openResource()` được gọi **trước `try`**, nên nếu thao tác mở thất bại thì `finally` này chưa được áp dụng; đồng thời lỗi `close()` có thể làm mất lỗi ban đầu nếu `try` cũng đã ném lỗi.

Với kiểu `AutoCloseable`, Java cung cấp `try-with-resources`:

```java
try (Resource resource = openResource()) {
    useResource(resource);
} catch (IOException ex) {
    handleIoFailure(ex);
} finally {
    finishOperation();
}
```

Đây là mẫu minh họa với kiểu `Resource` thực hiện `AutoCloseable` và các hàm hỗ trợ có chữ ký phù hợp. Cấu trúc này khác với `try-finally` thông thường vì có phần chỉ định tài nguyên `(...)` sau `try`. Một `try-with-resources` **có thể không có cả `catch` và `finally`**, miễn có ít nhất một tài nguyên hợp lệ trong phần `(...)`.

Các tài nguyên được khởi tạo thành công sẽ được đóng theo thứ tự ngược với lúc khởi tạo. Khi có `catch`/`finally` đi kèm, các thao tác đóng tự động của `try-with-resources` xảy ra **trước** khối `catch` và `finally` ở cùng câu lệnh. Nếu phần thân `try` ném lỗi còn `close()` cũng ném lỗi, lỗi đóng có thể được giữ trong `getSuppressed()` của ngoại lệ chính thay vì ghi đè ngoại lệ đó.

### Chương trình chạy được minh họa thứ tự đóng và `catch-finally`

Lưu thành `ResourceOrderDemo.java`:

```java
public class ResourceOrderDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("close");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("body");
            throw new IllegalStateException("failed");
        } catch (IllegalStateException ex) {
            System.out.println("catch=" + ex.getMessage());
        } finally {
            System.out.println("finally");
        }
        System.out.println("after");
    }
}
```

```bash
javac -encoding UTF-8 ResourceOrderDemo.java
java ResourceOrderDemo
```

Kết quả:

```text
body
close
catch=failed
finally
after
```

Thứ tự này cho thấy: thân `try-with-resources` chạy, tài nguyên tự động đóng, nhánh `catch` xử lý lỗi, `finally` thực hiện bước cuối, rồi chương trình chạy tiếp. Cần nhớ đây là **đối chiếu với cú pháp quản lý tài nguyên**; khi chỉ cần học hai cấu trúc gốc, `try-finally` và `try-catch-finally` không yêu cầu tài nguyên `AutoCloseable`.

## 10. Phân biệt phạm vi `try` với mã trước/sau cấu trúc

`finally` gắn với **một câu lệnh `try` cụ thể**. Nó không phải bộ xử lý “mọi mã trong phương thức”, nên phải chọn vị trí đặt `try` chính xác.

Ví dụ minh họa:

```java
String config = loadConfig(); // Nếu ném lỗi, chưa hề vào try bên dưới.
try {
    useConfig(config);
} finally {
    System.out.println("finally");
}
```

Nếu `loadConfig()` ném ngoại lệ trước khi câu lệnh `try` bắt đầu thực thi, `finally` dưới đó **không chạy** do chưa vào cấu trúc. Muốn dọn dẹp liên quan cả hai thao tác, cần thiết kế lại phạm vi `try` hoặc dùng cấu trúc tài nguyên phù hợp, không chỉ đặt `finally` ở bất kỳ đâu cuối phương thức.

Phạm vi biến cũng quan trọng. Một biến cục bộ được khai báo **chỉ bên trong khối `try`** không tự hiển thị trong `finally`:

```java
try {
    int count = 10;
    System.out.println(count);
} finally {
    // System.out.println(count); // Nếu mở comment: không tìm thấy biến count.
}
```

Khi thực sự cần dùng biến ở cả hai khối, phải khai báo nó ở phạm vi bao ngoài, đồng thời bảo đảm biến đã được khởi tạo theo quy tắc *definite assignment*:

```java
int count = 0;
try {
    count = 10;
} finally {
    System.out.println(count);
}
```

Ở ví dụ sau, `count` nhìn thấy và đã được khởi tạo trước cấu trúc, nên mã hợp lệ. Hai đoạn này là mã minh họa trong thân phương thức, không phải tệp có `main` độc lập.

## 11. Cú pháp sai thường gặp

### Sai 1: `try` thường không có `catch` hoặc `finally`

```java
class InvalidBareTry {
    void run() {
        try {
            System.out.println("work");
        }
    }
}
```

**Cố ý không biên dịch.** Đây không phải `try-with-resources`; cần ít nhất một `catch` hoặc `finally`.

### Sai 2: đặt `finally` trước `catch`

```java
class InvalidClauseOrder {
    void run() {
        try {
            throw new IllegalArgumentException("bad");
        } finally {
            System.out.println("cleanup");
        } catch (IllegalArgumentException ex) {
            System.out.println("handled");
        }
    }
}
```

**Cố ý không biên dịch.** Đúng thứ tự là `try { ... } catch (...) { ... } finally { ... }`. Không thể đặt `catch` sau `finally` trong cùng cấu trúc.

### Sai 3: bắt ngoại lệ cha trước ngoại lệ con

```java
class InvalidCatchOrder {
    void run() {
        try {
            throw new IllegalArgumentException("bad");
        } catch (RuntimeException ex) {
            System.out.println("general");
        } catch (IllegalArgumentException ex) {
            System.out.println("specific");
        } finally {
            System.out.println("cleanup");
        }
    }
}
```

**Cố ý không biên dịch** vì `RuntimeException` đã bao phủ `IllegalArgumentException`. Đặt nhánh con trước nhánh cha nếu thực sự cần xử lý riêng.

### Sai 4: xem `finally` như `catch` để nuốt checked exception

```java
import java.io.IOException;

class InvalidCheckedFinally {
    void run() {
        try {
            throw new IOException("failed");
        } finally {
            System.out.println("cleanup");
        }
    }
}
```

**Cố ý không biên dịch** vì `IOException` là checked exception và có thể thoát khỏi `run()`. Sửa bằng `void run() throws IOException` hoặc bắt đúng kiểu ở phạm vi phù hợp. `finally` không tự hoàn thành nghĩa vụ này.

### Sai 5: nghĩ `finally` luôn cứu được tiến trình

Ngay cả khi cú pháp hợp lệ, `finally` không bảo đảm chạy nếu tiến trình bị chấm dứt đột ngột từ bên ngoài, JVM crash hoặc lệnh dừng tiến trình không cho phép luồng Java thông thường tiếp tục. Đừng dùng `finally` như bảo đảm tuyệt đối cho việc ghi dữ liệu quan trọng khi tiến trình có thể mất nguồn hoặc bị dừng cưỡng bức.

## 12. Cách lựa chọn cấu trúc trong thực tế

| Nhu cầu | Cấu trúc thích hợp |
| --- | --- |
| Cần làm công việc cuối, nhưng lỗi nên truyền lên để tầng trên xử lý | `try-finally` |
| Có thể bắt lỗi cụ thể tại chỗ và vẫn cần thực hiện bước cuối | `try-catch-finally` |
| Muốn bắt lỗi và không có công việc cuối riêng | `try-catch` |
| Cần đóng một hay nhiều tài nguyên `AutoCloseable` | Ưu tiên `try-with-resources`; thêm `catch`/`finally` nếu cần |
| Muốn giữ thông tin lỗi gốc khi dịch ngoại lệ | `catch` tạo lỗi mới với `cause`; tránh `finally` ném lỗi đè |
| Chỉ muốn ghi log rồi để lỗi tiếp tục truyền | Thường cân nhắc ghi tại ranh giới thích hợp; `try-finally` không có nghĩa vụ log |
| Cần phục hồi bằng fallback hợp lệ | `catch` ở tầng có ngữ cảnh; `finally` chỉ xử lý việc cuối |

Cấu trúc phù hợp phụ thuộc trách nhiệm của tầng hiện tại. Ví dụ, tầng repository có thể để `IOException` lan lên service, còn tầng API có thể dùng `catch` hoặc một cơ chế xử lý lỗi tập trung. `finally` nên chứa công việc phải làm khi rời phạm vi, **không nên chứa logic thay thế kết quả hoặc ngoại lệ**.

## 13. Cách dự đoán kết quả của một đoạn `try-catch-finally`

Đọc mã theo thứ tự sau:

1. **Phần `try` làm gì?** Có hoàn tất bình thường, `throw`, `return`, `break` hoặc `continue`?
2. **Nếu có ngoại lệ, `catch` nào phù hợp?** Kiểm tra kiểu thực tế và thứ tự `catch`; đừng giả định mọi nhánh sẽ chạy.
3. **Nếu `catch` đã chạy, nó hoàn tất thế nào?** Trả kết quả, ném lại lỗi, tạo ngoại lệ mới hay hoàn tất bình thường?
4. **Phần `finally` có làm gì thay đổi quyền điều khiển không?** Nếu hoàn tất bình thường, lý do trước đó được giữ; nếu `throw` hoặc `return`, nó có thể thay thế.
5. **Sau toàn bộ cấu trúc, điều gì chạy?** Chỉ chạy câu lệnh tiếp theo nếu cấu trúc có thể hoàn tất bình thường trên đường đang xét. Nếu đang truyền lỗi, xét `catch` ở phạm vi ngoài.

Thử tự tính đầu ra của đoạn đặt trong phương thức:

```java
try {
    System.out.println("start");
    throw new IllegalArgumentException("bad");
} catch (IllegalArgumentException ex) {
    System.out.println("handled");
} finally {
    System.out.println("end");
}
System.out.println("next");
```

Kết quả:

```text
start
handled
end
next
```

Lỗi được xử lý ở `catch` đầu tiên tương thích, `finally` hoàn tất bình thường nên toàn bộ `try-catch-finally` cũng hoàn tất bình thường, sau đó mã chạy đến `next`.

Nếu xóa `catch` và giữ nguyên `finally`, kết quả trước khi ngoại lệ truyền ra ngoài chỉ gồm `start` và `end`; dòng `next` không chạy trên đường đó.

## 14. Câu hỏi tự kiểm tra

**1.** Có thể viết `try { ... } finally { ... }` mà không có `catch` không?  
**Có.** Đó là `try-finally`. Nếu `try` ném lỗi, `finally` bình thường không ngăn lỗi lan ra ngoài.

**2.** Trong `try-catch-finally`, `finally` đứng trước hay sau các `catch`?  
**Sau tất cả `catch`** cùng cấu trúc; viết ngược thứ tự là sai cú pháp.

**3.** Khi `try` không ném lỗi, `catch` có được chạy như `else` không?  
**Không.** Các `catch` bị bỏ qua; `finally` vẫn được thực hiện theo quy tắc.

**4.** Khi `catch` đã xử lý một lỗi và hoàn tất bình thường, `finally` có chạy không?  
**Có.** Sau đó chương trình có thể tiếp tục câu lệnh kế tiếp nếu `finally` cũng hoàn tất bình thường.

**5.** `return 10` trong `try` và `finally` chỉ in log thì kết quả trả về là gì?  
**10**, trừ khi `finally` tự gây lý do hoàn tất đột ngột khác. `finally` chạy trước khi phương thức thực sự trả về.

**6.** Nếu `finally` viết `return 20` trong khi `try` dự định `return 10` thì sao?  
Kết quả trở thành **20**. Đây là lý do cần tránh `return` trong `finally`.

**7.** Ngoại lệ ném từ `finally` có tự được một `catch` cùng cấp trước đó bắt không?  
**Không.** Nó truyền ra phạm vi ngoài; cần bộ xử lý bao ngoài nếu muốn bắt.

**8.** Đóng tài nguyên với `try-with-resources` có hoàn toàn giống viết `resource.close()` thủ công trong `finally` không?  
**Không.** Cú pháp tài nguyên có quy tắc khởi tạo, đóng tự động và suppressed exceptions riêng.

**9.** `try { throw new IOException(); } finally { ... }` có thể bỏ `throws IOException` ở chữ ký phương thức không?  
**Không**, nếu không có bộ xử lý thích hợp và `finally` có thể hoàn tất bình thường: checked exception vẫn phải được bắt hoặc khai báo.

**10.** `finally` có chạy nếu một thao tác trước câu lệnh `try` ném lỗi khiến không vào `try` không?  
**Không.** Phạm vi `finally` gắn với câu lệnh `try` mà chương trình chưa bắt đầu.

## Tài liệu tham khảo chuẩn

- [Java Language Specification 21 — §14.20: The `try` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20).
- [JLS 21 — §14.20.1: Execution of `try-catch`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.1).
- [JLS 21 — §14.20.2: Execution of `try-finally` and `try-catch-finally`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.2).
- [JLS 21 — §14.20.3: `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3).
- [JLS 21 — §11.2: Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2).

**Ghi nhớ:** `try-finally` dùng khi cần thực thi bước cuối và cho phép lỗi tiếp tục lan truyền; `try-catch-finally` thêm khả năng xử lý ngoại lệ tại chỗ. Trong cả hai cấu trúc, `finally` chạy trước khi hoàn tất việc rời câu lệnh theo luồng Java bình thường; nếu `finally` tự `return` hoặc ném lỗi, nó có thể thay thế kết quả hoặc ngoại lệ ban đầu.
