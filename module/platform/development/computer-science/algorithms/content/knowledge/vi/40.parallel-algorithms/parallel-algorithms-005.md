# Sắp xếp song song bằng trộn và phân hoạch

**Sắp xếp song song** (*parallel sorting*) phân chia công việc sắp xếp thành những bài toán con **có thể thực hiện đồng thời** trên nhiều nhân xử lý, với điều kiện các task không ghi đè lên vùng dữ liệu của nhau và được đồng bộ đúng. Hai chiến lược nền tảng:

1. **Song song hóa phép chia rồi trộn** (*parallel merge sort*): chia mảng thành hai nửa, sắp xếp hai nửa đồng thời, cuối cùng **merge** hai nửa có thứ tự.
2. **Song song hóa phép phân hoạch** (*parallel partition-based sorting*, thường là parallel quicksort): **partition** trước thành các vùng có quan hệ xác định với pivot, sau đó sắp xếp các vùng độc lập đồng thời.

Hai cách đều là **chia để trị**, nhưng có một khác biệt quan trọng: trong merge sort, **merge xảy ra sau khi hai nhánh xong**; trong quicksort, **partition xảy ra trước khi hai nhánh bắt đầu**. Đối với những cài đặt đơn giản, chính merge hoặc partition tuần tự trên mỗi node có thể trở thành **critical path** và hạn chế tốc độ lý tưởng.

Bài thuộc nhóm **Thuật toán song song** trong **Computer Science Algorithms**, đề bài **Sắp xếp song song bằng trộn và phân hoạch**. Nội dung trình bày tính đúng, tính ổn định, cách chia vùng ghi, phân tích **work–span**, ngưỡng tạo task và `ForkJoinPool`, cách phân hoạch ba vùng hiệu quả với khóa lặp, phòng trường hợp pivot lệch bằng **heapsort dự phòng**, và ý tưởng **parallel prefix scan** để phân hoạch thật sự song song.

Có một chương trình **Java 17+ độc lập** thực hiện stable parallel merge sort, three-way parallel quicksort có intro-depth safeguard, một bản tham chiếu stable partition bằng prefix counts, cùng bộ kiểm thử seeded và stdout có thể kiểm chứng. Các phép đo thực nghiệm thuật toán được tách khỏi khẳng định tốc độ: **pass correctness không có nghĩa song song chắc chắn nhanh hơn**.

## 1. Đầu vào, đầu ra, stability và tính đúng

Cho n phần tử:

**`A=[a₀,a₁,...,a_{n−1}]`**.

Giả sử mỗi item có một **khóa** `key(a)` và comparator nhất quán. Sau sort, cần:
- **Sortedness:** mọi cặp kề nhau có `key(out[i])≤key(out[i+1])`.
- **Permutation:** mọi occurrence của đầu vào xuất hiện đúng một lần trong đầu ra, không mất, không nhân đôi.
- **Stability** (*nếu bài yêu cầu*): hai occurrence có khóa bằng nhau phải giữ đúng **thứ tự tương đối ban đầu**.
- **Memory safety/concurrency:** không hai task không phối hợp cùng sửa một ô hoặc dùng dữ liệu đang bị task khác thay đổi.

Để kiểm tra stability, các item Java dùng record bất biến **`Item(int key,int originalIndex)`**; định dạng khi in là `key#originalIndex`.

Ví dụ đầu vào:

~~~text
[4#0, 1#1, 4#2, 2#3, 4#4, 1#5]
~~~

Đầu ra stable:

~~~text
[1#1, 1#5, 2#3, 4#0, 4#2, 4#4]
~~~

Dùng `int[]` rồi chỉ so các khóa đã tăng dần **không thể chứng nhận stability**; hai item có khóa 4 nhưng gốc ở index 0 và 4 sẽ bị coi như nhau. Một chứng minh/test stability phải giữ **danh tính occurrence**.

### Comparator cần là hàm thuần

Nếu comparator thay đổi kết quả theo thread, RNG, thời gian hoặc mutable state, cùng hai phần tử có thể bị so khác nhau ở các task. Trong Java nên dùng `Integer.compare(x.key(),y.key())` hoặc `Comparator.comparingInt(Item::key)` thay vì trừ hai số int; phép trừ có thể overflow và làm đổi dấu.

Bài này chỉ dùng **khóa số nguyên int**. Khi cần sort nhiều cột, xác định rõ khóa chính, khóa phụ và **quan hệ “bằng nhau” có phải bảo toàn thứ tự nguồn hay không**.

## 2. Đơn vị song song: task và ForkJoinPool

Không nên sinh một thread hệ điều hành cho mỗi phần tử. Tạo/hủy thread, chuyển ngữ cảnh và bộ nhớ stack thường lớn hơn lượng việc của một phần tử. `ForkJoinPool` duy trì một số worker và các task `RecursiveAction`, hỗ trợ **work stealing**: worker rảnh có thể lấy task đang chờ từ worker khác.

Mẫu fork–compute–join:

~~~text
sortLargeRange(lo, hi):
    if small:
        sequentialSort(lo, hi)
        return

    split into disjoint left and right ranges
    leftTask.fork()
    sort(right)               // parent helps do work
    leftTask.join()           // wait for completion

    combine if required
~~~

Ba nguyên tắc:
1. **Task con ghi vùng riêng**, không chồng vùng của task khác.
2. Parent chỉ đọc/merge dữ liệu của con **sau join**.
3. Chỉ fork khi đoạn đủ lớn để bù **scheduling overhead**.

Chương trình dùng `INSERTION_CUTOFF=24` để xử lý đoạn rất nhỏ bằng insertion sort và `PARALLEL_CUTOFF=2048` để tránh tạo task cho các đoạn nhỏ. Hai giá trị này chỉ là **tham số minh họa**, không tự tối ưu cho mọi CPU và JVM.

### Tại sao không fork cả hai nhánh rồi chờ?

Có thể fork hai nhánh, nhưng thường hiệu quả hơn khi **fork một nhánh, parent trực tiếp tính nhánh kia, rồi join**. Điều đó tránh để parent chỉ đứng chờ, tạo cơ hội dùng worker hiện tại cho công việc có ích.

## 3. Work, span và speedup

Trong thuật toán song song:
- **Work `W(n)`:** tổng các thao tác của thuật toán, bỏ qua chi phí điều phối.
- **Span `S(n)`:** thời gian của chuỗi phụ thuộc dài nhất (*critical path*) nếu có vô hạn bộ xử lý và thao tác đơn vị.
- **Parallelism `W/S`:** mức song song tiềm năng của đồ thị phụ thuộc.
- **`T_P`:** thời gian thực thi trên P worker/core trong môi trường cụ thể.

Hai cận dưới:

**`T_P≥W/P`** và **`T_P≥S`**,

suy ra **`T_P≥max(W/P,S)`**.

Nếu chỉ có một bước tuần tự tốn Θ(n), không số lượng core nào làm bước đó biến mất. Với work stealing tốt và các giả thiết lý tưởng, một cận thường dùng là `T_P=O(W/P+S)`, nhưng overhead, GC, cache, băng thông RAM và tính không cân bằng có thể khiến tốc độ thực tế kém hơn.

**Speedup** là `T₁/T_P` khi so với **cùng thuật toán** chạy trên một worker. Nó không mặc định bằng P. Với các array nhỏ, phiên bản song song có thể **chậm hơn** bản tuần tự vì chi phí fork/join.

Một cách diễn đạt bổ sung là **định luật Amdahl**: nếu tỷ lệ f của công việc phải tuần tự, speedup lý tưởng bị giới hạn bởi:

**`1/[f+(1−f)/P]`**.

## 4. Merge sort: chia trước, trộn sau

Merge sort trên đoạn nửa mở **`[lo,hi)`**:
1. Nếu rất ngắn, sort tuần tự.
2. Chọn `mid=lo+(hi−lo)/2`.
3. Sort **[lo,mid)** và **[mid,hi)**.
4. Merge hai đoạn đã sorted vào [lo,hi).

Pseudocode:

~~~text
mergeSort(lo, hi):
    if hi - lo <= cutoff:
        insertionSort(lo, hi)
        return

    mid = lo + (hi - lo) / 2

    if hi - lo >= parallelThreshold:
        left = new Task(lo, mid)
        left.fork()
        mergeSort(mid, hi)
        left.join()
    else:
        mergeSort(lo, mid)
        mergeSort(mid, hi)

    mergeSortedHalves(lo, mid, hi)
~~~

Hai nửa sort **đồng thời** vì chúng đọc/ghi những đoạn **không chồng nhau** của array và buffer. Parent chỉ merge khi nửa trái đã join và nửa phải đã hoàn tất.

### Merge stable

Giả sử nửa trái L và nửa phải R đều sorted. Dùng hai con trỏ i,j. Mỗi lượt lấy phần tử có khóa nhỏ hơn. **Khi khóa bằng nhau, lấy từ nửa trái trước**:

~~~text
while i < mid AND j < hi:
    if key(a[i]) <= key(a[j]):
        tmp[k++] = a[i++]
    else:
        tmp[k++] = a[j++]

copy remaining left/right
copy tmp[lo..hi) back to a[lo..hi)
~~~

Bản chất của dấu **`≤`** là giữ thứ tự những occurrence bằng khóa. Các item thuộc nửa trái vốn xuất hiện trước những item thuộc nửa phải trong input, nên nếu bằng khóa mà lấy bên phải trước thì phá stability.

### Chứng minh merge đúng

Đầu vòng lặp, phần đã ghi vào tmp là prefix nhỏ nhất có thứ tự của hợp hai dãy đầu vào. Vì cả hai dãy đều sorted, phần tử nhỏ nhất còn lại nằm tại một trong hai đầu i,j. Lấy nó không làm sai prefix. Mỗi lượt tiêu thụ đúng một item; phần còn lại của một phía đã sorted nên có thể copy nguyên. Do đó merge bảo toàn đa tập, sorted, và giữ stability khi tie chọn trái.

### Bỏ merge khi đã có thứ tự

Sau sort hai nửa, nếu `a[mid−1].key≤a[mid].key` thì toàn đoạn đã sorted theo đúng thứ tự, có thể bỏ merge. Với hai nửa stable, việc giữ nguyên thứ tự ấy cũng stable.

## 5. Bộ nhớ phụ và tính an toàn khi hai nửa chạy đồng thời

Mã Java cấp **một** `Item[] tmp` dài n cho toàn bộ merge sort. Một task trên [lo,mid) chỉ ghi `tmp[lo..mid)`, task trên [mid,hi) chỉ ghi `tmp[mid..hi)`. Hai miền rời nhau nên việc dùng **cùng một array object** không tự tạo data race. Parent join các con trước khi đọc/kết hợp.

Nếu mỗi task đều ghi từ `tmp[0]`, hoặc dùng chung một cursor buffer mutable không đồng bộ, dữ liệu sẽ bị phá. Nếu mỗi task cấp một tmp[] kích thước n, tổng bộ nhớ có thể bùng nổ.

**Bộ nhớ dữ liệu phụ:** O(n) references ngoài mảng input, cộng stack và task objects. Đây không phải O(1) chỉ vì tmp được cấp phát đúng một lần.

## 6. Work–span của merge sort có merge tuần tự

Với n đủ lớn, chia hai nhánh gần bằng nhau và merge **tuần tự Θ(n)**:

**`W(n)=2W(n/2)+Θ(n)=Θ(n log n)`**.

Nhưng span chỉ đợi nhánh chậm hơn rồi merge:

**`S(n)=S(n/2)+Θ(n)=Θ(n)`**.

Do đó mức parallelism lý tưởng của thiết kế là **`W/S=Θ(log n)`**, không phải Θ(n). Cài đặt fork/join không làm phép merge cuối cùng của một node tự động song song.

### Parallel merge nâng cao

Có thể chia output merge thành các đoạn độc lập. Với mỗi ranh giới output ở vị trí k, tìm **co-rank (i,j)** trong hai dãy đầu vào sao cho `i+j=k` và đúng thứ tự khóa. Mỗi task merge một cặp lát con của L và R vào một lát output riêng. Co-rank thường xác định bằng binary search O(log n), và stability đòi **quy tắc xử lý tie** đồng nhất giữa các lát.

Song song hóa chính merge có thể hạ span so với Θ(n), nhưng tăng độ phức tạp, số tìm kiếm biên, scratch và đồng bộ. **Code bên dưới chỉ song song hóa hai lời gọi sort con, không cài parallel merge**, nên không được gán cho nó span của thuật toán khác.

## 7. Quicksort: phân hoạch trước rồi mới tạo các task con

Quicksort chọn một khóa **pivot p** và phân đoạn [lo,hi) thành:
- Vùng **L** chứa item có khóa <p.
- Vùng **E** chứa item có khóa =p.
- Vùng **R** chứa item có khóa >p.

Sau đó chỉ cần sort L và R; E không cần sort thêm theo key. Hai vùng L,R có vị trí không giao nhau nên có thể xử lý **song song** sau khi partition hoàn tất.

~~~text
input:
    [ ?  ?  ?  ?  ?  ?  ? ]

partition by pivot p:
    [ keys<p ][ keys=p ][ keys>p ]
        L         E         R

parallel:
    sort(L)   ||   sort(R)
~~~

### Phân hoạch ba vùng (Dutch National Flag)

Đặt:
- `[lo,lt)`: đã xác định khóa <p.
- `[lt,i)`: đã xác định khóa =p.
- `[i,gt]`: chưa phân loại.
- `(gt,hi)`: đã xác định khóa >p.

Khởi tạo `lt=i=lo` và `gt=hi−1`. Khi `i≤gt`:
- Nếu `key(a[i])<p`, swap(a,lt,i), tăng **lt** và **i**.
- Nếu `key(a[i])>p`, swap(a,i,gt), giảm **gt** nhưng **không tăng i** vì item vừa chuyển từ gt về i chưa được kiểm.
- Nếu bằng p, tăng **i**.

Khi kết thúc, vùng chưa phân loại rỗng, tất cả occurrence đã vào đúng một trong ba vùng. Mỗi lần swap chỉ đổi vị trí hai occurrence nên **permutation** được bảo toàn.

### Tại sao ba vùng rất quan trọng?

Với n item có cùng khóa, thuật toán DNF đưa toàn bộ vào E bằng một lượt O(n) và **không đệ quy** vào E. Một quicksort hai vùng kém có thể liên tục sắp lại những item bằng pivot, tạo độ sâu không cần thiết.

### Invariant chứng minh tính đúng

Trong mọi bước, bốn vùng phân hoạch rời nhau và phủ [lo,hi). Các phần tử thuộc ba vùng đã phân loại luôn thỏa quan hệ tương ứng với pivot. Một vòng giảm số item chưa phân loại đi một, nên vòng dừng. Hai lần sort đệ quy trên L,R trả hai dãy sorted; vì mọi khóa L<p=E<p<R theo nghĩa nhóm, toàn đoạn sorted.

## 8. Quicksort in-place không stable

DNF dùng swap để đặt item có khóa nhỏ lên trước; một swap có thể **đảo thứ tự tương đối của các occurrence có khóa bằng nhau**.

Witness:
- 32 Item, 31 Item đầu có key 2 và originalIndex 0..30.
- Item cuối có key 1, originalIndex 31.
- Median-of-three pivot từ đầu/giữa/cuối cho pivot=2.

Khi phân hoạch, `1#31` được swap lên đầu và `2#0` bị đẩy xuống cuối. Dãy đã sorted theo khóa nhưng các Item khóa 2 có thứ tự từ 1..30 rồi 0; đây **không stable**.

Mã demo dùng 32 item vì ngưỡng insertion là 24. Nếu chỉ thử 3 item, chương trình có thể dùng insertion sort stable trên đoạn rất nhỏ và **không thực thi DNF**, khiến bài test thất bại trong việc phơi bày tính không ổn định.

## 9. Median-of-three, worst-case và heapsort dự phòng

Chọn pivot bằng trung vị của khóa đầu, giữa và cuối thường tránh được một số trường hợp xấu của pivot cố định, nhưng **không đảm bảo** hai nhánh cân bằng trên mọi input. Nếu partition cực lệch liên tục, quicksort thuần có worst-case **Θ(n²)**.

Để bảo vệ work, mã dùng biến thể **introspective quicksort**:
- Ngưỡng depth ban đầu **`2·floor(log₂n)`**.
- Mỗi lần partition giảm depth.
- Nếu depth hết mà đoạn vẫn lớn, sort đoạn còn lại bằng **heapsort**.

Heapsort có worst-case O(r log r) trên r item, nên với depth O(log n), tổng work của thuật toán quicksort + fallback có cận **O(n log n)** trong mô hình so sánh O(1), không dựa vào may mắn pivot.

Heapsort **không stable**, nhưng quicksort in-place cũng không hứa stable.

### Hạn chế stack

Khi không fork, mã gọi đệ quy trên **nhánh nhỏ hơn**, rồi dùng vòng while tiếp tục xử lý **nhánh lớn hơn** trong cùng stack frame. Kiểu tail-recursion elimination này giới hạn nhu cầu stack so với việc đệ quy vào nhánh lớn trên một input lệch.

### Không nói depth fallback làm toàn bộ span O(n)

Heapsort fallback có thể thực hiện tuần tự trên một đoạn lớn. Bảo đảm work worst-case O(n log n) **không** đồng nghĩa thời gian trên P core được bảo đảm O(n log n/P), vì span và overhead vẫn tồn tại.

## 10. Work–span của quicksort song song có partition tuần tự

Một lượt DNF partition có:
- Work Θ(n).
- Span Θ(n) vì một task quét liên tục.

Với partition cân bằng:

**`W(n)=2W(n/2)+Θ(n)=Θ(n log n)`**.

**`S(n)=S(n/2)+Θ(n)=Θ(n)`**.

Như merge sort có merge tuần tự, thiết kế **partition tuần tự rồi fork hai vùng** vẫn có critical path Θ(n) trong phân tích cân bằng. Với các nhánh rất lệch, span có thể xấu hơn; depth fallback bảo vệ work nhưng không loại mọi công việc tuần tự lớn.

**Khác biệt về vị trí của pha tuần tự:**
- Merge sort: sort song song **trước**, merge tuần tự **sau**.
- Quicksort: partition tuần tự **trước**, sort song song **sau**.

Nếu hai vùng có size 99% và 1% input, việc fork cả hai thường không giúp nhiều: một worker làm gần hết. Code chỉ fork khi cả hai vùng đủ lớn, và work stealing tận dụng task khác nếu có.

## 11. Phân hoạch thật sự song song qua map–scan–scatter

Muốn nhiều worker **cùng phân loại một đoạn lớn**, không thể đơn giản cho mọi thread sửa chung lt/i/gt bằng swap: dù thêm atomic counters, nhiều bước swap/đổi vùng không còn là một thao tác nguyên tử toàn cục và có thể phá invariant.

Một thiết kế rõ ràng hơn là **stable out-of-place partition** qua **prefix scan**.

Phân loại item theo ba nhóm:
- 0 nếu key<p.
- 1 nếu key=p.
- 2 nếu key>p.

Tại vị trí i, định nghĩa **exclusive prefix counts**:
- `lessBefore(i)`: số item <p trước i.
- `equalBefore(i)`: số item =p trước i.
- `greaterBefore(i)=i−lessBefore(i)−equalBefore(i)`.

Gọi L/E là tổng số item <p và =p trong toàn đoạn. Chỉ số output:

**`dest(i)=lessBefore(i)`** nếu item <p.

**`dest(i)=L+equalBefore(i)`** nếu item =p.

**`dest(i)=L+E+greaterBefore(i)`** nếu item >p.

Ba nhóm đích là những khoảng không chồng:
- `[0,L)`.
- `[L,L+E)`.
- `[L+E,n)`.

Trong mỗi nhóm, exclusive count tăng đúng một khi gặp thêm một occurrence của nhóm, nên **mỗi item có một ô đích duy nhất**, và occurrence đến trước nhận ô đích nhỏ hơn. Do đó cách scatter này **stable** và có thể cho các task ghi **đồng thời vào các vị trí output khác nhau**.

### Ví dụ

Input:

~~~text
[3#0, 1#1, 2#2, 3#3, 1#4, 2#5]
~~~

Pivot p=2, kết quả stable partition:

~~~text
[1#1, 1#4, 2#2, 2#5, 3#0, 3#3]
~~~

Counts: less=2, equal=2, greater=2.

### Ba pha song song

1. **Map/classify:** chia input thành chunk, mỗi worker tính flags/lớp vào vùng riêng.
2. **Parallel scan:** dùng thuật toán work-efficient, ví dụ Blelloch upsweep/downsweep, để tạo prefix counts. Trong mô hình lý tưởng có **O(n) work, O(log n) span**.
3. **Scatter:** mỗi worker tính dest(i) và ghi output[dest(i)]. Chứng minh các dest phân biệt loại bỏ data race do hai worker cùng ghi một phần tử.

**Chi phí:** O(n) bộ nhớ phụ cho output/flags/prefix, không phải partition in-place O(1) scratch. Với một partition O(log n) span và các nhánh sort cân bằng, lý tưởng hóa recurrence span có dạng `S(n)=S(n/2)+O(log n)=O(log² n)`. Đây là **thuật toán khác** so với DNF in-place tuần tự của Java demo; không được gán cận này cho bản demo.

### Tại sao code chỉ cài stable partition bằng prefix tuần tự?

Chương trình có `stablePartitionByPrefix` để minh họa **đúng công thức dest(i)** và dùng làm oracle. Nó tính prefix **tuần tự O(n) span**, vì mục tiêu là phân biệt giữa logic phân hoạch và thiết kế lịch chạy. Để cài scan thật sự song song cần thêm task chia block, tổng khối, offset, barrier và phân chia quyền ghi. **Chỉ khi prefix scan đã được song song hóa** mới có thể nói pha partition có span O(log n) theo mô hình.

## 12. Parallel merge nâng cao vs parallel partition nâng cao

Hai pha cần tối ưu khác nhau:

**Merge:** đã có hai dãy sorted, cần **co-rank** để xác định cặp ranh giới input cho mỗi chunk output. Quan trọng nhất là xử lý đúng tie, để merge stable. Các task ghi các chunk output rời nhau.

**Partition:** chưa có các nhóm sorted, cần biết **mỗi item thuộc nhóm nào và chỉ số output trong nhóm**. Dùng class flags, prefix counts và scatter tránh collision. Output có thể stable theo vị trí nguồn nếu prefix là exclusive và scatter đúng.

Cả hai có thể giảm span theo hướng thấp hơn tuyến tính, nhưng có thể tăng số lần đọc, allocation hoặc synchronization. Không có một chiến lược song song tối ưu tuyệt đối cho mọi n và P.

## 13. Java 17+ hoàn chỉnh

Mã sau chạy độc lập trên JDK 17 hoặc mới hơn. Chỉ dùng thư viện chuẩn.

**`parallelMergeSort`** có một mảng phụ tmp, trộn stable sau join. **`parallelQuickSort`** có DNF partition in-place tuần tự trên từng node, median-of-three, ngưỡng fork và heapsort fallback. **`stablePartitionByPrefix`** là **tham chiếu tuần tự** của prefix scatter, phục vụ học và kiểm thử, không tự tạo task.

Các Item immutable giúp tránh tình huống một worker sửa key trong khi worker khác so sánh; tuy nhiên mảng `Item[]` vẫn mutable nên phạm vi ghi của task vẫn phải rời nhau. Pool được tạo một lần cho cả demo và đóng bằng `shutdown()` sau khi mọi `invoke()` hoàn thành.

Lưu thành tệp **`ParallelMergePartitionSortDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.SplittableRandom;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;

public final class ParallelMergePartitionSortDemo {
    private static final int INSERTION_CUTOFF = 24;
    private static final int PARALLEL_CUTOFF = 2048;

    private record Item(int key, int originalIndex) {
        @Override
        public String toString() {
            return key + "#" + originalIndex;
        }
    }

    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    private static Item[] items(int... keys) {
        Item[] result = new Item[keys.length];
        for (int i = 0; i < keys.length; i++) {
            result[i] = new Item(keys[i], i);
        }
        return result;
    }

    private static void swap(Item[] a, int i, int j) {
        Item tmp = a[i];
        a[i] = a[j];
        a[j] = tmp;
    }

    // Stable for equal keys: shift only when previous > item.
    private static void insertionSort(
            Item[] a, int lo, int hi) {
        for (int i = lo + 1; i < hi; i++) {
            Item value = a[i];
            int j = i;
            while (j > lo
                    && a[j - 1].key() > value.key()) {
                a[j] = a[j - 1];
                j--;
            }
            a[j] = value;
        }
    }

    private static final class MergeTask
            extends RecursiveAction {
        private final Item[] a;
        private final Item[] tmp;
        private final int lo;
        private final int hi;

        MergeTask(Item[] a, Item[] tmp, int lo, int hi) {
            this.a = a;
            this.tmp = tmp;
            this.lo = lo;
            this.hi = hi;
        }

        @Override
        protected void compute() {
            mergeSortRange(a, tmp, lo, hi);
        }
    }

    // Stable merge: choose left when keys are equal.
    private static void merge(
            Item[] a, Item[] tmp,
            int lo, int mid, int hi) {
        int i = lo;
        int j = mid;
        int k = lo;

        while (i < mid && j < hi) {
            if (a[i].key() <= a[j].key()) {
                tmp[k++] = a[i++];
            } else {
                tmp[k++] = a[j++];
            }
        }
        while (i < mid) {
            tmp[k++] = a[i++];
        }
        while (j < hi) {
            tmp[k++] = a[j++];
        }
        System.arraycopy(tmp, lo, a, lo, hi - lo);
    }

    private static void mergeSortRange(
            Item[] a, Item[] tmp,
            int lo, int hi) {
        int length = hi - lo;
        if (length <= INSERTION_CUTOFF) {
            insertionSort(a, lo, hi);
            return;
        }

        int mid = lo + length / 2;
        if (length >= PARALLEL_CUTOFF) {
            MergeTask left = new MergeTask(a, tmp, lo, mid);
            left.fork();
            mergeSortRange(a, tmp, mid, hi);
            left.join();
        } else {
            mergeSortRange(a, tmp, lo, mid);
            mergeSortRange(a, tmp, mid, hi);
        }

        // Both halves sorted and boundary already in order.
        if (a[mid - 1].key() <= a[mid].key()) {
            return;
        }
        merge(a, tmp, lo, mid, hi);
    }

    private static void parallelMergeSort(
            Item[] a, ForkJoinPool pool) {
        if (a == null || pool == null) {
            throw new IllegalArgumentException(
                    "Null array or pool");
        }
        if (a.length < 2) {
            return;
        }
        Item[] tmp = new Item[a.length];
        pool.invoke(new MergeTask(a, tmp, 0, a.length));
    }

    // Median of first, middle and last key, deterministic.
    private static int median3(int a, int b, int c) {
        if (a > b) {
            int t = a;
            a = b;
            b = t;
        }
        if (b > c) {
            int t = b;
            b = c;
            c = t;
        }
        if (a > b) {
            int t = a;
            a = b;
            b = t;
        }
        return b;
    }

    // In-place heapsort of a [lo,hi) range.
    private static void siftDown(
            Item[] a, int lo, int root, int length) {
        while (root < length / 2) {
            int child = 2 * root + 1;
            if (child + 1 < length
                    && a[lo + child].key()
                       < a[lo + child + 1].key()) {
                child++;
            }
            if (a[lo + root].key()
                    >= a[lo + child].key()) {
                return;
            }
            swap(a, lo + root, lo + child);
            root = child;
        }
    }

    private static void heapSortRange(
            Item[] a, int lo, int hi) {
        int length = hi - lo;
        for (int root = length / 2 - 1;
                root >= 0; root--) {
            siftDown(a, lo, root, length);
        }
        for (int end = length - 1; end > 0; end--) {
            swap(a, lo, lo + end);
            siftDown(a, lo, 0, end);
        }
    }

    private static final class QuickTask
            extends RecursiveAction {
        private final Item[] a;
        private final int lo;
        private final int hi;
        private final int depth;

        QuickTask(Item[] a, int lo, int hi, int depth) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.depth = depth;
        }

        @Override
        protected void compute() {
            quickSortRange(a, lo, hi, depth);
        }
    }

    private static void quickSortRange(
            Item[] a, int lo, int hi, int depth) {
        while (hi - lo > INSERTION_CUTOFF) {
            if (depth == 0) {
                heapSortRange(a, lo, hi);
                return;
            }
            depth--;

            int mid = lo + (hi - lo) / 2;
            int pivot = median3(
                    a[lo].key(),
                    a[mid].key(),
                    a[hi - 1].key());

            // [lo,lt) < pivot
            // [lt,i)  = pivot
            // [i,gt]  unknown
            // (gt,hi) > pivot
            int lt = lo;
            int i = lo;
            int gt = hi - 1;

            while (i <= gt) {
                if (a[i].key() < pivot) {
                    swap(a, lt++, i++);
                } else if (a[i].key() > pivot) {
                    swap(a, i, gt--);
                } else {
                    i++;
                }
            }

            int rightStart = gt + 1;
            int leftSize = lt - lo;
            int rightSize = hi - rightStart;

            if (hi - lo >= PARALLEL_CUTOFF
                    && leftSize >= INSERTION_CUTOFF
                    && rightSize >= INSERTION_CUTOFF) {
                QuickTask right = new QuickTask(
                        a, rightStart, hi, depth);
                right.fork();
                quickSortRange(a, lo, lt, depth);
                right.join();
                return;
            }

            // Recurse on smaller side; loop on larger side.
            if (leftSize < rightSize) {
                quickSortRange(a, lo, lt, depth);
                lo = rightStart;
            } else {
                quickSortRange(a, rightStart, hi, depth);
                hi = lt;
            }
        }
        insertionSort(a, lo, hi);
    }

    private static void parallelQuickSort(
            Item[] a, ForkJoinPool pool) {
        if (a == null || pool == null) {
            throw new IllegalArgumentException(
                    "Null array or pool");
        }
        if (a.length < 2) {
            return;
        }
        int log2 = 31
                - Integer.numberOfLeadingZeros(a.length);
        int depthLimit = 2 * log2;
        pool.invoke(new QuickTask(
                a, 0, a.length, depthLimit));
    }

    // SEQUENTIAL prefix-count reference for stable partition.
    // A parallel scan plus disjoint scatter may implement
    // the same mapping, but this function itself is sequential.
    private static Item[] stablePartitionByPrefix(
            Item[] a, int pivot) {
        int n = a.length;
        int[] lessPrefix = new int[n + 1];
        int[] equalPrefix = new int[n + 1];

        for (int i = 0; i < n; i++) {
            lessPrefix[i + 1] = lessPrefix[i]
                    + (a[i].key() < pivot ? 1 : 0);
            equalPrefix[i + 1] = equalPrefix[i]
                    + (a[i].key() == pivot ? 1 : 0);
        }

        int lessCount = lessPrefix[n];
        int equalCount = equalPrefix[n];
        Item[] out = new Item[n];

        for (int i = 0; i < n; i++) {
            int destination;
            if (a[i].key() < pivot) {
                destination = lessPrefix[i];
            } else if (a[i].key() == pivot) {
                destination = lessCount + equalPrefix[i];
            } else {
                int greaterBefore = i
                        - lessPrefix[i] - equalPrefix[i];
                destination = lessCount + equalCount
                        + greaterBefore;
            }
            out[destination] = a[i];
        }
        return out;
    }

    private static boolean isStable(Item[] a) {
        for (int i = 1; i < a.length; i++) {
            Item previous = a[i - 1];
            Item current = a[i];

            if (previous.key() > current.key()) {
                return false;
            }
            if (previous.key() == current.key()
                    && previous.originalIndex()
                       > current.originalIndex()) {
                return false;
            }
        }
        return true;
    }

    private static void verifySortedPermutation(
            Item[] source, Item[] result) {
        check(source.length == result.length,
                "Size mismatch");
        boolean[] seen = new boolean[source.length];

        for (int i = 0; i < result.length; i++) {
            Item item = result[i];
            check(item != null, "Null item");
            int index = item.originalIndex();

            check(index >= 0 && index < source.length,
                    "Invalid source ID");
            check(!seen[index], "Duplicate source ID");
            check(item.equals(source[index]),
                    "Original item changed");
            seen[index] = true;

            if (i > 0) {
                check(result[i - 1].key() <= item.key(),
                        "Not sorted");
            }
        }
    }

    // Independent oracle: concatenate 3 original-order
    // class lists instead of reusing prefix arithmetic.
    private static void verifyStablePartition(
            Item[] source, Item[] partitioned,
            int pivot) {
        int cursor = 0;
        for (int category = 0; category < 3; category++) {
            for (Item item : source) {
                int currentCategory = item.key() < pivot ? 0
                        : item.key() == pivot ? 1 : 2;
                if (currentCategory == category) {
                    check(partitioned[cursor].equals(item),
                            "Stable partition mismatch");
                    cursor++;
                }
            }
        }
        check(cursor == source.length,
                "Partition lost items");
    }

    private static void verifySort(
            Item[] source, ForkJoinPool pool) {
        Item[] expected = source.clone();
        // Stable by Java library contract on Object[].
        Arrays.sort(expected,
                Comparator.comparingInt(Item::key));

        Item[] merged = source.clone();
        parallelMergeSort(merged, pool);
        verifySortedPermutation(source, merged);
        check(Arrays.equals(expected, merged),
                "Stable merge != stable library reference");
        check(isStable(merged), "Merge lost stability");

        Item[] quick = source.clone();
        parallelQuickSort(quick, pool);
        verifySortedPermutation(source, quick);
        // Quicksort is not required to preserve tie order.

        int pivot = source.length == 0
                ? 0 : source[source.length / 2].key();
        verifyStablePartition(
                source,
                stablePartitionByPrefix(source, pivot),
                pivot);
    }

    private static void randomChecks(
            ForkJoinPool pool) {
        SplittableRandom rng =
                new SplittableRandom(5262026L);
        int cases = 0;

        for (int trial = 0; trial < 5000; trial++) {
            int n = rng.nextInt(201);
            Item[] source = new Item[n];
            int mode = trial % 7;

            for (int i = 0; i < n; i++) {
                int key = switch (mode) {
                    case 0 -> i;
                    case 1 -> n - i;
                    case 2 -> 0;
                    case 3 -> i % 7;
                    case 4 -> rng.nextInt(-3, 4);
                    case 5 -> rng.nextInt(-10000, 10001);
                    default -> rng.nextInt(-20, 21);
                };
                source[i] = new Item(key, i);
            }
            verifySort(source, pool);
            cases++;
        }

        // Exercise sizes larger than the fork threshold.
        for (int trial = 0; trial < 32; trial++) {
            int n = PARALLEL_CUTOFF
                    + rng.nextInt(4096);
            Item[] source = new Item[n];

            for (int i = 0; i < n; i++) {
                int key = switch (trial % 4) {
                    case 0 -> i;
                    case 1 -> n - i;
                    case 2 -> i % 31;
                    default -> rng.nextInt(-2000, 2001);
                };
                source[i] = new Item(key, i);
            }
            verifySort(source, pool);
            cases++;
        }

        check(cases == 5032, "Wrong case count");
        System.out.println(
                "Randomized sort checks: 5032 PASS");

        // Independently exercise the depth fallback sorter.
        for (int trial = 0; trial < 300; trial++) {
            int n = rng.nextInt(301);
            Item[] source = new Item[n];

            for (int i = 0; i < n; i++) {
                source[i] = new Item(
                        rng.nextInt(-100, 101), i);
            }
            Item[] result = source.clone();
            heapSortRange(result, 0, n);
            verifySortedPermutation(source, result);
        }
        System.out.println(
                "Heapsort fallback checks: 300 PASS");
    }

    public static void main(String[] args) {
        int workers = Math.max(1,
                Math.min(4, Runtime.getRuntime()
                        .availableProcessors()));
        ForkJoinPool pool = new ForkJoinPool(workers);

        try {
            Item[] demo = items(4, 1, 4, 2, 4, 1);
            parallelMergeSort(demo, pool);
            System.out.println(
                    "Stable merge: " + Arrays.toString(demo));
            System.out.println(
                    "Merge stable verified: "
                    + isStable(demo));

            Item[] source = items(3, 1, 2, 3, 1, 2);
            Item[] partition = stablePartitionByPrefix(
                    source, 2);
            System.out.println(
                    "Stable partition pivot=2: "
                    + Arrays.toString(partition));

            Item[] witness = new Item[32];
            for (int i = 0; i < witness.length; i++) {
                witness[i] = new Item(
                        i == 31 ? 1 : 2, i);
            }
            Item[] originalWitness = witness.clone();
            parallelQuickSort(witness, pool);
            verifySortedPermutation(
                    originalWitness, witness);
            System.out.println(
                    "Three-way quick witness sorted: true");
            System.out.println(
                    "Three-way quick witness stable: "
                    + isStable(witness));

            Item[] empty = items();
            Item[] single = items(7);
            parallelMergeSort(empty, pool);
            parallelQuickSort(empty, pool);
            parallelMergeSort(single, pool);
            parallelQuickSort(single, pool);
            check(empty.length == 0
                    && single.length == 1
                    && single[0].key() == 7,
                    "Bad empty/singleton");
            System.out.println("Empty/singleton: PASS");

            randomChecks(pool);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 ParallelMergePartitionSortDemo.java
java ParallelMergePartitionSortDemo
~~~

**Stdout chính xác của chương trình:**

~~~text
Stable merge: [1#1, 1#5, 2#3, 4#0, 4#2, 4#4]
Merge stable verified: true
Stable partition pivot=2: [1#1, 1#4, 2#2, 2#5, 3#0, 3#3]
Three-way quick witness sorted: true
Three-way quick witness stable: false
Empty/singleton: PASS
Randomized sort checks: 5032 PASS
Heapsort fallback checks: 300 PASS
~~~

### Giải thích các kết quả

**Stable merge:** khóa 1 theo thứ tự occurrence 1,5; khóa 4 theo 0,2,4. Tính đúng được kiểm không chỉ qua sortedness mà còn qua định danh của từng occurrence.

**Stable partition:** công thức prefix counts tạo đúng ba nhóm <2,=2,>2 và bảo toàn thứ tự đến bên trong từng nhóm. Hàm này **tuần tự**, dùng làm mô hình của một bước partition có thể được triển khai song song bằng scan.

**Quick witness:** tất cả khóa đều được sắp đúng, nhưng một item khóa 2 bị swap qua các item khóa 2 khác. Hàm `isStable` trả false đúng theo tính chất DNF in-place.

**Empty/singleton:** n=0 hoặc 1 phải kết thúc an toàn, không gọi median-of-three hay truy cập index ngoài mảng.

**Randomized checks:** mã kiểm 5000 dãy nhỏ và 32 dãy lớn, trong đó:
- Merge so **chính xác từng Item** với `Arrays.sort(Object[], Comparator)`, vốn stable theo hợp đồng JDK.
- Quick kiểm keys tăng dần và mỗi Item xuất hiện đúng một lần; **không ép** kết quả có thứ tự tie giống stable reference.
- Stable prefix partition so với oracle ghép ba nhóm bằng vòng lặp trực tiếp, **không** dùng lại công thức prefix counts.
- 300 lần nữa kiểm trực tiếp heapsort dùng cho nhánh depth fallback.

Đây là QA correctness. Nó **không** đo throughput, scalability hay cam kết tăng tốc.

## 14. Oracle độc lập và kết quả kiểm thử mô hình

Để giảm rủi ro một lỗi giống nhau xuất hiện trong cả code và test, một mô hình thuật toán tách riêng đã được kiểm bằng các oracle khác cách triển khai:

- **18.000** dãy nhỏ với dữ liệu tăng, giảm, toàn bằng nhau, tuần hoàn và ngẫu nhiên có nhiều khóa lặp.
- **500** dãy lớn với độ dài 2048..10000.
- **5000** bài thử heapsort trực tiếp với đường fallback.
- Tổng **23.500 trường hợp sắp xếp**; mỗi merge result được so với stable reference và mỗi quick/heap result được kiểm tăng dần, không mất/trùng occurrence.
- **170.588 lượt DNF partition** được đối chiếu trực tiếp bất biến ba vùng <pivot,=pivot,>pivot.
- **30.000 lần stable three-way partition bằng prefix counts**, trên **1.807.399 occurrence**, được so với oracle ghép các nhóm theo thứ tự input.
- Một witness 32 item xác nhận **quicksort sorted=true nhưng stable=false**.

Các thử nghiệm đều đạt. Đây là kiểm thử hữu hạn, **không thay thế chứng minh toán học** cho mọi n. Muốn khẳng định correctness, cần dựa vào invariant DNF, invariant merge, tính disjoint của các đoạn task và việc parent join đúng.

## 15. Cách kiểm chứng không có data race

Mỗi task trong merge sort sở hữu một đoạn [lo,hi):
- Task trái chỉ sửa [lo,mid).
- Task phải chỉ sửa [mid,hi).
- Buffer tmp có cùng phân vùng chỉ số.
- Parent join trước khi merge.

Trong quicksort:
- **Partition thực hiện xong trước khi fork**.
- L và R là hai đoạn không chồng nhau.
- Mỗi task chỉ sửa đoạn của mình.
- Vùng bằng pivot không bị đệ quy sửa lại.
- Các task cùng dùng một `ForkJoinPool`, nhưng không chia sẻ biến lt/i/gt của partition cha.

Trong prefix scatter có thể song song:
- Mỗi item có một chỉ số dest(i) **duy nhất** nhờ exclusive prefix.
- Các lớp sử dụng những khoảng output rời nhau.
- Các task phải hoàn thành map/scan **trước khi** scatter.
- Không đọc vùng output trong lúc một task khác chưa ghi xong phần tử tương ứng.

**False sharing** khác data race: hai task có thể sửa hai ô khác nhau nhưng nằm trong cùng cache line, gây giảm hiệu năng mà không sai ngữ nghĩa.

### Kiểm thử race không chỉ bằng một seed

Một chương trình có race có thể PASS nhiều lần rồi fail khi scheduler thay đổi. Ngoài unit test, nên chạy với P=1,2,4,8 trên các kích thước lớn, kết hợp công cụ kiểm race/profiler phù hợp môi trường, và rà soát thủ công quyền ghi/dữ liệu chia sẻ. Java ThreadSanitizer hỗ trợ hay không còn phụ thuộc runtime/toolchain; không khẳng định công cụ có sẵn trên mọi JDK.

## 16. Vì sao không phải cứ có task là nhanh hơn

Chi phí thực tế:
- Fork/join và task scheduling.
- Lập tức copy dữ liệu vào tmp trong merge.
- Cache misses và băng thông RAM.
- Tranh shared cache/false sharing.
- Garbage collection do cấp quá nhiều task.
- Work imbalance do pivot.
- CPU quotas hoặc scheduler không có đủ core.

Một benchmark đúng cần:
1. Chạy warm-up để JIT tối ưu, rồi đo các lượt ổn định.
2. Dùng **cùng dữ liệu** cho so sánh P=1 và P>1.
3. So với phiên bản tuần tự tương ứng cùng comparator và algorithm.
4. So với `Arrays.sort` và `Arrays.parallelSort` trong JDK.
5. Thử các phân phối: sorted, reverse, all equal, ít giá trị, rất nhiều giá trị, nhiều duplicates.
6. Đo median/percentiles nhiều lần, không dùng một thời gian chạy.
7. Ghi n, P, JVM/CPU, heap, GC, threshold và số task.
8. Tiêu thụ/kiểm output để tránh benchmark bỏ việc hoặc chỉ đo setup.

Không dùng một tốc độ “x nhanh hơn 3×” nếu chưa có kết quả đo thực và mô tả điều kiện. **Bản Java minh họa không in thời gian**, vì mục tiêu là dạy thuật toán đúng.

### Tạo pool một lần hay tính cả thời gian tạo pool?

Hai phép đo hợp lệ:
- **Steady-state sort time:** pool tạo sẵn, đo riêng thời gian sort.
- **End-to-end latency:** bao gồm tạo pool, cấp buffer, sort, thu output.

Phải nói rõ đang so thước đo nào. Nếu một đối thủ đo gồm tạo pool còn đối thủ khác dùng pool có sẵn, benchmark có thể thiếu công bằng.

## 17. Phân tích chi phí bộ nhớ

**Parallel merge sort:**
- Input Item[]: O(n).
- tmp Item[]: O(n) tham chiếu.
- Task/stack: thêm bộ nhớ phụ tùy số task sống và số worker.
- Merge trên từng node: có truy cập/copy tuần tự, thường tốt về locality nhưng có thể bị giới hạn bởi memory bandwidth.

**Parallel DNF quicksort:**
- Partition sử dụng swap trong chính Item[], không có tmp n-element riêng.
- Heap fallback in-place ngoài stack/hằng số phụ.
- Task objects và stack của nhiều worker không miễn phí; tổng auxiliary memory có thể lớn hơn O(log n) của quicksort tuần tự.
- Pivot và data layout tác động tới locality.

**Stable parallel partition bằng scan:**
- Cần output array và flags/prefix hoặc bộ đếm theo chunk.
- O(n) memory đơn giản.
- Scatter đúng với nhiều task nhưng có overhead từ scan/barriers/allocations.

Không kết luận thuật toán nào luôn có ít **bytes allocated** hơn chỉ từ big-O; cần đo trên JVM đang dùng.

## 18. Độ phức tạp và giới hạn tổng hợp

| Tiêu chí | Parallel merge sort (code) | Parallel 3-way quicksort (code) |
|---|---|---|
| Chia bài | Chia đôi | Partition theo pivot |
| Pha tuần tự tại node | Merge sau join | DNF partition trước fork |
| Work thông thường | Θ(n log n) | Θ(n log n) khi cân bằng |
| Worst-case work | O(n log n) | O(n log n) nhờ heapsort fallback |
| Span khi cân bằng | Θ(n) | Θ(n) |
| Đảm bảo stable | Có | Không |
| Bộ nhớ dữ liệu phụ | O(n) tmp | In-place swap, thêm task/stack |
| Duplicates nhiều | Vẫn chia đôi | Three-way skip nhóm =pivot |
| Task con có ghi chồng không? | Không, nếu đúng đoạn | Không, nếu partition hoàn thành |
| Để hạ span của pha chính | Parallel merge/co-rank | Parallel partition/prefix scan |

Lưu ý: các cận xét comparator có chi phí O(1), bỏ qua scheduling. Với pivot lệch, quicksort có span lớn hơn; với intro fallback, work vẫn có worst-case cận nhưng một nhánh fallback có thể tuần tự.

## 19. Một số lựa chọn khác trong Java

**`Arrays.sort`:**
- Với object[] và Comparator, Java cung cấp một sort **stable** theo hợp đồng API.
- Với primitive arrays, implementation và bảo đảm ổn định không được suy từ object comparator sort.
- Không tự mặc định nó sẽ dùng tất cả core.

**`Arrays.parallelSort`:**
- API tiện dụng cho mảng lớn, có triển khai song song nội bộ và chính sách ngưỡng riêng.
- Cần đọc hợp đồng API cho overload cụ thể khi xét stability và comparator.
- Không phải “luôn nhanh hơn Arrays.sort”: dữ liệu nhỏ hoặc máy ít core có thể bị overhead.

**`ForkJoinPool` custom:**
- Kiểm soát số worker, giới hạn concurrency của ứng dụng.
- Cần dùng lại pool và có vòng đời rõ.
- Không nên tạo pool cho mọi lần gọi sort nhỏ.

**Stream.parallel():**
- Phù hợp một số tác vụ data-parallel, nhưng không thay thế trực tiếp cấu trúc chia để trị trong mọi sort; chi phí boxing/collecting và semantics cần đánh giá.
- Không dùng `parallel()` tùy tiện trên stream rồi tưởng đã được một partition có map–scan–scatter đúng.

## 20. Trường hợp đặc biệt và sai sót hay gặp

### Input rỗng và singleton

n=0/1 không chia, không gọi median/pivot. Nếu tính `log₂0` sẽ không có nghĩa; chương trình trở về ngay trước khi tính depth.

### Mảng tăng hoặc giảm

Merge sort ổn định và dùng cùng recurrence, nhưng có thể bỏ một số merge nếu boundary đã sorted. Quicksort dùng median-of-three để giảm rủi ro pivot xấu ở những dạng dữ liệu đơn giản, nhưng không loại hết worst-case adversarial input.

### Mảng toàn bằng nhau

Merge sort vẫn chia đôi/trộn hoặc bỏ merge khi boundary đã sorted; quicksort DNF đưa tất cả vào lớp =pivot và kết thúc sau một partition lớn. Đây là một lý do cần test riêng nhiều duplicate.

### Item cực trị int

So khóa bằng `Integer.compare` hoặc toán tử so sánh trực tiếp, không dùng hiệu int. OriginalIndex là int hợp lệ trong range array, kiểm lại khi đối chiếu permutation.

### n lớn và threshold

Nếu threshold quá thấp, chương trình sinh nhiều task làm tăng GC/scheduling overhead. Nếu quá cao, ít worker hoạt động song song. Ngưỡng cần tune; không có giá trị đúng tuyệt đối.

### Thread safety

Không gọi hai sort đồng thời **trên cùng một mảng**. Dù mỗi thuật toán chia task nội bộ đúng, hai cuộc gọi bên ngoài không phối hợp quyền ghi. Mutable Item/key/callback cũng có thể gây race khi comparator đọc.

## 21. Những lỗi thường gặp

1. **Tạo một thread cho mỗi phần tử** thay vì phân đoạn task.
2. **Cấp ForkJoinPool mới cho mỗi node**.
3. **Không đặt ngưỡng PARALLEL_CUTOFF**, fork quá nhiều task nhỏ.
4. **Không join**, parent merge trước khi con hoàn tất.
5. **Merge chọn item bên phải khi khóa bằng** và vẫn gọi stable.
6. **Hai MergeTask ghi cùng vùng tmp**, gây race.
7. **Mỗi task dùng tmp từ index 0** thay vì offset của đoạn.
8. **Dùng nhầm [lo,hi) và [lo,hi]**, sai biên.
9. **Tính mid=(lo+hi)/2 trên int lớn**, nguy cơ overflow.
10. **Quicksort tự nhận stable**, không kiểm witness.
11. **Chỉ kiểm sortedness mà không kiểm permutation**.
12. **Không giữ originalIndex khi test stability**.
13. **Tăng i sau swap với gt trong DNF**, bỏ qua item mới chuyển về.
14. **Đệ quy cả vùng =pivot**, giảm hiệu quả khi nhiều key trùng.
15. **Cho median-of-three luôn cân bằng**, sai với nhiều input.
16. **Không có depth fallback nhưng tuyên bố O(n log n) worst-case**.
17. **Cho heapsort stable**, không đúng.
18. **Heapsort ngoài phạm vi [lo,hi)**, sửa vùng task khác.
19. **So khóa bằng phép trừ int**, có thể overflow.
20. **Comparator có side effects hoặc mutable state**.
21. **Sử dụng synchronized cho vài swap và tưởng đã có parallel DNF đúng**, thiếu invariant toàn cục.
22. **Cấp một cursor output chung mà không tạo các dest riêng**, collision.
23. **Nhầm inclusive prefix với exclusive prefix**, lệch chỉ số scatter.
24. **Quên cộng offset L, L+E** cho hai lớp sau.
25. **Không chứng minh các dest(i) phân biệt**, có thể viết chồng.
26. **Gọi scan tuần tự là span O(log n)**, không đúng.
27. **Báo span O(log n) cho merge có merge tuần tự Θ(n)**.
28. **Báo speedup luôn bằng P**, bỏ qua span và overhead.
29. **Gọi một phiên bản quicksort partition tuần tự là “parallel partition”**, nhầm pha.
30. **Cho bản mẫu có span O(log² n) như scan-based algorithm**, sai.
31. **Không tính O(n) memory của prefix scatter**.
32. **Quên join task forked khi hàm trả về**, output có thể chưa hoàn tất.
33. **Chạy hai sorts trên cùng array đồng thời**, race giữa hai cuộc gọi.
34. **Nhầm false sharing với data race**, đánh giá sai correctness.
35. **Cho một item immutable nghĩa là toàn bộ array thread-safe**, không đúng.
36. **Chỉ test n lẻ hoặc n lũy thừa hai**, thiếu ranh giới.
37. **Không test mảng toàn equal và nhiều duplicates**, bỏ lỗi 3-way/tie.
38. **Chỉ test n nhỏ dưới cutoff**, chưa đi qua fork/partition.
39. **Không kiểm heapsort fallback trực tiếp**, nhánh phòng lỗi có thể hỏng.
40. **Một lần random PASS được xem là chứng minh mọi input**, không đủ.
41. **Dùng một lần stopwatch trước warm-up JVM để so tốc độ**.
42. **So P=4 nhưng thực tế chỉ có 1 core dành cho app**, diễn giải sai.
43. **Không so với Arrays.sort hoặc Arrays.parallelSort**, thiếu baseline.
44. **Không tính bộ nhớ task/stack và buffer tmp**, thiếu trade-off.
45. **Trộn hiệu năng của thao tác parallel scan lý tưởng với code tuần tự đã viết**, phóng đại tốc độ.

## 22. Bài tập tự luyện

**Bài 1 — Stable merge:** Tự merge [1#1,4#0,4#2] với [1#5,2#3,4#4] bằng tie-left. Kết quả phải giữ thứ tự chỉ số gốc của các khóa bằng nhau.

**Bài 2 — 3-way partition:** Với [3,1,2,3,1,2] và pivot 2, ghi trạng thái lt,i,gt sau từng bước. Vì sao nhánh > không tăng i?

**Bài 3 — Witness instability:** Dùng 32 item có 31 key2 và item cuối key1, xác định swap làm Item 2#0 về cuối, phá stability.

**Bài 4 — Work/span merge:** Giải W(n)=2W(n/2)+n và S(n)=S(n/2)+n. Giải thích vì sao hai nhánh song song không làm merge cuối biến mất.

**Bài 5 — Work/span partition:** Giải cùng recurrence cho partition tuần tự và phân tích trường hợp lệch một nhánh n−1, một nhánh 0.

**Bài 6 — Prefix scatter:** Tính lessBefore, equalBefore, greaterBefore và dest(i) với [3#0,1#1,2#2,3#3,1#4,2#5], p=2.

**Bài 7 — Parallel scan:** Thiết kế prefix sum work-efficient O(n) work và O(log n) span. Cần những bước đồng bộ nào trước scatter?

**Bài 8 — Co-rank:** Cho L=[1,2,2], R=[2,3] và cần merge stable. Xác định cách chia output thành hai chunk mà không đảo tie.

**Bài 9 — Depth limit:** Thử depth=0 cho một đoạn lớn, dùng heapSortRange; kiểm output với sắp xếp tham chiếu.

**Bài 10 — Thread safety:** Vẽ những vùng ghi A/tmp của hai MergeTask và chứng minh chúng không chồng. Thay đổi giả thiết để tạo một race.

**Bài 11 — Duplicate data:** Sinh mảng toàn key=0 có 100.000 Item, so số bước partition DNF với phiên bản 2-way kém.

**Bài 12 — Threshold:** Thử các ngưỡng 512,2048,8192 và số workers 1,2,4. Đo thời gian nhiều trial có warm-up.

**Bài 13 — Stable oracle:** Kiểm merge sort với mỗi key gắn originalIndex; vì sao Arrays.equals trên int[] không phát hiện đảo các occurrence bằng key?

**Bài 14 — Merge buffer:** Thiết kế một phiên bản chỉ cấp tmp[] đúng một lần; giải thích bộ nhớ O(n) và chi phí copy.

**Bài 15 — Comparator:** So Integer.MAX_VALUE với −1 bằng phép trừ int và Integer.compare; tìm lỗi overflow.

**Bài 16 — Parallel partition:** Viết map/scan/scatter cho ba lớp, chứng minh không có hai item ghi cùng dest.

**Bài 17 — Benchmark:** So Arrays.sort, Arrays.parallelSort, merge sort custom và quicksort custom trên các kích thước từ 100 tới vài triệu, phân biệt correctness và speedup.

**Bài 18 — Memory trade-off:** Ước lượng RAM phụ của stable merge O(n), DNF in-place và prefix-scan stable partition O(n), thêm overhead task.

**Bài 19 — Input rỗng/nhỏ:** Kiểm n=0,1,2,23,24,25,2047,2048,2049. Xác định nhánh nào chạy ở mỗi ngưỡng.

**Bài 20 — Thiết kế mới:** Phác thảo parallel stable quicksort dùng prefix scatter ở mọi node và phân tích điều kiện để span lý tưởng O(log² n).

## 23. Checklist cuối bài

- Đã xác định comparator và yêu cầu stability?
- Có giữ originalIndex để kiểm đúng thứ tự các occurrence bằng key?
- Các đoạn task con có ghi **rời nhau**?
- Parent có join trước khi merge/đọc kết quả con?
- Merge chọn trái khi bằng khóa?
- tmp[] có được dùng đúng offset và chỉ cấp một lần?
- Quicksort có three-way partition và bỏ qua =pivot?
- DNF có giữ invariant bốn vùng và không tăng i ở nhánh >?
- Có median/pivot policy và bảo vệ worst-case nếu cần?
- Có depth fallback và kiểm riêng heapsort?
- Có insertion/parallel thresholds?
- Có dùng ForkJoinPool tái sử dụng và tránh tạo thread/task quá nhỏ?
- Có phân biệt **parallel recursive sorts** với **parallel merge/partition**?
- Nếu dùng scan, có exclusive prefix và scatter collision-free?
- Có hiểu cận work/span của pha tuần tự tại mỗi node?
- Có test sorted, permutation và stability theo hợp đồng?
- Có test random, reverse, all equal, nhiều duplicate, empty, singleton, cutoff±1?
- Có benchmark P=1 và P>1, warm-up, cùng input và nhiều trial?
- Có so với thư viện Java chuẩn và báo rõ bộ nhớ/speedup?

**Kết luận:** parallel merge sort **chia và sort hai nửa song song rồi trộn stable**, còn parallel quicksort **phân hoạch theo pivot rồi sort các vùng độc lập song song**. Chúng phải xử lý đúng **quyền ghi vùng nhớ, join, duplicates, stability và task granularity**. Với merge/partition **tuần tự** trên từng node như Java demo, work cân bằng Θ(n log n) nhưng span Θ(n), nên thêm core không đem lại speedup tùy ý. Để song song hóa chính pha nặng có thể dùng **co-rank parallel merge** hoặc **parallel prefix scan + scatter** với các vùng output không chồng nhau; chúng đổi chi phí bộ nhớ/đồng bộ để giảm span. Một triển khai đáng tin cần được kiểm bằng oracle độc lập, không bịa benchmark và luôn phân biệt bảo đảm toán học với kết quả đo thực tế.