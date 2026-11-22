# Thực hành tổng hợp: Giải bài toán top-K và hàng đợi tác vụ theo ưu tiên

Khi một hệ thống nhận rất nhiều dữ liệu, đôi khi ta chỉ cần **K phần tử tốt nhất**, hoặc phải chọn **công việc nào được thực hiện tiếp theo** theo mức độ khẩn cấp. Cả hai bài toán đều có thể giải bằng `PriorityQueue` của Java, nhưng **mục tiêu và hướng so sánh khác nhau**.

Bài thực hành này áp dụng Java Collections Framework vào hai tình huống cụ thể. Sau bài học, bạn có thể:

- Mô tả rõ tiêu chí chọn top-K, kể cả giá trị trùng, đầu vào rỗng và trường hợp K vượt số phần tử.
- Dùng min-heap kích thước không quá K để tìm K giá trị lớn nhất.
- Phân tích bất biến, chứng minh tính đúng và tính độ phức tạp theo N, K.
- Xây dựng hàng đợi tác vụ lấy mức ưu tiên cao trước, giữ thứ tự đến khi bằng mức ưu tiên.
- Giải thích `offer()`, `peek()`, `poll()` và vì sao duyệt một `PriorityQueue` không cho kết quả đã sắp xếp.
- Kiểm tra bằng mã Java 17 biên dịch và chạy được, rồi mở rộng sang các trường hợp nghiệp vụ khác.

Các ví dụ được thiết kế cho chương trình chạy một luồng; vấn đề đồng thời được phân biệt ở phần lưu ý.

## 1. Hai đề bài và quy tắc đầu ra

### Bài toán A: chọn top-K điểm cao nhất

Một hệ thống lưu điểm các lượt kiểm tra trong mảng:

~~~text
[12, 7, 25, 10, 25, 3, 19, 18]
~~~

Hãy trả về **ba điểm lớn nhất**, sắp theo thứ tự giảm dần. Hai lượt đạt `25` là hai phần tử của đầu vào, vì vậy bài toán **cho phép trùng** và kết quả đúng là:

~~~text
[25, 25, 19]
~~~

Quy ước cần thống nhất trước khi lập trình:

| Trường hợp | Hành vi mong muốn |
| --- | --- |
| `k = 3` với mảng trên | `[25, 25, 19]` |
| `k = 0` | Danh sách rỗng |
| `k > n` (n là số phần tử) | Trả tất cả n phần tử, giảm dần |
| Mảng rỗng và `k ≥ 0` | Danh sách rỗng |
| `k < 0` | Ném `IllegalArgumentException` |
| Mảng đầu vào `null` | Ném `IllegalArgumentException` |

Hàm không được sắp xếp tại chỗ hay sửa mảng gốc. Bài toán chọn **K lần xuất hiện có giá trị cao nhất**, khác với chọn K giá trị *phân biệt*.

### Bài toán B: xử lý công việc theo độ ưu tiên

Hàng đợi nhận lần lượt:

| Thứ tự nhận | Tác vụ | Mức ưu tiên |
| --- | --- | --- |
| 0 | Sao lưu dữ liệu | 2 |
| 1 | Xử lý sự cố | 5 |
| 2 | Gửi email | 2 |
| 3 | Khôi phục dịch vụ | 5 |
| 4 | Dọn tệp tạm | 1 |

Quy tắc là **số ưu tiên lớn hơn được xử lý trước**. Nếu bằng mức ưu tiên, tác vụ nhận sớm hơn được xử lý trước. Kết quả lấy lần lượt khỏi hàng đợi phải là:

1. Xử lý sự cố (mức 5, đến số 1).
2. Khôi phục dịch vụ (mức 5, đến số 3).
3. Sao lưu dữ liệu (mức 2, đến số 0).
4. Gửi email (mức 2, đến số 2).
5. Dọn tệp tạm (mức 1, đến số 4).

Hàng đợi ưu tiên khác hàng đợi vào trước ra trước (FIFO) thông thường: công việc ưu tiên cao đến sau vẫn có thể vượt các công việc ưu tiên thấp đang chờ. FIFO chỉ là **tiêu chí phụ** bên trong một nhóm có cùng ưu tiên.

## 2. Vì sao `PriorityQueue` phù hợp?

`PriorityQueue<E>` thuộc `java.util`. Nó quản lý phần tử theo thứ tự tự nhiên hoặc một `Comparator` được cung cấp lúc khởi tạo. Triển khai tiêu chuẩn dùng binary heap để duy trì phần tử **đứng đầu theo comparator** mà không phải sắp xếp toàn bộ tập hợp sau mỗi lần thêm.

| API | Ý nghĩa | Độ phức tạp điển hình |
| --- | --- | --- |
| `offer(e)` | Thêm phần tử | O(log m) |
| `peek()` | Xem đầu hàng đợi, không xóa; rỗng trả `null` | O(1) |
| `poll()` | Xem và xóa đầu hàng đợi; rỗng trả `null` | O(log m) |
| `size()` / `isEmpty()` | Đếm / kiểm tra rỗng | O(1) |
| `contains(e)` | Tìm phần tử theo quy tắc bằng nhau | O(m) |
| `remove(e)` | Xóa một phần tử cụ thể | O(m) |

Trong bảng, m là số phần tử hiện đang lưu; các độ phức tạp mô tả triển khai `PriorityQueue` chuẩn.

Theo mặc định, `new PriorityQueue<Integer>()` là **min-heap**: `peek()` cho **số nhỏ nhất**. Với `Comparator.reverseOrder()`, nó hoạt động như **max-heap** theo thứ tự số nguyên: `peek()` cho **số lớn nhất**.

Cần phân biệt ba thứ tự:

- **Thứ tự nhận:** khi phần tử được đưa vào bằng `offer()`.
- **Thứ tự ưu tiên:** do `Comparable` hoặc `Comparator` xác định.
- **Thứ tự duyệt nội bộ:** thứ tự `iterator`, `for-each` hoặc `toString()` nhìn thấy; **không được bảo đảm đã sắp xếp theo ưu tiên**.

Chỉ khi dùng `poll()` liên tiếp mới nhận lần lượt các phần tử đứng đầu theo comparator. Nếu phải giữ hàng đợi để sử dụng sau, hãy tạo bản sao rồi `poll()` trên bản sao hoặc dùng cách sắp xếp khác.

Mặc định, `PriorityQueue` cũng **không giữ FIFO cho các phần tử bằng ưu tiên**. Muốn ổn định thứ tự đến trong cùng một mức, ta phải đưa thứ tự nhận vào comparator.

## 3. Top-K lớn nhất: dùng min-heap kích thước K

### 3.1. Trực giác lựa chọn cấu trúc

Một cách làm dễ hiểu là sao chép rồi sắp xếp toàn bộ n phần tử giảm dần, sau đó lấy K phần tử đầu. Cách này thường cần O(n log n) thời gian và phải giữ hoặc thao tác trên toàn bộ n phần tử.

Khi K nhỏ so với n, ta không cần nhớ tất cả. Ta chỉ cần duy trì **K ứng viên lớn nhất trong số phần tử đã đọc**. Để có thể thay nhanh phần tử yếu nhất trong nhóm ứng viên, ta đặt **phần tử nhỏ nhất của nhóm đó ở đầu heap**.

Vì thế, tìm **K số lớn nhất** lại sử dụng **min-heap**, không phải max-heap, ở giai đoạn chọn ứng viên. Max-heap toàn bộ n phần tử có thể lấy K số lớn nhất, nhưng phải giữ O(n) phần tử nếu đưa toàn bộ dữ liệu vào trước.

### 3.2. Thuật toán từng bước

Với K dương và mảng đầu vào:

1. Tạo `PriorityQueue<Integer> minHeap = new PriorityQueue<>()`.
2. Duyệt từng số `x`. Nếu heap có ít hơn K số, thêm `x` bằng `offer(x)`.
3. Nếu heap đã đủ K số, xem `minHeap.peek()`, tức **ứng viên nhỏ nhất**.
4. Nếu `x > minHeap.peek()`, xứng đáng thay ứng viên yếu nhất: gọi `poll()` rồi `offer(x)`.
5. Nếu `x ≤ minHeap.peek()`, giữ nguyên K ứng viên đã có. Với bài toán chỉ xét **giá trị số**, phần tử mới bằng ngưỡng không làm thay đổi tập kết quả.
6. Duyệt xong, sao chép các ứng viên sang `List<Integer>` rồi sắp xếp **giảm dần** để tạo đầu ra đúng hợp đồng.

### 3.3. Lần vết dữ liệu

Với K = 3, ta có bảng diễn biến sau. Cột cuối được **trình bày tăng dần để dễ nhìn**, không mô tả thứ tự trong mảng nội bộ của heap:

| Số vừa đọc | Quyết định | Các ứng viên đang giữ |
| --- | --- | --- |
| 12 | Chưa đủ 3, thêm | [12] |
| 7 | Chưa đủ 3, thêm | [7, 12] |
| 25 | Chưa đủ 3, thêm | [7, 12, 25] |
| 10 | Lớn hơn 7, thay 7 | [10, 12, 25] |
| 25 | Lớn hơn 10, thay 10 | [12, 25, 25] |
| 3 | Không lớn hơn 12, bỏ qua | [12, 25, 25] |
| 19 | Lớn hơn 12, thay 12 | [19, 25, 25] |
| 18 | Không lớn hơn 19, bỏ qua | [19, 25, 25] |

Sắp xếp ba ứng viên giảm dần, ta được `[25, 25, 19]`.

### 3.4. Bất biến và lý do thuật toán đúng

**Bất biến:** sau khi xử lý bất kỳ tiền tố nào của đầu vào, heap chứa đúng `min(K, số phần tử đã đọc)` giá trị lớn nhất của tiền tố ấy, **tính cả giá trị trùng**.

- Khi heap chưa đủ K, tất cả số đã gặp đều là ứng viên hợp lệ và được thêm.
- Khi heap đủ K, nếu số mới `x` không lớn hơn số nhỏ nhất đang giữ, đã tồn tại K ứng viên có giá trị không nhỏ hơn `x`; việc thêm x không cải thiện kết quả.
- Khi `x` lớn hơn số nhỏ nhất đang giữ, thay số nhỏ nhất bằng x sẽ giữ đúng K giá trị tốt nhất của tiền tố mới.

Tính chất được duy trì sau mỗi lượt; do đó khi duyệt hết mảng, heap giữ đúng các giá trị cần tìm. Việc sắp xếp cuối cùng chỉ đổi thứ tự trình bày, không đổi tập kết quả.

### 3.5. Phân tích chi phí

Đặt n là số phần tử, `h = min(K, n)` khi K ≥ 0. Heap có nhiều nhất h phần tử. Mỗi số có thể gây một thao tác thêm, lấy, thay với chi phí O(log h) khi h ≥ 2. Sắp xếp h kết quả tốn O(h log h).

**Thời gian:** O(n log h + h log h) khi h ≥ 2; các trường hợp h = 0 hoặc h = 1 được xử lý đơn giản hơn.

**Bộ nhớ phụ:** O(h) để giữ heap và danh sách kết quả. Nếu K = 10 mà n rất lớn, bộ nhớ lưu ứng viên vẫn tỉ lệ với 10, trong khi việc sắp xếp toàn bộ thường phải xử lý tập dữ liệu lớn hơn nhiều.

Không gọi `peek()` trên heap rỗng: đoạn mã mẫu sẽ kiểm tra K = 0, mảng rỗng và chỉ so sánh với `peek()` sau khi heap đã đạt đủ K phần tử.

## 4. Hàng đợi tác vụ: ưu tiên chính và tiêu chí phụ

### 4.1. Biểu diễn tác vụ

Mỗi tác vụ cần:

- `name`: tên mô tả.
- `priority`: mức ưu tiên số nguyên, số lớn hơn là khẩn cấp hơn.
- `sequence`: số thứ tự nhận vào, tăng dần và **duy nhất trong một hàng đợi**.

Java 17 hỗ trợ `record` để định nghĩa đối tượng chứa dữ liệu không đổi sau khi tạo. Dùng record giúp tránh trường hợp thay đổi độ ưu tiên khi đối tượng đang nằm trong heap.

### 4.2. Comparator đúng yêu cầu

Comparator phải xét **mức ưu tiên giảm dần**, rồi **số thứ tự nhận tăng dần**:

~~~java
Comparator<Task> taskOrder =
        Comparator.comparingInt((Task task) -> task.priority())
                .reversed()
                .thenComparingLong(Task::sequence);
~~~

Đây là đoạn minh họa nằm trong phạm vi lớp có kiểu `Task`; chương trình chạy độc lập đầy đủ ở mục 5.

Các tác vụ cùng mức 5 sẽ được lấy theo `sequence` tăng dần: 1 trước 3. Sau đó mới đến tác vụ mức 2, rồi mức 1. Bản thân việc đưa một tác vụ mới vào hàng đợi **không khởi chạy** tác vụ đó; `poll()` chỉ chọn và lấy phần tử kế tiếp.

Nếu một tác vụ đã bắt đầu chạy, tác vụ mới ưu tiên cao hơn không tự ngắt nó. Hàng đợi quản lý **việc chọn tác vụ tiếp theo**, không thực hiện cơ chế tiền nhiệm (preemption) cho tác vụ đang chạy.

## 5. Chương trình Java 17 hoàn chỉnh

Tạo tệp tên **`TopKAndPriorityDemo.java`** trong thư mục thực hành.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class TopKAndPriorityDemo {

    private record Task(long sequence, String name, int priority) {
    }

    public static List<Integer> topKLargest(int[] numbers, int k) {
        if (numbers == null) {
            throw new IllegalArgumentException("numbers không được null");
        }
        if (k < 0) {
            throw new IllegalArgumentException("k phải không âm");
        }
        if (k == 0 || numbers.length == 0) {
            return List.of();
        }

        PriorityQueue<Integer> minHeap = new PriorityQueue<>();

        for (int number : numbers) {
            if (minHeap.size() < k) {
                minHeap.offer(number);
            } else if (number > minHeap.peek()) {
                minHeap.poll();
                minHeap.offer(number);
            }
        }

        List<Integer> result = new ArrayList<>(minHeap);
        result.sort(Comparator.reverseOrder());
        return result;
    }

    public static void main(String[] args) {
        int[] scores = {12, 7, 25, 10, 25, 3, 19, 18};

        System.out.println("Top 3 điểm: " + topKLargest(scores, 3));
        System.out.println("Top 0 điểm: " + topKLargest(scores, 0));

        Comparator<Task> taskOrder =
                Comparator.comparingInt((Task task) -> task.priority())
                        .reversed()
                        .thenComparingLong(Task::sequence);

        PriorityQueue<Task> pending = new PriorityQueue<>(taskOrder);

        pending.offer(new Task(0, "Sao lưu dữ liệu", 2));
        pending.offer(new Task(1, "Xử lý sự cố", 5));
        pending.offer(new Task(2, "Gửi email", 2));
        pending.offer(new Task(3, "Khôi phục dịch vụ", 5));
        pending.offer(new Task(4, "Dọn tệp tạm", 1));

        System.out.println("Thứ tự xử lý tác vụ:");
        while (!pending.isEmpty()) {
            Task task = pending.poll();
            System.out.println("- " + task.name()
                    + " | ưu tiên=" + task.priority()
                    + " | đến=" + task.sequence());
        }
    }
}
~~~

Trong thư mục chứa tệp trên, biên dịch và chạy:

~~~text
javac -encoding UTF-8 --release 17 TopKAndPriorityDemo.java
java -Dfile.encoding=UTF-8 TopKAndPriorityDemo
~~~

**Kết quả stdout:**

~~~text
Top 3 điểm: [25, 25, 19]
Top 0 điểm: []
Thứ tự xử lý tác vụ:
- Xử lý sự cố | ưu tiên=5 | đến=1
- Khôi phục dịch vụ | ưu tiên=5 | đến=3
- Sao lưu dữ liệu | ưu tiên=2 | đến=0
- Gửi email | ưu tiên=2 | đến=2
- Dọn tệp tạm | ưu tiên=1 | đến=4
~~~

### Đọc đoạn code top-K

- `topKLargest(int[] numbers, int k)` từ chối mảng `null` và K âm.
- Khi K bằng 0 hoặc mảng rỗng, hàm trả `List.of()`. Danh sách rỗng này không cần thêm hoặc xóa phần tử.
- `minHeap.size() < k` cho phép thêm cho đến khi đủ K ứng viên.
- Khi đã đủ K, `number > minHeap.peek()` quyết định có thay phần tử nhỏ nhất hay không.
- `new ArrayList<>(minHeap)` chép dữ liệu khỏi heap; `sort(Comparator.reverseOrder())` là bước riêng để đáp ứng đầu ra giảm dần.
- `scores` là mảng đầu vào; thuật toán không sửa các vị trí của mảng này.

### Đọc đoạn code hàng đợi tác vụ

- `Task` có ba thành phần bất biến: `sequence`, `name`, `priority`.
- `Comparator.comparingInt(...).reversed()` đưa mức ưu tiên cao hơn lên trước.
- `thenComparingLong(Task::sequence)` bảo đảm thứ tự đến tăng dần khi mức ưu tiên bằng nhau.
- `pending.offer(...)` chỉ đưa tác vụ vào hàng đợi.
- Mỗi vòng `while (!pending.isEmpty())` gọi `poll()`, lấy một tác vụ có thứ tự ưu tiên cao nhất theo comparator và in thông tin của nó.
- Sau năm lần `poll()`, hàng đợi rỗng. Đầu ra trong chương trình ổn định vì comparator đã xác định cả ưu tiên và thứ tự đến.

Không được thay đoạn `poll()` bằng cách duyệt trực tiếp `pending` nếu cần in các tác vụ theo đúng thứ tự xử lý.

## 6. Đối chiếu hai cách dùng cùng một cấu trúc

| Khía cạnh | Top-K lớn nhất | Hàng đợi tác vụ |
| --- | --- | --- |
| Mục đích | Giữ lại K ứng viên tốt nhất | Chọn tác vụ kế tiếp |
| Phần tử đầu heap | Số nhỏ nhất trong nhóm K tốt nhất | Tác vụ ưu tiên nhất |
| Comparator | Thứ tự tự nhiên tăng dần của `Integer` | Ưu tiên giảm dần, rồi thứ tự đến tăng dần |
| Kích thước | Giới hạn không quá K | Tăng/giảm theo tác vụ chờ |
| Khi có phần tử mới | Có thể loại ứng viên yếu nhất | Thêm vào để xét thứ tự xử lý |
| Khi lấy phần tử | Loại ứng viên thấp trong quá trình cập nhật | Lấy tác vụ cần xử lý tiếp |
| Đầu ra | Chuyển thành `List` rồi sắp xếp giảm dần | `poll()` cho từng tác vụ |

Điểm quyết định là đặt đúng **phần tử cần xem thường xuyên** tại `peek()`. Với top-K, đó là giá trị thấp nhất trong K ứng viên. Với xử lý tác vụ, đó là công việc khẩn cấp nhất.

## 7. Biến thể bài toán và ảnh hưởng tới thiết kế

### 7.1. Top-K **không trùng giá trị**

Nếu đề bài đổi thành “K điểm **phân biệt** cao nhất”, kết quả ví dụ phải là `[25, 19, 18]`. Ta cần một bước loại giá trị trùng, chẳng hạn ghi nhận các giá trị đã thấy bằng `HashSet<Integer>` trước khi cân nhắc đưa vào heap. Một tập `HashSet` nhớ **tất cả** giá trị đã đọc có thể tốn O(s) bộ nhớ với s là số giá trị phân biệt, nên không còn chỉ dùng O(K) bộ nhớ tổng cộng. Cần nêu đúng chi phí của biến thể này.

### 7.2. Top-K **bản ghi** thay vì số

Nếu cần lấy K sinh viên có điểm cao nhất, mỗi phần tử có thể là `Student(id, score, sequence)`. Khi nhiều sinh viên cùng điểm và K cắt đúng vùng hòa điểm, phải xác định tiêu chí: mã sinh viên nhỏ hơn, đến trước hoặc chấp nhận bất kỳ? Việc so sánh `number > peek()` chỉ giải quyết **giá trị số**, chưa phải quy tắc lựa chọn các bản ghi bằng điểm. Comparator và điều kiện thay thế phải thống nhất cùng một chính sách tie-break.

### 7.3. Top-K **tần suất**

Nếu đề yêu cầu K từ xuất hiện nhiều nhất, ta phải đếm trước bằng `Map<String, Integer>`, rồi chọn K cặp (từ, tần suất) theo số lần xuất hiện. Cần quy định cách chọn khi hai từ có cùng tần suất; dùng giá trị từ làm tiêu chí chính là sai đề.

### 7.4. Ưu tiên thay đổi khi tác vụ đang chờ

`PriorityQueue` không tự sắp lại heap khi thay đổi các trường ảnh hưởng tới comparator của một đối tượng đã đưa vào. Với tác vụ đổi mức ưu tiên, phải thiết kế thao tác hủy/thêm lại hoặc cơ chế đánh dấu bản ghi cũ và thêm bản cập nhật. Record bất biến trong ví dụ tránh khả năng thay đổi ngầm làm hỏng thứ tự.

### 7.5. Đa luồng và nguồn tác vụ liên tục

`PriorityQueue` không bảo đảm an toàn khi nhiều luồng đồng thời thêm và lấy. Với nhiều producer/consumer, có thể cân nhắc `PriorityBlockingQueue` và mô hình worker phù hợp. Tuy nhiên, việc ưu tiên tác vụ **không tự bảo đảm giới hạn dung lượng hàng chờ, công bằng tuyệt đối hoặc tác vụ ít ưu tiên chắc chắn đến lượt**. Nếu liên tục xuất hiện tác vụ khẩn cấp, tác vụ ưu tiên thấp có thể chờ rất lâu; đó là vấn đề chính sách lập lịch, không giải quyết chỉ bằng comparator.

## 8. Lỗi thường gặp

**Sai 1 — Dùng max-heap chứa cả N phần tử để gọi là tối ưu bộ nhớ top-K.** Cách đó có thể đúng kết quả nhưng giữ O(N) phần tử nếu nạp toàn bộ mảng. Khi K nhỏ, min-heap giới hạn K tiết kiệm hơn.

**Sai 2 — In trực tiếp heap và tin rằng đã được sắp xếp.** `PriorityQueue` chỉ bảo đảm phần tử đầu; thứ tự iterator không phải thứ tự `poll()`. Muốn kết quả có thứ tự, phải sắp xếp danh sách hoặc lấy phần tử đúng cách.

**Sai 3 — Viết comparator bằng phép trừ `b - a`.** Số nguyên có thể tràn, làm thứ tự sai. Dùng `Integer.compare(b, a)` hoặc `Comparator.comparingInt(...).reversed()`. Với số thứ tự kiểu long, dùng `Long.compare` hoặc `thenComparingLong`.

**Sai 4 — Chỉ so sánh mức ưu tiên mà quên quy tắc khi bằng nhau.** Java không cam kết FIFO cho các tác vụ comparator xem là bằng nhau. Nếu yêu cầu “đến trước xử lý trước” trong cùng mức, thêm `sequence` vào comparator.

**Sai 5 — Gọi `peek()` ở hàng đợi rỗng hoặc bỏ qua K = 0.** Khi rỗng, `peek()` trả `null`; tự mở hộp số nguyên có thể gây `NullPointerException`. Xử lý các biên trước khi đi vào nhánh so sánh.

**Sai 6 — Thay đổi giá trị ưu tiên của phần tử đang nằm trong heap.** Cấu trúc có thể không tự tái lập thứ tự như mong đợi. Nên lưu dữ liệu ưu tiên bất biến hoặc cập nhật lại hàng đợi theo quy trình rõ ràng.

**Sai 7 — Coi hàng đợi ưu tiên là bộ lập lịch đang chạy.** Việc thêm vào hàng đợi hoặc lấy bằng `poll()` không tự tạo luồng, không tự quản lý retry, timeout hay ngắt tác vụ đang thực thi.

## 9. Bài tập củng cố và kết quả để tự đối chiếu

### Bài 1. Top-2 với phần tử trùng

Cho `[4, 15, 2, 15, 9, 20]` và K = 2. Ghi diễn biến ứng viên sau từng số rồi chạy hàm. Đầu ra mong đợi: `[20, 15]`. Giải thích vì sao một trong hai lần xuất hiện của `15` bị thay bởi `20`.

### Bài 2. Biên của top-K

Với đầu vào `[8, 1, 8]`, chạy hàm với K = 0, 1, 3, 5. Kết quả phải lần lượt là `[]`, `[8]`, `[8, 8, 1]`, `[8, 8, 1]`. Với K = -1, xác minh hàm ném `IllegalArgumentException` và mảng đầu vào không thay đổi.

### Bài 3. Trộn ưu tiên và thứ tự đến

Thêm A (đến 0, ưu tiên 2), B (đến 1, ưu tiên 4), C (đến 2, ưu tiên 4), D (đến 3, ưu tiên 1), E (đến 4, ưu tiên 2). Trước khi chạy, dự đoán chuỗi `poll()` là **B, C, A, E, D**. Sau khi chạy, giải thích hai cặp bằng ưu tiên B/C và A/E.

### Bài 4. Thêm hạn xử lý

Bổ sung trường `deadline` cho tác vụ. Yêu cầu mới: **mức ưu tiên giảm dần → hạn xử lý sớm hơn → thứ tự nhận tăng dần**. Hãy sửa comparator và tạo trường hợp ba tác vụ cùng ưu tiên, có hai hạn bằng nhau, để kiểm tra cả hai tiêu chí phụ. Đừng dùng đối tượng có deadline có thể bị thay đổi bên trong heap.

### Bài 5. Chọn cấu trúc khi dữ liệu rất lớn

Với n = 1.000.000 điểm và K = 10, so sánh lượng bộ nhớ cần giữ giữa việc sắp xếp toàn bộ bản sao mảng và min-heap giới hạn K. Nêu vì sao bước sắp xếp cuối cùng của chỉ 10 kết quả vẫn cần thiết nếu hợp đồng yêu cầu thứ tự giảm dần.

## 10. Checklist đánh giá lời giải

- Đề bài xác định rõ K lớn nhất/nhỏ nhất, có trùng hay phân biệt, và thứ tự xuất kết quả.
- Thuật toán top-K giữ đúng bất biến K ứng viên tốt nhất sau từng phần tử.
- Heap không vượt K phần tử; nhánh K = 0 và mảng rỗng được xử lý an toàn.
- Danh sách kết quả top-K được sắp giảm dần, không dựa vào thứ tự iterator của heap.
- Comparator tác vụ có cả ưu tiên chính và tie-break phản ánh yêu cầu.
- Mỗi tác vụ có số thứ tự đến xác định; không sửa các khóa sắp xếp khi tác vụ còn trong heap.
- Đã thử đầu vào trùng, K vượt N, nhiều tác vụ cùng ưu tiên và hàng đợi rỗng.
- Phân tích thời gian/bộ nhớ phản ánh đúng n, K và cấu trúc phụ thực sự sử dụng.

Khi hiểu điều kiện “phần tử nào phải đứng đầu” và quy tắc bất biến, bạn có thể dùng cùng một `PriorityQueue` để giữ nhóm K ứng viên tốt nhất hoặc lấy tác vụ cần xử lý tiếp theo, đồng thời kiểm chứng được tính đúng của cả hai giải pháp.