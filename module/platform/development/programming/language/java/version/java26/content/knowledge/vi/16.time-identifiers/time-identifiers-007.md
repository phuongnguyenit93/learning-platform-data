# Phần thời gian, tính duy nhất và mục đích dùng UUIDv7

UUIDv7 kết hợp dấu thời gian Unix theo mili giây với phần bit ngẫu nhiên trong một định danh 128 bit. Cách bố trí này làm cho UUID có xu hướng sắp xếp theo thời điểm tạo, đồng thời vẫn có không gian ngẫu nhiên lớn để giảm xác suất trùng giữa các máy phát độc lập. Từ JDK 26, Java cung cấp trực tiếp UUID.ofEpochMillis(long) để tạo UUIDv7 theo RFC 9562.

UUIDv7 phù hợp với định danh bản ghi, sự kiện, message và dữ liệu cần khả năng sắp xếp gần theo thời gian. Nó không phải bộ đếm toàn cục, không bảo đảm thứ tự tuyệt đối giữa mọi máy và không nên dùng làm bí mật xác thực. Muốn hiểu đúng giá trị của UUIDv7, cần tách ba khái niệm: timestamp được nhúng, xác suất không trùng và tính đơn điệu của thứ tự sinh.

## 1. UUIDv7 là gì?

UUID là định danh 128 bit. RFC 9562 chuẩn hóa các phiên bản UUID hiện đại, trong đó UUIDv7 sử dụng Unix timestamp theo mili giây ở phần đầu của giá trị. Các byte còn lại chứa version, variant và dữ liệu ngẫu nhiên hoặc cấu trúc bổ sung để hỗ trợ tính đơn điệu.

UUIDv7 có dạng chuỗi chuẩn 36 ký tự, gồm 32 chữ số hex và 4 dấu gạch nối:

~~~text
0195f4a8-6c20-7b31-9f2a-7d7e8c4a1023
~~~

Ví dụ trên chỉ minh họa hình dạng UUIDv7; không dùng nó như một giá trị kiểm thử có timestamp thật.

Khác với UUIDv4, vốn dùng gần như toàn bộ phần bit khả dụng cho dữ liệu ngẫu nhiên, UUIDv7 dành 48 bit đầu cho timestamp. Vì vậy, khi biểu diễn cùng thứ tự byte chuẩn, các UUID có timestamp mili giây sớm hơn thường đứng trước UUID có timestamp muộn hơn.

## 2. Cấu trúc bit của UUIDv7

UUIDv7 có 128 bit với các trường sau:

~~~text
Bit 0                                                        Bit 127
+-------------------------------+----+------------+--+-------------------------------+
| unix_ts_ms                    |ver | rand_a     |var| rand_b                        |
| 48 bit                        |4   | 12 bit     |2 | 62 bit                        |
+-------------------------------+----+------------+--+-------------------------------+
       48 bit timestamp                  74 bit còn lại cho random/counter
~~~

| Trường | Kích thước | Ý nghĩa |
|---|---:|---|
| unix_ts_ms | 48 bit | Unix timestamp tính bằng mili giây kể từ 1970-01-01T00:00:00Z, không tính leap second |
| ver | 4 bit | Giá trị 0111, nhận diện UUID version 7 |
| rand_a | 12 bit | Ngẫu nhiên hoặc một phần cấu trúc hỗ trợ đơn điệu |
| var | 2 bit | Giá trị 10, nhận diện IETF/RFC variant |
| rand_b | 62 bit | Ngẫu nhiên hoặc phần counter bổ sung |

Sau khi dành 4 bit version và 2 bit variant, UUIDv7 còn 74 bit cho dữ liệu ngẫu nhiên và/hoặc các cấu trúc tùy chọn hỗ trợ monotonicity. RFC 9562 quy định timestamp nằm trong 48 bit đầu theo thứ tự big-endian.

Điều này mang lại hai đặc điểm:

- **Sắp xếp theo thời gian ở độ phân giải mili giây:** timestamp chiếm phần quan trọng nhất của UUID.
- **Không cần máy chủ cấp ID trung tâm:** phần còn lại có entropy đủ lớn để các node độc lập tạo ID với xác suất va chạm thấp.

UUIDv7 không chứa timezone. Timestamp là số mili giây Unix UTC; chuyển sang giờ địa phương chỉ là bước hiển thị.

## 3. Tạo UUIDv7 bằng Java 26

JDK 26 bổ sung phương thức chính thức:

~~~java
public static UUID ofEpochMillis(long timestamp)
~~~

Phương thức nhận số mili giây kể từ Unix Epoch và tạo UUID version 7. Sáu byte đầu chứa timestamp; các bit version và variant được đặt theo RFC 9562; 74 bit còn lại được lấy từ bộ sinh số giả ngẫu nhiên có tính chất mật mã mạnh.

Ví dụ đơn giản:

~~~java
import java.time.Instant;
import java.util.UUID;

public class UuidV7Example {

    public static void main(String[] args) {
        long now = Instant.now().toEpochMilli();

        UUID id = UUID.ofEpochMillis(now);

        System.out.println("UUID: " + id);
        System.out.println("Version: " + id.version());
        System.out.println("Variant: " + id.variant());
    }
}
~~~

Kết quả cần có:

- id.version() trả về 7.
- id.variant() trả về 2, là IETF variant mà java.util.UUID sử dụng.
- Timestamp được truyền vào được nhúng trong 48 bit đầu.
- Phần còn lại được tạo ngẫu nhiên bằng bộ sinh mạnh về mật mã.

UUID.ofEpochMillis() không tự đọc đồng hồ hệ thống. Caller phải truyền timestamp. Cách thông thường là lấy từ Instant.now().toEpochMilli() hoặc từ một Clock được inject để dễ kiểm thử.

### Kiểm tra miền timestamp

48 bit là số nguyên không dấu. API Java nhận long nhưng chỉ chấp nhận timestamp trong khoảng:

~~~text
0 <= timestamp <= 2^48 - 1
~~~

Nếu giá trị âm hoặc lớn hơn giới hạn, phương thức ném IllegalArgumentException. Phạm vi này bao phủ nhiều thiên niên kỷ sau Unix Epoch, nên không phải giới hạn thực tế đối với ứng dụng hiện nay.

Không truyền System.nanoTime() vào ofEpochMillis(). nanoTime() là đồng hồ đo khoảng thời gian, không phải Unix timestamp. Dùng Instant.now().toEpochMilli() để tạo timestamp theo thời gian lịch.

## 4. Đọc timestamp từ UUIDv7

Không dùng UUID.timestamp() để lấy thời gian UUIDv7. Phương thức này được định nghĩa cho UUID version 1 và ném UnsupportedOperationException với các version khác.

Trong UUIDv7, timestamp nằm ở 48 bit cao nhất của getMostSignificantBits(). Có thể trích xuất như sau:

~~~java
import java.time.Instant;
import java.util.UUID;

static Instant timestampOf(UUID id) {
    if (id.version() != 7 || id.variant() != 2) {
        throw new IllegalArgumentException("Expected an IETF UUIDv7");
    }

    long epochMillis = id.getMostSignificantBits() >>> 16;
    return Instant.ofEpochMilli(epochMillis);
}
~~~

Phép dịch phải không dấu >>> 16 loại bỏ 12 bit rand_a cùng 4 bit version, giữ lại 48 bit timestamp ở dạng số dương.

Kiểm thử tạo rồi đọc lại:

~~~java
long timestamp = Instant.now().toEpochMilli();
UUID id = UUID.ofEpochMillis(timestamp);

Instant decoded = timestampOf(id);

if (decoded.toEpochMilli() != timestamp) {
    throw new AssertionError("UUID timestamp does not match input");
}
~~~

Khi nhận UUID từ hệ thống khác, kiểm tra cả version và variant trước khi diễn giải bit. UUID.fromString() chỉ phân tích cú pháp chuỗi UUID; nó không tự bảo đảm giá trị nhận vào là version 7.

## 5. Timestamp, uniqueness và monotonicity là ba khái niệm khác nhau

Các khái niệm này thường bị dùng thay thế cho nhau nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | UUIDv7 của JDK 26 |
|---|---|---|
| Timestamp | Thời điểm được mã hóa trong UUID | Có, độ phân giải mili giây |
| Uniqueness | Xác suất hai ID có cùng 128 bit | Rất cao nhờ 74 bit ngẫu nhiên; không phải bảo đảm toán học tuyệt đối |
| Monotonicity | ID sinh sau luôn lớn hơn ID sinh trước | Không được bảo đảm chỉ bằng UUID.ofEpochMillis() |

Timestamp tăng thường làm UUID tăng khi so sánh theo thứ tự byte chuẩn. Tuy nhiên, nếu nhiều UUID được tạo trong cùng một mili giây, phần timestamp giống nhau và thứ tự giữa chúng phụ thuộc vào 74 bit còn lại. JDK 26 tạo phần này bằng dữ liệu ngẫu nhiên, không phải counter tăng dần.

Ví dụ hai UUID cùng timestamp:

~~~text
0195f4a8-6c20-7b31-9f2a-7d7e8c4a1023
0195f4a8-6c20-7b31-8a11-42f0a0b1c2d3
~~~

Cả hai có thể được tạo trong cùng một mili giây. Không thể kết luận UUID nào được tạo trước chỉ bằng phần random.

Do đó, UUIDv7 cung cấp thứ tự gần theo thời gian, không tự tạo ra một thứ tự giao dịch tuyệt đối.

## 6. Vì sao UUIDv7 có xác suất trùng thấp?

Sau khi dành timestamp, version và variant, UUIDv7 có 74 bit dành cho dữ liệu ngẫu nhiên hoặc cấu trúc bổ sung. Với cách sinh ngẫu nhiên độc lập, số khả năng cho một timestamp mili giây là 2^74.

Nếu có n UUID được tạo trong cùng một mili giây và cùng miền timestamp, xác suất va chạm gần đúng theo birthday bound:

~~~text
P ≈ n(n - 1) / (2 * 2^74)
~~~

Ví dụ với một triệu UUID trong cùng một mili giây:

~~~text
P ≈ 2.65 × 10^-11
~~~

Đây là xác suất rất nhỏ, nhưng không bằng zero. Khi số ID tăng, xác suất va chạm cũng tăng theo quy luật birthday paradox.

Cần hiểu đúng phạm vi phép tính:

- Hai UUID có timestamp khác nhau thì giá trị 128 bit khác nhau vì phần timestamp đã khác.
- Rủi ro va chạm tập trung vào các UUID có cùng timestamp mili giây.
- Trong hệ thống phân tán, phải tính tổng lượng UUID có thể được sinh trên mọi node trong cùng timestamp bucket.
- Nếu thuật toán dùng counter thay cho một phần random, phải quản lý counter và overflow đúng chuẩn.

Không dùng xác suất va chạm thấp để bỏ qua unique constraint ở database. Với dữ liệu quan trọng, vẫn đặt primary key hoặc unique constraint để phát hiện và xử lý trường hợp hiếm gặp.

## 7. Vì sao UUIDv7 có thể sắp xếp gần theo thời gian?

RFC 9562 đặt timestamp ở các bit có trọng số cao nhất. Với hai UUIDv7 có timestamp mili giây khác nhau, giá trị có timestamp nhỏ hơn sẽ đứng trước khi so sánh theo thứ tự byte unsigned của biểu diễn chuẩn.

Điều này có ích trong:

- Chỉ mục B-tree của cơ sở dữ liệu.
- Log và event stream cần sắp xếp gần theo thời gian tạo.
- Phân trang theo khóa trong bảng lớn.
- Đồng bộ dữ liệu và xử lý batch.
- Truy vấn dữ liệu mới nhất theo ID khi ID được dùng làm khóa sắp xếp phù hợp.

Tuy nhiên, không nên khẳng định mọi cơ sở dữ liệu, kiểu lưu trữ hoặc collation đều sắp xếp UUID giống nhau. Hãy kiểm tra cách database so sánh kiểu UUID native, binary(16) hoặc chuỗi ký tự. Nếu lưu dưới dạng chuỗi, phải thống nhất format và collation. Nếu lưu binary, giữ đúng byte order của UUID chuẩn.

UUIDv7 cải thiện locality so với UUIDv4 trong nhiều workload chèn tăng dần theo thời gian. Nó không đảm bảo mọi truy vấn nhanh hơn: hiệu quả còn phụ thuộc index, phân bố dữ liệu, mức độ ghi đồng thời và chiến lược partitioning. Hãy đo trên workload thật.

## 8. Mục đích sử dụng phù hợp

### Khóa chính cho bản ghi mới

UUIDv7 có thể phù hợp làm primary key khi:

- Nhiều service hoặc node cần tự tạo ID mà không hỏi sequence trung tâm.
- Muốn ID có xu hướng sắp xếp theo thời gian tạo.
- Database hỗ trợ kiểu UUID hoặc lưu 16 byte nhất quán.
- Không muốn lộ một sequence số nguyên liên tục.

Ví dụ entity:

~~~java
import java.time.Instant;
import java.util.UUID;

record OrderId(UUID value) {

    static OrderId newId() {
        return new OrderId(
                UUID.ofEpochMillis(Instant.now().toEpochMilli()));
    }
}
~~~

Dùng wrapper type như OrderId để phân biệt ID của đơn hàng với ID của khách hàng hoặc sự kiện, tránh truyền nhầm UUID giữa các API.

### Event ID và message ID

UUIDv7 phù hợp cho event ID, message ID hoặc correlation record khi nhiều producer tạo dữ liệu độc lập. Timestamp hỗ trợ quan sát và sắp xếp gần theo thời gian; phần random giảm nhu cầu phối hợp giữa producer.

Tuy nhiên, không dùng UUIDv7 thay cho sequence offset của message broker. Offset thường biểu diễn thứ tự commit/append trong một partition; UUIDv7 không cung cấp semantics đó.

### Log và audit record

UUIDv7 có thể làm ID cho log event hoặc audit record để liên kết các bản ghi giữa service. Timestamp trong UUID hỗ trợ phân nhóm theo thời gian, nhưng timestamp của ID là thời điểm caller truyền vào, không nhất thiết là thời điểm transaction commit hoặc sự kiện thực sự xảy ra.

Nếu cần thời điểm nghiệp vụ chính xác, lưu một cột timestamp riêng với semantics rõ ràng như created_at hoặc committed_at. Không dùng timestamp trong UUID thay cho dữ liệu thời gian nghiệp vụ.

## 9. So sánh UUIDv7 với các version thường gặp

| Version | Cách tạo | Đặc điểm | Trường hợp dùng |
|---|---|---|---|
| UUIDv1 | Timestamp 100 ns theo Gregorian epoch, clock sequence và node | Có tính thời gian; cấu trúc node có thể tiết lộ thông tin định danh máy | Chủ yếu duy trì tương thích hệ thống cũ |
| UUIDv3 | Hash MD5 từ namespace và name | Cùng namespace/name tạo cùng ID; MD5 không phù hợp cho mục tiêu bảo mật hiện đại | Tương thích định danh xác định cũ |
| UUIDv4 | Dữ liệu ngẫu nhiên | Không chứa thời gian; có 122 bit ngẫu nhiên | ID ngẫu nhiên khi không cần sort theo thời gian |
| UUIDv5 | Hash SHA-1 từ namespace và name | Tạo ID xác định từ đầu vào; không phải ID ngẫu nhiên cho mỗi lần gọi | Định danh ổn định từ tên |
| UUIDv6 | Timestamp time-based được sắp xếp lại, cùng clock sequence/node | Cải thiện khả năng sắp xếp của UUIDv1 | Tương thích hệ thống time-based cũ |
| UUIDv7 | Unix timestamp mili giây + random/counter | Sắp xếp gần theo thời gian, entropy cao, không cần node ID | ID cho record, event và message |
| UUIDv8 | Layout tùy biến theo ứng dụng | Ý nghĩa và uniqueness phụ thuộc implementation | Giao thức tùy chỉnh có quy định riêng |

RFC 9562 khuyến nghị dùng UUIDv7 thay cho UUIDv1/UUIDv6 khi có thể. Điều này không có nghĩa phải chuyển đổi mọi UUID cũ: dữ liệu lịch sử và giao thức tương thích vẫn cần giữ nguyên cách diễn giải.

UUID.randomUUID() trong Java vẫn tạo UUIDv4. Nó không tự chuyển sang UUIDv7 khi chạy trên JDK 26. Muốn tạo v7, gọi rõ UUID.ofEpochMillis().

## 10. Không nhầm UUIDv7 với sequence tăng dần

UUIDv7 không phải auto-increment ID. Hai UUID có thể:

- Cùng timestamp nhưng random suffix theo thứ tự bất kỳ.
- Được tạo trên hai node có đồng hồ lệch nhau.
- Có timestamp nhỏ hơn ID đã tạo trước đó nếu đồng hồ hệ thống bị chỉnh lùi.
- Được ghi vào database theo thứ tự khác với thứ tự được tạo, do concurrency hoặc transaction commit.

Ví dụ: service A có đồng hồ nhanh hơn service B 200 ms. Một ID được tạo ở A có thể mang timestamp lớn hơn ID tạo sau đó ở B. Khi sắp xếp hai ID, kết quả phản ánh timestamp do mỗi node cung cấp, không phải thứ tự toàn cục của sự kiện.

Nếu cần thứ tự commit chính xác, dùng sequence/offset do nơi ghi dữ liệu quản lý, transaction timestamp hoặc cơ chế ordering của hệ thống phân tán. UUIDv7 có thể làm khóa bổ trợ, nhưng không thay thế cơ chế đồng bộ.

## 11. Tạo thứ tự tăng nghiêm ngặt trong một JVM

Nếu một ứng dụng đơn tiến trình cần thứ tự UUID tăng nghiêm ngặt, có thể cấp timestamp logic tăng dần trước khi gọi UUID.ofEpochMillis(). Ví dụ dưới đây bảo đảm timestamp được cấp bởi class này tăng nghiêm ngặt trong một JVM:

~~~java
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

public final class MonotonicUuidV7 {

    private static final long MAX_TIMESTAMP = (1L << 48) - 1;
    private static final AtomicLong LAST_MILLIS = new AtomicLong(-1);

    private MonotonicUuidV7() {}

    public static UUID next() {
        long wallClockMillis = Instant.now().toEpochMilli();

        long logicalMillis = LAST_MILLIS.updateAndGet(previous -> {
            if (previous >= MAX_TIMESTAMP) {
                throw new IllegalStateException("UUIDv7 timestamp exhausted");
            }

            long next = Math.max(wallClockMillis, previous + 1);

            if (next < 0 || next > MAX_TIMESTAMP) {
                throw new IllegalStateException("Timestamp outside UUIDv7 range");
            }

            return next;
        });

        return UUID.ofEpochMillis(logicalMillis);
    }
}
~~~

Mỗi lần gọi thành công, timestamp nhúng vào UUID lớn hơn timestamp của lần gọi trước trong cùng classloader/JVM. Vì timestamp nằm ở phần bit cao nhất, các UUID cũng tăng theo thứ tự giá trị chuẩn.

Đây là bộ cấp timestamp logic tối giản, có các giới hạn:

- Timestamp có thể chạy trước đồng hồ thật nếu tạo nhiều ID trong cùng một mili giây.
- Khi đồng hồ hệ thống bị chỉnh lùi, bộ cấp tiếp tục từ giá trị logic trước đó.
- Trạng thái AtomicLong mất khi tiến trình khởi động lại; không bảo đảm thứ tự xuyên lần restart.
- Hai JVM hoặc hai node có trạng thái độc lập; không bảo đảm thứ tự toàn cục.
- Không phù hợp nếu timestamp phải phản ánh chính xác thời điểm thực tế của từng event.

Nếu cần monotonicity qua restart hoặc trên nhiều node, cần một bộ cấp counter/clock state có đồng bộ và lưu bền vững, hoặc dùng sequence/ordering service phù hợp. RFC 9562 mô tả các phương pháp counter và cách xử lý clock rollback/overflow; không tự chế một layout UUIDv7 riêng nếu chưa xác định yêu cầu entropy và tương thích.

## 12. Đồng hồ hệ thống và clock rollback

Instant.now() lấy thời gian lịch từ clock hệ thống. Đồng hồ này có thể thay đổi do NTP, chỉnh giờ thủ công, VM migration hoặc cấu hình hệ thống. Nó không phải monotonic clock.

Các tình huống cần lưu ý:

- Nếu đồng hồ lùi, UUID mới có thể mang timestamp nhỏ hơn UUID tạo trước đó.
- Nếu đồng hồ đứng yên trong cùng mili giây, các UUID có cùng timestamp và random suffix.
- Nếu node có clock skew, thứ tự UUID giữa node không phản ánh chắc chắn thứ tự sự kiện.
- Nếu clock nhảy tiến, UUID mang timestamp tương lai so với thời điểm thực.

Với mục đích lưu trữ, đây thường là giới hạn chấp nhận được của ID có timestamp. Nếu thời gian nghiệp vụ cần chính xác, lưu timestamp riêng lấy từ nguồn thời gian đã xác định và xử lý clock synchronization theo yêu cầu hệ thống.

Không thay Instant.now() bằng System.nanoTime() để “tăng độ chính xác”. nanoTime() không có mốc Unix Epoch và không thể được diễn giải thành thời gian lịch.

## 13. Tính riêng tư và bảo mật

UUIDv7 để lộ timestamp theo mili giây ở phần đầu. Người quan sát ID có thể suy ra gần đúng thời điểm tạo và phân tích xu hướng tăng của hệ thống. Điều này có thể làm lộ:

- Thời điểm một bản ghi hoặc tài nguyên được tạo.
- Mật độ hoạt động trong một khoảng thời gian.
- Quan hệ gần nhau về thời gian giữa các ID.
- Một phần thông tin vận hành khi ID xuất hiện trong URL công khai hoặc log bên ngoài.

Phần random của JDK 26 được tạo bằng bộ sinh số giả ngẫu nhiên mạnh về mật mã, nhưng UUIDv7 vẫn không nên được dùng làm password, API key hoặc bearer token. Lý do là timestamp công khai, UUID là định danh có thể xuất hiện ở nhiều nơi và thiết kế ID không thay thế cơ chế cấp quyền.

Nếu cần token bí mật:

- Dùng token ngẫu nhiên có entropy phù hợp, không nhúng timestamp công khai.
- Lưu hash token nếu cần xác minh token ở server.
- Giới hạn thời hạn, scope và khả năng thu hồi.
- Không dùng UUID làm bằng chứng người gọi có quyền truy cập tài nguyên.

UUIDv7 cũng không mã hóa dữ liệu. Không đặt thông tin cá nhân hoặc dữ liệu nghiệp vụ vào các bit tùy biến của UUIDv8 rồi coi chúng là bí mật.

## 14. Lưu trữ và index trong database

UUID có kích thước 16 byte ở dạng nhị phân và thường được hiển thị thành chuỗi 36 ký tự. Với UUIDv7, lưu dạng native UUID hoặc 16 byte theo byte order chuẩn thường tiết kiệm hơn so với chuỗi, nếu database và driver hỗ trợ tốt.

Các điểm cần quyết định:

| Lựa chọn | Lưu ý |
|---|---|
| Kiểu UUID native | Ưu tiên khi database hỗ trợ và driver ánh xạ chuẩn |
| BINARY(16) / kiểu byte 16 | Giữ đúng byte order RFC; kiểm tra cách so sánh và serialize |
| CHAR(36) / VARCHAR(36) | Dễ đọc/debug nhưng tốn dung lượng hơn; collation phải thống nhất |
| Primary key | Kiểm tra tác động lên index, foreign key và các bảng liên quan |
| Secondary index | Đo chi phí ghi và truy vấn theo workload thật |

Do timestamp nằm ở phần đầu, UUIDv7 thường tạo vị trí insert gần cuối vùng index hiện tại hơn UUIDv4. Điều này có thể giảm random page insertion và cải thiện cache locality trong workload ghi nhiều. Mức lợi ích phụ thuộc database engine, cấu trúc index và phân bố dữ liệu.

Không dùng hàm byte-swap dành riêng cho UUIDv1 khi lưu UUIDv7. UUIDv7 đã sắp timestamp theo thứ tự byte cao trước; đổi thứ tự byte có thể phá tính sắp xếp mong muốn.

Khi phân trang, có thể dùng keyset pagination với điều kiện theo UUID nếu thứ tự database tương thích với thứ tự UUIDv7. Nếu cần sắp xếp theo thời điểm nghiệp vụ, vẫn dùng cột timestamp nghiệp vụ và thêm khóa phụ để phân định các bản ghi có cùng thời điểm.

## 15. Hỗ trợ theo phiên bản Java

| JDK | Khả năng |
|---|---|
| JDK 25 trở về trước | java.util.UUID chưa có ofEpochMillis(long) trong API chuẩn |
| JDK 26 | Có UUID.ofEpochMillis(long) để tạo UUIDv7; API chính thức, không phải preview |
| JDK 27 | Tiếp tục có UUID.ofEpochMillis(long) |

API mới được đánh dấu Since: 26. Không cần --enable-preview hoặc tùy chọn JVM đặc biệt để bật UUIDv7.

Nếu ứng dụng vẫn phải biên dịch với JDK 25 hoặc cũ hơn, có thể dùng thư viện bên ngoài có hỗ trợ RFC 9562, nhưng cần xác minh:

- Layout đúng RFC 9562.
- Timestamp là Unix epoch milliseconds ở 48 bit đầu.
- Version và variant bits được đặt đúng.
- Thuật toán random/counter và hành vi khi clock rollback.
- Khả năng tương thích giữa các service và ngôn ngữ.
- Chính sách nâng cấp thư viện và cách serialize/deserialize.

Khi baseline đã là JDK 26+, ưu tiên API chuẩn UUID.ofEpochMillis() để giảm phụ thuộc vào cách triển khai riêng của thư viện. API này tạo UUIDv7, trong khi UUID.randomUUID() vẫn là UUIDv4.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gọi UUID.timestamp() trên UUIDv7 bị lỗi | Phương thức timestamp cũ chỉ hỗ trợ UUIDv1 | Trích xuất 48 bit đầu bằng getMostSignificantBits() >>> 16 sau khi kiểm tra version |
| UUID tạo bằng randomUUID() có version 4 | randomUUID() vẫn sinh UUIDv4 | Gọi ofEpochMillis() để tạo UUIDv7 |
| ID không tăng theo thứ tự từng lệnh gọi | Nhiều ID cùng mili giây có suffix ngẫu nhiên | Chấp nhận thứ tự gần theo thời gian hoặc thiết kế monotonic generator riêng |
| ID mới có timestamp nhỏ hơn ID cũ | Đồng hồ hệ thống bị chỉnh lùi hoặc node clock lệch | Dùng logical clock nếu cần đơn điệu trong phạm vi xác định; không giả định thứ tự toàn cục |
| IllegalArgumentException từ ofEpochMillis() | Timestamp âm hoặc vượt 48 bit | Kiểm tra nguồn timestamp và giới hạn API |
| Sắp xếp trong DB không như mong đợi | Kiểu lưu, byte order hoặc collation không phù hợp | Kiểm tra thứ tự so sánh của database với UUIDv7 thực tế |
| UUID bị lộ thời gian tạo | Timestamp là phần công khai của UUIDv7 | Không dùng ID như secret; cân nhắc UUIDv4 hoặc token bí mật khi cần |
| Nghĩ UUIDv7 bảo đảm không trùng tuyệt đối | Uniqueness dựa trên xác suất | Giữ unique constraint và xử lý xung đột ở tầng lưu trữ |
| Nghĩ UUIDv7 là sequence phân tán | Timestamp không đồng bộ và suffix không có counter mặc định | Dùng sequence/offset/ordering service nếu cần thứ tự commit chính xác |
| Mã không biên dịch trên JDK 25 | API ofEpochMillis() mới từ JDK 26 | Nâng baseline hoặc dùng thư viện tương thích RFC 9562 |

## 17. Bài thực hành

Thực hiện bằng JDK 26 trở lên:

1. Tạo 100 UUID bằng UUID.ofEpochMillis(Instant.now().toEpochMilli()) và xác nhận tất cả có version() == 7 và variant() == 2.
2. Tạo UUID với timestamp cố định rồi giải mã bằng getMostSignificantBits() >>> 16; xác nhận timestamp khớp.
3. Gọi UUID.timestamp() với UUIDv7 và ghi nhận vì sao phương thức này không phù hợp.
4. Tạo nhiều UUID trong cùng một mili giây; quan sát chúng không nhất thiết tăng theo thứ tự gọi.
5. Tạo UUID ở hai timestamp khác nhau và so sánh thứ tự byte chuẩn.
6. Thử timestamp âm và timestamp lớn hơn (1L << 48) - 1; xác nhận IllegalArgumentException.
7. Thử bộ cấp timestamp logic đơn JVM và kiểm tra thứ tự tăng qua nhiều thread.
8. Lưu UUIDv7 trong database native UUID hoặc binary 16 byte; kiểm tra thứ tự index và keyset pagination.
9. So sánh workload insert với UUIDv4 và UUIDv7 bằng cùng schema, index và dữ liệu.
10. Kiểm tra log/API public để chắc chắn hệ thống không coi UUIDv7 là token bí mật.

**Tiêu chí hoàn thành:** giải thích được 48 bit timestamp và 74 bit còn lại; tạo UUIDv7 bằng API chuẩn JDK 26; kiểm tra version/variant; giải mã timestamp đúng cách; phân biệt timestamp, uniqueness và monotonicity; biết giới hạn khi đồng hồ lệch hoặc nhiều node; chọn đúng trường hợp dùng cho primary key/event ID; đánh giá tác động lên index và quyền riêng tư; xác định khả năng tương thích JDK 25/26/27.

## 18. Tài liệu tham khảo chính thức

- [RFC 9562: Universally Unique IDentifiers (UUIDs)](https://www.rfc-editor.org/rfc/rfc9562.html) — chuẩn UUID hiện hành, layout UUIDv7, timestamp, entropy, monotonicity và các khuyến nghị sử dụng.
- [Java 26 UUID API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/UUID.html) — UUID.ofEpochMillis(long), miền timestamp hợp lệ, version/variant và hành vi của timestamp().
- [Java 26 New API List](https://docs.oracle.com/en/java/javase/26/docs/api/new-list.html) — xác nhận UUID.ofEpochMillis(long) là API mới từ JDK 26.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html) — mục “Added Support for Creating a Type 7 UUID (UUIDv7)”.
- [Java 27 New API List](https://docs.oracle.com/en/java/javase/27/docs/api/new-list.html) — xác nhận API UUIDv7 tiếp tục hiện diện ở JDK 27.

UUIDv7 cung cấp định danh có timestamp và khả năng sắp xếp gần theo thời gian. Hãy dùng nó khi cần ID phân tán, dễ index và có thể quan sát thời điểm tạo; dùng cơ chế khác khi cần thứ tự toàn cục nghiêm ngặt, timestamp chính xác theo nghiệp vụ hoặc token bí mật.
