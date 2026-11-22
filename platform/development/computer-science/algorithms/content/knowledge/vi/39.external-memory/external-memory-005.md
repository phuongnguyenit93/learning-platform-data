# Sinh các đoạn có thứ tự ban đầu

**Sinh các đoạn có thứ tự ban đầu (initial sorted run generation)** là giai đoạn đầu của **external merge sort — sắp xếp trộn ngoài bộ nhớ**. Khi tập dữ liệu lớn hơn RAM, ta không thể nạp toàn bộ dữ liệu rồi gọi hàm sort một lần. Thay vào đó, thuật toán đọc dữ liệu **tuần tự từ đĩa**, tạo ra nhiều **đoạn/run đã được sắp tăng dần**, ghi từng run xuống tệp tạm, rồi ở các lượt sau **trộn các run** thành một dãy có thứ tự toàn cục.

Bài học thuộc nhóm **Ngoài bộ nhớ** của Computer Science Algorithms, tập trung đúng vào cách **tạo các sorted runs ban đầu**. Hai phương pháp chính là **chia lô cố định rồi sắp từng lô (fixed-size run generation/chunk sorting)** và **replacement selection (chọn thay thế bằng heap, tạm đóng băng phần tử không còn thuộc run hiện tại)**. Ta sẽ phân tích bộ nhớ, số lượt đọc/ghi đĩa (I/O), tính ổn định khi khóa trùng, mô hình active/frozen heap, sự khác nhau giữa run dài và số run ít, cách run được trộn qua nhiều lượt, chương trình Java 17+ ghi tệp thật, bộ kiểm thử với oracle độc lập, lỗi thường gặp và bài tập có lời giải.

## 1. Vì sao phải tạo sorted runs?

Giả sử một hệ thống có N bản ghi trên SSD/HDD, nhưng RAM chỉ chứa tối đa M bản ghi cùng lúc, với `N≫M`. Nếu thuật toán cố gọi `Collections.sort` sau khi đọc toàn bộ N bản ghi vào một `ArrayList`, bộ nhớ có thể vượt giới hạn, phát sinh swap rất nặng hoặc `OutOfMemoryError`.

Một quy trình external merge sort chuẩn gồm:

1. **Run generation:** đọc đầu vào tuần tự, sắp các nhóm bản ghi vừa RAM, ghi ra một hoặc nhiều **sorted runs** trên đĩa.
2. **Merge passes:** trộn nhiều runs đã có thứ tự bằng cách giữ một phần tử/đệm đầu của mỗi run trong RAM và ghi một run lớn hơn.
3. **Final output:** khi chỉ còn một run, nó là dãy được sắp toàn cục.

Bài này nhấn mạnh **bước 1**, nhưng cũng cài một bước **k-way merge** nhỏ để kiểm chứng rằng các run ban đầu có thể tạo ra kết quả cuối cùng đúng.

### Một run chính xác là gì?

Một **run** là một **chuỗi bản ghi có thứ tự không giảm theo khóa sắp xếp**. Ví dụ:

`[1, 3, 3, 8]` là một run tăng dần; `[1, 8, 3]` **không** là run tăng dần.

Hai run riêng lẻ không cần có ranh giới khóa toàn cục đúng. Ví dụ:

- Run 1: `[2, 5, 9]`.
- Run 2: `[1, 3, 7]`.

Cả hai đều là sorted runs, dù 1 ở run 2 nhỏ hơn 9 ở run 1. **Không được chỉ nối các run** để tạo output: phải **trộn (merge)** chúng theo thứ tự khóa.

### Run không giống một khối I/O

**Run** là dãy bản ghi đã sắp, có thể dài hàng triệu phần tử và nằm trong nhiều khối vật lý.

**I/O block/page** là đơn vị trao đổi dữ liệu giữa RAM và thiết bị lưu trữ (thường một vùng byte hoặc một số bản ghi).

Một run dài 1.000.000 bản ghi có thể chiếm hàng nghìn I/O blocks; “đã sắp thành một run” **không có nghĩa toàn run nằm trong RAM**.

## 2. Ký hiệu và mô hình chi phí

Đặt:

- `N`: tổng số bản ghi đầu vào.
- `M`: số bản ghi có thể giữ trong bộ nhớ làm việc của run generator; `M≥1`.
- `b`: số bản ghi vừa trong một **I/O block** (để tránh nhầm với M); giả sử kích thước bản ghi cố định trong mô hình lý thuyết.
- `R`: số sorted runs ban đầu được sinh ra.
- `f`: số run đầu vào có thể được trộn cùng lúc trong một merge pass (fan-in).
- `K`: khóa sắp xếp; bản ghi còn có thể có payload và vị trí xuất hiện ban đầu.

Trong I/O model, đọc một lần toàn bộ N bản ghi tốn xấp xỉ `N/b` lượt đọc block, và ghi N bản ghi ra các run tốn xấp xỉ `N/b` lượt ghi block:

\[
\text{I/O run generation}\approx 2N/b.
\]

Đây là **chi phí block lý tưởng**, chưa tính metadata, seek, hệ thống tệp, nén dữ liệu, write-ahead log, bộ đệm hệ điều hành hoặc chi phí đồng bộ. CPU sorting và I/O là **hai đại lượng cần phân biệt**.

### Vì sao ưu tiên truy cập tuần tự?

Thiết bị lưu trữ thường phát huy tốt thông lượng khi đọc/ghi theo dải liên tiếp. Sinh các run bằng đọc một luồng đầu vào và ghi các tệp tuần tự tránh nhiều truy cập ngẫu nhiên tới các vị trí xa nhau trên đĩa. Trên HDD, seek là vấn đề lớn; SSD cũng có chi phí I/O và throughput riêng.

Run generation không chỉ là bài toán so sánh khóa; nó còn là bài toán **dòng dữ liệu, giới hạn RAM và lượt I/O**.

## 3. Cách 1 — Chia lô cố định và sắp từng lô

**Fixed-size run generation** làm việc như sau:

1. Cấp bộ đệm chứa tối đa M bản ghi.
2. Đọc lần lượt tới M bản ghi từ file nguồn.
3. Sắp các bản ghi trong RAM theo khóa.
4. Ghi tuần tự nhóm đã sắp thành **một run file**.
5. Giải phóng/ghi đè bộ đệm và xử lý nhóm tiếp theo.
6. Nếu cuối file còn ít hơn M bản ghi, sắp và ghi nốt run cuối.

Giả mã:

~~~text
FIXED_RUNS(input, M):
    require M >= 1
    runs = []
    repeat:
        buffer = READ_AT_MOST_M_RECORDS(input)
        if buffer is empty: break
        SORT(buffer, by key and stable tie-breaker)
        file = NEW_RUN_FILE()
        WRITE_ALL(buffer, file)
        CLOSE(file)
        runs.add(file)
    return runs
~~~

### Bất biến

Mỗi run được tạo bằng cách sắp **toàn bộ các bản ghi của một lô** trước khi ghi, nên nó có thứ tự không giảm. Các lô liên tiếp **không giao nhau** và phủ toàn bộ input. Vì vậy:

- Mỗi input record xuất hiện trong **đúng một run**.
- Bên trong mỗi run, khóa không giảm.
- Tổng số bản ghi trên mọi run bằng N.

### Số run chắc chắn biết trước

Với N>0:

\[
R_{\text{fixed}}=\left\lceil\frac{N}{M}\right\rceil.
\]

Với N=0, `R=0`. Run cuối có thể ít hơn M bản ghi, không được đọc thêm dữ liệu đã hết hoặc tạo một run rỗng không cần thiết.

### Chi phí

Một lô M bản ghi được sort bằng so sánh trong O(M log M). Với toàn bộ dữ liệu:

\[
T_{\text{CPU}}=O(N\log M)
\]

cho bước sort, ngoài chi phí phân tích và ghi tệp. Dung lượng dữ liệu giữ trong RAM khoảng O(M) bản ghi, chưa tính các buffers phụ và metadata của runtime. I/O lý tưởng là **đọc N, ghi N**: khoảng `2N/b` lượt block.

**Ưu điểm:** đơn giản, dễ kiểm thử, số run dự đoán chính xác, hoạt động tốt với mọi thứ tự input.

**Hạn chế:** ngay cả input đã sắp tăng dần, nó vẫn tạo \(\lceil N/M\rceil\) runs dù toàn bộ input vốn đã là một run lớn.

## 4. Ví dụ fixed-size với N=11, M=4

Dòng khóa nguồn theo thứ tự xuất hiện:

`[8,1,6,6,2,7,3,9,0,5,4]`.

Ta đánh số mỗi bản ghi bằng **ordinal** bắt đầu từ 0. Dùng ký hiệu `key#ordinal` để phân biệt các bản ghi có cùng khóa, ví dụ `6#2` và `6#3`.

Ba lô đầu vào:

- Lô 1: `8#0,1#1,6#2,6#3`.
- Lô 2: `2#4,7#5,3#6,9#7`.
- Lô 3: `0#8,5#9,4#10`.

Sau khi sort riêng từng lô, ba run ban đầu là:

~~~text
run1=[1#1, 6#2, 6#3, 8#0]
run2=[2#4, 3#6, 7#5, 9#7]
run3=[0#8, 4#10, 5#9]
~~~

Số run là \(\lceil 11/4\rceil=3\). Dễ thấy **nối ba run lại không tạo dãy đã sắp**, vì khóa 2 ở run2 nhỏ hơn 8 ở cuối run1.

### Tính ổn định với khóa trùng

Nếu có hai bản ghi cùng key, thuật toán sort ổn định phải duy trì **thứ tự đến trước** của chúng. Trong ví dụ, hai bản ghi khóa 6 xuất hiện lần lượt với ordinal 2 rồi 3, nên trong kết quả cuối phải có `6#2` trước `6#3`.

Một cách bảo đảm ổn định rõ ràng, kể cả sau nhiều lượt merge, là dùng khóa sắp xếp tổng hợp:

\[
(\text{key},\ \text{originalOrdinal})
\]

theo thứ tự từ điển. `ordinal` là thứ tự **toàn cục**, không phải vị trí cục bộ trong mỗi run. Cách này khiến mọi record có thứ tự rõ ràng, ngay cả khi key bằng nhau ở **những run khác nhau**.

Nếu record có payload, ta chỉ dùng khóa+ordinal để quyết định thứ tự nhưng vẫn phải ghi/đọc **đủ payload**; không được làm mất trường dữ liệu trong lúc sort.

## 5. Cách 2 — Replacement selection

**Replacement selection** tìm cách sinh một run **dài hơn M** mặc dù tại mọi thời điểm heap chỉ giữ tối đa M bản ghi.

Ý tưởng: thay vì đợi gom đủ một lô M rồi đóng run, ta:

1. Ban đầu đọc tối đa M record vào một **min-heap active** theo `(key,ordinal)`.
2. Lấy record nhỏ nhất trong active ra, ghi ngay vào run hiện tại.
3. Đọc **một record mới** từ đầu vào để thay chỗ vừa giải phóng.
4. Nếu `new.key≥lastEmittedKey`, record mới vẫn có thể nằm trong run hiện tại: đưa vào **active heap**.
5. Nếu `new.key<lastEmittedKey`, record mới **không thể** tiếp nối run không giảm: đưa vào **frozen heap** để dành cho run sau.
6. Khi active trống, **đóng run hiện tại**. Chuyển frozen thành active, làm rỗng frozen và bắt đầu run mới.
7. Lặp cho đến khi hết input và cả hai heap trống.

Một số giáo trình triển khai bằng một heap và cờ “frozen”; dùng **hai heap active/frozen** giúp nhìn rõ bất biến hơn. Quan trọng là **tổng số record trong cả hai heap không vượt M**. Không phải hai heap đều được cấp tối đa M record mới, khiến hệ thống vượt gấp đôi ngân sách logic.

### Vì sao phải đóng băng?

Giả sử đã ghi khóa 8 vào run hiện tại. Nếu record mới tới có khóa 5 và ghi ngay, run sẽ chứa `…8,5…`, **không còn tăng dần**. Không thể đưa 5 vào cùng run vì phần 8 đã ghi ra file và không được “rút lại” để đổi thứ tự. Record 5 phải đợi run kế tiếp.

**Không được bỏ bản ghi 5**, cũng không thể sửa đầu ra đã ghi để cứu một run mà không cần giải thuật phức tạp hơn.

### Giả mã

~~~text
REPLACEMENT_SELECTION(input, M):
    require M >= 1
    active  = min_heap(key, originalOrdinal)
    frozen  = min_heap(key, originalOrdinal)
    fill active with at most M input records

    while active not empty:
        open a new run file
        lastKey = -infinity

        while active not empty:
            x = active.popMin()
            assert x.key >= lastKey
            WRITE(x)
            lastKey = x.key

            if another input record y exists:
                if y.key >= lastKey:
                    active.push(y)
                else:
                    frozen.push(y)

        close current run
        active = frozen
        frozen = new empty min_heap

    return run files
~~~

**Ràng buộc:** mỗi lần ghi một record, tối đa một record mới được nạp. Như vậy active.size + frozen.size ≤M luôn đúng. Khi active cạn, frozen có thể có những khóa nhỏ hơn các khóa run trước, nhưng đó là điều hợp lệ vì **chúng thuộc run mới**.

## 6. Chứng minh replacement selection tạo sorted runs đúng

### Bất biến 1: run hiện tại luôn không giảm

Ban đầu active là min-heap của tối đa M bản ghi. Khi pop x, vì x là phần tử nhỏ nhất của active, mọi record active còn lại có khóa ≥x.key.

Khi đọc record mới y:

- Nếu y.key≥x.key, y được đưa vào active. Nó vẫn hợp lệ với ngưỡng đã ghi.
- Nếu y.key<x.key, y được đưa vào frozen và không thể được xuất trong run hiện tại.

Vì vậy record active được xuất ở bước sau không có khóa nhỏ hơn record vừa ghi. Quy nạp theo số lần pop: **mỗi run tăng không giảm theo key**.

### Bất biến 2: bảo toàn tất cả bản ghi

Mỗi record đầu vào được đọc **một lần**, đưa vào active hoặc frozen. Mỗi record được pop khỏi active **một lần**, ghi đúng một lần rồi không còn trong heap. Chuyển frozen sang active không tạo bản sao. Đến khi hết input và active/frozen trống, **mọi record đã được xuất đúng một lần**.

### Bất biến 3: không vượt bộ nhớ dữ liệu

Ban đầu có tối đa M record. Mỗi vòng lặp pop một record, giảm tổng heap đi 1; sau đó đọc và chèn tối đa một record, tăng lại tối đa 1. Đổi active/frozen giữa các run chỉ chuyển tham chiếu. Do đó:

\[
|active|+|frozen|\le M.
\]

Ngoài M record trong heap còn cần bộ đệm đọc/ghi, đối tượng heap, parser, đường dẫn run, v.v. Khi triển khai ngoài thực tế, **RAM vật lý cần dự trù cả overhead**, không chỉ đếm M record lý tưởng.

### Tính ổn định khi key trùng

Ưu tiên `(key,ordinal)` trong mỗi heap. Record mới có key **bằng** lastKey được phép vào active. Do ordinal chỉ tăng khi đọc input, hai record cùng key sẽ được xuất theo thứ tự ordinal trong run, và merge cuối vẫn dùng bộ so sánh ấy. Nhờ đó **tính ổn định toàn cục** được giữ.

Nếu chỉ so sánh key và chọn tùy ý khi bằng nhau, output vẫn có thứ tự key đúng, nhưng có thể **không ổn định** đối với payload đi cùng khóa.

## 7. Ví dụ replacement selection với cùng dữ liệu

Input:

`[8,1,6,6,2,7,3,9,0,5,4]`, `M=4`.

Active ban đầu gồm: `8#0,1#1,6#2,6#3`.

Quá trình run đầu:

| Lần xuất | Record xuất | Record mới đọc | Nơi chèn record mới |
| ---: | --- | --- | --- |
| 1 | 1#1 | 2#4 | active vì 2≥1 |
| 2 | 2#4 | 7#5 | active vì 7≥2 |
| 3 | 6#2 | 3#6 | frozen vì 3<6 |
| 4 | 6#3 | 9#7 | active vì 9≥6 |
| 5 | 7#5 | 0#8 | frozen vì 0<7 |
| 6 | 8#0 | 5#9 | frozen vì 5<8 |
| 7 | 9#7 | 4#10 | frozen vì 4<9 |

Sau lần 7, active trống, nhưng frozen chứa `0#8,3#6,4#10,5#9`. Đóng run 1 và bắt đầu run 2 bằng frozen.

Hai run thu được:

~~~text
run1=[1#1, 2#4, 6#2, 6#3, 7#5, 8#0, 9#7]
run2=[0#8, 3#6, 4#10, 5#9]
~~~

So sánh:

- **Fixed-size:** 3 runs với độ dài `[4,4,3]`.
- **Replacement selection:** 2 runs với độ dài `[7,4]`.

Run dài 7 record được tạo dù heap chỉ giữ **4 record cùng lúc**. Đây là điểm mạnh cốt lõi của replacement selection.

### Vì sao run 2 có thể bắt đầu bằng 0?

Ở run 1 ta đã ghi 9, nhưng **run 2 là một tệp mới**, không yêu cầu khóa đầu của run 2 lớn hơn khóa cuối của run 1. Các run sẽ được merge sau. Nếu cố ràng buộc `min(run2)≥max(run1)`, ta sẽ không thể sắp nhiều đầu vào thực tế khi RAM hạn chế.

## 8. Chiều dài run: lợi ích và giới hạn

### Input tăng dần

Với M=4 và:

`[0,1,2,3,4,5,6,7,8,9,10]`,

fixed-size tạo 3 runs. Replacement selection liên tục nhận phần tử mới có key≥lastKey, nên **chỉ tạo 1 run dài 11**, dù M=4.

### Input giảm dần

Với:

`[10,9,8,7,6,5,4,3,2,1,0]`,

mọi phần tử mới đều nhỏ hơn khóa vừa ghi. Replacement selection phải đóng băng chúng, nên trong ví dụ vẫn cần **3 runs**, độ dài `[4,4,3]`. Không thể kỳ vọng replacement selection luôn cải thiện nhiều.

### Tất cả khóa bằng nhau

Với 7 record có key=2 và M=3, fixed-size tạo \(\lceil7/3\rceil=3\) runs. Replacement selection không phải đóng băng record mới vì key bằng lastKey vẫn hợp lệ, nên tạo **một run**.

### Trường hợp ngẫu nhiên

Với giả định **khóa độc lập, có phân bố tương đối đồng đều và thứ tự ngẫu nhiên**, chiều dài run trung bình của replacement selection thường **xấp xỉ 2M** trong mô hình lý tưởng. Đây là **nhận xét thống kê phụ thuộc giả định**, không phải bảo đảm tệ nhất hay công thức chính xác cho mọi input.

Đặc biệt:

- Input đã tăng: một run có thể dài tới N.
- Input giảm: độ dài thường gần M cho mỗi run trừ cuối.
- Phân bố có nhiều khóa trùng, tương quan theo thời gian, dữ liệu gần sắp hoặc ngược thứ tự có thể khác giả định 2M.

**Không được viết “replacement selection luôn sinh run dài 2M”**.

## 9. CPU và I/O của replacement selection

Mỗi bản ghi được đưa vào một heap và được lấy khỏi active một lần. Nếu tổng record trong active/frozen ≤M, thao tác heap tốn O(log M). Tổng chi phí CPU xấp xỉ:

\[
O(N\log M).
\]

Bộ nhớ logic cho dữ liệu đang được giữ là O(M). Về I/O, thuật toán vẫn **đọc toàn bộ N record một lần và ghi toàn bộ N record một lần**:

\[
\text{I/O run generation}\approx2N/b.
\]

Điểm cải thiện chính **không phải giảm số record ghi ở giai đoạn tạo run**, mà thường là **giảm số run R**, từ đó giảm số lượt trộn về sau.

Trong mã Java minh họa, mỗi run được ghi vào một file UTF-8, không nạp cả input. Các heap giữ record object nhỏ. Bộ đệm `BufferedReader` và `BufferedWriter` cũng chiếm bộ nhớ thực tế; `M` chỉ là giới hạn số record logic trong heap.

## 10. Sinh run ổn định và định dạng tệp

Một bản ghi có thể là:

`(key, ordinal, payload)`.

Trong code mẫu, để tập trung vào thuật toán, ta dùng:

`(int key, long ordinal)`.

Tệp nguồn là **mỗi dòng một khóa số nguyên**. Khi đọc dòng thứ i, run generator gắn ordinal=i. Run file chứa:

~~~text
key<TAB>ordinal
~~~

Trong file thật, `<TAB>` là một ký tự tab. Ví dụ hai dòng:

~~~text
6	2
6	3
~~~

Việc lưu ordinal giúp chứng minh và kiểm tra tính ổn định. Khi triển khai bản ghi có payload, phải ghi đủ payload cùng key và ordinal, bằng định dạng có **escape/length prefix** thích hợp. Nếu payload có tab hoặc newline, không được dùng phép `split("\t")` tùy tiện mà không có quy ước escape.

### Comparator ổn định

So sánh `key` trước; nếu hai key bằng nhau, so `ordinal` tăng dần.

Điều này là một **total order** cho từng bản ghi vì ordinal không trùng. Java dùng:

`Comparator.comparingInt(Row::key).thenComparingLong(Row::ordinal)`.

Tránh viết `a.key-b.key` trong comparator vì hai int lớn có thể tràn và phá thứ tự. Dùng `Integer.compare`/`Comparator.comparingInt` an toàn hơn.

### Không tự tạo ordinal cục bộ cho từng run

Nếu mỗi run lại gán ordinal từ 0, hai record ở hai run khác nhau có thể có cùng (key,ordinal). Kết quả merge khi bằng nhau sẽ phụ thuộc cách xử lý tie giữa các file, không còn bảo đảm ổn định toàn cục theo thứ tự input.

## 11. Trộn các run để kiểm tra kết quả

Khi đã có R sorted runs, có thể dùng **k-way merge**:

1. Mở tối đa f tệp run đầu vào.
2. Đọc record đầu tiên của mỗi tệp, đưa vào min-heap theo `(key,ordinal)`.
3. Pop record nhỏ nhất, ghi ra tệp run kết quả.
4. Chỉ đọc và push record tiếp theo từ **cùng tệp** vừa pop.
5. Lặp đến khi heap trống.

Bất biến: phần tử nhỏ nhất chưa được xuất của mỗi run đều có mặt ở đầu tệp/heap. Vì từng run đã có thứ tự, min trên các đầu run là record nhỏ nhất **toàn bộ những record chưa xuất**. Nhờ vậy run đầu ra cũng đã sắp.

### Không đưa toàn bộ các run vào RAM

Mỗi tệp đầu vào chỉ cần một **read buffer** (và một record ứng viên trong heap), đầu ra có một **write buffer**. Với f luồng vào, số record trong heap merge là O(f), không phải O(N).

Trong mô hình buffer lý tưởng, nếu RAM cho M record và mỗi bộ đệm cần b record, ta thường chọn:

\[
f \le \left\lfloor\frac{M}{b}\right\rfloor-1
\]

để dành một buffer cho output, **chưa tính overhead và record heap**. Thực tế fan-in còn bị giới hạn bởi số file descriptor và dung lượng RAM. Mẫu Java dùng `f=2` để minh họa multi-pass; `M=4` ở ví dụ chỉ là dung lượng **record logic**.

### Nhiều lượt merge

Nếu R>f, chưa thể trộn tất cả run một lần. Chia danh sách run thành nhóm tối đa f, merge từng nhóm thành run mới, rồi lặp. Số lượt gần:

\[
p=\left\lceil\log_f R\right\rceil
\]

khi f≥2, với R>1; trường hợp R=0 hoặc 1 không cần một lượt merge đầy đủ. Chi phí I/O ở các pass thường khoảng:

\[
O\left(\frac{N}{b}\log_f R\right)
\]

block transfers, vì mỗi pass lý tưởng đọc và ghi lượng dữ liệu tương ứng với những run được trộn.

**Phát biểu chi tiết:** cận trên xấp xỉ `2(N/b)·ceil(log_f R)` cho các pass trộn nếu mỗi pass đọc và ghi toàn bộ N record; nếu có nhóm chỉ một run được chuyển tiếp nguyên tệp thì thực tế có thể ít hơn. Run generation ban đầu cộng thêm khoảng `2N/b`.

### Ví dụ M=4, fan-in=2

- Fixed-size có R=3, cần **2 merge passes**: trước tiên merge run1 và run2, rồi merge kết quả với run3.
- Replacement selection có R=2, cần **1 merge pass**.

Hai cách sinh run đều phải đưa ra cùng dãy đã sắp:

~~~text
[0#8, 1#1, 2#4, 3#6, 4#10, 5#9, 6#2, 6#3, 7#5, 8#0, 9#7]
~~~

**Lợi ích:** replacement selection bớt một pass trộn trên ví dụ. Với file lớn, một pass có thể là thêm một lượt đọc/ghi gần toàn bộ dataset, nên giảm R có giá trị thực tế.

## 12. Mối quan hệ với natural runs

Một **natural run** là đoạn đã có thứ tự liên tiếp trong chính input, ví dụ:

`[1,2,5] [0,4,7] [3,9]`.

**Natural merge sort** nhận diện các đoạn đơn điệu có sẵn và dùng chúng như những runs. Điều này khác fixed-size run generation, vốn chia theo **số bản ghi**, và cũng khác replacement selection, vốn có thể tạo run dài bằng **heap tuyển chọn** dù input không có một đoạn liên tiếp tăng dài như vậy.

Nếu input gần sắp, natural run detection hoặc replacement selection có thể tận dụng cấu trúc tốt hơn fixed chunks. Tuy nhiên cần giữ rõ khái niệm:

- **Natural run:** đoạn liên tiếp có thứ tự trong input.
- **Fixed sorted run:** một lô M record được sort lại trong RAM.
- **Replacement-selected run:** dãy bản ghi được phát ra theo heap, có thể gồm các record **không liền nhau trong thứ tự input**.

Việc record chạy tới frozen không đồng nghĩa một “natural run” của input đã kết thúc.

## 13. Vòng đời và quản lý tệp chạy ngoài bộ nhớ

Một triển khai thực tế nên có quy tắc cụ thể:

- **Định danh tệp độc nhất:** tránh vô tình ghi đè run của một tác vụ khác. Tệp tạm được tạo trong thư mục riêng của job.
- **Đóng writer trước khi merge:** nếu chưa flush/close, các record cuối có thể còn ở buffer.
- **Lưu metadata:** đường dẫn, số record, key nhỏ nhất/lớn nhất, thứ tự run và có thể checksum/version.
- **Kiểm soát số file mở:** f không vượt giới hạn file descriptors, mỗi run có read buffer.
- **Xóa đúng lúc:** chỉ xóa input runs sau khi merge output đã được tạo và xác minh thích hợp; hệ thống production còn cần checkpoint/atomic rename.
- **Khi gặp lỗi I/O:** không coi file output đang ghi dở là run hoàn chỉnh.
- **Tách vùng đĩa tạm:** kiểm tra dung lượng vì external sort có thể phải giữ cả dữ liệu gốc và các runs/merged runs đồng thời.
- **Quy tắc xử lý trùng khóa:** nếu yêu cầu stable sort, lưu/duy trì original ordinal.
- **Định dạng record:** chuỗi biến độ dài cần byte budget, không đơn thuần giới hạn bằng “M objects”.

Mã minh họa dùng tệp thực trong một **temporary directory riêng**, chỉ phục vụ demo. Nó xác minh nội dung bằng cách đọc lại run trong các helper **kiểm thử**; bản thân thuật toán run generation và merge luôn **streaming**. Sau demo, chương trình xóa các tệp do chính nó tạo trong thư mục tạm.

## 14. Java 17+: tạo fixed runs, replacement runs và merge hai ngả

File đầy đủ: **`ExternalRunGenerationDemo.java`**.

Thiết kế:

- `Row(key, ordinal)`: giữ nguyên thứ tự nguồn để ổn định khi khóa trùng.
- `fixedRuns(input,M,dir)`: đọc một file đầu vào tuần tự, sort từng lô tối đa M record và ghi một run tạm cho mỗi lô.
- `replacementRuns(input,M,dir)`: giữ hai min-heaps active/frozen, tổng record trong chúng không vượt M, đóng run khi active cạn.
- `mergeGroup`: min-heap một record đầu từ mỗi tệp; ghi result tuần tự.
- `mergeMultiPass`: merge nhóm tối đa fanIn, chuyển các run chưa cần merge sang pass tiếp theo, xóa input runs sau khi đã trộn thành công.
- `verifyRuns` và `readRowsForTesting`: **chỉ dùng cho demo/test**, kiểm mỗi run có thứ tự, giữ đúng mọi ordinal đầu vào, không mất/trùng record.
- `randomChecks`: 180 đầu vào gồm mảng rỗng, tăng, giảm, tất cả bằng nhau, khóa cực trị int và mảng ngẫu nhiên; mỗi input được xử lý bằng **cả hai chiến lược** với nhiều M và fanIn, rồi so với oracle sort theo `(key,ordinal)`.

### Mã nguồn chạy được với Java 17+

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Random;
import java.util.StringJoiner;

public class ExternalRunGenerationDemo {
    record Row(int key, long ordinal) {}
    record Head(Row row, int source) {}
    record MergeResult(Path file, int passes) {}

    static final Comparator<Row> ORDER =
            Comparator.comparingInt(Row::key)
                      .thenComparingLong(Row::ordinal);

    static Row newInputRow(String line, long ordinal) {
        return new Row(Integer.parseInt(line.trim()), ordinal);
    }

    static void writeRow(BufferedWriter out, Row row)
            throws IOException {
        out.write(Integer.toString(row.key()));
        out.write('\t');
        out.write(Long.toString(row.ordinal()));
        out.newLine();
    }

    static Row readRow(BufferedReader reader)
            throws IOException {
        String line = reader.readLine();
        if (line == null) return null;
        int tab = line.indexOf('\t');
        if (tab < 0)
            throw new IOException("Run record missing tab");
        return new Row(
                Integer.parseInt(line.substring(0, tab)),
                Long.parseLong(line.substring(tab + 1)));
    }

    static Path inputFile(Path dir, int[] keys)
            throws IOException {
        Path file = Files.createTempFile(dir, "input-", ".txt");
        try (BufferedWriter out = Files.newBufferedWriter(
                file, StandardCharsets.UTF_8)) {
            for (int key : keys) {
                out.write(Integer.toString(key));
                out.newLine();
            }
        }
        return file;
    }

    static Path flushFixed(List<Row> buffer, Path dir)
            throws IOException {
        buffer.sort(ORDER);
        Path file = Files.createTempFile(
                dir, "fixed-", ".run");
        try (BufferedWriter out = Files.newBufferedWriter(
                file, StandardCharsets.UTF_8)) {
            for (Row row : buffer) writeRow(out, row);
        }
        return file;
    }

    // Fixed-size chunk sorting: at most memoryLimit records in RAM.
    static List<Path> fixedRuns(Path input,
            int memoryLimit, Path dir) throws IOException {
        if (memoryLimit < 1)
            throw new IllegalArgumentException("M must be >=1");
        List<Path> runs = new ArrayList<>();
        List<Row> buffer = new ArrayList<>(memoryLimit);
        long ordinal = 0;

        try (BufferedReader reader = Files.newBufferedReader(
                input, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                buffer.add(newInputRow(line, ordinal++));
                if (buffer.size() == memoryLimit) {
                    runs.add(flushFixed(buffer, dir));
                    buffer.clear();
                }
            }
        }
        if (!buffer.isEmpty()) {
            runs.add(flushFixed(buffer, dir));
        }
        return runs;
    }

    // Replacement selection: active+frozen hold <=M records.
    static List<Path> replacementRuns(Path input,
            int memoryLimit, Path dir) throws IOException {
        if (memoryLimit < 1)
            throw new IllegalArgumentException("M must be >=1");
        List<Path> runs = new ArrayList<>();
        PriorityQueue<Row> active = new PriorityQueue<>(ORDER);
        PriorityQueue<Row> frozen = new PriorityQueue<>(ORDER);
        long ordinal = 0;

        try (BufferedReader reader = Files.newBufferedReader(
                input, StandardCharsets.UTF_8)) {
            String line;
            while (active.size() < memoryLimit
                    && (line = reader.readLine()) != null) {
                active.add(newInputRow(line, ordinal++));
            }

            while (!active.isEmpty()) {
                Path file = Files.createTempFile(
                        dir, "replacement-", ".run");
                try (BufferedWriter out = Files.newBufferedWriter(
                        file, StandardCharsets.UTF_8)) {
                    int lastKey = Integer.MIN_VALUE;

                    while (!active.isEmpty()) {
                        Row row = active.remove();
                        if (row.key() < lastKey)
                            throw new AssertionError(
                                    "Run key decreased");
                        writeRow(out, row);
                        lastKey = row.key();

                        String nextLine = reader.readLine();
                        if (nextLine != null) {
                            Row next = newInputRow(
                                    nextLine, ordinal++);
                            if (next.key() >= lastKey)
                                active.add(next);
                            else
                                frozen.add(next);
                        }
                    }
                }
                runs.add(file);
                active = frozen;
                frozen = new PriorityQueue<>(ORDER);
            }
        }
        return runs;
    }

    // Streaming k-way merge: only one candidate per input run.
    static void mergeGroup(List<Path> group, Path output)
            throws IOException {
        BufferedReader[] readers =
                new BufferedReader[group.size()];

        try {
            for (int i = 0; i < group.size(); i++) {
                readers[i] = Files.newBufferedReader(
                        group.get(i), StandardCharsets.UTF_8);
            }

            PriorityQueue<Head> heap =
                    new PriorityQueue<>((x, y) -> {
                        int c = ORDER.compare(x.row(), y.row());
                        return c != 0 ? c
                                : Integer.compare(
                                    x.source(), y.source());
                    });

            for (int i = 0; i < readers.length; i++) {
                Row first = readRow(readers[i]);
                if (first != null)
                    heap.add(new Head(first, i));
            }

            try (BufferedWriter out = Files.newBufferedWriter(
                    output, StandardCharsets.UTF_8)) {
                while (!heap.isEmpty()) {
                    Head current = heap.remove();
                    writeRow(out, current.row());
                    Row next = readRow(readers[current.source()]);
                    if (next != null)
                        heap.add(new Head(
                                next, current.source()));
                }
            }
        } finally {
            for (BufferedReader reader : readers) {
                if (reader != null) reader.close();
            }
        }
    }

    // Merge at most fanIn runs at a time; preserve singleton runs.
    static MergeResult mergeMultiPass(
            List<Path> initial, int fanIn, Path dir)
            throws IOException {
        if (fanIn < 2)
            throw new IllegalArgumentException("fanIn must be >=2");
        if (initial.isEmpty()) {
            return new MergeResult(
                    Files.createTempFile(dir, "empty-", ".run"), 0);
        }

        List<Path> current = new ArrayList<>(initial);
        int passes = 0;
        while (current.size() > 1) {
            List<Path> next = new ArrayList<>();

            for (int start = 0;
                    start < current.size(); start += fanIn) {
                int end = Math.min(
                        current.size(), start + fanIn);
                List<Path> group =
                        current.subList(start, end);

                if (group.size() == 1) {
                    next.add(group.get(0));
                    continue;
                }

                Path output = Files.createTempFile(
                        dir, "merged-", ".run");
                mergeGroup(group, output);
                next.add(output);

                // Delete only successfully merged input runs.
                for (Path source : group)
                    Files.delete(source);
            }

            current = next;
            passes++;
        }
        return new MergeResult(current.get(0), passes);
    }

    // Helpers below may materialize a run ONLY for demo/QA.
    static List<Row> readRowsForTesting(Path file)
            throws IOException {
        List<Row> rows = new ArrayList<>();
        try (BufferedReader reader = Files.newBufferedReader(
                file, StandardCharsets.UTF_8)) {
            Row row;
            while ((row = readRow(reader)) != null)
                rows.add(row);
        }
        return rows;
    }

    static List<Row> expectedSort(int[] keys) {
        List<Row> rows = new ArrayList<>();
        for (int i = 0; i < keys.length; i++)
            rows.add(new Row(keys[i], i));
        rows.sort(ORDER);
        return rows;
    }

    // Independent validity check: each ordinal appears once
    // and each initial run is nondecreasing.
    static void verifyRuns(List<Path> runs, int n)
            throws IOException {
        boolean[] seen = new boolean[n];
        int count = 0;
        for (Path path : runs) {
            List<Row> rows = readRowsForTesting(path);
            if (rows.isEmpty())
                throw new AssertionError("Unexpected empty run");
            Row previous = null;

            for (Row row : rows) {
                if (previous != null
                        && ORDER.compare(previous, row) > 0)
                    throw new AssertionError("Unsorted run");
                if (row.ordinal() < 0
                        || row.ordinal() >= n)
                    throw new AssertionError("Bad ordinal");
                int id = (int) row.ordinal();
                if (seen[id])
                    throw new AssertionError("Duplicate record");
                seen[id] = true;
                count++;
                previous = row;
            }
        }

        if (count != n)
            throw new AssertionError("Record loss");
    }

    static String render(List<Row> rows) {
        StringJoiner j = new StringJoiner(", ", "[", "]");
        for (Row row : rows)
            j.add(row.key() + "#" + row.ordinal());
        return j.toString();
    }

    static String describeRuns(List<Path> runs)
            throws IOException {
        StringJoiner j = new StringJoiner(" | ");
        for (int i = 0; i < runs.size(); i++) {
            j.add("run" + (i + 1) + "="
                    + render(readRowsForTesting(runs.get(i))));
        }
        return j.toString();
    }

    static void verifyCase(int[] keys, int memoryLimit,
            int fanIn, Path dir) throws IOException {
        Path input = inputFile(dir, keys);
        List<Row> oracle = expectedSort(keys);

        List<Path> fixed = fixedRuns(input, memoryLimit, dir);
        List<Path> replacement =
                replacementRuns(input, memoryLimit, dir);
        verifyRuns(fixed, keys.length);
        verifyRuns(replacement, keys.length);

        MergeResult mergedFixed =
                mergeMultiPass(fixed, fanIn, dir);
        MergeResult mergedReplacement =
                mergeMultiPass(replacement, fanIn, dir);

        List<Row> one =
                readRowsForTesting(mergedFixed.file());
        List<Row> two =
                readRowsForTesting(mergedReplacement.file());
        if (!one.equals(oracle) || !two.equals(oracle))
            throw new AssertionError("Merged order/stability error");

        Files.delete(input);
        Files.delete(mergedFixed.file());
        Files.delete(mergedReplacement.file());
    }

    static void randomChecks(Path dir) throws IOException {
        Random random = new Random(5152026L);

        for (int trial = 0; trial < 180; trial++) {
            int n = trial % 17 == 0
                    ? 0 : random.nextInt(71);
            int[] keys = new int[n];
            for (int i = 0; i < n; i++) {
                switch (trial % 5) {
                    case 0 -> keys[i] = i - 30;
                    case 1 -> keys[i] = n - i;
                    case 2 -> keys[i] = 7;
                    case 3 -> keys[i] = i % 2 == 0
                            ? Integer.MIN_VALUE
                            : Integer.MAX_VALUE;
                    default -> keys[i] =
                            random.nextInt(51) - 25;
                }
            }

            int capacity = 1 + random.nextInt(12);
            int fanIn = 2 + random.nextInt(3);
            verifyCase(keys, capacity, fanIn, dir);
        }
        System.out.println(
                "randomCheck=PASS (180 inputs x 2)");
    }

    static void cleanupOwnTempDirectory(Path dir)
            throws IOException {
        // This program creates only files directly under dir.
        try (DirectoryStream<Path> entries =
                Files.newDirectoryStream(dir)) {
            for (Path file : entries)
                Files.deleteIfExists(file);
        }
        Files.deleteIfExists(dir);
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory(
                "external-runs-demo-");
        try {
            int[] keys = {8,1,6,6,2,7,3,9,0,5,4};
            int memoryLimit = 4;
            int fanIn = 2;
            Path input = inputFile(dir, keys);

            List<Path> fixed = fixedRuns(
                    input, memoryLimit, dir);
            List<Path> replacement = replacementRuns(
                    input, memoryLimit, dir);

            verifyRuns(fixed, keys.length);
            verifyRuns(replacement, keys.length);

            System.out.println(
                    "input=" + Arrays.toString(keys));
            System.out.println(
                    "capacity=" + memoryLimit
                    + " fanIn=" + fanIn);
            System.out.println("fixed runs=" + fixed.size());
            System.out.println(
                    "fixed details=" + describeRuns(fixed));
            System.out.println(
                    "replacement runs=" + replacement.size());
            System.out.println("replacement details="
                    + describeRuns(replacement));

            MergeResult mergedFixed =
                    mergeMultiPass(fixed, fanIn, dir);
            MergeResult mergedReplacement =
                    mergeMultiPass(replacement, fanIn, dir);
            List<Row> one =
                    readRowsForTesting(mergedFixed.file());
            List<Row> two =
                    readRowsForTesting(mergedReplacement.file());
            List<Row> oracle = expectedSort(keys);
            if (!one.equals(oracle) || !two.equals(oracle))
                throw new AssertionError("Wrong sorted output");

            System.out.println(
                    "fixed merged=" + render(one)
                    + " mergePasses=" + mergedFixed.passes());
            System.out.println(
                    "replacement merged=" + render(two)
                    + " mergePasses="
                    + mergedReplacement.passes());
            System.out.println("mergedEqual="
                    + one.equals(two)
                    + " stable=" + one.equals(oracle));

            int[] ascending = {0,1,2,3,4,5,6,7,8,9,10};
            Path inc = inputFile(dir, ascending);
            System.out.println("ascending runs fixed="
                    + fixedRuns(inc, 4, dir).size()
                    + " replacement="
                    + replacementRuns(inc, 4, dir).size());

            int[] descending = {10,9,8,7,6,5,4,3,2,1,0};
            Path dec = inputFile(dir, descending);
            System.out.println("descending runs fixed="
                    + fixedRuns(dec, 4, dir).size()
                    + " replacement="
                    + replacementRuns(dec, 4, dir).size());

            int[] equalKeys = {2,2,2,2,2,2,2};
            Path eq = inputFile(dir, equalKeys);
            System.out.println("equalKeys runs fixed="
                    + fixedRuns(eq, 3, dir).size()
                    + " replacement="
                    + replacementRuns(eq, 3, dir).size());

            Path blank = inputFile(dir, new int[0]);
            System.out.println("empty runs fixed="
                    + fixedRuns(blank, 4, dir).size()
                    + " replacement="
                    + replacementRuns(blank, 4, dir).size());

            try {
                fixedRuns(input, 0, dir);
                throw new AssertionError(
                        "Expected invalid memory limit");
            } catch (IllegalArgumentException expected) {
                System.out.println("invalidCapacity=rejected");
            }

            randomChecks(dir);
        } finally {
            cleanupOwnTempDirectory(dir);
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 ExternalRunGenerationDemo.java
java ExternalRunGenerationDemo
~~~

### Đầu ra dự kiến chính xác

~~~text
input=[8, 1, 6, 6, 2, 7, 3, 9, 0, 5, 4]
capacity=4 fanIn=2
fixed runs=3
fixed details=run1=[1#1, 6#2, 6#3, 8#0] | run2=[2#4, 3#6, 7#5, 9#7] | run3=[0#8, 4#10, 5#9]
replacement runs=2
replacement details=run1=[1#1, 2#4, 6#2, 6#3, 7#5, 8#0, 9#7] | run2=[0#8, 3#6, 4#10, 5#9]
fixed merged=[0#8, 1#1, 2#4, 3#6, 4#10, 5#9, 6#2, 6#3, 7#5, 8#0, 9#7] mergePasses=2
replacement merged=[0#8, 1#1, 2#4, 3#6, 4#10, 5#9, 6#2, 6#3, 7#5, 8#0, 9#7] mergePasses=1
mergedEqual=true stable=true
ascending runs fixed=3 replacement=1
descending runs fixed=3 replacement=3
equalKeys runs fixed=3 replacement=1
empty runs fixed=0 replacement=0
invalidCapacity=rejected
randomCheck=PASS (180 inputs x 2)
~~~

### Giải thích stdout

**fixed runs=3:** input 11 records, M=4, tạo ba lô 4,4,3; mỗi lô được sort riêng.

**replacement runs=2:** heap active/frozen giữ tối đa bốn record, nhưng run đầu kéo dài bảy record. Bốn record bị đóng băng sẽ tạo run thứ hai.

**mergePasses=2 và mergePasses=1:** với fan-in=2, ba runs ban đầu cần hai lượt trộn, còn hai runs chỉ cần một lượt. Số lượt trộn trong mã tính theo các vòng giảm danh sách runs cho tới khi chỉ còn một.

**mergedEqual=true:** hai chiến lược run generation khác nhau nhưng kết quả trộn là cùng một danh sách bản ghi.

**stable=true:** kết quả bằng oracle sort `(key,ordinal)`; hai record có key 6 vẫn theo thứ tự 6#2 trước 6#3.

**ascending:** input đã tăng, replacement selection tạo được một run dài 11, trong khi fixed vẫn tạo ba.

**descending:** dữ liệu giảm, replacement không giữ được nhiều record mới trong active, nên vẫn tạo ba runs.

**equalKeys:** tất cả khóa bằng nhau; replacement coi khóa mới bằng lastKey là hợp lệ và chỉ tạo một run.

**empty:** file nguồn rỗng được biểu diễn bằng **0 runs ban đầu**, không phát ra tệp run chứa dữ liệu giả.

**invalidCapacity:** M=0 không phải một kích thước RAM hợp lệ, hàm từ chối trước khi đọc file.

**randomCheck:** đối với 180 trường hợp với M từ 1 tới 12 và fan-in từ 2 tới 4, cả hai chiến lược được ghép lại rồi so với oracle độc lập. Tổng cộng 360 kết quả merge được so sánh, gồm mảng rỗng, tăng, giảm, nhiều khóa trùng, cực trị int và input ngẫu nhiên. Bộ test xác minh nội dung của mọi run được sinh ra trước khi merge.

**Giới hạn kiểm thử:** các bài test khẳng định mã đúng trên tập input đã thử; chứng minh cho mọi input đến từ bất biến sorted run, bảo toàn bản ghi, budget heap và tính đúng của k-way merge.

## 15. Độ phức tạp chương trình Java

| Thành phần | CPU | Bộ nhớ dữ liệu chính | I/O lý tưởng |
| --- | --- | --- | --- |
| fixedRuns | O(N log M) | O(M) records | Đọc N, ghi N |
| replacementRuns | O(N log M) | O(M) records active+frozen | Đọc N, ghi N |
| mergeGroup với f runs | O(N log f) | O(f) đầu run + buffers | Đọc N, ghi N |
| mergeMultiPass với R runs | O(N log f·ceil(log_f R)) cận cơ bản | O(f) đầu run + buffers | O((N/b)log_f R) block transfers |
| verifyRuns (test helper) | O(N) | O(N) do mảng seen | Đọc N |
| expectedSort (oracle demo) | O(N log N) | O(N) | Không áp dụng cho thuật toán external production |

Chỉ các helper **test/demo** mới tải cả run hoặc danh sách output vào bộ nhớ để so sánh; đường đi **fixedRuns → replacementRuns → mergeGroup** thực chất đọc/ghi file streaming. Khi triển khai thực tế trên dữ liệu hàng chục GB, không được gọi `readRowsForTesting` với toàn bộ output; nên dùng **streaming verification** hoặc checksum/record count.

## 16. Những lỗi triển khai thường gặp

1. Gọi sort trên toàn bộ N records dù N lớn hơn RAM.
2. Quên flush/close writer trước khi cho merge đọc run.
3. Coi một I/O block là một sorted run.
4. Chọn M=0 hoặc dùng M lớn hơn ngân sách RAM thực.
5. Không sort phần lô cuối nếu ít hơn M record.
6. Sinh một run rỗng khi file nguồn rỗng.
7. Mỗi lô chỉ sort khóa nhưng vô tình tách payload khỏi record.
8. Lưu ordinal cục bộ thay vì ordinal toàn cục, làm mất stable order qua các runs.
9. Viết comparator `a.key-b.key` gây overflow int.
10. Trộn run bằng phép nối file thay vì k-way merge.
11. Tính số fixed runs thành floor(N/M) và bỏ run cuối.
12. Quên rằng replacement selection cần **min-heap**, không phải max-heap.
13. Đưa bản ghi mới có khóa **nhỏ hơn lastKey** vào active.
14. Bỏ bản ghi bị frozen, làm mất dữ liệu.
15. Ghi bản ghi frozen ngay vào run hiện tại, làm run giảm khóa.
16. Dùng hai heap mỗi heap đầy M cùng lúc, vượt tổng ngân sách logic.
17. Khi active cạn, không khởi động run mới từ frozen.
18. Khi chuyển frozen sang active, quên xóa heap frozen cũ, ghi lặp record.
19. Dừng khi input EOF nhưng active/frozen còn record chưa xuất.
20. Giả định replacement selection luôn cho run dài đúng 2M.
21. Thấy run ít hơn rồi nói luôn giảm thời gian CPU hoặc số I/O generation; chủ yếu giảm merge passes.
22. Cho rằng các run phải có key ranges không giao nhau.
23. Không giữ metadata về run file và số record.
24. Mở cùng lúc mọi run khi R vượt số file descriptors/budget buffer.
25. Chọn fan-in f lớn hơn lượng RAM cho input/output buffers.
26. Trộn mà không theo `(key,ordinal)` khi yêu cầu tính ổn định.
27. Cho một run input chưa sắp vào merge mà không kiểm tra.
28. Chỉ test với dữ liệu đã tăng, không test giảm hoặc khóa trùng.
29. Không test M=1 và N=0.
30. Không test các cực trị int khi dùng comparator.
31. Xóa input runs trước khi merge output thành công.
32. Dùng tệp tạm có tên cố định gây ghi đè giữa hai jobs.
33. Quên rằng file I/O có thể thất bại do thiếu dung lượng/quyền truy cập.
34. Tưởng rằng Java BufferedReader/Writer không dùng bộ nhớ.
35. Dùng `readAllLines` trên file N lớn trong production.
36. In số run tốt hơn trên benchmark rồi tuyên bố có cận worst-case không được chứng minh.
37. Chỉ so số lượng run mà không kiểm tra đủ N record và đúng khóa/ordinal.
38. Merge cùng tệp vào chính nó, có thể phá nội dung nguồn.
39. Coi mọi input đã sort có natural runs giống replacement-generated runs.
40. Không phân biệt chi phí CPU O(N log M) và số block I/O thực tế.

## 17. Bài tập có lời giải

**Bài 1.** Tại sao cần initial sorted runs? **Đáp án:** tập dữ liệu N lớn hơn RAM M; chia và sort bằng bộ nhớ hạn chế rồi merge trên đĩa.

**Bài 2.** Một run hợp lệ là gì? **Đáp án:** dãy record không giảm theo khóa sắp xếp, có thể được lưu trên nhiều block.

**Bài 3.** Run có phải I/O block không? **Đáp án:** không; run là đơn vị logic đã sắp, block là đơn vị đọc/ghi đĩa.

**Bài 4.** Với N=11,M=4, fixed-size tạo bao nhiêu run? **Đáp án:** 3.

**Bài 5.** Độ dài các fixed runs ở bài 4? **Đáp án:** [4,4,3].

**Bài 6.** Với N=0,M=4, số fixed runs? **Đáp án:** 0.

**Bài 7.** Công thức số run fixed-size với N>0? **Đáp án:** `ceil(N/M)`.

**Bài 8.** Thời gian sort CPU của fixed-size? **Đáp án:** O(N log M).

**Bài 9.** I/O lý tưởng của run generation trong cả hai cách? **Đáp án:** đọc N và ghi N records, gần 2N/b block transfers.

**Bài 10.** Vì sao không nối ba run để được sorted output? **Đáp án:** thứ tự khóa giữa những run khác nhau không được bảo đảm.

**Bài 11.** Replacement selection dùng cấu trúc gì? **Đáp án:** min-heap active và min-heap frozen.

**Bài 12.** Khi new.key≥lastKey, đưa record mới vào đâu? **Đáp án:** active.

**Bài 13.** Khi new.key<lastKey, đưa vào đâu? **Đáp án:** frozen để dùng ở run sau.

**Bài 14.** Khi active trống thì làm gì? **Đáp án:** đóng run hiện tại, chuyển frozen thành active, tạo run mới nếu còn record.

**Bài 15.** Tổng số record active+frozen có thể vượt M không? **Đáp án:** không; mỗi pop chỉ đọc thêm tối đa một record.

**Bài 16.** Một run replacement có thể dài hơn M không? **Đáp án:** có, ví dụ run đầu 7 record với M=4.

**Bài 17.** Replacement luôn tạo run dài 2M không? **Đáp án:** không; 2M chỉ là hiện tượng kỳ vọng trong một số mô hình input ngẫu nhiên.

**Bài 18.** Khi input tăng dần, replacement selection có thể tạo bao nhiêu run? **Đáp án:** một run.

**Bài 19.** Khi input giảm dần, replacement selection có luôn tốt hơn fixed-size không? **Đáp án:** không; có thể tạo các run gần M record.

**Bài 20.** Với 7 khóa bằng 2 và M=3, replacement tạo bao nhiêu run? **Đáp án:** 1.

**Bài 21.** Với đầu vào mẫu của bài, run đầu replacement có những gì? **Đáp án:** `[1#1,2#4,6#2,6#3,7#5,8#0,9#7]`.

**Bài 22.** Run thứ hai của replacement chứa gì? **Đáp án:** `[0#8,3#6,4#10,5#9]`.

**Bài 23.** Tại sao key=0 được phép xuất sau key=9 nếu khác run? **Đáp án:** mỗi run chỉ cần được sort bên trong; merge sau mới sắp toàn cục.

**Bài 24.** Mục đích của originalOrdinal? **Đáp án:** bảo toàn thứ tự ban đầu giữa các record có cùng key.

**Bài 25.** Khi merge hai record có cùng key, ưu tiên record nào để stable? **Đáp án:** ordinal nhỏ hơn.

**Bài 26.** Vì sao comparator không nên trừ hai int? **Đáp án:** có thể tràn số và so sánh sai.

**Bài 27.** Cấu trúc dữ liệu cho k-way merge? **Đáp án:** min-heap chứa phần tử đầu chưa xuất của mỗi run.

**Bài 28.** Sau khi pop từ run i ở merge, đọc phần tử tiếp theo từ đâu? **Đáp án:** chính run i.

**Bài 29.** Với fan-in=2,R=3, có bao nhiêu pass merge? **Đáp án:** 2.

**Bài 30.** Với fan-in=2,R=2, số pass? **Đáp án:** 1.

**Bài 31.** Giảm R từ 3 xuống 2 ở ví dụ tiết kiệm gì? **Đáp án:** một lượt merge, tránh đọc/ghi thêm các run liên quan.

**Bài 32.** Số passes xấp xỉ với R runs và fan-in f≥2? **Đáp án:** `ceil(log_f R)` nếu R>1.

**Bài 33.** Fan-in bị giới hạn bởi gì? **Đáp án:** RAM cho input/output buffers, file descriptor và overhead.

**Bài 34.** Vì sao phải đóng writer trước khi merge? **Đáp án:** dữ liệu chưa flush có thể chưa hiện đủ trong file.

**Bài 35.** Run generation có tự tạo output toàn cục sorted chưa? **Đáp án:** chưa; phải merge khi còn hơn một run.

**Bài 36.** Natural run khác fixed sorted run ra sao? **Đáp án:** natural run là đoạn liên tiếp đã monotonic sẵn; fixed run được sort lại từ một lô M records.

**Bài 37.** Replacement run có bắt buộc là một đoạn liên tiếp trong input không? **Đáp án:** không; bản ghi bị frozen được dành sang run sau.

**Bài 38.** Tại sao dùng hai heaps active/frozen mà vẫn O(M) bộ nhớ? **Đáp án:** tổng record đang giữ không vượt M.

**Bài 39.** Có nên gọi `Files.readAllLines` trên file 100GB để làm run generation không? **Đáp án:** không; phải streaming.

**Bài 40.** Oracle chính xác khi test hai chiến lược là gì? **Đáp án:** trên input nhỏ, sắp toàn bộ record theo `(key,ordinal)` rồi so với output merged.

**Bài 41.** Làm sao phát hiện mất/trùng record? **Đáp án:** gắn ordinal duy nhất và xác nhận mỗi ordinal đầu vào xuất hiện đúng một lần trên các runs.

**Bài 42.** Vì sao phải thử N=0, M=1 và input giảm dần? **Đáp án:** chúng phơi bày lỗi kết thúc input, ngưỡng dung lượng heap và hành vi frozen.

**Bài 43.** Nếu RAM cho M=8 block buffers, một buffer output và mỗi run input cần một buffer, fan-in tối đa lý tưởng là bao nhiêu? **Đáp án:** 7, chưa tính các overhead khác.

**Bài 44.** Nếu chỉ có một initial run, có nhất thiết cần merge pass không? **Đáp án:** không; run ấy đã là output được sort toàn cục.

## 18. Checklist triển khai

1. Đã xác định rõ N, memory budget M và kích thước I/O block b?
2. Tệp input có được đọc tuần tự, không nạp toàn bộ vào RAM?
3. M có ≥1 và đã tính cả overhead parser, heap, buffers?
4. Định dạng record có giữ đủ key, originalOrdinal và payload?
5. Comparator có so key rồi ordinal, tránh overflow int?
6. Với fixed-size, có sort lô cuối dù chưa đủ M?
7. Có tạo đúng ceil(N/M) runs khi N>0 và 0 runs khi N=0?
8. Với replacement, dùng **min-heap** đúng thứ tự?
9. Khi new.key<lastKey, có đưa record vào frozen, không ghi bừa?
10. Khi active cạn, có chuyển frozen thành active và khởi tạo run mới?
11. Tổng số record trong active+frozen có ≤M?
12. Có xuất đủ mọi record, đúng một lần, không mất/trùng?
13. Mỗi run có khóa không giảm?
14. Khi key bằng nhau, có giữ ordinal tăng dần?
15. Run được flush và đóng writer trước khi merge?
16. Có lưu được danh sách/metadata của các run?
17. Fan-in f có nằm trong giới hạn buffer và file handles?
18. Merge có đọc một record đầu từ mỗi run rồi dùng min-heap?
19. Có trả đúng thứ tự toàn cục khi các runs chồng lấn miền khóa?
20. Có xóa input runs **sau** khi merge hoàn thành, không trước?
21. Đã cân nhắc xử lý lỗi, partial files, checksum và checkpoint khi production?
22. Có tách rõ I/O run generation với I/O merge?
23. Có đánh giá giảm số run thực sự tiết kiệm bao nhiêu merge passes?
24. Có test input tăng, giảm, trùng, ngẫu nhiên, rỗng và cực trị int?
25. Có so kết quả với oracle sort độc lập trên input nhỏ?
26. Có xác minh stability, record count và ordinal uniqueness?
27. Có tránh dùng helper tải cả output vào RAM khi dữ liệu production rất lớn?
28. Có biết 2M là nhận xét kỳ vọng, không phải chiều dài run bảo đảm?
29. Có tránh so performance chỉ dựa trên số run mà quên CPU, RAM, I/O và filesystem?
30. Có đóng/xóa đúng tệp tạm do tác vụ tạo ra mà không tác động tới nguồn ngoài phạm vi?

**Ghi nhớ:** mục tiêu của **initial sorted run generation** là biến một tệp rất lớn thành các **runs có thứ tự bên trong**, mỗi record được đọc/ghi có kiểm soát. **Fixed-size sorting** đơn giản, cho \(\lceil N/M\rceil\) runs khi N>0. **Replacement selection** dùng active/frozen min-heaps để tận dụng luồng khóa mới và có thể tạo run dài hơn M mà không vượt M record trong heap; **không có bảo đảm mọi run dài 2M**. Kết quả toàn cục chỉ có sau **merge**; khi R nhỏ hơn, thường cần ít merge passes hơn. Với các khóa trùng, comparator `(key, originalOrdinal)` là chìa khóa để giữ **stability** qua mọi giai đoạn.
