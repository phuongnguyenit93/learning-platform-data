# Xử lý lỗi khi khởi tạo một phần tài nguyên với try-with-resources trong Java

## 1. Tại sao khởi tạo dở dang vẫn phải dọn dẹp?

Một thao tác thường cần **nhiều tài nguyên**: mở kết nối cơ sở dữ liệu rồi tạo câu lệnh, mở nguồn đọc rồi tạo bộ giải mã, hoặc cấp phát hai tài nguyên phụ thuộc nhau. Nếu tài nguyên thứ nhất mở thành công nhưng việc tạo tài nguyên thứ hai thất bại, chương trình chưa vào thân `try`. Tuy vậy, tài nguyên thứ nhất **vẫn cần được đóng**.

Từ **Java 7**, `try-with-resources` giải quyết trường hợp này tự động cho các tài nguyên đã được khai báo và khởi tạo thành công trong phần đầu của câu lệnh:

~~~java
try (FirstResource first = openFirst();
     SecondResource second = openSecond(first)) {
    use(first, second);
}
~~~

Đây chỉ là **mã minh họa cấu trúc**; `FirstResource`, `SecondResource`, `openFirst`, `openSecond` và `use` là các tên giả định, không phải một chương trình tự biên dịch. Nếu `openSecond(first)` ném ngoại lệ, Java vẫn gọi `first.close()` (nếu `first` khác `null`), dù `use(...)` chưa từng chạy.

Bài này tập trung vào **xử lý lỗi khi chỉ khởi tạo được một phần dãy tài nguyên**: thứ tự khởi tạo/đóng, ngoại lệ chính (*primary exception*), ngoại lệ bị đè xuống (*suppressed exception*) và giới hạn trách nhiệm dọn dẹp khi một **factory/constructor** tự thất bại giữa chừng.

**Phạm vi phiên bản:** Đây là cơ chế còn áp dụng trong Java hiện đại. Ví dụ sử dụng **Java 21**, không yêu cầu chạy JDK 7 cũ, API lỗi thời hay tính năng preview.

## 2. Quy tắc của Java khi khởi tạo nhiều tài nguyên

Với cú pháp:

~~~java
try (Resource a = createA();
     Resource b = createB();
     Resource c = createC()) {
    doWork();
}
~~~

Giả sử `Resource` triển khai `AutoCloseable`; các tên phương thức ở đây chỉ nhằm minh họa. Theo Java Language Specification `14.20.3`:

1. **Khởi tạo từ trái sang phải.** Java gọi `createA()`, rồi `createB()`, rồi `createC()`. Chỉ tiếp tục khi biểu thức trước hoàn thành bình thường.
2. **Chỉ vào thân `try` sau khi tất cả biểu thức khởi tạo hoàn thành bình thường.** Nếu `createB()` ném ngoại lệ, `createC()` **không được gọi** và `doWork()` **không chạy**.
3. **Các tài nguyên đã khởi tạo trước đó được tự động đóng.** Nếu `a` đã khởi tạo, nó được đóng khi `b` thất bại.
4. **Đóng theo thứ tự ngược.** Nếu `a` và `b` đã khởi tạo rồi `c` thất bại, Java gọi `b.close()` trước, rồi `a.close()`.
5. **Nếu đóng cũng lỗi, vẫn thử đóng các tài nguyên còn lại.** Một lỗi tại `close()` không làm Java bỏ qua toàn bộ tài nguyên khác.
6. **Ngoại lệ khởi tạo là ngoại lệ chính.** Ngoại lệ từ `close()` sau khi đã có lỗi khởi tạo thường được gắn vào ngoại lệ chính bằng `Throwable.addSuppressed(...)`, đọc qua `getSuppressed()`.
7. **Tài nguyên có giá trị `null` không bị gọi `close()`.** Nếu initializer trả về `null` một cách bình thường, đó không tự động là lỗi khởi tạo; hãy kiểm tra hợp đồng của API nếu `null` không hợp lệ.

### Bảng tình huống

| Diễn biến | Thân `try` chạy? | Tài nguyên được đóng | Lỗi chính |
| --- | --- | --- | --- |
| `a`, `b`, `c` đều khởi tạo thành công | Có | `c` → `b` → `a` sau thân `try` | Không có nếu mọi thao tác/đóng đều thành công |
| `createA()` ném ngoại lệ | Không | Không có tài nguyên nào đã hoàn tất khởi tạo trong header | Lỗi từ `createA()` |
| `a` thành công, `createB()` ném | Không | `a` | Lỗi từ `createB()` |
| `a` và `b` thành công, `createC()` ném | Không | `b` → `a` | Lỗi từ `createC()`; lỗi đóng có thể bị suppress |
| `a` thành công, `createB()` ném, `a.close()` cũng ném | Không | Có gọi `a.close()`, dù nó lỗi | Lỗi `createB()`; lỗi `close()` nằm trong `getSuppressed()` |

**Phân biệt từ ngữ:** “Đã khởi tạo thành công” nghĩa là biểu thức initializer trong header **đã trả về bình thường** (có thể trả về `null`). Một factory có thể đã cấp phát tài nguyên bên trong nhưng **ném ngoại lệ trước khi trả về**; những thứ cấp phát nội bộ đó không tự nhiên trở thành tài nguyên đã được đăng ký trong header. Phần 6 giải thích trách nhiệm của factory.

## 3. Vì sao vẫn có thể rò rỉ nếu tự mở trước `try`?

Xét cách tổ chức chưa an toàn:

~~~java
InputStream input = Files.newInputStream(path);
OutputStream output = Files.newOutputStream(otherPath);
try (input; output) {
    // Xử lý.
}
~~~

Đây là **đoạn minh họa**, cần có `Path path`, `Path otherPath` và import phù hợp. Cú pháp dùng biến đã khai báo trong header `try (input; output)` được hỗ trợ từ **Java 9**, nếu các biến là `final` hoặc *effectively final*.

**Rủi ro:** nếu `Files.newOutputStream(...)` thất bại, chương trình **chưa đến lệnh `try`**; tài nguyên `input` mở trước đó không được header này quản lý để đóng. Đặt các lời gọi tạo tài nguyên **trực tiếp trong header** sẽ an toàn hơn:

~~~java
try (InputStream input = Files.newInputStream(path);
     OutputStream output = Files.newOutputStream(otherPath)) {
    // Xử lý.
}
~~~

Ở dạng thứ hai, nếu mở `output` thất bại, `input` đã được đăng ký và tự động đóng.

Lưu ý: ví dụ có ý định chỉ ra **vị trí bắt đầu quản lý vòng đời**. Nó không nói rằng mọi biến khai báo trước `try` đều sai; nếu tài nguyên đã được mở trước đó và có vòng đời rộng hơn, bạn cần thiết kế rõ quyền sở hữu và bảo đảm cleanup từ điểm được cấp phát.

## 4. Ví dụ Java hoàn chỉnh: bốn kịch bản và thứ tự đóng

Ví dụ dùng một `Tracked` tự triển khai `AutoCloseable`. Lời gọi `open(...)` in bước khởi tạo và có thể cố ý ném `IOException`; `close()` cũng in thông tin và có thể cố ý thất bại. Nhờ vậy, mọi đường đi đều **xác định**, không phụ thuộc tệp, cơ sở dữ liệu, mạng hoặc thời gian.

Tạo file `src/main/java/demo/PartialResourceInitExample.java`:

~~~java
package demo;

import java.io.IOException;

public final class PartialResourceInitExample {
    private PartialResourceInitExample() {
    }

    static final class Tracked implements AutoCloseable {
        private final String name;
        private final boolean failClose;

        private Tracked(String name, boolean failClose) {
            this.name = name;
            this.failClose = failClose;
        }

        static Tracked open(String name, boolean failInit, boolean failClose)
                throws IOException {
            System.out.println("init:" + name);
            if (failInit) {
                throw new IOException("init:" + name);
            }
            return new Tracked(name, failClose);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:" + name);
            if (failClose) {
                throw new IOException("close:" + name);
            }
        }
    }

    static void runCase(
            String label, boolean failFirst, boolean failSecond, boolean failFirstClose) {
        System.out.println("CASE:" + label);
        try (Tracked first = Tracked.open("first", failFirst, failFirstClose);
             Tracked second = Tracked.open("second", failSecond, false)) {
            System.out.println("body:" + first.name + "+" + second.name);
        } catch (IOException ex) {
            System.out.println("error=" + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        runCase("success", false, false, false);
        runCase("first-init-fail", true, false, false);
        runCase("second-init-fail", false, true, false);
        runCase("second-init-and-close-fail", false, true, true);
    }
}
~~~

Trong thư mục chứa `src/`, dùng JDK có khả năng biên dịch mức Java 21:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/PartialResourceInitExample.java
java -cp out demo.PartialResourceInitExample
~~~

**Stdout chính xác**:

~~~text
CASE:success
init:first
init:second
body:first+second
close:second
close:first
CASE:first-init-fail
init:first
error=init:first
CASE:second-init-fail
init:first
init:second
close:first
error=init:second
CASE:second-init-and-close-fail
init:first
init:second
close:first
error=init:second
suppressed=close:first
~~~

### Đọc kết quả theo từng kịch bản

**A. Khởi tạo thành công (`success`)**

- `first` và `second` được khởi tạo theo đúng thứ tự khai báo.
- Sau khi cả hai thành công, chương trình mới in `body:first+second`.
- Khi rời thân `try`, Java tự gọi `second.close()` trước `first.close()`. Không cần viết `finally` đóng từng tài nguyên.

**B. Tài nguyên đầu tiên khởi tạo thất bại (`first-init-fail`)**

- Có `init:first`, sau đó `open("first", true, ...)` ném `IOException("init:first")`.
- Chưa có tài nguyên nào được header khởi tạo hoàn chỉnh; `second` không được thử tạo và thân `try` không chạy.
- Không thấy `close:first` vì `Tracked.open(...)` chưa trả về một tham chiếu `Tracked` để header quản lý.

**C. Tài nguyên thứ hai khởi tạo thất bại (`second-init-fail`)**

- `first` đã được tạo, nên sau `init:second` bị lỗi, Java gọi `first.close()`.
- Không có dòng `body:...` hoặc `close:second`. `second` chưa được tạo xong và chưa trở thành tài nguyên đã khởi tạo của header.
- `catch (IOException ex)` được thực thi **sau khi xử lý đóng tài nguyên đã đăng ký**; nó in lỗi khởi tạo thứ hai làm lỗi chính.

**D. Khởi tạo thứ hai lỗi, đóng thứ nhất cũng lỗi (`second-init-and-close-fail`)**

- `second` ném lỗi `init:second`.
- Java vẫn cố gắng đóng `first`, nhưng `close()` ném thêm `IOException("close:first")`.
- `init:second` **giữ vai trò lỗi chính**; `close:first` được lưu trong danh sách `ex.getSuppressed()` nên stdout có cả hai dòng `error=...` và `suppressed=...`.
- Việc gặp lỗi đóng không biến lỗi đóng thành nguyên nhân khởi tạo; hai sự cố cần được ghi nhận **phân biệt**.

Trong ví dụ `Tracked` chỉ để minh họa vòng đời. Với tài nguyên thật như stream, channel hoặc kết nối, các phương thức `close()` có thể giải phóng tài nguyên hệ điều hành, hủy phiên hoặc thực hiện những thao tác I/O nên cũng có thể phát sinh lỗi.

## 5. Ngoại lệ chính và suppressed exception

Khi bộ khởi tạo tài nguyên thứ hai ném, lỗi đó là **primary exception** của quá trình thất bại. Nếu tài nguyên đã mở trước đó ném khi đóng, Java không nên che mất lỗi khởi tạo ban đầu. Thay vào đó, lỗi đóng được đính kèm dưới dạng **suppressed exception**:

~~~java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    use(first, second);
} catch (Exception ex) {
    System.err.println("Primary: " + ex);
    for (Throwable closeError : ex.getSuppressed()) {
        System.err.println("Suppressed during cleanup: " + closeError);
    }
}
~~~

Đây là **mã minh họa cấu trúc** với các loại/tên phương thức giả định, không phải file Java hoàn chỉnh.

### Phân biệt ba khái niệm dễ nhầm

| Thành phần | Ý nghĩa | Khi gặp lỗi khởi tạo dở dang |
| --- | --- | --- |
| Ngoại lệ chính (`ex` trong `catch`) | Lỗi đang được truyền ra từ quá trình thực hiện | Thường là ngoại lệ do initializer thất bại |
| `ex.getSuppressed()` | Những ngoại lệ phụ được gắn vào lỗi chính khi cleanup cũng ném | Có thể chứa một hoặc nhiều lỗi `close()` của tài nguyên đã đăng ký |
| `ex.getCause()` | Nguyên nhân mà người tạo exception chủ động khai báo qua constructor/`initCause` | **Không đồng nghĩa** danh sách lỗi `close()`; có thể là `null` |

**Chi tiết quan trọng:**

- Nếu initializer thất bại rồi một hay nhiều `close()` cũng thất bại, các lỗi đóng được suppress thay vì làm mất lỗi initializer; chương trình vẫn tiếp tục cố đóng những tài nguyên khác.
- Nếu không có lỗi khởi tạo hay lỗi từ thân `try`, nhưng `close()` thất bại, lỗi đóng **có thể chính là lỗi được ném ra**. Khi nhiều `close()` cùng thất bại, lỗi đóng phát sinh đầu tiên theo thứ tự đóng ngược có thể là lỗi chính; các lỗi đóng sau bị suppress.
- `Throwable.getSuppressed()` trả về một mảng, có thể rỗng. Đừng giả định chỉ có tối đa một lỗi bị suppress khi quản lý nhiều tài nguyên.
- Không nên chỉ ghi `ex.getMessage()` rồi bỏ mất `getSuppressed()` khi điều tra lỗi đóng tài nguyên. Logger xử lý stack trace của `Throwable` thường hiển thị các lỗi suppressed; hãy bảo đảm cấu hình logging không làm mất chúng.
- `try-with-resources` không tự phục hồi lỗi I/O hoặc đảm bảo thao tác nghiệp vụ đã được rollback. Nó chỉ định nghĩa vòng đời đóng tài nguyên và thứ tự ngoại lệ được truyền ra.

## 6. Giới hạn quan trọng: lỗi **bên trong factory/constructor** không được header tự dọn dẹp

Đây là phần thường gây hiểu nhầm nhất của “khởi tạo một phần tài nguyên”.

Giả sử `openSecond()` đã mở một socket hoặc stream nội bộ, rồi bước cấu hình/validation tiếp theo bị lỗi **trước khi phương thức trả về**. Từ góc nhìn của header:

~~~java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    use(first, second);
}
~~~

Java vẫn đóng `first` đã hoàn tất khởi tạo. **Nhưng** tài nguyên phụ mà `openSecond()` tự mở rồi chưa trả về **không tự động được header biết tới hoặc đóng giúp**. Factory/constructor phải có cơ chế dọn dẹp cho các bước *acquire → configure → publish* của chính nó.

### Ví dụ helper tự cleanup khi chưa trả tài nguyên cho caller

Đoạn phương thức sau dùng các API hiện đại, biên dịch được khi đặt trong một lớp có đủ `import`. Nó minh họa việc mở stream trước, kiểm tra bước tiếp theo rồi **chỉ chuyển quyền sở hữu cho caller khi thành công**:

~~~java
static InputStream openValidated(Path path) throws IOException {
    InputStream input = Files.newInputStream(path);
    try {
        if (Files.size(path) == 0L) {
            throw new IOException("empty file");
        }
        return input; // Thành công: caller nhận quyền đóng stream.
    } catch (IOException | RuntimeException | Error ex) {
        try {
            input.close();
        } catch (IOException closeEx) {
            ex.addSuppressed(closeEx);
        }
        throw ex;
    }
}
~~~

Các `import` tương ứng là `java.io.InputStream`, `java.io.IOException`, `java.nio.file.Path` và `java.nio.file.Files`. Phương thức này **không phải một chương trình độc lập**; nó được kiểm thử riêng bằng `javac --release 21`.

- Nếu `Files.newInputStream(path)` thất bại, chưa có `input` để dọn ở phương thức này.
- Nếu stream đã mở, nhưng `Files.size(path)` hoặc quy tắc kiểm tra ném, nhánh `catch` sẽ cố gắng đóng `input` trước khi ném lại lỗi.
- Nếu đóng `input` cũng gây `IOException`, lỗi đóng được gắn vào lỗi ban đầu bằng `addSuppressed`.
- Nếu hàm trả về thành công, **caller phải đặt tài nguyên được trả về vào `try-with-resources`** hoặc chuyển quyền sở hữu một cách rõ ràng.
- Kiểm tra `Files.size(...)` chỉ là ví dụ về **một bước có thể thất bại sau khi acquire**; nó không thay thế việc validate nội dung tệp hay đảm bảo tệp không bị thay đổi đồng thời.

Ví dụ cách gọi (cần khai báo `path` và các biến nghiệp vụ phù hợp):

~~~java
try (InputStream input = openValidated(path)) {
    // Đọc và xử lý input.
}
~~~

Trong code production, nên ưu tiên factory có hợp đồng **hoặc trả về một tài nguyên sẵn sàng để caller quản lý, hoặc tự đóng mọi thứ đã acquire nếu thất bại**. Tránh constructor mở nhiều handle rồi ném giữa chừng mà không cleanup.

## 7. Thiết kế khởi tạo tài nguyên thực tế

### 7.1. Đặt các thao tác cấp phát liên quan trong cùng header

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    // Thực thi truy vấn bằng statement.
} catch (SQLException ex) {
    // Xử lý hoặc báo lỗi truy cập cơ sở dữ liệu.
}
~~~

Đây là **mã minh họa**, cần `dataSource`, `sql`, `java.sql.Connection`, `java.sql.PreparedStatement`, `java.sql.SQLException`. Nếu `prepareStatement(...)` thất bại sau khi `connection` đã được trả về thành công, Java sẽ đóng `connection`.

**Không suy diễn rằng đóng kết nối tự động rollback mọi thay đổi:** trạng thái transaction, auto-commit và rollback phải xử lý theo hợp đồng JDBC/nguồn dữ liệu. `try-with-resources` quản lý đóng tài nguyên, không thay thế chính sách giao dịch.

### 7.2. Xếp thứ tự theo quan hệ phụ thuộc

Nếu tài nguyên `b` cần `a` để khởi tạo, thường mở `a` trước, `b` sau. Java đóng `b` trước `a`, phù hợp quan hệ “tài nguyên phụ thuộc phải đóng trước tài nguyên nền”.

Khi tài nguyên không độc lập, cần hiểu rõ **quyền sở hữu**: một wrapper có thể tự đóng tài nguyên nền khi đóng chính nó. Đặt đồng thời wrapper và tài nguyên nền trong header có thể gây đóng hai lần nếu API không cho phép hoặc không thiết kế idempotent. Đọc hợp đồng `close()` của từng API và chọn một nơi chịu trách nhiệm rõ ràng.

### 7.3. Phạm vi `try` phải bao phủ thời gian sử dụng thật

Một tài nguyên được khởi tạo trong header sẽ được đóng **khi câu lệnh `try-with-resources` kết thúc**, dù thân `try` hoàn thành bình thường, `return` sớm hay phát sinh ngoại lệ. Không trả về một đối tượng còn phụ thuộc vào stream/kết nối đã bị đóng, trừ khi API quy định rõ dữ liệu đã được sao chép độc lập.

### 7.4. Không tự động nuốt hoặc thay thế ngoại lệ khởi tạo

Khi initializer thất bại, đừng cố gắng “phục hồi” bằng cách tiếp tục như thể tất cả tài nguyên đã sẵn sàng. Tách bạch lỗi thiết lập, lỗi nghiệp vụ và lỗi khi dọn dẹp; trả kết quả lỗi/throw exception phù hợp với API. Nếu cần retry, thực hiện một **lượt acquire mới** và bảo đảm lượt cũ đã được dọn dẹp.

### 7.5. Trường hợp initializer trả về `null`

~~~java
try (AutoCloseable handle = possiblyNullResource()) {
    // handle có thể null nếu API cho phép.
}
~~~

Đây là đoạn minh họa. Cú pháp cho phép resource được khởi tạo bằng `null`; Java không gọi `close()` trên giá trị đó. Tuy nhiên, nếu thân `try` dùng `handle` mà không kiểm tra null, vẫn có thể gặp `NullPointerException`. Với API yêu cầu bắt buộc có handle, tốt hơn là factory trả về tài nguyên hợp lệ hoặc ném ngoại lệ rõ ràng, thay vì dùng `null` làm tín hiệu lỗi mơ hồ.

## 8. Những hiểu nhầm cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Lỗi tại initializer thứ hai thì Java chưa vào `try`, nên resource thứ nhất sẽ rò rỉ.” | Các resource đã hoàn tất initializer trong **header** vẫn được tự động đóng |
| “Java khởi tạo mọi resource trước khi đánh giá lỗi.” | Khởi tạo **trái → phải**, dừng khi một initializer ném |
| “Thân `try` vẫn được chạy để cleanup.” | Thân không chạy nếu header thất bại; cleanup do cơ chế `try-with-resources` thực hiện |
| “`close()` lỗi thì thay thế lỗi khởi tạo.” | Khi có lỗi khởi tạo trước đó, lỗi đóng thường được **suppressed** trên lỗi chính |
| “Tài nguyên thứ hai đang mở dở chắc chắn được Java đóng.” | Header chỉ quản lý resource đã được khởi tạo thành công; factory phải dọn acquisition nội bộ nếu không trả về |
| “Chỉ cần `getCause()` là thấy mọi lỗi đóng.” | Lỗi đóng bị suppress được đọc từ **`getSuppressed()`** |
| “Không cần biết thứ tự tài nguyên.” | Đóng ngược thứ tự mở; thứ tự quan trọng với resource phụ thuộc |
| “Tự mở resource trước, rồi sau đó mới `try (resource)` vẫn an toàn nếu khởi tạo cái khác lỗi.” | Rủi ro tồn tại trong khoảng **trước khi vào header**; nên đưa các bước acquire liên quan vào header |
| “`try-with-resources` bảo đảm rollback giao dịch hoặc file sẽ không hỏng.” | Nó bảo đảm quy tắc đóng/cố gắng đóng và xử lý exception, không thay cho transaction/atomicity |

## 9. Bài tập tự kiểm tra

**Bài 1 — Tài nguyên đầu tiên lỗi.** Có `try (A a = openA(); B b = openB())` và `openA()` ném ngoại lệ ngay trước khi trả tham chiếu. `openB()` và thân `try` có chạy không, `a.close()` có được gọi không?

**Đáp án:** Không. Vì `a` chưa hoàn tất initializer, header chưa quản lý một tham chiếu `a` để đóng; các bước sau không chạy. Nếu `openA()` đã tự cấp phát handle bên trong trước khi ném, chính nó phải cleanup handle đó.

**Bài 2 — Tài nguyên thứ ba lỗi.** `a` và `b` đã khởi tạo; `c` ném lúc khởi tạo. Thứ tự `close()` là gì?

**Đáp án:** `b.close()` rồi `a.close()`. Thân `try` không chạy.

**Bài 3 — Hai lỗi đồng thời.** `openB()` ném `IOException("openB")`, còn `a.close()` ném `IOException("closeA")`. Ngoại lệ nào là lỗi chính?

**Đáp án:** `openB` là lỗi chính. Ngoại lệ `closeA` được gắn dưới dạng suppressed và truy cập bằng `getSuppressed()`, trừ trường hợp đặc biệt có hành vi khác ngoài giả định (ví dụ lỗi hệ thống không phải exception thông thường).

**Bài 4 — Lỗi trong factory.** `openB()` tự mở một stream nội bộ, bước cấu hình thất bại trước khi nó trả về, còn `a` đã mở thành công trong header. Ai đóng gì?

**Đáp án:** Header đóng `a`. `openB()` phải tự đóng stream nội bộ đã acquire nhưng chưa chuyển quyền sở hữu; header không có tham chiếu tới stream đó.

**Bài 5 — Dùng biến có sẵn.** `InputStream a = openA(); OutputStream b = openB(); try (a; b) { ... }` có thể rò rỉ `a` nếu `openB()` ném không?

**Đáp án:** Có, nếu không có một cơ chế cleanup khác. `a` đã mở **trước khi** chương trình đến câu lệnh `try`; cách viết `try (a; b)` không tự bảo vệ đoạn cấp phát bên ngoài.

## 10. Checklist trước khi dùng trong dự án

- [ ] Những lời gọi cấp phát tài nguyên liên quan được đặt trong header `try-with-resources` khi phù hợp.
- [ ] Hiểu thứ tự khởi tạo từ trái qua phải và đóng từ phải qua trái.
- [ ] Nếu initializer sau ném, các tài nguyên **đã khởi tạo trước** được tự động đóng; thân `try` không chạy.
- [ ] Nếu `close()` lỗi sau lỗi khởi tạo, kiểm tra `getSuppressed()` và không đánh mất ngoại lệ chính.
- [ ] Factory/constructor tự dọn các handle đã acquire nội bộ nhưng chưa chuyển quyền sở hữu khi khởi tạo thất bại.
- [ ] Quy định tài nguyên nào sở hữu wrapper/stream/kết nối phụ thuộc; tránh đóng hai lần không an toàn.
- [ ] Không nhầm đóng tài nguyên với rollback, atomicity hoặc recovery.
- [ ] Code mẫu biên dịch/chạy trên JDK được hỗ trợ; kiểm tra đường đi thành công và từng vị trí initializer thất bại.

**Tài liệu chính thức:**

- [JLS SE 21 `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3): thứ tự khởi tạo/đóng, xử lý initializer lỗi và suppressed exception.
- [Javadoc Java 21 — AutoCloseable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng phương thức `close()`.
- [Javadoc Java 21 — Throwable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html): `getSuppressed()`, `addSuppressed(...)` và `getCause()`.

Các quy tắc trên vẫn còn áp dụng trong Java hiện đại; các ví dụ thực hành không dựa vào API đã legacy.
