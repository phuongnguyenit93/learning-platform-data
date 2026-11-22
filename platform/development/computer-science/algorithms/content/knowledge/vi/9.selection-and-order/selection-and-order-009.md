# Trộn nhiều dãy có thứ tự bằng hàng đợi ưu tiên

## 1. Bài toán và hợp đồng đầu vào

Cho k dãy đã được sắp **không giảm** (tăng dần, có thể bằng nhau). Dãy thứ i có n_i phần tử; tổng số phần tử là:

\[
N=\sum_{i=0}^{k-1}n_i.
\]

Yêu cầu: tạo một dãy kết quả chứa **đúng toàn bộ N phần tử**, với cả giá trị trùng lặp, theo thứ tự không giảm. Dãy đầu vào có thể rỗng. Không được giả định các dãy có cùng độ dài; cũng không được tự coi các dãy là đã sắp nếu hợp đồng đầu vào chưa nói rõ.

Ví dụ:

~~~text
S0 = [ 1, 4, 4, 9 ]
S1 = [ -2, 4, 10 ]
S2 = [ 1, 3, 4 ]
S3 = [ ]                  (dãy rỗng)

Kết quả = [ -2, 1, 1, 3, 4, 4, 4, 4, 9, 10 ]
~~~

Đây là bài toán **k-way merge**. Nếu k=2, có thể trộn bằng hai con trỏ trong O(n_0+n_1). Khi k lớn, dùng **hàng đợi ưu tiên (priority queue)**, triển khai bằng **min-heap**, để luôn lấy phần tử nhỏ nhất trong số các phần tử **đầu dãy chưa xử lý**.

Ứng dụng thường gặp: hợp nhất nhiều tệp log đã sắp theo thời gian, ghép kết quả từ nhiều máy chủ đã sắp theo khóa, trộn danh sách sự kiện theo timestamp, hợp nhất các đoạn đã sắp trong thuật toán external merge sort, hoặc gom kết quả truy vấn nhiều luồng.

**Phạm vi bài học:** các dãy nguồn đã sắp không giảm theo cùng một thứ tự; ví dụ dùng các giá trị int. Nếu dữ liệu là bản ghi, phải định nghĩa một comparator thống nhất cho mọi nguồn và cả heap kết quả.

## 2. Tại sao chỉ cần xét phần tử đứng đầu của từng dãy?

Giả sử S_i đã được sắp tăng và ta đã lấy đi p_i phần tử đầu tiên. Phần tử nhỏ nhất **còn lại** trong dãy S_i là S_i[p_i], nếu p_i chưa vượt độ dài dãy.

Vì vậy, **phần tử nhỏ nhất trên tất cả dữ liệu chưa xử lý** phải nằm trong tập các phần tử đầu còn lại của những dãy chưa hết. Không cần đặt mọi phần tử vào heap; tối đa một phần tử từ mỗi dãy là đủ.

Ta lưu một **nút heap** với ba thông tin:
- **value**: giá trị dùng để so sánh.
- **source**: chỉ số dãy gốc, để biết cần lấy phần tử tiếp theo ở đâu.
- **index**: vị trí phần tử trong dãy gốc, để xác định chính xác phần tử tiếp theo.

Có k dãy, nhưng chỉ m≤k dãy không rỗng đang đóng góp phần tử vào heap. Khi trộn, kích thước heap không vượt quá m.

Một PriorityQueue theo thứ tự **nhỏ nhất trước (min-heap)** cho phép:
- **peek**: xem phần tử đứng đầu heap, không xóa; O(1).
- **poll/remove**: lấy và xóa phần tử nhỏ nhất; O(log(m+1)) trong giới hạn kích thước heap m.
- **offer/add**: chèn một phần tử mới; O(log(m+1)).

Cấu trúc heap không giữ toàn bộ phần tử trong thứ tự tăng khi ta duyệt nội bộ mảng chứa nó: **chỉ phần tử đầu heap có bảo đảm ưu tiên nhỏ nhất**. Không duyệt nội bộ PriorityQueue để lấy một dãy đã sắp!

## 3. Thuật toán một đầu dãy trong heap

### Khởi tạo

Với từng dãy S_i:
1. Nếu S_i không rỗng, đưa nút (S_i[0], i, 0) vào min-heap.
2. Nếu S_i rỗng, không đưa gì vào heap.

Sau bước này, heap chứa **đúng một đầu chưa xử lý** của mỗi dãy không rỗng.

### Lặp cho tới khi heap rỗng

1. Lấy nút nhỏ nhất (x, i, p) khỏi heap.
2. Ghi x vào dãy kết quả (và có thể giữ thông tin i,p nếu cần nguồn gốc).
3. Nếu p+1 vẫn thuộc S_i, chèn nút (S_i[p+1], i, p+1) vào heap.
4. Lặp lại.

Không lấy thêm phần tử từ các dãy khác ở bước 3. Chỉ dãy vừa bị lấy mất đầu mới cần **bổ sung đầu kế tiếp**. Mọi dãy còn lại vẫn có nút đầu phù hợp ở heap.

Giả mã:

~~~text
heap = min-priority-queue ordered by value
for source = 0 .. k-1:
    if source sequence is nonempty:
        heap.offer((sequence[source][0], source, 0))

result = []
while heap is not empty:
    (value, source, index) = heap.poll()
    result.append(value)
    nextIndex = index + 1

    if nextIndex < sequence[source].length:
        heap.offer(
            (sequence[source][nextIndex], source, nextIndex)
        )

return result
~~~

**Bất biến then chốt:** trước mỗi vòng lặp, với mỗi dãy còn phần tử chưa xuất, heap chứa **chính xác một nút**, đại diện cho phần tử đầu tiên chưa xuất của dãy đó; không chứa nút nào của dãy đã hết. Khi lấy một nút và chèn phần tử kế tiếp từ đúng nguồn, bất biến này được duy trì.

## 4. Ví dụ chi tiết với giá trị trùng và dãy rỗng

Xét bốn nguồn:

~~~text
S0 = [1, 4, 4, 9]
S1 = [-2, 4, 10]
S2 = [1, 3, 4]
S3 = []
~~~

Ban đầu heap chứa S0[0]=1, S1[0]=-2 và S2[0]=1. S3 không có nút vì rỗng. Để minh họa **thứ tự xác định giữa các phần tử cùng giá trị**, ta chọn ưu tiên:
1. value tăng dần.
2. Nếu bằng value, source tăng dần.
3. Nếu vẫn bằng nhau, index tăng dần.

| Bước lấy | Phần tử được lấy | Nút bổ sung từ cùng nguồn | Kết quả sau bước |
|---|---|---|---|
| 1 | -2 từ S1[0] | 4 từ S1[1] | [-2] |
| 2 | 1 từ S0[0] | 4 từ S0[1] | [-2,1] |
| 3 | 1 từ S2[0] | 3 từ S2[1] | [-2,1,1] |
| 4 | 3 từ S2[1] | 4 từ S2[2] | [-2,1,1,3] |
| 5 | 4 từ S0[1] | 4 từ S0[2] | [-2,1,1,3,4] |
| 6 | 4 từ S0[2] | 9 từ S0[3] | [-2,1,1,3,4,4] |
| 7 | 4 từ S1[1] | 10 từ S1[2] | [-2,1,1,3,4,4,4] |
| 8 | 4 từ S2[2] | Không còn | [-2,1,1,3,4,4,4,4] |
| 9 | 9 từ S0[3] | Không còn | [-2,1,1,3,4,4,4,4,9] |
| 10 | 10 từ S1[2] | Không còn | [-2,1,1,3,4,4,4,4,9,10] |

Các giá trị 4 xuất hiện **bốn lần** trong kết quả: hai từ S0, một từ S1 và một từ S2. Không có bước nào tự xóa trùng.

Khi so sánh chỉ dựa vào value, những nút cùng value có thể được heap trả theo thứ tự không xác định: Java PriorityQueue **không cam kết ổn định** cho phần tử cùng ưu tiên. Nếu ứng dụng cần thứ tự tái lập giữa các nguồn hoặc muốn giữ thứ tự của các bản ghi đồng khóa, cần quy định và dùng **khóa phụ** như source/index. Chính sách value–source–index ở trên tạo thứ tự rõ ràng; với cùng value, dãy nguồn có chỉ số nhỏ hơn được ưu tiên. Nó không phải quy luật chung bắt buộc của k-way merge: đó là một **lựa chọn về tie-breaking**.

## 5. Chứng minh tính đúng đắn

Ta cần chứng minh hai điều: mọi bước xuất phần tử nhỏ nhất còn lại và cuối cùng không thiếu/không thừa phần tử.

### 5.1. Tính nhỏ nhất ở mỗi bước

Giả sử mỗi dãy nguồn đã được sắp không giảm. Ở một thời điểm bất kỳ, gọi h_i là **đầu chưa xử lý** của dãy i. Mọi phần tử còn lại trong dãy i đều **≥ h_i**. Vì thế phần tử nhỏ nhất trong hợp tất cả phần tử chưa xử lý phải là một trong các h_i.

Theo bất biến, min-heap chứa đúng các h_i hiện tồn tại. Nút lấy bởi poll chính là một nút có value nhỏ nhất trong các h_i; do đó value được xuất ra là **nhỏ nhất toàn cục** trong phần chưa xử lý.

Khi xuất một phần tử nhỏ nhất và lặp lại, dãy kết quả không giảm. Nếu có nhiều phần tử cùng value, bộ so sánh khóa phụ chỉ chọn thứ tự của những phần tử bằng nhau, không làm sai thứ tự theo value.

### 5.2. Không mất phần tử, không lặp sai

Ban đầu, mỗi dãy không rỗng đóng góp phần tử có index 0. Khi xuất phần tử index p của một nguồn, thuật toán chỉ chèn index p+1 nếu tồn tại. Vì vậy, trong từng nguồn, các index được xuất tuần tự **0,1,...,n_i−1**, mỗi index đúng một lần.

Mỗi lượt lấy ra làm số phần tử chưa xuất giảm đúng 1. Sau tổng cộng N lần lấy ra, tất cả nguồn đã cạn, heap rỗng, và kết quả chứa đúng N phần tử ban đầu (kể cả bản sao có cùng giá trị).

Từ hai lập luận, thuật toán trả về đúng phép trộn có thứ tự của toàn bộ k dãy.

### Điều kiện của chứng minh

- Mọi nguồn phải **đã được sắp theo cùng comparator**.
- Comparator phải xác định thứ tự nhất quán. Một comparator không bắc cầu hoặc thay đổi trong khi trộn có thể làm sai kết quả.
- Nếu nguồn thay đổi dữ liệu trong lúc heap lưu một nút đại diện, bất biến đầu dãy có thể không còn đúng. Với dữ liệu biến động, phải thiết kế giao thức đồng bộ hoặc snapshot riêng.

## 6. Java 17+: chương trình độc lập

Chương trình dùng **java.util.PriorityQueue** (min-heap theo Comparator). Mỗi nút lưu value, source và index dưới dạng record. Hàm merge trả cả nguồn gốc để thấy rõ quy tắc xử lý tie; nếu chỉ cần giá trị, có thể trích trường value từ kết quả.

**Hợp đồng dữ liệu:** mảng ngoài không được null; mỗi dãy con không được null; mỗi dãy con phải sắp không giảm. Dãy con rỗng hợp lệ, kể cả tất cả đều rỗng. Ví dụ kiểm tra tính đã sắp trước khi trộn để tránh âm thầm tạo đầu ra sai.

Lưu tệp **KWayPriorityQueueMergeDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public final class KWayPriorityQueueMergeDemo {
    private KWayPriorityQueueMergeDemo() {
    }

    record Entry(int value, int source, int index) {
    }

    public static List<Entry> merge(int[][] sequences) {
        if (sequences == null) {
            throw new IllegalArgumentException("Sequences must not be null");
        }

        long total = 0;
        for (int source = 0; source < sequences.length; source++) {
            int[] current = sequences[source];
            if (current == null) {
                throw new IllegalArgumentException(
                        "Null sequence at " + source);
            }

            for (int i = 1; i < current.length; i++) {
                if (current[i] < current[i - 1]) {
                    throw new IllegalArgumentException(
                            "Unsorted sequence at " + source);
                }
            }

            total += current.length;
            if (total > Integer.MAX_VALUE) {
                throw new IllegalArgumentException(
                        "Result too large for an in-memory Java list");
            }
        }

        // Không dùng phép trừ hai int để so sánh: có thể tràn số.
        // Khóa phụ đảm bảo thứ tự xác định khi value trùng nhau.
        Comparator<Entry> order =
                Comparator.comparingInt(Entry::value)
                        .thenComparingInt(Entry::source)
                        .thenComparingInt(Entry::index);
        PriorityQueue<Entry> heap = new PriorityQueue<>(order);

        // Chỉ đưa đầu của mỗi dãy không rỗng vào heap.
        for (int source = 0; source < sequences.length; source++) {
            if (sequences[source].length > 0) {
                heap.offer(new Entry(sequences[source][0], source, 0));
            }
        }

        List<Entry> result = new ArrayList<>((int) total);
        while (!heap.isEmpty()) {
            Entry smallest = heap.remove();
            result.add(smallest);

            int nextIndex = smallest.index() + 1;
            int source = smallest.source();
            if (nextIndex < sequences[source].length) {
                heap.offer(new Entry(
                        sequences[source][nextIndex], source, nextIndex));
            }
        }
        return result;
    }

    private static List<Integer> values(List<Entry> entries) {
        return entries.stream().map(Entry::value).toList();
    }

    private static List<String> origins(List<Entry> entries) {
        return entries.stream()
                .map(e -> e.value() + "@S" + e.source()
                        + "[" + e.index() + "]")
                .toList();
    }

    public static void main(String[] args) {
        int[][] sources = {
            {1, 4, 4, 9},
            {-2, 4, 10},
            {1, 3, 4},
            {}
        };

        List<Entry> merged = merge(sources);
        System.out.println("Values: " + values(merged));
        System.out.println("Origins: " + origins(merged));

        System.out.println("All empty: "
                + values(merge(new int[][] {{}, {}})));
        System.out.println("One source: "
                + values(merge(new int[][] {{-5, -5, 8}})));

        try {
            merge(new int[][] {{3, 1}});
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid input: " + ex.getMessage());
        }
    }
}
~~~

Lệnh chạy với JDK 17 trở lên:

~~~bash
javac KWayPriorityQueueMergeDemo.java
java KWayPriorityQueueMergeDemo
~~~

Stdout:

~~~text
Values: [-2, 1, 1, 3, 4, 4, 4, 4, 9, 10]
Origins: [-2@S1[0], 1@S0[0], 1@S2[0], 3@S2[1], 4@S0[1], 4@S0[2], 4@S1[1], 4@S2[2], 9@S0[3], 10@S1[2]]
All empty: []
One source: [-5, -5, 8]
Invalid input: Unsorted sequence at 0
~~~

Đọc mã:
- **Đầu vào được xác minh trước:** dãy null và dãy không tăng theo hợp đồng bị từ chối; dãy không giảm cho phép phần tử bằng nhau.
- **Heap chỉ chứa tối đa một Entry mỗi nguồn:** khi lấy phần tử, thêm phần tử tiếp theo từ đúng nguồn ấy.
- **Comparator.comparingInt / thenComparingInt** so sánh an toàn cả Integer.MIN_VALUE và Integer.MAX_VALUE; không trừ hai int làm khóa.
- **Origins** cho thấy bốn bản sao giá trị 4 thực sự đến từ các vị trí khác nhau. source và index không được mất trong quá trình trộn.
- **Empty** được xử lý bằng điều kiện ở bước khởi tạo; nếu tất cả dãy rỗng hoặc không có dãy nào, heap rỗng và kết quả là danh sách rỗng.
- **Một nguồn:** kết quả giống dãy nguồn, không cần trường hợp riêng.
- Danh sách result lưu N bản ghi Entry, nên nó sử dụng O(N) bộ nhớ. Nếu chỉ cần ghi kết quả ra tệp/luồng theo thứ tự, có thể xuất từng value khi poll để tránh giữ toàn bộ result.

Lưu ý: tính hợp lệ của đầu vào chỉ được kiểm tra một lần ở đầu hàm. Nếu một luồng khác sửa các mảng nguồn trong khi merge đang chạy, kết quả có thể không đúng; ví dụ xem dữ liệu là **không đổi** trong suốt lượt trộn.

## 7. Phân tích độ phức tạp

Gọi k là số dãy, m≤k là số dãy không rỗng, N là tổng số phần tử.

**Khởi tạo:**
- Duyệt k nguồn và đặt phần tử đầu của mỗi nguồn không rỗng vào heap.
- Nếu phải **kiểm tra thứ tự** từng dãy như trong mã Java, bước kiểm tra quét N phần tử: O(N+k).
- Chèn tối đa m nút đầu bằng offer có thể tốn O(m log(m+1)); điều này nằm trong tổng chi phí của thuật toán khi N≥m.

**Trong vòng lặp:** có đúng N lần poll. Sau mỗi lần poll, có **tối đa một lần offer** phần tử tiếp theo. Vì heap có nhiều nhất m phần tử, mỗi thao tác có chi phí O(log(m+1)); tổng là O(N log(m+1)).

**Tổng thời gian** với việc kiểm tra nguồn:

\[
O(k+N\log(k+1)).
\]

Viết **O(N log k)** thường được chấp nhận khi k≥2 và đang xét các dãy không rỗng, nhưng biểu thức có \(k+1\) và cộng k rõ hơn ở biên k=0, k=1 hoặc khi có rất nhiều dãy rỗng. Không nên nói O(N) bất kể k nếu số dãy lớn và chi phí quản lý các đầu dãy vẫn cần tính.

**Bộ nhớ phụ trợ của thuật toán trộn:**
- Heap giữ tối đa m≤k Entry: **O(k)**.
- Nếu lưu kết quả vào List<Entry>, cần **O(N)** thêm cho danh sách/đối tượng kết quả; tổng O(k+N).
- Nếu mọi nguồn là iterator/stream đã sắp và ta xuất ngay từng phần tử, có thể giữ O(k) nút đầu trong heap, **chưa tính bộ đệm của nguồn và nơi nhận**. Đây là lý do k-way merge hữu ích cho dữ liệu rất lớn trên đĩa.

Trong Java, PriorityQueue thực tế có chi phí cấp phát nút, bộ nhớ tham chiếu và tăng sức chứa mảng; các hằng số ấy không xuất hiện trong ký hiệu Big O nhưng ảnh hưởng hiệu năng thực.

## 8. So sánh các chiến lược trộn

| Cách làm | Ý tưởng | Thời gian điển hình | Đánh đổi |
|---|---|---|---|
| Quét các đầu còn lại | Mỗi lần tìm nhỏ nhất bằng cách duyệt k con trỏ | O(Nk) | Đơn giản, có thể hợp lý khi k rất nhỏ |
| Đưa tất cả vào mảng rồi sắp xếp | Nối toàn bộ N phần tử, dùng sort | O(N log N) | Không tận dụng đủ việc nguồn đã được sắp; cần giữ toàn bộ |
| Trộn từng dãy lần lượt vào kết quả | Merge hai dãy, rồi merge với dãy kế tiếp | Có thể O(Nk) | Dãy kết quả bị quét lặp lại, phụ thuộc phân bố kích thước |
| Trộn theo cây cân bằng | Ghép từng cặp, rồi ghép các kết quả theo tầng | O(N log(k+1)) | Có thể thuận lợi cho batch trên các mảng |
| Min-heap giữ một đầu mỗi nguồn | Chọn đầu nhỏ nhất, bổ sung đầu kế tiếp từ nguồn đó | O(k+N log(k+1)) | Tiện cho iterator và streaming; dùng heap O(k) |

Quét tuyến tính k đầu không nhất thiết “sai”; với k=2, phép merge hai con trỏ đơn giản thường hiệu quả và không cần heap. Lợi thế của heap rõ hơn khi **k tăng** và không muốn mỗi lần xuất lại so tất cả các đầu dãy.

Ngoài ra, nếu các dãy nguồn nằm trên nhiều máy hoặc tệp, thời gian I/O và độ trễ lấy phần tử tiếp theo có thể chi phối tổng thời gian; không được nhầm độ phức tạp CPU của heap với thời gian thực tế toàn hệ thống.

## 9. Trộn bản ghi có nhiều khóa, phần tử trùng và tính ổn định

Với bản ghi, chẳng hạn (timestamp, source, sequenceNumber, payload), heap nên chứa **bản ghi và thông tin nguồn**. Comparator phải dùng đúng khóa mà từng dãy nguồn cũng đã dùng để sắp.

Một cách thiết kế khóa ghép:
1. timestamp tăng dần;
2. nếu timestamp bằng nhau, source tăng dần;
3. nếu vẫn bằng nhau, sequenceNumber tăng dần.

Khi dùng nguồn sắp theo timestamp và sequenceNumber, trộn theo timestamp–source–sequenceNumber vẫn không giảm theo timestamp. Tuy nhiên, nếu muốn kết quả có **thứ tự toàn cục theo timestamp rồi sequenceNumber** bỏ qua source, thì các dãy nguồn cũng phải được sắp nhất quán theo hai khóa đó; không thể bổ sung một khóa phụ tùy ý vào comparator và mặc định mọi nguồn vẫn có thứ tự theo comparator mới.

**Ổn định (stable) có nhiều ý nghĩa cần làm rõ:**
- Bên trong một nguồn, thuật toán luôn xuất index theo thứ tự, nên giữ nguyên thứ tự của các bản ghi có cùng khóa ở nguồn đó.
- Giữa các nguồn, khái niệm “thứ tự ban đầu” không hiển nhiên nếu các dãy vốn là các luồng độc lập. Tie-break theo source/index quy định một thứ tự xác định, nhưng là **chính sách nghiệp vụ**, không phải điều bắt buộc của phép trộn.
- Java PriorityQueue không đảm bảo FIFO giữa những Entry mà comparator cho bằng 0. Nếu cần một thứ tự cụ thể, hãy đưa khóa phụ vào comparator hoặc lưu số thứ tự toàn cục đã xác định.
- Không thay phép so sánh bằng phép trừ trên số nguyên nếu có thể tràn; dùng Integer.compare, Long.compare hoặc Comparator.comparingInt/comparingLong.

**Không xóa trùng:** nếu nhiều nguồn cùng chứa một giá trị, tất cả bản sao phải xuất hiện. Bài toán “hợp nhất và loại trùng” khác k-way merge chuẩn; nếu cần distinct, sau khi lấy ra có thể bỏ những giá trị bằng với giá trị vừa xuất trước đó, nhưng lúc ấy số phần tử kết quả không còn là N và phải điều chỉnh đặc tả.

## 10. Mở rộng sang dữ liệu lớn và iterator

Nếu mỗi nguồn là **một iterator đang trả phần tử theo thứ tự**, không cần đọc hết toàn bộ dữ liệu để bắt đầu:
1. Tạo heap với phần tử đầu tiên từ mỗi iterator còn dữ liệu.
2. Lấy phần tử nhỏ nhất; xuất ngay tới nơi nhận.
3. Chỉ yêu cầu phần tử mới từ **iterator của phần tử vừa lấy**; giữ thông tin định danh nguồn để biết lấy tiếp ở đâu.
4. Khi iterator cạn, không chèn thêm nút.

Số mục cần giữ trong heap vẫn tối đa k. Trong hệ thống thực tế có thể cần bộ đệm đọc trước cho từng tệp, nên bộ nhớ thực tế là O(k) nút heap **cộng các buffer I/O**. Với nguồn mạng, còn cần quản lý lỗi kết nối, nguồn tạm dừng và thứ tự sự kiện đến muộn; min-heap một đầu mỗi luồng **không bảo đảm** thứ tự thời gian đúng nếu luồng không thực sự cung cấp đầu ra đã sắp hoặc có phần tử muộn chưa được công bố.

**External merge sort:** khi không đủ RAM để sắp toàn bộ dữ liệu, ta chia dữ liệu thành các run đã sắp trên đĩa. K-way merge sau đó dùng một đầu đọc từ mỗi run để xuất ra một run lớn đã sắp. Độ phức tạp I/O phụ thuộc số run, bộ đệm và kích thước khối đọc/ghi; không suy ra chi phí đĩa chỉ từ O(N log k) thao tác heap.

**Luồng vô hạn:** thuật toán có thể liên tục phát đầu ra nhỏ nhất nếu mỗi nguồn cung cấp phần tử theo thứ tự và luôn có đầu của các nguồn cần so sánh. Nếu một nguồn có thể chứa phần tử nhỏ hơn nhưng chưa xuất hiện do bị trì hoãn, không thể công bố một thứ tự toàn cục chắc chắn nếu thiếu giao thức watermark/giới hạn trễ thích hợp.

## 11. Lỗi thường gặp và ca kiểm thử

1. **Đưa toàn bộ phần tử lên heap cùng lúc:** vẫn có thể tạo kết quả đúng, nhưng heap tăng tới O(N), không tận dụng tính đã sắp của từng nguồn.
2. **Chỉ lưu value, mất source/index:** không biết bổ sung phần tử tiếp theo từ dãy nào, trừ khi thêm cơ chế khác tương đương.
3. **Quên chèn phần tử kế tiếp sau poll:** kết quả chỉ chứa vài đầu ban đầu, thiếu dữ liệu.
4. **Chèn phần tử kế tiếp từ tất cả nguồn:** phá bất biến một đầu mỗi nguồn và đưa nhiều phần tử không cần thiết vào heap.
5. **Nguồn chưa sắp:** một phần tử nhỏ nằm phía sau phần tử lớn trong cùng nguồn, nhưng heap không thấy nó đúng lúc; kết quả có thể sai.
6. **Nhầm Java PriorityQueue là danh sách đã sắp:** chỉ phần tử ở đỉnh heap có bảo đảm ưu tiên nhỏ nhất.
7. **Tin rằng heap ổn định khi value trùng:** Java không bảo đảm thứ tự các phần tử comparator trả 0; cần khóa phụ phù hợp.
8. **Dùng comparator kiểu (a,b) -> a.value-b.value:** phép trừ int có thể tràn, đảo thứ tự; dùng comparingInt hoặc Integer.compare.
9. **Không xử lý dãy rỗng hoặc k=0:** chỉ chèn đầu khi nguồn không rỗng; heap rỗng trả kết quả rỗng.
10. **Không tách bộ nhớ heap với bộ nhớ kết quả:** heap O(k) nhưng List kết quả O(N); nếu xuất streaming có thể giảm bộ nhớ cần giữ.
11. **Sửa nguồn trong lúc trộn:** nút đã lấy từ nguồn không còn phản ánh thứ tự mới; cần nguồn ổn định hoặc đồng bộ rõ.
12. **Sai độ phức tạp với biên k=1:** ghi O(N log k) sẽ cho log 1=0; dùng O(k+N log(k+1)) hoặc nói riêng trường hợp một nguồn.

**Các ca thử tối thiểu:**
- Không có nguồn (k=0), một nguồn rỗng, nhiều nguồn đều rỗng.
- Một nguồn đã sắp, nhiều nguồn độ dài khác nhau, nguồn có một phần tử.
- Âm, 0, dương; nhiều giá trị trùng cả trong và giữa các nguồn.
- Mỗi nguồn toàn một giá trị; số nguyên Integer.MIN_VALUE/Integer.MAX_VALUE.
- Nguồn không sắp, dãy null, mảng ngoài null (nếu API yêu cầu từ chối).
- Sinh ngẫu nhiên các dãy, sắp từng dãy bằng Arrays.sort rồi trộn; đối chiếu kết quả với việc nối tất cả phần tử và Arrays.sort, đồng thời kiểm tra kích thước kết quả bằng N.
- Với phần tử dạng bản ghi, kiểm thử riêng tính không đổi thứ tự nội bộ mỗi nguồn và chính sách tie-break giữa các nguồn.

## 12. Tự kiểm tra

**Câu 1.** Vì sao sau mỗi lần poll chỉ thêm phần tử tiếp theo **từ một nguồn**?

**Đáp án:** Chỉ nguồn của phần tử vừa bị lấy mới mất đại diện trong heap. Các nguồn khác vẫn đang có đúng một phần tử đầu chưa xuất; chèn thêm của chúng sẽ phá bất biến.

**Câu 2.** Với k dãy đã sắp, tại sao heap có kích thước tối đa k mà không phải N?

**Đáp án:** Với mỗi dãy còn dữ liệu, chỉ phần tử đầu chưa xuất mới có thể là phần tử nhỏ nhất của dãy đó; các phần tử phía sau được bảo đảm không nhỏ hơn đầu.

**Câu 3.** Tại sao O(N log k) không phải cách viết chính xác nhất nếu k=0 hoặc k=1?

**Đáp án:** log 0 không xác định, log 1 bằng 0 nhưng vẫn cần duyệt và xuất N phần tử. Viết O(k+N log(k+1)) tránh hai trường hợp biên; khi k lớn, cách viết quen thuộc O(N log k) vẫn hữu ích.

**Câu 4.** Nếu hai nguồn đều chứa giá trị 7, PriorityQueue có luôn lấy nguồn có chỉ số nhỏ hơn trước không?

**Đáp án:** Không, nếu comparator chỉ xét value. Muốn thứ tự đó, phải thêm source vào comparator làm khóa phụ, như chương trình Java đã minh họa.

**Câu 5.** Một nguồn chứa [1,9,3] có thể dùng trực tiếp với thuật toán không?

**Đáp án:** Không, vì nguồn chưa sắp không giảm. Phần tử 3 bị giấu phía sau 9; khi cần phát 3, heap chỉ nhìn thấy 9 nên có thể xuất sai thứ tự. Phải sắp nguồn trước hoặc đổi thuật toán.

**Ghi nhớ:** Trong k-way merge, min-heap chỉ cần giữ **một đầu chưa xuất của mỗi dãy**. Mỗi lần lấy nhỏ nhất, ghi kết quả và **bổ sung đầu mới từ đúng nguồn đó**. Bất biến này vừa chứng minh tính đúng vừa tạo thời gian O(k+N log(k+1)) với heap O(k).
