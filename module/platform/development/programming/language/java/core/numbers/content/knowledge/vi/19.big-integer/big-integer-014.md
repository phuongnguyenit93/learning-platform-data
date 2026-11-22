# Kiểm tra số nguyên tố xác suất và ý nghĩa certainty với BigInteger

> **Java core – numbers · BigInteger**  
> **Mục tiêu:** Hiểu kết quả của `BigInteger.isProbablePrime(int certainty)`, cách diễn giải cận sai số xác suất, các trường hợp biên (đặc biệt `certainty <= 0`), và sự khác nhau giữa kiểm tra một ứng viên, sinh probable prime và chứng minh nguyên tố. Bài sử dụng Java 17+.

## 1. Số nguyên tố và vì sao cần thuật toán xác suất?

Một số nguyên tố là **số nguyên dương lớn hơn 1** có đúng hai ước dương là 1 và chính nó. Ví dụ 2, 3, 5, 7, 11, 17, 97 là các số nguyên tố; 0, 1, −17, 21 và 561 không phải số nguyên tố theo định nghĩa đó.

Với số nhỏ, có thể thử chia bởi các số nguyên từ 2 đến căn bậc hai của n. Nhưng một `BigInteger` có thể chứa số dài hàng trăm hoặc hàng nghìn bit. Việc thử tất cả các ước nhỏ ở miền đó quá tốn kém. Java có phép thử nhanh theo xác suất:

```java
import java.math.BigInteger;

BigInteger n = new BigInteger("1000000007");
boolean probable = n.isProbablePrime(80);

System.out.println(probable); // true
```

Tên gọi **isProbablePrime** rất có chủ đích: phương thức không trả về chứng minh nguyên tố chính xác vô điều kiện. Nó kiểm tra ứng viên theo một mức tin cậy do caller đưa vào.

Ba thao tác dễ nhầm:

| Câu hỏi | API |
| --- | --- |
| Giá trị n đã có có khả năng là nguyên tố không? | `n.isProbablePrime(certainty)` |
| Sinh một giá trị ngẫu nhiên dương có đúng k bit và probably prime? | `BigInteger.probablePrime(k, rnd)` |
| Tìm probable prime đầu tiên lớn hơn n? | `n.nextProbablePrime()` |

Trong các ứng dụng nghiêm ngặt, cần phân biệt **probable prime** với **proven prime**: phép thử xác suất không tự tạo chứng chỉ để người khác xác minh n là nguyên tố.

## 2. Chữ ký và hai kiểu kết luận không đối xứng

Chữ ký trong `java.math.BigInteger`:

```java
public boolean isProbablePrime(int certainty)
```

Khi `certainty > 0`:

- `false`: số **chắc chắn là hợp số** theo hợp đồng Javadoc; phép thử đã loại ứng viên.
- `true`: số **probably prime** với mức tin cậy liên quan đến tham số `certainty`; chưa phải một chứng minh toán học tuyệt đối.

Ví dụ:

```java
System.out.println(BigInteger.valueOf(17)
        .isProbablePrime(80)); // true
System.out.println(BigInteger.valueOf(21)
        .isProbablePrime(80)); // false
```

Không đảo ý nghĩa thành “`false` là *probably composite* còn `true` là *definitely prime*”. Tư duy đúng là: nếu có bằng chứng hợp số, loại ngay; nếu chưa tìm thấy, coi là ứng viên nguyên tố theo xác suất của thuật toán.

**Điều kiện đầu vào:** vì khái niệm nguyên tố chỉ áp dụng cho n ≥ 2, nên một phương thức nghiệp vụ nên kiểm tra điều kiện này ngay cả khi implementation JDK có quy tắc xử lý các số âm.

## 3. certainty đại diện cho điều gì?

Javadoc Java 17 mô tả `certainty` là **mức bất định mà caller sẵn sàng chấp nhận**. Khi `isProbablePrime(certainty)` trả true, tài liệu nêu xác suất n là nguyên tố vượt:

\[
1 - \frac{1}{2^{\mathrm{certainty}}}.
\]

Theo cách diễn giải cận sai số trong mô hình của API, phần rủi ro còn lại được biểu thị bởi `2^-certainty`. certainty càng lớn thì yêu cầu tin cậy càng cao; kiểm tra thường có chi phí tính toán lớn hơn.

| certainty | `2^-certainty` (xấp xỉ) |
| ---: | ---: |
| 1 | 0,5 |
| 10 | 9,77×10^-4 |
| 20 | 9,54×10^-7 |
| 40 | 9,09×10^-13 |
| 80 | 8,27×10^-25 |
| 100 | 7,89×10^-31 |
| 128 | 2,94×10^-39 |

Ví dụ khi truyền 80, tài liệu diễn đạt một mức tin cậy cao, không phải yêu cầu chính xác 80 vòng kiểm tra.

### Không đồng nhất cận xác suất với xác suất hậu nghiệm của một số cố định

Một số nguyên n xác định **hoặc nguyên tố hoặc hợp số**. Nếu n cố định, thuộc tính đó không tự biến thành xác suất theo cách đếm. Sự bất định xuất phát từ lựa chọn thuật toán kiểm tra, các yếu tố xác suất/giả định và dữ liệu ứng viên. Do đó không nên nói:

> “Xác suất toán học chính xác n=... là nguyên tố bằng 1−2^-80.”

Đó không phải suy luận Bayes tự động hợp lệ cho mọi n do đối thủ cố ý chọn. Cách diễn đạt đúng trong thiết kế phần mềm là **dựa vào mức bảo đảm xác suất của API khi phép thử trả probable prime**, đồng thời xét chính sách sinh ứng viên và mô hình rủi ro hệ thống.

### certainty KHÔNG phải số vòng Miller–Rabin

`certainty=80` không bảo đảm có **đúng 80 vòng** Miller–Rabin. Số vòng thực tế và những phép thử bổ sung phụ thuộc implementation, độ dài bit của số và các tối ưu. Không viết mã dựa trên giả định “certainty chính là số lần lặp”.

Dùng `certainty` như tham số chất lượng, không phải tham số điều khiển vòng lặp hay thời gian chạy chính xác. Với yêu cầu kiểm toán thuật toán, xem đặc tả tiêu chuẩn hoặc implementation cụ thể thay vì đoán từ chữ ký.

## 4. Cạm bẫy lớn nhất: certainty <= 0 luôn trả true

Javadoc quy định rõ ràng: nếu `certainty <= 0`, `isProbablePrime` trả **true**, bất kể giá trị kiểm tra.

```java
BigInteger nine = BigInteger.valueOf(9);

System.out.println(nine.isProbablePrime(0));   // true
System.out.println(nine.isProbablePrime(-5));  // true
System.out.println(nine.isProbablePrime(80));  // false
```

Số 9 vẫn là hợp số `3×3`. Kết quả true của hai lời gọi đầu **không chứng minh** hay thậm chí cho mức tin cậy hữu ích về tính nguyên tố.

```java
System.out.println(BigInteger.ZERO.isProbablePrime(0)); // true
System.out.println(BigInteger.ONE.isProbablePrime(-1)); // true
```

**Không dùng 0 hay số âm để nhờ Java tự chọn mức mặc định.** Nếu certainty đọc từ cấu hình, env var, HTTP parameter hay database, phải validate `certainty > 0` trước khi gọi API.

Một helper rõ ý định:

```java
static boolean probablyPrimePositive(BigInteger n, int certainty) {
    if (certainty <= 0) {
        throw new IllegalArgumentException("certainty must be positive");
    }
    if (n == null || n.compareTo(BigInteger.TWO) < 0) {
        return false;
    }
    return n.isProbablePrime(certainty);
}
```

Đây là **phương thức minh họa** cần đặt trong một lớp. Chính sách null có thể được thiết kế là ném lỗi thay vì trả false; quan trọng là phải nói rõ trong API.

## 5. Số âm, 0, 1, 2 và những trường hợp biên

Theo định nghĩa nguyên tố:

| n | Có phải số nguyên tố? |
| ---: | --- |
| −17 | Không |
| −2 | Không |
| 0 | Không |
| 1 | Không |
| 2 | Có |
| 3 | Có |
| 4 | Không |
| 17 | Có |
| 21 | Không |

Với certainty dương, những tình huống thường dùng:

```java
System.out.println(BigInteger.ZERO.isProbablePrime(80)); // false
System.out.println(BigInteger.ONE.isProbablePrime(80));  // false
System.out.println(BigInteger.TWO.isProbablePrime(80));  // true
System.out.println(BigInteger.valueOf(100).isProbablePrime(80)); // false
```

### Tại sao cần kiểm tra n ≥ 2 trước API?

Trong OpenJDK 17, implementation `isProbablePrime` lấy **giá trị tuyệt đối** khi thử số:

```java
BigInteger negative = BigInteger.valueOf(-17);
System.out.println(negative.isProbablePrime(80));
// true trên OpenJDK 17
```

Độ lớn 17 là nguyên tố, nhưng **−17 không phải số nguyên tố dương**. Không lấy raw boolean từ API này làm quyết định nghiệp vụ trước khi enforce miền hợp lệ.

```java
boolean accepted = negative.compareTo(BigInteger.TWO) >= 0
        && negative.isProbablePrime(80);

System.out.println(accepted); // false
```

Quy tắc giá trị âm có thể là chi tiết triển khai; bằng cách validate n ≥ 2, code không phụ thuộc vào hành vi này để định nghĩa nguyên tố.

## 6. So sánh với phép thử chia xác định cho số nhỏ

Một kiểm tra **deterministic** cho số `long` nhỏ:

```java
static boolean trialPrime(long n) {
    if (n < 2) return false;
    if ((n & 1L) == 0L) return n == 2;
    for (long d = 3; d <= n / d; d += 2) {
        if (n % d == 0L) {
            return false;
        }
    }
    return true;
}
```

Hàm thử các ước lẻ đến √n. Điều kiện `d <= n/d` an toàn hơn kiểm tra `d*d <= n` vì phép nhân có thể overflow ở miền long lớn. Nếu thấy ước số, n là hợp số; nếu không có, n là nguyên tố.

```java
System.out.println(trialPrime(97));  // true
System.out.println(trialPrime(561)); // false
```

Nhược điểm: với số lớn gần giới hạn `long`, thử chia có thể chậm; với một BigInteger hàng trăm bit, thử chia thô không khả thi. Đó là lý do các phép thử nguyên tố hiện đại dùng số học modulo và chiến lược xác suất.

**Mục đích của trial division ở đây:** làm oracle nhỏ dễ tin cậy khi kiểm thử probable-prime API, chứ không phải cách sinh nguyên tố kích thước khóa mật mã.

## 7. Fermat và số Carmichael 561: vì sao một test đơn giản chưa đủ

Định lý nhỏ Fermat nói: nếu p nguyên tố và a không chia hết cho p thì:

\[
a^{p-1} \equiv 1 \pmod p.
\]

Java có phương thức `modPow` để tính lũy thừa modulo hiệu quả, không cần tạo một số `a^(p−1)` khổng lồ rồi mới chia:

```java
BigInteger n = BigInteger.valueOf(561);
BigInteger residue = BigInteger.TWO.modPow(
        n.subtract(BigInteger.ONE), n);

System.out.println(residue); // 1
```

Nếu áp dụng phép kiểm tra Fermat một cách ngây thơ, một người có thể cho 561 là nguyên tố. Nhưng:

\[
561 = 3\times11\times17.
\]

561 là **hợp số Carmichael**. Nó vượt qua các phép kiểm tra Fermat với nhiều cơ số, nên một kết quả `a^(n−1) mod n = 1` **không đủ chứng minh n nguyên tố**.

```java
System.out.println(
        BigInteger.valueOf(561).isProbablePrime(80)); // false
```

Thuật toán probable-prime của Java mạnh hơn kiểm tra Fermat một cơ số đơn lẻ trong ví dụ này. Tuy nhiên **không suy ra** rằng mọi hợp số khác đều bắt buộc bị phát hiện bởi mọi phép thử xác suất với certainty hữu hạn.

## 8. Trực giác về Miller–Rabin: tìm chứng cứ hợp số

Một kỹ thuật kiểm tra nguyên tố xác suất quan trọng là *Miller–Rabin*. Với số lẻ n>2, ta phân tích:

\[
n-1 = 2^s d,\quad d\text{ lẻ}.
\]

Sau đó chọn cơ số a và tính các lũy thừa/bình phương modulo n. Nếu chuỗi giá trị vi phạm những tính chất bắt buộc với số nguyên tố, ta phát hiện **chứng cứ hợp số** (*witness*).

- Có witness hợp số → loại ứng viên.
- Không tìm được witness trong các phép thử → ứng viên là *probable prime* theo phép thử đã dùng.
- Nhiều vòng/chiến lược thử phù hợp làm nguy cơ hợp số lọt qua thấp hơn.
- Kết quả pass **không tự tạo chứng chỉ primality**.

Không cần tự triển khai Miller–Rabin để sử dụng `BigInteger.isProbablePrime`. Tự triển khai dễ mắc lỗi ở các trường hợp n=2, n chẵn, phân tích n−1, chọn cơ số, thao tác modulo và randomness.

JDK có thể phối hợp các bước kiểm tra và sàng số nhỏ, tùy phiên bản. Vì thế tránh diễn đạt “`BigInteger.isProbablePrime` chắc chắn chỉ chạy đúng một thuật toán và đúng N vòng” khi API không cam kết.

## 9. Chọn certainty: tin cậy, chi phí và rủi ro nghiệp vụ

`certainty` càng lớn, mức cam kết kiểm tra càng cao và chi phí thường lớn hơn. Không có một giá trị duy nhất phù hợp mọi hệ thống.

Ví dụ một ứng dụng có thể chọn:

```java
private static final int PRIME_CERTAINTY = 100;
```

Nhưng `100` chỉ là một **giá trị minh họa** có mức tin cậy cao; nó không tự bảo đảm toàn bộ quy trình sinh khóa đáp ứng một tiêu chuẩn mật mã cụ thể.

Hãy quyết định theo:

1. **Hậu quả nếu một hợp số bị chấp nhận.**
2. **Số lượng ứng viên** mà hệ thống chấp nhận trong cả vòng đời.
3. **Độ dài bit** của ứng viên và chi phí CPU/bộ nhớ.
4. **Yêu cầu kiểm toán:** probable prime có đủ, hay cần chứng chỉ nguyên tố?
5. **Nguồn sinh và phân phối ứng viên**, nhất là nếu dữ liệu có thể do đối thủ tạo.
6. **Phiên bản JDK, thư viện hoặc chuẩn kỹ thuật** cần tuân thủ.

Nhiều lời gọi trong một dịch vụ tạo ra một bài toán **rủi ro tổng hợp**. Không được suy ra rằng lặp n lần luôn cho xác suất lỗi bằng đúng `n×2^-certainty` hoặc các lần kiểm tra độc lập; phải xét giả định về các biến cố. Trong các lập luận bảo thủ có thể dùng *union bound* cho cận lỗi khi các tiền đề phù hợp.

**Không dùng certainty rất lớn tùy tiện** với mục tiêu “bảo đảm tuyệt đối”: tính xác suất không trở thành chứng minh chỉ vì tham số lớn; chi phí tài nguyên có thể tăng.

## 10. isProbablePrime kiểm tra; probablePrime sinh ứng viên

Hai lời gọi trông gần giống nhưng phục vụ hai mục tiêu:

```java
// Kiểm tra n đã có:
boolean checked = n.isProbablePrime(80);

// Tạo một ứng viên nguyên tố ngẫu nhiên có 64 bit:
BigInteger generated = BigInteger.probablePrime(
        64, new java.security.SecureRandom());
```

`BigInteger.probablePrime(int bitLength, Random rnd)` trả **số dương có đúng độ dài bit được yêu cầu** và là probable prime. Javadoc Java 17 quy định xác suất kết quả sinh ra là hợp số **không vượt quá `2^-100`**.

- `bitLength` phải ≥2 và nằm trong giới hạn implementation.
- Giá trị cụ thể phụ thuộc nguồn ngẫu nhiên; đừng gán một stdout số cố định cho nó.
- Tham số có kiểu `Random` nhưng nếu dùng để tạo khóa, hãy dùng `SecureRandom`.
- API chỉ sinh *probable prime* chứ không cấp chứng chỉ chứng minh nguyên tố.

Với Java:

```java
import java.math.BigInteger;
import java.security.SecureRandom;

SecureRandom random = new SecureRandom();
BigInteger p = BigInteger.probablePrime(64, random);

System.out.println(p.bitLength()); // 64
System.out.println(p.signum() > 0); // true
System.out.println(p.testBit(0));   // true: prime 64 bit là số lẻ
```

Ba thuộc tính trên ổn định dù giá trị p ngẫu nhiên thay đổi mỗi lần chạy.

## 11. Ba constructor/factory dễ nhầm

| Cách tạo | Ý nghĩa |
| --- | --- |
| `BigInteger.probablePrime(64, rnd)` | Sinh probable prime dương có đúng 64 bit |
| `new BigInteger(64, 100, rnd)` | Sinh probable prime dương có đúng 64 bit, certainty 100 |
| `new BigInteger(64, rnd)` | Sinh một số không âm ngẫu nhiên có tối đa 64 bit; **không hứa prime** |

Constructor ba tham số:

```java
BigInteger p = new BigInteger(
        64, 100, new SecureRandom());
```

cho phép đặt certainty. Javadoc khuyến nghị **dùng `probablePrime`** trừ khi có lý do cụ thể cần tự chỉ định certainty.

Constructor hai tham số:

```java
BigInteger randomBits = new BigInteger(
        64, new SecureRandom());
```

chỉ tạo số ngẫu nhiên không âm; nó có thể chẵn, có thể nhỏ hơn 2 và hoàn toàn có thể là hợp số. **Không** coi nó là probable prime.

Đặc biệt, với constructor random-bits, số bit yêu cầu là **giới hạn tối đa**, không bảo đảm `bitLength() == 64`; bit cao nhất có thể bằng 0.

## 12. nextProbablePrime: tìm ứng viên đầu tiên lớn hơn n

Một phương thức tiện ích khác:

```java
BigInteger start = BigInteger.valueOf(100);
BigInteger next = start.nextProbablePrime();

System.out.println(next); // 101
```

`nextProbablePrime()` tìm probable prime **lớn hơn** n, không bao gồm chính n:

```java
System.out.println(
        BigInteger.valueOf(2).nextProbablePrime()); // 3
```

Javadoc Java 17 mô tả cận xác suất hợp số không vượt `2^-100` với kết quả tìm được; đồng thời phương thức **không bỏ qua một số nguyên tố thực sự** nằm giữa n và kết quả.

Đối với số âm, Java ném `ArithmeticException`:

```java
try {
    BigInteger.valueOf(-5).nextProbablePrime();
} catch (ArithmeticException ex) {
    System.out.println("negative search rejected");
}
```

Không nhầm với `isProbablePrime`: một hàm **phân loại số hiện tại**, hàm kia **tìm ứng viên lớn hơn**.

### Tính ngẫu nhiên không được suy ra từ nextProbablePrime

Nếu đầu vào `start` dự đoán được, `nextProbablePrime()` cũng có kết quả dự đoán được. Đừng dùng hàm tìm số kế tiếp như cách tự động tạo khóa mật mã khó đoán mà không có quy trình chọn ứng viên ngẫu nhiên và kiểm tra khóa đầy đủ.

## 13. SecureRandom quan trọng với sinh nguyên tố cho mật mã

API sinh probable prime nhận một `Random`, nhưng loại Random không phải lúc nào cũng đáp ứng tiêu chuẩn an ninh:

```java
import java.util.Random;
import java.security.SecureRandom;

// Chỉ phục vụ demo không mật mã:
// Random predictable = new Random(123);

// Khi dùng cho ứng dụng nhạy cảm:
SecureRandom secure = new SecureRandom();
BigInteger prime = BigInteger.probablePrime(128, secure);
```

`Random` thông thường không phải bộ sinh số ngẫu nhiên mật mã. Seed cố định khiến kết quả tái lập và dễ dự đoán; không phù hợp khi số sinh ra cần bí mật.

**Một probable prime chưa phải một khóa RSA hoàn chỉnh.** Quy trình RSA còn yêu cầu độ dài khóa, số mũ công khai, quan hệ giữa các nguyên tố p/q, tính toán khóa, bảo vệ bí mật, kiểm tra tiêu chuẩn và chống lỗi triển khai. Trong phần mềm thật nên dùng `KeyPairGenerator` hoặc thư viện mật mã đã được thẩm định.

Không log seed, p, q hoặc vật liệu khóa bí mật. Bài học chỉ nên in ra các **thuộc tính không nhạy cảm** của giá trị sinh ra.

## 14. Nhận dữ liệu đầu vào không tin cậy

Không nên nhận một chuỗi thập phân hàng triệu ký tự, một `certainty` rất lớn và rồi gọi `isProbablePrime` ngay trong HTTP request mà không giới hạn.

Các biện pháp thực tế:

- Giới hạn **độ dài chuỗi số** trước khi parse.
- Xác thực cú pháp với `BigInteger(String)` và xử lý `NumberFormatException`.
- Giới hạn `n.bitLength()` phù hợp bài toán.
- Đảm bảo `n >= 2` trước khi coi giá trị là ứng viên nguyên tố.
- Đảm bảo `certainty > 0` và không lớn hơn giới hạn policy cho phép.
- Giới hạn thời gian xử lý, số lời gọi đồng thời, CPU và bộ nhớ.
- Ghi rõ trạng thái lỗi input, hợp số, probable prime; không gom hết thành một boolean sai lệch.

Ví dụ helper:

```java
static boolean boundedPrimalityTest(
        BigInteger n, int certainty, int maxBits) {
    if (n == null || certainty <= 0 || maxBits < 2) {
        throw new IllegalArgumentException("Invalid input/policy");
    }
    if (n.compareTo(BigInteger.TWO) < 0) {
        return false;
    }
    if (n.bitLength() > maxBits) {
        throw new IllegalArgumentException("Too many bits");
    }
    return n.isProbablePrime(certainty);
}
```

Đây là phương thức minh họa. Giá trị `maxBits` là giới hạn nghiệp vụ, không phải ranh giới nội tại cố định của BigInteger. Production còn cần policy riêng cho chuỗi nhập, logging và giới hạn tài nguyên.

## 15. Chương trình Java 17+ hoàn chỉnh

Tạo tệp **`BigIntegerPrimalityDemo.java`**:

```java
import java.math.BigInteger;
import java.security.SecureRandom;
import java.util.List;
import java.util.Objects;

public class BigIntegerPrimalityDemo {
    private static final int CERTAINTY = 80;

    private static boolean acceptable(BigInteger n, int certainty) {
        Objects.requireNonNull(n, "candidate");
        if (certainty <= 0) {
            throw new IllegalArgumentException(
                    "certainty must be positive");
        }
        if (n.compareTo(BigInteger.TWO) < 0) {
            return false;
        }
        return n.isProbablePrime(certainty);
    }

    private static boolean trialPrime(long n) {
        if (n < 2) return false;
        if ((n & 1L) == 0L) return n == 2;

        for (long d = 3; d <= n / d; d += 2) {
            if (n % d == 0) return false;
        }
        return true;
    }

    public static void main(String[] args) {
        for (String text : List.of(
                "0", "1", "2", "17", "21", "561", "1000000007")) {
            BigInteger n = new BigInteger(text);
            boolean result = acceptable(n, CERTAINTY);
            System.out.println(text + " -> "
                    + (result ? "probably prime" : "composite"));
        }

        BigInteger nine = BigInteger.valueOf(9);
        System.out.println("certainty 0 for 9 = "
                + nine.isProbablePrime(0));
        System.out.println("certainty -3 for 0 = "
                + BigInteger.ZERO.isProbablePrime(-3));

        try {
            acceptable(nine, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("validated certainty = rejected");
        }

        BigInteger negative = BigInteger.valueOf(-17);
        System.out.println("negative -17 raw test = "
                + negative.isProbablePrime(CERTAINTY));
        System.out.println("negative -17 validated = "
                + acceptable(negative, CERTAINTY));

        BigInteger n561 = BigInteger.valueOf(561);
        BigInteger fermat = BigInteger.TWO.modPow(
                n561.subtract(BigInteger.ONE), n561);
        System.out.println("Fermat 2^560 mod 561 = " + fermat);

        System.out.println("trial division 97 = " + trialPrime(97));
        System.out.println("trial division 561 = " + trialPrime(561));
        System.out.println("next probable after 100 = "
                + BigInteger.valueOf(100).nextProbablePrime());

        try {
            BigInteger.valueOf(-5).nextProbablePrime();
        } catch (ArithmeticException ex) {
            System.out.println("negative search = rejected");
        }

        SecureRandom rnd = new SecureRandom();
        BigInteger generated = BigInteger.probablePrime(64, rnd);
        System.out.println("generated bit length = "
                + generated.bitLength());
        System.out.println("generated positive odd = "
                + (generated.signum() > 0 && generated.testBit(0)));
    }
}
```

Chạy trên môi trường có JDK 17 trở lên:

```bash
javac --release 17 BigIntegerPrimalityDemo.java
java BigIntegerPrimalityDemo
```

**Stdout dự kiến trên OpenJDK 17 (phần ngẫu nhiên chỉ in thuộc tính ổn định):**

```text
0 -> composite
1 -> composite
2 -> probably prime
17 -> probably prime
21 -> composite
561 -> composite
1000000007 -> probably prime
certainty 0 for 9 = true
certainty -3 for 0 = true
validated certainty = rejected
negative -17 raw test = true
negative -17 validated = false
Fermat 2^560 mod 561 = 1
trial division 97 = true
trial division 561 = false
next probable after 100 = 101
negative search = rejected
generated bit length = 64
generated positive odd = true
```

### Giải thích đầu ra

1. 0 và 1 không nguyên tố; 2 và 17 nguyên tố; 21 và 561 là hợp số.
2. certainty không dương khiến `isProbablePrime` trả true cho cả hợp số; wrapper có validation từ chối tình huống ấy.
3. OpenJDK có thể thử độ lớn của −17 và trả true; wrapper yêu cầu n≥2 nên trả false.
4. Carmichael 561 cho `2^560 mod 561 = 1` dù là hợp số; kiểm tra probable prime mức cao vẫn nhận diện nó là composite.
5. `nextProbablePrime` trả 101 khi tìm số lớn hơn 100; đối số âm của phương thức này bị từ chối.
6. `SecureRandom` sinh giá trị không cố định, nhưng probablePrime(64,...) bảo đảm đúng 64 bit và một số nguyên tố ứng viên dài 64 bit phải lẻ.

## 16. Những hiểu nhầm thường gặp

| Hiểu nhầm | Điều đúng |
| --- | --- |
| “`isProbablePrime(100) == true` là một chứng minh prime” | Đó là probably prime theo mức tin cậy API |
| “`false` chỉ là probably composite” | Với certainty>0, Javadoc nói false là definitely composite |
| “certainty 0 yêu cầu mặc định” | certainty≤0 trả true ngay |
| “certainty 80 là đúng 80 vòng Miller–Rabin” | API không cam kết số vòng cụ thể |
| “Đọc được 2^-80 là biết chính xác xác suất hậu nghiệm của một n cố định” | Phải xét mô hình xác suất/ứng viên, không diễn giải máy móc |
| “Số âm mặc định không bao giờ được isProbablePrime chấp nhận” | OpenJDK có thể thử theo trị tuyệt đối; tự kiểm tra n≥2 |
| “Số 1 là prime vì không có ước nhỏ” | 1 không nguyên tố theo định nghĩa |
| “Fermat a^(n−1) mod n = 1 chứng minh prime” | Có hợp số Carmichael như 561 |
| “probablePrime và isProbablePrime làm cùng một việc” | Một hàm sinh, một hàm kiểm tra |
| “new BigInteger(64, rnd) sinh probable prime” | Constructor này sinh số ngẫu nhiên không âm, có thể hợp số |
| “nextProbablePrime có thể trả lại chính số đang xét” | Trả số lớn hơn n |
| “Lặp lời gọi isProbablePrime nhiều lần luôn là các phép thử độc lập” | API không đưa ra cam kết như vậy |
| “SecureRandom mặc định đảm bảo mọi thao tác sinh RSA hợp chuẩn” | Cần quy trình khóa và tiêu chuẩn đầy đủ |
| “Tăng certainty vô hạn biến probability thành proof” | Không, nó vẫn là kiểm tra xác suất theo contract |
| “BigInteger loại bỏ mọi nguy cơ DoS” | CPU, RAM và giới hạn implementation vẫn hữu hạn |

## 17. Bài tập tự kiểm tra và lời giải

**Bài 1.** `BigInteger.valueOf(9).isProbablePrime(0)` trả gì? Có khiến 9 thành nguyên tố không?  
**Đáp án:** Trả true vì certainty≤0; 9 vẫn là hợp số. Cần validation.

**Bài 2.** `BigInteger.ONE.isProbablePrime(80)` và `BigInteger.TWO.isProbablePrime(80)` trả gì?  
**Đáp án:** Lần lượt false và true vì 1 không nguyên tố, 2 nguyên tố.

**Bài 3.** Vì sao không suy rằng `certainty=80` có đúng 80 vòng Miller–Rabin?  
**Đáp án:** Certainty biểu thị độ tin cậy yêu cầu; thuật toán, số vòng và các bước bổ sung là chi tiết triển khai.

**Bài 4.** Vì sao `2^560 mod 561=1` không chứng minh 561 nguyên tố?  
**Đáp án:** 561=3×11×17, là số Carmichael vượt qua phép kiểm tra Fermat với cơ số 2.

**Bài 5.** Giải thích khác biệt `BigInteger.probablePrime(64,rnd)` và `new BigInteger(64,rnd)`.  
**Đáp án:** Cái đầu sinh probable prime dương có đúng 64 bit; cái sau sinh số không âm có tối đa 64 bit, có thể hợp số.

**Bài 6.** Nếu cần số nguyên tố cho RSA, tại sao chỉ gọi `isProbablePrime(100)` chưa đủ?  
**Đáp án:** Cần nguồn ngẫu nhiên an toàn, lựa chọn p/q, tham số khóa, kiểm tra tiêu chuẩn và thư viện mật mã bảo mật.

**Bài 7.** `BigInteger.valueOf(100).nextProbablePrime()` trả gì?  
**Đáp án:** 101, vì cần tìm giá trị probable prime **lớn hơn** 100.

**Bài 8.** Một ứng dụng phải kiểm tra số nguyên tố dương nhưng n=−17. Kết quả đúng theo nghiệp vụ?  
**Đáp án:** False; tự kiểm tra n≥2 trước khi thử probable-prime dù implementation có thể thử trị tuyệt đối.

**Bài 9.** Nếu `isProbablePrime(100)` trả false cho n≥2, có nên thử lại 100 lần để chứng minh n prime không?  
**Đáp án:** Không. False nghĩa n đã bị phát hiện là hợp số theo API; lặp lại không đảo ngược bản chất toán học.

**Bài 10.** Khi cần chứng chỉ nguyên tố có thể xác minh độc lập, một giá trị `true` có đủ không?  
**Đáp án:** Không. Cần thuật toán/chứng chỉ primality proof phù hợp.

**Bài 11.** Tại sao cần giới hạn certainty đầu vào, dù tăng certainty có vẻ tốt?  
**Đáp án:** Vì CPU/chi phí có thể tăng và kẻ tấn công có thể yêu cầu mức kiểm tra cực lớn; giá trị phải theo policy.

**Bài 12.** Khi output từ `probablePrime(64,new SecureRandom())` thay đổi mỗi lần chạy, có phải lỗi không?  
**Đáp án:** Không. Đó là hành vi ngẫu nhiên bình thường; kiểm tra `bitLength()==64`, dương và lẻ thay vì so sánh giá trị số cố định.

## 18. Checklist khi áp dụng trong chương trình thật

1. **Xác định yêu cầu**: probable prime có đủ hay bắt buộc primality proof?
2. **Kiểm tra n ≥ 2** để tuân định nghĩa nguyên tố dương.
3. **Kiểm tra certainty > 0**; không dùng 0 hoặc âm làm mặc định.
4. **Đọc đúng true/false**: true là probable; false là composite theo contract.
5. **Không gán certainty bằng số vòng Miller–Rabin**.
6. **Không diễn giải máy móc cận 2^-certainty** như xác suất hậu nghiệm tuyệt đối cho n bất kỳ.
7. **Kiểm thử các giá trị biên**: âm, 0, 1, 2, chẵn, 561, số nguyên tố đã biết.
8. **Phân biệt API kiểm tra, sinh và tìm**: isProbablePrime, probablePrime và nextProbablePrime.
9. **Với dữ liệu mật mã:** dùng SecureRandom và các API/protocol sinh khóa chuẩn.
10. **Giới hạn tài nguyên**: độ dài input, bitLength, certainty và thời gian xử lý.
11. **Tránh in giá trị prime sinh ngẫu nhiên trong stdout tham khảo**; chỉ in đặc tính ổn định.
12. **Khi cần chứng minh:** dùng thuật toán chứng minh nguyên tố và chứng chỉ kiểm tra riêng.

### Tài liệu tham khảo

- [BigInteger — Javadoc Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html)
- [SecureRandom — Javadoc Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html)
- [Random — Javadoc Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html)

**Ghi nhớ:** `BigInteger.isProbablePrime(certainty)` kiểm tra **xác suất**, không cung cấp chứng chỉ nguyên tố. Với certainty dương, `false` là hợp số; `true` là probable prime theo mức tin cậy của API. Với certainty≤0, phương thức **trả true ngay**, nên tuyệt đối phải validate tham số. Sinh ứng viên cho mục đích bảo mật còn cần nguồn ngẫu nhiên và quy trình khóa phù hợp.
