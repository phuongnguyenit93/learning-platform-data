# Hoàn thiện bài giải với chứng minh, phân tích chi phí và kiểm thử

Một lời giải thuật toán hoàn chỉnh phải trả lời bốn câu hỏi: **bài toán được hiểu chính xác ra sao, vì sao thuật toán luôn đúng, nó tốn bao nhiêu tài nguyên, và bằng chứng nào cho thấy chương trình thực thi đúng hợp đồng?** Chỉ có mã chạy được chưa đủ. Một lời giải tốt nối đặc tả, ý tưởng, chứng minh, độ phức tạp, cài đặt và kiểm thử thành một lập luận thống nhất.

Bài thuộc nhóm **Thực hành tổng hợp** trong Computer Science Algorithms, với đề bài **“Hoàn thiện bài giải với chứng minh, phân tích chi phí và kiểm thử”**. Tài liệu đưa ra quy trình giải bài toán từ đầu đến cuối, cách xác định miền đầu vào và kết quả, xây dựng thuật toán vét cạn làm mốc, chọn cấu trúc dữ liệu, chứng minh bằng bất biến và quy nạp, đếm thời gian và bộ nhớ, thiết kế API Java, kiểm thử bằng oracle độc lập và kiểm tra trường hợp đối kháng. Ví dụ xuyên suốt là **tổng lớn nhất của một dãy con liên tiếp không rỗng (maximum subarray sum)** với thuật toán Kadane, chứng minh O(n), cài đặt Java 17+, oracle O(n²), kiểm thử ngẫu nhiên và đầu ra xác định.

## 1. Một bài giải hoàn chỉnh gồm những gì?

Một lời giải có thể được trình bày theo thứ tự sau:

1. **Đặc tả:** viết lại input, output, giới hạn, trường hợp biên và điều gì được xem là hợp lệ.
2. **Mô hình:** chọn kiểu dữ liệu, chỉ số, cấu trúc dữ liệu và định nghĩa kết quả.
3. **Ý tưởng:** mô tả vì sao hướng tiếp cận có thể giải bài toán.
4. **Thuật toán:** viết các bước hoặc giả mã không nhập nhằng.
5. **Chứng minh:** nêu bất biến, cơ sở, bước quy nạp và kết luận đúng.
6. **Phân tích chi phí:** đếm work/thời gian, bộ nhớ phụ và các chi phí đáng kể.
7. **Cài đặt:** chuyển giả mã thành API có hợp đồng, xử lý lỗi và tránh overflow.
8. **Kiểm thử:** so với oracle độc lập, kiểm biên, random, property và adversarial input.
9. **Đánh giá:** phân biệt bằng chứng đúng đắn, số đo benchmark và giới hạn của từng loại bằng chứng.
10. **Báo cáo:** ghi rõ giả định, kết quả, độ phức tạp và lệnh chạy để người khác tái lập.

Các phần phải **khớp nhau**. Nếu chứng minh nói dãy con không rỗng nhưng code cho phép trả tổng 0 từ dãy rỗng, lời giải sai đặc tả. Nếu phân tích tuyên bố O(n) nhưng code gọi sort O(n log n), phân tích sai cài đặt. Nếu test chỉ kiểm một ví dụ, nó chưa kiểm được hậu điều kiện tổng quát.

## 2. Chốt đặc tả trước khi chọn thuật toán

Đọc đề và ghi ra các câu hỏi:

- Input gồm kiểu gì, kích thước tối đa bao nhiêu?
- Có giá trị âm, 0, trùng nhau hoặc cực trị không?
- Output là một giá trị, một vị trí, một dãy, hay có thể không tồn tại?
- Thứ tự có quan trọng không? Dữ liệu có được sửa không?
- “Liên tiếp”, “khác nhau”, “ngắn nhất”, “lớn nhất” có nghĩa chính xác nào?
- Khi nhiều đáp án cùng tối ưu, quy tắc phá hòa là gì?
- Input rỗng có hợp lệ không?
- Giới hạn thời gian/bộ nhớ là gì?
- Có yêu cầu kết quả chính xác tuyệt đối hay chấp nhận sai số?
- Những input nào bị coi là lỗi thay vì một trường hợp không có kết quả?

**Không để những điều này ẩn trong code.** Đặc tả rõ giúp chọn kiểu trả về và tạo test có chủ đích.

### Ví dụ đặc tả maximum subarray

Cho mảng số nguyên `a[0..n)`. Tìm một đoạn **liên tiếp, không rỗng** [l,r) sao cho:

- 0 ≤ l < r ≤ n.
- Tổng S(l,r) = tổng a[i] với l ≤ i < r là lớn nhất trong tất cả đoạn hợp lệ.

Quy tắc phá hòa:

1. Ưu tiên **tổng lớn hơn**.
2. Nếu tổng bằng nhau, chọn **đoạn ngắn hơn**.
3. Nếu tổng và độ dài bằng nhau, chọn **đoạn có l nhỏ hơn**.

Nếu n=0, không tồn tại đoạn không rỗng, vì vậy hàm trả kết quả vắng mặt. Nếu n>0, luôn có ít nhất một đoạn hợp lệ.

Ví dụ `a=[-2,1,-3,4,-1,2,1,-5,4]` có đáp án [3,7), chứa [4,−1,2,1], tổng 6.

**Phân biệt subarray và subsequence:** subarray giữ các phần tử liền nhau; subsequence có thể bỏ qua vị trí ở giữa. Với [4,−100,5], maximum subarray sum là 5, còn maximum subsequence sum có thể là 9 nếu chọn 4 và 5. Không được đổi khái niệm giữa lời giải.

## 3. Bắt đầu bằng thuật toán vét cạn

Trước khi tối ưu, hãy xây một lời giải đơn giản để làm **định nghĩa thực thi** của bài toán.

Với mỗi vị trí bắt đầu l, thử mọi điểm kết thúc r>l, tính tổng tăng dần và giữ đoạn tốt nhất:

~~~text
best = no result
for l = 0 .. n-1:
    sum = 0
    for r = l+1 .. n:
        sum += a[r-1]
        candidate = [l,r) with this sum
        if candidate is better than best:
            best = candidate
return best
~~~

Số đoạn không rỗng của mảng n phần tử là n+(n−1)+...+1 = n(n+1)/2. Mỗi đoạn được xét đúng một lần; vì vậy thời gian O(n²), bộ nhớ phụ O(1) nếu chỉ giữ tổng hiện tại và đáp án.

Vét cạn có ba vai trò: mô hình dễ kiểm tra của đặc tả, oracle độc lập cho input nhỏ và mốc để hiểu phần tối ưu đã loại bỏ công việc lặp nào. Oracle không nhất thiết chạy được trên dữ liệu production; nó cần đơn giản, rõ ràng và đủ nhỏ để test. Không chép nguyên thuật toán Kadane rồi gọi nó là đối chứng.

## 4. Nhận ra cấu trúc để tối ưu: Kadane

Xét một đoạn tối ưu kết thúc tại vị trí i. Đoạn đó phải thuộc một trong hai dạng:

- Chỉ chứa phần tử a[i].
- Là một đoạn tối ưu kết thúc tại i−1, nối thêm a[i].

Gọi `ending[i]` là tổng lớn nhất của một đoạn **không rỗng kết thúc đúng tại i**. Khi đó:

`ending[i] = max(a[i], ending[i−1] + a[i])`.

Ta không cần lưu cả mảng ending. Chỉ cần giá trị tốt nhất ở vị trí trước, nên cập nhật bằng một biến. Đáp án toàn cục là giá trị lớn nhất của best trước đó và ending hiện tại.

Đây là ý tưởng Kadane. Mỗi phần tử chỉ được đọc và xử lý một lần.

### Quy tắc phá hòa

Khi mở rộng đoạn cũ và bắt đầu đoạn mới cho cùng tổng, đoạn bắt đầu mới ngắn hơn và được ưu tiên.

- Nếu `currentSum + a[i] > a[i]`, giữ đoạn hiện tại và nối a[i].
- Nếu `currentSum + a[i] <= a[i]`, bắt đầu đoạn mới tại i. Trường hợp bằng nhau cũng bắt đầu mới vì tổng bằng nhưng đoạn mới ngắn hơn.

Sau đó so ứng viên vừa kết thúc với đáp án toàn cục theo thứ tự: tổng giảm dần, độ dài tăng dần, chỉ số bắt đầu tăng dần.

**Điều kiện bằng nhau rất quan trọng:** nếu code chỉ dùng < thay cho <=, tổng lớn nhất vẫn đúng, nhưng quy tắc tie “đoạn ngắn nhất” có thể sai.

## 5. Giả mã hoàn chỉnh

~~~text
MAXIMUM_SUBARRAY(a):
    if length(a) == 0:
        return NO_RESULT

    currentSum = a[0]
    currentStart = 0
    best = (sum=a[0], start=0, end=1)

    for i = 1 .. length(a)-1:
        extended = currentSum + a[i]

        if extended <= a[i]:
            currentSum = a[i]
            currentStart = i
        else:
            currentSum = extended

        candidate = (
            sum=currentSum,
            start=currentStart,
            end=i+1
        )

        if candidate is better than best:
            best = candidate

    return best
~~~

Mảng rỗng được xử lý riêng vì không có phần tử đầu tiên để khởi tạo. Với mảng không rỗng, khởi tạo từ a[0] bảo đảm thuật toán luôn xét **đoạn không rỗng**, kể cả khi mọi số đều âm.

## 6. Chứng minh tính đúng bằng bất biến

Để chứng minh Kadane, tách hai mệnh đề:

1. Sau khi xử lý i, `currentSum` là tổng lớn nhất của mọi đoạn không rỗng **kết thúc tại i**; trong số đoạn cùng tổng, nó có độ dài ngắn nhất.
2. `best` là đoạn tốt nhất theo thứ tự ưu tiên đã định trong toàn bộ các đoạn kết thúc ở vị trí 0..i.

### Cơ sở quy nạp

Tại i=0, chỉ có một đoạn không rỗng kết thúc tại 0: [0,1). Ta khởi tạo current và best bằng đoạn đó, nên cả hai mệnh đề đúng.

### Bước quy nạp: chứng minh current

Xét một đoạn bất kỳ không rỗng kết thúc tại i.

- Nếu đoạn chỉ có a[i], tổng là a[i].
- Nếu đoạn dài hơn một phần tử, bỏ phần tử cuối a[i] sẽ còn một đoạn không rỗng kết thúc tại i−1. Theo giả thiết quy nạp, tổng tốt nhất của phần tiền tố đó là currentSum cũ. Nối a[i] cho tổng currentSum+a[i].

Vậy tổng lớn nhất kết thúc tại i là max(a[i], currentSum_old+a[i]).

Nếu hai lựa chọn có cùng tổng, đoạn bắt đầu mới là đoạn ngắn hơn. Nếu nối đoạn cũ cho tổng lớn hơn, ta phải giữ đoạn cũ. Do đó điều kiện `extended <= a[i]` chọn đúng đoạn tốt nhất và ngắn nhất kết thúc tại i.

### Bước quy nạp: chứng minh best

Mọi đoạn trong prefix [0,i+1) hoặc đã kết thúc trước i, hoặc kết thúc đúng i.

- Theo giả thiết quy nạp, best cũ là đoạn tốt nhất trong nhóm đầu.
- Theo mệnh đề current vừa chứng minh, candidate là đoạn tốt nhất trong nhóm kết thúc tại i.

So sánh hai đoạn theo cùng một thứ tự ưu tiên (tổng lớn hơn, ngắn hơn, trái hơn) trả về đoạn tốt nhất của hợp hai nhóm. Vì thế best vẫn đúng.

### Kết luận

Theo quy nạp, sau vòng lặp cuối, best là đoạn không rỗng có tổng lớn nhất trong toàn mảng, đồng thời tuân thủ hai quy tắc phá hòa. Với mảng rỗng, hàm trả không kết quả theo đặc tả. Vậy thuật toán đúng cho mọi mảng int hợp lệ.

**Một chứng minh đầy đủ cần cả hai phần:** current đúng cho từng điểm kết thúc và best đúng trên toàn prefix. Chỉ chứng minh recurrence của current chưa đủ để khẳng định kết quả cuối toàn mảng.

## 7. Phân tích chi phí từ chính mã

Với n=0, hàm kiểm độ dài rồi trả về, chi phí O(1). Với n≥1:

- Khởi tạo current và best: O(1).
- Vòng lặp chạy đúng n−1 lần.
- Mỗi vòng thực hiện một phép cộng, một nhánh chọn, tạo/so sánh một ứng viên với số trường cố định.
- Không có vòng lặp phụ thuộc n trong mỗi vòng.

Do đó T(n)=c0+c1(n−1)=Θ(n) với n≥1.

**Best, worst và mọi input:** bản cài Kadane quét toàn bộ n−1 phần tử còn lại, nên số lượt lặp luôn n−1. Giá trị phần tử có thể làm thay đổi nhánh, nhưng không làm giảm số vòng.

**Bộ nhớ phụ:** chỉ dùng một số hằng biến (current sum, current start, best sum/start/end, candidate), nên O(1). Record kết quả chỉ có ba primitive fields; không copy đoạn con trong vòng lặp.

| Phương pháp | Thời gian | Bộ nhớ phụ | Vai trò |
| --- | --- | --- | --- |
| Vét cạn mọi đoạn | O(n²) | O(1) | Oracle dễ hiểu |
| Kadane | O(n) | O(1) | Lời giải production |

Nếu n tăng gấp đôi, số đoạn vét cạn tăng gần 4 lần còn số vòng Kadane tăng gần 2 lần. Đây là dự đoán theo mô hình tiệm cận, không phải cam kết thời gian thực tế do cache, JIT và chi phí cố định.

## 8. Chọn kiểu số và kiểm soát overflow

Input là `int[]` nhưng tổng có thể lớn hơn miền int. Ví dụ `[2147483647,2147483647]` có tổng 4.294.967.294, vượt `Integer.MAX_VALUE`.

Dùng `long currentSum` và ép giá trị phần tử sang long khi cộng:

~~~java
long extended = currentSum + (long) values[i];
~~~

Trong Java, int được mở rộng sang long trước phép cộng ở biểu thức này. Nếu chỉ gán kết quả một phép nhân int sang long sau khi đã nhân, overflow vẫn có thể xảy ra trước khi gán.

Với `int[]` có kích thước tối đa biểu diễn bằng int, tổng trị tuyệt đối lớn nhất về mặt giới hạn lý thuyết nằm dưới `Long.MAX_VALUE`, vì mỗi phần tử có trị tuyệt đối không quá 2^31 và số phần tử không vượt 2^31−1. Vì vậy long đủ cho tổng của mọi mảng int có thể biểu diễn trong Java. Nếu đổi API sang `long[]`, cộng nhiều mảng hoặc tích lũy không giới hạn, cần kiểm tra overflow bằng `Math.addExact` hoặc dùng `BigInteger`.

**Không dùng 0 làm giá trị khởi tạo đáp án** cho bài toán đoạn không rỗng: với mảng [-8,-3,-6], đáp án phải là −3, không phải 0.

## 9. Hợp đồng API và kết quả

Dùng kiểu kết quả có tên trường rõ:

`record Subarray(long sum,int fromInclusive,int toExclusive)`.

Ý nghĩa: `sum` là tổng, `fromInclusive` là chỉ số đầu được lấy, `toExclusive` là biên cuối không lấy. Đoạn luôn không rỗng: `0≤fromInclusive<toExclusive≤n`. `length()` trả `toExclusive−fromInclusive`.

Chữ ký:

`static Optional<Subarray> maximumSubarray(int[] values)`.

**Tiền điều kiện:** `values != null`.

**Hậu điều kiện:**

- Nếu values rỗng, trả `Optional.empty()`.
- Nếu không rỗng, trả một đoạn hợp lệ và không rỗng.
- Tổng của đoạn bằng trường sum.
- Không có đoạn không rỗng nào có tổng lớn hơn.
- Nếu nhiều đoạn có cùng tổng tối đa, kết quả là đoạn ngắn nhất; nếu vẫn hòa, lấy điểm bắt đầu nhỏ nhất.
- Input không bị sửa.

Null vi phạm hợp đồng và bị từ chối bằng `Objects.requireNonNull`. Mảng rỗng là input hợp lệ, chỉ không có đoạn để trả.

## 10. Oracle vét cạn phải dùng tiêu chí phá hòa độc lập

Để kiểm Kadane, viết hàm O(n²) thử mọi đoạn. Mỗi đoạn được cộng tăng dần; tạo kết quả rồi so theo tiêu chí: tổng lớn hơn; nếu bằng, độ dài nhỏ hơn; nếu vẫn bằng, chỉ số đầu nhỏ hơn.

Trong test, oracle nên có logic so sánh được viết riêng. Nếu dùng chính helper `better()` của Kadane cho cả oracle, một lỗi trong tie-breaking có thể xuất hiện ở cả hai và không bị phát hiện.

Với n nhỏ, số đoạn chỉ là n(n+1)/2 nên oracle có thể chạy hàng nghìn test nhanh. Đối với n lớn, không dùng oracle O(n²) làm benchmark của thuật toán tối ưu.

## 11. Bộ kiểm thử cần bao phủ những gì?

| Input | Tổng tối đa | Đoạn theo tie-break |
| --- | ---: | --- |
| [-2,1,-3,4,-1,2,1,-5,4] | 6 | [3,7) |
| [-8,-3,-6] | −3 | [1,2) |
| [0,0,0] | 0 | [0,1) |
| [1,-1,1] | 1 | [0,1) |
| [] | Không có | Optional.empty |
| [Integer.MIN_VALUE] | −2147483648 | [0,1) |
| [MAX,MAX] | 4294967294 | [0,2) |

**Trường hợp biên:** mảng rỗng; một phần tử âm/0/dương; toàn âm; toàn 0; toàn dương; prefix âm rồi suffix dương; nhiều đoạn cùng tổng; giá trị int cực trị; mảng tăng/giảm, xen kẽ âm dương, phần tử lặp.

**Đối kháng:** `[-5,-1,-9]` phát hiện khởi tạo best=0; `[0,0,0]` phát hiện tie-break và đoạn rỗng; `[1,-1,1]` phát hiện quy tắc trái nhất; `[Integer.MAX_VALUE,Integer.MAX_VALUE]` phát hiện accumulator int; `[5,-5,5,-5,5]` tạo nhiều đoạn tối ưu cùng tổng.

Sinh mảng nhỏ có cả số âm, 0, dương, duplicates và cực trị; so toàn bộ kết quả Kadane với oracle vét cạn. Dùng seed cố định để lỗi có thể tái lập.

**Random testing không thay chứng minh:** nó giúp tìm bug trong code và trong việc dịch chứng minh thành implementation, nhưng hữu hạn test không chứng minh mọi mảng đúng.

## 12. Property-based và metamorphic testing

Ngoài so oracle, có thể kiểm các thuộc tính phải đúng trên mọi kết quả:

1. Nếu input rỗng thì không có result.
2. Nếu input không rỗng thì result tồn tại.
3. `0≤l<r≤n`.
4. Tổng được tính lại từ `a[l..r)` đúng bằng result.sum.
5. Không có đoạn nào có tổng lớn hơn result.sum (oracle kiểm trên input nhỏ).
6. Mọi input giữ nguyên sau lời gọi.

Một số biến đổi metamorphic hữu ích:

- **Nhân toàn bộ phần tử với hằng số dương k** sẽ nhân tổng tối đa với k và giữ thứ tự các tổng; tie-break về độ dài/vị trí giữ nguyên. Cần tránh overflow.
- **Nối một phần tử âm** chỉ giữ đáp án cũ nếu chứng minh mọi đoạn chứa phần tử mới đều kém best cũ; không dùng như property vô điều kiện.
- **Cộng một hằng số c cho mọi phần tử** không giữ nguyên đoạn tối ưu nói chung vì tổng một đoạn thay đổi thêm c×độ dài.

Metamorphic testing chỉ đáng tin khi quan hệ trước/sau được chứng minh, không nên tạo property bằng trực giác.

## 13. Java 17+ — chương trình hoàn chỉnh

Tên file: **`MaximumSubarraySolution.java`**. Chương trình cung cấp record `Subarray`, Kadane O(n) không mutate input, quy tắc tie-break tổng lớn hơn/đoạn ngắn hơn/điểm đầu nhỏ hơn, oracle O(n²) có logic so sánh riêng, ví dụ biên và 2.000 mảng ngẫu nhiên được đối chiếu.

### Mã nguồn

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.Optional;
import java.util.Random;

public class MaximumSubarraySolution {

    // A non-empty half-open interval [fromInclusive, toExclusive).
    record Subarray(long sum,
                    int fromInclusive,
                    int toExclusive) {
        Subarray {
            if (fromInclusive < 0
                    || toExclusive <= fromInclusive)
                throw new IllegalArgumentException(
                        "Subarray must be non-empty");
        }

        int length() {
            return toExclusive - fromInclusive;
        }
    }

    // Ordering: larger sum, then shorter interval,
    // then smaller starting index.
    static boolean better(Subarray candidate, Subarray current) {
        if (candidate.sum() != current.sum())
            return candidate.sum() > current.sum();
        if (candidate.length() != current.length())
            return candidate.length() < current.length();
        return candidate.fromInclusive()
                < current.fromInclusive();
    }

    static Optional<Subarray> maximumSubarray(int[] values) {
        Objects.requireNonNull(values, "values");
        if (values.length == 0)
            return Optional.empty();

        long currentSum = values[0];
        int currentStart = 0;
        Subarray best = new Subarray(values[0], 0, 1);

        for (int i = 1; i < values.length; i++) {
            long extended = currentSum + (long) values[i];

            // Restart on equality too: same sum, shorter interval.
            if (extended <= values[i]) {
                currentSum = values[i];
                currentStart = i;
            } else {
                currentSum = extended;
            }

            Subarray candidate =
                    new Subarray(currentSum, currentStart, i + 1);
            if (better(candidate, best))
                best = candidate;
        }
        return Optional.of(best);
    }

    // Independent O(n^2) oracle with its own tie comparison.
    static Optional<Subarray> bruteForceOracle(int[] values) {
        Objects.requireNonNull(values, "values");
        Subarray best = null;

        for (int left = 0; left < values.length; left++) {
            long sum = 0L;
            for (int right = left + 1;
                    right <= values.length; right++) {
                sum += (long) values[right - 1];
                Subarray candidate =
                        new Subarray(sum, left, right);

                boolean choose;
                if (best == null) {
                    choose = true;
                } else if (candidate.sum() > best.sum()) {
                    choose = true;
                } else if (candidate.sum() < best.sum()) {
                    choose = false;
                } else if (candidate.length() < best.length()) {
                    choose = true;
                } else if (candidate.length() > best.length()) {
                    choose = false;
                } else {
                    choose = candidate.fromInclusive()
                            < best.fromInclusive();
                }

                if (choose) best = candidate;
            }
        }
        return Optional.ofNullable(best);
    }

    static String describe(String label, int[] values) {
        Optional<Subarray> answer = maximumSubarray(values);
        if (answer.isEmpty())
            return label + " empty=empty";

        Subarray result = answer.orElseThrow();
        int[] selected = Arrays.copyOfRange(
                values, result.fromInclusive(), result.toExclusive());

        return label + " sum=" + result.sum()
                + " range=[" + result.fromInclusive()
                + "," + result.toExclusive() + ")"
                + " values=" + Arrays.toString(selected);
    }

    static void require(boolean condition, String message) {
        if (!condition)
            throw new AssertionError(message);
    }

    static void randomizedOracleTests() {
        Random random = new Random(5612026L);

        for (int trial = 0; trial < 2000; trial++) {
            int n = random.nextInt(41);
            int[] values = new int[n];

            for (int i = 0; i < n; i++) {
                int choice = random.nextInt(30);
                if (choice == 0) {
                    values[i] = Integer.MIN_VALUE;
                } else if (choice == 1) {
                    values[i] = Integer.MAX_VALUE;
                } else {
                    values[i] = random.nextInt(101) - 50;
                }
            }

            int[] original = values.clone();
            Optional<Subarray> fast = maximumSubarray(values);
            Optional<Subarray> slow = bruteForceOracle(values);

            require(fast.equals(slow),
                    "Kadane differs from oracle at trial " + trial);
            require(Arrays.equals(values, original),
                    "Algorithm modified input at trial " + trial);

            if (values.length == 0) {
                require(fast.isEmpty(),
                        "Empty input must have no non-empty subarray");
            } else {
                Subarray result = fast.orElseThrow();
                require(result.fromInclusive() >= 0
                                && result.fromInclusive()
                                   < result.toExclusive()
                                && result.toExclusive() <= values.length,
                        "Invalid returned interval");

                long recomputed = 0L;
                for (int i = result.fromInclusive();
                        i < result.toExclusive(); i++)
                    recomputed += (long) values[i];
                require(recomputed == result.sum(),
                        "Returned sum does not match interval");
            }
        }
        System.out.println(
                "randomizedOracle=PASS (2000 arrays)");
    }

    public static void main(String[] args) {
        System.out.println(describe("canonical", new int[]{
                -2, 1, -3, 4, -1, 2, 1, -5, 4
        }));
        System.out.println(describe(
                "allNegative", new int[]{-8, -3, -6}));
        System.out.println(describe(
                "allZero", new int[]{0, 0, 0}));
        System.out.println(describe(
                "tie", new int[]{1, -1, 1}));
        System.out.println(describe("empty", new int[0]));
        System.out.println(describe(
                "singletonMin", new int[]{Integer.MIN_VALUE}));
        System.out.println(describe("wideSum", new int[]{
                Integer.MAX_VALUE, Integer.MAX_VALUE
        }));

        randomizedOracleTests();

        int[] original = {3, -4, 5, -1};
        int[] snapshot = original.clone();
        maximumSubarray(original);
        require(Arrays.equals(original, snapshot),
                "Input was modified");
        System.out.println("immutability=PASS");

        try {
            maximumSubarray(null);
            throw new AssertionError("Expected null rejection");
        } catch (NullPointerException expected) {
            System.out.println("invalidInput=rejected");
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 MaximumSubarraySolution.java
java MaximumSubarraySolution
~~~

### Đầu ra dự kiến

~~~text
canonical sum=6 range=[3,7) values=[4, -1, 2, 1]
allNegative sum=-3 range=[1,2) values=[-3]
allZero sum=0 range=[0,1) values=[0]
tie sum=1 range=[0,1) values=[1]
empty empty=empty
singletonMin sum=-2147483648 range=[0,1) values=[-2147483648]
wideSum sum=4294967294 range=[0,2) values=[2147483647, 2147483647]
randomizedOracle=PASS (2000 arrays)
immutability=PASS
invalidInput=rejected
~~~

### Giải thích output

- **canonical:** đoạn [3,7) chứa [4,−1,2,1], tổng 6.
- **allNegative:** không có đoạn rỗng được phép; phần tử lớn nhất −3 là đáp án.
- **allZero:** mọi đoạn có tổng 0, nên chọn đoạn ngắn nhất và trái nhất [0,1).
- **tie:** hai singleton ở index0 và index2 đều có tổng 1; chọn index0.
- **empty:** không có đoạn không rỗng, trả Optional.empty.
- **singletonMin:** long biểu diễn chính xác Integer.MIN_VALUE.
- **wideSum:** hai Integer.MAX_VALUE được cộng bằng long, tổng 4.294.967.294.
- **randomizedOracle:** 2.000 mảng nhỏ gồm cả rỗng, duplicate, số âm/dương và int cực trị; Kadane phải giống oracle vét cạn về cả sum lẫn vị trí.
- **immutability:** input giữ nguyên sau khi gọi.
- **invalidInput:** null bị từ chối theo hợp đồng.

## 14. Đánh giá tính đúng và hiệu năng là hai phép kiểm khác nhau

Một chương trình có thể cho đúng mọi test đã chạy nhưng chưa chắc đáp ứng giới hạn thời gian. Ngược lại, một chương trình chạy rất nhanh vẫn có thể trả sai trên input biên.

**Correctness validation** kiểm tra kết quả đúng đặc tả, đoạn có biên hợp lệ, tổng khớp dữ liệu, tie-break đúng, input không bị sửa và empty/null được phân biệt đúng.

**Complexity validation** kiểm tra mã có thực sự chỉ quét tuyến tính, có vòng lặp lồng nhau hoặc copy ẩn không, có cấp phát object theo mỗi phần tử không, có tính lại tổng từ đầu không, và có dùng kiểu số khiến overflow làm sai kết quả.

**Benchmark** đo thời gian trên môi trường thực:

- Dùng nhiều kích thước n và nhiều kiểu dữ liệu (toàn dương, toàn âm, random, xen kẽ).
- Warmup JVM và dùng JMH nếu cần số liệu nghiêm túc.
- Lặp nhiều lần, báo median/percentile thay vì chỉ một lần đo.
- Giữ seed và input để tái lập.
- Tránh in console trong vùng được đo.
- So thuật toán trên cùng input và cùng cách tính kết quả.
- Ghi CPU/JDK/heap/GC khi số đo dùng cho quyết định kỹ thuật.

Không lấy benchmark vài mảng nhỏ để tuyên bố một cận toán học. Với Kadane, chứng minh vòng lặp chạy n−1 lần là bằng chứng O(n); benchmark chỉ trả lời nó chạy nhanh đến đâu trên môi trường cụ thể.

## 15. Chọn kỹ thuật chứng minh theo cấu trúc thuật toán

| Dạng thuật toán | Kỹ thuật chứng minh thường dùng | Điều cần chỉ ra |
| --- | --- | --- |
| Vòng lặp | Loop invariant | Khởi tạo, duy trì, kết thúc |
| Đệ quy/chia để trị | Quy nạp theo kích thước | Cơ sở và bước quy nạp |
| Greedy | Exchange argument / cut property | Có thể biến nghiệm tối ưu thành nghiệm do greedy chọn |
| BFS/DFS | Frontier, invariant thăm | Mọi đỉnh được thăm/độ sâu đúng theo quy tắc |
| Dynamic programming | Quy nạp trên trạng thái | Recurrence bao phủ mọi lựa chọn hợp lệ |
| Binary search | Khoảng ứng viên | Đáp án không bị loại và khoảng giảm |
| Minimum spanning tree | Cut/cycle property | Cạnh được chọn có thể thuộc một MST |
| Dijkstra | Thứ tự khoảng cách không giảm | Khi chốt đỉnh, không có đường đi tốt hơn qua đỉnh chưa chốt |
| Hashing | Xác suất collision và invariant bảng | Các khóa vẫn được tìm thấy theo quy tắc probe |

**Ví dụ Kadane:** bất biến theo vị trí kết thúc giúp chứng minh recurrence; best toàn cục được duy trì bằng phép so sánh ứng viên.

**Ví dụ binary search:** bất biến thường là đáp án luôn nằm trong [lo,hi], mỗi vòng giảm khoảng và điều kiện dừng trả đúng vị trí.

**Ví dụ greedy:** việc code chọn một lựa chọn “có vẻ tốt nhất ngay lúc này” không phải chứng minh. Cần lập luận rằng có một nghiệm tối ưu chứa lựa chọn đó hoặc có thể biến đổi nghiệm tối ưu để chứa nó mà không làm xấu mục tiêu.

## 16. Phân tích recurrence và tổng chi phí

Với thuật toán đệ quy, viết recurrence từ **công việc thực sự**:

`T(n)=aT(n/b)+f(n)`

nếu mỗi lời gọi tạo a bài toán con kích thước xấp xỉ n/b và làm f(n) việc ngoài đệ quy.

Ví dụ merge sort:

`T(n)=2T(n/2)+Θ(n)=Θ(n log n)`.

Ví dụ binary search:

`T(n)=T(n/2)+Θ(1)=Θ(log n)`.

Ví dụ Kadane không cần recurrence đệ quy: có n−1 vòng lặp, mỗi vòng O(1), nên Θ(n).

Nếu vòng ngoài chạy n lần và vòng trong chạy i lần ở bước i, tổng công việc là n(n+1)/2=Θ(n²). Nếu vòng trong chia đôi kích thước, có thể sinh tổng hình học 1+1/2+1/4+...<2. Phải cộng công việc thực sự, không suy độ phức tạp chỉ từ số vòng lặp nhìn thấy.

### Best, worst và average

Phải nêu phân phối nếu tính average. Một vòng lặp Kadane chạy đủ n−1 lần cho mọi dữ liệu, nên best/worst/average theo **số vòng** đều Θ(n). Với thuật toán dừng sớm, số vòng có thể phụ thuộc input; lúc đó mới phân tích từng trường hợp.

## 17. Phân tích bộ nhớ không chỉ đếm biến

Phân biệt input space, auxiliary space, output space, call stack và allocation/GC pressure.

Kadane chỉ dùng O(1) auxiliary space: không cần mảng DP n phần tử. Kết quả là ba trường primitive; không sao chép đoạn con trong quá trình tính. Vét cạn cũng có thể O(1) auxiliary space nếu chỉ giữ accumulator và best, dù thời gian O(n²).

Merge sort thường cần O(n) bộ nhớ phụ để merge. Quicksort in-place thường dùng mảng tại chỗ nhưng vẫn có stack đệ quy; worst-case stack có thể O(n) nếu partition lệch.

**Không ghi “space O(1)” mà quên copy mảng** trong implementation. Nếu hàm tạo một bản sao n phần tử, API tổng thể cần O(n) bộ nhớ bổ sung dù thuật toán lõi chỉ O(1).

## 18. Khi nào dùng kiểm thử thuộc tính, fuzzing và benchmark?

- **Unit tests:** ví dụ cố định cho hợp đồng và trường hợp biên.
- **Property-based tests:** sinh nhiều input và kiểm invariant/hậu điều kiện.
- **Differential tests:** so hai implementation độc lập, ví dụ Kadane với brute force.
- **Fuzzing:** sinh input đa dạng, đôi khi malformed, để tìm crash và bug parsing.
- **Metamorphic tests:** biến đổi input theo một quy luật đã chứng minh và kiểm mối quan hệ output.
- **Stress tests:** input lớn để quan sát bộ nhớ và hiệu năng.
- **Benchmark:** đo hiệu năng trên môi trường được kiểm soát.

Mỗi loại trả lời câu hỏi khác nhau. Fuzzing tìm lỗi nhưng không tự chứng minh thuật toán; benchmark đo tốc độ nhưng không chứng minh hậu điều kiện; brute-force oracle kiểm output nhưng không tự chứng minh O(n).

Khi một mảng random làm Kadane khác oracle, lưu seed và input. Sau đó thử loại bỏ nửa mảng, bỏ từng phần tử hoặc giảm trị tuyệt đối để tìm **phản ví dụ nhỏ nhất**. Một input như [0,0] thường dễ hiểu và sửa hơn một mảng 40 phần tử.

## 19. Cách viết lời giải để reviewer có thể kiểm chứng

Một báo cáo kỹ thuật nên có:

**Problem:** mô tả input/output và các giả định.

**Approach:** một đoạn giải thích ý tưởng và vì sao giảm được công việc.

**Algorithm:** pseudocode hoặc bước thực hiện rõ ràng.

**Correctness:** định lý và chứng minh; tránh câu “dễ thấy” ở chỗ cần lập luận.

**Complexity:** time/space với n và mô hình chi phí.

**Implementation:** ngôn ngữ, phiên bản, chữ ký API và cách xử lý lỗi.

**Validation:** test ví dụ, biên, oracle, random/property và lệnh chạy.

**Limitations:** giả định phân phối, giới hạn số, kích thước input, tie-breaking và phạm vi benchmark.

Một reviewer nên có thể trả lời: “Tôi biết vì sao thuật toán đúng, vì sao nó nằm trong giới hạn, và cách tái lập kiểm thử” mà không cần đoán các giả định ẩn.

## 20. Những lỗi làm một bài giải chưa hoàn chỉnh

1. Chưa định nghĩa rõ input/output và trường hợp rỗng.
2. Lẫn subarray liên tiếp với subsequence.
3. Không nói cách phá hòa khi có nhiều đáp án tối ưu.
4. Chỉ trình bày ý tưởng nhưng không đưa thuật toán có thể cài.
5. Đưa recurrence mà không giải thích mỗi hạng biểu diễn công việc gì.
6. Chứng minh một biến trung gian nhưng quên nối nó với output cuối.
7. Viết “greedy luôn tối ưu” mà không có exchange argument.
8. Dùng công thức average mà không nêu phân phối.
9. Dùng Big-O nhưng không nêu best/worst/expected đang xét.
10. Chỉ phân tích thời gian mà quên auxiliary space và stack.
11. Không kiểm overflow của accumulator.
12. Khởi tạo maximum sum bằng 0 dù bài yêu cầu đoạn không rỗng.
13. Đếm số vòng lặp sai vì quên lần kiểm điều kiện cuối.
14. Viết code khác giả mã ở điều kiện biên.
15. Test chỉ một ví dụ trong đề.
16. Dùng cùng implementation để sinh expected output.
17. Test random không lưu seed, không thể tái lập.
18. Ép parent/path duy nhất dù bài có nhiều đáp án hợp lệ.
19. Benchmark khi JVM chưa warmup hoặc có console I/O.
20. Kết luận hiệu năng từ một lần đo.
21. Dùng mảng copy trong code nhưng báo space O(1).
22. Không ghi phiên bản JDK hoặc lệnh build.
23. Bỏ qua empty/null và nhầm hai trạng thái.
24. Để code block không có ngôn ngữ hoặc stdout không khớp.
25. Đưa placeholder vào một lời giải được coi là hoàn tất.

## 21. Bài tập có lời giải

**Bài 1.** Bốn phần chính của một lời giải hoàn chỉnh? **Đáp án:** đặc tả, chứng minh, phân tích chi phí và kiểm thử; cài đặt phải giữ đúng các phần này.

**Bài 2.** Vì sao cần đặc tả trước khi code? **Đáp án:** để thống nhất input, output, biên và ngữ nghĩa, tránh code tự tạo giả định.

**Bài 3.** Subarray khác subsequence? **Đáp án:** subarray liên tiếp; subsequence giữ thứ tự nhưng được phép bỏ phần tử giữa.

**Bài 4.** Với [-2,1,-3,4,-1,2,1,-5,4], maximum subarray sum? **Đáp án:** 6 từ [3,7), đoạn [4,−1,2,1].

**Bài 5.** Vì sao không khởi tạo best=0 khi đoạn phải không rỗng? **Đáp án:** mảng toàn âm có đáp án âm; 0 sẽ biểu diễn đoạn rỗng không hợp lệ.

**Bài 6.** Số đoạn không rỗng của mảng n phần tử? **Đáp án:** n(n+1)/2.

**Bài 7.** Vét cạn maximum subarray mất thời gian cấp nào? **Đáp án:** Θ(n²).

**Bài 8.** Kadane giữ thông tin nào cho mỗi vị trí? **Đáp án:** tổng tốt nhất của đoạn không rỗng kết thúc đúng tại vị trí đó.

**Bài 9.** Recurrence của ending sum? **Đáp án:** max(a[i],ending[i−1]+a[i]).

**Bài 10.** Vì sao cần best toàn cục? **Đáp án:** đoạn tối ưu có thể kết thúc ở bất kỳ vị trí nào.

**Bài 11.** Trong tie-break ngắn hơn, vì sao dùng extended<=a[i]? **Đáp án:** khi bằng nhau, đoạn singleton có cùng tổng nhưng ngắn hơn.

**Bài 12.** Với [-8,-3,-6], đáp án? **Đáp án:** −3, đoạn [1,2).

**Bài 13.** Với [0,0,0], tie-break cho đáp án nào? **Đáp án:** [0,1), tổng 0.

**Bài 14.** Với [1,−1,1], tie-break trái nhất cho đoạn nào? **Đáp án:** [0,1).

**Bài 15.** Kadane có cần sort mảng không? **Đáp án:** không.

**Bài 16.** Kadane chạy bao nhiêu vòng sau khởi tạo? **Đáp án:** n−1 nếu n≥1.

**Bài 17.** Best/worst theo số vòng lặp của bản Kadane này? **Đáp án:** đều Θ(n), vì luôn quét hết.

**Bài 18.** Auxiliary space của Kadane? **Đáp án:** O(1).

**Bài 19.** Vì sao dùng long cho int[]? **Đáp án:** tổng nhiều phần tử int có thể vượt int.

**Bài 20.** Hai Integer.MAX_VALUE cộng bằng bao nhiêu? **Đáp án:** 4.294.967.294.

**Bài 21.** Oracle maximum subarray nên dùng cách nào? **Đáp án:** thử mọi đoạn O(n²), cộng tăng dần.

**Bài 22.** Vì sao oracle cần độc lập? **Đáp án:** tránh cùng lỗi logic với implementation nhanh.

**Bài 23.** Một oracle sai có thể làm gì? **Đáp án:** báo false failure hoặc cùng bug khiến lỗi không bị phát hiện.

**Bài 24.** Randomized test chứng minh mọi input đúng không? **Đáp án:** không; nó bổ trợ chứng minh và tìm phản ví dụ.

**Bài 25.** Property nào kiểm đoạn trả về? **Đáp án:** 0≤l<r≤n và tổng tính lại khớp sum.

**Bài 26.** Vì sao phải test toàn số âm? **Đáp án:** phát hiện khởi tạo sai và xử lý empty-subarray.

**Bài 27.** Vì sao phải test toàn số 0? **Đáp án:** phát hiện tie-break và lựa chọn đoạn rỗng/đoạn dài.

**Bài 28.** Kiểm input không bị sửa bằng cách nào? **Đáp án:** clone trước lời gọi và so lại sau.

**Bài 29.** Null khác empty không? **Đáp án:** null vi phạm hợp đồng, empty là input hợp lệ nhưng không có đoạn.

**Bài 30.** Best-case input của Kadane có làm vòng lặp dừng sớm không? **Đáp án:** không, bản cài này quét đủ mảng.

**Bài 31.** Chứng minh current đúng cần hai trường hợp nào? **Đáp án:** đoạn chỉ có a[i] hoặc nối một đoạn kết thúc tại i−1.

**Bài 32.** Chứng minh best toàn cục cần so nhóm nào? **Đáp án:** các đoạn kết thúc trước i và các đoạn kết thúc đúng i.

**Bài 33.** Nếu code copy toàn bộ input, space tổng thể? **Đáp án:** O(n), dù lõi Kadane O(1).

**Bài 34.** Benchmark có thay chứng minh O(n) không? **Đáp án:** không.

**Bài 35.** JMH giải quyết điều gì? **Đáp án:** hỗ trợ đo JVM có warmup, JIT và tránh một số sai lệch benchmark.

**Bài 36.** Khi nào cần recurrence? **Đáp án:** khi thuật toán đệ quy/chia để trị hoặc có cấu trúc phụ thuộc theo kích thước.

**Bài 37.** Merge sort recurrence? **Đáp án:** 2T(n/2)+Θ(n)=Θ(n log n).

**Bài 38.** Binary search recurrence? **Đáp án:** T(n/2)+Θ(1)=Θ(log n).

**Bài 39.** Auxiliary space có tính input không? **Đáp án:** thường không; cần nói rõ quy ước và tách input/output/stack.

**Bài 40.** Một bài giải có thể đúng nhưng chậm không? **Đáp án:** có; correctness và complexity/performance là hai tiêu chí riêng.

**Bài 41.** Một bài giải có thể nhanh nhưng sai không? **Đáp án:** có; benchmark không chứng minh correctness.

**Bài 42.** Nếu nhiều đáp án tối ưu thì cần gì? **Đáp án:** định nghĩa quy tắc phá hòa hoặc cho phép mọi đáp án tối ưu hợp lệ.

**Bài 43.** Khi random test fail nên lưu gì? **Đáp án:** seed, input, cấu hình và thông tin lỗi để tái lập.

**Bài 44.** Metamorphic test dùng khi nào? **Đáp án:** khi có biến đổi input với quan hệ output đã được chứng minh.

**Bài 45.** Có thể dùng max-subarray brute force trên n rất lớn không? **Đáp án:** thường không, vì O(n²); dùng làm oracle cho n nhỏ.

**Bài 46.** Vì sao báo cáo phải ghi giả định? **Đáp án:** để reviewer biết phạm vi mà chứng minh và số liệu áp dụng.

## 22. Checklist trước khi nộp lời giải

1. Đã viết lại input/output bằng ngôn ngữ chính xác?
2. Đã ghi giới hạn và miền giá trị?
3. Đã định nghĩa empty, null, duplicates và tie-break?
4. Đã phân biệt subarray, subsequence hoặc khái niệm tương tự?
5. Đã có một lời giải đơn giản làm mốc/oracle?
6. Ý tưởng tối ưu loại bỏ công việc lặp nào?
7. Giả mã có xử lý tất cả nhánh và biên?
8. Có chứng minh bất biến/định lý đủ cơ sở và bước duy trì?
9. Kết luận chứng minh có nối trực tiếp tới output?
10. Có chứng minh vòng lặp/đệ quy kết thúc?
11. Phân tích thời gian có đếm số lần lặp/thao tác?
12. Có phân biệt best/worst/average/expected khi cần?
13. Có nêu phân phối nếu nói average?
14. Có phân tích bộ nhớ phụ, stack và copy?
15. Kiểu số có đủ miền và không overflow?
16. Code có giữ đúng tie-break và empty semantics?
17. Input có bị mutate ngoài ý muốn?
18. Có oracle độc lập cho input nhỏ?
19. Có test ví dụ, biên, duplicates, cực trị và adversarial?
20. Có test random với seed tái lập?
21. Có property/hậu điều kiện kiểm tra trực tiếp?
22. Có phân biệt correctness test với benchmark?
23. Có đo hiệu năng trong điều kiện JVM phù hợp?
24. Lệnh compile/run có đầy đủ?
25. Output dự kiến có thể tái lập chính xác?
26. Báo cáo có nói rõ giới hạn của test và benchmark?

**Kết luận:** một bài giải hoàn chỉnh là một chuỗi lập luận khép kín: **đặc tả xác định điều phải tính; thuật toán biến đặc tả thành các bước; chứng minh bảo đảm bước đó đúng; phân tích chi phí xác định khả năng mở rộng; cài đặt giữ nguyên hợp đồng; kiểm thử độc lập tìm lỗi dịch từ lý thuyết sang code**. Với maximum subarray, Kadane đạt Θ(n) thời gian và O(1) bộ nhớ nhờ chỉ lưu đoạn tốt nhất kết thúc tại vị trí hiện tại và đáp án toàn cục. Chứng minh bất biến, oracle vét cạn, test tie/âm/empty/overflow và benchmark đúng cách làm cho lời giải có thể kiểm chứng và tái lập.
