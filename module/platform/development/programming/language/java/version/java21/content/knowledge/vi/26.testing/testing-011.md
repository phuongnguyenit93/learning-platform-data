# Kiểm thử KEM bằng đối chiếu shared secret và xử lý encapsulation không hợp lệ

## Mục tiêu

Khi dùng Key Encapsulation Mechanism (KEM), test quan trọng nhất là xác nhận bên gửi và bên nhận tạo được cùng shared secret từ một key pair và encapsulation message tương ứng. Bên cạnh luồng thành công, ứng dụng cần kiểm tra cách xử lý input encapsulation sai định dạng, key không phù hợp và lỗi do security provider.

Java 21 cung cấp API `javax.crypto.KEM`. API này ủy quyền thuật toán cụ thể cho security provider, vì vậy test cần xác định rõ runtime/provider hỗ trợ thuật toán và key type nào. Bài học sử dụng DHKEM với X25519 và JUnit Jupiter để kiểm tra round-trip, đối chiếu secret, xử lý encapsulation có độ dài không hợp lệ và tránh giả định sai rằng mọi dữ liệu bị thay đổi đều phải ném exception.

## 1. Các thuộc tính cần kiểm thử

Một bộ test KEM nên xác nhận các hành vi sau:

- Bên gửi có thể encapsulate bằng public key của bên nhận.
- Bên nhận có thể decapsulate message bằng private key tương ứng.
- Shared secret phía gửi và phía nhận có cùng key material.
- Encapsulation message được chuyển nguyên vẹn qua ranh giới truyền nhận.
- Input không đúng cấu trúc theo thuật toán được xử lý như lỗi, không làm ứng dụng tiếp tục sử dụng key không hợp lệ.
- Provider thực tế hỗ trợ algorithm, key type và parameters được chọn.
- Secret và private key không bị ghi log hoặc đưa vào assertion output.

Không nên kiểm thử bằng cách mong đợi một shared secret cố định. KEM sử dụng randomness, vì vậy mỗi lần encapsulate hợp lệ thường tạo secret và encapsulation message mới. Test nên kiểm tra quan hệ giữa hai phía trong cùng một lần chạy.

## 2. Xác định môi trường test và provider

Ví dụ trong bài dùng:

- Java 21.
- KEM algorithm `DHKEM`.
- Key pair algorithm `X25519`.
- JUnit Jupiter.

Oracle JDK 21 cung cấp DHKEM qua provider `SunJCE` và hỗ trợ X25519. Các JDK distribution hoặc provider khác có thể có phạm vi hỗ trợ khác nhau. Không hard-code tên provider trong test portable nếu hợp đồng triển khai không yêu cầu provider cụ thể.

Nếu CI chạy trên nhiều JDK/provider, có thể dùng JUnit assumption để đánh dấu test là aborted khi thuật toán không có sẵn. Như vậy test report phân biệt rõ môi trường không hỗ trợ với lỗi round-trip thực sự.

```java
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import java.security.NoSuchAlgorithmException;
import javax.crypto.KEM;

final class KemTestSupport {
    private KemTestSupport() {
    }

    static KEM dhkemOrSkip() throws NoSuchAlgorithmException {
        try {
            return KEM.getInstance("DHKEM");
        } catch (NoSuchAlgorithmException e) {
            assumeTrue(false, "Runtime không có provider hỗ trợ DHKEM: " + e.getMessage());
            throw e; // Chỉ để thỏa mãn luồng điều khiển của compiler.
        }
    }
}
```

Trong project thực tế, helper có thể đặt ở test source set dùng chung. Nếu môi trường CI bắt buộc phải hỗ trợ DHKEM, hãy cấu hình runtime phù hợp và để test thất bại khi thiếu provider thay vì skip.

## 3. Kiểm thử round-trip: hai phía tạo cùng shared secret

Bên nhận tạo key pair. Bên gửi dùng public key để encapsulate; bên nhận dùng private key tương ứng để decapsulate. Kết quả cần có cùng key material.

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.KEM;
import javax.crypto.SecretKey;
import org.junit.jupiter.api.Test;

class KemRoundTripTest {
    @Test
    void encapsulationAndDecapsulationProduceSameSecret() throws Exception {
        KeyPairGenerator keyPairGenerator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = keyPairGenerator.generateKeyPair();

        KEM kem = KemTestSupport.dhkemOrSkip();
        KEM.Encapsulated encapsulated = kem
                .newEncapsulator(recipientKeys.getPublic())
                .encapsulate();

        SecretKey senderSecret = encapsulated.key();
        byte[] encapsulationMessage = encapsulated.encapsulation();

        SecretKey receiverSecret = kem
                .newDecapsulator(recipientKeys.getPrivate())
                .decapsulate(encapsulationMessage);

        byte[] senderBytes = senderSecret.getEncoded();
        byte[] receiverBytes = receiverSecret.getEncoded();

        try {
            assertNotNull(senderBytes,
                    "Test provider cần cho phép export secret để so sánh key material");
            assertNotNull(receiverBytes,
                    "Test provider cần cho phép export secret để so sánh key material");
            assertTrue(MessageDigest.isEqual(senderBytes, receiverBytes),
                    "Hai phía phải khôi phục cùng shared secret");
        } finally {
            if (senderBytes != null) {
                Arrays.fill(senderBytes, (byte) 0);
            }
            if (receiverBytes != null) {
                Arrays.fill(receiverBytes, (byte) 0);
            }
        }
    }
}
```

Test tạo key pair mới và encapsulate mới trong mỗi lần chạy. `MessageDigest.isEqual()` so sánh hai dãy byte mà không đưa secret ra assertion message. Các bản sao byte lấy từ `getEncoded()` được xóa trong `finally` sau khi so sánh.

`SecretKey.getEncoded()` có thể trả về `null` nếu provider quản lý key theo cách không cho export, ví dụ key nằm trong HSM. Test trên dành cho software provider có thể export key material. Với provider không exportable, hãy kiểm tra việc hai phía sử dụng được key qua KDF hoặc cipher trong một integration test phù hợp, thay vì yêu cầu xuất secret ra byte array.

## 4. Kiểm thử encapsulation message được truyền nguyên vẹn

Encapsulation message là dữ liệu công khai cần gửi từ bên encapsulate sang bên decapsulate. Shared secret là dữ liệu bí mật và không được truyền đi. Test nên dùng đúng byte array do `encapsulate()` trả về và chuyển nó cho bên nhận.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import javax.crypto.KEM;
import org.junit.jupiter.api.Test;

class KemEncapsulationMessageTest {
    @Test
    void encapsulationMessageCanBePassedToRecipient() throws Exception {
        KeyPair recipientKeys = KeyPairGenerator.getInstance("X25519")
                .generateKeyPair();
        KEM kem = KemTestSupport.dhkemOrSkip();

        KEM.Encapsulated encapsulated = kem
                .newEncapsulator(recipientKeys.getPublic())
                .encapsulate();

        byte[] messageForRecipient = encapsulated.encapsulation();
        byte[] secondCopy = encapsulated.encapsulation();

        assertEquals(messageForRecipient.length, secondCopy.length);
        org.junit.jupiter.api.Assertions.assertArrayEquals(
                messageForRecipient, secondCopy);
    }
}
```

Ví dụ kiểm tra rằng API trả về cùng nội dung message khi đọc lại từ đối tượng `KEM.Encapsulated`. Trong test giao thức thực tế, nên serialize message vào đúng định dạng wire format, parse ở phía nhận và decapsulate dữ liệu đã parse. Việc đó kiểm tra thêm framing, length prefix, version và algorithm identifier của giao thức.

Không đưa `encapsulated.key()` vào message gửi cho bên nhận. Bên nhận tự khôi phục secret bằng private key và encapsulation message.

## 5. Kiểm thử encapsulation có độ dài không hợp lệ

Input sai định dạng cần bị từ chối. Với DHKEM dùng X25519, encapsulation message chứa ephemeral public key X25519 có độ dài 32 byte. Một message ngắn hơn, chẳng hạn 31 byte, không phải encoding hợp lệ cho cấu hình này.

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import javax.crypto.DecapsulateException;
import javax.crypto.KEM;
import org.junit.jupiter.api.Test;

class InvalidKemEncapsulationTest {
    @Test
    void truncatedDHKemX25519MessageIsRejected() throws Exception {
        KeyPair recipientKeys = KeyPairGenerator.getInstance("X25519")
                .generateKeyPair();
        KEM kem = KemTestSupport.dhkemOrSkip();
        KEM.Decapsulator decapsulator = kem
                .newDecapsulator(recipientKeys.getPrivate());

        byte[] truncatedMessage = new byte[31];

        assertThrows(DecapsulateException.class,
                () -> decapsulator.decapsulate(truncatedMessage));
    }
}
```

`DecapsulateException` biểu thị lỗi khi provider không thể decapsulate input. Test này gắn với profile DHKEM/X25519 có encapsulation length xác định; không dùng độ dài 31 byte như một quy tắc chung cho mọi KEM algorithm. Với thuật toán khác, hãy lấy định dạng và kích thước message từ đặc tả thuật toán và giao thức.

Trong production, cần kiểm tra length và cấu trúc message ở tầng parser trước khi gọi provider, đồng thời vẫn xử lý exception từ `decapsulate()` vì input có thể sai theo những cách khác.

## 6. Không giả định mọi message bị thay đổi đều ném `DecapsulateException`

Một điểm dễ nhầm là KEM không tự cung cấp tính toàn vẹn hoặc xác thực cho encapsulation message. Nếu một byte của message bị thay đổi nhưng dữ liệu sau thay đổi vẫn là một encoding hợp lệ, decapsulation có thể tạo ra một shared secret khác thay vì ném exception.

Với DHKEM/X25519, một ephemeral public key khác nhưng vẫn hợp lệ có thể dẫn đến một kết quả secret khác. Do đó, không viết test tổng quát kiểu “flip một bit thì bắt buộc phải ném `DecapsulateException`”. Hành vi cần kiểm tra phụ thuộc vào cấu trúc message và quy tắc xác thực của thuật toán.

Tương tự, dùng private key của một recipient khác không nhất thiết tạo ra exception. Decapsulator có thể thực hiện phép tính hợp lệ với private key đó nhưng thu được secret khác với secret bên gửi. Đây không phải cơ chế xác thực danh tính người nhận.

Nếu giao thức cần phát hiện sửa đổi hoặc xác thực peer, phải dùng cơ chế xác thực và bảo vệ dữ liệu phù hợp ở tầng giao thức, thường kết hợp KEM với KDF và AEAD. Test tích hợp nên xác nhận tag AEAD hoặc bước xác thực thất bại khi ciphertext, context hoặc thông tin binding bị thay đổi.

## 7. Kiểm thử dùng sai recipient key

Test sau minh họa rằng một private key khác có thể tạo ra secret khác. Vì đây là test trên DHKEM/X25519 với software provider hỗ trợ export secret, test so sánh key material trong cùng một lần chạy.

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.KEM;
import org.junit.jupiter.api.Test;

class WrongRecipientKeyTest {
    @Test
    void differentRecipientPrivateKeyDoesNotRecoverSenderSecret() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair intendedRecipient = generator.generateKeyPair();
        KeyPair otherRecipient = generator.generateKeyPair();
        KEM kem = KemTestSupport.dhkemOrSkip();

        KEM.Encapsulated encapsulated = kem
                .newEncapsulator(intendedRecipient.getPublic())
                .encapsulate();

        byte[] senderBytes = encapsulated.key().getEncoded();
        byte[] otherBytes = kem
                .newDecapsulator(otherRecipient.getPrivate())
                .decapsulate(encapsulated.encapsulation())
                .getEncoded();

        try {
            assertNotNull(senderBytes);
            assertNotNull(otherBytes);
            assertFalse(MessageDigest.isEqual(senderBytes, otherBytes));
        } finally {
            if (senderBytes != null) {
                Arrays.fill(senderBytes, (byte) 0);
            }
            if (otherBytes != null) {
                Arrays.fill(otherBytes, (byte) 0);
            }
        }
    }
}
```

Test không mong đợi `DecapsulateException` trong trường hợp private key khác nhưng vẫn hợp lệ về cấu trúc. Hai key pair được tạo độc lập nên secret khôi phục bằng private key không tương ứng sẽ khác secret phía gửi, với xác suất va chạm không đáng kể theo thuật toán.

## 8. Kiểm tra provider thực tế, không khóa vào tên mặc định

`KEM.getInstance("DHKEM")` yêu cầu JCA chọn provider phù hợp. Provider thực tế dùng cho encapsulator và decapsulator được quan sát sau khi tạo các đối tượng này:

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import javax.crypto.KEM;
import org.junit.jupiter.api.Test;

class KemProviderTest {
    @Test
    void selectedProvidersAreAvailableForBothOperations() throws Exception {
        KeyPair recipientKeys = KeyPairGenerator.getInstance("X25519")
                .generateKeyPair();
        KEM kem = KemTestSupport.dhkemOrSkip();

        KEM.Encapsulator encapsulator = kem.newEncapsulator(recipientKeys.getPublic());
        KEM.Decapsulator decapsulator = kem.newDecapsulator(recipientKeys.getPrivate());

        assertNotNull(encapsulator.providerName());
        assertNotNull(decapsulator.providerName());
    }
}
```

Không assert provider phải có tên `SunJCE` trong test portable. Một runtime có thể cài provider khác, chẳng hạn provider tích hợp HSM. Nếu compliance yêu cầu một provider cụ thể, hãy kiểm tra tên provider theo chính sách triển khai và chạy test trên đúng môi trường đó.

Provider có thể chọn implementation dựa trên key type và parameters. Vì thế, chỉ kiểm tra `KEM.getInstance()` thành công chưa chứng minh provider có thể tạo encapsulator hoặc decapsulator cho key thực tế của ứng dụng.

## 9. Kiểm thử trường hợp thuật toán không được hỗ trợ

Khi ứng dụng yêu cầu thuật toán không có trong các provider đã đăng ký, `KEM.getInstance()` ném `NoSuchAlgorithmException`. Có thể kiểm tra cách tầng cấu hình chuyển lỗi này thành lỗi khởi động rõ ràng:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.security.NoSuchAlgorithmException;
import javax.crypto.KEM;
import org.junit.jupiter.api.Test;

class UnsupportedKemAlgorithmTest {
    @Test
    void unknownAlgorithmIsReported() {
        assertThrows(NoSuchAlgorithmException.class,
                () -> KEM.getInstance("NO-SUCH-KEM-ALGORITHM"));
    }
}
```

Trong production, không nên đợi đến request đầu tiên mới phát hiện provider thiếu thuật toán. Có thể kiểm tra khả năng tạo KEM và các key/parameter cần thiết trong giai đoạn khởi tạo service hoặc health check phù hợp.

## 10. Kiểm tra `SecretKey` mà không làm lộ key material

Một số nguyên tắc khi viết test và log:

- Không đưa `SecretKey.getEncoded()` vào log, exception message hoặc report test.
- Không assert shared secret bằng một giá trị cố định vì encapsulation dùng randomness.
- Không so sánh `SecretKey` bằng identity của object; hai object khác nhau vẫn có thể chứa cùng key material.
- Dùng `MessageDigest.isEqual()` khi test cần so sánh hai bản sao key bytes có thể export.
- Xóa bản sao byte trong `finally` sau khi test dùng xong.
- Với key không exportable, kiểm thử việc sử dụng key qua API mật mã tiếp theo thay vì cố lấy byte array.

Việc gọi `Arrays.fill()` chỉ xóa bản sao byte mà test đang giữ. Nó không bảo đảm xóa mọi bản sao nội bộ của provider, JVM hoặc phần cứng. Không diễn giải thao tác này như một bảo đảm zeroization toàn bộ key material.

## 11. Tách unit test, provider test và interoperability test

KEM phụ thuộc vào thuật toán và provider, vì vậy nên phân chia mục tiêu test:

| Loại test | Phạm vi | Ví dụ |
|---|---|---|
| Unit test logic giao thức | Code đóng gói/parse message, chọn algorithm ID, quản lý lỗi | Reject message thiếu field hoặc sai version |
| Provider test | Runtime thực tế có hỗ trợ thuật toán, key type và parameters không | DHKEM/X25519 round-trip trên JDK triển khai |
| Negative provider test | Provider từ chối encoding hoặc key không hợp lệ | Encapsulation length sai, key type không tương thích |
| Interoperability test | Hai implementation độc lập có thể trao đổi message và khôi phục secret tương ứng không | Provider/JDK phía gửi khác phía nhận |
| Protocol integration test | KEM được kết hợp đúng với KDF, AEAD và authentication | Thay đổi encapsulation/context làm bước xác thực dữ liệu thất bại |

Không nên dùng một unit test với provider mặc định để tuyên bố mọi JDK hoặc HSM đều tương thích. Interoperability phải được kiểm tra trên các runtime/provider mà hệ thống thực sự triển khai.

## 12. Những lỗi kiểm thử thường gặp

| Lỗi | Vì sao sai | Cách làm phù hợp |
|---|---|---|
| So sánh shared secret với giá trị cố định | Encapsulation dùng randomness | So sánh secret hai phía trong cùng một lần chạy |
| So sánh object `SecretKey` bằng `==` | Hai object khác nhau có thể biểu diễn cùng key material | So sánh key bytes trong test provider exportable hoặc dùng key trong phép toán tiếp theo |
| Giả định `getEncoded()` luôn khác null | HSM/provider có thể không cho export key | Chọn test provider exportable hoặc test qua KDF/cipher |
| Flip một bit và luôn mong `DecapsulateException` | Message thay đổi nhưng vẫn hợp lệ có thể tạo secret khác | Test encoding sai cấu trúc riêng; kiểm tra integrity ở tầng AEAD/protocol |
| Dùng private key khác và mong luôn có exception | Decapsulation với key hợp lệ khác có thể trả secret khác | Đối chiếu secret hoặc xác thực ở tầng giao thức |
| Hard-code provider mặc định | Test dễ hỏng trên runtime có provider khác | Kiểm tra provider thực tế; chỉ assert tên khi chính sách yêu cầu |
| Dùng input sai độ dài cho mọi thuật toán | Encapsulation length phụ thuộc KEM và key type | Lấy định dạng từ đặc tả thuật toán cụ thể |
| Chỉ kiểm tra `KEM.getInstance()` | Chưa xác nhận key và parameters được provider hỗ trợ | Tạo encapsulator/decapsulator bằng key thật |
| Log shared secret để debug | Có thể làm lộ key material trong CI/log | Chỉ log algorithm, provider và trạng thái lỗi không nhạy cảm |

## 13. Checklist cho test KEM

Trước khi hoàn tất bộ test, hãy xác nhận:

1. Test đang chạy trên JDK/provider có hỗ trợ thuật toán và key type yêu cầu chưa?
2. Round-trip dùng đúng public/private key pair tương ứng chưa?
3. Shared secret được so sánh theo key material thay vì object identity chưa?
4. Test có xử lý trường hợp `getEncoded()` trả về `null` không?
5. Input malformed có dựa trên định dạng của đúng thuật toán không?
6. Test có phân biệt malformed input với message bị thay đổi nhưng vẫn hợp lệ không?
7. Có tránh giả định KEM tự xác thực peer hoặc bảo vệ integrity cho protocol không?
8. Provider thực tế của encapsulator và decapsulator có được quan sát khi cần không?
9. Secret/private key có được giữ khỏi log và assertion output không?
10. Interoperability và protocol integration có được kiểm thử riêng trên môi trường triển khai không?

## Tài liệu tham khảo

- [Java SE 21 API: `javax.crypto.KEM`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html)
- [Java SE 21 API: `javax.crypto.DecapsulateException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/DecapsulateException.html)
- [Java Security Standard Algorithm Names — Java 21](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html)
- [Oracle Providers Documentation — Java 21](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html)

## Kết luận

Kiểm thử KEM cần chứng minh bên gửi và bên nhận khôi phục cùng shared secret từ đúng key pair và encapsulation message. Với DHKEM/X25519, có thể kiểm tra round-trip bằng JUnit Jupiter, đối chiếu key material khi provider cho phép export và xác nhận message bị cắt ngắn bị từ chối bằng `DecapsulateException`. Không được giả định mọi thay đổi byte hoặc private key không tương ứng đều phải ném exception: KEM không tự cung cấp authentication hay integrity cho giao thức. Hãy kiểm tra provider thực tế, bảo vệ key material, và test riêng KDF/AEAD cùng các bước xác thực của protocol.
