# Chi phí khấu hao và chuỗi thao tác

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **chi phí thực tế của một thao tác**, **chi phí tệ nhất của thao tác**, **chi phí khấu hao** và **chi phí kỳ vọng/trung bình**.
2. Đánh giá tổng chi phí của **một chuỗi thao tác hợp lệ** thay vì nhân chi phí tệ nhất của một lần thao tác với số lần gọi.
3. Sử dụng ba phương pháp phân tích khấu hao: **tổng gộp (aggregate)**, **ghi sổ/tín dụng (accounting)** và **hàm thế năng (potential)**.
4. Giải thích và chứng minh thời gian thêm phần tử khấu hao `O(1)` của mảng động tăng dung lượng theo cấp số nhân; phân tích bộ đếm nhị phân và ngăn xếp có `MULTIPOP`.
5. Phát hiện trường hợp phân tích khấu hao không còn đúng do thay đổi quy tắc thao tác, chi phí hoặc trạng thái ban đầu.

## 1. Chi phí khấu hao là gì?

Trong một số cấu trúc dữ liệu, đa số thao tác có giá rẻ nhưng thỉnh thoảng có một thao tác rất đắt. Ví dụ mảng động gần đầy chỉ cần ghi phần tử mới vào một vị trí, còn khi **hết chỗ**, nó phải cấp phát vùng lớn hơn và sao chép toàn bộ phần tử cũ trước khi thêm.

**Phân tích khấu hao (amortized analysis)** đặt câu hỏi:

> Với **mọi chuỗi gồm `m` thao tác hợp lệ**, bắt đầu từ trạng thái được quy định, tổng công việc lớn nhất có thể phải trả là bao nhiêu?

Nếu chứng minh tổng chi phí `T(m) = O(m)`, ta nói chi phí **khấu hao mỗi thao tác là `O(1)`**. Điều đó **không** có nghĩa mọi lần gọi đều mất `O(1)` thời gian thực tế. Một lần mở rộng mảng có thể sao chép `n` phần tử, tức tốn `Θ(n)` cho chính lần đó; nhưng các lần mở rộng đắt không thể xảy ra liên tục tùy ý nếu quy tắc tăng dung lượng hợp lý.

So sánh bốn cách mô tả:

| Cách đánh giá | Câu hỏi | Vai trò của xác suất |
| --- | --- | --- |
| **Worst-case của một thao tác** | Một lần gọi riêng lẻ đắt nhất đến đâu trong trạng thái có kích thước `n`? | Không cần |
| **Worst-case của cả chuỗi** | Tổng chi phí lớn nhất trên mọi chuỗi `m` thao tác hợp lệ là bao nhiêu? | Không cần |
| **Amortized per operation** | Có thể phân bổ tổng chi phí chuỗi thành ngân sách nhỏ cho mỗi thao tác không? | Không cần |
| **Average-case / expected cost** | Chi phí trung bình hoặc kỳ vọng dưới phân phối đầu vào/nguồn ngẫu nhiên xác định là bao nhiêu? | **Cần** giả định xác suất khi nói về kỳ vọng |

Phân tích khấu hao là một **bảo đảm tất định trên chuỗi hợp lệ**, không phải lấy thời gian của vài lần chạy rồi chia trung bình và không mặc định giả sử dữ liệu đến ngẫu nhiên.

### Ký hiệu và mô hình chi phí

Gọi `D_0` là trạng thái ban đầu. Một chuỗi thao tác `op_1, op_2, \ldots, op_m` tạo ra các trạng thái `D_1, D_2, \ldots, D_m`. Ký hiệu:

- `c_i \ge 0`: **chi phí thực tế** của thao tác thứ `i` theo một mô hình được công bố, ví dụ số lần ghi hoặc sao chép phần tử.
- `T(m) = \sum_{i=1}^{m} c_i`: tổng chi phí thực tế của cả chuỗi.
- `\hat c_i`: **chi phí khấu hao** (ngân sách dùng để tính và trả chi phí, tùy phương pháp).

Mục tiêu thường là chứng minh `\sum_{i=1}^{m} c_i \le \sum_{i=1}^{m} \hat c_i` và mỗi `\hat c_i` được chặn bởi một hằng số, hoặc trực tiếp chứng minh `T(m) \le K m + b` với các hằng số không phụ thuộc vào `m`.

**Phạm vi phải nói rõ:** loại thao tác được phép (chỉ `append` hay cả `remove`), trạng thái bắt đầu (rỗng hay đã có sẵn dữ liệu), quy tắc cấp phát, điều kiện phát sinh thao tác đắt và đơn vị chi phí. Một chứng minh chỉ cho `append` không tự động áp dụng cho chuỗi xen kẽ `append`/`remove`.

## 2. Vì sao phải phân tích chuỗi thay vì từng thao tác?

Xét mảng động bắt đầu với **dung lượng (capacity) = 1**, **kích thước (size) = 0**. Mỗi lần `append(x)`:

1. Nếu còn chỗ, ghi phần tử vào cuối, chi phí quy ước `1`.
2. Nếu đầy với `n = capacity`, cấp phát vùng gấp đôi, sao chép `n` phần tử cũ rồi ghi phần tử mới; chi phí quy ước `n + 1`.

Chúng ta đếm **mỗi lần ghi phần tử mới** và **mỗi lần sao chép một phần tử cũ** là một đơn vị. Để tập trung vào thuật toán, bỏ qua chi phí cố định cấp phát, kiểm tra biên và thu gom rác; giả sử phép cấp phát thành công và dung lượng chưa vượt giới hạn biểu diễn. Quy tắc của ví dụ là do **chúng ta tự định nghĩa**, không khẳng định tất cả thư viện đều dùng chính xác cách tăng này.

| Lần `append` | Size sau thêm | Capacity sau thêm | Số phần tử sao chép | Chi phí `c_i` | Tổng đến đây |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 1 | 0 | 1 | 1 |
| 2 | 2 | 2 | 1 | 2 | 3 |
| 3 | 3 | 4 | 2 | 3 | 6 |
| 4 | 4 | 4 | 0 | 1 | 7 |
| 5 | 5 | 8 | 4 | 5 | 12 |
| 6 | 6 | 8 | 0 | 1 | 13 |
| 7 | 7 | 8 | 0 | 1 | 14 |
| 8 | 8 | 8 | 0 | 1 | 15 |
| 9 | 9 | 16 | 8 | 9 | 24 |

Lần thêm thứ 9 tốn 9 đơn vị vì phải sao chép 8 phần tử, nhưng tổng cả 9 lần chỉ tốn 24 đơn vị. Không thể kết luận chi phí cả chuỗi là `O(m^2)` chỉ vì **một** `append` có thể là `O(m)`. Ta còn phải xét những trạng thái cho phép lần mở rộng tiếp theo: capacity tăng gấp đôi, nên phải thêm nhiều phần tử nữa mới có lần sao chép lớn kế tiếp.

Đây là tư duy cốt lõi của phân tích khấu hao: **thao tác đắt được ngăn cách bởi những thao tác rẻ có thể “để dành” chi phí**.

## 3. Phương pháp tổng gộp (aggregate method)

Ta tính tổng toàn bộ các thao tác trước, sau đó chia cho số thao tác.

Với `m \ge 1` lần `append` bắt đầu từ mảng rỗng, luôn có đúng `m` lần ghi phần tử mới. Mỗi lần mở rộng xảy ra khi capacity lần lượt bằng `1, 2, 4, 8, \ldots`; số lần sao chép ở các sự kiện đó cũng lần lượt là `1, 2, 4, 8, \ldots`.

Giả sử sự kiện mở rộng cuối cùng (nếu có) đã sao chép `R` phần tử. Khi đó:

```text
Tổng số phần tử được sao chép
= 1 + 2 + 4 + ... + R
= 2R - 1.
```

Vì sự kiện ấy xảy ra ở thao tác `append` thứ `R+1`, ta có `R < m`. Do đó:

```text
Số bản sao < 2m.
Tổng chi phí T(m) = m lần ghi mới + số bản sao < 3m.
Chi phí khấu hao mỗi append < 3 đơn vị = O(1).
```

Nếu chưa hề mở rộng thì số bản sao bằng 0, nên kết luận vẫn đúng. Trường hợp `m = 0`, tổng chi phí bằng 0.

**Chứng minh này đúng cho mọi tiền tố** gồm `m` lần thêm, bất kể giá trị được thêm là gì; không cần phân phối xác suất hay đo máy. Điểm quan trọng là tổng cấp số nhân, **không phải từng lần mở rộng riêng lẻ có chi phí hằng số**.

> Lưu ý về hệ số: Với 9 thao tác, tổng số bản sao là `1 + 2 + 4 + 8 = 15`, lớn hơn 9. Vì vậy không được khẳng định “số bản sao luôn nhỏ hơn `m`” trong mô hình này. Bất đẳng thức an toàn đã chứng minh là **số bản sao `< 2m`**; tổng vẫn là `O(m)`.

### So sánh với tăng dung lượng từng đơn vị

Nếu mảng chỉ tăng capacity từ `n` lên `n+1` mỗi lần đầy, khi thêm `m` phần tử nó phải sao chép:

```text
0 + 1 + 2 + ... + (m - 1)
= m(m - 1)/2
= Θ(m²).
```

Vì vậy tổng thêm `m` phần tử là `Θ(m^2)` theo mô hình chi phí này, tức **`Θ(m)` khấu hao cho mỗi lần thêm**. Chính **chính sách mở rộng** quyết định kết quả phân tích, không phải tên gọi “mảng động”.

## 4. Phương pháp ghi sổ / tín dụng (accounting method)

Phương pháp này đặt một **mức thu phí khấu hao** cho mỗi thao tác. Thao tác rẻ trả ít công thực tế hơn mức thu, phần còn lại được giữ như **tín dụng**; thao tác đắt dùng tín dụng đã tích lũy. Tín dụng là công cụ chứng minh toán học, không phải bộ nhớ thật hay thời gian được “vay” từ CPU.

Với mảng gấp đôi ở mục 2, thử thu **3 đơn vị cho mỗi `append`**:

- Dùng 1 đơn vị để ghi phần tử mới.
- Giữ phần còn lại để trả cho việc sao chép khi mở rộng.
- Khi mở rộng, lấy tín dụng dự trữ để thanh toán việc sao chép các phần tử cũ.

| Sau lần thêm | Phí tích lũy (3 mỗi lần) | Chi phí thực tế tích lũy | Tín dụng còn lại |
| ---: | ---: | ---: | ---: |
| 1 | 3 | 1 | 2 |
| 2 | 6 | 3 | 3 |
| 3 | 9 | 6 | 3 |
| 4 | 12 | 7 | 5 |
| 5 | 15 | 12 | 3 |
| 8 | 24 | 15 | 9 |
| 9 | 27 | 24 | 3 |

Để trở thành **chứng minh**, không chỉ là một bảng ví dụ, phải chỉ ra **tín dụng không bao giờ âm với mọi tiền tố**. Từ giới hạn tổng gộp `T(k) < 3k` cho mọi `k \ge 1`, số dư `3k - T(k) \ge 0`; do đó lịch thu phí 3 đơn vị luôn đủ chi trả. Điều kiện này cũng có thể được chứng minh bằng bất biến về số tín dụng dành cho những phần tử đã thêm kể từ lần mở rộng trước.

Nếu một phương án “ghi sổ” cho phép số dư âm rồi hứa sẽ bù ở tương lai, nó **chưa** chứng minh được chặn trên cho mọi tiền tố: chuỗi thao tác hoàn toàn có thể dừng ngay khi đang nợ. Cần một bất biến không âm hoặc một ràng buộc rõ ràng về trạng thái ban đầu.

**Ứng dụng:** cách ghi sổ phù hợp khi bạn có trực giác “thao tác rẻ trả trước cho thao tác đắt”, chẳng hạn cập nhật chỉ mục theo lô hoặc dọn dẹp định kỳ. Tuy nhiên, phải nêu chính xác đơn vị công, nơi lưu tín dụng tưởng tượng và lý do không chi vượt số đã tích lũy.

## 5. Phương pháp thế năng (potential method)

Phương pháp thế năng làm ý tưởng “dự trữ” trở nên đại số. Chọn một hàm `\Phi(D) \ge 0` trên các trạng thái hợp lệ, với `\Phi(D_0) = 0`. Thế năng cao biểu thị một khoản công dự trữ có thể dùng để bù thao tác đắt.

Định nghĩa chi phí khấu hao của thao tác thứ `i`:

\[
\hat c_i = c_i + \Phi(D_i) - \Phi(D_{i-1}).
\]

Khi cộng tất cả thao tác, các số hạng ở giữa triệt tiêu:

\[
\sum_{i=1}^{m}\hat c_i
= \sum_{i=1}^{m}c_i + \Phi(D_m)-\Phi(D_0).
\]

Do `\Phi(D_0) = 0` và `\Phi(D_m) \ge 0`, suy ra:

\[
T(m) = \sum_{i=1}^{m} c_i \le \sum_{i=1}^{m}\hat c_i.
\]

Một thao tác đắt có thể **giảm thế năng** nhiều, khiến chi phí khấu hao của chính nó vẫn nhỏ. Khác với “chi phí thực tế”, `\hat c_i` trong một phép phân tích thế năng tổng quát thậm chí có thể âm; điều cần bảo đảm là bất đẳng thức tổng và các điều kiện đối với thế năng.

### Chọn thế năng cho mảng động chỉ thêm

Đặt `n` là số phần tử, `C` là capacity (`C \ge 1`). Chọn:

\[
\Phi(n,C) = \max(0,\;2n-C).
\]

Ban đầu `(n,C)=(0,1)` nên `\Phi=0`. Hàm thế năng không âm cho mọi trạng thái.

**Trường hợp 1 — thêm khi còn chỗ (`n < C`):**

- Chi phí thực tế `c_i = 1`.
- Capacity không đổi, size tăng từ `n` lên `n+1`.
- Vì biểu thức `\max(0,2n-C)` chỉ tăng nhiều nhất 2 khi `n` tăng 1, ta có `\Delta\Phi \le 2`.

Vì vậy `\hat c_i = 1 + \Delta\Phi \le 3`.

**Trường hợp 2 — mảng đầy (`n = C`), phải gấp đôi:**

- Sao chép `C` phần tử cũ và ghi phần tử mới: `c_i = C+1`.
- Trước khi thêm: `\Phi_{\text{trước}} = \max(0,2C-C)=C`.
- Sau khi thêm: `n'=C+1`, `C'=2C`, nên `\Phi_{\text{sau}} = \max(0,2(C+1)-2C)=2`.
- Biến thiên `\Delta\Phi = 2-C`.

Suy ra:

\[
\hat c_i = (C+1)+(2-C)=3.
\]

**Cả hai trường hợp đều có chi phí khấu hao không quá 3**, vì thế với mọi `m` lần thêm liên tiếp:

\[
T(m) \le \sum_{i=1}^{m}\hat c_i \le 3m,
\]

hay `O(1)` khấu hao mỗi `append`.

Ví dụ ở lần thêm thứ 9: trước đó `n=C=8`, thế năng là `8`; sau khi nở capacity thành `16` và thêm phần tử thứ 9, thế năng còn `2`. Chi phí thực tế `9` được bù bởi việc giảm `6` đơn vị thế năng, tạo chi phí khấu hao `9-6=3`.

| Thao tác | Chi phí thực tế | `\Phi` trước | `\Phi` sau | Chi phí khấu hao |
| --- | ---: | ---: | ---: | ---: |
| `append(1)` | 1 | 0 | 1 | 2 |
| `append(2)` | 2 | 1 | 2 | 3 |
| `append(3)` | 3 | 2 | 2 | 3 |
| `append(4)` | 1 | 2 | 4 | 3 |
| `append(5)` | 5 | 4 | 2 | 3 |
| `append(9)` (ngay sau 8 lần thêm) | 9 | 8 | 2 | 3 |

Bảng chỉ liệt kê một số lần, nhưng lập luận theo hai trường hợp ở trên bao phủ **mọi lần thêm**.

## 6. Ví dụ Java 17+: quan sát từng lần mở rộng

Đây là chương trình **độc lập và chạy được** có tên tệp `AmortizedDemo.java`. Nó tự hiện thực mảng động theo đúng quy tắc capacity `1, 2, 4, 8, \ldots` để đo **số lần ghi phần tử mới** và **số phần tử sao chép**. Vì chỉ quan sát 9 phần tử, chương trình không cần xử lý trường hợp capacity nhân đôi vượt giới hạn `int`; một mảng động phục vụ sản phẩm phải xử lý giới hạn kích thước và thất bại cấp phát.

```java
public class AmortizedDemo {
    private static final class IntVector {
        private int[] elements = new int[1];
        private int size = 0;
        private int lastCost = 0;
        private long writes = 0;
        private long copies = 0;

        void append(int value) {
            int copiedThisTime = 0;

            if (size == elements.length) {
                int[] expanded = new int[elements.length * 2];
                for (int i = 0; i < size; i++) {
                    expanded[i] = elements[i];
                    copies++;
                    copiedThisTime++;
                }
                elements = expanded;
            }

            elements[size] = value;
            size++;
            writes++;
            lastCost = copiedThisTime + 1;
        }

        int size() {
            return size;
        }

        int capacity() {
            return elements.length;
        }

        int lastCost() {
            return lastCost;
        }

        long writes() {
            return writes;
        }

        long copies() {
            return copies;
        }
    }

    public static void main(String[] args) {
        IntVector vector = new IntVector();

        for (int value = 1; value <= 9; value++) {
            vector.append(value);
            System.out.printf(
                    "append %d: size=%d, capacity=%d, cost=%d%n",
                    value, vector.size(),
                    vector.capacity(), vector.lastCost());
        }

        System.out.printf(
                "writes=%d, copies=%d, total=%d%n",
                vector.writes(), vector.copies(),
                vector.writes() + vector.copies());
    }
}
```

Biên dịch và chạy bằng JDK 17+ từ thư mục chứa tệp:

```bash
javac AmortizedDemo.java
java AmortizedDemo
```

Kết quả chuẩn chính xác:

```text
append 1: size=1, capacity=1, cost=1
append 2: size=2, capacity=2, cost=2
append 3: size=3, capacity=4, cost=3
append 4: size=4, capacity=4, cost=1
append 5: size=5, capacity=8, cost=5
append 6: size=6, capacity=8, cost=1
append 7: size=7, capacity=8, cost=1
append 8: size=8, capacity=8, cost=1
append 9: size=9, capacity=16, cost=9
writes=9, copies=15, total=24
```

Chương trình cho thấy **lần thêm thứ 9 đắt nhất trong mẫu** nhưng tổng chi phí vẫn gần tuyến tính với số lần thêm. Đây là minh họa thực nghiệm cho mô hình đếm thao tác; **chứng minh khấu hao** nằm ở bất đẳng thức cho mọi `m` trong mục 3 và 5. Không suy ra chặn `O(1)` từ việc chỉ chạy 9 phần tử. Thời gian thực bằng mili giây còn tùy JVM, phần cứng, bộ nhớ và thu gom rác.

## 7. Ví dụ 2: bộ đếm nhị phân

Giả sử một bộ đếm không âm bắt đầu ở `0`, có đủ bit để tăng mà không tràn. Một phép `INCREMENT` cộng 1 theo quy tắc:

1. Đổi các bit `1` liên tiếp ở cuối (trailing ones) thành `0`.
2. Đổi bit `0` đầu tiên ngay trước chúng thành `1`; nếu cần thì thêm bit cao mới.

Mô hình chi phí là **số bit bị lật**, mỗi lần đổi `0↔1` tốn 1 đơn vị. Ví dụ:

```text
0000 -> 0001 : 1 bit
0001 -> 0010 : 2 bit
0010 -> 0011 : 1 bit
0011 -> 0100 : 3 bit
...
0111 -> 1000 : 4 bit
```

Một lần tăng từ `2^k-1` lên `2^k` lật `k+1` bit, tốn `Θ(k)`, tức `Θ(\log v)` đối với giá trị bộ đếm `v` phù hợp. Tuy nhiên những lần lật rất nhiều bit không xuất hiện thường xuyên.

**Phân tích tổng gộp:** trong `m` lần tăng bắt đầu từ 0, bit thứ `j` (đếm từ bit thấp nhất là `j=0`) đổi trạng thái nhiều nhất `\lfloor m/2^j\rfloor` lần. Vậy tổng số lần lật bit không vượt:

\[
\sum_{j\ge0}\left\lfloor\frac{m}{2^j}\right\rfloor
< m+\frac m2+\frac m4+\cdots
= 2m.
\]

Do đó tổng chi phí `O(m)`, tức **`O(1)` khấu hao cho mỗi `INCREMENT`**, dù một lần tăng cá biệt có thể lật nhiều bit.

**Phân tích thế năng:** chọn `\Phi` bằng **số bit 1 đang có**. Nếu có `t` bit 1 liên tiếp ở cuối, một lần tăng sẽ:

- Lật `t+1` bit nên `c_i=t+1`.
- Xóa `t` bit 1 và tạo thêm một bit 1 nên `\Delta\Phi=1-t`.

Vì vậy `\hat c_i=(t+1)+(1-t)=2` cho mọi lần tăng. Từ trạng thái 0 có `\Phi_0=0`, nên tổng chi phí tối đa `2m`. Không cần dự đoán thao tác nào sẽ gặp chuỗi toàn bit 1.

Điều kiện **không tràn** cần được nêu: nếu sử dụng kiểu nguyên có độ rộng cố định và phép cộng tràn, hậu điều kiện và số bit lật phải được định nghĩa lại cho mô hình mới.

## 8. Ví dụ 3: ngăn xếp với MULTIPOP

Xét ngăn xếp bắt đầu **rỗng** hỗ trợ ba thao tác:

- `PUSH(x)`: đưa đúng một phần tử vào đỉnh; chi phí 1.
- `POP()`: bỏ phần tử đỉnh nếu có; chi phí 1 khi thực sự bỏ, 0 khi ngăn xếp rỗng theo mô hình đếm này.
- `MULTIPOP(k)`: bỏ tối đa `k` phần tử từ đỉnh; chi phí đúng bằng số phần tử thực sự bỏ.

Giả sử thao tác cơ bản thêm/xóa nút không làm phát sinh chi phí tái cấp phát (ví dụ dùng ngăn xếp liên kết phù hợp). Một lời gọi `MULTIPOP(k)` có thể tốn `Θ(k)` nếu đủ phần tử. Nhưng với một chuỗi bắt đầu từ rỗng:

**Lập luận tổng gộp:** mỗi phần tử được `PUSH` vào **một lần** và bị xóa bởi `POP` hoặc `MULTIPOP` **tối đa một lần**. Số lần xóa không thể vượt số lần thêm. Nếu chuỗi có `m` lời gọi API, tổng số lần thêm không vượt `m`; vì vậy tổng chi phí cơ bản `≤ 2m`.

**Lập luận thế năng:** chọn `\Phi(D)=\text{size(stack)}`, ban đầu bằng 0:

| Thao tác | Chi phí thực tế | `\Delta\Phi` | Chi phí khấu hao |
| --- | ---: | ---: | ---: |
| `PUSH(x)` | 1 | +1 | 2 |
| `POP()` lấy được phần tử | 1 | −1 | 0 |
| `POP()` khi rỗng | 0 | 0 | 0 |
| `MULTIPOP(k)` thực sự xóa `t` phần tử | `t` | `-t` | 0 |

Vì thế mỗi lời gọi có chi phí khấu hao nhiều nhất 2, và chuỗi `m` lời gọi có tổng chi phí `O(m)`. Lần `MULTIPOP` lớn được “trả” bằng thế năng tích lũy qua các lần `PUSH` trước đó.

Nếu ngăn xếp **không bắt đầu từ rỗng**, có thể xóa các phần tử đã tồn tại trước chuỗi mà chưa từng trả phí `PUSH` trong chuỗi. Khi đó phải cộng phần chi phí tương ứng trạng thái ban đầu, hoặc đặt thế năng/điều kiện đầu vào phù hợp. Không được sao chép kết luận `≤2m` mà bỏ điều kiện khởi tạo.

## 9. Chuỗi thao tác có thể làm hỏng một chứng minh khấu hao

Độ phức tạp khấu hao là thuộc tính của **cấu trúc dữ liệu + quy tắc vận hành + tập chuỗi hợp lệ**, không chỉ của một tên thao tác.

### Ví dụ: co mảng quá sớm

Giả sử mảng:

- **Gấp đôi** khi `append` gặp mảng đầy.
- **Giảm một nửa** capacity khi một lần xóa làm `size \le capacity/2`.
- Mỗi lần đổi capacity đều phải sao chép các phần tử còn lại.

Xét trạng thái `size=k+1`, `capacity=2k` (với `k` đủ lớn). Một lần xóa làm `size=k`, kích hoạt co capacity thành `k` và sao chép `k` phần tử. Ngay lần thêm tiếp theo, mảng có `size=capacity=k` nên phải nở lại thành `2k`, tiếp tục sao chép `k` phần tử trước khi ghi. Hai thao tác `remove, append` có thể lặp mãi tại kích thước gần `k`: **mỗi thao tác gây `Θ(k)` sao chép**.

Vì vậy, quy tắc “nở ở 100% đầy, co ngay tại 50%” có thể tạo ra **dao động capacity (thrashing)**, khiến kết luận thêm/xóa khấu hao `O(1)` không còn đúng với lập luận chỉ xét `append`. Một chiến lược phổ biến là tạo **khoảng cách ngưỡng**: chỉ co khi độ đầy thấp hơn đáng kể, ví dụ quanh `1/4`, và phân tích lại hàm thế năng cho **cả hai loại thao tác**. Không nên áp dụng máy móc thế năng `\max(0,2n-C)` của phần chỉ thêm cho chương trình đã có xóa/co.

### Những yếu tố khác cũng làm đổi giới hạn

- **Cấu trúc lưu trữ:** thao tác `PUSH` trên ngăn xếp có cấp phát lại và sao chép cần phân tích thêm chi phí tái cấp phát.
- **Trạng thái ban đầu:** mảng/stack có sẵn nhiều phần tử có thể phát sinh chi phí ngay từ thao tác đầu; có thể cần cộng `O(n_0)` hoặc ràng buộc về dung lượng ban đầu.
- **Quy tắc chi phí:** số phép gán mảng khác thời gian nanosecond; so sánh chuỗi dài hoặc thao tác I/O có chi phí không hằng số.
- **Giới hạn môi trường:** cấp phát có thể thất bại hoặc tràn kích thước số nguyên; chứng minh trên mô hình lý tưởng cần nêu phạm vi áp dụng khi chuyển vào chương trình thật.
- **Hành vi ngẫu nhiên:** một hash table có chi phí trung bình/kỳ vọng tốt không tự có chặn khấu hao tất định cho mọi chuỗi khóa đối kháng nếu chưa có giả định phù hợp về hàm băm và phân phối khóa.

Đặc biệt, đừng suy luận “thêm mảng động khấu hao `O(1)`” thành “mọi thao tác liên quan đến mảng động đều `O(1)`”: chèn/xóa ở đầu mảng phải dịch chuyển nhiều phần tử, thường `O(n)` cho một lần gọi, và không được bao phủ bởi chứng minh `append` nêu trên.

## 10. Chọn phương pháp và trình bày một chứng minh đúng

| Phương pháp | Làm gì? | Khi nào thường dễ dùng? |
| --- | --- | --- |
| **Tổng gộp** | Đếm trực tiếp tất cả công việc trong `m` thao tác; chia cho `m`. | Số lần sao chép hoặc số lần lật bit dễ được chặn bằng cấp số nhân/đếm tần suất. |
| **Ghi sổ** | Gán mức phí khấu hao, để dành tín dụng trong những thao tác rẻ; chứng minh không âm. | Có thể gắn khoản trả trước với những đối tượng hay sự kiện cần xử lý về sau. |
| **Thế năng** | Chọn `\Phi` trên trạng thái, phân tích `c_i+\Delta\Phi` rồi cộng dồn. | Trạng thái biến đổi phức tạp; cần cân đối nhiều loại thao tác đắt/rẻ trong cùng chuỗi. |

Quy trình đề nghị:

1. **Xác định đặc tả thao tác:** `append`, `remove`, `increment`, `multipop` tác động đến trạng thái như thế nào; có cho phép thao tác trên cấu trúc rỗng không?
2. **Công bố mô hình chi phí:** đếm phép gán, lần sao chép, bit flip, phép so sánh hay đại lượng nào.
3. **Cố định trạng thái khởi tạo:** rỗng hay có `n_0` phần tử; nếu không rỗng thì phần việc ban đầu được tính ra sao.
4. **Xét một chuỗi bất kỳ có `m` thao tác hợp lệ:** không chỉ một chuỗi thuận lợi. Nếu chi phí từng thao tác phụ thuộc trạng thái, nêu rõ trạng thái trước/sau.
5. **Chọn tổng gộp, ghi sổ hoặc thế năng:** với ghi sổ chứng minh tín dụng không âm ở mọi tiền tố; với thế năng chứng minh `\Phi(D_i)\ge0` và xử lý `\Phi(D_0)`.
6. **Cộng và rút chặn tổng:** chứng minh `T(m)`, rồi mới phát biểu chi phí khấu hao cho mỗi thao tác.
7. **Kiểm tra phản ví dụ:** xen kẽ thao tác, kích thước nhỏ, ngưỡng mở rộng/co, và trường hợp trạng thái đầu không rỗng.

Nếu hàm thế năng không bắt đầu ở 0 nhưng vẫn không âm, công thức tổng quát là:

\[
T(m)\le\sum_{i=1}^{m}\hat c_i+\Phi(D_0).
\]

Giá trị `\Phi(D_0)` có thể là một hằng số khi trạng thái đầu cố định, hoặc là một khoản cần nêu rõ khi kích thước đầu vào thay đổi.

## 11. Những hiểu nhầm thường gặp

1. **“Khấu hao `O(1)` nghĩa là không bao giờ có độ trễ lớn.”** Sai: lần nở mảng vẫn có thể tốn `Θ(n)`, ảnh hưởng đến latency nhạy cảm; chặn khấu hao chỉ kiểm soát tổng chi phí chuỗi.
2. **“Khấu hao là average-case dựa trên xác suất.”** Sai: các chứng minh bên trên áp dụng cho mọi chuỗi hợp lệ từ trạng thái quy định mà không cần phân phối.
3. **“Lấy worst-case `O(n)` rồi nhân `m` là đáp án tốt nhất.”** Đây là một chặn trên thô, thường bỏ qua ràng buộc các lần đắt không thể liên tiếp.
4. **“Một vài phép đo đã chứng minh `O(1)` khấu hao.”** Sai: đo đạc giúp kiểm chứng triển khai, nhưng cần lập luận đúng cho mọi độ dài `m` được xét.
5. **“Mọi khoản tín dụng có thể âm miễn về sau trả bù.”** Sai cho lập luận ghi sổ kiểu trả trước; chuỗi có thể kết thúc ở bất kỳ tiền tố nào.
6. **“Chọn hàm thế năng nào cũng được.”** Hàm phải được xác định trên trạng thái, kiểm soát chênh lệch chi phí và có điều kiện đầu/cuối phù hợp; một hàm âm không có chặn dưới dễ làm kết luận sai.
7. **“Đã chứng minh thêm nhanh thì thêm và xóa xen kẽ cũng nhanh.”** Sai: phải phân tích cả cơ chế co và các chuỗi khiến capacity dao động.
8. **“Chi phí phần tử/bit chính là thời gian chạy thực tế.”** Không nhất thiết; đó là mô hình độ phức tạp với đơn vị được chọn để chứng minh.

## 12. Bài tập tự kiểm tra

**Bài 1 — Mảng động.** Với capacity ban đầu 1 và chính sách gấp đôi, hãy ghi các chi phí của `append` thứ 1 đến thứ 5 theo mô hình một lần ghi phần tử mới + một đơn vị cho mỗi phần tử cũ được sao chép. Tổng và chi phí trung bình thực tế của 5 lần thêm là bao nhiêu? Bài toán có làm mất chặn khấu hao `O(1)` không?

**Bài 2 — So sánh quy tắc mở rộng.** Chứng minh tổng số bản sao khi tăng capacity mỗi lần đúng 1 chỗ trong `m` lần thêm bắt đầu từ capacity 1 là `\Theta(m^2)`. Nếu thay bằng gấp đôi, tổng bản sao được chặn như thế nào?

**Bài 3 — Thế năng.** Với mảng `n=C=8` trước khi mở rộng, dùng `\Phi(n,C)=\max(0,2n-C)` tính chi phí thực tế, thế năng trước/sau và chi phí khấu hao của lần thêm thứ 9.

**Bài 4 — Bộ đếm nhị phân.** Với `0111 → 1000`, có bao nhiêu bit thay đổi? Dùng thế năng là số bit 1 để tính chi phí khấu hao.

**Bài 5 — MULTIPOP.** Một ngăn xếp rỗng thực hiện 5 lần `PUSH` rồi một lần `MULTIPOP(5)`. Lời gọi cuối có chi phí thực tế bao nhiêu? Tổng chi phí sáu lời gọi và chặn khấu hao theo phương pháp thế năng là gì?

**Bài 6 — Phản ví dụ.** Giải thích vì sao quy tắc co mảng ở ngưỡng nửa đầy có thể làm chuỗi `remove, append, remove, append, \ldots` lặp các lần sao chép `\Theta(k)`. Nêu điều gì phải thay đổi trước khi khẳng định thời gian khấu hao hằng số cho cả thêm và xóa.

**Đáp án gợi ý:**

1. Dãy chi phí `1,2,3,1,5`; tổng `12`, trung bình thực tế `12/5 = 2{,}4` đơn vị cho chuỗi cụ thể. Chặn khấu hao `O(1)` vẫn đúng vì chứng minh xét mọi `m`.
2. Tổng sao chép `0+1+\cdots+(m-1)=m(m-1)/2=\Theta(m^2)`; gấp đôi cho tổng sao chép `<2m`.
3. Chi phí thực tế `9`; `\Phi_{\text{trước}}=8`, `\Phi_{\text{sau}}=2`; chi phí khấu hao `9+2-8=3`.
4. Bốn bit đổi; số bit 1 từ 3 còn 1; chi phí khấu hao `4+(1-3)=2`.
5. `MULTIPOP(5)` thực sự xóa 5 phần tử, chi phí 5. Tổng `5+5=10`; ngân sách tối đa `2` cho mỗi `PUSH` và `0` cho `MULTIPOP`, chặn trên của sáu lời gọi là 10 đơn vị theo thế năng này (cũng `≤2m=12`).
6. Khi size đang khoảng `k+1` và capacity `2k`, xóa làm size xuống `k` và co còn `k`; thêm ngay phải nở thành `2k`. Lặp lại gây sao chép lớn liên tiếp. Cần đặt ngưỡng co thấp hơn ngưỡng nở và **chứng minh lại** cho tập thao tác gồm thêm/xóa.

## Ghi nhớ

**Chi phí khấu hao** là cách phân bổ chi phí của **cả chuỗi thao tác** để đưa ra chặn trên cho mọi chuỗi hợp lệ, không phải cam kết từng thao tác luôn rẻ và không phải trung bình xác suất. Ba phương pháp tổng gộp, ghi sổ và thế năng đều phải dẫn đến bất đẳng thức về **tổng chi phí thực tế**. Mảng động gấp đôi, bộ đếm nhị phân và ngăn xếp có `MULTIPOP` minh họa cùng một nguyên lý: công việc đắt có giới hạn về tần suất hoặc được “trả” bởi công việc trước đó. Khi quy tắc thao tác hoặc trạng thái ban đầu thay đổi, phải xem lại chứng minh.
