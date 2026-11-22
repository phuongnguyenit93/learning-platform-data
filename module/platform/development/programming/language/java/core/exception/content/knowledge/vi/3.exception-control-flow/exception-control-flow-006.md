# Vị trí tiếp tục thực thi sau khi xử lý ngoại lệ trong Java

Một câu hỏi quan trọng khi đọc chương trình dùng `try`/`catch` là: **sau khi exception được bắt, Java chạy câu lệnh nào tiếp theo?** Java **không tự quay lại câu lệnh đã ném exception** và cũng **không tiếp tục những câu lệnh còn lại của khối `try` đã bị ngắt**. Nếu một `catch` phù hợp xử lý exception và kết thúc bình thường, luồng thực thi sẽ đi qua phần dọn dẹp cần thiết (nếu có) rồi tiếp tục tại **câu lệnh hợp lệ tiếp theo sau cấu trúc `try`/`catch`/`finally`** trong phạm vi hiện tại.

Tuy nhiên, vị trí thực tế còn phụ thuộc nơi đặt `catch`, phương thức nào đã bị tháo khỏi call stack, `finally`, `return`, `break`, `continue`, exception mới trong lúc xử lý, và việc exception có được bắt hay không. Bài này xây dựng quy tắc để xác định **đường thực thi tiếp theo** thay vì học thuộc riêng một ví dụ.

## 1. Quy tắc nền tảng: khối `try` đã ném exception không chạy tiếp

Với cấu trúc:

```java
try {
    statementA();
    statementB(); // Ném exception
    statementC();
} catch (SomeException e) {
    handle(e);
}
statementD();
```

Đây là **mã khung minh họa**, các phương thức và kiểu `SomeException` chưa được định nghĩa; không chạy độc lập. Giả sử `statementB()` ném đúng loại được `catch` bắt và `handle(e)` kết thúc bình thường, thứ tự thực thi là:

1. `statementA()` thực thi.
2. `statementB()` bắt đầu và ném exception; lời gọi đó **không hoàn tất bình thường**.
3. Java bỏ qua `statementC()` trong cùng khối `try`.
4. Java thực thi thân `catch` phù hợp, ở đây là `handle(e)`.
5. Khi `catch` kết thúc bình thường, Java thực thi `statementD()` nằm **sau toàn bộ cấu trúc `try/catch`**.

Java không “nhảy về” `statementB()` để thử lại, không tự chạy `statementC()` và không tiếp tục một phương thức đã bị thoát bất thường. Một lần thử lại chỉ xảy ra khi mã chương trình **chủ động** viết logic lặp hoặc gọi lại phương thức.

Nếu **không có exception**, các lệnh A, B, C chạy theo thứ tự; thân `catch` không chạy và sau đó mới đến D. Nếu exception **không có `catch` phù hợp**, nó tiếp tục lan truyền ra phương thức gọi; D có thể hoàn toàn không chạy.

## 2. Ví dụ đầu tiên: tiếp tục sau `catch`

Lưu mã sau thành tệp `CatchResumeDemo.java`. Đây là một chương trình đầy đủ chạy trên Java 17+:

```java
public class CatchResumeDemo {
    public static void main(String[] args) {
        System.out.println("1. Trước try");

        try {
            System.out.println("2. Đầu try");
            int number = Integer.parseInt("abc");
            System.out.println("3. Number = " + number);
        } catch (NumberFormatException e) {
            System.out.println("4. Đang xử lý NumberFormatException");
        }

        System.out.println("5. Sau try/catch");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 CatchResumeDemo.java
java CatchResumeDemo
```

**Stdout chính xác** khi console dùng UTF-8:

```text
1. Trước try
2. Đầu try
4. Đang xử lý NumberFormatException
5. Sau try/catch
```

Lý do không có dòng số 3: `Integer.parseInt("abc")` ném `NumberFormatException`, do đó phần còn lại của câu lệnh gán và lệnh `println` kế tiếp **không chạy**. `catch` được chọn dựa trên kiểu exception. Sau khi xử lý xong, lệnh số 5 nằm ngoài cấu trúc `try/catch` được thực thi.

Đừng nhầm “exception đã được bắt” với “câu lệnh gây lỗi đã trở thành thành công”. Exception vẫn xảy ra; chương trình chỉ có một đường đi xử lý khác và có thể tiếp tục làm những công việc phù hợp.

## 3. Quy tắc tìm `catch`: vị trí bắt quyết định vị trí tiếp tục

Khi một exception được ném, JVM tìm trình xử lý phù hợp theo cấu trúc của ngôn ngữ:

- Trước hết xét những `catch` gắn với `try` bao quanh điểm ném, theo thứ tự khai báo. Một `catch` phù hợp được chọn; những `catch` còn lại của cùng `try` không chạy.
- Nếu không có handler thích hợp tại tầng hiện tại, exception tiếp tục truyền ra ngoài phạm vi chứa `try` và lên phương thức gọi. Những phương thức bị thoát bất thường không tiếp tục từ câu lệnh kế tiếp sau lời gọi gây lỗi.
- Nếu tìm thấy một `catch` ở tầng cao hơn và khối `catch` đó kết thúc bình thường, việc thực thi có thể tiếp tục **sau cấu trúc `try/catch` ở tầng đó**.
- Những `finally` và thao tác đóng tài nguyên có liên quan vẫn được xét khi các phạm vi bị thoát; chúng có thể tạo thêm exception hoặc thay đổi việc kết thúc.

Các nhánh `catch` so khớp theo quan hệ kiểu. Một `catch (RuntimeException e)` có thể bắt `NumberFormatException` vì đây là lớp con gián tiếp. Một `catch (IOException e)` không bắt `NumberFormatException`. Khi có nhánh cụ thể và tổng quát trong cùng một `try`, đặt nhánh cụ thể trước để tránh mã `catch` không thể tới.

Hình dung luồng thông thường với handler khớp:

```text
Câu lệnh trước try
        │
        ▼
      try
        │
        ├─ Không ném exception ────────────┐
        │                                 │
        └─ Ném exception                   │
                 │                        │
                 ▼                        │
          catch tương thích               │
                 │                        │
                 └───────────┐            │
                             ▼            │
                  finally (nếu có) ◀──────┘
                             │
                             ▼
                  Sau toàn bộ try/catch/finally
```

Sơ đồ này mô tả **đường kết thúc bình thường** của handler. Nếu `catch`/`finally` ném exception, hoặc có `return`/`break`/`continue`, đích thực thi được xác định theo quy tắc của những trường hợp đó.

## 4. Exception từ phương thức con: caller không tự thử lại lời gọi

Đây là tình huống rất hay bị hiểu nhầm. Khi phương thức con ném exception, phương thức gọi có thể bắt nó nếu lời gọi nằm trong `try` phù hợp. Nhưng phương thức con đã thoát bất thường; Java **không mở lại stack frame cũ** để chạy tiếp ngay sau lệnh `throw`.

Lưu tệp `CallStackResumeDemo.java`:

```java
public class CallStackResumeDemo {
    static void parseAtLowerLevel() {
        System.out.println("B. Bắt đầu trong phương thức con");
        Integer.parseInt("not-a-number");
        System.out.println("C. Cuối phương thức con");
    }

    static void invokeWithoutHandling() {
        System.out.println("A. Trước khi gọi con");
        parseAtLowerLevel();
        System.out.println("D. Sau khi gọi con");
    }

    public static void main(String[] args) {
        System.out.println("0. Trong main");
        try {
            invokeWithoutHandling();
            System.out.println("E. Sau lời gọi trong try");
        } catch (NumberFormatException e) {
            System.out.println("F. Bắt tại main");
        }
        System.out.println("G. Tiếp tục tại main");
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 CallStackResumeDemo.java
java CallStackResumeDemo
```

**Stdout chính xác:**

```text
0. Trong main
A. Trước khi gọi con
B. Bắt đầu trong phương thức con
F. Bắt tại main
G. Tiếp tục tại main
```

Các dòng C, D, E không xuất hiện. `parseAtLowerLevel` và `invokeWithoutHandling` đã kết thúc bất thường vì không tự bắt exception; tới `main` mới có handler phù hợp. Sau handler ở `main`, câu lệnh G chạy, **không phải** D hoặc E.

Nếu muốn phương thức `invokeWithoutHandling` tiếp tục sau một lỗi đã biết, cần **đặt `try/catch` bên trong chính phương thức đó** quanh thao tác có thể lỗi, hoặc thay đổi hợp đồng của phương thức con để trả về một kết quả phù hợp.

## 5. Bắt ở bên trong hay bên ngoài lời gọi: hai kết quả khác nhau

Cùng một exception nhưng handler đặt ở đâu làm thay đổi những lệnh còn được chạy.

### Trường hợp A: phương thức con bắt lỗi, sau đó trả về bình thường

```java
static int parseOrDefault(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        return 0;
    }
}
```

Đây là **phương thức minh họa**, không có `main`. Với `text = "abc"`, `catch` được thực thi và `return 0` làm phương thức trả về bình thường. Caller có thể chạy lệnh ngay sau `parseOrDefault("abc")` vì lời gọi đã hoàn tất bình thường (giá trị `0`). Nhưng cần cân nhắc: sử dụng `0` làm giá trị dự phòng chỉ đúng nếu hợp đồng quy định rõ; nếu số `0` cũng là dữ liệu hợp lệ, nên cân nhắc kiểu kết quả phân biệt thành công/thất bại.

### Trường hợp B: phương thức con để lỗi đi ra; caller bắt lỗi

```java
static int parseStrict(String text) {
    return Integer.parseInt(text);
}

static void run() {
    try {
        int value = parseStrict("abc");
        System.out.println("Giá trị: " + value);
    } catch (NumberFormatException e) {
        System.out.println("Giá trị nhập sai");
    }
    System.out.println("Tiếp tục run");
}
```

Đây là **các phương thức minh họa** được đặt trong một lớp; không có `main`. Lệnh in `Giá trị:` bị bỏ qua vì lời gọi `parseStrict` không trả về bình thường. Lệnh `Tiếp tục run` nằm sau cấu trúc `try/catch` nên chạy nếu handler kết thúc bình thường.

Điểm cần nhớ: **“sau `catch`” là sau `catch` thuộc đúng phạm vi đang xử lý**, không có một vị trí tiếp tục toàn cục dành chung cho tất cả exception.

## 6. `finally` nằm trên đường rời `try/catch`

Một cấu trúc có `finally`:

```java
try {
    work();
} catch (SomeException e) {
    recover(e);
} finally {
    cleanup();
}
nextStep();
```

Đây là khung minh họa không chạy độc lập. Trường hợp `work()` ném `SomeException` và `recover(e)` kết thúc bình thường, thứ tự là: **`work` tới điểm ném → `catch` xử lý → `finally` dọn dẹp → `nextStep`**.

Nếu `work` không ném exception, thứ tự là `work` hoàn tất → `finally` → `nextStep`. Nếu exception không được bắt, `finally` vẫn được thực hiện trong quá trình exception lan truyền thông thường, nhưng `nextStep` không chạy tại phạm vi đang bị thoát.

Ví dụ hoàn chỉnh trong `FinallyResumeDemo.java`:

```java
public class FinallyResumeDemo {
    static void execute(boolean fail) {
        System.out.println("Bắt đầu");
        try {
            System.out.println("Trong try");
            if (fail) {
                throw new IllegalArgumentException("Dữ liệu sai");
            }
            System.out.println("Try thành công");
        } catch (IllegalArgumentException e) {
            System.out.println("Trong catch: " + e.getMessage());
        } finally {
            System.out.println("Trong finally");
        }
        System.out.println("Sau try/catch/finally");
    }

    public static void main(String[] args) {
        execute(false);
        System.out.println("---");
        execute(true);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 FinallyResumeDemo.java
java FinallyResumeDemo
```

**Stdout chính xác**:

```text
Bắt đầu
Trong try
Try thành công
Trong finally
Sau try/catch/finally
---
Bắt đầu
Trong try
Trong catch: Dữ liệu sai
Trong finally
Sau try/catch/finally
```

Ví dụ cho thấy `finally` được đặt trên cả đường thành công và đường exception đã được xử lý. Đừng đặt `return` hoặc ném exception mới trong `finally` một cách tùy tiện: chúng có thể ghi đè việc kết thúc đã được xác định trước đó.

**Lưu ý giới hạn:** `finally` không phải cam kết tuyệt đối trong mọi tình huống môi trường. Tiến trình bị chấm dứt cưỡng bức, JVM gặp sự cố nghiêm trọng hoặc lời gọi `System.exit` có thể ngăn việc thực hiện cleanup thông thường. Với tài nguyên `AutoCloseable`, `try-with-resources` thường là lựa chọn ưu tiên.

## 7. `return` trong `try` hoặc `catch`: không đi tiếp sau cấu trúc

Đường đi bình thường sau `catch` chỉ xảy ra khi khối `catch` hoàn tất **bình thường**. Nếu khối `catch` thực hiện `return`, phương thức sẽ trả về cho caller sau khi thực thi `finally` cần thiết, thay vì chạy lệnh đứng sau cấu trúc.

Tệp `ReturnFinallyDemo.java`:

```java
public class ReturnFinallyDemo {
    static int compute(boolean fail) {
        try {
            System.out.println("Try");
            if (fail) {
                throw new IllegalStateException("Không tính được");
            }
            return 10;
        } catch (IllegalStateException e) {
            System.out.println("Catch");
            return -1;
        } finally {
            System.out.println("Finally");
        }
    }

    public static void main(String[] args) {
        System.out.println("Kết quả A = " + compute(false));
        System.out.println("Kết quả B = " + compute(true));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 ReturnFinallyDemo.java
java ReturnFinallyDemo
```

**Stdout chính xác**:

```text
Try
Finally
Kết quả A = 10
Try
Catch
Finally
Kết quả B = -1
```

Ở lần A, `return 10` trong `try` khiến `finally` chạy trước khi caller nhận `10`; `catch` không chạy. Ở lần B, `try` ném exception, `catch` in rồi `return -1`, nhưng `finally` vẫn chạy trước khi caller nhận giá trị.

Tương tự, `throw` trong `catch` khiến exception mới đi lên thay vì tiếp tục với lệnh sau cấu trúc. Lệnh `break` hoặc `continue` bên trong `try/catch` nằm trong vòng lặp cũng điều khiển việc chuyển sang vị trí khác, sau khi chạy `finally` theo quy tắc.

**Cảnh báo:** `return` trong `finally` có thể làm mất cả giá trị `return` đang chờ lẫn exception đang lan truyền; thông thường tránh viết như vậy.

## 8. Nếu chính `catch` ném exception mới thì sao?

Các nhánh `catch` của **cùng một `try`** không phải chuỗi “thử tiếp nhánh khác” sau khi một handler gặp vấn đề. Một khi `catch` đã được chọn, những `catch` đứng sau trong cùng cấu trúc **không bắt exception được ném từ thân `catch` đó**. Exception mới phải đi tới một `try` bao ngoài hoặc caller phù hợp.

Ví dụ đầy đủ ở `CatchThrowsDemo.java`:

```java
public class CatchThrowsDemo {
    public static void main(String[] args) {
        try {
            try {
                throw new NumberFormatException("chuỗi sai");
            } catch (NumberFormatException e) {
                System.out.println("Catch bên trong");
                throw new IllegalStateException("Xử lý bị lỗi", e);
            } catch (IllegalStateException e) {
                System.out.println("Catch thứ hai ở bên trong");
            } finally {
                System.out.println("Finally bên trong");
            }
        } catch (IllegalStateException e) {
            System.out.println("Catch bên ngoài: " + e.getMessage());
        }
        System.out.println("Tiếp tục bên ngoài");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 CatchThrowsDemo.java
java CatchThrowsDemo
```

**Stdout chính xác**:

```text
Catch bên trong
Finally bên trong
Catch bên ngoài: Xử lý bị lỗi
Tiếp tục bên ngoài
```

Lý do: `NumberFormatException` được handler đầu tiên bắt, sau đó handler này ném `IllegalStateException`. Nhánh `catch (IllegalStateException e)` **cùng cấp** không được thử nữa. `finally` của cấu trúc bên trong chạy trước khi exception tiếp tục đến handler bên ngoài. Khi handler bên ngoài kết thúc bình thường, lệnh cuối của `main` mới chạy.

Sử dụng constructor chứa `cause` để giữ nguyên nhân ban đầu là `NumberFormatException`. Khi chẩn đoán, `e.getCause()` ở handler bên ngoài cho phép lần về lỗi gốc.

## 9. Nếu `finally` ném exception hoặc điều khiển luồng thì sao?

`finally` có thể thay đổi kết quả đã được xác định ở `try` hoặc `catch`. Ví dụ, một exception ban đầu đang được lan truyền, nhưng `finally` lại ném một exception khác: exception mới có thể **thay thế** exception ban đầu như kết quả trực tiếp quan sát được của toàn bộ cấu trúc.

Xét đoạn mã minh họa:

```java
try {
    throw new IllegalArgumentException("Lỗi chính");
} finally {
    throw new IllegalStateException("Lỗi trong cleanup");
}
```

Nếu được đặt trong một ngữ cảnh Java hợp lệ, exception thoát ra là `IllegalStateException` từ `finally`. Trong cách viết này, lỗi chính có thể bị che khuất. Vì vậy không chủ động `throw` hoặc `return` trong `finally` chỉ để “chắc chắn có xử lý”; ưu tiên code cleanup rõ ràng, giữ nguyên nhân và dùng `try-with-resources` khi thích hợp.

Tương tự, nếu `finally` có `return`, giá trị trả về đang chờ từ `try`/`catch` có thể bị thay thế. Java cho phép một số dạng này, nhưng chúng làm luồng thực thi khó lý giải và thường bị quy tắc code quality cảnh báo.

`finally` có thể không hoàn tất bình thường vì exception từ thao tác cleanup. Khi đó câu lệnh kế tiếp sau cấu trúc **không tự động chạy**, trừ khi tầng bao ngoài bắt exception mới và tiếp tục tại vị trí của tầng đó.

## 10. `try-with-resources`: đóng tài nguyên trước khi vào `catch` bên ngoài khối tài nguyên

Trong `try-with-resources`, Java đóng những tài nguyên `AutoCloseable` đã khởi tạo thành công khi rời khối `try`. Nếu có nhiều tài nguyên, chúng được đóng theo **thứ tự ngược với thứ tự khai báo**. Tài nguyên được đóng **trước** khi một `catch` hoặc `finally` gắn với câu lệnh `try-with-resources` ấy thực thi.

Tệp `ResourceResumeDemo.java`:

```java
public class ResourceResumeDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("A");
             Resource second = new Resource("B")) {
            System.out.println("Trong try");
            throw new IllegalArgumentException("Thao tác thất bại");
        } catch (IllegalArgumentException e) {
            System.out.println("Catch: " + e.getMessage());
        } finally {
            System.out.println("Finally");
        }
        System.out.println("Sau try-with-resources");
    }
}
```

Biên dịch, chạy:

```bash
javac -encoding UTF-8 --release 17 ResourceResumeDemo.java
java ResourceResumeDemo
```

**Stdout chính xác**:

```text
Mở A
Mở B
Trong try
Đóng B
Đóng A
Catch: Thao tác thất bại
Finally
Sau try-with-resources
```

Thứ tự có ý nghĩa: exception tại thân `try` không làm mã chạy tiếp ở đó; trước khi tới `catch`, hai tài nguyên đã được đóng theo B rồi A. Sau `catch` là `finally`, sau đó mới đến dòng cuối.

Khi `close()` cũng ném exception trong lúc một exception khác từ thân `try` đang được lan truyền, exception khi đóng **thường được đính kèm dưới dạng suppressed exception**, còn exception chính của thân `try` được giữ lại. Điều này khác cách viết `finally` ném lỗi mới có thể che lỗi ban đầu.

Ví dụ tối giản kiểm tra suppressed:

```java
public class SuppressedDemo {
    static class FailingClose implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("Không đóng được");
        }
    }

    public static void main(String[] args) {
        try (FailingClose resource = new FailingClose()) {
            throw new IllegalArgumentException("Thao tác lỗi");
        } catch (IllegalArgumentException e) {
            System.out.println("Chính: " + e.getMessage());
            System.out.println("Suppressed: " + e.getSuppressed().length);
            System.out.println("Phụ: " + e.getSuppressed()[0].getMessage());
        }
        System.out.println("Tiếp tục sau catch");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 SuppressedDemo.java
java SuppressedDemo
```

**Stdout chính xác**:

```text
Chính: Thao tác lỗi
Suppressed: 1
Phụ: Không đóng được
Tiếp tục sau catch
```

Đoạn này cho thấy `catch` nhìn thấy exception chính của thân `try`, và exception khi đóng được lưu trong `getSuppressed()`. Nếu chỉ `close()` thất bại mà thân `try` không ném exception, exception từ `close()` có thể trở thành exception chính và được handler phù hợp bắt.

## 11. `catch` nằm trong hay ngoài vòng lặp?

Vòng lặp làm vị trí tiếp tục dễ nhầm. So sánh hai cấu trúc:

**`try/catch` ở bên trong vòng lặp:**

```java
for (String value : inputs) {
    try {
        process(value);
    } catch (NumberFormatException e) {
        System.out.println("Bỏ qua input sai");
    }
}
```

**`try/catch` bao ngoài toàn bộ vòng lặp:**

```java
try {
    for (String value : inputs) {
        process(value);
    }
} catch (NumberFormatException e) {
    System.out.println("Dừng vòng lặp vì input sai");
}
```

Hai đoạn đều là **khung mã minh họa**, giả định có `inputs` và `process`. Với handler bên trong, lần lặp hiện tại có thể kết thúc rồi vòng lặp xét phần tử tiếp theo. Với handler bao ngoài, khi một lượt lặp ném exception và thoát đến `catch` bên ngoài, **toàn bộ vòng lặp đã bị thoát**; Java không tự quay lại phần tử tiếp theo.

Ví dụ hoàn chỉnh tại `LoopCatchDemo.java`:

```java
public class LoopCatchDemo {
    static void insideLoop(String[] values) {
        for (String value : values) {
            try {
                System.out.println("Trong: " + Integer.parseInt(value));
            } catch (NumberFormatException e) {
                System.out.println("Trong: bỏ qua " + value);
            }
        }
        System.out.println("Trong: kết thúc vòng lặp");
    }

    static void outsideLoop(String[] values) {
        try {
            for (String value : values) {
                System.out.println("Ngoài: " + Integer.parseInt(value));
            }
        } catch (NumberFormatException e) {
            System.out.println("Ngoài: bắt lỗi và rời vòng lặp");
        }
        System.out.println("Ngoài: sau try/catch");
    }

    public static void main(String[] args) {
        String[] values = {"1", "sai", "3"};
        insideLoop(values);
        System.out.println("---");
        outsideLoop(values);
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 LoopCatchDemo.java
java LoopCatchDemo
```

**Stdout chính xác**:

```text
Trong: 1
Trong: bỏ qua sai
Trong: 3
Trong: kết thúc vòng lặp
---
Ngoài: 1
Ngoài: bắt lỗi và rời vòng lặp
Ngoài: sau try/catch
```

Với `insideLoop`, lần lặp giá trị `"sai"` có handler tại chính lần lặp đó; sau `catch`, vòng lặp đi tới `"3"`. Với `outsideLoop`, lỗi tại `"sai"` khiến Java đi ra khỏi vòng lặp tới `catch` bên ngoài; `"3"` không còn được xử lý.

Quy tắc này không đồng nghĩa `catch` luôn có nghĩa “bỏ qua input sai”. Nếu trạng thái trung gian đã thay đổi hoặc có side effect, tiếp tục vòng lặp có thể không an toàn. Cần thiết kế chính sách xử lý theo hợp đồng và trạng thái.

## 12. `break`, `continue` và `return` thay đổi đích điều khiển

Trong các khối `try` hoặc `catch` đặt trong vòng lặp:

- `continue` chuyển điều khiển sang bước tiếp theo của vòng lặp tương ứng (hoặc nhãn vòng lặp được chỉ định), sau khi thực hiện `finally` cần thiết. Nó không đơn thuần chuyển đến câu lệnh sau khối `try/catch` của lần lặp hiện tại.
- `break` rời vòng lặp hoặc khối `switch` tương ứng (hoặc cấu trúc có nhãn) sau khi thực hiện `finally` cần thiết. Đích là câu lệnh sau vòng lặp/`switch`, không phải đầu lần lặp tiếp theo.
- `return` rời phương thức sau khi thực hiện `finally` cần thiết. Caller chỉ tiếp tục sau lời gọi khi phương thức kết thúc bình thường bằng việc trả về; nếu exception được ném tiếp ra ngoài, caller có thể phải bắt nó.
- `throw` tạo/đẩy exception và bắt đầu tìm handler phù hợp; những lệnh đứng sau `throw` trong cùng đường đi không thực hiện.

Ví dụ `continue` và `finally` trong `ContinueFinallyDemo.java`:

```java
public class ContinueFinallyDemo {
    public static void main(String[] args) {
        for (int i = 1; i <= 3; i++) {
            try {
                System.out.println("Try " + i);
                if (i == 2) {
                    continue;
                }
                System.out.println("Giữa " + i);
            } finally {
                System.out.println("Finally " + i);
            }
            System.out.println("Cuối lượt " + i);
        }
        System.out.println("Sau vòng lặp");
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 ContinueFinallyDemo.java
java ContinueFinallyDemo
```

**Stdout chính xác**:

```text
Try 1
Giữa 1
Finally 1
Cuối lượt 1
Try 2
Finally 2
Try 3
Giữa 3
Finally 3
Cuối lượt 3
Sau vòng lặp
```

Khi `i == 2`, `continue` trong `try` làm bỏ qua `Giữa 2` và `Cuối lượt 2`, nhưng **`Finally 2` vẫn được in** trước khi tới lần lặp có `i == 3`. Ví dụ này không có exception, vì mục tiêu là hiểu cách `finally` tương tác với các dạng điều khiển luồng khác nhau.

## 13. `try` lồng nhau: bắt ở mức gần nhất phù hợp

`try` lồng nhau có thể khiến ngoại lệ được xử lý ngay trong khối bên trong hoặc lan sang bên ngoài. Nếu tầng bên trong bắt và xử lý bình thường, câu lệnh sau cấu trúc bên trong **trong khối ngoài** có thể tiếp tục. Nếu bên trong không có handler phù hợp, Java rời phần còn lại của `try` ngoài để tìm `catch` ngoài.

Chương trình `NestedTryDemo.java`:

```java
public class NestedTryDemo {
    static void handledInside() {
        try {
            System.out.println("A1");
            try {
                throw new IllegalArgumentException("Lỗi A");
            } catch (IllegalArgumentException e) {
                System.out.println("A2: catch trong");
            }
            System.out.println("A3: tiếp trong try ngoài");
        } catch (RuntimeException e) {
            System.out.println("A4: catch ngoài");
        }
        System.out.println("A5: sau toàn bộ");
    }

    static void handledOutside() {
        try {
            System.out.println("B1");
            try {
                throw new IllegalStateException("Lỗi B");
            } catch (NumberFormatException e) {
                System.out.println("B2: catch trong");
            }
            System.out.println("B3: sau try trong");
        } catch (IllegalStateException e) {
            System.out.println("B4: catch ngoài");
        }
        System.out.println("B5: sau toàn bộ");
    }

    public static void main(String[] args) {
        handledInside();
        System.out.println("---");
        handledOutside();
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 NestedTryDemo.java
java NestedTryDemo
```

**Stdout chính xác**:

```text
A1
A2: catch trong
A3: tiếp trong try ngoài
A5: sau toàn bộ
---
B1
B4: catch ngoài
B5: sau toàn bộ
```

Trường hợp A, handler trong bắt `IllegalArgumentException`, nên khối ngoài vẫn ở đường thực thi bình thường và chạy A3. Trường hợp B, handler trong chỉ bắt `NumberFormatException`, không phù hợp với `IllegalStateException`; vì vậy B2 và B3 không chạy, exception đi tới handler B4 bên ngoài.

Một đặc điểm đáng chú ý: khi một `catch` đã hoàn tất bình thường, các câu lệnh sau cấu trúc của nó được chạy **nếu** không bị một thao tác điều khiển luồng khác chi phối. Ví dụ A3 chạy do việc bắt trong thành công, nhưng B3 không chạy vì phần `try` chứa B3 đã bị thoát bất thường.

## 14. Khi không có handler phù hợp, “tiếp tục” ở đâu?

Nếu một exception không được bắt ở phương thức hiện tại, nó tiếp tục truyền lên caller. Khi không còn handler phù hợp trên đường gọi, luồng đang thực thi có thể kết thúc bất thường. Với ứng dụng console đơn giản, exception thoát khỏi `main` thường dẫn đến in stack trace ra **stderr** và trạng thái kết thúc chương trình có lỗi.

Trong ứng dụng server, một framework có thể bắt exception tại ranh giới request, trả phản hồi lỗi và tiếp tục xử lý request khác. Trong ứng dụng đa luồng, exception không được bắt có thể kết thúc thread hiện tại mà không bắt buộc mọi thread khác cùng dừng. Vì vậy không có quy tắc “ném exception là chắc chắn JVM bị dừng toàn bộ”.

Đặc biệt, `try` không tự tạo ra handler. Một khối `try` chỉ kèm `finally` nhưng không có `catch` có thể dọn dẹp khi exception xảy ra, rồi **exception tiếp tục lan truyền**. Muốn khôi phục đường đi tại phạm vi hiện tại, cần một handler phù hợp hoặc phương án điều khiển hợp lệ khác.

## 15. Bảng tra nhanh: sau tình huống X sẽ chạy lệnh nào?

| Tình huống | Kết quả của `try/catch` ở phạm vi hiện tại | Vị trí tiếp theo |
| --- | --- | --- |
| `try` hoàn tất bình thường | Không chạy `catch`; chạy `finally` nếu có | Lệnh sau toàn bộ cấu trúc |
| `try` ném exception và `catch` phù hợp hoàn tất bình thường | Bỏ phần còn lại của `try`, xử lý `catch`, chạy `finally` nếu có | Lệnh sau toàn bộ cấu trúc |
| `try` ném exception, không có `catch` phù hợp | Thoát phạm vi, chạy cleanup/finally liên quan | Tìm handler bên ngoài hoặc ở caller; không chạy phần còn lại của phạm vi bị thoát |
| `catch` ném exception mới | Bỏ phần còn lại của `catch`, thực thi `finally` liên quan | Handler của `try` bao ngoài hoặc caller |
| `catch` thực hiện `return` | Chuẩn bị giá trị trả về, chạy `finally` nếu có | Caller nhận giá trị nếu không có can thiệp mới |
| `catch` thực hiện `break` trong loop | Rời loop sau `finally` cần thiết | Lệnh sau loop tương ứng |
| `catch` thực hiện `continue` trong loop | Chuyển lần lặp sau `finally` cần thiết | Bước cập nhật/kiểm tra tiếp theo của loop tương ứng |
| `finally` ném exception mới | Thay đổi kết quả điều khiển, có thể che exception/return cũ | Tìm handler bên ngoài cho exception mới |
| `try-with-resources` đóng tài nguyên thành công rồi handler bình thường | Đóng tài nguyên trước `catch` và `finally` | Lệnh sau toàn bộ cấu trúc |
| `try-with-resources` có lỗi chính và lỗi khi đóng | Lỗi đóng có thể được gắn suppressed vào lỗi chính | Handler nhận exception chính và có thể kiểm tra suppressed |
| `catch` trong một lời gọi con trả về bình thường | Lời gọi con hoàn tất bình thường | Câu lệnh ngay sau lời gọi ở caller |
| Handler chỉ có ở caller cao hơn | Những caller trung gian thoát bất thường | Lệnh sau cấu trúc `try/catch` tại caller thực sự bắt lỗi |

Bảng nêu các đường đi phổ biến; `finally` có thể thay đổi kết quả nếu tự nó kết thúc bất thường, và việc phục hồi phải được thiết kế phù hợp với trạng thái chương trình.

## 16. Các nhầm lẫn thường gặp và cách sửa

**Nhầm 1: “Sau `catch`, Java quay lại dòng ném lỗi.”**  
Sai. `catch` không hoạt động như retry tự động. Đường thực thi bị ném lỗi đã bị bỏ qua cho phạm vi đó; muốn retry phải viết vòng lặp hoặc gọi lại thao tác, chú ý trạng thái đã thay đổi và side effect.

**Nhầm 2: “Nếu bắt lỗi ở `main`, phương thức con được chạy tiếp.”**  
Sai. Nếu exception từ phương thức con đã lan ra ngoài, stack frame của phương thức đó đã bị tháo, không được tự phục hồi. `main` tiếp tục ở vị trí sau handler của chính nó.

**Nhầm 3: “Lệnh ngay sau `throw` vẫn chạy nếu ở dưới có `catch`.”**  
Sai. `throw` làm ngắt đường bình thường tại điểm đó. Mã sau `throw` trong cùng khối theo đường không có nhánh thay thế còn có thể là mã không thể tới và gây lỗi biên dịch.

**Nhầm 4: “`finally` chỉ chạy khi lỗi.”**  
Sai. `finally` thường chạy khi rời cấu trúc dù `try` thành công, có exception, `return` hoặc `continue`. Không được lạm dụng `finally` để viết `return` ghi đè kết quả.

**Nhầm 5: “Một `catch` có thể bắt exception mới từ `catch` đứng trước cùng cấp.”**  
Sai. Exception ném từ thân handler cần handler bao ngoài hoặc caller; các handler kế bên chỉ phục vụ exception xuất phát từ khối `try` tương ứng.

**Nhầm 6: “`try/catch` trong vòng lặp và ngoài vòng lặp đều xử lý phần tử sau giống nhau.”**  
Sai. Handler trong vòng lặp có thể cho phép lần lặp tiếp theo; handler bao ngoài nghĩa là vòng lặp đã bị thoát khi exception được bắt.

**Nhầm 7: “`try-with-resources` đóng sau khi `catch` chạy xong.”**  
Sai với `catch` gắn trực tiếp với câu lệnh `try-with-resources` ấy: các tài nguyên đã khởi tạo được đóng **trước** khi handler đó chạy.

**Nhầm 8: “Đã vào `catch` là chắc chắn chương trình ổn định và tiếp tục.”**  
Sai. `catch` có thể ném lỗi mới, chứa `return` hoặc làm mất bất biến dữ liệu. Quyết định tiếp tục chỉ an toàn khi trạng thái và hợp đồng thao tác được khôi phục phù hợp.

**Nhầm 9: “Bắt `Exception` là mọi lỗi Java đều dừng tại đây.”**  
Sai. `Error` không thuộc nhánh `Exception`; ngoài ra `catch` cũng có thể ném lỗi mới. Mỗi handler chỉ bắt các đối tượng phù hợp kiểu của nó từ phạm vi `try` gắn kèm.

## 17. Cách tự suy luận một đoạn Java có exception

Khi đọc code, đừng chỉ tìm chữ `catch` gần nhất về mặt văn bản. Hãy đánh dấu **phạm vi cấu trúc** và **thứ tự thực thi**:

1. Xác định chính xác biểu thức hoặc câu lệnh có thể ném exception; liệt kê các lệnh đã chạy trước điểm ném.
2. Xác định `try` bao quanh điểm ném; tìm handler có kiểu phù hợp, xét từ cấu trúc bên trong đến bên ngoài và lên chuỗi gọi khi cần.
3. Gạch bỏ những lệnh ở phần còn lại của `try` bị ngắt; cả những câu lệnh ngay sau lời gọi trong phương thức đã bị thoát bất thường.
4. Theo dõi những phần dọn dẹp khi unwind: `try-with-resources` đóng tài nguyên, `finally` chạy theo quy tắc.
5. Xác định handler có kết thúc **bình thường** hay thực hiện `return`, `break`, `continue`, `throw` hoặc ném lỗi mới.
6. Chỉ khi đường đi của toàn bộ cấu trúc kết thúc bình thường mới đánh dấu câu lệnh kế tiếp sau `try/catch/finally` là vị trí thực thi tiếp theo.
7. Với vòng lặp, nested `try` và caller/callee, xác định chính xác cấu trúc nào vẫn đang hoạt động sau xử lý.
8. Kiểm tra side effect trước lỗi và khả năng thực sự phục hồi. Tiếp tục thực thi là hành vi về luồng điều khiển, **không bảo đảm** dữ liệu và trạng thái đã đúng.

## 18. Bài tập tự kiểm tra

**Câu 1.** Sau khi `NumberFormatException` bị bắt bởi `catch` và handler kết thúc bình thường, Java chạy tiếp phần còn lại của `try` hay câu lệnh sau toàn bộ `try/catch`?  
**Đáp án:** Câu lệnh sau toàn bộ `try/catch`, sau `finally` nếu có. Phần còn lại của `try` bị bỏ qua.

**Câu 2.** `main` gọi `A()`, `A()` gọi `B()`; `B()` ném exception, chỉ `main` có handler. Câu lệnh sau lời gọi `B()` bên trong `A()` có được chạy không?  
**Đáp án:** Không. `A()` đã bị thoát bất thường. `main` tiếp tục sau handler phù hợp của nó nếu handler hoàn tất bình thường.

**Câu 3.** Một `catch` bắt exception rồi `return 5`, bên ngoài cấu trúc còn lệnh `println("X")` trong cùng phương thức. Có in X không?  
**Đáp án:** Không, nếu không có can thiệp thay đổi luồng và câu lệnh đó chỉ nằm sau cấu trúc. Phương thức trả về cho caller; `finally` liên quan vẫn thực hiện.

**Câu 4.** Trong vòng lặp xử lý ba chuỗi, chuỗi thứ hai gây lỗi. `try/catch` ở bên trong thân vòng lặp và handler kết thúc bình thường. Chuỗi thứ ba có được xử lý không?  
**Đáp án:** Có thể có, nếu điều kiện và cấu trúc vòng lặp vẫn cho phép. Ngược lại nếu `try/catch` bao ngoài toàn bộ vòng lặp, lỗi thoát vòng lặp tới handler bên ngoài, nên không tiếp tục phần tử thứ ba tự động.

**Câu 5.** Khi dùng `try (A a = ...; B b = ...)` và thân `try` ném exception, thứ tự đóng tài nguyên là gì?  
**Đáp án:** B rồi A, với các tài nguyên đã khởi tạo thành công; việc đóng diễn ra trước `catch`/`finally` gắn trực tiếp với câu lệnh đó.

**Câu 6.** `catch` bên trong ném một exception mới. `catch` kế tiếp cùng cấp có bắt được không?  
**Đáp án:** Không. Exception mới truyền ra `try` bao ngoài hoặc caller, sau khi hoàn thành cleanup/finally liên quan.

**Câu 7.** `finally` ném exception khác khi một exception cũ đang truyền ra thì sao?  
**Đáp án:** Exception mới từ `finally` có thể thay thế exception cũ như kết quả của cấu trúc, khiến lỗi gốc bị che khuất. Đây là một lý do tránh `throw` mới vô ý trong `finally`.

**Câu 8.** Nếu `try` kết thúc bình thường và có `finally`, câu lệnh sau cấu trúc chạy trước hay sau `finally`?  
**Đáp án:** Sau `finally`, với điều kiện `finally` cũng hoàn tất bình thường.

## 19. Ghi nhớ trọng tâm

Vị trí tiếp tục sau một exception đã được xử lý **phụ thuộc nơi nó được bắt**. Nếu handler hoàn tất bình thường, Java tiếp tục **sau toàn bộ cấu trúc `try/catch/finally` chứa handler ấy**, sau khi dọn dẹp liên quan; những lệnh còn lại của `try` bị ngắt không tự chạy lại. Nếu exception lan từ phương thức con lên caller, phương thức con và các phương thức trung gian đã thoát bất thường không tự tiếp tục. `return`, `break`, `continue`, `throw`, exception mới trong handler/`finally` và `try-with-resources` đều có thể thay đổi đường đi cụ thể.

Để suy luận đúng, luôn theo dõi bốn yếu tố: **điểm ném → handler phù hợp → cleanup/finally → vị trí điều khiển tiếp theo**. Khi cả bốn được xác định, bạn có thể giải thích chính xác vì sao một dòng được chạy, bị bỏ qua, hay chỉ chạy ở tầng gọi bên ngoài.
