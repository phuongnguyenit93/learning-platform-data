# Math.random và giới hạn sử dụng trong Java

## 1. Math.random() là gì?

`Math.random()` là phương thức `static` của `java.lang.Math`, dùng để lấy **một giá trị `double` giả ngẫu nhiên** (pseudorandom) trong khoảng từ `0.0` đến dưới `1.0`. Cú pháp đơn giản, không cần import:

```java
double value = Math.random();
```

Hợp đồng giá trị trả về:

```text
0.0 <= value < 1.0
```

Nghĩa là **0.0 thuộc khoảng**, còn **1.0 không thuộc khoảng**. Các giá trị được chọn giả ngẫu nhiên, phân bố *xấp xỉ đồng đều* trong khoảng này. Mỗi lần gọi lấy một giá trị mới từ chuỗi số do bộ sinh tạo ra; không có bảo đảm rằng các giá trị liên tiếp sẽ khác nhau.

Ví dụ, trong một lần chạy, kết quả *có thể* giống:

```text
0.182...
0.893...
0.407...
```

Đây chỉ là ví dụ minh họa hình dạng dữ liệu, **không phải stdout cố định**. Không viết test dựa trên các số cụ thể đó.

`Math.random()` thường phù hợp với các bài tập mô phỏng đơn giản, chọn ngẫu nhiên để hiển thị hoặc các trò chơi nhỏ **không có yêu cầu bảo mật**. Sử dụng đúng cũng cần hiểu giới hạn của nó: khoảng giá trị, độ chính xác `double`, cách chuyển thành số nguyên, khả năng tái lập kết quả, chất lượng ngẫu nhiên và chi phí khi gọi từ nhiều luồng.

## 2. Hành vi của bộ sinh và ý nghĩa “giả ngẫu nhiên”

Theo hợp đồng Java 17, lần gọi `Math.random()` đầu tiên khởi tạo một bộ sinh số giả ngẫu nhiên như thể tạo một đối tượng `new java.util.Random()`; những lời gọi tiếp theo dùng chung bộ sinh đó.

```text
Math.random() ─┐
Math.random() ─┼──> bộ sinh Random dùng chung ──> double trong [0.0, 1.0)
Math.random() ─┘
```

Một bộ sinh giả ngẫu nhiên tạo ra chuỗi số theo thuật toán và trạng thái nội bộ. Nhìn từ ngoài, chuỗi có thể hữu ích cho thống kê và mô phỏng, nhưng nó không tương đương với nguồn ngẫu nhiên bí mật hoặc ngẫu nhiên vật lý. Không được suy ra rằng một số “khó đoán bằng mắt” thì phù hợp làm mã xác thực.

Các hệ quả quan trọng:

- **Không truyền seed cho `Math.random()`:** phương thức không có tham số và không cho người gọi đặt hay đọc seed của bộ sinh dùng chung. Bạn không thể yêu cầu “chạy lại đúng dãy vừa rồi” bằng API này.
- **Trạng thái được chia sẻ:** nhiều lời gọi ở các phần khác nhau của ứng dụng cùng tiêu thụ chuỗi từ bộ sinh bên trong. Việc gọi thêm ở một nơi có thể thay đổi số mà nơi khác nhận được.
- **An toàn khi có nhiều luồng gọi:** Java đồng bộ hóa việc sử dụng đúng cách. Tuy nhiên, nhiều luồng gọi với tốc độ rất cao có thể gặp cạnh tranh truy cập bộ sinh dùng chung và giảm hiệu năng.
- **Không an toàn cho bảo mật:** thuật toán `Random` thông thường không nhằm chống dự đoán hoặc tấn công mật mã.

Các đặc điểm này khiến `Math.random()` rất tiện cho ví dụ ngắn, nhưng kém phù hợp khi hệ thống cần kiểm soát nguồn ngẫu nhiên, quản lý seed, chạy song song quy mô lớn hoặc tạo token bảo mật.

## 3. Tạo số nguyên bằng Math.random()

Muốn mô phỏng xúc xắc sáu mặt từ 1 đến 6, một cách thường gặp là:

```java
int dice = (int) (Math.random() * 6) + 1;
```

Giải thích từng bước:

1. `Math.random()` trả `r` với `0.0 <= r < 1.0`.
2. `r * 6` có giá trị từ `0.0` đến dưới `6.0`.
3. Ép `(int)` với một số hữu hạn không âm sẽ bỏ phần thập phân, cho kết quả từ `0` đến `5`.
4. Cộng `1` được số nguyên từ `1` đến `6`.

Dấu ngoặc quanh phép nhân **rất quan trọng**. So sánh:

```java
int correct = (int) (Math.random() * 10); // 0..9
int wrong   = (int) Math.random() * 10;   // luôn là 0
```

Ở dòng sai, `(int) Math.random()` luôn bằng `0`, vì kết quả gốc nhỏ hơn `1.0`, rồi mới nhân `10`. Java không tự điều chỉnh thứ tự phép tính theo ý định người viết.

Để tạo số nguyên trong `[min, max]` (*hai đầu đều bao gồm*), công thức phổ biến cho **khoảng nhỏ, hợp lệ** là:

```java
int value = min + (int) (Math.random() * (max - min + 1));
```

Ví dụ `min = 5`, `max = 9` sẽ cho các số 5, 6, 7, 8, 9. Nhưng công thức này có những **giới hạn quan trọng**:

- `max - min + 1` được tính bằng `int` trong ví dụ. Với khoảng lớn, phép tính có thể **tràn số nguyên** trước khi nhân với `Math.random()`.
- Phép đổi từ `double` sang `int` và phép nhân dấu phẩy động có giới hạn độ chính xác. Với số lượng kết quả rất lớn hoặc nhu cầu phân bố đều nghiêm ngặt, cách nhân rồi ép kiểu không phải lựa chọn tốt.
- Phương thức tạo `double` từ một tập giá trị rời rạc hữu hạn; chia số lượng trạng thái đó cho các khoảng nguyên có thể có độ chênh xác suất rất nhỏ. Với yêu cầu lấy số nguyên đồng đều, nên ưu tiên API sinh số nguyên theo khoảng thay vì tự biến đổi từ `double`.
- Nếu `min > max`, đầu vào không hợp lệ; không nên âm thầm tính tiếp.

Đối với số nguyên trong đoạn `[min, max)` (*bao gồm min, không bao gồm max*), `ThreadLocalRandom.current().nextInt(min, max)` hoặc một `RandomGenerator.nextInt(min, max)` làm rõ ý nghĩa giới hạn và xử lý việc lấy giá trị nguyên một cách phù hợp hơn. Với `max == Integer.MAX_VALUE`, đừng vô tình tính `max + 1` bằng `int` để cố tạo khoảng đóng; hãy chọn overload/ràng buộc khác phù hợp.

## 4. Lỗi off-by-one: biên bao gồm và loại trừ

Điều thường khiến code tạo số ngẫu nhiên sai là nhầm `[a, b]` với `[a, b)`.

| Yêu cầu | Cách dùng `Math.random()` cho ví dụ nhỏ | Kết quả |
| --- | --- | --- |
| Số nguyên từ 0 đến 9 | `(int) (Math.random() * 10)` | 0..9 |
| Số nguyên từ 1 đến 10 | `1 + (int) (Math.random() * 10)` | 1..10 |
| Xúc xắc sáu mặt | `1 + (int) (Math.random() * 6)` | 1..6 |
| Hai lựa chọn 0 hoặc 1 | `(int) (Math.random() * 2)` | 0 hoặc 1 |
| Xác suất xấp xỉ 25% | `Math.random() < 0.25` | `boolean` |
| Một số thực trong `[0, 1)` | `Math.random()` | `double` |

Trong điều kiện `Math.random() < 0.25`, kết quả `true` có xác suất xấp xỉ 25% theo mô hình phân bố đã nêu. Một số lần chạy ít ỏi không có lý do gì phải cho đúng 25% số lần `true`.

Các lỗi phổ biến khác:

```java
int a = (int) (Math.random() * 6);      // 0..5, không phải 1..6
int b = (int) (Math.random() * 6) + 1;  // 1..6

int c = Math.round((float) (Math.random() * 6)); // 0..6,
                                                  // xác suất ở hai biên khác phần giữa
```

`Math.round` làm tròn về số nguyên gần nhất, khiến khoảng giá trị gần hai đầu chỉ chiếm xấp xỉ một nửa chiều rộng so với các khoảng giữa; vì thế **không** phải cách thay thế tương đương cho `floor` khi muốn các số nguyên có xác suất gần như nhau.

Không nên kiểm tra `Math.random() == 1.0`: điều kiện ấy luôn `false` theo hợp đồng API. Nếu muốn cho phép số ở **cận trên**, hãy xác định rõ bài toán là số nguyên hay số thực. Với đoạn số thực đóng, công thức chuyển đổi đơn giản `min + Math.random() * (max - min)` cũng không đảm bảo mọi giá trị biên có xác suất như nhau; và làm tròn dấu phẩy động có thể ảnh hưởng cận. Đừng hứa hẹn tính chất toán học mà biểu diễn hữu hạn không bảo đảm.

## 5. Ví dụ hoàn chỉnh Java 17+: kiểm tra khoảng mà không đoán số ngẫu nhiên

Lưu tệp `MathRandomDemo.java`:

```java
import java.security.SecureRandom;
import java.util.Random;
import java.util.concurrent.ThreadLocalRandom;

public class MathRandomDemo {
    private static int rollWithMath() {
        return 1 + (int) (Math.random() * 6);
    }

    private static boolean validDie(int value) {
        return value >= 1 && value <= 6;
    }

    public static void main(String[] args) {
        double sample = Math.random();
        System.out.println("Math.random in [0,1): "
                + (sample >= 0.0 && sample < 1.0));

        int die = rollWithMath();
        System.out.println("Math dice in [1,6]: " + validDie(die));

        int threadedDie = ThreadLocalRandom.current().nextInt(1, 7);
        System.out.println("ThreadLocalRandom dice in [1,6]: "
                + validDie(threadedDie));

        Random first = new Random(12345L);
        Random second = new Random(12345L);
        boolean sameSequence = true;
        for (int i = 0; i < 100; i++) {
            if (first.nextInt(6) != second.nextInt(6)) {
                sameSequence = false;
            }
        }
        System.out.println("Same seed, same sequence: " + sameSequence);

        SecureRandom secure = new SecureRandom();
        byte[] tokenBytes = new byte[16];
        secure.nextBytes(tokenBytes);
        System.out.println("Secure byte length: " + tokenBytes.length);
    }
}
```

Chạy:

```bash
javac MathRandomDemo.java
java MathRandomDemo
```

Stdout **ổn định về các điều kiện được in**, dù những giá trị được sinh bên trong thay đổi giữa các lần chạy:

```text
Math.random in [0,1): true
Math dice in [1,6]: true
ThreadLocalRandom dice in [1,6]: true
Same seed, same sequence: true
Secure byte length: 16
```

Bài học của ví dụ: khi kiểm tra giá trị giả ngẫu nhiên, hãy kiểm tra những thuộc tính có bảo đảm (kiểu dữ liệu, phạm vi, cấu trúc, khả năng tái lập với seed xác định). Đừng assert một giá trị cố định từ `Math.random()`.

`SecureRandom` chỉ được dùng để minh họa cách tạo byte phù hợp cho trường hợp nhạy cảm về an toàn; 16 byte có đủ cho một ứng dụng cụ thể hay không phụ thuộc vào thiết kế token, entropy yêu cầu, thời hạn và cơ chế chống phát lại.

## 6. Hạn chế về khả năng tái lập và kiểm thử

Trong mô phỏng, lập trình viên thường muốn chạy **cùng đầu vào và cùng seed thì nhận cùng chuỗi ngẫu nhiên** để gỡ lỗi và so sánh kết quả. `Math.random()` không nhận seed và dùng trạng thái ẩn dùng chung, nên khó kiểm soát theo từng test.

Thay bằng đối tượng `java.util.Random` có seed được truyền từ bên ngoài:

```java
import java.util.Random;

public class SeededRandomDemo {
    public static void main(String[] args) {
        Random a = new Random(42L);
        Random b = new Random(42L);

        boolean same = true;
        for (int i = 0; i < 1000; i++) {
            same &= a.nextInt(100) == b.nextInt(100);
        }
        System.out.println("Repeatable: " + same);
    }
}
```

Chạy `javac SeededRandomDemo.java` và `java SeededRandomDemo`, stdout:

```text
Repeatable: true
```

Hai đối tượng `Random` độc lập với cùng seed và **cùng thứ tự lời gọi** tạo cùng chuỗi. Nếu một đối tượng gọi `nextInt` thêm một lần, dãy tiếp theo sẽ bị lệch so với đối tượng còn lại. Seed có ý nghĩa để tái hiện test, **không phải** để bảo mật.

Với thiết kế có thể test, nên truyền nguồn sinh số vào đối tượng nghiệp vụ (dependency injection) thay vì gọi `Math.random()` trực tiếp ở mọi nơi:

```java
import java.util.Objects;
import java.util.random.RandomGenerator;

public class DiceService {
    private final RandomGenerator rng;

    public DiceService(RandomGenerator rng) {
        this.rng = Objects.requireNonNull(rng);
    }

    public int roll() {
        return rng.nextInt(1, 7);
    }
}
```

Đây là class có thể biên dịch trên Java 17+, không có `main`. Để chạy ứng dụng, truyền một instance như `new DiceService(new java.util.Random(42L))`. Khi cần triển khai khác, người gọi có thể truyền generator khác tương thích với `RandomGenerator`. Việc test không còn phụ thuộc vào bộ sinh ẩn của `Math.random()`.

`RandomGenerator` là interface chuẩn từ Java 17, giúp tách mã nghiệp vụ khỏi thuật toán sinh số. Nếu yêu cầu **tái hiện tuyệt đối trong môi trường khác nhau**, hãy ghi rõ loại bộ sinh, seed, thứ tự sử dụng và phiên bản thực thi; tránh giả định mọi thuật toán hoặc mọi phiên bản đều cho cùng chuỗi chỉ vì seed giống nhau.

## 7. Giới hạn khi dùng nhiều luồng

`Math.random()` dùng một bộ sinh chia sẻ. Java bảo đảm gọi được an toàn từ nhiều luồng, nên bạn **không phải tự khóa** cho mỗi lần gọi. Nhưng với tác vụ có tần suất sinh ngẫu nhiên cao từ nhiều luồng, việc chia sẻ có thể dẫn tới cạnh tranh và làm chậm.

Với workload song song không nhạy cảm về bảo mật, `ThreadLocalRandom` thường phù hợp hơn:

```java
import java.util.concurrent.ThreadLocalRandom;

int id = ThreadLocalRandom.current().nextInt(1000, 2000);
double unit = ThreadLocalRandom.current().nextDouble();
```

Hai đoạn lệnh trên chỉ là **minh họa ở bên trong phương thức hoặc lớp**, không phải Java file chạy độc lập. `nextInt(1000, 2000)` cho các giá trị từ 1000 đến 1999; 2000 là biên **không bao gồm**. `nextDouble()` cũng cho số trong `[0.0, 1.0)`.

Lợi ích và giới hạn:

- Bộ sinh dành cho mỗi luồng giúp tránh phần lớn tranh chấp với một `Random` dùng chung.
- Không có cơ chế thiết lập seed cho `ThreadLocalRandom.current()` bằng API thông thường. Vì vậy nó không thích hợp nếu muốn tự điều khiển dãy bằng seed trong test.
- `ThreadLocalRandom` cũng **không phải nguồn ngẫu nhiên bảo mật**.
- Trong các mô phỏng song song yêu cầu tái lập, có thể cấp generator riêng cho mỗi task với seed được quản lý rõ ràng, hoặc nghiên cứu `SplittableRandom`/`RandomGenerator` phù hợp. Cần quy định việc chia các dòng ngẫu nhiên theo task để tránh thay đổi kết quả khi thay lịch luồng.

Việc dùng nhiều luồng tự nó không làm `Math.random()` sinh ra giá trị ngoài khoảng; giới hạn chính ở đây là khả năng kiểm soát và hiệu năng khi cạnh tranh cao.

## 8. Giới hạn bảo mật: tuyệt đối không tạo bí mật bằng Math.random()

Một chuỗi số khó đoán khi quan sát vài lần **không đồng nghĩa** khó dự đoán với người tấn công. `Math.random()` và `Random` được thiết kế cho mục đích giả ngẫu nhiên thông thường, không có bảo đảm về sức mạnh mật mã.

Không dùng `Math.random()` để tạo:

- Mã OTP, mã xác nhận giao dịch, mã reset mật khẩu.
- Session token, API key, access token, nonce phục vụ bảo mật.
- Khóa mã hóa, salt yêu cầu sinh ngẫu nhiên an toàn hoặc dữ liệu liên quan tới kiểm soát truy cập.
- Giá trị có thể mang lợi ích kinh tế cho kẻ đoán đúng, nếu việc bảo vệ chống dự đoán là một phần yêu cầu.

Dùng `java.security.SecureRandom` cho mục đích mật mã. Ví dụ tạo 32 byte ngẫu nhiên:

```java
import java.security.SecureRandom;

public class SecureBytesDemo {
    public static void main(String[] args) {
        SecureRandom random = new SecureRandom();
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);

        System.out.println("Generated bytes: " + bytes.length);
    }
}
```

Chạy `javac SecureBytesDemo.java` rồi `java SecureBytesDemo`:

```text
Generated bytes: 32
```

Đoạn code không in các byte bí mật ra log. Khi chuyển byte thành token, cần dùng encoding an toàn (ví dụ Base64 URL-safe), quản lý vòng đời token và lưu trữ phù hợp. Tạo byte ngẫu nhiên an toàn là một phần của thiết kế bảo mật, không tự nó giải quyết xác thực hay phân quyền.

Không cố cải thiện `Math.random()` bằng cách nhân, làm tròn, ghép nhiều kết quả hoặc đặt lại seed của một `Random` khác. Các thao tác đó không biến nguồn giả ngẫu nhiên không bảo mật thành nguồn đáp ứng yêu cầu mật mã.

## 9. Giới hạn thống kê và số dấu phẩy động

Một `double` có độ chính xác nhị phân hữu hạn (thường được mô tả bằng 53 bit significand). Vì vậy, các kết quả từ `Math.random()` là một **tập rời rạc hữu hạn** những số trong khoảng `[0.0, 1.0)`, chứ không phải mọi số thực của toán học.

Ba hệ quả:

**Thứ nhất, phân bố chỉ xấp xỉ đồng đều.** Đối với mô phỏng thông thường điều này thường đủ tốt. Với thuật toán cần đặc tính thống kê cao, chu kỳ dài, các luồng độc lập hoặc yêu cầu được kiểm chứng riêng, cần chọn bộ sinh và thiết kế phép thử phù hợp, không mặc định `Math.random()` là tối ưu.

**Thứ hai, phép chuyển khoảng không tự bảo toàn mọi tính chất lý tưởng.** Khi nhân `Math.random()` với một số nguyên rồi ép `int`, cách ánh xạ từ các trạng thái `double` hữu hạn đến các số nguyên có thể tạo sai lệch phân bố nhỏ. Đối với khoảng nguyên, API `nextInt(bound)` hay `nextInt(origin, bound)` thích hợp hơn việc tự viết phép đổi khi cần tính đúng đắn và xử lý các biên.

**Thứ ba, nhân/cộng số thực có thể làm tròn hoặc tràn.** Ví dụ:

```java
double min = 0.0;
double max = 10.0;
double value = min + Math.random() * (max - min);
```

Trong trường hợp đơn giản này, `value` nằm trong `[0.0, 10.0)` theo cách hiểu thông thường. Nhưng với các số `double` rất lớn, rất gần nhau hoặc không hữu hạn, phép `max - min`, nhân và cộng có thể tràn, mất precision hoặc bị làm tròn tới cận trên. Tránh đem công thức giản đơn áp dụng vô điều kiện cho mọi dải `double`.

Nếu đang dùng Java 17+ và cần các số `double` trong khoảng, xem các API `nextDouble(origin, bound)` của `RandomGenerator` hoặc `ThreadLocalRandom`, đồng thời kiểm tra đầu vào theo hợp đồng của API. Khi bài toán yêu cầu tiền tệ hay phép tính decimal chính xác, không nên lấy `double` từ `Math.random()` rồi giả định phép tính sau đó không còn sai số nhị phân.

## 10. Chọn API sinh số ngẫu nhiên phù hợp

| API | Hợp lý khi | Lưu ý |
| --- | --- | --- |
| `Math.random()` | Ví dụ ngắn, mô phỏng đơn giản, không cần quản lý seed | Trả `double` trong `[0,1)`; seed ẩn, bộ sinh dùng chung; không bảo mật |
| `new Random(seed)` | Test có thể lặp lại, thuật toán muốn chủ động quản lý seed | Có trạng thái riêng; đồng seed + cùng lời gọi tạo cùng dãy; không bảo mật |
| `ThreadLocalRandom.current()` | Tạo số thường xuyên trong nhiều luồng | Ít tranh chấp, có API khoảng nguyên; không cho caller đặt seed; không bảo mật |
| `SplittableRandom` | Mô phỏng cần chia bộ sinh thành các luồng/task riêng | Có thể đặt seed; không an toàn để chia sẻ cùng instance giữa nhiều luồng; không bảo mật |
| `RandomGenerator` (Java 17+) | Muốn tách thuật toán sinh số khỏi nghiệp vụ; lựa chọn/đổi implementation | Interface, tự nó không bảo đảm an toàn mật mã hay thread safety |
| `SecureRandom` | Sinh byte/token hoặc giá trị nhạy cảm về bảo mật | Có bảo đảm mật mã theo provider/thuật toán; có thể tốn tài nguyên hơn |

Với `ThreadLocalRandom`, `Random`, `SplittableRandom`, `SecureRandom`, các overload và tính chất của từng API có thể khác nhau. Hãy dùng đúng phương thức thay vì giả định mọi lớp đều có cùng signature.

Nguồn tham khảo chính thức (Java 17):

- [Math — random()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#random())
- [Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html)
- [ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html)
- [SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html)
- [java.util.random và RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html)

## 11. Kiểm thử đúng: test tính chất thay vì một mẫu cụ thể

Với `Math.random()`, tránh test kiểu:

```java
// Sai: không có bảo đảm sample == 0.5.
if (Math.random() != 0.5) {
    throw new AssertionError("Unexpected random value");
}
```

Nên kiểm tra đúng hợp đồng:

```java
double r = Math.random();
if (!(r >= 0.0 && r < 1.0)) {
    throw new AssertionError("Math.random out of range");
}
```

Đây là những đoạn lệnh ngắn đặt trong phương thức, không phải file độc lập. Với phép đổi số nguyên theo yêu cầu, kiểm tra cả cận dưới và cận trên. Khi phải khẳng định dãy kết quả cụ thể của thuật toán nghiệp vụ, hãy truyền một nguồn sinh số có thể điều khiển hoặc giả lập và test riêng phần tính toán.

Kiểm thử thống kê cần số mẫu và tiêu chí phù hợp; việc lấy 20 giá trị rồi thấy tỷ lệ mỗi số khác nhau không đủ để kết luận thuật toán sai. Ngược lại, vài mẫu trông có vẻ phân bố đều cũng không chứng minh bộ sinh thích hợp cho bảo mật.

## 12. Các sai lầm thường gặp

| Sai lầm | Điều gì xảy ra | Cách khắc phục |
| --- | --- | --- |
| Nghĩ `Math.random()` có thể trả `1.0` | Sai về cận trên | Ghi nhớ `0.0 <= r < 1.0` |
| Dùng `(int) Math.random() * n` | Luôn nhận 0 với `n` hữu hạn trong phép nhân nguyên | Dùng `(int) (Math.random() * n)` |
| Dùng `Math.round(Math.random() * n)` để lấy 0..n đồng đều | Các điểm biên có xác suất khác điểm trong | Với khoảng nguyên, dùng `nextInt` |
| Nhầm `nextInt(1, 6)` nghĩa là xúc xắc 1..6 | Chỉ tạo 1..5 | Dùng `nextInt(1, 7)` |
| Tính `max - min + 1` bằng `int` cho khoảng lớn | Có thể overflow | Dùng API khoảng hỗ trợ kiểu phù hợp và kiểm tra biên |
| Muốn test tái lập nhưng gọi `Math.random()` trực tiếp | Không thể kiểm soát seed/trình tự trên từng test | Truyền `Random` hoặc `RandomGenerator` có seed |
| Dùng `Math.random()` cho mã xác nhận/token | Có nguy cơ dự đoán, không đạt yêu cầu bảo mật | Dùng `SecureRandom` và thiết kế token an toàn |
| Một lượng lớn luồng cùng gọi `Math.random()` liên tục | Có thể tranh chấp bộ sinh dùng chung | Cân nhắc `ThreadLocalRandom` hoặc generator theo task |
| Suy từ một lần chạy rằng mọi kết quả đều xuất hiện đều | Nhầm hiện tượng ngẫu nhiên với đảm bảo tuyệt đối | Phân tích xác suất, chọn mẫu và tiêu chí thống kê phù hợp |
| Cho rằng nhân với 10 tạo đúng 10 giá trị `double` | Vẫn là `double` liên tục theo khoảng giá trị rời rạc hữu hạn | Ép nguyên đúng chỗ nếu cần giá trị nguyên |

## 13. Câu hỏi tự kiểm tra

1. **Khoảng của `Math.random()` là gì?** `[0.0, 1.0)`, nghĩa là có 0.0 nhưng không có 1.0.
2. **Vì sao `(int) Math.random() * 6` không mô phỏng xúc xắc?** Vì ép `int` trước phép nhân biến kết quả thành 0.
3. **Cách mô phỏng xúc xắc bằng `Math.random()` là gì?** `1 + (int) (Math.random() * 6)`, phù hợp bài tập nhỏ không cần chất lượng/khả năng bảo mật đặc biệt.
4. **Tại sao không dùng `Math.random()` để tạo password-reset token?** Vì nguồn `Random` bên trong không được thiết kế để chống dự đoán theo yêu cầu mật mã; nên dùng `SecureRandom`.
5. **Khi test muốn cùng seed cho ra cùng chuỗi, nên làm thế nào?** Dùng `new Random(seed)` hoặc một generator hỗ trợ seed, đảm bảo cùng thuật toán và cùng trình tự gọi.
6. **`ThreadLocalRandom.current().nextInt(1, 7)` có thể trả 7 không?** Không; biên trên 7 là exclusive, kết quả từ 1 đến 6.
7. **Nếu nhiều luồng cần hàng triệu số ngẫu nhiên cho mô phỏng, giới hạn nào của `Math.random()` cần lưu ý?** Trạng thái dùng chung có thể gây contention; cân nhắc generator theo luồng hoặc theo task.
8. **Một số `double` nhìn ngẫu nhiên có phải là đủ an toàn để tạo khóa bí mật?** Không; phân bố nhìn có vẻ tốt và bảo mật chống dự đoán là hai yêu cầu khác nhau.

## 14. Kết luận

`Math.random()` là công cụ ngắn gọn để lấy một `double` giả ngẫu nhiên trong `[0.0, 1.0)`. Nó phù hợp cho bài tập và mô phỏng nhỏ, nhưng có giới hạn do bộ sinh dùng chung, seed không kiểm soát được, tính rời rạc của `double`, rủi ro sai biên khi chuyển sang số nguyên và đặc biệt là **không bảo đảm an toàn mật mã**.

Hãy chọn API theo yêu cầu: `Random(seed)` cho test tái lập, `ThreadLocalRandom` cho tải song song thông thường, `RandomGenerator` để tách mã nghiệp vụ khỏi bộ sinh, và `SecureRandom` khi giá trị cần chống dự đoán. Khi chuyển đổi khoảng, phải định nghĩa chính xác **biên bao gồm/loại trừ** và test theo những thuộc tính API thực sự bảo đảm.
