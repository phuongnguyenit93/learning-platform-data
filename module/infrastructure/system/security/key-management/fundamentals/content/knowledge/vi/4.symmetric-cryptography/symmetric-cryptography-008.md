# Initialization vector (IV) — Giá trị khởi tạo trong mật mã đối xứng

## 1. Initialization vector là gì?

**Initialization vector (IV)** là giá trị được cung cấp cùng **khóa mật mã** để khởi tạo trạng thái của một chế độ mã hóa. Đối với nhiều chế độ mã hóa đối xứng, IV giúp các lần mã hóa khác nhau của cùng một dữ liệu bằng cùng khóa tạo ra kết quả khác nhau, hoặc giúp mỗi lần mã hóa sử dụng một luồng mã hóa khác biệt.

Ví dụ, dịch vụ thanh toán lưu hai bản ghi có cùng nội dung. Nếu dùng AES-GCM với **cùng khóa** và **nonce khác nhau**, bản mã thông thường sẽ khác nhau, và người quan sát không thể chỉ nhìn phần bản mã để kết luận chắc chắn hai bản ghi có cùng nội dung. Nếu dùng lại cùng nonce với cùng khóa AES-GCM, tính bảo mật và khả năng xác thực có thể bị phá vỡ nghiêm trọng.

Trong thực tế, tài liệu có thể gọi giá trị này là **IV** hoặc **nonce**. Hai tên thường được sử dụng gần nhau, nhưng cách tạo và điều kiện an toàn **phụ thuộc chế độ mã hóa**. Không có một quy tắc “IV phải ngẫu nhiên” áp dụng đúng cho mọi trường hợp.

> **Nguyên tắc quan trọng:** IV thường **không phải bí mật**. Cần bảo vệ **khóa**, đồng thời bảo đảm IV đáp ứng đúng điều kiện của chế độ mã hóa: có chế độ đòi IV **khó dự đoán**, có chế độ đòi nonce/counter **không được lặp với cùng khóa**, và có chế độ yêu cầu cả cấu trúc cụ thể khác.

### IV nằm ở đâu trong luồng mã hóa?

~~~mermaid
flowchart TD
    P[Dữ liệu rõ - plaintext] --> E[Chế độ mã hóa đối xứng]
    K[Khóa bí mật K] --> E
    V[IV/nonce phù hợp với mode] --> E
    A[AAD nếu dùng AEAD] --> E
    E --> C[Bản mã ciphertext]
    E --> T[Authentication tag nếu dùng AEAD]
    C --> S[Lưu hoặc gửi gói dữ liệu]
    V --> S
    T --> S
    A --> R[Ngữ cảnh xác thực phải tái tạo khi giải mã]
    S --> D[Giải mã với K, IV và tag]
    R --> D
~~~

Trong hệ thống dùng **AEAD** (Authenticated Encryption with Associated Data), như AES-GCM, IV/nonce là một phần của ngữ cảnh cần thiết để giải mã và xác thực. Tag được tạo dựa trên phép mã hóa, nonce, dữ liệu và AAD theo đặc tả thuật toán. Người nhận cần biết IV, bản mã, tag và AAD tương ứng để giải mã chính xác.

## 2. Phân biệt IV, nonce, counter, salt và authentication tag

| Thuật ngữ | Ý nghĩa | Bí mật? | Điều kiện cần lưu ý |
| --- | --- | --- | --- |
| **IV (Initialization vector)** | Giá trị đầu vào khởi tạo trạng thái mã hóa theo mode | Thông thường **không** | Kích thước, khả năng dự đoán và tính duy nhất tùy mode |
| **Nonce** | Giá trị được dùng một lần trong phạm vi bảo mật nhất định, thường là **mỗi khóa** | Thông thường **không** | Không được tái sử dụng khi mode yêu cầu nonce duy nhất |
| **Counter** | Bộ đếm được đưa vào phép tạo luồng mã hóa, có thể kết hợp nonce | Không | Không được lặp **counter block** dưới cùng khóa ở các vị trí mã hóa cần độc lập |
| **Salt** | Giá trị phụ trong KDF/hàm dẫn xuất khóa, giúp phân tách đầu ra hoặc chống tính toán sẵn trong ngữ cảnh thích hợp | Thường **không** | Không đồng nhất với IV; yêu cầu phụ thuộc KDF |
| **Authentication tag** | Giá trị kiểm chứng tính toàn vẹn/xác thực của bản mã và AAD trong AEAD | Không cần bí mật | Phải được kiểm tra trước khi coi plaintext là đáng tin |
| **Key** | Bí mật dùng bởi thuật toán mật mã đối xứng | **Có** | Phải bảo vệ, phân quyền, xoay vòng, thu hồi và hủy an toàn |

**Nonce** thường nhấn mạnh điều kiện **không lặp**; **IV** là tên tổng quát hơn trong nhiều API. Trong AES-GCM, tài liệu và thư viện đôi khi dùng hai tên thay thế nhau. Nhưng không nên suy ra từ tên gọi rằng một IV có thể lấy từ bộ đếm hay cần lấy từ nguồn ngẫu nhiên: **mode quyết định yêu cầu**.

### IV có phải là một phần của khóa không?

Không. Khóa AES-256 dài **32 byte**; IV trong AES-GCM thường dùng **12 byte (96 bit)**, còn IV cho AES-CBC có độ dài đúng **16 byte (128 bit)**, bằng kích thước khối AES. **Kích thước IV không phải kích thước khóa**. AES-GCM dùng IV 96 bit rất phổ biến dù kích thước khối AES vẫn là 128 bit.

Có thể lưu IV dưới dạng rõ cùng ciphertext vì thuật toán được thiết kế để an toàn khi IV đáp ứng điều kiện và kẻ tấn công biết IV. Tuy nhiên, **nếu dữ liệu không được xác thực**, việc thay đổi IV có thể dẫn đến thay đổi plaintext sau giải mã. IV không bí mật **không đồng nghĩa không cần bảo vệ tính toàn vẹn của gói dữ liệu**.

## 3. Mỗi chế độ mã hóa có yêu cầu IV khác nhau

| Chế độ/thuật toán | Giá trị khởi tạo thường dùng | Quy tắc an toàn trọng tâm | Tính toàn vẹn mặc định? |
| --- | --- | --- | --- |
| **AES-CBC** | IV **16 byte**, mới và **khó dự đoán** trước khi plaintext được chốt | IV phải không thể dự đoán theo yêu cầu của CBC; thường tạo bằng CSPRNG | **Không**, cần cơ chế xác thực riêng |
| **AES-CTR** | Khối đầu vào bộ đếm theo đặc tả, thường nonce + counter | Tuyệt đối tránh dùng lại bất kỳ **counter block** nào với cùng khóa | **Không**, cần MAC hoặc dùng AEAD |
| **AES-GCM** | Nonce/IV **12 byte** là lựa chọn chuẩn, thường dùng CSPRNG hoặc cơ chế cấp duy nhất | **Không lặp nonce với cùng khóa**; quản lý số lần dùng và bộ đếm | **Có**, qua authentication tag |
| **ChaCha20-Poly1305 (IETF)** | Nonce **12 byte** | **Không lặp nonce với cùng khóa** | **Có**, qua authentication tag |
| **XChaCha20-Poly1305** | Nonce **24 byte** trong các triển khai hỗ trợ | Tuân thủ đặc tả và cách cấp nonce của thư viện | **Có**, qua authentication tag |
| **AES-ECB** | Không dùng IV | Làm lộ mẫu khối, **không nên dùng để mã hóa dữ liệu thông thường** | Không |

Bảng so sánh các **quy tắc thiết kế phổ biến**, không thay thế đặc tả thư viện. Trong thực tế, AES-GCM là lựa chọn mặc định phù hợp cho nhiều trường hợp mã hóa dữ liệu ứng dụng, nếu quản lý được nonce và xác thực tag. CBC/CTR vẫn tồn tại ở hệ thống cũ hoặc giao thức đặc thù nhưng cần bổ sung bảo vệ tính toàn vẹn một cách đúng đắn.

### 3.1. AES-CBC: IV phải khó dự đoán

AES có kích thước khối 128 bit. Trong CBC, trước khi mã hóa, khối plaintext đầu tiên được XOR với IV:

~~~text
C1 = AES_Encrypt(K, P1 XOR IV)
C2 = AES_Encrypt(K, P2 XOR C1)
...
~~~

Vì IV đi vào phép biến đổi khối đầu tiên, việc lặp hoặc dự đoán IV có thể làm lộ quan hệ giữa các bản rõ trong những mô hình tấn công nhất định. Đặc biệt, với CBC, **chỉ có tính duy nhất là chưa đủ** cho yêu cầu bảo mật thông dụng: IV phải **khó dự đoán** trước khi plaintext liên quan được lựa chọn/chốt. Dùng bộ đếm tuần tự công khai làm CBC IV là lựa chọn sai.

**Nên:** Mỗi lần mã hóa CBC tạo IV 16 byte mới bằng bộ sinh ngẫu nhiên mật mã (CSPRNG). IV được lưu/gửi cùng bản mã. Cần bảo vệ tính toàn vẹn của **cả IV lẫn ciphertext**, ví dụ bằng cơ chế Encrypt-then-MAC được thiết kế đúng hoặc chuyển sang AEAD.

**Không nên:** Dùng IV toàn số 0, IV hằng trong cấu hình, IV dựa vào timestamp dễ đoán hoặc lấy các byte của khóa làm IV.

**CBC không tự xác thực dữ liệu.** Nếu ứng dụng giải mã CBC rồi trả lỗi padding khác với lỗi xác thực hoặc xử lý plaintext chưa kiểm chứng, hệ thống có thể mở ra **padding-oracle attack**. Không nên giải quyết chỉ bằng việc “đổi IV ngẫu nhiên”; cần giao thức xác thực đúng và ưu tiên AEAD.

### 3.2. AES-CTR: cấm lặp bộ đếm dưới cùng khóa

CTR biến block cipher thành cơ chế tạo luồng mã hóa: AES mã hóa các **counter block**, tạo keystream, rồi XOR với plaintext.

~~~text
S0 = AES_Encrypt(K, CounterBlock0)
S1 = AES_Encrypt(K, CounterBlock1)

CiphertextBlock0 = PlaintextBlock0 XOR S0
CiphertextBlock1 = PlaintextBlock1 XOR S1
~~~

Nếu cùng khóa **K** và cùng counter block được dùng lại, keystream sẽ lặp. Kẻ tấn công có hai ciphertext tương ứng có thể suy ra:

~~~text
C1 XOR C2 = P1 XOR P2
~~~

Đó là rò rỉ nghiêm trọng, dù kẻ tấn công không biết khóa AES. Vì vậy, với CTR phải quản lý **tính duy nhất của toàn bộ counter block**, tránh cả lặp giữa các thông điệp lẫn tràn bộ đếm trong một thông điệp. **CTR không tự bảo đảm tính toàn vẹn**: sửa bit ciphertext có thể gây sửa bit tương ứng ở plaintext.

### 3.3. AES-GCM: nonce không được lặp với cùng khóa

GCM kết hợp mã hóa dạng counter với cơ chế xác thực GHASH để tạo **ciphertext và authentication tag**. Với AES-GCM, quy tắc trọng tâm là:

> **Một cặp (key, nonce) chỉ được dùng cho một lần mã hóa độc lập.**

Nếu cùng khóa AES-GCM và nonce bị dùng lại, keystream có thể lặp, làm lộ quan hệ giữa plaintext, đồng thời gây rủi ro nghiêm trọng đối với bảo đảm xác thực/tag. **Ngay cả khi AAD khác nhau hoặc hai plaintext giống nhau, cũng không được cố tình tái sử dụng nonce cho hai lần mã hóa độc lập.**

IV GCM 12 byte thường được ưu tiên vì phù hợp với cách xây dựng bộ đếm tối ưu của GCM. Các độ dài IV khác có thể được hỗ trợ nhưng cần xử lý theo đặc tả; không nên tự chọn khác 12 byte khi không có yêu cầu cụ thể.

## 4. “Ngẫu nhiên” và “duy nhất” khác nhau thế nào?

**Ngẫu nhiên** (*random*) nghĩa là đầu ra được lấy từ bộ sinh có tính chất ngẫu nhiên phù hợp. **Khó dự đoán** (*unpredictable*) nghĩa là đối thủ không thể biết giá trị trước khi thời điểm/chọn plaintext có liên quan. **Duy nhất** (*unique*) nghĩa là một giá trị không được dùng lại trong phạm vi cần bảo vệ.

- Một **bộ đếm tăng đều** có thể là duy nhất nhưng dễ dự đoán: có thể phù hợp cho nonce của mode chỉ cần tính duy nhất, **không đủ** để làm IV CBC.
- Một giá trị lấy từ **CSPRNG** có thể khó dự đoán nhưng vẫn có **xác suất va chạm**; dùng ngẫu nhiên không đồng nghĩa bảo đảm toán học rằng mọi nonce đều duy nhất.
- Một IV lưu ở dạng rõ vẫn có thể an toàn: việc biết IV sau khi nó được tạo không làm cho CBC mất yêu cầu khó dự đoán tại **thời điểm quan trọng**, nếu IV đã được chọn đúng.
- Sự duy nhất luôn phải xác định **theo phạm vi**: cùng **khóa mật mã**, cùng scheme và cách phân bổ nonce. Đổi khóa thực sự tạo một không gian nonce độc lập, nhưng không phải lý do để quản lý nonce cẩu thả.

### Xác suất va chạm khi dùng GCM với nonce ngẫu nhiên 96 bit

Nếu tạo ngẫu nhiên đều các nonce dài 96 bit và mã hóa **q** thông điệp với **cùng khóa**, ước lượng theo bài toán ngày sinh cho xác suất có ít nhất một lần va chạm, khi q còn nhỏ so với không gian giá trị, là:

~~~text
p_collision ≈ q * (q - 1) / (2 * 2^96)
~~~

Xác suất tăng xấp xỉ theo **bình phương số lượt mã hóa**. Trong hệ thống mã hóa khối lượng lớn, **không thể chỉ nói “12 byte là rất dài nên chắc chắn không bao giờ trùng”**. Cần có **ngân sách số lượt mã hóa mỗi khóa**, quy trình xoay khóa và cơ chế phân bổ IV phù hợp với giới hạn của thuật toán/tiêu chuẩn và đặc tả sản phẩm.

Với phương pháp nonce ngẫu nhiên cho GCM, tài liệu NIST SP 800-38D có giới hạn số lượt gọi mã hóa trong phạm vi khóa và các cơ chế tạo IV thuộc điều kiện áp dụng; không nên tự đặt một ngưỡng tùy tiện cho production. Khi số lượng bản ghi/phiên/thiết bị lớn hoặc hệ thống phân tán phức tạp, thiết kế nonce xác định có đảm bảo duy nhất và được đánh giá có thể phù hợp hơn.

## 5. Điều gì xảy ra khi dùng lại IV hoặc nonce?

### 5.1. AES-GCM: hỏng cả bí mật lẫn khả năng xác thực

Giả sử hai bản rõ **P1** và **P2** được mã hóa bằng cùng key và cùng nonce trong GCM. Do GCM dùng cơ chế keystream dạng counter cho phần mã hóa:

~~~text
C1 = P1 XOR S
C2 = P2 XOR S

=> C1 XOR C2 = P1 XOR P2
~~~

Nếu đối thủ biết hoặc đoán một bản rõ, họ có thể suy ra thông tin về bản rõ còn lại. Sự lặp nonce cũng khiến cơ chế xác thực GCM suy yếu mạnh, có thể hỗ trợ giả mạo thông điệp. Vấn đề không thể “sửa” chỉ bằng cách giữ bí mật IV hoặc thay AAD.

**Phản ứng khi phát hiện nonce reuse:** ngăn các lần mã hóa mới bằng cặp khóa/nonce bị ảnh hưởng, xác định phạm vi các bản mã liên quan, thay khóa nếu cần, đánh giá việc lộ dữ liệu/giả mạo, rồi chuyển hoặc mã hóa lại dữ liệu theo quyết định của bộ phận bảo mật. Thay nonce ở metadata của **bản mã cũ** sẽ không khắc phục được bản mã đã tạo sai.

### 5.2. AES-CBC: IV hằng, đoán được hoặc bị sửa

Với cùng K, cùng IV và cùng khối plaintext đầu tiên, CBC sẽ cho **cùng khối ciphertext đầu tiên**, làm lộ mẫu. Dùng IV tuần tự dễ đoán không đáp ứng yêu cầu khó dự đoán của CBC. Ngoài ra, vì khối đầu tiên phụ thuộc vào **P1 XOR IV**, nếu không có cơ chế xác thực, kẻ tấn công có thể sửa IV để gây thay đổi có kiểm soát ở plaintext sau giải mã.

Không nên suy luận “CBC đã dùng IV ngẫu nhiên nên dữ liệu có toàn vẹn”. **CBC + IV tốt** vẫn cần một cơ chế xác thực phù hợp, và phải chống trả lời lỗi giải mã gây rò rỉ thông tin.

### 5.3. AES-CTR: lặp khối đếm hay vượt giới hạn bộ đếm

Một nonce được chọn khác nhưng bố trí counter block sai vẫn có thể gây **trùng counter block** giữa các thông điệp. Nếu ứng dụng dùng bộ đếm 32 bit cuối trong một khối 128 bit mà không giới hạn số block, bộ đếm có thể quay vòng và tái tạo keystream. Mỗi thông điệp phải có phạm vi counter block không trùng với thông điệp khác dùng cùng khóa.

## 6. Thiết kế quản lý IV an toàn trong hệ thống

### 6.1. Lựa chọn cách tạo

| Cách tạo | Khi nào có thể phù hợp | Điều kiện cần chứng minh |
| --- | --- | --- |
| **CSPRNG tạo 12 byte cho AES-GCM** | Nhiều ứng dụng mã hóa dữ liệu ở quy mô được kiểm soát | Nguồn ngẫu nhiên an toàn; theo dõi giới hạn tổng số lần mã hóa/khóa và rủi ro va chạm |
| **Bộ đếm/nonce xác định cho GCM/CTR** | Hệ thống cần bảo đảm không lặp tuyệt đối trong phạm vi cấu hình | Cấp phát duy nhất, bền vững qua restart, không trùng giữa các node, tránh overflow |
| **CSPRNG tạo 16 byte cho AES-CBC** | Hệ thống còn buộc dùng CBC | IV mới, **khó dự đoán**; có cơ chế xác thực ciphertext và IV |
| **IV từ timestamp, record ID, username hoặc hash plaintext** | Thường **không phù hợp làm giải pháp mặc định** | Không được giả định duy nhất/khó dự đoán; nguy cơ collision, lặp qua môi trường hoặc bị đoán |

**CSPRNG** có thể dùng API như **SecureRandom** của Java. Không sử dụng **java.util.Random** để tạo IV mật mã. Cũng không tạo IV bằng cách lấy 12 byte đầu từ UUID dạng chuỗi, cắt hash của dữ liệu hoặc hard-code trong cấu hình: các cách đó không chứng minh được thuộc tính mà mode cần.

### 6.2. Hệ thống phân tán: đừng để mỗi node nghĩ mình là duy nhất

Một lỗi dễ gặp là mỗi instance giữ counter nonce bắt đầu từ **0**. Khi hai instance mã hóa bằng **cùng một khóa**, cả hai có thể sinh cùng nonce. Điều tương tự xảy ra sau restart nếu counter không được lưu bền vững hoặc khi clone một bản sao máy/VM cùng trạng thái.

Các cách xử lý có thể gồm:

- **Phân vùng namespace nonce** theo danh tính node **được cấp và quản lý duy nhất**, kết hợp bộ đếm không lặp; phải bảo đảm cách ghép đúng với yêu cầu nonce của mode.
- **Cấp dải counter từ dịch vụ điều phối** hoặc nguồn trạng thái bền vững có tính nguyên tử; dự trù khi node crash khiến một số giá trị bị bỏ qua là chấp nhận được, miễn **không tái dùng**.
- **Dùng nonce ngẫu nhiên CSPRNG** nếu khối lượng và giới hạn cho phép, có theo dõi ngân sách số lượng thông điệp dưới cùng khóa.
- **Tách DEK theo nhóm dữ liệu/người thuê/phiên** khi kiến trúc phù hợp; mỗi khóa có phạm vi nonce riêng nhưng làm tăng nhu cầu quản lý khóa.

Không tự gán một prefix node bằng giá trị ngẫu nhiên ngắn rồi khẳng định chắc chắn không trùng. Mô hình cần xét số node, môi trường test/production, backup/restore, rollback deployment và việc các khóa/phiên bản được chia sẻ hay độc lập.

### 6.3. Với retry, queue và xử lý lại dữ liệu

Nếu một job mã hóa thất bại và được retry, hãy tạo **một nonce mới** cho lần mã hóa độc lập. Trong quy trình idempotent, nếu muốn trả lại **chính gói ciphertext đã tạo và lưu** ở lần đầu, có thể trả lại gói đó mà không thực hiện phép mã hóa mới; đây không phải là một lần dùng lại nonce để **mã hóa mới**.

Cần phân biệt hành động **gửi lại ciphertext có sẵn** với hành động **chạy thuật toán Encrypt lần nữa** bằng cùng nonce và khóa. Điều này quan trọng với worker queue, batch job và ứng dụng lưu trạng thái chưa hoàn chỉnh.

## 7. Ví dụ Java với AES-GCM: IV 12 byte mới cho mỗi lần mã hóa

Ví dụ dùng **JCA/JCE** với AES/GCM/NoPadding. Dữ liệu trả về gồm: **1 byte phiên bản định dạng**, **12 byte IV**, tiếp đến **ciphertext kèm tag GCM**. GCM trong JCA thường trả ciphertext và authentication tag nối liền trong kết quả của **doFinal**.

Đây là minh họa để hiểu cách quản lý IV, không phải một giao thức lưu trữ sản xuất hoàn chỉnh. Ở production, khóa nên được quản lý bởi KMS/HSM hoặc cơ chế quản lý khóa được phê duyệt; phải có key ID/version, chính sách xoay khóa, hạn mức mã hóa và xử lý lỗi phù hợp.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmIvDemo {
    private static final int IV_BYTES = 12;   // 96 bit
    private static final int TAG_BITS = 128;  // 16 byte
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final byte FORMAT_VERSION = 1;
    private static final SecureRandom RNG = new SecureRandom();

    // Mỗi lần gọi Encrypt sinh IV mới dưới cùng khóa.
    public static byte[] encrypt(SecretKey key, byte[] plaintext, byte[] aad)
            throws GeneralSecurityException {
        byte[] iv = new byte[IV_BYTES];
        RNG.nextBytes(iv);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, iv)
        );
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        return ByteBuffer
                .allocate(1 + IV_BYTES + ciphertextAndTag.length)
                .put(FORMAT_VERSION)
                .put(iv)
                .put(ciphertextAndTag)
                .array();
    }

    public static byte[] decrypt(SecretKey key, byte[] payload, byte[] aad)
            throws GeneralSecurityException {
        if (payload == null || payload.length < 1 + IV_BYTES + TAG_BYTES) {
            throw new GeneralSecurityException("Invalid encrypted payload");
        }

        ByteBuffer input = ByteBuffer.wrap(payload);
        byte version = input.get();
        if (version != FORMAT_VERSION) {
            throw new GeneralSecurityException("Unsupported format");
        }

        byte[] iv = new byte[IV_BYTES];
        input.get(iv);
        byte[] ciphertextAndTag = new byte[input.remaining()];
        input.get(ciphertextAndTag);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, iv)
        );
        cipher.updateAAD(aad);
        // Ném AEADBadTagException nếu tag không khớp.
        // Không coi plaintext là hợp lệ trước khi doFinal thành công.
        return cipher.doFinal(ciphertextAndTag);
    }

    public static void main(String[] args) throws Exception {
        // Chỉ tạo khóa trực tiếp ở đây để minh họa.
        // Trong production cần key management, key ID/version và rotation.
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey key = generator.generateKey();

        byte[] plaintext = "Hoa don 123".getBytes(StandardCharsets.UTF_8);
        // AAD không bí mật; cần nguồn dữ liệu/định danh đáng tin.
        byte[] aad = "tenant=demo|record=123".getBytes(StandardCharsets.UTF_8);

        byte[] payload1 = encrypt(key, plaintext, aad);
        byte[] payload2 = encrypt(key, plaintext, aad);

        System.out.println("IV khac nhau: "
                + !java.util.Arrays.equals(
                    java.util.Arrays.copyOfRange(payload1, 1, 13),
                    java.util.Arrays.copyOfRange(payload2, 1, 13)
                ));
        // Kết quả true là điều được kỳ vọng, nhưng nonce ngẫu nhiên
        // không bảo đảm tuyệt đối không va chạm khi số lần gọi tăng lớn.

        String restored = new String(
                decrypt(key, payload1, aad),
                StandardCharsets.UTF_8
        );
        System.out.println("Giai ma: " + restored);

        // Thử sai AAD: xác thực phải thất bại.
        byte[] wrongAad = "tenant=demo|record=124"
                .getBytes(StandardCharsets.UTF_8);
        try {
            decrypt(key, payload1, wrongAad);
            throw new IllegalStateException("Unexpected success");
        } catch (AEADBadTagException expected) {
            System.out.println("Sai AAD: bi tu choi");
        }
    }
}
~~~

### Vì sao ví dụ này có các bước đó?

1. **SecureRandom** tạo IV 12 byte mới. Đây là cách đơn giản cho một bài minh họa, nhưng cần theo dõi hạn mức với khóa dùng nhiều lần và quy mô lớn.
2. **GCMParameterSpec(TAG_BITS, iv)** truyền độ dài tag **theo bit**, không phải theo byte. GCM của Java hỗ trợ tag 128 bit trong cấu hình phổ biến.
3. **updateAAD** ràng buộc ngữ cảnh bản ghi với bản mã. Khi giải mã phải cung cấp **đúng cùng AAD**, nếu không xác thực sẽ thất bại. AAD **được xác thực nhưng không được mã hóa**.
4. **doFinal** trong DECRYPT_MODE kiểm tra tag và ném ngoại lệ khi thất bại. Không trả plaintext chưa xác thực cho các nghiệp vụ khác.
5. **IV được lưu cùng ciphertext/tag**, vì cần lấy lại chính IV của lần mã hóa để giải mã. Việc lưu IV dạng rõ không tiết lộ key.
6. **Phiên bản định dạng** cho phép thay đổi cách đóng gói về sau. Khi có nhiều key, nên lưu **key ID/version** trong metadata phù hợp và ràng buộc metadata nhạy cảm với AAD theo giao thức.

**Không diễn giải dòng “IV khác nhau: true” là kiểm thử chứng minh các IV luôn không lặp.** Nó chỉ minh họa hai lần mã hóa độc lập thường dùng hai IV khác nhau. Chứng minh giới hạn sử dụng và tính duy nhất ở quy mô lớn cần phân tích thiết kế hệ thống.

### Xử lý lỗi giải mã

Nếu nhận **AEADBadTagException**, có thể do ciphertext/tag/IV bị sửa, AAD không khớp, dùng nhầm khóa/phiên bản hoặc gói dữ liệu bị hỏng. Không nên tự động “bỏ qua tag” để cố giải mã. Nhật ký vận hành chỉ cần ghi metadata an toàn, mã lỗi và correlation ID; không in plaintext, key hoặc khóa dữ liệu bí mật.

## 8. Lưu trữ IV, AAD và metadata an toàn

Dữ liệu mã hóa cần đủ thông tin để chọn đúng khóa và giải mã về sau. Một cấu trúc logic cho **AES-GCM**:

~~~text
EncryptedRecord {
    formatVersion: 1
    algorithm: "AES-256-GCM"
    keyId: "payment-data-key"
    keyVersion: "v3"
    iv: <12 bytes>
    ciphertext: <bytes>
    tag: <16 bytes>
    aadContext: { tenantId, recordId, schemaVersion }
}
~~~

Đây là **sơ đồ dữ liệu minh họa**, không phải định dạng có thể sao chép trực tiếp vào ứng dụng. Trong dữ liệu thật, cần quy ước encoding byte, endian nếu có số, độ dài từng trường, giới hạn kích thước, thay đổi phiên bản và nguồn lấy AAD đáng tin. **Không tin giá trị AAD do người gửi tự khai mà không kiểm tra quan hệ của nó với dữ liệu và danh tính**.

Cũng cần quan tâm đến tính toàn vẹn của metadata điều hướng khóa. Nếu keyId hoặc keyVersion bị sửa, ứng dụng có thể chọn nhầm khóa hoặc làm hỏng quá trình giải mã. Có thể đưa các trường liên quan vào AAD được xác thực, kết hợp với xác thực ở tầng lưu trữ/protocol, tùy thiết kế. Đảm bảo mã hóa AAD theo quy tắc **không mơ hồ**, để cả bên mã hóa và bên giải mã tính cùng dãy byte.

**Không nên:** chỉ lưu ciphertext rồi trông chờ một IV hiện hành trong cấu hình; IV cần gắn với **từng lần mã hóa**, và không thể tự ý thay bằng IV mới khi cần đọc dữ liệu cũ.

## 9. IV trong envelope encryption và hệ thống KMS/HSM

Trong **envelope encryption**, ứng dụng thường dùng **DEK (Data Encryption Key)** để mã hóa dữ liệu, còn **KEK (Key Encryption Key)** được lưu hoặc quản lý trong **KMS/HSM** để bọc DEK. IV sử dụng cho thuật toán mã hóa dữ liệu bằng DEK **là một phần riêng của thao tác mã hóa**, không phải một “khóa con” mặc nhiên do KMS cấp phát.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant KMS as KMS/HSM
    participant DB as Storage
    App->>KMS: Yêu cầu tạo/cấp DEK hoặc giải bọc DEK
    KMS-->>App: DEK khả dụng theo chính sách, DEK được bọc
    Note over App: Sinh IV mới phù hợp AES-GCM
    App->>App: AES-GCM(plaintext, DEK, IV, AAD)
    App->>DB: Lưu ciphertext, IV, tag, wrapped DEK, metadata
    Note over App: Giảm thời gian giữ DEK dạng rõ trong bộ nhớ
    App->>DB: Đọc gói dữ liệu mã hóa
    DB-->>App: ciphertext, IV, tag, wrapped DEK, metadata
    App->>KMS: Giải bọc DEK theo quyền được cấp
    KMS-->>App: DEK khả dụng theo chính sách
    App->>App: Xác thực tag rồi giải mã với IV gốc và AAD
~~~

Tùy sản phẩm, KMS có thể cung cấp API **Encrypt/Decrypt** tự quản lý IV/nonce và định dạng ciphertext. Khi dùng API đó, tuân theo đặc tả của dịch vụ và **không tự ghép một nonce khác để thay thế**. Khi ứng dụng tự mã hóa dữ liệu bằng DEK với thư viện như JCA, **ứng dụng phải quản lý IV cho từng bản mã**.

### Xoay vòng KEK hoặc DEK ảnh hưởng thế nào đến IV?

- **Xoay KEK**: có thể yêu cầu bọc lại DEK nhưng không nhất thiết thay bản mã dữ liệu và IV hiện có. Điều này tùy kiến trúc KMS và phiên bản.
- **Xoay DEK**: các bản mã mới phải sử dụng DEK mới và IV/nonce phù hợp cho từng lần mã hóa. Nếu mã hóa lại dữ liệu cũ, mỗi lần mã hóa mới cũng phải có IV hợp lệ theo DEK mới.
- **Giữ DEK cũ để giải mã**: phải giữ **IV gốc** tương ứng với mỗi ciphertext; nếu mất IV thì không thể giải mã đúng chỉ bằng việc còn khóa.
- **Thu hồi hoặc hủy DEK**: cần biết các bản mã, bản sao lưu và archive còn phụ thuộc; xóa khóa không thể thay bằng “tạo lại IV”.

Nói cách khác, phạm vi cần bảo đảm duy nhất của GCM thường là **mỗi DEK dùng cho mã hóa AES-GCM**, không phải chỉ theo keyId của KEK trong KMS. Khi nhiều dịch vụ dùng chung một DEK, cần phối hợp nonce giữa các dịch vụ hoặc thay đổi cách phân bổ DEK.

### Các vai trò trong việc quản lý IV

| Vai trò | Trách nhiệm điển hình |
| --- | --- |
| **Key owner** | Phê duyệt loại mã hóa, yêu cầu bảo mật, giới hạn dữ liệu/khóa, vòng đời và rủi ro |
| **Key custodian** | Quản lý KMS/HSM, DEK/KEK, chính sách, rotation, vận hành kiểm toán |
| **Application team / key user** | Tạo IV theo đúng mode, gắn IV với ciphertext, lưu AAD, tránh reuse, xử lý lỗi tag |
| **Security reviewer** | Kiểm tra lựa chọn mode, thiết kế nonce ở hệ phân tán, giới hạn dùng khóa và phản ứng sự cố |
| **Auditor** | Kiểm tra quy trình, quyền truy cập và bằng chứng rằng khóa/phiên bản được kiểm soát và xử lý theo chính sách |

KMS/HSM bảo vệ vật liệu khóa rất quan trọng, nhưng **không tự giải quyết việc ứng dụng dùng cùng DEK và IV hai lần** nếu thao tác mã hóa diễn ra bên ngoài KMS/HSM.

## 10. Tình huống vận hành: dịch vụ lưu hóa đơn trên nhiều instance

Giả sử **invoice-service** triển khai 20 instance. Mỗi instance dùng cùng một DEK AES-256-GCM để mã hóa hóa đơn trước khi ghi vào database.

**Thiết kế lỗi:** mỗi instance đặt nonce bằng bộ đếm 96 bit khởi tạo từ 0 mỗi khi start. Instance 1 và instance 2 rất dễ cùng mã hóa với nonce 0, 1, 2... dưới cùng DEK; reboot tiếp tục gây trùng. Việc các bản ghi có ID khác nhau **không làm trùng nonce trở nên an toàn**.

**Một thiết kế khả thi:** tạo IV 12 byte bằng SecureRandom cho mỗi lần mã hóa, theo dõi giới hạn tổng số bản mã trên mỗi DEK và xoay DEK trước khi vượt ngưỡng được chính sách/tiêu chuẩn xác định. Với hệ thống quy mô rất lớn, cần phân tích xác suất collision và cân nhắc chiến lược nonce xác định có điều phối (ví dụ phân vùng phạm vi node được bảo đảm duy nhất cộng counter bền vững), hoặc tạo DEK riêng theo nhóm dữ liệu.

**Điều phải kiểm chứng khi vận hành:**

- Có bao nhiêu bản mã đã được tạo dưới mỗi DEK; có vượt ngưỡng sử dụng theo thiết kế hay chưa?
- Sau restart/restore từ snapshot, node có thể tái sử dụng trạng thái counter cũ không?
- Việc replay job có mã hóa lại bản ghi bằng nonce cũ không?
- Khi một instance tăng tải mạnh, việc phân bổ nonce có giữ đúng giới hạn và không lặp không?
- Khi chuyển vùng DR, dữ liệu IV gốc và metadata keyVersion có được sao chép đồng bộ không?
- Đã kiểm thử rằng tag GCM bị sửa, AAD sai hoặc dùng nhầm keyVersion đều dẫn tới **giải mã thất bại** chưa?

Tổ chức cần quyết định chính sách “một DEK cho một đối tượng”, “một DEK cho một batch” hay “một DEK cho nhiều bản ghi”. Không có một cấu hình đúng cho mọi hệ thống: mỗi lựa chọn thay đổi chi phí KMS, phạm vi ảnh hưởng khi lộ DEK và yêu cầu phối hợp IV.

## 11. Những sai lầm phổ biến và cách xử lý

| Sai lầm | Rủi ro | Cách phòng ngừa |
| --- | --- | --- |
| Dùng IV cố định, toàn zero hoặc sao chép từ ví dụ để mã hóa nhiều bản ghi | Lặp IV/nonce dưới cùng khóa; rò rỉ dữ liệu nghiêm trọng ở CTR/GCM | Tạo IV mới theo từng phép mã hóa và đúng đặc tả mode |
| Dùng timestamp hoặc bộ đếm dự đoán được cho CBC | Không đáp ứng yêu cầu IV khó dự đoán của CBC | CSPRNG cho IV CBC |
| Dùng SecureRandom và khẳng định GCM nonce “không bao giờ trùng” | Bỏ qua xác suất va chạm và hạn mức số lần mã hóa | Tính ngân sách mỗi key, giám sát rotation, phân tích quy mô |
| Mỗi node có counter bắt đầu từ 0 | Nonce/counter block trùng giữa các node | Phân vùng duy nhất, cấp phát dải bền vững hoặc kiến trúc nonce khác |
| Dùng lại nonce khi job retry và chạy lại Encrypt | Reuse cùng key/nonce dù plaintext giống | Sinh nonce mới nếu mã hóa mới; trả lại payload cũ nếu chỉ gửi lại |
| Lấy IV từ vài byte đầu của key | Liên hệ bí mật giữa key/IV và dễ lặp | Sinh IV độc lập theo cơ chế phù hợp |
| Dùng AES-CBC mà không xác thực ciphertext và IV | Sửa dữ liệu, padding oracle | Dùng AEAD hoặc cơ chế Encrypt-then-MAC đúng |
| Bỏ qua GCM tag khi giải mã lỗi | Trả về dữ liệu bị chỉnh sửa hoặc sai khóa/AAD | Từ chối và xử lý lỗi; không sử dụng plaintext chưa xác thực |
| Chỉ lưu ciphertext, không lưu IV/keyVersion | Không còn đủ thông tin giải mã sau restart/rotation | Đóng gói IV, tag, key ID/version và ngữ cảnh |
| Cho rằng KMS quản lý KEK thì tự bảo đảm IV của DEK | Ứng dụng có thể reuse nonce dù KEK an toàn | Xem rõ API nào đang mã hóa và ai quản lý IV |
| Lộ hoặc ghi plaintext key trong log cùng metadata | Mất bí mật; gia tăng mức độ tác động khi dữ liệu bị thu thập | Audit metadata cần thiết; loại bỏ key/DEK/plaintext khỏi log |

## 12. Checklist trước khi đưa mã hóa đối xứng vào production

1. **Mode:** Đã chọn AEAD như AES-GCM khi phù hợp? Nếu phải dùng CBC/CTR, đã có thiết kế xác thực độc lập an toàn chưa?
2. **Kích thước:** IV/nonce đúng kích thước và định dạng của mode và thư viện? Có nhầm IV AES-GCM 12 byte với kích thước khối AES 16 byte không?
3. **Yêu cầu:** CBC có IV mới và khó dự đoán; CTR có counter block không lặp; GCM/ChaCha20-Poly1305 có nonce không lặp với cùng khóa?
4. **Nguồn tạo:** Có dùng CSPRNG hoặc cơ chế cấp phát duy nhất đã đánh giá; tránh số ngẫu nhiên không dành cho mật mã, timestamp/ID không được chứng minh?
5. **Đa instance:** Restart, autoscaling, retry, DR, clone máy và xoay khóa có thể khiến nonce lặp không?
6. **Lưu trữ:** Mỗi payload có IV gốc, ciphertext, tag, key ID/version và dữ liệu AAD/metadata cần thiết để giải mã không?
7. **Xác thực:** Tag được kiểm tra; AAD nhất quán; lỗi xác thực được từ chối mà không đưa plaintext chưa tin cậy đến nghiệp vụ?
8. **Vòng đời:** Có ngân sách số lượt mã hóa mỗi key, giám sát, rotation, quy trình thay DEK/KEK và giữ khả năng đọc dữ liệu cũ?
9. **Quyền:** Ai được mã hóa/giải mã, ai cấp quyền KMS, ai quản lý DEK, ai kiểm toán? Có tách nhiệm vụ và audit thay đổi nhạy cảm?
10. **Ứng cứu:** Nếu phát hiện nonce reuse, đội ngũ biết khóa/phiên bản/bản mã nào bị ảnh hưởng, cách khóa luồng mã hóa mới, đánh giá rủi ro và chuyển đổi dữ liệu không?

### Ghi nhớ

**Initialization vector** là dữ liệu khởi tạo của một chế độ mã hóa đối xứng; nó **thường được công khai và lưu cùng ciphertext**, trong khi khóa phải được bảo vệ. **CBC cần IV khó dự đoán**; **CTR cần counter block không lặp**; **GCM/ChaCha20-Poly1305 cần nonce không lặp dưới cùng khóa**. Việc bảo vệ dữ liệu còn phụ thuộc vào **authentication tag, AAD, quản lý DEK/KEK, KMS/HSM, vòng đời xoay vòng–thu hồi–hủy và kiểm toán**. Dùng thuật toán mạnh nhưng quản lý sai IV vẫn có thể khiến toàn bộ thiết kế mã hóa thất bại.
