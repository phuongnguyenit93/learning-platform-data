# Xử lý lỗi cleanup mà vẫn giữ thông tin lỗi ban đầu

## 1. Khi công việc chính và cleanup cùng thất bại

Trong Java, một phương thức thường vừa làm công việc chính, vừa quản lý tài nguyên mà nó sử dụng. Công việc chính có thể là đọc file, ghi dữ liệu, thực thi truy vấn, gọi dịch vụ hoặc xử lý nghiệp vụ. Cleanup có thể là đóng stream, trả connection, giải phóng khóa, dừng session hoặc thu hồi tài nguyên tạm.

Một tình huống khó xảy ra khi **cả công việc chính và cleanup đều ném exception**. Chẳng hạn, thao tác ghi file thất bại vì lỗi I/O; trong lúc rời phương thức, thao tác đóng stream cũng thất bại. Khi đó có hai thông tin riêng cần giữ lại:

- **Primary exception (lỗi ban đầu)**: lỗi từ thao tác chính, giải thích vì sao công việc đang thực hiện không hoàn tất.
- **Cleanup exception (lỗi dọn dẹp)**: lỗi phát sinh khi cố hoàn tất hoặc giải phóng tài nguyên, cho biết một bước thu hồi cũng không thành công.

Nếu exception cleanup thay thế exception chính, lập trình viên có thể chỉ thấy “close failed” và không biết nguyên nhân thật là “write failed”. Nếu nuốt lỗi cleanup, người vận hành lại mất thông tin rằng việc đóng/hoàn tất tài nguyên có vấn đề.

**Mục tiêu thiết kế:** Khi công việc chính đã thất bại, tiếp tục giữ exception ban đầu làm exception được truyền ra và đính kèm exception cleanup để chẩn đoán. Khi công việc chính thành công nhưng cleanup thất bại, chính cleanup exception thường là lỗi của lời gọi.

Bảo toàn exception là một phần của **bảo toàn trạng thái**: nó giúp hệ thống quyết định kết quả, ghi nhận sự cố và xử lý hậu quả đúng. Tuy nhiên, giữ exception **không đồng nghĩa** tự rollback dữ liệu đã ghi hoặc phục hồi tài nguyên.

## 2. Vì sao finally có thể che mất lỗi gốc?

Khối **finally** được chạy khi luồng điều khiển rời **try/catch** trong điều kiện thông thường, kể cả khi thân **try** ném exception. Vì vậy nó thường được dùng cho cleanup. Vấn đề là **nếu finally ném exception khác, exception đang chờ được ném từ try có thể bị thay thế**.

Mã minh họa sau không phải chương trình Java độc lập:

~~~java
void save() throws java.io.IOException {
    try {
        throw new java.io.IOException("write failed");
    } finally {
        throw new java.io.IOException("close failed");
    }
}
~~~

Người gọi nhận lỗi **close failed**; lỗi **write failed** không tự xuất hiện trong **getCause()** hoặc **getSuppressed()**. Chỉ bọc **close()** vào **finally** chưa đủ để giữ thông tin lỗi chính.

Một biến thể còn nguy hiểm là **return trong finally**:

~~~java
// Minh họa phản mẫu; không phải chương trình độc lập.
try {
    performWork();  // Có thể ném exception.
} finally {
    return;         // Có thể che khuất exception đang chờ.
}
~~~

Nếu finally kết thúc bằng return, exception đang chờ có thể bị bỏ qua. Vì thế, tránh **return** trong finally và tránh cho lỗi cleanup bất ngờ che lấp lỗi cần báo ra.

Ngược lại, mẫu này cũng có vấn đề:

~~~java
// Minh họa phản mẫu; resource đã được khai báo ở nơi khác.
try {
    resource.close();
} catch (Exception ignored) {
    // Không còn bằng chứng về việc close() thất bại.
}
~~~

Catch rồi bỏ qua toàn bộ lỗi cleanup làm mất dữ liệu chẩn đoán; trong một số hệ thống, đó còn là dấu hiệu connection hoặc giao dịch đã ở trạng thái không đáng tin.

## 3. Cơ chế chuẩn: try-with-resources

Java cung cấp **try-with-resources** từ Java 7. Mọi tài nguyên triển khai **java.lang.AutoCloseable** có thể được khai báo trong dấu ngoặc của try, để Java tự gọi **close()** khi rời khối:

~~~java
// Minh họa cú pháp; openResource() trả về AutoCloseable.
try (var resource = openResource()) {
    performWork(resource);
}
~~~

Khi phần thân try và **close()** cùng ném exception, quy tắc là:

1. Giữ exception của thân try làm **primary exception**.
2. Gọi close theo quy tắc vòng đời tài nguyên.
3. Đưa exception phát sinh từ close vào danh sách **suppressed exceptions** trên chính primary.
4. Ném primary ra cho người gọi. Có thể lấy danh sách lỗi cleanup bằng **primary.getSuppressed()**.

Nếu phần thân không lỗi nhưng close lỗi, lỗi từ close trở thành exception chính. Java không tạo một exception phần thân giả để làm primary.

**Try-with-resources là giải pháp ưu tiên** khi cleanup chủ yếu là gọi close trên những tài nguyên AutoCloseable. Nó tránh phải tự viết nhiều nhánh catch/finally và giảm nguy cơ mất lỗi gốc.

### Một số điểm quan trọng về vòng đời

- Các tài nguyên trong try-with-resources được đóng theo **thứ tự ngược với thứ tự khai báo**.
- Nếu phần thân thất bại và nhiều close cũng thất bại, lỗi close lần lượt được suppressed vào exception phần thân.
- Nếu khởi tạo tài nguyên thứ hai thất bại sau khi tài nguyên thứ nhất đã được mở, Java vẫn cố đóng tài nguyên thứ nhất.
- Nếu thân try đang chuẩn bị **return**, close vẫn được thực hiện trước khi phương thức hoàn tất; close thất bại có thể khiến phương thức ném exception thay vì trả về giá trị.
- Try-with-resources đảm nhiệm việc gọi close và bảo toàn exception; nó **không bảo đảm** mọi tác dụng phụ trước đó được hoàn tác.

## 4. Ví dụ Java 17+ có thể biên dịch và chạy

Chương trình sau minh họa bốn trường hợp: cả thân và hai close đều thất bại, chỉ close thất bại, finally che lỗi gốc, và cleanup thủ công giữ lỗi gốc bằng **addSuppressed**.

Tạo file **CleanupFailureDemo.java**:

~~~java
import java.io.IOException;

public class CleanupFailureDemo {
    static final class DemoResource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        DemoResource(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (failOnClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    static void badFinally() throws IOException {
        try {
            throw new IOException("operation failed");
        } finally {
            throw new IOException("cleanup failed");
        }
    }

    static void manualPreserve() throws IOException {
        DemoResource resource = new DemoResource("manual", true);
        IOException primary = null;

        try {
            throw new IOException("operation failed");
        } catch (IOException original) {
            primary = original;
            throw original;
        } finally {
            try {
                resource.close();
            } catch (IOException cleanup) {
                if (primary != null) {
                    primary.addSuppressed(cleanup);
                } else {
                    throw cleanup;
                }
            }
        }
    }

    static void printFailure(IOException failure) {
        System.out.println("primary: " + failure.getMessage());
        Throwable[] suppressed = failure.getSuppressed();
        for (int i = 0; i < suppressed.length; i++) {
            System.out.println("suppressed " + (i + 1) + ": "
                    + suppressed[i].getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("== Work and two close failures ==");
        try (DemoResource a = new DemoResource("A", true);
             DemoResource b = new DemoResource("B", true)) {
            throw new IOException("operation failed");
        } catch (IOException failure) {
            printFailure(failure);
        }

        System.out.println("== Close failure only ==");
        try (DemoResource r = new DemoResource("single", true)) {
            System.out.println("operation succeeded");
        } catch (IOException failure) {
            printFailure(failure);
        }

        System.out.println("== Finally masks primary ==");
        try {
            badFinally();
        } catch (IOException failure) {
            printFailure(failure);
        }

        System.out.println("== Manual cleanup preserves primary ==");
        try {
            manualPreserve();
        } catch (IOException failure) {
            printFailure(failure);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 CleanupFailureDemo.java
java CleanupFailureDemo
~~~

Kết quả stdout đã kiểm tra trực tiếp với **javac --release 17** và **java**:

~~~text
== Work and two close failures ==
close B
close A
primary: operation failed
suppressed 1: close B failed
suppressed 2: close A failed
== Close failure only ==
operation succeeded
close single
primary: close single failed
== Finally masks primary ==
primary: cleanup failed
== Manual cleanup preserves primary ==
close manual
primary: operation failed
suppressed 1: close manual failed
~~~

### Phân tích đường chạy

**Thân try và hai close đều lỗi:** phần thân ném **IOException("operation failed")**. Khi rời try, B được đóng trước A. Cả hai lần đóng ném IOException; cả hai được lưu trong suppressed của lỗi phần thân. Vì vậy output vẫn có **primary: operation failed**, sau đó mới liệt kê **close B failed**, **close A failed**.

**Thân try thành công, close lỗi:** chương trình in **operation succeeded** trước khi đóng single. Do close thất bại và không có exception từ phần thân, **close single failed** trở thành primary; không có suppressed khác.

**Finally che lỗi ban đầu:** badFinally ném lỗi công việc trước và lỗi cleanup sau. Exception thoát ra từ phương thức là **cleanup failed**. Đây là phản ví dụ cho việc cleanup thủ công bất cẩn.

**Cleanup thủ công bảo toàn lỗi ban đầu:** manualPreserve ghi nhớ đối tượng IOException gốc rồi ném lại. Trong finally, nếu close lỗi, nó được thêm vào chính exception gốc qua **addSuppressed**; exception của phần thân tiếp tục được truyền ra.

Ví dụ **manualPreserve chỉ xử lý đường lỗi IOException**: nếu thân có thể ném RuntimeException hoặc Error, catch(IOException) sẽ không ghi nhận chúng; lỗi close phát sinh từ finally có thể che mất một lỗi khác. Không nên sao chép mẫu thủ công này như một cơ chế tổng quát cho mọi Throwable. Với tài nguyên AutoCloseable, **try-with-resources giải quyết trọn hơn** những trường hợp đó.

## 5. Suppressed exception là gì?

Mỗi đối tượng **Throwable** có thể giữ danh sách các exception bị suppressed. Hai phương thức chính:

- **addSuppressed(Throwable other)**: gắn một lỗi phụ vào Throwable hiện tại.
- **getSuppressed()**: lấy mảng những Throwable đã được gắn, theo thứ tự được thêm.

Ví dụ, bên ngoài một khối try-with-resources:

~~~java
// Ví dụ minh họa trong một catch block.
catch (java.io.IOException failure) {
    System.err.println("Primary: " + failure);
    for (Throwable cleanup : failure.getSuppressed()) {
        System.err.println("Cleanup: " + cleanup);
    }
    throw failure;
}
~~~

Đoạn trên chỉ là mã minh họa cho phần thân catch, không phải chương trình độc lập; catch phải đi kèm với một try phù hợp.

**Suppressed không phải cause.** Suppressed mô tả lỗi phụ xuất hiện khi một lỗi khác đang được xử lý hoặc hoàn tất tài nguyên. Cause mô tả chuỗi nguyên nhân của một exception được bọc hoặc chuyển đổi sang mức trừu tượng khác.

| Quan hệ | Ý nghĩa | Cách truy cập |
| --- | --- | --- |
| **Primary** | Lỗi chính được ném ra cho người gọi | Exception mà caller bắt được |
| **Cause** | Lỗi cấp dưới là nguyên nhân của lỗi cấp trên | **getCause()** |
| **Suppressed** | Lỗi phụ được giữ cùng primary, thường từ cleanup | **getSuppressed()** |

Ví dụ, tầng service bọc IOException thành IllegalStateException có cause. Nếu IOException đó mang suppressed của lỗi close thì caller cần đi theo **getCause()** để tìm suppressed trên IOException. Không có quy tắc tự động sao chép danh sách suppressed của cause lên object wrapper.

~~~java
// Minh họa trong một catch hợp lệ:
catch (java.io.IOException failure) {
    throw new IllegalStateException("Unable to save data", failure);
}
~~~

Cách này giữ lỗi ban đầu làm **cause**. Ngược lại, tạo exception mới chỉ với **failure.getMessage()** làm mất chuỗi cause và thông tin stack trace của original.

### Ràng buộc của addSuppressed

**Throwable.addSuppressed(null)** ném NullPointerException. Gắn chính Throwable vào nó sẽ ném IllegalArgumentException do self-suppression. Thông thường không được gắn cùng lỗi chính vào danh sách suppressed của chính nó. Ngoài ra, một số lớp Throwable đặc biệt có thể xây dựng với suppression bị vô hiệu hóa; khi đó addSuppressed không thực sự lưu lỗi. Vì thế việc ghi nhận suppression cần tuân thủ hợp đồng của throwable và không thay thế cơ chế logging/chẩn đoán khác trong mọi trường hợp.

## 6. Đóng nhiều tài nguyên theo thứ tự ngược

Giả sử có nhiều tài nguyên phụ thuộc nhau:

~~~java
// Ví dụ minh họa: cả hai lớp đều thực thi AutoCloseable.
try (ConnectionLike connection = openConnection();
     ReaderLike reader = openReader(connection)) {
    process(reader);
}
~~~

Java đóng **reader trước connection**, vì reader có thể còn cần connection trong quá trình close. Nếu phần thân lỗi và cả reader.close lẫn connection.close đều lỗi, cả hai được suppressed vào primary theo thứ tự close phát sinh.

Khi phân tích thứ tự đóng, cần xét:

1. **Thứ tự tạo** tài nguyên từ trái sang phải.
2. **Thứ tự đóng** từ phải sang trái.
3. **Đường lỗi trong lúc khởi tạo**: những tài nguyên đã tạo trước đó vẫn được đóng.
4. **Đường lỗi khi đóng**: các tài nguyên còn lại vẫn được thử đóng theo cơ chế try-with-resources.
5. **Bảo toàn primary**: lỗi phần thân hoặc lỗi khởi tạo có quyền ưu tiên so với lỗi close.

Một tài nguyên khai báo trong phần đầu nhưng trả về null sẽ không được gọi close. Trong thiết kế API, nên tránh sử dụng null làm tín hiệu tài nguyên hợp lệ khi có thể thiết kế hàm mở tài nguyên trả về object hợp lệ hoặc ném exception rõ ràng.

### Nếu khởi tạo một tài nguyên ở giữa thất bại

Hình dung thứ tự mở A, rồi mở B:

~~~text
open A: thành công
open B: ném exception E
close A: ném exception C

Exception thoát ra: E
Suppressed trên E: C
~~~

B chưa khởi tạo thành công nên không được đóng; A đã mở thành công được đóng. Vì E xảy ra trước trong công việc thiết lập tài nguyên, C được giữ như suppressed thay vì thay thế E.

Đây là một khác biệt lớn giữa try-with-resources và cleanup thủ công sơ sài: mã tự quản lý rất dễ quên đóng tài nguyên đã mở trước khi một tài nguyên sau thất bại.

## 7. Closeable, AutoCloseable và kiểu exception

**AutoCloseable** định nghĩa close có thể khai báo **throws Exception**. **java.io.Closeable** kế thừa AutoCloseable nhưng phương thức close khai báo **throws IOException**. Do đó loại tài nguyên quyết định checked exception nào code phải bắt hoặc khai báo.

Các class JDK thường gặp như InputStream, OutputStream, Reader, Writer, nhiều đối tượng JDBC đều hỗ trợ vòng đời thích hợp cho try-with-resources. Các API khác có thể ném SQLException hoặc exception riêng. Một class tự viết cũng có thể triển khai AutoCloseable và định nghĩa hành vi close theo tài nguyên mà nó sở hữu.

Ví dụ đọc file:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

// Phương thức minh họa theo ngữ cảnh; chưa phải file chương trình đầy đủ.
static String readFirstLine(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

Nếu readLine gây IOException và reader.close cũng gây IOException, lỗi đọc vẫn là primary. Nếu readLine hoàn tất nhưng close lỗi, readFirstLine có thể ném lỗi đóng thay vì trả về dòng đã đọc. Lệnh return trong thân try không bỏ qua quy trình đóng tài nguyên.

Từ Java 9, cú pháp try-with-resources có thể dùng biến tài nguyên **final hoặc effectively final** được khai báo trước khối:

~~~java
// Ví dụ minh họa, reader đã được khởi tạo và không bị gán lại.
try (reader) {
    process(reader);
}
~~~

Cú pháp này không biến một biến bất kỳ thành AutoCloseable; kiểu của reader vẫn phải phù hợp và biến phải thỏa điều kiện final/effectively final. Sau khi rời khối, tài nguyên đã được đóng, dù biến tham chiếu vẫn còn trong phạm vi.

Không nên giả định mọi AutoCloseable đều cho phép gọi close nhiều lần an toàn. Tính idempotent thuộc hợp đồng cụ thể của từng tài nguyên. Hạn chế đóng thủ công cùng resource bên trong thân try-with-resources nếu không có lý do rõ ràng.

## 8. Khi nào cần cleanup thủ công?

Không phải mọi cleanup đều tương đương một lần AutoCloseable.close. Có thể cần rollback transaction, khôi phục thông tin tạm, hủy yêu cầu, thu hồi một lock không bọc được thuận tiện, hoặc thực hiện nhiều thao tác có quy tắc phụ thuộc.

Nếu phải tự cleanup, cần thiết kế rõ ràng:

1. Lưu **primary** ngay tại nơi công việc chính thất bại.
2. Thử cleanup trong đường điều khiển đảm bảo phù hợp, thường là finally.
3. Nếu cleanup lỗi mà **chưa có primary**, truyền cleanup exception theo hợp đồng.
4. Nếu cleanup lỗi mà **đã có primary**, ghi nó vào suppressed (hoặc cơ chế quan sát có cấu trúc khác), đồng thời giữ primary để caller nhận.
5. Không nuốt **Error** hoặc RuntimeException ngoài ý muốn chỉ để tiếp tục chạy như thể thành công.
6. Nếu cleanup lỗi làm trạng thái hạ tầng không xác định, đánh dấu/loại bỏ tài nguyên không còn đáng tin.

Ví dụ helper hạn chế, chỉ minh họa việc gắn lỗi cleanup:

~~~java
// Mã minh họa: gọi khi caller đang quản lý primary Throwable.
static void closePreserving(AutoCloseable resource,
                            Throwable primary) throws Exception {
    if (resource == null) {
        return;
    }
    try {
        resource.close();
    } catch (Exception cleanup) {
        if (primary == null) {
            throw cleanup;
        }
        if (primary != cleanup) {
            primary.addSuppressed(cleanup);
        }
    }
}
~~~

Đoạn này **không phải** một giải pháp thay thế đầy đủ cho try-with-resources. Nó chỉ bắt Exception từ close, không bắt Error; nó không tự chạy phần thân, không tự ném lại primary và không giải quyết mọi nhánh của mã gọi. Nếu primary đã là Error hoặc một RuntimeException, phần gọi bên ngoài phải xử lý việc bảo toàn và ném lại đúng theo hợp đồng. Dùng try-with-resources khi có thể để Java lo các đường thông thường.

### Cleanup gồm nhiều bước

Giả sử phải đóng stream, connection và xóa file tạm. Nếu một bước cleanup đầu tiên ném exception mà mã không bắt, các bước cleanup sau có thể không được thử. Hãy quyết định bước nào độc lập và vẫn nên thử sau lỗi. Nếu cleanup bước sau nguy hiểm khi bước trước thất bại, không được tiếp tục chỉ để thu thêm exception.

Với nhiều tài nguyên AutoCloseable độc lập, một khối try-with-resources là lựa chọn thường tốt nhất: nó thử đóng các tài nguyên đúng thứ tự và tập hợp các exception phụ. Với các bước cleanup nghiệp vụ không có cùng mô hình, cần một chiến lược riêng và test những trường hợp lỗi kép, lỗi ba bước, lỗi giữa quá trình khởi tạo.

## 9. Lưu cause và suppressed khi chuyển exception qua các tầng

Một API có thể chuyển IOException thấp thành exception mức nghiệp vụ. Quan trọng là **không đánh mất original exception**:

~~~java
// Minh họa bên trong một phương thức thích hợp.
try {
    storeRecord();
} catch (java.io.IOException failure) {
    throw new IllegalStateException("Store operation failed", failure);
}
~~~

Constructor nhận cause giữ được cây exception. Nếu IOException có suppressed do resource.close thì những suppressed ấy vẫn nằm trên IOException trong cây cause; caller hoặc logger có thể duyệt cause rồi xem suppressed.

Phản mẫu:

~~~java
// Minh họa phản mẫu.
catch (java.io.IOException failure) {
    throw new IllegalStateException(failure.getMessage());
}
~~~

Cách này không truyền cause; thông tin lớp lỗi, vị trí phát sinh và suppressed của IOException ban đầu bị tách khỏi exception mới. Người đọc log khó xác định thao tác thực sự hỏng ở đâu.

Khi cần thêm ngữ cảnh, ưu tiên wrap bằng constructor có cause. Nếu không cần chuyển đổi abstraction, giữ và ném lại chính original. Không dùng suppressed để biểu diễn một lỗi thực sự là cause; hai quan hệ có ngữ nghĩa khác nhau.

## 10. Ghi log lỗi cleanup mà không che khuất lỗi ban đầu

Mục tiêu ghi log là cho người vận hành thấy được toàn bộ **Throwable tree**: primary, cause, suppressed và stack trace. Chỉ gọi **getMessage()** rồi in một chuỗi thường bỏ sót các phần quan trọng.

Nếu logging framework có API nhận Throwable, thường có thể truyền throwable trực tiếp:

~~~java
// Minh họa với logger hỗ trợ chữ ký error(String, Throwable).
logger.error("Operation failed; cleanup may also have failed", failure);
~~~

Đây là đoạn minh họa phụ thuộc logger cụ thể, không phải Java SE chạy độc lập. Với logger hay pipeline JSON tùy biến, cần kiểm tra formatter thực sự ghi cause/suppressed hay chỉ xuất message. Một số công cụ thu thập log rút gọn stack trace hoặc bỏ danh sách suppressed nếu cấu hình chưa đúng.

Bản stack trace đầy đủ thường có hình thức:

~~~text
java.io.IOException: operation failed
    ... stack trace of original failure ...
    Suppressed: java.io.IOException: close B failed
        ... stack trace ...
    Suppressed: java.io.IOException: close A failed
        ... stack trace ...
~~~

Đây là **định dạng minh họa**, khác với stdout chính xác ở ví dụ mục 4. Địa chỉ dòng mã cụ thể phụ thuộc chương trình và cách log hiển thị.

Một lưu ý khác: hệ thống ghi nhận sự cố cũng có thể thất bại. Nếu một callback ghi log tự ném exception khi đang xử lý primary, cần tránh để lỗi ghi log che lấp thông tin chính. Thiết kế đường báo lỗi nên đơn giản, có quan sát phù hợp và không tự động thay thế Throwable có giá trị chẩn đoán.

## 11. Cleanup liên quan gì tới bảo toàn trạng thái?

Cleanup thành công không có nghĩa dữ liệu chắc chắn đã được rollback:

- **Đóng OutputStream** không tự xóa các byte đã ghi trước đó. Một phần dữ liệu có thể đã được lưu, và lỗi khi đóng có thể liên quan tới flush hoặc hoàn tất ghi.
- **Đóng connection** không mặc nhiên xác nhận mọi thao tác SQL đã rollback theo ý người lập trình. Cần hiểu transaction mode và API đang dùng.
- **Release lock** giải phóng cơ chế đồng bộ nhưng không đảo ngược các biến hoặc collection đã sửa khi giữ lock.
- **Rollback** là thao tác khôi phục ở tầng giao dịch; rollback cũng có thể thất bại và cần được ghi nhận.
- **Hủy request từ xa** có thể không thu hồi tác dụng phụ nếu phía nhận đã xử lý.

Ví dụ một service ghi database bị lỗi, rồi gọi rollback nhưng rollback tiếp tục ném exception. Thông tin lỗi ghi vẫn cần được giữ vì nó giải thích lý do giao dịch đi vào đường thất bại; lỗi rollback cần được đính kèm vì nó cho biết tình trạng khôi phục không chắc chắn. **Việc thêm lỗi rollback vào suppressed không chứng minh rollback đã thành công.** Ứng dụng có thể phải loại bỏ connection, đánh dấu trạng thái chưa xác định, hoặc dùng cơ chế phục hồi được thiết kế riêng.

Ngược lại, **commit thất bại** có thể là lỗi chính của một thao tác nghiệp vụ dù diễn ra gần cuối phương thức. Không đánh đồng mọi thao tác ở cuối với cleanup có thể xem nhẹ. Hợp đồng nghiệp vụ và cơ chế lưu trữ quyết định việc nào thuộc công việc chính, việc nào chỉ là dọn dẹp vòng đời tài nguyên.

Trong các chương trình có side effect bên ngoài, thông tin suppressed giúp chẩn đoán nhưng không thể thay thế transaction, idempotency, hay cơ chế bù trừ (compensation) phù hợp.

## 12. Checked exception, RuntimeException, Error và interrupt

Quy tắc suppressed của try-with-resources áp dụng cho **Throwable**, không chỉ IOException. Nếu phần thân ném RuntimeException và close ném IOException, RuntimeException vẫn có thể là primary, còn IOException đóng tài nguyên được suppressed. Nếu thân ném Error, Java vẫn thực hiện nguyên tắc dọn dẹp và suppression; tuy nhiên ứng dụng không nên lạm dụng **catch(Throwable)** để nuốt lỗi nghiêm trọng.

Khi cleanup thủ công, cần hiểu chính xác loại exception mà code bắt:

- **catch(IOException)** bỏ sót RuntimeException và Error.
- **catch(Exception)** bắt checked exception và RuntimeException nhưng không bắt Error.
- **catch(Throwable)** bắt cả Error; chỉ dùng nếu thực sự cần cho bảo toàn thông tin và phải ném lại hoặc xử lý đúng bản chất, không im lặng phục hồi như thể mọi lỗi đều bình thường.

Một trường hợp đặc biệt là **InterruptedException**. Nếu code bắt và quyết định không ném lại InterruptedException, thường cần cân nhắc **Thread.currentThread().interrupt()** để giữ tín hiệu gián đoạn. Nhưng việc reset interrupt phụ thuộc hợp đồng của API và trạng thái thread; không nên biến thành thao tác máy móc trong mọi catch. Khi một cleanup gặp gián đoạn, phải xét cả lỗi chính và ý nghĩa của việc hủy tác vụ.

Không giả định rằng close chắc chắn không lỗi vì nó nằm ở finally; cũng không mặc định rằng AutoCloseable.close idempotent hoặc mọi lời gọi close an toàn để retry. Quyết định retry cleanup cần dựa trên tài nguyên cụ thể và tác dụng phụ của lần gọi trước.

## 13. Kiểm thử trường hợp cleanup lỗi và lỗi kép

Một test chỉ kiểm tra **assertThrows(IOException.class, ...)** là chưa đủ. Hai exception đều thuộc IOException nhưng exception thứ nhất giải thích thao tác hỏng, còn exception thứ hai chỉ giải thích cleanup. Nếu mã accidentally che primary, test chỉ so loại exception vẫn có thể PASS.

Bộ kiểm thử nên bao phủ ma trận:

| Công việc chính | Cleanup | Exception truyền ra | Suppressed |
| --- | --- | --- | --- |
| Thành công | Thành công | Không có | Không có |
| Thất bại A | Thành công | A | Không có |
| Thành công | Thất bại B | B | Không có |
| Thất bại A | Thất bại B | A | B |
| Thất bại A | B và C đều thất bại | A | B, C theo thứ tự đóng |
| Khởi tạo resource sau lỗi | Đóng resource trước cũng lỗi | Lỗi khởi tạo | Lỗi đóng resource trước |

Với try-with-resources, một kiểm thử mạnh nên:

1. Tạo một instance exception A xác định cho thao tác chính.
2. Tạo một instance exception B xác định cho close.
3. Cho thân try ném đúng object A, cho close ném object B.
4. Bắt từ bên ngoài và xác minh exception nhận được **chính là A** (so sánh tham chiếu, không chỉ message).
5. Xác minh **getSuppressed()** chứa đúng object B, đúng số lượng và đúng thứ tự.
6. Xác minh close được gọi ngay cả khi thân thất bại.
7. Thử thêm đường công việc thành công nhưng close lỗi để bảo đảm B được truyền ra.

Khi có nhiều tài nguyên, kiểm tra thứ tự close ngược với khai báo. Khi một constructor hoặc factory mở resource thất bại ở giữa, kiểm tra các tài nguyên đã mở trước được cleanup. Nếu cleanup có liên quan I/O/database thật, thêm integration test về trạng thái ngoài bộ nhớ; exception tree chính xác không thay cho việc kiểm tra kết quả transaction hay dữ liệu ghi.

Chương trình Java ở mục 4 mô phỏng các nhánh cần thiết bằng tài nguyên tự tạo, nên kết quả deterministic, dễ quan sát và không phụ thuộc file/network thật.

## 14. Những lỗi phổ biến

**Lỗi 1 — finally làm mất exception ban đầu.** Lệnh close trong finally có thể ném exception mới che lỗi phần thân. Dùng try-with-resources hoặc gắn lỗi cleanup bằng addSuppressed khi phải xử lý thủ công.

**Lỗi 2 — nuốt mọi exception cleanup.** Khó biết stream, connection hay rollback đã thực sự hoàn tất chưa. Nếu hợp đồng cho phép bỏ qua một lỗi cụ thể, phải có lý do; tránh bỏ qua mọi Exception.

**Lỗi 3 — chỉ log getMessage().** Thông điệp không chứa đầy đủ cause, stack trace và suppressed. Truyền Throwable vào logger có khả năng hiển thị cây lỗi.

**Lỗi 4 — xem suppressed giống cause.** Cause là quan hệ nguyên nhân giữa các lớp lỗi; suppressed là lỗi phụ được giữ cùng primary. Dùng getSuppressed để kiểm tra lỗi cleanup của try-with-resources.

**Lỗi 5 — nghĩ rằng cleanup thất bại luôn có thể bỏ qua.** Nếu thân thành công nhưng close thất bại, close exception thường là lỗi chính của cả lời gọi.

**Lỗi 6 — chỉ đóng tài nguyên cuối cùng.** Nếu mở nhiều resource rồi khởi tạo một resource sau thất bại, các resource đã mở trước cần được đóng. Try-with-resources giải quyết đường này theo quy tắc của Java.

**Lỗi 7 — helper cleanup chỉ catch một kiểu.** RuntimeException hoặc Error từ thân có thể bị che khi finally ném checked exception. Hiểu đầy đủ những loại Throwable có thể phát sinh.

**Lỗi 8 — tạo exception mới mà không truyền cause.** Khi wrap, luôn giữ exception gốc trong cause nếu nó là nguyên nhân thực sự, để các suppressed đi cùng được truy xuất.

**Lỗi 9 — gọi close hai lần không kiểm tra hợp đồng.** Không phải mọi AutoCloseable đều idempotent. Tránh tự close trong thân rồi tiếp tục để cơ chế tự động close nữa nếu không cần thiết.

**Lỗi 10 — nhầm giữ lỗi với phục hồi trạng thái.** Suppressed có thể cho biết rollback/close hỏng, nhưng không khiến dữ liệu tự trở về trạng thái trước thao tác.

## 15. Bảng kiểm khi thiết kế mã Java

Trước khi hoàn thiện phương thức có cleanup, kiểm tra:

1. **Loại tài nguyên:** có thể sử dụng AutoCloseable và try-with-resources không?
2. **Đường lỗi chính:** những lệnh nào trong công việc chính có thể ném exception?
3. **Đường lỗi cleanup:** close/rollback/release có thể ném checked, unchecked hay Error nào?
4. **Primary:** nếu hai bước đều lỗi, caller còn nhận exception đầu tiên của công việc chính không?
5. **Suppressed:** các lỗi cleanup được gắn vào primary và có thể truy xuất bằng getSuppressed không?
6. **Close-only:** nếu công việc chính thành công nhưng cleanup lỗi, caller có thấy lỗi cleanup theo đúng hợp đồng không?
7. **Nhiều tài nguyên:** thứ tự đóng, trường hợp khởi tạo lỗi giữa chừng và cleanup lỗi tiếp đã được xét chưa?
8. **Logs:** có giữ cause, suppressed và stack trace, đồng thời bảo vệ thông tin nhạy cảm không?
9. **Trạng thái:** nếu cleanup hoặc rollback lỗi, hệ thống có cần đánh dấu tài nguyên không còn đáng tin không?
10. **Tests:** test có kích hoạt lỗi kép, xác minh identity của primary và nội dung suppressed không?

**Ghi nhớ:** Với tài nguyên AutoCloseable, **try-with-resources** là cách chuẩn để cleanup mà vẫn bảo toàn lỗi công việc chính. Nếu cả thân try và close thất bại, lỗi thân là **primary**, lỗi close nằm trong **suppressed**. Khi phải cleanup thủ công, cần chủ động bảo vệ exception ban đầu, giữ thông tin lỗi phụ và xác định rõ trạng thái dữ liệu/tài nguyên sau đường thất bại.