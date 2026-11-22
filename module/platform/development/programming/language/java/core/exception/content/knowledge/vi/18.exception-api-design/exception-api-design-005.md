# Chuyển đổi ngoại lệ tại ranh giới trừu tượng trong Java

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một API nên biểu đạt lỗi theo ngôn ngữ của chính tầng trừu tượng mà nó cung cấp.
- Xác định đúng vị trí chuyển đổi ngoại lệ (exception translation) giữa tầng hạ tầng và tầng nghiệp vụ.
- Ánh xạ ngoại lệ cụ thể thành ngoại lệ có ý nghĩa đối với người gọi, giữ nguyên nguyên nhân gốc bằng cơ chế cause chaining.
- Thiết kế hợp đồng lỗi nhất quán, quyết định hợp lý giữa checked exception và unchecked exception.
- Tránh che giấu lỗi, đóng gói lặp nhiều tầng, bắt quá rộng hoặc xử lý sai ngắt luồng.

## 2. Exception translation là gì?

**Exception translation** là kỹ thuật bắt ngoại lệ được phát sinh ở một tầng triển khai và chuyển nó thành ngoại lệ thuộc hợp đồng của tầng đang cung cấp API. Người gọi nhận được một loại lỗi phản ánh thao tác mà họ yêu cầu, thay vì phải biết chi tiết tầng bên dưới dùng tệp, JDBC, HTTP client hay thư viện thứ ba nào.

Ví dụ, phương thức của kho tài liệu cung cấp thao tác **đọc tài liệu theo tên**. Bên dưới, nó dùng hệ thống tệp và có thể gặp <code>NoSuchFileException</code> hoặc <code>IOException</code>. Tầng kho tài liệu có thể công bố hai lỗi có ngữ nghĩa gần với nhu cầu của người dùng API:

- <code>DocumentNotFoundException</code>: tài liệu được yêu cầu không tồn tại.
- <code>DocumentAccessException</code>: không thể đọc tài liệu vì lỗi truy cập/hạ tầng.

Đây là thay đổi về **mức trừu tượng của lỗi**, chứ không phải thao tác sửa chữa nguyên nhân gốc. Ngoại lệ mới vẫn nên lưu ngoại lệ cũ trong <code>cause</code> để hỗ trợ chẩn đoán.

Một luồng xử lý điển hình:

~~~text
Application / Use case
        |
        | read("intro.txt")
        v
DocumentRepository       <- hợp đồng lỗi theo "tài liệu"
        |
        | Files.readString(...)
        v
Java NIO / File system   <- lỗi theo "đường dẫn, tệp, I/O"

NoSuchFileException
        |
        | catch, phân loại, giữ cause
        v
DocumentNotFoundException
        |
        v
Application xử lý theo nghĩa "không tìm thấy tài liệu"
~~~

Nếu khách hàng của <code>DocumentRepository</code> phải bắt trực tiếp hàng loạt loại <code>IOException</code> riêng của cơ chế lưu trữ, ranh giới trừu tượng đã để lọt chi tiết triển khai ra hợp đồng bên trên.

## 3. Khi nào nên chuyển đổi ngoại lệ?

**Nên chuyển đổi** khi cả ba điều kiện sau có ý nghĩa:

1. **Tầng hiện tại sở hữu một hợp đồng độc lập**: chẳng hạn repository, gateway, adapter, service API hoặc facade.
2. **Ngoại lệ bên dưới không phải ngôn ngữ phù hợp cho người gọi**: lỗi từ JDBC, filesystem hoặc HTTP client chỉ phản ánh cách cài đặt.
3. **Có ánh xạ đáng tin cậy** từ lỗi bên dưới sang ý nghĩa của thao tác: ví dụ không có bản ghi/tài liệu, xung đột phiên bản, từ chối truy cập, hoặc lỗi phụ thuộc tạm thời.

**Không nên chuyển đổi máy móc** mọi ngoại lệ tại mọi lời gọi phương thức. Trong một thư viện thao tác tệp được thiết kế để cho người gọi xử lý I/O trực tiếp, khai báo <code>throws IOException</code> có thể là hợp đồng đúng. Nếu loại ngoại lệ đã thuộc ngôn ngữ API và người gọi hiểu được nó, việc bọc thêm một ngoại lệ chung chỉ làm mất thông tin.

Cũng cần phân biệt:

- **Translation**: đổi kiểu hoặc ngữ nghĩa ngoại lệ; lỗi tiếp tục được ném ra.
- **Handling/recovery**: thật sự xử lý được lỗi, ví dụ dùng nguồn dự phòng hoặc cho người dùng thử lại.
- **Logging**: ghi nhận lỗi để quan sát; bản thân ghi log không xử lý được lỗi.
- **Mapping ở ranh giới giao tiếp**: chuyển lỗi nghiệp vụ thành HTTP response, gRPC status hoặc mã phản hồi. Việc này có thể xảy ra tại một tầng khác, sau khi exception translation đã hoàn thành.

## 4. Phân loại lỗi trước khi ánh xạ

Một ngoại lệ hạ tầng không luôn tương đương với một ngoại lệ nghiệp vụ. Cần dựa vào ngữ cảnh thao tác và các tín hiệu đáng tin cậy của API bên dưới.

| Tín hiệu ở tầng thấp | Ví dụ lỗi phù hợp ở tầng cao | Điều cần kiểm tra |
| --- | --- | --- |
| Không tìm thấy tệp khi đọc tài liệu | <code>DocumentNotFoundException</code> | Tệp đó thực sự đại diện cho tài liệu được yêu cầu |
| Không có bản ghi theo ID | <code>EntityNotFoundException</code> | Kết quả rỗng có phải tình huống bình thường theo hợp đồng hay không |
| Vi phạm khóa duy nhất khi tạo tài nguyên | <code>DuplicateResourceException</code> hoặc lỗi xung đột | Xác định chính xác ràng buộc, tránh coi mọi lỗi SQL là trùng dữ liệu |
| Timeout hoặc lỗi kết nối dịch vụ ngoài | <code>ExternalServiceUnavailableException</code> | Chỉ khẳng định tính tạm thời nếu có cơ sở; timeout không chứng minh thao tác chưa chạy |
| <code>IOException</code> không phân loại rõ | <code>DocumentAccessException</code> | Giữ cause để tra cứu nguyên nhân chi tiết |
| Dữ liệu đầu vào không hợp lệ trước khi gọi hạ tầng | <code>IllegalArgumentException</code> hoặc lỗi validation của API | Kiểm tra trước; không giả vờ đó là lỗi I/O |

**Nguyên tắc:** chuyển đổi theo *ngữ nghĩa có thể chứng minh*, tránh suy ra nguyên nhân chỉ từ chuỗi thông báo của ngoại lệ. Không so sánh <code>getMessage()</code> với một đoạn chữ cố định để quyết định loại lỗi; thông báo có thể thay đổi theo hệ điều hành, driver, ngôn ngữ hoặc phiên bản thư viện.

Thứ tự các khối <code>catch</code> cũng quan trọng. Ví dụ <code>NoSuchFileException</code> là lớp con của <code>IOException</code>, nên phải bắt loại chuyên biệt trước loại bao quát; làm ngược sẽ khiến nhánh chuyên biệt không thể tới được và Java báo lỗi biên dịch.

## 5. Ví dụ Java 17+ chạy độc lập

Ví dụ dùng một cổng truy cập văn bản có thể thay thế được để tái hiện ba tình huống **thành công**, **không tìm thấy**, **lỗi I/O** mà không phụ thuộc vào các tệp đang có trên máy. Điểm chuyển đổi nằm trong <code>DocumentRepository.read</code>. Ở môi trường thực tế, cổng đó có thể được nối với <code>Files.readString</code>, hệ cơ sở dữ liệu hoặc dịch vụ ngoài.

Tạo tệp **ExceptionTranslationDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.NoSuchFileException;

public class ExceptionTranslationDemo {

    @FunctionalInterface
    interface TextStore {
        String read(String name) throws IOException;
    }

    static final class DocumentNotFoundException extends RuntimeException {
        DocumentNotFoundException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class DocumentAccessException extends RuntimeException {
        DocumentAccessException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class DocumentRepository {
        private final TextStore store;

        DocumentRepository(TextStore store) {
            this.store = java.util.Objects.requireNonNull(store);
        }

        String read(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                        "Tên tài liệu không được để trống");
            }

            try {
                return store.read(name);
            } catch (NoSuchFileException e) {
                throw new DocumentNotFoundException(
                        "Không tìm thấy tài liệu: " + name, e);
            } catch (IOException e) {
                throw new DocumentAccessException(
                        "Không thể đọc tài liệu: " + name, e);
            }
        }
    }

    private static void show(String scenario, DocumentRepository repository) {
        try {
            System.out.println(scenario + ": " + repository.read("intro.txt"));
        } catch (DocumentNotFoundException | DocumentAccessException e) {
            System.out.println(
                    scenario + ": " + e.getClass().getSimpleName()
                    + " (cause=" + e.getCause().getClass().getSimpleName() + ")");
        }
    }

    public static void main(String[] args) {
        show("Thành công",
                new DocumentRepository(name -> "Xin chào Java"));

        show("Không tồn tại",
                new DocumentRepository(name -> {
                    throw new NoSuchFileException(name);
                }));

        show("Lỗi I/O",
                new DocumentRepository(name -> {
                    throw new IOException("Ổ đĩa không khả dụng");
                }));
    }
}
~~~

Biên dịch và chạy với Java 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 ExceptionTranslationDemo.java
java ExceptionTranslationDemo
~~~

Kết quả chuẩn (stdout):

~~~text
Thành công: Xin chào Java
Không tồn tại: DocumentNotFoundException (cause=NoSuchFileException)
Lỗi I/O: DocumentAccessException (cause=IOException)
~~~

**Cơ chế của từng nhánh:**

1. Nếu <code>TextStore.read</code> trả về văn bản, <code>DocumentRepository.read</code> trả về nguyên văn, không tạo ngoại lệ.
2. Nếu cổng ném <code>NoSuchFileException</code>, repository ném <code>DocumentNotFoundException</code>. Người gọi biết **tài liệu không tìm thấy**, không cần biết nơi lưu tài liệu.
3. Nếu cổng ném một <code>IOException</code> khác, repository ném <code>DocumentAccessException</code>. Như vậy các lỗi I/O chưa phân loại vẫn được biểu đạt chính xác ở mức tổng quát.
4. Mỗi ngoại lệ mới được khởi tạo với <code>super(message, cause)</code>, nên <code>getCause()</code> trả về đúng ngoại lệ thấp hơn. Chuỗi cause còn có thể chứa nhiều tầng khi cần chẩn đoán.

Để sử dụng Java NIO thật, có thể thay cách khởi tạo cổng như đoạn **minh họa tích hợp** sau (đây là biểu thức đặt trong mã có import và ngữ cảnh tương ứng, không phải một chương trình Java độc lập):

~~~java
DocumentRepository repository = new DocumentRepository(
        name -> java.nio.file.Files.readString(
                java.nio.file.Path.of(name),
                java.nio.charset.StandardCharsets.UTF_8));
~~~

Cần lưu ý: <code>Files.readString</code> còn có thể ném ngoại lệ không thuộc <code>IOException</code>, ví dụ <code>SecurityException</code> theo ngữ cảnh kiểm tra quyền truy cập. Hai nhánh <code>catch</code> trên chỉ chuyển đổi <code>NoSuchFileException</code> và <code>IOException</code>; ví dụ không tuyên bố xử lý tất cả lỗi có thể có của hệ thống tệp.

## 6. Giữ `cause`: chuyển ngữ nghĩa mà không làm mất nguồn gốc

Khi `DocumentRepository` bắt `IOException` rồi ném `DocumentAccessException`, đối tượng mới cần message ở tầng tài liệu **và** tham chiếu tới đúng lỗi hạ tầng:

~~~java
catch (IOException original) {
    throw new DocumentAccessException(
            "Không thể đọc tài liệu", original);
}
~~~

Đây là mảnh minh họa thuộc phương thức có `try` tương ứng. `getCause()` trên wrapper trỏ tới **chính instance `original`**; các stack frame/suppressed exceptions vốn có của lỗi gốc vẫn thuộc đối tượng ấy. Không chỉ chép `original.getMessage()` vào message của wrapper, và không tự copy stack trace sang object mới. Nếu lỗi đã là loại public thích hợp, có thể để nó truyền lên thay vì bọc thêm một lớp chỉ nói “failed”.

Bài **giữ `cause` khi chuyển lỗi kỹ thuật** kiểm tra sâu danh tính cause, chuỗi nhiều tầng và tác động của suppressed; bài hiện tại tập trung ở **ranh giới chuyển đổi và phân loại loại lỗi public**.

## 7. Thiết kế hợp đồng ngoại lệ cho API

Trước khi khai báo ngoại lệ mới, hãy xác định **người gọi cần có hành động khác nhau hay không**. Nếu khách hàng có thể chọn hành động riêng cho “không tìm thấy” và “không thể truy cập”, hai loại lỗi tách biệt đem lại giá trị. Nếu không thể phân biệt đáng tin cậy các nguyên nhân, một loại lỗi truy cập tổng quát có thể phù hợp hơn.

Một hợp đồng tốt cần:

- **Tên ổn định và thể hiện ý nghĩa**: phân biệt tài nguyên không tồn tại, yêu cầu sai, xung đột và lỗi phụ thuộc.
- **Phạm vi sở hữu rõ**: ngoại lệ thuộc API của tầng đó, tránh buộc mọi lớp bên trên phụ thuộc driver hoặc thư viện cụ thể.
- **Tài liệu hóa trường hợp phát sinh**: với unchecked exception, vẫn mô tả chúng trong Javadoc/contract.
- **Giữ nguyên cause**, bổ sung định danh nghiệp vụ hữu ích nếu an toàn (ví dụ mã tài liệu thay vì đường dẫn máy chủ).
- **Không hứa sai mức độ khôi phục**: “truy cập thất bại” không đương nhiên có nghĩa “thử lại sẽ thành công”.

Ví dụ khai báo hợp đồng (minh họa API, không phải chương trình độc lập):

~~~java
public interface DocumentReader {
    /**
     * Đọc văn bản của tài liệu đã định danh.
     *
     * @throws DocumentNotFoundException nếu tài liệu không tồn tại
     * @throws DocumentAccessException nếu kho tài liệu không thể đọc dữ liệu
     * @throws IllegalArgumentException nếu tên tài liệu không hợp lệ
     */
    String read(String name);
}
~~~

Trong API công khai, các ngoại lệ tùy biến nên có độ hiển thị phù hợp (<code>public</code> nếu client ở package khác cần bắt chúng), và code của client chỉ nên dựa trên những loại đã được công bố. Trong bản demo, các lớp được lồng gọn trong một tệp để dễ chạy, nên chưa minh họa cách tổ chức nhiều tệp cho thư viện được phát hành.

### Checked hay unchecked?

Java chia ngoại lệ thành:

- **Checked exception**: mọi <code>Exception</code> không kế thừa <code>RuntimeException</code>; trình biên dịch buộc người gọi bắt hoặc khai báo <code>throws</code>.
- **Unchecked exception**: <code>RuntimeException</code> và các lớp con của nó (ngoài ra <code>Error</code> và lớp con cũng unchecked). Người gọi không bắt buộc khai báo/bắt.

Ví dụ dùng unchecked domain exception để API không ràng buộc từng lời gọi với <code>throws IOException</code>. Đây là **quyết định thiết kế của ví dụ**, không phải quy tắc chung.

Chọn checked exception nếu API muốn buộc người gọi nhận biết tình huống thất bại dự kiến và thường có đường xử lý hợp lý. Chọn unchecked khi lỗi không thể hoặc không nên bị ép xử lý tại từng điểm gọi, hoặc theo quy ước chung của kiến trúc. Dù chọn loại nào, vẫn phải giữ ngữ nghĩa, cause và tài liệu hợp đồng nhất quán. Đừng chỉ đổi <code>IOException</code> thành <code>RuntimeException</code> vô danh để né trình biên dịch.

## 8. Chọn đúng ranh giới chuyển đổi

Tại một hệ thống nhiều tầng, ví dụ:

~~~text
Controller / CLI / Consumer
          |
          v
      Use-case Service
          |
          v
   DocumentRepository       => chuyển lỗi file/JDBC thành lỗi kho tài liệu
          |
          v
       File system

HTTP boundary / CLI boundary => nếu cần, ánh xạ lỗi API sang status/thông báo
~~~

Một lỗi chỉ nên được chuyển khi **ý nghĩa mà tầng đó cung cấp thật sự thay đổi**. Repository có thể sở hữu <code>DocumentNotFoundException</code>. Service nên để lỗi đi qua nếu nó đã khớp hợp đồng của service; chỉ chuyển lần nữa khi service bổ sung ngữ nghĩa khác, chẳng hạn “không thể hoàn tất phát hành hồ sơ” bao gồm nhiều thao tác nghiệp vụ.

Nếu tầng HTTP ánh xạ <code>DocumentNotFoundException</code> thành trạng thái HTTP 404, đó là quy tắc của adapter HTTP, không nên khiến repository phụ thuộc vào loại <code>HttpStatus</code>. Với những lỗi hạ tầng không xác định, adapter thường trả lỗi tổng quát an toàn thay vì gửi nguyên văn ngoại lệ nội bộ.

Một số lựa chọn cần nhất quán trên toàn API:

| Quyết định | Câu hỏi kiểm tra |
| --- | --- |
| Trả giá trị rỗng hay ném lỗi khi không tìm thấy? | “Không có tài liệu” có phải kết quả thông thường của thao tác tra cứu này không? |
| Có loại lỗi riêng cho truy cập bị từ chối? | Người gọi có hành động riêng và có tín hiệu đủ chắc chắn để phân loại không? |
| Ngoại lệ nào được công bố cho client? | Có thể giữ ổn định hợp đồng khi thay hệ lưu trữ không? |
| Có phép thử lại không? | Thao tác có tính idempotent hay có thể đã thành công một phần dù nhận timeout? |

Một API tra cứu có thể dùng <code>Optional</code> khi “không tồn tại” là tình huống bình thường. Với API cam kết tài liệu phải tồn tại, một ngoại lệ not-found thường diễn đạt rõ ràng hơn. Cả hai là lựa chọn hợp đồng; không tự động chuyển mọi giá trị rỗng thành ngoại lệ.

## 9. Ngoại lệ không nên bị nuốt hoặc biến dạng

### 9.1. Không bắt bao trùm một cách tùy tiện

Mẫu dễ gây lỗi:

~~~java
try {
    doWork();
} catch (Exception e) {
    throw new RuntimeException("Thất bại", e);
}
~~~

Đây là ví dụ minh họa, **không phải chương trình độc lập**. Nó có thể gom cả lỗi validation, lỗi lập trình, lỗi nghiệp vụ đã dịch và các checked exception khác vào một loại chung. Người gọi không còn phân biệt được lỗi nào cần xử lý. Hãy bắt những loại thuộc đúng ranh giới chuyển đổi; nếu cần bắt rộng tại điểm đầu ứng dụng để ghi log hoặc chặn crash, đó là trách nhiệm khác.

Tuyệt đối không dùng <code>catch (Throwable)</code> như một cách dịch lỗi thông thường: <code>Error</code> có thể đại diện cho tình trạng nghiêm trọng của JVM và không thuộc tập lỗi nghiệp vụ có thể khôi phục.

### 9.2. Không biến lỗi thành kết quả thành công giả

~~~java
try {
    return store.read(name);
} catch (IOException e) {
    return null;
}
~~~

Nếu hợp đồng không định nghĩa <code>null</code> là trạng thái lỗi được xử lý rõ ràng, đoạn mã trên xóa mất sự khác biệt giữa “không có nội dung” và “hệ thống thất bại”. Người gọi có thể tiếp tục thao tác như thể việc đọc đã thành công.

### 9.3. Không bọc lặp khi chưa thay đổi ý nghĩa

~~~java
catch (DocumentAccessException e) {
    throw new RuntimeException("Không đọc được tài liệu", e);
}
~~~

Khi không thêm được ý nghĩa mới, wrapper chỉ tạo thêm tầng stack trace và làm người gọi mất loại lỗi hữu ích. Có thể cho ngoại lệ đi qua nguyên vẹn.

### 9.4. Xử lý InterruptedException có chủ đích

<code>InterruptedException</code> mang tín hiệu điều khiển luồng, không nên tự động coi như một lỗi hạ tầng thông thường. Với một đoạn mã đang chờ thao tác blocking:

~~~java
try {
    blockingOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new TaskCancelledException("Tác vụ bị ngắt", e);
}
~~~

Đây là **mã minh họa**, giả định có <code>blockingOperation()</code> và <code>TaskCancelledException</code> phù hợp. Khi phương thức blocking ném <code>InterruptedException</code>, trạng thái interrupt thường đã bị xóa; gọi <code>interrupt()</code> để khôi phục tín hiệu nếu không thể ném trực tiếp ngoại lệ checked đó lên trên. Trong API cho phép, chuyển tiếp <code>InterruptedException</code> trực tiếp cũng là một lựa chọn hợp lệ. Không được âm thầm nuốt ngắt rồi chạy tiếp như bình thường.

### 9.5. Không làm mất lỗi trong quá trình đóng tài nguyên

Với tài nguyên hỗ trợ <code>AutoCloseable</code>, ưu tiên <code>try-with-resources</code>. Nếu cả thao tác chính và việc đóng tài nguyên đều lỗi, Java giữ ngoại lệ thao tác chính là ngoại lệ chủ đạo và thường gắn lỗi đóng tài nguyên trong danh sách <code>getSuppressed()</code>. Khi dịch ngoại lệ, giữ cause gốc giúp còn có thể truy vết các suppressed exceptions. Tránh tự viết <code>finally</code> để đóng tài nguyên rồi vô tình thay thế ngoại lệ chính bằng lỗi đóng tài nguyên.

## 10. Cách kiểm thử exception translation

Các kiểm thử nên xác nhận **hợp đồng và nguyên nhân**, thay vì cố so khớp toàn bộ stack trace hoặc thông điệp phụ thuộc môi trường.

| Tình huống đầu vào | Kết quả cần kiểm tra |
| --- | --- |
| Cổng trả chuỗi văn bản | Giá trị trả về được giữ nguyên; không có ngoại lệ |
| Cổng ném <code>NoSuchFileException</code> | Ném đúng <code>DocumentNotFoundException</code> |
| Cổng ném <code>IOException</code> chung | Ném đúng <code>DocumentAccessException</code> |
| Lỗi đã dịch có cause | <code>getCause()</code> là **chính đối tượng** ngoại lệ gốc |
| Tên tài liệu null/rỗng | Có lỗi input phù hợp; không gọi kho lưu trữ |
| Một <code>RuntimeException</code> khác từ cổng | Không bị hai nhánh <code>catch IOException</code> thay đổi ngoài ý muốn |

Có thể kiểm tra trực tiếp cause bằng một đối tượng <code>IOException</code> được tạo trước. Đoạn mã **minh họa trong cùng phạm vi truy cập của bản demo**:

~~~java
IOException original = new IOException("I/O failure");
DocumentRepository repository = new DocumentRepository(name -> {
    throw original;
});

try {
    repository.read("intro.txt");
    throw new AssertionError("Phải ném DocumentAccessException");
} catch (DocumentAccessException translated) {
    if (translated.getCause() != original) {
        throw new AssertionError("Không giữ đúng cause gốc");
    }
}
~~~

Lệnh so sánh bằng <code>==</code> ở đây có ý nghĩa: kiểm tra **cùng một instance** được giữ làm cause, không chỉ kiểm tra cùng loại ngoại lệ. Trong một dự án dùng JUnit, có thể áp dụng <code>assertThrows</code> và <code>assertSame</code> để diễn đạt hai yêu cầu đó.

## 11. Những lỗi thiết kế phổ biến

1. **Lộ kiểu ngoại lệ hạ tầng** trong public API dù client chỉ làm việc với khái niệm nghiệp vụ: thay hệ lưu trữ khiến client phải sửa cách bắt lỗi.
2. **Tạo một ngoại lệ chung cho mọi tình huống**: mất khả năng phân biệt not-found, xung đột, thiếu quyền và lỗi phụ thuộc.
3. **Dịch dựa trên chuỗi message** thay vì loại ngoại lệ, mã trạng thái hoặc contract rõ ràng: dễ hỏng khi thay driver hay ngôn ngữ.
4. **Không truyền cause**: khó tìm được call site và nguyên nhân thực tế.
5. **Bắt rộng và wrap hai lần**: vô tình đổi loại lỗi đã phù hợp, làm phức tạp stack trace.
6. **Log cùng một lỗi ở mọi tầng rồi ném tiếp**: sinh log trùng lặp, khó xem một sự cố. Nên có chiến lược ghi log ở tầng thực sự xử lý hoặc tại điểm giám sát thích hợp.
7. **Dùng lỗi nghiệp vụ để che lỗi lập trình** như <code>NullPointerException</code> hay vi phạm bất biến mà không có chủ đích.
8. **Đổi API mà không duy trì hợp đồng ngoại lệ**: client đang bắt một loại lỗi có thể bị ảnh hưởng dù chữ ký phương thức với unchecked exception không thay đổi.

## 12. Checklist áp dụng vào dự án

Khi thiết kế hoặc review một phương thức qua ranh giới trừu tượng, hãy tự kiểm tra:

- Người gọi đang yêu cầu thao tác ở **mức khái niệm nào** (tài liệu, tài khoản, đơn hàng, tác vụ)?
- Những ngoại lệ nào là chi tiết hạ tầng; những ngoại lệ nào đã thuộc hợp đồng công khai?
- Có nhận diện được chắc chắn từng trường hợp cần xử lý riêng không?
- Có giữ được **cause**, đồng thời bảo vệ thông tin nhạy cảm khi tạo thông báo công khai?
- Đã bắt ngoại lệ cụ thể trước loại tổng quát, tránh bắt cả lỗi không liên quan?
- Checked/unchecked có phù hợp kỳ vọng xử lý lỗi của client và quy ước dự án?
- Có kiểm thử nhánh thành công, các nhánh lỗi được ánh xạ, và danh tính cause?
- Tầng phía trên có thể xử lý lỗi theo hợp đồng mà không phải biết thư viện lưu trữ cụ thể không?

Khi trả lời được các câu hỏi này, exception translation giúp **giữ ổn định API trước thay đổi công nghệ** và vẫn để lại đủ thông tin điều tra sự cố. Giá trị của kỹ thuật nằm ở ánh xạ đúng ngữ nghĩa, đúng ranh giới và bảo toàn nguyên nhân gốc.