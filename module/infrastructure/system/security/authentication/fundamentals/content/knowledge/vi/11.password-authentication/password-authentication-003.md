# Password storage

> **Chương:** Password authentication  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Lưu trữ password verifier an toàn, lựa chọn password hashing/KDF, quản lý salt và pepper, điều chỉnh chi phí tính toán, nâng cấp dữ liệu cũ và ứng phó khi cơ sở dữ liệu xác thực bị lộ.

## 1. Mục tiêu của password storage

Máy chủ cần xác minh người dùng có nhập đúng mật khẩu hay không, nhưng **không cần và không nên biết lại mật khẩu gốc** sau khi tiếp nhận. Vì vậy, hệ thống lưu một **password verifier** được tạo bằng thuật toán dẫn xuất khóa hoặc băm mật khẩu chuyên dụng. Khi đăng nhập, máy chủ chạy cùng thuật toán với mật khẩu người dùng vừa nhập và so sánh kết quả với verifier đã lưu.

Mục tiêu của thiết kế lưu trữ là làm cho việc đoán mật khẩu sau khi kho dữ liệu bị đánh cắp trở nên tốn kém, đồng thời bảo đảm quy trình đăng nhập hợp lệ vẫn hoạt động ổn định.

Một thiết kế tốt cần đáp ứng:

- Không lưu mật khẩu dạng rõ, không lưu bản mã có thể giải mã ngược để lấy mật khẩu.
- Mỗi mật khẩu có salt ngẫu nhiên riêng, được lưu cùng verifier.
- Dùng thuật toán dành cho mật khẩu, có chi phí thời gian và/hoặc bộ nhớ đủ lớn.
- Lưu phiên bản thuật toán và tham số để có thể nâng cấp theo thời gian.
- Bảo vệ kho verifier, khóa pepper (nếu dùng), log và các bản sao lưu.
- Điều tiết số lần xác minh để KDF không trở thành điểm cạn kiệt tài nguyên.

**Password storage** là một phần của SECURITY_AUTHENTICATION_FUNDAMENTALS: credential, xác thực và ranh giới tin cậy phải được thiết kế xuyên suốt. Một kho verifier tốt làm giảm thiệt hại khi dữ liệu bị lộ; nó không thay thế MFA, chống phishing, bảo vệ phiên hay phân quyền tài nguyên.

## 2. Hash mật khẩu khác mã hóa mật khẩu

| Cách lưu | Có thể khôi phục mật khẩu gốc? | Đánh giá |
|---|---|---|
| Plaintext | Có, đọc trực tiếp | Không chấp nhận |
| Mã hóa đối xứng có thể giải mã | Có, nếu khóa mã hóa bị lấy | Không phù hợp để lưu mật khẩu đăng nhập |
| SHA-256(password) trực tiếp | Không giải mã trực tiếp, nhưng có thể thử đoán rất nhanh | Không phù hợp cho password storage |
| KDF/password hashing có salt và chi phí cao | Không khôi phục trực tiếp; mỗi phỏng đoán phải trả chi phí KDF | Phương pháp phù hợp |

Hàm băm mật mã thông thường như SHA-256 được tối ưu để tính nhanh. Tốc độ đó hữu ích cho kiểm tra toàn vẹn nhưng lại có lợi cho kẻ tấn công khi họ đã lấy được verifier: họ có thể thử một lượng lớn mật khẩu ứng viên ngoại tuyến.

Mật khẩu do con người chọn thường có entropy thấp hơn khóa ngẫu nhiên. Danh sách từ phổ biến, mẫu bàn phím, tên tổ chức và biến thể như thêm năm hoặc ký tự đặc biệt đều có thể nằm trong bộ từ điển đoán. Do đó, **băm nhanh một lần không đủ bảo vệ mật khẩu**.

Password hashing/KDF làm cho mỗi lần thử tốn tài nguyên hơn, thường bằng cách lặp nhiều bước và/hoặc dùng bộ nhớ. Mục tiêu không phải làm đăng nhập không thể thực hiện, mà là tạo chi phí đủ cao cho từng phỏng đoán, trong khi hệ thống vẫn phục vụ người dùng hợp lệ.

## 3. Cấu trúc của password verifier

Một bản ghi verifier cần đủ thông tin để kiểm tra mật khẩu về sau và nâng cấp khi cần:

| Thành phần | Mục đích | Có phải bí mật không? |
|---|---|---|
| Algorithm | Xác định thuật toán, ví dụ Argon2id | Không |
| Version | Phiên bản thuật toán/định dạng | Không |
| Parameters | Chi phí bộ nhớ, thời gian, song song hoặc số vòng | Không |
| Salt | Giá trị ngẫu nhiên riêng cho verifier | Không |
| Derived hash | Kết quả KDF dùng để xác minh | Cần bảo vệ; có thể bị dùng để đoán ngoại tuyến |
| Pepper reference/version (nếu có) | Xác định khóa bí mật bổ sung | Không nên chứa chính pepper |
| Created/updated metadata | Hỗ trợ nâng cấp và điều tra | Không, nhưng cần giới hạn dữ liệu |

Ví dụ minh họa một chuỗi PHC:

~~~text
$argon2id$v=19$m=65536,t=3,p=1$<salt-encoded>$<hash-encoded>
~~~

Các con số trên chỉ minh họa cấu trúc tham số; **không phải cấu hình bắt buộc cho mọi hệ thống**. Giá trị thực tế phải được lựa chọn và benchmark trên phần cứng, tải và mức bảo vệ mục tiêu. Nhiều thư viện lưu thuật toán, tham số, salt và kết quả trong một chuỗi định dạng chuẩn, nhờ đó ứng dụng có thể xác minh mà không phải tự quản lý các thành phần rời rạc.

Một schema khái niệm:

~~~sql
CREATE TABLE account_password (
    account_id          BIGINT PRIMARY KEY,
    password_verifier   TEXT NOT NULL,
    changed_at          TIMESTAMP NOT NULL,
    verifier_updated_at TIMESTAMP NOT NULL
);
~~~

Ví dụ chỉ biểu diễn nơi lưu verifier. Không thêm cột \`password\`, \`plain_password\` hoặc cột debug chứa dữ liệu người dùng nhập. Quyền đọc bảng này nên bị giới hạn cho dịch vụ xác thực và các tác vụ vận hành có thẩm quyền.

## 4. Salt: ngẫu nhiên, riêng cho từng mật khẩu

**Salt** là dữ liệu ngẫu nhiên được đưa vào phép tính KDF cùng mật khẩu. Salt không cần giữ bí mật và thường được lưu cùng verifier.

Salt giải quyết một số vấn đề quan trọng:

1. Hai tài khoản chọn cùng mật khẩu sẽ có verifier khác nhau nếu salt khác nhau.
2. Kẻ tấn công không thể dùng một bảng tính trước duy nhất để tra trực tiếp nhiều verifier có salt độc lập.
3. Mỗi verifier cần được tấn công bằng quá trình đoán riêng, làm giảm hiệu quả của precomputed hash/rainbow table.

~~~text
account A: KDF(password, salt_A, parameters) -> verifier_A
account B: KDF(password, salt_B, parameters) -> verifier_B

salt_A != salt_B
verifier_A != verifier_B  // với xác suất áp đảo
~~~

### Yêu cầu với salt

- Sinh bằng bộ tạo số ngẫu nhiên mật mã (CSPRNG) hoặc để thư viện password hashing tạo tự động.
- Mỗi verifier có salt riêng; không dùng một salt cố định chung cho toàn hệ thống.
- Salt đủ dài để tránh va chạm thực tế; 16 byte ngẫu nhiên là lựa chọn phổ biến khi ứng dụng tự quản lý salt.
- Lưu salt cùng verifier hoặc trong định dạng verifier của thư viện.
- Không dùng username, email, account ID hay thời điểm tạo tài khoản làm salt.

Salt **không phải pepper**. Salt công khai và riêng theo bản ghi; pepper là bí mật bổ sung được lưu tách khỏi kho verifier. Salt ngăn nhiều verifier có cùng kết quả và làm giảm lợi thế tính trước; nó không ngăn kẻ tấn công đoán riêng từng mật khẩu sau khi lấy được verifier.

## 5. Lựa chọn thuật toán password hashing/KDF

Không phải thuật toán nào có tên “hash” cũng phù hợp lưu mật khẩu. Lựa chọn cần dựa trên khuyến nghị hiện hành, thư viện được duy trì, môi trường triển khai và yêu cầu tuân thủ.

| Thuật toán | Đặc điểm | Khi cân nhắc |
|---|---|---|
| **Argon2id** | KDF memory-hard; kết hợp đặc tính của Argon2i và Argon2d | Lựa chọn ưu tiên phổ biến cho hệ thống mới khi thư viện và môi trường hỗ trợ |
| **scrypt** | Memory-hard, chi phí bộ nhớ có thể cấu hình | Hệ thống cần lựa chọn KDF memory-hard và có thư viện tốt |
| **bcrypt** | Password hashing lâu đời, có work factor | Tương thích hệ thống cũ; lưu ý giới hạn độ dài đầu vào theo byte |
| **PBKDF2-HMAC-SHA-256** | KDF dựa trên số vòng lặp; được hỗ trợ rộng | Môi trường cần triển khai theo yêu cầu chuẩn/FIPS hoặc thư viện được phê duyệt |
| **SHA-256/MD5/SHA-1 trực tiếp** | Hash nhanh, không có chi phí password hashing thích hợp | Không dùng trực tiếp để lưu mật khẩu |

### Argon2id

Argon2id thường là lựa chọn tốt cho hệ thống mới. Các tham số quan trọng gồm:

- **Memory cost (m):** lượng bộ nhớ cần dùng cho mỗi lần tính.
- **Time cost (t):** số lượt xử lý.
- **Parallelism (p):** mức song song.
- **Salt và output length:** kích thước salt và kết quả dẫn xuất.

Tăng chi phí bộ nhớ khiến việc chạy số lượng lớn phỏng đoán song song trở nên đắt hơn, đặc biệt với phần cứng chuyên dụng. Tuy nhiên, cấu hình quá cao có thể gây chậm đăng nhập hoặc cho phép kẻ tấn công tạo tải lớn lên máy chủ.

### bcrypt và giới hạn byte

bcrypt có giới hạn độ dài đầu vào khoảng 72 byte trong nhiều triển khai. Với mật khẩu dài hoặc Unicode, số byte không bằng số ký tự. Một số thư viện cắt đầu vào ở giới hạn này; nếu ứng dụng không phát hiện, hai chuỗi khác nhau có thể bị xử lý như nhau sau khi cắt.

Nếu đang duy trì bcrypt:

- Xác minh chính xác hành vi của thư viện và phiên bản đang dùng.
- Không âm thầm cắt mật khẩu.
- Không tự nối một tiền tố hoặc hậu tố tùy biến để vượt giới hạn nếu chưa có thiết kế mật mã được xem xét.
- Có kế hoạch chuyển sang KDF phù hợp hơn khi cần hỗ trợ passphrase dài.

### PBKDF2 và yêu cầu tuân thủ

PBKDF2 có thể phù hợp trong môi trường cần thư viện được phê duyệt hoặc yêu cầu tương thích nhất định. Nó chủ yếu tăng chi phí tính toán theo số vòng, không có đặc tính memory-hard giống Argon2id/scrypt. Tham số phải theo khuyến nghị hiện hành của tiêu chuẩn và chính sách tổ chức, không sao chép một con số cũ mà không đánh giá.

**Nguyên tắc:** chọn thuật toán chuẩn, thư viện đáng tin cậy và tham số được benchmark. Không tự xây thuật toán, không ghép nhiều hàm hash nhanh để tạo “KDF riêng”.

## 6. Điều chỉnh chi phí: bảo vệ ngoại tuyến và bảo vệ máy chủ

Chi phí KDF có hai mặt:

- Với kẻ tấn công ngoại tuyến, mỗi phỏng đoán trở nên đắt hơn sau khi kho verifier bị đánh cắp.
- Với hệ thống thật, mỗi lần đăng nhập cũng tốn CPU/bộ nhớ/thời gian tương ứng.

Vì vậy, cấu hình cần được đo trên phần cứng và mức tải sản xuất. Một quy trình lựa chọn thực tế:

1. Chọn thuật toán và thư viện đã được đánh giá.
2. Đặt mục tiêu thời gian xác minh phù hợp trải nghiệm và chính sách bảo mật.
3. Tăng memory/time cost đến mức cao nhất mà hạ tầng có thể chịu ổn định trong điều kiện tải dự kiến.
4. Đo cả độ trễ p95/p99, bộ nhớ trên mỗi yêu cầu và số lần đăng nhập đồng thời.
5. Kiểm tra tác động khi có burst đăng nhập hoặc bot gửi nhiều yêu cầu.
6. Ghi tham số vào verifier để lần xác minh sau biết cách xử lý.
7. Đánh giá lại định kỳ khi phần cứng, tải và năng lực tấn công thay đổi.

### Ví dụ về giới hạn tài nguyên

Giả sử KDF được cấu hình dùng khoảng 64 MiB bộ nhớ cho mỗi lần xác minh đồng thời. Nếu server cho phép 1.000 yêu cầu KDF chạy cùng lúc, nhu cầu bộ nhớ thô cho các tác vụ đó có thể lên tới khoảng 64 GiB, chưa tính ứng dụng và hệ điều hành. Con số chỉ là ví dụ để minh họa phép nhân; cấu hình thật phải dựa trên đo đạc và giới hạn concurrency.

Không được chỉ tăng tham số KDF rồi bỏ qua điều tiết lưu lượng. Hãy kết hợp:

- Rate limit theo tài khoản, nguồn và tín hiệu rủi ro.
- Hàng đợi hoặc semaphore giới hạn số phép KDF đồng thời.
- Timeout và giới hạn kích thước đầu vào.
- Giám sát CPU, bộ nhớ, độ trễ và tỷ lệ lỗi.
- Cơ chế phản hồi chung để giảm enumeration, nhưng tránh khóa tài khoản vĩnh viễn dễ bị lạm dụng.

Không bỏ qua KDF cho username không tồn tại nếu điều đó làm thời gian phản hồi khác biệt rõ rệt. Một verifier giả (dummy verifier) có thể giúp giảm chênh lệch nhánh xử lý, nhưng cần kiểm soát chi phí và không đảm bảo triệt tiêu mọi side channel.

## 7. Pepper: bí mật bổ sung ngoài cơ sở dữ liệu

**Pepper** là một bí mật bổ sung được dùng trong quy trình tạo hoặc xác minh password verifier. Khác với salt, pepper phải được bảo vệ và lưu **tách khỏi kho dữ liệu verifier**, ví dụ trong secret manager, HSM hoặc KMS theo thiết kế phù hợp.

Khi kẻ tấn công chỉ lấy được cơ sở dữ liệu mà không lấy được pepper, việc thử đoán verifier có thể khó hơn đáng kể nếu quy trình sử dụng pepper được thiết kế đúng. Tuy nhiên:

- Pepper không thay thế salt hoặc KDF.
- Nếu kẻ tấn công chiếm được cả ứng dụng đang chạy và bí mật pepper, lợi ích có thể mất.
- Nếu pepper bị mất mà không có bản sao/quy trình khôi phục an toàn, hệ thống có thể không xác minh được mật khẩu hiện tại.
- Xoay pepper cần một chiến lược chuyển đổi; không thể giả định có thể tính verifier mới nếu không có mật khẩu người dùng.

### Quản lý pepper

1. Tạo pepper bằng nguồn ngẫu nhiên mật mã và quản lý trong secret manager/HSM/KMS.
2. Chỉ dịch vụ xác thực cần thiết mới có quyền sử dụng; không đưa pepper vào source code, biến cấu hình công khai hoặc image container.
3. Không log pepper, không trả nó trong API và không lưu cạnh verifier.
4. Lưu **key version/reference** trong bản ghi để biết verifier cần phiên bản pepper nào.
5. Có kế hoạch backup, khôi phục, luân chuyển và xử lý sự cố mất/lộ khóa.
6. Kiểm thử quy trình xoay khóa trước khi áp dụng cho dữ liệu người dùng thật.

Không tự chế cơ chế như nối chuỗi pepper vào mật khẩu theo một cách tùy tiện rồi băm SHA-256. Nếu dùng pepper, hãy theo hướng dẫn của thư viện/KDF và thiết kế mật mã được xem xét. Có thể triển khai pepper bằng một bước keyed operation phù hợp, nhưng phải nhất quán giữa tạo, xác minh, nâng cấp và phục hồi.

### Khi nào cần pepper?

Pepper là lớp phòng thủ bổ sung, đặc biệt khi mô hình đe dọa xem rò rỉ chỉ riêng cơ sở dữ liệu là kịch bản đáng quan tâm và tổ chức có khả năng quản lý khóa an toàn. Nó làm tăng độ phức tạp vận hành. Với hệ thống nhỏ không có quản lý bí mật đáng tin cậy, một KDF mạnh, salt đúng, phân quyền cơ sở dữ liệu và backup an toàn có thể là ưu tiên trước.

## 8. Tạo verifier và xác minh mật khẩu

### Quy trình tạo verifier

~~~mermaid
flowchart TD
    P["Nhận mật khẩu qua HTTPS"] --> V["Kiểm tra chính sách và đầu vào"]
    V --> S["Sinh salt ngẫu nhiên riêng"]
    S --> K["Chạy password KDF với tham số đã chọn"]
    K --> H["Nhận verifier có thuật toán, salt, tham số"]
    H --> D["Lưu verifier và metadata tối thiểu"]
    D --> X["Không ghi mật khẩu rõ vào log/DB"]
~~~

Thư viện password hashing thường tự sinh salt và đóng gói tham số vào chuỗi verifier. Ưu tiên API cấp cao của thư viện thay vì tự viết phép tạo salt, mã hóa, giải mã hoặc so sánh.

### Mã giả với thư viện

~~~typescript
// Pseudocode: dùng API password-hashing đã được kiểm định.
// Tham số cần benchmark theo phần cứng và tải thực tế.
async function createPasswordVerifier(password: string) {
  validatePasswordPolicy(password);

  const verifier = await argon2.hash(password, {
    type: argon2.argon2id,
    memoryCost: CONFIGURED_MEMORY_COST,
    timeCost: CONFIGURED_TIME_COST,
    parallelism: CONFIGURED_PARALLELISM,
  });

  // Thư viện quản lý salt và định dạng verifier.
  return verifier;
}

async function verifyPassword(password: string, storedVerifier: string) {
  return argon2.verify(storedVerifier, password);
}
~~~

\`CONFIGURED_...\` là tham số được triển khai chọn sau khi benchmark; không phải tên biến có sẵn. Cú pháp API cụ thể tùy thư viện và phiên bản. Dùng kết quả verify của thư viện; không tự so sánh chuỗi hash bằng cách chuyển về dạng dễ bị timing leak.

### Luồng đăng nhập

~~~text
1. Nhận identifier và password qua HTTPS.
2. Áp dụng giới hạn thử và bảo vệ chống bot.
3. Tra tài khoản và password verifier.
4. Nếu không tìm thấy tài khoản, có thể chạy dummy verifier để giảm khác biệt thời gian.
5. Xác minh bằng thư viện KDF với verifier đã lưu.
6. Kiểm tra trạng thái tài khoản và chính sách MFA.
7. Nếu hợp lệ, cấp phiên/token theo chính sách.
8. Nếu verifier cũ, lên lịch rehash sau khi xác minh thành công.
9. Không log password, verifier đầy đủ hoặc token được cấp.
~~~

Mã giả không phải triển khai đăng nhập hoàn chỉnh. Cần xử lý lỗi, giới hạn tải KDF, trạng thái khóa/đình chỉ, MFA, phiên, logging và chống enumeration. Không trả về thông báo khác nhau như “username không tồn tại” và “sai mật khẩu” nếu điều đó làm lộ danh sách tài khoản.

## 9. Quản lý Unicode, độ dài và biểu diễn mật khẩu

Password storage có thể bị lỗi khi quá trình tạo và xác minh không xử lý đầu vào giống nhau.

### Độ dài theo ký tự và byte

Một chuỗi Unicode có thể có nhiều cách biểu diễn byte. Một ký tự hiển thị có thể gồm nhiều code point; một số ký tự có thể có dạng tổ hợp (combining marks). Vì vậy:

- Xác định rõ giới hạn đầu vào theo byte hoặc ký tự và công bố hợp lý.
- Không âm thầm cắt mật khẩu ở giới hạn của thư viện.
- Nếu có chuẩn hóa Unicode (ví dụ NFC), áp dụng **cùng một chính sách** khi thiết lập, đổi và xác minh; thay đổi chính sách có thể khiến người dùng không đăng nhập được.
- Dùng encoding nhất quán (thường UTF-8 trong ứng dụng web) và kiểm thử nhiều ngôn ngữ.
- Không loại bỏ khoảng trắng đầu/cuối hoặc đổi hoa-thường một cách âm thầm, trừ khi chính sách đã quy định rõ và áp dụng nhất quán.

### Giới hạn đầu vào để chống lạm dụng

KDF có thể nhận đầu vào lớn và tốn tài nguyên cho mỗi yêu cầu. Hệ thống nên đặt giới hạn tối đa đủ rộng cho passphrase nhưng tránh cho phép payload khổng lồ. Kiểm tra kích thước trước khi cấp phát tài nguyên KDF; phản hồi phù hợp mà không làm lộ thông tin tài khoản.

## 10. Nâng cấp verifier và di trú thuật toán

Thuật toán và tham số cần thay đổi theo thời gian khi phần cứng nhanh hơn hoặc khuyến nghị bảo mật thay đổi. Không cần buộc mọi người dùng đặt lại mật khẩu ngay lập tức nếu hệ thống có thể nâng cấp verifier an toàn khi họ đăng nhập.

### Rehash on login

Giả sử một tài khoản đang dùng bcrypt với work factor cũ. Người dùng nhập mật khẩu đúng; trong thời điểm đó server có mật khẩu hiện tại trong bộ nhớ xử lý. Server có thể:

1. Xác minh mật khẩu bằng verifier cũ.
2. Kiểm tra xem thuật toán/tham số hiện tại còn đạt chính sách không.
3. Nếu cần nâng cấp, tạo verifier mới bằng Argon2id và salt mới.
4. Cập nhật verifier trong giao dịch có kiểm soát.
5. Xóa tham chiếu đến plaintext sớm nhất có thể; không ghi mật khẩu vào log hoặc hàng đợi.

~~~mermaid
flowchart TD
    L["Người dùng đăng nhập"] --> O["Xác minh bằng verifier hiện tại"]
    O --> Q{"Mật khẩu đúng?"}
    Q -->|"Không"| F["Từ chối"]
    Q -->|"Có"| P{"Verifier đã đạt chính sách mới?"}
    P -->|"Có"| S["Tiếp tục MFA / cấp phiên"]
    P -->|"Không"| N["Tạo verifier mới với KDF/params mới"]
    N --> U["Cập nhật verifier nguyên tử"]
    U --> S
~~~

### Cập nhật có tranh chấp

Nếu hai yêu cầu đăng nhập đồng thời cùng nâng cấp verifier, cần tránh một bản cập nhật cũ ghi đè bản mới. Có thể dùng optimistic concurrency/version hoặc cập nhật có điều kiện dựa trên verifier cũ. Giao dịch phải bảo đảm chỉ thay verifier khi bản ghi vẫn ở phiên bản đã xác minh.

### Di trú khi không có mật khẩu hiện tại

Không thể chuyển đổi một verifier yếu sang KDF mới chỉ bằng cách băm lại chuỗi verifier cũ. Kết quả KDF mới lúc đó bảo vệ **hash cũ**, không bảo vệ mật khẩu người dùng như mong muốn. Nếu người dùng không đăng nhập trong thời hạn di trú, hệ thống có thể:

- Giữ verifier cũ trong phạm vi rủi ro và thời gian được phê duyệt.
- Yêu cầu đặt lại mật khẩu qua quy trình khôi phục an toàn.
- Đình chỉ phương thức mật khẩu cũ hoặc yêu cầu xác minh bổ sung khi chính sách quy định.

Không âm thầm coi verifier cũ là mật khẩu gốc. Việc chuyển đổi phải có kế hoạch cho tài khoản không hoạt động, tài khoản đặc quyền và người dùng không còn kênh khôi phục.

## 11. Khi cơ sở dữ liệu verifier bị lộ

Salt và KDF làm chậm việc đoán mật khẩu nhưng không biến verifier thành dữ liệu vô hại. Kẻ tấn công có thể sao chép verifier và thử mật khẩu ngoại tuyến mà không bị rate limit của endpoint đăng nhập.

### Tác động phụ thuộc vào những gì bị lộ

| Dữ liệu bị lộ | Tác động chính | Phản ứng |
|---|---|---|
| Chỉ verifier + salt | Có thể đoán mật khẩu ngoại tuyến | Đánh giá KDF/params, reset theo rủi ro, giám sát credential stuffing |
| Verifier và pepper | Lợi thế bổ sung của pepper mất | Xem là sự cố bí mật; xoay khóa, đánh giá phạm vi, reset/rehash theo kế hoạch |
| Verifier + email/username | Có thể nhắm mục tiêu phishing và credential stuffing | Cảnh báo người dùng, theo dõi đăng nhập bất thường |
| Verifier + token/phiên | Có thể truy cập ngay nếu token còn dùng được | Thu hồi phiên/token, xử lý lộ dữ liệu và credential |
| Backup cũ có plaintext | Mật khẩu bị lộ trực tiếp | Sự cố nghiêm trọng; reset, điều tra nơi backup được sao chép và xử lý lưu trữ |

### Quy trình ứng phó tham khảo

1. Xác định phạm vi, thời điểm và loại dữ liệu bị truy cập; bảo toàn bằng chứng.
2. Cô lập quyền truy cập trái phép và thu hồi credential vận hành/khóa bị lộ.
3. Đánh giá thuật toán, tham số, salt, pepper và mức độ dễ đoán của mật khẩu.
4. Xác định nhóm tài khoản cần reset bắt buộc theo mức rủi ro và yêu cầu áp dụng.
5. Yêu cầu người dùng đặt mật khẩu mới qua kênh chính thức, đồng thời rà soát MFA, passkey và thông tin khôi phục.
6. Thu hồi phiên/refresh token nếu có khả năng chúng cũng bị lộ hoặc bị sử dụng.
7. Theo dõi credential stuffing và thử đăng nhập bằng dữ liệu đã lộ.
8. Rà soát log, quyền truy cập database, backup, secret manager và quy trình triển khai.
9. Thông báo theo chính sách sự cố và yêu cầu pháp lý liên quan.

Không gửi danh sách mật khẩu đã đoán được qua email hoặc ticket. Không yêu cầu người dùng cung cấp mật khẩu hiện tại cho bộ phận hỗ trợ. Nếu cần reset, người dùng tự thiết lập bí mật mới qua kênh xác thực được kiểm soát.

## 12. Các lỗi thiết kế thường gặp

| Lỗi | Vì sao nguy hiểm | Hướng sửa |
|---|---|---|
| Lưu plaintext hoặc mã hóa giải mã được | Rò rỉ kho dữ liệu làm lộ trực tiếp mật khẩu | Chuyển sang password hashing/KDF |
| Dùng SHA-256 một lần | Tốc độ đoán ngoại tuyến rất cao | Argon2id/scrypt/bcrypt/PBKDF2 phù hợp |
| Dùng salt chung | Verifier trùng và hỗ trợ tấn công tính trước | Salt ngẫu nhiên riêng cho mỗi verifier |
| Salt từ username/email | Dễ đoán, không đảm bảo ngẫu nhiên | CSPRNG hoặc thư viện tự sinh |
| Dùng một pepper hardcode trong source | Lộ qua repository/image/log | Secret manager/HSM/KMS, quyền tối thiểu |
| Tham số KDF quá thấp | Giảm chi phí đoán ngoại tuyến | Benchmark và nâng cấp tham số |
| Tham số quá cao, không giới hạn concurrency | DoS qua endpoint đăng nhập | Rate limit, queue/semaphore, đo p95/p99 |
| Tự viết thuật toán hash | Dễ sai và khó kiểm chứng | Thư viện chuyên dụng được duy trì |
| Cắt mật khẩu dài âm thầm | Hai đầu vào khác nhau có thể trở thành cùng giá trị | Kiểm tra byte length và hành vi thư viện |
| Lưu verifier trong log hoặc analytics | Mở thêm nơi rò rỉ dữ liệu đoán ngoại tuyến | Redact, giới hạn quyền và thời hạn log |
| Rehash lại verifier cũ mà không có password | Chỉ bọc hash cũ, không tăng đúng bảo vệ mật khẩu | Rehash sau đăng nhập thành công hoặc reset |
| Đổi mật khẩu nhưng giữ mọi phiên không xem xét | Kẻ tấn công có thể tiếp tục dùng phiên bị chiếm | Thu hồi/đánh giá phiên, refresh token và grant |

## 13. Tình huống thực hành: di trú từ SHA-256 sang Argon2id

**Bối cảnh:** Một ứng dụng cũ lưu \`SHA256(password)\` cùng email trong bảng người dùng. Hệ thống có 80.000 tài khoản; một số người không đăng nhập trong hơn một năm. Đội vận hành muốn chuyển sang Argon2id nhưng không muốn làm gián đoạn tất cả người dùng cùng lúc.

### Phân tích

1. SHA-256 trực tiếp không có chi phí password hashing đủ cao. Nếu database bị lấy, kẻ tấn công có thể thử đoán ngoại tuyến.
2. Không thể tạo Argon2id verifier đúng cho mật khẩu gốc chỉ bằng cách chạy Argon2id trên chuỗi SHA-256 cũ.
3. Tài khoản đăng nhập thành công có thể được rehash ngay vì server đang có mật khẩu người dùng vừa cung cấp.
4. Tài khoản không hoạt động cần chính sách riêng: thời hạn di trú, reset bắt buộc hoặc tiếp tục chấp nhận verifier cũ trong thời gian hạn chế có giám sát.
5. Tài khoản quản trị, tài khoản truy cập dữ liệu nhạy cảm và tài khoản có dấu hiệu bị lộ cần được xử lý ưu tiên.

### Kế hoạch di trú mẫu

| Giai đoạn | Hành động | Tiêu chí hoàn tất |
|---|---|---|
| Chuẩn bị | Triển khai thư viện Argon2id, benchmark params, thêm định dạng/version verifier | Có cấu hình và rollback plan được xem xét |
| Đăng nhập | Xác minh SHA-256 legacy rồi rehash bằng mật khẩu vừa nhập | Verifier mới được lưu, legacy verifier bị thay |
| Giám sát | Đo tỷ lệ tài khoản đã di trú, lỗi KDF, tải và đăng nhập bất thường | Không có tăng lỗi hoặc quá tải ngoài ngưỡng |
| Xử lý tài khoản cũ | Thông báo và yêu cầu reset theo thời hạn/chính sách | Không còn legacy verifier được phép dùng |
| Kết thúc | Gỡ đường xác minh SHA-256 legacy | Mọi tài khoản hoạt động dùng verifier hiện hành |

### Pseudocode cho nâng cấp sau đăng nhập

~~~typescript
async function authenticateAndUpgrade(account, password) {
  const oldVerifier = account.passwordVerifier;
  const valid = await verifyUsingStoredFormat(password, oldVerifier);
  if (!valid) return { authenticated: false };

  if (needsRehash(oldVerifier, CURRENT_PASSWORD_POLICY)) {
    const newVerifier = await createCurrentVerifier(password);

    // Chỉ cập nhật nếu verifier chưa bị yêu cầu khác thay đổi.
    await updateVerifierIfUnchanged({
      accountId: account.id,
      expectedOldVerifier: oldVerifier,
      newVerifier,
    });
  }

  return { authenticated: true };
}
~~~

Hàm \`verifyUsingStoredFormat\`, \`needsRehash\` và \`createCurrentVerifier\` là lớp trừu tượng; triển khai phải dựa trên thư viện đã chọn và định dạng verifier được quản lý. Nếu cập nhật có điều kiện thất bại vì một yêu cầu khác đã thay verifier, không ghi đè dữ liệu mới hơn. Việc xác minh thành công vẫn cần kiểm tra trạng thái tài khoản, MFA và chính sách cấp phiên.

## 14. Checklist triển khai password storage

- [ ] Không lưu mật khẩu dạng rõ hoặc dạng có thể giải mã ngược.
- [ ] Dùng thuật toán password hashing/KDF chuyên dụng và thư viện được duy trì.
- [ ] Mỗi verifier có salt ngẫu nhiên riêng; salt không lấy từ định danh tài khoản.
- [ ] Lưu thuật toán, phiên bản, salt và tham số trong định dạng có thể nâng cấp.
- [ ] Benchmark chi phí KDF theo phần cứng, tải đồng thời và độ trễ thực tế.
- [ ] Rate limit và giới hạn concurrency để endpoint đăng nhập không bị DoS.
- [ ] Nếu dùng pepper, lưu ngoài database, quản lý phiên bản và kế hoạch khôi phục/luân chuyển.
- [ ] Xử lý mật khẩu dài, Unicode, byte length và chuẩn hóa nhất quán.
- [ ] Không cắt mật khẩu âm thầm; kiểm tra giới hạn của thư viện cũ như bcrypt.
- [ ] Rehash sau đăng nhập thành công khi verifier cũ không còn đạt chính sách.
- [ ] Không rehash verifier cũ như thể đó là mật khẩu gốc.
- [ ] Cập nhật verifier có điều kiện để tránh ghi đè do đăng nhập đồng thời.
- [ ] Log không chứa password, verifier không cần thiết, pepper, OTP hoặc token.
- [ ] Backup và bản sao dữ liệu được bảo vệ với quyền truy cập tối thiểu.
- [ ] Có kế hoạch ứng phó database breach và reset theo mức rủi ro.
- [ ] Kiểm thử xác minh sai mật khẩu, tài khoản không tồn tại, verifier sai định dạng và tải KDF cao.

## Ghi nhớ

Password storage an toàn dựa trên **password hashing/KDF chuyên dụng, salt riêng, tham số đủ tốn kém và quản lý verifier có thể nâng cấp**. Pepper có thể bổ sung một ranh giới bảo vệ nếu được quản lý tách biệt và có kế hoạch vận hành rõ ràng. Không dùng hash nhanh, không lưu plaintext và không tự thiết kế thuật toán.

Hãy xem kho verifier như dữ liệu nhạy cảm: nếu bị sao chép, kẻ tấn công có thể đoán ngoại tuyến mà không chịu rate limit của ứng dụng. Thiết kế cần giảm lợi thế đó, hạn chế tải đăng nhập trực tuyến, nâng cấp verifier theo thời gian và có quy trình ứng phó khi dữ liệu xác thực bị lộ.
