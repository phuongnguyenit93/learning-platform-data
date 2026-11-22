# Giới hạn tài nguyên trước đầu vào hoặc tải bất thường

Một API tạo báo cáo nhận tham số `size` để chọn số bản ghi cần xuất. Với `size=100`, hệ thống hoạt động bình thường. Nhưng nếu khách gửi `size=10000000`, ứng dụng có thể truy vấn hàng triệu dòng, đưa toàn bộ dữ liệu vào bộ nhớ, dựng một tệp lớn rồi giữ kết nối trong thời gian dài. Cùng lúc, các yêu cầu hợp lệ cũng bị chậm hoặc thất bại. Tình huống tương tự có thể xuất hiện khi tải tệp quá lớn, giải nén dữ liệu có kích thước phình to, xử lý JSON lồng sâu hoặc thử lại liên tục một dịch vụ đang quá tải.

Trong chương **Bảo mật** thuộc module `CODE_QUALITY_FUNDAMENTALS`, việc kiểm soát tài nguyên là một phần của chất lượng mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Một hệ thống chỉ kiểm tra dữ liệu có đúng định dạng mà không kiểm tra **chi phí xử lý** vẫn có thể bị cạn CPU, RAM, kết nối, dung lượng lưu trữ hoặc hàng đợi. Vấn đề có thể do lỗi cấu hình, người dùng thao tác nhầm, tải tăng hợp lệ hoặc hành vi cố ý gây cạn tài nguyên. Thiết kế cần bảo vệ khả năng phục vụ trong tất cả các trường hợp này.

Mục tiêu bài học là học cách **đặt ngân sách tài nguyên tại đúng ranh giới**, từ chối hay giảm tải một cách có kiểm soát, và xác minh giới hạn bằng kiểm thử.

Sau bài học, bạn có thể:

- Nhận diện đầu vào và luồng xử lý có thể tiêu thụ tài nguyên tăng không kiểm soát.
- Phân biệt giới hạn **kích thước dữ liệu**, **chi phí tính toán**, **số tác vụ đồng thời**, **thời gian xử lý** và **tốc độ yêu cầu**.
- Áp dụng giới hạn ở cả lớp HTTP, parser, logic nghiệp vụ, database, hàng đợi và dịch vụ phụ thuộc.
- Viết mã Java minh họa việc đọc dữ liệu có giới hạn, giới hạn phân trang và giới hạn tác vụ đồng thời.
- Thiết kế phản hồi quá tải rõ ràng, tránh làm ảnh hưởng đến các yêu cầu khác.
- Kiểm thử các ngưỡng và tình huống tài nguyên cạn mà không cần tạo tải phá hoại.

## 1. Độ sẵn sàng cũng là vấn đề bảo mật

Các mục tiêu bảo mật thường được diễn đạt qua tính bí mật, toàn vẹn và **sẵn sàng** (*availability*). Một chức năng không bị đọc trộm dữ liệu nhưng có thể bị một request đơn lẻ chiếm toàn bộ bộ nhớ vẫn chưa đủ an toàn. Nếu dịch vụ không thể phục vụ người dùng hợp lệ khi gặp đầu vào lớn hoặc tải tăng, khả năng sẵn sàng đã bị ảnh hưởng.

Một luồng xử lý đơn giản có thể sử dụng nhiều tài nguyên nối tiếp:

```text
Client
  |
  v
HTTP server ----> bộ nhớ nhận request, kết nối, số request đồng thời
  |
  v
Parser ---------> CPU, độ sâu lồng nhau, số phần tử tạo trong bộ nhớ
  |
  v
Business logic -> CPU, thời gian xử lý, đối tượng trung gian
  |
  v
Database -------> connection pool, số bản ghi, truy vấn, khóa
  |
  v
External API ---> kết nối, timeout, quota của dịch vụ phụ thuộc
  |
  v
Response -------> bộ nhớ tạo kết quả, băng thông, thời gian gửi
```

Giới hạn ở một nơi không tự bảo đảm các nơi còn lại được bảo vệ. API có thể chặn request body quá lớn nhưng vẫn cho phép tham số `pageSize` khổng lồ qua query string. Một timeout HTTP có thể kết thúc việc chờ ở client, nhưng công việc phía server vẫn tiếp tục nếu không có cơ chế hủy phù hợp.

**Câu hỏi căn bản:** Với mỗi đầu vào và mỗi bước xử lý, có giới hạn trên nào cho lượng tài nguyên mà một request hoặc một nhóm request được phép chiếm không?

## 2. Nhận diện tài nguyên nào đang có nguy cơ cạn

| Tài nguyên | Đầu vào/tình huống làm tăng chi phí | Hậu quả điển hình | Biện pháp ở ranh giới |
| --- | --- | --- | --- |
| Bộ nhớ | Request body, tệp, collection, kết quả truy vấn không giới hạn | Áp lực GC, hết bộ nhớ | Giới hạn byte/phần tử, stream, phân trang |
| CPU | Thuật toán có độ phức tạp cao, regex, JSON lồng sâu | Độ trễ, thiếu CPU cho request khác | Giới hạn đầu vào, độ sâu, lựa chọn thuật toán |
| Thread/tác vụ đồng thời | Chặn ở I/O ngoài quá lâu, quá nhiều công việc nền | Hết worker, request xếp hàng | Semaphore, pool có giới hạn, timeout |
| Kết nối | Nhiều HTTP request, truy vấn DB chậm | Hết connection pool | Giới hạn concurrency, timeout, đóng tài nguyên |
| Dung lượng lưu trữ | Upload, tệp tạm, log, bản ghi công việc không dọn | Hết ổ đĩa/quota | Quota, vòng đời dữ liệu, giới hạn upload |
| Băng thông | Download không giới hạn, response quá lớn | Chậm toàn hệ thống, chi phí tăng | Phân trang, nén phù hợp, quota truyền tải |
| Hàng đợi | Công việc đến nhanh hơn tốc độ xử lý | Tồn đọng tăng, RAM/đĩa cạn | Queue hữu hạn, backpressure, từ chối tải |
| Dịch vụ ngoài | Retry dồn dập, gọi nhiều nhánh song song | Vượt quota, gây quá tải dây chuyền | Deadline, giới hạn retry, concurrency và rate |

Một request có thể nhìn nhỏ nhưng gây chi phí lớn: ví dụ một biểu thức tìm kiếm buộc quét bảng dữ liệu lớn hoặc một tệp nén nhỏ tạo ra lượng dữ liệu giải nén rất lớn. Vì thế **kích thước đầu vào chỉ là một phần của ngân sách**.

Không có mức giới hạn chung luôn đúng cho mọi sản phẩm. Một API ảnh đại diện khác API nhập dữ liệu phân tích; một tác vụ xuất báo cáo nền khác truy vấn tương tác cần trả trong vài giây. Giới hạn cần dựa trên yêu cầu sản phẩm, sức chứa hệ thống và phép đo thực tế.

## 3. Đặt giới hạn ở nhiều ranh giới, tránh một điểm bảo vệ duy nhất

Hãy chia giới hạn theo lớp trách nhiệm:

1. **Cổng nhận request:** giới hạn request body, header, tốc độ, số kết nối và thời gian giữ kết nối theo khả năng của reverse proxy/server.
2. **Parser:** giới hạn số phần tử, số token, độ sâu lồng nhau, kích thước dữ liệu sau giải nén.
3. **Nghiệp vụ:** giới hạn số hàng cần xuất, số mục trong giỏ, phạm vi thời gian tìm kiếm hoặc số kết quả một giao dịch.
4. **Tài nguyên xử lý:** giới hạn công việc đang chạy, dung lượng hàng đợi và ngân sách thời gian.
5. **Phụ thuộc:** timeout, số lời gọi song song, quota, giới hạn retry và số dòng database trả về.
6. **Kết quả và lưu trữ:** giới hạn kích thước response, thời gian tồn tại của tệp tạm, số bản ghi tồn đọng.

Đặt giới hạn ngay từ ranh giới ngoài giúp từ chối rẻ và sớm. Đặt thêm giới hạn gần nơi tiêu thụ tài nguyên giúp bảo vệ khi dữ liệu đến từ nguồn khác như message broker, batch job hoặc một API nội bộ không đi qua HTTP gateway.

Ví dụ, không nên chỉ dựa vào UI để giới hạn `pageSize` ở 100: client khác vẫn có thể gửi giá trị lớn hơn. Server phải xác minh ràng buộc của chính nó.

### Giới hạn cần được diễn đạt chính xác

Một quy định “tệp không quá 5 MB” cần nêu:

- Giới hạn theo byte hay theo “MB” thập phân?
- Giới hạn áp cho dữ liệu trước nén, sau giải nén hay cả hai?
- Từng tệp hay tổng toàn request?
- Một lần tải hay tổng dung lượng của người dùng?
- Nếu vượt giới hạn, hệ thống từ chối trước khi lưu hay xóa tệp tạm sau đó?

Tên hằng nên phản ánh đơn vị: `MAX_REQUEST_BODY_BYTES`, `MAX_PAGE_SIZE`, `MAX_ACTIVE_EXPORTS`. Những tên chung chung như `LIMIT = 100` làm người bảo trì khó biết đang bảo vệ điều gì.

## 4. Đọc request body có giới hạn thay vì nạp vô hạn

Trong Java, `InputStream.readAllBytes()` rất tiện. Nhưng nếu nguồn là request hoặc tệp do người dùng kiểm soát, gọi trực tiếp có thể cố đưa toàn bộ dữ liệu vào bộ nhớ.

Ví dụ minh họa một bộ đọc **tối đa số byte đã cấu hình**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Objects;

final class PayloadTooLargeException extends IOException {
    PayloadTooLargeException(int maxBytes) {
        super("Payload exceeds " + maxBytes + " bytes");
    }
}

final class BoundedBodyReader {
    static byte[] read(InputStream source, int maxBytes) throws IOException {
        Objects.requireNonNull(source, "source");
        if (maxBytes < 0) {
            throw new IllegalArgumentException("Negative maxBytes");
        }

        byte[] buffer = new byte[8 * 1024];
        ByteArrayOutputStream result =
                new ByteArrayOutputStream(Math.min(maxBytes, buffer.length));
        int consumed = 0;
        int count;

        while ((count = source.read(buffer)) != -1) {
            if (count > maxBytes - consumed) {
                throw new PayloadTooLargeException(maxBytes);
            }
            result.write(buffer, 0, count);
            consumed += count;
        }
        return result.toByteArray();
    }
}
```

Cách sử dụng:

```java
private static final int MAX_JSON_BODY_BYTES = 64 * 1024;

// Tại ranh giới request, dùng try-with-resources hoặc cơ chế đóng
// của framework/server để đảm bảo stream được giải phóng.
byte[] body = BoundedBodyReader.read(inputStream, MAX_JSON_BODY_BYTES);
```

Điểm cần hiểu:

- Mỗi lần đọc dùng buffer 8 KiB, không tạo mảng theo kích thước do client khai báo.
- Trước khi thêm vào `ByteArrayOutputStream`, code kiểm tra tổng byte không vượt giới hạn.
- Phép kiểm tra `count > maxBytes - consumed` tránh vấn đề cộng số vượt quá ngưỡng trước khi so sánh.
- Khi phát hiện quá lớn, phương thức ném lỗi và **không tiếp tục tích lũy dữ liệu**.
- Việc trả `byte[]` phù hợp với dữ liệu nhỏ có giới hạn. Với tệp lớn hợp lệ, nên xử lý theo luồng với quota và lưu trữ phù hợp.

Giới hạn trên áp cho lượng byte mà phương thức đọc, nhưng `ByteArrayOutputStream` và `toByteArray()` vẫn có thể giữ **nhiều bản sao** của dữ liệu trong quá trình thao tác. Vì thế mức 64 KiB là ngân sách ví dụ cho một request nhỏ, không phải bảo đảm tổng bộ nhớ chỉ đúng 64 KiB.

Bộ đọc trên **không tự đặt timeout**, không kiểm tra định dạng JSON và không quyết định HTTP status. Tầng gọi phải đóng stream, giới hạn thời gian đọc, chuyển `PayloadTooLargeException` thành phản hồi phù hợp và xử lý việc ngắt/kết thúc kết nối theo server đang dùng.

### Vì sao không chỉ tin Content-Length?

Header `Content-Length` có thể giúp từ chối sớm khi giá trị công bố đã vượt ngưỡng. Tuy nhiên, dữ liệu cũng có thể được truyền theo cơ chế chunked hoặc qua các tầng xử lý khác; phía nhận không nên dựa riêng vào giá trị header để bảo vệ bộ nhớ.

Một chính sách hợp lý là **kiểm tra sớm khi có thông tin kích thước và vẫn đo lượng dữ liệu thực tế trong lúc đọc**. Trên server có reverse proxy, cần thống nhất giới hạn giữa proxy và ứng dụng, đặc biệt khi chúng xử lý nén hoặc chuyển đổi dữ liệu khác nhau.

## 5. Dữ liệu nén và parser: kích thước nhỏ chưa đồng nghĩa chi phí nhỏ

Một tệp nén nhỏ có thể tạo ra dữ liệu giải nén lớn, nhiều tệp con hoặc cấu trúc lồng nhau. Nếu chỉ kiểm tra kích thước tệp nén, hệ thống có thể vượt ngân sách bộ nhớ hoặc dung lượng đĩa sau khi giải nén.

Với nội dung nén hoặc archive, cần cân nhắc:

- Giới hạn kích thước **đầu vào nén** và **tổng dữ liệu đã giải nén**.
- Giới hạn số mục, độ sâu thư mục/lồng nhau và kích thước một mục.
- Giới hạn CPU/thời gian giải nén và số công việc giải nén đồng thời.
- Chỉ lưu vào vùng tạm có quota, kiểm soát đường dẫn và xóa dữ liệu khi xử lý thất bại.
- Không tạo toàn bộ danh sách file hoặc nội dung giải nén trong bộ nhớ nếu có thể xử lý theo luồng.

Với JSON/XML hoặc định dạng cây, số byte cũng không phải thước đo đầy đủ. Một dữ liệu có nhiều phần tử nhỏ hoặc lồng sâu có thể tạo ra cây object lớn hoặc làm parser tốn CPU. Hãy dùng khả năng giới hạn của parser/framework đang triển khai: **độ sâu, số token, số phần tử, độ dài trường và số thực thể được mở rộng** khi có liên quan.

**Không nên chỉ tăng heap hoặc timeout** để “giải quyết” một parser nhận dữ liệu không giới hạn. Việc mở rộng tài nguyên có thể trì hoãn triệu chứng nhưng không tạo ra giới hạn chi phí cho một yêu cầu.

### Bytes, ký tự và số phần tử là ba giới hạn khác nhau

`String.length()` trong Java đếm số đơn vị mã UTF-16, không tương đương trực tiếp với số byte UTF-8 hoặc số ký tự người dùng nhìn thấy. Nếu hợp đồng giới hạn byte truyền qua mạng, đo byte tại tầng nhận. Nếu giới hạn tên hiển thị theo ký tự, xác định chính sách ký tự thích hợp và kiểm tra tại tầng dữ liệu tương ứng.

Ví dụ: một chuỗi có độ dài `String.length() == 100` không có nghĩa là mã hóa UTF-8 của nó luôn chiếm đúng 100 byte.

## 6. Giới hạn danh sách và phân trang ngay tại hợp đồng nghiệp vụ

Quay lại API báo cáo. Nếu client được tự chọn `pageSize` hoặc `maxRows` tùy ý, một truy vấn hợp lệ về mặt cú pháp vẫn có thể tiêu thụ quá nhiều kết nối, bộ nhớ và CPU.

Ví dụ Java 17 dùng `record` để thực thi giới hạn:

```java
record PageRequest(int size, String cursor) {
    static final int MAX_PAGE_SIZE = 100;

    PageRequest {
        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                    "Page size must be between 1 and " + MAX_PAGE_SIZE);
        }
        if (cursor != null && cursor.length() > 512) {
            throw new IllegalArgumentException("Cursor is too long");
        }
    }
}
```

Ở đây, khoảng hợp lệ 1–100 là **chính sách minh họa**. Nếu sản phẩm hỗ trợ gói dữ liệu lớn hơn, giới hạn phải được quyết định theo nhu cầu và chi phí thực.

Để ràng buộc có tác dụng thật, tầng truy vấn vẫn phải áp giới hạn vào dữ liệu được lấy về:

```java
String sql = """
        SELECT id, customer_id, total_vnd
        FROM orders
        WHERE id > ?
        ORDER BY id
        LIMIT ?
        """;

// Chuẩn bị câu lệnh và bind tham số, không nối chuỗi từ client:
preparedStatement.setLong(1, lastSeenId);
preparedStatement.setInt(2, pageRequest.size());
```

Đây là SQL minh họa cho hệ quản trị hỗ trợ `LIMIT ?` và phân trang theo ID tăng dần. Khi dùng cursor thực tế, cần xác định thứ tự ổn định, tính hợp lệ của cursor và phạm vi dữ liệu mà người dùng được phép xem. Trong Java, constructor `PageRequest` chỉ kiểm tra kích thước và độ dài cursor, **chưa chứng thực nội dung hoặc quyền truy cập của cursor**.

Tránh chiến lược “truy vấn tất cả rồi `subList(0, 100)`”. Dù response chỉ có 100 phần tử, database và ứng dụng vẫn có thể phải xử lý toàn bộ tập dữ liệu. Giới hạn phải nằm **trước bước tốn tài nguyên**.

### Phân trang không chữa mọi truy vấn chậm

Một truy vấn có `LIMIT 100` vẫn có thể quét hoặc sắp xếp rất nhiều dòng nếu thiếu chỉ mục hoặc lọc phức tạp. Cần xem kế hoạch truy vấn, điều kiện lọc, thời hạn thực thi và cách dùng cursor. Đối với tìm kiếm toàn văn hay tổng hợp lớn, có thể cần giới hạn phạm vi thời gian hoặc chuyển sang tác vụ nền.

## 7. Độ phức tạp thuật toán quyết định chi phí của đầu vào

Một vòng lặp qua `n` phần tử thường có chi phí tăng gần tuyến tính; hai vòng lặp lồng nhau qua cùng dữ liệu có thể khiến số phép so sánh tăng gần `n²`. Với `n` nhỏ, cả hai đều ổn. Với `n` rất lớn do client điều khiển, cách tính thứ hai có thể tiêu tốn CPU đáng kể.

Ví dụ tìm các ID trùng nhau bằng việc so sánh mọi cặp:

```java
boolean hasDuplicatesSlow(List<String> ids) {
    for (int i = 0; i < ids.size(); i++) {
        for (int j = i + 1; j < ids.size(); j++) {
            if (ids.get(i).equals(ids.get(j))) {
                return true;
            }
        }
    }
    return false;
}
```

Với dữ liệu đã được giới hạn và khi bộ nhớ cho phép, có thể dùng tập hợp:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

boolean hasDuplicates(List<String> ids) {
    Set<String> seen = new HashSet<>();
    for (String id : ids) {
        if (!seen.add(id)) {
            return true;
        }
    }
    return false;
}
```

Cách thứ hai thường giảm số phép so sánh trung bình, nhưng dùng thêm bộ nhớ và vẫn cần giới hạn số phần tử. Nếu `ids` có thể chứa null hoặc chuỗi quá dài, hợp đồng phải xác định có chấp nhận không. Đổi thuật toán **không thay thế** việc giới hạn đầu vào.

### Với regex và parser, chú ý độ phức tạp trên dữ liệu bất thường

Một số biểu thức chính quy có kiểu lặp lồng nhau hoặc nhiều nhánh chồng lấn có thể tốn thời gian bất thường trên chuỗi do người dùng cung cấp. Nên dùng biểu thức đơn giản, có giới hạn độ dài đầu vào và tránh chạy những bộ phân tích tổng quát tốn CPU trên dữ liệu không tin cậy.

Ví dụ kiểm tra mã ngắn bằng tập ký tự rõ ràng:

```java
private static final Pattern SAFE_CODE =
        Pattern.compile("[A-Za-z0-9_-]{1,64}");

boolean isValidCode(String value) {
    return value != null && SAFE_CODE.matcher(value).matches();
}
```

Ví dụ cần `import java.util.regex.Pattern;`. Ràng buộc 1–64 ký tự thuộc bảng chữ ASCII đã nêu, dễ hiểu và hạn chế phạm vi xử lý. Nếu nghiệp vụ cần Unicode hoặc định dạng khác, phải thay quy tắc theo yêu cầu; **không tự dùng regex này để xử lý mọi tên người hoặc văn bản**.

## 8. Giới hạn số công việc đồng thời để một nhóm request không chiếm hết worker

Giả sử dịch vụ tạo báo cáo dùng 8 worker xử lý tác vụ nặng. Nếu nhận đồng thời hàng trăm tác vụ mà không giới hạn số đang chạy, bộ nhớ và CPU có thể bị quá tải ngay cả khi mỗi tác vụ đã có giới hạn riêng.

Một semaphore có thể bao một công việc đồng bộ:

```java
import java.util.Objects;
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;

final class ServiceBusyException extends RuntimeException {
    ServiceBusyException() {
        super("Too many active operations");
    }
}

final class ConcurrencyGate {
    private final Semaphore permits;

    ConcurrencyGate(int maxInFlight) {
        if (maxInFlight < 1) {
            throw new IllegalArgumentException("maxInFlight must be positive");
        }
        this.permits = new Semaphore(maxInFlight);
    }

    <T> T call(Supplier<T> operation) {
        Objects.requireNonNull(operation, "operation");

        if (!permits.tryAcquire()) {
            throw new ServiceBusyException();
        }
        try {
            return operation.get();
        } finally {
            permits.release();
        }
    }
}
```

Sử dụng:

```java
ConcurrencyGate reportGate = new ConcurrencyGate(8);

String reportId = reportGate.call(() -> reportGenerator.create(request));
```

Cơ chế có ba đặc điểm:

- Chỉ có tối đa 8 lời gọi nằm trong phần bảo vệ **tại một instance của `ConcurrencyGate`** cùng lúc.
- Khi hết chỗ, request mới được từ chối ngay thay vì xếp chồng vô hạn.
- `finally` bảo đảm nhả permit dù công việc ném exception.

Đây là giới hạn **đồng thời**, không phải giới hạn số request trong một phút. Nếu ứng dụng chạy 4 instance và mỗi instance có 8 permit, tổng giới hạn có thể lên tới 32 nếu không có cơ chế phối hợp. Trong hệ thống nhiều instance cần xét ngân sách tổng và giới hạn ở dịch vụ phụ thuộc.

Nếu `operation.get()` chỉ **khởi tạo công việc bất đồng bộ rồi trả ngay**, permit sẽ bị nhả quá sớm. Khi đó phải giữ permit đến lúc công việc thật sự hoàn tất hoặc hủy, đồng thời xử lý mọi đường thất bại. Không thể dùng ví dụ đồng bộ này nguyên xi để bảo vệ một `CompletionStage`.

### Semaphore không thay thế thời hạn và giới hạn hàng đợi

Một công việc giữ permit nhưng bị treo mãi có thể khiến các request sau bị từ chối vô hạn. Cần timeout, cơ chế hủy phù hợp và quan sát thời gian chiếm permit. Nếu hệ thống cần hàng đợi, số phần tử chờ cũng phải hữu hạn.

## 9. Hàng đợi vô hạn và retry có thể khuếch đại quá tải

Giả sử mỗi phút có 2.000 yêu cầu tạo báo cáo nhưng hệ thống chỉ xử lý xong 1.500 yêu cầu. Nếu cứ thêm vào hàng đợi vô hạn, phần còn lại tích tụ và tăng theo thời gian. Hệ thống có thể hết bộ nhớ hoặc dung lượng ổ đĩa dù không có lỗi xử lý riêng lẻ.

Một pool có queue hữu hạn trong Java có thể được khởi tạo như sau:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor executor = new ThreadPoolExecutor(
        4,
        4,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadPoolExecutor.AbortPolicy()
);
```

Đây là cấu hình minh họa: 4 worker, tối đa 100 tác vụ chờ. Khi không thể tiếp nhận thêm, `AbortPolicy` gây `RejectedExecutionException` tại điểm gửi tác vụ. Tầng gọi phải chuyển việc từ chối thành kết quả phù hợp, theo dõi số lần bị từ chối và đóng executor khi hết vòng đời ứng dụng.

Đừng thay `AbortPolicy` bằng cách tự động xếp yêu cầu sang một queue thứ hai **không giới hạn**. Điều đó chỉ dời vị trí quá tải. Nếu nhiệm vụ cần được xử lý sau khi request kết thúc, nên có cơ chế lưu bền vững và vòng đời công việc phù hợp, nhưng lưu bền vững cũng cần quota, thời hạn và chính sách xử lý khi đầy.

### Retry phải có ngân sách

Khi dịch vụ dưới tải lớn trả lỗi, các client tự động retry ngay có thể làm số lời gọi tăng mạnh. Một chính sách retry an toàn cần:

- Xác định lỗi tạm thời nào đáng thử lại.
- Có số lần thử tối đa, tổng deadline và khoảng chờ có backoff/jitter.
- Tôn trọng `Retry-After` khi server cung cấp và client được cấu hình hỗ trợ.
- Không retry mù các thao tác có tác dụng phụ nếu chưa có idempotency.
- Tránh nhiều tầng cùng tự nhân số lần retry (gateway, service, HTTP client).

**Không có cơ chế retry nào bảo đảm phục hồi khi nguyên nhân là quá tải kéo dài.** Thử lại có giới hạn phải đi cùng khả năng từ chối hoặc trì hoãn công việc.

## 10. Rate limiting: giới hạn tốc độ khác với giới hạn đồng thời

Một người dùng có thể gửi 10.000 request nhỏ mỗi phút dù mỗi request chỉ xử lý trong vài mili giây. Semaphore giới hạn bao nhiêu công việc xử lý **cùng lúc**, nhưng khi công việc kết thúc nhanh, nó không tự giới hạn **tổng số request theo thời gian**.

Rate limiter thường dùng ngân sách theo cửa sổ thời gian hoặc cơ chế token bucket. Ví dụ chính sách minh họa cho một API:

```text
Giới hạn theo API key:
- Tối đa 60 request mỗi phút cho endpoint tương tác.
- Dung lượng burst được đặt rõ trong token bucket.
- Khi hết ngân sách: trả 429 và thông tin thử lại nếu có.

Giới hạn tài nguyên hệ thống:
- Tối đa 8 báo cáo đang tạo đồng thời.
- Tối đa 100 báo cáo chờ tại mỗi worker pool.
- Khi hết khả năng hệ thống: từ chối hoặc hẹn xử lý sau.
```

Hai ngân sách bảo vệ hai tình huống khác nhau. Chính sách thực tế phải xác định ai được tính quota: tài khoản, tenant, API key, địa chỉ IP, route hay một tổ hợp phù hợp. Chỉ giới hạn theo IP có thể ảnh hưởng nhiều người dùng hợp lệ sau một mạng chung; chỉ theo tài khoản có thể thiếu hiệu quả với endpoint chưa đăng nhập.

Với nhiều server, nếu mỗi instance tự đếm độc lập, tổng tốc độ cho phép có thể lớn hơn dự kiến. Cần xét bộ đếm tập trung, điều phối qua gateway hoặc thiết kế giới hạn phân tán phù hợp; các thao tác cập nhật bộ đếm phải an toàn khi nhiều request đồng thời.

Một rate limiter cũng cần bảo vệ **chính trạng thái của nó**: nếu tạo bộ đếm mới vô hạn cho mọi key không xác thực mà client gửi, bộ nhớ của limiter có thể trở thành nơi cạn tài nguyên. Nên có giới hạn số key theo dõi, thời hạn lưu và chính sách xử lý key chưa xác thực.

## 11. Timeout, deadline và hủy: kết thúc chờ chưa chắc kết thúc công việc

Một lời gọi tới dịch vụ ngoài có thể treo lâu hơn ngân sách request chính. Timeout giúp giới hạn thời gian phía gọi chờ, nhưng cần phân biệt:

- **Connection timeout:** thời gian tối đa cho bước thiết lập kết nối.
- **Thời hạn request/call:** ngân sách cho thao tác tại client theo cơ chế của thư viện.
- **Deadline toàn luồng:** thời điểm công việc nghiệp vụ phải hoàn thành hoặc bị từ chối.
- **Hủy công việc:** tín hiệu yêu cầu dừng, không nhất thiết có hiệu lực tức thời.

Ví dụ cấu hình thời gian cho Java HTTP Client:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://shipping.example.test/quote"))
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();
```

Đây chỉ là ví dụ thiết lập timeout, **không phải mã gửi request hoàn chỉnh**. Thư viện và `BodyHandler` được chọn ảnh hưởng cách nhận/tiêu thụ body. Nếu ứng dụng nhận response dưới dạng stream và tự đọc sau khi đã nhận headers, cần xem tài liệu API để bảo vệ cả thời gian đọc phần nội dung và kích thước response. Không nên cho rằng cấu hình timeout một chỗ tự đặt giới hạn byte và chi phí parsing.

Khi request phía ngoài đã hết deadline, việc để tác vụ nền tiếp tục chiếm tài nguyên không có giá trị có thể làm tăng quá tải. Tuy nhiên, việc gọi `Future.cancel(true)` chỉ là yêu cầu ngắt; mã xử lý hoặc thư viện I/O phải hỗ trợ dừng an toàn. Các tác dụng phụ như ghi database hoặc thu tiền có thể đã xảy ra, nên không thể suy ra kết quả “chưa thực hiện” chỉ từ timeout.

### Ngân sách thời gian cần được truyền theo luồng

Nếu toàn bộ request chỉ còn 1 giây, không nên bắt đầu một lời gọi bên ngoài được phép chạy 10 giây. Các tầng nên xét thời gian còn lại và dành chỗ cho xử lý lỗi, đóng tài nguyên và trả phản hồi. Ở các quy trình có tác dụng phụ, trạng thái “kết quả chưa rõ” có thể cần đối soát trước khi retry.

## 12. Phản hồi quá tải: từ chối rõ và suy giảm an toàn

Khi vượt giới hạn, hành vi từ chối cần có hợp đồng ổn định:

| Tình huống | Phản hồi thường phù hợp | Ý nghĩa |
| --- | --- | --- |
| Request body vượt giới hạn đã công bố | HTTP `413 Payload Too Large` | Dữ liệu gửi lên quá lớn |
| Client/tài khoản vượt quota tốc độ | HTTP `429 Too Many Requests` | Cần giảm tốc độ hoặc thử lại theo chính sách |
| Server hết khả năng xử lý tạm thời | HTTP `503 Service Unavailable` | Không có đủ năng lực tiếp nhận hiện tại |
| Đầu vào sai quy tắc nghiệp vụ | HTTP `400` hoặc `422` tùy API | Dữ liệu không hợp lệ với hợp đồng |
| Phụ thuộc ngoài không phản hồi đúng hạn | Có thể `504 Gateway Timeout` ở vai trò gateway | Lỗi của phụ thuộc hoặc đường chuyển tiếp |

Đây là những hướng dẫn phổ biến, không phải mọi framework sẽ tự ánh xạ đúng nếu không cấu hình. `Retry-After` hữu ích với một số phản hồi 429 hoặc 503 khi có thể đưa ra chỉ dẫn phù hợp. Không đưa ra thời gian thử lại giả định nếu không biết khi nào hệ thống có thể phục hồi.

**Suy giảm chức năng an toàn** (*graceful degradation*) là duy trì phần chức năng có thể đáp ứng được mà không phá bất biến. Ví dụ tạm ẩn gợi ý sản phẩm khi dịch vụ gợi ý quá tải có thể hợp lý. Nhưng không được bỏ qua bước xác thực quyền hoặc kiểm tra thanh toán chỉ để trả kết quả nhanh hơn.

Một giới hạn bảo vệ tài nguyên cần được truyền đạt rõ; không biến lỗi thành giá trị thành công như danh sách rỗng, phí 0 hoặc kết quả “đã lưu” khi thao tác chưa hoàn tất.

## 13. Tính công bằng giữa các người dùng và các công việc

Nếu chỉ giới hạn tổng số request, một tenant gửi nhiều tác vụ nặng có thể sử dụng hết khả năng phục vụ của toàn hệ thống. Một thiết kế nhiều tenant có thể cần:

- Quota hoặc số tác vụ đồng thời riêng theo tenant/API key.
- Giới hạn tổng cấp hệ thống để bảo vệ tài nguyên chung.
- Ưu tiên hợp lý cho công việc tương tác so với tác vụ nền lớn.
- Hạn chế một job lớn giữ toàn bộ connection hoặc CPU.
- Quản lý hàng đợi và cách phân phối khả năng xử lý.

**Giới hạn tổng và giới hạn theo người dùng có thể cùng tồn tại.** Ví dụ tenant A được tối đa 3 báo cáo song song, còn toàn hệ thống được tối đa 12 báo cáo. Khi triển khai nhiều instance, phải xác định giới hạn này được thực thi ở cấp instance, cụm máy hay dịch vụ chung.

Không nên suy ra “mỗi tài khoản 100 request/phút” có chi phí như nhau. Một request xuất báo cáo theo một năm có thể nặng hơn nhiều so với một request lấy trạng thái đơn. Có thể cần ngân sách theo **trọng số công việc**, nhưng độ phức tạp của cơ chế tính điểm phải tương xứng với bằng chứng về tải.

## 14. Một ví dụ tổng hợp: API tạo báo cáo

Giả sử yêu cầu sản phẩm là tạo báo cáo đơn hàng theo khoảng thời gian, mỗi lần trả một trang kết quả. Hãy nhận diện các rủi ro theo đường đi:

```text
GET /reports/orders?from=...&to=...&size=...
  |
  +-- Validate:
  |     size từ 1 đến 100
  |     phạm vi ngày tối đa theo chính sách
  |     tenant có quyền xem dữ liệu
  |
  +-- Admission control:
  |     quota tốc độ theo tenant
  |     giới hạn truy vấn đang chạy
  |
  +-- Query:
  |     statement có tham số
  |     ORDER BY ổn định và LIMIT
  |     timeout truy vấn và chỉ mục phù hợp
  |
  +-- Build response:
  |     serialize từng trang có giới hạn
  |     không đưa cả bảng vào bộ nhớ
  |
  +-- Return:
        dữ liệu + cursor trang kế tiếp
        hoặc lỗi vượt giới hạn/quá tải rõ nghĩa
```

Giả sử hệ thống muốn cho phép tải CSV hàng triệu dòng, API phân trang tương tác có thể không phải đường phù hợp. Có thể chuyển sang tác vụ xuất nền, trả ID công việc và thông báo trạng thái; nhưng tác vụ nền vẫn cần **quota, giới hạn đang xử lý, kích thước tệp tối đa, TTL và cơ chế dọn tệp**.

### Kết hợp các giới hạn thành một ngân sách có thể kiểm chứng

| Ranh giới | Chính sách minh họa | Điều cần kiểm thử |
| --- | --- | --- |
| Query parameter | `size` trong 1–100 | 0 và 101 bị từ chối |
| Khoảng thời gian | Tối đa 31 ngày | Ngày bắt đầu > ngày kết thúc; khoảng quá lớn |
| Số truy vấn đồng thời | Tối đa 8 mỗi instance | Request thứ 9 không chiếm thêm worker |
| Database | Chỉ đọc một trang có thứ tự | Số dòng không vượt 100 |
| Response | Có giới hạn byte/tác vụ | Kết quả bị chặn hoặc chuyển sang cơ chế xuất phù hợp |
| Tốc độ tenant | Quota theo chính sách | Từ chối khi quá tốc độ, không ảnh hưởng tenant khác |
| Tác vụ nền | Queue hữu hạn và TTL | Khi đầy hoặc hết hạn được xử lý rõ ràng |

Các con số trong bảng **không phải cấu hình mặc định nên sao chép**. Cần đo tải thực, số request đồng thời và chi phí mỗi thao tác để xác định ngưỡng cho hệ thống.

## 15. Kiểm thử ranh giới tài nguyên bằng đầu vào có kiểm soát

Kiểm thử giới hạn không cần gửi dữ liệu khổng lồ để “xem có sập hay không”. Hãy dùng mức nhỏ trong môi trường test và kiểm tra đúng hành vi ở sát ngưỡng.

Ví dụ JUnit 5 cho bộ đọc `BoundedBodyReader` ở mục 4:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.io.ByteArrayInputStream;

class BoundedBodyReaderTest {
    @Test
    void acceptsExactlyTheAllowedBytes() throws Exception {
        byte[] data = new byte[] {1, 2, 3, 4};

        byte[] result = BoundedBodyReader.read(
                new ByteArrayInputStream(data), 4);

        assertArrayEquals(data, result);
    }

    @Test
    void rejectsOneByteOverTheLimit() {
        byte[] data = new byte[] {1, 2, 3, 4, 5};

        assertThrows(PayloadTooLargeException.class, () ->
                BoundedBodyReader.read(
                        new ByteArrayInputStream(data), 4));
    }

    @Test
    void rejectsInvalidLimit() {
        assertThrows(IllegalArgumentException.class, () ->
                BoundedBodyReader.read(
                        new ByteArrayInputStream(new byte[0]), -1));
    }
}
```

Test phân trang:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class PageRequestTest {
    @Test
    void allowsBoundarySizes() {
        assertEquals(1, new PageRequest(1, null).size());
        assertEquals(100, new PageRequest(100, null).size());
    }

    @Test
    void rejectsOversizedPage() {
        assertThrows(IllegalArgumentException.class, () ->
                new PageRequest(101, null));
        assertThrows(IllegalArgumentException.class, () ->
                new PageRequest(0, null));
    }
}
```

Các test này xác minh **giới hạn logic**. Chúng không kiểm chứng đầy đủ hệ thống HTTP, body giải nén, connection pool hay database thật. Vì vậy, cần bổ sung những loại kiểm thử phù hợp:

- **Unit test:** sát ngưỡng, trên ngưỡng, tham số null/âm, tác vụ bị từ chối khi hết permit.
- **Integration test:** HTTP status khi body quá lớn, timeout truy vấn, đóng stream, cấu hình giới hạn thật ở proxy/server, khả năng dọn tệp tạm.
- **Concurrency test có kiểm soát:** giữ N tác vụ trong giới hạn và xác nhận tác vụ N+1 được từ chối, sau khi kết thúc có thể tiếp nhận lại.
- **Load test trong môi trường riêng:** tăng tải tới ngưỡng dự kiến, theo dõi CPU, RAM, thread, connection, queue và tỷ lệ lỗi mà không ảnh hưởng hệ thống sản xuất.
- **Failure test:** một dịch vụ ngoài chậm hoặc queue đầy; hệ thống có từ chối đúng và phục hồi khi tải giảm không?

Điều quan trọng là **đặt kỳ vọng cụ thể** cho kết quả. Một test chỉ khẳng định “không ném exception” chưa đủ để xác nhận hệ thống giữ giới hạn tài nguyên.

## 16. Quan sát, đo đạc và điều chỉnh giới hạn

Không có giới hạn nào đúng mãi khi tải hoặc yêu cầu sản phẩm thay đổi. Cần đo để biết có nên giảm, tăng hay phân nhóm ngân sách.

Các tín hiệu thường hữu ích:

- Số request bị từ chối theo lý do: body quá lớn, quá quota, hết slot, queue đầy.
- Kích thước request/response và phân vị tải, kèm dữ liệu đủ để hiểu chi phí.
- Số tác vụ đang chạy, độ dài queue, thời gian chờ và thời gian xử lý.
- Bộ nhớ heap, tần suất GC, CPU, thread và số connection đang dùng.
- Độ trễ/trạng thái lỗi của database và dịch vụ ngoài; số retry.
- Tốc độ tăng tệp tạm, log, dung lượng lưu trữ và số job chưa hoàn thành.
- Sự khác biệt giữa nhóm tenant và loại tác vụ.

Mục tiêu không phải ghi toàn bộ request body hay dữ liệu nhạy cảm để phân tích quá tải. Có thể ghi **số byte, loại thao tác, mã lý do từ chối và correlation ID**, với chính sách logging phù hợp.

Khi thay đổi giới hạn, cần xét ảnh hưởng đến client hợp lệ: một số người có thể cần export lớn nhưng nên được phục vụ bằng công việc nền thay vì mở vô hạn API tương tác. Hãy kiểm tra lại tải thực trước khi nâng mức; nếu thuật toán hoặc truy vấn không hiệu quả, tăng giới hạn có thể làm vấn đề nặng hơn.

## 17. Những cách xử lý tưởng hợp lý nhưng làm hệ thống rủi ro hơn

**“Chỉ cần kiểm tra Content-Length.”** Dữ liệu có thể đi qua nhiều tầng, được chunked hoặc thay đổi khi giải nén. Phải đo dữ liệu thực tế tại nơi tiêu thụ.

**“Đọc hết vào RAM rồi mới kiểm tra dung lượng.”** Khi đó bộ nhớ đã bị sử dụng trước khi có thể từ chối. Giới hạn phải được áp dụng trong quá trình đọc.

**“Timeout là đủ.”** Timeout không tự giới hạn kích thước dữ liệu, CPU hoặc số tác vụ đồng thời; cũng không bảo đảm công việc ngoài đã dừng.

**“Queue vô hạn sẽ không mất công việc.”** Queue vô hạn có thể dẫn tới cạn RAM/đĩa và tăng thời gian chờ tới mức vô ích. Cần quota, giới hạn và chính sách quá tải.

**“Retry mọi lỗi giúp hệ thống bền hơn.”** Retry dồn dập làm tăng tải khi dịch vụ đang yếu; thao tác có tác dụng phụ còn có nguy cơ thực hiện trùng.

**“Trả danh sách rỗng khi database quá tải.”** Như vậy biến lỗi hệ thống thành kết quả nghiệp vụ thành công, khiến dữ liệu hiển thị sai và khó chẩn đoán.

**“Chặn mọi tài khoản theo cùng một quota là công bằng.”** Các công việc có chi phí khác nhau; có thể cần thêm giới hạn theo loại tác vụ hoặc chi phí thực.

**“Tăng heap/pool là sửa được.”** Mở rộng tài nguyên có thể có ích khi có nhu cầu hợp lệ, nhưng không thay thế giới hạn, backpressure và thuật toán phù hợp.

**“Có rate limiter nghĩa là hết nguy cơ DoS.”** Rate limiter chỉ là một lớp phòng vệ. Request đơn lẻ vẫn có thể rất đắt, các nguồn dữ liệu khác vẫn có thể vượt giới hạn, và bản thân bộ đếm quota cũng cần được giới hạn tài nguyên.

## 18. Tình huống vận dụng

### Tình huống A: API tìm kiếm với phân trang tùy ý

API `/products/search?pageSize=...` gọi database rồi đưa toàn bộ kết quả vào `List` trước khi chọn trang. Khi client yêu cầu 100.000 kết quả, bộ nhớ tăng mạnh.

Hãy xác định ranh giới đang thiếu, nơi cần đặt `MAX_PAGE_SIZE` và vì sao `LIMIT` tại database tốt hơn việc lấy hết rồi cắt danh sách. Cần test những giá trị ngay dưới, đúng và trên ngưỡng nào?

### Tình huống B: nhập dữ liệu JSON lồng sâu

Một endpoint chỉ kiểm tra request tối đa 1 MB nhưng parser có thể phải tạo cây JSON rất sâu. Khi dữ liệu bất thường được gửi liên tiếp, CPU tăng và thời gian phản hồi cao.

Hãy đề xuất thêm các giới hạn nào ở parser, cách giới hạn công việc đồng thời và những chỉ số giúp biết parser đang chiếm quá nhiều CPU. Không cần tạo dữ liệu phá hoại để trả lời.

### Tình huống C: hàng đợi gửi email

Dịch vụ gửi email xử lý 100 tác vụ/phút nhưng một chiến dịch đưa vào 20.000 tác vụ cùng lúc. Queue trong bộ nhớ không giới hạn; tiến trình có nguy cơ hết RAM.

Hãy thiết kế giới hạn số tác vụ chờ, khả năng lưu bền vững và cách phản hồi khi không thể nhận thêm. Nếu người gửi thử lại, cần cơ chế gì để tránh tạo trùng tác vụ?

### Tình huống D: giới hạn theo tenant

Một khách hàng doanh nghiệp hợp lệ xuất nhiều báo cáo lớn cùng lúc, chiếm hết worker và làm các tenant khác chờ.

Hãy phân biệt giới hạn theo tenant với giới hạn tổng hệ thống, đề xuất một cơ chế chia khả năng xử lý phù hợp và cách đo tác động khi áp dụng giới hạn mới.

### Tình huống E: upload file nén

Hệ thống giới hạn archive tải lên ở 10 MB nhưng không kiểm soát kích thước sau giải nén, số mục hoặc dung lượng tệp tạm.

Hãy nêu những ngân sách cần thêm và vị trí kiểm tra trước khi dùng dữ liệu để xử lý nghiệp vụ. Nếu quá giới hạn ở giữa quá trình, hệ thống phải giải phóng những tài nguyên nào?

### Tình huống F: báo giá giao hàng chậm

Một API gọi hãng vận chuyển với timeout 15 giây, trong khi toàn bộ request tương tác chỉ được phép phản hồi trong 3 giây. Client thử lại ngay khi không nhận được kết quả.

Hãy xác định vấn đề về deadline, số lời gọi đồng thời và retry. Nếu kết quả của thao tác bên ngoài có tác dụng phụ, bạn sẽ phân biệt “timeout” và “chưa thực hiện” thế nào?

Với mỗi tình huống, trả lời theo trình tự: **đầu vào/luồng tải → tài nguyên có thể cạn → giới hạn đặt ở đâu → hành vi khi vượt giới hạn → kiểm thử/metric chứng minh hiệu quả**.

## 19. Ghi nhớ

Một hệ thống đáng tin cậy cần biết **mỗi đầu vào có thể tiêu thụ bao nhiêu tài nguyên** và **hệ thống làm gì khi không thể tiếp nhận thêm công việc**.

- Giới hạn kích thước dữ liệu **trước và trong khi đọc**, đồng thời kiểm soát dữ liệu sau giải nén và độ phức tạp parser.
- Áp giới hạn số phần tử ở nghiệp vụ và tầng truy vấn, không chỉ cắt kết quả sau khi đã tải hết.
- Phân biệt **rate**, **concurrency**, **queue capacity**, **timeout** và **deadline**; mỗi cơ chế bảo vệ một chiều khác nhau.
- Dùng quota, admission control, backpressure và retry có ngân sách để ngăn tải lớn làm suy giảm toàn hệ thống.
- Từ chối quá tải với hợp đồng rõ ràng; không bỏ qua kiểm tra bảo mật quan trọng hoặc trả dữ liệu giả thành công.
- Quan sát mức sử dụng tài nguyên và kiểm thử các ranh giới bằng dữ liệu có kiểm soát.
- Chọn ngưỡng từ yêu cầu thực và sức chứa đã đo, tránh sao chép con số minh họa thành chính sách sản xuất.

Mã nguồn có giới hạn tài nguyên rõ ràng giúp người bảo trì hiểu chi phí của một thao tác, dự đoán hành vi khi quá tải và bảo vệ khả năng phục vụ của hệ thống ngay cả khi gặp dữ liệu hoặc tốc độ yêu cầu bất thường.
