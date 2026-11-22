# Thứ tự đóng tài nguyên và `suppressed exception` trong Java

Trong Java I/O, file, socket, stream, reader, writer và nhiều đối tượng truy cập tài nguyên phải được **đóng đúng lúc** để tránh rò rỉ handle, khóa file, kết nối hoặc dữ liệu còn trong bộ đệm. Việc đóng cũng có thể thất bại: `close()` có thể ném exception khi flush, hoàn tất một định dạng hoặc giải phóng tài nguyên.

`try-with-resources` giải quyết hai vấn đề quan trọng:

1. **Đóng tự động theo thứ tự ngược với thứ tự khai báo** các resource đã được khởi tạo thành công.
2. **Giữ lỗi chính (primary exception)** và đưa các lỗi phát sinh khi đóng vào danh sách **suppressed exceptions**, để lỗi gốc không bị che mất.

Hiểu đúng quy tắc này giúp giải thích exception nào được `catch` nhận, vì sao một lần thất bại có nhiều lỗi liên quan, và khi nào không nên khai báo đồng thời wrapper với luồng bên dưới.

## 1. `try-with-resources` quản lý những đối tượng nào?

Một đối tượng dùng được trong phần khai báo resource của `try` khi kiểu của nó implements `java.lang.AutoCloseable`.

- `AutoCloseable` khai báo `void close() throws Exception`; một implementation có thể thu hẹp kiểu exception hoặc không ném checked exception.
- `java.io.Closeable` kế thừa `AutoCloseable` và khai báo `close() throws IOException`, nên thường gặp ở `InputStream`, `OutputStream`, `Reader`, `Writer`.
- `Connection`, `Statement`, `ResultSet` trong JDBC cũng có API đóng tài nguyên, nhưng cơ chế transaction cần xem thêm hợp đồng riêng: `close()` **không được coi mặc định là `commit()`**.
- Một resource tùy biến có thể quản lý lock, file tạm, vùng nhớ hoặc trạng thái ứng dụng; không nhất thiết phải là một luồng I/O.

Ví dụ cú pháp cơ bản:

```java
try (ResourceType resource = openResource()) {
    use(resource);
} // Java tự gọi resource.close() khi rời khỏi khối.
```

Đây là **mẫu cú pháp minh họa**, không phải chương trình độc lập: `ResourceType`, `openResource()` và `use(...)` đại diện cho kiểu/phương thức do ứng dụng định nghĩa.

`try-with-resources` được giới thiệu trong Java 7. Từ Java 9 có thể sử dụng một biến resource đã tồn tại nếu biến đó là `final` hoặc *effectively final*:

```java
// Mã minh họa, reader đã được tạo và không bị gán lại.
BufferedReader reader = createReader();
try (reader) {
    System.out.println(reader.readLine());
}
```

Trong ví dụ này, biến `reader` không được gán lại nên hợp lệ ở Java 17+. Dù biến được tạo bên ngoài phần khai báo `try`, **resource vẫn sẽ bị đóng khi rời khối**; đừng sử dụng cách này nếu caller cần giữ reader mở.

## 2. Thứ tự mở từ trái sang phải, thứ tự đóng từ phải sang trái

Với:

```java
try (A a = openA();
     B b = openB();
     C c = openC()) {
    doWork();
}
```

Java **đánh giá các biểu thức khởi tạo từ trái sang phải**: `a`, rồi `b`, rồi `c`. Khi thoát khối, Java **đóng các resource đã tạo thành công theo thứ tự ngược**: `c.close()`, `b.close()`, `a.close()`.

```text
Khởi tạo:  A  -->  B  -->  C
                           |
Chạy thân try               v
Đóng:      A  <--  B  <--  C
```

Nếu một `close()` ném exception, Java **vẫn cố đóng các resource còn lại** đã được đăng ký trong cùng `try-with-resources`. Cơ chế này khác cách viết `finally` sơ sài, nơi một exception tại lần `close()` đầu tiên có thể làm những lần đóng phía sau bị bỏ qua.

### Ví dụ chạy được: quan sát thứ tự đóng

```java
// CloseOrderDemo.java
public class CloseOrderDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("A");
             Resource second = new Resource("B");
             Resource third = new Resource("C")) {
            System.out.println("work");
        }
    }
}
```

Lưu mã vào `CloseOrderDemo.java`, chạy bằng JDK 17+:

```bash
javac CloseOrderDemo.java
java CloseOrderDemo
```

Stdout chính xác:

```text
open A
open B
open C
work
close C
close B
close A
```

Tương tự khi thân `try` dùng `return`, `break` hoặc ném exception: resource vẫn được đóng trước khi luồng điều khiển thực sự rời khỏi vùng quản lý. Riêng kết quả cuối cùng có thể thay đổi nếu `close()` thất bại (xem phần lỗi).

### Hai ý nghĩa của “thứ tự đóng” cần phân biệt

**Thứ tự giữa các resource khai báo** là quy tắc ngược thứ tự của `try-with-resources`. **Thứ tự đóng các tầng wrapper** lại do logic `close()` của wrapper quyết định.

Ví dụ:

```text
BufferedReader (ngoài cùng)
      |
InputStreamReader
      |
FileInputStream (tầng giữ descriptor)
```

Nếu chỉ khai báo **`BufferedReader` ngoài cùng** là resource, khi nó đóng, các lớp chuẩn tương ứng sẽ chuyển yêu cầu đóng xuống tầng được bọc. Đó là **chuỗi đóng lan truyền** bên trong một lần `close()`, không phải ba biến độc lập được Java tự đóng ngược thứ tự.

Tránh vừa khai báo `FileInputStream`, vừa khai báo các wrapper bọc cùng file khi không cần: wrapper đã đóng tầng dưới; TWR sau đó có thể đóng raw stream thêm lần nữa. Nhiều `Closeable` chuẩn chịu được việc đóng lặp, nhưng không nên giả định mọi implementation tùy biến đều idempotent.

## 3. Primary exception và suppressed exception là gì?

Một khối `try-with-resources` có thể phát sinh lỗi ở **nhiều chỗ**:

1. Khi mở/khởi tạo resource.
2. Khi thực hiện nghiệp vụ bên trong thân `try` (`read`, `write`, parse, xử lý dữ liệu...).
3. Khi đóng một hoặc nhiều resource.

Nếu thân `try` đã thất bại, exception đó thường là **primary exception**: nguyên nhân trực tiếp khiến tác vụ thất bại. Nếu sau đó các lệnh `close()` cũng thất bại, Java không làm mất lỗi chính; nó gắn các lỗi đóng vào `primary.getSuppressed()`.

API để kiểm tra:

```java
Throwable primary = ...; // Mã minh họa: giá trị do catch bắt được.
Throwable[] secondaryFailures = primary.getSuppressed();
```

`getSuppressed()` trả một mảng `Throwable` (có thể rỗng). Các suppressed exceptions **không đồng nghĩa** với cause của exception:

- `getCause()` mô tả quan hệ nguyên nhân được một exception dùng để *wrap* hoặc liên kết một lỗi khác.
- `getSuppressed()` mô tả những lỗi bổ sung bị giữ lại trong quá trình xử lý lỗi/cleanup.
- Cùng một `Throwable` có thể vừa có cause vừa có suppressed exceptions; đó là hai quan hệ **khác nhau**.

Java tự tạo quan hệ suppressed khi thực thi `try-with-resources`; ứng dụng hiếm khi cần gọi thủ công `addSuppressed()` cho các đoạn quản lý tài nguyên thông thường.

## 4. Nếu thân `try` lỗi và `close()` cũng lỗi: lỗi thân là primary

Xem chương trình sau. Cả hai resource đều ném `IOException` khi đóng; thân `try` cũng ném một `IOException` khác.

```java
// BodyAndCloseFailureDemo.java
import java.io.IOException;

public class BodyAndCloseFailureDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            System.out.println("work");
            throw new IOException("work failed");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac BodyAndCloseFailureDemo.java
java BodyAndCloseFailureDemo
```

Stdout:

```text
work
close B
close A
primary=work failed
suppressed=close B failed
suppressed=close A failed
```

Diễn tiến:

1. `A` được tạo, sau đó `B` được tạo.
2. Thân `try` ném `IOException("work failed")`: đây là **primary**.
3. Java gọi `B.close()` trước; nó ném `"close B failed"` và lỗi này được **suppressed** dưới lỗi chính.
4. Java tiếp tục gọi `A.close()`; `"close A failed"` được **suppressed** tiếp.
5. `catch (IOException ex)` bên ngoài khối nhận **`work failed`**, không phải exception của `close()`. `getSuppressed()` cung cấp cả hai lỗi phụ.

Đây là lý do `try-with-resources` đáng tin cậy hơn việc để `finally` ném lỗi mới và làm che mất nguyên nhân ban đầu.

## 5. Nếu thân `try` thành công nhưng nhiều lần `close()` lỗi

Không phải lúc nào primary cũng xuất phát từ thân `try`. Nếu phần nghiệp vụ chạy **bình thường**, nhưng các thao tác đóng thất bại thì:

- Exception đầu tiên được ném trong **trình tự đóng** trở thành primary.
- Các exception từ những lần đóng tiếp theo sẽ là suppressed của primary đó.
- Tất cả resource đã đăng ký vẫn được thử đóng.

### Ví dụ chạy được

```java
// CloseOnlyFailureDemo.java
import java.io.IOException;

public class CloseOnlyFailureDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            System.out.println("work completed");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac CloseOnlyFailureDemo.java
java CloseOnlyFailureDemo
```

Stdout:

```text
work completed
close B
close A
primary=close B failed
suppressed=close A failed
```

`B.close()` chạy trước nên lỗi `"close B failed"` thành primary. Dù xảy ra lỗi đóng `B`, `A.close()` vẫn được gọi; lỗi `"close A failed"` được suppressed. Vì thế **không được kết luận thành công chỉ từ việc thân `try` chạy hết**. Một lần ghi file có thể thất bại ở `close()` khi dữ liệu còn đệm được đẩy ra.

### Bảng quyết định ngắn

| Tình huống | Primary exception | Suppressed exceptions |
| --- | --- | --- |
| Thân `try` thành công, mọi `close()` thành công | Không có | Không có |
| Thân `try` lỗi, mọi `close()` thành công | Lỗi thân `try` | Rỗng |
| Thân `try` lỗi, nhiều `close()` lỗi | Lỗi thân `try` | Các lỗi `close()` theo thứ tự xảy ra |
| Thân `try` thành công, nhiều `close()` lỗi | Lỗi từ `close()` đầu tiên trong **thứ tự đóng** | Những lỗi đóng tiếp theo |
| Khởi tạo một resource lỗi sau khi resource trước đã tạo | Lỗi khởi tạo | Lỗi khi đóng những resource trước, nếu có |

Khi không có primary do thân hoặc khởi tạo, lỗi của `close()` có thể thoát ra dù ứng dụng đã xử lý nghiệp vụ xong.

## 6. Lỗi khởi tạo resource giữa chừng: chỉ đóng những đối tượng đã tạo thành công

Phần khai báo trong `try-with-resources` cũng có thể ném exception. Nếu mở `A` thành công nhưng việc tạo `B` thất bại:

- Thân `try` **không chạy**.
- Chỉ `A` là resource đã được khởi tạo/đăng ký thành công, nên Java cố đóng `A`.
- Lỗi mở `B` là primary; lỗi khi đóng `A` (nếu có) trở thành suppressed.
- Không được cố đóng `B` như thể việc khởi tạo đã hoàn tất.

### Ví dụ chạy được: lỗi lúc mở B

```java
// InitializationFailureDemo.java
import java.io.IOException;

public class InitializationFailureDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    static Resource open(String name) throws IOException {
        System.out.println("open " + name);
        if ("B".equals(name)) {
            throw new IOException("open B failed");
        }
        return new Resource(name);
    }

    public static void main(String[] args) {
        try (Resource a = open("A");
             Resource b = open("B")) {
            System.out.println("body");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac InitializationFailureDemo.java
java InitializationFailureDemo
```

Stdout:

```text
open A
open B
close A
primary=open B failed
suppressed=close A failed
```

Không có dòng `body`, không có `close B`. Biến `b` không nhận một resource thành công để đăng ký. Trong code thật, nếu **bản thân constructor/factory** đã giữ được một tài nguyên nội bộ rồi thất bại *trước khi trả đối tượng*, factory phải tự bảo đảm cleanup phần đã giữ; `try-with-resources` của caller chỉ quản lý các resource **đã khởi tạo và đăng ký xong**.

Đây là một khác biệt quan trọng giữa **tài nguyên tạo thành công rồi lỗi về sau** với **tài nguyên chưa bao giờ được tạo thành công**.

## 7. Nếu resource bằng `null`, hoặc khối có `return`?

Một resource expression hợp lệ có thể có giá trị `null` (dù nên tránh nếu có thể); trong trường hợp đó TWR **bỏ qua lời gọi `close()`** trên giá trị `null`.

```java
// Mã minh họa: Resource là kiểu implement AutoCloseable.
try (Resource first = maybeNullResource();
     Resource second = openResource()) {
    use(second);
}
```

Nếu `first == null`, chỉ `second` được đóng. Nếu `second` lỗi khi khởi tạo, `first` chỉ được đóng nếu nó đã khác `null`.

Ngoài ra, `close()` xảy ra trước khi phương thức hoàn tất `return` của thân `try`. Nếu code chuẩn bị `return` nhưng `close()` ném exception, lời gọi phương thức có thể **kết thúc bằng exception thay vì trả giá trị**. Quy tắc primary/suppressed vẫn áp dụng cho những exception thực sự phát sinh. Vì thế không nên thiết kế phương thức “trả thành công” và bỏ qua lỗi đóng writer nếu tính toàn vẹn của dữ liệu quan trọng.

## 8. Vì sao `finally` viết thủ công dễ làm mất lỗi gốc?

Xét mã minh họa **không nên áp dụng nguyên trạng**:

```java
InputStream input = openInput();
try {
    process(input); // Có thể ném IOException("read failed")
} finally {
    input.close();   // Cũng có thể ném IOException("close failed")
}
```

Mã trên giả định `openInput()` và `process(...)` đã tồn tại. Nếu cả `process(input)` và `input.close()` cùng ném exception, exception từ `close()` trong `finally` có thể **thay thế** exception từ thân `try` khi thoát ra ngoài. Ngoài ra, nếu phải mở nhiều resource thủ công và một lần `close()` thất bại, các lệnh đóng còn lại trong `finally` có thể bị bỏ qua nếu không được bao trong các khối `try` riêng.

Dạng tương đương an toàn hơn:

```java
try (InputStream input = openInput()) {
    process(input);
}
```

TWR giữ `read failed` làm primary và thêm `close failed` vào suppressed. Điều này không có nghĩa lỗi đóng “không quan trọng”; nó được giữ để log và điều tra mà không lấn át lỗi ban đầu.

Nếu phải quản lý resource theo cách đặc biệt (chẳng hạn cleanup thủ công có nhiều bước), hãy chủ động bảo toàn exception gốc và thử cleanup từng bước. `Throwable.addSuppressed(Throwable)` có thể dùng khi thật sự cần tự xây dựng cơ chế tương tự, nhưng phải tránh gắn chính exception đó làm suppressed của chính nó và tránh lạm dụng với flow thông thường.

## 9. Quan hệ giữa wrapper I/O và thứ tự đóng

Một hệ thống I/O thường dùng wrapper:

```java
// Mã minh họa: path là java.nio.file.Path đã xác định.
try (BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(
                Files.newOutputStream(path), StandardCharsets.UTF_8))) {
    writer.write("Xin chào");
}
```

Các import cần thiết là `java.io.BufferedWriter`, `java.io.OutputStreamWriter`, `java.nio.file.Files`, `java.nio.charset.StandardCharsets`. Trong chuỗi này:

1. `Files.newOutputStream(path)` mở luồng byte với tài nguyên file.
2. `OutputStreamWriter` chuyển ký tự sang byte UTF-8.
3. `BufferedWriter` giữ bộ đệm ký tự.
4. TWR đóng **`BufferedWriter` ngoài cùng**; các wrapper chuẩn hoàn tất phần dữ liệu chưa ghi và đóng resource được bọc.

Đây là **một biến TWR nhưng nhiều tầng I/O**. Không cần khai báo riêng `OutputStream` raw rồi thêm `BufferedWriter` vào danh sách resource để mong “đóng đúng thứ tự”; có thể tạo tình huống đóng tầng raw hai lần. Ngược lại, nếu có **hai resource độc lập** (ví dụ luồng đọc và luồng ghi không bọc nhau), hãy khai báo cả hai và nhớ chúng được đóng **ngược thứ tự khai báo**.

### `flush()` khác `close()`

- `flush()` yêu cầu đẩy dữ liệu trong bộ đệm xuống tầng tiếp theo, nhưng resource **vẫn mở**.
- `close()` kết thúc vòng đời và với wrapper ghi chuẩn thường hoàn tất việc flush/encode trước khi đóng tầng dưới; các thao tác này **có thể ném lỗi**.
- `flush()`/`close()` thành công không tự bảo đảm dữ liệu đã được ghi bền vững xuống thiết bị lưu trữ; đó là mức bảo đảm khác của I/O/hệ điều hành.

Một ví dụ gần thực tế: thân `try` ghi qua `BufferedWriter` mà không lỗi; khi thoát khối, `close()` mới buộc dữ liệu còn đệm xuống file. Nếu thao tác ghi thực tế thất bại ở thời điểm này, `close()` có thể ném `IOException`. Đừng chỉ log lỗi từ `writer.write(...)` và giả định phần đóng luôn thành công.

## 10. Ownership: tài nguyên của ai thì người đó quyết định đóng

`try-with-resources` **luôn đóng** những resource mà bạn đưa vào danh sách quản lý khi rời khối. Điều đó chỉ đúng về thiết kế nếu phạm vi mã ấy **sở hữu** chúng.

| Tình huống | Cách xử lý |
| --- | --- |
| Hàm tự mở file để đọc/ghi | Dùng TWR, thường trên wrapper ngoài cùng do hàm tạo |
| Hàm nhận `InputStream` từ caller để xử lý tạm | Không tự đóng nếu hợp đồng không chuyển ownership |
| Dùng `System.in`/`System.out` từ nhiều nơi | Tránh đóng wrapper bọc standard stream trong helper vì `close()` có thể lan xuống stream dùng chung |
| Một `Closeable` dùng chung bởi nhiều tác vụ | Chỉ owner đóng sau khi các tác vụ hoàn tất |
| Một object do caller trả về và yêu cầu hàm đóng | Có thể dùng TWR, nhưng phải ghi rõ hợp đồng chuyển quyền sở hữu |

Ví dụ minh họa:

```java
// Hàm mượn reader: caller quản lý vòng đời.
static String firstLine(BufferedReader borrowed) throws IOException {
    return borrowed.readLine();
}
```

Không đưa `borrowed` vào `try (borrowed)` trong helper trừ khi được phép đóng. Ngược lại, với resource tạo nội bộ, TWR giúp cleanup dù có lỗi.

**Lưu ý đối với transaction:** Đóng `Connection` hoặc session truy cập dữ liệu có thể giải phóng tài nguyên, nhưng xử lý commit/rollback và lỗi của chúng phải tuân theo hợp đồng API. Không coi quy tắc tự động đóng của TWR là cơ chế commit giao dịch.

## 11. `AutoCloseable` và `Closeable`: phạm vi exception

Hai interface liên quan nhưng khác chữ ký:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

```java
public interface Closeable extends AutoCloseable {
    void close() throws IOException;
}
```

Đây là **chữ ký rút gọn để giải thích**, không phải mã cần tự định nghĩa lại trong dự án.

Vì `AutoCloseable.close()` có thể khai báo `Exception`, đoạn code dùng một resource `AutoCloseable` tổng quát có thể cần `catch (Exception)` hoặc `throws Exception`. `Closeable.close()` giới hạn checked exception ở `IOException`, thuận lợi khi xử lý Java I/O. Nếu phương thức `close()` cụ thể không khai báo checked exception, compiler có thể không yêu cầu `throws/catch` chỉ cho thao tác đóng.

Tài liệu `AutoCloseable` **không đòi hỏi mọi implementation đều idempotent**. Tài liệu `Closeable` có hợp đồng đóng lại không gây hiệu lực mới, nhưng đừng suy điều đó cho một wrapper tự viết chỉ implement `AutoCloseable`. Tài nguyên tùy biến cần định nghĩa rõ hành vi đóng nhiều lần, trạng thái sau khi đóng và exception khi cleanup.

### Exception có thể bị suppression không?

Thông thường, exception sinh ra khi đóng sẽ được thêm vào primary nhờ cơ chế TWR. Tuy nhiên, lớp `Throwable` có constructor chuyên biệt cho phép **vô hiệu hóa suppression** đối với một instance exception. Vì vậy `getSuppressed()` có thể trống ngay cả khi có quá trình thêm suppressed trong một số cấu hình khác thường. Với `IOException` và những exception thông dụng trong ví dụ, suppression được bật như bình thường.

Đó là ngoại lệ nâng cao, không làm thay đổi quy tắc sử dụng `try-with-resources` của Java I/O.

## 12. Ghi log, bắt lỗi và kiểm thử đúng cách

### `catch` bên ngoài TWR mới thấy lỗi đóng

Một cấu trúc điển hình:

```java
try (BufferedReader reader = openReader()) {
    consume(reader);
} catch (IOException e) {
    log(e);
}
```

Đây là mã minh họa với `openReader()`, `consume()` và `log()` do ứng dụng cung cấp. Khi `catch` bao ngoài toàn bộ `try-with-resources`, nó nhận cả lỗi thân `try` lẫn lỗi đóng (tùy loại exception).

Nếu đặt `catch` bên **trong** thân `try` để chỉ bao các thao tác đọc, nó không thể xử lý lỗi đóng xảy ra **sau** khi thân đó kết thúc. Muốn quan sát lỗi cleanup, đặt bộ xử lý ở ngoài vùng đóng hoặc để exception đi lên caller.

### Đừng chỉ xem `getMessage()`

Dùng `printStackTrace()` hoặc logger có khả năng log **nguyên đối tượng `Throwable`** thường giúp hiển thị suppressed exceptions. Nếu hệ thống log chỉ lưu message, hãy duyệt `getSuppressed()`:

```java
// Mã minh họa nằm bên trong catch, với e là Throwable.
System.err.println("primary: " + e);
for (Throwable suppressed : e.getSuppressed()) {
    System.err.println("suppressed: " + suppressed);
}
```

Khi cần điều tra, phân biệt lỗi đọc/ghi ban đầu, lỗi flush/close, lỗi khi mở resource tiếp theo và thứ tự cleanup. Nếu có lỗi đóng lồng nhau trong một wrapper tự viết, suppressed exceptions cũng có thể xuất hiện ở các cấp khác nhau trong cây exception; công cụ log nên giữ cấu trúc Throwable.

### Bộ test tối thiểu

1. Mở và đóng ba resource không lỗi: kiểm tra thứ tự mở trái→phải và đóng phải→trái.
2. Thân `try` ném exception, tất cả `close()` thành công: kiểm tra primary là lỗi thân.
3. Thân `try` lỗi và hai `close()` lỗi: kiểm tra primary vẫn là lỗi thân, suppressed đủ hai lỗi đóng.
4. Thân `try` thành công nhưng hai `close()` lỗi: kiểm tra lỗi đóng đầu tiên là primary, lỗi còn lại suppressed.
5. Tạo `A` thành công, tạo `B` thất bại: kiểm tra thân không chạy, `A` đóng và lỗi đóng `A` là suppressed.
6. Resource `null`: xác minh không có lời gọi `close()` trên null.
7. Wrapper writer có bộ đệm: bảo đảm đóng wrapper ngoài cùng hoàn tất dữ liệu và lỗi đóng được nhận diện.
8. Caller sở hữu stream: xác minh helper không đóng resource ngoài phạm vi quyền sở hữu.

## 13. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ thứ tự đóng giống thứ tự khai báo | Dễ hiểu sai luồng cleanup | TWR đóng **ngược thứ tự khai báo**. |
| Nghĩ `close()` thất bại sẽ khiến các resource còn lại không được thử đóng | Bỏ qua cơ chế TWR | TWR vẫn thử đóng các resource còn lại đã khởi tạo. |
| Nghĩ mọi lỗi đóng đều là primary | Mất ý nghĩa lỗi nghiệp vụ | Khi thân/khởi tạo đã có lỗi, close failures thường được **suppressed**. |
| Chỉ đọc `getCause()` để tìm mọi lỗi | Bỏ sót suppressed errors | Kiểm tra cả `getSuppressed()`. |
| Dùng `finally` đơn giản để đóng rồi ném lỗi khác | Có thể che mất lỗi thân `try` | Ưu tiên TWR. |
| Khai báo wrapper và luồng raw cùng là resource dù wrapper đóng raw | Đóng lặp và khó quản lý ownership | TWR trên wrapper ngoài cùng khi nó sở hữu nguồn. |
| Đóng một reader do caller truyền vào | Làm hỏng luồng dùng chung | Chỉ đóng resource mình sở hữu hoặc đã nhận chuyển ownership. |
| Cho rằng thân `try` thành công là ghi file thành công | Lỗi có thể phát sinh lúc flush/close | Xử lý lỗi đóng và quan sát exception. |
| Cho rằng `close()` cũng là `commit()` | Có thể sai ngữ nghĩa giao dịch | Dùng API transaction theo hợp đồng. |
| Chỉ log `exception.getMessage()` | Không thấy các lỗi suppressed | Log nguyên `Throwable` hoặc duyệt suppressed. |

## 14. Tự kiểm tra

**Câu 1.** `try (A a = ...; B b = ...; C c = ...)` đóng theo thứ tự nào khi cả ba đã tạo thành công?

**Đáp án:** `c.close()`, `b.close()`, `a.close()`.

**Câu 2.** Thân `try` ném `IOException("body")`, `B.close()` rồi `A.close()` đều ném lỗi. `catch` nhận primary nào?

**Đáp án:** Lỗi `"body"`; lỗi đóng `B`, `A` nằm trong `getSuppressed()` theo thứ tự phát sinh.

**Câu 3.** Thân `try` thành công, `B.close()` ném lỗi rồi `A.close()` cũng ném lỗi. Lỗi nào là primary?

**Đáp án:** Lỗi đóng `B`, vì B được đóng trước; lỗi đóng A suppressed dưới lỗi B.

**Câu 4.** Tạo A xong nhưng tạo B thất bại. B có được tự động đóng không?

**Đáp án:** Không có B được khởi tạo thành công để đóng; Java đóng A, có thể ghi lỗi đóng A vào suppressed của lỗi mở B.

**Câu 5.** `getCause()` và `getSuppressed()` có cùng ý nghĩa không?

**Đáp án:** Không. Cause diễn tả quan hệ nguyên nhân/wrapping; suppressed giữ những lỗi bổ sung xảy ra trong cleanup hoặc các trường hợp ứng dụng chủ động bổ sung.

**Câu 6.** `BufferedWriter` bọc `OutputStreamWriter` bọc `FileOutputStream`. Khi hàm sở hữu cả chuỗi, khai báo tài nguyên nào trong TWR?

**Đáp án:** Thường chỉ cần writer **ngoài cùng**, nếu close của những wrapper chuẩn lan xuống và đóng các tầng bên dưới.

**Câu 7.** Helper chỉ mượn `InputStream` của caller thì có đưa nó vào TWR không?

**Đáp án:** Không, trừ khi hợp đồng giao quyền đóng cho helper.

**Câu 8.** Vì sao cần quan tâm đến lỗi `close()` dù `write()` không ném lỗi?

**Đáp án:** Writer có thể còn dữ liệu trong buffer hoặc trạng thái mã hóa; việc flush/hoàn tất khi đóng có thể mới làm lỗi I/O xuất hiện.

**Ghi nhớ:** **TWR khởi tạo từ trái sang phải và đóng từ phải sang trái.** Nếu đã có lỗi ở thân `try` hoặc lúc khởi tạo, các lỗi `close()` được giữ dưới dạng **suppressed exceptions** (trong trường hợp suppression thông thường). Nếu thân thành công và nhiều lần đóng lỗi, **lỗi đóng xảy ra đầu tiên** là primary, những lỗi đóng sau là suppressed. Đóng đúng resource mình sở hữu và luôn xem cả `getSuppressed()` khi điều tra thất bại.
