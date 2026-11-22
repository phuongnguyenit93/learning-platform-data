# Trộn nhiều đường và lựa chọn phần tử bằng heap

**Chủ đề:** Computer Science Algorithms · Ngoài bộ nhớ

## 1. Mục tiêu của bài học

Một tập log hoặc dữ liệu giao dịch có thể chứa hàng tỷ bản ghi, lớn hơn RAM của một máy. Ta cần sắp xếp, hợp nhất và chọn những phần tử nhỏ nhất mà **không đọc toàn bộ dữ liệu vào bộ nhớ**. Đây là tình huống điển hình của thuật toán **ngoài bộ nhớ (external-memory algorithm)**.

Phương pháp **trộn nhiều đường (k-way merge)** kết hợp nhiều luồng dữ liệu **đã được sắp xếp**. Một **min-heap** chỉ chứa phần tử đầu chưa dùng của mỗi nguồn. Sau mỗi lần lấy phần tử nhỏ nhất, thuật toán chỉ đọc thêm từ chính nguồn vừa xuất phần tử.

Ba năng lực quan trọng:
1. **Merge:** tạo một luồng đã sắp từ k luồng đầu vào đã sắp.
2. **External merge sort:** chia dữ liệu lớn thành các **sorted runs** vừa RAM, sau đó merge nhiều lượt cho đến khi chỉ còn một run.
3. **Selection:** chọn **Top K nhỏ nhất** hoặc **phần tử thứ r** từ các run đã sắp, có thể dừng trước khi đọc hết dữ liệu.

Bài này giải thích chứng minh đúng, số phép so sánh, chi phí I/O theo block, fan-in và ngân sách bộ nhớ, xử lý duplicate/EOF, sự khác biệt giữa Top K từ sorted và unsorted streams, rồi cung cấp **một chương trình Java 17 hoàn chỉnh sử dụng file I/O thật**.

## 2. Thuật ngữ cơ bản

| Khái niệm | Ý nghĩa |
|---|---|
| Record | Bản ghi có khóa để so sánh |
| Sorted run | File/dãy các record đã sắp theo một comparator thống nhất |
| Head | Phần tử đầu tiên chưa xuất của một run |
| k-way merge | Gộp đồng thời k run đã sắp |
| Fan-in | Số run tối đa được mở làm input trong một merge group |
| Initial run | Run được sort từ một chunk đầu vào vừa RAM |
| Merge pass | Lượt biến nhiều run thành ít run hơn |
| Input buffer | Vùng RAM đọc trước từ một nguồn |
| Output buffer | Vùng RAM tích lũy bản ghi trước khi ghi |
| Min-heap | Cấu trúc dữ liệu tìm và lấy head nhỏ nhất |
| EOF | File đã hết dữ liệu, không có head mới |
| Top K | K bản ghi đầu theo thứ tự toàn cục |
| Rank r | Bản ghi thứ r, **đánh số từ 1** trong bài này |

Một **run đã sắp** là tiền điều kiện. Nếu một nguồn còn giá trị nhỏ hơn nằm ở phía sau head hiện tại, heap một head mỗi nguồn không thể chọn đúng phần tử nhỏ nhất toàn cục.

### 2.1. Ví dụ ba nguồn đã sắp

~~~text
Run 0: [1, 4, 7]
Run 1: [2, 5, 8]
Run 2: [1, 3, 9]
~~~

Output đúng theo khóa tăng:

~~~text
[1, 1, 2, 3, 4, 5, 7, 8, 9]
~~~

Phần tử bằng nhau phải có quy tắc tie-breaking nếu ứng dụng yêu cầu **sắp xếp ổn định (stable sort)**.

## 3. Thuật toán k-way merge bằng min-heap

Đặt k là số run đang mở, N là tổng số record của các run ấy.

**Khởi tạo:**
- Mở một reader cho từng run, trong phạm vi fan-in đã cho.
- Đọc record đầu tiên của mỗi run không rỗng.
- Đưa **Head(record,runId)** vào min-heap.

**Vòng lặp:**
1. Lấy head có khóa nhỏ nhất trên heap.
2. Ghi record đó ra output hoặc chuyển cho consumer.
3. Chỉ đọc record kế tiếp từ **cùng runId**.
4. Nếu chưa EOF, đưa head mới của run ấy lên heap.
5. Nếu đã EOF, không đưa thêm gì.
6. Dừng khi heap rỗng hoặc đã lấy đủ số record yêu cầu.

Pseudocode:

~~~text
heap = empty min-heap
for runId in 0 .. k-1:
    head = readNext(runId)
    if head exists:
        heap.push(head, runId)

while heap not empty and have not reached output limit:
    (record, runId) = heap.popMin()
    emit(record)
    next = readNext(runId)
    if next exists:
        heap.push(next, runId)
~~~

Heap chỉ chứa **tối đa một head cho một run**. Không bao giờ đưa cả một run vào heap.

### 3.1. Chứng minh đúng bằng bất biến

Bất biến trước mỗi lần pop:

> Với mỗi run chưa cạn, heap có đúng một phần tử đầu tiên chưa xuất từ run đó, và không có record nào khác của run trong heap.

Mỗi run đã sorted, nên mọi record phía sau head đều **không nhỏ hơn** head ấy. Do đó giá trị nhỏ nhất trong tất cả các record chưa xuất phải nằm trong **một trong các head**. Heap chọn head nhỏ nhất, chính là record nhỏ nhất tiếp theo của toàn bộ hợp các run.

Sau khi pop head từ run j, chỉ run j đổi phần tử đầu chưa xuất. Đọc next của chính j rồi push sẽ khôi phục bất biến; các head khác không đổi. Khi heap rỗng, mọi run đều cạn và output đã chứa đủ mọi record theo thứ tự.

Chứng minh này không dựa vào kích thước run, số record trùng hay vị trí lưu trữ trong RAM/đĩa; nó chỉ cần **mỗi run đã sorted theo cùng một comparator**.

### 3.2. Xử lý run rỗng và EOF

Không dùng số đặc biệt như -1 hoặc Long.MAX_VALUE để biểu diễn EOF: chúng có thể là **giá trị dữ liệu thật**. Hàm đọc trả một trạng thái không có record, chẳng hạn null sau khi reader.readLine() trả null. Nếu run rỗng ngay từ đầu, bỏ qua nó, không push node giả.

Khi chỉ còn một run chưa cạn, heap vẫn có một head và tiếp tục phát tuần tự. Với k=0, output rỗng. Với k=1, về lý thuyết có thể stream-copy không cần heap.

## 4. Độ phức tạp tính toán của heap

Với k≥2:
- Khởi tạo k head bằng k lần add: **O(k log k)**; có thể đạt O(k) nếu heapify một lần.
- Mỗi trong N record được poll đúng một lần.
- Sau mỗi poll có nhiều nhất một head mới được add.
- Mỗi poll/add mất O(log k).

Do đó:

\[
T_{\mathrm{CPU}}=O(k\log k+N\log k).
\]

Khi N≥k, biểu thức thường được rút gọn thành **O(N log k)**. Nếu k là hằng số nhỏ, một lần merge gần như tuyến tính theo N về số phép so.

So với cách quét tuyến tính k head mỗi lần để tìm nhỏ nhất, O(Nk), heap hữu ích khi fan-in lớn. Một số thư viện dùng **loser tree / tournament tree** để giảm hằng số phép so; độ phức tạp tương tự, không tự động nhanh hơn PriorityQueue trong mọi runtime.

**Không nhầm:** O(N log k) là chi phí thao tác heap của **một lượt merge**, không phải toàn bộ quá trình external sort với nhiều lượt đọc/ghi đĩa.

## 5. Vì sao phải có fan-in và bộ đệm I/O?

Trong external memory, dữ liệu nằm trên SSD/HDD. Đọc một byte đơn lẻ theo hàng tỷ lần thường kém hiệu quả hơn đọc liên tiếp các block. Một k-way merge sử dụng:
- k **input buffers**, thường mỗi run có một buffer kích thước khoảng B byte.
- Một **output buffer** để ghi tuần tự.
- Một min-heap tối đa k heads.
- Metadata của các reader và file descriptors.
- Bộ nhớ runtime cho parser/record.

Nếu RAM dành cho merge là M byte thì một điều kiện ngân sách đơn giản:

\[
kB+B+\operatorname{heapBytes}(k)+\operatorname{overhead}\le M.
\]

Đây chỉ là **bất đẳng thức định hướng thiết kế**: không thể đặt k=M/B mà bỏ qua output buffer, heap và overhead.

Hệ điều hành có giới hạn **open file descriptors**. Nếu fan-in cấu hình là 3 mà chương trình mở cả 4 input run, thuật toán vẫn có thể trả đáp án đúng trên dữ liệu nhỏ nhưng **đã vi phạm ràng buộc vận hành**.

### 5.1. Những bộ nhớ không được bỏ quên

Heap O(k) head không có nghĩa **toàn bộ chương trình O(k) RAM**:
- Danh sách tên của R run chiếm **O(R)** metadata nếu giữ trong RAM.
- API Top K trả list K records có thêm **O(K)**.
- BufferedReader có thể đọc trước một buffer từ mỗi file.
- Sort chunk ban đầu cần **O(C)** records nếu mỗi chunk chứa C record.
- Nhiều merge jobs song song nhân các ngân sách reader/heap/buffer.

Bản demo giữ danh sách Path của run cho dễ hiểu; nếu hàng triệu run, có thể dùng **manifest trên đĩa** hoặc xử lý metadata theo lô. Kích thước run không giới hạn dung lượng heap, nhưng số run thì có.

## 6. External merge sort: tạo và hợp nhất các run

### 6.1. Giai đoạn tạo initial runs

Cho file input chứa N record và RAM cho phép sort tối đa **C record/lần**:

1. Đọc tối đa C record.
2. Sort chunk trong RAM.
3. Ghi chunk đã sắp thành một run trên đĩa.
4. Xóa chunk trong RAM và tiếp tục phần sau.
5. Nếu chunk cuối ít hơn C record, vẫn sort và ghi nó.

Số initial runs là:

\[
\boxed{R_0=\lceil N/C\rceil}.
\]

Nếu N=0 thì R0=0; đầu ra cuối cũng rỗng. Nếu N≤C và N>0 thì chỉ có một run, **không cần merge pass nào**.

### 6.2. Giai đoạn trộn các run theo pass

Trong một pass có R run:
- Chia các run thành nhóm tối đa k run.
- Mỗi nhóm được merge thành một run mới đã sorted.
- Nhóm cuối có thể ít hơn k; vẫn xử lý đúng.
- Sau khi các output run đã hoàn tất, chuyển sang pass tiếp theo.

Số run sau một pass không vượt:

\[
R_{\rm next}=\lceil R/k\rceil.
\]

Với k≥2, khi R>1, số run giảm; khi còn một run thì kết thúc. Giới hạn fan-in=1 làm số run không giảm, nên code phải **từ chối** nếu muốn merge nhiều run.

Nếu R0>1, số pass kiểu gom tối đa k nhóm:

\[
\boxed{P=\lceil\log_k R_0\rceil}.
\]

Với R0≤1, đặt P=0. Công thức giả định mỗi pass gom các run theo fan-in tối đa; việc nhóm một run cuối vẫn tính là một output của pass đó.

### 6.3. Ví dụ bốn run, fan-in ba

Cho N=14 record, chunk C=4:

\[
R_0=\lceil14/4\rceil=4.
\]

Các run có kích thước 4,4,4,2. Với fan-in k=3:
- **Pass 1:** nhóm ba run đầu thành một run, nhóm cuối thành run riêng → **2 runs**.
- **Pass 2:** trộn 2 runs còn lại → **1 run**.
- Tổng merge passes = **2**.

\[
\lceil\log_3 4\rceil=2.
\]

Nếu đủ RAM và file descriptors cho k=4, có thể gộp cả bốn run trong **một pass**. Fan-in lớn làm giảm số pass nhưng tăng số buffers và descriptors. Đây là một đánh đổi cốt lõi của thuật toán ngoài bộ nhớ.

## 7. Phân tích I/O theo block

Phải phân biệt **byte** và **record** trong công thức:
- N là số records.
- B ở phần này là **số records/block**.
- C là **số records có thể sort trong RAM**.
- R0=ceil(N/C), k là fan-in.

Giai đoạn tạo run cần đọc N records và ghi N records, khoảng **2N/B block I/O** theo mô hình lý tưởng. Mỗi merge pass đầy đủ đọc và ghi mỗi record một lần, thêm khoảng **2N/B block I/O**.

Vậy số block I/O theo bậc tăng trưởng là:

\[
\boxed{
O\left(\frac NB\left(1+\lceil\log_k R_0\rceil\right)\right)
}
\]

khi R0>1, cùng các giả định về block/buffer và fan-in; nếu R0≤1 thì không có merge passes.

Hệ số 2 từ đọc + ghi thường được lược bỏ trong ký hiệu O. Thời gian thực còn chịu ảnh hưởng filesystem, SSD throughput, page cache, số thread, hằng số parsing và tình trạng bộ nhớ.

Trong mô hình external-memory chuẩn, với M records trong RAM và B records/block, fan-in có thể tỷ lệ khoảng M/B (trừ output buffer và overhead). External merge sort đạt cận I/O quen thuộc:

\[
O\left(\frac NB
\left(1+\log_{M/B}\frac NB\right)\right)
\]

trên miền tham số thích hợp.

**Không gộp ba cận khác nhau:**
- **O(N log k):** so sánh/heap operations của một merge pass.
- **O(N/B):** đọc/ghi theo block trong một pass.
- **O((N/B)(1+P)):** tổng I/O của quá trình gồm tạo run và P merge passes.

### 7.1. Tính I/O cho Top K

Nếu k run đã sorted và có thể mở trong fan-in, chọn Top K không nhất thiết đọc hết N. Trong điều kiện đọc theo block, còn phải tính **ít nhất các block đầu của những nguồn đã mở**, cộng các block đọc tiếp khi phát K records.

Một biểu thức lý tưởng mang tính tham khảo là **O(k+K/B)** block reads, nhưng filesystem có thể prefetch thêm; không có bảo đảm K records đồng nghĩa K/B blocks thực tế trên mọi môi trường. Nếu trước selection cần giảm quá nhiều run bằng pass trung gian, phải tính thêm I/O các pass đó.

## 8. Tính ổn định với những khóa bằng nhau

Trong nhiều ứng dụng, record gồm **khóa và payload**. Khi sort stable, các record có khóa bằng nhau phải giữ thứ tự xuất hiện **trong input gốc**.

Bài demo lưu mỗi record dạng:

~~~text
key@originalIndex
7@0, 1@1, 4@2, 1@3, 9@4, 2@5, 6@6,
2@7, 5@8, 8@9, 3@10, 1@11, 0@12, 5@13
~~~

Comparator toàn cục:
1. So **key tăng dần**.
2. Nếu key bằng, so **originalIndex tăng dần**.
3. Khi hoàn toàn bằng nhau, dùng runId làm tie-breaker deterministic; với ordinal duy nhất, trường hợp này không xuất hiện.

Vậy các record có key=1 xuất theo ordinal **1,3,11**, dù nằm ở những initial runs khác nhau.

### 8.1. Vì sao phải lưu ordinal?

Chỉ so key trong PriorityQueue không bảo đảm thứ tự của những record có key bằng nhau. Một thiết kế có thể dùng thứ tự run để giữ stability nếu các run luôn tương ứng các đoạn liên tiếp của input và metadata được duy trì nhất quán. Nhưng khi merge nhiều pass, điều phối lại nhóm có thể làm lập luận phức tạp.

Lưu **original ordinal** xuyên suốt mọi run và pass cung cấp một thứ tự tổng rõ ràng và dễ kiểm tra. Đổi lại, record trên đĩa cần thêm metadata.

### 8.2. Lỗi comparator khi dùng long

Tránh:

~~~java
return (int) (a.value() - b.value());
~~~

Trừ long có thể overflow; ép int còn cắt bớt bit. Dùng **Long.compare** hoặc **Comparator.comparingLong**.

Ví dụ nếu input có cả Long.MIN_VALUE và Long.MAX_VALUE, comparator dựa vào phép trừ có thể đổi dấu sai, làm output không sorted dù heap implementation đúng.

## 9. Chọn Top K và phần tử thứ r

### 9.1. Top K nhỏ nhất

Khi k run đã sorted:
- Khởi tạo min-heap bằng heads.
- Pop min K lần hoặc cho tới khi hết dữ liệu.
- Mỗi lần pop, refill head từ đúng run đó.
- Trả list kết quả hoặc stream trực tiếp.

CPU:

\[
O(k\log k+K\log k)
\]

với khởi tạo bằng k lần add. Bộ nhớ heap O(k); nếu trả **list K record**, phải tính thêm O(K). Nếu chỉ in/ghi trực tiếp, có thể tránh lưu K records trong RAM.

Top K có thể định nghĩa:
- K=0 → list rỗng.
- K>N → trả toàn bộ N records.
- K âm → từ chối.

### 9.2. Phần tử thứ r (rank 1-based)

Để tìm record ở vị trí thứ r:
1. Kiểm r>0.
2. Pop r record theo thứ tự.
3. Chỉ giữ **record vừa pop cuối cùng**.
4. Nếu heap cạn trước lượt r, báo không tồn tại.

Không cần giữ cả r records. CPU O(k log k+r log k), bộ nhớ trạng thái O(k) heads + I/O buffers, ngoài một record kết quả.

Với output:

~~~text
[0, 1, 1, 1, 2, 2, 3, 4, 5, 5, 6, 7, 8, 9]
~~~

- Rank 1 = 0.
- Rank 2,3,4 có key=1, nhưng là **ba record khác nhau**.
- Rank 7 = 3.
- Rank 15 không tồn tại vì N=14.

### 9.3. Distinct rank khác record rank

Nếu hỏi **phần tử phân biệt thứ r**, phải bỏ qua các khóa trùng sau khi merge. Khi có nhiều duplicate, để lấy r giá trị phân biệt có thể phải pop **nhiều hơn r record**. Vì vậy cận O(r log k) cho record rank không tự áp dụng cho distinct rank.

Tương tự, **Top K largest** từ các run tăng dần không giải được chỉ bằng đổi min-heap thành max-heap nhưng vẫn đọc phần tử **đầu** của mỗi run. Muốn largest cần luồng giảm dần, đọc lùi có hỗ trợ, hoặc phương pháp khác.

## 10. Chọn phần tử khi có quá nhiều run

Ví dụ có **4 initial runs nhưng chỉ được mở tối đa 3 input files**. Muốn Top 5 của tất cả các run, không được mở bốn readers rồi nói rằng fan-in vẫn bằng 3.

Hai hướng hợp lệ:
- Trộn một hoặc nhiều pass để số run còn ≤3, rồi dùng heap trực tiếp chọn Top K.
- Dùng cây trộn nhiều tầng có buffers, phải phân tích tổng bộ nhớ, file descriptors và I/O của tất cả các tầng.

Demo Java dùng hướng thứ nhất:
1. Bốn initial runs.
2. Merge pass 1 làm còn **hai runs**.
3. Chọn Top 5 và rank 7 từ **hai input readers**.
4. Merge pass 2 tạo output cuối.

Selection trả kết quả đúng và đồng thời **tuân thủ giới hạn fan-in**.

## 11. Java PriorityQueue và file streams

Java 17 có **java.util.PriorityQueue**:
- poll lấy record nhỏ nhất theo comparator.
- add/poll thường O(log k).
- peek O(1).
- Không ổn định tự động cho các phần tử có cùng khóa nếu comparator không phân biệt chúng.
- Iterator không bảo đảm duyệt theo thứ tự đã sắp.
- Không thay đổi khóa của node đã có trong heap mà không remove/reinsert.

Một node trong demo là **Head(Entry,runId)**. Entry có value và ordinal. Khi pop Head của run j, code đọc tiếp từ **reader j**, không đọc nhầm reader của run khác.

File input là mỗi dòng một số long. File run trung gian là mỗi dòng:

~~~text
value,originalIndex
~~~

Ví dụ:

~~~text
1,1
1,3
4,2
7,0
~~~

Các dòng này đã sorted theo (value,originalIndex). Reader của từng run chỉ cần đọc **một dòng kế tiếp mỗi lần heap yêu cầu**, còn BufferedReader tự quản lý buffer.

### 11.1. Giới hạn của demo so với production

Chương trình:
- Có I/O tệp thật, không dùng Files.readAllLines trong pipeline.
- Sort từng chunk C và đọc theo stream.
- Giữ tối đa fan-in reader ở mỗi nhóm.
- Giữ danh sách Path các run trong RAM, phù hợp demo và bộ dữ liệu vừa phải.
- Dùng text format UTF-8, có overhead parsing và dung lượng lớn hơn binary.
- Chỉ dùng in-memory oracle ở **test nhỏ**, không phải trong external sort production.
- Tạo thư mục tạm và xóa sau demo.

Hệ thống production cần thêm manifest, crash recovery, checksum, atomic commit/staging, quản lý nhiều merge jobs song song và kiểm soát giới hạn file descriptors. Bản demo **không** được mô tả như một external sorting service production-ready.

## 12. Java 17 hoàn chỉnh: file-based k-way merge và selection

Lưu tệp **ExternalKWayMergeDemo.java**. Toàn bộ mã độc lập, chỉ sử dụng Java standard library.

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.Random;
import java.util.stream.Stream;

public final class ExternalKWayMergeDemo {
    private ExternalKWayMergeDemo() {
    }

    // Original ordinal maintains stable order across all passes.
    public record Entry(long value, long ordinal) {
        @Override
        public String toString() {
            return value + "@" + ordinal;
        }
    }

    private record Head(Entry record, int runId) {
    }

    private static final Comparator<Entry> ENTRY_ORDER =
            Comparator.comparingLong(Entry::value)
                    .thenComparingLong(Entry::ordinal);

    private static final Comparator<Head> HEAD_ORDER =
            Comparator.comparingLong(
                    (Head h) -> h.record().value())
                    .thenComparingLong(
                    h -> h.record().ordinal())
                    .thenComparingInt(Head::runId);

    @FunctionalInterface
    private interface EntrySink {
        void accept(Entry entry) throws IOException;
    }

    // Own and close all readers, including on partial open errors.
    private static final class ReaderGroup implements AutoCloseable {
        final List<BufferedReader> readers = new ArrayList<>();

        ReaderGroup(List<Path> files) throws IOException {
            try {
                for (Path file : files) {
                    readers.add(Files.newBufferedReader(
                            file, StandardCharsets.UTF_8));
                }
            } catch (IOException | RuntimeException failure) {
                try {
                    close();
                } catch (IOException closing) {
                    failure.addSuppressed(closing);
                }
                throw failure;
            }
        }

        @Override
        public void close() throws IOException {
            IOException first = null;
            for (BufferedReader reader : readers) {
                try {
                    reader.close();
                } catch (IOException failure) {
                    if (first == null) {
                        first = failure;
                    } else {
                        first.addSuppressed(failure);
                    }
                }
            }
            if (first != null) {
                throw first;
            }
        }
    }

    private static Entry readEntry(BufferedReader reader)
            throws IOException {
        String line = reader.readLine();
        if (line == null) {
            return null;
        }

        int comma = line.indexOf(',');
        if (comma <= 0 || comma == line.length() - 1
                || line.indexOf(',', comma + 1) >= 0) {
            throw new IOException("Malformed sorted-run record");
        }

        try {
            long value = Long.parseLong(
                    line.substring(0, comma));
            long ordinal = Long.parseLong(
                    line.substring(comma + 1));
            return new Entry(value, ordinal);
        } catch (NumberFormatException malformed) {
            throw new IOException(
                    "Invalid numeric sorted-run record", malformed);
        }
    }

    private static void writeEntry(
            BufferedWriter writer, Entry entry)
            throws IOException {
        writer.write(Long.toString(entry.value()));
        writer.write(',');
        writer.write(Long.toString(entry.ordinal()));
        writer.newLine();
    }

    // Shared streaming logic: merge all, Top K, or rank r.
    // Only one heap head per nonempty run.
    private static long consumeMerged(
            List<Path> runs, long limit, EntrySink sink)
            throws IOException {
        Objects.requireNonNull(runs, "runs");
        Objects.requireNonNull(sink, "sink");
        if (limit < 0) {
            throw new IllegalArgumentException(
                    "Limit must be nonnegative");
        }
        if (limit == 0 || runs.isEmpty()) {
            return 0;
        }

        try (ReaderGroup group = new ReaderGroup(runs)) {
            PriorityQueue<Head> heap =
                    new PriorityQueue<>(HEAD_ORDER);

            for (int i = 0; i < group.readers.size(); i++) {
                Entry first = readEntry(group.readers.get(i));
                if (first != null) {
                    heap.add(new Head(first, i));
                }
            }

            long emitted = 0;
            while (emitted < limit && !heap.isEmpty()) {
                Head head = heap.poll();
                sink.accept(head.record());
                emitted++;

                Entry next = readEntry(
                        group.readers.get(head.runId()));
                if (next != null) {
                    heap.add(new Head(next, head.runId()));
                }
            }
            return emitted;
        }
    }

    // K=0 -> empty; K>N -> all N records.
    public static List<Entry> firstK(
            List<Path> sortedRuns, int k) throws IOException {
        if (k < 0) {
            throw new IllegalArgumentException(
                    "K must be nonnegative");
        }
        List<Entry> result = new ArrayList<>();
        consumeMerged(sortedRuns, k, result::add);
        return result;
    }

    // 1-based rank, duplicates count as separate records.
    // No list of rank entries is retained in RAM.
    public static Entry selectRank(
            List<Path> sortedRuns, long rank)
            throws IOException {
        if (rank <= 0) {
            throw new IllegalArgumentException(
                    "Rank must be positive and 1-based");
        }

        Entry[] last = new Entry[1];
        long emitted = consumeMerged(
                sortedRuns, rank, entry -> last[0] = entry);

        if (emitted < rank) {
            throw new NoSuchElementException(
                    "Rank exceeds record count");
        }
        return last[0];
    }

    private static Path writeSortedChunk(
            List<Entry> chunk, Path work, int runId)
            throws IOException {
        chunk.sort(ENTRY_ORDER);
        Path run = work.resolve("run-" + runId + ".txt");

        try (BufferedWriter writer = Files.newBufferedWriter(
                run, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE)) {
            for (Entry entry : chunk) {
                writeEntry(writer, entry);
            }
        }
        return run;
    }

    // Input: exactly one long integer per line.
    // Pipeline only retains chunkRecords entries here.
    public static List<Path> createInitialRuns(
            Path input, Path work, int chunkRecords)
            throws IOException {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(work, "work");
        if (chunkRecords <= 0) {
            throw new IllegalArgumentException(
                    "Chunk size must be positive");
        }

        List<Path> runs = new ArrayList<>();
        List<Entry> chunk = new ArrayList<>(chunkRecords);
        long ordinal = 0;

        try (BufferedReader reader = Files.newBufferedReader(
                input, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                long value = Long.parseLong(line.trim());
                chunk.add(new Entry(value, ordinal));
                ordinal = Math.addExact(ordinal, 1);

                if (chunk.size() == chunkRecords) {
                    runs.add(writeSortedChunk(
                            chunk, work, runs.size()));
                    chunk.clear();
                }
            }
        }

        if (!chunk.isEmpty()) {
            runs.add(writeSortedChunk(
                    chunk, work, runs.size()));
        }
        return runs;
    }

    private static void mergeGroup(
            List<Path> group, Path output)
            throws IOException {
        try (BufferedWriter writer = Files.newBufferedWriter(
                output, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE)) {
            consumeMerged(group, Long.MAX_VALUE,
                    entry -> writeEntry(writer, entry));
        }
    }

    // At most fanIn input readers in any merge group.
    public static List<Path> mergeOnePass(
            List<Path> runs, Path work,
            int fanIn, int passNo) throws IOException {
        Objects.requireNonNull(runs, "runs");
        Objects.requireNonNull(work, "work");
        if (fanIn < 2 || passNo <= 0) {
            throw new IllegalArgumentException(
                    "fanIn >= 2 and passNo >= 1 required");
        }

        List<Path> next = new ArrayList<>();
        for (int start = 0;
                start < runs.size(); start += fanIn) {
            int end = Math.min(start + fanIn, runs.size());
            Path output = work.resolve(
                    "pass-" + passNo
                    + "-group-" + next.size() + ".txt");
            mergeGroup(runs.subList(start, end), output);
            next.add(output);
        }

        // Only delete old run files after the new pass is built.
        for (Path previous : runs) {
            Files.delete(previous);
        }
        return next;
    }

    // Loads demo-sized output for testing ONLY, not sorting.
    private static List<Entry> readSmallDemoOutput(Path file)
            throws IOException {
        List<Entry> result = new ArrayList<>();
        try (BufferedReader reader = Files.newBufferedReader(
                file, StandardCharsets.UTF_8)) {
            Entry entry;
            while ((entry = readEntry(reader)) != null) {
                result.add(entry);
            }
        }
        return result;
    }

    private static List<Entry> inMemoryOracle(long[] source) {
        List<Entry> result = new ArrayList<>();
        for (int i = 0; i < source.length; i++) {
            result.add(new Entry(source[i], i));
        }
        result.sort(ENTRY_ORDER);
        return result;
    }

    private static void writeInput(Path input, long[] source)
            throws IOException {
        List<String> lines = new ArrayList<>();
        for (long value : source) {
            lines.add(Long.toString(value));
        }
        Files.write(input, lines, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE);
    }

    private static void require(boolean ok, String reason) {
        if (!ok) {
            throw new AssertionError(reason);
        }
    }

    // 60 tiny file-based regression cases with a RAM oracle.
    private static int selfTest(Path root) throws IOException {
        Random random = new Random(5142026L);

        for (int test = 0; test < 60; test++) {
            Path work = Files.createDirectory(
                    root.resolve("case-" + test));
            Path input = work.resolve("input.txt");
            Path output = work.resolve("output.txt");

            int n = random.nextInt(21);
            long[] a = new long[n];
            for (int i = 0; i < n; i++) {
                a[i] = random.nextInt(21) - 10;
            }
            int chunk = 1 + random.nextInt(6);
            int fanIn = 2 + random.nextInt(4);

            writeInput(input, a);
            List<Path> runs = createInitialRuns(
                    input, work, chunk);
            List<Entry> expected = inMemoryOracle(a);
            int pass = 0;

            while (runs.size() > fanIn) {
                runs = mergeOnePass(
                        runs, work, fanIn, ++pass);
            }

            int k = Math.min(n, 3);
            require(
                    firstK(runs, k).equals(
                            expected.subList(0, k)),
                    "Top K mismatch");

            if (n > 0) {
                require(
                        selectRank(runs, n).equals(
                                expected.get(n - 1)),
                        "Rank mismatch");
            }

            while (runs.size() > 1) {
                runs = mergeOnePass(
                        runs, work, fanIn, ++pass);
            }

            if (runs.isEmpty()) {
                Files.writeString(
                        output, "",
                        StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE);
            } else {
                Files.move(runs.get(0), output);
            }

            require(
                    readSmallDemoOutput(output).equals(expected),
                    "Stable external sort mismatch");
        }
        return 60;
    }

    private static void deleteTree(Path root)
            throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            for (Path path : paths.sorted(
                    Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    public static void main(String[] args)
            throws IOException {
        Path work = Files.createTempDirectory(
                "external-kway-");

        try {
            long[] inputValues = {
                7, 1, 4, 1, 9, 2, 6,
                2, 5, 8, 3, 1, 0, 5
            };
            Path input = work.resolve("input.txt");
            Path output = work.resolve("sorted.txt");
            writeInput(input, inputValues);

            int chunkSize = 4;
            int fanIn = 3;
            List<Path> runs = createInitialRuns(
                    input, work, chunkSize);

            int initialRuns = runs.size();
            int mergePasses = 0;

            // Selection may open at most fanIn readers.
            while (runs.size() > fanIn) {
                runs = mergeOnePass(
                        runs, work, fanIn, ++mergePasses);
            }

            System.out.println(
                    "Records: " + inputValues.length);
            System.out.println(
                    "Initial runs: " + initialRuns);
            System.out.println(
                    "Runs within fan-in: " + runs.size());

            System.out.println(
                    "Top 5: " + firstK(runs, 5));
            System.out.println(
                    "Rank 7: " + selectRank(runs, 7));
            System.out.println(
                    "Rank 1: " + selectRank(runs, 1));
            System.out.println(
                    "Top 0: " + firstK(runs, 0));

            try {
                selectRank(runs, 15);
                System.out.println(
                        "Rank 15 rejected: false");
            } catch (NoSuchElementException expected) {
                System.out.println(
                        "Rank 15 rejected: true");
            }

            while (runs.size() > 1) {
                runs = mergeOnePass(
                        runs, work, fanIn, ++mergePasses);
            }
            if (runs.isEmpty()) {
                Files.writeString(
                        output, "",
                        StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE);
            } else {
                Files.move(runs.get(0), output);
            }

            List<Entry> sorted = readSmallDemoOutput(output);
            List<Long> keys = new ArrayList<>();
            List<Long> origins = new ArrayList<>();
            for (Entry entry : sorted) {
                keys.add(entry.value());
                origins.add(entry.ordinal());
            }

            System.out.println(
                    "Merge passes: " + mergePasses);
            System.out.println("Sorted values: " + keys);
            System.out.println(
                    "Original indices: " + origins);
            System.out.println(
                    "Stable output matches oracle: "
                    + sorted.equals(
                            inMemoryOracle(inputValues)));

            Path empty = work.resolve("empty.txt");
            Files.writeString(
                    empty, "",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);
            System.out.println(
                    "Empty input runs: "
                    + createInitialRuns(
                        empty, work, chunkSize).size());

            try {
                mergeOnePass(
                        List.of(), work, 1, 1);
                System.out.println(
                        "Fan-in 1 rejected: false");
            } catch (IllegalArgumentException expected) {
                System.out.println(
                        "Fan-in 1 rejected: true");
            }

            try {
                selectRank(List.of(), 0);
                System.out.println(
                        "Rank 0 rejected: false");
            } catch (IllegalArgumentException expected) {
                System.out.println(
                        "Rank 0 rejected: true");
            }

            System.out.println(
                    "Self-test: " + selfTest(work)
                    + " cases PASS");
        } finally {
            deleteTree(work);
        }
    }
}
~~~

### 12.1. Biên dịch và chạy

Dùng **JDK 17 hoặc mới hơn**. Lưu chính xác tên file **ExternalKWayMergeDemo.java**, sau đó:

~~~bash
javac -encoding UTF-8 ExternalKWayMergeDemo.java
java ExternalKWayMergeDemo
~~~

**Stdout dự kiến:**

~~~text
Records: 14
Initial runs: 4
Runs within fan-in: 2
Top 5: [0@12, 1@1, 1@3, 1@11, 2@5]
Rank 7: 3@10
Rank 1: 0@12
Top 0: []
Rank 15 rejected: true
Merge passes: 2
Sorted values: [0, 1, 1, 1, 2, 2, 3, 4, 5, 5, 6, 7, 8, 9]
Original indices: [12, 1, 3, 11, 5, 7, 10, 2, 8, 13, 6, 0, 9, 4]
Stable output matches oracle: true
Empty input runs: 0
Fan-in 1 rejected: true
Rank 0 rejected: true
Self-test: 60 cases PASS
~~~

### 12.2. Phân tích output

**Records 14 / initial runs 4:** input có 14 dòng, chunkSize=4 tạo 4 run, dung lượng 4,4,4,2.

**Runs within fan-in 2:** sau merge pass đầu 4→2, Top 5 và rank 7 chỉ mở hai readers, không vượt fan-in=3.

**Top 5:** lấy năm record đầu của thứ tự tăng, kết quả 0@12, 1@1, 1@3, 1@11, 2@5; ba record có khóa 1 giữ đúng thứ tự ordinal 1,3,11.

**Rank 7:** bảy phần tử đầu lần lượt có khóa 0,1,1,1,2,2,3; record thứ bảy là 3@10. Rank đếm **cả duplicate**.

**Rank 15 rejected:** dữ liệu chỉ có 14 record. selectRank ném NoSuchElementException theo hợp đồng; không trả giá trị giả.

**Merge passes 2:** lượt đầu 4→2, lượt tiếp theo 2→1. Output cuối có đủ 14 record.

**Original indices:** các ordinal của record cùng khóa tăng dần; kết quả khớp oracle sort theo (value,ordinal).

**Empty input runs 0:** file rỗng không tạo run nào.

**Fan-in 1 rejected / Rank 0 rejected:** kiểm điều kiện đầu vào, tránh vòng lặp không giảm số run hoặc rank 1-based không hợp lệ.

**Self-test 60 cases PASS:** các trường hợp nhỏ bao gồm data rỗng, số âm, duplicate, chunk và fan-in khác nhau; mỗi trường hợp đối chiếu toàn bộ output, Top K và rank cuối với oracle sort trong RAM. Oracle **chỉ phục vụ kiểm thử**, không phải pipeline external sort.

### 12.3. Vì sao mã là demo external-memory thật?

**createInitialRuns** đọc input file theo từng dòng qua BufferedReader, chỉ giữ tối đa chunkRecords record trước khi sort và ghi run. Nó không gọi Files.readAllLines trên input lớn.

**consumeMerged** mở các input readers của một group, đưa một head mỗi run vào PriorityQueue, rồi đọc bổ sung từng record khi pop. Không giữ nguyên cả run trong heap.

**mergeOnePass** gom số input runs không vượt fan-in và ghi các run mới trước khi xóa run cũ. Mỗi run mới tự nó đã sorted.

**firstK / selectRank** sử dụng đúng cùng logic heap. firstK trả list có thể tốn O(K) RAM; selectRank chỉ giữ một biến last ngoài heap.

**ReaderGroup** đóng file ngay cả khi việc mở một nhóm readers thất bại ở giữa; tránh rò file descriptors.

**readSmallDemoOutput / inMemoryOracle** chỉ chạy sau sort trên bộ dữ liệu bé để kiểm thử. Nếu gọi những hàm này với file nhiều terabyte sẽ phá giới hạn RAM, nhưng pipeline xử lý file không phụ thuộc chúng.

**deleteTree** chỉ xóa thư mục tạm do chính demo tạo. Với production, output phải nằm ở vị trí bền vững sau khi hoàn tất, kèm manifest/checksum/cơ chế khôi phục phù hợp.

## 13. Một lỗi quan trọng: nguồn chưa được sắp

K-way merge giả định mỗi nguồn sorted. Nếu các nguồn là:

~~~text
Run 0: [10, 1]
Run 1: [2, 3]
~~~

Heap heads ban đầu chứa 10 và 2, nên chọn 2 trước dù toàn bộ dữ liệu còn phần tử **1** ở sâu trong Run 0. Thuật toán không có cách nhìn thấy 1 khi chưa đọc qua 10. Output bắt đầu bằng 2 là **sai** đối với mục tiêu sort tăng.

Vì vậy:
- Phải tạo các sorted runs trước.
- Hoặc chọn một thuật toán khác phù hợp dữ liệu unsorted.

### 13.1. Top K từ một luồng chưa sorted

Một cách phổ biến để chọn K **nhỏ nhất** từ luồng unsorted:
1. Duyệt toàn bộ N records.
2. Duy trì **max-heap kích thước K**.
3. Nếu heap chưa đủ K, thêm record.
4. Nếu record mới nhỏ hơn phần tử lớn nhất trong heap, thay thế phần tử lớn nhất.
5. Sau khi đọc hết luồng, heap chứa K record nhỏ nhất (cần xuất đúng thứ tự bằng sort/pop).

Thời gian thường O(N log K), bộ nhớ O(K). Nó phải xem hết N input records, trừ khi có thông tin bổ sung giúp dừng sớm.

Đây là bài toán **heap Top K từ unsorted stream**, **khác** k-way selection từ nhiều run đã sorted: thuật toán thứ hai có thể dừng sau K lần pop khi mọi nguồn đã sorted và có thể mở trong fan-in.

### 13.2. Top K largest

Nếu muốn K phần tử **lớn nhất** từ các run đã sắp **giảm** dần, có thể dùng max-heap trên heads. Nếu run sắp **tăng** dần nhưng chỉ đọc từ đầu, đổi min-heap thành max-heap trên heads không giải được largest toàn cục; cần đọc từ cuối hoặc thay đổi cách biểu diễn/thuật toán.

## 14. Trường hợp dữ liệu rất lớn và môi trường thật

### 14.1. Khối I/O, format và parsing

Demo dùng text records, dễ đọc nhưng parse số từ chuỗi. Với dữ liệu lớn có thể:
- Dùng file nhị phân có record framing rõ ràng.
- Dùng BufferedInputStream/FileChannel và buffer phù hợp.
- Ghi output theo block.
- Cân nhắc SSD throughput, OS page cache và hằng số CPU khi parse.

Buffer quá bé có thể gây nhiều I/O nhỏ. Buffer quá lớn cho k nguồn có thể tiêu tốn RAM vì tổng bộ đệm tỷ lệ k×B.

### 14.2. Replacement selection

Để giảm số initial runs, có kỹ thuật **replacement selection** dùng heap để tạo run có thể dài hơn C records khi dữ liệu có phân phối thuận lợi. Trên input ngẫu nhiên theo một số mô hình, độ dài run kỳ vọng có thể gần 2C, nhưng **không phải bảo đảm trên mọi input**.

Nếu số run R0 giảm, số merge passes có thể giảm, từ đó giảm I/O. Đổi lại thuật toán tạo run phức tạp hơn và cần quản lý record thuộc run hiện tại/run kế tiếp.

### 14.3. Loser tree và tournament tree

Nếu fan-in lớn, có thể thay PriorityQueue bằng **tournament tree/loser tree**:
- Vẫn chọn phần tử nhỏ nhất từ các heads.
- Cập nhật sau mỗi pop trong O(log k).
- Có thể giảm hằng số phép so/cải thiện locality ở một số implementation.

Cần đo thực nghiệm theo comparator, số run và môi trường; không tuyên bố winner tree hay loser tree luôn nhanh hơn PriorityQueue.

### 14.4. Pipeline và song song

Có thể đọc chunk tiếp trong khi sort chunk hiện tại, ghi run song song, hoặc merge các nhóm độc lập trong cùng pass. Nhưng nhiều merge groups chạy song song cũng **nhân số readers, buffers và output files**, có thể làm vượt ngân sách file descriptors/RAM hoặc gây I/O contention.

Mức song song tốt nhất cần đo throughput và latency thực tế; không tự tăng fan-in hay số threads vô điều kiện.

### 14.5. Lỗi I/O và tính bền vững

Khi đang ghi run mới mà mất điện hoặc disk full:
- File output có thể chưa hoàn tất.
- Run cũ không được xóa trước khi output mới đã được xác nhận an toàn.
- Cần manifest, checksum/record count, temp staging, atomic rename hoặc transaction thích hợp với filesystem.
- Một output nửa chừng không được dùng như sorted run hợp lệ sau restart.

Demo xóa file run cũ sau khi đã ghi xong pass mới, nhưng chưa có crash-safe manifest/fsync/resume. Không triển khai trực tiếp bản demo như một sort service cần bảo đảm dữ liệu bền vững.

## 15. Kiểm thử bằng oracle độc lập

Một output sorted nhìn hợp lý vẫn có thể:
- Mất record ở ranh giới run.
- Nhân đôi head.
- Bỏ run cuối.
- Đảo thứ tự những khóa bằng nhau.
- Đếm sai rank khi duplicate.
- Mở nhiều readers hơn fan-in.

Cần kiểm các thuộc tính:

### 15.1. Bảo toàn dữ liệu và thứ tự

1. Số record đầu ra đúng bằng N.
2. Mỗi cặp (value,originalOrdinal) đầu vào xuất đúng một lần.
3. Output không giảm theo **comparator toàn cục**.
4. Với khóa bằng nhau, ordinal giữ thứ tự tăng.
5. Không có EOF sentinel giả.

Khi n nhỏ, oracle có thể sort bản sao toàn bộ data trong RAM theo comparator y hệt, so chính xác từng record.

### 15.2. Top K và rank

Với oracle đã sorted:
- firstK(0) trả [].
- firstK(K) cho K≤N bằng K phần tử đầu.
- firstK(N+1) bằng toàn bộ N.
- rank1 bằng record đầu.
- rankN bằng record cuối.
- rankN+1 bị từ chối.
- rank0 bị từ chối.
- Trường hợp duplicate vẫn tính mỗi record đúng một lần.

### 15.3. Pass và fan-in

Với R input runs:
- Mỗi group mở tối đa k run.
- Sau pass, số run là ceil(R/k).
- Multiset của output runs bằng multiset input runs.
- Mọi output run đều sorted.
- Nếu R>1, k≥2 thì số run giảm.
- R=0 tạo đầu ra rỗng; R=1 không cần merge pass.

### 15.4. Các ca biên cần cố ý thử

- N=0,1,2.
- N=C−1, C, C+1.
- Đầy đủ duplicate; mỗi record có ordinal khác.
- Đầu vào đã tăng hoặc giảm.
- Có giá trị âm, 0, Long.MIN_VALUE và Long.MAX_VALUE.
- Fan-in=2, fan-in lớn hơn số run, fan-in=1 không hợp lệ.
- Run cuối thiếu record; nhóm merge cuối chỉ có một run.
- Một run rỗng, dữ liệu input malformed.
- Lỗi quyền đọc file, disk full, mất file trung gian.
- Nếu làm production: crash/restart giữa pass.

Test ngẫu nhiên không thay cho chứng minh bất biến heap; hai cách bổ sung cho nhau.

## 16. Các lỗi phổ biến

1. **Cho toàn bộ N records vào heap** thay vì một head mỗi run, phá ngân sách RAM.
2. **Không sort từng run trước merge**, khiến heap heads không đại diện cho min toàn cục.
3. **Pop một run nhưng refill từ run khác**, mất/nhân đôi record.
4. **Quên đưa head kế tiếp vào heap** khi run còn dữ liệu.
5. **Đưa sentinel -1/Long.MAX_VALUE khi EOF**, có thể trùng khóa hợp lệ.
6. **Không đóng readers**, gây lỗi quá giới hạn open files.
7. **Mở bốn run khi fan-in được cấu hình ba**, dù thuật toán vẫn trả sorted output.
8. **Quên output buffer/heap overhead** khi tính k từ RAM.
9. **Fan-in=1 nhưng lặp merge đến một run**, tạo vòng lặp không giảm.
10. **Quên xử lý run cuối ngắn hơn chunk size**.
11. **Quên nhóm merge cuối có số run nhỏ hơn fan-in**.
12. **Nhầm heap iterator với một dãy sorted**, trong Java không được bảo đảm.
13. **Đổi khóa của node trong PriorityQueue mà không reheapify**, làm heap sai.
14. **Dùng phép trừ long trong comparator**, overflow có thể đảo thứ tự.
15. **Không lưu tie-breaking**, làm mất stable sorting.
16. **Mất original ordinal sau một pass**, không còn chứng minh ổn định.
17. **Input runs dùng comparator khác nhau**, heap không còn hợp đồng.
18. **Đếm rank từ 0 dù API 1-based**, off-by-one.
19. **Rank>N nhưng trả last record**, che lỗi không có phần tử.
20. **Nhầm K-th record với K-th distinct**, đặc biệt khi duplicate nhiều.
21. **Dùng min-heap trên head của run tăng để chọn largest**, sai hướng.
22. **Coi số phép heap O(N log k) là toàn bộ I/O external sort**, bỏ qua các pass.
23. **Quên giai đoạn đọc/ghi tạo initial runs** trong I/O complexity.
24. **Dùng N theo byte và B theo record trong cùng một công thức**, sai đơn vị.
25. **Không tính block prefetch khi chỉ chọn K nhỏ**, đánh giá I/O quá lạc quan.
26. **Giữ tất cả K output records mà vẫn nói memory O(k)**, bỏ O(K).
27. **Giữ metadata R runs trong RAM mà bỏ O(R)**.
28. **Đọc toàn bộ file bằng Files.readAllLines trong pipeline external**, không còn giới hạn chunk.
29. **Dùng test nhỏ để tuyên bố ổn định tốc độ trên file hàng terabyte**, thiếu benchmark block I/O.
30. **Không kiểm multiset/ordinal**, có thể mất record vẫn trông sorted.
31. **Xóa input runs trước khi ghi output mới xong**, nguy cơ mất dữ liệu.
32. **Dùng output chưa commit sau crash như run hợp lệ**, tạo dữ liệu hỏng.
33. **Tăng fan-in quá cao**, vượt RAM/file descriptors.
34. **Chạy nhiều merge jobs song song mà không nhân bộ đệm**, vượt ngân sách.
35. **Không phân biệt rank đã sort và Top K unsorted**, áp dụng sai heap.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Sorted run là gì?

**Đáp án:** Một file hoặc đoạn đã sorted theo comparator dùng cho toàn bộ merge.

**Câu 2.** Trong k-way merge, heap có tối đa bao nhiêu phần tử?

**Đáp án:** Tối đa k heads, một của mỗi run chưa cạn.

**Câu 3.** Vì sao min của heads là min toàn cục còn lại?

**Đáp án:** Mỗi run sorted nên mọi phần tử chưa dùng của một run đều không nhỏ hơn head của chính run ấy.

**Câu 4.** Khi pop head thuộc run j, bước tiếp theo là gì?

**Đáp án:** Đọc next từ run j, nếu chưa EOF thì push head mới thuộc j.

**Câu 5.** CPU k-way merge N record, k run có cận gì?

**Đáp án:** O(k log k+N log k) với khởi tạo heap bằng từng lần add; thường viết O(N log k) khi N≥k.

**Câu 6.** I/O và CPU khác nhau thế nào?

**Đáp án:** CPU tính số phép so/heap, I/O tính các block đọc/ghi; external sort có nhiều merge passes.

**Câu 7.** N=14, C=4 tạo mấy initial runs?

**Đáp án:** 4 runs, kích thước 4,4,4,2.

**Câu 8.** R0=4 và fan-in=3 cần mấy passes?

**Đáp án:** 2 passes: 4→2→1.

**Câu 9.** Tăng fan-in có thể giúp gì và tốn gì?

**Đáp án:** Có thể giảm pass/I/O nhưng tăng buffers, heap và open file descriptors.

**Câu 10.** Vì sao cần ordinal khi duplicate?

**Đáp án:** Để giữ stable order của các record cùng key qua mọi run và pass.

**Câu 11.** Tại sao không trừ hai long để so sánh?

**Đáp án:** Có thể overflow, nên dùng comparingLong hoặc Long.compare.

**Câu 12.** Có cần merge toàn bộ N để lấy Top K từ sorted runs không?

**Đáp án:** Không; pop K record nhỏ nhất rồi dừng khi đủ hoặc hết dữ liệu.

**Câu 13.** Rank r có tính duplicate không?

**Đáp án:** Có, theo hợp đồng record rank 1-based ở bài này.

**Câu 14.** K-th distinct khác gì?

**Đáp án:** Phải bỏ các khóa trùng sau merge, nên có thể cần pop hơn K record.

**Câu 15.** Chọn rank r bằng heap cần giữ r record trong RAM không?

**Đáp án:** Không, chỉ cần một biến last ngoài heap heads/buffers.

**Câu 16.** Nếu k=4 nguồn nhưng giới hạn fan-in=3?

**Đáp án:** Phải giảm số nguồn qua merge pass hoặc dùng một cây merge nhiều tầng có ngân sách hợp lệ.

**Câu 17.** Với nguồn unsorted, một heap head mỗi nguồn còn đúng không?

**Đáp án:** Không; min thật có thể nằm sau head.

**Câu 18.** Với luồng unsorted, Top K nhỏ nhất dùng heap thế nào?

**Đáp án:** Duy trì max-heap kích thước K, quét toàn bộ N records, O(N log K).

**Câu 19.** File EOF nên biểu diễn bằng số nào?

**Đáp án:** Không dùng số dữ liệu; dùng null/Optional hoặc trạng thái EOF riêng.

**Câu 20.** Trường hợp run rỗng thì làm sao?

**Đáp án:** Không đưa head giả vào heap; bỏ qua reader đã EOF.

**Câu 21.** Vì sao cần kiểm số record sau sort?

**Đáp án:** Để phát hiện mất hoặc nhân đôi bản ghi dù thứ tự output nhìn đúng.

**Câu 22.** Bản Java có tự khôi phục sau crash không?

**Đáp án:** Không; nó là demo và cần manifest, commit/restart protocol để production crash-safe.

**Câu 23.** Khi nào không nên chọn external merge sort?

**Đáp án:** Khi dữ liệu đủ nhỏ trong RAM, hoặc có truy cập random/đặc tính bài toán giúp một phương pháp khác tốt hơn.

**Câu 24.** Một benchmark external-memory cần đo gì?

**Đáp án:** CPU time, số block/bytes đọc ghi, RAM, số file descriptors, số pass, throughput, độ ổn định khi lỗi.

## 18. Bài tập thực hành

**Bài 1 — Fan-in:** chạy lại cùng input với k=2,3,4; ghi số pass, output, peak number of readers.

**Bài 2 — Stability:** thêm duplicate vào nhiều run, kiểm ordinal của những key bằng nhau vẫn tăng.

**Bài 3 — Top K:** thử K=0,1,5,N,N+1 và rank=1,N,N+1; so với oracle.

**Bài 4 — Top K distinct:** sau mỗi pop, chỉ đếm khi key thay đổi; nêu sự khác biệt về số record đã quét.

**Bài 5 — Định dạng nhị phân:** dùng BufferedInputStream/FileChannel để ghi long+ordinal; đo I/O và kiểm tính đúng.

**Bài 6 — File lớn:** tạo input lớn hơn RAM, chứng minh pipeline không dùng readAllLines, đo peak heap/buffers.

**Bài 7 — Lỗi giữa pass:** thiết kế manifest và atomic swap để không mất run cũ khi output mới bị lỗi.

**Bài 8 — Top K unsorted:** cài max-heap K trên một stream chưa sort, đối chiếu độ phức tạp với k-way heap selection.

**Bài 9 — Loser tree:** thử thay PriorityQueue bằng tournament tree với k lớn và đo số comparator calls.

## 19. Ghi nhớ

**K-way merge** trộn những run đã sorted bằng **min-heap của các heads**, không cần giữ toàn bộ data trong RAM. Mỗi record được xuất một lần, refill chỉ từ run đã pop; một merge pass có CPU O(N log k) trong mô hình thông dụng.

**External merge sort** sort từng chunk vừa RAM thành initial runs, rồi trộn theo fan-in và nhiều passes. Với R0 initial runs và k≥2, số passes khoảng \(\lceil\log_kR_0\rceil\), tổng block I/O gần O((N/B)(1+P)) trên mô hình lý tưởng. Fan-in phụ thuộc RAM, buffers, heap và file descriptors.

**Selection** trên các run đã sorted có thể dừng sau K records cho Top K hoặc r records cho rank r, nhưng phải bảo đảm số nguồn mở không vượt fan-in. Khi duplicate xuất hiện, rank trong bài tính **từng record**, còn stable output giữ thứ tự **original ordinal**.

Một triển khai đúng phải kiểm cả **bất biến heap, EOF, tính sorted của run, số record bảo toàn, giới hạn tài nguyên và tính bền vững của intermediate files**.
