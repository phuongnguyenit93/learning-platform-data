# Khi nào nhiều loại ngoại lệ có thể dùng chung một cách xử lý trong Java?

Trong Java, không phải mỗi loại ngoại lệ đều cần một khối `catch` riêng. Nếu nhiều loại lỗi dẫn đến **cùng quyết định xử lý**, Java cho phép gom chúng trong một nhánh *multi-catch*: `catch (IOException | SQLException ex)`. Tuy nhiên, việc có thể viết chung về **cú pháp** không có nghĩa việc xử lý chung luôn đúng về **nghiệp vụ**.

Ví dụ, ứng dụng đọc dữ liệu từ tệp hoặc cơ sở dữ liệu. Nếu cả hai lỗi đều cho phép sử dụng một bản dữ liệu cache an toàn, một nhánh xử lý chung có thể hợp lý. Ngược lại, nếu lỗi I/O cần thử lại, lỗi SQL cần rollback giao dịch, hoặc `InterruptedException` phải bảo toàn tín hiệu hủy, việc gộp chúng vào một nhánh chung có thể che giấu các quyết định quan trọng.

Bài học này tập trung vào tiêu chí quyết định **khi nào nên dùng chung cách xử lý**, cách viết `multi-catch`, tương tác với kế thừa, `rethrow`, xử lý ngoại lệ ở nhiều tầng và cách không làm mất nguyên nhân gốc.

## 1. Multi-catch giải quyết vấn đề gì?

Trước Java 7, khi hai ngoại lệ cần cùng hành động, mã thường phải lặp logic xử lý:

```java
try {
    loadData();
} catch (IOException ex) {
    reportFailure(ex);
} catch (SQLException ex) {
    reportFailure(ex);
}
```

Đây là đoạn minh họa trong một phương thức, giả sử `loadData()` có thể ném `IOException` hoặc `SQLException`, và `reportFailure(Exception)` đã được định nghĩa. Hai nhánh khác nhau về **kiểu ngoại lệ** nhưng cùng gọi một hàm với cùng chính sách.

Có thể viết rõ hơn bằng multi-catch:

```java
try {
    loadData();
} catch (IOException | SQLException ex) {
    reportFailure(ex);
}
```

Cả hai loại được liệt kê bằng toán tử `|` trong **một** tham số của **một** nhánh `catch`. Nếu `try` ném một trong hai kiểu tương thích, khối chung chạy đúng một lần. Mã vẫn chịu các quy tắc checked exception và khả năng đến được của `catch` như thông thường.

Mục tiêu chính là **xóa sự lặp lại của cùng một quyết định**, thay vì chỉ gom những ngoại lệ có tên hoặc nguồn phát sinh tương tự.

## 2. Tiêu chí quan trọng: các lỗi có thật sự dùng được cùng chính sách?

Hãy trả lời đủ năm câu hỏi trước khi gộp:

1. **Kết quả mong muốn có giống nhau?** Ví dụ cả hai lỗi đều dẫn đến “không thể nạp dữ liệu, dùng cache đã được kiểm chứng”, hoặc “dừng thao tác và ném một ngoại lệ nghiệp vụ có cause”.
2. **Có cùng mức độ ảnh hưởng và khả năng phục hồi?** Việc tiếp tục với kết quả dự phòng phải an toàn đối với cả hai trường hợp; không được dùng chung fallback cho một lỗi có thể làm dữ liệu không nhất quán.
3. **Có cần thao tác chuyên biệt?** Ví dụ lỗi DB có thể cần rollback hoặc đánh dấu một kết nối không còn dùng được; lỗi mạng có thể cần retry; tín hiệu interrupt cần chính sách hủy. Nếu hành động khác nhau, tách nhánh.
4. **Có cần cung cấp kết quả khác nhau cho bên gọi?** Nếu một lỗi được ánh xạ thành “không tìm thấy dữ liệu”, còn lỗi kia thành “hệ thống tạm thời không sẵn sàng”, gộp mất sự phân biệt có ích.
5. **Có bảo toàn đủ thông tin để điều tra?** Một nhánh chung vẫn cần giữ kiểu lỗi thực tế, `message`, `cause` và `suppressed` khi cần, thay vì biến tất cả thành một chuỗi vô danh.

**Chỉ nên gộp khi cùng chính sách xử lý là đúng cho mọi loại lỗi trong nhánh.** Khi các loại ngoại lệ có chiến lược khác nhau, hai `catch` riêng thường sáng sủa và đúng hơn.

| Tình huống | Có nên chung `catch`? | Lý do |
| --- | --- | --- |
| Lỗi đọc tệp và lỗi truy vấn dữ liệu; cả hai có cache hợp lệ được phép sử dụng | Có thể | Cùng quyết định fallback, nhưng cần bảo đảm cache đáp ứng yêu cầu dữ liệu |
| Lỗi đọc tệp và lỗi DB đều được chuyển thành `DataLoadException` với cause | Có thể | Cùng hợp đồng lỗi của tầng dịch vụ, vẫn giữ nguyên nhân |
| `FileNotFoundException` cần hiển thị thông báo “thiếu cấu hình”, `AccessDeniedException` cần báo lỗi quyền | Nên tách | Ý nghĩa, cách khắc phục và thông điệp khác nhau |
| `SocketTimeoutException` có thể retry, `SQLException` có thể cần rollback/đánh dấu giao dịch lỗi | Thường tách | Hành động xử lý phụ thuộc nguồn lỗi và trạng thái hệ thống |
| `InterruptedException` và `IOException` | Thường tách | InterruptedException có nghĩa hủy/chuyển trạng thái interrupt, không đơn giản là lỗi I/O |
| `IOException` và `OutOfMemoryError` | Không nên gom để “xử lý mọi lỗi” | Lỗi nghiêm trọng của JVM không bảo đảm khả năng phục hồi như I/O thông thường |

Những gợi ý trong bảng phụ thuộc ngữ cảnh. Không có quy tắc rằng lỗi SQL luôn phải rollback thủ công hoặc lỗi timeout luôn được retry: quyết định dựa trên giao dịch, idempotency và hợp đồng API thực tế.

## 3. Cú pháp và giới hạn kiểu của multi-catch

Multi-catch dùng dấu `|` để liệt kê những **loại ngoại lệ đã chọn** và một thân handler chung:

```java
try {
    loadData();
} catch (IOException | SQLException ex) {
    reportFailure(ex);
}
```

Đây là đoạn minh họa cần `loadData()` và `reportFailure(...)` được định nghĩa. `IOException` và `SQLException` không có quan hệ cha–con nên có thể xuất hiện cùng nhau khi khối `try` thực sự có khả năng ném hai checked exception ấy.

Các ràng buộc chính: không ghép một lớp với chính subtype của nó (như `IOException | FileNotFoundException`); `ex` ngầm `final`; compiler chỉ cho gọi các thành viên có trên **kiểu tĩnh chung** của các alternative; và checked exception phải phù hợp với khả năng phát sinh từ `try`. Những ràng buộc này xác định **cú pháp hợp lệ**, còn câu hỏi chính của bài là liệu cả hai lỗi có **cùng chính sách nghiệp vụ** hay không.

## 4. Chương trình Java 17+: dùng chung fallback khi cả hai lỗi có cùng hậu quả

Giả sử cả nguồn tệp và DB đều chỉ là nguồn bổ sung; dịch vụ **được phép** trả dữ liệu cache đã xác minh khi không nạp được dữ liệu mới. Đây là chính sách nghiệp vụ cho ví dụ, không phải lời khuyên dùng cache bất kể dữ liệu có quan trọng hay không.

Lưu thành `SharedFallbackDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class SharedFallbackDemo {
    static String loadFresh(int mode) throws IOException, SQLException {
        if (mode == 1) {
            throw new IOException("file unavailable");
        }
        if (mode == 2) {
            throw new SQLException("database unavailable");
        }
        return "fresh-data";
    }

    static String loadWithFallback(int mode) {
        try {
            return loadFresh(mode);
        } catch (IOException | SQLException ex) {
            System.out.println("fallback after "
                    + ex.getClass().getSimpleName());
            return "verified-cache";
        }
    }

    public static void main(String[] args) {
        System.out.println("result=" + loadWithFallback(0));
        System.out.println("result=" + loadWithFallback(1));
        System.out.println("result=" + loadWithFallback(2));
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 SharedFallbackDemo.java
java SharedFallbackDemo
```

Kết quả:

```text
result=fresh-data
fallback after IOException
result=verified-cache
fallback after SQLException
result=verified-cache
```

Đường đi chính:

1. `mode = 0`: `loadFresh` hoàn tất bình thường, không chạy `catch`, trả `fresh-data`.
2. `mode = 1`: ném `IOException`, đi vào **cùng một nhánh multi-catch**, in kiểu lỗi và trả cache.
3. `mode = 2`: ném `SQLException`, vẫn đi vào nhánh chung và trả cùng fallback.
4. Phương thức `loadWithFallback` không cần `throws IOException, SQLException`, vì hai ngoại lệ checked đều được xử lý và không tiếp tục thoát khỏi phương thức.

Lợi ích nằm ở chỗ **quyết định fallback là một quy tắc thống nhất**. Nếu trong nghiệp vụ thật, lỗi SQL có thể cho biết dữ liệu đã bị ghi một phần và cache không còn đáng tin cậy, chính sách này không còn đúng: cần tách quy trình xử lý hoặc sửa hợp đồng thao tác.

## 5. Khi cùng cách xử lý là chuyển thành ngoại lệ nghiệp vụ

Một tầng lưu trữ có thể phát sinh nhiều kiểu checked exception hạ tầng, nhưng tầng dịch vụ muốn cung cấp một hợp đồng “không thể nạp thông tin”. Nếu cả hai lỗi đều có cùng ý nghĩa tại ranh giới đó, có thể **bọc chung**, giữ nguyên nhân thực tế:

```java
catch (IOException | SQLException ex) {
    throw new DataLoadException("Cannot load data", ex);
}
```

Đây là đoạn nằm trong phương thức được khai báo phù hợp với `throws DataLoadException`; `DataLoadException` phải là lớp ngoại lệ có constructor nhận `cause`. Bọc lỗi tạo **đối tượng ngoại lệ mới**, khác với rethrow cùng đối tượng.

Lưu thành `SharedTranslationDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class SharedTranslationDemo {
    static class DataLoadException extends Exception {
        DataLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String repository(int source) throws IOException, SQLException {
        if (source == 1) {
            throw new IOException("disk read failed");
        }
        if (source == 2) {
            throw new SQLException("query failed");
        }
        return "OK";
    }

    static String service(int source) throws DataLoadException {
        try {
            return repository(source);
        } catch (IOException | SQLException ex) {
            throw new DataLoadException("Cannot load data", ex);
        }
    }

    public static void main(String[] args) {
        for (int source = 0; source < 3; source++) {
            try {
                System.out.println("value=" + service(source));
            } catch (DataLoadException ex) {
                Throwable cause = ex.getCause();
                System.out.println("service=" + ex.getMessage());
                System.out.println("cause="
                        + cause.getClass().getSimpleName()
                        + ":" + cause.getMessage());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 SharedTranslationDemo.java
java SharedTranslationDemo
```

Kết quả:

```text
value=OK
service=Cannot load data
cause=IOException:disk read failed
service=Cannot load data
cause=SQLException:query failed
```

Hai loại lỗi bên dưới được **dịch thành một checked exception của tầng dịch vụ**. `service()` khai báo `throws DataLoadException`, còn `main()` bắt đúng hợp đồng đó. Vì `DataLoadException` nhận `ex` làm cause, bên điều tra vẫn phân biệt được `IOException` với `SQLException` và xem lại stack trace ban đầu.

Không nên thay thế bằng `throw new DataLoadException(ex.getMessage(), null)` hoặc tạo một ngoại lệ mới chỉ có message: làm vậy có thể đánh mất liên kết nguyên nhân. Khi ghi log, nên truyền cả đối tượng throwable cho API logging thay vì chỉ in text message.

## 6. Khi nào nên tách các nhánh `catch`?

Multi-catch là lựa chọn tốt khi hành động giống nhau. Khi có **quy tắc khác nhau**, hai nhánh độc lập trực tiếp phản ánh thiết kế:

```java
try {
    processRequest();
} catch (java.net.SocketTimeoutException ex) {
    scheduleBoundedRetry(ex);
} catch (java.sql.SQLException ex) {
    markOperationFailed(ex);
    throw ex;
}
```

Đây là **đoạn minh họa trong một phương thức**, giả định `processRequest()` khai báo các checked exceptions liên quan, hai phương thức hỗ trợ đã được định nghĩa, và phương thức bao ngoài khai báo `throws SQLException`. Không thể coi đây là chương trình độc lập.

Nhánh timeout lựa chọn retry có giới hạn; nhánh SQL đánh dấu thao tác thất bại và để ngoại lệ tiếp tục lan lên. Hai chính sách khác nhau nên không đáng gom chỉ để giảm số dòng.

Các dấu hiệu cần tách:

- **Mức độ khẩn cấp khác nhau:** lỗi thiếu tham số đầu vào có thể phản hồi ngay, lỗi hạ tầng cần đánh dấu thất bại hệ thống.
- **Khả năng thử lại khác nhau:** retry chỉ hợp lý nếu thao tác có tính idempotent hoặc có cơ chế bảo vệ khỏi tác dụng phụ lặp.
- **Tài nguyên và giao dịch khác nhau:** một lỗi cần đóng kết nối, lỗi khác cần rollback hoặc không được phép tiếp tục.
- **Yêu cầu bảo toàn trạng thái thread:** `InterruptedException` là tín hiệu phối hợp hủy; thường nên truyền lên hoặc đặt lại cờ interrupt và kết thúc thao tác, thay vì gom với một lỗi hạ tầng thông thường.
- **Phản hồi cho người dùng khác nhau:** lỗi quyền truy cập và lỗi tạm thời không sẵn sàng không nên tự động nhận cùng thông điệp.
- **Giám sát khác nhau:** dù cuối cùng đều thất bại, nhu cầu phân loại alert/metric có thể buộc giữ kiểu rõ ràng ở ranh giới ghi nhận.

**Không nên gộp rồi viết một chuỗi lớn `if (ex instanceof A) ... else ...` chỉ để khôi phục các nhánh đã gộp.** Nếu chính sách thực sự khác nhau, các `catch` riêng thường dễ đọc và ít lỗi hơn. Việc dùng `instanceof` vẫn hợp lý nếu có một bước nhỏ cần phân loại bổ sung bên trong một chính sách chung, nhưng nên đặt câu hỏi tại sao cần gộp.

## 7. Phân biệt “hành động chung” với “thông tin chung”

Cùng dùng một câu lệnh `logger.error("failed", ex)` chưa đủ để kết luận hai ngoại lệ nên được xử lý chung. Ghi log chỉ là **một tác dụng phụ**; điều quan trọng là **hậu quả cho hệ thống và hợp đồng tầng trên**.

Giả sử hai lỗi đều được ghi log:

```java
catch (IOException ex) {
    recordFailure(ex);
    return cachedValue();
} catch (SQLException ex) {
    recordFailure(ex);
    throw ex;
}
```

Hai nhánh chia sẻ `recordFailure(ex)`, nhưng một nhánh phục hồi, nhánh còn lại truyền lỗi. Đây **không phải cùng cách xử lý tổng thể**; không nên gộp thành một `catch` rồi tùy tiện trả cache trong mọi trường hợp.

Nếu muốn giảm mã trùng, trích logic ghi nhận thành phương thức chung như ví dụ. Hãy giữ các quyết định khác nhau ở nhánh phù hợp.

Một trường hợp khác: khi tầng biên luôn chuyển nhiều ngoại lệ sang cùng mã kết quả thất bại và cùng chính sách dừng, multi-catch có thể phù hợp dù các nguyên nhân khác nhau, **miễn nguyên nhân vẫn được lưu** để phân tích. Việc cùng thông điệp gửi cho người dùng không nhất thiết đồng nghĩa cần làm mất sự khác biệt trong log và metrics.

## 8. Multi-catch và rethrow: truyền đúng đối tượng ra tầng trên

Khi tầng hiện tại chưa thể phục hồi, một handler chung vẫn có thể ghi nhận ngữ cảnh rồi **ném lại đúng đối tượng lỗi**:

```java
static void forward() throws IOException, SQLException {
    try {
        loadData();
    } catch (IOException | SQLException ex) {
        System.out.println("forward=" + ex.getClass().getSimpleName());
        throw ex;
    }
}
```

Đây là phương thức minh họa; `loadData()` phải có hợp đồng `throws IOException, SQLException`. `throw ex;` **không** biến thất bại thành thành công và không tạo wrapper mới; caller tiếp tục chịu trách nhiệm xử lý. `IOException` và `SQLException` vẫn là hai checked exception trong chữ ký.

Nếu tầng hiện tại muốn diễn đạt một lỗi nghiệp vụ chung, thay vì ném lại có thể bọc bằng một exception mới **giữ `ex` làm `cause`**. Quyết định dịch hay ném lại là quyết định về tầng trách nhiệm, không phải lý do tự động gom các loại lỗi có chính sách khác nhau. Quy tắc suy luận checked exception hẹp khi rethrow được gọi là *precise rethrow* và có điều kiện riêng trong JLS.

## 9. Multi-catch không cho gán lại biến tham số

Trong `catch (IOException | SQLException ex)`, biến `ex` **ngầm `final`**: gán `ex = new IOException("other")` là lỗi biên dịch. Điều này không cấm **ném lại** `throw ex;`, đọc stack/cause hay tạo wrapper mới có `cause` là `ex`. Đừng nhầm việc tham số không thể gán lại với việc đối tượng `Throwable` bất biến; suppressed exceptions hoặc stack trace có thể có trạng thái riêng. Khi muốn thêm ngữ cảnh, tạo ngoại lệ mới kèm cause thay vì tìm cách sửa tham chiếu của handler.

## 10. Tính hợp lệ của `catch` với checked exceptions

Trình biên dịch Java kiểm tra xem phần `try` **có thể** ném loại checked exception mà nhánh `catch` bắt hay không. Việc viết tùy ý nhiều loại checked mà không có nguồn ngoại lệ tương ứng có thể gây lỗi biên dịch.

**Cố ý không hợp lệ:**

```java
import java.io.IOException;
import java.sql.SQLException;

class InvalidUnusedAlternative {
    static void run() {
        try {
            throw new IOException("disk");
        } catch (IOException | SQLException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Trong `try` này, không có đường ném `SQLException` checked; `javac` có thể báo `exception SQLException is never thrown in body of corresponding try statement`. Để hợp lệ, chỉ bắt `IOException`, hoặc đảm bảo thao tác trong `try` thực sự có hợp đồng có thể ném `SQLException`.

**Không dùng `throws SQLException` trên phương thức bao ngoài để hợp thức hóa một nhánh `catch (SQLException)` mà bản thân `try` không thể ném.** Khả năng bắt checked exception được xét theo nội dung/hoạt động của `try`, không dựa vào việc khai báo tùy ý loại lỗi trên chữ ký của phương thức chứa nó.

Với unchecked `RuntimeException`, Java cho phép bắt rộng hơn ngay cả khi trong phần `try` không có câu lệnh ném tường minh. Quy tắc checked exception là một phần kiểm tra tĩnh và cần được xét riêng với việc chọn nhánh `catch` lúc runtime.

## 11. Không được dùng multi-catch để che giấu ngữ nghĩa interrupt

Một sai lầm phổ biến là coi `InterruptedException` như một lỗi tạm thời có thể ghi log rồi tiếp tục:

```java
try {
    Thread.sleep(100);
    readData();
} catch (InterruptedException | IOException ex) {
    System.out.println("failed: " + ex.getMessage());
    // Tiếp tục công việc ngay lập tức: có thể làm mất yêu cầu hủy.
}
```

Đây là đoạn minh họa trong một phương thức, giả định `readData() throws IOException`. Cú pháp multi-catch là hợp lệ, nhưng **chính sách xử lý có vấn đề**: khi `Thread.sleep` ném `InterruptedException`, trạng thái interrupt thường đã được xóa theo hợp đồng của phương thức này. Nếu chỉ in log rồi tiếp tục, chương trình có thể vô tình bỏ qua yêu cầu dừng.

Nếu tầng hiện tại cần xử lý riêng, tách rõ:

```java
try {
    Thread.sleep(100);
    readData();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} catch (IOException ex) {
    handleIoFailure(ex);
}
```

Đoạn này giả định nằm trong một phương thức `void` với `readData() throws IOException`, `handleIoFailure(IOException)` đã tồn tại, và nó không phải chương trình độc lập. Nhánh interrupt bảo toàn tín hiệu hủy, nhánh I/O xử lý theo chính sách riêng. Nếu một phương thức có thể khai báo tiếp `throws InterruptedException`, để lan truyền cũng là lựa chọn hợp lý tùy hợp đồng.

Điểm cần nhớ là **hai lỗi cùng có thể xuất hiện trong một `try` không đủ để gộp chúng**. Cần cùng quyết định cuối cùng khi một trong hai xảy ra.

## 12. Quan hệ cha/con ảnh hưởng cách nhóm ngoại lệ

Nếu các lỗi có quan hệ kế thừa, **không thể** viết một union như `catch (FileNotFoundException | IOException ex)` vì `FileNotFoundException extends IOException`. Có hai lựa chọn tùy chính sách:

```java
catch (IOException ex) {
    handleAllIoFailures(ex); // Chỉ khi mọi lỗi I/O cần chung chính sách.
}
```

hoặc hai handler riêng, **kiểu con trước kiểu cha**:

```java
catch (FileNotFoundException ex) {
    reportMissingFile(ex);
} catch (IOException ex) {
    reportOtherIoFailure(ex);
}
```

Đây là các nhánh minh họa trong `try` phù hợp, cần import và hàm xử lý của ứng dụng. Bắt `IOException` tuy bao phủ các lớp con nhưng **không có nghĩa** mọi lỗi I/O đều nên retry hoặc dùng fallback. Mức độ bao phủ của kiểu và sự phù hợp của chính sách là hai câu hỏi khác nhau.

## 13. Khác biệt giữa `catch` riêng có logic trùng và multi-catch

Nếu mã xử lý trùng nhau nhưng có thể cần mở rộng riêng sau này, có hai cách thường hợp lệ:

**Cách A — một nhánh chung:**

```java
catch (IOException | SQLException ex) {
    throw new DataLoadException("Data loading failed", ex);
}
```

**Cách B — hai nhánh riêng dùng một hàm:**

```java
catch (IOException ex) {
    throw translate(ex);
} catch (SQLException ex) {
    throw translate(ex);
}
```

Hai đoạn là **minh họa phần `catch` của một `try`**, giả định `DataLoadException` và `translate(Exception)` đã được định nghĩa với chữ ký thích hợp. Hai cách có thể có tác dụng tương đương khi chính sách thật sự giống nhau.

Multi-catch hợp lý khi **cả quyết định lẫn tác dụng** giống nhau và có khả năng giữ ổn định. Hai `catch` riêng hữu ích nếu muốn báo metric khác nhau, bổ sung dữ liệu ngữ cảnh riêng hoặc có khả năng phải đưa ra chính sách xử lý khác nhau. Không cần cố ép một cú pháp duy nhất cho tất cả tình huống.

Một nguyên tắc thực hành: nếu thân multi-catch chủ yếu gồm các nhánh phân biệt kiểu bằng `instanceof`, đó là dấu hiệu nên cân nhắc tách các `catch` tương ứng, trừ khi phần chung vẫn là phần xử lý chính.

## 14. Có thể gom ở tầng xử lý tập trung nhưng phải giữ nghĩa lỗi

Một số ứng dụng có ranh giới xử lý chung như command-line entry point, worker task boundary hoặc global API error handler. Ở đó, nhiều lỗi có thể dẫn đến một hành động chung: đánh dấu request thất bại, trả phản hồi nhất quán, kết thúc công việc và ghi nhận trạng thái.

Dù vậy, cần phân biệt:

- **Gom cách xuất lỗi:** cùng một định dạng phản hồi, cùng cách ghi log, cùng kiểm soát việc lộ thông tin cho người dùng.
- **Gom ý nghĩa lỗi:** hai lỗi được coi như nhau về khả năng retry, mất dữ liệu, tính toàn vẹn và phương án phục hồi.

Có thể gom cách xuất lỗi nhưng vẫn giữ thông tin loại lỗi trong dữ liệu nội bộ. Nếu một lỗi nên làm người dùng nhập lại tham số, còn lỗi kia là sự cố hệ thống, việc trả cùng mã lỗi hoặc cùng hướng dẫn khắc phục có thể gây hiểu lầm.

Khi một ranh giới dùng `catch (Exception ex)` tổng quát, nó còn có thể nhận nhiều unchecked exception như `NullPointerException`, `IllegalStateException`. Vì vậy, `catch (Exception)` cần chủ đích rộng hơn đáng kể so với `catch (IOException | SQLException)`. Nó cũng **không bắt nhánh `Error`**. Chỉ nên bắt rộng ở nơi có chính sách lỗi tập trung rõ ràng, không coi đó là cách che mọi lỗi để tiếp tục làm việc như thành công.

## 15. `finally`, tài nguyên và multi-catch

Nếu trong `try` một lỗi được ném rồi chọn một nhánh multi-catch, `finally` liên quan vẫn chạy theo quy tắc Java trước khi cấu trúc hoàn tất chuyển quyền điều khiển. `finally` không biến nhiều nhánh `catch` thành nhiều lần xử lý.

Với `try-with-resources`, việc tự động đóng tài nguyên xảy ra trước khi đi tới `catch` của cấu trúc đó. Nếu phần thân `try` ném lỗi và thao tác `close()` cũng ném lỗi, lỗi đóng thường được lưu trong `getSuppressed()` của ngoại lệ chính. **Chọn `catch` dựa trên ngoại lệ chính được ném ra**, không lần lượt chạy các nhánh cho từng suppressed exception.

Vì vậy, một multi-catch dùng để bọc lỗi nên giữ nguyên đối tượng `ex` làm cause. Danh sách `suppressed` gắn với đối tượng nguyên nhân sẽ còn có thể được truy nguyên. Việc chỉ sao chép message bỏ qua nhiều thông tin hữu ích khi phân tích sự cố.

Nếu chính khối `catch` hoặc `finally` lại ném lỗi mới, phải phân biệt lỗi **được chọn để bắt ban đầu** và lỗi **đi ra ngoài**. Các nhánh `catch` kế bên không nhận ngoại lệ mới vừa phát sinh trong chính nhánh `catch`.

## 16. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gom mọi lỗi vì “cùng ghi log”. | Các chính sách phục hồi khác nhau bị trộn lẫn. | So sánh kết quả cuối cùng, retry, rollback, fallback, hủy tác vụ trước khi gộp. |
| Viết `catch (Exception ex)` thay cho các kiểu cần xử lý. | Có thể vô tình nuốt `RuntimeException` không liên quan. | Dùng multi-catch liệt kê đúng các kiểu nếu cùng chính sách. |
| Liệt kê cả lớp cha và lớp con trong multi-catch. | Lỗi biên dịch. | Bắt lớp cha nếu thật sự cùng xử lý; hoặc tách nhánh con trước cha. |
| Gán lại tham số multi-catch. | Lỗi biên dịch do tham số implicitly final. | Giữ `ex` nguyên vẹn; tạo biến khác nếu cần. |
| Bọc lỗi chỉ bằng `ex.getMessage()`. | Mất `cause`, khó truy stack và suppressed exception. | Truyền `ex` vào constructor nhận `Throwable cause`. |
| Rethrow `ex` nhưng cho rằng tầng hiện tại đã xử lý xong. | Lỗi tiếp tục đi lên; tầng trên vẫn có trách nhiệm. | Khai báo `throws` phù hợp hoặc bắt ở tầng ranh giới. |
| Gộp `InterruptedException` với lỗi I/O rồi tiếp tục. | Có thể mất tín hiệu hủy thread. | Tách và truyền interrupt hoặc khôi phục cờ, kết thúc tác vụ. |
| Cố bắt checked exception không thể phát sinh từ `try`. | Compiler có thể báo “never thrown”. | Căn cứ vào chữ ký và nguồn ngoại lệ thực tế của `try`. |
| Gộp `Throwable` hay `Error` vào một nhánh xử lý nghiệp vụ thông thường. | Có thể che khuất sự cố nghiêm trọng và giả định phục hồi sai. | Giới hạn kiểu cần bắt vào các ngoại lệ có chiến lược rõ ràng. |
| Dùng fallback bất kể dữ liệu có an toàn không. | Hệ thống có thể trả kết quả sai hoặc không nhất quán. | Chỉ fallback khi có hợp đồng và điều kiện kiểm chứng hợp lệ. |

## 17. Checklist quyết định trước khi viết multi-catch

Khi cân nhắc `catch (A | B ex)`, hãy lần lượt kiểm tra:

1. **A và B độc lập về kiểu?** Nếu một kiểu kế thừa kiểu kia, cú pháp multi-catch không hợp lệ.
2. **Khối `try` có thể ném cả A và B theo quy tắc compile-time?** Đặc biệt quan trọng với checked exceptions.
3. **Cả hai cùng một cách xử lý từ đầu đến cuối?** Xem cả fallback, retry, rollback, thông báo và trạng thái cuối.
4. **Quyết định xử lý chung có thật sự an toàn?** Không áp dụng chính sách “trông có vẻ hợp lý” cho lỗi có thể phá vỡ bất biến.
5. **Lỗi gốc có được giữ?** Khi rethrow, dùng `throw ex;`; khi translation, dùng constructor nhận `cause`.
6. **Tầng gọi biết điều gì?** Nếu đã phục hồi, trả kết quả hợp lệ; nếu chưa, khai báo checked exception còn có thể thoát.
7. **Có yêu cầu interrupt hoặc dọn dẹp riêng?** Nếu có, cân nhắc nhánh riêng hoặc logic quản lý tài nguyên rõ ràng.

Nếu mọi câu trả lời ủng hộ cùng hành động, multi-catch giúp mã ngắn hơn và giữ chính sách nhất quán. Nếu có khác biệt quan trọng, các `catch` riêng giúp diễn đạt đúng cách hệ thống cần phản ứng.

## 18. Tự kiểm tra

**Câu 1.** `IOException` và `SQLException` đều phải chuyển thành `DataLoadException`, cùng message và giữ cause. Dùng chung multi-catch có hợp lý không?  
**Có thể hợp lý.** Hai lớp không có quan hệ cha/con và cùng chính sách translation tại ranh giới tầng. Kiểm tra rằng `try` có thể ném cả hai loại checked.

**Câu 2.** `FileNotFoundException` và `IOException` đều dùng cùng hành động. Viết `catch (FileNotFoundException | IOException ex)` được không?  
**Không.** Multi-catch cấm kiểu thay thế là lớp con của kiểu thay thế khác. Có thể dùng `catch (IOException ex)` nếu tất cả `IOException` thuộc phạm vi cần xử lý chung, hoặc dùng các nhánh riêng.

**Câu 3.** Hai `catch` cùng gọi hàm ghi log nhưng một nhánh return fallback còn nhánh kia rethrow. Có nên gộp không?  
**Thường không.** Chính sách cuối khác nhau; trích hàm ghi log chung mà giữ hai nhánh xử lý là cách rõ ràng hơn.

**Câu 4.** Một multi-catch có chạy hai lần khi cả hai kiểu đều được khai báo?  
**Không.** Một ngoại lệ chính được chọn xử lý trong một nhánh duy nhất tại thời điểm đó.

**Câu 5.** Có thể viết `ex = replacement;` trong `catch (IOException | SQLException ex)`?  
**Không.** Tham số multi-catch là implicitly final.

**Câu 6.** `throw ex;` và `throw new DataLoadException("failed", ex);` có giống nhau không?  
**Không.** Cách đầu ném lại cùng đối tượng; cách sau tạo ngoại lệ mới thuộc hợp đồng khác và liên kết nguyên nhân qua cause.

**Câu 7.** Có nên gom `InterruptedException` với `IOException`, in message rồi cho worker tiếp tục?  
**Không nên**, vì thao tác chờ có thể đã xóa cờ interrupt, làm yêu cầu hủy bị bỏ qua. Cần chính sách interrupt đúng.

**Câu 8.** Nếu `try` chỉ có khả năng ném `IOException` checked, tự thêm `SQLException` vào multi-catch có luôn được không?  
**Không.** Java có kiểm tra checked exception có thể được ném từ `try`; loại không có khả năng phát sinh có thể bị từ chối.

## Tham khảo

- [Java Language Specification, Java SE 17 — §14.20 The `try` Statement, multi-catch](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20).
- [JLS 17 — §14.20.1 Execution of `try-catch`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.1).
- [JLS 17 — §11.2.2 Exception Analysis of Statements (precise rethrow)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.2).
- [JLS 17 — §11.2.3 Exception Checking](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.3).
- [JLS 17 — §4.10.4 Least Upper Bound (kiểu chung của multi-catch)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.4).

**Ghi nhớ:** Nhiều ngoại lệ có thể dùng chung một cách xử lý khi **đều dẫn đến cùng quyết định đúng và an toàn**. Dùng multi-catch cho chính sách chung, tách nhánh khi ý nghĩa hoặc cách phục hồi khác nhau, và luôn giữ thông tin nguyên nhân khi dịch hoặc ném lại lỗi.
