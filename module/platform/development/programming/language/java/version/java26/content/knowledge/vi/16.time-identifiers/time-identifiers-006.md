# Tạo UUIDv7 bằng UUID.ofEpochMillis

Java 26 bổ sung **UUID.ofEpochMillis(long)** để tạo UUID phiên bản 7 (UUIDv7) theo RFC 9562. Phần đầu UUID chứa thời điểm Unix Epoch tính bằng mili giây; phần còn lại chứa các bit ngẫu nhiên. Nhờ đặt timestamp ở các bit có trọng số cao, UUIDv7 có thể sắp xếp gần theo thời gian tạo và thường có tính cục bộ tốt hơn UUID ngẫu nhiên khi dùng làm khóa trong hệ thống lưu trữ.

API này thuộc **java.util.UUID** trong module **java.base**, được đánh dấu **Since: 26** và là API Java SE ổn định. Không cần bật preview hoặc thêm module. JDK 27 tiếp tục có phương thức này. Bài học thuộc module **JAVA_VERSION_JAVA26**, tập trung vào cách tạo UUIDv7, kiểm tra cấu trúc, đọc lại timestamp và hiểu chính xác giới hạn về thứ tự, đồng hồ hệ thống và tính duy nhất.

## 1. UUIDv7 là gì?

UUID là định danh 128 bit. RFC 9562 định nghĩa UUIDv7 là dạng UUID có timestamp Unix Epoch ở đầu và dữ liệu ngẫu nhiên ở phần còn lại.

Cấu trúc UUIDv7:

| Thành phần | Số bit | Ý nghĩa |
|---|---:|---|
| Unix timestamp | 48 | Số mili giây từ 1970-01-01T00:00:00Z, không tính leap second |
| Version | 4 | Giá trị cố định 7 |
| rand_a | 12 | Dữ liệu ngẫu nhiên |
| Variant | 2 | Bit variant IETF, giá trị nhị phân `10` |
| rand_b | 62 | Dữ liệu ngẫu nhiên |

Tổng cộng có 128 bit. Sau khi dành 4 bit cho version và 2 bit cho variant, còn **74 bit ngẫu nhiên**. Trong Java 26, `UUID.ofEpochMillis` lấy phần này từ một bộ sinh số giả ngẫu nhiên có độ mạnh mật mã.

Ví dụ hình thức chuỗi UUIDv7:

    019a....-....-7...-8...-............

- 12 chữ số hex đầu tiên biểu diễn 48 bit timestamp.
- Chữ số hex đầu tiên của nhóm thứ ba là version `7`.
- Nhóm thứ tư bắt đầu bằng chữ số thể hiện variant IETF (thường là `8`, `9`, `a` hoặc `b`).
- Các bit còn lại chứa dữ liệu ngẫu nhiên.

UUIDv7 không lưu ngày giờ theo múi giờ địa phương. Timestamp là Unix Epoch UTC tính bằng mili giây. Việc hiển thị thành giờ Việt Nam hay múi giờ khác là bước chuyển đổi ở tầng ứng dụng.

## 2. Tạo UUIDv7 bằng API Java 26

Cách dùng cơ bản:

    import java.time.Instant;
    import java.util.UUID;

    public class UuidV7Example {
        public static void main(String[] args) {
            long epochMillis = Instant.now().toEpochMilli();

            UUID id = UUID.ofEpochMillis(epochMillis);

            System.out.println("UUID: " + id);
            System.out.println("Version: " + id.version());
            System.out.println("Variant: " + id.variant());
        }
    }

Kết quả có dạng:

    UUID: 019...-....-7...-8...-............
    Version: 7
    Variant: 2

Phần ngẫu nhiên thay đổi theo mỗi lần gọi, vì vậy chuỗi UUID cụ thể không cố định. Giá trị `version()` phải là 7 và `variant()` phải là 2 đối với UUIDv7 theo RFC 9562.

Có thể viết ngắn hơn:

    UUID orderId = UUID.ofEpochMillis(System.currentTimeMillis());

Tuy nhiên, dùng `Instant.now().toEpochMilli()` giúp thể hiện rõ nguồn thời gian và thuận tiện khi ứng dụng đã dùng java.time. Phương thức `ofEpochMillis` chỉ nhận một giá trị long; nó không tự lấy giờ hiện tại.

## 3. Timestamp được mã hóa như thế nào?

Tham số truyền vào là số mili giây tính từ Unix Epoch:

    long timestamp = Instant.parse(
            "2026-11-27T10:30:00Z"
    ).toEpochMilli();

    UUID id = UUID.ofEpochMillis(timestamp);

Không truyền trực tiếp `Instant.getEpochSecond()`, vì đó là số giây, trong khi API cần mili giây. Cũng không truyền `System.nanoTime()`: giá trị này là đồng hồ đơn điệu dùng đo khoảng thời gian, không phải timestamp Unix Epoch.

Ví dụ phân biệt:

| Biểu thức | Đơn vị/ý nghĩa | Dùng cho ofEpochMillis? |
|---|---|---|
| `Instant.now().toEpochMilli()` | Mili giây từ Unix Epoch | Có |
| `System.currentTimeMillis()` | Mili giây từ Unix Epoch | Có |
| `Instant.now().getEpochSecond()` | Giây từ Unix Epoch | Không, sai đơn vị |
| `System.nanoTime()` | Bộ đếm đơn điệu để đo thời lượng | Không, không phải Unix Epoch |
| `LocalDateTime.now().toEpochSecond(...)` | Giây theo cách chuyển đổi cần múi giờ/offset | Không nếu chưa đổi sang mili giây |

Nếu dùng một thời điểm cố định trong kiểm thử, hãy chuyển qua Instant:

    Instant fixed = Instant.parse("2026-11-27T10:30:00Z");
    UUID id = UUID.ofEpochMillis(fixed.toEpochMilli());

Cách này làm cho phần timestamp có thể tái lập giữa các lần chạy; phần ngẫu nhiên của UUID vẫn khác nhau.

## 4. Kiểm tra UUIDv7 và đọc lại thời gian

Sau khi tạo hoặc nhận một UUID từ API, message queue hay database, có thể kiểm tra version và variant:

    static void requireUuidV7(UUID id) {
        if (id.version() != 7 || id.variant() != 2) {
            throw new IllegalArgumentException(
                    "Expected an RFC 9562 UUIDv7"
            );
        }
    }

Java 26 chưa định nghĩa `UUID.timestamp()` để trả về timestamp Unix milliseconds cho UUIDv7. Phương thức `timestamp()` hiện có được định nghĩa cho UUID version 1 và ném `UnsupportedOperationException` nếu UUID không phải version 1. Không gọi nó để đọc timestamp UUIDv7.

Với UUIDv7 hợp lệ, 48 bit timestamp nằm trong 48 bit cao nhất của `getMostSignificantBits()`. Có thể lấy timestamp bằng phép dịch phải không dấu 16 bit:

    import java.time.Instant;
    import java.util.UUID;

    static Instant creationTime(UUID id) {
        requireUuidV7(id);

        long epochMillis =
                id.getMostSignificantBits() >>> 16;

        return Instant.ofEpochMilli(epochMillis);
    }

Phép dịch `>>>` giữ cách diễn giải bit không dấu. Không dùng `>>` vì phép dịch phải có dấu sẽ mở rộng bit dấu nếu bit cao nhất là 1 trong các UUID có timestamp ở vùng rất xa trong tương lai.

Ví dụ đầy đủ:

    UUID id = UUID.ofEpochMillis(Instant.now().toEpochMilli());

    Instant embeddedTime = creationTime(id);

    System.out.println("ID: " + id);
    System.out.println("Embedded time: " + embeddedTime);

Timestamp lấy ra là thời điểm đã được mã hóa khi tạo UUID, không phải thời điểm UUID được đọc từ database. Nếu đồng hồ của máy tạo bị sai, UUID sẽ lưu timestamp sai tương ứng.

## 5. Giới hạn timestamp và lỗi đầu vào

UUIDv7 dành 48 bit cho timestamp. Vì vậy, `UUID.ofEpochMillis` chỉ chấp nhận giá trị trong khoảng:

    0 <= timestamp <= (1L << 48) - 1

Giới hạn dưới là Unix Epoch, tức 1970-01-01T00:00:00Z. Timestamp âm bị từ chối. Giá trị lớn hơn 48 bit cũng bị từ chối bằng `IllegalArgumentException`.

Có thể kiểm tra ranh giới:

    long maxTimestamp = (1L << 48) - 1;

    UUID atEpoch = UUID.ofEpochMillis(0);
    UUID atMax = UUID.ofEpochMillis(maxTimestamp);

    // Cả hai lời gọi trên hợp lệ.

Các lời gọi sau không hợp lệ:

    UUID.ofEpochMillis(-1);
    UUID.ofEpochMillis(maxTimestamp + 1);

Trong thực tế, timestamp 48 bit mili giây đủ dùng đến khoảng năm 10889 theo cách tính của RFC 9562. Ứng dụng hiện đại còn rất xa giới hạn này, nhưng không nên bỏ qua kiểm tra nếu nhận timestamp từ dữ liệu ngoài.

Nếu chuyển đổi một Instant có thời điểm quá xa sang mili giây, `Instant.toEpochMilli()` cũng có thể ném `ArithmeticException` do tràn long trước khi lời gọi UUID được thực hiện. Hãy xác thực miền thời gian theo nghiệp vụ trước khi tạo ID.

## 6. Thứ tự thời gian và tính đơn điệu

UUIDv7 được thiết kế để có thứ tự gần theo thời gian. Vì timestamp nằm ở phần đầu, hai UUID có timestamp mili giây khác nhau thường sắp xếp theo thời gian khi so sánh biểu diễn chuẩn theo thứ tự từ trái sang phải.

Tuy nhiên, **UUID.ofEpochMillis không tự bảo đảm mọi UUID tạo liên tiếp đều tăng nghiêm ngặt**.

Phương thức này dùng timestamp được caller truyền vào và điền 74 bit còn lại bằng dữ liệu ngẫu nhiên. Vì thế:

- Nếu timestamp lần sau lớn hơn timestamp lần trước, UUID có timestamp mới sẽ nằm sau nhóm UUID của timestamp cũ theo thứ tự từ điển của biểu diễn chuẩn.
- Nếu hai UUID được tạo trong cùng một mili giây, phần ngẫu nhiên quyết định thứ tự giữa chúng; UUID thứ hai không nhất thiết lớn hơn UUID thứ nhất.
- Nếu đồng hồ hệ thống lùi, timestamp truyền vào có thể nhỏ hơn lần trước và thứ tự thời gian cũng lùi.
- Nếu nhiều máy tạo UUID với đồng hồ lệch nhau, không có bảo đảm thứ tự toàn cục giữa các máy.

Tài liệu API yêu cầu caller tự bảo đảm timestamp đơn điệu nếu cần UUIDv7 đơn điệu. Đừng hiểu điều đó thành việc chỉ dùng `Instant.now()` là đã có thứ tự nghiêm ngặt.

### Khi nào cần thứ tự nghiêm ngặt?

Nếu mục tiêu chỉ là tạo ID có thể nhóm và sắp xếp gần theo mili giây, UUIDv7 chuẩn của JDK thường đáp ứng tốt. Nếu nghiệp vụ yêu cầu mỗi ID tiếp theo phải lớn hơn ID trước, kể cả khi tạo hàng nghìn ID trong cùng mili giây, cần một cơ chế sinh có bộ đếm hoặc logic monotonic theo RFC 9562 Section 6.2.

Không thể đạt bảo đảm đó chỉ bằng cách gọi lặp lại `UUID.ofEpochMillis(System.currentTimeMillis())`, vì timestamp có thể lặp và phần còn lại là ngẫu nhiên. Hãy chọn một implementation UUIDv7 có hỗ trợ counter/monotonic phù hợp, hoặc thiết kế bộ sinh có đồng bộ, xử lý clock rollback và kiểm thử cạnh tranh nhiều luồng. Nếu tự triển khai, phải tuân thủ bit layout và các yêu cầu RFC 9562; không tự sửa một vài bit tùy ý.

Một bộ sinh monotonic trong một tiến trình cũng không tự tạo thứ tự toàn cục giữa nhiều máy. Hệ thống phân tán cần thống nhất yêu cầu: thứ tự gần theo wall clock, thứ tự trong từng node hay thứ tự tuyệt đối theo một nguồn cấp sequence.

## 7. Đồng hồ hệ thống có thể thay đổi

`Instant.now()` và `System.currentTimeMillis()` lấy thời gian từ đồng hồ hệ thống. Đồng hồ này có thể được điều chỉnh bởi NTP, thao tác quản trị, đồng bộ máy ảo hoặc cấu hình hệ điều hành. Vì thế, timestamp UUIDv7 có thể:

- Lặp lại trong nhiều lần gọi nếu clock chưa tăng qua mili giây tiếp theo.
- Lùi về một giá trị cũ sau khi clock bị điều chỉnh lùi.
- Khác với thời điểm thực tế nếu máy có clock skew.
- Khác thời điểm của một node khác trong cùng cụm.

`System.nanoTime()` là đồng hồ đơn điệu phù hợp để đo elapsed time, nhưng không thể thay thế timestamp Unix Epoch trong UUIDv7. Nếu cần thứ tự đơn điệu, dùng `nanoTime()` như tín hiệu nội bộ để điều phối khoảng thời gian hoặc dùng counter, nhưng phần timestamp UUIDv7 vẫn phải tuân theo định dạng Unix milliseconds.

Không sử dụng timestamp UUID làm nguồn thời gian pháp lý hoặc dữ liệu audit duy nhất. Nếu nghiệp vụ cần thời điểm tạo chính xác, lưu riêng cột `created_at` theo Instant/UTC từ nguồn thời gian được quản lý. UUID là định danh có thông tin thời gian nhúng, không thay thế hệ thống timestamp nghiệp vụ.

## 8. So sánh UUIDv7 với UUIDv4

Java đã có `UUID.randomUUID()` để tạo UUID version 4. UUIDv4 dùng dữ liệu ngẫu nhiên cho phần lớn bit, còn UUIDv7 đưa timestamp vào 48 bit đầu.

| Tiêu chí | UUIDv4 | UUIDv7 |
|---|---|---|
| Version | 4 | 7 |
| Timestamp nhúng | Không | Có, Unix milliseconds |
| Sắp xếp gần theo thời gian | Không | Có, theo timestamp |
| Dữ liệu ngẫu nhiên | 122 bit sau version/variant | 74 bit sau timestamp/version/variant |
| Lộ thời điểm tạo | Không trực tiếp | Có, đến độ phân giải mili giây |
| API tạo trong JDK 26 | `UUID.randomUUID()` | `UUID.ofEpochMillis(long)` |
| Thứ tự nghiêm ngặt trong cùng mili giây | Không | Không được bảo đảm bởi factory mặc định |

UUIDv7 hữu ích khi muốn ID có thứ tự thời gian để sắp xếp hoặc cải thiện tính cục bộ của index. UUIDv4 phù hợp khi không cần timestamp trong ID và muốn tránh tiết lộ thời điểm tạo.

74 bit ngẫu nhiên từ bộ sinh mạnh về mật mã làm xác suất va chạm rất thấp, nhưng không biến UUID thành một bí mật hoặc bảo đảm không bao giờ trùng. Nếu dùng làm khóa chính database, vẫn đặt unique constraint và xử lý trường hợp vi phạm uniqueness theo thiết kế hệ thống.

## 9. Lưu ý bảo mật và riêng tư

UUIDv7 không mã hóa timestamp. Bất kỳ ai có UUID đều có thể đọc gần đúng thời điểm tạo bằng cách trích 48 bit đầu. Điều này có thể làm lộ thời điểm phát sinh đơn hàng, tài khoản, phiên hoặc sự kiện.

Phần ngẫu nhiên được tạo bằng cryptographically strong pseudo-random number generator, nhưng không nên dùng UUIDv7 như access token, password reset token hoặc secret capability. Những token này cần có chính sách entropy, thời hạn, lưu trữ và thu hồi riêng; dùng một token ngẫu nhiên chuyên dụng với độ dài phù hợp.

Các lưu ý thực tế:

- Không đưa dữ liệu cá nhân, mã người dùng hoặc thông tin bí mật vào các bit UUID.
- Không coi UUID là cơ chế phân quyền; luôn kiểm tra quyền truy cập tài nguyên ở server.
- Không dùng timestamp nhúng để chứng minh ai đã tạo sự kiện hoặc thời điểm chính xác nếu không có chữ ký/nguồn thời gian đáng tin cậy.
- Đặt unique constraint ở database cho cột ID.
- Cân nhắc UUIDv4 hoặc token ngẫu nhiên riêng nếu cần ID công khai mà không muốn tiết lộ thời gian tạo.
- Nếu log UUID, xem xét việc timestamp có tiết lộ nhịp hoạt động hoặc lưu lượng hệ thống hay không.

## 10. Dùng UUIDv7 làm khóa trong database

UUIDv7 thường hữu ích cho khóa chính hoặc event ID vì timestamp nằm ở phần đầu. Khi database sắp xếp UUID theo thứ tự byte hoặc theo dạng canonical string tương ứng, các ID tạo gần nhau có xu hướng nằm gần nhau hơn so với UUIDv4 ngẫu nhiên.

Lợi ích có thể gồm:

- Giảm phân tán ghi index so với ID ngẫu nhiên hoàn toàn trong một số hệ quản trị.
- Hỗ trợ sắp xếp và truy vấn theo khoảng ID gần với thời gian tạo.
- Cho phép tạo ID ở application trước khi insert, không cần round trip lấy sequence từ database.

Tuy nhiên, không có cam kết mọi database đều lưu hoặc so sánh kiểu UUID giống nhau. Hãy kiểm tra native UUID type, binary representation, byte order, collation và index implementation của database/driver. Nếu lưu dạng CHAR(36), dùng biểu diễn chuẩn và collation phù hợp; nếu lưu 16-byte binary, giữ đúng thứ tự byte RFC 9562. Không tự hoán đổi byte như một số cách lưu UUIDv1 cũ.

Không thay thế cột thời gian nghiệp vụ bằng UUIDv7. Timestamp của UUID chỉ có độ phân giải mili giây và phụ thuộc đồng hồ node. Nếu cần truy vấn theo thời gian nghiệp vụ, vẫn lưu cột timestamp riêng và lập index phù hợp.

## 11. Biên dịch và chạy trên JDK 26

`UUID.ofEpochMillis` là API Java SE ổn định từ Java 26, không phải preview hoặc incubator.

Kiểm tra JDK:

    java --version
    javac --version

Biên dịch:

    javac --release 26 -encoding UTF-8 -d out src/UuidV7Example.java

Chạy:

    java -cp out UuidV7Example

Không cần `--enable-preview`, `--add-modules` hoặc dependency ngoài cho chức năng tạo UUIDv7 cơ bản. `java.util.UUID` thuộc module `java.base`, luôn có trong Java runtime chuẩn.

JDK 25 trở về trước không có `UUID.ofEpochMillis`. Nếu dự án phải chạy trên các release đó, dùng thư viện UUIDv7 có uy tín và xác nhận implementation tuân thủ RFC 9562; không tự tạo UUID bằng cách ghép bit thiếu kiểm chứng. Khi nâng lên JDK 26 hoặc 27, có thể dùng factory chuẩn của JDK và bỏ dependency ngoài nếu dependency đó chỉ phục vụ việc tạo UUIDv7.

## 12. Checklist triển khai

1. Xác nhận runtime và compiler là JDK 26 trở lên.
2. Lấy timestamp theo Unix Epoch milliseconds bằng `Instant.now().toEpochMilli()` hoặc `System.currentTimeMillis()`.
3. Không truyền epoch seconds, nanoTime hoặc timestamp âm.
4. Kiểm tra miền 48 bit nếu timestamp đến từ dữ liệu bên ngoài.
5. Tạo ID bằng `UUID.ofEpochMillis(timestamp)`.
6. Xác minh `version() == 7` và `variant() == 2` khi nhận UUID từ nguồn không tin cậy.
7. Không gọi `UUID.timestamp()` cho UUIDv7; trích timestamp bằng `getMostSignificantBits() >>> 16` sau khi kiểm tra version.
8. Không giả định các UUID tạo trong cùng mili giây tự tăng nghiêm ngặt.
9. Nếu cần monotonic trong batch hoặc giữa nhiều node, chọn cơ chế counter/sequence và xử lý clock rollback rõ ràng.
10. Không dùng UUIDv7 làm secret token hoặc nguồn audit timestamp duy nhất.
11. Kiểm tra cách database lưu và sắp xếp UUID trước khi kỳ vọng index locality.
12. Giữ unique constraint và xử lý va chạm theo quy trình của ứng dụng.

## Tài liệu chính thức

- [Java SE 26 API — UUID](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/UUID.html): hợp đồng `ofEpochMillis`, giới hạn timestamp, version, variant và hành vi `timestamp()`.
- [Oracle — JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): xác nhận `UUID.ofEpochMillis(long)` được bổ sung trong JDK 26 để tạo UUID version 7.
- [Java SE 27 API — UUID](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/UUID.html): xác nhận API tiếp tục có trong JDK 27.
- [RFC 9562 — Universally Unique IDentifiers (UUIDs), Section 5.7](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.7): cấu trúc UUIDv7 và timestamp Unix milliseconds.
- [RFC 9562 — Section 6.1 and 6.2](https://www.rfc-editor.org/rfc/rfc9562.html#section-6.1): cân nhắc nguồn timestamp, clock rollback, tính đơn điệu và counter.
- [RFC 9562 — Section 6.9](https://www.rfc-editor.org/rfc/rfc9562.html#section-6.9): yêu cầu về tính duy nhất và dữ liệu ngẫu nhiên.

UUIDv7 qua `UUID.ofEpochMillis` là API ổn định từ JDK 26. Nó tạo định danh có timestamp UTC ở phần đầu và dữ liệu ngẫu nhiên mạnh ở phần còn lại. Điểm cần nhớ khi triển khai là timestamp chỉ có độ phân giải mili giây, factory không tự bảo đảm thứ tự nghiêm ngặt trong cùng mili giây, và UUIDv7 tiết lộ gần đúng thời điểm tạo.
