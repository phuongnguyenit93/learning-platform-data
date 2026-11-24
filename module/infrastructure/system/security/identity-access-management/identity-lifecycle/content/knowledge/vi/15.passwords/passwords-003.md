# Tạo mật khẩu an toàn trong IAM Identity Lifecycle

## 1. Tạo mật khẩu là gì và nằm ở đâu trong vòng đời danh tính?

**Tạo mật khẩu** (*password creation*) là hành động chọn hoặc sinh một bí mật mà người dùng hoặc hệ thống sẽ dùng làm yếu tố **knowledge-based authentication**: bên đăng nhập phải chứng minh mình biết đúng bí mật đó. Trong hệ thống **Identity and Access Management (IAM)**, việc tạo mật khẩu có thể xảy ra khi người dùng đăng ký lần đầu, kích hoạt tài khoản mới, khôi phục tài khoản, thay đổi phương thức xác thực hoặc khởi tạo một credential dành cho hệ thống cũ.

Bài này thuộc chương **Mật khẩu** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, kết nối quá trình tạo tài khoản và cấp quyền với **Joiner–Mover–Leaver (JML)**, **Identity Provider (IdP), Single Sign-On (SSO), SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và thu hồi quyền truy cập tồn dư**.

Mật khẩu là **thông tin xác thực**, không phải một **định danh** và cũng không phải **quyền nghiệp vụ**:

- **Identity proofing** xác lập mức tin cậy rằng người đăng ký là chủ thể của danh tính được khai.
- **Enrollment** liên kết tài khoản với phương thức xác thực, có thể bao gồm thiết lập mật khẩu.
- **Authentication** kiểm tra người đăng nhập có chứng minh được bí mật theo giao thức hay không.
- **Authorization** kiểm tra danh tính/phiên đã xác thực có được thực hiện hành động trên tài nguyên không.
- **Lifecycle management** quy định khi nào tài khoản và credential được tạo, thay đổi, hạn chế và vô hiệu hóa.

**Tạo được một mật khẩu mạnh không tự động chứng minh danh tính người sở hữu, không bảo đảm an toàn mọi phiên, và không tạo quyền truy cập.** Ngược lại, khi nhân viên nghỉ việc, chỉ đổi mật khẩu cũng không đủ thay cho vô hiệu hóa tài khoản, thu hồi token, phiên và quyền ở các hệ thống đích.

### Các tình huống tạo mật khẩu

| Bối cảnh | Ai khởi tạo? | Điều cần bảo vệ |
|---|---|---|
| Đăng ký tài khoản tự phục vụ | Người dùng, sau các điều kiện của hệ thống | Đúng người, chính sách mật khẩu, bí mật không rò rỉ |
| Joiner doanh nghiệp | HRIS/IAM/IdP điều phối lời mời; người dùng chọn mật khẩu | Không gửi mật khẩu chung cho người mới; liên kết đúng hồ sơ |
| Đổi mật khẩu chủ động | Người dùng đã xác thực | Xác minh phiên đủ mạnh, chống chiếm quyền |
| Đặt lại vì quên | Quy trình recovery được kiểm soát | Không cho kẻ mạo danh thay credential |
| Mật khẩu tạm của ứng dụng legacy | Hệ thống sinh theo chính sách, dùng trong phạm vi hẹp | Thời hạn, kênh bàn giao, buộc thay nếu thích hợp |
| Credential của service account | Owner kỹ thuật và hệ thống quản lý bí mật | Bí mật ngẫu nhiên, vault, quyền tối thiểu, luân chuyển |
| Tài khoản khẩn cấp | Quy trình đặc biệt được phê duyệt | Vault, kiểm soát truy cập, kiểm toán và thử nghiệm định kỳ |

## 2. Mật khẩu mạnh chống lại những rủi ro nào?

Một kẻ tấn công có thể lấy được hoặc đoán mật khẩu thông qua nhiều con đường khác nhau:

| Mối đe dọa | Cách xảy ra | Ý nghĩa đối với tạo mật khẩu |
|---|---|---|
| **Đoán trực tuyến** | Thử nhiều mật khẩu qua trang đăng nhập | Cần chống mật khẩu phổ biến và kiểm soát tốc độ thử |
| **Password spraying** | Thử một vài mật khẩu phổ biến với nhiều tài khoản | Không dùng mẫu chung hoặc mật khẩu mặc định |
| **Credential stuffing** | Dùng tổ hợp tên đăng nhập/mật khẩu bị lộ từ dịch vụ khác | Mỗi tài khoản cần **mật khẩu duy nhất** |
| **Đoán ngoại tuyến** | Kẻ tấn công có hash của mật khẩu và thử đoán tại máy của họ | Tăng độ khó đoán; phía server phải lưu hash bằng thuật toán chuyên dụng |
| **Phishing** | Người dùng nhập mật khẩu vào trang giả | Mật khẩu dài vẫn có thể bị lộ; cần xác thực chống phishing và MFA khi phù hợp |
| **Malware/keylogger** | Thiết bị bị kiểm soát và bí mật bị đánh cắp | Mật khẩu mạnh không thay thế bảo vệ thiết bị/phiên |
| **Lộ qua vận hành** | Credential xuất hiện trong email, log, ticket hoặc repository | Không cấp phát/lưu/truyền bằng kênh không an toàn |
| **Social engineering/recovery abuse** | Kẻ khác lợi dụng quy trình hỗ trợ để đặt lại mật khẩu | Recovery phải kiểm chứng và có audit |

**Độ mạnh của mật khẩu giúp chống đoán**, nhưng không ngăn hoàn toàn phishing, malware hoặc việc server xử lý bí mật sai. Do đó, tạo mật khẩu phải được thiết kế cùng các kiểm soát xác thực và quản lý vòng đời.

## 3. Các nguyên tắc cơ bản khi tạo mật khẩu

Một mật khẩu phù hợp nên có các thuộc tính:

1. **Đủ dài:** độ dài làm tăng không gian tìm kiếm, đặc biệt với chuỗi được chọn ngẫu nhiên từ tập ký tự lớn hoặc passphrase chọn từ danh sách từ đủ rộng.
2. **Khó đoán:** không dựa vào tên, ngày sinh, tên công ty, số điện thoại, tên sản phẩm hay quy luật bàn phím.
3. **Duy nhất cho từng tài khoản:** không tái sử dụng giữa ứng dụng công việc và cá nhân hoặc giữa các hệ thống nội bộ.
4. **Không nằm trong danh sách đã bị lộ hoặc quá phổ biến:** hệ thống kiểm tra danh sách chặn (*blocklist*) theo chính sách.
5. **Được tạo và lưu qua công cụ đáng tin:** password manager, bộ sinh ngẫu nhiên mật mã hoặc quy trình cấp phát có kiểm soát.
6. **Không truyền và lưu như dữ liệu công khai:** tránh chat, email không bảo vệ, tài liệu chia sẻ, source code, log và screenshot.
7. **Phù hợp cơ chế đăng nhập:** kiểm tra trước hạn chế kỹ thuật của hệ thống cũ mà không chấp nhận việc âm thầm cắt ngắn mật khẩu.

**Nhiều loại ký tự không tự bảo đảm một mật khẩu tốt.** Một chuỗi có chữ hoa, chữ thường, số và dấu nhưng theo mẫu dễ đoán vẫn yếu. Ngược lại, một chuỗi dài được sinh ngẫu nhiên hoặc một passphrase được chọn thực sự ngẫu nhiên có thể dễ sử dụng và khó đoán hơn.

### Hai câu hỏi để tự đánh giá

- Người khác có thể đoán nó từ **thông tin cá nhân, tổ chức, từ điển hoặc cấu trúc dễ dự đoán** không?
- Mật khẩu đã xuất hiện ở **một tài khoản hoặc một lần rò rỉ khác** chưa?

Nếu câu trả lời là có hoặc không chắc, nên tạo một mật khẩu mới bằng công cụ đáng tin cậy.

## 4. Ba cách tạo mật khẩu thường gặp

### 4.1. Dùng trình quản lý mật khẩu để sinh ngẫu nhiên

**Password manager** là lựa chọn thuận tiện cho phần lớn tài khoản: công cụ có thể sinh một chuỗi ngẫu nhiên, duy nhất, lưu trong kho được bảo vệ và tự động điền tại đúng ứng dụng.

Cách làm:

1. Chọn password manager được tổ chức cho phép hoặc một công cụ đáng tin cậy cho tài khoản cá nhân.
2. Tại mục tạo credential cho đúng ứng dụng, dùng chức năng **Generate password**.
3. Ưu tiên một mật khẩu ngẫu nhiên dài theo chính sách dịch vụ; không tự thay vài ký tự theo mẫu.
4. Lưu credential cùng tên miền hoặc định danh ứng dụng chính xác trong manager.
5. Xác minh mật khẩu đã được lưu và có thể được dùng đúng nơi trước khi kết thúc phiên thiết lập.
6. Không chia sẻ bản sao qua tin nhắn, tài liệu hay ticket chỉ để “dự phòng”.

Password manager không khiến mọi rủi ro biến mất: tài khoản manager, thiết bị đang sử dụng, khả năng khôi phục và việc đồng bộ kho vẫn cần được bảo vệ theo chính sách.

### 4.2. Passphrase gồm các từ **được chọn ngẫu nhiên**

**Passphrase** là cụm nhiều từ. Nó có thể dễ ghi nhớ hơn chuỗi ký tự lộn xộn, nhưng chỉ có độ khó đoán tốt khi **mỗi từ được lựa chọn ngẫu nhiên, độc lập từ một danh sách đủ lớn**.

Ví dụ sử dụng quy trình kiểu Diceware: tung xúc xắc thật hoặc dùng bộ sinh ngẫu nhiên mật mã để chọn các từ từ một wordlist được thiết kế phù hợp. Tránh lấy lời bài hát, câu nói, khẩu hiệu hoặc một câu tự nghĩ ra, vì các câu quen thuộc dễ được đưa vào từ điển tấn công.

Nếu chọn độc lập \(k\) từ trong danh sách \(N\) từ theo phân phối đều, entropy lý tưởng xấp xỉ:

\[
H \approx k \log_2(N)\ \text{bit}
\]

Ví dụ **sáu từ** chọn độc lập từ wordlist có **7.776 từ** có entropy lý tưởng khoảng **77,5 bit**, giả sử quá trình chọn thực sự ngẫu nhiên và attacker biết phương pháp/danh sách nhưng không biết kết quả. Đây là ví dụ toán học, **không phải bảo đảm an toàn tuyệt đối**; tấn công còn phụ thuộc bảo vệ verifier, rate limiting, mức độ rò rỉ và cách dùng.

### 4.3. Người dùng tự đặt mật khẩu khi không có bộ sinh

Khi bắt buộc tự đặt, ưu tiên **độ dài, tính riêng biệt và khó đoán**, tránh mẫu dễ nhớ phổ biến như viết hoa chữ đầu, thêm số cuối hoặc dùng tên dự án cộng năm. Nếu có thể, nên chuyển sang phương pháp tạo ngẫu nhiên rồi ghi nhớ qua luyện tập hoặc lưu trong password manager.

Người dùng không nên được yêu cầu tạo nhiều mật khẩu chỉ khác nhau ở một ký tự để đáp ứng lịch đổi định kỳ. Những biến thể có quy luật tạo ra rủi ro đoán chéo rất lớn.

## 5. Độ dài, độ ngẫu nhiên và mật khẩu có thể đoán được

**Không gian tìm kiếm** của mật khẩu được sinh đều từ tập \(A\) ký tự, mỗi vị trí độc lập, là \(A^L\) với độ dài \(L\). Mức entropy lý tưởng:

\[
H = L\log_2(A)
\]

Ví dụ lý thuyết:

| Cách sinh | Điều kiện giả định | Độ khó đoán lý tưởng |
|---|---|---|
| 12 ký tự ngẫu nhiên từ 62 ký tự | Bộ sinh mật mã, phân phối đều | Khoảng 71,5 bit |
| 20 ký tự ngẫu nhiên từ 62 ký tự | Bộ sinh mật mã, phân phối đều | Khoảng 119 bit |
| 6 từ chọn độc lập từ 7.776 từ | Wordlist và quy trình chọn ngẫu nhiên | Khoảng 77,5 bit |
| Tên dự án + năm + ký tự đặc biệt | Người tự nghĩ theo mẫu phổ biến | **Không thể gán entropy lý tưởng như chuỗi ngẫu nhiên** |

Các con số chỉ để hiểu sự khác biệt giữa ngẫu nhiên và mẫu dự đoán được. Không nên biến chúng thành khẳng định “mật khẩu này mất X năm để bẻ khóa”, vì tốc độ tấn công phụ thuộc mật mã, cấu hình hashing, khả năng thử trực tuyến, tài nguyên attacker và việc lộ dữ liệu.

Mật khẩu **dài nhưng có cấu trúc phổ biến** vẫn có thể yếu. Mật khẩu **khó gõ nhưng ngắn** cũng không mặc nhiên mạnh. Độ dài kết hợp **quy trình tạo** mới quyết định đáng kể khả năng chống đoán.

## 6. Chính sách tạo mật khẩu của tổ chức

Chính sách mật khẩu cần dựa trên **mô hình đe dọa và hướng dẫn hiện hành**, không chỉ là những quy tắc lịch sử như bắt buộc đổi theo tháng hoặc bắt buộc thêm ký tự đặc biệt.

Các thực hành đáng cân nhắc khi thiết kế verifier:

| Hạng mục | Thiết kế nên hướng tới | Điều cần tránh |
|---|---|---|
| Độ dài tối thiểu | Chọn theo mức assurance, MFA và chuẩn/chính sách áp dụng | Chấp nhận mật khẩu quá ngắn chỉ vì có nhiều loại ký tự |
| Độ dài tối đa | Cho phép mật khẩu dài và passphrase; hỗ trợ tối thiểu mức theo chuẩn áp dụng | Cắt ngắn âm thầm hoặc giới hạn thấp bất hợp lý |
| Blocklist | Từ chối mật khẩu phổ biến, bị lộ hoặc dễ suy ra từ tên dịch vụ | Chỉ kiểm tra có chữ hoa/số/ký hiệu |
| Composition rules | Ưu tiên độ dài và blocklist hơn các mẫu ép buộc | Buộc đổi một ký tự hoa, số và dấu theo cách dễ đoán |
| Đổi mật khẩu | Yêu cầu khi bị lộ, bị nghi chiếm quyền, recovery hoặc chính sách có căn cứ | Ép thay định kỳ vô điều kiện làm người dùng tạo mẫu tuần tự |
| Paste/autofill | Cho phép dán và dùng password manager | Chặn paste khiến người dùng chọn mật khẩu dễ gõ và yếu |
| Unicode và dấu cách | Xử lý đúng theo chuẩn, đặc tính hệ thống và nhất quán nhập/xác minh | Biến đổi bí mật không rõ ràng hoặc cắt ngắn theo byte |
| Rate limiting | Giới hạn thử sai trực tuyến và phát hiện tấn công | Dựa vào độ dài mật khẩu để bỏ qua bảo vệ đăng nhập |

Ví dụ, khi tổ chức áp dụng **NIST SP 800-63B**, cần đối chiếu đúng **ấn bản đang được chấp nhận và điều kiện một yếu tố/đa yếu tố** khi đặt mức tối thiểu. Không tuyên bố một hệ thống đạt chuẩn chỉ vì nó đáp ứng một hàng trong bảng; chuẩn còn có yêu cầu về xác thực, bảo vệ verifier và vận hành.

**Không nên ép người dùng thay mật khẩu theo lịch nếu không có dấu hiệu hoặc yêu cầu có căn cứ**, vì dễ tạo biến thể dễ đoán. Khi phát hiện credential bị lộ hoặc nghi bị chiếm quyền, phải kích hoạt quá trình thay đổi/thu hồi phù hợp, không đợi tới kỳ tiếp theo.

## 7. Mật khẩu có bị lộ hoặc nằm trong blocklist không?

Khi người dùng đặt mật khẩu, verifier nên **so sánh với danh sách giá trị yếu và đã biết bị lộ** theo quy trình được thiết kế bảo vệ bí mật. Danh sách có thể bao gồm:

- Mật khẩu phổ biến trong các bộ dữ liệu bị lộ và các biến thể hay gặp.
- Tên dịch vụ, tên tổ chức, tên đăng nhập và các chuỗi dễ suy ra trong bối cảnh.
- Mẫu bàn phím và các chuỗi tuần tự phổ biến.
- Mật khẩu mặc định đã từng dùng ở hệ thống hoặc thiết bị liên quan.

Nếu mật khẩu bị từ chối, phản hồi cho người dùng nên giải thích **nguyên nhân ở mức an toàn** và hướng dẫn tạo một mật khẩu mạnh hơn. Không lặp lại mật khẩu thô trong thông báo hoặc log.

**Không gửi plaintext password tới API kiểm tra rò rỉ bên ngoài một cách tùy tiện.** Nếu cần kiểm tra với dịch vụ bên thứ ba, phải sử dụng giải pháp và mô hình bảo vệ được tổ chức đánh giá, ví dụ kỹ thuật tra cứu băm theo tiền tố hoặc cơ chế tương đương nếu phù hợp, hiểu rõ giới hạn bảo mật và dữ liệu gửi ra ngoài.

## 8. Tạo mật khẩu bằng bộ sinh mật mã

Với mật khẩu do hệ thống sinh, cần dùng **Cryptographically Secure Pseudorandom Number Generator (CSPRNG)**. Trong Java, **SecureRandom** là một lựa chọn chuẩn; không dùng **Math.random()**, giá trị thời gian, tên người hoặc một pseudo-random generator thông thường để sinh credential bảo mật.

Ví dụ Java tạo mật khẩu ngẫu nhiên từ tập ký tự cho phép:

~~~java
import java.security.SecureRandom;

public final class PasswordGenerator {
    // Chọn ký tự mà hệ thống đích chấp nhận; ví dụ chỉ dùng chữ và số.
    private static final char[] ALPHABET =
            "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
                    .toCharArray();
    private static final SecureRandom RNG = new SecureRandom();

    private PasswordGenerator() {}

    public static char[] generate(int length) {
        if (length < 16) {
            throw new IllegalArgumentException("Length below local policy");
        }

        char[] password = new char[length];
        for (int i = 0; i < length; i++) {
            password[i] = ALPHABET[RNG.nextInt(ALPHABET.length)];
        }
        return password;
    }
}
~~~

### Vì sao mẫu này phù hợp với mục đích minh họa?

- **SecureRandom** cung cấp nguồn ngẫu nhiên phù hợp cho tác vụ mật mã trong môi trường Java được cấu hình và vận hành đúng.
- **nextInt(bound)** chọn chỉ số trong phạm vi tập ký tự mà không dùng phép modulo tự chế gây thiên lệch.
- Tập ký tự được định nghĩa rõ; không phụ thuộc vào giá trị ngẫu nhiên từ thời gian hoặc ID.
- Mật khẩu được trả về dạng **char[]** để bên gọi có thể cố gắng xóa bộ đệm sau khi sử dụng. Dù vậy, **char[] không bảo đảm mọi bản sao trong runtime/SDK đã được xóa**.
- Ví dụ dùng ngưỡng dài tối thiểu **16 ký tự như một chính sách minh họa của đoạn code**, không phải mức bắt buộc áp cho mọi hệ thống hoặc mọi tiêu chuẩn.

### Những giới hạn cần chú ý

**Không log, không in ra console, không gửi mật khẩu qua email hoặc lưu vào source code.** Đoạn code chỉ sinh bí mật; nó không chứng minh việc **cấp phát, trao nhận, lưu trữ, xoay vòng hoặc thu hồi** đã an toàn.

Nếu hệ thống đích bắt buộc lớp ký tự cụ thể, cần thiết kế thuật toán đáp ứng policy mà không vô tình giảm entropy hoặc tạo phân phối không mong muốn. Nên cân nhắc thay đổi chính sách nếu yêu cầu composition cũ gây khó dùng mà không tăng bảo mật hữu ích.

**Không tự xây lại thuật toán mật mã hoặc bộ sinh ngẫu nhiên** nếu có thư viện đáng tin cậy và được duyệt. Với account người dùng, thông thường nên để **người dùng đặt mật khẩu qua luồng IdP** hoặc dùng password manager, thay vì tổ chức tự tạo rồi phân phát plaintext.

## 9. Tạo mật khẩu khi Joiner và identity enrollment

Khi nhân viên mới gia nhập, quy trình có thể dùng **HRIS → IAM/IGA → IdP → ứng dụng**. Tạo mật khẩu là **một bước enrollment** trong đó, không nên bị biến thành “IT tạo cùng một mật khẩu rồi gửi qua email”.

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant IAM as IAM / IGA
    participant IDP as IdP / Enrollment
    participant U as Người dùng
    participant APP as Ứng dụng đích
    HR->>IAM: Joiner event + identity ID + effectiveAt
    IAM->>IAM: Xác minh nguồn, quan hệ, quyền baseline
    IAM->>IDP: Chuẩn bị identity / policy
    IDP-->>U: Mời vào kênh enrollment được phê duyệt
    U->>IDP: Xác minh điều kiện và tạo mật khẩu riêng
    IDP->>IDP: Kiểm tra policy + blocklist, lưu verifier an toàn
    IDP-->>IAM: Enrollment state đã được xác minh
    IAM->>APP: Provision account + quyền theo RBAC/ABAC
    APP-->>IAM: Kết quả/đối soát trạng thái
    IAM-->>U: Thông báo hoàn tất đúng phạm vi
~~~

### Luồng an toàn hơn việc gửi mật khẩu ban đầu

1. Nguồn nhân sự tạo bản ghi và kênh liên hệ được kiểm tra theo chính sách.
2. IAM xác minh định danh và điều kiện trước khi cấp account.
3. IdP phát **lời mời có phạm vi và thời hạn**, thay vì gửi một mật khẩu cố định cho cả nhóm Joiner.
4. Người nhận đi qua quy trình kiểm chứng danh tính/kênh cần thiết, rồi đặt **mật khẩu duy nhất** theo chính sách hoặc đăng ký authenticator thay thế.
5. IdP kiểm tra chính sách và lưu **verifier thích hợp**, không gửi plaintext password về HRIS, IAM, SCIM connector hoặc manager.
6. IAM cấp quyền theo role/attribute và chỉ xác nhận hoàn tất khi các bước cần thiết đạt.

**Một email đã được gửi không chứng minh đúng người đã nhận lời mời.** Kênh enrollment và proofing phải bảo đảm việc đăng ký mật khẩu không bị chuyển cho người khác.

## 10. Mật khẩu tạm: khi nào và sử dụng thế nào?

Một số hệ thống legacy vẫn yêu cầu **temporary password** khi tạo user. Đây nên là giải pháp có kiểm soát, không phải lựa chọn mặc định cho hệ thống IdP hiện đại.

| Rủi ro của mật khẩu tạm | Kiểm soát phù hợp |
|---|---|
| Nhân viên IT có thể biết mật khẩu | Ưu tiên quy trình không lộ plaintext; giới hạn người thấy khi không thể tránh |
| Mật khẩu bị gửi nhầm người | Kiểm tra kênh và danh tính trước khi bàn giao |
| Mật khẩu tồn tại quá lâu | Thời hạn ngắn, hủy khi không sử dụng hoặc khi quan hệ bị hủy |
| Mật khẩu bị tái sử dụng | Sinh ngẫu nhiên riêng cho từng account, không dùng giá trị chung |
| Bị dùng để bỏ qua proofing | Yêu cầu bước liên kết danh tính/đăng nhập phù hợp trước khi trao credential |
| Không đổi sau kích hoạt | Nếu là quy trình tạm thời, ép đặt credential riêng theo chính sách |
| Credential còn hiệu lực sau Leaver | Deactivate, revoke session/token, xử lý ứng dụng local và đối soát |

Một **temporary password** dù ngẫu nhiên vẫn có thể là bearer secret: người biết có thể sử dụng nó. Vì vậy, không nên mặc nhiên cho rằng **“buộc đổi ở lần đăng nhập đầu tiên”** là đủ nếu kẻ khác có thể dùng mật khẩu tạm trước người được mời.

Khi không thể dùng luồng đặt mật khẩu trực tiếp tại IdP, nên áp dụng phương thức bàn giao riêng được tổ chức phê duyệt, kiểm chứng đúng người, giới hạn thời gian và lưu bằng chứng **không chứa mật khẩu thô**.

## 11. Mật khẩu được lưu ở phía verifier như thế nào?

**Tạo mật khẩu và lưu trữ mật khẩu là hai bài toán khác nhau nhưng liên quan chặt chẽ.** Verifier không nên giữ plaintext password để so sánh hoặc cho nhân viên hỗ trợ “xem lại”.

Thay vào đó, hệ thống dùng một **password hashing/KDF chuyên dụng, có salt ngẫu nhiên riêng**, với thông số chi phí được lựa chọn và duy trì theo môi trường, ví dụ **Argon2id, scrypt, bcrypt hoặc PBKDF2** tùy yêu cầu nền tảng và tuân thủ. Không dùng SHA-256 thuần hoặc MD5 thuần như giải pháp lưu password.

### Kiến trúc khái quát

~~~mermaid
flowchart LR
    U[Người dùng tạo mật khẩu] --> T[Luồng HTTPS và kiểm tra chính sách]
    T --> H[Password KDF + salt riêng + thông số chi phí]
    H --> DB[Lưu verifier, salt, thuật toán và tham số]
    DB --> A[Kiểm tra đăng nhập tương lai]
    A --> C{Kết quả xác thực + rate limit}
    C -->|Hợp lệ| S[Tạo phiên theo chính sách]
    C -->|Không hợp lệ| R[Từ chối / kiểm soát thử sai]
~~~

**Salt** không cần bí mật nhưng phải đủ ngẫu nhiên và riêng biệt để cản các cuộc tấn công dùng bảng tính sẵn và giảm khả năng so sánh cùng mật khẩu giữa account. **Pepper** là một bí mật bổ sung ở phía verifier khi thiết kế yêu cầu, phải được lưu tách biệt trong vùng bảo vệ như HSM/secret manager; nó **không thay thế salt hoặc KDF đúng**.

### Các lưu ý thực thi

- Tạo **salt riêng** cho mỗi credential; không dùng một salt cố định toàn tổ chức.
- Chọn độ khó tính toán dựa trên chính sách và khả năng server, kèm kiểm thử tải và kế hoạch điều chỉnh.
- Lưu metadata về thuật toán, tham số và version để nâng cấp về sau.
- Với bcrypt, lưu ý các giới hạn đầu vào của triển khai (thường có giới hạn **72 byte**); không âm thầm cắt ngắn mật khẩu dài. Kiểm tra thư viện/cơ chế tiền xử lý phù hợp.
- Đối với Unicode, phải có quy tắc xử lý nhất quán giữa tạo và xác minh, theo tiêu chuẩn/chính sách áp dụng; tránh khác biệt ngoài ý muốn khiến mật khẩu không xác minh được.
- Bảo vệ đường truyền và các nơi trung gian; hạn chế xuất plaintext vào log, trace, error message hoặc crash dump.
- Kiểm soát truy cập dữ liệu verifier, sao lưu và quy trình khôi phục; **hash không làm database chứa credential trở thành dữ liệu công khai**.

Trong nền tảng doanh nghiệp, một ứng dụng dùng **SSO** thường **không cần sở hữu một mật khẩu riêng của nhân viên**. Nếu có thể, nên dùng IdP và federation để giảm số mật khẩu cần tạo/lưu ở các ứng dụng đích.

## 12. Khác biệt giữa mật khẩu, MFA và passkey

**Mật khẩu** là một yếu tố “biết” (*something you know*). Nó có thể là thành phần của **Multi-Factor Authentication (MFA)** khi kết hợp một yếu tố độc lập khác theo yêu cầu.

**Passkey/FIDO2/WebAuthn** sử dụng mật mã khóa công khai; trong thiết kế phù hợp, chúng có thể cung cấp xác thực chống phishing tốt hơn mật khẩu truyền thống. Tuy nhiên việc triển khai, đồng bộ, phục hồi và cấp quyền vẫn cần chính sách.

| Phương thức | Điểm mạnh | Giới hạn/nhu cầu bổ sung |
|---|---|---|
| Mật khẩu dài, duy nhất | Hỗ trợ rộng, triển khai đơn giản | Có thể bị phishing, lộ hoặc tái sử dụng |
| Mật khẩu + MFA phù hợp | Thêm lớp chứng minh khi mật khẩu bị biết | Không phải MFA nào cũng chống phishing |
| Passkey/WebAuthn | Xác thực dựa vào khóa công khai và ràng buộc nguồn gốc của RP | Cần enrollment, quản lý thiết bị/khóa, recovery |
| Workload identity/secret ngắn hạn | Phù hợp máy–máy, giảm mật khẩu tĩnh | Cần hạ tầng tin cậy và chính sách cấp/thu hồi |

**Chọn mật khẩu mạnh vẫn cần thiết khi tổ chức còn dùng mật khẩu**, nhưng không nên coi mật khẩu là biện pháp bảo mật duy nhất cho quyền quản trị hoặc dữ liệu nhạy cảm.

## 13. Đổi mật khẩu và khôi phục tài khoản

**Đổi mật khẩu** là thao tác mà người dùng đã xác thực hợp lệ chủ động thực hiện; **đặt lại mật khẩu (reset)** có thể xảy ra khi người dùng không còn chứng minh được bí mật cũ. Hai quy trình có mức rủi ro khác nhau.

### Luồng đổi mật khẩu

- Xác minh phiên hiện tại và yêu cầu **step-up authentication** khi rủi ro hoặc chính sách đòi hỏi.
- Kiểm tra mật khẩu mới theo độ dài, blocklist và yêu cầu phù hợp.
- Ngăn tái sử dụng credential theo chính sách mà không lưu lịch sử plaintext.
- Lưu verifier mới bằng KDF thích hợp; cập nhật metadata và ghi log **không chứa giá trị mật khẩu**.
- Đánh giá thu hồi hoặc làm mới session/token theo chính sách rủi ro và năng lực hệ thống.
- Gửi cảnh báo thay đổi qua kênh tin cậy khi phù hợp để chủ tài khoản phát hiện thao tác bất ngờ.

### Luồng đặt lại mật khẩu

Reset có thể là con đường **chiếm quyền tài khoản** nếu helpdesk gửi link hoặc credential cho người mạo danh. Cần xác minh danh tính/kênh đủ mạnh theo mức rủi ro, token một lần có thời hạn, rate limiting và kiểm toán.

**Không sử dụng câu hỏi bí mật dễ đoán** như tên trường học hoặc ngày sinh như bằng chứng bảo mật mạnh. Tránh đặt lại mật khẩu chỉ vì ai đó biết email hoặc số điện thoại của người dùng. Đặc biệt, nếu kẻ tấn công đang kiểm soát email cá nhân, việc chỉ gửi link qua email đó có thể chưa đáp ứng yêu cầu của tài khoản nhạy cảm.

### Khi nghi mật khẩu bị lộ

Mật khẩu mới cần được thiết lập qua luồng đáng tin; đồng thời đánh giá **phiên còn hoạt động, refresh token, thiết bị, MFA registration, recovery method, các tài khoản khác có nguy cơ dùng chung mật khẩu** và log bất thường. Đổi mật khẩu mà không xử lý session hoặc token bị chiếm có thể để lại đường truy cập.

## 14. Tạo mật khẩu trong Joiner–Mover–Leaver

### 14.1. Joiner: bắt đầu với credential riêng

HRIS phát sự kiện Joiner, IAM/IGA xác lập danh tính, IdP tạo account theo chính sách. Người mới nên **tự đặt mật khẩu qua enrollment an toàn** hoặc nhận authenticator khác được phép, thay vì dùng cùng một giá trị do quản trị viên biết trước. Nếu có temporary password, phải là ngẫu nhiên, riêng, ngắn hạn và được trao qua quy trình được phê duyệt.

Quyền nghiệp vụ cấp theo **RBAC/ABAC** và approval, không dựa trên việc người dùng “đã đổi mật khẩu”. **Enrollment completed** và **access provisioning confirmed** là các mốc độc lập.

### 14.2. Mover: thay vai trò không tự động yêu cầu đổi mọi mật khẩu

Người dùng chuyển từ Sales sang Finance phải được **thu hồi quyền Sales** và cấp quyền Finance hợp lệ. Việc chuyển vai trò **không tự khiến mật khẩu hiện tại yếu đi** và không mặc nhiên cần ép đổi toàn bộ password.

Tuy vậy, nên đánh giá tăng cường xác thực hoặc đổi credential nếu:

- Người dùng sắp nhận quyền đặc biệt và chính sách yêu cầu thêm yếu tố hoặc step-up.
- Mật khẩu có dấu hiệu lộ, từng được chia sẻ hoặc có lý do tin rằng chủ thể cũ biết credential.
- Có thay đổi thiết bị, chính sách bảo mật hoặc phát hiện sự cố xác thực.
- Người dùng từng sở hữu secret, shared account hay credential mà vai trò mới không còn cần.

**Quyền cũ cần được thu hồi độc lập**, kể cả khi người dùng không phải đổi mật khẩu.

### 14.3. Leaver: vô hiệu hóa và đối soát, không chỉ đổi password

Khi nhận sự kiện Leaver có hiệu lực, IAM phải xử lý **account IdP, các phiên/token, quyền hệ thống đích, API key, SSH key, VPN, ứng dụng local và các credential liên quan** theo chính sách.

Chỉ đổi mật khẩu của nhân viên có thể không chặn:

- Phiên SSO hoặc phiên ứng dụng đã được cấp.
- Refresh token và access token còn hiệu lực.
- SSH key hoặc PAT gắn riêng vào dịch vụ.
- Tài khoản local khác hoặc tài khoản cloud không đồng bộ.
- Secret dùng chung mà người rời đi biết.

Cần ưu tiên **cắt truy cập đúng hạn và xác minh kết quả tại từng hệ thống đích**. Nếu một tài khoản buộc phải giữ bản ghi để lưu dữ liệu, trạng thái của nó phải không cho phép sử dụng ngoài phạm vi được duyệt.

### 14.4. Rejoiner: tránh tái dùng credential cũ

Nếu người cũ quay lại, có thể dùng lại identity record gốc để giữ lịch sử, nhưng phải kiểm tra quan hệ mới, proofing/enrollment theo chính sách, trạng thái credential và quyền mới. Không tự động mở lại account cũ với password/token/role cũ.

## 15. Mật khẩu của service account và thiết bị

**Service account, bot, thiết bị và workload identity** không giống tài khoản nhân viên. Nếu có thể, nên ưu tiên **workload identity federation, managed identity, certificate hoặc token ngắn hạn** thay cho mật khẩu tĩnh. Khi ứng dụng legacy vẫn bắt buộc password, cần quản lý nghiêm ngặt.

| Vấn đề | Cách thực hành |
|---|---|
| Nhiều dịch vụ dùng chung một mật khẩu | Cấp credential riêng theo service/workload và môi trường khi có thể |
| Secret nằm trong source code hoặc CI logs | Dùng secret manager/vault và cơ chế truy xuất theo danh tính workload |
| Nhân viên rời đi từng biết password | Rà soát owner, quyền, xoay secret cần thiết và kiểm tra phụ thuộc |
| Mật khẩu hết hạn làm ngừng batch | Luân chuyển có kế hoạch, triển khai trước vào ứng dụng phụ thuộc rồi xác minh |
| Secret còn hiệu lực dù workload đã ngừng | Thu hồi credential và quyền tại đích, kiểm tra tài khoản mồ côi |
| Thiết bị tái cấp/thải loại | Vô hiệu hóa chứng chỉ, device account, secret và chính sách mạng liên quan |
| Emergency account ít khi dùng | Bảo vệ trong vault, giám sát, thử nghiệm và rà soát theo chính sách |

Với mật khẩu của service account, **sinh ngẫu nhiên bằng CSPRNG, dùng độ dài lớn theo khả năng đích, quản lý quyền truy cập vault và luân chuyển theo rủi ro** là những nguyên tắc quan trọng. Việc tự động luân chuyển phải được kiểm thử để tránh làm mất kết nối hệ thống sản xuất.

Không nên nhầm **owner** của account với **người duy nhất được phép sử dụng**; bot có thể tiếp tục hợp lệ khi owner thay đổi. Leaver của owner cần dẫn đến **chuyển giao trách nhiệm và xử lý bí mật** hơn là xóa mù quáng mọi service account.

## 16. Thiết kế UX cho màn hình tạo mật khẩu

Một màn hình đặt mật khẩu tốt phải bảo vệ hệ thống **và** giúp người dùng chọn credential đúng:

- Hiển thị rõ yêu cầu độ dài, giới hạn kỹ thuật và gợi ý dùng password manager/passphrase.
- Nếu có kiểm tra blocklist, thông báo an toàn khi không đạt mà không lộ giá trị đã nhập.
- Cho phép **paste/autofill** để hỗ trợ mật khẩu ngẫu nhiên dài.
- Có tùy chọn hiển thị/ẩn mật khẩu tại thiết bị người dùng khi cần, với thiết kế tránh lộ vô ý.
- Đặt trọng tâm vào **tính duy nhất và khả năng chống đoán**, không chỉ biểu đồ “mạnh” dựa trên đếm chữ hoa/số.
- Không gửi giá trị mật khẩu thô qua analytics, error monitoring hoặc network không được bảo vệ.
- Sử dụng quy trình đổi/reset dễ nhận diện, có thông báo khi credential bị thay bất ngờ.
- Bảo vệ khỏi tấn công thử sai và enumeration nhưng không khóa người dùng theo cách tạo đường DoS không kiểm soát.
- Đảm bảo hỗ trợ người dùng khuyết tật, bàn phím di động, dấu cách và phương thức nhập trong chính sách.

**Cảnh báo về password strength meter:** một thanh báo “mạnh” không thể tính đầy đủ mức độ rò rỉ hoặc đoán được của bí mật. Không dùng nó thay cho blocklist và chính sách của verifier.

## 17. Các sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao không an toàn | Cách sửa |
|---|---|---|
| Dùng tên công ty cộng năm | Dễ nằm trong danh sách đoán theo ngữ cảnh | Sinh ngẫu nhiên hoặc passphrase ngẫu nhiên |
| Một password cho nhiều hệ thống | Lộ một nơi gây credential stuffing nơi khác | Mỗi tài khoản một bí mật duy nhất |
| Chỉ ép chữ hoa/số/ký hiệu | Người dùng dễ tạo mẫu cố định | Ưu tiên độ dài, blocklist, chống thử sai |
| Đổi bắt buộc mỗi tháng vô điều kiện | Thúc đẩy biến thể có quy luật và ghi chép ngoài hệ thống | Đổi khi có căn cứ hoặc theo chính sách rủi ro phù hợp |
| Sinh password bằng Math.random() | Không phù hợp tạo bí mật mật mã | Dùng CSPRNG như SecureRandom |
| Gửi password tạm qua email chung | Người khác có thể đọc hoặc chuyển tiếp | Luồng enrollment trực tiếp, kênh bàn giao được kiểm chứng nếu bắt buộc |
| In password vào log | Bí mật bị sao chép sang hệ thống quan sát | Redact, không log secret |
| Lưu SHA-256/MD5 thuần | Quá nhanh cho phòng thủ trước đoán ngoại tuyến | Dùng password KDF có salt và tham số phù hợp |
| Cắt ngắn password quá dài không báo | Hai bí mật khác nhau có thể trở thành tương đương | Xử lý giới hạn rõ, không truncate âm thầm |
| Chặn copy/paste | Cản password manager và thúc đẩy password dễ gõ | Cho phép paste/autofill |
| Cho helpdesk đổi mật khẩu chỉ dựa vào email | Recovery dễ bị mạo danh | Xác minh theo mức rủi ro, kênh có thẩm quyền |
| Chỉ đổi password khi Leaver | Phiên, token và quyền khác có thể vẫn hoạt động | Deprovision + revoke + readback toàn scope |
| Dùng secret chung cho bot | Một vụ lộ ảnh hưởng nhiều workload | Secret riêng, vault, quyền tối thiểu và luân chuyển |

## 18. Tình huống thực tế: từ Joiner đến Leaver

Giả sử **Lan** gia nhập tổ chức ngày **01/12/2026** ở vị trí phân tích dữ liệu.

**Bước 1 — Joiner:** HRIS gửi hồ sơ đã xác minh theo chính sách cùng mã person ID bền vững. IAM điều phối khởi tạo tài khoản IdP ở trạng thái phù hợp với ngày bắt đầu, không phát một mật khẩu dùng chung qua email.

**Bước 2 — Enrollment:** Lan nhận lời mời qua kênh đã được kiểm tra, mở cổng IdP chính thức, thực hiện proofing khi cần và tạo mật khẩu ngẫu nhiên riêng bằng password manager. IdP kiểm tra chính sách và blocklist, lưu verifier được bảo vệ; Lan đăng ký MFA theo yêu cầu.

**Bước 3 — Provisioning:** IAM tính baseline RBAC/ABAC, đồng bộ account và nhóm đến các ứng dụng qua SCIM hoặc connector tương ứng. Việc đặt mật khẩu thành công **không tự tạo quyền xem báo cáo**; quyền này chỉ có khi hệ thống đích xác nhận.

**Bước 4 — Mover:** Sau ba tháng, Lan chuyển sang nhóm phụ trách dữ liệu nhạy cảm. IAM thu hồi nhóm cũ và cấp nhóm mới sau phê duyệt. Chính sách có thể yêu cầu authenticator mạnh hơn hoặc step-up; không bắt buộc đổi mật khẩu chỉ vì chuyển bộ phận nếu không có căn cứ.

**Bước 5 — Sự cố:** Hệ thống phát hiện mật khẩu Lan đã xuất hiện trong dữ liệu bị lộ hoặc có dấu hiệu bị chiếm. IAM yêu cầu thay credential bằng luồng an toàn và đánh giá session/token, MFA, thiết bị, log bất thường và các account có nguy cơ tái dùng.

**Bước 6 — Leaver:** Lan nghỉ việc. IdP bị vô hiệu hóa theo effectiveAt, các phiên và token được xử lý theo năng lực hệ thống, các tài khoản/quyền khác được deprovision và readback. Nếu Lan từng biết password của bot đồng bộ, đội vận hành chuyển owner và luân chuyển secret khi cần.

**Bước 7 — Rehire:** Một năm sau Lan trở lại. Dù có thể giữ identity ID để nối lịch sử, tổ chức phải xác minh quan hệ mới và enrollment/credential theo chính sách, không tự dùng lại password, phiên hay quyền đã bị thu hồi.

Tình huống này cho thấy tạo password chỉ là **khởi điểm của vòng đời credential**, không phải biện pháp kiểm soát toàn bộ vòng đời truy cập.

## 19. Checklist khi thiết kế quy trình tạo mật khẩu

1. **Tài khoản nào cần password?** Có thể dùng SSO, passkey, managed identity hoặc federation thay cho password riêng không?
2. **Ai tạo password?** Người dùng tự đặt qua IdP hay hệ thống phải sinh temporary password? Có quy trình xác minh đúng chủ thể?
3. **Đủ khó đoán?** Password được sinh CSPRNG hoặc passphrase ngẫu nhiên, độ dài phù hợp và không dựa vào thông tin cá nhân?
4. **Duy nhất?** Có hướng dẫn và công cụ ngăn tái sử dụng giữa dịch vụ?
5. **Policy tốt?** Có yêu cầu độ dài, blocklist và thông báo dễ hiểu; tránh composition/rotation vô điều kiện thiếu căn cứ?
6. **Bảo vệ khi nhập?** HTTPS, chống enumeration/thử sai, không đẩy secret sang analytics/log?
7. **Bảo vệ khi lưu?** Verifier dùng password KDF với salt riêng và tham số hợp lý, không lưu plaintext hoặc hash nhanh?
8. **Password manager?** Có cho phép paste/autofill và hỗ trợ tạo credential đủ dài không?
9. **Mật khẩu khởi tạo?** Có phạm vi, thời hạn, thu hồi và kênh bàn giao đã kiểm chứng, không gửi chung plaintext?
10. **Reset và đổi?** Có kiểm tra identity/phiên đúng mức, xử lý session và alert khi nghi bị chiếm?
11. **JML?** Joiner tạo đúng credential, Mover rà soát role, Leaver khóa account/phiên/token và quyền chứ không chỉ đổi password?
12. **Phi con người?** Service/device secrets nằm trong vault hoặc cơ chế danh tính máy, có owner và luân chuyển phù hợp?
13. **Đối soát?** Sau tạo/đổi/thu hồi có kiểm tra trạng thái thực tế ở IdP và ứng dụng đích không?
14. **Kiểm toán?** Có log sự kiện, kết quả và chủ thể thực hiện mà **không chứa mật khẩu thô** không?
15. **Trải nghiệm người dùng?** Có thể làm đúng quy trình mà không cần chia sẻ secret, dùng mật khẩu yếu hoặc dựa vào kênh không rõ nguồn?

### Ghi nhớ

**Tạo mật khẩu tốt nghĩa là tạo một bí mật dài, khó đoán, duy nhất và bảo vệ nó xuyên suốt từ lúc được chọn đến khi bị thay thế hoặc thu hồi.** Với người dùng, password manager và passphrase chọn ngẫu nhiên thường hỗ trợ tốt hơn các mẫu tự nghĩ; với hệ thống, cần CSPRNG, quy trình enrollment đáng tin, verifier hashing phù hợp và không làm lộ plaintext. Trong **IAM Identity Lifecycle**, mật khẩu phải được quản lý cùng **IdP/SSO, MFA, RBAC/ABAC, provisioning và Joiner–Mover–Leaver**, đặc biệt là **thu hồi và xác minh mọi đường truy cập tồn dư khi quan hệ kết thúc**.
