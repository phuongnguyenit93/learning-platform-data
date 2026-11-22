# Khối `catch` đầu tiên phù hợp được thực thi trong Java

Khi một ngoại lệ phát sinh trong khối `try`, Java tìm một nhánh `catch` có thể nhận **đối tượng ngoại lệ thực tế**. Với các `catch` thuộc cùng một `try`, Java xét chúng **từ trên xuống dưới theo thứ tự khai báo** và chỉ thực thi **nhánh đầu tiên có kiểu tương thích**. Khi đã chọn được nhánh này, Java không chạy tiếp những `catch` còn lại của cùng cấu trúc, ngay cả khi kiểu của chúng cũng có thể bắt được đối tượng ấy.

Đây là quy tắc của Java Language Specification (JLS) §14.20.1. Nắm vững nó giúp viết đúng thứ tự bắt ngoại lệ cha/con, dự đoán luồng xử lý, nhận ra mã `catch` không thể tới, và tránh nhầm một ngoại lệ được ném lại từ `catch` với ngoại lệ mới được xử lý bởi nhánh kế bên.

## 1. Nhìn ngay vào quy tắc chọn nhánh

```java
try {
    throw new NumberFormatException("not a number");
} catch (NumberFormatException ex) {
    System.out.println("specific");
} catch (IllegalArgumentException ex) {
    System.out.println("general");
}
```

Đây là đoạn mã hợp lệ khi đặt trong một phương thức. Kết quả duy nhất là:

```text
specific
```

`NumberFormatException` kế thừa `IllegalArgumentException`, nên về mặt quan hệ kiểu **cả hai `catch` đều có thể tiếp nhận** ngoại lệ này. Tuy nhiên, nhánh `catch (NumberFormatException ex)` xuất hiện đầu tiên nên được chọn. `catch (IllegalArgumentException ex)` không chạy trong lần ném này.

Một cách diễn đạt chính xác:

1. Đánh giá và thực thi phần `try`.
2. Nếu `try` kết thúc bình thường, **không `catch` nào chạy**.
3. Nếu `try` hoàn tất đột ngột vì ném đối tượng ngoại lệ `V`, xét các `catch` của chính cấu trúc `try` này **theo thứ tự trái sang phải trong đặc tả**, tương ứng thứ tự từ trên xuống dưới trong mã nguồn.
4. Chọn `catch` **đầu tiên** có kiểu bắt được tương thích với **kiểu thực tế tại runtime** của `V`, rồi gán `V` cho tham số `catch`.
5. Nếu khối `catch` được chọn xử lý và hoàn tất bình thường, toàn bộ `try-catch` có thể hoàn tất bình thường. Nếu nó lại `throw` hay `return`, cấu trúc bao ngoài tiếp tục theo lý do hoàn tất mới đó.
6. Nếu không có `catch` phù hợp, ngoại lệ **tiếp tục lan truyền** ra ngữ cảnh bên ngoài.

**Một lần ném ngoại lệ không khiến tất cả các nhánh `catch` tương thích cùng chạy.** Các `catch` là những phương án xử lý thay thế nhau, không phải các bộ xử lý liên tiếp.

## 2. Kiểu thực tế, quan hệ kế thừa và tính tương thích

Ngoại lệ được ném phải là một đối tượng thuộc `Throwable` hoặc lớp con. Để một `catch (T ex)` thông thường bắt được đối tượng `V`, kiểu runtime của `V` phải gán được cho kiểu `T`. Một nhánh dùng kiểu cha có thể bắt một đối tượng kiểu con.

Ví dụ sơ đồ kế thừa tiêu biểu:

```text
Throwable
├── Error
│   └── OutOfMemoryError
└── Exception
    ├── IOException
    │   ├── FileNotFoundException
    │   └── EOFException
    └── RuntimeException
        └── IllegalArgumentException
            └── NumberFormatException
```

Cây này chỉ thể hiện những lớp phục vụ bài học. Từ cây trên:

| Đối tượng đang được ném | `catch` có thể tiếp nhận | `catch` không phù hợp |
| --- | --- | --- |
| `new NumberFormatException(...)` | `NumberFormatException`, `IllegalArgumentException`, `RuntimeException`, `Exception`, `Throwable` | `IOException` |
| `new FileNotFoundException(...)` | `FileNotFoundException`, `IOException`, `Exception`, `Throwable` | `RuntimeException` |
| `new EOFException(...)` | `EOFException`, `IOException`, `Exception`, `Throwable` | `FileNotFoundException` |
| `new OutOfMemoryError(...)` | `OutOfMemoryError`, `Error`, `Throwable` | `Exception` |

Lưu ý: bảng mô tả **khả năng tương thích kiểu**, không phải lời khuyên bắt `OutOfMemoryError` trong ứng dụng. Lỗi thuộc nhánh `Error` thường cần để lan truyền và điều tra ở cấp phù hợp.

Nếu trong `try` có:

```java
IOException failure = new FileNotFoundException("settings.ini");
throw failure;
```

thì đối tượng được ném thực sự là `FileNotFoundException`. Bất kể biến `failure` được khai báo kiểu `IOException`, việc chọn `catch` lúc chạy dựa vào **lớp thực tế của đối tượng**, không chỉ dựa vào kiểu khai báo của biến. Trình biên dịch vẫn dùng thông tin kiểu khai báo và phân tích ngoại lệ để kiểm tra những nhánh `catch` nào hợp lệ trong mã.

## 3. Phải đặt ngoại lệ cụ thể trước ngoại lệ tổng quát

Trong cùng một chuỗi `catch`, nếu kiểu của một nhánh là lớp con của kiểu ở nhánh khác, đặt nhánh **con trước cha**. Nhánh cha đặt trước sẽ bắt luôn các đối tượng kiểu con, khiến nhánh con sau đó không bao giờ được chọn.

**Đúng:**

```java
try {
    readConfig();
} catch (FileNotFoundException ex) {
    System.out.println("Không tìm thấy tệp");
} catch (IOException ex) {
    System.out.println("Lỗi I/O khác");
}
```

Đây là đoạn minh họa bên trong phương thức, giả sử `readConfig()` được khai báo `throws IOException` và `FileNotFoundException` đã được import từ `java.io`. Nhánh đầu xử lý trường hợp chuyên biệt; nhánh sau là dự phòng cho những `IOException` còn lại.

**Sai — không biên dịch:**

```java
try {
    readConfig();
} catch (IOException ex) {
    System.out.println("I/O");
} catch (FileNotFoundException ex) {
    System.out.println("Không tìm thấy tệp");
}
```

Ở đoạn sai, `IOException` nằm trước và là lớp cha của `FileNotFoundException`, nên mọi `FileNotFoundException` đều bị nhánh đầu bắt. Trình biên dịch Java bác bỏ nhánh sau với chẩn đoán kiểu **exception FileNotFoundException has already been caught**. Đây là lỗi biên dịch, không phải một nhánh chỉ đơn giản bị bỏ qua khi chạy.

Quy tắc áp dụng tương tự cho:

- `catch (Exception ex)` đặt trước `catch (IOException ex)`.
- `catch (RuntimeException ex)` đặt trước `catch (IllegalArgumentException ex)`.
- `catch (IllegalArgumentException ex)` đặt trước `catch (NumberFormatException ex)`.
- `catch (Throwable ex)` đặt trước bất kỳ kiểu `Throwable` con nào.

Thứ tự **không bắt buộc phải chuyên biệt hơn** giữa hai lớp *không có quan hệ cha/con*, ví dụ `IOException` và `SQLException`; trong trường hợp đó, mỗi nhánh bắt các kiểu khác nhau. Tuy nhiên, nên bố trí chúng theo thứ tự dễ đọc và ý nghĩa nghiệp vụ.

## 4. Chương trình Java 17+: kiểm chứng `catch` đầu tiên phù hợp

Lưu thành `CatchOrderDemo.java`:

```java
import java.io.EOFException;
import java.io.FileNotFoundException;
import java.io.IOException;

public class CatchOrderDemo {
    static void fetch(int code) throws IOException {
        switch (code) {
            case 0 -> throw new FileNotFoundException("profile.txt");
            case 1 -> throw new EOFException("partial data");
            case 2 -> throw new IllegalArgumentException("invalid code");
            default -> System.out.println("fetch=OK");
        }
    }

    public static void main(String[] args) {
        for (int code = 0; code < 4; code++) {
            try {
                fetch(code);
            } catch (FileNotFoundException ex) {
                System.out.println("file=" + ex.getMessage());
            } catch (IOException ex) {
                System.out.println("io=" + ex.getClass().getSimpleName());
            } catch (RuntimeException ex) {
                System.out.println("runtime=" + ex.getMessage());
            }

            System.out.println("done=" + code);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CatchOrderDemo.java
java CatchOrderDemo
```

Kết quả:

```text
file=profile.txt
done=0
io=EOFException
done=1
runtime=invalid code
done=2
fetch=OK
done=3
```

Diễn giải từng lượt:

1. `code = 0`: `fetch()` ném `FileNotFoundException`. Nhánh `catch (FileNotFoundException)` được chọn đầu tiên dù `IOException` cũng tương thích.
2. `code = 1`: `fetch()` ném `EOFException`, vốn là lớp con của `IOException` nhưng không phải `FileNotFoundException`. Nhánh đầu không phù hợp, nhánh `IOException` chạy.
3. `code = 2`: `IllegalArgumentException` thuộc `RuntimeException`; hai nhánh I/O không phù hợp nên nhánh `RuntimeException` chạy. Việc `fetch()` chỉ khai báo `throws IOException` không ngăn nó ném unchecked exception.
4. `code = 3`: không có ngoại lệ, chỉ in `fetch=OK`; toàn bộ ba `catch` được bỏ qua.

Dòng `done=...` xuất hiện sau mọi lượt vì mỗi `catch` đã chọn hoàn tất bình thường. Nếu một `catch` ném lại lỗi hoặc có ngoại lệ khác chưa được xử lý, dòng đó không nhất thiết chạy.

## 5. Không có ngoại lệ thì không chạy `catch` nào

`catch` không hoạt động như nhánh `else` bắt buộc sau mỗi `try`. Nếu toàn bộ `try` hoàn tất bình thường, Java bỏ qua các `catch`:

```java
try {
    System.out.println("try complete");
} catch (RuntimeException ex) {
    System.out.println("will not print in this run");
}
System.out.println("after");
```

Đây là đoạn minh họa bên trong phương thức, cho kết quả:

```text
try complete
after
```

`catch (RuntimeException ex)` hợp lệ dù khối `try` không chứa lời gọi ném unchecked exception tường minh. Nhưng không có lỗi runtime nào xảy ra trong lần thực thi này nên nó không chạy.

Nếu đặt `catch (IOException ex)` cho một `try` **không có khả năng ném `IOException` checked** (và không có tài nguyên có thể ném lỗi đó khi đóng), trình biên dịch có thể bác bỏ với thông báo `exception IOException is never thrown in body of corresponding try statement`. Việc `catch` có hợp lệ lúc biên dịch và việc nó có được chọn ở runtime là hai câu hỏi khác nhau.

## 6. Một `catch` đã chọn không “chạy tiếp” các `catch` phía dưới

Xét đoạn mã:

```java
try {
    throw new IllegalArgumentException("bad");
} catch (IllegalArgumentException ex) {
    System.out.println("first");
} catch (RuntimeException ex) {
    System.out.println("second");
} catch (Exception ex) {
    System.out.println("third");
}
System.out.println("after");
```

Kết quả:

```text
first
after
```

Ba nhánh đều có thể nhận đối tượng `IllegalArgumentException` theo quan hệ kế thừa, nhưng chỉ nhánh đầu chạy. Sau khi nhánh đó hoàn tất bình thường, luồng chuyển đến câu lệnh **sau toàn bộ `try-catch`**, không chuyển sang `catch` thứ hai.

Điều này khác với một số cấu trúc `switch` truyền thống có thể *fall through*. Các khối `catch` không có cơ chế fall-through; không cần viết `break` để dừng chuỗi `catch`.

Nếu muốn xử lý chung cho nhiều kiểu ngoại lệ, có thể viết **multi-catch** hoặc chuyển logic chung vào một phương thức, thay vì mong nhiều nhánh `catch` cùng chạy.

## 7. `catch` mới ném ngoại lệ: nhánh kế bên có bắt được không?

**Không.** Các `catch` của một `try` chỉ chọn nhánh để xử lý ngoại lệ từ phần `try` (bao gồm các quy tắc mở rộng với tài nguyên). Nếu một nhánh `catch` đã được chọn rồi **ném ngoại lệ mới**, các nhánh `catch` còn lại **cùng cấp** không được thử tiếp cho ngoại lệ mới đó.

Ví dụ:

```java
try {
    throw new IllegalArgumentException("input");
} catch (IllegalArgumentException ex) {
    throw new IllegalStateException("translated", ex);
} catch (IllegalStateException ex) {
    System.out.println("not selected for the new error");
}
```

Đây là **đoạn minh họa cú pháp hợp lệ** trong một phương thức, nhưng khi chạy ngoại lệ `IllegalStateException` được truyền ra ngoài cấu trúc `try-catch` nếu không có bộ xử lý ở tầng bao ngoài. Nhánh `catch (IllegalStateException)` chỉ là phương án cho lỗi được ném từ `try`, không xử lý lỗi mới của nhánh `catch` trước.

Trong thực tế, chuyển đổi ngoại lệ ở tầng xử lý có thể cần thiết; nên gắn `cause` để giữ nguyên nhân ban đầu, như constructor `new IllegalStateException("translated", ex)` ở trên.

## 8. Chương trình Java 17+: `catch` lồng nhau và ngoại lệ được chuyển đổi

Lưu thành `NestedCatchDemo.java`:

```java
import java.io.IOException;

public class NestedCatchDemo {
    static void process() {
        try {
            try {
                throw new IOException("disk");
            } catch (IOException ex) {
                System.out.println("inner=" + ex.getMessage());
                throw new IllegalStateException("service failed", ex);
            } catch (RuntimeException ex) {
                System.out.println("unreached sibling");
            } finally {
                System.out.println("inner-finally");
            }
        } catch (IllegalStateException ex) {
            System.out.println("outer=" + ex.getMessage());
            System.out.println("cause=" + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("after");
    }

    public static void main(String[] args) {
        process();
    }
}
```

```bash
javac -encoding UTF-8 NestedCatchDemo.java
java NestedCatchDemo
```

Kết quả:

```text
inner=disk
inner-finally
outer=service failed
cause=IOException
after
```

Luồng xử lý:

1. Phần `try` bên trong ném `IOException`; nhánh `catch (IOException)` bên trong phù hợp và được thực thi.
2. Nhánh này tạo `IllegalStateException` mới, giữ `IOException` làm `cause`.
3. Nhánh `catch (RuntimeException)` kế bên **không** được chạy cho lỗi vừa ném trong nhánh `catch` đầu.
4. `finally` của cấu trúc bên trong vẫn chạy và hoàn tất bình thường.
5. Ngoại lệ `IllegalStateException` truyền ra cấu trúc `try` bên ngoài; `catch (IllegalStateException)` phía ngoài nhận nó.
6. Nhánh ngoài hoàn tất bình thường, nên `after` được in.

Ví dụ chứng minh hai quy tắc đồng thời: **chỉ một `catch` được chọn trong mỗi cấu trúc `try`**, và các cấu trúc `try-catch` lồng nhau có thể xử lý **những đối tượng ngoại lệ ở các thời điểm khác nhau**.

## 9. Tìm `catch` theo từng phạm vi `try`, không quét tất cả `catch` trong chương trình

Từ “đầu tiên” chỉ có nghĩa khi đã xác định **cấu trúc `try` đang xét**. Java tìm bộ xử lý gần nhất trên đường lan truyền của ngoại lệ. Các `catch` ở cùng một `try` được xét theo thứ tự khai báo; nếu không có nhánh phù hợp, ngoại lệ tiếp tục đi ra ngoài và có thể gặp `try-catch` ở phương thức gọi.

```text
caller(): try {
    service(): try {
        repository(): throw FileNotFoundException
    } catch (IOException) {
        // chọn ở service() nếu lỗi tới đây và catch phù hợp
    }
} catch (Exception) {
    // chỉ nhận nếu ngoại lệ đi qua service() mà chưa được xử lý
}
```

Đây là sơ đồ luồng gọi để giải thích, **không phải cú pháp Java**.

Một `catch (Exception)` trong `try` bao quanh gần hơn có thể được chọn trước một `catch (FileNotFoundException)` ở tầng gọi xa hơn. Không có thuật toán tìm “lớp bắt cụ thể nhất trong toàn ứng dụng”. Java ưu tiên **phạm vi xử lý** trước, rồi chọn **nhánh đầu tiên tương thích** bên trong phạm vi đó.

Tương tự, một đối tượng ngoại lệ có thể đi từ `repository()` lên `service()` rồi `controller()` nếu không có `catch` thích hợp ở tầng thấp. Mệnh đề `throws` mô tả nghĩa vụ checked exception lúc biên dịch; nó không thay đổi quy tắc lựa chọn nhánh `catch` lúc chạy.

## 10. `multi-catch` có nhiều kiểu nhưng chỉ một khối xử lý

Từ Java 7, cú pháp `catch (IOException | SQLException ex)` cho phép **một nhánh `catch` nhận một trong nhiều kiểu**. Về lựa chọn bộ xử lý, đây **vẫn là một nhánh `catch` duy nhất**. Không có chuyện Java thực thi riêng từng nhánh con vì thấy toán tử `|`.

Lưu thành `MultiCatchDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultiCatchDemo {
    static void work(int mode) throws IOException, SQLException {
        if (mode == 0) {
            throw new IOException("disk");
        }
        if (mode == 1) {
            throw new SQLException("database");
        }
        System.out.println("work=OK");
    }

    public static void main(String[] args) {
        for (int mode = 0; mode < 3; mode++) {
            try {
                work(mode);
            } catch (IOException | SQLException ex) {
                System.out.println("handled="
                        + ex.getClass().getSimpleName() + ":" + ex.getMessage());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 MultiCatchDemo.java
java MultiCatchDemo
```

Kết quả:

```text
handled=IOException:disk
handled=SQLException:database
work=OK
```

Một số giới hạn:

- Các kiểu trong cùng `multi-catch` không được có quan hệ lớp cha/con với nhau. Ví dụ `catch (FileNotFoundException | IOException ex)` **không hợp lệ**, vì `FileNotFoundException extends IOException`.
- Tham số `ex` trong `multi-catch` là **implicitly final**: không thể gán lại biến đó.
- Có thể gọi các thành viên chung của các kiểu, chẳng hạn `ex.getMessage()`.
- Nếu các lỗi cần chiến lược xử lý khác nhau, viết các `catch` riêng biệt sẽ dễ hiểu hơn.
- Nếu có `catch` khác phía sau `multi-catch`, quy tắc **nhánh đầu tiên tương thích** vẫn áp dụng.

## 11. `catch` và checked exception được trình biên dịch kiểm tra riêng

Trình biên dịch Java kiểm tra các loại checked exception mà một `try` có thể ném. Nó cũng kiểm tra những trường hợp nhánh `catch` bị che hoàn toàn bởi nhánh trước.

So sánh ba trường hợp:

| Mã | Trạng thái | Giải thích |
| --- | --- | --- |
| `catch (IOException)` rồi `catch (FileNotFoundException)` | Không hợp lệ | Nhánh đầu đã bao phủ mọi `FileNotFoundException`. |
| `catch (FileNotFoundException)` rồi `catch (IOException)` | Hợp lệ khi `try` có khả năng ném các checked exception liên quan | Nhánh riêng xử lý lỗi không có tệp; nhánh chung xử lý phần còn lại. |
| `catch (IOException)` rồi `catch (SQLException)` | Có thể hợp lệ | Hai kiểu không thuộc quan hệ cha/con; `try` phải có khả năng ném những checked exception đó tương ứng. |

Một `try` chỉ có lệnh `System.out.println("ok")` không cho phép tự do thêm `catch (java.io.IOException)` khi không có thao tác nào có thể ném `IOException` checked. Ngược lại, nhánh bắt `RuntimeException` hay `Exception` có những quy tắc cho phép rộng hơn vì chúng bao gồm unchecked exceptions; không suy ra rằng mọi kiểu `catch` đều yêu cầu một câu lệnh `throw` tường minh.

**Thứ tự và tính hợp lệ của `catch` được kiểm tra lúc biên dịch; chọn nhánh cho đối tượng cụ thể xảy ra khi chạy.** Đây là hai bước khác nhau. Kết quả compile-time còn phụ thuộc chữ ký `throws` của phương thức được gọi, không chỉ vào những gì bạn đã quan sát trong một bộ dữ liệu thử.

## 12. `finally` chạy sau khi chọn `catch`, không phải nhánh `catch` kế tiếp

Trong `try-catch-finally`, nếu có một ngoại lệ trong `try`, Java chọn nhánh `catch` phù hợp như trên, thực hiện khối `catch`, sau đó thực thi `finally` theo quy tắc của ngôn ngữ trước khi hoàn tất việc ra khỏi cấu trúc.

```java
try {
    throw new IllegalArgumentException("invalid");
} catch (IllegalArgumentException ex) {
    System.out.println("caught");
} catch (RuntimeException ex) {
    System.out.println("not used");
} finally {
    System.out.println("cleanup");
}
System.out.println("after");
```

Đoạn minh họa trong một phương thức in:

```text
caught
cleanup
after
```

`finally` không phải một `catch` bổ sung và không phụ thuộc nhánh `catch` nào đã chọn; nó có nhiệm vụ thực thi mã dọn dẹp theo quy tắc thông thường. Nếu khối `catch` kết thúc đột ngột do `throw` hoặc `return`, `finally` vẫn được chạy trước khi lý do đó tiếp tục lan đi, miễn chương trình thực sự đi qua cơ chế xử lý Java bình thường.

**Cẩn thận:** nếu `finally` tự ném ngoại lệ hoặc `return`, lý do mới có thể thay thế lỗi/giá trị đang chờ. Trong mã ứng dụng, nên tránh `return` trong `finally` và tránh làm mất ngoại lệ chính trong thao tác dọn dẹp.

## 13. `try-with-resources`: lỗi đóng tài nguyên được xử lý trước khi chọn `catch`

Với `try-with-resources`, tài nguyên sẽ được tự động đóng. Nếu phần thân `try` ném lỗi và `close()` cũng ném lỗi, ngoại lệ từ `close()` thường được đưa vào `getSuppressed()` của ngoại lệ chính. Khi đi tới các nhánh `catch`, **kiểu ngoại lệ chính** quyết định nhánh được chọn.

Ví dụ Java 17+, lưu thành `ResourceCatchDemo.java`:

```java
import java.io.IOException;

public class ResourceCatchDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new IllegalStateException("work");
        } catch (IOException ex) {
            System.out.println("io=" + ex.getMessage());
        } catch (IllegalStateException ex) {
            System.out.println("selected=" + ex.getMessage());
            System.out.println("suppressed="
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 ResourceCatchDemo.java
java ResourceCatchDemo
```

Kết quả:

```text
selected=work
suppressed=close
```

Dù `close()` ném `IOException`, lỗi chính của lần thực thi là `IllegalStateException("work")` phát sinh trong phần thân `try`. `IOException` bị đính kèm làm suppressed, không trở thành một ngoại lệ chính riêng để kích hoạt nhánh `catch (IOException)`. Vì vậy nhánh `catch (IllegalStateException)` được chọn.

Nếu phần thân `try` hoàn tất bình thường nhưng `close()` ném `IOException`, lỗi khi đóng có thể trở thành ngoại lệ chính và nhánh `catch (IOException)` khi đó được chọn. Đây là lý do cần hiểu đúng mối quan hệ giữa lỗi chính và lỗi suppressed thay vì chỉ đếm số ngoại lệ xảy ra.

## 14. Vì sao thường nên bắt các kiểu cụ thể?

Mã sau thường khó bảo trì:

```java
try {
    performBusinessOperation();
} catch (Exception ex) {
    System.out.println("Something went wrong");
}
```

Đây là đoạn minh họa với `performBusinessOperation()` được định nghĩa ở nơi khác. `catch (Exception)` có thể nhận nhiều loại checked exception và `RuntimeException`, khiến chương trình dùng chung một cách xử lý cho những tình huống rất khác nhau. Nó cũng **không bắt `Error`** vì `Error` là nhánh khác của `Throwable`.

Cách thiết kế phù hợp hơn thường là:

1. Xác định những lỗi có thể xử lý tại tầng này (ví dụ `FileNotFoundException` để báo thiếu cấu hình).
2. Đặt `catch` của tình huống cụ thể trước, rồi đến kiểu cha phù hợp nếu cần xử lý rộng hơn.
3. Chỉ dùng `catch (Exception)` tại ranh giới có yêu cầu xử lý lỗi tập trung rõ ràng, và không giả định đã phục hồi được trạng thái ứng dụng.
4. Giữ nguyên đối tượng lỗi hoặc `cause` khi dịch ngoại lệ; không chỉ ghi `ex.getMessage()` rồi bỏ mất stack trace nếu cần điều tra.
5. Không dùng `catch (Throwable)` như một cách “chặn mọi sự cố” trong nghiệp vụ thông thường vì nó còn nhận cả những `Error` nghiêm trọng.

Cần nhớ rằng **không có quy tắc “cứ kiểu càng cụ thể thì JVM sẽ tự ưu tiên”**. JVM xét các nhánh theo thứ tự mã nguồn. Chính lập trình viên phải sắp xếp để các nhánh chuyên biệt được sử dụng đúng.

## 15. Những nhầm lẫn và lỗi thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| “Có ba `catch` tương thích thì cả ba đều chạy.” | Chỉ nhánh đầu tiên phù hợp của cùng `try` được chạy. |
| “JVM tự chọn `catch` cụ thể nhất bất kể thứ tự.” | Java xét thứ tự khai báo; nhánh cha trước nhánh con dẫn tới lỗi biên dịch do che khuất. |
| “Biến được khai báo `IOException` thì ngoại lệ thực tế không thể vào `catch (FileNotFoundException)`.” | Nếu đối tượng runtime là `FileNotFoundException`, nó có thể được nhánh chuyên biệt bắt. |
| “`catch (Exception)` bắt được mọi `Error`.” | Không; `Exception` và `Error` là hai nhánh riêng dưới `Throwable`. |
| “Lỗi ném ra từ `catch` đầu sẽ thử `catch` thứ hai.” | Không; lỗi mới lan ra cấu trúc bên ngoài. |
| “`finally` chạy thay cho một `catch`.” | Không; `finally` có quy tắc thực thi riêng, sau khi khối `try`/`catch` đã được xác định. |
| “Hai kiểu trong `multi-catch` nghĩa là hai `catch` liên tiếp.” | Không; đó là một nhánh có thể nhận một trong các kiểu được khai báo. |
| “Nếu không có ngoại lệ, `catch` cuối là đường mặc định.” | Không có `catch` nào chạy nếu `try` hoàn tất bình thường. |
| “Chỉ xét nhánh `catch` trong cùng phương thức đang lỗi.” | Ngoại lệ có thể lan lên các phương thức gọi cho đến khi gặp bộ xử lý phù hợp. |
| “Lỗi bị suppress khi đóng tài nguyên vẫn tự kích hoạt `catch` theo kiểu riêng.” | Nhánh được chọn theo ngoại lệ chính được ném ra từ cấu trúc `try-with-resources`. |

## 16. Cách tự xác định nhánh nào chạy

Khi đọc một đoạn mã bất kỳ, làm theo bốn bước:

**Bước 1.** Xác định chính xác **đối tượng ngoại lệ đã được ném** và kiểu runtime của nó; xem `cause` và `suppressed` chỉ khi cần truy nguyên, vì chúng không tự trở thành đối tượng đang được `catch` phân loại.

**Bước 2.** Xác định **cấu trúc `try` gần nhất đang bao quanh điểm ném** mà quá trình truyền ngoại lệ đang đi qua. Nếu lỗi xuất phát từ một `catch`, tìm bộ xử lý ở cấu trúc bao ngoài thay vì nhánh `catch` kế bên.

**Bước 3.** Trong cấu trúc `try` đó, đọc từng nhánh `catch` **từ trên xuống**, kiểm tra quan hệ kiểu: kiểu thực tế của lỗi có gán được cho kiểu `catch` này không? Nếu có, dừng tìm tại nhánh đầu tiên.

**Bước 4.** Theo dõi xem nhánh được chọn kết thúc bình thường, `return`, hay `throw` tiếp; sau đó xét `finally` và cấu trúc bao ngoài để xác định lời gọi kết thúc như thế nào.

Ví dụ tư duy:

```java
RuntimeException ex = new NumberFormatException("bad");
try {
    throw ex;
} catch (NumberFormatException caught) {
    System.out.println("A");
} catch (IllegalArgumentException caught) {
    System.out.println("B");
} catch (RuntimeException caught) {
    System.out.println("C");
}
System.out.println("D");
```

Kết quả:

```text
A
D
```

Biến `ex` khai báo kiểu `RuntimeException` nhưng đối tượng thực tế là `NumberFormatException`. Nhánh `A` đầu tiên phù hợp, nhánh `B` và `C` không chạy; cấu trúc `try-catch` hoàn tất bình thường nên in `D`.

## 17. Tự kiểm tra

**Câu 1.** `catch (IOException)` và `catch (Exception)` đều có thể nhận `FileNotFoundException`. Nhánh nào chạy?  
Nhánh `catch` **đầu tiên tương thích theo thứ tự khai báo**. Trong thứ tự vừa nêu, đó là `IOException`.

**Câu 2.** Có thể đặt `catch (Exception)` trước `catch (IOException)` để “ưu tiên ngoại lệ tổng quát” không?  
**Không.** Nhánh `IOException` phía sau bị che hoàn toàn và bị compiler từ chối.

**Câu 3.** Nếu `catch (IOException)` đã bắt lỗi rồi `throw new IllegalStateException(...)`, nhánh `catch (RuntimeException)` kế bên có nhận lỗi mới không?  
**Không.** Ngoại lệ mới cần `catch` của cấu trúc bao ngoài hoặc sẽ tiếp tục truyền lên.

**Câu 4.** `catch (IOException | SQLException ex)` có thực thi hai lần với một lỗi `IOException` không?  
**Không.** Đó là **một** nhánh `catch` duy nhất.

**Câu 5.** `try` hoàn tất bình thường thì nhánh `catch` nào chạy?  
**Không nhánh nào.** Luồng tiếp tục sau cấu trúc `try-catch`, với `finally` được thực thi nếu có.

**Câu 6.** `catch (Exception)` có bắt được `OutOfMemoryError` không?  
**Không.** `OutOfMemoryError` thuộc `Error`. Có thể bắt nó bằng kiểu tương thích như `Error` hoặc `Throwable`, nhưng bắt được không đồng nghĩa có thể phục hồi an toàn.

**Câu 7.** `FileNotFoundException` được lưu trong biến `IOException` rồi ném, `catch (FileNotFoundException)` có thể nhận không?  
**Có.** Chọn bộ xử lý dựa trên kiểu runtime của đối tượng.

**Câu 8.** Phần thân `try-with-resources` ném `IllegalStateException`, còn `close()` ném `IOException` bị suppress. Nhánh `catch (IOException)` có được chọn vì lỗi phụ đó không?  
**Không.** Nhánh xử lý được chọn theo ngoại lệ chính `IllegalStateException` đang được ném.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 21 — §14.20.1: Execution of `try-catch`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.1).
- [JLS 21 — §14.20.2: Execution of `try-finally` and `try-catch-finally`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.2).
- [JLS 21 — §14.20.3: `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3).
- [JLS 21 — §11.2.3: Exception Checking](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2.3).

**Ghi nhớ:** Đối với một `try` đang xử lý ngoại lệ, Java dùng **kiểu thực tế của đối tượng ném ra** và **thứ tự `catch` trong mã nguồn**, chọn đúng **nhánh đầu tiên tương thích**. Đặt kiểu con trước kiểu cha, không trông chờ `catch` sau chạy tiếp, và theo dõi `finally` cũng như `try-catch` bên ngoài khi có ngoại lệ mới.
