# Kiểm soát tràn số, giá trị vô cực và sai số trọng số

Trong các thuật toán **đường đi ngắn nhất** (*shortest paths*), công thức chuyển trạng thái thường rất ngắn:

```text
newDistance = dist[u] + weight(u, v)

nếu newDistance < dist[v]:
    dist[v] = newDistance
```

Nhưng chỉ một sai sót về **kiểu số**, **đại diện của “chưa tới được”**, **cộng vào giá trị vô cực**, **dấu của trọng số** hoặc **sai số số thực** cũng có thể khiến một thuật toán đúng về mặt ý tưởng trả lời sai. Đặc biệt, phép cộng bị tràn có thể biến khoảng cách dương rất lớn thành số âm; bộ giải khi đó “tìm thấy” một đường đi rẻ hơn không tồn tại.

Bài này hướng dẫn cách thiết kế số học **an toàn và có hợp đồng rõ ràng** khi cài đặt Dijkstra, Bellman–Ford, Floyd–Warshall và các biến thể tìm đường tối ưu bằng **Java 17+**.

Nội dung chính:

1. Phân biệt **không tới được**, **khoảng cách bằng 0**, **khoảng cách rất lớn** và **không có giá trị nhỏ nhất hữu hạn do chu trình âm**.
2. Hiểu tràn số nguyên ở `int`/`long` và vì sao “đổi tất cả thành long” chưa phải bảo đảm tuyệt đối.
3. Chọn giữa **sentinel INF có chứng minh cận trên**, **boolean reachable + long**, **Math.addExact**, và **BigInteger**.
4. Chỉ cộng hai khoảng cách khi hai trạng thái thực sự tới được; không nhầm `Long.MAX_VALUE` với một đường đi có trọng số hợp lệ bằng chính số ấy.
5. Xử lý **trọng số âm, chu trình âm và số thực double** theo đúng giả thiết của thuật toán.
6. Dùng chương trình Java hoàn chỉnh có **Dijkstra long, Dijkstra BigInteger, Bellman–Ford và Floyd–Warshall**, trường hợp biên, output xác định và các phép kiểm chứng cụ thể.

**Thông điệp cốt lõi:** Tính đúng của thuật toán đồ thị phụ thuộc không chỉ vào việc duyệt đỉnh/cạnh, mà còn vào việc **biểu diễn giá trị và kiểm soát mọi phép tính so sánh, cộng, khởi tạo, phát hiện lỗi**.

## 1. Các giá trị “đặc biệt” phải phân biệt

Với nguồn s, câu hỏi là đường đi ngắn nhất từ s tới v. Có ít nhất bốn trạng thái khác nhau:

| Trạng thái | Ý nghĩa | Cách hiển thị rõ ràng |
| --- | --- | --- |
| **Tới được, khoảng cách hữu hạn** | Có đường đi hợp lệ, có giá trị nhỏ nhất hữu hạn | Một số nguyên/thập phân, kể cả 0 hoặc rất lớn |
| **Không tới được** | Không có đường đi từ s tới v | `INF` hoặc `UNREACHABLE` |
| **Không bị chặn dưới bởi giá trị hữu hạn** | Có chu trình tổng trọng số âm nằm trên một đường đi từ s tới v; đi thêm vòng làm chi phí giảm vô hạn | `-INF` hoặc `NEGATIVE_INFINITY` |
| **Lỗi miền biểu diễn** | Giá trị toán học vượt khả năng lưu trữ của kiểu số, hoặc input không hợp lệ | Ngoại lệ/kiểu số lớn hơn, **không** báo “không tới được” |

Ví dụ:

- Có đường 0→1 trọng số **0**: dist[1]=0, **không phải** unreachable.
- Không có đường từ 0 tới 2: dist[2]=INF theo nghĩa **trạng thái không tới được**, không phải một giá trị số hữu hạn.
- Có cung 0→1 trọng số đúng bằng `Long.MAX_VALUE`: đỉnh 1 **tới được**, mặc dù khoảng cách trùng với sentinel phổ biến trong nhiều bản code.
- Có đường tới một chu trình âm rồi từ chu trình đi tiếp tới v: không có khoảng cách ngắn nhất hữu hạn cho v; có thể làm chi phí nhỏ tùy ý bằng cách lặp chu trình.
- Có tổng chi phí toán học là `Long.MAX_VALUE + 10`: cần **BigInteger** hoặc báo lỗi miền số, không được âm thầm chuyển thành số âm.

**INF là khái niệm logic**, không nhất thiết là một số nguyên cụ thể. Việc chọn giá trị đại diện INF quyết định rất nhiều điều kiện biên của code.

## 2. Tràn số nguyên trong Java

Các giới hạn quan trọng:

| Kiểu | Số bit | Miền giá trị |
| --- | ---: | --- |
| `int` | 32 | −2.147.483.648 đến 2.147.483.647 |
| `long` | 64 | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |
| `BigInteger` | Độ dài động | Số nguyên có độ lớn phụ thuộc bộ nhớ, không giới hạn 64 bit |

Java sử dụng phép toán số nguyên hai bù với kết quả **wraparound** đối với phép cộng/trừ/nhân thông thường của `int` và `long`; nó **không tự ném ngoại lệ** khi tràn số trong các biểu thức này.

Ví dụ:

```java
int a = 2_000_000_000;
int b = 2_000_000_000;

System.out.println(a + b);          // -294967296 (đã tràn)
System.out.println((long) a + b);   // 4000000000 (đúng)
```

Hai cạnh có trọng số 2 tỷ cho tổng 4 tỷ. Nếu lưu bằng int, kết quả âm khiến bước relax trong Dijkstra tưởng đường mới **ngắn hơn mọi đường dương**, một lỗi logic nghiêm trọng.

### 2.1. Đổi sang long trước phép cộng

```java
int w1 = 2_000_000_000;
int w2 = 2_000_000_000;

long correct = (long) w1 + w2;
```

Nhưng:

```java
long stillWrong = w1 + w2;
```

ở dòng sau, `w1+w2` được tính **bằng int trước**, bị tràn rồi mới chuyển sang long. Ép kiểu hoặc dùng long **trước khi tính** mới tránh tràn trung gian.

**Quy tắc:** Kiểu của biến nhận không tự quyết định kiểu của phép cộng đã hoàn thành trong vế phải.

### 2.2. Long vẫn có thể tràn

```java
long nearMax = Long.MAX_VALUE - 3;
long result = nearMax + 10; // wraparound, sai giá trị toán học
```

Không được suy luận rằng một bài n≤100.000 thì tổng đường đi chắc chắn nằm trong long; cần cả **cận trên của trọng số mỗi cạnh**. Nếu một đường đơn có tối đa n−1 cạnh, mỗi trọng số không âm ≤W, cận trên đơn giản của chi phí đường đơn là:

```text
(n - 1) * W
```

Phép nhân kiểm tra cận cũng cần được thực hiện bằng kiểu không tràn, ví dụ BigInteger hoặc kiểm tra trước phép nhân. Nếu `(n−1)×W≤Long.MAX_VALUE` và thuật toán chỉ cộng những đoạn đường đơn không âm, long là lựa chọn hợp lý.

Trong đồ thị có **trọng số âm hoặc chu trình**, phân tích giới hạn có thể phức tạp hơn; không nên dùng cận “đường đơn không quá n−1 cạnh” để khẳng định mọi **giá trị trung gian** của một triển khai luôn vừa long khi chương trình vẫn có thể duyệt những walk không đơn.

## 3. Ba cách thiết kế khoảng cách và INF

### 3.1. Sentinel INF hữu hạn

Nhiều chương trình dùng:

```java
final long INF = Long.MAX_VALUE / 4;
long[] dist = new long[n];
Arrays.fill(dist, INF);
dist[source] = 0;
```

Ưu điểm: đơn giản, ít trạng thái, thuận tiện trong bài có cận trọng số rõ.

Nhưng phải có hợp đồng:

> Mọi khoảng cách hữu hạn và mọi phép cộng trung gian cần xử lý đúng trong thuật toán đều được chứng minh **nhỏ hơn INF** và nằm trong miền kiểu số.

Nếu có đường thật chi phí bằng INF, biểu thức:

```java
if (candidate < dist[v]) { ... }
```

không thể cập nhật dist[v] từ INF sang candidate=INF, nên sẽ **báo không tới được sai**.

Dùng `Long.MAX_VALUE/4` chỉ để giảm nguy cơ cộng tràn **không tự chứng minh rằng mọi đường đi nhỏ hơn ngưỡng ấy**.

### 3.2. Dùng Long.MAX_VALUE làm INF

```java
long INF = Long.MAX_VALUE;
```

Rủi ro kép:

1. Nếu khoảng cách thật **đúng bằng Long.MAX_VALUE**, không thể phân biệt với “không có đường”.
2. Với `dist[u]=INF`, phép `dist[u]+w` khi w>0 sẽ tràn và có thể biến thành số âm.

Kiểm tra:

```java
if (dist[u] == INF) {
    continue;
}
```

chặn được phép cộng từ một **đỉnh không tới được** theo hợp đồng sentinel, nhưng vẫn **không giải quyết** xung đột với một khoảng cách hữu hạn đúng bằng INF.

Vì vậy, nếu dùng sentinel, phải nêu rõ **mọi khoảng cách hợp lệ nhỏ hơn INF**. Không có giả thiết ấy thì nên dùng một trạng thái tách biệt.

### 3.3. Tách trạng thái reachable khỏi số long

Đây là lựa chọn an toàn khi muốn **cho phép khoảng cách bằng Long.MAX_VALUE**:

```java
boolean[] reachable = new boolean[n];
long[] dist = new long[n];

reachable[source] = true;
dist[source] = 0;

if (!reachable[v] || candidate < dist[v]) {
    reachable[v] = true;
    dist[v] = candidate;
}
```

Khi `reachable[v]=false`, giá trị số hiện có trong `dist[v]` **không có ý nghĩa** và không được so sánh như một khoảng cách thật. Khi true, dist[v] là một khoảng cách biểu diễn bằng long, kể cả Long.MAX_VALUE.

**Chú ý:** Tách reachable giúp tránh **xung đột sentinel**, **không tự ngăn tràn phép cộng**. Khi tổng mới vượt long, vẫn cần Math.addExact, BigInteger hoặc một hợp đồng kiểm tra khác.

### 3.4. Dùng OptionalLong, null hoặc kiểu dữ liệu riêng

Nếu có ít trạng thái, có thể dùng `OptionalLong`, hoặc dùng `Long[]` và `null` cho unreachable. Trong đồ thị nhiều đỉnh, mảng primitive `boolean[] + long[]` thường tiết kiệm phân bổ đối tượng và dễ kiểm soát hơn.

Một kết quả chứa **reachable / finite / negativeInfinity** bằng các trường riêng giúp phân biệt rõ ba trạng thái toán học. Không nên gán cùng một số âm để đại diện đồng thời “không tới được”, “chu trình âm” và “cạnh âm”.

## 4. Phép cộng chính xác và chính sách khi vượt long

Java cung cấp:

```java
long candidate = Math.addExact(dist[u], weight);
```

Nếu phép cộng toán học không biểu diễn được trong long, `Math.addExact` ném `ArithmeticException` với thông điệp như `long overflow`.

Có ba chính sách thường gặp:

1. **Fail fast:** Dừng và báo rằng bài toán vượt giới hạn biểu diễn đã chọn. Phù hợp khi input cần thỏa một hợp đồng số cụ thể, hoặc khi kết quả sai âm thầm là không thể chấp nhận.
2. **BigInteger:** Lưu mọi giá trị khoảng cách bằng số nguyên có độ dài động. Phù hợp khi tổng chi phí có thể thực sự lớn hơn long và cần đáp án chính xác.
3. **Chặn (saturate) có chứng minh:** Chỉ dùng khi bài toán định nghĩa ngưỡng cắt và chứng minh mọi giá trị ≥ngưỡng tương đương cho mục tiêu. Không được tùy tiện gộp một khoảng cách hữu hạn với trạng thái unreachable.

Ví dụ kiểm tra trước cộng hai số **không âm**:

```java
if (a > Long.MAX_VALUE - b) {
    throw new ArithmeticException("long overflow");
}
long sum = a + b;
```

Điều kiện này giả định `a,b≥0`. Với trọng số âm, cần kiểm tra cả cận dưới `Long.MIN_VALUE`; dùng `Math.addExact` đơn giản và ít sai hơn.

### 4.1. Fail fast có nghĩa gì?

Một bản Dijkstra dùng Math.addExact có thể ném ngoại lệ khi gặp **một đường đi ứng viên** quá lớn, dù vẫn tồn tại một đường đi ngắn nhất khác nhỏ hơn long. Vì chương trình chưa được thiết kế để bỏ qua ứng viên vượt miền hoặc dùng kiểu số lớn, fail-fast là một **chính sách có chủ ý**: nó không đưa ra một đáp án sai có vẻ hợp lệ.

Nếu yêu cầu “phải trả đáp án chính xác cho mọi input có trọng số nguyên lớn”, hãy sử dụng BigInteger (hoặc một cách biểu diễn được chứng minh đủ miền), thay vì ngầm cho rằng việc kết thúc với ngoại lệ là một lời giải đầy đủ.

### 4.2. Khi nào có thể bỏ qua đường ứng viên quá lớn?

Với Dijkstra có trọng số **không âm**, nếu đích đã có một khoảng cách hữu hạn trong long nhỏ hơn giá trị ứng viên vượt Long.MAX_VALUE, đường ứng viên ấy không thể cải thiện đích. Trong một triển khai được chứng minh riêng, có thể xử lý overflow như “ứng viên không cải thiện” khi **đã biết** đáp án đích hữu hạn đủ nhỏ.

Tuy vậy, nếu một đỉnh chỉ có các đường đi vượt long mà bài đòi biểu diễn đường đi thực, im lặng bỏ ứng viên rồi báo unreachable là **sai**. Chính sách này phải thể hiện rõ việc **không biết** kết quả vì vượt miền; không được lẫn với không có đường.

## 5. Kiểm soát INF ở các thuật toán phổ biến

### 5.1. Dijkstra

Dijkstra yêu cầu các cạnh có **trọng số không âm** để việc chốt đỉnh có khoảng cách tạm thời nhỏ nhất là hợp lệ.

Mẫu đúng khi dùng sentinel có cận:

```java
if (dist[u] == INF) {
    continue; // không cộng từ trạng thái unreachable
}

long cand = Math.addExact(dist[u], weight);
if (cand < dist[v]) {
    dist[v] = cand;
}
```

Mẫu dùng reachable + long:

```java
if (!reachable[u]) {
    continue;
}

long cand = Math.addExact(dist[u], weight);
if (!reachable[v] || cand < dist[v]) {
    reachable[v] = true;
    dist[v] = cand;
}
```

Nếu dùng PriorityQueue của Java, **không so hai khoảng cách bằng phép trừ ép int**:

```java
// SAI: có thể tràn hoặc mất thứ tự.
(a, b) -> (int) (a.distance() - b.distance())

// ĐÚNG: so sánh trực tiếp giá trị long.
Comparator.comparingLong(State::distance)
```

Comparator sai có thể lấy một đỉnh có khoảng cách rất lớn trước một đỉnh nhỏ, phá tính đúng của biến thể Dijkstra có mảng settled/finalized. Trường hợp dùng hàng đợi có bản ghi cũ (*stale entries*), cần kiểm tra bản ghi đang lấy có khớp khoảng cách hiện hành trước khi relax.

**Cung âm:** Không được sửa một Dijkstra sai số bằng cách tăng INF hay đổi int thành long; nếu có cung âm, giả thiết thuật toán đã sai. Chọn Bellman–Ford, Johnson hoặc một thuật toán hỗ trợ trọng số âm đúng mô hình.

### 5.2. Bellman–Ford

Bellman–Ford hỗ trợ trọng số âm và phát hiện **chu trình âm tới được từ nguồn**. Với sentinel:

```java
for (Edge e : edges) {
    if (dist[e.from] == INF) {
        continue;
    }

    long cand = Math.addExact(
            dist[e.from], e.weight);
    if (cand < dist[e.to]) {
        dist[e.to] = cand;
    }
}
```

**Lỗi nổi bật:** Bỏ điều kiện `dist[from] != INF`, rồi cộng INF với một cạnh trọng số âm, ví dụ INF−5. Số đó nhỏ hơn INF và khiến một đỉnh **không tới được** bị gán một khoảng cách hữu hạn giả.

Sau tối đa n−1 lượt relax, có thể duyệt thêm một lượt để tìm cạnh vẫn còn giảm được khoảng cách từ một đỉnh tới được. Đây là dấu hiệu có một **chu trình âm tới được từ nguồn**. Các đỉnh đi tới được **từ những đỉnh bị ảnh hưởng** cũng có khoảng cách ngắn nhất không bị chặn dưới (−∞).

Không nên đánh dấu toàn bộ các đỉnh của đồ thị là −∞ chỉ vì có một chu trình âm ở đâu đó. Nếu chu trình âm **không tới được từ nguồn**, nó không ảnh hưởng đường đi đơn nguồn ấy. Nếu chu trình tới được nhưng không thể đi tiếp tới đích t, nó cũng không làm dist[s→t] trở thành −∞.

**Math.addExact ở Bellman–Ford:** Trọng số có thể âm, phép cộng có thể tràn ở cả hai đầu miền long; fail-fast hoặc BigInteger đều là chính sách cần lựa chọn rõ.

### 5.3. Floyd–Warshall

Floyd–Warshall tính đường đi ngắn nhất giữa **mọi cặp đỉnh** bằng công thức:

```text
dist[i][j] =
    min(dist[i][j], dist[i][k] + dist[k][j])
```

Điều kiện **bắt buộc** trước khi cộng:

```text
cặp (i,k) phải tới được
VÀ
cặp (k,j) phải tới được.
```

Mẫu với INF sentinel:

```java
if (dist[i][k] != INF && dist[k][j] != INF) {
    long cand = Math.addExact(
            dist[i][k], dist[k][j]);

    if (cand < dist[i][j]) {
        dist[i][j] = cand;
    }
}
```

Trong đồ thị có trọng số âm, thiếu guard khiến `INF + (-7)` nhỏ hơn INF và tạo một đường đi **không có thật**. Khi trọng số dương lớn, `INF + w` còn có thể tràn số. Guard là điều kiện logic, **không chỉ là mẹo chống tràn**.

Floyd–Warshall có thể dùng `boolean[][] reachable` và `long[][] dist` để tránh va chạm sentinel, như chương trình Java phía dưới.

**Chu trình âm:** Nếu sau thuật toán tồn tại `dist[v][v] < 0`, đồ thị có chu trình âm. Nhưng điều đó **không có nghĩa mọi cặp (i,j) đều có khoảng cách −∞**. Một cặp (i,j) bị ảnh hưởng nếu tồn tại đỉnh k trên một chu trình âm sao cho `i tới được k` và `k tới được j`. Khi ấy có thể đi lặp chu trình âm để giảm chi phí tùy ý.

Nếu muốn trả khoảng cách chính xác của từng cặp trên đồ thị có chu trình âm, cần **đánh dấu riêng những cặp bị ảnh hưởng**; bảng dist cuối thông thường chưa phải đáp án hữu hạn đúng cho các cặp ấy.

## 6. Lưu ý về trọng số âm và chu trình âm

| Thuật toán | Cạnh âm? | Chu trình âm? | Lưu ý số học |
| --- | --- | --- | --- |
| **BFS** | Chỉ dùng trực tiếp cho cạnh đồng trọng số, thường 1 | Không xét theo mô hình trọng số tùy ý | Khoảng cách theo số cạnh; đếm lớp có thể dùng int/long |
| **0–1 BFS** | Chỉ trọng số **0 hoặc 1** | Không có cạnh âm | Chú ý phân biệt cạnh 0 và không có cạnh |
| **Dijkstra** | **Không** trong giả thiết chuẩn | Không thể có chu trình âm nếu tất cả trọng số không âm | Trọng số và phép cộng phải vừa miền số |
| **Bellman–Ford** | **Có** | Có thể phát hiện chu trình âm tới được và lan truyền ảnh hưởng | Guard unreachable, kiểm tra overflow ở hai hướng |
| **Floyd–Warshall** | **Có** | Phát hiện bằng đường chéo âm; ảnh hưởng theo từng cặp | Guard hai vế trước cộng, không trộn INF với số |

**Đừng nhầm chu trình trọng số 0 với chu trình âm.** Chu trình tổng 0 có thể gây rất nhiều đường đi/đường đi bộ có cùng chi phí, nhưng không làm khoảng cách bị giảm xuống −∞. Dijkstra vẫn xử lý được các cạnh trọng số 0 nếu không có cạnh âm.

## 7. Sai số số thực với trọng số double

Trọng số không phải lúc nào cũng là số nguyên. Thời gian, độ dài, xác suất hoặc dữ liệu hình học có thể được biểu diễn bằng `double`. Kiểu double của Java thường theo IEEE 754 với 53 bit precision của phần significand, nên nhiều số thập phân hữu hạn như 0,1 **không biểu diễn chính xác bằng nhị phân**.

Ví dụ:

```java
double via = 0.1 + 0.2;
double direct = 0.3;

System.out.println(via);              // 0.30000000000000004
System.out.println(via == direct);     // false
```

Hai đường đi có chi phí **bằng nhau trong toán học thập phân** có thể bị xếp thứ tự khác nhau bởi double do làm tròn.

### 7.1. Khi nào double phù hợp?

- Khi bài toán **cho phép sai số**, dữ liệu đầu vào vốn là số thực xấp xỉ, và cần số chữ số chính xác hữu hạn.
- Khi phạm vi trọng số/tổng được kiểm soát, không xuất hiện NaN/Infinity không mong muốn.
- Khi tính đúng được hiểu theo một **mô hình xấp xỉ** hoặc có ngưỡng sai số do đề bài định nghĩa.

Không nên dùng double để tính **chính xác tuyệt đối** tổng tiền, số đếm, số nguyên rất lớn hoặc để phân biệt hai đường chỉ chênh nhau một đơn vị ở cỡ trên 2^53.

Ví dụ số nguyên:

```text
9007199254740993 = 2^53 + 1

Chuyển số ấy sang double:
9007199254740992  (mất 1 đơn vị)
```

Một giá trị double quanh mức đó có bước biểu diễn lớn hơn 1; hai tổng nguyên khác nhau có thể bị làm tròn thành cùng giá trị.

### 7.2. Không dùng “EPS” tùy tiện trong PriorityQueue

Một mẹo so sánh xấp xỉ:

```text
a gần b nếu:
abs(a-b) <= absTol + relTol * max(abs(a),abs(b))
```

có thể hữu ích khi **đánh giá kết quả số học** với tolerance được xác định rõ. Tuy nhiên quan hệ “gần bằng” thường **không bắc cầu**:

```text
a ≈ b, b ≈ c
không nhất thiết a ≈ c.
```

Comparator của PriorityQueue/TreeMap cần quan hệ thứ tự phù hợp với hợp đồng Java. **Không trả 0 trong comparator khi |a−b|≤EPS** một cách tùy tiện, vì có thể phá tính bắc cầu và làm sai các giả định của cấu trúc dữ liệu.

Với PriorityQueue chứa khoảng cách double hữu hạn, dùng:

```java
Comparator.comparingDouble(State::distance)
```

để có thứ tự xác định theo biểu diễn double, cùng quy tắc phụ phá hòa nếu cần. Nếu thuật toán/đề bài đòi so sánh chi phí toán học chính xác, **chỉ thay comparator vẫn chưa đủ**: phải chọn biểu diễn trọng số phù hợp (scaled integer, BigDecimal, rational, v.v.).

### 7.3. Kiểm tra giá trị không hữu hạn

Java có:

```java
Double.isFinite(weight)
Double.isNaN(weight)
Double.POSITIVE_INFINITY
Double.NEGATIVE_INFINITY
```

Nếu chấp nhận trọng số double, nên **từ chối NaN**, kiểm tra `Double.isFinite(weight)` nếu input phải hữu hạn, và kiểm tra **tổng mới** vẫn hữu hạn sau phép cộng. Hai số finite rất lớn vẫn có thể cộng thành +Infinity.

**NaN đặc biệt nguy hiểm:** So sánh `NaN < x`, `NaN > x` và `NaN == x` đều trả false, khiến các nhánh relax có thể không thực hiện dù trạng thái dữ liệu đã bị hỏng.

Với cạnh âm dưới dạng double, Dijkstra vẫn không hợp lệ theo giả thiết thuật toán; rủi ro này **độc lập** với sai số floating-point.

### 7.4. ±0.0 và phép so sánh

double có `+0.0` và `-0.0`. Phép so sánh bằng `==` coi chúng bằng nhau, trong khi `Double.compare(-0.0,+0.0)` phân biệt thứ tự. Nếu ý nghĩa chi phí của ứng dụng coi chúng là cùng mức 0, có thể chuẩn hóa trọng số 0 khi đọc input. Không nên để quy tắc dấu của zero vô tình quyết định một thuật toán vốn mong chờ thứ tự toán học trên các số thực.

## 8. Khi cần chính xác thập phân: BigDecimal và số nguyên tỉ lệ

Nếu trọng số là tiền với đúng hai chữ số thập phân, một lựa chọn phổ biến là chuyển thành **số nguyên đơn vị nhỏ nhất**:

```text
12.34 đơn vị -> 1234 đơn vị nhỏ nhất
0.05 đơn vị  -> 5 đơn vị nhỏ nhất
```

Khi đó thuật toán dùng `long` hoặc `BigInteger` chính xác, tránh cộng double. Tuy nhiên **phải chuyển đổi từ dữ liệu decimal một cách chính xác**, không tùy tiện nhân double rồi ép long nếu đầu vào có sai số.

Trong Java:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal sum = a.add(b);

System.out.println(sum.toPlainString()); // 0.3
```

Dùng chuỗi decimal gốc cho `new BigDecimal("...")` giúp giữ ý nghĩa thập phân. `new BigDecimal(0.1)` sẽ biểu diễn **chính xác giá trị nhị phân của double 0.1**, vốn không đúng bằng 0.1 thập phân. `BigDecimal.valueOf(0.1)` thường phù hợp hơn constructor nhận double trực tiếp, nhưng khi có chuỗi input gốc, cách minh bạch nhất vẫn là parse từ chuỗi.

### 8.1. equals khác compareTo của BigDecimal

```java
new BigDecimal("0.30")
    .equals(new BigDecimal("0.3"))      // false

new BigDecimal("0.30")
    .compareTo(new BigDecimal("0.3"))   // 0
```

`equals` quan tâm cả **scale**; `compareTo` so giá trị số. Trong thuật toán đường đi, khi dùng BigDecimal để so chi phí, thường dùng `compareTo`. Nếu cần chuẩn hóa scale cho tiền, xác định rõ quy tắc làm tròn và scale trước khi đưa vào thuật toán.

### 8.2. BigDecimal không tự giải quyết mọi vấn đề

BigDecimal bảo toàn phép cộng chính xác của các số thập phân hữu hạn được nhập chính xác, nhưng nếu có phép chia, căn bậc hai hoặc hàm phi đại số, có thể cần **MathContext, precision và rounding mode**. Phép cộng/nhân nếu không chỉ định MathContext thường chính xác đối với giá trị decimal đã biểu diễn, nhưng bộ nhớ và thời gian có thể tăng.

Với dữ liệu khoảng cách hình học được tính từ căn bậc hai, việc chuyển một kết quả double **đã làm tròn** sang BigDecimal không thể khôi phục giá trị thực đã mất.

**Bài học:** Chọn biểu diễn **ngay từ nguồn dữ liệu**, trước khi sai số hoặc tràn đã xảy ra.

## 9. Thiết kế hợp đồng số học trước khi viết thuật toán

Trước khi chọn int, long, double hay BigInteger, trả lời:

1. **Trọng số từng cạnh thuộc miền nào?** Có âm không? Bằng 0 được không? Là số nguyên hay decimal?
2. **Đồ thị có bao nhiêu đỉnh/cạnh?** Số cạnh tối đa trên một đường đơn/tổng cần xét?
3. **Input có thể không liên thông?** Phải có trạng thái unreachable riêng.
4. **Có chu trình âm không?** Nếu có, cần phân biệt giá trị −∞ với unreachable.
5. **Tổng trung gian có thể vượt long không?** Nếu có, cần BigInteger hoặc chính sách fail-fast đã công bố.
6. **Cho phép sai số bao nhiêu?** Đáp án cần chính xác tuyệt đối hay so sánh theo tolerance?
7. **Có cần phục hồi đường đi?** Nếu có, mảng parent phải tương ứng với những cập nhật khoảng cách thực sự hợp lệ.
8. **Kết quả được in thế nào?** Phải phân biệt INF, -INF, finite và overflow, không gộp tất cả thành số âm.
9. **Có phép cộng nào được tính trước khi kiểm tra reachability không?** Nếu có, sửa thứ tự.
10. **Kiểu số của comparator/trung gian là gì?** Tránh trừ số lớn để so thứ tự và tránh cộng bằng int trước khi ép long.

### Một hợp đồng ví dụ cho Dijkstra long

> Đồ thị có hướng với cạnh trọng số long không âm, n≥1. Đỉnh chưa tới được được lưu bằng boolean riêng. Mọi phép cộng khoảng cách dùng Math.addExact. Nếu một đường ứng viên vượt miền long, chương trình ném ArithmeticException và không khẳng định đã giải chính xác bài ấy. Muốn hỗ trợ tổng lớn hơn long, dùng bản Dijkstra BigInteger.

Đây là một hợp đồng **rõ ràng, kiểm tra được và không nhập nhằng**. Nó mạnh hơn việc viết `INF=1e18` mà không nêu giới hạn đầu vào.

## 10. Chương trình Java 17+ hoàn chỉnh

Chương trình minh họa bốn tình huống:

- **Dijkstra long không dùng INF sentinel:** Lưu `reachable[]` và `dist[]` riêng, cập nhật bằng `Math.addExact` và dùng `PriorityQueue` có comparator an toàn. Có thể biểu diễn chính xác một đường đi với chi phí `Long.MAX_VALUE`.
- **Dijkstra BigInteger:** Dùng `BigInteger[]`, trong đó `null` nghĩa là unreachable. Tính chính xác các tổng lớn hơn miền long.
- **Bellman–Ford long:** Hỗ trợ trọng số âm, phân biệt unreachable và các đỉnh có đường ngắn nhất **−∞** do chu trình âm tới được từ nguồn. Phát hiện cạnh còn relax được sau n−1 vòng và lan truyền ảnh hưởng theo cung đi ra.
- **Floyd–Warshall long:** Sử dụng `reachable[i][j]` riêng, chỉ cộng hai khoảng cách đã tới được, có kiểm tra chu trình âm bằng đường chéo. Giá trị tại các cặp bị ảnh hưởng bởi chu trình âm không được coi là khoảng cách hữu hạn cuối cùng.

Tất cả các bản long đều chọn chính sách **fail fast khi Math.addExact phát hiện tràn**. Với bài cần đáp án nguyên chính xác vượt long, bản BigInteger giải quyết trực tiếp cho trường hợp Dijkstra không âm.

### Định dạng input và kiểm tra

- Đỉnh đánh số 0..n−1. Hàm một nguồn yêu cầu n≥1 và source hợp lệ.
- `Edge(from,to,weight)` biểu diễn một **cung có thật**, kể cả khi weight=0. Không dùng -1 làm sentinel vì **Bellman–Ford/Floyd–Warshall có thể có cạnh -1 hợp lệ**.
- Danh sách cạnh có thể chứa cung song song hoặc self-loop; thuật toán hoạt động theo định nghĩa có hướng.
- Dijkstra từ chối trọng số âm. Bellman–Ford và Floyd–Warshall chấp nhận trọng số long âm.
- Trong Floyd–Warshall, nếu có nhiều cung u→v, lấy trọng số **nhỏ nhất** làm khoảng cách trực tiếp.
- Kết quả Bellman–Ford có mảng `negativeInfinity[]` riêng; không dùng Long.MIN_VALUE làm sentinel vì đó cũng có thể là một giá trị hữu hạn.
- Với n=0, Floyd–Warshall trả bảng rỗng và không có chu trình âm; thuật toán một nguồn từ chối vì không có source hợp lệ.

Lưu tệp **`ShortestPathNumericSafetyDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.StringJoiner;

public class ShortestPathNumericSafetyDemo {
    record Edge(int from, int to, long weight) {}
    record BigEdge(int from, int to, BigInteger weight) {}

    record LongState(int vertex, long distance) {}
    record BigState(int vertex, BigInteger distance) {}

    record LongPaths(
            boolean[] reached, long[] distance, int[] parent) {}

    record BigPaths(BigInteger[] distance) {}

    record BellmanResult(
            boolean[] reached, long[] distance,
            boolean[] negativeInfinity) {}

    record FloydResult(
            boolean[][] reached, long[][] distance,
            boolean negativeCycle) {}

    private static void checkSource(int n, int source) {
        if (n <= 0) {
            throw new IllegalArgumentException(
                    "vertexCount must be positive");
        }
        if (source < 0 || source >= n) {
            throw new IllegalArgumentException(
                    "source out of range");
        }
    }

    private static void checkEdges(
            int n, List<Edge> edges, boolean allowNegative) {
        Objects.requireNonNull(edges, "edges must not be null");
        for (Edge e : edges) {
            Objects.requireNonNull(e, "edge must not be null");
            if (e.from() < 0 || e.from() >= n
                    || e.to() < 0 || e.to() >= n) {
                throw new IllegalArgumentException(
                        "vertex index out of range");
            }
            if (!allowNegative && e.weight() < 0) {
                throw new IllegalArgumentException(
                        "negative edge not allowed in Dijkstra");
            }
        }
    }

    private static List<List<Edge>> adjacency(
            int n, List<Edge> edges) {
        List<List<Edge>> out = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            out.add(new ArrayList<>());
        }
        for (Edge e : edges) {
            out.get(e.from()).add(e);
        }
        return out;
    }

    // Khong dung Long.MAX_VALUE lam INF.
    // reached[v] phan biet 0/MAX_VALUE voi unreachable.
    static LongPaths dijkstraLong(
            int n, List<Edge> edges, int source) {
        checkSource(n, source);
        checkEdges(n, edges, false);

        List<List<Edge>> out = adjacency(n, edges);
        boolean[] reached = new boolean[n];
        long[] dist = new long[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        PriorityQueue<LongState> pq =
                new PriorityQueue<>(
                        Comparator.comparingLong(
                                LongState::distance)
                                .thenComparingInt(
                                        LongState::vertex));

        reached[source] = true;
        dist[source] = 0;
        pq.add(new LongState(source, 0));

        while (!pq.isEmpty()) {
            LongState state = pq.remove();
            int u = state.vertex();

            // Bo qua ban ghi cu khi khoang cach da tot hon.
            if (!reached[u]
                    || state.distance() != dist[u]) {
                continue;
            }

            for (Edge e : out.get(u)) {
                int v = e.to();
                long cand = Math.addExact(
                        dist[u], e.weight());

                if (!reached[v] || cand < dist[v]) {
                    reached[v] = true;
                    dist[v] = cand;
                    parent[v] = u;
                    pq.add(new LongState(v, cand));
                }
            }
        }
        return new LongPaths(reached, dist, parent);
    }

    // Tra duong tu source toi target theo parent;
    // [] neu khong toi duoc. Cha cua source la -1.
    static int[] reconstructPath(
            LongPaths paths, int target) {
        if (target < 0
                || target >= paths.reached().length) {
            throw new IllegalArgumentException(
                    "target out of range");
        }
        if (!paths.reached()[target]) {
            return new int[0];
        }

        int n = paths.parent().length;
        int[] reverse = new int[n];
        int length = 0;

        for (int at = target; at != -1;
                at = paths.parent()[at]) {
            if (length == n) {
                throw new AssertionError(
                        "cycle in parent pointers");
            }
            reverse[length++] = at;
        }

        int[] result = new int[length];
        for (int i = 0; i < length; i++) {
            result[i] = reverse[length - 1 - i];
        }
        return result;
    }

    static BigPaths dijkstraBig(
            int n, List<BigEdge> edges, int source) {
        checkSource(n, source);
        Objects.requireNonNull(edges, "edges must not be null");

        List<List<BigEdge>> out = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            out.add(new ArrayList<>());
        }
        for (BigEdge e : edges) {
            Objects.requireNonNull(e, "edge must not be null");
            Objects.requireNonNull(
                    e.weight(), "weight must not be null");
            if (e.from() < 0 || e.from() >= n
                    || e.to() < 0 || e.to() >= n) {
                throw new IllegalArgumentException(
                        "vertex index out of range");
            }
            if (e.weight().signum() < 0) {
                throw new IllegalArgumentException(
                        "negative edge not allowed in Dijkstra");
            }
            out.get(e.from()).add(e);
        }

        // null = unreachable; khong xung dot mot so cu the.
        BigInteger[] dist = new BigInteger[n];
        PriorityQueue<BigState> pq = new PriorityQueue<>(
                (a, b) -> {
                    int cmp = a.distance().compareTo(
                            b.distance());
                    return cmp != 0
                            ? cmp
                            : Integer.compare(
                                    a.vertex(), b.vertex());
                });

        dist[source] = BigInteger.ZERO;
        pq.add(new BigState(source, BigInteger.ZERO));

        while (!pq.isEmpty()) {
            BigState state = pq.remove();
            int u = state.vertex();

            if (dist[u] == null
                    || !state.distance().equals(dist[u])) {
                continue;
            }
            for (BigEdge e : out.get(u)) {
                BigInteger cand =
                        dist[u].add(e.weight());
                int v = e.to();

                if (dist[v] == null
                        || cand.compareTo(dist[v]) < 0) {
                    dist[v] = cand;
                    pq.add(new BigState(v, cand));
                }
            }
        }
        return new BigPaths(dist);
    }

    // Co the co canh am, nhung Math.addExact se
    // nem ngoai le neu tong vuot pham vi long.
    static BellmanResult bellmanFord(
            int n, List<Edge> edges, int source) {
        checkSource(n, source);
        checkEdges(n, edges, true);

        boolean[] reached = new boolean[n];
        long[] dist = new long[n];
        reached[source] = true;
        dist[source] = 0;

        for (int pass = 1; pass < n; pass++) {
            boolean changed = false;

            for (Edge e : edges) {
                if (!reached[e.from()]) {
                    continue;
                }

                long cand = Math.addExact(
                        dist[e.from()], e.weight());

                if (!reached[e.to()]
                        || cand < dist[e.to()]) {
                    reached[e.to()] = true;
                    dist[e.to()] = cand;
                    changed = true;
                }
            }

            if (!changed) {
                break;
            }
        }

        List<List<Edge>> out = adjacency(n, edges);
        boolean[] negativeInfinity = new boolean[n];
        ArrayDeque<Integer> q = new ArrayDeque<>();

        // Canh con giam duoc sau n-1 luot:
        // dich cua canh bi anh huong boi chu trinh am.
        for (Edge e : edges) {
            if (!reached[e.from()]) {
                continue;
            }

            long cand = Math.addExact(
                    dist[e.from()], e.weight());
            if ((!reached[e.to()]
                    || cand < dist[e.to()])
                    && !negativeInfinity[e.to()]) {
                negativeInfinity[e.to()] = true;
                q.addLast(e.to());
            }
        }

        // Moi dinh di toi duoc tu chu trinh am
        // cung co khoang cach khong bi chan duoi.
        while (!q.isEmpty()) {
            int u = q.removeFirst();
            for (Edge e : out.get(u)) {
                int v = e.to();
                if (!negativeInfinity[v]) {
                    negativeInfinity[v] = true;
                    q.addLast(v);
                }
            }
        }

        return new BellmanResult(
                reached, dist, negativeInfinity);
    }

    // Khong dung gia tri so INF: reached[i][j]
    // duoc luu doc lap voi dist[i][j].
    static FloydResult floydWarshall(
            int n, List<Edge> edges) {
        if (n < 0) {
            throw new IllegalArgumentException(
                    "vertexCount must be nonnegative");
        }
        checkEdges(n, edges, true);

        boolean[][] reached = new boolean[n][n];
        long[][] dist = new long[n][n];

        for (int i = 0; i < n; i++) {
            reached[i][i] = true;
            dist[i][i] = 0;
        }
        for (Edge e : edges) {
            int u = e.from();
            int v = e.to();

            if (!reached[u][v]
                    || e.weight() < dist[u][v]) {
                reached[u][v] = true;
                dist[u][v] = e.weight();
            }
        }

        for (int k = 0; k < n; k++) {
            for (int i = 0; i < n; i++) {
                if (!reached[i][k]) {
                    continue;
                }
                for (int j = 0; j < n; j++) {
                    if (!reached[k][j]) {
                        continue;
                    }

                    long cand = Math.addExact(
                            dist[i][k], dist[k][j]);

                    if (!reached[i][j]
                            || cand < dist[i][j]) {
                        reached[i][j] = true;
                        dist[i][j] = cand;
                    }
                }
            }
        }

        boolean negativeCycle = false;
        for (int v = 0; v < n; v++) {
            if (dist[v][v] < 0) {
                negativeCycle = true;
            }
        }
        return new FloydResult(
                reached, dist, negativeCycle);
    }

    private static String formatLong(LongPaths r) {
        StringJoiner sj = new StringJoiner(", ", "[", "]");
        for (int v = 0; v < r.distance().length; v++) {
            sj.add(r.reached()[v]
                    ? Long.toString(r.distance()[v])
                    : "INF");
        }
        return sj.toString();
    }

    private static String formatBig(BigPaths r) {
        StringJoiner sj = new StringJoiner(", ", "[", "]");
        for (BigInteger d : r.distance()) {
            sj.add(d == null ? "INF" : d.toString());
        }
        return sj.toString();
    }

    private static String formatBellman(
            BellmanResult r) {
        StringJoiner sj = new StringJoiner(", ", "[", "]");

        for (int v = 0; v < r.distance().length; v++) {
            if (r.negativeInfinity()[v]) {
                sj.add("-INF");
            } else if (!r.reached()[v]) {
                sj.add("INF");
            } else {
                sj.add(Long.toString(r.distance()[v]));
            }
        }
        return sj.toString();
    }

    private static String formatFloydRow(
            FloydResult r, int source) {
        StringJoiner sj = new StringJoiner(", ", "[", "]");
        for (int v = 0; v < r.distance().length; v++) {
            sj.add(r.reached()[source][v]
                    ? Long.toString(r.distance()[source][v])
                    : "INF");
        }
        return sj.toString();
    }

    public static void main(String[] args) {
        int a = 2_000_000_000;
        int b = 2_000_000_000;
        System.out.println("int wrap: " + (a + b));
        System.out.println(
                "long exact: " + ((long) a + b));

        List<Edge> large = List.of(
                new Edge(0, 1, 2_000_000_000L),
                new Edge(1, 2, 2_000_000_000L),
                new Edge(0, 2, 5_000_000_000L),
                new Edge(2, 3, 7L),
                new Edge(1, 3, 3_000_000_000L),
                new Edge(0, 3, 9_000_000_000L),
                new Edge(3, 4, 0L),
                new Edge(0, 4, 8_000_000_000L));

        LongPaths d = dijkstraLong(6, large, 0);
        System.out.println(
                "Dijkstra long: " + formatLong(d));
        System.out.println(
                "Path to 4: " + Arrays.toString(
                        reconstructPath(d, 4)));

        LongPaths maxPath = dijkstraLong(3, List.of(
                new Edge(0, 1, Long.MAX_VALUE),
                new Edge(1, 2, 0L)), 0);
        System.out.println(
                "Long.MAX_VALUE reachable: "
                        + formatLong(maxPath));

        LongPaths zero = dijkstraLong(3, List.of(
                new Edge(0, 1, 0),
                new Edge(1, 2, 0),
                new Edge(0, 2, 4)), 0);
        System.out.println(
                "Zero edges: " + formatLong(zero));

        LongPaths absent = dijkstraLong(3,
                List.of(new Edge(1, 2, 5)), 0);
        System.out.println(
                "Unreachable: " + formatLong(absent));

        BigInteger max =
                new BigInteger("9223372036854775807");
        BigPaths huge = dijkstraBig(3, List.of(
                new BigEdge(0, 1, max),
                new BigEdge(1, 2, BigInteger.TEN)), 0);
        System.out.println(
                "BigInteger path: " + formatBig(huge));

        BellmanResult negativeEdge = bellmanFord(4,
                List.of(
                        new Edge(0, 1, 4),
                        new Edge(0, 2, 5),
                        new Edge(1, 2, -3),
                        new Edge(2, 3, 2)), 0);
        System.out.println(
                "Bellman-Ford: " + formatBellman(negativeEdge));

        BellmanResult negativeCycle = bellmanFord(5,
                List.of(
                        new Edge(0, 1, 1),
                        new Edge(1, 2, -3),
                        new Edge(2, 1, 1),
                        new Edge(2, 3, 2)), 0);
        System.out.println(
                "Bellman-Ford negative cycle: "
                        + formatBellman(negativeCycle));

        FloydResult fw = floydWarshall(4, List.of(
                new Edge(0, 1, 7),
                new Edge(1, 2, -5),
                new Edge(0, 2, 10),
                new Edge(2, 3, 3),
                new Edge(3, 1, 4)));
        System.out.println(
                "Floyd row 0: " + formatFloydRow(fw, 0)
                        + ", negativeCycle="
                        + fw.negativeCycle());

        FloydResult badCycle = floydWarshall(2,
                List.of(
                        new Edge(0, 1, -2),
                        new Edge(1, 0, 1)));
        System.out.println(
                "Floyd negative cycle: "
                        + badCycle.negativeCycle());

        try {
            dijkstraLong(3, List.of(
                    new Edge(0, 1, Long.MAX_VALUE - 3),
                    new Edge(1, 2, 10)), 0);
        } catch (ArithmeticException ex) {
            System.out.println(
                    "Long overflow detected: "
                            + ex.getMessage());
        }

        try {
            dijkstraLong(2,
                    List.of(new Edge(0, 1, -1)), 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Negative edge rejected: "
                            + ex.getMessage());
        }

        double via = 0.1 + 0.2;
        double direct = 0.3;
        System.out.println(
                "Double: " + via + " == " + direct
                        + " -> " + (via == direct));

        BigDecimal decimalSum =
                new BigDecimal("0.1").add(
                        new BigDecimal("0.2"));
        System.out.println(
                "BigDecimal: "
                        + decimalSum.toPlainString()
                        + ", compareTo(0.3)="
                        + decimalSum.compareTo(
                                new BigDecimal("0.3")));

        BigDecimal x = new BigDecimal("0.30");
        BigDecimal y = new BigDecimal("0.3");
        System.out.println(
                "Scale: equals=" + x.equals(y)
                        + ", compareTo=" + x.compareTo(y));

        long exact = 9_007_199_254_740_993L;
        long rounded = (long) (double) exact;
        System.out.println(
                "Double lost integer: " + rounded
                        + " vs " + exact);
    }
}
```

Biên dịch với JDK 17 trở lên:

```bash
javac ShortestPathNumericSafetyDemo.java
java ShortestPathNumericSafetyDemo
```

**Stdout kỳ vọng chính xác:**

```text
int wrap: -294967296
long exact: 4000000000
Dijkstra long: [0, 2000000000, 4000000000, 4000000007, 4000000007, INF]
Path to 4: [0, 1, 2, 3, 4]
Long.MAX_VALUE reachable: [0, 9223372036854775807, 9223372036854775807]
Zero edges: [0, 0, 0]
Unreachable: [0, INF, INF]
BigInteger path: [0, 9223372036854775807, 9223372036854775817]
Bellman-Ford: [0, 4, 1, 3]
Bellman-Ford negative cycle: [0, -INF, -INF, -INF, INF]
Floyd row 0: [0, 7, 2, 5], negativeCycle=false
Floyd negative cycle: true
Long overflow detected: long overflow
Negative edge rejected: negative edge not allowed in Dijkstra
Double: 0.30000000000000004 == 0.3 -> false
BigDecimal: 0.3, compareTo(0.3)=0
Scale: equals=false, compareTo=0
Double lost integer: 9007199254740992 vs 9007199254740993
```

### 10.1. Đọc hiểu từng ca trong stdout

**int wrap / long exact:** 2 tỷ + 2 tỷ vượt miền int. Giá trị âm do wraparound là lỗi số học, không phải bằng chứng tồn tại cạnh âm.

**Dijkstra long:** Hai cung 2 tỷ nối nhau cho khoảng cách 4 tỷ tới đỉnh 2. Đường đi tốt nhất tới 3 đi qua 2 có chi phí 4.000.000.007; tới đỉnh 4 thêm cạnh trọng số 0 nên vẫn cùng chi phí. Đỉnh 5 không tới được.

**Long.MAX_VALUE reachable:** Cung 0→1 có trọng số Long.MAX_VALUE, cung 1→2 trọng số 0. Cả đỉnh 1 và 2 đều **tới được**, và có khoảng cách đúng bằng Long.MAX_VALUE. Nếu dùng số ấy làm INF sentinel mà không có reachable riêng, thông tin này bị mất.

**Zero edges:** Cạnh 0 trọng số 0 vẫn là cạnh thật. Đường ngắn nhất 0→1→2 có chi phí 0, không phải unreachable.

**Unreachable:** Đồ thị chỉ có cung 1→2; xuất phát từ 0 nên không tới được 1 hoặc 2. Kết quả khác hẳn một đường có khoảng cách 0.

**BigInteger path:** Tổng `Long.MAX_VALUE+10=9223372036854775817` vượt long nhưng được BigInteger tính chính xác.

**Bellman–Ford:** Cạnh 1→2 trọng số −3 hợp lệ; đường 0→1→2 có chi phí 1, rồi tới 3 có chi phí 3. Dijkstra không được dùng cho mô hình có cạnh âm này.

**Bellman–Ford negative cycle:** Có chu trình 1→2→1 với tổng −2, tới được từ 0. Từ chu trình đi tới 3, nên các đỉnh 1,2,3 có khoảng cách **−∞**. Đỉnh 4 hoàn toàn không tới được nên có trạng thái **INF**, không phải −INF. Nguồn 0 vẫn có khoảng cách 0 vì không có cung trở lại 0 từ chu trình âm.

**Floyd row 0:** Các cạnh âm vẫn cho kết quả hữu hạn khi không có chu trình âm. Đường 0→1→2 có tổng 7−5=2, đường tiếp tới 3 có tổng 5. Chu trình 1→2→3→1 có chi phí 2, không âm.

**Floyd negative cycle:** Hai cung 0→1 trọng số −2 và 1→0 trọng số 1 tạo chu trình tổng −1. Cờ phát hiện âm được bật; không nên coi các ô dist bị ảnh hưởng là khoảng cách hữu hạn cuối cùng.

**Overflow:** Long.MAX_VALUE−3 cộng thêm 10 vượt miền long; Math.addExact báo lỗi. Chương trình không đưa ra số âm giả.

**Negative edge rejected:** Dijkstra từ chối cạnh âm ngay khi xác thực input, thay vì cố chạy rồi trả một kết quả không được bảo đảm.

**Double:** `0.1+0.2` không bằng 0.3 dưới biểu diễn double. BigDecimal tạo từ chuỗi giữ phép cộng thập phân đúng. Hai BigDecimal `0.30` và `0.3` bằng nhau về **giá trị số** nhưng `equals` vẫn false vì scale khác.

**Double lost integer:** Số nguyên 2^53+1 chuyển sang double bị làm tròn thành 2^53, cho thấy không nên dùng double thay thế số nguyên long khi cần phân biệt từng đơn vị.

### 10.2. Vì sao Dijkstra dùng parent nhưng Bellman–Ford không in đường đi?

Dijkstra với cạnh không âm, không có chu trình âm, có thể lưu `parent[v]=u` mỗi khi tìm được khoảng cách nhỏ hơn. Khi cập nhật strictly smaller, các liên kết parent của kết quả được hình thành từ các đường đi hợp lệ; với cấu trúc tìm kiếm đúng, có thể truy vết lại tới source.

Với Bellman–Ford, nếu có chu trình âm ảnh hưởng tới đỉnh v, **không tồn tại một đường ngắn nhất hữu hạn để phục hồi**. Vì vậy ví dụ ưu tiên trả trạng thái `negativeInfinity` và không hứa có một parent path ngắn nhất cho v. Với các đỉnh hữu hạn không bị ảnh hưởng, có thể bổ sung truy vết parent theo quy tắc cập nhật của Bellman–Ford khi cần.

### 10.3. Floyd–Warshall với chu trình âm cần cẩn trọng hơn

Đoạn Java trả cờ `negativeCycle` toàn đồ thị. Khi cờ true, **không được in bảng như một ma trận khoảng cách ngắn nhất hữu hạn đúng cho mọi cặp**. Cần phân loại từng cặp (i,j) có thể tới chu trình âm rồi rời chu trình để tới j hay không. Những cặp đó phải được đánh dấu **−INF** ở lớp biểu diễn logic riêng.

Bản Floyd ở đây minh họa cách **chống tràn và chống sentinel sai**, đồng thời phát hiện có chu trình âm. Nó không tự triển khai lớp đánh dấu −INF cho từng cặp; đây là giới hạn được nói rõ, không phải một mặc định ngầm.

### 10.4. Nơi có thể xuất hiện overflow trước khi tìm nghiệm

Nếu trong quá trình Dijkstra thử một đường đi ứng viên quá lớn, Math.addExact có thể báo lỗi dù đường tối ưu của một đỉnh khác vẫn nằm trong long. Điều này **cố ý** theo chính sách fail-fast. Bản BigInteger được cung cấp khi đầu vào không cho phép ta chứng minh an toàn rằng mọi phép cộng cần thực hiện đều nằm trong long.

Nếu bài đòi tốc độ tối đa với trọng số nhỏ đã biết, dùng long kèm kiểm tra giới hạn đầu vào có thể nhanh hơn BigInteger; không cần chuyển toàn bộ chương trình sang BigInteger một cách máy móc.

## 11. Kiểm thử overflow và INF có hệ thống

### 11.1. Một đồ thị không có cạnh

Tạo n=3, source=0, edges rỗng. Kết quả:

```text
[0, INF, INF]
```

Nếu thuật toán trả 0 cho 1 hoặc 2, có thể đã nhầm giá trị mặc định của mảng số với khoảng cách thật.

### 11.2. Cạnh trọng số 0

```text
0 --0--> 1 --0--> 2
```

Kết quả [0,0,0]. Nếu code dùng điều kiện `weight>0` để nhận biết cạnh tồn tại, sẽ bỏ sai các cung 0.

### 11.3. Khoảng cách đúng bằng sentinel

Tạo cung 0→1 trọng số Long.MAX_VALUE. Hệ thống chỉ dùng `dist[v]==Long.MAX_VALUE` để kiểm tra unreachable sẽ không phân biệt được hai trường hợp; thiết kế `reachable[]` giúp trả đúng.

### 11.4. Tổng vượt int nhưng chưa vượt long

Hai cạnh 2 tỷ liên tiếp. Kết quả 4 tỷ. Kiểm tra rằng toán hạng được chuyển thành long **trước cộng**.

### 11.5. Tổng vượt long

Cung 0→1 trọng số Long.MAX_VALUE−3; 1→2 trọng số 10. Chính sách long fail-fast phải báo ArithmeticException; bản BigInteger phải trả được giá trị nếu input được biểu diễn chính xác bằng BigInteger.

### 11.6. Cạnh âm không có chu trình âm

```text
0->1 = 4
0->2 = 5
1->2 = -3
2->3 = 2
```

Bellman–Ford trả [0,4,1,3]. Dijkstra phải từ chối input vì có cạnh âm.

### 11.7. Chu trình âm có thể và không thể tới được

Nếu chu trình âm tới được từ s và từ chu trình tới được v, khoảng cách tới v là −∞. Nếu chu trình nằm trong một thành phần hoàn toàn không tới được từ s, nó không ảnh hưởng các khoảng cách từ s.

Một ca cần phân biệt:

```text
0 -> 1, trọng số 2

2 -> 3, trọng số -5
3 -> 2, trọng số 1
```

Từ s=0, chu trình âm giữa 2 và 3 **không tới được**. Dist[0]=0, dist[1]=2, dist[2]=INF, dist[3]=INF; không có đỉnh nào −INF trong bài toán một nguồn ấy.

### 11.8. Kiểm thử số thực và thứ tự comparator

Kiểm tra `0.1+0.2` khác `0.3` dưới double. Kiểm tra thêm việc comparator phải sử dụng Long.compare/Double.compare, **không** trừ khoảng cách rồi ép int, và không dùng quan hệ EPS “gần bằng” làm comparator heap.

### 11.9. So sánh với oracle chính xác

Với đồ thị nhỏ có trọng số nguyên, có thể dùng:

- **BigInteger Bellman–Ford** hoặc một brute force đường đi đơn trên đồ thị không có chu trình âm để làm oracle cho tổng lớn.
- Với Dijkstra nonnegative và n nhỏ, so kết quả với Floyd–Warshall BigInteger hoặc một thuật toán chậm nhưng chính xác.
- Với Floyd–Warshall có chu trình âm, kiểm tra phát hiện đường chéo âm và ảnh hưởng theo từng cặp, không chỉ đối chiếu vài ô bất kỳ.

Nếu bản long báo ArithmeticException nhưng bản BigInteger có kết quả, đó là bằng chứng **giới hạn miền số**, không phải chứng minh thuật toán đồ thị sai.

## 12. Lỗi thường gặp và cách sửa

1. **Dùng int để cộng nhiều trọng số lớn.** Chuyển sang long trước phép cộng hoặc dùng BigInteger.
2. **Tưởng khai báo biến nhận long là đủ.** Vế phải có thể đã cộng bằng int và tràn trước khi gán.
3. **Nói long không thể tràn.** Long vẫn có cận ±9,22×10^18.
4. **Dùng Long.MAX_VALUE làm INF mà không có giới hạn giá trị đường thật.** Có thể bỏ mất đường có chi phí đúng bằng Long.MAX_VALUE.
5. **Dùng Long.MAX_VALUE/4 mà không chứng minh khoảng cách nhỏ hơn INF.** Ngưỡng thấp hơn vẫn có thể va chạm đường hợp lệ.
6. **Cộng INF với trọng số rồi mới kiểm tra unreachable.** Phải kiểm tra reachability trước cộng.
7. **Dùng Math.min(INF, candidate) sau khi candidate đã tràn.** Một phép min không thể sửa phép cộng đã cho số sai.
8. **Cho rằng Math.addExact tự chọn BigInteger.** Nó chỉ **ném ngoại lệ**, không tự nâng kiểu.
9. **Bỏ qua ArithmeticException rồi in INF.** Overflow không đồng nghĩa không có đường.
10. **Gộp reachable và negativeInfinity vào cùng một số sentinel âm.** Hai trạng thái có ý nghĩa khác nhau.
11. **Đánh dấu −INF cho mọi đỉnh khi có chu trình âm ở đâu đó.** Chỉ những đỉnh ảnh hưởng bởi chu trình âm tới được mới có −∞.
12. **Coi chu trình 0 là chu trình âm.** Chi phí không thể giảm vô hạn khi lặp một chu trình tổng 0.
13. **Dùng Dijkstra trên cạnh âm.** Lỗi giả thiết thuật toán, không phải lỗi INF.
14. **Cho rằng Dijkstra phải từ chối cạnh trọng số 0.** Cạnh 0 hợp lệ và thường gặp.
15. **Dùng số −1 để biểu diễn “không có cạnh” khi bài cho phép cạnh trọng số −1.** Cần tách tồn tại cạnh ra khỏi trọng số.
16. **Dùng Comparator trừ hai long và ép int.** Có thể tràn hoặc đổi sai thứ tự heap.
17. **Không bỏ qua state cũ trong PriorityQueue của Dijkstra.** Có thể làm thừa việc; với một số biến thể có settled sai sẽ ảnh hưởng kết quả.
18. **Lưu dist mặc định 0 nhưng quên reachable.** Đỉnh chưa tới được trông giống đỉnh có chi phí 0.
19. **Không guard cả dist[i][k] và dist[k][j] trong Floyd–Warshall.** Tạo đường qua một cặp không tới được.
20. **Không xử lý nhiều cung song song.** Floyd phải lấy giá nhỏ nhất; Dijkstra có thể giữ tất cả cung và relax bình thường.
21. **Coi dist[v][v]<0 của Floyd là câu trả lời cho mọi cặp.** Phải phân loại cặp có thể đi qua chu trình âm.
22. **Chuyển int sang double vì “double lớn hơn”.** Double mất tính chính xác đơn vị nguyên trên 2^53.
23. **Dùng EPS trong Comparator của PriorityQueue.** Có thể phá tính bắc cầu/thuộc tính thứ tự.
24. **Không từ chối NaN hoặc Infinity trong input double.** So sánh/relax không còn có ý nghĩa dự kiến.
25. **Dùng BigDecimal(double) để mong lấy đúng số thập phân gốc.** Tạo từ chuỗi decimal sẽ rõ ràng hơn.
26. **Dùng BigDecimal.equals cho so sánh giá trị chi phí mà không xét scale.** Dùng compareTo cho thứ tự số học.
27. **Làm tròn từng cạnh trước khi cộng mà không có quy tắc.** Tổng của các số đã làm tròn có thể khác kết quả làm tròn cuối.
28. **Cho rằng đổi biểu diễn sau phép cộng double khôi phục sai số.** Thông tin đã mất thì không tự trở lại.
29. **Không xác định nguồn và đích hợp lệ.** Với n=0, không có source để chạy thuật toán một nguồn.
30. **Không kiểm tra negative weight khi chạy Dijkstra.** Phải xác thực giả thiết trước khi thực thi.
31. **Không tính giới hạn số cạnh trên một đường hợp lệ.** Khó chứng minh long đủ miền cho giá trị trung gian.
32. **Không phân biệt lỗi overflow của phép cộng ứng viên với không có tour/đường.** Phải trả trạng thái/lỗi riêng.
33. **Sử dụng tổng trọng số âm rồi chặn thành 0 vì chi phí “không thể âm”.** Bellman–Ford có đường hữu hạn âm hợp lệ.
34. **Không giữ chính xác trọng số cung gốc khi đổi đơn vị.** Làm tròn/nhân double tùy tiện có thể thay đổi thứ tự tối ưu.
35. **Tin một output trông hợp lý mà không thử sát ngưỡng số.** Cần test Long.MAX_VALUE, cộng vượt long, INF, cạnh 0, cạnh âm và số double sát nhau.

## 13. Bài tập tự luyện có đáp án

**Bài 1.** Với hai cạnh trọng số 2 tỷ, tổng là bao nhiêu và kiểu nào phù hợp?

**Đáp án:** Tổng **4.000.000.000**, vượt int nhưng còn trong long. Phải chuyển một toán hạng sang long trước khi cộng.

**Bài 2.** Phát biểu điều kiện tối thiểu để dùng Long.MAX_VALUE/4 làm INF sentinel mà không sai.

**Đáp án:** Mọi khoảng cách hữu hạn cần biểu diễn và phép tính ứng viên cần so sánh phải được chứng minh nằm dưới ngưỡng INF và không tràn kiểu số; các phép cộng chỉ thực hiện trên trạng thái tới được.

**Bài 3.** Nếu có cung từ 0 tới 1 trọng số đúng bằng Long.MAX_VALUE, có được coi đỉnh 1 là không tới được khi dist[1]==Long.MAX_VALUE không?

**Đáp án:** Không. Cung có thật, đường tồn tại. Phải có `reachable[1]=true` hoặc một biểu diễn khác không xung đột.

**Bài 4.** `Math.addExact(Long.MAX_VALUE,1)` làm gì?

**Đáp án:** Ném ArithmeticException thay vì trả kết quả âm do wraparound. Nó **không** tự động trả BigInteger.

**Bài 5.** Nếu bài toán cần kết quả nguyên chính xác lớn hơn Long.MAX_VALUE, nên dùng gì?

**Đáp án:** BigInteger hoặc một kiểu biểu diễn chính xác khác đủ miền. Không lấy một giá trị INF hữu hạn thay cho đáp án thật.

**Bài 6.** Có cạnh 0→1 trọng số 0 và không có cạnh từ 0 tới 2. Trạng thái ra sao?

**Đáp án:** Dist[1]=0 và reachable[1]=true; đỉnh 2 là unreachable. Số 0 không dùng làm sentinel cho “không có đường”.

**Bài 7.** Bellman–Ford: Vì sao `INF+(-5)` gây lỗi nếu không guard?

**Đáp án:** Nó có thể tạo số nhỏ hơn INF, khiến đỉnh không tới được bị relax thành hữu hạn. Phải kiểm tra trạng thái nguồn cạnh tới được trước cộng.

**Bài 8.** Dijkstra có hợp lệ khi có một cạnh trọng số −1 không?

**Đáp án:** Không theo giả thiết thuật toán chuẩn. Đổi kiểu số hoặc tăng INF không giải quyết. Dùng Bellman–Ford hoặc thuật toán hỗ trợ cạnh âm.

**Bài 9.** Nếu nguồn tới được một chu trình âm, mọi đỉnh của graph đều có dist=−∞ không?

**Đáp án:** Không. Chỉ các đỉnh có thể đi tới được từ chu trình âm ấy (và chu trình âm tới được từ nguồn) mới có khoảng cách −∞. Các đỉnh không tới được vẫn INF.

**Bài 10.** Với cạnh 0→1=4, 0→2=5, 1→2=−3, 2→3=2, dist từ 0 tới 3 là bao nhiêu?

**Đáp án:** 0→1→2→3 có chi phí 4−3+2=**3**; không có chu trình âm trong mẫu này.

**Bài 11.** Tại sao Floyd–Warshall phải kiểm tra cả hai trạng thái (i,k), (k,j)?

**Đáp án:** Chỉ khi i tới k **và** k tới j mới có đường ghép i→k→j. Cộng với INF sẽ tạo đường giả hoặc tràn.

**Bài 12.** Giá trị `0.1+0.2==0.3` trong double Java là true hay false?

**Đáp án:** False; 0.1+0.2 thường được biểu diễn thành 0.30000000000000004.

**Bài 13.** Khi nào dùng BigDecimal thay cho double?

**Đáp án:** Khi dữ liệu gốc là decimal hữu hạn (ví dụ tiền) và bài yêu cầu phép cộng/so sánh thập phân chính xác. Parse từ chuỗi hoặc dùng scaled integer với quy tắc chuyển đổi rõ.

**Bài 14.** `new BigDecimal("0.30").equals(new BigDecimal("0.3"))` trả gì? `compareTo`?

**Đáp án:** equals=false vì scale khác; compareTo=0 vì giá trị số bằng nhau.

**Bài 15.** Có nên so hai khoảng cách trong PriorityQueue bằng `(int)(a-b)` không?

**Đáp án:** Không. Phép trừ có thể tràn long hoặc ép mất bit. Dùng Long.compare/Comparator.comparingLong và quy tắc phá hòa.

**Bài 16.** Tại sao EPS “gần bằng” không nên dùng trực tiếp làm comparator?

**Đáp án:** Quan hệ gần bằng có thể không bắc cầu, vi phạm hợp đồng thứ tự của comparator; heap/tree có thể hoạt động không phù hợp với dự định. Cần so sánh thứ tự ổn định và quy định sai số ở lớp đánh giá kết quả.

**Bài 17.** Nếu Bellman–Ford tìm thấy chu trình âm ở một thành phần không tới được từ nguồn, kết quả từ nguồn có phải −∞ không?

**Đáp án:** Không. Chu trình không tới được không thể ảnh hưởng đường xuất phát từ nguồn. Đỉnh trong thành phần ấy vẫn unreachable.

**Bài 18.** Floyd–Warshall phát hiện có chu trình âm. Có được đánh dấu mọi dist[i][j]=−∞ không?

**Đáp án:** Không. Chỉ những cặp (i,j) có đường i→chu trình âm→j bị ảnh hưởng. Các cặp khác có thể có đường hữu hạn hoặc không tới được.

**Bài 19.** Vì sao một đường có tổng Long.MAX_VALUE−3+10 phải báo overflow trong bản long fail-fast?

**Đáp án:** Tổng là Long.MAX_VALUE+7, vượt miền long; trả wraparound sẽ sai. Bản dùng Math.addExact phải ném ngoại lệ, còn bản BigInteger có thể trả chính xác.

**Bài 20.** Nếu thuật toán dùng Math.addExact nhưng ném ngoại lệ khi gặp đường ứng viên lớn, có thể coi nó đã tính xong đáp án nhỏ nhất chưa?

**Đáp án:** Không. Ngoại lệ nghĩa là bản triển khai **từ chối giải trong miền số đã chọn**, không trả kết quả. Nếu đề đòi đáp án cho input ấy, cần bản đủ miền hoặc cách xử lý overflow đã chứng minh đúng.

**Bài 21.** Đồ thị có cung 0→1 trọng số 0, 1→2 trọng số 0, 0→2 trọng số 4. Đường ngắn nhất 0→2 là gì?

**Đáp án:** 0→1→2 với chi phí **0**. Mọi thuật toán đúng cho cạnh không âm phải cho phép cạnh trọng số 0.

**Bài 22.** Tại sao không nên lưu Long.MIN_VALUE làm ký hiệu −∞ nếu input hỗ trợ giá trị âm rất lớn?

**Đáp án:** Long.MIN_VALUE cũng có thể là một khoảng cách hữu hạn hợp lệ. Tách cờ `negativeInfinity` khỏi giá trị số tránh nhập nhằng.

**Bài 23.** Double có thể biểu diễn chính xác mọi số nguyên long không?

**Đáp án:** Không. Trên 2^53, các số nguyên liên tiếp không còn bảo đảm biểu diễn phân biệt; ví dụ 2^53+1 bị làm tròn thành 2^53.

**Bài 24.** Nêu một bộ kiểm thử tối thiểu cho tính an toàn số của shortest path.

**Đáp án:** Cạnh 0, không có đường, tổng vượt int, đường đúng bằng INF sentinel, tổng vượt long, cạnh âm, chu trình âm tới được/không tới được, hai đường có chi phí double gần bằng nhau, và đường đi có nhiều cạnh song song.

## 14. Bảng ghi nhớ nhanh

| Tình huống | Cách làm đúng |
| --- | --- |
| Trọng số/tổng vừa int | int có thể dùng nếu chứng minh an toàn; long thường đơn giản hơn |
| Tổng vượt int | Dùng long **trước phép cộng** |
| Tổng có thể vượt long | BigInteger hoặc chính sách fail-fast có công bố |
| Unreachable và khoảng cách có thể bằng Long.MAX_VALUE | `reachable[]` riêng hoặc kiểu Optional/null |
| Dùng INF sentinel | Có chứng minh mọi khoảng cách hợp lệ **nhỏ hơn INF** |
| Floyd có một vế không tới được | **Không thực hiện phép cộng** |
| Dijkstra gặp cạnh âm | Từ chối hoặc chọn thuật toán khác |
| Bellman–Ford gặp chu trình âm tới được | Đánh dấu các đỉnh ảnh hưởng là −∞ |
| Floyd có chu trình âm | Đánh dấu các **cặp** đi qua chu trình âm, không gán mọi cặp −∞ |
| Double có NaN/Infinity | Kiểm tra tính hữu hạn đầu vào và tổng |
| Dữ liệu decimal yêu cầu exact | Scaled integer/BigDecimal từ chuỗi |
| So sánh trong PriorityQueue | Long.compare / Double.compare / BigInteger.compareTo |
| Cần kiểm thử | Các giá trị sát ngưỡng, 0, không tới được, chu trình âm và số thực |

## Kết luận

**Kiểm soát tràn số, giá trị vô cực và sai số trọng số** là một phần của **chứng minh tính đúng** của thuật toán đường đi ngắn nhất, không chỉ là chi tiết cú pháp Java.

- **Tràn số:** Phép cộng int/long bình thường có thể wraparound. Dùng kiểu đủ miền, kiểm tra trước phép tính hoặc `Math.addExact`; chọn BigInteger nếu cần đáp án nguyên chính xác vượt long.
- **Vô cực:** Không tới được là **trạng thái**, không phải một số hữu hạn bất kỳ. Nếu dùng INF sentinel thì cần chứng minh khoảng cách thật không bao giờ chạm ngưỡng; nếu không, dùng reachable riêng.
- **Cạnh và chu trình âm:** Dijkstra yêu cầu trọng số không âm; Bellman–Ford và Floyd–Warshall có quy tắc riêng. Chu trình âm tới được và ảnh hưởng tới đích tạo khoảng cách **−∞**, khác hoàn toàn unreachable.
- **Số thực:** Double có sai số và giới hạn độ chính xác nguyên; không dùng EPS tùy tiện trong comparator, không nhận NaN/Infinity ngoài hợp đồng. Khi yêu cầu chính xác decimal, dùng biểu diễn số phù hợp từ dữ liệu gốc.
- **Kiểm thử:** Đừng chỉ chạy các số nhỏ. Hãy thử 0, ngưỡng int/long, đường đúng bằng INF, đường bị tràn, cạnh âm, chu trình âm, không có đường và các số double gần bằng nhau.

Một thuật toán có công thức relax đúng nhưng **biểu diễn sai khoảng cách** vẫn có thể sai toàn bộ. Xác định miền giá trị và cách biểu diễn unreachable/overflow/−∞ **trước khi cài đặt** là bước then chốt để xây bộ giải shortest path đáng tin cậy.
