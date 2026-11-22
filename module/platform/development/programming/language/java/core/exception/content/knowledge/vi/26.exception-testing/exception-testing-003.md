# Kiểm tra message, thuộc tính ngữ cảnh và cause khi phù hợp — Kiểm thử Java Exception

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định **hợp đồng lỗi** mà một phương thức Java phải cung cấp khi thất bại.
- Viết kiểm thử kiểm tra **loại exception**, **message**, **thuộc tính ngữ cảnh** và **cause** mà không ràng buộc quá mức vào các chi tiết triển khai.
- Dùng JUnit 5: <code>assertThrows</code>, <code>assertThrowsExactly</code>, <code>assertEquals</code>, <code>assertSame</code>, <code>assertInstanceOf</code>, <code>assertAll</code> và <code>assertDoesNotThrow</code> đúng mục đích.
- Chọn phép so sánh message phù hợp: khớp chính xác, kiểm tra phần ổn định, mã lỗi hoặc dữ liệu có cấu trúc.
- Chứng minh ngoại lệ khi chuyển tầng **giữ đúng đối tượng cause** và không mất ngữ cảnh giúp chẩn đoán.
- Kiểm tra exception do validation, nghiệp vụ, I/O, timeout hoặc thao tác bất đồng bộ theo hợp đồng từng API.
- Tránh các test “chỉ thấy có exception là đủ”, bắt quá rộng, so sánh stack trace nguyên văn hay dùng message JVM không được bảo đảm.
- Tách các thuộc tính **cần ổn định với người gọi** khỏi thông tin chẩn đoán nội bộ không nên khóa chặt bằng unit test.

Bài thuộc **Java Core — exception**, mục **Kiểm thử**. Các chương trình đầu tiên dùng Java 17+ độc lập. Những ví dụ JUnit 5 cần thư viện JUnit Jupiter trong dự án; bài không giả định JUnit là một phần sẵn có của JDK.

## 2. Kiểm thử exception là kiểm thử hợp đồng, không chỉ kiểm tra “có lỗi”

Giả sử phương thức <code>loadDocument("DOC-42")</code> đọc tài liệu từ repository. Nếu tầng dưới ném <code>IOException</code>, service có thể chuyển nó thành exception tầng ứng dụng. Người gọi không nhất thiết cần biết lớp I/O cụ thể, nhưng có thể phụ thuộc các yếu tố:

1. **Loại lỗi có ý nghĩa:** <code>DocumentLoadException</code>.
2. **Message đã công bố:** ví dụ “Không thể tải tài liệu”.
3. **Thuộc tính ngữ cảnh:** <code>documentId="DOC-42"</code>, <code>operation="LOAD"</code>.
4. **Cause:** giữ <code>IOException</code> ban đầu để chẩn đoán.
5. **Không tạo ra kết quả thành công giả:** thao tác lỗi phải được biểu diễn đúng theo hợp đồng.
6. **Không tiết lộ thông tin nội bộ** khi biến exception thành thông báo cho người dùng.

Một bài test chỉ viết:

~~~java
assertThrows(RuntimeException.class,
        () -> service.loadDocument("DOC-42"));
~~~

là **đoạn minh họa JUnit 5**. Nó rất yếu nếu service được yêu cầu ném một loại exception domain cụ thể, vì <code>NullPointerException</code>, <code>IllegalStateException</code> hoặc nhiều bug khác cũng là subclass của <code>RuntimeException</code>. Test có thể “xanh” dù service hỏng sai cách.

Một test có ý nghĩa hơn phải gắn với **những gì caller có quyền kỳ vọng**. Không phải thuộc tính nào của Throwable cũng cần assert. Chọn những phần thuộc hợp đồng công khai hoặc phục vụ một yêu cầu chẩn đoán cụ thể.

## 3. Các lớp thông tin có thể kiểm tra

| Khía cạnh | API quan sát | Khi nào nên kiểm tra |
| --- | --- | --- |
| Loại exception | <code>getClass()</code>, <code>instanceof</code>, JUnit <code>assertThrows</code> | Khi caller phân nhánh xử lý theo loại lỗi |
| Message | <code>getMessage()</code> | Khi message hoặc một phần nội dung là hợp đồng thực sự |
| Thuộc tính ngữ cảnh | Getter/record accessor do ứng dụng định nghĩa | Khi caller cần mã lỗi, ID tác vụ, thao tác, trạng thái retry |
| Cause trực tiếp | <code>getCause()</code> | Khi tầng trên cần giữ nguyên lỗi gốc hoặc phân loại nguyên nhân |
| Cause chain | Lặp qua <code>getCause()</code> | Khi một số tầng wrapper hợp lệ và cần tìm nguyên nhân sâu hơn |
| Suppressed exceptions | <code>getSuppressed()</code> | Với cleanup, try-with-resources hoặc lỗi phụ cần lưu |
| Stack trace | <code>getStackTrace()</code> | Chỉ khi đặc tính ghi trace là yêu cầu chẩn đoán cụ thể |
| Mã lỗi công khai | <code>code()</code>, <code>getErrorCode()</code> hoặc error DTO | Khi client không nên phân tích message tự do |
| Ranh giới lỗi async | <code>Future.get()</code>, <code>CompletableFuture.join()</code> | Khi lỗi được bọc theo hợp đồng async |

### Điều không nên mặc định assert

- Số dòng nguồn trong stack trace.
- Thứ tự hoặc số lượng frame cụ thể.
- Message của NPE, SQLException hay IOException do JVM/driver/thư viện tạo nếu không thuộc hợp đồng của bạn.
- Toàn văn log do framework render trong mọi phiên bản.
- Một message chứa đường dẫn file, tên máy chủ, token hay chi tiết nội bộ vốn không được công bố ổn định.

**Câu hỏi trước khi viết assert:** “Nếu triển khai thay đổi mà hành vi caller vẫn đúng, assertion này có nên tiếp tục PASS không?”

## 4. assertThrows: bắt exception và trả về chính đối tượng đó

JUnit 5 cung cấp:

~~~java
DocumentLoadException thrown =
        assertThrows(DocumentLoadException.class,
                () -> service.loadDocument("DOC-42"));
~~~

Đây là **đoạn JUnit 5 minh họa**, giả định có <code>service</code> và lớp <code>DocumentLoadException</code>. Nếu executable không ném exception phù hợp, assertion thất bại. Nếu ném đúng kiểu yêu cầu hoặc một subtype được chấp nhận, assertion thành công và trả về đối tượng Throwable bắt được.

Bạn có thể kiểm tra tiếp:

~~~java
assertEquals("Không thể tải tài liệu", thrown.getMessage());
assertEquals("DOC-42", thrown.documentId());
assertEquals("LOAD", thrown.operation());
assertNotNull(thrown.getCause());
~~~

Những assertion này chỉ nên dùng khi service công bố đúng các thuộc tính như ví dụ. Nếu message được phép thay đổi theo locale, không nên bắt test khớp một câu tiếng Việt duy nhất. Nếu caller cần mã lỗi ổn định, kiểm tra mã lỗi trước.

### Tại sao phải giữ biến thrown?

Việc viết riêng lẻ:

~~~java
assertThrows(DocumentLoadException.class,
        () -> service.loadDocument("DOC-42"));
~~~

chỉ kiểm tra loại exception. Lưu kết quả vào <code>thrown</code> giúp kiểm tra message, field và cause **trên cùng lần thực thi**, tránh gọi operation thêm lần nữa.

Đặc biệt với I/O, transaction hay thao tác có side effect, đừng gọi service hai hoặc ba lần chỉ để kiểm tra từng thuộc tính. Những lần gọi có thể trả trạng thái khác nhau, phát sinh chi phí hoặc tạo tác dụng phụ không mong muốn.

## 5. assertThrows và assertThrowsExactly khác nhau

Trong JUnit Jupiter:

- <code>assertThrows(Expected.class, executable)</code> chấp nhận <code>Expected</code> **hoặc subclass** của nó.
- <code>assertThrowsExactly(Expected.class, executable)</code> yêu cầu **chính xác class đó**, không chấp nhận subclass. API này có trong các phiên bản JUnit Jupiter hiện đại, bao gồm JUnit 5.8+.

Ví dụ minh họa:

~~~java
class ApplicationException extends RuntimeException {
}

class DocumentException extends ApplicationException {
}

assertThrows(ApplicationException.class,
        () -> { throw new DocumentException(); });

assertThrowsExactly(DocumentException.class,
        () -> { throw new DocumentException(); });
~~~

Đây là **đoạn JUnit 5 minh họa**. Cả hai assertion trên sẽ thành công.

Nếu hợp đồng cho phép hệ thống mở rộng lỗi bằng subclass, <code>assertThrowsExactly</code> có thể khiến test quá chặt. Nếu API thực sự yêu cầu đúng loại lỗi không phân cấp, phép kiểm tra exact mới phù hợp.

### Phân biệt việc bắt rộng và kiểm tra có chủ đích

<code>assertThrows(RuntimeException.class, ...)</code> có thể hợp lệ với một test chỉ yêu cầu bất kỳ lỗi runtime nào. Nhưng với validation cụ thể, hãy kiểm tra <code>IllegalArgumentException</code> hoặc lớp domain được công bố.

Một lựa chọn sai thường gặp:

~~~java
assertThrows(Exception.class, () -> parseAndSave(input));
~~~

Đây là **mã minh họa**. Test này có thể PASS vì một bug không liên quan như I/O thất bại, thay vì lỗi validation mong muốn. Hãy thu hẹp loại exception và xem thêm các thuộc tính ngữ nghĩa của nó.

## 6. Test message: khi nào so sánh chính xác?

Với một thông báo **do ứng dụng sở hữu, ổn định và được công bố là hợp đồng**, có thể dùng:

~~~java
assertEquals("Số lượng phải lớn hơn 0", thrown.getMessage());
~~~

Ưu điểm: test phát hiện thay đổi không mong muốn về wording, dấu tiếng Việt hoặc thông báo dành cho caller. Nhược điểm: thay đổi nhỏ về dấu câu/bản dịch cũng làm test fail.

So sánh chính xác phù hợp khi:

- Message là một phần hợp đồng có chủ đích.
- Hệ thống không áp dụng localization ở lớp đang test.
- Người dùng/caller cần nhận đúng template này.
- Test nhằm bảo vệ một yêu cầu cụ thể về văn bản, ví dụ một câu thông báo accessibility/UX đã được duyệt.

### Khi nào chỉ kiểm tra phần ổn định?

Nếu message được phép thêm chi tiết hoặc ID do ứng dụng quản lý, một assertion mềm hơn có thể hợp lý:

~~~java
assertTrue(thrown.getMessage().contains("Không thể tải tài liệu"));
~~~

Đây là **đoạn JUnit 5 minh họa**. Tuy nhiên, phép <code>contains</code> có thể quá yếu hoặc cho PASS giả. Ví dụ một message dài chứa cụm từ đó nhưng diễn đạt sai trạng thái. Có thể kiểm tra <code>startsWith</code> hoặc một mẫu được duyệt, nhưng chỉ khi thật sự là hợp đồng.

Nếu message có thể null, gọi <code>getMessage().contains(...)</code> sẽ tự ném <code>NullPointerException</code>, khiến báo lỗi test khó hiểu. Có thể dùng:

~~~java
String message = thrown.getMessage();
assertNotNull(message);
assertTrue(message.contains("Không thể tải tài liệu"));
~~~

Những dòng này là **mã JUnit minh họa**. Nó cho failure rõ hơn khi exception không có message.

### Khi nào không nên test text?

Message của <code>NumberFormatException</code> do <code>Integer.parseInt()</code>, <code>NullPointerException</code> do runtime hoặc <code>IOException</code> do filesystem không phải văn bản mà ứng dụng toàn quyền kiểm soát. Nếu test cần nhận diện loại lỗi, assert class; nếu có wrapper do ứng dụng định nghĩa, kiểm tra message của wrapper hoặc mã lỗi ổn định, không khóa vào chi tiết của thư viện bên dưới.

**Quy tắc:** kiểm tra giá trị caller có quyền dựa vào, không kiểm tra chi tiết tình cờ của một implementation.

## 7. Thuộc tính ngữ cảnh: nên là dữ liệu, không chỉ nằm trong chuỗi

Một lớp exception tầng ứng dụng có thể có:

~~~java
final class DocumentLoadException extends RuntimeException {
    private final String documentId;
    private final String operation;

    DocumentLoadException(
            String message, String documentId,
            String operation, Throwable cause) {
        super(message, cause);
        this.documentId = documentId;
        this.operation = operation;
    }

    String documentId() {
        return documentId;
    }

    String operation() {
        return operation;
    }
}
~~~

Đây là **định nghĩa lớp minh họa**, có thể dùng như một lớp riêng hoặc nested class nếu điều chỉnh phạm vi. Hai field cung cấp dữ liệu có cấu trúc cho tầng gọi.

Test:

~~~java
assertEquals("DOC-42", error.documentId());
assertEquals("LOAD", error.operation());
~~~

Tốt hơn việc phân tích message:

~~~java
assertTrue(error.getMessage().contains("DOC-42"));
~~~

Chứa ID trong message chưa chứng minh object có đúng thuộc tính context mà caller cần. Khi giữ ID trong field, ứng dụng có thể thay đổi hoặc dịch message mà không phá hợp đồng dữ liệu.

### Chọn thuộc tính nào là context?

Chỉ giữ những thuộc tính cần cho ngữ nghĩa API hoặc chẩn đoán:

- ID tài liệu/đơn hàng nếu được phép sử dụng trong tầng hiện tại.
- Mã thao tác như <code>LOAD</code>, <code>SAVE</code>, <code>DELETE</code>.
- Mã lỗi domain cố định như <code>DOCUMENT_UNAVAILABLE</code>.
- Cờ <code>retryable</code> nếu đã xác định chính sách retry thực sự hợp lệ.
- Tham chiếu correlation/request ID an toàn theo hợp đồng.
- Trạng thái đối tượng hoặc loại tài nguyên nếu không vi phạm quyền truy cập.

Không lưu mật khẩu, access token hoặc toàn bộ payload nhạy cảm vào exception context chỉ để test tiện. Context có thể bị log hoặc truyền qua nhiều tầng.

### Thông điệp không phải luôn là public message

Một exception nội bộ có thể có message chẩn đoán chứa ID nội bộ. Response gửi tới người dùng thường nên được tạo từ **mã lỗi ổn định và template an toàn**, không gửi trực tiếp <code>Throwable.getMessage()</code>. Vì vậy test service và test error mapper có thể kiểm tra hai hợp đồng **khác nhau**.

## 8. Kiểm tra cause: kiểu, nội dung hay identity?

Khi một tầng chuyển <code>IOException</code> thành <code>DocumentLoadException</code>, câu hỏi quan trọng là “exception gốc có được giữ không?”.

~~~java
try {
    return repository.read(documentId);
} catch (IOException original) {
    throw new DocumentLoadException(
            "Không thể tải tài liệu",
            documentId,
            "LOAD",
            original);
}
~~~

Đây là **đoạn mã minh họa trong một phương thức phù hợp**. Constructor nhận <code>original</code> làm cause, nên:

~~~java
assertSame(original, translated.getCause());
~~~

là phép kiểm tra mạnh nhất nếu test có thể giữ **chính instance gốc**. <code>assertSame</code> xác nhận hai tham chiếu trỏ tới cùng object. Điều này mạnh hơn:

~~~java
assertEquals(original.getClass(),
        translated.getCause().getClass());
~~~

vì hai exception khác nhau có thể cùng class.

### So sánh ba cấp độ

| Assertion | Chứng minh điều gì | Giới hạn |
| --- | --- | --- |
| <code>assertNotNull(error.getCause())</code> | Có cause | Không biết cause đúng hay không |
| <code>assertInstanceOf(IOException.class, error.getCause())</code> | Cause thuộc loại kỳ vọng | Chưa chứng minh là chính instance nguồn |
| <code>assertSame(original, error.getCause())</code> | Cause trực tiếp đúng **cùng object** | Chỉ phù hợp nếu hợp đồng yêu cầu giữ nguyên cause |

Trong JUnit 5, <code>assertEquals</code> trên exception thường không phải lựa chọn tương đương với <code>assertSame</code>; các Throwable thông thường không định nghĩa equality theo toàn bộ stack trace, type, message và cause. Nếu muốn kiểm tra identity, dùng <code>assertSame</code> cho rõ.

### Vì sao không chỉ so message của cause?

Một wrapper có thể sao chép message gốc nhưng đánh mất stack trace:

~~~java
throw new DocumentLoadException(
        original.getMessage(),
        documentId,
        "LOAD",
        null);
~~~

Đây là **mã minh họa cố ý không phù hợp khi cần bảo toàn cause**. Caller nhìn thấy một message giống nhau, nhưng <code>getCause() == null</code> và mất đường truy nguyên exception ban đầu. Test identity bằng <code>assertSame</code> phát hiện lỗi đó.

Tuy nhiên, không phải mọi API cần giữ **cause trực tiếp** là cùng object. Một số tầng có chủ đích dùng thêm wrapper trung gian. Khi hợp đồng chỉ yêu cầu “cause chain giữ được lỗi gốc”, test cần duyệt chuỗi và kiểm tra đúng cấp thay vì cứng nhắc yêu cầu một tầng duy nhất.

## 9. Ví dụ Java 17 độc lập: hợp đồng message, context và cause

Chương trình này dùng cơ chế tự kiểm tra đơn giản để chạy được chỉ với JDK. Nó không thay JUnit trong dự án nhưng thể hiện rõ cách kiểm tra cùng một exception qua nhiều thuộc tính.

Lưu tệp **ExceptionContractDemo.java**:

~~~java
import java.io.IOException;

public class ExceptionContractDemo {

    static final class DocumentLoadException extends RuntimeException {
        private final String documentId;
        private final String operation;

        DocumentLoadException(
                String message, String documentId,
                String operation, Throwable cause) {
            super(message, cause);
            this.documentId = documentId;
            this.operation = operation;
        }

        String documentId() {
            return documentId;
        }

        String operation() {
            return operation;
        }
    }

    static final class FakeRepository {
        final IOException original =
                new IOException("simulated storage failure");

        String read(String documentId) throws IOException {
            throw original;
        }
    }

    static String load(String documentId, FakeRepository repository) {
        if (documentId == null || documentId.isBlank()) {
            throw new IllegalArgumentException("documentId không được trống");
        }

        try {
            return repository.read(documentId);
        } catch (IOException original) {
            throw new DocumentLoadException(
                    "Không thể tải tài liệu",
                    documentId,
                    "LOAD",
                    original);
        }
    }

    static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Contract failed");
        }
    }

    public static void main(String[] args) {
        FakeRepository repository = new FakeRepository();

        try {
            load("DOC-42", repository);
            throw new AssertionError("Expected DocumentLoadException");
        } catch (DocumentLoadException failure) {
            require("Không thể tải tài liệu".equals(
                    failure.getMessage()));
            require("DOC-42".equals(failure.documentId()));
            require("LOAD".equals(failure.operation()));
            require(failure.getCause() == repository.original);

            System.out.println("Type: "
                    + failure.getClass().getSimpleName());
            System.out.println("Message: " + failure.getMessage());
            System.out.println("Context documentId: "
                    + failure.documentId());
            System.out.println("Context operation: "
                    + failure.operation());
            System.out.println("Same original cause: "
                    + (failure.getCause() == repository.original));
            System.out.println("Contract: PASS");
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 ExceptionContractDemo.java
java ExceptionContractDemo
~~~

**Stdout chính xác:**

~~~text
Type: DocumentLoadException
Message: Không thể tải tài liệu
Context documentId: DOC-42
Context operation: LOAD
Same original cause: true
Contract: PASS
~~~

### Giải thích

1. <code>FakeRepository.original</code> giữ một <code>IOException</code> có identity ổn định để test đối chiếu.
2. <code>load</code> có guard cho ID không hợp lệ, sau đó bắt đúng <code>IOException</code> ở tầng repository.
3. Wrapper giữ message có ý nghĩa ở tầng service, hai field context và **chính đối tượng cause**.
4. Khối <code>catch (DocumentLoadException)</code> chỉ chạy với loại error phù hợp. Các điều kiện <code>require</code> làm chương trình báo thất bại bằng <code>AssertionError</code> nếu bất kỳ thuộc tính nào không đúng.
5. Mọi kết quả được in sau khi các kiểm tra PASS, nên stdout xác định, không phụ thuộc thời gian hoặc thread pool.
6. Message của <code>IOException</code> gốc được giữ cho chẩn đoán, nhưng stdout ví dụ không xuất toàn bộ exception kỹ thuật cho người dùng.

Tại dự án thật, nên dùng framework test để báo rõ assertion nào thất bại, chứ không tự viết <code>require</code> chung như minh họa.

## 10. JUnit 5: bài test hoàn chỉnh cho exception có ngữ cảnh

Ví dụ dưới đây dùng JUnit Jupiter. Nó cho thấy cách kiểm tra bốn nhóm thuộc tính trong **một lần gọi** và cách kiểm tra cả nhánh validation.

Lưu tệp **DocumentServiceTest.java** trong source set kiểm thử của dự án, nơi JUnit Jupiter đã được cấu hình:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import org.junit.jupiter.api.Test;

class DocumentServiceTest {

    static final class DocumentLoadException extends RuntimeException {
        private final String documentId;
        private final String operation;

        DocumentLoadException(
                String message,
                String documentId,
                String operation,
                Throwable cause) {
            super(message, cause);
            this.documentId = documentId;
            this.operation = operation;
        }

        String documentId() {
            return documentId;
        }

        String operation() {
            return operation;
        }
    }

    static final class FakeRepository {
        final IOException original =
                new IOException("disk temporarily unavailable");

        String read(String documentId) throws IOException {
            throw original;
        }
    }

    static String loadDocument(String documentId, FakeRepository repository) {
        if (documentId == null || documentId.isBlank()) {
            throw new IllegalArgumentException(
                    "documentId không được trống");
        }

        try {
            return repository.read(documentId);
        } catch (IOException original) {
            throw new DocumentLoadException(
                    "Không thể tải tài liệu",
                    documentId,
                    "LOAD",
                    original);
        }
    }

    @Test
    void translationKeepsMessageContextAndOriginalCause() {
        FakeRepository repository = new FakeRepository();

        DocumentLoadException error = assertThrowsExactly(
                DocumentLoadException.class,
                () -> loadDocument("DOC-7", repository));

        assertAll("DocumentLoadException contract",
                () -> assertEquals(
                        "Không thể tải tài liệu", error.getMessage()),
                () -> assertEquals("DOC-7", error.documentId()),
                () -> assertEquals("LOAD", error.operation()),
                () -> assertSame(repository.original, error.getCause()));
    }

    @Test
    void blankDocumentIdReportsValidationError() {
        FakeRepository repository = new FakeRepository();

        IllegalArgumentException error = assertThrowsExactly(
                IllegalArgumentException.class,
                () -> loadDocument("   ", repository));

        assertEquals("documentId không được trống", error.getMessage());
        assertNull(error.getCause());
    }
}
~~~

### Điều kiện chạy

- Java 17+ để biên dịch mã ví dụ.
- Thư viện **JUnit Jupiter** (JUnit 5) được khai báo cho test source set.
- Test runner JUnit Jupiter được kích hoạt qua Maven Surefire, Gradle Test hoặc IDE phù hợp.
- <code>assertThrowsExactly</code> cần phiên bản JUnit Jupiter có API đó (JUnit 5.8+).

Nếu dự án dùng Maven với cấu trúc chuẩn, ví dụ có thể đặt tại:

~~~text
src/test/java/DocumentServiceTest.java
~~~

Đây là **đường dẫn gợi ý cấu trúc dự án**, không phải tệp được tạo trong công việc hiện tại. Chạy bằng công cụ build của dự án sau khi đã có dependency phù hợp, chẳng hạn:

~~~bash
mvn test
~~~

Đây là **lệnh cho dự án Maven đã cấu hình test**, không phải lệnh có thể chạy trực tiếp với JDK trần. Kết quả kỳ vọng là **2 tests passed**, không có stdout nghiệp vụ cố định vì JUnit runner có định dạng báo cáo riêng theo tool/version.

### Vì sao dùng assertAll?

<code>assertAll</code> giúp gom nhiều assertion độc lập cho cùng error. Khi nhiều thuộc tính cùng sai, framework có thể báo nhóm lỗi assertion, giúp thấy được bức tranh thay vì dừng ngay ở điều kiện đầu tiên. Tuy nhiên, mọi expression cần chuẩn bị an toàn: nếu trước khi vào <code>assertAll</code> đã dereference một giá trị null bất ngờ, test vẫn có thể hỏng theo cách khó đọc.

<code>assertThrowsExactly</code> trong ví dụ là lựa chọn vì bài cố tình định nghĩa loại wrapper cụ thể. Nếu hợp đồng chấp nhận subclass, dùng <code>assertThrows</code> sẽ linh hoạt hơn.

## 11. Kiểm tra nhánh không ném lỗi: assertDoesNotThrow

Kiểm thử exception cũng cần chứng minh **đường hợp lệ không phát sinh lỗi**. Ví dụ phương thức validation:

~~~java
static void validateQuantity(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "quantity must be positive");
    }
}
~~~

Đây là **đoạn Java minh họa** trong lớp phù hợp.

JUnit:

~~~java
assertDoesNotThrow(() -> validateQuantity(1));

IllegalArgumentException error = assertThrowsExactly(
        IllegalArgumentException.class,
        () -> validateQuantity(0));

assertEquals("quantity must be positive", error.getMessage());
~~~

Đây là **mã JUnit 5 minh họa**. Kết hợp cả hai trường hợp giúp tránh một implementation luôn ném lỗi hoặc luôn trả về bình thường mà vẫn lọt qua bộ test chỉ có một nhánh.

Với method trả giá trị:

~~~java
String result = assertDoesNotThrow(() -> normalize("  a  "));
assertEquals("a", result);
~~~

Đây là **mã minh họa**, giả định <code>normalize</code> được thiết kế trả về chuỗi đã trim. Nếu một operation thực sự được phép ném một số exception có kiểm soát nhưng caller vẫn chấp nhận được, không nên ép test dùng <code>assertDoesNotThrow</code> một cách máy móc.

## 12. Cause chain: kiểm tra cấp nào là hợp đồng?

Một hệ thống nhiều tầng có thể sinh ra:

~~~text
HttpAdapterException
   |
   +-- ServiceException
          |
          +-- IOException
~~~

Nếu hợp đồng của adapter chỉ yêu cầu **bảo toàn nguyên nhân gốc**, đừng viết test bắt buộc hai cấp wrapper cố định nếu việc thêm hoặc bỏ một wrapper không ảnh hưởng caller.

Hai cách kiểm tra:

### 12.1. Kiểm tra cause trực tiếp

~~~java
assertSame(original, serviceError.getCause());
~~~

Phù hợp khi constructor/service cam kết giữ chính <code>original</code> ở cấp cause đầu tiên.

### 12.2. Kiểm tra một nguyên nhân nằm trong chain

Nếu có thêm wrapper hợp lệ:

~~~java
Throwable current = outer;
boolean containsOriginal = false;

while (current != null) {
    if (current == original) {
        containsOriginal = true;
        break;
    }
    current = current.getCause();
}

assertTrue(containsOriginal);
~~~

Đây là **đoạn JUnit 5 minh họa** với <code>outer</code> và <code>original</code> được tạo trước, giả định chain không bị tạo vòng. Trong thư viện chẩn đoán tổng quát, có thể thêm tập nhận diện identity để phòng chuỗi Throwable bất thường. Đừng thay identity check bằng so sánh message vì nhiều exception có thể có cùng văn bản.

### Không unwrap bừa bãi

Một exception có thể có cause hợp lệ nhưng không đại diện cho failure mà tầng gọi cần xử lý trực tiếp. Ví dụ một lớp domain đã cố tình chuyển <code>SQLException</code> thành <code>DocumentLoadException</code>. Nếu code test hoặc application chỉ đi tìm root cause để quyết định hành vi nghiệp vụ, nó có thể bỏ qua chính sách đã được đặt ở tầng domain.

**Kiểm tra cả ngữ nghĩa lớp wrapper và bảo toàn nguyên nhân khi phù hợp**, không chỉ root cause.

## 13. Ví dụ Java 17 độc lập: chuỗi cause và suppressed exception

Lưu tệp **CauseChainDemo.java**:

~~~java
import java.io.IOException;

public class CauseChainDemo {

    static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected exception structure");
        }
    }

    public static void main(String[] args) {
        IOException root = new IOException("read timeout");
        IllegalStateException middle =
                new IllegalStateException("storage failure", root);
        RuntimeException outer =
                new RuntimeException("request failure", middle);
        IOException cleanup = new IOException("cleanup failure");
        outer.addSuppressed(cleanup);

        Throwable directCause = outer.getCause();
        Throwable deepestCause = directCause.getCause();
        Throwable[] suppressed = outer.getSuppressed();

        require(directCause == middle);
        require(deepestCause == root);
        require(suppressed.length == 1);
        require(suppressed[0] == cleanup);

        System.out.println("Outer: "
                + outer.getClass().getSimpleName());
        System.out.println("Direct cause: "
                + directCause.getClass().getSimpleName());
        System.out.println("Root cause: "
                + deepestCause.getClass().getSimpleName());
        System.out.println("Root identity: " + (deepestCause == root));
        System.out.println("Suppressed count: " + suppressed.length);
        System.out.println("Suppressed identity: "
                + (suppressed[0] == cleanup));
        System.out.println("Checks: PASS");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CauseChainDemo.java
java CauseChainDemo
~~~

**Stdout chính xác:**

~~~text
Outer: RuntimeException
Direct cause: IllegalStateException
Root cause: IOException
Root identity: true
Suppressed count: 1
Suppressed identity: true
Checks: PASS
~~~

### Những gì ví dụ chứng minh

- <code>outer.getCause()</code> trỏ tới **cùng instance** <code>middle</code>.
- <code>middle.getCause()</code> trỏ tới **cùng instance** <code>root</code>.
- <code>getSuppressed()</code> chứa exception phụ <code>cleanup</code>, khác với cause chain.
- Đọc cause và suppressed không yêu cầu in cả stack trace.
- Hai đường lưu thông tin lỗi này có ngữ nghĩa khác nhau: cause mô tả nguyên nhân, suppressed lưu các exception bổ sung theo cơ chế sử dụng.

Không nên đưa tất cả exception vào cause chain theo một thứ tự tùy tiện chỉ để thỏa test; điều đó làm sai ngữ nghĩa. Với nhiều lỗi độc lập, có thể cần kiểu kết quả tổng hợp, danh sách lỗi hoặc chính sách riêng.

## 14. Checked exception cũng cần kiểm tra hợp đồng

Không chỉ <code>RuntimeException</code> mới được kiểm thử bằng <code>assertThrows</code>. Một API Java có thể khai báo:

~~~java
String read(Path path) throws IOException {
    return Files.readString(path);
}
~~~

Đây là **đoạn minh họa**, cần import <code>Path</code>, <code>Files</code> và <code>IOException</code>. Khi test với điều kiện I/O xác định và phù hợp, có thể viết:

~~~java
IOException error = assertThrows(IOException.class,
        () -> reader.read(path));
~~~

Đây là **mã JUnit 5 minh họa**. Nhưng test không nên giả định một lỗi I/O cụ thể chỉ dựa vào trạng thái filesystem thật trên máy chạy CI. Cùng một tệp có thể bị xóa, thay quyền hoặc được tạo bởi process khác.

Nếu mục tiêu là kiểm tra **cách service chuyển IOException**, hãy dùng fake repository có thể ném **đúng instance** được tạo sẵn, như ví dụ trong phần 9–10. Điều đó giúp test:

- Không phụ thuộc vào hệ điều hành.
- Không cần quyền đặc biệt hay đường dẫn cứng.
- Không mở file thật và gây race.
- So sánh cause identity rõ ràng.
- Dễ tái hiện trên CI và máy lập trình viên.

Với integration test filesystem, có thể dùng thư mục tạm và dọn tài nguyên đúng cách. Tuy nhiên, đó là test về tích hợp I/O, không phải đơn vị nhỏ nhất cần dùng để kiểm tra hợp đồng exception của service.

## 15. Test thông báo dành cho người dùng khác test message nội bộ

Một lỗi hạ tầng có thể chứa message kiểu:

~~~text
connection refused to internal-db:5432
~~~

Tầng service giữ cause này cho chẩn đoán, nhưng API không nên đưa message thô đó cho người dùng. Thay vào đó, error mapper có thể trả:

~~~json
{
  "code": "DOCUMENT_UNAVAILABLE",
  "message": "Không thể tải tài liệu lúc này. Vui lòng thử lại sau.",
  "requestId": "RQ-1042"
}
~~~

Đây là **JSON minh họa**, không phải response từ một server được khởi chạy trong bài.

Hai bộ test nên tách nhau:

1. **Service test:** wrapper đúng loại, message nội bộ nếu là hợp đồng, context và cause được giữ.
2. **API/error mapper test:** mã lỗi, status và thông điệp công khai đúng; không có hostname, token, SQL, đường dẫn nội bộ hoặc stack trace.

Một test bảo mật có thể chèn secret giả vào <code>IOException</code> nguồn rồi kiểm tra **toàn bộ payload response** không chứa secret đó. Không chỉ kiểm tra một field message nếu các field khác cũng có thể làm lộ dữ liệu.

### Không dựa vào exact text của mọi lỗi

Một public message được bản địa hóa theo ngôn ngữ có thể khác nhau theo locale. Khi đó test code/status/semantics và chỉ kiểm tra text cụ thể ở test dành riêng cho locale/template. Đừng cố dùng duy nhất một assertion exact tiếng Việt cho mọi locale.

**Khả năng chẩn đoán nội bộ và tính an toàn công khai là hai thuộc tính độc lập**. Một hệ thống có thể giữ cause rất tốt nhưng leak lỗi kỹ thuật ở response; ngược lại, response an toàn nhưng service làm mất cause. Cần kiểm thử cả hai nếu đều là yêu cầu.

## 16. Không kiểm tra stack trace nguyên văn nếu không cần

Một anti-pattern:

~~~java
assertEquals(
        "at com.example.Service.load(Service.java:42)",
        error.getStackTrace()[0].toString());
~~~

Đây là **mã JUnit minh họa cố ý không khuyến nghị**. Số dòng, tên file, thứ tự frame và compiler/JIT/test runner có thể làm test lỗi dù hệ thống vẫn đúng.

Nếu yêu cầu là “exception có stack trace giúp chẩn đoán”, có thể kiểm tra mức độ hợp lý:

~~~java
assertTrue(error.getStackTrace().length > 0);
~~~

Nhưng ngay cả assertion này cũng có giới hạn: một số exception được thiết kế với <code>writableStackTrace=false</code>, hoặc runtime có tối ưu phụ thuộc JVM. Nếu hệ thống đã quyết định dùng exception nhẹ, test cần phản ánh chính sách đó chứ không áp điều kiện chung cho mọi Throwable.

Nếu mục tiêu chính là giữ nguyên cause, <code>assertSame(original, error.getCause())</code> thường bám sát hợp đồng hơn so sánh số lượng frame.

## 17. Kiểm thử message có tham số động

Một message có thể có ID, số lượng hoặc tên thao tác. Đừng chỉ kiểm tra “có một chuỗi bất kỳ”:

~~~java
assertNotNull(error.getMessage());
~~~

Assertion này không chứng minh message có đủ ngữ cảnh. Tuy nhiên, việc đưa ID trực tiếp vào message cũng không phải luôn là lựa chọn tốt.

**Nếu API có field có cấu trúc**, ưu tiên:

~~~java
assertEquals("DOC-7", error.documentId());
assertEquals("LOAD", error.operation());
~~~

Và chỉ kiểm tra phần message ổn định:

~~~java
assertTrue(error.getMessage().startsWith("Không thể tải tài liệu"));
~~~

Nếu message chính xác đã được công bố là contract:

~~~java
assertEquals("Không thể tải tài liệu DOC-7",
        error.getMessage());
~~~

Đây đều là **đoạn mã JUnit 5 minh họa**; chúng đại diện cho **những hợp đồng giả định khác nhau**, không phải ba assertion cùng bắt buộc đặt lên một implementation.

### Message có thể null

Theo hợp đồng <code>Throwable</code>, message có thể null. Có API cố ý tạo exception không message nhưng có error code và context riêng. Vì vậy test phải biết trường hợp nào yêu cầu message khác null, trường hợp nào chấp nhận null.

Không gọi <code>getMessage().contains(...)</code> trên assumption mù quáng; nếu cần, kiểm tra <code>assertNotNull</code> trước để tránh chính test ném NPE khó hiểu.

## 18. assertInstanceOf, class equality và cấp trừu tượng

JUnit Jupiter cung cấp <code>assertInstanceOf</code> cho nhu cầu khẳng định object thuộc một class/interface; một số phiên bản có overload trả về giá trị đã được ép kiểu để dùng tiếp.

Ví dụ:

~~~java
Throwable cause = error.getCause();
IOException io = assertInstanceOf(IOException.class, cause);
assertNotNull(io.getMessage());
~~~

Đây là **mã JUnit 5 minh họa**. Nếu hợp đồng yêu cầu cause là một loại ngoại lệ I/O hoặc subtype của nó, assertion này phù hợp.

Nếu cần đúng class:

~~~java
assertEquals(IOException.class, cause.getClass());
~~~

Nhưng hãy cẩn trọng: một implementation thay <code>IOException</code> bằng subclass có ý nghĩa hơn có thể vẫn đúng hợp đồng, còn phép so class exact sẽ khiến test fail. Với test về cause identity, ưu tiên <code>assertSame(original, cause)</code> khi instance nguồn có thể kiểm soát được.

**Không biến test thành bản sao của cấu trúc nội bộ.** Test nên bảo vệ contract người dùng của tầng đó, không ép các lớp wrapper/driver phải giữ đúng class cụ thể nếu điều đó không được công bố.

## 19. Exception trong Future và CompletableFuture

Khi tác vụ chạy bất đồng bộ, exception có thể không xuất hiện trực tiếp tại lời gọi khởi tạo hoặc submit.

Với <code>Future.get()</code>, lỗi từ task thường được báo qua <code>ExecutionException</code>. Với <code>CompletableFuture.join()</code>, lỗi completion thông thường được báo qua <code>CompletionException</code>; cancellation có thể ném <code>CancellationException</code> trực tiếp theo ngữ nghĩa từng future.

Ví dụ JUnit minh họa:

~~~java
IOException original = new IOException("network error");
CompletableFuture<String> failed = new CompletableFuture<>();
failed.completeExceptionally(original);

CompletionException wrapper =
        assertThrows(CompletionException.class, failed::join);

assertSame(original, wrapper.getCause());
~~~

Đây là **mã JUnit 5 minh họa**; cần import các lớp <code>java.io</code> và <code>java.util.concurrent</code> tương ứng. Khi gọi <code>get()</code> thay vì <code>join()</code>, loại exception báo cho caller sẽ khác:

~~~java
ExecutionException wrapper =
        assertThrows(ExecutionException.class, failed::get);

assertSame(original, wrapper.getCause());
~~~

Đây cũng là **mã JUnit 5 minh họa** sử dụng future đã hoàn tất lỗi ở đoạn trước. Mục tiêu là test lớp wrapper đúng theo API quan sát kết quả.

Không chỉ viết <code>assertThrows(IOException.class, failed::join)</code> rồi kết luận code sai khi assertion fail: hợp đồng của <code>join()</code> không hứa ném trực tiếp checked exception gốc. Cần hiểu cách API bọc lỗi.

Đối với một pipeline phức tạp, cause có thể đi qua nhiều <code>CompletionException</code> hoặc wrapper do các stage tạo. Test nên xác định **cấp lỗi nào có ý nghĩa với caller**, không tự động unwrap mọi lớp mà bỏ qua mã lỗi domain.

## 20. Các trường hợp ngoại lệ có thể bị thay thế hoặc che lấp

### 20.1. finally tự ném ngoại lệ mới

~~~java
try {
    operation();
} finally {
    cleanupThatThrows();
}
~~~

Đây là **mã minh họa**, giả định hai lời gọi tồn tại. Nếu <code>operation()</code> đã ném một lỗi và <code>cleanupThatThrows()</code> cũng ném, lỗi từ <code>finally</code> có thể thay thế lỗi ban đầu. Một test chỉ kiểm tra type cuối không bảo đảm nguyên nhân chính được giữ.

Nếu cần bảo toàn nhiều lỗi khi đóng tài nguyên, ưu tiên <code>try-with-resources</code> cho tài nguyên <code>AutoCloseable</code> phù hợp. Lỗi đóng có thể được lưu trong <code>getSuppressed()</code> của lỗi chính. Khi hợp đồng yêu cầu, hãy test suppressed thay vì chỉ cause.

### 20.2. Wrapper tạo bằng message mà không truyền cause

~~~java
catch (IOException original) {
    throw new DocumentLoadException(
            original.getMessage(),
            documentId,
            "LOAD",
            null);
}
~~~

Đây là **mã minh họa cố ý sai khi hợp đồng yêu cầu giữ cause**. Test message vẫn có thể PASS, nhưng <code>assertSame(original, thrown.getCause())</code> sẽ phát hiện lỗi.

### 20.3. Catch quá rộng

~~~java
catch (RuntimeException any) {
    throw new DocumentLoadException(
            "Không thể tải tài liệu",
            documentId,
            "LOAD",
            any);
}
~~~

Đây là **mã minh họa**. Nếu một bug <code>NullPointerException</code> ở service được chuyển thành lỗi đọc tài liệu, test chỉ kiểm tra có <code>DocumentLoadException</code> không phát hiện việc phân loại sai. Hãy thiết kế test cho những trường hợp **không nên bị chuyển lỗi** hoặc thu hẹp catch đúng loại hạ tầng.

## 21. Test negative cases: điều gì không nên xảy ra?

Kiểm thử tốt không chỉ xác nhận một nhánh lỗi mong muốn mà còn bảo vệ các nhánh tránh phân loại nhầm.

| Tình huống | Điều cần bảo vệ |
| --- | --- |
| Input trống | Validation exception có type/message phù hợp, không gọi repository |
| Input hợp lệ, repository thành công | Trả dữ liệu, không tạo exception |
| Repository ném IOException | Wrapper domain giữ context và cause |
| Repository ném một bug RuntimeException ngoài hợp đồng chuyển lỗi | Không bị đánh tráo thành lỗi validation hoặc “not found” |
| Cause message chứa secret | Public response không lộ secret |
| Message domain được localization | Error code ổn định; test message theo locale ở tầng phù hợp |
| Task async thất bại | Wrapper theo <code>join/get</code> có cause phù hợp |
| Try-with-resources vừa lỗi thao tác vừa lỗi đóng | Lỗi chính và suppressed phản ánh đúng hợp đồng |

### Kiểm tra dependency không bị gọi ở nhánh validation

Nếu bạn dùng fake repository có biến đếm:

~~~java
final class CountingRepository {
    int calls;

    String read(String id) {
        calls++;
        return "ok";
    }
}
~~~

Đây là **lớp minh họa**, không phải một test hoàn chỉnh. Khi ID sai, test có thể xác nhận method validation ném đúng exception và <code>calls == 0</code>. Điều này giúp bắt những implementation gọi I/O rồi mới validate.

Nhưng đừng gắn assertion “không gọi dependency” nếu thiết kế không công bố thứ tự đó hoặc nếu side effect không bị ảnh hưởng; hãy test điều kiện phản ánh yêu cầu thực sự.

## 22. Thử nghiệm message và cause trong một test có nhiều thông tin

Một pattern dễ đọc là nhóm các assertion theo trách nhiệm:

~~~java
DocumentLoadException error = assertThrowsExactly(
        DocumentLoadException.class,
        () -> service.loadDocument("DOC-7"));

assertAll("public exception contract",
        () -> assertEquals("DOCUMENT_UNAVAILABLE", error.code()),
        () -> assertEquals("DOC-7", error.documentId()),
        () -> assertEquals("LOAD", error.operation()));

assertAll("diagnostic cause",
        () -> assertNotNull(error.getCause()),
        () -> assertSame(original, error.getCause()));
~~~

Đây là **đoạn minh họa** với service, loại exception có <code>code()</code> và biến <code>original</code> được tạo ở phần chuẩn bị test. Các nhóm <code>assertAll</code> tách rõ dữ liệu mà caller dùng với dữ liệu chẩn đoán.

**Tránh test quá rộng:** không gom hàng chục tình huống độc lập vào một test duy nhất rồi khó xác định lỗi ở bước nào. Một test có thể có nhiều assertion khi tất cả cùng mô tả **một lần thất bại và một hợp đồng**.

Nếu message công khai được ánh xạ ở tầng controller, không bắt service exception đồng thời phải chứa đúng message công khai. Hãy kiểm tra tại đúng ranh giới.

## 23. Mức kiểm thử nào nên kiểm tra thuộc tính nào?

### Unit test lớp service

Phù hợp cho:

- Loại exception do service ném.
- Message hoặc error code tầng service được công bố.
- Context: document ID, operation, resource type.
- Cause: identity của exception nguồn.
- Đường input hợp lệ, validation và mapping lỗi.

### Integration test lớp repository

Phù hợp cho:

- Cách thư viện JDBC, filesystem hoặc HTTP client báo lỗi.
- Việc chuyển lỗi hạ tầng tại adapter theo contract.
- Tài nguyên được đóng đúng trong cả đường thành công và thất bại.

Tránh test integration phụ thuộc vào một hostname hoặc đường dẫn hệ điều hành không ổn định nếu không cần thiết.

### API contract test

Phù hợp cho:

- Status và error code client nhận được.
- Message công khai theo locale được chọn.
- Field ngữ cảnh được phép xuất.
- Không lộ secret, raw cause, stack trace hoặc thông tin hạ tầng.
- Correlation/request ID theo hợp đồng.

### End-to-end test

Phù hợp để chứng minh một workflow lỗi hiển thị thông báo đúng mức và có hướng xử lý, nhưng không nên thay mọi unit test bằng e2e đắt đỏ nếu chỉ cần khẳng định cause identity.

**Một thuộc tính nên được kiểm tra ở tầng sở hữu hợp đồng đó.** Kiểm tra cùng một message kỹ thuật ở tất cả tầng tạo test khó bảo trì và dễ làm rò rỉ chi tiết nội bộ.

## 24. Cách chọn assertion cho message biến động

Một quyết định thực hành:

| Message | Assertion gợi ý | Lý do |
| --- | --- | --- |
| Template công khai cố định của ứng dụng | <code>assertEquals(expected, message)</code> | Bảo vệ nội dung đã công bố |
| Message có đoạn ngữ nghĩa ổn định | <code>assertNotNull</code> + <code>contains</code>/<code>startsWith</code> | Bỏ qua bối cảnh phụ không thuộc hợp đồng |
| Message thay đổi theo locale | Kiểm tra theo locale cụ thể hoặc mã lỗi | Tránh test phụ thuộc locale mặc định của máy |
| Message do JDK/driver tạo | Kiểm tra type/cause; hạn chế exact text | Tránh khóa vào implementation |
| Message có secret nội bộ | Test public payload **không** chứa secret; internal log tuân thủ chính sách | Bảo mật |
| Message có ID nhưng API có field <code>documentId</code> | Assert field; message chỉ kiểm tra phần ổn định | Không parse dữ liệu từ text |
| Message được phép null | Kiểm tra hợp đồng nullable; không tự gọi <code>contains</code> | Phản ánh thực tế API |

Đừng dùng regex cực rộng như <code>.*error.*</code> chỉ để “test có text”. Nó có thể PASS khi nội dung không còn hữu ích. Cũng đừng dùng regex mô phỏng đúng từng dấu câu của một lỗi từ thư viện nếu hợp đồng không cam kết chúng.

## 25. Những lỗi phổ biến trong test exception

1. **Chỉ viết <code>assertThrows(Exception.class, ...)</code>:** có thể PASS vì lỗi không liên quan.
2. **Gọi lại service nhiều lần để kiểm tra từng thuộc tính:** thao tác có thể có side effect hoặc kết quả khác nhau.
3. **Chọn <code>assertThrowsExactly</code> khi subclass là hợp lệ:** test quá chặt với phân cấp exception.
4. **Chọn <code>assertThrows</code> quá rộng khi cần exact type:** test có thể bỏ sót chuyển loại sai.
5. **Assert exact message của JDK/driver:** dễ vỡ khi đổi runtime hoặc thư viện.
6. **Chỉ kiểm tra message chứa ID:** không bảo vệ field context có cấu trúc.
7. **Dùng <code>assertEquals</code> khi muốn chứng minh cùng Throwable instance:** hãy dùng <code>assertSame</code>.
8. **Chỉ kiểm tra cause không null:** có thể giữ nhầm exception.
9. **Chỉ kiểm tra cause root, bỏ qua loại wrapper domain:** có thể không phát hiện API mapping sai.
10. **Bắt nguyên stack trace thành snapshot cố định:** số dòng và frame không ổn định.
11. **Test lỗi I/O bằng file thật khi chỉ cần fake:** tạo test chậm và dễ phụ thuộc hệ điều hành.
12. **Dùng <code>catch (Exception)</code> trong test rồi assert <code>true</code>:** có thể bắt cả lỗi do chính assertion/test tạo ra.
13. **Không test nhánh thành công:** implementation luôn ném lỗi vẫn có thể PASS bộ test chỉ có negative case.
14. **Không kiểm tra public response:** service giữ cause đúng nhưng adapter có thể leak secret.
15. **Dùng <code>getCause()</code> như một API không bao giờ null:** test có thể ném NPE thay vì báo assertion rõ ràng.
16. **Không phân biệt <code>Future.get</code> và <code>CompletableFuture.join</code>:** assertion chọn sai wrapper exception.
17. **Không xét suppressed trong try-with-resources:** bỏ sót lỗi cleanup quan trọng khi hợp đồng yêu cầu.
18. **Test khẳng định mọi lỗi đều retryable:** retry phải tuân theo ngữ nghĩa và side effect thực tế.
19. **Đặt dữ liệu nhạy cảm thật trong fixture/test output:** dùng marker giả an toàn.
20. **Kiểm tra quá nhiều chi tiết nội bộ không được công bố:** test cản trở refactor hợp lệ.

## 26. Checklist trước khi hoàn tất bài test

Hãy tự hỏi:

1. Phương thức có **hợp đồng thất bại** rõ ràng không?
2. Test đã bắt đúng loại exception, hay chỉ một superclass quá rộng?
3. Có cần exact type, hay subclass cũng được chấp nhận?
4. Message có được công bố ổn định không? Nếu không, nên kiểm tra mã lỗi hoặc phần ngữ nghĩa nào?
5. Thuộc tính context nào caller thực sự cần: code, ID, operation, retryable, correlation ID?
6. Các field context được kiểm tra trực tiếp thay vì parse từ message chưa?
7. Nếu tầng đang wrap lỗi, test có giữ được object gốc để <code>assertSame</code> không?
8. Hợp đồng yêu cầu cause trực tiếp hay chỉ bảo toàn root cause trong chain?
9. Có cần kiểm tra suppressed exception khi cleanup lỗi không?
10. Test có tránh phụ thuộc vào raw stack trace, số dòng hoặc wording của JDK/driver không?
11. Nhánh thành công và nhánh validation đã được kiểm tra riêng chưa?
12. Nếu dùng fake/mocks, chúng có đủ xác định để tránh flaky test không?
13. Public response đã có test không lộ thông tin nhạy cảm từ exception gốc chưa?
14. Async API có được quan sát qua wrapper exception đúng hợp đồng không?
15. Khi thay implementation nhưng giữ contract, bộ test có thể tiếp tục PASS không?

## 27. Tóm tắt

- **Exception là một phần hợp đồng của API**, không chỉ là một sự kiện ném lỗi.
- Kiểm tra loại exception bằng <code>assertThrows</code> hoặc <code>assertThrowsExactly</code> theo yêu cầu chấp nhận subtype.
- Kiểm tra **message** khi nó có ý nghĩa và độ ổn định đã được công bố; tránh khóa vào wording tình cờ của JVM/thư viện.
- Kiểm tra **context** qua getter/field có cấu trúc, không tách ID từ chuỗi message.
- Kiểm tra **cause** bằng <code>assertSame(original, error.getCause())</code> khi cần bảo toàn cùng đối tượng; chọn kiểm tra chain nếu hợp đồng cho phép wrapper trung gian.
- Phân biệt cause, suppressed, lỗi async và thông báo công khai dành cho client.
- Dùng fake để tạo lỗi xác định, giữ test độc lập với filesystem hoặc hệ thống mạng.
- Kiểm thử đủ cả nhánh hợp lệ và thất bại, nhưng không ràng buộc những chi tiết triển khai không thuộc hợp đồng.

**Kết luận:** một bài kiểm thử exception tốt không dừng ở câu hỏi “có ném lỗi không?”. Nó xác minh **đúng loại lỗi, đủ ngữ cảnh, message phù hợp và cause được bảo toàn khi cần**, đồng thời không khiến test mong manh vì chi tiết tình cờ của JVM, log hay lớp hạ tầng.