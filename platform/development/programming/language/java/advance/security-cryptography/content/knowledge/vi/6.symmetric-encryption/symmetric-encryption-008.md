# 6.8. Truyền AAD trước dữ liệu; phân biệt dữ liệu được xác thực với dữ liệu được mã hóa

## 1. Mục tiêu: hiểu đúng hai lớp bảo vệ trong AEAD

Khi mã hóa đối xứng, “người ngoài không đọc được nội dung” và “người ngoài không sửa được nội dung mà không bị phát hiện” là **hai yêu cầu khác nhau**:

- **Confidentiality (bí mật):** kẻ không có khóa khó khôi phục plaintext từ ciphertext.
- **Integrity/authenticity (toàn vẹn và xác thực):** bên nhận có thể phát hiện dữ liệu hoặc ngữ cảnh đã bị sửa mà không có quyền tạo authentication tag hợp lệ.

AEAD (*Authenticated Encryption with Associated Data*) phối hợp hai yêu cầu: nó **mã hóa và xác thực plaintext**, đồng thời cho phép xác thực thêm một vùng dữ liệu **không mã hóa** gọi là *Additional Authenticated Data* (AAD, đôi khi viết AD). Trong Java, một cách phổ biến là dùng `Cipher` với transformation `AES/GCM/NoPadding`.

Ví dụ thực tế: hệ thống gửi một hóa đơn với:

- Header: `version=1;tenant=shop-7` cần đọc được để định tuyến/hiểu định dạng, nhưng **không được lén đổi**.
- Payload: `hoa-don:120000 VND` cần được giữ **bí mật** và không được thay đổi.
- Nonce/IV: giá trị không bí mật, bên giải mã cần dùng đúng giá trị mã hóa đã sử dụng.
- Authentication tag: bằng chứng mật mã ràng buộc ciphertext và AAD với khóa/nonce/thuật toán.

Đưa **header** vào AAD và **payload** vào `Cipher.doFinal` cho AEAD sẽ tạo hai mức xử lý khác nhau: header còn nguyên dạng để truyền, nhưng sửa header khiến xác thực thất bại; payload được mã hóa, đồng thời được xác thực.

**Mục tiêu của bài:** biết byte nào được mã hóa, byte nào chỉ được xác thực; gọi `Cipher.updateAAD` đúng thứ tự; kiểm tra lỗi tag; thiết kế định dạng truyền dữ liệu đủ thông tin và an toàn.

## 2. AAD khác plaintext, ciphertext, IV và tag thế nào?

| Thành phần | Có bị mã hóa bởi AES-GCM? | Có được ràng buộc bởi xác thực AEAD? | Vai trò |
| --- | --- | --- | --- |
| **Plaintext** đi qua `update`/`doFinal` ở chế độ mã hóa | **Có**: trở thành ciphertext | **Có**: bên nhận chỉ chấp nhận plaintext sau kiểm tra tag | Dữ liệu cần bí mật và toàn vẹn |
| **AAD** đi qua `updateAAD` | **Không**: vẫn giữ nguyên byte công khai | **Có**: thay AAD sẽ làm tag không khớp | Header, loại bản ghi, tenant, version, định danh ngữ cảnh |
| **Ciphertext** | Đã là dữ liệu mã hóa | **Có** | Kết quả mã hóa payload; sửa byte sẽ làm xác thực thất bại |
| **IV/nonce** của GCM | **Không**; thường được lưu/truyền công khai | Phải khớp với phép mã hóa và ảnh hưởng đến quá trình tính tag | Bảo đảm uniqueness mỗi lần mã hóa dưới cùng khóa; cần đúng nonce để giải mã |
| **Authentication tag** | Không phải plaintext bí mật; thường gắn sau ciphertext trong kết quả `doFinal` | Là giá trị được kiểm tra để quyết định xác thực | Phát hiện sửa đổi dữ liệu/tag/ngữ cảnh |
| Dữ liệu **không** đưa vào AAD, cũng **không** mã hóa | Không | **Không**, trừ khi có cơ chế xác thực riêng | Không được tin là đã được AEAD bảo vệ |

Một điểm thường bị hiểu nhầm: **AAD là authenticated, nhưng không confidential**. Nếu header chứa tên khách hàng, email hay thông tin nhạy cảm, đưa header đó vào AAD **không che giấu** các thông tin này. Muốn bí mật, đặt dữ liệu trong plaintext để mã hóa (và xác thực), hoặc bảo vệ riêng bằng cơ chế thích hợp.

Tương tự, “dữ liệu đã mã hóa” chưa tự chứng minh an toàn nếu chỉ dùng một mode không xác thực như AES-CBC đơn lẻ. Ở đây AES-GCM vừa mã hóa vừa tạo tag; bên giải mã phải **kiểm tra tag thành công** trước khi sử dụng kết quả.

### Minh họa về phạm vi byte

```text
Bản ghi truyền/lưu trữ (ví dụ)
+---------------------------+----------------------+---------------------+
| header (AAD, rõ)          | nonce/IV (rõ)        | ciphertext || tag   |
| version=1;tenant=shop-7   | 12 byte              | byte đã mã hóa + tag |
+---------------------------+----------------------+---------------------+
           |                          |                       |
           +----------- đưa vào ------|------> Cipher GCM <----+
                            updateAAD(header)
                                      init(key, nonce)
                                      doFinal(payload)

Khi giải mã, cùng key + nonce + AAD + ciphertext/tag:
    tag hợp lệ --> nhận plaintext
    tag sai    --> từ chối toàn bộ bản ghi
```

Sơ đồ chỉ mô tả **ý nghĩa** các trường; trong ứng dụng thật phải có cấu trúc nhị phân hoặc JSON có schema/version/độ dài byte rõ ràng. Không trông chờ `Cipher` tự biết header nào là AAD: ứng dụng phải **chủ động** gọi `updateAAD` với đúng byte header.

## 3. Thứ tự gọi API bắt buộc trong Java

Với GCM/CCM, tài liệu `javax.crypto.Cipher` quy định **toàn bộ AAD phải được cung cấp trước khi bắt đầu xử lý dữ liệu** bằng `update` hoặc `doFinal`. Điều này áp dụng cho **cả mã hóa lẫn giải mã**.

Thứ tự đúng:

1. `Cipher.getInstance("AES/GCM/NoPadding")` để lấy engine.
2. `cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv))` để chọn khóa và tham số.
3. `cipher.updateAAD(headerBytes)` để nạp dữ liệu chỉ cần xác thực. Có thể gọi `updateAAD` nhiều lần, nhưng mọi lần đều phải diễn ra **trước** thao tác trên plaintext/ciphertext.
4. `cipher.update(payloadChunk)` không bắt buộc nếu xử lý theo từng khối; hoặc đi thẳng tới `cipher.doFinal(plaintext)` nếu dữ liệu đủ nhỏ.
5. `cipher.doFinal(...)` kết thúc phép mã hóa và trả ciphertext kèm tag xác thực.

Đối với giải mã, thay `ENCRYPT_MODE` bằng `DECRYPT_MODE` và cung cấp **chính xác cùng AAD** trước khi xử lý ciphertext. `doFinal(ciphertextAndTag)` sẽ kiểm tra tag; nếu tag không khớp, API có thể ném `AEADBadTagException`. Không sử dụng hoặc công bố plaintext khi chưa xác minh thành công.

```java
// Trích đoạn minh họa, giả sử key, iv, aad, plaintext đã tồn tại.
Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
encryptor.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
encryptor.updateAAD(aad);                   // 1. Xác thực header
byte[] encrypted = encryptor.doFinal(plaintext); // 2. Mã hóa payload + tag
```

**Sai thứ tự** là gọi `update(plaintextChunk)` trước rồi mới gọi `updateAAD(aad)`. Với GCM/CCM, `Cipher.updateAAD` sau khi dữ liệu đã được xử lý là sai trạng thái và có thể ném `IllegalStateException`; không coi lỗi này là “provider tùy ý”, vì contract Java đã yêu cầu AAD đi trước. Cũng không được xử lý dữ liệu bằng `doFinal` rồi mới gửi AAD: lúc đó phép toán đã kết thúc.

Lý do của thứ tự này: các mode AEAD xử lý tính xác thực AAD trước khi bắt đầu phần tính xác thực ciphertext. Provider cần nhận đủ AAD để triển khai đúng và tránh phải giữ lại toàn bộ ciphertext trong bộ đệm chỉ vì AAD đến muộn.

### Có thể gọi updateAAD nhiều lần không?

Có, khi các byte thuộc cùng một thông điệp GCM được truyền theo từng mảnh **trước payload**. Ví dụ:

```java
cipher.updateAAD(versionBytes);
cipher.updateAAD(tenantBytes);
cipher.updateAAD(headerBytes);
byte[] output = cipher.doFinal(plaintext);
```

Đây là **đoạn mã minh họa** trong ngữ cảnh đã khởi tạo `cipher` và xác định rõ các mảng. Hãy nhớ GCM xác thực **chuỗi byte AAD theo đúng thứ tự**. Nếu bên gửi ghép `versionBytes||tenantBytes||headerBytes` mà bên nhận dùng một thứ tự khác, quá trình xác thực sẽ thất bại.

Đặc biệt, với các trường có độ dài biến đổi cần **định nghĩa serialization không mơ hồ**: chẳng hạn mỗi trường có tag loại và độ dài cố định/tiền tố độ dài. Chuỗi `"ab" + "c"` và `"a" + "bc"` tạo cùng byte nếu chỉ nối trần; nếu ý nghĩa các trường khác nhau, ứng dụng phải mã hóa ranh giới trường vào AAD.

## 4. Ví dụ Java 17+ chạy độc lập: header rõ nhưng phải xác thực

Chương trình tạo một khóa AES dùng riêng cho demo, sinh nonce ngẫu nhiên mới dài 12 byte, đưa header vào AAD, mã hóa payload bằng AES-GCM và giải mã đúng. Sau đó chương trình lần lượt sửa **AAD**, **ciphertext** và **IV** để xác nhận bản ghi bị từ chối.

Tạo file `AadGcmDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AadGcmDemo {
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int TAG_BITS = 128;

    static byte[] encrypt(SecretKey key, byte[] iv, byte[] aad,
            byte[] plaintext) throws Exception {
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        cipher.updateAAD(aad); // Must precede update/doFinal on payload.
        return cipher.doFinal(plaintext);
    }

    static byte[] decrypt(SecretKey key, byte[] iv, byte[] aad,
            byte[] ciphertextAndTag) throws Exception {
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        cipher.updateAAD(aad); // Supply exactly the same AAD bytes.
        return cipher.doFinal(ciphertextAndTag); // Checks authentication tag.
    }

    static boolean accepted(SecretKey key, byte[] iv, byte[] aad,
            byte[] ciphertextAndTag) throws Exception {
        try {
            decrypt(key, iv, aad, ciphertextAndTag);
            return true;
        } catch (AEADBadTagException rejected) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] iv = new byte[12]; // Fresh IV for this encryption.
        new SecureRandom().nextBytes(iv);

        byte[] aad = "version=1;tenant=shop-7"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "hoa-don:120000 VND"
                .getBytes(StandardCharsets.UTF_8);

        byte[] ciphertextAndTag = encrypt(key, iv, aad, plaintext);
        byte[] recovered = decrypt(key, iv, aad, ciphertextAndTag);

        System.out.println("AAD visible: " +
                new String(aad, StandardCharsets.UTF_8));
        System.out.println("Decrypted data: " +
                new String(recovered, StandardCharsets.UTF_8));
        System.out.println("Tag overhead: " +
                (ciphertextAndTag.length - plaintext.length) + " bytes");

        byte[] changedAad = aad.clone();
        changedAad[0] ^= 1;
        System.out.println("Changed AAD accepted: " +
                accepted(key, iv, changedAad, ciphertextAndTag));

        byte[] changedCiphertext = ciphertextAndTag.clone();
        changedCiphertext[0] ^= 1;
        System.out.println("Changed ciphertext accepted: " +
                accepted(key, iv, aad, changedCiphertext));

        byte[] changedIv = iv.clone();
        changedIv[0] ^= 1;
        System.out.println("Changed IV accepted: " +
                accepted(key, changedIv, aad, ciphertextAndTag));
    }
}
```

Biên dịch và chạy (JDK 17 trở lên có hỗ trợ AES/GCM):

```bash
javac AadGcmDemo.java
java AadGcmDemo
```

Stdout chính xác cho mọi lần chạy thành công, dù khóa/IV/ciphertext được sinh ngẫu nhiên:

```text
AAD visible: version=1;tenant=shop-7
Decrypted data: hoa-don:120000 VND
Tag overhead: 16 bytes
Changed AAD accepted: false
Changed ciphertext accepted: false
Changed IV accepted: false
```

### Giải thích vì sao ba lần sửa đều thất bại

- **Đổi AAD:** ciphertext/tag/khóa/IV vẫn y như cũ, nhưng header thay một byte. Vì AAD được dùng để tính tag GCM, `doFinal` bên giải mã ném `AEADBadTagException`. Điều này minh họa **AAD được xác thực dù không bị mã hóa**.
- **Đổi ciphertext:** header AAD giữ nguyên, nhưng một byte ciphertext đã đổi. Tag không còn hợp lệ, nên không chấp nhận payload đã bị sửa.
- **Đổi IV:** IV là tham số quan trọng của một lần mã hóa. Giải mã với IV khác sẽ không khôi phục đúng dữ liệu/tag đã tạo; ví dụ cho thấy xác thực bị từ chối.
- **Tag overhead:** với tag dài 128 **bit** thì ciphertext trả về từ `doFinal` ở ví dụ có thêm 16 **byte** tag so với plaintext. Đây là tag xác thực, không phải `PKCS5Padding`; transformation dùng `NoPadding`.
- **Giá trị AAD công khai:** chương trình cố ý in nguyên header để cho thấy AAD không hề được mã hóa. Không suy ra AAD phải đưa lên màn hình/log trong ứng dụng thật; điều đó phụ thuộc yêu cầu riêng tư của header.

**Phạm vi ví dụ:** khóa chỉ tồn tại trong process; đây không phải quy trình lưu key/ciphertext lâu dài. Khi giải mã trên máy khác hoặc sau khi restart, cần truy xuất đúng khóa qua keystore/KMS và truyền/lưu đúng IV, header AAD cùng ciphertext/tag.

## 5. Phân biệt “đã được xác thực” và “đã được mã hóa”

### 5.1. Dữ liệu được mã hóa và xác thực

Trong AES-GCM, **payload** đi qua `Cipher.update`/`doFinal` được biến đổi thành ciphertext; người không có khóa phù hợp không đọc được plaintext theo giả định an toàn của thuật toán. Đồng thời, tag GCM ràng buộc payload, AAD, khóa và nonce trong quá trình xác thực. Bên giải mã chỉ **chấp nhận kết quả sau khi tag hợp lệ**.

Từ “được mã hóa” không đồng nghĩa “bất cứ ciphertext nào cũng an toàn”: cần đúng mode AEAD, nonce/IV, độ dài tag, quản lý khóa và quy trình kiểm tra kết quả.

### 5.2. Dữ liệu được xác thực nhưng không mã hóa

**AAD** không đi qua phép mã hóa plaintext, nên người quan sát vẫn đọc được nội dung AAD nếu bản ghi chứa nó ở dạng rõ. Tuy nhiên, bên nhận gọi `updateAAD` trước `doFinal` để kiểm tra tính toàn vẹn của chính những byte đó cùng payload.

Trường hợp sử dụng: version của định dạng, loại bản ghi, tên tenant không nhạy cảm, định danh tài liệu, sequence number hoặc content type mà bên nhận cần xem *sớm* để định tuyến. Chỉ dùng các trường này để ra quyết định bảo mật **sau khi xác thực thành công**; nếu cần dùng sơ bộ để định tuyến/lấy khóa, phải coi chúng là dữ liệu chưa tin cậy và kiểm tra lại sau xác thực.

### 5.3. Dữ liệu hoàn toàn nằm ngoài phạm vi AEAD

Nếu một trường đi cùng bản ghi mà bạn **không** nạp vào AAD, cũng **không** đưa vào plaintext được mã hóa, thì GCM không tự bảo vệ trường đó. Ví dụ `tenantId` trong JSON nằm ngoài ciphertext mà bị bỏ qua ở `updateAAD` có thể bị sửa mà phép kiểm tra tag vẫn hợp lệ cho ciphertext cũ. Đây là lỗi thiết kế ngữ cảnh rất dễ bị bỏ sót.

Cách sửa: xác định từ đầu danh sách metadata ảnh hưởng đến diễn giải, quyền và bản sắc bản ghi; biểu diễn thành chuỗi byte AAD có version và truyền đúng những byte đó vào AEAD.

### 5.4. AAD không thay thế mã hóa hay chữ ký số

- AAD không bảo vệ **tính bí mật** của chính header.
- AEAD không tự chứng minh danh tính pháp lý của người gửi: nếu nhiều bên biết cùng khóa đối xứng, bên nào có khóa cũng có thể tạo tag hợp lệ.
- Không giải quyết **replay**: bản ghi ciphertext/tag/AAD/IV hợp lệ có thể bị phát lại nguyên vẹn. Chống replay cần sequence number/nonce nghiệp vụ/timestamp được xác thực **và** kiểm soát dùng lại/hết hạn ở ứng dụng.
- Không thay thế kiểm tra **authorization**: tag hợp lệ chưa có nghĩa người yêu cầu được quyền xem hoặc sửa bản ghi của tenant đó.

## 6. Thiết kế record với AAD: những byte nào phải khớp?

Ví dụ một record có thể gồm:

| Trường | Cách bảo vệ | Lưu ý |
| --- | --- | --- |
| `formatVersion` | AAD | Không cho phép kẻ gửi lặng lẽ đổi định dạng; kiểm tra version được hỗ trợ trước khi parse sâu. |
| `tenantId` | AAD nếu công khai; plaintext nếu cần bí mật | Định danh tenant cần ràng buộc với ciphertext và quyền truy cập thực tế. |
| `contentType` | AAD | Ngăn thay đổi cách phân tích payload sau giải mã. |
| `keyId` | AAD hoặc ràng buộc qua giao thức an toàn | Có thể cần dùng để tra khóa **trước xác thực**, lúc này keyId vẫn chưa đáng tin; chỉ dùng whitelist/lookup có giới hạn và xác minh lại. |
| `iv` | Trường công khai riêng | Phải bảo đảm duy nhất theo khóa khi mã hóa; dùng đúng IV ở phía giải mã. |
| `ciphertextAndTag` | Ciphertext bí mật và tag xác thực | Lưu cả tag; không tách/nhầm số byte. |
| `payload` | Plaintext đưa vào `doFinal` | Mã hóa + xác thực; ví dụ số tiền, mô tả nội dung, dữ liệu riêng tư. |

Định nghĩa **byte serialization nhất quán**: một record JSON dùng để hiển thị vẫn có thể khác thứ tự field, whitespace, Unicode normalization hoặc kiểu số giữa hai runtime. Nếu bên gửi tính AAD bằng UTF-8 của `"version=1;tenant=shop-7"` còn bên nhận dùng UTF-8 của `"tenant=shop-7;version=1"`, hai byte array khác nhau và xác thực thất bại.

Hai cách xử lý hợp lý:

1. **Lưu/truyền nguyên byte header đã được xác thực.** Bên nhận lấy chính byte này, chuyển vào `updateAAD`, chỉ sau khi tag hợp lệ mới tin các trường đã parse.
2. **Dùng serialization có chuẩn canonical rõ ràng.** Định nghĩa encoding UTF-8, thứ tự trường, độ dài và loại trường, canonicalization; cả hai phía tái tạo **giống chính xác từng byte**.

Không chỉ nối các giá trị biến độ dài mà không có ranh giới: `"ab" + "c"` và `"a" + "bc"` có cùng chuỗi byte dù hai cặp field khác nhau. Dùng length prefix hoặc cấu trúc field có tag/length và version để tránh nhập nhằng.

## 7. Xử lý dữ liệu theo stream mà không vi phạm thứ tự

Java có các overload:

- `cipher.updateAAD(byte[])`;
- `cipher.updateAAD(byte[], offset, len)`;
- `cipher.updateAAD(ByteBuffer)`.

Và các phương thức xử lý dữ liệu như `update(...)`, `doFinal(...)`. Thứ tự hợp lệ nếu mã hóa/decrypt dữ liệu theo mảnh:

```text
Cipher.init(...)
  |
  +-- updateAAD(headerPart1)
  +-- updateAAD(headerPart2)
  +-- updateAAD(headerPart3)   <-- KẾT THÚC AAD
  |
  +-- update(payloadPart1)
  +-- update(payloadPart2)
  +-- doFinal(lastPayloadPart)
       |
       +-- encrypt: ciphertext cuối + authentication tag
       +-- decrypt: kiểm tra tag; thành công mới chấp nhận plaintext
```

Với `ByteBuffer`, `updateAAD(ByteBuffer)` xử lý các byte trong phần `remaining()` của buffer và cập nhật `position` đến `limit`; nó không đồng nghĩa toàn bộ dung lượng vật lý của buffer nếu position/limit đã thay đổi.

### Không sử dụng plaintext giải mã trước khi kiểm tra tag

Trong GCM, việc kiểm tra tag cuối cùng xảy ra ở `doFinal`. Một số implementation có thể buffer đầu ra giải mã, số khác có thể cung cấp plaintext từ `update` trước khi tag cuối được xác nhận. Vì vậy **không gửi dữ liệu tạm giải mã ra network, ghi vào DB như dữ liệu đáng tin hoặc thực thi nó** trước khi toàn bộ phép xác thực thành công. Với dữ liệu lớn, dùng vùng đệm/quy trình staging và chỉ commit/publish khi `doFinal` thành công; nếu xác thực thất bại, loại bỏ dữ liệu tạm.

Nếu `doFinal` ném `AEADBadTagException`, không thử “giải mã tiếp” hoặc bỏ qua tag để cứu plaintext. Từ chối bản ghi, dọn buffer nhạy cảm thích hợp và xử lý lỗi ở ranh giới ứng dụng.

### Có phải luôn phải gọi updateAAD?

Không. AAD là **tùy chọn** trong AES-GCM: nếu không có metadata cần xác thực bổ sung, ứng dụng có thể không gọi `updateAAD` và vẫn mã hóa/xác thực payload bằng GCM. Nhưng một khi **đã thiết kế** header phải được bảo vệ như AAD, thì cả bên mã hóa và giải mã đều phải gửi đúng byte header qua `updateAAD` trước xử lý payload. Quên bước này ở **cả hai phía** có thể khiến mã hóa/giải mã vẫn chạy nhưng header không được xác thực như mong muốn.

## 8. Rủi ro và nguyên tắc an toàn đi kèm

1. **Không dùng lại (key, IV) khi mã hóa AES-GCM.** IV ngẫu nhiên 96 bit từ `SecureRandom` là một cách sinh nonce phổ biến; hệ thống tải lớn cần kiểm soát xác suất đụng độ, số lần mã hóa mỗi khóa và rotation. Không dùng IV hằng số, không tái sử dụng bản ghi cũ để mã hóa thông điệp mới.
2. **Tách IV và AAD.** IV điều khiển quá trình GCM; AAD là byte metadata tùy chọn nhưng được xác thực. Chúng không thay thế nhau. IV công khai không có nghĩa có thể dùng sai IV mà vẫn mong giải mã đúng.
3. **Dùng tag đủ mạnh theo giao thức.** Ví dụ tag 128 bit và IV 12 byte; `GCMParameterSpec(128, iv)` nhận **bit**, không phải byte. Không để client tự yêu cầu tag ngắn không theo chính sách.
4. **Bảo vệ khóa.** AAD, IV và ciphertext/tag có thể lưu/truyền công khai theo thiết kế, nhưng khóa AES phải được quản lý an toàn bằng keystore/KMS, kiểm soát truy cập và vòng đời riêng. Không hardcode khóa thật.
5. **Không dùng header chưa xác thực để cấp quyền.** Có thể parse sơ bộ version/keyId cho định tuyến nhưng phải giới hạn thuật toán/khóa được phép và **kiểm tra lại** tất cả ngữ cảnh khi tag hợp lệ.
6. **Không dùng AAD chứa dữ liệu mà bạn kỳ vọng được giấu.** Tên người dùng, địa chỉ, tài khoản hoặc nội dung riêng tư trong AAD có thể lộ cho người quan sát. Đưa phần cần bí mật vào plaintext.
7. **Không coi mã hóa AES-CBC đơn lẻ tương đương AEAD.** CBC không có tính năng xác thực AAD/tag của GCM. Nếu cần xác thực toàn bộ message, dùng AEAD hoặc giao thức encrypt-then-MAC được thiết kế đúng.
8. **Giới hạn kích thước và đầu vào.** Kiểm tra IV length, version, tag length, ciphertext size, header length, charset và trường bắt buộc trước khi cấp phát bộ nhớ hoặc giải mã. Từ chối các transformation không nằm trong allowlist.
9. **Không tiết lộ lý do xác thực thất bại quá chi tiết.** Dữ liệu sai AAD, sai key, sai IV, bị sửa ciphertext/tag có thể đều dẫn tới lỗi tag. Ứng dụng cần phản hồi từ chối phù hợp, tránh log plaintext hoặc key.
10. **Không tái dùng Cipher để mã hóa thông điệp mới với cùng key/IV.** Mỗi lần mã hóa phải khởi tạo với IV mới độc nhất. `Cipher` không phải đối tượng chia sẻ tùy tiện giữa các thread.

## 9. Triệu chứng lỗi và cách gỡ

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `IllegalStateException` khi `updateAAD` | Gọi sau `update`, sau thao tác hoàn tất, trước `init`, hoặc mode/provider không ở trạng thái chấp nhận AAD | Khởi tạo cipher và truyền toàn bộ AAD trước khi gửi bất kỳ payload/ciphertext nào |
| `IllegalArgumentException` | Truyền byte[] AAD là `null` hoặc tham số offset/length sai | Xác minh dữ liệu và giới hạn mảng trước khi gọi |
| `AEADBadTagException` từ `doFinal` | AAD/key/IV/ciphertext/tag khác với lúc mã hóa, hoặc dữ liệu bị cắt/sửa | Từ chối toàn bộ bản ghi; kiểm tra contract byte và metadata; không bỏ qua xác thực |
| Dữ liệu payload giải mã đúng nhưng header đổi mà không báo lỗi | Header không được đưa vào AAD ở cả hai phía, hoặc ứng dụng đọc trường khác với trường đã authenticated | Rà soát chính xác byte đã nạp qua `updateAAD` và vùng metadata thực sự được bảo vệ |
| Đổi thứ tự header fields thì decrypt thất bại | Serialization/canonicalization AAD giữa hai bên khác nhau | Định nghĩa byte representation tường minh và kiểm thử round-trip |
| Tag dài hơn dự kiến 16 byte | Nhầm `GCMParameterSpec` tag length **bit** với byte hoặc tách tag sai | Xác định tag 128 bit = 16 byte và cách `doFinal` trả ciphertext+tag |
| Bản ghi bị phát lại vẫn decrypt thành công | AEAD bảo vệ tính toàn vẹn, **không tự chống replay** | Dùng sequence/messageId/timestamp được xác thực và kiểm soát trùng ở application |

Đừng “chữa lỗi” `AEADBadTagException` bằng cách bỏ `updateAAD` trên cả hai phía để dữ liệu giải mã được; cách này vô hiệu hóa mục tiêu bảo vệ header. Cũng không được thay GCM bằng mode không xác thực chỉ để tránh lỗi tag.

## 10. Checklist tự kiểm tra và bài tập

Trước khi triển khai AEAD có AAD, hãy tự trả lời:

- Thành phần nào **chỉ xác thực** (AAD), thành phần nào **vừa mã hóa vừa xác thực** (payload), trường nào nằm ngoài phạm vi AEAD?
- AAD được chuyển thành byte theo encoding/schema nào? Cả bên gửi và nhận có dùng **đúng cùng chuỗi byte** và thứ tự không?
- Có gọi `updateAAD` **trước** `update`/`doFinal` trên **cả hai phía**?
- IV có được tạo mới, unique theo khóa mỗi lần mã hóa? Key được lưu và truy xuất theo cơ chế nào?
- Chỉ công bố/sử dụng plaintext **sau** khi `doFinal` giải mã thành công?
- Header dùng để phân quyền, định tuyến hay chọn khóa có được kiểm tra lại sau khi tag hợp lệ?
- Có kiểm tra sai AAD, sai IV, đổi byte ciphertext/tag, cắt ngắn payload, sai version, replay không?

**Bài tập 1:** thêm một trường `contentType=application/json` vào AAD có độ dài được mã hóa rõ ràng; cho bên giải mã dùng cùng byte, rồi thử đổi `contentType` nhưng giữ nguyên ciphertext/tag để kiểm tra thất bại.

**Bài tập 2:** chuyển payload từ `doFinal(plaintext)` sang nhiều lần `update`, kết thúc bằng `doFinal`. Giữ `updateAAD` trước tất cả các lần `update` và so sánh kết quả round-trip; thử gọi `updateAAD` sau `update` để quan sát lỗi trạng thái trên provider.

**Bài tập 3:** tạo bản ghi có version, keyId, IV, AAD và ciphertext/tag. Xây dựng quy tắc serialization/canonicalization ổn định; test sau khi lưu/đọc qua file hoặc database. Không đưa khóa AES thật vào bài tập hay kho mã nguồn.

## 11. Tài liệu chính thức

- [Cipher — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `updateAAD`, `update`, `doFinal`, lưu ý GCM/CCM phải nạp toàn bộ AAD trước dữ liệu và kiểm tra tag.
- [GCMParameterSpec — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): IV và độ dài tag theo bit.
- [AEADBadTagException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/AEADBadTagException.html): lỗi tag xác thực không khớp khi giải mã AEAD.
- [Java Security Developer's Guide — Oracle](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): kiến trúc provider và cách dùng các engine mật mã, bao gồm chế độ AEAD.
