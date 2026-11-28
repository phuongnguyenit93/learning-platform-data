# Chọn key size trong mật mã đối xứng

## 1. Vì sao phải chọn đúng kích thước khóa?

**Key size (key length, độ dài khóa)** là số bit của khóa mật mã theo định nghĩa của thuật toán. Trong mã hóa đối xứng, các bên được phép dùng cùng một khóa bí mật để mã hóa và giải mã dữ liệu. Chọn kích thước khóa là một quyết định thiết kế: khóa phải đủ mạnh trước mô hình đe dọa dự kiến, phù hợp thời gian cần bảo vệ dữ liệu và được các thành phần thực tế hỗ trợ.

Ví dụ, AES cho phép ba độ dài khóa: **128, 192 và 256 bit**. Cả ba đều là lựa chọn được định nghĩa bởi AES; không có quy tắc rằng mọi hệ thống bắt buộc dùng 256 bit. Một hệ thống có yêu cầu bảo vệ dữ liệu lâu dài có thể ưu tiên AES-256; một giao thức đã được thẩm định và thiết kế ở mức an toàn 128 bit có thể chọn AES-128. Điều quan trọng là hiểu rõ **mức an toàn cần đạt** và kiểm tra toàn bộ kiến trúc, thay vì chỉ nhìn con số trong tên thuật toán.

Trong chương **Mật mã đối xứng** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, việc chọn key size phải gắn với cả vòng đời quản lý khóa: tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy. Một khóa AES-256 bị ghi trong log hoặc bị cấp quyền giải mã cho mọi dịch vụ có thể gây rủi ro lớn hơn một khóa AES-128 được sinh và bảo vệ đúng cách.

**Mục tiêu học tập:** Sau bài này, bạn có thể phân biệt key size với các thông số mật mã khác, chọn giữa AES-128/192/256 theo yêu cầu thực tế, triển khai đúng độ dài khóa trong Java, đồng thời lập kế hoạch đổi kích thước khóa mà không làm mất khả năng giải mã dữ liệu cũ.

## 2. Các khái niệm cần phân biệt

### 2.1. Key size, key space và security strength

Với khóa bí mật dài \(n\) bit được chọn **đồng đều, độc lập** trong toàn bộ không gian giá trị, số khóa khả dĩ là:

\[
|K| = 2^n
\]

Do đó, khóa 128 bit có \(2^{128}\) giá trị khả dĩ, trong khi khóa 256 bit có \(2^{256}\) giá trị. Nếu chỉ xét thử toàn bộ khóa bằng vét cạn trong mô hình cổ điển, tăng độ dài làm số ứng viên tăng theo cấp số mũ.

Tuy nhiên, **key space** là số giá trị có thể biểu diễn, còn **security strength** là mức khó tấn công ước lượng trong những giả định xác định. Với một thuật toán đối xứng đủ mạnh và khóa được sinh chuẩn, độ mạnh chống dò khóa thường gần với độ dài khóa. Trong thực tế, mức an toàn có thể thấp hơn do thuật toán, mode, số lần sử dụng, cách sinh khóa hoặc lỗi triển khai.

| Khái niệm | Nghĩa | Sai lầm thường gặp |
| --- | --- | --- |
| **Key size** | Số bit khóa mà thuật toán nhận | Thấy chuỗi 32 byte thì mặc nhiên coi là khóa mạnh 256 bit |
| **Key space** | Tập khóa khả dĩ về mặt biểu diễn | Tưởng ứng dụng chắc chắn sinh khóa đều trên toàn bộ tập này |
| **Entropy** | Mức khó đoán thực tế của khóa hoặc nguồn sinh khóa | Đệm mật khẩu ngắn thành 32 byte rồi dùng như khóa AES-256 |
| **Security strength** | Độ khó tấn công ước lượng dưới một mô hình cụ thể | Cho rằng mọi thuật toán có khóa 256 bit đều an toàn như AES-256 |
| **Key lifetime** | Thời gian hoặc giới hạn sử dụng của khóa | Cho rằng tăng độ dài khóa cho phép dùng vô hạn lần |

Ví dụ, một ứng dụng dùng chuỗi `"123456"` và đệm ký tự `0` thành 32 byte rồi nạp vào AES-256. API có thể chấp nhận đầu vào **256 bit**, nhưng khóa vẫn dễ đoán vì bí mật gốc quá yếu. **Kích thước biểu diễn không tạo thêm entropy.**

### 2.2. Key size khác block size, nonce, IV và tag

Với AES, kích thước khối (**block size**) **luôn là 128 bit**, dù khóa là AES-128, AES-192 hay AES-256.

Khi sử dụng AES-GCM, ta còn phải quản lý **nonce/IV**, **authentication tag** và có thể có **AAD** (Additional Authenticated Data):

| Tham số | Ví dụ trong AES-256-GCM | Chức năng |
| --- | --- | --- |
| Khóa AES | **256 bit = 32 byte** | Bí mật quyết định phép mã hóa/giải mã |
| Block size AES | **128 bit = 16 byte** | Kích thước khối xử lý nội bộ của AES |
| Nonce/IV GCM | Thường **96 bit = 12 byte** | Phân biệt các lần mã hóa dưới cùng khóa |
| Authentication tag | Thường **128 bit = 16 byte** | Kiểm tra tính hợp lệ của ciphertext và AAD |
| AAD | Độ dài tùy ứng dụng | Xác thực ngữ cảnh nhưng không mã hóa nội dung AAD |

Nonce và tag **không phải khóa**. Nonce không cần bí mật, nhưng với GCM **không được tái sử dụng một nonce cho hai lần mã hóa dưới cùng một khóa**. Việc tăng AES-128 lên AES-256 không khắc phục được lỗi trùng nonce; sự cố này có thể gây hậu quả nghiêm trọng cho cả tính bí mật và tính xác thực.

## 3. So sánh AES-128, AES-192 và AES-256

AES là thuật toán mã hóa khối tiêu chuẩn, hỗ trợ chính xác ba độ dài khóa sau:

| Tiêu chí | AES-128 | AES-192 | AES-256 |
| --- | ---: | ---: | ---: |
| Độ dài khóa | 128 bit | 192 bit | 256 bit |
| Độ dài khóa theo byte | 16 | 24 | 32 |
| Số vòng AES | 10 | 12 | 14 |
| Kích thước khối | 128 bit | 128 bit | 128 bit |
| Độ mạnh chống vét cạn cổ điển, theo giả định thông thường | Xấp xỉ 128 bit | Xấp xỉ 192 bit | Xấp xỉ 256 bit |
| Cân nhắc thường gặp | Mức an toàn mạnh, phổ biến, hỗ trợ rộng | Phương án trung gian, phải kiểm tra khả năng tương thích | Biên độ an toàn dài hạn lớn hơn, hay được chọn theo yêu cầu chính sách |

**AES-128 không được xem là yếu chỉ vì có ít bit hơn AES-256.** Tấn công vét cạn một khóa AES-128 được sinh đủ ngẫu nhiên vẫn nằm ngoài khả năng thực tế của hệ thống tính toán cổ điển hiện nay. AES-256 cung cấp biên độ chống dò khóa lớn hơn, nhưng có thêm chi phí tính toán tùy phần cứng/provider. Khi được tăng tốc phần cứng, mức chênh lệch hiệu năng thực tế có thể nhỏ trong toàn bộ thời gian xử lý ứng dụng; cần đo trên hạ tầng sử dụng.

### 3.1. Khi nào nên chọn AES-128?

AES-128 có thể phù hợp khi:

- Mức an toàn mục tiêu của hệ thống là khoảng **128 bit** và chính sách cho phép.
- Thuật toán, mode, thư viện và toàn bộ giao thức đã được đánh giá ở mức đó.
- Dữ liệu không có yêu cầu riêng bắt buộc AES-256, đồng thời hiệu năng hoặc khả năng tương thích là yếu tố quan trọng.
- Hệ thống có cơ chế **sinh khóa an toàn, AEAD, quản lý nonce, phân quyền, kiểm toán và xoay vòng** tương ứng.

Ví dụ, một nền tảng xử lý phiên làm việc ngắn hạn có thể dùng một giao thức đã chuẩn hóa ở mức bảo mật 128 bit. Với các giao thức như TLS, bộ mã đối xứng thường được **thương lượng và quản lý bởi thư viện giao thức**; không nên tự chọn rồi thay khóa phiên bên ngoài giao thức.

### 3.2. Khi nào nên chọn AES-256?

AES-256 thường là ứng viên khi:

- Chính sách tổ chức, quy định hợp đồng hoặc yêu cầu sản phẩm quy định khóa đối xứng 256 bit.
- Dữ liệu cần duy trì tính bí mật trong thời gian dài và kiến trúc muốn thêm biên độ an toàn.
- Hệ thống đã hỗ trợ tốt AES-256 thông qua Java, KMS/HSM và các bên liên quan, với hiệu năng đạt yêu cầu.
- Tổ chức muốn ưu tiên mức độ mạnh đối xứng cao hơn trong quá trình chuẩn bị cho rủi ro tính toán tương lai, kể cả một số cân nhắc liên quan mật mã hậu lượng tử.

**Lưu ý về lượng tử:** Trong mô hình lý thuyết, thuật toán Grover có thể giảm số bước tìm kiếm vét cạn khóa đối xứng; việc quy đổi thành chi phí tấn công thực tế còn phụ thuộc mạnh vào tài nguyên và giả định máy tính lượng tử. Không thể kết luận AES-128 “đã bị phá” hoặc AES-256 bảo đảm an toàn tuyệt đối trong mọi kịch bản. Khi có yêu cầu bảo vệ dài hạn, nên theo dõi tiêu chuẩn và chính sách mật mã được áp dụng.

### 3.3. AES-192 có phải lựa chọn tối ưu ở giữa?

AES-192 là thuật toán hợp lệ với độ dài khóa 192 bit và 12 vòng. Nó có thể phù hợp nếu chính sách hoặc khả năng tương thích yêu cầu. Tuy nhiên, nhiều thiết kế thực tế tập trung vào **AES-128 và AES-256** vì hệ sinh thái, các cấu hình triển khai và thư viện có thể ưu tiên hai lựa chọn này. Không nên tự suy diễn rằng AES-192 luôn có hiệu năng, độ an toàn thực tế hoặc mức hỗ trợ “nằm giữa” một cách thuận lợi. Hãy kiểm tra **provider Java, KMS/HSM, giao thức, SDK và đối tác** trước khi dùng.

## 4. Không dùng cùng một phép so sánh bit cho mọi thuật toán

Các tên thuật toán và key size có thể gây nhầm lẫn:

| Thuật toán/cơ chế | Kích thước liên quan | Điều cần hiểu |
| --- | --- | --- |
| AES-128/192/256 | 128/192/256 bit bí mật | Là ba kích thước khóa AES hỗ trợ |
| ChaCha20 | Khóa 256 bit | Là một stream cipher khác AES; thường dùng trong ChaCha20-Poly1305 |
| 3DES/TDEA | Các thành phần khóa DES, thường gọi 2-key hoặc 3-key | Là thiết kế cũ, có giới hạn độ mạnh và dữ liệu; không chọn cho hệ thống mới |
| HMAC-SHA-256 | Khóa HMAC có độ dài lựa chọn và SHA-256 có đầu ra 256 bit | SHA-256 **không yêu cầu** khóa HMAC phải là 256 bit; tag, key length và mức an toàn là các đại lượng riêng |
| RSA-3072 | Modulus RSA 3072 bit | Không phải khóa đối xứng 3072 bit; độ mạnh cổ điển thường xấp xỉ 128 bit |
| ECC P-256 | Tham số đường cong cỡ 256 bit | Không thể so số bit trực tiếp với AES-256; độ mạnh cổ điển thường xấp xỉ 128 bit |

Khóa ký số và khóa trao đổi mật mã bất đối xứng phục vụ mục đích khác khóa mã hóa dữ liệu. Chọn **AES-256** để mã hóa dữ liệu không làm cho chữ ký RSA-2048 tự đạt 256 bit bảo mật. Nếu hệ thống có nhiều primitive kết hợp, hãy đánh giá **mức an toàn của toàn bộ chuỗi mật mã**, bao gồm việc xác thực public key, thiết lập khóa phiên và bảo vệ private key.

## 5. Quy trình chọn key size theo yêu cầu thực tế

Một quy trình thực dụng bắt đầu từ **những gì hệ thống cần bảo vệ**, tiếp đến mới chọn độ dài khóa.

### Bước 1 — Phân loại dữ liệu và thời gian cần giữ bí mật

Xác định dữ liệu là thông tin phiên, hồ sơ khách hàng, dữ liệu tài chính, bản sao lưu lưu giữ nhiều năm hay thông tin có nghĩa vụ bảo mật dài hạn. Đồng thời xác định hậu quả nếu dữ liệu bị lộ vào hôm nay, trong vài năm hoặc sau khi hệ thống ngừng hoạt động.

**Ví dụ:** Dữ liệu tạm của một phiên có thời gian bảo vệ khác với hồ sơ pháp lý phải giữ lâu năm. Thời gian lưu trữ không tự quyết định độ dài khóa nhưng là yếu tố quan trọng để xác định biên độ an toàn.

### Bước 2 — Xác định mô hình đe dọa và mức an toàn mục tiêu

Đánh giá đối thủ có thể tiếp cận ciphertext, metadata, backup, mạng, tài khoản KMS hay chính ứng dụng không. Chọn security strength tối thiểu mà hệ thống cần duy trì, cùng các giả định về thuật toán và môi trường.

Nếu rủi ro chủ yếu là **lộ dữ liệu lưu trữ**, tăng key size có thể tăng biên độ chống dò khóa, nhưng phần quyết định vẫn là **giữ bí mật DEK/KEK**. Nếu rủi ro là **workload bị chiếm quyền có quyền Decrypt**, cần giới hạn quyền và giám sát; chỉ tăng AES-128 thành AES-256 thường không đổi phạm vi tấn công đó.

### Bước 3 — Chọn thuật toán và mode an toàn

Với dữ liệu ứng dụng cần cả bí mật và xác thực, lựa chọn thường gặp là **AES-GCM** hoặc AEAD phù hợp khác. Tránh AES-ECB cho dữ liệu ứng dụng. AES-CBC hoặc CTR riêng lẻ không tự bảo vệ tính toàn vẹn; nếu phải duy trì hệ thống cũ, cần thiết kế xác thực phù hợp, quản lý IV và chống các lỗi liên quan.

Chỉ sau khi đã xác định đúng thuật toán/mode mới lựa chọn các **key size được hỗ trợ**. Ví dụ, không tự gán khóa 160 bit cho AES vì “160 nằm giữa 128 và 192”.

### Bước 4 — Đối chiếu chính sách, quy định và thời gian bảo vệ

Kiểm tra các yêu cầu của tổ chức, hợp đồng, ngành hoặc tiêu chuẩn áp dụng tại thời điểm triển khai. Khi một chính sách yêu cầu **AES-256**, phải đáp ứng đúng yêu cầu đó; nếu chấp nhận **128 bit security strength**, AES-128 có thể là lựa chọn hợp lệ. Cần xác định chính xác yêu cầu nói về **độ dài khóa**, **mức độ mạnh bảo mật** hay **nhóm thuật toán được phép**.

### Bước 5 — Kiểm tra tương thích và hiệu năng

Đối chiếu cấu hình thực tế:

- **Java/JCE provider:** Có sinh khóa AES đúng kích thước và hỗ trợ `AES/GCM/NoPadding` không?
- **KMS/HSM:** Có key type, thuật toán, key length và API bọc/giải bọc cần thiết không?
- **Giao thức/đối tác:** Có chấp nhận thông số thuật toán và định dạng ciphertext, tag, nonce, phiên bản không?
- **Hiệu năng:** Độ trễ ở đường đọc/ghi, thông lượng, CPU, API KMS, giới hạn request và chi phí vận hành có đáp ứng SLA không?
- **Khả năng triển khai:** Có quản lý được key version, sao lưu, giám sát và quá trình thay khóa không?

Không kết luận chỉ từ benchmark AES thuần nếu sản phẩm thực tế còn thực hiện mạng, database, phân quyền, KMS và serialization. Đo ở mức **quy trình thực tế của hệ thống**.

### Bước 6 — Ghi lại quyết định và kế hoạch thay đổi

Quyết định nên được lưu dưới dạng cấu hình và tài liệu kiến trúc rõ ràng: thuật toán, mode, key size, nguồn sinh khóa, mục đích, key ID/version, ranh giới dữ liệu, chính sách sử dụng và thời điểm đánh giá lại. Điều này giúp hệ thống có thể **rotate hoặc migrate** mà không đoán lại các tham số của bản mã cũ.

~~~mermaid
flowchart TD
    A["Phân loại dữ liệu và thời gian bảo mật"] --> B["Xác định security strength mục tiêu"]
    B --> C["Chọn thuật toán/mode phù hợp, ưu tiên AEAD"]
    C --> D{"Chính sách yêu cầu key size cụ thể?"}
    D -->|"Có"| E["Dùng kích thước được quy định, xác nhận hỗ trợ"]
    D -->|"Không"| F["So sánh AES-128/192/256 theo yêu cầu"]
    E --> G["Kiểm tra Java, KMS/HSM, giao thức, hiệu năng"]
    F --> G
    G --> H{"Đạt yêu cầu và tương thích?"}
    H -->|"Chưa"| I["Điều chỉnh thiết kế hoặc cấu hình được hỗ trợ"]
    I --> G
    H -->|"Đạt"| J["Ghi quyết định, key ID/version và kế hoạch rotation"]
~~~

## 6. Các ví dụ quyết định chọn khóa

| Tình huống | Đề xuất đánh giá | Lý do / điều kiện |
| --- | --- | --- |
| API nội bộ xử lý dữ liệu nghiệp vụ trong thời gian ngắn, chính sách chấp nhận mức 128 bit | **AES-128-GCM có thể phù hợp** | Độ mạnh cổ điển cao; cần nonce đúng, xác thực, phân quyền và quản lý khóa |
| Bản sao lưu dữ liệu nhạy cảm cần giữ bí mật dài hạn, hệ thống hỗ trợ tốt 256 bit | **Ưu tiên cân nhắc AES-256-GCM** | Biên độ chống dò khóa lớn hơn, cần xem chính sách retention/restore |
| Quy định bắt buộc AES-256 | **AES-256** | Đáp ứng yêu cầu chính sách, đồng thời kiểm tra mode và kiến trúc |
| Thiết bị cũ chỉ hỗ trợ một thuật toán/mode không an toàn | **Xem xét nâng cấp thiết bị hoặc thiết kế** | Chọn khóa dài hơn không sửa được nhược điểm nghiêm trọng của mode |
| Ứng dụng lưu AES key trong Git hoặc log | **Sửa quản lý khóa trước** | Rò rỉ key vô hiệu hóa lợi ích của việc tăng key size |
| Dữ liệu nằm trong envelope encryption, DEK đang là AES-128 và chỉ KEK được đổi sang loại mạnh hơn | **Đánh giá có cần thay DEK hay không** | Đổi KEK không tự nâng mức bảo vệ của ciphertext do DEK AES-128 tạo ra |

**Các ví dụ là cách ra quyết định, không phải tuyên bố tuân thủ một tiêu chuẩn cụ thể.** Nếu chưa biết chính sách, môi trường và thời gian dữ liệu cần bảo vệ, không thể kết luận chỉ một key size là tốt nhất cho mọi trường hợp.

## 7. Thực hành Java: tạo khóa AES theo key size

Trong Java, **KeyGenerator** sinh khóa với kích thước mà thuật toán/provider hỗ trợ; **SecureRandom** cung cấp nguồn ngẫu nhiên phù hợp cho thao tác mật mã. Với AES, ứng dụng nên giới hạn đầu vào về 128, 192 hoặc 256 bit:

~~~java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class AesKeySizeDemo {
    private static final SecureRandom RNG = new SecureRandom();

    private AesKeySizeDemo() {}

    public static SecretKey generateAesKey(int keySizeBits)
            throws Exception {
        if (keySizeBits != 128 && keySizeBits != 192 &&
                keySizeBits != 256) {
            throw new IllegalArgumentException(
                    "AES supports 128, 192 or 256-bit keys");
        }

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(keySizeBits, RNG);
        return generator.generateKey();
    }

    public static void main(String[] args) throws Exception {
        SecretKey key128 = generateAesKey(128);
        SecretKey key256 = generateAesKey(256);

        // Ví dụ dùng khóa phần mềm có thể xuất để kiểm tra độ dài.
        // Tuyệt đối không in byte khóa vào console hoặc ghi log.
        System.out.println("AES-128 length: "
                + (key128.getEncoded().length * 8) + " bits");
        System.out.println("AES-256 length: "
                + (key256.getEncoded().length * 8) + " bits");
    }
}
~~~

Kết quả mong đợi của ví dụ:

~~~text
AES-128 length: 128 bits
AES-256 length: 256 bits
~~~

Ở đây, `getEncoded()` chỉ phù hợp khi khóa phần mềm **cho phép xuất**. Khóa bên trong HSM/KMS có thể không xuất được, nên kết quả có thể là `null` hoặc API không hỗ trợ thao tác này. Trong production, nên dùng metadata/key spec được KMS hoặc provider cung cấp thay vì cố trích xuất vật liệu khóa để đo kích thước.

### 7.1. Dùng khóa đã chọn với AES-GCM

Ví dụ sau cho thấy **key size** và **nonce/tag size** được cấu hình ở hai lớp khác nhau. Để ngắn gọn, chương trình chỉ mã hóa một thông điệp; code sản xuất còn cần chiến lược bảo đảm nonce duy nhất theo khóa và giới hạn số lần mã hóa.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmSizeDemo {
    private AesGcmSizeDemo() {}

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, random); // 256 bit là KEY size
        SecretKey dek = generator.generateKey();

        byte[] nonce = new byte[12]; // 96 bit là NONCE size
        random.nextBytes(nonce);     // Nonce mới, dùng một lần với DEK

        byte[] aad = "tenant=42;record=9"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Ho so can ma hoa"
                .getBytes(StandardCharsets.UTF_8);

        Cipher enc = Cipher.getInstance("AES/GCM/NoPadding");
        enc.init(Cipher.ENCRYPT_MODE, dek,
                 new GCMParameterSpec(128, nonce)); // 128 bit TAG
        enc.updateAAD(aad);
        byte[] ciphertextWithTag = enc.doFinal(plaintext);

        Cipher dec = Cipher.getInstance("AES/GCM/NoPadding");
        dec.init(Cipher.DECRYPT_MODE, dek,
                 new GCMParameterSpec(128, nonce));
        dec.updateAAD(aad);
        byte[] restored = dec.doFinal(ciphertextWithTag);

        System.out.println(new String(restored, StandardCharsets.UTF_8));
    }
}
~~~

Trong Java/JCE, nếu ciphertext hoặc tag sai hay AAD không khớp, bước giải mã GCM sẽ thất bại khi xác thực. **Không chấp nhận hoặc xuất plaintext nếu xác thực thất bại.** AAD là thông tin được xác thực, **không được mã hóa**; tránh đặt bí mật cần che giấu vào AAD.

**Chú ý:** Tạo nonce bằng `SecureRandom` như trên chỉ minh họa một lần mã hóa. Hệ thống có lưu lượng cao phải xét xác suất trùng nonce, giới hạn sử dụng theo thuật toán, đồng bộ giữa nhiều tiến trình và phương án cấp nonce độc nhất. Bảo mật không tự tăng khi thay `generator.init(128, ...)` thành `generator.init(256, ...)` nếu vẫn dùng nonce trùng.

## 8. Chọn key size cùng KMS/HSM và envelope encryption

Trong **envelope encryption**, ứng dụng thường dùng hai vai trò khóa:

1. **DEK (Data Encryption Key):** Khóa đối xứng trực tiếp mã hóa dữ liệu, ví dụ AES-128-GCM hoặc AES-256-GCM.
2. **KEK (Key Encryption Key):** Khóa dùng để wrap/unwrap DEK; có thể được quản lý trong **KMS/HSM**. Thuật toán hoặc độ dài của KEK phụ thuộc loại khóa và khả năng dịch vụ.

~~~mermaid
flowchart TD
    C["Yêu cầu: bảo vệ bản ghi nhạy cảm"] --> P["Chọn DEK AES-128 hoặc AES-256 theo policy"]
    P --> E["Mã hóa dữ liệu bằng AEAD, nonce hợp lệ"]
    P --> W["Wrap DEK bằng KEK được KMS/HSM bảo vệ"]
    E --> S["Lưu ciphertext, nonce, tag, keyId/version"]
    W --> S
    S --> R["Khi đọc: xác thực user và quyền bản ghi"]
    R --> U["KMS cho unwrap DEK theo danh tính/context"]
    U --> D["Giải mã và xác minh AEAD"]
~~~

**Không suy ra key size của KEK từ key size của DEK.** Một hệ thống có thể có DEK AES-128 hoặc AES-256 được bảo vệ bởi các cơ chế wrap khác nhau. Cần kiểm tra tài liệu và cấu hình thực tế của API thay vì giả định “mọi khóa trong cây đều là AES-256”.

KMS/HSM giúp **bảo vệ vật liệu khóa, quản lý quyền sử dụng và ghi nhận sự kiện**. Tuy vậy, nếu tài khoản ứng dụng có quyền gọi `Decrypt`/unwrap trên mọi dữ liệu, kẻ tấn công chiếm được tài khoản đó có thể khai thác quyền hợp lệ bất kể độ dài khóa. Phải áp dụng **least privilege**, tách môi trường/tenant, kiểm tra quyền nghiệp vụ và giám sát thao tác bất thường.

### 8.1. Những gì cần lưu cùng ciphertext

Một bản mã có thể cần:

- Định danh thuật toán và mode (ví dụ `AES-256-GCM`).
- **Key ID và key version** tham chiếu DEK hoặc wrapped DEK phù hợp.
- Nonce/IV và authentication tag theo định dạng đã thống nhất.
- Wrapped DEK và thông tin KEK hoặc encryption context cần để giải bọc.
- Metadata đủ để dựng lại AAD và xác thực ngữ cảnh đúng bản ghi/tenant.

**Không** lưu plaintext DEK ngay cạnh ciphertext trong hệ thống lưu trữ. Những metadata không phải bí mật vẫn cần được xác thực hoặc kiểm soát đúng cách để tránh bị đánh tráo.

## 9. Nâng key size và xoay vòng khóa đúng cách

Giả sử hệ thống đang dùng **DEK AES-128-GCM** và quyết định chuyển sang **DEK AES-256-GCM**. Đây là thay đổi vật liệu khóa và có thể thay đổi metadata; không phải đổi một con số trong cấu hình là ciphertext cũ tự dùng AES-256.

### 9.1. Phân biệt rotate KEK với thay key size của DEK

| Hành động | Điều thay đổi | Tác động lên ciphertext dữ liệu |
| --- | --- | --- |
| **Rotate KEK** | Dùng KEK mới để bảo vệ/rewrap DEK | Có thể giữ nguyên ciphertext nếu DEK không đổi |
| **Rotate DEK cùng key size** | Sinh DEK mới có cùng độ dài | Dữ liệu phụ thuộc cần được mã hóa lại để không còn dùng DEK cũ |
| **Migrate DEK từ AES-128 sang AES-256** | Sinh DEK AES-256 và mã hóa lại | Phải giải mã và mã hóa lại dữ liệu cần chuyển; cập nhật thuật toán/key ID/version |
| **Thay thuật toán/mode** | Đổi primitive hoặc cấu hình AEAD | Cần phân tích định dạng, nonce, tag, AAD, tương thích và kế hoạch migration riêng |

### 9.2. Quy trình migration có kiểm soát

1. **Kiểm kê:** Xác định bản ghi/tệp, DEK, KEK, thuật toán và phiên bản đang dùng, kể cả dữ liệu trong backup.
2. **Tạo khóa mới:** Dùng CSPRNG/KMS/HSM sinh DEK AES-256 đủ ngẫu nhiên; thiết lập quyền và chính sách.
3. **Viết mới bằng khóa mới:** Từ thời điểm chuyển đổi, dữ liệu mới sử dụng key ID/version và thuật toán mới.
4. **Chuyển dữ liệu cũ:** Dùng đúng khóa AES-128 cũ để giải mã, kiểm tra tag/AAD; sau đó mã hóa bằng DEK AES-256 với nonce phù hợp, lưu ciphertext và metadata mới.
5. **Kiểm thử:** Thử đọc bản ghi cũ/mới, xử lý lỗi giải mã, rollback có kiểm soát, phiên bản ở các dịch vụ, dữ liệu backup và dữ liệu được nhân bản.
6. **Ngừng dùng khóa cũ:** Chỉ vô hiệu hóa/hủy DEK cũ sau khi xác nhận không còn dữ liệu hoặc nghĩa vụ cần giải mã bằng khóa đó.
7. **Kiểm toán:** Ghi lại quyết định, mốc chuyển đổi, key ID/version và kết quả mà không ghi vật liệu khóa hay plaintext vào log.

Đối với **khóa đã bị lộ**, phải xử lý thêm phạm vi dữ liệu bị ảnh hưởng, quyền truy cập đã bị chiếm, bản sao khóa và dữ liệu có thể đã bị giải mã. Tăng key size của khóa mới **không thu hồi được plaintext** đã bị sao chép.

## 10. Những lỗi thường gặp khi chọn key size

| Lỗi | Vì sao nguy hiểm? | Cách xử lý |
| --- | --- | --- |
| Chọn AES-256 nhưng sinh khóa từ timestamp hoặc password yếu | Khóa có entropy thấp, dễ đoán | Sinh khóa hệ thống bằng CSPRNG/KMS; dùng password KDF phù hợp nếu xuất phát từ mật khẩu |
| Tăng key size nhưng vẫn dùng ECB | Mode làm lộ mẫu bản rõ dù khóa lớn | Chọn AEAD phù hợp, kiểm tra tính toàn vẹn |
| Tái sử dụng nonce dưới cùng khóa AES-GCM | Có thể phá bí mật và tính xác thực | Quản lý nonce duy nhất, giới hạn lượt sử dụng và rotation |
| Tưởng khóa AES-256 cần nonce 256 bit | Nhầm key size với nonce size | Chọn nonce theo yêu cầu GCM, thường 96 bit; quản lý tính duy nhất |
| Dùng key size không được AES/JCE/KMS hỗ trợ | Hệ thống lỗi hoặc phải đổi thiết kế vào phút cuối | Chọn đúng 128/192/256 bit; kiểm tra provider và key spec |
| In key bằng Base64 vào log để “debug” | Base64 chỉ là cách biểu diễn, không mã hóa bảo mật | Không xuất vật liệu khóa; log key ID và metadata an toàn |
| Chọn AES-256 nhưng cho mọi workload quyền Decrypt | Quyền bị lạm dụng tạo ra bản rõ hợp lệ | Giới hạn quyền theo danh tính, tenant, mục đích và kiểm toán |
| Rotate KEK rồi tuyên bố dữ liệu đã chuyển từ AES-128 lên AES-256 | DEK bảo vệ dữ liệu vẫn là AES-128 | Thay DEK và re-encrypt khi yêu cầu nâng key size dữ liệu |
| Xóa khóa AES-128 ngay sau khi bật cấu hình AES-256 | Dữ liệu cũ và backup không còn giải mã được | Lưu key ID/version, thử migration và kiểm kê phụ thuộc trước khi hủy |
| Chọn kích thước lớn nhất mà không kiểm thử | Có thể gặp giới hạn provider, HSM hoặc giao thức | Kiểm tra tính tương thích và hiệu năng trong kiến trúc thật |

## 11. Checklist review quyết định key size

Trước khi triển khai môi trường production, hãy trả lời:

1. **Tài sản:** Dữ liệu nào được bảo vệ, cần bí mật trong bao lâu và hậu quả khi lộ là gì?
2. **Mức an toàn:** Chính sách yêu cầu key size cụ thể hay yêu cầu security strength tối thiểu?
3. **Thuật toán:** Đã chọn primitive/mode phù hợp, tránh những mode làm lộ thông tin hoặc không xác thực?
4. **Kích thước:** AES dùng đúng **128, 192 hoặc 256 bit**? Có nhầm với nonce, tag, block size hoặc key size của RSA/ECC?
5. **Nguồn sinh:** Khóa có đủ entropy và được sinh bằng CSPRNG/KMS/HSM thay vì mật khẩu thô?
6. **Giới hạn sử dụng:** Nonce có duy nhất theo khóa? Số lần mã hóa và thời gian sống có đáp ứng giới hạn của thuật toán?
7. **Quyền:** DEK/KEK được lưu ở đâu, ai có quyền Encrypt, Decrypt, Wrap, Unwrap, Rotate và Delete?
8. **Tương thích:** Java provider, KMS/HSM, giao thức và đối tác có hỗ trợ đúng cấu hình không? Đã kiểm tra hiệu năng?
9. **Phiên bản:** Ciphertext có gắn key ID/version và metadata để đọc dữ liệu cũ sau migration?
10. **Phục hồi/kiểm toán:** Có thử khôi phục, kế hoạch rotation/thu hồi/hủy và log an toàn để điều tra sự cố?

## 12. Ghi nhớ

- **AES-128, AES-192 và AES-256** là ba độ dài khóa AES hợp lệ, lần lượt có khóa **16, 24 và 32 byte**. AES luôn có **block size 128 bit**.
- **AES-128** là lựa chọn có độ mạnh cổ điển cao trong nhiều hệ thống; **AES-256** tăng biên độ an toàn và có thể phù hợp yêu cầu bảo vệ dài hạn hoặc chính sách. AES-192 cần được kiểm tra hỗ trợ của toàn bộ hệ thống.
- **Key size không đồng nghĩa entropy, security strength hay mức an toàn toàn hệ thống**. Mode, nonce, KDF, quyền truy cập, KMS/HSM, kiểm toán và bảo vệ khóa dạng rõ đều quan trọng.
- **Envelope encryption** tách DEK mã hóa dữ liệu khỏi KEK bảo vệ khóa. Đổi KEK không tự nâng key size của DEK; nâng AES-128 lên AES-256 cho dữ liệu thường cần **sinh DEK mới và mã hóa lại**.
- Quyết định chọn key size phải có thể được **kiểm tra, vận hành và thay đổi an toàn** trong suốt vòng đời khóa.

Khi gặp câu hỏi “nên chọn AES-128 hay AES-256?”, hãy bắt đầu bằng **dữ liệu cần bảo vệ, thời gian bảo mật, chính sách, mô hình đe dọa và khả năng triển khai**, rồi mới quyết định key size. Khóa dài có ý nghĩa khi được **sinh đúng, dùng đúng và quản lý đúng**.
