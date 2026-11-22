# Heap và hàng đợi ưu tiên để chọn phần tử tốt nhất

Nhiều thuật toán thường xuyên cần trả lời một câu hỏi: **“Trong số những ứng viên hiện có, phần tử nào tốt nhất theo một tiêu chí đã định?”** Ví dụ: xử lý tác vụ khẩn cấp nhất, lấy khoảng thời gian kết thúc sớm nhất, chọn đỉnh có khoảng cách tạm thời nhỏ nhất, hoặc lấy phần tử nhỏ nhất trong nhiều dãy đã sắp xếp.

Một cách làm là mỗi lần lại duyệt tất cả ứng viên để tìm phần tử tốt nhất. Tuy đơn giản, cách này tốn thời gian nếu thao tác “thêm ứng viên” và “lấy ứng viên tốt nhất” diễn ra liên tục. **Hàng đợi ưu tiên** (priority queue) mô tả các thao tác cần có; **heap** là một cách cài đặt rất phổ biến để hỗ trợ những thao tác đó hiệu quả.

Điểm cốt lõi là xác định **“tốt nhất” nghĩa là gì**, bảo toàn đúng thứ tự ưu tiên khi dữ liệu thay đổi, và chứng minh việc luôn lấy phần tử ưu tiên nhất thực sự phù hợp với thuật toán tổng thể.

## 1. Phân biệt hàng đợi ưu tiên và heap

### 1.1. Hàng đợi ưu tiên là giao diện thao tác trừu tượng

Hàng đợi thông thường (FIFO) lấy phần tử đã vào trước. Hàng đợi ưu tiên lấy phần tử đứng đầu theo **quan hệ ưu tiên** do bài toán định nghĩa, bất kể phần tử ấy được thêm trước hay sau.

Các thao tác chính:

- **insert / offer:** thêm một ứng viên cùng khóa ưu tiên của nó.
- **peek / find-min hoặc find-max:** xem ứng viên tốt nhất mà chưa xóa.
- **extract-min / extract-max, poll:** lấy và xóa ứng viên tốt nhất.
- **isEmpty / size:** kiểm tra số ứng viên đang có.

Tùy ứng dụng còn cần xóa phần tử bất kỳ, đổi mức ưu tiên, tìm một phần tử theo danh tính; những thao tác này **không được mọi triển khai priority queue hỗ trợ hiệu quả**.

“Ưu tiên cao hơn” không nhất thiết là số lớn hơn:
- Bệnh nhân có **mức khẩn cấp lớn nhất** có thể được xử lý trước (max-priority).
- Đường đi có **khoảng cách tạm thời nhỏ nhất** được xét trước (min-priority).
- Công việc có **deadline sớm nhất** đứng trước.
- Khi hai khóa bằng nhau, bài toán có thể yêu cầu quy tắc phụ như “đến trước xử lý trước”.

Muốn dùng đúng cấu trúc, phải nêu rõ **khóa**, **chiều so sánh** và **cách xử lý hòa**.

### 1.2. Heap là cấu trúc lưu trữ có bất biến

**Binary heap** là cây nhị phân **gần đầy theo từng tầng** (complete binary tree), thường lưu bằng mảng. Nó duy trì tính chất cục bộ:

- **Min-heap:** khóa của nút cha **không lớn hơn** khóa của các nút con.
- **Max-heap:** khóa của nút cha **không nhỏ hơn** khóa của các nút con.

Từ bất biến này, **gốc là phần tử tốt nhất**, nhưng các phần tử còn lại **không được sắp xếp hoàn toàn**. Ví dụ mảng biểu diễn min-heap có thể là \`[1, 2, 6, 7]\`: đây là heap hợp lệ dù không có cam kết thứ tự tăng dần giữa các nhánh.

Với chỉ số mảng bắt đầu từ 0:
- Nút cha của i > 0: \`parent(i) = (i - 1) / 2\` (chia lấy phần nguyên).
- Con trái: \`left(i) = 2 * i + 1\`.
- Con phải: \`right(i) = 2 * i + 2\`.
- Nút con chỉ tồn tại nếu chỉ số của nó nhỏ hơn n.

Không cần lưu con trỏ trái/phải của từng nút; tính chất cây gần đầy giúp cách đánh số mảng liên tục, tiết kiệm overhead liên kết.

## 2. Vì sao heap giúp chọn phần tử tốt nhất nhanh?

Giả sử đang có n ứng viên:

| Cách lưu ứng viên | Thêm phần tử | Xem phần tử tốt nhất | Lấy và xóa tốt nhất |
| --- | ---: | ---: | ---: |
| Mảng/danh sách chưa sắp xếp | O(1) cuối dãy (amortized với mảng động) | O(n) | O(n) để tìm (và xóa phù hợp) |
| Mảng/danh sách luôn sắp xếp | O(n) nếu phải dời phần tử | O(1) ở đầu/cuối thích hợp | O(1) nếu xóa từ đầu/cuối không cần dời |
| Binary heap | O(log n) | O(1) | O(log n) |

Bảng mô tả chi phí tiệm cận trong cách tổ chức dữ liệu phù hợp. Nếu cần xóa từ **đầu** ArrayList thì dịch chuyển mất O(n), còn nếu giữ giá trị tốt nhất ở **cuối** mảng đã sắp xếp, thao tác xóa cuối có thể O(1). Sự lựa chọn biểu diễn và đầu lấy dữ liệu phải nhất quán.

Heap dùng **O(n)** bộ nhớ để chứa n phần tử. Dựng heap từ mảng có sẵn bằng cách hiệu chỉnh từ các nút không phải lá ngược lên gốc (**bottom-up heapify**) tốn **O(n)**, dù lặp lại từng thao tác offer từ một heap rỗng có thể tốn O(n log n).

Vì sao bottom-up heapify là O(n)? Phần lớn nút nằm gần lá nên cần rất ít bước đi xuống; chỉ một số ít nút gần gốc có thể đi xuống nhiều tầng. Cộng chi phí theo chiều cao cho toàn bộ nút cho tổng thời gian tuyến tính, không phải “n nút × log n” trong trường hợp này.

### 2.1. Thêm phần tử: đẩy lên (sift up)

Đưa phần tử mới vào vị trí cuối mảng để giữ dạng cây gần đầy. Nếu nó đứng trước nút cha theo quan hệ ưu tiên, hoán đổi với cha và tiếp tục đi lên. Dừng khi không còn vi phạm hoặc lên đến gốc.

Ví dụ min-heap với các khóa 7, 2, 6, 1:
1. Thêm 7 → \`[7]\`.
2. Thêm 2 → \`[2, 7]\` (2 đổi chỗ với 7).
3. Thêm 6 → \`[2, 7, 6]\`.
4. Thêm 1 → ban đầu \`[2, 7, 6, 1]\`, đẩy lên qua 7 rồi 2 → \`[1, 2, 6, 7]\`.

Mỗi lần đẩy lên tối đa chiều cao cây là O(log n).

### 2.2. Lấy phần tử tốt nhất: đẩy xuống (sift down)

Gốc là phần tử được trả về. Đưa phần tử cuối mảng lên gốc, giảm kích thước heap, rồi so sánh với hai con. Nếu vi phạm thứ tự, đổi chỗ với **nút con có ưu tiên tốt nhất** và tiếp tục đi xuống.

Từ \`[1, 2, 6, 7]\`:
1. Lấy 1; tạm đưa 7 lên gốc: \`[7, 2, 6]\`.
2. Trong hai con 2 và 6, con 2 tốt hơn; đổi 7 và 2 → \`[2, 7, 6]\`.
3. Heap lại hợp lệ; phần tử ưu tiên nhất tiếp theo là 2.

Nếu heap có một phần tử, lấy nó sẽ khiến heap rỗng; không cần bước đổi chỗ nào. Nếu có giá trị trùng, bất biến dùng ≤ hoặc ≥ nên nhiều cấu hình hợp lệ; heap **không tự đảm bảo thứ tự xuất hiện giữa các phần tử cùng ưu tiên**.

## 3. Chọn đúng khóa so sánh và quy tắc hòa

Đối với bài “xử lý tác vụ khẩn cấp”, cần làm rõ:
- Số ưu tiên nhỏ hơn hay lớn hơn được chọn trước?
- Nếu bằng nhau, tác vụ đến trước hay có mã nhỏ hơn được chọn trước?
- Mức ưu tiên có thay đổi sau khi tác vụ đã vào hàng đợi hay không?
- Có quy định thời gian chờ tối đa để tránh một nhóm tác vụ liên tục bị trì hoãn không?

Ví dụ tác vụ \`(tên, mức ưu tiên, thứ tự đến)\`, trong đó **mức càng nhỏ càng quan trọng**, nếu cùng mức thì tác vụ **đến trước** được chọn trước. Ta so sánh theo:
1. \`priority\` tăng dần.
2. \`arrival\` tăng dần để phá hòa.

Khi viết comparator trong Java, nên dùng \`Comparator.comparingInt\`, \`Integer.compare\` hoặc \`Long.compare\`; tránh viết \`return a.priority - b.priority\` vì phép trừ có thể **tràn int** và làm sai kết quả so sánh.

**Khác biệt cần nhớ:** Java \`PriorityQueue\` là hàng đợi ưu tiên dựa trên heap. Tính toán lấy đúng phần tử đầu theo comparator, nhưng **không bảo đảm FIFO khi comparator đánh giá hai phần tử ngang nhau**. Nếu cần ổn định thứ tự, hãy đưa thứ tự đến vào khóa phụ; bảo đảm trường đó là duy nhất/được quản lý nhất quán nếu bài yêu cầu trật tự hoàn toàn xác định.

Một comparator dùng cho \`PriorityQueue\` phải xác định thứ tự nhất quán: kết quả đối xứng theo dấu, có tính bắc cầu, ổn định đối với các khóa đang nằm trong heap. Thay đổi một thuộc tính tham gia so sánh **sau khi đã chèn** có thể khiến bất biến heap không còn phản ánh ưu tiên mới.

## 4. Ví dụ Java 17 hoàn chỉnh: lập lịch ưu tiên và trộn k dãy

Chương trình minh họa **hai mục đích**:

1. Lập lịch theo mức ưu tiên nhỏ nhất, dùng thời điểm đến làm khóa phụ.
2. Trộn nhiều dãy **đã sắp xếp tăng dần** thành một dãy tăng dần bằng min-heap. Mỗi lúc heap chỉ giữ **phần tử đầu tiên chưa lấy** của mỗi dãy không rỗng.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.StringJoiner;

public class HeapPriorityQueueDemo {
    record Job(String name, int priority, int arrival) {}

    record Cursor(int value, int source, int index) {}

    static List<Integer> mergeSorted(int[][] arrays) {
        PriorityQueue<Cursor> heap = new PriorityQueue<>(
            Comparator.comparingInt(Cursor::value)
                .thenComparingInt(Cursor::source)
                .thenComparingInt(Cursor::index)
        );

        for (int source = 0; source < arrays.length; source++) {
            if (arrays[source].length > 0) {
                heap.offer(new Cursor(arrays[source][0], source, 0));
            }
        }

        List<Integer> merged = new ArrayList<>();

        while (!heap.isEmpty()) {
            Cursor best = heap.poll();
            merged.add(best.value());

            int nextIndex = best.index() + 1;
            int source = best.source();

            if (nextIndex < arrays[source].length) {
                heap.offer(
                    new Cursor(arrays[source][nextIndex], source, nextIndex)
                );
            }
        }

        return merged;
    }

    public static void main(String[] args) {
        PriorityQueue<Job> jobs = new PriorityQueue<>(
            Comparator.comparingInt(Job::priority)
                .thenComparingInt(Job::arrival)
        );

        jobs.offer(new Job("A", 3, 0));
        jobs.offer(new Job("B", 1, 1));
        jobs.offer(new Job("C", 1, 2));
        jobs.offer(new Job("D", 2, 3));

        StringJoiner order = new StringJoiner(", ");
        while (!jobs.isEmpty()) {
            order.add(jobs.poll().name());
        }
        System.out.println("job order: " + order);

        int[][] arrays = {
            {1, 4, 4},
            {2, 5},
            {},
            {1, 3, 6}
        };

        System.out.println("merged: " + mergeSorted(arrays));
    }
}
~~~

Lưu thành **HeapPriorityQueueDemo.java** rồi chạy với **JDK 17+**:

~~~bash
javac HeapPriorityQueueDemo.java
java HeapPriorityQueueDemo
~~~

Kết quả đúng:

~~~text
job order: B, C, D, A
merged: [1, 1, 2, 3, 4, 4, 5, 6]
~~~

**Giải thích phần lập lịch.** B và C đều có \`priority = 1\`; B đến trước nên được chọn trước C. Tiếp đó là D (2), rồi A (3). Hai lần \`poll()\` liên tiếp đều dựa trên ưu tiên, **không dựa vào thứ tự offer**.

**Giải thích phần trộn dãy.** Ban đầu các ứng viên là 1 (dãy 0), 2 (dãy 1), 1 (dãy 3). Khi lấy 1 từ dãy 0, phần tử tiếp theo 4 của dãy 0 mới được đưa vào heap. Khi lấy 1 từ dãy 3, phần tử 3 của dãy 3 được đưa vào heap. Dãy rỗng không tạo ứng viên. Kết quả giữ đủ **hai số 1 và hai số 4** vì bài toán trộn dãy yêu cầu bảo toàn số lần xuất hiện.

\`Arrays\` được import trong ví dụ nhưng không sử dụng; có thể bỏ import đó mà không ảnh hưởng kết quả. Các \`record\` dùng thành phần bất biến sau khi tạo, tránh lỗi thay đổi khóa ưu tiên bên trong heap.

## 5. Vì sao trộn k dãy bằng heap đúng?

Giả sử có k dãy, **mỗi dãy đã sắp tăng không giảm**, tổng cộng N phần tử. Thuật toán giữ bất biến:

> Với mỗi dãy còn phần tử chưa lấy, heap chứa **đúng phần tử đầu tiên chưa lấy** của dãy đó; mỗi dãy như vậy có đúng một mục trong heap.

**Khởi tạo:** thêm phần tử đầu của từng dãy không rỗng, bất biến đúng.

**Duy trì:** vì mỗi dãy đã sắp, phần tử đầu chưa lấy là phần tử nhỏ nhất còn lại trong chính dãy đó. Phần tử nhỏ nhất trong **toàn bộ** dữ liệu chưa lấy phải nằm trong tập các đầu dãy, tức nằm trong heap. \`poll()\` chọn chính phần tử nhỏ nhất toàn cục; sau đó thêm phần tử kế tiếp của cùng dãy để giữ bất biến.

**Kết thúc:** mỗi vòng lặp đưa đúng một phần tử vào kết quả, nên sau N vòng không còn phần tử nào, heap rỗng. Dãy kết quả tăng không giảm và chứa đúng tất cả phần tử đầu vào, kể cả phần tử trùng.

**Độ phức tạp:** duyệt k dãy để đưa đầu dãy vào heap tốn O(k) thao tác kiểm tra; có tối đa k ứng viên trong heap tại bất kỳ thời điểm nào. Mỗi phần tử được thêm và lấy tối đa một lần, mỗi thao tác heap tốn O(log(k + 1)). Tổng thời gian **O(k + N log(k + 1))**; heap dùng **O(k)** bộ nhớ bổ sung, ngoài bộ nhớ dành cho kết quả O(N). Đối chiếu với cách mỗi lần quét đầu của cả k dãy để chọn nhỏ nhất: khi cả k dãy đều còn dữ liệu, chi phí mỗi lượt có thể là O(k), tổng xấu nhất O(Nk).

**Giả thiết không được bỏ qua:** nếu một dãy chưa sắp xếp, phần tử đầu chưa lấy chưa chắc nhỏ nhất của dãy đó, nên việc chỉ giữ đầu dãy có thể cho kết quả sai. Heap hoạt động chính xác ở đây vì bất biến của **bài toán và biểu diễn đầu dãy**, không phải vì bản thân heap tự sắp xếp dữ liệu ở mọi dãy nguồn.

## 6. Dùng heap trong những thuật toán khác

### 6.1. Chọn k giá trị lớn nhất trong dòng dữ liệu

Bài có n số và cần giữ **k phần tử lớn nhất**, k nhỏ hơn n nhiều. Dùng **min-heap với tối đa k phần tử**:
1. Với mỗi số x, nếu heap chưa đủ k phần tử thì đưa vào.
2. Nếu heap đủ k, so sánh x với phần tử nhỏ nhất đang được giữ tại gốc.
3. Nếu x lớn hơn gốc, loại gốc và đưa x vào; nếu không thì bỏ x.
4. Cuối cùng heap chứa k giá trị lớn nhất (tính cả phần tử trùng nếu yêu cầu giữ k vị trí đầu vào), dù thứ tự khi duyệt heap không nhất thiết đã sắp xếp.

**Lý do:** mọi phần tử bị loại đều không tốt hơn phần tử nhỏ nhất trong k phần tử được giữ ở thời điểm loại. Các phần tử tương lai chỉ có thể làm ngưỡng này tăng hoặc giữ nguyên. Với \`1 ≤ k ≤ n\`, thời gian **O(n log(k + 1))**, bộ nhớ bổ sung **O(k)**. Nếu k = 0, kết quả rỗng và không có thao tác \`peek()\` trên heap rỗng. Với các phần tử bằng nhau, cần làm rõ đề bài yêu cầu *giá trị* hay *bản ghi có danh tính* để có khóa phụ phù hợp.

Nếu muốn lấy phần tử **lớn nhất trong toàn bộ tập ứng viên** nhiều lần, một **max-heap** (Java: \`new PriorityQueue<Integer>(Comparator.reverseOrder())\`) phù hợp hơn. Nhưng để giữ k giá trị lớn nhất, **min-heap kích thước k** là cách đặt “phần tử kém nhất trong nhóm đang giữ” ở gốc để thay thế nhanh.

### 6.2. Dijkstra: chọn đỉnh có khoảng cách tạm thời nhỏ nhất

Trong Dijkstra, mỗi bước xét trạng thái có **khoảng cách tạm thời nhỏ nhất**. Min-heap giữ các cặp \`(distance, vertex)\`. Khi tìm đường đi tốt hơn tới một đỉnh, chương trình có thể thêm một cặp mới vào heap.

Một lưu ý quan trọng với Java \`PriorityQueue\`: nó **không có thao tác decrease-key trực tiếp** cho đối tượng đã nằm trong heap. Cách cài đặt thường dùng là **lazy deletion**:
- Mỗi lần cập nhật khoảng cách tốt hơn cho v, thêm cặp \`(newDistance, v)\`.
- Khi lấy \`(distance, v)\`, nếu \`distance\` khác \`dist[v]\` hiện hành thì bỏ qua mục đã cũ.
- Chỉ xử lý các cạnh đi ra từ v khi lấy được trạng thái còn hợp lệ.

Điều kiện trọng số cạnh **không âm** là một giả thiết then chốt để lựa chọn khoảng cách nhỏ nhất theo Dijkstra có chứng minh đúng. Heap chỉ làm nhanh việc chọn ứng viên; nó **không làm Dijkstra đúng trên đồ thị có cạnh âm**. Với cách giữ các mục cũ trong heap, số mục có thể lên tới O(E), nên có thể dùng cận thời gian **O((V + E) log(V + E))** cho đồ thị có V đỉnh, E cạnh trong mô hình phân tích chuẩn, kèm bộ nhớ cho các mục heap; cài đặt cụ thể và cách xử lý cập nhật ảnh hưởng cận chi tiết.

### 6.3. Hàng đợi sự kiện và lập lịch

Trong mô phỏng theo sự kiện, mỗi mục có thời gian diễn ra. Min-heap theo thời gian luôn trả về sự kiện đến sớm nhất. Khi xử lý một sự kiện, hệ thống có thể sinh thêm sự kiện mới vào heap. Nếu có nhiều sự kiện cùng thời gian, khóa phụ như thứ tự tạo hoặc mã sự kiện giúp kết quả xác định.

Trong lập lịch, định nghĩa “ưu tiên cao nhất” có thể kết hợp mức khẩn cấp, deadline hoặc độ trễ. Tuy nhiên, liên tục lấy mục ưu tiên nhất **không tự động tối ưu** số việc hoàn thành, độ trễ trung bình hay công bằng. Muốn chứng minh một chính sách lập lịch tối ưu, phải dựa trên đặc tả mục tiêu và các giả thiết của bài toán, chứ không chỉ dựa vào việc dùng priority queue.

## 7. Java PriorityQueue: hành vi quan trọng cần nhớ

\`java.util.PriorityQueue<E>\` thường dùng **min-heap** theo thứ tự tự nhiên của phần tử hoặc theo \`Comparator\` được truyền vào constructor.

| Thao tác Java | Ý nghĩa | Chi phí điển hình |
| --- | --- | --- |
| \`offer(x)\` | Thêm x vào heap | O(log n) |
| \`peek()\` | Xem phần tử ưu tiên nhất, không xóa | O(1) |
| \`poll()\` | Lấy và xóa phần tử ưu tiên nhất | O(log n) |
| \`size()\`, \`isEmpty()\` | Kiểm tra số phần tử | O(1) |
| \`contains(x)\` | Tìm phần tử bất kỳ theo \`equals\` | O(n) |
| \`remove(x)\` | Tìm và xóa phần tử bất kỳ | O(n) để tìm, sau đó sửa heap |
| Duyệt qua iterator | Duyệt các phần tử hiện có | **Không bảo đảm thứ tự ưu tiên** |

Chi phí \`offer\` và \`poll\` tăng theo chiều cao heap, không phải theo toàn bộ n phần tử. Cần tránh hiểu lầm rằng mọi thao tác của PriorityQueue đều O(log n): kiểm tra một phần tử bất kỳ hoặc xóa theo giá trị thường phải duyệt tìm.

Một số chi tiết API:
- Khi rỗng, \`peek()\` và \`poll()\` trả **null**; \`element()\` và \`remove()\` dạng không tham số ném \`NoSuchElementException\`.
- \`PriorityQueue\` **không nhận phần tử null**. Nếu không truyền comparator, các phần tử phải so sánh được với nhau theo thứ tự tự nhiên.
- \`PriorityQueue\` không đồng bộ để dùng chung từ nhiều luồng mà không có cơ chế phối hợp; nếu cần hàng đợi ưu tiên an toàn giữa nhiều luồng, hãy chọn cấu trúc đồng thời phù hợp và hiểu rõ hành vi của nó.
- Thứ tự duyệt bằng \`iterator\` hoặc \`for-each\` **không tương đương** thứ tự \`poll()\`. Muốn lấy toàn bộ theo thứ tự ưu tiên, cần lần lượt \`poll()\` (làm thay đổi hàng đợi), hoặc tạo bản sao rồi \`poll()\` trên bản sao.
- Thay đổi trường được comparator sử dụng trên đối tượng **đang nằm trong heap** không tự sắp xếp lại heap. Hãy ưu tiên khóa bất biến; nếu mức ưu tiên đổi, dùng cấu trúc hỗ trợ cập nhật khóa hoặc thêm trạng thái mới và loại trạng thái cũ bằng cơ chế rõ ràng.

### Sai lầm về comparator và số nguyên

Comparator kiểu \`(a, b) -> a.score() - b.score()\` có thể tràn int. Ví dụ \`Integer.MAX_VALUE - (-1)\` vượt khả năng biểu diễn int và cho dấu sai. Hãy viết \`Comparator.comparingInt(Item::score)\` hoặc \`Integer.compare(a.score(), b.score())\`.

Đảo ngược toàn bộ comparator gồm nhiều khóa phụ có thể vô tình đảo cả thứ tự phá hòa. Nếu muốn **điểm cao nhất trước nhưng người đến trước trước khi điểm bằng nhau**, một cách phù hợp là:

~~~java
Comparator<Job> higherPriorityFirst =
    Comparator.comparingInt(Job::priority)
        .reversed()
        .thenComparingInt(Job::arrival);
~~~

Đây là **đoạn mã minh họa** dùng \`Job\` record khai báo trong chương trình đầy đủ ở trên, không phải chương trình độc lập. \`reversed()\` ở đây chỉ đảo khóa \`priority\`, sau đó mới thêm khóa phụ \`arrival\` tăng dần. Định nghĩa chiều ưu tiên ở đây **ngược** với ví dụ chạy chính (nơi số nhỏ được ưu tiên trước); cả hai đều hợp lệ nếu nhất quán với đặc tả.

## 8. Khi nào heap là lựa chọn hợp lý?

Hãy xét đúng chuỗi thao tác mà bài toán cần:

| Nhu cầu nổi bật | Biểu diễn nên cân nhắc | Lý do |
| --- | --- | --- |
| Thêm ứng viên và lấy tốt nhất lặp lại | Heap / priority queue | Cân bằng O(log n) cho thêm và lấy |
| Chỉ cần tìm min/max một lần | Một vòng quét | O(n), không cần dựng heap |
| Cần toàn bộ kết quả đã sắp xếp và ít cập nhật | Sắp xếp mảng/list | Dễ duyệt tuần tự; thường O(n log n) |
| Lấy k phần tử lớn nhất với k nhỏ | Min-heap kích thước k | O(n log(k + 1)), O(k) bộ nhớ |
| Cần tìm và xóa tùy ý theo khóa | TreeMap, cấu trúc có chỉ mục, hoặc heap + map vị trí | Heap thường không tối ưu cho tra cứu tùy ý |
| Cần lấy phần tử theo thứ tự đến | Queue FIFO | Quy tắc “đến trước” mới là tiêu chí |
| Ưu tiên thay đổi liên tục | Indexed heap/decrease-key hoặc lazy entries | Heap thường không tự phản ánh khóa đã đổi |

So sánh nên tính cả **chi phí tạo cấu trúc**, số lần chèn/lấy, số phần tử tối đa, độ phức tạp bộ nhớ và ý nghĩa của việc phá hòa. Chỉ vì một bài có chữ “tốt nhất” chưa chắc đã dùng được quy tắc tham lam; cần phân biệt **chọn tốt nhất trong số ứng viên hiện tại** với **lời giải tối ưu cho toàn bộ bài**.

## 9. Các tình huống biên và cách kiểm tra

1. **Heap rỗng:** trước khi \`poll()\`, xác định thuật toán có kiểm tra rỗng chưa. Nếu rỗng thì \`poll()\` trả null; không được gọi phương thức trên đối tượng null.
2. **Chỉ một phần tử:** \`peek()\` trả đúng phần tử đó, \`poll()\` trả nó rồi heap rỗng.
3. **Nhiều phần tử cùng ưu tiên:** kết quả được chọn phải đúng mức ưu tiên; nếu bài yêu cầu thứ tự ổn định, thêm khóa phụ nhất quán.
4. **Giá trị âm và cực trị:** min-heap vẫn dùng được với số âm; comparator viết bằng phép trừ có nguy cơ tràn.
5. **Chèn xen kẽ lấy ra:** thường dễ lộ lỗi sift-up/sift-down hơn trường hợp chỉ chèn hết rồi lấy hết.
6. **Dữ liệu nguồn rỗng trong trộn k dãy:** bỏ qua dãy đó khi tạo heap; kết quả rỗng nếu tất cả dãy rỗng.
7. **Giá trị trùng trong top-k/trộn dãy:** có giữ từng lần xuất hiện hay chỉ giữ giá trị phân biệt? Cấu trúc \`PriorityQueue\` có thể chứa phần tử trùng; đừng tự dùng \`Set\` nếu bài yêu cầu bội số.
8. **Ưu tiên thay đổi sau khi chèn:** hoặc loại và thêm lại theo giao thức chính xác, hoặc dùng kỹ thuật lazy entries có điều kiện bỏ bản cũ.
9. **K rất nhỏ so với N:** giữ heap chỉ có k phần tử có thể tiết kiệm bộ nhớ hơn đưa toàn bộ n ứng viên vào.
10. **Thuật toán cần biết vị trí/phần tử bất kỳ:** không giả định heap hỗ trợ tìm kiếm ngẫu nhiên O(log n); đó không phải tính chất của binary heap.

Một bộ kiểm thử cho priority queue có thể bắt đầu từ chuỗi:
- \`offer(7)\`, \`offer(2)\`, \`offer(6)\`, \`offer(1)\`; \`peek()\` phải cho 1.
- \`poll()\` lần lượt phải cho 1, 2, 6, 7.
- Thêm 3 và 3, lấy hai lần phải nhận hai giá trị 3; nếu mỗi mục có danh tính và quy tắc phá hòa, kiểm tra thêm thứ tự theo danh tính.
- \`poll()\` tiếp khi rỗng phải trả null.

Với mã tự cài heap, sau **mỗi thao tác** nên kiểm tra: số phần tử đúng, cây còn gần đầy và mọi cặp cha/con đều thỏa bất biến. Với Java \`PriorityQueue\`, có thể đối chiếu thứ tự \`poll()\` với một bản danh sách nhỏ đã sắp xếp bằng comparator để kiểm thử hành vi ứng dụng.

## 10. Những lỗi tư duy phổ biến

- **Nhầm heap với mảng đã sắp:** chỉ gốc bảo đảm có ưu tiên tốt nhất; các nhánh không được sắp xếp toàn cục.
- **Nhầm priority queue với FIFO:** phần tử thêm sau vẫn có thể được lấy trước nếu có ưu tiên cao hơn.
- **Không xác định thứ tự phá hòa:** hai tác vụ cùng khóa có thể được lấy theo thứ tự không mong muốn.
- **Chọn sai min-heap/max-heap:** k giá trị lớn nhất thường dùng min-heap kích thước k, không phải cứ “lớn nhất” là dùng max-heap.
- **Quên các mục cũ khi ưu tiên thay đổi:** đặc biệt khi dùng \`PriorityQueue\` cho đường đi ngắn nhất.
- **Tin rằng truy vấn tùy ý O(log n):** binary heap chỉ ưu tiên phần tử ở gốc; tìm phần tử theo giá trị không phải thế mạnh.
- **Bỏ qua tiền điều kiện thuật toán:** trộn k dãy cần từng dãy đã sắp; Dijkstra cần trọng số không âm theo phiên bản chuẩn.
- **Lấy được phần tử nhỏ nhất rồi kết luận lời giải tối ưu:** dùng heap không thay thế chứng minh tham lam, quy hoạch động hay chứng minh bất biến.
- **Đọc iterator và tưởng đã có thứ tự ưu tiên:** cần lấy bằng \`poll()\` để có thứ tự trả về chính xác.
- **Tối ưu cấu trúc quá sớm:** nếu chỉ tìm một giá trị tốt nhất trong n số một lần, duyệt O(n) thường đơn giản hơn dựng heap.

## 11. Tự luyện và đáp án tham khảo

**Bài 1.** Cho min-heap rỗng, lần lượt thêm 7, 2, 6, 1. Hãy ghi trạng thái mảng sau mỗi lần thêm và sau một lần lấy phần tử nhỏ nhất.

*Đáp án:* \`[7]\` → \`[2, 7]\` → \`[2, 7, 6]\` → \`[1, 2, 6, 7]\`; lấy 1, sửa heap thành \`[2, 7, 6]\`.

**Bài 2.** Tại sao trộn k dãy đã sắp xếp chỉ cần giữ một ứng viên cho mỗi dãy trong min-heap, thay vì đưa cả N phần tử vào heap?

*Đáp án:* Ứng viên đầu chưa lấy của mỗi dãy luôn là phần tử nhỏ nhất còn lại trong chính dãy đó. Phần tử nhỏ nhất toàn cục phải thuộc các đầu dãy; heap giữ tối đa k ứng viên và mỗi lượt chỉ thêm đầu tiếp theo của dãy vừa lấy.

**Bài 3.** Có 1.000.000 số đến lần lượt, cần giữ 100 số lớn nhất tại mọi thời điểm. Nên giữ một max-heap toàn bộ dữ liệu hay min-heap tối đa 100 phần tử?

*Đáp án:* Min-heap tối đa 100 phần tử. Gốc là phần tử nhỏ nhất đang thuộc nhóm 100 tốt nhất; số mới chỉ thay thế gốc khi tốt hơn. Bộ nhớ O(100), mỗi lần cập nhật O(log 100). Cần xác định cách xử lý giá trị trùng nếu bài quan tâm đến danh tính các bản ghi.

**Bài 4.** Nếu ta muốn ưu tiên thời điểm đến sớm khi mức ưu tiên bằng nhau, chỉ đưa \`priority\` vào comparator đã đủ chưa?

*Đáp án:* Chưa. \`PriorityQueue\` không bảo đảm FIFO khi hai khóa được comparator xem là bằng nhau. Phải thêm \`arrival\` vào khóa thứ hai (và khóa tiếp theo nếu cần bảo đảm thứ tự hoàn toàn xác định).

**Bài 5.** Dijkstra đang có \`dist[v] = 5\`, heap vẫn còn mục cũ \`(9, v)\`. Khi lấy mục này, phải làm gì với cài đặt lazy entries?

*Đáp án:* Bỏ qua mục \`(9, v)\` vì khoảng cách của nó không còn bằng \`dist[v]\`. Chỉ xử lý trạng thái có khóa còn khớp với khoảng cách tốt nhất hiện tại.

## Ghi nhớ

**Priority queue** diễn tả yêu cầu “chọn ứng viên ưu tiên nhất”; **binary heap** là cách cài hiệu quả dựa trên bất biến **cha không kém con**. Heap cho \`peek\` O(1), thêm/lấy O(log n), dựng bottom-up O(n) và bộ nhớ O(n). Điều làm một lời giải thành công là chọn đúng **khóa ưu tiên, quy tắc phá hòa, điều kiện duy trì ứng viên**, đồng thời chứng minh rằng chọn ứng viên ấy phù hợp với mục tiêu tổng thể.