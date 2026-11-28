# Session identifier entropy

## 1. Vì sao định danh phiên cần khó đoán?

Một hệ thống có thể xác thực người dùng rất chặt chẽ nhưng vẫn để mất phiên nếu định danh phiên dễ dự đoán. Với một phiên sử dụng bearer token, bên xuất trình được token hợp lệ có thể được hệ thống nhận diện là người đang sở hữu phiên đó. Kẻ tấn công không nhất thiết phải biết mật khẩu nếu có thể đoán đúng một token còn hiệu lực.

Ví dụ, hệ thống cấp session ID theo bộ đếm:

```text
session-100001
session-100002
session-100003
```

Các giá trị có thể không trùng nhau, nhưng người quan sát một giá trị có thể suy ra những giá trị lân cận. Thêm tên người dùng, thời gian tạo hoặc một tiền tố cố định không tự làm chúng trở thành bí mật khó dự đoán.

Mục tiêu bảo mật cần chuyển thành yêu cầu cụ thể là:

> Khi biết thuật toán, định dạng, thời điểm phát hành và các session ID của chính mình, một bên không có quyền vẫn không thể dự đoán thực tế được định danh của phiên khác hoặc phiên được tạo tiếp theo.

Bài này tập trung vào định danh phiên dạng opaque token: client giữ một giá trị không mang ý nghĩa nghiệp vụ, còn máy chủ liên kết giá trị đó với trạng thái phiên. Với token tự chứa được ký như JWT, tính xác thực phụ thuộc cơ chế kiểm tra chữ ký và các ràng buộc của token; không thể đánh giá an toàn bằng độ ngẫu nhiên của toàn bộ chuỗi JWT hoặc riêng trường `jti`.

## 2. Entropy, độ dài và tính duy nhất là những thuộc tính khác nhau

### 2.1. Entropy diễn tả mức khó đoán

Nếu một giá trị được chọn độc lập và đều từ `2^b` khả năng, nó có `b` bit entropy theo mô hình lý tưởng đó. Tăng thêm một bit làm không gian lựa chọn tăng gấp đôi.

```text
32 bit  → 2^32 khả năng
64 bit  → 2^64 khả năng
128 bit → 2^128 khả năng
```

Đối với một lần đoán, tính phân bố đều rất quan trọng. Nếu một giá trị có xác suất xuất hiện lớn bất thường, kẻ tấn công có thể ưu tiên giá trị đó thay vì tìm kiếm đều trong toàn bộ không gian.

Một đại lượng diễn tả trường hợp dễ đoán nhất là min-entropy:

```text
H_min(X) = -log2(max_x P[X = x])
```

Ví dụ, một bộ sinh có hàng triệu giá trị đầu ra nhưng trả về một giá trị cố định với xác suất 1/2 chỉ có min-entropy 1 bit. Số giá trị có thể xuất hiện lớn không đủ chứng minh chúng đều khó đoán.

Khi phân tích bảo mật, phải xét thông tin kẻ tấn công đã biết. Nếu biết seed hoặc trạng thái của bộ sinh và từ đó tính được giá trị tiếp theo, chuỗi đầu ra nhìn có vẻ ngẫu nhiên vẫn không có tính khó dự đoán cần thiết đối với người đó.

### 2.2. Ba thuộc tính cần kiểm tra riêng

| Thuộc tính | Câu hỏi cần trả lời | Điều chưa được bảo đảm |
|---|---|---|
| Độ dài | Token chứa bao nhiêu ký tự hoặc byte? | Những ký tự đó có thực sự khó dự đoán không? |
| Tính duy nhất | Hai phiên có được gán cùng một định danh không? | Có đoán được định danh của phiên khác không? |
| Tính khó dự đoán | Biết các thông tin công khai có giúp đoán token không? | Token có được bảo vệ khỏi đánh cắp hoặc rò rỉ không? |

Bộ đếm có thể duy nhất nhưng dễ đoán. Một token mật mã đủ dài có thể rất khó đoán nhưng vẫn bị lộ trong log. Từng thuộc tính cần yêu cầu và bằng chứng riêng.

### 2.3. Ngẫu nhiên mật mã không có nghĩa mỗi byte là entropy vật lý mới

CSPRNG là bộ sinh số giả ngẫu nhiên an toàn cho mục đích mật mã. Nó có thể mở rộng trạng thái đã được khởi tạo an toàn thành nhiều byte đầu ra có tính khó dự đoán về mặt tính toán.

Vì vậy cần phân biệt:

- Số bit đầu ra và kích thước không gian biểu diễn.
- Entropy của nguồn khởi tạo hoặc nguồn bổ sung trạng thái.
- Độ mạnh mật mã của bộ sinh và khả năng giữ bí mật trạng thái đó.

Sinh 32 byte tạo ra một đầu ra có kích thước 256 bit. Điều này không tự chứng minh đã thu thập 256 bit entropy độc lập mới hoặc toàn bộ cơ chế có độ mạnh mật mã 256 bit. Đặc tả phải nêu nguồn sinh và yêu cầu độ mạnh, thay vì suy tất cả từ chiều dài kết quả.

## 3. Độ dài chuỗi không phải số bit entropy

Với bảng ký tự có `A` phần tử và chuỗi dài `L`, số bit tối đa có thể biểu diễn là:

```text
b_max = L × log2(A)
```

Đây là giới hạn trên. Nó chỉ tương ứng với entropy khi việc lựa chọn có phân bố và tính độc lập phù hợp. Ký tự cố định, tiền tố công khai, thời gian tạo hoặc quan hệ giữa các ký tự làm giảm phần chưa biết.

### 3.1. Encoding chỉ đổi cách biểu diễn

| Dữ liệu đầu vào | Hexadecimal | Base64url không padding |
|---|---|---|
| 16 byte | 32 ký tự | 22 ký tự |
| 24 byte | 48 ký tự | 32 ký tự |
| 32 byte | 64 ký tự | 43 ký tự |

Nếu đầu vào là 16 byte ngẫu nhiên theo mô hình lý tưởng, chuyển từ hex sang Base64url vẫn biểu diễn cùng 128 bit. Chuỗi ngắn hơn không có nghĩa mất entropy nếu phép mã hóa giữ đầy đủ dữ liệu.

Ngược lại, không được nhân mọi chuỗi Base64url 22 ký tự với 6 rồi kết luận có 132 bit entropy. Khi mã hóa 16 byte, ký tự cuối chỉ mang hai bit dữ liệu; bốn bit còn lại trong nhóm mã hóa là các bit đệm bằng không. Có bốn khả năng cho ký tự cuối đó, không phải 64.

Padding `=` cũng không tạo thêm entropy. Việc bỏ padding trong một định dạng được xác định rõ chỉ bỏ thông tin biểu diễn dư thừa.

### 3.2. Phần công khai không được tính vào ngân sách bí mật

Giả sử token có 32 ký tự hex nhưng 16 ký tự đầu là tiền tố đã biết. Chỉ 16 ký tự hex còn lại là ngẫu nhiên độc lập:

```text
Entropy lý tưởng của phần bí mật = 16 × 4 = 64 bit
```

Nếu token có cấu trúc:

```text
version.shard.randomSecret
```

thì `version` và `shard` có thể giúp chọn cách xử lý hoặc định tuyến. Các trường công khai đó không đóng góp vào entropy của `randomSecret`. Việc biết shard thậm chí có thể giúp kẻ tấn công xác định tập phiên cần nhắm đến; mô hình tấn công phải sử dụng số phiên và không gian token của đúng phạm vi đó.

Không tính user ID hoặc email vào phần bí mật chỉ vì người dùng khác chưa nhìn thấy chúng. Đây thường là dữ liệu có thể biết hoặc suy ra từ các nguồn khác.

### 3.3. Hash không biến dữ liệu dễ đoán thành bí mật mạnh

Ví dụ sau vẫn yếu nếu người tấn công có thể liệt kê các đầu vào:

```text
sessionId = SHA-256(userId || timestamp || counter)
```

Chuỗi hash dài 256 bit nhưng kẻ tấn công có thể tính hash cho các tổ hợp đầu vào có khả năng xảy ra. Độ dài đầu ra không mở rộng lượng bí mật của đầu vào.

Một thiết kế dựa trên hàm mật mã có khóa bí mật có thể có tính khó dự đoán nhờ khóa, nhưng khi đó cần đánh giá khóa và giao thức tương ứng. Không thể dùng kết luận về hash không khóa để thay cho phân tích thiết kế có khóa, cũng không nên tự thêm một lớp hash rồi coi đó là bằng chứng bộ sinh phiên đã an toàn.

## 4. Định lượng nguy cơ đoán trúng phiên

### 4.1. Nhắm vào một phiên cụ thể

Giả sử định danh mục tiêu được chọn đều trong không gian `N = 2^b` và mỗi lần đoán độc lập, có hoàn lại. Sau `q` lần đoán:

```text
P_trúng_một_phiên = 1 - (1 - 1/N)^q
```

Khi `q/N` rất nhỏ:

```text
P_trúng_một_phiên ≈ q / 2^b
```

Nếu kẻ tấn công thử các giá trị không lặp, xác suất với một mục tiêu là `q/N` khi `q <= N`. Trong mô hình đồng đều, hai cách gần tương đương ở vùng xác suất nhỏ.

### 4.2. Chỉ cần trúng bất kỳ phiên nào đang hoạt động

Đối với nhiều ứng dụng công khai, kẻ tấn công không cần nhắm trước một người cụ thể. Một phiên hợp lệ bất kỳ đã có thể gây thiệt hại.

Giả sử có `m` session ID hợp lệ khác nhau trong cùng không gian, tập này giữ nguyên trong thời gian xét và mỗi lần đoán độc lập:

```text
P_trúng_bất_kỳ = 1 - (1 - m/N)^q
```

Khi `q × m / N` rất nhỏ:

```text
P_trúng_bất_kỳ ≈ q × m / 2^b
```

Đây là lý do không được bỏ qua số phiên đang có hiệu lực. Cùng một số bit nhưng một hệ thống có nhiều phiên hợp lệ hơn tạo nhiều mục tiêu hơn cho mỗi lần đoán.

Nếu số phiên thay đổi theo thời gian, có thể phân tích theo các khoảng với số phiên tương ứng hoặc dùng một giới hạn trên phù hợp. Không áp dụng công thức tập phiên cố định mà bỏ qua hoàn toàn giả định này.

### 4.3. Ví dụ tính toán

Giả sử một mô hình tấn công có:

- `m = 10^6` phiên hợp lệ đồng thời trong cùng không gian.
- `q = 10^12` lần kiểm tra token trong khoảng thời gian đang phân tích.
- Token lý tưởng, phân bố đều và các lần đoán độc lập.

Với không gian 64 bit:

```text
q × m / 2^64 ≈ 0,05421
P chính xác theo mô hình ≈ 0,05277 ≈ 5,28%
```

Ở ví dụ này, dùng công thức gần đúng cho kết quả khoảng 5,42%; công thức chính xác cho khoảng 5,28%. Chênh lệch xuất hiện vì đại lượng gần đúng không còn rất nhỏ.

Với không gian 128 bit:

```text
q × m / 2^128 ≈ 2,94 × 10^-21
```

Các con số là phép tính của mô hình minh họa, không phải dự báo một hệ thống thực sẽ cho phép `10^12` lần thử. Giới hạn tốc độ, thời gian sống phiên và cấu trúc kiểm tra token quyết định ngân sách tấn công thực tế.

### 4.4. Từ mức rủi ro đến số bit

Với một ngưỡng rủi ro minh họa `epsilon = 10^-12`, có thể dùng chặn trên theo hợp các sự kiện:

```text
P_trúng_bất_kỳ <= q × m / 2^b

Muốn q × m / 2^b <= epsilon:

b >= ceil(log2(q × m / epsilon))
```

Với `q = 10^12` và `m = 10^6`, kết quả là ít nhất 100 bit trong mô hình đồng đều. Đây không phải lý do chọn đúng 100 bit cho triển khai. Thiết kế còn cần biên dự phòng, nguồn sinh mật mã phù hợp, thay đổi quy mô và chính sách bảo mật của tổ chức.

OWASP phân biệt entropy với độ dài biểu diễn; hướng dẫn nêu tối thiểu 64 bit entropy và khuyến nghị dùng CSPRNG với kích thước ít nhất 128 bit nếu tự tạo session ID. Không nên đọc ngưỡng tối thiểu đó thành khẳng định 64 bit đủ cho mọi quy mô và ngân sách tấn công. Xem [OWASP Session Management Cheat Sheet — Session ID Properties](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#session-id-properties).

## 5. Đoán trúng và va chạm là hai bài toán khác nhau

Tấn công đoán token xét khả năng một bên tìm được token đang hợp lệ. Va chạm xét khả năng bộ sinh tạo hai token giống nhau cho các lần phát hành khác nhau.

Với `n` token độc lập, đồng đều trong không gian `2^b`, xác suất có ít nhất một va chạm được xấp xỉ:

```text
P_va_chạm ≈ 1 - exp(-n(n - 1) / (2 × 2^b))
```

Khi xác suất rất nhỏ:

```text
P_va_chạm ≈ n(n - 1) / (2 × 2^b)
```

Ví dụ, phát hành `10^9` token 128 bit lý tưởng có xác suất va chạm xấp xỉ `1,47 × 10^-21`. Đây là phép tính va chạm, không phải xác suất một kẻ tấn công chiếm phiên sau `10^9` lần đoán.

Tham số `n` phải khớp yêu cầu. Nếu chỉ xét xung đột trong kho phiên đang hoạt động, cần xét các token cùng tồn tại trong kho đó. Nếu tuyên bố không trùng trong toàn bộ lịch sử phát hành, phải dùng tổng số token của lịch sử tương ứng.

Kho phiên vẫn phải có thao tác tạo không ghi đè khi khóa đã tồn tại. Nếu hiếm khi gặp trùng, hệ thống có thể sinh lại trong số lần thử bị chặn bởi một giới hạn và phát cảnh báo thích hợp khi lỗi lặp lại. Không được thay thế phiên đang có bằng phiên của người khác.

Một ràng buộc duy nhất trong cơ sở dữ liệu giúp ngăn xung đột lưu trữ. Nó không sửa được bộ sinh dễ dự đoán: bộ đếm vẫn có thể vượt kiểm tra duy nhất mà hoàn toàn không đáp ứng yêu cầu chống đoán.

## 6. Nguồn sinh ngẫu nhiên là một phần của yêu cầu bảo mật

Yêu cầu “token có 128 bit entropy” chưa đủ để giao cho đội phát triển. Cần xác định những đặc tính phải có của cơ chế sinh:

1. Dùng cơ chế ngẫu nhiên phục vụ mục đích mật mã được nền tảng hỗ trợ.
2. Có nguồn khởi tạo và bổ sung trạng thái phù hợp với môi trường triển khai.
3. Không đặt seed từ timestamp, user ID, bộ đếm hoặc một hằng số.
4. Không làm lộ hoặc nhân bản trạng thái bộ sinh qua snapshot, cấu hình hay dữ liệu chẩn đoán không được kiểm soát.
5. Không chuyển sang bộ sinh yếu khi thành phần mật mã lỗi hoặc chậm.
6. Không làm mất phần ngẫu nhiên khi mã hóa, truyền, lưu và so sánh token.

### 6.1. Những cách sinh dễ gây sai

| Cách làm | Vấn đề |
|---|---|
| Bộ đếm hoặc timestamp | Có thể suy ra từ thứ tự và thời gian |
| Ghép user ID với dữ liệu công khai | Phần công khai không đóng góp bí mật |
| Bộ sinh dùng cho mô phỏng, trò chơi hoặc phân phối tải | Không có cơ sở mặc định để dùng làm bí mật phiên |
| CSPRNG nhưng tự seed bằng hằng số hoặc thời gian | Có thể làm suy yếu quá trình khởi tạo tùy bộ sinh và cách dùng |
| Sinh nhiều byte rồi cắt chuỗi cho vừa cột | Làm giảm không gian token được chấp nhận |
| Lấy byte ngẫu nhiên rồi ánh xạ modulo vào bảng ký tự không chia hết 256 | Tạo phân bố lệch nếu không loại bỏ phần dư thích hợp |
| Dùng lại token sau khi đổi identity | Làm sai ràng buộc giữa token, phiên và chủ thể |

Ví dụ về modulo: với bảng 62 ký tự, `byteValue % 62` trên byte đồng đều từ 0 đến 255 khiến một số ký tự có năm tiền ảnh và số khác có bốn. Cách đơn giản để tránh tự xử lý phân bố ký tự là sinh byte mật mã rồi dùng encoding chuẩn giữ nguyên dữ liệu.

### 6.2. Nhiều node và khởi động lại

Một bộ sinh có thể hoạt động đúng trong một tiến trình đơn lẻ nhưng gặp vấn đề khi được đưa vào cách triển khai khác. Khi đánh giá thiết kế, cần xem:

- Các node có dùng chung seed cố định từ cấu hình không?
- Bản image có vô tình chứa trạng thái bộ sinh đã khởi tạo không?
- Snapshot hoặc clone máy ảo có cần cơ chế làm mới trạng thái theo nền tảng không?
- Khởi động lại có làm tái tạo một chuỗi token cũ không?
- Đường dự phòng khi phát hành lỗi có tự chuyển sang token ngắn hoặc có quy luật không?

Không khẳng định mọi snapshot đều gây trùng token. Yêu cầu đúng là hiểu cơ chế của runtime và nền tảng đang dùng, sau đó có bằng chứng các điều kiện triển khai đó không tạo chuỗi dự đoán hoặc lặp không kiểm soát.

## 7. Ví dụ Java: sinh dữ liệu bí mật rồi mã hóa

Ví dụ dưới đây minh họa việc sinh 32 byte và giữ nguyên chúng trong Base64url. Nó chỉ là thành phần sinh giá trị; không phải toàn bộ hệ thống quản lý phiên.

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class SessionIdentifierGenerator {
    private static final int TOKEN_BYTES = 32;

    private final SecureRandom random = new SecureRandom();
    private final Base64.Encoder encoder =
            Base64.getUrlEncoder().withoutPadding();

    public String generate() {
        byte[] value = new byte[TOKEN_BYTES];
        random.nextBytes(value);
        return encoder.encodeToString(value);
    }
}
```

Theo tài liệu Java, `SecureRandom` cung cấp bộ sinh ngẫu nhiên cho mục đích mật mã; cách khởi tạo phụ thuộc implementation. Ví dụ dùng `nextBytes` và không tự đặt seed. Việc đáp ứng một mức độ mạnh mật mã cụ thể vẫn cần đối chiếu thuật toán, provider và môi trường thực tế. Xem [Java SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html).

`withoutPadding()` trả về encoder bỏ ký tự padding cuối dữ liệu; nó không cắt byte đầu vào. Xem [Java Base64.Encoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Base64.Encoder.html#withoutPadding()).

Trong ví dụ:

- Mỗi lần gọi tạo mảng mới và điền đủ 32 byte.
- Kết quả Base64url không padding dài 43 ký tự.
- Không đưa user ID, role hoặc thời gian vào định danh.
- Không ghi token ra màn hình hoặc log.
- Chuỗi vẫn biểu diễn đủ 256 bit dữ liệu đầu ra, không suy ra từ đó rằng độ mạnh thực tế luôn là 256 bit.

Nếu nền tảng hoặc framework đã quản lý session ID, cần kiểm chứng cấu hình và đường thực thi của cơ chế đó thay vì lắp thêm một bộ sinh riêng nhưng không được sử dụng. Một hàm sinh đúng nhưng không nằm trên đường cấp phiên thật không đáp ứng yêu cầu.

## 8. Bảo toàn phần ngẫu nhiên trên toàn đường xử lý

Lỗi có thể xuất hiện sau khi token đã được sinh đúng. Đường kiểm tra cần bao phủ:

```text
Nguồn ngẫu nhiên
    → byte bí mật
    → encoding
    → cookie hoặc kênh mang token
    → bộ phân tích đầu vào
    → khóa tra cứu phiên
    → kiểm tra phiên hợp lệ
```

### 8.1. Không cắt hoặc so sánh một phần token

Ví dụ, bộ sinh tạo token 43 ký tự nhưng tầng lưu chỉ giữ 16 ký tự đầu. Hoặc truy vấn chỉ so sánh tiền tố vì muốn tăng tốc. Khi đó không gian dùng để nhận diện phiên đã bị giảm, dù cookie phía client vẫn trông dài.

Yêu cầu phải nêu rõ dữ liệu nào được dùng để xác thực phiên và phép so sánh có giữ đầy đủ thông tin cần thiết không. Với thiết kế tách mã tra cứu công khai và secret verifier, biết mã tra cứu một mình không được đủ để có phiên; ngân sách bí mật phải nằm ở verifier độc lập.

### 8.2. Quy tắc encoding và so sánh phải nhất quán

Base64url phân biệt chữ hoa và chữ thường. Nếu kho lưu dùng quy tắc so sánh không phân biệt hoa thường cho token dạng này, hai chuỗi khác nhau có thể bị coi là tương đương và không gian hiệu lực bị thay đổi.

Đặc tả nên chọn biểu diễn chuẩn, yêu cầu so sánh đúng biểu diễn đó hoặc giải mã nghiêm ngặt rồi so sánh đầy đủ byte theo thiết kế. Với Base64url không padding, cần xác định cách xử lý độ dài sai, ký tự ngoài bảng và các biểu diễn không chuẩn.

Nếu nhiều chuỗi được chấp nhận cho cùng một dãy byte do xử lý các bit đệm không nghiêm ngặt, có thể phát sinh lỗi khi danh sách thu hồi, cache và tầng tra cứu chuẩn hóa khác nhau. Đây không mặc nhiên là mất entropy của secret, nhưng vẫn là một điểm cần loại bỏ hoặc kiểm soát nhất quán.

### 8.3. Không nhận token do client tự chọn thành phiên đã xác thực

Một chuỗi đúng độ dài và đúng bảng ký tự chưa phải session ID hợp lệ. Hệ thống phải kiểm tra nó có tương ứng với phiên được phát hành có thẩm quyền và còn hiệu lực hay không.

Nếu client có thể đưa một token tùy ý rồi hệ thống gắn phiên đăng nhập vào token đó, kẻ tấn công có thể chọn trước token và chờ nạn nhân sử dụng. Tăng độ dài đầu ra của bộ sinh không giải quyết được đường tiếp nhận token do client kiểm soát này.

## 9. Đặc tả yêu cầu có thể kiểm chứng

Giả sử một ứng dụng chọn chính sách token opaque được sinh từ 32 byte CSPRNG, với yêu cầu đánh giá cơ chế sinh đạt độ mạnh mật mã tối thiểu 128 bit. Kích thước 32 byte và ngưỡng 128 bit là hai thuộc tính riêng; không thay thế nhau.

Bảng sau là một ví dụ đặc tả, cần điều chỉnh theo mô hình rủi ro của hệ thống thật:

| ID | Yêu cầu | Bằng chứng hoặc tiêu chí chấp nhận |
|---|---|---|
| SIE-01 | Mọi định danh cho phiên xác thực trong phạm vi phải được phát hành qua cơ chế CSPRNG đã được đánh giá | Lập được danh sách đường cấp phiên, thuật toán/provider và cấu hình dùng ở từng môi trường |
| SIE-02 | Thành phần bí mật của token phải lấy đủ 32 byte đầu ra CSPRNG; tiền tố công khai không được tính vào kích thước này | Đối chiếu code và cấu hình; giải mã mẫu kết quả được đủ 32 byte |
| SIE-03 | Cơ chế sinh phải được đánh giá đạt độ mạnh mật mã tối thiểu 128 bit trong môi trường triển khai | Có căn cứ kỹ thuật về thuật toán, provider, nguồn khởi tạo và cách sử dụng; không dùng kiểm tra trùng mẫu thay cho bằng chứng này |
| SIE-04 | Không dùng seed cố định, timestamp, thông tin người dùng hoặc bộ sinh không phù hợp làm nguồn bí mật | Kiểm tra các đường khởi tạo, cấu hình triển khai và cơ chế thay thế khi lỗi |
| SIE-05 | Encoding, truyền, lưu và kiểm tra phải giữ nguyên toàn bộ byte bí mật | Kiểm tra round-trip và schema kho phiên; không có truncate, so sánh tiền tố hoặc chuyển đổi hoa thường |
| SIE-06 | Khi tạo phiên gặp khóa đã tồn tại, hệ thống không được ghi đè phiên cũ | Ép bộ sinh kiểm thử trả về giá trị trùng; phiên gốc giữ nguyên và hành vi sinh lại hoặc báo lỗi tuân thủ chính sách |
| SIE-07 | Khi cơ chế sinh thất bại, hệ thống không được phát hành phiên bằng token dự phòng yếu | Tiêm lỗi tại ranh giới bộ sinh trong môi trường kiểm thử; không có phiên xác thực mới và có tín hiệu vận hành |
| SIE-08 | Token đúng định dạng nhưng chưa được phát hành không được cấp quyền truy cập phiên xác thực | Gửi giá trị kiểm thử không có trong kho; kết quả không được nhận diện thành người dùng khác |
| SIE-09 | Các node, lần khởi động lại và cách phục hồi được hỗ trợ không được tái sử dụng trạng thái sinh theo cách làm lặp chuỗi ngoài kiểm soát | Có phân tích cơ chế khởi tạo của nền tảng và kiểm thử hồi quy cho các điều kiện triển khai liên quan |
| SIE-10 | Hồ sơ thiết kế phải nêu ngân sách đoán token, số phiên hợp lệ và thời gian xét khi chọn kích thước | Có phép tính với giả định rõ ràng và biên dự phòng được chấp thuận |
| SIE-11 | Token thô không được xuất hiện trong log ứng dụng, gateway, tracing và thông báo lỗi trong phạm vi | Kiểm tra bằng token canary ở môi trường kiểm thử, quan sát các kênh ghi nhận được xác định |
| SIE-12 | Việc xác thực phiên phải kiểm tra đầy đủ secret hoặc verifier theo thiết kế, không chỉ mã tra cứu công khai | Có ca kiểm thử biết mã tra cứu nhưng không biết secret vẫn không truy cập được phiên |

SIE-11 kiểm soát rò rỉ, không trực tiếp tăng entropy. Nó được đưa vào đặc tả để tránh một triển khai có bộ sinh mạnh nhưng vô hiệu hóa mục tiêu bảo mật bằng việc công khai chính token.

## 10. Cách thu thập bằng chứng mà không tuyên bố quá mức

### 10.1. Kiểm tra cấu trúc và encoding

Các kiểm tra có ích gồm:

- Đầu ra có đúng bảng ký tự và độ dài đã đặc tả không?
- Giải mã có nhận lại đủ số byte ban đầu không?
- Token có đi qua proxy, cookie parser và kho lưu mà không thay đổi không?
- Các đường phát hành cho web, mobile, quản trị hoặc công việc nền có dùng cùng chính sách cần thiết không?
- Có giới hạn đầu vào hợp lý để từ chối chuỗi quá dài mà không gây chi phí xử lý bất thường không?

Kiểm tra độ dài và round-trip chỉ chứng minh thuộc tính biểu diễn. Chúng không chứng minh bộ sinh có tính khó dự đoán.

### 10.2. Thống kê đầu ra chỉ là dấu hiệu bổ sung

Thu thập token mẫu trong môi trường kiểm thử có thể giúp phát hiện lỗi rõ ràng như hằng số, tiền tố bất ngờ, khoảng đếm hoặc lặp chuỗi sau restart. Nhưng cần diễn giải đúng:

- Không có token trùng trong một triệu mẫu không chứng minh đạt 128 bit entropy.
- Tần suất bit có vẻ cân bằng không chứng minh khả năng chống dự đoán.
- Một bộ sinh có seed dễ đoán vẫn có thể tạo đầu ra vượt nhiều kiểm tra thống kê đơn giản.
- Một sai lệch ngẫu nhiên nhỏ trong mẫu cũng không tự chứng minh bộ sinh mật mã bị lỗi.

Bằng chứng chính đến từ thiết kế, nguồn ngẫu nhiên, implementation, cấu hình và cách bảo vệ trạng thái. Kết quả thống kê đóng vai trò phát hiện hồi quy hoặc bất thường, không phải giấy chứng nhận an toàn.

### 10.3. Kiểm thử lỗi và tính nguyên vẹn

Một số ca kiểm thử có giá trị hơn việc cố đoán ngẫu nhiên token:

| Tình huống | Điều cần quan sát |
|---|---|
| Bộ sinh trả lỗi | Không phát hành token yếu hoặc tạo phiên thiếu định danh |
| Hai lần phát hành nhận cùng token trong kiểm thử | Không ghi đè hoặc liên kết nhầm chủ thể |
| Hai node cùng tạo khóa bị ép trùng | Thao tác tạo có bảo đảm nhất quán, không dựa vào kiểm tra trước khi ghi |
| Cột lưu ngắn hơn định dạng | Cấu hình bị phát hiện hoặc thao tác thất bại rõ ràng, không âm thầm cắt token |
| Thay đổi hoa thường trong token Base64url | Không vô tình nhận thành token gốc do collation không phù hợp |
| Token đúng định dạng nhưng không tồn tại | Không tạo quyền hoặc nhận diện một phiên bất kỳ |
| Gây lỗi tạo token sau xác thực thông tin đăng nhập | Không trả phiên nửa hoàn tất hoặc làm lộ secret trong lỗi |

Các token mẫu, dump bộ nhớ hoặc dữ liệu chẩn đoán có chứa token phải được xử lý như dữ liệu bí mật. Không thu thập hàng loạt token production chỉ để chạy một bài kiểm tra thống kê không có phạm vi và cơ chế bảo vệ rõ ràng.

## 11. Ranh giới của biện pháp tăng entropy

Entropy cao giảm khả năng đoán hoặc dự đoán giá trị bí mật. Nó không tự xử lý những đường chiếm phiên khác:

| Đường tấn công hoặc lỗi | Tăng số byte ngẫu nhiên có giải quyết không? | Nhóm yêu cầu cần xem thêm |
|---|---|---|
| Đoán token của phiên còn hiệu lực | Có tác dụng trực tiếp trong mô hình thích hợp | CSPRNG, ngân sách tấn công, giới hạn thử |
| Token lộ trong log hoặc URL | Không | Giảm rò rỉ và kiểm soát truy cập dữ liệu chẩn đoán |
| Token bị đọc từ client hoặc truyền tải | Không | Bảo vệ kênh và nơi lưu token |
| Token bị cố định trước khi đăng nhập | Không | Quy tắc tiếp nhận và thay thế định danh phiên |
| Phiên đã hết hạn nhưng vẫn được chấp nhận | Không | Kiểm tra thời gian hiệu lực và trạng thái phiên |
| Một phiên được gắn nhầm identity hoặc tenant | Không | Ràng buộc dữ liệu phiên và authorization |
| Bộ sinh bị lộ trạng thái | Không thể khắc phục chỉ bằng tăng chiều dài đầu ra | Bảo vệ trạng thái, xử lý sự cố và đánh giá lại phiên chịu ảnh hưởng |

Một bản đặc tả tốt phải nối đúng mối đe dọa với đúng kiểm soát. “Session ID dài 64 ký tự” chỉ mô tả hình thức. Yêu cầu có thể kiểm chứng phải nêu phần bí mật được sinh như thế nào, có độ mạnh nào, được bảo toàn ra sao, đối chiếu với ngân sách tấn công nào và được chứng minh bằng loại bằng chứng nào.
