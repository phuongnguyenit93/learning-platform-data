# Sắp xếp trước để đơn giản hóa các bước xử lý

**Sắp xếp trước khi xử lý** (*sort-first preprocessing*) là một kỹ thuật thiết kế thuật toán: ta chủ động chuyển dữ liệu từ thứ tự ban đầu sang thứ tự theo một khóa, chấp nhận trả chi phí sắp xếp để các thao tác sau trở nên đơn giản và có thể chứng minh hiệu quả. Khi dữ liệu đã sắp, phần tử bằng nhau thường liền kề, mọi giá trị bên trái không lớn hơn giá trị đang xét, các khoảng có thể quét theo đầu mút, và truy vấn theo ngưỡng có ranh giới đơn điệu.

Điều quan trọng không phải lúc nào cũng “cứ sort rồi giải”. Ta cần trả lời: **Thứ tự ban đầu có phải một phần của bài toán không? Sau sort sẽ dùng được bất biến nào? Chi phí sắp có được bù lại? Có cần giữ chỉ số gốc hay tính ổn định giữa các bản ghi bằng khóa không?**

Bài học thuộc nhóm **Biến đổi và tiền xử lý**, tập trung vào cách dùng phép sắp xếp như một bước biến đổi để giải các bài toán về dãy, cặp phần tử, khoảng và truy vấn offline. Các ví dụ chính dùng Java 17, có đầu ra xác định và giải thích bất biến.

## 1. Sắp xếp thay đổi điều gì?

Cho dãy:

~~~text
Ban đầu:              [7, 1, 3, 3, 2, 7, -1]
Sắp tăng không giảm:   [-1, 1, 2, 3, 3, 7, 7]
~~~

Mảng sau sắp vẫn chứa đúng các giá trị −1, 1, 2, 3, 3, 7, 7, mỗi giá trị với cùng **số lần xuất hiện**. Nhưng các phần tử đã đổi vị trí. Từ thứ tự mới, ta có một số quy luật:

- Hai phần tử có cùng giá trị không bị ngăn cách bởi phần tử có giá trị khác: các giá trị trùng tạo thành **một nhóm liên tiếp**.
- Nếu i < j, `a[i] <= a[j]`; nhờ vậy có thể loại bỏ hàng loạt ứng viên khi so sánh tổng hai số với một ngưỡng.
- Điều kiện `a[i] <= x` đúng trên một **tiền tố**, còn `a[i] > x` đúng trên **hậu tố**, giúp dùng tìm kiếm nhị phân.
- Sau khi sắp các khoảng theo đầu trái, khoảng tiếp theo không thể bắt đầu trước các khoảng đã xét, giúp gộp theo một lượt quét.
- Sau khi sắp sự kiện theo thời gian, trạng thái có thể cập nhật theo thứ tự thời gian thay vì xét mọi cặp sự kiện.

Các kết luận trên phụ thuộc **khóa so sánh**. Với đối tượng `(score,id)`, sắp theo score sẽ tạo tính đơn điệu theo score, **không tự động** tạo tính đơn điệu theo id.

### Phần nào được bảo toàn, phần nào không?

**Được bảo toàn:** đa tập giá trị hoặc bản ghi nếu phép sắp chỉ hoán vị, số lượng phần tử, và những tính chất chỉ phụ thuộc đa tập như min, max, tổng, sự tồn tại của hai giá trị có tổng cụ thể.

**Có thể bị thay đổi:** chỉ số ban đầu, thứ tự thời gian, quan hệ liền kề trong dãy gốc, các đoạn con liên tiếp, thứ tự tương đối của hai bản ghi bằng khóa nếu phép sắp không ổn định.

Ví dụ nếu bài hỏi **tổng đoạn con liên tiếp lớn nhất**, không thể tự ý sắp dãy trước, vì sau sort, các tập phần tử liền nhau có thể hoàn toàn khác. Để dùng sort-first an toàn, phải chứng minh **thứ tự gốc không ảnh hưởng mục tiêu** hoặc phải mang theo đủ thông tin gốc để khôi phục kết quả.

## 2. Chi phí tiền xử lý và điểm hòa vốn

Gọi n là số phần tử, q là số truy vấn. Với sort so sánh tổng quát, chi phí thường là O(n log n), trong khi bước xử lý sau khi sort có thể chỉ O(n) hoặc O(log n) một truy vấn.

| Chiến lược | Chi phí chuẩn bị | Chi phí mỗi yêu cầu | Tổng chi phí |
| --- | --- | --- | --- |
| Quét mảng ban đầu cho mỗi ngưỡng x | O(1) | O(n) | O(nq) |
| Sắp một lần, sau đó binary search theo x | O(n log n) | O(log(n+1)) | O(n log n + q log(n+1)) |
| Sắp một lần rồi gộp/duyệt toàn bộ | O(n log n) | O(n) cho một lượt | O(n log n) |
| Chỉ tìm min hoặc max một lần | Không cần sắp | O(n) quét | O(n) |

Bởi vậy:
- **Một truy vấn đơn lẻ:** có thể quét O(n), không đáng sắp O(n log n).
- **Rất nhiều truy vấn trên dữ liệu không đổi:** sắp một lần rồi trả từng truy vấn O(log n) có lợi.
- **Cần kết quả đã sắp:** chi phí sort chính là một phần yêu cầu.
- **Dữ liệu thay đổi giữa truy vấn:** việc sắp lại mỗi lần có thể tốn kém; phải cân nhắc cấu trúc online.

Khi nói “sau sort giải trong O(n)”, phải ghi rõ **tổng thuật toán là O(n log n + n) = O(n log n)**, không được bỏ qua chi phí đã trả trước. Nếu dữ liệu đã được đảm bảo sắp sẵn, không cần sort lại và lúc đó chỉ còn chi phí bước xử lý.

Trong thực tế, chi phí còn phụ thuộc bộ nhớ, cache, so sánh chuỗi dài, boxing, cấp phát object, GC và cách biểu diễn bản ghi. Các ký hiệu Big-O là cơ sở so sánh khả năng mở rộng, không phải cam kết về thời gian đo được trên mọi máy.

## 3. Mẫu 1: gom nhóm, đếm tần suất và loại trùng

Sau khi sắp `[7,1,3,3,2,7,-1]`, ta được:

~~~text
Dãy đã sắp: [-1, 1, 2, 3, 3, 7, 7]
Nhóm giá trị: [-1] [1] [2] [3,3] [7,7]
Các giá trị khác nhau: [-1, 1, 2, 3, 7]
Tần suất: -1:1, 1:1, 2:1, 3:2, 7:2
~~~

**Thuật toán loại trùng:** sau khi sort, duyệt i từ 0 đến n−1; ghi a[i] vào kết quả nếu i=0 hoặc a[i] khác giá trị liền trước. Có thể dùng hai con trỏ `read` và `write` trên bản sao mảng đã sắp để nén vào đầu mảng rồi cắt đúng phần tử cần dùng.

**Thuật toán đếm tần suất:** giữ vị trí bắt đầu của nhóm `start`, tăng `end` tới vị trí đầu tiên có giá trị khác; nhóm có tần suất `end-start`. Mỗi phần tử được duyệt đúng một lần khi quét.

### Vì sao đúng?

Giả sử `a[i] = a[j] = v` với i < j trong một dãy đã sắp không giảm. Mọi phần tử ở giữa thỏa `v <= a[k] <= v`, nên cũng bằng v. Vì thế tất cả phần tử cùng giá trị nằm trong **một đoạn liên tiếp**. Lấy đầu mỗi đoạn sẽ cho đúng **một lần xuất hiện của mỗi giá trị**.

**Độ phức tạp:** sort O(n log n), duyệt O(n), tổng O(n log n). Nếu cần một danh sách giá trị mới, dung lượng đầu ra có thể O(n). Nếu chỉ cần đếm tần suất, một `HashMap` thường đạt O(n) kỳ vọng và O(u) bộ nhớ với u số giá trị phân biệt, nhưng **không tự tạo thứ tự tăng dần** của khóa.

**Lỗi hay gặp:** dùng phần tử `a[0]` khi mảng rỗng; xóa trùng trong khi bài yêu cầu giữ bội số; nhầm việc “lấy các giá trị khác nhau” với “lấy từng bản ghi có danh tính khác nhau”. Nếu nhiều bản ghi có cùng khóa nhưng thông tin khác, cần xác định chính xác yêu cầu gom nhóm.

## 4. Mẫu 2: two pointers sau sắp để tìm cặp tổng mục tiêu

Cho mảng n số, cần tìm **một cặp phần tử ở hai chỉ số khác nhau** có tổng bằng `target`, hoặc báo không tồn tại. Bài này không yêu cầu cặp đầu tiên theo chỉ số gốc và không yêu cầu liệt kê mọi cặp.

Sau khi sắp tăng, đặt `left=0` và `right=n−1`:

~~~text
while left < right:
    sum = a[left] + a[right]
    if sum == target: tìm được một cặp
    if sum < target: left = left + 1
    else: right = right - 1
Nếu hai con trỏ gặp nhau: không tồn tại cặp
~~~

### Tại sao được phép bỏ một đầu?

Nếu tổng hiện tại **nhỏ hơn target**, vì `a[right]` là phần tử lớn nhất trong đoạn ứng viên, ta có:

~~~text
với mọi j <= right:
    a[left] + a[j] <= a[left] + a[right] < target
~~~

Vậy `a[left]` không thể ghép với bất kỳ vị trí còn lại nào để đạt target. Tăng left là **loại bỏ an toàn**.

Nếu tổng hiện tại **lớn hơn target**, vì `a[left]` là phần tử nhỏ nhất trong đoạn, với mọi i ≥ left, `a[i]+a[right] >= a[left]+a[right] > target`. Vậy giảm right cũng an toàn.

Mỗi bước dịch một con trỏ vào trong, nên lượt xử lý sau sort chỉ O(n). Thuật toán đúng vì **thứ tự không giảm biến việc loại bỏ một con trỏ thành loại bỏ cả một tập ứng viên không thể thành công**.

### Ví dụ có cả dịch trái và dịch phải

~~~text
Đầu vào:        [8, 3, 5, 2, 7, 3]
Sau sắp:        [2, 3, 3, 5, 7, 8]
target = 12
~~~

| Giá trị ở left / right | Tổng | Hành động |
| --- | ---: | --- |
| 2 / 8 | 10 | Quá nhỏ → tăng left |
| 3 / 8 | 11 | Quá nhỏ → tăng left |
| 3 / 8 | 11 | Quá nhỏ → tăng left |
| 5 / 8 | 13 | Quá lớn → giảm right |
| 5 / 7 | 12 | Tìm được cặp |

Kết quả có thể là **(5,7)**; trong mảng gốc, chúng ở **chỉ số 2 và 4** (0-based).

Nếu đề yêu cầu **trả chỉ số gốc**, không được chỉ sort một `int[]` rồi trả vị trí trong mảng đã sắp. Cần lưu từng bản ghi `(value,originalIndex)`, sắp theo value và mang theo originalIndex. Với target=6, hai số 3 ở chỉ số gốc **1 và 5** tạo thành cặp hợp lệ; điều kiện `left<right` đảm bảo hai chỉ số thực sự khác nhau.

**Cẩn thận tràn số:** tính tổng hai `int` bằng `int` có thể tràn. Trong Java, ép một toán hạng sang long trước khi cộng: `long sum=(long) a[left]+a[right]`. Comparator cho bản ghi cũng phải dùng `Integer.compare` hoặc `Comparator.comparingInt`, không trừ hai khóa nguyên.

**Đánh đổi:** một lần two-sum có thể dùng `HashMap` O(n) kỳ vọng với O(n) bộ nhớ, không cần sắp. Sắp + two pointers O(n log n) phù hợp nếu dữ liệu đã sắp, cần những phép xử lý khác trên thứ tự ấy, hoặc muốn giải một họ bài toán nhiều ngưỡng/cặp. Đừng dùng sort chỉ vì có thể dùng two pointers.

## 5. Mẫu 3: merge các khoảng sau khi sắp đầu trái

Cho m đoạn **đóng** `[start,end]` với start ≤ end. Mục tiêu là xuất những khoảng biểu diễn **hợp các khoảng ban đầu**, đã gộp những khoảng giao nhau hoặc chạm ở đầu mút và được sắp theo start.

Ví dụ:

~~~text
Đầu vào:
[5,7], [1,3], [2,4], [8,8], [7,9], [12,15]

Sau sắp theo start:
[1,3], [2,4], [5,7], [7,9], [8,8], [12,15]

Kết quả:
[1,4], [5,9], [12,15]
~~~

### Thuật toán

1. Sắp các khoảng theo `start` tăng dần; nếu bằng start, có thể so tiếp `end` để kết quả rõ ràng.
2. Giữ danh sách kết quả, ban đầu rỗng.
3. Với mỗi đoạn mới `next=[l,r]`:
   - Nếu kết quả rỗng: thêm một bản sao của next.
   - Nếu đoạn cuối là `current=[L,R]` và `l <= R`: thay đoạn cuối bằng `[L,max(R,r)]`.
   - Nếu `l > R`: thêm một đoạn riêng.
4. Sau khi xử lý hết, trả kết quả.

**Vì sao cần max(R,r)?** Nếu current=[1,10] còn next=[3,4], đoạn sau **nằm hoàn toàn bên trong** đoạn trước. Gán current.end=4 sẽ làm mất phần [4,10]; dùng max giữ đúng hợp.

### Bất biến khi quét

Sau khi xử lý t đoạn theo thứ tự start, danh sách kết quả biểu diễn đúng hợp của t đoạn ấy, không có hai đoạn nào trong danh sách giao nhau theo quy ước gộp.

Với đoạn tiếp theo [l,r], nếu l≤R thì phần giao/chạm cho phép hợp nhất mà không thay đổi tập điểm được phủ. Nếu l>R thì đoạn hiện tại tách biệt đoạn cuối; do các đoạn tiếp theo chỉ có start **không nhỏ hơn l**, chúng không thể quay ngược để nối đoạn đã chốt. Vì vậy có thể thêm đoạn mới một cách an toàn.

**Chi phí:** sắp O(m log m), quét O(m), tổng O(m log m). Nếu đầu vào đã sắp theo start, chỉ cần lượt gộp O(m).

### Khoảng đóng và khoảng nửa mở

Hai khoảng đóng [1,3] và [3,5] **giao nhau tại điểm 3** và được gộp thành [1,5]. Hai khoảng nửa mở [1,3) và [3,5) **không giao nhau**, nhưng hợp của chúng đúng bằng [1,5), nên có thể gộp nếu bài yêu cầu **biểu diễn hợp tối giản**, không chỉ gộp khi có giao thật. Phải định nghĩa trước điều kiện hợp nhất theo yêu cầu.

Với khoảng đóng trên các số nguyên, hai đoạn [1,2] và [3,4] **không giao nhau**, dù không thiếu số nguyên nào giữa chúng. Nếu bài cho phép gộp **kề nhau**, điều kiện khác với chỉ gộp khoảng giao. Không tự động dùng `end+1` trên int mà chưa tính trường hợp tràn.

## 6. Mẫu 4: nhiều truy vấn ngưỡng và binary search

Có n số nguyên **không thay đổi giữa các truy vấn**, cùng q câu hỏi:

> Có bao nhiêu phần tử `<= x`?

Quét riêng mỗi câu mất O(nq). Sau khi sắp mảng không giảm, các phần tử ≤ x tạo thành **một tiền tố liên tiếp**. Độ dài tiền tố này chính là vị trí đầu tiên có phần tử **> x**, hay **upper bound**.

Ví dụ:

~~~text
Mảng đã sắp: [-1, 1, 2, 3, 3, 7, 7]
countAtMost(-2) = 0
countAtMost(3)  = 5
countAtMost(5)  = 5
countAtMost(7)  = 7
~~~

### Cách tìm upper bound với khoảng nửa mở

~~~text
left = 0; right = n
while left < right:
    mid = left + (right-left) / 2
    if a[mid] <= x:
        left = mid + 1
    else:
        right = mid
return left
~~~

**Bất biến:** mọi phần tử trước left đều ≤ x; mọi phần tử từ right trở đi đều > x. Vì dữ liệu đã sắp, một phép so sánh tại mid đủ để xác nhận cả một nửa các vị trí. Khi left=right, đó chính là cận đầu tiên có giá trị > x, nên số phần tử ≤ x bằng left.

Các kết quả biên hợp lệ: trả 0 nếu mọi số > x, trả n nếu mọi số ≤ x. Không được truy cập `a[n]` sau khi hàm trả n vì đó là **vị trí chèn logic**, không phải chỉ số phần tử hợp lệ.

**Phân biệt lower/upper bound:**
- `lower_bound(x)`: vị trí đầu tiên có giá trị **≥ x**, đếm số phần tử **< x**.
- `upper_bound(x)`: vị trí đầu tiên có giá trị **> x**, đếm số phần tử **≤ x**.
- Số phần tử **bằng x** = upper_bound(x) − lower_bound(x).

Điều kiện `<` và `<=` khác nhau khi có phần tử trùng, nên mảng [2,2,2] là phản ví dụ nhỏ để thử.

**Chi phí tổng:** sort O(n log n) một lần; mỗi truy vấn O(log(n+1)); q truy vấn tổng O(n log n + q log(n+1)). Nếu q rất nhỏ, quét O(n) cho từng truy vấn có thể đủ và đơn giản hơn.

### Biến thể offline: sắp cả truy vấn

Nếu có rất nhiều truy vấn ngưỡng, có thể sắp các truy vấn theo x tăng dần và duyệt đồng thời dãy giá trị đã sắp. Với mỗi query.x, di chuyển con trỏ pos qua các giá trị ≤ x, rồi ghi đáp án pos. **Phải lưu originalQueryIndex** nếu kết quả cần trả theo thứ tự truy vấn ban đầu. Chi phí khoảng O(n log n + q log q + n + q), không cần q phép binary search riêng.

Điểm chung: sort-first giúp biến các phần tử thỏa ngưỡng thành **một tiền tố**, từ đó trả lời bằng một ranh giới thay vì duyệt toàn bộ mỗi lần.

## 7. Mẫu 5: sắp sự kiện theo thời gian và quét

Bài có nhiều sự kiện, chẳng hạn bắt đầu/kết thúc công việc, vào/ra phòng, mở/đóng phiên hoặc thay đổi mức phủ. Khi sắp **thời điểm** tăng dần, ta có thể giữ trạng thái đang hoạt động thay vì xét mọi cặp sự kiện.

Với các khoảng thời gian **nửa mở [start,end)**, tạo sự kiện:
- `(start,+1)`: tăng số sự kiện đang hoạt động.
- `(end,-1)`: giảm số sự kiện đang hoạt động.

Sắp sự kiện theo timestamp. Tại mỗi thời điểm t, có thể **gộp tất cả delta cùng thời điểm** rồi cập nhật số lượng đang hoạt động. Giá trị này không đổi trên đoạn [t,nextTimestamp). Cách gộp cùng timestamp giúp tránh sai lệch tạm thời do xử lý bắt đầu trước hay kết thúc trước khi hai sự kiện cùng mốc.

Nếu đề dùng khoảng **đóng** hoặc quan tâm đến tình trạng “đang hoạt động đúng tại t” theo một quy tắc sự kiện cụ thể, thứ tự xử lý hòa sẽ khác. Cần nêu rõ quy ước trước khi viết comparator. Không có một quy tắc ưu tiên start/end đúng cho mọi bài.

Sắp sự kiện là một ví dụ của phương pháp **sweep line**: sắp một tọa độ, sau đó dùng trạng thái quét để giải bài toán trên tập đối tượng. Khi dữ liệu đầu vào vốn theo thứ tự thời gian, có thể bỏ bước sắp, miễn được **bảo đảm** thứ tự ấy.

## 8. Ví dụ Java 17 hoàn chỉnh

Chương trình sau gom bốn ứng dụng chính:
1. Sort rồi loại trùng bằng hai con trỏ read/write.
2. Sort rồi dùng upper bound để đếm số phần tử ≤ ngưỡng.
3. Sort các bản ghi `(value,originalIndex)` rồi tìm cặp tổng bằng hai con trỏ.
4. Sort các khoảng đóng rồi gộp, giữ nguyên các mảng gốc nhờ bản sao.

Các hàm độc lập, có tiền điều kiện rõ ràng, kết quả chạy được đối chiếu bên dưới.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class SortBeforeProcessingDemo {
    record Entry(int value, int originalIndex) {}
    record Pair(int leftValue, int rightValue,
                int leftIndex, int rightIndex) {}

    static int[] distinctSorted(int[] input) {
        int[] sorted = input.clone();
        Arrays.sort(sorted);
        if (sorted.length == 0) {
            return new int[0];
        }
        int write = 1;
        for (int read = 1; read < sorted.length; read++) {
            if (sorted[read] != sorted[write - 1]) {
                sorted[write] = sorted[read];
                write++;
            }
        }
        return Arrays.copyOf(sorted, write);
    }

    // Trả một cặp hợp lệ, không hứa trả cặp duy nhất.
    static Pair twoSumAfterSort(int[] input, long target) {
        Entry[] entries = new Entry[input.length];
        for (int i = 0; i < input.length; i++) {
            entries[i] = new Entry(input[i], i);
        }
        Arrays.sort(entries,
                Comparator.comparingInt(Entry::value)
                        .thenComparingInt(Entry::originalIndex));

        int left = 0;
        int right = entries.length - 1;
        while (left < right) {
            long sum = (long) entries[left].value()
                    + entries[right].value();
            if (sum == target) {
                return new Pair(entries[left].value(),
                        entries[right].value(),
                        entries[left].originalIndex(),
                        entries[right].originalIndex());
            }
            if (sum < target) {
                left++;
            } else {
                right--;
            }
        }
        return null;
    }

    static String pairText(Pair p) {
        if (p == null) {
            return "none";
        }
        return "values=(" + p.leftValue() + ", " + p.rightValue()
                + "), originalIndices=(" + p.leftIndex()
                + ", " + p.rightIndex() + ")";
    }

    // Đoạn đóng [start, end], có start <= end.
    static int[][] mergeClosedIntervals(int[][] input) {
        int[][] intervals = new int[input.length][2];
        for (int i = 0; i < input.length; i++) {
            if (input[i] == null || input[i].length != 2
                    || input[i][0] > input[i][1]) {
                throw new IllegalArgumentException("Invalid interval");
            }
            intervals[i] = input[i].clone();
        }
        Arrays.sort(intervals, (a, b) -> {
            int byStart = Integer.compare(a[0], b[0]);
            return byStart != 0
                    ? byStart : Integer.compare(a[1], b[1]);
        });

        List<int[]> merged = new ArrayList<>();
        for (int[] next : intervals) {
            if (merged.isEmpty()
                    || next[0] > merged.get(merged.size() - 1)[1]) {
                merged.add(next.clone());
            } else {
                int[] current = merged.get(merged.size() - 1);
                current[1] = Math.max(current[1], next[1]);
            }
        }
        return merged.toArray(new int[0][]);
    }

    // Mảng sorted bắt buộc đã sắp không giảm.
    static int countAtMost(int[] sorted, int x) {
        int left = 0;
        int right = sorted.length;
        while (left < right) {
            int mid = left + (right - left) / 2;
            if (sorted[mid] <= x) {
                left = mid + 1;
            } else {
                right = mid;
            }
        }
        return left;
    }

    public static void main(String[] args) {
        int[] values = {7, 1, 3, 3, 2, 7, -1};
        int[] sorted = values.clone();
        Arrays.sort(sorted);

        System.out.println("sorted=" + Arrays.toString(sorted));
        System.out.println("distinct="
                + Arrays.toString(distinctSorted(values)));
        for (int x : new int[]{-2, 3, 5, 7}) {
            System.out.println("count<=" + x + "="
                    + countAtMost(sorted, x));
        }
        System.out.println("originalPreserved="
                + Arrays.equals(values,
                    new int[]{7, 1, 3, 3, 2, 7, -1}));

        int[] pairInput = {8, 3, 5, 2, 7, 3};
        System.out.println("twoSum12="
                + pairText(twoSumAfterSort(pairInput, 12)));
        System.out.println("twoSum6="
                + pairText(twoSumAfterSort(pairInput, 6)));
        System.out.println("twoSum100="
                + pairText(twoSumAfterSort(pairInput, 100)));

        int[][] sourceIntervals = {
            {5, 7}, {1, 3}, {2, 4},
            {8, 8}, {7, 9}, {12, 15}
        };
        int[][] merged = mergeClosedIntervals(sourceIntervals);
        System.out.println("merged=" + Arrays.deepToString(merged));

        int[][] empty = {};
        System.out.println("emptyIntervals="
                + Arrays.deepToString(mergeClosedIntervals(empty)));
    }
}
~~~

Lưu tệp **SortBeforeProcessingDemo.java**. Với **JDK 17 trở lên**, chạy:

~~~bash
javac SortBeforeProcessingDemo.java
java SortBeforeProcessingDemo
~~~

**Đầu ra chính xác:**

~~~text
sorted=[-1, 1, 2, 3, 3, 7, 7]
distinct=[-1, 1, 2, 3, 7]
count<=-2=0
count<=3=5
count<=5=5
count<=7=7
originalPreserved=true
twoSum12=values=(5, 7), originalIndices=(2, 4)
twoSum6=values=(3, 3), originalIndices=(1, 5)
twoSum100=none
merged=[[1, 4], [5, 9], [12, 15]]
emptyIntervals=[]
~~~

### Những quyết định triển khai cần chú ý

**Dữ liệu gốc được giữ:** `distinctSorted` và thao tác sắp mảng count dùng clone, `twoSumAfterSort` tạo Entry mới, còn `mergeClosedIntervals` clone từng đoạn hai phần tử. Chương trình không buộc người gọi đánh mất thứ tự/giá trị gốc.

**Pair và Entry là record:** Java 17 hỗ trợ cú pháp này. Mỗi Entry giữ `value` và `originalIndex`; sắp theo value rồi index để có quy tắc hòa xác định. `Pair` chỉ trả một nghiệm; không có cam kết nghiệm duy nhất hoặc nghiệm đầu tiên theo thứ tự index.

**Tổng hai int được nâng lên long trước khi cộng:** phép `(long) entries[left].value() + entries[right].value()` tránh overflow int. Bài có target kiểu long nên kiểm tra được cả các tổng nằm ngoài miền int.

**Khoảng giao:** code dùng điều kiện `next.start <= current.end` để gộp đoạn đóng giao hoặc chạm nhau; đoạn nằm trong đoạn khác không làm đầu phải co lại vì dùng `Math.max`.

**countAtMost không sắp lại:** hàm được gọi trên `sorted`, phải bảo đảm tiền điều kiện đầu vào đã sắp không giảm. Có thể dùng một bản dữ liệu đã sắp để trả nhiều truy vấn mà không mất lại chi phí sort.

**Bộ nhớ:** các bản sao và đối tượng Entry là lựa chọn có chủ đích để bảo toàn đầu vào/metadata. Không được kết luận “toàn bộ thuật toán O(1) bộ nhớ phụ” chỉ vì lượt quét sau sort cần vài con trỏ.

## 9. Chứng minh tính đúng của sort-first

Một chứng minh tốt cần hai phần: **tại sao phép sắp hợp lệ với mục tiêu** và **tại sao thao tác sau khi sắp đúng**.

### 9.1. Tiền xử lý hợp lệ

Nếu bài toán chỉ quan tâm đến **đa tập giá trị**, việc sắp chỉ hoán vị nên không làm thay đổi lời giải. Ví dụ: có tồn tại hai số với tổng x không, có bao nhiêu phần tử ≤ x, hoặc các giá trị nào xuất hiện. Sắp không phá những tính chất đó.

Nếu đề hỏi giá trị cùng **chỉ số gốc**, có thể giữ bản ghi `(value, originalIndex)` và chuyển đáp án về hệ chỉ số gốc. Nhưng nếu đề hỏi **đoạn con liên tiếp**, sort có thể thay đổi tập các đoạn hợp lệ, nên không thể sử dụng mà thiếu một chứng minh tương đương.

### 9.2. Bất biến two pointers

Trong đoạn ứng viên `[left,right]`, nếu vẫn tồn tại cặp đáp án chưa tìm thấy, ít nhất một nghiệm nằm hoàn toàn trong đoạn đó. Khi tổng quá nhỏ, bỏ left vì không thể ghép nó với bất kỳ giá trị còn lại đạt target. Khi tổng quá lớn, bỏ right vì nó ghép với mọi giá trị còn lại đều quá lớn. Mỗi bước thu hẹp đoạn, nên thuật toán kết thúc và không bỏ sót một nghiệm tồn tại.

### 9.3. Bất biến merge intervals

Sau khi quét một tiền tố của các đoạn đã sắp theo start, danh sách kết quả có hợp đúng với các đoạn đã xem và gồm các đoạn không giao nhau. Khi đoạn tiếp theo bắt đầu trước hoặc bằng end của đoạn cuối, gộp chúng vẫn giữ đúng hợp; khi bắt đầu muộn hơn, đoạn mới tách biệt với đoạn cuối. Vì các start còn lại không thể giảm, những đoạn đã hoàn tất không cần xét lại.

### 9.4. Bất biến upper bound

Trong tìm kiếm nhị phân, mọi vị trí trước left đã biết chứa giá trị ≤ x, còn mọi vị trí từ right tới cuối đã biết chứa giá trị > x. Bởi a đã sắp, kiểm tra một mid đủ để phân loại cả phía liên quan. Khi left=right, đó chính là số vị trí ≤ x. Tính đúng của upper bound **phụ thuộc việc sort đúng** trước đó.

Từ các bất biến ấy, ta thấy sắp không chỉ “làm chương trình gọn”: nó **tạo ra một cấu trúc có thể chứng minh**, cho phép loại trừ an toàn những ứng viên hoặc chốt một đoạn kết quả.

## 10. Phân tích độ phức tạp và bộ nhớ thực tế

| Công việc | Tiền xử lý | Xử lý sau sắp | Tổng thời gian | Bộ nhớ thêm trong cách cài ví dụ |
| --- | --- | --- | --- | --- |
| Giá trị phân biệt (n số) | O(n log n) | O(n) | O(n log n) | O(n) do clone và kết quả |
| Two-sum với chỉ số gốc | O(n log n) | O(n) | O(n log n) | O(n) Entry và mảng tham chiếu |
| Gộp m đoạn | O(m log m) | O(m) | O(m log m) | O(m) bản sao và kết quả |
| q truy vấn count≤x | O(n log n) | O(log(n+1)) mỗi truy vấn | O(n log n+q log(n+1)) | O(n) bản clone một lần |
| e sự kiện thời gian | O(e log e) | O(e) | O(e log e) | Phụ thuộc cách lưu sự kiện |

**Chi phí thư viện:** `Arrays.sort(int[])` thay đổi mảng primitive tại chỗ; `Arrays.sort(Object[],Comparator)` có thể cần vùng đệm và mang chi phí sắp các tham chiếu. Mức RAM thực phụ thuộc phiên bản/runtime và cách cài. Tuyên bố O(1) bộ nhớ cho toàn bộ chương trình ví dụ là sai vì đã clone dữ liệu và tạo bản ghi.

**Trường hợp đầu vào đã sắp:** nếu có bảo đảm đầu vào tăng không giảm, có thể bỏ bước tiền xử lý. Nhưng nếu dữ liệu chỉ **có vẻ** đã sắp trong một vài mẫu, không được tùy tiện bỏ sort. Có thể xác nhận bằng một lượt quét O(n) khi điều đó phù hợp hợp đồng.

**Đầu ra lớn:** nếu bài yêu cầu liệt kê tất cả cặp thỏa điều kiện, có thể có Θ(n²) kết quả. Không phương pháp nào in từng cặp trong thời gian dưới bậc số lượng cặp được xuất, bất kể đã sắp.

## 11. Tính ổn định, khóa phụ và các phép so sánh an toàn

**Sắp ổn định** (*stable sort*) giữ thứ tự tương đối ban đầu của các bản ghi mà comparator đánh giá bằng nhau. Ví dụ:

~~~text
Trước:     [(2,A), (1,B), (2,C)]
Ổn định:   [(1,B), (2,A), (2,C)]
~~~

Trong Java 17, `Arrays.sort(T[],Comparator)` sắp ổn định theo hợp đồng. Tuy nhiên, một mảng primitive `int[]` không có danh tính riêng của các số bằng nhau để quan sát tính ổn định. Nếu có các trường dữ liệu gắn kèm, hãy sắp **các bản ghi đầy đủ** hoặc **chỉ số** thay vì chỉ sắp cột khóa.

Một comparator theo `value` rồi `originalIndex` sẽ phục hồi thứ tự chỉ số trong nhóm cùng value. Nhưng đây là **khóa so sánh hai tầng**, không tự chứng minh thuật toán sort bên dưới ổn định.

### Tránh tràn số khi so sánh

Comparator kiểu `(a,b) -> a.value-b.value` có thể tràn int với khóa cực trị, dẫn tới sai dấu và phá tính bắc cầu. Hãy dùng `Integer.compare(a.value,b.value)`, `Comparator.comparingInt`, hoặc `Long.compare` nếu dùng long.

Trong Java, `Integer.MAX_VALUE - Integer.MIN_VALUE` tràn int. Tương tự, tổng hai số int có thể tràn trước khi so với target. Nhớ **nâng kiểu trước phép tính**, không đợi tới lúc gán kết quả vào long mới nâng kiểu.

Comparator phải xác định thứ tự nhất quán, không phụ thuộc biến toàn cục có thể đổi trong quá trình sort. Với hai khóa, nên định nghĩa quy tắc phá hòa rõ ràng và không đảo nhầm chiều của khóa phụ.

### Khóa nào phù hợp?

- Gom nhóm/tần suất: sắp theo khóa mà muốn nhóm.
- Merge intervals: sắp theo `start`, có thể phá hòa bằng `end`.
- Two-sum: sắp theo **giá trị số**, không theo originalIndex.
- Xử lý deadline: sắp theo **thời điểm kết thúc** hoặc deadline nếu chứng minh tham lam yêu cầu nó, không chỉ chọn tùy ý.
- Sweep line: sắp theo **tọa độ thời gian**; khi bằng thời gian, xử lý quy ước hòa phù hợp với loại khoảng.

Sai khóa so sánh có thể tạo mảng “được sắp” nhưng **không có bất biến mà bước xử lý cần**.

## 12. Khi nào không nên sắp trước?

**Bài phụ thuộc thứ tự gốc.** Ví dụ cần tổng đoạn con liên tiếp lớn nhất của `[5,-100,5]`. Kết quả đúng trên dãy gốc là 5. Nếu sắp thành `[-100,5,5]`, đoạn liên tiếp [5,5] có tổng 10, nhưng đoạn đó **không tồn tại trong dữ liệu gốc**. Đây là phản ví dụ trực tiếp cho việc sort làm thay đổi bài toán.

**Bài chỉ cần một thống kê tuyến tính.** Tìm min, max, tổng, kiểm tra tồn tại hay đếm điều kiện một lần thường làm O(n) bằng quét; sort O(n log n) là dư thừa.

**Bài online cập nhật liên tục.** Sau mỗi lần thêm/xóa, nếu phải trả lời truy vấn thứ tự ngay, sort lại toàn bộ có thể tốn nhiều lần O(n log n). Tùy yêu cầu, có thể dùng heap, cây cân bằng, Fenwick tree, segment tree hoặc một chỉ mục có hỗ trợ cập nhật.

**Bài phù hợp hash.** Two-sum một lần, đếm tần suất hoặc tra cứu tồn tại theo khóa thường có giải pháp hash O(n) kỳ vọng. Dùng hash nếu không cần thứ tự; dùng sort nếu các bước sau cần thứ tự hoặc muốn tránh một số chi phí bộ nhớ hash.

**Miền khóa nhỏ.** Với số nguyên trong miền nhỏ, counting array hoặc bucket có thể rẻ hơn sort so sánh. Phải tính giới hạn khóa và bộ nhớ, không áp dụng tùy tiện cho bản ghi có comparator phức tạp.

**Dữ liệu lớn hơn RAM.** Khi không nạp vừa vào RAM, chọn external sorting và quét theo các run trên đĩa có thể phù hợp hơn thuật toán in-memory. Chi phí I/O, buffer và số lượt đọc/ghi quan trọng không kém Big-O theo n.

## 13. Trường hợp biên và cách tự kiểm thử

| Trường hợp | Đầu vào mẫu | Kỳ vọng |
| --- | --- | --- |
| Không có phần tử | [] | Distinct=[], count≤x=0, không có two-sum |
| Một phần tử | [5] | Distinct=[5], không được dùng cùng chỉ số để ghép cặp |
| Mọi giá trị bằng nhau | [2,2,2] | Distinct=[2], count≤2=3 |
| Có số âm | [-1,2,-1,3] | Distinct=[-1,2,3] |
| Two-sum dùng hai giá trị bằng nhau | [3,3], target=6 | Có cặp ở hai chỉ số khác nhau |
| Two-sum không tồn tại | [1,2,3], target=10 | Không có cặp |
| Khoảng lồng nhau | [[1,10],[3,4]] | [[1,10]] |
| Khoảng đóng chạm đầu mút | [[1,2],[2,3]] | [[1,3]] |
| Không có khoảng | [] | Danh sách khoảng rỗng |
| Query dưới min | [-5,0,10], x=-6 | count≤x = 0 |
| Query trên max | [-5,0,10], x=11 | count≤x = 3 |
| Dữ liệu cực trị | [Integer.MIN_VALUE,Integer.MAX_VALUE] | Comparator và phép cộng không được tràn |

Để kiểm thử bằng **lời giải chuẩn (oracle)**:
1. Trên mảng nhỏ, loại trùng bằng `Set` rồi sắp các phần tử của tập để so danh sách.
2. Two-sum: duyệt mọi cặp chỉ số `i<j` và cộng bằng long. Nếu lời giải trả cặp nào đó, xác thực cả hai chỉ số, tổng và tính khác nhau; **không yêu cầu** trùng đúng cặp mà oracle tìm trước.
3. Merge intervals: kiểm tra đầu ra không chồng lấn, được sắp, và hợp các khoảng được bảo toàn; dùng một phiên bản chậm hơn trên tập nhỏ để đối chiếu.
4. Count≤x: đếm bằng vòng quét mảng gốc, so với upper bound trên mảng đã sắp.
5. Thử đầu vào đã sắp, đảo ngược, nhiều giá trị trùng, mảng rỗng, số âm, cực trị và nhiều truy vấn có cùng ngưỡng.

Các phép kiểm thử phát hiện lỗi cài đặt; **bất biến** giúp chứng minh đúng trên mọi đầu vào thỏa tiền điều kiện.

## 14. Sai lầm thường gặp

1. **Bỏ qua chi phí sort** khi báo độ phức tạp tổng.
2. **Sắp mất chỉ số gốc** nhưng lại trả vị trí trong mảng đã sắp như thể là vị trí ban đầu.
3. **Xóa phần tử trùng** trong khi đề cần bội số hoặc cần giữ từng bản ghi.
4. **Dùng two pointers khi chưa sắp** và không có tính đơn điệu để biện minh di chuyển con trỏ.
5. **Dùng upper bound như lower bound**, nhầm `<` với `<=` khi gặp nhiều khóa trùng.
6. **Quên quy ước đoạn đóng/nửa mở** khi gộp khoảng chạm đầu mút.
7. **Gán end thay vì max(end)** khi gặp khoảng lồng.
8. **Dùng comparator bằng phép trừ int**, gây overflow ở dữ liệu cực trị.
9. **Sort lại mỗi truy vấn** dù dữ liệu cố định và có thể tái sử dụng mảng sắp.
10. **Nhầm stable sort với khóa phụ**: ổn định giữ thứ tự gốc giữa các phần tử comparator xem là bằng nhau; khóa phụ thay đổi quan hệ so sánh.
11. **Cho rằng đã sort nghĩa là có thể làm mọi bước tham lam**: cần chứng minh riêng sự lựa chọn tham lam.
12. **Đếm độ phức tạp nhỏ hơn kích thước đầu ra** khi bài yêu cầu in số lượng cặp/đoạn rất lớn.

## 15. Tự luyện và đáp án

**Bài 1.** Sắp `[4,1,4,2,1,3]` rồi lấy các giá trị phân biệt và tần suất.

*Đáp án:* Sau sắp [1,1,2,3,4,4]; distinct [1,2,3,4]; tần suất 1:2, 2:1, 3:1, 4:2.

**Bài 2.** Cho [1,2,4,5,7,11] đã tăng, target=9. Hãy mô phỏng two pointers tới khi tìm cặp.

*Đáp án:* 1+11=12 quá lớn nên giảm right tới 7; 1+7=8 quá nhỏ nên tăng left tới 2; 2+7=9, có cặp (2,7).

**Bài 3.** Mảng [8,3,5,2,7,3] và target=12, đề yêu cầu hai chỉ số gốc. Cần giữ thông tin gì khi sort?

*Đáp án:* Cần giữ `(value,originalIndex)` hoặc ánh xạ tương đương, vì vị trí đã sắp không phải vị trí ban đầu. Một cặp đúng là giá trị (5,7) ở chỉ số (2,4).

**Bài 4.** Các đoạn đóng [[1,4],[2,3],[6,8],[8,11]] gộp thành gì?

*Đáp án:* [[1,4],[6,11]]. [2,3] nằm trong [1,4] nên không thu nhỏ đoạn; [6,8] và [8,11] chạm tại 8.

**Bài 5.** Có 100.000 số và 100.000 câu hỏi `countAtMost(x)`. So sánh quét lại mỗi câu với sort + binary search.

*Đáp án:* Quét có cận O(nq), tức khoảng 10 tỷ phép xét trong tình huống xấu; sort một lần + mỗi truy vấn binary search có cận O(n log n + q log n), phù hợp hơn cho dữ liệu tĩnh.

**Bài 6.** Vì sao không thể sắp [5,-100,5] trước khi tìm tổng đoạn con liên tiếp lớn nhất?

*Đáp án:* Sau sort [-100,5,5] có một đoạn [5,5] tổng 10 không tồn tại liên tiếp trong mảng gốc; đáp án gốc là 5.

**Bài 7.** Hai khoảng nửa mở [1,3) và [3,5) có giao nhau không? Có thể gộp thành [1,5) không?

*Đáp án:* Không giao nhau vì 3 không thuộc [1,3); nhưng hợp của chúng bằng [1,5), nên có thể gộp khi bài muốn biểu diễn hợp tối giản. Phải phân biệt “giao nhau” và “có thể gộp hợp”.

**Bài 8.** Chỉ cần số nhỏ nhất trong một triệu phần tử. Có nên sort trước không?

*Đáp án:* Không cần. Một lượt quét O(n) với O(1) bộ nhớ phụ tốt hơn việc sắp toàn bộ O(n log n) chỉ để lấy phần tử đầu.

## Kết luận

**Sort-first** là một phép tiền xử lý hữu ích khi thứ tự mới giúp sinh ra **bất biến đơn điệu**:

- Giá trị bằng nhau nằm liền kề → gom nhóm, đếm tần suất, loại trùng.
- Hai đầu trên mảng tăng → tìm cặp bằng two pointers.
- Khoảng được sắp theo start → gộp bằng một lượt quét.
- Dữ liệu đã tăng → truy vấn ngưỡng bằng lower/upper bound.
- Sự kiện đã sắp theo thời gian → sweep line với quy tắc hòa rõ ràng.

Điều quyết định là **chứng minh sắp không làm sai bài toán**, **chọn đúng khóa**, **giữ metadata cần thiết**, **đếm cả chi phí sort**, và **dùng thuật toán thay thế khi dữ liệu gốc/đặc tính online không cho phép sort**.
