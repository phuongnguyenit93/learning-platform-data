# Giới hạn kích thước thuộc tính, số thuộc tính và tổng dung lượng phiên

Spring Session cho phép nhiều instance của ứng dụng Spring cùng đọc và ghi một phiên làm việc thông qua kho dữ liệu dùng chung như Redis hoặc JDBC. Vì dữ liệu phiên được lưu ngoài bộ nhớ của từng instance, kích thước phiên ảnh hưởng trực tiếp đến dung lượng kho lưu trữ, thời gian đọc ghi, lưu lượng mạng và khả năng mở rộng của ứng dụng.

Spring Session cung cấp mô hình quản lý phiên thống nhất, nhưng không đặt ra một hạn mức chung áp dụng cho mọi repository về số thuộc tính, kích thước từng thuộc tính hay tổng dung lượng một phiên. Ứng dụng cần xác định chính sách phù hợp với dữ liệu thực tế, serializer và giới hạn của Redis hoặc hệ quản trị cơ sở dữ liệu đang sử dụng.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt giới hạn số lượng thuộc tính, kích thước một thuộc tính và tổng dung lượng một phiên.
- Xác định giới hạn đến từ Spring Session, repository, cơ sở dữ liệu, Redis hay cookie.
- Thiết kế chính sách dung lượng và kiểm tra trước khi ghi thuộc tính vào HttpSession.
- Đánh giá ảnh hưởng của TTL, nhiều instance và các request đồng thời.
- Kiểm thử, giám sát và xử lý lỗi khi phiên vượt hạn mức.

## 1. Ba loại giới hạn cần quản lý

Một phiên thường chứa nhiều thuộc tính được ứng dụng đặt bằng HttpSession.setAttribute. Ví dụ, một phiên có thể lưu mã người dùng, ngôn ngữ, trạng thái quy trình và một số lựa chọn ngắn hạn. Ba hạn mức sau giải quyết ba vấn đề khác nhau:

| Hạn mức | Ý nghĩa | Rủi ro khi vượt |
|---|---|---|
| Số thuộc tính tối đa | Số tên thuộc tính ứng dụng được phép tồn tại trong một phiên | Tăng số mục phải tuần tự hóa, đọc, ghi và quản lý; tạo nhiều bản ghi nếu repository lưu từng thuộc tính thành một hàng |
| Kích thước tối đa của một thuộc tính | Số byte của một giá trị sau khi tuần tự hóa, thường tính cả tên thuộc tính trong chính sách ứng dụng | Một giá trị lớn có thể làm tăng đột biến bộ nhớ, lưu lượng mạng hoặc kích thước LOB |
| Tổng dung lượng tối đa của phiên | Tổng kích thước biểu diễn của tất cả thuộc tính trong một phiên | Một phiên đơn lẻ chiếm quá nhiều tài nguyên và làm chậm các thao tác đọc ghi |

Có thể mô hình hóa dung lượng ứng dụng cần kiểm soát như sau:

\[
S_{\text{app}} = \sum_{i=1}^{N} \left(B_{\text{name},i} + B_{\text{value},i}\right)
\]

Trong đó:

- \(N\) là số thuộc tính ứng dụng trong phiên.
- \(B_{\text{name},i}\) là số byte của tên thuộc tính theo cách mã hóa được chọn.
- \(B_{\text{value},i}\) là số byte của giá trị sau khi dùng serializer của repository.

Đây là kích thước biểu diễn ở cấp ứng dụng, không phải tổng bộ nhớ vật lý mà Redis hoặc database tiêu thụ. Kho lưu trữ còn có metadata, cấu trúc dữ liệu, chỉ mục, chi phí cấp phát và các bản sao. Vì vậy, cần chừa khoảng dự phòng khi đặt ngưỡng.

Không nên lấy kích thước đối tượng trong heap Java làm số đo duy nhất. Một đối tượng có thể chiếm ít bộ nhớ trong JVM nhưng tạo ra payload lớn sau tuần tự hóa; ngược lại, serializer có thể nén hoặc biểu diễn dữ liệu khác với cấu trúc đối tượng ban đầu. Chuỗi tiếng Việt, emoji và dữ liệu đa byte cũng khiến số ký tự khác số byte.

## 2. Giới hạn nằm ở lớp nào?

### 2.1. API HttpSession và Spring Session

API Servlet HttpSession cho phép thêm, đọc, thay thế và xóa thuộc tính. API này không định nghĩa một quota chung cho số thuộc tính hay tổng số byte của phiên. Spring Session thay thế cách lưu trữ phiên mặc định bằng repository, nhưng không tự áp dụng một bộ giới hạn dung lượng giống nhau cho mọi repository.

Do đó, không nên giả định chỉ cần bật Spring Session là ứng dụng đã được bảo vệ trước một thuộc tính rất lớn hoặc một phiên chứa hàng trăm thuộc tính. Chính sách phải được thực thi ở tầng ứng dụng hoặc tại một lớp lưu trữ tùy chỉnh có khả năng kiểm soát thao tác ghi.

### 2.2. Redis

Spring Session Data Redis lưu dữ liệu phiên trong Redis. Với repository Redis thông dụng, metadata và thuộc tính phiên được lưu trong cấu trúc hash; giá trị thuộc tính được tuần tự hóa trước khi gửi tới Redis. Tên khóa, tên trường, payload, metadata và cấu trúc nội bộ đều góp phần tạo nên dung lượng thực tế.

Redis có các giới hạn kỹ thuật và cấu hình bộ nhớ ở cấp máy chủ, nhưng đó không phải quota riêng cho từng phiên của ứng dụng. Cấu hình maxmemory quản lý ngân sách bộ nhớ của Redis nói chung. Nếu một phiên quá lớn, nó có thể góp phần làm Redis chạm ngưỡng bộ nhớ, gây eviction hoặc khiến thao tác ghi thất bại tùy chính sách vận hành.

Khi dùng Redis, hãy đo payload bằng chính serializer mà Spring Session Redis đang sử dụng. Nếu thay serializer, thay đổi định dạng JSON, kiểu dữ liệu hoặc cách lưu metadata, kết quả đo và dữ liệu hiện có có thể thay đổi. Các instance đang chạy đồng thời phải tương thích với cùng định dạng tuần tự hóa.

### 2.3. JDBC

Spring Session JDBC thường lưu metadata phiên trong bảng SPRING_SESSION và các thuộc tính trong bảng SPRING_SESSION_ATTRIBUTES. Schema chuẩn có cột ATTRIBUTE_NAME với độ dài khai báo hữu hạn, thường là VARCHAR(200), và cột ATTRIBUTE_BYTES dùng kiểu dữ liệu nhị phân phù hợp với hệ quản trị cơ sở dữ liệu.

Giới hạn thực tế phụ thuộc schema đã triển khai, hệ quản trị cơ sở dữ liệu, kiểu LOB hoặc BLOB, giới hạn hàng, giới hạn packet, transaction và cấu hình driver. Nếu đổi schema, phải bảo đảm các instance cùng phiên bản hiểu được cấu trúc mới. Không nên tự tăng kích thước cột mà chưa đánh giá migration, chỉ mục và khả năng tương thích.

Với JDBC, số lượng thuộc tính lớn cũng có thể tạo ra nhiều hàng cho một phiên. Vì vậy, giới hạn số thuộc tính có ích ngay cả khi từng giá trị nhỏ và cột dữ liệu nhị phân còn đủ chỗ.

### 2.4. Cookie và giới hạn header HTTP

Trong cấu hình Spring Session lưu phiên phía máy chủ, cookie thông thường chỉ mang session ID để trình duyệt gửi lại ở các request tiếp theo. Nội dung thuộc tính được lưu trong Redis hoặc JDBC, không được nhét toàn bộ vào cookie. Vì thế, giới hạn kích thước cookie không phải giới hạn tổng dung lượng của phiên phía máy chủ.

Nhiều trình duyệt có giới hạn kích thước cookie vào khoảng 4 KiB cho mỗi cookie, nhưng con số cụ thể phụ thuộc trình duyệt và môi trường. Nếu cookie chứa session ID, chữ ký hoặc dữ liệu bổ sung quá lớn, request có thể gặp lỗi do giới hạn cookie hoặc header tại trình duyệt, proxy hay máy chủ, chẳng hạn 400 hoặc 431. Nếu ứng dụng tự thiết kế cơ chế lưu toàn bộ trạng thái trong cookie, đó là một mô hình khác và phải đánh giá riêng giới hạn cookie, mã hóa và bảo mật.

## 3. Đặt chính sách dung lượng cho ứng dụng

Hãy bắt đầu từ dữ liệu ứng dụng thực sự cần lưu trong phiên. Ví dụ cấu hình dưới đây chỉ minh họa một chính sách nội bộ; các tên dưới app.session.limits là thuộc tính do ứng dụng tự định nghĩa, không phải thuộc tính chuẩn của Spring Boot:

~~~yaml
app:
  session:
    limits:
      max-attributes: 32
      max-attribute-bytes: 16384
      max-session-bytes: 65536

spring:
  session:
    timeout: 30m
    redis:
      namespace: portal:sessions
~~~

Trong ví dụ, ứng dụng cho phép tối đa 32 thuộc tính, mỗi thuộc tính có tối đa 16 KiB và tổng phần dữ liệu thuộc tính có tối đa 64 KiB. Đây không phải giá trị mặc định hoặc khuyến nghị bắt buộc của Spring Session. Hãy điều chỉnh theo payload đo được, số phiên đồng thời, ngân sách Redis hoặc database và yêu cầu độ trễ.

Ba hạn mức bổ trợ cho nhau. Chỉ giới hạn tổng dung lượng vẫn cho phép một phiên có rất nhiều thuộc tính nhỏ, làm tăng chi phí quản lý. Chỉ giới hạn số thuộc tính vẫn cho phép một thuộc tính chứa cả một danh sách lớn. Chỉ giới hạn từng thuộc tính vẫn cho phép nhiều giá trị lớn cộng lại thành một phiên quá nặng.

Nên xác định rõ chính sách xử lý khi vượt ngưỡng:

1. Từ chối ghi và trả về lỗi nghiệp vụ có thể xử lý được.
2. Nếu nghiệp vụ cho phép, thay dữ liệu lớn bằng một mã tham chiếu tới database hoặc object storage.
3. Xóa thuộc tính cũ khi trạng thái nghiệp vụ không còn cần thiết.
4. Không âm thầm cắt ngắn payload hoặc bỏ một phần dữ liệu, vì việc đó có thể làm hỏng trạng thái nghiệp vụ.

## 4. Đo payload bằng serializer của repository

Kích thước cần kiểm tra là kích thước sau tuần tự hóa. Hãy tạo một bộ đo dùng chung và cấu hình nó bằng serializer thực tế của repository. Với Spring Session Redis, nếu ứng dụng đã cấu hình bean serializer có tên springSessionDefaultRedisSerializer, có thể tạo adapter như sau:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.data.redis.serializer.RedisSerializer;

@Bean
SessionAttributeSizer sessionAttributeSizer(
        @Qualifier("springSessionDefaultRedisSerializer")
        RedisSerializer<Object> serializer) {
    return (name, value) -> {
        byte[] payload = serializer.serialize(value);
        int nameBytes = name.getBytes(StandardCharsets.UTF_8).length;
        return nameBytes + (payload == null ? 0 : payload.length);
    };
}
~~~

Đoạn adapter trên chỉ phù hợp khi serializer được inject chính là serializer mà repository dùng để lưu thuộc tính. Nếu ứng dụng dùng JDBC hoặc một serializer khác, hãy viết adapter tương ứng với converter hoặc serializer thực tế của repository. Một phép đo bằng JSON tùy ý không thể đại diện chính xác cho payload nếu repository đang lưu bằng định dạng khác.

Giao diện bộ đo có thể giữ độc lập với repository:

~~~java
@FunctionalInterface
public interface SessionAttributeSizer {
    int serializedBytes(String name, Object value);
}
~~~

Kích thước tính trong ví dụ gồm byte của tên thuộc tính và payload đã tuần tự hóa. Nó chưa gồm metadata, overhead của Redis hash, overhead hàng và chỉ mục của JDBC. Dùng nó làm ngưỡng chính sách ở cấp ứng dụng và chừa dự phòng cho phần overhead của kho lưu trữ.

## 5. Kiểm tra trước khi ghi thuộc tính

Nên gom các thao tác ghi phiên vào một service để các luồng nghiệp vụ dùng cùng chính sách. Ví dụ dưới đây minh họa cách kiểm tra số thuộc tính, kích thước thuộc tính mới và tổng dung lượng trước khi gọi HttpSession.setAttribute:

~~~java
import java.util.Enumeration;
import java.util.Objects;

import jakarta.servlet.http.HttpSession;

public final class SessionBudget {
    private final SessionAttributeSizer sizer;
    private final int maxAttributes;
    private final int maxAttributeBytes;
    private final long maxSessionBytes;

    public SessionBudget(
            SessionAttributeSizer sizer,
            int maxAttributes,
            int maxAttributeBytes,
            long maxSessionBytes) {
        this.sizer = Objects.requireNonNull(sizer);
        if (maxAttributes < 1 || maxAttributeBytes < 0
                || maxSessionBytes < 0) {
            throw new IllegalArgumentException("Invalid session limits");
        }
        this.maxAttributes = maxAttributes;
        this.maxAttributeBytes = maxAttributeBytes;
        this.maxSessionBytes = maxSessionBytes;
    }

    public void setAttribute(
            HttpSession session, String name, Object value) {
        Objects.requireNonNull(session);
        Objects.requireNonNull(name);

        // Theo Servlet API, giá trị null tương đương xóa thuộc tính.
        if (value == null) {
            session.removeAttribute(name);
            return;
        }

        int newBytes = sizer.serializedBytes(name, value);
        if (newBytes > maxAttributeBytes) {
            throw new IllegalArgumentException(
                    "Session attribute exceeds its size limit: " + name);
        }

        int otherAttributeCount = 0;
        long otherAttributeBytes = 0;
        Enumeration<String> names = session.getAttributeNames();
        while (names.hasMoreElements()) {
            String oldName = names.nextElement();
            // Thay thế thuộc tính hiện có không làm tăng số lượng.
            if (oldName.equals(name)) {
                continue;
            }
            Object oldValue = session.getAttribute(oldName);
            if (oldValue != null) {
                otherAttributeCount++;
                otherAttributeBytes +=
                        sizer.serializedBytes(oldName, oldValue);
            }
        }

        if (otherAttributeCount + 1 > maxAttributes) {
            throw new IllegalArgumentException(
                    "Session has too many attributes");
        }
        if (otherAttributeBytes + newBytes > maxSessionBytes) {
            throw new IllegalArgumentException(
                    "Session exceeds its total size limit");
        }

        session.setAttribute(name, value);
    }
}
~~~

Ví dụ này minh họa chính sách ở cấp ứng dụng, không phải tính năng quota tích hợp sẵn trong Spring Session. Với Spring Boot 2 dùng Servlet API cũ, thay import jakarta.servlet bằng javax.servlet. Trong ứng dụng thực tế, nên dùng một exception nghiệp vụ riêng và chuyển nó thành phản hồi phù hợp với giao thức của ứng dụng.

Khi kiểm tra, cần xử lý đúng ba trường hợp:

- Thêm tên mới: số thuộc tính tăng một.
- Ghi đè tên đã tồn tại: thay kích thước cũ bằng kích thước mới, không tăng số thuộc tính.
- Ghi giá trị null hoặc gọi removeAttribute: thuộc tính bị loại khỏi số lượng và tổng dung lượng.

Việc duyệt tất cả thuộc tính trước mỗi lần ghi có chi phí tăng theo số thuộc tính. Cách này phù hợp khi giới hạn số thuộc tính nhỏ. Nếu phiên có nhiều thuộc tính hoặc ghi rất thường xuyên, hãy cân nhắc cấu trúc dữ liệu phiên gọn hơn hoặc một bộ quản lý trạng thái chuyên biệt.

Quan trọng: kiểm tra rồi ghi là hai thao tác riêng. Hai request đồng thời trên cùng một phiên có thể cùng đọc tổng dung lượng cũ, cùng vượt qua kiểm tra và sau đó cùng ghi, khiến tổng cuối cùng vượt hạn mức. Đồng bộ bằng synchronized trong một instance không bảo vệ được các instance khác. Nếu hạn mức là ràng buộc cứng, cần tuần tự hóa cập nhật theo session ID bằng cơ chế khóa phân tán có thời hạn hoặc triển khai thao tác kiểm tra và ghi nguyên tử tại tầng repository. Cơ chế khóa phải có timeout, xử lý lỗi và giải phóng an toàn để tránh làm treo phiên.

Để kiểm soát đầy đủ, hãy bảo đảm các đường ghi thuộc tính trong ứng dụng đều đi qua service hoặc một lớp bao có kiểm soát. Nếu code cũ gọi trực tiếp HttpSession.setAttribute ở nhiều nơi, cần rà soát các điểm ghi và chuyển chúng về một đường dùng chung. Một helper chỉ được một vài controller sử dụng sẽ không tạo thành quota toàn ứng dụng.

## 6. Thiết kế dữ liệu phiên gọn

Biện pháp hiệu quả nhất thường là giảm dữ liệu cần lưu trong phiên. Phiên phù hợp với trạng thái ngắn hạn, nhỏ và cần dùng lại giữa các request, ví dụ:

- ID người dùng hoặc ID của đối tượng nghiệp vụ.
- Mã ngôn ngữ, múi giờ hoặc lựa chọn giao diện.
- Một vài cờ trạng thái và mốc thời gian.
- ID quy trình đang thực hiện hoặc một mã tham chiếu tới bản nháp được lưu ở nơi khác.

Tránh lưu toàn bộ JPA entity, danh sách kết quả tìm kiếm lớn, nội dung file, ảnh, request/response, đối tượng chứa quan hệ vòng, hoặc bản sao lớn của hồ sơ người dùng. Những đối tượng này vừa làm phiên nặng, vừa có thể kéo theo dữ liệu cũ và phụ thuộc vào phiên bản class khi triển khai phiên bản ứng dụng mới.

Với giỏ hàng lớn, bản nháp nhiều trường hoặc quy trình kéo dài, hãy lưu trạng thái chính trong database hoặc kho phù hợp và chỉ giữ mã tham chiếu trong phiên. Khi request cần dữ liệu, ứng dụng đọc trạng thái theo ID và kiểm tra quyền truy cập. Cách này giúp phiên nhỏ, dữ liệu nghiệp vụ có thể truy vấn và cập nhật độc lập, đồng thời tránh truyền cả payload lớn qua Redis hoặc JDBC ở mỗi lần lưu phiên.

Chỉ lưu đối tượng có thể tuần tự hóa theo serializer đang dùng. Nếu serializer dùng Java serialization, kiểu dữ liệu cần đáp ứng yêu cầu của serializer đó. Nếu dùng JSON, cần bảo đảm kiểu dữ liệu, constructor, thông tin type và chính sách tương thích khi nâng cấp ứng dụng.

## 7. Quan hệ giữa dung lượng, TTL và nhiều instance

TTL hay maxInactiveInterval xác định khoảng thời gian phiên được giữ khi không hoạt động. TTL không giới hạn số byte của một phiên. Một phiên nhỏ tồn tại lâu vẫn góp phần vào tổng dung lượng; một phiên lớn có TTL ngắn vẫn có thể gây đột biến bộ nhớ hoặc lưu lượng trong thời gian tồn tại.

Có thể ước lượng sơ bộ ngân sách lưu trữ bằng:

\[
M \approx C \times \overline{S} \times F
\]

Trong đó \(C\) là số phiên đồng thời, \(\overline{S}\) là dung lượng trung bình mỗi phiên và \(F\) là hệ số dự phòng cho metadata, cấu trúc lưu trữ, bản sao và overhead vận hành. Đây là ước lượng để lập ngân sách; hãy dùng số đo Redis hoặc database để xác nhận.

Với Spring Session dùng repository chia sẻ, mọi instance có thể truy cập cùng phiên. Một instance không nên giả định dữ liệu đang có trong bộ nhớ cục bộ là nguồn chính xác để tính quota. Khi triển khai nhiều instance:

- Dùng cùng chính sách giới hạn và định dạng serializer trên tất cả instance.
- Đảm bảo phiên bản ứng dụng mới có thể đọc dữ liệu do phiên bản cũ ghi trong giai đoạn rolling deployment.
- Kiểm tra lỗi tuần tự hóa và giải tuần tự hóa sau mỗi lần đổi class hoặc serializer.
- Kiểm tra request đồng thời, cập nhật ghi đè và xóa phiên.

Khi người dùng đăng xuất, ứng dụng nên vô hiệu hóa phiên bằng HttpSession.invalidate hoặc cơ chế logout tương ứng. Spring Session có các sự kiện vòng đời như SessionDeletedEvent và SessionExpiredEvent; với Redis, việc nhận sự kiện hết hạn phụ thuộc cấu hình keyspace notifications và repository. Có thể dùng sự kiện để cập nhật số liệu hoặc dọn dữ liệu phụ trợ, nhưng không nên phụ thuộc vào sự kiện bất đồng bộ để ngăn một lần ghi vượt quota.

Việc xóa dữ liệu vật lý có thể diễn ra theo cơ chế hết hạn hoặc dọn dẹp của repository. Vì vậy, TTL và invalidate xác định vòng đời logic của phiên, còn thời điểm tài nguyên vật lý được thu hồi phụ thuộc kho lưu trữ và cấu hình vận hành.

## 8. Kiểm thử giới hạn và tình huống vận hành

Kiểm thử đơn vị cho bộ quản lý dung lượng nên bao phủ các biên:

| Tình huống | Kết quả mong đợi |
|---|---|
| Ghi thuộc tính có kích thước đúng bằng giới hạn | Được chấp nhận |
| Ghi thuộc tính lớn hơn giới hạn một byte | Bị từ chối trước khi ghi |
| Thêm thuộc tính khi số lượng đang ở ngưỡng tối đa | Bị từ chối |
| Thay thế thuộc tính đã có | Không tăng số lượng; tính lại tổng dung lượng |
| Xóa thuộc tính | Số lượng và tổng dung lượng giảm |
| Dữ liệu Unicode hoặc emoji | Đo theo byte sau mã hóa, không theo số ký tự |
| Giá trị không thể tuần tự hóa | Báo lỗi rõ ràng, không ghi trạng thái một phần |
| Hai request cùng cập nhật một phiên | Kiểm tra hành vi tranh chấp và cơ chế bảo vệ quota |

Ngoài unit test, cần integration test với đúng loại repository đang triển khai:

1. Khởi động Redis hoặc database thử nghiệm cùng schema thực tế.
2. Ghi các giá trị sát ngưỡng, đọc lại từ repository và xác nhận dữ liệu giữ nguyên.
3. Khởi động hai instance ứng dụng cùng dùng repository đó; tạo phiên ở instance thứ nhất và đọc, cập nhật ở instance thứ hai.
4. Gửi request đồng thời để kiểm tra race condition khi hai request cùng thêm thuộc tính.
5. Kiểm tra timeout, logout, xóa phiên và các sự kiện vòng đời nếu ứng dụng sử dụng chúng.
6. Kiểm tra rolling deployment khi serializer hoặc class chứa thuộc tính thay đổi.

Trong môi trường vận hành, nên theo dõi số thuộc tính mỗi phiên, phân bố kích thước payload, số lần từ chối do vượt hạn mức, lỗi serializer, độ trễ đọc ghi và số phiên đang hoạt động. Với Redis, theo dõi bộ nhớ, eviction, lỗi ghi và độ trễ lệnh. Với JDBC, theo dõi kích thước bảng thuộc tính, dung lượng LOB, số hàng theo phiên, thời gian transaction và lỗi do schema hoặc giới hạn packet.

Không ghi giá trị thuộc tính, token, thông tin xác thực hoặc toàn bộ session ID vào log chỉ để đo dung lượng. Chỉ ghi metric tổng hợp, loại lỗi và định danh đã được xử lý an toàn khi thật sự cần điều tra.

## 9. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Ghi phiên thất bại khi thêm một giá trị lớn | Payload vượt giới hạn ứng dụng, giới hạn LOB hoặc giới hạn của kho lưu trữ | Đo payload bằng serializer thực tế; giảm dữ liệu hoặc lưu nội dung lớn ở nơi khác |
| Redis tăng bộ nhớ nhanh | Nhiều phiên đồng thời, phiên quá lớn, TTL dài hoặc overhead và bản sao chưa được tính | Đo phân bố kích thước, đặt quota, rà soát TTL và ngân sách bộ nhớ |
| JDBC tạo nhiều hàng cho mỗi phiên | Quá nhiều thuộc tính nhỏ | Giảm số thuộc tính, gom trạng thái liên quan thành một cấu trúc nhỏ và có phiên bản |
| Một instance đọc được phiên nhưng instance khác lỗi giải tuần tự hóa | Serializer hoặc class giữa các instance không tương thích | Đồng bộ cấu hình và triển khai chuyển đổi dữ liệu có kế hoạch |
| Cookie hoặc request bị từ chối do header quá lớn | Cookie session ID hoặc cookie bổ sung vượt giới hạn của client/proxy/server | Giảm kích thước cookie; không đưa dữ liệu phiên phía máy chủ vào cookie |
| Tổng dung lượng đôi lúc vượt ngưỡng dù đã kiểm tra | Nhiều request cùng kiểm tra và ghi trên một phiên | Tuần tự hóa cập nhật hoặc thực hiện quota nguyên tử tại repository |

Khi từ chối một lần ghi, hãy đưa ứng dụng về trạng thái nhất quán. Không bắt lỗi rồi tiếp tục xử lý như thể dữ liệu đã được lưu. Tùy nghiệp vụ, có thể yêu cầu người dùng tải lại trạng thái, lưu dữ liệu lớn vào kho riêng hoặc bắt đầu phiên mới. Lỗi lưu phiên cần được quan sát như một lỗi vận hành thực sự vì các request tiếp theo có thể đọc trạng thái cũ.

## 10. Checklist trước khi đưa lên production

- [ ] Đã xác định rõ giới hạn số thuộc tính, từng thuộc tính và tổng dung lượng.
- [ ] Bộ đo dùng đúng serializer hoặc converter của repository.
- [ ] Các đường ghi thuộc tính đều áp dụng cùng chính sách.
- [ ] Đã kiểm tra thay thế, xóa, Unicode và các trường hợp đúng biên.
- [ ] Đã đánh giá request đồng thời trên cùng session ID.
- [ ] Schema JDBC hoặc cấu hình Redis đáp ứng kích thước dự kiến và có dự phòng.
- [ ] TTL phù hợp với số phiên đồng thời và ngân sách lưu trữ.
- [ ] Các instance tương thích về serializer trong giai đoạn triển khai.
- [ ] Có metric cho kích thước phiên, lỗi ghi, lỗi serializer và dung lượng kho lưu trữ.
- [ ] Log không làm lộ dữ liệu nhạy cảm nằm trong phiên.

Giới hạn dung lượng phiên là một chính sách của ứng dụng được triển khai dựa trên đặc điểm của repository. Khi đo bằng đúng serializer, giới hạn đồng thời cả số thuộc tính, kích thước từng thuộc tính và tổng payload, đồng thời kiểm thử các request đồng thời trên nhiều instance, ứng dụng Spring Session sẽ kiểm soát được chi phí lưu trữ và giảm nguy cơ lỗi khi tải tăng.
