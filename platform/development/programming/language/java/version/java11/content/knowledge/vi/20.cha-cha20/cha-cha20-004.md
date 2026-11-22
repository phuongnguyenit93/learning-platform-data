# `ChaCha20ParameterSpec`: nonce 96 bit và block counter 32 bit trong Java 11+

## 1. Mục tiêu và vị trí của API

**`ChaCha20ParameterSpec`** là lớp trong package `javax.crypto.spec`, xuất hiện từ **Java 11** cùng hỗ trợ chuẩn ChaCha20 của Java Cryptography Architecture (JCA/JCE, JEP 329). Nó dùng để truyền **tham số khởi tạo** cho thuật toán mã hóa dòng `ChaCha20`:

```java
byte[] nonce = new byte[12];                 // 96 bit
new SecureRandom().nextBytes(nonce);
int initialCounter = 1;                     // block counter ban đầu

ChaCha20ParameterSpec spec =
        new ChaCha20ParameterSpec(nonce, initialCounter);
```

Đây là API **vẫn được hỗ trợ ở JDK hiện hành**, không phải API legacy. Nó **không chứa khóa bí mật**, không tự mã hóa dữ liệu và không thay thế `Cipher` hay `SecretKey`. Hai trường của nó là:

- **Nonce:** dãy **12 byte = 96 bit**, dùng để phân biệt các lần mã hóa với cùng khóa. **Không được lặp lại nonce với cùng một key** khi dùng ChaCha20 theo thiết kế thông thường.
- **Counter:** một giá trị `int` 32 bit, chỉ định **chỉ số khối dòng khóa đầu tiên** mà ChaCha20 sẽ dùng để mã hóa. Counter được tăng nội bộ mỗi khi thuật toán cần khối dòng khóa 64 byte tiếp theo.

ChaCha20 là một **stream cipher**: nó tạo keystream từ key + nonce + counter rồi XOR keystream với plaintext. Vì vậy phải phân biệt **mã hóa để giữ bí mật** với **xác thực để chống sửa dữ liệu**. ChaCha20 thuần **không tạo authentication tag**; khi phát triển giao thức/ứng dụng mới cần mã hóa và toàn vẹn, thông thường nên dùng **ChaCha20-Poly1305 (AEAD)**, không dùng ChaCha20 đơn lẻ. `ChaCha20ParameterSpec` chỉ dùng với **`Cipher.getInstance("ChaCha20")`**; ChaCha20-Poly1305 dùng tham số khác, giải thích ở mục 7.

## 2. Chữ ký API và các thành phần

Định nghĩa công khai:

```java
package javax.crypto.spec;

public final class ChaCha20ParameterSpec implements AlgorithmParameterSpec {
    public ChaCha20ParameterSpec(byte[] nonce, int counter);
    public byte[] getNonce();
    public int getCounter();
}
```

Đây là **chữ ký rút gọn để học**, không phải file Java cần tự chép để biên dịch.

| Thành phần | Kiểu | Vai trò |
| --- | --- | --- |
| `ChaCha20ParameterSpec(byte[] nonce, int counter)` | Constructor | Xác lập nonce 12 byte và counter 32 bit ban đầu |
| `getNonce()` | `byte[]` | Trả **bản sao mới** của nonce mỗi lần gọi |
| `getCounter()` | `int` | Trả đúng giá trị counter đã cấu hình |
| `AlgorithmParameterSpec` | Interface | Hợp đồng chung của tham số thuật toán cho `Cipher.init` |
| `Cipher.getInstance("ChaCha20")` | `Cipher` | Lấy một implementation ChaCha20 từ security provider |
| `Cipher.init(mode, key, spec)` | Phương thức | Cấp key, nonce và counter cho thao tác mã hóa hoặc giải mã |

**Kiểm tra đầu vào của constructor:** `nonce == null` gây `NullPointerException`; nonce có độ dài khác **12 byte** gây `IllegalArgumentException`. Constructor **không tự sinh nonce ngẫu nhiên**, không bảo đảm nonce chưa được sử dụng và không xác thực tính phù hợp của key: những trách nhiệm đó thuộc ứng dụng và `Cipher.init`.

Ví dụ truy cập tham số:

```java
byte[] n = new byte[12];
ChaCha20ParameterSpec p = new ChaCha20ParameterSpec(n, 1);

System.out.println(p.getNonce().length); // 12
System.out.println(p.getCounter());      // 1
```

Đoạn mã trên giả định import `javax.crypto.spec.ChaCha20ParameterSpec` và đặt trong method; **nonce toàn số 0 chỉ dùng minh họa cấu trúc**, không phải cách tạo nonce phù hợp cho nhiều message trong production.

### 2.1. Defensive copy của nonce

`ChaCha20ParameterSpec` **copy mảng nonce đầu vào** khi khởi tạo và `getNonce()` trả **mảng mới** mỗi lần. Điều này tránh việc người gọi sửa ngầm tham số đã lưu:

```java
byte[] original = new byte[12];
ChaCha20ParameterSpec p = new ChaCha20ParameterSpec(original, 1);

byte[] before = p.getNonce();
original[0] = 99;             // Không sửa nonce bên trong p.
byte[] extracted = p.getNonce();
extracted[1] = 88;            // Không sửa nonce bên trong p.

boolean unchanged = Arrays.equals(before, p.getNonce()); // true
```

Đoạn minh họa cần import `java.util.Arrays` và `ChaCha20ParameterSpec`. **Lưu ý:** defensive copy chỉ ngăn sửa mảng ngoài ý muốn, **không tự bảo đảm tính duy nhất** của nonce hay bảo vệ ciphertext khỏi bị chỉnh sửa.

## 3. Các khái niệm: key, nonce, counter và keystream

ChaCha20 IETF (RFC 8439) tạo các khối keystream dựa vào ba tham số:

| Tham số | Kích thước | Đặc điểm | Cần giữ bí mật? |
| --- | --- | --- | --- |
| **Key** | **256 bit / 32 byte** | Bí mật, dùng cho một hoặc nhiều message theo chính sách quản lý khóa | **Có** |
| **Nonce** | **96 bit / 12 byte** | Phải **duy nhất trên mỗi key**; có thể gửi kèm ciphertext để giải mã | Không, nhưng phải quản lý chính xác |
| **Initial block counter** | **32 bit** | Vị trí khởi tạo dòng khóa, tăng theo khối 64 byte | Không, nhưng phải đúng giá trị khi giải mã |
| **Keystream block** | **512 bit / 64 byte** | Output của hàm ChaCha20 block cho bộ (key,nonce,counter) cụ thể | Không được để lộ cùng plaintext theo cách làm lộ dòng khóa |
| **Plaintext/Ciphertext** | Số byte tùy dữ liệu và giới hạn giao thức | `ciphertext = plaintext XOR keystream` | Plaintext cần bảo mật theo ứng dụng |

Ví dụ một message 150 byte cần ba khối dòng khóa:

```text
key 256-bit, nonce 96-bit, initial counter = 1
          |
          +--> Block(counter=1) -> 64 byte keystream [0..63]
          +--> Block(counter=2) -> 64 byte keystream [64..127]
          +--> Block(counter=3) -> 64 byte keystream [128..149] (lấy 22 byte)
          |
plaintext[150 byte] XOR keystream[150 byte] => ciphertext[150 byte]
```

Counter đếm **khối 64 byte**, không phải số byte, số ký tự Java hay số lần gọi `Cipher.update(...)`. Nếu dữ liệu dài 150 byte, Java tự sử dụng các khối dòng khóa nối tiếp; **không phải tự tăng counter bằng vòng lặp** cho từng lời gọi `update`.

**Quan trọng:** cùng một bộ `(key, nonce, counter)` tạo cùng keystream. Việc dùng lại keystream với hai plaintext là lỗi bảo mật nghiêm trọng. Cụ thể, nếu có `C1 = P1 XOR K` và `C2 = P2 XOR K` thì `C1 XOR C2 = P1 XOR P2`, rò rỉ quan hệ giữa hai plaintext. Với stream cipher thuần, còn có tính **malleability**: kẻ tấn công sửa bit ciphertext sẽ ảnh hưởng bit plaintext sau giải mã mà không bị thuật toán thuần phát hiện.

## 4. Nonce: 12 byte, không cần bí mật nhưng bắt buộc khác nhau

### 4.1. Nonce có chức năng gì?

Nonce (number used once) đảm bảo cùng một key có thể tạo **những keystream khác nhau** cho những message khác nhau. IETF ChaCha20 dùng **96-bit nonce**, tức:

```java
byte[] nonce = new byte[12]; // 96 bit
new SecureRandom().nextBytes(nonce);
```

Đây là cách tạo **nonce ví dụ** khi dùng khóa mới trong chương trình demo. Một nonce ngẫu nhiên được sinh bằng `SecureRandom` **không có nghĩa bảo đảm toán học 100% không trùng** qua số lượng rất lớn message hoặc các process độc lập.

**Quy tắc cho production:** với **mỗi khóa**, phải có thiết kế đảm bảo **không tái sử dụng nonce**. Những lựa chọn thường gặp:

- Cấp **unique per-key nonce** bằng bộ đếm 96 bit hoặc một bố cục gồm *sender ID + message sequence number*, được lưu trạng thái bền vững và tránh đụng độ giữa nhiều producer.
- Phân vùng nonce space cho các instance/nút khác nhau nếu dùng chung key; tránh hai worker đều bắt đầu counter nonce từ 0.
- Nếu dùng random nonce, phải đánh giá **xác suất va chạm**, tổng số message mỗi key và chính sách thay key; không giả định random là bằng chứng tuyệt đối của uniqueness.
- **Không tái sử dụng nonce sau khi ứng dụng restart** nếu key vẫn như cũ; lưu bộ đếm và cập nhật atomically hoặc thay key theo kiến trúc được phê duyệt.

Nonce **không phải password, không phải key**. Nó có thể được lưu dưới dạng metadata bên cạnh ciphertext. Nhưng **sửa nonce** sẽ làm giải mã sai, nên với dữ liệu truyền/lưu thực tế cần định dạng **có xác thực** để phát hiện việc sửa nonce, ciphertext và metadata liên quan.

### 4.2. Lặp nonce với cùng key nguy hiểm thế nào?

Không nên nghĩ “chỉ cần thay counter là có thể dùng lại nonce cho message mới”. Vì mỗi message có thể dùng **nhiều block counter** và các khoảng counter rất dễ **chồng lấn**, thay counter ban đầu một chút vẫn có thể dùng lại keystream block.

Ví dụ sai về thiết kế:

```text
Message A: same key, same nonce, initialCounter=1, length=150 bytes
  -> sử dụng block 1,2,3

Message B: same key, same nonce, initialCounter=2, length=90 bytes
  -> sử dụng block 2,3

=> Các khối 2,3 bị tái sử dụng giữa hai message: KHÔNG AN TOÀN.
```

Vì vậy **counter khối không phải bộ cấp phát nonce độc lập**. Cách đơn giản và an toàn hơn là **mỗi message có một nonce mới duy nhất với cùng key**, còn counter khởi tạo theo protocol (thường 0 hoặc 1).

Nếu giao thức chuyên dụng cố phân bổ phạm vi counter trên một nonce, phải có chứng minh không trùng khối, giới hạn chiều dài và thiết kế được đánh giá mật mã. Không tự thiết kế kiểu này cho ứng dụng thông thường.

### 4.3. Khi giải mã, nonce lấy ở đâu?

Phía giải mã cần **đúng key, đúng nonce và đúng counter ban đầu** đã dùng khi mã hóa. Nonce và counter có thể lưu trong header/envelope dữ liệu (ví dụ cấu trúc `version | keyId | nonce | counter | ciphertext`). **Key không được lưu lộ thiên** trong cùng một payload.

Tuy nhiên, với ChaCha20 thuần, envelope chưa có authentication tag nên **không bảo đảm integrity**. Khuyến nghị thực tế là sử dụng **ChaCha20-Poly1305** với format có xác thực và quản lý nonce/key thích hợp (xem mục 7 và 11).

## 5. Block counter 32 bit: bắt đầu ở đâu và tại sao có giới hạn?

### 5.1. Counter là chỉ số khối, không phải số lượng message

Constructor nhận `int counter`:

```java
ChaCha20ParameterSpec p0 = new ChaCha20ParameterSpec(nonce, 0);
ChaCha20ParameterSpec p1 = new ChaCha20ParameterSpec(nonce, 1);
```

Trong RFC 8439, block counter **có thể khởi tạo 0 hoặc 1 tùy giao thức**. Với ChaCha20 thuần, cả hai là những giá trị block counter theo thuật toán. Với **ChaCha20-Poly1305**, khối counter 0 được dùng để tạo **one-time Poly1305 key**, còn luồng mã hóa payload bắt đầu ở counter 1, theo thiết kế AEAD. **Ứng dụng không tự đặt counter cho `ChaCha20-Poly1305`**.

Trong Java, `Cipher` tự tăng counter khi phát keystream block tiếp theo. Không sử dụng `counter` như **đồng hồ thời gian**, **sequence ID** hay **số lần gọi Cipher.doFinal()**. Đặc biệt, reinitialize một `Cipher` từ đầu với **cùng key,nonce,counter** cho các chunk khác nhau là **khởi động lại keystream**, không phải tiếp tục vị trí cũ.

### 5.2. Vì sao Java dùng `int` dù RFC nói 32-bit unsigned?

`ChaCha20ParameterSpec.getCounter()` có kiểu Java `int`, và Java `int` là **signed**. Nhưng state của thuật toán ChaCha20 có một **word 32 bit**; các bit được dùng như counter 32 bit. Vì vậy giá trị Java `-1` có biểu diễn bit `0xffffffff`, tương ứng **4.294.967.295 nếu đọc dưới dạng unsigned**:

```java
ChaCha20ParameterSpec p =
        new ChaCha20ParameterSpec(new byte[12], -1);

System.out.println(p.getCounter());                    // -1
System.out.println(Integer.toUnsignedString(p.getCounter())); // 4294967295
```

Đoạn này minh họa **biểu diễn bit**, không khuyến nghị khởi tạo counter gần điểm tràn. Bởi vì state counter chỉ có 32 bit, khi counter đến cuối khoảng thì không được tiếp tục dùng keystream theo kiểu **wrap về block đã sử dụng**.

### 5.3. Giới hạn block và không để counter tràn

Mỗi block ChaCha20 tạo **64 byte keystream** và counter chỉ có **2^32 trạng thái khác nhau**. Vì vậy upper bound theo lý thuyết khi dùng toàn bộ vùng counter là khoảng **256 GiB** keystream trên một key/nonce; thực tế số block còn lại phụ thuộc **initial counter** và các quy tắc của giao thức. Với initial counter = 1 và khối 0 dành cho chức năng khác, sẽ còn tối đa `2^32 - 1` block (gần 256 GiB).

Đây là **giới hạn thuật toán**, không phải khuyến nghị mã hóa một file vài trăm GiB bằng một nonce. Trong phần mềm thực tế:

- Chia dữ liệu thành các record/message có nonce riêng và giới hạn kích thước nghiêm ngặt.
- Thay key/rekey theo chính sách quản lý khóa.
- Không tự tin dựa vào exception “counter overflow” của một provider cụ thể: hãy **thiết kế không bao giờ đến gần giới hạn**.
- Không quay counter về 0 khi hết số; làm vậy tái sử dụng keystream.
- Không tự tạo nhiều `Cipher` có các khoảng counter chồng nhau cho cùng key/nonce.

`Cipher.update(...)` và `doFinal(...)` xử lý việc tiêu thụ keystream trong **một vòng đời Cipher**; không cần đếm số chunk để cập nhật counter bằng tay.

## 6. Tạo `Cipher.getInstance("ChaCha20")` từ `ChaCha20ParameterSpec`

Một luồng mã hóa/giải mã tối thiểu:

```java
// Key là SecretKey 256-bit cho ChaCha20.
// nonce là byte[12] duy nhất với key này.
// plaintext là byte[].
ChaCha20ParameterSpec parameters = new ChaCha20ParameterSpec(nonce, 1);

Cipher encrypt = Cipher.getInstance("ChaCha20");
encrypt.init(Cipher.ENCRYPT_MODE, key, parameters);
byte[] ciphertext = encrypt.doFinal(plaintext);

Cipher decrypt = Cipher.getInstance("ChaCha20");
decrypt.init(Cipher.DECRYPT_MODE, key, parameters);
byte[] recovered = decrypt.doFinal(ciphertext);
```

Đoạn trên là **mã minh họa**, cần import và khai báo `key`, `nonce`, `plaintext`. Mục 9 có một chương trình độc lập đầy đủ đã được kiểm thử.

Những quy tắc:

1. `key` phải là **khóa 256 bit** phù hợp thuật toán. Có thể sinh bằng `KeyGenerator.getInstance("ChaCha20")` hoặc byte ngẫu nhiên 32 byte được quản lý đúng với `SecretKeySpec(bytes, "ChaCha20")`.
2. `nonce` là **12 byte**; không dùng giá trị cố định hay lặp lại cho các lần **mã hóa mới** dưới cùng key.
3. Khi **giải mã ciphertext đã có**, phải tái sử dụng **đúng nonce và counter** của lần mã hóa đó. Đây không phải việc *encrypt một message khác*, nên không vi phạm quy tắc uniqueness cho encrypt.
4. `doFinal` trả byte[] ciphertext có **cùng độ dài** với plaintext trong ChaCha20 thuần, không thêm padding hay authentication tag.
5. `Cipher` **không được giả định thread-safe**. Tạo instance riêng cho mỗi hoạt động, không chia sẻ cùng một Cipher mutable cho các thread.
6. Có thể dùng `Cipher.update` để mã hóa dạng streaming, nhưng phải duy trì đúng **cùng vòng đời Cipher** và quản lý độ dài/counter; không `init` lại với tuple cũ cho từng chunk.
7. **Không dùng ChaCha20 thuần cho message không được xác thực** trong ứng dụng mới; đọc mục tiếp theo trước khi lựa chọn thuật toán production.

### 6.1. Chuyện gì xảy ra khi dùng sai nonce hoặc counter để giải mã?

Khi giải mã với cùng key nhưng **nonce hoặc counter sai**, ChaCha20 thuần sẽ XOR ciphertext với **keystream khác**, tạo kết quả sai. Vì không có tag, nó **không biết kết quả vừa tạo là dữ liệu rác hoặc bị chỉnh sửa**. `Cipher.doFinal` có thể thành công mà plaintext sai hoàn toàn.

Đây là điểm rất khác so với một **AEAD cipher**: khi tag không hợp lệ, giải mã AEAD từ chối trả plaintext như thể đã xác thực thành công.

## 7. Đừng nhầm `ChaCha20ParameterSpec` với tham số ChaCha20-Poly1305

Java 11 hỗ trợ cả hai thuật toán:

| Tiêu chí | `ChaCha20` thuần | `ChaCha20-Poly1305` |
| --- | --- | --- |
| `Cipher.getInstance` | `"ChaCha20"` | `"ChaCha20-Poly1305"` |
| Cấp nonce | `ChaCha20ParameterSpec` | **`IvParameterSpec`** có IV 12 byte |
| Counter | Ứng dụng chọn initial counter thông qua `ChaCha20ParameterSpec` | Thuật toán quản lý counter nội bộ, **không truyền counter riêng** |
| Confidentiality | Có | Có |
| Integrity/authentication | **Không có** | **Có**, bằng Poly1305 authentication tag |
| AAD | Không có authenticated AAD | Hỗ trợ `Cipher.updateAAD(...)` |
| Bị sửa ciphertext | Có thể giải mã thành dữ liệu sai **không báo lỗi** | Giải mã từ chối với lỗi xác thực, thường `AEADBadTagException` |
| Chiều dài ciphertext | Bằng chiều dài plaintext | Thêm **16 byte tag** (trong format JCE thông dụng) |
| Ưu tiên ứng dụng mới | Chỉ khi protocol đã cung cấp integrity độc lập, được thiết kế/đánh giá đúng | **Thường nên ưu tiên** cho mã hóa dữ liệu cần bảo mật và toàn vẹn |

Cú pháp ChaCha20-Poly1305:

```java
byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);

Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
cipher.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
cipher.updateAAD(aad); // Nếu có metadata AAD, truyền trước dữ liệu.
byte[] sealed = cipher.doFinal(plaintext);
```

Đây là ví dụ minh họa, `key` phải là khóa 256-bit đúng và `aad` là `byte[]` được thỏa thuận; mã đầy đủ ở mục 9.

**Quan trọng:** không truyền `ChaCha20ParameterSpec` vào `Cipher.getInstance("ChaCha20-Poly1305")` rồi chờ provider nhận counter; với SunJCE, AEAD mode dùng **`IvParameterSpec`**. Không chuyển ngược sang `GCMParameterSpec` — lớp này dành cho GCM, không phải ChaCha20-Poly1305.

### 7.1. Counter trong ChaCha20-Poly1305

Theo RFC 8439, AEAD ChaCha20-Poly1305 sử dụng block ChaCha20 với **counter=0** để tạo khóa Poly1305 một lần, còn mã hóa payload bắt đầu từ **counter=1**. Đây là chi tiết **nội bộ của cấu trúc AEAD**, không phải chỗ người dùng truyền `ChaCha20ParameterSpec(nonce, 1)`.

Nếu nonce AEAD lặp lại với cùng key, mức độ rủi ro đặc biệt nghiêm trọng: tái sử dụng keystream và làm suy yếu cơ chế xác thực. Đừng dùng `ChaCha20-Poly1305` làm lý do nới lỏng yêu cầu nonce unique.

### 7.2. AAD là gì?

`Cipher.updateAAD(...)` nhận **Additional Authenticated Data**: dữ liệu được xác thực cùng ciphertext nhưng không mã hóa vào phần nội dung (ví dụ version, key ID, sequence number, message type). Bên giải mã phải cung cấp **cùng AAD byte-for-byte** trước `doFinal`. Sửa AAD, nonce hoặc ciphertext khiến xác thực tag thất bại với xác suất áp đảo.

Đối với ứng dụng thực tế, định dạng hóa rõ ràng các thành phần của packet/envelope để không có **ambiguity** giữa các trường. Không truyền một đối tượng Java tùy ý rồi giả định hai phía có cùng serialization.

## 8. Nguyên tắc an toàn với nonce: quản lý vòng đời, không tái sử dụng

**Quy tắc cốt lõi: unique (key, nonce) cho từng lần encrypt.** Counter **không** thay thế nonce.

Một envelope minh họa (không phải chuẩn serialize có sẵn của Java):

```text
version | algorithm-id | key-id | nonce[12] | ciphertext | tag[16]
```

Ứng dụng gửi/lưu **nonce không bí mật**, còn key nằm trong keystore/KMS hoặc hệ thống quản lý bí mật; **đừng lưu key plaintext trong packet**. Các header có ý nghĩa cần được đưa vào AAD hoặc cơ chế xác thực toàn bộ envelope để kẻ tấn công không tự sửa version, thuật toán, key ID hay message type mà không bị phát hiện.

**Lưu ý nonce generator:**

- Một **counter/sequence bền vững** không lặp trên từng key thường dễ chứng minh uniqueness hơn cách tạo random nonce không kiểm soát, nhất là khi gửi số lượng rất lớn message.
- Cần phân vùng nonce giữa **nhiều server/producer** dùng chung key và xử lý restart/crash/retry; không để hai process phát cùng một nonce.
- Trước khi encrypt lại một message sau retry, phải xác định protocol có cho phép **gửi lại nguyên ciphertext** không. Nếu **mã hóa lại một payload**, cần nonce mới theo contract; không mặc định giữ nonce cũ là hợp lệ.
- Với **random 96-bit**, phải áp dụng giới hạn số lần mã hóa trên mỗi key và đánh giá xác suất collision (birthday bound). Không khẳng định “SecureRandom làm trùng nonce là bất khả thi”.
- Thay key định kỳ theo lưu lượng/tuổi khóa và tuân thủ chính sách mã hóa; không dùng nonce uniqueness để thay thế key management.
- Nếu chia dữ liệu lớn thành records, mỗi record phải có nonce/sequence được cấp phát chính xác, authentication tag riêng và quy tắc chống phát lại khi cần. Mã hóa ChaCha20 thuần liên tục cho dữ liệu không giới hạn không phải kiến trúc ứng dụng khuyên dùng.
- Không dùng mật khẩu người dùng trực tiếp làm khóa ChaCha20; nếu source là password, cần KDF hiện đại có salt/work factor phù hợp, hoặc tốt hơn lấy khóa ngẫu nhiên 256-bit từ KMS.

## 9. Chương trình Java 11 hoàn chỉnh: nonce, counter, integrity và AEAD

Ví dụ sau chạy **hoàn toàn trong bộ nhớ**, không cần network hay dependency ngoài JDK. Nó thực hiện:

1. Sinh key ngẫu nhiên 256 bit và nonce ngẫu nhiên 12 byte cho ví dụ ChaCha20 thuần.
2. Tạo `ChaCha20ParameterSpec(nonce, 1)`, mã hóa rồi giải mã bằng đúng tham số.
3. Chứng minh constructor và getter **defensive-copy nonce**.
4. Thử giải mã với **counter sai**: không có authentication tag nên dữ liệu được giải mã nhưng **không giống plaintext**.
5. Sửa một byte ciphertext ChaCha20 thuần: **không có lỗi xác thực**.
6. Bắt `IllegalArgumentException` khi nonce dài 11 byte.
7. Hiển thị `int -1` dưới dạng unsigned 32 bit để thấy biểu diễn counter.
8. Dùng **khóa mới và nonce khác** cho `ChaCha20-Poly1305`, mã hóa có AAD và chứng minh tag bị sửa sẽ khiến `AEADBadTagException`.

**Tạo file `ChaCha20NonceCounterDemo.java`:**

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class ChaCha20NonceCounterDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    static SecretKeySpec freshKey() {
        byte[] keyBytes = new byte[32];
        RANDOM.nextBytes(keyBytes);
        return new SecretKeySpec(keyBytes, "ChaCha20");
    }

    static byte[] freshNonce() {
        byte[] nonce = new byte[12];
        RANDOM.nextBytes(nonce);
        return nonce;
    }

    static byte[] rawCipher(int mode, SecretKeySpec key,
                            ChaCha20ParameterSpec spec, byte[] input)
            throws Exception {
        Cipher cipher = Cipher.getInstance("ChaCha20");
        cipher.init(mode, key, spec);
        return cipher.doFinal(input);
    }

    public static void main(String[] args) throws Exception {
        SecretKeySpec key = freshKey();
        byte[] nonce = freshNonce();
        ChaCha20ParameterSpec params = new ChaCha20ParameterSpec(nonce, 1);
        byte[] message = "ChaCha20 trong Java 11: Xin chào!"
                .getBytes(StandardCharsets.UTF_8);

        System.out.println("nonce bytes: " + params.getNonce().length);
        System.out.println("initial counter: " + params.getCounter());

        byte[] cipherText = rawCipher(Cipher.ENCRYPT_MODE, key, params, message);
        byte[] recovered = rawCipher(Cipher.DECRYPT_MODE, key, params, cipherText);
        System.out.println("ciphertext length equals plaintext: " +
                (cipherText.length == message.length));
        System.out.println("raw ChaCha20 round-trip: " +
                Arrays.equals(message, recovered));

        byte[] saved = params.getNonce();
        nonce[0] ^= 1; // Mutate the constructor's original input array.
        System.out.println("constructor copied nonce: " +
                Arrays.equals(saved, params.getNonce()));
        byte[] extracted = params.getNonce();
        extracted[1] ^= 1; // Mutate a returned array.
        System.out.println("getter copied nonce: " +
                Arrays.equals(saved, params.getNonce()));

        ChaCha20ParameterSpec wrongCounter =
                new ChaCha20ParameterSpec(params.getNonce(), 2);
        byte[] wrong = rawCipher(Cipher.DECRYPT_MODE,
                key, wrongCounter, cipherText);
        System.out.println("wrong counter gives original: " +
                Arrays.equals(message, wrong));

        byte[] tampered = cipherText.clone();
        tampered[0] ^= 1;
        byte[] rawTamperResult = rawCipher(Cipher.DECRYPT_MODE,
                key, params, tampered);
        System.out.println("raw tampering raised exception: false");
        System.out.println("raw tampering changed plaintext: " +
                !Arrays.equals(message, rawTamperResult));

        try {
            new ChaCha20ParameterSpec(new byte[11], 1);
            System.out.println("invalid nonce: unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid nonce: IllegalArgumentException");
        }

        ChaCha20ParameterSpec unsigned =
                new ChaCha20ParameterSpec(new byte[12], -1);
        System.out.println("counter unsigned example: " +
                Integer.toUnsignedString(unsigned.getCounter()));

        SecretKeySpec aeadKey = freshKey();
        byte[] aeadNonce = freshNonce();
        byte[] aad = "meta:v1".getBytes(StandardCharsets.UTF_8);

        Cipher aeadEncrypt = Cipher.getInstance("ChaCha20-Poly1305");
        aeadEncrypt.init(Cipher.ENCRYPT_MODE, aeadKey,
                new IvParameterSpec(aeadNonce));
        aeadEncrypt.updateAAD(aad);
        byte[] authenticated = aeadEncrypt.doFinal(message);

        Cipher aeadDecrypt = Cipher.getInstance("ChaCha20-Poly1305");
        aeadDecrypt.init(Cipher.DECRYPT_MODE, aeadKey,
                new IvParameterSpec(aeadNonce));
        aeadDecrypt.updateAAD(aad);
        System.out.println("AEAD round-trip: " +
                Arrays.equals(message, aeadDecrypt.doFinal(authenticated)));
        System.out.println("AEAD tag adds 16 bytes: " +
                (authenticated.length == message.length + 16));

        authenticated[authenticated.length - 1] ^= 1;
        Cipher corrupted = Cipher.getInstance("ChaCha20-Poly1305");
        corrupted.init(Cipher.DECRYPT_MODE, aeadKey,
                new IvParameterSpec(aeadNonce));
        corrupted.updateAAD(aad);
        try {
            corrupted.doFinal(authenticated);
            System.out.println("AEAD tampering: unexpected");
        } catch (AEADBadTagException expected) {
            System.out.println("AEAD tampering: AEADBadTagException");
        }
    }
}
```

**Lệnh biên dịch và chạy bằng JDK 11 trở lên:**

```bash
javac --release 11 -encoding UTF-8 ChaCha20NonceCounterDemo.java
java ChaCha20NonceCounterDemo
```

**Đầu ra đúng đã kiểm thử** (không in key hoặc nonce bí mật/metadata thực tế):

```text
nonce bytes: 12
initial counter: 1
ciphertext length equals plaintext: true
raw ChaCha20 round-trip: true
constructor copied nonce: true
getter copied nonce: true
wrong counter gives original: false
raw tampering raised exception: false
raw tampering changed plaintext: true
invalid nonce: IllegalArgumentException
counter unsigned example: 4294967295
AEAD round-trip: true
AEAD tag adds 16 bytes: true
AEAD tampering: AEADBadTagException
```

### 9.1. Tại sao kết quả ổn định dù key/nonce random?

Chương trình không in giá trị ciphertext ngẫu nhiên; nó chỉ in những **bất biến logic** như độ dài, việc round-trip thành công, và thông báo lỗi xác thực. Mỗi lần chạy với key/nonce mới vẫn có thể kiểm thử cùng hành vi.

- **`nonce bytes: 12`**: đúng kích thước constructor yêu cầu.
- **`raw ChaCha20 round-trip: true`**: decryption dùng cùng key/nonce/counter và trả lại đúng plaintext.
- **`constructor copied nonce: true`**, **`getter copied nonce: true`**: sửa mảng ở ngoài không thay tham số đã lưu trong `ChaCha20ParameterSpec`.
- **`wrong counter gives original: false`**: counter=2 tạo keystream khác counter=1, vì thế plaintext không khôi phục. Không có cơ chế “tự đọc counter” từ ciphertext.
- **`raw tampering raised exception: false`**: trong ví dụ decrypt ChaCha20 thuần đã chạy thành công trên ciphertext bị sửa; dòng này được in sau `doFinal(...)` thành công. Một thay đổi bit làm plaintext sai nhưng không có authentication tag để cảnh báo.
- **`invalid nonce: IllegalArgumentException`**: nonce 11 byte bị từ chối ngay khi tạo spec.
- **`counter unsigned example: 4294967295`**: biểu diễn unsigned của int -1; **không dùng giá trị này để encrypt một message lớn**.
- **`AEAD round-trip: true`**: khác ChaCha20 thuần, ChaCha20-Poly1305 xác thực tag khi giải mã.
- **`AEAD tag adds 16 bytes: true`**: JCE trả ciphertext kèm 16-byte Poly1305 tag.
- **`AEAD tampering: AEADBadTagException`**: sửa 1 byte tag khiến việc giải mã bị từ chối. Không nên chấp nhận hoặc sử dụng plaintext nếu xác thực thất bại.

**Lưu ý an toàn:** đây là bài tập mật mã cục bộ. Trong production cần một format versioned, lưu nonce/key ID, chống lặp nonce giữa nhiều process, bảo vệ khóa và giới hạn message; không lấy trực tiếp demo này làm một giao thức bảo mật hoàn chỉnh.

## 10. Đối chiếu với test vector chuẩn RFC 8439

Một cách kiểm tra tính tương thích mà **không phụ thuộc random key/nonce** là dùng vector ChaCha20 từ **RFC 8439 `2.3.2**. Với:

- Key = 32 byte tăng dần `00 01 02 ... 1f`.
- Nonce = `00 00 00 09 00 00 00 4a 00 00 00 00`.
- Initial counter = **1**.
- Đầu vào = **64 byte 0**.

Vì `ciphertext = plaintext XOR keystream`, khi plaintext toàn số 0, 64 byte output chính là một block keystream. **16 byte đầu** theo RFC là `10 f1 e7 e4 d1 3b 59 15 50 0f dd 1f a3 20 71 c4`.

Tạo file **`ChaCha20RfcVector.java`**:

```java
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.SecretKeySpec;
import javax.crypto.spec.ChaCha20ParameterSpec;

public class ChaCha20RfcVector {
    private static byte[] hex(String s) {
        byte[] bytes = new byte[s.length() / 2];
        for (int i = 0; i < bytes.length; i++) {
            bytes[i] = (byte) Integer.parseInt(
                    s.substring(2*i, 2*i+2), 16);
        }
        return bytes;
    }

    public static void main(String[] args) throws Exception {
        byte[] key = new byte[32];
        for (int i = 0; i < 32; i++) key[i] = (byte)i;

        byte[] nonce = hex("000000090000004a00000000");
        Cipher cipher = Cipher.getInstance("ChaCha20");
        cipher.init(Cipher.ENCRYPT_MODE,
                new SecretKeySpec(key, "ChaCha20"),
                new ChaCha20ParameterSpec(nonce, 1));
        byte[] output = cipher.doFinal(new byte[64]);
        byte[] prefix = Arrays.copyOf(output, 16);

        System.out.println("RFC 8439 block vector matches: " +
                Arrays.equals(prefix,
                        hex("10f1e7e4d13b5915500fdd1fa32071c4")));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 11 -encoding UTF-8 ChaCha20RfcVector.java
java ChaCha20RfcVector
```

**Đầu ra đã kiểm thử:**

```text
RFC 8439 block vector matches: true
```

Đây là **test vector công khai, chỉ dùng để kiểm thử**. **Không bao giờ dùng key/nonce cố định này để bảo vệ dữ liệu thật**. Test vector giúp xác nhận cách Java triển khai **key, nonce, initial counter và thứ tự byte** theo RFC; nó không chứng minh protocol ứng dụng đã quản lý nonce, integrity hoặc secret storage an toàn.

## 11. Lỗi thường gặp: từ compile-time đến lỗi bảo mật

| Vấn đề | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `IllegalArgumentException` khi tạo spec | Nonce không phải đúng **12 byte** | Tạo `byte[12]`; không dùng `String.length()==12` làm điều kiện đủ |
| `NullPointerException` khi tạo spec | `nonce == null` | Cấp byte array hợp lệ trước |
| `InvalidKeyException` ở `Cipher.init` | Key sai thuật toán/độ dài, ví dụ không phải ChaCha20 256-bit | Tạo key 32 byte từ CSPRNG hoặc KeyGenerator hỗ trợ |
| `InvalidAlgorithmParameterException` ở `Cipher.init` | Truyền sai loại spec cho algorithm | `ChaCha20` dùng `ChaCha20ParameterSpec`; `ChaCha20-Poly1305` dùng `IvParameterSpec` |
| `NoSuchAlgorithmException` / `NoSuchPaddingException` | Provider/runtime không hỗ trợ algorithm được yêu cầu | Kiểm tra JDK/provider Java 11+ và cấu hình security provider |
| Ciphertext giải ra dữ liệu rác nhưng không ném exception | Sai key/nonce/counter hoặc ciphertext bị sửa; ChaCha20 thuần không có tag | Đối chiếu tham số; dùng **AEAD** để xác thực dữ liệu |
| `AEADBadTagException` | Key/nonce/AAD/tag/ciphertext không khớp hoặc dữ liệu bị sửa | Xem lỗi là **authentication failure**, không trả plaintext, không thử tắt xác thực |
| Tái dùng một nonce sau restart | Bộ đếm nonce không được lưu hoặc key được giữ nguyên | Lưu sequence bền vững, phân vùng writers, rotate key |
| Dùng counter=2 để “né” trùng nonce với message khác | Các khoảng block có thể chồng lấn dù starting counter khác | Cấp **nonce mới duy nhất** cho mỗi message |
| `getNonce()` không phản ánh sửa mảng `nonce` ban đầu | Spec sao chép mảng | Đây là hành vi **đúng**, không phải lỗi |
| `String.length()` không trùng ciphertext byte length | String UTF-16 code units khác byte UTF-8 | Mã hóa `String` bằng `StandardCharsets.UTF_8` rồi mã hóa byte[] |
| Tự tăng counter sau mỗi `update` | Counter đếm **64-byte blocks**, không phải số lần update | Để Cipher duy trì state xuyên suốt các update |
| Counter tiến tới 32-bit limit | Có nguy cơ exhaustion/wrap và tái sử dụng keystream | Giới hạn size, tách message và nonce, rekey trước |
| Dùng `Cipher.getInstance("ChaCha20")` cho dữ liệu có thể bị kẻ xấu chỉnh sửa | **Không có authentication tag** | Dùng `ChaCha20-Poly1305` hoặc giao thức đã chứng minh integrity |
| Chia sẻ một `Cipher` cho nhiều thread | Cipher có trạng thái stream nội bộ | Tạo instance riêng, không dùng chung không đồng bộ |
| Log key/nonce/ciphertext tùy tiện | Rò rỉ key/metadata hoặc dữ liệu nhạy cảm | Không log khóa, bảo vệ metadata và hạn chế logging |
| Thấy đầu ra thử nghiệm khác nhau mỗi lần | Key/nonce dùng `SecureRandom` | Test logic round-trip; dùng vector RFC để kiểm chứng deterministic |

### 11.1. Sai counter thường không tạo exception

Đừng viết unit test chỉ assert không ném lỗi rồi kết luận decryption đúng. ChaCha20 thuần có thể trả byte[] bất kỳ với cùng chiều dài đầu vào; **dữ liệu plaintext sai cũng không làm `doFinal` báo lỗi**.

Để kiểm thử đúng, so sánh recovered plaintext với expected bằng `Arrays.equals(...)`. Trong ứng dụng thực tế cần **xác thực toàn vẹn** bằng AEAD để không chấp nhận kết quả bị thay đổi.

### 11.2. Lỗi nonce trong xử lý byte và charset

Nonce là **mảng byte**, không phải chuỗi Unicode. `"123456789012".getBytes(UTF_8)` có thể dài 12 byte trong một trường hợp đơn giản nhưng **không bảo đảm uniqueness** và chỉ là byte text dễ đoán. Với ký tự tiếng Việt, số byte UTF-8 còn có thể khác số ký tự Java. Không tạo nonce bằng cách cắt chuỗi ngày giờ, username hoặc timestamp thiếu cơ chế chống trùng.

Nếu lưu nonce trong Base64/hex, phải **decode lại chính xác 12 byte** trước khi tạo spec. `getNonce()` trả bytes, không phải một chuỗi có sẵn. Nếu serialize message, nêu rõ thứ tự byte và format version để hai phía đọc giống nhau.

### 11.3. Phân biệt kiểm tra định dạng và bảo mật

`nonce.length == 12` chỉ đảm bảo **độ dài**. `getCounter() == 1` chỉ đảm bảo **giá trị counter**. `Cipher.init(...)` thành công chỉ đảm bảo provider chấp nhận tham số. Không có bước nào trong đó **chứng minh nonce chưa lặp**, key đủ bí mật, ciphertext chưa bị sửa, hoặc attacker không thể replay.

Do đó, cần security review ở **mức protocol**, không chỉ test từng lời gọi Java API.

## 12. Thiết kế lưu trữ và truyền ciphertext an toàn

Nếu ứng dụng cần mã hóa một message rồi lưu hoặc gửi cho hệ thống khác, một thiết kế thực tế nên xác định **protocol envelope** rõ ràng:

```text
header:
  version       : 1 byte (ví dụ)
  algorithmId   : 1 byte (ví dụ "ChaCha20-Poly1305")
  keyId         : ID tham chiếu đến key trong KMS/keystore
  nonce         : 12 byte, unique với keyId/key material

body:
  ciphertext    : byte[] đã mã hóa
  tag           : 16 byte xác thực (theo định dạng AEAD được chọn)
```

Đây là **thiết kế minh họa**, không phải format chuẩn được Java tự sinh. Cần làm rõ byte order, framing, độ dài field và thứ tự AAD để tránh ambiguity. Với `Cipher.getInstance("ChaCha20-Poly1305")`, JCE có thể trả byte[] dạng **ciphertext nối tag**; nếu format ngoài tách tag riêng thì ứng dụng phải tách/ghép theo contract và **không bỏ tag**.

Phía nhận cần xác định:

1. Thuật toán và version có được cho phép không?
2. Lấy đúng **key** từ KMS bằng `keyId`; không chấp nhận chuyển thuật toán/key theo dữ liệu không xác thực mà không có chính sách.
3. Đọc **nonce đúng 12 byte** và thiết lập `IvParameterSpec` cho AEAD.
4. Cung cấp **AAD cùng byte** mà bên gửi đã dùng.
5. Gọi `doFinal` và **chỉ sử dụng plaintext sau khi tag được xác thực thành công**.
6. Xử lý `AEADBadTagException` như lỗi an toàn, không tự retry với plaintext/khoá/ngôn ngữ khác vô hạn để “thử giải mã”.

**Chống replay** là bài toán ngoài confidentiality/integrity: AEAD tag hợp lệ không chứng minh message chưa được gửi trước đó. Nếu giao thức có yêu cầu chống replay, cần sequence number/timestamp/window được **xác thực** và trạng thái chống trùng.

## 13. Khi nào giữ ChaCha20 thuần và khi nào nên chọn AEAD?

**`ChaCha20ParameterSpec` không lỗi thời** và vẫn có các ứng dụng hợp lệ: đọc/ghi format có sẵn, thực hiện test vector, tương tác với giao thức đã chỉ định một **cơ chế xác thực riêng** và được kiểm chứng. Điều cần tránh là sử dụng **ChaCha20 thuần như một giải pháp tự đầy đủ về confidentiality + integrity**.

Đối với **ứng dụng mới cần mã hóa message**, thường ưu tiên:

- **ChaCha20-Poly1305 (AEAD)** theo RFC 8439, khi môi trường hỗ trợ, key/nonce management và policy phù hợp.
- Hoặc **AES-GCM (AEAD)** nếu giao thức, hardware/platform và chính sách yêu cầu thuật toán đó.
- Trong cả hai trường hợp, **nonce/IV uniqueness** với cùng key, quản lý khóa và xác thực AAD/ciphertext vẫn quan trọng. **Không tự thiết kế crypto protocol** mà thiếu review.

**Không dùng RC4 hoặc thuật toán mã hóa dòng đã yếu** để thay thế, cũng không dùng “encrypt rồi tự thêm CRC32/hash thường” như MAC. CRC32 và hash không khóa **không cung cấp message authentication**. Nếu buộc dùng encryption-only primitive theo protocol cụ thể, phải có cơ chế authentication được xác định độc lập và phân tích đúng về thứ tự Encrypt-then-MAC, key separation, chống replay và framing.

## 14. Bài tập tự kiểm tra

**Câu 1.** `ChaCha20ParameterSpec` lưu những trường nào?  
**Đáp án:** **Nonce 12 byte** và **initial block counter 32 bit**; không chứa key.

**Câu 2.** Counter tăng sau mỗi byte, mỗi `Cipher.update` hay mỗi block?  
**Đáp án:** Theo **block keystream 64 byte**. Cipher quản lý block counter nội bộ khi xử lý input.

**Câu 3.** Vì sao hai lần encrypt dùng cùng key/nonce/counter nguy hiểm?  
**Đáp án:** Tái sử dụng keystream; `C1 XOR C2 = P1 XOR P2`, có thể lộ dữ liệu. Thay counter cho message mới **không bảo đảm không overlap**.

**Câu 4.** Nonce có cần giấu khỏi người nhận ciphertext không?  
**Đáp án:** Không; nó không phải secret. Nhưng phải **duy nhất với key** và được xử lý đúng trong định dạng có integrity.

**Câu 5.** Khi giải mã có dùng nonce mới ngẫu nhiên được không?  
**Đáp án:** Không. Phải dùng **đúng nonce và initial counter** của ciphertext đã mã hóa.

**Câu 6.** `getNonce()` có trả tham chiếu vào mảng lưu bên trong không?  
**Đáp án:** Không. Javadoc quy định trả **mảng mới mỗi lần**, và constructor cũng giữ bản sao nonce.

**Câu 7.** `ChaCha20ParameterSpec(new byte[8], 1)` gây lỗi gì?  
**Đáp án:** `IllegalArgumentException` do nonce phải dài 12 byte.

**Câu 8.** `getCounter()` trả `-1` có nghĩa thuật toán dùng counter âm không?  
**Đáp án:** Java `int` mang biểu diễn bit signed, nhưng state counter có 32 bit; mẫu bit `0xffffffff` tương ứng `4294967295` nếu đọc unsigned. Không nên chọn gần điểm overflow.

**Câu 9.** `ChaCha20-Poly1305` có dùng `ChaCha20ParameterSpec(nonce, 1)` không?  
**Đáp án:** Với JDK Java 11 SunJCE, **không**. Dùng `IvParameterSpec(nonce)`; counter AEAD được thuật toán quản lý nội bộ.

**Câu 10.** Sửa 1 byte ciphertext ChaCha20 thuần có nhất thiết ném exception không?  
**Đáp án:** Không. Không có authentication tag để nhận ra sửa đổi; phải dùng AEAD/cơ chế xác thực phù hợp.

**Câu 11.** Vì sao chương trình RFC vector có thể dùng key/nonce cố định?  
**Đáp án:** Vì đó là **test vector công khai để kiểm tra thuật toán**, không dùng mã hóa thông tin bí mật hoặc dữ liệu production.

**Câu 12.** Nếu cần mã hóa và toàn vẹn cho message ứng dụng mới, nên dùng gì?  
**Đáp án:** Thường chọn **ChaCha20-Poly1305** hoặc AEAD hiện đại khác theo policy, với key/nonce unique, AAD chính xác, lưu tag và xử lý lỗi xác thực.

## 15. Ghi nhớ và tài liệu nguồn

- **`ChaCha20ParameterSpec(byte[12] nonce, int counter)`** có từ Java 11 và còn dùng hiện nay.
- **Nonce = 96 bit**, **counter = 32 bit**, **keystream block = 64 byte**, **key = 256 bit**.
- Nonce phải **duy nhất với mỗi key khi encrypt**; counter chỉ định **khối đầu** và được Cipher tăng theo từng block.
- `getNonce()` và constructor bảo vệ nonce bằng **defensive copy**, nhưng **không tự bảo đảm uniqueness**.
- ChaCha20 thuần **chỉ mã hóa**; sai counter/nonce hoặc ciphertext bị sửa có thể tạo plaintext sai mà không ném lỗi.
- **`ChaCha20-Poly1305` dùng `IvParameterSpec`**, có authentication tag/AAD; counter 0/1 là chi tiết cấu trúc AEAD, không truyền bằng `ChaCha20ParameterSpec`.
- **Chọn AEAD cho ứng dụng mới**; không tái sử dụng (key,nonce), không để counter wrap, không log/lưu key plaintext, có quản lý vòng đời khóa và thử nghiệm lỗi xác thực.
- Ví dụ đã kiểm chứng `javac --release 11`, mã hóa/giải mã, defensive copy, counter sai, tampering và RFC 8439 vector.

**Tài liệu chính thức còn áp dụng:** [Oracle Java 11 — ChaCha20ParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html); [Oracle Java 25 — ChaCha20ParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html); [Oracle Java 11 — Cipher](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/Cipher.html); [Oracle Java 11 — IvParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/IvParameterSpec.html); [OpenJDK JEP 329 — ChaCha20 and Poly1305](https://openjdk.org/jeps/329); [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols](https://www.rfc-editor.org/rfc/rfc8439.html); [Oracle Java SE 11 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/11/docs/specs/security/standard-names.html).