# Giữ cause khi chuyển lỗi kỹ thuật thành lỗi có ý nghĩa với bên gọi trong Java

## 1. Mục tiêu

Khi hoàn thành bài này, bạn có thể:

- Phân biệt **ngoại lệ được công bố cho bên gọi** với **ngoại lệ kỹ thuật gây ra sự cố**.
- Dùng constructor có tham số <code>Throwable cause</code> để chuyển lỗi mà không đánh mất dấu vết lỗi ban đầu.
- Giải thích cách <code>getCause()</code>, stack trace, <code>printStackTrace()</code> và chuỗi <code>Caused by</code> hỗ trợ điều tra lỗi.
- Phân biệt cause với suppressed exception, message và thông tin cần hiển thị cho người dùng.
- Kiểm tra rằng việc chuyển lỗi giữ **đúng đối tượng** cause, đồng thời tránh bọc lỗi dư thừa, che giấu lỗi hoặc tiết lộ chi tiết hạ tầng.

## 2. Bài toán: một lỗi có hai góc nhìn

Giả sử một API cung cấp thao tác <code>getDocument("guide")</code>. Bên gọi chỉ quan tâm liệu có đọc được tài liệu hay không. Việc tài liệu nằm trên hệ thống tệp, cơ sở dữ liệu hoặc dịch vụ từ xa là chi tiết cài đặt.

Trong quá trình đọc, tầng kỹ thuật có thể ném <code>java.nio.file.NoSuchFileException</code> hoặc <code>java.io.IOException</code>. Nếu API muốn cung cấp ngôn ngữ lỗi ổn định, nó có thể ném <code>DocumentNotFoundException</code> hoặc <code>DocumentReadException</code> cho bên gọi.

Vấn đề nằm ở chỗ: nếu chỉ tạo một ngoại lệ mới với thông báo “Không thể đọc tài liệu”, ta biết **thao tác nào thất bại** nhưng có thể mất **nguyên nhân kỹ thuật nào dẫn tới thất bại**. Vì vậy, một phép chuyển đổi tốt cần đồng thời giữ hai phần thông tin:

| Thành phần | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Ngoại lệ bên ngoài (translated exception) | Thao tác ở tầng API thất bại như thế nào? | <code>DocumentReadException</code> |
| Message của ngoại lệ bên ngoài | Ngữ cảnh nào hữu ích cho bên gọi? | “Không thể đọc tài liệu: guide” |
| Cause | Điều gì trực tiếp khiến thao tác thất bại ở tầng dưới? | Đối tượng <code>IOException</code> ban đầu |
| Stack trace | Ngoại lệ được tạo/ném qua những vị trí thực thi nào? | Vị trí đọc dữ liệu và vị trí chuyển đổi ngoại lệ |

**Giữ cause** nghĩa là giữ tham chiếu tới đối tượng ngoại lệ đã gây ra lỗi và nối nó với ngoại lệ mới, thường bằng <code>super(message, cause)</code>. Cause không bị thay bằng chuỗi ký tự hoặc bằng một ngoại lệ mới cùng loại.

Mô hình:

~~~text
Bên gọi: DocumentGateway.get("guide")
                |
                v
       Lỗi kỹ thuật: IOException
                |
                | catch (IOException original)
                v
   DocumentReadException("Không thể đọc...", original)
                |
                +---- ngoại lệ bên ngoài: thông điệp theo hợp đồng API
                |
                +---- getCause(): chính đối tượng IOException gốc
~~~

Việc dịch loại lỗi và việc bảo toàn nguyên nhân là hai trách nhiệm có liên hệ nhưng khác nhau. Có tình huống nên giữ nguyên ngoại lệ mà không cần tạo wrapper mới; khi thật sự cần chuyển đổi, việc giữ cause giúp tránh mất thông tin.

## 3. Cause trong cơ chế ngoại lệ Java

Lớp gốc <code>java.lang.Throwable</code> cung cấp các cơ chế quan trọng:

| API | Ý nghĩa |
| --- | --- |
| <code>getMessage()</code> | Thông báo chi tiết của chính ngoại lệ đang được xét; có thể là <code>null</code> |
| <code>getCause()</code> | Ngoại lệ được liên kết là nguyên nhân của ngoại lệ hiện tại; có thể là <code>null</code> |
| <code>printStackTrace()</code> | In stack trace cùng chuỗi cause/suppressed khi có, phục vụ chẩn đoán |
| <code>getStackTrace()</code> | Lấy stack trace của chính <code>Throwable</code> dưới dạng mảng phần tử |
| <code>getSuppressed()</code> | Lấy các ngoại lệ bị giữ lại dạng *suppressed*, không phải cause chính |

Một đối tượng <code>Throwable</code> chỉ có tối đa **một cause trực tiếp**, nhưng cause cũng có thể có cause riêng, tạo thành một chuỗi. Ví dụ:

~~~text
DocumentExportException
    caused by -> DocumentReadException
        caused by -> IOException
~~~

Ở đây:

- <code>exportFailure.getCause()</code> trả về <code>DocumentReadException</code>.
- <code>exportFailure.getCause().getCause()</code> trả về <code>IOException</code>.
- <code>exportFailure.getCause()</code> **không** trực tiếp trả về ngoại lệ sâu nhất.
- Chuỗi cause chỉ có giá trị khi mỗi lần chuyển đổi thể hiện thêm ý nghĩa cần thiết; không nên tạo thêm tầng chỉ để có nhiều tầng.

**Cause khác với message.** Message là văn bản có thể thay đổi theo ngữ cảnh hoặc phiên bản triển khai. Cause là tham chiếu tới một đối tượng chứa loại lỗi, thông điệp, stack trace và các thông tin liên quan. Việc sao chép <code>original.getMessage()</code> vào message mới không đồng nghĩa với giữ nguyên cause.

## 4. Constructor có cause: cách nên dùng

Khi định nghĩa một loại unchecked exception ở tầng API, constructor đơn giản nhất cho việc chuyển đổi lỗi là:

~~~java
public final class DocumentReadException extends RuntimeException {
    public DocumentReadException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là **một lớp độc lập** nếu đặt trong tệp <code>DocumentReadException.java</code>. Constructor của <code>RuntimeException</code> tiếp nhận cả message và cause, nên:

- <code>getMessage()</code> của ngoại lệ mới trả về message dành cho API.
- <code>getCause()</code> của ngoại lệ mới trả về đối tượng đã truyền vào.
- Stack trace của ngoại lệ mới phản ánh vị trí tạo/ném wrapper, trong khi cause giữ stack trace của chính nó.

Nếu API dùng checked exception, cách giữ cause tương tự, chỉ cần kế thừa <code>Exception</code> và khai báo/bắt checked exception theo quy định Java:

~~~java
public final class DocumentReadCheckedException extends Exception {
    public DocumentReadCheckedException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây cũng là một lớp độc lập nếu lưu tại <code>DocumentReadCheckedException.java</code>. Việc chọn checked hay unchecked là lựa chọn hợp đồng API, không làm thay đổi nguyên tắc giữ cause.

### Ba cách viết và hệ quả

Các đoạn sau là **mã minh họa đặt trong một khối <code>catch (IOException original)</code>** với exception class phù hợp.

**Đúng — message ở tầng API, cause là lỗi gốc:**

~~~java
throw new DocumentReadException(
        "Không thể đọc tài liệu đã yêu cầu", original);
~~~

**Sai — chỉ giữ message, bỏ mất cause:**

~~~java
throw new DocumentReadException(
        "Không thể đọc tài liệu: " + original.getMessage(), null);
~~~

**Sai về mặt thiết kế — tạo một lỗi kỹ thuật mới thay cho lỗi kỹ thuật gốc:**

~~~java
throw new DocumentReadException(
        "Không thể đọc tài liệu",
        new IOException(original.getMessage()));
~~~

Cách thứ ba có thể tạo ra một <code>IOException</code> mới không có cùng stack trace và danh tính với lỗi gốc. Nếu không liên kết <code>original</code> là cause của ngoại lệ trung gian thì mất đường truy vết tới chính sự cố đã xảy ra. Cách đúng thường là truyền thẳng <code>original</code> làm cause.

Đừng sử dụng text của lỗi gốc để giả lập type của ngoại lệ hoặc đặt thông tin nhạy cảm vào thông báo công khai. Message của ngoại lệ mới nên mô tả hành động thất bại theo hợp đồng; cause phục vụ chẩn đoán kỹ thuật.

## 5. Ví dụ Java 17+ độc lập: đọc tài liệu và giữ đúng cause

Tạo tệp **CausePreservationDemo.java** với toàn bộ nội dung sau. Ví dụ dùng một nguồn dữ liệu giả lập để kết quả xác định và không phụ thuộc tệp thực tế trên máy.

~~~java
import java.io.IOException;
import java.nio.file.NoSuchFileException;
import java.util.Objects;

public class CausePreservationDemo {

    @FunctionalInterface
    interface RawDocumentSource {
        String read(String id) throws IOException;
    }

    static final class DocumentNotFoundException extends RuntimeException {
        DocumentNotFoundException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class DocumentReadException extends RuntimeException {
        DocumentReadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class DocumentGateway {
        private final RawDocumentSource source;

        DocumentGateway(RawDocumentSource source) {
            this.source = Objects.requireNonNull(source);
        }

        String getDocument(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("ID tài liệu không hợp lệ");
            }

            try {
                return source.read(id);
            } catch (NoSuchFileException original) {
                throw new DocumentNotFoundException(
                        "Không tìm thấy tài liệu: " + id, original);
            } catch (IOException original) {
                throw new DocumentReadException(
                        "Không thể đọc tài liệu: " + id, original);
            }
        }
    }

    public static void main(String[] args) {
        DocumentGateway success =
                new DocumentGateway(id -> "Nội dung hướng dẫn");
        System.out.println("Thành công: " + success.getDocument("guide"));

        NoSuchFileException missing = new NoSuchFileException("guide");
        DocumentGateway absent = new DocumentGateway(id -> {
            throw missing;
        });

        try {
            absent.getDocument("guide");
        } catch (DocumentNotFoundException translated) {
            System.out.println(
                    "Không tìm thấy: " + translated.getClass().getSimpleName()
                    + " <- " + translated.getCause().getClass().getSimpleName());
            System.out.println(
                    "Giữ đúng instance cause: " + (translated.getCause() == missing));
        }

        IOException diskError = new IOException("Storage failure");
        DocumentGateway failed = new DocumentGateway(id -> {
            throw diskError;
        });

        try {
            failed.getDocument("guide");
        } catch (DocumentReadException translated) {
            System.out.println(
                    "Không đọc được: " + translated.getClass().getSimpleName()
                    + " <- " + translated.getCause().getClass().getSimpleName());
            System.out.println(
                    "Giữ đúng instance cause: " + (translated.getCause() == diskError));
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 CausePreservationDemo.java
java CausePreservationDemo
~~~

**Stdout chính xác:**

~~~text
Thành công: Nội dung hướng dẫn
Không tìm thấy: DocumentNotFoundException <- NoSuchFileException
Giữ đúng instance cause: true
Không đọc được: DocumentReadException <- IOException
Giữ đúng instance cause: true
~~~

### Diễn giải cơ chế

1. <code>RawDocumentSource</code> đại diện cho tầng cung cấp dữ liệu thô. Nó được phép ném <code>IOException</code>, giống như nhiều API I/O của Java.
2. <code>DocumentGateway</code> là ranh giới API dành cho bên gọi. Nó không bắt người gọi phải hiểu chi tiết lưu trữ.
3. <code>NoSuchFileException</code> được bắt trước <code>IOException</code> vì nó là lớp con của <code>IOException</code>. Thứ tự ngược lại khiến khối <code>catch</code> chuyên biệt không thể tới được.
4. Từng <code>catch</code> tạo ngoại lệ mang ý nghĩa API và **truyền cùng đối tượng** <code>original</code> vào constructor.
5. Phép so sánh <code>translated.getCause() == missing</code> và <code>== diskError</code> trả về <code>true</code>. Đây là bằng chứng mạnh hơn việc chỉ kiểm tra cùng class hoặc cùng message.
6. Trường hợp thành công không sinh wrapper. Việc chuyển lỗi chỉ xảy ra khi nguồn thực sự ném ngoại lệ phù hợp.
7. Kiểm tra ID trống được thực hiện trước truy cập tầng dưới; lỗi yêu cầu không hợp lệ không bị ngụy trang thành lỗi I/O.

Ví dụ trên dùng kiểu unchecked exception của API. Nếu hợp đồng muốn dùng checked exception, có thể dùng lớp kế thừa <code>Exception</code> và khai báo <code>throws</code> tương ứng; **cách nối cause vẫn giữ nguyên**.

Tại một triển khai thực tế, <code>RawDocumentSource</code> có thể gọi <code>Files.readString(...)</code>, JDBC hoặc một adapter khác. Tuy nhiên, không phải mọi lỗi kỹ thuật đều nên quy về “không tìm thấy”: ví dụ <code>IOException</code> chung được dịch thành “không thể đọc” để tránh khẳng định sai nguyên nhân.

## 6. Đọc chuỗi cause khi điều tra lỗi

Khi một exception wrapper được in bằng <code>printStackTrace()</code> hoặc được logger ghi kèm đối tượng <code>Throwable</code>, đầu ra thường có đoạn kiểu sau:

~~~text
DocumentReadException: Không thể đọc tài liệu: guide
    at ...DocumentGateway.getDocument(...)
Caused by: java.io.IOException: Storage failure
    at ... vị trí sinh lỗi gốc ...
~~~

Đây là **minh họa cấu trúc stack trace**, không phải stdout chính xác của chương trình phía trên. Tên package, đường dẫn tệp, số dòng, stack trace và định dạng có thể khác nhau tùy cách chạy.

Điều cần hiểu:

- Phần trước <code>Caused by</code> mô tả ngoại lệ của tầng API cùng vị trí nó được ném.
- Phần <code>Caused by</code> chứa loại ngoại lệ và stack trace được lưu trên đối tượng kỹ thuật ban đầu.
- Nếu có nhiều tầng cause, các mục <code>Caused by</code> được hiển thị tiếp theo thứ tự liên kết.
- Khi in stack trace, Java có thể rút gọn các frame chung bằng dòng dạng <code>... N more</code>. Đó là tối ưu hiển thị, không có nghĩa cause đã bị mất.

Không nên dựng lại chuỗi lỗi bằng cách nối <code>getMessage()</code> của từng tầng rồi coi đó là bằng chứng hoàn chỉnh. Chuỗi ký tự không lưu được danh tính exception, cấu trúc cause hay đầy đủ stack trace.

### Khi truy cập cause bằng code

~~~java
Throwable cause = translated.getCause();
if (cause != null) {
    System.out.println("Cause type: " + cause.getClass().getName());
    System.out.println("Cause message: " + cause.getMessage());
}
~~~

Đây là **đoạn minh họa** giả định biến <code>translated</code> đang chứa một ngoại lệ. Việc kiểm tra <code>null</code> cần thiết vì không phải ngoại lệ nào cũng có cause. Với code sản phẩm, cân nhắc không đưa message kỹ thuật ra giao diện người dùng.

Một số thư viện cung cấp tiện ích phân tích “root cause”, nhưng <code>Throwable</code> chỉ quy định liên kết cause trực tiếp. Muốn truy sâu, phải duyệt từng cấp theo nhu cầu; tránh giả định mọi ngoại lệ có cùng số tầng hoặc cause luôn khác <code>null</code>.

## 7. Giữ cause qua nhiều ranh giới: khi nào thật sự cần thêm wrapper?

Giả sử tầng lưu trữ đã ném <code>DocumentReadException</code>. Tầng dùng nó để **xuất báo cáo** có thể muốn biểu diễn một hành động lớn hơn, chẳng hạn <code>ReportExportException</code>, vì người gọi tác vụ xuất báo cáo cần hiểu thất bại ở mức báo cáo.

Một sơ đồ hợp lý có thể là:

~~~text
IOException
    |
    | giữ cause khi vào DocumentGateway
    v
DocumentReadException
    |
    | chỉ chuyển tiếp hoặc bọc thêm nếu hợp đồng xuất báo cáo
    | cần diễn đạt một ngữ nghĩa mới
    v
ReportExportException
~~~

Nếu muốn bọc thêm ở một tầng mới, constructor vẫn nhận cause:

~~~java
public final class ReportExportException extends RuntimeException {
    public ReportExportException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Trong phạm vi một phương thức nghiệp vụ có đối tượng <code>gateway</code> tương ứng, có thể minh họa như sau:

~~~java
try {
    String document = gateway.getDocument("guide");
    exportReport(document);
} catch (DocumentReadException original) {
    throw new ReportExportException("Không thể xuất báo cáo", original);
}
~~~

**Đoạn <code>try/catch</code> này chỉ minh họa**, giả định <code>gateway</code> và <code>exportReport</code> đã được khai báo trong ứng dụng. Nếu không có ngữ nghĩa xuất báo cáo cần thêm, nên cho <code>DocumentReadException</code> đi qua, tránh wrapper thừa.

Một chuỗi cause gồm ba đối tượng là hợp lý nếu nó mô tả ba trách nhiệm thực sự khác nhau. Nếu tầng nào cũng bọc bằng một <code>RuntimeException("Lỗi", e)</code> chung, người đọc sẽ phải tháo nhiều lớp vô nghĩa để tìm ra lỗi thực.

### Khi nào không nên wrap?

- Ngoại lệ đã biểu đạt đúng hợp đồng của tầng hiện tại; có thể ném tiếp bằng <code>throw e;</code> hoặc để lan truyền.
- Tầng hiện tại chỉ ghi log rồi chuyển lỗi lên; việc tạo exception mới chỉ để log thường không tăng ích lợi.
- Không hiểu được nguyên nhân kỹ thuật để phân loại một cách đáng tin cậy; khi cần, dùng loại lỗi API tổng quát thích hợp với cause gốc.
- Ngoại lệ là lỗi lập trình hoặc lỗi nghiêm trọng không nằm trong hợp đồng xử lý của thao tác.

### Khi nào xử lý thay vì wrap?

Nếu ứng dụng có nguồn dự phòng và có thể hoàn thành thao tác đúng hợp đồng, đó là **phục hồi lỗi**, có thể không cần ném wrapper. Ngược lại, trả <code>null</code>, chuỗi rỗng hoặc dữ liệu giả chỉ để làm ngoại lệ biến mất sẽ khiến bên gọi hiểu sai kết quả nếu hợp đồng không quy định cách đó.

## 8. Cause, suppressed exception và lỗi khi đóng tài nguyên

Cause và suppressed exception giải quyết hai vấn đề khác nhau:

- **Cause**: lỗi trực tiếp gây ra ngoại lệ hiện tại, thường là lỗi được dịch từ tầng dưới.
- **Suppressed**: các ngoại lệ phát sinh thêm trong quá trình xử lý lỗi hoặc đóng tài nguyên, được giữ để không che mất lỗi chính.

Với <code>try-with-resources</code>, nếu cả thao tác trong <code>try</code> và thao tác <code>close()</code> đều ném ngoại lệ, lỗi trong thân <code>try</code> thường là lỗi chính; lỗi từ <code>close()</code> được thêm vào <code>getSuppressed()</code> của lỗi chính.

Ví dụ Java 17 độc lập, lưu thành **SuppressedCauseDemo.java**:

~~~java
import java.io.IOException;

public class SuppressedCauseDemo {

    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("Lỗi khi đóng");
        }
    }

    static final class ReadOperationException extends RuntimeException {
        ReadOperationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void read() {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("Lỗi khi đọc");
        } catch (IOException original) {
            throw new ReadOperationException("Đọc tài nguyên thất bại", original);
        }
    }

    public static void main(String[] args) {
        try {
            read();
        } catch (ReadOperationException translated) {
            Throwable cause = translated.getCause();
            System.out.println("Cause: " + cause.getMessage());
            System.out.println("Suppressed: "
                    + cause.getSuppressed()[0].getMessage());
            System.out.println("Số suppressed: "
                    + cause.getSuppressed().length);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SuppressedCauseDemo.java
java SuppressedCauseDemo
~~~

**Stdout chính xác:**

~~~text
Cause: Lỗi khi đọc
Suppressed: Lỗi khi đóng
Số suppressed: 1
~~~

Ở đây wrapper giữ nguyên đối tượng <code>IOException("Lỗi khi đọc")</code> làm cause. Đối tượng cause đó đã giữ ngoại lệ <code>IOException("Lỗi khi đóng")</code> trong danh sách suppressed. Nếu tạo một <code>IOException</code> mới từ message rồi bỏ bản gốc, cả bối cảnh đọc lẫn lỗi đóng tài nguyên có nguy cơ bị mất.

Không được giả định mọi <code>IOException</code> đều có suppressed exception; chương trình ví dụ cố ý làm lỗi cả hai thao tác. Trong sản phẩm, phải kiểm tra độ dài mảng <code>getSuppressed()</code> trước khi truy cập phần tử. Khi chỉ cần ghi log chẩn đoán, việc truyền toàn bộ ngoại lệ cho logger thường tốt hơn viết mã thủ công để ghép từng suppressed error.

## 9. Không dùng initCause như lựa chọn mặc định

Ngoài constructor <code>Throwable(String message, Throwable cause)</code>, Java còn cung cấp <code>initCause(Throwable cause)</code>. API này phục vụ tình huống cần liên kết cause **sau khi** tạo ngoại lệ, chẳng hạn khi lớp ngoại lệ cũ không có constructor thích hợp.

Ví dụ minh họa trong ngữ cảnh phù hợp:

~~~java
RuntimeException translated =
        new RuntimeException("Không thể xử lý yêu cầu");
translated.initCause(original);
throw translated;
~~~

Trong đoạn trên, <code>original</code> là một đối tượng <code>Throwable</code> đã có trước. Không gọi <code>initCause</code> nhiều lần và không đặt chính ngoại lệ đó làm cause của nó. Nếu cause đã được khởi tạo bằng constructor (kể cả constructor có tham số cause là <code>null</code>), gọi <code>initCause</code> tiếp sẽ phát sinh <code>IllegalStateException</code>; việc tự gán chính nó làm cause cũng không hợp lệ. 

Đối với lớp ngoại lệ do mình sở hữu, constructor nhận <code>Throwable cause</code> thường rõ ràng và ít sai sót hơn. <code>initCause</code> phù hợp hơn với trường hợp tương thích API cũ, không nên dùng để sửa chữa một chuỗi cause đã tạo sai.

## 10. Chẩn đoán nội bộ và thông báo an toàn cho bên gọi

Giữ cause **không có nghĩa công khai mọi thông tin trong cause**. Ngoại lệ kỹ thuật có thể chứa đường dẫn máy chủ, tên bảng dữ liệu, thông tin truy vấn, hostname, địa chỉ dịch vụ hoặc dữ liệu nhạy cảm.

Nên tách:

1. **Hợp đồng cho client**: loại lỗi nghiệp vụ/kỹ thuật ở mức API, mã lỗi ổn định nếu cần, message không tiết lộ bí mật.
2. **Chẩn đoán nội bộ**: full exception object, cause chain, suppressed exceptions, thông tin tương quan như request ID, được lưu ở nơi có kiểm soát truy cập.
3. **Hành vi xử lý**: client có thể quyết định thông báo người dùng, yêu cầu nhập lại, chuyển hướng hoặc thử lại khi thao tác thật sự cho phép.

Ví dụ, API bên ngoài có thể chỉ phản hồi “Không thể tải tài liệu lúc này”, trong khi log nội bộ vẫn truy tới <code>DocumentReadException</code> và <code>IOException</code>. Việc ánh xạ ngoại lệ sang một HTTP status hay mã gRPC phụ thuộc vào ranh giới giao tiếp, không thuộc trách nhiệm của lớp I/O.

### Chiến lược ghi log

Khi cần ghi stack trace bằng thư viện logging có hỗ trợ đối tượng <code>Throwable</code>, hãy truyền exception vào tham số phù hợp của logger, thay vì chỉ nối <code>e.getMessage()</code>. Tuy nhiên, không nên ghi cùng một ngoại lệ ở mọi tầng rồi ném lại, vì có thể tạo nhiều bản log giống nhau cho một yêu cầu.

Nếu lỗi chưa được xử lý ở tầng hiện tại, có thể giữ cause và để lỗi lan truyền tới ranh giới giám sát thích hợp. Nếu tầng hiện tại đã thực sự khôi phục lỗi, log ở mức phù hợp với sự cố đã được xử lý. Chính sách cụ thể phụ thuộc ứng dụng, nhưng việc giữ cause khiến lựa chọn quan sát ở tầng sau vẫn khả thi.

**Tránh** dùng message của ngoại lệ thấp làm lời giải thích công khai bắt buộc. Message của driver hoặc thư viện không phải hợp đồng ổn định, và có thể lộ thông tin hoặc thay đổi giữa các phiên bản.

## 11. Những trường hợp đặc biệt cần phân biệt

### 11.1. Không bắt mọi Exception rồi dịch thành một lỗi duy nhất

~~~java
try {
    executeOperation();
} catch (Exception e) {
    throw new DocumentReadException("Lỗi đọc tài liệu", e);
}
~~~

Đây là **mã minh họa**, không phải chương trình độc lập. Nó giữ cause, nhưng có thể vẫn **dịch sai ngữ nghĩa**: lỗi validate, lỗi lập trình, lỗi nghiệp vụ đã được dịch hoặc <code>InterruptedException</code> đều có nguy cơ bị gộp vào “lỗi đọc”. Giữ cause là điều kiện quan trọng nhưng **chưa đủ** cho một exception translation đúng.

Nên bắt các loại ngoại lệ thuộc phạm vi chuyển đổi của API, phân loại theo hợp đồng, và tránh bắt <code>Throwable</code> như một lỗi nghiệp vụ thông thường. <code>Error</code> và các lỗi nghiêm trọng của môi trường chạy không nên bị mặc định biến thành lỗi có thể phục hồi.

### 11.2. InterruptedException cần bảo toàn tín hiệu ngắt

Nếu một thao tác blocking ném <code>InterruptedException</code> và API buộc phải chuyển nó thành unchecked exception, ứng dụng thường cần khôi phục trạng thái ngắt trước khi ném wrapper:

~~~java
try {
    blockingCall();
} catch (InterruptedException original) {
    Thread.currentThread().interrupt();
    throw new OperationInterruptedException(
            "Thao tác bị ngắt", original);
}
~~~

Đây là **mã minh họa**: <code>blockingCall()</code> và <code>OperationInterruptedException</code> là những thành phần được giả định có trong ngữ cảnh ứng dụng. Nếu hợp đồng cho phép, khai báo và chuyển tiếp <code>InterruptedException</code> trực tiếp là một lựa chọn tốt khác.

Việc chỉ lưu <code>original</code> làm cause **không tự khôi phục interrupt flag** cho luồng. Hai việc này độc lập: cause giữ bằng chứng, còn <code>Thread.currentThread().interrupt()</code> khôi phục tín hiệu điều khiển hợp tác để code phía trên có thể nhận biết.

### 11.3. Không tự động biến timeout thành “chưa xử lý”

Một lời gọi tới dịch vụ ngoài timeout có thể đã được máy chủ xử lý trước khi kết nối đứt. Wrapper có cause chỉ cho biết ngoại lệ kỹ thuật gốc, không tự chứng minh thao tác chưa thành công. Nếu cho client thử lại, cần dựa vào đặc tính idempotent, idempotency key hoặc hợp đồng riêng của thao tác.

### 11.4. Không sửa trực tiếp stack trace để che cause

Không nên gọi <code>setStackTrace(...)</code> hay tạo đối tượng lỗi mới từ text chỉ nhằm bỏ dấu vết gốc. Trong những tình huống bảo mật, cần kiểm soát **nơi hiển thị/log lỗi**, đồng thời vẫn bảo toàn thông tin nội bộ theo chính sách lưu trữ thích hợp. Chỉ cân nhắc loại bỏ thông tin khi đó là chủ đích rõ ràng của ranh giới tin cậy.

## 12. Kiểm thử: xác nhận danh tính cause và hợp đồng bên ngoài

Một bộ kiểm thử tốt không chỉ hỏi “có ném exception không?” mà còn hỏi ngoại lệ có **đúng tầng nghĩa**, và cause có **đúng đối tượng ban đầu** hay không.

| Tình huống | Điều cần khẳng định |
| --- | --- |
| Nguồn dữ liệu trả nội dung bình thường | Không ném ngoại lệ; nội dung không thay đổi |
| Nguồn ném <code>NoSuchFileException</code> | Bên gọi nhận <code>DocumentNotFoundException</code> |
| Nguồn ném <code>IOException</code> khác | Bên gọi nhận <code>DocumentReadException</code> |
| Ngoại lệ đã được dịch | <code>translated.getCause() == original</code> |
| Bên gọi nhận lỗi được công bố | Không cần phụ thuộc trực tiếp vào loại exception nội bộ của adapter để ra quyết định |
| Nguồn sinh lỗi bất ngờ ngoài <code>IOException</code> | Không bị các nhánh <code>catch (IOException)</code> đổi loại vô cớ |
| Thao tác đóng tài nguyên cũng thất bại | Suppressed exception còn được truy cập qua cause nếu nguyên nhân ban đầu được giữ |
| Input sai | Được từ chối ở ranh giới input theo hợp đồng, không bị giả dạng thành lỗi hạ tầng |

Trong demo chạy độc lập ở mục 5, hai phép so sánh <code>==</code> đã kiểm tra chính xác object identity. Với JUnit 5, có thể viết kiểm thử bằng <code>assertThrows</code> và <code>assertSame</code>.

Đoạn mã bên dưới **minh họa trong một dự án JUnit 5 đã có dependency, các lớp <code>DocumentGateway</code> và <code>DocumentReadException</code> ở phạm vi truy cập phù hợp**:

~~~java
IOException original = new IOException("disk error");
DocumentGateway gateway = new DocumentGateway(id -> {
    throw original;
});

DocumentReadException actual = assertThrows(
        DocumentReadException.class,
        () -> gateway.getDocument("guide"));

assertSame(original, actual.getCause());
~~~

Khi áp dụng trong tệp test thực tế, cần có import <code>java.io.IOException</code> và các static import từ <code>org.junit.jupiter.api.Assertions</code>. Đoạn minh họa trên không phải một chương trình Java độc lập.

Điểm mấu chốt của <code>assertSame</code>: hai exception có thể cùng class, cùng message nhưng là **hai đối tượng khác nhau**. Chỉ kiểm tra <code>getCause() instanceof IOException</code> sẽ không phát hiện trường hợp ai đó tạo <code>new IOException(original.getMessage())</code> rồi đánh mất exception gốc.

Đối với message của API, nên kiểm tra phần thông tin hợp đồng ổn định. Đừng buộc kiểm thử phụ thuộc từng câu message của hệ điều hành hoặc từng dòng stack trace, vì chúng thay đổi giữa môi trường.

## 13. Lỗi phổ biến khi giữ cause

1. **Chỉ copy message:** <code>new HighLevelException(original.getMessage())</code> không ghi lại đối tượng nguyên nhân.
2. **Truyền <code>null</code> vô tình:** constructor có cause nhưng thực tế không nhận được lỗi gốc.
3. **Tạo cause “tương tự”:** thay <code>original</code> bằng <code>new IOException(original.getMessage())</code> làm mất danh tính, stack trace và có thể cả suppressed exceptions.
4. **Chỉ giữ cause mà dịch sai loại lỗi:** ví dụ mọi ngoại lệ đều thành <code>NotFoundException</code>. Cause không cứu được hợp đồng sai.
5. **Bọc lặp nhiều tầng không thêm nghĩa:** stack trace khó đọc, client phải lần qua wrapper không cần thiết.
6. **Tưởng message là stack trace:** message chỉ là một chuỗi, còn full exception mang nhiều thông tin hơn.
7. **Quên kiểm tra <code>getCause() == null</code>:** nhiều ngoại lệ được ném trực tiếp không có cause.
8. **Nhầm suppressed exception với cause:** lỗi đóng tài nguyên có thể được lưu trong <code>getSuppressed()</code> của cause.
9. **Bắt quá rộng:** có thể che <code>InterruptedException</code>, lỗi validation hoặc các lỗi đã được dịch đúng.
10. **Lộ chi tiết kỹ thuật cho người dùng:** giữ cause nội bộ nhưng không tự động gửi nguyên stack trace hoặc message nhạy cảm ra API response.
11. **Ghi log lặp lại mọi lần catch:** cùng một sự cố xuất hiện nhiều lần trong log mà không cung cấp thêm bối cảnh.
12. **Kiểm thử chỉ nhìn loại ngoại lệ bên ngoài:** không phát hiện hồi quy làm mất nguyên nhân gốc.

## 14. Cách review một phép chuyển đổi lỗi

Hãy đọc một khối <code>catch</code> theo trình tự:

1. **Có cần dịch không?** Tầng này có cung cấp một hợp đồng khác tầng phát sinh lỗi không?
2. **Ánh xạ đúng không?** Loại exception mới có diễn đạt đúng điều có thể biết chắc từ lỗi thấp hơn không?
3. **Giữ gốc chưa?** Constructor có nhận **chính biến exception đã bắt** làm cause không?
4. **Message có phù hợp không?** Có giải thích hành động thất bại ở mức API mà không tiết lộ dữ liệu nhạy cảm không?
5. **Có thông tin phụ nào cần giữ không?** Cause có mang stack trace, suppressed exceptions và bối cảnh lỗi của thư viện không?
6. **Kiểm thử đã chứng minh chưa?** Có ít nhất một trường hợp khẳng định <code>assertSame(original, translated.getCause())</code> hoặc tương đương không?
7. **Tầng tiếp theo nên làm gì?** Cho ngoại lệ đi qua, chuyển sang hợp đồng nghiệp vụ khác, khôi phục lỗi hay ánh xạ sang kết quả giao tiếp?
8. **Có xử lý luồng và tài nguyên đúng không?** Đặc biệt với interrupt, cleanup và thao tác có thể đã thành công một phần.

**Điều cần nhớ:** Ngoại lệ bên ngoài giúp bên gọi hiểu **ý nghĩa của thất bại**; cause giữ lại **bằng chứng về thất bại đã xảy ra**. Kết hợp đúng hai thông tin này cho phép API che giấu chi tiết triển khai mà vẫn giữ được khả năng chẩn đoán chính xác khi sự cố phát sinh.