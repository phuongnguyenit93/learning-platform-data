# 6.11 Giới hạn của CipherInputStream khi cần phát hiện lỗi xác thực AEAD

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích AEAD xác thực điều gì và vì sao phải kiểm tra authentication tag trước khi sử dụng plaintext.
2. Nêu chính xác cảnh báo trong Java SE 17 đối với **javax.crypto.CipherInputStream** khi giải mã bằng AEAD như AES-GCM: một số lỗi xác thực có thể bị bắt và **không chuyển tiếp** cho code gọi.
3. Phân biệt **đọc hết InputStream mà không thấy IOException** với **đã xác thực thành công ciphertext**.
4. Dùng **javax.crypto.Cipher.doFinal()** trực tiếp để nhận lỗi **AEADBadTagException**, kiểm soát trường hợp ciphertext bị sửa, sai AAD, sai khóa hoặc bị cắt cụt.
5. Thiết kế quy trình giải mã giữ plaintext ở trạng thái **chưa được tin cậy** đến khi xác thực thành công, kể cả với dữ liệu lớn; tránh sử dụng đầu ra một phần, xử lý lỗi sai hoặc chấp nhận dữ liệu chưa đủ tag.

**Ý chính:** Khi ứng dụng bắt buộc phát hiện lỗi xác thực, không nên lấy việc đọc thành công từ **CipherInputStream** làm bằng chứng. Tài liệu Java 17 cảnh báo class này có thể nuốt lỗi integrity check trong quá trình giải mã GCM. **Cipher API trực tiếp**, đặc biệt **doFinal()**, cho phép quan sát kết quả xác thực rõ ràng hơn.

## 1. AEAD bảo vệ dữ liệu như thế nào?

**AEAD (Authenticated Encryption with Associated Data)** là mã hóa có xác thực. Với AES-GCM, ngoài bí mật của plaintext, hệ thống có thể kiểm tra tính toàn vẹn và xác thực theo khóa của ciphertext cùng **AAD**.

Các thành phần cần hiểu:

- **Key:** khóa AES bí mật, phải được bảo vệ và cấp quyền đúng cách.
- **Nonce/IV:** giá trị của lần mã hóa, thường 12 byte với GCM; **không được lặp lại khi dùng cùng khóa**. Nonce có thể lưu cùng ciphertext nhưng phải đúng byte ban đầu.
- **Plaintext:** dữ liệu trước khi mã hóa.
- **Ciphertext:** dữ liệu sau khi mã hóa.
- **Authentication tag:** mã xác thực do GCM tạo; thường 16 byte (128 bit), tính trên khóa, nonce, dữ liệu và AAD.
- **AAD (Additional Authenticated Data):** ngữ cảnh không cần giữ bí mật nhưng phải kiểm tra toàn vẹn, ví dụ tenant ID, loại bản ghi, version hoặc định danh tài nguyên.

Sơ đồ:

~~~text
MÃ HÓA:
plaintext + key + nonce + AAD
               |
        AES-GCM encrypt
               |
         ciphertext || tag
               |
       lưu/truyền cùng nonce

GIẢI MÃ:
ciphertext || tag + key + nonce + AAD
                   |
            AES-GCM decrypt
                   |
               Verify tag
                 /     \
               Đúng    Sai
                |       |
          plaintext   Từ chối
~~~

Trong Java JCA, **Cipher.getInstance("AES/GCM/NoPadding")** trả một Cipher có thể dùng cho mã hóa hoặc giải mã. Khi mã hóa, **Cipher.doFinal(plaintext)** tạo ciphertext kèm tag theo định dạng đầu ra của JCA/provider. Khi giải mã, **Cipher.doFinal(ciphertextWithTag)** xác minh tag. Nếu không khớp, phương thức có thể ném **AEADBadTagException**.

Một bản ghi có tag sai có thể là do ciphertext bị chỉnh sửa, sai khóa, sai nonce, sai AAD, bị cắt mất byte hoặc bị hỏng trong lưu/truyền. **Tag sai nghĩa là không xác thực được; không tự chứng minh nguyên nhân hoặc người gây ra lỗi.**

### 1.1 Tại sao phải kiểm tra tag trước khi dùng plaintext?

Giả sử một dịch vụ đọc thông tin tài khoản đã mã hóa AES-GCM từ storage. Kẻ tấn công sửa ciphertext trên disk mà không biết khóa. Hành vi đúng của dịch vụ là:

1. Giải mã và xác thực bằng đúng key/nonce/AAD.
2. Nếu tag sai, không trả hồ sơ hoặc bản ghi rỗng được đánh dấu hợp lệ.
3. Không ghi plaintext chưa xác thực vào cache, DB, response hoặc hệ thống downstream.
4. Phát hiện lỗi, xử lý theo quy trình và ghi log phù hợp, không rò key/plaintext.

Dùng dữ liệu trước khi xác thực hoàn tất làm mất mục tiêu bảo vệ toàn vẹn của AEAD.

## 2. CipherInputStream hoạt động thế nào?

**javax.crypto.CipherInputStream** bọc một **InputStream** nền và một **Cipher** đã khởi tạo. Mỗi khi bên gọi read(), lớp bọc đọc byte nguồn và đưa qua Cipher trước khi trả dữ liệu cho phía gọi.

~~~text
encrypted.bin
     |
  InputStream
     |
CipherInputStream
  [Cipher]
     |
read()/readAllBytes()
     |
byte[] đầu ra
~~~

API này thuận tiện khi muốn xử lý luồng byte theo giao diện InputStream. Nhưng vì hoạt động trên hai lớp trừu tượng khác nhau, **hợp đồng về exception không giống trực tiếp Cipher API**.

### 2.1 Cảnh báo chính thức trong Java SE 17

JavaDoc Java 17 của **CipherInputStream** ghi rõ lớp này tuân thủ semantics, đặc biệt **failure semantics**, của **FilterInputStream** và **InputStream**. Nó bắt các exception không thuộc tập ngoại lệ mà giao diện lớp cha khai báo. Cụ thể:

- Nó **có thể bắt BadPaddingException và các exception khác** xuất hiện khi kiểm tra tính toàn vẹn thất bại trong lúc giải mã.
- Những exception đó **không được ném lại**, nên code gọi **có thể không biết** kiểm tra integrity đã thất bại.
- Vì vậy, CipherInputStream **có thể không phù hợp để giải mã chế độ authenticated encryption như GCM**.
- Ứng dụng cần authenticated encryption có thể sử dụng **Cipher API trực tiếp** thay thế.

Nguồn gốc kỹ thuật:

- [Oracle Java SE 17 — CipherInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/CipherInputStream.html)
- [Oracle Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html)
- [Oracle Java SE 17 — AEADBadTagException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/AEADBadTagException.html)

**Độ chính xác trong diễn giải:** tài liệu nói **có thể** bỏ qua lỗi xác thực, không có nghĩa mọi JVM/provider luôn có cùng kết quả. Một provider hay một lần thử phát hiện lỗi đúng **không tạo ra bảo đảm portable cho mọi môi trường**.

### 2.2 Tại sao exception mật mã có thể biến mất?

Trong mô hình Cipher:

~~~text
Cipher.doFinal(ciphertextAndTag)
          |
     Verify tag
       /     \
     OK       FAILED
      |          |
  plaintext   AEADBadTagException
~~~

Trong mô hình CipherInputStream:

~~~text
Stream.read()
    |
Cipher (có thể gọi doFinal khi kết thúc input)
    |
Tag verification thất bại
    |
BadPaddingException / AEADBadTagException
    |
CipherInputStream có thể bắt và không chuyển tiếp
    |
Bên đọc stream có thể không nhận được tín hiệu tag sai
~~~

**AEADBadTagException** là subclass của **BadPaddingException**, mà BadPaddingException thuộc nhóm **GeneralSecurityException**. **InputStream.read()** chủ yếu tuân theo hợp đồng **IOException**. Việc bọc Cipher vào InputStream không đương nhiên biến mọi lỗi mật mã thành IOException truyền ra ngoài.

Không nên suy ra “CipherInputStream bảo vệ được dữ liệu vì bên trong dùng Cipher đúng”. Thuật toán có thể phát hiện sai tag nhưng **bên ngoài lại không quan sát được lỗi**.

## 3. Ví dụ anti-pattern: đọc hết không đồng nghĩa xác thực thành công

Đoạn Java sau chỉ là minh họa một cách dùng dễ gây hiểu nhầm; các biến Cipher/InputStream đã được khởi tạo bên ngoài, nên đây **không phải chương trình độc lập**.

~~~java
// decryptCipher là Cipher AES-GCM đã init ở DECRYPT_MODE.
// encryptedInput chứa nonce đã được xử lý ở bước init,
// còn luồng này chứa ciphertext || authentication tag.
try (CipherInputStream stream =
         new CipherInputStream(encryptedInput, decryptCipher)) {

    byte[] received = stream.readAllBytes();

    // Không được suy ra tag hợp lệ chỉ vì readAllBytes() không throw.
    // Không sử dụng received như plaintext đã xác thực.
}
~~~

Vấn đề nằm ở giả định ngầm của lập trình viên:

~~~text
"readAllBytes không ném IOException"
                  |
                  v
"Tag chắc chắn đã được kiểm tra thành công"   <- SUY LUẬN SAI
                  |
                  v
"Được phép dùng dữ liệu làm đầu vào nghiệp vụ"
~~~

Khi tag không hợp lệ, tùy provider, bạn có thể thấy lỗi, đầu ra thiếu/rỗng hoặc hành vi khác; không nên tự dựa vào một kết quả thực nghiệm cụ thể rồi coi nó là hợp đồng của API.

### 3.1 Cả readAllBytes(), close() và catch(IOException) đều không sửa được vấn đề

| Cách xử lý | Điều thực sự làm được | Điều không được bảo đảm |
| --- | --- | --- |
| **readAllBytes()** | Cố đọc toàn bộ byte cho tới EOF, trừ khi có lỗi đọc | Không buộc wrapper phải ném lại lỗi tag mà nó đã bắt |
| **try-with-resources/close()** | Giải phóng resource đúng vòng đời | Không chứng minh toàn bộ message đã được xác thực |
| **catch(IOException)** | Bắt các IOException được truyền ra | Không bắt một AEADBadTagException đã bị wrapper giữ lại |
| **available()** | Báo ước lượng byte có thể đọc không chặn theo giao diện InputStream | Không phải trạng thái integrity check hay tag |
| **skip()** | Bỏ qua byte theo semantics stream | Không xác thực thay cho quy trình kết thúc Cipher |
| **Kiểm tra plaintext có dữ liệu** | Có thể kiểm tra độ dài hoặc cú pháp cơ bản | Không xác minh tính toàn vẹn mật mã |

Đóng stream thành công **không tương đương** với **doFinal đã trả plaintext sau khi xác minh tag thành công**.

### 3.2 Lỗi đọc và lỗi xác thực là hai loại sự cố

Một **IOException** có thể đến từ filesystem, mạng hoặc InputStream nền. Còn **AEADBadTagException** cho thấy authentication tag không phù hợp với key, nonce, AAD và ciphertext được đưa vào Cipher.

Ứng dụng nên phân biệt:

- **Lỗi format** trước khi giải mã (version, cấu trúc, thiếu nonce, payload quá ngắn).
- **Lỗi đọc nguồn** (disk/network).
- **Lỗi xác thực** khi gọi Cipher.doFinal.
- **Lỗi nghiệp vụ** sau khi có plaintext đã xác thực.

Không biến tất cả thành “tệp rỗng” hoặc “chưa có dữ liệu”. Tuy nhiên khi trả lỗi cho client không tin cậy, hạn chế thông tin nhạy cảm và tránh tạo oracle tiết lộ chi tiết xử lý mật mã.

## 4. Thiết kế an toàn cho payload có giới hạn kích thước

Với một bản ghi hoặc file có kích thước phù hợp bộ nhớ:

1. **Giới hạn kích thước đầu vào** trước và trong lúc đọc.
2. Phân tích **version, key ID nếu có, nonce và ciphertext/tag**, kiểm tra cấu trúc tối thiểu.
3. Lấy khóa từ key manager/KMS phù hợp, giới hạn quyền sử dụng.
4. **Cipher.init(DECRYPT_MODE, key, new GCMParameterSpec(tagBits, nonce))**.
5. Gọi **Cipher.updateAAD(aad)** trước khi đưa ciphertext vào Cipher.
6. Gọi trực tiếp **Cipher.doFinal(ciphertextWithTag)**. Phương thức trả plaintext khi thành công hoặc ném lỗi mật mã khi thất bại.
7. **Chỉ sau khi doFinal thành công** mới công bố hoặc xử lý plaintext.
8. Khi thất bại, từ chối bản ghi; không dùng byte trung gian, không thử chế độ bảo mật yếu hơn.

~~~text
Input ciphertext có giới hạn
            |
Kiểm tra header/nonce/version
            |
Cipher.init(DECRYPT_MODE)
Cipher.updateAAD(...)
            |
Cipher.doFinal(ciphertext || tag)
        /                 \
   thành công         AEADBadTagException
        |                 |
Dùng plaintext        Từ chối, không publish
~~~

Tại sao đây là khác biệt quan trọng? Bên gọi **trực tiếp nhận kết quả cuối của Cipher**, và exception xác thực không phải đi qua một lớp InputStream có semantics cho phép bỏ qua nó.

## 5. Ví dụ Java 17+ hoàn chỉnh: phát hiện sai tag bằng doFinal

Chương trình tự sinh khóa AES cho **một lần chạy minh họa**, mã hóa bằng AES-GCM và thử giải mã trong bốn tình huống: gói đúng, tag bị sửa, AAD sai và thiếu byte cuối.

Định dạng binary minh họa:

~~~text
+------------+----------------+---------------------------+
| version 1B | nonce 12 bytes | ciphertext || tag 16 B   |
+------------+----------------+---------------------------+
~~~

Ứng dụng thực tế phải bổ sung key ID, chính sách nonce, giao thức lưu trữ/truyền, giới hạn dung lượng và xử lý lỗi/rotation. Ví dụ này dùng dữ liệu công khai và **không đưa khóa vào output**.

Tạo tệp **AeadDoFinalDemo.java** và lưu UTF-8:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;

import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AeadDoFinalDemo {
    private static final byte VERSION = 1;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final SecureRandom RANDOM = new SecureRandom();

    private static byte[] encrypt(byte[] plaintext,
                                  SecretKey key,
                                  byte[] aad)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        byte[] ciphertextWithTag = cipher.doFinal(plaintext);

        return ByteBuffer.allocate(
                    1 + NONCE_BYTES + ciphertextWithTag.length)
                .put(VERSION)
                .put(nonce)
                .put(ciphertextWithTag)
                .array();
    }

    private static byte[] decrypt(byte[] packet,
                                  SecretKey key,
                                  byte[] aad)
            throws GeneralSecurityException {
        if (packet.length < 1 + NONCE_BYTES + TAG_BYTES) {
            throw new IllegalArgumentException("Payload qua ngan");
        }

        ByteBuffer input = ByteBuffer.wrap(packet);
        if (input.get() != VERSION) {
            throw new IllegalArgumentException("Version khong hop le");
        }

        byte[] nonce = new byte[NONCE_BYTES];
        input.get(nonce);

        byte[] ciphertextWithTag = new byte[input.remaining()];
        input.get(ciphertextWithTag);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);

        // Trả plaintext sau khi tag được xác thực,
        // hoặc ném AEADBadTagException nếu tag không hợp lệ.
        return cipher.doFinal(ciphertextWithTag);
    }

    private static boolean tagRejected(byte[] packet,
                                       SecretKey key,
                                       byte[] aad)
            throws GeneralSecurityException {
        try {
            decrypt(packet, key, aad);
            return false;
        } catch (AEADBadTagException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] plaintext = "Ban ghi thu nghiem"
                .getBytes(StandardCharsets.UTF_8);
        byte[] aad = "record:42".getBytes(StandardCharsets.UTF_8);

        byte[] packet = encrypt(plaintext, key, aad);
        byte[] recovered = decrypt(packet, key, aad);

        System.out.println("Ban goc hop le: "
                + Arrays.equals(plaintext, recovered));

        byte[] tampered = packet.clone();
        tampered[tampered.length - 1] ^= 1;
        System.out.println("Sua tag bi tu choi: "
                + tagRejected(tampered, key, aad));

        byte[] wrongAad = "record:43"
                .getBytes(StandardCharsets.UTF_8);
        System.out.println("Sai AAD bi tu choi: "
                + tagRejected(packet, key, wrongAad));

        byte[] truncated = Arrays.copyOf(
                packet, packet.length - 1);
        System.out.println("Thieu byte cuoi bi tu choi: "
                + tagRejected(truncated, key, aad));

        Arrays.fill(plaintext, (byte) 0);
        Arrays.fill(recovered, (byte) 0);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 AeadDoFinalDemo.java
java AeadDoFinalDemo
~~~

Stdout dự kiến trên triển khai AES-GCM thông dụng của JDK 17:

~~~text
Ban goc hop le: true
Sua tag bi tu choi: true
Sai AAD bi tu choi: true
Thieu byte cuoi bi tu choi: true
~~~

Diễn giải:

- **Ban goc hop le: true:** cùng key, nonce và AAD; tag hợp lệ; doFinal trả lại plaintext đúng.
- **Sua tag bi tu choi: true:** lật một bit trong byte cuối của tag; doFinal không trả plaintext mà ném AEADBadTagException.
- **Sai AAD bi tu choi: true:** giữ nguyên ciphertext/tag nhưng đổi context từ record:42 thành record:43. Tag không phù hợp với AAD mới.
- **Thieu byte cuoi bi tu choi: true:** input vẫn vượt kiểm tra độ dài cấu trúc tối thiểu, nhưng tag bị thiếu một byte, khiến xác thực thất bại.

Nonce và key là ngẫu nhiên nên ciphertext thay đổi mỗi lần chạy; chương trình không in ciphertext/tag và chỉ in những điều kiện đúng/sai có thể kiểm chứng. Phần phát hiện lỗi cụ thể phụ thuộc provider JCA được sử dụng, nhưng dùng Cipher.doFinal có hợp đồng ném lỗi AEAD trong Java SE 17.

**Lưu ý:** ví dụ không quản lý key bền vững và không phải giao thức production. Arrays.fill() chỉ xóa các byte[] mà code kiểm soát, không đảm bảo xóa mọi bản sao trong JVM.

### 5.1 Phân biệt AEADBadTagException với lỗi dữ liệu khác

**AEADBadTagException** kế thừa **BadPaddingException**, có thể được bắt riêng để phân biệt với lỗi cấu trúc đã phát hiện trước khi gọi Cipher. Nhưng lỗi xác thực không nói chắc nguyên nhân là tấn công, hỏng tệp hay sai metadata.

Không nên dùng đường fallback như:

~~~text
GCM tag sai
     |
Thử giải mã lại mà không xác thực tag
     |
Chấp nhận nội dung "đọc được"
~~~

Đó là việc bỏ qua thuộc tính integrity cốt lõi của AEAD. **Từ chối toàn bộ bản ghi** là kết quả an toàn khi tag sai.

## 6. Cảnh báo khác: plaintext từ Cipher.update cũng chưa được xác thực

Giả sử bạn không dùng CipherInputStream mà tự viết vòng lặp đọc ciphertext theo chunk. Code gọi **Cipher.update(...)** có thể trả về byte[] trung gian; lượng byte trả về phụ thuộc provider và chế độ.

~~~text
cipher.update(chunk1) -> candidatePlaintext1 (có thể rỗng)
cipher.update(chunk2) -> candidatePlaintext2 (có thể rỗng)
...
cipher.doFinal(lastChunkAndTag) -> phần cuối HOẶC lỗi xác thực
~~~

**Không được gọi candidatePlaintext là “đã được xác thực” trước khi doFinal thành công.** Một số provider có thể giữ mọi plaintext tới cuối; provider khác có thể cung cấp byte sớm hơn. Ứng dụng phải xử lý theo yêu cầu bảo mật chứ không dựa vào cách provider đệm byte cụ thể.

Nếu code đã:

- Ghi candidatePlaintext vào database thật;
- Đưa byte sang bộ parse hoặc giải nén nhạy cảm;
- Phát dữ liệu ra HTTP response;
- Gửi event, mở khóa tài nguyên hoặc cập nhật trạng thái nghiệp vụ;

thì một lỗi tag xảy ra ở cuối **không thể tự động hoàn tác** các side effect đã xuất hiện.

Quy tắc: **Giữ dữ liệu chưa xác thực cách ly cho đến khi bước xác minh cuối thành công.**

## 7. Giải mã file lớn an toàn

### 7.1 Cách đơn giản cho file có kích thước được giới hạn

Nếu payload phù hợp RAM:

1. Giới hạn kích thước file/request một cách thực tế.
2. Đọc toàn bộ byte encrypted payload kèm tag (đây là việc đọc byte thường, không phải CipherInputStream để xác thực).
3. Gọi Cipher.doFinal trực tiếp.
4. Chỉ chuyển kết quả plaintext cho nghiệp vụ nếu không có exception.

**Files.readAllBytes/InputStream.readAllBytes** có thể cấp phát rất nhiều bộ nhớ; không phù hợp nguồn không đáng tin hoặc file vượt giới hạn. Cần kiểm tra kích thước trước và trong lúc đọc hoặc dùng cơ chế bounded read.

### 7.2 Cách staging cho file lớn

Nếu phải giải mã theo chunk để tiết kiệm RAM:

1. Parse metadata, kiểm tra chính sách key/version/nonce/AAD và giới hạn dữ liệu.
2. Dùng **Cipher.update()** trực tiếp để xử lý những chunk ciphertext, giữ mọi output mà provider trả về trong **staging riêng biệt**, không cho client hoặc nghiệp vụ dùng.
3. Sau khi thực sự đọc đến cuối ciphertext **bao gồm tag**, gọi **Cipher.doFinal()**; đưa output còn lại (nếu có) vào staging.
4. Nếu **doFinal thất bại**, loại bỏ staging và hủy mọi thao tác; không publish bản ghi.
5. Nếu **doFinal thành công**, đóng staging, thực hiện commit/move sang vị trí chính thức qua quy trình bảo đảm tính nhất quán, chẳng hạn atomic rename khi filesystem hỗ trợ hoặc transaction thích hợp.
6. Bảo vệ staging bằng quyền truy cập nghiêm ngặt, thời hạn lưu, quy tắc dọn lỗi; lưu ý staging có thể chứa **plaintext nhạy cảm chưa xác thực**.

Hạn chế quan trọng: **GCM tag xác thực toàn bộ bản ghi**. Nếu app cần truyền từng chunk plaintext cho client **trước khi nhận tag ở cuối**, một ciphertext GCM duy nhất không cho bảo đảm mỗi chunk độc lập đã được xác thực.

Trong trường hợp cần streaming online thật sự, phải **thiết kế protocol phân mảnh có xác thực**: mỗi chunk là một AEAD record riêng với nonce duy nhất, AAD gắn record number/stream ID, và cơ chế phát hiện mất, lặp, đảo thứ tự hoặc cắt cụt record cuối. Việc cắt một ciphertext GCM thành các mảnh rồi cho rằng mỗi mảnh có tag riêng là **không đúng**.

### 7.3 Vì sao không thể chỉ đóng stream ở cuối?

Close() giải phóng resource theo hợp đồng InputStream/FilterInputStream. Nó không sửa được việc lỗi xác thực từ Cipher có thể đã bị CipherInputStream giữ lại. Vì vậy:

~~~text
try (CipherInputStream stream = ...) {
    byte[] bytes = stream.readAllBytes();
}
// Thoát try bình thường.
~~~

**Không đồng nghĩa** với:

~~~text
Cipher.doFinal() đã xác thực tag thành công
và trả plaintext hợp lệ cho đúng thông điệp.
~~~

Mọi quy trình dựa vào việc “đọc hết + đóng stream không lỗi” để khẳng định GCM integrity đều cần được xem xét lại.

## 8. Checklist đúng cho AES-GCM

Đổi API chỉ giải quyết phần **phát hiện lỗi xác thực**, không sửa được thiết kế mật mã sai.

| Yêu cầu | Vì sao cần |
| --- | --- |
| Nonce duy nhất khi dùng cùng key | Lặp nonce AES-GCM có thể phá hỏng bí mật và toàn vẹn |
| Khóa được quản lý riêng, đúng quyền | Kẻ biết khóa có thể tạo ciphertext/tag hợp lệ |
| AAD đúng thứ tự và cùng byte hai phía | AAD sai phải làm tag verification thất bại |
| Phiên bản định dạng và thuật toán cố định/allowlist | Không để attacker ép dùng chế độ yếu hoặc diễn giải khác |
| Có đủ ciphertext và tag trước khi doFinal | Thiếu tag không thể xác thực |
| Giới hạn kích thước input và output | Tránh cạn RAM, disk, CPU khi gặp input không tin cậy |
| Không dùng output trước final success | Đảm bảo không tiêu thụ plaintext chưa xác thực |
| Hủy staging khi lỗi xác thực | Tránh artifact giả được phục vụ như dữ liệu hợp lệ |
| Không log key/plaintext hay debug payload nhạy cảm | Ngăn rò dữ liệu qua quan sát vận hành |
| Chống replay nếu nghiệp vụ cần | AEAD đúng tag không ngăn phát lại gói cũ |
| Có test sai tag, sai AAD, cắt cụt | Chứng minh đường xử lý lỗi đang từ chối dữ liệu |

### 8.1 Lưu ý nonce và key rotation

AES-GCM yêu cầu không lặp nonce với cùng khóa. Nhiều ví dụ sinh nonce ngẫu nhiên 12 byte, nhưng hệ thống mã hóa số lượng lớn phải thiết kế chính sách giới hạn lưu lượng, quản lý nonce và key rotation để giảm nguy cơ va chạm. Nonce không bí mật, có thể lưu cạnh ciphertext. Key phải được bảo vệ bằng KMS/secret manager hoặc cơ chế phù hợp.

Không hardcode khóa vào Java source, không ghi key vào header, log hoặc URL. Khi đổi khóa, bản ghi cũ có thể cần key ID để chọn đúng khóa giải mã. Đừng vô hiệu hóa xác thực chỉ vì một bản ghi cũ lỗi sau rotation.

### 8.2 AAD và ngữ cảnh bản ghi

AAD có thể gồm tenant ID, record ID, version hoặc context nghiệp vụ cần ràng buộc với ciphertext. Nó không được mã hóa bí mật nhưng được đưa vào phép xác thực. Bên giải mã phải cung cấp đúng byte AAD trước khi đưa ciphertext vào Cipher.

Nếu ứng dụng tự chuyển object thành JSON rồi parse và serialize lại, thứ tự field, khoảng trắng hoặc Unicode normalization có thể thay đổi byte. Cần quy định dạng canonical và metadata được bảo vệ rõ ràng, tránh “dữ liệu logic giống nhau” nhưng tag khác vì byte khác.

### 8.3 Từ chối dữ liệu có tag sai không có nghĩa xác định được thủ phạm

GCM không phân biệt:

- attacker chủ động thay ciphertext;
- bản sao backup bị cắt cụt;
- lỗi storage truyền thiếu byte;
- lấy sai key từ keystore;
- đưa sai nonce;
- AAD không cùng ngữ cảnh.

Mọi trường hợp đều phải từ chối sử dụng dữ liệu chưa xác thực. Để phân tích nguyên nhân, cần log metadata không nhạy cảm, kiểm tra hạ tầng và quy trình khôi phục có kiểm soát; không xuất key hoặc plaintext để “debug nhanh”.

## 9. Bảng quyết định chọn API

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Giải mã một bản ghi GCM nhỏ và phải biết chắc tag đúng | Cipher.doFinal trực tiếp, bắt AEADBadTagException |
| Đọc một file lớn mã hóa thành một bản ghi GCM | Cipher.update/doFinal trực tiếp, staging không công bố trước final success |
| Phục vụ plaintext của từng chunk trước khi đến cuối file | Thiết kế giao thức AEAD theo record, xác thực từng record và tính đầy đủ của luồng |
| Đang dùng CipherInputStream rồi xem “không IOException” là thành công | Sửa thiết kế: đây không phải kết quả xác thực AEAD đáng tin |
| Dùng CipherInputStream trong tình huống không cần nhận lỗi integrity AEAD | Đánh giá theo mode và API contract cụ thể; không áp dụng kết luận rộng ngoài phạm vi |
| Input hợp lệ về Base64 nhưng tag không hợp lệ | Reject tại Cipher.doFinal; Base64 chỉ là mã hóa biểu diễn |
| Tag hợp lệ nhưng bản ghi đã được gửi từ hôm trước | Thêm freshness/anti-replay theo giao thức; tag không tự kiểm tra tính mới |

### 9.1 Những hiểu nhầm phổ biến

1. **“CipherInputStream luôn ném AEADBadTagException nếu tag sai.”** Không có bảo đảm đó theo JavaDoc.
2. **“Cứ readAllBytes rồi catch IOException là an toàn.”** Lỗi xác thực có thể bị lớp wrapper che mất.
3. **“close() sẽ báo lỗi tag còn thiếu.”** Không được coi đó là hợp đồng xác thực.
4. **“Cipher.update luôn trả plaintext ngay.”** Hành vi đệm phụ thuộc provider.
5. **“Provider của tôi hiện đệm tới cuối nên chắc mọi provider cũng vậy.”** Không nên dùng quan sát đó thay hợp đồng bảo mật.
6. **“Có doFinal ở cuối rồi, trước đó stream plaintext ra HTTP cũng được.”** Không: dữ liệu chưa xác thực đã được công bố.
7. **“Tag sai nhưng phần đầu plaintext trông hợp lệ, vẫn xử lý được.”** Không: toàn bộ bản ghi chưa vượt xác thực.
8. **“available() bằng 0 nghĩa là đã xác thực xong.”** Không: available không báo trạng thái tag/EOF.
9. **“Sai tag chỉ có thể do attacker sửa ciphertext.”** Không: key, nonce, AAD, lỗi lưu/truyền hoặc thiếu byte cũng là nguyên nhân.
10. **“Tôi đã dùng GCM nên không cần nonce policy.”** Không: nonce lặp với cùng khóa là lỗi nghiêm trọng.
11. **“Có thể tự cắt file GCM thành chunk và coi mỗi chunk đã được xác thực.”** Không: cần framing AEAD có tag riêng cho từng record và kiểm tra sự đầy đủ của luồng.
12. **“Base64 decode thành công nghĩa là ciphertext đáng tin.”** Không: phải xác thực GCM tag.

## 10. Tình huống thực tế

**Tình huống A — Hồ sơ khách hàng bị sửa trên disk.** Dịch vụ đọc qua CipherInputStream và nhận mảng byte rỗng hoặc thiếu, nhưng không thấy IOException; ứng dụng ghi đè hồ sơ bằng dữ liệu rỗng. Đây là lỗi **diễn giải tín hiệu thành công của stream**. Cần đổi sang Cipher.doFinal trực tiếp, từ chối bản ghi khi tag không hợp lệ và không commit bất kỳ dữ liệu chưa xác thực nào.

**Tình huống B — Giải nén trước kiểm tra tag.** Một pipeline giải mã GCM → giải nén → parse → nhập DB có thể xử lý byte chưa xác thực trước khi doFinal. Nếu tag sai ở cuối, tác động từ parser/DB có thể đã xảy ra. Giải pháp: stage plaintext chưa xác thực, verify toàn bộ trước khi cho logic nhạy cảm truy cập; đặt giới hạn dung lượng để tránh tấn công tài nguyên.

**Tình huống C — File hàng GB không thể readAllBytes.** Không cần nhét toàn bộ plaintext vào RAM. Dùng Cipher.update/doFinal trực tiếp và staging an toàn; chỉ đổi trạng thái file sang “đã xác thực” sau doFinal, rồi mới mở cho người dùng/ứng dụng. Nếu phải phát từng phần trước khi có tag cuối, thiết kế bản ghi AEAD riêng có liên kết thứ tự và dấu kết thúc.

**Tình huống D — Sai AAD sau khi chuyển tenant.** Ciphertext và tag không đổi, nhưng ứng dụng dùng AAD với tenant ID mới. doFinal ném AEADBadTagException. Đây là cơ chế bảo vệ đúng: ciphertext không được dùng sai ngữ cảnh. Không bỏ AAD để làm cho “giải mã thành công”.

**Tình huống E — InputStream bị ngắt giữa chừng.** Không thể lấy phần byte đã giải mã rồi coi là kết quả. Ứng dụng phải từ chối bản ghi không đầy đủ, xử lý I/O failure riêng, và không công bố artifact cho tới khi toàn bộ dữ liệu cùng tag được xác thực.

### 10.1 Bảng test thiết yếu

| Test | Kết quả đúng |
| --- | --- |
| Key + nonce + AAD + ciphertext/tag đều đúng | doFinal trả plaintext chính xác |
| Lật một bit của ciphertext | Từ chối, không publish plaintext |
| Lật một bit của tag | AEADBadTagException hoặc lỗi xác thực phù hợp |
| Đổi AAD | Từ chối, không dùng output |
| Đổi key hoặc nonce | Từ chối do xác thực không hợp lệ |
| Cắt bỏ một phần tag | Từ chối, không coi đó là file hợp lệ |
| Input thiếu version/nonce | Reject tại kiểm tra định dạng |
| Giải mã staging rồi tag fail | Xóa staging, không tạo output chính thức |
| Đọc source bị IOException | Fail closed, không công bố byte một phần |
| Thử nhiều provider/JDK được hỗ trợ | Luồng lỗi qua Cipher API vẫn được xử lý đúng |

Test quan trọng nhất không chỉ là “có exception”, mà còn là **không có side effect từ dữ liệu chưa xác thực**.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Nếu CipherInputStream.readAllBytes() trả về bình thường, đã chắc tag AES-GCM hợp lệ chưa?

**Trả lời:** Chưa. JavaDoc cảnh báo CipherInputStream có thể bắt và không truyền lỗi integrity check ra ngoài.

**Câu 2.** Muốn bắt lỗi xác thực GCM rõ ràng trong Java 17 thì nên dùng gì?

**Trả lời:** Dùng Cipher trực tiếp, gọi doFinal với đúng key, nonce, AAD và ciphertext/tag; bắt AEADBadTagException và từ chối dữ liệu nếu lỗi.

**Câu 3.** Có thể dùng các byte Cipher.update trả về ngay cho nghiệp vụ không?

**Trả lời:** Không được xem đó là plaintext đã xác thực khi chưa có doFinal thành công. Cần giữ trong staging hoặc bộ đệm chưa công bố.

**Câu 4.** Tại sao close() không đủ?

**Trả lời:** Close chỉ hoàn tất vòng đời resource; nó không bảo đảm lỗi xác thực đã bị lớp wrapper giữ lại sẽ được truyền tới caller.

**Câu 5.** Tag sai có chứng minh chắc chắn có tấn công không?

**Trả lời:** Không. Dữ liệu hỏng, thiếu byte, sai key, nonce hoặc AAD đều có thể khiến doFinal thất bại.

**Câu 6.** Nếu file quá lớn để giữ toàn bộ trong RAM thì có phải quay lại CipherInputStream không?

**Trả lời:** Không. Có thể dùng Cipher.update/doFinal trực tiếp với staging an toàn; chỉ publish sau khi tag được xác thực.

**Câu 7.** Có thể cắt một ciphertext GCM lớn thành các chunk rồi xác thực từng chunk bằng tag cuối không?

**Trả lời:** Không. Muốn xác thực từng chunk độc lập cần thiết kế record AEAD với nonce/tag riêng, thứ tự và tính đầy đủ của luồng được bảo vệ.

**Câu 8.** Vì sao mã hóa AES-GCM vẫn cần quản lý nonce?

**Trả lời:** Tái sử dụng nonce với cùng key gây nguy cơ nghiêm trọng cho bí mật và toàn vẹn, dù API giải mã có báo lỗi tag đúng cách.

## Kết luận

**CipherInputStream là API đọc byte tiện lợi nhưng không phải tín hiệu xác thực AEAD đáng tin trong mọi trường hợp.** Khi bảo mật phụ thuộc vào việc phát hiện tag sai, dùng **Cipher.doFinal() trực tiếp**, kiểm soát key/nonce/AAD và từ chối dữ liệu khi lỗi. Với xử lý stream lớn, giữ plaintext trong vùng tạm chưa được tin cậy và chỉ công bố sau khi bước xác thực cuối cùng thành công.
