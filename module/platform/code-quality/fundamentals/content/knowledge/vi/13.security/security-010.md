# Phân biệt mẫu mã nguy hiểm với rủi ro thực tế của hệ thống

Khi công cụ phân tích mã báo “có nguy cơ SQL injection”, “sử dụng thuật toán mã hóa yếu” hay “đầu vào không được kiểm tra”, nhóm phát triển cần xem đó là tín hiệu quan trọng. Tuy nhiên, **một mẫu mã đáng ngờ không tự chứng minh một lỗ hổng đang có thể bị khai thác**, và ngược lại, **một hệ thống có thể gặp rủi ro nghiêm trọng dù mã vượt qua các bộ quy tắc kiểm tra tĩnh**.

Bài học thuộc chương **Bảo mật** của **CODE_QUALITY_FUNDAMENTALS**. Theo mục tiêu của module, chất lượng mã cần hỗ trợ hệ thống **đáng tin cậy khi vận hành, dễ hiểu khi đọc và dễ thay đổi khi yêu cầu phát triển**. Nội dung này hướng dẫn phân biệt *dấu hiệu trong mã*, *điểm yếu bảo mật*, *đường khai thác khả dĩ*, *tác động nghiệp vụ* và *mức rủi ro trong môi trường thực tế*.

## 1. Bốn cấp độ cần phân biệt

### 1.1. Mẫu mã nguy hiểm hoặc đáng ngờ

**Mẫu mã nguy hiểm** là cấu trúc lập trình thường liên quan đến một nhóm lỗi bảo mật, chẳng hạn:

- Nối chuỗi để tạo câu SQL từ dữ liệu không đáng tin.
- Đưa dữ liệu người dùng vào lệnh hệ điều hành.
- Dùng một hàm sinh số ngẫu nhiên không phù hợp để tạo token bảo mật.
- Ghi token, mật khẩu hoặc dữ liệu nhạy cảm vào log.
- Tắt bước kiểm tra chứng chỉ TLS.
- Tải tài nguyên từ URL do người dùng kiểm soát mà không giới hạn đích.
- Lựa chọn đối tượng chỉ dựa vào ID gửi từ client mà không kiểm tra quyền.

Mẫu này có thể được nhận diện qua review, static application security testing (**SAST**), linter bảo mật hoặc kiểm tra kiến trúc. Đây là **tín hiệu cần điều tra**, vì công cụ thường không nắm đầy đủ dữ liệu nghiệp vụ, cấu hình triển khai, nguồn gốc dữ liệu và các cơ chế bảo vệ bên ngoài đoạn mã.

### 1.2. Điểm yếu và lỗ hổng

**Điểm yếu (weakness)** là thiếu sót trong thiết kế, mã hoặc vận hành có thể dẫn đến vấn đề bảo mật. Nhiều nhóm điểm yếu được đặt tên trong danh mục CWE, ví dụ kiểu lỗi xử lý dữ liệu đầu vào không an toàn.

**Lỗ hổng (vulnerability)** là điểm yếu cụ thể trong bối cảnh hệ thống, có thể tạo điều kiện vi phạm một yêu cầu bảo mật. Muốn kết luận một cảnh báo là lỗ hổng có thể khai thác, cần kiểm tra nguồn dữ liệu, đường đi tới thao tác nguy hiểm, điều kiện thực thi và các biện pháp kiểm soát hiệu quả.

Ví dụ, biểu thức SQL được ghép từ một hằng số lập trình viên chọn nội bộ có tính chất khác với biểu thức SQL ghép từ tham số trong request Internet. Dù vậy, cách nối chuỗi vẫn có thể **làm tăng rủi ro khi code được thay đổi** hoặc khi một nguồn tưởng đáng tin bị thay thế bằng dữ liệu không đáng tin.

### 1.3. Đường khai thác và điều kiện tiên quyết

Để một điểm yếu gây hậu quả, thường phải có **đường tác động** từ tác nhân đến tài sản cần bảo vệ:

1. Tác nhân có thể tiếp cận một điểm vào.
2. Tác nhân kiểm soát được dữ liệu hoặc hành động liên quan.
3. Dữ liệu đi qua các bước xử lý và đến thao tác nhạy cảm.
4. Các kiểm soát trên đường đi không chặn được hành vi gây hại.
5. Kết quả có thể vi phạm tính bảo mật, toàn vẹn hoặc sẵn sàng của hệ thống.

Có lỗ hổng không cần dữ liệu đầu vào trực tiếp, ví dụ cấu hình công khai nhầm một tài nguyên nhạy cảm. Vì thế, không nên thu hẹp mọi đánh giá về mô hình “tham số người dùng → hàm nguy hiểm”.

### 1.4. Rủi ro thực tế

**Rủi ro bảo mật** xem xét điều có thể xảy ra trong bối cảnh cụ thể và hậu quả đối với hệ thống. Hai điểm yếu cùng loại có thể có mức ưu tiên khác nhau vì:

- Độ phơi lộ: Internet công khai, mạng đối tác, mạng nội bộ hay tác vụ chỉ chạy trên máy cô lập.
- Quyền cần có: khách chưa đăng nhập, tài khoản thường, quản trị viên hay tác nhân có quyền vận hành.
- Dữ liệu và tài sản: dữ liệu giả, dữ liệu khách hàng, tiền, bí mật, khả năng sửa cấu hình hoặc điều khiển hạ tầng.
- Điều kiện khai thác: đơn giản, cần nhiều bước, cần trạng thái hiếm hoặc cần tương tác của người dùng.
- Kiểm soát đã có: xác thực, phân quyền, cách ly mạng, giới hạn quyền, kiểm tra hợp đồng, giám sát và khả năng phục hồi.
- Quy mô tác động: một bản ghi, một tenant, toàn bộ cơ sở dữ liệu hoặc hệ thống liên quan.
- Khả năng phát hiện và ứng phó: có log, cảnh báo, thu hồi quyền, khôi phục hoặc đối soát hay không.

**Kết luận:** cảnh báo mã nguồn là một đầu mối; xác định rủi ro là hoạt động nối đầu mối đó với **mô hình đe dọa, đường đi thực tế và tác động nghiệp vụ**.

## 2. Không đánh đồng các thuật ngữ

| Thuật ngữ | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Security code smell / pattern** | Cấu trúc mã nào thường dẫn tới lỗi? | Ghép tham số vào chuỗi SQL |
| **Weakness** | Lỗi thiết kế hoặc cách sử dụng API nào đang tồn tại? | Dữ liệu không đáng tin bị xử lý như cú pháp SQL |
| **Vulnerability** | Trong hệ thống này, điểm yếu có tạo điều kiện vi phạm an toàn không? | Endpoint truy cập được có thể đưa đầu vào đến câu SQL không an toàn |
| **Exploitability** | Tác nhân nào, từ đâu và với điều kiện gì có thể lợi dụng? | Người dùng bên ngoài kiểm soát tham số được dùng trực tiếp trong truy vấn |
| **Impact** | Nếu thành công thì hậu quả là gì? | Đọc hoặc sửa dữ liệu vượt quyền, gián đoạn dịch vụ |
| **Risk** | Mức đáng lo và mức ưu tiên xử lý ở bối cảnh hiện tại là bao nhiêu? | Phụ thuộc tác động, khả năng xảy ra và kiểm soát thực tế |
| **Finding** | Một kết quả kiểm tra/report đang nói gì? | Cảnh báo từ SAST hoặc phát hiện trong review |
| **Incident** | Sự kiện vi phạm bảo mật đã xảy ra hoặc đang được xử lý? | Có bằng chứng truy cập dữ liệu trái phép |

Một **finding** không mặc nhiên là sự cố, cũng không thể loại bỏ chỉ vì chưa có bằng chứng sự cố. “Chưa thấy ai khai thác” không phải bằng chứng rằng điểm yếu không thể bị khai thác.

## 3. Đánh giá theo ranh giới tin cậy, không chỉ theo dòng mã

Một **ranh giới tin cậy (trust boundary)** phân chia các vùng có mức tin cậy, quyền hoặc trách nhiệm khác nhau. Ví dụ: trình duyệt và backend, dịch vụ và database, ứng dụng và hệ điều hành, một tenant và tenant khác, hệ thống nội bộ và API đối tác.

~~~mermaid
flowchart LR
    U[Người dùng / hệ thống bên ngoài] --> A[API nhận dữ liệu]
    A --> V[Xác thực và phân quyền]
    V --> B[Logic ứng dụng]
    B --> Q[Thao tác nhạy cảm: DB / tệp / API]
    Q --> D[Dữ liệu và tài nguyên được bảo vệ]
~~~

Trên sơ đồ, chỉ có các hộp “xác thực” và “phân quyền” không bảo đảm chúng làm đúng nhiệm vụ. Cần xem **điều kiện thực tế**: quyền có được kiểm tra theo đúng bản ghi, hành động, tenant và trạng thái nghiệp vụ hay không?

Một cách phân tích thường dùng là **source → propagation → sink**:

- **Source:** nơi dữ liệu hoặc hành động có thể bị điều khiển, ví dụ query parameter, HTTP header, message, file upload hoặc dữ liệu từ đối tác.
- **Propagation:** dữ liệu được truyền, nối, giải mã, ánh xạ hoặc lưu thế nào; có bị biến đổi làm mất ý nghĩa bảo vệ không?
- **Sink:** điểm mà dữ liệu trở thành lệnh, truy vấn, đường dẫn, URL, nội dung HTML hoặc quyết định phân quyền.
- **Control:** kiểm soát phù hợp tại ranh giới, như parameterized query, xác minh quyền trên đối tượng, giới hạn điểm đến hoặc encoding cho đúng ngữ cảnh đầu ra.

**Điểm cần chú ý:** cùng một giá trị có thể an toàn ở một sink nhưng nguy hiểm ở sink khác. Ví dụ, kiểm tra “chỉ gồm chữ số” có thể phù hợp với một số ID, nhưng không thay thế kiểm tra quyền; HTML escaping không phải cơ chế bảo vệ SQL; mã hóa URL không tự làm an toàn việc truy cập tài nguyên mạng.

## 4. Ví dụ Java: nhìn thấy mẫu SQL nguy hiểm, xác định đường tác động

Giả sử một API cho phép tìm tài khoản theo email. Một phiên bản triển khai ghép email vào câu truy vấn:

~~~java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

final class UnsafeAccountLookup {
    static boolean exists(Connection connection, String email)
            throws SQLException {

        String sql = "SELECT id FROM accounts WHERE email = '"
                + email + "'";

        try (Statement statement = connection.createStatement();
             ResultSet results = statement.executeQuery(sql)) {
            return results.next();
        }
    }
}
~~~

**Mẫu đáng ngờ:** dữ liệu **email** được chèn vào **cú pháp SQL** bằng nối chuỗi. Nếu email đến từ yêu cầu của người dùng và không có cách xử lý tách dữ liệu khỏi cú pháp, có khả năng phát sinh lỗi **SQL injection**.

Để kết luận trong hệ thống cụ thể, cần làm rõ:

1. Ai cung cấp email? Có từ form hoặc API công khai không?
2. Luồng gọi hàm có thật sự được dùng ở môi trường đang xem xét không?
3. Có bước nào biến email thành một giá trị đã được xác nhận theo hợp đồng không?
4. Tài khoản kết nối DB có những quyền gì? Chỉ đọc một bảng hay có thể sửa nhiều dữ liệu?
5. Có kiểm soát nào khác không, và nó bảo vệ được chính trường hợp này theo cách nào?
6. Lỗi có thể ảnh hưởng đến thông tin của một người hay nhiều người?
7. Khi sau này nguồn email thay đổi, giả thiết an toàn hiện tại có còn đúng không?

Không nên coi **kiểm tra định dạng email** là cơ chế phòng vệ chính cho SQL injection. Giải pháp bền vững là **tách tham số dữ liệu khỏi cú pháp SQL**.

### 4.1. Dùng PreparedStatement đúng chỗ

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

final class AccountLookup {
    static boolean exists(Connection connection, String email)
            throws SQLException {

        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("email is required");
        }

        String sql = "SELECT id FROM accounts WHERE email = ?";
        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, email);

            try (ResultSet results = statement.executeQuery()) {
                return results.next();
            }
        }
    }
}
~~~

Dấu **?** được bind với giá trị email qua API có hỗ trợ tham số. Cơ sở dữ liệu không cần diễn giải chuỗi email như một phần cú pháp SQL.

Cần lưu ý:

- **PreparedStatement** bảo vệ phần **giá trị tham số** được bind đúng cách, không tự bảo vệ các đoạn SQL động vẫn được ghép chuỗi.
- Tên bảng, tên cột, chiều sắp xếp hoặc mệnh đề SQL cấu trúc thường không thể bind như một giá trị; phải lựa chọn từ **danh sách cho phép** đã xác định trên server.
- Truy vấn an toàn trước injection **không tự bảo đảm phân quyền**, tính đúng nghiệp vụ hay quyền DB tối thiểu.
- Tài khoản DB của ứng dụng nên có quyền phù hợp với chức năng, nhằm giảm tác động nếu một lớp bảo vệ thất bại.

### 4.2. Hai bối cảnh với cùng mẫu mã

| Bối cảnh | Nhận định phù hợp |
| --- | --- |
| Email nhận trực tiếp từ endpoint công khai, chèn vào câu SQL có quyền đọc dữ liệu thật | Có đường đầu vào đến sink đáng ngờ; cần ưu tiên xác minh và xử lý, không chờ xảy ra sự cố |
| Đoạn mã chỉ nằm trong PoC chưa triển khai, giá trị hiện lấy từ hằng số thử nghiệm | Có mẫu nguy hiểm và nguy cơ lan sang cách dùng không an toàn; tác động hiện tại có thể thấp hơn, nhưng phải sửa trước khi đưa vào môi trường có dữ liệu thật |
| Dữ liệu chỉ đến từ một dịch vụ nội bộ | **Không tự động an toàn**: dịch vụ nội bộ có thể nhận dữ liệu bên ngoài, bị cấu hình sai hoặc thay đổi hợp đồng |
| Truy vấn dùng parameter binding và chỉ chấp nhận một trong vài cột được server ánh xạ cố định | Khả năng bị injection theo đường này thấp hơn; vẫn cần kiểm thử hợp đồng và phân quyền |

Việc phân loại theo bối cảnh không phải giấy phép giữ lại kiểu xử lý không an toàn. Một cách sửa đơn giản, ít ảnh hưởng và loại bỏ cả rủi ro tương lai thường đáng thực hiện ngay.

## 5. Ví dụ ngược lại: mã SQL an toàn nhưng kiểm soát quyền không an toàn

Giả sử API nhận **orderId** từ URL. Ứng dụng dùng PreparedStatement, vì vậy không có mẫu ghép chuỗi SQL nguy hiểm:

~~~java
String sql = "SELECT id, owner_id, total_vnd "
        + "FROM orders WHERE id = ?";
~~~

Nếu API cho phép một người đã đăng nhập thay **orderId** để đọc đơn hàng của người khác, hệ thống có thể gặp **lỗi phân quyền theo đối tượng**. Trường hợp này thường được gọi là broken object-level authorization (BOLA) hoặc IDOR tùy ngữ cảnh.

Câu truy vấn an toàn trước injection **không trả lời câu hỏi “người gọi có được xem đơn này không?”**. Xác thực chỉ chứng minh danh tính của người dùng; nó không chứng minh quyền xem **mọi** bản ghi.

Nếu nghiệp vụ là “mỗi người chỉ xem đơn thuộc sở hữu của chính mình”, có thể kết hợp phạm vi chủ sở hữu vào câu truy vấn:

~~~java
String sql = "SELECT id, owner_id, total_vnd "
        + "FROM orders WHERE id = ? AND owner_id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, orderId);
    statement.setLong(2, authenticatedUserId);

    try (ResultSet result = statement.executeQuery()) {
        if (!result.next()) {
            // Không trả dữ liệu của đơn hàng nằm ngoài quyền truy cập.
            return null;
        }
        // Ánh xạ các trường cần thiết sang DTO phù hợp.
    }
}
~~~

**Giả thiết bắt buộc:** **authenticatedUserId** phải được lấy từ ngữ cảnh xác thực đáng tin ở server, không phải từ tham số mà client tự khai. Quy tắc phân quyền thật có thể còn gồm tenant, vai trò hỗ trợ, trạng thái đơn, quyền được ủy quyền hoặc quyền xem có thời hạn. Không được suy diễn rằng **owner_id** là chính sách đầy đủ cho mọi dự án.

Điểm chính: **không có cảnh báo injection vẫn có thể có lỗ hổng nghiêm trọng**, vì rủi ro đến từ việc không áp dụng đúng chính sách truy cập theo nghiệp vụ.

## 6. Nhiều mẫu bảo mật không thể chấm mức rủi ro từ tên API

| Mẫu thường bị cảnh báo | Khi nào đáng lo | Điều phải kiểm tra trước khi kết luận |
| --- | --- | --- |
| Nối dữ liệu vào SQL | Dữ liệu không đáng tin có thể trở thành cú pháp truy vấn | Nguồn dữ liệu, parameter binding thực tế, quyền DB, khả năng truy cập |
| Tạo lệnh hệ điều hành động | Dữ liệu tác nhân có thể thay đổi lệnh hoặc đối số theo cách nguy hiểm | Có gọi shell không, đầu vào nào kiểm soát được, quyền tiến trình và mục đích thao tác |
| Tạo đường dẫn từ đầu vào | Có thể đọc/ghi ra ngoài vùng cho phép | Đường dẫn gốc, chuẩn hóa, symlink, quyền hệ điều hành, giới hạn kiểu tệp |
| Tải URL do bên ngoài cung cấp | Hệ thống có thể gọi tài nguyên nội bộ không được phép (SSRF) | Đích cho phép, DNS/redirect, chính sách egress, mạng riêng, quyền dịch vụ |
| Ghi request/response vào log | Bí mật hoặc dữ liệu nhạy cảm bị ghi và lưu trữ | Trường dữ liệu thực, người có quyền đọc log, thời gian lưu, cách che dữ liệu |
| Tắt kiểm tra chứng chỉ TLS | Mất bảo đảm xác thực máy chủ trong đường truyền | Có nằm ở luồng thật không, môi trường triển khai, mạng có thể bị can thiệp |
| Sinh token bằng công cụ ngẫu nhiên không thích hợp | Token bảo mật có thể đoán được | Token dùng để làm gì, yêu cầu entropy, nguồn ngẫu nhiên và tuổi thọ |
| Dùng hàm băm nhanh cho mật khẩu | Mật khẩu lưu có thể bị dò dễ hơn khi dữ liệu bị lộ | Mục đích hash, thuật toán lưu mật khẩu, salt, cấu hình work factor, quy trình nâng cấp |
| Deserialization dữ liệu không tin cậy | Đối tượng được tạo hoặc hành vi không mong đợi | Định dạng, kiểu được phép, thư viện và cấu hình, ranh giới tin cậy |
| Thiếu kiểm tra quyền đối tượng | Người dùng xem/sửa dữ liệu nằm ngoài phạm vi cho phép | Quy tắc ownership/tenant, auth context đáng tin, kiểm tra tại điểm truy cập |

Đây là bảng **định hướng điều tra**, không phải danh sách cho phép dùng hay cấm tuyệt đối mọi API.

### 6.1. Đường dẫn tệp: normalize chưa giải quyết toàn bộ vấn đề

Ví dụ, hệ thống lưu báo cáo theo tên tệp người dùng gửi. Đặt đường dẫn gốc và kiểm tra đường dẫn sau chuẩn hóa là một phần phòng vệ:

~~~java
import java.nio.file.Path;

final class ReportPathPolicy {
    static Path resolveInside(Path reportRoot, String filename) {
        if (filename == null || filename.isBlank()) {
            throw new IllegalArgumentException("filename is required");
        }

        Path root = reportRoot.toAbsolutePath().normalize();
        Path target = root.resolve(filename).normalize();

        if (!target.startsWith(root)) {
            throw new IllegalArgumentException(
                    "Path escapes the report directory");
        }
        return target;
    }
}
~~~

**Giới hạn quan trọng:** phương thức này kiểm tra đường dẫn theo cấu trúc cú pháp. Nó **chưa bảo vệ hoàn toàn trước symlink, thay đổi tệp giữa lúc kiểm tra và sử dụng (TOCTOU), hay quyền truy cập sai của tiến trình**. Với hệ thống ghi/đọc tệp từ đầu vào không tin cậy, cần chính sách tên tệp cho phép, quyền tối thiểu, cơ chế mở tệp an toàn theo nền tảng và thiết kế tránh phụ thuộc vào đường dẫn tùy ý khi khả thi.

Nếu báo cáo chỉ có các mã đã biết do hệ thống sinh, phương án tốt hơn có thể là ánh xạ **reportId → tên tệp server tự tạo**, thay vì chấp nhận một đường dẫn đầy đủ từ client.

### 6.2. Đầu ra log: hữu ích cho vận hành nhưng có thể làm lộ dữ liệu

~~~java
// Không nên ghi toàn bộ header Authorization hoặc payload nhạy cảm.
logger.info("checkoutFailed requestId={} errorType={}",
        requestId, errorCategory);
~~~

Bản ghi có chọn lọc giúp chẩn đoán mà không cần lưu token hoặc dữ liệu thanh toán. Tuy nhiên, cả **requestId** cũng có thể chứa thông tin nhạy cảm nếu cách sinh hoặc quy tắc lưu trữ không phù hợp. Cần có chính sách dữ liệu, giới hạn quyền đọc log, thời gian lưu và cơ chế xóa/che dữ liệu theo yêu cầu.

### 6.3. Hàm băm và ngữ cảnh sử dụng

Cảnh báo “dùng hàm băm nhanh” cần phân biệt hai nhu cầu:

- Tính checksum không dùng để bảo vệ trước đối thủ, hoặc lập chỉ mục/băm dữ liệu thông thường: các tiêu chí chủ yếu là hiệu năng, độ ổn định và phát hiện lỗi theo mục đích.
- **Lưu mật khẩu:** cần dùng thuật toán chuyên dụng có khả năng làm chậm việc thử đoán mật khẩu, chẳng hạn Argon2id, scrypt, bcrypt hoặc PBKDF2 với cấu hình được lựa chọn theo môi trường và chính sách bảo mật.

Việc dùng SHA-256 cho checksum không đồng nghĩa hệ thống có lỗ hổng lưu mật khẩu; ngược lại, dùng hash nhanh trực tiếp để lưu mật khẩu không trở nên an toàn chỉ vì đầu vào được giữ bí mật trước khi lưu. Phải xác định **tài sản và mục đích bảo vệ** trước khi kết luận.

## 7. Rủi ro phụ thuộc vào môi trường và quyền hạn

Giả sử công cụ SAST báo hai đoạn mã cùng dùng một API dễ gây lỗi. Muốn ưu tiên sửa, không thể chỉ nhìn tên hàm:

| Câu hỏi | Trường hợp A: script thử nghiệm | Trường hợp B: API sản xuất |
| --- | --- | --- |
| Có được triển khai không? | Chỉ chạy trên máy dev cô lập | Chạy thường xuyên ở môi trường phục vụ người dùng |
| Dữ liệu xử lý | Dữ liệu giả | Dữ liệu đơn hàng và khách hàng thật |
| Ai có thể đưa đầu vào? | Tác giả tự tạo tập dữ liệu | Người dùng hoặc hệ thống ngoài có thể kiểm soát một phần |
| Quyền thực thi | Tài khoản thử nghiệm giới hạn | Tài khoản dịch vụ có quyền đọc/ghi nghiệp vụ |
| Phạm vi ảnh hưởng | Kết quả thử nghiệm | Nhiều khách hàng hoặc tài nguyên quan trọng |
| Cách xử lý | Sửa hoặc loại bỏ trước khi tái sử dụng; ghi giới hạn | Ưu tiên xác minh đường khai thác, kiểm soát rủi ro và sửa mã |

**Script nội bộ không mặc nhiên an toàn.** Một script chỉ do hai quản trị viên chạy nhưng có quyền xóa kho dữ liệu sản xuất có thể có hậu quả rất lớn. Mức phơi lộ thấp chỉ là một yếu tố; quyền cao và tác động nặng vẫn có thể tạo rủi ro đáng ưu tiên.

Bên cạnh đó, môi trường đang xét có thể thay đổi: một PoC hôm nay trở thành công cụ nội bộ ngày mai, rồi được đưa vào workflow sản xuất. Cần ghi **điều kiện phải đánh giá lại** khi quyền, nguồn dữ liệu, người dùng hoặc phạm vi triển khai thay đổi.

## 8. Mô hình đe dọa giúp định nghĩa rủi ro thực tế

**Threat modeling** không nhất thiết là tài liệu lớn. Với một luồng nghiệp vụ, có thể bắt đầu bằng các câu hỏi:

1. **Tài sản cần bảo vệ:** thông tin cá nhân, bí mật, số dư, dữ liệu đơn hàng, tính toàn vẹn báo cáo, tính sẵn sàng?
2. **Tác nhân và khả năng:** khách chưa đăng nhập, tài khoản hợp lệ, đối tác, nhân viên, tiến trình bị chiếm quyền, lỗi cấu hình?
3. **Điểm vào và ranh giới:** API, thông điệp, file, callback, dữ liệu trong DB, quy trình triển khai?
4. **Hành động nhạy cảm:** đọc hoặc sửa bản ghi, xuất dữ liệu, gửi tiền, truy cập mạng nội bộ, thực thi tác vụ?
5. **Kiểm soát hiện có:** xác thực, phân quyền theo đối tượng, tách tenant, tham số truy vấn, sandbox, hạn mức, giám sát?
6. **Hệ quả nếu kiểm soát sai:** một bản ghi sai, nhiều tài khoản bị lộ, mất khả năng phục hồi, gián đoạn dài?
7. **Giả thiết còn thiếu:** ai xác minh được kiểm soát thực sự có hiệu lực trong môi trường chạy?

Ví dụ với chức năng xuất hóa đơn: mục tiêu không chỉ là “SQL không bị injection”. Nó còn phải bảo đảm **người gọi chỉ xuất hóa đơn họ có quyền xem**, tệp được lưu đúng không gian/tenant, đường dẫn tải xuống không bị lộ và dữ liệu nhạy cảm không bị ghi log trái phép.

Một **lớp kiểm soát tốt** có thể giảm rủi ro nhưng không nên được dùng làm lý do bỏ qua lỗi gốc khi có thể sửa. Ví dụ, WAF hoặc kiểm tra đầu vào ở gateway có thể giúp giảm bề mặt tấn công, nhưng không thay thế parameter binding và phân quyền đúng trong ứng dụng.

## 9. Phương pháp đánh giá một finding có hệ thống

### Bước 1 — Xác nhận chính xác cảnh báo

Ghi vị trí mã, dữ liệu/cấu hình liên quan, quy tắc công cụ, phiên bản analyzer và loại hành vi nguy hiểm được cho là có thể xảy ra. Đừng chỉ giữ tiêu đề “High Severity” mà không đọc đường phân tích.

### Bước 2 — Tìm đường từ điểm vào tới thao tác nhạy cảm

Xem dữ liệu có thể bị tác nhân kiểm soát hay không, có đi tới sink không và các bước biến đổi có làm thay đổi tính an toàn không. Nếu cảnh báo chỉ dựa trên một chuỗi ký tự nhưng không có đường đi khả thi, cần ghi lại lý do.

### Bước 3 — Xác định điều kiện thực thi

Đoạn mã có được gọi trong production không? Có feature flag, vai trò hoặc điều kiện dữ liệu nào ảnh hưởng? Việc kiểm soát bằng quyền có đủ chặt và được kiểm tra ở server không?

### Bước 4 — Mô tả hậu quả và phạm vi ảnh hưởng

Kết luận phải gắn với tài sản và quyền thật: đọc dữ liệu của người khác, sửa đơn, tạo giao dịch không hợp lệ, làm hệ thống ngừng phục vụ hoặc lộ token. Tránh ghi mơ hồ “ảnh hưởng bảo mật” khi chưa làm rõ ảnh hưởng gì.

### Bước 5 — Đánh giá kiểm soát hiện tại

Kiểm tra từ cấu hình và hành vi thực tế: quyền DB, phân quyền endpoint, mức cô lập tenant, network policy, validation/encoding, cơ chế ghi log và giám sát. Một kiểm soát trên giấy nhưng không được áp dụng vào đường đi nguy hiểm không được coi là biện pháp bảo vệ có hiệu lực.

### Bước 6 — Phân loại kết quả

| Trạng thái | Khi nào có thể dùng | Điều cần ghi |
| --- | --- | --- |
| **Vulnerability confirmed** | Có bằng chứng đủ mạnh về điểm yếu cụ thể trong bối cảnh hệ thống | Đường tác động, điều kiện tiên quyết, hậu quả, phạm vi và biện pháp xử lý |
| **Potential vulnerability** | Có điểm yếu khả dĩ nhưng thiếu một vài dữ kiện quan trọng | Giả thiết đang chờ xác minh, chủ sở hữu và cách kiểm tra |
| **False positive** | Có bằng chứng đáng tin rằng quy tắc báo sai đối với trường hợp này | Vì sao đường khai thác không tồn tại hoặc sink được bảo vệ |
| **Accepted risk** | Chủ sở hữu có thẩm quyền đã chấp nhận rủi ro còn lại theo quy trình | Lý do, giới hạn, biện pháp bù trừ, hạn xem lại và người phê duyệt |
| **Mitigated/fixed** | Lỗi đã được xử lý và kiểm chứng theo phạm vi đã xác định | Thay đổi, test bảo vệ và bằng chứng triển khai nếu cần |

Không nên dùng “false positive” để chỉ mọi việc chưa đủ thời gian điều tra. **Chưa xác minh** và **đã chứng minh không có rủi ro theo đường cảnh báo** là hai trạng thái khác nhau.

### Bước 7 — Xếp ưu tiên dựa trên rủi ro còn lại

Có thể xem xét đồng thời mức ảnh hưởng, điều kiện/khả năng bị khai thác, độ phơi lộ, kiểm soát có hiệu lực và khả năng khôi phục. Những hệ thống có chính sách định lượng có thể dùng phương pháp chấm điểm nhất quán, nhưng không nên coi phép nhân vài số cảm tính là kết luận chắc chắn.

Nếu cần ghi **CVSS**, hãy hiểu đó là khung mô tả mức nghiêm trọng kỹ thuật theo các thông số được xác định; **điểm CVSS không thay thế đánh giá tác động nghiệp vụ, mức phơi lộ và biện pháp giảm thiểu cụ thể**. Một lỗ hổng có điểm kỹ thuật tương tự có thể tạo mức ưu tiên sửa khác nhau ở hai hệ thống.

### Bước 8 — Sửa và xác nhận bằng bằng chứng đúng loại

Phòng vệ thường cần kết hợp:

- **Sửa nguyên nhân gốc:** parameterized query, kiểm tra quyền theo đối tượng, giới hạn đích kết nối, xử lý dữ liệu đầu ra đúng ngữ cảnh, thay cơ chế token không an toàn.
- **Giảm quyền và bề mặt tác động:** least privilege, tách tài khoản, hạn chế endpoint, network segmentation, giới hạn tài nguyên.
- **Kiểm thử hồi quy bảo mật:** kiểm tra trường hợp được phép/bị từ chối, dữ liệu biên, quyền khác nhau, dữ liệu không đáng tin và hành vi lỗi.
- **Xác minh ngoài mã:** cấu hình triển khai, bí mật, kiểm soát quyền, quyền truy cập log và giám sát.

Nếu chỉ sửa code nhưng thay đổi chưa được triển khai tới môi trường ảnh hưởng, không nên tuyên bố rủi ro thực tế đã được loại bỏ.

## 10. Bằng chứng bảo mật cần tương xứng với kết luận

| Câu hỏi | Bằng chứng hữu ích | Giới hạn |
| --- | --- | --- |
| Có mẫu mã nguy hiểm? | Review mã hoặc SAST có chỉ rõ dữ liệu và sink | Có thể có false positive/negative |
| Đường đầu vào đến sink có thật? | Data-flow review, trace có kiểm soát, kiểm thử tích hợp | Có thể thiếu đường đi hiếm hoặc cấu hình khác |
| Kiểm tra quyền có đúng? | Unit/integration test với nhiều user, tenant, vai trò | Test giả lập không chứng minh mọi cấu hình production |
| Cơ chế mã hóa/khóa có đúng? | Review cấu hình và API, kiểm thử tính năng theo hợp đồng | Không tự chứng minh không có lộ khóa ở môi trường |
| Không còn lỗi sau khi sửa? | Regression test + kiểm tra bản build/triển khai | Chưa bao quát mọi biến thể hoặc thay đổi tương lai |
| Rủi ro còn lại chấp nhận được? | Threat model, mức ảnh hưởng, kiểm soát, quyết định người phụ trách | Là đánh giá tại thời điểm và bối cảnh xác định |

**Cần phân biệt việc “test không thất bại” với “đã có bằng chứng không thể khai thác”.** Một kiểm thử chỉ dùng tài khoản quản trị không đủ xác nhận người dùng thường không đọc được dữ liệu ngoài phạm vi. Một bài test SQL với đầu vào an toàn không chứng minh đường SQL động không bị tác động bởi dữ liệu không tin cậy.

Nếu kiểm tra hành vi khai thác, chỉ thực hiện trong **môi trường và phạm vi được phép**, dùng dữ liệu kiểm thử an toàn và không làm ảnh hưởng hệ thống bên ngoài. Đối với rủi ro cao, nên phối hợp với người phụ trách bảo mật để chọn mức kiểm chứng phù hợp.

## 11. Hai tình huống để thấy “mẫu” và “rủi ro” khác nhau

### 11.1. Cảnh báo nguy hiểm nhưng môi trường hiện chưa tạo đường tác động rõ

Một phương thức có chuỗi truy vấn SQL ghép từ các hằng số do nhóm phát triển định nghĩa, chỉ chạy trong tool thử nghiệm trên dữ liệu giả. SAST báo vì phát hiện **String concatenation**.

Nhận định phù hợp:

- **Mẫu mã cần xem xét:** có.
- **Đường dữ liệu không đáng tin tới cú pháp SQL:** chưa thấy trong phạm vi hiện tại, cần kiểm tra thực tế.
- **Phạm vi tài sản:** môi trường và dữ liệu thử nghiệm theo giả thiết đã xác nhận.
- **Hậu quả hiện tại:** có thể thấp hơn hệ thống production, nhưng không bằng 0 nếu tool dùng quyền cao hoặc kết nối nhầm môi trường.
- **Xử lý:** cân nhắc đổi sang truy vấn có tham số, tránh tái sử dụng sai; ghi điều kiện cần rà soát khi nguồn dữ liệu hoặc môi trường thay đổi.

Không nên bỏ qua phát hiện bằng câu “đây chỉ là tool nội bộ” nếu chưa xác minh tài khoản, dữ liệu và môi trường đang dùng.

### 11.2. Mã không có mẫu nguy hiểm rõ ràng nhưng rủi ro cao

Một endpoint dùng ORM chuẩn, không nối SQL, không chứa mật khẩu trong mã và đã bật HTTPS. Tuy nhiên, việc tải tài liệu chỉ kiểm tra **người dùng đã đăng nhập**, không kiểm tra tài liệu có thuộc về người đó hoặc được chia sẻ hợp lệ hay không.

Nhận định phù hợp:

- **Mẫu bị SAST gắn cờ:** có thể không.
- **Điểm yếu:** thiếu phân quyền theo đối tượng ở ranh giới dữ liệu.
- **Đường tác động:** tài khoản hợp lệ thay đổi mã tài liệu trong request.
- **Hậu quả:** có thể lộ tài liệu của người dùng hoặc tenant khác.
- **Xử lý:** áp dụng chính sách phân quyền đúng ở server, kiểm tra ở điểm đọc và ở mọi đường truy cập khác; bổ sung test với hai danh tính, hai nhóm dữ liệu và cả ca bị từ chối.

Đây là lý do review bảo mật phải xét **ngữ nghĩa nghiệp vụ và danh tính**, không chỉ các hàm API thường được coi là nguy hiểm.

## 12. Bài tập phân loại

### Bài tập A — Cảnh báo về SQL động

Một công cụ báo “SQL constructed from strings”. Đoạn truy vấn dùng tên cột được chọn từ enum do server định nghĩa và giá trị đầu vào được bind qua PreparedStatement.

**Câu hỏi:** có thể kết luận SQL injection ngay không?

**Gợi ý:** chưa thể kết luận từ tên cảnh báo. Cần xem chuỗi tên cột có hoàn toàn đến từ danh sách cố định hay bị tác nhân điều khiển, việc bind giá trị có đúng không và những đoạn truy vấn còn lại có chứa dữ liệu không đáng tin không. Nếu đã kiểm chứng chỉ có tên cột từ allowlist, nên ghi lý do và kiểm thử hợp đồng; không xem cảnh báo đơn lẻ là bằng chứng khai thác.

### Bài tập B — Random dùng cho hai mục đích

Một dịch vụ dùng công cụ sinh số ngẫu nhiên thông thường để chia người dùng vào hai giao diện A/B; một dịch vụ khác dùng cùng loại công cụ để sinh mã khôi phục mật khẩu.

**Câu hỏi:** hai tình huống có cùng hậu quả không?

**Gợi ý:** không. Chia A/B phục vụ mục tiêu phân phối hoặc thử nghiệm có yêu cầu khác với token xác thực. Mã khôi phục mật khẩu cần nguồn ngẫu nhiên bảo mật, thời hạn hiệu lực, giới hạn thử, bảo vệ dữ liệu lưu và quy trình thu hồi. Đánh giá phải dựa vào **mục đích của giá trị**, không chỉ tên class.

### Bài tập C — API nội bộ có quyền quá rộng

Một endpoint chỉ nhận request từ mạng nội bộ nhưng dùng tài khoản DB có quyền sửa mọi bảng và ghi trạng thái theo ID do caller gửi.

**Câu hỏi:** có thể đánh giá rủi ro thấp vì “không public” không?

**Gợi ý:** mạng nội bộ giảm một số đường tiếp cận nhưng không thay thế xác thực, phân quyền, giới hạn quyền DB hoặc kiểm tra ID. Một tài khoản nội bộ bị chiếm quyền hoặc một hệ thống gọi khác bị lỗi vẫn có thể tạo tác động lớn. Cần xác minh ranh giới và thu hẹp đặc quyền.

### Bài tập D — Đã sửa code nhưng vẫn còn nguy cơ

Nhóm thay truy vấn ghép chuỗi bằng PreparedStatement. Tuy nhiên, một phiên bản cũ vẫn chạy trên job theo lịch ở một môi trường khác.

**Câu hỏi:** có thể đóng finding “fixed” cho toàn hệ thống chưa?

**Gợi ý:** chỉ có thể xác nhận **mã nguồn nhánh mới đã sửa**. Cần rà soát phiên bản triển khai và phạm vi ảnh hưởng, dừng/nâng cấp job cũ, kiểm chứng trạng thái chạy và theo dõi dấu hiệu bất thường trước khi kết luận mọi đường liên quan đã được xử lý.

### Bài tập E — Cảnh báo logger không đủ ngữ cảnh

SAST báo logger nhận trực tiếp một biến chuỗi. Đó có thể là **correlationId do server sinh** hoặc **header Authorization** lấy nguyên từ HTTP request.

**Câu hỏi:** cần tìm bằng chứng gì?

**Gợi ý:** xác định nguồn và tính chất dữ liệu, chính sách cho phép ghi log, khả năng chứa bí mật, quyền xem và thời gian lưu log. Hai chuỗi dùng cùng hàm logger nhưng khác mức độ rủi ro. Ngay cả correlationId cũng cần được thiết kế để không lộ dữ liệu nhạy cảm.

## 13. Những ngộ nhận thường gặp

**“SAST báo High tức là chắc chắn bị khai thác được.”** Không đúng. SAST phát hiện mẫu hoặc luồng dữ liệu theo khả năng phân tích; cần kiểm tra điều kiện, quyền và tác động thật. Tuy vậy, cảnh báo nghiêm trọng không nên bị trì hoãn vô hạn vì thiếu bằng chứng khai thác.

**“Không có cảnh báo thì đã an toàn.”** Sai. Thiếu phân quyền, logic nghiệp vụ sai, cấu hình công khai, vấn đề quyền sở hữu dữ liệu và hành vi theo thời gian có thể không bị nhận ra qua static rules.

**“Dữ liệu nội bộ đều đáng tin.”** Không. Dữ liệu từ database, message broker hay service khác có thể có nguồn gốc từ người dùng, từ phiên bản cũ, từ quy trình nhập liệu hoặc từ tài khoản bị xâm nhập.

**“Chỉ cần validate đầu vào là xong mọi lỗ hổng.”** Không. Parameter binding, output encoding, quyền theo đối tượng, xác thực máy chủ, phân tách tenant và cơ chế retry an toàn giải quyết những vấn đề khác nhau.

**“Có WAF nên không cần sửa query nguy hiểm.”** Không. WAF có thể là biện pháp giảm thiểu bổ sung; nó không thay thế cách xử lý dữ liệu đúng tại sink, cũng không bảo đảm bảo vệ mọi đường truy cập.

**“Điểm CVSS thấp nghĩa là luôn có thể bỏ qua.”** Không. Rủi ro với một hệ thống có dữ liệu trọng yếu hoặc nhiều phụ thuộc nghiệp vụ có thể khác đánh giá kỹ thuật nền tảng; cũng phải xem khả năng khai thác và các kiểm soát có hiệu lực.

**“Cần chứng minh bằng cách khai thác production.”** Không. Có thể dùng phân tích luồng dữ liệu, hợp đồng, test an toàn ở môi trường được phép và review cấu hình. Không nên gây tác động không cần thiết để xác nhận một rủi ro đã có đủ bằng chứng.

**“Không thể khai thác hôm nay thì không có việc phải làm.”** Không hẳn. Mẫu nguy hiểm có thể gây khó bảo trì và trở thành lỗ hổng khi nguồn dữ liệu, quyền hoặc phạm vi triển khai đổi. Nên sửa nguyên nhân gốc hoặc ghi rõ điều kiện xem lại.

**“Bảo mật tốt thì mã chắc dễ bảo trì.”** Không mặc nhiên. Một cơ chế phòng vệ dàn trải, lặp quy tắc quyền ở nhiều nơi có thể khó thay đổi và dễ sửa thiếu. Nên đặt kiểm soát tại ranh giới rõ ràng, ghi hợp đồng và viết test phù hợp.

## 14. Checklist review: từ mã đáng ngờ tới rủi ro có căn cứ

Trước khi ưu tiên hoặc đóng một cảnh báo, hãy trả lời:

1. **Mẫu gì?** Quy tắc nào báo, loại thao tác nhạy cảm là gì?
2. **Nguồn nào?** Ai kiểm soát dữ liệu hoặc hành động đưa vào đường xử lý?
3. **Đường đi nào?** Có đường khả thi từ điểm vào tới sink, có điều kiện hoặc trạng thái đặc biệt không?
4. **Ranh giới nào?** Dữ liệu có đi qua vùng quyền khác nhau, tenant khác nhau hoặc thành phần ngoài không?
5. **Quy tắc bảo mật nào?** Tính bí mật, toàn vẹn, sẵn sàng hay yêu cầu phân quyền cụ thể nào phải giữ?
6. **Tài sản gì?** Dữ liệu, tiền, bí mật, năng lực thực thi hoặc hoạt động nghiệp vụ nào bị ảnh hưởng?
7. **Kiểm soát có hiệu lực?** Đã kiểm tra chính sách và triển khai thật, không chỉ nhìn tên lớp/hàm?
8. **Phạm vi và khả năng?** Điều kiện tiên quyết, người có thể tiếp cận, số đối tượng và quy mô hệ quả?
9. **Bằng chứng nào?** Mã, test, luồng dữ liệu, cấu hình, số liệu quan sát và độ chắc chắn của kết luận?
10. **Hành động và chủ sở hữu?** Sửa nguyên nhân gốc, giảm quyền, test hồi quy, triển khai và đánh giá rủi ro còn lại?
11. **Khi nào xem lại?** Quyền, dữ liệu, nguồn đầu vào, phụ thuộc, phiên bản hoặc mục đích sử dụng thay đổi có kích hoạt rà soát không?

Một ghi nhận hữu ích có thể dùng cấu trúc **Phát hiện → Bối cảnh → Đường tác động → Tài sản và hậu quả → Kiểm soát → Mức chắc chắn → Phương án xử lý → Bằng chứng xác nhận**. Cấu trúc này giúp nhóm tránh hai sai lầm đối lập: sửa hàng loạt theo nhãn cảnh báo mà không hiểu hệ thống, hoặc gạt bỏ điểm yếu chỉ vì chưa thấy sự cố.

## 15. Kết luận

**Mẫu mã nguy hiểm là dấu hiệu để đặt câu hỏi; rủi ro thực tế là kết luận về hệ thống, quyền, dữ liệu và tác động trong một bối cảnh xác định.** Nhận diện mẫu bằng công cụ rất hữu ích, nhưng cần bổ sung phân tích luồng dữ liệu, mô hình đe dọa, kiểm tra hợp đồng và kiểm thử hành vi bảo mật để biết điều gì thật sự cần được bảo vệ.

Trong **CODE_QUALITY_FUNDAMENTALS**, cách tiếp cận này khiến mã không chỉ **ít mẫu nguy hiểm hơn**, mà còn **đáng tin cậy hơn trước hành vi ngoài dự kiến, dễ hiểu hơn về ranh giới trách nhiệm và dễ thay đổi hơn khi môi trường hoặc mối đe dọa thay đổi**. Bảo mật hiệu quả là bảo vệ đúng tài sản bằng đúng kiểm soát, dựa trên bằng chứng thay vì chỉ một điểm số hay một cảnh báo tự động.
