# Ngoại lệ không tự hoàn tác file, dữ liệu hay tác động bên ngoài

## 1. Hiểu đúng điều mà exception thực hiện

Trong Java, **ném ngoại lệ (`throw`) làm thay đổi luồng điều khiển**, không tự động quay ngược các thay đổi đã xảy ra. JVM tìm `catch` phù hợp bằng cách tháo stack; các khối `finally` liên quan được thực thi theo quy tắc ngôn ngữ, và `try-with-resources` cố đóng tài nguyên được quản lý. Không có bước mặc định nào của Java thực hiện “undo” cho các phép ghi file, thay đổi đối tượng, lệnh SQL đã commit, HTTP request, email hoặc thông điệp đã gửi.

Giả sử một thao tác gồm:

1. Ghi thêm nội dung vào file.
2. Gửi lệnh ghi đơn hàng đến cơ sở dữ liệu.
3. Gọi dịch vụ thanh toán bên ngoài.
4. Ném `IllegalStateException` do bước cuối kiểm tra thất bại.

Exception ở bước 4 **không chứng minh** rằng bước 1–3 đã được hoàn tác. Muốn biết trạng thái thực sau thất bại, phải xét riêng từng hiệu ứng: ghi file đã tới đâu, SQL đang trong transaction nào, bên thanh toán đã nhận/xử lý yêu cầu chưa và chương trình đã làm gì để khôi phục.

Bài này tập trung vào bảo toàn trạng thái khi có exception: phân biệt **giải phóng tài nguyên**, **khôi phục thay đổi**, **tính nguyên tử**, **giao dịch**, và **bù trừ tác động ngoài hệ thống**; thực hành những mẫu phù hợp trong Java 17+.

## 2. Phân biệt năm hành động rất dễ bị nhầm

| Hành động | Mục đích | Tự đảo ngược nội dung đã thay đổi? |
| --- | --- | --- |
| `throw` một exception | Báo rằng luồng xử lý bình thường không thể tiếp tục | **Không** |
| `catch` exception | Cho caller cơ hội xử lý, quyết định tiếp tục hay lan truyền | **Không**, trừ khi mã trong `catch` chủ động khôi phục |
| `finally` | Thực thi tác vụ dọn dẹp khi rời khối `try` trong các tình huống thông thường | **Không**; muốn hoàn tác phải viết logic thích hợp |
| `try-with-resources` | Gọi `close()` đối với tài nguyên khai báo trong ngoặc `try` | **Không mặc định**; `close()` không đồng nghĩa rollback |
| `rollback()` của transaction | Yêu cầu hệ thống giao dịch huỷ các thay đổi chưa commit thuộc transaction đó | **Có trong phạm vi transaction được hỗ trợ**, không bao trùm file, email, HTTP hay giao dịch đã commit |

Ví dụ `FileOutputStream.close()` giải phóng tài nguyên file, nhưng không làm biến mất bytes đã được ghi. Tương tự, `BufferedWriter.close()` có thể flush phần dữ liệu đang đệm; thao tác đóng thậm chí có thể khiến dữ liệu được ghi ra trong quá trình xử lý exception. Ngược lại, kết nối JDBC đóng lại **không phải hợp đồng rollback có thể tin tưởng cho mọi trường hợp**: quản lý transaction cần được thực hiện tường minh hoặc giao cho transaction manager.

Ngoại lệ có thể xuất hiện **sau khi một hiệu ứng thành công**; vì thế “phương thức ném exception” và “phương thức không làm thay đổi gì” là hai khẳng định hoàn toàn khác nhau.

## 3. Trạng thái trong bộ nhớ cũng không tự trở lại như cũ

Java không lưu bản sao đối tượng trước khi đi vào `try`. Nếu đã thay đổi một `List`, `Map`, field của object hoặc một đối tượng chia sẻ giữa các thread, ném exception không hủy phép gán trước đó.

~~~java
import java.util.ArrayList;
import java.util.List;

class MemoryStateExample {
    public static void main(String[] args) {
        List<String> steps = new ArrayList<>();
        steps.add("created");

        try {
            steps.add("charged");
            throw new IllegalStateException("report failed");
        } catch (IllegalStateException e) {
            System.out.println(e.getMessage());
        }

        System.out.println(steps);
    }
}
~~~

Lưu thành `MemoryStateExample.java` rồi chạy:

~~~bash
javac --release 17 MemoryStateExample.java
java MemoryStateExample
~~~

Stdout:

~~~text
report failed
[created, charged]
~~~

Đây là ví dụ Java 17 độc lập: phép `steps.add("charged")` tồn tại sau `catch`. `finally`, nếu được thêm, cũng sẽ không tự xóa phần tử này.

Khi cần cam kết **hoặc thay đổi toàn bộ hoặc giữ nguyên trạng thái cũ**, cách thường rõ hơn là kiểm tra trước, xây dựng kết quả mới trong biến cục bộ rồi cập nhật trạng thái dùng chung tại một điểm cuối có kiểm soát. Ví dụ tính một `List.copyOf(...)` hoàn chỉnh trước khi thay tham chiếu state. Cần nhớ rằng phép gán tham chiếu đơn lẻ không biến toàn bộ chuỗi hiệu ứng đa tài nguyên thành một transaction, và xử lý concurrency vẫn cần cơ chế đồng bộ phù hợp.

## 4. Ghi file: dữ liệu có thể đã thay đổi trước khi exception được ném

### 4.1. Ví dụ Java 17 chạy độc lập: ghi dở và ghi qua file tạm

Ví dụ sau cố tình ném exception **sau khi ghi thêm vào file** để chứng minh dữ liệu không tự hoàn tác. Sau đó nó tạo file ứng viên riêng và cố tình từ chối trước bước xuất bản, để cho thấy thao tác trên **file đích** chưa xảy ra. Cuối cùng nó minh họa lần thay thế bình thường.

Lưu thành **`ExceptionSideEffectDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;

public class ExceptionSideEffectDemo {
    static void appendThenFail(Path file) throws IOException {
        Files.writeString(file, "|append", StandardCharsets.UTF_8,
                StandardOpenOption.APPEND);
        throw new IllegalStateException("failure after append");
    }

    static void stagedReplace(Path target, String next, boolean reject)
            throws IOException {
        Path candidate = Files.createTempFile(
                target.getParent(), "candidate-", ".txt");
        try {
            Files.writeString(candidate, next, StandardCharsets.UTF_8);
            if (reject) {
                throw new IllegalArgumentException("rejected before publish");
            }
            Files.move(candidate, target, StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(candidate);
        }
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("exception-state-");
        Path file = dir.resolve("data.txt");
        try {
            Files.writeString(file, "initial", StandardCharsets.UTF_8);
            try {
                appendThenFail(file);
            } catch (IllegalStateException e) {
                System.out.println("1. " + e.getMessage());
            }
            System.out.println("2. " + Files.readString(file));

            try {
                stagedReplace(file, "candidate", true);
            } catch (IllegalArgumentException e) {
                System.out.println("3. " + e.getMessage());
            }
            System.out.println("4. " + Files.readString(file));

            stagedReplace(file, "published", false);
            System.out.println("5. " + Files.readString(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file với JDK 17 trở lên:

~~~bash
javac --release 17 ExceptionSideEffectDemo.java
java ExceptionSideEffectDemo
~~~

Stdout khi các thao tác file được hệ điều hành cho phép:

~~~text
1. failure after append
2. initial|append
3. rejected before publish
4. initial|append
5. published
~~~

**Vì sao có kết quả như vậy?**

- Ban đầu file `data.txt` chứa `initial`.
- `appendThenFail` thực hiện `Files.writeString(..., APPEND)` và sau đó ném `IllegalStateException`. Sau khi `catch` nhận lỗi, dữ liệu đã trở thành `initial|append`, chứng tỏ exception không đảo ngược việc append.
- `stagedReplace(..., true)` ghi dữ liệu mới vào một file tạm **khác**; nó ném trước `Files.move`. `finally` xóa file tạm, còn file đích vẫn chứa `initial|append`.
- `stagedReplace(..., false)` đi tới `Files.move` để thay file đích bằng nội dung `published`. Đây chỉ là minh họa đường thành công; lệnh `Files.move` có `REPLACE_EXISTING` **không bảo đảm thay thế nguyên tử trong mọi tình huống**, vì chưa dùng `ATOMIC_MOVE`.

Ví dụ cố ý dùng thư mục tạm và xóa trong `finally` để không để lại dữ liệu sau khi chạy thành công. Ở môi trường mà việc tạo, ghi, chuyển hoặc xóa file bị từ chối, chương trình có thể ném `IOException` và không in được toàn bộ stdout. Những exception từ việc dọn dẹp cũng cần được cân nhắc riêng trong mã production.

### 4.2. Tại sao ngay cả phương thức ghi bị lỗi vẫn không chứng minh file còn nguyên?

Ghi file không nhất thiết là một thao tác “tất cả hoặc không có gì”. Một vòng lặp ghi nhiều khối có thể ghi thành công vài khối rồi gặp `IOException`; nội dung file đích có thể đã thay đổi. `Files.writeString` hoặc `OutputStream.write` không cung cấp một hợp đồng transaction cho nhiều thao tác ghi liên tiếp. Buffer trong bộ nhớ, page cache của hệ điều hành và dữ liệu bền vững trên thiết bị lưu trữ còn là những tầng khác nhau.

Ví dụ sai:

~~~java
// Anti-pattern: ghi trực tiếp file đích rồi hy vọng exception tự khôi phục.
Files.writeString(target, generatedText);
runValidationThatMayThrow();
~~~

Đây là đoạn minh họa giả định `target`, `generatedText` và hàm validation đã tồn tại. Nếu validation ném exception, file có thể đã bị thay nội dung.

Cần phân biệt:
- **Trước bước công bố:** tạo kết quả mới trong file tạm, kiểm tra tính hợp lệ, checksum/độ dài hoặc định dạng, rồi mới xét công bố.
- **Bước công bố:** nếu yêu cầu thay thế nguyên tử và file system hỗ trợ, có thể dùng `Files.move(candidate, target, ATOMIC_MOVE)`; bắt `AtomicMoveNotSupportedException` để áp dụng chính sách rõ ràng.
- **Sau công bố:** nếu đã công bố file mới rồi một thao tác khác thất bại, không thể cho rằng file đã quay về bản cũ.

Trong JDK, `ATOMIC_MOVE` là tùy chọn yêu cầu phép move như **một thao tác nguyên tử của file system**, nhưng nhà cung cấp có thể không hỗ trợ và ném `AtomicMoveNotSupportedException`. Khi chỉ định `ATOMIC_MOVE`, hành vi thay thế đích đang tồn tại phụ thuộc implementation và các tùy chọn khác bị bỏ qua theo hợp đồng API; không hứa thay thế đích trên mọi file system. Không âm thầm fallback sang non-atomic move nếu tính nguyên tử là yêu cầu bắt buộc. Thực thi an toàn có thể phải fail-fast hoặc thiết kế một chiến lược phục hồi riêng theo môi trường triển khai.

Ngay cả atomic rename/move cũng **không đồng nghĩa bảo đảm dữ liệu tồn tại sau mất điện**. Cần đánh giá việc flush dữ liệu, `FileChannel.force`, metadata thư mục và bảo đảm của file system/hệ điều hành nếu tính bền vững trước sự cố máy là yêu cầu. Đặc biệt, ghi hai file riêng rồi move từng file không tạo một transaction nguyên tử cho cả hai file.

### 4.3. Phục hồi bằng file tạm có những giới hạn nào?

Thứ tự điển hình:

~~~text
Đọc phiên bản hiện tại
    -> tạo phiên bản mới trong file tạm
    -> xác thực phiên bản mới
    -> công bố phiên bản mới
    -> dọn file tạm/ghi nhận kết quả
~~~

Chiến lược này giới hạn thời gian file đích chịu tác động, giúp lỗi phát sinh **trước khi công bố** không phá dữ liệu đích. Tuy nhiên cần xử lý:
- Lỗi ngay lúc công bố, đặc biệt khi file system không hỗ trợ atomic replacement.
- Tiến trình chết khiến file tạm chưa được xóa; nên có cơ chế dọn file mồ côi an toàn.
- Nhiều writer cạnh tranh: không để phiên bản cũ ghi đè phiên bản mới nếu không được phép; cân nhắc khóa, version/checksum hoặc giao thức đồng bộ phù hợp.
- Quyền truy cập, ownership, attributes và symlink: thay file có thể ảnh hưởng metadata; đừng giả định mọi thuộc tính giữ nguyên.
- Lỗi **sau công bố**: file mới vẫn có thể tồn tại dù caller nhận exception từ bước dọn dẹp hoặc thao tác tiếp theo.

Vì vậy cần định nghĩa rõ **điểm công bố/commit** để có thể trả lời: “Nếu lỗi xảy ra trước và sau điểm này thì trạng thái ra sao?”.

## 5. `finally` và try-with-resources chỉ giải quyết một phần bài toán

`finally` rất phù hợp cho việc thả khóa, dọn file tạm, reset một trạng thái tạm, hoặc giải phóng tài nguyên. Nhưng nó không thể tự suy ra phép hoàn tác hợp lệ. Nếu mã trong `try` đã gửi email, gọi `close()` trên client cũng không thu hồi email.

Ví dụ:

~~~java
try (var writer = Files.newBufferedWriter(path)) {
    writer.write("updated");
    throw new IllegalStateException("later step failed");
}
~~~

Đây là đoạn minh họa không độc lập (giả định `path` đã khai báo và được phép ghi). Khi rời `try` do exception, `writer.close()` được gọi; nó không có nghĩa file trở lại như trước. Với `newBufferedWriter(path)` dùng tùy chọn mặc định, file có thể đã được tạo hoặc bị truncate ngay khi mở. Việc close thường flush dữ liệu đang đệm; không phải rollback.

**Nếu đóng tài nguyên cũng phát sinh lỗi**, try-with-resources áp dụng quy tắc ngoại lệ bị ức chế (*suppressed exceptions*): khi body đã ném exception và `close()` cũng ném, lỗi đóng được gắn vào lỗi chính qua `getSuppressed()`. Với logic `finally` viết thủ công, exception trong `finally` có thể che mất exception ban đầu nếu không xử lý cẩn thận.

Do đó cần tách hai mục tiêu:
- **Resource safety:** tài nguyên được đóng, file tạm được dọn, lock được thả.
- **State/transaction safety:** thay đổi nghiệp vụ có được commit đầy đủ, rollback có thể thực hiện và giới hạn phạm vi phục hồi là gì?

Một chương trình có thể làm tốt resource safety nhưng thất bại về state safety, hoặc ngược lại.

## 6. Database: chỉ transaction đúng phạm vi mới có thể rollback

Với JDBC, mỗi `Connection` mới thường ở chế độ `autoCommit = true`. Trong chế độ này, từng câu lệnh SQL hoàn tất theo cơ chế commit của JDBC/database; một exception ném **sau câu lệnh đã commit** không tự hủy thay đổi. Để nhiều câu lệnh tham gia cùng transaction, cần quản lý `autoCommit(false)`, `commit()` và `rollback()` thích hợp, hoặc sử dụng transaction manager/framework được cấu hình đúng.

Sơ đồ:

~~~text
BEGIN transaction
    UPDATE accounts SET balance = ... WHERE ...
    INSERT INTO ledger (...)
    kiểm tra invariant cuối
    +-- thành công ------> COMMIT
    +-- lỗi trước commit -> ROLLBACK
~~~

Đây là sơ đồ khái niệm, không phải mã SQL có thể chạy nguyên trạng. Khi database hỗ trợ transaction phù hợp và các lệnh tham gia đúng transaction, rollback có thể hủy thay đổi **chưa commit** của các lệnh đó. Nếu đã `commit()` thành công, `rollback()` sau đó không thu hồi commit trước.

Một mẫu JDBC cần bảo vệ nhiều điểm:
1. Chỉ tắt `autoCommit` khi thực sự sở hữu phạm vi transaction; tránh vô tình can thiệp connection do pool/framework quản lý.
2. Thực thi các statement liên quan qua **cùng transaction phù hợp**; không giả định nhiều connection tự tham gia transaction chung.
3. `commit()` sau khi tất cả điều kiện cần cho giao dịch nội bộ hoàn tất.
4. Nếu thất bại trước commit, gọi `rollback()` và cố giữ exception ban đầu; nếu rollback cũng lỗi thì ghi nhận nó như lỗi phụ, không âm thầm nuốt.
5. Phục hồi/đóng connection theo hợp đồng thư viện hoặc trả về pool; tránh để trạng thái transaction bị rò rỉ cho request kế tiếp.

Cần thêm hai ngoại lệ quan trọng đối với suy luận:
- **Không phải mọi storage/DDL/engine đều rollback giống nhau.** Cơ chế transaction và khả năng rollback tùy database, loại lệnh, engine và mức isolation. Không đưa một lệnh bên ngoài phạm vi transaction rồi khẳng định nó sẽ được hoàn tác.
- **`commit()` ném lỗi không phải lúc nào cũng chứng minh transaction chưa commit.** Ví dụ mất kết nối đúng lúc nhận phản hồi có thể tạo trạng thái kết quả không chắc chắn; cần truy vấn lại theo mã giao dịch/định danh có tính idempotent hoặc theo quy trình phục hồi thiết kế trước.

### 6.1. Bẫy “đã commit rồi mới có exception”

~~~text
BEGIN DB transaction
    INSERT order
COMMIT thành công
gửi email xác nhận
email service ném exception
catch -> gọi rollback của DB
~~~

`rollback` ở cuối **không hoàn tác đơn hàng đã commit**. Ngược lại, nếu gửi email trước khi commit và commit thất bại, người dùng có thể nhận “đã đặt hàng” dù cơ sở dữ liệu không ghi nhận đơn. Hai tài nguyên độc lập không tự nằm trong một transaction chung chỉ vì chúng được gọi trong cùng một phương thức Java.

Đối với Spring hay các framework khác, annotation/quy tắc transaction chỉ áp dụng khi transaction manager thật sự bao bọc các resource có hỗ trợ và các điều kiện gọi phù hợp. Ví dụ, transaction DB không tự mở rộng tới HTTP, filesystem hoặc email. Không giả định mọi unchecked/checked exception đều dẫn đến rollback trong mọi cấu hình framework; quy tắc rollback phải được kiểm chứng theo công nghệ sử dụng.

## 7. Tác động bên ngoài: không có nút undo chung

Một lời gọi có side effect bên ngoài có thể là:
- HTTP POST tạo một đơn hàng ở dịch vụ khác;
- gửi email hoặc tin nhắn;
- đẩy event lên message broker;
- trừ tiền, tạo yêu cầu thanh toán hoặc lưu một đối tượng ở remote storage;
- gửi lệnh đến thiết bị hoặc một tiến trình khác.

Ngay khi lời gọi trả thành công hoặc phía nhận thực thi lệnh, một exception Java tại caller **không gửi yêu cầu hủy mặc định**. Thậm chí khi caller thấy timeout, phía nhận có thể đã xử lý thành công rồi nhưng phản hồi bị thất lạc. Đây là **kết quả chưa xác định** chứ không đương nhiên là “thất bại, không phát sinh tác động”.

### 7.1. Retry cần có idempotency và trạng thái truy vết

Ví dụ một API thanh toán nhận khóa idempotency `paymentRequestId` cố định theo **một yêu cầu logic**. Khi HTTP timeout, client có thể truy vấn trạng thái theo định danh hoặc retry **cùng khóa** nếu dịch vụ thật sự cam kết idempotent: các yêu cầu trùng khóa được diễn giải là cùng một tác vụ, không tạo lần trừ tiền thứ hai.

Chỉ đặt header có tên “Idempotency-Key” mà phía server không hỗ trợ lưu dấu và chống race condition thì **chưa có bảo đảm**. Server thường cần cơ chế ghi nhận kết quả theo key, ràng buộc uniqueness và quy tắc về vòng đời key/payload. Với thao tác không idempotent, không retry tự động khi không biết request đầu đã được áp dụng hay chưa.

### 7.2. Transactional outbox

Khi phải cập nhật database **và** gửi event, một chiến lược phổ biến:

~~~text
Trong 1 DB transaction:
    INSERT/UPDATE dữ liệu nghiệp vụ
    INSERT bản ghi outbox
    COMMIT

Sau commit:
    worker đọc outbox
    gửi event
    ghi nhận đã gửi hoặc retry
~~~

Điểm mạnh là dữ liệu nghiệp vụ và bản ghi “cần gửi event” được commit cùng một transaction **trong cùng database/phạm vi giao dịch**. Tránh tình huống nghiệp vụ commit nhưng hoàn toàn mất dấu ý định phát event. Tuy nhiên worker có thể gửi thành công rồi chết trước khi đánh dấu đã gửi, dẫn đến **gửi lại**. Vì thế consumer vẫn cần xử lý idempotent/deduplicate. Outbox **không bảo đảm exactly-once end-to-end** chỉ bằng việc có bảng outbox.

### 7.3. Compensation/Saga

Nếu quy trình đã tạo đơn, giữ hàng và yêu cầu thanh toán ở nhiều hệ thống độc lập, thất bại bước sau có thể kích hoạt hành động bù trừ như hủy giữ hàng hoặc phát lệnh hoàn tiền. Đây là **thao tác mới**, không phải JVM quay ngược thời gian hay một rollback transaction toàn cục. Compensation cũng có thể thất bại và cần retry, giám sát, đối soát; không phải hiệu ứng nào cũng có phép đảo ngược (email không thể “rút lại” đáng tin cậy, sự kiện đã tới người nghe có thể đã kích hoạt tác động tiếp).

Cần thiết kế:
- Định danh giao dịch và trạng thái tiến trình (`PENDING`, `CONFIRMED`, `COMPENSATING`, `FAILED` hoặc trạng thái phù hợp);
- Thứ tự và điều kiện thực thi bước tiếp;
- Hành động bù trừ cụ thể, tính idempotency của từng bước;
- Chính sách retry, giới hạn retry, dead-letter/đối soát thủ công khi cần;
- Quy tắc cập nhật trạng thái khi một kết quả remote không chắc chắn.

Không dùng compensation như lý do để bỏ qua transaction nội bộ đơn giản có thể dùng được.

## 8. Cam kết an toàn dựa trên điểm xảy ra side effect

Với file hoặc dịch vụ bên ngoài, đánh giá mức bảo đảm theo **thời điểm lỗi** thay vì coi mọi exception giống nhau:

| Lỗi xuất hiện ở đâu? | Điều có thể khẳng định | Điều không được suy ra |
| --- | --- | --- |
| Trước khi gửi lệnh/ghi dữ liệu đích | Chưa có side effect **từ bước ấy**; trạng thái nội bộ có thể vẫn cần kiểm tra | Toàn bộ hệ thống chắc chắn chưa thay đổi |
| Khi đang ghi file trực tiếp | File có thể chứa dữ liệu dở dang | File đã tự rollback vì có exception |
| Sau khi thay thế thành công file ứng viên | File đích có thể đã là phiên bản mới | Exception ở bước thông báo sẽ khôi phục file |
| Sau khi gửi yêu cầu remote nhưng trước ACK | Kết quả remote **chưa chắc chắn**; cần hỏi trạng thái hoặc đối soát | Remote chắc chắn chưa xử lý, nên retry vô điều kiện |
| Trong cleanup hoặc compensation | Có thể đã xảy ra một lỗi phụ cần lưu bằng `suppressed`/log | Undo chắc chắn thành công chỉ vì code đã vào `finally` |

Trong phạm vi một object, **basic guarantee** giữ invariant dù giá trị có thể đã đổi; **strong guarantee** giữ nguyên trạng thái quan sát được nếu thất bại trong phạm vi công bố. Đối với mạng, file và nhiều resource, hai thuật ngữ này **không tự mở rộng** thành cam kết toàn ứng dụng.

Một hậu điều kiện rõ ràng hơn câu “exception sẽ rollback tất cả” là:

> Nếu validation từ chối trước publish, file đích không bị thay bằng bản ứng viên. Nếu file đã publish nhưng gửi thông báo thất bại, file đích vẫn có thể là bản mới; hệ thống ghi nhận trạng thái thông báo để xử lý lại có kiểm soát.

Vì vậy, trạng thái **đã xảy ra**, **chưa xảy ra** và **chưa biết** phải được biểu diễn riêng khi tích hợp bên ngoài; một exception tự nó không thể phân biệt đầy đủ ba trường hợp.

## 9. Thiết kế một thao tác an toàn theo từng giai đoạn

Giả sử cần cập nhật cấu hình JSON và phát sự kiện thay đổi cấu hình:

1. **Xác định invariant và phạm vi:** JSON phải hợp lệ, có version mới, dữ liệu hiện tại phải đọc được; event có thể gửi lại an toàn theo version.
2. **Chuẩn bị:** tạo JSON mới trong bộ nhớ; kiểm tra schema, kích thước, checksum/logic liên quan trước khi sửa file đích.
3. **Stage:** ghi một file tạm trong vị trí phù hợp; xác nhận đã ghi đầy đủ. Nếu lỗi giai đoạn này, xóa ứng viên.
4. **Publish:** dùng cơ chế thay thế file phù hợp file system và yêu cầu atomicity; nếu `ATOMIC_MOVE` là yêu cầu, phải xử lý khi không được hỗ trợ.
5. **Ghi nhận phiên bản đã publish:** tránh tình trạng sau crash không biết version nào là phiên bản hiện tại; cần có cách đọc lại trạng thái thực.
6. **Phát event:** chọn cơ chế phù hợp với phạm vi bền vững, ví dụ outbox nếu dữ liệu chính nằm trong DB; thiết kế version/idempotency để consumer tránh xử lý trùng.
7. **Dọn và giám sát:** xóa file tạm không còn dùng, ghi nhận lỗi phục hồi, phân biệt trạng thái “thất bại trước publish” và “publish xong nhưng thông báo lỗi”.

Với file + database + broker là **ba tài nguyên riêng**, quy trình trên không tự trở thành transaction toàn cục. Nếu hệ thống đòi hỏi tính nguyên tử xuyên cả ba, phải thiết kế giao thức nhất quán và trạng thái khôi phục; không giải quyết được bằng một `try/catch` duy nhất.

### 9.1. Tại sao thứ tự side effect ảnh hưởng đến phục hồi?

So sánh hai quy trình:

~~~text
Phương án A:
    gửi email "đã thành công"
    -> ghi dữ liệu
    -> ghi dữ liệu thất bại
Kết quả: email đã gửi, dữ liệu chưa có.

Phương án B:
    commit dữ liệu và outbox trong cùng transaction
    -> worker gửi email dựa trên outbox
    -> gửi thất bại tạm thời, worker retry
Kết quả: dữ liệu đã commit và vẫn giữ yêu cầu gửi để khôi phục.
~~~

Phương án B phù hợp khi dữ liệu và outbox nằm trong transaction có hỗ trợ, worker xử lý idempotent và có cơ chế giám sát. Nó vẫn không thể cam kết email được phát chính xác một lần trong mọi tình huống. Thông điệp gửi đi cần phản ánh trạng thái thực tế: ví dụ sự kiện “đơn đã ghi nhận” khác “thanh toán chắc chắn đã hoàn tất”.

## 10. Các anti-pattern trong xử lý exception và trạng thái

### 10.1. Nuốt exception và thông báo thành công

~~~java
try {
    writeToDisk();
} catch (Exception ignored) {
    // Không báo lỗi, nhưng phía trên vẫn nghĩ toàn bộ thao tác đã thành công.
}
return true;
~~~

Đoạn minh họa không độc lập: `writeToDisk` và phương thức bao quanh chỉ là giả định. Nếu lệnh ghi làm thay đổi một phần file rồi ném exception, trả `true` vừa che lỗi vừa che trạng thái không chắc chắn. Nên truyền lỗi, trả trạng thái có cấu trúc hoặc khởi động phục hồi theo đúng hợp đồng.

### 10.2. Gọi rollback sau mọi exception dù đã commit

~~~text
try:
    commit thành công
    gọi bên ngoài (ném lỗi)
catch:
    rollback và tuyên bố tất cả đã hủy
~~~

Rollback không tác động đến transaction **đã commit**. Cần phân biệt lỗi trước commit, lỗi sau commit và lỗi không rõ commit đã thành công hay chưa.

### 10.3. Dùng `finally` để luôn xóa file đích

~~~java
try {
    produceOutput();
} finally {
    Files.deleteIfExists(target);
}
~~~

Fragment giả định biến và hàm có sẵn. Nếu `target` là sản phẩm chính thức của một thao tác đã thành công, việc xóa trong `finally` lại phá kết quả. Chỉ dọn **tài nguyên tạm thuộc sở hữu của lần gọi**; không xóa dữ liệu chính hoặc dữ liệu do request khác sở hữu.

### 10.4. Retry POST sau timeout mà không có idempotency

Một lần timeout có thể xảy ra **sau khi server đã tạo tài nguyên**. Retry không kiểm soát có thể tạo đơn/trừ tiền hai lần. Dùng mã yêu cầu ổn định và cơ chế tra trạng thái hoặc idempotency được server hỗ trợ.

### 10.5. Tưởng `close()` chính là rollback

Đóng writer/stream không thu hồi bytes đã ghi; đóng client mạng không thu hồi request đã tới server. Kết nối JDBC phải được quản lý transaction đúng hợp đồng; không ủy thác tính chính xác cho giả định về hành vi `close`.

### 10.6. Khôi phục bằng thao tác mới nhưng không chuẩn bị khi thao tác đó thất bại

Ví dụ một API trừ tồn kho, sau lỗi gọi API cộng lại số lượng. Cả hai thao tác có thể mất kết nối hoặc cạnh tranh với giao dịch khác; phép cộng lại cũng có thể sai nếu áp dụng hai lần. Phép bù trừ cần tính idempotency, định danh nguyên nhân và giới hạn concurrency, hoặc một transaction đúng nghĩa nếu có thể.

## 11. Kiểm thử theo điểm lỗi, không chỉ theo loại exception

Để chứng minh lời hứa về bảo toàn trạng thái, chỉ assert `assertThrows(...)` là chưa đủ. Cần kiểm tra **trạng thái sau từng điểm có thể thất bại**.

| Vị trí tiêm lỗi | Cần xác nhận |
| --- | --- |
| Trước khi thay đổi state | File/database/đối tượng vẫn nguyên |
| Sau khi append một phần | Dữ liệu có thể đã thay; hợp đồng có báo đúng trạng thái không |
| Khi tạo file tạm/ghi file tạm | Không ảnh hưởng file đích; cleanup file tạm đúng mức |
| Khi validation từ chối trước publish | Version cũ vẫn tồn tại và có thể đọc |
| Trong khi move/publish | Hệ thống phát hiện failure, đọc lại trạng thái thực, không giả định chắc chắn chưa publish |
| Ngay sau khi commit DB | Rollback tiếp theo không được coi là đã đảo commit |
| Trong lúc gửi request remote | Phân biệt “phản hồi thất bại” và “server chưa thực hiện” |
| Khi cleanup/close lỗi | Exception chính và lỗi phụ không bị đánh đồng; tài nguyên/trạng thái được ghi nhận |
| Khi retry cùng idempotency key | Không tạo thêm hiệu ứng ngoài số lần mà dịch vụ cam kết |

Có thể dùng file tạm thật cho test I/O nhỏ; dùng fake/stub có khả năng ném lỗi **trước/sau khi thay đổi trạng thái** cho service khác; dùng transaction test với database thật khi xác minh rollback. Khi test timeout remote, mô phỏng trường hợp **đã xử lý nhưng phản hồi bị mất**, chứ không chỉ trường hợp server từ chối ngay lập tức.

Một số invariant cần assert:
- Không phát thông báo “thành công” trước khi kết quả thật sự đạt điều kiện công bố.
- Phần dữ liệu chưa commit có thể rollback theo engine và transaction; dữ liệu đã commit không bị nhận nhầm là đã hủy.
- Tệp đích không bị sửa bởi lỗi xảy ra trong bước stage theo hợp đồng.
- Mọi bước có thể lặp lại đều có idempotency hoặc điều kiện an toàn được kiểm chứng.
- Khi không chắc kết quả, hệ thống có trạng thái để điều tra/đối soát, thay vì trả về `false` và coi như không có side effect.

## 12. Checklist khi viết API Java có side effect

1. **Công bố phạm vi bất biến:** nếu phương thức ném exception, phần nào có thể đã thay đổi? Phần nào được bảo đảm giữ nguyên?
2. **Phân biệt resource cleanup với rollback:** `finally`/try-with-resources đóng và dọn; rollback chỉ tồn tại khi tài nguyên/giao thức thực sự hỗ trợ.
3. **Tối thiểu hóa side effect trước validation:** kiểm tra và tính toán trước, ghi qua staging nếu phù hợp.
4. **Định nghĩa điểm commit/publish:** lỗi trước/sau mốc này có hậu quả khác nhau.
5. **Giữ nguyên exception và cause:** lỗi trong cleanup/compensation cần được ghi nhận, tránh che lỗi đầu tiên và tránh nuốt exception.
6. **Dùng transaction đúng ranh giới:** cùng transaction DB thì rollback được theo bảo đảm của DB; giao dịch ngoài DB không tự tham gia.
7. **Chấp nhận trạng thái không chắc chắn từ hệ thống xa:** timeout không chứng minh chưa xử lý; dùng status query, idempotency và đối soát.
8. **Thiết kế bù trừ và retry có kiểm soát:** hành động bù trừ là side effect mới, có thể lỗi và có thể cần chạy lại.
9. **Test trạng thái sau lỗi:** thử lỗi trước ghi, sau ghi, sau commit, sau publish, trong cleanup và khi mất phản hồi.
10. **Không hứa rollback toàn bộ khi không có bằng chứng:** tài liệu API nên nói rõ trường hợp nào bất biến, trường hợp nào thay đổi một phần và cách caller khôi phục.

### Bài tập vận dụng

Thiết kế một phương thức `saveReportAndNotify(Path path, Report report)` có nhiệm vụ sinh nội dung báo cáo, lưu vào file và gửi thông báo qua dịch vụ remote. Hãy nêu trạng thái của file và thông báo khi lỗi xảy ra tại ba vị trí: (a) trước khi ghi ứng viên, (b) sau khi publish file nhưng trước khi gửi thông báo, (c) sau khi dịch vụ remote thực thi thông báo nhưng client bị timeout. Sau đó đề xuất một cơ chế ghi nhận version/trạng thái và retry không tạo thông báo trùng. Nêu rõ bảo đảm nào chỉ áp dụng cho **một file**, bảo đảm nào áp dụng cho **một transaction DB**, và bảo đảm nào cần giao thức riêng cho **tác động bên ngoài**.

Điểm cần nhớ: **exception nói rằng luồng xử lý Java bị gián đoạn; nó không nói rằng thế giới bên ngoài đã quay về trạng thái trước khi phương thức được gọi.**