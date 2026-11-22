# Tổng tiền tố và truy vấn tổng đoạn

**Tổng tiền tố (prefix sum)** là kỹ thuật tiền xử lý giúp tính nhanh tổng của một đoạn liên tiếp trong mảng. Thay vì cộng lại tất cả phần tử mỗi khi nhận truy vấn, ta lưu các tổng tích lũy từ đầu mảng. Với mảng **không thay đổi**, sau O(n) thời gian xây dựng, một truy vấn tổng đoạn có thể trả lời bằng đúng một phép trừ giữa hai giá trị đã tính sẵn, tức O(1) trong mô hình RAM thông thường.

Kỹ thuật này xuất hiện trong xử lý dãy, thống kê cửa sổ, truy vấn nhiều khoảng, đếm tần suất, tổng trên ma trận và là nền tảng để hiểu các cấu trúc hỗ trợ truy vấn phức tạp hơn.

**Mục tiêu:** tự xây dựng được mảng tổng tiền tố; chuyển đổi đúng giữa chỉ số 0-based/1-based và đoạn đóng/nửa mở; chứng minh công thức truy vấn; phân tích độ phức tạp; lựa chọn kiểu số tránh tràn; nhận biết trường hợp cần Fenwick tree, segment tree hoặc mảng hiệu thay cho tổng tiền tố tĩnh.

## 1. Vì sao cần tổng tiền tố?

Cho mảng có n phần tử:

`a = [3, -2, 5, 1, -4, 6]`

Giả sử có nhiều truy vấn: “tổng các phần tử từ vị trí L đến R là bao nhiêu?”. Nếu dùng cách trực tiếp, với mỗi truy vấn ta cộng tất cả phần tử trong đoạn được hỏi.

Ví dụ, đoạn từ vị trí 2 tới 5 theo chỉ số bắt đầu bằng 1 là:

`(-2) + 5 + 1 + (-4) = 0`.

Một truy vấn dài k phần tử tốn Θ(k) phép cộng. Trường hợp xấu nhất đoạn có n phần tử nên tốn Θ(n) cho mỗi truy vấn. Với q truy vấn, tổng thời gian có thể tới **Θ(nq)** nếu nhiều truy vấn đều bao phủ phần lớn mảng; nếu tính cả việc đọc mảng, chi phí là Θ(n + tổng độ dài các đoạn truy vấn).

Khi mảng không bị chỉnh sửa giữa các truy vấn, ta đang cộng lại nhiều đoạn chồng lấn. Tổng tiền tố chuyển một phần công việc lặp đi lặp lại thành bước tiền xử lý duy nhất.

## 2. Định nghĩa với chỉ số 0-based và đoạn nửa mở

Sử dụng quy ước an toàn, phổ biến trong lập trình:

- Mảng gốc `a[0], a[1], ..., a[n-1]` có n phần tử.
- Mảng `prefix` có **n + 1** phần tử, được đánh chỉ số từ 0 tới n.
- Đặt `prefix[0] = 0`, tức tổng của **đoạn rỗng**.
- Với `0 ≤ i < n`, xây dựng `prefix[i+1] = prefix[i] + a[i]`.

Tương đương:

`prefix[k] = a[0] + a[1] + ... + a[k-1]` với `1 ≤ k ≤ n`.

Như vậy, `prefix[k]` chứa tổng của **k phần tử đầu tiên**, không phải tổng “đến phần tử chỉ số k”. Cách đặt n + 1 ô tránh phải xử lý riêng các đoạn bắt đầu tại vị trí 0.

Ví dụ:

| Chỉ số `k` | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `a[k]` (nếu tồn tại) | 3 | -2 | 5 | 1 | -4 | 6 | — |
| `prefix[k]` | 0 | 3 | 1 | 6 | 7 | 3 | 9 |

Đối với đoạn **nửa mở** `[l, r)`, gồm các phần tử có chỉ số từ l đến r − 1 và thỏa `0 ≤ l ≤ r ≤ n`:

**`sum(l, r) = prefix[r] − prefix[l]`.**

Ví dụ:

- `[0, 4)` chứa `3, -2, 5, 1` ⇒ `prefix[4] − prefix[0] = 7 − 0 = 7`.
- `[2, 6)` chứa `5, 1, -4, 6` ⇒ `prefix[6] − prefix[2] = 9 − 1 = 8`.
- `[3, 5)` chứa `1, -4` ⇒ `prefix[5] − prefix[3] = 3 − 6 = -3`.
- `[4, 4)` là đoạn rỗng ⇒ `prefix[4] − prefix[4] = 0`.

**Lợi thế của đoạn nửa mở:** độ dài luôn là `r − l`; ghép hai đoạn liền kề `[l,m)` và `[m,r)` thành `[l,r)` mà không trùng phần tử; đoạn rỗng biểu diễn tự nhiên khi `l=r`.

## 3. Công thức cho ba cách đánh chỉ số thường gặp

Đề bài có thể sử dụng chỉ số và quy ước khác nhau. Phải đọc đúng định nghĩa L, R trước khi viết code.

| Quy ước của truy vấn | Phần tử thuộc đoạn | Điều kiện hợp lệ | Công thức với `prefix[0]=0` |
|---|---|---|---|
| 0-based, nửa mở `[l,r)` | `a[l]..a[r-1]` | `0 ≤ l ≤ r ≤ n` | `prefix[r] − prefix[l]` |
| 0-based, hai đầu bao gồm `[l,r]` | `a[l]..a[r]` | `0 ≤ l ≤ r < n` | `prefix[r+1] − prefix[l]` |
| 1-based, hai đầu bao gồm `[L,R]` | Phần tử thứ L tới thứ R | `1 ≤ L ≤ R ≤ n` | `prefix[R] − prefix[L−1]` |

Ví dụ trên mảng `[3,-2,5,1,-4,6]`, đoạn gồm các phần tử `5,1,-4` có thể viết:

- 0-based nửa mở `[2,5)`: `prefix[5] − prefix[2] = 3 − 1 = 2`.
- 0-based đóng `[2,4]`: `prefix[4+1] − prefix[2] = 2`.
- 1-based đóng `[3,5]`: `prefix[5] − prefix[3−1] = 2`.

Ba công thức cho **cùng một đoạn thực tế**. Lỗi lệch một đơn vị (off-by-one) thường xuất hiện khi nhớ một công thức nhưng áp dụng cho quy ước khác.

Nếu đề bài định nghĩa đoạn trống hợp lệ, đoạn nửa mở cho phép `l=r` và kết quả 0. Với đoạn đóng, thường chỉ xét `l≤r`; không tự cho rằng `L>R` là hợp lệ khi đề bài không nói vậy.

## 4. Chứng minh tính đúng đắn

### 4.1. Bất biến khi xây dựng

Sau khi xử lý i phần tử đầu tiên, bất biến là:

`prefix[i] = Σ_{j=0}^{i−1} a[j]`.

**Cơ sở:** trước khi đọc phần tử nào, `i=0` và `prefix[0]=0` đúng bằng tổng rỗng.

**Bước quy nạp:** giả sử `prefix[i]` đúng. Khi xử lý `a[i]`, chương trình đặt `prefix[i+1] = prefix[i] + a[i]`. Thay giả thiết quy nạp vào, ta được tổng đúng của `i+1` phần tử đầu. Vì vậy bất biến tiếp tục đúng.

**Kết luận:** sau n bước, mọi phần tử `prefix[0..n]` đều biểu diễn đúng tổng tiền tố theo định nghĩa, với giả thiết phép cộng không bị tràn hoặc mất tính chính xác theo kiểu số.

### 4.2. Chứng minh truy vấn bằng hiệu hai tiền tố

Với `0 ≤ l ≤ r ≤ n`:

`prefix[r] = a[0] + ... + a[l−1] + a[l] + ... + a[r−1]`;

`prefix[l] = a[0] + ... + a[l−1]`.

Lấy hiệu hai biểu thức, các phần tử trước l triệt tiêu, còn lại:

`prefix[r] − prefix[l] = a[l] + ... + a[r−1]`.

Đây chính là tổng của đoạn `[l,r)`. Chứng minh không yêu cầu các phần tử dương, đã sắp xếp hay không trùng nhau. **Số âm hoàn toàn hợp lệ**.

Lưu ý: việc lấy hiệu đúng về mặt toán học; khi triển khai bằng kiểu số hữu hạn, phải bảo đảm các tổng trung gian và phép trừ không tràn.

## 5. Xây dựng và trả lời truy vấn trong Java

Ý tưởng tối giản:

~~~java
long[] prefix = new long[a.length + 1];
for (int i = 0; i < a.length; i++) {
    prefix[i + 1] = prefix[i] + a[i];
}

// Tổng của đoạn nửa mở [l, r):
long sum = prefix[r] - prefix[l];
~~~

Đây là **mảnh mã minh họa**, chưa phải chương trình độc lập; cần có mảng `a` và hai chỉ số `l, r` hợp lệ.

Nếu mọi phần tử gốc nằm trong `int`, tổng có thể vượt `int`. Sử dụng `long[] prefix` nếu chứng minh được tổng tiền tố và tổng đoạn nằm trong miền `long`. Với dữ liệu có giá trị rất lớn hoặc độ dài rất dài, cần phân tích giới hạn kỹ hơn hoặc dùng số nguyên tùy ý như `BigInteger`, khi đó chi phí phép toán không còn được xem hằng số một cách vô điều kiện.

**Một lợi ích về bộ nhớ:** không bắt buộc phải lưu riêng mảng `a` nếu chỉ cần tổng đoạn và toàn bộ truy vấn xuất hiện sau khi đọc xong dữ liệu. Ta có thể đọc lần lượt từng giá trị, cập nhật `prefix` và bỏ giá trị gốc; nhờ vậy chỉ dùng một mảng `long[n+1]`.

## 6. Phân tích độ phức tạp

Giả sử phép cộng/trừ trên `long` và truy cập một phần tử mảng có chi phí O(1) theo mô hình RAM:

- **Xây dựng:** vòng lặp qua n phần tử, mỗi lần cập nhật một tổng ⇒ Θ(n) thời gian.
- **Một truy vấn:** đọc hai ô và trừ ⇒ Θ(1) thời gian.
- **q truy vấn:** Θ(q) thời gian sau tiền xử lý.
- **Tổng:** Θ(n + q) thời gian nếu cần xây dựng và trả lời q truy vấn.
- **Bộ nhớ:** Θ(n) cho mảng `prefix`; nếu lưu thêm mảng gốc sẽ tốn thêm Θ(n) nhưng vẫn cùng bậc.

Cách cộng trực tiếp từng đoạn tốn Θ(r−l) với một truy vấn `[l,r)`; tổng là Θ(n + Σ_k (r_k−l_k)) nếu tính cả việc đọc dữ liệu gốc. Trong trường hợp các đoạn đều dài gần n, chi phí trở thành Θ(nq). Tuy nhiên, nếu chỉ có **một truy vấn** và không cần sử dụng lại dữ liệu, quét trực tiếp có thể đơn giản và tiết kiệm bộ nhớ hơn. Tổng tiền tố đáng giá nhất khi có **nhiều truy vấn trên mảng tĩnh**.

**Thời gian và không gian là hai đánh đổi khác nhau:** tiết kiệm thời gian trả lời truy vấn bằng cách chi thêm Θ(n) bộ nhớ cho dữ liệu tiền xử lý. Nếu bộ nhớ rất hạn chế hoặc truy vấn xuất hiện trước khi có đủ dữ liệu, cần lựa chọn khác.

Với đầu ra là q số nguyên, bản thân việc xuất q dòng đã cần xử lý ít nhất lượng ký tự tương ứng. Đánh giá Θ(n + q) thường xem mỗi đáp án kiểu `long` có độ dài ký tự bị chặn và I/O được tối ưu bằng bộ đệm.

## 7. Ví dụ Java 17+ hoàn chỉnh: truy vấn nhiều đoạn

**Hợp đồng nhập/xuất của ví dụ:**

- Dòng đầu gồm hai số nguyên `n q`: số phần tử và số truy vấn.
- Tiếp theo có đúng n số nguyên có dấu, có thể nằm trên một hoặc nhiều dòng.
- Mỗi truy vấn gồm `L R`, dùng **chỉ số 1-based và hai đầu bao gồm**, với `1 ≤ L ≤ R ≤ n`.
- In một dòng cho mỗi truy vấn, theo đúng thứ tự.
- Giả sử `n, q` là số không âm vừa kiểu `int`, mảng cấp phát được trong bộ nhớ, mỗi phần tử nhập vừa kiểu `long`, và tất cả tổng tiền tố cũng như phép trừ dùng để trả lời truy vấn đều vừa kiểu `long`. Nếu `n=0` thì `q=0` theo hợp đồng.

Lưu tệp **`PrefixSumQueries.java`**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.util.StringTokenizer;

public class PrefixSumQueries {
    private static final class FastScanner {
        private final BufferedReader reader =
                new BufferedReader(new InputStreamReader(System.in));
        private StringTokenizer tokens = new StringTokenizer("");

        String next() throws IOException {
            while (!tokens.hasMoreTokens()) {
                String line = reader.readLine();
                if (line == null) {
                    throw new EOFException("Unexpected end of input");
                }
                tokens = new StringTokenizer(line);
            }
            return tokens.nextToken();
        }

        int nextInt() throws IOException {
            return Integer.parseInt(next());
        }

        long nextLong() throws IOException {
            return Long.parseLong(next());
        }
    }

    public static void main(String[] args) throws Exception {
        FastScanner in = new FastScanner();
        int n = in.nextInt();
        int q = in.nextInt();

        if (n < 0 || q < 0 || (n == 0 && q > 0)) {
            throw new IllegalArgumentException("Invalid n or q");
        }

        long[] prefix = new long[n + 1];
        for (int i = 0; i < n; i++) {
            long value = in.nextLong();
            prefix[i + 1] = Math.addExact(prefix[i], value);
        }

        BufferedWriter out =
                new BufferedWriter(new OutputStreamWriter(System.out));

        for (int k = 0; k < q; k++) {
            int left = in.nextInt();
            int right = in.nextInt();

            if (left < 1 || left > right || right > n) {
                throw new IllegalArgumentException("Invalid query range");
            }

            long answer =
                    Math.subtractExact(prefix[right], prefix[left - 1]);
            out.write(Long.toString(answer));
            out.newLine();
        }

        out.flush();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PrefixSumQueries.java
java PrefixSumQueries
~~~

Ví dụ nhập vào:

~~~text
6 5
3 -2 5 1 -4 6
1 4
2 2
3 6
4 5
1 6
~~~

Kết quả in chính xác:

~~~text
7
-2
8
-3
9
~~~

**Đối chiếu từng đáp án** với mảng `a=[3,-2,5,1,-4,6]` và `prefix=[0,3,1,6,7,3,9]`:

| Truy vấn 1-based | Hiệu hai tiền tố | Tổng |
|---|---|---:|
| `[1,4]` | `prefix[4]-prefix[0] = 7-0` | 7 |
| `[2,2]` | `prefix[2]-prefix[1] = 1-3` | -2 |
| `[3,6]` | `prefix[6]-prefix[2] = 9-1` | 8 |
| `[4,5]` | `prefix[5]-prefix[3] = 3-6` | -3 |
| `[1,6]` | `prefix[6]-prefix[0] = 9-0` | 9 |

**Các quyết định triển khai cần hiểu:**

1. `prefix` có n + 1 ô, `prefix[0]` mặc định bằng 0 vì Java khởi tạo mảng số nguyên với giá trị 0.
2. Chỉ số của truy vấn là **1-based đóng**, nên dùng `prefix[right] - prefix[left-1]`. Nếu đề bài dùng 0-based đóng thì công thức phải đổi.
3. `Math.addExact` và `Math.subtractExact` ném `ArithmeticException` nếu phép toán `long` bị tràn. Điều này giúp phát hiện vi phạm giả thiết kiểu số; nó **không** làm phép tính có độ chính xác vô hạn.
4. `BufferedReader`/`StringTokenizer` đọc các token qua nhiều dòng, còn `BufferedWriter` ghi nhiều kết quả mà không giữ toàn bộ đầu ra trong một `StringBuilder`.
5. Thời gian tiền xử lý Θ(n), mỗi truy vấn Θ(1) về phép toán số, bộ nhớ phụ Θ(n) cho `prefix` cộng bộ đệm I/O cố định. Chương trình không cần giữ riêng mảng gốc.

## 8. Lỗi tràn số và miền giá trị

Cho `1 ≤ n ≤ 200_000`, `|a[i]| ≤ 10^9`. Một phần tử vừa trong `int`, nhưng tổng tiền tố có thể đạt trị tuyệt đối:

`n × 10^9 = 2 × 10^14`.

Vì vậy `int[] prefix` không đủ; `long[]` phù hợp cho bộ giới hạn này. Phải xét cả **giá trị trung gian**, không chỉ kết quả cuối cùng.

Ví dụ đặc biệt:

`a = [Long.MAX_VALUE, 1, -Long.MAX_VALUE, -1]`

Tổng cả mảng bằng 0 về mặt toán học. Nhưng tiền tố thứ hai bằng `Long.MAX_VALUE + 1`, vượt miền `long`, nên **không thể** lưu các tiền tố một cách chính xác trong `long[]`. Chương trình ví dụ sẽ ném lỗi tràn tại `Math.addExact`. Không được lập luận “tổng các đoạn được hỏi nhỏ nên mọi tiền tố đều an toàn”.

Nếu miền của bài cho phép tổng vượt `long`, cần một biểu diễn rộng hơn (ví dụ `BigInteger`) và điều chỉnh giả thiết chi phí. Với yêu cầu chỉ tính **tổng modulo m**, có thể lưu tổng tiền tố modulo m nếu bài toán cần đúng phần dư, nhưng phải xử lý dấu âm và tránh tràn khi cộng/trừ trong mô-đun. Không thay thế tổng chính xác bằng modulo nếu đề bài cần giá trị tổng thật.

Đặc biệt, **số âm không làm sai công thức tổng tiền tố**. Nó chỉ ảnh hưởng đến tính đơn điệu của tiền tố: khi các phần tử có thể âm, `prefix[i]` không nhất thiết tăng. Vì thế các kỹ thuật dựa vào tính đơn điệu (chẳng hạn tìm kiếm nhị phân trên `prefix` để tìm một ngưỡng) không được áp dụng nếu chưa chứng minh điều kiện riêng.

## 9. Truy vấn nhiều đoạn, chi phí tiền xử lý và cách chọn phương án

Giả sử n = 100.000 và q = 100.000, nhiều truy vấn hỏi các đoạn dài gần n. Quét trực tiếp có thể cần số lượng phép cộng cùng bậc với `nq = 10^10`. Tổng tiền tố chỉ cần đọc n phần tử, thực hiện n phép cập nhật tiền tố, rồi q phép trừ để trả lời: cùng bậc với `n+q = 200.000` phép xử lý mức cao, chưa tính I/O và chi tiết môi trường chạy.

Tuy nhiên, nếu q = 1 và chỉ cần tổng của một đoạn ngắn, quét trực tiếp một lần là hợp lý: không cần dành mảng `prefix[n+1]` và không cần tiền xử lý các vị trí khác.

Để lựa chọn, hãy xác định:

- **Dữ liệu có tĩnh không?** Mọi truy vấn có dựa trên cùng một mảng không thay đổi?
- **Có bao nhiêu truy vấn?** Một truy vấn, vài truy vấn, hay hàng trăm nghìn truy vấn?
- **Có đủ RAM cho `n+1` tổng không?** Kiểu `long` dùng khoảng `8(n+1)` byte chỉ cho dữ liệu phần tử, ngoài header mảng và I/O.
- **Cần đáp án chính xác hay modulo?** Miền số có làm tràn kiểu đang chọn không?
- **Chỉ cần tổng hay còn cần min/max, số lần xuất hiện, kth, cập nhật...?** Không phải mọi phép toán trên đoạn đều xử lý bằng hiệu hai tổng tiền tố.
- **Đầu vào có đến tuần tự không?** Nếu mỗi truy vấn đến ngay sau một lần cập nhật, tổng tiền tố tĩnh có thể không phù hợp.

## 10. Khi có cập nhật phần tử: vì sao tổng tiền tố tĩnh không còn O(1) cho mọi thao tác?

Giả sử `a[i]` tăng thêm `delta`. Khi đó mọi `prefix[k]` với `k > i` đều phải tăng thêm `delta`. Nếu lưu tường minh mảng tiền tố, sửa một phần tử có thể tốn Θ(n) thời gian cập nhật trong trường hợp xấu, dù truy vấn tổng đoạn sau đó vẫn O(1).

Ví dụ `a=[3,-2,5,1]` có `prefix=[0,3,1,6,7]`. Nếu thay `a[1]` từ -2 thành 4, tức `delta=6`, các tiền tố `prefix[2], prefix[3], prefix[4]` đều phải tăng 6; tiền tố mới là `[0,3,7,12,13]`.

Với nhiều cập nhật xen kẽ nhiều truy vấn, cân nhắc:

| Loại thao tác cần hỗ trợ | Cấu trúc/chiến lược | Chi phí điển hình |
|---|---|---|
| Chỉ đọc, nhiều tổng đoạn, không cập nhật | Mảng tổng tiền tố | Xây O(n), truy vấn O(1), bộ nhớ O(n) |
| Một số ít cập nhật, rất nhiều truy vấn giữa các lần cập nhật | Có thể tái xây tiền tố sau mỗi đợt cập nhật | Mỗi lần tái xây O(n), truy vấn O(1) |
| Cập nhật một phần tử + tổng đoạn xen kẽ | **Fenwick tree (Binary Indexed Tree)** | Cập nhật O(log n), tổng tiền tố O(log n), tổng đoạn từ hai tổng tiền tố O(log n) |
| Cập nhật một phần tử + truy vấn nhiều loại phép kết hợp | **Segment tree** với phép kết hợp phù hợp | Xây O(n), cập nhật và truy vấn O(log n), thường O(n) bộ nhớ |
| Nhiều phép **cộng thêm vào cả đoạn**, cuối cùng mới cần mảng kết quả | **Mảng hiệu (difference array)** | Mỗi phép cộng đoạn O(1), kết xuất mảng O(n) |

Điều kiện quan trọng: bảng này mô tả những kịch bản có hợp đồng thao tác khác nhau. Không phải “Fenwick luôn nhanh hơn prefix”; với mảng bất biến, tổng tiền tố trả lời O(1) và đơn giản hơn.

## 11. Liên hệ với mảng hiệu và cập nhật đoạn

**Mảng hiệu** có mục tiêu gần như ngược với tổng tiền tố:

- Tổng tiền tố tiền xử lý để **đọc tổng một đoạn nhanh**.
- Mảng hiệu lưu những thay đổi biên để **cộng một giá trị vào cả đoạn nhanh**, rồi xây kết quả khi cần.

Với chỉ số 0-based và cập nhật cộng `delta` vào đoạn nửa mở `[l,r)`, có thể lưu:

`diff[l] += delta` và `diff[r] -= delta`,

với mảng `diff` có ít nhất n + 1 ô. Sau khi ghi tất cả cập nhật, duyệt cộng dồn:

`running += diff[i]`; `a[i] += running` cho `i = 0..n−1`.

Ví dụ bắt đầu từ mảng 5 số 0, cộng 3 vào `[1,4)`:

`diff = [0, 3, 0, 0, -3, 0]`

Lấy tổng tích lũy ở các vị trí `0..4` thu được `[0,3,3,3,0]`.

Một lần ghi mảng hiệu cần O(1) thao tác, nhưng để truy vấn giá trị ở vị trí bất kỳ **trước khi xây lại mảng**, có thể phải cộng dồn nhiều phần tử. Không được suy ra mảng hiệu tự động hỗ trợ cả **cập nhật đoạn O(1)** và **truy vấn tổng đoạn O(1)** trong một luồng cập nhật-truy vấn tùy ý.

Khi có cả cập nhật và truy vấn trộn lẫn, cần xem chính xác kiểu cập nhật (cộng đoạn, gán đoạn, cộng điểm...) để chọn Fenwick, segment tree hoặc kỹ thuật khác.

## 12. Mở rộng: tổng tiền tố hai chiều

Với ma trận `a` có R hàng và C cột, có thể tính tổng một hình chữ nhật bằng bảng tổng tiền tố 2D. Dùng chỉ số **1-based** cho `a[i][j]` (với `1≤i≤R, 1≤j≤C`) và bảng `P` có hàng 0, cột 0 toàn số 0.

Công thức xây dựng:

**`P[i][j] = a[i][j] + P[i−1][j] + P[i][j−1] − P[i−1][j−1]`.**

Đây là nguyên lý cộng các hình chữ nhật “bên trên” và “bên trái”, rồi trừ phần bị tính hai lần.

Tổng hình chữ nhật đóng từ góc trên trái `(r1,c1)` tới góc dưới phải `(r2,c2)`:

**`S = P[r2][c2] − P[r1−1][c2] − P[r2][c1−1] + P[r1−1][c1−1]`.**

Hàng/cột 0 bổ sung giúp công thức hoạt động cả khi hình chữ nhật chạm biên trên hoặc biên trái.

Ví dụ ma trận:

~~~text
1  2  3
4  5  6
7  8  9
~~~

Hình chữ nhật gồm hàng 2..3 và cột 2..3 có các phần tử `5,6,8,9`, tổng bằng 28. Bảng tiền tố cho biết `P[3][3]=45`, `P[1][3]=6`, `P[3][1]=12`, `P[1][1]=1`, nên `45−6−12+1=28`.

Xây bảng mất **Θ(RC)** thời gian, mỗi truy vấn hình chữ nhật O(1) theo mô hình RAM, bộ nhớ Θ(RC). Đây là mở rộng trực tiếp của bài toán tổng đoạn một chiều, với công thức bao hàm–loại trừ (inclusion–exclusion). Nếu ma trận cập nhật thường xuyên, bảng tĩnh cũng sẽ cần cập nhật nhiều ô hoặc phải dùng cấu trúc động phù hợp.

## 13. Mở rộng: đếm phần tử theo tính chất bằng tiền tố

Tổng tiền tố không chỉ cộng giá trị gốc. Nếu muốn **đếm** số phần tử thỏa điều kiện trong một đoạn, đặt:

`b[i] = 1` nếu `a[i]` thỏa điều kiện, ngược lại `b[i] = 0`.

Xây `countPrefix` trên `b`. Khi đó số phần tử thỏa điều kiện trong `[l,r)` bằng:

`countPrefix[r] − countPrefix[l]`.

Ví dụ đếm phần tử chẵn của `[3,2,6,1,8]`: mảng đánh dấu là `[0,1,1,0,1]`; tiền tố đếm là `[0,0,1,2,2,3]`. Đoạn `[1,4)` gồm `2,6,1`, có `2` số chẵn; hiệu `countPrefix[4]-countPrefix[1] = 2-0=2`.

Có thể áp dụng tương tự để đếm số âm, số lớn hơn một ngưỡng cố định, số lần một ký tự cụ thể xuất hiện, hoặc số ô được đánh dấu trong một hàng. Nếu điều kiện thay đổi theo từng truy vấn (ví dụ mỗi truy vấn có một ngưỡng khác nhau), thường không thể chỉ dùng **một** mảng tiền tố đếm; cần tiền xử lý nhiều điều kiện hoặc cấu trúc/phương pháp khác.

## 14. Kiểm thử biên và lỗi thường gặp

### Các trường hợp cần kiểm tra

| Trường hợp | Dữ liệu / truy vấn | Kết quả mong đợi |
|---|---|---|
| Một phần tử | `a=[-7]`, đoạn đóng 1-based `[1,1]` | -7 |
| Toàn mảng | `a=[3,-2,5]`, `[1,3]` | 6 |
| Đoạn bắt đầu tại phần tử đầu | `a=[3,-2,5]`, `[1,2]` | 1 |
| Đoạn kết thúc tại phần tử cuối | `a=[3,-2,5]`, `[2,3]` | 3 |
| Chỉ một phần tử | `a=[3,-2,5]`, `[2,2]` | -2 |
| Tất cả số âm | `a=[-3,-1,-2]`, `[1,3]` | -6 |
| Có số 0 | `a=[0,5,0]`, `[1,3]` | 5 |
| Đoạn rỗng theo quy ước nửa mở | `[2,2)` | 0 |
| Tổng vượt `int` | `a=[10^9,10^9,10^9]`, `[1,3]` | 3.000.000.000 bằng `long` |
| Số truy vấn lớn | Cùng mảng tĩnh, rất nhiều đoạn ngẫu nhiên | Các câu trả lời đúng và tổng thời gian gần Θ(n+q) |

Có thể dùng **đối chiếu với cách cộng trực tiếp** trên các mảng nhỏ ngẫu nhiên: xây tiền tố, xét mọi cặp biên hợp lệ `(l,r)` và so sánh `prefix[r]-prefix[l]` với tổng tính bởi vòng lặp. Cách này kiểm tra công thức chỉ số rất hiệu quả.

### Những lỗi phổ biến

1. **Nhầm kích thước mảng tiền tố:** cấp phát `prefix[n]` thay vì `prefix[n+1]` rồi truy cập `prefix[n]`. Luôn đặt ô 0 cho tổng rỗng khi dùng công thức nửa mở.
2. **Nhầm 0-based và 1-based:** dùng `prefix[R]-prefix[L]` cho truy vấn đóng 1-based làm bỏ mất phần tử tại L. Hãy viết ra bộ phần tử cụ thể và kiểm tra đoạn có một phần tử.
3. **Nhầm hai đầu bao gồm và nửa mở:** dùng `prefix[r]-prefix[l]` cho đoạn 0-based đóng `[l,r]` làm bỏ phần tử `a[r]`.
4. **Lấy hiệu sai thứ tự:** `prefix[l]-prefix[r]` trả số đối của tổng đúng, trừ trường hợp tổng bằng 0.
5. **Sử dụng `int` cho tổng:** từng phần tử vừa int không đảm bảo tổng cũng vừa int; tính cận `n × max|a[i]|` và kiểm tra thêm phép trừ.
6. **Cho rằng tiền tố tăng:** với số âm, `prefix` có thể giảm, nên không được dùng tìm kiếm nhị phân theo giá trị tiền tố khi không có tính đơn điệu.
7. **Giữ tiền tố cũ sau khi cập nhật mảng:** tổng tiền tố đã trở nên lỗi thời. Phải cập nhật lại phần liên quan hoặc chuyển sang cấu trúc động.
8. **Bỏ qua định dạng I/O:** q truy vấn có thể tạo lượng đầu ra lớn; sử dụng bộ đệm và xử lý đúng cả các số âm.
9. **Đếm sai bộ nhớ:** nếu giữ cả `a`, `prefix`, kết quả và dữ liệu tạm, mức sử dụng thực tế lớn hơn một mảng tiền tố.
10. **Áp dụng phép trừ tiền tố cho phép toán khác không có cấu trúc phù hợp:** ví dụ cực tiểu đoạn không bằng hiệu hai “tiền tố cực tiểu”; công thức tổng dựa vào phép cộng có phép nghịch đảo là phép trừ.

### Checklist trước khi dùng trong một bài thuật toán

- Dãy có **bất biến** trong suốt các truy vấn không?
- Kích thước n, số truy vấn q và giới hạn bộ nhớ là bao nhiêu?
- Truy vấn dùng chỉ số **0-based hay 1-based**, đoạn **đóng hay nửa mở**?
- `prefix[0]=0`, độ dài `n+1` và bất biến xây dựng đã đúng chưa?
- Các tổng tiền tố, hiệu hai tiền tố và số trung gian có nằm trong miền kiểu dữ liệu không?
- Truy vấn tại đầu, cuối, một phần tử, toàn mảng và (nếu hợp lệ) đoạn rỗng đã được kiểm thử chưa?
- Có truy vấn/cập nhật khác ngoài tổng đoạn không? Nếu có, mô hình xử lý tĩnh còn đúng không?
- Đã tách chi phí xây dựng, mỗi truy vấn, bộ nhớ và I/O chưa?

**Ghi nhớ:** với dãy tĩnh, tổng tiền tố biến truy vấn tổng đoạn từ việc cộng lại nhiều phần tử thành **hiệu của hai tổng tích lũy**. Công thức gọn nhưng đòi hỏi quản lý chỉ số chính xác và bảo đảm các phép cộng/trừ không bị tràn theo miền đầu vào.