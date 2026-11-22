# Xác suất trùng UUID và giới hạn ý nghĩa duy nhất

## 1. “Duy nhất” có hai lớp ý nghĩa

UUID giúp nhiều nơi tạo định danh mà không cần hỏi một bộ đếm trung tâm cho từng lần tạo. Tuy nhiên, tên gọi UUID không biến mọi giá trị do chương trình tạo ra thành một cam kết toán học rằng sẽ không bao giờ trùng.

Cần phân biệt:

- **Khả năng tránh trùng của cách sinh:** một bộ sinh tốt có thể làm xác suất trùng cực nhỏ.
- **Ràng buộc duy nhất của hệ thống:** nơi lưu dữ liệu phải từ chối định danh đã tồn tại trong phạm vi cần bảo vệ.

Ví dụ, hai dịch vụ cùng tạo đơn hàng bằng `UUID.randomUUID()`. Cách sinh giúp chúng ít phải phối hợp khi chọn mã. Nhưng cơ sở dữ liệu vẫn nên có khóa chính hoặc ràng buộc duy nhất cho mã đơn hàng, vì dữ liệu trùng còn có thể đến từ sao chép, nhập lại hay lỗi chương trình.

Bài này tính xác suất cho **UUID phiên bản 4 được sinh ngẫu nhiên đúng cách**. Không áp dụng nguyên con số đó cho mọi UUID hoặc mọi chuỗi có hình thức giống UUID.

## 2. Vì sao tính trên 122 bit thay vì 128 bit?

UUID có tổng cộng 128 bit. Với UUID phiên bản 4 theo biến thể chuẩn đang dùng, 4 bit dành cho phiên bản và 2 bit dành cho biến thể; còn **122 bit ngẫu nhiên**.

Nếu các phần ngẫu nhiên phân bố đều, không gian lựa chọn là:

```text
N = 2^122 ≈ 5,317 × 10^36
```

`UUID.randomUUID()` của Java tạo UUID phiên bản 4 bằng bộ sinh số giả ngẫu nhiên mạnh về mật mã. Đó là tính chất của phương thức sinh này, không phải của mọi đối tượng `UUID` được phân tích từ chuỗi hay tạo bằng constructor. Xem [API UUID.randomUUID](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/UUID.html#randomUUID()) và [RFC 9562, mục UUIDv4](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.4).

Những phép tính tiếp theo giả sử các lần sinh độc lập và phân bố đều trên không gian này. Nếu một chương trình luôn trả cùng hằng UUID, hoặc tự giới hạn phần ngẫu nhiên vào một miền nhỏ, công thức cho bộ sinh lý tưởng không còn mô tả chương trình đó.

## 3. Hai lần sinh và rất nhiều lần sinh là hai câu hỏi khác nhau

Với hai lần chọn độc lập từ `N` giá trị, xác suất trùng là:

```text
P(trùng giữa hai lần) = 1 / N
```

Nhưng khi có `n` UUID, số cặp cần xét là:

```text
số cặp = n × (n - 1) / 2
```

Ví dụ, bốn định danh A, B, C, D tạo ra sáu cặp: AB, AC, AD, BC, BD, CD. Số cơ hội trùng tăng gần theo bình phương số lần sinh. Đây là cơ chế của **bài toán ngày sinh (birthday problem)**: không hỏi một giá trị có trùng một giá trị đã chỉ định hay không, mà hỏi có cặp nào trùng trong cả tập hay không.

Ta có thể tự suy ra xác suất không trùng bằng cách chọn lần lượt:

- Lần đầu: chưa có gì để trùng.
- Lần thứ hai: phải tránh 1 giá trị đã dùng, xác suất thành công là `1 - 1/N`.
- Lần thứ ba, với điều kiện hai lần đầu khác nhau: phải tránh 2 giá trị, xác suất là `1 - 2/N`.
- Tiếp tục đến lần thứ `n`.

Với `0 <= n <= N`, công thức chính xác theo mô hình độc lập, đồng đều là:

```text
P(không có cặp trùng) = tích của (1 - k/N), với k từ 0 đến n-1

P(có ít nhất một cặp trùng) = 1 - P(không có cặp trùng)
```

Nếu số lần chọn vượt số giá trị có thể có, ít nhất một cặp trùng là bắt buộc. Nhưng không cần đợi đến lúc lấp đầy không gian mới xuất hiện xác suất trùng đáng kể.

## 4. Công thức gần đúng và cách đọc kết quả

Khi `n` nhỏ so với `N`, dùng xấp xỉ:

```text
lambda = n × (n - 1) / (2 × N)

P(có ít nhất một cặp trùng) ≈ 1 - exp(-lambda)
```

`lambda` là kỳ vọng số cặp trùng trong mô hình này. **Kỳ vọng số cặp không phải xác suất**, dù khi `lambda` rất nhỏ thì xác suất xấp xỉ bằng `lambda`.

Với UUIDv4 lý tưởng:

| Tổng số UUID đã sinh n | Xác suất có ít nhất một cặp trùng, gần đúng |
|---|---:|
| `10^6` — một triệu | `9,404 × 10^-26` |
| `10^9` — một tỷ | `9,404 × 10^-20` |
| `10^12` | `9,404 × 10^-14` |
| `10^15` | `9,404 × 10^-8` |

Các giá trị trong cột cuối là **xác suất từ 0 đến 1**, chưa nhân 100 để đổi sang phần trăm. Chẳng hạn `9,404 × 10^-8` tương đương khoảng `0,000009404%`.

Giải xấp xỉ cho xác suất bằng 50%:

```text
n ≈ sqrt(2 × N × ln(2))
  ≈ 2,715 × 10^18
```

Mốc đó không có nghĩa rằng “sinh đến trước mốc thì chắc chắn không trùng” hoặc “đến đúng mốc sẽ trùng”. Nó mô tả xác suất trên các thử nghiệm giả định lặp lại của cả quá trình.

Nếu nhiều máy cùng tạo mã trong một miền cần giữ duy nhất, `n` là **tổng số lần sinh của toàn miền**, không phải số lần sinh của một máy. Muốn đánh giá khoảng thời gian dài, cần tính cả những mã lịch sử mà nghiệp vụ không cho phép tái sử dụng.

### Xác suất một cặp trùng khác xác suất đoán một mã

Công thức trên đo rủi ro có **bất kỳ cặp nào** trùng trong tập. Nó không phải công thức cho một bên cố đoán một mã mục tiêu, cũng không chứng minh một mã là bí mật. Khi thiết kế kiểm soát truy cập, vẫn phải xác minh quyền với tài nguyên được yêu cầu.

## 5. Chương trình Java tính các ví dụ

Lưu mã sau vào `UuidCollisionDemo.java`. Phần đầu tính xác suất theo mô hình, không sinh hàng tỷ UUID. Phần cuối cố ý thêm cùng một UUID hai lần để minh họa việc phát hiện trùng.

```java
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

public class UuidCollisionDemo {
    private static final double V4_SPACE = Math.scalb(1.0, 122);

    static double approximateCollisionProbability(long count) {
        if (count < 0) {
            throw new IllegalArgumentException("Negative count");
        }
        if (count < 2) {
            return 0.0;
        }
        double n = count;
        double expectedPairs = n * (n - 1.0) / (2.0 * V4_SPACE);
        return -Math.expm1(-expectedPairs);
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        long[] counts = {
                1_000_000L,
                1_000_000_000L,
                1_000_000_000_000L,
                1_000_000_000_000_000L
        };
        check(approximateCollisionProbability(0) == 0.0, "n=0");
        check(approximateCollisionProbability(1) == 0.0, "n=1");

        double previous = 0.0;
        for (long count : counts) {
            double probability = approximateCollisionProbability(count);
            check(probability > previous && probability < 1.0,
                    "Probability must grow in these samples");
            previous = probability;
            System.out.printf(Locale.ROOT, "n=%d p~%.3e%n",
                    count, probability);
        }

        double halfProbabilityCount =
                Math.sqrt(2.0 * V4_SPACE * Math.log(2.0));
        System.out.printf(Locale.ROOT, "p~0.5 at n~%.3e%n",
                halfProbabilityCount);

        Set<UUID> seen = new HashSet<>();
        UUID fixed = UUID.fromString(
                "550e8400-e29b-41d4-a716-446655440000");
        check(seen.add(fixed), "First insertion failed");
        boolean duplicateRejected = !seen.add(fixed);
        check(duplicateRejected, "Duplicate was accepted");
        System.out.println("duplicate rejected=" + duplicateRejected);
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```shell
javac -encoding UTF-8 --release 17 UuidCollisionDemo.java
java UuidCollisionDemo
```

Stdout:

```text
n=1000000 p~9.404e-26
n=1000000000 p~9.404e-20
n=1000000000000 p~9.404e-14
n=1000000000000000 p~9.404e-08
p~0.5 at n~2.715e+18
duplicate rejected=true
```

### Vì sao dùng expm1?

Tính trực tiếp `1.0 - Math.exp(-lambda)` với `lambda` cực nhỏ có thể bị mất thông tin khi `Math.exp(-lambda)` được làm tròn rất gần hoặc bằng 1.

`Math.expm1(x)` tính `exp(x) - 1` theo cách phù hợp hơn ở vùng gần 0. Xem [API Math.expm1](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#expm1(double)). Vì vậy:

```text
1 - exp(-lambda) = -expm1(-lambda)
```

Chương trình dùng `double`, nên kết quả vẫn là xấp xỉ số học, không phải chứng minh xác suất chính xác từng chữ số. Ở số đếm rất lớn, phép chuyển `long` sang `double` cũng có thể mất độ chính xác ở các chữ số cuối. Điều đó phù hợp mục tiêu ước lượng bậc độ lớn của ví dụ, nhưng phải ghi rõ khi sử dụng kết quả.

### Vì sao không sinh một triệu UUID rồi kết luận?

Một lần chạy không thấy trùng chỉ cho biết mẫu dữ liệu vừa thử không trùng. Nó không chứng minh rằng mọi lần chạy sau đều như vậy. Với xác suất lý tưởng rất thấp, kiểm thử ngẫu nhiên thông thường còn rất khó chạm được vào nhánh xử lý trùng.

Ngược lại, việc cố ý cấp cùng một UUID trong phần `HashSet` giúp kiểm tra nhánh phát hiện trùng một cách xác định. `HashSet` ở đây chạy trong một luồng và chỉ minh họa trong bộ nhớ; nó không thay thế ràng buộc lưu trữ bền vững hoặc xử lý nhiều tiến trình.

## 6. Những nguyên nhân trùng mà phép tính lý tưởng không bao quát

Trong hệ thống thật, cần phân biệt một va chạm ngẫu nhiên hiếm với việc chương trình tái sử dụng một mã:

| Tình huống | Vì sao phép tính 122 bit không đủ để đánh giá |
|---|---|
| Mã được gán cứng trong dữ liệu mẫu rồi đưa vào luồng thật | Không có lần chọn ngẫu nhiên độc lập |
| Dùng lại đối tượng mang ID cũ khi tạo bản ghi mới | Lỗi vòng đời dữ liệu |
| Một yêu cầu được gửi lại và chèn lần thứ hai | Có thể là cùng thao tác nghiệp vụ được thực hiện lại |
| Sao chép hoặc nhập lại cùng bản ghi | Mã cũ được tái sử dụng có chủ đích hoặc vô tình |
| Tự xây bộ sinh và lặp lại trạng thái của nó | Giả thiết độc lập có thể sai |
| Chỉ giữ vài ký tự của UUID làm mã chính | Không gian định danh bị thu nhỏ |

Dùng UUID không tự sửa các lỗi này. Khi thấy xung đột mã, hãy điều tra đường đi dữ liệu, nguồn sinh và ngữ nghĩa của thao tác thay vì kết luận ngay rằng đã gặp một sự kiện ngẫu nhiên cực hiếm.

Đặc biệt, cắt ngắn UUID hoặc lấy một giá trị băm ngắn không bảo toàn không gian `2^122`. Muốn ước lượng lại phải biết số bit thực sự còn lại, phân bố đầu ra và số giá trị sẽ cùng tồn tại.

## 7. Đưa tính duy nhất thành điều kiện được kiểm tra

Với một bảng đơn hàng, khóa chính trên cột mã đơn hàng bảo vệ việc hai hàng không mang cùng khóa và không có khóa rỗng. Nếu mã đó chỉ là một trường riêng, có thể cần ràng buộc `UNIQUE` kết hợp yêu cầu không rỗng. Ví dụ cơ chế khóa chính và ràng buộc duy nhất được mô tả trong [tài liệu PostgreSQL](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-UNIQUE-CONSTRAINTS).

Đừng chỉ làm hai bước “kiểm tra chưa có mã” rồi “chèn bản ghi”. Hai yêu cầu đồng thời có thể cùng thấy mã chưa tồn tại trước khi một trong hai ghi. Việc chấp nhận hay từ chối xung đột phải nằm ở thao tác lưu có cơ chế đồng bộ phù hợp.

Khi thao tác lưu báo xung đột:

1. Xác định **ràng buộc nào** bị vi phạm. Trùng email hay trùng khóa nghiệp vụ không phải va chạm UUID.
2. Nếu đúng là mã mới do hệ thống tự sinh đã trùng và thao tác cho phép đổi mã, có thể sinh lại với số lần thử hữu hạn, trong cách quản lý giao dịch phù hợp.
3. Nếu đây là gửi lại cùng một thao tác, xử lý theo chính sách chống thực hiện lặp (idempotency); không tạo mã mới rồi âm thầm tạo thêm bản ghi.
4. Không ghi đè dữ liệu đã có chỉ vì mã trùng. Giữ thông tin chẩn đoán để phân biệt nguyên nhân.

Trong thiết kế kiểm thử, nên cho phép thay nguồn cấp ID bằng một nguồn có kịch bản: lần đầu trả mã đã dùng, lần sau trả mã khác. Như vậy có thể kiểm tra nhánh thử lại mà không chờ va chạm ngẫu nhiên thật. Không cần thay thuật toán chuẩn bằng bộ sinh tự chế để làm kiểm thử.

## 8. UUID duy nhất không đồng nghĩa điều gì?

| Suy luận sai | Cách hiểu phù hợp |
|---|---|
| Hai bản ghi có UUID khác nhau thì chắc chắn là hai sự kiện nghiệp vụ khác nhau | Một yêu cầu bị gửi lại có thể tạo hai UUID khác nhau |
| UUID đúng hình thức thì chắc chắn do hệ thống mình sinh | Chuỗi đúng hình thức có thể đến từ nhiều nguồn |
| UUID khó trùng nên không cần kiểm tra quyền | Tính duy nhất và quyền truy cập là hai trách nhiệm riêng |
| UUIDv4 cho biết thời điểm tạo hoặc thứ tự tạo | UUIDv4 ngẫu nhiên không cung cấp thứ tự thời gian đó |
| Có ràng buộc duy nhất trong một bảng thì bảo đảm toàn bộ hệ thống không trùng | Phạm vi của ràng buộc chỉ là nơi nó được áp dụng |
| Mọi UUID đều có 122 bit ngẫu nhiên | Con số trong bài áp dụng cho mô hình UUIDv4 đã nêu |

Một ràng buộc duy nhất ở tập dữ liệu đang hoạt động cũng không tự bảo vệ toàn bộ lịch sử sau khi xóa dữ liệu. Nếu không được tái sử dụng định danh trong suốt vòng đời nghiệp vụ, cần xác định nơi lưu lịch sử hoặc cơ chế bảo vệ phạm vi đó.

## 9. Bài thực hành

1. Thay `N` trong một bản thử riêng thành `2^16`. Tính lại mốc xác suất 50% và giải thích vì sao vài trăm lần sinh đã đáng chú ý dù có 65.536 giá trị.
2. Vẽ sáu cặp của bốn định danh, rồi đếm số cặp của năm định danh. Dùng cách đếm đó giải thích vì sao xác suất cho cả tập không bằng `n/N`.
3. Thiết kế ba kịch bản kiểm thử: ID trùng do nguồn cấp cố ý, gửi lại cùng thao tác, và vi phạm một ràng buộc nghiệp vụ khác. Mô tả vì sao ba nhánh không nên được xử lý giống nhau.
4. Với hệ thống có nhiều máy sinh mã, xác định `n` phải cộng từ những nguồn nào và trong bao lâu. Ghi rõ giả thiết nào của mô hình xác suất cần được đáp ứng.

Khi giải thích tính duy nhất, hãy luôn nêu đủ: cách sinh mã, phạm vi cần duy nhất, tổng số mã đang xét và cơ chế từ chối trùng khi lưu. Những thông tin đó làm cho tuyên bố “UUID rất khó trùng” trở thành một đánh giá có thể kiểm tra.
