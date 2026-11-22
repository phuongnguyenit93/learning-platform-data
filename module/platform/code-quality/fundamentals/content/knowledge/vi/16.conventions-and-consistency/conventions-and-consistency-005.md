# Quy ước ngoại lệ, null, tài nguyên và log

Một dịch vụ Java trả `null` khi không tìm thấy báo cáo. Một dịch vụ khác ném `IllegalStateException` cho cùng tình huống. Khi ghi tệp thất bại, lớp thứ ba bắt mọi ngoại lệ, ghi log “đã có lỗi” rồi trả về như thể công việc thành công. Người gọi phải tự nhớ quy ước của từng lớp, còn người vận hành không thể biết bản ghi lỗi nào là nguyên nhân gốc.

Những lựa chọn này không chỉ là sở thích viết mã. Chúng quyết định **người gọi hiểu hợp đồng ra sao, ai chịu trách nhiệm khôi phục sau lỗi, tài nguyên có được giải phóng không và hệ thống có đủ bằng chứng để điều tra hay không**.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở chương **Quy ước và nhất quán**, bài này trình bày cách thống nhất bốn nhóm quyết định thường xuất hiện trên ranh giới giữa các thành phần: **ngoại lệ, giá trị thiếu, vòng đời tài nguyên và ghi log**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **đầu vào sai**, **trường hợp không tìm thấy theo hợp đồng**, **từ chối nghiệp vụ** và **sự cố kỹ thuật** để chọn cách báo lỗi phù hợp.
- Định nghĩa nhất quán khi nào Java API chấp nhận `null`, trả về `Optional` hoặc collection rỗng, và khi nào cần từ chối dữ liệu ngay tại ranh giới.
- Xác định **ai tạo, ai sở hữu, ai đóng** một tài nguyên; dùng `try-with-resources` mà không vô tình đóng tài nguyên do người gọi sở hữu.
- Ghi log đúng mức, đúng ranh giới, đủ ngữ cảnh nhưng không lộ bí mật hoặc ghi trùng cùng một lỗi.
- Áp dụng các quy ước trong một ví dụ Java 17 có kiểm thử JUnit 5 và nhận diện những đánh đổi cần được nhóm thống nhất.

## 1. Quy ước là một phần của hợp đồng

Hợp đồng của một phương thức không chỉ gồm kiểu tham số và kiểu trả về. Người gọi cần biết **đầu vào hợp lệ là gì, trường hợp nào là kết quả bình thường, trường hợp nào là lỗi, tài nguyên nào sẽ còn mở sau lời gọi và điều gì được ghi nhận khi thất bại**.

Xem cùng một nhu cầu “tìm báo cáo theo mã”:

~~~java
Report findById(String id);                  // Có trả null không?
Optional<Report> findById(String id);        // Không tìm thấy là trường hợp bình thường?
Report requireById(String id);               // Không tìm thấy có ném ngoại lệ?
~~~

Ba chữ ký có thể hợp lý trong ba bối cảnh. Điều gây vấn đề là **không công bố rõ hợp đồng** hoặc đổi cách xử lý ngẫu nhiên giữa những thành phần tương tự.

| Điều cần thống nhất | Câu hỏi của người gọi | Hệ quả nếu mơ hồ |
| --- | --- | --- |
| Ngoại lệ và lỗi | Lỗi nào có thể xảy ra? Tôi xử lý hay cho lan lên? | Bắt sai loại lỗi, nuốt lỗi, trả thành công giả |
| `null` và vắng dữ liệu | `null` là hợp lệ, chưa có dữ liệu hay lập trình sai? | `NullPointerException` bất ngờ, nhầm “không có” với “thất bại” |
| Tài nguyên | Phương thức có đóng stream/connection của tôi không? | Rò rỉ, dùng tài nguyên đã đóng, tranh chấp vòng đời |
| Log | Ai ghi lỗi, ghi mức nào, có chứa dữ liệu nhạy cảm không? | Log trùng, thiếu ngữ cảnh, rò rỉ thông tin |

Một nhóm có thể có hơn một quy tắc nếu **ranh giới khác nhau**. Chẳng hạn, tầng HTTP ánh xạ ngoại lệ thành mã trạng thái, trong khi tầng nghiệp vụ có thể trả một kiểu kết quả. Nhất quán không đồng nghĩa **mọi phương thức đều phải dùng cùng một ngoại lệ hoặc cùng một kiểu trả về**. Nó có nghĩa các lựa chọn có lý do, có tài liệu và được áp dụng nhất quán trong phạm vi tương ứng.

## 2. Quy ước ngoại lệ: phân loại trước khi bắt

Trong Java, ngoại lệ có thể là **checked exception** (ví dụ `IOException`, thường phải khai báo hoặc xử lý) hoặc **unchecked exception** (ví dụ `IllegalArgumentException`, `IllegalStateException`). Đây là cơ chế ngôn ngữ, **không phải** sự phân loại hoàn chỉnh giữa lỗi người dùng, lỗi nghiệp vụ và lỗi hệ thống.

Một cách phân loại để thảo luận trong nhóm:

| Tình huống | Ý nghĩa | Cách thể hiện có thể phù hợp |
| --- | --- | --- |
| Tham số sai điều kiện cục bộ | Người gọi vi phạm tiền điều kiện | `IllegalArgumentException`; `NullPointerException` cho tham số bắt buộc bị `null` |
| Không tìm thấy dữ liệu trong thao tác tìm kiếm | Vắng dữ liệu là khả năng được dự kiến | `Optional.empty()` |
| Không tìm thấy dữ liệu mà thao tác yêu cầu bắt buộc phải có | Không thể hoàn tất thao tác | Ngoại lệ có tên rõ, ví dụ `ReportNotFoundException`, hoặc kiểu kết quả thất bại |
| Từ chối theo chính sách | Ví dụ hết chỗ, đơn hàng không được phép hủy | Kiểu kết quả/từ chối nghiệp vụ hoặc ngoại lệ theo hợp đồng |
| Không đọc/ghi được tệp, mạng lỗi | Hạ tầng không thực hiện được thao tác | `IOException` hoặc một ngoại lệ tầng ứng dụng có giữ nguyên nguyên nhân |
| Trạng thái đối tượng vi phạm điều kiện thao tác | Thao tác không hợp lệ với trạng thái hiện tại | `IllegalStateException` khi đúng ngữ nghĩa |
| Lỗi lập trình bất ngờ | Bất biến bị phá vỡ, sai giả định | Để lỗi được phát hiện và sửa, không đổi tùy tiện thành kết quả bình thường |

### Không dùng ngoại lệ làm đường đi “bình thường” khi có hợp đồng rõ hơn

Ví dụ, kho dữ liệu có thể dùng:

~~~java
public interface ReportRepository {
    Optional<Report> findById(String reportId);
}
~~~

Với phương thức **tìm**, không có báo cáo là một kết quả tự nhiên. Ngược lại, thao tác **xuất một báo cáo được yêu cầu** có thể coi “không tồn tại” là một thất bại và chuyển nó thành `ReportNotFoundException`. Đây là hai hợp đồng khác nhau, không mâu thuẫn.

Nếu hệ thống có nhiều lý do từ chối nghiệp vụ mà người dùng cần xử lý, kiểu kết quả `Success`/`Rejected(reason)` có thể rõ ràng hơn việc dùng ngoại lệ cho mọi lý do. Nhưng không nên dựng một hệ thống kiểu kết quả phức tạp chỉ để thay thế một lỗi đơn giản đã có quy ước ổn định.

### Bắt đúng nơi có thể xử lý

Một khối `catch` nên có mục đích rõ: **khôi phục**, **chuyển đổi thành hợp đồng của ranh giới**, **dọn dẹp có kiểm soát** hoặc **bổ sung ngữ cảnh mà không làm mất nguyên nhân**.

Không nên viết:

~~~java
try {
    exportReport();
} catch (Exception ignored) {
    // Giả vờ công việc đã hoàn tất.
}
~~~

Đoạn này có thể biến lỗi đọc dữ liệu, lỗi ghi tệp và lỗi lập trình thành một đường thành công giả, khiến dữ liệu bị thiếu nhưng hệ thống không báo.

Nếu cần chuyển ngoại lệ hạ tầng sang ngoại lệ của dịch vụ, hãy giữ **cause**:

~~~java
public final class ReportExportException extends RuntimeException {
    public ReportExportException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
try {
    writeReportFile();
} catch (IOException ex) {
    throw new ReportExportException("Report export failed", ex);
}
~~~

Hai đoạn trên minh họa **mẫu chuyển đổi**, không phải các hàm đầy đủ độc lập của ví dụ ở phần sau. Việc bọc `IOException` chỉ hợp lý nếu ranh giới mới có hợp đồng thống nhất dùng `ReportExportException`. Nếu tầng gọi vẫn xử lý `IOException` được, có thể khai báo `throws IOException` và để nó đi lên; bọc một cách máy móc chỉ làm mất phân biệt lỗi.

**Không bắt `Throwable` hoặc `Error` như một cơ chế xử lý nghiệp vụ thông thường.** Với `InterruptedException`, không được vô tình nuốt tín hiệu gián đoạn: nếu chuyển thành unchecked exception trong trường hợp phù hợp, cần khôi phục cờ bằng `Thread.currentThread().interrupt()` trước khi chuyển.

## 3. `null`: “không có” hay “không hợp lệ”?

Một giá trị `null` có thể mang nhiều cách hiểu: người gọi chưa cung cấp, kết quả chưa tồn tại, không áp dụng hoặc lỗi chưa được báo. **Cùng một giá trị nhưng nhiều ý nghĩa** khiến người đọc phải đoán.

Với một API Java mới, có thể cân nhắc quy ước:

1. **Tham số bắt buộc:** từ chối `null` ở ranh giới, thường với `Objects.requireNonNull`.
2. **Tìm kiếm có thể không có kết quả:** trả `Optional<T>` nếu sự vắng mặt là một phần tự nhiên của hợp đồng.
3. **Tập hợp không có phần tử:** thường trả collection rỗng, không trả `null`.
4. **Dữ liệu đầu vào ngoài hệ thống:** phân biệt *trường không có*, *trường có giá trị `null`* và *trường rỗng* theo hợp đồng JSON/API, không tự gộp ba trạng thái.
5. **API kế thừa đang cho phép `null`:** tôn trọng tương thích hiện có hoặc thay đổi bằng kế hoạch chuyển đổi; không “dọn” ngay mà không xem tác động.

Ví dụ:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public final class CustomerDirectory {
    private final CustomerRepository repository;

    public CustomerDirectory(CustomerRepository repository) {
        this.repository = Objects.requireNonNull(repository, "repository");
    }

    public Optional<Customer> find(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                "customerId must not be blank"
            );
        }
        return repository.findById(customerId);
    }

    public List<Customer> findActiveCustomers() {
        return List.copyOf(repository.findActive());
    }
}
~~~

Đây là **đoạn minh họa quy ước**: các kiểu `CustomerRepository` và `Customer` cần có định nghĩa của dự án. Phương thức `find` từ chối mã không hợp lệ, nhưng `Optional.empty()` có thể có nghĩa là mã hợp lệ về hình thức nhưng không tìm thấy. `findActiveCustomers` trả danh sách rỗng khi không có khách nào, đồng thời `List.copyOf` không chấp nhận phần tử `null` và tạo kết quả không thể sửa qua API.

### Dùng `Optional` đúng ngữ cảnh

`Optional<T>` phù hợp khi **kết quả trả về có thể vắng mặt theo hợp đồng**:

~~~java
Optional<Report> report = repository.findById("R-42");
report.ifPresent(this::displayReport);
~~~

Nhưng `Optional` không phải vật thay thế mặc định cho mọi tham số, trường dữ liệu hoặc collection. Một trường bắt buộc nên được khai báo và kiểm tra như trường bắt buộc; một tập hợp không có phần tử nên là danh sách rỗng nếu quy tắc nói vậy.

Không làm như sau nếu “không tìm thấy” và “database đang lỗi” là hai trạng thái cần phân biệt:

~~~java
try {
    return repository.findById(reportId);
} catch (Exception ex) {
    return Optional.empty(); // Sai: biến sự cố thành "không có".
}
~~~

Sự cố kỹ thuật phải được xử lý theo hợp đồng lỗi, không tự động biến thành “không tìm thấy”. Tương tự, không dùng `null` như một kết quả thay thế cho việc phải xử lý thất bại thật.

### Nullable annotations có ích nhưng không thay runtime checks

Tùy dự án, các annotation như `@Nullable` và `@NonNull` có thể giúp IDE hoặc công cụ phân tích phát hiện việc gọi sai. Tuy nhiên, chúng thuộc các thư viện và quy ước khác nhau, nên cần thống nhất **một bộ annotation được hỗ trợ** và cách công cụ hiểu chúng. Annotation không tự động kiểm tra mọi lời gọi lúc chạy. Ở ranh giới nhận dữ liệu từ HTTP hoặc nguồn không tin cậy, validation thực tế vẫn cần thiết.

## 4. Tài nguyên: ai tạo thì ai đóng?

Tài nguyên như file stream, kết nối mạng, reader/writer, transaction và executor có **vòng đời**, không chỉ có giá trị dữ liệu. Nếu mở ra mà không đóng, hệ thống có thể cạn file descriptor, giữ kết nối quá lâu hoặc không đẩy hết dữ liệu ra đích.

Một quy ước quan trọng:

**Thành phần tạo ra tài nguyên thường chịu trách nhiệm giải phóng nó, trừ khi hợp đồng thể hiện rõ quyền sở hữu được chuyển giao.**

| Tình huống | Ai thường chịu trách nhiệm đóng? | Điều cần công bố |
| --- | --- | --- |
| Phương thức tự gọi `Files.newBufferedWriter(...)` | Chính phương thức | Đóng/flush khi kết thúc, kể cả khi lỗi |
| Phương thức nhận `OutputStream` do người gọi truyền | Thường là người gọi | Callee có được đóng stream không? |
| Repository cấp một `Stream<T>` gắn với kết nối DB | Tùy hợp đồng repository | Stream có giữ connection mở và ai giải phóng |
| Một pool kết nối được tạo khi khởi động ứng dụng | Thành phần quản lý vòng đời ứng dụng | Khi nào pool bị đóng và ai được dùng chung |
| Một transaction phục vụ một thao tác nghiệp vụ | Ranh giới transaction | Điều kiện commit, rollback và đóng tài nguyên |

Điều cần tránh là **đóng tài nguyên do người gọi còn cần sử dụng**, hoặc trả về tài nguyên mở mà không nói ai phải đóng.

### Dùng `try-with-resources` cho tài nguyên mình sở hữu

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

void writeLines(Path target, List<String> lines) throws IOException {
    try (BufferedWriter writer = Files.newBufferedWriter(
            target, StandardCharsets.UTF_8)) {
        for (String line : lines) {
            writer.write(line);
            writer.newLine();
        }
    }
}
~~~

`BufferedWriter` thực thi `AutoCloseable`. Java gọi `close()` khi rời khối, kể cả lúc `write` ném ngoại lệ; việc đóng còn flush bộ đệm theo hợp đồng của writer. Nhưng **đóng tài nguyên có thể tự phát sinh lỗi** và file có thể đã được ghi một phần trước đó. `try-with-resources` bảo đảm thực hiện bước đóng theo cơ chế ngôn ngữ, không bảo đảm toàn bộ xuất tệp là một transaction nguyên tử.

Nếu thân khối và `close()` đều ném ngoại lệ, Java giữ lỗi chính trong ngoại lệ được ném ra và có thể gắn lỗi phát sinh lúc đóng vào **suppressed exceptions**. Khi điều tra một lỗi khó, `getSuppressed()` có thể cung cấp thông tin quan trọng; không nên thay thế toàn bộ lỗi bằng một thông điệp chung làm mất dấu vết.

### Không tự ý đóng tài nguyên nhận từ người gọi

~~~java
void writeMessage(OutputStream destination, String message)
        throws IOException {
    destination.write(message.getBytes(StandardCharsets.UTF_8));
    // Không tự đóng destination: người gọi còn sở hữu stream.
}
~~~

Nếu phương thức muốn nhận quyền sở hữu và tự đóng `destination`, hợp đồng phải ghi điều đó rõ ràng. Việc bao một `OutputStream` do người gọi sở hữu vào `BufferedWriter` rồi dùng `try-with-resources` sẽ **đóng luôn stream nền** khi wrapper được đóng, trừ khi dùng thiết kế chuyên biệt xử lý quyền sở hữu. Cần quyết định từ đầu, không dựa vào suy đoán.

## 5. Log: ghi sự kiện hữu ích, không ghi mọi thứ

Log phục vụ **chẩn đoán, quan sát và vận hành**. Nó không thay thế kết quả trả về hay cơ chế xử lý lỗi. Một dòng log hữu ích cần cho biết **điều gì xảy ra, ở đâu, với điều kiện nào đủ để điều tra** nhưng không tạo thêm rủi ro bảo mật.

Gợi ý quy ước mức độ log (có thể điều chỉnh theo hệ thống):

| Mức / loại | Khi nào phù hợp | Ví dụ |
| --- | --- | --- |
| DEBUG / FINE | Chi tiết kỹ thuật phục vụ điều tra, có thể bật/tắt | Quyết định nhánh xử lý, thời gian chờ, chỉ số không nhạy cảm |
| INFO | Sự kiện hoạt động bình thường đáng quan sát | Job xuất báo cáo hoàn tất, thay đổi trạng thái quan trọng |
| WARN / WARNING | Bất thường có thể xử lý nhưng đáng chú ý | Từ chối do vi phạm chính sách, retry nhiều lần (tùy lưu lượng) |
| ERROR / SEVERE | Thao tác quan trọng thất bại, cần xử lý hoặc cảnh báo | Không ghi được tệp, mất kết nối hệ thống bắt buộc |
| Audit record | Sự kiện có yêu cầu truy vết, kiểm soát truy cập và lưu giữ riêng | Ai phê duyệt thao tác nhạy cảm, quyết định quyền truy cập |

Tên mức phụ thuộc framework: `java.util.logging` có `FINE`, `INFO`, `WARNING`, `SEVERE`; SLF4J thường dùng `DEBUG`, `INFO`, `WARN`, `ERROR`. Không cần mọi dự án dùng cùng thư viện, nhưng **cần thống nhất ngữ nghĩa và cách thu thập trong chính dự án**.

### Ghi tại nơi chịu trách nhiệm xử lý

Giả sử repository ném `IOException`, service bắt và ghi một stack trace rồi ném lại, controller lại ghi stack trace lần nữa, còn tầng HTTP cũng ghi lỗi. **Một sự cố có thể xuất hiện thành ba hoặc bốn “lỗi”** trong hệ thống log, làm người trực khó xác định số sự cố thực.

Một nguyên tắc hữu ích là: **thành phần thấp cung cấp ngoại lệ có ý nghĩa và nguyên nhân đầy đủ; ranh giới chịu trách nhiệm xử lý hoặc báo lỗi ghi log với bối cảnh vận hành thích hợp**. Nếu một lớp trung gian log để bổ sung thông tin thật sự cần thiết, phải thống nhất tránh lặp cùng stack trace tại các tầng khác.

Không ghi mọi lỗi đầu vào như lỗi hệ thống nghiêm trọng. Một mã báo cáo không tồn tại có thể chỉ là kết quả nghiệp vụ thường gặp; ghi mức `SEVERE` cho mỗi request như vậy sẽ gây nhiễu cảnh báo. Ngược lại, một lỗi ghi tệp lặp lại có thể là sự cố đáng theo dõi.

### Ngữ cảnh có ích và dữ liệu không nên ghi

Một bản ghi vận hành thường có ích khi mang theo **mã sự kiện, correlation/trace ID, tên thao tác, thời gian, môi trường/phiên bản và loại lỗi** theo nhu cầu điều tra.

Tránh đưa thẳng vào log:

- Mật khẩu, access token, API key, cookie xác thực hoặc chuỗi kết nối chứa bí mật.
- Nội dung báo cáo, dữ liệu cá nhân hoặc dữ liệu thanh toán không cần thiết cho mục đích log.
- Toàn bộ request body hoặc header chỉ vì gặp lỗi.
- Chuỗi không tin cậy được dùng để tự dựng định dạng log mà không xử lý phù hợp, làm nội dung giả dòng hoặc giả trường log.

**Stack trace cũng có thể chứa đường dẫn, tham số hoặc thông điệp từ hệ thống ngoài.** Quyết định log toàn bộ exception cần đi cùng chính sách truy cập, che dữ liệu và thời hạn lưu giữ log.

Nếu cần audit cho hành vi nhạy cảm, dùng cơ chế audit được thiết kế riêng cho yêu cầu truy vết và chống sửa trái phép; log ứng dụng thông thường không tự đáp ứng đầy đủ mục tiêu audit.

## 6. Ví dụ xuyên suốt: xuất báo cáo ra tệp

Giả sử một ứng dụng có thao tác xuất báo cáo văn bản với **hợp đồng giả định**:

- `reportId` bắt buộc, không được `null` hoặc rỗng.
- Tìm báo cáo trong repository; trường hợp không có báo cáo là một kết quả có thể xảy ra của việc tìm.
- Khi yêu cầu **xuất** một báo cáo không tồn tại, thao tác bị từ chối bằng một ngoại lệ có tên rõ.
- Lỗi mở, ghi hoặc đóng tệp được báo cho tầng gọi như `IOException`.
- Dịch vụ tạo writer thì phải đóng writer đó, kể cả khi gặp lỗi.
- Dịch vụ không tự ghi log mỗi lần ném lỗi; ranh giới ứng dụng chịu trách nhiệm ghi log và ánh xạ phản hồi.

Các đoạn sau dùng **Java 17 trở lên**. Khi đưa vào dự án thực tế, các kiểu `public` cần đặt trong tệp Java phù hợp. Ví dụ chỉ tập trung vào bốn quy ước của bài; đường dẫn đầu ra giả định **đã được thành phần đáng tin cậy lựa chọn**, không lấy trực tiếp từ đường dẫn do người dùng ngoài gửi.

### 6.1. Giá trị báo cáo và repository

~~~java
import java.util.List;
import java.util.Objects;

public record Report(List<String> lines) {
    public Report {
        lines = List.copyOf(Objects.requireNonNull(lines, "lines"));
    }
}
~~~

`Report` chứa các dòng văn bản. `List.copyOf` tạo danh sách không thể sửa qua API và từ chối phần tử `null`. Vì phần tử là `String` (bất biến), người gọi không thể sửa nội dung dòng thông qua một tham chiếu được chia sẻ. Nếu bài toán thật có cấu trúc dòng phức tạp và có thể sửa, cần xem xét sao chép hoặc kiểu giá trị riêng.

~~~java
import java.util.Optional;

public interface ReportRepository {
    Optional<Report> findById(String reportId);
}
~~~

Repository trả `Optional.empty()` cho trường hợp **không tìm thấy** đã được dự kiến. Lỗi kết nối hoặc truy vấn hạ tầng phải theo hợp đồng lỗi riêng của adapter; không được tự động biến mọi lỗi thành `Optional.empty()`.

### 6.2. Ngoại lệ có ý nghĩa

~~~java
public final class ReportNotFoundException extends RuntimeException {
    public ReportNotFoundException() {
        super("Requested report does not exist");
    }
}
~~~

Ở ví dụ này, không gắn mã báo cáo vào thông điệp lỗi để tránh vô tình đẩy một định danh nhạy cảm sang các tầng log không kiểm soát. Nếu dự án cần mã phục vụ điều tra, nên quản lý theo chính sách dữ liệu và ngữ cảnh log, không mặc định cho mọi exception chứa toàn bộ input.

### 6.3. Dịch vụ quản lý tài nguyên và lỗi

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class ReportExportService {
    private final ReportRepository repository;

    public ReportExportService(ReportRepository repository) {
        this.repository = Objects.requireNonNull(repository, "repository");
    }

    public void exportToFile(String reportId, Path destination)
            throws IOException {
        if (reportId == null || reportId.isBlank()) {
            throw new IllegalArgumentException("reportId must not be blank");
        }
        Objects.requireNonNull(destination, "destination");

        Report report = repository.findById(reportId)
            .orElseThrow(ReportNotFoundException::new);

        try (BufferedWriter writer = Files.newBufferedWriter(
                destination, StandardCharsets.UTF_8)) {
            for (String line : report.lines()) {
                writer.write(line);
                writer.newLine();
            }
        }
    }
}
~~~

Những quyết định có thể đọc ngay từ mã:

1. **Tiền điều kiện:** mã trống bị từ chối trước khi tìm repository; đường dẫn `null` bị từ chối trước khi tạo writer.
2. **Vắng dữ liệu:** repository có thể trả `Optional.empty()`, còn tác vụ xuất chuyển nó thành `ReportNotFoundException` vì không thể hoàn tất thao tác.
3. **I/O:** phương thức công bố `throws IOException`, không biến lỗi ghi tệp thành thành công giả.
4. **Quyền sở hữu:** chính phương thức tạo writer và đóng bằng `try-with-resources`.
5. **Log:** service không ghi cùng một ngoại lệ ở nhiều chỗ; tầng xử lý request/job có thể bổ sung ngữ cảnh và ghi nhận theo quy ước vận hành.

**Giới hạn của ví dụ:** `Files.newBufferedWriter` với tùy chọn mặc định có thể tạo tệp mới hoặc ghi đè nội dung tệp đang tồn tại. Nếu ghi lỗi giữa chừng, tệp đích có thể chứa một phần dữ liệu. Với yêu cầu xuất tệp phải **nguyên tử**, cần thiết kế thêm bước ghi tệp tạm, đồng bộ dữ liệu nếu cần, di chuyển tệp theo khả năng hỗ trợ của hệ thống tệp và quy tắc khôi phục. Không được hiểu `try-with-resources` là bảo đảm giao dịch cho filesystem.

Đường dẫn do client gửi cũng có thể tạo rủi ro truy cập sai phạm vi. Ví dụ trên giả định `destination` đã được chọn ở tầng đáng tin cậy; hệ thống thật phải kiểm tra quyền ghi, vùng lưu trữ cho phép và chính sách ghi đè.

## 7. Kiểm thử hợp đồng với JUnit 5

Một bộ test nên kiểm tra **đầu vào hợp lệ, đầu vào sai, dữ liệu không tồn tại và lỗi I/O**. Ví dụ JUnit Jupiter dùng `@TempDir` để mỗi test có thư mục riêng:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ReportExportServiceTest {
    @TempDir
    Path tempDir;

    private ReportRepository repository() {
        return id -> "R-1".equals(id)
            ? Optional.of(new Report(List.of("Report", "Total: 200")))
            : Optional.empty();
    }

    @Test
    void exportsReportWhenPresent() throws IOException {
        ReportExportService service =
            new ReportExportService(repository());
        Path file = tempDir.resolve("report.txt");

        service.exportToFile("R-1", file);

        assertEquals(
            List.of("Report", "Total: 200"),
            Files.readAllLines(file)
        );
    }

    @Test
    void missingReportDoesNotCreateOutputFile() {
        ReportExportService service =
            new ReportExportService(repository());
        Path file = tempDir.resolve("missing.txt");

        assertThrows(
            ReportNotFoundException.class,
            () -> service.exportToFile("R-404", file)
        );
        assertFalse(Files.exists(file));
    }

    @Test
    void rejectsInvalidArguments() {
        ReportExportService service =
            new ReportExportService(repository());
        Path file = tempDir.resolve("report.txt");

        assertThrows(
            IllegalArgumentException.class,
            () -> service.exportToFile(" ", file)
        );
        assertThrows(
            NullPointerException.class,
            () -> service.exportToFile("R-1", null)
        );
    }

    @Test
    void propagatesFileSystemFailure() {
        ReportExportService service =
            new ReportExportService(repository());
        Path file = tempDir.resolve("absent-parent").resolve("report.txt");

        assertThrows(
            IOException.class,
            () -> service.exportToFile("R-1", file)
        );
    }
}
~~~

Các expected values xuất phát từ **hợp đồng đã mô tả**, không tự tính bằng đúng thuật toán của phương thức xuất. `@TempDir` giúp giảm rủi ro test cùng dùng một tệp cố định. Test cố ý chọn đường dẫn có thư mục cha không tồn tại để kiểm tra lỗi I/O được lan truyền; đây là trường hợp cụ thể, không chứng minh mọi loại lỗi ghi tệp đều được kiểm tra.

Test không cần gọi `close()` thủ công: kiểm tra việc dùng `try-with-resources` là phần review mã, còn integration test có thể kiểm chứng hành vi khi hệ thống tệp có sự cố và tệp ghi dở. Với kết nối database hoặc tài nguyên hạ tầng khác, cần các kiểm thử ở ranh giới tương ứng; fake repository không chứng minh adapter thật đóng connection đúng.

## 8. Đưa log về ranh giới xử lý, không làm mất lỗi

Giả sử job là một ranh giới vận hành có `traceId` đã được tạo từ nguồn đáng tin cậy. Job handler có thể lựa chọn mức log và chuyển thất bại theo chính sách của ứng dụng.

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class ExportJobHandler {
    private static final Logger LOG =
        Logger.getLogger(ExportJobHandler.class.getName());

    private final ReportExportService exportService;

    public ExportJobHandler(ReportExportService exportService) {
        this.exportService = java.util.Objects.requireNonNull(exportService);
    }

    public void run(String reportId, Path destination, String traceId)
            throws IOException {
        try {
            exportService.exportToFile(reportId, destination);
            LOG.log(Level.INFO, "export_completed traceId={0}", traceId);
        } catch (ReportNotFoundException ex) {
            LOG.log(Level.INFO, "export_not_found traceId={0}", traceId);
            throw ex;
        } catch (IOException ex) {
            LOG.log(
                Level.SEVERE,
                "export_io_failed traceId=" + traceId,
                ex
            );
            throw ex;
        }
    }
}
~~~

Ở đây, handler ghi một bản ghi cho từng kết quả xử lý có ý nghĩa, còn service không ghi log trùng. Nếu handler ném tiếp ngoại lệ lên scheduler/controller và tầng trên cũng có quy ước ghi stack trace, nhóm cần quyết định **nơi nào là điểm ghi lỗi cuối cùng**. Đoạn mã này giả định `traceId` đã được chuẩn hóa và an toàn để đưa vào log; trong hệ thống thật không nên tin giá trị chứa ký tự điều khiển hoặc nội dung do người dùng tự chọn.

Tương tự, việc truyền `ex` cho `LOG.log` có thể khiến message/cause/stack trace được ghi. Phải đánh giá chính sách bảo mật log và cách exception của adapter mang dữ liệu nhạy cảm trước khi áp dụng trực tiếp ở hệ thống thật.

### Ghi log không phải xử lý lỗi

Một bản ghi `SEVERE` không làm thao tác thất bại được phục hồi, không rollback dữ liệu, không retry và không thông báo người dùng một cách có kiểm soát. Những hành vi này cần được quy định **riêng**.

Với job có thể thử lại, handler hoặc scheduler phải biết lỗi nào được phép retry, có khả năng tạo tệp trùng/ghi đè không và cách xác định một thao tác đã hoàn tất. Nếu retry không có idempotency hoặc cơ chế kiểm tra trạng thái, cùng một lỗi có thể tạo tác dụng phụ nhiều lần. Quy ước logging tốt giúp điều tra nhưng không thay thế thiết kế retry an toàn.

## 9. Các quy ước phải thống nhất với nhau

Bốn chủ đề không thể tách rời:

~~~text
          Đầu vào & trạng thái
                  |
          null / Optional / validate
                  |
             Thao tác nghiệp vụ
                  |
          +-------+--------+
          |                |
       Thành công       Thất bại
          |                |
     Đóng tài nguyên   Giữ nguyên cause
          |                |
          +-------+--------+
                  |
          Ranh giới xử lý
          ghi log / phản hồi
~~~

Một thiết kế không nhất quán thường có những tổ hợp như:

- Trả `null` khi database timeout → người gọi tưởng “không có dữ liệu”.
- Ghi log lỗi nhưng trả success → monitoring ghi thất bại trong khi API báo thành công.
- Bắt ngoại lệ, thoát sớm mà không đóng stream → tài nguyên rò rỉ đúng khi hệ thống đang gặp lỗi.
- Đóng stream do người gọi sở hữu → một thao tác “tiện lợi” gây lỗi cho phần xử lý tiếp theo.
- Ném ngoại lệ không có cause, nhưng log ở từng tầng → vừa mất bằng chứng gốc vừa tạo nhiều bản ghi trùng.

Chất lượng đến từ **hợp đồng đầu vào, lỗi, tài nguyên và quan sát cùng hướng về một ý nghĩa**. Khi người bảo trì nhìn thấy `Optional.empty()`, họ phải biết đó là dữ liệu không tồn tại theo hợp đồng; khi thấy `IOException`, họ phải biết thao tác I/O không hoàn tất; khi thấy log `export_io_failed`, họ phải truy vết được một lần xử lý thật sự bị lỗi.

## 10. Chọn quy ước phù hợp theo ranh giới

Một số quyết định nên được nhóm ghi ngắn gọn, không nhất thiết thành tài liệu dài:

| Ranh giới | Quy ước có thể chọn | Điểm cần xem lại khi thay đổi |
| --- | --- | --- |
| API Java công khai | `null` bắt buộc bị từ chối; absence dùng `Optional` khi phù hợp | Khả năng tương thích của người gọi hiện có |
| Domain/service | Kết quả nghiệp vụ khác với sự cố hạ tầng | Định nghĩa lại trạng thái, lỗi và cơ chế retry |
| Repository | “Không tìm thấy” khác “không đọc được dữ liệu” | Adapter thật có giữ đúng phân biệt không |
| I/O adapter | Tài nguyên được tạo tại adapter và đóng đúng phạm vi | Streaming, pooling, transaction |
| HTTP/controller | Ngoại lệ được ánh xạ thành mã lỗi và nội dung công khai | Tránh rò rỉ thông tin, ổn định lỗi API |
| Job/scheduler | Lỗi nào retry được, lỗi nào cần dừng/cảnh báo | Idempotency, dữ liệu ghi dở, giới hạn retry |
| Logging/observability | Mã sự kiện, trace ID, mức log và chính sách che dữ liệu | Dữ liệu nhạy cảm, retention, cảnh báo trùng |

**Đừng thay đổi quy ước chỉ để làm mã “đẹp hơn”** nếu điều đó phá vỡ hợp đồng với client. Chuyển một API đang trả `null` sang `Optional<T>` là thay đổi chữ ký; đổi từ kết quả `false` sang ngoại lệ là thay đổi hành vi; tự đóng một `OutputStream` trước đây để mở là thay đổi vòng đời tài nguyên. Cần review khả năng tương thích, cập nhật tài liệu và kiểm thử hồi quy.

## 11. Checklist khi review mã

1. **Đầu vào:** `null` có được chấp nhận không? Chuỗi trống, danh sách trống và đối tượng thiếu dữ liệu có ý nghĩa khác nhau không?
2. **Kết quả:** `Optional.empty()` đại diện cho thiếu dữ liệu hay đang che một lỗi thật? Collection rỗng có phù hợp không?
3. **Ngoại lệ:** Phân biệt đầu vào sai, từ chối nghiệp vụ và lỗi hạ tầng được chưa? Có ngoại lệ bị bắt quá rộng hoặc bị nuốt không?
4. **Nguyên nhân lỗi:** Khi bọc ngoại lệ, `cause` và thông tin chẩn đoán cần thiết còn nguyên không? Lỗi gián đoạn luồng có được xử lý đúng không?
5. **Quyền sở hữu:** Ai mở và ai đóng stream/connection/executor? Có đóng nhầm tài nguyên của caller không?
6. **Đường thất bại:** Khi lỗi giữa chừng, tài nguyên có được đóng? Có tệp/transaction/dữ liệu dở dang cần khôi phục không?
7. **Log:** Đúng tầng nào ghi log? Có log trùng hoặc ghi mọi trường hợp từ chối là lỗi nghiêm trọng không?
8. **Bảo mật log:** Có token, dữ liệu cá nhân, nội dung tệp, đường dẫn nhạy cảm hoặc input chưa được kiểm soát không?
9. **Tính nhất quán:** Các service tương đương có cùng cách mô tả lỗi, vắng dữ liệu và vòng đời không? Nếu khác, có lý do được công bố không?
10. **Kiểm chứng:** Có test cho giá trị thiếu, tham số sai, kết quả bình thường và lỗi tài nguyên phù hợp không? Adapter thật có được kiểm thử tích hợp khi cần không?

Một quy ước tốt giúp người đọc dự đoán **điều gì xảy ra mà không cần mở toàn bộ mã nguồn của từng tầng**. Đây là lợi ích lớn của sự nhất quán trong dự án nhiều người phát triển.

## 12. Bài tập thực hành

Xét phương thức đọc dòng đầu của một tệp văn bản:

~~~java
String readFirstLine(Path path) {
    try {
        BufferedReader reader = Files.newBufferedReader(path);
        return reader.readLine();
    } catch (Exception ex) {
        System.out.println("FAILED: " + ex.getMessage());
        return null;
    }
}
~~~

Giả sử hợp đồng mong muốn:

- `path` không được `null`.
- **Tệp rỗng** là kết quả bình thường và được biểu diễn như “không có dòng đầu”.
- **Không mở hoặc đọc được tệp** là lỗi I/O cần báo cho caller.
- Phương thức sở hữu reader mà nó tạo ra và phải đóng reader.
- Phương thức tiện ích này không tự quyết định chính sách log của ứng dụng.

**Câu hỏi A.** Đoạn mã hiện tại có ít nhất bốn vấn đề gì về quy ước?

**Câu hỏi B.** Hãy thiết kế lại chữ ký để phân biệt “tệp rỗng” và “lỗi I/O” mà không trả `null`.

**Câu hỏi C.** Nên ghi log tại đâu nếu chức năng được gọi từ một HTTP endpoint? Vì sao?

### Gợi ý đáp án

**A.** Reader không được đóng; `catch (Exception)` quá rộng; `null` vừa có thể nghĩa “tệp rỗng” vừa “lỗi”; dùng `System.out.println` không có ngữ cảnh/kiểm soát bảo mật; `path == null` bị gộp vào đường lỗi chung; người gọi không biết khi nào cần thử lại.

**B.** Có thể dùng:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;
import java.util.Optional;

public static Optional<String> readFirstLine(Path path) throws IOException {
    Objects.requireNonNull(path, "path");

    try (BufferedReader reader =
            Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return Optional.ofNullable(reader.readLine());
    }
}
~~~

`BufferedReader.readLine()` trả `null` khi tới cuối tệp mà không đọc được dòng nào; chuyển kết quả thành `Optional.empty()` mô tả rõ trường hợp tệp rỗng. Lỗi mở/đọc/đóng được báo qua `IOException`, còn `try-with-resources` xử lý việc đóng reader. Với tệp chứa dòng đầu tiên rỗng, phương thức trả `Optional.of("")` — **khác** với tệp không có dòng nào. Sự phân biệt này có ích nếu hợp đồng quan tâm tới nội dung dòng.

**C.** Lớp tiện ích giữ nguyên `IOException`. HTTP handler hoặc lớp xử lý ngoại lệ được quy định trong ứng dụng nên ánh xạ lỗi thành phản hồi phù hợp và ghi log với trace ID/mã lỗi sau khi lọc thông tin nhạy cảm. Nếu tiện ích, service và handler đều log cùng stack trace, một lần lỗi có thể bị tính thành nhiều sự cố.

## Ghi nhớ

**Quy ước ngoại lệ, null, tài nguyên và log** giúp các thành phần giao tiếp qua những hợp đồng có thể dự đoán. Ngoại lệ nói rõ vì sao thao tác không hoàn tất; `Optional` hoặc collection rỗng mô tả sự vắng mặt khi đó là kết quả bình thường; quyền sở hữu tài nguyên quyết định ai phải đóng và khôi phục; log cung cấp bằng chứng điều tra ở đúng ranh giới.

Không có một lựa chọn bắt buộc cho mọi dự án. Điều quan trọng là **phân biệt đúng các tình huống**, công bố **hợp đồng phù hợp với trách nhiệm**, thực thi **nhất quán**, và có kiểm thử cho các đường lỗi. Khi các quy ước bổ trợ lẫn nhau, mã nguồn dễ đọc hơn, giảm lỗi sử dụng sai và dễ thay đổi mà không làm người gọi phải đoán.
