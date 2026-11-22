# Vì sao dùng phép % tùy tiện có thể tạo thiên lệch khi sinh số ngẫu nhiên?

Khi cần tạo một giá trị ngẫu nhiên trong khoảng `0` đến `n - 1`, mã như `randomNumber % n` trông có vẻ hợp lý: phép chia lấy dư đưa một số lớn về một số nhỏ hơn `n`. Nhưng **giới hạn miền giá trị không đồng nghĩa với phân phối đều**. Nếu miền các giá trị ban đầu không chia hết thành các nhóm có cùng số phần tử, một số kết quả sẽ xuất hiện thường xuyên hơn các kết quả còn lại. Đó là **modulo bias** (thiên lệch khi lấy dư).

Ví dụ tạo mặt xúc xắc từ một nguồn giả định sinh đều một trong tám số nguyên `0, 1, ..., 7`:

```java
int face = source % 6; // source nằm trong [0, 8), đồng đều
```

Mã luôn trả một trong `0..5`, nhưng kết quả **không đồng đều**: `0` và `1` có hai tiền ảnh, các số còn lại có một. Nếu mục tiêu là xúc xắc sáu mặt công bằng, không thể dùng trực tiếp phép `% 6` này.

## 1. Chứng minh bằng cách đếm: nguồn có 8 giá trị, đích có 6 giá trị

Giả sử nguồn thật sự đồng đều trên `[0, 8)`, nghĩa là mỗi số nguyên từ 0 đến 7 có xác suất `1/8`. Bảng ánh xạ:

| Giá trị nguồn `x` | `x % 6` | Kết quả cuối |
|---:|---:|---|
| 0 | 0 | 0 |
| 1 | 1 | 1 |
| 2 | 2 | 2 |
| 3 | 3 | 3 |
| 4 | 4 | 4 |
| 5 | 5 | 5 |
| 6 | 0 | 0 (trùng kết quả của 0) |
| 7 | 1 | 1 (trùng kết quả của 1) |

Phân phối sau ánh xạ:

| Kết quả | Số giá trị nguồn tạo ra nó | Xác suất sau `% 6` | Xác suất mong muốn |
|---:|---:|---:|---:|
| 0 | 2 | 2/8 = 25% | 1/6 ≈ 16,67% |
| 1 | 2 | 2/8 = 25% | 1/6 ≈ 16,67% |
| 2 | 1 | 1/8 = 12,5% | 1/6 ≈ 16,67% |
| 3 | 1 | 1/8 = 12,5% | 1/6 ≈ 16,67% |
| 4 | 1 | 1/8 = 12,5% | 1/6 ≈ 16,67% |
| 5 | 1 | 1/8 = 12,5% | 1/6 ≈ 16,67% |

Như vậy kết quả 0 xuất hiện **gấp đôi** kết quả 2 dù các số đầu vào đều có xác suất bằng nhau. Tăng số lần mô phỏng chỉ làm tỷ lệ đo được tiến gần phân phối **đã bị lệch**; chạy nhiều hơn không tự sửa thuật toán.

### Điều kiện tổng quát

Giả sử nguồn đồng đều gồm `N` giá trị nguyên liên tiếp từ `0` đến `N - 1`; cần ánh xạ vào `n` kết quả từ `0` đến `n - 1`. Đặt:

```text
N = q × n + r, trong đó 0 ≤ r < n
q = N / n (chia nguyên)
r = N % n
```

Nếu lấy `x % n` trực tiếp:

- `r` kết quả đầu tiên (`0 .. r - 1`) có `q + 1` giá trị nguồn dẫn đến chúng.
- `n - r` kết quả còn lại (`r .. n - 1`) có `q` giá trị nguồn dẫn đến chúng.
- Khi `r = 0`, mọi kết quả có cùng `q` tiền ảnh: **không có modulo bias do phép ánh xạ này**, với điều kiện nguồn thật sự đồng đều.
- Khi `r ≠ 0`, phân phối bị lệch.

Với `N = 8`, `n = 6`: `q = 1`, `r = 2`. Hai kết quả 0, 1 nhận mỗi kết quả hai tiền ảnh; bốn kết quả còn lại mỗi kết quả một tiền ảnh.

Phép đếm trên là chứng minh trong **miền hữu hạn có phân phối đồng đều**; nó không chứng minh nguồn giả ngẫu nhiên nói chung là chất lượng cao, độc lập hoặc an toàn mật mã.

## 2. Trường hợp quen thuộc: byte ngẫu nhiên rồi `% 10`

Một byte lấy ngẫu nhiên đồng đều có `256` khả năng: `0..255`. Giả sử muốn sinh chữ số thập phân `0..9`:

```java
int digit = unsignedByte % 10; // unsignedByte ở [0, 255]
```

Ta có:

```text
256 = 25 × 10 + 6
```

Vì thế các chữ số `0..5` có **26** giá trị nguồn tương ứng, còn `6..9` chỉ có **25** giá trị nguồn tương ứng:

| Chữ số | Số tiền ảnh | Xác suất |
|---|---:|---:|
| 0, 1, 2, 3, 4, 5 | 26 mỗi chữ số | 26/256 ≈ 10,15625% |
| 6, 7, 8, 9 | 25 mỗi chữ số | 25/256 ≈ 9,765625% |

Phân phối công bằng phải là `10%` cho **mỗi** chữ số. Mức lệch ở đây nhỏ hơn ví dụ 8 → 6, nhưng vẫn là lệch có tính hệ thống. Điều này quan trọng khi sinh nhiều token, chọn phần thưởng, lấy mẫu thống kê hoặc khi yêu cầu bảo mật phải tránh sai lệch biết trước.

**Mức độ thiên lệch phụ thuộc cả kích thước miền nguồn và số lượng kết quả**, không thể kết luận mọi phép `%` đều lệch nhiều hoặc luôn lệch. Chẳng hạn nguồn 256 giá trị lấy `% 16` có đúng 16 tiền ảnh cho mỗi kết quả; còn `% 10` lệch vì 256 không chia hết cho 10.

## 3. Cách sửa bằng rejection sampling (lấy mẫu và loại giá trị dư)

Một cách chuẩn để giữ phân phối đều là **chỉ chấp nhận một miền đầu vào có kích thước chia hết cho `n`**, còn các giá trị ngoài miền thì bốc lại.

Với nguồn 8 giá trị và `n = 6`:

1. Lấy một số đồng đều từ `0..7`.
2. Nếu bằng 6 hoặc 7 thì **loại và lấy lại**.
3. Nếu là `0..5` thì trả chính số đó.

Trong số các lần lấy **được chấp nhận**, mỗi kết quả 0..5 có đúng một tiền ảnh, nên xác suất bằng `1/6`. Mỗi lần thử có xác suất được chấp nhận `6/8 = 75%`, và số lần thử kỳ vọng cho một kết quả hợp lệ là `8/6 = 4/3`.

Mã minh họa thuật toán:

```java
int value;
do {
    value = rng.nextInt(8);
} while (value >= 6);
// value đồng đều trong [0, 6), nếu mỗi lần rng.nextInt(8)
// đồng đều và các lần lấy đáp ứng giả định của nguồn
```

Đây là **đoạn mã trong ngữ cảnh đã khai báo biến `rng`**; với Java thông thường, lời giải đơn giản hơn là **gọi thẳng `rng.nextInt(6)`**.

### Công thức rejection tổng quát cho một byte không dấu

Đối với nguồn nguyên đồng đều `[0, 256)`, nếu cần `n` kết quả và `1 ≤ n ≤ 256`, đặt:

```text
limit = 256 - (256 % n)
```

Giá trị `limit` là bội số lớn nhất của `n` không vượt 256. Lặp:

```java
static int uniformFromByte(java.util.Random rng, int n) {
    if (n < 1 || n > 256) {
        throw new IllegalArgumentException("n must be in [1, 256]");
    }

    int limit = 256 - (256 % n);
    int sample;
    do {
        sample = rng.nextInt(256); // nguồn đồng đều 0..255
    } while (sample >= limit);

    return sample % n; // lúc này mỗi kết quả có số tiền ảnh như nhau
}
```

Đây là **phương thức** cần đặt trong một lớp; nó minh họa toán học chứ không phải cách cần tự triển khai cho hầu hết chương trình Java. Ví dụ `n = 10`: `limit = 250`; loại `250..255`, chấp nhận `0..249`. Mỗi chữ số nhận đúng **25** tiền ảnh, nên xác suất đều bằng `1/10`. Xác suất chấp nhận mỗi lần là `250/256`, số lần thử kỳ vọng `256/250 ≈ 1,024`.

Tại sao ở cuối vẫn dùng `% n`? Vì **sau khi từ chối các mẫu dư, số giá trị được chấp nhận đã chia hết cho `n`**. Phép chia lấy dư khi đó không tạo thiên lệch. Vấn đề nằm ở việc dùng `%` trước khi xử lý miền đầu vào có phần dư, không nằm ở toán tử `%` trong mọi hoàn cảnh.

### Những điều cần kiểm tra khi tự triển khai

- Biết chính xác **miền đầu vào** và giả định phân phối đồng đều; không đoán nguồn dựa vào tên API.
- Miền chấp nhận phải có kích thước là bội số của `n`.
- Phải **lấy mẫu mới** sau khi từ chối, không đổi mẫu bị từ chối thành một kết quả tùy ý.
- Tránh tràn số khi tính bội số, ngưỡng hoặc giá trị tuyệt đối trên miền lớn như 32/64 bit.
- Nếu nguồn không đồng đều sẵn, rejection sampling đơn giản trên tiền ảnh cũng **không tự chữa** mọi khuyết điểm của nguồn.

Với ứng dụng thực tế, nên dùng **API bounded random** của JDK đã xử lý các tình huống này thay vì tự viết thuật toán.

## 4. Java nên dùng API nào?

Khi cần số nguyên ngẫu nhiên **trong một khoảng**, ưu tiên API cung cấp trực tiếp khoảng hoặc cận trên:

```java
import java.util.Random;
import java.util.concurrent.ThreadLocalRandom;

Random random = new Random();

// Đồng đều trên các giá trị 0..5 theo hợp đồng API:
int zeroBasedDie = random.nextInt(6);

// Mặt xúc xắc 1..6:
int die = random.nextInt(6) + 1;

// Sinh trong khoảng [10, 20) = 10..19:
int value = ThreadLocalRandom.current().nextInt(10, 20);
```

Đoạn mã trên minh họa các phép gọi bên trong một phương thức; nó không phải một chương trình `main` độc lập. Với Java 17 trở lên, giao diện `java.util.random.RandomGenerator` còn định nghĩa các biến thể bounded như `nextInt(bound)` và `nextInt(origin, bound)`.

| Nhu cầu | API điển hình | Khoảng kết quả |
|---|---|---|
| Sinh chỉ số cho `List` có `size > 0` | `random.nextInt(size)` | `0..size-1` |
| Xúc xắc 6 mặt | `random.nextInt(6) + 1` | `1..6` |
| Khoảng nguyên bất kỳ có `origin < bound` | `ThreadLocalRandom.current().nextInt(origin, bound)` | `[origin, bound)` |
| Nhiều tác vụ đồng thời thông thường | `ThreadLocalRandom` hoặc bộ sinh thích hợp với nhu cầu chia sẻ trạng thái | Theo tham số bounded |
| Sinh giá trị khó đoán phục vụ bảo mật | `new SecureRandom().nextInt(bound)` | `0..bound-1` với nguồn ngẫu nhiên mật mã |

**`bound` là cận trên loại trừ**: `nextInt(6)` cho 0 đến 5, không phải 1 đến 6. `nextInt(0)` hoặc cận không hợp lệ không có nghĩa là “lấy số bất kỳ”; thông thường sẽ ném `IllegalArgumentException`.

`Random` và `ThreadLocalRandom` phục vụ sinh giả ngẫu nhiên thông thường, **không được dùng để tạo mã bí mật, token xác thực hoặc giá trị bảo mật khó đoán**. Với trường hợp bảo mật, chọn `SecureRandom`:

```java
import java.security.SecureRandom;

SecureRandom secureRandom = new SecureRandom();
int secureDigit = secureRandom.nextInt(10); // 0..9
```

Ở đây `SecureRandom` giúp bảo vệ tính **khó dự đoán**; việc dùng `nextInt(10)` giúp ánh xạ vào khoảng kết quả theo hợp đồng bounded API. Hai yêu cầu **khó dự đoán** và **phân phối đều** có liên quan nhưng không đồng nhất. Việc lấy một byte ngẫu nhiên mật mã rồi lập tức `% 10` vẫn có modulo bias theo lập luận 256 = 25×10 + 6.

## 5. Ví dụ Java 17+ độc lập, dễ kiểm chứng

Lưu chương trình vào `ModuloBiasDemo.java`. Ví dụ **đếm toàn bộ các trạng thái** thay vì dựa vào mô phỏng may rủi nên cho kết quả xác định ở mỗi lần chạy.

```java
import java.util.Arrays;
import java.util.Random;

public class ModuloBiasDemo {
    private static int fromByteWithRejection(Random random, int bound) {
        if (bound < 1 || bound > 256) {
            throw new IllegalArgumentException("bound must be 1..256");
        }
        int limit = 256 - (256 % bound);
        int value;
        do {
            value = random.nextInt(256);
        } while (value >= limit);
        return value % bound;
    }

    public static void main(String[] args) {
        int[] eightModuloSix = new int[6];
        int[] eightAcceptedSix = new int[6];
        for (int value = 0; value < 8; value++) {
            eightModuloSix[value % 6]++;
            if (value < 6) {
                eightAcceptedSix[value]++;
            }
        }

        System.out.println("8 states % 6: "
                + Arrays.toString(eightModuloSix));
        System.out.println("8 states after rejection: "
                + Arrays.toString(eightAcceptedSix));
        System.out.println("Rejected from 8: " + (8 - 6));

        int[] byteModuloTen = new int[10];
        int[] byteAcceptedTen = new int[10];
        for (int value = 0; value < 256; value++) {
            byteModuloTen[value % 10]++;
            if (value < 250) {
                byteAcceptedTen[value % 10]++;
            }
        }

        System.out.println("256 states % 10: "
                + Arrays.toString(byteModuloTen));
        System.out.println("256 states after rejection: "
                + Arrays.toString(byteAcceptedTen));
        System.out.println("Rejected from 256: " + (256 - 250));

        Random rng = new Random(12345);
        for (int i = 0; i < 10_000; i++) {
            int bounded = rng.nextInt(6);
            int rejection = fromByteWithRejection(rng, 10);
            if (bounded < 0 || bounded >= 6
                    || rejection < 0 || rejection >= 10) {
                throw new AssertionError("Value outside expected range");
            }
        }
        System.out.println("10,000 bounded draws: ranges OK");

        System.out.println("-5 % 6 = " + (-5 % 6));
        System.out.println("floorMod(-5, 6) = " + Math.floorMod(-5, 6));
    }
}
```

Chạy:

```bash
javac ModuloBiasDemo.java
java ModuloBiasDemo
```

Stdout:

```text
8 states % 6: [2, 2, 1, 1, 1, 1]
8 states after rejection: [1, 1, 1, 1, 1, 1]
Rejected from 8: 2
256 states % 10: [26, 26, 26, 26, 26, 26, 25, 25, 25, 25]
256 states after rejection: [25, 25, 25, 25, 25, 25, 25, 25, 25, 25]
Rejected from 256: 6
10,000 bounded draws: ranges OK
-5 % 6 = -5
floorMod(-5, 6) = 1
```

**Cách đọc kết quả:**

1. Hai mảng `8 states` xác nhận bằng phép đếm rằng phép `% 6` trực tiếp cho hai kết quả được ưu ái, còn từ chối `6, 7` tạo số tiền ảnh đồng đều.
2. Hai mảng `256 states` thể hiện chính xác mức lệch của phép `% 10` và cách ngưỡng `250` loại sáu giá trị dư.
3. Vòng lặp `10_000` kiểm tra **giới hạn kết quả** của API và ví dụ rejection, không phải chứng minh bằng thực nghiệm rằng một PRNG bất kỳ có phân phối đều. Chứng minh loại bỏ modulo bias nằm ở phép **đếm miền tiền ảnh**.
4. Dòng `-5 % 6` cho thấy toán tử `%` trong Java là **phép dư mang dấu**, không tự bảo đảm kết quả từ 0 đến 5 khi số đầu vào âm.

## 6. Các bẫy Java liên quan

### Bẫy A: `random.nextInt() % n` có thể âm

`Random.nextInt()` không có đối số trả về số nguyên 32 bit có dấu. Trong Java, phép `%` giữ dấu theo số bị chia:

```java
int remainder = -5 % 6;        // -5
int wrapped = Math.floorMod(-5, 6); // 1
```

`Math.floorMod(x, n)` khi `n > 0` giải quyết bài toán **kết quả âm**, nhưng **không tự loại modulo bias** trên một miền nguồn không chia hết cho `n`. Đừng xem “không âm” là bằng chứng phân phối đều.

### Bẫy B: `Math.abs(random.nextInt()) % n` không phải cách sửa

`Math.abs(Integer.MIN_VALUE) == Integer.MIN_VALUE` vì giá trị tuyệt đối của `-2147483648` không biểu diễn được bằng `int`. Do đó kết quả có thể vẫn âm, ngay cả trước khi `% n`. Ngoài ra, lấy trị tuyệt đối làm gộp các giá trị đối nhau và có thể tạo phân phối không đều; nó không bảo đảm số lần xuất hiện cân bằng.

```java
int value = Math.abs(random.nextInt()) % 6; // tránh
int correct = random.nextInt(6);            // ưu tiên
```

Không nên dùng mẹo `(x % n + n) % n` làm lời giải cho modulo bias: biểu thức đó chỉ chuẩn hóa **phần dư âm** nếu phép tính không gây vấn đề tràn và `n` hợp lệ; nó vẫn không sửa sự khác nhau về số lượng tiền ảnh.

### Bẫy C: Chỉ thử vài nghìn lần rồi kết luận “đều”

Ngay cả một thuật toán không thiên lệch cũng có dao động ngẫu nhiên trong mẫu hữu hạn; một thuật toán có thiên lệch nhỏ cũng có thể trông tương đối đều trong vài lần thử. Để đánh giá cần:

- Lý luận về **miền đầu vào, số lượng tiền ảnh và thuật toán ánh xạ**.
- Kiểm tra hợp đồng API và chất lượng bộ sinh phù hợp mục đích.
- Dùng kiểm định thống kê khi cần đánh giá thực nghiệm, với giả thuyết và kích thước mẫu phù hợp. Kết quả thống kê không thay thế chứng minh về phép ánh xạ.

### Bẫy D: `%` vừa hết không đủ để khẳng định cả bộ sinh tốt

Nếu `N` chia hết cho `n`, riêng bước ánh xạ `x % n` không gây sai lệch tần suất **khi nguồn đồng đều**. Nhưng nếu generator tạo quy luật tuần hoàn dễ đoán, có tương quan hoặc các bit thấp chất lượng kém, việc chỉ lấy phần dư (đặc biệt với lũy thừa của 2) vẫn có thể phơi bày các nhược điểm đó. Do đó hãy dùng API bounded của bộ sinh đáp ứng nhu cầu ứng dụng và đừng suy diễn rằng `%` “an toàn” chỉ vì `n` là lũy thừa của 2.

### Bẫy E: Mỗi lần làm tròn/mapping đều thay đổi phân phối

Các lối tắt khác như `Math.round(Math.random() * 5)` cũng có thể không đều: các điểm ở mép phạm vi nhận độ dài khoảng làm tròn khác điểm ở giữa. Nên tránh suy từ việc “đầu ra nằm trong khoảng” thành “đầu ra đồng đều”. Nếu dùng số nguyên bounded, hãy gọi API nguyên trực tiếp.

## 7. Trường hợp thực tế và lựa chọn phù hợp

| Tình huống | Cách tiếp cận |
|---|---|
| Chọn ngẫu nhiên một phần tử trong danh sách có `size > 0` | `list.get(rng.nextInt(list.size()))` |
| Mô phỏng xúc xắc công bằng 1 đến 6 | `rng.nextInt(6) + 1` |
| Tạo số nguyên trong `[min, max)` | API `nextInt(min, max)`; chú ý cận trên loại trừ và miền hợp lệ |
| Tạo mã xác thực/token bảo mật bằng bảng ký tự | Dùng `SecureRandom` và API bounded; quản lý thêm độ dài, entropy và chính sách token |
| Có sẵn byte ngẫu nhiên đồng đều, cần chữ số 0..9 | Loại `250..255` rồi lấy `% 10`, hoặc dùng trực tiếp API sinh số trong `[0, 10)` |
| Dữ liệu mẫu thiên lệch theo chủ đích | Xác định và triển khai phân phối mong muốn; không vô tình tạo thiên lệch bằng phép dư |

Hai yêu cầu cần tách biệt:

- **Đồng đều:** các kết quả trong miền đích có cùng xác suất.
- **Khó đoán:** người quan sát không thể suy ra kết quả tiếp theo với khả năng thực tế đáng kể.

`Random.nextInt(bound)` có thể phù hợp mô phỏng thông thường nhưng không cung cấp cam kết bảo mật của `SecureRandom`. Ngược lại, nguồn khó đoán vẫn có thể bị ánh xạ sai thành phân phối có thiên lệch nếu dùng `%` một cách tùy tiện.

## 8. Tự kiểm tra

**Câu 1.** Nguồn đồng đều `0..9`, dùng `x % 4`: kết quả nào xuất hiện nhiều hơn?  
**Đáp án:** `10 = 2×4 + 2`; kết quả `0` và `1` có ba tiền ảnh mỗi số, `2` và `3` có hai tiền ảnh mỗi số. Xác suất lần lượt 30%, 30%, 20%, 20%; phân phối không đều.

**Câu 2.** Nguồn đồng đều `0..15`, dùng `x % 4` có modulo bias không?  
**Đáp án:** Không có bias do ánh xạ này vì `16` chia hết `4`. Mỗi kết quả có đúng bốn tiền ảnh. Điều này không tự nói lên chất lượng hoặc an toàn của nguồn.

**Câu 3.** Tại sao loại `250..255` trước khi lấy `% 10` trên byte ngẫu nhiên đều lại hợp lý?  
**Đáp án:** Miền chấp nhận `0..249` có 250 giá trị, chia hết cho 10; mỗi chữ số 0..9 có 25 tiền ảnh. Mẫu bị loại phải được **lấy mới**.

**Câu 4.** `Math.floorMod(random.nextInt(), 6)` đã loại được modulo bias chưa?  
**Đáp án:** Chưa. Hàm giải quyết phần dư âm; miền nguồn nguyên 32 bit có `2^32` giá trị, không chia hết cho 6, nên vẫn tồn tại độ lệch tần suất do ánh xạ.

**Câu 5.** Vì sao `Math.abs(random.nextInt())` không bảo đảm không âm?  
**Đáp án:** `Integer.MIN_VALUE` không có trị tuyệt đối biểu diễn được bằng kiểu `int`, nên `Math.abs(Integer.MIN_VALUE)` vẫn âm.

**Câu 6.** Với Java, nên viết gì để chọn đều một chỉ số từ danh sách có 10 phần tử?  
**Đáp án:** `rng.nextInt(10)`. Nếu lựa chọn liên quan bí mật hoặc bảo mật, dùng bộ sinh phù hợp như `SecureRandom.nextInt(10)`.

**Ghi nhớ:** `x % n` đưa giá trị về một số dư nhưng **không tự bảo đảm phân phối đều**. Nếu số trạng thái nguồn không chia hết cho `n`, phần dư có nhiều tiền ảnh hơn sẽ được ưu ái. Dùng **bounded RNG API** của Java hoặc **rejection sampling** đúng cách để tránh thiên lệch này.
