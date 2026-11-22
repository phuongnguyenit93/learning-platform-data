# Viết mã giả và bảng theo dõi trước khi lập trình

## 1. Vì sao nên thiết kế trước khi viết Java?

Khi giải một bài toán, viết ngay các câu lệnh `if`, `for` và `System.out.println` có thể khiến ta bỏ sót điều kiện, chọn sai biến hoặc không biết vì sao kết quả sai. **Mã giả** (*pseudocode*) và **bảng theo dõi** (*trace table/dry-run table*) giúp kiểm tra ý tưởng trước khi phụ thuộc vào cú pháp của một ngôn ngữ lập trình.

- **Mã giả** diễn tả trình tự thuật toán bằng ngôn ngữ tự nhiên có cấu trúc. Nó nêu **làm gì và theo thứ tự nào**, không nhất thiết tuân theo cú pháp Java.
- **Bảng theo dõi** ghi lại sự thay đổi của các biến sau từng bước quan trọng, đặc biệt khi chương trình có vòng lặp và nhánh điều kiện.
- **Chạy tay** (*dry run*) là mô phỏng thuật toán với một bộ dữ liệu cụ thể mà chưa cần chạy máy.
- **Triển khai** là chuyển thuật toán đã được kiểm tra thành Java rồi đối chiếu kết quả thực tế với kết quả mong đợi.

Quy trình hiệu quả:

```text
Đọc đề
   |
   v
Xác định input, output, quy tắc, trường hợp biên
   |
   v
Viết mã giả theo các bước rõ ràng
   |
   v
Chạy tay và lập bảng theo dõi
   |
   v
Sửa lỗi logic nếu có
   |
   v
Viết Java 17+, biên dịch và kiểm thử
   |
   v
So sánh kết quả với bảng theo dõi và yêu cầu
```

Không phải bài toán nhỏ nào cũng cần bảng dài. Mục tiêu là **đủ rõ để chứng minh cách giải hợp lý và tìm lỗi sớm**, không phải thêm thủ tục hình thức.

## 2. Xác định yêu cầu và hợp đồng đầu vào/đầu ra

Trước khi viết mã giả, trả lời bốn câu hỏi:

1. **Đầu vào là gì?** Một số nguyên, một mảng, danh sách, chuỗi hay dữ liệu đọc từ file?
2. **Đầu ra là gì?** Giá trị cần trả về, nội dung cần in, hoặc trạng thái cần cập nhật?
3. **Quy tắc tính toán và ràng buộc là gì?** Chẳng hạn số dương nghĩa là `x > 0` (không tính `0`), có thể có số âm, mảng có thể rỗng.
4. **Trường hợp biên và trường hợp sai là gì?** Mảng rỗng, không có phần tử đạt điều kiện, một phần tử, giá trị lớn, `null`...

Ví dụ xuyên suốt:

**Đề bài:** Cho một mảng số nguyên `int[]`. Hãy đếm số phần tử **dương**, tính **tổng** các số dương, xác định **số dương lớn nhất** và tính **trung bình** các số dương. Nếu không có số dương, phải báo rõ là không có số dương và **không thực hiện phép chia cho 0**.

Đầu vào mẫu:

```text
[4, -2, 7, 0, 3]
```

Kết quả cần suy ra:

- Số dương: `4`, `7`, `3`.
- Số lượng: `3`.
- Tổng: `4 + 7 + 3 = 14`.
- Giá trị lớn nhất: `7`.
- Trung bình: `14 / 3`, khi hiển thị hai chữ số thập phân là `4.67`.

Trong ví dụ này, **`0` không phải số dương**. Cũng cần quyết định trước: nếu không có số dương thì không có giá trị lớn nhất/trung bình hợp lệ; không nên tự coi giá trị lớn nhất là `0` như một kết quả nghiệp vụ.

Đối với một API tái sử dụng, phải quy định thêm cách xử lý tham chiếu `null`: từ chối bằng ngoại lệ hay chấp nhận như mảng rỗng. Trong chương trình mẫu bên dưới, phương thức yêu cầu mảng khác `null` và chủ động báo lỗi nếu vi phạm.

## 3. Cách viết mã giả dễ chuyển thành chương trình

Mã giả **không có một cú pháp duy nhất bắt buộc**. Hãy dùng tên biến rõ ràng và những cấu trúc phổ biến:

| Ý tưởng thuật toán | Cách ghi mã giả | Gợi ý khi chuyển sang Java |
| --- | --- | --- |
| Gán trạng thái ban đầu | `count ← 0` | `int count = 0;` |
| Rẽ nhánh | `IF value > 0 THEN ...` | `if (value > 0) { ... }` |
| Duyệt phần tử | `FOR EACH value IN numbers` | `for (int value : numbers) { ... }` |
| Cập nhật biến | `sum ← sum + value` | `sum += value;` |
| Xử lý trường hợp không có dữ liệu | `IF count = 0 THEN ...` | `if (count == 0) { ... }` |
| Xuất kết quả | `OUTPUT count, sum` | `System.out.println(...)` |

Dấu `←` là ký hiệu **gán** thường dùng trong mã giả, không phải toán tử Java. Mã giả dùng `=` để so sánh chỉ khi quy ước đã được làm rõ; trong Java, **`==`** kiểm tra bằng nhau đối với số nguyên còn **`=`** là phép gán.

Một mã giả tốt nên:

- Ghi rõ **điểm bắt đầu**, dữ liệu cần giữ và thứ tự các bước.
- Đặt tên biến có ý nghĩa, ví dụ `count` (số lượng), `sum` (tổng), `max` (giá trị lớn nhất).
- Diễn tả điều kiện biên bằng biểu thức chính xác, không dùng câu mơ hồ như “nếu giá trị thích hợp”.
- Làm rõ mỗi lần lặp **xử lý một phần tử** và biến nào được thay đổi.
- Tránh gắn chặt vào việc in ra màn hình nếu mục tiêu chính là thuật toán; in là một cách trình bày kết quả.
- Tránh nhảy ngay vào tối ưu hóa phức tạp trước khi chứng minh thuật toán đơn giản là đúng.

## 4. Viết mã giả cho bài toán đếm và thống kê số dương

Một phiên bản mã giả đủ chi tiết:

```text
INPUT numbers: mảng các số nguyên, không null

count ← 0
sum ← 0
max ← 0                  // Chưa được coi là kết quả cho tới khi count > 0

FOR EACH value IN numbers DO
    IF value > 0 THEN
        IF count = 0 OR value > max THEN
            max ← value
        END IF
        count ← count + 1
        sum ← sum + value
    END IF
END FOR

OUTPUT count
OUTPUT sum

IF count = 0 THEN
    OUTPUT "no positive values"
ELSE
    average ← sum / count  // Chia số thực, không chia nguyên
    OUTPUT max
    OUTPUT average với 2 chữ số sau dấu thập phân
END IF
```

Đây là **mã giả, không được biên dịch bởi `javac`**. Một số quyết định thiết kế quan trọng:

1. `count` và `sum` bắt đầu bằng `0` vì chưa xử lý phần tử nào.
2. `value > 0` lọc đúng các số dương; số âm và `0` không đổi bộ đếm, tổng và giá trị lớn nhất.
3. `count = 0` trong điều kiện cập nhật `max` nghĩa là **đang gặp số dương đầu tiên**. Nhờ vậy, giá trị khởi tạo `max ← 0` không phải một ứng viên lớn nhất thực sự.
4. Cần kiểm tra `count = 0` **trước khi tính trung bình** để không chia cho `0`.
5. Trung bình phải dùng phép chia **số thực**. Nếu dùng phép chia hai số nguyên, phần thập phân bị mất.
6. Trong Java, dùng `long sum` để mở rộng phạm vi tổng so với `int`, vì cộng nhiều số `int` dương có thể vượt `Integer.MAX_VALUE`. `long` vẫn có giới hạn, nên bài toán kích thước cực lớn cần ràng buộc đầu vào hoặc cách tính thích hợp hơn.

### Bất biến vòng lặp

Một cách tự giải thích tính đúng đắn là nêu điều gì phải luôn đúng sau khi xử lý mỗi phần tử:

- `count` = số phần tử dương đã gặp trong phần đầu của mảng.
- `sum` = tổng các phần tử dương đã gặp.
- Khi `count > 0`, `max` = số lớn nhất trong các phần tử dương đã gặp.

Ban đầu, với phần đầu của mảng có độ dài `0`, `count = 0`, `sum = 0`; điều kiện về `max` chưa áp dụng. Mỗi bước bỏ qua phần tử không dương hoặc cập nhật đúng ba biến cho phần tử dương, nên các điều kiện trên tiếp tục đúng. Sau vòng lặp, phần đầu đã xét là **toàn bộ mảng**, do đó các kết quả thu được đúng theo định nghĩa.

Không cần viết chứng minh hình thức quá dài cho mọi bài tập, nhưng việc nhận diện bất biến giúp kiểm tra thiết kế vòng lặp có bỏ sót hoặc đếm trùng dữ liệu hay không.

## 5. Lập bảng theo dõi (*trace table*) từng lần lặp

Bảng theo dõi nên có **dữ liệu đầu vào, vị trí đang xét, điều kiện rẽ nhánh, giá trị các biến sau khi cập nhật**. Với `numbers = [4, -2, 7, 0, 3]`, ta có:

| Bước | Chỉ số `i` | `value` | `value > 0` | `count` sau bước | `sum` sau bước | `max` hợp lệ sau bước |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| Khởi tạo | — | — | — | 0 | 0 | Chưa có |
| 1 | 0 | 4 | Đúng | 1 | 4 | 4 |
| 2 | 1 | -2 | Sai | 1 | 4 | 4 |
| 3 | 2 | 7 | Đúng | 2 | 11 | 7 |
| 4 | 3 | 0 | Sai | 2 | 11 | 7 |
| 5 | 4 | 3 | Đúng | 3 | 14 | 7 |

Cách tính:

- **Bước 1:** gặp `4 > 0`; đây là số dương đầu tiên, nên `max = 4`, `count = 1`, `sum = 4`.
- **Bước 2:** `-2` không dương, giữ nguyên trạng thái.
- **Bước 3:** gặp `7`, tăng `count = 2`, `sum = 11`, cập nhật `max = 7`.
- **Bước 4:** `0` không dương, giữ nguyên trạng thái.
- **Bước 5:** gặp `3`, tăng `count = 3`, `sum = 14`; `max` vẫn là `7`.
- **Sau vòng lặp:** vì `count = 3`, trung bình bằng `(double) 14 / 3 ≈ 4.666...`, được in là `4.67` nếu dùng định dạng hai chữ số thập phân với `Locale.US`.

Cột `max` ghi **“Chưa có”** lúc khởi tạo để phân biệt giá trị lưu tạm trong biến với **kết quả đã có nghĩa**. Không nên in `max = 0` như số dương lớn nhất khi mảng không có số dương.

### Chọn nội dung cho bảng theo dõi

Một bảng theo dõi nên trả lời được: “Tại sao sau bước thứ ba lại có `sum = 11`?” Nếu chỉ ghi kết quả cuối, bảng không giúp tìm lỗi logic. Nhưng cũng không cần ghi tất cả biến không liên quan, vì bảng sẽ dài và khó đọc.

Cách đơn giản là **mỗi hàng tương ứng một lần lặp** và các cột là biến thay đổi hoặc điều kiện quyết định. Với vòng lặp lồng nhau, có thể thêm chỉ số vòng ngoài/vòng trong; với thuật toán tìm kiếm, có thể ghi điều kiện dừng và trạng thái “đã tìm thấy” hay chưa.

## 6. Thử trường hợp biên ngay trên mã giả

Chỉ kiểm tra một bộ dữ liệu “đẹp” là chưa đủ. Dùng mã giả và bảng trạng thái để thử những trường hợp khác:

| Đầu vào | `count` | `sum` | Kết luận |
| --- | ---: | ---: | --- |
| `[]` | 0 | 0 | Không có số dương; không tính `max`/`average` |
| `[-1, 0]` | 0 | 0 | Không có số dương |
| `[5]` | 1 | 5 | `max = 5`, `average = 5.00` |
| `[2, 2, 2]` | 3 | 6 | `max = 2`, `average = 2.00` |
| `[0, 3, -4, 8]` | 2 | 11 | `max = 8`, `average = 5.50` |

Những trường hợp này kiểm tra trực tiếp các sai sót phổ biến:

- Dùng `>= 0` thay vì `> 0` làm `0` bị đếm thành số dương.
- Không kiểm tra `count == 0` trước khi chia.
- Khởi tạo sai `max` khi mảng không có số dương.
- Chỉ kiểm tra phần tử đầu hoặc bỏ sót phần tử cuối.
- Chia nguyên khi cần trung bình có phần lẻ.

Mảng `null` không giống mảng rỗng. Nếu yêu cầu của phương thức không chấp nhận `null`, nên **từ chối rõ ràng** thay vì vô tình gây `NullPointerException` sâu trong vòng lặp.

## 7. Chuyển mã giả thành Java 17+ chạy được

Tạo tệp **`PseudocodeTraceDemo.java`**:

```java
import java.util.Locale;
import java.util.Objects;

public class PseudocodeTraceDemo {
    static void report(int[] numbers) {
        Objects.requireNonNull(numbers, "numbers");

        int count = 0;
        long sum = 0;
        int max = 0;

        for (int value : numbers) {
            if (value > 0) {
                if (count == 0 || value > max) {
                    max = value;
                }
                count++;
                sum += value;
            }
        }

        System.out.println("count=" + count);
        System.out.println("sum=" + sum);

        if (count == 0) {
            System.out.println("no positive values");
        } else {
            double average = (double) sum / count;
            System.out.println("max=" + max);
            System.out.printf(Locale.US, "average=%.2f%n", average);
        }
    }

    public static void main(String[] args) {
        System.out.println("Case A");
        report(new int[] {4, -2, 7, 0, 3});

        System.out.println("Case B");
        report(new int[] {-1, 0});

        System.out.println("Case C");
        report(new int[] {5});
    }
}
```

Trong thư mục chứa tệp, dùng **JDK 17 trở lên** trên Windows PowerShell/CMD hoặc Linux/macOS:

```bash
javac -encoding UTF-8 PseudocodeTraceDemo.java
java PseudocodeTraceDemo
```

**Stdout chính xác** (biên dịch thành công không in thông báo):

```text
Case A
count=3
sum=14
max=7
average=4.67
Case B
count=0
sum=0
no positive values
Case C
count=1
sum=5
max=5
average=5.00
```

### Đối chiếu từng bước với mã giả

| Mã giả | Java 17+ | Ý nghĩa |
| --- | --- | --- |
| `count ← 0` | `int count = 0;` | Trạng thái ban đầu |
| `sum ← 0` | `long sum = 0;` | Tổng, dùng `long` |
| `FOR EACH value IN numbers` | `for (int value : numbers)` | Duyệt lần lượt từng phần tử |
| `IF value > 0` | `if (value > 0)` | Lọc số dương |
| `count ← count + 1` | `count++;` | Tăng bộ đếm |
| `sum ← sum + value` | `sum += value;` | Cộng vào tổng |
| `IF count = 0` | `if (count == 0)` | Kiểm tra không có số dương |
| `average ← sum / count` | `(double) sum / count` | Chia thực, giữ phần lẻ |

Hai điểm cần kiểm tra sau khi chuyển:

1. **Đúng thứ tự:** ở Java, `max` được cập nhật **trước** khi tăng `count`, nên điều kiện `count == 0` nhận diện chính xác số dương đầu tiên. Nếu chuyển vị trí `count++` lên trước, điều kiện này không còn phát hiện lần đầu.
2. **Đúng kiểu:** `sum` là `long`, nhưng có phép ép rõ `(double) sum` khi chia để không tạo phép chia nguyên. `System.out.printf(Locale.US, ...)` đảm bảo dấu chấm thập phân trong đầu ra ví dụ.

`Objects.requireNonNull` ném `NullPointerException` có thông điệp tên tham số khi `numbers == null`. Ở đây đó là **tiền điều kiện của API**; mã hoàn chỉnh không truyền `null` nên stdout ổn định.

## 8. Các kiểu lỗi mà chạy tay giúp phát hiện

### Lỗi bỏ sót phần tử cuối (*off-by-one*)

Mã giả muốn duyệt mọi phần tử của mảng có `n` phần tử, chỉ số hợp lệ là `0` đến `n - 1`.

```java
// Minh họa trong phương thức:
for (int i = 0; i < numbers.length - 1; i++) {
    // Bị bỏ sót phần tử cuối nếu mục tiêu là duyệt cả mảng.
}
```

Bảng theo dõi buộc người viết ghi chỉ số `i`; nếu mảng có năm phần tử mà bảng chỉ có bốn bước, lỗi dễ được phát hiện. Cách thông thường để duyệt đủ chỉ số là `i < numbers.length`, hoặc dùng for-each khi không cần chỉ số.

### Lỗi cập nhật biến sai nhánh

```java
// Minh họa sai logic:
for (int value : numbers) {
    if (value > 0) {
        sum += value;
    }
    count++; // Sai: đếm cả số âm và 0.
}
```

Bảng theo dõi với `[-2, 4]` cho thấy sau bước xét `-2`, `count` tăng thành 1 mặc dù chưa gặp số dương. Cần đặt `count++` **bên trong** nhánh `value > 0`.

### Lỗi khởi tạo hoặc cập nhật cực trị

Nếu tìm giá trị lớn nhất trong **mọi số**, khởi tạo `max = 0` là sai đối với mảng chỉ chứa số âm. Bài xuyên suốt tìm số **dương** lớn nhất nên có điều kiện `count > 0` và cập nhật `max` khi nhận số dương đầu tiên. **Không được lấy quy tắc khởi tạo này áp dụng máy móc cho bài toán khác**.

### Lỗi chia nguyên

```java
int count = 3;
long sum = 14;
double wrong = sum / count;          // 4.0: chia nguyên trước, rồi đổi sang double.
double correct = (double) sum / count; // 4.6666...
```

Bảng theo dõi cho `sum = 14`, `count = 3`; khi lấy trung bình nếu chương trình in `4.00`, đó là dấu hiệu chọn sai kiểu phép chia. `printf("%.2f")` chỉ định dạng kết quả; **không khôi phục phần lẻ đã mất** vì phép chia nguyên.

## 9. Bảng theo dõi khác gì việc in debug?

**Bảng theo dõi trước khi chạy** là dự đoán được viết ra từ logic thuật toán; **dòng in debug** là trạng thái thực tế khi JVM thực thi. So sánh chúng giúp khoanh vùng dòng làm thuật toán đi sai.

Ví dụ, có thể tạm thêm sau mỗi vòng lặp trong `report`:

```java
System.out.println("value=" + value
        + " count=" + count
        + " sum=" + sum);
```

Đây là **dòng minh họa** để đặt trong thân vòng lặp, không thuộc chương trình hoàn chỉnh ở mục 7. Khi in debug, hãy đảm bảo vị trí in nằm **sau cập nhật trạng thái** nếu bảng cũng ghi trạng thái sau mỗi bước. Nếu in trước cập nhật mà đem so với bảng sau cập nhật, dễ tưởng rằng có lỗi dù chỉ là hai thời điểm quan sát khác nhau.

Trong chương trình thực tế, có thể dùng breakpoint/debugger hoặc unit test thay vì để nhiều `println` debug trong mã sản xuất.

Một bảng theo dõi không chứng minh thuật toán đúng cho **mọi** đầu vào. Để tăng tin cậy, hãy kết hợp:
- Bảng chạy tay cho trường hợp thông thường và trường hợp biên.
- Lập luận bất biến hoặc lý do điều kiện/vòng lặp đúng.
- Kiểm thử tự động với đầu ra kỳ vọng rõ ràng.
- Kiểm tra hành vi khi đầu vào không hợp lệ.

## 10. Mẫu bảng theo dõi có thể tái sử dụng

Khi thực hành những bài khác, hãy chuẩn bị trước bảng đơn giản:

| Bước | Dữ liệu đang xét | Điều kiện | Biến trước | Biến sau | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| Khởi tạo | Chưa xét | — | — | Trạng thái ban đầu | Đặt giá trị khởi tạo |
| 1 | Phần tử thứ nhất | Đúng/Sai | Trạng thái cũ | Trạng thái mới | Ghi nhánh đã chọn |
| 2 | Phần tử thứ hai | Đúng/Sai | Trạng thái cũ | Trạng thái mới | Xem có cập nhật đúng không |
| Kết thúc | Hết dữ liệu | Điều kiện dừng | Trạng thái cuối | Kết quả | Kiểm tra hậu điều kiện |

Bảng trên là **khuôn minh họa**, không phải bảng kết quả của ví dụ số dương. Với bài tìm kiếm, thay các cột bằng `index`, `target`, `found`; với bài đếm, theo dõi `count`; với bài tính tổng, theo dõi `sum`. Luôn ưu tiên các biến quyết định tính đúng của thuật toán.

### Checklist trước khi bắt đầu viết mã Java

1. Đã xác định **input, output** và ý nghĩa của từng kết quả chưa?
2. Các điều kiện như `>`, `>=`, `==` có đúng yêu cầu không?
3. Đã nêu rõ cách xử lý **mảng rỗng/không có dữ liệu hợp lệ** chưa?
4. Biến đếm, tổng, cực trị đã được khởi tạo hợp lý chưa?
5. Mỗi bước lặp cập nhật đúng biến, đúng nhánh và **không bỏ sót phần tử** chưa?
6. Bảng theo dõi có bao gồm trường hợp thường và ít nhất một **trường hợp biên** không?
7. Có phép chia cho 0, chia nguyên ngoài ý muốn, hoặc nguy cơ tràn số không?
8. Khi chuyển sang Java, kết quả chạy thực tế có **khớp dự đoán** không?

**Ghi nhớ:** viết mã giả để diễn đạt thuật toán trước cú pháp; dùng bảng theo dõi để quan sát những thay đổi của biến và phát hiện sai logic sớm; sau đó mới triển khai Java và kiểm thử. Một thuật toán được suy nghĩ, chạy tay và kiểm tra đầu vào biên trước thường dễ hiểu và dễ sửa hơn mã được viết bằng thử-sai ngẫu nhiên.