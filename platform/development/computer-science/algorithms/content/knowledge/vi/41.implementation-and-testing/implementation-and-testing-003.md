# Tràn số nguyên, giá trị vô cực và tính toán modulo

**Tràn số nguyên** (*integer overflow*), **giá trị vô cực giả lập** (*infinity sentinel*) và **tính toán modulo** là ba nguồn lỗi lặng lẽ thường làm sai thuật toán dù ý tưởng và độ phức tạp đã đúng. Một phép cộng trong Dijkstra có thể biến khoảng cách không thể tới thành số âm; một tích hai số `int` có thể tràn trước khi được gán vào `long`; hoặc công thức `(a*b)%m` có thể tràn `long` trước khi phép `%` xảy ra. Các lỗi này thường khó phát hiện nếu bộ kiểm thử chỉ dùng số nhỏ và đồ thị liên thông.

Bài thuộc chủ đề **Cài đặt và kiểm thử**, hướng dẫn thiết kế **hợp đồng miền giá trị** và kiểm tra bằng Java 17 trở lên. Ta sẽ xem rõ sự khác nhau giữa số nguyên toán học và số nguyên máy, giới hạn `int`/`long`, `Math.addExact`/`multiplyExact`/`toIntExact`, dùng `BigInteger` khi cần kết quả chính xác lớn, lựa chọn `INF` trong đồ thị/DP, phép chia dư với số âm, chuẩn hóa modulo, cộng/nhân/lũy thừa modulo không tràn và điều kiện tồn tại nghịch đảo modulo.

Chương trình Java 17+ độc lập **`IntegerInfinityModuloDemo.java`** ở cuối bài kiểm chứng thực tế những rủi ro đó, bao gồm một Dijkstra dùng `INF` có kiểm tra và nhiều phép toán modulo lớn gần `Long.MAX_VALUE`. Các phép kiểm thử ngẫu nhiên đối chiếu với **`BigInteger`** và **Bellman–Ford số nguyên chính xác** để tránh dùng lại cùng thuật toán làm oracle.

## 1. Số nguyên toán học khác kiểu dữ liệu có độ rộng cố định

Trong toán học, nếu hai số nguyên a và b xác định, phép `a+b` và `a*b` cho một số nguyên có thể dài tùy ý. Trong Java, kiểu nguyên thủy thông dụng chỉ có số bit hữu hạn:

| Kiểu | Số bit | Miền giá trị |
| --- | ---: | --- |
| `byte` | 8 | −128 đến 127 |
| `short` | 16 | −32.768 đến 32.767 |
| `char` | 16 | 0 đến 65.535 (một code unit UTF-16, không phải luôn một ký tự Unicode hoàn chỉnh) |
| `int` | 32 | −2.147.483.648 đến 2.147.483.647 |
| `long` | 64 | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |

`int` và `long` là **số nguyên có dấu** (*signed integer*) với biểu diễn bù hai. Khi thực hiện **cộng, trừ hoặc nhân nguyên thủy** và kết quả nằm ngoài miền kiểu dữ liệu, Java giữ các bit thấp của kết quả toán học (tương đương phép tính trên vòng `2^32` hoặc `2^64`) và diễn giải lại theo số có dấu. Không có ngoại lệ tự động chỉ vì `int`/`long` bị tràn.

Ví dụ:

```java
int max = Integer.MAX_VALUE;
int wrapped = max + 1;  // -2147483648
```

Và:

```java
long max = Long.MAX_VALUE;
long wrapped = max + 1; // -9223372036854775808
```

Giá trị âm đột ngột không phải lỗi trong runtime Java: đó là **ngữ nghĩa của phép cộng nguyên thủy**. Lỗi xảy ra khi **thuật toán của ta kỳ vọng phép cộng toán học không giới hạn**.

### 1.1. Underflow cũng nguy hiểm

Nếu số nhỏ hơn `Integer.MIN_VALUE` hoặc `Long.MIN_VALUE`, phép trừ/đảo dấu cũng có thể tràn. Ví dụ:

```java
int min = Integer.MIN_VALUE;
int wrong = min - 1;  // Integer.MAX_VALUE
```

Đảo dấu giá trị âm nhỏ nhất là trường hợp đặc biệt:

```java
long min = Long.MIN_VALUE;
long result = -min;       // vẫn là Long.MIN_VALUE (tràn)
```

Vì miền số âm chứa nhiều hơn miền dương một đơn vị, không có giá trị `long` dương biểu diễn được `-Long.MIN_VALUE`. Điều đó cũng giải thích vì sao:

```java
Math.abs(Long.MIN_VALUE) == Long.MIN_VALUE
```

là `true`. **Không dùng `Math.abs(x)` để mặc định khẳng định kết quả không âm** nếu x có thể là giá trị MIN.

### 1.2. Tại sao kiểm thử chỉ dùng số nhỏ rất dễ bỏ lọt?

Với số nhỏ:

```text
a=100, b=200, a+b=300
a*b=20000
```

mọi kiểu int/long đều chứa được. Thuật toán trông đúng. Nhưng khi input có:

```text
a=2,000,000,000
b=2,000,000,000
```

phép cộng `int` đã vượt `Integer.MAX_VALUE`, còn tích vượt rất xa int. Bộ test nên chứa **số sát biên**, giá trị MIN/MAX, zero, số âm, phép cộng lặp, trường hợp không thể tới và kết quả modulo của số rất lớn.

## 2. Lỗi “gán vào long thì sẽ an toàn” — sai vì thứ tự đánh giá

Java quyết định kiểu số học theo **kiểu của các toán hạng khi biểu thức được tính**, không theo kiểu của biến nhận kết quả.

Ví dụ:

```java
int a = 50_000;
int b = 50_000;

long wrong = a * b;
```

`a*b` được tính bằng **int**, tràn thành:

```text
-1794967296
```

sau đó mới được mở rộng (*widening conversion*) sang long, nên biến `wrong` chứa một giá trị long **đã sai**.

Cách đúng:

```java
long correct = (long) a * b;  // 2500000000
```

Ép **ít nhất một toán hạng lên long trước phép nhân**. Một cách khác:

```java
long correct = 1L * a * b;
```

Với phép cộng cũng tương tự:

```java
int x = 2_000_000_000;
int y = 2_000_000_000;

long bad = x + y;          // int tràn trước
long good = (long)x + y;   // long chứa được 4000000000
```

### 2.1. `long` chưa chắc chứa được mọi tích

Hai giá trị `long` lớn có tích vượt xa 64 bit. Khi cần tính chính xác:

```java
BigInteger product = BigInteger.valueOf(a)
    .multiply(BigInteger.valueOf(b));
```

Nếu mục tiêu là **lấy modulo m**, có thể dùng thuật toán nhân modulo tránh tạo tích đầy đủ, hoặc dùng `BigInteger` và `.mod(...)`.

### 2.2. Khác nhau giữa ép kiểu mở rộng và ép kiểu thu hẹp

```java
long wide = Integer.MAX_VALUE;   // không mất thông tin
int narrow = (int) 3_000_000_000L; // cắt bớt bit cao
```

Ép từ `long` sang `int` không tự kiểm tra vùng. Nếu bắt buộc kết quả nằm trong int:

```java
int safe = Math.toIntExact(wideValue);
```

`Math.toIntExact` ném `ArithmeticException` khi long nằm ngoài miền int.

**Không nhầm:** `Long.parseLong` có thể ném lỗi khi chuỗi ngoài miền long, nhưng sau khi đã có số long rồi, các phép cộng/nhân tiếp theo vẫn có thể tràn.

## 3. Phát hiện overflow thay vì im lặng wrap

Java cung cấp các hàm kiểm tra chính xác:

```java
Math.addExact(a,b)
Math.subtractExact(a,b)
Math.multiplyExact(a,b)
Math.negateExact(a)
Math.incrementExact(a)
Math.decrementExact(a)
Math.toIntExact(value)
```

Ví dụ:

```java
try {
    long x = Math.addExact(Long.MAX_VALUE, 1);
} catch (ArithmeticException ex) {
    // Xử lý trường hợp vượt miền long.
}
```

Với `Math.multiplyExact`, cùng nguyên tắc:

```java
long product = Math.multiplyExact(a, b);
```

Nếu phép toán không biểu diễn được trong kiểu đã chọn, chương trình ném `ArithmeticException` thay vì âm thầm wrap.

### 3.1. Dùng `Exact` khi nào?

**Nên dùng** khi:

- Giá trị là tiền, tổng độ dài, tổng số lượng hoặc đáp án cần đúng tuyệt đối.
- Input có thể sát giới hạn kiểu số.
- Một lỗi overflow phải được báo cho caller thay vì thành “đáp án hợp lệ”.
- Muốn đảm bảo thuật toán đồ thị/DP không diễn giải số âm do tràn thành giá trị tối ưu.

**Có thể không dùng** khi phép toán theo thiết kế thực sự làm việc trên vòng số học bù hai (ví dụ một số hàm trộn hash 64 bit). Tuy nhiên cần ghi rõ wrap là **chủ ý toán học**, tránh tái sử dụng cho biến đại diện tần suất/khoảng cách thật.

### 3.2. Bảo vệ trước một phép cộng không âm

Nếu `0<=a`, `0<=b` và giới hạn trên là `LIMIT`, cần đảm bảo:

```text
a + b < LIMIT
```

mà **không cộng trước**, hãy kiểm tra:

```text
b < LIMIT - a
```

với điều kiện `0<=a<LIMIT`. Điều này đặc biệt hữu ích khi `LIMIT` là một **sentinel dành riêng** như INF.

Nếu yêu cầu `a+b<=LIMIT` thay vì `<`, điều kiện thay thành `b<=LIMIT-a`. **Dấu bằng rất quan trọng**: nếu `LIMIT` đồng thời biểu thị “không có đáp án”, giá trị đúng bằng LIMIT không được gán cho một kết quả hữu hạn.

### 3.3. Cộng nhiều số vẫn phải kiểm tra từng bước

Cộng ba số:

```java
long result = Math.addExact(
    Math.addExact(a, b), c);
```

Nếu tổng cuối vừa long nhưng một tổng trung gian theo thứ tự tính **không vừa**, `addExact` vẫn ném lỗi. Ví dụ tổng toán học của `Long.MAX_VALUE + 1 - 1` là Long.MAX_VALUE, nhưng tổng hai số đầu đã vượt long. Nếu bài toán thực sự cho phép các trung gian vượt miền dù kết quả cuối vừa, dùng `BigInteger` hoặc thay đổi thứ tự tính với chứng minh hợp lệ.

## 4. Khi nào chuyển sang `BigInteger`?

`java.math.BigInteger` là kiểu số nguyên độ dài tùy ý (giới hạn thực tế bởi bộ nhớ và thời gian). Nó thích hợp cho:

- Tổ hợp rất lớn (`n choose k`, giai thừa).
- Đếm số cách lớn hơn `Long.MAX_VALUE`.
- Phép nhân chính xác nhiều chữ số.
- Oracle độc lập để kiểm thử phép toán long tối ưu.
- Các kết quả không thể được đại diện bằng một sentinel long.

Ví dụ:

```java
BigInteger a = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger b = a.add(BigInteger.ONE);
System.out.println(b);
// 9223372036854775808
```

Không thể viết `BigInteger` bằng `+` hoặc `*`:

```java
BigInteger sum = a.add(b);
BigInteger product = a.multiply(b);
```

Khi chuyển ngược sang long:

```java
long checked = bigValue.longValueExact();
```

`longValueExact()` ném lỗi nếu không biểu diễn được; `longValue()` chỉ lấy những bit thấp và **có thể trả kết quả bị cắt**.

### 4.1. Ví dụ tổ hợp vượt long

```text
C(67,33)=14226520737620288370
```

Giá trị này lớn hơn:

```text
Long.MAX_VALUE=9223372036854775807
```

nên không dùng long nếu muốn kết quả chính xác. Công thức tích chia từng bước với `BigInteger` có thể tính đúng:

```java
result = result.multiply(BigInteger.valueOf(n-k+i))
               .divide(BigInteger.valueOf(i));
```

sau khi quy k về `min(k,n-k)` trong cách tính tổ hợp chuẩn. Các thương từng bước là số nguyên khi xây dựng theo công thức tổ hợp.

### 4.2. `BigInteger` không có nghĩa là luôn cần thiết

`BigInteger` tạo đối tượng và tốn CPU/bộ nhớ hơn phép toán primitive trong nhiều trường hợp. Nếu bài toán chứng minh được tổng nằm trong long, `long` với `Math.*Exact` có thể đủ và nhanh hơn. Nếu chỉ cần kết quả modulo m, có thể không cần biểu diễn số nguyên lớn đầy đủ; phép modular arithmetic có thể tránh overflow trực tiếp.

**Thiết kế số học đúng là chọn kiểu từ cận trên của bài toán**, không chọn BigInteger một cách máy móc hoặc chọn int chỉ vì ví dụ nhỏ.

## 5. Giá trị INF trong thuật toán đồ thị và quy hoạch động

Các thuật toán tìm đường đi ngắn, DP min-cost, khoảng cách chưa khởi tạo, hoặc giải bài toán tối ưu thường cần một giá trị biểu thị:

```text
"chưa thể tới"
"chưa tìm được lời giải"
"không có khoảng cách hữu hạn"
```

Trong ngôn ngữ toán học dùng `+∞`. Trong `long`, **không có số nguyên vô cực thật**. Lập trình viên thường chọn một **sentinel**:

```java
static final long INF = Long.MAX_VALUE / 4;
```

Giá trị này bằng:

```text
2305843009213693951
```

và được dành riêng cho trạng thái **không thể tới**.

### 5.1. Vì sao không dùng thẳng `Long.MAX_VALUE` rồi cộng?

Giả sử:

```java
long dist = Long.MAX_VALUE; // unreachable
long candidate = dist + 10;
```

Phép cộng long overflow; candidate trở thành giá trị âm, có thể làm thuật toán tin đó là đường đi rất ngắn.

Đối với `INF=Long.MAX_VALUE/4`, cộng một vài trọng số nhỏ có thể không overflow, nhưng **không được dựa vào phép cộng với INF**:

```java
long candidate = INF + weight; // sai ngữ nghĩa, dù chưa overflow
```

Vì INF là **ký hiệu trạng thái**, không phải khoảng cách thật. Nếu `dist[u]==INF`, không được relax từ u như thể có một đường đi dài INF.

### 5.2. `INF=MAX/4` không phải phép thuật chống overflow

Chọn một sentinel nhỏ hơn MAX có thể tạo vùng an toàn cho một số phép cộng dự kiến, nhưng chỉ khi **có chứng minh giới hạn tổng**. Nếu trọng số rất lớn hoặc đường đi dài, cộng nhiều lần vẫn có thể vượt vùng dành cho giá trị hữu hạn.

Hợp đồng an toàn trong demo:

```text
0 <= finite distance < INF
0 <= edge weight < INF
INF reserved only for unreachable.
```

Để cộng khoảng cách hữu hạn d với trọng số w:

```java
if (w >= INF-d) {
    throw new ArithmeticException(
        "finite path reaches reserved INF range");
}
long candidate = d+w;
```

Như vậy **không bao giờ** trả `INF` cho một đường đi hữu hạn trong miền hợp đồng. Nếu phát hiện đường đi đạt hoặc vượt INF, demo **fail-fast** thay vì âm thầm coi nó là không thể tới. Chương trình có thể từ chối cả một đồ thị mà **đường tối ưu vẫn nhỏ nhưng có một đường ứng viên quá lớn được xét**; đó là giới hạn thiết kế minh bạch của demo, không phải tính chất toán học bắt buộc của Dijkstra.

### 5.3. Có nên bão hòa về INF (*saturating addition*)?

Một số code viết:

```java
candidate = Math.min(INF, dist[u] + weight);
```

Cách này **không an toàn** nếu `dist[u]+weight` đã overflow thành âm trước khi min. Có thể kiểm tra trước:

```text
if weight >= INF-dist:
    candidate = INF
else:
    candidate = dist+weight
```

nhưng bão hòa như thế **mất phân biệt** giữa “có đường đi hữu hạn rất lớn” và “không có đường đi”. Nó chỉ đúng nếu **đề bài và output chấp nhận cắt ngưỡng**, hoặc ta đã chứng minh mọi đường đi cần quan tâm đều nhỏ hơn INF.

Bài này chủ trương **throw** khi gặp giá trị hữu hạn không biểu diễn được theo hợp đồng, nhằm không trả một kết quả sai có vẻ hợp lệ.

### 5.4. Phân biệt khoảng cách 0, INF và lớn bất thường

Nếu đỉnh nguồn là s:

```text
distance[s]=0.
```

Một đỉnh khác có đường đi trọng số 0 cũng có thể có distance 0; **zero không nghĩa unreachable**.

Nếu không thể tới:

```text
distance[v]=INF.
```

Nếu có đường đi hữu hạn gần INF, phải biết hợp đồng cho phép hay từ chối. Không sử dụng dấu âm để biểu diễn unreachable trong thuật toán có khoảng cách không âm nếu nó có thể lẫn với lỗi overflow hoặc với bài toán cho trọng số âm.

### 5.5. Trong DP cần phân biệt min và max sentinel

Với bài toán **min** và trạng thái không hợp lệ, thường dùng `+INF` rồi lấy min. Với bài toán **max**, thường dùng `-INF` cho trạng thái không thể đạt rồi lấy max. Không tự cộng giá trị sentinel với transition cost trong cả hai trường hợp.

Nếu bài toán cho kết quả âm thật, `-1` có thể là giá trị hợp lệ; dùng `-1` làm “không thể tới” cần chứng minh miền đáp án không chứa -1. Một mô hình dùng `boolean[] reachable` cùng `long[] value` hoặc kiểu `OptionalLong`/`BigInteger` có thể rõ ràng hơn nếu miền giá trị dài.

## 6. Dijkstra với số nguyên an toàn

Dijkstra áp dụng khi **mọi cạnh có trọng số không âm**. Cài đặt minh họa dùng:

```java
long[] dist;
Arrays.fill(dist, INF);
dist[source]=0;
```

Mỗi lần xét cạnh `(u,v,w)` từ một đỉnh đang có khoảng cách hữu hạn:

```text
candidate = addFiniteDistance(dist[u],w)

if candidate < dist[v]:
    dist[v] = candidate.
```

### 6.1. Ưu tiên hàng đợi không được trừ để so sánh

Một comparator có nguy cơ tràn:

```java
(a,b) -> (int)(a.distance - b.distance)
```

Vì chênh lệch của hai long có thể vượt int hoặc long, comparator có thể vi phạm thứ tự tổng quát và làm `PriorityQueue` hỏng.

Cách đúng:

```java
Comparator.comparingLong(State::distance)
```

hoặc:

```java
Long.compare(a.distance, b.distance)
```

Sự an toàn của comparator **độc lập** với việc phép cộng trọng số đã được kiểm tra overflow.

### 6.2. Đỉnh unreachable và stale entries

Nếu hàng đợi ưu tiên chứa một trạng thái cũ cho đỉnh v, bỏ qua khi:

```java
if (top.distance != dist[top.vertex]) continue;
```

Đây là kỹ thuật lazy priority queue thường dùng với Dijkstra. Nó không liên quan trực tiếp đến overflow nhưng cần cho tính đúng/hiệu năng của ví dụ.

Trong demo, chỉ đưa vào queue những đỉnh đang có khoảng cách **hữu hạn**. Đỉnh không thể tới không có phần tử queue, và kết quả ở `dist[v]` tiếp tục là INF.

### 6.3. Ví dụ sáu đỉnh

Đồ thị có hướng:

```text
0 -> 1 (6)
0 -> 2 (2)
2 -> 1 (1)
1 -> 3 (3)
2 -> 3 (12)
3 -> 4 (1)

Đỉnh 5 không có đường đi từ 0.
```

Kết quả:

```text
dist[0]=0
dist[1]=3  (0->2->1)
dist[2]=2
dist[3]=6  (0->2->1->3)
dist[4]=7  (0->2->1->3->4)
dist[5]=INF (unreachable).
```

Mã in:

```text
[0, 3, 2, 6, 7, INF]
```

Không in số thô `2305843009213693951` ở vị trí đỉnh 5, vì đó là **nhãn trạng thái** chứ không phải độ dài đường đi.

### 6.4. Dijkstra không giải được cạnh âm chỉ bằng kiểu long lớn

Ngay cả khi tất cả phép cộng được làm chính xác bằng BigInteger, Dijkstra vẫn không đúng cho đồ thị có cạnh âm trong trường hợp tổng quát. Nếu cạnh âm có thể xuất hiện, chọn Bellman–Ford hoặc thuật toán phù hợp với hợp đồng input. **Kiểm soát số học không thay thế điều kiện toán học của thuật toán**.

### 6.5. Giới hạn ở các đường ứng viên

Trong demo, `addFiniteDistance` được gọi **trước khi so sánh với dist[v]**. Nếu một đường ứng viên có tổng đạt INF, chương trình ném lỗi **ngay cả khi** đỉnh v đã có một đường khác ngắn hơn. Tính chất này là lựa chọn **fail-fast bảo toàn hợp đồng** trên mọi phép relaxation được xét.

Nếu bài toán yêu cầu tiếp tục tìm những đường ngắn trong đồ thị có các đường đi rất lớn, ta có thể dùng `BigInteger` hoặc một thiết kế `reachable` riêng và so sánh các giá trị lớn không mất thông tin. Không giải quyết bằng cách âm thầm bỏ một cạnh mà chưa chứng minh nó không ảnh hưởng đáp án.

## 7. Đếm số cách và DP: overflow có thể xuất hiện trước giới hạn

Nhiều bài DP đếm số cách yêu cầu:

```text
dp[i] = dp[j] + dp[k] + ...
```

Số phương án có thể tăng nhanh hơn độ dài input. Dùng int chỉ vì `n<=100` không chứng minh đủ: có những bài tổ hợp với số cách cỡ `2^n` hoặc lớn hơn, vượt cả long.

Có ba hợp đồng đáp án khác nhau:

1. **Đáp án chính xác:** dùng BigInteger nếu upper bound vượt long.
2. **Đáp án modulo m:** lưu phần dư được chuẩn hóa và dùng phép toán modulo đúng.
3. **Chỉ cần biết có vượt ngưỡng T:** có thể dùng saturating count tới T+1 nếu đề bài chỉ hỏi `count>T` và công thức/threshold cho phép.

Không được dùng một đáp án modulo để trả lời câu hỏi “có bao nhiêu cách chính xác?” hoặc để so sánh thứ tự lớn–bé của hai số cách thật. Hai giá trị lớn khác nhau có thể có cùng phần dư.

### 7.1. Đếm số cách và trạng thái unreachable là hai vấn đề

Với bài toán min-cost, INF thường biểu thị **không thể đạt**. Với bài toán count, zero có thể biểu thị **không có cách**. Nếu đếm modulo m, một số cách thật dương có thể chia hết m và có phần dư 0. Do đó `waysMod==0` **không chứng minh** không có cách; nếu cần kiểm tra có/không có cách, lưu một trạng thái reachability riêng.

## 8. Phép `%` trong Java là phần dư, không luôn là modulo không âm

Trong toán học, phần dư chuẩn modulo m dương thường thuộc:

```text
0,1,...,m-1.
```

Java `%` là phép **remainder**; dấu của kết quả theo số bị chia, nên:

```java
-7 % 5 == -2
```

và:

```java
Math.floorMod(-7,5) == 3
```

vì:

```text
-7 = (-2)*5 + 3
```

với thương lấy floor là −2.

Nếu bài toán yêu cầu khóa bucket nằm trong `[0,m)`, dùng:

```java
long normalized = Math.floorMod(value, modulus);
```

khi `modulus>0`.

### 8.1. Công thức chuẩn hóa hai lần `%`

Một cách viết phổ biến:

```java
((x % m) + m) % m
```

với m>0. Nhưng nếu `x%m` không âm và m gần `Long.MAX_VALUE`, phép cộng thêm m **có thể overflow**; vì vậy công thức này không an toàn tổng quát cho long lớn.

An toàn hơn:

```java
Math.floorMod(x,m)
```

hoặc nếu cần tự viết với m>0:

```java
long r = x % m;
if (r < 0) r += m;
```

Ở nhánh `r<0`, `r+m` nằm từ 1 tới m-1 nên không tràn long. Nếu r=0 thì giữ nguyên 0.

### 8.2. Trường hợp `Long.MIN_VALUE`

Không viết:

```java
Math.abs(x) % m
```

để “lấy modulo dương”. Với x=`Long.MIN_VALUE`, `Math.abs(x)` vẫn âm. Phương thức `floorMod` không đòi lấy trị tuyệt đối, nên xử lý được x nhỏ nhất.

Ví dụ:

```text
Long.MIN_VALUE = -9223372036854775808
Long.MAX_VALUE =  9223372036854775807

floorMod(Long.MIN_VALUE, Long.MAX_VALUE)
    = 9223372036854775806.
```

### 8.3. Modulo m=1

Mọi số nguyên đều đồng dư 0 theo modulo 1:

```text
x mod 1 = 0.
```

Đây là trường hợp biên phải được các hàm cộng, nhân, lũy thừa modulo hỗ trợ. Chẳng hạn:

```text
a^0 mod 1 = 1 mod 1 = 0.
```

Lưu ý: phép **nghịch đảo modulo** thông thường được xét với m>1; demo từ chối m<=1 để tránh diễn giải ring tầm thường như trường hợp thông thường.

### 8.4. Modulo 0 và số âm

Mã demo yêu cầu **m>0** cho mọi hàm modular arithmetic. Modulo 0 là không xác định trong toán học và phép `%0` trong Java ném `ArithmeticException`. Modulo âm có những quy ước khác nhau giữa ngôn ngữ; muốn code có thể kiểm tra dễ dàng, đặt hợp đồng `modulus>0`.

## 9. Quy tắc cộng, trừ và nhân modulo

Cho m>0 và hai phần dư đã chuẩn hóa:

```text
0 <= a < m
0 <= b < m.
```

Trong toán học:

```text
(a+b) mod m
(a-b) mod m
(a*b) mod m.
```

Không được giả định Java có số nguyên chính xác không giới hạn.

### 9.1. Cộng modulo vẫn có thể tràn

Sai khi m lớn:

```java
long result = (a + b) % m;
```

Dù a,b nhỏ hơn m, tổng có thể lên tới `2m-2`, vượt Long.MAX_VALUE nếu m lớn.

Một phương pháp **không cần BigInteger** là:

```java
long room = m - b;
return a >= room ? a - room : a + b;
```

Với `0<=a,b<m`, `room=m-b` nằm `[1,m]`. Nếu `a<room`, thì `a+b<m`, nên cộng không tràn. Nếu `a>=room`, thì:

```text
a+b-m = a-(m-b)
```

và kết quả nằm `[0,m-1]`, được tính bằng phép trừ an toàn.

Ví dụ với:

```text
m = Long.MAX_VALUE
a = m-2
b = m-3
```

toán học cho:

```text
a+b = 2m-5
(a+b) mod m = m-5 = 9223372036854775802.
```

Hàm `addMod` trong Java trả giá trị này mà **không hề tạo 2m-5 trong long**.

### 9.2. Trừ modulo

Với a,b chuẩn hóa:

```text
(a-b) mod m
```

có thể tính an toàn:

```java
long subtractMod(long a, long b, long m) {
    if (a >= b) return a - b;
    return m - (b - a);
}
```

với `0<=a,b<m` và m>0. Không cần lấy `%` nếu kết quả đã trong `[0,m)`.

Hãy tránh `a-b+m` khi chưa phân tích overflow: mặc dù `a-b` an toàn do hai số trong `[0,m)`, cộng m sau đó có thể được viết sai thứ tự hoặc mở rộng sang trường hợp input chưa chuẩn hóa. Nên giữ hợp đồng rõ ràng và kiểm thử số sát m.

### 9.3. Nhân modulo — phép nhân trước `%` có thể tràn

Sai với long lớn:

```java
long product = (a*b) % m;
```

Toán học có thể cần tới 126 bit để chứa tích hai số 63 bit, trong khi Java long chỉ 64 bit. `%m` diễn ra **sau khi tích đã bị wrap**, nên phần dư thường sai.

Có hai hướng an toàn:

**Hướng A — BigInteger:**

```java
long r = BigInteger.valueOf(a)
    .multiply(BigInteger.valueOf(b))
    .mod(BigInteger.valueOf(m))
    .longValueExact();
```

m>0. Cách này dễ audit, phù hợp khi hiệu năng cho phép.

**Hướng B — nhân nhị phân bằng cộng modulo an toàn:**

```text
result=0
while b>0:
    if b odd:
        result=(result+a) mod m safely
    b = floor(b/2)
    if b>0:
        a=(a+a) mod m safely
return result
```

Với a,b đã chuẩn hóa, m>0, vòng lặp khoảng số bit của b, tối đa 63 vòng khi m<=Long.MAX_VALUE. Độ phức tạp O(log b) phép cộng modulo; không hình thành tích a*b trực tiếp. Demo dùng hướng B và đối chiếu với BigInteger trên 2.500 input ngẫu nhiên.

### 9.4. Bất biến của nhân nhị phân

Ban đầu:

```text
result=0, factor=a, remaining=b.
```

Tại mọi vòng có thể xem:

```text
result + factor*remaining ≡ a_original*b_original (mod m).
```

Nếu remaining lẻ, chuyển một factor sang result, sau đó chia đôi remaining. Nếu remaining chẵn, chỉ nhân đôi factor và chia đôi remaining. Dùng `addMod` để tính các phép cộng/nhân đôi phần dư, giữ mọi trạng thái trong `[0,m)`.

Vì remaining giảm theo chia đôi, thuật toán kết thúc sau O(log b) vòng. Khi remaining=0, bất biến cho:

```text
result ≡ a_original*b_original (mod m)
```

và do result đã chuẩn hóa, đó là phần dư cần trả.

### 9.5. `Long.remainderUnsigned` có thay thế nhân modulo không?

`Long.remainderUnsigned` giúp diễn giải số nguyên long như số unsigned trong phép chia dư, nhưng **không khôi phục các bit cao của tích 128-bit** đã bị mất vì phép nhân 64-bit. Nếu trước đó đã tính `a*b` bằng long và tràn, đổi `%m` sang `Long.remainderUnsigned` không biến nó thành phép nhân modulo chính xác.

## 10. Lũy thừa modulo bằng binary exponentiation

Muốn tính:

```text
base^exponent mod m
```

với `exponent>=0`, `m>0`, không tạo `base^exponent` nguyên trước. Ta dùng bình phương nhanh (*exponentiation by squaring*):

```text
result = 1 mod m
factor = floorMod(base,m)

while exponent>0:
    if exponent odd:
        result = multiplyMod(result,factor,m)
    exponent = floor(exponent/2)
    if exponent>0:
        factor = multiplyMod(factor,factor,m)
return result
```

Bất biến:

```text
result * factor^remaining
    ≡ base_original^exponent_original (mod m).
```

Vòng lặp số bước O(log exponent). Vì `multiplyMod` bằng cộng nhị phân có O(log m) bước trong trường hợp tổng quát, chi phí demo là:

```text
O(log exponent * log m)
```

phép cộng modulo. Nếu dùng nhân modulo nhanh hơn hoặc BigInteger được tối ưu, chi phí thực tế khác, nhưng vẫn phải kiểm soát overflow.

### 10.1. Các trường hợp biên

```text
exponent=0:
    base^0 mod m = 1 mod m.

m=1:
    mọi kết quả modulo = 0.

base âm:
    trước tiên chuẩn hóa floorMod(base,m).
```

Ví dụ demo:

```text
powMod(-2,63,1000000007)=708828003
```

Đầu vào âm không gây phần dư âm ở cuối vì code chuẩn hóa base.

### 10.2. Vì sao không dùng `Math.pow`?

`Math.pow` trả về `double` và có thể mất chính xác nguyên khi số lớn; sau đó ép sang long và `%m` không phục hồi các chữ số đã bị làm tròn. Ngoài ra, `double` có thể thành Infinity. Đối với modular exponentiation số nguyên, dùng thuật toán lũy thừa modulo hoặc `BigInteger.modPow` thay vì `Math.pow`.

## 11. Nghịch đảo modulo và phép chia

Muốn giải:

```text
a*x ≡ 1 (mod m)
```

ta tìm **nghịch đảo modulo** của a, ký hiệu `a^(-1) mod m`. Với m>1, nghịch đảo tồn tại **khi và chỉ khi**:

```text
gcd(a,m)=1.
```

Ví dụ:

```text
3*4 =12 ≡1 mod 11
inverse(3,11)=4.
```

Nhưng:

```text
gcd(6,9)=3
```

nên `6` **không có nghịch đảo modulo 9**. Việc chia thông thường `a/b` rồi lấy `%m` không tương đương nhân với nghịch đảo trong số học modulo.

### 11.1. Cách tìm nghịch đảo

Các phương pháp thường dùng:

- **Extended Euclidean algorithm**: tìm x,y sao cho `a*x+m*y=gcd(a,m)`; khi gcd=1, x chính là nghịch đảo theo modulo m.
- **Fermat nhỏ**: nếu m=p là **số nguyên tố** và a không chia hết cho p, có thể tính `a^(p-2) mod p`.
- **BigInteger.modInverse**: dùng thư viện cho số nguyên lớn và tránh overflow trong hệ số Euclid tự cài bằng long.

Demo dùng:

```java
BigInteger.valueOf(a)
    .modInverse(BigInteger.valueOf(m))
```

sau khi chuẩn hóa và kiểm tra gcd=1. Không cần chứng minh m nguyên tố, vì điều kiện tổng quát là **coprime**. Nếu gcd≠1, mã ném `ArithmeticException`.

### 11.2. Modulo không phải phép chia trường số thực

Ta có:

```text
a/b (mod m)
```

chỉ hợp lệ dưới cách hiểu:

```text
a * inverse(b,m) mod m
```

khi nghịch đảo tồn tại. Nếu m không nguyên tố, có nhiều b không khả nghịch. Nếu b chia hết m, phép nghịch đảo không tồn tại. Đối với những bài toán có m nguyên tố, cần biết **m thực sự là prime** và b không tương đương 0.

### 11.3. Có thể chia cả hai vế cho gcd không?

Với đồng dư tuyến tính:

```text
b*x ≡ a (mod m)
```

nếu `d=gcd(b,m)`, nghiệm tồn tại khi `d` chia a. Khi đó có thể rút gọn phương trình theo d và tìm nghiệm trong modulo `m/d`, nhưng không đồng nghĩa “b có nghịch đảo modulo m”. Bài toán giải đồng dư tuyến tính là việc khác với phép chia modulo trực tiếp. Hãy nêu rõ ngữ nghĩa yêu cầu trước khi code.

## 12. Overflow trong trung gian thuật toán tối ưu

### 12.1. Cộng đường đi trong đồ thị

Khi tính:

```text
candidate = dist[u] + edgeWeight
```

cần xét:

- `dist[u]` có phải INF không?
- `edgeWeight` có không âm nếu dùng Dijkstra không?
- Tổng toán học có nằm trong miền hữu hạn không?
- Phép cộng có overflow kiểu số không?
- Comparator có ổn khi khoảng cách lớn không?

Một lỗi trong bất kỳ điểm nào có thể tạo đường đi ngắn giả.

### 12.2. Tổng prefix và sliding window

```java
long prefix[i] = prefix[i-1] + a[i];
```

Nếu `a[i]` có cả số âm và dương, tổng cuối có thể nhỏ nhưng prefix trung gian có thể vượt long. Dùng BigInteger nếu giới hạn input không đảm bảo. Nếu chỉ cần modulo m, cập nhật prefix bằng phép cộng modulo an toàn.

### 12.3. Binary search tính midpoint

Sai trong môi trường có thể tràn:

```java
int mid = (lo + hi) / 2;
```

Nếu `lo,hi>=0` và tổng vượt Integer.MAX_VALUE, midpoint bị âm. Cách thường dùng khi `0<=lo<=hi`:

```java
int mid = lo + (hi - lo) / 2;
```

vì `hi-lo` không âm và <=Integer.MAX_VALUE trong hợp đồng đó. Nếu lo có thể âm rất lớn và hi rất lớn, ngay cả `hi-lo` có thể overflow; khi đó phải chọn phương thức tính trung điểm theo miền giá trị đã chứng minh hoặc dùng số rộng hơn.

Trong Java hiện đại, một cách cẩn thận cho indices không âm có thể là:

```java
int mid = (lo + hi) >>> 1;
```

được dùng ở một số thư viện để khử tràn theo ngữ nghĩa unsigned, nhưng **không được tự áp dụng cho khoảng có chỉ số âm** mà chưa phân tích. Hãy chọn cách đơn giản nhất phù hợp hợp đồng index.

### 12.4. Comparator dựa trên phép trừ

Không viết:

```java
(a,b) -> a-b
```

để so sánh int có thể sát hai đầu miền. `a-b` có thể overflow, gây comparator không nhất quán. Dùng:

```java
Integer.compare(a,b)
Long.compare(a,b)
```

hoặc các `Comparator.comparingInt/comparingLong` tương ứng.

### 12.5. Hash dùng overflow cố ý khác tổng chi phí

Nhiều hash/mixer 64-bit cố ý cho phép phép nhân/cộng wrap. Điều đó **hợp lệ trong thiết kế hash** nếu phép toán trên bit được chứng minh hoặc kiểm thử. Nhưng không nên “tái sử dụng kiểu hash-safe long arithmetic” làm arithmetic cho tiền/khoảng cách/tần suất. Ngữ nghĩa yêu cầu khác nhau.

## 13. Vô cực với số thực `double` và `float`

Java có các giá trị IEEE-754:

```java
Double.POSITIVE_INFINITY
Double.NEGATIVE_INFINITY
Double.NaN
```

Khác với `long INF` chỉ là **sentinel được người viết chọn**, `Double.POSITIVE_INFINITY` là một giá trị dấu phẩy động có biểu diễn đặc biệt.

```java
double x = 1.0 / 0.0; // +Infinity
double y = 0.0 / 0.0; // NaN
```

Có thể kiểm tra:

```java
Double.isInfinite(x)
Double.isNaN(y)
Double.isFinite(value)
```

### 13.1. NaN làm hỏng các so sánh trực giác

Với `NaN`, các phép `<`, `>`, `==` thông thường đều không phản ánh thứ tự như số thực: `NaN==NaN` là false. Nếu một thuật toán tối ưu dùng `double`, phải xác định cách xử lý NaN thay vì trộn NaN vào comparators một cách im lặng.

### 13.2. `double` không thay thế số nguyên 64-bit chính xác

`double` chỉ có 53 bit độ chính xác nhị phân cho các số nguyên (bao gồm bit ẩn) và không thể biểu diễn **mọi** số nguyên 64-bit. Dùng double để “tránh tràn long” có thể làm hai khoảng cách nguyên khác nhau bị làm tròn thành cùng số. Nếu yêu cầu đếm/chấm điểm chính xác, dùng long với hợp đồng cận hoặc BigInteger.

### 13.3. Khi nào dùng vô cực IEEE?

Trong một số thuật toán số thực, `Double.POSITIVE_INFINITY` là giá trị khởi tạo thuận tiện cho min-distance, nhưng phải kiểm soát NaN, số thực không chính xác, overflow sang Infinity, và giả thiết về trọng số. Không thể áp dụng quy tắc `long==INF` cho double không thay đổi, cũng không nên dùng phép so `==` cho các kết quả số thực tích lũy cần sai số.

## 14. Xác định cận kiểu số trước khi cài đặt

Một checklist phân tích miền:

1. **Giới hạn đầu vào:** từng giá trị có thể lớn/nhỏ đến đâu?
2. **Số lần tích lũy:** tổng có thể chứa tối đa bao nhiêu số?
3. **Tích:** hai hệ số có thể lớn đến đâu? Có cần 128 bit trung gian?
4. **Cực trị:** có thể gặp MIN_VALUE/MAX_VALUE hoặc số âm không?
5. **Trạng thái đặc biệt:** INF được dành riêng cho “không tới” hay cho một giá trị thật?
6. **Đáp án:** chính xác, modulo m hay so sánh tới một ngưỡng?
7. **Comparator:** có dùng phép trừ có thể tràn không?
8. **Oracle:** có công cụ độc lập (`BigInteger`, brute force, Bellman–Ford) kiểm tra trường hợp nhỏ?
9. **Giới hạn dịch chuyển:** ép `long->int` có thể mất dữ liệu không?
10. **Trách nhiệm lỗi:** nếu input vượt hợp đồng, throw, trả status riêng hay dùng BigInteger?

Nếu không chứng minh được một cận hữu hạn, dùng `BigInteger` cho phần tính chính xác hoặc nêu rõ rằng phiên bản tối ưu có giới hạn dữ liệu. **Không đoán cỡ số dựa vào vài ví dụ hoặc test mẫu.**

## 15. Bộ quy tắc modulo an toàn trong Java

Với `m>0` và phần dư chuẩn hóa `0<=a,b<m`:

| Phép toán | Cách làm an toàn | Giới hạn |
| --- | --- | --- |
| Chuẩn hóa số có dấu | `Math.floorMod(x,m)` | M phải dương |
| Cộng modulo | So `a` với `m-b`, rồi cộng hoặc trừ | a,b đã chuẩn hóa |
| Trừ modulo | `a>=b ? a-b : m-(b-a)` | a,b đã chuẩn hóa |
| Nhân modulo | Binary multiply bằng `addMod`, hoặc BigInteger | Không tạo `a*b` trong long |
| Lũy thừa modulo | Binary exponentiation + `multiplyMod` | exp không âm, m dương |
| Nghịch đảo modulo | Extended Euclid hoặc BigInteger `.modInverse()` | Chỉ có khi gcd(a,m)=1, m>1 |
| Phép chia modulo | Nhân với nghịch đảo | Phải tồn tại nghịch đảo |

Đừng gọi `Math.floorMod` mỗi lần cho một giá trị đã chuẩn hóa nếu vấn đề hiệu năng rất nhạy, nhưng **đừng hy sinh correctness** trước khi có benchmark và chứng minh.

### 15.1. Bảo vệ tính đúng cho số gần `Long.MAX_VALUE`

Với:

```text
m = 9223372036854775807
a = m-2
b = m-3
```

Tích toán học của a và b quá lớn cho long. Tuy nhiên:

```text
a ≡ -2 (mod m)
b ≡ -3 (mod m)

a*b ≡ 6 (mod m).
```

Hàm `multiplyMod` demo trả 6 bằng cộng modulo nhị phân, không tạo tích.

Tổng:

```text
a+b ≡ -5 (mod m) = m-5
                  = 9223372036854775802.
```

Hàm `addMod` demo trả đúng mà không overflow.

## 16. Đánh giá độ phức tạp các giải pháp

Giả sử mô hình máy coi cộng/so sánh long là O(1), `m>0` và b đã chuẩn hóa:

| Tác vụ | Thời gian theo số bước | Bộ nhớ phụ |
| --- | --- | --- |
| `normalize` với `Math.floorMod` | O(1) | O(1) |
| `addMod` | O(1) | O(1) |
| `multiplyMod` | O(log b) vòng | O(1) |
| `powerMod` | O(log exponent × log m) cộng modulo | O(1) |
| `inverseMod` qua BigInteger | Phụ thuộc bit length và thuật toán Euclid trong thư viện | BigInteger temporaries |
| `choose(n,k)` BigInteger | O(k) bước nhân/chia số lớn | Tăng theo số bit của đáp án |
| Dijkstra với binary heap | O((V+E) log V) hoặc thường viết O((V+E) log V) với lazy duplicate heap (điều chỉnh log theo số entries) | O(V+E) |
| Bellman–Ford oracle | O(VE) | O(V) ngoài graph |

**Chi tiết Dijkstra:** Khi dùng priority queue không có decrease-key, số phần tử queue có thể là O(E) nên phân tích cẩn thận là `O((V+E) log(V+E))` trong mô hình graph tổng quát. Với simple graph E<=V², ta có log E=O(log V), thường rút thành `O((V+E) log V)`. Với multigraph có vô số cạnh song song theo V, không tự đồng nhất log E với log V. Code demo dùng lazy insertion và bỏ stale entries.

**Chi tiết BigInteger:** Nếu kích thước bit không còn cố định, các phép nhân/chia BigInteger không còn O(1); chi phí phụ thuộc số chữ số và thuật toán nội bộ. Vì bài nói về tràn số và cận bộ nhớ, cần phân biệt cận trên **mô hình từ máy 64-bit** với mô hình bit complexity.

### 16.1. Khi nào tối ưu nhân modulo hơn repeated doubling?

Nếu phải thực hiện hàng triệu phép nhân modulo với m lớn, O(log m) phép cộng cho mỗi phép có thể tốn CPU. Có thể nghiên cứu:

- `BigInteger` đã tối ưu trên số lớn;
- Montgomery multiplication khi modulus phù hợp;
- Barrett reduction;
- Các thủ thuật dùng unsigned multiplication high bits hoặc phần cứng hỗ trợ, với chứng minh cẩn thận.

Không sao chép một mẹo nhân 128-bit/64-bit phụ thuộc ngôn ngữ khác vào Java rồi tin rằng ép kiểu `long` là đủ. Ưu tiên **đúng trước** và chỉ tối ưu sau khi benchmark.

## 17. Ví dụ chạy độc lập Java 17+

Tệp **`IntegerInfinityModuloDemo.java`** chứa:

- `normalize`: đưa số nguyên có dấu về phần dư không âm bằng `Math.floorMod`.
- `addMod`: cộng hai phần dư theo phép so sánh, **không bao giờ cộng quá m−1 trong long**.
- `multiplyMod`: nhân theo bit bằng cộng modulo an toàn.
- `powerMod`: lũy thừa nhị phân với số mũ không âm.
- `inverseMod`: dùng `BigInteger.modInverse`, chỉ khi gcd=1.
- `choose`: tính tổ hợp chính xác bằng BigInteger.
- `INF` và `addFiniteDistance`: giữ bất biến mọi khoảng cách hữu hạn `<INF`.
- `dijkstra`: weighted directed graph, chỉ trọng số không âm, dùng comparator không trừ.
- `exactDistances`: oracle Bellman–Ford dùng BigInteger trên đồ thị nhỏ.
- `randomOracles`: 2.500 phép cộng/nhân modulo lớn, 700 phép lũy thừa, 400 phép nghịch đảo và 350 đồ thị để kiểm tra kết quả Dijkstra.
- `expectFailure`: xác nhận các input không hợp lệ/overflow bị phát hiện đúng lớp lỗi.

Trong `randomOracles`, các phép toán modulo được so với `BigInteger` **độc lập** với thuật toán tối ưu. Các đồ thị ngẫu nhiên có trọng số không âm nhỏ và số đỉnh không quá 9; oracle Bellman–Ford đúng trong phạm vi đó và không dùng lại Dijkstra để tự kiểm.

**Không có phép đo hiệu năng thời gian thực**, không sinh số ngẫu nhiên bảo mật và không tạo file/thư viện ngoài Java standard library.

### 17.1. Mã đầy đủ

```java
import java.math.BigInteger;
import java.util.*;

public class IntegerInfinityModuloDemo {
    static final long INF = Long.MAX_VALUE / 4;

    record Edge(int to, long weight) {}
    record State(int vertex, long distance) {}

    static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }

    static void expectFailure(
            Class<? extends Throwable> kind, Runnable action) {
        try {
            action.run();
        } catch (Throwable ex) {
            if (kind.isInstance(ex)) return;
            throw new AssertionError("Wrong error type: " + ex);
        }
        throw new AssertionError(
                "Expected failure: " + kind.getSimpleName());
    }

    static long normalize(long x, long modulus) {
        if (modulus <= 0)
            throw new IllegalArgumentException("modulus must be positive");
        return Math.floorMod(x, modulus);
    }

    // Input contract: 0 <= a,b < modulus; modulus > 0.
    static long addMod(long a, long b, long modulus) {
        if (modulus <= 0 || a < 0 || b < 0
                || a >= modulus || b >= modulus) {
            throw new IllegalArgumentException(
                    "addMod requires normalized residues");
        }
        long room = modulus - b; // safe: 1 <= room <= modulus
        return a >= room ? a - room : a + b;
    }

    // Binary (Russian-peasant) multiplication; never forms a*b.
    static long multiplyMod(long a, long b, long modulus) {
        if (modulus <= 0 || a < 0 || b < 0
                || a >= modulus || b >= modulus) {
            throw new IllegalArgumentException(
                    "multiplyMod requires normalized residues");
        }
        long result = 0;
        while (b != 0) {
            if ((b & 1L) != 0) {
                result = addMod(result, a, modulus);
            }
            b >>>= 1;
            if (b != 0) a = addMod(a, a, modulus);
        }
        return result;
    }

    static long powerMod(long base, long exponent, long modulus) {
        if (exponent < 0 || modulus <= 0) {
            throw new IllegalArgumentException(
                    "exponent must be nonnegative, modulus positive");
        }
        long factor = normalize(base, modulus);
        long result = 1 % modulus;
        while (exponent != 0) {
            if ((exponent & 1L) != 0) {
                result = multiplyMod(result, factor, modulus);
            }
            exponent >>>= 1;
            if (exponent != 0) {
                factor = multiplyMod(factor, factor, modulus);
            }
        }
        return result;
    }

    static long inverseMod(long value, long modulus) {
        if (modulus <= 1)
            throw new IllegalArgumentException(
                    "inverse requires modulus > 1");
        BigInteger m = BigInteger.valueOf(modulus);
        BigInteger x = BigInteger.valueOf(normalize(value, modulus));
        if (!x.gcd(m).equals(BigInteger.ONE)) {
            throw new ArithmeticException("modular inverse does not exist");
        }
        return x.modInverse(m).longValueExact();
    }

    static BigInteger choose(int n, int k) {
        if (n < 0 || k < 0 || k > n)
            throw new IllegalArgumentException("invalid n,k");
        k = Math.min(k, n-k);
        BigInteger result = BigInteger.ONE;
        for (int i = 1; i <= k; i++) {
            result = result.multiply(BigInteger.valueOf(n-k+i))
                           .divide(BigInteger.valueOf(i));
        }
        return result;
    }

    // INF is reserved for UNREACHABLE, never a valid finite distance.
    static long addFiniteDistance(long distance, long weight) {
        if (distance < 0 || distance >= INF
                || weight < 0 || weight >= INF) {
            throw new IllegalArgumentException(
                    "require 0<=distance,weight<INF");
        }
        if (weight >= INF-distance) {
            throw new ArithmeticException(
                    "finite path reaches reserved INF range");
        }
        return distance + weight;
    }

    static long[] dijkstra(List<List<Edge>> graph, int source) {
        Objects.requireNonNull(graph);
        int n = graph.size();
        if (n == 0 || source < 0 || source >= n)
            throw new IllegalArgumentException("invalid source/graph");
        for (int v = 0; v < n; v++) {
            for (Edge e : graph.get(v)) {
                if (e.to < 0 || e.to >= n
                        || e.weight < 0 || e.weight >= INF) {
                    throw new IllegalArgumentException(
                            "bad destination or nonnegative weight");
                }
            }
        }
        long[] distance = new long[n];
        Arrays.fill(distance, INF);
        distance[source] = 0;
        PriorityQueue<State> pq = new PriorityQueue<>(
                Comparator.comparingLong(State::distance));
        pq.add(new State(source, 0));
        while (!pq.isEmpty()) {
            State top = pq.poll();
            if (top.distance != distance[top.vertex]) continue;
            for (Edge e : graph.get(top.vertex)) {
                long candidate =
                        addFiniteDistance(top.distance, e.weight);
                if (candidate < distance[e.to]) {
                    distance[e.to] = candidate;
                    pq.add(new State(e.to, candidate));
                }
            }
        }
        return distance;
    }

    static List<List<Edge>> newGraph(int n) {
        List<List<Edge>> g = new ArrayList<>();
        for (int i = 0; i < n; i++) g.add(new ArrayList<>());
        return g;
    }

    static void addEdge(
            List<List<Edge>> graph, int from, int to, long weight) {
        graph.get(from).add(new Edge(to, weight));
    }

    // Independent exact-integer Bellman-Ford oracle for small graphs.
    static BigInteger[] exactDistances(
            List<List<Edge>> g, int source) {
        int n = g.size();
        BigInteger[] d = new BigInteger[n];
        d[source] = BigInteger.ZERO;
        for (int pass = 0; pass < n-1; pass++) {
            boolean changed = false;
            for (int v = 0; v < n; v++) {
                if (d[v] == null) continue;
                for (Edge e : g.get(v)) {
                    BigInteger candidate = d[v].add(
                            BigInteger.valueOf(e.weight));
                    if (d[e.to] == null
                            || candidate.compareTo(d[e.to]) < 0) {
                        d[e.to] = candidate;
                        changed = true;
                    }
                }
            }
            if (!changed) break;
        }
        return d;
    }

    static String distancesToString(long[] distances) {
        List<String> values = new ArrayList<>();
        for (long d : distances) {
            values.add(d == INF ? "INF" : Long.toString(d));
        }
        return values.toString();
    }

    static void example() {
        int max = Integer.MAX_VALUE;
        long longMax = Long.MAX_VALUE;
        int squareInput = 50_000;
        long badPromotion = squareInput * squareInput;
        long goodPromotion = (long) squareInput * squareInput;
        System.out.println("int wrap: " + (max + 1)
                + ", long wrap: " + (longMax + 1));
        System.out.println("Promotion: wrong=" + badPromotion
                + ", correct=" + goodPromotion);
        expectFailure(ArithmeticException.class,
                () -> Math.addExact(Integer.MAX_VALUE, 1));
        expectFailure(ArithmeticException.class,
                () -> Math.multiplyExact(Long.MAX_VALUE, 2L));
        expectFailure(ArithmeticException.class,
                () -> Math.negateExact(Long.MIN_VALUE));
        expectFailure(ArithmeticException.class,
                () -> Math.toIntExact((long) Integer.MAX_VALUE + 1));
        System.out.println("Exact arithmetic guards: PASS");

        check((-7L % 5L) == -2L && normalize(-7, 5) == 3,
                "bad modulo normalization");
        System.out.println("Negative modulo: -7%5=" + (-7L % 5L)
                + ", floorMod(-7,5)=" + normalize(-7, 5));
        check(normalize(Long.MIN_VALUE, Long.MAX_VALUE)
                == Long.MAX_VALUE-1, "min long modulo");
        System.out.println("Long.MIN_VALUE mod Long.MAX_VALUE="
                + normalize(Long.MIN_VALUE, Long.MAX_VALUE));

        long modulus = Long.MAX_VALUE;
        check(addMod(modulus-2, modulus-3, modulus)
                == modulus-5, "large modular addition");
        check(multiplyMod(modulus-2, modulus-3, modulus)
                == 6, "large modular multiplication");
        System.out.println("Large mod: add=" + addMod(
                modulus-2, modulus-3, modulus)
                + ", multiply="
                + multiplyMod(modulus-2, modulus-3, modulus));
        System.out.println("powMod(-2,63,1000000007)="
                + powerMod(-2, 63, 1_000_000_007L));
        System.out.println("inverse(3,11)=" + inverseMod(3, 11)
                + ", C(67,33)=" + choose(67, 33));
        expectFailure(ArithmeticException.class,
                () -> inverseMod(6, 9));
        expectFailure(IllegalArgumentException.class,
                () -> normalize(1, 0));
        System.out.println("Inverse existence and invalid modulus: PASS");

        List<List<Edge>> g = newGraph(6);
        addEdge(g, 0, 1, 6);
        addEdge(g, 0, 2, 2);
        addEdge(g, 2, 1, 1);
        addEdge(g, 1, 3, 3);
        addEdge(g, 2, 3, 12);
        addEdge(g, 3, 4, 1);
        long[] distances = dijkstra(g, 0);
        check(Arrays.equals(distances,
                new long[] {0, 3, 2, 6, 7, INF}), "Dijkstra sample");
        System.out.println("Dijkstra from 0: "
                + distancesToString(distances));
        expectFailure(ArithmeticException.class,
                () -> addFiniteDistance(INF-1, 1));
        expectFailure(IllegalArgumentException.class,
                () -> addFiniteDistance(INF, 0));
        System.out.println("Reserved INF range guard: PASS");
    }

    static void randomOracles() {
        SplittableRandom rng = new SplittableRandom(5372026L);
        for (int trial = 0; trial < 2500; trial++) {
            long m = rng.nextLong(1, Long.MAX_VALUE);
            long rawA = rng.nextLong(), rawB = rng.nextLong();
            long a = normalize(rawA, m), b = normalize(rawB, m);
            BigInteger mod = BigInteger.valueOf(m);
            long expectedAdd = BigInteger.valueOf(a)
                    .add(BigInteger.valueOf(b)).mod(mod)
                    .longValueExact();
            long expectedMul = BigInteger.valueOf(a)
                    .multiply(BigInteger.valueOf(b)).mod(mod)
                    .longValueExact();
            check(addMod(a, b, m) == expectedAdd,
                    "addMod differs from BigInteger");
            check(multiplyMod(a, b, m) == expectedMul,
                    "multiplyMod differs from BigInteger");
            if (trial < 700) {
                long exponent = rng.nextLong(0, 1000);
                long expectedPow = BigInteger.valueOf(a)
                        .modPow(BigInteger.valueOf(exponent), mod)
                        .longValueExact();
                check(powerMod(rawA, exponent, m) == expectedPow,
                        "powerMod differs from BigInteger");
            }
        }
        for (int trial = 0; trial < 400; trial++) {
            long m = rng.nextLong(2, 1_000_000L);
            long x = rng.nextLong();
            BigInteger mm = BigInteger.valueOf(m);
            BigInteger xx = BigInteger.valueOf(
                    normalize(x, m));
            if (xx.gcd(mm).equals(BigInteger.ONE)) {
                long inverse = inverseMod(x, m);
                check(multiplyMod(normalize(x, m),
                        inverse, m) == 1, "wrong modular inverse");
            } else {
                final long value = x, modulus = m;
                expectFailure(ArithmeticException.class,
                        () -> inverseMod(value, modulus));
            }
        }
        for (int trial = 0; trial < 350; trial++) {
            int n = rng.nextInt(1, 10);
            List<List<Edge>> g = newGraph(n);
            for (int u = 0; u < n; u++) {
                for (int v = 0; v < n; v++) {
                    if (u != v && rng.nextInt(4) == 0) {
                        addEdge(g, u, v, rng.nextLong(0, 101));
                    }
                }
            }
            int source = rng.nextInt(n);
            long[] actual = dijkstra(g, source);
            BigInteger[] oracle = exactDistances(g, source);
            for (int v = 0; v < n; v++) {
                check(actual[v] == (oracle[v] == null ? INF
                        : oracle[v].longValueExact()),
                        "Dijkstra mismatch with BigInteger oracle");
            }
        }
        System.out.println(
                "Random oracle QA: PASS (2500 mod-add/multiply, "
                + "700 mod-powers, 400 inverse cases, 350 graphs)");
    }

    public static void main(String[] args) {
        example();
        randomOracles();
    }
}
```

### 17.2. Cách biên dịch và chạy

Dùng JDK 17+:

```bash
javac IntegerInfinityModuloDemo.java
java IntegerInfinityModuloDemo
```

**Stdout chính xác của chương trình với seed cố định:**

```text
int wrap: -2147483648, long wrap: -9223372036854775808
Promotion: wrong=-1794967296, correct=2500000000
Exact arithmetic guards: PASS
Negative modulo: -7%5=-2, floorMod(-7,5)=3
Long.MIN_VALUE mod Long.MAX_VALUE=9223372036854775806
Large mod: add=9223372036854775802, multiply=6
powMod(-2,63,1000000007)=708828003
inverse(3,11)=4, C(67,33)=14226520737620288370
Inverse existence and invalid modulus: PASS
Dijkstra from 0: [0, 3, 2, 6, 7, INF]
Reserved INF range guard: PASS
Random oracle QA: PASS (2500 mod-add/multiply, 700 mod-powers, 400 inverse cases, 350 graphs)
```

### 17.3. Phân tích từng dòng kết quả

**`int wrap` và `long wrap`:** Cộng 1 vào giá trị nguyên dương lớn nhất của mỗi kiểu sinh giá trị âm nhỏ nhất theo ngữ nghĩa wrap. Đây là minh chứng Java không tự throw khi dùng phép `+` nguyên thủy.

**`Promotion`:** `50_000*50_000` trong int tràn thành −1.794.967.296 rồi mới được gán vào long; ép một toán hạng lên long **trước phép nhân** trả 2.500.000.000.

**`Exact arithmetic guards`:** Chương trình xác nhận bốn trường hợp overflow/thu hẹp không hợp lệ làm `Math.addExact`, `Math.multiplyExact`, `Math.negateExact` và `Math.toIntExact` báo `ArithmeticException`.

**`Negative modulo`:** Toán tử `%` Java của -7 với 5 trả -2, còn `floorMod` trả 3 chuẩn hóa.

**`Long.MIN_VALUE mod Long.MAX_VALUE`:** Xử lý số âm nhỏ nhất mà không dùng `Math.abs`, trả 9.223.372.036.854.775.806.

**`Large mod`:** Cộng hai phần dư sát modulus lớn nhất không overflow và nhân hai phần dư sát modulus cho ra 6 đúng theo đồng dư (−2)×(−3)=6.

**`powMod`:** Lũy thừa modulo của base âm, số mũ 63 và modulus 1.000.000.007 trả 708.828.003, được tính bằng binary exponentiation và nhân modulo an toàn.

**`inverse` và `C(67,33)`:** Nghịch đảo của 3 modulo 11 là 4. Giá trị tổ hợp vượt long được in chính xác bằng BigInteger.

**`Inverse existence`:** Nghịch đảo của 6 modulo 9 bị từ chối vì gcd≠1. Modulus 0 cũng bị từ chối.

**`Dijkstra`:** Đường đi hữu hạn được in bằng số, đỉnh 5 không thể tới được in ký hiệu INF. Phép cộng đạt/qua miền sentinel được phát hiện và throw.

**`Random oracle QA`:** 2.500 cặp phép cộng/nhân modulo long được so với BigInteger, trong đó 700 trường hợp còn có lũy thừa modulo; 400 trường hợp nghịch đảo có hoặc không tồn tại được kiểm tra theo gcd; 350 đồ thị có trọng số nhỏ so Dijkstra với Bellman–Ford BigInteger. **Đây là kiểm thử tính đúng, không phải bảo đảm xác suất rằng mọi phép toán trên tất cả đầu vào đều đúng chỉ vì test random qua.** Các bất biến/điều kiện đã được trình bày riêng.

## 18. Bất biến và tính đúng của các thành phần

### 18.1. `addMod`

Tiền điều kiện:

```text
m>0, 0<=a,b<m.
```

Nếu `a<m-b`, `a+b<m` và `a+b` không overflow. Nếu `a>=m-b`, kết quả cần là `a+b-m=a-(m-b)`, dùng phép trừ hai số hợp lệ nên không overflow và nằm trong `[0,m)`. Kết quả đồng dư a+b trong cả hai nhánh.

### 18.2. `multiplyMod`

Tại mỗi vòng, giữ quan hệ đồng dư:

```text
result + a*remaining ≡ A*B (mod m).
```

Khi remaining lẻ, cộng a vào result; sau đó chia đôi remaining và nhân đôi a. Các phép cộng dùng `addMod`, kết quả luôn chuẩn hóa. Khi remaining thành 0, result là phần dư tích.

### 18.3. `powerMod`

Tại mỗi vòng:

```text
result * factor^remaining
    ≡ base_original^exponent_original (mod m).
```

Nếu remaining lẻ, nhân factor vào result; sau đó bình phương factor và giảm remaining. Mọi phép nhân dùng `multiplyMod`, không tạo lũy thừa nguyên khổng lồ. Cuối vòng remaining=0, result là phần dư mong muốn.

### 18.4. `addFiniteDistance`

Tiền điều kiện distance và weight không âm, nhỏ hơn INF. Nếu `weight>=INF-distance`, phép cộng không có đại diện hợp lệ `<INF`, nên ném lỗi. Nếu ngược lại, `distance+weight<INF` và vì INF<MAX, phép cộng nằm trong miền long. Như vậy **không nhầm đường đi hữu hạn với unreachable sentinel** trên mọi kết quả trả thành công.

### 18.5. Dijkstra

Mọi cạnh có trọng số không âm và mọi relaxation được biểu diễn chính xác trong miền `<INF` nếu chương trình trả thành công. Khi lấy một đỉnh có khoảng cách nhỏ nhất khỏi priority queue, tính chất nonnegative weights đảm bảo khoảng cách ấy không thể cải thiện bằng một đường đi qua đỉnh chưa xử lý có khoảng cách lớn hơn. Các relaxation an toàn và comparator đúng thứ tự, nên kết quả hữu hạn là shortest distances; các đỉnh không có đường đi vẫn giữ INF.

Một thuật toán đúng trong số học toán học có thể thất bại ở máy nếu không bảo vệ biểu diễn. Do đó chứng minh tính đúng ở đây phải kèm **hợp đồng số học**, không chỉ định lý Dijkstra trừu tượng.

## 19. Các lỗi thường gặp

1. Dùng `int` cho tổng mà cận lớn nhất có thể vượt 2.147.483.647.
2. Nghĩ phép cộng int/long overflow trong Java tự ném exception.
3. Viết `long answer=intA*intB` rồi tin không overflow.
4. Ép kết quả sau khi phép nhân đã tràn thay vì ép toán hạng trước.
5. Dùng long nhưng không tính trường hợp tích hai long vẫn vượt miền.
6. Dùng `Math.abs(Long.MIN_VALUE)` rồi tin kết quả không âm.
7. Dùng dấu `-` để đảo `Long.MIN_VALUE` mà không xử lý overflow.
8. Tưởng `longValue()` của BigInteger luôn giữ đúng giá trị.
9. Dùng `(int)largeLong` mà không kiểm tra phạm vi cần thiết.
10. Dùng `Math.pow` double để tính số nguyên lớn chính xác.
11. Dùng `double` để biểu diễn chính xác mọi số nguyên 64-bit.
12. Coi `Double.POSITIVE_INFINITY` giống hệt một sentinel long.
13. Không kiểm tra NaN khi tính toán số thực có comparators.
14. Dùng `Long.MAX_VALUE` làm INF rồi cộng trọng số trực tiếp.
15. Chọn `INF=Long.MAX_VALUE/4` rồi cho rằng mọi phép cộng đều an toàn.
16. Relax một cạnh từ trạng thái unreachable mà không kiểm tra.
17. Cho phép kết quả hữu hạn đúng bằng INF nhưng lại dùng INF nghĩa unreachable.
18. Dùng `Math.min(INF,dist+w)` khi `dist+w` có thể tràn trước.
19. Bão hòa kết quả về INF rồi mặc định trả lời shortest path chính xác.
20. Dùng -1 cho unreachable khi -1 có thể là đáp án hợp lệ.
21. Dùng Dijkstra cho trọng số âm vì tin kiểu long rộng đủ.
22. Dùng comparator `(int)(a.distance-b.distance)` cho long.
23. Dùng `a-b` comparator int có thể overflow.
24. Không bỏ stale entries của Dijkstra lazy queue.
25. Nhầm INF dành riêng với khoảng cách hữu hạn rất lớn.
26. Không tính đường đi ứng viên vượt INF dù đường tối ưu có thể vẫn nhỏ.
27. Không kiểm thử đồ thị rời rạc hoặc đỉnh không thể tới.
28. Dùng phần dư Java `%` và tin kết quả với số âm luôn không âm.
29. Dùng `Math.abs(x)%m` để chuẩn hóa modulo, hỏng với MIN_VALUE.
30. Viết `((x%m)+m)%m` mà không xét overflow khi m sát MAX.
31. Để modulus bằng 0 hoặc âm mà không kiểm tra hợp đồng.
32. Quên `x mod 1=0`.
33. Viết `(a+b)%m` với a,b gần long MAX mà không xử lý overflow.
34. Viết `(a*b)%m` dù a*b vượt long.
35. Đổi `%` sang `remainderUnsigned` sau tích long đã tràn rồi tưởng đúng.
36. Dùng cộng modulo với a,b chưa chuẩn hóa nhưng bỏ kiểm tra đầu vào.
37. Viết binary multiplication mà không giữ invariant đồng dư.
38. Dùng `Math.pow` để tính `a^b mod m`.
39. Quên `a^0 mod m=1 mod m`.
40. Bỏ chuẩn hóa base âm trước lũy thừa modulo.
41. Cho rằng mọi số khác 0 đều có nghịch đảo modulo m.
42. Chia hai phần dư modulo như phép chia số nguyên thông thường.
43. Dùng Fermat `a^(m-2)` khi m không được chứng minh nguyên tố.
44. Dùng nghịch đảo modulo cho a chia hết m.
45. Coi `waysMod==0` là chứng minh có đúng 0 cách thật.
46. Coi phần dư modulo là số cách chính xác thay vì kết quả đã rút gọn.
47. Tính tổ hợp bằng long mà không kiểm tra cận.
48. Bỏ exception trong `Math.addExact` rồi thay bằng một giá trị 0 giả.
49. Dùng chính hàm modular multiplication làm oracle kiểm tra nó.
50. Không thử số sát MIN/MAX, modulus=1 và khóa/đỉnh không thể tới.
51. Chỉ kiểm thử số dương nhỏ nên bỏ lọt overflow âm/dương.
52. Nhầm một test random thành chứng minh toàn bộ miền long.
53. Không phân biệt lỗi đầu vào vượt hợp đồng với lỗi thuật toán.
54. Tối ưu sang bit tricks mà chưa chứng minh phép toán giữ được phần dư.
55. Viết lại biểu thức toán học tương đương nhưng không xét overflow của **trung gian**.
56. Không tính chi phí BigInteger trong phân tích bộ nhớ/thời gian.
57. Giữ INF ở mảng long nhưng in giá trị thô như khoảng cách thật.
58. Không ghi rõ modulus là dương và phần dư thuộc `[0,m)`.
59. Dùng phép cộng dồn của `Arrays.stream(int[]).sum()` mà không biết trả int.
60. Quên thử `Long.MIN_VALUE / -1` và phân biệt overflow chia với chia cho 0.

## 20. Bài tập tự luyện kèm đáp án

**Bài 1.** Miền giá trị của int trong Java?

**Đáp án:** `[-2^31,2^31-1]`, tức −2.147.483.648 đến 2.147.483.647.

**Bài 2.** `Integer.MAX_VALUE + 1` cho kết quả gì khi dùng phép cộng int nguyên thủy?

**Đáp án:** `Integer.MIN_VALUE`, tức −2.147.483.648.

**Bài 3.** `Long.MAX_VALUE+1` kết quả gì?

**Đáp án:** `Long.MIN_VALUE` khi wrap.

**Bài 4.** `int a=50000,b=50000; long x=a*b;` kết quả?

**Đáp án:** −1.794.967.296, vì phép nhân được tính bằng int trước.

**Bài 5.** Sửa bài 4 để có tích chính xác?

**Đáp án:** `long x=(long)a*b`, cho 2.500.000.000.

**Bài 6.** `Math.addExact(Integer.MAX_VALUE,1)` cho kết quả?

**Đáp án:** Ném `ArithmeticException`, không trả số int wrap.

**Bài 7.** `Math.negateExact(Long.MIN_VALUE)`?

**Đáp án:** Ném `ArithmeticException`, vì giá trị đối dấu không vừa long.

**Bài 8.** `Math.abs(Long.MIN_VALUE)` là số dương không?

**Đáp án:** Không; nó vẫn là Long.MIN_VALUE do giới hạn biểu diễn.

**Bài 9.** Vì sao `BigInteger.longValue()` không phải phép chuyển chính xác được kiểm chứng?

**Đáp án:** Nó có thể chỉ giữ 64 bit thấp; dùng `longValueExact()` khi bắt buộc không mất dữ liệu.

**Bài 10.** `C(67,33)` có vừa long signed không?

**Đáp án:** Không; 14.226.520.737.620.288.370 > Long.MAX_VALUE.

**Bài 11.** Tại sao dùng `INF=Long.MAX_VALUE` rồi cộng trọng số có thể sai?

**Đáp án:** Vì INF là sentinel, phép cộng có thể tràn thành âm và làm sai relaxation.

**Bài 12.** Trong demo, INF bằng bao nhiêu?

**Đáp án:** `Long.MAX_VALUE/4=2305843009213693951`.

**Bài 13.** Vì sao đường đi hữu hạn bằng INF không được mã demo chấp nhận?

**Đáp án:** Vì INF đã được dành riêng cho unreachable, hai trạng thái không thể cùng dùng một giá trị.

**Bài 14.** `addFiniteDistance(INF-1,1)` làm gì?

**Đáp án:** Ném `ArithmeticException`, vì tổng đạt sentinel dành riêng.

**Bài 15.** Một đỉnh unreachable trong ví dụ Dijkstra được in gì?

**Đáp án:** Ký hiệu `INF`.

**Bài 16.** Đường đi tốt nhất 0→2→1 trong ví dụ dài bao nhiêu?

**Đáp án:** 2+1=3.

**Bài 17.** Dijkstra có áp dụng cho cạnh trọng số âm không?

**Đáp án:** Không trong trường hợp tổng quát; cần thuật toán phù hợp như Bellman–Ford.

**Bài 18.** Vì sao comparator dựa trên `a-b` nguy hiểm?

**Đáp án:** Phép trừ có thể overflow và sai thứ tự; dùng `Integer.compare`/`Long.compare`.

**Bài 19.** `-7 % 5` trong Java là bao nhiêu?

**Đáp án:** −2.

**Bài 20.** `Math.floorMod(-7,5)` là bao nhiêu?

**Đáp án:** 3.

**Bài 21.** `Math.floorMod(Long.MIN_VALUE, Long.MAX_VALUE)` là bao nhiêu?

**Đáp án:** `9223372036854775806`.

**Bài 22.** Modulo 1 của mọi x là bao nhiêu?

**Đáp án:** 0.

**Bài 23.** `(a+b)%m` có thể overflow không nếu `0<=a,b<m`?

**Đáp án:** Có, vì a+b có thể gần 2m khi m lớn.

**Bài 24.** Cho m=10, a=8, b=7. `addMod` trả gì?

**Đáp án:** 5; `8+7=15`, phần dư 5.

**Bài 25.** Cho m=10, a=1, b=7, nhánh nào của `addMod` được dùng?

**Đáp án:** `room=10-7=3`, `a=1<3`, nên trả `a+b=8`.

**Bài 26.** Cho m=Long.MAX_VALUE, a=m−2, b=m−3. Tổng modulo?

**Đáp án:** `m−5=9223372036854775802`.

**Bài 27.** Cùng a,b của bài 26, tích modulo?

**Đáp án:** `(-2)*(-3) mod m = 6`.

**Bài 28.** Nhân modulo nhị phân có bao nhiêu vòng theo b?

**Đáp án:** O(log b) vòng nếu b>0, dùng cộng modulo an toàn.

**Bài 29.** `powerMod(7,0,13)` bằng bao nhiêu?

**Đáp án:** `1 mod 13=1`.

**Bài 30.** `powerMod(7,0,1)` bằng bao nhiêu?

**Đáp án:** 0 vì mọi số modulo 1 đều 0.

**Bài 31.** Tại sao không dùng Math.pow cho lũy thừa modulo lớn?

**Đáp án:** Math.pow trả double có sai số và có thể Infinity; cần lũy thừa modulo bằng số nguyên.

**Bài 32.** `inverse(3,11)` là bao nhiêu?

**Đáp án:** 4, vì 3×4≡1 mod 11.

**Bài 33.** `inverse(6,9)` có tồn tại không?

**Đáp án:** Không, vì gcd(6,9)=3.

**Bài 34.** Điều kiện để a có nghịch đảo modulo m>1?

**Đáp án:** `gcd(a,m)=1`.

**Bài 35.** Có thể tính nghịch đảo bằng `a^(m−2)` với m=9 không?

**Đáp án:** Không thể dùng công thức Fermat một cách tổng quát vì 9 không nguyên tố.

**Bài 36.** Khi phép đếm modulo cho phần dư 0, số cách thật có bắt buộc bằng 0 không?

**Đáp án:** Không; số cách có thể là một bội dương của modulus.

**Bài 37.** Vì sao cần oracle BigInteger cho modular multiplication?

**Đáp án:** Để tính tích chính xác mà không dùng cùng thuật toán cộng nhị phân, phát hiện lỗi trung gian/modulo.

**Bài 38.** Bộ kiểm thử chương trình so bao nhiêu phép cộng/nhân modulo?

**Đáp án:** 2.500 trường hợp cặp cộng và nhân, cùng oracle BigInteger.

**Bài 39.** Bộ kiểm thử có bao nhiêu đồ thị Dijkstra?

**Đáp án:** 350 đồ thị ngẫu nhiên nhỏ, đối chiếu Bellman–Ford BigInteger.

**Bài 40.** Hãy nêu ba bảo đảm quan trọng khi dùng INF trong shortest path.

**Đáp án:** Không relax từ unreachable; mọi khoảng cách hữu hạn biểu diễn được và **khác** INF; mọi phép cộng khoảng cách được kiểm tra trước khi vượt miền/sentinel.

**Bài 41.** `long s=(long)Integer.MAX_VALUE+Integer.MAX_VALUE` có tràn không?

**Đáp án:** Không; giá trị 4.294.967.294 vừa long.

**Bài 42.** `long s=Integer.MAX_VALUE+Integer.MAX_VALUE` có đúng không?

**Đáp án:** Không; phép cộng hai int tràn trước, cho -2 rồi mới gán long.

**Bài 43.** Một phép cộng trung gian bị tràn nhưng tổng cuối toán học vừa long, `Math.addExact` có thể throw không?

**Đáp án:** Có; phải tính số trung gian chính xác bằng BigInteger hoặc thiết kế lại thứ tự với chứng minh.

**Bài 44.** Dùng `Long.remainderUnsigned(a*b,m)` có sửa được tích tràn long không?

**Đáp án:** Không; những bit cao của tích toán học đã mất khi tính a*b.

**Bài 45.** Mối nguy khi dùng `Math.abs(x)%m` trên x=Long.MIN_VALUE?

**Đáp án:** Math.abs vẫn âm, không cho phần dư chuẩn hóa như kỳ vọng.

## 21. Checklist kiểm thử và đưa vào production

- [ ] Có bảng giới hạn `int`/`long` của biến đầu vào và kết quả?
- [ ] Mọi phép cộng/nhân với khả năng overflow đã dùng `Exact`, guard hoặc BigInteger?
- [ ] Đã ép sang kiểu rộng **trước** khi đánh giá biểu thức?
- [ ] Không chuyển BigInteger sang long bằng `.longValue()` khi cần chính xác?
- [ ] Đã kiểm tra `Integer.MIN_VALUE`, `Long.MIN_VALUE`, `MAX_VALUE` và số âm?
- [ ] Có phân biệt overflow là chủ ý của bit hash và overflow là lỗi của kết quả toán học?
- [ ] Nếu dùng INF, đã định nghĩa rõ trạng thái và cận **hữu hạn `<INF`**?
- [ ] Có kiểm tra `dist[u]!=INF` trước relax?
- [ ] Có phát hiện tổng đường đi đạt/vượt sentinel trước khi cộng?
- [ ] Có xét đồ thị rời rạc, cạnh trọng số 0, nhiều cạnh song song và cạnh âm?
- [ ] Comparator đã dùng `Long.compare` thay phép trừ?
- [ ] Modulus luôn dương, và phép nghịch đảo chỉ dùng với m>1?
- [ ] Số âm được chuẩn hóa bằng `Math.floorMod` hoặc công thức có chứng minh?
- [ ] Mọi phần dư đầu vào cho `addMod`/`multiplyMod` đều nằm `[0,m)`?
- [ ] Không dùng `(a+b)%m` hoặc `(a*b)%m` trực tiếp khi a,b,m sát long MAX?
- [ ] `powMod` kiểm tra số mũ âm và xử lý exponent=0, modulus=1?
- [ ] Nếu chia modulo, đã kiểm tra gcd=1 hoặc bài toán đồng dư riêng?
- [ ] Nếu dùng Fermat, đã biết m nguyên tố và a không chia hết m?
- [ ] Bộ test có số sát MIN/MAX, modulo 1, modulo lớn, số âm và kết quả 0?
- [ ] Có oracle **độc lập** BigInteger và brute force/Bellman–Ford cho trường hợp nhỏ?
- [ ] Đã phân biệt đáp án modulo với giá trị chính xác hoặc reachability?
- [ ] Những giới hạn của sentinel/kiểu số được trình bày rõ để caller biết khi nào throw?
- [ ] Có test các trường hợp lỗi mong đợi, không chỉ happy path?
- [ ] Có tách benchmark hiệu năng khỏi kiểm thử tính đúng?

## Kết luận

Ba tư tưởng chính của **Tràn số nguyên, giá trị vô cực và tính toán modulo**:

1. **Kiểu nguyên thủy không phải số nguyên vô hạn.** Java int/long cộng/nhân có thể wrap; gán vào long quá muộn không cứu được phép nhân int đã tràn. Dùng giới hạn dữ liệu, `Math.*Exact` hoặc `BigInteger` tùy hợp đồng bài toán.
2. **INF là trạng thái đặc biệt, không phải khoảng cách lớn để cộng tùy ý.** Dijkstra/DP cần phân biệt unreachable với mọi giá trị hữu hạn, dùng guard trước cộng, comparator đúng kiểu và từ chối các giá trị nằm ngoài miền đã cam kết.
3. **Modulo phải giữ chuẩn hóa và tránh overflow trung gian.** `%` với số âm trong Java không luôn dương; `(a+b)%m`, `(a*b)%m` có thể sai với long lớn. Hãy dùng `floorMod`, cộng modulo có guard, nhân nhị phân/BigInteger, lũy thừa nhanh và kiểm tra gcd khi tính nghịch đảo.

Các phương pháp này quan trọng không chỉ cho một bài toán cụ thể mà cho **mọi thuật toán có chi phí, số lượng, khoảng cách hoặc phép đếm lớn**. Kiểm thử với các biên và oracle độc lập là cách thực hành giúp phát hiện những lỗi số học vốn hiếm khi xuất hiện trên dữ liệu ví dụ nhỏ.
