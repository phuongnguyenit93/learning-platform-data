# Duyệt một lần với trạng thái tích lũy

## 1. Ý tưởng cốt lõi

Nhiều bài toán xử lý dãy không cần lưu toàn bộ kết quả trung gian hay duyệt đi duyệt lại các phần tử. Ta có thể đi từ trái sang phải, **mỗi phần tử đúng một lần**, đồng thời giữ một lượng thông tin đã được rút gọn từ phần tiền tố đã xem. Thông tin đó gọi là **trạng thái tích lũy** (accumulated state).

Ví dụ: để biết tổng, giá trị nhỏ nhất, giá trị lớn nhất và số phần tử chẵn của một dãy, tại thời điểm đọc phần tử mới x, chỉ cần cập nhật:

- total ← total + x;
- minimum ← min(minimum, x);
- maximum ← max(maximum, x);
- evenCount ← evenCount + 1 nếu x chẵn.

Không cần tạo một mảng tổng trung gian. Sau khi đọc n phần tử, trạng thái chứa kết quả cuối cùng.

Hình dung luồng xử lý:

~~~text
Dãy:           x0        x1        x2                 x(n-1)
               |         |         |                     |
Trạng thái:  S0 -> update(S0,x0) -> ... -> update(...,x(n-1))
                                                   |
                                                   v
                                              Kết quả
~~~

Đây thường được gọi là **single pass**, **one-pass scan**, **running accumulation** hoặc **fold/reduce** khi phép cập nhật có dạng phù hợp. Điểm then chốt không chỉ là có một vòng for mà là biết **giữ đủ thông tin về phần quá khứ** để xử lý phần tương lai, không phải đọc lại những gì đã đi qua.

## 2. Hợp đồng đầu vào, đầu ra và trạng thái

Trước khi thiết kế phép duyệt, xác định:

1. **Đầu vào:** dãy chứa kiểu gì, số phần tử n, thứ tự có ý nghĩa không, có thể rỗng hay null không, dữ liệu có thể trùng hoặc âm không?
2. **Đầu ra:** cần một số, một chỉ số, một đoạn [l, r), một tập giá trị hay nhiều thống kê? Nếu có nhiều lời giải tốt ngang nhau, chọn lời giải nào?
3. **Trạng thái:** sau khi duyệt tiền tố a[0..i), ta cần biết những gì để xử lý a[i] mà không quay lại?
4. **Khởi tạo:** trạng thái khi chưa xem phần tử nào, hoặc sau phần tử đầu tiên, là gì?
5. **Chuyển trạng thái:** với giá trị x mới, cập nhật trạng thái như thế nào?
6. **Bất biến:** sau mỗi bước, từng biến trong trạng thái phải có ý nghĩa chính xác nào?
7. **Kết thúc:** biến nào chính là đáp án, cần chuyển đổi hay kiểm tra bổ sung không?

Định nghĩa hình thức đơn giản: S₀ là trạng thái ban đầu, và với i từ 0 đến n−1,

~~~text
S(i+1) = update(S(i), a[i])
answer = finish(S(n))
~~~

Nếu số thao tác của update và finish đều O(1), thời gian O(n); nếu trạng thái có số biến cố định, bộ nhớ phụ O(1). **Một vòng lặp không tự động bảo đảm O(n)**: nếu mỗi lần cập nhật lại sắp xếp, sao chép hoặc quét cả tiền tố, tổng thời gian có thể lớn hơn O(n).

Đối với xử lý trực tuyến (online), phần tử có thể đến lần lượt mà không cần biết toàn bộ dãy từ trước. Một thuật toán một lượt và bộ nhớ nhỏ thường thích hợp với luồng dữ liệu; tuy nhiên không phải mọi bài toán đều có thể trả lời chính xác bằng số biến cố định.

## 3. Ví dụ cơ bản: tích lũy nhiều thống kê

Cho dãy a khác null và không rỗng. Hãy trả về tổng, phần tử nhỏ nhất, lớn nhất, số lượng số chẵn và chỉ số đầu tiên của số chẵn (nếu không có thì −1).

Một trạng thái đủ gồm:

| Biến | Ý nghĩa sau khi đã đọc ít nhất một phần tử |
| --- | --- |
| sum | Tổng các giá trị trong tiền tố đã đọc |
| min | Giá trị nhỏ nhất trong tiền tố |
| max | Giá trị lớn nhất trong tiền tố |
| evenCount | Số phần tử chẵn trong tiền tố |
| firstEvenIndex | Chỉ số nhỏ nhất có phần tử chẵn; −1 nếu chưa gặp |
| i | Chỉ số phần tử đang xử lý |

Dùng tổng kiểu long để không tràn số nguyên 32-bit khi cộng nhiều phần tử kiểu int. Khởi tạo min và max từ phần tử đầu tiên, không khởi tạo chúng bằng 0: nếu mảng toàn số dương thì min=0 sẽ sai; nếu mảng toàn số âm thì max=0 sẽ sai.

~~~text
sum = 0
min = a[0]
max = a[0]
evenCount = 0
firstEvenIndex = -1

for i = 0 .. n-1:
    x = a[i]
    sum = sum + x
    min = min(min, x)
    max = max(max, x)
    if x là số chẵn:
        evenCount = evenCount + 1
        if firstEvenIndex == -1:
            firstEvenIndex = i
~~~

Ví dụ với a = [3, −2, 5, −7, 4, 4, −1]:

| Bước | x | sum | min | max | evenCount | firstEvenIndex |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 3 | 3 | 3 | 3 | 0 | −1 |
| 1 | −2 | 1 | −2 | 3 | 1 | 1 |
| 2 | 5 | 6 | −2 | 5 | 1 | 1 |
| 3 | −7 | −1 | −7 | 5 | 1 | 1 |
| 4 | 4 | 3 | −7 | 5 | 2 | 1 |
| 5 | 4 | 7 | −7 | 5 | 3 | 1 |
| 6 | −1 | 6 | −7 | 5 | 3 | 1 |

Đầu ra là tổng 6, min −7, max 5, ba số chẵn và chỉ số số chẵn đầu tiên là 1 (đếm từ 0). Một lần duyệt đủ để tính đồng thời cả năm đại lượng; không nhất thiết phải có năm vòng lặp.

**Bất biến:** sau khi xử lý xong vị trí i, sum bằng tổng a[0] + ... + a[i]; min/max là cực trị đúng của a[0..i]; evenCount đếm đúng các phần tử chẵn trong a[0..i]; firstEvenIndex là chỉ số nhỏ nhất thỏa điều kiện trong tiền tố hoặc −1. Phép cập nhật dựa trên giá trị cũ và a[i] giữ đúng từng mệnh đề, nên khi i=n−1, đó là các thống kê của toàn dãy.

## 4. Thiết kế trạng thái: đủ thông tin, ít thông tin thừa

Để tìm được trạng thái tốt, hãy hỏi: “Nếu không được nhìn lại các phần tử đã đi qua, cần nhớ điều gì để quyết định khi gặp phần tử kế tiếp?”

Một vài mẫu thường gặp:

| Bài toán | Trạng thái tích lũy | Cập nhật khi gặp x | Bộ nhớ phụ |
| --- | --- | --- | --- |
| Tổng toàn dãy | sum | sum += x | O(1) |
| Đếm phần tử thỏa điều kiện P | count | Nếu P(x) thì count++ | O(1) |
| Giá trị nhỏ nhất và vị trí đầu tiên | min, index | Nếu x < min thì ghi min, index | O(1) |
| Trung bình số học | long sum, count | sum += x; count++ rồi chia khi kết thúc | O(1), với int và tổng phù hợp |
| Dãy con tăng liên tiếp dài nhất | currentLength, bestLength, previous | So sánh x với previous, tăng hoặc đặt lại currentLength | O(1) |
| Tổng đoạn con liên tiếp lớn nhất | bestEndingHere, bestSoFar | Mở rộng hoặc bắt đầu lại đoạn kết thúc ở x | O(1) |
| Tần suất mỗi giá trị phân biệt | Bảng đếm theo khóa | Tăng bộ đếm ứng với x | O(k) với k khóa khác nhau |

**Không phải trạng thái nào cũng O(1) bộ nhớ.** Với bài toán tần suất của các giá trị chưa biết trước, một Map có thể tăng đến O(k), k ≤ n. Nếu cần lưu tất cả tổng tiền tố để trả lời nhanh nhiều truy vấn đoạn [l, r), ta thường tạo mảng prefixSum O(n) bộ nhớ. Nếu chỉ cần tổng toàn dãy hoặc một tổng đang chạy, biến sum O(1) là đủ.

**Đừng giữ thiếu thông tin:** chỉ lưu tổng không đủ để tìm vị trí số chẵn đầu tiên; cần thêm chỉ số đầu tiên hoặc thông tin tương đương. Ngược lại, lưu cả tiền tố khi chỉ cần tổng là dư thừa. Thiết kế trạng thái chính là tìm một bản tóm tắt của quá khứ **đủ để bảo toàn các quyết định trong tương lai**.

## 5. Trường hợp phức tạp hơn: tổng đoạn con liên tiếp lớn nhất

Bài toán: cho mảng int không rỗng, tìm **đoạn con liên tiếp, không rỗng**, có tổng lớn nhất. Trả về tổng và ranh giới nửa mở [from, toExclusive), tức phần tử cuối là toExclusive−1.

Cách ngây thơ có thể thử mọi cặp đầu/cuối, rồi cộng lại từng đoạn, tốn tới O(n³). Dùng tổng tiền tố, có thể tính mỗi tổng đoạn O(1) sau tiền xử lý và thử O(n²) cặp. Nhưng ta có thể làm tốt hơn bằng một lượt duyệt với **quyết định giữ hay bỏ đoạn đang nối tới phần tử trước**.

Đặt:

- endingSum: tổng lớn nhất của một đoạn con không rỗng **kết thúc chính xác tại i**;
- endingStart: chỉ số bắt đầu đoạn tương ứng;
- bestSum: tổng lớn nhất của mọi đoạn đã hoàn toàn nằm trong tiền tố a[0..i];
- bestFrom, bestTo: ranh giới của đoạn đạt bestSum.

Với phần tử hiện tại x = a[i], mọi đoạn kết thúc tại i thuộc đúng một trong hai trường hợp:

1. Bắt đầu mới tại i, tổng bằng x.
2. Nối x vào một đoạn kết thúc tại i−1, tốt nhất là đoạn có tổng endingSum cũ, cho tổng endingSum + x.

Do đó phương trình trạng thái của thuật toán Kadane là:

~~~text
bestEndingAt(i) = max(a[i], bestEndingAt(i-1) + a[i])
bestInPrefix(i) = max(bestInPrefix(i-1), bestEndingAt(i))
~~~

Các giá trị ban đầu tại i=0 đều bằng a[0]. Không khởi tạo bestSum = 0 nếu **không cho phép đoạn rỗng**: với mảng [−6, −2, −5], đáp án phải là −2, không phải 0.

Để có kết quả xác định khi nhiều đoạn có cùng tổng, ví dụ dưới đây quy định:

- Khi có hai lựa chọn cùng tổng **và cùng điểm kết thúc**, giữ đoạn bắt đầu sớm hơn (nối vào đoạn cũ).
- Khi có nhiều đoạn tốt nhất ở các điểm kết thúc khác nhau, giữ đoạn đã tìm thấy trước đó (điểm kết thúc sớm nhất).

Những quy tắc phá hòa này là một phần của hợp đồng đầu ra; nếu hệ thống muốn ưu tiên đoạn ngắn nhất hay chỉ số bắt đầu nhỏ nhất trên toàn dãy thì phải sửa cả quy tắc và phép kiểm thử.

### Minh họa bằng tay

Với a = [3, −2, 5, −7, 4, 4, −1]:

| i | x | endingSum | Đoạn đang kết thúc ở i | bestSum | Đoạn tốt nhất [from, to) |
| ---: | ---: | ---: | --- | ---: | --- |
| 0 | 3 | 3 | [0, 1) | 3 | [0, 1) |
| 1 | −2 | 1 | [0, 2) | 3 | [0, 1) |
| 2 | 5 | 6 | [0, 3) | 6 | [0, 3) |
| 3 | −7 | −1 | [0, 4) | 6 | [0, 3) |
| 4 | 4 | 4 | [4, 5) | 6 | [0, 3) |
| 5 | 4 | 8 | [4, 6) | 8 | [4, 6) |
| 6 | −1 | 7 | [4, 7) | 8 | [4, 6) |

Kết quả là tổng **8**, đoạn [4, 6) chứa hai phần tử 4, 4. Cũng như thống kê cơ bản, chỉ cần một số biến được cập nhật khi mỗi phần tử đi qua.

## 6. Cài đặt Java 17+ chạy được

Lưu toàn bộ chương trình sau vào tệp **OnePassAccumulator.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class OnePassAccumulator {
    private OnePassAccumulator() {}

    record Summary(
            long sum,
            int min,
            int max,
            int evenCount,
            int firstEvenIndex) {}

    record BestSlice(long sum, int from, int toExclusive) {}

    /**
     * Requires a non-null, non-empty array.
     * Computes all statistics in one pass without modifying input.
     */
    static Summary summarize(int[] values) {
        Objects.requireNonNull(values, "values");
        if (values.length == 0) {
            throw new IllegalArgumentException("array must not be empty");
        }

        long sum = 0L;
        int min = values[0];
        int max = values[0];
        int evenCount = 0;
        int firstEvenIndex = -1;

        for (int i = 0; i < values.length; i++) {
            int x = values[i];
            sum += x;
            if (x < min) {
                min = x;
            }
            if (x > max) {
                max = x;
            }
            if (x % 2 == 0) {
                evenCount++;
                if (firstEvenIndex == -1) {
                    firstEvenIndex = i;
                }
            }
        }
        return new Summary(sum, min, max, evenCount, firstEvenIndex);
    }

    /**
     * Requires a non-null, non-empty array.
     * Finds a non-empty maximum-sum contiguous slice [from, toExclusive).
     * Keeps the earliest finishing optimal slice; for the same finish,
     * keeps the earliest start. Does not modify input.
     */
    static BestSlice maxSubarray(int[] values) {
        Objects.requireNonNull(values, "values");
        if (values.length == 0) {
            throw new IllegalArgumentException("array must not be empty");
        }

        long endingSum = values[0];
        long bestSum = values[0];
        int endingStart = 0;
        int bestFrom = 0;
        int bestTo = 1;

        for (int i = 1; i < values.length; i++) {
            long extended = endingSum + values[i];

            if (extended >= values[i]) {
                endingSum = extended;    // Keep earlier start on a tie.
            } else {
                endingSum = values[i];  // Start a new segment at i.
                endingStart = i;
            }

            if (endingSum > bestSum) {
                bestSum = endingSum;
                bestFrom = endingStart;
                bestTo = i + 1;
            }
        }
        return new BestSlice(bestSum, bestFrom, bestTo);
    }

    public static void main(String[] args) {
        int[] values = {3, -2, 5, -7, 4, 4, -1};

        System.out.println("Summary: " + summarize(values));
        System.out.println("Best: " + maxSubarray(values));
        System.out.println("All negative: "
                + maxSubarray(new int[] {-6, -2, -5}));
        System.out.println("Large sum: "
                + summarize(new int[] {
                    Integer.MAX_VALUE, Integer.MAX_VALUE
                }).sum());
        System.out.println("Unchanged: " + Arrays.toString(values));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac OnePassAccumulator.java
java OnePassAccumulator
~~~

Stdout dự kiến chính xác trên Java 17+:

~~~text
Summary: Summary[sum=6, min=-7, max=5, evenCount=3, firstEvenIndex=1]
Best: BestSlice[sum=8, from=4, toExclusive=6]
All negative: BestSlice[sum=-2, from=1, toExclusive=2]
Large sum: 4294967294
Unchanged: [3, -2, 5, -7, 4, 4, -1]
~~~

Record trong Java tự cung cấp cách biểu diễn toString theo tên record và tên các thành phần, vì vậy các dòng Summary[...] và BestSlice[...] hiển thị như trên. Ví dụ Large sum dùng hai giá trị Integer.MAX_VALUE (2.147.483.647); tổng 4.294.967.294 vượt giới hạn int nhưng vừa trong long. Nhờ dùng long ngay từ đầu, không có phép cộng int bị tràn trước khi chuyển kiểu.

**Lưu ý về số lượt duyệt:** mỗi lời gọi summarize hoặc maxSubarray duyệt mảng đúng một lần. Trong hàm main hai phương thức được gọi riêng để minh họa, nên để tính **cả hai loại kết quả** chương trình duyệt mảng hai lượt. Nếu ứng dụng cần cả hai cùng lúc và muốn đúng một lượt tổng cộng, có thể gộp các biến trạng thái và cập nhật chúng trong một vòng lặp; không được nhầm “mỗi thuật toán một lượt” với “toàn chương trình một lượt”.

## 7. Vì sao thuật toán đúng?

### 7.1. Bất biến cho thống kê

Sau khi xử lý các phần tử từ 0 tới i:

- sum là tổng chính xác của các phần tử đó theo kiểu long;
- min/max là cực trị của tiền tố không rỗng;
- evenCount là số giá trị có phần dư chia 2 bằng 0;
- firstEvenIndex là vị trí đầu tiên có giá trị chẵn, hoặc −1 nếu chưa xuất hiện.

Trước vòng lặp, sum, evenCount và firstEvenIndex phù hợp với tiền tố rỗng; min/max đã được gán giá trị a[0] để tránh khởi tạo sai với số âm/dương. Mỗi phép cập nhật giữ đúng nghĩa của biến. Quy nạp theo i cho thấy khi hết dãy, các biến tương ứng chính xác với kết quả cần trả.

### 7.2. Bất biến cho Kadane

Sau khi xử lý a[i]:

1. endingSum bằng **giá trị lớn nhất** trong tất cả các đoạn con không rỗng kết thúc tại i; endingStart là một điểm bắt đầu đạt giá trị này theo quy tắc phá hòa.
2. bestSum bằng **giá trị lớn nhất** trong tất cả các đoạn con không rỗng nằm trong a[0..i]; [bestFrom, bestTo) là một đoạn thực sự đạt tổng ấy.

**Cơ sở i=0:** chỉ có một đoạn không rỗng [0, 1), tổng a[0], nên cả hai mệnh đề đúng.

**Bước quy nạp:** mọi đoạn kết thúc tại i hoặc chỉ gồm a[i], hoặc là một đoạn kết thúc tại i−1 nối thêm a[i]. Theo bất biến cũ, lựa chọn nối tốt nhất có tổng endingSum(cũ) + a[i]. Lấy max của hai trường hợp tạo ra endingSum mới đúng. bestSum mới bằng max giữa kết quả tốt nhất trong tiền tố trước và kết quả tốt nhất kết thúc tại i, nên cũng đúng. Cập nhật chỉ khi giá trị tốt hơn, giữ được quy tắc phá hòa đã công bố.

**Kết thúc:** chỉ số i tăng đúng một đơn vị cho đến n−1, vòng lặp chấm dứt sau n−1 lượt kể từ phần tử thứ hai. Bất biến tại cuối dãy bảo đảm kết quả tối ưu trên toàn bộ mảng. Đây là lập luận vừa về tính đúng vừa về kết thúc, không chỉ kiểm tra vài ví dụ.

## 8. Phân tích thời gian và bộ nhớ

Với n = values.length > 0:

| Thuật toán | Số lượt đọc theo vòng lặp | Thời gian | Bộ nhớ phụ |
| --- | --- | --- | --- |
| summarize | n phần tử | Θ(n) | Θ(1) |
| maxSubarray | n phần tử tổng cộng (phần tử đầu được đọc khi khởi tạo) | Θ(n) | Θ(1) |
| Gộp hai trạng thái trong một vòng | n phần tử | Θ(n) | Θ(1) |

Tại mỗi bước có số hữu hạn phép cộng, so sánh, gán và kiểm tra chẵn, không phụ thuộc n. Với mô hình RAM và truy cập mảng O(1), toàn bộ thao tác là tuyến tính. Cần xem việc tạo record kết quả là O(1) và không tính bộ nhớ của chính mảng đầu vào vào bộ nhớ phụ.

Nếu yêu cầu biết min hoặc max của **một mảng bất kỳ** với không có thông tin tiền xử lý, về nguyên tắc cần xem tất cả n giá trị ở trường hợp tệ nhất: một giá trị chưa đọc có thể là cực trị mới. Do đó một lượt duyệt tuyến tính là phù hợp với cận dưới Ω(n) cho tác vụ này trong mô hình truy cập phần tử.

**Một lượt duyệt không đồng nghĩa xử lý dòng thời gian thực luôn có độ trễ thấp.** Thời gian thực tế còn phụ thuộc kích thước dữ liệu, cache, đọc I/O, JVM và chi phí cập nhật. Phát biểu Θ(n) mô tả tốc độ tăng với n theo giả định đã chọn, không mô tả số mili giây cố định.

## 9. Những điều kiện biên phải quyết định trước

- **Mảng rỗng:** tổng và số đếm có thể quy ước là 0; nhưng min/max và đoạn con không rỗng không tồn tại. Trong hợp đồng của hai phương thức Java trên, mọi mảng rỗng gây IllegalArgumentException. Nếu API cần chấp nhận rỗng, hãy đổi kiểu kết quả hoặc quy ước đầu ra một cách nhất quán, chẳng hạn Optional cho min/max.
- **Mảng null:** code dùng Objects.requireNonNull nên ném NullPointerException. Đây là hành vi rõ ràng khác với mảng rỗng.
- **Toàn số âm:** Kadane khởi tạo từ a[0], nên chọn phần tử âm lớn nhất (gần 0 nhất), ví dụ [−6, −2, −5] trả −2.
- **Toàn số 0 hoặc nhiều đáp án ngang nhau:** cần xác định cách phá hòa. Code giữ điểm kết thúc sớm nhất; khi cùng điểm kết thúc và tổng bằng nhau, ưu tiên điểm bắt đầu sớm hơn.
- **Giá trị trùng:** nếu cần vị trí đầu tiên của giá trị đạt min/max, chỉ cập nhật vị trí khi x < min hoặc x > max, không phải khi bằng; ký hiệu < so với ≤ ảnh hưởng trực tiếp đến hợp đồng.
- **Tràn số:** kiểu int có thể tràn khi cộng nhiều phần tử. long khắc phục cho tổng của mảng int với kích thước Java khả thi; nếu dữ liệu là long hoặc bài toán không có giới hạn tổng phù hợp, cần xét BigInteger hoặc chính sách tràn rõ ràng.
- **Thứ tự:** tính tổng/min/max không phụ thuộc vào thứ tự phần tử về mặt toán học, nhưng tìm đoạn con liên tiếp, đếm chuỗi và chỉ số đầu tiên **phụ thuộc** vào thứ tự. Không được xáo dãy rồi kỳ vọng cùng ranh giới đoạn.
- **Sửa đầu vào:** cả hai phương thức chỉ đọc mảng. Nếu dãy bị luồng khác thay đổi đồng thời khi duyệt, ý nghĩa của kết quả không còn dựa trên một snapshot nhất quán; hợp đồng nên yêu cầu đầu vào không bị sửa trong lúc thực thi.

## 10. Khi nào một lượt với O(1) trạng thái là không đủ?

Không phải cứ cần tính một kết quả từ dãy là có cách một lượt, bộ nhớ hằng số, trả lời chính xác trong mọi trường hợp. Số trạng thái cần giữ phụ thuộc vào **thông tin của quá khứ mà phần tương lai có thể hỏi lại**.

Một số ví dụ:

1. **Tìm các giá trị khác nhau trong miền không giới hạn:** chỉ lưu tổng và min/max không đủ; thường cần set/hash map có kích thước tăng theo số giá trị phân biệt.
2. **In tất cả tổng tiền tố sau khi đọc toàn bộ luồng:** nếu phải lưu để trả lời truy vấn ngẫu nhiên sau này, cần giữ mảng prefix sums hoặc lưu ra ngoài. Nếu được in ngay khi tính thì vẫn có thể một lượt với O(1) bộ nhớ nội bộ.
3. **Trung vị chính xác của luồng tùy ý:** không có phép cộng dồn đơn giản tương tự tổng; các cấu trúc duy trì thứ tự thường phải giữ nhiều giá trị hoặc thông tin bổ sung.
4. **Cửa sổ trượt độ dài k:** khi phần tử ở đầu cửa sổ rời khỏi phạm vi, có thể cần deque, bộ đếm hoặc cấu trúc lưu thông tin của k phần tử, tùy phép toán.
5. **Truy vấn thay đổi dữ liệu sau khi duyệt:** một trạng thái tổng cuối cùng không đủ để hỗ trợ mọi truy vấn cập nhật/đoạn; cần cấu trúc dữ liệu khác.

Ngược lại, một số bài toán khó hơn nhìn bề ngoài vẫn cho phép trạng thái nhỏ nếu tìm được bất biến phù hợp: tổng đoạn con tốt nhất của Kadane chỉ cần thông tin tốt nhất kết thúc tại vị trí trước, và một kết quả tốt nhất toàn cục.

## 11. Kiểm thử theo hợp đồng và theo bất biến

Với phương thức summarize:

| Đầu vào | Kết quả kiểm tra |
| --- | --- |
| [3, −2, 5, −7, 4, 4, −1] | sum=6, min=−7, max=5, evenCount=3, firstEvenIndex=1 |
| [−3, −1] | sum=−4, min=−3, max=−1, evenCount=0, firstEvenIndex=−1 |
| [2] | sum=2, min=2, max=2, evenCount=1, firstEvenIndex=0 |
| [Integer.MAX_VALUE, Integer.MAX_VALUE] | sum=4294967294 (long) |
| [] | IllegalArgumentException |
| null | NullPointerException |

Với maxSubarray:

| Đầu vào | Tổng lớn nhất | Đoạn [from, toExclusive) |
| --- | ---: | --- |
| [3, −2, 5, −7, 4, 4, −1] | 8 | [4, 6) |
| [−6, −2, −5] | −2 | [1, 2) |
| [5] | 5 | [0, 1) |
| [0, 0] | 0 | [0, 1) theo quy tắc phá hòa |
| [2, −1, 2] | 3 | [0, 3) |
| [] | Ngoại lệ | IllegalArgumentException |

Ngoài các trường hợp mẫu, kiểm tra **tính chất**:

- Với mọi đầu vào hợp lệ, summarize.sum phải bằng tổng tính bằng kiểu long; min ≤ mọi phần tử ≤ max; evenCount thuộc [0, n]; firstEvenIndex = −1 nếu và chỉ nếu không có số chẵn.
- Đối với maxSubarray, 0 ≤ from < toExclusive ≤ n; tổng các phần tử trong đoạn được trả bằng trường sum; không tồn tại đoạn không rỗng nào có tổng lớn hơn.
- Cả hai phương thức không thay đổi nội dung mảng đầu vào.

Với mảng ngẫu nhiên **ngắn**, có thể dùng phép thử mọi đoạn con O(n²) hoặc O(n³) làm oracle, so sánh tổng lớn nhất để phát hiện lỗi Kadane. Oracle chậm vẫn hữu ích khi kích thước kiểm thử nhỏ. Khi kiểm tra thêm ranh giới đoạn, phải áp dụng **cùng quy tắc phá hòa**; nếu không, hai kết quả khác vị trí nhưng có cùng tổng tối ưu đều có thể đúng theo hợp đồng khác nhau.

## 12. Những lỗi triển khai thường gặp

1. **Không định nghĩa trạng thái sau mỗi bước.** Có biến nhưng không biết đại diện cho tiền tố hay cho đoạn kết thúc tại i, dẫn đến cập nhật sai. Hãy viết bất biến thành một câu chính xác trước khi code.
2. **Khởi tạo min/max bằng 0.** Với dãy toàn dương hoặc toàn âm sẽ trả cực trị sai. Khởi tạo từ phần tử đầu tiên hoặc định nghĩa trường hợp rỗng riêng.
3. **Cho phép đoạn rỗng ngoài ý muốn.** Kadane với bestSum = 0 trả sai cho toàn số âm khi yêu cầu đoạn không rỗng.
4. **Cập nhật trạng thái sai thứ tự.** Nếu dùng endingSum mới trong công thức cần endingSum cũ ở các nhánh khác, có thể đếm hai lần cùng phần tử. Dùng biến tạm hoặc cập nhật theo thứ tự đã chứng minh.
5. **Mất chỉ số khi đặt lại đoạn.** Khi bắt đầu đoạn mới tại i, phải cập nhật endingStart = i; khi best mới được cải thiện, lưu cả hai ranh giới.
6. **Tràn số do chọn kiểu hẹp.** Chuyển sang long *sau khi* phép cộng int đã tràn không cứu được kết quả. Dùng biến cộng dồn long ngay từ đầu.
7. **Lẫn bài toán toàn dãy với bài toán đoạn liên tiếp.** Tổng lớn nhất của một đoạn liên tiếp không giống tổng các phần tử dương được chọn tùy ý.
8. **Cho rằng có một for là O(n).** Nếu thân vòng lặp gọi hàm tính lại tổng tiền tố dài i, tổng thời gian là Θ(n²), dù chỉ viết một for bên ngoài.
9. **Giữ thừa dữ liệu.** Lưu mọi prefix sum khi chỉ cần tổng cuối khiến bộ nhớ tăng O(n) không cần thiết.
10. **Không kiểm thử mảng rỗng, null, toàn âm, một phần tử và hòa tổng.** Những trường hợp này thường làm lộ lỗi khởi tạo và quy tắc phá hòa.

## 13. Checklist thiết kế một thuật toán tích lũy một lượt

- [ ] Đã xác định rõ đầu ra, điều kiện đầu vào và chính sách cho dãy rỗng/null.
- [ ] Mỗi biến trạng thái có định nghĩa liên quan trực tiếp đến tiền tố đã đọc.
- [ ] Trạng thái ban đầu đúng và không đánh mất trường hợp biên.
- [ ] Phép cập nhật chỉ dùng trạng thái cũ và phần tử mới, không phụ thuộc dữ liệu đã bỏ qua mà chưa lưu.
- [ ] Có bất biến được chứng minh từ khởi tạo qua từng lần cập nhật đến kết thúc.
- [ ] Các chỉ số đoạn, vị trí đầu tiên và quy tắc phá hòa được định nghĩa rõ.
- [ ] Chọn kiểu số đủ rộng, hiểu chính sách tràn và ranh giới [l, r).
- [ ] Chi phí cập nhật thật sự O(1) nếu tuyên bố toàn thuật toán O(n).
- [ ] Đo lường bộ nhớ tính trên trạng thái phụ, phân biệt với bộ nhớ mảng đầu vào.
- [ ] Đã thử dãy mẫu, dãy rỗng, một phần tử, toàn âm/toàn 0, cực trị số và các trường hợp ngang nhau.
- [ ] Nếu cần nhiều kết quả, xác định có thể gộp trạng thái trong **cùng một lượt duyệt** hay không.

**Điều cần nhớ:** duyệt một lần hiệu quả nhờ xây dựng trạng thái chứa đúng phần thông tin của quá khứ cần cho tương lai. Bất biến cho biết *vì sao* cập nhật đúng; phân tích chi phí cho biết *vì sao* thuật toán mở rộng tuyến tính; kiểm thử xác nhận cài đặt bám sát hợp đồng.