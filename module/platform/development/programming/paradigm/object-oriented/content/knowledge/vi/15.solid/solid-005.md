# Phân tách giao diện: hợp đồng phù hợp từng bên sử dụng (Interface Segregation Principle — ISP)

> **Ngữ cảnh:** SOLID trong thiết kế hướng đối tượng. **Ý chính:** một bên sử dụng chỉ nên phụ thuộc vào những thao tác mà nó thực sự cần.

## 1. ISP giải quyết vấn đề gì?

**Interface Segregation Principle (ISP)** thường được diễn đạt: *Clients should not be forced to depend upon interfaces that they do not use* — không ép client phụ thuộc vào các phương thức mà nó không sử dụng.

Trong Java, **client** là lớp, dịch vụ hoặc module gọi qua một hợp đồng; không nhất thiết là người dùng cuối. **Interface** ở đây mang nghĩa hợp đồng lập trình, có thể là Java interface hay lớp trừu tượng. Một hợp đồng quá nhiều trách nhiệm (*fat interface*) buộc các client rất khác nhau nhìn thấy cùng một nhóm thao tác.

Ví dụ, ứng dụng quản lý tài liệu có ba nhu cầu riêng:

| Client | Nhu cầu thực tế | Hợp đồng nên biết |
| --- | --- | --- |
| Dịch vụ tải tài liệu | Đọc theo mã | **DocumentReader** |
| Tác vụ nhập tài liệu | Lưu tài liệu | **DocumentWriter** |
| Tác vụ dọn dữ liệu | Xóa theo chính sách | **DocumentDeleter** |
| Kho lưu trữ chỉ đọc | Cung cấp dữ liệu để tra cứu | Chỉ cần triển khai **DocumentReader** |

Nếu tất cả đều phụ thuộc vào **DocumentStorage** chứa cả đọc, ghi và xóa, ứng dụng tạo ra những phụ thuộc không cần thiết. Đặc biệt, kho chỉ đọc có thể bị ép khai báo các thao tác mà nó không hỗ trợ.

### Dấu hiệu thiết kế đang vi phạm ISP

- Lớp triển khai hàng loạt phương thức chỉ để ném **UnsupportedOperationException**, trả giá trị giả hoặc để trống.
- Một client chỉ dùng 1–2 phương thức nhưng phải mock/stub một hợp đồng có hàng chục phương thức để kiểm thử.
- Bổ sung tính năng thuộc một nhóm client lại kéo theo sửa nhiều lớp thuộc nhóm khác.
- Phân quyền nghiệp vụ khác nhau (chỉ đọc, chỉ ghi, quản trị) nhưng tất cả cùng nhận một API toàn quyền.

**Điểm cần phân biệt:** một interface có nhiều phương thức *không tự động* là sai. Sai khi các nhóm client có nhu cầu khác nhau nhưng bị buộc phụ thuộc vào các thao tác không liên quan.

## 2. Thiết kế ban đầu: hợp đồng quá rộng

Giả sử ta bắt mọi loại kho tài liệu tuân theo ba thao tác:

~~~java
import java.util.Map;
import java.util.Optional;

interface DocumentStorage {
    Optional<String> findById(String id);
    void save(String id, String content);
    void delete(String id);
}

final class ReadOnlyArchive implements DocumentStorage {
    private final Map<String, String> snapshot = Map.of("A1", "Biên bản");

    @Override
    public Optional<String> findById(String id) {
        return Optional.ofNullable(snapshot.get(id));
    }

    @Override
    public void save(String id, String content) {
        throw new UnsupportedOperationException("Kho chỉ đọc");
    }

    @Override
    public void delete(String id) {
        throw new UnsupportedOperationException("Kho chỉ đọc");
    }
}
~~~

**Vấn đề:** **ReadOnlyArchive** chỉ có năng lực đọc, nhưng **DocumentStorage** lại tuyên bố đối tượng có cả năng lực ghi và xóa. Client có thể gọi **save/delete** một cách hợp lệ ở thời điểm biên dịch và chỉ nhận lỗi khi chạy. Việc này đồng thời là dấu hiệu đáng xem xét dưới góc độ **Liskov Substitution Principle (LSP)**: đối tượng triển khai không thực hiện đúng kỳ vọng của hợp đồng rộng.

Không nên vá bằng cách trả về thành công giả, thêm phương thức rỗng hoặc dùng **default method** để che một khả năng vốn không tồn tại. Hãy thu nhỏ hợp đồng theo người sử dụng.

## 3. Thiết kế lại theo ISP: nhiều hợp đồng nhỏ, có mục đích

Mã sau đặt trong **IspDemo.java**, dùng **Java 17+**, biên dịch và chạy độc lập. Mỗi interface mô tả một năng lực. **InMemoryStore** cung cấp cả ba năng lực; **ReadOnlyArchive** chỉ cung cấp năng lực đọc. Client chỉ nhận đúng hợp đồng nó cần.

~~~java
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public class IspDemo {

    // Hợp đồng dành cho client chỉ cần đọc.
    interface DocumentReader {
        Optional<String> findById(String id);
    }

    // Hợp đồng dành cho client cần nhập hoặc cập nhật.
    interface DocumentWriter {
        void save(String id, String content);
    }

    // Hợp đồng dành cho công việc dọn dữ liệu.
    interface DocumentDeleter {
        void delete(String id);
    }

    // Một adapter được phép hỗ trợ nhiều hợp đồng.
    static final class InMemoryStore
            implements DocumentReader, DocumentWriter, DocumentDeleter {
        private final Map<String, String> data = new ConcurrentHashMap<>();

        @Override
        public Optional<String> findById(String id) {
            return Optional.ofNullable(data.get(id));
        }

        @Override
        public void save(String id, String content) {
            data.put(Objects.requireNonNull(id),
                     Objects.requireNonNull(content));
        }

        @Override
        public void delete(String id) {
            data.remove(id);
        }
    }

    // Không cần triển khai phương thức ghi/xóa giả.
    static final class ReadOnlyArchive implements DocumentReader {
        private final Map<String, String> snapshot;

        ReadOnlyArchive(Map<String, String> source) {
            this.snapshot = Map.copyOf(source);
        }

        @Override
        public Optional<String> findById(String id) {
            return Optional.ofNullable(snapshot.get(id));
        }
    }

    static final class DownloadService {
        private final DocumentReader reader;

        DownloadService(DocumentReader reader) {
            this.reader = Objects.requireNonNull(reader);
        }

        String download(String id) {
            return reader.findById(id)
                    .orElseThrow(() -> new NoSuchElementException(id));
        }
    }

    static final class ImportService {
        private final DocumentWriter writer;

        ImportService(DocumentWriter writer) {
            this.writer = Objects.requireNonNull(writer);
        }

        void importFile(String id, String content) {
            writer.save(id, content);
        }
    }

    public static void main(String[] args) {
        InMemoryStore mainStore = new InMemoryStore();

        new ImportService(mainStore).importFile("D01", "Hợp đồng mới");
        System.out.println(
                new DownloadService(mainStore).download("D01"));

        DocumentReader archive =
                new ReadOnlyArchive(Map.of("A01", "Bản lưu năm trước"));
        System.out.println(
                new DownloadService(archive).download("A01"));
    }
}
~~~

Chạy:

~~~bash
javac IspDemo.java
java IspDemo
~~~

Kết quả:

~~~text
Hợp đồng mới
Bản lưu năm trước
~~~

**Điều đáng chú ý trong ví dụ:**

1. **DownloadService** chỉ biết **DocumentReader**. Nó không thấy API xóa dù đối tượng thực tế có thể hỗ trợ xóa.
2. **ImportService** chỉ biết **DocumentWriter**. Nó nhận được **InMemoryStore**, nhưng không được giả định quyền đọc hoặc xóa.
3. **ReadOnlyArchive** không cần phương thức không hỗ trợ, vì hợp đồng đã phản ánh đúng năng lực.
4. Một lớp được **implements** nhiều interface khi bản thân thực sự cung cấp nhiều năng lực. ISP không buộc tạo một lớp riêng cho mỗi interface.
5. **Optional.empty()** thể hiện tài liệu không tồn tại. Nó không đại diện cho lỗi mạng, lỗi phân quyền hoặc lỗi hệ thống; các trường hợp đó cần cơ chế lỗi phù hợp.

Để ứng dụng sản xuất dễ bảo trì, hãy đặt từng interface và các lớp nghiệp vụ vào file/package thích hợp. Việc lồng các kiểu trong **IspDemo** chỉ nhằm cung cấp ví dụ chạy được ngay.

## 4. Sơ đồ phụ thuộc sau khi phân tách

~~~mermaid
classDiagram
    class DocumentReader {
        <<interface>>
        +findById(id) Optional~String~
    }
    class DocumentWriter {
        <<interface>>
        +save(id, content) void
    }
    class DocumentDeleter {
        <<interface>>
        +delete(id) void
    }
    class DownloadService
    class ImportService
    class InMemoryStore
    class ReadOnlyArchive

    DownloadService --> DocumentReader : uses
    ImportService --> DocumentWriter : uses
    DocumentReader <|.. InMemoryStore
    DocumentWriter <|.. InMemoryStore
    DocumentDeleter <|.. InMemoryStore
    DocumentReader <|.. ReadOnlyArchive
~~~

Mũi tên từ **Service** sang **interface** diễn đạt sự phụ thuộc ở phía client; mũi tên **implements** diễn đạt những năng lực mà adapter cung cấp. Mỗi client có thể đổi implementation mà không phải nhận thêm phương thức ngoài nhu cầu của mình.

## 5. Kiểm thử trở nên tập trung hơn

Với **JUnit 5**, ta truyền implementation tối thiểu cho từng client. **DocumentReader** và **DocumentWriter** mỗi loại chỉ có một abstract method, nên có thể biểu diễn bằng lambda khi phù hợp.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class IspDemoTest {

    @Test
    void taiTaiLieuTuKhoChiDoc() {
        var archive =
                new IspDemo.ReadOnlyArchive(Map.of("A1", "Bản lưu"));
        var service = new IspDemo.DownloadService(archive);

        assertEquals("Bản lưu", service.download("A1"));
    }

    @Test
    void nhapTaiLieuChiCanHopDongGhi() {
        AtomicReference<String> recorded = new AtomicReference<>();
        IspDemo.DocumentWriter writer =
                (id, content) -> recorded.set(id + ":" + content);

        var service = new IspDemo.ImportService(writer);
        service.importFile("D1", "Nội dung");

        assertEquals("D1:Nội dung", recorded.get());
    }
}
~~~

Bài kiểm thử đầu xác nhận client đọc hoạt động với kho chỉ đọc. Bài thứ hai kiểm tra client ghi mà không cần tạo các stub cho đọc/xóa. Với ứng dụng Spring, cùng nguyên tắc được áp dụng khi inject các interface theo nhu cầu vào từng **@Service**; các adapter **@Component/@Repository** có thể triển khai nhiều hợp đồng. Nếu có nhiều bean cùng một interface, cấu hình lựa chọn bean bằng **@Qualifier**, **@Primary** hoặc cơ chế cấu hình thích hợp.

## 6. Phân biệt ISP với các nguyên lý gần nó

| Nguyên lý | Câu hỏi thiết kế | Liên hệ với ví dụ |
| --- | --- | --- |
| **ISP** — Interface Segregation | Client có bị phụ thuộc vào phương thức không cần dùng không? | DownloadService chỉ nhận DocumentReader. |
| **SRP** — Single Responsibility | Một module có bao nhiêu lý do độc lập để thay đổi? | Logic tải tài liệu và logic nhập tài liệu nằm ở dịch vụ khác nhau khi trách nhiệm khác nhau. |
| **DIP** — Dependency Inversion | Module nghiệp vụ có phụ thuộc vào abstraction phù hợp thay vì chi tiết lưu trữ không? | DownloadService phụ thuộc DocumentReader, không phụ thuộc InMemoryStore. |
| **LSP** — Liskov Substitution | Implementation có giữ lời hứa của hợp đồng không? | ReadOnlyArchive không tuyên bố hỗ trợ ghi/xóa rồi ném lỗi vì thiếu khả năng. |

Các nguyên lý bổ trợ nhau nhưng không thay thế nhau. Chỉ dùng interface thay cho concrete class chưa chắc thỏa ISP nếu interface đó vẫn quá rộng.

## 7. Thiết kế ranh giới hợp đồng trong dự án thật

Không có quy tắc “cứ một phương thức là một interface”. Hãy phân tách theo **vai trò sử dụng, năng lực và lý do thay đổi**.

| Trường hợp | Quyết định hợp lý | Lý do |
| --- | --- | --- |
| Mọi client luôn cần cùng tập thao tác, chúng có ý nghĩa gắn bó | Giữ một interface gọn, nhất quán | Tránh tạo ra quá nhiều kiểu không mang ý nghĩa. |
| Người xem chỉ đọc, tác vụ đồng bộ chỉ ghi | Tách **Reader** và **Writer** | Client chỉ thấy đúng năng lực cần. |
| Một adapter hỗ trợ toàn bộ các vai trò | Cho lớp đó triển khai nhiều interface | Không phải nhân bản logic hoặc instance. |
| Một client quản trị thực sự cần đầy đủ chức năng | Có thể dùng interface tổng hợp cho đúng client đó | Ví dụ **DocumentAdmin extends DocumentReader, DocumentWriter, DocumentDeleter**. |
| Một thao tác luôn ném **UnsupportedOperationException** vì không hỗ trợ | Xem lại lời hứa của hợp đồng | Có khả năng interface đã bao trùm quá nhiều năng lực. |

Trong hệ thống REST/Spring, phân tách interface Java **không tự động tạo ra phân quyền bảo mật**. Một client chỉ nhận **DocumentReader** là giới hạn ở mức thiết kế/biên dịch; endpoint ghi/xóa vẫn cần kiểm tra xác thực, phân quyền và quy tắc nghiệp vụ tại biên hệ thống.

### Cách refactor an toàn một interface lớn

1. **Lập bản đồ client:** ghi rõ mỗi client đang gọi những phương thức nào, nhóm hành vi nào thay đổi cùng nhau.
2. **Định nghĩa hợp đồng nhỏ:** đặt tên theo năng lực có ý nghĩa trong domain, ví dụ **DocumentReader**, **DocumentWriter**.
3. **Chuyển phụ thuộc dần:** đổi constructor/field/kiểm thử của từng client sang interface tương ứng; để adapter hiện tại triển khai các hợp đồng thực sự hỗ trợ.
4. **Xử lý hợp đồng cũ:** chỉ bỏ interface cũ khi không còn nơi sử dụng; với thư viện public cần cân nhắc tương thích nguồn/binary và lộ trình migration.
5. **Kiểm tra hành vi:** không đánh đổi semantics (lỗi không tìm thấy, quyền truy cập, tính nhất quán dữ liệu) chỉ để interface ngắn hơn.

**Lỗi thường gặp khi áp dụng ISP:**

- Tách interface theo từng hàm một cách máy móc, làm API khó tìm hiểu.
- Chỉ tạo nhiều interface nhưng client vẫn inject một interface tổng hợp.
- Dùng một “God Service” phía sau nhiều interface mà không cải thiện phụ thuộc hoặc trách nhiệm thực tế; ISP chỉ giảm phụ thuộc của client, không tự giải quyết mọi vấn đề của implementation.
- Lạm dụng interface chỉ đọc ở Java để thay cho cơ chế authorization lúc chạy.

## 8. Bài tập thực hành

Một hệ thống thông báo có hợp đồng **NotificationService** gồm **sendEmail()**, **sendSms()**, **sendPush()**. Một job chỉ gửi email, còn một adapter chỉ hỗ trợ SMS.

Hãy thiết kế các interface theo nhóm client (**EmailSender**, **SmsSender**, **PushSender**), viết một **OtpService** chỉ phụ thuộc vào khả năng gửi SMS và tạo fake **SmsSender** để test. Sau đó tự kiểm tra:

- Adapter chỉ hỗ trợ SMS có phải khai báo phương thức email/push giả không?
- **OtpService** có nhìn thấy và vô tình gọi được **sendEmail()** không?
- Nếu một provider hỗ trợ cả email và SMS, nó có thể triển khai hai interface mà không nhân bản provider không?
- Nếu sau này thêm kênh chat, client chỉ dùng SMS có bị buộc sửa không?

**Tiêu chí đạt:** hợp đồng ở phía client chỉ chứa những thao tác client có lý do sử dụng; mỗi implementation thực hiện đúng mọi thao tác mà nó công bố. Đó là giá trị thực tế của **Interface Segregation Principle**.