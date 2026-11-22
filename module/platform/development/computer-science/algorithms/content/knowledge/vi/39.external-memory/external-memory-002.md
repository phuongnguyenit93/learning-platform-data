# Chọn kích thước lô theo bộ nhớ khả dụng

## 1. Vấn đề: xử lý dữ liệu lớn hơn RAM

Trong các thuật toán **ngoài bộ nhớ (external-memory)**, dữ liệu được giữ chủ yếu trên đĩa hoặc kho lưu trữ và chuyển từng phần vào bộ nhớ chính để xử lý. Một tác vụ đọc log, sort tệp lớn, ETL, hash aggregation hoặc import dữ liệu có thể thất bại khi cố giữ cả tập dữ liệu trong RAM. Giải pháp thường là chia thành **lô (batch/chunk)**, xử lý và ghi kết quả của lô hiện tại trước khi chuyển sang lô sau.

Nhưng lô quá nhỏ hoặc quá lớn đều có chi phí:

- **Quá nhỏ:** tạo nhiều tệp trung gian, tốn nhiều lần đọc/ghi và overhead khởi tạo; external merge sort có thể cần thêm nhiều lượt trộn.
- **Quá lớn:** dễ hết heap/RAM, tăng thời gian garbage collection, gây đổi trang hoặc thậm chí bị container OOM-kill.
- **Không xét dữ liệu biến dài:** một lô 1.000 JSON lớn có thể tốn nhiều bộ nhớ hơn 100.000 số nguyên 32-bit.
- **Không xét concurrency:** nhiều worker mỗi worker giữ một lô có thể dùng nhiều RAM hơn giới hạn của toàn ứng dụng.

Tư duy đúng là **lập ngân sách bằng byte**, tính các cấu trúc phải tồn tại đồng thời, dự phòng biến động, chọn lô vừa ngân sách và đánh giá thông lượng/độ trễ bằng số đo thật.

Câu hỏi trung tâm: nếu thuật toán được cấp M byte bộ nhớ làm việc, có chi phí cố định F byte, dự phòng S byte và một bản ghi thực sự chiếm r byte, số bản ghi tối đa một lô là bao nhiêu?

~~~text
F + S + batchCount*r <= M

batchCount <= floor((M-F-S)/r)
~~~

Công thức chỉ an toàn khi F và r bao gồm đủ **bộ đệm, cấu trúc phụ và bản sao tạm**; nếu r chỉ là độ dài lưu trên đĩa hoặc kích thước trung bình, đây chỉ là ước lượng thô, chưa phải bảo đảm.

Bài này trình bày công thức, ứng dụng vào **external merge sort**, cách tính số run và fan-in, quản lý file descriptor, xử lý hàng biến độ dài, backpressure, kiểm chứng tính đúng, rồi triển khai ví dụ Java 17 chạy với các tệp thực.

## 2. Mô hình bộ nhớ ngoài N–M–B

Trong mô hình I/O cổ điển, ta phân biệt:

~~~text
N: kich thuoc du lieu / so phan tu
M: bo nho trong RAM danh cho thuat toan
B: block du lieu chuyen qua moi lan I/O
~~~

Khi dùng công thức theo byte, phải đổi **N, M và B về cùng đơn vị**. Với một mảng N số nguyên có dấu 32-bit được lưu nhị phân, kích thước tệp là `4*N` byte.

CPU thao tác trên dữ liệu trong RAM rất nhanh, nhưng đọc/ghi từ bộ nhớ thứ cấp có độ trễ và chi phí khác biệt. Thuật toán external-memory cố gắng giảm **số block truyền** và ưu tiên đọc/ghi tuần tự khi có thể.

### Đừng nhầm kích thước block với kích thước buffer Java

Một `BufferedInputStream` có thể đọc trước nhiều byte vào mảng. Gọi `readInt()` nhiều lần không có nghĩa mỗi lần chạm thiết bị vật lý. Hệ điều hành còn có page cache, filesystem có read-ahead, thiết bị lưu trữ có cache và lịch trình riêng.

Vì vậy **số byte đọc/ghi logic** từ code, số lệnh gọi API và **I/O vật lý thực tế** là những đại lượng khác nhau. Mô hình I/O giúp lập luận thuật toán, nhưng benchmark mới xác định hiệu năng trên hệ thống thật.

### Đơn vị thường gặp

- 1 KiB = 1.024 byte.
- 1 MiB = 1.048.576 byte.
- 1 MB = 1.000.000 byte.
- Java `int` là 32-bit; một giá trị ghi bằng `DataOutputStream.writeInt` tạo 4 byte, dạng big-endian.
- Java `long` có 64 bit; số phần tử/byte hoặc checksum lớn nên dùng `long` để tránh tràn các phép nhân trung gian.

Một lô gồm một triệu `int` có 4.000.000 byte **payload**, nhưng mảng Java còn header, còn stream và mã thuật toán có overhead khác. Không được dùng `payloadBytes == peakProcessMemory`.

## 3. Ngân sách RAM phải trừ những gì?

Một kế hoạch bộ nhớ nên tách các phần:

~~~text
Mwork = S + F + I + O + P + H

S: safety reserve / headroom
F: fixed overhead cua thuat toan
I: bo dem dau vao dang ton tai
O: bo dem dau ra dang ton tai
P: payload lo ban ghi
H: heap, index, hashmap, metadata, sort workspace...
~~~

Các pha khác nhau có cách phân bổ khác nhau. Trong **tạo run** của external sort, cần một mảng phần tử, một input buffer và một output buffer. Trong **merge k run**, cần k input buffers, một output buffer và một hàng đợi ưu tiên chứa trạng thái đầu mỗi run; không cần giữ cả k run trong RAM.

### Mwork không nhất thiết là RAM toàn máy

Trong Java, `-Xmx` giới hạn heap tối đa, không bao hàm tất cả native memory, thread stack, direct memory, page cache hay hệ điều hành. Một container có memory limit riêng; các tác vụ đồng thời còn chia sẻ quota đó.

Do vậy hãy xác định **Mwork là ngân sách cho phần thuật toán đang lập kế hoạch**, không mặc định là toàn bộ RAM khả dụng. Mã minh họa dùng `workingBytes` là một mức kế hoạch, **không phải cơ chế cưỡng chế sử dụng bộ nhớ cứng của JVM**.

### Safety reserve có ý nghĩa gì?

Kích thước object, tình trạng GC, buffer tạm, giải nén và concurrency có thể làm memory peak cao hơn tính toán nominal. Chừa S byte để hấp thụ chênh lệch.

Một tỷ lệ phần trăm dự phòng chỉ là điểm khởi đầu. Phải đo trên input khó, có outlier và trong môi trường triển khai thực tế rồi điều chỉnh. Bỏ hoàn toàn dự phòng thường là cách tăng nguy cơ OOM, chứ không phải tối ưu hiệu năng.

### Phân biệt peak với tổng cộng theo thời gian

Nếu các pha read, transform, sort, write **tuần tự** và trả lại bộ nhớ giữa pha, peak là giá trị lớn nhất trong số các pha. Nếu pipeline chạy **đồng thời** và giữ nhiều batch trong queue, các phần dùng RAM đồng thời phải được **cộng**.

## 4. Công thức cho lô bản ghi cố định

Giả sử mỗi bản ghi được giữ trong một `int[]`, phần tử có payload 4 byte. Gọi:

~~~text
Mwork: working-memory budget
S: safety reserve
F: fixed workspace overhead allowance
I: input buffer cho run generation
O: output buffer cho run generation

payloadBytes = Mwork - S - F - I - O

runCapacity = floor(payloadBytes / 4)
~~~

Nếu `payloadBytes < 4`, ngân sách không đủ chứa dù chỉ một số nguyên theo mô hình; phải điều chỉnh hoặc từ chối. Nếu lô có `c` bản ghi, mảng lưu lô cần khoảng `4*c` byte payload, còn header/overhead phải nằm trong F/S.

### Ví dụ 2 MiB cho thuật toán

| Khoản | Bytes | Quy đổi |
| --- | ---: | --- |
| Mwork | 2.097.152 | 2 MiB |
| S | 524.288 | 512 KiB |
| F | 262.144 | 256 KiB |
| I | 65.536 | 64 KiB |
| O | 65.536 | 64 KiB |
| Còn cho payload | 1.179.648 | 1.125 KiB |
| Payload mỗi int | 4 | byte |
| Sức chứa lô | 294.912 | số int |

~~~text
2,097,152 - 524,288 - 262,144 - 65,536 - 65,536
= 1,179,648

floor(1,179,648 / 4) = 294,912
~~~

Giả sử có 700.000 int:

~~~text
inputBytes = 700,000 * 4 = 2,800,000

run0: 294,912 ints
run1: 294,912 ints
run2: 110,176 ints

numberOfRuns = ceil(700000/294912) = 3
~~~

**Lô cuối chỉ có số phần tử thực sự đọc**, không thêm số 0 hay bản ghi giả để đủ capacity, vì như vậy sẽ làm thay đổi dữ liệu.

### Số bản ghi không có nghĩa byte

Nếu thay `int[]` bằng `List<String>` hoặc `ArrayList<Record>`, số byte mỗi bản ghi lớn và khó xác định hơn, nên công thức phải đổi theo kiểu biểu diễn mới. Không lấy 4 byte/record từ ví dụ để áp cho JSON hay đối tượng Java.

## 5. Bản ghi biến độ dài và giới hạn byte linh hoạt

Giả sử có ba dòng JSON với dung lượng lưu trữ:

~~~text
rowA:       80 bytes
rowB:      250 bytes
rowC: 8,000,000 bytes
~~~

Chọn lô 10.000 dòng dựa vào average 200 byte có thể thất bại khi gặp bản ghi cực lớn.

### Số byte raw và heap là hai chuyện khác nhau

- Một chuỗi có ký tự Unicode có số byte UTF-8 khác số ký tự.
- Parse JSON tạo nhiều map/list/string/number object.
- Có thể đồng thời giữ raw bytes, decoded text, parsed object, transformed object và serialization buffer.
- Một số phép sort tạo chỉ số hoặc bản sao tạm.
- Dữ liệu nén có thể nở ra rất nhiều khi giải nén.

Để ước lượng an toàn, cần **cận trên hợp lý** cho chi phí xử lý mỗi record hoặc giới hạn byte động với cơ chế overflow.

### Ghép batch theo byte

~~~text
batch = empty
used = 0

for each record:
    cost = estimateRetainedBytes(record)

    if cost > payloadBudget:
        handleOversizedRecord(record)  // spill, stream, reject
        continue

    if used + cost > payloadBudget:
        processAndRelease(batch)
        batch = empty
        used = 0

    batch.add(record)
    used += cost

if batch not empty:
    processAndRelease(batch)
~~~

Cần tính cả vùng tạm phát sinh khi **processAndRelease**. Không được hiểu `estimateRetainedBytes()` là phép đo exact của JVM nếu chỉ dựa trên kích thước dữ liệu serialized.

### Quá lớn so với một batch

Nếu một record vượt ngân sách ngay cả khi đứng riêng, có thể stream từng phần nếu ngữ nghĩa cho phép, giữ payload trên đĩa rồi xử lý theo offset, hoặc báo lỗi có lý do. **Không tự truncate record** vì như thế thay dữ liệu.

## 6. Backpressure và nhiều lô cùng tồn tại

Ngay cả khi mỗi batch riêng lẻ vừa RAM, hệ thống có thể OOM nếu giữ quá nhiều batch trong bộ đệm giữa các công đoạn.

Ví dụ:

~~~text
reader -> queue -> 4 processors -> queue -> writer
~~~

Nếu reader tạo batch nhanh hơn writer tiêu thụ và queue không giới hạn, bộ nhớ backlog sẽ tăng.

### Ngân sách đồng thời

Một cận lập kế hoạch:

~~~text
peakMemory
 <= sharedFixed
  + activeWorkers * peakPerWorker
  + queuedBatches * queuedBatchBytes
  + safetyReserve
~~~

Cần biết **bao nhiêu worker có thể đang xử lý cùng lúc**, mỗi worker đang giữ những cấu trúc nào, queue có bao nhiêu batch, và có bao nhiêu bản sao của cùng dữ liệu.

### Backpressure đúng mục đích

Đặt queue có giới hạn theo số batch hoặc byte. Khi đạt ngưỡng, reader tạm dừng đến khi consumer giải phóng vùng nhớ; không tạo thêm batch chỉ để tiết kiệm thời gian chờ I/O.

Giảm batch size nhưng tăng concurrency từ một worker lên mười worker có thể **tăng** peak RAM. Bài toán tối ưu phải xét cặp `(batchSize, concurrency)`.

### Thời gian và độ trễ

Lô lớn có thể tăng throughput do giảm overhead một batch; nhưng thời gian chờ lô đầy và thời gian xử lý trước khi có output cũng tăng. Một hệ thống tương tác có SLA độ trễ thấp có thể chọn batch nhỏ hơn cấu hình đạt throughput cao nhất.

## 7. External merge sort: cách chia và trộn lô

Một thuật toán ngoại bộ phổ biến là **external merge sort**:

1. **Sinh run:** đọc một lô không vượt `runCapacity`, sort trong RAM, ghi vào một tệp đã sắp xếp. Lặp đến cuối input.
2. **Trộn run:** chọn tối đa k run, mở một stream cho mỗi run và một output stream, dùng priority queue giữ phần tử đầu của mỗi run, xuất ra run lớn hơn.
3. Tiếp tục cho đến khi chỉ còn một run cuối; đó là tệp kết quả đã sort.

~~~text
unsorted input file
       |
       v
batch 0 -> sort -> run0
batch 1 -> sort -> run1
batch 2 -> sort -> run2
                  |
                  v
       multi-pass merging
                  |
                  v
        final sorted file
~~~

### Bất biến khi sinh run

Mỗi run chứa đúng đa tập các phần tử đọc được trong một lô, đã được sắp xếp. Các run hợp lại chứa **toàn bộ input một lần**, không mất và không thêm bản ghi.

### Vì sao tạo run có ích?

Ta cần RAM chỉ đủ để sort **một lô**, còn dữ liệu gốc và các run nằm trên đĩa. Mỗi run được ghi/đọc theo kiểu tuần tự. Điều này khác với việc đọc cả tệp 700.000 int vào một mảng rồi mới gọi `Arrays.sort`.

### Số run

Với N_records phần tử và capacity c≥1:

~~~text
initialRuns = ceil(N_records/c)
~~~

Đối với N_records=0, không có run và output phải rỗng. Đối với 1..c phần tử, chỉ có một run và không cần pass trộn.

## 8. Fan-in của merge: RAM và file descriptor

Trong một phép trộn **k-way**, ta thường cần:

- k input buffers, mỗi buffer I byte.
- Một output buffer O byte.
- Một head/metadata cho mỗi run, ước lượng H byte/run.
- Fixed overhead F và safety reserve S.

Điều kiện memory:

~~~text
S + F + O + k*(I+H) <= Mwork
~~~

Và nếu chỉ dành tối đa D tệp mở đồng thời cho một phép merge, cần:

~~~text
k input files + 1 output file <= D

k <= D-1
~~~

Từ đó:

~~~text
k_memory = floor((Mwork-S-F-O)/(I+H))
k_files  = D-1
k        = min(k_memory, k_files, numberOfRuns)
~~~

Để giảm số run trong một pass phải có **k≥2**. Nếu k=1, gom một run thành một run không có tiến triển.

### Tính cho cấu hình 2 MiB

~~~text
Mwork-S-F-O
= 2,097,152 - 524,288 - 262,144 - 65,536
= 1,245,184

I = 65,536 bytes
H = 128 bytes/run (estimate)

k_memory = floor(1,245,184 / 65,664) = 18
~~~

Nhưng cấu hình demo chỉ dành **D=3 file**, gồm hai input và một output:

~~~text
k_files = 3-1 = 2
mergeFanIn = min(18,2,3) = 2
~~~

Ở đây **giới hạn file descriptor**, không phải RAM, quyết định số run được trộn cùng lúc. Trong hệ thống thật phải tính cả file logs, sockets, các luồng merge khác và file limit toàn process.

`H=128 byte/run` chỉ là **ước lượng lập kế hoạch**, không phải kích thước object Java được bảo đảm. Cần đo thực tế và sử dụng S để hấp thụ chênh lệch.

## 9. Số pass, run lẻ và I/O logic

Với R run ban đầu, fan-in k≥2, số vòng merge trong mô hình thường có cận khoảng:

~~~text
passes = ceil(log_base_k(R))   (R>1)
~~~

Khi R=3 và k=2:

~~~text
initial:
  run0 294,912 ints
  run1 294,912 ints
  run2 110,176 ints

pass1:
  merge(run0,run1) -> merged01 589,824 ints
  carry(run2)      -> run2    110,176 ints

pass2:
  merge(merged01,run2) -> final 700,000 ints

merge passes = 2
~~~

Nếu nhóm cuối của một pass chỉ có **một run**, có thể chuyển nó thẳng sang pass tiếp theo thay vì đọc/ghi lại. Đây là một cách tránh I/O không cần thiết.

### Logical bytes được chuyển

Sinh run cần đọc input và ghi run:

~~~text
2,800,000 read + 2,800,000 write
= 5,600,000 bytes
~~~

Pass 1 trộn hai run đầu:

~~~text
2 * 589,824 * 4 = 4,718,592 bytes
~~~

Pass 2 trộn toàn bộ dữ liệu:

~~~text
2 * 700,000 * 4 = 5,600,000 bytes
~~~

Tổng lưu lượng **đọc + ghi logic cho các pha sort**:

~~~text
5,600,000 + 4,718,592 + 5,600,000
= 15,918,592 bytes
~~~

Không bao gồm bước tạo input, bước kiểm output, file metadata, page cache và mọi I/O vật lý ngoài mô hình. Nếu tăng giới hạn file mở lên D=4 (vẫn đủ bộ nhớ cho k=3), có thể merge cả ba run trong một pass, giảm I/O trung gian.

### Lô quá nhỏ có thể làm nổ số pass

Nếu chỉ đọc 1.000 int mỗi lô, 700.000 int tạo **700 run**. Với k=2, số tầng merge khoảng `ceil(log₂ 700)=10`, so với 2 tầng của capacity=294.912. Rất nhiều tệp và pass khiến overhead tăng.

## 10. Độ phức tạp trong mô hình I/O

Trong mô hình truyền block B, external merge sort có chi phí I/O tiệm cận thường phát biểu:

~~~text
O((N/B) * (1 + log_(M/B)(N/B)))
~~~

với các giả thiết kinh điển như M đủ lớn so với B, dữ liệu được chia thành block và có thể trộn nhiều run cùng lúc. Cần dùng **đơn vị nhất quán**, không nhầm N_records với N_bytes.

### Chi phí CPU

Một run có c phần tử cần khoảng O(c log c) phép so sánh khi sort thông thường. Một phép trộn k-way với priority queue cần O(N_merge log k) phép thao tác heap. Nhưng khi storage chậm, số pass và lượng I/O thường là biến quyết định.

### Khi nào tăng batch không cải thiện?

- Dữ liệu được parse/giải nén chậm khiến CPU-bound.
- Sort object nặng gây GC.
- Storage/network đã bão hòa, hoặc page cache không đủ.
- Nhiều worker tranh cùng disk.
- Tệp run quá lớn khiến đường đi write/read có độ trễ cao hoặc thiếu disk space.

Vì vậy **cận lý thuyết không thay thế benchmark**. Đo peak memory và throughput trên input đại diện trước khi chọn cấu hình sản xuất.

## 11. Ví dụ đầu vào cố định và kết quả chuẩn

Ví dụ Java trong bài tạo một tệp nhị phân gồm 700.000 số nguyên có dấu 32-bit:

~~~text
value(i) = ((i*37) mod 10007) - 5000

i = 0..699999
~~~

Miền giá trị là `[−5000,5006]`. Nhiều giá trị trùng nhau; việc chỉ kiểm min/max và tổng **không đủ chứng minh bảo toàn đa tập**.

### Kế hoạch lô và merge

~~~text
working budget:       2 MiB
safety reserve:      512 KiB
fixed overhead:      256 KiB
input buffer:         64 KiB
output buffer:        64 KiB
per-run state:       128 bytes (estimate)
max merge open files: 3

run capacity:        294912 integers
initial runs:             3
merge fan-in:             2
merge passes:             2
input file size:    2800000 bytes
~~~

Tính độc lập bằng một vòng lặp trên công thức phát sinh dữ liệu:

~~~text
count = 700000
min   = -5000
max   = 5006
sum   = 1897415
~~~

Checksum tổng 1.897.415 chỉ là một đối chứng phụ. Mã sẽ tính **tần suất kỳ vọng** cho mọi giá trị từ input generator, quét output và so tần suất chính xác; đồng thời kiểm output không giảm và số bản ghi không thay đổi.

### Tái lập được

Dùng công thức số nguyên thay vì RNG giúp kết quả kiểm thử xác định và không phụ thuộc seed. Nếu benchmark bằng dữ liệu ngẫu nhiên, cần công bố seed, phân phối giá trị và điều kiện thử nghiệm.

## 12. Java 17: external sort theo batch budget

Chương trình sau dùng **tệp binary thật** và `DataInputStream/DataOutputStream`; đây không chỉ là giả mã.

- `Budget.runCapacity`: tính tối đa số int có thể giữ trong mảng theo ngân sách.
- `Budget.mergeFanIn`: chặn số run đang trộn theo memory buffers và file cap.
- `createRuns` bên trong `externalSort`: mỗi lô được đọc vào `int[]`, sort và ghi một run đã sắp xếp.
- `mergeSorted`: priority queue giữ **một head mỗi run**, không load toàn run.
- `externalSort`: trộn theo pass cho đến một run; có xử lý input rỗng và carry run lẻ.
- `audit`: so sortedness, số record, min/max, checksum và bảng tần suất độc lập.
- `finally`: xóa tệp tạm do chương trình tạo khi luồng Java còn hoạt động; không bảo đảm dọn được sau crash hoặc kill cứng.

Bài này không phải hệ thống chống lỗi ghi dữ liệu production: nếu cần xuất bản output có tính giao dịch, hãy ghi output tạm riêng rồi công bố khi đã xác minh đúng, với cơ chế atomic move và recovery phù hợp filesystem.

**Lưu thành tệp `BatchSizingExternalSortDemo.java`:**

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class BatchSizingExternalSortDemo {
    private static final int DOMAIN = 10007;
    private static final int OFFSET = 5000;

    record Budget(long workingBytes, long safetyBytes,
                  long fixedBytes, int inputBufferBytes,
                  int outputBufferBytes, int perRunStateBytes,
                  int maxMergeOpenFiles) {
        Budget {
            if (workingBytes <= 0 || safetyBytes < 0
                    || fixedBytes < 0 || inputBufferBytes < 4
                    || outputBufferBytes < 4
                    || perRunStateBytes < 0
                    || maxMergeOpenFiles < 3) {
                throw new IllegalArgumentException(
                        "invalid budget parameters");
            }
        }

        int runCapacity() {
            long available = workingBytes - safetyBytes
                    - fixedBytes - inputBufferBytes
                    - outputBufferBytes;
            if (available < Integer.BYTES) {
                throw new IllegalArgumentException(
                        "not enough memory for one record");
            }
            return (int) Math.min(
                    available / Integer.BYTES,
                    Integer.MAX_VALUE - 8L);
        }

        int mergeFanIn() {
            long available = workingBytes - safetyBytes
                    - fixedBytes - outputBufferBytes;
            long perInput = (long) inputBufferBytes
                    + perRunStateBytes;
            long memoryCap = available / perInput;
            long fileCap = (long) maxMergeOpenFiles - 1;
            long fan = Math.min(memoryCap, fileCap);
            if (fan < 2) {
                throw new IllegalArgumentException(
                        "not enough memory/files for merge");
            }
            return (int) fan;
        }
    }

    record Stats(long records, int capacity, int fanIn,
                 int initialRuns, int mergePasses) {}
    private record Head(int value, int runIndex) {}
    record Audit(long count, int minimum, int maximum,
                 long checksum, boolean sorted,
                 boolean sameMultiset) {}

    private static int generatedValue(int index) {
        return (int) (((long) index * 37L) % DOMAIN)
                - OFFSET;
    }

    private static void createInput(
            Path file, int count, int bufferSize)
            throws IOException {
        try (DataOutputStream out = new DataOutputStream(
                new BufferedOutputStream(
                        Files.newOutputStream(file),
                        bufferSize))) {
            for (int i = 0; i < count; i++) {
                out.writeInt(generatedValue(i));
            }
        }
    }

    private static void mergeSorted(
            List<Path> sources, Path destination,
            Budget budget) throws IOException {
        PriorityQueue<Head> queue = new PriorityQueue<>(
                Comparator.comparingInt(Head::value)
                        .thenComparingInt(Head::runIndex));
        List<DataInputStream> readers = new ArrayList<>();
        long[] remaining = new long[sources.size()];

        try {
            for (int i = 0; i < sources.size(); i++) {
                Path path = sources.get(i);
                long bytes = Files.size(path);
                if (bytes % Integer.BYTES != 0) {
                    throw new IllegalArgumentException(
                            "run size not divisible by four");
                }

                DataInputStream in = new DataInputStream(
                        new BufferedInputStream(
                                Files.newInputStream(path),
                                budget.inputBufferBytes()));
                readers.add(in);

                long count = bytes / Integer.BYTES;
                if (count > 0) {
                    queue.add(new Head(in.readInt(), i));
                    count--;
                }
                remaining[i] = count;
            }

            try (DataOutputStream out = new DataOutputStream(
                    new BufferedOutputStream(
                            Files.newOutputStream(destination),
                            budget.outputBufferBytes()))) {
                while (!queue.isEmpty()) {
                    Head head = queue.remove();
                    out.writeInt(head.value());

                    int stream = head.runIndex();
                    if (remaining[stream] > 0) {
                        queue.add(new Head(
                                readers.get(stream).readInt(),
                                stream));
                        remaining[stream]--;
                    }
                }
            }
        } finally {
            for (DataInputStream in : readers) {
                in.close();
            }
        }
    }

    public static Stats externalSort(
            Path input, Path output, Budget budget)
            throws IOException {
        if (input.toAbsolutePath().normalize().equals(
                output.toAbsolutePath().normalize())) {
            throw new IllegalArgumentException(
                    "input and output must differ");
        }
        long fileBytes = Files.size(input);
        if (fileBytes % Integer.BYTES != 0) {
            throw new IllegalArgumentException(
                    "input size not divisible by four");
        }

        int capacity = budget.runCapacity();
        int fanIn = budget.mergeFanIn();
        long records = fileBytes / Integer.BYTES;
        Path scratch = Files.createTempDirectory(
                "external-merge-runs-");
        List<Path> created = new ArrayList<>();

        try {
            List<Path> runs = new ArrayList<>();
            try (DataInputStream in = new DataInputStream(
                    new BufferedInputStream(
                            Files.newInputStream(input),
                            budget.inputBufferBytes()))) {
                int[] chunk = new int[capacity];
                long unread = records;

                while (unread > 0L) {
                    int used = (int) Math.min(
                            unread, (long) capacity);
                    for (int i = 0; i < used; i++) {
                        chunk[i] = in.readInt();
                    }
                    Arrays.sort(chunk, 0, used);

                    Path run = Files.createTempFile(
                            scratch, "run-", ".bin");
                    created.add(run);
                    try (DataOutputStream out = new DataOutputStream(
                            new BufferedOutputStream(
                                    Files.newOutputStream(run),
                                    budget.outputBufferBytes()))) {
                        for (int i = 0; i < used; i++) {
                            out.writeInt(chunk[i]);
                        }
                    }
                    runs.add(run);
                    unread -= used;
                }
            }

            int initialRuns = runs.size();
            int passes = 0;
            while (runs.size() > 1) {
                List<Path> next = new ArrayList<>();
                for (int start = 0; start < runs.size();
                        start += fanIn) {
                    int end = Math.min(
                            start + fanIn, runs.size());
                    List<Path> group = runs.subList(start, end);

                    if (group.size() == 1) {
                        next.add(group.get(0));
                        continue;
                    }

                    Path merged = Files.createTempFile(
                            scratch, "merge-", ".bin");
                    created.add(merged);
                    mergeSorted(group, merged, budget);
                    next.add(merged);
                }
                runs = next;
                passes++;
            }

            if (runs.isEmpty()) {
                try (OutputStream unused =
                        Files.newOutputStream(output)) {
                    // Empty file is the sorted result.
                }
            } else {
                Files.move(runs.get(0), output,
                        StandardCopyOption.REPLACE_EXISTING);
            }

            return new Stats(
                    records, capacity, fanIn,
                    initialRuns, passes);
        } finally {
            for (Path file : created) {
                Files.deleteIfExists(file);
            }
            Files.deleteIfExists(scratch);
        }
    }

    private static Audit audit(
            Path file, int expectedCount, int bufferSize)
            throws IOException {
        if (Files.size(file)
                != (long) expectedCount * Integer.BYTES) {
            throw new AssertionError(
                    "output record count mismatch");
        }

        int[] expected = new int[DOMAIN];
        for (int i = 0; i < expectedCount; i++) {
            expected[generatedValue(i) + OFFSET]++;
        }

        int[] actual = new int[DOMAIN];
        int prev = Integer.MIN_VALUE;
        int min = Integer.MAX_VALUE;
        int max = Integer.MIN_VALUE;
        long checksum = 0L;
        boolean sorted = true;

        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(
                        Files.newInputStream(file),
                        bufferSize))) {
            for (int i = 0; i < expectedCount; i++) {
                int x = in.readInt();
                if (x < prev) {
                    sorted = false;
                }
                prev = x;
                min = Math.min(min, x);
                max = Math.max(max, x);
                checksum += x;

                int bucket = x + OFFSET;
                if (bucket < 0 || bucket >= DOMAIN) {
                    throw new AssertionError(
                            "unexpected output value");
                }
                actual[bucket]++;
            }
        }

        boolean same = Arrays.equals(expected, actual);
        if (!sorted || !same) {
            throw new AssertionError(
                    "external sort validation failed");
        }
        return new Audit(
                expectedCount, min, max, checksum,
                sorted, same);
    }

    public static void main(String[] args)
            throws IOException {
        Budget budget = new Budget(
                2L * 1024L * 1024L,
                512L * 1024L,
                256L * 1024L,
                64 * 1024,
                64 * 1024,
                128,
                3);

        System.out.println(
                "run capacity = " + budget.runCapacity());
        System.out.println(
                "merge fan-in = " + budget.mergeFanIn());

        Path work = Files.createTempDirectory(
                "external-sort-lesson-");
        Path input = work.resolve("input.bin");
        Path sorted = work.resolve("sorted.bin");
        Path emptyInput = work.resolve("empty-input.bin");
        Path emptyOutput = work.resolve("empty-output.bin");
        Path invalidInput = work.resolve("invalid-input.bin");

        try {
            int count = 700000;
            createInput(
                    input, count, budget.outputBufferBytes());
            Stats stats = externalSort(input, sorted, budget);
            Audit proof = audit(
                    sorted, count, budget.inputBufferBytes());

            System.out.println(
                    "input bytes = " + Files.size(input));
            System.out.println(
                    "initial runs = " + stats.initialRuns());
            System.out.println(
                    "merge passes = " + stats.mergePasses());
            System.out.println(
                    "sorted records = " + proof.count());
            System.out.println(
                    "minimum = " + proof.minimum());
            System.out.println(
                    "maximum = " + proof.maximum());
            System.out.println(
                    "checksum = " + proof.checksum());
            System.out.println(
                    "sorted nondecreasing = " + proof.sorted());
            System.out.println(
                    "multiset preserved = "
                    + proof.sameMultiset());

            Files.write(emptyInput, new byte[0]);
            Stats empty = externalSort(
                    emptyInput, emptyOutput, budget);
            System.out.println(
                    "empty: runs=" + empty.initialRuns()
                    + ", passes=" + empty.mergePasses()
                    + ", bytes=" + Files.size(emptyOutput));

            Files.write(invalidInput, new byte[] {1, 2, 3});
            try {
                externalSort(
                        invalidInput,
                        work.resolve("bad-output.bin"),
                        budget);
            } catch (IllegalArgumentException error) {
                System.out.println(
                        "invalid input: " + error.getMessage());
            }

            try {
                new Budget(
                        2048L, 2048L, 0L,
                        16, 16, 0, 3).runCapacity();
            } catch (IllegalArgumentException error) {
                System.out.println(
                        "invalid budget: " + error.getMessage());
            }
            System.out.println("all checks passed = true");
        } finally {
            Files.deleteIfExists(input);
            Files.deleteIfExists(sorted);
            Files.deleteIfExists(emptyInput);
            Files.deleteIfExists(emptyOutput);
            Files.deleteIfExists(invalidInput);
            Files.deleteIfExists(work);
        }
    }
}
~~~

### Biên dịch/chạy

~~~bash
javac BatchSizingExternalSortDemo.java
java BatchSizingExternalSortDemo
~~~

**Stdout dự kiến đúng theo dữ liệu và ngân sách:**

~~~text
run capacity = 294912
merge fan-in = 2
input bytes = 2800000
initial runs = 3
merge passes = 2
sorted records = 700000
minimum = -5000
maximum = 5006
checksum = 1897415
sorted nondecreasing = true
multiset preserved = true
empty: runs=0, passes=0, bytes=0
invalid input: input size not divisible by four
invalid budget: not enough memory for one record
all checks passed = true
~~~

**Giới hạn minh họa:** `Budget` dự trù các buffer, mảng dữ liệu và một phần overhead theo mô hình, nhưng không đo/tự áp đặt toàn bộ memory process. Java object headers, quản lý stream, garbage collection, native memory và OS cache có thể làm footprint thực cao hơn. Chương trình cũng không tự đặt disk quota hay bảo đảm khôi phục đầy đủ khi process bị kill.

## 13. Chứng minh tính đúng của hai pha sort

### Run generation

Mỗi lô đọc tối đa c bản ghi thực tế, sắp xếp chúng bằng `Arrays.sort(chunk,0,used)` rồi ghi đúng `used` phần tử. Vì `unread` giảm đúng `used`, mọi bản ghi input thuộc đúng một run. Mỗi run đã tăng dần; các run hợp lại chứa đúng đa tập input.

### K-way merge

Bất biến: priority queue chứa **phần tử chưa xuất nhỏ nhất** của mỗi run còn dữ liệu. Mỗi run đã sort nên phần tử nhỏ nhất trong toàn bộ dữ liệu chưa xuất nằm trong một trong các head.

Lấy head nhỏ nhất toàn queue làm output tiếp theo. Sau khi xuất head của run i, lấy phần tử tiếp theo của đúng run i để phục hồi bất biến. Vì vậy output không giảm, không bỏ/nhân đôi phần tử.

Các pass trộn mỗi nhóm run theo nguyên tắc ấy, còn nhóm một run giữ nguyên. Chúng duy trì tính đúng của đa tập. Khi chỉ còn một run, run đó đã sort và chứa toàn bộ input, nên là đáp án chính xác.

### Giá trị bằng nhau

Với các số nguyên, các giá trị bằng nhau không có payload khác để phân biệt. Nếu dữ liệu thực là `(key,record)` và cần stable sort, phải thiết kế cách giữ thứ tự tương đối cho các bản ghi có key bằng nhau, ví dụ lưu original ordinal và xử lý tie theo ordinal. Không suy ra tính stable từ demo sort `int` này.

## 14. Kiểm chứng output bằng oracle độc lập

Chỉ biết tệp được sắp xếp **không chứng minh** đã giữ đủ dữ liệu: tệp bỏ mất một số phần tử vẫn có thể tăng dần. Chỉ biết checksum cũng không đủ vì hai đa tập khác nhau có thể cùng tổng.

Demo kiểm:

1. **Count:** số byte output đúng `700000*4`.
2. **Sortedness:** mỗi giá trị đọc không nhỏ hơn giá trị trước.
3. **Range:** mọi giá trị output thuộc miền `[−5000,5006]`.
4. **Exact multiset:** tạo bảng tần suất kỳ vọng từ công thức input, so với bảng tần suất output.
5. **Checksum/min/max:** in thêm để phát hiện chênh lệch trong debug.

Bảng tần suất có 10.007 phần tử `int`, khoảng 40 KiB payload, nhưng thuộc **giai đoạn kiểm thử sau khi sort**, không phải payload mà external sort cần giữ lúc tạo run.

Trên dữ liệu production có khóa không giới hạn và N quá lớn, không thể luôn có một frequency array nhỏ. Khi ấy kiểm thử bằng tập input nhỏ và oracle khác ý tưởng, integrity check nhiều tầng, hoặc cơ chế kiểm dữ liệu mạnh hơn là cần thiết.

### Không thay chứng minh bằng ví dụ

Test 700.000 int là một trường hợp dữ liệu lớn và có giá trị trùng. Chứng minh tổng quát vẫn dựa trên bất biến run và merge. Một output đúng không chứng minh không có lỗi ở case input rỗng, thiếu byte, bộ nhớ thiếu hoặc tệp nhiều run hơn.

## 15. Lô quá nhỏ, quá lớn và điểm cân bằng

### Lô nhỏ

Tạo nhiều tệp run, tăng chi phí metadata, open/close, số pass merge, chi phí request và overhead cố định trên mỗi lô. Với k=2, tăng run từ 3 lên 700 sẽ tăng số pass từ 2 lên khoảng 10.

### Lô lớn

Có thể giảm số run và pass, nhưng tăng peak heap, GC, bộ nhớ lưu dữ liệu tạm và thời gian chờ một lô hoàn thành. Nếu vượt giới hạn thì throughput thực có thể **giảm mạnh** do paging/GC hoặc task thất bại.

### Cách benchmark

Thử các cấu hình batch capacity khác nhau trong phạm vi RAM được phép, giữ cố định cùng input, máy và số worker. Ghi:

- Thông lượng bản ghi/giây và số byte/giây.
- Peak heap/RSS và GC pauses.
- Số run và merge passes.
- Disk read/write bytes logic và quan sát, thời gian chờ I/O.
- Số file descriptors mở đỉnh và dung lượng disk tạm.
- Latency đến output đầu tiên, throughput toàn hệ thống.

Không kết luận một kích thước là tối ưu chỉ dựa vào Big-O hoặc một lần đo. Ở máy khác, storage và GC khác có thể dẫn đến lựa chọn khác.

## 16. Khi có nhiều worker đồng thời

Nếu p worker xử lý batch cùng lúc, tổng bộ nhớ không còn là một lô:

~~~text
totalApprox
 = sharedFixed
 + p * (perWorkerBuffers + perWorkerPayload + state)
 + queuedBatchBytes
 + safetyReserve
~~~

Ví dụ 8 worker mỗi worker dùng 80 MiB đã cần khoảng 640 MiB **chỉ riêng các worker**, trước khi cộng queue, runtime và dự phòng. Nếu container chỉ có 512 MiB, kế hoạch không hợp lệ dù từng worker chạy đơn lẻ ổn.

### File cap khi merge song song

Một merge k-way cần `k+1` tệp mở. Nếu chạy p merges đồng thời, phần này có thể cần `p*(k+1)` descriptor, chưa tính các tài nguyên khác. Không dùng một giới hạn tệp mở của **một** merge làm giới hạn cho **toàn** hệ thống.

### Queue hữu hạn

Giới hạn backlog theo byte hoặc số batch, dừng producer khi consumer chưa kịp xử lý. Nếu chỉ điều chỉnh batch size nhưng queue không chặn, dữ liệu tích tụ vẫn gây OOM.

## 17. Bản ghi biến dài, streaming và điều chỉnh thích nghi

Trong CSV/JSON/log, chọn batch theo **số byte thực tế được giữ** hoặc ước lượng có kiểm chứng; không chỉ đếm số dòng.

~~~text
targetBatchBytes
  = memoryBudget - safety - fixed - allBuffers

if estimatedRecordBytes > targetBatchBytes:
    spill / stream / reject

else:
    accumulate while estimatedTotal <= targetBatchBytes
    process batch
    release batch
~~~

Nếu quá trình parse tạo các object có overhead lớn, byte trên đĩa chỉ là **một phần** chi phí. Lấy trung bình của vài dòng đầu không phải cận trên cho mọi dòng. Có thể dùng giới hạn byte mềm, size histogram, cùng một lối xử lý overflow rõ ràng.

### Điều chỉnh thích nghi

Theo dõi memory peak, GC pressure và tốc độ I/O. Nếu gần hạn mức, giảm lô hoặc concurrency; nếu lô quá nhỏ, overhead lớn và còn headroom ổn định, tăng lô theo bước nhỏ. Có **min/max và hysteresis** để tránh batch size dao động liên tục.

### Một record quá lớn

Nếu một bản ghi duy nhất lớn hơn payload budget, cần streaming từng mảnh nếu ngữ nghĩa cho phép, externalize payload lớn, hoặc báo lỗi rõ. Không được cắt bớt dữ liệu để “vừa RAM” nếu đầu ra đòi chính xác.

## 18. Ứng dụng trong các workload khác

### ETL

Nhiều dòng CSV/JSON được đọc, chuẩn hóa rồi bulk insert. Cần tính parse overhead, query parameter limit và transaction size, ngoài memory. Một batch DB quá lớn có thể tăng thời gian khóa/rollback; quá nhỏ tăng commit overhead.

### Hash aggregation

Bảng hash lưu **số nhóm distinct**, không chỉ một batch dữ liệu đầu vào. Với khóa phân bố lệch, một partition có thể vượt RAM; phải dùng spill/partitioning và kiểm skew. Chọn lô theo byte input thuần chưa đủ cho bảng hash.

### Hash join và sort-merge join

Hash join phải lưu build-side hash table hoặc partition của nó. Sort-merge join dùng run, buffer và quy trình merge. Đừng dùng cùng công thức cho hai loại state nếu chi phí cấu trúc khác nhau.

### Machine learning

Một batch có thể tạo activation tensors, gradients và workspace nhiều lần kích thước input. Memory bound phụ thuộc sequence length, model, dtype và framework. Kích thước batch không thể chọn chỉ từ số mẫu hay dung lượng file.

### Streaming logs

Có thể flush batch khi đạt **ngưỡng số byte, số bản ghi hoặc thời gian tối đa**, để không phải chờ lô đầy mãi trong giờ ít dữ liệu. Khi có offset và exactly-once semantics, cần xử lý đúng thứ tự, retry và checkpoint.

## 19. Sai lầm phổ biến và ca biên

| Sai lầm | Vấn đề | Hướng sửa |
| --- | --- | --- |
| Chọn một số record cố định cho mọi dataset | Không xét kích thước | Dùng byte budget |
| Dùng độ dài ký tự làm số byte UTF-8 | Sai với Unicode | Đếm byte encoding |
| Chỉ tính payload mà bỏ header/object | Đánh giá RAM quá thấp | Đo footprint, dự phòng |
| Dùng toàn bộ RAM làm Mwork | Quên JVM/OS/task khác | Tách working budget |
| Không tính buffer in/out | M vượt giới hạn | Trừ buffer trước |
| Không tính nhiều run reader | Merge OOM | Fan-in theo RAM |
| Quên giới hạn file mở | Too many open files | Chặn k+1 và concurrency |
| k=1 vẫn mong giảm run | Không tiến triển | Bắt k≥2 |
| Tạo quá nhiều run nhỏ | I/O nhiều pass | Tăng lô nếu có thể |
| Nhân đôi batch qua queue | Peak tăng | Backpressure |
| Tính theo record size trung bình | Outlier gây OOM | Cận/overflow path |
| Không xử lý record quá lớn | Crash hoặc loop | Spill/stream/reject |
| Quên lô cuối chưa đầy | Sai số bản ghi | Ghi đúng used |
| Không xét input rỗng | Lỗi chỉ số | Output rỗng |
| Chỉ kiểm checksum | Không bắt mọi lỗi | Count, sorted, multiset |
| Trộn run chưa sort | Output sai | Giữ bất biến |
| Dùng `int` cho số byte lớn | Overflow | Dùng `long` |
| Nhầm MiB với MB | Sai ngân sách | Ghi rõ đơn vị |
| Dùng một k cho mọi worker | Tổng file cap vượt | Tính global |
| Không dự trù dung lượng đĩa tạm | Đầy đĩa | Disk-space budget |
| Không dọn tệp khi lỗi | Rò rỉ dung lượng | Cleanup/recovery |
| Gọi working budget là hard heap limit | Khẳng định sai | Đo RSS/heap thật |
| Tăng batch mà không đo GC | Có thể chậm hơn | Benchmark |
| In ra “đã tối ưu” sau một phép đo | Không chứng minh | Báo điều kiện thử nghiệm |

### Ca biên cần test

- N=0: 0 run, 0 pass, output rỗng.
- N đúng bằng capacity: một run, không merge.
- N=capacity+1: phải có hai run.
- N=2·capacity+1: có ba run, với k=2 cần hai pass.
- Số byte input không chia hết cho 4: tệp binary sai cấu trúc.
- Trọng số/giá trị âm, trùng và nằm ở biên của kiểu số.
- Budget quá nhỏ để chứa một bản ghi, hoặc không đủ mở hai input và một output.
- Có nhiều run hơn khả năng open file; không được mở tất cả một lúc.
- Số file tạm và disk space phải được quản lý ngay cả khi chương trình gặp exception.

### Tệp tạm và lỗi hệ thống

`finally` giúp dọn file nếu luồng Java đi qua `finally`, nhưng không xử lý được mọi trường hợp mất điện/process kill. Với production, dùng scratch dir được quản lý, dọn rác theo job ID, output tạm và quy trình publish an toàn khi kết quả đã hoàn chỉnh.

## 20. Bài tập và checklist cuối

### Bài tập

1. Phân biệt in-memory sort và external merge sort.
2. Định nghĩa N, M, B trong mô hình bộ nhớ ngoài.
3. Quy đổi 2 MiB thành byte.
4. Phân biệt MB và MiB.
5. Nêu tất cả khoản S,F,I,O,P,H.
6. Giải thích vì sao Mwork không đồng nghĩa toàn RAM máy.
7. Với Mwork=2MiB,S=512KiB,F=256KiB,I=O=64KiB, tính payload.
8. Chia payload cho 4 để tính capacity int.
9. Tính kích thước file của 700.000 int.
10. Chia thành ba run và nêu độ dài run cuối.
11. Giải thích tại sao lô cuối không được đệm thêm số.
12. So 1.000 int/lô với 294.912 int/lô về số run.
13. Nêu phản ví dụ chọn batch theo số dòng trung bình.
14. Đếm byte của một UTF-8 string chứa ký tự đa byte.
15. Giải thích vì sao heap object lớn hơn serialized bytes.
16. Thiết kế batch builder theo giới hạn byte thay vì count.
17. Nêu ba cách xử lý một record quá lớn.
18. Chứng minh bất biến mỗi run đã sort.
19. Chứng minh merge chọn head nhỏ nhất luôn đúng.
20. Chứng minh merge bảo toàn đa tập.
21. Tính fan-in từ Mwork,S,F,O,I và H.
22. Giải thích giới hạn D file.
23. Vì sao D=3 làm k=2?
24. Mô phỏng hai merge passes khi R=3.
25. Tính bytes đọc/ghi run generation.
26. Tính I/O pass 1 chỉ merge 589.824 int.
27. Tính tổng logical I/O là 15.918.592 bytes.
28. Điều gì thay đổi nếu được phép mở 4 file?
29. Vì sao k=1 không giảm số run?
30. Viết giả mã trộn k run với PriorityQueue.
31. Chứng minh priority queue không chứa toàn bộ dữ liệu.
32. Tạo và đọc tệp binary int trong Java.
33. Kiểm số byte file chia hết cho 4.
34. Kiểm số lượng output record sau sort.
35. Kiểm output không giảm.
36. Chứng minh checksum đơn lẻ không đủ kiểm đa tập.
37. Thiết kế oracle theo frequency array cho miền hẹp.
38. Kiểm case N=capacity+1.
39. Test input rỗng và input lỗi 3 byte.
40. Tạo budget khiến capacity<1 rồi kiểm exception.
41. Giải thích việc cleanup tệp tạm trong `finally`.
42. Nêu giới hạn cleanup khi process bị kill.
43. Ước lượng peak memory khi có 8 worker.
44. Thiết kế bounded queue với backpressure.
45. So throughput và latency của batch lớn/nhỏ.
46. Đề xuất benchmark có đo peak RSS, heap và GC.
47. Chọn batch cho ETL JSON với bản ghi biến dài.
48. Chọn batch cho hash aggregation có nhiều nhóm.
49. Giải thích vì sao ML batch còn tốn activation memory.
50. Thiết kế flush theo byte/count/time cho stream.
51. Xác định khi nào phải dùng spill-to-disk.
52. Nêu rủi ro thiếu disk space cho run trung gian.
53. Phân biệt I/O logic và số I/O vật lý.
54. Lập kế hoạch phối hợp batch size và concurrency.
55. Nêu vì sao không có một capacity tối ưu cho mọi dataset.
56. Viết checklist kiểm tra memory/headroom/file cap trước triển khai.

### Checklist

- Đã thống nhất byte, KiB, MiB, số record chưa?
- Mwork là **ngân sách thuật toán**, không nhầm với toàn heap?
- Đã trừ safety, fixed state, input/output buffer, workspace?
- Record size là cận trên hay chỉ trung bình?
- Có xử lý record vượt lô và backpressure?
- Có tính toàn bộ batch đồng thời cùng queue?
- Run cuối ghi đúng số phần tử thực?
- Merge fan-in chặn bởi cả RAM và file descriptor?
- Đã có `k≥2` khi cần trộn nhiều run?
- Đã kiểm input format, sortedness, count và multiset?
- Đã đo peak memory, I/O, throughput và thời gian GC?
- Đã dự phòng disk tạm, cleanup và recovery khi lỗi?

**Kết luận:** Kích thước lô là kết quả **lập ngân sách theo byte** và **đánh đổi chi phí**. Với bản ghi cố định:

~~~text
runCapacity
  = floor((Mwork-S-F-I-O)/bytesPerRecord)

mergeFanIn
  = min(
      floor((Mwork-S-F-O)/(inputBuffer+perRunState)),
      maxMergeOpenFiles-1,
      numberOfRuns
    )
~~~

Lô lớn hơn có thể giảm số run/pass nhưng tăng peak memory và latency; lô nhỏ hơn dễ khống chế RAM nhưng tăng I/O và overhead. Với bản ghi biến dài, các cấu trúc bổ sung và worker song song, luôn dùng byte budget, đo thực tế và backpressure/spill. **Đừng coi một công thức lập kế hoạch là giới hạn RAM cứng**, và đừng đánh đổi tính đúng của dữ liệu để làm lô vừa bộ nhớ.
