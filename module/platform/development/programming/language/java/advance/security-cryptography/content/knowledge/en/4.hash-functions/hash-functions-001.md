# 4.1. Tính một chiều, tiền ảnh và va chạm của hàm băm mật mã

Một hàm băm mật mã (cryptographic hash function) biến dữ liệu có độ dài bất kỳ thành một **giá trị băm (digest) có độ dài cố định**. Ta thường dùng SHA-256 để tính dấu vân tay cho một tệp, kiểm tra dữ liệu đã đổi hay chưa, hoặc làm thành phần bên trong chữ ký số và HMAC. Nhưng để hiểu vì sao một giá trị băm có thể dùng trong các cơ chế bảo mật, phải phân biệt ba thuộc tính: **kháng tiền ảnh**, **kháng tiền ảnh thứ hai** và **kháng va chạm**.

Ví dụ, SHA-256 của chuỗi UTF-8 `abc` là:

```text
Input bytes (UTF-8): 61 62 63
SHA-256 (hex):
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

Kết quả gồm 32 byte, thường được trình bày thành **64 chữ số hex**. Một chuỗi khác thường tạo digest khác, nhưng không thể khẳng định rằng *mọi* hai chuỗi khác nhau đều có hash khác nhau.

Sau bài học, bạn cần:
- Giải thích hàm băm “một chiều” có nghĩa là khó tìm đầu vào từ digest, không phải không thể về mặt toán học.
- Phân biệt rõ bài toán tìm **preimage**, **second preimage** và **collision**, đặc biệt là những thông tin kẻ tấn công được cho trước.
- Ước lượng chi phí tấn công lý tưởng với đầu ra `n` bit: cỡ `2^n` cho tiền ảnh/tiền ảnh thứ hai và `2^(n/2)` cho va chạm.
- Hiểu nghịch lý sinh nhật (birthday bound), tác động của rút ngắn digest, và vì sao dữ liệu ít entropy vẫn có thể bị đoán dễ dàng.
- Áp dụng SHA-256 bằng Java 17+, đọc kết quả dưới dạng byte/hex, và không nhầm hash thường với cơ chế xác thực hay lưu mật khẩu.

## 1. Hàm băm mật mã là gì?

Ký hiệu tổng quát:

```text
             H
Message M --------> Digest h = H(M)
(any length)        (fixed n bits)
```

Mô hình lý tưởng hóa:

\[
H:\{0,1\}^{*}\rightarrow\{0,1\}^{n}
\]

Trong đó:
- `M` là một dãy **byte/bit**, không mặc nhiên là ký tự; cách mã hóa UTF-8, chuẩn hóa hay serialize JSON ảnh hưởng trực tiếp đến digest.
- `n` là độ dài digest tính bằng bit. Với SHA-256, `n = 256`; với SHA-512, `n = 512`.
- `H` là thuật toán công khai, xác định: cùng đúng một dãy byte thì cho cùng digest. Thuật toán SHA-256 không cần một bí mật riêng để hoạt động.

Một hàm băm mật mã phù hợp thường được thiết kế để có các đặc điểm:
1. **Tính xác định (deterministic):** `H(M)` luôn cho cùng kết quả nếu thuật toán và byte đầu vào không đổi.
2. **Hiệu quả khi tính xuôi:** với thông điệp và thuật toán, tính digest có chi phí chấp nhận được.
3. **Kháng tiền ảnh:** khi chỉ biết một digest mục tiêu, khó tìm một thông điệp băm ra giá trị đó.
4. **Kháng tiền ảnh thứ hai:** khi biết một thông điệp cụ thể, khó tìm một thông điệp *khác* có cùng digest.
5. **Kháng va chạm:** khó tự tìm *bất kỳ cặp* thông điệp khác nhau nào có cùng digest.

Các mục 3–5 là **mục tiêu an toàn trước đối thủ có tài nguyên tính toán hữu hạn**, không phải bảo đảm tồn tại duy nhất một thông điệp cho mỗi digest. Hiện tượng avalanche — đổi một ít bit đầu vào thường làm nhiều bit đầu ra đổi — là đặc tính mong muốn, nhưng chỉ nhìn thấy avalanche **không đủ chứng minh** ba mức kháng tấn công trên.

### 1.1. Vì sao va chạm chắc chắn tồn tại?

Đầu vào có thể dài tùy ý, trong khi đầu ra chỉ có `2^n` giá trị khác nhau. Theo nguyên lý Dirichlet (pigeonhole principle), có nhiều thông điệp khác nhau chia sẻ cùng digest. Nói cách khác:

\[
\exists M_1 \neq M_2 : H(M_1) = H(M_2)
\]

**Va chạm tồn tại về mặt toán học**; câu hỏi bảo mật thực tế là đối thủ có thể **tìm được** một va chạm hữu ích với chi phí khả thi hay không.

Đừng hiểu câu “xác suất va chạm thấp” thành “không tồn tại va chạm”, và cũng đừng hiểu “có va chạm” thành “hàm băm bị phá”. Một hàm băm 256 bit tốt vẫn có vô số cặp va chạm, nhưng việc chủ động tìm cặp bằng tấn công tổng quát dự kiến rất tốn kém.

## 2. Ba bài toán: preimage, second preimage và collision

Hãy đặt tên cho digest mục tiêu là `h`, thông điệp gốc là `M` và thông điệp mới là `M'`.

| Thuộc tính | Đối thủ được cho trước | Đối thủ muốn tìm | Điều kiện thành công |
| --- | --- | --- | --- |
| **Kháng tiền ảnh (preimage resistance)** | Một digest `h` | Bất kỳ `M` | `H(M) = h` |
| **Kháng tiền ảnh thứ hai (second-preimage resistance)** | Một thông điệp `M` cụ thể | Một `M'` khác `M` | `H(M') = H(M)` |
| **Kháng va chạm (collision resistance)** | Hàm `H`, **không bị cố định trước M** | Hai thông điệp `M_1, M_2` khác nhau | `H(M_1) = H(M_2)` |

Khác biệt quyết định nằm ở **mức tự do được chọn đầu vào**:

- **Preimage:** digest đã được chọn; đối thủ cần tìm *một lời giải* cho giá trị đó.
- **Second preimage:** thông điệp gốc đã cố định; đối thủ không được tùy ý chọn cả hai thông điệp.
- **Collision:** đối thủ được tự chọn **cả hai** thông điệp, nên có thể thử rất nhiều ứng viên và tìm bất kỳ cặp trùng nhau nào.

### 2.1. Hình dung từng thách thức

**Thử thách A — tiền ảnh:** Người kiểm tra đưa digest `h = SHA-256(secretMessage)`, không tiết lộ secretMessage. Nhiệm vụ là tìm **bất cứ** dữ liệu `X` sao cho `SHA-256(X) = h`. `X` không nhất thiết đúng bằng secretMessage ban đầu.

**Thử thách B — tiền ảnh thứ hai:** Người kiểm tra công khai một file hợp đồng `M` đã được chấp thuận. Đối thủ phải tạo một file `M' != M` sao cho `SHA-256(M') = SHA-256(M)`. Giữ nguyên digest của một thông điệp **cố định** là điều kiện quan trọng.

**Thử thách C — va chạm:** Đối thủ tự tạo hai tệp `A` và `B` bất kỳ, miễn `A != B` nhưng có cùng digest. Nếu đối thủ còn điều khiển được ý nghĩa của hai tệp (ví dụ một tệp trông vô hại và một tệp độc hại), đây có thể là tiền đề cho một cuộc tấn công thay thế tài liệu trong giao thức ký hoặc phê duyệt thiết kế sai.

**Không nhầm:** có một collision `H(A)=H(B)` **không tự động** cho phép tìm second preimage của một tài liệu khác `M` đã được chọn từ trước. Kẻ tấn công sở hữu cặp `A,B` không được giả định rằng `A=M`.

### 2.2. Ba tính chất liên quan nhưng không đồng nhất

Kháng va chạm là yêu cầu mạnh trong nhiều thiết kế ký/định danh nội dung vì đối thủ có thể tìm cặp dữ liệu trước khi một bên đáng tin xử lý một trong hai. Kháng tiền ảnh và tiền ảnh thứ hai bảo vệ các kịch bản **mục tiêu đã cố định**.

Không suy ra “hàm băm một chiều ⇒ chống va chạm” hoặc “dễ tìm va chạm ⇒ tìm được tiền ảnh bất kỳ”. Đây là các trò chơi an ninh khác nhau, có phương pháp tấn công và mô hình lựa chọn đầu vào khác nhau.

## 3. Độ khó lý tưởng theo số bit

Với hàm băm `n` bit được mô hình như ánh xạ ngẫu nhiên đủ tốt, đầu vào/đầu ra được chọn trong điều kiện phù hợp và chưa có điểm yếu cấu trúc nào, độ khó tổng quát được ước lượng:

| Bài toán | Độ khó tổng quát điển hình | Nếu digest 256 bit |
| --- | --- | --- |
| Tìm preimage của mục tiêu ngẫu nhiên | Xấp xỉ `2^n` lần thử | `2^256` |
| Tìm second preimage của thông điệp đã cố định | Xấp xỉ `2^n` lần thử | `2^256` |
| Tìm collision của hai thông điệp tùy chọn | Xấp xỉ `2^(n/2)` lần thử | `2^128` |

Đây là **ước lượng trong mô hình lý tưởng**, không phải bằng chứng mọi hàm băm thực tế đạt đúng các mốc đó; nội dung dài đặc biệt, cấu trúc thuật toán, nhiều mục tiêu và các kiểu tấn công cụ thể có thể làm thay đổi công việc cần thiết. Ngoài ra, **mật khẩu hoặc mã PIN có ít khả năng** sẽ bị đoán theo không gian đầu vào nhỏ, chứ không phải đợi tới `2^256` thử.

### 3.1. Vì sao va chạm tìm nhanh hơn: birthday bound

Giả sử thử `q` đầu vào khác nhau và quan sát `q` digest `n` bit có phân phối đều. Có khoảng:

\[
\frac{q(q-1)}{2}
\]

cặp digest có thể so sánh. Mỗi cặp có xác suất khoảng `1/2^n` để trùng nhau trong mô hình ngẫu nhiên. Khi `q` còn nhỏ so với không gian đầu ra, xác suất có ít nhất một collision xấp xỉ:

\[
P(\text{collision}) \approx 1 -
\exp\left(-\frac{q(q-1)}{2^{n+1}}\right).
\]

Khi `q` đạt mức cùng bậc với `2^{n/2}`, xác suất va chạm trở nên đáng kể. Để đạt xấp xỉ **50%**, cần khoảng `1,177 \times 2^{n/2}` mẫu ngẫu nhiên; hệ số 1,177 không đổi bậc độ phức tạp.

Ví dụ với digest chỉ **16 bit**: có `2^16 = 65.536` kết quả. Chỉ cần khoảng **301 mẫu** là xác suất thấy ít nhất một cặp trùng nhau đạt khoảng 50% trong mô hình đều. Đây là lý do phép thử Java ở phần sau dễ tìm collision ở **2 byte đầu** của SHA-256.

Độ mạnh chống va chạm của hash `n` bit theo cách tính tổng quát thường chỉ ở mức khoảng **`n/2` bit an ninh**, trong khi độ mạnh preimage lý tưởng có thể khoảng **`n` bit**. Khi thiết kế ID chống đối thủ chủ động hoặc rút ngắn digest để lưu trữ, đừng nhầm “128-bit hash” với “128-bit chống collision”; digest 128 bit chỉ có birthday bound ở cỡ `2^64`.

### 3.2. Tìm collision không đồng nghĩa với đoán được nội dung

Nếu biết `H(password)`, đối thủ thường thử các mật khẩu khả dĩ theo từ điển rồi băm và so sánh. Đây là một kiểu **đoán preimage trong tập đầu vào entropy thấp**, khác với thuật toán tìm collision tự do.

Một PIN 4 chữ số có tối đa 10.000 ứng viên. Dù đem qua SHA-256, entropy của PIN **không tăng** lên 256 bit. Đối thủ có digest và khả năng kiểm tra ngoại tuyến có thể thử toàn bộ không gian nhỏ này rất nhanh nếu chỉ dùng SHA-256 trực tiếp.

## 4. “Một chiều” là tính chất tính toán, không phải mã hóa

Khác biệt giữa hash và encryption:

| Hàm băm | Mã hóa |
| --- | --- |
| Đưa dữ liệu tới digest có kích thước cố định | Biến plaintext thành ciphertext theo scheme và tham số |
| Thông thường không cần khóa bí mật | Cần khóa để mã hóa/giải mã, tùy loại scheme |
| Không có thuật toán “decrypt hash” đúng nghĩa để khôi phục bản gốc | Bên có quyền và khóa thích hợp có thể giải mã, kiểm tra tag nếu là AEAD |
| Có thể nhiều đầu vào cùng digest | Scheme giải mã hợp lệ phải xác định được plaintext từ bản mã phù hợp |
| Phù hợp làm thành phần cho dấu vân tay, chữ ký, MAC, KDF… | Phù hợp bảo vệ tính bí mật, AEAD còn có xác thực/toàn vẹn |

Khi chỉ có một digest, việc “đảo ngược” thường phải dựa vào thử ứng viên, khai thác đầu vào đoán được hoặc tìm điểm yếu thuật toán. Website “reverse SHA-256” thường tra bảng digest của các giá trị phổ biến: đó **không phải** giải mã toán học SHA-256.

Cần phân biệt:
- **Một chiều theo định nghĩa bảo mật:** chưa biết phương pháp hiệu quả để tìm preimage trong mô hình đe dọa tương ứng.
- **Không thể đảo ngược duy nhất:** từ một digest cố định không đủ thông tin để xác định một đầu vào ban đầu duy nhất vì có rất nhiều đầu vào cho cùng digest.
- **Đầu vào khó đoán:** là điều kiện độc lập về entropy. Một hàm băm rất mạnh vẫn không thể làm một mật khẩu phổ biến thành bí mật khó đoán khi bị tấn công offline.

## 5. Khi nào các thuộc tính được sử dụng?

### 5.1. Kiểm tra toàn vẹn tệp

Giả sử người tải file biết trước digest SHA-256 kỳ vọng thông qua **nguồn đáng tin**, rồi tính SHA-256 của file đã tải và so sánh. Nếu digest khác, file chắc chắn không trùng đúng byte với kỳ vọng (bỏ qua khả năng lỗi xử lý không thuộc mô hình); nếu digest giống, xác suất đối thủ cố ý đưa file khác có cùng digest được đánh giá theo an ninh của hash và mô hình tấn công.

Nhưng nếu kẻ tấn công thay được **cả file lẫn dòng SHA-256 hiển thị trên cùng trang không đáng tin**, việc so sánh không xác thực tác giả hoặc nguồn tải. Muốn xác minh nguồn, cần nguồn digest đã được xác thực, chữ ký số hợp lệ với public key đáng tin, hoặc cơ chế xác thực tương đương.

### 5.2. Chữ ký số và tài liệu đã ký

Nhiều sơ đồ chữ ký xử lý digest hay chuỗi byte đã qua encoding/hash theo thuật toán ký. Nếu đối thủ có thể chế tạo hai tài liệu mang cùng digest trong bối cảnh ký thiếu ràng buộc, họ có thể cố gắng làm cho chữ ký trên tài liệu lành tính được chấp nhận cho tài liệu khác.

Vì vậy, **kháng collision** đặc biệt quan trọng trong các giao thức mà bên tấn công có quyền chọn tài liệu được đưa ra để ký. Tuy nhiên, chỉ nêu `H(M)` chưa mô tả toàn bộ an ninh chữ ký: còn phải có thuật toán ký chuẩn, định dạng encode/verify phù hợp, kiểm soát domain/loại thông điệp, khóa ký được tin cậy và quyền ký.

### 5.3. Định danh nội dung, cache và Merkle tree

Digest có thể dùng để tham chiếu một blob nội dung (content addressing) hoặc tổ chức Merkle tree. Với nguồn dữ liệu và quy tắc encoding đã định, cùng byte sinh cùng digest, giúp kiểm tra tái sử dụng/cập nhật.

Nếu đầu vào do đối thủ kiểm soát, rủi ro collision và cách dùng hash làm **khóa định danh duy nhất** phải được xem xét. Ở cấu trúc cây, nên phân biệt rõ hash của leaf và hash của internal node bằng tag/domain separation để tránh nhập nhằng cấu trúc. Hash không tự chứng minh ai là người xuất bản nội dung.

### 5.4. Lưu mật khẩu: yêu cầu khác hẳn

**Không lưu `SHA-256(password)` trực tiếp** như password verifier. SHA-256 được thiết kế tính nhanh, trong khi mật khẩu do con người chọn thường dễ đoán. Hãy sử dụng password-hashing/KDF chuyên dụng có salt riêng và tham số chi phí được thiết lập hợp lý: Argon2id thường là lựa chọn ưu tiên trong hệ thống hỗ trợ; scrypt, bcrypt hoặc PBKDF2 có thể phù hợp theo ràng buộc triển khai, với thông số được thẩm định.

**Salt không phải khóa bí mật**: có thể lưu kèm verifier; mục đích là làm các bản ghi có cùng password dùng đầu vào khác nhau, ngăn tái sử dụng bảng băm tính trước trên nhiều bản ghi. Salt không làm mật khẩu yếu tự tăng entropy; lựa chọn hàm cố ý tốn tài nguyên tính toán/bộ nhớ mới giúp tăng chi phí đoán offline.

## 6. Bit, byte, hex và việc rút ngắn digest

Với SHA-256:

```text
256 bits = 32 bytes = 64 hexadecimal digits

"abc" (UTF-8): 61 62 63
SHA-256("abc"):
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

Độ dài hex không phải độ mạnh an ninh độc lập: 64 chữ số hex mã hóa 256 bit đầu ra, trong khi chuỗi 64 ký tự *văn bản* nói chung không nhất thiết có 256 bit entropy.

### 6.1. Rút ngắn digest có thể làm giảm an ninh nhanh

Nếu chỉ giữ `t` bit đầu trong digest rồi xem như định danh:

\[
H_t(M) = \operatorname{prefix}_t(H(M))
\]

thì trong mô hình đều, chống preimage mục tiêu ở mức cỡ `2^t`, còn chống collision chỉ ở mức cỡ `2^{t/2}`. Ví dụ giữ **16 bit đầu** của SHA-256 tạo ra một *hàm băm 16 bit mới* dễ có va chạm; phát hiện collision ở đó **không phải** phát hiện collision của toàn bộ SHA-256.

Không tự rút ngắn digest trong giao thức ký/xác thực hoặc thiết kế chống va chạm nếu chưa xác định security level, số lượng dữ liệu và các yêu cầu của chuẩn liên quan. Với mục đích kiểm tra dữ liệu chống sửa đổi có chủ đích, nên giữ đầu ra đầy đủ của thuật toán chuẩn khi có thể.

### 6.2. Khác biệt byte dẫn tới khác biệt digest

So sánh:

```text
"abc"      -> bytes 61 62 63
"abc\n"   -> bytes 61 62 63 0a
"ABC"      -> bytes 41 42 43
```

SHA-256 tính trên **byte thực tế**, không hiểu rằng hai chuỗi “trông tương đương”. Một tệp có CRLF khác LF có thể có digest khác; JSON có thứ tự thuộc tính hoặc khoảng trắng khác có thể có digest khác; văn bản Unicode có thể có nhiều cách mã hóa tổ hợp khác nhau.

Khi một giao thức yêu cầu hai bên tính digest/chữ ký của “cùng thông điệp”, phải chỉ rõ:
- Charset (ví dụ UTF-8), chuẩn hóa Unicode nếu có, cách mã hóa dòng/ký tự.
- Canonical serialization của JSON/XML/đối tượng, độ dài và phân cách các trường, thứ tự trường.
- Phiên bản format, domain/application context và những byte chính xác được bảo vệ.

**Không tùy tiện trim, lowercase hay normalize sau khi đã ký**: thao tác như vậy có thể làm thay đổi nghĩa nghiệp vụ hoặc gây nhập nhằng. Cần thống nhất format trước khi tính hash.

## 7. Java 17+: quan sát tính xác định và collision do cắt còn 16 bit

Ví dụ dưới đây dùng `MessageDigest` trong Java Cryptography Architecture (JCA). Chương trình tính SHA-256 của `abc`, so sánh digest, sau đó **cố ý chỉ lấy 16 bit đầu** để tìm một collision dễ quan sát.

Tạo tệp `HashFundamentalsDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;

public class HashFundamentalsDemo {
    private static byte[] sha256(String input) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        return md.digest(input.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        byte[] digest = sha256("abc");
        System.out.println("SHA-256(abc): "
                + HexFormat.of().formatHex(digest));

        System.out.println("Same input => same digest: "
                + MessageDigest.isEqual(sha256("abc"), sha256("abc")));
        System.out.println("abc vs abd same digest: "
                + MessageDigest.isEqual(sha256("abc"), sha256("abd")));

        // Demo: collision on a deliberately truncated 16-bit digest.
        // It does NOT claim a collision in full 256-bit SHA-256.
        Map<Integer, String> seen = new HashMap<>();
        for (int i = 0; i < 100_000; i++) {
            String input = "message-" + i;
            byte[] fullDigest = sha256(input);
            int prefix16 = ((fullDigest[0] & 0xff) << 8)
                    | (fullDigest[1] & 0xff);

            String previous = seen.putIfAbsent(prefix16, input);
            if (previous != null) {
                System.out.println("Collision on 16-bit prefix: "
                        + previous + " / " + input);
                System.out.printf("Prefix (hex): %04x%n", prefix16);
                System.out.println("Full SHA-256 equal: "
                        + MessageDigest.isEqual(sha256(previous), fullDigest));
                break;
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac HashFundamentalsDemo.java
java HashFundamentalsDemo
```

Kết quả (đã kiểm tra với JDK; đầu vào và thứ tự duyệt cố định):

```text
SHA-256(abc): ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
Same input => same digest: true
abc vs abd same digest: false
Collision on 16-bit prefix: message-126 / message-133
Prefix (hex): 6620
Full SHA-256 equal: false
```

Giải thích chi tiết:

1. `MessageDigest.getInstance("SHA-256")` tạo đối tượng tính SHA-256. `digest(byte[])` cho mảng **32 byte**, không phải chuỗi hex. `HexFormat.of().formatHex(...)` chỉ là cách hiển thị.
2. Hai lần băm chính xác cùng byte `abc` trả digest giống nhau. Đây là **tính xác định**, không phải một bằng chứng về kháng collision.
3. Băm `abc` và `abd` trả hai digest khác nhau; đây là **một quan sát** cho cặp cụ thể, không thể suy ra mọi cặp khác nhau đều có digest khác.
4. `prefix16` lấy 2 byte đầu, tức chỉ có `65.536` giá trị có thể. Chương trình ghi nhớ các tiền tố đã thấy và dừng khi gặp cặp trùng.
5. `message-126` và `message-133` cùng tiền tố `6620`, nhưng **toàn bộ SHA-256 khác nhau**. Đây là collision của hàm `H_16` do ta định nghĩa bằng cách cắt ngắn, không phải lỗ hổng SHA-256.
6. `MessageDigest.isEqual(...)` so sánh byte digest theo API dành cho so sánh giá trị băm. Nó **không biến** SHA-256 không khóa thành MAC; không dùng kết quả so khớp digest tự công bố để xác thực bên gửi.

Từ ví dụ, có thể tự thay `prefix16` thành 8 bit hoặc 24 bit để quan sát thay đổi trong số lượng mẫu cần thử, nhưng không dùng một thí nghiệm nhỏ để khẳng định xác suất “chắc chắn” cho mọi tập dữ liệu. Birthday bound mô tả **xác suất** dưới giả định phân phối phù hợp.

### 7.1. Vì sao ví dụ không “phá SHA-256”?

Chương trình tìm hai chuỗi `A,B` sao cho:

\[
\operatorname{prefix}_{16}(SHA256(A))
=
\operatorname{prefix}_{16}(SHA256(B)).
\]

Nhưng nó đồng thời kiểm tra:

\[
SHA256(A) \neq SHA256(B).
\]

Muốn chứng minh collision của **SHA-256 gốc**, phải chỉ ra hai thông điệp khác nhau có **toàn bộ 256 bit** digest trùng khớp. Việc đoán trúng một vài byte đầu chỉ là collision trên hàm bị rút ngắn do ta tạo ra.

### 7.2. Lưu ý dùng MessageDigest ngoài demo

- Chỉ định rõ `StandardCharsets.UTF_8` cho dữ liệu văn bản. Không lệ thuộc platform default charset.
- Đối tượng `MessageDigest` là mutable; không mặc định chia sẻ một instance giữa nhiều thread. Tạo instance theo lần dùng hoặc quản lý concurrency đúng cách.
- `digest(...)` xử lý mảng byte đầu vào; với file lớn nên đọc thành các khối và gọi `update(...)` nhiều lần, sau đó `digest()` để hoàn tất, thay vì buộc toàn bộ file vào RAM.
- Đừng dùng `new String(digestBytes, UTF_8)` để biểu diễn digest: digest là bytes ngẫu nhiên về mặt biểu diễn và có thể không tạo UTF-8 hợp lệ. Dùng hex/base64 nếu cần văn bản.
- Chỉ dựa vào digest so sánh với **giá trị kỳ vọng đáng tin** cho mục đích toàn vẹn; nếu phải xác thực đối tác, chọn HMAC/chữ ký hoặc giao thức xác thực thích hợp.

## 8. Các lỗi phổ biến và giới hạn của hàm băm

| Ngộ nhận/thiết kế | Vấn đề | Cách hiểu hoặc xử lý đúng |
| --- | --- | --- |
| “SHA-256 không thể có collision” | Đầu vào vô hạn, digest hữu hạn | Va chạm chắc chắn tồn tại; bảo mật dựa vào độ khó tìm |
| “Preimage, second preimage và collision giống nhau” | Quên ràng buộc thông điệp/digest đã cố định | Xác định chính xác điều đối thủ được chọn |
| “Hash 256 bit chống collision ở mức 256 bit” | Bỏ qua birthday bound | Độ khó collision tổng quát cỡ `2^128` |
| “Có cặp collision bất kỳ là thay được file M đã ký” | Không phân biệt collision với second preimage | Kiểm tra liệu kẻ tấn công có kiểm soát tài liệu trước khi ký không |
| “Lưu SHA-256(password) đã an toàn” | SHA-256 quá nhanh, mật khẩu entropy thấp | Dùng Argon2id/scrypt/bcrypt/PBKDF2 theo chính sách phù hợp cùng salt |
| “Hash là mã hóa, có thể decrypt hash” | Digest không có phép giải mã giữ nguyên dữ liệu | Dùng encryption khi cần giữ bí mật và giải mã |
| “Gửi SHA-256 cùng file chứng minh file từ server đúng” | Đối thủ có thể sửa cả hai | Digest/signature phải được xác thực qua trust source |
| “Chỉ cần hash(req) là xác thực API” | Hash không có bí mật và không chứng minh tác giả | Dùng HMAC hoặc chữ ký với quản lý khóa và identity binding |
| “Dùng `SHA-256(secret || message)` làm MAC” | Thiết kế tự chế có thể chịu length-extension/ambiguity | Dùng chuẩn HMAC-SHA256, không tự sáng tạo MAC |
| “Thay đổi 1 bit làm digest đổi mạnh ⇒ hash đã an toàn” | Avalanche không chứng minh kháng tấn công | Cần phân tích thuật toán và bằng chứng mật mã |
| “MD5/SHA-1 dùng cho chữ ký hiện đại vẫn đủ tốt” | Va chạm thực tế đã làm suy yếu các hàm này | Tránh MD5/SHA-1 cho an ninh collision; dùng thuật toán hiện đại được chấp nhận |
| “Chỉ so hai chuỗi hex nên không cần thống nhất encoding” | UTF-8/JSON/newline/Unicode khác → bytes khác | Chuẩn hóa format rõ ràng trước khi băm |
| “`String.hashCode()` và CRC32 cũng là hash nên có thể ký” | Không được thiết kế chống đối thủ tìm va chạm/giả mạo | Dùng hàm băm mật mã chuyên dụng |

### 8.1. Cẩn thận với thuật toán cũ và phép xây dựng tự chế

- **MD5** và **SHA-1** có các vấn đề va chạm đã được chứng minh thực tế, nên không phù hợp cho cơ chế an ninh đòi hỏi collision resistance hiện đại. Đừng đánh đồng việc một thuật toán vẫn tồn tại trong API tương thích với việc nó nên được chọn cho thiết kế mới.
- **SHA-256**, **SHA-384/512** và họ **SHA-3** là những họ hàm băm tiêu chuẩn dùng theo yêu cầu an ninh và chính sách tương thích. Chọn hàm phải xét security strength, yêu cầu hiệu năng, trường hợp ứng dụng, thuật toán ký/MAC liên quan và quy định hiện hành.
- Với SHA-256 kiểu Merkle–Damgård, biết `SHA-256(secret || message)` có thể tạo cơ hội cho **length-extension attack** khi một ứng dụng tự xây MAC bằng cách ghép secret vào trước message. Kháng preimage **không có nghĩa** ghép khóa vào SHA-256 đã trở thành MAC an toàn. Dùng HMAC theo chuẩn và phân định thông điệp/ngữ cảnh phù hợp.

Không nên tự thiết kế thuật toán hash, giao thức ký hoặc MAC chỉ bằng cách ghép string và thêm digest; các lỗi encoding, domain separation và xử lý trust thường không lộ ra trong unit test “hash đúng”.

## 9. Đọc tình huống theo đúng thuộc tính

**Tình huống 1 — Tệp đã công bố có digest đáng tin.** Bên tấn công muốn thay bản tải về bằng *một tệp khác* mà vẫn khớp chính digest đã công bố. Tệp/digest mục tiêu đã cố định. Đây gần với bài toán **second preimage** của tệp mục tiêu, dưới giả định digest được công bố xác thực.

**Tình huống 2 — Hai hợp đồng có cùng digest trước khi ký.** Bên tấn công tự làm hai hợp đồng, cho người dùng ký hợp đồng lành tính rồi chuyển chữ ký sang hợp đồng còn lại trong một giao thức không phân biệt thông điệp. Trọng tâm là khả năng tìm **collision**, đặc biệt là collision có tính chất mà tấn công yêu cầu.

**Tình huống 3 — Digest của một API token ngẫu nhiên.** Bên tấn công chỉ có digest và muốn tìm một giá trị bất kỳ có cùng digest. Đây là **preimage**; nếu token có entropy đủ cao thì khó về tổng quát. Nếu token chỉ là mã PIN 4 chữ số thì thử vét cạn theo tập giá trị khả dĩ có thể dễ.

**Tình huống 4 — Hai tệp lớn trong kho lưu trữ có 2 byte đầu SHA-256 giống nhau.** Đây là collision của **digest 16 bit bị rút ngắn**, và chưa cho biết có collision của SHA-256 đầy đủ hay không.

**Tình huống 5 — Attacker đổi file tải và đổi SHA-256 trên cùng website đã bị chiếm.** Ở đây không cần tấn công hash; lỗ hổng là **nguồn digest không đáng tin**. Phải xác thực nguồn hoặc chữ ký, không chỉ chọn hash dài hơn.

## 10. Bài tập tự kiểm tra

**Câu 1.** Với hàm băm 160 bit lý tưởng, độ khó tổng quát để tìm một cặp collision là cỡ bao nhiêu?

**Đáp án:** Cỡ `2^80` phép thử, khác với bài toán preimage mục tiêu cố định vốn cỡ `2^160` trong mô hình phù hợp.

**Câu 2.** Người kiểm tra giao digest `h` mà không giao thông điệp gốc. Bạn phải tìm `M` bất kỳ sao cho `H(M)=h`. Đây là thuộc tính gì?

**Đáp án:** Kháng tiền ảnh (preimage resistance).

**Câu 3.** Người kiểm tra đưa sẵn `M`; bạn cần `M' != M` nhưng `H(M')=H(M)`. Có được tự tạo hai thông điệp khác bất kỳ để tìm collision không?

**Đáp án:** Không. Đây là second-preimage challenge; thông điệp gốc đã cố định.

**Câu 4.** Một hàm băm `n=32` bit có `2^32` giá trị đầu ra. Khi thử vài chục nghìn đầu vào khác nhau, vì sao vẫn có thể xuất hiện collision sớm?

**Đáp án:** Vì số cặp giữa các mẫu tăng xấp xỉ theo bình phương số mẫu; birthday bound cho mức cỡ `2^16` mẫu thì collision đã có xác suất đáng kể, không cần thử hết `2^32` giá trị.

**Câu 5.** Vì sao `SHA-256("1234")` không làm mật khẩu “1234” có sức chống đoán tương đương khóa ngẫu nhiên 256 bit?

**Đáp án:** Không gian mật khẩu vẫn nhỏ và dễ đoán. Đối thủ có thể tính SHA-256 của các ứng viên và so sánh; cần mật khẩu đủ mạnh cùng password-hashing chuyên dụng và chính sách kiểm soát xác thực.

**Câu 6.** Bạn có thể xem hai SHA-256 digest của file được tính ở hai máy là “khác file” nếu một máy đã tự động chuyển CRLF thành LF không?

**Đáp án:** Có thể khác digest vì byte file khác, dù phần hiển thị trông gần giống. Cần thống nhất byte và quy tắc canonicalization khi bài toán yêu cầu cùng nội dung logic.

**Câu 7.** Tại sao hai thông điệp khác nhau cùng *4 ký tự hex đầu* của SHA-256 chưa chứng minh collision của SHA-256?

**Đáp án:** 4 hex chỉ biểu diễn 16 bit đầu; 240 bit còn lại có thể khác. Va chạm đầy đủ đòi hỏi cả 256 bit trùng.

## 11. Sơ đồ ghi nhớ

```text
               DỮ LIỆU BYTE M
                      |
              Cryptographic hash H
                      |
                Digest n bit
                      |
      +---------------+------------------+
      |               |                  |
  Preimage        Second preimage     Collision
  Cho trước h     Cho trước M         Tự chọn M1, M2
  Tìm M           Tìm M' != M         M1 != M2
  H(M) = h        H(M') = H(M)        H(M1) = H(M2)
  ~2^n            ~2^n               ~2^(n/2)
                      |
       Mốc độ khó trên là mô hình lý tưởng,
       không phải bảo đảm tuyệt đối mọi trường hợp
```

**Điểm cần nhớ:** *Một chiều* nói về sự khó khăn của việc tìm đầu vào cho digest cố định; *second preimage* yêu cầu thay thế một thông điệp đã biết mà giữ nguyên digest; *collision* cho phép chọn tự do cả hai thông điệp, vì thế chịu birthday bound. Tính chất mật mã của hash chỉ phát huy trong giao thức dùng đúng byte, đúng thuật toán, mức độ dài phù hợp và nguồn tin cậy được xác thực.

### Tài liệu tham khảo

- NIST FIPS 180-4, *Secure Hash Standard (SHS)* — định nghĩa SHA-256 và các thuật toán SHA-2: https://csrc.nist.gov/pubs/fips/180-4/upd1/final
- NIST FIPS 202, *SHA-3 Standard* — họ SHA-3: https://csrc.nist.gov/pubs/fips/202/final
- NIST SP 800-107 Rev. 1, *Recommendation for Applications Using Approved Hash Algorithms* — định nghĩa các mức an ninh của hash: https://csrc.nist.gov/pubs/sp/800/107/r1/final
- Java SE 17 API, `MessageDigest`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- Java SE 17 API, `HexFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html
- OWASP, *Password Storage Cheat Sheet* — hướng dẫn lưu mật khẩu chuyên dụng: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
