# Ghi rõ giả thiết, bất biến và giới hạn sử dụng của lời giải

Một lời giải thuật toán **không đúng vô điều kiện chỉ vì biên dịch được và chạy qua ví dụ mẫu**. Tìm kiếm nhị phân cần dữ liệu được sắp xếp; cửa sổ trượt tìm đoạn ngắn nhất đạt ngưỡng cần tính đơn điệu, chẳng hạn các phần tử không âm; Dijkstra cần trọng số cạnh không âm. Nếu các giả thiết ấy không được ghi rõ, lời giải dễ được tái sử dụng với đầu vào sai và trả kết quả sai mà không báo lỗi.

Bài thuộc nhóm **Cài đặt và kiểm thử**, tập trung vào cách mô tả và kiểm chứng **giả thiết (assumptions/preconditions)**, **bất biến (invariants)**, **hậu điều kiện (postconditions)** và **giới hạn sử dụng (limitations)**. Một README thuật toán tốt phải trả lời được: nhận input nào, trả output gì, tại sao đúng, khi nào dừng, chi phí tài nguyên bao nhiêu, số học có tràn không, và khi dữ liệu không thuộc miền hợp lệ chương trình xử lý ra sao.

Bài dùng **ba ví dụ Java 17+ có thể chạy độc lập**: `lowerBoundAssumingSorted` (tìm ranh giới trong mảng sorted), `minimumWindowAtLeast` (cửa sổ trượt trên dãy không âm) và `dijkstra` (đồ thị trọng số không âm, sentinel `INF` dành riêng). Bộ kiểm thử so với oracle độc lập qua **800 dãy**, **600 bài cửa sổ** và **400 đồ thị**. Các kiểm thử củng cố bằng chứng thực nghiệm nhưng không thay thế chứng minh tính đúng bằng bất biến.

## 1. Bốn khái niệm không được đánh đồng

| Khái niệm | Thời điểm cần đúng | Câu hỏi | Ví dụ |
| --- | --- | --- | --- |
| **Precondition** | Trước khi gọi | Input và môi trường phải thỏa điều gì? | Mảng đã sắp xếp không giảm |
| **Invariant** | Tại các ranh giới trạng thái/vòng lặp | Điều gì luôn được bảo toàn? | Mọi vị trí trước `lo` nhỏ hơn target |
| **Postcondition** | Khi hàm trả thành công | Kết quả cam kết điều gì? | Chỉ số đầu tiên có giá trị ≥ target |
| **Limitation** | Trong thiết kế và lúc sử dụng | Thuật toán/biểu diễn không hỗ trợ gì? | Fast API không tự kiểm tra mảng sorted |

Ví dụ câu “mảng đã được sắp xếp” là **tiền điều kiện**, không phải một bất biến mà tìm kiếm nhị phân tự tạo. Câu “hàm trả chỉ số trong `[0,n]`” là **hậu điều kiện**. Câu “mảng có thể chứa tối đa số phần tử vừa heap JVM” là **giới hạn tài nguyên**. Một chương trình có thể giữ bất biến vòng lặp nhưng vẫn sai nếu tiền điều kiện không thỏa hoặc phép cộng bị tràn kiểu nguyên.

### 1.1. Giả thiết phải kiểm tra hay chỉ được caller cam kết?

Hai thiết kế API đều hợp lý:

- **Fast API**: caller phải đưa mảng sorted, hàm không quét kiểm tra lại; giữ độ phức tạp `O(log(n+1))`.
- **Checked API**: kiểm tra tính sorted trong `O(n)`, sau đó tìm kiếm `O(log(n+1))`; toàn bộ chi phí là `O(n)`.

Không được viết README của Checked API là `O(log n)` vì bước kiểm tra làm tăng độ phức tạp. Ngược lại, không được quảng cáo Fast API là “tự phát hiện mọi đầu vào chưa sorted” khi không có validation. Hợp đồng nêu **ai chịu trách nhiệm bảo đảm precondition**.

### 1.2. Đầu vào sai và “không có đáp án” khác nhau

Với `lower_bound`, nếu không có phần tử lớn hơn hoặc bằng target, trả **n** là một kết quả hợp lệ. Với `minimumWindowAtLeast`, không tồn tại cửa sổ thì trả **0**. Đồ thị có đỉnh không thể tới trả ký hiệu **INF** tại vị trí ấy. Những trạng thái này không phải lỗi input; cần phân biệt với `IllegalArgumentException` do mảng không sorted hoặc cạnh âm và `ArithmeticException` do tính toán ngoài miền số học.

## 2. Khuôn mẫu một đặc tả đủ để triển khai và review

Có thể dùng khuôn sau, điền bằng điều kiện thực sự của bài toán:

```text
NAME/GOAL:
    Bài toán toán học và ý nghĩa kết quả.

INPUT:
    Kiểu dữ liệu, chỉ số, rỗng/null, dấu, định dạng.

PRECONDITIONS:
    Thứ tự / tính đơn điệu / cấu trúc / miền / tính bất biến.
    Caller cam kết gì? API tự kiểm tra gì?

STATE/INVARIANTS:
    Trạng thái theo vòng lặp, ranh giới quan sát, mệnh đề bảo toàn.

TERMINATION:
    Đại lượng nào không âm và giảm đến khi dừng?

POSTCONDITIONS:
    Đầu ra đúng chính xác thế nào?
    Không có nghiệm, trùng nhau, hòa điểm được xử lý ra sao?
    Đầu vào có bị thay đổi không?

NUMERIC/REPRESENTATION LIMITS:
    int/long/BigInteger, INF, overflow, modulo, precision.

COMPLEXITY:
    Thời gian, bộ nhớ phụ, recursion stack, I/O nếu liên quan.
    Tính validation và preprocessing hay chưa?

UNSUPPORTED/FAILURE:
    Throw, return status, fallback hoặc trách nhiệm caller.

TEST EVIDENCE:
    Biên, invalid input, oracle độc lập, random seed.
```

Cấu trúc này hữu ích hơn một chú thích “works in most cases”, vì người khác có thể viết **test từ từng dòng hợp đồng**. Các tiền điều kiện quan trọng nên xuất hiện trong tài liệu public hoặc JavaDoc; chứng minh sâu hơn có thể nằm trong README.

### 2.1. Cách viết có tính hình thức

Trong Hoare logic, một đặc tả cơ bản có dạng:

```text
{P} algorithm {Q}
```

`P` là tiền điều kiện, `Q` là hậu điều kiện. Với một vòng lặp, viết thêm bất biến `I` và hàm giảm `V` (ranking function) để chứng minh:

1. **Khởi tạo**: Từ P, trước vòng đầu tiên I đúng.
2. **Bảo toàn**: Từ I và điều kiện lặp, sau mỗi nhánh cập nhật I vẫn đúng.
3. **Kết thúc**: V là số nguyên không âm (hoặc thuộc tập có thứ tự tốt) và giảm nghiêm ngặt.
4. **Đáp án**: Khi vòng lặp kết thúc, I cùng điều kiện dừng suy ra Q.
5. **Hợp lệ của phép toán**: Mọi index và phép toán trung gian đều thuộc miền biểu diễn cho phép.

Nếu chỉ có I mà không chứng minh termination, ta mới có **partial correctness**. Nếu chứng minh thuật toán toán học trên số nguyên không giới hạn nhưng Java dùng `long` có thể overflow, chứng minh chưa áp dụng cho implementation.

## 3. Nhóm giả thiết cần rà soát trước khi chọn thuật toán

**Hình dạng và kích thước:** n có thể bằng 0? Có mảng jagged hay phải hình chữ nhật? Đồ thị có V=0, self-loop, nhiều cạnh hoặc đỉnh cô lập không? Mỗi record có null không?

**Thứ tự và tính đơn điệu:** Mảng có sorted theo comparator hiện hành? Khóa có trùng? Phép sliding window cần phần tử không âm hay chỉ cần tổng cửa sổ có tính đơn điệu khác? Heuristic dùng trong A* có thỏa điều kiện đủ để đạt optimality không?

**Miền dấu và biểu diễn số:** Có số âm, zero, `Integer.MIN_VALUE`, `Long.MAX_VALUE`? Tổng và tích **trung gian** có vừa kiểu không? Có dùng modulo m, m có dương không? Giá trị vô cực được biểu diễn ra sao và có thể trùng đáp án hữu hạn không?

**Trạng thái dữ liệu:** Input bất biến trong quá trình xử lý hay có concurrent mutation? Có cho phép online updates? Cấu trúc chứa trong RAM hay cần thuật toán ngoài bộ nhớ?

**Ngữ nghĩa kết quả:** Trả một nghiệm, nghiệm nhỏ nhất, tất cả nghiệm hay đếm số nghiệm? Trả phần tử đầu tiên hay bất kỳ phần tử nào? Tính đúng theo tập hợp hay đa tập? Khi không có đáp án trả gì?

**Nguồn tài nguyên:** Độ phức tạp tính cả bước kiểm tra input chưa? Bộ nhớ phụ khác với kích thước input ra sao? Đệ quy có thể gây stack overflow không? Tính toán song song có yêu cầu synchronization và điều kiện happens-before không?

Một thay đổi nhỏ ở đề bài có thể phá hợp đồng. Ví dụ chuyển “trọng số cạnh không âm” thành “có thể âm” là **thay đổi correctness domain của Dijkstra**, không phải chỉ là thêm một test.

## 4. Ví dụ 1: tìm kiếm nhị phân cần mảng sorted

Bài toán: tìm chỉ số đầu tiên `i` có `a[i]>=target`; nếu không có, trả `n`. Mảng là `int[]` không giảm, có thể rỗng và chứa số âm/trùng nhau.

### 4.1. Đặc tả trước khi viết code

```text
PRE:
  array != null.
  array[i] <= array[i+1] với mọi i hợp lệ.

POST:
  0 <= result <= n.
  Mọi i < result: array[i] < target.
  Mọi i >= result: array[i] >= target.

LIMITS:
  Fast API tin sortedness của caller, không tự kiểm tra.
  Checked wrapper quét O(n) trước khi tìm.
  Không mutate input.
```

Với `[1,2,2,2,5]`:

```text
target=2 -> result=1
target=3 -> result=4
target=7 -> result=5
```

Nếu `n=0`, luôn trả `0`. Điều này vẫn phù hợp `0<=result<=n`.

### 4.2. Bất biến vòng lặp

Ta duy trì:

```text
0 <= lo <= hi <= n.
Mọi phần tử tại index < lo có giá trị < target.
Mọi phần tử tại index >= hi có giá trị >= target.
```

Ban đầu `lo=0`, `hi=n`; hai miền đã phân loại đều rỗng. Ở mỗi vòng:

```java
int mid = lo + (hi - lo)/2;
if (array[mid] < target) lo = mid+1;
else hi = mid;
```

Nếu phần tử giữa nhỏ hơn target, **nhờ mảng sorted**, tất cả phần tử trước hoặc bằng giữa đều nhỏ hơn target, nên có thể tăng lo. Nếu phần tử giữa ≥ target, mọi phần tử từ mid trở đi đều ≥target, nên giảm hi. Bất biến vẫn đúng. `hi-lo` giảm nghiêm ngặt khi `lo<hi`, nên thuật toán kết thúc tại `lo==hi`; từ bất biến suy ra đó là ranh giới đầu tiên cần tìm.

Công thức midpoint `lo+(hi-lo)/2` an toàn hơn `(lo+hi)/2` với chỉ số int không âm.

### 4.3. Phản ví dụ nếu bỏ precondition

Với `[3,1,2]`, không tồn tại tính thứ tự cho phép kết luận từ phần tử ở giữa về toàn bộ nửa mảng. Binary search có thể loại sai nửa chứa đáp án, và invariant không còn được duy trì. Nếu input không tin cậy, wrapper kiểm tra từng cặp kề rồi ném `IllegalArgumentException` khi gặp cặp giảm.

**Độ phức tạp:** Fast API `O(log(n+1))` thời gian và `O(1)` memory; Checked API `O(n)` tổng thời gian vì xác thực sortedness là O(n). Không được quảng cáo cả hai là O(log n).

## 5. Ví dụ 2: cửa sổ trượt cần dữ liệu không âm

Bài toán: tìm độ dài nhỏ nhất **của một đoạn con liên tiếp không rỗng** có tổng ≥ target. Phiên bản này yêu cầu:

```text
data != null.
target > 0.
Mọi data[i] >= 0.
Mọi tổng trung gian tính bằng long phải nằm trong miền long.
```

Nếu không có đoạn thỏa, hàm trả **0**. Nếu target=0, bài toán có thể cho phép đoạn rỗng hay yêu cầu đoạn không rỗng; thay vì đoán, phiên bản mẫu **từ chối ngưỡng không dương**. Nếu có số âm, thuật toán hai con trỏ này **từ chối**; muốn xử lý tổng quát cần thuật toán khác như prefix sums kết hợp deque đơn điệu.

### 5.1. Bất biến của hai con trỏ

Khi đã thêm phần tử `data[end]`, tổng `sum` mô tả đoạn `[start,end]` nếu không rỗng. Khi `sum>=target`, ghi nhận độ dài rồi bỏ phần tử ở `start` và tăng start. **Vì mọi phần tử không âm**, việc bỏ bên trái không thể làm tổng tăng. Khi vòng thu hẹp kết thúc:

```text
sum < target.
Các ứng viên có đầu trái trước start và đã đạt ngưỡng
đều được ghi nhận khi chúng còn là một cửa sổ hợp lệ.
```

Một con trỏ chỉ tăng, không quay lại; mỗi index được thêm nhiều nhất một lần và bị loại khỏi cửa sổ nhiều nhất một lần. Thời gian O(n), bộ nhớ O(1), cộng một lượt kiểm tra dấu cũng O(n).

Ví dụ `[2,3,1,2,4,3]`, target=7, đáp án là 2 từ cửa sổ `[4,3]`.

### 5.2. Tại sao số âm làm hỏng chứng minh?

Với `data=[1,-1,5]`, target=5, đáp án thật là đoạn `[5]` dài 1. Thuật toán cửa sổ vốn dựa trên các số không âm có thể tăng right tới tổng 5 của cả ba phần tử, ghi độ dài 3, rồi bỏ số 1 làm tổng 4 và dừng thu hẹp. Nó bỏ lỡ đoạn `[5]`, vì **bỏ phần tử âm** ở đầu có thể làm tổng tăng, trái giả thiết đơn điệu.

Do đó phần tài liệu phải ghi rõ nonnegative, thay vì chỉ nêu “sliding window O(n) cho mọi mảng”.

### 5.3. Giới hạn số học cũng thuộc hợp đồng

Mã dùng:

```java
sum = Math.addExact(sum, data[end]);
```

và `Math.subtractExact` để tránh overflow bị che giấu. Với `data=[Long.MAX_VALUE-1,2]`, `target=Long.MAX_VALUE`, phép cộng ở phần tử thứ hai vượt long, hàm **ném `ArithmeticException`**. Điều này không có nghĩa bài toán không có nghiệm; nghĩa là triển khai đã **chạm giới hạn biểu diễn** mà README cam kết sẽ phát hiện. Nếu bài toán cần nhận tổng vượt long, phải dùng `BigInteger` hoặc một biểu diễn có chứng minh đúng khác.

## 6. Ví dụ 3: Dijkstra cần trọng số không âm và INF hợp lệ

Bài toán: đồ thị **có hướng** biểu diễn bằng danh sách kề, mọi trọng số cạnh không âm. Tìm khoảng cách ngắn nhất từ nguồn tới mỗi đỉnh.

### 6.1. Tiền điều kiện

```text
graph != null; n=graph.size()>0.
source in [0,n).
Mọi adjacency list và Edge khác null.
Mọi Edge.to in [0,n).
Mọi Edge.weight >= 0 và < INF.
Mọi phép relaxation được xử lý thành công tạo candidate < INF.
```

Trong implementation:

```java
static final long INF = Long.MAX_VALUE/4;
```

`INF` có nghĩa **unreachable**, không phải khoảng cách thật. Mọi khoảng cách hữu hạn trong kết quả phải nằm ở `[0,INF)`. Nếu một candidate được xét đạt/vượt INF, code **fail-fast** bằng `ArithmeticException` thay vì trả khoảng cách giả. Giới hạn này hẹp hơn lý thuyết Dijkstra trên số nguyên toán học không giới hạn.

### 6.2. Bất biến

- Mọi nhãn `dist[v]` hữu hạn bằng độ dài một đường đi từ nguồn tới v đã tìm được.
- Khi lấy một entry hiện hành có nhãn nhỏ nhất ra khỏi priority queue, trọng số không âm đảm bảo khoảng cách của đỉnh này là tối ưu.
- Entry cũ khác `dist[v]` được bỏ qua.
- Không tạo phép cộng với giá trị INF như số hữu hạn; không cho candidate đạt INF.
- Các đỉnh không thể tới từ nguồn giữ nhãn INF.

**Phác thảo chứng minh:** Nếu đỉnh u được lấy ra với nhãn nhỏ nhất nhưng tồn tại đường ngắn hơn, xét đỉnh đầu tiên chưa được chốt trên đường ngắn hơn. Tiền tố dẫn đến nó qua một đỉnh đã được chốt sẽ được relaxation và do trọng số không âm tạo nhãn không lớn hơn độ dài tiền tố, mâu thuẫn với cách chọn u là nhỏ nhất. Vì vậy u có khoảng cách tối ưu.

### 6.3. Ví dụ, INF và điều kiện lỗi

Đồ thị:

```text
0 -> 1 (8)
0 -> 2 (1)
2 -> 1 (2)
1 -> 3 (1)
2 -> 3 (10)
đỉnh 4 không thể tới từ 0
```

Kết quả:

```text
[0, 3, 1, 4, INF]
```

Cạnh âm `-1` bị từ chối; không chỉ cảnh báo. Nếu đường ứng viên có `dist=INF-1`, `weight=1` thì tổng bằng INF bị từ chối vì nó trùng sentinel dành riêng.

**Giới hạn bổ sung:** Chương trình từ chối **mọi candidate được xử lý** mà tổng đạt/vượt INF, kể cả nếu đích đã có đường khác ngắn hơn. Đó là fail-fast theo hợp đồng, không phải điều kiện toán học bắt buộc. Muốn hỗ trợ mọi trọng số long không âm và mọi tổng lớn, có thể dùng `BigInteger` và trạng thái reachable riêng.

**Độ phức tạp:** Với V đỉnh, E cạnh, kiểm tra graph là O(V+E). Heap lazy insert có thể chứa O(E) entries, nên cận tổng quát `O((V+E)log(V+E))` thời gian, `O(V+E)` bộ nhớ phụ trong mô hình thao tác số nguyên O(1). Trên đồ thị đơn, thường rút cận thành `O((V+E)log V)`. Không dùng comparator trừ hai long vì có thể tràn; dùng `Comparator.comparingLong`.

## 7. Nhận diện giới hạn sử dụng theo bốn miền

### 7.1. Miền tính đúng

Một tiền đề toán học bị vi phạm thường làm hỏng chứng minh:

- Binary search cần sorted input.
- Sliding window tổng ngưỡng dùng hai con trỏ cần tính đơn điệu; phần tử không âm là tiền đề đủ cho phiên bản này.
- Dijkstra cần trọng số không âm.
- Topological order chỉ tồn tại nếu đồ thị DAG; có chu trình cần báo không có thứ tự đầy đủ.
- Một heuristic A* chỉ có các bảo đảm optimality tương ứng khi nó thỏa những điều kiện thuật toán yêu cầu.
- Một thuật toán tham lam phải dựa trên tính chất lựa chọn tham lam đã chứng minh, không thể chỉ “trông hợp lý trên ví dụ”.

### 7.2. Miền tài nguyên

Một thuật toán vẫn đúng nhưng không phù hợp khi `O(n²)` quá chậm, recursion quá sâu làm tràn call stack, hoặc cấu trúc O(n) không vừa RAM. External-memory algorithms phải xét chi phí I/O theo khối, không chỉ CPU. Thuật toán song song phải xét thêm task creation, synchronization và data movement; tăng worker không tự tạo speedup tuyến tính.

Lời hứa “hỗ trợ 10 triệu bản ghi” cần dựa trên kiểu dữ liệu, byte/record, bộ nhớ thực, thời gian và benchmark đại diện, không chỉ suy từ Big-O.

### 7.3. Miền số học và biểu diễn

- Phép `int*int` tràn **trước** khi gán kết quả sang long nếu không ép một toán hạng từ đầu.
- Cộng khoảng cách với INF không hợp lý vì INF là trạng thái, không phải số.
- Kết quả modulo không phải số đếm chính xác.
- `double` có sai số, NaN và Infinity; không biểu diễn chính xác mọi số nguyên 64 bit.
- Sentinel `-1`, `0` hoặc `INF` phải không lẫn với giá trị đáp án hợp lệ.
- Nếu output có thể vượt long, dùng BigInteger hoặc ghi rõ giới hạn và throw.

### 7.4. Miền cập nhật và dữ liệu chia sẻ

Các hợp đồng thường bỏ sót: hàm có thay đổi input không, input có bị thay bởi thread khác trong lúc chạy không, dữ liệu có thể có duplicates/self-loops/multiple edges/null không, output có bảo toàn thứ tự và bag semantics không. Với nhiều thread, phải nêu điều kiện publication/happens-before hoặc dùng immutable input; một thuật toán đúng trong single-thread không tự động đúng khi có data race.

## 8. Kiểm thử từ hợp đồng, thay vì chỉ chạy ví dụ thuận lợi

Mỗi precondition/hậu điều kiện phải gợi được ít nhất một test:

| Điều kiện | Test đúng hợp đồng | Test sai/cận biên |
| --- | --- | --- |
| Mảng sorted | Rỗng, một phần tử, tất cả trùng | `[3,1,2]` |
| Lower bound | Khóa nhỏ hơn min / lớn hơn max | Trả index n |
| Window nonnegative | Có zero, target nhỏ/lớn | `[1,-1,5]` |
| Window target>0 | target=1, mảng rỗng | target=0 |
| Window long sum | Giá trị vừa long | `[MAX-1,2]` với target=MAX |
| Dijkstra nonnegative | Cạnh 0, nhiều đường, rời rạc | Cạnh âm |
| INF distinct | Khoảng cách nhỏ hơn INF | candidate bằng INF |
| Output exact | Kết quả theo oracle | Phản ví dụ off-by-one |

**Oracle độc lập:** Tìm kiếm nhị phân được so với **quét tuyến tính**. Sliding window được so với **liệt kê tất cả đoạn con O(n²)** trên input nhỏ. Dijkstra được so với **Bellman–Ford dùng BigInteger**. Không gọi lại cùng thuật toán tối ưu để tạo “kết quả kỳ vọng”, vì có thể cả hai cùng chứa cùng một lỗi.

**Random có seed:** Sinh đầu vào nhỏ theo miền precondition, lưu seed và kiểm tra tính tái lập. 800 test binary, 600 test window và 400 đồ thị chỉ bao phủ những trường hợp đã sinh, **không phải bằng chứng rằng mọi input trong miền đều đã được kiểm chứng**.

**Test invalid input:** Kiểm tra exception được dự định xuất hiện thay vì chỉ nhìn xem mã có bị crash hay không. Nếu lời gọi phải từ chối cạnh âm, test nên xác nhận đúng loại exception. Nếu bài toán không có đáp án, test nên kiểm tra sentinel/status hợp lệ, không coi nó là exception.

## 9. Java 17+ độc lập: hợp đồng được thể hiện ngay trong code

Tệp `SolutionContractsDemo.java` dùng chuẩn Java 17, không cần thư viện ngoài. `lowerBoundAssumingSorted` đặt tiền điều kiện trong comment; `checkedLowerBound` minh họa trade-off validation/time. `minimumWindowAtLeast` có guard target/giá trị âm và arithmetic exact. `dijkstra` có guard chỉ số/trọng số/INF. Oracle `linearLowerBound`, `bruteWindow`, `bellmanFordOracle` cố ý dùng **cách tính khác** với phương pháp được kiểm thử.

### 9.1. Mã đầy đủ

```java
import java.math.BigInteger;
import java.util.*;

public class SolutionContractsDemo {
    static final long INF = Long.MAX_VALUE / 4;

    record Edge(int to, long weight) {}
    record State(int vertex, long distance) {}

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static boolean failsAs(
            Class<? extends Throwable> expected, Runnable action) {
        try {
            action.run();
            return false;
        } catch (Throwable error) {
            if (expected.isInstance(error)) return true;
            throw new AssertionError("Unexpected failure: " + error);
        }
    }

    // PRE: array != null and sorted nondecreasing.
    // POST: first index i with array[i] >= target, or n.
    // Loop invariant: [0,lo) < target; [hi,n) >= target.
    // TIME: O(log(n+1)); does not verify the sortedness promise.
    static int lowerBoundAssumingSorted(int[] array, int target) {
        Objects.requireNonNull(array, "array");
        int lo = 0, hi = array.length;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (array[mid] < target) lo = mid + 1;
            else hi = mid;
        }
        return lo;
    }

    // Explicit input validation costs O(n), not O(log n).
    static int checkedLowerBound(int[] array, int target) {
        Objects.requireNonNull(array, "array");
        for (int i = 1; i < array.length; i++) {
            if (array[i-1] > array[i]) {
                throw new IllegalArgumentException(
                        "Binary search requires sorted input");
            }
        }
        return lowerBoundAssumingSorted(array, target);
    }

    // PRE: target>0; data!=null; every element >=0.
    // POST: minimum NONEMPTY window length with sum>=target,
    // or 0 when no such window exists.
    // Throws if any intermediate sum is outside long.
    // TIME O(n) because both pointers only move right.
    static int minimumWindowAtLeast(long[] data, long target) {
        Objects.requireNonNull(data, "data");
        if (target <= 0) {
            throw new IllegalArgumentException("target must be positive");
        }
        for (long value : data) {
            if (value < 0) {
                throw new IllegalArgumentException(
                        "Sliding window requires nonnegative elements");
            }
        }
        long sum = 0;
        int start = 0, best = data.length + 1;
        for (int end = 0; end < data.length; end++) {
            sum = Math.addExact(sum, data[end]);
            while (sum >= target) {
                best = Math.min(best, end - start + 1);
                sum = Math.subtractExact(sum, data[start++]);
            }
        }
        return best == data.length + 1 ? 0 : best;
    }

    // PRE: graph is directed, non-null, all weights nonnegative
    // and < INF. Every visited candidate must remain < INF.
    // POST: exact shortest nonnegative distances; INF for
    // unreachable vertices. Throws instead of concealing
    // a path candidate that crosses the reserved INF range.
    static long[] dijkstra(List<List<Edge>> graph, int source) {
        Objects.requireNonNull(graph, "graph");
        int n = graph.size();
        if (n == 0 || source < 0 || source >= n) {
            throw new IllegalArgumentException("invalid source/graph");
        }
        for (List<Edge> edges : graph) {
            if (edges == null) {
                throw new IllegalArgumentException("null adjacency");
            }
            for (Edge edge : edges) {
                if (edge == null || edge.to() < 0 || edge.to() >= n
                        || edge.weight() < 0 || edge.weight() >= INF) {
                    throw new IllegalArgumentException(
                            "Dijkstra needs valid nonnegative weights");
                }
            }
        }
        long[] distance = new long[n];
        Arrays.fill(distance, INF);
        distance[source] = 0;
        PriorityQueue<State> queue = new PriorityQueue<>(
                Comparator.comparingLong(State::distance));
        queue.add(new State(source, 0));
        while (!queue.isEmpty()) {
            State current = queue.remove();
            if (current.distance() != distance[current.vertex()]) continue;
            for (Edge edge : graph.get(current.vertex())) {
                if (edge.weight() >= INF - current.distance()) {
                    throw new ArithmeticException(
                            "path candidate outside finite distance range");
                }
                long candidate = current.distance() + edge.weight();
                if (candidate < distance[edge.to()]) {
                    distance[edge.to()] = candidate;
                    queue.add(new State(edge.to(), candidate));
                }
            }
        }
        return distance;
    }

    static List<List<Edge>> graph(int vertices) {
        List<List<Edge>> result = new ArrayList<>();
        for (int i = 0; i < vertices; i++) {
            result.add(new ArrayList<>());
        }
        return result;
    }

    static void edge(List<List<Edge>> graph,
                     int from, int to, long weight) {
        graph.get(from).add(new Edge(to, weight));
    }

    static int linearLowerBound(int[] sorted, int target) {
        for (int i = 0; i < sorted.length; i++) {
            if (sorted[i] >= target) return i;
        }
        return sorted.length;
    }

    // Oracle O(n^2), independent of the sliding-window method.
    static int bruteWindow(long[] data, long target) {
        int answer = data.length + 1;
        for (int left = 0; left < data.length; left++) {
            long sum = 0;
            for (int right = left; right < data.length; right++) {
                sum = Math.addExact(sum, data[right]);
                if (sum >= target) {
                    answer = Math.min(answer, right - left + 1);
                }
            }
        }
        return answer == data.length + 1 ? 0 : answer;
    }

    // Independent exact Bellman-Ford oracle, null = unreachable.
    static BigInteger[] bellmanFordOracle(
            List<List<Edge>> graph, int source) {
        int n = graph.size();
        BigInteger[] distance = new BigInteger[n];
        distance[source] = BigInteger.ZERO;
        for (int pass = 0; pass < n - 1; pass++) {
            boolean changed = false;
            for (int from = 0; from < n; from++) {
                if (distance[from] == null) continue;
                for (Edge e : graph.get(from)) {
                    BigInteger candidate = distance[from].add(
                            BigInteger.valueOf(e.weight()));
                    if (distance[e.to()] == null
                            || candidate.compareTo(distance[e.to()]) < 0) {
                        distance[e.to()] = candidate;
                        changed = true;
                    }
                }
            }
            if (!changed) break;
        }
        return distance;
    }

    static String printDistances(long[] distance) {
        List<String> out = new ArrayList<>();
        for (long d : distance) {
            out.add(d == INF ? "INF" : Long.toString(d));
        }
        return out.toString();
    }

    static void examples() {
        int[] sorted = {1, 2, 2, 2, 5};
        check(lowerBoundAssumingSorted(sorted, 2) == 1,
                "lower bound for duplicate keys");
        check(checkedLowerBound(sorted, 3) == 4,
                "lower bound for insertion point");
        System.out.println("Lower bound: x=2 -> 1, x=3 -> 4");

        boolean unsortedRejected = failsAs(IllegalArgumentException.class,
                () -> checkedLowerBound(new int[] {3, 1, 2}, 2));
        check(unsortedRejected, "Unsorted input must be rejected");
        System.out.println("Checked binary search rejects unsorted: "
                + unsortedRejected);

        long[] window = {2, 3, 1, 2, 4, 3};
        int minimum = minimumWindowAtLeast(window, 7);
        check(minimum == 2, "Window example is wrong");
        System.out.println(
                "Nonnegative window: target=7 -> minLength=" + minimum);

        boolean negativeRejected = failsAs(
                IllegalArgumentException.class,
                () -> minimumWindowAtLeast(
                        new long[] {1, -1, 5}, 5));
        check(negativeRejected, "Negative element must fail");
        System.out.println("Negative window input rejected: "
                + negativeRejected);

        boolean overflowRejected = failsAs(ArithmeticException.class,
                () -> minimumWindowAtLeast(
                        new long[] {Long.MAX_VALUE - 1, 2},
                        Long.MAX_VALUE));
        check(overflowRejected, "Overflow must be explicit");
        System.out.println("Window sum overflow rejected: "
                + overflowRejected);

        List<List<Edge>> g = graph(5);
        edge(g, 0, 1, 8);
        edge(g, 0, 2, 1);
        edge(g, 2, 1, 2);
        edge(g, 1, 3, 1);
        edge(g, 2, 3, 10);
        long[] result = dijkstra(g, 0);
        check(Arrays.equals(result, new long[] {0, 3, 1, 4, INF}),
                "Dijkstra sample result");
        System.out.println("Dijkstra: "
                + printDistances(result));

        List<List<Edge>> invalid = graph(2);
        edge(invalid, 0, 1, -1);
        boolean negativeEdgeRejected = failsAs(
                IllegalArgumentException.class,
                () -> dijkstra(invalid, 0));
        check(negativeEdgeRejected, "Negative edge must fail");
        System.out.println("Negative Dijkstra edge rejected: "
                + negativeEdgeRejected);

        List<List<Edge>> tooLarge = graph(3);
        edge(tooLarge, 0, 1, INF - 1);
        edge(tooLarge, 1, 2, 1);
        boolean largeDistanceRejected = failsAs(
                ArithmeticException.class,
                () -> dijkstra(tooLarge, 0));
        check(largeDistanceRejected, "Reserved INF must fail");
        System.out.println("Reserved INF distance rejected: "
                + largeDistanceRejected);

        boolean invalidTargetRejected = failsAs(
                IllegalArgumentException.class,
                () -> minimumWindowAtLeast(new long[] {1}, 0));
        check(invalidTargetRejected, "target<=0 must fail");
        System.out.println("Nonpositive target rejected: "
                + invalidTargetRejected);
    }

    static void randomOracles() {
        SplittableRandom random = new SplittableRandom(5482026L);
        for (int trial = 0; trial < 800; trial++) {
            int n = random.nextInt(0, 101);
            int[] values = new int[n];
            for (int i = 0; i < n; i++) {
                values[i] = random.nextInt(-25, 26);
            }
            Arrays.sort(values);
            int target = random.nextInt(-30, 31);
            int oracle = linearLowerBound(values, target);
            check(lowerBoundAssumingSorted(values, target) == oracle,
                    "Binary search differs from linear oracle");
            check(checkedLowerBound(values, target) == oracle,
                    "Checked binary search differs from oracle");
        }
        for (int trial = 0; trial < 600; trial++) {
            int n = random.nextInt(0, 41);
            long[] values = new long[n];
            for (int i = 0; i < n; i++) {
                values[i] = random.nextInt(0, 21);
            }
            long target = random.nextInt(1, 151);
            check(minimumWindowAtLeast(values, target)
                    == bruteWindow(values, target),
                    "Sliding window differs from quadratic oracle");
        }
        for (int trial = 0; trial < 400; trial++) {
            int n = random.nextInt(1, 10);
            List<List<Edge>> g = graph(n);
            for (int from = 0; from < n; from++) {
                for (int to = 0; to < n; to++) {
                    if (from != to && random.nextInt(4) == 0) {
                        edge(g, from, to, random.nextInt(0, 51));
                    }
                }
            }
            int source = random.nextInt(n);
            long[] actual = dijkstra(g, source);
            BigInteger[] expected = bellmanFordOracle(g, source);
            for (int i = 0; i < n; i++) {
                long oracle = expected[i] == null
                        ? INF : expected[i].longValueExact();
                check(actual[i] == oracle,
                        "Dijkstra differs from Bellman-Ford oracle");
            }
        }
        System.out.println(
                "Random oracle QA: PASS (800 binary searches, "
                + "600 sliding windows, 400 graphs)");
    }

    public static void main(String[] args) {
        examples();
        randomOracles();
    }
}
```

### 9.2. Cách chạy

Lưu mã vào `SolutionContractsDemo.java` và chạy:

```bash
javac SolutionContractsDemo.java
java SolutionContractsDemo
```

**Stdout chính xác với seed trong mã:**

```text
Lower bound: x=2 -> 1, x=3 -> 4
Checked binary search rejects unsorted: true
Nonnegative window: target=7 -> minLength=2
Negative window input rejected: true
Window sum overflow rejected: true
Dijkstra: [0, 3, 1, 4, INF]
Negative Dijkstra edge rejected: true
Reserved INF distance rejected: true
Nonpositive target rejected: true
Random oracle QA: PASS (800 binary searches, 600 sliding windows, 400 graphs)
```

### 9.3. Giải thích output

1. Lower bound của 2 trong `[1,2,2,2,5]` là 1, không phải vị trí số 2 bất kỳ. Lower bound của 3 là 4 vì giá trị tại index 4 là 5.
2. Wrapper từ chối `[3,1,2]` bằng exception, không lặng lẽ chạy fast search.
3. Window với target 7 cho độ dài tối thiểu 2, từ `[4,3]`.
4. `[1,-1,5]` bị từ chối vì phần tử âm phá precondition nonnegative.
5. `[Long.MAX_VALUE-1,2]` không được phép wrap; `Math.addExact` phát hiện overflow.
6. Dijkstra trả `[0,3,1,4,INF]`; đỉnh cuối không có đường đi.
7. Dijkstra từ chối cạnh âm thay vì trả đường đi không được chứng minh đúng.
8. Candidate đạt đúng INF bị từ chối để không nhầm với unreachable.
9. Target 0 bị từ chối vì miền target của thuật toán là dương.
10. Random QA đã so **800 dãy**, **600 cửa sổ** và **400 đồ thị** với oracle độc lập.

### 9.4. Độ phức tạp thực của mã

| Phương thức | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| `lowerBoundAssumingSorted` | O(log(n+1)) | O(1) |
| `checkedLowerBound` | O(n) gồm validation | O(1) |
| `minimumWindowAtLeast` | O(n) | O(1) |
| `dijkstra` | O((V+E)log(V+E)) | O(V+E) |
| `linearLowerBound` oracle | O(n) | O(1) |
| `bruteWindow` oracle | O(n²) | O(1) |
| `bellmanFordOracle` | O(VE) lần relaxation, cộng chi phí số lớn | O(V) ngoài graph |

BigInteger trong oracle có chi phí phụ thuộc độ dài bit, không phải mọi phép cộng đều có chi phí O(1) trên số nguyên tùy ý dài. Các cận trên mô tả **đường chạy hợp lệ**, không tính một phép gọi thất bại ngay ở validation.

## 10. Thực hành chứng minh vòng lặp và điều kiện dừng

**Binary search:** Ranking function `hi-lo` không âm và giảm khi `lo<hi`; invariant phân hoạch hai miền đã xác định, khi lo==hi suy ra index đầu tiên ≥ target.

**Sliding window:** `end` chỉ tăng; `start` chỉ tăng. Dù `sum` không giảm trên toàn vòng, mỗi phần tử được thêm và bỏ nhiều nhất một lần. Định lý dấu không âm bảo đảm bỏ bên trái không thể tăng tổng; khi `sum<target` cần mở thêm bên phải mới có thể đạt ngưỡng.

**Dijkstra:** Mỗi lần lấy entry hiện hành nhỏ nhất, nhãn của đỉnh được xác định tối ưu nhờ trọng số không âm; relax không tạo nhãn giả khi số học chính xác. Với số đỉnh/cạnh hữu hạn, số entry/relaxation hữu hạn và queue cạn. Khi bỏ tiền điều kiện cạnh không âm hoặc cho overflow làm khoảng cách âm, lập luận không còn áp dụng.

**Bất biến và mã phải thống nhất:** Nếu README viết cửa sổ `[start,end)` nhưng code cập nhật `data[end]` rồi xử lý `[start,end]` bao gồm end, chứng minh có lỗi ranh giới. Hãy nêu rõ 0-based indices, đoạn đóng/nửa mở và ý nghĩa của sentinel.

## 11. Vì sao cần ghi rõ hành vi lỗi

Không có một chính sách duy nhất cho mọi API:

- **Fail-fast** bằng exception phù hợp với input vi phạm hợp đồng không thể sửa âm thầm.
- **Validate and normalize** phù hợp khi dữ liệu đầu vào có thể chuyển về dạng hợp lệ mà không đổi ngữ nghĩa.
- **Fallback** sang thuật toán tổng quát hơn là lựa chọn tốt khi yêu cầu mở rộng miền; complexity và test phải được cập nhật.
- **Caller responsibility** hợp lý cho một primitive tối ưu chỉ được gọi sau validation ở tầng khác, nhưng phải ghi rõ.

Ví dụ lower bound không thể tự phát hiện unsorted mà vẫn luôn giữ O(log n), vì phát hiện tính sorted toàn cục trong trường hợp tổng quát cần quét nhiều phần tử. Ví dụ sliding window nếu muốn hỗ trợ số âm thực sự thì không chỉ bỏ guard mà phải dùng thuật toán tổng quát khác. Dijkstra nếu muốn hỗ trợ cạnh âm thì cần thay thuật toán, không chỉ tăng `INF`.

## 12. Những lỗi thường gặp khi viết assumptions, invariants, limits

1. Tuyên bố “đúng cho mọi input” nhưng không nêu miền.
2. Chỉ nêu ý tưởng chung mà thiếu định nghĩa output.
3. Nhầm precondition với invariant.
4. Nhầm invariant với postcondition.
5. Bất biến quá yếu không suy ra kết quả.
6. Quên chứng minh khởi tạo bất biến.
7. Quên chứng minh bất biến được duy trì qua từng nhánh.
8. Không tìm ranking function để chứng minh dừng.
9. Dùng chỉ số nửa mở/đóng lẫn lộn.
10. Nhầm lower bound với tìm kiếm bằng target.
11. Bỏ trường hợp không có phần tử thỏa.
12. Bỏ trường hợp mảng rỗng hoặc có khóa trùng.
13. Ghi fast binary search O(log n) nhưng tự xác thực sortedness O(n).
14. Coi test chạy đúng nghĩa sortedness đã được kiểm chứng.
15. Áp sliding window hai con trỏ lên mảng có số âm.
16. Quên target>0 và đoạn con không rỗng.
17. Dùng 0 đồng thời là độ dài hợp lệ và trạng thái không đáp án mà không định nghĩa.
18. Không kiểm tra overflow của tổng trung gian.
19. Ép int sang long sau khi phép nhân int đã overflow.
20. Dùng INF như khoảng cách hữu hạn có thể cộng tùy ý.
21. Cho phép đường hữu hạn bằng INF rồi đánh dấu unreachable.
22. Dùng Dijkstra với cạnh âm.
23. Không xác thực vertex IDs và null adjacency.
24. Không bỏ stale priority queue entries theo triển khai lazy.
25. Comparator trừ hai long gây overflow.
26. Nhầm directed graph với undirected graph.
27. Bỏ đỉnh cô lập khi test shortest path.
28. Không ghi giới hạn thời gian/heap.
29. Không tính recursion stack của DFS/DP.
30. Không tính validation vào complexity.
31. Dùng cùng thuật toán để xây oracle.
32. Chỉ test happy path mà không test input sai.
33. Nuốt exception và thay bằng giá trị giả.
34. Coi 1000 random tests là chứng minh toán học.
35. Không ghi seed để tái lập test random.
36. Chạy oracle O(n²) trên input sản xuất khổng lồ.
37. Không phân biệt resource limit với correctness limit.
38. Không ghi liệu hàm mutate input.
39. Bỏ giả thiết concurrent modification.
40. Không nêu hành vi khi NaN/Infinity trong thuật toán số thực.
41. Dùng assert có thể bị tắt thay vì validate public input.
42. Bỏ tiền điều kiện khi copy code sang bài khác.
43. Ghi “giới hạn dữ liệu lớn” quá mơ hồ, không có con số/mô hình.
44. Không xác định n, V, E trong cận Big-O.
45. Không phân biệt kết quả đúng theo dữ liệu logic và kết quả được kiểm thử trên mẫu.
46. Không phân biệt lỗi caller và lỗi implementation.
47. Không ghi rõ output tie-breaking/duplicates.
48. Gọi wrapper checked là O(log n) dù có quét input.
49. Tự động sửa input bằng sort mà không nói nó thay đổi bài toán và chi phí.
50. Tuyên bố xử lý dữ liệu file lớn trong khi mã dùng array nằm trong RAM.

## 13. Bài tập tự luyện kèm đáp án

**Bài 1.** Precondition là gì?

**Đáp án:** Điều phải đúng ở đầu lời gọi để lời cam kết tính đúng của thuật toán áp dụng.

**Bài 2.** Invariant là gì?

**Đáp án:** Một mệnh đề trạng thái được bảo toàn tại những ranh giới lặp/trạng thái xác định.

**Bài 3.** Postcondition là gì?

**Đáp án:** Điều được bảo đảm về kết quả/trạng thái khi hàm kết thúc thành công.

**Bài 4.** Tại sao cần ranking function?

**Đáp án:** Để chứng minh thuật toán kết thúc, thường dùng đại lượng nguyên không âm giảm nghiêm ngặt.

**Bài 5.** Binary search lower bound cần precondition nào?

**Đáp án:** Mảng sorted không giảm theo comparator phù hợp.

**Bài 6.** Lower bound của 2 trong `[1,2,2,2,5]`?

**Đáp án:** 1.

**Bài 7.** Lower bound của 3 trong mảng đó?

**Đáp án:** 4.

**Bài 8.** Lower bound của 7 trong mảng đó?

**Đáp án:** 5, bằng n.

**Bài 9.** Lower bound trên mảng rỗng trả gì?

**Đáp án:** 0.

**Bài 10.** Viết invariant binary search lower bound.

**Đáp án:** `0<=lo<=hi<=n`; mọi phần tử trước lo nhỏ hơn target; mọi phần tử từ hi trở đi lớn hơn hoặc bằng target.

**Bài 11.** Fast search khi caller đã bảo đảm sortedness có complexity nào?

**Đáp án:** `O(log(n+1))` thời gian, `O(1)` bộ nhớ phụ.

**Bài 12.** Thêm validation sortedness làm complexity thành gì?

**Đáp án:** `O(n)` tổng thời gian.

**Bài 13.** Vì sao `[3,1,2]` không hợp lệ cho fast binary search?

**Đáp án:** Nó không sorted; không thể loại nửa khoảng dựa trên giá trị giữa.

**Bài 14.** Sliding window trong bài yêu cầu tính chất gì?

**Đáp án:** Mọi phần tử không âm, target>0, phép cộng trung gian vừa long.

**Bài 15.** Dãy `[2,3,1,2,4,3]`, target 7 có đáp án nào?

**Đáp án:** Độ dài 2, đoạn `[4,3]`.

**Bài 16.** `[1,-1,5]`, target 5 có đáp án toán học gì?

**Đáp án:** 1, đoạn `[5]`; song hàm mẫu từ chối vì có số âm.

**Bài 17.** Vì sao số âm phá sliding window hai con trỏ này?

**Đáp án:** Bỏ phần tử âm có thể làm tổng tăng; mất tính đơn điệu của thao tác thu hẹp.

**Bài 18.** Nếu mảng rỗng, target 7, hàm mẫu trả gì?

**Đáp án:** 0 vì không có cửa sổ không rỗng thỏa.

**Bài 19.** Nếu target=0?

**Đáp án:** `IllegalArgumentException`, vì hợp đồng yêu cầu target dương.

**Bài 20.** Vì sao dùng `Math.addExact`?

**Đáp án:** Để phát hiện overflow thay vì âm thầm wrap và trả kết quả sai.

**Bài 21.** Dãy `[Long.MAX_VALUE-1,2]` với target MAX gây điều gì?

**Đáp án:** `ArithmeticException` khi phép cộng vượt long.

**Bài 22.** Dijkstra cần cạnh có trọng số dấu nào?

**Đáp án:** Không âm; trọng số 0 được phép.

**Bài 23.** `INF=Long.MAX_VALUE/4` có nghĩa gì trong code?

**Đáp án:** Sentinel dành riêng cho đỉnh không thể tới, không phải khoảng cách hữu hạn.

**Bài 24.** Candidate đúng bằng INF được xử lý ra sao?

**Đáp án:** Throw `ArithmeticException` theo giới hạn biểu diễn của demo.

**Bài 25.** Dijkstra sample từ nguồn 0 có kết quả gì?

**Đáp án:** `[0,3,1,4,INF]`.

**Bài 26.** Vì sao không dùng comparator bằng phép trừ long?

**Đáp án:** Có thể overflow và sai thứ tự; dùng `Long.compare`/`comparingLong`.

**Bài 27.** Oracle độc lập đơn giản cho lower bound?

**Đáp án:** Quét tuyến tính tìm phần tử đầu tiên >=target.

**Bài 28.** Oracle cho shortest qualifying window trên input nhỏ?

**Đáp án:** Liệt kê tất cả đoạn con O(n²), chọn độ dài nhỏ nhất.

**Bài 29.** Oracle cho Dijkstra mẫu?

**Đáp án:** Bellman–Ford với `BigInteger` trên đồ thị nhỏ.

**Bài 30.** Random test PASS có chứng minh mọi trường hợp đúng không?

**Đáp án:** Không; chỉ xác nhận các case đã chạy, còn cần invariant/chứng minh.

**Bài 31.** Khi nào cần test input vi phạm precondition?

**Đáp án:** Khi code hứa validate/throw hoặc fallback, để xác nhận không im lặng trả sai.

**Bài 32.** Nếu một thuật toán đúng nhưng O(n²) quá chậm với n lớn?

**Đáp án:** Đó là giới hạn tài nguyên chứ không tự biến thuật toán thành sai toán học.

**Bài 33.** Nếu bài mới cho phép số âm trong sliding window, có nên bỏ guard không?

**Đáp án:** Không; phải chọn thuật toán tổng quát hơn và chứng minh lại.

**Bài 34.** Nêu bốn mục luôn phải có trong mô tả giải pháp.

**Đáp án:** Precondition, invariant/correctness, postcondition và limitation/complexity; nên thêm failure behavior và test evidence.

**Bài 35.** Vì sao không ghi wrapper checked là O(log n)?

**Đáp án:** Nó quét toàn mảng O(n) trước khi tìm kiếm O(log n), nên tổng là O(n).

**Bài 36.** Khi nào assert không thay thế được input validation?

**Đáp án:** Khi assertion có thể tắt hoặc không bảo đảm phát hiện mọi input sai tại trust boundary.

**Bài 37.** Đỉnh unreachable trong Dijkstra có được cộng trọng số như số thường không?

**Đáp án:** Không; INF biểu thị trạng thái, không phải độ dài đường đi.

**Bài 38.** Nếu đồ thị có cạnh âm, điều kiện nào phải đổi?

**Đáp án:** Chọn thuật toán khác phù hợp như Bellman–Ford, sửa hợp đồng và complexity.

**Bài 39.** Khi copy code sang dự án khác, cần kiểm tra gì?

**Đáp án:** Miền input, output/sentinel, số học, giới hạn tài nguyên, concurrency và oracle trên workload mới.

**Bài 40.** Vì sao hợp đồng giúp giảm lỗi tích hợp?

**Đáp án:** Nó phân biệt dữ liệu sai, lỗi thuật toán và giới hạn tài nguyên, đồng thời quy định rõ cách caller diễn giải kết quả/lỗi.

## 14. Checklist bàn giao lời giải

- [ ] Định nghĩa bài toán, input/output và chỉ số rõ?
- [ ] Miền dấu, null, rỗng, trùng nhau và kích thước hợp lệ?
- [ ] Precondition toán học đã ghi và xác thực/caller cam kết rõ?
- [ ] Invariant đủ mạnh và đúng ở từng nhánh cập nhật?
- [ ] Ranking function chứng minh kết thúc?
- [ ] Hậu điều kiện mô tả đầy đủ cả không có đáp án?
- [ ] Số học trung gian tránh overflow/sentinel collision?
- [ ] Complexity gồm validation và preprocessing?
- [ ] Bộ nhớ phụ, recursion stack và I/O đã tính khi cần?
- [ ] Hàm có mutate input hoặc phụ thuộc concurrency không?
- [ ] Failure behavior khi input sai/ngoài phạm vi có rõ?
- [ ] Code, class name, lệnh `javac`/`java`, stdout đã chạy kiểm chứng?
- [ ] Test empty, duplicates, negative, no solution, INF và overflow?
- [ ] Oracle độc lập, seed và cỡ random cases có được ghi?
- [ ] Không nhầm test PASS với chứng minh đúng tuyệt đối?
- [ ] Khi mở rộng miền input, đã chọn lại thuật toán và proof?

## Kết luận

**Một lời giải đáng tin phải có phạm vi và bằng chứng.** Giả thiết trả lời *khi nào được dùng*, bất biến trả lời *vì sao phép biến đổi đúng*, hậu điều kiện trả lời *đáp án nghĩa là gì*, còn giới hạn sử dụng cho biết *khi nào cần từ chối, đổi thuật toán hoặc thay biểu diễn*. Những công thức Big-O chỉ đúng khi tính đủ validation và mô hình tài nguyên đã nêu.

Tìm kiếm nhị phân phải có sortedness; cửa sổ trượt hai con trỏ trong bài phải có số không âm; Dijkstra phải có cạnh không âm và khoảng cách biểu diễn an toàn. Những tiền đề này không thể bị xóa chỉ vì chương trình biên dịch được hoặc chạy qua ví dụ. Ghi rõ contract, chứng minh bất biến, kiểm thử bằng oracle độc lập và công khai giới hạn là các bước thiết yếu của **cài đặt và kiểm thử thuật toán**.
