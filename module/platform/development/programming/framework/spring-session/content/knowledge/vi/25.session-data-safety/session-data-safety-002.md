# Sinh định danh, nguồn ngẫu nhiên và SessionIdGenerator theo phiên bản

Session ID là định danh mà client gửi lại trong cookie hoặc header để máy chủ tìm đúng phiên đã lưu. Với ứng dụng dùng Spring Session, repository có thể nằm trong Redis hoặc JDBC và được nhiều instance chia sẻ. Vì vậy, session ID không chỉ là một khóa kỹ thuật: ai sở hữu một ID còn hiệu lực có thể được máy chủ xem như đang sở hữu phiên tương ứng. Hãy bảo vệ nó như một bearer credential.

Spring Session mặc định sinh ID ngẫu nhiên an toàn. Trong phần lớn ứng dụng, nên giữ mặc định thay vì tự viết thuật toán. Khi có yêu cầu rõ ràng về định dạng, độ dài, nguồn ngẫu nhiên hoặc chuẩn tích hợp, Spring Session cung cấp điểm mở rộng SessionIdGenerator từ phiên bản 3.2. Bài học này giải thích cách sinh ID khó đoán, cách cấu hình SPI theo phiên bản, tác động tới Redis/JDBC và cách kiểm thử khi triển khai nhiều instance.

## 1. Phân biệt định danh, tính duy nhất và tính khó đoán

Một session ID cần đáp ứng đồng thời hai mục tiêu:

- **Khó đoán:** người ngoài không thể suy ra ID hợp lệ tiếp theo từ các ID đã quan sát.
- **Đủ duy nhất:** xác suất hai phiên nhận cùng ID phải cực kỳ thấp trong quy mô và thời gian vận hành của hệ thống.

Hai mục tiêu này liên quan nhưng không giống nhau. Bộ đếm tăng dần có thể tạo giá trị duy nhất nhưng dễ đoán. Một chuỗi dài có thể trông phức tạp nhưng vẫn yếu nếu được tạo từ timestamp, username, địa chỉ IP hoặc số thứ tự.

Session ID thường được dùng như một capability: client gửi ID, server tra repository và khôi phục trạng thái. Nếu kẻ tấn công đoán hoặc đánh cắp ID, họ có thể chiếm phiên cho tới khi ID bị thu hồi, hết hạn hoặc bị thay thế. Vì vậy, ID phải được sinh bằng nguồn ngẫu nhiên mật mã học, không phải chỉ bằng thuật toán tạo chuỗi duy nhất.

### 1.1. Entropy quan trọng hơn độ dài hiển thị

Entropy biểu thị mức không chắc chắn của giá trị. Nếu một ID có 128 bit entropy, không gian giá trị lý tưởng có kích thước 2^128. Thêm ký tự cố định hoặc thêm timestamp không làm tăng entropy tương ứng.

| Cách tạo ID | Đặc điểm | Đánh giá |
|---|---|---|
| Bộ đếm tuần tự | Dễ dự đoán giá trị tiếp theo | Không an toàn |
| Timestamp hiện tại | Không gian đoán được từ thời gian | Không an toàn |
| Hash của username và thời gian | Đầu vào có thể dự đoán hoặc tìm kiếm | Không thay thế CSPRNG |
| UUID phiên bản 4 | Dùng nguồn ngẫu nhiên mạnh; có 122 bit ngẫu nhiên do các bit phiên bản/biến thể | Mặc định tốt cho phần lớn hệ thống |
| 32 byte từ SecureRandom | 256 bit ngẫu nhiên trước khi mã hóa | Phù hợp khi có lý do cần token dài hơn |

Không đánh giá độ an toàn chỉ bằng số ký tự. Một ID 64 ký tự được tạo từ bộ đếm có thể yếu hơn UUID ngẫu nhiên 36 ký tự.

## 2. Nguồn ngẫu nhiên mật mã học

Trong Java, dùng java.security.SecureRandom để sinh byte ngẫu nhiên. SecureRandom là API dành cho số ngẫu nhiên mật mã học và được triển khai qua provider của JCA.

Không dùng các nguồn sau để tạo session ID:

- java.util.Random.
- ThreadLocalRandom.
- Math.random().
- Timestamp, sequence, số thứ tự database hoặc hash từ dữ liệu người dùng.
- Bộ sinh giả ngẫu nhiên tự viết.
- SecureRandom được seed thủ công bằng thời gian, PID, hostname hoặc giá trị dễ đoán.

Thông thường, tạo một SecureRandom cho generator singleton và gọi nextBytes cho mỗi ID. Không tạo lại generator cho từng request. Không tự đặt seed bằng dữ liệu ứng dụng; hãy để JVM/provider khởi tạo nguồn entropy theo môi trường.

### 2.1. UUID ngẫu nhiên mặc định

Spring Session dùng UuidSessionIdGenerator làm lựa chọn mặc định trong các phiên bản hỗ trợ SPI. Lớp này sinh ID bằng java.util.UUID. UUID phiên bản 4 dành phần lớn bit cho dữ liệu ngẫu nhiên và giữ một số bit để biểu thị version/variant.

UUID ngẫu nhiên là lựa chọn phù hợp cho phần lớn ứng dụng web. Chỉ nên thay đổi khi có yêu cầu cụ thể, chẳng hạn cần độ dài/định dạng khác, tương thích với một hệ thống tích hợp hoặc chính sách bảo mật đã được đánh giá.

Không nên thay UUID mặc định chỉ vì ID trông ngắn hoặc muốn thêm tiền tố tên ứng dụng. Tiền tố không tạo entropy; nếu muốn phân biệt môi trường hoặc tenant, hãy dùng namespace ở cấu hình repository và metadata vận hành thay vì nhúng dữ liệu nhận diện vào bearer token.

## 3. SessionIdGenerator xuất hiện từ phiên bản nào?

API tùy chỉnh cách sinh ID có thay đổi theo thế hệ Spring Session. Cần kiểm tra version thực tế của dependency trước khi viết import hoặc gọi setter.

| Phiên bản Spring Session | Cách tiếp cận |
|---|---|
| Trước 3.2 | Không có SPI chung SessionIdGenerator như API hiện hành. Các repository mặc định vẫn sinh ID an toàn; MapSession có ID ngẫu nhiên theo mặc định. Không dùng ví dụ import của 3.2+ trong dự án cũ. |
| 3.2 trở lên | Có org.springframework.session.SessionIdGenerator và UuidSessionIdGenerator. Có thể cung cấp bean hoặc cấu hình trực tiếp repository nếu tự tạo repository. |
| Các bản 3.2.x, 3.3.x, 3.4.x, 3.5.x và 4.x | API SessionIdGenerator là điểm mở rộng được công bố; kiểm tra Javadoc đúng minor version và loại repository đang dùng. |

SPI được thêm trong dòng 3.2. Với các bản milestone hoặc snapshot, tên API có thể khác trước khi ổn định; không lấy ví dụ từ milestone để áp dụng cho bản release. Hãy dùng BOM/dependency management để giữ Spring Session và các module Spring tương thích cùng một dòng phiên bản.

### 3.1. Các kiểu API cần nhận diện

Trong Spring Session 3.2+:

- SessionIdGenerator nằm trong package org.springframework.session.
- Phương thức generate() trả về String.
- UuidSessionIdGenerator là implementation mặc định sinh UUID ngẫu nhiên.
- MapSession và các repository được hỗ trợ có thể nhận SessionIdGenerator.
- Cấu hình Spring Session có thể sử dụng bean SessionIdGenerator do ứng dụng cung cấp.

SessionIdGenerator là SPI của Spring Session. Nó không phải HttpSessionIdResolver, CookieSerializer hoặc WebSessionIdResolver. Các thành phần kia quyết định cách client gửi/nhận ID; generator chỉ tạo giá trị ID mới.

## 4. Cấu hình mặc định: không cần tự sinh ID

Nếu không khai báo generator tùy chỉnh, Spring Session sử dụng chiến lược mặc định của repository. Với Spring Session 3.2+, lựa chọn phổ biến là UuidSessionIdGenerator.

Đối với cấu hình tiêu chuẩn như @EnableJdbcHttpSession hoặc @EnableRedisHttpSession, không cần tạo bean chỉ để lặp lại mặc định. Chỉ thêm SessionIdGenerator bean khi thực sự muốn thay thuật toán:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.SessionIdGenerator;
import org.springframework.session.UuidSessionIdGenerator;

@Configuration
public class SessionIdConfiguration {

    @Bean
    SessionIdGenerator sessionIdGenerator() {
        return UuidSessionIdGenerator.getInstance();
    }
}
~~~

Ví dụ trên minh họa cách tham chiếu implementation mặc định một cách tường minh. Trong ứng dụng không có yêu cầu tùy chỉnh, có thể bỏ cả bean này và để Spring Session tự cấu hình.

## 5. Tạo SessionIdGenerator tùy chỉnh bằng SecureRandom

Giả sử một hệ thống có yêu cầu ID dạng chữ số hex viết thường và muốn dùng 32 byte ngẫu nhiên. Mỗi byte mang 8 bit entropy; 32 byte tương đương 256 bit. Mã hóa hex tạo chuỗi 64 ký tự, mỗi ký tự biểu diễn 4 bit.

~~~java
import java.security.SecureRandom;
import java.util.HexFormat;

import org.springframework.session.SessionIdGenerator;

public final class SecureSessionIdGenerator implements SessionIdGenerator {

    private static final int RANDOM_BYTES = 32;
    private static final HexFormat HEX = HexFormat.of();

    private final SecureRandom secureRandom = new SecureRandom();

    @Override
    public String generate() {
        byte[] randomBytes = new byte[RANDOM_BYTES];
        this.secureRandom.nextBytes(randomBytes);
        return HEX.formatHex(randomBytes);
    }
}
~~~

Đặc điểm của ví dụ:

- Mỗi lần gọi generate() lấy 32 byte mới từ SecureRandom.
- HexFormat mặc định tạo chữ số hex viết thường.
- ID có 64 ký tự thuộc tập 0-9 và a-f.
- Không chứa username, timestamp, node name hoặc dữ liệu nghiệp vụ.
- Một instance SecureRandom được tái sử dụng bởi generator; không khởi tạo nguồn ngẫu nhiên mới trong mỗi lần gọi.

Java HexFormat có từ Java 17. Spring Session 3.2+ thuộc thế hệ yêu cầu Java hiện đại; nếu dự án có ràng buộc runtime khác, dùng encoder tương thích với Java target và kiểm tra lại định dạng đầu ra.

### 5.1. Đăng ký bean cho Spring Session

Với cấu hình repository do Spring Session quản lý:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.SessionIdGenerator;

@Configuration
public class SessionIdConfiguration {

    @Bean
    SessionIdGenerator sessionIdGenerator() {
        return new SecureSessionIdGenerator();
    }
}
~~~

Khi bean SessionIdGenerator được cung cấp, cấu hình Spring Session tương ứng sử dụng generator đó để tạo session ID mới. Cách này áp dụng cho cấu hình repository được hỗ trợ; cần kiểm tra đúng module và phiên bản khi dùng cấu hình đặc biệt.

Nếu ứng dụng tự khởi tạo SessionRepository thay vì dùng annotation/auto-configuration, đặt generator trực tiếp trên implementation hỗ trợ setter:

~~~java
repository.setSessionIdGenerator(sessionIdGenerator);
~~~

Ví dụ setter trên có trong các repository như JdbcIndexedSessionRepository và RedisSessionRepository ở Spring Session 3.2+. Chỉ gọi setter nếu kiểu repository và phiên bản thực tế cung cấp API đó. Không dùng reflection để sửa trường nội bộ khi setter không tồn tại.

### 5.2. Chỉ có một chiến lược rõ ràng

Ứng dụng nên có một generator được lựa chọn rõ ràng cho repository đang dùng. Nếu có nhiều bean cùng kiểu mà cấu hình không xác định bean nào được sử dụng, quá trình khởi tạo có thể lỗi hoặc repository nhận nhầm chiến lược.

Không tạo generator khác nhau tùy request, tenant hoặc node nếu không có thiết kế rõ ràng. Mọi node cần chấp nhận định dạng ID do các node khác phát ra; việc generate không cần cùng trạng thái ngẫu nhiên giữa node, nhưng hợp đồng định dạng phải tương thích.

## 6. Chọn định dạng ID

Định dạng ID ảnh hưởng đến cookie, schema database, index, log, proxy và công cụ tích hợp. Chọn định dạng đơn giản, không chứa dữ liệu nhận diện và có kích thước phù hợp.

| Định dạng | Ví dụ đặc điểm | Lưu ý |
|---|---|---|
| UUID dạng chuẩn | 36 ký tự có dấu gạch nối | Mặc định tương thích với schema JDBC phổ biến |
| Hex 32 byte | 64 ký tự hex viết thường | Dễ kiểm tra, URL-safe; cần tăng độ dài cột JDBC mặc định |
| Base64 URL-safe 32 byte | Khoảng 43 ký tự, có thể bỏ padding | Ngắn hơn hex; cần chú ý so sánh phân biệt hoa/thường trong database |
| Chuỗi có tiền tố | Ví dụ app- cộng token | Tiền tố không tăng entropy và làm dài cookie/schema |

Không dùng Base64 thường nếu ký tự + hoặc / gây vấn đề với hệ thống truyền dẫn. Nếu dùng Base64 URL-safe, kiểm tra mọi thành phần có giữ nguyên chữ hoa/chữ thường hay không. Session ID là giá trị opaque và phải được so sánh chính xác.

Với ví dụ hex viết thường, chuỗi dễ truyền trong cookie, URL-safe và không phụ thuộc vào chữ hoa. Đổi lại, 32 byte ngẫu nhiên thành 64 ký tự, dài hơn UUID chuẩn.

## 7. Tác động đến schema JDBC

Đây là điểm phải kiểm tra trước khi triển khai generator tùy chỉnh. Schema JDBC mặc định của Spring Session thường khai báo:

~~~sql
SESSION_ID CHAR(36) NOT NULL
~~~

Độ dài này phù hợp với UUID chuẩn 36 ký tự. Generator trong ví dụ tạo ID 64 ký tự; nếu giữ nguyên schema, insert có thể thất bại, bị cắt dữ liệu hoặc gặp lỗi tùy database và cấu hình.

Trước khi bật generator dài hơn:

1. Xác định độ dài tối đa của ID mới.
2. Tạo migration database để mở rộng cột SESSION_ID đủ chứa giá trị.
3. Giữ unique index trên SESSION_ID.
4. Kiểm tra giới hạn độ dài index của hệ quản trị và encoding/collation.
5. Triển khai migration trước khi các node bắt đầu phát ID mới.
6. Kiểm thử insert, lookup, change ID và delete với định dạng mới.

Với token hex 64 ký tự, có thể cân nhắc VARCHAR(64) hoặc cột rộng hơn để dự phòng thay đổi sau này. Cú pháp ALTER TABLE và loại cột phù hợp phụ thuộc PostgreSQL, MySQL, SQL Server, Oracle hoặc database đang dùng; dùng migration riêng cho dialect thực tế.

Không tự động thay đổi PRIMARY_ID chỉ vì SESSION_ID dài hơn. PRIMARY_ID là khóa nội bộ của bảng session; SessionIdGenerator sinh session ID mà client sử dụng. Hai giá trị có vai trò khác nhau.

### 7.1. Index và collation

SESSION_ID cần được tra cứu chính xác và có unique constraint/index. Nếu định dạng chứa cả chữ hoa và chữ thường, collation không phân biệt hoa/thường có thể khiến hai chuỗi khác nhau bị xem như cùng giá trị. Khi đó cần collation hoặc kiểu so sánh phân biệt chữ hoa/thường.

Ví dụ hex viết thường chỉ dùng 0-9 và a-f, nên tránh khác biệt do chữ hoa trong generator. Dù vậy, hãy kiểm tra kiểu cột, collation và index trên database thật; không suy luận từ H2 hoặc môi trường test.

## 8. Tác động đến Redis và các hệ thống phụ trợ

Redis không có cột SESSION_ID cố định 36 ký tự như schema JDBC mặc định, nhưng ID thường được đưa vào tên key hoặc cấu trúc lưu trữ. ID dài hơn làm key dài hơn và tăng nhẹ dung lượng metadata.

Kiểm tra:

- Namespace/key format của repository có được cấu hình thống nhất không.
- Không có script hoặc công cụ vận hành giả định ID là UUID 36 ký tự.
- Không có regex ở proxy, WAF, log parser hoặc API gateway chỉ chấp nhận UUID.
- Cookie/header được giữ nguyên, không bị decode hoặc chuẩn hóa sai.
- Các node dùng chung serializer và cấu hình repository.

Không tự sửa key nội bộ của Spring Session để phù hợp generator. Repository chịu trách nhiệm ánh xạ ID vào cấu trúc lưu trữ. Ứng dụng nên dùng SessionRepository API thay vì tự tạo hoặc phân tích key.

## 9. SessionIdGenerator và cookie resolver là hai việc khác nhau

Luồng khái niệm:

1. Repository gọi SessionIdGenerator để tạo ID mới.
2. Session được lưu trong Redis/JDBC bằng ID đó.
3. Resolver/serializer gửi ID tới client, thường qua cookie.
4. Client gửi lại cookie/header trong request sau.
5. Resolver trích ID và repository tìm session tương ứng.

Với Servlet, CookieSerializer như DefaultCookieSerializer quyết định tên cookie, path, domain và thuộc tính cookie. Với WebFlux, WebSessionIdResolver quyết định cách gửi/đọc ID. Các thành phần này không sinh session ID.

Thay tên cookie không thay đổi entropy. Thêm jvmRoute hoặc suffix để định tuyến cũng không tạo thêm entropy. Nếu cookie bị lộ, kẻ tấn công vẫn có thể dùng giá trị session ID hợp lệ; hãy bảo vệ cookie bằng HTTPS, Secure, HttpOnly, SameSite phù hợp và không ghi giá trị vào log.

## 10. Đổi session ID sau xác thực

Session fixation xảy ra khi kẻ tấn công biết trước session ID của nạn nhân và tìm cách khiến nạn nhân tiếp tục dùng ID đó sau khi đăng nhập. Sau xác thực, ứng dụng cần đổi session ID theo cơ chế bảo vệ fixation của Spring Security/Servlet.

SessionIdGenerator cung cấp giá trị mới cho thao tác tạo ID hoặc đổi ID trong repository. Ứng dụng không nên tự gán một chuỗi tùy ý vào cookie hoặc sửa trực tiếp cột SESSION_ID.

Sau khi đổi ID:

- Client phải nhận ID mới.
- ID cũ không còn được chấp nhận để khôi phục phiên đã xác thực.
- Các thuộc tính session hợp lệ cần được giữ theo chiến lược fixation.
- Request tiếp theo dùng ID mới phải tìm được cùng trạng thái phiên.
- Kiểm tra nhiều node đều xử lý được ID sau khi đổi.

Không nhầm đổi session ID với tạo một tài khoản hoặc session mới hoàn toàn. Rotation thay định danh của phiên theo cơ chế framework, trong khi dữ liệu phiên được bảo toàn theo chính sách.

## 11. Thay generator khi hệ thống đang chạy

Thay thuật toán sinh ID không có nghĩa phải đổi ID của tất cả session đang tồn tại. Session cũ tiếp tục mang ID đã được cấp cho tới khi hết hạn, logout hoặc bị thu hồi. Generator mới chỉ áp dụng khi tạo session mới hoặc khi framework cần ID mới, ví dụ rotation.

ID cũ và mới có thể cùng tồn tại nếu repository xem ID như chuỗi opaque và mọi node đều hỗ trợ độ dài/định dạng cần thiết.

### 11.1. Triển khai rolling an toàn

Một quy trình mở rộng schema trước, đổi generator sau:

1. Kiểm kê các node, phiên bản Spring Session, schema và thành phần trung gian có kiểm tra định dạng ID.
2. Mở rộng cột SESSION_ID và index theo migration tương thích ngược.
3. Cập nhật proxy, WAF, log parser và công cụ hỗ trợ nếu chúng đang giả định UUID 36 ký tự.
4. Kiểm thử phiên UUID cũ và ID mới trên cùng repository.
5. Triển khai generator mới trên các node theo kế hoạch rolling.
6. Xác nhận node cũ có thể lookup ID mới nếu còn tham gia phục vụ traffic.
7. Theo dõi lỗi lưu/đọc session, cookie parsing và session fixation rotation.
8. Giữ schema mới trong thời gian session cũ còn tồn tại; chỉ thu hẹp sau khi không còn ID dài và có kế hoạch rõ ràng.

Nếu node cũ có logic parse UUID thay vì xem ID là opaque string, nó có thể không đọc được ID mới. Khi đó cần nâng cấp tất cả node đọc trước khi bật phát ID mới, hoặc dùng một giai đoạn chuyển tiếp tương thích. Không bật generator mới chỉ trên một node mà chưa xác nhận các node còn lại.

### 11.2. Rollback

Rollback code không tự động làm mất các session đã được tạo bằng ID mới. Nếu schema vẫn đủ rộng và code cũ xử lý ID như chuỗi, node cũ có thể tiếp tục tra cứu chúng. Nếu code cũ, proxy hoặc database schema giới hạn 36 ký tự, rollback có thể khiến phiên mới không truy cập được.

Vì vậy, phải kiểm thử rollback trước khi triển khai. Không thu hẹp cột SESSION_ID trong cùng đợt rollback nếu vẫn còn session dùng ID dài.

## 12. Những điều không nên nhúng vào session ID

Không nhúng các thông tin sau vào ID:

- Username, email hoặc user ID.
- Tenant ID, vai trò hoặc quyền.
- Timestamp, thời điểm hết hạn hoặc thời gian đăng nhập.
- Hostname, tên node hoặc địa chỉ IP.
- Mã phiên bản ứng dụng.
- Trạng thái nghiệp vụ hoặc mã đơn hàng.

Các thông tin này có thể tiết lộ dữ liệu, tạo ID dễ đoán hoặc làm tăng coupling giữa cookie và hạ tầng. Nếu cần trace hoặc phân vùng, dùng correlation ID riêng hoặc metadata được quản lý an toàn; không biến session ID thành cấu trúc mang dữ liệu.

Một tiền tố cố định như app- chỉ giúp nhận diện bằng mắt, không làm ID an toàn hơn. Nếu cần namespace, cấu hình namespace ở repository hoặc cookie name theo môi trường.

## 13. Kiểm thử generator

Kiểm thử cần xác nhận định dạng, khả năng sinh đồng thời và tích hợp repository. Một unit test cơ bản:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashSet;
import java.util.Set;

import org.junit.jupiter.api.Test;

class SecureSessionIdGeneratorTests {

    private final SecureSessionIdGenerator generator =
        new SecureSessionIdGenerator();

    @Test
    void generatesOpaqueHexIds() {
        Set<String> ids = new HashSet<>();

        for (int i = 0; i < 10_000; i++) {
            String id = this.generator.generate();
            assertThat(id).hasSize(64).matches("[0-9a-f]{64}");
            assertThat(ids.add(id)).isTrue();
        }
    }
}
~~~

Test này kiểm tra định dạng và phát hiện lỗi triển khai hiển nhiên như ID rỗng hoặc trùng trong mẫu nhỏ. Nó không chứng minh entropy 256 bit và không thay thế việc đánh giá nguồn SecureRandom.

### 13.1. Kiểm thử đa luồng

Gọi generator đồng thời từ nhiều thread và kiểm tra:

- Mỗi kết quả đúng định dạng.
- Không có giá trị rỗng/null.
- Không có lỗi do chia sẻ generator.
- Không có trùng lặp trong mẫu kiểm thử.
- Thời gian sinh ID phù hợp tải dự kiến.

Generator thường là singleton bean dùng trong nhiều request. SecureRandom được thiết kế để dùng an toàn trong môi trường đa luồng; không tự tạo một SecureRandom mới cho mỗi request chỉ để tránh chia sẻ.

### 13.2. Kiểm thử repository

Với repository thật:

1. Gọi createSession().
2. Kiểm tra ID có định dạng mới.
3. Gọi save(session).
4. Dùng findById(id) để đọc lại.
5. Gọi changeSessionId() theo API session phù hợp và kiểm tra ID mới.
6. Xác nhận ID cũ không còn truy cập được theo hợp đồng repository.
7. Xóa phiên và xác nhận lookup không còn kết quả.

Chạy kiểm thử với Redis hoặc database cùng loại production. Với JDBC, xác minh migration cột SESSION_ID và unique index. Với Redis, xác minh key namespace và các thao tác lookup/delete.

## 14. Kiểm thử tích hợp HTTP và nhiều instance

Kiểm thử generator riêng chưa đủ. Cần kiểm tra toàn bộ vòng đời:

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Tạo session mới | Gọi endpoint tạo session | Cookie mang ID đúng định dạng |
| Request tiếp theo | Gửi lại cookie | Repository khôi phục đúng session |
| Rotation sau login | Đăng nhập và lấy cookie mới | ID mới được phát; ID cũ không còn dùng được |
| Redis/JDBC lookup | Đọc từ repository bằng ID mới | Session được tìm thấy |
| Hai node | Tạo session ở A, đọc ở B | B khôi phục session |
| ID cũ và mới cùng tồn tại | Tạo session trước/sau thay đổi generator | Cả hai định dạng được lookup trong giai đoạn chuyển tiếp |
| JDBC schema | Lưu ID dài hơn 36 ký tự | Insert/lookup thành công, unique index hoạt động |
| Proxy/WAF | Gửi cookie ID mới qua hạ tầng | Không bị regex hoặc giới hạn header từ chối |
| Rollback | Chạy node phiên bản trước với ID mới | Hành vi đúng như kế hoạch tương thích |
| Logging | Tạo và sử dụng session | ID không xuất hiện trong log/trace |

Không dùng cookie thật của người dùng production làm fixture. Test cần tạo session ID ngẫu nhiên riêng và xóa dữ liệu sau khi hoàn tất.

## 15. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy SessionIdGenerator khi compile | Dự án dùng Spring Session trước 3.2 | Dùng API đúng phiên bản hoặc nâng cấp có kế hoạch |
| Bean generator không được sử dụng | Repository được tạo thủ công hoặc cấu hình khác với auto-configuration | Gọi setter trên repository hỗ trợ và kiểm tra cấu hình thực tế |
| JDBC insert lỗi hoặc ID bị cắt | SESSION_ID vẫn là CHAR(36) | Mở rộng cột và giữ unique index trước khi bật generator |
| Node A tạo được nhưng node B không đọc được | Node B parse UUID hoặc giới hạn định dạng/độ dài | Đồng bộ phiên bản và kiểm thử ID opaque giữa node |
| Hai ID khác nhau bị xem là trùng | Database collation không phân biệt hoa/thường | Chọn định dạng thống nhất hoặc collation phân biệt chính xác |
| ID dài nhưng vẫn đoán được | Dùng timestamp, bộ đếm hoặc Random | Dùng SecureRandom và đánh giá entropy thực |
| Cookie không được gửi | Cookie policy, domain/path, proxy hoặc giới hạn header | Kiểm tra resolver/serializer và hạ tầng |
| Session fixation không đổi ID | Cơ chế rotation chưa chạy hoặc custom code bỏ qua strategy | Bật session fixation protection và kiểm thử ID cũ/mới |
| Rollback làm mất truy cập phiên mới | Node cũ không hỗ trợ định dạng mới hoặc schema bị thu hẹp | Giữ schema tương thích và kiểm thử rollback |
| Log có session ID | Debug HTTP/APM ghi cookie hoặc header | Redact Cookie, Set-Cookie và trường nhạy cảm |

## 16. Checklist triển khai

- Xác định rõ version Spring Session và kiểm tra API tương ứng.
- Giữ UuidSessionIdGenerator mặc định nếu không có yêu cầu thay đổi đã được đánh giá.
- Nếu tùy chỉnh trên Spring Session 3.2+, triển khai SessionIdGenerator và dùng SecureRandom.
- Sinh đủ entropy; không dùng timestamp, bộ đếm, username hoặc Random.
- Giữ ID opaque, không nhúng dữ liệu cá nhân hoặc thông tin hạ tầng.
- Đăng ký generator như bean hoặc cấu hình trực tiếp repository theo API phiên bản.
- Kiểm tra độ dài cookie, proxy, WAF, log parser và schema database.
- Với JDBC, mở rộng SESSION_ID trước khi phát ID dài hơn 36 ký tự; giữ unique index.
- Đồng bộ khả năng đọc ID giữa mọi node trong rolling deployment.
- Kiểm thử create, lookup, rotation, delete, multi-node và rollback.
- Không ghi session ID hoặc cookie vào log, trace, metric label hay ticket hỗ trợ.

## 17. Tài liệu tham khảo chính thức

- Spring Session – Common Configurations, mục Changing How Session IDs Are Generated: https://docs.spring.io/spring-session/reference/configuration/common.html
- Spring Session – SessionIdGenerator API: https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/SessionIdGenerator.html
- Spring Session – UuidSessionIdGenerator API: https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/UuidSessionIdGenerator.html
- Spring Session – JdbcIndexedSessionRepository API và schema mặc định: https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/jdbc/JdbcIndexedSessionRepository.html
- Java Platform – SecureRandom API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html

Session ID là thông tin truy cập, nên mục tiêu chính là tạo giá trị không thể đoán và giữ nó opaque trong toàn bộ vòng đời. Spring Session 3.2+ cung cấp SessionIdGenerator để thay chiến lược mặc định khi thật sự cần; SecureRandom là nền tảng phù hợp cho generator tùy chỉnh. Khi đổi định dạng, phải tính cả schema JDBC, cookie, proxy, rolling deployment và khả năng đọc ID giữa các node, chứ không chỉ thay một bean trong ứng dụng.
