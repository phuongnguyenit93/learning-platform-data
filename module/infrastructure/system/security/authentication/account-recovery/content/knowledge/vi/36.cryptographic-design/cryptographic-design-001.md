# Randomness source selection

## 1. Nguồn ngẫu nhiên là một phần của quyền khôi phục

Trong khôi phục tài khoản, nhiều giá trị trở thành bằng chứng để cấp một quyền nhạy cảm: token đặt lại mật khẩu, backup code, challenge xác nhận, recovery grant hoặc bí mật tạm thời của một phiên khôi phục. Nếu kẻ tấn công đoán được chúng, các bước kiểm tra phía sau có thể hoàn toàn đúng mà tài khoản vẫn bị chiếm đoạt.

**Randomness source selection** là lựa chọn nguồn sinh số ngẫu nhiên phù hợp với mục tiêu bảo mật và môi trường vận hành. Mục tiêu không chỉ là tạo chuỗi nhìn khó đọc, mà là khiến bên không được phép không thể dự đoán giá trị với chi phí khả thi.

Ví dụ, một token được tạo như sau vẫn nguy hiểm:

```text
token = SHA-256(account_id || current_time_millis)
```

Hash tạo ra chuỗi có hình thức khó đoán bằng mắt, nhưng đầu vào có thể nằm trong một tập nhỏ mà kẻ tấn công tự thử được. Mã hóa base64, thêm tiền tố bí mật trong mã nguồn hoặc băm thêm nhiều vòng không tự sửa được nguồn đầu vào yếu.

Ngược lại, một token sinh bằng nguồn mật mã tốt vẫn cần được ràng buộc với account, recovery flow và mục đích, có thời hạn, được lưu an toàn và chỉ dùng một lần. Ngẫu nhiên mạnh bảo vệ khả năng không đoán được; nó không tự tạo ra quyết định xác minh danh tính đúng.

## 2. Phân biệt entropy, CSPRNG và cách biểu diễn

### 2.1. Entropy không phải số ký tự

Entropy mô tả mức bất định của nguồn đối với bên đang cố dự đoán. Chuỗi dài không đồng nghĩa có nhiều entropy.

| Cách tạo | Nhìn bên ngoài | Điều cần hiểu |
| --- | --- | --- |
| Timestamp được đổi sang hex | Có thể dài | Khoảng thời gian có thể đoán được |
| Counter được băm | Có thể trông rất ngẫu nhiên | Không gian đầu vào vẫn có thể dễ duyệt |
| Mã sáu chữ số sinh đều | Dễ nhập | Chỉ có một triệu khả năng |
| 32 byte từ CSPRNG phù hợp | Có thể mã hóa thành token dài | Có không gian đầu ra lớn, nhưng vẫn phụ thuộc chất lượng nguồn và trạng thái bộ sinh |

Một chuỗi base64url biểu diễn 32 byte có thể dài 43 ký tự khi bỏ padding. Không được nhân 43 với 8 rồi kết luận có 344 bit ngẫu nhiên. Đó chỉ là cách biểu diễn 256 bit dữ liệu đầu ra.

Tương tự, lấy 8 byte ngẫu nhiên rồi in thành chuỗi dài hoặc băm thành 32 byte không làm nó trở thành một bí mật có 256 bit bất định.

### 2.2. CSPRNG mở rộng một trạng thái được khởi tạo an toàn

CSPRNG là bộ sinh giả ngẫu nhiên được thiết kế cho mục tiêu mật mã. Nó tạo đầu ra từ trạng thái nội bộ, với yêu cầu chống dự đoán phù hợp, và cần được khởi tạo bằng entropy đủ tốt. Nguồn entropy, thuật toán bộ sinh và việc bảo vệ trạng thái đều quan trọng.

[RFC 4086 về randomness cho bảo mật](https://www.rfc-editor.org/rfc/rfc4086.html) giải thích rằng thuật toán phức tạp không cứu được một seed nằm trong không gian dễ đoán. Vì vậy, ứng dụng nên dùng cơ chế đã được nền tảng cung cấp, thay vì tự kết hợp đồng hồ, process ID và dữ liệu môi trường để sáng tác nguồn ngẫu nhiên.

```text
Nguồn entropy của nền tảng
        ↓
Bộ sinh mật mã được quản lý
        ↓
Byte ngẫu nhiên cho token
        ↓
Biểu diễn và vòng đời token của ứng dụng
```

Số bit đầu ra không phải bằng chứng rằng thuật toán hoặc seed có cùng mức bảo đảm. Chẳng hạn, yêu cầu 256 bit đầu ra không tự chứng minh toàn bộ cấu hình bộ sinh đạt sức mạnh bảo mật 256 bit.

## 3. Xác định giá trị nào cần nguồn mật mã

| Giá trị trong hệ thống | Yêu cầu chính | Cách lựa chọn |
| --- | --- | --- |
| Token khôi phục hoặc recovery grant | Khó đoán và đủ dài | Byte từ CSPRNG phù hợp |
| OTP ngắn | Phân bố đều trong miền mã | CSPRNG cùng giới hạn lần thử và thời hạn |
| Backup code | Bí mật khó đoán, dùng một lần | CSPRNG; định dạng và entropy được xác định rõ |
| Challenge chống phát lại | Mới, khó dự đoán khi giao thức yêu cầu | Nguồn và quy tắc của giao thức |
| Khóa HMAC hoặc khóa mã hóa | Đạt yêu cầu của thuật toán và vòng đời khóa | API sinh khóa của thư viện/provider hoặc dịch vụ khóa phù hợp |
| ID sắp xếp nội bộ, số ngẫu nhiên cho giao diện | Có thể chỉ cần phân bố hoặc tính duy nhất | Không tự coi ID đó là bí mật cấp quyền |

Một số giao thức yêu cầu nonce duy nhất theo một khóa, một số yêu cầu challenge khó đoán, và có trường hợp cần cả hai. Không áp dụng một công thức “cứ random là đủ” cho mọi IV hoặc nonce mật mã; cần tuân theo yêu cầu của thuật toán và giao thức cụ thể.

Đối với thao tác khôi phục, nên cấp giá trị ngẫu nhiên mới cho từng mục đích. Không lấy một token rồi cắt từng đoạn để dùng làm mã email, challenge và quyền đặt lại mật khẩu. Lộ một phần không được tạo ra quan hệ dễ khai thác với các quyền khác.

## 4. Lựa chọn nguồn trong Java

Đối với bí mật khôi phục trong Java, dùng API mật mã thay cho các bộ sinh phục vụ mô phỏng hoặc hiệu năng thông thường.

| API hoặc cách làm | Dùng để tạo bí mật khôi phục? | Lý do |
| --- | --- | --- |
| `Math.random()` | Không | Không có hợp đồng bảo mật cần thiết |
| `Random`, `ThreadLocalRandom`, `SplittableRandom` | Không | Không phải lựa chọn cho bí mật mật mã |
| Counter, timestamp hoặc dữ liệu tài khoản | Không | Có thể đoán hoặc suy ra |
| `SecureRandom` với provider phù hợp | Có | API chuyên cho ngẫu nhiên mật mã |
| Dịch vụ sinh khóa được quản lý | Tùy loại giá trị | Phù hợp khi cần khóa và chính sách quản lý riêng |

[OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html#secure-random-number-generation) phân biệt các bộ sinh thông thường với nguồn dành cho chức năng bảo mật và liệt kê `SecureRandom` cho Java.

Kiểu biến không thay thế loại bộ sinh thực tế. Một dependency nhận `RandomGenerator` có thể được gán nhiều triển khai khác nhau; cần bảo đảm đường tạo bí mật thực sự nhận một nguồn mật mã được cho phép.

Không lấy tốc độ cao của một bộ sinh thông thường làm lý do sử dụng nó cho token. Nếu đường khôi phục quá tải, cần giới hạn lưu lượng và điều chỉnh kiến trúc; không giảm chất lượng nguồn ngẫu nhiên để duy trì thông lượng.

## 5. Ví dụ tạo token và mã số

Ví dụ sau tập trung vào sinh bí mật, không triển khai toàn bộ dịch vụ khôi phục:

```java
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Locale;

public final class RecoverySecrets {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder TOKEN_ENCODER =
            Base64.getUrlEncoder().withoutPadding();

    private RecoverySecrets() {
    }

    public static String newRecoveryToken() {
        byte[] secret = new byte[32];
        RANDOM.nextBytes(secret);
        return TOKEN_ENCODER.encodeToString(secret);
    }

    public static String newSixDigitCode() {
        int value = RANDOM.nextInt(1_000_000);
        return String.format(Locale.ROOT, "%06d", value);
    }
}
```

Java cung cấp cơ chế tự lấy seed từ nguồn của triển khai khi cần; `nextBytes` điền byte ngẫu nhiên vào mảng. `SecureRandom` hỗ trợ sử dụng từ nhiều thread. Xem [Java API: SecureRandom](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureRandom.html).

Trong ví dụ:

- 32 byte là lựa chọn minh họa cho token ngẫu nhiên dài, không phải quy định chung cho mọi giao thức.
- Base64url phục vụ truyền và biểu diễn; nó không mã hóa bí mật và không tăng entropy.
- Mã sáu chữ số vẫn là một bí mật có không gian nhỏ, dù được sinh bằng nguồn tốt.
- Kết quả cần được đưa vào vòng đời token: lưu verifier an toàn, ràng buộc ngữ cảnh, hết hạn và tiêu thụ nguyên tử.
- Các chuỗi bí mật không được đưa vào log hoặc response ngoài kênh cấp phát đã thiết kế.

Việc tái sử dụng một instance trong ví dụ tránh tạo một cấu hình sinh bí mật mới ở từng chỗ gọi. Nếu hệ thống cần một provider hoặc cấu hình cụ thể, nên tập trung lựa chọn đó trong thành phần chuyên trách, thay vì để mỗi endpoint tự quyết định.

### 5.1. Không dùng modulo tùy ý để chọn ký tự hoặc chữ số

Ví dụ không nên sao chép:

```java
int digit = (randomByte & 0xff) % 10;
```

Một byte có 256 giá trị, không chia đều cho 10. Các phần dư từ 0 đến 5 có nhiều giá trị đầu vào hơn các phần dư từ 6 đến 9. Kết quả bị lệch dù byte ban đầu được sinh đều.

Dùng API chọn số nguyên trong miền như `nextInt(bound)`, hoặc một cơ chế rejection sampling được thư viện cung cấp. Không tự lấy trị tuyệt đối của số nguyên ngẫu nhiên rồi chia lấy dư; giá trị nhỏ nhất của kiểu số nguyên còn có trường hợp đặc biệt khi lấy trị tuyệt đối.

Nếu chọn ký tự từ một bảng chữ cái, cũng cần tránh modulo bias. Một cách đơn giản cho token không cần nhập tay là sinh byte rồi mã hóa theo định dạng cố định.

## 6. Không làm yếu nguồn bằng seed tự tạo

Một lỗi có hình thức trông đúng:

```java
SecureRandom random = new SecureRandom();
random.setSeed(System.currentTimeMillis());
```

Đồng hồ không phải entropy bí mật. Tương tự, account ID, process ID, tên máy hoặc hằng số trong cấu hình không nên được dùng làm seed thay cho cơ chế của provider.

Theo [JCA Reference Guide về seeding](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html), seed do caller cung cấp và entropy do triển khai lấy cần được hiểu đúng. Đặc biệt, tự đặt seed trước lần sinh đầu tiên có thể ngăn cơ chế tự seed của một PRNG lấy entropy như người viết mã đang kỳ vọng.

Không nên diễn giải rằng mọi lần gọi `setSeed` đều thay thế và làm mất một trạng thái đã được seed tốt; API có quy tắc bổ sung seed. Sai lầm ở đây là tự coi dữ liệu dễ đoán là đủ cho việc khởi tạo an toàn.

Các việc cần tránh:

- Tạo `SecureRandom` từ một mảng byte cố định để các node “đồng nhất”.
- Lưu seed vào biến môi trường rồi dùng lại qua mọi lần khởi động.
- Gọi `setSeed(timestamp)` trước mỗi lần tạo token.
- Băm token cũ để tạo token mới.
- Trộn nhiều nguồn không an toàn rồi cho rằng tổng hợp ấy đương nhiên trở thành an toàn.

Nguồn cố định có thể hữu ích trong một ví dụ mô phỏng hoặc một môi trường kiểm thử được cô lập. Nó không được đi vào đường tạo quyền khôi phục thật qua một cờ debug hoặc một cấu hình fallback.

## 7. Có phải luôn dùng getInstanceStrong()?

`SecureRandom.getInstanceStrong()` chọn triển khai dựa trên cấu hình `securerandom.strongAlgorithms`. Tên phương thức không bảo đảm mọi môi trường có cùng provider hoặc cùng độ trễ. Một số triển khai có thể chờ nguồn entropy. [Java API: getInstanceStrong](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureRandom.html#getInstanceStrong()).

Lựa chọn cần dựa trên môi trường triển khai:

| Tình huống | Hướng lựa chọn |
| --- | --- |
| Ứng dụng Java thông thường với JDK và nền tảng được quản lý | Dùng nguồn mật mã của nền tảng, không tự seed |
| Chính sách yêu cầu thuật toán hoặc provider cụ thể | Chọn và cấu hình rõ, xác định hành vi khi không có triển khai ấy |
| Cần sinh khóa lâu dài với yêu cầu quản lý riêng | Dùng API sinh khóa hoặc hệ thống quản lý khóa phù hợp |
| Có yêu cầu về mô-đun mật mã đã được xác nhận | Đối chiếu đúng provider, phiên bản và chế độ; tên API không tự chứng minh đáp ứng |

Không hardcode một tên thuật toán chỉ vì nó chạy trên máy phát triển. Danh sách provider và cơ chế lấy entropy có thể khác giữa hệ điều hành hoặc bản phân phối JDK.

`generateSeed` phục vụ lấy vật liệu seed; không cần gọi nó cho từng token rồi tự dựng thêm một bộ sinh. Đường tạo token nên dùng API sinh đầu ra đã chọn, với quyền khởi tạo và reseed do thiết kế của provider quản lý.

Nếu một provider được yêu cầu là điều kiện bảo mật bắt buộc nhưng không có, ứng dụng phải báo lỗi hoặc không sẵn sàng cấp token theo chính sách. Không bắt exception rồi chuyển sang `Random` cho “chạy tiếp”.

## 8. Nguồn ngẫu nhiên và môi trường vận hành

### 8.1. Khởi động, blocking và readiness

Nguồn mật mã có thể cần chờ điều kiện khởi tạo. Ví dụ, tài liệu Linux mô tả `getrandom()` mặc định chờ khi nguồn entropy chưa được khởi tạo. Đây là hành vi của API và trạng thái hệ điều hành cụ thể, không phải lý do để tự đổi sang một nguồn yếu. Xem [Linux getrandom(2)](https://man7.org/linux/man-pages/man2/getrandom.2.html).

Ứng dụng cần xác định:

- Việc khởi tạo nguồn sinh bí mật xảy ra ở đâu.
- Nếu nguồn không sẵn sàng, đường cấp token phản hồi thế nào.
- Thời gian chờ và tài nguyên có bị tích lũy khi nhiều request cùng đến không.
- Thành phần nào chịu trách nhiệm cảnh báo và khôi phục vận hành.

Có thể chủ động khởi tạo thành phần sinh bí mật khi ứng dụng bắt đầu phục vụ. Một lần gọi thành công chỉ xác nhận thành phần hoạt động ở thời điểm đó; không chứng minh chất lượng mật mã bằng việc nhìn vài byte và không bảo đảm mọi lần gọi sau đều thành công.

Không tự sửa các thiết lập entropy của hệ điều hành dựa trên một hướng dẫn dành cho môi trường khác. Container, máy ảo và máy vật lý cần dựa trên cơ chế được nền tảng hỗ trợ.

### 8.2. Snapshot và nhân bản trạng thái

Một CSPRNG dựa trên trạng thái có thể sinh cùng chuỗi nếu hai bản sao tiếp tục từ cùng trạng thái với cùng cách xử lý. Vì vậy, snapshot đang chạy, checkpoint/restore hoặc sao chép đối tượng bộ sinh là những tình huống cần được thiết kế ở mức runtime và nền tảng.

Không serialize instance hoặc seed để các node sử dụng chung. Mỗi tiến trình cần được khởi tạo theo cơ chế an toàn của môi trường.

Nếu ứng dụng dùng nền tảng snapshot/restore, cần xác định cơ chế hỗ trợ khôi phục nguồn ngẫu nhiên trước khi cấp bí mật mới. Không giả định rằng process ID mới hoặc một lệnh `setSeed(currentTimeMillis())` tự giải quyết nguy cơ nhân bản.

### 8.3. Lỗi nguồn phải dừng việc cấp bí mật

Một nguyên tắc vận hành của thiết kế này:

```text
Không lấy được byte ngẫu nhiên theo chính sách
  → không tạo token thay thế từ dữ liệu dễ đoán
  → không ghi bản ghi token thành công
  → không gửi email chứa giá trị dự phòng
  → trả lỗi có thể xử lý và phát tín hiệu vận hành
```

Không trả mảng mặc định toàn số không khi lệnh sinh lỗi. Không dùng timestamp làm token dự phòng. Không retry vô hạn trên thread xử lý HTTP.

Nếu việc cấp token gồm ghi database và gửi email, cần bảo đảm lỗi sinh bí mật không để lại một quyền nửa hoàn tất. Chỉ bắt đầu thao tác lưu token sau khi đã có bí mật hợp lệ; các lỗi tiếp theo được xử lý theo giao dịch và cơ chế chuyển phát của hệ thống.

## 9. Độ dài, xác suất đoán và tính duy nhất

Với một bí mật được chọn đều trong không gian có `2^n` giá trị, xác suất đoán trúng một bí mật cố định trong `q` lần thử khác nhau xấp xỉ:

```text
P ≈ q / 2^n
```

Công thức áp dụng khi các giả định về phân bố và không gian đúng, và kết quả được giới hạn không vượt 1. Nó không còn mô tả hệ thống nếu bộ sinh bị dự đoán hoặc bí mật bị lộ qua log.

Mã sáu chữ số được chọn đều có một triệu khả năng. Với tối đa năm lần thử khác nhau cho cùng một mã, xác suất đoán trúng là `5 / 1.000.000`. Điều này giải thích vì sao mã ngắn cần thời hạn và giới hạn số lần thử nghiêm ngặt; nguồn tốt không làm không gian mã lớn lên.

Không được cho phép người dùng xin lại mã để vô hạn lần đặt lại bộ đếm. Chính sách cần tính các lần thử và cấp lại ở phạm vi recovery flow, tài khoản và các tín hiệu chống lạm dụng phù hợp.

### 9.1. Collision khác với dự đoán

Một nguồn mạnh vẫn có xác suất sinh trùng. Tính ngẫu nhiên không phải cam kết duy nhất tuyệt đối.

Đối với `m` giá trị chọn đều trong không gian `2^n`, khi xác suất còn nhỏ, xác suất có ít nhất một va chạm được xấp xỉ bằng:

```text
P_collision ≈ m × (m - 1) / (2 × 2^n)
```

Đây là bài toán khác việc kẻ tấn công đoán một token cụ thể. Hệ thống nên có ràng buộc duy nhất ở nơi cần định danh không trùng và xử lý xung đột bằng cách sinh giá trị mới trong giới hạn hợp lý.

Nếu phát hiện nhiều xung đột bất thường, không chỉ tăng số lần retry rồi bỏ qua. Cần xem xét lỗi triển khai, cắt ngắn dữ liệu, dùng nhầm nguồn, trạng thái bị sao chép hoặc lỗi lưu trữ.

Không áp dụng quy tắc “mọi OTP trên toàn hệ thống phải khác nhau”: nhiều challenge độc lập có thể có cùng mã ngắn. Điều quyết định là xác minh mã trong đúng ngữ cảnh và giới hạn lần thử.

### 9.2. UUID cần được hiểu theo cách sinh cụ thể

Trong Java, `UUID.randomUUID()` tạo UUID v4 bằng bộ sinh giả ngẫu nhiên mật mã, theo [tài liệu Java UUID](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/UUID.html#randomUUID()). Không nên nói rằng mọi UUID đều có thể dự đoán hoặc mọi UUID đều an toàn như nhau.

Tuy nhiên, UUID có các bit dành cho cấu trúc, và UUID dựa trên thời gian hoặc tên khác với một token gồm toàn byte ngẫu nhiên. Thiết kế token cần xác định cách sinh, số bit ngẫu nhiên và mục đích, không chỉ chọn một kiểu định danh quen thuộc.

Đặc biệt, lấy vài ký tự đầu của UUID để làm “mã an toàn ngắn” làm giảm mạnh không gian bí mật. Nếu cần token 32 byte, hãy sinh đúng 32 byte bằng nguồn phù hợp thay vì ghép và cắt nhiều ID.

## 10. Quan sát nguồn sinh mà không làm lộ đầu ra

Có thể ghi nhận tên thuật toán, provider, phiên bản runtime, lỗi khởi tạo và độ trễ thao tác theo chính sách vận hành. Không ghi seed, trạng thái nội bộ, token, backup code hoặc byte ngẫu nhiên được dùng làm bí mật.

Một thành phần quan sát không nên thu thập toàn bộ đầu ra để “đánh giá entropy” ở production. Chính việc thu thập có thể tạo ra kho bí mật ngoài dự kiến.

Cũng không được kết luận nguồn an toàn chỉ vì:

- Một số lượng nhỏ token không trùng.
- Biểu đồ tần suất ký tự trông đều.
- Chuỗi không có mẫu nhìn thấy bằng mắt.
- Token vượt qua một kiểm tra thống kê đơn giản.

Một chuỗi xác định có thể có thống kê đẹp nhưng vẫn bị dự đoán nếu biết trạng thái hoặc seed. Mức tin cậy đến từ thiết kế nguồn, triển khai được quản lý, cấu hình và việc bảo vệ môi trường.

Khi có dấu hiệu nguồn bị suy yếu hoặc trạng thái bị lộ, cần xác định phạm vi bí mật được cấp trong khoảng thời gian ảnh hưởng. Biện pháp có thể gồm dừng cấp mới, sửa nguồn, vô hiệu hóa token đang chờ và yêu cầu khởi động lại recovery flow. Chỉ tăng độ dài chuỗi mà giữ nguyên nguồn bị dự đoán không giải quyết gốc vấn đề.

## 11. Ví dụ lựa chọn cho một dịch vụ khôi phục

Giả sử dịch vụ cần token email dài, mã xác nhận ngắn và challenge cho một bước xác minh:

| Thành phần | Quyết định minh họa | Điều kiện đi kèm |
| --- | --- | --- |
| Token email | Sinh 32 byte từ `SecureRandom`, mã hóa base64url | Không log, lưu verifier, giới hạn mục đích và dùng một lần |
| Mã xác nhận | Chọn đều bằng `nextInt(bound)` | Giới hạn lần thử, hết hạn, ràng buộc challenge |
| Challenge giao thức | Dùng cơ chế sinh và xác minh của giao thức | Kiểm tra đúng ngữ cảnh và chống phát lại |
| Kho nguồn ngẫu nhiên | Thành phần Java được quản lý tập trung | Không seed thủ công; chính sách provider rõ ràng |
| Nguồn gặp lỗi | Dừng việc cấp bí mật | Không fallback sang thời gian, counter hoặc bộ sinh thông thường |

Nếu người dùng mất điện thoại chứa MFA hoặc passkey, nguồn ngẫu nhiên chỉ bảo vệ các bí mật của luồng thay thế. Nó không cho phép bỏ qua xác minh danh tính hoặc tự cấp session mạnh chỉ vì token có nhiều byte.

Lựa chọn nguồn đạt mục tiêu khi ứng dụng biết rõ bí mật được tạo từ đâu, vì sao khó dự đoán, môi trường nào duy trì bảo đảm đó và điều gì xảy ra khi nguồn không còn đáp ứng.
