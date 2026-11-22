# Không dùng `hashCode()` làm mã định danh duy nhất hoặc mã bảo mật

Trong Java, `hashCode()` trả về một số nguyên `int` dùng chủ yếu để hỗ trợ các cấu trúc dữ liệu dựa trên băm như `HashMap` và `HashSet`. Số này giúp phân phối và tra cứu phần tử hiệu quả, nhưng **không phải mã định danh duy nhất**, **không phải bí mật**, và **không phải hàm băm mật mã**. Hai đối tượng khác nhau có thể có cùng `hashCode()`, còn một hash dễ tính lại không chứng minh được ai đã tạo ra dữ liệu.

Bài học nằm trong **hợp đồng `hashCode` của Java**: hiểu chính xác điều gì được bảo đảm, vì sao dùng hash làm ID hoặc cơ chế bảo mật là sai, và chọn công cụ thay thế theo mục đích.

## 1. Hợp đồng `hashCode()` thực sự nói gì?

Mỗi lớp Java đều có `hashCode()` kế thừa từ `Object`, và lớp có thể ghi đè phương thức đó. Hợp đồng cốt lõi là:

1. Khi trạng thái tham gia `equals` không thay đổi trong **cùng một lần thực thi ứng dụng**, các lần gọi `hashCode()` trên một đối tượng phải cho kết quả nhất quán.
2. **Nếu `a.equals(b)` là `true`, thì `a.hashCode() == b.hashCode()` bắt buộc đúng.**
3. Nếu `a.equals(b)` là `false`, hai hash code **được phép bằng nhau**. Sinh hai giá trị khác nhau thường giúp hiệu năng tốt hơn, nhưng không phải yêu cầu bắt buộc.

Diễn đạt bằng logic:

```text
a.equals(b) == true  => a.hashCode() == b.hashCode()
a.hashCode() == b.hashCode() =/=> a.equals(b) == true
```

Chiều suy luận thứ hai **không hợp lệ**. Hash là công cụ thu hẹp các khả năng tra cứu, không thay thế bước kiểm tra bằng nhau.

Một lưu ý về `null`: không được gọi `null.hashCode()`. Nếu cần hash an toàn với `null`, dùng `Objects.hashCode(x)` (trả về `0` với `null`) hoặc `Objects.hash(...)` khi tính băm kết hợp nhiều trường.

## 2. Vì sao hash code không thể được coi là mã duy nhất?

### 2.1. Miền giá trị `int` có giới hạn

`hashCode()` trả về **`int` 32 bit**, tức chỉ có `2^32` (4.294.967.296) mẫu bit khác nhau, bao gồm cả số âm. Tập đối tượng hoặc giá trị đầu vào có thể cần phân biệt không bị giới hạn bởi số mẫu bit của một `int`. Theo nguyên lý chuồng bồ câu, nếu số giá trị cần gán vượt số hash khả dụng, **va chạm (collision) là điều không tránh khỏi**.

Ngay cả trước khi đạt giới hạn trên, một thuật toán băm cụ thể đã có thể tạo va chạm. Không có hợp đồng nào nói phải dùng hết `2^32` giá trị hoặc phân phối các giá trị một cách hoàn hảo.

### 2.2. Hai giá trị khác nhau có thể cho hash giống nhau

Trong Java, hai chuỗi **`"FB"` và `"Ea"`** có nội dung khác nhau nhưng có cùng `String.hashCode()`:

```text
"FB": 31 * 'F' + 'B' = 31 * 70 + 66 = 2236
"Ea": 31 * 'E' + 'a' = 31 * 69 + 97 = 2236
```

Với chuỗi hai ký tự trên, phép tính tuân theo thuật toán `String.hashCode()` được Java quy định; đây là **va chạm xác định**, không phải điều cần chờ ngẫu nhiên xảy ra. `"FB".equals("Ea")` vẫn là `false`.

Lớp tự định nghĩa `hashCode()` cũng có thể trả về cùng một số cho mọi đối tượng. Điều đó gây hiệu năng băm kém nhưng **không tự nó vi phạm hợp đồng** nếu `equals` và `hashCode` vẫn nhất quán.

### 2.3. Hash trùng không có nghĩa là cùng instance

`System.identityHashCode(obj)` bỏ qua cách lớp ghi đè `hashCode()` và lấy hash theo ngữ nghĩa danh tính mặc định của `Object`. Tuy nhiên, **identity hash code vẫn có thể va chạm** và không phải địa chỉ bộ nhớ. Nếu cần kiểm tra hai tham chiếu có trỏ tới cùng một đối tượng trong Java hay không, dùng `a == b`.

Không được tạo một bản đồ `Map<Integer, Object>` với `obj.hashCode()` làm khóa duy nhất rồi kết luận hash trùng là cùng đối tượng. Cách làm này có thể ghi đè nhầm bản ghi của đối tượng khác.

## 3. Ví dụ Java 17+: HashMap xử lý va chạm bằng `equals`

Chương trình dưới đây kết hợp va chạm có thật của `String` với một lớp cố tình trả về cùng một hash, để làm rõ rằng **băm trùng không xóa bỏ tính khác nhau của các khóa**.

Lưu thành `HashCodeNotIdentityDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

final class Key {
    private final String id;

    Key(String id) {
        this.id = Objects.requireNonNull(id);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof Key other)) {
            return false;
        }
        return id.equals(other.id);
    }

    @Override
    public int hashCode() {
        return 7; // Hợp đồng vẫn đúng nhưng mọi Key đều va chạm.
    }
}

public class HashCodeNotIdentityDemo {
    public static void main(String[] args) {
        String first = "FB";
        String second = "Ea";

        System.out.println("FB hash: " + first.hashCode());
        System.out.println("Ea hash: " + second.hashCode());
        System.out.println("FB equals Ea: " + first.equals(second));

        Set<String> words = new HashSet<>();
        words.add(first);
        words.add(second);
        System.out.println("HashSet size: " + words.size());

        Key a1 = new Key("A");
        Key a2 = new Key("A");
        Key b = new Key("B");
        System.out.println("A equals B: " + a1.equals(b));
        System.out.println("A equals another A: " + a1.equals(a2));
        System.out.println("A/B hashes equal: "
                + (a1.hashCode() == b.hashCode()));

        Map<Key, String> labels = new HashMap<>();
        labels.put(a1, "first");
        labels.put(b, "second");
        System.out.println("HashMap size: " + labels.size());
        System.out.println("Lookup new A: " + labels.get(a2));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac HashCodeNotIdentityDemo.java
java HashCodeNotIdentityDemo
```

Đầu ra **xác định**:

```text
FB hash: 2236
Ea hash: 2236
FB equals Ea: false
HashSet size: 2
A equals B: false
A equals another A: true
A/B hashes equal: true
HashMap size: 2
Lookup new A: first
```

Các điều cần hiểu từ kết quả:

- `"FB"` và `"Ea"` có cùng hash 2236, nhưng `equals` trả `false`, nên `HashSet` lưu được cả hai.
- `Key.hashCode()` cố ý trả `7` cho mọi instance; `Key("A")` và `Key("B")` vẫn là hai khóa khác nhau vì `Key.equals` so sánh `id`.
- Hai `Key("A")` có cùng giá trị `id` và cùng hash nên `labels.get(a2)` tìm được bản ghi đặt bằng `a1`, dù `a1` và `a2` là hai instance.
- `HashMap` sử dụng hash để chọn vùng tra cứu, rồi dùng cơ chế so khớp khóa (trong đó có `equals`) để phân biệt phần tử va chạm. **Tự lấy `hashCode` làm ID và bỏ qua `equals` sẽ làm mất bước phân biệt quan trọng này.**
- Trả một hằng số trong `Key.hashCode()` chỉ nhằm minh họa tính đúng đắn khi có va chạm; **không phải cách cài đặt được khuyến nghị** vì nhiều va chạm làm giảm hiệu năng. Thực tế nên băm các trường tham gia `equals` bằng `Objects.hash(...)` hoặc thuật toán nhất quán phù hợp.

## 4. Vì sao không dùng `hashCode()` làm ID lưu trữ lâu dài?

Ngay cả khi tạm thời chưa quan sát va chạm, một hash code vẫn thiếu những tính chất cần có ở mã định danh.

| Yêu cầu đối với ID | Giới hạn của `hashCode()` |
| --- | --- |
| Phân biệt duy nhất các thực thể trong phạm vi hệ thống | Hash có thể va chạm, kể cả hai đối tượng không bằng nhau |
| Giữ ổn định qua vòng đời lưu trữ, tái khởi động và triển khai | `Object.hashCode()`/identity hash không có bảo đảm ổn định giữa các lần chạy; cách lớp ghi đè hash cũng có thể đổi |
| Không thay đổi khi thuộc tính trình bày thay đổi | Hash dựa trên các trường có thể thay đổi sẽ đổi theo trạng thái |
| Tương thích giữa các dịch vụ hoặc ngôn ngữ | Không có hợp đồng chung đảm bảo thuật toán `hashCode` tự định nghĩa tương thích giữa các hệ thống |
| Không để lộ một giá trị có thể đoán trước trong tình huống nhạy cảm | `hashCode()` không được thiết kế có tính bí mật hoặc khó dự đoán |

Cần phân biệt hai trường hợp:

1. **`String.hashCode()`** được quy định theo nội dung ký tự, nên với cùng chuỗi, thuật toán cho cùng kết quả qua các lần chạy Java. Điều này **không biến nó thành ID duy nhất hoặc bảo mật**: chuỗi khác nhau vẫn có thể trùng hash và ai cũng có thể tính lại kết quả.
2. **`Object.hashCode()` mặc định** gắn với cơ chế hashing danh tính của JVM, không mang hợp đồng ổn định xuyên các lần chạy. Không thể coi mã hash đó là khóa database hay địa chỉ đối tượng.

Nếu lớp override `hashCode()` bằng các trường mutable, giá trị băm còn có thể thay đổi khi trường thay đổi. Việc dùng đối tượng ấy làm khóa `HashMap` trước và sau khi thay đổi thường dẫn tới lỗi tra cứu. Hãy ưu tiên giá trị khóa bất biến, và cấp **ID riêng không phụ thuộc hash** khi đối tượng cần được nhận diện lâu dài.

### Chọn ID thay thế theo phạm vi

- **ID cơ sở dữ liệu:** khóa chính được database quản lý, như `BIGINT` sinh theo sequence/identity hoặc UUID; áp đặt ràng buộc `PRIMARY KEY`/`UNIQUE` để ngăn bản ghi trùng trong phạm vi quy định.
- **ID trao đổi giữa nhiều tiến trình hoặc dịch vụ:** UUID do hệ thống cấp phát (ví dụ `UUID.randomUUID()`) là lựa chọn thông dụng khi không có bộ cấp phát tập trung. UUID ngẫu nhiên giảm xác suất trùng xuống rất thấp trong điều kiện sử dụng phù hợp, nhưng **không phải bảo đảm toán học tuyệt đối**; nơi lưu trữ vẫn nên kiểm tra duy nhất.
- **Chỉ cần kiểm tra cùng đối tượng trong một JVM:** dùng `==` trên các reference; với map cần phân biệt instance, cân nhắc `IdentityHashMap` nếu đúng ngữ nghĩa bài toán.
- **ID tăng tuần tự trong một tiến trình:** một bộ đếm như `AtomicLong` có thể cấp các số phân biệt khi không vượt phạm vi, nhưng phải tự quản lý khởi tạo lại, tràn số và tính duy nhất giữa các tiến trình. Đây là giải pháp cấp ID có chủ đích, không phải `hashCode()`.

Đừng dùng `Integer.toHexString(obj.hashCode())` rồi coi chuỗi hệ 16 là một ID mới; chuyển cách biểu diễn **không tăng thông tin hoặc ngăn va chạm**.

## 5. Vì sao `hashCode()` không phải mã bảo mật?

Một hàm băm dùng cho collection và một công cụ mật mã có mục tiêu khác nhau:

| Tính chất | `hashCode()` Java | Công cụ phù hợp với bảo mật |
| --- | --- | --- |
| Mục tiêu chính | Phân phối khóa, hỗ trợ tra cứu | Chống giả mạo, dẫn xuất khóa, lưu mật khẩu hoặc tạo token tùy mục đích |
| Đầu ra | `int` 32 bit | Kích thước và thuật toán tùy yêu cầu, thường lớn hơn nhiều |
| Chống tìm giá trị đầu vào khi biết hash | Không bảo đảm | Password hashing/KDF chậm, có salt và chi phí tính toán |
| Chống kẻ tấn công cố tìm va chạm | Không bảo đảm | Hàm băm mật mã khi cần khả năng chống va chạm |
| Xác thực nguồn gốc dữ liệu | Không | HMAC hoặc chữ ký số dựa trên khóa đúng cách |
| Tạo chuỗi bí mật khó đoán để xác thực | Không | Bộ sinh số ngẫu nhiên mật mã như `SecureRandom` |

Các sai lầm thường gặp:

- **Lưu mật khẩu thành `password.hashCode()`:** miền 32 bit rất nhỏ, thuật toán rẻ, không salt và dễ tính thử hàng loạt. Khi cần lưu mật khẩu, dùng thuật toán chuyên dụng như **Argon2id**, **scrypt**, **bcrypt** hoặc **PBKDF2**, với salt ngẫu nhiên, tham số chi phí phù hợp và thư viện được bảo trì.
- **Dùng `userId.hashCode()` làm session ID, mã khôi phục mật khẩu, mã xác nhận hoặc API token:** đầu vào có thể đoán được và hash có thể bị tính lại. Kẻ tấn công không cần biết bí mật để tạo lại giá trị.
- **Gắn `message.hashCode()` để chứng minh dữ liệu không bị sửa trái phép:** bất kỳ ai sửa dữ liệu cũng có thể tính lại hash; hơn nữa va chạm rất dễ xuất hiện. Để kiểm chứng tính toàn vẹn và nguồn gốc trong mô hình có khóa chia sẻ, dùng **HMAC**; trong mô hình khóa công khai, cân nhắc **chữ ký số**.
- **Cho rằng chỉ cần chuyển hash sang hex hoặc Base64 sẽ an toàn:** đây chỉ là mã hóa biểu diễn, không tạo tính bí mật hoặc xác thực.

`MessageDigest` với SHA-256 cung cấp **hàm băm mật mã**, nhưng bản thân SHA-256 không phải cơ chế lưu mật khẩu tối ưu (vì quá nhanh), cũng không phải cơ chế xác thực người gửi khi thiếu khóa. Mỗi nhu cầu bảo mật cần đúng primitive.

### Ví dụ tạo token bí mật với `SecureRandom`

Để có thể biên dịch và chạy độc lập, lưu ví dụ Java 17 sau vào `SecureTokenDemo.java`. Chương trình chỉ in **độ dài** của token, không làm lộ token bí mật ra stdout.

```java
import java.security.SecureRandom;
import java.util.Base64;

public class SecureTokenDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();
        byte[] bytes = new byte[32]; // 256 bit ngẫu nhiên
        secureRandom.nextBytes(bytes);

        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
        System.out.println("token length = " + token.length());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 SecureTokenDemo.java
java SecureTokenDemo
```

Stdout (256 bit = 32 byte, Base64 URL-safe không padding nên có 43 ký tự):

```text
token length = 43
```

`SecureRandom` tạo byte khó đoán theo cơ chế mật mã; Base64 URL-safe chỉ biểu diễn số byte đó thành chuỗi thuận tiện để gửi qua HTTP. Token là một **bí mật truy cập**: cần truyền qua HTTPS, giới hạn thời gian và quyền sử dụng, bảo vệ khi lưu trữ và không ghi nguyên token vào log. Không có giá trị stdout cố định vì token được sinh ngẫu nhiên. Không nên thay `SecureRandom` bằng `hashCode()`, `System.currentTimeMillis()` hay `java.util.Random` khi cần bí mật.

## 6. Phân biệt các API dễ bị nhầm

- **`obj.hashCode()`:** theo cài đặt của lớp; với value object thường phụ thuộc các trường có ý nghĩa trong `equals`.
- **`Objects.hashCode(obj)`:** tiện ích an toàn `null`, trả `0` cho `null`, còn lại gọi `obj.hashCode()`.
- **`Objects.hash(a, b, ...)`:** hash tổng hợp nhiều giá trị, hữu ích khi tự viết `hashCode()`. Vẫn chỉ là băm dạng `int`, không duy nhất và không có bảo đảm mật mã.
- **`System.identityHashCode(obj)`:** hash theo danh tính mặc định, kể cả khi lớp override `hashCode`; vẫn có va chạm, không phải địa chỉ bộ nhớ hay ID ổn định xuyên phiên chạy.
- **`MessageDigest` (ví dụ SHA-256):** công cụ băm mật mã cho dữ liệu byte; không thay `equals` trong collection và không tự tạo bí mật.
- **`SecureRandom`:** sinh giá trị ngẫu nhiên mật mã để tạo token/nonce phù hợp. Mã định danh ngẫu nhiên cũng cần quy trình kiểm soát va chạm và vòng đời.
- **`UUID.randomUUID()`:** tiện ích sinh UUID phiên bản 4; hữu ích cho ID phân tán, nhưng UUID hiển thị công khai không mặc nhiên đóng vai trò mật khẩu hoặc quyền truy cập.

## 7. Checklist thiết kế

Trước khi chọn một trường làm khóa, hãy tự hỏi:

1. **Cần so sánh bằng nhau hay cần duy nhất?** Nếu dùng collection dựa trên hash, viết `equals`/`hashCode` đúng hợp đồng; collection tự xử lý va chạm. Nếu cần ID duy nhất, cấp và quản lý ID riêng.
2. **Khóa có vượt phạm vi một lần chạy JVM không?** Nếu có, đừng dựa vào identity hash hoặc bất kỳ hash code nào không có hợp đồng ổn định phù hợp.
3. **Dữ liệu được dùng để xác thực hay ngăn giả mạo không?** Nếu có, dùng API mật mã tương ứng; `hashCode` không cung cấp bảo vệ này.
4. **Có cần giữ bí mật một token không?** Nếu có, token phải khó đoán, đủ entropy và có vòng đời phù hợp; không suy từ thông tin công khai bằng `hashCode()`.
5. **Các trường tham gia `equals`/`hashCode` có thay đổi không?** Nếu thay đổi sau khi đối tượng được dùng làm key, cơ chế tra cứu có thể hỏng; ưu tiên bất biến hoặc chọn khóa khác.

**Ghi nhớ:** `hashCode()` là một **gợi ý phân nhóm/tra cứu**; nhiều đối tượng khác nhau có thể dùng chung một số băm. Nó không chứng minh danh tính, không thay thế ID lưu trữ và không đáp ứng yêu cầu mật mã. Hãy dùng `equals` khi cần xác định bằng nhau, cấp ID theo phạm vi dữ liệu, và chọn primitive bảo mật chuyên dụng cho xác thực hoặc tạo bí mật.
