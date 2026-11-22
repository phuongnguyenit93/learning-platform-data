# Mã hóa file nhạy cảm trong Spring Batch

## 1. Bối cảnh và mục tiêu

Một Spring Batch job thường nhận và sinh ra các tệp lớn: CSV giao dịch, dữ liệu lương, thông tin khách hàng, báo cáo đối soát, bản trích xuất cơ sở dữ liệu hoặc hồ sơ có định danh cá nhân. Các tệp này có thể đi qua nhiều nơi: SFTP/object storage, thư mục tạm của worker, RAM, log, vùng backup và thư mục output. Một lần rò rỉ ở bất kỳ điểm nào đều có thể khiến toàn bộ dữ liệu nhạy cảm bị lộ, ngay cả khi application database đã được bảo vệ.

**Mã hóa file nhạy cảm** là yêu cầu bảo mật xuyên suốt vòng đời batch, không chỉ là gọi một hàm mã hóa trước khi upload. Để thiết kế đúng, cần giải quyết đồng thời:

1. **Tính bí mật (confidentiality):** người không có khóa không đọc được nội dung file.
2. **Tính toàn vẹn và xác thực (integrity/authenticity):** phát hiện file bị sửa, ghép, cắt hoặc tráo nội dung.
3. **Quản lý khóa:** lưu, phân quyền, xoay và thu hồi khóa mà không hard-code trong source.
4. **Luồng xử lý Spring Batch:** reader/processor/writer cần đọc được nội dung được ủy quyền mà không để lại plaintext ngoài ý muốn.
5. **Transaction và restart:** job lỗi, retry hoặc restart không làm lộ file chưa hoàn chỉnh và không xuất bản sai kết quả.
6. **Hiệu năng:** hỗ trợ file lớn mà không giải mã toàn bộ vào Java heap một cách nguy hiểm.
7. **Quan sát và kiểm thử:** phát hiện sai khóa, tampering, lỗi KMS, cleanup thất bại và bản ghi nhạy cảm trong log.

Bài thuộc *Spring Batch Core Processing → Security*. Những ví dụ cụ thể dùng **Java 17, Spring Boot 3.x và Spring Batch 5.2.x**; phần mật mã dùng Java Cryptography Architecture (JCA). Code minh họa thuật toán và tích hợp ở quy mô file nhỏ, **không thay thế một định dạng mã hóa tệp được tiêu chuẩn hóa hoặc thư viện mã hóa đã được đánh giá bảo mật** cho dữ liệu production lớn.

---

## 2. Xác định dữ liệu nào cần bảo vệ

### 2.1. Các dạng dữ liệu thường gặp

| Dữ liệu | Nguy cơ khi lộ | Lưu ý trong batch |
|---|---|---|
| CSV khách hàng | Tên, số liên hệ, địa chỉ, định danh | Không ghi dòng dữ liệu vào log lỗi |
| File bảng lương | Thu nhập, tài khoản nhận lương | Quyền truy cập, audit và retention nghiêm ngặt |
| File thanh toán | Số tài khoản, giao dịch, dữ liệu tài chính | Tránh retry/publish trùng; kiểm tra integrity |
| Trích xuất dữ liệu sản xuất | Có thể chứa thông tin nội bộ nhiều hệ thống | Bảo vệ cả file gốc, file tạm và backup |
| File đối soát | Mã giao dịch, dữ liệu đối tác | Xác định quyền chia sẻ và khóa theo đối tác |
| File lỗi/quarantine | Có thể lưu nguyên record nhạy cảm | Không coi file lỗi là dữ liệu không nhạy cảm |
| Metadata/manifest | Tên file, customer ID, số record, thời điểm | Một phần metadata cũng có thể nhạy cảm |

Mã hóa file không tự làm dữ liệu trở nên “vô danh”; người có quyền giải mã vẫn có thể xem được nội dung gốc. Nếu quy định yêu cầu che trường, tokenization, pseudonymization hoặc xóa dữ liệu, phải thiết kế thêm những cơ chế đó.

### 2.2. Data flow cần được đánh giá

Ví dụ job chuyển dữ liệu khách hàng từ một đối tác sang hệ thống nội bộ:

```text
Đối tác
   │
   │ file.enc qua HTTPS/SFTP/TLS
   ▼
Vùng nhận file (encrypted object)
   │
   ▼
Spring Batch worker
   │    ├── lấy key/unwrap DEK từ KMS hoặc vault
   │    ├── xác thực + giải mã dữ liệu
   │    ├── ItemReader → ItemProcessor → ItemWriter
   │    └── tạo output được mã hóa
   ▼
Vùng output mã hóa
   │
   ├── publish theo chính sách atomic/idempotent
   ├── giao cho bên nhận có quyền
   └── retention/cleanup
```

Các nơi dễ bị bỏ quên: thư mục `/tmp`, file spool khi unzip, heap dump, crash dump, console log, dead-letter file, thư mục cache của FTP client, object-storage multipart upload chưa hoàn tất và bản sao do hệ thống backup tạo ra.

### 2.3. Mã hóa ở những lớp nào?

| Lớp bảo vệ | Ví dụ | Bảo vệ được gì? | Chưa giải quyết gì? |
|---|---|---|---|
| Trong quá trình truyền | HTTPS/TLS, SFTP, mTLS | Dữ liệu trên đường truyền | File nằm trên ổ đĩa của nguồn/đích |
| Mã hóa ổ đĩa/storage | LUKS, EBS encryption, SSE-KMS | Thiết bị lưu trữ, snapshot, một số rủi ro mất ổ cứng | Process/identity có quyền đọc object vẫn nhận plaintext |
| Mã hóa file/application-level | AES-GCM, OpenPGP phù hợp hợp đồng | File vẫn có ciphertext khi copy sang nơi khác | Khóa, plaintext trong RAM và lúc xử lý |
| Mã hóa trường dữ liệu | Field-level encryption/tokenization | Giảm lộ một số trường ngay cả trong file xử lý | Phức tạp với tìm kiếm, mapping, tổng hợp |
| Quyền truy cập, audit | IAM, ACL, short-lived credential | Hạn chế ai có thể lấy ciphertext/khóa | Không thay thế mã hóa và integrity |

**Bảo vệ nhiều lớp:** file nhạy cảm có thể được mã hóa ở tầng ứng dụng **và** lưu trong bucket có SSE-KMS, truy cập qua TLS, giới hạn IAM. Một cơ chế không tự thay thế các cơ chế còn lại.

---

## 3. Mô hình đe dọa cho batch file

Trước khi chọn thuật toán, hãy xác định ai có thể đọc hay sửa file, nơi khóa được cung cấp và đối tượng nào đáng tin cậy.

| Tình huống đe dọa | Tác động | Kiểm soát cần cân nhắc |
|---|---|---|
| Người có quyền đọc bucket nhưng không được đọc dữ liệu | Lộ nội dung nếu file plaintext | Mã hóa ở mức file với khóa tách quyền |
| Kẻ tấn công thay ciphertext | Dữ liệu biến đổi hoặc job import sai | Authenticated encryption + xác minh tag |
| File bị cắt cụt khi upload | Batch đọc thiếu record | Xác thực toàn file, manifest/length/final marker |
| Thay file của ngày A bằng ngày B | Nhập sai kỳ nghiệp vụ | Bind identity/ngày/tên dataset vào authenticated metadata (AAD) |
| Worker ghi plaintext vào `/tmp` | Lộ qua container, snapshot, diagnostic | Tránh plaintext disk hoặc dùng staging bảo vệ và cleanup |
| Mất khóa sau khi đã mã hóa | Không thể khôi phục file | KMS, backup/retention khóa và quy trình rotation |
| Kẻ tấn công lấy được khóa và ciphertext | Đọc được nội dung | Phân quyền KMS, key separation, audit, giới hạn thời gian |
| Reuse nonce với cùng AES-GCM key | Phá vỡ bảo mật mật mã | Nonce duy nhất theo key, quy trình sinh nonce an toàn |
| Retry/restart xuất bản file trùng | Người nhận xử lý hai lần | Business key, conditional publish, manifest và idempotency |
| Log/heap dump chứa plaintext | Rò rỉ qua kênh phụ | Redaction, quyền truy cập dump/log, giới hạn retention |
| Bị phát lại một file hợp lệ đã cũ | Import lại giao dịch cũ | Freshness/replay protection gắn với business identity |

Đối tượng có quyền gọi KMS decrypt và quyền đọc ciphertext có thể giải mã; vì vậy **quyền truy cập key là một phần của mô hình dữ liệu**, không phải chi tiết cấu hình nhỏ.

---

## 4. Chọn thuật toán: authenticated encryption

### 4.1. Vì sao không chỉ dùng mã hóa bí mật?

Một số chế độ mã hóa chỉ che nội dung nhưng không tự phát hiện ciphertext bị thay đổi. Nếu batch giải mã một file đã bị chỉnh sửa rồi ghi dữ liệu vào hệ thống đích, tác động có thể nghiêm trọng.

**Authenticated encryption with associated data (AEAD)** cung cấp cả bí mật và xác thực. Lựa chọn thường gặp là **AES-GCM**; trong Java JCA sử dụng:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
```

Các tham số cần hiểu:

- **AES key:** 128-bit hoặc 256-bit được sinh bằng nguồn ngẫu nhiên mật mã phù hợp; không tạo từ mật khẩu thông thường bằng cách lấy byte chuỗi.
- **Nonce/IV:** với AES-GCM thường chọn 96-bit (12 byte); **không được tái sử dụng cùng nonce với cùng key**.
- **Authentication tag:** thường dùng 128-bit (16 byte).
- **AAD:** metadata được xác thực nhưng không mã hóa, ví dụ phiên bản định dạng, file ID, dataset/tenant/businessDate.
- **Ciphertext:** nội dung đã mã hóa; khi verify tag thất bại phải **fail closed**, không phát hành plaintext như dữ liệu hợp lệ.

```text
Plaintext + AES key + nonce + AAD
                  │
                  ▼
              AES-GCM
                  │
                  ├── ciphertext
                  └── authentication tag

Ciphertext + tag + key + nonce + AAD
                  │
                  ▼
       Verify tag trước khi tin output
                  │
          ├── đúng → plaintext hợp lệ
          └── sai  → từ chối toàn bộ file/record
```

Lưu ý: **AEAD không ngăn mọi replay.** Một ciphertext hợp lệ của hôm qua vẫn có tag đúng. Cần bind dataset ID/businessDate và duy trì registry những kỳ đã xử lý để ngăn nhập lại file hợp lệ nhưng sai kỳ.

### 4.2. CBC, ECB và “Base64 encryption”

Không nên dùng `AES/ECB` để mã hóa dữ liệu file: chế độ này để lộ mẫu lặp và không có integrity. AES-CBC chỉ mã hóa, muốn an toàn cần cơ chế MAC đúng chuẩn và thiết kế phức tạp hơn; với bài toán mới, ưu tiên AEAD hoặc định dạng file mã hóa đã được chuẩn hóa. `Base64` chỉ **mã hóa biểu diễn**, không bảo mật: bất kỳ ai cũng giải mã Base64 được nếu có chuỗi.

Không tự thiết kế kết hợp “AES rồi hash thường” để thay thế authentication tag. MAC, AAD và verification phải được implement đúng với thiết kế mật mã đã được đánh giá.

### 4.3. Tại sao nonce uniqueness quan trọng?

Với GCM, việc lặp nonce dưới **cùng key** có thể phá vỡ bí mật và integrity nghiêm trọng. Với các file riêng biệt có key dùng chung, nonce 12 byte từ `SecureRandom` là lựa chọn thông dụng khi số lượng file và chính sách key lifecycle được kiểm soát, nhưng vẫn phải đánh giá giới hạn xác suất va chạm và tổng khối lượng dùng cùng key.

Một chính sách production đơn giản hơn để giảm phạm vi ảnh hưởng là **mỗi file một data encryption key (DEK)**, được KMS/vault cung cấp hoặc tạo và wrap đúng cách. Khi đó nonce uniqueness được quản lý trong phạm vi file/key. Nếu một file được phân thành các record/chunk mã hóa độc lập, mỗi record vẫn phải dùng nonce duy nhất với key của file đó.

**Không bao giờ dùng timestamp mili-giây hoặc counter không bền vững làm nonce một cách tùy tiện**: nhiều node và restart có thể tạo cùng giá trị. Với counter nonce, cần giao thức đảm bảo duy nhất ngay cả khi crash/retry và chuyển worker.

---

## 5. Ví dụ Java 17: AES-GCM cho file nhỏ có giới hạn kích thước

Ví dụ dưới đây dạy cách dùng JCA một cách tường minh và dễ kiểm thử. Nó chỉ xử lý **file nhỏ (tối đa 10 MiB plaintext)** vì AES-GCM decryption và authentication có thể đòi hỏi buffer đáng kể; đây **không phải giải pháp streaming cho file hàng GB**.

### 5.1. Định dạng file demo

```text
┌──────────────┬────────────────┬───────────────────────┐
│ magic/version│ random nonce   │ ciphertext + GCM tag  │
│ "SBENC1"     │ 12 bytes       │ variable + 16 bytes   │
└──────────────┴────────────────┴───────────────────────┘
       6 B             12 B               N + 16 B
```

Phần `magic/version` cho phép nhận diện định dạng. Trong demo, magic được đưa vào AAD để tránh bị thay đổi mà không phát hiện. Nonce được truyền vào GCM; thay nonce sẽ làm tag verification thất bại (trừ trường hợp giả mạo mật mã vượt giả định bảo mật).

**Định dạng trên chỉ là định dạng học tập, không phải một tiêu chuẩn tương thích giữa tổ chức.** File production nên dùng một định dạng chuẩn hoặc một giao thức đã review, có version, key ID, wrapped DEK, thuật toán, quy tắc AAD và migration.

### 5.2. AesGcmFileCodec

```java
package com.example.batch.security;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Objects;

import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmFileCodec {

    private static final byte[] MAGIC =
            "SBENC1".getBytes(StandardCharsets.US_ASCII);

    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;

    public static final int MAX_PLAIN_BYTES = 10 * 1024 * 1024;
    public static final int MAX_ENCRYPTED_BYTES =
            MAGIC.length + NONCE_BYTES
                    + MAX_PLAIN_BYTES + TAG_BYTES;

    private final SecureRandom random = new SecureRandom();

    public byte[] encrypt(byte[] plaintext, SecretKey key)
            throws GeneralSecurityException {

        Objects.requireNonNull(plaintext, "plaintext");
        Objects.requireNonNull(key, "key");

        if (plaintext.length > MAX_PLAIN_BYTES) {
            throw new IllegalArgumentException(
                    "File too large for in-memory demo codec");
        }

        byte[] nonce = new byte[NONCE_BYTES];
        random.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));

        // Header được xác thực; không bảo mật (không cần bí mật).
        cipher.updateAAD(MAGIC);

        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        return ByteBuffer.allocate(
                        MAGIC.length + nonce.length
                                + ciphertextAndTag.length)
                .put(MAGIC)
                .put(nonce)
                .put(ciphertextAndTag)
                .array();
    }

    public byte[] decrypt(byte[] encoded, SecretKey key)
            throws GeneralSecurityException {

        Objects.requireNonNull(encoded, "encoded");
        Objects.requireNonNull(key, "key");

        int minimumLength =
                MAGIC.length + NONCE_BYTES + TAG_BYTES;

        if (encoded.length < minimumLength
                || encoded.length > MAX_ENCRYPTED_BYTES) {
            throw new IllegalArgumentException(
                    "Invalid encrypted file length");
        }

        ByteBuffer buffer = ByteBuffer.wrap(encoded);

        byte[] magic = new byte[MAGIC.length];
        buffer.get(magic);

        if (!Arrays.equals(magic, MAGIC)) {
            throw new IllegalArgumentException(
                    "Unsupported encrypted file format");
        }

        byte[] nonce = new byte[NONCE_BYTES];
        buffer.get(nonce);

        byte[] ciphertextAndTag = new byte[buffer.remaining()];
        buffer.get(ciphertextAndTag);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));

        cipher.updateAAD(MAGIC);

        // AEADBadTagException nếu sai key, sai nonce,
        // ciphertext/tag bị sửa hoặc file bị cắt cụt.
        return cipher.doFinal(ciphertextAndTag);
    }
}
```

**Điểm đáng chú ý:**

1. `SecureRandom` sinh nonce mới cho mỗi lần mã hóa. Một key+nonce không được lặp lại.
2. `GCMParameterSpec(128, nonce)` yêu cầu tag 128 bit.
3. `cipher.updateAAD(MAGIC)` đưa magic/version vào vùng được xác thực.
4. `Cipher.doFinal` khi giải mã phải xác thực tag; exception được truyền ra, **không có fallback đọc plaintext**.
5. `MAX_PLAIN_BYTES` giới hạn bài demo để tránh vô tình gọi `Files.readAllBytes` trên tệp lớn.
6. Java `SecretKey` phải được cấp bởi thành phần quản lý khóa an toàn; **codec không tự lưu khóa trong file**.
7. Output ciphertext có thể khác nhau dù plaintext giống nhau vì nonce khác nhau — đây là hành vi mong muốn.
8. Bộ giải mã phải được dùng sau bước kiểm tra định dạng và giới hạn đầu vào. File bị đổi magic bị từ chối trước khi giải mã.
9. Nếu thay đổi định dạng trong tương lai, hãy tăng version và có decoder tương ứng; không âm thầm diễn giải mọi byte theo cùng một định dạng.

### 5.3. Sinh khóa trong môi trường test

Chỉ để test đơn vị hoặc ví dụ học tập:

```java
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256);

SecretKey testKey = generator.generateKey();
```

Không dùng việc tạo ngẫu nhiên key mới mỗi lần application restart để mã hóa file cần giải mã sau này: nếu không lưu/wrap key một cách an toàn, file trở nên không thể đọc. Với production, dùng KMS/vault và một kế hoạch lưu `keyId`/wrapped DEK trong metadata của file.

---

## 6. Đọc và ghi file an toàn: giới hạn kích thước và xuất bản nguyên tử

Mã hóa đúng thuật toán vẫn có thể thất bại về an toàn vận hành nếu output đang ghi dở đã được consumer đọc, hoặc file plaintext tạm bị lộ.

### 6.1. Đọc file có giới hạn mà không nạp dữ liệu vô hạn

Với codec demo tối đa 10 MiB, có thể dùng helper:

```java
package com.example.batch.security;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class BoundedFileReader {

    private BoundedFileReader() {}

    public static byte[] readLimited(Path path, int maximum)
            throws IOException {

        if (maximum < 0
                || maximum == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid maximum");
        }

        try (InputStream stream = Files.newInputStream(path)) {
            byte[] value = stream.readNBytes(maximum + 1);

            if (value.length > maximum) {
                throw new IOException("Input exceeds size limit");
            }

            return value;
        }
    }
}
```

Cách đọc tối đa `maximum+1` giúp phát hiện file lớn mà không vô tình nạp toàn bộ nội dung vào RAM. Khi input lớn không được phép, **fail rõ ràng** thay vì cố tăng `-Xmx`.

### 6.2. Mã hóa vào file tạm rồi publish

Dưới đây là một helper minh họa thao tác phát hành **file đã mã hóa**. Giả định thư mục đích thuộc vùng được phép, đã tạo sẵn, nằm trên filesystem hỗ trợ atomic rename; đường dẫn nguồn/đích đã được validate và input nhỏ.

```java
package com.example.batch.security;

import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.GeneralSecurityException;

import javax.crypto.SecretKey;

public final class EncryptedPublisher {

    private final AesGcmFileCodec codec;

    public EncryptedPublisher(AesGcmFileCodec codec) {
        this.codec = codec;
    }

    public void publishSmallFile(
            Path plaintextInput,
            Path encryptedOutput,
            SecretKey encryptionKey)
            throws IOException, GeneralSecurityException {

        // Ví dụ chỉ nhận output mới; không tự thay file đã publish.
        if (Files.exists(encryptedOutput)) {
            throw new IOException("Output already exists");
        }

        Path directory = encryptedOutput.getParent();
        if (directory == null) {
            throw new IllegalArgumentException(
                    "Output path must have a parent directory");
        }

        byte[] plaintext = BoundedFileReader.readLimited(
                plaintextInput, AesGcmFileCodec.MAX_PLAIN_BYTES);

        byte[] encrypted = codec.encrypt(
                plaintext, encryptionKey);

        // Tạo file tạm trong cùng filesystem với đích.
        Path temporary = Files.createTempFile(
                directory, ".encrypted-", ".tmp");

        try {
            Files.write(temporary, encrypted);

            try {
                Files.move(temporary, encryptedOutput,
                        StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException unsupported) {
                throw new IOException(
                        "Atomic publish is required", unsupported);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}
```

Các giới hạn bảo mật và vận hành của ví dụ:

- `Files.move(..., ATOMIC_MOVE)` yêu cầu filesystem hỗ trợ và file đích phù hợp. Với một số provider, hành vi khi đích đã tồn tại có tính đặc thù; **kiểm tra trước không phải cơ chế khóa chống race**. Khi cần chắc chắn không overwrite, sử dụng một tên đích bất biến/duy nhất, lock/conditional create hoặc API conditional object upload phù hợp.
- Directory tạo file tạm phải có quyền truy cập chặt chẽ; file tạm ở đây đã là **ciphertext**, ít rủi ro hơn plaintext.
- Code này không xác thực `plaintextInput` có thuộc allowlisted directory hay là symlink nguy hiểm. Trong production cần kiểm soát path traversal, symlink, hardlink và ownership.
- `Files.write` hoàn tất chưa tự bảo đảm durability khi mất điện; nếu yêu cầu bền vững cao, cần cơ chế fsync/file channel, directory sync và xác nhận theo filesystem/object storage.
- Java byte arrays `plaintext` và `encrypted` còn có thể tồn tại trong heap cho đến lúc GC; không bảo đảm xóa khỏi mọi bản sao memory. Có thể xóa array khi không cần, nhưng `Arrays.fill` không đảm bảo xóa tất cả bản sao và không thay thế memory isolation.
- Nếu `encryptedOutput` đã tồn tại từ lần chạy trước, không tự xóa ghi đè khi retry. Kiểm tra manifest, checksum, business key và tình trạng publish để quyết định replay/reconcile.

### 6.3. Thứ tự thao tác nên ưu tiên

```text
Ghi dữ liệu vào vùng chưa công bố
             │
             ▼
Hoàn tất mã hóa + authentication tag
             │
             ▼
Kiểm tra file format / checksum / manifest
             │
             ▼
Publish nguyên tử hoặc conditional object PUT
             │
             ▼
Ghi nhận kết quả và audit
             │
             ▼
Cleanup vùng tạm theo chính sách
```

**Không để downstream nhận file khi writer hoặc encryptor chưa hoàn tất.** Với object storage, dùng tên tạm/temporary prefix hoặc conditional manifest object như tín hiệu “ready”, rồi chỉ cho consumer đọc những object đã được xác nhận công bố.

---

## 7. Giải mã trước khi ItemReader xử lý

Một `FlatFileItemReader` bình thường nhận `Resource` chứa văn bản CSV plaintext. Nếu file input đã mã hóa, không thể đưa trực tiếp ciphertext vào tokenizer rồi mong reader tự hiểu.

Có hai nhóm kiến trúc:

1. **File nhỏ, bounded in-memory:** giải mã và xác thực toàn bộ file trước, sau đó cung cấp `ByteArrayResource` cho reader. Đây là cách dễ minh họa, nhưng dùng heap theo kích thước file.
2. **File lớn:** dùng một định dạng mã hóa hỗ trợ streaming có authentication chuẩn, hoặc giải mã trong một staging area đủ bảo vệ rồi chỉ chuyển vào Spring Batch sau khi toàn bộ file đã xác thực. Cần thiết kế tránh plaintext chưa xác thực được commit vào database.

### 7.1. Bean @StepScope cho file nhỏ

Giả sử đã có `AesGcmFileCodec`, một `KeyProvider` cung cấp `SecretKey` theo reference từ cấu hình và model `Payment`:

```java
package com.example.batch.security;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.io.IOException;

import javax.crypto.SecretKey;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ByteArrayResource;

@Configuration(proxyBeanMethods = false)
class SensitiveInputConfig {

    @Bean
    @StepScope
    FlatFileItemReader<Payment> encryptedPaymentReader(
            @Value("#{jobParameters['encryptedInputFile']}")
                    String inputFile,
            AesGcmFileCodec codec,
            KeyProvider keyProvider) throws IOException,
                    GeneralSecurityException {

        byte[] ciphertext = BoundedFileReader.readLimited(
                Path.of(inputFile),
                AesGcmFileCodec.MAX_ENCRYPTED_BYTES);

        // Reference xác định key do KMS quản lý, không phải raw key.
        SecretKey key = keyProvider.loadDecryptKey(
                "batch-payments-v1");

        // Toàn bộ GCM tag được verify trước khi tạo reader.
        byte[] plaintext = codec.decrypt(ciphertext, key);

        return new FlatFileItemReaderBuilder<Payment>()
                .name("encryptedPaymentReader")
                .resource(new ByteArrayResource(plaintext))
                .encoding(StandardCharsets.UTF_8.name())
                .strict(true)
                .linesToSkip(1)
                .delimited()
                .names("id", "amount")
                .fieldSetMapper(fs -> new Payment(
                        fs.readLong("id"),
                        fs.readBigDecimal("amount")))
                .build();
    }
}
```

Trong ví dụ này, `Payment` là một model với constructor nhận `long` và `BigDecimal`; `KeyProvider` là interface do ứng dụng định nghĩa:

```java
package com.example.batch.security;

import javax.crypto.SecretKey;

public interface KeyProvider {
    SecretKey loadDecryptKey(String keyReference);
}
```

**Đây là kiến trúc demo cho file nhỏ**, không phải khuyến nghị mặc định cho mọi dữ liệu nhạy cảm. `ByteArrayResource` giữ plaintext trong Java heap cho tới khi resource/reader không còn reachable; `@StepScope` sống trong cả một `StepExecution`. Với file 5 GiB, cách này không phù hợp và có nguy cơ `OutOfMemoryError`.

Một cải tiến cho file nhỏ là cung cấp AAD mang `businessDate`/`fileId`, nhưng khi đó format và codec cũng phải được thay đổi đồng bộ ở cả encrypt/decrypt để xác thực metadata.

### 7.2. Vì sao không giải mã trước khi verify rồi cứ ghi DB?

Khi dùng authenticated encryption trên toàn file, kết quả chỉ đáng tin sau khi xác minh **toàn bộ authentication tag**. Nếu code đọc decrypted stream và cho item writer commit từng chunk trước khi tag cuối được kiểm tra, kẻ tấn công có thể đưa dữ liệu sai vào database rồi làm file fail integrity ở cuối.

Với dạng file mã hóa toàn khối, các hướng an toàn hơn là:

- **Xác thực/giải mã toàn bộ trước khi publish plaintext cho reader** (bounded memory hoặc secure staging).
- Dùng **định dạng mã hóa streaming được chuẩn hóa** có quy tắc authentication theo frame và xác thực toàn file, đồng thời bảo đảm transaction/publish không xảy ra trước khi file được xác nhận đầy đủ theo hợp đồng.
- Chỉ công bố kết quả sau một bước integrity validation hoàn chỉnh; nếu đã ghi tạm vào DB, staging phải được cách ly và có cơ chế rollback/discard/công bố riêng, không dùng ngay trong nghiệp vụ.

Spring Batch chunk commit không thể tự “đảo ngược” những thay đổi đã commit từ những chunk trước nếu cuối file mới phát hiện tag không hợp lệ.

---

## 8. File lớn: streaming encryption và authentication

### 8.1. Cạm bẫy của CipherInputStream với AES-GCM

Java có `CipherInputStream` và `CipherOutputStream`. Chúng có ích với một số chế độ mã hóa, nhưng **không nên mặc định dùng `CipherInputStream` để decrypt dữ liệu AES-GCM cần xác minh integrity**.

Javadoc Java cảnh báo `CipherInputStream` có thể bắt một số exception liên quan kiểm tra integrity (ví dụ `BadPaddingException`) mà **không truyền lại cho client**, nên không phù hợp cho một số tình huống giải mã authenticated mode như GCM. Một chương trình đọc tới EOF có thể không biết việc verify thất bại nếu dựa vào wrapper không báo lỗi như mong đợi.

Điều cần bảo đảm là: **tag verification failure phải làm job fail và không được phát hành dữ liệu**. Dùng API hoặc thư viện đã được kiểm chứng có hợp đồng xác thực rõ ràng; không tự coi “đọc hết stream” là “file hợp lệ”.

### 8.2. AES-GCM toàn file và bộ nhớ

Với `Cipher.doFinal` trên toàn bộ dữ liệu, code demo `AesGcmFileCodec` đọc file vào byte array. Một số provider JCA có thể buffer lượng lớn ciphertext/decoded output cho tới lúc verify tag, nên không thể suy ra rằng gọi `Cipher.update` trong vòng lặp sẽ tự tạo một pipeline decrypt file hàng GB với heap hằng số.

Để xử lý file lớn, phải chọn một định dạng/protocol có **streaming authentication được thiết kế trước**, hoặc dùng công cụ/thư viện được đánh giá cho bài toán file encryption.

### 8.3. Record/frame-based AEAD

Một định dạng streaming có thể chia plaintext thành các frame có kích thước giới hạn, mỗi frame mã hóa với key/nonce/AAD riêng:

```text
File header:
  version, algorithm, key reference/wrapped DEK,
  fileId, declared dataset/business identity

Frame 0:
  index=0, nonce0, ciphertext0, tag0
Frame 1:
  index=1, nonce1, ciphertext1, tag1
...
Final authenticated record:
  final marker, frame count, total length,
  manifest/digest theo giao thức
```

Một thiết kế đúng cần giải quyết tối thiểu:

- **Nonce uniqueness** cho mọi frame dưới cùng key, kể cả sau crash/restart.
- **Frame ordering:** không chấp nhận đảo thứ tự frame.
- **Truncation detection:** không chấp nhận file chỉ chứa các frame đầu, dù từng frame hợp lệ.
- **Replay/mix-and-match:** không chấp nhận frame của file khác cùng key ghép vào.
- **Version/key ID binding:** metadata liên quan phải được authentication với AAD.
- **Atomic completion:** biết lúc nào toàn bộ file đã hoàn tất và có thể publish.
- **Maximum frame size:** không cho client cấp phát buffer vô hạn từ length do file bên ngoài khai báo.
- **Restart semantics:** không tái sử dụng nonce và không tiếp tục từ trạng thái crypto chưa đủ thông tin.

**Đây là mô tả yêu cầu, không phải lời mời tự sáng chế định dạng mã hóa.** Một lỗi nhỏ ở frame count, final marker hoặc nonce có thể làm một file bị cắt/ghép vẫn được chấp nhận. Với production, ưu tiên định dạng/thư viện đã được review và tương thích với bên nhận.

### 8.4. Secure staging khi cần xác thực toàn bộ trước khi xử lý

Nếu hợp đồng file bên ngoài chỉ có một AES-GCM tag cuối và file rất lớn, có thể cần một bước giải mã được đánh giá kỹ, ghi plaintext vào **vùng staging được mã hóa ở cấp ổ đĩa và giới hạn quyền**, chỉ chuyển trạng thái “verified” sau khi xác thực toàn file thành công.

```text
encrypted input
       │
       ▼
restricted staging process
  ├── decrypt to protected temporary area
  ├── verify complete authentication tag
  └── if invalid: delete/quarantine, never publish
       │
       ▼ only verified
      ItemReader
       │
       ▼
 Spring Batch processing
       │
       ▼
 encrypted output + atomic publish
```

Giới hạn của phương án:

- Plaintext **có tồn tại trên disk** trong một khoảng thời gian; nếu quy định cấm, phương án này không được phép.
- Cần kiểm soát ACL, filesystem encryption, mount options, symlinks, snapshots, backup, swap, page cache và diagnostic.
- Cleanup file tạm không có nghĩa byte đã bị xóa vật lý an toàn trên SSD, filesystem copy-on-write hoặc cloud snapshot.
- Quyền giải mã và quyền đọc staging phải được tách theo vai trò nhỏ nhất có thể.
- Việc chuyển trạng thái verified và publish cần có manifest/audit không thể bị giả mạo bởi actor không được ủy quyền.

**Nếu không có vùng plaintext staging được phép**, cần một pipeline dựa trên streaming AEAD chuẩn cùng mô hình staging data/commit phù hợp, hoặc chuyển việc giải mã sang một dịch vụ chuyên trách bảo mật.

---

## 9. Key management: yếu tố quyết định hệ thống có an toàn không

### 9.1. Không hard-code khóa

Không lưu key thực trong:

- Source code, Git repository hoặc file `application.yml` commit lên Git.
- Command line arguments dễ xuất hiện trong process listing.
- URL, query string, log, tracing, exception message.
- `JobParameters`, `ExecutionContext` hoặc bảng metadata `BATCH_*`.
- Docker image, container layer hoặc build artifact.
- Plaintext file kèm cạnh ciphertext.

Ví dụ không nên:

```java
byte[] key = "my-secret-password-32-bytes....."
        .getBytes(StandardCharsets.UTF_8);
SecretKey unsafeKey = new SecretKeySpec(key, "AES");
```

Một password bình thường không tự trở thành AES key an toàn chỉ nhờ padding/cắt thành 16 hoặc 32 byte. Nếu dùng mật khẩu làm nguồn, cần một key derivation function chuẩn với salt/parameters phù hợp; với hệ thống batch production nên ưu tiên key từ KMS/vault thay vì phát triển cơ chế password-encryption riêng.

### 9.2. Envelope encryption

Một mô hình thường dùng:

- **DEK (data encryption key):** khóa dùng mã hóa dữ liệu của một file.
- **KEK (key encryption key):** khóa do KMS/HSM quản lý, dùng để wrap/unwrap DEK.
- **Encrypted DEK:** bản DEK đã được wrap, có thể lưu cùng header/manifest của ciphertext theo thiết kế.
- **Key ID/version:** chỉ thị khóa nào cần dùng để unwrap, không phải secret.

```text
KMS/HSM giữ KEK
      │
      ├─ Sinh/wrap một DEK cho file
      ▼
     DEK ─────────────► AES-GCM(plaintext, nonce, AAD)
      │                          │
      │                          ▼
      └─ wrap dưới KEK      encrypted file + auth tag
               │                 │
               ▼                 │
        wrapped DEK + key ID ─────┘
                  │
              lưu trong manifest/header

Khi giải mã:
  đọc key ID → KMS unwrap DEK → verify AEAD → xử lý
```

Lợi ích:

- Có thể cấp DEK riêng cho từng file, giới hạn phạm vi rủi ro của một DEK.
- Không cần giữ cùng một raw master key trong mọi worker.
- KMS IAM/audit kiểm soát ai có thể unwrap.
- Có thể thay/rotate KEK hoặc rewrap DEK theo quy trình hỗ trợ mà không luôn phải giải mã rồi mã hóa lại toàn bộ dữ liệu.

**Phân biệt:** thay KEK/rewrap DEK không nhất thiết thay ciphertext data; thay DEK thường yêu cầu decrypt và re-encrypt file. Mọi thay đổi phải phù hợp với định dạng, AAD và khả năng đọc file cũ.

### 9.3. Chọn quyền KMS

Áp dụng least privilege:

| Principal | Quyền cần có | Không nên có |
|---|---|---|
| Worker nhận file | Unwrap/decrypt đúng key/dataset | Khả năng export raw KEK, quyền đọc mọi vùng dữ liệu |
| Worker tạo output | Generate data key hoặc encrypt/wrap cho key được phép | Decrypt mọi file lịch sử nếu không cần |
| Dashboard giám sát | Đọc trạng thái job, metadata đã mask | Decrypt data hoặc đọc plaintext |
| Người vận hành | Xem audit, điều phối và yêu cầu recovery theo role | Khóa raw hoặc secret của tenant khác |
| Consumer file | Decrypt chỉ file/dataset được cấp phép | Key của đối tác/region khác |

Identity có thể đến từ workload identity/role gắn với process, không cần secret dài hạn trong file config. Với multi-tenant, phải kiểm tra tenant/file ownership trước khi yêu cầu decrypt; **key ID do file bên ngoài khai báo không được dùng để vượt chính sách ủy quyền**.

### 9.4. Key rotation, retention và khôi phục

Nếu file cần giữ bảy năm, khả năng giải mã cũng phải tồn tại trong thời gian retention hợp lệ. Xóa key quá sớm làm file vĩnh viễn không thể khôi phục. Ngược lại, lưu key không giới hạn khi dữ liệu đã hết hạn làm tăng rủi ro.

Cần chính sách:

1. Key version nào mã hóa file nào.
2. Ai có quyền decrypt và trong khoảng thời gian nào.
3. Khi rotation, file cũ dùng key cũ hay được rewrap/re-encrypt.
4. Khi key compromised, phạm vi file bị ảnh hưởng và quy trình thay thế.
5. Khi xóa dữ liệu/crypto-shredding, tác động lên backup và object versions.
6. Khôi phục KMS/khóa và metadata sau sự cố thiên tai; diễn tập khôi phục định kỳ.

Không log raw `SecretKey.getEncoded()` hoặc gửi unwrapped DEK sang observability system. JVM có thể giữ các bản sao key trong memory; giảm thời gian tồn tại và giới hạn quyền truy cập memory dump.

---

## 10. Gắn mã hóa vào Spring Batch theo ranh giới step

### 10.1. Ba mô hình tích hợp

| Mô hình | Cách làm | Điểm mạnh | Lưu ý |
|---|---|---|---|
| Giải mã trước, xử lý sau | Tasklet riêng xác thực input rồi tạo verified resource | Tách trách nhiệm, dễ fail sớm | Plaintext staging nếu không ở memory |
| Reader đọc format mã hóa | Custom `ItemStreamReader` hoặc adapter của thư viện mã hóa chuẩn | Có thể giảm plaintext staging | Phải bảo đảm auth, restart, nonce/frame ordering |
| Mã hóa sau khi writer hoàn tất | Step tạo output tạm → step encrypt/publish | Có thể xác thực output và chỉ publish khi xong | Plaintext output tạm phải được bảo vệ |
| Writer sinh ciphertext trực tiếp | Custom writer/stream encryption chuẩn | Tránh plaintext file ở output | Authentication, commit, failure/restart phức tạp |

Với bài toán nhạy cảm và cần checkpoint, nên có kiến trúc rõ:

```text
Job: secureTransferJob
  │
  ├─ Step A: verifyAndPrepareInput
  │     ├─ kiểm tra identity/manifest
  │     ├─ lấy key theo quyền
  │     └─ verify decrypt integrity
  │
  ├─ Step B: processData
  │     ├─ ItemReader
  │     ├─ ItemProcessor
  │     └─ ItemWriter ghi vùng unpublished
  │
  └─ Step C: encryptAndPublish
        ├─ tạo ciphertext hoàn chỉnh
        ├─ kiểm tra format/tag/manifest
        ├─ conditional/atomic publish
        └─ tạo audit + cleanup policy
```

**Mỗi step phải có contract về dữ liệu tạm và trạng thái hoàn tất.** Nếu Step C thất bại sau khi file đã publish nhưng trước khi `JobRepository` commit trạng thái, restart có thể chạy lại Step C. Vì vậy hành động publish phải **idempotent và có thể reconcile**, không dựa vào giả định filesystem tự rollback theo database.

### 10.2. JobParameters không nên chứa secret

Một ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("fileId", "payments-2026-11-15", true)
        .addString("inputObjectKey", "incoming/2026-11-15.enc", false)
        .addString("outputObjectKey", "outgoing/2026-11-15.enc", false)
        .toJobParameters();
```

Không truyền raw DEK, API token, khóa private key hoặc plaintext vào `JobParameters`; chúng được persist trong metadata và có thể hiển thị ở các API giám sát. `fileId`/`businessDate` là business identity; `inputObjectKey` được kiểm soát chặt và nếu chính nó nhạy cảm, cần mask trong log/UI.

Tương tự, `ExecutionContext` nên giữ checkpoint nhỏ (offset đã xác nhận, segment ID, file version/manifest digest) thay vì key hoặc dữ liệu record đã giải mã.

### 10.3. Restart, retry và output encryption

Hãy xác định các tình huống:

| Điểm lỗi | Trạng thái có thể còn lại | Recovery cần có |
|---|---|---|
| KMS không cấp quyền | Chưa giải mã file | Fail closed; sửa quyền trước khi restart |
| Input sai tag | File không đáng tin | Quarantine ciphertext, không commit dữ liệu |
| Process thất bại giữa job | Một số chunk đã commit | Restart từ checkpoint, tạm output cần phù hợp |
| Writer chưa flush xong | Output tạm chưa hoàn chỉnh | Xóa/rebuild hoặc resume theo format được hỗ trợ |
| Encrypt xong nhưng chưa publish | Ciphertext tạm hợp lệ | Reconcile và publish an toàn |
| Publish thành công nhưng step commit metadata fail | Đích đã có file dù `StepExecution` FAILED | Kiểm tra business key/manifest trước khi publish lại |
| Worker chết lúc cleanup plaintext | Tệp tạm có thể bị bỏ lại | Sweeper có audit/TTL và quyền truy cập hạn chế |
| Đổi key giữa hai attempt | Đầu ra có ciphertext khác | Key version/manifest ổn định hoặc re-encrypt có kiểm soát |

Với AES-GCM, **không resume một phiên mã hóa ở giữa file bằng nonce/cipher state không được bảo đảm**. Nếu không có giao thức frame/checkpoint đủ chặt, giải pháp an toàn thường là viết lại một **output tạm mới với nonce/DEK mới**, sau đó publish conditionally và đối chiếu kết quả.

### 10.4. Batch commit khác file publish

Database transaction của Spring Batch và hệ thống file/S3 thường không cùng transaction:

```text
Chunk commit trong DB ──────────── Xong
       │
       │   (không tự commit/rollback file publish)
       ▼
Output file object ─────────────── Có thể chưa publish

Hoặc:
Output đã publish ──────────────── Xong
       │
       ▼
JobRepository update metadata ──── Thất bại
```

Cần thiết kế một trong các chiến lược: staging + final manifest, atomic rename, conditional object creation, outbox/saga, hoặc reconcile theo business key. Không tin rằng `@Transactional` bao phủ remote object storage.

---

## 11. AAD và bảo vệ đúng danh tính file

### 11.1. Authenticated metadata là gì?

AAD (associated authenticated data) **không được mã hóa** nhưng được đưa vào phép xác thực của AEAD. Ví dụ một file chứa dữ liệu cho:

- `tenantId=merchant-12`
- `businessDate=2026-11-15`
- `dataset=customer-balance`
- `schemaVersion=4`
- `fileId=balance-2026-11-15-merchant-12`

Nếu các thông tin này được dùng để quyết định dữ liệu phải nhập vào bảng/tenant/ngày nào, chúng phải được **ràng buộc đáng tin** với ciphertext. Nếu không, người có quyền thay tên object có thể tráo một ciphertext hợp lệ của tenant A vào đường dẫn tenant B.

Ví dụ ở mức JCA:

```java
byte[] aad = ("v1|tenant=merchant-12"
        + "|date=2026-11-15"
        + "|dataset=customer-balance")
        .getBytes(StandardCharsets.UTF_8);

cipher.updateAAD(aad);
byte[] encrypted = cipher.doFinal(plaintext);
```

Giải mã phải dùng **chính xác cùng AAD bytes**, không chỉ chuỗi “trông tương đương” nhưng khác thứ tự, Unicode normalization hoặc encoding. Nên định nghĩa một serialization canonical rõ ràng, bao gồm độ dài/trường, tránh ghép chuỗi tùy ý dễ nhập nhằng.

### 11.2. Metadata lấy từ đâu?

Nếu tất cả AAD do file header không đáng tin khai báo, kẻ tấn công có thể thay cả header và ciphertext tương ứng của một file khác trong cùng bộ mà vẫn vượt xác thực theo file đó. Để ngăn tráo file, phải so khớp **AAD được mong đợi từ nguồn tin cậy** (manifest đã ký, job parameters được kiểm soát, bảng mapping được ủy quyền) với metadata trong file trước khi nhập.

### 11.3. Không đưa thông tin nhạy cảm tùy tiện vào AAD

AAD không bí mật. Tên khách hàng, email, số tài khoản hoặc thông tin đặc biệt nếu đưa vào header/AAD sẽ vẫn được lộ ở dạng plaintext. Chỉ dùng ID hoặc metadata tối thiểu cần thiết; nếu identity cũng cần giữ bí mật thì phải mã hóa nó trong payload hoặc bảo vệ manifest bằng cơ chế khác.

---

## 12. PGP/OpenPGP, AES-GCM, KMS và mã hóa ở tầng storage

Không phải lúc nào cũng nên tự làm một định dạng AES-GCM với file header riêng.

| Nhu cầu | Hướng thường dùng | Lưu ý |
|---|---|---|
| Trao đổi file định kỳ với đối tác | OpenPGP/PGP theo hợp đồng | Key công khai/bí mật, signing, integrity, interoperability |
| File nội bộ nhỏ, format do hệ thống kiểm soát | AEAD với key management chuẩn | Không tự làm protocol yếu; đảm bảo nonce/AAD/version |
| Lưu object ở cloud, chủ yếu chống lộ storage | SSE-KMS và IAM | Đọc object theo quyền hợp lệ vẫn nhận plaintext; có thể cần application encryption |
| File rất lớn giữa service nội bộ | Định dạng/thư viện streaming encryption đã được review | Frame auth, truncation, key rotation, restart |
| Nhiều bên nhận cùng file | Envelope encryption/public key wrapping | Phân quyền mỗi bên, quản lý bản mã hóa DEK |
| Yêu cầu chữ ký nguồn gửi | Digital signature hoặc xác thực nguồn theo hợp đồng | AES-GCM với symmetric key không tự chứng minh danh tính một sender duy nhất nếu nhiều bên cùng biết key |

**PGP encryption và PGP signing là hai chức năng khác nhau.** Một file đã được mã hóa chưa chắc có chữ ký số chứng minh người gửi. Khi có yêu cầu xác thực danh tính nguồn, cần xác minh chữ ký/chứng chỉ/public key và policy trust đúng cách.

**Cloud SSE-KMS** thường bảo vệ dữ liệu nằm trên storage; nó có ích nhưng không luôn thay cho việc trao ciphertext cho đối tác. Nếu bên nhận có quyền đọc object đã được dịch vụ storage giải mã, ứng dụng vẫn thấy plaintext.

Chọn giải pháp theo hợp đồng chia sẻ file, yêu cầu audit, compliance, khả năng tương thích và năng lực vận hành, không chỉ theo tên thuật toán.

---

## 13. Kiểm thử mật mã và bảo mật file

Không test AES bằng một ciphertext cố định làm “đáp án” rồi coi hệ thống an toàn. Cần kiểm thử **behavior** và các đường lỗi. Sử dụng khóa và dữ liệu test riêng, không dùng key production.

### 13.1. Unit test codec

Ví dụ JUnit Jupiter:

```java
package com.example.batch.security;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;

import javax.crypto.AEADBadTagException;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class AesGcmFileCodecTest {

    private AesGcmFileCodec codec;
    private SecretKey key;

    @BeforeEach
    void setUp() throws GeneralSecurityException {
        codec = new AesGcmFileCodec();

        KeyGenerator generator =
                KeyGenerator.getInstance("AES");
        generator.init(256);
        key = generator.generateKey();
    }

    @Test
    void roundTripRestoresOriginalBytes()
            throws GeneralSecurityException {

        byte[] input = "id,amount\n1,100.00\n"
                .getBytes(StandardCharsets.UTF_8);

        byte[] encrypted = codec.encrypt(input, key);
        byte[] decrypted = codec.decrypt(encrypted, key);

        assertArrayEquals(input, decrypted);
        assertFalse(Arrays.equals(input, encrypted));
    }

    @Test
    void tamperedTagFailsAuthentication()
            throws GeneralSecurityException {

        byte[] encrypted = codec.encrypt(
                "confidential".getBytes(StandardCharsets.UTF_8),
                key);

        encrypted[encrypted.length - 1] ^= 0x01;

        assertThrows(AEADBadTagException.class,
                () -> codec.decrypt(encrypted, key));
    }

    @Test
    void wrongKeyCannotDecrypt()
            throws GeneralSecurityException {

        KeyGenerator generator =
                KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey otherKey = generator.generateKey();

        byte[] encrypted = codec.encrypt(
                "private".getBytes(StandardCharsets.UTF_8),
                key);

        assertThrows(AEADBadTagException.class,
                () -> codec.decrypt(encrypted, otherKey));
    }

    @Test
    void truncatedFileIsRejected()
            throws GeneralSecurityException {

        byte[] encrypted = codec.encrypt(
                "1234567890".getBytes(StandardCharsets.UTF_8),
                key);

        byte[] shortened = Arrays.copyOf(
                encrypted, encrypted.length - 4);

        assertThrows(GeneralSecurityException.class,
                () -> codec.decrypt(shortened, key));
    }

    @Test
    void oversizedPlaintextIsRejected() {
        byte[] oversized =
                new byte[AesGcmFileCodec.MAX_PLAIN_BYTES + 1];

        assertThrows(IllegalArgumentException.class,
                () -> codec.encrypt(oversized, key));
    }
}
```

Các assertion minh họa:

- Round trip phục hồi đúng byte, không tự thay encoding hay newline.
- Thay tag/ciphertext phải làm decrypt thất bại.
- Sai khóa không được tạo “plaintext rác rồi cứ xử lý”.
- File bị cắt cụt phải bị từ chối.
- Giới hạn kích thước được thực thi.

Với `AEADBadTagException`, kết quả phụ thuộc API/provider mật mã và cách exception được gói. Unit test trên gọi trực tiếp `Cipher.doFinal` qua codec JCA, nên kiểm tra trực tiếp tag failure là phù hợp; nếu thêm wrapper, nên assert exception chain/code an toàn thay vì phụ thuộc duy nhất vào message.

### 13.2. Kiểm thử tích hợp Spring Batch

Tạo một fixture CSV nhỏ, mã hóa bằng khóa test và ghi thành input encrypted. Chạy job có reader giải mã và writer output; xác minh:

1. File đúng khóa/tag được đọc và có `readCount`/`writeCount` như kỳ vọng.
2. File sai tag làm step/job `FAILED`, **không** commit dữ liệu nghiệp vụ.
3. File sai key không được retry vô hạn.
4. File không đúng magic/version bị từ chối rõ ràng.
5. Một file quá lớn bị từ chối mà heap không tăng theo kích thước file thực.
6. Khi job lỗi giữa chừng, output encrypted chưa được publish cho consumer.
7. Restart theo cùng identifying `JobParameters` không ghi đè kết quả đã publish và không tái sử dụng nonce/key state không an toàn.
8. Log, `ExitDescription`, quarantine và metrics không lộ nội dung record hoặc raw key.

Với pipeline lớn, kiểm thử thêm trường hợp frame cuối bị thiếu, frame đảo thứ tự, frame của file khác bị ghép vào và manifest không khớp. Những bài test này phải theo **định dạng streaming thực tế** được sử dụng; không áp giả định của demo full-file AES-GCM cho mọi thư viện.

### 13.3. Kiểm thử key management

Một số kịch bản vận hành quan trọng:

| Tình huống | Kết quả cần xác minh |
|---|---|
| KMS/Vault từ chối decrypt | Job fail closed, không xử lý file |
| Key ID không thuộc tenant được ủy quyền | Từ chối trước hoặc tại bước key retrieval |
| Key bị rotate nhưng file cũ còn hợp lệ | Có thể đọc bằng key version cũ theo chính sách |
| Key bị thu hồi | Không còn giải mã được từ principal không được phép |
| KMS timeout tạm thời | Retry có giới hạn và không biến lỗi thành empty plaintext |
| Worker restart sau khi lấy DEK | Key lifecycle và recovery đúng, không log DEK |
| File được giải mã bằng context AAD khác | Authentication thất bại |
| Manifest chỉ tới file ID khác | Không cho import sai business identity |

Không cần dùng KMS production trong test; dùng fake provider hoặc KMS test environment có quyền hạn thấp và khóa riêng.

### 13.4. Kiểm thử đường dẫn, quyền và cleanup

- Đường dẫn `../` hoặc symlink vượt allowlisted root phải bị chặn.
- Worker không được đọc file của tenant khác.
- Temporary directory không mở quyền ghi/đọc cho user không liên quan.
- Lỗi giữa lúc encrypt/decrypt phải xóa/quarantine temp theo chính sách.
- Dọn file tạm sau crash bằng sweeper có audit; không xóa file đang được worker sử dụng.
- Không ghi plaintext trong log theo mặc định.
- Đã publish encrypted file thì consumer không đọc phiên bản đang ghi dở.

---

## 14. Monitoring và audit bảo mật

### 14.1. Những sự kiện nên ghi

| Event | Dữ liệu có thể ghi | Không nên ghi |
|---|---|---|
| FILE_RECEIVED | fileId, dataset, timestamp, size | Nội dung file |
| DECRYPT_STARTED | executionId, key reference, fileId | Raw key/DEK |
| AUTHENTICATION_FAILED | fileId, loại lỗi, correlationId | Full ciphertext/plaintext, key material |
| DECRYPT_COMPLETED | fileId, elapsed, số byte | PII trong record |
| OUTPUT_ENCRYPTED | fileId, algorithm/version, keyId, size | Khóa bí mật |
| FILE_PUBLISHED | object key đã kiểm soát, manifest hash, businessDate | Credential URL |
| CLEANUP_FAILED | temp object ID, error category | Secret, nội dung record |
| KMS_ACCESS_DENIED | principal, key reference, operation | Key bytes |

Metrics nên có số file mã hóa, số lần tag verification fail, thời gian encrypt/decrypt, lỗi KMS, thời gian chờ, backlog file chưa xử lý, số temp file còn tồn đọng và trạng thái publish. Dùng labels ổn định; không đưa `fileId` của từng khách hàng hoặc thông tin riêng tư vào metric tags dễ gây high cardinality.

### 14.2. Phân biệt lỗi mật mã với lỗi dữ liệu

| Lỗi | Cách phân loại |
|---|---|
| `AEADBadTagException` | Vi phạm integrity/sai key/sai AAD; không retry đổi plaintext |
| Unknown key version | Lỗi cấu hình hoặc key lifecycle, fail và điều tra |
| KMS throttling/timeout | Lỗi hạ tầng có thể retry giới hạn |
| File magic/version sai | Input không đúng hợp đồng |
| CSV sai schema sau khi decrypt hợp lệ | Lỗi dữ liệu, không phải crypto failure |
| Filesystem full lúc output encrypt | Lỗi storage; giữ trạng thái unpublished |
| Atomic move không được hỗ trợ | Lỗi publish capability; không âm thầm đổi sang cách yếu hơn nếu atomicity bắt buộc |
| Access denied trên vùng staging | Lỗi quyền, không mở rộng permission toàn bộ |
| File ciphertext không tồn tại | Lỗi nhận file/scheduling, không phải sai khóa |

Nếu tag verification fail, không nên “cố salvage vài dòng đọc được” rồi coi job thành công. Với dữ liệu tài chính hoặc định danh cá nhân, cách xử lý an toàn thường là quarantine **ciphertext** và tạo incident để xác minh nguồn file/khóa.

---

## 15. Performance: bảo mật và chunk memory

### 15.1. AES-GCM không tự giải quyết memory của chunk

Một `FlatFileItemReader` xử lý từng dòng sẽ giúp working set nhỏ. Nhưng nếu trước đó code `Files.readAllBytes()` với file 5 GiB để giải mã, memory đã có thể vượt giới hạn **trước khi chunk processing bắt đầu**.

Cần tách:

- **Kích thước file mã hóa**: có thể nhiều GiB.
- **Kích thước buffer cryptographic framing**: nên bounded theo design được review.
- **Chunk size của Spring Batch**: số input item/transaction.
- **Reader prefetch/page size**: lượng item reader giữ.
- **Writer buffer**: số byte chờ flush/encrypt.
- **Concurrency**: số file/step/partition đang chạy đồng thời.

Một công thức tư duy:

```text
Peak memory ≈
  Spring/JVM baseline
  + activeFiles × crypto working buffer
  + activeChunks × chunk object graph
  + reader/writer/ORM buffer
  + native/off-heap memory
  + GC headroom
```

Các giá trị phải được đo trên workload thực tế. Đừng chỉ giảm `chunkSize` rồi bỏ qua crypto buffer của cả file.

### 15.2. Chọn vị trí nén

Thông thường, nếu cần nén dữ liệu để giảm dung lượng, **nén trước khi mã hóa**, vì ciphertext có entropy cao và nén sau đó gần như không hiệu quả. Nhưng giải nén dữ liệu không đáng tin cần giới hạn kích thước output để chống decompression bomb. Nếu plaintext chứa secret trộn với dữ liệu do kẻ tấn công kiểm soát trong một giao thức có phản hồi quan sát được, compression side-channel cũng cần được xem xét theo threat model.

### 15.3. Theo dõi throughput và timeout

Bảo mật có overhead:

- Gọi KMS để tạo/unwrap DEK.
- Encrypt/decrypt CPU.
- Ghi tệp tạm và publish.
- Hash/checksum, manifest, audit.
- Xác minh authentication tag trước khi mở dữ liệu cho downstream.

Với file nhỏ, overhead KMS/network có thể lớn hơn chi phí AES. Với file lớn, I/O thường là nút thắt; nên benchmark AES-GCM implementation, buffer size, storage throughput và số job đồng thời.

Không tăng concurrency đến mức một worker giữ nhiều bản plaintext trong RAM hoặc vượt hạn mức KMS. Có thể cache DEK ngắn hạn nếu chính sách cho phép và key lifecycle/audit được thiết kế rõ, nhưng không cache raw KEK hoặc giữ key không giới hạn.

---

## 16. Tuân thủ retention, backup và xóa dữ liệu

File nhạy cảm có thể tồn tại ở nhiều bản:

- Encrypted input file.
- Temporary decrypted representation.
- Output temp trước mã hóa.
- Encrypted output.
- Quarantine/error file.
- Bucket version history.
- Snapshot/backup của filesystem.
- Log, tracing payload, heap dump.
- Cache/CDN hoặc bản sao bên đối tác.

Một kế hoạch retention phải xác định **bản nào được lưu bao lâu**, ai xóa, kiểm chứng xóa bằng cách nào và việc xóa key có làm mất khả năng khôi phục hợp pháp không.

### 16.1. Secure deletion không đơn giản

`Files.deleteIfExists(path)` xóa directory entry nhưng không bảo đảm các byte plaintext đã biến mất khỏi SSD, snapshot, copy-on-write filesystem, cloud backup hoặc page cache. Vì vậy tránh tạo plaintext disk ngay từ đầu là ưu tiên khi threat model yêu cầu nghiêm ngặt; nếu phải tạo, dùng vùng đã mã hóa, quyền chặt chẽ và chính sách lifecycle.

### 16.2. Khả năng giải mã sau nhiều năm

Nếu file được archive bảy năm, cần giữ khả năng unwrap DEK hợp lệ cho đúng thời gian đó; phải có quy trình key backup/recovery, versioning và kiểm thử đọc lại file archive. Nếu KMS key bị xóa mất, ciphertext có thể không thể phục hồi dù backup file còn nguyên.

### 16.3. Không đồng nhất encryption và compliance

Mã hóa là một biện pháp kỹ thuật. Yêu cầu về thông báo, phân loại, tối thiểu hóa dữ liệu, phân quyền, audit, thời gian lưu và xử lý yêu cầu xóa/truy cập dữ liệu vẫn cần được đánh giá riêng theo hợp đồng và luật áp dụng.

---

## 17. Runbook xử lý sự cố file nhạy cảm

### Bước 1 — Xác định phạm vi

Ghi lại `jobName`, `jobExecutionId`, `fileId`, businessDate, key reference, nguồn file và trạng thái output. Không đính kèm file plaintext vào ticket/chat.

### Bước 2 — Phân loại lỗi

- Sai format/header/version?
- Tag authentication failed?
- KMS access denied, key disabled hay timeout?
- File bị cắt cụt khi truyền?
- Filesystem/storage hết chỗ?
- Publish đã xảy ra nhưng JobRepository chưa cập nhật?
- Cleanup plaintext staging thất bại?

### Bước 3 — Fail closed và cô lập

Nếu integrity không xác thực được, **không tiếp tục đưa data vào hệ thống nghiệp vụ**. Đưa ciphertext và manifest vào khu vực quarantine được kiểm soát, giữ bằng chứng phục vụ điều tra, không giải mã thử bằng nhiều key không có policy.

### Bước 4 — Khôi phục có kiểm soát

- Yêu cầu đối tác gửi lại file nếu bị hỏng.
- Khôi phục key version bằng quy trình KMS nếu key vẫn hợp lệ.
- Kiểm tra manifest/AAD/bộ định danh nghiệp vụ.
- Nếu output đã publish, reconcile trạng thái trước khi chạy lại để tránh trùng.
- Nếu cần restart, dùng identifying `JobParameters` phù hợp.
- Không tự bỏ qua bước verify tag để đạt SLA.

### Bước 5 — Kiểm tra dấu vết plaintext

Rà soát file tạm, log, lỗi/quarantine, heap dump, backup và consumer đã đọc output chưa. Nếu có khả năng rò rỉ, kích hoạt quy trình security incident và hạn chế truy cập theo quy định.

### Bước 6 — Đối soát và đóng sự cố

Xác minh checksum/manifest, số record, output đúng businessDate/tenant, quyền trên file và audit đầy đủ. Chỉ đóng incident khi xác định dữ liệu đã được xử lý và phát hành chính xác.

---

## 18. Sai lầm thường gặp

| Sai lầm | Rủi ro | Hướng đúng |
|---|---|---|
| Dùng Base64 như mã hóa | Không bảo mật | AEAD/định dạng mã hóa được review |
| Dùng AES/ECB | Lộ pattern, thiếu integrity | AES-GCM hoặc format chuẩn |
| Dùng AES-CBC mà không xác thực | Có thể sửa dữ liệu không bị phát hiện | Authenticated encryption |
| Reuse AES-GCM nonce cùng key | Phá vỡ bảo mật | Nonce uniqueness và key lifecycle |
| Hard-code raw AES key trong YAML/Git | Lộ key và toàn bộ file | KMS/vault, quyền tối thiểu |
| Đưa raw key vào JobParameters | Key bị persist trong `BATCH_*` | Key reference, KMS authorization |
| Chỉ mã hóa file output, quên file input/temp | Plaintext tồn tại ở nhiều nơi | Đánh giá toàn bộ data flow |
| Dùng `CipherInputStream` và không kiểm tra AEAD integrity | Có thể bỏ qua lỗi xác thực | API/format bảo đảm tag verify |
| Decrypt streaming rồi commit từng chunk trước khi xác thực toàn file | Có thể commit dữ liệu từ ciphertext không hợp lệ | Verify trước publish hoặc staging isolation |
| Đọc toàn file lớn với `readAllBytes` | OOM, GC pressure | Bounded input + streaming format phù hợp |
| Ghi ciphertext thẳng vào tên output công khai | Consumer đọc file chưa hoàn tất | Temp + atomic/conditional publish |
| Coi `@Transactional` rollback file ngoài DB | File/object storage không cùng transaction | Idempotent publish và reconciliation |
| Tái sử dụng nonce/cipher state khi restart | Nguy cơ cryptographic failure | Giao thức restart đã review hoặc mã hóa lại file mới |
| Chỉ kiểm tra file magic/header | Không chứng minh integrity | GCM tag/signature/manifest verification |
| AAD lấy hoàn toàn từ nguồn không đáng tin | Tráo file giữa tenant/kỳ | AAD kỳ vọng từ manifest/trusted business identity |
| Log decrypted record khi lỗi | Lộ PII và secret | Structured logs, masking, audit |
| Xóa temp và cho rằng dữ liệu đã xóa vật lý | Snapshot/SSD còn bản sao | Tránh plaintext disk, lifecycle/crypto controls |
| Không giữ key version | File archive không giải mã được | Key ID/version, rotation và retention |
| Tự thiết kế streaming AEAD ad hoc | Dễ bỏ sót truncation/order/replay | Thư viện/format đã review |
| Bỏ qua KMS permission error để tiếp tục | Fail-open và dữ liệu sai | Fail closed |

---

## 19. Bài tập thực hành

### Bài 1 — Phân loại dữ liệu

Vẽ luồng của một job nhận file CSV chứa thông tin khách hàng từ SFTP, làm sạch và ghi vào object storage. Liệt kê mọi nơi có ciphertext/plaintext, những principal được phép truy cập và chính sách retention cho input, temp, output, backup, error/quarantine.

### Bài 2 — AES-GCM round trip

Dùng `AesGcmFileCodec` mã hóa rồi giải mã một file UTF-8 nhỏ. Kiểm tra byte output khớp đầu vào, kể cả dòng có dấu tiếng Việt, ký tự xuống dòng và dấu phẩy trong dữ liệu.

### Bài 3 — Tamper detection

Mã hóa file nhỏ, sửa một byte ở ciphertext/tag và thử giải mã. Xác nhận exception bị propagate; job không gọi writer hoặc publish bất kỳ dữ liệu nào từ file sai tag.

### Bài 4 — Sai khóa và key version

Tạo hai AES key trong test. Mã hóa bằng key A, thử giải mã bằng B và xác nhận fail. Thiết kế metadata `keyId`/wrapped DEK và mô tả cách một file cũ vẫn đọc được sau khi KMS rotation theo chính sách.

### Bài 5 — Authentication của business identity

Mở rộng codec demo để nhận AAD chứa `tenantId`, `businessDate` và `fileId` theo serialization canonical. Kiểm tra giải mã bằng AAD khác làm tag verification fail. Giải thích vì sao metadata AAD phải được đối chiếu với kỳ vọng từ nguồn đáng tin.

### Bài 6 — Spring Batch reader

Viết reader `@StepScope` dùng `ByteArrayResource` cho file encrypted dưới 10 MiB. Chạy integration test: file hợp lệ → đúng read/write counts; file sai tag → `FAILED` và không có output được công bố.

### Bài 7 — File lớn

Giả sử cần xử lý file 20 GiB với heap 1 GiB. So sánh bounded-memory streaming encryption format và secure staging. Nêu quy tắc nonce, frame order, truncation detection, final marker, AAD và ranh giới commit cần có.

### Bài 8 — Crash khi publish

Giả lập file đã được publish nhưng cập nhật `StepExecution` trong repository thất bại. Thiết kế manifest/conditional publish giúp restart không ghi đè sai và không để consumer nhận hai file cho cùng businessDate.

### Bài 9 — KMS outage

Dùng `KeyProvider` giả lập lỗi access denied và timeout. Xác minh hệ thống từ chối decrypt khi không được cấp quyền, retry giới hạn đúng loại lỗi transient và không ghi key vào log.

### Bài 10 — Security runbook

Viết runbook cho trường hợp file từ đối tác bị authentication tag failure và lỗi cleanup plaintext staging. Xác định dữ liệu cần giữ làm bằng chứng, vai trò vận hành được phép xem gì và cách kiểm tra không có file đã công bố sai.

---

## 20. Tài liệu tham khảo

- [NIST SP 800-38D — Galois/Counter Mode (GCM)](https://csrc.nist.gov/pubs/sp/800/38/d/final): nguyên tắc AES-GCM, IV/nonce và authentication.
- [NIST SP 800-57 — Key Management](https://csrc.nist.gov/projects/key-management/key-management-guidelines): quản lý khóa, lifecycle và phân quyền.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): lựa chọn thuật toán, authenticated encryption và key management.
- [Java 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `AES/GCM/NoPadding`, `updateAAD` và `doFinal`.
- [Java 17 — GCMParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): authentication tag length và IV.
- [Java 17 — CipherInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/CipherInputStream.html): giới hạn truyền exception integrity khi decrypt authenticated mode.
- [Java 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): sinh dữ liệu ngẫu nhiên mật mã.
- [Spring Batch — Flat File Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files.html): đọc/ghi file và `Resource`.
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): vòng đời `open/update/close` và checkpoint/restart.
- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): transaction chunk và xử lý từng item.
- [Spring Batch — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): metadata và transaction.
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/): kiểm soát quyền ứng dụng và service identities liên quan.
- [OpenPGP — RFC 9580](https://www.rfc-editor.org/rfc/rfc9580.html): định dạng thông điệp OpenPGP cho trao đổi dữ liệu theo hợp đồng.

**Tổng kết:** mã hóa file nhạy cảm trong Spring Batch không chỉ là chuyển plaintext thành ciphertext. Một giải pháp an toàn cần **authenticated encryption**, khóa được quản lý và phân quyền chặt, kiểm soát tất cả nơi plaintext có thể xuất hiện, xác thực file trước khi tin dữ liệu, và cơ chế publish/restart có tính idempotent. Với file nhỏ, ví dụ AES-GCM dùng JCA giúp hiểu nguyên tắc; với file lớn hoặc trao đổi đối tác, hãy chọn định dạng/thư viện chuẩn có authentication và key lifecycle được review. Chỉ khi thiết kế những ranh giới này cùng lúc, batch mới có thể xử lý dữ liệu nhạy cảm mà vẫn giữ được tính đúng đắn, khả năng recovery và bảo mật xuyên suốt.
