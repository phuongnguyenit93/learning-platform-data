# 6.9 ChaCha20, ChaCha20-Poly1305 và quản lý nonce

**ChaCha20** là stream cipher hiện đại dùng khóa bí mật 256 bit để tạo luồng byte giả ngẫu nhiên (*keystream*) rồi XOR với dữ liệu cần mã hóa. **ChaCha20-Poly1305** kết hợp ChaCha20 với cơ chế xác thực Poly1305 để tạo **AEAD** (*Authenticated Encryption with Associated Data*): vừa bảo vệ bí mật bản rõ, vừa phát hiện nội dung và metadata được xác thực bị thay đổi. Cả hai đòi hỏi quản lý **nonce** cẩn thận. Lặp nonce với cùng khóa có thể làm lộ thông tin bản rõ; với ChaCha20-Poly1305 còn phá vỡ các giả định bảo mật của thẻ xác thực.

Bài học thuộc phần **mã hóa đối xứng** của Java Cryptography Architecture/Extension (JCA/JCE). Mục tiêu là hiểu thuật toán, dùng đúng API Java 17+, và thiết kế vòng đời nonce an toàn khi ứng dụng có nhiều bản tin, luồng, tiến trình hoặc phải phục hồi sau sự cố.

## 1. Phân biệt rõ ba khái niệm

| Thành phần | Chức năng | Kích thước theo biến thể IETF/RFC 8439 | Điều không được nhầm |
| --- | --- | --- | --- |
| **ChaCha20** | Mã hóa/giải mã bằng XOR với keystream | Khóa **256 bit**; nonce **96 bit**; bộ đếm block **32 bit**; block keystream **64 byte** | Chỉ bảo mật nội dung; **không tự phát hiện sửa ciphertext**. |
| **Poly1305** | Bộ xác thực thông điệp với **khóa dùng một lần** | Tag **128 bit (16 byte)** | Không dùng Poly1305 độc lập với một khóa dùng đi dùng lại cho nhiều thông điệp. |
| **ChaCha20-Poly1305** | AEAD: mã hóa và kiểm tra tính toàn vẹn/xác thực | Khóa **256 bit**; nonce **96 bit (12 byte)**; tag **128 bit (16 byte)** | Tag được kiểm tra khi giải mã; **nonce vẫn phải duy nhất với mỗi khóa mã hóa**. |

Trong cả hai chế độ, nonce là giá trị phân biệt một lần sử dụng khóa; nó **không bắt buộc bí mật**. Có thể gửi nonce cùng ciphertext để bên nhận giải mã. Tuy nhiên, từ “không cần bí mật” **không** đồng nghĩa “được phép lặp lại”.

Đối với AEAD, dữ liệu phụ trợ **AAD** (ví dụ phiên bản định dạng, mã bản ghi, tenant, thứ tự bản tin) được **xác thực nhưng không mã hóa**. Chúng vẫn nhìn thấy được nếu gửi rõ. Cùng một AAD phải được sử dụng dưới dạng **các byte giống hệt nhau** lúc mã hóa và giải mã.

**Chọn đúng lớp bảo vệ:** khi chỉ dùng `ChaCha20`, người nhận không có bằng chứng ciphertext được giữ nguyên. Với nội dung có thể bị tấn công, ưu tiên `ChaCha20-Poly1305` hoặc một AEAD được phê duyệt, thay vì tự ghép stream cipher với một checksum như SHA-256.

## 2. ChaCha20 hoạt động như thế nào?

ChaCha20 là một ARX cipher (*addition, rotation, XOR*). Lõi của thuật toán xử lý một trạng thái 16 từ 32 bit, thực hiện **20 vòng** biến đổi bằng các phép cộng modulo `2^32`, xoay bit và XOR. Mỗi lần xử lý block sinh **64 byte keystream** từ:

- Một **key 32 byte**;
- Một **nonce 12 byte**;
- Một **block counter 32 bit**.

Đối với một block, phép mã hóa có thể hình dung:

```text
                         key 256 bit
                             |
nonce 96 bit ----------> ChaCha20 block function <---------- block counter 32 bit
                             |
                       keystream 64 byte
                             |
plaintext block -------------XOR---------------------------> ciphertext block
```

Giải mã cũng là XOR cùng keystream:

```text
C = P XOR KS(key, nonce, counter)
P = C XOR KS(key, nonce, counter)
```

Bởi `x XOR y XOR y = x`, cùng khóa, nonce và counter phải được dùng để khôi phục bản rõ. **Bộ đếm block** tăng khi xử lý các block liên tiếp của *cùng một thông điệp*. Điều đó khác với **bộ đếm thông điệp** mà hệ thống dùng để tạo một nonce mới cho thông điệp kế tiếp.

### 2.1 Hai bộ đếm khác nhau

| Bộ đếm | Nằm ở đâu? | Nhiệm vụ |
| --- | --- | --- |
| **ChaCha20 block counter (32 bit)** | Bên trong thao tác mã hóa một thông điệp | Chọn block keystream tiếp theo của cùng cặp key/nonce; phải tránh wrap và chồng vùng keystream. |
| **Message sequence / nonce counter** | Do ứng dụng hoặc giao thức quản lý | Cấp **nonce 96 bit mới** cho mỗi lần mã hóa dùng cùng key; phải được cấp phát duy nhất, kể cả khi chạy đồng thời và khởi động lại. |

Trong biến thể IETF, mỗi cặp `(key, nonce)` có không gian block counter hữu hạn, xấp xỉ tối đa 256 GiB keystream nếu tính `2^32 × 64` byte, và AEAD còn dành block counter 0 cho khóa Poly1305. Không thiết kế một bản tin lớn vô hạn dựa vào việc counter tự wrap. Thực tế nên chia thành **bản ghi có kích thước giới hạn**, mỗi bản ghi dùng nonce mới, và áp dụng giới hạn nhỏ hơn theo giao thức/provider.

### 2.2 Vì sao tái sử dụng nonce nguy hiểm?

Nếu hai thông điệp được mã hóa bằng **cùng key, cùng nonce và vùng counter trùng nhau**, keystream tương ứng bị lặp:

```text
C1 = P1 XOR KS
C2 = P2 XOR KS

C1 XOR C2 = P1 XOR P2
```

Kẻ quan sát có thể tính XOR của hai bản rõ từ hai bản mã. Nếu biết một bản rõ, họ khôi phục được phần tương ứng của bản rõ còn lại. Nếu thông điệp có cấu trúc dự đoán được, mức rò rỉ có thể nghiêm trọng. Đây **không** phải chuyện nonce “ít ngẫu nhiên” theo cảm giác; lỗi cốt lõi là **dùng lại vùng keystream**.

Thay đổi `counter` không được coi là một cách tùy tiện để “cứu” nonce lặp. Nếu ứng dụng tự chia vùng counter thì phải bảo đảm các vùng keystream không chồng, theo dõi giới hạn block và nhất quán giao thức; trong hệ thống thông thường, quy tắc đơn giản và an toàn hơn là **mỗi thông điệp có nonce riêng**.

## 3. ChaCha20-Poly1305 bổ sung điều gì?

ChaCha20-Poly1305 theo RFC 8439 là một dạng **AEAD**. Một lần mã hóa dùng:

```text
Input:
  key       = 32 byte
  nonce     = 12 byte, không lặp với key này
  plaintext = byte[] cần giữ bí mật
  AAD       = byte[] cần xác thực nhưng không cần giấu

Output:
  ciphertext
  authentication tag = 16 byte
```

Quy trình khái quát:

1. Dùng ChaCha20 với `counter = 0` để **dẫn xuất khóa Poly1305 dùng một lần** từ cặp key/nonce. Khóa này không phải một khóa lâu dài độc lập.
2. Dùng ChaCha20 từ `counter = 1` để mã hóa plaintext thành ciphertext.
3. Tính tag Poly1305 trên **AAD, ciphertext, phần đệm và độ dài được mã hóa theo RFC 8439**. Tag 16 byte được gửi cùng ciphertext.
4. Khi giải mã, kiểm tra tag theo đúng AAD và ciphertext. Nếu sai, **từ chối bản tin**; không sử dụng plaintext chưa được xác thực.

```text
                      (key, nonce)
                            |
                +-----------+-----------+
                |                       |
        ChaCha20 counter=0      ChaCha20 counter=1,2,...
                |                       |
        one-time Poly1305 key       ciphertext
                |                       |
                +-----------+-----------+
                            |
             Poly1305 xác thực AAD + ciphertext
                            |
                       tag 16 byte
```

Từ góc nhìn Java, ta **không cần tự triển khai** phép lấy khóa Poly1305, sắp xếp phần đệm hay kiểm tra tag. `Cipher.getInstance("ChaCha20-Poly1305")` làm các bước này. Tự ghép `ChaCha20` với `Poly1305` rất dễ sai ranh giới dữ liệu, counter, độ dài và xử lý lỗi.

### 3.1 AAD mang ý nghĩa gì?

Giả sử một bản ghi có:

- `version`: phiên bản định dạng;
- `recordId`: định danh bản ghi;
- `tenantId`: phạm vi sở hữu;
- `ciphertext`: dữ liệu thực tế.

Ứng dụng có thể đưa `version`, `recordId`, `tenantId` đã được mã hóa thành byte theo chuẩn nhất quán vào **AAD**. Nếu ai đó sửa `tenantId` hoặc `recordId` trong metadata được xác thực, giải mã với AAD khác sẽ thất bại. Tuy nhiên, nếu phần metadata đó không được đưa vào AAD, AEAD **không tự biết** ứng dụng muốn bảo vệ trường nào.

AAD không bí mật; không đặt mật khẩu/khóa vào đó. Tránh ghép chuỗi bằng dấu phân cách mơ hồ (`a|bc` so với `ab|c`) hoặc phụ thuộc thứ tự trường không cố định. Chọn encoding cố định (ví dụ dạng nhị phân gồm field ID + độ dài + bytes, hoặc cấu trúc canonical đã quy định) và giữ cả hai phía thống nhất.

### 3.2 AEAD không tự chống replay

Nếu một ciphertext, nonce, AAD, tag **hợp lệ** được gửi lại nguyên vẹn, kiểm tra tag vẫn có thể thành công. AEAD bảo vệ tính xác thực của dữ liệu, không tự ghi nhớ rằng thông điệp đã từng được xử lý. Với giao thức có trạng thái, cần thêm `messageId`, sequence hoặc timestamp **được xác thực** và một cơ chế chống replay/rollback ở đầu nhận.

## 4. API Java 17+: gọi đúng thuật toán và ParameterSpec

JCA/JCE cung cấp hai tên `Cipher` có liên quan nhưng contract khác nhau:

| Tác vụ | JCA/JCE | Key | Tham số khởi tạo |
| --- | --- | --- | --- |
| Stream cipher thuần | `Cipher.getInstance("ChaCha20")` | `SecretKeySpec(rawKey32, "ChaCha20")` | `new ChaCha20ParameterSpec(nonce12, initialBlockCounter)` |
| AEAD | `Cipher.getInstance("ChaCha20-Poly1305")` | `SecretKeySpec(rawKey32, "ChaCha20")` | `new IvParameterSpec(nonce12)` |
| AAD cho AEAD | `cipher.updateAAD(aad)` | Dùng key đã `init` | **Phải gọi trước** `update`/`doFinal` của dữ liệu |
| Hoàn tất | `cipher.doFinal(input)` | Dùng key đã `init` | AEAD khi mã hóa trả `ciphertext || tag`; khi giải mã kiểm tra tag |

**Chi tiết quan trọng:** `ChaCha20ParameterSpec` là tham số của **ChaCha20 thuần**, chứa nonce 12 byte và counter 32 bit. Với **ChaCha20-Poly1305** trên provider JDK thông thường, dùng `IvParameterSpec` chứa nonce 12 byte; counter được AEAD quản lý bên trong. Đừng lấy `GCMParameterSpec` của AES-GCM để khởi tạo ChaCha20-Poly1305, cũng đừng ghép `/GCM/NoPadding` vào tên ChaCha20.

Java 17+ có các lớp `javax.crypto.Cipher`, `javax.crypto.AEADBadTagException`, `javax.crypto.spec.ChaCha20ParameterSpec`, `javax.crypto.spec.IvParameterSpec` và `javax.crypto.spec.SecretKeySpec`. Các provider phải được kiểm tra trong **JDK mà ứng dụng thực tế triển khai**; provider ngoài JDK/HSM có thể khác về cách hỗ trợ thuật toán, khóa và tham số.

Khi `Cipher.init(..., key, params)` được gọi, phía giải mã **phải biết nonce và các byte AAD chính xác**. Nonce thường được truyền bên ngoài ciphertext; bảo vệ và xác thực các metadata quan trọng bằng AAD hoặc định dạng giao thức.

## 5. Chương trình chạy được: ChaCha20 thuần không xác thực bản mã

Lưu nguyên đoạn sau thành **`ChaCha20StreamDemo.java`**. Chương trình sinh khóa/nonce cho một lượt demo, mã hóa một thông điệp và giải mã lại. Sau đó nó sửa một bit ciphertext, giải mã lần nữa và cho thấy phép giải mã **vẫn trả bytes** dù dữ liệu đã đổi.

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class ChaCha20StreamDemo {
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        byte[] rawKey = new byte[32];
        byte[] nonce = new byte[12];
        random.nextBytes(rawKey);
        random.nextBytes(nonce);

        SecretKeySpec key = new SecretKeySpec(rawKey, "ChaCha20");
        ChaCha20ParameterSpec params = new ChaCha20ParameterSpec(nonce, 1);
        byte[] plaintext = "Hello ChaCha20".getBytes(StandardCharsets.UTF_8);

        Cipher encryptor = Cipher.getInstance("ChaCha20");
        encryptor.init(Cipher.ENCRYPT_MODE, key, params);
        byte[] ciphertext = encryptor.doFinal(plaintext);

        Cipher decryptor = Cipher.getInstance("ChaCha20");
        decryptor.init(Cipher.DECRYPT_MODE, key, params);
        byte[] recovered = decryptor.doFinal(ciphertext);
        System.out.println("Giai ma: "
                + new String(recovered, StandardCharsets.UTF_8));

        // Chỉ sửa bản mã để minh họa thiếu tính toàn vẹn; không mã hóa
        // một thông điệp thứ hai bằng cùng cặp key/nonce.
        byte[] tampered = ciphertext.clone();
        tampered[0] ^= 1;

        Cipher decryptor2 = Cipher.getInstance("ChaCha20");
        decryptor2.init(Cipher.DECRYPT_MODE, key, params);
        byte[] altered = decryptor2.doFinal(tampered);
        System.out.println("Giai ma ban ma bi sua: thanh cong");
        System.out.println("Noi dung con giong: "
                + Arrays.equals(plaintext, altered));

        Arrays.fill(rawKey, (byte) 0);
    }
}
```

```bash
javac -encoding UTF-8 ChaCha20StreamDemo.java
java ChaCha20StreamDemo
```

Stdout trên JDK có provider hỗ trợ ChaCha20:

```text
Giai ma: Hello ChaCha20
Giai ma ban ma bi sua: thanh cong
Noi dung con giong: false
```

Hai thao tác giải mã cùng cặp key/nonce là hành vi **đọc lại bản mã**, không phải hai lần sinh keystream cho hai plaintext mới. Đầu ra khác sau khi sửa ciphertext chứng minh ChaCha20 đơn thuần không phát hiện sửa đổi: thư viện không ném ngoại lệ xác thực, vì vốn không có tag.

**Không dùng ví dụ này như một định dạng lưu trữ dữ liệu chống giả mạo.** Nếu yêu cầu có toàn vẹn/xác thực, chuyển sang AEAD. Việc `Arrays.fill(rawKey,...)` xóa buffer do chương trình nắm giữ, không bảo đảm mọi bản sao khóa trong `SecretKeySpec`, `Cipher` hoặc bộ nhớ JVM đã bị xóa.

## 6. Chương trình chạy được: ChaCha20-Poly1305, AAD và tag thất bại

Lưu nguyên đoạn sau thành **`ChaCha20Poly1305Demo.java`**. Đây là một ví dụ tự chứa, dùng một khóa/nonce mới trong đúng một phép mã hóa. Để tập trung vào API, nonce được sinh ngẫu nhiên **chỉ cho một thông điệp demo**. Mục 7–9 sẽ đưa ra cách cấp phát nonce bảo đảm không lặp cho dịch vụ sản xuất.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class ChaCha20Poly1305Demo {
    private static byte[] encrypt(
            SecretKeySpec key, byte[] nonce, byte[] aad, byte[] plaintext)
            throws GeneralSecurityException {
        if (nonce.length != 12) {
            throw new IllegalArgumentException("Nonce phai 12 byte");
        }
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
        cipher.updateAAD(aad); // Luon truoc thao tac tren plaintext.
        return cipher.doFinal(plaintext); // ciphertext || 16-byte tag
    }

    private static byte[] decrypt(
            SecretKeySpec key, byte[] nonce, byte[] aad,
            byte[] ciphertextAndTag) throws GeneralSecurityException {
        if (nonce.length != 12 || ciphertextAndTag.length < 16) {
            throw new IllegalArgumentException("Khung du lieu khong hop le");
        }
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag); // Kiem tra tag.
    }

    public static void main(String[] args) throws GeneralSecurityException {
        SecureRandom random = new SecureRandom();
        byte[] rawKey = new byte[32];
        byte[] nonce = new byte[12];
        random.nextBytes(rawKey);
        random.nextBytes(nonce);

        SecretKeySpec key = new SecretKeySpec(rawKey, "ChaCha20");
        byte[] plaintext = "Hello AEAD".getBytes(StandardCharsets.UTF_8);
        byte[] aad = "record=v1".getBytes(StandardCharsets.UTF_8);
        try {
            byte[] ciphertextAndTag = encrypt(key, nonce, aad, plaintext);
            byte[] recovered = decrypt(key, nonce, aad, ciphertextAndTag);
            System.out.println("Giai ma: "
                    + new String(recovered, StandardCharsets.UTF_8));
            System.out.println("Tag bytes: "
                    + (ciphertextAndTag.length - plaintext.length));

            byte[] tampered = ciphertextAndTag.clone();
            tampered[tampered.length - 1] ^= 1;
            try {
                decrypt(key, nonce, aad, tampered);
                throw new AssertionError("Da chap nhan tag sai");
            } catch (AEADBadTagException expected) {
                System.out.println("Tag bi sua: tu choi");
            }

            byte[] wrongAad = "record=v2".getBytes(StandardCharsets.UTF_8);
            try {
                decrypt(key, nonce, wrongAad, ciphertextAndTag);
                throw new AssertionError("Da chap nhan AAD sai");
            } catch (AEADBadTagException expected) {
                System.out.println("AAD bi sua: tu choi");
            }
        } finally {
            Arrays.fill(rawKey, (byte) 0);
        }
    }
}
```

```bash
javac -encoding UTF-8 ChaCha20Poly1305Demo.java
java ChaCha20Poly1305Demo
```

Stdout trên provider JDK phổ biến:

```text
Giai ma: Hello AEAD
Tag bytes: 16
Tag bi sua: tu choi
AAD bi sua: tu choi
```

**Giải thích từng kiểm tra:**

1. `Cipher.getInstance("ChaCha20-Poly1305")` chọn AEAD; `IvParameterSpec` truyền đúng nonce 12 byte. Bộ đếm block và cách dẫn xuất khóa Poly1305 được provider quản lý.
2. `updateAAD(aad)` chạy trước `doFinal`. Khi giải mã, AAD phải giống hệt byte-for-byte.
3. `encrypt` trả `ciphertext || tag` nên dài hơn plaintext **16 byte**. Ví dụ không mã hóa nonce vào mảng output; hệ thống thật phải lưu/truyền nonce cùng bản ghi.
4. Sửa một bit tag dẫn tới `AEADBadTagException`; thay AAD mà giữ ciphertext/tag cũ cũng bị từ chối.
5. `decrypt` không trả plaintext khi tag thất bại. Không dùng `catch (AEADBadTagException)` để bỏ tag rồi giải mã bằng ChaCha20 thường.

**Giới hạn demo:** sinh nonce ngẫu nhiên cho một thông điệp minh họa không phải cơ chế cấp phát nonces dài hạn; nếu khóa được tái sử dụng cho nhiều bản tin, toàn hệ thống phải thực thi chính sách nonce **không trùng**. Không lưu raw key trong source code, log, cơ sở dữ liệu plaintext hoặc response của dịch vụ.

## 7. Quy tắc quan trọng nhất: nonce phải duy nhất theo khóa

Với IETF ChaCha20-Poly1305, mỗi lần **mã hóa** bằng một khóa `K` phải dùng nonce `N` chưa từng được dùng để mã hóa trước đó cùng `K`. Đó là điều kiện về **tính duy nhất**, không phải yêu cầu nonce phải bí mật hoặc không thể đoán.

```text
(key K, nonce N0) -> message 0    HOP LE
(key K, nonce N1) -> message 1    HOP LE  (N1 != N0)
(key K, nonce N0) -> message 2    SAI!   (N0 da dung voi K)
(key K2, nonce N0) -> message 3   Co the hop le, neu K2 thuc su la key khac
```

Dùng lại `(K,N)` làm ChaCha20 lặp keystream và làm Poly1305 lặp khóa xác thực dùng một lần. Hậu quả không chỉ là để lộ quan hệ XOR giữa plaintext; các bảo đảm về xác thực cũng bị tổn hại. **Tuyệt đối không “khắc phục” lỗi trùng nonce bằng cách tăng counter nội bộ của Cipher hoặc bỏ tag.** Nếu hệ thống phát hiện nghi ngờ trùng nonce, cần dừng ghi với key đó, điều tra phạm vi và xử lý rủi ro/đổi khóa theo chính sách.

### 7.1 Nonce 96 bit: có thể random hay nên dùng counter?

Có hai họ chiến lược thường được nhắc tới:

| Cách cấp nonce | Ưu điểm | Giới hạn/rủi ro |
| --- | --- | --- |
| **12 byte từ `SecureRandom`** | Dễ dùng trong demo/lưu lượng nhỏ, ít trạng thái. | Ngẫu nhiên **không bảo đảm duy nhất tuyệt đối**; xác suất va chạm tăng khi số message cùng key tăng; khó chứng minh không trùng trong nhiều writer. |
| **Nonce xác định và duy nhất**: prefix phân miền + bộ đếm liên tục | Có thể bảo đảm không lặp nếu cấp phát phối hợp, trạng thái bền vững và không wrap. | Cần quản lý phân miền, restart, concurrency, cấp phát số thứ tự và key rotation chính xác. |

Với `n` nonce được chọn đều ngẫu nhiên trong không gian `2^96`, xác suất có va chạm gần đúng khi `n` nhỏ so với căn bậc hai của không gian là:

```text
P(collision) ~ n(n - 1) / (2 * 2^96)
```

Công thức chỉ dùng để **đánh giá rủi ro**, không biến random nonce thành một cơ chế chứng minh duy nhất. RFC 8439 nhấn mạnh việc mỗi lần gọi với cùng key phải có nonce duy nhất; đối với thiết kế dài hạn/multiwriter, ưu tiên **counter và phân hoạch không gian nonce** theo chính sách giao thức. Ví dụ random nonce ở mục 6 chỉ tập trung minh họa Java API.

### 7.2 Mẫu phân hoạch nonce theo writer + sequence

Một cách mô tả cấu trúc 96 bit là:

```text
        12 bytes / 96 bits
+----------------+--------------------------------+
| writerId/prefix| monotonically increasing seq   |
| 4 bytes        | 8 bytes                        |
+----------------+--------------------------------+
         hai phần phải được phân bổ nhất quán theo scope một key
```

- `writerId`/prefix **phải duy nhất giữa các writer đang dùng cùng key**, được cấp một cách có kiểm soát; không giả định prefix 4 byte chọn random chắc chắn không trùng.
- `seq` phải tăng **không lặp lại** trong cùng prefix và key. Hai thread không được cùng nhận một số. Không wrap về 0 khi đạt giới hạn.
- Sau crash/restart, writer phải phục hồi từ trạng thái **bền vững** chưa từng cấp lại; chỉ dùng `AtomicLong` trong RAM là **không đủ**.
- Một nonce đã **cấp phát và dùng** phải được coi là tiêu thụ, kể cả thao tác ghi dữ liệu thất bại hoặc response gửi lại bị mất. Retry một phép mã hóa mới phải lấy nonce **mới**, hoặc gửi lại đúng ciphertext đã lưu mà không mã hóa lại.
- Nếu có nhiều tiến trình, container, vùng địa lý hoặc shard dùng cùng key, phải có cơ chế cấp miền/sequence duy nhất toàn hệ thống. Một process tự đếm từ 0 là không đủ.

Đây là **một ví dụ bố trí bit**, không phải định dạng bắt buộc của mọi giao thức. Những hệ thống như TLS có cách tạo nonce riêng gắn với số thứ tự và bí mật phiên; **không** tự thay thế quy tắc của giao thức bằng mẫu tự chế này.

## 8. Chương trình chạy được: minh họa bộ cấp nonce dạng counter

Ví dụ này chỉ minh họa cách ghép prefix 4 byte với sequence 8 byte và cấp số atomically trong **một JVM**. Nó không có lưu trữ bền vững hay cơ chế phân quyền prefix, vì vậy **không phải allocator production**. Prefix `01 02 03 04` được cố định để stdout dễ kiểm chứng; tuyệt đối không sao chép prefix và khởi tạo counter bằng 0 vào nhiều worker cùng key trong thực tế.

Lưu thành **`NonceCounterDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.util.HexFormat;
import java.util.concurrent.atomic.AtomicLong;

public final class NonceCounterDemo {
    private final byte[] prefix;
    private final AtomicLong nextSequence;

    NonceCounterDemo(byte[] prefix, long initialSequence) {
        if (prefix == null || prefix.length != 4 || initialSequence < 0) {
            throw new IllegalArgumentException(
                    "Prefix hoac sequence khong hop le");
        }
        this.prefix = prefix.clone();
        this.nextSequence = new AtomicLong(initialSequence);
    }

    byte[] nextNonce() {
        long current;
        do {
            current = nextSequence.get();
            if (current == Long.MAX_VALUE) {
                throw new IllegalStateException("Het vung nonce");
            }
        } while (!nextSequence.compareAndSet(current, current + 1));

        return ByteBuffer.allocate(12)
                .put(prefix)
                .putLong(current) // Quy uoc big-endian cho sequence trong demo.
                .array();
    }

    public static void main(String[] args) {
        NonceCounterDemo allocator =
                new NonceCounterDemo(new byte[]{1, 2, 3, 4}, 0);
        System.out.println(HexFormat.of().formatHex(allocator.nextNonce()));
        System.out.println(HexFormat.of().formatHex(allocator.nextNonce()));
    }
}
```

```bash
javac -encoding UTF-8 NonceCounterDemo.java
java NonceCounterDemo
```

Stdout:

```text
010203040000000000000000
010203040000000000000001
```

Điều cần hiểu trong ví dụ:

- `compareAndSet` giúp các thread chia sẻ **một** `AtomicLong` không nhận cùng số do race trong JVM.
- Dùng `ByteBuffer.putLong` theo byte order mặc định big-endian cho **định dạng message sequence**, không phải đang mô tả endian của từ bên trong ChaCha20. ChaCha20 nhận nonce dưới dạng **12 byte**; tính duy nhất là vấn đề chính.
- Để đơn giản, ví dụ chỉ sử dụng miền sequence không âm `0..Long.MAX_VALUE-1` và từ chối khi tới giới hạn, tránh lỗi wrap của `long`. Không bắt buộc dùng hết không gian 64 bit.
- Mỗi lần chạy lại `new NonceCounterDemo(..., 0)` sẽ trả **nonce cũ**. Nếu dùng lại key, đây là lỗi nghiêm trọng. Production phải có trạng thái persistent/atomic hoặc cơ chế phân biệt khóa/miền đã được thiết kế.

**Trường hợp nhiều writer:** phân bổ prefix không trùng cho từng writer cùng key; hoặc cấp dải sequence tập trung; hoặc tách khóa theo sender qua KDF thích hợp rồi quản lý nonce trong từng miền key. Mỗi phương án phải có cách chứng minh không trùng khi scale, failover, rollback và redeploy.

## 9. Kiến trúc quản lý nonce trong ứng dụng thực tế

Đây là một thiết kế tham chiếu có các thành phần bắt buộc; **không** phải đoạn mã triển khai đầy đủ cho cơ sở dữ liệu/phân tán.

```text
          Kho khóa/KMS                          Durable allocator
              |                                (per keyId + writer)
      keyId -> secret key                            |
              |                            cấp nonce không trùng
              +---------------+---------------------+
                              |
                        Encrypt service
                              |
          header(version, keyId, nonce, flags) + AAD
                              |
                  ChaCha20-Poly1305 encrypt
                              |
              ciphertext || authentication tag
                              |
          Lưu/truyền một record theo format đã version hóa
```

### 9.1 Ràng buộc khóa và nonce

**Khóa:** sinh ngẫu nhiên 32 byte bằng bộ sinh số ngẫu nhiên mật mã phù hợp, hoặc lấy từ KMS/keystore qua cơ chế tạo khóa đã phê duyệt. Không dùng `new Random()`, timestamp, username hay `password.getBytes()` như một khóa ChaCha20 trực tiếp. Nếu nguồn là password/shared secret cần dùng KDF đúng mục tiêu và quản lý salt/tham số theo thiết kế; không tự lắp hash để tạo khóa. Tránh dùng chung một khóa cho những mục đích khác nhau nếu giao thức không chứng minh tương thích.

**Key ID:** bản ghi cần chỉ ra khóa nào dùng để giải mã; khi xoay khóa, bản ghi cũ vẫn cần khả năng tìm khóa cũ cho đến khi được chuyển đổi hoặc hết hạn. Key ID có thể công khai, nhưng phải nằm trong miền tin cậy; nên xác thực metadata nhạy cảm bằng AAD.

**Nonce uniqueness domain:** khóa và nonce phải được quản lý như một cặp. Bộ đếm có thể bắt đầu lại **với khóa mới thực sự độc lập**, nhưng không được reset rồi dùng lại key cũ. KMS/rotation và allocator cần thống nhất lifecycle `keyId` để tránh cấp phát lại vùng nonce.

### 9.2 Bản ghi có phiên bản

Một format có thể là:

```text
version (1 byte)
keyIdLength + keyId
nonce (12 bytes)
ciphertextLength + ciphertext
tag (16 bytes)

AAD = encoding chinh xac cua version + keyId + recordId/tenant/context
```

Các trường độ dài và encoding phải được định nghĩa **không mơ hồ**, có giới hạn chặn payload bất thường; đoạn minh họa trên chỉ là phác thảo schema. Java `Cipher.doFinal` với ChaCha20-Poly1305 thường trả `ciphertext || tag` trong **một byte array**, do đó khi serialize cần biết nonce 12 byte ở đâu và tag 16 byte ở đâu. Không coi tag hay nonce là secret, và không được để phía nhận tự đoán key/nonce/version.

Nếu `recordId` hay `tenant` là thuộc tính kiểm soát quyền truy cập, hãy đưa chúng vào AAD và đồng thời **kiểm tra authorization** ở lớp ứng dụng; AEAD không thay thế kiểm soát quyền. Không dùng AAD để giấu dữ liệu nhạy cảm vì AAD vẫn nhìn thấy được.

### 9.3 Cấp phát bền vững trước khi mã hóa

Một hệ thống với khóa sống lâu có thể áp dụng chiến lược:

1. Xác định duy nhất `(keyId, writerId)` và miền sequence dành riêng cho nó.
2. **Reserve** sequence hoặc một khoảng sequence trong một kho giao dịch/allocator đáng tin, theo kiểu atomic, **commit dấu mốc đã cấp trước khi sử dụng**.
3. Tạo nonce từ prefix đã phân bổ + số sequence vừa cấp, chưa bao giờ lặp lại.
4. Mã hóa một record bằng AEAD rồi lưu `(keyId, nonce, AAD schema, ciphertext, tag)` theo định dạng ổn định.
5. Nếu process chết sau cấp nonce nhưng trước khi ghi record, **bỏ qua** nonce đã cấp; không lấy lại chỉ vì không thấy ciphertext trong DB.
6. Nếu response bị mất sau khi record đã lưu, **trả lại record ciphertext cũ** theo idempotency key. Nếu cần mã hóa lại dữ liệu, reserve **nonce mới**.
7. Không cho sequence wrap; cảnh báo khi tới ngưỡng định trước và xoay key theo chính sách.

Không thể chứng minh không trùng chỉ bằng `synchronized`, `AtomicLong`, khóa mutex trong một pod hay Redis key không được bảo toàn qua failover. Hệ thống cần xác minh tính bền vững và các trường hợp network partition, rollback DB, restore backup, autoscaling và di chuyển workload.

### 9.4 Các lỗi nonce phổ biến

| Lỗi | Vì sao sai | Cách phòng tránh |
| --- | --- | --- |
| Mọi lần encrypt dùng `new byte[12]` (toàn số 0) với khóa sống lâu | Lặp `(key,nonce)` từ lần thứ hai. | Chỉ nonce duy nhất cho mỗi lần encrypt; zero nonce chỉ có thể phù hợp nếu key thật sự mới mỗi bản tin theo giao thức đã thiết kế. |
| Dùng `System.currentTimeMillis()` hoặc `Random` | Dễ trùng/đoán được và không có bảo đảm duy nhất; `Random` không phải CSPRNG. | Counter phối hợp bền vững, hoặc chính sách random có chứng minh rủi ro được phê duyệt. |
| Mỗi pod tự đếm từ 0 với cùng key/prefix | Các pod tạo cùng nonce. | Cấp prefix/miền độc quyền hoặc bộ cấp sequence tập trung. |
| Restart từ counter 0 | Tạo lại nonce đã dùng trước crash. | Lưu high-water mark trước khi dùng, không cấp lại sau rollback. |
| Retry mã hóa bản ghi với nonce cũ nhưng payload/AAD thay đổi | Cặp `(key,nonce)` bị dùng lại cho một phép mã hóa mới. | Retry ciphertext đã lưu hoặc xin nonce mới cho lần encrypt mới. |
| Coi nonce là secret; không truyền nonce | Bên nhận không biết tham số giải mã, dễ phải suy đoán. | Lưu/truyền nonce rõ ràng cùng bản ghi, đồng thời kiểm soát key. |
| Cho phép counter wrap hoặc xử lý một message vô hạn | Lặp block keystream/đụng giới hạn thuật toán. | Giới hạn kích thước record, kiểm tra overflow, xoay key/nonce. |
| Cố “sửa” AEAD tag sai bằng cách giải mã stream thường | Bỏ qua xác thực, có nguy cơ đưa dữ liệu giả vào xử lý nghiệp vụ. | Từ chối toàn bộ record; điều tra key/nonce/AAD/tag. |

## 10. Xử lý lỗi Java và những điều cần tránh

| Lỗi hoặc tình huống | Thường xảy ra khi | Cách xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` | `Cipher.getInstance("ChaCha20")` hoặc `getInstance("ChaCha20-Poly1305")` không có implementation | Kiểm tra JDK/provider, cấu hình và thuật toán; phát hiện sớm lúc startup. |
| `InvalidKeyException` | `Cipher.init` nhận khóa không đúng thuật toán/kích thước hoặc bị provider từ chối | Kiểm tra key 256 bit và nguồn cấp khóa; không thử khóa yếu/tự chuyển thuật toán. |
| `InvalidAlgorithmParameterException` | Nonce sai kích thước hoặc tham số không đúng với engine/provider | Đối chiếu `ChaCha20ParameterSpec` với stream cipher, `IvParameterSpec` với AEAD; nonce 12 byte. |
| `IllegalArgumentException` | Constructor `ChaCha20ParameterSpec` nhận nonce dài khác 12 byte hoặc validation của ứng dụng | Sửa đầu vào, không coi là xác thực bản mã thất bại. |
| `IllegalStateException` | `updateAAD` sai thứ tự/trạng thái; tái sử dụng cipher hoặc khởi tạo lại với nonce không an toàn theo kiểm tra provider | Tạo phép toán mới, cấp nonce mới; không dựa vào việc provider sẽ phát hiện mọi lần reuse ở các tiến trình. |
| `AEADBadTagException` | `doFinal` khi giải mã thấy ciphertext/tag/AAD/key/nonce không khớp | **Từ chối thông điệp**, không trả plaintext. Xử lý response tránh tạo oracle chi tiết. |

`AEADBadTagException` không có nghĩa chắc chắn “sai mật khẩu” hay “nonce bị trùng”: cùng ngoại lệ có thể xuất hiện khi ciphertext bị sửa, key sai, nonce sai, tag sai hoặc AAD không khớp. Đầu nhận nên trả thông báo xác thực thất bại thống nhất và ghi chẩn đoán giới hạn trong log bảo vệ; không log key, plaintext hay secret từ KMS.

**Không tái sử dụng cùng `Cipher` để mã hóa lần nữa bằng key/nonce cũ.** Một số provider từ chối tái sử dụng trên cùng instance, nhưng bộ nhớ chống trùng của một `Cipher` không bảo vệ các instance/process khác. Cần bộ cấp nonce ở lớp thiết kế.

### 10.1 Kiểm tra cấu hình tại startup

Đoạn dưới đây chỉ minh họa khả năng lookup (không phải một chương trình độc lập):

```java
// Đoạn mã ở trong phương thức đã khai báo throws GeneralSecurityException.
Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
System.out.println(cipher.getProvider().getName());
```

Nếu provider cụ thể được yêu cầu (ví dụ policy/FIPS), dùng overload thích hợp và không tự động fallback khi provider không sẵn có. Việc một JDK có ChaCha20-Poly1305 **không đồng nghĩa** provider hay mô-đun đó được chứng nhận theo chính sách của hệ thống; kiểm tra yêu cầu tuân thủ riêng.

## 11. ChaCha20-Poly1305, AES-GCM và XChaCha20-Poly1305

| Tiêu chí | ChaCha20-Poly1305 (IETF) | AES-GCM | XChaCha20-Poly1305 |
| --- | --- | --- | --- |
| Loại | AEAD | AEAD | AEAD dùng biến thể mở rộng nonce của ChaCha |
| Key | 256 bit | 128/192/256 bit tùy triển khai và policy | Thường 256 bit |
| Nonce | **96 bit** trong RFC 8439 | **96 bit** phổ biến/được khuyến nghị | **192 bit** |
| Tag | 128 bit | Thường 128 bit (có cấu hình khác được phép theo policy) | 128 bit |
| Java JCA/JCE | `ChaCha20-Poly1305` trên JDK hỗ trợ | `AES/GCM/NoPadding` | **Không** giả định là tên thuật toán JCA chuẩn có sẵn; cần thư viện/provider tương ứng |
| Cảnh báo chính | Không trùng nonce với key | Không trùng IV/nonce với key | Khác định dạng/nonce; không tự thay một tên bằng tên khác |

Không kết luận thuật toán nào **luôn** nhanh hơn; hiệu năng tùy CPU, tăng tốc phần cứng, provider và workload. AES-GCM và ChaCha20-Poly1305 đều là lựa chọn AEAD mạnh nếu sử dụng đúng chính sách, khóa, nonce, AAD và quản lý lỗi. Chọn dựa trên giao thức tương tác, yêu cầu compliance, thư viện sẵn có và benchmark của môi trường thật.

**XChaCha20-Poly1305 không tương thích trực tiếp với IETF ChaCha20-Poly1305**: nonce 24 byte không thể truyền vào `IvParameterSpec` 12 byte rồi gọi cùng tên để tự có XChaCha. Nếu dùng XChaCha, cần thư viện/định dạng tương ứng và quy tắc quản lý nonce của nó, không tự chế bước dẫn xuất.

## 12. Tình huống tự kiểm tra

**Tình huống A — Hai thread cùng key, mỗi thread `AtomicLong(0)`:** Có an toàn không?  
**Trả lời:** Không. Mỗi thread có counter riêng nên cùng prefix có thể tạo cùng nonce. Cần một allocator chia sẻ có cấp phát nguyên tử hoặc các prefix/miền được phân bổ duy nhất.

**Tình huống B — Tăng block counter lên 2 cho message thứ hai nhưng giữ key/nonce:** Có giải quyết được nonce reuse không?  
**Trả lời:** Không phải chính sách an toàn cho message mới. Nếu vùng keystream trùng, hai plaintext rò rỉ XOR; cần một thiết kế quản lý range và giới hạn rất chặt chẽ. Mặc định bắt buộc **nonce mới** cho mỗi lần mã hóa độc lập.

**Tình huống C — Thay AAD `tenant=alpha` thành `tenant=beta`, giữ nonce/ciphertext/tag:** Kết quả?  
**Trả lời:** AEAD từ chối do tag không khớp (nếu chuỗi byte AAD thay đổi). Điều đó không thay thế kiểm soát phân quyền tenant ở lớp ứng dụng.

**Tình huống D — Đồng bộ DB từ backup cũ khiến allocator cấp lại sequence đã dùng:** Có thể tiếp tục dùng cùng key?  
**Trả lời:** Không nên. Phải bảo đảm khôi phục trạng thái cấp nonce không bị lùi, hoặc thay key/miền trước khi mã hóa tiếp; xác định phạm vi các nonce đã có thể trùng và xử lý sự cố.

**Tình huống E — Tag hợp lệ nhưng message cũ bị gửi lại:** AEAD có tự chặn?  
**Trả lời:** Không. Cần deduplication, sequence/timestamp được xác thực và trạng thái chống replay theo giao thức.

**Tình huống F — Một file lớn được mã hóa bằng ChaCha20 với counter 32 bit và xử lý không giới hạn:** Vấn đề?  
**Trả lời:** Block counter hữu hạn; khi wrap có nguy cơ lặp keystream. Chia record hữu hạn, dùng nonce mới cho record mới, giới hạn kích thước theo giao thức/provider.

**Tình huống G — Người lập trình gọi `cipher.update(plaintext)` rồi `cipher.updateAAD(header)`:** Có đúng?  
**Trả lời:** Không. Với AEAD, AAD phải được đưa vào trước phần plaintext/ciphertext; provider có thể ném `IllegalStateException`. Hãy xác thực toàn bộ header trước khi xử lý payload.

## 13. Checklist khi thiết kế và review

- **Mục tiêu bảo mật:** cần tính bí mật **và** xác thực? Dùng AEAD thay vì ChaCha20 thuần.
- **Đúng API:** `ChaCha20ParameterSpec(nonce12, counter)` cho `ChaCha20`; `IvParameterSpec(nonce12)` cho `ChaCha20-Poly1305`.
- **Khóa:** 32 byte đủ ngẫu nhiên, quản lý trong KMS/keystore hoặc cơ chế an toàn tương ứng, không hardcode.
- **Nonce:** không lặp cho cùng key; định rõ scope, cấp phát duy nhất trong multiwriter, trạng thái bền vững qua restart/crash, không wrap.
- **AAD:** cố định encoding, có version/định danh/context liên quan nếu cần; cung cấp trước phần dữ liệu và kiểm tra lại đúng byte.
- **Record:** lưu/truyền version, keyId, nonce, ciphertext và tag theo định dạng không mơ hồ; có giới hạn độ dài.
- **Giải mã:** từ chối nếu tag sai; không trả plaintext chưa được xác thực, không log secret hoặc fallback sang stream cipher thuần.
- **Replay:** nếu nghiệp vụ cần, kiểm tra thứ tự/ID/timestamp trên dữ liệu được xác thực và lưu trạng thái ở đầu nhận.
- **Lifecycle:** phối hợp key rotation với allocator, backup/restore và xử lý sự cố trùng nonce; kiểm tra tải trọng/trần counter.
- **Kiểm thử:** test round-trip, sửa ciphertext, sửa tag, sửa AAD, sai key/nonce, record thiếu trường, restart allocator và hai writer cấp đồng thời.

## Tài liệu chính thức

1. [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols](https://www.rfc-editor.org/rfc/rfc8439.html): cấu trúc ChaCha20, nonce 96 bit, block counter, dẫn xuất khóa Poly1305, AEAD, cảnh báo reuse.
2. [Java SE 21 — `ChaCha20ParameterSpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html): nonce 12 byte và initial counter 32 bit.
3. [Java SE 21 — `Cipher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html): `getInstance`, `init`, `updateAAD`, `doFinal`, ngoại lệ và AEAD.
4. [Java SE 21 — `AEADBadTagException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/AEADBadTagException.html): lỗi xác thực tag khi giải mã.
5. [Java SE 21 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): tên chuẩn `ChaCha20` và `ChaCha20-Poly1305` trong JCA/JCE.

**Kết luận kỹ thuật:** ChaCha20 biến khóa và nonce thành keystream để mã hóa; ChaCha20-Poly1305 thêm tag xác thực và AAD. Sự an toàn của cả hai phụ thuộc vào **không tái sử dụng nonce với cùng khóa**. Trong Java, dùng đúng `Cipher`/`ParameterSpec`, còn ở cấp hệ thống phải quản lý nonce bền vững, duy nhất giữa các writer và sống sót qua crash/restart.